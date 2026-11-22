# Định dạng tự động trong trình soạn thảo DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích định dạng tự động (automatic formatting) và vai trò của nó trong trình soạn thảo DSL.
- Phân biệt formatter với lexer, parser, validator, linter và refactoring tool.
- Mô tả cách formatter dùng cú pháp hoặc AST để in lại mã nguồn nhất quán.
- Thiết kế quy tắc cho thụt lề, khoảng trắng, xuống dòng, dấu ngoặc, danh sách và biểu thức.
- Giữ đúng ngữ nghĩa, comment, chuỗi, chú thích định dạng và vị trí nguồn khi định dạng.
- Hiểu các chế độ format toàn tệp, format vùng chọn và format khi lưu.
- Xử lý mã chưa hoàn chỉnh trong lúc người dùng đang gõ.
- Tích hợp formatter với editor, language server và cấu hình dự án.
- Kiểm thử tính ổn định, idempotence và khả năng bảo toàn hành vi của formatter.

## 1. Định dạng tự động là gì?

Định dạng tự động (automatic formatting) là quá trình trình bày lại mã nguồn theo một bộ quy tắc thống nhất. Formatter có thể điều chỉnh khoảng trắng, thụt lề, xuống dòng, vị trí dấu ngoặc, cách đặt dấu phẩy và cách trình bày biểu thức để mã dễ đọc và nhất quán hơn.

Ví dụ, người dùng có thể viết:

~~~text
rule "bulk_discount"{when order.quantity>=10 then order.discount=5%}
~~~

Formatter có thể trình bày lại:

~~~text
rule "bulk_discount" {
    when order.quantity >= 10
    then order.discount = 5%
}
~~~

Cấu trúc và ý nghĩa của rule được giữ nguyên; thay đổi chủ yếu nằm ở cách trình bày.

Trong trình soạn thảo DSL, formatter giúp người viết tập trung vào nội dung quy tắc, đồng thời giữ mã nguồn theo phong cách chung của dự án. Nó cũng giúp review thay đổi, so sánh phiên bản và nhận biết cấu trúc lồng nhau dễ dàng hơn.

Formatter thường được gọi bằng các tên như pretty printer, code formatter hoặc source formatter. Các tên này có thể nhấn mạnh những khía cạnh khác nhau, nhưng đều hướng đến việc tạo ra cách trình bày nhất quán từ một chương trình đã được phân tích.

## 2. Vì sao trình soạn thảo DSL cần formatter?

DSL thường được thiết kế để người dùng nghiệp vụ, nhà phân tích hoặc lập trình viên mô tả quy tắc trong một cú pháp gần với miền công việc. Khi chương trình lớn dần, cách trình bày có ảnh hưởng đáng kể đến khả năng đọc và bảo trì.

Formatter đem lại một số lợi ích:

- **Nhất quán:** mọi tệp có cùng quy tắc thụt lề và khoảng trắng.
- **Dễ đọc:** khối lệnh và biểu thức lồng nhau có cấu trúc trực quan.
- **Review dễ hơn:** diff tập trung vào thay đổi nội dung thay vì phong cách cá nhân.
- **Giảm tranh luận về style:** nhóm dùng một cấu hình chung.
- **Hỗ trợ học DSL:** mã được trình bày theo một hình thức dễ nhận biết.
- **Giảm lỗi thao tác:** dấu ngoặc, dấu phẩy và xuống dòng được đặt theo quy tắc rõ ràng.
- **Tích hợp công cụ:** formatter có thể được chạy khi lưu, trong CI hoặc trước khi xuất bản cấu hình.

Ví dụ, hai người viết cùng một rule theo hai phong cách:

~~~text
rule "eligible" {
when customer.age >= 18 then allow()
}
~~~

~~~text
rule "eligible"
{
    when customer.age >= 18
    then allow()
}
~~~

Cả hai có thể hợp lệ, nhưng formatter của dự án có thể đưa về một phong cách chuẩn để mã nguồn không bị phân mảnh.

### 2.1. Formatter không sửa ý nghĩa chương trình

Mục tiêu cơ bản của formatter là bảo toàn cấu trúc và ngữ nghĩa của chương trình. Nó không tự ý đổi điều kiện nghiệp vụ, thay tên biến, thêm bước xử lý hoặc tối ưu thuật toán.

Nếu một biểu thức có lỗi cú pháp, formatter có thể không thể xác định cách trình bày đầy đủ. Khi đó, nó cần một chiến lược xử lý mã chưa hoàn chỉnh thay vì đoán cấu trúc rồi viết lại tùy tiện.

### 2.2. Formatter không thay thế người viết

Formatter giúp chuẩn hóa hình thức. Người viết vẫn quyết định nội dung rule, tên biến, cấu trúc nghiệp vụ và cách chia chương trình thành các phần hợp lý.

## 3. Phân biệt formatter với các công cụ khác

Nhiều công cụ làm việc trên cùng mã nguồn nhưng có trách nhiệm khác nhau.

| Công cụ | Trách nhiệm | Ví dụ |
|---|---|---|
| Lexer | Chia ký tự thành token | Nhận diện từ khóa, định danh và toán tử |
| Parser | Tạo cấu trúc cú pháp | Phân tích rule có điều kiện và action |
| Formatter | Trình bày lại mã | Thụt lề block, thêm khoảng trắng |
| Validator | Kiểm tra ràng buộc | Rule phải có ít nhất một action |
| Linter | Phát hiện vấn đề về style hoặc chất lượng | Cảnh báo tên biến quá ngắn |
| Refactoring tool | Thay đổi cấu trúc có chủ đích | Đổi tên symbol trên toàn dự án |
| Optimizer | Thay đổi biểu diễn thực thi để tăng hiệu năng | Constant folding |

Một formatter có thể gọi parser để hiểu cấu trúc, nhưng nó không phải parser. Một linter có thể đề xuất format, nhưng cảnh báo lint không đồng nghĩa với việc formatter tự sửa nội dung.

### 3.1. Formatting và refactoring

Formatting thường thay đổi whitespace và cách trình bày. Refactoring có thể đổi tên, di chuyển hoặc tái cấu trúc node trong chương trình. Hai thao tác có thể cùng xuất hiện trong editor nhưng cần được phân biệt để người dùng biết loại thay đổi nào sẽ được áp dụng.

### 3.2. Formatting và normalization

Normalization đưa mô hình về một biểu diễn chuẩn phục vụ compiler. Formatting tạo ra văn bản có cách trình bày nhất quán. Formatter có thể dựa vào canonical AST, nhưng không nhất thiết phải thay đổi mô hình ngữ nghĩa.

### 3.3. Formatting và validation

Mã hợp lệ vẫn có thể được trình bày kém. Ngược lại, formatter có thể trình bày một phần mã sai cú pháp mà không thể xác nhận chương trình hợp lệ. Validation cần được thực hiện bởi các bước tương ứng.

## 4. Formatter hoạt động như thế nào?

Có nhiều cách triển khai formatter. Với DSL có grammar rõ ràng, cách phổ biến là phân tích mã nguồn rồi in lại từ cấu trúc cú pháp.

Một pipeline khái niệm:

~~~text
Mã nguồn
   |
   v
Lexer
   |
   v
Parser
   |
   v
AST hoặc Syntax Tree
   |
   v
Formatter / Pretty Printer
   |
   v
Văn bản đã định dạng
~~~

### 4.1. Đọc token và khoảng trắng

Formatter có thể dùng token stream để nhận diện dấu ngoặc, dấu phẩy và từ khóa. Cách này đơn giản hơn parser nhưng khó xử lý các cấu trúc lồng phức tạp và những trường hợp cùng token có vai trò khác nhau theo ngữ cảnh.

### 4.2. Dựa trên AST

AST mô tả cấu trúc chương trình. Formatter duyệt node và quyết định cách trình bày mỗi loại node.

Ví dụ:

~~~text
Rule
  name: "bulk_discount"
  condition:
    GreaterOrEqual
      Property(order, quantity)
      Integer(10)
  action:
    Assign
      Property(order, discount)
      Percentage(5)
~~~

Formatter biết đâu là tên rule, đâu là điều kiện và đâu là action. Nó có thể đặt mỗi phần ở dòng riêng, thụt lề theo cấu trúc và chèn khoảng trắng quanh toán tử.

### 4.3. Concrete Syntax Tree

AST thường bỏ qua một số chi tiết cú pháp như dấu ngoặc dư, comment hoặc token gốc. Concrete Syntax Tree (CST) có thể giữ lại nhiều chi tiết nguồn hơn. Formatter phục vụ editor thường hưởng lợi từ CST vì nó cần bảo toàn comment, dấu phân cách và các phần cú pháp mà AST có thể đã loại bỏ.

### 4.4. Token và trivia

Một số parser lưu whitespace và comment như trivia gắn với token. Formatter có thể dùng thông tin đó để giữ comment gần vị trí ban đầu hoặc giữ cách viết đặc biệt được người dùng chủ động chọn.

### 4.5. Pretty printing qua document model

Một cách thiết kế formatter là tạo ra một mô hình tài liệu trung gian (document model) thay vì nối chuỗi trực tiếp. Mô hình có thể chứa:

- Text: đoạn văn bản cố định.
- Line: điểm có thể hoặc phải xuống dòng.
- Soft line: có thể là khoảng trắng hoặc xuống dòng tùy độ rộng.
- Indent: tăng mức thụt lề cho vùng con.
- Group: nhóm nội dung được thử trình bày trên một dòng nếu đủ chỗ.

Sau đó, pretty printer chọn cách bố trí phù hợp với chiều rộng dòng.

Ví dụ khái niệm:

~~~text
Group(
  "call(" +
  Indent(
    SoftLine +
    Join("," + SoftLine, arguments)
  ) +
  SoftLine +
  ")"
)
~~~

Nếu lời gọi ngắn, formatter có thể in trên một dòng. Nếu dài, nó có thể xuống dòng và thụt lề các đối số.

## 5. Quy tắc khoảng trắng

Khoảng trắng là phần dễ nhận thấy nhất của định dạng tự động. Mỗi DSL cần quy định vị trí có khoảng trắng, vị trí không có khoảng trắng và nơi khoảng trắng có thể thay đổi theo độ dài dòng.

### 5.1. Khoảng trắng quanh toán tử

Một style phổ biến đặt một dấu cách quanh toán tử nhị phân:

~~~text
total = quantity * unitPrice + shippingFee
active = order.status == "PAID"
~~~

Toán tử một ngôi thường không có khoảng trắng giữa nó và toán hạng:

~~~text
isInvalid = !valid
negative = -amount
~~~

Đây chỉ là quy ước. DSL có thể chọn style khác, nhưng cần nhất quán và không làm thay đổi cách lexer nhận diện token.

### 5.2. Dấu phẩy

Có thể đặt dấu phẩy sát phần tử trước và một dấu cách sau:

~~~text
sendEmail(customer, subject, body)
~~~

Trong danh sách nhiều dòng:

~~~text
permissions = [
    Read,
    Write,
    Approve,
]
~~~

Trailing comma có thể được cho phép để diff dễ đọc, nhưng formatter cần theo grammar của DSL.

### 5.3. Dấu hai chấm

Trong DSL dùng dấu hai chấm để mở block hoặc khai báo trường, quy tắc khoảng trắng cần được xác định rõ:

~~~text
if order.total > 100:
    approve(order)
~~~

Với map hoặc object:

~~~text
customer = {
    name: "An",
    active: true,
}
~~~

### 5.4. Dấu ngoặc

Formatter cần quy định khoảng trắng quanh dấu ngoặc tròn, vuông và nhọn:

~~~text
calculate(order.total)
items[index]
rule "discount" {
    ...
}
~~~

Không nên thêm khoảng trắng tùy tiện bên trong dấu ngoặc nếu style không yêu cầu.

### 5.5. Dấu chấm truy cập thuộc tính

Thông thường không đặt khoảng trắng quanh dấu chấm:

~~~text
order.customer.address
~~~

Nếu DSL dùng dấu chấm cho một cú pháp đặc biệt khác, formatter phải dựa vào cấu trúc cú pháp thay vì xử lý mọi dấu chấm giống nhau.

### 5.6. Khoảng trắng trong chuỗi

Formatter không được thay đổi khoảng trắng bên trong string literal theo cách làm thay đổi giá trị chuỗi.

~~~text
message = "  Please keep this spacing.  "
~~~

Khoảng trắng đầu và cuối có thể là dữ liệu. Formatter phải giữ nguyên nội dung literal trừ khi DSL có một quy tắc riêng cho việc chuẩn hóa chuỗi.

## 6. Thụt lề và cấu trúc block

Thụt lề cho thấy quan hệ cha-con giữa các khối. DSL có thể dùng dấu ngoặc nhọn, dấu hai chấm hoặc thụt lề làm thành phần cú pháp.

### 6.1. Block dùng dấu ngoặc

~~~text
rule "free_shipping" {
    when order.total >= 500000
    then order.shippingFee = 0
}
~~~

Formatter cần tăng indent sau dấu mở block và giảm indent trước dấu đóng block.

### 6.2. Block lồng nhau

~~~text
workflow "approval" {
    if order.total > 1000000 {
        if customer.isVip {
            approve(order)
        } else {
            requestManagerReview(order)
        }
    }
}
~~~

Mỗi cấp lồng thường tăng một đơn vị indent. Khi rời block, indent trở về mức của block cha.

### 6.3. DSL dùng thụt lề làm cú pháp

Một số DSL dùng indentation-sensitive syntax:

~~~text
rule "discount":
    when order.total > 100
    then:
        set order.discount = 5
        notify(order.owner)
~~~

Trong loại ngôn ngữ này, thụt lề có thể ảnh hưởng trực tiếp đến parse. Formatter phải tuân thủ grammar và không được đổi indent theo cách thay đổi block.

### 6.4. Tabs và spaces

Dự án cần chọn tab hoặc spaces, cũng như độ rộng indent. Nếu dùng spaces, formatter thường chèn một số lượng dấu cách cố định cho mỗi cấp. Nếu dùng tab, editor và terminal có thể hiển thị độ rộng khác nhau.

Cần quy định rõ kiểu indent, độ rộng indent, có chuyển tab hiện có thành spaces không và cách xử lý tab trong chuỗi hoặc nội dung nguyên văn.

### 6.5. Continuation line

Biểu thức dài có thể được xuống dòng sau toán tử hoặc dấu phẩy:

~~~text
let eligible =
    customer.isActive
    and order.total >= minimumTotal
    and order.items.count > 0
~~~

Formatter cần có quy tắc continuation indent để người đọc nhận ra các dòng thuộc cùng một biểu thức.

## 7. Xuống dòng và giới hạn chiều rộng

Formatter thường có một cấu hình độ rộng dòng (print width), ví dụ 80, 100 hoặc 120 ký tự. Đây là mục tiêu trình bày, không nhất thiết là giới hạn cứng.

### 7.1. Nhóm biểu thức ngắn

~~~text
let total = quantity * unitPrice + shippingFee
~~~

Nếu đủ độ rộng, formatter có thể giữ trên một dòng.

### 7.2. Biểu thức dài

~~~text
let eligible =
    customer.isActive
    and order.total >= minimumTotal
    and order.shippingAddress.country == "VN"
~~~

Nếu một biểu thức vượt độ rộng, formatter có thể chọn điểm ngắt hợp lý.

### 7.3. Lời gọi hàm nhiều đối số

~~~text
sendNotification(
    recipient = customer.email,
    subject = "Order confirmed",
    message = buildOrderMessage(order),
)
~~~

Một lời gọi ngắn có thể ở một dòng; lời gọi dài có thể chuyển sang dạng nhiều dòng.

### 7.4. Không cắt chuỗi tùy tiện

Nếu một string literal dài, formatter không thể tự ý chèn newline vào giữa giá trị. Nếu DSL hỗ trợ nối chuỗi hoặc multiline string, formatter có thể dùng cú pháp đó khi chắc chắn bảo toàn giá trị. Nếu không, nó nên để nguyên dòng dài hoặc áp dụng quy tắc đã được ngôn ngữ định nghĩa.

### 7.5. Blank line

Blank line giúp phân tách các nhóm khai báo hoặc logic. Formatter có thể giữ một dòng trống giữa các nhóm khai báo, không tạo nhiều dòng trống liên tiếp, giữ dòng trống có ý nghĩa trong multiline text và không tự tách một biểu thức chỉ vì nó dài.

### 7.6. End-of-file newline

Nhiều công cụ yêu cầu một newline ở cuối tệp. Formatter có thể thêm newline cuối cùng nếu cấu hình dự án yêu cầu. Đây là quy tắc trình bày phổ biến, nhưng cần được áp dụng nhất quán.

## 8. Quy tắc trình bày theo loại cấu trúc

Một formatter tốt cần biết từng node trong DSL có cách trình bày phù hợp.

### 8.1. Khai báo

~~~text
let minimumTotal = 500000
constant DEFAULT_TIMEOUT = 30 seconds
type CustomerId = String
~~~

Có thể quy định cách đặt dấu cách quanh dấu gán, kiểu và từ khóa.

### 8.2. Rule

~~~text
rule "high_value_order" {
    when order.total >= 1000000
    then:
        set order.priority = "HIGH"
        notify(order.owner)
}
~~~

Các phần name, condition và action nên có cách trình bày nhất quán.

### 8.3. Danh sách

~~~text
allowedRegions = [
    "north",
    "central",
    "south",
]
~~~

Danh sách có thể trình bày trên một dòng nếu ngắn hoặc nhiều dòng nếu dài.

### 8.4. Object và map

~~~text
customer = {
    id: 1024,
    name: "Lan",
    active: true,
}
~~~

Formatter cần giữ đúng thứ tự trường nếu thứ tự là một phần của semantics hoặc được người dùng quan tâm. Nếu map không có thứ tự, formatter có thể giữ thứ tự nguồn hoặc dùng thứ tự ổn định theo cấu hình; không nên tự thay đổi semantics.

### 8.5. Match hoặc switch

~~~text
match order.status {
    case "NEW":
        validate(order)
    case "PAID":
        prepareShipment(order)
    default:
        reportUnknownStatus(order)
}
~~~

Mỗi case có indent và break/arrow theo grammar của DSL.

### 8.6. Pipeline

~~~text
orders
    .filter(order => order.status == "PAID")
    .map(order => order.total)
    .sum()
~~~

Formatter cần quy định cách xuống dòng quanh dấu chấm, toán tử pipeline và lambda.

### 8.7. Query DSL

~~~text
from orders
where status == "PAID"
select customerId, total
order by total descending
~~~

Các mệnh đề thường được đặt trên các dòng riêng để người đọc nhận ra cấu trúc truy vấn.

### 8.8. Workflow

~~~text
workflow "purchase" {
    step "validate":
        validateOrder(order)

    step "approve":
        waitForApproval(order)

    step "complete":
        createPurchaseOrder(order)
}
~~~

Formatter nên nhất quán với cách trình bày block và step của DSL.

## 9. Comment và tài liệu nhúng

Comment là một phần quan trọng của mã nguồn. Formatter cần giữ chúng ở vị trí hợp lý.

### 9.1. Comment một dòng

~~~text
# Chỉ áp dụng cho đơn hàng đã thanh toán
when order.status == "PAID":
    ship(order)
~~~

Formatter có thể căn comment theo block hoặc giữ comment trước node tương ứng.

### 9.2. Comment cuối dòng

~~~text
timeout = 30 seconds  # Giới hạn thời gian xử lý
~~~

Formatter có thể căn comment cuối dòng theo quy tắc. Tuy nhiên, căn tất cả comment vào cùng một cột có thể tạo ra nhiều khoảng trắng và diff lớn. Cần chọn style rõ ràng.

### 9.3. Comment nhiều dòng

~~~text
/*
 * Quy tắc ưu tiên khách hàng thành viên.
 * Cần được rà soát trước khi thay đổi.
 */
rule "member_priority" {
    ...
}
~~~

Formatter nên giữ nội dung và cấu trúc comment, chỉ điều chỉnh indent nếu quy tắc cho phép.

### 9.4. Comment gắn với node

Comment ngay trước một node thường giải thích node đó. Khi formatter trình bày lại node, comment cần đi cùng node liên quan. Formatter thuần túy không nên tự sắp xếp lại khai báo nếu không có yêu cầu khác.

### 9.5. Comment định dạng đặc biệt

Một số hệ thống dùng directive trong comment để điều khiển formatter:

~~~text
# format: off
legacyBlock =   {   keepOriginalSpacing( )   }
# format: on
~~~

Formatter cần nhận diện directive và bỏ qua vùng được đánh dấu. Directive phải có quy tắc đóng/mở rõ ràng, kể cả khi vùng đó chứa comment hoặc block lồng.

### 9.6. Documentation comment

Comment tài liệu có thể dùng Markdown hoặc cú pháp đặc biệt. Formatter nên giữ nội dung, tránh reflow nếu việc xuống dòng có thể ảnh hưởng ví dụ code, bảng hoặc danh sách.

### 9.7. Nội dung nhúng

Một DSL có thể nhúng SQL, JSON, regex hoặc template. Formatter cần biết vùng nào thuộc ngôn ngữ chủ và vùng nào thuộc ngôn ngữ nhúng. Có thể giữ nguyên vùng nhúng, gọi formatter chuyên dụng, chỉ format delimiter bên ngoài hoặc dùng chế độ format riêng được cấu hình.

Không nên áp dụng quy tắc khoảng trắng của DSL chủ vào SQL string hoặc regex literal.

## 10. Bảo toàn chuỗi, literal và nội dung nguyên văn

Formatter không được làm thay đổi giá trị của literal chỉ vì muốn mã đẹp hơn.

### 10.1. Chuỗi thường

~~~text
message = "  Keep both leading and trailing spaces.  "
~~~

Hai khoảng trắng đầu và cuối có thể là dữ liệu. Formatter phải giữ nguyên.

### 10.2. Escape sequence

~~~text
message = "Line one\nLine two"
path = "C:\\temp\\orders"
~~~

Formatter có thể chuẩn hóa cách viết escape nếu DSL quy định các dạng tương đương, nhưng việc đó cần được xác định rõ. Không nên đổi escape chỉ dựa trên phỏng đoán.

### 10.3. Raw string

~~~text
pattern = r"\d+\s+items"
~~~

Nội dung raw string thường không diễn giải escape. Formatter cần giữ chính xác các ký tự trong literal.

### 10.4. Multiline string

~~~text
message = """
    Order confirmed.
    Please prepare shipment.
"""
~~~

Indent bên trong multiline string có thể là một phần của giá trị. Formatter cần biết DSL có loại bỏ common indentation hay không. Nếu không, dịch chuyển các dòng bên trong có thể đổi nội dung.

### 10.5. Heredoc

Với heredoc, delimiter kết thúc và quy tắc thụt lề có thể ảnh hưởng giá trị literal. Formatter chỉ được thay đổi indent khi semantics của heredoc bảo đảm giá trị không đổi.

### 10.6. Number literal

Một số literal có thể có nhiều cách viết như 1000, 1_000 hoặc 1e3. Formatter có thể chuẩn hóa nếu DSL xác định chúng tương đương, nhưng nên giữ kiểu, độ chính xác và đơn vị. Nếu style yêu cầu giữ cách viết gốc, lưu raw lexeme trong syntax tree.

## 11. Format toàn tệp và format vùng chọn

Trình soạn thảo thường cung cấp nhiều cách gọi formatter.

### 11.1. Format document

Format document định dạng toàn bộ tệp. Đây là thao tác phổ biến khi người dùng chọn Format Document hoặc lưu tệp với tùy chọn format on save.

Quy trình:
1. Lấy văn bản hiện tại.
2. Phân tích cú pháp hoặc tạo syntax tree.
3. Tạo document model.
4. Chọn line break và indent.
5. Tạo văn bản mới.
6. So sánh với văn bản cũ.
7. Áp dụng thay đổi vào editor và cập nhật selection/cursor phù hợp.

### 11.2. Format selection

Format selection chỉ định dạng vùng được chọn. Đây là thao tác hữu ích khi người dùng chỉ muốn chuẩn hóa một block.

Khó khăn:
- Selection có thể bắt đầu hoặc kết thúc giữa một node.
- Vùng chọn có thể thiếu dấu mở/đóng block.
- Comment ở ranh giới có thể thuộc node trước hoặc node sau.
- Formatter cần xác định phạm vi cú pháp lớn nhất phù hợp.

Một cách làm là mở rộng selection đến các node cú pháp hoàn chỉnh, định dạng chúng rồi chỉ áp dụng edit trong vùng tương ứng. Editor cần giữ selection hợp lý sau khi format.

### 11.3. Format range

Một số editor gửi một range cụ thể. Formatter cần trả về các text edit trong range đó. Nếu formatter phải xem ngữ cảnh bên ngoài để xác định indent, nó vẫn có thể đọc AST lớn hơn nhưng chỉ sửa phần được phép.

### 11.4. Format on save

Khi lưu tệp, editor có thể tự gọi formatter. Người dùng thường mong muốn:
- Không có thay đổi nếu mã đã đúng style.
- Không làm mất nội dung.
- Lưu không bị treo vì formatter chạy quá lâu.
- Lỗi format được báo rõ.
- File được lưu với encoding và line ending theo cấu hình.

### 11.5. Format on type

Editor có thể format một phần khi người dùng gõ ký tự như dấu đóng block, dấu chấm phẩy hoặc newline. Đây thường là formatting cục bộ, cần độ trễ thấp và không nên viết lại toàn bộ tệp sau mỗi phím bấm.

### 11.6. Format paste

Khi người dùng dán một đoạn code, editor có thể tự điều chỉnh indent của đoạn dán theo vị trí mới. Cần phân biệt paste formatting với format document để không thay đổi các đoạn văn bản không liên quan.

## 12. Mã chưa hoàn chỉnh khi người dùng đang gõ

Trong editor, mã nguồn thường không hợp lệ tạm thời. Người dùng có thể đang nhập một block chưa đóng hoặc một biểu thức chưa hoàn chỉnh.

Ví dụ:

~~~text
rule "discount" {
    when order.total >
~~~

Parser đầy đủ có thể báo lỗi vì biểu thức chưa xong. Nếu formatter từ chối mọi mã lỗi, trải nghiệm gõ sẽ kém.

### 12.1. Tolerant parsing

Formatter cho editor có thể dùng parser chịu lỗi (error-tolerant parser) để tạo syntax tree một phần. Nó giữ các node hợp lệ và đánh dấu vùng chưa hoàn chỉnh.

### 12.2. Bảo toàn vùng lỗi

Nếu không thể xác định cấu trúc, formatter có thể giữ nguyên vùng đó và chỉ format các vùng chắc chắn. Cần tránh đoán dấu đóng hoặc tự thêm token làm thay đổi ý định người dùng.

### 12.3. Format đến điểm an toàn

Formatter có thể chỉ format các block hoàn chỉnh trước vị trí lỗi. Ví dụ, các khai báo ở đầu tệp có thể được format dù người dùng đang gõ một biểu thức ở cuối.

### 12.4. Không sửa nội dung đang nhập một cách bất ngờ

Format on type cần thay đổi nhỏ, dễ dự đoán. Nếu mỗi lần gõ một ký tự mà formatter di chuyển nhiều dòng, cursor có thể nhảy và làm gián đoạn người dùng.

### 12.5. Cursor và selection mapping

Sau khi formatter thay đổi văn bản, editor cần ánh xạ cursor và selection từ vị trí cũ sang vị trí mới. Có thể dùng text edits có offset hoặc mapping theo token/node. Nếu chỉ thay toàn bộ document bằng một chuỗi mới, cursor dễ bị đặt sai vị trí.

## 13. Formatter và Language Server Protocol

Một DSL editor có thể dùng Language Server Protocol (LSP) để giao tiếp với language server. LSP định nghĩa các yêu cầu formatting phổ biến.

Các thao tác thường gặp:
- textDocument/formatting: format toàn document.
- textDocument/rangeFormatting: format một vùng.
- textDocument/onTypeFormatting: format khi gõ một ký tự nhất định.

Language server trả về danh sách text edit. Editor áp dụng các edit đó vào document.

### 13.1. Text edit

Một text edit gồm range cần thay và nội dung thay thế. Formatter nên trả về các edit không xung đột, có thứ tự và dùng đúng encoding/position convention mà giao thức yêu cầu.

### 13.2. Document version

Nếu văn bản thay đổi trong lúc formatter đang chạy, edit cũ có thể không còn áp dụng đúng. Client/server cần dùng document version hoặc cơ chế đồng bộ để tránh áp dụng edit lên phiên bản khác.

### 13.3. Cancellation

Với tài liệu lớn, người dùng có thể tiếp tục gõ hoặc đóng tệp trong khi formatter đang chạy. Server nên hỗ trợ hủy tác vụ khi có thể và không áp dụng kết quả lỗi thời.

### 13.4. Capability negotiation

Client có thể hỗ trợ document formatting, range formatting hoặc on-type formatting. Server chỉ nên quảng bá các khả năng mà nó thực sự triển khai.

### 13.5. Lỗi giao tiếp

Nếu server không thể format vì parser lỗi hoặc cấu hình không hợp lệ, nó nên trả lỗi phù hợp hoặc không tạo edit. Không nên trả về văn bản rỗng khiến editor xóa toàn bộ tệp.

## 14. Cấu hình phong cách định dạng

Formatter cần có bộ cấu hình để nhóm dự án kiểm soát style. Cấu hình có thể nằm trong file dự án, workspace settings hoặc user settings.

Ví dụ:

~~~text
format {
    indentStyle = "spaces"
    indentSize = 4
    lineWidth = 100
    endOfLine = "lf"
    insertFinalNewline = true
    trailingComma = "multiline"
    braceStyle = "same-line"
}
~~~

Đây là cú pháp minh họa; định dạng cấu hình thực tế phụ thuộc công cụ.

### 14.1. Project configuration và user configuration

Project configuration xác định style chung cho repository. User configuration có thể điều chỉnh cách editor hiển thị nhưng không nên âm thầm ghi đè style dự án khi format on save, nếu mục tiêu là tạo kết quả thống nhất cho cả nhóm.

### 14.2. Thứ tự ưu tiên

Một thứ tự có thể là:
1. Cấu hình dự án.
2. Cấu hình workspace.
3. Cấu hình người dùng.
4. Giá trị mặc định của formatter.

Cần công bố rõ để người dùng biết setting nào đang có hiệu lực.

### 14.3. Cấu hình không hợp lệ

Nếu indentSize âm hoặc lineWidth bằng 0, formatter cần báo cấu hình không hợp lệ và dùng fallback xác định hoặc dừng format. Không nên âm thầm chọn giá trị khác mà không thông báo.

### 14.4. Phiên bản cấu hình

Khi formatter thay đổi quy tắc mặc định, dự án có thể cần version hoặc pin formatter version để kết quả không đổi ngoài ý muốn giữa các máy.

### 14.5. Cấu hình theo file hoặc vùng

Một dự án có thể có file DSL sinh tự động, file legacy hoặc vùng cần giữ nguyên. Có thể dùng pattern theo đường dẫn hoặc directive trong file để chọn cấu hình riêng. Cần tránh tạo quá nhiều biến thể style khiến repository thiếu nhất quán.

## 15. Line ending, encoding và ký tự đặc biệt

Formatter thay đổi văn bản nên cần xử lý đúng quy ước tệp.

### 15.1. LF và CRLF

LF dùng một ký tự newline; CRLF dùng cặp ký tự. Nếu formatter đổi line ending toàn bộ tệp, diff có thể lớn dù nội dung logic không đổi.

Có thể giữ line ending hiện tại, dùng cấu hình dự án, dùng EditorConfig hoặc cơ chế tương đương, hoặc chuẩn hóa toàn bộ file theo chính sách repository.

### 15.2. Encoding

Formatter nên giữ encoding nguồn hoặc dùng encoding dự án đã quy định. Không nên chuyển một file sang encoding khác một cách bất ngờ, đặc biệt nếu file chứa ký tự Unicode.

### 15.3. BOM

Nếu file có BOM, formatter cần giữ hoặc loại bỏ theo cấu hình. Việc xử lý BOM cần nhất quán giữa editor và công cụ dòng lệnh.

### 15.4. Tab trong nội dung

Tab dùng để indent code có thể được chuyển đổi theo style. Tab bên trong string hoặc heredoc có thể là dữ liệu và phải được giữ nguyên.

### 15.5. Unicode và độ rộng hiển thị

Độ dài một dòng theo code point có thể khác độ rộng hiển thị. Ký tự tiếng Việt có dấu, ký tự kết hợp hoặc ký tự Đông Á có thể khiến tính toán print width không giống số code unit. Formatter cần dùng một quy ước nhất quán và tránh cắt literal dựa trên phép đếm ký tự đơn giản.

## 16. Bảo toàn comment, directive và thứ tự nguồn

Formatter thường không nên thay đổi thứ tự khai báo nếu thứ tự đó có ý nghĩa hoặc người dùng mong muốn giữ nguyên.

### 16.1. Comment thuộc về node nào?

Comment trước một node có thể là leading comment. Comment sau node có thể là trailing comment. Comment giữa các token có thể thuộc một cấu trúc hoặc vùng trivia riêng.

Parser/CST cần giữ đủ thông tin để formatter đặt comment đúng vị trí.

### 16.2. Comment ở ranh giới

~~~text
let total = order.total  # tổng đơn hàng
# Chỉ xử lý đơn đã thanh toán
if order.status == "PAID":
    ship(order)
~~~

Formatter cần giữ comment cuối dòng với khai báo total và comment phía trên if với điều kiện.

### 16.3. Comment trong block

Comment có thể nằm giữa các action và giải thích nhóm hành động. Không nên tự di chuyển comment sang đầu hoặc cuối block chỉ để căn lề.

### 16.4. Directive

Một số comment điều khiển formatter, linter hoặc compiler. Formatter cần phân biệt comment tài liệu và directive, giữ đúng phạm vi ảnh hưởng.

### 16.5. Thứ tự khai báo

Một số DSL coi rule là tập hợp không thứ tự, nhưng nhiều DSL thực thi theo thứ tự nguồn. Formatter nên giữ thứ tự trừ khi có một thao tác sắp xếp riêng và semantics cho phép.

## 17. Format ổn định và idempotence

Một formatter tốt nên idempotent: chạy nhiều lần không tiếp tục thay đổi kết quả.

~~~text
format(format(source)) = format(source)
~~~

### 17.1. Vì sao idempotence quan trọng?

- Format on save không tạo thay đổi lặp.
- CI không báo diff mới sau mỗi lần chạy.
- Nhiều editor cho cùng kết quả.
- Người dùng không phải chạy formatter nhiều lần để đạt style ổn định.

### 17.2. Nguyên nhân không idempotent

- Hai quy tắc xuống dòng mâu thuẫn.
- Một pass thêm dấu phẩy nhưng pass khác xóa nó.
- Comment bị gắn vào node khác sau mỗi lần parse.
- Line ending bị đổi qua lại.
- Cấu hình độ rộng dòng được áp dụng không nhất quán.
- Formatter và parser hiểu khác nhau về cấu trúc.

### 17.3. Quy tắc ưu tiên

Nếu nhiều quy tắc có thể áp dụng, cần có thứ tự ưu tiên. Ví dụ, formatter có thể ưu tiên giữ nhóm biểu thức logic, sau đó mới chọn điểm xuống dòng theo print width.

### 17.4. Deterministic output

Cùng một nguồn, cùng cấu hình và cùng phiên bản formatter nên tạo cùng đầu ra. Không để kết quả phụ thuộc thứ tự duyệt map không ổn định, locale máy hoặc thời điểm chạy.

## 18. Format khi mã có lỗi cú pháp

Mã đang viết dở hoặc có lỗi là tình huống bình thường trong editor.

### 18.1. Formatter yêu cầu AST hoàn chỉnh

Cách này đơn giản và phù hợp với formatter chạy trong CI hoặc format document khi mã đã hoàn chỉnh. Nếu parser thất bại, formatter có thể trả diagnostic và không tạo edit.

### 18.2. Formatter dùng syntax tree chịu lỗi

Parser có thể tạo error node và giữ token chưa phân tích. Formatter định dạng các vùng đã hiểu và bảo toàn vùng lỗi.

### 18.3. Giới hạn vùng format

Nếu lỗi nằm trong một block, formatter có thể chỉ format các block khác. Đây là lựa chọn tốt cho trải nghiệm editor nếu có thể xác định ranh giới an toàn.

### 18.4. Không tự sửa lỗi cú pháp

Formatter không nên tự thêm toán tử, đổi tên biến hoặc đoán dấu đóng để làm parser thành công, trừ khi đó là hành vi riêng được người dùng yêu cầu như auto-completion hoặc code action.

### 18.5. Diagnostic rõ ràng

Nếu formatter không thể chạy, editor nên cho biết lý do và vị trí lỗi. Tránh thông báo chung chung nếu parser có thể cung cấp nguyên nhân cụ thể.

## 19. Tích hợp với editor

Formatter là một phần của trải nghiệm chỉnh sửa, vì vậy cần xem xét cursor, selection, undo, save và hiệu năng.

### 19.1. Lệnh Format Document

Editor có thể cung cấp menu hoặc phím tắt để format toàn tệp. Lệnh nên dễ tìm và có phản hồi khi formatter không thể xử lý.

### 19.2. Lệnh Format Selection

Khi có vùng chọn, editor gửi range. Sau khi format, selection nên vẫn bao phủ vùng logic tương ứng.

### 19.3. Format on save

Người dùng có thể bật hoặc tắt format on save. Nếu dự án bắt buộc style, CI có thể chạy formatter check để phát hiện file chưa được format.

### 19.4. Undo/redo

Một lần format document thường nên được xem như một thao tác undo có ý nghĩa. Người dùng có thể hoàn tác toàn bộ kết quả format, thay vì phải undo từng ký tự.

### 19.5. Cursor preservation

Formatter cần trả về edits hoặc mapping để editor giữ cursor gần vị trí ban đầu. Nếu cursor đang ở trong biểu thức, nó không nên nhảy về đầu tệp sau khi format.

### 19.6. Không giành quyền điều khiển khi người dùng đang gõ

Format on type cần nhanh và cục bộ. Nếu formatter toàn tệp mất nhiều thời gian, nên chạy bất đồng bộ hoặc chỉ kích hoạt theo lệnh rõ ràng.

### 19.7. Preview hoặc diff

Với một lần format lớn, editor có thể cho xem diff trước khi áp dụng. Điều này hữu ích khi thay đổi formatter version hoặc style config làm nhiều dòng thay đổi.

## 20. Hiệu năng và xử lý tài liệu lớn

Một formatter có thể chạy trên file lớn hoặc được gọi nhiều lần trong quá trình gõ.

### 20.1. Parse một lần, dùng lại syntax tree

Nếu editor đã có syntax tree cập nhật tăng dần, formatter có thể dùng lại thay vì parse toàn bộ tệp mỗi lần. Cần đảm bảo tree tương ứng đúng document version.

### 20.2. Incremental formatting

Khi chỉ một vùng thay đổi, formatter có thể format vùng đó hoặc các node phụ thuộc. Tuy nhiên, thay đổi một dấu ngoặc có thể ảnh hưởng indent của cả block lớn.

### 20.3. Giới hạn thời gian

Formatter trong editor cần có timeout hoặc cancellation để không làm giao diện bị treo. Với file lớn, có thể ưu tiên format document theo lệnh rõ ràng.

### 20.4. Tránh tạo diff quá lớn

Một thay đổi nhỏ không nên khiến formatter viết lại toàn bộ tệp nếu không cần. Stable formatting và text edits tối thiểu giúp review dễ hơn.

### 20.5. Cache

Formatter có thể cache kết quả phân tích hoặc document model theo document version và config hash. Khi nguồn hoặc cấu hình thay đổi, cache cần được invalidated.

## 21. Cấu hình dự án và công cụ dòng lệnh

Một formatter nên có thể chạy ngoài editor để bảo đảm kết quả thống nhất trong CI và quy trình review.

### 21.1. Format command

Ví dụ lệnh minh họa:

~~~text
dsl format src/rules.dsl
~~~

Có thể hỗ trợ format một file, nhiều file, toàn thư mục, chỉ các file thay đổi và check mode không ghi file.

### 21.2. Check mode

Check mode kiểm tra file đã theo style chưa. Nó có thể trả mã thoát khác 0 nếu formatter sẽ tạo thay đổi, nhưng không tự ghi file.

~~~text
dsl format --check src/rules.dsl
~~~

### 21.3. CI

CI có thể chạy check mode để ngăn mã chưa được format đi vào nhánh chính. Nên pin phiên bản formatter và cấu hình dự án để kết quả ổn định.

### 21.4. EditorConfig hoặc cấu hình tương đương

Các thuộc tính chung như indent, line ending và final newline có thể lấy từ cấu hình repository. Quy tắc riêng của DSL như brace style, trailing comma hoặc cách xuống dòng biểu thức cần cấu hình formatter riêng.

### 21.5. Formatter version

Khi nâng cấp formatter, kết quả có thể thay đổi. Dự án nên ghi rõ phiên bản hoặc chấp nhận một lần format toàn bộ có review để tránh diff rải rác trong các PR sau.

## 22. Thiết kế formatter cho DSL có nhiều ngôn ngữ nhúng

Một DSL có thể chứa nhiều vùng cú pháp khác nhau: DSL chủ, SQL, JSON, regex, template text hoặc script language.

### 22.1. Nhận diện vùng nhúng

Parser hoặc lexer cần đánh dấu ranh giới và loại ngôn ngữ của vùng nhúng. Formatter dùng metadata đó để chọn quy tắc phù hợp.

### 22.2. Gọi formatter chuyên dụng

Nếu vùng nhúng là SQL và có formatter SQL, DSL formatter có thể gửi nội dung vùng đó cho formatter chuyên dụng rồi ghép kết quả trở lại.

### 22.3. Giữ nguyên vùng không hỗ trợ

Nếu không có formatter phù hợp, giữ nguyên vùng nhúng an toàn hơn việc áp dụng style của DSL chủ.

### 22.4. Indent ở ranh giới

Có thể cần điều chỉnh indent bên ngoài vùng nhúng mà không thay đổi nội dung bên trong. Ví dụ, một SQL block được lùi vào theo block DSL nhưng các dòng SQL giữ tương quan indent nội bộ.

### 22.5. Lỗi từ formatter con

Nếu formatter SQL thất bại, formatter DSL có thể giữ nguyên vùng SQL và vẫn format phần DSL còn lại. Cần thông báo rõ vùng nào không được format.

## 23. Những lỗi triển khai thường gặp

### 23.1. Format bằng thay thế chuỗi đơn giản

Dùng regex hoặc thay thế whitespace toàn cục có thể làm hỏng string literal, comment, regex và nội dung nhúng. Formatter nên hiểu token hoặc cấu trúc cú pháp.

### 23.2. Không phân biệt khoảng trắng cú pháp và khoảng trắng dữ liệu

Khoảng trắng trong code có thể thay đổi mà không ảnh hưởng semantics; khoảng trắng trong chuỗi có thể là dữ liệu. Cần biết lexer mode và loại node trước khi sửa.

### 23.3. Thay đổi thứ tự khai báo

Sắp xếp rule theo tên có thể thay đổi thứ tự thực thi nếu DSL có semantics tuần tự. Formatter thông thường nên giữ thứ tự nguồn.

### 23.4. Làm mất comment

AST có thể bỏ comment. Nếu formatter chỉ in AST, comment có thể biến mất. Cần giữ trivia hoặc CST.

### 23.5. Không giữ newline và encoding

Đổi CRLF sang LF hoặc làm mất BOM có thể tạo diff lớn và ảnh hưởng công cụ khác. Cần có chính sách rõ.

### 23.6. Không idempotent

Nếu format lần thứ hai lại tạo thay đổi, formatter hoặc quy tắc của nó chưa ổn định.

### 23.7. Format mã chưa hoàn chỉnh quá mạnh

Tự thêm dấu đóng hoặc di chuyển nhiều dòng trong khi người dùng đang gõ có thể làm editor khó sử dụng. Nên giới hạn phạm vi và bảo toàn vùng lỗi.

### 23.8. Làm cursor nhảy

Thay toàn bộ document mà không map vị trí khiến cursor hoặc selection bị mất. Dùng text edits hoặc position mapping.

### 23.9. Cấu hình khác nhau giữa máy

Nếu editor và CI dùng formatter version hoặc config khác nhau, file có thể liên tục bị đổi format. Pin phiên bản và dùng cấu hình repository.

### 23.10. Trả văn bản rỗng khi formatter lỗi

Nếu editor hiểu kết quả rỗng là nội dung mới, toàn bộ file có thể bị xóa. Khi lỗi, formatter phải trả lỗi hoặc không có edit, không được giả vờ format thành công.

## 24. Kiểm thử formatter

Formatter cần được kiểm thử về cấu trúc, nội dung và tích hợp editor.

### 24.1. Golden tests

Mỗi test có input và output mong đợi:

~~~text
Input:
rule "r"{when x>10 then approve()}

Expected:
rule "r" {
    when x > 10
    then approve()
}
~~~

Golden test giúp phát hiện thay đổi đầu ra khi quy tắc formatter được sửa.

### 24.2. Idempotence tests

~~~text
once = format(source)
twice = format(once)
assert once == twice
~~~

Đây là kiểm thử quan trọng cho formatter.

### 24.3. Parse-format-parse

Một phép kiểm tra hữu ích:
1. Parse nguồn ban đầu.
2. Format.
3. Parse kết quả.
4. So sánh cấu trúc hoặc semantics.

Nếu formatter tạo văn bản không parse được, đó là lỗi.

### 24.4. Semantic preservation

Chạy chương trình trước và sau format trong interpreter tham chiếu, rồi so sánh kết quả và tác dụng phụ quan sát được. Formatter không nên làm thay đổi hành vi.

### 24.5. Comment và literal tests

Kiểm tra comment đầu file, cuối dòng và trong block; documentation comment; directive format off/on; string có khoảng trắng đầu/cuối; escape sequence; raw string; multiline string và heredoc; SQL hoặc JSON nhúng.

### 24.6. Range formatting tests

Kiểm tra selection ở đầu file, cuối file, giữa block, một phần biểu thức và vùng lỗi cú pháp. Xác nhận edit không vượt phạm vi cho phép.

### 24.7. Error-tolerant tests

Cung cấp mã thiếu dấu ngoặc, thiếu toán hạng hoặc đang gõ dở. Xác nhận formatter giữ vùng chưa hoàn chỉnh và không xóa nội dung.

### 24.8. Cross-platform tests

Chạy formatter với LF và CRLF, nhiều encoding được hỗ trợ, tab, Unicode và đường dẫn khác nhau. Đảm bảo kết quả tuân thủ config.

### 24.9. Performance tests

Đo thời gian format với file nhỏ, file lớn, block lồng sâu và nhiều comment. Theo dõi bộ nhớ và khả năng hủy tác vụ.

### 24.10. Fuzz testing

Sinh nguồn ngẫu nhiên hoặc gần hợp lệ với dấu ngoặc, comment, string và delimiter lồng nhau. Formatter không được crash, treo hoặc làm mất dữ liệu tùy tiện. Khi parse thất bại, hành vi fallback phải có giới hạn và xác định.

## 25. Quy trình thiết kế và triển khai formatter

Một quy trình có thể gồm:

1. Đọc grammar và xác định các node cú pháp cần trình bày.
2. Quy định style: indent, whitespace, brace, line width, comma, blank line và final newline.
3. Xác định comment, trivia, literal và vùng nhúng cần bảo toàn.
4. Chọn representation: token stream, AST, CST hoặc document model.
5. Xây quy tắc pretty-print cho từng node.
6. Thiết kế chiến lược cho mã chưa hoàn chỉnh và lỗi cú pháp.
7. Triển khai format document, range và on-type theo nhu cầu editor.
8. Tích hợp text edits, document version, cancellation và cursor mapping.
9. Đọc cấu hình dự án và pin formatter version.
10. Viết golden, idempotence, parse-format-parse và semantic tests.
11. Đo hiệu năng trên tài liệu đại diện.
12. Cung cấp CLI/check mode để editor và CI dùng cùng formatter.

## 26. Ví dụ tổng hợp: format một rule DSL

Nguồn ban đầu:

~~~text
rule "free_shipping"{when order.status=="PAID" and order.total>=500000 then:set order.shippingFee=0;notify(order.owner,"Free shipping")}
~~~

Sau khi parse, formatter nhận biết:
- Rule tên free_shipping.
- Một biểu thức điều kiện gồm hai phép so sánh kết hợp bằng and.
- Một block action có phép gán và lời gọi notify.
- Các literal chuỗi và số.

Đầu ra có thể là:

~~~text
rule "free_shipping" {
    when order.status == "PAID"
        and order.total >= 500000

    then:
        set order.shippingFee = 0
        notify(
            order.owner,
            "Free shipping",
        )
}
~~~

### 26.1. Vì sao formatter chọn cách trình bày này?

- Dấu ngoặc mở và đóng block nằm ở vị trí nhất quán.
- Nội dung bên trong block được thụt lề.
- Toán tử có khoảng trắng hai bên.
- Điều kiện dài được tách dòng tại toán tử logic.
- Các action nằm trên dòng riêng.
- Lời gọi dài được trình bày theo từng đối số.
- String literal được giữ nguyên giá trị.

### 26.2. Điều cần giữ

Formatter phải giữ tên rule, thứ tự điều kiện, thứ tự action, giá trị literal, cấu trúc kết hợp điều kiện, comment và source mapping nếu có.

### 26.3. Kết quả ổn định

Khi chạy formatter lần thứ hai trên đầu ra, văn bản không thay đổi. Đây là một đặc tính quan trọng để format on save và CI hoạt động ổn định.

## 27. Bài tập tự kiểm tra

### Bài 1: Xác định trách nhiệm

Hãy giải thích sự khác nhau giữa lexer, parser, formatter, validator và linter trong một DSL editor. Cho ví dụ một thao tác mà formatter không nên tự thực hiện.

### Bài 2: Quy tắc khoảng trắng

Thiết kế quy tắc khoảng trắng cho phép gán, toán tử so sánh, lời gọi hàm, danh sách và truy cập thuộc tính. Viết một ví dụ trước và sau khi format.

### Bài 3: Thụt lề block

Cho một rule có hai block lồng nhau và một danh sách action. Hãy viết kết quả format theo indent 4 spaces và giải thích cách xử lý dấu mở/đóng.

### Bài 4: Độ rộng dòng

Một lời gọi hàm có sáu đối số và vượt line width 100. Hãy đề xuất cách xuống dòng, indent và trailing comma.

### Bài 5: Bảo toàn literal

Một string có hai khoảng trắng đầu, một tab và một escape newline. Hãy giải thích vì sao formatter không được thay đổi nội dung đó chỉ để đạt line width.

### Bài 6: Comment và directive

Một tệp có comment đầu block, comment cuối dòng và vùng format off. Hãy mô tả cách formatter giữ vị trí và phạm vi của từng loại.

### Bài 7: Mã chưa hoàn chỉnh

Người dùng đang gõ một biểu thức còn thiếu toán hạng. Hãy so sánh cách xử lý của formatter yêu cầu AST hoàn chỉnh và formatter dùng tolerant parser.

### Bài 8: Range formatting

Selection bắt đầu giữa một block và kết thúc giữa biểu thức. Hãy đề xuất cách xác định node phù hợp để format mà không sửa ngoài phạm vi người dùng yêu cầu.

### Bài 9: Idempotence

Một formatter đổi một lời gọi ngắn thành nhiều dòng ở lần đầu, rồi gộp lại thành một dòng ở lần hai. Hãy nêu nguyên nhân có thể có và cách thiết kế quy tắc ưu tiên để kết quả ổn định.

### Bài 10: Kiểm thử

Hãy lập bộ test cho formatter gồm golden tests, parse-format-parse, comment, string, range formatting, mã lỗi cú pháp, LF/CRLF và performance. Nêu kết quả mong đợi của từng nhóm.

## Kết luận

Định dạng tự động giúp trình soạn thảo DSL trình bày mã nguồn nhất quán, dễ đọc và dễ review. Formatter có thể dựa trên token, AST, CST hoặc document model để quyết định khoảng trắng, thụt lề, xuống dòng và cách trình bày từng cấu trúc. Một formatter đáng tin cậy phải bảo toàn ngữ nghĩa, comment, literal và thứ tự nguồn; hỗ trợ format toàn tệp, vùng chọn và mã chưa hoàn chỉnh theo phạm vi đã xác định; đồng thời tích hợp đúng với editor, LSP, cấu hình dự án và quy trình CI. Tính idempotent, đầu ra xác định và kiểm thử parse-format-parse là những nền tảng để formatter hoạt động ổn định trên nhiều máy và trong suốt vòng đời phát triển DSL.

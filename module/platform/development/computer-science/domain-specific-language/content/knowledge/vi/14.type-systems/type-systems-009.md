# Kiểm tra kiểu tĩnh trong DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích kiểm tra kiểu tĩnh (static type checking) và vai trò của nó trong hệ kiểu của một DSL.
- Phân biệt kiểm tra cú pháp, phân giải tên, kiểm tra kiểu tĩnh và xác thực dữ liệu khi chạy.
- Mô tả môi trường kiểu, phán đoán kiểu và cách kiểm tra kiểu của biểu thức, câu lệnh, hàm và thuộc tính.
- Đọc các quy tắc kiểu cơ bản và hiểu cách bộ kiểm tra suy luận kiểu của một biểu thức.
- Phân biệt kiểm tra kiểu tĩnh tường minh với suy luận kiểu.
- Thiết kế quy tắc cho kiểu miền, collection, hàm, giá trị tùy chọn và chuyển kiểu.
- Xây dựng thông báo lỗi có vị trí và ngữ cảnh rõ ràng.
- Nhận diện giới hạn của kiểm tra kiểu tĩnh và xác định phần nào vẫn cần xác thực khi chạy.

## 1. Kiểm tra kiểu tĩnh là gì?

Kiểm tra kiểu tĩnh (static type checking) là quá trình phân tích chương trình trước khi thực thi để xác định các biểu thức và thao tác có tuân theo quy tắc kiểu của ngôn ngữ hay không. Một biểu thức sai kiểu sẽ bị từ chối trước khi chương trình được chạy hoặc trước khi cấu hình DSL được chấp nhận.

Trong một DSL, kiểu mô tả loại giá trị mà một thành phần biểu diễn. Ví dụ:

- Integer biểu diễn số nguyên.
- Decimal biểu diễn số thập phân.
- String biểu diễn văn bản.
- Boolean biểu diễn giá trị đúng hoặc sai.
- Date biểu diễn ngày.
- Money biểu diễn số tiền cùng quy tắc về đơn vị tiền tệ.
- Order biểu diễn một đơn hàng trong miền bán hàng.

Một phép toán chỉ hợp lệ với những kiểu mà DSL quy định. Phép cộng hai số có thể hợp lệ; phép cộng một khách hàng với một ngày thường không có ý nghĩa. Bộ kiểm tra kiểu tĩnh phát hiện những trường hợp như vậy trước khi biểu thức được thực thi.

Ví dụ DSL:

~~~text
let quantity: Integer = 3
let unitPrice: Money = 120000 VND
let total: Money = unitPrice * quantity
~~~

Nếu DSL định nghĩa phép nhân Money với Integer cho kết quả Money, khai báo total hợp lệ. Nhưng nếu viết:

~~~text
let total: Money = unitPrice + "free"
~~~

bộ kiểm tra kiểu có thể từ chối vì phép cộng giữa Money và String không được định nghĩa.

Kiểm tra kiểu tĩnh không có nghĩa là chương trình chắc chắn đúng về mọi mặt. Nó chỉ kiểm tra những thuộc tính mà hệ kiểu và thông tin có sẵn cho phép chứng minh trước khi chạy. Các điều kiện phụ thuộc dữ liệu thực tế, trạng thái hệ thống, quyền truy cập hoặc dịch vụ bên ngoài vẫn có thể cần được kiểm tra lúc chạy.

## 2. Phân biệt các giai đoạn kiểm tra

Một công cụ DSL thường thực hiện nhiều giai đoạn phân tích. Mỗi giai đoạn trả lời một câu hỏi khác nhau.

~~~text
Văn bản DSL
    |
    v
Lexer: nhận diện token
    |
    v
Parser: kiểm tra cấu trúc cú pháp
    |
    v
AST: cây cú pháp trừu tượng
    |
    v
Phân giải tên và phạm vi
    |
    v
Kiểm tra kiểu tĩnh
    |
    v
Kiểm tra ràng buộc miền tĩnh
    |
    v
Sinh mã / tạo kế hoạch / diễn giải
    |
    v
Xác thực dữ liệu và thực thi khi chạy
~~~

### 2.1. Kiểm tra từ vựng

Lexer nhận diện các chuỗi ký tự thành token như IDENTIFIER, INTEGER, STRING, PLUS hoặc WHEN. Ví dụ, nó có thể nhận diện chuỗi total là một định danh. Lexer chưa biết định danh đó có được khai báo hay không hoặc có kiểu gì.

### 2.2. Kiểm tra cú pháp

Parser xác định token có kết hợp theo grammar hay không. Ví dụ, câu lệnh gán có thể yêu cầu tên biến, dấu bằng và biểu thức:

~~~text
assignment ::= IDENTIFIER "=" expression
~~~

Chuỗi total = 10 có thể đúng cú pháp. Chuỗi total = có thể sai cú pháp vì thiếu biểu thức ở vế phải.

### 2.3. Phân giải tên

Phân giải tên (name resolution) xác định tên được nhắc đến đại diện cho khai báo nào trong phạm vi hiện tại.

Ví dụ, nếu biểu thức tham chiếu order.total, công cụ cần xác định order có tồn tại trong môi trường hiện tại không và total có phải thuộc tính được khai báo của kiểu Order không. Nếu tên không tồn tại, đây là lỗi phân giải tên; nó có thể xuất hiện trước hoặc được báo cùng quá trình kiểm tra kiểu.

### 2.4. Kiểm tra kiểu tĩnh

Sau khi biết các tên tham chiếu đến đâu, bộ kiểm tra xác định kiểu của từng biểu thức và kiểm tra các phép toán, gán, lời gọi hàm, truy cập thuộc tính và điều kiện.

Ví dụ, order.total có thể có kiểu Money. Nếu DSL yêu cầu điều kiện của when phải là Boolean, biểu thức when order.total sẽ bị từ chối vì Money không phải Boolean.

### 2.5. Xác thực ngữ nghĩa và runtime

Một biểu thức có thể đúng kiểu nhưng vi phạm quy tắc nghiệp vụ. Ví dụ, Money trừ Money là phép toán hợp lệ, nhưng hoàn tiền nhiều hơn số tiền đã thu có thể bị cấm. Tương tự, một Order có kiểu đúng nhưng đã chuyển sang trạng thái SHIPPED thì không thể hủy.

Những quy tắc này có thể được kiểm tra tĩnh nếu dữ liệu và điều kiện đã biết, nhưng thường cần xác thực khi chạy vì chúng phụ thuộc vào trạng thái thực tế.

## 3. Môi trường kiểu và phán đoán kiểu

Để kiểm tra một biểu thức, công cụ cần biết các tên hiện có và kiểu của chúng. Thông tin này thường được lưu trong **môi trường kiểu** (type environment), ký hiệu phổ biến là Γ (Gamma).

Ví dụ:

~~~text
Γ = {
  quantity: Integer,
  unitPrice: Money,
  customer: Customer,
  isActive: Boolean
}
~~~

Môi trường kiểu cho biết quantity có kiểu Integer, unitPrice có kiểu Money, customer có kiểu Customer và isActive có kiểu Boolean.

Một cách diễn đạt hình thức cho kết quả kiểm tra kiểu là **phán đoán kiểu** (typing judgment):

~~~text
Γ ⊢ expression : Type
~~~

Ký hiệu này đọc là: trong môi trường kiểu Γ, biểu thức expression có kiểu Type.

Ví dụ:

~~~text
Γ ⊢ quantity : Integer
Γ ⊢ unitPrice : Money
Γ ⊢ isActive : Boolean
~~~

Phán đoán kiểu giúp đặc tả quy tắc của ngôn ngữ một cách chính xác. Nó cũng là cơ sở để triển khai type checker đệ quy trên AST.

### 3.1. Môi trường kiểu được tạo như thế nào?

Môi trường kiểu có thể được xây dựng từ:

- Khai báo biến và tham số trong chương trình DSL.
- Mô hình miền hoặc metamodel.
- Schema của dữ liệu mà DSL truy cập.
- Các hàm và toán tử dựng sẵn.
- Thư viện kiểu và hàm được công cụ cung cấp.
- Ngữ cảnh thực thi, chẳng hạn đối tượng hiện tại hoặc biến môi trường.

Ví dụ, một DSL quy tắc có thể cung cấp sẵn biến order với kiểu Order. Bộ kiểm tra biết các thuộc tính của Order như id, total, status và customer thông qua schema hoặc mô hình kiểu.

### 3.2. Phạm vi (scope)

Tên có thể được khai báo trong các phạm vi khác nhau: toàn cục, module, hàm, khối lệnh hoặc biểu thức lambda. Khi đi vào một phạm vi mới, môi trường kiểu có thể được mở rộng bằng các khai báo mới.

Ví dụ:

~~~text
let total: Money = 100000 VND

rule "discount" {
    let rate: Percentage = 10%
    when order.total > total
    then order.discount = order.total * rate
}
~~~

Trong khối rule, rate là tên cục bộ. Công cụ cần xác định total ở biểu thức điều kiện tham chiếu đến biến nào nếu có nhiều khai báo cùng tên ở các phạm vi khác nhau.

### 3.3. Che khuất tên (shadowing)

Một DSL có thể cho phép khai báo tên cục bộ trùng tên với tên ở phạm vi bên ngoài. Nếu cho phép, quy tắc shadowing cần rõ ràng: khai báo gần nhất có thể che khuất khai báo bên ngoài.

Một số DSL chọn cấm trùng tên để giảm nhầm lẫn. Dù chọn cách nào, bộ phân giải tên phải quyết định chính xác khai báo nào được sử dụng trước khi kiểm tra kiểu biểu thức.

## 4. Quy tắc kiểu cho các biểu thức cơ bản

Type checker thường được triển khai bằng cách duyệt AST từ dưới lên: kiểm tra các nút con, lấy kiểu kết quả của chúng, sau đó xác định kiểu của nút cha.

### 4.1. Literal

Literal là giá trị được viết trực tiếp trong nguồn. Mỗi loại literal có một kiểu mặc định hoặc kiểu được suy ra từ cú pháp.

| Literal | Kiểu thường gặp |
|---|---|
| 42 | Integer |
| 3.14 | Decimal |
| "hello" | String |
| true | Boolean |
| 2026-11-15 | Date, nếu cú pháp ngày được hỗ trợ |
| 10ms | Duration, nếu DSL định nghĩa hậu tố thời lượng |

Kiểu literal cần được quy định nhất quán. Ví dụ, một số nguyên lớn hơn phạm vi của Integer có thể cần kiểu BigInteger hoặc bị từ chối.

### 4.2. Định danh

Với một định danh x, bộ kiểm tra tra môi trường kiểu:

~~~text
Γ(x) = T
----------------
Γ ⊢ x : T
~~~

Nếu x không có trong môi trường, công cụ báo lỗi tên chưa được khai báo hoặc không thể phân giải. Nếu tên tồn tại, kiểu của nó được dùng để kiểm tra biểu thức bao quanh.

### 4.3. Phép cộng số

Một quy tắc đơn giản cho phép cộng số nguyên:

~~~text
Γ ⊢ left : Integer
Γ ⊢ right : Integer
-------------------------------
Γ ⊢ left + right : Integer
~~~

Quy tắc này nói rằng nếu cả hai toán hạng có kiểu Integer, biểu thức cộng có kiểu Integer.

DSL có thể định nghĩa thêm:

~~~text
Integer + Decimal -> Decimal
Money + Money -> Money
String + String -> String
~~~

Mỗi phép toán phải có quy tắc rõ. Không nên giả định mọi kiểu đều có thể cộng với nhau chỉ vì ngôn ngữ chủ có toán tử tương ứng.

### 4.4. So sánh

Phép so sánh có thể nhận hai giá trị tương thích và trả về Boolean:

~~~text
Γ ⊢ left : T
Γ ⊢ right : T
T supports comparison
--------------------------------
Γ ⊢ left > right : Boolean
~~~

Điều kiện T supports comparison thể hiện rằng không phải mọi kiểu đều có quan hệ lớn hơn hoặc nhỏ hơn. Ví dụ, so sánh hai ngày có thể hợp lệ; so sánh một khách hàng với một khoản tiền thường không có nghĩa.

Một DSL có thể cho phép so sánh giữa các kiểu khác nhau khi có quy tắc rõ ràng, chẳng hạn DateTime với DateTimeOffset sau khi chuẩn hóa múi giờ. Quy tắc đó cần được định nghĩa thay vì dựa vào chuyển đổi ngầm không rõ ràng.

### 4.5. Toán tử logic

Nếu and và or yêu cầu hai toán hạng Boolean:

~~~text
Γ ⊢ left : Boolean
Γ ⊢ right : Boolean
--------------------------------
Γ ⊢ left and right : Boolean
~~~

Toán tử not nhận một Boolean và trả về Boolean:

~~~text
Γ ⊢ value : Boolean
-------------------------------
Γ ⊢ not value : Boolean
~~~

Nếu DSL cho phép truthiness, ví dụ số 0 được xem như false, đó là một quy tắc chuyển đổi riêng. Với DSL nghiệp vụ, yêu cầu Boolean tường minh thường giúp biểu thức dễ hiểu và giảm nhầm lẫn.

### 4.6. Truy cập thuộc tính

Giả sử Order có thuộc tính total kiểu Money:

~~~text
Γ ⊢ order : Order
Order có thuộc tính total : Money
---------------------------------
Γ ⊢ order.total : Money
~~~

Nếu Order không có thuộc tính price, biểu thức order.price bị từ chối. Nếu thuộc tính có thể vắng mặt, kiểu kết quả có thể là Optional<T> hoặc một kiểu nullable tùy hệ kiểu của DSL.

### 4.7. Gán giá trị

Với phép gán:

~~~text
Γ ⊢ target : T
Γ ⊢ value : S
S assignable to T
-------------------------------
Γ ⊢ target = value : Unit
~~~

Điều kiện assignable to xác định kiểu S có thể được gán vào vị trí kiểu T hay không. Nếu DSL không có kiểu Unit, câu lệnh gán có thể không tạo giá trị hoặc có một kiểu kết quả khác được quy định.

Ví dụ, gán Integer vào biến Decimal có thể được cho phép nếu có chuyển đổi mở rộng an toàn. Gán String vào Money thường phải bị từ chối trừ khi có thao tác parse hoặc chuyển đổi được chỉ định rõ.

## 5. Kiểm tra kiểu cho câu lệnh và cấu trúc điều khiển

Không chỉ biểu thức riêng lẻ mới cần kiểm tra kiểu. Các cấu trúc điều khiển cũng đặt ra yêu cầu về kiểu.

### 5.1. Điều kiện

Một câu lệnh if có thể yêu cầu điều kiện Boolean:

~~~text
if order.total > 1000000 {
    applyDiscount(order)
}
~~~

Biểu thức order.total > 1000000 cần có kiểu Boolean. Nếu người viết viết:

~~~text
if order.total {
    applyDiscount(order)
}
~~~

thì công cụ từ chối nếu Money không được phép dùng như điều kiện.

### 5.2. Vòng lặp

Một vòng lặp for có thể yêu cầu giá trị có thể duyệt:

~~~text
for line in order.lines {
    print(line.product.name)
}
~~~

Nếu order.lines có kiểu List<OrderLine>, biến line trong thân vòng lặp có kiểu OrderLine. Bộ kiểm tra dùng kiểu phần tử này để kiểm tra line.product.name.

Nếu order.lines có kiểu không thể duyệt, vòng lặp bị từ chối.

### 5.3. Nhánh điều kiện

Với biểu thức điều kiện nhiều nhánh:

~~~text
if order.status == "NEW" {
    processNew(order)
} else {
    processExisting(order)
}
~~~

Điều kiện phải là Boolean. Nếu DSL cho phép biểu thức if tạo ra giá trị, hai nhánh có thể cần trả về kiểu tương thích. Ví dụ, if dùng để tạo giá trị Discount thì cả nhánh then và else phải trả về Discount hoặc một kiểu chung được xác định.

### 5.4. Khối lệnh

Một khối có thể chứa nhiều câu lệnh. Nếu DSL phân biệt statement với expression, khối lệnh có thể không có kiểu giá trị. Nếu khối trả về giá trị của biểu thức cuối, type checker cần xác định quy tắc đó rõ ràng.

## 6. Kiểm tra lời gọi hàm và chữ ký kiểu

Một hàm có chữ ký (function signature) mô tả tên, kiểu tham số và kiểu kết quả. Ví dụ:

~~~text
calculateTax(amount: Money, rate: Percentage) -> Money
~~~

Khi gặp lời gọi:

~~~text
calculateTax(order.total, 8%)
~~~

bộ kiểm tra cần xác minh:

- Tên hàm có tồn tại trong môi trường hiện tại không.
- Số lượng đối số có đúng không.
- Mỗi đối số có kiểu tương thích với tham số tương ứng không.
- Kiểu kết quả của lời gọi là gì.

### 6.1. Quy tắc kiểu cho lời gọi hàm

Nếu hàm f có chữ ký:

~~~text
f: (T1, T2, ..., Tn) -> R
~~~

thì lời gọi f(e1, e2, ..., en) hợp lệ khi:

~~~text
Γ ⊢ e1 : T1
Γ ⊢ e2 : T2
...
Γ ⊢ en : Tn
~~~

Kết quả của lời gọi có kiểu R.

### 6.2. Số lượng đối số

Nếu hàm yêu cầu hai tham số nhưng người viết chỉ truyền một đối số, đó là lỗi lời gọi hàm. Nếu có tham số tùy chọn hoặc tham số có giá trị mặc định, chữ ký cần mô tả chính xác số lượng hợp lệ.

### 6.3. Hàm quá tải (overloading)

Một DSL có thể cho phép nhiều hàm cùng tên với chữ ký khác nhau:

~~~text
format(value: Date) -> String
format(value: Money) -> String
format(value: Integer) -> String
~~~

Khi kiểm tra format(order.createdAt), công cụ chọn phiên bản nhận Date. Nếu nhiều overload đều phù hợp, DSL cần quy tắc chọn rõ ràng hoặc báo lỗi mơ hồ.

Không nên chọn overload dựa trên thứ tự khai báo một cách tùy tiện, vì kết quả có thể thay đổi khi thư viện được mở rộng.

## 7. Kiểm tra kiểu tĩnh và suy luận kiểu

Kiểm tra kiểu tĩnh không bắt buộc người viết phải khai báo kiểu cho mọi biến. Công cụ có thể suy luận kiểu từ literal, biểu thức và chữ ký hàm.

### 7.1. Khai báo kiểu tường minh

~~~text
let quantity: Integer = 3
let customerName: String = "An"
~~~

Người viết nêu kiểu mong muốn. Type checker kiểm tra giá trị khởi tạo có tương thích hay không.

### 7.2. Suy luận kiểu

~~~text
let quantity = 3
let customerName = "An"
~~~

Công cụ suy luận quantity có kiểu Integer và customerName có kiểu String dựa trên literal.

### 7.3. Suy luận từ biểu thức

~~~text
let subtotal = unitPrice * quantity
~~~

Nếu unitPrice có kiểu Money, quantity có kiểu Integer và phép nhân Money × Integer được định nghĩa trả về Money, subtotal có kiểu Money.

### 7.4. Suy luận cần có giới hạn rõ

Một biểu thức có thể không đủ thông tin để suy ra một kiểu duy nhất. Ví dụ:

~~~text
let empty = []
~~~

Danh sách rỗng không cho biết kiểu phần tử. DSL có thể yêu cầu chú thích:

~~~text
let empty: List<Order> = []
~~~

Hoặc cho phép suy luận khi kiểu được xác định từ ngữ cảnh sử dụng. Cả hai cách đều cần được đặc tả.

### 7.5. Kiểm tra tính nhất quán của kiểu suy luận

Nếu biến được suy luận là Integer, việc gán sau đó một String có thể bị từ chối:

~~~text
let count = 3
count = "three"
~~~

Một DSL có thể cho phép biến thay đổi kiểu động, nhưng khi đó nó không còn duy trì cùng bảo đảm kiểu tĩnh cho biến đó. Nếu muốn kiểu tĩnh, cần xác định kiểu của biến và kiểm tra mọi phép gán sau này.

## 8. Kiểu con, tương thích và chuyển kiểu

Hai kiểu không nhất thiết phải giống hệt nhau mới có thể sử dụng thay thế. Hệ kiểu có thể định nghĩa quan hệ kiểu con (subtyping) hoặc chuyển kiểu (conversion).

### 8.1. Kiểu con

Giả sử Manager là kiểu con của Employee:

~~~text
Manager <: Employee
~~~

Điều này có nghĩa một giá trị Manager có thể được dùng ở vị trí yêu cầu Employee nếu DSL áp dụng quy tắc thay thế kiểu con.

Ví dụ:

~~~text
approve(request, manager)
~~~

Nếu hàm approve yêu cầu một Employee và manager có kiểu Manager, lời gọi có thể hợp lệ.

### 8.2. Chuyển kiểu mở rộng và thu hẹp

Một số chuyển đổi có thể an toàn trong mọi trường hợp của kiểu nguồn:

- Integer sang Decimal có thể là chuyển đổi mở rộng nếu Decimal biểu diễn được toàn bộ giá trị Integer.
- Decimal sang Integer thường là chuyển đổi thu hẹp vì có thể mất phần thập phân.

DSL cần quy định chuyển đổi nào tự động, chuyển đổi nào yêu cầu cú pháp tường minh và chuyển đổi nào không được phép.

### 8.3. Chuyển kiểu ngầm

Chuyển kiểu ngầm (implicit conversion) có thể giúp biểu thức ngắn gọn, nhưng quá nhiều chuyển đổi ngầm làm cho ý nghĩa khó đoán.

Ví dụ, nếu String tự động chuyển thành Date, biểu thức:

~~~text
order.createdAt > "2026-01-01"
~~~

có thể được chấp nhận. Nhưng định dạng ngày, múi giờ và lỗi parse cần được xác định. Một DSL có thể yêu cầu literal ngày tường minh để tránh phụ thuộc locale.

### 8.4. Kiểu miền và đơn vị đo

Một số giá trị có cùng dạng vật lý nhưng khác ý nghĩa:

- Money và Decimal.
- Distance và Duration.
- CustomerId và OrderId.
- Percentage và Integer.

Nếu dùng cùng một kiểu nguyên thủy, bộ kiểm tra khó ngăn nhầm lẫn. Kiểu miền (domain-specific type) giúp biểu diễn ý nghĩa và giới hạn thao tác.

Ví dụ:

~~~text
Money + Money -> Money
Money * Integer -> Money
Distance / Duration -> Speed
CustomerId == CustomerId -> Boolean
CustomerId == OrderId -> không hợp lệ
~~~

Đây là các quy tắc minh họa. DSL cần xác định phép toán hợp lệ cho từng kiểu miền thay vì mặc định mọi kiểu số có thể thay thế nhau.

## 9. Kiểm tra kiểu với collection và kiểu tham số hóa

Collection lưu nhiều giá trị. Kiểu collection thường mang theo kiểu của phần tử:

- List<Integer>
- Set<Customer>
- Map<String, Money>

### 9.1. Kiểu phần tử

Nếu order.lines có kiểu List<OrderLine>, phần tử khi duyệt có kiểu OrderLine:

~~~text
for line in order.lines {
    print(line.quantity)
}
~~~

Nếu line.quantity có kiểu Integer, phép cộng line.quantity + 1 có thể hợp lệ.

### 9.2. Kiểm tra collection literal

~~~text
let numbers = [1, 2, 3]
~~~

Công cụ có thể suy luận kiểu List<Integer>.

Nếu các phần tử không cùng kiểu:

~~~text
let values = [1, "two", true]
~~~

DSL cần quyết định có cho phép collection chứa nhiều kiểu không. Có thể từ chối, suy ra kiểu hợp nhất như List<Any>, hoặc yêu cầu khai báo một kiểu union. Lựa chọn ảnh hưởng đến mức an toàn khi truy cập phần tử.

### 9.3. Kiểu tham số hóa

Một kiểu như List<T> có tham số kiểu T. Khi kiểm tra:

~~~text
List<Integer> + List<Integer> -> List<Integer>
~~~

quy tắc có thể yêu cầu hai collection có cùng kiểu phần tử.

### 9.4. Variance

Trong một số hệ kiểu, List<Manager> có thể được dùng ở nơi cần List<Employee> hay không phụ thuộc vào quy tắc variance của kiểu collection. Nếu collection chỉ đọc, quan hệ kiểu con có thể an toàn theo một hướng. Nếu collection cho phép thêm phần tử, cho phép thay thế có thể gây lỗi kiểu.

DSL không nhất thiết phải hỗ trợ variance phức tạp. Nhưng nếu có kiểu tham số hóa và subtyping, cần đặc tả rõ để tránh các phép gán không an toàn.

## 10. Giá trị tùy chọn, null và kiểu kết quả

Một thuộc tính có thể không có giá trị. Hệ kiểu cần biểu diễn trạng thái đó rõ ràng.

### 10.1. Kiểu Optional

Nếu customer.email có thể vắng mặt, kiểu của nó có thể là Optional<String>:

~~~text
let email: Optional<String> = customer.email
~~~

Không thể gọi thao tác chỉ dành cho String trực tiếp trên Optional<String> nếu chưa kiểm tra hoặc lấy giá trị.

### 10.2. Kiểm tra giá trị có mặt

~~~text
if customer.email is present {
    sendEmail(customer.email.value)
}
~~~

Trong nhánh điều kiện, một số hệ kiểu có thể thu hẹp kiểu (type narrowing) từ Optional<String> thành String. Cơ chế này còn được gọi là flow-sensitive typing hoặc smart cast tùy ngôn ngữ.

### 10.3. Null safety

Nếu DSL cho phép null, cần xác định:

- Kiểu nào có thể nhận null.
- Có được truy cập thuộc tính trên giá trị nullable không.
- Phép so sánh với null có kết quả kiểu gì.
- Cách xử lý giá trị vắng mặt khi gán hoặc truyền tham số.
- Có toán tử truy cập an toàn hay toán tử mặc định không.

Ví dụ:

~~~text
customer.email?.length
~~~

Toán tử ?. có thể trả về Optional<Integer> hoặc Integer nullable. Cách biểu diễn phải thống nhất trong hệ kiểu.

## 11. Suy luận kiểu theo luồng điều khiển

Một số hệ kiểu có thể sử dụng điều kiện trong chương trình để thu hẹp kiểu của biến tại từng nhánh.

Ví dụ:

~~~text
if value is String {
    print(value.length)
}
~~~

Nếu trước điều kiện value có kiểu String | Integer, trong nhánh then bộ kiểm tra có thể suy luận value chỉ còn kiểu String. Đây là type narrowing dựa trên luồng điều khiển.

Một ví dụ khác:

~~~text
if order.payment is present {
    process(order.payment)
}
~~~

Trong nhánh then, payment có thể được xem là đã có giá trị.

Flow-sensitive typing làm DSL biểu đạt mạnh hơn nhưng tăng độ phức tạp của type checker. Công cụ phải xác định thông tin kiểu thay đổi như thế nào sau mỗi nhánh, vòng lặp, phép gán và điểm hợp nhất luồng điều khiển.

## 12. Kiểm tra kiểu tĩnh dựa trên schema

Nhiều DSL truy vấn, báo cáo và quy tắc phụ thuộc vào dữ liệu có cấu trúc. Ví dụ, DSL có thể tham chiếu:

~~~text
order.customer.address.city
order.lines.quantity
order.total
~~~

Để kiểm tra các biểu thức đó, công cụ cần schema mô tả:

~~~text
Order {
    customer: Customer
    lines: List<OrderLine>
    total: Money
}

Customer {
    address: Address
}

Address {
    city: String
}

OrderLine {
    quantity: Integer
}
~~~

Từ schema, type checker có thể suy ra:

| Biểu thức | Kiểu |
|---|---|
| order.customer | Customer |
| order.customer.address | Address |
| order.customer.address.city | String |
| order.lines | List<OrderLine> |
| order.lines[0].quantity | Integer, nếu truy cập phần tử được phép |
| order.total | Money |

### 12.1. Tên trường không tồn tại

Nếu người viết nhập order.prcie, checker tra schema không thấy thuộc tính prcie và báo lỗi. Công cụ có thể đề xuất price hoặc total nếu có tên gần giống.

### 12.2. Schema có phiên bản

Nếu schema thay đổi, kết quả kiểm tra có thể thay đổi. Một DSL source hợp lệ với schema phiên bản 1 có thể không còn hợp lệ với phiên bản 2.

Do đó, công cụ cần xác định:

- DSL source sử dụng phiên bản schema nào.
- Metadata được tải từ đâu.
- Kiểm tra có dùng schema tại thời điểm lưu hay tại thời điểm chạy không.
- Điều gì xảy ra khi schema không sẵn sàng.
- Cách thông báo và di chuyển khi trường hoặc kiểu bị đổi.

### 12.3. Kiểu không xác định do schema động

Nếu schema chỉ biết khi kết nối tới nguồn dữ liệu, một phần kiểm tra có thể bị trì hoãn. Công cụ có thể hỗ trợ chế độ kiểm tra tĩnh với schema đã chọn và kiểm tra lại khi thực thi để phát hiện schema thực tế không khớp.

## 13. Các chiến lược kiểm tra kiểu tĩnh

Không phải DSL nào cũng cần cùng mức độ phức tạp. Có thể chọn chiến lược phù hợp với phạm vi ngôn ngữ.

### 13.1. Kiểu tường minh

Người viết khai báo kiểu cho biến, tham số và giá trị trả về. Cách này dễ hiểu và giúp phát hiện sai khác ngay tại khai báo, nhưng có thể làm chương trình dài hơn.

### 13.2. Suy luận cục bộ

Công cụ suy luận kiểu từ literal, toán tử và lời gọi hàm trong phạm vi biểu thức. Cách này giảm chú thích nhưng vẫn giữ kiểu tĩnh.

### 13.3. Kiểu theo schema

Kiểu của các đối tượng và trường được lấy từ schema hoặc metamodel. Phù hợp với DSL truy vấn và DSL quy tắc trên dữ liệu nghiệp vụ.

### 13.4. Kiểu theo ngữ cảnh

Kiểu mong đợi ở vị trí sử dụng có thể giúp suy luận kiểu của biểu thức. Ví dụ, nếu tham số hàm yêu cầu Date, literal ngày có thể được diễn giải theo kiểu Date.

### 13.5. Kết hợp tĩnh và động

Phần có thể biết trước được kiểm tra tĩnh; phần phụ thuộc dữ liệu hoặc môi trường được kiểm tra khi chạy. Đây là chiến lược phổ biến trong DSL có tích hợp hệ thống bên ngoài.

## 14. Kiến trúc một bộ kiểm tra kiểu

Một type checker có thể được tổ chức thành các thành phần:

~~~text
AST
 |
 v
Symbol Resolver
 |
 v
Type Environment
 |
 v
Expression Type Checker
 |
 v
Statement / Function Checker
 |
 v
Constraint Checker
 |
 v
Typed AST + Diagnostics
~~~

### 14.1. Symbol resolver

Phân giải tên, xây bảng ký hiệu và liên kết mỗi nút tham chiếu đến khai báo tương ứng.

### 14.2. Type environment

Lưu kiểu của biến, tham số, hàm, trường, kiểu miền và các thành phần dựng sẵn. Môi trường có thể được mở rộng theo phạm vi.

### 14.3. Expression type checker

Duyệt từng nút biểu thức và tính kiểu kết quả dựa trên kiểu của các nút con và quy tắc toán tử.

### 14.4. Statement checker

Kiểm tra câu lệnh gán, điều kiện, vòng lặp, khai báo, trả về và lời gọi hành động.

### 14.5. Constraint checker

Kiểm tra các ràng buộc bổ sung như multiplicity, kiểu miền, quan hệ giữa thuộc tính hoặc điều kiện chỉ có thể xác định sau khi mô hình đã được xây dựng.

### 14.6. Typed AST

Sau khi kiểm tra, công cụ có thể tạo AST đã gắn kiểu cho mỗi biểu thức. Các bước sinh mã hoặc diễn giải dùng thông tin này thay vì phải suy luận lại.

## 15. Mã giả cho type checker

Một checker đệ quy đơn giản có thể trả về kiểu của mỗi nút AST:

~~~text
function inferType(expression, environment):
    match expression:
        case IntegerLiteral(value):
            return Integer

        case StringLiteral(value):
            return String

        case Variable(name):
            if environment contains name:
                return environment.typeOf(name)
            else:
                report UnknownName(name)
                return ErrorType

        case Add(left, right):
            leftType = inferType(left, environment)
            rightType = inferType(right, environment)

            if leftType == Integer and rightType == Integer:
                return Integer

            if leftType == Money and rightType == Money:
                return Money

            report InvalidOperands("+", leftType, rightType)
            return ErrorType

        case GreaterThan(left, right):
            leftType = inferType(left, environment)
            rightType = inferType(right, environment)

            if comparable(leftType, rightType):
                return Boolean

            report IncomparableTypes(leftType, rightType)
            return ErrorType
~~~

ErrorType là kiểu đặc biệt dùng để tiếp tục phân tích sau một lỗi mà không tạo quá nhiều lỗi dây chuyền. Cách phục hồi cần được thiết kế để không che giấu lỗi gốc.

### 15.1. Kiểm tra câu lệnh gán

~~~text
function checkAssignment(target, value, environment):
    targetType = inferType(target, environment)
    valueType = inferType(value, environment)

    if isAssignable(valueType, targetType):
        return success

    report AssignmentTypeMismatch(
        expected = targetType,
        actual = valueType
    )
~~~

### 15.2. Kiểm tra điều kiện

~~~text
function checkCondition(condition, environment):
    conditionType = inferType(condition, environment)

    if conditionType != Boolean:
        report ExpectedBoolean(conditionType)
~~~

Mã giả chỉ minh họa cấu trúc. Một checker thực tế cần xử lý kiểu con, overload, generic, null, lỗi phân giải tên, vị trí nguồn và các quy tắc chuyển đổi.

## 16. Chất lượng thông báo lỗi kiểu

Một bộ kiểm tra kiểu hữu ích không chỉ trả về “type error”. Nó cần giúp người viết biết biểu thức nào sai, kiểu nào được mong đợi và cách sửa.

Thông báo nên có:

- Tệp và vị trí nguồn.
- Biểu thức hoặc câu lệnh liên quan.
- Kiểu mong đợi.
- Kiểu thực tế.
- Quy tắc không thỏa.
- Gợi ý sửa khi có thể đưa ra chắc chắn.

Ví dụ chưa tốt:

~~~text
Type mismatch.
~~~

Ví dụ rõ hơn:

~~~text
rules.dsl:12:18
Không thể gán String vào order.total.
Kiểu mong đợi: Money
Kiểu thực tế: String
Hãy dùng một giá trị Money hoặc chuyển đổi chuỗi bằng thao tác parseMoney tường minh.
~~~

### 16.1. Phân biệt kiểu mong đợi và kiểu thực tế

Thông báo cần tránh đảo ngược hai kiểu. Với phép gán total = "free", kiểu mong đợi ở vế phải là kiểu tương thích với total, chẳng hạn Money; kiểu thực tế của literal là String.

### 16.2. Đưa ngữ cảnh miền vào lỗi

Thay vì chỉ nói “Expected Boolean”, công cụ có thể nói “Điều kiện sau when phải trả về đúng hoặc sai; biểu thức order.total có kiểu Money”. Thông báo như vậy giúp chuyên gia miền hiểu vấn đề mà không cần biết chi tiết compiler.

### 16.3. Gợi ý sửa cần thận trọng

Nếu tên trường gần giống, công cụ có thể đề xuất tên tương tự. Nếu kiểu không tương thích, chỉ gợi ý chuyển đổi khi có phép chuyển đổi rõ ràng. Không nên tự sửa hoặc tự ép kiểu làm thay đổi ý nghĩa nghiệp vụ.

## 17. Giới hạn của kiểm tra kiểu tĩnh

Kiểm tra kiểu tĩnh rất hữu ích nhưng không chứng minh chương trình đúng trong mọi tình huống.

### 17.1. Dữ liệu chỉ biết khi chạy

Một biểu thức có kiểu Integer vẫn có thể nhận giá trị âm khi dữ liệu được nạp từ hệ thống bên ngoài. Nếu miền yêu cầu số lượng dương, cần kiểu PositiveInteger có constructor xác thực hoặc validator runtime.

### 17.2. Trạng thái thay đổi

Một Order có thể có kiểu Order ở mọi thời điểm, nhưng trạng thái của nó thay đổi từ NEW sang SHIPPED. Kiểu tĩnh cơ bản không tự chứng minh thao tác hủy hợp lệ tại thời điểm chạy.

### 17.3. Tài nguyên bên ngoài

Kiểm tra kiểu không bảo đảm dịch vụ thanh toán đang hoạt động, người dùng có quyền hoặc bản ghi được tham chiếu vẫn tồn tại.

### 17.4. Schema thay đổi

Nếu dữ liệu thực tế khác schema dùng lúc kiểm tra, biểu thức đã được chấp nhận có thể thất bại khi chạy. Cần quản lý phiên bản schema và xác thực tại ranh giới tích hợp.

### 17.5. Kiểu quá rộng

Nếu DSL cho phép Any, Dynamic hoặc kiểu không xác định ở nhiều nơi, bộ kiểm tra không thể phát hiện các thao tác mà nó thiếu thông tin. Kiểu quá rộng làm giảm lợi ích của kiểm tra tĩnh.

### 17.6. Không thay thế kiểm thử

Kiểm tra kiểu không chứng minh thuật toán đúng, kết quả phù hợp chính sách hoặc mọi trường hợp biên đã được xử lý. Vẫn cần kiểm thử đơn vị, kiểm thử tích hợp và xác thực nghiệp vụ.

## 18. Kiểm tra kiểu tĩnh so với kiểm tra kiểu động

| Tiêu chí | Kiểm tra kiểu tĩnh | Kiểm tra kiểu động |
|---|---|---|
| Thời điểm | Trước khi thực thi | Khi biểu thức chạy |
| Phát hiện lỗi | Có thể phát hiện sớm các sai khác kiểu đã biết | Chỉ phát hiện khi đường chạy liên quan được thực hiện |
| Thông tin cần có | AST, khai báo, schema hoặc môi trường kiểu | Giá trị và kiểu thực tế tại runtime |
| Tính linh hoạt | Bị ràng buộc bởi hệ kiểu và thông tin có sẵn | Linh hoạt với dữ liệu và kiểu thay đổi |
| Công cụ | Type checker, compiler, IDE | Runtime checks, interpreter, validator |
| Giới hạn | Không biết mọi trạng thái và dữ liệu tương lai | Lỗi có thể xuất hiện muộn và chỉ ở một số đường chạy |

Hai cách có thể được kết hợp. Ví dụ, một DSL có thể kiểm tra tĩnh rằng order.total là Money và phép so sánh với Money hợp lệ; khi chạy, nó vẫn kiểm tra giá trị tiền có nằm trong giới hạn chính sách hay không.

## 19. Kiểm thử bộ kiểm tra kiểu

Type checker là một thành phần có quy tắc rõ ràng nên cần được kiểm thử bằng cả trường hợp hợp lệ và không hợp lệ.

### 19.1. Kiểm thử biểu thức hợp lệ

Ví dụ:

- Integer + Integer cho kết quả Integer.
- Money + Money cho kết quả Money nếu đơn vị tương thích.
- Date > Date cho kết quả Boolean.
- Gọi hàm với đúng số lượng và kiểu tham số.
- Truy cập thuộc tính tồn tại trên kiểu tương ứng.
- Dùng kiểu con ở vị trí chấp nhận kiểu cha nếu subtyping được hỗ trợ.

### 19.2. Kiểm thử biểu thức sai kiểu

Ví dụ:

- Integer + String.
- Money * Customer.
- Gán String vào thuộc tính Money.
- Dùng Money làm điều kiện Boolean.
- Gọi hàm với sai số lượng tham số.
- Truy cập thuộc tính không tồn tại.
- Truyền OrderId vào vị trí yêu cầu CustomerId.

### 19.3. Kiểm thử suy luận kiểu

Kiểm tra literal, biểu thức lồng nhau, danh sách rỗng, overload và kiểu trả về. Cần xác định trường hợp nào có thể suy luận và trường hợp nào phải yêu cầu chú thích kiểu.

### 19.4. Kiểm thử phạm vi và shadowing

Kiểm tra tên ở phạm vi toàn cục, cục bộ, hàm và khối lệnh. Nếu shadowing được hỗ trợ, xác nhận đúng khai báo được sử dụng. Nếu bị cấm, xác nhận lỗi được báo tại khai báo trùng.

### 19.5. Kiểm thử lỗi và vị trí nguồn

Mỗi lỗi kiểu nên trỏ đến biểu thức gây lỗi, không chỉ trỏ đến đầu tệp. Với biểu thức lồng nhau, thông báo cần xác định đúng toán hạng sai hoặc vị trí lời gọi hàm.

### 19.6. Kiểm thử schema và phiên bản

Chạy cùng một DSL source với các phiên bản schema khác nhau để xác nhận trường bị đổi hoặc bị xóa được báo đúng. Kiểm tra trường hợp schema không tải được hoặc không khớp phiên bản.

### 19.7. Kiểm thử hồi quy

Khi thêm toán tử, kiểu miền hoặc overload, chạy lại các trường hợp trước đó để bảo đảm quy tắc kiểu cũ không thay đổi ngoài ý muốn.

## 20. Hiệu năng và phân tích tăng dần

Với DSL nhỏ, type checker có thể duyệt toàn bộ AST mỗi lần người dùng thay đổi nội dung. Với DSL lớn hoặc IDE tương tác, có thể cần tối ưu.

### 20.1. Tái sử dụng thông tin kiểu

Nếu một phần AST không thay đổi và môi trường kiểu không thay đổi, công cụ có thể lưu kết quả suy luận để tránh tính lại.

### 20.2. Phân tích tăng dần

Incremental type checking chỉ kiểm tra lại những phần bị ảnh hưởng bởi chỉnh sửa. Điều này cần theo dõi phụ thuộc giữa biểu thức, khai báo, schema và kiểu.

Ví dụ, đổi kiểu của biến unitPrice có thể ảnh hưởng đến mọi biểu thức sử dụng biến đó. Công cụ cần đánh dấu các nút phụ thuộc để kiểm tra lại.

### 20.3. Tránh tối ưu quá sớm

Đối với DSL nhỏ, một checker đệ quy đơn giản và rõ ràng thường dễ bảo trì. Chỉ bổ sung cache hoặc phân tích tăng dần khi kích thước chương trình hoặc trải nghiệm IDE thực sự yêu cầu.

## 21. Thiết kế hệ kiểu cho DSL: các quyết định quan trọng

Khi thiết kế kiểm tra kiểu tĩnh, nhóm phát triển nên xác định:

1. DSL có những kiểu nguyên thủy nào?
2. Có cần kiểu miền riêng như Money, OrderId hoặc Percentage không?
3. Biểu thức nào trả về kiểu nào?
4. Phép toán nào được hỗ trợ cho từng kiểu?
5. Có kiểu con, generic, union hoặc kiểu hàm không?
6. Kiểu có thể nullable hoặc optional không?
7. Chuyển đổi nào tự động và chuyển đổi nào phải tường minh?
8. Biến có kiểu cố định hay được phép đổi kiểu?
9. Kiểu của trường lấy từ metamodel hay schema bên ngoài?
10. Lỗi kiểu được phát hiện ở thời điểm nào?
11. Runtime còn cần xác thực điều gì?
12. Thông báo lỗi sẽ dùng thuật ngữ kỹ thuật hay thuật ngữ nghiệp vụ?

Một hệ kiểu nhỏ nhưng nhất quán thường hữu ích hơn một hệ kiểu nhiều tính năng nhưng không có quy tắc rõ ràng.

## 22. Ví dụ tổng hợp: kiểm tra kiểu của một quy tắc DSL

Xét quy tắc:

~~~text
rule "high_value_order" {
    when order.total >= 10000000
         and order.customer.isActive == true
    then applyDiscount(order, 5%)
}
~~~

Giả sử schema và hàm dựng sẵn:

~~~text
Order.total: Money
Order.customer: Customer
Customer.isActive: Boolean

applyDiscount(order: Order, rate: Percentage) -> Unit
~~~

### 22.1. Phân giải tên

Công cụ xác định:

- order là biến có kiểu Order.
- total là thuộc tính Money của Order.
- customer là thuộc tính Customer của Order.
- isActive là thuộc tính Boolean của Customer.
- applyDiscount là hàm được cung cấp.

### 22.2. Kiểm tra biểu thức so sánh

Biểu thức order.total >= 10000000 cần xác định literal 10000000 được diễn giải thành Money hay Integer. Nếu DSL hỗ trợ literal tiền tệ ngầm theo ngữ cảnh, checker cần áp dụng quy tắc đó. Nếu không, người viết phải dùng literal rõ đơn vị:

~~~text
order.total >= 10000000 VND
~~~

Kết quả so sánh có kiểu Boolean.

### 22.3. Kiểm tra biểu thức logic

order.customer.isActive có kiểu Boolean; true cũng có kiểu Boolean. Phép and giữa hai biểu thức Boolean cho kết quả Boolean. Vì vậy, điều kiện của when hợp lệ.

### 22.4. Kiểm tra lời gọi hành động

order có kiểu Order; 5% có kiểu Percentage. Chữ ký applyDiscount yêu cầu Order và Percentage, nên lời gọi hợp lệ về kiểu.

### 22.5. Những điều vẫn cần kiểm tra khi chạy

Mặc dù biểu thức hợp lệ về kiểu, hệ thống vẫn có thể cần xác minh:

- Đơn hàng có tồn tại không.
- Khách hàng có còn hoạt động không tại thời điểm xử lý.
- Đơn hàng có đủ điều kiện áp dụng giảm giá theo chính sách hiện hành không.
- Người thực thi có quyền áp dụng giảm giá không.
- Dịch vụ cập nhật đơn hàng có hoạt động không.

Ví dụ này cho thấy kiểm tra kiểu tĩnh xác nhận cấu trúc và tính tương thích của giá trị, còn tính hợp lệ nghiệp vụ có thể phụ thuộc trạng thái runtime.

## 23. Những hiểu lầm thường gặp

### Kiểm tra kiểu tĩnh đồng nghĩa với biên dịch

Không hoàn toàn. Kiểm tra kiểu tĩnh có thể được thực hiện trong compiler, language server, công cụ kiểm tra cấu hình hoặc khi lưu một mô hình DSL. Điểm cốt lõi là kiểm tra trước khi thực thi.

### Có khai báo kiểu là không còn lỗi kiểu

Không đúng. Khai báo kiểu chỉ cung cấp thông tin. Công cụ vẫn cần kiểm tra phép gán, lời gọi hàm, phép toán, truy cập thuộc tính và dữ liệu tại ranh giới.

### Suy luận kiểu là kiểm tra kiểu động

Không đúng. Suy luận kiểu có thể diễn ra hoàn toàn tĩnh. Người viết không cần khai báo mọi kiểu nhưng công cụ vẫn xác định kiểu trước khi chạy.

### Biểu thức đúng kiểu thì chắc chắn đúng nghiệp vụ

Không đúng. Kiểu Money không chứng minh số tiền hợp lệ theo chính sách; kiểu Order không chứng minh đơn hàng đang ở trạng thái cho phép thao tác.

### Càng nhiều chuyển đổi ngầm càng dễ dùng

Không nhất thiết. Chuyển đổi ngầm thiếu rõ ràng có thể che giấu lỗi đơn vị, định dạng hoặc mất dữ liệu. Chỉ nên hỗ trợ các chuyển đổi có quy tắc và kết quả dễ đoán.

## 24. Bài tập tự kiểm tra

### Bài 1: Phân biệt các giai đoạn

Một DSL có biểu thức:

~~~text
order.prcie + "free"
~~~

Hãy phân biệt lỗi có thể xảy ra ở giai đoạn phân giải tên và kiểm tra kiểu. Giả sử Order không có trường prcie và có trường price kiểu Money.

### Bài 2: Xây môi trường kiểu

Cho các khai báo:

~~~text
quantity: Integer
unitPrice: Money
customer: Customer
~~~

Hãy viết môi trường kiểu Γ và xác định kiểu của quantity * 2 nếu DSL định nghĩa Integer × Integer trả về Integer.

### Bài 3: Viết quy tắc kiểu

Hãy mô tả quy tắc kiểu cho phép so sánh hai giá trị Date bằng toán tử lớn hơn. Kết quả có kiểu gì? Điều gì xảy ra nếu một toán hạng là String?

### Bài 4: Kiểm tra lời gọi hàm

Một hàm có chữ ký:

~~~text
ship(order: Order, address: Address, priority: Boolean) -> Shipment
~~~

Xác định lỗi trong các lời gọi:

~~~text
ship(order, address)
ship(order, "Hanoi", true)
ship(order, address, true)
~~~

Giả sử các biến order và address có đúng kiểu được khai báo.

### Bài 5: Suy luận kiểu

Với:

~~~text
let count = 3
let next = count + 1
~~~

Hãy xác định kiểu của count và next. Nếu đổi giá trị khởi tạo count thành "three", lỗi nào có thể xuất hiện ở biểu thức tiếp theo?

### Bài 6: Optional và null

Một thuộc tính customer.email có kiểu Optional<String>. Hãy đề xuất cách kiểm tra trước khi gọi thao tác length và giải thích vì sao không nên truy cập trực tiếp nếu chưa xác nhận giá trị tồn tại.

### Bài 7: Kiểu miền

Hệ thống dùng Integer cho CustomerId và OrderId. Hãy giải thích một lỗi mà cách thiết kế này có thể bỏ lọt và đề xuất kiểu miền riêng để type checker phát hiện.

### Bài 8: Giới hạn kiểm tra tĩnh

Một quy tắc gọi cancel(order) đã được kiểm tra kiểu hợp lệ. Khi chạy, đơn hàng đã chuyển sang trạng thái SHIPPED. Giải thích vì sao type checker cơ bản không thể tự phát hiện điều này và đề xuất lớp kiểm tra phù hợp.

### Bài 9: Schema thay đổi

Schema phiên bản 1 có trường order.total; phiên bản 2 đổi thành order.grandTotal. Hãy mô tả cách công cụ nên quản lý phiên bản schema, thông báo lỗi và hỗ trợ di chuyển DSL source.

### Bài 10: Thiết kế chiến lược kiểm tra

Một DSL cho chuyên viên nghiệp vụ viết quy tắc giá. Hãy đề xuất kiểu nguyên thủy, kiểu miền, quy tắc toán tử, cách suy luận kiểu và những điều kiện cần xác thực khi chạy.

## Kết luận

Kiểm tra kiểu tĩnh phân tích DSL trước khi thực thi để xác định các biểu thức, phép gán, lời gọi hàm và cấu trúc điều khiển có tuân theo hệ kiểu hay không. Công cụ sử dụng môi trường kiểu, phân giải tên và các quy tắc suy luận để xác định kiểu của từng nút trong AST. Hệ kiểu có thể bao gồm kiểu nguyên thủy, kiểu miền, collection, hàm, kiểu con và giá trị tùy chọn. Một bộ kiểm tra tốt báo lỗi sớm, chỉ rõ kiểu mong đợi và kiểu thực tế, đồng thời hỗ trợ người viết sửa đúng vấn đề. Tuy vậy, kiểm tra kiểu tĩnh không thay thế xác thực dữ liệu, trạng thái và quy tắc nghiệp vụ phụ thuộc runtime. Thiết kế DSL cần xác định rõ ranh giới giữa điều có thể chứng minh trước khi chạy và điều phải kiểm tra khi hệ thống thực sự xử lý dữ liệu.

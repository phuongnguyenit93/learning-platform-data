# Giá trị null

## 1. Giá trị null là gì?

Trong hệ kiểu của một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **null** thường biểu diễn việc một giá trị không hiện diện hoặc chưa có giá trị cụ thể tại một vị trí. Nó khác với một giá trị bình thường như số 0, chuỗi rỗng hay false.

Ví dụ:

~~~text
customer.middle_name = null
order.note = ""
order.total = 0 VND
promotion.enabled = false
~~~

Bốn trường hợp có ý nghĩa khác nhau:

- middle_name không có giá trị tên đệm.
- note là một chuỗi có mặt nhưng không chứa ký tự nào.
- total có giá trị tiền tệ bằng không.
- enabled có giá trị Boolean false.

Nếu DSL coi tất cả các trường hợp này là tương đương, chương trình sẽ mất thông tin quan trọng. Chẳng hạn, một đơn hàng có tổng tiền bằng 0 vẫn có thể là đơn hàng hợp lệ; một ghi chú rỗng vẫn khác với việc chưa cung cấp ghi chú.

Null xuất hiện trong nhiều ngữ cảnh: dữ liệu đầu vào, cấu hình, kết quả truy vấn, trường tùy chọn, biến chưa được gán, giá trị trả về hoặc thuộc tính của đối tượng. Vì vậy, DSL cần định nghĩa null ở cả cấp kiểu dữ liệu, cú pháp, kiểm tra tĩnh và hành vi khi chạy.

## 2. Phân biệt null với các trạng thái dễ nhầm lẫn

Không nên dùng null như một cách biểu diễn chung cho mọi dạng thiếu thông tin. Các trạng thái sau có thể khác nhau:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| Null | Có một giá trị null được biểu diễn rõ ràng | note = null |
| Missing / absent | Trường không xuất hiện trong dữ liệu | Không có khóa note trong object |
| Empty string | Có chuỗi nhưng độ dài bằng 0 | note = "" |
| Zero | Giá trị số bằng 0 | quantity = 0 |
| False | Giá trị Boolean false | enabled = false |
| Unknown | Chưa biết giá trị hoặc chưa thể xác định | Kết quả tra cứu đang chờ |
| Not applicable | Trường không áp dụng trong tình huống này | shipping_address với đơn nhận tại quầy |

Một hệ thống có thể chọn gộp một số trạng thái nếu nghiệp vụ cho phép, nhưng quyết định đó phải rõ ràng. Không nên vô tình gộp chúng chỉ vì kiểu dữ liệu hoặc API hiện tại thuận tiện hơn.

### 2.1 Null và missing

Giả sử DSL đọc một object cấu hình:

~~~json
{
  "retry_limit": null
}
~~~

Khóa retry_limit có mặt và mang giá trị null. Nếu object không có khóa retry_limit, trạng thái là missing. Hai trường hợp có thể mang ý nghĩa:

- Missing: dùng giá trị mặc định của hệ thống.
- Null: người cấu hình chủ động yêu cầu không đặt giới hạn hoặc tắt tính năng.

Đó chỉ là một chính sách minh họa. Trong một DSL khác, null có thể không hợp lệ và missing mới là cách duy nhất để dùng mặc định.

Khi thiết kế DSL cho cấu hình, API hoặc dữ liệu trao đổi, hãy quyết định rõ liệu cần phân biệt ba trạng thái: không cung cấp, cung cấp null và cung cấp một giá trị cụ thể.

### 2.2 Null và chuỗi rỗng

Chuỗi rỗng vẫn là một giá trị chuỗi:

~~~text
display_name = ""
~~~

Null không phải chuỗi:

~~~text
display_name = null
~~~

Nếu DSL cần kiểm tra nội dung, có thể có các phép kiểm tra riêng:

~~~text
display_name is null
display_name == ""
display_name is blank
~~~

is blank có thể coi chuỗi chỉ gồm khoảng trắng là trống, trong khi phép so sánh với chuỗi rỗng thì không. Cần định nghĩa rõ việc chuẩn hóa Unicode và khoảng trắng nếu dùng quy tắc này.

## 3. Null trong hệ kiểu

Một hệ kiểu phải xác định kiểu nào có thể chứa null và kiểu nào không thể.

### 3.1 Kiểu không nullable và kiểu nullable

Một kiểu không nullable chỉ nhận giá trị thuộc kiểu đó:

~~~text
age: Integer
~~~

Nếu age là kiểu không nullable, giá trị null không hợp lệ.

Một kiểu nullable cho phép cả giá trị thuộc kiểu gốc và null:

~~~text
middle_name: String?
~~~

Dấu hỏi là một quy ước thường gặp để chỉ kiểu nullable; DSL cụ thể có thể dùng cú pháp khác. Theo cách hiểu này, middle_name có thể là String hoặc null.

Có thể mô hình hóa:

\[
Nullable(T) = T \cup \{null\}
\]

Đây là cách diễn đạt khái niệm: kiểu nullable chứa các giá trị của T cùng một giá trị null. Trong một hệ kiểu cụ thể, cách triển khai có thể là tagged union, option type, reference có khả năng null hoặc một cơ chế riêng.

### 3.2 Null type

Một số ngôn ngữ xem null là một literal có kiểu riêng, đôi khi gọi là Null type hoặc bottom-like type. Literal null có thể được gán cho một kiểu nullable tương thích, nhưng không thể gán cho kiểu không nullable.

Ví dụ:

~~~text
String? name = null       // hợp lệ
Integer? count = null     // hợp lệ
String name = null        // lỗi kiểu nếu String không nullable
~~~

DSL có thể suy luận kiểu của null từ ngữ cảnh. Ví dụ, trong phép gán cho biến String?, literal null được hiểu là giá trị rỗng của kiểu nullable đó. Nhưng biểu thức chỉ gồm null mà không có kiểu đích có thể mơ hồ.

~~~text
let x = null
~~~

Nếu không có thông tin kiểu khác, compiler cần một chính sách: từ chối vì không suy luận được kiểu, gán kiểu Null đặc biệt, hoặc yêu cầu khai báo kiểu tường minh.

### 3.3 Null không phải một kiểu dữ liệu nghiệp vụ

Null không nên thay thế các kiểu miền như:

- UnknownCustomer
- NotProvided
- NotApplicable
- PendingResult
- Unavailable

Nếu trạng thái có ý nghĩa nghiệp vụ riêng, nên biểu diễn nó bằng một kiểu hoặc trạng thái rõ ràng. Null chỉ nên dùng khi thực sự muốn nói rằng không có giá trị theo hợp đồng của kiểu.

## 4. Cách biểu diễn null trong DSL

Một DSL thường dùng từ khóa null:

~~~text
customer.middle_name = null
~~~

Lexer nhận diện null như một keyword hoặc literal token. Parser tạo node null literal trong AST. Semantic analyzer kiểm tra vị trí sử dụng có chấp nhận null không.

### 4.1 Null literal trong AST

AST có thể có node riêng:

~~~java
sealed interface Expression {}

record NullLiteral() implements Expression {}
record StringLiteral(String value) implements Expression {}
record IntegerLiteral(long value) implements Expression {}
~~~

Một cách khác là tạo LiteralExpression có kiểu và giá trị tổng quát:

~~~java
record LiteralExpression(
    Type type,
    Object value
) implements Expression {}
~~~

Nếu dùng Object value, cần bảo đảm type và value nhất quán. Không nên để một literal null có type String nhưng lại được xử lý như Integer ở backend.

### 4.2 Null như keyword hay identifier

Nếu null là literal dành riêng, người dùng không thể dùng null làm tên biến thông thường. Đây là lựa chọn phổ biến vì giảm mơ hồ.

Nếu DSL cho phép identifier tên null, parser phải dùng ngữ cảnh để phân biệt. Cách này thường không đem lại lợi ích đủ lớn so với sự phức tạp.

### 4.3 Null trong JSON và YAML

Nếu DSL sử dụng JSON hoặc YAML làm định dạng cấu hình, cần tuân theo quy tắc của định dạng đó hoặc công bố rõ phần mở rộng.

JSON có literal null viết thường:

~~~json
{
  "middle_name": null,
  "nickname": ""
}
~~~

YAML có nhiều cách viết null theo phiên bản và parser, ví dụ null hoặc ~. Nếu muốn file cấu hình nhất quán giữa nhiều công cụ, nên chọn một cách viết chuẩn và kiểm tra hành vi của thư viện parser.

Không nên giả định mọi định dạng cấu hình đều phân biệt null và missing theo cùng một cách.

## 5. Kiểm tra null ở thời điểm biên dịch

Một DSL có hệ kiểu tĩnh có thể phát hiện nhiều lỗi liên quan null trước khi chạy.

Ví dụ:

~~~text
let name: String = null
~~~

Nếu String không nullable, semantic analyzer phải từ chối phép gán.

Ngược lại:

~~~text
let name: String? = null
~~~

là hợp lệ nếu String? là kiểu nullable.

### 5.1 Gán giá trị nullable vào kiểu không nullable

~~~text
let optional_name: String? = customer.middle_name
let required_name: String = optional_name
~~~

Phép gán thứ hai không an toàn vì optional_name có thể là null. DSL nên yêu cầu kiểm tra hoặc cung cấp giá trị thay thế trước khi chuyển sang kiểu không nullable.

### 5.2 Gán giá trị không nullable vào kiểu nullable

~~~text
let required_name: String = "An"
let optional_name: String? = required_name
~~~

Phép gán này thường an toàn: mọi String đều là một giá trị hợp lệ của String?. Đây là chiều mở rộng từ tập giá trị hẹp sang tập giá trị rộng hơn.

### 5.3 Suy luận kiểu với null

Các trường hợp cần được định nghĩa:

| Biểu thức | Vấn đề cần giải quyết |
|---|---|
| let x = null | Không có kiểu đích để suy luận |
| let x: String? = null | Kiểu đích đã rõ |
| let x = if c then null else "A" | Suy luận kiểu hợp nhất thành String? |
| list = [null, "A"] | Suy luận kiểu phần tử nullable |
| function(null) | Chọn overload nào nếu có nhiều kiểu nullable? |

Khi có nhiều overload nhận các kiểu nullable khác nhau, literal null có thể gây mơ hồ. Có thể yêu cầu ép kiểu tường minh hoặc cung cấp cú pháp khai báo kiểu.

## 6. Kiểm tra luồng null (flow-sensitive typing)

Một số hệ kiểu cho phép thu hẹp kiểu sau khi kiểm tra null. Kỹ thuật này thường được gọi là flow-sensitive typing hoặc smart cast.

Ví dụ:

~~~text
if customer.middle_name is not null
  print(customer.middle_name.length)
~~~

Trong nhánh if, hệ thống có thể suy luận middle_name không null và cho phép truy cập length mà không cần kiểm tra lại.

### 6.1 Type narrowing

Ban đầu:

~~~text
middle_name: String?
~~~

Sau điều kiện:

~~~text
middle_name is not null
~~~

Trong nhánh đúng, kiểu có thể được thu hẹp thành String. Trong nhánh else, giá trị còn lại là null nếu biểu thức chỉ có hai khả năng String và null.

### 6.2 Kiểm tra bằng equality

DSL có thể cho phép:

~~~text
if value != null
  use(value)
~~~

Nhưng cần xác định phép so sánh với null có tạo ra thông tin đủ để thu hẹp kiểu hay không. Nếu equality có thể bị overload hoặc có tác dụng phụ, phân tích luồng cần một quy tắc rõ ràng.

### 6.3 Alias và thay đổi giá trị

Smart cast chỉ an toàn nếu giá trị không thể thay đổi theo cách làm mất điều kiện đã kiểm tra. Ví dụ:

~~~text
if account.owner is not null
  update_account()
  print(account.owner.name)
~~~

Nếu update_account có thể thay đổi account.owner, giá trị có thể trở thành null sau khi kiểm tra. DSL cần chọn chính sách:

- Chỉ cho smart cast với biến bất biến.
- Dùng snapshot của giá trị đã kiểm tra.
- Yêu cầu kiểm tra lại sau lời gọi có tác dụng phụ.
- Không hỗ trợ smart cast trong tình huống alias có thể thay đổi.

Không nên cho phép compiler suy luận không null nếu runtime không thể bảo đảm điều kiện vẫn đúng.

## 7. Các cách xử lý null trong biểu thức

DSL có thể cung cấp một số toán tử để xử lý giá trị nullable.

### 7.1 Kiểm tra null tường minh

~~~text
if value is null
  use_default()
else
  process(value)
~~~

Đây là cách dễ đọc và cho phép xử lý riêng từng trường hợp.

### 7.2 Null coalescing

Toán tử null coalescing thường có dạng ??:

~~~text
display_name = customer.nickname ?? customer.legal_name
~~~

Nếu vế trái không null, kết quả là vế trái. Nếu vế trái null, kết quả là vế phải.

Ngữ nghĩa cần xác định vế phải có được đánh giá lazy hay không. Thông thường, toán tử này chỉ đánh giá vế phải khi vế trái null, giúp tránh thao tác không cần thiết.

### 7.3 Safe navigation

Safe navigation có thể dùng ?.:

~~~text
city = customer.address?.city
~~~

Nếu customer.address là null, biểu thức trả null mà không truy cập city. Nếu không null, nó trả giá trị city.

Kiểu kết quả thường trở thành nullable, ngay cả khi city bên trong là kiểu không nullable, vì toàn bộ chuỗi truy cập có thể dừng ở một đối tượng null.

### 7.4 Non-null assertion

Một số ngôn ngữ cho phép toán tử khẳng định không null:

~~~text
print(customer.nickname!)
~~~

Toán tử ! khẳng định rằng người viết tin giá trị không null. Nếu giả định sai, runtime có thể phát sinh lỗi.

Đây là cách bỏ qua bảo vệ kiểu và nên dùng hạn chế. DSL có thể không cung cấp toán tử này, hoặc chỉ cho phép trong ngữ cảnh được kiểm soát.

### 7.5 Hàm mặc định

Một số API cung cấp hàm:

~~~text
value.or_else("Unknown")
~~~

hoặc:

~~~text
value.or_else_get(compute_default)
~~~

Hai dạng có thể khác nhau về thời điểm tính giá trị mặc định. Dạng thứ nhất có thể đánh giá sẵn đối số; dạng thứ hai chỉ gọi hàm khi cần.

## 8. Ngữ nghĩa của toán tử với null

Một phần quan trọng của hệ kiểu là xác định từng toán tử hoạt động ra sao khi một toán hạng là null.

### 8.1 So sánh bằng và khác

Có nhiều mô hình:

**Null equality:** null == null trả true; null == một giá trị không null trả false.

**Unknown comparison:** mọi phép so sánh thông thường có null tạo ra unknown.

**Error on null:** phép so sánh không được phép và gây lỗi.

Không có một quy tắc phù hợp cho mọi DSL. Điều quan trọng là phải chọn và tài liệu hóa.

Nếu DSL dùng quy tắc null equality:

| Biểu thức | Kết quả |
|---|---|
| null == null | true |
| null == "A" | false |
| null != "A" | true |

Nếu DSL dùng logic ba giá trị kiểu SQL, kết quả sẽ khác; phần tiếp theo giải thích mô hình đó.

### 8.2 So sánh thứ tự

Các biểu thức:

~~~text
null < 10
null >= 10
~~~

cần có hành vi được định nghĩa. Một lựa chọn là trả unknown; lựa chọn khác là lỗi kiểu hoặc lỗi dữ liệu. Không nên tự coi null là 0 hoặc nhỏ hơn mọi giá trị nếu nghiệp vụ chưa quy định.

### 8.3 Số học

Với null propagation:

~~~text
null + 5 = null
null * 2 = null
~~~

Đây là một chính sách có thể dùng, nhưng không bắt buộc. Một DSL có thể từ chối phép toán khi toán hạng null để tránh âm thầm lan truyền thiếu dữ liệu.

Nếu chọn null propagation, cần xem xét biểu thức lồng nhau: một null có thể làm toàn bộ kết quả trở thành null. Người dùng cần biết cách xử lý bằng coalescing hoặc kiểm tra tường minh.

### 8.4 Boolean logic

Nếu Boolean có thể nullable, cần định nghĩa AND, OR và NOT với null. Có thể dùng logic ba giá trị:

| A | NOT A |
|---|---|
| true | false |
| false | true |
| unknown | unknown |

Với AND:

| A | B | A AND B |
|---|---|---|
| true | true | true |
| true | false | false |
| true | unknown | unknown |
| false | true | false |
| false | false | false |
| false | unknown | false |
| unknown | true | unknown |
| unknown | false | false |
| unknown | unknown | unknown |

Với OR:

| A | B | A OR B |
|---|---|---|
| true | true | true |
| true | false | true |
| true | unknown | true |
| false | true | true |
| false | false | false |
| false | unknown | unknown |
| unknown | true | true |
| unknown | false | unknown |
| unknown | unknown | unknown |

Logic ba giá trị thường hữu ích khi DSL làm việc với dữ liệu có thể thiếu. Tuy nhiên, nó khiến kết quả điều kiện có thể là true, false hoặc unknown. Câu lệnh if, rule engine và bộ lọc cần định nghĩa cách xử lý unknown.

## 9. Null và logic ba giá trị trong SQL

SQL là ví dụ quen thuộc về logic ba giá trị. Trong nhiều phép so sánh SQL, nếu một toán hạng là NULL thì kết quả là UNKNOWN, không phải TRUE hoặc FALSE.

Ví dụ:

~~~sql
SELECT *
FROM customer
WHERE middle_name = NULL;
~~~

Điều kiện trên không dùng để tìm các dòng có giá trị NULL. Cần dùng:

~~~sql
SELECT *
FROM customer
WHERE middle_name IS NULL;
~~~

Tương tự, IS NOT NULL dùng để tìm giá trị có mặt.

### 9.1 WHERE xử lý UNKNOWN

Trong SQL, WHERE chỉ giữ hàng khi điều kiện là TRUE. FALSE và UNKNOWN đều không được chọn.

Ví dụ:

~~~sql
SELECT *
FROM order_record
WHERE amount > 100;
~~~

Nếu amount là NULL, biểu thức amount > 100 trả UNKNOWN và hàng không được chọn.

### 9.2 NOT và UNKNOWN

Trong logic ba giá trị:

~~~sql
NOT UNKNOWN = UNKNOWN
~~~

Vì vậy, đổi điều kiện bằng NOT không nhất thiết biến trường hợp null thành kết quả đối lập như với Boolean hai giá trị.

### 9.3 NOT IN và null

Một lỗi thường gặp:

~~~sql
customer_id NOT IN (1, 2, NULL)
~~~

Nếu danh sách bên phải có NULL, kết quả của phép NOT IN có thể là UNKNOWN cho các giá trị không khớp, khiến truy vấn không trả hàng như người viết mong đợi. Khi xây DSL sinh SQL, cần hiểu rõ quy tắc này và không giả định NOT IN luôn là phủ định đơn giản của IN trong mọi trường hợp null.

Có thể cần loại bỏ null khỏi tập so sánh, dùng NOT EXISTS hoặc định nghĩa semantics khác rồi chuyển đổi cẩn thận.

## 10. Optional, Maybe và kiểu union

Một số hệ sinh thái biểu diễn giá trị có thể vắng mặt bằng kiểu bao (wrapper type) thay vì cho phép mọi reference nhận null.

Ví dụ:

- Java: Optional<T> cho kết quả có thể không có giá trị.
- Kotlin: T? biểu diễn kiểu nullable.
- Rust: Option<T> với Some(value) hoặc None.
- Haskell: Maybe a với Just value hoặc Nothing.
- TypeScript: T | null hoặc T | undefined.

Các cách này có điểm chung là trạng thái có hoặc không có giá trị được thể hiện trong kiểu, nhưng chi tiết ngữ nghĩa khác nhau.

### 10.1 Option/Maybe

Có thể mô hình hóa:

~~~text
Option<T> =
    Some(T)
  | None
~~~

Khi đó, null không cần được phép ở mọi vị trí. Một hàm tìm khách hàng có thể trả Option<Customer>:

~~~text
find_customer(id) -> Option<Customer>
~~~

Người gọi phải xử lý Some hoặc None:

~~~text
match find_customer(id)
  Some(customer) -> process(customer)
  None -> report_not_found()
~~~

### 10.2 Nullable reference và Optional không hoàn toàn giống nhau

Nullable reference thường cho phép giá trị null nằm trực tiếp trong biến. Optional là một object hoặc kiểu đại diện cho hai trạng thái có/không có giá trị.

Optional có thể giúp API thể hiện ý định rõ hơn, nhưng không tự động giải quyết mọi vấn đề:

- Optional có thể bị null nếu ngôn ngữ cho phép.
- Optional lồng nhau có thể biểu diễn nhiều trạng thái nhưng khó hiểu.
- Optional không tự phân biệt missing với explicit null trừ khi được thiết kế như vậy.
- Việc serialize Optional cần quy tắc riêng.

DSL nên chọn mô hình phù hợp với miền và công bố rõ cách chuyển đổi sang kiểu của ngôn ngữ triển khai.

## 11. Hàm và tham số nullable

Một hàm có thể nhận tham số nullable:

~~~text
greet(name: String?)
~~~

Ngữ nghĩa cần xác định hàm xử lý null thế nào. Có thể:

- Dùng tên mặc định.
- Bỏ qua phần chào tên.
- Trả lỗi vì tên là bắt buộc trong tình huống cụ thể.
- Trả về một kết quả nullable.

### 11.1 Tham số tùy chọn khác tham số nullable

Hai khái niệm này không giống nhau:

~~~text
function greet(name: String = "Guest")
~~~

Người gọi có thể bỏ qua tham số và hàm dùng mặc định.

~~~text
function greet(name: String?)
~~~

Người gọi phải cung cấp đối số, nhưng đối số có thể là null.

~~~text
function greet(name: String? = null)
~~~

Người gọi có thể bỏ qua tham số hoặc truyền null. Nếu cần phân biệt hai trường hợp, chữ ký này chưa đủ; cần một kiểu biểu diễn sự hiện diện riêng.

### 11.2 Return nullable

Một hàm tìm kiếm có thể trả về null khi không tìm thấy:

~~~text
find_customer(id) -> Customer?
~~~

Người gọi phải kiểm tra kết quả trước khi truy cập thuộc tính. Một API khác có thể trả Result<Customer, NotFoundError> để phân biệt không tìm thấy với lỗi hạ tầng.

Không nên dùng null cho mọi dạng thất bại nếu người gọi cần biết nguyên nhân.

## 12. Null trong collection và cấu trúc dữ liệu

Null có thể xuất hiện trong list, map hoặc object:

~~~text
values = [1, null, 3]
settings = {
  "timeout": null,
  "retry": 3
}
~~~

Hệ kiểu cần quyết định:

- List<Integer> có cho phép phần tử null không?
- Map có cho phép giá trị null không?
- Khóa map có thể null không?
- Một field nullable có khác với field bị thiếu không?
- Khi duyệt collection, phần tử null được xử lý ra sao?

Nếu list cho phép null, kiểu phần tử có thể là List<Integer?>. Nếu list không cho phép null, cần từ chối giá trị null ngay khi tạo hoặc chèn phần tử.

### 12.1 Null trong collection và lọc

Ví dụ:

~~~text
values.filter(value -> value > 0)
~~~

Nếu value có thể null, phép so sánh cần một quy tắc. Có thể lọc null trước:

~~~text
values
  .filter(value -> value is not null)
  .filter(value -> value > 0)
~~~

Hoặc DSL có toán tử null-safe. Nhưng không nên âm thầm bỏ phần tử null nếu người dùng không yêu cầu.

### 12.2 Map lookup

Khi truy vấn map, cần phân biệt:

- Key không tồn tại.
- Key tồn tại và value là null.
- Key tồn tại và value là giá trị bình thường.

Một phép get trả null duy nhất không thể phân biệt hai trường hợp đầu nếu map cho phép null value. API có thể cung cấp containsKey, lookup trả Option hoặc một kết quả tagged.

## 13. Null trong cơ sở dữ liệu và ánh xạ dữ liệu

Database thường có cột nullable. Khi DSL đọc hoặc ghi dữ liệu, cần xác định cách ánh xạ giữa null của DSL và NULL của database.

### 13.1 Cột nullable và NOT NULL

Schema:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    middle_name VARCHAR(100) NULL,
    email VARCHAR(255) NOT NULL
);
~~~

middle_name có thể chứa SQL NULL; email bắt buộc có giá trị. Nếu DSL cho phép email = null, lỗi có thể xuất hiện khi ghi database. Tốt hơn là kiểm tra ràng buộc trước hoặc chuyển lỗi database thành diagnostic rõ ràng.

### 13.2 Default value và NULL

Trong SQL, default thường được áp dụng khi cột bị bỏ khỏi lệnh INSERT hoặc khi dùng từ khóa DEFAULT theo cú pháp hỗ trợ. Truyền NULL tường minh không nhất thiết kích hoạt default.

Vì vậy, DSL sinh SQL cần phân biệt:

- Không phát sinh cột trong INSERT.
- Ghi NULL.
- Ghi DEFAULT.
- Ghi một giá trị cụ thể.

Nếu DSL gom tất cả thành null, hành vi dữ liệu có thể khác ý định người dùng.

### 13.3 Mapping từ database sang object

Khi đọc một hàng:

- SQL NULL có thể được ánh xạ thành null reference.
- Có thể được ánh xạ thành Optional.empty().
- Có thể được ánh xạ thành một trạng thái riêng.

Hãy bảo đảm kiểu đích cho phép giá trị null. Với kiểu nguyên thủy Java như int hoặc boolean, không thể lưu null trực tiếp; cần dùng wrapper Integer/Boolean hoặc một kiểu tùy chọn.

## 14. Null trong serialization và API

Các định dạng trao đổi có quy tắc riêng:

### 14.1 JSON

JSON phân biệt khóa vắng mặt và khóa có giá trị null:

~~~json
{}
~~~

khác với:

~~~json
{
  "middle_name": null
}
~~~

Với API cập nhật, sự khác biệt có thể rất quan trọng:

- Không gửi trường: không thay đổi giá trị hiện tại.
- Gửi null: xóa giá trị hiện tại.
- Gửi chuỗi: đặt giá trị mới.

Đây là một hợp đồng API phổ biến nhưng phải được xác nhận theo endpoint cụ thể.

### 14.2 JSON Schema

JSON Schema có thể cho phép null trong type:

~~~json
{
  "type": ["string", "null"]
}
~~~

Điều này cho phép giá trị string hoặc null. Việc một thuộc tính có bắt buộc xuất hiện hay không được xác định riêng bằng required. Vì thế, cho phép null không đồng nghĩa với bắt buộc hoặc không bắt buộc.

### 14.3 Protobuf và các schema khác

Một số schema hoặc giao thức có quy tắc riêng để biểu diễn presence, optional field và default. Không nên giả định mọi định dạng đều ánh xạ null giống JSON.

Khi DSL sinh hoặc đọc dữ liệu, cần xác định:

- Field presence được giữ lại hay bị mất?
- Default có được áp dụng khi field vắng mặt không?
- Null có được hỗ trợ trực tiếp không?
- Có cần wrapper hoặc oneof để phân biệt các trạng thái không?

## 15. Null safety và thiết kế API

Một DSL an toàn nên làm rõ vị trí có thể xuất hiện null và giúp người dùng xử lý trước khi truy cập.

### 15.1 Ưu tiên non-null mặc định

Một chính sách thường hữu ích là kiểu không nullable theo mặc định; người dùng phải đánh dấu nullable khi thực sự cần.

Ví dụ:

~~~text
name: String
middle_name: String?
~~~

Điều này giúp phần lớn biểu thức không cần kiểm tra null. Tuy nhiên, chính sách này chỉ hiệu quả nếu dữ liệu đầu vào, thư viện và ranh giới tích hợp được kiểm tra đúng.

### 15.2 Không tin dữ liệu bên ngoài

Ngay cả khi DSL khai báo field là String không nullable, JSON hoặc database vẫn có thể cung cấp null. Runtime phải validate dữ liệu tại boundary trước khi tạo object có kiểu.

Không nên dựa vào annotation hoặc type declaration nếu parser dữ liệu không thực hiện kiểm tra tương ứng.

### 15.3 Thiết kế toán tử null-safe có giới hạn

Safe navigation và coalescing có thể làm code ngắn hơn, nhưng quá nhiều toán tử ẩn có thể che giấu dữ liệu thiếu. Với các trường bắt buộc như số tiền hoặc trạng thái đơn hàng, kiểm tra tường minh và diagnostic có thể phù hợp hơn.

### 15.4 Không dùng null làm tín hiệu điều khiển tùy tiện

Tránh API mà null có thể có nhiều ý nghĩa tùy nơi gọi: bỏ qua, xóa, dùng mặc định, không tìm thấy hoặc lỗi. Hãy dùng enum, Option, Result hoặc một command riêng nếu cần phân biệt.

## 16. Null propagation và chuỗi truy cập

Một số DSL chọn lan truyền null qua biểu thức. Ví dụ:

~~~text
customer.address.city
~~~

Nếu customer.address là null, truy cập city có thể:

- Gây lỗi null dereference.
- Trả null.
- Trả một kết quả lỗi có cấu trúc.

Nếu dùng safe navigation:

~~~text
customer.address?.city
~~~

runtime có thể trả null khi address null.

### 16.1 Chuỗi safe navigation

~~~text
customer.address?.city?.name
~~~

Mỗi bước an toàn có thể lan truyền null đến cuối chuỗi. Kiểu kết quả thường là String? nếu name là String.

### 16.2 Null propagation có thể che lỗi

Nếu customer bắt buộc phải tồn tại, trả null khi customer thiếu có thể che giấu lỗi dữ liệu quan trọng. Safe navigation nên được dùng cho thuộc tính thực sự tùy chọn, không phải để bỏ qua mọi kiểm tra.

### 16.3 Optional chaining và phép gọi hàm

Nếu DSL hỗ trợ:

~~~text
customer.address?.normalize()
~~~

cần quy định hàm normalize có được gọi khi address null hay không. Thông thường không gọi và kết quả là null, nhưng kiểu kết quả và hành vi lỗi phải được tài liệu hóa.

## 17. Null và kiểm soát luồng

Null có thể ảnh hưởng đến if, while, filter và các cấu trúc điều khiển khác.

### 17.1 Điều kiện if

Nếu điều kiện có kiểu Boolean? thay vì Boolean, DSL cần quy định:

- Từ chối ở compile time.
- Unknown được xem là false.
- Phát sinh lỗi khi chạy.
- Yêu cầu xử lý cả ba trường hợp.

Một lựa chọn rõ ràng là chỉ cho phép Boolean không nullable trong if:

~~~text
if customer.is_active
  approve()
~~~

Nếu biểu thức trả Boolean?, người viết phải xử lý null trước:

~~~text
if customer.is_active ?? false
  approve()
~~~

### 17.2 Bộ lọc

Nếu predicate trả unknown, bộ lọc cần quyết định có giữ, loại bỏ hay báo lỗi phần tử đó. SQL WHERE loại bỏ cả false và unknown; một DSL khác có thể chọn cách khác.

### 17.3 Pattern matching

Pattern matching có thể xử lý null như một nhánh:

~~~text
match value
  null -> use_default()
  some(item) -> process(item)
~~~

Nếu kiểu là nullable, compiler có thể kiểm tra tính đầy đủ của các nhánh. Nếu chỉ có nhánh some mà thiếu null, có thể báo lỗi exhaustiveness trước khi chạy.

## 18. Null và kiểu dữ liệu tổng hợp

Null có thể ảnh hưởng đến object, record, tuple và kiểu generic.

Ví dụ:

~~~text
Customer {
  id: Integer
  middle_name: String?
  email: String
}
~~~

Ở đây, middle_name có thể null; id và email không thể null theo khai báo. Runtime cần kiểm tra dữ liệu khi tạo Customer.

### 18.1 Generic nullable

Một kiểu collection có thể phân biệt:

~~~text
List<String>
List<String?>
List<String>?
~~~

Ba kiểu này có ý nghĩa khác:

- List<String>: danh sách không null, từng phần tử không null.
- List<String?>: danh sách không null, phần tử có thể null.
- List<String>?: danh sách có thể null, nhưng nếu có thì phần tử không null.

Nếu DSL cho phép kiểu lồng nhau, cần tài liệu hóa rõ dấu hỏi áp dụng cho tầng nào.

### 18.2 Nested nullable

~~~text
List<String?>?
~~~

Danh sách có thể null và các phần tử trong danh sách cũng có thể null. Các phép truy cập, lọc và serialize phải giữ đúng hai tầng trạng thái.

## 19. Null trong nhiều backend

Nếu DSL có nhiều backend, cùng một biểu thức null phải có ý nghĩa nhất quán hoặc phải công bố giới hạn hỗ trợ.

Ví dụ:

~~~text
customer.middle_name is null
~~~

Backend Java có thể tạo kiểm tra reference null. Backend SQL dùng IS NULL. Backend JavaScript có thể cần phân biệt null với undefined.

Các khác biệt cần xem xét:

- Java có null reference; kiểu nguyên thủy không thể chứa null.
- SQL dùng NULL và logic ba giá trị trong phép so sánh.
- JavaScript có cả null và undefined.
- JSON có null và missing property.
- Một số ngôn ngữ dùng Option/Maybe thay cho null trực tiếp.

Backend không nên tự chọn ngữ nghĩa riêng. IR cần biểu diễn null test, missing test hoặc optional access đủ rõ để từng backend tạo hành vi tương đương.

Nếu target không thể phân biệt hai trạng thái mà DSL yêu cầu, backend cần từ chối cấu trúc hoặc nêu rõ giới hạn. Không nên âm thầm gộp trạng thái.

## 20. Kiểm thử giá trị null

Null cần được kiểm thử như một phần của hệ kiểu và runtime.

### 20.1 Kiểm thử kiểu tĩnh

- Gán null cho kiểu nullable có hợp lệ không?
- Gán null cho kiểu không nullable có bị từ chối không?
- Gán T? vào T có yêu cầu kiểm tra không?
- Suy luận kiểu của null có nhất quán không?
- Overload nhận nhiều kiểu nullable có gây mơ hồ không?
- Smart cast có bị vô hiệu khi giá trị có thể thay đổi không?

### 20.2 Kiểm thử toán tử

- So sánh null với null.
- So sánh null với giá trị không null.
- Phép toán số học có lan truyền null không?
- AND/OR/NOT với unknown.
- Coalescing có đánh giá vế phải lazy không?
- Safe navigation có dừng đúng chỗ không?

### 20.3 Kiểm thử cấu trúc dữ liệu

- Field bị thiếu và field null.
- Phần tử null trong list.
- Key không tồn tại và key có value null.
- Object lồng nhau có thuộc tính null.
- Default có được áp dụng đúng không?

### 20.4 Kiểm thử tích hợp

- Đọc SQL NULL vào kiểu DSL.
- Ghi null vào cột nullable và NOT NULL.
- Serialize field null thành JSON.
- Phân biệt field bị bỏ qua và field được gửi null trong API cập nhật.
- Chuyển nullable type qua các backend.

### 20.5 Kiểm thử biên và tính chất

Có thể dùng property-based testing để kiểm tra các tính chất:

- Safe navigation không dereference giá trị null.
- Coalescing trả vế trái khi vế trái có giá trị.
- Coalescing trả vế phải khi vế trái null.
- Null không bị biến thành zero nếu không có quy tắc chuyển đổi.
- Serialization và parse lại giữ đúng presence/null theo hợp đồng.

## 21. Những sai lầm thường gặp

### Coi null giống zero hoặc false

Điều này làm mất sự khác biệt giữa không có dữ liệu và một giá trị hợp lệ.

**Cách khắc phục:** dùng kiểu nullable hoặc trạng thái riêng và định nghĩa phép toán rõ ràng.

### Gộp missing với null

Một cấu hình không cung cấp trường có thể cần dùng default, trong khi null tường minh có thể yêu cầu xóa hoặc tắt giá trị.

**Cách khắc phục:** giữ thông tin presence khi nghiệp vụ cần phân biệt.

### Cho phép null ở mọi kiểu

Nếu mọi biến đều có thể null, người dùng phải kiểm tra ở quá nhiều nơi và lỗi chỉ xuất hiện khi chạy.

**Cách khắc phục:** cân nhắc non-null mặc định, nullable tường minh và validation ở boundary.

### Dùng non-null assertion quá nhiều

Toán tử khẳng định không null có thể biến lỗi kiểu tĩnh thành lỗi runtime.

**Cách khắc phục:** ưu tiên kiểm tra, pattern matching, coalescing hoặc kiểu kết quả có trạng thái.

### Không định nghĩa Boolean unknown

Nếu điều kiện có thể null, câu lệnh if hoặc rule engine có thể xử lý khác nhau.

**Cách khắc phục:** chọn Boolean hai giá trị hoặc logic ba giá trị và quy định cách dùng trong control flow.

### Dùng null cho mọi lỗi

Không tìm thấy, timeout, không có quyền và dữ liệu chưa đến là các trạng thái khác nhau.

**Cách khắc phục:** dùng Result, Error hoặc trạng thái miền có cấu trúc khi cần giải thích nguyên nhân.

### Giả định các backend xử lý null giống nhau

Java, SQL, JavaScript và JSON có khác biệt về null, missing và undefined.

**Cách khắc phục:** định nghĩa semantics ở cấp DSL, giữ presence trong IR và kiểm thử từng target.

## 22. Quy trình thiết kế null cho một DSL

Khi bổ sung null vào hệ kiểu, có thể thực hiện:

1. **Thu thập tình huống miền:** xác định trường nào thật sự có thể không có giá trị.
2. **Phân loại trạng thái:** phân biệt null, missing, empty, unknown và not applicable.
3. **Chọn mô hình kiểu:** nullable type, Option/Maybe hoặc union type.
4. **Quy định cú pháp:** literal null, dấu nullable và cách khai báo presence.
5. **Định nghĩa kiểm tra tĩnh:** gán, gọi hàm, suy luận kiểu và flow narrowing.
6. **Định nghĩa toán tử:** equality, ordering, arithmetic, Boolean logic, coalescing và safe navigation.
7. **Định nghĩa control flow:** cách if, filter, match và rule xử lý unknown.
8. **Định nghĩa boundary:** mapping với JSON, database, API và target khác.
9. **Định nghĩa lỗi:** phân biệt null hợp lệ với dữ liệu thiếu hoặc lỗi hạ tầng.
10. **Viết ví dụ và test:** kiểm tra trường hợp null, missing, biên và nhiều backend.

Không cần hỗ trợ tất cả toán tử null-safe nếu DSL không có nhu cầu. Một mô hình đơn giản, nhất quán và được tài liệu hóa tốt thường dễ dùng hơn nhiều cách xử lý null chồng chéo.

## 23. Ví dụ tổng hợp

Giả sử DSL quản lý thông tin khách hàng:

~~~text
type Customer {
  id: Integer
  name: String
  middle_name: String?
  email: String?
  age: Integer?
}

let customer = load_customer(1001)

if customer is null
  report "Customer not found"
else
  let display_name =
    customer.middle_name
      ?.trim()
      ?? customer.name

  if customer.age is not null
    require customer.age >= 18
~~~

Trong ví dụ:

- customer có thể null nếu không tìm thấy bản ghi.
- middle_name và email là thuộc tính nullable.
- name và id là thuộc tính không nullable theo khai báo.
- Safe navigation ngăn gọi trim khi middle_name null.
- Null coalescing dùng name làm giá trị thay thế.
- age được kiểm tra trước khi so sánh.

Đặc tả cần làm rõ load_customer trả về Customer? hay một Result riêng, trim có thể lỗi hay không, và require thất bại sẽ dừng chương trình hay tạo một diagnostic.

## 24. Câu hỏi tự kiểm tra

1. Null khác zero, false và chuỗi rỗng như thế nào?
2. Phân biệt null với missing trong object cấu hình.
3. Kiểu nullable biểu diễn tập giá trị ra sao?
4. Vì sao literal null có thể không suy luận được kiểu nếu thiếu ngữ cảnh?
5. Flow-sensitive typing giúp xử lý nullable như thế nào?
6. Null coalescing và safe navigation có hành vi gì?
7. Phân biệt logic Boolean hai giá trị với logic ba giá trị.
8. Vì sao SQL dùng IS NULL thay vì = NULL?
9. Phân biệt tham số nullable với tham số tùy chọn có giá trị mặc định.
10. Vì sao List<String?> khác List<String>??
11. Khi serialize JSON, tại sao cần phân biệt field vắng mặt và field null?
12. Những khác biệt nào cần xem xét khi chuyển null qua nhiều backend?

Giá trị null là một phần của hợp đồng kiểu và hành vi DSL. Khi phân biệt rõ null với các trạng thái thiếu thông tin khác, quy định cách kiểm tra và xử lý trong từng biểu thức, đồng thời giữ nguyên ý nghĩa qua các ranh giới dữ liệu, DSL sẽ giảm được lỗi khó dự đoán và giúp người dùng thể hiện ý định chính xác hơn.

# Số lượng phần tử trong mô hình trừu tượng của DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích ý nghĩa của số lượng phần tử (multiplicity hoặc cardinality) trong mô hình trừu tượng của một DSL.
- Đọc và diễn giải cận dưới, cận trên như 0..1, 1, 0..* và 1..*.
- Phân biệt số lượng phần tử của một thuộc tính hoặc quan hệ với số lượng đối tượng của một lớp.
- Xác định khi nào một giá trị là bắt buộc, tùy chọn, đơn lẻ hoặc một tập hợp.
- Phân biệt multiplicity với kiểu dữ liệu, thứ tự và tính duy nhất của phần tử.
- Ánh xạ số lượng phần tử trong mô hình trừu tượng với cú pháp DSL và kiểm tra tính hợp lệ của mô hình.
- Thiết kế các ràng buộc số lượng phù hợp với quy tắc của miền và khả năng mở rộng của ngôn ngữ.

## 1. Số lượng phần tử trong mô hình trừu tượng là gì?

Mô hình trừu tượng (abstract model hoặc abstract syntax model) mô tả những khái niệm mà DSL biểu diễn và quan hệ giữa chúng. Mô hình có thể gồm lớp, kiểu, thuộc tính, tham chiếu và các ràng buộc. Nó tập trung vào ý nghĩa cấu trúc của chương trình DSL, không phụ thuộc hoàn toàn vào cách người dùng viết văn bản, dùng biểu tượng trực quan hay thao tác qua giao diện.

Một câu hỏi quan trọng khi mô hình hóa là: **mỗi đối tượng được phép có bao nhiêu giá trị hoặc liên kết ở một thuộc tính/quan hệ?** Số lượng phần tử (multiplicity) trả lời câu hỏi đó bằng cách quy định số lượng tối thiểu và tối đa.

Ví dụ, trong miền bán hàng:

- Một Đơn hàng phải thuộc về đúng một Khách hàng.
- Một Đơn hàng phải có ít nhất một Dòng đơn hàng.
- Một Đơn hàng có thể chưa có Giao dịch thanh toán hoặc có nhiều giao dịch.
- Một Đơn hàng có thể có hoặc không có ghi chú giao hàng.

Những quy tắc này có thể được mô tả bằng multiplicity:

| Thuộc tính/quan hệ của Đơn hàng | Số lượng | Ý nghĩa |
|---|---:|---|
| customer | 1 | Bắt buộc có đúng một khách hàng |
| lines | 1..* | Phải có ít nhất một dòng hàng |
| payments | 0..* | Có thể không có hoặc có nhiều giao dịch |
| deliveryNote | 0..1 | Có thể không có hoặc có một ghi chú |

Multiplicity giúp mô hình biểu diễn những giới hạn cấu trúc quan trọng ngay tại nơi khai báo thuộc tính hoặc quan hệ. Nhờ đó, công cụ DSL có thể phát hiện một mô hình thiếu thành phần bắt buộc hoặc chứa quá nhiều giá trị.

## 2. Cardinality và multiplicity

Trong mô hình hóa phần mềm, hai thuật ngữ cardinality và multiplicity thường được dùng gần nghĩa nhau để nói về số lượng phần tử. Cách dùng có thể khác nhau giữa công cụ hoặc phương pháp mô hình hóa:

- **Multiplicity** thường nhấn mạnh khoảng số lượng được phép tại một thuộc tính hoặc đầu quan hệ, ví dụ 0..1 hoặc 1..*.
- **Cardinality** thường được dùng để chỉ số lượng phần tử thực tế của một tập hợp hoặc số lượng thể hiện của một quan hệ.

Trong bài học này, multiplicity là quy tắc giới hạn số lượng được mô hình khai báo; cardinality là số phần tử đang có trong một giá trị hoặc liên kết cụ thể. Ví dụ, multiplicity của lines là 1..*, còn cardinality hiện tại của danh sách lines trong một đơn hàng cụ thể có thể là 3.

Phân biệt này giúp tránh nhầm giữa **giới hạn được phép** và **số lượng đang tồn tại**. Một thuộc tính có multiplicity 1..* không có nghĩa mọi đối tượng luôn có cùng số lượng phần tử; nó chỉ yêu cầu mỗi đối tượng hợp lệ có ít nhất một phần tử.

## 3. Cận dưới và cận trên

Multiplicity thường được viết dưới dạng:

~~~text
lowerBound .. upperBound
~~~

Trong đó:

- **Cận dưới (lower bound)** là số phần tử ít nhất phải có.
- **Cận trên (upper bound)** là số phần tử nhiều nhất được phép có.
- Dấu sao (*) thường biểu thị không giới hạn trên.

Ví dụ:

| Multiplicity | Cận dưới | Cận trên | Ý nghĩa |
|---|---:|---:|---|
| 0..1 | 0 | 1 | Không có hoặc có một |
| 1 | 1 | 1 | Chính xác một |
| 0..* | 0 | Không giới hạn | Không có hoặc có nhiều |
| 1..* | 1 | Không giới hạn | Ít nhất một |
| 2..5 | 2 | 5 | Từ hai đến năm |
| 3..3 | 3 | 3 | Chính xác ba |

Một số công cụ cho phép viết 1 thay cho 1..1. Các công cụ khác có thể dùng cú pháp riêng, chẳng hạn dấu ? hoặc dấu * trong khai báo collection. Khi đọc mô hình, cần hiểu ý nghĩa của cận dưới và cận trên thay vì chỉ dựa vào ký hiệu.

### 3.1. Cận dưới bằng 0: phần tử tùy chọn

Nếu cận dưới là 0, đối tượng có thể không có giá trị hoặc liên kết đó.

Ví dụ, một Đơn hàng có thể chưa được gán mã vận đơn:

~~~text
Order
  trackingCode: String [0..1]
~~~

Đơn hàng mới tạo có thể chưa có trackingCode. Khi đơn vị vận chuyển tiếp nhận, trường này có thể được gán một giá trị.

### 3.2. Cận dưới bằng 1: phần tử bắt buộc

Nếu cận dưới là 1, đối tượng hợp lệ phải có ít nhất một giá trị hoặc liên kết.

Ví dụ, một Dòng đơn hàng phải tham chiếu đến đúng một Sản phẩm:

~~~text
OrderLine
  product: Product [1]
~~~

Một dòng hàng không có sản phẩm sẽ không có ý nghĩa trong miền bán hàng, nên multiplicity 1 thể hiện quy tắc bắt buộc.

### 3.3. Cận trên bằng 1: tối đa một phần tử

Cận trên bằng 1 giới hạn số lượng ở mức một. Khi cận dưới là 0, thuộc tính có thể vắng mặt; khi cận dưới là 1, thuộc tính phải có đúng một giá trị.

### 3.4. Cận trên không giới hạn

Khi cận trên là *, mô hình không đặt một giới hạn cố định về số lượng phần tử. Điều đó không có nghĩa hệ thống thực tế có thể lưu vô hạn phần tử. Cơ sở dữ liệu, bộ nhớ, hiệu năng, chính sách và giới hạn vận hành vẫn có thể đặt ngưỡng riêng.

### 3.5. Cận dưới và cận trên phải nhất quán

Một multiplicity hợp lệ phải có cận dưới không âm và cận trên không nhỏ hơn cận dưới. Ví dụ, 3..5 hợp lệ; 5..3 không hợp lệ. Nếu dùng * làm cận trên, nó đại diện cho không giới hạn theo quy ước của mô hình.

## 4. Phân biệt số lượng thuộc tính với số lượng đối tượng

Đây là điểm dễ nhầm khi đọc mô hình lớp hoặc mô hình miền.

Giả sử có lớp Customer và lớp Order. Multiplicity 0..* ở đầu Order của quan hệ Customer–Order thường có nghĩa **mỗi Customer có thể liên kết với không hoặc nhiều Order**. Nó không có nghĩa hệ thống chỉ được tạo tối đa một khách hàng hay tổng số đơn hàng trong hệ thống bị giới hạn.

Cần đọc multiplicity tại từng đầu quan hệ theo đối tượng ở đầu đối diện:

~~~text
Customer  1  <--------  0..*  Order
~~~

Có thể diễn giải:

- Mỗi Order gắn với đúng một Customer.
- Mỗi Customer có thể có không hoặc nhiều Order.

Multiplicity mô tả số liên kết được phép từ một đối tượng trong ngữ cảnh quan hệ. Nó không trực tiếp mô tả tổng số thể hiện của lớp trong toàn hệ thống.

### 4.1. Multiplicity của thuộc tính

Một thuộc tính có thể lưu một giá trị hoặc nhiều giá trị:

~~~text
Customer
  name: String [1]
  email: String [0..1]
  phoneNumbers: String [0..*]
~~~

Trong ví dụ này, name bắt buộc có đúng một giá trị; email có thể không có hoặc có một giá trị; phoneNumbers là một tập hợp có thể rỗng hoặc có nhiều số điện thoại.

### 4.2. Multiplicity của quan hệ

Một quan hệ mô tả liên kết giữa các đối tượng:

~~~text
Order
  customer: Customer [1]
  lines: OrderLine [1..*]
  payments: Payment [0..*]
~~~

Ở đây, customer, lines và payments là các tham chiếu tới đối tượng khác. Số lượng cho biết một Order có thể hoặc phải liên kết với bao nhiêu đối tượng ở mỗi vai trò.

## 5. Các dạng multiplicity thường gặp trong mô hình DSL

### 5.1. Một-một (one-to-one)

Một đối tượng ở phía này liên kết với tối đa một đối tượng ở phía kia và ngược lại, theo giới hạn đã chọn.

Ví dụ, trong một hệ thống giả định, mỗi Hồ sơ cá nhân có đúng một Tài khoản đăng nhập và mỗi Tài khoản đăng nhập thuộc đúng một Hồ sơ cá nhân:

~~~text
Profile.account: Account [1]
Account.profile: Profile [1]
~~~

Quan hệ một-một cần được xác định rõ cả hai đầu. Nếu một đầu là 0..1, đối tượng tương ứng có thể tồn tại mà chưa có liên kết.

### 5.2. Một-nhiều (one-to-many)

Một đối tượng có thể liên kết với nhiều đối tượng khác, trong khi mỗi đối tượng ở phía nhiều chỉ thuộc về một đối tượng ở phía một.

Ví dụ:

~~~text
Customer.orders: Order [0..*]
Order.customer: Customer [1]
~~~

Một khách hàng có thể chưa có đơn hàng hoặc có nhiều đơn hàng; mỗi đơn hàng thuộc về đúng một khách hàng.

### 5.3. Nhiều-nhiều (many-to-many)

Một đối tượng ở mỗi phía có thể liên kết với nhiều đối tượng ở phía còn lại.

Ví dụ, một Sinh viên có thể đăng ký nhiều Khóa học và một Khóa học có thể có nhiều Sinh viên:

~~~text
Student.courses: Course [0..*]
Course.students: Student [0..*]
~~~

Nếu quan hệ có dữ liệu riêng như ngày đăng ký, điểm số hoặc trạng thái, nên mô hình hóa nó thành một lớp liên kết, chẳng hạn Enrollment:

~~~text
Student.enrollments: Enrollment [0..*]
Course.enrollments: Enrollment [0..*]
Enrollment.student: Student [1]
Enrollment.course: Course [1]
Enrollment.registeredAt: DateTime [1]
~~~

Cách này giúp biểu diễn thuộc tính và vòng đời của chính quan hệ đăng ký.

## 6. Số lượng phần tử và kiểu dữ liệu

Kiểu dữ liệu và multiplicity là hai khía cạnh khác nhau:

- **Kiểu dữ liệu** cho biết một giá trị thuộc loại nào, ví dụ String, Integer, Date hoặc Customer.
- **Multiplicity** cho biết có bao nhiêu giá trị thuộc loại đó được phép hoặc bắt buộc xuất hiện.

Ví dụ:

~~~text
email: String [0..1]
tags: String [0..*]
quantity: Integer [1]
~~~

email có kiểu String và tối đa một giá trị; tags có nhiều giá trị String; quantity có đúng một giá trị Integer.

Không nên nhầm một thuộc tính có kiểu collection với multiplicity của thuộc tính. Ví dụ, khai báo tags: List<String> đã nói kiểu của giá trị là danh sách chuỗi, nhưng vẫn cần xác định danh sách có được rỗng không, có giới hạn số phần tử không và có cho phép trùng lặp không.

### 6.1. Optional không đồng nghĩa với collection rỗng

Hai trường hợp sau có thể khác nhau:

- Một thuộc tính tùy chọn không có giá trị.
- Một thuộc tính collection tồn tại nhưng không có phần tử.

Ví dụ:

~~~text
middleName: String [0..1]
phoneNumbers: String [0..*]
~~~

middleName có thể vắng mặt; phoneNumbers có thể là collection rỗng. Trong triển khai, trạng thái vắng mặt có thể được biểu diễn bằng null, Optional, trường không có trong JSON hoặc một cơ chế khác. Collection rỗng thường được biểu diễn bằng danh sách hoặc tập hợp có kích thước 0.

Không nên gộp hai trạng thái này nếu miền cần phân biệt “chưa cung cấp” với “đã cung cấp danh sách nhưng hiện không có phần tử”.

### 6.2. Optional và giá trị null

Multiplicity 0..1 không bắt buộc phải được triển khai bằng null. Nó chỉ quy định rằng có thể không có giá trị. Một hệ thống kiểu có thể biểu diễn bằng Optional<T>, kiểu nullable hoặc một cấu trúc khác.

Nếu dùng null, cần xác định null có nghĩa là chưa biết, chưa cung cấp, không áp dụng hay bị xóa. Những ý nghĩa này không phải lúc nào cũng giống nhau.

### 6.3. Kiểu collection và multiplicity

Một số kiểu collection thường gặp:

| Kiểu collection | Cho phép trùng lặp? | Có giữ thứ tự? | Ví dụ sử dụng |
|---|---|---|---|
| Set | Không | Thường không | Tập quyền truy cập |
| Bag / Multiset | Có | Không nhất thiết | Các mặt hàng có thể lặp |
| Sequence / List | Có | Có | Các bước trong quy trình |
| Ordered Set | Không | Có | Danh sách mã duy nhất theo thứ tự |

Multiplicity cho biết số lượng phần tử, còn kiểu collection xác định thêm cách tổ chức và quy tắc phần tử.

## 7. Thứ tự và tính duy nhất không phải multiplicity

Một mô hình có multiplicity 1..* vẫn chưa cho biết các phần tử có được trùng lặp hay không hoặc thứ tự có quan trọng hay không.

### 7.1. Tính duy nhất (unique)

Nếu một collection là unique, cùng một phần tử không được xuất hiện nhiều lần theo định nghĩa so sánh của mô hình. Nếu không unique, phần tử có thể lặp.

Ví dụ:

- roles có thể là tập hợp unique vì một người không cần có cùng một vai trò lặp nhiều lần.
- orderLines có thể cho phép hai dòng cùng tham chiếu một sản phẩm nhưng có thể khác giá, khuyến mại hoặc ghi chú.

Cần xác định “trùng” nghĩa là cùng định danh đối tượng, cùng giá trị hay cùng toàn bộ nội dung. Với đối tượng có định danh, hai đối tượng khác nhau có thể có các thuộc tính giống hệt nhau mà vẫn không phải cùng một phần tử.

### 7.2. Thứ tự (ordered)

Nếu collection là ordered, vị trí phần tử có ý nghĩa. Ví dụ, các bước trong quy trình phê duyệt phải giữ thứ tự thực hiện. Nếu collection không ordered, công cụ không nên giả định phần tử đầu tiên hay phần tử cuối cùng có ý nghĩa đặc biệt.

### 7.3. Kết hợp multiplicity, ordered và unique

Một mô hình có thể mô tả các thuộc tính độc lập:

~~~text
approvalSteps: ApprovalStep [1..*]
  ordered = true
  unique = true

requiredPermissions: Permission [1..*]
  ordered = false
  unique = true

lineItems: Product [0..*]
  ordered = true
  unique = false
~~~

Các tên thuộc tính trên chỉ là ký hiệu minh họa. Ngôn ngữ mô hình hoặc công cụ DSL thực tế có thể biểu diễn ordered và unique bằng cách khác.

## 8. Biểu diễn multiplicity trong mô hình trừu tượng

Mô hình trừu tượng có thể được biểu diễn bằng class diagram, metamodel, cấu trúc dữ liệu hoặc mô hình đối tượng. Một khai báo thuộc tính thường gồm tên, kiểu và giới hạn số lượng.

Ví dụ mô hình miền:

~~~text
class Order {
    id: OrderId [1]
    customer: Customer [1]
    lines: OrderLine [1..*]
    payments: Payment [0..*]
    note: String [0..1]
}

class OrderLine {
    product: Product [1]
    quantity: PositiveInteger [1]
    unitPrice: Money [1]
}
~~~

Mô hình này cho biết:

- Mỗi Order có đúng một id và một customer.
- Mỗi Order có ít nhất một OrderLine.
- Mỗi Order có thể có không hoặc nhiều Payment.
- note có thể vắng mặt.
- Mỗi OrderLine phải tham chiếu một Product, có quantity và unitPrice.

### 8.1. Multiplicity trong mô hình lớp

Trong UML, multiplicity thường được ghi ở đầu thuộc tính hoặc đầu quan hệ, chẳng hạn 1, 0..1, 0..* và 1..*. Với quan hệ hai lớp, phải đọc multiplicity tại đúng đầu liên kết.

Ví dụ:

~~~text
Customer "1" -------- "0..*" Order
~~~

Có thể đọc từ phía Order: mỗi Order gắn với đúng một Customer. Đọc từ phía Customer: mỗi Customer liên kết với không hoặc nhiều Order.

### 8.2. Multiplicity trong metamodel

Metamodel mô tả cấu trúc của các mô hình được tạo ra bằng DSL. Ví dụ, metamodel của DSL quy tắc có thể có các lớp Rule, Condition và Action:

~~~text
Rule
  name: Identifier [1]
  conditions: Condition [1..*]
  actions: Action [1..*]
  description: String [0..1]
~~~

Mỗi Rule phải có tên, ít nhất một điều kiện và ít nhất một hành động; mô tả là tùy chọn. Khi người dùng viết một rule không có action, mô hình được tạo ra vi phạm multiplicity và cần bị từ chối hoặc yêu cầu bổ sung.

### 8.3. Containment và tham chiếu

Một metamodel có thể phân biệt quan hệ chứa (containment) với tham chiếu thông thường:

- Quan hệ chứa thể hiện một đối tượng con thuộc cấu trúc sở hữu của đối tượng cha.
- Tham chiếu thông thường liên kết đến đối tượng khác mà không nhất thiết sở hữu vòng đời của nó.

Ví dụ, Rule có thể chứa các Condition và Action. Nhưng Rule có thể tham chiếu đến một kiểu miền hoặc một schema dùng chung mà không sở hữu chúng.

Multiplicity vẫn cần được khai báo cho cả quan hệ chứa và tham chiếu. Việc một quan hệ là containment không tự quyết định số lượng phần tử.

## 9. Ánh xạ multiplicity từ cú pháp DSL sang mô hình

Cú pháp cụ thể (concrete syntax) là cách người dùng viết hoặc thao tác với DSL. Mô hình trừu tượng lưu cấu trúc và ý nghĩa sau khi phân tích. Hai phần cần thống nhất về số lượng phần tử.

Giả sử DSL có cú pháp:

~~~text
rule "free_shipping" {
    when order.total >= 500000
    then order.shipping_fee = 0
}
~~~

Mô hình trừu tượng có thể là:

~~~text
Rule
  name: String [1]
  condition: Expression [1]
  action: Action [1]
~~~

Ở đây, grammar yêu cầu đúng một tên, một điều kiện và một hành động; metamodel cũng yêu cầu multiplicity 1 cho ba thuộc tính tương ứng.

Nếu DSL cho phép nhiều điều kiện:

~~~text
rule "priority_shipping" {
    when order.total >= 500000
    and customer.level == "gold"
    and order.destination == "domestic"
    then order.shipping_fee = 0
}
~~~

Metamodel có thể dùng:

~~~text
Rule
  conditions: Expression [1..*]
  action: Action [1]
~~~

Một luật phải có ít nhất một điều kiện, có thể có nhiều điều kiện và chỉ có một hành động chính.

### 9.1. Grammar lặp và multiplicity

Nếu grammar cho phép một hoặc nhiều phần tử:

~~~text
conditionList ::= condition { "and" condition }
~~~

thì multiplicity tương ứng thường là 1..*. Nếu grammar cho phép không hoặc nhiều:

~~~text
conditionList ::= { condition }
~~~

thì multiplicity thường là 0..*.

Ký hiệu cụ thể phụ thuộc biến thể EBNF, nhưng nguyên tắc là số lần xuất hiện trong grammar cần phù hợp với giới hạn của mô hình.

### 9.2. Không đồng nhất cú pháp với mô hình

Một cú pháp có thể dùng dấu ngoặc hoặc dấu phẩy để biểu diễn collection, trong khi mô hình chỉ lưu danh sách các đối tượng. Ngược lại, mô hình có thể có thuộc tính được hệ thống tự sinh hoặc mặc định mà người dùng không cần viết trực tiếp.

Ví dụ, nếu mỗi Rule tự có ID do công cụ cấp, metamodel có thể quy định id [1] dù cú pháp nguồn không có trường id. Đây là giá trị do hệ thống tạo, không phải thành phần bị thiếu trong DSL source.

### 9.3. Khi grammar và metamodel không khớp

Có hai dạng sai lệch thường gặp:

- Grammar cho phép danh sách rỗng nhưng metamodel yêu cầu ít nhất một phần tử.
- Grammar yêu cầu một thành phần nhưng metamodel lại cho phép vắng mặt.

Sai lệch có thể làm parser tạo ra mô hình không hợp lệ hoặc khiến người dùng viết cú pháp được parser chấp nhận nhưng bị validator từ chối. Cần quyết định rõ lớp nào chịu trách nhiệm kiểm tra và thông báo lỗi nên xuất hiện ở đâu.

## 10. Kiểm tra multiplicity và tính hợp lệ của mô hình

Sau khi parser tạo mô hình trừu tượng, validator có thể kiểm tra số lượng phần tử.

Với một thuộc tính có cận dưới L và cận trên U, số lượng hiện tại n hợp lệ khi:

~~~text
L <= n <= U
~~~

Nếu U là *, chỉ cần kiểm tra n >= L.

Ví dụ:

| Thuộc tính | Multiplicity | Số phần tử hiện có | Kết quả |
|---|---:|---:|---|
| Rule.name | 1 | 1 | Hợp lệ |
| Rule.conditions | 1..* | 0 | Không hợp lệ |
| Rule.actions | 1..* | 2 | Hợp lệ |
| Order.payments | 0..* | 0 | Hợp lệ |
| Order.note | 0..1 | 2 | Không hợp lệ |

### 10.1. Kiểm tra khi phân tích hay khi xác thực mô hình?

Một số ràng buộc số lượng có thể được grammar bảo đảm. Ví dụ, grammar yêu cầu một biểu thức sau dấu bằng thì parser không thể tạo phép gán thiếu biểu thức.

Những ràng buộc khác phù hợp hơn với validator trên mô hình, đặc biệt khi:

- Mô hình được tạo từ nhiều nguồn.
- Thành phần được bổ sung qua API hoặc giao diện trực quan.
- Số lượng phụ thuộc vào cấu hình hoặc schema.
- Cần báo lỗi theo khái niệm mô hình thay vì theo ký tự nguồn.

Có thể kiểm tra multiplicity ở nhiều lớp để bảo vệ các ranh giới khác nhau, nhưng không nên đưa ra thông báo mâu thuẫn.

### 10.2. Thời điểm kiểm tra

Multiplicity có thể được kiểm tra:

- Khi người dùng đang soạn DSL để phản hồi sớm.
- Sau khi parse để xác nhận AST/metamodel.
- Khi lưu mô hình vào kho dữ liệu.
- Trước khi thực thi hoặc sinh mã.
- Khi dữ liệu runtime được nạp hoặc thay đổi.

Với quy tắc cấu trúc tĩnh, kiểm tra càng sớm càng giúp người dùng sửa lỗi thuận tiện. Với dữ liệu động, vẫn cần kiểm tra lại tại thời điểm sử dụng.

### 10.3. Thông báo lỗi nên nêu giới hạn

Thông báo tốt cho biết thuộc tính nào vi phạm, số lượng mong đợi và số lượng thực tế.

Ví dụ:

~~~text
Rule "free_shipping" không hợp lệ:
  conditions yêu cầu ít nhất 1 phần tử nhưng hiện có 0.
  Hãy thêm một điều kiện sau từ khóa when.
~~~

Hoặc:

~~~text
Order "ORD-204" chỉ được có tối đa 1 deliveryNote,
nhưng mô hình hiện có 2 giá trị.
~~~

Thông báo theo miền giúp người viết hiểu điều gì cần sửa thay vì chỉ thấy một lỗi kiểu dữ liệu chung.

## 11. Ràng buộc số lượng phức tạp hơn

Multiplicity cơ bản chỉ giới hạn số lượng của một thuộc tính hoặc quan hệ. Nhiều quy tắc miền cần phối hợp nhiều thuộc tính hoặc phụ thuộc vào điều kiện.

### 11.1. Ràng buộc chính xác một trong nhiều lựa chọn

Giả sử một phương thức giao hàng cần có đúng một trong hai thông tin: địa chỉ giao tận nơi hoặc điểm nhận hàng.

Hai thuộc tính riêng có thể có multiplicity 0..1:

~~~text
Delivery
  address: Address [0..1]
  pickupPoint: PickupPoint [0..1]
~~~

Nhưng chỉ hai multiplicity này chưa bảo đảm có đúng một giá trị. Chúng cho phép cả hai cùng vắng mặt hoặc cả hai cùng xuất hiện.

Cần thêm ràng buộc:

~~~text
exactlyOne(address, pickupPoint)
~~~

Ràng buộc này là minh họa cho một quy tắc ngữ nghĩa bổ sung. Công cụ thực tế có thể dùng OCL, constraint language hoặc mã validator.

### 11.2. Ràng buộc phụ thuộc điều kiện

Ví dụ, nếu đơn hàng có trạng thái SHIPPED thì phải có ít nhất một mã vận đơn:

~~~text
if order.status == SHIPPED
then order.trackingCodes.size >= 1
~~~

Multiplicity của trackingCodes có thể là 0..* vì trước khi giao hàng danh sách có thể rỗng. Quy tắc điều kiện mới bắt buộc có phần tử khi trạng thái thay đổi.

### 11.3. Ràng buộc tổng số lượng

Một đơn hàng có thể giới hạn tối đa 100 dòng hàng:

~~~text
order.lines.size <= 100
~~~

Đây có thể được biểu diễn trực tiếp bằng multiplicity 1..100 nếu giới hạn luôn áp dụng. Nếu giới hạn thay đổi theo loại khách hàng hoặc chính sách, cần validator phụ thuộc ngữ cảnh.

### 11.4. Ràng buộc giữa các đầu quan hệ

Trong quan hệ hai chiều, số lượng liên kết phải nhất quán. Nếu Order.customer trỏ tới Customer A thì Customer A.orders phải phản ánh Order đó nếu mô hình duy trì cả hai đầu tham chiếu.

Một mô hình cần quy định một đầu là nguồn chuẩn hay cả hai đầu đều được cập nhật đồng bộ. Nếu không, có thể xuất hiện quan hệ không nhất quán.

### 11.5. Multiplicity và khóa duy nhất

Multiplicity 1..* không bảo đảm các phần tử khác nhau. Nếu một danh sách cần không trùng lặp, cần thêm quy tắc unique. Nếu mỗi phần tử phải có mã duy nhất, cần ràng buộc uniqueness trên thuộc tính định danh.

Ví dụ, một Rule có thể có 1..* conditions và yêu cầu mỗi condition có ID riêng. Số lượng và tính duy nhất là hai ràng buộc độc lập.

## 12. Cách triển khai multiplicity trong công cụ DSL

### 12.1. Lưu cận dưới và cận trên trong metamodel

Một công cụ có thể biểu diễn multiplicity như hai số nguyên:

~~~text
Multiplicity {
    lowerBound: Integer
    upperBound: Optional<Integer>
}
~~~

Giá trị upperBound vắng mặt có thể biểu thị không giới hạn. Một số framework dùng giá trị đặc biệt như -1 cho cận trên không giới hạn; cần theo đúng quy ước của framework.

Ví dụ:

~~~text
Multiplicity(0, 1)
Multiplicity(1, 1)
Multiplicity(0, unbounded)
Multiplicity(1, unbounded)
~~~

### 12.2. Hàm kiểm tra số lượng

Mã giả:

~~~text
function validateMultiplicity(values, lower, upper):
    count = size(values)

    if count < lower:
        return error("Too few elements")

    if upper is bounded and count > upper:
        return error("Too many elements")

    return success
~~~

Với thuộc tính đơn, có thể quy đổi số lượng thành 0 hoặc 1 tùy việc giá trị có tồn tại hay không. Với collection, dùng kích thước hiện tại.

### 12.3. Kiểm tra đầu vào trước khi tạo mô hình

Một parser có thể phát hiện thiếu thành phần bắt buộc ngay trong cú pháp. Nhưng nếu mô hình được tạo bằng API, validator cần kiểm tra lại trước khi lưu hoặc thực thi.

Không nên chỉ dựa vào giao diện người dùng để bảo đảm multiplicity. API, importer, plugin hoặc mã sinh tự động cũng có thể tạo mô hình; tất cả các đường vào cần tuân theo cùng một quy tắc.

### 12.4. Hỗ trợ sinh biểu mẫu và editor

Multiplicity có thể giúp công cụ tự sinh giao diện:

- 1: hiển thị trường bắt buộc đơn.
- 0..1: hiển thị trường đơn không bắt buộc.
- 0..*: cho phép danh sách rỗng và thêm nhiều phần tử.
- 1..*: yêu cầu ít nhất một mục.
- 2..5: giới hạn số mục có thể thêm.

Editor có thể dùng cận dưới để cảnh báo khi còn thiếu phần tử và cận trên để vô hiệu hóa nút thêm. Tuy nhiên, giao diện chỉ hỗ trợ trải nghiệm; validator phía mô hình vẫn phải thực thi quy tắc.

## 13. Ví dụ tổng hợp: mô hình DSL cho quy trình phê duyệt

Giả sử DSL mô tả quy trình phê duyệt yêu cầu mua hàng. Mô hình trừu tượng gồm Process, Step, Approver và Condition.

~~~text
Process
  name: Identifier [1]
  steps: Step [1..*]
  description: String [0..1]

Step
  name: Identifier [1]
  approvers: Approver [1..*]
  conditions: Condition [0..*]
  timeout: Duration [0..1]

Approver
  role: Role [1]

Condition
  expression: BooleanExpression [1]
~~~

Diễn giải:

- Mỗi Process có đúng một tên.
- Mỗi Process phải có ít nhất một Step.
- Description có thể không có.
- Mỗi Step phải có ít nhất một Approver.
- Một Step có thể không có điều kiện bổ sung hoặc có nhiều Condition.
- Timeout là tùy chọn.
- Mỗi Condition phải chứa đúng một biểu thức điều kiện.

### 13.1. Cú pháp DSL minh họa

~~~text
process "purchase_approval" {
    step "manager_review" {
        approvers: [role("manager")]
        conditions: [
            request.amount > 10000000,
            request.category == "equipment"
        ]
        timeout: 2 days
    }
}
~~~

Parser có thể tạo một Process với một Step. Step có một Approver, hai Condition và một Timeout.

### 13.2. Các mô hình không hợp lệ

| Trường hợp | Quy tắc bị vi phạm |
|---|---|
| Process không có Step | steps yêu cầu 1..* |
| Step không có Approver | approvers yêu cầu 1..* |
| Step có hai giá trị timeout | timeout chỉ cho phép 0..1 |
| Condition không có expression | expression yêu cầu 1 |
| Process có hai tên | name chỉ cho phép 1 |

### 13.3. Những quy tắc multiplicity chưa đủ

Mô hình vẫn có thể thỏa multiplicity nhưng sai nghiệp vụ:

- Hai Step có cùng tên nếu tên phải duy nhất trong Process.
- Một Approver tham chiếu đến Role không tồn tại.
- Hai Condition mâu thuẫn nhau.
- Timeout âm.
- Một quy trình không có đường đi đến trạng thái kết thúc.

Những trường hợp này cần các ràng buộc ngữ nghĩa bổ sung. Multiplicity là một phần của tính hợp lệ cấu trúc, không phải toàn bộ định nghĩa về một mô hình hợp lệ.

## 14. Những lỗi thiết kế thường gặp

### 14.1. Dùng 0..* cho mọi thuộc tính collection

Đây là cách khai báo dễ viết nhưng có thể làm mô hình cho phép trạng thái vô nghĩa. Nếu một Rule bắt buộc phải có hành động, actions nên là 1..* thay vì 0..*.

### 14.2. Dùng 1 khi thực tế cần tùy chọn

Nếu trường chưa có ở giai đoạn đầu của vòng đời đối tượng, multiplicity 1 có thể khiến việc tạo đối tượng trở nên bất khả thi hoặc buộc phải dùng giá trị giả. Hãy mô hình hóa đúng thời điểm và trạng thái.

### 14.3. Nhầm 0..1 với 0..*

0..1 cho phép không hoặc một giá trị; 0..* cho phép không hoặc nhiều. Hai quy tắc tạo ra hành vi editor, API và validator khác nhau.

### 14.4. Cho phép danh sách rỗng nhưng nghiệp vụ yêu cầu phần tử

Một collection rỗng có thể hợp lệ về cấu trúc dữ liệu nhưng không hợp lệ trong miền. Hãy chọn cận dưới theo quy tắc thực tế.

### 14.5. Nghĩ multiplicity bảo đảm duy nhất

1..* chỉ bảo đảm có ít nhất một phần tử. Nó không ngăn các phần tử trùng lặp. Cần ràng buộc unique hoặc dùng kiểu collection phù hợp.

### 14.6. Nghĩ multiplicity quyết định thứ tự

0..* không nói phần tử nào đứng trước. Nếu thứ tự ảnh hưởng đến ý nghĩa, cần mô hình hóa ordered hoặc dùng sequence.

### 14.7. Mô hình và grammar không nhất quán

Nếu grammar cho phép không có điều kiện nhưng metamodel yêu cầu ít nhất một điều kiện, người dùng có thể viết cú pháp được parser chấp nhận nhưng bị validator từ chối. Hãy đồng bộ các giới hạn hoặc giải thích rõ giai đoạn kiểm tra.

### 14.8. Bỏ qua dữ liệu được tạo từ API hoặc import

Một mô hình có thể được tạo mà không qua parser DSL. Nếu chỉ kiểm tra multiplicity trong grammar, các đường tạo mô hình khác có thể đưa dữ liệu sai vào hệ thống. Validator cần được dùng tại ranh giới thích hợp.

## 15. Hướng dẫn chọn multiplicity

Khi thiết kế thuộc tính hoặc quan hệ, hãy lần lượt hỏi:

1. Một đối tượng hợp lệ có thể không có giá trị này không?
2. Nếu có, số lượng tối thiểu là bao nhiêu?
3. Có giới hạn tối đa cố định không?
4. Giá trị là một thuộc tính đơn hay một collection?
5. Collection có cho phép trùng lặp không?
6. Thứ tự phần tử có mang ý nghĩa không?
7. Số lượng có phụ thuộc trạng thái hoặc loại đối tượng không?
8. Có cần thêm ràng buộc liên thuộc tính hoặc uniqueness không?
9. Grammar DSL có cho phép đúng số lượng mà metamodel yêu cầu không?
10. Validator sẽ báo lỗi ở thời điểm nào và chỉ ra vị trí nào?

Một số gợi ý:

| Nhu cầu miền | Multiplicity thường phù hợp |
|---|---:|
| Mỗi đơn hàng phải có một khách hàng | 1 |
| Mỗi đơn hàng có ít nhất một dòng hàng | 1..* |
| Khách hàng có thể chưa đặt đơn | 0..* |
| Mã vận đơn chỉ có sau khi giao hàng | 0..1, kèm ràng buộc trạng thái |
| Một quy trình cần từ hai đến năm người phê duyệt | 2..5 |
| Một cấu hình có thể không có mô tả | 0..1 |
| Một biểu thức có thể có nhiều đối số, kể cả không có | 0..* |

Đây là gợi ý theo tình huống, không phải quy tắc cố định cho mọi miền. Hãy xác nhận với chuyên gia miền và các trường hợp thực tế trước khi chốt multiplicity.

## 16. Thay đổi multiplicity và tương thích mô hình

Multiplicity là một phần của hợp đồng cấu trúc. Thay đổi nó có thể ảnh hưởng đến dữ liệu, cú pháp, API, công cụ editor và chương trình DSL đã tồn tại.

### 16.1. Nới lỏng cận dưới

Đổi 1 thành 0..1 cho phép mô hình thiếu giá trị trước đây bắt buộc. Đây thường là thay đổi nới lỏng về cấu trúc, nhưng ứng dụng tiêu thụ có thể đang giả định giá trị luôn tồn tại và cần xử lý trường hợp vắng mặt.

### 16.2. Siết chặt cận dưới

Đổi 0..1 thành 1 hoặc 0..* thành 1..* làm một số mô hình cũ trở nên không hợp lệ. Cần xác định cách bổ sung dữ liệu, giá trị mặc định hoặc quy trình di chuyển.

### 16.3. Nới lỏng cận trên

Đổi 0..1 thành 0..* cho phép nhiều phần tử hơn. API có thể cần chuyển từ giá trị đơn sang collection; grammar có thể cần hỗ trợ danh sách.

### 16.4. Siết chặt cận trên

Đổi 0..* thành 0..1 hoặc 1..* thành 1 có thể làm dữ liệu cũ chứa nhiều phần tử không còn hợp lệ. Cần quy tắc chọn phần tử, gộp dữ liệu hoặc báo lỗi.

### 16.5. Quy trình thay đổi an toàn

- Xác định mô hình và tài liệu đang sử dụng thuộc tính.
- Tìm các DSL source có số lượng phần tử không còn hợp lệ.
- Đánh giá ảnh hưởng đến AST, API, schema và editor.
- Thiết kế bước chuyển đổi dữ liệu nếu cần.
- Cập nhật grammar, validator và ví dụ.
- Ghi phiên bản mô hình và hướng dẫn di chuyển.

Không nên thay đổi multiplicity chỉ để làm parser dễ viết hơn nếu điều đó làm sai quy tắc miền.

## 17. Bài tập tự kiểm tra

### Bài 1: Đọc multiplicity

Một mô hình có:

~~~text
Course
  title: String [1]
  assistants: Person [0..*]
  mainTeacher: Person [1]
  room: Room [0..1]
  lessons: Lesson [1..*]
~~~

Hãy giải thích số lượng hợp lệ của từng thuộc tính. Nêu một ví dụ mô hình hợp lệ và một ví dụ không hợp lệ.

### Bài 2: Phân biệt số lượng và số đối tượng

Một Customer có multiplicity 0..* ở đầu quan hệ Order. Giải thích quy tắc này áp dụng cho mỗi Customer hay tổng số Order trong toàn hệ thống.

### Bài 3: Chọn multiplicity cho quy trình

Một quy trình phê duyệt có tên bắt buộc, mô tả tùy chọn, ít nhất một bước và mỗi bước có thể có nhiều người phê duyệt. Hãy đề xuất multiplicity cho từng thuộc tính và giải thích.

### Bài 4: Phân biệt optional và collection rỗng

So sánh middleName: String [0..1] với phoneNumbers: String [0..*]. Giải thích khi nào hai trạng thái vắng mặt và rỗng cần được phân biệt trong miền.

### Bài 5: Kết hợp multiplicity và unique

Một danh sách roles có multiplicity 1..*. Hãy giải thích vì sao vẫn có thể xuất hiện cùng một vai trò nhiều lần và đề xuất thêm ràng buộc để ngăn điều đó.

### Bài 6: Tìm ràng buộc còn thiếu

Một Delivery có address [0..1] và pickupPoint [0..1]. Nghiệp vụ yêu cầu phải chọn đúng một trong hai. Hãy nêu các trạng thái mà multiplicity hiện tại cho phép và đề xuất ràng buộc bổ sung.

### Bài 7: Ánh xạ grammar sang metamodel

Grammar có:

~~~text
argumentList ::= expression { "," expression }
~~~

Hãy xác định multiplicity tương ứng của arguments trong metamodel. Nếu đổi thành:

~~~text
argumentList ::= [ expression { "," expression } ]
~~~

thì giới hạn số lượng thay đổi ra sao?

### Bài 8: Đánh giá thay đổi mô hình

Một thuộc tính approvers được đổi từ 1..* thành 0..*. Hãy phân tích ảnh hưởng tới tính hợp lệ của mô hình, giao diện chỉnh sửa, validator và các chương trình DSL hiện có.

## Kết luận

Số lượng phần tử (multiplicity) xác định số giá trị hoặc liên kết tối thiểu và tối đa mà một thuộc tính hay quan hệ trong mô hình trừu tượng được phép có. Cận dưới và cận trên giúp biểu diễn phần tử bắt buộc, tùy chọn, đơn lẻ và collection. Multiplicity cần được phân biệt với kiểu dữ liệu, số lượng đối tượng toàn hệ thống, thứ tự và tính duy nhất. Khi thiết kế DSL, grammar cụ thể và metamodel cần nhất quán về số lần xuất hiện; validator cần kiểm tra các giới hạn cấu trúc cùng những ràng buộc miền phức tạp hơn. Thay đổi multiplicity cũng cần được xem như thay đổi hợp đồng mô hình vì nó có thể ảnh hưởng dữ liệu, API, cú pháp và các chương trình DSL đã tồn tại.

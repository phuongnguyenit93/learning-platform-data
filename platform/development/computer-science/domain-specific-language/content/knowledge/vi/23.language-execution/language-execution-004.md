# Hàm và phép toán trong DSL

Ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường cho phép người dùng mô tả điều kiện, tính toán, chuyển đổi dữ liệu và hành động bằng những biểu thức gần với khái niệm của miền. Khi chương trình DSL được thực thi, runtime phải xác định cách gọi hàm, truyền đối số, tính giá trị trả về và áp dụng toán tử.

**Hàm** (*function*) đóng gói một thao tác có thể gọi lại. Hàm có thể nhận dữ liệu đầu vào, thực hiện một phép tính hoặc hành động, rồi trả về kết quả. **Phép toán** (*operation*) là thao tác được biểu diễn bằng toán tử hoặc cú pháp chuyên biệt, chẳng hạn cộng, so sánh, truy cập thuộc tính, kết hợp logic hoặc kiểm tra sự hiện diện của giá trị.

Hàm và phép toán là nền tảng của quá trình thực thi DSL. Ngôn ngữ cần quy định chữ ký hàm, cách liên kết đối số với tham số, thứ tự đánh giá biểu thức, độ ưu tiên toán tử, quy tắc chuyển kiểu, hành vi khi có lỗi và những tác dụng phụ được phép. Nếu các quy tắc này không rõ, cùng một chương trình có thể cho kết quả khác nhau giữa interpreter, backend hoặc môi trường chạy.

## 1. Hàm trong DSL

### 1.1. Hàm là gì?

Hàm là một thành phần có tên hoặc có thể tham chiếu, nhận không hoặc nhiều giá trị đầu vào và có thể tạo ra một kết quả. Ví dụ:

~~~text
function calculateTax(amount: Money, rate: Decimal): Money {
    return amount * rate
}
~~~

Hàm calculateTax nhận một số tiền và một tỷ lệ, sau đó trả về số tiền thuế. Khi thực thi lời gọi:

~~~text
calculateTax(order.total, 0.08)
~~~

runtime cần tìm định nghĩa hàm, đánh giá các đối số, gắn từng giá trị vào tham số tương ứng, thực hiện thân hàm và trả kết quả về vị trí gọi.

### 1.2. Chữ ký hàm

Chữ ký hàm (*function signature*) mô tả những đặc điểm cần thiết để gọi hàm. Tùy DSL, chữ ký có thể gồm:

- Tên hàm.
- Số lượng và thứ tự tham số.
- Tên tham số.
- Kiểu của từng tham số.
- Tham số bắt buộc hoặc tùy chọn.
- Giá trị mặc định.
- Kiểu kết quả.
- Tham số kiểu generic hoặc ràng buộc kiểu.
- Thông tin về tác dụng phụ hoặc khả năng lỗi.

Ví dụ:

~~~text
function convertCurrency(
    amount: Money,
    target: Currency,
    at: Instant = clock.now()
): Result<Money, ConversionError>
~~~

Chữ ký cho biết hàm nhận Money, Currency và một Instant tùy chọn; kết quả có thể thành công với Money hoặc thất bại với ConversionError.

### 1.3. Khai báo và lời gọi

Khai báo mô tả hàm có thể làm gì:

~~~text
function isEligible(customer: Customer): Boolean {
    return customer.tier == GOLD
}
~~~

Lời gọi yêu cầu runtime thực hiện hàm:

~~~text
let eligible = isEligible(currentCustomer)
~~~

Khai báo và lời gọi là hai khái niệm khác nhau. Một hàm có thể được khai báo nhưng không bao giờ được gọi; một lời gọi chỉ hợp lệ khi runtime hoặc compiler có thể tìm thấy một hàm phù hợp.

### 1.4. Hàm trả về giá trị và hàm hành động

Một số hàm tạo kết quả:

~~~text
function totalWithTax(order: Order): Money {
    return order.total + calculateTax(order)
}
~~~

Một số hàm chủ yếu thực hiện hành động:

~~~text
function sendReceipt(order: Order): Unit {
    emailGateway.send(order.customer.email, renderReceipt(order))
}
~~~

Kiểu Unit biểu thị không có kết quả dữ liệu hữu ích. Một DSL cũng có thể dùng kiểu Void hoặc cú pháp action riêng.

Nên phân biệt hàm tính toán với hành động có tác dụng phụ. Điều này giúp người đọc hiểu lời gọi chỉ tạo giá trị hay còn thay đổi trạng thái bên ngoài.

## 2. Tham số và đối số

### 2.1. Tham số và đối số khác nhau

**Tham số** (*parameter*) là tên và kiểu được khai báo trong định nghĩa hàm. **Đối số** (*argument*) là biểu thức hoặc giá trị được cung cấp tại nơi gọi.

~~~text
function add(left: Integer, right: Integer): Integer {
    return left + right
}

let result = add(10, 20)
~~~

left và right là tham số; 10 và 20 là đối số. Khi hàm chạy, runtime liên kết giá trị của đối số với tham số tương ứng.

### 2.2. Đối số theo vị trí

Với lời gọi theo vị trí, thứ tự đối số quyết định tham số nhận giá trị nào:

~~~text
applyDiscount(order, 0.15)
~~~

Đối số đầu tiên được gắn với order, đối số thứ hai được gắn với rate nếu chữ ký hàm khai báo theo thứ tự đó.

Ưu điểm là cú pháp ngắn. Nhược điểm là lời gọi khó đọc khi có nhiều tham số cùng kiểu.

### 2.3. Đối số có tên

Một DSL có thể cho phép chỉ định tên tham số:

~~~text
createShipment(
    order = currentOrder,
    priority = HIGH,
    insurance = true
)
~~~

Đối số có tên giúp lời gọi dễ hiểu và cho phép bỏ qua tham số tùy chọn. Runtime cần kiểm tra tên có tồn tại, có bị truyền lặp và có thiếu tham số bắt buộc hay không.

### 2.4. Tham số mặc định

Tham số có thể có giá trị mặc định:

~~~text
function formatMoney(
    amount: Money,
    includeCurrency: Boolean = true
): String
~~~

Hai lời gọi sau có thể tương đương:

~~~text
formatMoney(total)
formatMoney(total, true)
~~~

DSL cần quy định thời điểm đánh giá giá trị mặc định. Nếu mặc định là hằng số, có thể lưu trong metadata. Nếu mặc định gọi hàm hoặc đọc context, nó thường được đánh giá tại thời điểm gọi.

### 2.5. Tham số tùy chọn và giá trị vắng mặt

Tham số tùy chọn không nhất thiết đồng nghĩa với tham số có thể nhận null. Một DSL có thể phân biệt:

- Không cung cấp đối số.
- Cung cấp giá trị null.
- Cung cấp một giá trị Optional rỗng.

Những trường hợp này có ý nghĩa khác nhau và cần được biểu diễn rõ trong chữ ký hàm.

### 2.6. Tham số biến số lượng

Một hàm có thể nhận nhiều đối số cùng loại:

~~~text
function maximum(values: List<Decimal>): Decimal
~~~

Hoặc DSL có thể hỗ trợ cú pháp biến số lượng:

~~~text
maximum(12, 18, 9, 25)
~~~

Nếu hỗ trợ variadic parameter, cần xác định cách gom đối số thành danh sách, kiểu phần tử, vị trí tham số variadic và cách kết hợp với tham số có tên.

### 2.7. Truyền giá trị hay tham chiếu

DSL cần quy định cách truyền đối số:

- Truyền giá trị: hàm nhận giá trị của biểu thức.
- Truyền tham chiếu: hàm có thể truy cập hoặc thay đổi đối tượng được tham chiếu.
- Truyền bản sao: runtime tạo bản sao theo quy tắc kiểu.
- Truyền theo tên hoặc trì hoãn: biểu thức chỉ được đánh giá khi hàm cần dùng.

Nhiều DSL nên ưu tiên ngữ nghĩa truyền giá trị dễ dự đoán, đặc biệt với kiểu bất biến. Nếu hàm có thể thay đổi đối tượng, tác dụng phụ cần được thể hiện trong hợp đồng.

## 3. Quá trình thực thi lời gọi hàm

### 3.1. Các bước cơ bản

Một lời gọi hàm thường được thực hiện theo các bước:

1. Xác định hàm hoặc overload được gọi.
2. Đánh giá các đối số theo thứ tự đã quy định.
3. Kiểm tra và liên kết đối số với tham số.
4. Tạo frame hoặc context cho lần gọi.
5. Gán giá trị tham số và khởi tạo biến cục bộ.
6. Thực thi thân hàm.
7. Xử lý return hoặc lỗi.
8. Trả kết quả về nơi gọi và giải phóng tài nguyên của lần gọi.

Đây là mô hình khái quát. Interpreter có thể dùng stack frame; runtime dựa trên bytecode có thể dùng operand stack hoặc register; backend sinh mã có thể dựa vào calling convention của target.

### 3.2. Đánh giá đối số trước khi vào hàm

Ví dụ:

~~~text
calculateTax(order.total, getTaxRate(customer))
~~~

Runtime cần đánh giá order.total và lời gọi getTaxRate(customer) trước khi thực thi calculateTax, nếu DSL dùng quy tắc eager evaluation.

Thứ tự đánh giá hai đối số phải được xác định. Nếu getTaxRate có tác dụng phụ, thay đổi thứ tự có thể làm chương trình cho kết quả khác.

### 3.3. Liên kết tham số

Sau khi có giá trị đối số, runtime tạo môi trường gọi:

~~~text
Parameter environment:
  amount = Money(100000, VND)
  rate   = Decimal(0.08)
~~~

Các tham số có thể được lưu trong stack frame, activation record hoặc cấu trúc context tùy implementation.

### 3.4. Thực thi thân hàm

Thân hàm có thể gồm biểu thức, khai báo biến, điều kiện, vòng lặp, lời gọi hàm khác và thao tác miền.

Một hàm có thể gọi hàm khác. Mỗi lời gọi lồng nhau tạo một ngữ cảnh thực thi riêng và có quy tắc trả kết quả về caller.

### 3.5. Return

Khi gặp return, runtime kết thúc lần gọi hiện tại và chuyển giá trị kết quả về nơi gọi:

~~~text
function square(value: Decimal): Decimal {
    return value * value
}
~~~

Nếu hàm khai báo kiểu trả về Decimal, mọi đường kết thúc hợp lệ phải cung cấp kết quả tương thích theo quy tắc của DSL.

### 3.6. Hàm không trả về

Một hàm có thể kết thúc bình thường mà không trả dữ liệu:

~~~text
function recordAudit(event: AuditEvent): Unit {
    auditLog.append(event)
}
~~~

Nếu DSL dùng Unit, một lời gọi có thể đứng riêng thành câu lệnh. Nếu hàm không trả kết quả nhưng được dùng ở vị trí yêu cầu một giá trị, compiler hoặc runtime cần báo lỗi.

## 4. Phạm vi biến và vòng đời lời gọi

### 4.1. Biến cục bộ

Biến được khai báo bên trong hàm thường chỉ tồn tại trong lần gọi đó:

~~~text
function calculate(order: Order): Money {
    let subtotal = order.total
    let fee = calculateFee(order)
    return subtotal + fee
}
~~~

subtotal và fee thuộc môi trường của lần gọi calculate. Chúng không tự động trở thành biến toàn cục.

### 4.2. Stack frame

Trong một interpreter hoặc runtime dựa trên stack, mỗi lần gọi có thể tạo một stack frame chứa:

- Tham số.
- Biến cục bộ.
- Địa chỉ hoặc vị trí tiếp tục sau lời gọi.
- Giá trị tạm.
- Thông tin xử lý lỗi.
- Tham chiếu đến frame hoặc lexical environment bên ngoài.

Khi hàm kết thúc, frame được thu hồi theo quy tắc runtime.

### 4.3. Đệ quy

Một hàm có thể gọi lại chính nó:

~~~text
function factorial(n: Integer): Integer {
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}
~~~

Mỗi lần gọi đệ quy có tham số và biến cục bộ riêng. Runtime cần giới hạn độ sâu hoặc có chiến lược xử lý để tránh tràn stack khi đầu vào quá lớn hoặc điều kiện dừng không đạt được.

### 4.4. Hàm lồng nhau và closure

Một DSL có thể hỗ trợ hàm được khai báo bên trong hàm khác:

~~~text
function makeThreshold(minimum: Decimal): Function<Decimal, Boolean> {
    function above(value: Decimal): Boolean {
        return value >= minimum
    }
    return above
}
~~~

Hàm above tham chiếu biến minimum từ môi trường bên ngoài. Nếu hàm được trả ra và chạy sau khi makeThreshold kết thúc, runtime cần giữ lại lexical environment cần thiết. Cặp hàm và môi trường được giữ lại thường được gọi là closure.

### 4.5. Biến mutable được capture

Nếu closure giữ biến có thể thay đổi, DSL cần xác định closure nhìn thấy giá trị tại thời điểm tạo hay giá trị mới nhất khi gọi. Với thực thi đồng thời, còn cần quy tắc đồng bộ và an toàn luồng.

## 5. Hàm dựng sẵn và hàm do người dùng định nghĩa

### 5.1. Hàm dựng sẵn

Runtime thường cung cấp một thư viện hàm dựng sẵn (*built-in functions*) để thực hiện các thao tác phổ biến:

- Toán học: abs, min, max, round.
- Chuỗi: length, trim, contains, replace.
- Ngày giờ: dateAdd, startOfMonth, durationBetween.
- Collection: map, filter, sum, count.
- Chuyển đổi: parseInteger, formatDate, toString.
- Miền nghiệp vụ: calculateTax, isEligible, normalizeAddress.

Các hàm này cần có chữ ký và ngữ nghĩa được tài liệu hóa. Tên giống nhau ở hai DSL không bảo đảm hành vi giống nhau.

### 5.2. Hàm do người dùng định nghĩa

Người dùng có thể khai báo hàm theo cú pháp của DSL:

~~~text
function shippingCost(order: Order): Money {
    if order.total >= 1000000 VND {
        return Money.zero("VND")
    }
    return Money.of(30000, "VND")
}
~~~

Compiler hoặc interpreter xử lý hàm này như một phần của chương trình, nhưng vẫn cần xác định cách lưu, liên kết và thực thi định nghĩa.

### 5.3. Hàm native hoặc external

Một hàm DSL có thể được ánh xạ đến implementation viết bằng Java hoặc ngôn ngữ khác:

~~~text
external function lookupCustomer(id: CustomerId): Optional<Customer>
    providedBy "customer-service"
~~~

Runtime cần đăng ký provider, kiểm tra chữ ký và xử lý lỗi khi gọi qua ranh giới hệ thống.

### 5.4. Registry hàm

Một function registry có thể quản lý:

- Tên hàm.
- Chữ ký và overload.
- Implementation.
- Module hoặc provider.
- Quyền được phép gọi.
- Metadata về purity, effects và lỗi.
- Phiên bản API.

Registry giúp resolver và runtime dùng cùng một định nghĩa thay vì tra cứu rời rạc ở nhiều nơi.

### 5.5. Tránh phụ thuộc ngầm vào môi trường

Hàm built-in như now(), random() hoặc currentUser() phụ thuộc môi trường. Cần xác định nguồn clock, random generator và identity context. Điều này đặc biệt quan trọng khi cần tái hiện kết quả, kiểm thử hoặc chạy lại một rule.

## 6. Hàm thuần và hàm có tác dụng phụ

### 6.1. Hàm thuần

Hàm thuần (*pure function*) có hai đặc điểm:

- Cùng đầu vào thì cùng kết quả.
- Không tạo tác dụng phụ quan sát được bên ngoài.

Ví dụ:

~~~text
function double(value: Decimal): Decimal {
    return value * 2
}
~~~

Hàm này chỉ tính toán dựa trên đối số. Nó có thể dễ kiểm thử, cache và tối ưu hơn.

### 6.2. Hàm có tác dụng phụ

Một hàm có thể:

- Ghi database.
- Gửi email.
- Cập nhật trạng thái.
- Gọi API.
- Ghi log.
- Đọc đồng hồ hoặc dữ liệu môi trường.

Ví dụ:

~~~text
function charge(payment: Payment): ChargeResult {
    return paymentGateway.charge(payment)
}
~~~

Hai lần gọi cùng đối số có thể tạo kết quả khác nhau hoặc tạo hai giao dịch. Runtime cần kiểm soát quyền, retry và idempotency theo hợp đồng.

### 6.3. Vì sao cần phân biệt?

Compiler có thể tối ưu hàm thuần bằng cách tính trước hoặc tái sử dụng kết quả. Những tối ưu đó có thể sai với hàm có tác dụng phụ.

Ví dụ, không thể tùy ý bỏ một lời gọi gửi email chỉ vì kết quả trả về không được dùng.

### 6.4. Khai báo effect

DSL có thể mô tả effect:

~~~text
function charge(payment: Payment): ChargeResult
    effects [Network, ExternalState]
~~~

Metadata effect giúp compiler hoặc runtime biết hàm có thể truy cập tài nguyên nào. Cú pháp và hệ effect tùy DSL; điều quan trọng là các quyền và tác dụng phụ được công bố rõ.

### 6.5. Tính xác định

Hàm phụ thuộc thời gian, random hoặc dữ liệu bên ngoài có thể không xác định. Nếu hệ thống cần replay, audit hoặc cache, cần ghi nhận đầu vào môi trường hoặc đưa chúng thành tham số tường minh.

## 7. Phép toán trong DSL

### 7.1. Phép toán là gì?

Phép toán là thao tác kết hợp một hoặc nhiều toán hạng để tạo ra kết quả hoặc thay đổi trạng thái. Phép toán có thể được viết bằng ký hiệu:

~~~text
total + shippingFee
order.total >= threshold
isMember and hasCoupon
~~~

Một số DSL cũng biểu diễn phép toán bằng từ khóa hoặc hàm:

~~~text
between(age, 18, 65)
contains(tags, "priority")
~~~

### 7.2. Toán tử một ngôi, hai ngôi và nhiều ngôi

| Loại | Số toán hạng | Ví dụ |
|---|---:|---|
| Unary | 1 | not active, -amount |
| Binary | 2 | left + right, a == b |
| Ternary | 3 | condition ? first : second |
| Nhiều ngôi | Có thể nhiều hơn 3 | Hàm min(1, 2, 3) hoặc cú pháp miền riêng |

Một DSL không cần hỗ trợ mọi loại toán tử. Nó nên chọn cách viết phù hợp với người dùng và miền.

### 7.3. Các nhóm toán tử phổ biến

| Nhóm | Ví dụ | Kết quả thường gặp |
|---|---|---|
| Số học | +, -, *, /, % | Giá trị số hoặc kiểu miền |
| So sánh | ==, !=, <, <=, >, >= | Boolean |
| Logic | and, or, not | Boolean |
| Chuỗi | concat, contains, startsWith | String hoặc Boolean |
| Collection | in, contains, index | Boolean hoặc phần tử |
| Null-safe | ?., ?? | Giá trị tùy chọn hoặc giá trị thay thế |
| Miền | overlaps, before, within | Boolean hoặc kiểu miền |

### 7.4. Toán tử có ngữ nghĩa theo kiểu

Ký hiệu + có thể mang ý nghĩa khác nhau:

- Cộng hai Integer.
- Cộng hai Money cùng tiền tệ.
- Nối hai String nếu DSL cho phép.
- Ghép hai collection.

Compiler hoặc runtime phải chọn quy tắc dựa trên kiểu toán hạng, không chỉ dựa trên ký tự +.

## 8. Thứ tự ưu tiên và kết hợp toán tử

### 8.1. Độ ưu tiên

Biểu thức:

~~~text
2 + 3 * 4
~~~

thường được hiểu là 2 + (3 * 4), vì phép nhân có độ ưu tiên cao hơn phép cộng.

Nếu DSL không định nghĩa precedence, biểu thức hỗn hợp có thể gây hiểu nhầm hoặc cần bắt buộc dùng ngoặc.

### 8.2. Bảng ưu tiên minh họa

Một DSL có thể dùng thứ tự:

| Mức | Nhóm toán tử | Ví dụ |
|---:|---|---|
| 1 | Truy cập và gọi | a.b, f(x) |
| 2 | Unary | not x, -x |
| 3 | Nhân chia | *, /, % |
| 4 | Cộng trừ | +, - |
| 5 | So sánh | <, <=, ==, != |
| 6 | AND | and |
| 7 | OR | or |
| 8 | Điều kiện | if/then/else hoặc ?: |

Đây chỉ là ví dụ. Compiler phải tuân theo bảng ưu tiên được định nghĩa cho DSL cụ thể.

### 8.3. Associativity

Kết hợp trái:

~~~text
10 - 3 - 2
~~~

được hiểu là (10 - 3) - 2 nếu toán tử kết hợp trái.

Kết hợp phải:

~~~text
a = b = c
~~~

có thể được hiểu là a = (b = c) nếu phép gán kết hợp phải và DSL cho phép chuỗi gán.

### 8.4. Ngoại lệ không kết hợp

Một số toán tử so sánh có thể được quy định không kết hợp. Ví dụ:

~~~text
a < b < c
~~~

DSL cần quyết định biểu thức này có nghĩa là (a < b) and (b < c), hay bị từ chối để tránh hiểu nhầm.

### 8.5. Ngoặc và biểu thức nhóm

Ngoặc cho phép người viết thể hiện rõ thứ tự:

~~~text
(2 + 3) * 4
~~~

Parser thường tạo cấu trúc AST phản ánh nhóm biểu thức. Ngoặc không nhất thiết tạo phép toán runtime riêng, nhưng có thể được giữ trong metadata nguồn.

## 9. Quy tắc đánh giá toán hạng

### 9.1. Eager evaluation

Với eager evaluation, toán hạng được đánh giá trước khi áp dụng toán tử:

~~~text
calculate() + 10
~~~

Runtime gọi calculate(), lấy kết quả rồi cộng 10.

### 9.2. Thứ tự đánh giá trái sang phải

Một DSL có thể quy định toán hạng được đánh giá từ trái sang phải. Khi đó:

~~~text
first() + second()
~~~

first() được gọi trước second(). Quy tắc này cần được ghi rõ nếu các hàm có tác dụng phụ.

### 9.3. Lazy evaluation

Với lazy evaluation, biểu thức chỉ được đánh giá khi giá trị thực sự cần. Điều này thường xuất hiện trong:

- AND và OR có short-circuit.
- Tham số trì hoãn.
- Biểu thức điều kiện.
- Collection hoặc sequence lười.

### 9.4. Đánh giá có điều kiện

~~~text
if customer != null then customer.email else ""
~~~

Chỉ nhánh được chọn được đánh giá nếu DSL định nghĩa điều kiện theo cách lazy. Điều này tránh truy cập customer.email khi customer là null.

### 9.5. Tác dụng phụ và thứ tự

Nếu hai biểu thức có tác dụng phụ, thứ tự đánh giá có thể làm thay đổi kết quả. Vì vậy, runtime cần một quy tắc xác định và optimizer phải giữ nguyên thứ tự quan sát được.

## 10. Phép toán logic và short-circuit

### 10.1. AND

Với toán tử AND theo short-circuit, nếu vế trái là false, vế phải không cần được đánh giá:

~~~text
customer != null and customer.isActive
~~~

Nếu customer là null, runtime dừng ở vế trái và không truy cập isActive.

### 10.2. OR

Với OR theo short-circuit, nếu vế trái là true, vế phải không cần được đánh giá:

~~~text
isAdministrator or hasSpecialPermission()
~~~

Nếu isAdministrator đã true, hàm hasSpecialPermission không được gọi.

### 10.3. Short-circuit và side effect

Vì vế phải có thể không được chạy, không nên đặt hành động bắt buộc trong vế phải của một biểu thức logic nếu người viết kỳ vọng nó luôn xảy ra.

~~~text
isValid and recordAudit()
~~~

Nếu isValid là false, recordAudit không được gọi theo short-circuit. Nếu cần ghi audit trong mọi trường hợp, hãy viết thành câu lệnh riêng.

### 10.4. Đánh giá đầy đủ

Một số DSL có thể chọn eager Boolean evaluation, nghĩa là luôn đánh giá cả hai vế. Cách này khác với short-circuit và cần được quy định rõ. Không nên để interpreter và backend tự chọn cách khác nhau.

### 10.5. Ba giá trị logic

Nếu DSL có null hoặc unknown, logic có thể có ba trạng thái: true, false và unknown. Khi đó, bảng chân trị của AND, OR và NOT cần được định nghĩa. Ví dụ, false AND unknown có thể cho false, còn true AND unknown có thể cho unknown.

Đây là mô hình hữu ích trong truy vấn dữ liệu có giá trị null, nhưng người dùng cần hiểu kết quả unknown khác false.

## 11. Toán tử số học và kiểu miền

### 11.1. Cộng và trừ

Phép cộng và trừ cần xác định:

- Những kiểu nào tương thích.
- Kết quả có kiểu gì.
- Có cho phép chuyển kiểu ngầm không.
- Cách xử lý overflow.
- Cách xử lý đơn vị và độ chính xác.

Ví dụ, cộng Money cùng currency có thể hợp lệ, còn cộng USD với VND cần quy tắc chuyển đổi rõ.

### 11.2. Nhân và chia

Nhân một Money với Decimal có thể tạo Money. Chia Money cho Money cùng currency có thể tạo Decimal. Chia cho zero cần được quy định là lỗi, exception hoặc kết quả đặc biệt.

### 11.3. Modulo

Modulo thường áp dụng cho số nguyên nhưng một DSL có thể hỗ trợ kiểu số khác. Cần quy định dấu của kết quả và hành vi khi chia cho zero.

### 11.4. Làm tròn

Các phép tính tiền cần quy tắc làm tròn:

- Half up.
- Half even.
- Down hoặc truncate.
- Scale theo currency.

Không nên để cách làm tròn phụ thuộc ngầm vào backend hoặc thư viện số học.

### 11.5. Tràn số

Khi kết quả vượt phạm vi kiểu số, DSL có thể:

- Báo lỗi.
- Ném exception runtime.
- Dùng số nguyên độ rộng lớn hơn.
- Bão hòa ở giá trị tối đa hoặc tối thiểu.
- Dùng số học modulo.

Chính sách phải nhất quán giữa biên dịch, interpreter và backend.

### 11.6. Thứ nguyên và đơn vị

Nếu DSL có kiểu đơn vị, phép toán cần tuân theo đại số đơn vị:

~~~text
Distance / Duration -> Speed
Speed * Duration -> Distance
~~~

Phép cộng Distance với Duration không hợp lệ. Việc kiểm tra đơn vị có thể diễn ra khi phân tích kiểu hoặc trong một semantic pass riêng.

## 12. Toán tử so sánh và equality

### 12.1. So sánh thứ tự

Các toán tử <, <=, > và >= cần một quan hệ thứ tự hợp lệ. Date có thể được so sánh theo thời gian; Money có thể so sánh khi cùng currency; Customer có thể không có thứ tự tự nhiên.

### 12.2. Equality

Toán tử == cần xác định so sánh theo:

- Giá trị (*value equality*).
- Định danh (*identity equality*).
- Nội dung cấu trúc.
- Khóa nghiệp vụ.

Ví dụ, hai đối tượng Customer có cùng ID có được xem là bằng nhau không, hay phải là cùng instance? DSL cần chọn quy tắc phù hợp.

### 12.3. Null equality

Nếu null được hỗ trợ, cần xác định:

~~~text
value == null
~~~

có luôn trả Boolean hay có thể trả unknown. Một số DSL có toán tử riêng để kiểm tra null hoặc sự hiện diện.

### 12.4. Equality và collection

Các phép contains, distinct và set membership phụ thuộc quy tắc equality. Nếu kiểu miền không có equality ổn định, kết quả của collection operation có thể khó dự đoán.

### 12.5. So sánh chuỗi

So sánh chuỗi có thể phụ thuộc chữ hoa/thường, Unicode normalization và locale. DSL nên quy định so sánh ordinal, case-insensitive hay theo locale.

## 13. Toán tử truy cập và collection

### 13.1. Truy cập thuộc tính

~~~text
customer.address.city
~~~

Runtime có thể lần lượt đọc customer, address và city. Mỗi bước cần xác định kiểu và cách xử lý giá trị vắng mặt.

### 13.2. Null-safe navigation

Một DSL có thể hỗ trợ:

~~~text
customer?.address?.city
~~~

Nếu một thành phần ở giữa là null, phép truy cập có thể trả Optional hoặc null mà không ném lỗi. Kiểu kết quả cần phản ánh khả năng vắng mặt.

### 13.3. Null coalescing

Toán tử ?? có thể cung cấp giá trị thay thế:

~~~text
customer.nickname ?? customer.name
~~~

Vế phải thường chỉ được đánh giá nếu vế trái vắng mặt. Cần xác định null và Optional được xử lý ra sao.

### 13.4. Indexing

~~~text
orders[0]
~~~

Indexing cần quy định:

- Chỉ số bắt đầu từ 0 hay 1.
- Kiểu chỉ số được phép.
- Hành vi khi vượt phạm vi.
- Cách xử lý collection rỗng.
- Kiểu kết quả.

### 13.5. Slicing

Một số DSL hỗ trợ lấy đoạn:

~~~text
orders[2..5]
~~~

Phải xác định biên cuối có bao gồm hay không, chỉ số âm có được phép và hành vi khi phạm vi vượt giới hạn.

### 13.6. Membership

~~~text
customer.id in approvedCustomerIds
~~~

Toán tử in kiểm tra phần tử có thuộc collection hay không. Runtime cần dùng quy tắc equality tương ứng với kiểu phần tử.

## 14. Operator overloading

### 14.1. Khái niệm

Operator overloading cho phép một kiểu định nghĩa ý nghĩa riêng cho toán tử đã có:

~~~text
Money + Money -> Money
Distance + Distance -> Distance
~~~

Cùng ký hiệu + có thể được ánh xạ đến những implementation khác nhau tùy kiểu toán hạng.

### 14.2. Ánh xạ toán tử

Một DSL có thể định nghĩa:

~~~text
operator + for Money, Money returns Money
    using addMoney
~~~

Khi compiler gặp phép cộng hai Money, nó chọn implementation addMoney.

### 14.3. Quy tắc cần thiết

Operator overloading cần quy định:

- Những toán tử nào được overload.
- Số lượng và kiểu toán hạng.
- Kiểu kết quả.
- Cách chọn implementation khi có nhiều overload.
- Thứ tự đánh giá.
- Tác dụng phụ được phép.
- Quy tắc equality và thứ tự nếu có.

### 14.4. Tránh overload gây bất ngờ

Không nên định nghĩa phép + cho Customer theo nghĩa gửi email hoặc xóa dữ liệu. Người đọc thường kỳ vọng toán tử số học hoặc ghép có hành vi dễ đoán.

Toán tử nên giữ ý nghĩa gần với trực giác hoặc đặc tính toán học của kiểu.

### 14.5. Tính nhất quán đại số

Nếu kiểu Money hỗ trợ cộng, phép cộng nên có tính chất và quy tắc phù hợp với mô hình tiền tệ. Nếu toán tử equality được overload, nó nên nhất quán với hash/equality của collection khi DSL cung cấp các cấu trúc đó.

### 14.6. Khi nào nên dùng hàm thay toán tử?

Với thao tác miền phức tạp, hàm có tên thường rõ hơn:

~~~text
convertCurrency(amount, targetCurrency)
~~~

thay vì dùng toán tử tùy biến khó hiểu. Operator overloading phù hợp khi ký hiệu có ý nghĩa tự nhiên và ổn định.

## 15. Hàm bậc cao và hàm như giá trị

### 15.1. First-class function

Một DSL có thể coi hàm là giá trị: lưu trong biến, truyền làm đối số hoặc trả về từ hàm khác.

~~~text
let predicate = customer -> customer.tier == GOLD
~~~

Giá trị predicate là một hàm nhận Customer và trả Boolean nếu DSL hỗ trợ lambda.

### 15.2. Higher-order function

Hàm bậc cao (*higher-order function*) nhận một hàm khác hoặc trả về một hàm:

~~~text
function filter<T>(
    items: List<T>,
    predicate: Function<T, Boolean>
): List<T>
~~~

Sử dụng:

~~~text
let goldCustomers = filter(customers, c -> c.tier == GOLD)
~~~

### 15.3. map

map áp dụng một hàm lên từng phần tử và tạo collection kết quả:

~~~text
let names = map(customers, c -> c.name)
~~~

Nếu đầu vào là List<Customer> và lambda trả String, kết quả là List<String>.

### 15.4. filter

filter giữ lại những phần tử mà predicate trả true:

~~~text
let activeOrders = filter(orders, order -> order.isActive)
~~~

Thứ tự phần tử thường được giữ với List, nhưng cần quy định riêng cho Set hoặc collection không có thứ tự.

### 15.5. reduce hoặc fold

reduce kết hợp các phần tử thành một giá trị:

~~~text
let total = reduce(
    orders,
    Money.zero("VND"),
    (acc, order) -> acc + order.total
)
~~~

Nếu phép kết hợp có tính kết hợp và không có tác dụng phụ, runtime có thể xem xét xử lý song song. Nếu không, cần giữ thứ tự.

### 15.6. Lambda và closure

Lambda là hàm không nhất thiết có tên. Nó có thể capture biến bên ngoài. Runtime cần định nghĩa thời điểm capture, vòng đời và quy tắc khi closure được gọi bất đồng bộ.

## 16. Hàm bất đồng bộ và thao tác có thời gian chờ

### 16.1. Hàm async

Một DSL có thể cho phép hàm thực hiện công việc bất đồng bộ:

~~~text
async function loadCustomer(id: CustomerId): Customer
~~~

Lời gọi có thể trả về một Future hoặc Promise thay vì Customer ngay lập tức.

### 16.2. Await

~~~text
let customer = await loadCustomer(customerId)
~~~

await chờ kết quả bất đồng bộ theo mô hình runtime. DSL cần quy định await chỉ hợp lệ trong ngữ cảnh async nào và lỗi được truyền ra sao.

### 16.3. Thứ tự và concurrency

Hai tác vụ độc lập có thể được chạy song song:

~~~text
let customerTask = loadCustomer(id)
let orderTask = loadOrders(id)

let customer = await customerTask
let orders = await orderTask
~~~

Runtime cần quản lý task, cancellation, timeout và ngoại lệ. Nếu các tác vụ cùng sửa một trạng thái, cần đồng bộ hoặc transaction.

### 16.4. Lỗi bất đồng bộ

Lỗi có thể xuất hiện khi task hoàn thành chứ không phải ngay lúc gọi. Hợp đồng hàm nên thể hiện lỗi qua exception, Result hoặc kiểu tương đương.

### 16.5. Timeout và cancellation

Một DSL workflow hoặc integration cần quy định hành vi khi thao tác quá thời gian hoặc bị hủy. Runtime không nên để task chạy vô hạn nếu giới hạn thực thi yêu cầu timeout.

## 17. Xử lý lỗi trong hàm và phép toán

### 17.1. Exception

Một hàm có thể ném exception khi gặp điều kiện không thể tiếp tục:

~~~text
function parseAge(value: String): Integer {
    if not isNumeric(value) {
        throw InvalidAge(value)
    }
    return toInteger(value)
}
~~~

DSL cần xác định exception được truyền qua lời gọi, có thể bắt ở đâu và runtime ghi nhận thông tin nguồn thế nào.

### 17.2. Result type

Một cách khác là biểu diễn thành công hoặc thất bại trong kiểu trả về:

~~~text
function parseAge(value: String): Result<Integer, ParseError>
~~~

Người gọi phải xử lý hai nhánh. Cách này làm lỗi trở thành một phần của hợp đồng kiểu.

### 17.3. Optional và lỗi khác nhau

Optional biểu diễn giá trị có thể vắng mặt. Result biểu diễn thao tác có thể thất bại. Không nên dùng Optional để che giấu mọi lỗi, vì “không có kết quả” khác với “dịch vụ bị lỗi”.

### 17.4. Lỗi toán học

Các phép toán có thể thất bại do:

- Chia cho zero.
- Overflow.
- Căn bậc hai của giá trị không thuộc miền xác định.
- Chuyển đổi mất dữ liệu.
- Đơn vị không tương thích.
- Giá trị NaN hoặc vô cực nếu kiểu số cho phép.

DSL cần quy định lỗi được phát hiện tĩnh hay động và biểu diễn ra sao.

### 17.5. Bắt lỗi

~~~text
try {
    let result = convertCurrency(amount, target)
    save(result)
} catch ConversionError as error {
    recordFailure(error)
}
~~~

Nếu DSL hỗ trợ try/catch, cần xác định loại lỗi bắt được, phạm vi khối catch, thứ tự xử lý và hành vi khi handler cũng thất bại.

### 17.6. Không nuốt lỗi

Một handler không nên âm thầm bỏ qua lỗi quan trọng. Nếu xử lý tiếp, cần ghi nhận hoặc chuyển trạng thái lỗi theo hợp đồng để hệ thống vận hành có thể quan sát.

## 18. Hàm và phép toán trong ngữ cảnh miền

### 18.1. Context của DSL

Hàm DSL có thể cần context chứa:

- Người dùng hiện tại.
- Thời điểm đánh giá.
- Đơn vị tiền tệ mặc định.
- Dữ liệu đầu vào của rule.
- Dịch vụ hoặc repository được cấp.
- Trace ID và thông tin kiểm toán.

Context cần được truyền theo cơ chế rõ ràng. Phụ thuộc toàn cục ngầm có thể làm kiểm thử và replay khó khăn.

### 18.2. Hàm miền

Hàm như isEligible, calculateShipping hoặc canRefund thể hiện khái niệm của miền. Chữ ký và ngữ nghĩa nên được định nghĩa cùng chuyên gia nghiệp vụ và nhóm triển khai.

### 18.3. Quy tắc đơn vị

Một hàm calculateDistance có thể trả Distance; một hàm estimateDuration có thể nhận Distance và trả Duration. Type system có thể ngăn truyền nhầm đơn vị.

### 18.4. Quy tắc trạng thái

Hàm approveOrder có thể chỉ hợp lệ khi trạng thái đơn hàng là PENDING. Nếu trạng thái chỉ biết lúc chạy, runtime phải kiểm tra trước khi thay đổi.

### 18.5. Idempotency

Hàm thực hiện hành động bên ngoài có thể được gọi lại khi retry. Ví dụ, chargePayment không nên tạo hai giao dịch nếu cùng một yêu cầu được gửi lại. Cần idempotency key hoặc cơ chế deduplication theo hợp đồng.

### 18.6. Transaction

Nếu một hàm thực hiện nhiều thao tác dữ liệu, cần xác định transaction boundary, rollback và hành vi khi một bước thất bại. Không nên giả định nhiều lời gọi liên tiếp tự động nằm trong cùng transaction.

## 19. Quyền và giới hạn khi gọi hàm

### 19.1. Whitelist hàm

DSL không nên tự động cho phép gọi mọi method có thể truy cập trong host language. Runtime nên cung cấp danh sách hàm được phép gọi theo mục đích của DSL.

### 19.2. Capability

Một hàm có thể yêu cầu capability như DatabaseRead, NetworkCall hoặc SendEmail. Context thực thi chỉ cấp những capability cần thiết.

### 19.3. Kiểm tra quyền tại runtime

Compiler có thể xác nhận hàm được đăng ký, nhưng quyền của người dùng và trạng thái hệ thống cần được xác minh tại thời điểm hành động.

### 19.4. Giới hạn chi phí

Một hàm có thể chạy lâu, gọi đệ quy hoặc xử lý collection rất lớn. Runtime có thể giới hạn:

- Thời gian thực thi.
- Số lần gọi hàm.
- Độ sâu đệ quy.
- Bộ nhớ.
- Số phần tử xử lý.
- Số lời gọi dịch vụ.

### 19.5. Không gọi implementation tùy ý

Nếu hàm được cung cấp bởi plugin, registry cần kiểm tra nguồn và phiên bản. Không nên nạp hoặc chạy implementation tùy ý chỉ vì tên hàm xuất hiện trong DSL.

## 20. Hiệu năng thực thi hàm và phép toán

### 20.1. Chi phí lời gọi

Một lời gọi hàm có thể cần tra cứu, tạo frame, truyền tham số và xử lý kết quả. Runtime có thể tối ưu những lời gọi nhỏ hoặc thường xuyên, nhưng cần bảo toàn semantics.

### 20.2. Inline

Inlining thay lời gọi hàm bằng thân hàm tại vị trí gọi khi điều kiện phù hợp:

~~~text
function square(x) = x * x
let result = square(5)
~~~

Compiler có thể biến thành phép nhân trực tiếp. Inlining có thể giảm overhead nhưng làm tăng kích thước mã và không phải lúc nào cũng có lợi.

### 20.3. Memoization

Với hàm thuần và đầu vào ổn định, runtime có thể cache kết quả:

~~~text
memoize calculateTaxTable
~~~

Cache key phải chứa mọi đầu vào ảnh hưởng đến kết quả. Không nên memoize hàm phụ thuộc clock, quyền, dữ liệu thay đổi hoặc tác dụng phụ nếu không có chính sách invalidation rõ.

### 20.4. Vectorization

Một số DSL dữ liệu có thể áp dụng phép toán trên cả collection hoặc cột dữ liệu:

~~~text
orders.total * 1.08
~~~

Thay vì gọi hàm từng phần tử, backend có thể sinh phép tính vector hóa hoặc biểu thức SQL. Ngữ nghĩa null, overflow và thứ tự vẫn cần được giữ.

### 20.5. Đánh giá lười collection

Sequence lười chỉ tính phần tử khi cần. Điều này có thể giảm bộ nhớ nhưng thay đổi thời điểm tác dụng phụ và lỗi xuất hiện. DSL cần quy định rõ.

### 20.6. Đo lường trước tối ưu

Không nên mặc định mọi lời gọi hàm đều tốn kém. Hãy đo thời gian và số lần gọi trong workload thực tế, sau đó mới chọn inlining, caching hoặc batching.

## 21. Chẩn đoán lỗi liên quan đến hàm và phép toán

### 21.1. Lỗi hàm không tồn tại

Runtime hoặc compiler không tìm thấy hàm theo tên và phạm vi hiện tại. Diagnostic cần chỉ ra tên, module hoặc registry đang tra cứu.

### 21.2. Không có overload phù hợp

Tên tồn tại nhưng không có chữ ký nào nhận đối số hiện tại. Thông báo nên nêu kiểu mong đợi và kiểu thực tế.

### 21.3. Sai số lượng đối số

Diagnostic cần nêu số tham số cần có và số đối số được cung cấp, đồng thời phân biệt tham số tùy chọn.

### 21.4. Sai kiểu kết quả

Một lời gọi có thể trả Optional<Money> trong khi vị trí sử dụng yêu cầu Money. Thông báo nên giải thích cách unwrap hoặc xử lý giá trị vắng mặt.

### 21.5. Toán tử không hỗ trợ

Nếu kiểu không định nghĩa phép toán, diagnostic nên nêu toán tử và kiểu của từng toán hạng.

### 21.6. Lỗi đánh giá runtime

Chia cho zero hoặc truy cập index ngoài phạm vi có thể chỉ phát hiện lúc chạy nếu giá trị động. Diagnostic runtime nên có source location hoặc source map.

### 21.7. Mã lỗi ổn định

Một số mã minh họa:

| Mã | Ý nghĩa |
|---|---|
| FUNC_NOT_FOUND | Không tìm thấy hàm |
| FUNC_NO_MATCHING_OVERLOAD | Không có chữ ký phù hợp |
| FUNC_ARGUMENT_COUNT | Sai số lượng đối số |
| FUNC_ARGUMENT_TYPE | Kiểu đối số không phù hợp |
| FUNC_RETURN_TYPE | Kiểu kết quả không phù hợp |
| FUNC_PERMISSION_DENIED | Không có quyền gọi hàm |
| OPERATOR_NOT_DEFINED | Toán tử không được định nghĩa cho kiểu |
| OPERATOR_DIVIDE_BY_ZERO | Chia cho zero |
| OPERATOR_OVERFLOW | Tràn số |
| OPERATOR_INDEX_OUT_OF_RANGE | Chỉ số ngoài phạm vi |
| OPERATOR_UNIT_MISMATCH | Đơn vị không tương thích |

Mã lỗi giúp IDE, CLI và hệ thống log phân loại sự cố mà không phải phân tích câu thông báo.

## 22. Kiểm thử hàm và phép toán

### 22.1. Unit test cho hàm

Mỗi hàm cần test các đầu vào bình thường, biên và không hợp lệ. Với hàm thuần, có thể kiểm tra trực tiếp quan hệ đầu vào-kết quả.

### 22.2. Test chữ ký và liên kết đối số

Kiểm tra:

- Đối số theo vị trí.
- Đối số có tên.
- Tham số mặc định.
- Tham số tùy chọn.
- Sai số lượng và sai kiểu.
- Overload.

### 22.3. Test thứ tự đánh giá

Dùng hàm có log hoặc bộ đếm để xác nhận thứ tự đánh giá đối số và short-circuit theo đúng đặc tả.

### 22.4. Test bảng chân trị

Nếu DSL có Boolean ba trạng thái, cần test đầy đủ các tổ hợp AND, OR và NOT với true, false và unknown.

### 22.5. Test số học và đơn vị

Kiểm tra overflow, chia zero, làm tròn, currency, scale và phép toán thứ nguyên.

### 22.6. Test tác dụng phụ

Kiểm tra hàm ghi dữ liệu, gửi thông điệp hoặc gọi API có được thực hiện đúng số lần và đúng thứ tự.

### 22.7. Test interpreter và backend

Nếu DSL có nhiều cách thực thi, cùng một chương trình và context nên tạo kết quả tương đương theo hợp đồng. Differential testing có thể phát hiện khác biệt giữa interpreter và mã sinh.

### 22.8. Test lỗi và source mapping

Kiểm tra lỗi runtime được ánh xạ về đúng lời gọi hoặc toán tử trong DSL, kèm thông tin đủ để điều tra.

## 23. Ví dụ tổng hợp: tính giá đơn hàng

Giả sử DSL hỗ trợ các kiểu Money, Decimal, Order và Customer. Các hàm:

~~~text
function subtotal(order: Order): Money
function discountRate(customer: Customer): Decimal
function shippingFee(order: Order): Money
function calculateTotal(order: Order, customer: Customer): Money
~~~

Định nghĩa:

~~~text
function calculateTotal(order: Order, customer: Customer): Money {
    let base = subtotal(order)
    let rate = discountRate(customer)
    let discount = base * rate
    let shipping = shippingFee(order)
    return base - discount + shipping
}
~~~

### 23.1. Phân tích lời gọi

Khi chạy calculateTotal, runtime:

1. Đánh giá order và customer.
2. Liên kết hai giá trị với tham số.
3. Gọi subtotal và nhận Money.
4. Gọi discountRate và nhận Decimal.
5. Nhân base với rate để tính discount.
6. Gọi shippingFee và nhận Money.
7. Tính base trừ discount rồi cộng shipping.
8. Trả Money về caller.

### 23.2. Kiểm tra kiểu

Phép nhân Money với Decimal cần được định nghĩa để trả Money. Phép trừ và cộng Money cần cùng currency. Nếu currency khác nhau, runtime hoặc type checker cần yêu cầu chuyển đổi rõ.

### 23.3. Tác dụng phụ

Nếu subtotal chỉ đọc dữ liệu và discountRate là hàm thuần, chúng có thể có semantics dễ dự đoán. Nếu shippingFee gọi dịch vụ vận chuyển, nó có thể có lỗi mạng hoặc phụ thuộc trạng thái bên ngoài.

### 23.4. Lỗi miền

Nếu rate lớn hơn 1 trong khi chính sách chỉ cho phép giảm tối đa 100%, validation cần phát hiện. Nếu rate lấy từ cấu hình động, kiểm tra phải được thực hiện lúc chạy.

### 23.5. Tái hiện kết quả

Để tái hiện phép tính, context cần giữ dữ liệu đơn hàng, khách hàng, currency, thời điểm và mọi thông tin bên ngoài có ảnh hưởng đến kết quả.

## 24. Những sai lầm thường gặp

### 24.1. Không quy định thứ tự đánh giá

Hai implementation có thể đánh giá đối số theo thứ tự khác nhau và tạo hành vi khác khi có side effect. Thứ tự cần nằm trong đặc tả DSL.

### 24.2. Coi mọi hàm là thuần

Hàm gọi database hoặc gửi email không thể được tối ưu như phép tính thuần. Cần metadata effect hoặc hợp đồng rõ.

### 24.3. Overload toán tử tùy tiện

Khi + hoặc == mang ý nghĩa bất ngờ, chương trình khó đọc. Dùng hàm có tên cho hành động miền phức tạp.

### 24.4. Không phân biệt Optional và lỗi

Không tìm thấy dữ liệu có thể là kết quả hợp lệ; dịch vụ bị lỗi là tình huống khác. Kiểu trả về nên biểu diễn rõ.

### 24.5. Để hành động trong biểu thức logic

Short-circuit có thể khiến hành động không được gọi. Hành động bắt buộc nên được viết thành câu lệnh riêng.

### 24.6. Không kiểm soát đệ quy và vòng lặp

Hàm đệ quy hoặc xử lý collection lớn có thể tiêu tốn tài nguyên. Runtime cần giới hạn phù hợp.

### 24.7. Dựa vào kiểu số chung cho mọi đơn vị

Decimal không phân biệt tiền, phần trăm, khoảng cách và thời gian. Kiểu miền hoặc metadata đơn vị giúp tránh phép toán sai.

### 24.8. Khác biệt giữa interpreter và backend

Nếu interpreter dùng short-circuit nhưng backend đánh giá đầy đủ, cùng một chương trình có thể có hành vi khác. Cần một hợp đồng semantics chung và kiểm thử tương đương.

## 25. Quy trình thiết kế hàm và phép toán

Một quy trình có thể gồm:

1. Xác định thao tác miền cần cung cấp.
2. Thiết kế tên và chữ ký hàm.
3. Chọn kiểu tham số và kiểu kết quả.
4. Xác định tham số bắt buộc, tùy chọn và mặc định.
5. Quy định thứ tự đánh giá và truyền đối số.
6. Phân loại hàm thuần, hàm có tác dụng phụ và capability cần thiết.
7. Định nghĩa toán tử, precedence và associativity.
8. Xác định chuyển kiểu, null, đơn vị và lỗi toán học.
9. Đăng ký built-in hoặc provider external.
10. Thiết kế diagnostic, timeout, retry và xử lý lỗi.
11. Kiểm thử lời gọi, toán tử, side effect và các backend.
12. Version hóa API và theo dõi tương thích runtime.

## 26. Câu hỏi tự đánh giá

1. Phân biệt khai báo hàm, chữ ký hàm và lời gọi hàm.
2. Tham số khác đối số như thế nào?
3. Runtime thực hiện những bước nào khi gọi một hàm?
4. Vì sao thứ tự đánh giá đối số cần được quy định?
5. Hàm thuần khác hàm có tác dụng phụ như thế nào?
6. Short-circuit của AND và OR hoạt động ra sao?
7. Precedence và associativity ảnh hưởng đến cách hiểu biểu thức thế nào?
8. Khi nào operator overloading hữu ích và khi nào nên dùng hàm có tên?
9. Optional khác Result như thế nào?
10. Runtime cần kiểm soát điều gì khi thực thi hàm async?
11. Vì sao Money và Distance không nên chỉ được xem là Decimal?
12. Làm thế nào để bảo đảm interpreter và backend thực thi cùng semantics?

## Kết luận

Hàm và phép toán xác định cách một DSL thực hiện tính toán và hành động. Chữ ký hàm mô tả tham số, kiểu và kết quả; runtime đánh giá đối số, liên kết tham số, chạy thân hàm và trả kết quả. Phép toán kết hợp toán hạng theo quy tắc kiểu, độ ưu tiên, associativity và thứ tự đánh giá đã được định nghĩa.

Một DSL đáng tin cậy cần phân biệt hàm thuần với hàm có tác dụng phụ, quy định rõ short-circuit, chuyển kiểu, null, đơn vị, lỗi toán học và hành vi bất đồng bộ. Các hàm miền và operator cần có hợp đồng dễ hiểu, quyền gọi được kiểm soát và diagnostic có thể truy về nguồn. Khi interpreter, optimizer và backend tuân theo cùng semantics, chương trình DSL sẽ cho kết quả nhất quán, dễ kiểm thử và an toàn hơn khi tích hợp với hệ thống thực tế.

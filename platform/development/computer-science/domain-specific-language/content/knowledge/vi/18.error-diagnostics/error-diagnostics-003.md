# Lỗi ngữ nghĩa trong DSL

Một chương trình trong ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) có thể được viết đúng quy tắc từ vựng và cú pháp nhưng vẫn không có ý nghĩa hợp lệ. Ví dụ, biểu thức có thể cộng một ngày với tên khách hàng, gọi một hàm bằng sai số lượng tham số, tham chiếu đến một thuộc tính không tồn tại trên kiểu dữ liệu, hoặc khai báo một quy tắc vi phạm ràng buộc của miền nghiệp vụ.

Những vấn đề đó thuộc nhóm **lỗi ngữ nghĩa** (*semantic errors*). Chúng xuất hiện khi cấu trúc chương trình đã được phân tích nhưng ý nghĩa của cấu trúc không phù hợp với quy tắc của ngôn ngữ, hệ kiểu hoặc miền bài toán. Lỗi ngữ nghĩa có thể được phát hiện trước khi chạy, trong quá trình biên dịch hoặc chỉ khi thực thi, tùy vào thông tin mà hệ thống có thể biết ở từng thời điểm.

Chẩn đoán lỗi ngữ nghĩa giúp người dùng hiểu vì sao một cấu trúc hợp lệ về hình thức lại không thể được chấp nhận hoặc không thể thực hiện đúng. Một compiler DSL tốt cần phân biệt lỗi ngữ nghĩa với lỗi cú pháp, phân loại nguyên nhân, gắn lỗi với vị trí nguồn và tránh báo nhiều lỗi dây chuyền từ cùng một vấn đề gốc.

## 1. Lỗi ngữ nghĩa là gì?

### 1.1. Cú pháp đúng chưa có nghĩa là chương trình đúng

Xét biểu thức:

~~~text
customer.total + "free shipping"
~~~

Parser có thể nhận diện biểu thức này là phép cộng giữa hai toán hạng. Cấu trúc cú pháp hợp lệ nếu grammar cho phép biểu thức cộng. Tuy nhiên, nếu customer.total có kiểu Money còn chuỗi có kiểu String, phép cộng có thể không được định nghĩa.

Parser chỉ xác nhận rằng các token được kết hợp theo grammar. Semantic analyzer xác định biểu thức có ý nghĩa theo quy tắc kiểu và miền hay không.

Một ví dụ khác:

~~~text
rule Discount {
    when order.total > 1000000
    then applyDiscount(150)
}
~~~

Đoạn DSL có thể parse thành công. Nhưng nếu hàm applyDiscount chỉ chấp nhận tỷ lệ từ 0 đến 100, giá trị 150 vi phạm ràng buộc miền. Đây là lỗi ngữ nghĩa hoặc lỗi validation tĩnh tùy cách DSL định nghĩa giá trị và thời điểm kiểm tra.

### 1.2. Ngữ nghĩa của chương trình

Ngữ nghĩa (*semantics*) mô tả ý nghĩa và hành vi của cấu trúc DSL. Nó trả lời các câu hỏi:

- Biểu thức tạo ra giá trị thuộc kiểu nào?
- Phép toán có được phép áp dụng cho các kiểu đó không?
- Tên tham chiếu chỉ đến khai báo nào?
- Hàm được gọi có tồn tại và nhận đúng đối số không?
- Quy tắc có thỏa điều kiện miền không?
- Giá trị có nằm trong phạm vi cho phép không?
- Hành động có thể thực hiện trong ngữ cảnh hiện tại không?
- Chương trình có thể thực thi theo mô hình dữ liệu và quyền hiện có không?

Ngữ nghĩa có thể được định nghĩa bằng quy tắc kiểu, quy tắc đánh giá biểu thức, hợp đồng API, bất biến miền và chính sách thực thi.

### 1.3. Lỗi ngữ nghĩa không chỉ là lỗi kiểu

Lỗi kiểu là một nhóm quan trọng của lỗi ngữ nghĩa, nhưng không phải toàn bộ. Những lỗi sau cũng có thể là lỗi ngữ nghĩa:

- Dùng một biến trước khi được khởi tạo.
- Gọi hàm không đúng số lượng hoặc kiểu tham số.
- Trả về giá trị không phù hợp với kiểu kết quả.
- Khai báo hai thành phần vi phạm quy tắc duy nhất.
- Tạo khoảng thời gian có ngày kết thúc trước ngày bắt đầu.
- Áp dụng hành động không được phép trong trạng thái hiện tại.
- Vi phạm ràng buộc nghiệp vụ như tỷ lệ chiết khấu ngoài giới hạn.
- Dùng một biểu thức không phải Boolean ở vị trí điều kiện.
- Tham chiếu một phần tử không tồn tại trong mô hình dữ liệu đã xác định.

### 1.4. Ngữ nghĩa tĩnh và ngữ nghĩa động

Có thể chia kiểm tra ngữ nghĩa thành hai nhóm lớn:

| Nhóm | Thời điểm kiểm tra | Ví dụ |
|---|---|---|
| Ngữ nghĩa tĩnh | Trước khi thực thi, khi đã có đủ thông tin | Kiểu hai vế phép cộng không tương thích |
| Ngữ nghĩa động | Khi chương trình chạy, phụ thuộc dữ liệu hoặc môi trường thực tế | Số dư tài khoản không đủ để thanh toán |

Ranh giới giữa hai nhóm phụ thuộc thiết kế DSL. Nếu một giá trị là hằng số tại thời điểm biên dịch, hệ thống có thể kiểm tra nó tĩnh. Nếu giá trị chỉ có khi nhận dữ liệu thực tế, việc kiểm tra có thể phải diễn ra lúc chạy.

## 2. Phân biệt lỗi từ vựng, cú pháp, phân giải tên, kiểu và ngữ nghĩa miền

Các giai đoạn xử lý DSL thường tạo ra những loại lỗi khác nhau. Phân loại đúng giúp diagnostic chỉ ra nguyên nhân thay vì dùng một thông báo chung.

| Loại lỗi | Câu hỏi hệ thống cần trả lời | Ví dụ |
|---|---|---|
| Từ vựng | Ký tự có tạo thành token hợp lệ không? | Chuỗi chưa đóng dấu nháy |
| Cú pháp | Token có được sắp xếp theo grammar không? | Thiếu từ khóa then hoặc dấu đóng khối |
| Phân giải tên | Tên tham chiếu có chỉ đến khai báo hợp lệ không? | Biến taxRate chưa được khai báo |
| Kiểu | Các giá trị và phép toán có tương thích kiểu không? | Cộng Money với Customer |
| Ngữ nghĩa miền | Cấu trúc có thỏa quy tắc nghiệp vụ không? | Tỷ lệ giảm giá là 150% khi giới hạn là 100% |
| Thực thi | Hành động có thể hoàn tất trong môi trường thực tế không? | Dịch vụ thanh toán không phản hồi |

Các nhóm có thể liên quan. Ví dụ, nếu tên chưa được phân giải, type checker không thể biết kiểu của biểu thức. Khi đó, lỗi tên là nguyên nhân gốc; một lỗi kiểu phát sinh tiếp theo có thể chỉ là hệ quả.

### 2.1. Ví dụ cú pháp đúng nhưng ngữ nghĩa sai

~~~text
let deliveryDate: Date = customer.name
~~~

Giả sử customer.name có kiểu String. Cú pháp khai báo biến có thể hợp lệ, tên customer và name đều được phân giải, nhưng giá trị String không thể gán cho Date nếu DSL không có chuyển đổi phù hợp. Đây là lỗi tương thích kiểu.

### 2.2. Ví dụ kiểu đúng nhưng vi phạm miền

~~~text
let discountRate: Decimal = 1.75
~~~

Decimal là kiểu hợp lệ, nhưng nếu miền quy định tỷ lệ giảm giá nằm trong khoảng từ 0 đến 1, giá trị 1.75 vi phạm ràng buộc. Đây không phải lỗi cú pháp và cũng không nhất thiết là lỗi kiểu cơ bản; đó là lỗi ràng buộc miền.

### 2.3. Ví dụ hợp lệ khi biên dịch nhưng thất bại lúc chạy

~~~text
when account.balance >= payment.amount
then transfer(payment.amount)
~~~

Nếu số dư thay đổi giữa lúc kiểm tra và lúc chuyển tiền, hành động vẫn có thể thất bại. Đây là vấn đề thực thi và nhất quán dữ liệu, không thể luôn được phát hiện bằng kiểm tra tĩnh.

## 3. Các giai đoạn phân tích ngữ nghĩa

Một pipeline DSL thường tách việc phân tích cú pháp khỏi việc xác định ý nghĩa. Một luồng khái quát:

~~~mermaid
flowchart TD
    A["Nguồn DSL"] --> B["Lexer"]
    B --> C["Parser"]
    C --> D["AST"]
    D --> E["Xây dựng symbol và scope"]
    E --> F["Phân giải tên"]
    F --> G["Kiểm tra kiểu"]
    G --> H["Kiểm tra ràng buộc miền"]
    H --> I["IR hoặc mô hình đã kiểm tra"]
    I --> J["Thực thi hoặc sinh mã"]
    B -.-> K["Diagnostic"]
    C -.-> K
    F -.-> K
    G -.-> K
    H -.-> K
    J -.-> K
~~~

Đây là một cách tổ chức phổ biến. DSL nhỏ có thể gộp một số bước; DSL lớn có thể chia thành nhiều pass riêng.

### 3.1. Xây dựng mô hình khai báo

Sau khi parser tạo AST, compiler thu thập khai báo kiểu, biến, hàm, module và quy tắc. Những thông tin này được đưa vào symbol table hoặc mô hình tương đương.

Mục tiêu là có đủ thông tin để phân giải các tham chiếu và kiểm tra quan hệ giữa các thành phần.

### 3.2. Phân giải tên

Resolver tìm đối tượng tương ứng với mỗi tên. Nếu không tìm thấy, tên mơ hồ hoặc không được truy cập, compiler phát diagnostic và có thể tạo ký hiệu lỗi để tiếp tục.

### 3.3. Kiểm tra kiểu

Type checker xác định kiểu của biểu thức và kiểm tra những phép toán, lời gọi, phép gán và kết quả trả về có hợp lệ hay không.

### 3.4. Kiểm tra ràng buộc miền

Semantic analyzer có thể kiểm tra những điều kiện chuyên biệt của miền như giới hạn số tiền, trạng thái quy trình, quan hệ giữa các trường, tính hợp lệ của khoảng ngày hoặc quyền áp dụng một hành động.

### 3.5. Tạo mô hình đã kiểm tra

Khi các kiểm tra cần thiết thành công, compiler có thể tạo IR hoặc mô hình đã xác nhận ngữ nghĩa. Backend và runtime sử dụng cấu trúc này để sinh mã hoặc thực thi.

Không nên để backend phải tự diễn giải lại những quy tắc ngữ nghĩa cơ bản mà các pass trước đã có thể kiểm tra.

## 4. Lỗi kiểu dữ liệu

### 4.1. Phép toán không tương thích kiểu

Mỗi toán tử có những kiểu toán hạng được phép. Ví dụ:

| Toán tử | Kiểu thường được hỗ trợ | Ví dụ không hợp lệ |
|---|---|---|
| Cộng số | Integer, Decimal hoặc kiểu số tương thích | 10 + Customer |
| So sánh ngày | Date với Date | Date > Money |
| Logic AND | Boolean với Boolean | true and "yes" |
| Nối chuỗi | String với kiểu được chuyển đổi rõ | String + Payment |
| Truy cập chỉ mục | Collection và kiểu chỉ mục hợp lệ | Date[2] |

DSL có thể định nghĩa phép toán khác với ngôn ngữ lập trình thông thường. Chẳng hạn, phép cộng hai giá trị Money chỉ hợp lệ khi chúng cùng đơn vị tiền tệ.

### 4.2. Gán sai kiểu

~~~text
let customerCount: Integer = "twenty"
~~~

Nếu chuỗi không được chuyển đổi tường minh, việc gán String cho Integer không hợp lệ.

Diagnostic nên nêu:

- Kiểu đích mà khai báo yêu cầu.
- Kiểu thực tế của biểu thức.
- Vị trí của biểu thức không tương thích.
- Chuyển đổi tường minh được hỗ trợ nếu có.

### 4.3. Sai kiểu tham số hàm

~~~text
function applyDiscount(rate: Decimal, order: Order)

applyDiscount(order, 0.10)
~~~

Tên hàm được tìm thấy và số lượng đối số đúng, nhưng thứ tự kiểu không đúng. Diagnostic nên chỉ ra vị trí tham số và kiểu mong đợi tương ứng.

### 4.4. Sai kiểu kết quả trả về

~~~text
function calculateTotal(order: Order): Money {
    return order.customer
}
~~~

Nếu order.customer có kiểu Customer, giá trị trả về không tương thích với Money.

### 4.5. Kiểu không thể suy luận

Một biểu thức generic hoặc biểu thức rỗng có thể không cung cấp đủ thông tin để xác định kiểu.

~~~text
let empty = []
~~~

Nếu DSL không có kiểu danh sách rỗng mặc định và không có ngữ cảnh đích, compiler có thể yêu cầu khai báo kiểu:

~~~text
let empty: List<Customer> = []
~~~

Không nên tự chọn một kiểu tùy ý nếu điều đó làm thay đổi hành vi về sau.

### 4.6. Kiểu nullable và giá trị vắng mặt

Nếu một trường có thể không có giá trị, hệ kiểu cần biểu diễn điều đó rõ ràng, chẳng hạn Optional<T> hoặc kiểu nullable.

~~~text
let email: Optional<String> = customer.email
sendEmail(email)
~~~

Nếu sendEmail yêu cầu String, truyền Optional<String> trực tiếp là không hợp lệ. Người dùng cần kiểm tra sự hiện diện hoặc cung cấp giá trị thay thế.

### 4.7. Null và quy tắc so sánh

DSL cần định nghĩa cách xử lý null:

- Có kiểu Null riêng không?
- Có cho phép gán null vào mọi kiểu không?
- So sánh null dùng phép bằng thông thường hay toán tử riêng?
- Phép toán trên giá trị null tạo lỗi, null hay kết quả Boolean đặc biệt?

Nếu quy tắc không rõ, cùng một biểu thức có thể được hiểu khác nhau ở parser, type checker và runtime.

## 5. Lỗi chuyển đổi kiểu

### 5.1. Chuyển đổi ngầm và tường minh

Một số hệ kiểu cho phép chuyển đổi ngầm giữa những kiểu tương thích, ví dụ Integer sang Decimal. Chuyển đổi khác cần được viết rõ:

~~~text
let amount: Money = parseMoney(input)
~~~

Chuyển đổi ngầm làm cú pháp gọn nhưng có thể che giấu mất dữ liệu hoặc thay đổi ý nghĩa. DSL nên giới hạn những chuyển đổi được phép và tài liệu hóa chúng.

### 5.2. Mất độ chính xác

~~~text
let whole: Integer = decimalValue
~~~

Nếu decimalValue là 12.8, chuyển sang Integer có thể làm tròn hoặc cắt phần thập phân. Hệ thống cần quy định hành vi và yêu cầu chuyển đổi tường minh nếu có nguy cơ mất thông tin.

### 5.3. Chuyển đổi không được định nghĩa

Không phải mọi kiểu đều có thể chuyển đổi sang nhau. Chẳng hạn, một Customer không thể tự động trở thành Money. Diagnostic nên tránh đề xuất phép ép kiểu chỉ để làm cho biểu thức biên dịch được.

### 5.4. Chuyển đổi do người dùng định nghĩa

DSL có thể cho phép đăng ký converter:

~~~text
converter String to Money using parseMoney
~~~

Khi có nhiều converter cùng phù hợp, việc chọn converter cũng có thể mơ hồ. Semantic analyzer cần xác định quy tắc ưu tiên hoặc yêu cầu người dùng chỉ định converter.

### 5.5. Chuyển đổi có thể thất bại

Chuyển một chuỗi thành số có thể thất bại khi dữ liệu không đúng định dạng. Nếu đầu vào chỉ được biết lúc chạy, kết quả chuyển đổi nên biểu diễn khả năng lỗi, chẳng hạn Result<Integer, ParseError>, thay vì giả định luôn thành công.

## 6. Lỗi lời gọi hàm và toán tử

### 6.1. Số lượng tham số

~~~text
function calculateTax(amount: Money, region: Region): Money

calculateTax(order.total)
~~~

Lời gọi thiếu đối số region. Đây là lỗi chữ ký hàm, có thể được phát hiện sau khi phân giải tên.

### 6.2. Tên tham số và đối số có tên

Nếu DSL hỗ trợ đối số có tên:

~~~text
calculateTax(amount = order.total, country = "VN")
~~~

thì tên tham số country phải tồn tại trong chữ ký. Nếu hàm chỉ khai báo region, country là tên đối số không hợp lệ.

### 6.3. Overload không phù hợp

Một tên hàm có thể có nhiều chữ ký. Semantic analyzer phải chọn overload theo kiểu đối số và quy tắc chuyển đổi. Nếu không có chữ ký phù hợp, diagnostic cần liệt kê chữ ký được hỗ trợ.

### 6.4. Overload mơ hồ

Nếu hai overload đều phù hợp với cùng đối số, hệ thống cần một quy tắc chọn duy nhất hoặc báo lỗi mơ hồ. Không nên dựa vào thứ tự khai báo nếu thứ tự đó không phải một phần hợp đồng của DSL.

### 6.5. Toán tử chưa được định nghĩa cho kiểu

~~~text
customerA + customerB
~~~

Nếu kiểu Customer không định nghĩa phép cộng, biểu thức không hợp lệ. Nếu DSL cho phép operator overloading, semantic analyzer cần xác định toán tử được ánh xạ đến hàm nào và kiểm tra chữ ký của hàm đó.

## 7. Lỗi về khai báo và luồng điều khiển

### 7.1. Biến chưa được khởi tạo

~~~text
let total: Money
if order.isPaid {
    total = order.total
}
applyDiscount(total)
~~~

Nếu nhánh điều kiện không chạy, total chưa có giá trị. Một phân tích luồng dữ liệu có thể phát hiện rằng biến chưa được gán trên mọi đường đi trước khi sử dụng.

### 7.2. Khai báo trùng hoặc khai báo không hợp lệ

Một DSL có thể yêu cầu tên duy nhất trong một phạm vi, hoặc yêu cầu một loại khai báo chỉ xuất hiện một lần. Vi phạm các quy tắc đó là vấn đề ngữ nghĩa của môi trường khai báo.

### 7.3. Return thiếu hoặc sai kiểu

~~~text
function getCustomer(id: CustomerId): Customer {
    if id.isValid {
        return database.findCustomer(id)
    }
}
~~~

Nếu hàm yêu cầu trả về Customer trên mọi đường đi, nhánh id không hợp lệ đang thiếu giá trị trả về. Compiler có thể yêu cầu trả về Optional<Customer>, ném lỗi hoặc xử lý nhánh còn lại theo quy tắc của DSL.

### 7.4. Return không phù hợp với hàm

~~~text
function isEligible(customer: Customer): Boolean {
    return customer.name
}
~~~

Nếu customer.name có kiểu String, giá trị trả về không phù hợp với Boolean.

### 7.5. Break hoặc continue ngoài vòng lặp

Nếu DSL có vòng lặp, break và continue chỉ hợp lệ trong ngữ cảnh được quy định. Dùng chúng ở ngoài vòng lặp có thể là lỗi ngữ nghĩa dù parser nhận diện đúng từ khóa.

### 7.6. Đường đi không thể tiếp cận

~~~text
return result
applyDiscount(0.10)
~~~

Nếu return kết thúc hàm, câu lệnh sau không thể được thực thi. Một DSL có thể báo warning về mã không thể tiếp cận. Tùy chính sách, warning không nhất thiết làm chương trình thất bại.

### 7.7. Điều kiện không phải Boolean

~~~text
if order.total {
    applyDiscount(0.10)
}
~~~

Nếu điều kiện yêu cầu Boolean nhưng order.total là Money, biểu thức không hợp lệ. DSL nên yêu cầu phép so sánh tường minh.

## 8. Ràng buộc miền nghiệp vụ

### 8.1. Khác biệt giữa kiểu cơ bản và kiểu miền

Kiểu Decimal có thể biểu diễn nhiều số, nhưng không phải mọi số đều hợp lệ làm tỷ lệ giảm giá. Kiểu Money có thể biểu diễn số tiền, nhưng giá trị âm có thể không hợp lệ cho một số thao tác.

Ràng buộc miền bổ sung điều kiện lên giá trị hoặc quan hệ giữa nhiều giá trị.

### 8.2. Miền giá trị

Ví dụ:

~~~text
discountRate: Decimal between 0 and 1
quantity: Integer greater than 0
age: Integer between 0 and 130
~~~

Nếu giá trị hằng nằm ngoài miền, compiler có thể phát hiện ngay. Nếu giá trị được nạp từ dữ liệu lúc chạy, validator hoặc runtime cần kiểm tra trước khi thực hiện hành động.

### 8.3. Bất biến giữa các trường

Một khoảng thời gian cần ngày kết thúc không sớm hơn ngày bắt đầu:

~~~text
type DateRange {
    start: Date
    end: Date
    invariant end >= start
}
~~~

Hai trường có thể đều đúng kiểu Date nhưng đối tượng vẫn vi phạm bất biến nếu end nhỏ hơn start.

### 8.4. Ràng buộc phụ thuộc trạng thái

Một hành động có thể chỉ hợp lệ ở một số trạng thái:

~~~text
when order.status is PAID
then ship(order)
~~~

Nếu hành động ship chỉ được phép khi đơn hàng đã thanh toán, compiler có thể kiểm tra khi trạng thái là hằng hoặc được ràng buộc tĩnh. Nếu trạng thái đến từ dữ liệu thực tế, runtime cần xác nhận trước khi thực hiện.

### 8.5. Ràng buộc quyền nghiệp vụ

Một DSL workflow có thể quy định chỉ người có vai trò MANAGER mới được phê duyệt đơn hàng trên một ngưỡng nhất định. Nếu vai trò được xác định từ cấu hình tĩnh, một phần kiểm tra có thể làm trước. Nếu phụ thuộc người dùng đăng nhập, kiểm tra phải diễn ra tại thời điểm thực thi và dựa trên danh tính đã xác thực.

### 8.6. Ràng buộc đơn vị

Hai giá trị cùng có kiểu số vẫn có thể không tương thích nếu đơn vị khác nhau:

~~~text
distance: 10 km
duration: 30 minutes
~~~

Không thể cộng distance với duration. Một số phép toán có thể tạo kiểu đơn vị mới, chẳng hạn distance chia cho duration tạo vận tốc. DSL có thể dùng dimensional analysis để phát hiện phép toán sai đơn vị trước khi chạy.

### 8.7. Tiền tệ

Money thường gồm số tiền và mã tiền tệ. Cộng 100 VND với 10 USD không nên được cho phép nếu chưa có quy tắc chuyển đổi tỷ giá rõ ràng.

Nếu chuyển đổi tiền tệ phụ thuộc tỷ giá tại thời điểm giao dịch, phép chuyển đổi có thể cần dữ liệu runtime và nguồn tỷ giá được xác định.

## 9. Lỗi ngày giờ và khoảng thời gian

### 9.1. Ngày không hợp lệ

Một literal ngày có thể đúng cú pháp nhưng không tồn tại:

~~~text
date = 2026-02-30
~~~

Nếu DSL biết lịch Gregorian và kiểm tra literal tĩnh, nó có thể báo ngày không hợp lệ ngay khi phân tích.

### 9.2. Múi giờ

Một thời điểm không có múi giờ có thể mơ hồ khi được diễn giải trong nhiều môi trường. DSL cần quy định thời gian không có múi giờ được hiểu theo timezone nào hoặc yêu cầu người dùng cung cấp offset.

### 9.3. Khoảng thời gian đảo ngược

~~~text
between 2026-12-01 and 2026-11-01
~~~

Nếu DSL yêu cầu điểm đầu không muộn hơn điểm cuối, đây là lỗi ràng buộc miền.

### 9.4. Thời gian tương đối

Biểu thức last 30 days phụ thuộc thời điểm đánh giá và timezone. Nó không nhất thiết là lỗi, nhưng compiler cần biết đây là biểu thức động và không nên cố đánh giá như hằng số nếu chưa có đồng hồ hoặc ngữ cảnh thời gian được cung cấp.

### 9.5. Giờ mùa hè và thời điểm không tồn tại

Một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần khi chuyển đổi giờ mùa hè. Nếu DSL hỗ trợ thời gian địa phương, cần định nghĩa cách xử lý những trường hợp này và tạo diagnostic hoặc yêu cầu chính sách rõ ràng.

## 10. Hằng số và biểu thức có thể đánh giá tĩnh

### 10.1. Constant expression

Một biểu thức hằng chỉ phụ thuộc vào những giá trị được biết trong quá trình biên dịch:

~~~text
let maxRetries = 2 + 3
~~~

Compiler có thể tính ra 5. Quá trình này được gọi là constant folding.

### 10.2. Phát hiện lỗi khi đánh giá hằng

~~~text
let invalid = 10 / 0
~~~

Nếu DSL định nghĩa phép chia cho zero là lỗi và cả hai toán hạng đều là hằng, compiler có thể báo lỗi trước khi thực thi.

### 10.3. Không đánh giá quá mức

~~~text
let result = 10 / runtimeValue
~~~

Nếu runtimeValue chưa biết, compiler không thể kết luận phép chia sẽ lỗi. Nó có thể chèn kiểm tra runtime hoặc yêu cầu xử lý lỗi tùy ngữ nghĩa DSL.

### 10.4. Tràn số và độ chính xác

Một biểu thức hằng có thể vượt phạm vi của kiểu số. Compiler cần định nghĩa overflow là lỗi, giá trị bão hòa hay phép toán modulo. Với kiểu Decimal dùng cho tiền, cần quy tắc scale và làm tròn rõ ràng.

### 10.5. Phép tính không thuần

Không nên đánh giá hàm có tác dụng phụ trong quá trình biên dịch chỉ vì đối số trông giống hằng số. Constant evaluation nên giới hạn ở các phép toán thuần và được cho phép rõ ràng.

## 11. Lỗi trong biểu thức điều kiện và logic

### 11.1. Kết hợp giá trị không phải Boolean

~~~text
when customer.age and order.isPaid
~~~

Nếu age là Integer, biểu thức AND không hợp lệ khi toán tử yêu cầu Boolean ở cả hai vế.

### 11.2. Phủ định

~~~text
not order.total
~~~

Nếu total là Money, toán tử not không được áp dụng trừ khi DSL có quy tắc truthiness được định nghĩa. Với DSL nghiệp vụ, yêu cầu Boolean tường minh thường dễ hiểu hơn.

### 11.3. So sánh giữa kiểu không tương thích

~~~text
customer.birthDate > order.total
~~~

Hai kiểu Date và Money không có quan hệ so sánh hợp lệ. Diagnostic nên nêu hai kiểu và toán tử gây lỗi.

### 11.4. So sánh null

Nếu giá trị nullable, phép so sánh thông thường có thể không trả về Boolean theo logic hai giá trị. DSL cần quy định null propagation, three-valued logic hoặc yêu cầu kiểm tra null trước.

### 11.5. Điều kiện luôn đúng hoặc luôn sai

Một điều kiện hằng có thể được nhận diện:

~~~text
when true
then applyDiscount(0.10)
~~~

Điều này không nhất thiết là lỗi. Nhưng compiler có thể cảnh báo rằng điều kiện luôn đúng, khiến quy tắc được áp dụng mọi lần. Warning cần phản ánh rủi ro hoặc sự bất thường, không tự động coi mọi điều kiện hằng là sai.

## 12. Lỗi trong mô hình quy tắc và workflow

### 12.1. Quy tắc thiếu thành phần bắt buộc

Một rule có thể cần ít nhất một điều kiện và một hành động. Nếu AST cho phép parser tạo rule nhưng thiếu phần cần thiết do cú pháp tùy chọn, semantic validation có thể phát hiện cấu trúc chưa đủ ý nghĩa.

### 12.2. Hành động không phù hợp với ngữ cảnh

Một hành động như refund có thể chỉ hợp lệ sau khi payment thành công. Nếu workflow khai báo refund ở trạng thái trước thanh toán, đó là lỗi mô hình hoặc lỗi ràng buộc trạng thái.

### 12.3. Trạng thái không thể đạt tới

Một workflow có thể chứa trạng thái không có đường chuyển đến. Đây có thể là warning hoặc error tùy yêu cầu của DSL. Semantic analyzer có thể dùng đồ thị trạng thái để kiểm tra khả năng tiếp cận.

### 12.4. Trạng thái không có đường thoát

Một trạng thái có thể tạo vòng lặp vô hạn hoặc không có chuyển tiếp kết thúc. Nếu DSL yêu cầu mọi workflow phải có đường kết thúc, hệ thống có thể báo lỗi.

### 12.5. Điều kiện chuyển trạng thái mâu thuẫn

Hai chuyển tiếp từ cùng trạng thái có thể có điều kiện không thể đồng thời đúng hoặc có thể cùng đúng mà không có quy tắc ưu tiên. Trường hợp đầu có thể làm một nhánh không bao giờ xảy ra; trường hợp sau có thể tạo tính không xác định.

### 12.6. Hành động trùng lặp hoặc xung đột

Một quy tắc có thể áp dụng hai hành động không tương thích, chẳng hạn vừa khóa vừa mở cùng một tài khoản trong cùng bước mà không có thứ tự xác định. Semantic validation có thể phát hiện một số xung đột dựa trên hợp đồng hành động.

## 13. Lỗi phụ thuộc dữ liệu và môi trường lúc chạy

### 13.1. Dữ liệu thực tế không đáp ứng giả định

Một chương trình có thể được kiểm tra tĩnh thành công nhưng dữ liệu thực tế thiếu trường, sai định dạng hoặc nằm ngoài miền.

~~~text
let age = customer.age
when age >= 18
then allowPurchase()
~~~

Nếu customer.age là null hoặc dữ liệu đầu vào không có trường age, runtime cần xử lý theo chính sách null và validation dữ liệu.

### 13.2. Tài nguyên không tồn tại

Một tên nguồn dữ liệu có thể hợp lệ theo schema nhưng bảng hoặc file thực tế đã bị xóa. Đây là lỗi môi trường hoặc lỗi tài nguyên lúc chạy, trừ khi compiler có thể truy vấn metadata đáng tin cậy tại thời điểm kiểm tra.

### 13.3. Quyền bị thay đổi

Một người dùng có thể có quyền khi biên dịch nhưng mất quyền trước lúc thực thi. Runtime phải kiểm tra quyền tại thời điểm hành động cần được thực hiện, đặc biệt với thao tác nhạy cảm.

### 13.4. Lỗi dịch vụ bên ngoài

Gọi API, cơ sở dữ liệu hoặc dịch vụ thanh toán có thể thất bại do timeout, lỗi mạng hoặc trạng thái từ chối. Những lỗi này không nhất thiết làm cho DSL sai ngữ nghĩa, nhưng là lỗi thực thi cần được biểu diễn và chẩn đoán.

### 13.5. Phân biệt lỗi chương trình và lỗi dữ liệu

Nếu DSL yêu cầu trường total phải là Money nhưng bản ghi đầu vào chứa String, lỗi có thể thuộc validation dữ liệu. Nếu chương trình cố cộng Money với Customer, lỗi thuộc chương trình. Phân biệt hai nguồn giúp xác định đúng nơi cần sửa.

## 14. Thiết kế diagnostic cho lỗi ngữ nghĩa

### 14.1. Cấu trúc một diagnostic

Một diagnostic hữu ích thường chứa:

- Mã lỗi ổn định.
- Mức độ: error, warning hoặc information.
- Thông điệp ngắn và rõ.
- Vị trí nguồn chính.
- Vị trí liên quan nếu có.
- Kiểu mong đợi và kiểu thực tế nếu lỗi liên quan đến kiểu.
- Gợi ý sửa hoặc tài liệu liên quan.

Ví dụ cấu trúc khái niệm:

~~~text
Diagnostic {
    code: "SEM_TYPE_MISMATCH"
    severity: Error
    message: "Không thể gán String cho biến kiểu Date"
    primarySpan: source:8:24-8:36
    related: []
    expectedType: Date
    actualType: String
}
~~~

### 14.2. Nêu rõ mong đợi và thực tế

Thông báo “type error” không đủ hữu ích. Người dùng cần biết kiểu nào được yêu cầu và kiểu nào thực tế được suy ra.

Ví dụ:

~~~text
Không thể truyền order.customer vào tham số orderId.
Kiểu mong đợi: OrderId
Kiểu thực tế: Customer
~~~

### 14.3. Gắn lỗi với toán tử hoặc biểu thức gây vấn đề

Với biểu thức:

~~~text
order.total + customer
~~~

vị trí lỗi có thể là toán tử + hoặc toán hạng customer tùy chính sách. Diagnostic nên chọn vùng giúp người dùng hiểu phép toán nào không được định nghĩa.

### 14.4. Diagnostic nhiều vị trí

Một lỗi có thể liên quan đến hai hoặc nhiều nơi:

- Khai báo kiểu và nơi sử dụng.
- Tham số hàm và đối số được truyền.
- Hai trường vi phạm một bất biến.
- Hai nhánh điều kiện có kết quả kiểu khác nhau.

Diagnostic nên chỉ ra vị trí chính và các vị trí liên quan thay vì nối tất cả thành một thông báo dài.

### 14.5. Mã lỗi ổn định

Một số mã minh họa:

| Mã | Ý nghĩa |
|---|---|
| SEM_TYPE_MISMATCH | Kiểu thực tế không tương thích kiểu mong đợi |
| SEM_INVALID_OPERATOR | Toán tử không được định nghĩa cho toán hạng |
| SEM_ARGUMENT_COUNT | Sai số lượng đối số |
| SEM_RETURN_MISMATCH | Kiểu trả về không phù hợp |
| SEM_UNINITIALIZED_VALUE | Dùng biến chưa được gán trên mọi đường đi |
| SEM_UNREACHABLE_CODE | Mã không thể được thực thi |
| SEM_DOMAIN_CONSTRAINT | Vi phạm ràng buộc miền |
| SEM_INVALID_RANGE | Khoảng giá trị hoặc thời gian không hợp lệ |
| SEM_UNIT_MISMATCH | Đơn vị đo không tương thích |
| SEM_CONSTANT_EVALUATION | Lỗi khi đánh giá biểu thức hằng |
| SEM_INVALID_STATE_TRANSITION | Chuyển trạng thái không hợp lệ |

Mã lỗi nên độc lập với câu chữ và ngôn ngữ hiển thị để IDE, CLI và CI có thể xử lý ổn định.

### 14.6. Phân biệt error và warning

Không phải mọi bất thường đều khiến chương trình không thể thực thi.

| Mức độ | Cách dùng thường gặp |
|---|---|
| Error | Chương trình không thể được chấp nhận hoặc thực thi an toàn |
| Warning | Cấu trúc hợp lệ nhưng có dấu hiệu bất thường hoặc rủi ro |
| Information | Gợi ý hoặc thông tin giúp hiểu chương trình |

Ví dụ, biến không được sử dụng có thể là warning; gán String cho Date thường là error. Chính sách cụ thể tùy DSL và môi trường triển khai.

## 15. Phục hồi và tránh lỗi dây chuyền

### 15.1. Lỗi gốc và lỗi phụ

Một lỗi ở đầu biểu thức có thể khiến những bước kiểm tra sau không còn đủ thông tin. Ví dụ, nếu tên customer không phân giải được, hệ thống không biết kiểu của customer.address.

Không nên tiếp tục báo hàng loạt lỗi kiểu cho từng thành phần con nếu chúng đều xuất phát từ cùng một tên chưa biết.

### 15.2. Error type

Compiler có thể dùng một kiểu lỗi đặc biệt để đánh dấu biểu thức đã có lỗi. Những phép kiểm tra sau nhận biết kiểu này và tránh phát thêm diagnostic trùng lặp.

~~~text
unknownCustomer.address + 10
~~~

Nếu unknownCustomer không tồn tại, resolver phát một lỗi tên. Các pass sau có thể gán ErrorType cho biểu thức và tiếp tục phân tích phần độc lập.

### 15.3. Tiếp tục kiểm tra phần độc lập

~~~text
let first = 10 + "text"
let second = customer.total
let third = 20 + 30
~~~

Compiler có thể báo lỗi kiểu ở first, lỗi tên hoặc thuộc tính ở second, đồng thời vẫn xác định third có kiểu hợp lệ.

### 15.4. Giới hạn số lỗi

Một chương trình có thể tạo hàng nghìn diagnostic từ cùng một lỗi gốc hoặc dữ liệu sai. Compiler nên có giới hạn hợp lý, nhóm lỗi lặp lại và dừng một pass khi không còn đủ thông tin để tiếp tục an toàn.

### 15.5. Không che giấu lỗi gốc

Việc phục hồi không nên biến một lỗi thật thành thành công giả. Mô hình IR có thể chứa node lỗi để tiếp tục phân tích, nhưng backend không nên thực thi chương trình có lỗi ngữ nghĩa nghiêm trọng trừ khi có chế độ đặc biệt được xác định rõ.

## 16. Phân tích luồng dữ liệu và trạng thái

### 16.1. Definite assignment

Phân tích definite assignment kiểm tra biến đã được gán giá trị trên mọi đường đi trước khi đọc hay chưa.

~~~text
let result: Money
if condition {
    result = order.total
}
return result
~~~

Nếu condition có thể sai, result có đường đi chưa được gán. Semantic analyzer có thể báo lỗi.

### 16.2. Phân tích nhánh

Nếu cả hai nhánh đều gán:

~~~text
let result: Money
if condition {
    result = order.total
} else {
    result = Money.zero()
}
return result
~~~

thì biến được gán trên mọi nhánh theo mô hình điều khiển đơn giản.

### 16.3. Phân tích khả năng null

Một biến có thể được gán null ở một nhánh và giá trị thực ở nhánh khác. Type checker có thể theo dõi trạng thái nullable để cảnh báo khi truy cập mà chưa kiểm tra.

### 16.4. Phân tích trạng thái workflow

Với DSL workflow, trạng thái hiện tại có thể được mô hình hóa thành node trong đồ thị. Semantic analyzer kiểm tra chuyển tiếp, trạng thái kết thúc và những nhánh không thể đạt tới.

### 16.5. Phân tích luồng không phải chứng minh mọi hành vi

Phân tích tĩnh thường dùng mô hình xấp xỉ. Nó có thể cảnh báo bảo thủ hoặc bỏ sót lỗi phụ thuộc môi trường. Diagnostic nên diễn đạt mức độ chắc chắn phù hợp, tránh tuyên bố chương trình chắc chắn sai khi hệ thống chỉ phát hiện một khả năng rủi ro.

## 17. Kiểm tra ràng buộc miền và validation

### 17.1. Validation tĩnh

Nếu giá trị được biết trước:

~~~text
discountRate = 1.5
~~~

và DSL giới hạn tỷ lệ trong khoảng từ 0 đến 1, compiler có thể phát hiện ngay.

### 17.2. Validation lúc chạy

Nếu giá trị đến từ input:

~~~text
discountRate = request.discountRate
~~~

thì cần kiểm tra dữ liệu thực tế trước khi áp dụng. Một schema có thể mô tả giới hạn, còn runtime thực hiện validation trên giá trị nhận được.

### 17.3. Bất biến đối tượng

Một đối tượng miền có thể có bất biến:

~~~text
type Transfer {
    source: Account
    destination: Account
    amount: Money

    invariant source.id != destination.id
    invariant amount > Money.zero()
}
~~~

Hai tài khoản phải khác nhau và số tiền phải dương. Một đối tượng có thể đúng kiểu ở mọi trường nhưng vẫn vi phạm bất biến tổng thể.

### 17.4. Bất biến liên quan đến dữ liệu bên ngoài

Một quy tắc có thể yêu cầu khách hàng tồn tại hoặc tài khoản đang hoạt động. Nếu thông tin được lưu trong hệ thống khác, compiler có thể không xác minh được khi biên dịch. Runtime cần truy vấn hoặc xác thực bằng nguồn dữ liệu có thẩm quyền.

### 17.5. Phân biệt validation và authorization

Validation xác nhận dữ liệu hoặc cấu trúc có đáp ứng quy tắc hay không. Authorization xác nhận chủ thể có quyền thực hiện hành động hay không. Một DSL có thể mô tả cả hai, nhưng kiểm tra quyền phải dựa trên danh tính và chính sách có thẩm quyền tại thời điểm thích hợp.

## 18. Diagnostic trong IDE, CLI và language server

### 18.1. Hiển thị trong editor

IDE có thể gạch chân biểu thức sai, hiển thị kiểu mong đợi và kiểu thực tế khi rê chuột, đồng thời cung cấp quick fix.

### 18.2. Quick fix có căn cứ

Ví dụ, nếu DSL có một phép chuyển đổi an toàn duy nhất, IDE có thể đề xuất thêm chuyển đổi tường minh. Nếu có nhiều cách chuyển đổi hoặc việc sửa có thể mất dữ liệu, IDE nên hiển thị lựa chọn và giải thích thay vì tự động thay đổi.

### 18.3. Điều hướng đến định nghĩa kiểu

Khi báo kiểu không tương thích, IDE có thể liên kết đến khai báo kiểu hoặc chữ ký hàm. Điều này giúp người dùng tìm ra hợp đồng mà biểu thức phải tuân theo.

### 18.4. Diagnostic dạng máy đọc được

Một công cụ có thể xuất cấu trúc JSON:

~~~json
{
  "code": "SEM_TYPE_MISMATCH",
  "severity": "error",
  "message": "Không thể gán String cho Date",
  "range": {
    "start": { "line": 7, "character": 22 },
    "end": { "line": 7, "character": 35 }
  },
  "expectedType": "Date",
  "actualType": "String"
}
~~~

Đây là định dạng minh họa. Nếu công cụ tích hợp Language Server Protocol, nó có thể ánh xạ thông tin sang cấu trúc Diagnostic của giao thức.

### 18.5. Chẩn đoán trong CI

CI có thể thu thập diagnostic theo mã, mức độ, file và vị trí. Một số warning có thể được cấu hình thành lỗi trong quy trình phát hành. Tuy nhiên, chính sách CI không nên thay đổi ngữ nghĩa cơ bản của chương trình.

## 19. Thiết kế thông báo lỗi hướng người dùng

### 19.1. Tránh thông báo quá kỹ thuật

Thông báo như “No applicable method found” hoặc “Type inference failed” có thể hữu ích cho người phát triển compiler nhưng chưa đủ cho người viết DSL.

Nên nói rõ thao tác miền đang được thực hiện và điều kiện không được đáp ứng.

### 19.2. Nêu kiểu mong đợi và kiểu thực tế

Ví dụ:

~~~text
Tham số amount của calculateTax cần kiểu Money,
nhưng biểu thức order.quantity có kiểu Integer.
~~~

### 19.3. Nêu ràng buộc cụ thể

~~~text
Giá trị discountRate là 1.25.
Miền cho phép: từ 0 đến 1.
~~~

Thông điệp này tốt hơn “Invalid value” vì người dùng biết giới hạn và giá trị gây lỗi.

### 19.4. Giải thích khi lỗi phụ thuộc ngữ cảnh

~~~text
Hành động refund chỉ được phép khi payment.status là PAID.
Trạng thái hiện tại được xác định là PENDING.
~~~

Nếu trạng thái có thể thay đổi lúc chạy, thông báo cần nói đây là kiểm tra runtime hoặc điều kiện tại thời điểm đánh giá, không khẳng định lỗi tĩnh nếu không đủ cơ sở.

### 19.5. Bản địa hóa

Mã lỗi nên ổn định, còn thông điệp có thể được dịch. Tên kiểu, tên trường và biểu thức người dùng viết nên được giữ nguyên để họ có thể đối chiếu với tài liệu nguồn.

### 19.6. Vị trí và đơn vị chỉ số

Nếu nguồn có Unicode, compiler và editor cần thống nhất cách tính offset. Một thành phần có thể đếm byte UTF-8, thành phần khác đếm UTF-16 code unit. Nếu không chuyển đổi đúng, vùng lỗi có thể bị gạch chân sai vị trí.

## 20. Lỗi ngữ nghĩa trong DSL có đơn vị đo

### 20.1. Kiểu số chưa đủ để mô tả ý nghĩa

Một giá trị Decimal có thể đại diện cho tiền, phần trăm, trọng lượng hoặc tỷ lệ. Nếu DSL chỉ dùng kiểu số chung, nhiều phép toán sai miền có thể vẫn vượt qua kiểm tra kiểu.

### 20.2. Kiểm tra thứ nguyên

Có thể gắn đơn vị vào kiểu:

~~~text
Distance
Duration
Speed
~~~

Phép toán hợp lệ có thể được mô tả:

~~~text
Distance / Duration -> Speed
Speed * Duration -> Distance
~~~

Phép cộng Distance với Duration bị từ chối vì thứ nguyên không tương thích.

### 20.3. Chuyển đổi đơn vị

Chuyển 1 km thành 1000 m có thể là chuyển đổi xác định. Chuyển USD sang VND cần tỷ giá và thời điểm tham chiếu. Hai loại chuyển đổi có đặc tính khác nhau và cần hợp đồng rõ.

### 20.4. Làm tròn và độ chính xác

Khi tính tiền hoặc phần trăm, cần xác định scale, chế độ làm tròn và thời điểm làm tròn. Hai biểu thức có cùng kiểu nhưng khác chính sách làm tròn có thể tạo kết quả nghiệp vụ khác nhau.

## 21. Lỗi ngữ nghĩa trong DSL truy vấn và dữ liệu

### 21.1. Trường không tồn tại trong schema

Một truy vấn có thể parse đúng nhưng tham chiếu đến trường không có trong schema dữ liệu:

~~~text
select customer.fullName from Customers
~~~

Nếu schema chỉ có firstName và lastName, hệ thống có thể báo trường fullName không tồn tại và gợi ý cách ghép trường nếu DSL hỗ trợ.

### 21.2. So sánh kiểu không tương thích

~~~text
where order.createdAt > 100
~~~

Nếu createdAt là Date, so sánh với Integer không hợp lệ nếu không có quy tắc chuyển đổi.

### 21.3. Hàm tổng hợp không áp dụng được

~~~text
sum(customer.name)
~~~

Nếu sum chỉ nhận kiểu số, truyền String là lỗi kiểu. Một diagnostic tốt chỉ rõ sum yêu cầu kiểu số và trường name có kiểu String.

### 21.4. Nhóm và phép tổng hợp

Một truy vấn có thể yêu cầu mọi trường không tổng hợp phải xuất hiện trong nhóm. Đây là ràng buộc ngữ nghĩa của DSL truy vấn, dù từng trường đều tồn tại và đúng kiểu.

### 21.5. Schema thay đổi

Nếu schema dữ liệu được cập nhật sau khi DSL đã được biên dịch, một tham chiếu trước đây hợp lệ có thể trở thành không hợp lệ. Hệ thống cần xác định thời điểm kiểm tra schema, cache metadata và cách phát hiện phiên bản schema không còn phù hợp.

## 22. Kiểm thử chẩn đoán lỗi ngữ nghĩa

### 22.1. Kiểm thử từng loại lỗi

Với mỗi quy tắc ngữ nghĩa, cần có ví dụ hợp lệ và không hợp lệ. Chẳng hạn:

- Gán kiểu tương thích và không tương thích.
- Gọi hàm đúng và sai chữ ký.
- Biến được gán trên mọi đường đi và chưa được gán.
- Giá trị trong và ngoài miền.
- Phép toán đúng và sai đơn vị.
- Workflow có và không có đường kết thúc.

### 22.2. Kiểm thử vị trí nguồn

Không chỉ kiểm tra mã lỗi. Cần xác nhận source span trỏ đúng biểu thức, toán tử, tham số hoặc literal gây lỗi.

### 22.3. Kiểm thử không tạo lỗi dây chuyền

Với một tên chưa phân giải hoặc biểu thức có ErrorType, xác nhận compiler không tạo hàng loạt diagnostic phụ cho mọi node con.

### 22.4. Kiểm thử nhiều lỗi độc lập

Một chương trình có thể chứa nhiều lỗi không phụ thuộc nhau. Compiler nên phát hiện chúng trong cùng lượt phân tích khi có thể.

### 22.5. Kiểm thử ranh giới tĩnh và động

Giá trị hằng sai miền nên bị phát hiện tĩnh nếu DSL cam kết kiểm tra. Giá trị chỉ biết lúc chạy cần được kiểm tra tại runtime. Không nên báo lỗi tĩnh khi chưa đủ thông tin.

### 22.6. Kiểm thử diagnostic ổn định

Mã lỗi, mức độ và cấu trúc dữ liệu nên ổn định qua những thay đổi câu chữ hoặc bản dịch thông báo. Điều này giúp IDE và CI dựa vào hợp đồng máy đọc được.

## 23. Những sai lầm thường gặp

### 23.1. Coi mọi lỗi sau parser là lỗi kiểu

Ràng buộc miền, luồng điều khiển, quyền và trạng thái cũng có thể gây lỗi ngữ nghĩa. Cần phân loại theo nguyên nhân thực tế.

### 23.2. Đẩy mọi kiểm tra sang runtime

Những lỗi có thể phát hiện tĩnh nên được báo sớm. Nếu chờ đến runtime, người dùng có thể chỉ phát hiện lỗi khi một quy tắc hiếm gặp được kích hoạt.

### 23.3. Cố kiểm tra tĩnh dữ liệu chưa biết

Ngược lại, không nên giả định compiler biết giá trị phụ thuộc database, đồng hồ hoặc dịch vụ bên ngoài. Cần dùng validation runtime cho những điều kiện đó.

### 23.4. Cho phép chuyển đổi ngầm quá rộng

Chuyển đổi tự động có thể làm mất dữ liệu, thay đơn vị hoặc che giấu lỗi nghiệp vụ. Nên chỉ cho phép chuyển đổi an toàn và có quy tắc rõ.

### 23.5. Báo lỗi phụ thay vì lỗi gốc

Nếu tên hoặc kiểu gốc đã lỗi, các lỗi tiếp theo có thể chỉ là hệ quả. Cần dùng ErrorSymbol hoặc ErrorType để kiểm soát diagnostic.

### 23.6. Diagnostic chỉ nêu mã nội bộ

Người dùng cần hiểu biểu thức nào sai và sửa ra sao. Mã lỗi nên đi kèm thông điệp và thông tin ngữ cảnh.

### 23.7. Coi warning luôn vô hại

Một warning về workflow không có đường kết thúc hoặc điều kiện luôn đúng có thể ảnh hưởng đáng kể đến nghiệp vụ. Cần đặt mức độ dựa trên hậu quả và hợp đồng của DSL.

## 24. Quy trình xây dựng semantic analyzer

Một quy trình triển khai có thể gồm:

1. **Định nghĩa ngữ nghĩa:** mô tả hành vi của từng cấu trúc DSL và các quy tắc miền.
2. **Xác định dữ liệu cần kiểm tra:** kiểu, khai báo, trạng thái, đơn vị, giới hạn và quyền.
3. **Tạo mô hình khai báo:** thu thập symbol, scope, type và chữ ký.
4. **Phân giải tên:** liên kết tham chiếu với khai báo.
5. **Suy luận và kiểm tra kiểu:** xác định kiểu biểu thức và tính hợp lệ của phép toán.
6. **Kiểm tra luồng điều khiển:** definite assignment, return, unreachable code và trạng thái.
7. **Kiểm tra ràng buộc miền:** giá trị, bất biến, đơn vị và điều kiện nghiệp vụ.
8. **Phân loại lỗi:** tách lỗi gốc, lỗi phụ, warning và lỗi runtime.
9. **Tạo diagnostic có cấu trúc:** mã, mức độ, vị trí, kiểu mong đợi và thông tin liên quan.
10. **Tạo mô hình đã kiểm tra:** chỉ chuyển sang backend khi những điều kiện cần thiết đã được đáp ứng.

## 25. Ví dụ tổng hợp: quy tắc ưu đãi đơn hàng

Giả sử DSL có các kiểu:

~~~text
Order
Customer
Money
Decimal
Boolean
~~~

Một quy tắc:

~~~text
rule MemberDiscount {
    when customer.tier is GOLD
         and order.total >= 2000000 VND
    then applyDiscount(order, 0.10)
}
~~~

Giả sử chữ ký hàm là:

~~~text
function applyDiscount(order: Order, rate: Decimal): Money
~~~

### 25.1. Trường hợp hợp lệ

Nếu customer và order được khai báo đúng kiểu, tier là thuộc tính hợp lệ, total là Money, hằng 2000000 có đơn vị VND và applyDiscount nhận đúng hai đối số, quy tắc có thể vượt qua các kiểm tra ngữ nghĩa tương ứng.

### 25.2. Sai kiểu so sánh

~~~text
order.total >= customer.name
~~~

Nếu total là Money và name là String, phép so sánh không được định nghĩa. Diagnostic nên nêu hai kiểu và toán tử gây lỗi.

### 25.3. Sai ràng buộc miền

~~~text
applyDiscount(order, 1.50)
~~~

Nếu tỷ lệ hợp lệ nằm trong khoảng 0 đến 1, giá trị 1.50 vi phạm giới hạn. Nếu đây là hằng số, lỗi có thể được phát hiện tĩnh.

### 25.4. Sai đơn vị

~~~text
order.total >= 2000 kg
~~~

Hai vế không cùng thứ nguyên. Đây là lỗi đơn vị, dù cả hai giá trị có thể được lưu bằng số.

### 25.5. Sai trạng thái

Nếu applyDiscount chỉ được phép trước khi đơn hàng đã thanh toán, nhưng quy tắc được cấu hình cho trạng thái SHIPPED, semantic validation có thể phát hiện xung đột với hợp đồng hành động.

### 25.6. Giá trị phụ thuộc runtime

Nếu tỷ lệ giảm giá được đọc từ cấu hình bên ngoài, compiler có thể không biết giá trị thực. Runtime phải xác thực tỷ lệ trước khi áp dụng và trả lỗi miền nếu cấu hình vượt giới hạn.

Ví dụ này cho thấy semantic analyzer cần kết hợp hệ kiểu, đơn vị, ràng buộc miền và ngữ cảnh trạng thái. Không một bước kiểm tra đơn lẻ nào thay thế được toàn bộ các quy tắc đó.

## 26. Câu hỏi tự đánh giá

1. Vì sao một chương trình đúng cú pháp vẫn có thể sai ngữ nghĩa?
2. Phân biệt lỗi kiểu với lỗi ràng buộc miền.
3. Những lỗi nào có thể phát hiện tĩnh và những lỗi nào cần kiểm tra lúc chạy?
4. Vì sao chuyển đổi ngầm có thể gây lỗi nghiệp vụ?
5. Definite assignment kiểm tra điều gì?
6. ErrorType giúp tránh lỗi dây chuyền như thế nào?
7. Vì sao cùng kiểu Decimal vẫn có thể không tương thích về đơn vị?
8. Phân biệt validation dữ liệu với authorization.
9. Diagnostic lỗi ngữ nghĩa nên nêu những thông tin nào?
10. Khi nào compiler nên tạo IR hoặc cho phép backend thực thi?

## Kết luận

Lỗi ngữ nghĩa xuất hiện khi cấu trúc DSL đã được phân tích nhưng ý nghĩa của nó không phù hợp với hệ kiểu, quy tắc ngôn ngữ hoặc miền nghiệp vụ. Lỗi có thể liên quan đến kiểu dữ liệu, chuyển đổi, chữ ký hàm, luồng điều khiển, giá trị chưa khởi tạo, đơn vị, ngày giờ, bất biến và trạng thái workflow. Một số lỗi có thể được phát hiện tĩnh; những lỗi phụ thuộc dữ liệu hoặc môi trường cần được kiểm tra lúc chạy.

Semantic analyzer cần phân giải tên, xác định kiểu, kiểm tra ràng buộc và tạo diagnostic có cấu trúc. Thông báo tốt nêu rõ vị trí, kiểu hoặc điều kiện mong đợi, giá trị thực tế và cách khắc phục. Cơ chế phục hồi cần tránh lỗi dây chuyền nhưng vẫn giữ trạng thái lỗi để backend không thực thi nhầm chương trình chưa hợp lệ. Khi các quy tắc ngữ nghĩa được định nghĩa rõ và kiểm tra ở đúng thời điểm, DSL trở nên dễ hiểu, an toàn và dự đoán được hơn.

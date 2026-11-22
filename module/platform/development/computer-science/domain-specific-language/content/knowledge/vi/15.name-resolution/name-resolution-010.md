# Chẩn đoán tên không hợp lệ trong DSL

Trong ngôn ngữ đặc tả miền (Domain-Specific Language, DSL), người dùng thường đặt tên cho biến, quy tắc, kiểu dữ liệu, hàm, trường, module hoặc tài nguyên miền. Khi một tên xuất hiện trong chương trình, hệ thống phải xác định tên đó chỉ đến đối tượng nào. Quá trình này được gọi là **phân giải tên** (*name resolution*).

Một tên có thể đúng về mặt ký tự nhưng vẫn không hợp lệ trong ngữ cảnh sử dụng. Ví dụ, tên có thể chưa được khai báo, nằm ngoài phạm vi nhìn thấy, bị trùng với một khai báo khác, tham chiếu đến sai loại đối tượng hoặc mơ hồ vì nhiều đối tượng cùng phù hợp. Một số tên còn sai ngay từ bước phân tích từ vựng, chẳng hạn chứa ký tự không được phép hoặc vi phạm quy tắc đặt tên.

**Chẩn đoán tên không hợp lệ** (*invalid-name diagnostics*) là cơ chế phát hiện, phân loại và giải thích những vấn đề đó cho người dùng. Chẩn đoán tốt giúp người viết biết tên nào có vấn đề, lỗi xảy ra ở đâu, vì sao tên không được chấp nhận và có thể sửa bằng cách nào. Chẩn đoán cũng cần giúp compiler tiếp tục phân tích những phần độc lập để có thể báo nhiều lỗi hữu ích trong một lần chạy.

## 1. Tên và phân giải tên trong DSL

### 1.1. Tên là gì?

Tên (*name*) là ký hiệu dùng để tham chiếu đến một khai báo hoặc thành phần trong mô hình. Tùy DSL, tên có thể đại diện cho:

- Biến hoặc hằng số.
- Kiểu dữ liệu hoặc type alias.
- Hàm, toán tử hoặc bộ chuyển đổi.
- Quy tắc, workflow hoặc hành động.
- Thuộc tính của một đối tượng miền.
- Module, namespace hoặc package.
- Bảng, trường dữ liệu hoặc nguồn dữ liệu.
- Tham số generic hoặc tham số hàm.

Ví dụ:

~~~text
let orderTotal = order.total

rule WeekendDiscount {
    when customer.tier is GOLD
    then applyDiscount(orderTotal)
}
~~~

Trong ví dụ, orderTotal, order, total, WeekendDiscount, customer, tier và applyDiscount đều là những tên cần được hiểu theo các quy tắc khai báo và phạm vi của DSL.

### 1.2. Phân giải tên là gì?

Phân giải tên là quá trình tìm đối tượng mà một tên tham chiếu đến. Bộ phân giải thường sử dụng:

- Văn bản tên và cấu trúc định danh.
- Phạm vi hiện tại (scope).
- Các khai báo có hiệu lực trong phạm vi đó.
- Namespace hoặc module được import.
- Loại đối tượng mà ngữ cảnh đang yêu cầu.
- Quy tắc che khuất tên và ưu tiên tra cứu.

Ví dụ, trong biểu thức:

~~~text
customer.address.city
~~~

hệ thống có thể phải phân giải lần lượt customer, sau đó xác định kiểu của nó, tìm thuộc tính address trong kiểu đó và cuối cùng tìm city trong kiểu của address.

Nếu không tìm thấy một thành phần ở bất kỳ bước nào, hệ thống cần chỉ ra chính xác thành phần gây lỗi. Một thông báo chung như “không phân giải được biểu thức” sẽ không đủ hữu ích.

### 1.3. Tên hợp lệ phụ thuộc vào ngữ cảnh

Một tên có thể hợp lệ ở vị trí này nhưng không hợp lệ ở vị trí khác.

Ví dụ:

~~~text
type Customer

let customer: Customer
~~~

Customer hợp lệ ở vị trí yêu cầu kiểu. Nhưng nếu một DSL có cú pháp gọi hàm và người dùng viết:

~~~text
Customer()
~~~

thì việc có tìm thấy kiểu Customer chưa đủ để kết luận lời gọi hợp lệ. Ngữ cảnh có thể yêu cầu một hàm hoặc constructor có thể gọi được.

Vì vậy, chẩn đoán tên cần phân biệt “không tìm thấy tên” với “đã tìm thấy tên nhưng không đúng loại đối tượng cần dùng”.

## 2. Các lớp lỗi liên quan đến tên

Tên không hợp lệ có thể được phát hiện ở nhiều giai đoạn. Phân loại rõ giúp hệ thống đưa ra thông báo chính xác và tránh gộp mọi trường hợp vào một lỗi chung.

| Nhóm lỗi | Ý nghĩa | Ví dụ |
|---|---|---|
| Lỗi từ vựng | Chuỗi ký tự không tạo thành định danh hợp lệ | customer-name trong DSL không cho phép dấu gạch ngang |
| Tên chưa khai báo | Không có khai báo phù hợp trong phạm vi tra cứu | Dùng customerTier khi chưa khai báo |
| Tên trùng | Có nhiều khai báo xung đột trong cùng phạm vi | Khai báo hai biến cùng tên trong một block |
| Tên mơ hồ | Nhiều khai báo đều phù hợp với một tham chiếu | Hai module import cùng tên format |
| Tên không truy cập được | Khai báo tồn tại nhưng không hiển thị ở ngữ cảnh hiện tại | Gọi thành phần private từ module khác |
| Sai namespace | Tên được viết với đường dẫn namespace không hợp lệ | finance.tax.rate khi module finance không có tax |
| Sai loại đối tượng | Tên tồn tại nhưng không đúng loại mà vị trí đó yêu cầu | Dùng biến như một kiểu dữ liệu |
| Sai chữ ký | Tên hàm tồn tại nhưng không có overload phù hợp | Gọi round với số lượng đối số không hợp lệ |
| Tên dành riêng | Tên xung đột với từ khóa hoặc tên hệ thống không được phép dùng | Khai báo biến tên when |
| Sai chuẩn hóa hoặc ký tự | Tên có biểu diễn Unicode hoặc ký tự gây nhầm lẫn | Hai định danh nhìn giống nhau nhưng khác chuỗi chuẩn hóa |

Không phải mọi DSL đều có đủ các nhóm trên. Một ngôn ngữ nhỏ có thể chỉ cần lỗi từ vựng, chưa khai báo và khai báo trùng. Một DSL có module, plugin và hệ kiểu phong phú thường cần nhiều loại chẩn đoán hơn.

## 3. Lỗi định danh ở bước từ vựng

### 3.1. Quy tắc định danh

Trước khi phân giải, lexer cần xác định chuỗi ký tự có phải một định danh hợp lệ hay không. Một quy tắc đơn giản có thể là:

~~~text
identifier = letter, { letter | digit | "_" } ;
~~~

Với quy tắc này, tên bắt đầu bằng chữ cái và phần tiếp theo có thể gồm chữ cái, chữ số hoặc dấu gạch dưới.

Ví dụ hợp lệ:

~~~text
customer
customer2
order_total
DiscountPolicy
~~~

Ví dụ không hợp lệ theo quy tắc trên:

~~~text
2customer
order-total
customer name
~~~

Thông báo lỗi nên giải thích quy tắc bị vi phạm, ví dụ: “Tên định danh không được bắt đầu bằng chữ số” thay vì chỉ báo “token không hợp lệ”.

### 3.2. Ký tự đặc biệt và dấu phân cách

Một DSL có thể cho phép một số ký tự đặc biệt trong tên, chẳng hạn dấu gạch ngang hoặc dấu chấm. Tuy nhiên, nếu dấu chấm cũng dùng để truy cập thuộc tính hoặc phân cách namespace, lexer và parser phải có quy tắc phân biệt rõ.

Ví dụ:

~~~text
customer.address
~~~

Có thể là một tên định danh có phân cấp, hoặc là phép truy cập thuộc tính address trên đối tượng customer. Chẩn đoán cần dựa trên cấu trúc cú pháp đã được xác định, không tự đoán ý định chỉ từ chuỗi ký tự.

### 3.3. Từ khóa dành riêng

Một số từ được dành riêng cho cú pháp:

~~~text
rule
when
then
type
function
import
~~~

Nếu người dùng khai báo:

~~~text
let when = 10
~~~

parser có thể từ chối vì when là từ khóa. Diagnostic nên nêu tên từ khóa và có thể gợi ý tên thay thế như whenValue nếu phù hợp.

Một DSL có thể dùng từ khóa theo ngữ cảnh, nghĩa là một từ chỉ là từ khóa ở một vị trí nhất định. Khi đó, thông báo lỗi cần phản ánh đúng ngữ cảnh thay vì tuyên bố từ đó luôn bị cấm.

### 3.4. Unicode và ký tự nhìn giống nhau

Nếu DSL hỗ trợ Unicode trong định danh, cần quy định:

- Những nhóm ký tự Unicode nào được phép.
- Có phân biệt chữ hoa và chữ thường không.
- Chuỗi được chuẩn hóa theo dạng nào.
- Cách xử lý ký tự kết hợp.
- Có chấp nhận ký tự vô hình hoặc ký tự điều khiển không.

Hai tên có thể nhìn giống nhau trên màn hình nhưng có chuỗi mã khác nhau. Ví dụ, một chữ cái có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cái cộng dấu kết hợp. Nếu không có quy tắc chuẩn hóa, người dùng có thể khó nhận ra vì sao hai tên không trùng nhau.

Một số ký tự đồng hình (*homoglyph*) trong các bảng chữ cái khác nhau cũng có thể tạo tên trông giống tên chuẩn. Với DSL có quyền truy cập dữ liệu hoặc hành động quan trọng, hệ thống nên cảnh báo hoặc hạn chế những tên dễ gây nhầm lẫn.

### 3.5. Chẩn đoán ở giai đoạn lexer

Lexer thường có vị trí nguồn chính xác cho token lỗi. Một diagnostic nên chứa:

- Mã lỗi ổn định, ví dụ LEX_INVALID_IDENTIFIER.
- Vị trí bắt đầu và kết thúc của chuỗi lỗi.
- Nội dung tên đã đọc được nếu có.
- Quy tắc định danh liên quan.
- Gợi ý sửa khi có thể xác định chắc chắn.

Nếu lexer có thể phục hồi, nó nên bỏ qua phần token lỗi hoặc tạo token lỗi có kiểm soát để parser tiếp tục xử lý phần còn lại.

## 4. Tên chưa được khai báo

### 4.1. Khái niệm

Tên chưa khai báo (*unresolved name* hoặc *undefined name*) xảy ra khi hệ thống không tìm thấy khai báo phù hợp trong tất cả phạm vi tra cứu được phép.

Ví dụ:

~~~text
let total = order.amount
let tax = taxRate * total
~~~

Nếu taxRate chưa được khai báo, hệ thống cần báo tên này chưa được định nghĩa.

### 4.2. Phân biệt chưa khai báo với không truy cập được

Hai trường hợp thường bị nhầm:

- Chưa khai báo: không có đối tượng phù hợp trong tập khai báo mà hệ thống biết.
- Không truy cập được: có đối tượng phù hợp nhưng quy tắc visibility không cho phép dùng tại đây.

Ví dụ, nếu finance.taxRate tồn tại nhưng là private, việc truy cập từ module bán hàng nên được chẩn đoán là lỗi quyền truy cập, không phải tên không tồn tại. Sự phân biệt này giúp người dùng biết cần khai báo thêm hay thay đổi phạm vi truy cập.

### 4.3. Tên chưa khai báo do sai chính tả

Một lỗi thường gặp:

~~~text
let discount = customer.discoutRate
~~~

Trong schema, thuộc tính có thể là discountRate. Hệ thống có thể đề xuất tên gần giống:

~~~text
Không tìm thấy thuộc tính "discoutRate" trên kiểu Customer.
Có phải bạn muốn dùng "discountRate"?
~~~

Gợi ý chỉ nên xuất hiện khi có ứng viên đủ gần và đúng ngữ cảnh. Nếu có nhiều ứng viên tương đương, hãy liệt kê một số lựa chọn thay vì tự chọn một tên.

### 4.4. Tra cứu theo phạm vi

Khi tìm tên, hệ thống thường kiểm tra phạm vi hiện tại rồi lần lượt đến phạm vi cha hoặc các namespace được import.

~~~text
module sales {
    let taxRate = 0.08

    function calculate(order) {
        return order.total * taxRate
    }
}
~~~

Trong hàm calculate, tên taxRate được tìm thấy ở phạm vi module nếu quy tắc của DSL cho phép tham chiếu biến module từ bên trong hàm.

Nếu không tìm thấy tên ở bất kỳ phạm vi hợp lệ nào, diagnostic nên mô tả nơi tra cứu có liên quan, chẳng hạn “Không tìm thấy taxRate trong hàm hoặc module sales”.

## 5. Khai báo trùng tên

### 5.1. Trùng trong cùng phạm vi

Khai báo trùng (*duplicate declaration*) xảy ra khi một phạm vi có nhiều khai báo cùng tên mà quy tắc DSL không cho phép.

~~~text
let discountRate = 0.10
let discountRate = 0.15
~~~

Diagnostic hữu ích nên chỉ ra cả khai báo mới và khai báo trước:

~~~text
Tên "discountRate" đã được khai báo trong phạm vi này.
Khai báo đầu tiên: dòng 1.
Khai báo trùng: dòng 2.
~~~

Vị trí của khai báo đầu tiên giúp người dùng tìm nơi xung đột và quyết định nên đổi tên hay cập nhật khai báo hiện có.

### 5.2. Khai báo trùng giữa các loại tên

Một DSL có thể cho phép hoặc cấm một biến và một hàm cùng tên. Cần định nghĩa namespace của từng loại khai báo.

Ví dụ, nếu kiểu, hàm và biến nằm trong các namespace riêng, các tên giống nhau có thể không xung đột. Nếu chúng cùng nằm trong một namespace, hệ thống cần báo lỗi hoặc có quy tắc phân giải rõ ràng.

Không nên để kết quả phụ thuộc vào thứ tự parser gặp khai báo.

### 5.3. Trùng tên trong module và import

Hai module có thể cùng xuất một tên:

~~~text
import sales.format
import finance.format

let result = format(value)
~~~

Nếu cả hai hàm đều được đưa vào cùng một namespace không có alias, lời gọi format có thể mơ hồ. Người dùng có thể giải quyết bằng tên đầy đủ:

~~~text
sales.format(value)
finance.format(value)
~~~

Hoặc khai báo alias:

~~~text
import sales.format as formatSales
import finance.format as formatMoney
~~~

Diagnostic cần cho biết những khai báo nào xung đột và đưa ra cách phân biệt.

### 5.4. Cho phép che khuất tên hay không?

Một số ngôn ngữ cho phép khai báo bên trong che khuất khai báo bên ngoài:

~~~text
let rate = 0.05

function calculate() {
    let rate = 0.10
    return rate
}
~~~

Trong hàm, rate chỉ biến cục bộ. Đây là shadowing, không nhất thiết là lỗi.

DSL cần quy định shadowing có được phép không, có cần cảnh báo không và cách người dùng truy cập tên ở phạm vi ngoài. Nếu shadowing bị cấm, diagnostic nên nói rõ khai báo nào bị che khuất và tại sao.

## 6. Tên mơ hồ

### 6.1. Khi nào tên mơ hồ?

Tên mơ hồ (*ambiguous name*) xảy ra khi có từ hai khai báo trở lên cùng phù hợp với một tham chiếu và quy tắc phân giải không thể chọn duy nhất.

Ví dụ:

~~~text
import sales.discount
import loyalty.discount

apply discount to order
~~~

Nếu cả hai module đều cung cấp một đối tượng tên discount và DSL không có quy tắc ưu tiên, tham chiếu này mơ hồ.

### 6.2. Khác với khai báo trùng

Khai báo trùng là xung đột trong nơi định nghĩa. Tên mơ hồ là xung đột tại nơi sử dụng do nhiều ứng viên cùng phù hợp.

Một chương trình có thể chứa nhiều khai báo cùng tên trong các namespace khác nhau mà hoàn toàn hợp lệ. Lỗi chỉ xuất hiện khi người dùng tham chiếu bằng một tên ngắn không đủ để xác định đối tượng.

### 6.3. Diagnostic cần liệt kê ứng viên

Ví dụ:

~~~text
Tham chiếu "discount" không xác định được duy nhất.
Các ứng viên:
  - sales.discount
  - loyalty.discount
Hãy dùng tên đầy đủ hoặc import một tên bằng alias.
~~~

Nên giới hạn danh sách nếu có quá nhiều ứng viên và sắp xếp theo mức độ liên quan. Tuy nhiên, không được bỏ qua ứng viên có thể làm thay đổi kết quả.

### 6.4. Không giải quyết mơ hồ bằng thứ tự ngẫu nhiên

Chọn ứng viên đầu tiên theo thứ tự import hoặc thứ tự quét thư mục làm cho kết quả khó dự đoán. Một thay đổi không liên quan trong cấu hình có thể khiến chương trình gọi sang hàm khác.

Nếu DSL có quy tắc ưu tiên, ví dụ local trước imported, quy tắc đó phải được định nghĩa công khai và ổn định. Khi vẫn còn nhiều ứng viên cùng mức ưu tiên, hệ thống nên báo lỗi.

## 7. Tên tồn tại nhưng không truy cập được

### 7.1. Phạm vi truy cập

Một khai báo có thể tồn tại nhưng chỉ được dùng trong một phạm vi:

- private: chỉ trong thành phần sở hữu.
- internal: trong một module hoặc package.
- public: được phép truy cập từ bên ngoài theo hợp đồng.

Đây là các mức minh họa; DSL có thể dùng từ khóa khác hoặc chỉ có một số mức.

Ví dụ:

~~~text
module finance {
    private function internalTaxRule(amount) {
        ...
    }
}

module sales {
    let tax = finance.internalTaxRule(order.total)
}
~~~

Nếu internalTaxRule là private, tham chiếu từ module sales không hợp lệ.

### 7.2. Chẩn đoán quyền truy cập

Thông báo nên nói:

- Tên đã tìm thấy.
- Vị trí khai báo.
- Mức truy cập hiện tại.
- Phạm vi đang thực hiện truy cập.
- Cách sửa hợp lệ nếu có.

Ví dụ: “finance.internalTaxRule được khai báo private trong module finance và không thể gọi từ module sales. Hãy dùng API công khai được module finance cung cấp.”

### 7.3. Không làm lộ thông tin nhạy cảm

Trong môi trường nhiều người dùng hoặc nhiều module có quyền riêng, việc tiết lộ tên khai báo không truy cập được cũng có thể làm lộ cấu trúc nội bộ.

Chính sách chẩn đoán cần cân bằng giữa khả năng sửa lỗi và bảo mật. Có thể hiển thị thông báo tổng quát cho người không có quyền xem metadata, trong khi công cụ quản trị có thêm chi tiết.

## 8. Tên sai loại đối tượng

### 8.1. Namespace theo loại tên

Một DSL có thể có các namespace riêng cho:

- Kiểu dữ liệu.
- Giá trị và biến.
- Hàm.
- Module.
- Thuộc tính.

Ví dụ:

~~~text
type Customer
let customer: Customer
~~~

Nếu người dùng viết:

~~~text
let another: customer
~~~

thì customer là biến, không phải kiểu. Hệ thống đã tìm thấy tên nhưng sai loại đối tượng cho vị trí khai báo kiểu.

### 8.2. Dùng biến như hàm

~~~text
let taxRate = 0.10
taxRate(order.total)
~~~

Tên taxRate tồn tại nhưng không phải hàm có thể gọi. Diagnostic nên nêu: “taxRate là một giá trị kiểu Decimal, không phải hàm. Có phải bạn định gọi calculateTax?”

### 8.3. Dùng hàm như giá trị

Một DSL có thể yêu cầu hàm phải được gọi trước khi dùng kết quả:

~~~text
let total = calculateTax
~~~

Nếu DSL không hỗ trợ first-class function, tên hàm không thể được dùng như giá trị. Nếu có hỗ trợ, hệ thống cần xác định kiểu hàm và cách truyền tham số.

### 8.4. Phân biệt sai loại với sai chữ ký

Nếu tên không phải hàm, đó là lỗi sai loại đối tượng. Nếu tên là hàm nhưng không có overload nào nhận được các đối số đã truyền, đó là lỗi phân giải chữ ký.

Hai lỗi này nên có mã và thông điệp khác nhau vì cách sửa khác nhau.

## 9. Tên có qualifier và namespace không hợp lệ

### 9.1. Tên đơn và tên đầy đủ

Tên đơn:

~~~text
taxRate
~~~

Tên có qualifier:

~~~text
finance.taxRate
~~~

Tên đầy đủ giúp tránh xung đột và làm rõ nguồn gốc. Tuy nhiên, mỗi thành phần trong đường dẫn đều phải được phân giải theo namespace tương ứng.

### 9.2. Thành phần đầu tiên không tồn tại

~~~text
finanace.taxRate
~~~

Nếu module đúng là finance, lỗi nằm ở thành phần đầu tiên finanace. Diagnostic có thể gợi ý:

~~~text
Không tìm thấy namespace "finanace".
Có phải bạn muốn dùng "finance"?
~~~

### 9.3. Namespace tồn tại nhưng thiếu thành phần tiếp theo

~~~text
finance.tax
~~~

Nếu namespace finance không xuất tên tax, hệ thống nên chỉ ra rằng tax không tồn tại bên trong finance, thay vì báo toàn bộ đường dẫn không hợp lệ.

### 9.4. Truy cập thuộc tính và namespace

Một dấu chấm có thể đại diện cho truy cập thuộc tính, namespace hoặc cả hai tùy cú pháp. Type checker nên phân biệt dựa trên kiểu của phần bên trái và grammar.

Nếu customer là một biến kiểu Customer, customer.address có thể là thuộc tính. Nếu finance là namespace, finance.taxRate có thể là tên đầy đủ. Khi phần bên trái chưa phân giải được, các lỗi phía sau có thể chỉ là lỗi dây chuyền.

### 9.5. Alias và import

Khi người dùng import module bằng alias:

~~~text
import finance.tax as tax

tax.calculate(amount)
~~~

Alias tax có phạm vi và quy tắc trùng tên riêng. Nếu alias xung đột với một biến cục bộ, hệ thống cần áp dụng quy tắc namespace hoặc báo lỗi rõ.

## 10. Tên hàm và overload

### 10.1. Tên hàm có thể có nhiều chữ ký

Một DSL có thể hỗ trợ overload:

~~~text
function format(value: Date): String
function format(value: Money): String
~~~

Khi gọi format(order.total), hệ thống cần xác định kiểu của order.total và chọn chữ ký phù hợp.

### 10.2. Không có overload phù hợp

Nếu có tên hàm nhưng không có chữ ký nhận các đối số hiện tại, diagnostic cần nói tên hàm đã được tìm thấy nhưng danh sách tham số không phù hợp.

Ví dụ:

~~~text
function round(value: Decimal): Integer
function round(value: Decimal, scale: Integer): Decimal

round("12.5")
~~~

Tên round tồn tại, nhưng không có overload nhận String. Thông báo có thể là:

~~~text
Không có phiên bản "round" nhận đối số kiểu String.
Các chữ ký được hỗ trợ:
  round(Decimal): Integer
  round(Decimal, Integer): Decimal
~~~

### 10.3. Quá nhiều overload phù hợp

Nếu nhiều overload cùng phù hợp sau khi áp dụng chuyển đổi ngầm, lời gọi có thể mơ hồ. Diagnostic cần liệt kê các chữ ký cạnh tranh và yêu cầu ép kiểu hoặc chỉ định tham số rõ ràng.

### 10.4. Sai số lượng tham số kiểu generic

Với khai báo:

~~~text
Map<K, V>
~~~

nếu người dùng viết Map<String>, số lượng đối số kiểu không phù hợp. Đây là lỗi arity của generic, không phải tên Map không tồn tại.

Diagnostic nên nêu số lượng tham số kiểu cần có và số lượng đã cung cấp.

## 11. Thiết kế một diagnostic hữu ích

### 11.1. Các thành phần cơ bản

Một diagnostic về tên nên có:

1. **Mã lỗi:** định danh ổn định để IDE, CI và tài liệu tham chiếu.
2. **Mức độ:** error, warning hoặc information.
3. **Thông điệp:** mô tả trực tiếp vấn đề.
4. **Vị trí nguồn:** dòng, cột hoặc khoảng ký tự gây lỗi.
5. **Vị trí liên quan:** khai báo gốc hoặc các ứng viên khác.
6. **Gợi ý sửa:** một hay nhiều cách khắc phục có căn cứ.
7. **Ngữ cảnh:** module, scope hoặc loại đối tượng liên quan.

Một cấu trúc dữ liệu minh họa:

~~~text
Diagnostic {
    code: "NAME_NOT_FOUND"
    severity: Error
    message: "Không tìm thấy tên 'taxRate'"
    primarySpan: source:12:18-12:25
    related: []
    suggestions: ["tax.rate", "taxAmount"]
}
~~~

Tên trường và định dạng trên chỉ là ví dụ. Điều quan trọng là diagnostic có dữ liệu có cấu trúc, không chỉ là một chuỗi văn bản khó xử lý.

### 11.2. Thông điệp nên ngắn và cụ thể

Thông điệp tốt thường trả lời ba câu:

- Tên nào có vấn đề?
- Hệ thống mong đợi điều gì?
- Người dùng có thể làm gì tiếp theo?

Ví dụ:

**Chưa đủ cụ thể:** “Name resolution failed.”

**Cụ thể hơn:** “Không tìm thấy thuộc tính deliveryDate trên kiểu Order. Thuộc tính hiện có gồm createdAt, paidAt và shippedAt.”

### 11.3. Vị trí nguồn chính xác

Diagnostic nên gắn với đúng phần tên gây lỗi, không tô sáng toàn bộ dòng hoặc toàn bộ biểu thức nếu không cần thiết.

Với tên có qualifier:

~~~text
finance.tax.rate
        ^^^
~~~

Nếu tax không tồn tại trong namespace finance, vị trí chính nên bao quanh tax. Nếu rate không tồn tại trong kiểu được phân giải từ finance.tax, vị trí chính nên bao quanh rate.

### 11.4. Thông tin liên quan

Với khai báo trùng, cần tham chiếu đến khai báo trước. Với tên mơ hồ, cần tham chiếu đến từng ứng viên. Với lỗi visibility, cần liên kết đến nơi khai báo và mức truy cập.

Những vị trí liên quan giúp IDE hiển thị liên kết điều hướng và giúp người dùng sửa nhanh hơn.

### 11.5. Mã lỗi ổn định

Mã lỗi không nên phụ thuộc vào ngôn ngữ hiển thị hoặc câu chữ của thông báo. Ví dụ:

| Mã minh họa | Trường hợp |
|---|---|
| NAME_INVALID_IDENTIFIER | Định danh sai quy tắc |
| NAME_NOT_FOUND | Không tìm thấy tên |
| NAME_DUPLICATE | Khai báo trùng |
| NAME_AMBIGUOUS | Tham chiếu mơ hồ |
| NAME_NOT_VISIBLE | Tên tồn tại nhưng không truy cập được |
| NAME_WRONG_KIND | Tên sai loại đối tượng |
| NAME_BAD_QUALIFIER | Thành phần namespace hoặc qualifier sai |
| NAME_NO_MATCHING_OVERLOAD | Không có chữ ký hàm phù hợp |
| NAME_GENERIC_ARITY | Sai số lượng đối số kiểu |

Mã ổn định giúp công cụ có thể lọc, nhóm và kiểm thử diagnostic mà không phải phân tích câu thông báo.

## 12. Gợi ý sửa tên

### 12.1. Tìm tên gần giống

Khi không tìm thấy tên, hệ thống có thể tìm ứng viên có cách viết gần giống. Một số phương pháp:

- Khoảng cách Levenshtein.
- So sánh tiền tố hoặc hậu tố.
- So sánh theo từ trong tên camelCase hoặc snake_case.
- Ưu tiên tên trong cùng scope hoặc cùng kiểu miền.
- So sánh tên trong namespace đã import.

Khoảng cách chuỗi chỉ là một tín hiệu. Tên gần giống nhưng sai loại hoặc không truy cập được có thể không phải gợi ý tốt.

### 12.2. Ưu tiên ứng viên theo ngữ cảnh

Ví dụ, nếu người dùng viết:

~~~text
order.shippedAt
~~~

và kiểu Order có thuộc tính shippedOn, shippedBy, createdAt, hệ thống nên ưu tiên ứng viên cùng loại thuộc tính và cùng kiểu dữ liệu hơn một hàm toàn cục có tên gần giống.

Có thể xếp hạng dựa trên:

1. Cùng namespace hoặc scope.
2. Cùng loại khai báo.
3. Khoảng cách tên.
4. Kiểu dữ liệu và chữ ký phù hợp.
5. Mức độ truy cập.

### 12.3. Không tự sửa khi có nhiều khả năng

Nếu có nhiều tên gần giống, diagnostic nên đưa ra lựa chọn thay vì tự động thay thế. Việc tự sửa sai có thể làm thay đổi hành vi chương trình.

Quick fix chỉ nên áp dụng tự động khi có một ứng viên duy nhất, có độ tin cậy cao và không làm thay đổi ngữ nghĩa ngoài ý định rõ ràng của người dùng.

### 12.4. Gợi ý thêm khai báo hoặc import

Nếu tên tồn tại trong module chưa import, hệ thống có thể đề xuất thêm import:

~~~text
Không tìm thấy calculateTax trong phạm vi hiện tại.
Hàm này được cung cấp bởi module finance.
Gợi ý: import finance.calculateTax
~~~

Chỉ đề xuất khi module thực sự có thể truy cập và không tạo xung đột tên mới.

## 13. Phục hồi sau lỗi phân giải tên

### 13.1. Vì sao cần phục hồi?

Một compiler hoặc editor thường muốn hiển thị nhiều lỗi trong một lần phân tích. Nếu dừng ngay khi gặp tên đầu tiên chưa được khai báo, người dùng phải sửa từng lỗi theo nhiều vòng.

Phục hồi giúp hệ thống tiếp tục xử lý những phần không phụ thuộc vào lỗi hiện tại.

### 13.2. Error symbol

Một cách thường dùng là tạo một ký hiệu lỗi (*error symbol*) thay cho tên chưa phân giải được. Ký hiệu này mang trạng thái lỗi và kiểu đặc biệt để các bước sau biết rằng nguyên nhân đã được báo.

Ví dụ:

~~~text
let total = unknownPrice + tax
let result = total * discountRate
~~~

Nếu unknownPrice chưa được khai báo, resolver có thể tạo ErrorSymbol. Semantic analyzer tránh báo thêm nhiều lỗi vô nghĩa chỉ vì kiểu của unknownPrice chưa biết.

### 13.3. Tránh lỗi dây chuyền

Một lỗi gốc có thể kéo theo nhiều lỗi phụ:

~~~text
unknownCustomer.address.city
~~~

Nếu unknownCustomer chưa tồn tại, không nên đồng thời báo address và city không tồn tại vì hệ thống chưa có kiểu của đối tượng gốc.

Nên báo lỗi ở thành phần đầu tiên không phân giải được, sau đó truyền trạng thái lỗi qua phần còn lại của biểu thức.

### 13.4. Tiếp tục phân tích phần độc lập

~~~text
let a = missingOne
let b = missingTwo
let c = 10
~~~

Hệ thống có thể báo hai lỗi tên chưa khai báo và vẫn xử lý c bình thường.

### 13.5. Giới hạn phục hồi

Phục hồi quá mạnh có thể tạo nhiều diagnostic sai. Nếu không thể xác định cấu trúc tiếp theo, parser hoặc resolver nên đồng bộ tại một ranh giới an toàn như dấu chấm phẩy, dấu đóng khối hoặc khai báo tiếp theo.

Mục tiêu là báo thêm lỗi độc lập mà không tạo ra một chuỗi lỗi giả từ cùng một nguyên nhân.

## 14. Chẩn đoán theo pipeline compiler

Một pipeline có thể phân chia trách nhiệm:

~~~mermaid
flowchart TD
    A["Nguồn DSL"] --> B["Lexer"]
    B --> C["Parser"]
    C --> D["Tạo AST và scope"]
    D --> E["Name Resolver"]
    E --> F["Type Checker"]
    F --> G["Diagnostic Collector"]
    B -.-> G
    C -.-> G
    D -.-> G
    E -.-> G
    F -.-> G
    G --> H["IDE / CLI / Báo cáo"]
~~~

### 14.1. Lexer

Lexer chịu trách nhiệm phát hiện định danh sai cú pháp, ký tự không hợp lệ và lỗi token. Nó biết vị trí ký tự nhưng thường chưa biết tên có được khai báo hay không.

### 14.2. Parser

Parser phát hiện tên hoặc cấu trúc được đặt ở vị trí không hợp lệ theo grammar. Ví dụ, một từ khóa được dùng ở vị trí cần identifier có thể tạo lỗi cú pháp.

### 14.3. Xây dựng scope

Sau khi có cấu trúc khai báo, hệ thống xây dựng symbol table hoặc scope graph. Nó ghi nhận tên, loại khai báo, phạm vi, vị trí nguồn và quyền truy cập.

Khai báo trùng thường có thể được phát hiện trong giai đoạn này.

### 14.4. Name resolver

Resolver tìm đối tượng cho mỗi tham chiếu. Nó phát hiện tên chưa khai báo, mơ hồ, sai namespace và không truy cập được.

### 14.5. Type checker

Type checker có thể phát hiện tên đúng nhưng sai loại hoặc sai chữ ký. Ví dụ, một tên được phân giải thành biến kiểu Decimal nhưng lại được dùng như hàm.

### 14.6. Diagnostic collector

Một thành phần thu thập diagnostic có thể chuẩn hóa mã lỗi, vị trí, mức độ và dữ liệu liên quan. IDE, CLI hoặc API sau đó trình bày theo cách phù hợp.

Tách việc tạo diagnostic khỏi việc hiển thị giúp cùng một compiler hỗ trợ nhiều công cụ mà không phải viết lại logic phát hiện lỗi.

## 15. Symbol table và dữ liệu cần lưu cho chẩn đoán

### 15.1. Symbol table

Symbol table lưu thông tin về các khai báo đã được nhận diện:

~~~text
Symbol {
    name
    kind
    type
    scope
    visibility
    declarationSpan
    module
}
~~~

Đây là mô hình khái niệm. Một implementation có thể dùng hash map, cây scope, đồ thị module hoặc cấu trúc chỉ mục khác.

### 15.2. Scope graph

Scope graph mô tả các quan hệ giữa phạm vi:

- Phạm vi con nhìn thấy khai báo từ phạm vi cha theo quy tắc.
- Module import có thể đưa tên vào phạm vi hiện tại.
- Namespace có thể chứa namespace con.
- Một số phạm vi có thể bị giới hạn bởi quyền truy cập.

Đồ thị này giúp resolver tìm tên và giải thích vì sao một khai báo được hoặc không được nhìn thấy.

### 15.3. Lưu vị trí khai báo

Mỗi symbol nên giữ source span của nơi khai báo. Khi báo trùng hoặc tham chiếu đến tên không truy cập được, diagnostic có thể liên kết đến vị trí gốc.

### 15.4. Lưu loại khai báo

Thông tin kind giúp phân biệt biến, hàm, kiểu, namespace và thuộc tính. Nếu một vị trí yêu cầu TypeSymbol nhưng resolver chỉ tìm thấy ValueSymbol, hệ thống có thể tạo lỗi sai loại thay vì lỗi không tìm thấy.

### 15.5. Phân biệt symbol công khai và nội bộ

Với module hoặc plugin, symbol table cần thể hiện symbol nào được export. Không nên đưa mọi khai báo nội bộ vào tập tra cứu công khai.

## 16. Chẩn đoán trong IDE và công cụ dòng lệnh

### 16.1. Hiển thị trực tiếp trong editor

IDE có thể gạch chân phần tên lỗi, hiển thị thông điệp khi rê chuột và mở danh sách diagnostic. Nếu có quick fix, người dùng có thể chọn sửa tên, thêm import hoặc đổi qualifier.

### 16.2. Hoàn thành tên

Autocomplete có thể dùng cùng dữ liệu scope và symbol table để đề xuất những tên hợp lệ tại vị trí hiện tại.

Nếu một tên bị thiếu, danh sách gợi ý nên lọc theo:

- Loại đối tượng được yêu cầu.
- Phạm vi nhìn thấy.
- Kiểu hoặc chữ ký phù hợp.
- Quyền truy cập.
- Namespace đang được import.

### 16.3. Điều hướng đến khai báo

Với tên đã phân giải, IDE có thể điều hướng đến nơi khai báo. Với tên trùng hoặc mơ hồ, IDE có thể mở các vị trí liên quan.

### 16.4. Định dạng máy đọc được

CLI hoặc language server có thể xuất diagnostic dạng JSON:

~~~json
{
  "code": "NAME_NOT_FOUND",
  "severity": "error",
  "message": "Không tìm thấy tên 'taxRate'",
  "range": {
    "start": { "line": 11, "character": 17 },
    "end": { "line": 11, "character": 24 }
  }
}
~~~

Định dạng thực tế tùy giao thức. Nếu dùng Language Server Protocol, có thể ánh xạ diagnostic sang cấu trúc chuẩn của giao thức để editor hiển thị nhất quán.

### 16.5. Chẩn đoán trong CI

Trong quy trình tích hợp liên tục, diagnostic nên có mã ổn định và vị trí nguồn để log có thể tìm kiếm, nhóm và liên kết với file. CI có thể đặt chính sách cảnh báo hoặc lỗi theo mã, nhưng quyết định đó thuộc cấu hình công cụ, không nên làm thay đổi ngữ nghĩa của compiler.

## 17. Quốc tế hóa thông báo lỗi

### 17.1. Tách mã lỗi khỏi thông điệp

Mã lỗi như NAME_NOT_FOUND nên ổn định, còn câu thông báo có thể được dịch sang nhiều ngôn ngữ.

### 17.2. Giữ nguyên tên trong diagnostic

Tên do người dùng viết thường nên được hiển thị nguyên văn, kể cả khi thông điệp được bản địa hóa. Điều này giúp họ đối chiếu chính xác với mã nguồn.

### 17.3. Không dịch định danh kỹ thuật

Nếu tên module hoặc trường dữ liệu là customerTier, không nên tự dịch thành “hạng khách hàng” trong phần tên được trích dẫn. Có thể thêm nhãn mô tả bên cạnh nhưng cần giữ định danh gốc.

### 17.4. Hỗ trợ văn bản Unicode

Vị trí nguồn cần được quy đổi đúng giữa byte offset, code point, UTF-16 code unit hoặc đơn vị mà editor sử dụng. Nếu các thành phần dùng hệ đếm khác nhau, phần gạch chân có thể lệch khỏi tên thực tế.

## 18. Bảo mật và độ tin cậy của phân giải tên

### 18.1. Không để tên truy cập tùy ý tài nguyên

Nếu DSL có thể tham chiếu file, URL, biến môi trường hoặc dịch vụ, việc phân giải tên cần tuân theo danh sách tài nguyên và quyền được cấp.

Tên hợp lệ về cú pháp không có nghĩa người dùng có quyền truy cập đối tượng đó.

### 18.2. Phòng tránh nhầm lẫn Unicode

Tên chứa ký tự đồng hình có thể được dùng để giả mạo tên hàm hoặc biến. Có thể áp dụng cảnh báo khi tên mới giống tên có sẵn về mặt hiển thị nhưng khác code point.

### 18.3. Không tiết lộ symbol nhạy cảm

Trong môi trường đa tenant, diagnostic không nên liệt kê tên của module hoặc biến mà người dùng không có quyền xem. Chính sách hiển thị cần xét quyền của người nhận diagnostic.

### 18.4. Giới hạn chi phí tìm kiếm

Gợi ý tên gần giống có thể phải so sánh với nhiều symbol. Với dự án lớn, nên giới hạn tập ứng viên, dùng chỉ mục và giới hạn số gợi ý để tránh làm editor chậm.

### 18.5. Không thực thi mã khi gợi ý

Việc tạo gợi ý tên nên dựa trên metadata và symbol table. Không nên chạy hàm hoặc plugin chỉ để xem một tên có tồn tại hay không, vì việc đó có thể gây tác động phụ hoặc làm lộ dữ liệu.

## 19. Ví dụ tổng hợp: chẩn đoán tên trong DSL bán hàng

Giả sử DSL có các khai báo:

~~~text
module sales {
    type Customer {
        tier: CustomerTier
        discountRate: Decimal
    }

    function applyDiscount(rate: Decimal)
}

module finance {
    function calculateTax(amount: Money): Money
}
~~~

Người dùng viết:

~~~text
import sales.Customer
import sales.applyDiscount
import finance.calculateTax

rule MemberOffer {
    when customer.tier is GOLD
    then applyDiscount(customer.discoutRate)
         and calculateTax(order.total)
}
~~~

Giả sử customer và order chưa được khai báo trong phạm vi rule, đồng thời thuộc tính đúng là discountRate.

### 19.1. Chẩn đoán tên chưa khai báo

Hệ thống báo:

~~~text
NAME_NOT_FOUND: Không tìm thấy tên "customer" trong phạm vi của rule MemberOffer.
NAME_NOT_FOUND: Không tìm thấy tên "order" trong phạm vi của rule MemberOffer.
~~~

Nếu DSL yêu cầu khai báo đầu vào của rule, người dùng cần khai báo hoặc bind hai đối tượng đó.

### 19.2. Chẩn đoán thuộc tính sai chính tả

Sau khi customer được khai báo là Customer, resolver tìm thuộc tính discoutRate và không thấy. Vì kiểu Customer có discountRate, hệ thống có thể gợi ý:

~~~text
NAME_NOT_FOUND: Không tìm thấy thuộc tính "discoutRate" trên kiểu Customer.
Gợi ý: discountRate
~~~

### 19.3. Chẩn đoán sai kiểu đối số

Nếu order.total có kiểu Decimal trong khi calculateTax yêu cầu Money, tên hàm và thuộc tính đều có thể được phân giải thành công nhưng lời gọi vẫn không hợp lệ:

~~~text
TYPE_ARGUMENT_MISMATCH: calculateTax yêu cầu Money nhưng nhận Decimal.
~~~

Đây là lỗi kiểu ở bước sau phân giải tên, không phải lỗi tên không tồn tại.

### 19.4. Chẩn đoán import mơ hồ

Nếu module khác cũng export applyDiscount, import không alias có thể làm lời gọi mơ hồ. Hệ thống cần chỉ ra cả hai module và yêu cầu tên đầy đủ hoặc alias.

Ví dụ này cho thấy một dòng DSL có thể chứa nhiều loại vấn đề. Diagnostic nên phân loại đúng từng lỗi để người dùng sửa theo nguyên nhân.

## 20. Những sai lầm thường gặp khi chẩn đoán tên

### 20.1. Gộp mọi lỗi thành “không tìm thấy”

Tên sai loại, tên private và tên mơ hồ có nguyên nhân khác nhau. Gộp chúng làm người dùng khó sửa và khiến IDE không thể cung cấp quick fix phù hợp.

### 20.2. Chỉ hiển thị tên mà không có vị trí

Một file có thể dùng cùng một tên nhiều lần. Diagnostic cần chỉ ra lần tham chiếu cụ thể gây lỗi.

### 20.3. Không chỉ ra khai báo liên quan

Khi khai báo trùng, chỉ báo vị trí mới không đủ. Người dùng cần biết khai báo trước nằm ở đâu.

### 20.4. Đề xuất tên không đúng ngữ cảnh

Một tên có cách viết gần giống nhưng sai loại hoặc không truy cập được có thể khiến người dùng sửa theo hướng không hợp lệ. Gợi ý phải xét cả scope, kind và kiểu.

### 20.5. Tạo nhiều lỗi dây chuyền

Nếu một đối tượng gốc không tồn tại, việc tiếp tục báo mọi thuộc tính con đều không tồn tại sẽ làm nhiễu danh sách diagnostic.

### 20.6. Phụ thuộc thứ tự import

Chọn một tên theo thứ tự nạp module khiến kết quả không ổn định. Cần quy tắc ưu tiên rõ hoặc báo mơ hồ.

### 20.7. Bỏ qua chuẩn hóa tên

Nếu Unicode, chữ hoa thường hoặc ký tự đồng hình không được xử lý nhất quán, người dùng có thể gặp lỗi trùng hoặc không tìm thấy dù tên nhìn giống nhau.

### 20.8. Thông báo lỗi chỉ dành cho compiler developer

Các thông báo như SymbolResolutionException hoặc UnknownBinding có thể hữu ích trong log nội bộ nhưng không giải thích đủ cho người viết DSL. Cần chuyển chúng thành diagnostic hướng người dùng.

## 21. Quy trình xây dựng chẩn đoán tên

Một quy trình triển khai có thể gồm:

1. **Định nghĩa quy tắc tên:** ký tự hợp lệ, từ khóa, chuẩn hóa và phân biệt hoa thường.
2. **Xác định các loại symbol:** biến, hàm, kiểu, thuộc tính, namespace và module.
3. **Mô hình hóa scope:** quan hệ cha-con, import, visibility và shadowing.
4. **Xây dựng symbol table:** lưu tên, kind, type, scope và source span.
5. **Triển khai resolver:** tra cứu tên theo quy tắc xác định.
6. **Phân loại lỗi:** chưa khai báo, trùng, mơ hồ, không truy cập được, sai kind và sai chữ ký.
7. **Tạo diagnostic có cấu trúc:** mã, mức độ, thông điệp, vị trí và thông tin liên quan.
8. **Thêm gợi ý có kiểm soát:** so khớp tên, lọc theo ngữ cảnh và không tự sửa khi mơ hồ.
9. **Thiết kế phục hồi:** dùng error symbol và tránh lỗi dây chuyền.
10. **Tích hợp công cụ:** editor, CLI, language server và CI.

## 22. Câu hỏi tự đánh giá

1. Phân giải tên khác phân tích cú pháp như thế nào?
2. Phân biệt tên chưa khai báo, tên trùng và tên mơ hồ.
3. Vì sao cần phân biệt tên không tồn tại với tên không truy cập được?
4. Một tên có thể hợp lệ về ký tự nhưng sai ngữ cảnh như thế nào?
5. Symbol table cần lưu những thông tin nào để tạo diagnostic hữu ích?
6. Vì sao diagnostic cần mã lỗi ổn định và source span chính xác?
7. Gợi ý tên gần giống nên xét những yếu tố nào ngoài khoảng cách chuỗi?
8. Error symbol giúp tránh lỗi dây chuyền ra sao?
9. Vì sao thứ tự import không nên quyết định ngẫu nhiên tên nào được chọn?
10. Chẩn đoán tên cần phối hợp với type checker như thế nào?

## Kết luận

Chẩn đoán tên không hợp lệ là một phần thiết yếu của phân giải tên trong DSL. Lỗi có thể bắt nguồn từ định danh sai cú pháp, tên chưa khai báo, khai báo trùng, tham chiếu mơ hồ, quyền truy cập, namespace, loại đối tượng hoặc chữ ký hàm. Mỗi trường hợp cần được phân loại đúng để thông báo phản ánh nguyên nhân thực tế.

Một diagnostic hữu ích có mã ổn định, thông điệp cụ thể, vị trí nguồn chính xác và liên kết đến khai báo hoặc ứng viên liên quan. Gợi ý sửa cần dựa trên scope, loại symbol và kiểu; cơ chế phục hồi cần tiếp tục phân tích phần độc lập mà không tạo lỗi dây chuyền. Khi resolver, symbol table, type checker và công cụ phát triển dùng chung một mô hình diagnostic có cấu trúc, người dùng có thể tìm và sửa lỗi tên nhanh hơn, đồng thời hệ thống giữ được hành vi phân giải nhất quán và dễ dự đoán.

# Che khuất tên

Trong một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), người dùng đặt tên cho biến, thực thể, thuộc tính, kiểu dữ liệu, quy tắc, hàm và các thành phần khác. Khi nhiều khai báo có cùng tên xuất hiện trong các phạm vi khác nhau, bộ phân giải tên phải xác định tham chiếu đang chỉ đến khai báo nào. Một tình huống phổ biến là **che khuất tên** (*name shadowing*): một khai báo trong phạm vi gần hơn có cùng tên với khai báo ở phạm vi bên ngoài, khiến tham chiếu trong phạm vi gần hơn được liên kết đến khai báo mới thay vì khai báo bên ngoài.

Ví dụ, DSL cho phép khai báo biến toàn cục `discountRate` và một biến cục bộ cùng tên trong một quy tắc:

~~~text
let discountRate = 0.05;

rule "special customer" {
    let discountRate = 0.10;
    applyDiscount(order.total * discountRate);
}
~~~

Nếu DSL sử dụng phạm vi từ vựng lồng nhau và quy tắc tìm tên gần nhất, tham chiếu `discountRate` trong thân quy tắc sẽ chỉ đến biến cục bộ có giá trị `0.10`. Khai báo bên ngoài vẫn tồn tại, nhưng bị che khuất trong phạm vi bên trong.

Che khuất tên là một phần của thiết kế phạm vi và phân giải tên. Nó có thể giúp tái sử dụng tên quen thuộc trong một ngữ cảnh hẹp, nhưng cũng có thể khiến người đọc nhầm lẫn, làm thay đổi ý nghĩa khi thêm một khai báo mới hoặc che mất một hàm, kiểu hay thành phần tích hợp quan trọng. Vì vậy, đặc tả DSL cần quy định rõ tên nào có thể bị che khuất, phạm vi nào được phép, cách tham chiếu đến tên bên ngoài và cách công cụ thông báo khi có nguy cơ nhầm lẫn.

## 1. Khái niệm che khuất tên

### Phạm vi và khai báo

**Khai báo** (*declaration*) giới thiệu một tên vào môi trường ngôn ngữ. Tùy DSL, khai báo có thể tạo ra biến, hằng, tham số, kiểu, thực thể, hàm, hành động, chính sách hoặc module.

**Phạm vi** (*scope*) là vùng chương trình trong đó một khai báo có thể được tham chiếu theo quy tắc phân giải tên. Phạm vi có thể được tạo bởi module, khối, hàm, quy tắc, vòng lặp, biểu thức `let`, mẫu khớp hoặc một cấu trúc riêng của DSL.

Ví dụ:

~~~text
let taxRate = 0.08;

policy InvoicePolicy {
    let taxRate = 0.10;
    calculate invoice.total * taxRate;
}
~~~

Trong ví dụ này, `taxRate` ở cấp chính sách có thể che khuất `taxRate` ở cấp module. Tên được tra cứu trong phạm vi gần nhất trước; nếu không tìm thấy, bộ phân giải mới tiếp tục tìm ở phạm vi bao quanh.

### Định nghĩa name shadowing

Một khai báo `D_inner` che khuất khai báo `D_outer` nếu:

1. Hai khai báo có cùng tên theo quy tắc so sánh tên của DSL.
2. `D_inner` nằm trong phạm vi lồng bên trong phạm vi của `D_outer`, hoặc có độ ưu tiên tra cứu cao hơn theo quy tắc của DSL.
3. Một tham chiếu trong vùng chịu ảnh hưởng được phân giải đến `D_inner` thay vì `D_outer`.

Ví dụ khái quát:

~~~text
outer scope:
    name -> declaration A

    inner scope:
        name -> declaration B
        reference name -> declaration B
~~~

Khai báo B che khuất A đối với các tham chiếu trong phạm vi bên trong có thể nhìn thấy B. Khi ra khỏi phạm vi bên trong, tham chiếu `name` lại có thể được phân giải đến A.

### Che khuất có làm mất khai báo bên ngoài không?

Không. Che khuất là quy tắc chọn khai báo khi phân giải một tham chiếu trong một ngữ cảnh. Nó không nhất thiết xóa, ghi đè hay thay đổi khai báo bên ngoài. Khai báo bên ngoài vẫn có thể được dùng ở các phạm vi khác, hoặc được tham chiếu bằng tên đầy đủ nếu DSL hỗ trợ qualified name.

Ví dụ:

~~~text
let mode = "production";

workflow Deployment {
    let mode = "dry-run";
    log(mode);          // "dry-run"
    log(root.mode);     // "production", nếu root là namespace gốc
}
~~~

Cú pháp `root.mode` chỉ là ví dụ minh họa. DSL phải định nghĩa rõ cơ chế truy cập tên đã bị che khuất; không thể mặc định mọi ngôn ngữ đều có từ khóa `root` hoặc cú pháp tương tự.

## 2. Cách phân giải tên trong các phạm vi lồng nhau

Che khuất thường gắn với phạm vi từ vựng (*lexical scope*). Khi gặp một tham chiếu, bộ phân giải bắt đầu từ phạm vi chứa tham chiếu rồi lần lượt đi ra các phạm vi bao quanh.

### Quy tắc tìm tên gần nhất

Một thuật toán phổ biến:

1. Xác định phạm vi hiện tại của tham chiếu.
2. Tìm khai báo phù hợp trong phạm vi hiện tại.
3. Nếu có đúng một khai báo hợp lệ, chọn khai báo đó.
4. Nếu không có, chuyển sang phạm vi cha.
5. Lặp lại cho đến phạm vi gốc hoặc namespace được phép tra cứu.
6. Nếu không tìm thấy, báo lỗi tên chưa được khai báo.
7. Nếu có nhiều khai báo không thể phân biệt trong cùng mức ưu tiên, báo lỗi mơ hồ thay vì chọn tùy ý.

Ví dụ:

~~~text
module Orders {
    let limit = 100;

    workflow ProcessOrder {
        let limit = 50;

        step Validate {
            let limit = 20;
            require order.quantity <= limit;
        }
    }
}
~~~

Trong `Validate`, `limit` được phân giải đến giá trị `20`. Nếu tham chiếu xuất hiện trong `ProcessOrder` nhưng bên ngoài `Validate`, nó được phân giải đến `50`. Nếu tham chiếu xuất hiện ở cấp module `Orders`, nó được phân giải đến `100`.

### Mô hình phạm vi

~~~mermaid
flowchart TD
    A[Module Orders: limit = 100]
    B[Workflow ProcessOrder: limit = 50]
    C[Step Validate: limit = 20]
    A --> B
    B --> C
    C --> D[Reference limit]
    D --> E[Chọn khai báo gần nhất: 20]
~~~

Sơ đồ thể hiện đường tìm kiếm từ phạm vi nhỏ nhất ra ngoài. Nếu phạm vi hiện tại có khai báo cùng tên, các khai báo bên ngoài không được chọn cho tham chiếu đó theo quy tắc tìm tên gần nhất.

### Ranh giới phạm vi

DSL cần xác định cấu trúc nào tạo phạm vi mới. Ví dụ, dấu ngoặc nhọn có thể tạo block scope; một `rule` có thể tạo scope riêng; tham số của lambda có thể chỉ có hiệu lực trong thân lambda; biến trong vòng lặp có thể chỉ có hiệu lực trong thân vòng lặp.

Không nên suy luận rằng mọi cặp dấu ngoặc đều tạo phạm vi. Dấu ngoặc chỉ nhóm biểu thức có thể không tạo scope. Ví dụ:

~~~text
let rate = 0.1;
let total = (subtotal + tax) * rate;
~~~

Ngoặc quanh biểu thức chỉ thay đổi cách nhóm phép tính, không nhất thiết tạo phạm vi mới. Đặc tả phải phân biệt grouping syntax với scope-forming construct.

## 3. Các loại tên có thể bị che khuất

Che khuất không chỉ áp dụng cho biến. Tùy cách tổ chức namespace của DSL, nhiều loại khai báo có thể cùng tên hoặc có quy tắc ưu tiên riêng.

| Loại tên | Ví dụ | Câu hỏi thiết kế |
|---|---|---|
| Biến và hằng | `let amount = ...` | Biến cục bộ có được che khuất biến module không? |
| Tham số | `rule(order) { ... }` | Tham số có che khuất biến cùng tên ở ngoài không? |
| Hàm hoặc hành động | `approveOrder()` | Một hàm cục bộ có thể che khuất hàm tích hợp không? |
| Kiểu và thực thể | `entity Customer` | Kiểu cục bộ có thể che khuất kiểu được import không? |
| Thuộc tính | `order.status` | Thuộc tính có được tra cứu trong namespace riêng không? |
| Quy tắc hoặc chính sách | `rule Discount` | Quy tắc cùng tên ở module con có che khuất quy tắc module cha không? |
| Module hoặc namespace | `module Billing` | Alias module có thể che khuất tên module khác không? |
| Tên sự kiện | `event OrderCreated` | Sự kiện cục bộ có được ưu tiên hơn sự kiện import không? |
| Built-in | `now()`, `currentUser()` | Người dùng có thể khai báo tên trùng built-in không? |

Một DSL có thể dùng nhiều namespace độc lập: namespace biến, namespace kiểu, namespace hành động và namespace module. Khi đó, cùng một chuỗi tên có thể hợp lệ ở các namespace khác nhau. Ví dụ `Customer` có thể là tên kiểu và đồng thời là tên một biến nếu ngôn ngữ quy định hai namespace tách biệt. Nếu DSL chỉ có một namespace chung, trường hợp này có thể là khai báo trùng hoặc che khuất.

## 4. Phân biệt shadowing, hiding, overloading và overriding

Các thuật ngữ này thường bị dùng lẫn nhau trong tài liệu ngôn ngữ lập trình. Cách gọi cụ thể có thể khác giữa các ngôn ngữ, nhưng nên phân biệt theo bản chất để đặc tả DSL rõ ràng.

### Shadowing

Shadowing xảy ra khi một khai báo trong phạm vi gần hơn có cùng tên với khai báo ở phạm vi bao quanh, làm tham chiếu trong phạm vi gần hơn chọn khai báo gần nhất.

~~~text
let status = "global";

rule Process {
    let status = "local";
    log(status); // tham chiếu đến status cục bộ
}
~~~

### Hiding

Hiding thường được dùng để mô tả một khai báo che khuất hoặc làm tên ở phạm vi khác không còn được nhìn thấy qua cách tra cứu thông thường. Trong một số ngôn ngữ hướng đối tượng, tên thành viên ở lớp con có thể hide thành viên cùng tên ở lớp cha, đặc biệt khi chữ ký không tương thích hoặc thành viên không phải phương thức được override.

Ví dụ khái quát:

~~~text
type Base {
    field code: String;
}

type Derived extends Base {
    field code: Integer;
}
~~~

Nếu DSL hỗ trợ kế thừa mô hình và cho phép thành viên lớp con che khuất thành viên lớp cha, cần quy định cách truy cập thành viên gốc, kiểm tra kiểu và ảnh hưởng đến tính tương thích.

### Overloading

Overloading là việc có nhiều khai báo cùng tên nhưng khác chữ ký, thường phân biệt bằng số lượng hoặc kiểu tham số. Bộ phân giải chọn phiên bản phù hợp dựa trên kiểu đối số và quy tắc overload resolution.

~~~text
function format(value: Money): Text;
function format(value: Date): Text;

format(order.total);
format(order.createdAt);
~~~

Hai hàm `format` không nhất thiết che khuất nhau. Chúng là các overload trong cùng một tập ứng viên. Nếu không có overload nào phù hợp hoặc có nhiều overload cùng phù hợp mà không có quy tắc ưu tiên, bộ phân giải phải báo lỗi mơ hồ.

### Overriding

Overriding là việc một kiểu con cung cấp triển khai thay thế cho phương thức có thể override của kiểu cha, thường giữ hợp đồng chữ ký và tham gia cơ chế dispatch động.

~~~text
type BaseNotifier {
    method send(message: Text) { ... }
}

type EmailNotifier extends BaseNotifier {
    override method send(message: Text) { ... }
}
~~~

Ở đây, `EmailNotifier.send` thay thế hành vi của phương thức cha khi dispatch trên đối tượng có kiểu thực tế `EmailNotifier`. Đây là cơ chế đa hình, khác với việc một biến cục bộ che khuất biến bên ngoài.

### Bảng đối chiếu

| Khái niệm | Điều kiện điển hình | Cách chọn hoặc hành vi |
|---|---|---|
| Shadowing | Cùng tên ở các phạm vi lồng nhau. | Tham chiếu chọn khai báo có độ ưu tiên phạm vi cao nhất. |
| Hiding | Một khai báo làm tên/thành viên khác không được thấy qua tra cứu thông thường. | Phụ thuộc quy tắc phạm vi hoặc kế thừa của ngôn ngữ. |
| Overloading | Cùng tên trong một tập khai báo, khác chữ ký. | Chọn theo kiểu và quy tắc overload resolution. |
| Overriding | Kiểu con triển khai lại phương thức có thể override của kiểu cha. | Dispatch theo kiểu thực tế của đối tượng. |

Một DSL có thể không hỗ trợ kế thừa, overloading hoặc overriding. Không cần đưa các cơ chế này vào chỉ vì chúng tồn tại trong ngôn ngữ chủ. Hãy dùng thuật ngữ phù hợp với tính năng thực tế mà DSL cung cấp.

## 5. Shadowing của biến, tham số và biến vòng lặp

Biến và tham số là trường hợp che khuất dễ gặp nhất trong DSL biểu diễn biểu thức, quy tắc và quy trình.

### Biến cục bộ che khuất biến bên ngoài

~~~text
let threshold = 100;

rule LargeOrder {
    let threshold = 500;
    require order.total >= threshold;
}
~~~

Trong `LargeOrder`, ngưỡng `500` được sử dụng. Nếu người viết muốn dùng ngưỡng toàn cục `100`, DSL cần cung cấp qualified name hoặc một cơ chế truy cập rõ ràng.

### Tham số che khuất biến ngoài

~~~text
let customer = defaultCustomer;

function calculateDiscount(customer: Customer) {
    return customer.discountRate;
}
~~~

Trong thân hàm, `customer` chỉ tham chiếu đến tham số. Biến ngoài cùng tên không được chọn qua tra cứu tên không định danh.

### Biến vòng lặp

~~~text
let item = defaultItem;

for each item in order.items {
    process(item);
}

process(item); // biến ngoài nếu scope của vòng lặp đã kết thúc
~~~

Nếu biến vòng lặp chỉ có hiệu lực trong thân vòng lặp, nó che khuất biến ngoài trong thân nhưng không thay đổi biến ngoài. DSL phải xác định biến vòng lặp có tồn tại sau vòng lặp hay không và mỗi lần lặp có tạo binding mới hay tái sử dụng cùng binding.

### Pattern binding

Một cấu trúc pattern matching có thể tạo biến mới:

~~~text
match payment {
    Accepted(amount) => approve(amount),
    Rejected(reason) => reject(reason)
}
~~~

Các tên `amount` và `reason` chỉ có hiệu lực trong nhánh tương ứng. Nếu một biến bên ngoài cũng có tên `amount`, binding của pattern có thể che khuất nó trong nhánh. Phạm vi chính xác cần được đặc tả để tránh tham chiếu ngoài ý muốn.

## 6. Shadowing trong biểu thức lồng nhau và lambda

DSL nhúng hoặc DSL có biểu thức hàm thường tạo nhiều phạm vi nhỏ. Lambda, closure và biểu thức truy vấn có thể khai báo tham số cùng tên với biến ở ngoài.

Ví dụ:

~~~text
let threshold = 100;

orders.filter(order => {
    let threshold = order.minimumTotal;
    order.total >= threshold
});
~~~

Trong lambda, `threshold` cục bộ che khuất biến bên ngoài. Điều này có thể hợp lệ, nhưng nếu người đọc không nhận ra phạm vi lồng nhau, họ có thể nghĩ điều kiện đang dùng ngưỡng `100`.

### Capture và closure

Một closure có thể tham chiếu đến biến từ phạm vi bên ngoài nếu không có khai báo cùng tên trong phạm vi bên trong.

~~~text
let minimum = 100;

let predicate = order => order.total >= minimum;
~~~

`minimum` được capture từ phạm vi bao quanh. Nếu lambda khai báo một biến cục bộ cũng tên `minimum`, tham chiếu trong lambda có thể bị che khuất và không còn capture biến ngoài.

~~~text
let minimum = 100;

let predicate = order => {
    let minimum = order.specialThreshold;
    order.total >= minimum
};
~~~

Ở đây, `minimum` trong biểu thức cuối là biến cục bộ của lambda. Khi thiết kế DSL, cần phân biệt capture với shadowing và xác định biến capture được đọc theo giá trị tại thời điểm tạo closure hay theo binding có thể thay đổi.

### Shadowing và thời gian sống của binding

Scope quyết định nơi tên có thể được dùng; lifetime quyết định binding hoặc giá trị tồn tại trong thời gian nào. Hai khái niệm liên quan nhưng không giống nhau. Một biến có thể không còn nhìn thấy theo tên sau khi rời scope nhưng giá trị của nó vẫn tồn tại vì closure giữ tham chiếu đến binding đó.

DSL có closure cần quy định:

- Biến cục bộ được capture theo giá trị hay theo tham chiếu?
- Binding có thể bị thay đổi sau khi closure được tạo không?
- Nếu tên bị shadow trong scope con, closure được tạo trước đó có bị ảnh hưởng không?
- Có cho phép capture biến chưa khởi tạo hoặc biến có vòng đời ngắn hơn closure không?

## 7. Shadowing giữa namespace, module và import

Một DSL có thể hỗ trợ module, package hoặc namespace để tổ chức khai báo. Khi nhiều module có cùng tên thành phần, bộ phân giải cần quy tắc ưu tiên và cú pháp định danh đầy đủ.

### Import và tên cục bộ

~~~text
import Finance.Payment;

module Checkout {
    entity Payment { ... }

    let payment: Payment;
}
~~~

Trong ví dụ này, `Payment` có thể chỉ đến kiểu cục bộ `Checkout.Payment` thay vì kiểu được import `Finance.Payment`, nếu DSL ưu tiên khai báo cục bộ. Nếu không muốn hành vi này gây bất ngờ, DSL có thể báo lỗi xung đột hoặc yêu cầu tên đầy đủ.

### Qualified name

Tên đầy đủ có thể loại bỏ sự mơ hồ:

~~~text
let localPayment: Checkout.Payment;
let externalPayment: Finance.Payment;
~~~

Qualified name cũng hữu ích khi người dùng muốn truy cập một khai báo đã bị che khuất. DSL cần xác định namespace gốc, alias, cách phân tách thành phần và quy tắc phân giải từng phần.

### Import alias

~~~text
import Finance.Payment as ExternalPayment;

let payment: ExternalPayment;
~~~

Alias tạo một tên mới trong phạm vi module. Nếu alias trùng với một khai báo cục bộ, DSL cần quy định lỗi trùng tên hay thứ tự ưu tiên. Không nên để thứ tự xử lý file quyết định alias nào được chọn.

### Ưu tiên tra cứu đề xuất

Một DSL có thể chọn thứ tự tra cứu như sau:

1. Binding cục bộ trong biểu thức hoặc block hiện tại.
2. Tham số của hàm, lambda hoặc rule.
3. Khai báo trong module hiện tại.
4. Khai báo được import tường minh.
5. Khai báo trong namespace cha theo quy tắc được công bố.
6. Built-in hoặc thư viện chuẩn.

Đây chỉ là một thứ tự minh họa. Có DSL ưu tiên import, có DSL yêu cầu qualified name và có DSL tách namespace theo loại tên. Đặc tả phải công bố thứ tự thực tế và tránh các tầng ưu tiên ẩn.

## 8. Che khuất tên built-in và hàm tích hợp

DSL thường cung cấp các hàm hoặc giá trị tích hợp như `now`, `currentUser`, `sum`, `min`, `max`, `emit` hoặc `log`. Nếu người dùng được phép khai báo cùng tên, built-in có thể bị che khuất.

Ví dụ:

~~~text
let now = "not-a-time";

rule Expiration {
    require promotion.endsAt > now;
}
~~~

Nếu `now` vốn là built-in trả về thời điểm hiện tại, khai báo cục bộ có thể làm tham chiếu trong rule chuyển sang chuỗi văn bản. Đây có thể là lỗi khó nhận ra vì cú pháp vẫn hợp lệ.

### Các chính sách có thể chọn

- **Cấm shadow built-in:** tên dành riêng không thể được khai báo lại.
- **Cho phép nhưng cảnh báo:** chương trình hợp lệ nhưng compiler phát warning.
- **Cho phép với namespace:** built-in phải được gọi qua namespace như `std.now()`.
- **Ưu tiên local:** khai báo cục bộ được chọn; built-in chỉ truy cập qua tên đầy đủ.
- **Tách namespace:** biến và hàm có thể dùng cùng lexeme nếu DSL quy định hai không gian tên riêng.

Đối với hàm tích hợp có tác dụng bảo mật hoặc kiểm soát quyền, nên tránh để shadowing âm thầm thay đổi ý nghĩa. Ví dụ, một hàm `authorize` hoặc `audit` bị che khuất có thể khiến quy tắc quan trọng không còn thực hiện hành vi dự kiến.

## 9. Shadowing trong kế thừa mô hình

Một số DSL mô hình hóa kiểu, thực thể hoặc component có quan hệ kế thừa. Khi đó, tên thành viên của kiểu con có thể trùng tên thành viên kiểu cha.

~~~text
type BaseOrder {
    field status: Text;
    method total(): Money;
}

type SpecialOrder extends BaseOrder {
    field status: SpecialOrderStatus;
}
~~~

Nếu DSL cho phép `SpecialOrder.status` che khuất `BaseOrder.status`, cần trả lời:

- Truy cập `specialOrder.status` trả về kiểu nào?
- Có thể truy cập trường gốc bằng cú pháp qualified hay `super` không?
- Việc che khuất có tương thích với kiểu cha không?
- Khi dùng đối tượng `SpecialOrder` qua tham chiếu `BaseOrder`, trường nào được nhìn thấy?
- Nếu thành viên cùng tên nhưng khác kiểu, có cần cấm để tránh phá vỡ hợp đồng?

### Trường dữ liệu và phương thức

Trong nhiều ngôn ngữ, trường dữ liệu không có dispatch động như phương thức. Một trường cùng tên ở kiểu con có thể hide trường cha, còn phương thức có thể override và được chọn theo kiểu thực tế. Nếu DSL hỗ trợ cả hai, không nên dùng chung một quy tắc phân giải cho mọi loại thành viên.

### Thành viên tĩnh và thành viên instance

Tên thành viên tĩnh có thể được tra cứu theo kiểu hoặc namespace; thành viên instance được tra cứu trên kiểu của đối tượng. Việc cùng tên xuất hiện ở hai nơi có thể tạo sự mơ hồ nếu cú pháp không phân biệt. Cần quy định rõ quy tắc lookup và kiểm tra kiểu.

## 10. Shadowing và phạm vi từ vựng so với phạm vi động

Trong **phạm vi từ vựng** (*lexical scoping*), việc phân giải tên được xác định dựa trên cấu trúc mã nguồn và các phạm vi bao quanh tại vị trí khai báo. Đây là mô hình phổ biến trong các ngôn ngữ hiện đại.

Trong **phạm vi động** (*dynamic scoping*), việc tìm biến có thể phụ thuộc vào chuỗi lời gọi đang hoạt động khi chương trình chạy. Khi đó, cùng một biểu thức có thể nhìn thấy binding khác nhau tùy đường gọi.

Ví dụ khái niệm:

~~~text
let rate = 0.05;

function calculate() {
    return rate;
}

function execute() {
    let rate = 0.10;
    return calculate();
}
~~~

Với lexical scoping, `calculate` nhìn thấy `rate` ở phạm vi nơi nó được định nghĩa, nên trả về `0.05`. Với dynamic scoping, nếu lookup đi theo chuỗi lời gọi, nó có thể thấy `rate` cục bộ trong `execute` và trả về `0.10`.

DSL cần công bố mô hình scoping. Nếu dùng lexical scoping, shadowing thường có thể xác định ngay trong giai đoạn phân giải tĩnh. Nếu dùng dynamic scoping, việc xác định binding có thể cần ngữ cảnh thực thi và khó phân tích trước hơn.

## 11. Quy tắc khai báo trước và sau tham chiếu

Một câu hỏi quan trọng là khai báo có cần xuất hiện trước nơi dùng hay không.

### Declaration-before-use

Một DSL có thể yêu cầu khai báo xuất hiện trước tham chiếu:

~~~text
let threshold = 100;
require order.total >= threshold;
~~~

Nếu tham chiếu xuất hiện trước khai báo, bộ phân giải báo lỗi. Quy tắc này làm quá trình đọc tuần tự đơn giản hơn và hạn chế một số trường hợp shadowing khó hiểu.

### Forward reference

DSL khác có thể cho phép tham chiếu đến khai báo ở phía sau:

~~~text
rule First {
    call Second;
}

rule Second {
    approveOrder;
}
~~~

Để hỗ trợ forward reference, compiler thường cần thu thập khai báo trước, xây dựng symbol table, rồi mới phân giải các tham chiếu. Khi nhiều phạm vi có cùng tên, cần xác định khai báo nào có hiệu lực tại vị trí tham chiếu.

### Khai báo che khuất xuất hiện giữa một phạm vi

Ví dụ:

~~~text
let mode = "outer";
log(mode);

let mode = "inner";
log(mode);
~~~

DSL cần quy định liệu khai báo thứ hai có được phép che khuất tên trong phần còn lại của block hay không. Một số ngôn ngữ cho phép shadowing theo vị trí; một số cấm khai báo trùng trong cùng scope; một số chỉ cho phép khai báo mới trong block con. Nếu cho phép, tham chiếu trước và sau khai báo có thể được phân giải khác nhau.

## 12. Symbol table và biểu diễn shadowing

**Symbol table** là cấu trúc dữ liệu mà compiler hoặc interpreter dùng để quản lý các khai báo và thông tin liên quan. Nó là thành phần cốt lõi trong phân giải tên.

Một symbol có thể lưu:

- Tên và loại symbol.
- Kiểu dữ liệu hoặc chữ ký.
- Phạm vi khai báo.
- Vị trí nguồn khai báo.
- ID ổn định của symbol.
- Quyền truy cập hoặc visibility.
- Symbol cha hoặc namespace chứa nó.
- Trạng thái khởi tạo và các metadata khác.

### Scope tree

Một cách cài đặt phổ biến là tạo cây phạm vi. Mỗi scope có bảng symbol riêng và liên kết đến scope cha.

~~~text
Scope(Module)
  symbols:
    limit -> Symbol#1
  parent: none

  Scope(Workflow)
    symbols:
      limit -> Symbol#2
    parent: Module

    Scope(Step)
      symbols:
        limit -> Symbol#3
      parent: Workflow
~~~

Khi phân giải `limit` trong `Step`, bộ phân giải tìm `Symbol#3` trước. Nếu không có, nó mới đi đến `Workflow`, rồi `Module`.

### Pseudocode phân giải tên

~~~text
resolve(name, currentScope):
    scope = currentScope

    while scope is not null:
        candidates = scope.lookupLocal(name)

        if candidates is not empty:
            return chooseCandidateOrReportAmbiguity(candidates)

        scope = scope.parent

    report UnknownName(name)
~~~

Đối với DSL có nhiều namespace, `lookupLocal` cần nhận thêm loại tên hoặc namespace. Đối với overloading, hàm chọn ứng viên còn cần kiểu đối số và quy tắc overload resolution.

### Không chỉ lưu tên đã phân giải

Sau khi phân giải, AST nên liên kết tham chiếu đến symbol identity, không chỉ giữ chuỗi tên. Ví dụ `NameReference("limit")` có thể được gắn với `Symbol#3`. Điều này giúp các bước sau không phải phân giải lại bằng văn bản và tránh nhầm hai khai báo cùng tên ở hai scope.

## 13. Mô hình hóa kết quả phân giải

Một tham chiếu tên có thể ở một trong các trạng thái:

- **Resolved:** tìm được đúng một symbol phù hợp.
- **Unresolved:** không có symbol phù hợp.
- **Ambiguous:** có nhiều ứng viên cùng mức ưu tiên và không có quy tắc chọn duy nhất.
- **Inaccessible:** có symbol nhưng tham chiếu không được phép truy cập do visibility hoặc quyền.
- **Wrong kind:** có tên nhưng loại symbol không phù hợp, ví dụ dùng tên kiểu ở vị trí cần một giá trị.
- **Shadowed:** có khai báo cùng tên ở phạm vi khác nhưng tham chiếu được chọn theo một khai báo gần hơn.

`Shadowed` thường là thông tin bổ sung về quan hệ giữa các khai báo, không nhất thiết là trạng thái lỗi. Compiler có thể ghi nhận khai báo bị che khuất để tạo cảnh báo hoặc hỗ trợ IDE.

### Thông tin shadowing trong symbol graph

Một symbol có thể lưu liên kết đến symbol bị nó che khuất:

~~~text
Symbol#3
  name: limit
  scope: Step
  shadows: Symbol#2

Symbol#2
  name: limit
  scope: Workflow
  shadows: Symbol#1

Symbol#1
  name: limit
  scope: Module
  shadows: none
~~~

Liên kết này không bắt buộc để phân giải tên, nhưng hữu ích cho cảnh báo, điều hướng và giải thích vì sao một tham chiếu chọn symbol cụ thể.

## 14. Tác động của shadowing đến kiểu và kiểm tra ngữ nghĩa

Khi một tên bị che khuất, kiểu của tham chiếu có thể thay đổi theo khai báo được chọn. Điều này có thể làm biểu thức trước đây hợp lệ trở thành sai kiểu hoặc thay đổi hành vi mà cú pháp vẫn không đổi.

Ví dụ:

~~~text
let status: OrderStatus = PAID;

rule Review {
    let status: Text = "manual-review";
    require status == PAID;
}
~~~

Trong phạm vi `Review`, `status` là `Text`. Biểu thức `status == PAID` có thể sai kiểu nếu `PAID` là giá trị thuộc `OrderStatus`. Nếu người viết tưởng đang dùng biến ngoài, lỗi này rất dễ gây nhầm lẫn.

### Type checking sau name resolution

Một pipeline thường:

1. Thu thập khai báo và tạo scope.
2. Phân giải mỗi tham chiếu đến symbol cụ thể.
3. Gán hoặc tra kiểu của symbol.
4. Kiểm tra phép toán, đối số và kiểu kết quả.

Không nên kiểm tra kiểu của tên dựa trên chuỗi lexeme mà chưa xác định symbol. Hai khai báo cùng tên có thể có kiểu khác nhau.

### Shadowing và type inference

Nếu DSL suy luận kiểu, khai báo mới có thể có kiểu được suy luận từ biểu thức khởi tạo. Bộ phân giải phải xác định scope và binding trước khi suy luận những biểu thức tham chiếu đến tên đó. Với khai báo đệ quy hoặc forward reference, có thể cần tạo symbol tạm và giải quyết kiểu theo nhiều lượt.

## 15. Khi nào nên cho phép shadowing?

Cho phép shadowing có thể làm tên cục bộ ngắn gọn và giúp cấu trúc lồng nhau tự nhiên hơn. Tuy nhiên, lợi ích phụ thuộc vào người dùng và độ phức tạp của DSL.

### Lợi ích

- Cho phép dùng tên quen thuộc trong ngữ cảnh hẹp mà không phải tạo nhiều tên dài.
- Hỗ trợ tham số lambda như `order`, `item` hoặc `customer` trong các biểu thức lồng.
- Giúp khối con độc lập hơn với chi tiết đặt tên ở bên ngoài.
- Hỗ trợ cấu trúc lồng nhau có ý nghĩa miền riêng, chẳng hạn biến `status` trong từng bước workflow.
- Cho phép module hoặc quy tắc chuyên biệt định nghĩa lại một tên trong phạm vi giới hạn.

### Rủi ro

- Người đọc có thể nhầm tham chiếu đang dùng khai báo nào.
- Thêm một khai báo cục bộ có thể âm thầm đổi ý nghĩa chương trình.
- Một hàm tích hợp hoặc tên chuẩn có thể bị che khuất.
- Refactoring hoặc di chuyển đoạn mã có thể làm thay đổi scope và binding.
- Lỗi kiểu có thể xuất hiện xa nơi khai báo che khuất.
- Cấu trúc lồng sâu khiến việc tìm khai báo thực tế khó khăn.

### Chính sách lựa chọn

Một DSL có thể chọn một trong các hướng:

| Chính sách | Mô tả | Đánh đổi |
|---|---|---|
| Cho phép shadowing tự do | Tên trong scope gần hơn luôn có thể che khuất tên ngoài. | Linh hoạt nhưng dễ che khuất ngoài ý muốn. |
| Chỉ cho phép ở block con | Không cho khai báo trùng trong cùng scope, nhưng cho phép ở scope lồng. | Hạn chế xung đột cùng mức, vẫn giữ tính tiện dụng. |
| Cấm shadowing | Mỗi tên không được lặp trong các scope đang nhìn thấy nhau. | Dễ đọc và ít bất ngờ, nhưng có thể buộc dùng tên dài. |
| Cho phép với cảnh báo | Chương trình hợp lệ nhưng cảnh báo khi khai báo che khuất tên khác. | Cân bằng giữa linh hoạt và khả năng phát hiện rủi ro. |
| Chỉ cho phép một số loại | Ví dụ biến được shadow, built-in và kiểu không được. | Kiểm soát tốt nhưng cần quy tắc chi tiết. |

Với DSL hướng đến chuyên viên nghiệp vụ, quy tắc đơn giản và cảnh báo rõ thường quan trọng hơn khả năng biểu đạt tối đa. Với DSL hướng đến lập trình viên, shadowing có thể quen thuộc hơn, nhưng vẫn cần nhất quán.

## 16. Thiết kế cảnh báo và lỗi liên quan đến shadowing

Không phải mọi trường hợp che khuất đều là lỗi. Compiler nên phân biệt trường hợp hợp lệ với trường hợp đáng ngờ.

### Cảnh báo khi che khuất biến ngoài

Ví dụ:

~~~text
let amount = order.total;

rule Discount {
    let amount = order.discount;
    apply(amount);
}
~~~

Compiler có thể cảnh báo:

~~~text
Warning DSL-W102: 'amount' shadows a declaration in an outer scope.
  Local declaration: policies/discount.dsl:4
  Shadowed declaration: policies/discount.dsl:1
  Consider using a more specific name such as 'discountAmount'.
~~~

Cảnh báo nên cung cấp cả vị trí khai báo mới và khai báo bị che khuất. Người dùng có thể điều hướng đến cả hai để quyết định có cần đổi tên không.

### Cảnh báo khi che khuất built-in

Nếu `now()` hoặc `currentUser()` là hàm chuẩn, việc khai báo tên trùng có thể đáng ngờ hơn. DSL có thể cấm hoàn toàn hoặc phát cảnh báo mức cao.

### Lỗi khi không thể phân giải duy nhất

Nếu nhiều khai báo cùng tên xuất hiện trong cùng một namespace và cùng mức ưu tiên, không nên chọn dựa vào thứ tự file hoặc thứ tự duyệt. Hãy báo lỗi ambiguity và yêu cầu qualified name hoặc đổi tên.

### Diagnostic nên giải thích binding được chọn

Khi có shadowing phức tạp, thông báo có thể nói:

~~~text
Reference 'limit' resolves to the declaration in scope 'Validate'.
The outer declaration in scope 'ProcessOrder' is shadowed here.
~~~

Thông tin này hữu ích trong IDE, đặc biệt khi người dùng hover lên tên hoặc yêu cầu giải thích phân giải.

## 17. Shadowing, macro và hygiene

Một DSL có macro hoặc template có thể sinh thêm tên và cấu trúc. Nếu macro tạo một biến tên `temp` trong phạm vi của người gọi, biến cùng tên của người dùng có thể bị che khuất hoặc bị tham chiếu nhầm. Đây là vấn đề **variable capture**.

### Macro không hygienic

Giả sử macro:

~~~text
macro withTemporary(value, body) {
    let temp = value;
    body(temp);
}
~~~

Người dùng gọi macro trong một scope đã có biến `temp`. Nếu macro mở rộng văn bản đơn giản và dùng cùng namespace, binding do macro tạo có thể xung đột với binding của người dùng.

### Macro hygiene

Macro hygienic giữ được ranh giới tên giữa mã macro và mã gọi. Các định danh được tạo tự động có thể được gắn mark hoặc symbol identity riêng để tránh capture ngoài ý muốn.

Các kỹ thuật thường gặp:

- Sinh tên nội bộ duy nhất (*gensym*) cho biến tạm.
- Giữ nguồn gốc và ngữ cảnh định danh của macro.
- Phân giải tên theo môi trường định nghĩa hoặc môi trường gọi theo quy tắc rõ ràng.
- Dùng macro expansion trên AST thay vì thay thế chuỗi văn bản.
- Phân biệt định danh do macro tạo với định danh do người dùng viết.

### Call-site và definition-site

Macro có thể được thiết kế để một số tên được phân giải theo nơi định nghĩa macro, còn tên khác theo nơi gọi. Đây là quyết định ngữ nghĩa quan trọng. Nếu không định nghĩa, cùng macro có thể hoạt động khác nhau tùy scope gọi và gây lỗi khó tái lập.

DSL không có macro vẫn có thể gặp vấn đề tương tự với template, snippet hoặc cú pháp rút gọn được mở rộng thành các khai báo tạm.

## 18. Shadowing và bảo mật

Che khuất tên có thể tạo rủi ro nếu DSL cho phép người dùng định nghĩa tên trùng với các hàm tích hợp hoặc các thao tác nhạy cảm.

Ví dụ, một chính sách kiểm soát truy cập có thể sử dụng:

~~~text
require authorize(currentUser, resource);
~~~

Nếu `authorize` hoặc `currentUser` có thể bị che khuất bởi một hàm hay biến do người dùng khai báo, ý nghĩa của quy tắc có thể thay đổi. Nếu bộ kiểm tra chỉ xác nhận cú pháp mà không kiểm tra symbol identity, một chính sách tưởng như đang gọi hàm bảo mật chuẩn có thể gọi một thành phần khác.

Các biện pháp thiết kế:

- Đặt built-in nhạy cảm trong namespace dành riêng.
- Cấm shadowing các tên liên quan đến phân quyền, kiểm toán hoặc sandbox.
- Yêu cầu qualified name cho API bảo mật quan trọng.
- Gắn tham chiếu đã phân giải với symbol identity và kiểm tra quyền trên symbol đó.
- Hiển thị rõ nguồn gốc của hàm được gọi trong IDE và diagnostic.
- Kiểm thử rằng khai báo cục bộ không thể thay thế cơ chế kiểm soát đặc quyền ngoài ý muốn.

Không nên xem việc đổi tên hoặc che khuất một hàm là bằng chứng về quyền. Quyền phải được kiểm tra dựa trên danh tính và chính sách bảo mật thực tế, không dựa vào tên hiển thị.

## 19. Ví dụ tổng hợp: DSL xử lý đơn hàng

Giả sử DSL cho phép khai báo chính sách ở cấp module, biến cục bộ trong workflow và tham số trong một rule.

~~~text
module OrderProcessing {
    let approvalLimit = 10000000;

    workflow ReviewOrder(order: Order) {
        let approvalLimit = 5000000;

        rule CheckHighValue(order: Order) {
            let approvalLimit = 2000000;

            require order.total <= approvalLimit
                or order.hasManagerApproval;
        }
    }
}
~~~

Trong `CheckHighValue`, tham chiếu `approvalLimit` được phân giải đến khai báo ở scope rule với giá trị `2.000.000`. Khai báo trong workflow (`5.000.000`) và module (`10.000.000`) bị che khuất tại vị trí này.

Ngoài ra, tham số `order` của rule che khuất tham số `order` của workflow. Nếu hai đối tượng không giống nhau, các tham chiếu trong rule sẽ sử dụng đối tượng được truyền vào `CheckHighValue`.

### Bảng phân giải

| Tham chiếu | Scope hiện tại | Các ứng viên theo đường tìm kiếm | Kết quả |
|---|---|---|---|
| `approvalLimit` trong `CheckHighValue` | Rule | Rule → Workflow → Module | Khai báo trong Rule. |
| `approvalLimit` trong phần khác của Workflow | Workflow | Workflow → Module | Khai báo trong Workflow. |
| `approvalLimit` ở cấp module | Module | Module | Khai báo trong Module. |
| `order` trong `CheckHighValue` | Rule | Rule parameter → Workflow parameter | Tham số của Rule. |

### Truy cập khai báo bên ngoài

Nếu DSL cần dùng ngưỡng module trong rule, có thể yêu cầu tên đầy đủ:

~~~text
require order.total <= OrderProcessing.approvalLimit;
~~~

Hoặc dùng một cơ chế truy cập scope cha đã được định nghĩa. Việc truy cập rõ ràng giúp người đọc biết đang dùng binding nào và giảm phụ thuộc vào shadowing.

### Chẩn đoán đề xuất

Compiler có thể phát cảnh báo cho hai khai báo `approvalLimit` ở các scope con:

~~~text
Warning DSL-W102: 'approvalLimit' shadows a declaration in Workflow.
Warning DSL-W102: 'approvalLimit' shadows a declaration in Module.
~~~

Nếu chính sách dự án cho phép shadowing nhưng yêu cầu code dễ đọc, người dùng có thể đổi tên thành `ruleApprovalLimit`, `workflowApprovalLimit` và `moduleApprovalLimit`.

## 20. Quy trình phân giải tên có xét shadowing

Một quy trình compiler có thể thực hiện theo các bước sau:

1. **Xác định cấu trúc tạo scope:** module, block, function, rule, lambda, loop, pattern hoặc namespace.
2. **Thu thập khai báo:** tạo symbol cho mỗi biến, kiểu, hành động, module và thành phần được khai báo.
3. **Xây dựng cây scope:** liên kết scope con với scope cha và xác định các namespace được nhìn thấy.
4. **Phát hiện khai báo trùng:** phân biệt duplicate trong cùng scope với shadowing giữa các scope.
5. **Phân giải từng tham chiếu:** tìm từ scope gần nhất ra ngoài theo thứ tự ưu tiên đã định nghĩa.
6. **Xử lý overload và loại symbol:** nếu có nhiều ứng viên, áp dụng quy tắc chữ ký, kiểu và namespace; báo mơ hồ nếu không chọn được duy nhất.
7. **Gắn symbol identity:** liên kết nút tham chiếu AST với khai báo đã chọn.
8. **Ghi nhận quan hệ shadowing:** xác định khai báo bên ngoài bị che khuất nếu cần cho warning và IDE.
9. **Kiểm tra kiểu và visibility:** xác nhận symbol được dùng đúng loại và có quyền truy cập.
10. **Tạo diagnostic:** báo tên chưa khai báo, khai báo trùng, shadowing đáng ngờ hoặc tham chiếu mơ hồ.

Một số DSL cần thu thập toàn bộ khai báo của module trước khi phân giải vì hỗ trợ forward reference. Một số DSL xử lý tuần tự theo thứ tự văn bản. Dù chọn cách nào, kết quả không nên phụ thuộc vào thứ tự file hoặc thứ tự duyệt không được quy định.

## 21. Kiểm thử hành vi che khuất tên

Kiểm thử cần xác nhận không chỉ tên nào được chọn mà còn scope, kiểu và vị trí nguồn của symbol được chọn.

### Kiểm thử scope lồng nhau

~~~text
Input:
    let rate = 0.05;
    block {
        let rate = 0.10;
        use(rate);
    }

Expected:
    use(rate) resolves to inner declaration.
~~~

### Kiểm thử khôi phục khai báo ngoài

~~~text
Input:
    let rate = 0.05;
    block {
        let rate = 0.10;
        use(rate);
    }
    use(rate);

Expected:
    reference inside block resolves to inner declaration.
    reference after block resolves to outer declaration.
~~~

### Kiểm thử tham số che khuất biến

~~~text
Input:
    let order = defaultOrder;
    function process(order) { use(order); }

Expected:
    reference inside function resolves to parameter.
~~~

### Kiểm thử built-in

~~~text
Input:
    let now = "text";
    use(now());

Expected:
    Either reject declaration, report shadowing, or resolve according to the documented namespace policy.
~~~

### Kiểm thử ambiguity và duplicate

Tạo hai khai báo cùng tên trong một scope, hoặc hai import cùng ưu tiên. Xác nhận compiler báo lỗi rõ ràng thay vì chọn theo thứ tự xử lý.

### Kiểm thử macro hygiene

Tạo macro dùng biến tạm có tên trùng biến ở call site. Xác nhận expansion không làm thay đổi binding của tham chiếu do người dùng viết.

### Kiểm thử refactoring

Đổi tên một symbol bị che khuất và xác nhận chỉ các tham chiếu đã liên kết đến symbol đó được cập nhật. Không thay tất cả chuỗi có cùng tên.

## 22. Hỗ trợ shadowing trong IDE

IDE có thể giúp người dùng hiểu rõ tham chiếu đang liên kết đến khai báo nào.

Các tính năng hữu ích:

- **Go to Definition:** đưa con trỏ đến đúng khai báo đã phân giải.
- **Hover:** hiển thị tên, loại, kiểu, scope và vị trí khai báo.
- **Find References:** liệt kê tham chiếu theo symbol identity, không chỉ theo văn bản.
- **Highlight shadowed declaration:** làm nổi bật khai báo bị che khuất và khai báo đang che khuất.
- **Rename:** đổi tên đúng một symbol và các tham chiếu tương ứng.
- **Warning:** cảnh báo khi che khuất biến, tham số hoặc built-in đáng chú ý.
- **Quick fix:** đề xuất tên cụ thể hơn hoặc qualified name.
- **Explain resolution:** giải thích đường tìm kiếm và lý do một khai báo được chọn.

Ví dụ khi hover `limit`, IDE có thể hiển thị:

~~~text
limit: Integer
Declared in: Rule CheckHighValue
Shadows: Workflow.approvalLimit
~~~

Thông tin này giảm thời gian tìm hiểu một tham chiếu trong chương trình có nhiều scope lồng nhau.

## 23. Những lỗi thiết kế thường gặp

**Không định nghĩa rõ scope.** Nếu người dùng không biết block, rule hoặc lambda nào tạo phạm vi mới, họ không thể dự đoán tên nào sẽ bị che khuất.

**Cho phép khai báo trùng trong cùng scope nhưng xử lý như shadowing.** Hai khai báo cùng namespace và cùng phạm vi thường cần được xem là duplicate hoặc overload theo chữ ký, không nên âm thầm chọn khai báo cuối.

**Để thứ tự file quyết định binding.** Nếu import hoặc khai báo được xử lý theo thứ tự tình cờ, cùng dự án có thể phân giải khác nhau khi build hoặc tải module.

**Không phân biệt namespace.** Biến, kiểu, hành động và module có thể có quy tắc lookup khác nhau. Gộp chúng mà không có đặc tả sẽ tạo lỗi mơ hồ.

**Cho phép shadow built-in nhạy cảm mà không cảnh báo.** Các tên liên quan đến quyền, kiểm toán hoặc thời gian hệ thống có thể bị thay đổi ý nghĩa ngoài ý muốn.

**Chỉ lưu chuỗi tên trong AST.** Các bước sau có thể phân giải lại nhầm symbol khi nhiều khai báo cùng tên. Nên liên kết đến symbol identity.

**Nhầm shadowing với overriding hoặc overloading.** Các cơ chế này có quy tắc khác nhau về phạm vi, chữ ký và dispatch. Dùng sai thuật ngữ làm đặc tả khó hiểu.

**Bỏ qua capture trong closure và macro.** Việc sinh hoặc di chuyển mã có thể làm tham chiếu liên kết sang biến khác nếu không bảo vệ binding.

**Không cung cấp cách truy cập tên bị che khuất.** Nếu DSL cho phép shadowing nhưng không có qualified name hoặc cơ chế tương đương, người dùng có thể không truy cập được khai báo bên ngoài khi cần.

**Cảnh báo quá nhiều hoặc quá ít.** Cảnh báo mọi trường hợp hợp lệ có thể gây nhiễu; không cảnh báo các trường hợp che khuất built-in hoặc biến quan trọng có thể làm lỗi khó phát hiện.

## 24. Hướng dẫn thiết kế chính sách shadowing cho DSL

Khi định nghĩa ngôn ngữ, nhóm nên quyết định rõ các điểm sau:

1. **Mô hình scope:** những cấu trúc nào tạo phạm vi và phạm vi nào lồng nhau?
2. **Namespace:** tất cả tên có dùng chung một không gian hay tách theo loại symbol?
3. **Quy tắc lookup:** tìm từ scope hiện tại ra ngoài theo thứ tự nào?
4. **Shadowing được phép:** loại khai báo nào có thể che khuất loại nào?
5. **Duplicate:** khai báo trùng trong cùng scope được xử lý ra sao?
6. **Built-in:** tên chuẩn có thể bị che khuất không?
7. **Import và qualified name:** cách truy cập tên ngoài scope hoặc tên trùng giữa module?
8. **Overload:** nếu có nhiều hàm cùng tên, cách chọn theo chữ ký và kiểu như thế nào?
9. **Kế thừa:** thành viên kiểu con có thể hide hoặc override thành viên kiểu cha không?
10. **Closure và macro:** binding được capture và hygiene được bảo đảm ra sao?
11. **Diagnostic:** khi nào cảnh báo, khi nào lỗi và thông tin nào cần hiển thị?
12. **IDE:** làm thế nào để điều hướng và rename theo symbol identity?

### Một chính sách mặc định có thể cân nhắc

Với DSL nghiệp vụ, một chính sách tương đối dễ hiểu có thể là:

- Cho phép biến hoặc tham số trong scope con che khuất biến ở scope cha.
- Cấm hai khai báo cùng loại và cùng tên trong một scope, trừ overload được định nghĩa rõ.
- Cấm hoặc cảnh báo mạnh khi che khuất built-in quan trọng.
- Dùng qualified name để truy cập khai báo ở module hoặc namespace khác.
- Phân giải tên theo lexical scope, không phụ thuộc thứ tự runtime.
- Gắn mọi tham chiếu với symbol identity sau khi phân giải.
- Cảnh báo khi một tên cục bộ che khuất một tên ngoài có thể gây nhầm lẫn.

Đây là một lựa chọn thiết kế, không phải quy tắc bắt buộc. DSL có thể chọn cấm shadowing hoàn toàn nếu người dùng không chuyên lập trình hoặc nếu việc nhầm lẫn có rủi ro nghiệp vụ cao.

## 25. Kết quả cần có khi đặc tả che khuất tên

Một đặc tả phân giải tên hoàn chỉnh nên cung cấp:

- **Mô hình phạm vi:** danh sách cấu trúc tạo scope và quan hệ cha–con.
- **Quy tắc tra cứu:** thứ tự tìm kiếm, namespace, import và qualified name.
- **Chính sách shadowing:** loại tên được phép che khuất, trường hợp bị cấm và cách xử lý khai báo trùng.
- **Phân biệt cơ chế tên:** quy tắc riêng cho shadowing, hiding, overloading và overriding nếu DSL hỗ trợ.
- **Symbol model:** cách lưu khai báo, kiểu, scope, vị trí nguồn, symbol identity và quan hệ bị che khuất.
- **Quy tắc closure/macro:** cách capture, expansion và tránh variable capture.
- **Diagnostic:** mã lỗi, cảnh báo, vị trí khai báo và gợi ý sửa.
- **Hỗ trợ công cụ:** điều hướng định nghĩa, tìm tham chiếu, rename và giải thích phân giải.
- **Bộ kiểm thử:** scope lồng nhau, tham số, vòng lặp, import, built-in, ambiguity, macro và refactoring.

Che khuất tên là kết quả trực tiếp của cách DSL tổ chức phạm vi và phân giải tên. Khi quy tắc được định nghĩa rõ, người dùng có thể dự đoán tham chiếu sẽ liên kết đến khai báo nào, còn compiler có thể kiểm tra kiểu, phát hiện xung đột và cung cấp thông tin hữu ích cho IDE. Một chính sách shadowing tốt cần cân bằng sự tiện dụng của tên cục bộ với khả năng đọc, an toàn và tính ổn định của chương trình DSL.

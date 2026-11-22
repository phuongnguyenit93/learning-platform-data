# Ràng buộc tham chiếu

Trong một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), một thành phần thường không đứng độc lập. Quy tắc có thể tham chiếu đến thực thể, thuộc tính, kiểu, hành động hoặc quy tắc khác; một workflow có thể gọi một workflow con; một mô hình có thể liên kết đến một mô hình khác; một chính sách có thể sử dụng khai báo được import từ module bên ngoài. Bộ phân giải tên xác định tham chiếu đang trỏ đến đối tượng nào, còn **ràng buộc tham chiếu** (*reference constraints*) xác định tham chiếu đó có hợp lệ theo cấu trúc và ngữ nghĩa của DSL hay không.

Ví dụ, một chính sách phê duyệt đơn hàng có thể viết:

~~~text
policy OrderApproval {
    when order.customer.creditProfile.riskLevel == LOW
    then approveOrder(order);
}
~~~

Để chương trình hợp lệ, `order` phải là một biến hoặc tham số đã được khai báo; kiểu của nó phải có thuộc tính `customer`; kiểu của `customer` phải có `creditProfile`; `riskLevel` phải tồn tại và có kiểu phù hợp với `LOW`; `approveOrder` phải là hành động có thể gọi trong ngữ cảnh này; tham số truyền vào phải tương thích với chữ ký hành động. Nếu `creditProfile` là tham chiếu tùy chọn, DSL còn cần quy định điều gì xảy ra khi hồ sơ tín dụng chưa tồn tại.

Như vậy, kiểm tra tham chiếu không dừng ở việc tìm thấy một tên. Nó kiểm tra quan hệ giữa nguồn tham chiếu và đích tham chiếu, loại đối tượng được phép trỏ đến, phạm vi nhìn thấy, tính tồn tại, số lượng liên kết, tính duy nhất, các quy tắc toàn vẹn và những điều kiện miền liên quan. Các ràng buộc này thường được kiểm tra trong giai đoạn phân tích ngữ nghĩa sau khi parser đã tạo AST và bộ phân giải tên đã xác định các symbol có thể tham chiếu.

## 1. Tham chiếu trong DSL là gì?

**Tham chiếu** (*reference*) là một liên kết từ một phần tử của chương trình hoặc mô hình đến một phần tử khác. Tùy loại DSL, tham chiếu có thể được biểu diễn bằng tên văn bản, đường dẫn có cấu trúc, ID, khóa, cổng kết nối hoặc một đối tượng liên kết trong mô hình nội bộ.

Ví dụ các dạng tham chiếu:

~~~text
// Tham chiếu biến và thuộc tính
order.total

// Tham chiếu hành động
approveOrder(order)

// Tham chiếu quy tắc
use policy StandardApproval;

// Tham chiếu kiểu
let customer: Customer;

// Tham chiếu module
import Finance.Payment;

// Tham chiếu phần tử trong mô hình
connect StartNode.output -> ApproveNode.input;
~~~

Tham chiếu thường có hai phía:

- **Nguồn tham chiếu (source):** nơi chứa liên kết, chẳng hạn thuộc tính `customer` của một đơn hàng hoặc lời gọi `approveOrder` trong rule.
- **Đích tham chiếu (target):** phần tử mà liên kết trỏ đến, chẳng hạn đối tượng `Customer`, hành động `approveOrder` hoặc node `ApproveNode`.

Trong mô hình dữ liệu, có thể phân biệt tham chiếu đơn (*single reference*) và tham chiếu nhiều (*multi-reference*). Một thuộc tính `customer` có thể trỏ đến đúng một khách hàng; một thuộc tính `approvers` có thể trỏ đến nhiều người phê duyệt.

### Tham chiếu không phải là containment

**Containment** biểu diễn quan hệ sở hữu hoặc cấu trúc cha–con: một phần tử nằm bên trong phần tử khác và thường có vòng đời phụ thuộc vào phần tử chứa. **Cross-reference** liên kết hai phần tử độc lập, có thể nằm ở các nhánh hoặc tài liệu khác nhau.

Ví dụ:

~~~text
entity Order {
    items: List<OrderItem>;
    customer: Customer;
}
~~~

`items` có thể là quan hệ containment nếu `OrderItem` thuộc sở hữu của `Order`. `customer` thường là cross-reference vì `Customer` tồn tại độc lập và có thể được nhiều đơn hàng tham chiếu.

Sự phân biệt này ảnh hưởng đến việc xóa phần tử, sao chép mô hình, serialization, kiểm tra vòng đời và tính toàn vẹn. Không nên mặc định mọi thuộc tính trỏ đến một đối tượng đều là containment.

## 2. Ràng buộc tham chiếu là gì?

Ràng buộc tham chiếu là điều kiện mà một liên kết phải thỏa để được xem là hợp lệ trong mô hình DSL. Một ràng buộc có thể kiểm tra:

- Đích tham chiếu có tồn tại hay không.
- Đích có đúng loại hoặc kiểu được yêu cầu hay không.
- Đích có nằm trong phạm vi mà nguồn được phép truy cập hay không.
- Tham chiếu đơn có đúng số lượng đích hay không.
- Danh sách tham chiếu có phần tử trùng lặp hay không.
- Đích có đang ở trạng thái hoặc giai đoạn vòng đời phù hợp hay không.
- Liên kết có vi phạm quy tắc toàn vẹn, tính duy nhất hoặc quan hệ hai chiều hay không.
- Đồ thị tham chiếu có tạo chu kỳ bị cấm hay không.
- Tham chiếu ngoài có thể được tải, xác thực và tin cậy hay không.

Một tham chiếu có thể được phân giải thành công nhưng vẫn vi phạm ràng buộc. Ví dụ, `approveOrder` tồn tại và được nhìn thấy, nhưng chỉ nhận tham số `Order`; nếu lời gọi truyền một `Customer`, tên đã được phân giải nhưng tham chiếu đến hành động được dùng sai kiểu.

### Phân biệt name resolution và reference validation

| Hoạt động | Câu hỏi chính | Ví dụ kết quả |
|---|---|---|
| Name resolution | Tên này trỏ đến khai báo nào? | `approveOrder` được liên kết đến symbol `Action#42`. |
| Kiểm tra loại tham chiếu | Đích có đúng loại không? | Vị trí cần một `Action`, nhưng tên trỏ đến `Entity`. |
| Kiểm tra kiểu | Kiểu nguồn và đích có tương thích không? | `Customer` không thể truyền vào tham số `Order`. |
| Kiểm tra toàn vẹn | Liên kết có thỏa quy tắc mô hình không? | Một `Order` bắt buộc phải có đúng một `Customer`. |
| Kiểm tra ngữ nghĩa miền | Liên kết có hợp lệ trong nghiệp vụ không? | Không được phê duyệt đơn của khách hàng bị khóa. |

Các bước này có thể được triển khai trong cùng một pass hoặc nhiều pass riêng. Dù tổ chức thế nào, cần giữ ranh giới khái niệm để diagnostic cho biết lỗi thuộc loại nào.

## 3. Các nhóm ràng buộc tham chiếu phổ biến

| Nhóm | Nội dung kiểm tra | Ví dụ |
|---|---|---|
| Existence | Đích tham chiếu phải tồn tại. | Rule gọi một action đã được khai báo. |
| Type/kind | Đích phải đúng loại hoặc kiểu. | Cổng đầu ra chỉ nối đến cổng đầu vào tương thích. |
| Scope/visibility | Nguồn được phép nhìn thấy và truy cập đích. | Module không thể dùng khai báo private của module khác. |
| Cardinality | Số lượng liên kết nằm trong giới hạn. | Mỗi `Order` có đúng một `Customer`. |
| Uniqueness | Liên kết hoặc khóa không trùng theo quy tắc. | Một node không được có hai cạnh cùng định danh. |
| Referential integrity | Đích vẫn hợp lệ trong mô hình hoặc kho dữ liệu. | Không để tham chiếu đến entity đã bị xóa. |
| Lifecycle | Đích ở trạng thái cho phép được tham chiếu. | Chỉ dùng phiên bản workflow đã publish. |
| Bidirectional consistency | Hai đầu quan hệ phản ánh cùng một liên kết. | `order.customer` tương ứng với `customer.orders`. |
| Acyclicity | Đồ thị tham chiếu không chứa chu kỳ bị cấm. | Kế thừa kiểu không được tạo vòng. |
| Domain constraint | Quan hệ thỏa quy tắc nghiệp vụ. | Người phê duyệt phải thuộc đơn vị có quyền xử lý. |

Không phải DSL nào cũng cần mọi nhóm. Một DSL tính toán biểu thức có thể chủ yếu cần existence, scope và type. Một DSL mô hình dữ liệu hoặc workflow có thể cần cardinality, lifecycle, integrity và graph constraints.

## 4. Ràng buộc tồn tại của đích (existence)

Một tham chiếu thường phải trỏ đến một phần tử đã được khai báo hoặc có thể được tải từ nguồn hợp lệ.

Ví dụ:

~~~text
workflow ProcessOrder {
    call ValidateOrder;
    call ReserveInventory;
    call CreateShipment;
}
~~~

Nếu `CreateShipment` không được khai báo, tham chiếu đó không hợp lệ. Compiler có thể phát diagnostic tại tên `CreateShipment` và gợi ý các workflow có tên gần giống.

### Khai báo chưa tồn tại và forward reference

Một DSL có thể cho phép tham chiếu đến khai báo xuất hiện phía sau:

~~~text
workflow Main {
    call ValidateOrder;
}

workflow ValidateOrder {
    check order.isValid;
}
~~~

Đây là forward reference. Nó không phải tham chiếu chưa tồn tại nếu compiler thu thập khai báo toàn module trước khi phân giải. Đặc tả cần xác định phạm vi của forward reference: cùng block, cùng module, toàn dự án hay chỉ các module được import.

### Tham chiếu tùy chọn và tham chiếu bắt buộc

Một trường có thể được phép để trống:

~~~text
entity Order {
    customer: Customer?;
}
~~~

Dấu `?` minh họa một tham chiếu tùy chọn. Nếu trường không có giá trị, điều đó có thể hợp lệ. Với trường bắt buộc:

~~~text
entity Order {
    customer: Customer;
}
~~~

mô hình cần bảo đảm có một đích hợp lệ trước khi được xem là hoàn chỉnh hoặc trước khi thực hiện thao tác yêu cầu khách hàng.

### Deferred reference

Một số DSL cho phép tham chiếu chưa được giải quyết ngay vì tài liệu được tải từng phần, module có thể chưa được đồng bộ hoặc đích nằm ở dịch vụ bên ngoài. Khi đó, hệ thống cần phân biệt:

- Tham chiếu chưa phân giải tạm thời do nguồn chưa được tải.
- Tham chiếu không tồn tại sau khi đã hoàn tất phạm vi tra cứu.
- Tham chiếu bị từ chối do quyền truy cập hoặc nguồn không đáng tin cậy.

Không nên báo lỗi “unknown reference” ngay khi một module phụ thuộc chưa được tải nếu DSL hỗ trợ tải trì hoãn. Ngược lại, không nên coi một tham chiếu chưa được xác minh là hợp lệ chỉ vì có thể sẽ tồn tại sau này.

## 5. Ràng buộc loại và kiểu của đích

Một tham chiếu có thể tìm thấy tên nhưng trỏ đến loại đối tượng không được phép.

Ví dụ:

~~~text
entity Customer { ... }
action ApproveOrder(order: Order) { ... }

workflow ProcessOrder {
    call Customer;
}
~~~

Nếu vị trí `call` yêu cầu một action hoặc workflow nhưng `Customer` là entity, bộ kiểm tra phải báo lỗi loại tham chiếu. Việc tên tồn tại không làm cho cách dùng đó hợp lệ.

### Kiểu đích và kiểu nguồn

Giả sử một quan hệ được định nghĩa:

~~~text
entity Order {
    customer: Customer;
}
~~~

Mọi giá trị được gán vào `Order.customer` phải là đối tượng tương thích với `Customer` theo quy tắc kiểu của DSL. Nếu DSL có subtyping, một kiểu con có thể được chấp nhận; nếu có interface hoặc trait, đích có thể phải thỏa hợp đồng tương ứng.

### Covariance và contravariance

Trong một số mô hình kiểu, quan hệ tham chiếu đến kiểu con/kiểu cha có thể phụ thuộc variance. Ví dụ, một danh sách chỉ đọc các `Customer` có thể chấp nhận danh sách `PreferredCustomer` nếu `PreferredCustomer` là kiểu con. Nhưng một danh sách có thể ghi thêm mọi `Customer` không thể an toàn thay bằng danh sách chỉ nhận `PreferredCustomer`.

DSL không cần hỗ trợ covariance hoặc contravariance nếu không có generic hoặc collection type. Nếu có, cần định nghĩa rõ variance của tham chiếu và cách kiểm tra khi gán hoặc truyền tham số.

### Kiểu tham chiếu có thể khác kiểu đích thực tế

Một biến có kiểu tham chiếu là `Customer` có thể trỏ đến một đối tượng thực tế thuộc kiểu `PreferredCustomer`. Kiểm tra tĩnh xác nhận kiểu khai báo tương thích; kiểm tra runtime có thể xác nhận loại đối tượng thực tế nếu DSL hỗ trợ dynamic dispatch hoặc dữ liệu động.

## 6. Ràng buộc phạm vi và khả năng truy cập

Đích tồn tại và đúng kiểu vẫn có thể không được phép tham chiếu từ nguồn hiện tại.

### Lexical scope

Một biến cục bộ chỉ có thể được tham chiếu trong phạm vi có hiệu lực. Ví dụ:

~~~text
workflow Process {
    if order.isPaid {
        let receipt = createReceipt(order);
        sendReceipt(receipt);
    }

    archive(receipt); // ngoài phạm vi của receipt
}
~~~

Nếu `receipt` chỉ tồn tại trong block của `if`, tham chiếu bên ngoài không hợp lệ. Đây là lỗi phạm vi, dù khai báo `receipt` có tồn tại ở nơi khác trong tài liệu.

### Visibility

Một module có thể khai báo thành phần `public`, `internal` hoặc `private`:

~~~text
module Finance {
    public entity Invoice { ... }
    private action RecalculateLedger { ... }
}

module Billing {
    import Finance;
    use Finance.Invoice;
    use Finance.RecalculateLedger; // không được phép nếu private
}
~~~

Ràng buộc visibility kiểm tra quyền truy cập theo module, package, namespace hoặc vai trò. Diagnostic nên trỏ đến tham chiếu và có thể chỉ ra khai báo đích cùng mức visibility.

### Namespace và qualified reference

Khi nhiều module có tên giống nhau, qualified name giúp xác định đích:

~~~text
Finance.Invoice
Sales.Invoice
~~~

Compiler cần kiểm tra từng phần của đường dẫn: namespace gốc tồn tại, thành phần con được export, kiểu cuối cùng phù hợp và không có alias xung đột.

### Import và dependency

Một tham chiếu qua module chỉ hợp lệ nếu module được import hoặc nằm trong dependency graph được phép. Không nên để một module truy cập mọi khai báo trên classpath hoặc trong kho dữ liệu chỉ vì chúng có cùng tên.

## 7. Ràng buộc số lượng liên kết (cardinality)

Cardinality quy định số lượng đích mà một tham chiếu hoặc quan hệ có thể có. Đây là một ràng buộc quan trọng trong DSL mô hình hóa dữ liệu, quy trình và quan hệ giữa thực thể.

Các dạng thường gặp:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `0..1` | Không có hoặc có tối đa một đích. | Một đơn hàng có thể chưa gán người giao. |
| `1` hoặc `1..1` | Bắt buộc đúng một đích. | Mỗi hóa đơn thuộc về một khách hàng. |
| `0..*` | Không có giới hạn trên. | Một khách hàng có thể có nhiều đơn hàng. |
| `1..*` | Ít nhất một đích. | Một workflow phải có ít nhất một bước. |
| `2..5` | Từ hai đến năm đích. | Một yêu cầu cần từ hai đến năm người duyệt. |

Ví dụ:

~~~text
entity Customer {
    orders: Order[0..*];
}

entity Order {
    customer: Customer[1];
}
~~~

Mỗi `Order` phải tham chiếu đúng một `Customer`; một `Customer` có thể được nhiều `Order` tham chiếu.

### Kiểm tra cardinality tĩnh và động

Nếu mô hình khai báo tường minh các liên kết, compiler có thể đếm và kiểm tra ngay. Nếu liên kết được tạo trong lúc chạy, cardinality có thể cần được kiểm tra tại runtime hoặc khi lưu giao dịch.

Ví dụ, một workflow khai báo ba nhánh phê duyệt có thể được kiểm tra tĩnh. Một đơn hàng chỉ được gán người duyệt sau khi nhận dữ liệu thực tế thì cần kiểm tra ở thời điểm tạo hoặc cập nhật.

### Cardinality của tham số

Một hành động có thể nhận một hoặc nhiều đối tượng:

~~~text
action Approve(order: Order, reviewers: Reviewer[2..3]);
~~~

Lời gọi phải truyền đúng một `Order` và từ hai đến ba `Reviewer`. Nếu tham số collection có thể chứa null hoặc phần tử trùng, đó là các ràng buộc riêng cần được đặc tả.

## 8. Ràng buộc duy nhất và tham chiếu trùng lặp

Một collection tham chiếu có thể yêu cầu không có cùng một đích xuất hiện nhiều lần.

~~~text
entity ApprovalRequest {
    reviewers: Set<Reviewer>;
}
~~~

Nếu DSL dùng `Set`, tính duy nhất có thể được bảo đảm bởi kiểu dữ liệu. Nếu dùng `List`, có thể cần ràng buộc riêng:

~~~text
constraint UniqueReviewers on ApprovalRequest {
    reviewers.distinctBy(reviewer.id).count == reviewers.count;
}
~~~

Khóa so sánh cần được định nghĩa. Hai đối tượng khác nhau trong bộ nhớ có thể đại diện cùng một thực thể nghiệp vụ nếu có cùng ID. Ngược lại, hai đối tượng có cùng một số thuộc tính không nhất thiết là cùng một thực thể. DSL cần quy định uniqueness dựa trên identity, khóa tự nhiên hay giá trị.

### Tham chiếu duy nhất đến một đích

Một quan hệ có thể yêu cầu mỗi đích chỉ được gắn với tối đa một nguồn:

~~~text
constraint OneActiveAssignmentPerDevice {
    for each device in Devices:
        count(Assignments where device == device and active) <= 1;
}
~~~

Đây là ràng buộc toàn cục giữa nhiều phần tử. Kiểm tra một tham chiếu riêng lẻ là chưa đủ; validator cần xem xét tập dữ liệu hoặc mô hình có liên quan.

## 9. Referential integrity – tính toàn vẹn tham chiếu

Tính toàn vẹn tham chiếu bảo đảm một liên kết không trỏ đến đích không còn hợp lệ. Khái niệm này thường gặp trong cơ sở dữ liệu, nhưng cũng áp dụng cho mô hình DSL, workflow, tài liệu cấu hình và đồ thị thành phần.

Ví dụ, `Order.customerId` tham chiếu đến một `Customer`. Nếu khách hàng bị xóa trong khi đơn hàng vẫn còn, liên kết có thể trở thành dangling reference.

### Các quy tắc khi đích bị xóa

Khi một phần tử đang được tham chiếu bị xóa, DSL hoặc công cụ quản lý mô hình có thể chọn:

- **Restrict:** từ chối xóa nếu còn tham chiếu.
- **Cascade delete:** xóa các phần tử phụ thuộc theo quy tắc sở hữu.
- **Set null:** đặt tham chiếu tùy chọn về rỗng.
- **Reassign:** yêu cầu người dùng chọn một đích thay thế.
- **Mark unresolved:** giữ liên kết nhưng đánh dấu chưa phân giải, nếu mô hình cho phép trạng thái này.

Không nên áp dụng cascade delete cho mọi cross-reference. Nếu một khách hàng được nhiều đơn hàng tham chiếu, xóa khách hàng có thể làm mất dữ liệu nghiệp vụ quan trọng. Quy tắc cần phân biệt containment với liên kết tham chiếu độc lập.

### Tham chiếu đến phiên bản

Một workflow có thể tham chiếu đến phiên bản policy cụ thể:

~~~text
workflow OrderReview {
    uses policy FraudPolicy@v3;
}
~~~

Nếu `v3` bị xóa hoặc không còn được phép sử dụng, tham chiếu có thể mất tính hợp lệ. Một số hệ thống giữ artifact phiên bản bất biến để bảo đảm workflow lịch sử có thể replay. Chính sách vòng đời cần được định nghĩa rõ.

### Dangling reference

Dangling reference là tham chiếu có thông tin liên kết nhưng không còn tìm được đích. Nó có thể xuất hiện khi:

- Phần tử đích bị xóa.
- ID bị đổi hoặc dữ liệu được nhập thiếu.
- Module chứa đích không được tải.
- Tệp được di chuyển mà tham chiếu không được cập nhật.
- Kho dữ liệu bên ngoài không đồng bộ.

Validator cần phân biệt đích thực sự không tồn tại với đích tạm thời chưa được tải.

## 10. Ràng buộc hai chiều (bidirectional references)

Một quan hệ có thể được biểu diễn ở cả hai phía. Ví dụ, `Order.customer` và `Customer.orders` có thể mô tả cùng một liên kết.

~~~text
entity Order {
    customer: Customer[1] opposite orders;
}

entity Customer {
    orders: Order[0..*] opposite customer;
}
~~~

Nếu một đơn hàng tham chiếu đến khách hàng A, danh sách `A.orders` cần phản ánh đơn hàng đó. Hai phía phải nhất quán.

### Đồng bộ hai đầu quan hệ

Nếu người dùng sửa `order.customer`, hệ thống có thể tự cập nhật `customer.orders`. Nếu người dùng sửa `customer.orders`, hệ thống có thể cập nhật lại `order.customer`. DSL hoặc model runtime phải xác định một nguồn sự thật và quy tắc đồng bộ để tránh vòng lặp cập nhật.

### Kiểm tra tính nhất quán

Một validator có thể kiểm tra:

~~~text
for each order in Orders:
    assert order in order.customer.orders;

for each customer in Customers:
    for each order in customer.orders:
        assert order.customer == customer;
~~~

Các biểu thức trên minh họa tính hai chiều; cú pháp thực tế phụ thuộc DSL. Với dữ liệu lớn, nên xây dựng chỉ mục hoặc kiểm tra theo các thay đổi thay vì duyệt toàn bộ mô hình sau mỗi thao tác.

### Quan hệ hai chiều không có nghĩa hai collection giống nhau

Một phía có thể là tham chiếu đơn, phía kia là collection nhiều phần tử. Ví dụ `Order.customer` có cardinality 1, còn `Customer.orders` có cardinality 0..*. Hai phía mô tả cùng một quan hệ nhưng hình dạng dữ liệu khác nhau.

## 11. Ràng buộc vòng đời và trạng thái đích

Một đích có thể tồn tại nhưng không ở trạng thái được phép tham chiếu.

Ví dụ, DSL quản lý workflow có các trạng thái `Draft`, `Published`, `Retired`:

~~~text
workflow OrderProcessing {
    uses workflow PaymentAuthorization@Published;
}
~~~

Tham chiếu có thể yêu cầu workflow đích đã được publish. Nếu nó đang ở trạng thái Draft hoặc Retired, liên kết có thể không hợp lệ đối với một workflow production.

Các ràng buộc vòng đời có thể gồm:

- Chỉ tham chiếu đến phiên bản đã publish.
- Không tham chiếu đến đối tượng đã archived hoặc deleted.
- Không dùng component đã hết hạn trong workflow mới.
- Không dùng policy có hiệu lực trong tương lai hoặc đã hết hiệu lực tại thời điểm thực thi.
- Chỉ cho phép liên kết giữa các thành phần thuộc cùng tenant hoặc môi trường.

### Thời điểm kiểm tra lifecycle

Có ràng buộc cần kiểm tra khi thiết kế hoặc compile; có ràng buộc cần kiểm tra lúc publish; có ràng buộc cần kiểm tra lại khi thực thi vì trạng thái đích có thể thay đổi. Ví dụ, một người phê duyệt có thể hợp lệ lúc cấu hình workflow nhưng bị khóa trước thời điểm đơn hàng được xử lý.

Do đó, đặc tả cần nêu rõ tính hợp lệ là bất biến tĩnh hay phụ thuộc trạng thái động.

## 12. Ràng buộc chu kỳ trong đồ thị tham chiếu

Các tham chiếu giữa phần tử có thể tạo thành đồ thị. Một số quan hệ cho phép chu kỳ, một số quan hệ yêu cầu đồ thị không chu kỳ (*acyclic*).

### Ví dụ chu kỳ kế thừa

~~~text
type A extends B;
type B extends C;
type C extends A;
~~~

Nếu kế thừa kiểu yêu cầu đồ thị có hướng không chu kỳ, chu kỳ `A -> B -> C -> A` là không hợp lệ. Compiler cần phát hiện và chỉ ra các cạnh tham chiếu tạo chu kỳ.

### Ví dụ dependency workflow

~~~text
task Prepare dependsOn Validate;
task Validate dependsOn Reserve;
task Reserve dependsOn Prepare;
~~~

Nếu quan hệ `dependsOn` được dùng để xác định thứ tự thực hiện, chu kỳ có thể khiến không có thứ tự topo hợp lệ.

### Không phải mọi chu kỳ đều sai

Quan hệ hai chiều như `Order.customer` và `Customer.orders` có thể tạo đường đi quay lại cùng đối tượng nhưng không nhất thiết là chu kỳ sai. Một đồ thị object có thể chứa chu kỳ hợp lệ. Cần kiểm tra theo **loại quan hệ** và quy tắc miền, không cấm mọi chu kỳ một cách tổng quát.

Ví dụ, kế thừa có thể yêu cầu acyclic; liên kết bạn bè có thể cho phép chu kỳ; quan hệ parent-child có thể yêu cầu không tạo chu kỳ; graph workflow có thể cho phép vòng lặp nếu có điều kiện dừng được định nghĩa.

### Phát hiện chu kỳ

Với đồ thị có hướng, có thể dùng DFS với ba trạng thái:

- `WHITE`: chưa thăm.
- `GRAY`: đang nằm trên đường DFS hiện tại.
- `BLACK`: đã xử lý xong.

Nếu duyệt một cạnh đến node `GRAY`, đã phát hiện chu kỳ. Thuật toán có độ phức tạp `O(V + E)` với `V` là số đỉnh và `E` là số cạnh trong đồ thị được kiểm tra.

Một cách khác là dùng thuật toán strongly connected components (SCC) để tìm các thành phần liên thông mạnh. Thành phần có nhiều hơn một đỉnh hoặc có self-loop thể hiện chu kỳ. SCC hữu ích khi cần báo cáo nhiều nhóm chu kỳ trong mô hình.

## 13. Ràng buộc tham chiếu trong mô hình đồ thị và workflow

DSL đồ họa thường biểu diễn tham chiếu bằng edge giữa các node. Một edge không chỉ cần hai đầu mút tồn tại; nó còn phải nối đúng cổng và thỏa điều kiện tương thích.

Ví dụ:

~~~text
node Start: StartEvent;
node Approve: ApprovalTask;
node Notify: NotificationTask;

connect Start.output -> Approve.input;
connect Approve.approved -> Notify.input;
~~~

Các ràng buộc có thể gồm:

- Cả node nguồn và node đích đều tồn tại.
- Cổng nguồn và cổng đích tồn tại trên node tương ứng.
- Kiểu dữ liệu hoặc loại sự kiện của hai cổng tương thích.
- Cổng chỉ nhận một kết nối không được nhận nhiều edge.
- Edge không được nối từ output sang output hoặc input sang input.
- Node bắt buộc phải có đường vào hoặc đường ra.
- Đồ thị phải có một entry point và một hoặc nhiều exit point theo quy tắc.
- Một số loại cycle được cho phép, một số loại bị cấm.

### Kiểm tra kiểu cổng

Nếu `Approve.approved` phát ra sự kiện `ApprovalResult` còn `Notify.input` chỉ nhận `Text`, kết nối có thể sai kiểu. Bộ kiểm tra cần trỏ đến edge hoặc cổng gây lỗi và chỉ ra kiểu nguồn/đích.

### Kiểm tra số lượng kết nối

Một node có thể có cổng `input` bắt buộc đúng một edge, còn cổng `error` có thể không có hoặc có một edge. Cardinality của edge là một ràng buộc tham chiếu giữa node và cổng.

### Kiểm tra khả năng đi tới

Một node tồn tại nhưng không thể được đi tới từ entry point có thể là cấu trúc chết. Đây không phải lỗi tham chiếu cơ bản mà là ràng buộc ngữ nghĩa trên đồ thị. Validator cần phân biệt “edge trỏ đến node không tồn tại” với “node tồn tại nhưng không reachable”.

## 14. Ràng buộc tham chiếu trong DSL mô hình dữ liệu

DSL mô hình dữ liệu thường mô tả entity, thuộc tính, quan hệ và khóa. Ràng buộc tham chiếu giúp bảo đảm các quan hệ nhất quán.

### Quan hệ một-nhiều

~~~text
entity Customer {
    id: CustomerId key;
    orders: Order[0..*] opposite customer;
}

entity Order {
    id: OrderId key;
    customer: Customer[1] opposite orders;
}
~~~

Mỗi `Order` phải tham chiếu một `Customer`; một `Customer` có thể có nhiều `Order`. Nếu một `Customer` bị xóa, chính sách delete cần xử lý các đơn liên quan.

### Khóa ngoại

Một tham chiếu có thể được triển khai bằng foreign key:

~~~text
Order.customerId -> Customer.id
~~~

Khi lưu dữ liệu, database có thể bảo đảm khóa ngoại trỏ đến một hàng tồn tại. Tuy nhiên, kiểm tra trong DSL vẫn cần xác nhận kiểu khóa, phạm vi tenant, quyền truy cập và chính sách xóa.

### Khóa ghép và định danh

Một đích có thể được xác định bằng khóa ghép:

~~~text
reference product by (tenantId, productCode);
~~~

Ràng buộc cần xác nhận toàn bộ tổ hợp khóa là duy nhất và thuộc cùng phạm vi dữ liệu. Chỉ kiểm tra `productCode` có thể không đủ nếu mã chỉ duy nhất trong từng tenant.

### Quan hệ có thuộc tính

Một quan hệ có thể chứa dữ liệu riêng, ví dụ `Membership` liên kết `User` với `Team` và lưu vai trò:

~~~text
entity Membership {
    user: User[1];
    team: Team[1];
    role: TeamRole;
}
~~~

Ràng buộc có thể yêu cầu một cặp `(user, team)` chỉ có một Membership đang hiệu lực. Đây là uniqueness trên quan hệ, không chỉ trên một tham chiếu riêng lẻ.

## 15. Ràng buộc tham chiếu giữa module và phiên bản

DSL lớn thường chia thành nhiều module hoặc package. Một tham chiếu xuyên module cần tuân thủ dependency và version constraints.

Ví dụ:

~~~text
module OrderService {
    requires CustomerModel version "2.x";
    import CustomerModel.Customer;
}
~~~

Các điều kiện có thể gồm:

- Module đích tồn tại trong dependency graph.
- Phiên bản được chọn thỏa version range.
- Symbol được export từ module đích.
- Không có dependency cycle nếu hệ thống cấm.
- Không có hai phiên bản không tương thích của cùng module trong một context.
- Tham chiếu không vượt qua ranh giới tenant hoặc môi trường bị cấm.

### Version range

Một module có thể yêu cầu phiên bản tương thích như `2.x` hoặc `>=2.1 <3.0`. Bộ phân giải dependency cần chọn một phiên bản cụ thể và ghi nhận nó để build có thể tái lập. Nếu chỉ dùng “latest”, cùng source có thể phân giải đến API khác nhau theo thời gian.

### API compatibility

Module đích có thể tồn tại nhưng đã đổi chữ ký hoặc xóa symbol. Ràng buộc tham chiếu cần xác nhận API mà module nguồn sử dụng vẫn được cung cấp trong phiên bản được chọn. Một tham chiếu tên còn tồn tại nhưng đổi kiểu hoặc cardinality vẫn có thể làm module nguồn không tương thích.

## 16. Tham chiếu ngoài và liên kết đến hệ thống khác

Một DSL có thể tham chiếu đến tài nguyên bên ngoài như URL, API endpoint, bảng dữ liệu, topic sự kiện hoặc định danh dịch vụ.

Ví dụ:

~~~text
connector PaymentGateway {
    endpoint: service("payments.authorize");
}

workflow CapturePayment {
    call PaymentGateway.authorize(order.payment);
}
~~~

Tham chiếu ngoài cần các ràng buộc riêng:

- Định danh hoặc URI có cú pháp hợp lệ.
- Connector hoặc dịch vụ đích đã được cấu hình.
- API hoặc operation tồn tại trong phiên bản được khai báo.
- Kiểu request/response tương thích.
- Nguồn tham chiếu được phép truy cập đích theo chính sách.
- Secret hoặc credential cần thiết được quản lý ngoài mã DSL.
- Đích có thể không sẵn sàng lúc compile; cần phân biệt kiểm tra cấu hình với kiểm tra kết nối thực tế.

### Static validation và connectivity check

Compiler có thể kiểm tra cấu trúc endpoint, tên operation và schema request mà không gọi dịch vụ. Kiểm tra dịch vụ có phản hồi hay không thường là health check hoặc validation lúc triển khai. Không nên biến mọi lần compile thành một lời gọi mạng bắt buộc nếu điều đó làm build phụ thuộc trạng thái dịch vụ.

### Trust boundary

Tham chiếu đến plugin, script hoặc service bên ngoài có thể vượt qua ranh giới tin cậy. DSL cần xác định nguồn nào được phép, quyền nào cần có và cách xác thực schema. Một tên tồn tại không đồng nghĩa tài nguyên đó an toàn để gọi.

## 17. Ràng buộc tham chiếu và điều kiện nghiệp vụ

Một tham chiếu có thể hợp lệ về cấu trúc nhưng không hợp lệ theo nghiệp vụ.

Ví dụ:

~~~text
entity Order {
    customer: Customer[1];
}

constraint OrderCustomerCanPurchase {
    order.customer.accountStatus == ACTIVE;
}
~~~

Tham chiếu `order.customer` có thể tồn tại và đúng kiểu `Customer`, nhưng nếu tài khoản khách hàng đã bị khóa thì thao tác mua hàng không được phép.

Một số ràng buộc miền:

- Người phê duyệt phải thuộc đơn vị quản lý đơn hàng.
- Người giao hàng phải được phân công trong vùng phục vụ.
- Sản phẩm phải thuộc catalog đang mở bán.
- Tài khoản thanh toán phải thuộc cùng khách hàng hoặc tổ chức.
- Một bước workflow chỉ được gọi service đã được phê duyệt.
- Một policy chỉ được tham chiếu đến model có phiên bản tương thích.

### Ràng buộc phụ thuộc dữ liệu

Điều kiện nghiệp vụ có thể phụ thuộc dữ liệu đang thay đổi. Ví dụ, người phê duyệt có thể hợp lệ khi thiết kế workflow nhưng bị vô hiệu hóa trước lúc xử lý đơn. DSL cần quy định ràng buộc được kiểm tra ở thời điểm nào và có cần kiểm tra lại trước khi thực hiện hành động không.

### Phân biệt lỗi cấu trúc và lỗi trạng thái

Nếu tham chiếu trỏ đến một symbol không tồn tại trong model, đó thường là lỗi cấu trúc hoặc phân giải. Nếu symbol tồn tại nhưng đối tượng đang ở trạng thái không cho phép thao tác, đó là lỗi trạng thái hoặc nghiệp vụ. Tách hai loại giúp thông báo đúng và xác định nơi cần sửa.

## 18. Ràng buộc tham chiếu tĩnh và động

Không phải mọi điều kiện đều có thể kiểm tra tại thời điểm compile.

### Kiểm tra tĩnh

Có thể kiểm tra tĩnh khi thông tin cần thiết đã có trong AST, symbol table, type model hoặc dependency graph:

- Tên đích có được khai báo không?
- Loại đích có phù hợp không?
- Phạm vi và visibility có cho phép không?
- Cardinality của các liên kết được khai báo tường minh có đúng không?
- Đồ thị kế thừa có chu kỳ không?
- Module dependency có thỏa phiên bản không?

### Kiểm tra lúc tải hoặc xác thực mô hình

Một số tham chiếu chỉ có thể kiểm tra khi mô hình dữ liệu đã được tải:

- ID đích có tồn tại trong repository không?
- Các liên kết hai chiều có nhất quán không?
- Có vi phạm uniqueness trên toàn bộ mô hình không?
- Các node workflow có được kết nối đầy đủ không?

### Kiểm tra lúc chạy

Một số điều kiện phụ thuộc dữ liệu và trạng thái thực tế:

- Đối tượng đích còn hoạt động không?
- Người dùng hiện tại có quyền truy cập không?
- Dịch vụ ngoài có khả dụng không?
- Số lượng tham chiếu thực tế có nằm trong giới hạn không?
- Quan hệ có còn hợp lệ sau một cập nhật đồng thời không?

### Bảng phân loại

| Thời điểm | Ví dụ | Công cụ thực hiện |
|---|---|---|
| Compile-time | Tên action không tồn tại, sai kiểu tham số | Name resolver, type checker. |
| Model load/validation | Dangling ID, quan hệ hai chiều không khớp | Model validator, repository layer. |
| Publish/deploy | Module sai phiên bản, workflow chưa publish | Build/deployment validator. |
| Runtime | Đích bị xóa, quyền thay đổi, service không sẵn sàng | Interpreter, runtime guard, service adapter. |

Một ràng buộc có thể được kiểm tra ở nhiều giai đoạn. Ví dụ, compiler xác nhận một tham chiếu đến `Customer` có kiểu đúng; runtime vẫn kiểm tra customer ID thực tế có tồn tại và người gọi có quyền truy cập.

## 19. Đặc tả ràng buộc tham chiếu

Ràng buộc nên được biểu diễn bằng quy tắc rõ ràng, có thể kiểm tra và giải thích. DSL có thể dùng type declaration, multiplicity, constraint expression hoặc một ngôn ngữ truy vấn.

### Khai báo quan hệ bằng kiểu và multiplicity

~~~text
entity Order {
    customer: Customer[1];
    approvers: Reviewer[1..3];
    optionalShipment: Shipment[0..1];
}
~~~

Kiểu đích và multiplicity mô tả một phần hợp đồng tham chiếu. Compiler hoặc model validator có thể kiểm tra dữ liệu thực tế có thỏa số lượng liên kết hay không.

### Constraint expression

~~~text
constraint EveryOrderHasCustomer on Order {
    self.customer != null;
}

constraint ReviewersAreUnique on Order {
    self.approvers.distinctBy(id).count == self.approvers.count;
}
~~~

Biểu thức ràng buộc có thể kiểm tra các thuộc tính không thể diễn đạt chỉ bằng kiểu và multiplicity. DSL cần quy định giá trị null, cách xử lý collection rỗng và liệu biểu thức constraint có được phép có tác dụng phụ hay không. Thông thường, constraint nên thuần để kết quả kiểm tra ổn định.

### Ràng buộc tham chiếu trong mô hình đồ thị

~~~text
constraint CompatiblePorts on Edge {
    self.source.outputType isAssignableTo self.target.inputType;
}

constraint SingleIncomingEdge on InputPort {
    incomingEdges.count <= 1;
}
~~~

Các ví dụ này mô tả quan hệ giữa edge và port. Cú pháp cụ thể có thể khác, nhưng cần nêu rõ đối tượng ngữ cảnh của `self` và cách truy cập các liên kết.

## 20. Thứ tự kiểm tra và phụ thuộc giữa các ràng buộc

Các ràng buộc tham chiếu có thể phụ thuộc nhau. Không nên kiểm tra một ràng buộc đòi hỏi đích đã được phân giải trước khi hoàn thành bước phân giải tên.

Một pipeline thường có thể gồm:

1. Parse văn bản hoặc đọc mô hình đầu vào.
2. Thu thập khai báo và xây dựng namespace/scope.
3. Phân giải các tham chiếu tường minh.
4. Kiểm tra loại symbol, visibility và kiểu.
5. Xây dựng đồ thị quan hệ hoặc chỉ mục liên kết.
6. Kiểm tra existence, cardinality, uniqueness và integrity.
7. Kiểm tra chu kỳ, tính liên thông hoặc các thuộc tính toàn cục.
8. Kiểm tra ràng buộc nghiệp vụ cần dữ liệu hoặc trạng thái bổ sung.
9. Tổng hợp diagnostic và vị trí liên quan.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A[Source / Model] --> B[Parse]
    B --> C[Collect declarations]
    C --> D[Resolve references]
    D --> E[Check kind, scope and type]
    E --> F[Build reference graph]
    F --> G[Check existence, cardinality and uniqueness]
    G --> H[Check integrity, cycles and domain rules]
    H --> I[Diagnostics with source locations]
~~~

Thứ tự thực tế phụ thuộc DSL. Một số ràng buộc có thể kiểm tra song song sau khi các dependency đã sẵn sàng. Nếu một tham chiếu chưa phân giải, các kiểm tra phụ thuộc vào đích đó nên được bỏ qua hoặc đánh dấu là chưa thể kết luận để tránh tạo nhiều lỗi thứ cấp.

## 21. Thuật toán kiểm tra tham chiếu

### Tra cứu đích

Với tham chiếu dựa trên tên, bộ phân giải tra symbol table theo scope và namespace. Với tham chiếu dựa trên ID, hệ thống tra repository hoặc index. Cần phân biệt kết quả không tìm thấy với kết quả chưa tải hoặc không được phép truy cập.

### Kiểm tra cardinality

Với một collection, có thể đếm số liên kết `k` và so sánh với giới hạn `[min, max]`:

~~~text
min <= k <= max
~~~

Nếu collection lớn hoặc dữ liệu nằm trong database, có thể dùng truy vấn đếm hoặc constraint ở tầng lưu trữ. Cần bảo đảm dữ liệu không thay đổi giữa lúc kiểm tra và lúc ghi nếu tính toàn vẹn cần được bảo vệ đồng thời.

### Kiểm tra uniqueness

Có thể xây dựng set các khóa đã gặp:

~~~text
seen = empty set

for each reference in references:
    key = identityKey(reference.target)
    if key in seen:
        report duplicate reference
    else:
        seen.add(key)
~~~

Thuật toán có thời gian trung bình `O(n)` với hash set, giả sử thao tác hash và so sánh có chi phí hằng số. Nếu khóa không hash được hoặc cần thứ tự ổn định, có thể dùng sort rồi kiểm tra phần tử liền kề với chi phí `O(n log n)`.

### Kiểm tra chu kỳ

Với quan hệ yêu cầu DAG, DFS hoặc SCC có thể phát hiện chu kỳ trong `O(V + E)`. Diagnostic nên giữ đường đi hoặc tập cạnh tạo chu kỳ để người dùng biết những tham chiếu nào cần sửa.

### Kiểm tra quan hệ hai chiều

Có thể duyệt một phía và xác nhận mỗi liên kết có phần tử nghịch đảo tương ứng. Dùng index theo ID giúp tránh tìm tuyến tính cho từng phần tử. Với mô hình lớn, validator có thể chỉ kiểm tra các liên kết bị ảnh hưởng bởi thay đổi gần nhất.

## 22. Xử lý tham chiếu chưa phân giải và mô hình từng phần

Trong IDE, dự án có thể chưa hoàn chỉnh: người dùng đang gõ tên, module chưa tải, file import đang được tạo hoặc repository đang đồng bộ. Một validator tốt cần phân biệt trạng thái chưa hoàn tất với lỗi chắc chắn.

Các trạng thái có thể gồm:

- `RESOLVED`: tìm được đích và đã kiểm tra.
- `UNRESOLVED`: không tìm được đích sau khi tra cứu hoàn tất.
- `PENDING`: nguồn hoặc dependency chưa sẵn sàng.
- `INACCESSIBLE`: đích tồn tại nhưng không được phép truy cập.
- `INVALID_TYPE`: đích tồn tại nhưng sai loại hoặc kiểu.
- `AMBIGUOUS`: có nhiều đích cùng phù hợp.

Ví dụ, người dùng đang gõ `approveOr` và chưa hoàn thành tên. IDE có thể hiển thị completion mà không lập tức phát lỗi nghiêm trọng. Khi tài liệu đã được lưu hoặc compile, tên chưa phân giải có thể trở thành error.

### Proxy hoặc lazy reference

Một mô hình lớn có thể lưu tham chiếu dưới dạng proxy chứa ID hoặc URI và chỉ tải đối tượng đích khi cần. Khi đó, validator cần biết proxy đã được tải, tải thất bại hay đích không tồn tại. Không nên nhầm trạng thái “chưa tải” với “dangling reference”.

### Chính sách khi build và publish

IDE có thể chấp nhận trạng thái pending để người dùng tiếp tục làm việc. Build hoặc publish thường cần mức xác thực nghiêm ngặt hơn và có thể từ chối mọi tham chiếu chưa phân giải. Hai chế độ nên dùng cùng quy tắc ngữ nghĩa nhưng khác chính sách xử lý trạng thái chưa hoàn tất.

## 23. Ràng buộc tham chiếu và cập nhật mô hình

Một mô hình có thể hợp lệ trước khi chỉnh sửa và không hợp lệ sau khi một phần tử bị đổi tên, di chuyển hoặc xóa. Các thao tác chỉnh sửa cần cập nhật hoặc xác thực lại những tham chiếu phụ thuộc.

### Rename

Đổi tên một phần tử cần cập nhật mọi tham chiếu đến symbol đó. Công cụ nên dựa trên symbol identity, không tìm và thay mọi chuỗi có cùng ký tự. Comment hoặc string literal có thể chứa cùng tên nhưng không phải tham chiếu.

### Move

Di chuyển một khai báo sang module khác có thể làm thay đổi visibility, namespace và dependency. Một tham chiếu từng hợp lệ có thể cần import mới hoặc qualified name.

### Delete

Xóa đích có thể tạo dangling reference. Công cụ cần áp dụng chính sách restrict, cascade, set null hoặc yêu cầu người dùng sửa các liên kết.

### Copy

Sao chép một mô hình có thể cần tạo ID mới cho các phần tử được copy, đồng thời quyết định tham chiếu nào giữ nguyên đích cũ và tham chiếu nào trỏ đến bản copy. Quyết định này phụ thuộc semantics của containment và cross-reference.

### Refactoring an toàn

Một thao tác refactoring nên:

1. Xác định symbol hoặc phần tử đích.
2. Tìm tất cả tham chiếu theo identity.
3. Tính các thay đổi cần thiết.
4. Kiểm tra visibility, kiểu và integrity sau thay đổi.
5. Áp dụng thay đổi theo giao dịch hoặc snapshot.
6. Báo lỗi nếu thao tác làm mô hình vi phạm ràng buộc không thể tự sửa.

## 24. Kiểm tra gia tăng các ràng buộc tham chiếu

Với mô hình lớn, kiểm tra toàn bộ ràng buộc sau mỗi chỉnh sửa có thể tốn kém. Incremental validation chỉ kiểm tra những ràng buộc có thể bị ảnh hưởng bởi thay đổi.

Ví dụ, nếu người dùng đổi `order.customer` từ Customer A sang Customer B, các kiểm tra liên quan có thể gồm:

- Kiểu của Customer B.
- Customer B có tồn tại và được truy cập không.
- Cardinality của quan hệ mới.
- Danh sách `CustomerA.orders` và `CustomerB.orders` có được cập nhật không.
- Ràng buộc một đơn hàng thuộc đúng một khách hàng.
- Các điều kiện nghiệp vụ phụ thuộc khách hàng.

Không nhất thiết phải kiểm tra lại mọi workflow hoặc mọi entity không phụ thuộc vào quan hệ này.

### Dependency graph của validator

Validator có thể duy trì đồ thị phụ thuộc từ phần tử nguồn đến các ràng buộc cần kiểm tra. Khi một phần tử thay đổi, hệ thống đánh dấu các validator liên quan là dirty rồi chạy lại chúng.

### Giữ đúng tính nhất quán

Tối ưu gia tăng không được bỏ sót ràng buộc toàn cục. Ví dụ, đổi một khóa ID có thể ảnh hưởng uniqueness trên toàn repository. Nếu không có chỉ mục hoặc dependency tracking đủ mạnh, hệ thống cần chạy kiểm tra rộng hơn hoặc trì hoãn xác nhận đến giai đoạn commit.

### Snapshot và concurrent update

Nếu hai người dùng cùng chỉnh sửa mô hình, một kiểm tra tham chiếu trên snapshot cũ có thể không còn đúng khi ghi. Các ràng buộc quan trọng cần được xác nhận lại trong giao dịch hoặc bằng cơ chế optimistic concurrency, unique constraint và foreign key ở tầng lưu trữ.

## 25. Diagnostic cho ràng buộc tham chiếu

Thông báo lỗi nên chỉ rõ tham chiếu nào sai, ràng buộc nào bị vi phạm và nếu có thể thì đích hoặc khai báo liên quan nằm ở đâu.

### Tham chiếu không tồn tại

~~~text
policies/order.dsl:8:10: error DSL3001: Unknown action 'ApproveOrdr'.
  call ApproveOrdr(order);
       ^^^^^^^^^^^
  help: Did you mean 'ApproveOrder'?
~~~

### Sai kiểu đích

~~~text
error DSL3004: Expected an Action reference, but 'Customer' resolves to an Entity.
~~~

### Vi phạm cardinality

~~~text
error DSL3010: 'Order.customer' requires exactly one Customer reference; found none.
~~~

### Tham chiếu bị xóa

~~~text
error DSL3020: Reference to Customer#C104 is unresolved because the target was deleted.
  Referencing element: Order#O882.customer
~~~

### Chu kỳ

~~~text
error DSL3030: Inheritance cycle detected: A -> B -> C -> A.
  A extends B at model.dsl:4
  B extends C at model.dsl:9
  C extends A at model.dsl:14
~~~

Diagnostic có thể có primary location tại tham chiếu gây lỗi và related locations tại khai báo đích, khai báo xung đột hoặc các cạnh tạo chu kỳ. Với lỗi runtime, có thể thêm execution ID hoặc object ID thay vì đưa dữ liệu nhạy cảm vào message.

## 26. Vị trí nguồn và tham chiếu trong IDE

IDE cần giữ liên kết từ AST hoặc model node đến vị trí văn bản để hiển thị diagnostic và hỗ trợ điều hướng.

Các tính năng hữu ích:

- Go to Definition đưa người dùng đến khai báo đích.
- Find References liệt kê mọi nguồn đang trỏ đến một phần tử.
- Rename cập nhật đúng các tham chiếu theo identity.
- Hover hiển thị loại, cardinality, visibility và trạng thái phân giải.
- Diagnostic tô sáng tham chiếu vi phạm.
- Quick Fix đề xuất import, qualified name, đổi tên hoặc chọn đích thay thế.
- Model explorer hiển thị nguồn và đích của một quan hệ.

Nếu DSL hỗ trợ nhiều tệp, mỗi reference phải giữ source ID và target ID. Không nên chỉ lưu chuỗi tên vì cùng một tên có thể xuất hiện trong nhiều namespace hoặc scope.

## 27. Kiểm thử ràng buộc tham chiếu

Kiểm thử nên bao phủ từng loại ràng buộc và cả tương tác giữa chúng.

| Nhóm kiểm thử | Trường hợp |
|---|---|
| Existence | Đích tồn tại, không tồn tại, chưa tải và bị xóa. |
| Type/kind | Đúng loại, sai loại, kiểu con, kiểu không tương thích. |
| Scope/visibility | Cùng scope, scope cha, module import, private/public. |
| Cardinality | Không có, đúng giới hạn, dưới min và vượt max. |
| Uniqueness | Đích trùng theo ID, trùng theo khóa tự nhiên và khác identity. |
| Referential integrity | Xóa đích, đổi ID, import/export mô hình và lưu lại. |
| Bidirectional | Hai đầu khớp, một đầu thiếu hoặc một đầu trỏ sai. |
| Lifecycle | Draft, published, retired, archived và expired. |
| Cycles | Không chu kỳ, self-loop, chu kỳ nhiều node và quan hệ cho phép chu kỳ. |
| External reference | Endpoint hợp lệ, schema sai, service chưa sẵn sàng và quyền bị từ chối. |
| Incremental validation | Sửa một liên kết và xác nhận các ràng buộc phụ thuộc được chạy lại. |
| Diagnostics | Primary/related location, source ID, version và message. |

### Kiểm thử ví dụ

~~~text
Given:
  Order.customer has cardinality 1
  Customer C1 exists

When:
  Order O1.customer = C1

Then:
  reference is valid
~~~

Trường hợp lỗi:

~~~text
Given:
  Order.customer has cardinality 1
  no customer target is assigned

Then:
  validator reports a cardinality violation
  diagnostic points to Order.customer
~~~

### Kiểm thử property-based

Có thể sinh mô hình ngẫu nhiên theo metamodel, áp dụng các thao tác thêm, xóa, đổi tên và liên kết, rồi xác nhận validator cho kết quả phù hợp với một validator tham chiếu đơn giản hoặc các bất biến đã định nghĩa.

### Kiểm thử đồng thời

Nếu hai giao dịch cùng sửa liên kết, kiểm tra rằng kết quả commit không tạo dangling reference, vi phạm uniqueness hoặc phá vỡ quan hệ hai chiều. Kiểm thử cần bao gồm lịch cập nhật xen kẽ và xung đột optimistic locking.

## 28. Ví dụ tổng hợp: ràng buộc tham chiếu trong quy trình đơn hàng

Giả sử DSL mô tả khách hàng, đơn hàng, người phê duyệt và workflow:

~~~text
entity Customer {
    id: CustomerId key;
    status: CustomerStatus;
    orders: Order[0..*] opposite customer;
}

entity Order {
    id: OrderId key;
    customer: Customer[1] opposite orders;
    approvers: Reviewer[1..3];
    payment: Payment[0..1];
}

workflow OrderApproval {
    uses policy StandardApproval;
    call ValidateCustomer;
    call ApproveOrder;
}
~~~

Một bộ kiểm tra tham chiếu có thể áp dụng các quy tắc:

1. `Order.customer` phải trỏ đến một `Customer` tồn tại.
2. `Customer.orders` phải phản ánh các đơn hàng có `customer` trỏ đến khách hàng đó.
3. Mỗi đơn hàng có từ một đến ba người phê duyệt.
4. Mỗi phần tử trong `approvers` phải là `Reviewer` hợp lệ và không trùng theo reviewer ID.
5. `payment` là tùy chọn, nhưng nếu có thì phải trỏ đến một `Payment` thuộc đúng đơn hàng.
6. `StandardApproval`, `ValidateCustomer` và `ApproveOrder` phải được khai báo, được import và có loại phù hợp.
7. Các workflow hoặc policy được tham chiếu phải ở phiên bản tương thích và trạng thái được phép sử dụng.
8. Người phê duyệt phải thuộc phạm vi tổ chức có quyền xử lý đơn hàng.

### Phân loại lỗi

| Tình huống | Loại ràng buộc | Thời điểm kiểm tra phù hợp |
|---|---|---|
| Không khai báo `ApproveOrder` | Existence/name resolution | Compile-time. |
| `StandardApproval` là một Entity thay vì Policy | Kind/type | Compile-time. |
| Không gán `Order.customer` | Cardinality | Model validation hoặc trước commit. |
| `approvers` có bốn phần tử | Cardinality | Model validation. |
| Một reviewer xuất hiện hai lần | Uniqueness | Model validation. |
| Customer bị xóa khi Order còn tồn tại | Referential integrity | Repository transaction. |
| Reviewer bị khóa trước lúc duyệt | Lifecycle/domain | Runtime. |
| Workflow dependency tạo chu kỳ | Acyclicity | Compile/publish. |

Ví dụ này cho thấy ràng buộc tham chiếu bao gồm cả cấu trúc tĩnh và điều kiện phụ thuộc trạng thái thực tế. Một thiết kế tốt phân loại rõ để kiểm tra đúng giai đoạn và đưa ra thông báo phù hợp.

## 29. Những lỗi thiết kế thường gặp

**Chỉ kiểm tra tên có tồn tại.** Một tên có thể tồn tại nhưng trỏ đến sai loại, sai kiểu hoặc nằm ngoài phạm vi truy cập.

**Nhầm unresolved với chưa tải.** Trong dự án nhiều module hoặc repository từ xa, đích có thể chưa được tải. Cần phân biệt trạng thái pending với lỗi thật.

**Không quy định cardinality.** Quan hệ bắt buộc và tùy chọn có thể bị diễn giải khác nhau giữa parser, model editor và runtime.

**Coi mọi quan hệ là containment.** Xóa một phần tử có thể làm mất dữ liệu khác nếu cascade delete được áp dụng không đúng.

**Không kiểm tra dangling reference sau khi xóa hoặc đổi ID.** Mô hình có thể lưu được nhưng không còn nhất quán.

**Không đồng bộ hai đầu quan hệ.** `Order.customer` và `Customer.orders` có thể mâu thuẫn sau chỉnh sửa.

**Cấm mọi chu kỳ.** Một số quan hệ hai chiều hoặc graph có vòng lặp là hợp lệ; chỉ cấm chu kỳ ở loại quan hệ có yêu cầu acyclic.

**Kiểm tra toàn cục ở mọi lần sửa.** Validator có thể quá chậm; cần dependency tracking nhưng vẫn phải bảo đảm các ràng buộc toàn cục được kiểm tra ở commit hoặc publish.

**Để thứ tự module quyết định tham chiếu.** Dependency và qualified name phải được phân giải theo quy tắc ổn định, không theo thứ tự tải ngẫu nhiên.

**Chỉ kiểm tra lúc compile.** Trạng thái đối tượng, quyền truy cập và dịch vụ ngoài có thể thay đổi trước khi runtime sử dụng tham chiếu.

**Diagnostic không chỉ ra đích hoặc quan hệ liên quan.** Người dùng khó tìm nơi khai báo hoặc cạnh tạo chu kỳ nếu chỉ nhận một thông báo chung.

## 30. Quy trình thiết kế và triển khai ràng buộc tham chiếu

Một quy trình thực tế có thể gồm:

1. **Mô hình hóa quan hệ:** xác định nguồn, đích, loại tham chiếu và việc quan hệ là containment hay cross-reference.
2. **Định nghĩa đích hợp lệ:** loại, kiểu, namespace, scope, visibility và dependency.
3. **Định nghĩa cardinality:** số lượng tối thiểu/tối đa, optionality và quy tắc collection.
4. **Định nghĩa identity và uniqueness:** khóa, định danh ổn định, phạm vi duy nhất và xử lý trùng.
5. **Định nghĩa vòng đời:** hành vi khi đích bị xóa, đổi tên, archive hoặc đổi phiên bản.
6. **Định nghĩa quan hệ nghịch đảo:** nếu có hai đầu liên kết, quy tắc đồng bộ và kiểm tra nhất quán.
7. **Định nghĩa graph constraints:** quan hệ nào phải acyclic, quan hệ nào cho phép chu kỳ và cách phát hiện.
8. **Phân loại thời điểm kiểm tra:** compile, load, validate, publish, transaction hay runtime.
9. **Xây dựng symbol/reference index:** lưu target identity, source identity và dependency.
10. **Thiết kế diagnostic:** mã, severity, primary/related location, thông tin đích và gợi ý sửa.
11. **Tích hợp kiểm tra gia tăng:** theo dõi những ràng buộc bị ảnh hưởng khi một phần tử thay đổi.
12. **Kiểm thử:** existence, type, scope, cardinality, integrity, cycle, lifecycle, external reference và concurrency.

## 31. Checklist cho một loại tham chiếu mới

Khi thêm một quan hệ mới vào DSL, có thể xem xét:

- Nguồn và đích của tham chiếu là những loại phần tử nào?
- Tham chiếu được biểu diễn bằng tên, ID, đường dẫn hay edge?
- Đích phải tồn tại ở thời điểm nào?
- Có cho phép forward reference hoặc lazy resolution không?
- Kiểu hoặc loại đích nào được chấp nhận?
- Tham chiếu có bị giới hạn bởi scope, module, visibility hoặc tenant không?
- Cardinality tối thiểu và tối đa là bao nhiêu?
- Có cho phép nhiều nguồn trỏ cùng một đích không?
- Có yêu cầu uniqueness theo identity hoặc khóa nghiệp vụ không?
- Quan hệ có phía nghịch đảo không và cách đồng bộ thế nào?
- Khi xóa hoặc đổi đích, hệ thống xử lý ra sao?
- Đích có điều kiện lifecycle hoặc version không?
- Quan hệ có được phép tạo chu kỳ không?
- Điều kiện nào kiểm tra tĩnh, điều kiện nào cần runtime?
- Diagnostic sẽ trỏ đến nguồn, đích hay cả hai?
- Có thể kiểm tra gia tăng khi một phần tử thay đổi không?

## 32. Kết quả cần có sau khi đặc tả ràng buộc tham chiếu

Một thiết kế ràng buộc tham chiếu đầy đủ thường tạo ra:

- **Mô hình tham chiếu:** source, target, loại liên kết, containment và cross-reference.
- **Quy tắc phân giải:** existence, namespace, scope, visibility, import và dependency.
- **Quy tắc kiểu:** kind, type compatibility, subtype và chữ ký được chấp nhận.
- **Quy tắc cấu trúc:** cardinality, optionality, uniqueness và quan hệ nghịch đảo.
- **Quy tắc toàn vẹn:** dangling reference, delete policy, lifecycle và version compatibility.
- **Quy tắc đồ thị:** acyclicity, reachability và những loại chu kỳ được phép.
- **Chính sách thời điểm:** compile-time, model validation, publish và runtime.
- **Cơ chế triển khai:** symbol/reference index, validator, dependency graph và incremental validation.
- **Diagnostic:** vị trí nguồn, vị trí đích, quan hệ liên quan, mã lỗi và gợi ý sửa.
- **Bộ kiểm thử:** trường hợp hợp lệ, không hợp lệ, biên, thay đổi mô hình và cập nhật đồng thời.

Ràng buộc tham chiếu giúp bảo đảm các liên kết trong DSL trỏ đến đúng đối tượng, đúng loại, đúng phạm vi và đúng trạng thái. Khi chỉ kiểm tra tên tồn tại, một mô hình vẫn có thể chứa liên kết sai kiểu, sai số lượng, trỏ đến đối tượng đã xóa hoặc tạo ra chu kỳ không hợp lệ. Vì vậy, bộ kiểm tra ngữ nghĩa cần xem xét cả đích tham chiếu lẫn quan hệ mà nó tham gia, xác định thời điểm kiểm tra phù hợp và cung cấp diagnostic đủ rõ để người dùng sửa đúng liên kết. Những quy tắc này tạo nền tảng cho mô hình DSL nhất quán, workflow đáng tin cậy và các công cụ biên tập có thể giải thích được vì sao một tham chiếu được chấp nhận hoặc bị từ chối.

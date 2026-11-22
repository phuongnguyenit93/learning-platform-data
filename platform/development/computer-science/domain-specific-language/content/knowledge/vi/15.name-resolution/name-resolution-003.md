# Namespace và import

## 1. Namespace và import trong phân giải tên

Trong một DSL (Domain-Specific Language), chương trình thường được chia thành nhiều tệp, module hoặc package. Mỗi phần có thể khai báo biến, hàm, kiểu dữ liệu, rule, schema hoặc thành phần cấu hình. Khi một phần của chương trình sử dụng tên được khai báo ở nơi khác, compiler cần xác định chính xác tên đó trỏ tới khai báo nào.

Hai cơ chế thường dùng để tổ chức việc này là **namespace** và **import**:

- **Namespace** tạo không gian tên để nhóm các khai báo và tránh trùng tên giữa những thành phần độc lập.
- **Import** đưa một hoặc nhiều tên từ module hoặc namespace khác vào phạm vi hiện tại, giúp sử dụng chúng thuận tiện hơn.

Ví dụ, một hệ thống bán hàng có thể có hai hàm cùng tên:

~~~text
namespace billing {
    function calculateFee(order) { ... }
}

namespace shipping {
    function calculateFee(order) { ... }
}
~~~

Hai hàm đều có tên calculateFee nhưng thuộc hai namespace khác nhau. Khi gọi, chương trình có thể chỉ rõ:

~~~text
billing.calculateFee(order)
shipping.calculateFee(order)
~~~

Namespace cung cấp ngữ cảnh để tên không bị nhập nhằng. Import cho phép chọn những khai báo cần dùng mà không phải viết đầy đủ đường dẫn namespace ở mọi chỗ.

## 2. Vì sao DSL cần namespace?

Trong một chương trình nhỏ, tên có thể được quản lý trong một phạm vi duy nhất. Nhưng khi hệ thống mở rộng, nhiều nhóm có thể cùng tạo các thành phần với tên tự nhiên giống nhau:

- Module billing và module shipping đều có kiểu Address.
- Nhiều nhóm có thể định nghĩa hàm validate hoặc normalize.
- Các rule khác nhau có thể cùng dùng tên active hoặc eligible.
- Một thư viện dùng tên Order trong khi ứng dụng có kiểu Order riêng.

Nếu mọi khai báo đều nằm trong một không gian tên toàn cục, hệ thống dễ gặp xung đột tên. Người dùng phải tạo tên dài và khó hiểu như BillingOrderAddress hoặc ShippingOrderAddress để phân biệt.

Namespace giải quyết vấn đề bằng cách chia tên thành các nhóm:

~~~text
billing.Address
shipping.Address
sales.Order
warehouse.Order
~~~

Nó mang lại các lợi ích:

1. **Tránh xung đột:** các module có thể dùng cùng tên ngắn mà vẫn phân biệt được.
2. **Thể hiện quyền sở hữu:** đường dẫn cho biết thành phần thuộc miền hoặc module nào.
3. **Tổ chức API:** người dùng tìm được các hàm, kiểu và rule theo nhóm chức năng.
4. **Hỗ trợ mở rộng:** thư viện mới có thể thêm khai báo mà ít ảnh hưởng đến tên hiện có.
5. **Tăng khả năng đọc:** tên đầy đủ cung cấp ngữ cảnh khi đọc chương trình lớn.
6. **Hỗ trợ phân quyền và kiểm soát:** hệ thống có thể áp dụng chính sách theo module hoặc namespace.

Namespace là cơ chế tổ chức tên. Nó không nhất thiết tương ứng một-một với thư mục, tệp, package vật lý hoặc dịch vụ triển khai. Một namespace có thể trải trên nhiều tệp; một tệp có thể khai báo nhiều namespace nếu DSL cho phép.

## 3. Namespace, module, package và scope khác nhau thế nào?

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò chính | Ví dụ |
|---|---|---|
| Namespace | Nhóm tên và tạo định danh đầy đủ | sales.Order |
| Module | Đơn vị mã nguồn hoặc đơn vị biên dịch có giao diện và phụ thuộc | module sales.orders |
| Package | Đơn vị phân phối hoặc tổ chức thư viện theo quy ước của hệ sinh thái | com.example.sales |
| Scope | Xác định nơi một khai báo có hiệu lực | Biến cục bộ trong một hàm |
| File | Đơn vị lưu trữ vật lý | orders.dsl |

Một module có thể khai báo một hoặc nhiều namespace. Một namespace có thể chứa nhiều module hoặc được mở rộng bởi nhiều tệp, tùy thiết kế ngôn ngữ. Scope thường nhỏ hơn và gắn với cấu trúc chương trình như block, hàm hoặc rule.

Ví dụ:

~~~text
module sales.orders {
    namespace sales.ordering {
        type Order { ... }
        function submit(order: Order) { ... }
    }
}
~~~

Trong ví dụ này, module sales.orders là đơn vị mã nguồn hoặc biên dịch; namespace sales.ordering là không gian tên mà các khai báo được đặt vào. Biến cục bộ bên trong submit vẫn có scope riêng.

Khi thiết kế DSL, cần công bố rõ module và namespace có quan hệ thế nào. Nếu hai khái niệm bị dùng thay thế cho nhau mà không có quy tắc, người dùng sẽ khó hiểu cách import, quản lý phụ thuộc và phân quyền.

## 4. Tên đơn giản và tên đầy đủ

Một định danh có thể được viết ở dạng tên đơn giản hoặc tên đầy đủ:

- **Tên đơn giản (simple name):** tên không chứa đường dẫn namespace, ví dụ Order hoặc calculateFee.
- **Tên đầy đủ (qualified name):** tên kèm namespace hoặc module, ví dụ sales.orders.Order hoặc billing.calculateFee.

Ví dụ:

~~~text
namespace sales.orders {
    type Order { ... }
}

let current: sales.orders.Order;
~~~

Tên đầy đủ luôn cho biết rõ nguồn gốc của khai báo nếu quy tắc namespace là duy nhất. Tên đơn giản ngắn hơn nhưng cần được phân giải dựa trên import và scope hiện tại.

Một DSL cũng có thể hỗ trợ tên tương đối (relative name), được diễn giải dựa trên namespace hiện tại:

~~~text
namespace sales.checkout {
    import sales.orders.Order;

    function createOrder(): Order {
        ...
    }
}
~~~

Ở đây Order là tên đơn giản được import từ sales.orders. Nếu không có import, DSL có thể yêu cầu dùng tên đầy đủ hoặc tìm trong namespace hiện tại theo quy tắc đã định.

## 5. Khai báo namespace

Một DSL có thể dùng block namespace:

~~~text
namespace inventory {
    type Product {
        id: ProductId;
        name: String;
        availableQuantity: Integer;
    }

    function canFulfill(product: Product, quantity: Integer): Boolean {
        return product.availableQuantity >= quantity;
    }
}
~~~

Các khai báo bên trong thuộc namespace inventory. Tên đầy đủ của kiểu Product là inventory.Product; tên đầy đủ của hàm canFulfill là inventory.canFulfill.

Một cú pháp khác dùng khai báo namespace ở đầu tệp:

~~~text
namespace inventory;

type Product { ... }
function canFulfill(product: Product, quantity: Integer): Boolean { ... }
~~~

Trong kiểu cú pháp này, mọi khai báo ở cấp tệp thuộc namespace inventory. Cách viết nào phù hợp phụ thuộc vào DSL, nhưng cần quy định:

- Namespace có phân biệt chữ hoa và chữ thường không?
- Các thành phần của namespace được phân tách bằng dấu chấm, dấu gạch chéo hay ký hiệu khác?
- Namespace có thể lồng nhau không?
- Một namespace có thể được khai báo ở nhiều tệp không?
- Có cho phép namespace mặc định hoặc global namespace không?
- Một module có thể export nhiều namespace không?

### 5.1. Namespace lồng nhau

Namespace có thể được phân cấp để thể hiện miền và chức năng:

~~~text
namespace commerce.orders {
    type Order { ... }
}

namespace commerce.payments {
    type Payment { ... }
}
~~~

Tên đầy đủ lần lượt là commerce.orders.Order và commerce.payments.Payment. Phân cấp namespace nên phản ánh cấu trúc có ý nghĩa đối với người sử dụng, không nhất thiết sao chép toàn bộ cấu trúc thư mục.

### 5.2. Namespace mở rộng qua nhiều tệp

Một số ngôn ngữ cho phép nhiều tệp cùng đóng góp khai báo vào một namespace:

~~~text
// orders.dsl
namespace commerce.orders;
type Order { ... }
~~~

~~~text
// order-functions.dsl
namespace commerce.orders;
function calculateTotal(order: Order): Money { ... }
~~~

Nếu hỗ trợ cách tổ chức này, compiler phải kết hợp các khai báo và phát hiện tên trùng trong toàn bộ namespace sau khi nạp các tệp liên quan. Không nên để kết quả phụ thuộc thứ tự đọc tệp nếu ngôn ngữ không công bố quy tắc đó.

## 6. Import một khai báo cụ thể

Import cho phép dùng tên đơn giản của một khai báo thuộc namespace khác:

~~~text
import sales.orders.Order;
import billing.money.Money;

function invoice(order: Order): Money {
    ...
}
~~~

Compiler ghi nhận các import trong môi trường phân giải tên. Khi gặp Order, nó tìm khai báo tương ứng theo quy tắc import. Cách import cụ thể giúp người đọc biết chương trình phụ thuộc vào những thành phần nào.

Một import có thể trỏ đến:

- Kiểu dữ liệu hoặc class.
- Hàm hoặc method cấp module.
- Hằng số hoặc enum.
- Rule, policy hoặc schema.
- Module con hoặc namespace.

Không phải DSL nào cũng cho phép import mọi loại khai báo. Chẳng hạn, một DSL cấu hình có thể chỉ import schema và function được phép, không cho import tùy ý mã thực thi.

## 7. Import toàn bộ namespace và wildcard import

Một số DSL cho phép import tất cả các khai báo được export từ namespace:

~~~text
import sales.orders.*;

let order: Order;
let result = calculateTotal(order);
~~~

Wildcard import giúp giảm số dòng import khi sử dụng nhiều khai báo từ cùng namespace. Tuy nhiên, nó cũng làm nguồn gốc của tên trở nên kém rõ ràng. Nếu sau này namespace bổ sung một khai báo trùng tên với một tên đang được import từ nơi khác, chương trình có thể trở nên mơ hồ.

Ví dụ:

~~~text
import billing.*;
import shipping.*;

let address: Address;
~~~

Nếu cả hai namespace đều export Address, compiler cần phát hiện xung đột. Nó không nên âm thầm chọn một khai báo theo thứ tự import trừ khi quy tắc ưu tiên như vậy được thiết kế và công bố rõ.

Trong các DSL dùng cho cấu hình quan trọng, import tường minh thường dễ kiểm soát hơn wildcard import. Có thể giới hạn wildcard import chỉ trong một số ngữ cảnh hoặc không hỗ trợ.

## 8. Import alias

Alias đặt một tên thay thế cho khai báo hoặc namespace được import. Nó hữu ích khi tên dài hoặc có xung đột:

~~~text
import billing.Address as BillingAddress;
import shipping.Address as ShippingAddress;

let invoiceAddress: BillingAddress;
let deliveryAddress: ShippingAddress;
~~~

Alias cũng có thể đặt cho toàn bộ namespace:

~~~text
import commerce.orders as orders;
import commerce.payments as payments;

let current: orders.Order;
let payment: payments.Payment;
~~~

Alias giúp tên ngắn mà vẫn thể hiện nguồn gốc. Một DSL cần quyết định:

- Alias có bắt buộc duy nhất trong scope hiện tại không?
- Alias có thể trùng với tên khai báo cục bộ không?
- Có cho phép import nhiều tên cùng alias không?
- Alias có được export lại cho module khác không?
- Tên đầy đủ gốc có còn truy cập được sau khi alias không?

Thông thường, alias chỉ có hiệu lực trong tệp hoặc module chứa import. Nó không tự động đổi tên khai báo trong module nguồn.

## 9. Import có chọn lọc và đổi tên nhiều khai báo

Một cú pháp import có chọn lọc có thể gom các khai báo từ cùng namespace:

~~~text
from sales.orders import Order, OrderStatus, calculateTotal;
~~~

Một số DSL cho phép alias từng tên:

~~~text
from billing.money import Money as CurrencyAmount;
~~~

Import có chọn lọc giúp danh sách phụ thuộc rõ ràng. Khi đọc đầu tệp, người bảo trì biết module sử dụng những thành phần nào. Nó cũng giúp compiler hoặc công cụ phân tích xác định chính xác các tên có thể xuất hiện trong scope.

Nếu cú pháp hỗ trợ import nhiều tên, cần quy định cách xử lý khi một tên không tồn tại hoặc không được export. Thông thường, đó là lỗi phân giải tên tại vị trí import, kèm gợi ý các tên gần giống nếu compiler có thể tìm được.

## 10. Visibility: public, private và protected

Namespace xác định nhóm tên; visibility (phạm vi truy cập) xác định nơi một khai báo có thể được sử dụng.

Ví dụ:

~~~text
namespace billing {
    public type Money { ... }

    public function calculateTax(invoice: Invoice): Money {
        return internalTaxFormula(invoice);
    }

    private function internalTaxFormula(invoice: Invoice): Money {
        ...
    }
}
~~~

Module khác có thể import Money và calculateTax nếu chúng được export. Nó không thể import internalTaxFormula nếu khai báo này là private.

Các mức truy cập phổ biến:

| Mức truy cập | Phạm vi thường gặp |
|---|---|
| public/exported | Module khác được phép sử dụng |
| internal/module | Chỉ các thành phần trong cùng module |
| private | Chỉ trong khai báo hoặc module hiện tại theo quy tắc DSL |
| protected | Có thể truy cập trong kiểu hiện tại và kiểu mở rộng nếu DSL hỗ trợ kế thừa |

Tên mức truy cập và phạm vi thực tế tùy ngôn ngữ. Một DSL có thể chỉ cần public và private để giữ mô hình đơn giản. Điều quan trọng là import không được vượt qua visibility: biết tên đầy đủ không đồng nghĩa có quyền sử dụng khai báo đó.

## 11. Quy tắc phân giải tên khi có nhiều nguồn

Khi compiler gặp một tên đơn giản, nó cần tìm đúng khai báo theo một thứ tự xác định. Một chiến lược minh họa:

1. Tìm biến hoặc khai báo cục bộ trong scope gần nhất.
2. Tìm các scope cha theo thứ tự lồng nhau.
3. Tìm khai báo trong namespace hiện tại.
4. Tìm các tên được import tường minh.
5. Tìm tên từ import wildcard nếu DSL hỗ trợ.
6. Tìm khai báo từ namespace mặc định hoặc thư viện chuẩn nếu được quy định.
7. Nếu vẫn không tìm thấy, báo lỗi tên chưa xác định.

Đây chỉ là một chính sách ví dụ. DSL cần công bố thứ tự chính xác, đặc biệt khi cùng một tên có thể xuất hiện ở nhiều nguồn. Nếu có nhiều ứng viên cùng mức ưu tiên, compiler nên báo lỗi mơ hồ thay vì chọn ngẫu nhiên.

Ví dụ:

~~~text
namespace sales {
    type Order { ... }
}

namespace shipping {
    type Order { ... }
}

namespace checkout {
    import sales.Order;

    function submit(order: Order) { ... }
}
~~~

Trong checkout, Order được import tường minh từ sales. Nếu đồng thời có import shipping.Order mà không có alias, tên Order có hai ứng viên và cần được xem là xung đột theo chính sách import.

### 11.1. Tên cục bộ và tên import

Nếu một biến cục bộ trùng với tên được import, DSL cần xác định tên nào được ưu tiên. Một số ngôn ngữ cho phép local declaration che khuất import; một số khác báo lỗi để tránh nhầm lẫn.

Ví dụ:

~~~text
import sales.Order;

function process() {
    let Order = "draft";
    ...
}
~~~

Nếu cho phép shadowing, bên trong hàm Order có thể là biến chuỗi thay vì kiểu sales.Order. Điều này dễ gây nhầm lẫn. Với DSL miền nghiệp vụ, có thể cấm khai báo cục bộ che khuất kiểu hoặc hàm đã import.

## 12. Symbol table và import graph

Để phân giải tên trong chương trình nhiều module, compiler thường duy trì symbol table và đồ thị phụ thuộc.

**Symbol table** lưu thông tin về khai báo:

- Tên đơn giản và tên đầy đủ.
- Loại symbol: type, function, variable, rule hoặc module.
- Namespace sở hữu.
- Visibility và trạng thái export.
- Vị trí khai báo.
- Kiểu hoặc chữ ký.

**Import graph** mô tả quan hệ phụ thuộc giữa các module. Nếu module A import B, đồ thị có một cạnh A -> B.

Ví dụ:

~~~mermaid
flowchart TD
    A["checkout"] --> B["sales.orders"]
    A --> C["billing.money"]
    B --> D["common.types"]
    C --> D
~~~

Compiler có thể dùng đồ thị để xác định thứ tự nạp và biên dịch. Trong ví dụ, checkout phụ thuộc sales.orders và billing.money; cả hai cùng phụ thuộc common.types.

Nếu có vòng phụ thuộc:

~~~mermaid
flowchart LR
    A["module A"] --> B["module B"]
    B --> C["module C"]
    C --> A
~~~

DSL cần quyết định có cho phép vòng import hay không. Nếu không, compiler phải phát hiện chu trình và báo lỗi. Nếu có, cần quy tắc xử lý khai báo tiến về phía trước, khởi tạo và liên kết symbol để tránh trạng thái chưa hoàn chỉnh.

## 13. Import vòng và quản lý phụ thuộc

Import vòng có thể làm việc phân giải tên và biên dịch phức tạp:

~~~text
// a.dsl
module a;
import b.B;
type A { value: B; }
~~~

~~~text
// b.dsl
module b;
import a.A;
type B { value: A; }
~~~

Một số ngôn ngữ cho phép tham chiếu kiểu qua lại nếu chỉ cần biết tên và cấu trúc có thể được liên kết sau. Một số ngôn ngữ cấm vòng phụ thuộc để giữ thứ tự biên dịch đơn giản.

Các chiến lược thường gặp:

- **Cấm chu trình:** import graph phải là DAG (directed acyclic graph). Compiler báo chu trình và chỉ ra đường đi gây vòng.
- **Cho phép tham chiếu tiến:** tên có thể được đăng ký trước, sau đó mới phân tích đầy đủ định nghĩa.
- **Tách interface và implementation:** module công bố chữ ký hoặc schema trước, phần triển khai được liên kết sau.
- **Dùng module nền tảng:** chuyển các kiểu dùng chung sang module độc lập để giảm phụ thuộc vòng.

Không nên giải quyết import vòng bằng cách bỏ qua lỗi hoặc nạp module theo thứ tự bất kỳ. Điều đó có thể làm kết quả phụ thuộc môi trường build.

## 14. Import và thư viện chuẩn

DSL thường có một tập khai báo chuẩn như kiểu số, chuỗi, ngày giờ, hàm chuyển đổi hoặc thao tác collection. Chúng có thể được cung cấp trong namespace chuẩn:

~~~text
import std.time.Date;
import std.money.Money;
import std.collections.List;
~~~

Một DSL cũng có thể tự động đưa một số tên chuẩn vào scope mà không cần import. Cách này tiện cho người viết, nhưng có thể làm nguồn gốc tên kém rõ ràng và gây xung đột khi thư viện chuẩn bổ sung tên mới.

Nếu có namespace mặc định, cần quy định:

- Những tên nào được đưa vào tự động?
- Phiên bản thư viện chuẩn nào được sử dụng?
- Người dùng có thể che khuất tên chuẩn không?
- Có thể tắt namespace mặc định không?
- Tên mới trong thư viện chuẩn có thể làm chương trình cũ mơ hồ không?

Với các chương trình cần tái lập, nên gắn phiên bản DSL và thư viện chuẩn với môi trường biên dịch hoặc manifest phụ thuộc.

## 15. Import có điều kiện và import động

Một số DSL có thể cho phép import phụ thuộc môi trường:

~~~text
if environment == "production" {
    import config.production;
} else {
    import config.development;
}
~~~

Cú pháp này chỉ là ví dụ minh họa; nhiều compiler không cho import nằm trong nhánh runtime vì import thường cần được giải quyết trước khi thực thi.

Nếu import phụ thuộc điều kiện, cần xác định điều kiện được biết lúc compile hay runtime. Import tĩnh thường được xử lý khi biên dịch, nhờ đó compiler có thể kiểm tra tên và kiểu đầy đủ. Import động có thể tải module khi chạy, nhưng khi đó lỗi thiếu module hoặc sai phiên bản có thể chỉ xuất hiện ở runtime.

Với DSL cấu hình và quy tắc quan trọng, import tĩnh thường dễ kiểm soát hơn. Nếu cần nạp module động, nên dùng API registry hoặc loader có hợp đồng rõ, xác thực nguồn gốc, kiểm tra phiên bản và giới hạn quyền.

## 16. Namespace và import trong bảo mật

Namespace và import không tự tạo ra ranh giới bảo mật. Chúng chủ yếu tổ chức định danh và phụ thuộc. Tuy vậy, hệ thống có thể kết hợp chúng với visibility và capability để giới hạn những gì chương trình được phép sử dụng.

Ví dụ:

~~~text
import std.math.*;
import approved.reporting.generateReport;

// Không cho phép import trực tiếp namespace system.files
// trong policy chạy ở môi trường không tin cậy.
~~~

Một runtime an toàn cần kiểm soát:

- Namespace nào được phép import trong từng môi trường.
- Package hoặc module đến từ registry đáng tin cậy nào.
- Hàm hoặc capability nào được export.
- Phiên bản và chữ ký của package.
- Quyền đọc dữ liệu, truy cập tệp hoặc mạng của module.
- Cách audit module và hàm được gọi.

Không nên xem việc ẩn tên bằng private là biện pháp bảo mật hoàn chỉnh. Quyền truy cập tài nguyên phải được kiểm soát tại runtime hoặc ranh giới thực thi có thẩm quyền.

## 17. Phiên bản namespace, module và import

Khi thư viện phát triển, cùng một tên đầy đủ có thể có hành vi khác giữa các phiên bản. Ví dụ, sales.orders.Order ở phiên bản 1 có thể có trường status, trong phiên bản 2 có thêm trạng thái mới hoặc thay đổi cấu trúc.

Một DSL có thể quản lý phiên bản qua package:

~~~text
dependency sales.orders version "2.3.1";
import sales.orders.Order;
~~~

Hoặc qua alias có phiên bản:

~~~text
import sales.orders.v2 as orders;
~~~

Đây là các kiểu cú pháp minh họa. Dù chọn cách nào, hệ thống nên:

- Ghi rõ phiên bản phụ thuộc.
- Khóa phiên bản trong môi trường build cần tái lập.
- Phát hiện import tới package không tồn tại hoặc không tương thích.
- Có chính sách tương thích và deprecation.
- Tránh để tên cùng namespace trỏ tới nội dung khác nhau mà không có version metadata.

Import một tên không nên ngầm lấy phiên bản mới nhất nếu điều đó làm chương trình đã triển khai thay đổi hành vi mà không qua review.

## 18. Chẩn đoán lỗi namespace và import

Compiler nên đưa ra thông báo lỗi cụ thể thay vì chỉ báo không thể tìm thấy tên.

Một số lỗi thường gặp:

| Mã lỗi minh họa | Nguyên nhân | Gợi ý xử lý |
|---|---|---|
| NS001 | Namespace không tồn tại | Kiểm tra tên module hoặc package |
| NS002 | Tên không được export | Kiểm tra visibility |
| NS003 | Tên đơn giản mơ hồ | Dùng tên đầy đủ hoặc alias |
| IM001 | Module được import không tồn tại | Kiểm tra dependency và registry |
| IM002 | Import vòng bị cấm | Tách module hoặc chuyển kiểu dùng chung |
| IM003 | Phiên bản module không tương thích | Chọn phiên bản hỗ trợ |
| IM004 | Import trùng hoặc alias xung đột | Loại import dư hoặc đổi alias |

Ví dụ diagnostic:

~~~text
ERROR NS003: Ambiguous name 'Address'.
  Imported candidates:
    billing.Address
    shipping.Address
  Hint: Use a qualified name or import one candidate with an alias.
~~~

Thông báo này cho biết tên nào bị mơ hồ và liệt kê các ứng viên. Người viết có thể sửa bằng:

~~~text
import billing.Address as BillingAddress;
import shipping.Address as ShippingAddress;
~~~

Compiler cũng nên báo vị trí của câu lệnh import sai và vị trí khai báo liên quan nếu có. Điều đó giúp xử lý lỗi nhanh hơn trong dự án có nhiều module.

## 19. Ví dụ hoàn chỉnh: tổ chức một DSL bán hàng

Giả sử hệ thống có ba module: đơn hàng, thanh toán và giao hàng.

Tệp khai báo đơn hàng:

~~~text
namespace commerce.orders;

public type Order {
    id: OrderId;
    customerId: CustomerId;
    total: Money<VND>;
}

public function calculateTotal(order: Order): Money<VND> {
    ...
}
~~~

Tệp khai báo thanh toán:

~~~text
namespace commerce.payments;

public type Payment {
    orderId: OrderId;
    amount: Money<VND>;
}

public function authorize(payment: Payment): AuthorizationResult {
    ...
}
~~~

Tệp khai báo giao hàng:

~~~text
namespace commerce.shipping;

public type Address { ... }
public function estimate(address: Address): Duration { ... }
~~~

Module checkout sử dụng các khai báo:

~~~text
namespace commerce.checkout;

import commerce.orders.Order;
import commerce.orders.calculateTotal;
import commerce.payments.Payment;
import commerce.payments.authorize;
import commerce.shipping.Address as ShippingAddress;
import commerce.shipping.estimate;

function checkout(order: Order, address: ShippingAddress) {
    let amount = calculateTotal(order);
    let payment = Payment(order.id, amount);
    let authorization = authorize(payment);
    let deliveryTime = estimate(address);

    return CheckoutResult(authorization, deliveryTime);
}
~~~

Compiler xử lý chương trình theo các bước khái quát:

1. Đọc namespace của module checkout.
2. Tải và xác minh các module được import.
3. Kiểm tra visibility của Order, calculateTotal, Payment, authorize, Address và estimate.
4. Đăng ký tên import cùng alias ShippingAddress vào môi trường hiện tại.
5. Phân giải các tên trong chữ ký hàm checkout và thân hàm.
6. Kiểm tra kiểu đối số, kiểu trả về và các thuộc tính được truy cập.
7. Báo lỗi nếu có tên không tồn tại, xung đột hoặc phụ thuộc không hợp lệ.

Ví dụ cho thấy namespace giữ tên đầy đủ có cấu trúc, còn import cho phép mã checkout sử dụng các tên cần thiết mà không phải lặp lại toàn bộ đường dẫn.

## 20. Thực hành thiết kế namespace và import

Khi thiết kế một DSL mới hoặc tổ chức lại DSL hiện có, nên quyết định các điểm sau:

1. **Chọn quy ước đặt tên.** Namespace dùng phân cấp nào, có phân biệt hoa thường không và tên đầy đủ được viết ra sao?
2. **Xác định đơn vị module.** Module có tương ứng tệp, package hay đơn vị biên dịch độc lập?
3. **Quy định visibility.** Khai báo nào được export và khai báo nào chỉ dùng nội bộ?
4. **Chọn dạng import.** Có import từng tên, import namespace, alias và wildcard không?
5. **Định nghĩa thứ tự phân giải.** Local scope, namespace hiện tại và import được ưu tiên thế nào?
6. **Xử lý xung đột.** Tên trùng hoặc alias trùng bị báo lỗi hay có quy tắc ưu tiên?
7. **Quản lý phụ thuộc.** Import graph có được phép có chu trình không và cách phát hiện ra sao?
8. **Quản lý phiên bản.** Package và thư viện chuẩn được khóa phiên bản thế nào?
9. **Thiết kế diagnostics.** Lỗi thiếu namespace, thiếu export, mơ hồ và vòng phụ thuộc cần thông báo cụ thể.
10. **Kết hợp bảo mật.** Chỉ cho phép import package, capability và nguồn phát hành được tin cậy.

Một số nguyên tắc thực hành:

- Ưu tiên tên đầy đủ khi cần loại bỏ sự mơ hồ.
- Dùng import tường minh cho các phụ thuộc quan trọng.
- Dùng alias khi hai khai báo có tên giống nhau hoặc namespace quá dài.
- Hạn chế wildcard import ở module lớn.
- Giữ namespace phản ánh miền nghiệp vụ ổn định, tránh thay đổi chỉ vì tái cấu trúc thư mục.
- Tránh phụ thuộc vòng; chuyển kiểu hoặc hợp đồng dùng chung sang module nền tảng.
- Ghi phiên bản dependency để build và runtime có thể tái lập.

## 21. Kết luận

Namespace và import là hai cơ chế cốt lõi để tổ chức tên trong một DSL có nhiều module. Namespace tạo định danh đầy đủ và tránh xung đột giữa các nhóm khai báo. Import cho phép sử dụng có chọn lọc những tên được export từ module khác, với các lựa chọn như import tường minh, wildcard hoặc alias.

Để phân giải tên dự đoán được, DSL cần định nghĩa rõ quan hệ giữa namespace, module và scope; quy tắc visibility; thứ tự tìm kiếm tên; cách xử lý xung đột; và chính sách phụ thuộc vòng. Compiler thường dùng symbol table cùng import graph để nạp module, kiểm tra quyền truy cập và liên kết các khai báo.

Khi thiết kế, hãy giữ tên đầy đủ ổn định, dùng import có chủ đích, báo lỗi mơ hồ rõ ràng và khóa phiên bản thư viện. Những quy tắc này giúp chương trình DSL dễ đọc, dễ mở rộng và ít bị ảnh hưởng bởi xung đột tên khi hệ thống phát triển.

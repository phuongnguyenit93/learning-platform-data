# Phân giải nhiều tệp

Một DSL nhỏ có thể được viết trong một tệp duy nhất. Khi mô hình miền lớn dần, người dùng thường tách khai báo entity, kiểu dữ liệu, quy tắc, truy vấn và workflow thành nhiều tệp để dễ tổ chức và tái sử dụng. Khi đó, một tên được sử dụng trong tệp này có thể được khai báo ở tệp khác. Hệ thống phải xác định chính xác tên đó tham chiếu đến khai báo nào. Quá trình này được gọi là **phân giải tên nhiều tệp (cross-file name resolution)**.

Phân giải tên nhiều tệp mở rộng việc tra cứu tên trong một phạm vi đơn lẻ thành việc tra cứu qua các module hoặc đơn vị biên dịch. Nó cần biết tệp nào thuộc module nào, khai báo nào được xuất, tệp nào được phép import, tên nào được nhìn thấy, và phải xử lý thế nào khi có tên trùng, tham chiếu vòng hoặc phụ thuộc chưa được nạp.

Đây là một phần quan trọng của thiết kế DSL có khả năng mở rộng. Nếu quy tắc import và phân giải không rõ ràng, cùng một tên có thể được hiểu khác nhau tùy thứ tự đọc tệp hoặc cách công cụ chạy. Một hệ thống tốt cần tạo kết quả xác định, báo lỗi có vị trí nguồn và hỗ trợ biên dịch lại khi chỉ một phần dự án thay đổi.

## 1. Phân giải tên nhiều tệp là gì?

Phân giải tên (name resolution) là quá trình liên kết một tên được sử dụng trong chương trình với khai báo tương ứng. Ví dụ, khi biểu thức dùng `Order`, hệ thống tìm khai báo kiểu `Order` trong các phạm vi được phép truy cập.

Trong một tệp, việc tìm tên có thể chỉ cần xét scope cục bộ, module hiện tại và các khai báo đã biết. Với nhiều tệp, hệ thống còn phải xét quan hệ giữa các đơn vị nguồn:

- Tệp nào thuộc cùng một module hoặc package?
- Tệp nào cung cấp khai báo ra bên ngoài?
- Tệp nào import module hoặc tên cụ thể?
- Tên được tham chiếu có phải là tên công khai không?
- Có nhiều khai báo cùng tên trong các module được import không?
- Một tệp có thể tham chiếu khai báo ở tệp chưa được phân tích hay chưa?

Ví dụ, dự án có cấu trúc:

```text
project/
├── model/
│   ├── customer.dsl
│   └── order.dsl
├── rules/
│   └── shipping.dsl
└── main.dsl
```

`order.dsl` có thể khai báo `Order`; `shipping.dsl` sử dụng `Order`; `main.dsl` kết hợp các quy tắc. Khi phân tích `shipping.dsl`, compiler cần tìm được `Order` trong module hoặc tệp mà nó import, dù khai báo nằm ở một tệp khác.

## 2. Phân biệt tệp, module và đơn vị biên dịch

Phân giải nhiều tệp cần một mô hình rõ về cách các tệp được nhóm và biên dịch. Ba khái niệm sau có liên quan nhưng không nhất thiết đồng nhất.

| Khái niệm | Ý nghĩa |
|---|---|
| Tệp nguồn | Một đơn vị lưu trữ văn bản DSL trên hệ thống tệp hoặc nguồn ảo |
| Module/package | Đơn vị tổ chức tên, quyền truy cập và tái sử dụng các khai báo |
| Đơn vị biên dịch | Phạm vi mà compiler phân tích và xử lý như một đầu vào biên dịch; có thể là một tệp, một module hoặc nhiều tệp |

Một module có thể gồm nhiều tệp. Ngược lại, một tệp có thể chứa nhiều namespace hoặc module con nếu DSL cho phép. Compiler không nên mặc định rằng tên tệp chính là tên module trừ khi đặc tả quy định điều đó.

### 2.1. Tệp là nơi lưu trữ, module là ranh giới ngôn ngữ

Ví dụ, `customer.dsl` và `order.dsl` có thể cùng thuộc module `sales`. Khi đó, chúng có thể chia sẻ một namespace hoặc nhìn thấy các khai báo nội bộ theo chính sách của module.

```text
module sales

// customer.dsl
entity Customer {
    id: CustomerId
    name: String
}

// order.dsl
entity Order {
    id: OrderId
    customer: Customer
}
```

Nếu module `sales` gom cả hai tệp, `Order` có thể tham chiếu `Customer` theo quy tắc nội bộ của module mà không cần import riêng từng khai báo. Đây chỉ là một mô hình; DSL khác có thể yêu cầu import tường minh giữa các tệp.

### 2.2. Đơn vị biên dịch ảnh hưởng đến khả năng tham chiếu trước

Nếu compiler xử lý từng tệp độc lập theo thứ tự tuần tự, khai báo ở tệp chưa được đọc có thể chưa tồn tại trong symbol table. Để hỗ trợ tham chiếu trước (forward reference), compiler thường cần tách bước thu thập khai báo khỏi bước kiểm tra và xử lý thân khai báo.

## 3. Khai báo, export và import

Để tên có thể được dùng từ tệp khác, DSL cần quy định cách một khai báo được công khai và cách tệp sử dụng nó.

### 3.1. Export khai báo

Khai báo có thể mặc định là nội bộ hoặc công khai. Ví dụ:

```text
module sales

export entity Customer {
    id: CustomerId
    name: String
}

entity InternalDraft {
    createdAt: Instant
}
```

Trong ví dụ này, `Customer` được export và có thể được module khác tham chiếu; `InternalDraft` chỉ được dùng trong phạm vi mà đặc tả cho phép. Một DSL có thể dùng từ khóa `public`, `export`, modifier hoặc file manifest để mô tả quyền truy cập.

Điểm quan trọng là export phải có semantics rõ: nó công khai tên, kiểu, schema hay cả các thành phần con? Một entity công khai có tự động công khai các thuộc tính của nó không? Một hàm công khai có thể dùng kiểu nội bộ trong chữ ký không? Những quy tắc này cần được xác định.

### 3.2. Import module

Một tệp có thể import toàn bộ module:

```text
import sales

rule notifyNewCustomer {
    when customer.status == ACTIVE
    then sales.sendWelcomeMessage(customer)
}
```

Cú pháp trên chỉ minh họa. DSL cần xác định import module có đưa toàn bộ tên công khai vào scope hiện tại hay chỉ cho phép truy cập qua tên module.

### 3.3. Import tên cụ thể

Để giảm việc đưa quá nhiều tên vào scope, DSL có thể cho phép import chọn lọc:

```text
from sales import Customer, Order
```

Khi đó, chỉ các tên được liệt kê được đưa vào phạm vi tên cục bộ. Compiler cần kiểm tra từng tên tồn tại và được export.

### 3.4. Import alias

Alias cho phép đổi tên module hoặc khai báo khi sử dụng:

```text
import sales as s
from sales import Customer as Buyer
```

Alias hữu ích khi tên module dài hoặc khi hai module có các tên phổ biến giống nhau. Tuy nhiên, quy tắc alias phải nhất quán và không được làm mất khả năng truy vết về tên gốc trong diagnostic.

### 3.5. Import wildcard

Một số ngôn ngữ cho phép import tất cả tên công khai:

```text
import sales.*
```

Cách này ngắn nhưng có thể gây xung đột tên và làm phụ thuộc của tệp khó nhìn thấy. Nếu DSL hỗ trợ wildcard import, nên quy định rõ cách xử lý tên trùng, thứ tự tìm kiếm và cách công cụ hiển thị nguồn gốc của tên.

## 4. Namespace và tên đủ điều kiện

Namespace giúp phân biệt các khai báo có cùng tên nhưng thuộc những miền hoặc module khác nhau.

Ví dụ, hai module có thể cùng định nghĩa `Status`: một cho đơn hàng và một cho thanh toán.

```text
module sales.orders
enum Status { DRAFT, PAID, SHIPPED }

module billing.payments
enum Status { PENDING, SETTLED, FAILED }
```

Khi cả hai module được import, tham chiếu `Status` có thể trở nên mơ hồ. Tên đủ điều kiện (qualified name) giải quyết bằng cách nêu rõ namespace:

```text
sales.orders.Status
billing.payments.Status
```

### 4.1. Quy tắc phân giải tên không đủ điều kiện

Với tên ngắn như `Status`, DSL cần quy định thứ tự tìm kiếm. Một chính sách có thể là:

1. Scope cục bộ của biểu thức hoặc khai báo.
2. Scope bao quanh, từ gần đến xa.
3. Khai báo trong module hiện tại.
4. Các tên được import tường minh.
5. Namespace hoặc thư viện mặc định được DSL công bố.

Thứ tự này chỉ là ví dụ. Một DSL có thể chọn không cho phép nhập tên trần khi có nhiều nguồn phù hợp, và yêu cầu người viết dùng qualified name.

Không nên để kết quả phụ thuộc thứ tự tệp được nạp hoặc thứ tự phần tử trong một map. Nếu có nhiều ứng viên cùng mức ưu tiên, compiler nên báo lỗi mơ hồ.

### 4.2. Shadowing và xung đột tên

Shadowing xảy ra khi một tên ở scope gần hơn che khuất tên cùng tên ở scope ngoài. Ví dụ, biến cục bộ `Order` có thể che khuất kiểu `Order` được import. DSL phải quy định có cho phép shadowing hay không, và nếu có thì tên được phân giải theo thứ tự nào.

Với tên module, kiểu và hàm, một số DSL chọn namespace riêng để giảm xung đột. Ví dụ, `type.Order` và `module.Order` có thể được phân biệt theo loại tên. Nếu dùng chung một không gian tên, cần có quy tắc rõ cho khai báo trùng.

## 5. Symbol table toàn dự án

**Symbol table** là cấu trúc dữ liệu lưu thông tin về các tên đã khai báo và cho phép tra cứu chúng. Trong một DSL nhiều tệp, compiler thường cần symbol table theo nhiều cấp:

- Scope cục bộ của block hoặc biểu thức.
- Scope của khai báo như entity, rule hoặc workflow.
- Scope của module.
- Không gian tên công khai giữa các module.
- Registry hoặc package index của thư viện phụ thuộc.

Một symbol có thể lưu:

| Trường | Mục đích |
|---|---|
| Tên gốc | Tên được khai báo trong nguồn |
| Qualified name | Tên đầy đủ kèm namespace/module |
| Loại symbol | Entity, type, function, rule, constant... |
| Tệp nguồn | Vị trí khai báo |
| Source span | Dòng, cột hoặc offset của khai báo |
| Visibility | Private, module, public hoặc mức truy cập khác |
| Chữ ký/kiểu | Kiểu thuộc tính, tham số, kiểu trả về hoặc metadata liên quan |
| Module sở hữu | Module chứa khai báo |
| Export state | Có được phép tham chiếu từ module khác không |

### 5.1. Tách bảng tên theo module

Ví dụ cấu trúc khái quát:

```text
ProjectSymbolIndex
├── sales
│   ├── Customer -> customer.dsl:3
│   └── Order -> order.dsl:1
├── billing
│   └── Invoice -> invoice.dsl:1
└── shipping
    └── Shipment -> shipment.dsl:1
```

Khi `shipping` tham chiếu `sales.Order`, resolver tra cứu module `sales`, kiểm tra `Order` có được export và trả về symbol cùng source location.

### 5.2. Khai báo trùng

Nếu hai tệp trong cùng module khai báo cùng một tên mà DSL yêu cầu tên duy nhất, compiler cần phát hiện duplicate declaration. Diagnostic nên chỉ cả vị trí khai báo đầu tiên và vị trí khai báo trùng:

```text
Duplicate declaration: Customer
First declared at model/customer.dsl:4
Declared again at model/customer_extra.dsl:2
```

Không nên âm thầm để khai báo sau ghi đè khai báo trước trừ khi DSL chủ đích hỗ trợ cơ chế override với quy tắc rõ ràng.

### 5.3. Tên chưa được phân giải

Khi không tìm thấy tên, lỗi nên chỉ ra tên được yêu cầu, phạm vi đang tìm và các gợi ý phù hợp nếu có. Ví dụ:

```text
Unknown type: CustomerAdress
Did you mean: CustomerAddress?
The current module imports: sales, shipping
```

Gợi ý tên gần giống chỉ nên hỗ trợ người dùng; nó không được tự động thay thế tham chiếu trong chương trình.

## 6. Quy trình phân giải tên nhiều tệp

Một compiler có thể dùng quy trình nhiều pha để không phụ thuộc thứ tự tệp.

```text
Danh sách tệp đầu vào / project manifest
                |
                v
       Xác định module và package
                |
                v
       Đọc import và dependency
                |
                v
       Thu thập mọi khai báo
                |
                v
       Xây dựng symbol index
                |
                v
       Kiểm tra export / visibility
                |
                v
       Phân giải import và qualified names
                |
                v
       Phân giải tham chiếu trong AST
                |
                v
       Kiểm tra kiểu và ngữ nghĩa
```

### 6.1. Pha 1: xác định tập tệp và module

Compiler cần biết những tệp nào thuộc dự án hoặc đơn vị biên dịch. Tập tệp có thể đến từ manifest, cấu hình build, đường dẫn nguồn hoặc một lệnh compile nhận nhiều đầu vào.

Không nên tự động quét mọi tệp trong thư mục nếu điều đó không nằm trong đặc tả. Tập tệp đầu vào cần xác định ổn định để cùng một lệnh compile luôn xử lý cùng phạm vi.

### 6.2. Pha 2: đọc import và tạo dependency graph

Với mỗi module, compiler ghi nhận module mà nó phụ thuộc. Ví dụ:

```text
shipping -> sales
shipping -> inventory
sales -> common
inventory -> common
```

Đồ thị này cho biết `shipping` cần thông tin công khai từ `sales` và `inventory`; cả hai lại phụ thuộc `common`.

### 6.3. Pha 3: thu thập khai báo trước khi phân giải thân

Compiler đọc phần khai báo cấp cao nhất của tất cả tệp và tạo symbol table. Bước này cho phép một tệp tham chiếu tên được khai báo ở tệp khác, kể cả khi tệp khai báo chưa được xử lý thân trước.

Ví dụ, `order.dsl` dùng `Customer` trong khi `customer.dsl` khai báo `Customer`. Sau khi thu thập khai báo, resolver đã biết symbol `Customer` tồn tại; bước kiểm tra kiểu có thể tiếp tục khi định nghĩa cần thiết đã sẵn sàng.

### 6.4. Pha 4: phân giải import và visibility

Compiler kiểm tra module được import tồn tại, tên được import đã export và alias không xung đột. Nếu một module không công khai symbol, module khác không thể tham chiếu nó chỉ bằng cách biết tên.

### 6.5. Pha 5: phân giải tham chiếu trong AST

Mỗi identifier trong AST được liên kết với symbol tương ứng. Sau bước này, node tham chiếu không chỉ giữ chuỗi tên mà còn có thể giữ symbol ID hoặc con trỏ đến định nghĩa.

### 6.6. Pha 6: kiểm tra kiểu và ngữ nghĩa

Khi tên đã được phân giải, compiler mới có đủ thông tin để kiểm tra kiểu của thuộc tính, chữ ký hàm, quan hệ giữa entity và các quy tắc miền. Một tên không được phân giải không nên bị đoán kiểu dựa trên tên gần giống.

## 7. Forward reference và khai báo ở tệp khác

**Forward reference** là việc tham chiếu đến một khai báo xuất hiện sau vị trí sử dụng hoặc nằm trong một tệp được xử lý sau.

Ví dụ:

```text
// order.dsl
entity Order {
    customer: Customer
}

// customer.dsl
entity Customer {
    name: String
}
```

Nếu `Order` được phân tích trước `Customer`, compiler vẫn có thể xử lý bằng hai pha: thu thập tên và chữ ký khai báo trước, sau đó phân tích chi tiết kiểu và thân khai báo.

### 7.1. Declaration pass và definition pass

Một cách triển khai phổ biến:

1. **Declaration pass:** đọc tên, loại khai báo, visibility và chữ ký đủ để tạo symbol.
2. **Definition pass:** phân tích thuộc tính, biểu thức, thân rule hoặc hàm và kiểm tra các tham chiếu.

Với kiểu đệ quy hoặc quan hệ entity vòng, compiler có thể tạo symbol chưa hoàn chỉnh ở pha đầu rồi hoàn thiện ở pha sau.

### 7.2. Chữ ký trước, thân sau

Với hàm, có thể thu thập tên, tham số và kiểu trả về trước khi kiểm tra thân hàm. Nhờ vậy, hai hàm có thể gọi lẫn nhau nếu DSL cho phép và các chữ ký đã biết.

```text
// module a
function calculateA(x: Number): Number {
    return calculateB(x) + 1
}

// module b
function calculateB(x: Number): Number {
    return x * 2
}
```

Khả năng gọi qua lại còn phụ thuộc quy tắc import và chu trình module. Việc có thể biết chữ ký không tự động có nghĩa mọi phụ thuộc vòng đều được phép.

## 8. Đồ thị phụ thuộc và thứ tự xử lý

Các module tạo thành một dependency graph. Mỗi node là module hoặc đơn vị biên dịch; cạnh `A -> B` biểu thị A phụ thuộc vào B.

### 8.1. Đồ thị không chu trình (DAG)

Nếu đồ thị không có chu trình, compiler có thể xử lý theo thứ tự topo (topological order), thường là module phụ thuộc được xử lý trước module sử dụng nó.

Ví dụ:

```text
        common
        /    \\
       v      v
     sales  inventory
       \\      /
        v    v
        shipping
```

Một thứ tự hợp lệ là `common`, sau đó `sales` và `inventory`, cuối cùng `shipping`. Nếu hai module không phụ thuộc nhau, thứ tự giữa chúng có thể thay đổi mà không ảnh hưởng kết quả, miễn compiler không tạo ra phụ thuộc ngầm vào thứ tự xử lý.

### 8.2. Phát hiện chu trình

Ví dụ chu trình:

```text
A -> B
B -> C
C -> A
```

Compiler cần xác định chu trình có hợp lệ hay không. Có DSL cấm mọi import cycle để đơn giản hóa module initialization. Có DSL cho phép chu trình ở mức khai báo kiểu nhưng cấm chu trình khi thực thi hoặc khởi tạo giá trị.

Không nên chỉ báo “có circular dependency”. Diagnostic hữu ích nên chỉ ra đường đi tạo chu trình:

```text
Circular module dependency:
A imports B
B imports C
C imports A
```

### 8.3. Strongly connected components

Nếu DSL cho phép một số chu trình, compiler có thể tìm các thành phần liên thông mạnh (strongly connected components — SCC). Mỗi SCC được xử lý như một nhóm phụ thuộc chặt chẽ. Compiler có thể:

- Cho phép SCC chỉ chứa khai báo kiểu hoặc chữ ký.
- Yêu cầu mọi chữ ký trong nhóm được thu thập trước khi kiểm tra thân.
- Từ chối khởi tạo giá trị phụ thuộc vòng.
- Báo lỗi nếu chu trình chứa loại khai báo không được phép.

Quy tắc phải được định nghĩa theo semantics của DSL. Thuật toán SCC chỉ giúp phát hiện và nhóm chu trình; nó không tự quyết định chu trình nào hợp lệ.

## 9. Visibility và quyền truy cập xuyên tệp

Không phải khai báo nào cũng nên được truy cập từ mọi tệp. DSL có thể có nhiều mức visibility:

| Mức truy cập | Phạm vi tham khảo |
|---|---|
| Private/file-local | Chỉ trong tệp khai báo |
| Module/internal | Các tệp thuộc cùng module |
| Package | Các module hoặc namespace thuộc package được phép |
| Public/exported | Có thể được module khác import theo hợp đồng công khai |

Ví dụ:

```text
module sales

private function normalizeAddress(value: String): String {
    ...
}

export entity Customer {
    id: CustomerId
    name: String
}
```

Module khác có thể dùng `Customer` nếu import đúng, nhưng không thể gọi `normalizeAddress` nếu hàm đó chỉ private. Việc ẩn chi tiết nội bộ giúp module thay đổi implementation mà không buộc mọi consumer phải cập nhật.

### 9.1. Public API và implementation detail

Khai báo export là hợp đồng mà module cung cấp. Compiler nên kiểm tra chữ ký công khai không phụ thuộc vào kiểu private không thể truy cập từ bên ngoài, trừ khi DSL có cơ chế opaque type hoặc type abstraction để cho phép điều đó.

### 9.2. Re-export

Một module có thể xuất lại tên từ module khác:

```text
module commerce
import sales.Customer
export Customer
```

Re-export hữu ích để tạo API tổng hợp, nhưng cần quy định nguồn gốc symbol, quyền truy cập và cách xử lý khi hai module được re-export cùng một tên.

## 10. Xử lý tên mơ hồ và xung đột import

Giả sử một tệp import hai module đều export `Status`:

```text
import sales.orders
import billing.payments

let current: Status
```

Compiler không thể tự chọn một tên nếu hai ứng viên có cùng mức ưu tiên. Có thể giải quyết bằng qualified name:

```text
let orderStatus: sales.orders.Status
let paymentStatus: billing.payments.Status
```

Hoặc import alias:

```text
import sales.orders as Orders
import billing.payments as Payments

let current: Orders.Status
```

### 10.1. Quy tắc ưu tiên import

Nếu DSL cho phép import tên trần, nên quy định rõ:

- Import tường minh có ưu tiên hơn wildcard import không?
- Tên trong module hiện tại có che khuất tên import không?
- Alias có thể trùng với tên khai báo cục bộ không?
- Hai wildcard import cùng chứa một tên được xử lý thế nào?
- Re-export có tạo thêm một ứng viên hay giữ nguyên định danh nguồn?

Một lựa chọn an toàn là từ chối tên mơ hồ và yêu cầu người viết dùng qualified name hoặc alias. Cách này khiến nguồn gốc tham chiếu rõ ràng trong mã.

### 10.2. Không phụ thuộc thứ tự đọc tệp

Kết quả phân giải không nên thay đổi chỉ vì hệ điều hành liệt kê tệp theo thứ tự khác hoặc người dùng truyền danh sách đầu vào theo thứ tự khác. Nếu có quy tắc ưu tiên, nó phải dựa trên semantics của scope/import, không dựa trên thứ tự xử lý tình cờ.

## 11. Import path và tìm kiếm module

Compiler cần xác định import trỏ đến module nào. Một DSL có thể dùng tên module logic, đường dẫn tương đối hoặc package identifier.

Ví dụ:

```text
import sales.orders
import "../shared/money.dsl"
import package("company/common", version = "2.1")
```

Các hình thức trên có đặc tính khác nhau:

- **Tên module logic:** ổn định với cấu trúc thư mục, cần module resolver hoặc manifest.
- **Đường dẫn tương đối:** dễ hiểu trong dự án nhỏ nhưng có thể nhạy với vị trí tệp và cách tổ chức thư mục.
- **Package có phiên bản:** hỗ trợ tái sử dụng thư viện, nhưng cần quản lý dependency và version resolution.

### 11.1. Search path

Nếu compiler tìm module trong nhiều thư mục, thứ tự search path phải được quy định. Hai thư mục có cùng module name không nên dẫn đến lựa chọn ngẫu nhiên. Có thể báo lỗi trùng module hoặc yêu cầu cấu hình ưu tiên rõ ràng.

### 11.2. Canonical path và cùng một tệp được nạp nhiều lần

Một tệp có thể được tham chiếu qua nhiều đường dẫn tương đối hoặc symlink. Compiler cần có cách xác định danh tính nguồn để tránh phân tích và khai báo cùng một module hai lần ngoài ý muốn.

Có thể dùng canonical path, module identifier hoặc package identity. Với build từ xa và môi trường sandbox, danh tính module nên độc lập với đường dẫn máy cá nhân nếu cần kết quả tái lập.

### 11.3. Phiên bản phụ thuộc

Khi import package ngoài, compiler cần xác định phiên bản được dùng. Nếu hai module yêu cầu hai phiên bản không tương thích của cùng package, hệ thống phải có chính sách giải quyết xung đột, cô lập phiên bản hoặc báo lỗi.

## 12. Phân giải tên đệ quy và phụ thuộc vòng ở cấp khai báo

Không phải mọi tham chiếu vòng đều là lỗi. Hai entity có thể tham chiếu lẫn nhau:

```text
// customer.dsl
entity Customer {
    orders: List<Order>
}

// order.dsl
entity Order {
    customer: Customer
}
```

Đây có thể là mô hình hợp lệ nếu các tham chiếu là liên kết kiểu chứ không phải yêu cầu khởi tạo hai đối tượng ngay lập tức.

Compiler có thể xử lý bằng cách tạo symbol cho cả `Customer` và `Order` trước, sau đó hoàn thiện kiểu thuộc tính. Nếu kiểu cần kích thước hoặc giá trị khởi tạo phụ thuộc trực tiếp vào nhau, cần quy tắc riêng để phát hiện vòng lặp không thể giải quyết.

### 12.1. Tham chiếu kiểu và khởi tạo giá trị khác nhau

`Customer` chứa danh sách `Order` là một quan hệ kiểu. Nhưng nếu khai báo hằng số `A = B` và `B = A`, giá trị của chúng có thể không bao giờ được xác định. DSL cần phân biệt vòng tham chiếu kiểu được phép với vòng khởi tạo giá trị không hợp lệ.

### 12.2. Lazy resolution

Một số hệ thống trì hoãn phân giải hoặc khởi tạo đến khi tên thực sự được sử dụng. Cách này có thể hỗ trợ một số chu trình, nhưng cũng khiến lỗi xuất hiện muộn hơn. Cần xác định rõ thời điểm phát hiện và bảo đảm kết quả không phụ thuộc đường đi thực thi không mong muốn.

## 13. Chẩn đoán lỗi xuyên nhiều tệp

Khi phân giải tên thất bại, thông tin hữu ích thường nằm ở nhiều tệp: nơi tham chiếu, nơi khai báo ứng viên và nơi import. Diagnostic nên kết nối được các vị trí này.

Ví dụ tên không được export:

```text
Access error: sales.InternalDraft is not exported
Referenced from: shipping/rules.dsl:12:18
Declared at: sales/model.dsl:27:1
```

Ví dụ import không tìm thấy module:

```text
Cannot resolve module: inventory.stock
Imported from: shipping/shipping.dsl:1:1
Search locations checked:
  - project/modules
  - dependencies/company-common
```

Một diagnostic tốt nên có:

- Vị trí tham chiếu trong tệp đang phân tích.
- Tên đầy đủ đang được tìm.
- Module hoặc scope được tìm kiếm.
- Lý do thất bại: không tồn tại, không export, sai visibility hay mơ hồ.
- Vị trí các khai báo ứng viên nếu có.
- Gợi ý sửa như import, alias hoặc qualified name.

Không nên chỉ báo “undefined name” nếu nguyên nhân thực tế là tên tồn tại nhưng không được export. Phân biệt nguyên nhân giúp người dùng sửa đúng vấn đề.

## 14. Biên dịch tăng dần và cache phân giải tên

Trong dự án lớn, thay đổi một tệp không nên buộc compiler phân tích lại mọi tệp nếu không cần. Incremental compilation sử dụng quan hệ phụ thuộc và kết quả phân tích đã lưu để chỉ xử lý phần bị ảnh hưởng.

### 14.1. Dependency graph

Compiler có thể lưu cạnh phụ thuộc giữa module hoặc giữa symbol được sử dụng và symbol được khai báo. Khi một module thay đổi, hệ thống xác định những consumer cần được kiểm tra lại.

Ví dụ, `shipping` import `sales.Order`. Nếu chỉ thay đổi phần thân một rule nội bộ của `sales` mà không đổi API công khai, có thể không cần biên dịch lại tất cả consumer. Nếu thay đổi kiểu hoặc tên công khai của `Order`, những module tham chiếu đến nó có thể phải được kiểm tra lại.

### 14.2. API fingerprint hoặc module interface

Để xác định thay đổi có ảnh hưởng consumer không, compiler có thể tạo fingerprint từ API công khai:

- Tên và qualified name của khai báo export.
- Chữ ký kiểu và tham số.
- Visibility và modifier.
- Các kiểu miền được công khai.
- Metadata ảnh hưởng đến semantics.

Nếu fingerprint không đổi, một số bước phân giải hoặc kiểm tra của consumer có thể được tái sử dụng. Fingerprint phải bao gồm mọi thông tin công khai có ảnh hưởng đến kết quả.

### 14.3. Cache phải gắn với đầu vào và phiên bản

Kết quả phân giải tên phụ thuộc vào nội dung tệp, danh sách import, search path, phiên bản package, compiler và quy tắc ngôn ngữ. Cache cần được vô hiệu hóa khi một trong các yếu tố liên quan thay đổi.

Không nên cache chỉ theo tên tệp hoặc thời gian sửa đổi nếu hệ thống cần độ tin cậy cao. Hash nội dung và fingerprint dependency thường tạo căn cứ ổn định hơn.

### 14.4. Build xác định và tái lập

Cùng một tập nguồn, dependency và cấu hình nên tạo cùng kết quả phân giải. Search path, thứ tự ưu tiên và version resolution cần được kiểm soát để build trên máy khác hoặc CI không chọn module khác nhau.

## 15. Phân giải tên trong DSL nội bộ và DSL bên ngoài

Phân giải nhiều tệp xuất hiện ở cả hai loại DSL, nhưng cách tích hợp có thể khác.

- Với **DSL bên ngoài**, parser thường tạo AST cho từng tệp, sau đó module resolver kết hợp các AST hoặc symbol index thành một project model.
- Với **DSL nội bộ**, compiler của ngôn ngữ chủ thường xử lý import và module trước; thư viện DSL có thể xây dựng symbol model hoặc AST miền dựa trên các kiểu và API đã được liên kết.

Ví dụ, một DSL truy vấn nhúng trong Kotlin có thể tham chiếu kiểu `Order` được import từ package Kotlin. Việc tìm class hoặc symbol thuộc về compiler Kotlin; thư viện DSL có thể thực hiện thêm phân giải tên cho các field, alias hoặc schema động trong query model.

Vì vậy, cần xác định ranh giới: tên nào do host language resolver quản lý, tên nào thuộc DSL resolver. Nếu cả hai cùng xử lý một tên mà không có quy tắc phối hợp, diagnostic và visibility có thể trở nên khó hiểu.

## 16. Thiết kế import và module cho DSL

Khi thiết kế hệ thống nhiều tệp, có thể bắt đầu từ một tập quy tắc nhỏ và rõ:

1. Mỗi tệp hoặc nhóm tệp thuộc một module xác định.
2. Module có namespace duy nhất trong project hoặc package.
3. Khai báo phải được export mới có thể truy cập từ module khác.
4. Import có thể theo module hoặc theo tên cụ thể; alias được hỗ trợ để tránh xung đột.
5. Qualified name luôn cung cấp cách tham chiếu không mơ hồ.
6. Khai báo cấp cao nhất được thu thập trước khi phân giải thân để hỗ trợ forward reference.
7. Chu trình module được phát hiện; chỉ cho phép loại chu trình đã được đặc tả.
8. Thứ tự tìm kiếm và search path được xác định, không phụ thuộc thứ tự liệt kê tệp.
9. Mọi lỗi import hoặc name resolution có source location và thông tin nguồn gốc.
10. Dependency và API fingerprint được dùng để hỗ trợ incremental compilation nếu quy mô dự án cần.

Không phải DSL nào cũng cần package manager hoặc cơ chế dependency phức tạp. Một DSL cấu hình nhỏ có thể chỉ cần module name và import tương đối. Hãy chọn cơ chế phù hợp với quy mô, nhưng giữ semantics ổn định khi dự án mở rộng.

## 17. Ví dụ tổng hợp: phân giải tên giữa ba module

Giả sử dự án có ba module:

```text
common
  └── money.dsl

sales
  ├── customer.dsl
  └── order.dsl

shipping
  └── shipping-rule.dsl
```

Module `common` khai báo kiểu tiền:

```text
module common

export type Money {
    amount: Decimal
    currency: CurrencyCode
}
```

Module `sales` dùng `Money` và export `Order`:

```text
module sales
import common.Money

export entity Order {
    id: OrderId
    total: Money
    status: OrderStatus
}
```

Module `shipping` import `Order` và định nghĩa rule:

```text
module shipping
import sales.Order

rule freeShipping {
    when order.total.amount >= 1_000_000
    then shippingFee = Money(0, order.total.currency)
}
```

Quy trình resolver:

1. Đọc ba module và ghi nhận dependency `sales -> common`, `shipping -> sales`.
2. Thu thập symbol export: `common.Money`, `sales.Order`.
3. Kiểm tra `sales` được phép import `common.Money` và `shipping` được phép import `sales.Order`.
4. Phân giải `Order` trong `shipping` thành symbol `sales.Order`.
5. Phân giải `order.total` thành thuộc tính `total` của `sales.Order`, kiểu `common.Money`.
6. Phân giải `amount` và `currency` theo định nghĩa `common.Money`.
7. Kiểm tra kiểu của điều kiện và biểu thức tạo phí vận chuyển.

Nếu `Money` không được export, lỗi phải chỉ ra `sales.Order.total` phụ thuộc vào kiểu không thể truy cập. Nếu `Order` không được export, lỗi phải chỉ ra tham chiếu từ `shipping-rule.dsl` đến `sales.Order` bị từ chối. Nếu có hai module export `Order`, người viết phải dùng qualified name hoặc alias theo chính sách của DSL.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Xử lý tệp theo thứ tự liệt kê | Tham chiếu hợp lệ có thể lỗi khi thứ tự đầu vào đổi | Thu thập khai báo trước và dùng dependency graph |
| Đồng nhất tệp với module | Không tổ chức được module nhiều tệp hoặc nhiều namespace | Định nghĩa riêng file, module và compilation unit |
| Import tự động mọi tên | Tăng xung đột và khó biết nguồn gốc tên | Dùng export/import rõ ràng và qualified name |
| Không phân biệt public và private | Module bên ngoài truy cập implementation detail | Định nghĩa visibility và kiểm tra export |
| Chọn tên trùng theo thứ tự import | Kết quả không ổn định và khó dự đoán | Báo ambiguity hoặc yêu cầu alias |
| Không phát hiện dependency cycle | Compiler có thể lặp vô hạn hoặc khởi tạo sai | Phân tích graph và quy định loại cycle được phép |
| Chỉ báo tên không tồn tại | Người dùng không biết tên bị ẩn hay import sai | Phân biệt unknown, not exported, inaccessible và ambiguous |
| Cache không gắn với API dependency | Dùng symbol hoặc kiểu đã lỗi thời | Cache theo nội dung, phiên bản và fingerprint |
| Resolver và type checker dùng hai nguồn tên khác nhau | Một tên được nhận ở bước này nhưng bị từ chối ở bước khác | Chia sẻ symbol model hoặc hợp đồng phân giải thống nhất |

## 19. Kiểm thử phân giải tên nhiều tệp

Kiểm thử cần bao gồm các tình huống bình thường và lỗi ở cấp dự án:

- Một tệp import khai báo public từ module khác.
- Forward reference đến khai báo ở tệp được xử lý sau.
- Import tên cụ thể và import alias.
- Qualified name khi hai module có tên trùng.
- Tên private được tham chiếu từ module ngoài.
- Khai báo trùng trong cùng module.
- Hai wildcard import tạo tên mơ hồ.
- Module không tồn tại hoặc package không đúng phiên bản.
- Chu trình import được phép và chu trình bị cấm.
- Hai entity tham chiếu kiểu lẫn nhau.
- Thay đổi API công khai làm invalidation đúng consumer.
- Thay đổi phần thân nội bộ không làm rebuild quá mức.
- Thứ tự tệp đầu vào khác nhau vẫn cho cùng kết quả.

Với compiler có nhiều pha, nên kiểm tra cả symbol table và diagnostic. Có thể dùng project fixture gồm nhiều tệp nhỏ để xác nhận resolver trả đúng symbol và source location.

## 20. Kết luận

Phân giải nhiều tệp là quá trình liên kết tên được tham chiếu trong một tệp với khai báo nằm ở tệp hoặc module khác. Để thực hiện chính xác, DSL cần mô hình module và namespace, quy tắc export/import, visibility, alias, qualified name, symbol table và cách xử lý dependency.

Một pipeline nhiều pha — xác định tập tệp, đọc dependency, thu thập khai báo, xây dựng symbol index, phân giải import, liên kết tham chiếu rồi kiểm tra kiểu — giúp hỗ trợ forward reference mà không phụ thuộc thứ tự đọc tệp. Dependency graph cho phép phát hiện chu trình, xác định thứ tự xử lý và hỗ trợ biên dịch tăng dần.

Khi thiết kế DSL, hãy làm cho nguồn gốc của mỗi tên có thể dự đoán và truy vết. Tên mơ hồ, khai báo không được export, module không tìm thấy và dependency cycle cần có diagnostic rõ ràng. Những quy tắc nhất quán này giúp dự án DSL phát triển từ một tệp đơn lẻ thành nhiều module mà vẫn dễ hiểu, dễ bảo trì và có kết quả biên dịch ổn định.

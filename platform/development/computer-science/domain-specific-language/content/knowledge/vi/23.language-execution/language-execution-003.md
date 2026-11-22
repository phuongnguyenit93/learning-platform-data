# Biến và phạm vi chạy

Khi một DSL được thực thi, các biểu thức và câu lệnh cần một nơi để đọc, lưu và cập nhật giá trị. Biến cung cấp tên để chương trình tham chiếu đến giá trị; phạm vi chạy (runtime scope) xác định tên nào có thể được nhìn thấy tại một vị trí và giá trị đó tồn tại trong bao lâu. Hai khái niệm này là nền tảng của cách interpreter hoặc mã đích được sinh quản lý trạng thái trong quá trình thực thi DSL.

Ví dụ, một rule có thể dùng biến `order`, một biến cục bộ `discount` và một giá trị cấu hình `minimumTotal`. `order` có thể đến từ context của rule engine, `discount` chỉ tồn tại trong lần đánh giá hiện tại, còn `minimumTotal` có thể được khai báo ở cấp module. Nếu không xác định rõ nguồn gốc, phạm vi và vòng đời của các giá trị, cùng một tên có thể bị hiểu khác nhau giữa các lần chạy hoặc giữa các thành phần của chương trình.

## 1. Biến trong DSL là gì?

Biến là một binding (liên kết) giữa một tên và một giá trị hoặc một vị trí lưu trữ có thể chứa giá trị. Khi biểu thức tham chiếu tên biến, runtime tìm binding tương ứng trong môi trường hiện tại rồi lấy giá trị theo quy tắc của DSL.

Ví dụ:

```text
let quantity = 3
let unitPrice = Money(120_000, VND)
let total = quantity * unitPrice
```

Trong ví dụ này, `quantity`, `unitPrice` và `total` là các tên được liên kết với giá trị. Runtime cần biết kiểu và giá trị của từng binding để đánh giá biểu thức tiếp theo.

Biến trong DSL có thể đại diện cho:

- Giá trị tạm thời được tính trong một biểu thức hoặc block.
- Tham số truyền vào hàm, rule hoặc workflow.
- Dữ liệu của đối tượng miền như `order` hoặc `customer`.
- Cấu hình hoặc hằng số ở cấp module.
- Kết quả của một bước trước trong quy trình.
- Trạng thái được lưu giữa nhiều lần thực thi nếu DSL hỗ trợ persistence.

### 1.1. Tên biến và binding

Tên là cách chương trình gọi đến một binding. Binding còn có thể chứa thông tin kiểu, quyền đọc/ghi, phạm vi, vị trí khai báo và thời điểm khởi tạo.

Có thể mô hình hóa đơn giản:

```text
Binding
├── name: "quantity"
├── value: 3
├── type: Integer
├── mutable: false
└── declaration: source span
```

Đây là mô hình khái niệm. Runtime thực tế có thể lưu binding trong map, slot của stack frame, object, register hoặc cấu trúc khác.

### 1.2. Biến khác với thuộc tính

Biến cục bộ như `discount` thường được khai báo trong một block hoặc hàm. Thuộc tính như `order.total` thuộc về một đối tượng miền. Việc đọc/ghi thuộc tính có thể tuân theo quyền, validation, lazy loading hoặc tác dụng phụ khác với biến cục bộ.

Ví dụ:

```text
let discount = Money(0, VND)
order.discount = discount
```

`discount` là binding cục bộ; `order.discount` là thuộc tính của đối tượng `order`. Hai vị trí có thể chứa giá trị cùng kiểu nhưng có vòng đời và quy tắc cập nhật khác nhau.

## 2. Phạm vi chạy là gì?

Phạm vi (scope) là vùng chương trình trong đó một tên có thể được tham chiếu và được phân giải đến một binding cụ thể. Phạm vi chạy là cách runtime áp dụng các quy tắc đó trong lúc đánh giá chương trình.

Ví dụ:

```text
let threshold = 100

rule checkOrder {
    let eligible = order.total >= threshold
    if eligible {
        let message = "Approved"
        notify(message)
    }
}
```

`threshold` được khai báo ở phạm vi bên ngoài rule nên có thể được dùng trong rule nếu DSL cho phép rule nhìn thấy scope đó. `eligible` thuộc phạm vi của rule. `message` chỉ tồn tại trong block `if` và không thể được tham chiếu sau khi block kết thúc.

Phạm vi giúp:

- Giới hạn nơi một tên có thể được sử dụng.
- Tránh xung đột giữa các tên giống nhau ở những vùng khác nhau.
- Xác định cách tra cứu biến khi có nhiều khai báo cùng tên.
- Quản lý vòng đời và thời điểm giải phóng dữ liệu.
- Cô lập dữ liệu giữa các lần gọi hàm, rule hoặc workflow.
- Hỗ trợ kiểm tra kiểu và phân tích ngữ nghĩa.

### 2.1. Scope không chỉ là vị trí văn bản

Trong nhiều ngôn ngữ, scope được xác định từ cấu trúc mã nguồn (lexical scope). Runtime xây dựng môi trường tương ứng khi thực thi. Một số ngôn ngữ khác có dynamic scope, trong đó việc tìm tên phụ thuộc chuỗi lời gọi đang hoạt động. DSL cần công bố rõ mô hình nào được sử dụng.

### 2.2. Scope và lifetime là hai khái niệm liên quan nhưng khác nhau

Scope quyết định nơi tên có thể được nhìn thấy. Lifetime quyết định giá trị hoặc binding tồn tại trong khoảng thời gian nào. Một closure có thể giữ binding sau khi hàm khai báo đã kết thúc; khi đó vùng nhìn thấy theo cấu trúc chương trình và thời gian tồn tại vật lý không trùng nhau.

## 3. Environment và store trong runtime

Interpreter thường dùng hai khái niệm để mô tả trạng thái:

- **Environment (môi trường):** ánh xạ tên hoặc symbol đến binding.
- **Store (kho trạng thái):** ánh xạ vị trí lưu trữ đến giá trị hiện tại.

Ví dụ, environment có thể nói tên `quantity` trỏ đến vị trí `L1`; store lưu tại `L1` giá trị `3`.

```text
Environment E
├── quantity -> L1
└── total    -> L2

Store S
├── L1 -> 3
└── L2 -> Money(360000, VND)
```

Việc tách environment và store giúp mô tả biến mutable: binding vẫn trỏ đến cùng vị trí, nhưng giá trị trong store có thể thay đổi khi thực hiện phép gán.

### 3.1. Environment lồng nhau

Một môi trường có thể trỏ đến môi trường cha:

```text
Block Environment
├── message -> L3
└── parent -> Rule Environment
                  ├── eligible -> L2
                  ├── order    -> L1
                  └── parent -> Module Environment
```

Khi tìm tên `order` trong block, runtime kiểm tra block hiện tại trước. Nếu không tìm thấy, nó đi lên môi trường cha cho đến khi tìm được binding hoặc hết chuỗi môi trường.

### 3.2. Environment và symbol table

Symbol table thường là cấu trúc của compiler dùng để lưu thông tin khai báo và phân giải tên. Runtime environment lưu binding thực tế trong một lần chạy. Hai cấu trúc có thể liên kết với nhau qua symbol ID, nhưng không nhất thiết là cùng một đối tượng.

Compiler có thể gán mỗi biến một symbol ID và slot index. Runtime dùng slot index để truy cập nhanh thay vì tìm chuỗi tên trong map mỗi lần.

## 4. Các loại phạm vi thường gặp

Một DSL có thể có nhiều cấp scope. Tên gọi và ranh giới cụ thể tùy thiết kế, nhưng các cấp thường gặp gồm:

| Loại scope | Ví dụ | Phạm vi sử dụng |
|---|---|---|
| Global/project | Hằng số hoặc khai báo chung của dự án | Nhiều module theo chính sách truy cập |
| Module | Khai báo trong một module | Các tệp hoặc thành phần thuộc module |
| Rule/workflow | Context và biến của một rule/workflow | Trong lần đánh giá hoặc thực thi cấu trúc đó |
| Function | Tham số và biến cục bộ | Trong lần gọi hàm |
| Block | Biến khai báo trong `{ ... }` | Trong block và các block con |
| Expression/local binding | Biến tạm hoặc binding trong biểu thức | Trong vùng biểu thức được định nghĩa |

### 4.1. Global scope

Global scope chứa các tên được chia sẻ ở cấp chương trình hoặc runtime. Ví dụ, DSL có thể cung cấp hằng số `VND`, hàm `now()` hoặc dịch vụ `logger` ở phạm vi toàn cục.

Global scope cần được kiểm soát vì binding toàn cục có thể tạo phụ thuộc ẩn và gây khó khăn cho test. Những giá trị phụ thuộc môi trường như thời gian hiện tại hoặc cấu hình nên được truyền qua execution context nếu cần tính tái lập.

### 4.2. Module scope

Module scope chứa các khai báo thuộc module, chẳng hạn entity, function, constant hoặc rule được export. Quy tắc import/export quyết định module khác có thể truy cập tên nào.

Ví dụ:

```text
module sales

const minimumOrder: Money = Money(100_000, VND)
export function calculateTotal(order: Order): Money {
    return order.total
}
```

`minimumOrder` có thể chỉ dùng nội bộ module; `calculateTotal` được export. Phạm vi module và quyền truy cập cần được phân biệt: một tên có thể nằm trong module nhưng không được module khác nhìn thấy.

### 4.3. Function scope

Mỗi lần gọi hàm thường tạo một activation record hoặc stack frame chứa tham số, biến cục bộ, địa chỉ quay về và dữ liệu thực thi cần thiết.

```text
function calculateDiscount(order: Order): Money {
    let rate = 0.1
    let discount = order.total * rate
    return discount
}
```

`order`, `rate` và `discount` thuộc phạm vi của lần gọi hàm. Nếu hàm được gọi nhiều lần, mỗi lần gọi có binding cục bộ riêng, trừ khi DSL quy định biến static hoặc trạng thái dùng chung.

### 4.4. Block scope

Block scope giới hạn biến trong một khối lệnh:

```text
if order.isPaid {
    let statusMessage = "Paid"
    notify(statusMessage)
}

// statusMessage không còn nhìn thấy ở đây
```

Khi block kết thúc, binding cục bộ không còn được phân giải từ code phía sau. Nếu không có closure hoặc tham chiếu giữ lại, runtime có thể giải phóng dữ liệu tương ứng.

### 4.5. Rule và workflow scope

Với DSL nghiệp vụ, rule hoặc workflow có thể tạo scope riêng chứa đối tượng hiện tại, biến kết quả, trạng thái bước và thông tin thực thi.

Ví dụ:

```text
rule highValueOrder {
    let order = context.currentOrder
    let isHighValue = order.total >= context.minimumTotal
    when isHighValue
    then markForReview(order)
}
```

`context` có thể được cung cấp bởi rule engine; `order` và `isHighValue` là biến của lần đánh giá rule. Cần xác định chúng có được giữ lại giữa các lần đánh giá hay được tạo mới mỗi lần.

## 5. Lexical scope và dynamic scope

Có hai mô hình tra cứu tên quan trọng.

### 5.1. Lexical (static) scope

Lexical scope xác định binding dựa trên vị trí khai báo trong mã nguồn. Một hàm nhìn thấy các biến trong scope bao quanh nơi hàm được định nghĩa, không phụ thuộc hàm được gọi từ đâu.

Ví dụ:

```text
let rate = 0.1

function calculate(amount) {
    return amount * rate
}

function processOrder() {
    let rate = 0.2
    return calculate(100)
}
```

Với lexical scope, `calculate` sử dụng `rate` ở nơi nó được định nghĩa, nên kết quả là `10`, không phải `20`. Biến `rate` cục bộ trong `processOrder` không thay đổi binding mà `calculate` tham chiếu.

Ưu điểm của lexical scope là hành vi dễ dự đoán, dễ phân tích tĩnh và phù hợp với closure.

### 5.2. Dynamic scope

Dynamic scope tìm tên theo chuỗi lời gọi đang hoạt động. Trong ví dụ trên, khi `calculate` được gọi từ `processOrder`, nó có thể nhìn thấy `rate` trong caller và cho kết quả `20` nếu quy tắc dynamic scope được áp dụng.

Dynamic scope có thể tiện cho một số context tạm thời, nhưng làm hành vi phụ thuộc đường gọi. Cùng một hàm có thể cho kết quả khác khi được gọi từ nơi khác dù mã định nghĩa hàm không đổi.

### 5.3. DSL nên công bố mô hình nào?

Đối với phần lớn DSL hiện đại, lexical scope thường dễ hiểu và dễ kiểm tra hơn. Dynamic scope đôi khi được mô phỏng có chủ đích thông qua context object hoặc execution context thay vì thay đổi quy tắc phân giải tên của toàn ngôn ngữ.

Ví dụ, thay vì để `currentUser` được tìm động từ caller, DSL có thể truyền `context.currentUser` rõ ràng. Điều này làm phụ thuộc dễ thấy và hỗ trợ kiểm thử.

## 6. Quy tắc tra cứu tên

Với lexical scope, một quy tắc phổ biến là tìm từ scope gần nhất ra ngoài:

1. Scope của biểu thức hoặc block hiện tại.
2. Scope của block hoặc hàm bao quanh.
3. Scope của rule/workflow.
4. Scope module.
5. Scope global hoặc các binding mặc định được công bố.

Đây là một ví dụ; DSL cần xác định thứ tự cụ thể, nhất là khi có import, alias hoặc nhiều namespace.

### 6.1. Tra cứu qua chuỗi môi trường

Mã giả:

```text
lookup(name, environment):
    current = environment
    while current is not null:
        if current contains name:
            return current.binding(name)
        current = current.parent
    raise UnknownName(name)
```

Trong compiler đã phân giải tên trước khi chạy, runtime có thể không cần tra cứu theo chuỗi văn bản. AST node có thể chứa symbol ID hoặc slot index. Tuy vậy, mô hình môi trường lồng nhau vẫn hữu ích để hiểu semantics.

### 6.2. Tên chưa được khai báo

Nếu không tìm thấy tên trong bất kỳ scope hợp lệ nào, compiler có thể báo lỗi tĩnh. Với tên được tạo động hoặc dữ liệu runtime, lỗi có thể xuất hiện khi thực thi. DSL cần xác định tên nào có thể phân giải tĩnh và tên nào được phép tra cứu động.

### 6.3. Import và scope module

Import có thể đưa tên vào scope module hiện tại hoặc cho phép truy cập qua qualified name. Nếu hai module export cùng một tên, DSL cần quy tắc alias hoặc báo ambiguity. Runtime không nên tự chọn binding theo thứ tự nạp module.

## 7. Shadowing: che khuất tên

Shadowing xảy ra khi một binding trong scope bên trong có cùng tên với binding ở scope bên ngoài. Khi đó, quy tắc tra cứu thường chọn binding gần nhất.

Ví dụ:

```text
let status = "new"

if order.isPaid {
    let status = "paid"
    log(status)
}

log(status)
```

Trong block `if`, `status` tham chiếu biến cục bộ có giá trị `"paid"`. Sau block, `status` tham chiếu binding bên ngoài có giá trị `"new"`.

### 7.1. Shadowing có luôn được phép không?

Có DSL cho phép shadowing để tạo tên cục bộ ngắn gọn; DSL khác cấm khai báo trùng trong scope lồng nhau để giảm nhầm lẫn.

Nếu cho phép, compiler và IDE nên hiển thị binding mà mỗi tham chiếu trỏ đến. Nếu cấm, diagnostic nên chỉ vị trí khai báo bị che khuất và khai báo mới.

### 7.2. Shadowing khác với assignment

Khai báo mới trong scope con tạo binding khác. Assignment cập nhật binding đã được phân giải.

```text
let count = 1

if enabled {
    let count = 10  // binding mới, shadow binding ngoài
    count = count + 1
}

count = count + 1   // cập nhật binding bên ngoài
```

Không nên nhầm `let count = 10` với `count = 10`; một câu tạo binding, câu còn lại cập nhật binding đã tồn tại theo quy tắc DSL.

## 8. Khai báo, khởi tạo và assignment

Vòng đời của biến thường bắt đầu từ khai báo, tiếp theo là khởi tạo và có thể có các lần gán mới.

### 8.1. Khai báo

Khai báo tạo tên và binding trong một scope:

```text
let quantity: Integer
```

### 8.2. Khởi tạo

Khởi tạo gán giá trị ban đầu:

```text
let quantity: Integer = 3
```

DSL cần quy định có cho phép biến chưa khởi tạo không. Nếu có, đọc biến trước khi khởi tạo phải bị từ chối hoặc trả về một trạng thái rõ ràng; không nên trả về giá trị rác.

### 8.3. Assignment

Assignment cập nhật giá trị của binding mutable:

```text
var quantity = 3
quantity = quantity + 1
```

Compiler cần xác nhận biến có thể ghi và giá trị mới tương thích với kiểu. Nếu DSL dùng biến immutable, assignment sau khởi tạo sẽ là lỗi.

### 8.4. Khởi tạo một lần và gán nhiều lần

Có thể phân biệt `let` (binding không thể gán lại) với `var` (binding có thể gán lại). Đây là quy ước thường gặp nhưng DSL có thể dùng từ khóa khác hoặc chính sách khác.

```text
let currency = VND
var total = Money(0, currency)
total = total + order.total
```

`currency` không đổi binding; `total` được cập nhật nhiều lần. Việc giá trị bên trong một object có thể mutable hay không là vấn đề riêng với khả năng gán lại biến.

## 9. Mutable và immutable bindings

Biến mutable cho phép thay đổi giá trị được lưu tại binding; biến immutable không cho phép gán lại sau khi khởi tạo.

| Đặc điểm | Immutable | Mutable |
|---|---|---|
| Gán lại binding | Không | Có |
| Dễ suy luận luồng dữ liệu | Thường dễ hơn | Cần theo dõi các lần cập nhật |
| Dùng trong closure | Dễ xác định giá trị | Cần quy định capture và đồng bộ |
| Dùng trong xử lý song song | Ít nguy cơ race do gán lại | Cần kiểm soát chia sẻ |
| Ví dụ | `let threshold = 100` | `var attempts = 0` |

### 9.1. Immutable binding không có nghĩa object bất biến

Ví dụ:

```text
let order = loadOrder()
order.status = PAID
```

`order` có thể không được gán lại sang một object khác, nhưng object mà nó tham chiếu vẫn có thể thay đổi thuộc tính. DSL cần phân biệt immutable reference với immutable value.

### 9.2. Lợi ích của immutability

Binding bất biến giảm số trạng thái có thể xảy ra, giúp đọc code, tối ưu và chạy song song dễ hơn. Với rule engine, việc dùng biến tạm immutable có thể giúp mỗi lần đánh giá rule có kết quả nhất quán hơn.

### 9.3. Kiểm soát mutation

Nếu DSL cho phép mutation, cần xác định thay đổi có tác động ngay lên đối tượng chia sẻ hay chỉ tạo một phiên bản mới. Với dữ liệu miền, assignment có thể được chuyển thành command hoặc event thay vì sửa object trực tiếp.

## 10. Lifetime và storage của biến

Lifetime là khoảng thời gian binding hoặc giá trị còn tồn tại. Lifetime có thể ngắn hơn, bằng hoặc dài hơn scope nhìn thấy tên.

### 10.1. Biến cục bộ trong lần gọi

Biến cục bộ thông thường được tạo khi hàm hoặc block bắt đầu và hết hiệu lực khi phạm vi tương ứng kết thúc.

```text
function calculate(order) {
    let total = order.total
    return total
}
```

Khi hàm trả về, binding `total` không còn được dùng từ code gọi. Runtime có thể thu hồi slot stack frame nếu không còn closure hoặc tham chiếu giữ lại.

### 10.2. Stack frame

Mỗi lần gọi hàm có thể tạo stack frame chứa tham số và biến cục bộ:

```text
Call stack
┌─────────────────────────────┐
│ frame: processOrder         │
│ order -> slot 0             │
│ result -> slot 1            │
├─────────────────────────────┤
│ frame: calculateDiscount    │
│ order -> slot 0             │
│ rate -> slot 1              │
│ discount -> slot 2          │
└─────────────────────────────┘
```

Khi `calculateDiscount` kết thúc, frame của nó được bỏ khỏi call stack. Stack là một cách triển khai phổ biến, không phải yêu cầu của semantics DSL.

### 10.3. Heap và object được chia sẻ

Object có thể được cấp phát trên heap và được nhiều binding tham chiếu. Lifetime của object phụ thuộc còn tham chiếu hay cơ chế quản lý bộ nhớ, không chỉ phụ thuộc scope của một biến.

### 10.4. Module-level và global lifetime

Binding ở cấp module hoặc global có thể tồn tại suốt vòng đời chương trình hoặc runtime. Nếu chúng mutable, trạng thái có thể rò rỉ giữa các lần chạy rule hoặc request. Cần xác định rõ có reset hay không và ai được phép cập nhật.

### 10.5. Persistent state

Một workflow chạy lâu có thể cần lưu biến qua nhiều lần kích hoạt hoặc qua restart. Khi đó biến không còn là local runtime variable thông thường mà là trạng thái persistent, cần schema, versioning, serialization và quy tắc migration.

## 11. Closure và biến được capture

Closure là một hàm hoặc biểu thức có thể sử dụng các biến từ scope nơi nó được định nghĩa, ngay cả khi scope đó đã kết thúc.

Ví dụ:

```text
function makeThresholdChecker(minimum) {
    return function(order) {
        return order.total >= minimum
    }
}

let isLargeOrder = makeThresholdChecker(Money(500_000, VND))
```

Hàm bên trong sử dụng `minimum`, dù `makeThresholdChecker` đã trả về. Runtime phải giữ binding được capture đủ lâu để closure tiếp tục hoạt động.

### 11.1. Capture theo giá trị và theo tham chiếu

Có hai cách khái niệm thường gặp:

- **Capture by value:** closure giữ một bản sao hoặc giá trị tại thời điểm tạo closure.
- **Capture by reference:** closure giữ liên kết đến binding gốc, nên có thể quan sát các thay đổi sau đó.

Ví dụ:

```text
var rate = 0.1
let calculate = () => amount * rate
rate = 0.2
```

Nếu capture by reference, lời gọi sau đó có thể dùng `0.2`. Nếu capture by value tại thời điểm tạo, nó có thể dùng `0.1`. DSL cần quy định hành vi này.

### 11.2. Capture và lifetime

Khi closure giữ binding từ scope bên ngoài, runtime không thể giải phóng binding đó chỉ vì hàm tạo closure đã kết thúc. Có thể cần heap-allocate environment hoặc dùng closure object chứa các giá trị capture.

### 11.3. Capture mutable và concurrency

Nếu nhiều closure hoặc luồng cùng truy cập binding mutable, có thể phát sinh race condition. DSL cần quy định đồng bộ, isolation hoặc hạn chế capture mutable trong môi trường song song.

## 12. Biến trong rule engine

Rule engine thường đánh giá cùng một rule trên nhiều đối tượng hoặc nhiều lần khi dữ liệu thay đổi. Scope của biến cần được xác định theo từng lần đánh giá.

Ví dụ:

```text
rule reviewLargeOrder {
    let currentOrder = context.order
    let limit = context.reviewLimit
    let shouldReview = currentOrder.total >= limit

    when shouldReview
    then createReviewTask(currentOrder)
}
```

Các câu hỏi semantics:

- `currentOrder` được tạo mới cho mỗi lần đánh giá hay được giữ lại?
- `limit` là snapshot của context lúc bắt đầu hay đọc lại khi dùng?
- `shouldReview` có được cache không?
- Nếu cùng rule chạy song song trên hai order, binding có bị chia sẻ không?
- Action có thể cập nhật binding cục bộ hoặc chỉ được phép cập nhật trạng thái miền?

Một thiết kế dễ dự đoán thường tạo environment riêng cho mỗi lần đánh giá rule, chứa context và các biến local. Những binding global hoặc module được chia sẻ cần có chính sách rõ ràng.

### 12.1. Fact và context

Trong một rule engine, dữ liệu đầu vào có thể được gọi là facts, context hoặc variables. Cần phân biệt dữ liệu do engine cung cấp với biến do DSL khai báo. Dữ liệu context có thể chỉ đọc; biến cục bộ có thể được gán theo quy tắc khác.

### 12.2. Nhiều rule và chia sẻ trạng thái

Nếu nhiều rule cùng truy cập một object, thứ tự thực thi có thể ảnh hưởng giá trị quan sát được. Engine cần xác định rule chạy tuần tự, theo ưu tiên hay song song; mutation được commit ngay hay gom lại; và cách xử lý xung đột.

## 13. Biến trong workflow và thực thi kéo dài

Workflow thường có nhiều bước, có thể tạm dừng chờ sự kiện rồi tiếp tục sau. Vì vậy, scope và lifetime của biến cần gắn với vòng đời workflow.

Ví dụ:

```text
workflow fulfillOrder(orderId) {
    let order = loadOrder(orderId)
    let payment = charge(order)
    waitForConfirmation(payment.id)
    let shipment = createShipment(order)
    return shipment
}
```

Nếu workflow tạm dừng tại `waitForConfirmation`, các giá trị cần dùng ở bước sau có thể phải được lưu lại. Runtime có thể serialize workflow state thay vì giữ nguyên stack frame trong bộ nhớ.

### 13.1. Local variables và workflow state

Biến local chỉ tồn tại trong lần thực thi đồng bộ thông thường. Workflow state được lưu bền vững qua thời gian, có thể qua nhiều worker hoặc lần khởi động runtime.

Không phải mọi local variable đều cần serialize. Compiler hoặc workflow engine có thể phân tích biến nào còn được dùng sau điểm suspension và chỉ lưu các biến đó.

### 13.2. Versioning state

Khi workflow definition thay đổi trong lúc workflow cũ đang chạy, dữ liệu đã lưu có thể không còn khớp cấu trúc mới. Cần version state, migration hoặc chính sách tiếp tục bằng phiên bản definition ban đầu.

### 13.3. Isolation giữa các workflow instance

Mỗi instance thường cần environment riêng. Nếu biến của một instance bị chia sẻ với instance khác, dữ liệu khách hàng hoặc trạng thái xử lý có thể rò rỉ. Đây là ràng buộc cả về semantics lẫn bảo mật.

## 14. Execution context và biến được cung cấp sẵn

Runtime có thể cung cấp một execution context chứa thông tin môi trường:

```text
ExecutionContext
├── currentUser
├── tenant
├── clock
├── locale
├── permissions
├── transaction
├── services
└── input data
```

DSL có thể truy cập các thành phần này qua tên được định nghĩa hoặc qua đối tượng `context`. Cần xác định thành phần nào có sẵn, có thể ghi hay không, và có được truy cập ở mọi loại scope không.

### 14.1. Truyền context tường minh

Việc truyền context như tham số giúp dependencies dễ thấy:

```text
function evaluateOrder(context: ExecutionContext, order: Order) {
    return order.total >= context.minimumTotal
}
```

Cách này thuận tiện cho unit test vì có thể tạo context giả với clock, user và dữ liệu cụ thể.

### 14.2. Context không nên trở thành global mutable bag

Nếu mọi thành phần đều đọc và ghi tùy ý vào một context toàn cục, phụ thuộc trở nên khó truy vết và các lần thực thi có thể ảnh hưởng lẫn nhau. Nên phân biệt dữ liệu chỉ đọc, dịch vụ có tác dụng phụ và trạng thái cục bộ.

### 14.3. Clock và tính tái lập

Nếu DSL cung cấp `now()`, cùng một chương trình có thể cho kết quả khác ở những thời điểm khác nhau. Có thể đưa clock vào context để test có thể cố định thời gian và để workflow xác định thời điểm đánh giá.

## 15. Phạm vi và concurrency

Khi DSL cho phép chạy rule, task hoặc expression song song, biến mutable trở thành vấn đề quan trọng.

### 15.1. Race condition

Hai luồng có thể cùng đọc và cập nhật một biến:

```text
var counter = 0

parallel {
    counter = counter + 1
    counter = counter + 1
}
```

Nếu hai lần đọc/ghi không được đồng bộ, kết quả có thể không phải `2`. DSL cần xác định biến nào được chia sẻ, phép cập nhật có atomic không và cơ chế đồng bộ nào được hỗ trợ.

### 15.2. Thread-local hoặc task-local scope

Một số runtime tạo context riêng cho mỗi thread, task hoặc workflow instance. Điều này giúp tránh chia sẻ binding cục bộ, nhưng không tự bảo đảm object được tham chiếu là immutable hoặc không chia sẻ.

### 15.3. Isolation model

Các lựa chọn thiết kế có thể gồm:

- Chỉ cho phép biến local immutable trong nhánh chạy song song.
- Copy dữ liệu đầu vào cho mỗi task.
- Dùng message passing thay vì chia sẻ mutable state.
- Dùng lock hoặc atomic operations cho binding chia sẻ.
- Gộp kết quả của các task theo một phép merge được định nghĩa.

Không nên để kết quả phụ thuộc lịch scheduler nếu DSL không công bố semantics nondeterministic.

## 16. Phạm vi và bảo mật

Scope không chỉ giúp tổ chức tên; nó còn góp phần kiểm soát dữ liệu và quyền truy cập.

### 16.1. Least privilege

Một rule chỉ nên nhìn thấy dữ liệu và dịch vụ cần thiết cho nhiệm vụ. Không nên đưa mọi biến global, secret hoặc service nhạy cảm vào mọi environment.

### 16.2. Secret và credential

Credential có thể được cung cấp qua secret store hoặc capability riêng, thay vì biến global có thể in ra log. Diagnostic và debug view cần tránh hiển thị giá trị bí mật.

### 16.3. Tenant isolation

Trong hệ thống multi-tenant, context và store phải bảo đảm binding của tenant này không thể được truy cập từ tenant khác. Scope riêng là một phần của thiết kế, nhưng cần kết hợp kiểm tra quyền ở runtime.

### 16.4. Shadowing tên nhạy cảm

Cho phép biến cục bộ shadow tên như `currentUser` hoặc `permissions` có thể gây nhầm lẫn. DSL có thể cấm shadowing một số tên context đặc biệt hoặc yêu cầu qualified access để giữ nguồn gốc rõ ràng.

## 17. Ví dụ triển khai environment đơn giản

Một interpreter nhỏ có thể mô hình hóa environment như map tên đến binding và có con trỏ đến parent:

```text
Environment:
    values: Map<Name, Value>
    parent: Environment?

define(name, value):
    values[name] = value

lookup(name):
    if name in values:
        return values[name]
    if parent exists:
        return parent.lookup(name)
    raise UnknownVariable(name)

assign(name, value):
    if name in values:
        values[name] = value
        return
    if parent exists:
        parent.assign(name, value)
        return
    raise UnknownVariable(name)
```

`define` tạo binding trong environment hiện tại. `lookup` tìm từ trong ra ngoài. `assign` cập nhật binding gần nhất đã tồn tại. Một DSL có thể chọn semantics khác, chẳng hạn cấm assignment xuyên scope hoặc yêu cầu khai báo mutable rõ ràng.

### 17.1. Tạo scope con

Khi bước vào block:

```text
blockEnvironment = Environment(parent = currentEnvironment)
execute(block.statements, blockEnvironment)
```

Khi block kết thúc, runtime khôi phục environment trước đó. Nếu closure giữ lại block environment, nó có thể tiếp tục tồn tại sau khi block kết thúc.

### 17.2. Activation record cho hàm

Khi gọi hàm, runtime có thể tạo environment mới chứa tham số và biến local, với parent là lexical environment đã capture khi hàm được định nghĩa.

```text
callEnvironment = Environment(parent = function.closureEnvironment)
bind parameters into callEnvironment
execute function body in callEnvironment
```

Cách này mô phỏng lexical scope và closure. Một runtime tối ưu có thể dùng slot index hoặc frame layout thay vì map.

## 18. Biến trong generated code

Nếu DSL được biên dịch sang target language, backend phải ánh xạ biến và scope của DSL sang cơ chế tương ứng của target.

### 18.1. Name mangling

Tên DSL có thể trùng keyword hoặc tên biến tạm do compiler tạo. Backend cần đổi tên để tránh xung đột nhưng vẫn giữ mapping về symbol nguồn.

Ví dụ DSL:

```text
let class = "priority"
```

Nếu `class` là keyword của Java, backend có thể sinh `class_` hoặc một tên nội bộ duy nhất. Source map/debug metadata cần giữ liên kết với tên DSL `class`.

### 18.2. Scope mapping

Block DSL có thể ánh xạ sang block `{}` của target, function local hoặc object environment. Nếu target không có cùng semantics, backend phải sinh wrapper hoặc helper để mô phỏng.

### 18.3. Closure conversion

Nếu target không hỗ trợ closure theo đúng cách DSL cần, compiler có thể chuyển closure thành object chứa code và các giá trị capture. Việc capture by value hay by reference phải giữ đúng semantics nguồn.

### 18.4. Persistent workflow variables

Biến cần sống qua điểm suspension có thể được chuyển thành field trong state object thay vì local variable trên stack. Backend phải chỉ serialize các giá trị cần thiết và bảo đảm type/version tương thích.

## 19. Diagnostic liên quan đến biến và scope

Các lỗi phổ biến cần được báo ở đúng vị trí:

- Tên biến chưa được khai báo.
- Biến được dùng trước khi khởi tạo.
- Assignment vào binding immutable.
- Tên bị shadowing trái quy tắc.
- Biến không còn trong scope.
- Closure capture một biến không hợp lệ.
- Giá trị được chia sẻ ngoài phạm vi được phép.
- Biến workflow không thể serialize.
- Truy cập biến context không có quyền.

Ví dụ:

```text
Unknown variable "discount".
The variable is declared inside the previous if-block and is not visible here.
```

Hoặc:

```text
Cannot assign to immutable binding "currency".
Declared with "let" at rules/pricing.dsl:4:5.
```

Diagnostic nên cung cấp vị trí khai báo liên quan, scope hiện tại và gợi ý khai báo hoặc truyền giá trị phù hợp.

## 20. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Không định nghĩa thứ tự tra cứu tên | Cùng tên có thể trỏ đến binding khác nhau | Công bố scope chain và quy tắc resolution |
| Nhầm khai báo với assignment | Biến bị tạo mới hoặc cập nhật ngoài ý muốn | Dùng cú pháp và semantics riêng cho define/assign |
| Không tách scope của mỗi lần gọi | Các lần gọi dùng chung biến local | Tạo activation environment riêng |
| Cho phép global mutable không kiểm soát | Trạng thái rò rỉ giữa request hoặc rule | Hạn chế global state và dùng context tường minh |
| Không quy định shadowing | Tên cục bộ che khuất dữ liệu quan trọng | Cho phép có điều kiện hoặc cấm shadowing |
| Không định nghĩa closure capture | Kết quả thay đổi khó dự đoán sau khi hàm ngoài kết thúc | Quy định capture by value/reference |
| Coi scope và lifetime là một | Closure hoặc workflow mất dữ liệu cần thiết | Định nghĩa riêng visibility và lifetime |
| Chia sẻ mutable state trong parallel block | Race condition và kết quả không xác định | Isolation, immutability hoặc synchronization |
| Dùng context như global bag | Phụ thuộc ẩn và khó test | Truyền context có cấu trúc, quyền rõ |
| Không version persistent state | Workflow cũ không tương thích definition mới | Schema versioning và migration |

## 21. Kiểm thử biến và phạm vi chạy

Kiểm thử cần xác nhận cả phân giải tên tĩnh và hành vi runtime:

1. Biến trong cùng block được đọc đúng.
2. Biến block con không nhìn thấy sau khi block kết thúc.
3. Scope lồng nhau tra cứu binding gần nhất.
4. Shadowing tạo binding riêng và không làm thay đổi binding ngoài.
5. Assignment cập nhật đúng binding đã phân giải.
6. Immutable binding từ chối assignment.
7. Mỗi lần gọi hàm có local environment riêng.
8. Closure giữ binding theo capture semantics đã định nghĩa.
9. Rule chạy song song không làm rò dữ liệu giữa các lần đánh giá.
10. Workflow lưu/khôi phục đúng biến qua điểm suspension.
11. Context không cho phép truy cập dữ liệu ngoài quyền.
12. Diagnostic trỏ đúng vị trí khai báo và tham chiếu.

Với DSL có interpreter và compiler backend, nên chạy cùng bộ test scope trên cả hai cách thực thi để xác nhận semantics nhất quán.

## 22. Nguyên tắc thiết kế biến và scope cho DSL

Khi thiết kế runtime, có thể áp dụng các nguyên tắc sau:

1. **Định nghĩa binding rõ ràng.** Phân biệt tên, giá trị, vị trí lưu trữ, kiểu và khả năng mutable.
2. **Công bố scope chain.** Nêu thứ tự tra cứu từ block đến module và global.
3. **Chọn lexical hoặc dynamic scope có chủ đích.** Không để hành vi tìm tên phụ thuộc implementation.
4. **Tách scope và lifetime.** Xác định riêng thời gian nhìn thấy tên và thời gian dữ liệu còn tồn tại.
5. **Phân biệt khai báo và assignment.** Quy định `let`, `var` hoặc cú pháp tương đương.
6. **Kiểm soát shadowing.** Cho biết tên nào được che khuất và cách truy cập binding ngoài.
7. **Định nghĩa closure capture.** Chọn capture by value/reference và xử lý lifetime.
8. **Cô lập từng lần thực thi.** Rule, function và workflow instance cần environment phù hợp.
9. **Hạn chế mutable shared state.** Xác định isolation và concurrency semantics.
10. **Truyền context tường minh.** Làm rõ dữ liệu, clock, quyền và dịch vụ runtime.
11. **Bảo vệ dữ liệu nhạy cảm.** Áp dụng least privilege và tenant isolation.
12. **Kiểm thử cả interpreter lẫn generated target.** Cùng một chương trình phải có semantics scope tương đương.

## 23. Kết luận

Biến là binding giữa tên và giá trị hoặc vị trí lưu trữ; phạm vi chạy xác định nơi tên có thể được phân giải trong quá trình thực thi. Runtime thường sử dụng environment để tra cứu binding và store để quản lý giá trị, với các scope lồng nhau cho block, function, rule, module và global.

Thiết kế DSL cần xác định rõ lexical hay dynamic scope, thứ tự tra cứu tên, shadowing, khai báo và assignment, mutability, lifetime và closure capture. Với rule engine và workflow, cần thêm quy tắc cô lập mỗi lần thực thi, lưu trạng thái qua suspension, xử lý concurrency và bảo vệ dữ liệu trong context.

Khi các quy tắc này được đặc tả nhất quán, interpreter và code generator có thể quản lý biến theo cùng một semantics. Người viết DSL cũng dễ dự đoán tên nào đang được dùng, giá trị tồn tại bao lâu và thay đổi ở một phạm vi có ảnh hưởng đến phần còn lại của chương trình hay không.

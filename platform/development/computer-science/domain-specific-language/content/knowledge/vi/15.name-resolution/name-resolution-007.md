# Liên kết tham chiếu

## 1. Liên kết tham chiếu trong phân giải tên

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường cho phép người viết đặt tên cho biến, trường dữ liệu, hàm, quy tắc, pipeline, tài nguyên hoặc thành phần cấu hình. Khi một tên được khai báo, các vị trí khác trong chương trình có thể dùng tên đó để tham chiếu đến thành phần đã khai báo. Công cụ DSL phải xác định chính xác mỗi lần xuất hiện của tên đang nói đến khai báo nào.

Quá trình xác định mối liên hệ đó được gọi là **liên kết tham chiếu (reference binding)**. Nó là một phần quan trọng của **phân giải tên (name resolution)**. Thay vì chỉ giữ chuỗi ký tự như customerId, công cụ xác định đối tượng khai báo mà tên đó đại diện trong ngữ cảnh cụ thể.

Ví dụ DSL giả định:

~~~text
let taxRate = 0.08

rule "calculate-tax" {
    let subtotal = order.subtotal
    let tax = subtotal * taxRate
    output tax
}
~~~

Trong ví dụ này:

- taxRate ở dòng khai báo là tên được định nghĩa.
- taxRate trong biểu thức nhân là một tham chiếu đến khai báo ở phía trên.
- subtotal trong biểu thức nhân tham chiếu đến khai báo subtotal trong khối rule.
- order có thể là một đối tượng được cung cấp sẵn bởi môi trường hoặc một tên được khai báo ở phạm vi bên ngoài.

Nếu công cụ chỉ lưu chuỗi taxRate trong cả hai vị trí, các giai đoạn sau phải tự tìm lại khai báo mỗi lần cần sử dụng. Nếu liên kết được thực hiện trong giai đoạn phân giải tên, nút tham chiếu có thể trỏ đến một symbol đã xác định. Điều này giúp kiểm tra kiểu, kiểm tra quyền, phân tích phụ thuộc, sinh mã và thực thi chính xác hơn.

Liên kết tham chiếu không đơn giản là tìm chuỗi có cùng cách viết. Cùng một tên có thể xuất hiện ở nhiều phạm vi, bị che khuất bởi khai báo gần hơn, được nhập từ module khác hoặc có nhiều phiên bản hàm được phân biệt bằng kiểu tham số. Kết quả phụ thuộc vào quy tắc tên của DSL.

## 2. Khai báo, tham chiếu và symbol

Ba khái niệm cần phân biệt:

- **Khai báo (declaration):** vị trí tạo ra một tên và giới thiệu một thành phần vào môi trường tên. Ví dụ khai báo biến, hàm, rule hoặc module.
- **Tham chiếu (reference):** vị trí sử dụng một tên đã được khai báo hoặc được cung cấp bởi môi trường.
- **Symbol:** bản ghi nội bộ đại diện cho thành phần được khai báo, thường gồm tên, loại, kiểu, phạm vi, vị trí nguồn và metadata khác.

Ví dụ:

~~~text
let discount = 15
let finalPrice = price - discount
~~~

Trong đoạn này, hai khai báo tạo ra hai symbol: discount và finalPrice. Tên price là một tham chiếu; nếu không có khai báo price trong phạm vi hiện tại hoặc môi trường được phép, công cụ sẽ báo lỗi tên chưa được giải quyết.

Một symbol thường chứa thông tin như:

| Trường | Mục đích |
|---|---|
| Symbol ID | Định danh ổn định trong một lần phân tích hoặc phiên bản chương trình |
| Name | Tên được khai báo |
| Kind | Loại thành phần: biến, hàm, kiểu, rule, module, field... |
| Type | Kiểu dữ liệu hoặc kiểu chữ ký nếu có |
| Declaration location | Vị trí khai báo trong nguồn |
| Scope | Phạm vi mà symbol có hiệu lực |
| Visibility | Quy tắc truy cập: local, module, public hoặc private |
| Owner | Module, lớp miền hoặc khối chứa khai báo |
| Metadata | Thuộc tính bổ sung phục vụ compiler hoặc runtime |

Không phải mọi DSL cần toàn bộ trường này. Một DSL cấu hình nhỏ có thể chỉ cần tên, loại, vị trí và phạm vi. DSL có module, kiểu dữ liệu, plugin hoặc phân quyền sẽ cần mô hình symbol phong phú hơn.

### 2.1. Tên khai báo và tên tham chiếu trong AST

AST nên phân biệt nút định nghĩa tên với nút sử dụng tên nếu hai vị trí có trách nhiệm khác nhau:

~~~text
VariableDeclaration
├── DeclaredName("discount")
└── NumberLiteral(15)

VariableDeclaration
├── DeclaredName("finalPrice")
└── Subtract
    ├── NameReference("price")
    └── NameReference("discount")
~~~

Sau khi phân giải tên, nút NameReference("discount") có thể được gắn symbol ID trỏ đến khai báo discount. Tên văn bản vẫn được giữ để hiển thị, nhưng các thao tác phân tích có thể dùng liên kết đã xác định.

### 2.2. Tên hiển thị và định danh nội bộ

Tên do người dùng viết không nhất thiết là định danh tốt nhất để dùng trong toàn bộ compiler. Hai phạm vi khác nhau có thể có biến cùng tên x. Vì vậy, compiler thường tạo symbol ID riêng:

~~~text
Scope A: x -> symbol-101
Scope B: x -> symbol-205
~~~

Hai tên hiển thị giống nhau nhưng đại diện cho hai symbol khác nhau. Điều này giúp compiler không nhầm lẫn khi phân tích biểu thức nằm trong các phạm vi khác nhau.

## 3. Liên kết tham chiếu diễn ra ở giai đoạn nào?

Một pipeline xử lý DSL có thể gồm các giai đoạn:

~~~text
Source text
    |
    v
Lexer / Tokenizer
    |
    v
Parser
    |
    v
AST construction
    |
    v
Name resolution
    |
    v
Type and semantic analysis
    |
    v
IR / Execution plan
    |
    v
Interpreter or code generation
~~~

Parser xác định rằng một vị trí là tên định danh theo grammar. Parser có thể tạo nút NameReference nhưng thường chưa biết nó trỏ đến khai báo nào. Name resolver tra cứu tên trong các phạm vi, xác định symbol phù hợp và gắn liên kết vào nút tham chiếu.

Sau khi liên kết, bộ kiểm tra kiểu có thể dùng symbol để lấy kiểu dữ liệu hoặc chữ ký hàm. Bộ kiểm tra ngữ nghĩa có thể xác nhận symbol có được phép dùng tại vị trí đó hay không. Code generator hoặc interpreter có thể dùng symbol ID để truy cập đúng biến hoặc hàm.

Một số DSL nhỏ kết hợp parsing và name resolution trong cùng một lượt. Cách này có thể đơn giản khi ngữ pháp chỉ cho phép khai báo trước khi dùng. Tuy nhiên, tách hai giai đoạn thường hữu ích khi hỗ trợ tham chiếu trước khai báo, module, import, nhiều loại namespace hoặc phân tích gia tăng.

## 4. Phạm vi tên và môi trường tra cứu

Phạm vi (scope) xác định nơi một khai báo có thể được nhìn thấy. Mỗi tham chiếu được phân giải trong một môi trường tên phù hợp với vị trí của nó.

Ví dụ:

~~~text
let region = "global"

rule "north-report" {
    let limit = 100
    filter amount > limit
    output region
}
~~~

Nếu DSL dùng phạm vi từ vựng, tham chiếu limit được tìm thấy trong scope của rule; region không có trong scope đó nên resolver đi lên scope cha và tìm thấy khai báo ở cấp ngoài.

### 4.1. Phạm vi từ vựng (lexical scope)

Với lexical scope, nơi một tên được khai báo trong cấu trúc nguồn quyết định những vị trí có thể nhìn thấy nó. Resolver thường bắt đầu ở scope chứa tham chiếu, sau đó lần lượt tra cứu scope cha cho đến khi tìm thấy tên hoặc đến scope gốc.

~~~text
Global Scope
  ├── region
  └── Rule Scope
        ├── limit
        └── Step Scope
              └── threshold
~~~

Một tham chiếu trong Step Scope có thể tìm tên theo thứ tự:

1. Step Scope.
2. Rule Scope.
3. Global Scope.
4. Các môi trường được DSL quy định thêm, chẳng hạn built-in symbols.

Thứ tự này phải được xác định trong đặc tả. Nếu import hoặc built-in được ưu tiên ở vị trí khác, resolver phải tuân theo thứ tự đã công bố.

### 4.2. Phạm vi động (dynamic scope)

Với dynamic scope, việc tìm tên có thể phụ thuộc chuỗi lời gọi tại thời điểm thực thi thay vì cấu trúc khai báo trong nguồn. Cách này ít phổ biến hơn trong DSL hiện đại vì làm kết quả phụ thuộc vào ngữ cảnh chạy và khó phân tích tĩnh.

Ví dụ minh họa:

~~~text
let rate = 0.05

function calculate() {
    return amount * rate
}

function run() {
    let rate = 0.10
    calculate()
}
~~~

Với lexical scope, calculate tham chiếu đến rate ở nơi function được định nghĩa. Với dynamic scope, một số ngôn ngữ có thể tra rate theo chuỗi gọi và lấy giá trị trong run. DSL cần nói rõ chính sách nếu hỗ trợ cơ chế tương tự.

### 4.3. Scope lồng nhau và phạm vi khối

Một block có thể tạo scope mới:

~~~text
rule "discount" {
    let rate = 0.10

    if customer.isMember {
        let rate = 0.15
        apply_discount rate
    }

    apply_discount rate
}
~~~

Trong khối if, tên rate có thể trỏ đến khai báo gần nhất trong block if. Sau khi ra khỏi block, tham chiếu rate trỏ lại khai báo trong rule. Đây là hiện tượng shadowing, sẽ được giải thích ở phần sau.

Không phải mọi block cú pháp đều phải tạo scope. DSL cần quy định block nào tạo môi trường tên mới, block nào chỉ nhóm câu lệnh và block nào kế thừa hoặc chia sẻ scope.

## 5. Bảng symbol và cách tra cứu

Symbol table là cấu trúc dữ liệu lưu các khai báo có thể được tra cứu. Một scope thường có bảng symbol riêng và liên kết đến scope cha.

Mô hình khái quát:

~~~text
Scope
  parent: Scope?
  symbols: Map<Name, Symbol>
  children: List<Scope>
~~~

Khi phân giải một tham chiếu tên:

1. Tra tên trong bảng symbol của scope hiện tại.
2. Nếu tìm thấy, kiểm tra loại symbol có phù hợp với cách sử dụng không.
3. Nếu không tìm thấy, tra scope cha theo quy tắc của DSL.
4. Tiếp tục cho đến khi tìm thấy hoặc hết môi trường tra cứu.
5. Nếu không tìm thấy, tạo chẩn đoán unresolved reference.

Ví dụ pseudocode:

~~~text
resolve(name, scope):
    current = scope
    while current is not null:
        if current.symbols contains name:
            return current.symbols[name]
        current = current.parent
    return UNRESOLVED
~~~

Đây là cách tra cứu cơ bản cho một tên đơn trong lexical scope. Ngôn ngữ có namespace, import, overload hoặc tên phân cấp cần thêm bước phân giải tương ứng.

### 5.1. Kiểm tra loại symbol

Tìm thấy tên chưa có nghĩa là tham chiếu hợp lệ. Ví dụ:

~~~text
let retries = 3
call retries()
~~~

Nếu retries là biến số nguyên, nó không thể được gọi như một hàm. Resolver có thể xác định tên đã tồn tại nhưng sai loại; type checker hoặc semantic analyzer sẽ báo lỗi phù hợp.

Do đó cần phân biệt:

- Unresolved: không tìm thấy symbol.
- Resolved but wrong kind: tìm thấy tên nhưng không đúng loại được yêu cầu.
- Resolved and valid: tìm thấy symbol phù hợp với ngữ cảnh.
- Ambiguous: có nhiều symbol cùng phù hợp và không có quy tắc chọn duy nhất.

### 5.2. Khóa tra cứu và phân biệt hoa thường

DSL cần xác định tên có phân biệt chữ hoa thường không. Nếu có, Customer và customer là hai tên khác nhau. Nếu không, resolver cần chuẩn hóa tên trước khi tra cứu và xử lý trường hợp hai khai báo khác nhau chỉ bởi cách viết hoa thường.

Không nên chuẩn hóa Unicode hoặc thay đổi dấu tiếng Việt tùy tiện. Quy tắc so sánh tên cần được ghi rõ để parser, compiler, formatter và công cụ IDE có cùng kết quả.

## 6. Liên kết tham chiếu theo từng loại tên

Không phải mọi tên đều được tra cứu theo cùng một namespace. DSL có thể có nhiều loại tên:

| Loại tên | Ví dụ | Nơi tra cứu thường gặp |
|---|---|---|
| Biến | total, region | Scope biến |
| Trường dữ liệu | customer_id, amount | Schema hoặc kiểu của dữ liệu |
| Hàm | sum, normalize | Namespace hàm hoặc module |
| Kiểu | Customer, Money | Namespace kiểu |
| Rule | eligible-customer | Registry rule hoặc module |
| Pipeline | daily-report | Registry pipeline |
| Tài nguyên | warehouse.main | Namespace tài nguyên |
| Module | billing.tax | Module/import resolver |

Một DSL có thể dùng chung một namespace cho mọi tên. Cách này đơn giản nhưng dễ tạo xung đột. Một DSL khác có thể tách namespace biến, hàm, kiểu và tài nguyên để các tên giống nhau vẫn có thể tồn tại trong các nhóm khác nhau.

### 6.1. Trường dữ liệu và biến

Trong biểu thức:

~~~text
filter customer.status == "ACTIVE"
~~~

customer có thể là biến hoặc đối tượng dữ liệu; status có thể là trường của kiểu Customer. Resolver cần biết customer thuộc scope nào và schema của nó có trường status hay không. Việc tìm trường thường là một bước phân giải thành viên (member resolution), khác với tra cứu biến đơn giản.

### 6.2. Thành viên và chuỗi truy cập

Với biểu thức:

~~~text
order.customer.address.city
~~~

Quá trình có thể diễn ra theo từng bước:

1. Phân giải order thành một symbol hoặc giá trị có kiểu.
2. Dựa vào kiểu của order để tìm thành viên customer.
3. Dựa vào kiểu của customer để tìm address.
4. Dựa vào kiểu của address để tìm city.

Nếu một thành viên không tồn tại hoặc kiểu ở bước trước không có thành viên cần tìm, công cụ báo lỗi tại phần tương ứng. Không nên chỉ báo toàn bộ chuỗi truy cập là không hợp lệ nếu có thể xác định chính xác thành phần gây lỗi.

## 7. Tên đủ điều kiện và namespace

Tên đủ điều kiện (qualified name) dùng nhiều thành phần để xác định rõ vị trí của một symbol:

~~~text
module.submodule.function
domain.customer.status
~~~

Tên đủ điều kiện giúp tránh xung đột giữa các module hoặc nhóm khái niệm. Resolver có thể lần theo từng namespace từ trái sang phải.

Ví dụ:

~~~text
module billing {
    function calculateTax(amount) {
        return amount * 0.08
    }
}

module shipping {
    function calculateTax(amount) {
        return amount * 0.02
    }
}

use billing.calculateTax(100)
use shipping.calculateTax(100)
~~~

Hai hàm có cùng tên đơn nhưng khác namespace. Tên đầy đủ xác định chính xác hàm được tham chiếu.

### 7.1. Namespace lồng nhau

Namespace có thể được tổ chức thành cây:

~~~text
Root
├── billing
│   ├── invoice
│   └── tax
└── shipping
    ├── parcel
    └── tax
~~~

Resolver đi theo các thành phần của qualified name và báo lỗi tại thành phần đầu tiên không tồn tại. Cần quy định dấu phân cách namespace, cách escape nếu tên chứa dấu đó và quy tắc phân biệt namespace với truy cập thành viên của đối tượng.

### 7.2. Tên ngắn và tên đủ điều kiện

Một DSL có thể cho phép dùng tên ngắn khi namespace đã được import:

~~~text
import billing.tax

calculateTax(100)
~~~

Nếu có nhiều module cùng export calculateTax, tên ngắn có thể trở nên mơ hồ. Khi đó người viết cần dùng tên đủ điều kiện hoặc alias được DSL hỗ trợ. Import không nên âm thầm thay đổi kết quả tra cứu theo thứ tự không ổn định.

## 8. Import và liên kết giữa các module

Với DSL có nhiều tệp hoặc module, tham chiếu có thể trỏ đến khai báo nằm ngoài tệp hiện tại. Import tạo khả năng đưa symbol từ module khác vào môi trường tên hiện tại.

Ví dụ:

~~~text
// module: billing
export function calculateTax(amount) {
    return amount * 0.08
}
~~~

~~~text
// module: monthly-report
import billing.calculateTax

let tax = calculateTax(250)
~~~

Resolver cần:

1. Xác định module billing.
2. Tìm symbol calculateTax được export.
3. Kiểm tra symbol có thể truy cập từ module hiện tại không.
4. Đưa symbol vào môi trường import hoặc tạo alias theo quy tắc.
5. Liên kết lời gọi calculateTax với symbol đã tìm thấy.

### 8.1. Import toàn bộ và import chọn lọc

Import toàn bộ đưa một nhóm tên công khai vào phạm vi:

~~~text
import billing.tax.*
~~~

Import chọn lọc chỉ đưa các tên cần dùng:

~~~text
import billing.tax.calculateTax
import billing.tax.TaxPolicy
~~~

Import chọn lọc thường làm nguồn gốc tên rõ hơn và giảm nguy cơ xung đột. Import wildcard tiện khi module có nhiều thành phần thường dùng cùng nhau, nhưng cần có quy tắc rõ nếu nhiều module export tên giống nhau.

### 8.2. Alias import

Một số DSL cho phép đổi tên khi import:

~~~text
import billing.tax as taxModule

taxModule.calculateTax(250)
~~~

Alias giúp tránh trùng namespace và rút gọn tên dài. Resolver phải ghi nhận alias như một liên kết đến module gốc; không nên tạo một bản sao symbol độc lập vì điều đó có thể làm sai danh tính và metadata của khai báo.

### 8.3. Visibility và export

Không phải khai báo nào cũng được module khác truy cập. DSL có thể hỗ trợ:

- private: chỉ dùng trong module hoặc scope quy định.
- internal: dùng trong một nhóm module.
- public/export: có thể được module khác import.

Resolver cần phân biệt tên tồn tại nhưng không được phép truy cập với tên hoàn toàn không tồn tại. Thông báo lỗi có thể nói symbol không được export hoặc không có visibility phù hợp mà không tiết lộ các chi tiết nội bộ không cần thiết.

### 8.4. Phụ thuộc vòng giữa module

Nếu module A import B và B import A, hệ thống có phụ thuộc vòng. DSL cần quy định có cho phép hay không. Nếu cho phép, resolver có thể cần tách việc đăng ký khai báo khỏi việc phân tích thân hàm, hoặc dùng nhiều lượt để các tên được biết trước khi phân tích tham chiếu.

Nếu không cho phép, module loader nên phát hiện chu trình và báo đường đi tạo thành vòng phụ thuộc, ví dụ A -> B -> C -> A.

## 9. Tham chiếu trước khai báo và thứ tự khai báo

Một DSL phải quyết định tham chiếu có được phép xuất hiện trước vị trí khai báo hay không.

Ví dụ:

~~~text
rule "report" {
    output total
}

let total = 125
~~~

Có hai chính sách phổ biến:

- **Khai báo trước khi dùng:** tên chỉ có hiệu lực sau vị trí khai báo. Ví dụ trên không hợp lệ.
- **Phân giải toàn phạm vi:** compiler thu thập khai báo trước, sau đó liên kết tham chiếu. Ví dụ có thể hợp lệ nếu quy tắc scope cho phép.

### 9.1. Phân giải một lượt

Trong mô hình một lượt, parser hoặc resolver xử lý theo thứ tự nguồn. Khi gặp khai báo, symbol được thêm vào bảng; khi gặp tham chiếu, resolver tra bảng hiện có.

Ưu điểm là đơn giản và có thể xử lý trực tuyến. Hạn chế là khó hỗ trợ tham chiếu trước khai báo hoặc khai báo phụ thuộc lẫn nhau.

### 9.2. Phân giải nhiều lượt

Trong mô hình nhiều lượt:

1. Thu thập module và khai báo.
2. Tạo symbol cho các tên đã khai báo.
3. Xây dựng scope và quan hệ import.
4. Duyệt các tham chiếu để liên kết với symbol.
5. Kiểm tra kiểu và quy tắc ngữ nghĩa.

Cách này hỗ trợ forward reference và nhiều loại phụ thuộc hơn, nhưng cần xử lý khai báo trùng, module vòng và các khai báo có điều kiện.

### 9.3. Hàm đệ quy và tham chiếu lẫn nhau

Hàm có thể gọi chính nó:

~~~text
function factorial(n) {
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}
~~~

Khi phân tích thân hàm, symbol factorial phải có sẵn trong scope để lời gọi đệ quy được liên kết. Với hai hàm gọi lẫn nhau, compiler có thể cần đăng ký cả hai khai báo trước khi phân tích thân của chúng.

## 10. Shadowing và xung đột tên

Shadowing xảy ra khi một scope con khai báo tên trùng với tên ở scope cha. Trong scope con, tên gần nhất thường che khuất tên bên ngoài.

~~~text
let mode = "production"

rule "test" {
    let mode = "debug"
    use mode
}

use mode
~~~

Nếu DSL cho phép shadowing:

- mode trong rule test liên kết đến khai báo debug.
- mode bên ngoài rule liên kết đến khai báo production.

### 10.1. Khi nào cho phép shadowing?

Cho phép shadowing giúp scope con dùng tên tự nhiên mà không cần đặt tên dài. Tuy nhiên, nó cũng có thể khiến người đọc khó nhận ra tham chiếu đang dùng giá trị nào.

DSL có thể chọn:

- Cho phép shadowing ở mọi scope.
- Chỉ cho phép shadowing giữa một số loại khai báo.
- Cảnh báo khi tên bị che khuất.
- Cấm khai báo trùng tên trong scope lồng nhau.

Chính sách phải nhất quán và được thể hiện trong thông báo lỗi hoặc cảnh báo.

### 10.2. Khai báo trùng trong cùng scope

Hai khai báo cùng tên trong cùng scope có thể là lỗi:

~~~text
let limit = 10
let limit = 20
~~~

Nếu DSL không hỗ trợ khai báo lại, resolver báo duplicate declaration. Nếu hỗ trợ cập nhật biến, cần phân biệt khai báo mới với phép gán:

~~~text
let limit = 10
limit = 20
~~~

Khai báo tạo symbol; phép gán tham chiếu đến symbol đã tồn tại. Không nên xử lý cả hai như cùng một thao tác.

### 10.3. Ambiguous reference

Một tham chiếu mơ hồ xảy ra khi có nhiều symbol cùng phù hợp mà quy tắc phân giải không chọn được duy nhất:

~~~text
import billing.*
import shipping.*

calculateTax(100)
~~~

Nếu cả hai module export calculateTax với chữ ký phù hợp và DSL không có quy tắc ưu tiên, công cụ phải báo ambiguous reference. Người viết có thể sửa bằng tên đủ điều kiện:

~~~text
billing.calculateTax(100)
~~~

Không nên âm thầm chọn symbol được import trước hoặc sau nếu kết quả phụ thuộc thứ tự file và không được đặc tả.

## 11. Overload và liên kết lời gọi hàm

Một số DSL cho phép nhiều hàm cùng tên nhưng khác chữ ký (overloading). Khi đó, việc liên kết không chỉ dựa trên tên mà còn cần kiểu của các đối số và ngữ cảnh mong đợi.

Ví dụ:

~~~text
function format(value: Date) { ... }
function format(value: Decimal) { ... }

format(orderDate)
format(totalAmount)
~~~

Resolver hoặc overload resolver thực hiện các bước:

1. Tìm tập hàm có tên format trong namespace phù hợp.
2. Xác định kiểu của từng đối số.
3. Loại bỏ chữ ký không nhận được kiểu đối số.
4. Áp dụng quy tắc chuyển đổi kiểu hoặc generic nếu DSL hỗ trợ.
5. Chọn ứng viên phù hợp nhất hoặc báo lỗi nếu không có ứng viên duy nhất.

### 11.1. Không tìm thấy overload phù hợp

Nếu không hàm nào nhận kiểu đối số, công cụ báo lỗi no applicable overload và có thể liệt kê chữ ký được hỗ trợ.

### 11.2. Nhiều overload cùng phù hợp

Nếu nhiều chữ ký có độ ưu tiên ngang nhau, lời gọi mơ hồ. DSL cần định nghĩa quy tắc chọn overload, ví dụ ưu tiên kiểu chính xác hơn chuyển đổi widening, hoặc yêu cầu người dùng ép kiểu tường minh.

### 11.3. Generic và suy luận kiểu

Với hàm generic, resolver có thể cần suy luận tham số kiểu từ đối số và kiểu kết quả mong đợi. Nếu DSL có generic, quy tắc suy luận phải xác định rõ trường hợp không suy ra được kiểu hoặc có nhiều nghiệm.

Không nên để overload resolution phụ thuộc vào thứ tự đăng ký hàm nếu điều đó không được quy định. Tính xác định giúp kết quả biên dịch ổn định giữa các môi trường.

## 12. Liên kết tham chiếu đến trường và schema dữ liệu

Trong DSL truy vấn hoặc xử lý dữ liệu, tên trường thường được phân giải dựa trên schema của nguồn:

~~~text
source orders as o
filter o.status == "PAID"
aggregate total = sum(o.amount)
~~~

Resolver cần biết alias o đại diện cho nguồn orders. Sau đó member resolver kiểm tra status và amount có tồn tại trong schema của orders hay không.

### 12.1. Alias nguồn

Alias tạo tên ngắn cho một nguồn hoặc quan hệ:

~~~text
source customers as c
source orders as o

join c and o on c.id == o.customer_id
~~~

Trong biểu thức c.id, c phải liên kết đến alias nguồn customers; id được tìm trong schema tương ứng. Nếu hai nguồn đều có trường id, tiền tố alias giúp phân biệt.

### 12.2. Trường không xác định

Nếu viết:

~~~text
filter customer_status == "ACTIVE"
~~~

nhưng schema không có customer_status, resolver báo unknown field. Chẩn đoán hữu ích có thể nêu nguồn đang được tham chiếu và các tên gần giống nếu việc gợi ý là đáng tin cậy.

### 12.3. Trường trùng tên

Khi join hai nguồn có cùng tên trường, DSL có thể yêu cầu qualified field:

~~~text
filter c.id == o.customer_id
~~~

Nếu DSL cho phép dùng id không có alias, cần quy định cách xử lý khi nhiều nguồn cùng có trường đó. Báo ambiguous field thường an toàn hơn việc chọn tùy tiện một nguồn.

### 12.4. Schema động

Một số nguồn chỉ cung cấp schema tại runtime. Khi đó, resolver có thể liên kết tên trường ở mức biểu tượng tạm thời hoặc trì hoãn kiểm tra đến lúc đọc nguồn. Thông báo lỗi cần phân biệt tên chưa thể xác minh tĩnh với tên đã được xác nhận.

Nếu schema thay đổi theo thời gian, kết quả liên kết có thể cần gắn với phiên bản schema hoặc metadata của nguồn để lần chạy có thể tái lập.

## 13. Liên kết tham chiếu trong AST và IR

Sau khi resolve, công cụ cần lưu kết quả theo cách ổn định và dễ dùng.

### 13.1. Gắn symbol trực tiếp vào nút tham chiếu

Một cách là nút tham chiếu giữ symbol:

~~~text
NameReference
    name = "taxRate"
    symbolId = 205
~~~

Ưu điểm là visitor có thể truy cập symbol ngay từ nút. Hạn chế là AST có thể trở nên mutable hoặc phụ thuộc vào symbol table của compilation hiện tại.

### 13.2. Dùng bảng liên kết riêng

Một cách khác là giữ AST gần như bất biến và lưu liên kết bên ngoài:

~~~text
ReferenceBindingTable
    node-42 -> symbol-205
    node-57 -> symbol-205
    node-61 -> symbol-310
~~~

Cách này tách cú pháp khỏi kết quả phân tích. Nó hữu ích khi một AST nguồn cần được dùng bởi nhiều cấu hình hoặc môi trường khác nhau.

### 13.3. Chuyển tham chiếu thành symbol reference trong IR

IR có thể thay tên văn bản bằng symbol ID hoặc slot đã xác định:

~~~text
LoadSymbol(symbol-205)
Multiply
    LoadField("subtotal")
    LoadConstant(0.08)
~~~

Khi đó runtime không phải tra tên lại theo chuỗi ở mọi lần thực thi. Việc dùng symbol ID hoặc slot cũng giúp phân biệt các biến cùng tên ở những scope khác nhau.

### 13.4. Bảo toàn thông tin nguồn

Dù dùng symbol ID trong IR, công cụ vẫn nên giữ source span hoặc source map để báo lỗi và hỗ trợ gỡ lỗi. Một lỗi xảy ra khi đọc symbol-205 cần được ánh xạ về tham chiếu trong file DSL mà người dùng đã viết.

## 14. Liên kết tham chiếu và thực thi

Khi chương trình đã được phân giải, runtime có thể truy cập symbol theo cơ chế phù hợp:

- Biến local được ánh xạ vào slot trong activation frame.
- Biến môi trường được lưu trong environment object.
- Hàm được liên kết đến implementation hoặc function handle.
- Trường dữ liệu được ánh xạ đến cột hoặc vị trí trong record.
- Resource name được liên kết đến handle đã được kiểm tra quyền.

Ví dụ:

~~~text
let threshold = 100
filter amount > threshold
~~~

Sau binding, tham chiếu threshold có thể trỏ đến slot 0 trong frame hiện tại. Khi interpreter chạy biểu thức, nó đọc giá trị từ slot thay vì tìm chuỗi threshold trong một map tổng quát.

Tuy nhiên, không phải mọi tham chiếu đều được cố định hoàn toàn khi biên dịch. DSL hỗ trợ dynamic plugin, biến môi trường hoặc schema runtime có thể cần một bước lookup lúc chạy. Trường hợp này nên được xác định rõ và có chính sách lỗi riêng.

### 14.1. Static binding

Static binding xác định đích tham chiếu trước khi thực thi. Lợi ích:

- Phát hiện tên không tồn tại sớm.
- Hỗ trợ kiểm tra kiểu và quyền tĩnh.
- Giảm tra cứu chuỗi trong runtime.
- Tạo kế hoạch thực thi ổn định và dễ phân tích.

### 14.2. Dynamic lookup

Dynamic lookup tìm đích tham chiếu tại thời điểm chạy. Nó có thể cần thiết khi tên phụ thuộc dữ liệu, plugin được nạp muộn hoặc môi trường thực thi. Đổi lại, lỗi có thể chỉ xuất hiện khi thao tác được thực hiện và kết quả có thể phụ thuộc cấu hình runtime.

Nếu dùng dynamic lookup, nên giới hạn namespace và quyền truy cập. Không nên để một chuỗi do dữ liệu người dùng cung cấp tự do truy cập mọi hàm hoặc tài nguyên trong engine.

## 15. Liên kết tham chiếu, quyền truy cập và an toàn

Việc tìm thấy symbol không đồng nghĩa người dùng được phép sử dụng nó. Resolver có thể xác định tên, nhưng bước kiểm tra visibility hoặc authorization phải xác nhận quyền phù hợp.

Ví dụ:

~~~text
import finance.internal.calculatePayroll
~~~

Module có thể tồn tại và export một symbol, nhưng người dùng hiện tại không có quyền gọi nó. Công cụ cần phân biệt:

- Không tìm thấy module hoặc symbol.
- Symbol tồn tại nhưng không được export.
- Symbol được export nhưng caller không có quyền.
- Symbol được phép dùng nhưng tham số hoặc ngữ cảnh không hợp lệ.

Quyền có thể được kiểm tra tĩnh dựa trên vai trò đã biết, hoặc kiểm tra tại runtime nếu phụ thuộc danh tính phiên chạy và chính sách động.

Đặc biệt với DSL cho phép gọi hàm hoặc truy cập tài nguyên, không nên coi name resolution là một cơ chế bảo mật. Việc liên kết tên phải đi kèm kiểm tra quyền ở ranh giới thực thi, vì quyền có thể thay đổi sau khi chương trình được biên dịch.

## 16. Thông báo lỗi khi liên kết tham chiếu thất bại

Các lỗi liên kết thường gặp:

| Loại lỗi | Tình huống | Chẩn đoán phù hợp |
|---|---|---|
| Unresolved reference | Không tìm thấy tên trong các scope | Tên chưa được khai báo hoặc chưa được import |
| Duplicate declaration | Hai khai báo cùng tên trong một scope không cho phép | Chỉ rõ cả vị trí khai báo đầu và khai báo trùng |
| Ambiguous reference | Nhiều symbol cùng phù hợp | Liệt kê các ứng viên và yêu cầu tên đủ điều kiện |
| Wrong symbol kind | Dùng biến như hàm hoặc kiểu như giá trị | Nêu loại symbol thực tế và loại mong đợi |
| Inaccessible symbol | Symbol tồn tại nhưng không được phép truy cập | Nêu quy tắc visibility hoặc quyền bị vi phạm |
| Unknown member | Thành viên không tồn tại trên kiểu hoặc schema | Chỉ rõ receiver và thành viên không tìm thấy |
| Invalid overload | Không có hoặc có nhiều overload phù hợp | Hiển thị chữ ký và kiểu đối số liên quan |
| Import cycle | Các module tạo phụ thuộc vòng không được phép | Hiển thị chu trình module |

### 16.1. Ví dụ unresolved reference

~~~text
rule "report" {
    output totalAmount
}
~~~

Nếu không có khai báo totalAmount trong scope có thể nhìn thấy, công cụ có thể báo:

~~~text
report.dsl:2:12: error DSL-NAME-001
Không tìm thấy tên "totalAmount" trong phạm vi hiện tại.
Hãy kiểm tra khai báo hoặc import tương ứng.
~~~

### 16.2. Ví dụ ambiguous reference

~~~text
import billing.*
import shipping.*

calculateTax(100)
~~~

Thông báo nên nêu hai ứng viên billing.calculateTax và shipping.calculateTax, sau đó gợi ý dùng tên đủ điều kiện hoặc alias.

### 16.3. Gợi ý tên gần giống

Một resolver có thể đề xuất tên gần giống nếu khoảng cách ký tự nhỏ và namespace đủ rõ. Ví dụ viết cusotmerId có thể được gợi ý customerId. Gợi ý chỉ là trợ giúp; không được tự động liên kết sang một tên khác nếu việc đó có thể thay đổi ý nghĩa.

## 17. Triển khai name resolver trong Java

Một triển khai đơn giản có thể dùng lớp Scope chứa bảng symbol và tham chiếu đến scope cha.

~~~java
final class Symbol {
    private final String name;
    private final SymbolKind kind;
    private final Object type;

    Symbol(String name, SymbolKind kind, Object type) {
        this.name = name;
        this.kind = kind;
        this.type = type;
    }

    String name() {
        return name;
    }

    SymbolKind kind() {
        return kind;
    }

    Object type() {
        return type;
    }
}

enum SymbolKind {
    VARIABLE,
    FUNCTION,
    TYPE,
    RULE
}
~~~

Scope:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class Scope {
    private final Scope parent;
    private final Map<String, Symbol> symbols = new HashMap<>();

    Scope(Scope parent) {
        this.parent = parent;
    }

    boolean declare(Symbol symbol) {
        if (symbols.containsKey(symbol.name())) {
            return false;
        }
        symbols.put(symbol.name(), symbol);
        return true;
    }

    Optional<Symbol> resolve(String name) {
        Symbol local = symbols.get(name);
        if (local != null) {
            return Optional.of(local);
        }
        return parent == null
            ? Optional.empty()
            : parent.resolve(name);
    }
}
~~~

Trong ví dụ này, declare từ chối khai báo trùng trong cùng scope. resolve tra scope hiện tại trước rồi đi lên scope cha, do đó hỗ trợ shadowing theo lexical scope. Đây là nền tảng minh họa; triển khai thực tế cần thêm source location, namespace, visibility, overload, import và chẩn đoán.

### 17.1. Gắn kết quả vào AST

Sau khi resolve, một nút tham chiếu có thể giữ symbol:

~~~java
final class NameReference {
    private final String name;
    private Symbol resolvedSymbol;

    NameReference(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void bind(Symbol symbol) {
        this.resolvedSymbol = symbol;
    }

    Symbol resolvedSymbol() {
        return resolvedSymbol;
    }
}
~~~

Trong compiler lớn, có thể ưu tiên AST bất biến và lưu binding trong một bảng riêng thay vì sửa trực tiếp node. Nếu dùng cách mutable, cần bảo đảm mỗi tham chiếu chỉ được bind một lần trong một phiên phân tích và không tái sử dụng AST đã bind cho môi trường khác mà không làm mới kết quả.

### 17.2. Phân biệt khai báo trùng với shadowing

Khi thêm symbol, resolver cần biết scope hiện tại và scope cha. Nếu tên đã tồn tại trong scope hiện tại, đó có thể là duplicate declaration. Nếu tên chỉ tồn tại trong scope cha, DSL có thể cho phép hoặc cấm shadowing theo chính sách.

Không nên dùng một lệnh put đơn giản rồi ghi đè symbol cũ mà không kiểm tra. Làm như vậy sẽ mất thông tin về khai báo trước và khiến chẩn đoán duplicate hoặc shadowing không chính xác.

## 18. Phân giải gia tăng và thay đổi chương trình

Trong IDE hoặc môi trường chỉnh sửa trực tiếp, người dùng có thể thay đổi một phần DSL liên tục. Phân tích lại toàn bộ dự án sau mỗi ký tự có thể tốn kém. Incremental name resolution cập nhật các liên kết bị ảnh hưởng bởi thay đổi.

Ví dụ, nếu người dùng đổi tên biến discount thành rebate, công cụ cần:

1. Cập nhật symbol của khai báo.
2. Tìm các tham chiếu đang liên kết đến symbol đó.
3. Cập nhật hoặc đánh dấu các tham chiếu cần resolve lại.
4. Báo lỗi ở những vị trí còn dùng tên cũ.
5. Cập nhật gợi ý hoàn thành và điều hướng trong IDE.

### 18.1. Symbol ID ổn định

Nếu mỗi lần parse lại tạo ID hoàn toàn mới cho mọi symbol, các công cụ IDE khó giữ trạng thái như selection, diagnostics hoặc cache. Một hệ thống có thể duy trì ID ổn định qua các lần chỉnh sửa khi khai báo vẫn được nhận diện là cùng một thành phần.

Tuy nhiên, ID ổn định cần được quản lý cẩn thận khi di chuyển hoặc sao chép khai báo. Hai khai báo mới không được vô tình dùng chung ID.

### 18.2. Cache kết quả phân giải

Resolver có thể cache kết quả cho tham chiếu dựa trên:

- Node ID hoặc source span.
- Scope ID.
- Phiên bản symbol table.
- Phiên bản module và import.
- Schema hoặc metadata môi trường.

Khi một khai báo hoặc import thay đổi, cache phụ thuộc vào nó cần được vô hiệu hóa. Nếu không, tham chiếu có thể tiếp tục trỏ đến symbol đã lỗi thời.

### 18.3. Rename refactoring

Một tính năng rename an toàn nên dựa trên symbol binding. Khi đổi tên khai báo, công cụ chỉ cập nhật các tham chiếu liên kết đến symbol đó. Nó không nên thay mọi chuỗi có cùng ký tự, vì một chuỗi có thể là tên ở scope khác, tên trường độc lập hoặc nội dung literal.

## 19. Quy trình liên kết tham chiếu tổng quát

Một quy trình có thể áp dụng cho DSL có scope và module:

1. **Tạo cấu trúc AST.** Giữ riêng nút khai báo và nút tham chiếu tên.
2. **Tạo namespace và scope.** Xác định phạm vi cấp chương trình, module, rule, hàm và block.
3. **Đăng ký khai báo.** Tạo symbol và phát hiện khai báo trùng trong cùng scope.
4. **Xử lý import và export.** Xác định symbol nào được đưa vào module hiện tại và symbol nào có thể truy cập.
5. **Phân giải tên đơn.** Tra cứu theo thứ tự scope và namespace đã định nghĩa.
6. **Phân giải tên đủ điều kiện.** Đi qua các namespace hoặc thành viên theo từng thành phần.
7. **Chọn overload.** Nếu tên tham chiếu đến nhóm hàm, dùng kiểu đối số và quy tắc overload để chọn một symbol.
8. **Kiểm tra visibility và loại symbol.** Xác nhận tham chiếu được phép và phù hợp với ngữ cảnh.
9. **Gắn binding.** Lưu symbol ID hoặc kết quả trong binding table.
10. **Báo lỗi và cảnh báo.** Xử lý unresolved, duplicate, ambiguous, inaccessible và shadowing.
11. **Chuyển sang phân tích kiểu hoặc IR.** Các giai đoạn sau dùng liên kết đã xác định.

Với DSL nhỏ, một số bước có thể gộp. Với DSL nhiều module hoặc có schema động, việc phân tách giúp quản lý phụ thuộc và tái phân tích tốt hơn.

## 20. Những quyết định thiết kế cần ghi rõ

Khi đặc tả liên kết tham chiếu, nhóm thiết kế DSL cần trả lời:

- Tên có phân biệt hoa thường không?
- Những loại khai báo nào dùng chung namespace?
- Scope nào được tạo bởi block, function, rule hoặc module?
- Tra cứu tên đi từ scope trong ra ngoài theo thứ tự nào?
- Shadowing có được phép không?
- Khai báo có thể xuất hiện sau tham chiếu không?
- Có hỗ trợ import wildcard, import chọn lọc và alias không?
- Có hỗ trợ qualified name và namespace lồng nhau không?
- Hàm có overload hoặc generic không?
- Trường dữ liệu được resolve từ schema tĩnh hay schema runtime?
- Symbol có visibility hoặc quyền truy cập không?
- Binding được lưu trực tiếp trong AST hay trong bảng riêng?
- Khi module hoặc schema thay đổi, kết quả binding được cập nhật thế nào?
- Runtime có cho phép dynamic lookup không và trong phạm vi nào?

Những quy tắc này là một phần của ngữ nghĩa ngôn ngữ. Nếu không được đặc tả, cùng một chương trình có thể được các công cụ khác nhau hiểu theo cách khác nhau.

## 21. Những sai lầm thường gặp

### 21.1. Chỉ so sánh chuỗi tên

Hai tên giống nhau không nhất thiết là cùng một symbol. Scope, namespace và vị trí khai báo quyết định mối liên hệ. Dùng chuỗi làm định danh duy nhất sẽ gây lỗi khi có shadowing hoặc module.

### 21.2. Gộp khai báo và tham chiếu

Khai báo tạo symbol; tham chiếu sử dụng symbol. Nếu không phân biệt hai vai trò, compiler khó kiểm tra khai báo trùng, tìm tất cả nơi sử dụng và thực hiện rename an toàn.

### 21.3. Không định nghĩa thứ tự tra cứu

Nếu không rõ local, parent, import và built-in được ưu tiên ra sao, resolver có thể chọn kết quả khác nhau. Cần quy định thứ tự và không dựa vào thứ tự duyệt file ngẫu nhiên.

### 21.4. Cho phép shadowing mà không cảnh báo

Shadowing có thể hợp lệ nhưng cũng dễ làm người đọc nhầm giá trị. Cân nhắc cảnh báo hoặc yêu cầu tên đủ rõ ở những miền nhạy cảm.

### 21.5. Tự chọn một tham chiếu mơ hồ

Chọn symbol đầu tiên tìm thấy có thể làm chương trình phụ thuộc thứ tự import. Khi không có quy tắc ưu tiên rõ ràng, phải báo ambiguous reference.

### 21.6. Coi import là bản sao khai báo

Import nên tạo khả năng truy cập đến symbol gốc hoặc alias của nó. Tạo một symbol độc lập không có liên kết đến khai báo gốc có thể làm sai điều hướng, quyền và metadata.

### 21.7. Bỏ qua quyền truy cập

Resolve thành công không có nghĩa thao tác được phép. Visibility và authorization cần được kiểm tra theo chính sách của DSL và môi trường thực thi.

### 21.8. Không cập nhật binding sau chỉnh sửa

IDE hoặc compiler gia tăng có thể giữ binding cũ sau khi khai báo, import hoặc schema thay đổi. Cần version hóa scope và vô hiệu hóa cache phụ thuộc.

## 22. Câu hỏi tự kiểm tra

1. Liên kết tham chiếu là gì? Phân biệt khai báo, tham chiếu và symbol.
2. Vì sao hai tên giống nhau có thể liên kết đến hai symbol khác nhau?
3. Mô tả cách resolver tìm một tên trong lexical scope.
4. Phân biệt lexical scope và dynamic scope.
5. Qualified name và namespace giúp giải quyết xung đột tên như thế nào?
6. Import chọn lọc, import wildcard và alias import khác nhau ra sao?
7. Khi nào cần phân giải nhiều lượt thay vì một lượt?
8. Shadowing khác duplicate declaration như thế nào?
9. Vì sao overload resolution cần xét kiểu đối số ngoài tên hàm?
10. Trong DSL truy vấn, tên trường được liên kết với schema và alias nguồn như thế nào?
11. So sánh việc gắn symbol trực tiếp vào AST với lưu binding trong bảng riêng.
12. Vì sao rename refactoring cần dựa trên symbol binding thay vì thay thế chuỗi?
13. Hãy đề xuất quy tắc phân giải tên cho DSL có module, biến cục bộ, hàm built-in và import.
14. Nêu các loại lỗi cần báo khi một tham chiếu không thể liên kết duy nhất.

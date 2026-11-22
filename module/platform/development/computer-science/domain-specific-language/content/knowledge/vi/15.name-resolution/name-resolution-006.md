# Tham chiếu trước khai báo

Trong một **Domain-Specific Language (DSL)**, người viết thường cần tham chiếu đến biến, hàm, tài nguyên, bước quy trình hoặc kiểu dữ liệu được khai báo ở một vị trí khác trong chương trình. Có trường hợp phần sử dụng xuất hiện trước phần khai báo. Hiện tượng này được gọi là **tham chiếu trước khai báo (forward reference)**.

Ví dụ, một pipeline có thể khai báo bước kiểm thử trước bước biên dịch mà nó phụ thuộc:

~~~text
pipeline "build" {
    step test {
        command "gradle test"
        after compile
    }

    step compile {
        command "gradle build"
    }
}
~~~

Ở đây, tên compile được sử dụng trước khi bước compile xuất hiện. DSL cần có quy tắc xác định tham chiếu này có hợp lệ hay không, cách tìm khai báo tương ứng và thời điểm kiểm tra. Nếu ngôn ngữ chỉ cho phép dùng tên đã khai báo trước đó, chương trình trên sẽ bị từ chối. Nếu ngôn ngữ hỗ trợ forward reference, bộ phân giải tên có thể tìm thấy khai báo compile ở phần sau của cùng pipeline.

Tham chiếu trước khai báo là một vấn đề của **phân giải tên (name resolution)** và thứ tự xử lý chương trình. Nó không chỉ là chi tiết cú pháp. Quy tắc này ảnh hưởng đến phạm vi tên, khả năng khai báo đệ quy, cách tổ chức parser, thiết kế symbol table, xử lý phụ thuộc và chất lượng thông báo lỗi.

## 1. Tham chiếu trước khai báo là gì?

Một tham chiếu là việc sử dụng tên để chỉ đến một thực thể đã được định nghĩa hoặc khai báo trong chương trình. Tham chiếu có thể xuất hiện trong biểu thức, lời gọi hàm, kiểu dữ liệu, cấu hình, quan hệ phụ thuộc hoặc một khai báo khác.

Ví dụ:

~~~text
let total = unitPrice * quantity
let quantity = 3
let unitPrice = 120000
~~~

Các tên unitPrice và quantity được tham chiếu trong khai báo total trước khi hai tên đó được khai báo. Nếu DSL cho phép tra cứu tên trong toàn bộ phạm vi hiện tại, chương trình có thể hợp lệ. Nếu DSL yêu cầu khai báo trước khi sử dụng, chương trình phải được viết lại theo thứ tự:

~~~text
let quantity = 3
let unitPrice = 120000
let total = unitPrice * quantity
~~~

Tham chiếu trước khai báo có thể áp dụng cho nhiều loại tên:

- Biến hoặc hằng số.
- Hàm hoặc thủ tục.
- Kiểu dữ liệu, interface hoặc schema.
- Tài nguyên và thành phần cấu hình.
- Bước workflow và quan hệ phụ thuộc.
- Rule, event handler hoặc tác vụ được gọi từ một khai báo khác.
- Module, package hoặc định danh được import.

Không phải mọi loại tên đều cần cùng một chính sách. DSL có thể cho phép tham chiếu trước đối với tên bước trong pipeline nhưng vẫn yêu cầu biến cục bộ phải được khai báo trước khi dùng.

## 2. Phân biệt khai báo, định nghĩa và sử dụng

Để hiểu forward reference, cần phân biệt ba hoạt động:

- **Khai báo (declaration)** giới thiệu tên và thông tin về thực thể, chẳng hạn tên hàm cùng kiểu tham số và kiểu trả về.
- **Định nghĩa (definition)** cung cấp nội dung hoặc hành vi cụ thể của thực thể, chẳng hạn thân hàm hoặc giá trị khởi tạo.
- **Sử dụng (use/reference)** dùng tên đã được giới thiệu để gọi, đọc, ghi hoặc liên kết với thực thể đó.

Một số ngôn ngữ tách khai báo và định nghĩa thành hai bước. Khi đó, có thể khai báo chữ ký hàm trước rồi định nghĩa thân hàm ở vị trí sau:

~~~text
declare function calculateTotal(items: List<Item>): Decimal

function calculateTotal(items: List<Item>): Decimal {
    return sum(items.price)
}
~~~

Khai báo ban đầu giúp bộ phân giải biết tên calculateTotal và hợp đồng kiểu của nó. Định nghĩa phía sau cung cấp phần triển khai. Một tham chiếu đến hàm có thể được kiểm tra kiểu ngay cả khi thân hàm chưa được đọc.

Trong DSL khác, declaration và definition có thể là cùng một cấu trúc. Ví dụ, khai báo một hằng số đồng thời cung cấp giá trị:

~~~text
let taxRate = 0.1
~~~

Khi thiết kế ngôn ngữ, cần xác định tham chiếu trước khai báo chỉ được phép khi tên đã có declaration, hay còn cho phép dùng tên trước cả declaration và definition. Hai chính sách này khác nhau về khả năng kiểm tra và cách triển khai.

## 3. Chính sách khai báo trước khi sử dụng

Một DSL có thể chọn một trong ba chính sách tổng quát.

### 3.1. Bắt buộc khai báo trước khi sử dụng

Với chính sách này, tên chỉ có hiệu lực từ vị trí khai báo trở đi trong phạm vi hiện tại.

~~~text
let count = 5
let next = count + 1
~~~

Đoạn trên hợp lệ. Đoạn sau không hợp lệ:

~~~text
let next = count + 1
let count = 5
~~~

Ưu điểm:

- Có thể phân giải tên theo thứ tự đọc từ trên xuống.
- Người đọc dễ xác định tên được giới thiệu ở đâu.
- Giảm một số phụ thuộc vòng và làm quy tắc khởi tạo đơn giản hơn.
- Parser hoặc semantic analyzer có thể báo lỗi ngay tại vị trí sử dụng.

Đánh đổi:

- Người viết phải sắp xếp khai báo theo thứ tự phụ thuộc.
- Một số cấu trúc tương hỗ hoặc mô hình đồ thị khó biểu diễn trực tiếp.
- Việc di chuyển một khai báo có thể làm nhiều tham chiếu trở nên không hợp lệ.

Chính sách này phù hợp với DSL cấu hình tuần tự, ngôn ngữ kịch bản đơn giản hoặc DSL muốn làm rõ thứ tự khai báo.

### 3.2. Cho phép tham chiếu trước khai báo

Với chính sách này, tên có thể được sử dụng trước vị trí khai báo nếu khai báo tương ứng tồn tại trong phạm vi được phép.

~~~text
let total = subtotal + tax
let tax = subtotal * taxRate
let subtotal = 100
let taxRate = 0.1
~~~

Bộ phân giải phải xem xét toàn bộ vùng khai báo liên quan hoặc có một cơ chế khai báo trước. Người viết có thể tổ chức chương trình theo nhóm khái niệm thay vì buộc thứ tự source trùng với thứ tự phụ thuộc.

Ưu điểm:

- Cho phép cấu trúc source theo cách tự nhiên với miền nghiệp vụ.
- Hỗ trợ các quan hệ tham chiếu lẫn nhau.
- Giảm yêu cầu sắp xếp thủ công theo thứ tự phụ thuộc.
- Hữu ích cho DSL mô tả đồ thị, schema, workflow hoặc rule.

Đánh đổi:

- Cần phân giải tên qua nhiều bước hoặc có bảng khai báo đầy đủ.
- Phải xác định rõ phạm vi và quy tắc trùng tên.
- Có thể tạo phụ thuộc vòng hoặc tham chiếu không hợp lệ chỉ phát hiện được sau khi thu thập khai báo.
- Người đọc cần công cụ hỗ trợ tìm đến vị trí định nghĩa.

### 3.3. Cho phép có điều kiện theo loại khai báo

DSL có thể kết hợp hai chính sách:

| Loại tên | Chính sách minh họa |
|---|---|
| Biến cục bộ trong block | Phải khai báo trước khi dùng |
| Hàm cấp module | Có thể tham chiếu trước |
| Kiểu dữ liệu | Có thể khai báo trước để hỗ trợ kiểu đệ quy |
| Bước workflow | Có thể tham chiếu trước trong cùng pipeline |
| Tài nguyên bên ngoài | Phải được import hoặc khai báo trong phạm vi |
| Biến môi trường | Phải được khai báo trong schema hoặc cung cấp bởi runtime |

Chính sách hỗn hợp có thể phản ánh đúng bản chất miền, nhưng cần được tài liệu hóa rõ ràng. Nếu hai cấu trúc trông giống nhau nhưng tuân theo quy tắc khác nhau, diagnostics và IDE nên giúp người viết nhận ra khác biệt.

## 4. Phân giải tên khi có forward reference

Để xử lý tham chiếu trước khai báo, compiler hoặc interpreter cần biết tên đang tham chiếu tới thực thể nào. Một quy trình phổ biến gồm:

1. Đọc cấu trúc source và tạo AST.
2. Thu thập các khai báo trong phạm vi cần thiết.
3. Tạo symbol table chứa tên, loại symbol, kiểu và vị trí khai báo.
4. Duyệt các node có tham chiếu và tìm symbol phù hợp.
5. Kiểm tra phạm vi, quyền truy cập, loại symbol và tính tương thích kiểu.
6. Ghi liên kết từ node tham chiếu tới symbol hoặc node định nghĩa.
7. Báo lỗi cho tên không tồn tại, mơ hồ hoặc không được phép tham chiếu ở vị trí đó.

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    A[Source DSL] --> B[Parser]
    B --> C[AST]
    C --> D[Thu thập khai báo]
    D --> E[Symbol table]
    C --> F[Thu thập tham chiếu]
    E --> G[Name resolution]
    F --> G
    G --> H{Tìm thấy đúng symbol?}
    H -->|Có| I[Liên kết tham chiếu]
    H -->|Không| J[Diagnostic]
    I --> K[Type checking và semantic analysis]
~~~

Ví dụ, với pipeline:

~~~text
pipeline "build" {
    step test {
        after compile
    }

    step compile {
        command "gradle build"
    }
}
~~~

Ở bước thu thập khai báo, bộ phân giải thêm test và compile vào symbol table. Khi xử lý quan hệ after compile, tên compile đã có trong bảng nên tham chiếu được liên kết tới symbol của bước compile.

## 5. Symbol table và thông tin khai báo

**Symbol table** là cấu trúc dữ liệu lưu thông tin về tên được khai báo trong chương trình. Một mục symbol thường có:

- Tên định danh.
- Loại symbol: biến, hàm, kiểu, tài nguyên, bước hoặc rule.
- Kiểu dữ liệu hoặc chữ ký nếu có.
- Phạm vi chứa symbol.
- Vị trí khai báo trong source.
- Trạng thái khai báo và định nghĩa.
- Liên kết tới AST node hoặc mô hình miền tương ứng.
- Thông tin visibility, module hoặc namespace.

Ví dụ bảng symbol cho pipeline:

| Tên | Loại | Phạm vi | Vị trí khai báo | Trạng thái |
|---|---|---|---|---|
| build | Step | pipeline build | dòng 7 | Đã định nghĩa |
| test | Step | pipeline build | dòng 2 | Đã định nghĩa |
| package | Step | pipeline build | dòng 11 | Đã định nghĩa |

Khi gặp tham chiếu compile, bộ phân giải tìm symbol có tên compile trong phạm vi pipeline build. Nếu không có, nó có thể tìm ở phạm vi cha theo quy tắc lexical scope hoặc báo lỗi nếu tên bước chỉ được tra cứu trong pipeline hiện tại.

### 5.1. Phân biệt symbol với giá trị runtime

Symbol table dùng trong phân tích ngữ nghĩa không nhất thiết chứa giá trị runtime. Ví dụ, khi khai báo:

~~~text
let price: Decimal = loadPrice()
~~~

Symbol table có thể ghi nhận price có kiểu Decimal và vị trí khai báo, dù giá trị thực tế chỉ được tính khi chạy. Việc phân giải tên xác định symbol; việc đánh giá biểu thức mới xác định giá trị.

Phân biệt hai lớp này giúp xử lý forward reference mà không cần thực thi chương trình trong lúc phân tích tên.

## 6. Phân giải một lượt và nhiều lượt

### 6.1. Phân giải một lượt

Với DSL yêu cầu khai báo trước khi sử dụng, compiler có thể duyệt source từ trên xuống. Khi gặp khai báo, nó thêm symbol vào bảng; khi gặp tham chiếu, nó tra cứu ngay.

Mã giả:

~~~text
symbols = new SymbolTable()

for declaration in sourceOrder:
    registerDeclaration(declaration, symbols)

    for reference in referencesOf(declaration):
        resolveUsingVisibleSymbols(reference, symbols)
~~~

Cách triển khai cụ thể có thể đăng ký khai báo trước khi xử lý phần thân của chính khai báo đó. Điểm cốt yếu là một tham chiếu chỉ nhìn thấy những symbol đã được đưa vào phạm vi theo quy tắc thứ tự.

Ưu điểm là đơn giản và có thể phát hiện lỗi sớm. Hạn chế là không tự nhiên với forward reference và quan hệ tương hỗ.

### 6.2. Phân giải nhiều lượt (multi-pass)

Với forward reference, một cách phổ biến là chia xử lý thành nhiều lượt:

**Lượt 1 — Thu thập khai báo:** duyệt phạm vi và đăng ký tên, loại symbol, chữ ký hoặc kiểu sơ bộ.

**Lượt 2 — Phân giải tham chiếu:** duyệt AST, tra cứu từng tên trong symbol table và tạo liên kết.

**Lượt 3 — Kiểm tra ngữ nghĩa:** kiểm tra kiểu, số lượng tham số, quy tắc miền, tính hợp lệ của dependency và các ràng buộc khác.

Ví dụ mã giả:

~~~text
symbols = new SymbolTable()

for declaration in allDeclarations:
    symbols.declare(
        name = declaration.name,
        kind = declaration.kind,
        signature = declaration.signature,
        sourceSpan = declaration.span
    )

for reference in allReferences:
    symbol = symbols.lookup(reference.name, reference.scope)
    if symbol is missing:
        reportUndefinedName(reference)
    else:
        reference.bindTo(symbol)

for node in semanticNodes:
    validateSemantics(node)
~~~

Lượt đầu không nhất thiết phải biết toàn bộ kiểu cuối cùng. Với kiểu phụ thuộc lẫn nhau, compiler có thể cần tạo placeholder symbol rồi giải quyết kiểu sau. Số lượt xử lý phụ thuộc vào độ phức tạp của DSL.

### 6.3. So sánh

| Tiêu chí | Một lượt theo thứ tự source | Nhiều lượt |
|---|---|---|
| Forward reference | Thường không hỗ trợ trực tiếp | Hỗ trợ thuận tiện |
| Cấu trúc triển khai | Đơn giản hơn | Có thêm giai đoạn và trạng thái |
| Phát hiện lỗi | Có thể báo ngay | Một số lỗi được báo sau khi thu thập khai báo |
| Quan hệ tương hỗ | Khó biểu diễn | Có thể hỗ trợ qua placeholder và resolve |
| Phạm vi áp dụng | DSL tuần tự, quy tắc đơn giản | DSL có nhiều tham chiếu, module hoặc đồ thị |

## 7. Hoisting và forward declaration

Hai cơ chế thường được nhắc đến khi nói về tham chiếu trước khai báo là **hoisting** và **forward declaration**.

### 7.1. Hoisting

Hoisting là quy tắc ngôn ngữ theo đó một số khai báo được xem như có hiệu lực từ đầu phạm vi, dù vị trí viết trong source nằm phía dưới. Điều này có thể áp dụng cho khai báo hàm, kiểu hoặc một số loại biến tùy ngôn ngữ.

Ví dụ minh họa:

~~~text
runReport()

function runReport() {
    print "Report ready"
}
~~~

Nếu DSL hoist khai báo hàm trong module, lời gọi runReport ở đầu file có thể được phân giải tới hàm định nghĩa phía dưới.

Hoisting không có nghĩa mọi phần thân khai báo đều được thực thi sớm. Nó thường chỉ thay đổi thời điểm tên được đưa vào phạm vi hoặc cách compiler thu thập khai báo. Việc khởi tạo giá trị vẫn tuân theo quy tắc riêng.

### 7.2. Forward declaration

Forward declaration là khai báo tên và hợp đồng của một thực thể trước khi phần định nghĩa đầy đủ xuất hiện.

~~~text
declare function calculate(value: Decimal): Decimal

function run() {
    let result = calculate(10.5)
}

function calculate(value: Decimal): Decimal {
    return value * 1.1
}
~~~

Lời gọi calculate được kiểm tra dựa trên chữ ký đã khai báo. Khi compiler gặp definition, nó kiểm tra phần thân có khớp với chữ ký hay không.

Forward declaration có thể hữu ích khi:

- Hai hàm gọi lẫn nhau.
- Các module phụ thuộc vào interface của nhau.
- Một DSL cần tách hợp đồng khỏi phần triển khai.
- Một kiểu được tham chiếu trước khi các trường hoặc phương thức của nó được định nghĩa đầy đủ.

### 7.3. Phân biệt

| Cơ chế | Bản chất |
|---|---|
| Forward reference | Một vị trí sử dụng tên xuất hiện trước vị trí khai báo/định nghĩa |
| Hoisting | Quy tắc làm cho khai báo được xem là có hiệu lực sớm trong phạm vi |
| Forward declaration | Khai báo trước tên và hợp đồng, định nghĩa đầy đủ ở vị trí sau |

Hoisting là một chính sách của ngôn ngữ; forward declaration là một cấu trúc khai báo cụ thể; forward reference là tình huống sử dụng tên trước vị trí khai báo. Chúng có thể phối hợp nhưng không đồng nghĩa.

## 8. Tham chiếu trước khai báo trong phạm vi lồng nhau

Phân giải tên cần xét cả thứ tự khai báo và phạm vi (scope). Một tên được khai báo ở phạm vi nào không nhất thiết nhìn thấy ở mọi nơi.

Ví dụ:

~~~text
let rate = 0.1

scope {
    let total = subtotal * rate
    let subtotal = 100
}
~~~

Nếu DSL cho phép forward reference trong một block, subtotal được tìm thấy trong phạm vi scope đó. Tên rate được tìm ở phạm vi cha nếu lexical scoping cho phép tra cứu lên trên.

Nhưng tham chiếu từ bên ngoài vào một tên chỉ được khai báo trong block con thường không hợp lệ:

~~~text
scope {
    let internalLimit = 10
}

use internalLimit
~~~

Ngay cả khi DSL cho phép forward reference, điều đó không tự động mở rộng visibility ra ngoài phạm vi khai báo. Quy tắc thứ tự và quy tắc phạm vi là hai trục riêng:

- **Thứ tự** xác định tên có thể được dùng trước vị trí khai báo hay không.
- **Phạm vi** xác định vị trí nào có quyền nhìn thấy tên đó.

Một bộ phân giải cần áp dụng cả hai. Không được tìm thấy một symbol ở bất kỳ đâu trong file rồi coi mọi tham chiếu tới nó là hợp lệ.

## 9. Tham chiếu giữa các module và namespace

DSL lớn có thể chia chương trình thành module. Một module có thể tham chiếu đến kiểu, hàm hoặc tài nguyên được khai báo trong module khác.

Ví dụ:

~~~text
module billing {
    import customer.Customer

    function invoiceFor(customer: Customer): Invoice {
        ...
    }
}
~~~

Nếu module customer được xử lý sau billing, compiler vẫn có thể phân giải Customer nếu nó thu thập interface hoặc symbol export của các module trước khi kiểm tra thân chương trình.

Một quy trình thường gặp:

1. Xác định module và namespace.
2. Đọc import và export.
3. Thu thập symbol công khai của từng module.
4. Xây dựng môi trường tên cho module tiêu thụ.
5. Phân giải các tham chiếu trong thân module.
6. Kiểm tra visibility và quyền truy cập.

### 9.1. Tên đầy đủ và tên rút gọn

Nếu nhiều module export cùng tên Customer, tên rút gọn có thể mơ hồ. DSL cần quy định:

- Có bắt buộc dùng tên đầy đủ như customer.Customer không?
- Import có thể đổi alias không?
- Import hai symbol trùng tên có bị từ chối không?
- Thứ tự import có ảnh hưởng đến cách chọn tên không?

Ví dụ alias:

~~~text
import customer.Customer as Buyer
import crm.Customer as CRMCustomer
~~~

Tham chiếu trước khai báo không nên làm mất quy tắc namespace. Một tên chỉ được resolve trong tập symbol mà module hiện tại được phép nhìn thấy.

### 9.2. Chu trình phụ thuộc module

Nếu module A import B và B import A, hệ thống có một chu trình phụ thuộc. Điều này không nhất thiết luôn sai, nhưng cần được hỗ trợ rõ ràng. Có thể cho phép chu trình ở cấp interface nhưng cấm chu trình khi khởi tạo giá trị; hoặc yêu cầu tổ chức lại module để loại bỏ phụ thuộc vòng.

## 10. Hàm đệ quy và định nghĩa tương hỗ

Forward reference có vai trò quan trọng khi định nghĩa các hàm gọi lẫn nhau.

Ví dụ hai hàm kiểm tra số chẵn và lẻ:

~~~text
function isEven(n: Integer): Boolean {
    if n == 0 {
        return true
    }
    return isOdd(n - 1)
}

function isOdd(n: Integer): Boolean {
    if n == 0 {
        return false
    }
    return isEven(n - 1)
}
~~~

Trong thân isEven, tên isOdd xuất hiện trước định nghĩa của isOdd. Ngược lại, isOdd cũng tham chiếu tới isEven. Đây là **định nghĩa tương hỗ (mutual recursion)**.

Nếu DSL chỉ cho phép gọi hàm đã được định nghĩa trước, hai hàm này khó được viết trực tiếp theo cách trên. Có thể dùng forward declaration:

~~~text
declare function isEven(n: Integer): Boolean
declare function isOdd(n: Integer): Boolean

function isEven(n: Integer): Boolean {
    ...
}

function isOdd(n: Integer): Boolean {
    ...
}
~~~

Hoặc compiler có thể thu thập chữ ký của mọi hàm trong module trước khi kiểm tra thân hàm. Khi đó, cả hai tên đã tồn tại trong symbol table trước giai đoạn phân giải lời gọi.

Cho phép forward reference không có nghĩa mọi đệ quy đều hợp lệ. Compiler vẫn cần kiểm tra chữ ký, kiểu trả về, khả năng kết thúc nếu DSL yêu cầu và những giới hạn tài nguyên khi chạy.

## 11. Tham chiếu kiểu trước khai báo

Kiểu dữ liệu có thể tham chiếu lẫn nhau, đặc biệt trong mô hình cây, đồ thị hoặc quan hệ giữa các thực thể.

Ví dụ:

~~~text
type Employee {
    name: String
    manager: Employee?
    reports: List<Employee>
}
~~~

Employee tham chiếu chính nó. Đây là kiểu đệ quy. Một ví dụ tương hỗ:

~~~text
type Author {
    books: List<Book>
}

type Book {
    authors: List<Author>
}
~~~

Author tham chiếu Book trước khi Book được định nghĩa; Book tham chiếu lại Author. DSL cần cho phép các kiểu được khai báo trong cùng một nhóm trước khi kiểm tra đầy đủ các trường.

Một cách xử lý:

1. Đăng ký tên Author và Book dưới dạng type symbol chưa hoàn chỉnh.
2. Phân tích các trường và ghi lại type reference.
3. Resolve các tham chiếu tới symbol tương ứng.
4. Kiểm tra kiểu trường, nullability, generic và các ràng buộc.
5. Hoàn tất định nghĩa type.

Với một số DSL, kiểu đệ quy cần có điểm gián tiếp như reference hoặc collection. Nếu kiểu có kích thước giá trị trực tiếp vô hạn, hệ thống có thể cần từ chối hoặc yêu cầu một dạng tham chiếu gián tiếp.

## 12. Forward reference trong DSL cấu hình và workflow

Forward reference không chỉ xuất hiện trong ngôn ngữ lập trình tổng quát. Nó đặc biệt tự nhiên trong DSL mô tả quan hệ.

### 12.1. Quan hệ phụ thuộc trong pipeline

~~~text
pipeline "release" {
    step deploy {
        command "deploy.sh"
        after package
    }

    step package {
        command "build-package.sh"
        after test
    }

    step test {
        command "run-tests.sh"
        after compile
    }

    step compile {
        command "compile.sh"
    }
}
~~~

Các bước được viết theo nhóm hoặc theo mức quan trọng đối với người đọc. Bộ phân giải thu thập toàn bộ tên bước, sau đó liên kết dependency. Sau khi resolve, engine có thể tạo đồ thị:

~~~mermaid
flowchart LR
    A[compile] --> B[test]
    B --> C[package]
    C --> D[deploy]
~~~

Nếu package tham chiếu tới test không tồn tại, lỗi cần được báo tại tham chiếu after test. Nếu đồ thị có chu trình, đó là lỗi semantic khác với tên không tồn tại.

### 12.2. Tham chiếu tài nguyên

Một DSL hạ tầng có thể cho phép dịch vụ tham chiếu tới network được khai báo phía sau:

~~~text
service "orders" {
    network = "backend"
}

network "backend" {
    cidr = "10.20.0.0/16"
}
~~~

Nếu DSL hỗ trợ forward reference trong phạm vi file hoặc module, dịch vụ có thể liên kết tới network sau khi thu thập tài nguyên. Tuy nhiên, cần kiểm tra loại tài nguyên, visibility, tên duy nhất và các quy tắc phụ thuộc.

### 12.3. Tham chiếu biến môi trường

Một DSL cấu hình có thể tham chiếu biến được khai báo ở phần sau:

~~~text
service "api" {
    port = API_PORT
}

variable API_PORT: Integer = 8080
~~~

Quy tắc resolve có thể cho phép biến trong toàn bộ module hoặc chỉ cho phép biến đã khai báo trước. Nếu biến có thể được cung cấp từ môi trường bên ngoài, compiler cần phân biệt symbol nội bộ với symbol external và xác định lúc nào giá trị thực tế được cung cấp.

## 13. Phụ thuộc vòng và tham chiếu trước khai báo

Khi cho phép forward reference, chương trình có thể tạo ra đồ thị phụ thuộc. Một tham chiếu đơn lẻ không nhất thiết là vấn đề; điều cần xem xét là toàn bộ đồ thị có chu trình hay không.

Ví dụ:

~~~text
let a = b + 1
let b = c + 1
let c = 10
~~~

Đồ thị phụ thuộc là a -> b -> c. Nếu các khai báo là biểu thức thuần và có thể đánh giá theo thứ tự phụ thuộc, compiler có thể tính c trước, sau đó b và a.

Ví dụ chu trình:

~~~text
let a = b + 1
let b = a + 1
~~~

Ở đây a phụ thuộc b và b phụ thuộc a. Với khai báo giá trị thông thường, đây có thể là lỗi circular dependency hoặc uninitialized value. Tuy nhiên, trong ngôn ngữ hỗ trợ định nghĩa đệ quy hoặc lazy evaluation, chu trình có thể có ý nghĩa nếu được quy định cẩn thận.

### 13.1. Phân biệt tham chiếu vòng và đệ quy hợp lệ

Không phải mọi chu trình đều là lỗi:

- Hai hàm có thể gọi lẫn nhau và được hỗ trợ bằng mutual recursion.
- Hai kiểu có thể tham chiếu lẫn nhau thông qua reference hoặc collection.
- Hai giá trị khởi tạo eager có thể phụ thuộc vòng và không thể tính được.
- Hai module có thể có chu trình import nhưng vẫn hợp lệ nếu interface được xử lý trước.

Vì vậy, kiểm tra chu trình phải xét loại node và loại cạnh trong đồ thị. Một chu trình giữa function symbol không có cùng ý nghĩa với chu trình giữa eager value initializer.

### 13.2. Phát hiện chu trình trong đồ thị phụ thuộc

Với đồ thị phụ thuộc có hướng, có thể dùng DFS hoặc thuật toán sắp xếp tô-pô để phát hiện chu trình. Nếu đồ thị không có chu trình, thứ tự tô-pô cung cấp một thứ tự xử lý hợp lệ.

~~~text
dependencies = buildDependencyGraph(declarations)

if hasCycle(dependencies):
    reportCircularDependency(cyclePath)
else:
    order = topologicalSort(dependencies)
    evaluateDeclarations(order)
~~~

Thông báo tốt nên hiển thị đường đi của chu trình, ví dụ:

~~~text
Circular value dependency:
a -> b -> c -> a
~~~

Với đồ thị lớn, diagnostics có thể chỉ ra từng vị trí khai báo và tham chiếu tạo thành chu trình.

## 14. Khởi tạo giá trị và thời điểm đánh giá

Cho phép tham chiếu trước khai báo không tự quyết định khi nào biểu thức khởi tạo được tính. Cần phân biệt:

- **Thời điểm phân giải tên:** xác định tham chiếu trỏ tới symbol nào.
- **Thời điểm kiểm tra kiểu:** xác định biểu thức có tương thích với kiểu yêu cầu không.
- **Thời điểm đánh giá:** tính giá trị của biểu thức.
- **Thời điểm khởi tạo:** tạo trạng thái hoặc object thực tế trong runtime.

Ví dụ:

~~~text
let result = calculate(input)
let input = loadInput()
~~~

Compiler có thể resolve tên calculate và input nhờ thu thập khai báo trước. Nhưng nếu DSL dùng eager initialization theo thứ tự source, result vẫn có thể được đánh giá khi input chưa được khởi tạo. Điều này tạo ra lỗi khác với lỗi undefined name.

Một DSL có thể chọn:

- Khởi tạo theo thứ tự source và từ chối đọc giá trị chưa khởi tạo.
- Tính theo đồ thị phụ thuộc nếu các initializer thuần và không có chu trình.
- Dùng lazy evaluation để chỉ tính khi giá trị được yêu cầu.
- Chia giai đoạn khai báo và giai đoạn khởi tạo để tất cả symbol đã tồn tại trước khi đánh giá.

Chính sách cần nhất quán và có diagnostics riêng cho uninitialized value, circular dependency và undefined name.

## 15. Quy tắc shadowing và khai báo trùng tên

Forward reference có thể làm việc tra cứu tên phức tạp hơn khi cùng tên xuất hiện ở nhiều phạm vi.

Ví dụ:

~~~text
let status = "global"

scope {
    use status
    let status = "local"
}
~~~

Nếu DSL cho phép forward reference và áp dụng lexical scope, tham chiếu status bên trong block có thể trỏ tới khai báo local dù nó xuất hiện phía sau. Nếu DSL áp dụng quy tắc khai báo trước khi dùng, tham chiếu có thể trỏ tới status ở phạm vi cha hoặc bị từ chối tùy chính sách.

Đây là lý do cần quy định rõ:

- Tên cục bộ có che khuất tên ở phạm vi cha hay không?
- Khai báo local có hiệu lực từ đầu block hay từ vị trí khai báo?
- Hai khai báo cùng tên trong cùng scope có bị từ chối không?
- Một tên được khai báo nhiều lần trong các nhánh điều kiện có tạo cùng symbol hay không?

Ví dụ khai báo trùng:

~~~text
let timeout = 10
let timeout = 20
~~~

Nếu DSL không cho phép redeclaration trong cùng phạm vi, bộ phân giải phải báo lỗi duplicate declaration, kể cả khi tham chiếu trước đó đã resolve được tới một trong hai khai báo.

## 16. Tên chưa được định nghĩa và tham chiếu mơ hồ

Sau khi thu thập khai báo, một tham chiếu có thể rơi vào các trường hợp:

1. Tìm thấy đúng một symbol phù hợp.
2. Không tìm thấy symbol nào.
3. Tìm thấy nhiều symbol cùng phù hợp.
4. Tìm thấy symbol nhưng không đúng loại.
5. Tìm thấy symbol ngoài phạm vi truy cập.
6. Tìm thấy declaration nhưng chưa có definition cần thiết.

Ví dụ tên không tồn tại:

~~~text
step deploy {
    after package
}
~~~

nhưng không có bước package trong pipeline.

Ví dụ mơ hồ:

~~~text
import billing.Customer
import crm.Customer

let owner: Customer
~~~

Nếu cả hai module đều export Customer và DSL không có quy tắc ưu tiên, tên Customer là mơ hồ. Người viết cần dùng tên đầy đủ hoặc alias.

Ví dụ sai loại:

~~~text
let result = Customer
~~~

Nếu Customer là tên kiểu nhưng vị trí này yêu cầu một giá trị, việc tìm thấy symbol vẫn chưa đủ. Bộ phân giải hoặc semantic analyzer cần kiểm tra symbol kind.

## 17. Thông báo lỗi cho forward reference

Diagnostics nên phân biệt các nguyên nhân khác nhau. Một thông báo chung như "Name error" không giúp người viết biết liệu tên chưa được khai báo, nằm ngoài phạm vi hay chỉ được khai báo nhưng chưa định nghĩa.

Ví dụ thông báo:

~~~text
pipeline.dsl:4:15
Unknown step 'package'.
No step named 'package' is declared in pipeline 'release'.
~~~

Trường hợp declaration tồn tại nhưng không được phép dùng trước:

~~~text
config.dsl:2:14
Variable 'region' is used before its declaration.
Declare 'region' before this expression or move the declaration above this line.
~~~

Trường hợp declaration có nhưng thiếu definition:

~~~text
rules.dsl:8:5
Function 'calculateTax' was declared but has no definition in this module.
~~~

Trường hợp mơ hồ:

~~~text
module.dsl:12:10
Reference to 'Customer' is ambiguous.
Candidates:
  - billing.Customer
  - crm.Customer
Use a qualified name or import an alias.
~~~

Một diagnostic hữu ích thường gồm vị trí tham chiếu, tên đang tìm, phạm vi tra cứu, vị trí khai báo gần nhất nếu có và gợi ý sửa phù hợp. Nếu tên được khai báo ở phía dưới, IDE có thể cung cấp liên kết điều hướng tới declaration.

## 18. Thiết kế thuật toán phân giải tên

Một bộ phân giải tên cho DSL có forward reference có thể được tổ chức thành các giai đoạn sau:

### Bước 1: Tạo phạm vi

Tạo scope cho module, class, pipeline, function hoặc block theo cấu trúc AST. Mỗi scope có liên kết tới scope cha và bảng symbol riêng.

### Bước 2: Thu thập declaration

Duyệt các khai báo thuộc phạm vi được phép forward reference. Với từng khai báo, tạo symbol và kiểm tra trùng tên. Nếu cần, tạo symbol ở trạng thái declared-but-not-defined.

### Bước 3: Xử lý namespace và import

Đưa các symbol được export hoặc import vào môi trường tên thích hợp. Kiểm tra alias, visibility và xung đột.

### Bước 4: Resolve reference

Duyệt các node sử dụng tên. Tra cứu theo thứ tự scope được quy định, ví dụ local scope trước rồi đến parent scope. Nếu có qualified name, resolve từng phần theo namespace.

### Bước 5: Kiểm tra loại symbol

Đảm bảo vị trí sử dụng yêu cầu đúng loại: biểu thức cần value, lời gọi cần callable, annotation cần type, dependency cần step hoặc resource phù hợp.

### Bước 6: Kiểm tra definition và phụ thuộc

Đối với symbol cần có phần định nghĩa, xác nhận definition tồn tại. Với giá trị khởi tạo hoặc dependency graph, kiểm tra chu trình theo chính sách của DSL.

### Bước 7: Gắn liên kết và diagnostics

Lưu binding từ reference node tới symbol. Khi không resolve được, tạo diagnostic với source span. Khi resolve thành công, các giai đoạn type checking và code generation có thể dùng liên kết này thay vì tra cứu tên lại từ đầu.

Mã giả tổng quát:

~~~text
buildScopes(ast)

for scope in scopes:
    for declaration in scope.declarations:
        registerSymbol(scope, declaration)

for scope in scopes:
    resolveImports(scope)

for reference in ast.references:
    candidates = lookup(reference.name, reference.scope)
    symbol = selectUniqueCompatibleSymbol(candidates, reference)

    if symbol is missing:
        reportResolutionError(reference, candidates)
    else:
        reference.binding = symbol

validateDefinitions()
validateDependencyCycles()
typeCheck(ast)
~~~

Đây là cấu trúc khái niệm. Compiler có thể kết hợp một số bước hoặc lặp lại chúng khi kiểu và namespace phụ thuộc lẫn nhau.

## 19. Cân nhắc giữa parser và name resolver

Forward reference thường không cần parser phải biết tên đã khai báo hay chưa. Parser chủ yếu xác định cấu trúc cú pháp và tạo AST. Việc một tên có tồn tại trong phạm vi hay không thuộc trách nhiệm của semantic analysis.

Ví dụ, parser có thể chấp nhận:

~~~text
after compile
~~~

vì compile phù hợp với grammar của một identifier. Sau đó, name resolver mới xác định compile có phải một step trong pipeline hiện tại hay không.

Tách hai trách nhiệm giúp:

- Grammar không phụ thuộc vào symbol table.
- Parser có thể xử lý source khi khai báo nằm phía sau.
- Diagnostics phân biệt lỗi cú pháp và lỗi phân giải tên.
- IDE có thể tạo AST một phần khi source chưa hoàn chỉnh.
- Semantic analysis có thể áp dụng chính sách scope và forward reference mà không làm parser phức tạp.

Một số DSL có thể dùng parser hỗ trợ semantic predicate hoặc symbol-aware parsing, nhưng cần cân nhắc chi phí vì thay đổi symbol table có thể ảnh hưởng cách parse. Với phần lớn DSL, parser tạo cấu trúc trước và name resolver xử lý liên kết sau là cách tổ chức dễ kiểm soát.

## 20. Kiểm tra kiểu sau khi phân giải tên

Resolve thành công chỉ xác định tên trỏ tới symbol nào. Nó chưa chứng minh việc sử dụng symbol đó là hợp lệ về kiểu.

Ví dụ:

~~~text
let retries: Integer = 3
let endpoint: String = "https://example.test"

let result = retries(endpoint)
~~~

Nếu retries là biến Integer chứ không phải hàm, tên đã được tìm thấy nhưng việc gọi nó là sai loại symbol. Nếu tên trỏ tới một hàm, type checker tiếp tục kiểm tra số lượng và kiểu tham số.

Với forward declaration của hàm:

~~~text
declare function calculate(value: Decimal): Decimal

let total = calculate(100)
~~~

Name resolver liên kết calculate với function symbol. Type checker xác nhận đối số 100 có thể được dùng như Decimal theo quy tắc literal conversion. Khi definition xuất hiện, compiler kiểm tra chữ ký và phần thân có nhất quán hay không.

Do đó, pipeline thường có thứ tự logic: resolve name, kiểm tra loại symbol và kiểu, rồi mới sinh mã hoặc thực thi.

## 21. Tương tác với import, module và cache

Với DSL lớn, việc resolve toàn bộ module mỗi lần có thể tốn thời gian. Compiler hoặc language server có thể cache symbol export của module. Tuy nhiên, cache phải được làm mới khi file khai báo, import, alias hoặc cấu hình namespace thay đổi.

Các thông tin có thể cần trong cache:

- Module identifier và phiên bản.
- Danh sách symbol được export.
- Kiểu và chữ ký của symbol.
- Visibility và namespace.
- Vị trí nguồn hoặc metadata điều hướng.
- Hash hoặc timestamp của nội dung ảnh hưởng tới symbol table.

Nếu chỉ thay đổi phần thân hàm mà không đổi chữ ký, một số consumer có thể không cần resolve lại toàn bộ module. Nếu đổi tên symbol hoặc kiểu export, các module tham chiếu cần được phân tích lại.

Với IDE, source có thể đang ở trạng thái chưa hoàn chỉnh. Resolver cần có khả năng biểu diễn symbol chưa hoàn chỉnh hoặc reference chưa resolve mà không làm hỏng toàn bộ trải nghiệm soạn thảo. Khi người dùng tiếp tục gõ, kết quả phân giải có thể được cập nhật.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho phép forward reference nhưng chỉ resolve theo thứ tự source | Tên phía sau vẫn bị báo không tồn tại | Thu thập declaration trước khi resolve |
| Coi mọi tên xuất hiện trong file đều nhìn thấy ở mọi nơi | Vi phạm scope và visibility | Resolve trong đúng namespace và phạm vi |
| Nhầm declaration với definition | Symbol có chữ ký nhưng chưa có phần thân vẫn bị xem là hoàn chỉnh | Theo dõi trạng thái declared/defined |
| Không kiểm tra duplicate declaration | Một tên có nhiều mục tiêu không rõ ràng | Phát hiện xung đột khi xây symbol table |
| Không phát hiện dependency cycle | Giá trị khởi tạo hoặc workflow có thể không thể xử lý | Phân tích đồ thị theo loại quan hệ |
| Cấm mọi chu trình | Không hỗ trợ mutual recursion hoặc kiểu đệ quy hợp lệ | Phân biệt chu trình hợp lệ và không hợp lệ |
| Hoisting mọi loại khai báo | Có thể đọc biến trước khi khởi tạo | Tách thời điểm visibility và initialization |
| Để parser tự tra cứu symbol trong mọi trường hợp | Grammar và semantic analysis phụ thuộc chặt | Tách parsing khỏi name resolution khi phù hợp |
| Báo một lỗi chung cho mọi tham chiếu thất bại | Khó sửa lỗi | Phân biệt undefined, ambiguous, inaccessible và undefined definition |
| Cache symbol table không được invalidation | Resolver dùng thông tin khai báo cũ | Gắn cache với nội dung và dependency |

## 23. Quy trình thiết kế chính sách forward reference

Khi xây dựng DSL, có thể quyết định chính sách theo trình tự:

1. **Liệt kê loại symbol**: biến, hàm, kiểu, resource, step, rule, module và các loại tên khác.
2. **Chọn chính sách theo loại**: khai báo trước khi dùng, forward reference, hoisting hoặc forward declaration.
3. **Xác định phạm vi**: module, block, pipeline, function hoặc namespace nào cho phép tham chiếu.
4. **Xác định thời điểm hiệu lực**: tên có hiệu lực từ vị trí khai báo hay từ đầu scope?
5. **Tách declaration và definition**: loại symbol nào cần hai giai đoạn?
6. **Thiết kế symbol table**: lưu tên, kind, type, scope, source span và trạng thái definition.
7. **Chọn số lượt phân tích**: một lượt, hai lượt hoặc nhiều giai đoạn semantic analysis.
8. **Định nghĩa chu trình**: loại dependency nào được phép đệ quy và loại nào phải là đồ thị không chu trình?
9. **Định nghĩa khởi tạo**: eager, lazy, theo thứ tự source hay theo dependency graph?
10. **Định nghĩa diagnostics**: undefined, ambiguous, inaccessible, duplicate và declared-but-not-defined.
11. **Tài liệu hóa ví dụ**: có ví dụ hợp lệ, không hợp lệ và trường hợp tham chiếu tương hỗ.

Một chính sách rõ ràng giúp người viết biết khi nào có thể tổ chức khai báo theo ý muốn và khi nào phải tuân theo thứ tự. Nó cũng giúp người triển khai xác định đúng giai đoạn chịu trách nhiệm cho từng loại lỗi.

## 24. Tiêu chí của cơ chế tham chiếu trước khai báo tốt

Một cơ chế forward reference tốt cần bảo đảm người viết dự đoán được tên nào có thể được sử dụng trước, trong phạm vi nào và với điều kiện gì. Compiler phải resolve đúng symbol, phân biệt declaration với definition, phát hiện tên mơ hồ và xử lý phụ thuộc vòng theo ngữ nghĩa của từng loại khai báo.

Các câu hỏi quan trọng:

- Loại khai báo nào hỗ trợ tham chiếu trước?
- Tên có hiệu lực từ vị trí khai báo hay từ đầu phạm vi?
- Forward reference có vượt qua ranh giới module hoặc namespace không?
- Declaration có thể tồn tại mà chưa có definition không?
- Hàm hoặc kiểu có thể tham chiếu tương hỗ không?
- Giá trị khởi tạo được tính theo thứ tự nào?
- Chu trình phụ thuộc nào hợp lệ và chu trình nào là lỗi?
- Resolver báo vị trí tham chiếu và vị trí khai báo như thế nào?

Tham chiếu trước khai báo giúp DSL biểu diễn quan hệ và tổ chức source linh hoạt hơn, đặc biệt với workflow, schema, hàm đệ quy và mô hình nhiều module. Để hỗ trợ an toàn, ngôn ngữ cần quy định rõ scope, symbol table, các giai đoạn phân giải, thời điểm khởi tạo và chính sách chu trình. Khi những quy tắc đó nhất quán, forward reference trở thành một khả năng có kiểm soát của ngôn ngữ thay vì nguồn gây mơ hồ trong chương trình.

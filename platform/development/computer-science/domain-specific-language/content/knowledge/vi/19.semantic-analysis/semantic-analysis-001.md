# Các pha kiểm tra

Trong một **Domain-Specific Language (DSL)**, parser xác nhận source tuân theo grammar và tạo ra cấu trúc như Abstract Syntax Tree (AST). Tuy nhiên, một chương trình có cú pháp hợp lệ vẫn có thể sai về ý nghĩa: tên tài nguyên không tồn tại, biến được dùng sai kiểu, một bước workflow phụ thuộc vào chính nó hoặc cấu hình vi phạm quy tắc của miền nghiệp vụ.

**Kiểm tra ngữ nghĩa (semantic analysis)** là tập hợp các bước phân tích nhằm xác định chương trình có ý nghĩa hợp lệ theo quy tắc của DSL hay không. Công việc này thường được chia thành nhiều **pha kiểm tra (analysis phases)**. Mỗi pha tập trung vào một nhóm câu hỏi, sử dụng kết quả của các pha trước và bổ sung thông tin cho mô hình chương trình.

Ví dụ, DSL mô tả pipeline có thể có source:

~~~text
pipeline "release" {
    step deploy {
        command "deploy.sh"
        after package
    }

    step package {
        command "package.sh"
        after test
    }

    step test {
        command "test.sh"
        after compile
    }

    step compile {
        command "compile.sh"
    }
}
~~~

Parser có thể tạo AST cho đoạn này vì các token và cấu trúc khối hợp lệ. Semantic analysis tiếp tục kiểm tra tên các bước, quan hệ phụ thuộc, tính hợp lệ của đồ thị, kiểu tham số, quyền truy cập và các quy tắc riêng của workflow. Sau các pha kiểm tra, compiler hoặc runtime mới có thể sử dụng mô hình đã được phân giải.

## 1. Vì sao cần chia kiểm tra ngữ nghĩa thành các pha?

Một chương trình DSL có thể chứa nhiều loại thông tin liên quan lẫn nhau. Kiểm tra tất cả trong một lượt duy nhất thường khiến logic khó tổ chức, khó giải thích và khó mở rộng.

Việc chia pha mang lại một số lợi ích:

- **Tách trách nhiệm:** mỗi pha giải quyết một nhóm vấn đề như phạm vi tên, kiểu dữ liệu hoặc luồng điều khiển.
- **Xác định thứ tự phụ thuộc:** kiểm tra kiểu cần biết tên tham chiếu tới symbol nào; kiểm tra dependency cần biết các bước đã được thu thập.
- **Tái sử dụng kết quả:** symbol table, type information và source span được nhiều pha sử dụng.
- **Diagnostics rõ ràng:** lỗi có thể được phân loại theo giai đoạn và hiển thị vị trí phù hợp.
- **Mở rộng theo miền:** DSL có thể thêm pha kiểm tra quy tắc nghiệp vụ mà không làm parser phải biết mọi ràng buộc.
- **Hỗ trợ công cụ:** IDE, formatter, validator và compiler có thể dùng chung một phần mô hình phân tích.

Không có một thứ tự pha duy nhất phù hợp với mọi DSL. Một DSL cấu hình đơn giản có thể chỉ cần phân giải tên, kiểm tra kiểu và kiểm tra ràng buộc. Một DSL lập trình hoặc workflow phức tạp có thể cần thêm phân tích luồng điều khiển, luồng dữ liệu, phụ thuộc, hiệu ứng và tính khả thi khi thực thi.

## 2. Vị trí của semantic analysis trong pipeline

Một pipeline xử lý DSL thường có các giai đoạn lớn:

1. Đọc source và xử lý encoding.
2. Lexical analysis: chuyển ký tự thành token.
3. Parsing: kiểm tra grammar và tạo AST.
4. Semantic analysis: phân giải tên, kiểm tra kiểu và các ràng buộc.
5. Lowering hoặc xây dựng intermediate representation (IR).
6. Tối ưu hóa, sinh mã hoặc thực thi.

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    A[DSL source] --> B[Lexer]
    B --> C[Parser]
    C --> D[AST]
    D --> E[Semantic analysis]
    E --> F{Ngữ nghĩa hợp lệ?}
    F -->|Không| G[Diagnostics]
    F -->|Có| H[Typed AST / Semantic model]
    H --> I[IR hoặc domain model]
    I --> J[Optimize / Generate / Execute]
~~~

Parser thường không cần biết một biến đã được khai báo hay một resource có tồn tại. Nó chỉ cần nhận diện cấu trúc tên và biểu thức theo grammar. Semantic analysis dùng thông tin từ toàn bộ phạm vi hoặc module để xác định ý nghĩa thực tế của các tên và kiểm tra các quy tắc cao hơn.

Ranh giới giữa các pha có thể thay đổi theo công nghệ. Một số parser generator hỗ trợ semantic action; một số compiler kết hợp name resolution với type checking. Dù triển khai kết hợp hay tách riêng, các trách nhiệm logic vẫn cần được xác định rõ.

## 3. Đầu vào và đầu ra của các pha

Đầu vào phổ biến của semantic analysis là AST cùng thông tin source location. Các pha có thể tạo hoặc cập nhật:

- Scope tree: cây phạm vi tên.
- Symbol table: bảng symbol đã khai báo.
- Binding: liên kết giữa node tham chiếu và symbol.
- Type information: kiểu của biểu thức, biến và hàm.
- Dependency graph: đồ thị quan hệ giữa các thực thể.
- Control-flow graph: đồ thị luồng điều khiển.
- Data-flow facts: thông tin khởi tạo, khả năng null hoặc giá trị được biết.
- Diagnostics: lỗi, cảnh báo và ghi chú.
- Semantic model hoặc typed AST: mô hình đã được bổ sung thông tin để các bước sau sử dụng.

Một node AST ban đầu có thể chỉ chứa tên:

~~~text
NameReference("compile")
~~~

Sau name resolution, node được liên kết tới symbol:

~~~text
NameReference
    name: "compile"
    binding: Symbol(id = 17, kind = Step)
~~~

Sau các bước kiểm tra khác, semantic model có thể biết symbol đó thuộc pipeline nào, có kiểu gì và quan hệ dependency có hợp lệ hay không. Thông tin bổ sung giúp compiler không phải tra cứu lại tên ở mọi giai đoạn sau.

## 4. Pha 1 — Tạo phạm vi và thu thập khai báo

Trước khi kiểm tra một tham chiếu, hệ thống cần biết những tên nào được khai báo và phạm vi nào chứa chúng. Pha đầu tiên thường tạo scope và thu thập declaration.

### 4.1. Tạo scope tree

Scope là vùng mà một nhóm tên có hiệu lực. DSL có thể có scope cho:

- Toàn bộ chương trình hoặc module.
- Pipeline, service, schema hoặc rule group.
- Hàm và tham số.
- Block lồng nhau.
- Namespace hoặc package.

Ví dụ:

~~~text
module billing {
    let taxRate = 0.1

    function total(price: Decimal): Decimal {
        let fee = 2
        return price * (1 + taxRate) + fee
    }
}
~~~

Có thể tạo scope tree:

~~~text
ModuleScope(billing)
├── taxRate
└── FunctionScope(total)
    ├── price
    └── fee
~~~

Scope của hàm có thể tra cứu tên ở scope module cha theo lexical scoping. Nhưng scope module không thể tự động nhìn thấy biến fee chỉ tồn tại trong hàm.

### 4.2. Thu thập symbol

Mỗi declaration được đưa vào symbol table với thông tin phù hợp:

| Trường | Mục đích |
|---|---|
| Name | Tên định danh |
| Kind | Biến, hàm, kiểu, step, resource hoặc rule |
| Scope | Phạm vi chứa tên |
| Type/signature | Kiểu hoặc chữ ký nếu đã biết |
| Source span | Vị trí khai báo |
| Visibility | Public, private hoặc phạm vi truy cập |
| State | Declared, defined hoặc trạng thái chưa hoàn chỉnh |

Với DSL hỗ trợ forward reference, pha này có thể thu thập mọi khai báo trong một phạm vi trước khi resolve các tham chiếu. Với DSL yêu cầu khai báo trước khi dùng, compiler vẫn có thể xây scope tree nhưng phải giữ thông tin thứ tự để xác định tên có hiệu lực từ vị trí nào.

### 4.3. Kiểm tra khai báo trùng

Ví dụ:

~~~text
let timeout = 10
let timeout = 20
~~~

Nếu DSL không cho phép redeclaration trong cùng scope, pha thu thập khai báo có thể báo lỗi duplicate declaration. Nếu shadowing được phép trong scope con, cùng tên ở scope khác không nhất thiết là lỗi.

Pha này thường tạo đầu ra là scope tree và symbol table ban đầu.

## 5. Pha 2 — Phân giải tên và liên kết tham chiếu

**Name resolution** xác định mỗi tên trong source trỏ tới symbol nào. Đây là bước biến tên văn bản thành liên kết cụ thể trong semantic model.

Ví dụ:

~~~text
let subtotal: Decimal = 100
let taxRate: Decimal = 0.1
let total = subtotal * (1 + taxRate)
~~~

Các node subtotal và taxRate trong biểu thức được resolve tới symbol tương ứng.

### 5.1. Quy tắc tra cứu

Với lexical scope, bộ phân giải thường tìm từ phạm vi gần nhất rồi đi lên phạm vi cha:

1. Tìm tên trong scope hiện tại.
2. Nếu không có, tìm trong scope cha.
3. Tiếp tục cho đến module hoặc global scope.
4. Nếu vẫn không tìm thấy, báo undefined name.

Nếu có namespace hoặc module, bộ phân giải còn cần xét import, alias, visibility và tên đầy đủ.

### 5.2. Kiểm tra loại symbol

Tìm thấy tên chưa có nghĩa là sử dụng đúng. Một biểu thức gọi hàm cần symbol có thể gọi; một annotation cần type symbol; một dependency cần step hoặc resource phù hợp.

Ví dụ:

~~~text
let retries: Integer = 3
let result = retries()
~~~

Tên retries tồn tại nhưng là biến Integer, không phải hàm. Semantic analyzer cần báo lỗi gọi một giá trị không callable.

### 5.3. Forward reference

Nếu DSL cho phép tham chiếu trước khai báo, name resolution thường cần thu thập khai báo trước rồi mới resolve tham chiếu. Nếu DSL không cho phép, bộ phân giải phải kiểm tra thứ tự source hoặc thời điểm hiệu lực của symbol.

### 5.4. Tham chiếu không tồn tại hoặc mơ hồ

Các lỗi thường gặp:

- Undefined name: không có symbol phù hợp.
- Ambiguous reference: có nhiều symbol cùng phù hợp.
- Inaccessible symbol: symbol tồn tại nhưng không được phép truy cập.
- Wrong symbol kind: tên tồn tại nhưng không đúng loại cho vị trí sử dụng.
- Missing definition: có declaration nhưng thiếu definition bắt buộc.

Đầu ra của pha này là các binding từ reference node tới symbol hoặc diagnostics nếu không thể resolve.

## 6. Pha 3 — Phân giải kiểu và kiểm tra kiểu

Sau khi biết mỗi tên trỏ tới symbol nào, hệ thống có thể kiểm tra các biểu thức có dùng kiểu đúng quy tắc hay không.

### 6.1. Gán kiểu cho biểu thức

Với biểu thức:

~~~text
let quantity: Integer = 3
let unitPrice: Decimal = 12.5
let total: Decimal = quantity * unitPrice
~~~

Type checker xác định:

- quantity có kiểu Integer.
- unitPrice có kiểu Decimal.
- Phép nhân Integer với Decimal được phép theo numeric promotion nếu DSL định nghĩa quy tắc đó.
- Kết quả có kiểu Decimal và tương thích với kiểu của total.

Một phán đoán kiểu thường được ký hiệu:

\[
\Gamma \vdash e : T
\]

Trong đó \(\Gamma\) là môi trường kiểu, \(e\) là biểu thức và \(T\) là kiểu được suy ra.

### 6.2. Kiểm tra toán tử

Mỗi toán tử có quy tắc kiểu toán hạng và kiểu kết quả. Ví dụ:

| Toán tử | Kiểu toán hạng | Kiểu kết quả |
|---|---|---|
| + số học | Integer, Decimal theo promotion | Kiểu số theo quy tắc |
| and | Boolean, Boolean | Boolean |
| < | Hai kiểu có phép so sánh hợp lệ | Boolean |
| contains | Collection<T> và T | Boolean |
| * | Các kiểu số được hỗ trợ | Kiểu số theo promotion |

Nếu người viết áp dụng and cho một số nguyên, checker có thể từ chối thay vì tự chuyển số nguyên sang boolean nếu DSL không định nghĩa coercion đó.

### 6.3. Kiểm tra lời gọi hàm

Với lời gọi:

~~~text
calculateTax(order.total, customer.region)
~~~

Type checker cần xác nhận:

- Tên calculateTax đã resolve tới function symbol.
- Số lượng đối số đúng.
- Kiểu từng đối số tương thích với tham số tương ứng.
- Kiểu kết quả phù hợp với nơi sử dụng.
- Generic constraint hoặc overload được giải quyết rõ ràng nếu có.

### 6.4. Suy luận kiểu

DSL có thể cho phép bỏ qua kiểu tường minh:

~~~text
let count = 3
let label = "ready"
~~~

Compiler suy ra count là Integer và label là String. Suy luận kiểu thường cần phối hợp với việc kiểm tra biểu thức và có thể phải lặp lại nếu kiểu của một khai báo phụ thuộc vào khai báo khác.

### 6.5. Kiểm tra kiểu generic và variance

Với List<T>, Map<K,V> hoặc Function<A,B>, checker cần áp dụng quy tắc tương thích generic. Nếu DSL hỗ trợ covariance, contravariance hoặc invariance, quy tắc phải được dùng nhất quán ở gán biến, truyền tham số và trả về.

Đầu ra của pha type checking là kiểu được gán cho các node biểu thức, các ràng buộc kiểu đã giải quyết và diagnostics cho các trường hợp không tương thích.

## 7. Pha 4 — Kiểm tra khai báo, chữ ký và ràng buộc cấu trúc

Một số quy tắc không chỉ là kiểm tra kiểu biểu thức mà liên quan đến cấu trúc khai báo hoặc hợp đồng giữa các thành phần.

Ví dụ:

- Hàm được khai báo có đúng một definition không?
- Chữ ký definition có khớp forward declaration không?
- Interface được triển khai có đủ thành viên bắt buộc không?
- Một schema có khai báo trường trùng tên không?
- Một resource có tên duy nhất trong namespace không?
- Một rule có đủ điều kiện và hành động bắt buộc không?

Ví dụ DSL:

~~~text
declare function calculate(value: Decimal): Decimal

function calculate(value: Integer): Integer {
    return value
}
~~~

Tên hàm giống nhau nhưng chữ ký không khớp. Pha kiểm tra declaration/definition cần báo sự không nhất quán. Việc name resolution thành công chưa bảo đảm hợp đồng khai báo được đáp ứng.

## 8. Pha 5 — Kiểm tra phạm vi, quyền truy cập và visibility

Name resolution xác định symbol có thể được tìm thấy theo quy tắc tra cứu. Access checking xác định vị trí hiện tại có quyền sử dụng symbol đó hay không.

Ví dụ:

~~~text
module payment {
    private let secretKey = "..."

    public function charge() {
        ...
    }
}

module report {
    import payment
    use payment.secretKey
}
~~~

Nếu secretKey là private, module report không được truy cập dù tên có thể được tìm thấy qua metadata module. Ngược lại, charge là public nên có thể được sử dụng theo chính sách import.

Các mức visibility thường gặp:

- Private: chỉ dùng trong phạm vi khai báo.
- Internal/module: dùng trong module hoặc package.
- Public/exported: dùng được từ module khác.
- Protected: dùng trong kiểu con hoặc phạm vi kế thừa nếu DSL có mô hình đó.

DSL cấu hình có thể không cần hệ visibility phức tạp, nhưng vẫn có các quy tắc như resource chỉ được tham chiếu trong project, secret chỉ được dùng trong environment được cấp quyền hoặc biến chỉ có hiệu lực trong pipeline hiện tại.

## 9. Pha 6 — Kiểm tra hằng số và biểu thức tĩnh

Một số biểu thức có thể tính được trước khi chạy vì chúng chỉ phụ thuộc vào literal và các giá trị hằng đã biết. **Constant evaluation** tính các biểu thức như vậy để phát hiện lỗi sớm hoặc phục vụ các ràng buộc cần giá trị tĩnh.

Ví dụ:

~~~text
const MAX_RETRIES = 3
const BUFFER_SIZE = 1024 * 8
~~~

Compiler có thể tính BUFFER_SIZE thành 8192.

### 9.1. Kiểm tra giá trị literal

Một số ràng buộc cần giá trị cụ thể:

~~~text
array size = 10
port = 8080
timeout = 30s
~~~

Nếu DSL yêu cầu port là hằng số trong khoảng 1 đến 65535, compiler có thể kiểm tra ngay khi giá trị được biết.

### 9.2. Biểu thức không thể tính tĩnh

~~~text
let port = readEnvironment("PORT")
~~~

Giá trị này phụ thuộc môi trường runtime nên không thể tính tại compile time nếu compiler không có nguồn dữ liệu tương ứng. DSL cần phân biệt lỗi “không phải biểu thức hằng” với lỗi “giá trị hằng nằm ngoài miền”.

### 9.3. Giới hạn và an toàn

Constant evaluator nên giới hạn độ sâu, thời gian và kích thước kết quả. Một biểu thức đệ quy hoặc phép tính rất lớn không nên làm compiler tiêu tốn tài nguyên vô hạn. Các phép chia cho 0, overflow hoặc chuyển kiểu không hợp lệ cần tạo diagnostics theo chính sách số học của DSL.

Đầu ra có thể là giá trị hằng đã tính, metadata biểu thức tĩnh hoặc lỗi nếu một ngữ cảnh bắt buộc giá trị compile-time nhưng biểu thức không thể tính được.

## 10. Pha 7 — Kiểm tra luồng điều khiển

Với DSL có hàm, điều kiện, vòng lặp hoặc cấu trúc nhánh, semantic analysis có thể cần phân tích các đường đi trong chương trình.

Ví dụ:

~~~text
function getDiscount(active: Boolean): Decimal {
    if active {
        return 0.1
    }
}
~~~

Nếu hàm yêu cầu trả về Decimal trên mọi đường đi, nhánh active = false không có return. Control-flow analysis có thể phát hiện đường đi kết thúc mà không trả kết quả.

### 10.1. Control-flow graph

Một control-flow graph (CFG) biểu diễn các basic block và cạnh chuyển tiếp có thể xảy ra:

~~~mermaid
flowchart TD
    A[Entry] --> B{active?}
    B -->|true| C[return 0.1]
    B -->|false| D[Exit without return]
    C --> E[Exit]
    D --> E
~~~

CFG giúp kiểm tra:

- Hàm có return trên mọi đường đi không?
- Có câu lệnh nào không thể tới được không?
- Break hoặc continue có nằm trong vòng lặp hợp lệ không?
- Một nhánh có thể rơi xuyên sang nhánh khác không?
- Một block có đường đi không thể kết thúc không?

### 10.2. Reachability

Ví dụ:

~~~text
return 1
log("unreachable")
~~~

Nếu return kết thúc hàm, lời gọi log phía sau không thể được thực thi. Compiler có thể báo warning unreachable code.

### 10.3. Return, break và continue

DSL cần xác định các câu lệnh điều khiển hợp lệ trong ngữ cảnh nào. return chỉ có thể xuất hiện trong function hoặc một khối được quy định; break cần nằm trong vòng lặp hoặc switch; continue cần có vòng lặp bao quanh.

Kiểm tra cú pháp không đủ để xác nhận những quy tắc ngữ cảnh này. Parser có thể nhận diện token return, nhưng semantic analyzer mới biết nó có nằm trong function body hợp lệ hay không.

## 11. Pha 8 — Phân tích luồng dữ liệu

**Data-flow analysis** theo dõi thông tin về giá trị hoặc trạng thái của biến qua các điểm trong chương trình. Nó có thể xác định biến đã được khởi tạo trước khi đọc, giá trị có thể null hay không, hoặc một giá trị có còn được sử dụng không.

Ví dụ:

~~~text
let result: Integer

if condition {
    result = 10
}

print(result)
~~~

Nếu condition là false, result chưa được gán trước khi đọc. Definite-assignment analysis có thể phát hiện điều này.

### 11.1. Definite assignment

Phân tích definite assignment kiểm tra một biến đã được gán trên mọi đường đi dẫn tới điểm sử dụng hay chưa.

~~~mermaid
flowchart TD
    A[Declare result] --> B{condition?}
    B -->|true| C[Assign result = 10]
    B -->|false| D[Skip assignment]
    C --> E[Merge paths]
    D --> E
    E --> F[Read result]
    F --> G[May be uninitialized]
~~~

Nếu DSL có default initialization, kết quả có thể khác. Vì vậy, data-flow analysis phải sử dụng đúng quy tắc khởi tạo của ngôn ngữ.

### 11.2. Nullability analysis

Một biến có kiểu optional có thể chứa null:

~~~text
let customer: Customer?
if customer != null {
    print(customer.name)
}
~~~

Trong nhánh true, analyzer có thể suy ra customer không null. Nếu truy cập customer.name ở ngoài điều kiện, hệ thống cần kiểm tra lại vì giá trị có thể null.

### 11.3. Constant propagation và liveness

Data-flow analysis cũng có thể theo dõi giá trị hằng đã biết hoặc biến nào còn cần thiết:

~~~text
let limit = 10
let next = limit + 1
~~~

Nếu limit không thay đổi, compiler có thể truyền giá trị 10 vào biểu thức tiếp theo. Liveness analysis xác định biến còn được sử dụng ở đâu, hỗ trợ tối ưu hóa hoặc cảnh báo biến không dùng.

Các phân tích này có thể thuộc semantic analysis mở rộng hoặc các bước tối ưu hóa sau đó, tùy kiến trúc compiler. Điều quan trọng là phân biệt kiểm tra bắt buộc để chương trình hợp lệ với phân tích phục vụ tối ưu.

## 12. Pha 9 — Kiểm tra quan hệ và phụ thuộc của miền DSL

Đây là pha đặc biệt quan trọng đối với DSL vì nhiều ràng buộc không thể diễn đạt đầy đủ bằng grammar hoặc kiểu dữ liệu tổng quát.

### 12.1. Kiểm tra dependency graph

Với workflow:

~~~text
step deploy { after package }
step package { after test }
step test { after compile }
step compile { }
~~~

Semantic analyzer tạo đồ thị dependency và kiểm tra:

- Mọi tên bước được tham chiếu có tồn tại không?
- Một bước có tự phụ thuộc không?
- Có chu trình không?
- Có dependency tới bước thuộc pipeline khác không?
- Có quan hệ bị cấm theo chính sách miền không?

Nếu workflow yêu cầu DAG, có thể dùng topological sort để xác định thứ tự thực thi. Nếu có chu trình, cần báo đường đi tạo chu trình.

### 12.2. Kiểm tra tài nguyên

DSL hạ tầng có thể mô tả:

~~~text
service "api" {
    replicas = 3
    memory = "512Mi"
    network = "backend"
}
~~~

Các kiểm tra miền có thể gồm:

- replicas phải lớn hơn 0.
- memory phải nằm trong giới hạn được hỗ trợ.
- network backend phải tồn tại và có loại phù hợp.
- Service không được tham chiếu tới tài nguyên thuộc project khác nếu không được cấp quyền.
- Tổng tài nguyên không vượt ngân sách cấu hình nếu DSL có quy tắc này.

### 12.3. Kiểm tra quy tắc nghiệp vụ

DSL tính giá đơn hàng có thể yêu cầu:

~~~text
discountRate >= 0 and discountRate <= 1
quantity > 0
currency == order.currency
~~~

Các biểu thức trên có thể parse và type-check thành công nhưng vẫn cần được đánh giá theo quy tắc nghiệp vụ. Pha domain validation xác nhận mô hình thỏa các bất biến đó.

## 13. Pha 10 — Kiểm tra khả năng thực thi và hiệu ứng

Một chương trình có thể hợp lệ về cú pháp, tên và kiểu nhưng không thể thực thi theo chính sách của DSL.

Ví dụ:

- Một workflow yêu cầu secret chưa được cung cấp.
- Một rule gọi capability mà môi trường không cho phép.
- Một service yêu cầu vùng triển khai không được hỗ trợ.
- Một hành động ghi file nằm ngoài sandbox.
- Một transaction chứa thao tác không được phép trong chế độ read-only.

Các kiểm tra này có thể cần thông tin từ cấu hình runtime, môi trường triển khai hoặc capability registry. Vì vậy, cần phân biệt:

- **Static semantic validation:** có thể kiểm tra từ source, schema và metadata đã biết.
- **Environment validation:** cần biết môi trường đích hoặc cấu hình triển khai.
- **Runtime validation:** chỉ có thể xác nhận khi chương trình chạy hoặc khi dữ liệu thực tế xuất hiện.

Không nên gọi một lỗi runtime là lỗi parser. Diagnostics nên chỉ ra pha và điều kiện khiến lỗi được phát hiện.

## 14. Pha 11 — Xây dựng typed AST hoặc semantic model

Sau khi các kiểm tra cần thiết hoàn tất, compiler có thể tạo một mô hình giàu thông tin hơn AST ban đầu.

Ví dụ AST:

~~~text
BinaryExpression(
    NameReference("quantity"),
    "*",
    NameReference("unitPrice")
)
~~~

Typed AST:

~~~text
BinaryExpression
    operator: Multiply
    left:
        NameReference
            symbol: quantity#12
            type: Integer
    right:
        NameReference
            symbol: unitPrice#13
            type: Decimal
    resultType: Decimal
~~~

Typed AST có thể chứa:

- Symbol binding đã resolve.
- Kiểu của mỗi node.
- Kiểu kết quả của toán tử.
- Thông tin chuyển kiểu được chèn ngầm định.
- Giá trị hằng đã tính.
- Source span và diagnostics.
- Dependency hoặc control-flow metadata.

Các bước lowering và code generation có thể dùng thông tin này để tránh lặp lại việc phân tích tên và kiểu.

Không nhất thiết phải sửa AST gốc. Một số kiến trúc tạo semantic model riêng hoặc lưu annotation ngoài cây để giữ syntax tree bất biến.

## 15. Thứ tự phụ thuộc giữa các pha

Một chuỗi pha thường gặp:

1. Tạo scope và thu thập khai báo.
2. Resolve import, namespace và tên.
3. Kiểm tra declaration/definition và visibility.
4. Type checking và type inference.
5. Constant evaluation và kiểm tra ràng buộc compile-time.
6. Control-flow và data-flow analysis.
7. Domain-specific validation.
8. Kiểm tra khả năng thực thi theo môi trường.
9. Tạo typed AST hoặc semantic model để lowering.

Sơ đồ phụ thuộc minh họa:

~~~mermaid
flowchart TD
    A[AST] --> B[Scope và declaration collection]
    B --> C[Name resolution]
    C --> D[Visibility và declaration checks]
    C --> E[Type checking]
    D --> E
    E --> F[Constant evaluation]
    E --> G[Control-flow analysis]
    E --> H[Data-flow analysis]
    F --> I[Domain validation]
    G --> I
    H --> I
    I --> J[Environment checks]
    J --> K[Typed AST / Semantic model]
~~~

Đây là mô hình tham khảo, không phải lịch trình bắt buộc. Ví dụ, một số kiểm tra miền cần chạy trước type inference; một số constant expression cần kiểu đã biết; data-flow analysis cần CFG; một DSL cấu hình có thể không có CFG. Compiler có thể gộp, tách hoặc lặp lại các pha tùy quan hệ dữ liệu.

## 16. Phân tích một lượt, nhiều lượt và xử lý lặp

### 16.1. Một lượt

Một lượt phù hợp khi:

- Khai báo phải xuất hiện trước khi sử dụng.
- Không có quan hệ tương hỗ phức tạp.
- Kiểu và ngữ nghĩa có thể xác định ngay tại vị trí đọc.
- Không cần phân tích toàn cục.

Ưu điểm là đơn giản và tiết kiệm bộ nhớ. Nhược điểm là khó hỗ trợ forward reference, inference phụ thuộc lẫn nhau hoặc đồ thị quan hệ.

### 16.2. Nhiều lượt

Nhiều lượt thường dùng khi compiler cần biết toàn bộ khai báo trước khi resolve hoặc type-check:

~~~text
pass 1: buildScopes()
pass 2: collectDeclarations()
pass 3: resolveReferences()
pass 4: inferAndCheckTypes()
pass 5: validateControlAndDataFlow()
pass 6: validateDomainRules()
~~~

Mỗi lượt có đầu vào và đầu ra rõ ràng, giúp kiểm tra và debug dễ hơn. Đổi lại, cần quản lý trạng thái node, symbol và diagnostics giữa các lượt.

### 16.3. Phân tích lặp hoặc fixed-point

Một số thông tin chỉ ổn định sau nhiều lần lan truyền. Ví dụ, type inference trong một nhóm khai báo tương hỗ hoặc data-flow analysis trên CFG có thể cần lặp cho tới khi không còn thay đổi.

Mã giả data-flow:

~~~text
initializeFacts()
changed = true

while changed:
    changed = false

    for block in controlFlowGraph:
        newFacts = transfer(block, incomingFacts(block))

        if newFacts != oldFacts(block):
            updateFacts(block, newFacts)
            changed = true
~~~

Điều kiện dừng là tập facts không thay đổi qua một lượt. Để bảo đảm thuật toán kết thúc, miền dữ liệu và phép hợp nhất facts cần có tính chất phù hợp; trong thực tế có thể cần widening hoặc giới hạn iteration cho phân tích phức tạp.

## 17. Diagnostics và quản lý lỗi giữa các pha

Một semantic analyzer hữu ích cần tạo lỗi dễ hiểu và tiếp tục phân tích khi có thể. Nếu một pha thất bại, các pha sau cần biết node nào chưa có thông tin đáng tin cậy.

### 17.1. Phân loại diagnostics

| Pha | Ví dụ lỗi hoặc cảnh báo |
|---|---|
| Declaration collection | Tên khai báo trùng |
| Name resolution | Tên không tồn tại hoặc mơ hồ |
| Type checking | Gán Decimal vào Boolean |
| Visibility | Truy cập symbol private |
| Constant evaluation | Chia cho 0 trong biểu thức hằng |
| Control flow | Hàm thiếu return trên một nhánh |
| Data flow | Đọc biến có thể chưa khởi tạo |
| Domain validation | Workflow có dependency cycle |
| Environment validation | Thiếu capability hoặc secret |

### 17.2. Error type và error node

Khi resolve tên thất bại, compiler có thể gán một ErrorType hoặc ErrorSymbol cho node để các pha sau tiếp tục mà không tạo hàng loạt lỗi dây chuyền.

Ví dụ:

~~~text
let result = missingName + 1
~~~

Pha name resolution báo missingName không tồn tại. Type checker có thể đánh dấu node đó là ErrorType và tránh báo thêm lỗi không cần thiết như “không thể cộng ErrorType với Integer” nếu lỗi thứ hai không cung cấp thông tin mới.

### 17.3. Vị trí nguồn và liên kết lỗi

Diagnostics nên giữ source span của node tham chiếu và có thể kèm vị trí khai báo liên quan. Một lỗi duplicate declaration có thể trỏ tới khai báo thứ hai và ghi chú vị trí khai báo đầu tiên.

### 17.4. Mức độ nghiêm trọng

Compiler có thể phân loại:

- Error: chương trình không thể được chấp nhận.
- Warning: chương trình hợp lệ nhưng có khả năng sai hoặc khó bảo trì.
- Info/Hint: thông tin hỗ trợ người dùng.

Một DSL có thể cho phép cấu hình mức cảnh báo, nhưng không nên biến lỗi vi phạm bất biến an toàn thành warning nếu điều đó làm runtime nhận mô hình không hợp lệ.

## 18. Ví dụ tổng hợp: các pha kiểm tra một DSL workflow

Xét source:

~~~text
pipeline "release" {
    variable retries: Integer = 3

    step deploy {
        command "deploy.sh"
        after package
        retry retries
    }

    step package {
        command "package.sh"
        after test
    }

    step test {
        command "test.sh"
        after compile
    }

    step compile {
        command "compile.sh"
    }
}
~~~

### Pha 1: Thu thập khai báo

Tạo scope pipeline release và đăng ký variable retries cùng bốn step deploy, package, test, compile.

### Pha 2: Phân giải tên

Resolve retries trong retry retries tới variable symbol. Resolve package, test và compile trong các quan hệ after tới step symbol tương ứng.

### Pha 3: Kiểm tra kiểu

Xác nhận retries là Integer và tham số của retry yêu cầu Integer dương. Xác nhận command nhận String nếu DSL định nghĩa command như một chuỗi.

### Pha 4: Kiểm tra quan hệ miền

Tạo các cạnh:

~~~text
compile -> test
test -> package
package -> deploy
~~~

Xác nhận tất cả step tồn tại, không có self-dependency và đồ thị không có chu trình.

### Pha 5: Kiểm tra giá trị tĩnh

retries có giá trị hằng 3. Nếu retry yêu cầu giá trị trong khoảng 0 đến 10, điều kiện được thỏa mãn.

### Pha 6: Tạo semantic model

Mô hình cuối cùng có thể chứa các Step đã resolve, dependency graph, retry count và command. Runtime không cần tìm lại tên package hoặc compile trong source.

Nếu thay after package thành after publish, lỗi undefined step được phát hiện ở name resolution. Nếu giữ tên nhưng tạo dependency cycle, lỗi được phát hiện ở domain validation. Hai lỗi khác pha dù cùng liên quan tới dependency.

## 19. Ví dụ tổng hợp: kiểm tra DSL cấu hình dịch vụ

Xét:

~~~text
environment "production" {
    service "orders-api" {
        image = "orders:2.4"
        replicas = 3
        memory = "512Mi"
        network = "backend"
    }

    network "backend" {
        cidr = "10.20.0.0/16"
    }
}
~~~

Các pha có thể thực hiện:

- **Declaration collection:** đăng ký environment, service và network.
- **Name resolution:** resolve network backend trong thuộc tính service.
- **Type checking:** kiểm tra replicas là Integer, memory là MemorySize theo kiểu DSL, image là String.
- **Constant evaluation:** tính các giá trị tĩnh như replicas.
- **Domain validation:** replicas phải lớn hơn 0; memory phải nằm trong giới hạn; CIDR phải hợp lệ; network phải thuộc cùng environment.
- **Environment validation:** kiểm tra image có thể được lấy từ registry và môi trường có capability triển khai tương ứng nếu thông tin đó sẵn có.

Source có thể parse thành công nhưng vẫn thất bại ở một pha sau. Ví dụ replicas = 0 có kiểu Integer hợp lệ nhưng vi phạm bất biến của service. Tương tự, network có tên đúng nhưng nằm ngoài environment mà service được phép sử dụng.

## 20. Tối ưu và tổ chức hiệu năng các pha

Với chương trình lớn, semantic analysis có thể tốn thời gian. Một số nguyên tắc tổ chức:

- Dùng symbol table và scope tree có cấu trúc tra cứu hiệu quả.
- Lưu binding đã resolve để không tra cứu tên lặp lại.
- Cache type information và metadata của module nếu có thể xác định dependency invalidation.
- Chỉ chạy các pha phụ thuộc vào vùng source đã thay đổi khi hỗ trợ incremental analysis.
- Dùng source span và node identity ổn định để cập nhật diagnostics.
- Tách kiểm tra bắt buộc khỏi phân tích tùy chọn phục vụ tối ưu hóa.
- Giới hạn tài nguyên cho constant evaluation và phân tích đồ thị.

### 20.1. Incremental semantic analysis

IDE thường phân tích lại khi người dùng gõ. Thay vì chạy lại mọi pha trên toàn dự án, language server có thể xác định thay đổi ảnh hưởng tới scope, symbol hoặc module nào.

Ví dụ:

- Sửa literal trong thân hàm có thể chỉ cần type check và phân tích liên quan trong hàm.
- Đổi tên symbol export có thể ảnh hưởng mọi module import symbol đó.
- Thay đổi kiểu tham số hàm có thể làm các lời gọi ở nhiều file cần type-check lại.
- Thay đổi dependency trong workflow có thể yêu cầu xây lại phần đồ thị liên quan.

Incremental analysis cần dependency graph giữa các kết quả phân tích để invalidation chính xác. Nếu cache không được làm mới khi đầu vào liên quan thay đổi, IDE có thể hiển thị kết quả cũ.

## 21. Kiểm thử các pha semantic analysis

Mỗi pha nên có ví dụ kiểm tra riêng và có các bài tích hợp xuyên suốt pipeline.

### 21.1. Kiểm thử scope và declaration

- Khai báo hợp lệ trong cùng scope.
- Trùng tên trong cùng scope.
- Shadowing trong scope con.
- Tên private được truy cập từ bên ngoài.
- Forward reference theo chính sách của DSL.

### 21.2. Kiểm thử name resolution

- Tên tồn tại và được resolve đúng symbol.
- Tên không tồn tại.
- Tên mơ hồ do import.
- Symbol sai loại.
- Tham chiếu vượt phạm vi.

### 21.3. Kiểm thử type checking

- Gán đúng kiểu và sai kiểu.
- Numeric promotion.
- Gọi hàm sai số lượng hoặc kiểu tham số.
- Generic variance.
- Nullable và non-nullable.
- Overload resolution.

### 21.4. Kiểm thử control-flow và data-flow

- Hàm return trên mọi đường đi.
- Nhánh unreachable.
- Break/continue ngoài vòng lặp.
- Biến được gán trên mọi đường đi.
- Truy cập giá trị có thể null.

### 21.5. Kiểm thử domain validation

- Resource tồn tại và đúng loại.
- Dependency graph không có chu trình.
- Ràng buộc số lượng và giới hạn được thỏa mãn.
- Quy tắc môi trường và capability.

### 21.6. Kiểm thử tích hợp

Một test tích hợp nên xác nhận source hợp lệ đi qua toàn bộ các pha và tạo semantic model đúng. Test lỗi nên xác nhận diagnostic xuất hiện ở pha phù hợp, không chỉ kiểm tra có lỗi bất kỳ.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dồn mọi kiểm tra vào parser | Grammar phụ thuộc symbol và quy tắc miền | Tách cấu trúc cú pháp khỏi semantic analysis |
| Type-check trước khi resolve tên | Không biết kiểu của biến hoặc hàm được tham chiếu | Resolve symbol trước hoặc dùng placeholder có kiểm soát |
| Chỉ kiểm tra kiểu mà bỏ qua bất biến miền | Mô hình đúng kiểu nhưng sai nghiệp vụ | Bổ sung domain validation |
| Không phân biệt lỗi và warning | Người dùng không biết lỗi nào chặn thực thi | Định nghĩa severity và chính sách rõ |
| Một lỗi gây nhiều lỗi dây chuyền | Diagnostics nhiễu và khó sửa | Dùng error symbol/type để phục hồi phân tích |
| Không lưu source span | Không thể chỉ vị trí chính xác | Gắn source location vào AST và symbol |
| Chạy phân tích phụ thuộc trước khi có CFG | Kết quả luồng điều khiển thiếu cơ sở | Xây CFG trước các phân tích cần nó |
| Không invalidation cache | IDE/compiler dùng thông tin semantic cũ | Theo dõi dependency giữa các pha |
| Coi mọi DSL đều cần mọi pha | Kiến trúc phức tạp không cần thiết | Chọn pha theo khả năng và quy tắc của miền |
| Trộn kiểm tra tĩnh với kiểm tra runtime | Báo lỗi sai thời điểm hoặc dựa vào môi trường không có | Phân loại static, environment và runtime validation |

## 23. Quy trình thiết kế các pha kiểm tra cho DSL

Khi thiết kế compiler hoặc validator cho DSL, có thể bắt đầu từ các bước:

1. **Liệt kê quy tắc ngữ nghĩa:** tên, kiểu, phạm vi, cấu trúc, luồng điều khiển, phụ thuộc và bất biến miền.
2. **Xác định dữ liệu cần cho mỗi quy tắc:** AST, scope, symbol, type, CFG, dependency graph hoặc environment metadata.
3. **Xác định phụ thuộc giữa các kiểm tra:** pha nào cần kết quả của pha nào?
4. **Nhóm thành các pha có trách nhiệm rõ:** tránh tạo một pha quá lớn hoặc quá nhiều pha nhỏ không cần thiết.
5. **Định nghĩa đầu vào và đầu ra:** mỗi pha nhận gì, cập nhật gì và tạo diagnostics nào?
6. **Xác định chiến lược xử lý lỗi:** pha sau có thể tiếp tục khi pha trước thất bại đến mức nào?
7. **Chọn một lượt hay nhiều lượt:** xét forward reference, inference, dependency và phân tích luồng.
8. **Xác định static và runtime boundary:** quy tắc nào có thể kiểm tra trước khi chạy?
9. **Thiết kế kiểm thử theo pha:** có test riêng và test tích hợp cho các đường đi quan trọng.
10. **Xem xét incremental analysis:** nếu DSL được dùng trong IDE hoặc file lớn, cần biết thay đổi nào làm mất hiệu lực kết quả cũ.

Một tài liệu thiết kế pha nên mô tả rõ mục tiêu, dữ liệu vào, dữ liệu ra, lỗi có thể tạo, điều kiện chạy và các pha phụ thuộc. Nhờ đó, người triển khai có thể thay đổi một bước mà không vô tình phá vỡ hợp đồng của các bước khác.

## 24. Tiêu chí của quy trình kiểm tra ngữ nghĩa tốt

Một quy trình semantic analysis tốt xác định được chương trình hợp lệ theo các quy tắc của DSL, tạo thông tin đủ để compiler hoặc runtime sử dụng và giải thích lỗi ở đúng vị trí. Các pha nên có trách nhiệm rõ ràng, thứ tự phụ thuộc hợp lý và cơ chế phục hồi khi gặp lỗi.

Các câu hỏi quan trọng:

- Tên và phạm vi được thu thập, phân giải ở pha nào?
- Type checking có sử dụng binding đã resolve không?
- Những ràng buộc nào cần giá trị hằng?
- DSL có cần control-flow hoặc data-flow analysis không?
- Các quan hệ miền như dependency graph được kiểm tra ở đâu?
- Kiểm tra nào là static, kiểm tra nào cần môi trường hoặc runtime?
- Khi một pha thất bại, các pha sau tiếp tục thế nào?
- Semantic model cuối cùng chứa những annotation nào?
- Cache và incremental analysis được invalidation theo dependency ra sao?

Các pha kiểm tra giúp chuyển AST từ một cấu trúc cú pháp thành mô hình có ý nghĩa và có thể sử dụng an toàn. Khi scope, name resolution, type checking, phân tích luồng và validation theo miền được tổ chức rõ ràng, DSL có thể phát hiện lỗi sớm, cung cấp diagnostics hữu ích và tạo nền tảng đáng tin cậy cho lowering, sinh mã hoặc thực thi.

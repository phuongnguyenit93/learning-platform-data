# Hướng dẫn nhập môn Computer Science Domain Specific Language

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích DSL là gì, vì sao một ngôn ngữ chuyên biệt được tạo ra và khác gì với ngôn ngữ lập trình đa mục đích.
- Nhận diện các thành phần cơ bản của một DSL: từ vựng, cú pháp, kiểu dữ liệu, ngữ nghĩa, thư viện và runtime.
- Đọc tài liệu ngôn ngữ, ví dụ và thông báo lỗi một cách có hệ thống.
- Chuẩn bị môi trường học tập và xác định công cụ cần dùng để viết, kiểm tra và chạy chương trình DSL.
- Viết, chạy và giải thích một chương trình đầu tiên bằng cú pháp minh họa.
- Hiểu biến, kiểu dữ liệu, biểu thức, điều kiện, vòng lặp, hàm và cấu trúc dữ liệu.
- Phân biệt lỗi cú pháp, lỗi kiểu, lỗi ngữ nghĩa và lỗi runtime.
- Áp dụng quy trình thử nghiệm, debug và cải tiến chương trình.
- Tổ chức bài tập theo độ khó và xây dựng lộ trình học DSL có hiệu quả.
- Nhận biết cách DSL kết nối với ứng dụng, dữ liệu, workflow và hệ thống bên ngoài.

## 1. Computer Science DSL là gì?

DSL là viết tắt của Domain-Specific Language, nghĩa là ngôn ngữ chuyên biệt cho một miền vấn đề. Một DSL được thiết kế để diễn đạt một nhóm công việc cụ thể bằng các khái niệm gần với miền đó.

Ví dụ:
- SQL tập trung vào truy vấn và thao tác dữ liệu.
- Regular expressions tập trung vào mô tả mẫu chuỗi.
- CSS tập trung vào cách trình bày giao diện.
- Một workflow DSL tập trung vào các bước, điều kiện, nhánh và sự kiện của quy trình.
- Một rule DSL tập trung vào điều kiện và hành động của luật.
- Một query DSL tập trung vào việc lọc, kết hợp và tổng hợp dữ liệu.

Trong chương trình học Computer Science Domain Specific Language, người học tiếp cận cách mô tả các khái niệm khoa học máy tính bằng những ngôn ngữ có mục đích rõ ràng. Nội dung có thể bao gồm cú pháp, kiểu dữ liệu, biểu thức, truy vấn, luật, quy trình, API, tích hợp, hiệu năng và công cụ phát triển.

Một DSL thường không nhằm thay thế mọi ngôn ngữ lập trình. Nó cung cấp cách diễn đạt ngắn gọn và phù hợp hơn cho một loại công việc. Phần còn lại của ứng dụng vẫn có thể được viết bằng ngôn ngữ đa mục đích như Java, Kotlin, Python, C# hoặc TypeScript.

### 1.1. DSL và ngôn ngữ đa mục đích

| Tiêu chí | DSL | Ngôn ngữ đa mục đích |
|---|---|---|
| Phạm vi | Một miền hoặc nhóm tác vụ cụ thể | Nhiều loại ứng dụng |
| Từ vựng | Gần với khái niệm miền | Tổng quát hơn |
| Cấu trúc | Tối ưu cho một số loại biểu đạt | Linh hoạt cho nhiều cấu trúc |
| Người dùng | Chuyên gia miền, developer hoặc cả hai | Chủ yếu là người phát triển phần mềm |
| Runtime | Có thể cần engine hoặc compiler riêng | Thường có hệ sinh thái runtime rộng |
| Ví dụ | SQL, CSS, workflow DSL | Java, Python, C# |

### 1.2. DSL và cấu hình

Một file cấu hình cũng có thể trông giống ngôn ngữ, nhưng không phải mọi file cấu hình đều là DSL. Cấu hình thường khai báo giá trị hoặc lựa chọn. DSL có thể mô tả biểu thức, quan hệ, quy tắc, luồng điều khiển hoặc hành vi có thể thực thi.

Ranh giới không phải lúc nào cũng tuyệt đối. Một cấu hình có điều kiện và biểu thức có thể dần trở thành một DSL.

### 1.3. DSL bên trong và DSL bên ngoài

- **External DSL:** có cú pháp và parser riêng, ví dụ một ngôn ngữ truy vấn được viết trong file riêng.
- **Internal DSL:** được xây dựng trên cú pháp của một ngôn ngữ chủ, thường dùng API, builder hoặc function chaining.

External DSL có thể gần với ngôn ngữ nghiệp vụ hơn nhưng cần compiler/parser riêng. Internal DSL tái sử dụng toolchain của ngôn ngữ chủ nhưng bị giới hạn bởi cú pháp của ngôn ngữ đó.

## 2. Vì sao cần học DSL?

DSL giúp diễn đạt một công việc bằng những khái niệm phù hợp với công việc đó. Người dùng không cần biết mọi chi tiết của hệ thống bên dưới để mô tả điều họ muốn.

Một DSL tốt có thể:
- Làm cho ý định của chương trình rõ ràng hơn.
- Giảm mã lặp lại.
- Giới hạn các thao tác được phép.
- Cho phép kiểm tra lỗi trước khi chạy.
- Tạo cơ hội tối ưu hóa dựa trên ý nghĩa miền.
- Cho phép chuyên gia miền tham gia xây dựng quy tắc.
- Sinh code, query plan hoặc workflow từ một mô tả có cấu trúc.

Ví dụ, thay vì tự viết vòng lặp và xử lý từng record:

~~~text
for each order in orders:
    if order.status == "PAID":
        total = total + order.amount
~~~

Một query DSL có thể diễn đạt:

~~~text
orders
    .filter(status == "PAID")
    .sum(amount)
~~~

Cách viết thứ hai thể hiện ý định lọc và tổng hợp. Engine có thể chọn cách thực thi phù hợp, chẳng hạn chạy trong bộ nhớ hoặc đẩy phép tính xuống database.

### 2.1. DSL không tự động làm chương trình tốt hơn

Một DSL thiết kế kém có thể khó đọc hơn ngôn ngữ đa mục đích. Một biểu thức ngắn không bảo đảm hiệu năng cao. Người học vẫn cần hiểu dữ liệu, kiểu, lỗi, giới hạn runtime và tác động của các thao tác.

### 2.2. Hiểu miền trước khi học cú pháp

Khi gặp một DSL mới, hãy xác định:
- DSL giải quyết vấn đề gì?
- Ai là người dùng chính?
- Dữ liệu đầu vào là gì?
- Kết quả đầu ra là gì?
- Hệ thống thực thi mô tả đó như thế nào?
- Những hành vi nào bị cấm hoặc bị giới hạn?

Những câu hỏi này giúp đọc tài liệu có mục đích thay vì chỉ ghi nhớ từ khóa.

## 3. Các thành phần cơ bản của một DSL

Một DSL có thể được hiểu qua nhiều lớp.

~~~text
Source Text
    |
    v
Lexical Structure
    |
    v
Syntax / Grammar
    |
    v
Parsing
    |
    v
AST
    |
    v
Semantic Analysis
    |
    v
Execution / Compilation
    |
    v
Result
~~~

### 3.1. Từ vựng (lexical structure)

Từ vựng xác định những đơn vị nhỏ nhất mà parser nhận diện:
- Keyword.
- Identifier.
- Literal.
- Operator.
- Punctuation.
- Comment.
- Whitespace.

Ví dụ:

~~~text
let quantity = 3 + 2
~~~

Có thể được chia thành các token let, quantity, =, 3, +, 2.

### 3.2. Cú pháp (syntax)

Cú pháp quy định cách token kết hợp thành biểu thức hoặc câu lệnh hợp lệ.

Ví dụ, grammar có thể yêu cầu khai báo biến theo dạng:

~~~text
let <identifier> = <expression>
~~~

Khi người học viết thiếu tên biến hoặc thiếu dấu bằng, parser có thể báo lỗi cú pháp.

### 3.3. Ngữ nghĩa (semantics)

Ngữ nghĩa giải thích chương trình có ý nghĩa gì khi được thực thi. Cùng một cú pháp có thể có semantics khác nhau trong các DSL khác nhau.

Ví dụ a + b có thể là phép cộng số, nối chuỗi hoặc phép toán trên kiểu vector tùy kiểu của hai operand.

### 3.4. Kiểu dữ liệu (types)

Type system quy định loại giá trị mà biểu thức có thể tạo ra và thao tác nào được phép.

### 3.5. Standard library và built-in

DSL có thể cung cấp function, operator, type và module có sẵn, ví dụ:
- String functions.
- Date/time functions.
- Collection operations.
- Math functions.
- Query operators.
- Workflow actions.

### 3.6. Runtime hoặc execution engine

Runtime thực hiện chương trình DSL hoặc chương trình đã được compile. Nó có thể quản lý memory, state, I/O, transaction, scheduling và error handling.

### 3.7. Tooling

Tooling gồm editor support, syntax highlighting, formatter, linter, validator, debugger, language server, compiler và tài liệu.

## 4. Đọc tài liệu DSL theo thứ tự nào?

Khi bắt đầu một ngôn ngữ mới, không nên đọc mọi trang từ đầu đến cuối mà không có mục tiêu. Hãy tìm những phần giúp viết và chạy được chương trình nhỏ trước.

Một thứ tự hữu ích:

1. Overview: ngôn ngữ giải quyết bài toán gì?
2. Installation hoặc setup: cần cài công cụ nào?
3. Quick start: chương trình nhỏ nhất có thể chạy.
4. Syntax: cách viết khai báo và biểu thức.
5. Types: kiểu dữ liệu và chuyển đổi.
6. Expressions và control flow: tính toán và điều khiển.
7. Built-in operations: thư viện và function.
8. Errors: cách hiểu thông báo lỗi.
9. Examples: các chương trình đại diện.
10. Reference: tra cứu chi tiết khi cần.

### 4.1. Phân biệt tutorial và reference

- Tutorial dẫn người học qua một quy trình.
- Reference liệt kê cú pháp, kiểu, function và option.
- Concept guide giải thích cách suy nghĩ hoặc mô hình của DSL.
- Example project cho thấy các thành phần phối hợp trong một bài toán thực tế.

Người mới thường cần tutorial trước, sau đó dùng reference như từ điển.

### 4.2. Đọc ví dụ chủ động

Với mỗi ví dụ:
- Xác định input.
- Dự đoán output trước khi chạy.
- Gạch chân keyword và identifier.
- Thử thay một giá trị.
- Quan sát lỗi khi xóa một thành phần.
- Giải thích vì sao kết quả thay đổi.

Đọc chủ động giúp hiểu semantics thay vì chỉ sao chép cú pháp.

### 4.3. Ghi chú những quy tắc dễ nhầm

Nên ghi riêng:
- Operator precedence.
- Null behavior.
- Kiểu mặc định của literal.
- Quy tắc scope.
- Thứ tự đánh giá.
- Giá trị mặc định.
- Quy tắc lỗi và retry.

Đây là những chi tiết thường gây lỗi khi chương trình lớn dần.

## 5. Chuẩn bị môi trường học tập

Môi trường cụ thể tùy DSL và toolchain. Trước khi viết chương trình, xác định các thành phần cần thiết.

### 5.1. Thành phần thường gặp

- Editor hoặc IDE.
- Runtime hoặc compiler.
- SDK nếu DSL phụ thuộc nền tảng.
- CLI để validate, compile hoặc execute.
- Plugin syntax highlighting.
- Formatter hoặc linter.
- Sample project.
- Bộ test hoặc playground.

### 5.2. Kiểm tra cài đặt

Một toolchain thường cung cấp lệnh xem version hoặc trợ giúp:

~~~bash
dsl --version
dsl --help
~~~

Đây là tên lệnh giả định để minh họa. Hãy dùng tên CLI trong tài liệu của DSL đang học.

### 5.3. Tổ chức thư mục

Một project học tập đơn giản có thể có cấu trúc:

~~~text
dsl-learning/
├── README.md
├── examples/
│   ├── hello.dsl
│   ├── expressions.dsl
│   └── conditions.dsl
├── exercises/
│   ├── exercise-01.dsl
│   └── exercise-02.dsl
└── notes/
    └── concepts.md
~~~

Giữ ví dụ nhỏ và đặt tên phản ánh nội dung giúp dễ tìm lại.

### 5.4. Tách môi trường học và môi trường thật

Không dùng credential production hoặc dữ liệu khách hàng thật trong bài tập. Nếu DSL có thể gọi API, database hoặc workflow thật, hãy dùng sandbox, mock service hoặc dữ liệu giả lập.

### 5.5. Lưu phiên bản

Ghi lại version compiler/runtime và cấu hình dùng cho bài tập. Một ví dụ có thể thay đổi hành vi khi DSL hoặc runtime nâng version.

## 6. Chương trình đầu tiên

Ví dụ sau dùng cú pháp giả định để minh họa một DSL dạng khai báo.

~~~text
program "hello" {
    print("Hello, DSL!")
}
~~~

Chương trình có:
- program: khai báo một chương trình.
- "hello": tên chương trình.
- print: thao tác xuất dữ liệu.
- Chuỗi literal: nội dung được in ra.

Output mong đợi:

~~~text
Hello, DSL!
~~~

Cú pháp thực tế của DSL đang học có thể khác. Điều cần hiểu là cách khai báo một đơn vị chương trình, gọi operation và quan sát kết quả.

### 6.1. Thay đổi chương trình

Thử đổi chuỗi thành:

~~~text
print("My first program")
~~~

Chạy lại và quan sát output. Sau đó thử:
- Xóa dấu ngoặc đóng.
- Xóa dấu nháy.
- Đổi print thành một tên không tồn tại.
- Truyền hai argument thay vì một.

Mỗi thay đổi có thể tạo một loại lỗi khác nhau.

### 6.2. Đọc output và exit status

Một CLI thường hiển thị kết quả hoặc lỗi và trả exit code. Exit code 0 thường biểu thị thành công; mã khác 0 thường biểu thị lỗi. Tuy nhiên, quy ước cụ thể cần theo toolchain.

### 6.3. Chạy và kiểm tra

Một quy trình cơ bản:
1. Lưu file.
2. Chạy validator hoặc compiler.
3. Đọc lỗi nếu có.
4. Sửa một lỗi tại một thời điểm.
5. Chạy lại.
6. Ghi lại kết quả mong đợi và thực tế.

## 7. Biến và giá trị

Biến là tên được dùng để tham chiếu đến một giá trị.

~~~text
let language = "DSL"
let year = 2026
let isReady = true

print(language)
print(year)
print(isReady)
~~~

Một số DSL dùng let, var, set hoặc cú pháp khai báo khác.

### 7.1. Immutable và mutable

- Immutable binding không thể được gán lại sau khi tạo.
- Mutable binding có thể thay đổi giá trị trong phạm vi cho phép.

Ví dụ giả định:

~~~text
let taxRate = 0.1
var quantity = 2

quantity = quantity + 1
~~~

Ưu tiên giá trị bất biến khi không cần cập nhật giúp chương trình dễ suy luận hơn.

### 7.2. Scope

Scope xác định nơi một tên có thể được sử dụng:
- Global scope.
- Module scope.
- Function scope.
- Block scope.
- Local scope.

Một biến được khai báo trong block có thể không tồn tại bên ngoài block đó.

### 7.3. Naming

Tên biến nên phản ánh ý nghĩa. customerCount thường dễ hiểu hơn x khi lưu số khách hàng. Tránh tên quá dài hoặc chứa thông tin không liên quan.

### 7.4. Literal

Literal là giá trị được viết trực tiếp trong source:
- 42: integer literal.
- 3.14: decimal hoặc floating literal tùy DSL.
- "hello": string.
- true: Boolean.
- null: giá trị không có nếu DSL hỗ trợ.

## 8. Kiểu dữ liệu thường gặp

| Kiểu | Mô tả | Ví dụ |
|---|---|---|
| Integer | Số nguyên | 42 |
| Decimal / Float | Số có phần thập phân | 12.5 |
| Boolean | Đúng hoặc sai | true |
| String | Chuỗi ký tự | "hello" |
| Date | Ngày lịch | 2026-11-15 |
| DateTime / Instant | Thời điểm | 2026-11-15T10:30:00Z |
| Enum | Tập giá trị đặt tên | PENDING |
| List / Array | Tập giá trị có thứ tự | [1, 2, 3] |
| Map / Object | Tập cặp key-value | {name: "An"} |
| Optional / Nullable | Giá trị có thể không tồn tại | null hoặc None |

### 8.1. Kiểu tĩnh và kiểu động

- Static typing kiểm tra kiểu trước khi chạy hoặc trước khi sinh code.
- Dynamic typing xác định hoặc kiểm tra kiểu tại runtime.

Một số DSL kết hợp hai cách: schema tĩnh cho dữ liệu chính và giá trị động cho một số phần mở rộng.

### 8.2. Type inference

Compiler có thể suy luận kiểu từ biểu thức:

~~~text
let count = 10
~~~

Nếu DSL suy luận count là integer, người dùng không cần khai báo kiểu tường minh. Nhưng trong API hoặc schema quan trọng, khai báo kiểu rõ có thể giúp tài liệu và validation tốt hơn.

### 8.3. Type conversion

Chuyển đổi kiểu có thể là:
- Implicit: compiler tự thực hiện.
- Explicit: người dùng yêu cầu rõ.
- Safe conversion: không mất thông tin theo quy tắc kiểu.
- Narrowing conversion: có thể mất range hoặc precision.

Không nên giả định mọi kiểu số có thể chuyển đổi an toàn.

### 8.4. Null và optional

Optional và nullable không giống nhau. Optional nói một field có thể vắng mặt; nullable nói field có thể chứa giá trị null. Cần đọc semantics của DSL trước khi dùng.

## 9. Biểu thức và toán tử

Biểu thức (expression) tính ra một giá trị. Toán tử kết hợp operand để tạo biểu thức mới.

### 9.1. Số học

~~~text
let subtotal = unitPrice * quantity
let total = subtotal + shippingFee
let average = total / itemCount
~~~

Các toán tử phổ biến: +, -, *, /, %.

### 9.2. So sánh

~~~text
age >= 18
status == "ACTIVE"
balance != 0
~~~

Kết quả thường là Boolean, nhưng một DSL có thể hỗ trợ logic ba giá trị khi có null.

### 9.3. Logic

~~~text
isActive and hasPermission
isAdmin or isOwner
not isBlocked
~~~

Một số DSL dùng &&, ||, ! thay cho and, or, not.

### 9.4. Precedence

Precedence xác định toán tử nào được đánh giá trước:

~~~text
a + b * c
~~~

Thông thường phép nhân được thực hiện trước phép cộng. Dùng ngoặc để làm rõ ý định:

~~~text
(a + b) * c
~~~

### 9.5. Short-circuit

Với biểu thức AND hoặc OR có short-circuit, operand thứ hai có thể không được đánh giá nếu kết quả đã xác định. Không đặt side effect vào biểu thức nếu chưa hiểu rõ quy tắc này.

### 9.6. String expression

DSL có thể hỗ trợ nối chuỗi, template hoặc interpolation:

~~~text
message = "Hello, " + customer.name
~~~

Cần chú ý escaping, Unicode và cách xử lý null.

## 10. Cấu trúc điều khiển

Cấu trúc điều khiển quyết định câu lệnh nào được thực thi.

### 10.1. Điều kiện if/else

~~~text
if score >= 80 {
    result = "PASS"
} else {
    result = "REVIEW"
}
~~~

Điều kiện phải có kiểu phù hợp, thường là Boolean.

### 10.2. Nhiều nhánh

~~~text
match order.status {
    PENDING -> processPending(order)
    PAID -> prepareShipment(order)
    CANCELLED -> archiveOrder(order)
    otherwise -> reportUnknownStatus(order)
}
~~~

Pattern matching có thể giúp xử lý enum hoặc cấu trúc dữ liệu rõ hơn chuỗi if/else dài.

### 10.3. Vòng lặp

~~~text
for item in items {
    print(item.name)
}
~~~

Một số DSL hỗ trợ while, repeat hoặc vòng lặp theo range. Cần hiểu điều kiện dừng và khả năng tạo vòng lặp vô hạn.

### 10.4. Break và continue

- break thoát vòng lặp hiện tại.
- continue chuyển sang iteration tiếp theo.

Nếu DSL không hỗ trợ hai từ khóa này, có thể dùng filter hoặc cấu trúc khác.

### 10.5. Recursion

Recursion là function tự gọi lại chính nó. Cần có base case để dừng và giới hạn độ sâu nếu runtime không tối ưu tail call.

## 11. Hàm và tái sử dụng logic

Function gom một phần logic thành đơn vị có tên, input và output.

~~~text
function calculateTotal(unitPrice: Decimal, quantity: Integer): Decimal {
    return unitPrice * quantity
}

let total = calculateTotal(125000, 2)
~~~

### 11.1. Parameter và return value

Parameter là dữ liệu truyền vào function. Return value là kết quả function trả về. Một số DSL có procedure hoặc action không trả giá trị.

### 11.2. Pure function

Pure function cho cùng input thì cùng output và không tạo side effect. Function thuần dễ test, cache và tối ưu hơn.

### 11.3. Side effect

Side effect có thể gồm:
- Ghi dữ liệu.
- Gửi message.
- Gọi API.
- In log.
- Thay đổi state.
- Đọc thời gian hiện tại.

Cần nhận diện side effect để biết function nào có thể chạy lại hoặc được tối ưu.

### 11.4. Reuse và abstraction

Tách logic lặp lại thành function giúp tránh copy-paste. Tuy nhiên, không nên tạo quá nhiều abstraction nhỏ đến mức người đọc phải nhảy qua nhiều định nghĩa để hiểu một thao tác đơn giản.

## 12. Cấu trúc dữ liệu và collection

DSL thường cung cấp list, map, record, object hoặc table.

### 12.1. List

~~~text
let scores = [75, 90, 82]
let firstScore = scores[0]
~~~

Cần xác định index bắt đầu từ 0 hay 1 và hành vi khi truy cập ngoài phạm vi.

### 12.2. Map

~~~text
let customer = {
    id: "CUS-1042",
    name: "Nguyen An",
    active: true
}
~~~

Map thường ánh xạ key sang value. Record hoặc object có thể có schema và kiểu field cố định.

### 12.3. Collection operations

Các operation phổ biến:
- map: biến đổi từng phần tử.
- filter: giữ phần tử thỏa điều kiện.
- reduce: tổng hợp collection thành một giá trị.
- find: tìm phần tử đầu tiên phù hợp.
- any: kiểm tra có ít nhất một phần tử phù hợp.
- all: kiểm tra mọi phần tử phù hợp.

Ví dụ:

~~~text
let activeNames =
    customers
        .filter(customer.active)
        .map(customer.name)
~~~

### 12.4. Mutation và immutability

Một operation có thể tạo collection mới hoặc thay đổi collection hiện tại. Cần hiểu điều này để tránh vô tình sửa dữ liệu dùng chung.

### 12.5. Lazy và eager evaluation

Eager evaluation tính ngay kết quả collection. Lazy evaluation trì hoãn tính toán cho đến khi cần. Lazy có thể tiết kiệm bộ nhớ nhưng có thể khiến một biểu thức chạy nhiều lần nếu không cache.

## 13. Một số họ DSL thường gặp trong khoa học máy tính

Không có một cú pháp chung cho mọi DSL. Tuy nhiên, nhiều DSL có thể được nhóm theo mục đích.

### 13.1. Query DSL

Query DSL mô tả cách tìm, lọc, kết hợp và tổng hợp dữ liệu.

~~~text
orders
    .filter(status == "PAID")
    .groupBy(customerId)
    .sum(total)
~~~

Cần hiểu schema, predicate, null logic, join và pagination.

### 13.2. Rule DSL

Rule DSL mô tả điều kiện và hành động:

~~~text
rule "adult_customer" {
    when customer.age >= 18
    then markEligible(customer)
}
~~~

Cần hiểu activation, priority, conflict resolution và side effect.

### 13.3. Workflow DSL

Workflow DSL mô tả các bước và quan hệ thực thi:

~~~text
workflow "onboard_customer" {
    step verifyIdentity
    step createAccount
    step sendWelcomeMessage
}
~~~

Cần hiểu state, transition, branch, retry, timeout và compensation.

### 13.4. API DSL

API DSL mô tả endpoint, schema, request và response:

~~~text
operation getCustomer {
    method = GET
    path = "/customers/{customerId}"
    response 200: Customer
}
~~~

Cần hiểu contract, versioning, validation và authentication.

### 13.5. Integration DSL

Integration DSL mô tả cách kết nối service hoặc ứng dụng:

~~~text
connector "billing" {
    endpoint = config.billingUrl
    timeout = 5 seconds
    call billing.createInvoice(order)
}
~~~

Cần hiểu protocol, credentials, retry, idempotency và error mapping.

### 13.6. Configuration và build DSL

Các DSL này mô tả dependency, build step, deployment hoặc cấu hình. Người học cần phân biệt khai báo cấu hình với logic có thể thực thi.

## 14. Từ source đến kết quả: parser, AST và runtime

Khi một DSL được thực thi, source text thường đi qua nhiều bước.

### 14.1. Parsing

Parser kiểm tra source có đúng grammar không và tạo cấu trúc nội bộ.

### 14.2. Abstract Syntax Tree

AST biểu diễn cấu trúc chương trình. Ví dụ:

~~~text
let total = price * quantity
~~~

Có thể được biểu diễn khái quát:

~~~text
VariableDeclaration
  name: total
  initializer:
    Multiply
      Identifier: price
      Identifier: quantity
~~~

### 14.3. Semantic analysis

Compiler kiểm tra:
- Tên có được khai báo không?
- Kiểu hai operand có tương thích không?
- Function có tồn tại không?
- Có quyền gọi operation đó không?
- Control flow có hợp lệ không?

### 14.4. Intermediate representation

IR biểu diễn chương trình theo dạng dễ phân tích và tối ưu hơn source syntax.

### 14.5. Interpretation và compilation

- Interpreter đọc cấu trúc DSL và thực hiện trực tiếp.
- Compiler chuyển DSL thành code hoặc bytecode rồi runtime thực thi.

Một hệ thống có thể kết hợp cả hai, ví dụ compile một số biểu thức và interpret các phần còn lại.

### 14.6. Generated code

Generated code có thể là Java, bytecode, SQL, JavaScript, native code hoặc instruction riêng. Người dùng DSL thường không cần sửa code sinh trực tiếp, nhưng nên biết cách xem nó khi debug hoặc tối ưu.

## 15. Chạy, kiểm tra và lặp lại

Một quy trình học hiệu quả là vòng lặp nhỏ:

~~~text
Viết một thay đổi nhỏ
        |
        v
Validate / Compile
        |
        v
Chạy chương trình
        |
        v
Quan sát kết quả
        |
        v
So sánh với dự đoán
        |
        v
Sửa và thử lại
~~~

### 15.1. Validate trước khi chạy

Nếu toolchain có validator, hãy chạy nó để phát hiện lỗi cú pháp, kiểu và contract trước runtime.

### 15.2. Dùng input nhỏ

Bắt đầu với một hoặc hai record. Input nhỏ giúp dễ dự đoán output và xác định nguyên nhân khi kết quả sai.

### 15.3. Thay một yếu tố mỗi lần

Khi thử nghiệm, chỉ đổi một biểu thức hoặc một giá trị. Nếu đổi nhiều thứ cùng lúc, khó biết thay đổi nào gây ra kết quả.

### 15.4. Ghi expected và actual output

Viết kết quả mong đợi trước khi chạy. Sau đó so sánh với output thật. Đây là cách đơn giản để phát hiện hiểu sai semantics.

### 15.5. Lưu ví dụ tối thiểu

Khi gặp bug, tạo một ví dụ nhỏ nhất vẫn tái hiện lỗi. Minimal reproduction giúp debug nhanh và có thể trở thành regression test.

## 16. Nhận diện các loại lỗi

Không phải lỗi nào cũng có cùng nguyên nhân hoặc cách sửa.

| Loại lỗi | Thời điểm thường xuất hiện | Ví dụ |
|---|---|---|
| Lexical error | Phân tích token | Ký tự không hợp lệ |
| Syntax error | Parsing | Thiếu dấu ngoặc |
| Name resolution error | Phân tích tên | Dùng biến chưa khai báo |
| Type error | Kiểm tra kiểu | Cộng số với object không hỗ trợ |
| Semantic error | Kiểm tra ngữ nghĩa | Dùng operation sai trạng thái |
| Runtime error | Khi chạy | Chia cho 0, timeout |
| Integration error | Gọi hệ thống ngoài | API trả 503 |
| Logic error | Kết quả sai nhưng chương trình chạy | Điều kiện nghiệp vụ viết ngược |

### 16.1. Đọc thông báo lỗi

Khi nhận lỗi, hãy tìm:
- Error code.
- Message.
- File hoặc module.
- Dòng và cột.
- Source span.
- Expected token hoặc type.
- Cause chain.
- Correlation ID nếu lỗi runtime/integration.

### 16.2. Sửa lỗi từ nguyên nhân đầu tiên

Một lỗi parser có thể gây nhiều lỗi tiếp theo. Hãy sửa lỗi đầu tiên hoặc lỗi gốc rồi chạy lại, thay vì cố sửa tất cả thông báo cùng lúc.

### 16.3. Phân biệt lỗi compiler và lỗi chương trình

Compiler báo type mismatch khác với chương trình chạy thành công nhưng tính sai kết quả. Một trường hợp cần sửa source hoặc schema; trường hợp kia cần kiểm tra logic.

## 17. Debug một chương trình DSL

Debug là quá trình xác định trạng thái và bước khiến chương trình có hành vi không mong đợi.

### 17.1. Bắt đầu từ một ví dụ tái hiện

Ghi lại source DSL, input, cấu hình, version runtime, expected output, actual output và error hoặc trace.

### 17.2. Kiểm tra từng lớp

Nếu chương trình có compiler:
1. Xem source.
2. Xem AST hoặc diagnostic.
3. Xem IR nếu có.
4. Xem generated code nếu cần.
5. Quan sát runtime behavior.

Không cần kiểm tra mọi lớp cho mọi lỗi. Bắt đầu từ thông tin lỗi chỉ ra.

### 17.3. Logging

Log giúp ghi nhận các mốc thực thi. Nên log dữ liệu đủ để điều tra nhưng không ghi secret hoặc dữ liệu nhạy cảm không cần thiết.

### 17.4. Breakpoint và stepping

Nếu debugger hỗ trợ DSL source mapping, đặt breakpoint tại DSL line và chạy từng bước. Nếu chỉ debug generated code, dùng source map hoặc metadata để liên kết về DSL.

### 17.5. Inspect state

Quan sát biến, context, current workflow step hoặc query result ở từng điểm. Kiểm tra giả định về input trước khi kết luận compiler sai.

### 17.6. Debug integration

Khi DSL gọi service ngoài, lưu correlation ID, request ID, operation, duration và error code. Phân biệt lỗi từ DSL, adapter, network và provider.

## 18. Viết chương trình nhỏ theo từng bước

Một cách học tốt là bắt đầu từ bài toán cụ thể rồi mở rộng dần.

Giả sử cần phân loại đơn hàng theo tổng tiền.

### Bước 1: Xác định input

~~~text
order.total: Decimal
~~~

### Bước 2: Xác định quy tắc

- Tổng tiền từ 1.000.000 trở lên: nhóm HIGH_VALUE.
- Còn lại: nhóm STANDARD.

### Bước 3: Viết biểu thức

~~~text
if order.total >= 1000000 {
    category = "HIGH_VALUE"
} else {
    category = "STANDARD"
}
~~~

### Bước 4: Thử dữ liệu biên

| Input | Expected |
|---:|---|
| 0 | STANDARD |
| 999999 | STANDARD |
| 1000000 | HIGH_VALUE |
| 1000001 | HIGH_VALUE |

### Bước 5: Thử dữ liệu không hợp lệ

Nếu order.total là null hoặc âm, chương trình xử lý thế nào? Bổ sung validation hoặc quy tắc phù hợp với domain.

### Bước 6: Tách thành function

~~~text
function classifyOrder(total: Decimal): String {
    if total >= 1000000 {
        return "HIGH_VALUE"
    }
    return "STANDARD"
}
~~~

### Bước 7: Kiểm thử

Gọi function với các giá trị biên và xác nhận kết quả. Sau đó thử gọi từ workflow hoặc API operation nếu DSL hỗ trợ.

## 19. Tư duy thiết kế: mô tả ý định trước khi chọn cú pháp

Một DSL được thiết kế để thể hiện ý định. Khi học, hãy diễn đạt bài toán bằng ngôn ngữ tự nhiên trước.

Ví dụ: “Lấy các đơn đã thanh toán trong tháng, nhóm theo khách hàng và tính tổng tiền.”

Sau đó xác định:
- Nguồn dữ liệu: orders.
- Điều kiện: status = PAID.
- Khoảng thời gian: trong tháng.
- Nhóm: customerId.
- Phép tổng hợp: sum(total).

Rồi mới viết DSL:

~~~text
orders
    .filter(status == "PAID")
    .filter(createdAt in currentMonth())
    .groupBy(customerId)
    .sum(total)
~~~

Cách làm này giúp tránh chọn cú pháp trước khi hiểu bài toán.

### 19.1. Xác định input và output

Mọi chương trình nên có input và output rõ. Nếu không biết output mong đợi, rất khó xác định chương trình đúng hay sai.

### 19.2. Xác định invariant

Invariant là điều kiện luôn phải đúng, ví dụ quantity phải lớn hơn 0 hoặc một đơn hàng đã hoàn tất không thể quay lại trạng thái NEW.

### 19.3. Xác định side effect

Ghi rõ thao tác nào chỉ tính toán và thao tác nào thay đổi hệ thống. Điều này quan trọng với retry, test và tối ưu hóa.

### 19.4. Xác định lỗi

Nêu trước điều gì xảy ra khi thiếu dữ liệu, sai kiểu, resource không tồn tại hoặc service ngoài không phản hồi.

## 20. Thực hành và xây dựng thói quen học

Học DSL cần thực hành ngắn, đều đặn và có phản hồi.

### 20.1. Từ ví dụ đến biến thể

Với mỗi ví dụ:
1. Chạy nguyên bản.
2. Thay literal.
3. Thêm một điều kiện.
4. Thêm một trường dữ liệu.
5. Cố ý tạo lỗi.
6. Giải thích sự khác biệt.

### 20.2. Bài tập theo mức độ

- Mức 1: đọc và dự đoán output.
- Mức 2: sửa một biểu thức.
- Mức 3: viết một function hoặc query.
- Mức 4: kết hợp nhiều cấu trúc.
- Mức 5: xử lý lỗi và dữ liệu biên.
- Mức 6: tối ưu, kiểm thử và giải thích trade-off.

### 20.3. Tự giải thích

Sau khi hoàn thành bài tập, viết vài câu:
- Bài toán cần giải quyết là gì?
- DSL biểu diễn bài toán ra sao?
- Vì sao chọn cấu trúc đó?
- Input đặc biệt nào cần kiểm tra?
- Giới hạn hoặc giả định nào còn lại?

### 20.4. Xem lại lỗi cũ

Ghi lại lỗi, nguyên nhân và cách sửa. Sau một thời gian, nhóm lỗi theo cú pháp, kiểu, logic, runtime và integration để nhận ra khuynh hướng.

### 20.5. Tạo portfolio nhỏ

Lưu một số chương trình:
- Query dữ liệu.
- Rule phân loại.
- Workflow đơn giản.
- API contract.
- Integration có retry.
- Ví dụ có test.

Một portfolio nhỏ giúp thể hiện khả năng áp dụng DSL trong nhiều ngữ cảnh.

## 21. Làm việc với ví dụ và dữ liệu an toàn

Bài tập nên dùng dữ liệu giả lập.

### 21.1. Dữ liệu mẫu

~~~text
customers = [
    {id: "C-1", name: "An", active: true},
    {id: "C-2", name: "Binh", active: false},
    {id: "C-3", name: "Chi", active: true}
]
~~~

### 21.2. Không dùng thông tin thật

Không đưa password, token, số thẻ, dữ liệu cá nhân hoặc nội dung production vào bài tập và log.

### 21.3. Kiểm tra tác dụng phụ

Nếu DSL có thể gửi email, tạo giao dịch hoặc ghi database, hãy dùng mock hoặc sandbox. Đọc kỹ thao tác trước khi chạy trên môi trường thật.

### 21.4. Quản lý secret

Secret nên được cấp qua cơ chế quản lý credential của môi trường. Không hardcode trong source hoặc commit vào repository.

## 22. Làm việc nhóm và quản lý source DSL

Một chương trình DSL cũng cần được quản lý như source code.

### 22.1. Version control

Lưu file DSL trong Git hoặc hệ thống version control tương đương. Commit nên mô tả thay đổi về hành vi, không chỉ ghi update.

### 22.2. Code review

Reviewer có thể kiểm tra:
- Bài toán và điều kiện.
- Input/output.
- Type và validation.
- Side effect.
- Error handling.
- Test cases.
- Hiệu năng nếu liên quan.

### 22.3. Formatter

Formatter giúp source thống nhất về indentation, quote style, line break và cách trình bày block.

### 22.4. Linter

Linter có thể phát hiện biến không dùng, nhánh unreachable, expression nguy hiểm, query không giới hạn hoặc cấu hình thiếu timeout.

### 22.5. Tài liệu hóa

Mỗi module hoặc workflow nên có mô tả mục đích, input, output, dependency, error behavior và ví dụ.

## 23. Kiểm thử chương trình DSL

Test xác nhận chương trình hoạt động theo contract.

### 23.1. Unit test

Kiểm tra một expression, function hoặc rule riêng biệt.

### 23.2. Boundary test

Kiểm tra giá trị ngay dưới, đúng bằng và ngay trên ngưỡng. Ví dụ age 17, 18 và 19 khi điều kiện là age >= 18.

### 23.3. Negative test

Dùng input thiếu field, sai kiểu, null hoặc giá trị ngoài range để kiểm tra validation.

### 23.4. Integration test

Kiểm tra DSL với database, API hoặc message broker. Nên dùng sandbox hoặc test double nếu không cần gọi hệ thống thật.

### 23.5. Regression test

Khi thay đổi rule hoặc query, chạy lại các case cũ để bảo đảm hành vi không bị thay đổi ngoài dự kiến.

### 23.6. Property-based test

Sinh nhiều input và kiểm tra invariant, ví dụ tổng số phần tử sau filter không vượt số phần tử đầu vào.

### 23.7. Snapshot test

Với output có cấu trúc, snapshot test có thể phát hiện thay đổi. Cần review snapshot mới để tránh chấp nhận thay đổi sai một cách máy móc.

## 24. Hiệu năng ở mức nhập môn

Người mới chưa cần tối ưu sớm, nhưng nên hiểu một số nguyên tắc.

### 24.1. Đo trước khi tối ưu

Không suy đoán bottleneck từ số dòng source. Dùng benchmark và profiler khi chương trình có yêu cầu hiệu năng.

### 24.2. Tránh công việc thừa

- Không đọc dữ liệu nhiều lần nếu có thể dùng lại kết quả an toàn.
- Chỉ lấy field cần thiết.
- Dùng batch khi API hỗ trợ.
- Giới hạn collection và query result.
- Tránh vòng lặp không có điều kiện dừng.

### 24.3. Hiểu chi phí I/O

Một lời gọi network hoặc database thường đắt hơn nhiều phép tính số học. Giảm round trip có thể có tác động lớn hơn tối ưu một expression nhỏ.

### 24.4. Hiểu code generation

Nếu DSL compile thành code, hãy tìm cách xem IR hoặc code sinh khi cần. Không chỉnh sửa artifact sinh trực tiếp nếu toolchain sẽ tạo lại nó.

### 24.5. Giữ chương trình dễ hiểu

Tối ưu quá sớm có thể làm source khó đọc và khó sửa. Ưu tiên tính đúng, sau đó đo và tối ưu phần thực sự quan trọng.

## 25. Những lỗi thường gặp của người mới

### 25.1. Học thuộc cú pháp mà không hiểu semantics

Biết viết filter chưa đủ; cần hiểu predicate được đánh giá khi nào, null được xử lý ra sao và kết quả có được tính ngay không.

### 25.2. Bỏ qua kiểu dữ liệu

Một giá trị "10" là string, còn 10 có thể là integer. So sánh hoặc cộng hai kiểu này có thể không hợp lệ hoặc có kết quả khác.

### 25.3. Không đọc error message

Thông báo lỗi thường chỉ rõ file, vị trí và expected type/token. Đọc phần đầu tiên của lỗi trước khi sửa source.

### 25.4. Thay đổi quá nhiều thứ cùng lúc

Khi có lỗi, thay từng phần và chạy lại để tìm nguyên nhân.

### 25.5. Dùng dữ liệu quá lớn khi chưa hiểu chương trình

Bắt đầu với input nhỏ. Khi kết quả đúng, tăng quy mô để kiểm tra hiệu năng và giới hạn.

### 25.6. Không kiểm tra giá trị biên

Các lỗi thường xuất hiện tại null, empty list, zero, negative number, maximum value và thời điểm chuyển ngày.

### 25.7. Nhầm lỗi runtime với lỗi logic

Chương trình chạy không lỗi không có nghĩa kết quả đúng. Luôn có expected output hoặc invariant để đối chiếu.

### 25.8. Copy ví dụ mà không thay đổi

Hãy sửa ví dụ và dự đoán kết quả. Nếu chỉ copy, người học khó biết mình đã hiểu hay chưa.

### 25.9. Bỏ qua version

Cú pháp hoặc runtime behavior có thể thay đổi giữa các version. Kiểm tra tài liệu đúng version đang dùng.

### 25.10. Không ghi lại cách tái hiện

Khi hỏi trợ giúp, cung cấp source nhỏ, input, output mong đợi, output thực tế và version toolchain. Điều này giúp người khác hỗ trợ chính xác hơn.

## 26. Lộ trình học đề xuất

Một lộ trình có thể chia thành các giai đoạn.

| Giai đoạn | Nội dung | Kết quả mong đợi |
|---|---|---|
| 1. Làm quen | DSL, môi trường, chương trình đầu tiên | Chạy được ví dụ cơ bản |
| 2. Cú pháp | Token, grammar, biến, expression | Đọc và viết source đơn giản |
| 3. Kiểu dữ liệu | Primitive, collection, record, null | Xác định input/output đúng kiểu |
| 4. Điều khiển | Condition, loop, function | Xây logic có cấu trúc |
| 5. Mô hình miền | Query, rule, workflow hoặc API | Diễn đạt một use case thực tế |
| 6. Lỗi | Validation, runtime, integration error | Xử lý tình huống bất thường |
| 7. Kiểm thử | Unit, boundary, integration, regression | Chứng minh hành vi |
| 8. Hiệu năng | Profiling, query plan, code generation | Tìm và giải quyết bottleneck |
| 9. Dự án | Kết hợp nhiều thành phần | Xây một ứng dụng nhỏ hoàn chỉnh |

### 26.1. Mốc hoàn thành cơ bản

Người học có thể:
- Đọc một ví dụ DSL và giải thích từng thành phần.
- Viết chương trình ngắn với biến và biểu thức.
- Dùng điều kiện và collection.
- Nhận diện lỗi cú pháp và kiểu.
- Chạy test đơn giản.

### 26.2. Mốc ứng dụng

Người học có thể xây query, rule hoặc workflow nhỏ, dùng schema, xử lý lỗi và viết test.

### 26.3. Mốc nâng cao

Người học có thể đọc IR hoặc generated code, đánh giá optimization, thiết kế integration contract và phân tích trade-off runtime.

## 27. Bài tập thực hành

Các bài tập dưới đây dùng cú pháp minh họa. Hãy chuyển sang cú pháp thực tế của DSL đang học.

### Bài 1: Hello

Viết chương trình in ra tên DSL và một câu chào. Giải thích token và câu lệnh được sử dụng.

### Bài 2: Tính toán

Khai báo price và quantity, tính subtotal và in kết quả. Thử quantity bằng 0 và số âm.

### Bài 3: Phân loại

Viết điều kiện phân loại một số là âm, bằng 0 hoặc dương. Kiểm tra các giá trị biên.

### Bài 4: Collection

Cho danh sách số, lọc số chẵn và tính tổng. So sánh kết quả bằng vòng lặp và collection pipeline.

### Bài 5: Function

Viết function tính tổng có thuế. Xác định kiểu input, output và rounding rule.

### Bài 6: Record

Tạo record Customer với id, name và active. Viết biểu thức lấy các khách hàng active.

### Bài 7: Query

Từ danh sách orders, lọc đơn đã thanh toán và nhóm theo customerId.

### Bài 8: Rule

Viết rule đánh dấu đơn cần review nếu total vượt ngưỡng hoặc riskScore cao.

### Bài 9: Workflow

Mô tả quy trình tạo đơn gồm validate, reserve inventory, authorize payment và confirm. Xác định hành vi khi thanh toán lỗi.

### Bài 10: Error handling

Tạo một integration call giả lập timeout. Thiết kế retry có giới hạn và nhánh manual review khi hết retry.

### Bài 11: Test

Viết các test cho giá trị bình thường, null, empty list và giá trị sát ngưỡng.

### Bài 12: Giải thích chương trình

Chọn một ví dụ đã viết và giải thích input, output, semantics, side effect, lỗi có thể xảy ra và cách kiểm thử.

## 28. Bảng thuật ngữ nhập môn

| Thuật ngữ | Ý nghĩa |
|---|---|
| DSL | Ngôn ngữ chuyên biệt cho một miền |
| Domain | Lĩnh vực hoặc nhóm vấn đề được mô hình hóa |
| Syntax | Quy tắc hình thức của source |
| Semantics | Ý nghĩa và hành vi của chương trình |
| Token | Đơn vị từ vựng |
| Grammar | Quy tắc kết hợp token |
| Parser | Thành phần phân tích cú pháp |
| AST | Cây cú pháp trừu tượng |
| Type system | Quy tắc kiểu dữ liệu |
| Runtime | Môi trường thực thi |
| Compiler | Chuyển source sang dạng thực thi khác |
| Interpreter | Thực thi source hoặc biểu diễn trực tiếp |
| IR | Biểu diễn trung gian |
| Scope | Phạm vi có thể truy cập tên |
| Literal | Giá trị viết trực tiếp trong source |
| Expression | Cấu trúc tính ra giá trị |
| Statement | Câu lệnh thực hiện hành động |
| Side effect | Tác động quan sát được ngoài giá trị trả về |
| Validation | Kiểm tra dữ liệu hoặc contract |
| Debugging | Điều tra và sửa lỗi |
| Benchmark | Phép đo hiệu năng có kiểm soát |
| Profiling | Thu thập dữ liệu hành vi runtime |
| Optimization | Biến đổi để cải thiện một mục tiêu |
| Regression test | Test phát hiện hành vi cũ bị hỏng |

## 29. Checklist tự học

Trước khi chuyển sang chủ đề tiếp theo, người học có thể tự kiểm tra:

- [ ] Tôi giải thích được DSL giải quyết bài toán gì.
- [ ] Tôi phân biệt được DSL với ngôn ngữ đa mục đích và file cấu hình.
- [ ] Tôi biết tìm quick start, syntax reference và error guide.
- [ ] Tôi đã chạy được một chương trình nhỏ.
- [ ] Tôi hiểu biến, literal, kiểu và expression.
- [ ] Tôi dùng được condition, loop hoặc function cơ bản.
- [ ] Tôi biết input và output của chương trình.
- [ ] Tôi phân biệt lỗi syntax, type, semantic và runtime.
- [ ] Tôi có thể tạo một ví dụ tái hiện lỗi.
- [ ] Tôi biết viết test cho trường hợp bình thường và biên.
- [ ] Tôi dùng dữ liệu giả lập và quản lý secret an toàn.
- [ ] Tôi biết version compiler/runtime đang sử dụng.

## Kết luận

Học một Computer Science DSL hiệu quả bắt đầu từ việc hiểu miền vấn đề và mục đích của ngôn ngữ, sau đó tìm hiểu cú pháp, kiểu dữ liệu, semantics, runtime và công cụ hỗ trợ. Người mới nên chạy một chương trình nhỏ, thay đổi từng phần, dự đoán output và đọc lỗi theo từng lớp. Khi đã nắm biến, biểu thức, điều khiển, function và collection, có thể tiến tới query, rule, workflow, API và integration. Thực hành với input nhỏ, dữ liệu giả lập, test biên và ví dụ có thể tái hiện giúp củng cố kiến thức. Sau khi chương trình đúng, benchmark và profiling mới cho biết nơi cần tối ưu. Lộ trình từng bước này tạo nền tảng để đọc, viết, kiểm thử và áp dụng DSL vào các bài toán khoa học máy tính thực tế.

# Tài liệu ngữ nghĩa

## 1. Tài liệu ngữ nghĩa là gì?

Tài liệu ngữ nghĩa (semantic documentation) giải thích một DSL (Domain-Specific Language) có ý nghĩa gì và chương trình sẽ hành xử như thế nào khi được phân tích hoặc thực thi. Nó mô tả cách các cấu trúc cú pháp được diễn giải, các quy tắc kiểu và phạm vi, thứ tự đánh giá biểu thức, kết quả của phép toán, điều kiện lỗi và các đặc tính runtime.

Tài liệu cú pháp trả lời câu hỏi "viết cấu trúc này như thế nào?". Tài liệu ngữ nghĩa trả lời "cấu trúc đó có nghĩa gì, được đánh giá ra sao và kết quả nào được bảo đảm?".

Ví dụ, grammar có thể cho phép:

~~~text
if condition {
    approve(order)
} else {
    reject(order)
}
~~~

Nhưng chỉ grammar chưa cho biết:

- condition phải có kiểu Boolean hay có thể dùng kiểu truthy?
- Nhánh else có bắt buộc không?
- Chỉ một nhánh được thực thi hay cả hai nhánh được đánh giá?
- Nếu condition là null thì điều gì xảy ra?
- approve có thể thay đổi trạng thái bên ngoài không?
- Nếu approve phát sinh lỗi thì workflow tiếp tục hay dừng?

Tài liệu ngữ nghĩa cần trả lời các câu hỏi đó bằng quy tắc chính xác, ví dụ và giới hạn được công bố. Nó giúp developer hiểu chương trình, người thiết kế DSL giữ semantics nhất quán, và người dùng biết hành vi nào có thể dựa vào khi nâng cấp phiên bản.

## 2. Vì sao DSL cần tài liệu ngữ nghĩa?

Một DSL có thể có cú pháp ngắn nhưng hành vi phía sau khá phức tạp. Nếu chỉ mô tả grammar, người dùng có thể viết chương trình hợp lệ về cú pháp nhưng hiểu sai cách nó chạy.

Tài liệu ngữ nghĩa giúp:

1. Giải thích hành vi thực tế của keyword, expression, type, function và statement.
2. Phân biệt quy tắc được bảo đảm với chi tiết implementation.
3. Làm rõ lỗi compile-time và lỗi runtime.
4. Giúp người dùng dự đoán kết quả mà không phải đọc compiler source.
5. Giữ compiler, interpreter, optimizer và backend tuân theo cùng hợp đồng.
6. Hỗ trợ viết test và kiểm tra tương thích.
7. Làm rõ thay đổi nào là breaking change khi phát hành phiên bản mới.
8. Cung cấp thông tin chính xác cho IDE, language server và documentation generator.
9. Hạn chế hành vi phụ thuộc ngẫu nhiên vào backend hoặc môi trường.
10. Hỗ trợ onboarding và bảo trì các chương trình DSL lâu dài.

Ngữ nghĩa là một phần của hợp đồng công khai của ngôn ngữ. Nếu implementation thay đổi hành vi mà tài liệu không thay đổi, người dùng có thể gặp regression dù source vẫn compile.

## 3. Cú pháp, ngữ nghĩa và implementation

Ba khái niệm cần được phân biệt:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Syntax | Cấu trúc nào được phép viết? | if expression cần condition và block |
| Semantics | Cấu trúc hợp lệ có nghĩa gì? | Chỉ đánh giá một nhánh theo kết quả condition |
| Implementation | Compiler/runtime thực hiện bằng cách nào? | AST node được biên dịch thành conditional jump |

Syntax thường được mô tả bằng grammar, EBNF hoặc parser rule. Semantics được mô tả bằng quy tắc kiểu, evaluation rule, trạng thái và hành vi quan sát được. Implementation có thể dùng interpreter, bytecode, native code hoặc query plan.

Ví dụ, một DSL quy định:

~~~text
let total = price * quantity
~~~

Ngữ nghĩa có thể nói:

- price và quantity phải có kiểu tương thích với phép nhân.
- Kết quả có kiểu được xác định theo type rule.
- Nếu quantity là null thì kết quả là null hoặc lỗi theo null semantics.
- Phép nhân không có side effect.

Implementation có thể dùng instruction nhân số nguyên hoặc gọi decimal library. Chi tiết đó không nhất thiết phải nằm trong tài liệu ngữ nghĩa nếu nó không ảnh hưởng hợp đồng quan sát được.

## 4. Các lớp ngữ nghĩa

Tài liệu ngữ nghĩa có thể được tổ chức theo nhiều lớp:

### 4.1. Lexical semantics

Giải thích ý nghĩa của token, literal, escape, identifier và comment khi chúng ảnh hưởng cách diễn giải source.

Ví dụ:

- Identifier có phân biệt chữ hoa/chữ thường không?
- Chuỗi có hỗ trợ escape sequence nào?
- Numeric literal có hậu tố đơn vị không?
- Unicode identifier được chuẩn hóa như thế nào?

### 4.2. Static semantics

Static semantics là các quy tắc có thể kiểm tra trước khi chương trình chạy:

- Name resolution.
- Scope và visibility.
- Type checking.
- Overload resolution.
- Generic constraints.
- Kiểm tra assignment.
- Kiểm tra quyền hoặc capability tĩnh nếu DSL hỗ trợ.

### 4.3. Dynamic semantics

Dynamic semantics mô tả hành vi khi chương trình thực thi:

- Thứ tự đánh giá.
- Control flow.
- State mutation.
- Exception và error propagation.
- Concurrency và async behavior.
- I/O và side effect.
- Kết quả của function và operator.

### 4.4. Domain semantics

Domain semantics giải thích khái niệm chuyên ngành:

- Money và currency.
- Date, time và business calendar.
- Order state và transition.
- Query window và aggregation.
- Workflow event và compensation.

Một DSL tốt cần liên kết các lớp này. Ví dụ, kiểu Money có static rule về đơn vị và dynamic rule về rounding khi thực hiện phép chia.

## 5. Mô hình hóa ngữ nghĩa của DSL

Một cách tổ chức tài liệu là xác định các thành phần ngữ nghĩa chính:

- **Entities:** các đối tượng hoặc khái niệm mà DSL thao tác.
- **Expressions:** biểu thức tạo ra giá trị.
- **Statements:** cấu trúc điều khiển hoặc hành động.
- **Types:** kiểu dữ liệu và quy tắc tương thích.
- **Environment:** scope, biến, module và context.
- **State:** trạng thái có thể thay đổi trong quá trình chạy.
- **Effects:** I/O, network, database hoặc side effect.
- **Errors:** điều kiện lỗi và cách truyền lỗi.
- **Execution model:** interpreter, query engine hoặc workflow runtime ở mức hợp đồng.

Một mô hình đơn giản:

~~~text
Program
  -> declarations
  -> expressions
  -> statements
  -> environment
  -> evaluation
  -> result or error
~~~

Tài liệu không cần trình bày compiler nội bộ nếu người dùng chỉ cần hành vi ngôn ngữ. Tuy nhiên, cần định nghĩa đủ chính xác để người triển khai compiler và runtime có thể xây dựng implementation tương thích.

## 6. Name resolution và scope semantics

Name resolution quy định một tên trong source liên kết với declaration nào.

Ví dụ:

~~~text
let threshold = 100

function check(order) {
    let threshold = 50
    return order.total > threshold
}
~~~

Nếu DSL dùng lexical scoping, threshold trong hàm tham chiếu tới biến cục bộ có giá trị 50. Tài liệu ngữ nghĩa cần giải thích:

- Scope được tạo bởi function, block, module hay class?
- Khai báo có hiệu lực từ vị trí nào?
- Có hỗ trợ shadowing không?
- Import và local declaration được ưu tiên ra sao?
- Có hoisting không?
- Closure capture biến theo value hay reference?
- Visibility private, internal và public được hiểu thế nào?

### 6.1. Shadowing

Shadowing xảy ra khi declaration bên trong che khuất declaration cùng tên ở scope ngoài. Tài liệu nên có ví dụ để người dùng biết tên nào được resolve.

### 6.2. Hoisting và temporal dead zone

Nếu DSL cho phép dùng tên trước vị trí khai báo, cần nói rõ declaration nào được hoist. Nếu không cho phép, cần mô tả lỗi và vị trí phát hiện.

### 6.3. Closure capture

Một closure có thể giữ giá trị biến tại thời điểm tạo hoặc tham chiếu tới binding có thể thay đổi. Khác biệt này ảnh hưởng trực tiếp tới kết quả trong loop và callback bất đồng bộ.

Ví dụ:

~~~text
let handlers = []

for item in items {
    handlers.add(() => process(item))
}
~~~

Tài liệu cần nêu item được capture theo từng iteration hay tất cả closure cùng tham chiếu một binding thay đổi.

## 7. Type semantics

Type semantics quy định một giá trị thuộc kiểu nào, các kiểu tương thích ra sao và phép toán tạo ra kiểu kết quả gì.

Ví dụ:

~~~text
let amount: Money = money(120, USD)
let count: Integer = 3
let average: Money = amount / count
~~~

Tài liệu cần xác định:

- Kiểu nguyên thủy và kiểu miền.
- Type inference.
- Subtyping và coercion.
- Generic và variance.
- Union, nullable và optional type.
- Overload resolution.
- Return type và exception type.
- Runtime type check nếu có.

### 7.1. Explicit conversion và implicit coercion

Nếu DSL tự chuyển Integer sang Decimal, tài liệu cần nói rõ khi nào conversion xảy ra và có mất chính xác không.

Ví dụ:

~~~text
let ratio = decimal(count) / total
~~~

Chuyển đổi tường minh dễ thấy hơn trong source và giúp tránh các coercion ngầm gây bất ngờ. Nếu có implicit coercion, cần định nghĩa thứ tự ưu tiên và trường hợp mơ hồ.

### 7.2. Overload resolution

Nếu nhiều function cùng tên, compiler cần chọn implementation phù hợp với kiểu đối số. Tài liệu nên giải thích cách xếp hạng candidate, conversion được phép và lỗi khi có nhiều candidate ngang nhau.

### 7.3. Generic constraints

Generic có thể yêu cầu type parameter hỗ trợ một tập operation:

~~~text
function maximum<T: Comparable>(left: T, right: T): T
~~~

Tài liệu cần giải thích constraint được kiểm tra lúc compile hay runtime và kiểu nào đáp ứng contract Comparable.

## 8. Value semantics và reference semantics

Value semantics và reference semantics quyết định cách giá trị được sao chép và chia sẻ.

Ví dụ:

~~~text
let first = Point(1, 2)
let second = first
second.x = 9
~~~

Nếu Point có value semantics, sửa second không nhất thiết thay first. Nếu Point là reference type, cả hai có thể trỏ tới cùng object và thay đổi được chia sẻ.

Tài liệu cần nêu:

- Kiểu nào là immutable?
- Assignment sao chép value hay reference?
- Collection có mutable không?
- Equality so sánh value hay identity?
- Khi nào object được chia sẻ giữa closure hoặc task?

Các quy tắc này ảnh hưởng correctness, concurrency và hiệu năng. Không nên để người dùng phải suy đoán từ cách viết cú pháp.

## 9. Evaluation order

Evaluation order quy định thứ tự các biểu thức được tính.

Ví dụ:

~~~text
result = first() + second() * third()
~~~

Tài liệu cần phân biệt precedence của toán tử với thứ tự đánh giá operand. Precedence quyết định cây biểu thức; evaluation order quyết định side effect hoặc lỗi xảy ra trước sau thế nào.

### 9.1. Left-to-right hay unspecified?

Nếu DSL quy định đánh giá từ trái sang phải, người dùng có thể dựa vào thứ tự đó khi các biểu thức có side effect. Nếu thứ tự không được bảo đảm, cần nói rõ không được viết chương trình phụ thuộc vào thứ tự.

### 9.2. Short-circuit evaluation

Với toán tử and/or, nhiều DSL chỉ đánh giá vế phải khi cần:

~~~text
if customer != null and customer.isActive {
    approve()
}
~~~

Nếu and dùng short-circuit, customer.isActive không được đánh giá khi customer là null. Nếu toán tử đánh giá cả hai vế, ví dụ này có thể gây lỗi.

Tài liệu cần nêu:

- Có short-circuit không?
- Giá trị logic có thể là true, false và unknown không?
- Side effect trong operand có được phép không?
- Toán tử có thể được overload không?

### 9.3. Conditional evaluation

Với if/else hoặc conditional expression, cần nêu chỉ nhánh được chọn mới được đánh giá hay cả hai nhánh được tính trước. Điều này ảnh hưởng function có side effect, lỗi và hiệu năng.

## 10. Null, missing và optional semantics

Null và missing không nhất thiết là cùng một khái niệm:

- Null: field có mặt nhưng giá trị rỗng theo mô hình dữ liệu.
- Missing: field không tồn tại trong record hoặc document.
- Optional: kiểu biểu diễn có hoặc không có giá trị.
- Undefined: giá trị chưa được khởi tạo hoặc không xác định theo ngôn ngữ.

Ví dụ:

~~~text
where customer.address.city == "Hanoi"
~~~

Nếu address có thể missing, DSL cần quy định truy cập field gây lỗi, trả null hay trả unknown.

### 10.1. Three-valued logic

Một query DSL có thể dùng logic ba giá trị: true, false và unknown. Khi so sánh null, kết quả có thể là unknown thay vì true hoặc false.

Ví dụ:

~~~text
null == 10   // unknown theo semantics ba giá trị
null != 10   // unknown
~~~

Trong filter, chỉ predicate true có thể giữ record; false và unknown có thể bị loại. Tài liệu phải nêu rõ để người dùng hiểu vì sao record có field null không xuất hiện.

### 10.2. Null propagation

Một số ngôn ngữ lan truyền null qua phép toán:

~~~text
customer.address?.city
~~~

Optional access có thể trả null nếu customer hoặc address không có giá trị. Cần phân biệt optional access với exception handling.

## 11. Numeric semantics

Numeric semantics quy định biểu diễn số, phép toán, overflow, precision và rounding.

Các kiểu thường gặp:

- Integer có hoặc không có dấu.
- Decimal với precision và scale.
- Floating-point.
- BigInteger hoặc arbitrary precision.
- Money hoặc Quantity có đơn vị.

### 11.1. Integer overflow

Nếu Integer có giới hạn 32 bit, phép cộng vượt giới hạn có thể:

- Báo lỗi.
- Wrap quanh.
- Saturate tại giá trị lớn nhất/nhỏ nhất.

Đây là khác biệt ngữ nghĩa quan trọng và cần được tài liệu hóa. Không nên để behavior phụ thuộc CPU hoặc backend.

### 11.2. Decimal và rounding

Với phép chia hoặc chuyển đổi, cần xác định precision, scale và rounding mode. Ví dụ, chia 1.00 cho 3 không thể biểu diễn chính xác với số chữ số thập phân hữu hạn.

Tài liệu có thể chỉ rõ rounding mode mặc định và cách yêu cầu mode khác nếu được hỗ trợ.

### 11.3. Floating-point

Floating-point có rounding và các giá trị đặc biệt như NaN, positive infinity và negative infinity. So sánh bằng chính xác có thể không phù hợp cho mọi use case.

### 11.4. Domain units

Money, Duration, Distance và Percentage cần semantics về đơn vị. Không nên cho phép cộng hai Money khác currency nếu chưa có quy tắc conversion rõ ràng.

## 12. String và Unicode semantics

Tài liệu cần giải thích:

- String là sequence của byte, code point hay grapheme cluster?
- Indexing dùng đơn vị nào?
- Equality có phân biệt chữ hoa/chữ thường không?
- So sánh có phụ thuộc locale không?
- Unicode normalization được áp dụng khi nào?
- Collation của backend có ảnh hưởng kết quả không?

Ví dụ, hai chuỗi có thể hiển thị giống nhau nhưng có representation Unicode khác nhau. Nếu DSL dùng binary equality, chúng có thể không bằng nhau.

### 12.1. String indexing

Index theo byte, UTF-16 code unit hoặc Unicode code point cho kết quả khác nhau với ký tự ngoài BMP. Tài liệu nên mô tả đơn vị và behavior khi index vượt giới hạn.

### 12.2. Case folding và collation

So sánh không phân biệt hoa thường có thể phụ thuộc Unicode version hoặc locale. Nếu DSL muốn kết quả ổn định giữa backend, cần quy định collation hoặc yêu cầu backend hỗ trợ cùng semantics.

## 13. Date, time và timezone semantics

Date/time là nguồn gây khác biệt giữa môi trường nếu không có quy tắc rõ.

Các kiểu cần phân biệt:

- Date: ngày lịch không có thời gian.
- LocalDateTime: thời gian địa phương không gắn timezone.
- Instant: một thời điểm trên timeline.
- ZonedDateTime: thời điểm kèm vùng thời gian.
- Duration: khoảng thời gian tuyệt đối.
- Period: khoảng theo lịch như tháng hoặc năm.

Ví dụ:

~~~text
where createdAt >= startOfDay("Asia/Ho_Chi_Minh")
~~~

Tài liệu cần xác định:

- Timezone mặc định.
- Cách xử lý daylight saving time.
- Cách chuyển local time thành instant.
- Hành vi với thời điểm không tồn tại hoặc bị lặp khi đổi giờ.
- now() được lấy một lần hay nhiều lần trong query.
- Calendar arithmetic như cộng một tháng.

Không nên dùng timezone mặc định của máy chủ mà không công bố vì cùng query có thể cho kết quả khác giữa môi trường.

## 14. Operator semantics

Mỗi operator nên có mô tả ngữ nghĩa riêng:

| Operator | Câu hỏi cần mô tả |
|---|---|
| +, - | Kiểu operand, kiểu kết quả, overflow và side effect |
| *, / | Precision, rounding và chia cho zero |
| ==, != | Value equality hay identity, null behavior |
| <, > | Kiểu được so sánh và collation |
| and, or | Short-circuit và logic hai/ba giá trị |
| in | Membership, collection rỗng và null |
| ?? | Null coalescing và evaluation order |
| ?. | Optional access và propagation |

### 14.1. Precedence và associativity

Tài liệu cú pháp có thể liệt kê precedence, nhưng tài liệu ngữ nghĩa nên giải thích kết quả:

~~~text
a + b * c
~~~

Nếu multiplication có precedence cao hơn addition, biểu thức tương đương a + (b * c). Nếu các toán tử có cùng precedence, associativity quyết định cách nhóm.

### 14.2. Operator overloading

Nếu DSL cho phép định nghĩa operator cho type riêng, cần quy định:

- Type nào có thể overload?
- Có thể thay đổi precedence không?
- Operator có thể có side effect không?
- Equality và ordering có contract nào?
- Optimizer có thể giả định operator thuần không?

## 15. Function semantics và effect

Function documentation cần mô tả nhiều hơn signature:

- Input và output type.
- Điều kiện tiền đề.
- Điều kiện hậu nghiệm.
- Exception hoặc error.
- Side effect.
- Determinism.
- Thread safety.
- I/O hoặc network dependency.
- Capability cần có.
- Cost hoặc giới hạn nếu đáng kể.

Ví dụ:

~~~text
/**
 * Returns the current instant from the runtime clock.
 *
 * Effect: reads clock.
 * Determinism: result may differ between executions.
 */
function now(): Instant
~~~

Function now không phải pure function vì kết quả phụ thuộc clock. Optimizer không được tự do tính trước hoặc dùng lại kết quả ở mọi vị trí nếu semantics yêu cầu mỗi lần gọi có thể khác.

### 15.1. Pure function

Pure function trả cùng kết quả cho cùng input và không thay đổi trạng thái quan sát được. Nó dễ cache, test và tối ưu hơn.

### 15.2. Side-effecting function

Function có thể ghi database, gửi message hoặc gọi service. Tài liệu cần nêu capability và retry semantics. Nếu function được gọi lại, side effect có thể lặp.

### 15.3. Error contract

Function có thể trả error value, ném exception hoặc tạo diagnostic. Tài liệu nên giải thích loại lỗi, điều kiện phát sinh và cách caller xử lý.

## 16. Control-flow semantics

Control flow mô tả chương trình chuyển từ statement này sang statement khác như thế nào.

Các cấu trúc thường gặp:

- if/else.
- match hoặc switch.
- for/while.
- break/continue.
- return.
- exception handling.
- defer/finally.
- async/await.

Tài liệu cần làm rõ:

- Điều kiện loop được đánh giá trước hay sau body?
- break thoát loop gần nhất hay label cụ thể?
- finally có chạy khi return hoặc exception không?
- return trong closure có thoát function ngoài không?
- Exception có unwind stack không?
- Có giới hạn recursion hoặc loop không?

Ví dụ:

~~~text
for item in items {
    if item.invalid {
        continue
    }
    process(item)
}
~~~

Ngữ nghĩa cần nêu continue chuyển tới iteration tiếp theo và phần còn lại của body bị bỏ qua.

## 17. Exception và error semantics

Tài liệu ngữ nghĩa cần phân biệt:

- Syntax error: source không đúng grammar.
- Static semantic error: tên hoặc kiểu không hợp lệ.
- Runtime error: lỗi trong lúc thực thi.
- Domain error: vi phạm quy tắc nghiệp vụ.
- External error: dependency hoặc service bên ngoài thất bại.
- Cancellation/timeout: execution bị dừng theo policy.

Ví dụ:

~~~text
try {
    charge(payment)
} catch PaymentDeclined as error {
    markOrderPending()
} finally {
    releaseTemporaryResources()
}
~~~

Tài liệu nên nêu exception matching theo type hay hierarchy, catch order, propagation, finally behavior và liệu exception có thể bị optimizer hoặc async boundary biến đổi không.

### 17.1. Error value hay exception

Một DSL có thể dùng Result type thay cho exception. Khi đó người dùng cần biết lỗi có được truyền qua return value hay làm dừng evaluation.

### 17.2. Error propagation

Với operator hoặc pipeline, cần quy định lỗi của một bước có dừng toàn bộ pipeline hay được chuyển thành error item.

### 17.3. Source location

Runtime error nên có thể liên kết tới source span hoặc generated source map. Tài liệu có thể mô tả loại location được cung cấp, nhưng không nên hứa line/column chính xác nếu code transformation làm mất mapping.

## 18. Concurrency và asynchronous semantics

Nếu DSL hỗ trợ task hoặc async operation, cần mô tả:

- Task được schedule khi nào?
- await có block thread hay suspend coroutine?
- Có đảm bảo thứ tự hoàn thành không?
- Shared state được đồng bộ ra sao?
- Cancellation có cooperative không?
- Exception từ child task truyền về parent thế nào?
- Task có được structured theo scope không?

Ví dụ:

~~~text
let customerTask = async loadCustomer(customerId)
let orderTask = async loadOrders(customerId)

let customer = await customerTask
let orders = await orderTask
~~~

Nếu hai task độc lập, runtime có thể chạy song song. Tài liệu cần phân biệt concurrency với parallel execution; không phải mọi async operation đều chạy trên core riêng.

### 18.1. Memory visibility

Nếu nhiều task chia sẻ mutable state, cần quy định synchronization và memory visibility hoặc yêu cầu dùng primitive được cung cấp. Không nên để người dùng dựa vào thứ tự thread không được bảo đảm.

### 18.2. Cancellation

Cancellation có thể chỉ gửi yêu cầu dừng; function bên ngoài có thể tiếp tục nếu không hỗ trợ cancellation. Tài liệu cần mô tả giới hạn và side effect có thể đã xảy ra.

## 19. Query DSL semantics

Nếu DSL có phần truy vấn dữ liệu, tài liệu ngữ nghĩa cần làm rõ:

- Source và snapshot semantics.
- Null/missing logic trong filter.
- Projection và alias.
- Join cardinality.
- Ordering và tie-breaking.
- Grouping và aggregate behavior.
- Pagination.
- Window function.
- Backend portability.
- Authorization và policy filtering.

Ví dụ:

~~~text
from Orders
where total > threshold
order by createdAt descending
limit 20
~~~

Cần nói rõ kết quả có thứ tự xác định hay không, field null được xử lý thế nào và limit được áp dụng sau ordering hay trước. Một DSL declarative có thể cho optimizer đổi execution plan nhưng vẫn phải giữ kết quả theo contract.

### 19.1. Aggregation

count, sum, average, min và max cần định nghĩa:

- Null có bị bỏ qua không?
- Collection rỗng trả 0, null hay error?
- Numeric precision và overflow ra sao?
- Kết quả có deterministic khi chạy parallel không?

### 19.2. Join

Tài liệu cần mô tả inner, left, semi hoặc cross join nếu hỗ trợ, bao gồm duplicate và null key.

### 19.3. Consistency

Query trên nhiều nguồn có thể không đọc cùng một snapshot. Nếu DSL không bảo đảm transaction hoặc snapshot consistency, cần nêu giới hạn.

## 20. Workflow DSL semantics

Với workflow DSL, tài liệu cần mô tả state machine và quy tắc điều phối:

- Khi nào một step được kích hoạt?
- Điều kiện transition được đánh giá lúc nào?
- Parallel branch hoàn tất theo all, any hay quorum?
- Retry có giữ cùng input và idempotency key không?
- Timeout chuyển instance sang trạng thái nào?
- Compensation chạy theo thứ tự nào?
- Event trễ được xử lý ra sao?
- Workflow version ảnh hưởng instance đang chạy thế nào?

Ví dụ:

~~~text
workflow approveOrder {
    step validate {
        call order.validate()
    }

    step review {
        wait for approval
        timeout 2 days
    }

    step confirm {
        call order.confirm()
    }
}
~~~

Tài liệu cần nêu review chỉ hoàn tất khi event approval hợp lệ được nhận trước deadline; nếu hết hạn thì workflow chuyển sang timeout path. Chỉ nhìn cú pháp wait không thể suy ra các quy tắc đó.

## 21. Transaction và consistency semantics

DSL có thể thao tác dữ liệu trong transaction hoặc điều phối nhiều service. Cần phân biệt:

- Atomicity của một database transaction.
- Consistency của dữ liệu.
- Isolation level.
- Durability.
- Saga và compensation.
- Eventual consistency.

Ví dụ:

~~~text
transaction {
    update Account set balance = balance - amount
    update Ledger add debitEntry
}
~~~

Nếu hai update cùng một database transaction, chúng có thể được commit hoặc rollback cùng nhau theo transaction contract. Nếu bước thứ ba gọi payment service ngoài database, nó không tự động nằm trong transaction đó.

Tài liệu cần giải thích ranh giới transaction, nested transaction behavior, timeout và lỗi commit không xác định.

## 22. Security semantics

Ngữ nghĩa của DSL cũng bao gồm quyền và giới hạn:

- Principal được xác định từ đâu?
- Policy được áp dụng trên source, row và field nào?
- Function nào cần capability?
- Query có timeout hoặc cost budget không?
- Secret được resolve lúc nào?
- Sandboxed execution giới hạn tài nguyên gì?

Ví dụ:

~~~text
from Orders
where status == APPROVED
select orderId, total
~~~

Tài liệu cần nêu query engine có thể tự áp dụng tenant filter từ authenticated context. Người dùng không thể bỏ filter bảo mật bằng cách sửa query.

Không nên mô tả quyền chỉ như một tùy chọn giao diện. Security semantics phải chỉ rõ enforcement point và behavior khi policy service không khả dụng.

## 23. Determinism và portability

Một số semantics có thể phụ thuộc môi trường:

- Locale.
- Timezone.
- Random source.
- Clock.
- Database collation.
- Backend numeric type.
- Parallel execution order.
- External API response.

Tài liệu cần phân biệt:

- Hành vi được bảo đảm giống nhau trên mọi backend.
- Hành vi chỉ được bảo đảm trong một dialect.
- Hành vi không xác định hoặc phụ thuộc môi trường.

Nếu một phép toán không deterministic, cần nêu lý do và giới hạn tối ưu/cache. Ví dụ, now() có thể thay đổi giữa lần chạy; query không có order by có thể trả record theo thứ tự không được bảo đảm.

## 24. Cách trình bày một quy tắc ngữ nghĩa

Một semantic rule nên có cấu trúc nhất quán để người đọc tìm được thông tin cần thiết.

Mẫu đề xuất:

~~~text
Rule name:
  Short description:
  Applies to:
  Preconditions:
  Evaluation:
  Result:
  Errors:
  Side effects:
  Guarantees:
  Limitations:
  Examples:
  Related rules:
~~~

Ví dụ cho toán tử and:

**Tên:** Logical AND

**Áp dụng:** Hai biểu thức có kiểu Boolean hoặc kiểu được DSL cho phép chuyển đổi.

**Đánh giá:** Vế trái được đánh giá trước. Nếu vế trái là false, vế phải không được đánh giá.

**Kết quả:** true khi cả hai vế true; false khi có ít nhất một vế false; unknown nếu không có vế false và có vế unknown trong logic ba giá trị.

**Lỗi:** Lỗi phát sinh khi đánh giá vế trái được truyền ra; lỗi ở vế phải không xuất hiện nếu vế phải bị short-circuit.

**Giới hạn:** Không dùng operator này để đảm bảo thứ tự của side effect ngoài quy tắc evaluation được công bố.

### 24.1. Quy tắc cần ví dụ đối chiếu

Với semantics dễ gây hiểu nhầm, nên đưa ví dụ:

- Trường hợp hợp lệ.
- Trường hợp không hợp lệ.
- Boundary value.
- Null hoặc missing.
- Side effect hoặc lỗi.
- Khác biệt giữa các phiên bản nếu có.

### 24.2. Nêu rõ điều không được bảo đảm

Tài liệu tốt không chỉ nêu guarantee mà còn nói điều gì unspecified hoặc implementation-defined. Ví dụ, thứ tự record khi không có order by có thể không được bảo đảm.

## 25. Formal semantics và mức độ hình thức

Không phải DSL nào cũng cần một đặc tả toán học đầy đủ. Tuy nhiên, khi semantics phức tạp hoặc nhiều implementation cần tương thích, formalization có thể giúp loại bỏ mơ hồ.

Các cách mô tả:

- Operational semantics: mô tả bước chuyển trạng thái khi đánh giá.
- Denotational semantics: ánh xạ cấu trúc chương trình thành ý nghĩa toán học.
- Axiomatic semantics: mô tả điều kiện trước và sau.
- Type rules: mô tả khi nào một expression có kiểu hợp lệ.
- State transition system: mô tả workflow hoặc protocol.

### 25.1. Operational rule

Một quy tắc evaluation có thể được biểu diễn:

~~~text
if condition evaluates to true:
    evaluate thenBranch
otherwise:
    evaluate elseBranch
~~~

Với đặc tả hình thức, có thể dùng judgment notation:

\[
\langle e, \sigma \rangle \Downarrow \langle v, \sigma' \rangle
\]

Trong đó e là expression, sigma là state trước đánh giá, v là kết quả và sigma' là state sau đánh giá. Ký hiệu này hữu ích khi cần mô tả side effect hoặc state transition chính xác.

### 25.2. Type rule

Một type rule có thể nêu:

\[
\frac{\Gamma \vdash e_1 : \text{Integer} \qquad
      \Gamma \vdash e_2 : \text{Integer}}
     {\Gamma \vdash e_1 + e_2 : \text{Integer}}
\]

Gamma đại diện cho môi trường kiểu. Quy tắc này nói nếu hai operand có kiểu Integer thì biểu thức cộng có kiểu Integer, trong phạm vi các điều kiện của language specification.

### 25.3. Khi nào cần formalization?

Formal semantics hữu ích khi:

- DSL có nhiều implementation.
- Optimizer thực hiện biến đổi phức tạp.
- Ngôn ngữ có concurrency hoặc transaction semantics.
- Có yêu cầu chứng minh hoặc kiểm tra tính tương đương.
- Người dùng cần guarantee mạnh về behavior.

Với DSL nhỏ, ví dụ và prose chính xác có thể đủ. Không nên dùng ký hiệu hình thức chỉ để làm tài liệu trông phức tạp nếu người dùng mục tiêu không cần.

## 26. Ví dụ ngữ nghĩa có thể thực thi

Ví dụ trong tài liệu nên được kiểm tra bằng compiler hoặc runtime tương ứng. Một ví dụ được gọi là runnable cần có:

- Language version.
- Required module hoặc dependency.
- Input fixture.
- Expected output hoặc expected error.
- Runtime configuration nếu cần.

Ví dụ:

~~~text
let amount = money(120, USD)
let quantity = 3
let unitPrice = amount / quantity
print(unitPrice)
~~~

Tài liệu cần nêu rounding mode và output mong đợi nếu muốn ví dụ minh họa numeric semantics. Nếu kết quả phụ thuộc runtime configuration, cấu hình phải được ghi kèm.

### 26.1. Example test

CI có thể chạy ví dụ để xác nhận:

- Source parse được.
- Type checking thành công.
- Output khớp expected result.
- Expected error thực sự xuất hiện.
- Ví dụ vẫn hợp lệ với language version được chỉ định.

Ví dụ chỉ có tính minh họa nhưng không thể chạy cũng nên được đánh dấu rõ là pseudocode hoặc fragment.

### 26.2. Boundary examples

Nên có ví dụ cho giá trị biên như:

- Empty collection.
- Null field.
- Integer overflow.
- Division by zero.
- Date tại ranh giới timezone.
- Query không có record.
- Workflow event đến sau deadline.

Boundary example giúp người dùng hiểu semantics ở nơi dễ có khác biệt nhất.

## 27. Tài liệu ngữ nghĩa và conformance test

Conformance test kiểm tra một implementation có tuân thủ semantics được công bố hay không.

Một test case có thể gồm:

~~~yaml
id: logical-and-short-circuit-01
languageVersion: 3
source: |
  false and fail("should not execute")
expected:
  result: false
~~~

Bộ test nên bao gồm:

- Grammar và static semantic.
- Type compatibility.
- Evaluation order.
- Null behavior.
- Numeric and string semantics.
- Error propagation.
- Side effect.
- Query semantics.
- Workflow state transition.
- Backend portability.
- Optimization equivalence.

### 27.1. Specification test

Test case nên gắn với semantic rule ID để biết quy tắc nào đang được kiểm tra. Khi rule thay đổi, reviewer có thể thấy test và tài liệu cần cập nhật.

### 27.2. Differential test

Nếu có interpreter và compiled backend, chạy cùng test trên cả hai và so sánh kết quả. Điều này giúp phát hiện hai execution mode diễn giải khác nhau.

### 27.3. Property-based test

Kiểm tra thuộc tính tổng quát như parse/format giữ semantics hoặc optimizer không thay đổi kết quả. Property test bổ sung cho ví dụ cụ thể, không thay thế test case theo specification.

## 28. Tài liệu ngữ nghĩa được sinh tự động

Một phần semantic documentation có thể được sinh từ:

- Symbol model và type information.
- Function signature và effect metadata.
- Schema và constraint.
- Annotation hoặc documentation tag.
- Operator registry.
- Query capability registry.
- Workflow state model.
- Conformance test metadata.

Ví dụ, function registry có thể cung cấp:

~~~text
Function: calculateTax
Signature: (Order) -> Money
Effect: Pure
Deterministic: Yes
Throws: InvalidOrder
~~~

Generator có thể tạo bảng API reference. Tuy nhiên, phần diễn giải nghiệp vụ như quy tắc rounding hoặc thời điểm tính thuế thường cần người có chuyên môn viết và review.

### 28.1. Nguồn sự thật

Mỗi quy tắc cần có nguồn có thẩm quyền:

- Grammar cho cú pháp.
- Type checker hoặc language specification cho static semantics.
- Runtime contract cho dynamic behavior.
- Schema registry cho field và constraint.
- Domain owner cho quy tắc nghiệp vụ.

Không nên suy ra semantics chỉ từ implementation hiện tại nếu hành vi đó chưa được cam kết công khai. Implementation có thể chứa behavior tình cờ hoặc bug.

### 28.2. Generated và authored content

Generated content phù hợp với tên, kind, signature, type, source location và capability có cấu trúc. Authored content phù hợp với rationale, ví dụ nghiệp vụ, giới hạn và giải thích khó suy ra từ metadata.

Hai phần nên được ghép qua document model và có traceability tới rule hoặc symbol nguồn.

## 29. Tài liệu ngữ nghĩa trong IDE và language server

Semantic documentation có thể được tích hợp vào developer tooling:

- Hover hiển thị type, signature và behavior summary.
- Completion hiển thị mô tả function và operator.
- Go to Definition dẫn tới semantic rule.
- Diagnostic liên kết tới quy tắc vi phạm.
- Outline cho biết symbol và container.
- Quick documentation mở phần giải thích đầy đủ.

Ví dụ hover:

~~~text
calculateTax(order: Order): Money

Calculates tax using the order currency.
Pure function. Does not modify the order.
Throws InvalidOrder when required fields are missing.
~~~

Hover nên ngắn gọn, còn tài liệu đầy đủ có thể chứa semantics chi tiết, ví dụ và liên kết.

Language server không nên tiết lộ metadata hoặc documentation private nếu caller không có quyền xem. Documentation có thể chứa thông tin nội bộ về service hoặc schema.

## 30. Versioning và compatibility của semantics

Semantics là hợp đồng có version. Thay đổi grammar không phải lúc nào cũng breaking; ngược lại, đổi behavior của một operator có thể là breaking dù source vẫn parse.

Ví dụ thay đổi có thể phá tương thích:

- Null comparison từ unknown sang false.
- Đổi rounding mode mặc định.
- Đổi evaluation order.
- Thay đổi overflow behavior.
- Đổi timezone mặc định.
- Thay đổi retry hoặc transaction semantics.
- Đổi cách resolve overload.

Một release note nên mô tả:

- Semantic rule bị thay đổi.
- Hành vi trước và sau.
- Source hoặc data nào bị ảnh hưởng.
- Migration hoặc compatibility option.
- Version nào bắt đầu áp dụng.

### 30.1. Language version

Compiler có thể hỗ trợ nhiều language version. Source cần xác định version để behavior không âm thầm đổi khi compiler nâng cấp.

### 30.2. Deprecation

Nếu một semantics cũ sẽ bị loại bỏ, có thể phát warning và cung cấp cách viết mới. Không nên đổi behavior ngay trong patch release nếu người dùng đang dựa vào hợp đồng cũ.

### 30.3. Backend conformance

Nếu cùng DSL chạy trên nhiều backend, mỗi backend cần tuân thủ semantics lõi hoặc công bố capability/dialect. Không nên để cùng query trả kết quả khác nhau mà không có tài liệu giải thích.

## 31. Traceability giữa tài liệu, implementation và test

Mỗi semantic rule có thể có ID ổn định:

~~~text
SEM-EXPR-AND-001
SEM-TYPE-NULL-002
SEM-NUM-OVERFLOW-003
SEM-QUERY-ORDER-004
SEM-WORKFLOW-TIMEOUT-005
~~~

ID có thể liên kết:

- Trang tài liệu.
- Grammar hoặc type rule.
- Compiler/runtime implementation.
- Conformance tests.
- Release note.
- Issue hoặc decision record.

Ví dụ:

| Rule ID | Tài liệu | Implementation area | Test |
|---|---|---|---|
| SEM-EXPR-AND-001 | Logical AND | Expression evaluator | and-short-circuit |
| SEM-NUM-OVERFLOW-003 | Integer arithmetic | Numeric runtime | int-overflow |
| SEM-QUERY-ORDER-004 | Ordering | Query planner | stable-order |

Traceability giúp biết một thay đổi trong implementation có thể ảnh hưởng quy tắc nào và test nào cần chạy.

## 32. Cách tổ chức bộ tài liệu ngữ nghĩa

Một cấu trúc có thể gồm:

~~~text
language-reference/
  overview.md
  lexical-semantics.md
  names-and-scope.md
  type-system.md
  expressions.md
  evaluation-order.md
  values-and-collections.md
  errors-and-effects.md
  concurrency.md
  query-semantics.md
  workflow-semantics.md
  security-semantics.md
  portability.md
  version-compatibility.md
~~~

Với DSL nhỏ, các phần có thể nằm trong một tài liệu. Với DSL lớn, chia theo chủ đề giúp người dùng tìm nhanh và cho phép owner quản lý từng phần.

Mỗi trang nên có:

- Phạm vi và language version.
- Thuật ngữ được dùng.
- Rule ID nếu có.
- Quy tắc và guarantee.
- Ví dụ hợp lệ và không hợp lệ.
- Lỗi và boundary cases.
- Liên kết tới syntax, API và test.
- Lịch sử thay đổi semantics.

## 33. Viết tài liệu ngữ nghĩa rõ ràng

Một số nguyên tắc biên soạn:

1. Dùng thuật ngữ nhất quán và định nghĩa trước khi dùng.
2. Phân biệt guarantee, default, unspecified và implementation-defined behavior.
3. Nêu điều kiện áp dụng của từng quy tắc.
4. Dùng ví dụ nhỏ tập trung vào một semantics.
5. Bổ sung boundary case cho quy tắc dễ gây hiểu nhầm.
6. Mô tả error behavior và side effect.
7. Nêu version hoặc dialect nếu behavior khác nhau.
8. Tránh mô tả implementation detail như guarantee nếu không có cam kết.
9. Liên kết quy tắc với test có thể chạy.
10. Viết cho người dùng mục tiêu nhưng giữ độ chính xác kỹ thuật.

### 33.1. Dùng từ chính xác

Các từ "always", "never", "may", "must" và "unspecified" có ý nghĩa khác nhau. Nếu nói "engine có thể tối ưu", người đọc không nên hiểu đó là guarantee rằng optimizer luôn thực hiện.

### 33.2. Phân biệt lỗi và kết quả hợp lệ

Nếu phép toán chia cho zero phát sinh error, tài liệu cần nói error type và thời điểm phát hiện. Nếu nó trả infinity theo floating-point semantics, đó là kết quả hợp lệ của kiểu đó.

### 33.3. Không dùng ví dụ mơ hồ

Ví dụ phụ thuộc timezone máy, locale hoặc data không xác định sẽ khó tái lập. Hãy nêu context hoặc dùng fixture cụ thể.

## 34. Những lỗi thường gặp khi viết tài liệu ngữ nghĩa

### Chỉ mô tả grammar

Người đọc biết cách viết nhưng không biết chương trình chạy thế nào. Bổ sung evaluation, type, error và state behavior.

### Trộn implementation với specification

Một chi tiết nội bộ bị hiểu thành guarantee. Phân biệt contract công khai với cách compiler/runtime hiện thực.

### Bỏ qua null và boundary case

Người dùng suy luận behavior theo trực giác hoặc backend khác. Định nghĩa null, missing, empty collection và overflow.

### Không mô tả thứ tự đánh giá

Side effect hoặc exception xảy ra không như mong đợi. Nêu evaluation order và short-circuit.

### Bỏ qua side effect và determinism

Optimizer hoặc retry có thể làm hành vi khác. Mô tả effect, purity và determinism.

### Ví dụ không được kiểm tra

Ví dụ cũ hoặc không compile làm giảm độ tin cậy. Gắn version và chạy example test.

### Không version hóa semantics

Người dùng không biết behavior nào áp dụng cho compiler hiện tại. Gắn language version và migration note.

### Không liên kết test

Tài liệu và implementation có thể lệch nhau. Gắn semantic rule với conformance test.

### Mô tả guarantee quá rộng

Nói "cùng query luôn cho cùng kết quả" dù query phụ thuộc time hoặc external state. Nêu rõ điều kiện của guarantee.

## 35. Quy trình xây dựng tài liệu ngữ nghĩa

Một quy trình thực tế:

1. **Liệt kê cấu trúc ngôn ngữ.** Expression, statement, type, function, query và workflow construct.
2. **Xác định static semantics.** Scope, name resolution, type, overload và constraint.
3. **Xác định dynamic semantics.** Evaluation order, state, errors, effects và concurrency.
4. **Xác định domain rules.** Money, time, query, workflow và schema behavior.
5. **Tách guarantee khỏi implementation.** Ghi rõ behavior được bảo đảm và phần không xác định.
6. **Tạo semantic rule ID.** Cho các quy tắc quan trọng và có khả năng thay đổi.
7. **Viết ví dụ.** Bao gồm normal, boundary, invalid và error case.
8. **Liên kết implementation.** Xác định compiler/runtime component chịu trách nhiệm.
9. **Tạo conformance tests.** Kiểm tra implementation tuân thủ quy tắc.
10. **Tích hợp tooling.** Hover, diagnostics và cross-reference.
11. **Version hóa.** Gắn language version và migration note.
12. **Duy trì traceability.** Cập nhật docs, test và release notes cùng thay đổi semantics.

## 36. Ví dụ end-to-end: tài liệu ngữ nghĩa cho toán tử AND

Giả sử DSL hỗ trợ logic ba giá trị và short-circuit evaluation.

Source:

~~~text
if customer != null and customer.isActive {
    approve(customer)
}
~~~

Semantic rules:

**SEM-EXPR-AND-001 — Evaluation order**

- Đánh giá operand bên trái trước.
- Nếu operand trái là false, không đánh giá operand phải.
- Nếu operand trái là true, đánh giá operand phải.
- Nếu operand trái là unknown, đánh giá operand phải để xác định kết quả theo bảng chân trị.

**SEM-EXPR-AND-002 — Result**

| Left | Right | Result |
|---|---|---|
| false | bất kỳ | false |
| true | true | true |
| true | false | false |
| true | unknown | unknown |
| unknown | false | false |
| unknown | true | unknown |
| unknown | unknown | unknown |

**SEM-EXPR-AND-003 — Error propagation**

- Lỗi khi đánh giá operand trái được truyền ra.
- Operand phải không được đánh giá nếu operand trái là false.
- Lỗi ở operand phải chỉ xảy ra khi operand phải được đánh giá.

Conformance test:

~~~text
false and fail("not evaluated")
=> false

true and true
=> true

unknown and false
=> false
~~~

IDE hover có thể hiển thị:

~~~text
and — logical conjunction

Uses three-valued logic and evaluates left to right.
The right operand is skipped when the left operand is false.
See SEM-EXPR-AND-001 and SEM-EXPR-AND-002.
~~~

Từ một quy tắc ngữ nghĩa, hệ thống có thể tạo phần documentation ngắn, test có thể chạy và liên kết tới implementation. Khi semantics thay đổi, rule ID giúp nhóm tìm đúng tài liệu và test cần cập nhật.

## 37. Kết luận

Tài liệu ngữ nghĩa giải thích hành vi được bảo đảm của DSL: tên được resolve ra sao, kiểu tương thích thế nào, biểu thức được đánh giá theo thứ tự nào, null và lỗi được xử lý ra sao, function có side effect gì và query hoặc workflow tuân theo quy tắc nào. Nó bổ sung cho grammar bằng cách mô tả ý nghĩa của chương trình thay vì chỉ mô tả cách viết.

Một bộ tài liệu tốt phân biệt static semantics, dynamic semantics và implementation; nêu rõ guarantee cùng giới hạn; dùng ví dụ có thể kiểm tra; version hóa các quy tắc; và liên kết tài liệu với compiler/runtime cùng conformance tests. Với những phần phức tạp, formal semantics hoặc state transition model giúp giảm mơ hồ, nhưng mức hình thức nên phù hợp với người đọc và yêu cầu của DSL.

Khi tài liệu, implementation và test cùng tham chiếu tới các semantic rule ổn định, nhóm có thể thay đổi compiler hoặc optimizer mà vẫn giữ hợp đồng ngôn ngữ. Người dùng cũng có cơ sở dự đoán chương trình sẽ làm gì, xử lý trường hợp biên thế nào và thay đổi phiên bản có thể ảnh hưởng ra sao.

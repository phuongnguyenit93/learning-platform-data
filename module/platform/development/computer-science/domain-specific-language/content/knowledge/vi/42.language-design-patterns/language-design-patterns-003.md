# Thiết kế hợp thành

Một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) thường bắt đầu bằng một số cấu trúc nhỏ như literal, expression, function, rule, query hoặc action. Khi kết hợp những cấu trúc này theo các quy tắc nhất quán, người dùng có thể mô tả một quy trình hoặc chính sách lớn mà vẫn giữ chương trình dễ đọc, tái sử dụng và kiểm tra. **Thiết kế hợp thành (compositional design)** là cách xây dựng DSL sao cho các thành phần nhỏ có thể kết hợp thành thành phần lớn hơn, đồng thời ý nghĩa của toàn bộ chương trình có thể được hiểu từ ý nghĩa và quan hệ của các phần cấu thành.

Một DSL có tính hợp thành tốt không yêu cầu người dùng viết lại cùng một logic trong nhiều nơi. Một biểu thức có thể được đặt trong một function; function có thể được dùng trong rule; rule có thể được nhóm thành policy; policy có thể được gọi trong workflow. Mỗi lớp có một contract rõ ràng về input, output, kiểu dữ liệu, phạm vi và side effect.

Hợp thành không đơn giản là cho phép lồng nhiều cú pháp. Nếu các thành phần có semantics mơ hồ, phụ thuộc thứ tự ngầm hoặc thay đổi trạng thái toàn cục, việc ghép chúng có thể tạo hành vi khó dự đoán. Thiết kế cần quy định cách truyền dữ liệu, đánh giá biểu thức, xử lý lỗi, quản lý scope, kiểm soát quyền và xác định thứ tự thực thi.

Bài học này trình bày nguyên tắc hợp thành, cấu trúc ngôn ngữ theo lớp, expression và function composition, module và namespace, rule và policy, query và pipeline, workflow và sub-workflow, grammar và AST, type system, scope, error propagation, side effect, tối ưu, khả năng mở rộng và các ví dụ thiết kế DSL theo hướng hợp thành.

## 1. Hợp thành là gì?

Hợp thành là quá trình tạo một cấu trúc lớn bằng cách kết hợp các cấu trúc nhỏ theo một quy tắc xác định.

Ví dụ, hai expression có thể được kết hợp bằng toán tử cộng:

~~~text
subtotal + tax
~~~

Một expression lớn có thể được đặt trong function:

~~~text
function totalPrice(subtotal: Decimal, tax: Decimal): Decimal {
  return subtotal + tax
}
~~~

Function có thể được sử dụng trong một rule:

~~~text
rule isHighValueOrder(order) {
  totalPrice(order.subtotal, order.tax) >= 10000000
}
~~~

Rule có thể được dùng trong workflow:

~~~text
if isHighValueOrder(order) {
  requestManagerApproval(order)
}
~~~

Mỗi cấu trúc được xây dựng từ cấu trúc nhỏ hơn. Nếu contract của từng cấu trúc rõ ràng, người đọc có thể hiểu toàn bộ chương trình bằng cách lần theo các thành phần.

### 1.1. Composition và reuse

Reuse là sử dụng lại một thành phần đã có. Composition là kết hợp nhiều thành phần để tạo hành vi mới. Hai khái niệm liên quan nhưng không giống nhau.

Một function có thể được reuse nhiều lần. Khi kết hợp function validateCustomer, calculatePrice và reserveInventory thành một workflow, đó là composition.

### 1.2. Composition và inheritance

Inheritance tạo quan hệ kế thừa giữa các type hoặc class. Composition kết hợp các thành phần qua interface hoặc contract. Trong DSL, composition thường giúp mô hình hóa nghiệp vụ linh hoạt hơn việc tạo một hệ thống type kế thừa sâu.

### 1.3. Composition và configuration

Configuration chọn hoặc nối các thành phần có sẵn. Composition có thể diễn ra ở cấp cú pháp, AST, runtime hoặc deployment. Ví dụ, cấu hình pipeline nối các task đã khai báo thành một đồ thị thực thi.

### 1.4. Tính cục bộ của ý nghĩa

Một nguyên tắc quan trọng là ý nghĩa của một thành phần nên được hiểu từ contract của nó và các input được truyền vào. Nếu một function thay đổi kết quả dựa trên global variable không được khai báo, composition sẽ khó phân tích và kiểm thử.

### 1.5. Tính đóng

Một tập cấu trúc có tính đóng nếu kết quả của một phép kết hợp vẫn có thể được dùng như input của cùng loại cấu trúc. Ví dụ, nếu mọi arithmetic expression đều trả về một expression có type xác định, có thể lồng chúng trong biểu thức lớn hơn.

## 2. Vì sao DSL cần thiết kế hợp thành?

DSL thường phục vụ một miền có nhiều quy tắc và quy trình liên kết. Nếu không có composition, chương trình dễ trở thành một tập khai báo rời rạc hoặc một đoạn script lớn khó bảo trì.

### 2.1. Giảm lặp logic

Một predicate như isEligibleCustomer có thể được dùng trong nhiều rule. Nếu logic bị sao chép, các bản sao có thể dần khác nhau khi chính sách thay đổi.

### 2.2. Tăng khả năng đọc

Một workflow có thể mô tả ở cấp nghiệp vụ:

~~~text
validateOrder(order)
reserveStock(order)
collectPayment(order)
arrangeDelivery(order)
~~~

Người đọc không cần xem toàn bộ chi tiết của từng function ngay lập tức.

### 2.3. Tăng khả năng kiểm thử

Mỗi thành phần nhỏ có thể được test riêng. Sau đó test composition để xác minh các thành phần phối hợp đúng.

### 2.4. Tạo abstraction theo miền

DSL có thể cung cấp abstraction như pricing policy, approval flow hoặc data mapping. Người dùng kết hợp các abstraction này mà không phải thao tác trực tiếp với chi tiết hạ tầng.

### 2.5. Hỗ trợ mở rộng

Khi thêm một rule hoặc action mới, hệ thống có thể kết hợp nó vào module hoặc workflow hiện có nếu contract tương thích.

### 2.6. Tạo cơ sở cho phân tích tĩnh

Khi thành phần có type và dependency rõ, compiler có thể kiểm tra type mismatch, dependency cycle, capability thiếu và cấu hình không hợp lệ trước khi chạy.

## 3. Các nguyên tắc thiết kế hợp thành

### 3.1. Thành phần nhỏ, một trách nhiệm

Mỗi thành phần nên có mục đích rõ. Function tính thuế không nên đồng thời gửi email, ghi database và thay đổi trạng thái đơn hàng.

### 3.2. Contract rõ ràng

Một component cần mô tả:
- Tên và phiên bản.
- Input type.
- Output type.
- Preconditions.
- Postconditions.
- Side effects.
- Required capabilities.
- Error behavior.
- Resource constraints.

### 3.3. Kết hợp qua interface

Thành phần nên tương tác qua type hoặc interface công khai thay vì phụ thuộc vào implementation nội bộ.

### 3.4. Explicit data flow

Dữ liệu nên được truyền qua tham số, context hoặc output có tên. Tránh phụ thuộc vào biến toàn cục hoặc ambient state không rõ nguồn.

### 3.5. Semantics ổn định

Cùng một cấu trúc với cùng input và context cần có hành vi xác định theo contract. Nếu thứ tự khai báo hoặc thứ tự load ảnh hưởng kết quả, cần công bố điều đó rõ ràng.

### 3.6. Composition không che giấu lỗi

Nếu một thành phần thất bại, parent cần nhận được kết quả lỗi hoặc diagnostic rõ ràng. Không chuyển lỗi thành giá trị mặc định tùy tiện.

### 3.7. Side effect có ranh giới

Pure expression nên được ưu tiên cho tính toán. Side effect nên được khai báo qua action hoặc capability để runtime có thể kiểm tra quyền, retry và audit.

### 3.8. Có thể quan sát

Mỗi thành phần có thể có identity, trace span hoặc diagnostic location để truy nguyên lỗi từ composition về thành phần nguồn.

## 4. Các lớp composition trong DSL

Một DSL có thể tổ chức thành nhiều lớp trừu tượng.

~~~text
Literal and Variable
        |
        v
Expression and Operator
        |
        v
Function and Predicate
        |
        v
Rule and Policy
        |
        v
Query and Pipeline
        |
        v
Workflow and Module
        |
        v
Application Configuration
~~~

Đây là mô hình minh họa. DSL cụ thể có thể có ít hoặc nhiều lớp hơn.

### 4.1. Expression layer

Biểu thức tạo ra giá trị. Các expression có thể được kết hợp bằng toán tử, function call và conditional.

### 4.2. Function layer

Function đóng gói một phép tính hoặc hành vi có contract. Function có thể gọi function khác nếu dependency hợp lệ.

### 4.3. Rule layer

Rule đặt tên cho một điều kiện hoặc quyết định. Rule có thể dùng predicate và function.

### 4.4. Policy layer

Policy kết hợp nhiều rule để đưa ra quyết định. Cần semantics về precedence, deny/allow và default behavior.

### 4.5. Query layer

Query kết hợp source, filter, join, grouping, projection và ordering thành một pipeline dữ liệu.

### 4.6. Workflow layer

Workflow kết hợp step, event, state, guard và action thành quy trình dài hạn.

### 4.7. Module layer

Module gom các thành phần có liên quan, quản lý namespace và public interface.

## 5. Expression composition

Expression composition là cách tạo biểu thức lớn từ literal, variable, operator, function call và expression khác.

### 5.1. Arithmetic composition

~~~text
let subtotal = unitPrice * quantity
let tax = subtotal * taxRate
let total = subtotal + tax
~~~

Mỗi biểu thức có type và kết quả riêng. Compiler có thể kiểm tra phép nhân, cộng và conversion.

### 5.2. Boolean composition

~~~text
let isEligible =
  customer.active
  and customer.tier in [SILVER, GOLD]
  and order.total >= minimumOrder
~~~

Các predicate nhỏ có thể được đặt tên:

~~~text
predicate isActive(customer) {
  customer.active
}

predicate hasEligibleTier(customer) {
  customer.tier in [SILVER, GOLD]
}

predicate meetsMinimum(order) {
  order.total >= minimumOrder
}

predicate isEligible(customer, order) {
  isActive(customer)
    and hasEligibleTier(customer)
    and meetsMinimum(order)
}
~~~

### 5.3. Conditional composition

Một conditional expression có thể trả về giá trị và được lồng trong expression khác:

~~~text
let shippingFee =
  if order.total >= freeShippingThreshold
  then 0
  else baseFee + distanceFee
~~~

Hai nhánh cần có type tương thích để expression có một output type xác định.

### 5.4. Function composition

Có thể kết hợp function theo kiểu output của function trước là input của function sau:

~~~text
function normalizeEmail(value: String): String {
  lower(trim(value))
}

function validateEmail(value: String): Boolean {
  matchesEmailPattern(value)
}

let valid = validateEmail(normalizeEmail(input.email))
~~~

### 5.5. Pipeline operator

Một DSL có thể hỗ trợ cú pháp pipeline để làm rõ thứ tự:

~~~text
input.email
  |> trim
  |> lower
  |> validateEmail
~~~

Cần định nghĩa rõ cách truyền giá trị, cách xử lý nhiều tham số và cách lan truyền lỗi.

### 5.6. Associativity và evaluation order

Với toán tử cộng số học, phép kết hợp có thể được xác định theo associativity. Với function có side effect, thay đổi thứ tự gọi có thể làm đổi kết quả. DSL cần phân biệt expression thuần và action có side effect.

## 6. Function composition và higher-order function

Function là một abstraction quan trọng để composition.

### 6.1. Function contract

~~~text
function calculateTax(
  amount: Decimal,
  rate: Decimal
): Decimal {
  return amount * rate
}
~~~

Contract cho biết input, output và logic. Nếu function thuần, nó không đọc hoặc thay đổi trạng thái bên ngoài.

### 6.2. Higher-order function

Higher-order function nhận function khác làm input hoặc trả về function:

~~~text
function applyToItems(
  items: List<Item>,
  transform: Item -> Decimal
): List<Decimal> {
  return items.map(transform)
}
~~~

Cú pháp minh họa cho phép function type. Một DSL không cần hỗ trợ higher-order function nếu miền không cần khả năng này.

### 6.3. Map, filter và reduce

Các thao tác collection là các phép composition phổ biến:

~~~text
let activePrices =
  items
    .filter(item => item.active)
    .map(item => item.price)

let total =
  activePrices.reduce(0, (sum, price) => sum + price)
~~~

Mỗi stage nhận collection từ stage trước. Type checker có thể suy ra kiểu phần tử qua từng bước.

### 6.4. Function decorator hoặc wrapper

Có thể bọc function để thêm behavior như logging, retry hoặc caching:

~~~text
let reliableLookup = withRetry(customerLookup)
let cachedLookup = withCache(reliableLookup)
~~~

Wrapper cần giữ contract và quy định rõ behavior khi function lỗi hoặc bị cancel.

### 6.5. Partial application

Một function có nhiều tham số có thể được cố định một phần:

~~~text
let calculateVat10 = calculateTax(rate = 0.10)
~~~

Partial application hữu ích khi một chính sách được tái sử dụng với một cấu hình cố định. DSL cần quy định cách resolve named argument và default.

### 6.6. Giới hạn function composition

Không phải function nào cũng có thể kết hợp tùy ý. Function bất đồng bộ, function trả lỗi và function có side effect cần contract riêng.

## 7. Composition với kiểu dữ liệu

Type system giúp xác định những thành phần nào có thể kết hợp an toàn.

### 7.1. Type compatibility

Nếu function A trả Decimal và function B nhận Decimal, output của A có thể truyền vào B.

~~~text
function subtotal(order: Order): Decimal
function calculateTax(amount: Decimal): Decimal

let tax = calculateTax(subtotal(order))
~~~

Nếu A trả String nhưng B nhận Decimal, compiler cần báo lỗi hoặc yêu cầu conversion tường minh.

### 7.2. Generic type

Generic cho phép tạo component có thể dùng với nhiều type:

~~~text
function first<T>(items: List<T>): T? {
  if items.isEmpty() {
    return null
  }

  return items[0]
}
~~~

Generic giúp composition mà không phải tạo function riêng cho từng loại record.

### 7.3. Union và result type

Một function có thể trả success hoặc failure:

~~~text
type Result<T, E> =
  Success(T)
  | Failure(E)
~~~

Function tiếp theo có thể map success hoặc propagate failure. Cách biểu diễn này làm rõ lỗi trong composition.

### 7.4. Optional type

Nếu function A trả T? thì function B nhận T cần xử lý trường hợp null. DSL có thể cung cấp map, flatMap hoặc null-safe operator.

### 7.5. Structural và nominal typing

Structural typing cho phép kết hợp type dựa trên field và shape. Nominal typing yêu cầu type identity hoặc declaration tương thích. Lựa chọn ảnh hưởng khả năng reuse và ranh giới domain.

### 7.6. Refinement type

Một type có constraint như PositiveDecimal hoặc EmailAddress giúp compiler và validator biết miền giá trị. Component có thể yêu cầu type đã được refine thay vì lặp lại kiểm tra.

### 7.7. Type inference

Type inference giảm annotation nhưng cần giới hạn để diagnostics dễ hiểu và compile time dự đoán được. Với composition sâu, error message nên chỉ ra vị trí nơi hai contract không tương thích.

## 8. Module và namespace composition

Module gom các thành phần liên quan và cung cấp public interface cho phần còn lại của chương trình.

### 8.1. Module boundary

Một module có thể chứa:
- Type.
- Function.
- Predicate.
- Rule.
- Query.
- Policy.
- Workflow.
- Constant.
- Import.

Ví dụ:

~~~text
module Pricing {
  export type PriceResult
  export function calculatePrice
  export predicate isEligibleForDiscount
}
~~~

### 8.2. Import và export

Module khác có thể import public symbol:

~~~text
module Checkout {
  import Pricing.calculatePrice
  import Inventory.reserve
}
~~~

Chỉ symbol được export mới là public contract. Implementation detail có thể được giữ private.

### 8.3. Namespace

Namespace giúp tránh tên trùng:

~~~text
Pricing.calculate
Tax.calculate
Shipping.calculate
~~~

Tên đầy đủ làm rõ domain của operation.

### 8.4. Dependency graph

Module dependency tạo thành graph. Compiler cần phát hiện cycle hoặc định nghĩa semantics cho dependency cycle nếu có. Cycle không kiểm soát làm khó incremental compilation và initialization order.

### 8.5. Versioned module

Module có thể có version và dependency constraint. Một project cần biết đang dùng version nào và migration nào cần thiết khi nâng cấp.

### 8.6. Public API stability

Thay đổi private implementation không nên buộc mọi consumer sửa code. Thay đổi public type hoặc function contract cần compatibility policy.

### 8.7. Module composition và package

Nhiều module có thể được đóng gói thành package. Package manifest ghi dependency, version, export, capability và target runtime.

## 9. Rule và policy composition

Rule biểu diễn điều kiện hoặc quyết định. Policy kết hợp nhiều rule để đưa ra kết quả ở cấp cao hơn.

### 9.1. Predicate composition

~~~text
predicate isLargeOrder(order) {
  order.total >= 5000000
}

predicate isPriorityCustomer(customer) {
  customer.tier == GOLD
}

predicate needsManualReview(order, customer) {
  isLargeOrder(order)
    and not isPriorityCustomer(customer)
}
~~~

### 9.2. Rule set

Một rule set có thể gom các rule theo mục tiêu:

~~~text
ruleSet orderValidation {
  rule hasItems
  rule hasValidAddress
  rule supportedCurrency
  rule totalWithinLimit
}
~~~

### 9.3. Policy composition

~~~text
policy approveOrder(order, actor) {
  require orderValidation(order)

  allow if actor.hasRole("MANAGER")
    and order.total <= actor.approvalLimit

  deny otherwise
}
~~~

### 9.4. Precedence

Nếu nhiều rule cùng match, policy cần quy tắc:
- First match.
- Highest priority.
- Explicit deny overrides allow.
- Collect all decisions.
- Reject ambiguity.

Không nên để thứ tự load file hoặc iteration order quyết định quyền.

### 9.5. Explainability

Policy engine nên trả decision cùng lý do hoặc rule ID đã match. Điều này giúp debug và audit.

### 9.6. Policy versioning

Một policy được dùng để phê duyệt hoặc truy cập dữ liệu nên có version. Audit record cần biết version nào tạo ra quyết định.

## 10. Query composition

Query DSL thường có các operator có thể ghép thành pipeline xử lý dữ liệu.

### 10.1. Source, filter và projection

~~~text
from Order
where status == PAID
select {
  id,
  customerId,
  total
}
~~~

Source xác định tập dữ liệu, filter giảm tập và projection chọn output shape.

### 10.2. Join composition

~~~text
from Order as order
join Customer as customer
  on customer.id == order.customerId
where customer.active
select {
  order.id,
  customer.name,
  order.total
}
~~~

### 10.3. Grouping và aggregation

~~~text
from Order
where status == PAID
group by customerId
select {
  customerId: group.key,
  orderCount: group.count(),
  revenue: group.sum(order.total)
}
~~~

### 10.4. Query as value

Nếu query plan có type, một query có thể được truyền vào function hoặc kết hợp với query khác. DSL cần định nghĩa query có eager hay lazy execution.

### 10.5. Pipeline composition

~~~text
let report =
  paidOrders
    .filter(order => order.createdAt >= periodStart)
    .groupBy(order => order.storeId)
    .map(group => summarize(group))
    .sortBy(result => result.revenue, DESC)
~~~

### 10.6. Pushdown optimization

Query pipeline có thể được optimizer chuyển filter hoặc projection xuống database. Chỉ thực hiện rewrite khi giữ nguyên null semantics, ordering và error behavior.

### 10.7. Resource contract

Query component cần giới hạn row count, execution time, memory và data scope. Composition nhiều query có thể tạo chi phí lớn hơn từng query riêng.

## 11. Workflow và pipeline composition

Workflow kết hợp các step thành một tiến trình. Mỗi step có input/output và có thể có dependency, retry hoặc event.

### 11.1. Step composition

~~~text
workflow processOrder(order) {
  step validate {
    run validateOrder(order)
  }

  step reserve {
    after validate
    run reserveInventory(order)
  }

  step payment {
    after reserve
    run collectPayment(order)
  }

  step shipping {
    after payment
    run arrangeShipping(order)
  }
}
~~~

### 11.2. Sequence composition

Sequence đảm bảo step sau chỉ bắt đầu khi step trước đạt điều kiện hoàn tất.

### 11.3. Parallel composition

Một số step độc lập có thể chạy song song:

~~~text
parallel {
  run calculateTax(order)
  run checkFraud(order)
  run prepareInvoice(order)
}
~~~

Cần định nghĩa join condition, failure propagation và cancellation.

### 11.4. Conditional composition

~~~text
if order.requiresApproval {
  run approvalWorkflow(order)
} else {
  run autoApprove(order)
}
~~~

### 11.5. Sub-workflow

Workflow lớn có thể gọi workflow con:

~~~text
call paymentWorkflow(order)
call fulfillmentWorkflow(order)
~~~

Parent cần quy định cách nhận completion, failure, cancellation và output từ child.

### 11.6. Compensation

Nếu một step tạo side effect rồi step sau thất bại, workflow có thể chạy compensation tương ứng. Compensation là action nghiệp vụ riêng và có thể thất bại.

### 11.7. Composition và transaction boundary

Không giả định cả workflow nằm trong một database transaction. Mỗi step có thể commit riêng và cần idempotency, retry, timeout và recovery.

## 12. Grammar và AST composition

Thiết kế hợp thành cần được hỗ trợ ở tầng ngữ pháp và cấu trúc nội bộ.

### 12.1. Grammar theo lớp

Một grammar có thể định nghĩa expression từ các production nhỏ:

~~~text
Expression
  ::= Literal
   | Identifier
   | UnaryExpression
   | BinaryExpression
   | FunctionCall
   | ConditionalExpression
   | ParenthesizedExpression
~~~

Mỗi production tham chiếu production khác, tạo cấu trúc lồng nhau.

### 12.2. Precedence và associativity

Grammar cần quy định precedence của toán tử và associativity. Nếu không, expression như a + b * c có thể bị diễn giải khác nhau giữa parser hoặc runtime.

### 12.3. AST node contract

Mỗi AST node có thể chứa:
- Node kind.
- Source range.
- Child node.
- Static type sau analysis.
- Symbol binding.
- Metadata.
- Diagnostic attachment.

### 12.4. Reusable node interface

Compiler có thể định nghĩa interface chung cho expression:

~~~text
interface Expression {
  sourceRange: SourceRange
  inferredType: Type?
}
~~~

Các node literal, call và binary expression cùng tuân theo contract. Visitor hoặc pattern matching có thể xử lý từng loại.

### 12.5. AST transformation

Optimizer có thể thay một subtree bằng subtree tương đương. Transformation cần giữ source mapping, type correctness và semantics.

### 12.6. IR composition

Intermediate representation có thể gồm instruction, block, function và module. Các lớp này được kết hợp thành chương trình target.

### 12.7. Error recovery

Nếu một child node lỗi parse, parent node cần có representation cho missing hoặc invalid child để parser tiếp tục và tạo diagnostic. Không nên tạo AST không hợp lệ mà không đánh dấu.

## 13. Scope, name resolution và dependency

Composition cần xác định tên nào có thể được nhìn thấy ở đâu.

### 13.1. Lexical scope

Biến khai báo trong block chỉ tồn tại trong phạm vi được định nghĩa. Điều này tránh tên cục bộ vô tình ảnh hưởng component khác.

### 13.2. Parameter scope

Function nhận dữ liệu qua parameter. Không nên dựa vào biến từ caller trừ khi DSL có semantics closure được đặc tả rõ.

### 13.3. Module scope

Symbol public được import theo namespace. Symbol private chỉ có thể dùng trong module định nghĩa.

### 13.4. Shadowing

Nếu scope con khai báo tên trùng scope cha, DSL cần quy định shadowing có được phép và cách resolve. Diagnostic có thể cảnh báo shadowing gây nhầm lẫn.

### 13.5. Dependency cycle

Nếu function A gọi B và B gọi A, DSL cần hỗ trợ recursion có giới hạn hoặc từ chối cycle. Module cycle cũng cần policy riêng.

### 13.6. Initialization order

Nếu module có constant hoặc state khởi tạo, thứ tự dependency cần xác định. Ưu tiên khai báo thuần và initialization xác định để tránh side effect trong quá trình load.

## 14. Error composition và kết quả

Một thành phần có thể thành công hoặc thất bại. Composition cần quy tắc lan truyền và xử lý lỗi.

### 14.1. Fail fast

Fail fast dừng ngay khi một thành phần lỗi. Phù hợp khi bước sau không thể chạy nếu bước trước không thành công.

### 14.2. Accumulating validation

Validation có thể thu thập nhiều lỗi độc lập thay vì dừng ở lỗi đầu tiên:

~~~text
let result = validateAll([
  validateName(customer),
  validateEmail(customer),
  validateAddress(customer)
])
~~~

### 14.3. Result type

~~~text
Result<Price, PricingError>
~~~

Function composition có thể map success hoặc propagate failure. Cần tránh bỏ qua error một cách vô tình.

### 14.4. Error context

Khi lỗi đi qua nhiều lớp, thêm context như function name, rule ID, workflow step và source location. Không thay thế root cause bằng một thông báo chung.

### 14.5. Recovery boundary

Một workflow có thể xử lý lỗi ở step cụ thể bằng retry hoặc compensation. Lỗi không được xử lý cần lan đến parent hoặc execution supervisor.

### 14.6. Diagnostic aggregation

Có thể gộp nhiều diagnostic theo severity và source range, nhưng vẫn giữ code và location gốc để người dùng điều tra.

## 15. Pure composition và side effects

Một trong những quyết định quan trọng nhất là phân biệt tính toán thuần với hành động làm thay đổi hệ thống.

### 15.1. Pure function

Pure function không đọc hoặc thay đổi trạng thái bên ngoài và cùng input luôn trả cùng output. Nó dễ cache, test và composition.

### 15.2. Side-effecting action

Action có thể:
- Ghi database.
- Gửi message.
- Gọi payment provider.
- Tạo file.
- Thay đổi workflow state.

Action cần permission, timeout, retry, idempotency và audit.

### 15.3. Effect declaration

DSL có thể khai báo effect của function:

~~~text
function calculateTotal(order): Decimal
  effects: none

action reserveStock(order): Reservation
  effects: inventory.write
~~~

Compiler hoặc runtime có thể kiểm tra nơi gọi có đủ capability hay không.

### 15.4. Effect composition

Nếu function A gọi action B, effect của A phải bao gồm effect cần thiết hoặc khai báo dependency tương ứng. Không nên che giấu side effect trong function có vẻ thuần.

### 15.5. Ordering

Hai action có side effect không nhất thiết có thể đổi thứ tự. Composition cần thể hiện dependency và thứ tự thực thi.

### 15.6. Idempotency

Khi workflow retry, action có thể chạy lại. Side effect nên có idempotency key hoặc semantics chống trùng.

### 15.7. Transaction

Composition của nhiều action không tự động atomic. Cần xác định commit boundary, compensation và recovery.

## 16. Composition và tính xác định

Tính xác định giúp người dùng dự đoán kết quả khi kết hợp component.

### 16.1. Deterministic evaluation

Cùng input, context và version cần tạo cùng kết quả nếu DSL hứa semantics deterministic.

### 16.2. Không phụ thuộc iteration order ngầm

Nếu collection không có ordering contract, không nên dựa vào thứ tự phần tử khi tạo output hoặc quyết định business.

### 16.3. Clock và random

Time và random nên được truyền qua execution context hoặc capability rõ ràng nếu cần reproducibility.

### 16.4. External data

Function gọi API có thể nhận response khác nhau. Ghi lại dependency result hoặc snapshot khi cần replay.

### 16.5. Parallel composition

Các nhánh song song cần độc lập hoặc có synchronization rõ. Race condition có thể khiến output thay đổi giữa các lần chạy.

### 16.6. Version pinning

Composition phụ thuộc module version và policy version. Artifact cần ghi dependency version để kết quả có thể được tái lập.

## 17. Composition trong thiết kế syntax

Cú pháp cần giúp người dùng nhận ra cách ghép cấu trúc mà không tạo quá nhiều trường hợp đặc biệt.

### 17.1. Consistent nesting

Nếu block được dùng cho function, rule và workflow, cách viết block nên nhất quán. Tuy nhiên, semantics của mỗi block vẫn cần khác biệt rõ.

### 17.2. Named composition

Tên có ý nghĩa nghiệp vụ giúp che chi tiết triển khai:

~~~text
let eligible = customerEligibility(order, customer)
~~~

Tốt hơn việc lặp lại một biểu thức dài ở nhiều nơi.

### 17.3. Fluent syntax

Fluent syntax nối operation theo chuỗi:

~~~text
orders
  .filter(isPaid)
  .filter(isWithinPeriod)
  .groupBy(storeId)
  .map(summarize)
~~~

Cần đảm bảo mỗi operation trả type phù hợp cho operation tiếp theo.

### 17.4. Declarative composition

Declarative syntax mô tả kết quả mong muốn và quan hệ:

~~~text
report MonthlyRevenue {
  source: paidOrders
  groupBy: storeId
  aggregate: sum(total)
}
~~~

Runtime hoặc compiler quyết định cách thực thi.

### 17.5. Embedded composition

DSL có thể nhúng expression trong một host language hoặc ngược lại. Cần xác định ranh giới parser, type conversion, error và security.

### 17.6. Không lạm dụng cú pháp đặc biệt

Nếu mọi feature đều có một cách lồng riêng, người học phải nhớ quá nhiều quy tắc. Ưu tiên một số composition mechanism nhất quán.

## 18. Composition và tối ưu compiler

Compiler có thể tận dụng cấu trúc hợp thành để phân tích và tối ưu chương trình.

### 18.1. Constant folding

Biểu thức thuần có constant input có thể được tính trước:

~~~text
let taxRate = 0.1 + 0.05
~~~

Compiler có thể thay bằng constant nếu numeric semantics cho phép.

### 18.2. Common subexpression elimination

Nếu cùng một pure expression được tính nhiều lần trong cùng context, compiler có thể tính một lần và tái sử dụng.

### 18.3. Inlining

Function nhỏ có thể được inline để giảm call overhead. Nhưng inlining làm tăng code size và có thể ảnh hưởng debugging hoặc compilation time.

### 18.4. Dead code elimination

Component không ảnh hưởng output hoặc side effect có thể bị loại bỏ nếu semantics cho phép. Không được xóa expression có effect hoặc exception behavior quan sát được.

### 18.5. Query pushdown

Query composition có thể được chuyển thành một plan thực thi tại database. Optimizer cần giữ semantics của null, order, collation và limit.

### 18.6. Parallelization

Các subtree độc lập có thể được đánh giá song song. Cần phân tích dependency, side effect và resource budget trước khi chạy.

### 18.7. Incremental recomputation

Nếu một input thay đổi, chỉ recompute các node phụ thuộc. Dependency graph chính xác giúp tránh tính lại toàn bộ composition.

## 19. Thiết kế API để hỗ trợ composition

DSL thường cần API host hoặc extension function. Contract của API quyết định mức độ kết hợp an toàn.

### 19.1. Small interface

API nên có trách nhiệm rõ, input/output type và error contract. Tránh expose một service container tổng quát.

### 19.2. Composable result

API có thể trả Result, Optional hoặc typed value để component tiếp theo xử lý theo contract.

### 19.3. Async contract

Function bất đồng bộ nên thể hiện rõ Future, Task hoặc Async result. DSL cần quy định await, cancellation và timeout.

### 19.4. Resource ownership

Nếu API trả stream, file handle hoặc cursor, phải xác định ai đóng resource và lifetime của nó.

### 19.5. Capability

API có side effect cần capability được cấp cho execution. Composition không được tự nâng quyền khi gọi component con.

### 19.6. Versioning

Extension API có version. Module cần khai báo version tương thích để tránh compile thành công nhưng runtime thiếu method.

## 20. Ví dụ hoàn chỉnh: composition cho quy trình đặt hàng

Giả sử một hệ thống cần kiểm tra đơn, tính giá, giữ hàng, thu tiền và giao hàng.

### 20.1. Domain types

~~~text
record Order {
  id: OrderId
  customerId: CustomerId
  items: List<OrderItem>
  address: Address
}

record OrderItem {
  sku: String
  quantity: Integer
  unitPrice: Decimal
}

record PriceResult {
  subtotal: Decimal
  discount: Decimal
  tax: Decimal
  total: Decimal
}
~~~

### 20.2. Function thuần

~~~text
function calculateSubtotal(order: Order): Decimal {
  return order.items.sum(item => item.quantity * item.unitPrice)
}

function calculateDiscount(order: Order): Decimal {
  let subtotal = calculateSubtotal(order)
  return discountPolicy(order.customerId, subtotal)
}

function calculateTax(amount: Decimal): Decimal {
  return amount * taxRate
}

function calculatePrice(order: Order): PriceResult {
  let subtotal = calculateSubtotal(order)
  let discount = calculateDiscount(order)
  let taxable = subtotal - discount
  let tax = calculateTax(taxable)

  return PriceResult {
    subtotal: subtotal,
    discount: discount,
    tax: tax,
    total: taxable + tax
  }
}
~~~

### 20.3. Validation composition

~~~text
function validateOrder(order): ValidationResult {
  return validateAll([
    validateItems(order.items),
    validateAddress(order.address),
    validateCustomer(order.customerId)
  ])
}
~~~

### 20.4. Action components

~~~text
action reserveInventory(order): Reservation
action collectPayment(order, price): PaymentReceipt
action arrangeShipment(order, reservation): Shipment
~~~

Các action được expose qua capability có scope và idempotency.

### 20.5. Workflow composition

~~~text
workflow placeOrder(order) {
  let validation = validateOrder(order)

  if not validation.valid {
    return Rejected(validation.issues)
  }

  let price = calculatePrice(order)
  let reservation = reserveInventory(order)
  let payment = collectPayment(order, price)
  let shipment = arrangeShipment(order, reservation)

  return Confirmed(order.id, payment, shipment)
}
~~~

Đây là pseudocode đồng bộ để minh họa cách ghép. Runtime thực tế có thể dùng state machine bất đồng bộ và lưu checkpoint giữa các action.

### 20.6. Failure behavior

- Validation fail: không gọi action.
- Inventory unavailable: trả business rejection hoặc retry theo policy.
- Payment timeout: dùng idempotency key và reconcile provider.
- Shipment fail sau payment: chạy compensation hoặc chuyển manual handling.
- Duplicate request: dùng order request ID để tránh tạo đơn lặp.

### 20.7. Tách composition khỏi implementation

Function calculatePrice có thể được thay đổi mà workflow vẫn dùng cùng contract PriceResult. Inventory provider có thể đổi implementation nhưng action reserveInventory giữ contract ổn định.

### 20.8. Kiểm thử composition

Test từng function, từng action adapter và workflow end-to-end. Kiểm tra cả thứ tự action, không gọi action khi validation fail và behavior khi dependency lỗi.

## 21. Ví dụ: composition cho policy truy cập

Một policy lớn có thể được tạo từ predicate nhỏ.

### 21.1. Predicate cơ bản

~~~text
predicate isActive(user) {
  user.status == ACTIVE
}

predicate sameTenant(user, resource) {
  user.tenantId == resource.tenantId
}

predicate hasRole(user, role) {
  role in user.roles
}
~~~

### 21.2. Rule

~~~text
predicate canReadCustomer(user, customer) {
  isActive(user)
    and sameTenant(user, customer)
    and (
      hasRole(user, "CUSTOMER_SUPPORT")
      or hasRole(user, "ACCOUNT_MANAGER")
    )
}
~~~

### 21.3. Policy

~~~text
policy customerAccess(user, customer, action) {
  deny if not isActive(user)
  deny if not sameTenant(user, customer)

  allow if action == READ
    and canReadCustomer(user, customer)

  default deny
}
~~~

### 21.4. Explain decision

Decision result có thể gồm:
- Allow hoặc deny.
- Policy ID và version.
- Rule ID đã match.
- Reason code.
- Correlation ID.

### 21.5. Test composition

Test predicate riêng, sau đó test policy khi nhiều predicate kết hợp. Đảm bảo default deny vẫn hoạt động khi thêm role hoặc rule mới.

## 22. Những lỗi thiết kế hợp thành thường gặp

**Thành phần quá lớn.** Function vừa tính toán vừa ghi dữ liệu và gửi notification khó test và tái sử dụng. Hãy tách pure calculation khỏi action.

**Contract không rõ.** Component nhận context ngầm hoặc trả output không có type rõ khiến consumer phải đoán. Hãy khai báo input/output và error behavior.

**Global state.** Kết quả component phụ thuộc biến toàn cục thay đổi theo execution khác. Hãy truyền context tường minh và cô lập state.

**Composition quá sâu.** Nhiều lớp wrapper và function call làm khó trace và diagnostics. Hãy giữ abstraction cần thiết và cung cấp source mapping.

**Side effect bị che giấu.** Function có tên như calculateTotal nhưng âm thầm ghi database. Hãy khai báo effect và dùng action cho thao tác thay đổi hệ thống.

**Thứ tự ngầm.** Rule hoặc action cùng match nhưng kết quả phụ thuộc thứ tự load. Hãy định nghĩa precedence hoặc từ chối ambiguity.

**Type conversion tự động quá rộng.** Component có thể nhận dữ liệu sai nghĩa chỉ vì coercion. Hãy dùng conversion tường minh cho boundary quan trọng.

**Error bị nuốt.** Một component trả default khi lỗi khiến parent tưởng thành công. Hãy dùng Result hoặc diagnostic rõ.

**Module phụ thuộc vòng.** Dependency cycle gây khó load và build. Hãy tách contract chung hoặc thay đổi module boundary.

**Tối ưu làm đổi semantics.** Reordering expression có side effect hoặc floating-point có thể đổi kết quả. Chỉ tối ưu khi chứng minh tương đương.

**Composition không có resource budget.** Ghép nhiều query hoặc async call có thể tạo tải quá lớn. Hãy giới hạn concurrency, output và execution time.

**Public API quá rộng.** Consumer phụ thuộc implementation detail. Hãy export interface tối thiểu và version contract.

## 23. Quy trình thiết kế DSL theo hướng hợp thành

Có thể triển khai theo trình tự:

1. **Xác định miền:** liệt kê khái niệm và hành vi cốt lõi.
2. **Chọn đơn vị nhỏ:** literal, expression, function, rule, query, action hoặc step.
3. **Định nghĩa contract:** input, output, type, error, effect và resource.
4. **Thiết kế composition operator:** function call, pipeline, block, module import hoặc workflow dependency.
5. **Định nghĩa semantics:** evaluation order, precedence, scope, null và error propagation.
6. **Thiết kế type system:** kiểm tra component có thể kết hợp hay không.
7. **Xây AST và IR:** biểu diễn composition rõ ràng và giữ source mapping.
8. **Thiết kế module boundary:** public/private, dependency và version.
9. **Xử lý effect:** capability, transaction, retry và idempotency.
10. **Kiểm thử:** unit, composition, property, integration và performance test.
11. **Quan sát:** trace, diagnostic, dependency graph và execution identity.
12. **Tiến hóa:** version contract và giữ compatibility khi thêm component.

## 24. Kiểm thử tính hợp thành

Một component chạy đúng riêng lẻ chưa chứng minh composition của nó đúng.

### 24.1. Unit test

Kiểm tra từng function, predicate, query operator hoặc action adapter theo contract.

### 24.2. Composition test

Kết hợp hai hoặc nhiều component và kiểm tra output, error và effect. Test cả component có type tương thích lẫn trường hợp type mismatch.

### 24.3. Property-based test

Kiểm tra tính chất tổng quát:
- Composition của pure function giữ tính deterministic.
- Filter không tạo record ngoài input.
- Mapping bảo toàn invariant đã công bố.
- Policy default deny.
- Retry action không tạo side effect trùng khi idempotency được đảm bảo.

### 24.4. Order test

Với component có side effect, xác minh thứ tự thực thi và cancellation.

### 24.5. Error propagation test

Kiểm tra lỗi từ child được chuyển lên parent đúng error type và giữ context.

### 24.6. Module compatibility test

Test consumer với module version cũ và mới theo compatibility policy.

### 24.7. Resource test

Composition nhiều query, function hoặc workflow cần test memory, concurrency, timeout và output limit.

### 24.8. Determinism test

Chạy cùng input và context nhiều lần, so sánh output nếu semantics yêu cầu deterministic.

## 25. Kết luận

Thiết kế hợp thành giúp DSL phát triển từ những cấu trúc nhỏ thành chương trình lớn có thể đọc, kiểm tra, tái sử dụng và mở rộng. Expression, function, rule, policy, query, workflow và module đều có thể là những đơn vị composition nếu chúng có contract rõ ràng và semantics nhất quán.

Một DSL hợp thành tốt cần type system để kiểm tra tương thích, scope và module boundary để kiểm soát dependency, error model để lan truyền thất bại, effect model để phân biệt tính toán thuần với side effect và resource policy để kiểm soát chi phí. Compiler có thể phân tích AST/IR và tối ưu composition, nhưng mọi rewrite phải giữ nguyên semantics.

Hãy bắt đầu từ các thành phần nhỏ có trách nhiệm rõ, truyền dữ liệu qua contract tường minh và kết hợp chúng bằng những quy tắc ổn định. Khi người dùng có thể hiểu một chương trình lớn bằng cách hiểu từng thành phần và cách chúng phối hợp, DSL sẽ dễ học, dễ kiểm thử và dễ tiến hóa hơn.


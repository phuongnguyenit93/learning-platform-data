# Luật điều kiện và hành động

## 1. Luật điều kiện và hành động là gì?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) dùng cho luật và quyết định, **luật điều kiện và hành động (condition-action rule)** mô tả một hành động cần thực hiện khi một điều kiện được thỏa mãn.

Một luật thường có dạng:

~~~text
WHEN condition
THEN action
~~~

Ví dụ:

~~~text
rule "Discount for large orders"
  when order.total >= 2_000_000
  then order.discount = 0.10
~~~

Luật trên diễn đạt rằng khi tổng giá trị đơn hàng đạt ngưỡng quy định, hệ thống áp dụng mức giảm giá 10%.

Một hệ thống có thể chứa nhiều luật:

~~~text
rule "Free shipping"
  when order.total >= 1_000_000
  then order.shippingFee = 0

rule "High value review"
  when order.total >= 10_000_000
  then order.requiresApproval = true
~~~

Mỗi luật thể hiện một mối quan hệ giữa điều kiện và kết quả. Khi chạy, rule engine đánh giá điều kiện trên dữ liệu hiện tại, xác định luật nào được kích hoạt và thực hiện hành động theo chính sách điều phối đã định nghĩa.

Một luật điều kiện và hành động thường có các thành phần:

- **Tên hoặc ID:** định danh ổn định của luật.
- **Điều kiện (condition):** biểu thức hoặc mẫu cần khớp.
- **Hành động (action):** thao tác được thực hiện khi luật được chọn.
- **Metadata:** mô tả, nhóm, chủ sở hữu, phiên bản hoặc nguồn.
- **Thuộc tính thực thi:** độ ưu tiên, trạng thái enable/disable, giới hạn hoặc nhóm loại trừ.

Không phải DSL nào cũng có đầy đủ các thuộc tính này. Tuy nhiên, việc phân biệt điều kiện, hành động và chính sách thực thi giúp mô hình luật dễ hiểu, kiểm thử và bảo trì.

## 2. Luật điều kiện-hành động và câu lệnh if-then

Một luật có thể trông giống câu lệnh if-then trong ngôn ngữ lập trình:

~~~text
if order.total >= 2_000_000:
    order.discount = 0.10
~~~

Nhưng hai khái niệm không nhất thiết giống nhau.

| Đặc điểm | Câu lệnh if-then | Condition-action rule |
|---|---|---|
| Vị trí | Nằm trong luồng điều khiển của chương trình | Được khai báo trong tập luật |
| Điều phối | Thường theo thứ tự câu lệnh | Có thể do rule engine điều phối |
| Kích hoạt | Khi luồng thực thi đi đến câu lệnh | Khi điều kiện khớp trong một lần đánh giá |
| Nhiều luật | Thứ tự thường nằm trong code | Có thể dùng agenda, priority hoặc conflict policy |
| Dữ liệu | Thường đọc biến trong scope hiện tại | Có thể khớp facts hoặc domain objects |
| Quản lý | Thường thay đổi bằng sửa code | Có thể quản lý, bật/tắt hoặc version hóa tập luật |

Một DSL đơn giản có thể biên dịch mỗi rule thành một nhánh if. Một rule engine tổng quát hơn có thể tách việc xác định luật đủ điều kiện khỏi việc chọn và thực thi luật.

### 2.1 Khi nào dùng if-then?

If-then phù hợp khi:

- Luồng xử lý tuyến tính và nhỏ.
- Thứ tự đánh giá đã rõ trong code.
- Điều kiện ít thay đổi.
- Không cần quản lý tập luật độc lập.

### 2.2 Khi nào dùng rule?

Condition-action rules phù hợp khi:

- Có nhiều quy tắc nghiệp vụ độc lập.
- Người dùng miền cần đọc hoặc cấu hình luật.
- Nhiều luật có thể cùng khớp.
- Tập luật thay đổi thường xuyên.
- Cần giải thích luật nào đã kích hoạt.
- Cần quản lý phiên bản, ưu tiên hoặc nhóm luật.

Không nên đưa mọi điều kiện đơn giản vào một rule engine nếu câu lệnh thông thường đã đủ rõ. Một hệ thống luật có thêm chi phí về matching, conflict resolution, vòng đời facts và kiểm soát tác dụng phụ.

## 3. Cấu trúc tổng quát của một rule

Một DSL có thể định nghĩa cú pháp:

~~~text
rule "rule-id" {
  description: "Human-readable explanation"
  priority: 100
  enabled: true

  when:
    condition-expression

  then:
    action-statement
}
~~~

Đây là cú pháp minh họa. Một DSL khác có thể dùng từ khóa when/then, if/do hoặc match/execute.

### 3.1 Rule identity

Tên hiển thị giúp người dùng đọc luật. ID ổn định giúp hệ thống theo dõi luật qua các lần đổi tên, version và triển khai.

Ví dụ:

~~~text
id: pricing.large-order-discount
name: "Large order discount"
~~~

Không nên dùng tên hiển thị làm khóa duy nhất nếu người dùng có thể đổi tên hoặc dịch tên.

### 3.2 Description và metadata

Description giải thích mục đích của luật. Metadata có thể gồm:

- Nhóm nghiệp vụ.
- Người sở hữu.
- Ngày hiệu lực.
- Ngày hết hạn.
- Phiên bản.
- Nguồn hoặc ticket.
- Nhãn kiểm toán.

Metadata giúp quản trị tập luật nhưng không nên làm thay đổi điều kiện hoặc hành động nếu không được định nghĩa rõ.

### 3.3 Điều kiện

Điều kiện có thể là:

- Biểu thức Boolean.
- Một mẫu khớp với facts.
- Nhiều điều kiện kết hợp AND/OR/NOT.
- Điều kiện có ràng buộc kiểu.
- Điều kiện trên dữ liệu từ nhiều đối tượng.

### 3.4 Hành động

Hành động có thể:

- Gán giá trị.
- Tạo hoặc cập nhật fact.
- Phát sinh kết quả quyết định.
- Ghi diagnostic hoặc audit event.
- Gửi thông điệp qua adapter.
- Gọi một tác vụ đã được cấp quyền.

Nên giới hạn tập hành động mà DSL cho phép. Nếu cho phép thực thi mã tùy ý, luật có thể khó kiểm soát, khó kiểm thử và tạo rủi ro bảo mật.

## 4. Điều kiện và biểu thức Boolean

Điều kiện thường trả về true hoặc false:

~~~text
order.total >= 2_000_000
customer.tier == GOLD
customer.active == true
~~~

Rule được xem là đủ điều kiện khi biểu thức điều kiện thỏa mãn theo semantics của DSL.

### 4.1 So sánh

Các toán tử thường gặp:

| Toán tử | Ý nghĩa |
|---|---|
| == | Bằng |
| != | Khác |
| > | Lớn hơn |
| >= | Lớn hơn hoặc bằng |
| < | Nhỏ hơn |
| <= | Nhỏ hơn hoặc bằng |
| in | Thuộc tập hợp |
| matches | Khớp mẫu |
| is null | Giá trị null |

Ngữ nghĩa cụ thể phải được định nghĩa theo kiểu dữ liệu. So sánh string có thể phân biệt hoa thường hoặc không; so sánh tiền tệ phải xét currency và scale.

### 4.2 AND

AND yêu cầu mọi điều kiện con đều đúng:

~~~text
when customer.active
 and customer.tier == GOLD
 and order.total >= 2_000_000
~~~

### 4.3 OR

OR yêu cầu ít nhất một điều kiện con đúng:

~~~text
when customer.isEmployee
 or customer.hasPremiumMembership
~~~

### 4.4 NOT

NOT phủ định một điều kiện:

~~~text
when not customer.blocked
~~~

Với dữ liệu nullable hoặc unknown, DSL cần định nghĩa rõ NOT unknown có kết quả gì.

### 4.5 Nhóm điều kiện

Ngoặc giúp thể hiện precedence:

~~~text
when (customer.tier == GOLD or customer.tier == PLATINUM)
 and order.total >= 2_000_000
~~~

Không nên dựa vào thứ tự đọc tự nhiên nếu grammar không quy định precedence rõ.

## 5. Kiểu dữ liệu trong điều kiện

Điều kiện cần tuân thủ type system của DSL.

Ví dụ hợp lệ:

~~~text
order.total >= 2_000_000 VND
customer.age >= 18
order.createdAt before today
~~~

Ví dụ không hợp lệ nếu DSL kiểm tra kiểu nghiêm ngặt:

~~~text
order.total >= "large"
customer.age >= "adult"
~~~

### 5.1 Type checking

Compiler nên kiểm tra kiểu của toán hạng và kết quả điều kiện trước khi thực thi luật. Một condition thường phải có kiểu Boolean hoặc kiểu truth value được DSL định nghĩa.

### 5.2 Null và missing

Field có thể:

- Không tồn tại.
- Có giá trị null.
- Có giá trị hợp lệ.

Nếu DSL phân biệt missing và null, condition cần giữ được sự khác biệt đó.

Ví dụ:

~~~text
when customer.email is missing
~~~

khác với:

~~~text
when customer.email is null
~~~

### 5.3 Logic ba giá trị

Nếu điều kiện có thể là true, false hoặc unknown, engine cần quy định cách xử lý. Một lựa chọn là chỉ kích hoạt rule khi kết quả true; false và unknown đều không kích hoạt nhưng có thể được phân biệt trong diagnostics.

### 5.4 Domain types

Các kiểu như Money, Duration, Date, Percentage và Identifier nên có semantics riêng. Không nên chuyển tất cả thành string hoặc double rồi so sánh tùy tiện.

Ví dụ, so sánh 100 USD với 100 EUR cần chính sách chuyển đổi tiền tệ; nếu chưa có tỷ giá, điều kiện có thể không hợp lệ.

## 6. Điều kiện trên một đối tượng và nhiều đối tượng

Một rule đơn giản có thể kiểm tra một object:

~~~text
when order.status == PENDING
then order.requiresReview = true
~~~

Rule khác có thể liên kết nhiều đối tượng:

~~~text
when customer.id == order.customerId
 and customer.riskScore >= 80
 and order.total > 5_000_000
then order.requiresApproval = true
~~~

Engine cần xác định customer nào được liên kết với order và có bao nhiêu tổ hợp object thỏa mãn điều kiện.

### 6.1 Pattern matching

Trong rule engine dựa trên facts, điều kiện có thể khai báo mẫu:

~~~text
when
  Customer(tier == GOLD, active == true)
  Order(customerId == Customer.id, total >= 2_000_000)
then
  applyGoldDiscount(Order)
~~~

Mẫu cho biết các fact nào cần tìm và ràng buộc giữa chúng.

### 6.2 Binding

Một điều kiện có thể bind object hoặc giá trị để action dùng lại:

~~~text
when
  customer: Customer(tier == GOLD)
  order: Order(customerId == customer.id, total >= 2_000_000)
then
  order.discount = calculateDiscount(customer, order)
~~~

Binding phải có scope rõ và không được nhầm với biến toàn cục hoặc biến được khai báo trong action.

### 6.3 Số lượng kết quả khớp

Một điều kiện có thể khớp:

- Không có object.
- Một object.
- Nhiều object.
- Nhiều tổ hợp object.

Engine cần định nghĩa một activation được tạo cho mỗi object, mỗi tổ hợp hay mỗi nhóm kết quả.

### 6.4 Duplicate activation

Nếu cùng một tổ hợp facts được phát hiện lại, engine cần chính sách tránh tạo activation trùng ngoài ý muốn. Có thể dùng identity của fact và match tuple làm khóa.

## 7. Hành động của rule

Hành động là phần được thực hiện khi rule được kích hoạt và được chọn để chạy.

Ví dụ:

~~~text
rule "Block suspended customer"
  when customer.status == SUSPENDED
  then
    decision.allowed = false
    decision.reason = "Customer is suspended"
~~~

### 7.1 Gán giá trị

Hành động có thể cập nhật field:

~~~text
then order.discount = 0.10
~~~

Nên quy định field có mutable không, ai được phép ghi và kiểu giá trị phải phù hợp.

### 7.2 Tạo fact

Rule có thể tạo một fact mới:

~~~text
then insert ApprovalRequired(order.id)
~~~

Fact mới có thể làm điều kiện của luật khác trở thành đúng.

### 7.3 Cập nhật fact

Nếu rule engine duy trì index cho facts, update cần đi qua API của engine để các điều kiện phụ thuộc được đánh giá lại.

Sửa trực tiếp object mà engine không biết có thể khiến index hoặc activation bị stale.

### 7.4 Xóa fact

Một action có thể retract hoặc xóa fact:

~~~text
then retract temporaryOffer
~~~

Engine cần cập nhật các match phụ thuộc vào fact bị xóa.

### 7.5 Phát sinh quyết định

Một rule có thể tạo kết quả thay vì sửa input:

~~~text
then emit Decision(
  outcome = APPROVE,
  reason = "All required checks passed"
)
~~~

Đây thường là cách dễ kiểm thử và audit hơn so với thay đổi nhiều object dùng chung.

### 7.6 Gọi dịch vụ bên ngoài

Action có thể gửi email, gọi API hoặc ghi database, nhưng cần cân nhắc retry, timeout, transaction và idempotency. Các tác dụng phụ bên ngoài làm việc chạy lại rule trở nên phức tạp.

## 8. Condition matching và activation

Trong một rule engine, cần phân biệt:

- **Rule:** định nghĩa điều kiện và hành động.
- **Match:** một tập facts thỏa điều kiện.
- **Activation:** một lần thực thi tiềm năng được tạo từ rule và match cụ thể.
- **Firing:** việc thực thi action của activation.

Ví dụ:

~~~text
Rule: "Gold customer discount"

Facts:
  Customer(id=1, tier=GOLD)
  Order(id=10, customerId=1, total=2500000)
  Order(id=11, customerId=1, total=4000000)
~~~

Nếu điều kiện khớp từng Order, engine có thể tạo hai activation:

~~~text
Activation A: rule + Customer(1) + Order(10)
Activation B: rule + Customer(1) + Order(11)
~~~

Hai activation có thể cùng chờ trong agenda.

### 8.1 Agenda

Agenda là danh sách các activation đang chờ được thực thi. Rule engine dùng conflict resolution để chọn activation tiếp theo.

### 8.2 Match không đồng nghĩa action đã chạy

Một điều kiện có thể khớp nhưng activation chưa được chọn. Nó cũng có thể bị hủy trước khi firing nếu facts thay đổi hoặc policy loại bỏ activation.

### 8.3 Re-evaluation

Khi facts thay đổi, engine cần cập nhật các match phụ thuộc. Có thể thêm activation mới, loại activation cũ hoặc giữ activation nếu match vẫn hợp lệ.

### 8.4 Snapshot và consistency

Một activation cần biết nó được tạo từ trạng thái dữ liệu nào. Nếu dữ liệu thay đổi trước lúc firing, engine phải quyết định dùng snapshot cũ, kiểm tra lại điều kiện hoặc hủy activation.

## 9. Conflict resolution và thứ tự thực thi

Nhiều luật có thể cùng khớp. Engine cần quy tắc chọn luật tiếp theo.

Ví dụ:

~~~text
rule "Standard discount"
  priority: 10
  when order.total >= 1_000_000
  then order.discount = 0.05

rule "Gold discount"
  priority: 50
  when customer.tier == GOLD
  then order.discount = 0.10
~~~

Nếu cả hai luật cùng khớp, priority có thể quyết định luật nào được chạy trước. Nhưng chạy trước không tự động có nghĩa luật còn lại không được chạy.

### 9.1 Salience hoặc priority

Một số rule engine dùng salience/priority để xếp activation. Giá trị cao hơn có thể được ưu tiên, nhưng chiều ưu tiên phải được quy định rõ.

### 9.2 Tie-breaking

Nếu hai activation cùng priority, engine có thể dùng:

- Thứ tự khai báo.
- Thứ tự tạo activation.
- Độ mới của fact.
- Rule group.
- ID ổn định.
- Chính sách deterministic riêng.

Không nên để kết quả phụ thuộc thứ tự iteration không ổn định của HashMap hoặc cấu trúc tương tự.

### 9.3 Conflict policy

Các chính sách thường gặp:

- First match wins.
- Highest priority wins.
- Run all matching rules.
- Exclusive group: chỉ một luật trong nhóm được chạy.
- Ordered evaluation: chạy theo thứ tự được khai báo.

Tên chính sách không đủ; cần định nghĩa cách xử lý khi action của luật trước làm điều kiện của luật sau thay đổi.

### 9.4 Priority không thay thế logic nghiệp vụ

Nếu hai luật mâu thuẫn, tăng priority chỉ che giấu vấn đề nếu không có lý do nghiệp vụ rõ. Có thể cần định nghĩa nhóm loại trừ hoặc điều kiện để các luật không cùng khớp.

## 10. Firing và chu kỳ thực thi

Một engine theo kiểu forward-chaining thường lặp:

~~~text
Facts in working memory
          |
          v
Evaluate / update matches
          |
          v
Build activation agenda
          |
          v
Select next activation
          |
          v
Execute action (fire)
          |
          v
Update facts
          |
          +------> evaluate affected rules
~~~

Chu kỳ tiếp tục cho đến khi không còn activation phù hợp, đạt giới hạn hoặc bị dừng.

### 10.1 Insert facts

Đưa dữ liệu vào working memory để rule engine có thể sử dụng.

### 10.2 Match

Engine tìm các điều kiện thỏa mãn. Với hệ thống lớn, có thể dùng mạng matching được tối ưu để không phải đánh giá lại mọi luật từ đầu.

### 10.3 Agenda selection

Engine chọn activation theo priority và conflict policy.

### 10.4 Fire

Engine thực hiện action của activation đã chọn.

### 10.5 Update và retract

Action có thể làm thay đổi facts. Những thay đổi này có thể tạo hoặc hủy activation khác.

### 10.6 Halt

Quá trình kết thúc khi không còn activation cần chạy, khi gặp lệnh halt, khi đạt giới hạn hoặc khi có lỗi theo policy.

## 11. Forward chaining và backward chaining

Condition-action rules thường được dùng trong forward chaining, nhưng DSL luật có thể hỗ trợ nhiều cách suy luận.

### 11.1 Forward chaining

Forward chaining bắt đầu từ facts đã biết và tìm luật có điều kiện khớp. Action có thể tạo facts mới, từ đó kích hoạt luật tiếp theo.

~~~text
Fact A
  |
  v
Rule 1: A -> B
  |
  v
Fact B
  |
  v
Rule 2: B -> C
  |
  v
Fact C
~~~

Phù hợp khi sự kiện hoặc dữ liệu mới đến và hệ thống cần suy ra các kết luận.

### 11.2 Backward chaining

Backward chaining bắt đầu từ mục tiêu hoặc câu hỏi, rồi tìm các luật có thể chứng minh mục tiêu đó.

Ví dụ:

~~~text
Goal: customerEligible

To prove customerEligible:
  check customerActive
  check accountInGoodStanding
~~~

Phù hợp với truy vấn kiểu "vì sao điều kiện này đúng?" hoặc "cần dữ liệu gì để chứng minh kết luận?".

### 11.3 Kết hợp

Một hệ thống có thể dùng forward chaining để cập nhật kết luận và backward chaining để giải thích hoặc truy vấn mục tiêu. Cần xác định rõ semantics và giới hạn recursion.

## 12. Chaining và phụ thuộc giữa các luật

Chaining xảy ra khi action của luật này thay đổi dữ liệu khiến luật khác được kích hoạt.

Ví dụ:

~~~text
rule "Identify preferred customer"
  when customer.totalSpent >= 50_000_000
  then insert PreferredCustomer(customer.id)

rule "Offer premium support"
  when PreferredCustomer(customer.id)
  then customer.supportLevel = PREMIUM
~~~

Luật đầu tạo fact PreferredCustomer. Luật thứ hai khớp fact đó và cập nhật supportLevel.

### 12.1 Positive chaining

Action tạo thêm facts hoặc điều kiện đúng, dẫn đến activation mới.

### 12.2 Negative condition

Một luật có thể phụ thuộc vào việc không tồn tại fact:

~~~text
when not ApprovalRecord(order.id)
then insert ApprovalRequired(order.id)
~~~

Khi có fact mới, điều kiện phủ định có thể không còn đúng. Engine cần xử lý activation đã tạo từ điều kiện absence.

### 12.3 Dependency graph

Có thể biểu diễn quan hệ giữa rule:

~~~text
Rule A --creates CustomerRisk--> Rule B
Rule B --creates ManualReview--> Rule C
~~~

Dependency graph giúp phân tích thứ tự, vòng lặp và khả năng song song.

### 12.4 Không giả định thứ tự chỉ từ tên rule

Tên hoặc vị trí trong file không tự tạo dependency. Nếu rule B cần kết quả của rule A, hãy thể hiện qua facts, phase hoặc dependency contract.

## 13. Vòng lặp và điều kiện dừng

Một tập luật có thể tự kích hoạt vô hạn nếu action tạo điều kiện khiến chính luật đó hoặc luật khác chạy lại.

Ví dụ:

~~~text
rule "Increase score"
  when customer.score >= 0
  then customer.score = customer.score + 1
~~~

Điều kiện vẫn đúng sau mỗi lần firing, nên luật có thể chạy mãi.

### 13.1 No-loop

Một số engine có tùy chọn tránh activation mới của chính rule do action của nó tạo ra. Đây là một chính sách tiện ích nhưng không thay thế phân tích vòng lặp toàn hệ thống.

### 13.2 Activation groups

Một activation group có thể quy định khi một rule trong nhóm fire thì các activation còn lại bị hủy. Điều này hữu ích cho các lựa chọn loại trừ nhau.

### 13.3 Rule firing limit

Engine có thể đặt giới hạn số lần firing hoặc số bước suy luận cho một lần chạy.

### 13.4 Time budget

Có thể giới hạn thời gian xử lý để tránh một tập luật chiếm tài nguyên vô hạn. Khi vượt giới hạn, engine cần trả trạng thái rõ ràng, không giả vờ đã đánh giá hết.

### 13.5 Cycle detection

Có thể theo dõi trạng thái facts hoặc fingerprint để phát hiện một chu kỳ lặp. Việc so sánh state cần xét những dữ liệu có ý nghĩa với semantics, không chỉ object identity.

### 13.6 Termination policy

Một execution có thể kết thúc vì:

- Không còn activation.
- Gặp halt.
- Đạt firing limit.
- Hết time budget.
- Bị cancellation.
- Có lỗi không thể phục hồi.

Các kết quả này cần được phân biệt trong response và audit.

## 14. Thứ tự hành động và tác dụng phụ

Action có thể làm thay đổi state hoặc tương tác với hệ thống bên ngoài. Vì vậy, thứ tự thực thi thường có ý nghĩa.

Ví dụ:

~~~text
rule "Reserve inventory"
  when order.status == NEW
  then reserve(order.items)

rule "Charge payment"
  when order.inventoryReserved
  then charge(order.payment)
~~~

Nếu charge chạy trước reserve, hành vi có thể sai.

### 14.1 Pure action và effectful action

Pure action chỉ tính kết quả mà không thay đổi trạng thái bên ngoài. Effectful action có thể ghi dữ liệu, gửi event hoặc gọi dịch vụ.

Tách hai loại giúp:

- Dễ kiểm thử.
- Dễ retry.
- Dễ chạy song song phần thuần.
- Quản lý transaction và lỗi tốt hơn.

### 14.2 Action order

DSL cần định nghĩa:

- Các statement trong một action chạy theo thứ tự nào?
- Nếu statement đầu thành công nhưng statement sau thất bại thì sao?
- Có rollback không?
- Có tiếp tục với statement sau không?

### 14.3 Transaction

Nếu action cập nhật nhiều bản ghi cần tính nhất quán, có thể thực thi trong transaction. Transaction boundary nên được định nghĩa ở cấp rule, activation, batch hoặc decision session.

### 14.4 External side effects

Gửi email hoặc gọi API không tự động rollback khi rule thất bại. Nên cân nhắc outbox pattern, idempotency key hoặc workflow compensation.

### 14.5 Không thực hiện side effect trong condition

Condition có thể được đánh giá nhiều lần khi facts thay đổi. Nếu condition gửi email hoặc tăng counter, engine có thể lặp side effect ngoài ý muốn.

Giữ condition thuần và đặt tác động vào action giúp semantics rõ hơn.

## 15. Idempotency và retry

Rule engine có thể chạy lại một activation do retry, phục hồi session hoặc xử lý thông điệp ít nhất một lần.

Idempotent action là action mà thực hiện lặp lại không làm thay đổi kết quả ngoài lần đầu theo semantics đã định.

Ví dụ, thao tác đặt trạng thái order thành APPROVED thường dễ idempotent hơn thao tác cộng thêm một khoản tiền vào balance.

### 15.1 Idempotency key

Có thể dùng khóa từ rule ID, fact identity và decision ID:

~~~text
idempotencyKey =
  ruleId + decisionId + factId
~~~

Hệ thống nhận action có thể từ chối xử lý lại cùng khóa.

### 15.2 Retry policy

Retry cần xác định:

- Loại lỗi được retry.
- Số lần tối đa.
- Backoff.
- Timeout.
- Idempotency.
- Hành vi khi hết retry.

Không retry mọi lỗi như lỗi validation hoặc lỗi quyền truy cập.

### 15.3 At-least-once và exactly-once

Trong hệ thống phân tán, bảo đảm exactly-once end-to-end thường khó. Thực tế thường kết hợp at-least-once delivery với idempotent processing và deduplication.

## 16. Kết quả quyết định và giải thích

Một rule system không chỉ cần thực thi; nó còn cần giải thích vì sao quyết định được đưa ra.

Ví dụ:

~~~text
Decision: REVIEW_REQUIRED

Matched rules:
  - high-risk-customer
  - large-order-review

Facts:
  - customer.riskScore = 85
  - order.total = 12_000_000
~~~

### 16.1 Activation trace

Trace có thể ghi:

- Rule nào được đánh giá.
- Condition nào khớp.
- Fact nào tham gia match.
- Activation nào được tạo.
- Priority và thứ tự firing.
- Action nào đã chạy.
- Fact nào thay đổi.

### 16.2 Explanation tree

Với quyết định phức tạp, có thể hiển thị cây giải thích:

~~~text
REVIEW_REQUIRED
   |
   +-- high-risk-customer
   |      |
   |      +-- riskScore >= 80
   |
   +-- large-order-review
          |
          +-- total >= 10,000,000
~~~

### 16.3 Vì sao một rule không chạy?

Hệ thống có thể giải thích:

- Rule bị disable.
- Condition false.
- Condition unknown.
- Không có fact phù hợp.
- Activation bị loại bởi conflict policy.
- Rule nằm ngoài effective date.
- Rule bị giới hạn bởi execution mode.

### 16.4 Audit

Với quyết định quan trọng, cần lưu rule version, input snapshot hoặc reference, thời điểm, actor, kết quả và lý do. Không ghi dữ liệu cá nhân hoặc secret vượt quá yêu cầu audit.

## 17. Tập luật, nhóm và phạm vi áp dụng

Một hệ thống thực tế có thể có hàng trăm hoặc hàng nghìn rule. Cần tổ chức chúng.

### 17.1 Rule package

Package nhóm các rule theo miền hoặc chức năng:

~~~text
pricing/
  discounts.rules
  shipping.rules

risk/
  customer-risk.rules
  transaction-risk.rules
~~~

### 17.2 Rule group

Group có thể dùng để:

- Chạy một tập luật theo phase.
- Bật/tắt một nhóm.
- Áp dụng priority riêng.
- Quản lý phiên bản.
- Giới hạn scope.

### 17.3 Effective date

Rule có thể có ngày bắt đầu và kết thúc hiệu lực. Cần định nghĩa timezone, inclusive/exclusive boundary và hành vi khi clock không đáng tin cậy.

### 17.4 Tenant hoặc organization scope

Trong hệ thống nhiều tổ chức, rule có thể áp dụng theo tenant. Engine phải bảo đảm facts của tenant này không bị dùng để kích hoạt luật của tenant khác.

### 17.5 Rule inheritance

Một nhóm luật có thể kế thừa rule chung và override một số thuộc tính. Cần quy định rõ override condition/action có thay thế toàn bộ hay merge từng phần.

### 17.6 Enablement

Bật/tắt rule nên có trạng thái rõ và provenance. Một rule bị disable không nên tạo activation dù condition đúng.

## 18. Decision table và condition-action rules

Decision table là cách biểu diễn nhiều trường hợp điều kiện và kết quả dưới dạng bảng. Nó thường được biên dịch thành một tập rule hoặc decision logic.

Ví dụ:

| Customer tier | Order total | Discount |
|---|---:|---:|
| STANDARD | Dưới 1 triệu | 0% |
| STANDARD | Từ 1 triệu | 5% |
| GOLD | Dưới 1 triệu | 5% |
| GOLD | Từ 1 triệu | 10% |

### 18.1 Hit policy

Nếu nhiều hàng cùng khớp, decision table cần hit policy:

- Unique: chỉ một hàng được khớp.
- First: dùng hàng đầu tiên theo thứ tự.
- Priority: chọn kết quả có priority cao nhất.
- Any: nhiều hàng được phép khớp nếu output tương đương.
- Collect: thu thập hoặc tổng hợp nhiều kết quả.

Tên và semantics cụ thể phụ thuộc chuẩn hoặc DSL được dùng.

### 18.2 Chuyển bảng thành rule

Mỗi hàng có thể thành một condition-action rule. Tuy nhiên, cần giữ hit policy khi compile; chỉ sinh các rule độc lập có thể làm thay đổi kết quả khi nhiều hàng cùng khớp.

### 18.3 Khi nào dùng decision table?

Decision table phù hợp khi:

- Nhiều tổ hợp điều kiện đơn giản.
- Người dùng cần nhìn toàn bộ trường hợp.
- Cần phát hiện khoảng trống hoặc chồng lấn.

Condition-action rules linh hoạt hơn khi hành động phức tạp, có chaining hoặc cần tương tác với facts.

## 19. Hiệu năng của rule matching

Khi số lượng rule và facts tăng, việc kiểm tra mọi condition trên mọi fact có thể rất tốn kém.

### 19.1 Naive evaluation

Một engine đơn giản có thể duyệt mọi rule và đánh giá condition mỗi lần dữ liệu thay đổi. Cách này dễ triển khai nhưng chi phí tăng theo số rule và số fact.

### 19.2 Indexing

Có thể index facts theo loại, field hoặc giá trị để nhanh chóng loại bỏ candidate không thể khớp.

### 19.3 Rete-style network

Một số rule engine dùng mạng matching kiểu Rete để chia sẻ kết quả kiểm tra giữa các rule và chỉ cập nhật phần bị ảnh hưởng khi facts thay đổi.

Mô hình khái quát:

~~~text
Facts
  |
  v
Type / attribute tests
  |
  v
Join nodes
  |
  v
Partial matches
  |
  v
Activations
~~~

Rete là một chiến lược matching, không phải yêu cầu bắt buộc của mọi DSL rule engine.

### 19.4 Incremental matching

Khi một fact được update, engine có thể chỉ đánh giá lại các node phụ thuộc vào loại fact và field bị thay đổi.

### 19.5 Cardinality

Join nhiều tập facts có thể tạo ra rất nhiều tổ hợp. Cần giới hạn hoặc tối ưu join, tránh tạo activation explosion.

### 19.6 Profiling

Metrics hữu ích:

- Số condition evaluations.
- Số partial matches.
- Số activation tạo/hủy.
- Thời gian firing theo rule.
- Số lần update facts.
- Số lần rule được đánh giá lại.

## 20. Determinism và khả năng tái lập

Với cùng tập facts, cùng phiên bản rule và cùng configuration, engine nên tạo kết quả ổn định nếu hợp đồng yêu cầu deterministic execution.

### 20.1 Các nguồn không xác định

- Thứ tự iteration collection.
- Timestamp hiện tại.
- Random number.
- Dữ liệu remote thay đổi.
- Parallel firing.
- Priority tie không có tie-breaker.
- Side effect phụ thuộc môi trường.

### 20.2 Stable ordering

Nếu cần thứ tự xác định, hãy dùng priority và tie-breaker ổn định như rule ID hoặc activation key.

### 20.3 Parallel execution

Chỉ chạy song song các activation khi có thể chứng minh chúng độc lập hoặc có cơ chế đồng bộ phù hợp. Hai action cùng ghi một fact có thể tạo race và kết quả không xác định.

### 20.4 Execution record

Lưu:

- Rule set version.
- Engine version.
- Input/fact snapshot reference.
- Configuration fingerprint.
- Clock hoặc effective time.
- Execution policy.

Nhờ đó có thể tái lập hoặc giải thích quyết định sau này.

## 21. Kiểm thử condition-action rules

Rule cần được kiểm thử ở nhiều cấp.

### 21.1 Condition tests

Kiểm tra condition:

- True.
- False.
- Null hoặc unknown.
- Boundary values.
- Type mismatch.
- Thiếu fact.

### 21.2 Action tests

Kiểm tra action:

- State sau thực thi.
- Fact được insert/update/retract.
- Diagnostic hoặc decision output.
- Error handling.
- Idempotency khi chạy lại.

### 21.3 Rule integration tests

Tạo facts, chạy engine và xác nhận:

- Activation được tạo đúng.
- Rule fire đúng số lần.
- Conflict policy được tuân thủ.
- Chaining tạo kết quả mong đợi.
- Không có vòng lặp vô hạn.

### 21.4 Negative tests

Kiểm tra luật không được kích hoạt khi:

- Condition false.
- Rule disabled.
- Fact thuộc tenant khác.
- Rule chưa đến ngày hiệu lực.
- Required field thiếu.

### 21.5 Conflict tests

Tạo nhiều luật cùng khớp và xác nhận thứ tự, exclusivity hoặc collect policy.

### 21.6 Property-based tests

Sinh nhiều input trong miền giá trị và kiểm tra invariant:

~~~text
for every order:
  discount >= 0
  discount <= configuredMaximum
~~~

### 21.7 Regression tests

Lưu các trường hợp quyết định quan trọng cùng rule version để phát hiện thay đổi hành vi ngoài ý muốn sau khi sửa rule hoặc engine.

## 22. Diagnostics và lỗi trong rule

Compiler nên phát hiện lỗi trước khi thực thi:

- Rule thiếu condition hoặc action.
- Condition không trả Boolean/truth value hợp lệ.
- Biến hoặc fact không được khai báo.
- Kiểu so sánh không tương thích.
- Action ghi vào field chỉ đọc.
- Rule ID trùng.
- Priority sai kiểu.
- Dependency hoặc group không tồn tại.
- Hành động không được phép.

Ví dụ diagnostic:

~~~text
Error: Condition must produce a Boolean value.
Rule: pricing.gold-discount
Expression: order.total + customer.tier
~~~

### 22.1 Runtime errors

Lỗi runtime có thể gồm:

- Fact đã bị xóa trước firing.
- Dịch vụ bên ngoài không sẵn sàng.
- Action vượt timeout.
- Transaction thất bại.
- Giá trị không còn thỏa invariant.

### 22.2 Rule-level error policy

Engine cần quy định lỗi của một action:

- Dừng toàn bộ session.
- Hủy activation hiện tại và tiếp tục.
- Retry theo policy.
- Đưa activation vào dead-letter hoặc error queue.

Không nên âm thầm bỏ qua lỗi của rule quan trọng.

### 22.3 Source location

Mỗi rule và expression nên giữ source range để diagnostics chỉ đúng dòng, cột hoặc node gây lỗi.

## 23. Bảo mật và quyền thực thi action

Condition-action rules có thể thực thi hành động quan trọng. Một rule độc hại hoặc cấu hình sai có thể làm thay đổi dữ liệu, gửi thông điệp hoặc gọi endpoint không mong muốn.

Các nguyên tắc:

- Chỉ cho phép action nằm trong allowlist.
- Không thực thi mã tùy ý từ file rule không tin cậy.
- Kiểm tra quyền của người tạo hoặc triển khai rule.
- Giới hạn truy cập facts theo tenant và scope.
- Giới hạn số lần firing và thời gian.
- Validate dữ liệu trước action.
- Audit rule version và action result.
- Không ghi secret vào trace.

### 23.1 Capability-based actions

Có thể chia action thành capability:

~~~text
read-order
update-decision
publish-event
send-notification
~~~

Rule chỉ được dùng capability đã cấp. Một rule tính discount không nhất thiết cần quyền gửi email hoặc xóa dữ liệu.

### 23.2 Sandbox

Nếu action có script, sandbox cần giới hạn file, network, reflection, thread và resource. Việc chạy script trong một interface hoặc class loader riêng không tự tạo sandbox an toàn.

### 23.3 Separation of duties

Người tạo rule, người phê duyệt và người triển khai có thể là các vai trò khác nhau đối với quyết định nhạy cảm.

## 24. Những sai lầm thường gặp

### Condition có side effect

Condition được đánh giá nhiều lần và có thể gửi thông báo hoặc thay đổi state lặp lại.

**Cách khắc phục:** giữ condition thuần; đặt side effect trong action.

### Không xác định conflict policy

Nhiều rule cùng khớp và ghi đè kết quả theo thứ tự không rõ.

**Cách khắc phục:** định nghĩa agenda, priority, tie-breaker và nhóm loại trừ.

### Coi priority là điều kiện loại trừ

Rule priority cao chạy trước nhưng rule thấp vẫn có thể chạy sau.

**Cách khắc phục:** dùng exclusive group hoặc first-match policy nếu chỉ cho phép một rule.

### Action cập nhật fact ngoài engine

Engine không biết dữ liệu thay đổi nên match index bị stale.

**Cách khắc phục:** cập nhật qua working-memory API hoặc cơ chế invalidation.

### Không kiểm soát vòng lặp

Action tạo điều kiện kích hoạt lại cùng luật vô hạn.

**Cách khắc phục:** phân tích dependency, no-loop, firing limit và cycle detection.

### Gọi dịch vụ ngoài trực tiếp trong action mà không có idempotency

Retry có thể gửi email hoặc trừ tiền nhiều lần.

**Cách khắc phục:** dùng idempotency key, outbox, transaction hoặc compensation.

### Không giữ rule version

Khó giải thích vì sao quyết định cũ khác quyết định hiện tại.

**Cách khắc phục:** lưu rule set version và execution metadata.

### Không phân biệt no-match với error

Không có rule khớp có thể là kết quả hợp lệ; lỗi thực thi là trạng thái khác.

**Cách khắc phục:** định nghĩa result type và diagnostics riêng.

### Chạy song song khi có shared state

Các action ghi cùng fact có thể race.

**Cách khắc phục:** phân tích dependency và chỉ parallelize khi an toàn.

## 25. Quy trình thiết kế condition-action rules

Khi thiết kế một rule hoặc tập luật, có thể thực hiện:

1. **Xác định mục tiêu nghiệp vụ:** quyết định hoặc phản ứng nào cần mô tả?
2. **Xác định facts:** dữ liệu nào là input, identity và scope của chúng?
3. **Viết condition:** biểu thức, kiểu, null semantics và binding.
4. **Viết action:** output hoặc thay đổi state cần thiết.
5. **Xác định effects:** action thuần hay có side effect?
6. **Đặt rule identity và metadata:** ID, description, owner và version.
7. **Định nghĩa conflict policy:** priority, order, exclusivity hoặc collect.
8. **Phân tích chaining:** action có tạo hoặc xóa facts kích hoạt luật khác không?
9. **Kiểm soát termination:** firing limit, timeout và cycle policy.
10. **Xác định transaction/idempotency:** retry và lỗi được xử lý ra sao?
11. **Thiết kế explanation:** lưu match, firing và lý do quyết định.
12. **Kiểm tra quyền:** action được phép truy cập những capability nào?
13. **Viết test:** boundary, no-match, conflict, chaining và regression.
14. **Version hóa và triển khai:** giữ snapshot rule set có thể tái lập.

## 26. Ví dụ tổng hợp: quyết định phê duyệt đơn hàng

Giả sử DSL nhận facts:

~~~text
Customer(id, tier, riskScore, active)
Order(id, customerId, total, status)
~~~

Tập luật:

~~~text
rule "Reject inactive customer"
  priority: 100
  when
    customer: Customer(active == false)
    order: Order(customerId == customer.id, status == NEW)
  then
    emit Decision(order.id, REJECT, "Customer is inactive")

rule "Require review for high risk"
  priority: 80
  when
    customer: Customer(riskScore >= 80)
    order: Order(customerId == customer.id, status == NEW)
  then
    emit Decision(order.id, REVIEW, "Risk score is high")

rule "Approve standard order"
  priority: 10
  when
    customer: Customer(active == true, riskScore < 80)
    order: Order(customerId == customer.id, total < 10_000_000, status == NEW)
  then
    emit Decision(order.id, APPROVE, "Standard checks passed")
~~~

### 26.1 Matching

Engine tìm Customer và Order có quan hệ customerId phù hợp, sau đó kiểm tra các điều kiện còn lại.

### 26.2 Conflict

Nếu một khách hàng không active nhưng riskScore cũng cao, hai luật đầu có thể cùng khớp. Priority có thể khiến luật reject chạy trước, nhưng cần xác định rõ liệu luật review có còn được phép chạy.

Nếu chỉ một kết quả được phép tồn tại, có thể dùng exclusive group hoặc thiết kế điều kiện để các rule loại trừ nhau.

### 26.3 Action

Các luật phát sinh Decision thay vì ghi trực tiếp nhiều field lên Order. Decision có outcome và reason, giúp audit và kiểm thử.

### 26.4 No match

Nếu không rule nào khớp, engine trả trạng thái NO_DECISION hoặc yêu cầu xử lý mặc định theo contract. Không nên tự coi no-match là APPROVE.

### 26.5 Explanation

Kết quả có thể kèm rule ID, version, facts đã khớp và condition evaluation để người vận hành hiểu vì sao đơn hàng bị reject, review hoặc approve.

## 27. Câu hỏi tự kiểm tra

1. Luật điều kiện và hành động gồm những thành phần nào?
2. Condition-action rule khác câu lệnh if-then trong code như thế nào?
3. Điều kiện AND, OR và NOT được đánh giá ra sao?
4. Vì sao cần type checking và null semantics cho condition?
5. Phân biệt rule, match, activation và firing.
6. Agenda và conflict resolution có vai trò gì?
7. Priority có tự động ngăn các rule khác chạy không?
8. Forward chaining và backward chaining khác nhau như thế nào?
9. Action insert/update/retract facts ảnh hưởng activation ra sao?
10. Vì sao condition nên thuần và side effect nên nằm trong action?
11. Chaining có thể tạo vòng lặp vô hạn như thế nào?
12. No-loop, activation group và firing limit giải quyết những vấn đề gì?
13. Idempotency giúp xử lý retry ra sao?
14. Decision table hit policy ảnh hưởng kết quả thế nào?
15. Rete-style matching hỗ trợ hiệu năng ra sao?
16. Những thông tin nào cần có trong execution trace để giải thích quyết định?
17. Vì sao cần lưu rule set version và input snapshot?
18. Những biện pháp nào hạn chế action nguy hiểm hoặc không được cấp quyền?

Luật điều kiện và hành động tách mô tả nghiệp vụ khỏi cơ chế điều phối thực thi. Khi condition có kiểu và semantics rõ, action được kiểm soát, conflict policy được công bố và vòng đời activation được quản lý, một DSL có thể biểu diễn các quyết định phức tạp theo cách dễ giải thích, kiểm thử và vận hành.

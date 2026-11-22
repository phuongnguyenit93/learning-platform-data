# Ngữ nghĩa động

## 1. Ngữ nghĩa động là gì?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), cú pháp cho biết người dùng được phép viết những cấu trúc nào. Ngữ nghĩa cho biết các cấu trúc đó có ý nghĩa gì. **Ngữ nghĩa động (dynamic semantics)** mô tả điều xảy ra khi một chương trình hoặc mô tả DSL được thực thi: giá trị được tính như thế nào, trạng thái thay đổi ra sao, thao tác nào được thực hiện và kết quả nào được tạo ra.

Ví dụ, một DSL chính sách có thể cho phép viết:

~~~text
discount "Gold member"
  when customer.tier == GOLD
   and order.total >= 2000000 VND
  then apply 10 percent
~~~

Cú pháp cho biết một chính sách có tên, có điều kiện và có hành động. Ngữ nghĩa động cần trả lời những câu hỏi cụ thể:

- Khi nào chính sách được đánh giá?
- customer.tier và order.total lấy từ đâu?
- Hai điều kiện được đánh giá theo thứ tự nào?
- Nếu điều kiện đầu tiên sai, điều kiện thứ hai có được đánh giá không?
- Nếu tổng đơn hàng không có giá trị hoặc dùng sai loại tiền thì sao?
- Nếu cả hai điều kiện đúng, khoản giảm giá được tính và áp dụng như thế nào?
- Việc áp dụng ưu đãi có thay đổi trạng thái đơn hàng không?
- Nếu thao tác lưu kết quả thất bại, hệ thống xử lý ra sao?

Một DSL có thể parse thành công nhưng vẫn có ngữ nghĩa động chưa được định nghĩa hoặc được triển khai không nhất quán. Ví dụ, hai backend cùng nhận một biểu thức nhưng xử lý null, thời gian hoặc thứ tự đánh giá khác nhau có thể tạo kết quả khác nhau. Vì vậy, ngữ nghĩa động phải được mô tả rõ và kiểm chứng trong môi trường thực thi.

## 2. Phân biệt ngữ nghĩa động với cú pháp và ngữ nghĩa tĩnh

Ba lớp thường được xem xét riêng:

| Lớp | Câu hỏi chính | Ví dụ |
|---|---|---|
| Cú pháp (syntax) | Cấu trúc này có được viết đúng grammar không? | Thiếu từ khóa then hoặc dấu ngoặc |
| Ngữ nghĩa tĩnh (static semantics) | Cấu trúc có hợp lệ theo kiểu, tên, phạm vi và quy tắc trước khi chạy không? | So sánh Money với Duration |
| Ngữ nghĩa động (dynamic semantics) | Khi chạy, cấu trúc thực hiện điều gì và tạo kết quả nào? | Đánh giá điều kiện rồi áp dụng mức giảm |

Xét biểu thức:

~~~text
order.total >= 2000000 VND
~~~

- Parser kiểm tra biểu thức có đúng grammar.
- Semantic analyzer kiểm tra order.total có kiểu tiền tệ và đơn vị có tương thích với VND.
- Runtime lấy giá trị tổng đơn hàng trong context, thực hiện phép so sánh và trả về kết quả Boolean hoặc lỗi theo hợp đồng DSL.

Kiểm tra tĩnh có thể phát hiện nhiều lỗi trước khi chạy, nhưng không thể luôn biết giá trị dữ liệu thực tế. Một thuộc tính có thể có kiểu Money hợp lệ nhưng lúc chạy không có dữ liệu. Ngược lại, ngữ nghĩa động không nên phải đoán những điều có thể xác định chắc chắn ở giai đoạn tĩnh.

## 3. Xác định đơn vị thực thi của DSL

Trước khi mô tả quy tắc động, cần xác định runtime thực thi những gì. Tùy DSL, đơn vị đó có thể là:

- Một biểu thức được đánh giá với context.
- Một rule được kiểm tra trên một đối tượng.
- Một policy gồm điều kiện và hành động.
- Một workflow gồm nhiều bước và trạng thái.
- Một file cấu hình được nạp rồi dùng để điều khiển ứng dụng.
- Một truy vấn được thực thi trên nguồn dữ liệu.
- Một khai báo tài nguyên được chuyển thành thao tác triển khai.

Không phải DSL nào cũng là ngôn ngữ lập trình tổng quát. Một DSL khai báo chính sách có thể không có vòng lặp, biến hay hàm do người dùng định nghĩa. Tuy vậy, nó vẫn có ngữ nghĩa động: runtime cần xác định cách kiểm tra chính sách, kết hợp kết quả và tạo tác động tương ứng.

### 3.1 Tách mô tả khỏi runtime

Một kiến trúc thường có các thành phần:

~~~text
DSL source
    |
    v
Lexer / Parser
    |
    v
AST / IR
    |
    v
Static validation
    |
    v
Runtime / Evaluator
    |
    +--> Environment / Context
    |
    +--> State
    |
    +--> Services / Effects
    |
    v
Result / State transition / Output
~~~

AST hoặc IR mô tả ý định của người dùng. Runtime cung cấp dữ liệu và quy tắc để diễn giải ý định đó. Việc tách hai phần giúp một mô tả có thể được kiểm tra, lưu trữ, đánh giá hoặc chạy trên các context khác nhau.

## 4. Environment và context khi thực thi

Một biểu thức thường cần dữ liệu bên ngoài để tạo kết quả. **Environment** hoặc **evaluation context** là tập thông tin mà runtime cung cấp trong lúc đánh giá.

Ví dụ:

~~~text
discount = order.total * 10 percent
~~~

Biểu thức cần biết order.total. Nếu DSL có thể tham chiếu customer.tier, ngày hiện tại hoặc cấu hình cửa hàng, các giá trị đó cũng cần được cung cấp.

Một context có thể gồm:

- Các giá trị đầu vào của giao dịch hoặc yêu cầu.
- Các biến và tham số đã được liên kết.
- Các đối tượng miền được phép truy cập.
- Đồng hồ hoặc thời điểm đánh giá.
- Cấu hình runtime và phiên bản chính sách.
- Các dịch vụ được phép gọi.
- Thông tin người dùng hoặc quyền thực thi.

Ví dụ mô hình Java:

~~~java
record EvaluationContext(
    Order order,
    Customer customer,
    Clock clock,
    String policyVersion
) {}
~~~

Đây là mô hình minh họa. Một context thực tế nên chỉ chứa dữ liệu và năng lực mà DSL cần. Không nên truyền toàn bộ application container hoặc một object có thể truy cập tùy ý mọi dịch vụ nếu chính sách chỉ cần đọc một vài thuộc tính.

### 4.1 Tra cứu tên và giá trị

Khi runtime gặp identifier như order.total, nó cần xác định:

1. Tên đó đã được phân giải ở giai đoạn tĩnh hay chưa.
2. Thuộc tính thuộc đối tượng nào.
3. Context hiện tại có cung cấp đối tượng đó không.
4. Giá trị có tồn tại và có kiểu phù hợp không.
5. Quyền truy cập có cho phép đọc giá trị đó không.

Nếu name resolution đã tạo symbol reference, runtime có thể dùng định danh đã phân giải thay vì tra cứu chuỗi tên lặp lại. Cách này giảm lỗi do gõ tên và làm rõ phạm vi.

### 4.2 Giá trị thiếu và null

Ngữ nghĩa động cần phân biệt:

- Giá trị có mặt và hợp lệ.
- Giá trị null.
- Thuộc tính không được cung cấp.
- Không tìm thấy đối tượng.
- Giá trị không thể đọc do lỗi nguồn dữ liệu.

Các trạng thái này có thể có cách xử lý khác nhau. Ví dụ, customer.middleName có thể null hợp lệ, nhưng order.total bị thiếu có thể là lỗi dữ liệu. Không nên tự động biến tất cả trường hợp thành false hoặc zero.

## 5. Môi trường, trạng thái và cấu hình

Trong ngôn ngữ có biến hoặc trạng thái thay đổi, runtime cần mô tả không chỉ giá trị hiện tại mà cả cách giá trị được lưu và cập nhật.

Một mô hình khái quát:

- **Environment** ánh xạ tên hoặc symbol đến vị trí lưu trữ.
- **Store** ánh xạ vị trí lưu trữ đến giá trị hiện tại.

Ký hiệu:

\[
\rho : Name \rightarrow Location
\]

\[
\sigma : Location \rightarrow Value
\]

Environment cho biết tên x tham chiếu vị trí nào; store cho biết vị trí đó đang chứa giá trị gì. Trong DSL khai báo bất biến, có thể chỉ cần environment ánh xạ tên đến giá trị mà không cần store mutable.

### 5.1 Ví dụ với biến

Giả sử DSL cho phép:

~~~text
let base = 100
let tax = 10
let total = base + tax
~~~

Runtime có thể:

1. Tính biểu thức 100 và gắn giá trị với base.
2. Tính biểu thức 10 và gắn giá trị với tax.
3. Tra cứu base và tax.
4. Tính tổng.
5. Gắn giá trị 110 với total.

Nếu DSL cho phép gán lại:

~~~text
let count = 1
count = count + 1
~~~

runtime phải xác định việc gán cập nhật vị trí hiện có hay tạo binding mới, phạm vi của biến và cách xử lý biến chưa khai báo.

### 5.2 Scope lồng nhau

Với block lồng nhau:

~~~text
let rate = 5
scope {
  let rate = 10
  apply rate
}
apply rate
~~~

DSL cần xác định quy tắc shadowing. Nếu block bên trong tạo binding mới, lần apply trong block dùng 10; lần apply bên ngoài dùng 5. Nếu shadowing bị cấm, khai báo thứ hai phải tạo lỗi. Đây là quy tắc ngữ nghĩa tĩnh kết hợp với hành vi tra cứu lúc chạy.

### 5.3 Thời điểm đọc cấu hình

Một giá trị cấu hình có thể được đọc khi:

- Nạp file DSL.
- Khởi tạo runtime.
- Bắt đầu một request.
- Đánh giá từng biểu thức.

Thời điểm đọc ảnh hưởng đến việc thay đổi cấu hình có tác dụng ngay hay chỉ có tác dụng với lần thực thi tiếp theo. Cần ghi rõ chính sách snapshot hoặc live reload để kết quả có thể dự đoán.

## 6. Quy tắc đánh giá biểu thức

Ngữ nghĩa động cần định nghĩa cách tính từng loại biểu thức. Ví dụ, với số học:

~~~text
1 + 2 * 3
~~~

Nếu phép nhân có precedence cao hơn phép cộng, kết quả là 7. Nếu runtime thực hiện từ trái sang phải mà không xét precedence, kết quả có thể thành 9. Cú pháp parse được không đủ để xác định cách tính; ngữ nghĩa phải quy định thứ tự nhóm và đánh giá.

### 6.1 Literal

Literal thường tự đánh giá thành giá trị tương ứng:

~~~text
42
"ACTIVE"
true
~~~

Runtime tạo các giá trị có kiểu Integer, String hoặc Boolean theo định nghĩa DSL. Với literal tiền, ngày hoặc thời lượng, runtime cần tạo kiểu miền đã quy định.

### 6.2 Identifier

Identifier được đánh giá bằng cách tra cứu trong environment hoặc context:

~~~text
order.total
~~~

Kết quả phụ thuộc vào đối tượng order của lần thực thi hiện tại. Nếu không có binding hoặc quyền truy cập, runtime trả lỗi có cấu trúc theo hợp đồng.

### 6.3 Toán tử nhị phân

Với biểu thức:

~~~text
left + right
~~~

Ngữ nghĩa cần quy định:

- Thứ tự đánh giá hai toán hạng.
- Kiểu nào được phép cộng.
- Có chuyển đổi kiểu ngầm hay không.
- Kết quả có kiểu gì.
- Trường hợp tràn số hoặc giá trị không hợp lệ.
- Có tác dụng phụ trong quá trình đánh giá hay không.

### 6.4 Toán tử logic và short-circuit

Với AND:

~~~text
conditionA and conditionB
~~~

DSL có thể quy định short-circuit: nếu conditionA là false, conditionB không được đánh giá vì kết quả toàn biểu thức đã xác định là false.

Với OR, nếu conditionA là true, conditionB có thể không cần đánh giá.

Short-circuit quan trọng khi biểu thức thứ hai có thể tốn chi phí, truy cập dữ liệu hoặc gây lỗi. Nếu DSL muốn biểu thức thuần và không tác dụng phụ, thứ tự vẫn nên được quy định để kết quả nhất quán.

### 6.5 Hàm và lời gọi dịch vụ

Một biểu thức gọi hàm:

~~~text
is_eligible(customer)
~~~

Runtime cần xác định hàm nào được gọi, tham số được đánh giá ra sao, quyền truy cập nào cần thiết và kết quả lỗi được truyền thế nào. Nếu DSL chỉ cho phép một tập hàm được đăng ký, tên hàm phải được phân giải và kiểm tra trước khi chạy.

Không nên để identifier trong DSL tự động trở thành lời gọi method tùy ý trên object Java. Hãy dùng registry hoặc API được kiểm soát để xác định năng lực mà DSL được phép sử dụng.

## 7. Thứ tự đánh giá

Thứ tự đánh giá có thể làm thay đổi kết quả khi biểu thức có tác dụng phụ, lỗi hoặc truy cập dữ liệu biến đổi.

Ví dụ:

~~~text
check_balance(account) and reserve_funds(account)
~~~

Nếu DSL đánh giá từ trái sang phải và short-circuit, reserve_funds chỉ chạy khi check_balance trả true. Nếu thứ tự không được định nghĩa, hai runtime có thể thực hiện khác nhau.

Cần quyết định:

- Toán hạng được đánh giá từ trái sang phải hay có quy tắc khác?
- Có short-circuit với AND/OR không?
- Đối số hàm được đánh giá trước hay trong lúc gọi?
- Một biểu thức có được đánh giá nhiều lần không?
- Runtime có được phép reorder biểu thức để tối ưu không?
- Các biểu thức có tác dụng phụ có bị cấm trong điều kiện không?

Với DSL khai báo, lựa chọn an toàn thường là biểu thức điều kiện thuần, có kết quả xác định từ context và không thay đổi trạng thái. Các hành động có tác dụng phụ nên được biểu diễn tách biệt.

## 8. Ngữ nghĩa của câu lệnh và cấu trúc điều khiển

Nếu DSL có câu lệnh, cần định nghĩa cách thực hiện theo thứ tự.

### 8.1 Sequence

~~~text
step A
step B
step C
~~~

Ngữ nghĩa tuần tự thường là thực hiện A, sau đó B, rồi C. Cần quy định điều gì xảy ra khi A thất bại: dừng ngay, chuyển sang nhánh lỗi, thử lại hay tiếp tục B.

### 8.2 Conditional

~~~text
if condition
  then actionA
  else actionB
~~~

Runtime đánh giá condition, sau đó thực hiện một nhánh theo kết quả. Nếu condition không xác định được hoặc phát sinh lỗi, DSL cần quy định đây là lỗi, nhánh mặc định hay một trạng thái riêng.

### 8.3 Repetition

Nếu DSL hỗ trợ lặp:

~~~text
repeat 3 times
  notify customer
~~~

Cần định nghĩa số lần lặp, thứ tự, hành vi khi một lần lặp lỗi và giới hạn tài nguyên. Không nên cho phép số lần lặp vô hạn nếu runtime không có cơ chế giới hạn.

### 8.4 Return, break và continue

Nếu DSL có các lệnh điều khiển luồng, cần xác định phạm vi tác động:

- return thoát khỏi rule, function hay toàn bộ workflow?
- break thoát khỏi vòng lặp gần nhất hay block được đặt tên?
- continue chuyển sang vòng lặp tiếp theo như thế nào?
- Lệnh có hợp lệ bên ngoài cấu trúc tương ứng không?

Một số điều kiện phạm vi có thể được kiểm tra tĩnh; hành vi khi thực thi cần được định nghĩa trong ngữ nghĩa động.

## 9. Ngữ nghĩa động của rule và policy

Nhiều DSL nghiệp vụ là ngôn ngữ khai báo rule hoặc policy. Chúng không nhất thiết có câu lệnh gán hay vòng lặp, nhưng vẫn cần quy tắc đánh giá.

Giả sử:

~~~text
rule "Gold discount"
  when customer.tier == GOLD
   and order.total >= 2000000 VND
  then discount 10 percent
~~~

Ngữ nghĩa cần xác định:

1. Rule được đánh giá trên một customer/order hay một tập dữ liệu?
2. Mỗi rule được đánh giá một lần hay nhiều lần?
3. Nếu nhiều rule cùng khớp thì xử lý tất cả hay chọn một?
4. Thứ tự ưu tiên được xác định bằng trường priority, thứ tự file hay một thuật toán khác?
5. Hành động được thực thi ngay hay chỉ tạo một đề xuất?
6. Nếu hành động thất bại, các hành động trước đó có được hoàn tác không?
7. Kết quả có được lưu cùng phiên bản rule đã áp dụng không?

### 9.1 Một rule trả kết quả hay gây tác động?

Có thể thiết kế rule theo hai hướng:

- **Evaluation thuần:** trả về kết quả như eligible, discount amount hoặc reason mà không thay đổi hệ thống bên ngoài.
- **Execution có tác động:** gửi thông báo, cập nhật đơn hàng hoặc tạo giao dịch.

Tách hai bước thường giúp hệ thống dễ kiểm thử và kiểm soát:

~~~text
evaluate(policy, context)
        |
        v
Decision / Proposed actions
        |
        v
authorize and execute
        |
        v
new state / effects
~~~

Kết quả đánh giá có thể được review hoặc kiểm tra quyền trước khi hành động thật được thực hiện.

### 9.2 Nhiều rule cùng khớp

Nếu hai rule cùng áp dụng, DSL cần quy định:

- Thực hiện cả hai hay chỉ một?
- Có thứ tự ưu tiên không?
- Có thể kết hợp kết quả không?
- Một rule có thể loại trừ rule khác không?
- Nếu hai hành động xung đột thì sao?

Ví dụ, một rule giảm giá 10% và một rule giảm 100.000 đồng cùng khớp. Runtime cần biết có cộng hai mức giảm, chọn mức lớn hơn hay áp dụng một chính sách ưu tiên. Không thể suy ra quyết định này chỉ từ grammar.

## 10. Ngữ nghĩa trạng thái và chuyển trạng thái

Một số DSL mô tả workflow, state machine hoặc quy trình nghiệp vụ. Trong trường hợp đó, ngữ nghĩa động tập trung vào cách hệ thống chuyển từ trạng thái này sang trạng thái khác.

Ví dụ:

~~~text
workflow "Order approval"
  state Draft
  state Submitted
  state Approved
  state Rejected

  transition Draft -> Submitted
    when submit_requested

  transition Submitted -> Approved
    when manager_approved

  transition Submitted -> Rejected
    when manager_rejected
~~~

Ngữ nghĩa cần xác định:

- Trạng thái khởi đầu.
- Sự kiện hoặc điều kiện kích hoạt transition.
- Transition nào hợp lệ từ mỗi trạng thái.
- Có thể có nhiều transition cùng thỏa điều kiện không.
- Hành động nào xảy ra khi vào hoặc rời trạng thái.
- Điều gì xảy ra khi sự kiện đến sai thứ tự.
- Trạng thái có được lưu bền vững không?

### 10.1 Transition như một hàm

Có thể mô hình hóa chuyển trạng thái:

\[
\delta : State \times Event \rightarrow State
\]

Trong đó \(\delta\) nhận trạng thái hiện tại và sự kiện, rồi trả về trạng thái tiếp theo. Nếu một sự kiện không hợp lệ, hàm có thể trả lỗi hoặc một kết quả từ chối rõ ràng.

Ví dụ:

~~~text
delta(Draft, SubmitRequested) = Submitted
delta(Submitted, ManagerApproved) = Approved
delta(Submitted, ManagerRejected) = Rejected
~~~

Một workflow phức tạp có thể cần thêm context, guard condition và effects:

\[
\delta(State, Event, Context) \rightarrow (State', Effects)
\]

Điều này tách quyết định chuyển trạng thái khỏi thao tác thực hiện bên ngoài.

### 10.2 Bất biến trạng thái

Ngữ nghĩa cần giữ các invariant. Ví dụ:

- Đơn hàng đã hủy không thể được phê duyệt.
- Giao dịch đã hoàn tất không thể bị ghi nhận hoàn tất lần thứ hai.
- Workflow không thể chuyển đến trạng thái không được khai báo.

Invariant có thể được kiểm tra trước và sau mỗi transition. Nếu vi phạm, runtime phải từ chối thay đổi hoặc chuyển sang cơ chế xử lý lỗi đã định nghĩa.

## 11. Tác dụng phụ và hiệu ứng

Một chương trình có thể đọc dữ liệu, ghi dữ liệu, gọi dịch vụ, gửi thông báo hoặc tạo tài nguyên. Các hành động này là **side effects** (tác dụng phụ).

Ví dụ:

~~~text
then
  reserve inventory
  charge payment
  send confirmation
~~~

Ngữ nghĩa động cần mô tả:

- Thứ tự các hành động.
- Điều kiện thực hiện từng hành động.
- Cách truyền kết quả giữa các bước.
- Hành động nào có thể thử lại.
- Hành động nào không thể hoàn tác.
- Cách xử lý khi một bước thất bại.

### 11.1 Tách biểu thức thuần và hành động

Biểu thức thuần (pure expression) chỉ tạo kết quả từ đầu vào, không thay đổi trạng thái bên ngoài. Ví dụ:

~~~text
order.total >= 2000000 VND
~~~

Hành động có tác dụng phụ có thể là:

~~~text
send_email(customer.email)
~~~

Tách hai loại giúp runtime dễ dự đoán và dễ kiểm thử. Điều kiện có thể được đánh giá nhiều lần mà không gây thêm tác động; hành động chỉ được gọi tại bước thực thi được xác định.

### 11.2 Mô hình effect

Một DSL có thể mô tả hành động như dữ liệu thay vì thực hiện ngay:

~~~text
Decision:
  eligible = true
  effects = [
    ApplyDiscount(10 percent),
    AddAuditEntry("Gold policy matched")
  ]
~~~

Ứng dụng nhận danh sách effect rồi kiểm tra quyền và thực thi. Cách này tạo ranh giới rõ giữa quyết định và tác động. Nó cũng giúp ghi log, review hoặc chạy mô phỏng trước khi áp dụng.

### 11.3 Retry và idempotency

Nếu một hành động gọi dịch vụ ngoài, timeout không cho biết dịch vụ đã thực hiện hay chưa. Thử lại có thể gây tác động trùng.

Ngữ nghĩa phải xác định:

- Hành động nào được phép retry.
- Có giới hạn số lần thử và khoảng chờ không.
- Có dùng idempotency key không.
- Kết quả không rõ ràng được xử lý thế nào.
- Có ghi nhận mã giao dịch để đối soát không.

Không nên định nghĩa retry như một vòng lặp đơn giản mà không xét tác động của thao tác.

## 12. Ngữ nghĩa lỗi và ngoại lệ

Một runtime cần phân biệt kết quả nghiệp vụ với lỗi thực thi.

Ví dụ:

- Không đủ điều kiện khuyến mãi: kết quả nghiệp vụ bình thường.
- Không tìm thấy thuộc tính bắt buộc: lỗi dữ liệu hoặc context.
- Chia cho zero: lỗi tính toán nếu DSL không định nghĩa kết quả khác.
- Không kết nối được dịch vụ: lỗi hạ tầng.
- Người dùng không có quyền: lỗi authorization hoặc kết quả từ chối theo hợp đồng.

Một mô hình kết quả có thể biểu diễn:

~~~java
sealed interface EvaluationResult {
    record Success(Value value) implements EvaluationResult {}
    record Rejected(String reason) implements EvaluationResult {}
    record Failure(Diagnostic diagnostic) implements EvaluationResult {}
}
~~~

Ví dụ trên là cách mô hình hóa minh họa. Cần quyết định lỗi nào được trả về, lỗi nào được ném exception và lỗi nào có thể phục hồi.

### 12.1 Fail-fast và tích lũy lỗi

Với một biểu thức cần giá trị để tiếp tục, runtime có thể dừng ngay khi gặp lỗi. Với validator kiểm tra nhiều trường độc lập, có thể thu thập nhiều lỗi rồi trả về cùng lúc.

Không nên trộn hai chiến lược mà không có quy tắc. Người dùng cần biết liệu runtime sẽ tiếp tục đánh giá các điều kiện sau một lỗi hay dừng toàn bộ policy.

### 12.2 Error propagation

Nếu một hàm con thất bại, lỗi có thể:

- Truyền lên biểu thức cha.
- Được bắt và chuyển thành kết quả nghiệp vụ.
- Được chuyển đến nhánh lỗi.
- Được ghi nhận và workflow chuyển sang trạng thái Failed.

Phạm vi catch và cách chuyển đổi lỗi là một phần của ngữ nghĩa động. Cần tránh nuốt lỗi rồi trả false vì điều đó có thể biến sự cố hệ thống thành quyết định nghiệp vụ sai.

## 13. Transaction và tính nguyên tử

Một policy có thể thực hiện nhiều thay đổi cần được xem như một đơn vị giao dịch.

Ví dụ:

~~~text
transaction:
  reserve inventory
  create order
  record payment
~~~

Nếu record payment thất bại sau khi inventory đã được reserve và order đã tạo, hệ thống cần xác định:

- Rollback toàn bộ thay đổi có thể rollback.
- Giữ lại trạng thái trung gian để xử lý tiếp.
- Phát hành compensation action để hoàn tác về mặt nghiệp vụ.
- Đánh dấu workflow cần người vận hành can thiệp.

### 13.1 Atomicity trong một transaction

Trong một database transaction, các thao tác có thể được commit cùng nhau hoặc rollback nếu thất bại. Nhưng transaction không tự động bao phủ email, API thanh toán hoặc dịch vụ ngoài.

### 13.2 Saga và compensation

Với workflow phân tán, có thể dùng saga: mỗi bước có hành động bù tương ứng nếu bước sau thất bại.

~~~text
reserve inventory
    |
    v
create order
    |
    v
charge payment
    |
    +--> success: complete
    |
    +--> failure: cancel order
                   release inventory
~~~

DSL workflow cần mô tả thứ tự, điều kiện và hành động bù nếu muốn runtime thực hiện theo mô hình này. Không nên giả định mọi tác dụng phụ đều có thể rollback như database.

## 14. Ngữ nghĩa thời gian

Nhiều quy tắc nghiệp vụ phụ thuộc thời gian:

~~~text
promotion is active when
  now >= starts_at
  and now < ends_at
~~~

Ngữ nghĩa động cần xác định now lấy từ đâu và được cố định ở thời điểm nào.

Các câu hỏi cần trả lời:

- Dùng instant tuyệt đối hay local date-time?
- Múi giờ nào áp dụng?
- Khoảng thời gian có bao gồm thời điểm bắt đầu và kết thúc không?
- Clock được đọc một lần cho toàn bộ policy hay mỗi lần gặp now?
- Khi chạy lại một quyết định cũ, dùng thời gian hiện tại hay thời gian sự kiện?

### 14.1 Inject clock

Không nên gọi trực tiếp system clock ở nhiều nơi nếu cần kết quả tái lập. Có thể truyền Clock vào context:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-12-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Test có thể cố định clock để kiểm tra chính xác ngày bắt đầu, ngày kết thúc và thời điểm biên.

### 14.2 Event time và processing time

Trong hệ thống xử lý sự kiện:

- **Event time** là thời điểm sự kiện thực sự xảy ra theo dữ liệu sự kiện.
- **Processing time** là thời điểm runtime xử lý sự kiện.

Hai thời điểm có thể khác nhau do mạng chậm hoặc dữ liệu đến muộn. DSL cần quy định điều kiện thời gian dựa trên thời điểm nào, đặc biệt với hạn chót, hiệu lực chính sách và xử lý sự kiện đến trễ.

## 15. Ngữ nghĩa đồng thời và thứ tự sự kiện

Nếu nhiều request hoặc event được xử lý cùng lúc, kết quả có thể phụ thuộc thứ tự cập nhật trạng thái.

Ví dụ, hai yêu cầu cùng kiểm tra một mã khuyến mãi chỉ còn một lượt sử dụng. Nếu cả hai cùng đọc số lượt còn lại trước khi một yêu cầu ghi cập nhật, hệ thống có thể áp dụng vượt giới hạn.

Ngữ nghĩa cần xác định:

- Một policy được đánh giá trên snapshot hay trạng thái mới nhất?
- Các transition có được tuần tự hóa không?
- Khi hai event cùng cập nhật một đối tượng, event nào được ưu tiên?
- Có kiểm soát phiên bản hoặc optimistic locking không?
- Event trùng lặp có được nhận diện không?
- Kết quả có bảo đảm thứ tự hay chỉ bảo đảm eventual consistency?

### 15.1 Determinism

Một phép đánh giá có tính xác định nếu cùng chương trình, cùng context và cùng trạng thái liên quan tạo cùng kết quả.

Tính xác định giúp:

- Kiểm thử dễ hơn.
- Tái hiện lỗi từ log.
- So sánh kết quả giữa các backend.
- Audit quyết định đã đưa ra.

Nếu runtime phụ thuộc random, clock, network hoặc trạng thái bên ngoài, những phụ thuộc đó cần được đưa vào context hoặc ghi lại để có thể tái hiện.

### 15.2 Race condition

Nếu một biểu thức đọc trạng thái rồi hành động dựa trên trạng thái đó, một request khác có thể thay đổi dữ liệu giữa hai bước. Cần dùng transaction, lock, version check hoặc một giao thức phù hợp để bảo vệ invariant.

DSL có thể mô tả ý định, nhưng runtime và hệ thống lưu trữ phải thực hiện cơ chế đồng bộ tương ứng. Không thể giải quyết race condition chỉ bằng cú pháp.

## 16. Trace và khả năng giải thích kết quả

Người dùng thường cần biết vì sao một rule được áp dụng hoặc bị từ chối. Runtime có thể tạo execution trace ghi lại các bước quan trọng:

~~~text
Rule: Gold member discount
  customer.tier == GOLD
    actual: GOLD
    result: true

  order.total >= 2000000 VND
    actual: 2500000 VND
    result: true

  action: apply 10 percent
  outcome: eligible
~~~

Trace có thể chứa:

- Rule hoặc policy được đánh giá.
- Phiên bản mô tả.
- Giá trị đầu vào đã được phép ghi nhận.
- Điều kiện và kết quả từng bước.
- Hành động được đề xuất hoặc thực thi.
- Thời gian và mã tương quan.
- Lỗi hoặc cảnh báo.

Không nên ghi mọi giá trị nhạy cảm vào log. Có thể chỉ ghi trạng thái, giá trị đã che hoặc lý do quyết định tùy yêu cầu audit và quyền riêng tư.

### 16.1 Trace không phải ngữ nghĩa

Trace giúp quan sát một lần thực thi; nó không thay thế định nghĩa ngữ nghĩa. Nếu thứ tự đánh giá hoặc cách xử lý lỗi không được quy định, log chỉ cho thấy implementation hiện tại đã làm gì.

## 17. Các mô hình hình thức mô tả ngữ nghĩa động

Có nhiều cách mô tả ngữ nghĩa. Ba hướng thường được nhắc đến là operational semantics, denotational semantics và axiomatic semantics.

### 17.1 Operational semantics

Operational semantics mô tả cách chương trình tiến triển qua các bước thực thi. Nó gần với cách xây interpreter hoặc runtime.

**Big-step semantics** mô tả quan hệ từ biểu thức ban đầu đến kết quả cuối:

\[
\langle e, \sigma \rangle \Downarrow v
\]

Có thể đọc là: biểu thức \(e\), khi chạy trong trạng thái \(\sigma\), đánh giá thành giá trị \(v\).

Ví dụ quy tắc cộng:

\[
\frac{
  \langle e_1,\sigma\rangle \Downarrow v_1
  \qquad
  \langle e_2,\sigma\rangle \Downarrow v_2
}{
  \langle e_1 + e_2,\sigma\rangle \Downarrow v_1 + v_2
}
\]

Quy tắc nói rằng nếu hai toán hạng đánh giá thành \(v_1\) và \(v_2\), biểu thức cộng đánh giá thành tổng của chúng.

**Small-step semantics** mô tả từng bước chuyển tiếp:

\[
e \rightarrow e'
\]

Ví dụ:

~~~text
(1 + 2) * 3
    -> 3 * 3
    -> 9
~~~

Small-step hữu ích khi cần mô tả thứ tự đánh giá, trạng thái trung gian, vòng lặp hoặc lỗi tại một bước cụ thể.

### 17.2 Denotational semantics

Denotational semantics ánh xạ một cấu trúc ngôn ngữ sang một đối tượng toán học biểu diễn ý nghĩa của nó.

Ví dụ:

\[
\llbracket e \rrbracket : Environment \rightarrow Value
\]

Ký hiệu \(\llbracket e \rrbracket\) biểu diễn ý nghĩa của biểu thức \(e\). Với một environment, nó trả về giá trị tương ứng.

Với biểu thức có trạng thái, kiểu ánh xạ có thể mở rộng để nhận store và trả về giá trị cùng store mới:

\[
\llbracket e \rrbracket : Environment \times Store
\rightarrow Value \times Store
\]

Denotational semantics giúp mô tả ý nghĩa ở mức trừu tượng, ít phụ thuộc vào cách runtime cài đặt.

### 17.3 Axiomatic semantics

Axiomatic semantics mô tả tính đúng của chương trình bằng các mệnh đề trước và sau khi thực thi. Một ký hiệu quen thuộc là Hoare triple:

\[
\{P\}\ C\ \{Q\}
\]

Trong đó:

- \(P\) là precondition trước khi chạy.
- \(C\) là câu lệnh hoặc chương trình.
- \(Q\) là postcondition sau khi chạy nếu chương trình kết thúc đúng theo giả định.

Ví dụ:

~~~text
{balance >= 100}
withdraw(100)
{balance = old(balance) - 100}
~~~

Mô hình này hữu ích khi DSL mô tả thao tác cần bảo đảm invariant, quyền hạn hoặc điều kiện trước/sau.

### 17.4 Chọn mức hình thức phù hợp

Không phải mọi DSL đều cần đặc tả toán học đầy đủ. Với DSL nhỏ, bảng quy tắc và ví dụ có thể đủ để thống nhất hành vi. Với DSL điều khiển tài chính, workflow phân tán hoặc nhiều backend, đặc tả hình thức giúp tránh cách hiểu khác nhau và hỗ trợ chứng minh tính chất quan trọng.

## 18. Ví dụ hoàn chỉnh: đánh giá và thực thi chính sách giảm giá

Xét DSL:

~~~text
policy "Gold discount"
  when customer.tier == GOLD
   and order.total >= 2000000 VND
  then discount 10 percent
~~~

### 18.1 Đầu vào

Context:

~~~text
customer.tier = GOLD
order.total = 2500000 VND
evaluation_time = 2026-12-15T10:00:00Z
~~~

### 18.2 Phân tích tĩnh

Trước khi chạy, hệ thống xác nhận:

- customer.tier là thuộc tính hợp lệ.
- GOLD thuộc kiểu CustomerTier.
- order.total có kiểu Money.
- Literal 2000000 VND có kiểu Money cùng đơn vị.
- Phần trăm 10 nằm trong giới hạn chính sách.
- Hành động discount hợp lệ trong context policy.

### 18.3 Đánh giá động

1. Runtime nhận context.
2. Đánh giá customer.tier == GOLD, kết quả true.
3. Vì vế đầu true, tiếp tục đánh giá order.total >= 2000000 VND.
4. Giá trị thực tế là 2500000 VND, kết quả true.
5. Toàn bộ điều kiện true.
6. Runtime tạo đề xuất giảm 10%.

Nếu cơ sở tính giảm giá là toàn bộ tổng đơn hàng, kết quả minh họa là 250000 VND. Nhưng quy tắc cơ sở tính phải được định nghĩa trong miền; không thể tự suy ra chỉ từ cú pháp.

### 18.4 Thực thi tác động

Ứng dụng có thể kiểm tra quyền và giới hạn trước khi áp dụng:

~~~text
Evaluation result:
  eligible = true
  proposed_discount = 250000 VND

Execution:
  validate discount limit
  apply discount to order
  record policy version
  append audit event
~~~

Nếu bước ghi audit thất bại, runtime phải có chính sách rõ: rollback thay đổi, retry hoặc đánh dấu cần đối soát. Đây là một phần của ngữ nghĩa động của hành động, không phải chi tiết cú pháp.

### 18.5 Trường hợp không đủ điều kiện

Nếu customer.tier là SILVER, điều kiện đầu false. Với AND short-circuit, runtime không cần đánh giá điều kiện tổng đơn hàng. Kết quả có thể là:

~~~text
eligible = false
reason = "CUSTOMER_TIER_NOT_ELIGIBLE"
~~~

Nếu DSL yêu cầu thu thập tất cả lý do không đạt, runtime có thể đánh giá cả hai điều kiện thay vì short-circuit. Hai chính sách này khác nhau và phải được chọn rõ.

## 19. Kiểm thử ngữ nghĩa động

Kiểm thử runtime nên dựa trên các quy tắc đã được xác nhận và context có thể tái lập.

### 19.1 Kiểm thử giá trị và điều kiện

Với mỗi toán tử và rule, cần có:

- Trường hợp đúng.
- Trường hợp sai.
- Giá trị đúng bằng ngưỡng.
- Giá trị thiếu hoặc null.
- Kiểu dữ liệu không hợp lệ nếu có thể lọt qua static validation.
- Giá trị biên theo giới hạn miền.

### 19.2 Kiểm thử thứ tự đánh giá

Dùng các biểu thức có thể quan sát số lần gọi hoặc tạo lỗi để xác nhận short-circuit:

~~~text
false and expensive_check()
true or expensive_check()
~~~

Nếu ngữ nghĩa quy định short-circuit, expensive_check không được gọi trong cả hai ví dụ trên.

### 19.3 Kiểm thử trạng thái

Với workflow hoặc DSL có gán:

- Kiểm tra trạng thái đầu.
- Kiểm tra transition hợp lệ.
- Từ chối transition không hợp lệ.
- Kiểm tra invariant trước và sau.
- Kiểm tra hành vi khi hai event cạnh tranh.

### 19.4 Kiểm thử tác dụng phụ

Dùng fake service hoặc transaction test để xác nhận:

- Hành động đúng được gọi.
- Thứ tự hành động đúng.
- Hành động không được gọi khi điều kiện sai.
- Retry không tạo tác động trùng.
- Lỗi được truyền hoặc bù theo chính sách.

### 19.5 Kiểm thử tính xác định

Chạy lại cùng chương trình với cùng context, clock và snapshot dữ liệu rồi so sánh kết quả. Nếu kết quả khác nhau, cần xác định phụ thuộc ẩn như random, trạng thái dùng chung hoặc thời gian hệ thống.

## 20. Những sai lầm thường gặp

### Chỉ mô tả grammar mà không mô tả hành vi

Một câu DSL có thể parse được nhưng không rõ thứ tự đánh giá, nguồn dữ liệu hoặc kết quả.

**Cách khắc phục:** với mỗi cấu trúc, viết ví dụ đầu vào, context, diễn biến và kết quả mong đợi.

### Để backend tự quyết định ngữ nghĩa

Java, SQL và JavaScript có thể khác nhau về null, số và thời gian.

**Cách khắc phục:** định nghĩa ngữ nghĩa chung ở cấp DSL hoặc IR, sau đó kiểm thử tương đương giữa các backend.

### Trộn điều kiện với tác dụng phụ

Một biểu thức điều kiện gọi dịch vụ hoặc thay đổi dữ liệu có thể tạo kết quả khó dự đoán khi được đánh giá nhiều lần.

**Cách khắc phục:** tách evaluation thuần khỏi execution effects.

### Coi mọi trường hợp không đạt là false

Dữ liệu thiếu, lỗi dịch vụ và không đủ điều kiện là những tình huống khác nhau.

**Cách khắc phục:** dùng kết quả và diagnostic có cấu trúc.

### Dựa vào thời gian hoặc trạng thái ẩn

Runtime đọc system clock hoặc dữ liệu thay đổi mà không ghi nhận có thể khiến quyết định không tái lập.

**Cách khắc phục:** đưa clock, snapshot và phụ thuộc vào context; ghi lại phiên bản dữ liệu cần thiết.

### Không định nghĩa hành vi khi nhiều rule cùng khớp

Kết quả có thể phụ thuộc thứ tự file hoặc thứ tự duyệt vô tình.

**Cách khắc phục:** định nghĩa rõ priority, combine, exclusion và xử lý xung đột.

### Giả định tác dụng phụ có thể rollback

Email hoặc API bên ngoài không thể được hoàn tác giống thay đổi trong database transaction.

**Cách khắc phục:** xác định transaction boundary, idempotency và compensation.

## 21. Quy trình đặc tả ngữ nghĩa động

Khi thiết kế một cấu trúc DSL mới, có thể đi theo các bước:

1. **Nêu mục đích:** cấu trúc dùng để tính toán, quyết định, chuyển trạng thái hay thực hiện hành động?
2. **Xác định context:** dữ liệu, biến, thời gian và dịch vụ nào được phép truy cập?
3. **Định nghĩa đánh giá:** giá trị đầu vào, thứ tự và kết quả của từng biểu thức.
4. **Định nghĩa trạng thái:** có thay đổi biến, workflow hoặc dữ liệu miền không?
5. **Định nghĩa effects:** thao tác bên ngoài nào được phép và theo thứ tự nào?
6. **Định nghĩa lỗi:** phân biệt từ chối nghiệp vụ, dữ liệu không hợp lệ và lỗi hạ tầng.
7. **Định nghĩa tính xác định:** phụ thuộc nào phải được cố định hoặc ghi lại?
8. **Định nghĩa cạnh tranh:** xử lý đồng thời, sự kiện trùng và dữ liệu đến muộn ra sao?
9. **Viết ví dụ thực thi:** cung cấp context, trace và kết quả mong đợi.
10. **Kiểm thử runtime:** kiểm tra trường hợp bình thường, biên, lỗi và tác dụng phụ.

Một đặc tả tốt nên được người hiểu nghiệp vụ và người phát triển cùng xác nhận. Người nghiệp vụ xác nhận quyết định và tác động có đúng chính sách không; người phát triển xác nhận runtime có thể thực hiện nhất quán và kiểm thử được không.

## 22. Câu hỏi tự kiểm tra

1. Phân biệt cú pháp, ngữ nghĩa tĩnh và ngữ nghĩa động.
2. Environment hoặc evaluation context cung cấp những thông tin nào cho runtime?
3. Phân biệt giá trị null, thuộc tính thiếu và lỗi khi đọc dữ liệu.
4. Vì sao thứ tự đánh giá có thể ảnh hưởng đến kết quả?
5. Short-circuit của AND và OR hoạt động như thế nào?
6. Phân biệt evaluation thuần với execution có tác dụng phụ.
7. Ngữ nghĩa của workflow cần định nghĩa những gì về state transition?
8. Vì sao retry có thể gây tác động trùng và idempotency giúp ích ra sao?
9. Phân biệt event time và processing time.
10. Operational semantics, denotational semantics và axiomatic semantics mô tả hành vi theo các cách nào?
11. Vì sao cần trace và phiên bản policy để giải thích quyết định?
12. Nêu các test cần có để kiểm chứng ngữ nghĩa động của một DSL.

Ngữ nghĩa động là hợp đồng về hành vi khi DSL chạy. Khi hợp đồng này xác định rõ context, thứ tự đánh giá, trạng thái, effects, lỗi và kết quả, runtime có thể triển khai nhất quán và người dùng có thể dự đoán điều gì sẽ xảy ra với mô tả của họ.

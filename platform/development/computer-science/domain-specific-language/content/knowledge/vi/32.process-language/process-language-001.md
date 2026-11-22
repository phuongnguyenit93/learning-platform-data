# Trạng thái và chuyển tiếp

Trong một DSL quy trình (workflow DSL), chương trình thường mô tả công việc kéo dài qua nhiều bước, chờ sự kiện, gọi dịch vụ bên ngoài và phản ứng với kết quả. Một quy trình không chỉ cần biết bước nào được thực hiện tiếp theo; nó còn cần ghi nhận hiện tại đang ở giai đoạn nào, điều kiện nào cho phép đi tiếp và sự kiện nào làm thay đổi tình trạng. Hai khái niệm trung tâm để mô tả hành vi đó là **trạng thái (state)** và **chuyển tiếp (transition)**.

Trạng thái mô tả tình trạng hiện tại của workflow, một bước, một yêu cầu hoặc một đối tượng nghiệp vụ. Chuyển tiếp là quy tắc biến hệ thống từ trạng thái này sang trạng thái khác khi một sự kiện xảy ra và các điều kiện liên quan được thỏa mãn. Ví dụ, một đơn hàng có thể đi từ PENDING sang CONFIRMED khi thanh toán được chấp nhận, hoặc sang CANCELLED khi người dùng hủy trước thời điểm xử lý.

Một workflow DSL thường cho phép khai báo trạng thái, trạng thái bắt đầu, trạng thái kết thúc, sự kiện kích hoạt, guard condition, hành động và quy tắc chuyển tiếp. Runtime diễn giải các khai báo đó để điều khiển quy trình. Mô hình rõ ràng giúp tránh trạng thái bất hợp lệ, xử lý lỗi và retry, đồng thời tạo lịch sử có thể quan sát và kiểm tra.

Bài học này trình bày mô hình trạng thái, state machine, transition, event, guard, action, vòng đời workflow, trạng thái song song và phân cấp, xử lý timeout và lỗi, tính nhất quán, lưu trữ trạng thái, versioning, bảo mật, kiểm thử và cách thiết kế một workflow DSL có ngữ nghĩa trạng thái rõ ràng.

## 1. Trạng thái là gì?

Trạng thái là mô tả về tình trạng hiện tại của một đối tượng hoặc tiến trình tại một thời điểm.

Ví dụ, đơn hàng có thể có các trạng thái:

~~~text
PENDING
CONFIRMED
PAID
FULFILLED
CANCELLED
FAILED
~~~

Workflow xử lý đơn hàng có thể có:

~~~text
CREATED
VALIDATING
WAITING_FOR_PAYMENT
PROCESSING
COMPLETED
REJECTED
~~~

Trạng thái trả lời câu hỏi: hệ thống đang ở đâu trong vòng đời nghiệp vụ? Nó có thể quyết định hành động nào được phép, sự kiện nào được chấp nhận và bước nào có thể chạy tiếp.

### 1.1. Trạng thái không chỉ là một nhãn

Một state thường có nhiều thông tin liên quan:

- Định danh trạng thái.
- Dữ liệu hoặc context hiện tại.
- Các sự kiện có thể được tiếp nhận.
- Các transition được phép.
- Các invariant cần được duy trì.
- Entry action hoặc exit action.
- Thời điểm bắt đầu hoặc kết thúc trạng thái.
- Metadata phục vụ quan sát và audit.

Ví dụ, WAITING_FOR_PAYMENT có thể giữ paymentRequestId, thời điểm hết hạn, số lần gửi yêu cầu và correlation ID để nhận phản hồi từ cổng thanh toán.

### 1.2. State và status

Trong thực tế, state và status đôi khi được dùng thay thế nhau. Có thể phân biệt:

- State là một phần của mô hình hành vi và xác định các chuyển tiếp hợp lệ.
- Status thường là trường biểu diễn trạng thái hiện tại trong dữ liệu hoặc giao diện.

Ví dụ, state machine định nghĩa đơn hàng chỉ được chuyển từ PENDING sang CONFIRMED sau khi kiểm tra hợp lệ. Trường status trong database lưu giá trị PENDING hoặc CONFIRMED.

Một status field tự do có thể chứa giá trị bất kỳ nếu không có constraint. State machine đặt ra quy tắc giá trị nào được phép và chuyển đổi ra sao.

### 1.3. Trạng thái hiện tại và lịch sử trạng thái

Trạng thái hiện tại là kết quả mới nhất của quá trình xử lý. Lịch sử trạng thái ghi lại các lần chuyển tiếp:

~~~text
10:00 CREATED
10:01 VALIDATING
10:02 WAITING_FOR_PAYMENT
10:05 PAYMENT_CONFIRMED
10:05 PROCESSING
10:08 COMPLETED
~~~

Lịch sử hữu ích cho audit, điều tra lỗi, báo cáo thời gian xử lý và tái dựng tiến trình. Không nên chỉ lưu trạng thái cuối nếu nghiệp vụ cần biết các bước trước đó.

## 2. State machine

State machine là mô hình mô tả một hệ thống bằng tập trạng thái và các quy tắc chuyển giữa chúng. Một state machine hữu hạn thường có:

- Tập trạng thái.
- Trạng thái bắt đầu.
- Tập trạng thái kết thúc hoặc chấp nhận.
- Tập sự kiện.
- Các quy tắc chuyển tiếp.
- Guard condition.
- Action được thực hiện khi chuyển tiếp.

Mô hình đơn giản:

~~~text
             submit
   +-------+ ---------> +---------+
   | DRAFT |            | PENDING |
   +-------+ <--------- +---------+
       |       edit          |
       |                     | approve
       | cancel              v
       v                 +----------+
   +-----------+         | APPROVED |
   | CANCELLED |         +----------+
   +-----------+              |
                              | complete
                              v
                         +-----------+
                         | COMPLETED |
                         +-----------+
~~~

Sơ đồ chỉ minh họa một phần vòng đời. Mô hình thực tế cần xác định cả nhánh từ chối, lỗi, timeout và quyền thực hiện transition.

### 2.1. Tập trạng thái

State set là tập trạng thái được khai báo cho một machine. Mỗi trạng thái cần có tên hoặc ID duy nhất trong phạm vi machine.

~~~text
state DRAFT
state SUBMITTED
state APPROVED
state REJECTED
state COMPLETED
~~~

Không nên tạo state chỉ để biểu diễn một thông tin phụ có thể lưu trong data field. Trạng thái nên phản ánh giai đoạn hoặc chế độ làm thay đổi hành vi của workflow.

### 2.2. Initial state

Initial state là trạng thái mà instance nhận khi được khởi tạo.

~~~text
initial state DRAFT
~~~

Một machine thường có đúng một initial state cho mỗi vùng trạng thái hoạt động. Nếu DSL cho phép nhiều initial state, cần có quy tắc lựa chọn xác định.

### 2.3. Final state

Final state biểu thị machine hoặc workflow đã kết thúc theo nghĩa nghiệp vụ.

~~~text
final state COMPLETED
final state REJECTED
final state CANCELLED
~~~

Final state không nhất thiết có nghĩa mọi tài nguyên đã được giải phóng hoặc mọi thông báo đã gửi. Runtime cần phân biệt kết thúc logic với công việc hậu xử lý nếu có.

### 2.4. Transition relation

Transition relation mô tả trạng thái nguồn, trigger, guard và trạng thái đích:

~~~text
transition DRAFT -> SUBMITTED
  on submit
~~~

Có thể bổ sung điều kiện:

~~~text
transition SUBMITTED -> APPROVED
  on approve
  when reviewer.hasPermission
~~~

### 2.5. Determinism

Một machine là deterministic trong một context nếu cùng trạng thái, cùng sự kiện và cùng dữ liệu liên quan chỉ dẫn đến một kết quả xác định.

Nếu hai transition cùng khớp, runtime cần quy tắc rõ: từ chối cấu hình mơ hồ, chọn theo priority hoặc cho phép nhiều nhánh song song nếu semantics hỗ trợ. Không nên dựa vào thứ tự tình cờ của danh sách khai báo.

## 3. Transition là gì?

Transition là quy tắc chuyển machine từ trạng thái nguồn sang trạng thái đích. Một transition thường được kích hoạt bởi event hoặc trigger, có thể có guard và thực hiện action.

Cấu trúc khái quát:

~~~text
transition SOURCE -> TARGET
  on EVENT
  when GUARD
  do ACTION
~~~

Ví dụ:

~~~text
transition PENDING -> CONFIRMED
  on payment.accepted
  when payment.amount == order.total
  do markOrderConfirmed(order)
~~~

Transition chỉ được thực hiện khi workflow đang ở PENDING, event phù hợp được tiếp nhận và guard trả true.

### 3.1. Source state

Source state là trạng thái hiện tại mà transition yêu cầu. Nếu machine không ở trạng thái này, event không kích hoạt transition đó.

### 3.2. Trigger

Trigger xác định sự kiện hoặc điều kiện làm transition được xét. Trigger có thể là:
- Domain event.
- User command.
- Timer.
- Kết quả action.
- Tín hiệu từ hệ thống ngoài.
- Completion của sub-workflow.

### 3.3. Guard

Guard là điều kiện Boolean quyết định transition có được phép thực hiện hay không. Guard thường được đánh giá trước khi action chuyển trạng thái chạy.

### 3.4. Target state

Target state là trạng thái mới sau khi transition thành công. Runtime cần xác định thời điểm state được cập nhật so với action, transaction và event emission.

### 3.5. Transition action

Action là công việc gắn với transition, ví dụ cập nhật dữ liệu, ghi audit record hoặc gửi command. Action có thể có side effect, vì vậy cần chính sách retry và lỗi rõ ràng.

### 3.6. Internal transition

Internal transition xử lý event nhưng không đổi state. Nó có thể cập nhật data hoặc phát action trong khi machine vẫn ở trạng thái hiện tại.

Ví dụ, khi đang WAITING_FOR_PAYMENT, event payment.reminderRequested có thể gửi nhắc nhở nhưng không đổi state.

### 3.7. External transition

External transition rời state hiện tại và vào state khác. Nó có thể kích hoạt exit action của state nguồn và entry action của state đích.

## 4. Event và trigger

Event biểu diễn một điều đã xảy ra. Trigger là điều làm runtime xét một transition. Trong nhiều DSL, event là trigger chính.

Ví dụ:

~~~text
event PaymentAccepted {
  orderId: OrderId
  paymentId: PaymentId
  amount: Decimal
  occurredAt: Instant
}
~~~

Event mang dữ liệu cần thiết để xử lý. Transition có thể sử dụng payload đó trong guard và action.

### 4.1. Event khác command

Command yêu cầu hệ thống thực hiện một việc; event thông báo một việc đã xảy ra.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Command | Yêu cầu thực hiện | ApproveOrder |
| Event | Sự kiện đã xảy ra | OrderApproved |
| Trigger | Điều làm transition được xét | on OrderApproved |
| Action | Công việc được thực hiện | SendConfirmation |

Một command có thể bị từ chối. Event thường biểu diễn kết quả đã được chấp nhận hoặc sự kiện đã xảy ra theo hợp đồng của producer.

### 4.2. Event payload

Payload cần có schema và version. Event có thể chứa:
- Entity ID.
- Event ID.
- Correlation ID.
- Causation ID.
- Thời điểm xảy ra.
- Phiên bản dữ liệu.
- Các thuộc tính nghiệp vụ.

Không nên đưa toàn bộ object lớn vào event nếu consumer chỉ cần một số định danh và giá trị cần thiết.

### 4.3. Event correlation

Một workflow có thể phát nhiều request và nhận nhiều phản hồi. Correlation ID hoặc business key giúp xác định event thuộc instance nào.

Ví dụ, payment.accepted cần liên kết với orderId và paymentRequestId để tránh một phản hồi cũ làm thay đổi đơn hàng khác.

### 4.4. Event ordering

Event có thể đến trễ hoặc sai thứ tự. Runtime cần xác định:
- Có yêu cầu thứ tự theo aggregate không?
- Có sequence number không?
- Event cũ có bị bỏ qua không?
- Event đến trước khi workflow sẵn sàng được lưu lại hay từ chối?
- Event trùng được xử lý ra sao?

### 4.5. Duplicate event

Message broker hoặc mạng có thể khiến cùng event được giao nhiều lần. Workflow cần idempotency hoặc deduplication để tránh thực hiện transition và side effect lặp ngoài ý muốn.

### 4.6. Event không có transition phù hợp

Khi event đến mà không có transition phù hợp, runtime có thể:
- Bỏ qua và ghi log.
- Lưu vào dead-letter hoặc unmatched-event queue.
- Đánh dấu lỗi instance.
- Chuyển sang handler mặc định.
- Trả kết quả từ chối nếu event là command.

Chính sách cần được cấu hình rõ và phù hợp với loại event.

## 5. Guard condition

Guard là biểu thức xác định transition có được phép hay không. Guard nên đọc dữ liệu hiện tại và event payload, rồi trả về kết quả Boolean.

Ví dụ:

~~~text
transition PENDING -> APPROVED
  on approveRequested
  when order.total <= approvalLimit
    and reviewer.role in [MANAGER, ADMIN]
~~~

### 5.1. Guard nên thuần

Guard tốt không thay đổi trạng thái, không gửi message và không thực hiện side effect. Nếu guard có side effect, runtime có thể gọi nó nhiều lần khi retry hoặc khi kiểm tra candidate transition, dẫn đến hành vi khó dự đoán.

### 5.2. Guard có thể dùng event payload

~~~text
transition WAITING_FOR_PAYMENT -> PAID
  on payment.accepted
  when event.orderId == order.id
    and event.amount == order.total
~~~

Điều kiện liên kết event với đúng instance và kiểm tra giá trị thanh toán.

### 5.3. Guard và quyền

Guard có thể thể hiện điều kiện nghiệp vụ như reviewer thuộc nhóm approver. Tuy nhiên, quyền truy cập cần được xác minh tại service có thẩm quyền. Không nên dựa vào dữ liệu role do client tự gửi.

### 5.4. Nhiều guard cùng trigger

Có thể có nhiều transition cùng nhận một event:

~~~text
transition SUBMITTED -> APPROVED
  on reviewCompleted
  when event.decision == APPROVE

transition SUBMITTED -> REJECTED
  on reviewCompleted
  when event.decision == REJECT
~~~

Nếu guard loại trừ nhau, kết quả rõ ràng. Nếu nhiều guard cùng true, runtime cần báo ambiguity hoặc áp dụng priority đã khai báo.

### 5.5. Guard false

Guard false không nhất thiết là lỗi. Nó có thể có nghĩa transition chưa đủ điều kiện. Runtime có thể tiếp tục tìm transition khác, giữ event chờ hoặc từ chối event tùy semantics.

Cần phân biệt guard false với lỗi khi đánh giá guard, chẳng hạn null dereference hoặc service timeout.

### 5.6. Guard phức tạp

Nếu guard dài, hãy tách thành predicate có tên:

~~~text
predicate canApprove(order, reviewer) {
  order.total <= reviewer.approvalLimit
    and reviewer.active
}
~~~

Việc đặt tên giúp dễ đọc, kiểm thử và tái sử dụng. Guard vẫn nên giữ tính thuần.

## 6. Entry action, exit action và transition action

Một state machine có thể gắn hành động vào ba thời điểm:

- Entry action: chạy khi machine đi vào state.
- Exit action: chạy khi machine rời state.
- Transition action: chạy như một phần của transition cụ thể.

Ví dụ:

~~~text
state WAITING_FOR_PAYMENT {
  onEntry:
    schedulePaymentTimeout(order.id, 15 minutes)

  onExit:
    cancelPaymentTimeout(order.id)
}

transition WAITING_FOR_PAYMENT -> PAID
  on payment.accepted
  do recordPayment(event.paymentId)
~~~

### 6.1. Entry action

Entry action thường dùng để khởi tạo timer, ghi nhận thời điểm bắt đầu, gửi thông báo hoặc chuẩn bị dữ liệu của state.

Cần xác định entry action chạy trước hay sau khi state được ghi bền vững. Nếu action thất bại, runtime có thể retry hoặc chuyển sang error state.

### 6.2. Exit action

Exit action dọn tài nguyên hoặc hủy công việc gắn với state cũ, chẳng hạn hủy timer khi payment đã đến.

Exit action cần idempotent nếu runtime có khả năng retry.

### 6.3. Transition action

Transition action thường thực hiện thay đổi gắn với sự kiện, ví dụ lưu payment result trước khi chuyển sang PAID.

Cần xác định action chạy trước hay sau khi cập nhật state và cách khôi phục nếu action thất bại.

### 6.4. Thứ tự thực thi

Một chính sách có thể là:

1. Nhận event và xác định candidate transition.
2. Đánh giá guard.
3. Chạy exit action.
4. Chạy transition action.
5. Ghi state mới và data.
6. Chạy entry action.
7. Phát event sau transition.

Đây không phải thứ tự bắt buộc cho mọi runtime. DSL cần định nghĩa transaction boundary và điểm commit. Thứ tự ảnh hưởng đến khả năng retry và tính nhất quán.

### 6.5. Action bất đồng bộ

Action có thể trả về kết quả sau một khoảng thời gian. Runtime cần xác định transition đã được commit trước khi chờ action hay chỉ hoàn tất khi action trả kết quả. Với action dài, có thể mô hình hóa state trung gian như PROCESSING hoặc WAITING.

## 7. Mô hình state machine trong workflow DSL

Một DSL có thể cung cấp cú pháp khai báo state machine trực tiếp.

~~~text
workflow orderLifecycle(order: Order) {
  initial state PENDING

  state CONFIRMED
  state PAID
  state FULFILLED
  state CANCELLED
  state FAILED

  final state FULFILLED
  final state CANCELLED
  final state FAILED

  transition PENDING -> CONFIRMED
    on confirm
    when order.isValid

  transition CONFIRMED -> PAID
    on payment.accepted

  transition PAID -> FULFILLED
    on shipment.delivered

  transition PENDING -> CANCELLED
    on cancel

  transition CONFIRMED -> CANCELLED
    on cancel
}
~~~

### 7.1. State declaration

Khai báo state xác định tập giá trị hợp lệ. Type checker hoặc validator cần đảm bảo mọi target state đều tồn tại.

### 7.2. Transition declaration

Mỗi transition tham chiếu state nguồn và đích. Validator cần kiểm tra tên state, trigger, guard và action có hợp lệ.

### 7.3. Initial và final

Initial state được dùng khi tạo instance. Final state xác định instance đã hoàn tất. Cần phân biệt final success với final failure nếu hệ thống cần báo cáo kết quả.

### 7.4. Default transition

Một số machine có thể có fallback transition khi không có transition cụ thể. Fallback cần được dùng cẩn thận vì có thể che giấu event không hợp lệ.

### 7.5. Transition priority

Nếu DSL cho phép priority, cần định nghĩa số nhỏ hay lớn được ưu tiên, hai transition cùng priority được xử lý ra sao và thứ tự có ổn định không.

### 7.6. Self-transition

Transition có source và target là cùng một state có thể:
- Chỉ chạy action mà không gọi exit/entry.
- Rời state rồi vào lại state.
- Cập nhật data và reset timer.

Các semantics này khác nhau. DSL nên phân biệt internal transition với external self-transition.

## 8. State data và context

State machine thường cần lưu dữ liệu nghiệp vụ trong một context. State biểu diễn giai đoạn; context chứa thông tin cần thiết để đánh giá guard và chạy action.

Ví dụ:

~~~text
context OrderProcess {
  orderId: OrderId
  customerId: CustomerId
  total: Decimal
  paymentId: PaymentId?
  retryCount: Integer
  lastError: String?
}
~~~

### 8.1. State không thay thế data

Không nên tạo state riêng cho mọi giá trị dữ liệu. Thay vì tạo state HAS_THREE_ITEMS, lưu itemCount trong context nếu số lượng chỉ là dữ liệu.

State nên đại diện cho các chế độ có ý nghĩa đối với luồng điều khiển.

### 8.2. State-dependent data

Một số dữ liệu chỉ có ý nghĩa ở một state. Ví dụ paymentId có thể bắt buộc sau khi vào PAID. Validator có thể hỗ trợ invariant theo state:

~~~text
invariant state == PAID implies paymentId != null
~~~

### 8.3. Context mutation

Action có thể cập nhật context. Cần xác định mutation có được phép trực tiếp hay phải thông qua command hoặc event. Một mô hình immutable state transition có thể tạo context mới thay vì sửa object cũ.

### 8.4. Context version

Khi lưu context, có thể dùng version hoặc revision để phát hiện cập nhật đồng thời. Điều này đặc biệt quan trọng khi nhiều worker xử lý event của cùng workflow instance.

### 8.5. Context schema evolution

Workflow có thể chạy nhiều ngày hoặc nhiều tháng. Context schema cần được version và có migration để instance cũ tiếp tục hoạt động khi DSL thay đổi.

## 9. Trạng thái workflow và trạng thái step

Một workflow thường có trạng thái tổng thể và trạng thái riêng của từng step.

### 9.1. Workflow state

Workflow có thể ở:
- CREATED.
- RUNNING.
- WAITING.
- SUSPENDED.
- COMPLETED.
- FAILED.
- CANCELLED.

### 9.2. Step state

Mỗi step có thể ở:
- PENDING.
- READY.
- RUNNING.
- WAITING.
- RETRYING.
- COMPLETED.
- SKIPPED.
- FAILED.
- COMPENSATED.

### 9.3. Quan hệ giữa hai cấp

Workflow RUNNING có thể chứa nhiều step COMPLETED, một step RUNNING và một step PENDING. Workflow WAITING có thể đang chờ một event ở một step cụ thể.

Không nên suy ra workflow state chỉ từ một step nếu có nhánh song song hoặc step tùy chọn.

### 9.4. Step transition

Một step có thể có vòng đời:

~~~text
PENDING -> READY -> RUNNING -> COMPLETED
                         |
                         +-> WAITING
                         |
                         +-> FAILED
                         |
                         +-> RETRYING
~~~

Runtime cần quy định khi nào step được READY, khi nào được schedule và khi nào đánh dấu COMPLETED.

### 9.5. Skip và cancellation

SKIPPED có thể có nghĩa điều kiện nhánh không chọn step. CANCELLED có thể có nghĩa execution bị hủy. Hai trạng thái không nên bị gộp nếu báo cáo và compensation cần phân biệt.

## 10. Trạng thái phân cấp

Một state có thể chứa các substate. Mô hình phân cấp giúp tránh lặp lại transition chung.

Ví dụ:

~~~text
state PROCESSING {
  initial state VALIDATING
  state RESERVING
  state CHARGING
  final state DONE
}
~~~

PROCESSING là composite state, gồm các state con.

### 10.1. Composite state

Composite state có thể có entry/exit action riêng. Khi vào PROCESSING, runtime vào substate initial. Khi rời composite state, cần xác định exit action của substate và composite state chạy theo thứ tự nào.

### 10.2. Transition ở cấp cha

Một transition khai báo ở cấp PROCESSING có thể áp dụng cho mọi substate, chẳng hạn cancel. Điều này tránh phải khai báo cancel từ từng state con.

### 10.3. Event bubbling

Nếu substate không xử lý event, runtime có thể chuyển event lên parent state để tìm handler. Quy tắc bubbling cần xác định rõ, nhất là khi parent và child cùng có transition phù hợp.

### 10.4. History state

History state cho phép quay lại substate trước đó khi vào lại composite state. Có thể lưu:
- Shallow history: nhớ substate trực tiếp.
- Deep history: nhớ toàn bộ cấu trúc state lồng nhau.

History hữu ích khi workflow tạm dừng rồi tiếp tục, nhưng cần xác định dữ liệu và timer có được khôi phục hay không.

### 10.5. Lợi ích và giới hạn

Phân cấp giúp mô hình ngắn gọn, nhưng quá nhiều cấp làm người đọc khó hiểu thứ tự xử lý event. Nên dùng khi nhiều state thực sự chia sẻ hành vi hoặc tạo thành một giai đoạn nghiệp vụ có ý nghĩa.

## 11. Trạng thái song song và vùng hoạt động

Một số quy trình có các nhánh độc lập chạy đồng thời. State machine có thể hỗ trợ orthogonal regions hoặc parallel states.

Ví dụ, sau khi xác nhận đơn hàng, hệ thống có thể đồng thời chuẩn bị vận chuyển và gửi hóa đơn:

~~~text
state PROCESSING {
  parallel {
    region shipping {
      initial state PREPARING
      state SHIPPED
    }

    region invoicing {
      initial state CREATING
      state ISSUED
    }
  }
}
~~~

### 11.1. Parallel region

Mỗi region có state machine con riêng. Workflow có thể cần tất cả region hoàn thành trước khi chuyển sang COMPLETED.

### 11.2. Join condition

Join condition xác định khi nào các nhánh song song đã đạt trạng thái cần thiết:

~~~text
transition PROCESSING -> COMPLETED
  when shipping.state == SHIPPED
    and invoicing.state == ISSUED
~~~

### 11.3. Race condition

Hai event có thể đến gần như đồng thời và cùng cố gắng thay đổi state hoặc context. Runtime cần cơ chế serialization, optimistic locking hoặc transaction để bảo vệ invariant.

### 11.4. Failure ở một nhánh

Nếu shipping thất bại nhưng invoicing đã hoàn tất, workflow cần chính sách:
- Retry nhánh shipping.
- Hủy nhánh invoicing nếu có thể.
- Chạy compensation.
- Đánh dấu workflow cần xử lý thủ công.

### 11.5. Cancellation propagation

Khi workflow bị cancel, các nhánh đang chạy cần nhận cancellation signal. Không phải action bên ngoài nào cũng có thể dừng ngay, vì vậy cần state như CANCELLING hoặc CANCEL_REQUESTED trước khi đạt CANCELLED.

## 12. Timeout và timer transition

Workflow có thể cần chuyển trạng thái khi hết thời gian chờ.

Ví dụ:

~~~text
state WAITING_FOR_PAYMENT {
  after 15 minutes -> PAYMENT_EXPIRED
}
~~~

### 12.1. Timer trigger

Timer có thể được tính từ:
- Lúc vào state.
- Lúc bắt đầu workflow.
- Một timestamp trong context.
- Một lịch biểu bên ngoài.

Cần xác định timezone và cách xử lý daylight saving nếu dùng thời gian lịch.

### 12.2. Deadline và duration

Duration là khoảng thời gian như 15 phút. Deadline là thời điểm tuyệt đối. Một workflow có thể lưu deadline rồi tính thời gian còn lại khi restart. Không nên chỉ dùng bộ đếm trong memory nếu instance cần tồn tại qua process restart.

### 12.3. Timer cancellation

Khi rời state WAITING_FOR_PAYMENT do payment đến, timer cần được hủy hoặc đánh dấu stale. Nếu timer event vẫn được giao sau đó, guard phải ngăn nó làm đơn hàng PAID chuyển thành EXPIRED.

### 12.4. Timeout transition

Timeout có thể là một transition riêng:

~~~text
transition WAITING_FOR_PAYMENT -> PAYMENT_EXPIRED
  on payment.timeout
~~~

Event timeout nên có instance ID, timer ID và generation hoặc token để nhận biết timer cũ.

### 12.5. Clock và test

Để test timer, runtime nên cho phép inject clock hoặc scheduler giả lập. Không cần chờ 15 phút thật để kiểm tra một transition timeout.

## 13. Retry, lỗi và trạng thái phục hồi

Action có thể thất bại do mạng, service tạm thời không khả dụng hoặc dữ liệu không hợp lệ. Workflow cần phân biệt lỗi có thể retry và lỗi không thể phục hồi tự động.

### 13.1. Retry state

Một step có thể chuyển:

~~~text
RUNNING -> FAILED_TEMPORARY -> RETRY_WAIT -> RUNNING
~~~

Hoặc runtime giữ state RUNNING và quản lý attempt riêng. Dù chọn cách nào, trạng thái cần thể hiện được retry đang diễn ra.

### 13.2. Retry policy

Một policy có thể khai báo:

~~~text
retry {
  maxAttempts: 5
  initialDelay: 2 seconds
  multiplier: 2
  maxDelay: 1 minute
  jitter: true
}
~~~

Backoff giảm áp lực lên dịch vụ đang lỗi. Jitter tránh nhiều workflow retry đồng thời.

### 13.3. Phân loại lỗi

Có thể phân loại:
- Transient: timeout, kết nối tạm mất.
- Permanent: dữ liệu không hợp lệ, tài khoản không tồn tại.
- Business rejection: nghiệp vụ từ chối hợp lệ.
- Technical failure: lỗi runtime hoặc bug.
- Unknown: chưa phân loại được.

Không nên retry mọi lỗi giống nhau. Retry lỗi permanent có thể lãng phí tài nguyên và tạo side effect.

### 13.4. Error transition

Một state machine có thể định nghĩa transition khi action thất bại:

~~~text
transition CHARGING -> PAYMENT_FAILED
  on action.failed
  when error.kind == PERMANENT
~~~

Transient error có thể đưa đến RETRY_WAIT; permanent error có thể kết thúc hoặc chuyển sang xử lý thủ công.

### 13.5. Dead-letter và manual intervention

Sau số lần retry tối đa, workflow có thể chuyển sang MANUAL_REVIEW hoặc DEAD_LETTER. Cần lưu nguyên nhân, attempt, input liên quan và correlation ID để người vận hành xử lý.

### 13.6. Compensation

Nếu một bước đã tạo side effect và bước sau thất bại, workflow có thể cần hành động bù. Ví dụ, nếu đã reserve inventory nhưng charge payment thất bại, hệ thống có thể release inventory.

Compensation không phải rollback database tự động; nó là hành động nghiệp vụ riêng và cũng có thể thất bại. Mỗi compensation cần idempotency, timeout, retry và audit.

## 14. Transaction và tính nhất quán của transition

Transition có thể cập nhật context, lưu state và phát event. Các thao tác này cần có chính sách nhất quán.

### 14.1. Atomic state change

Một transition logic có thể cần đảm bảo:
- State nguồn vẫn đúng tại thời điểm commit.
- Guard được đánh giá trên dữ liệu phù hợp.
- Action nội bộ và context update nhất quán.
- State đích được lưu.
- Event phát ra không bị mất hoặc phát lặp ngoài ý muốn.

### 14.2. Optimistic concurrency

Mỗi instance có thể có version. Khi xử lý event, runtime đọc version v, tính transition và ghi với điều kiện version vẫn là v. Nếu worker khác cập nhật trước, thao tác conflict và cần đọc lại hoặc retry.

### 14.3. Compare-and-set

Một transition có thể được lưu bằng điều kiện:

~~~sql
UPDATE WorkflowInstance
SET state = 'PAID', version = version + 1
WHERE id = :id
  AND state = 'WAITING_FOR_PAYMENT'
  AND version = :expectedVersion;
~~~

Nếu số dòng cập nhật bằng 0, state đã thay đổi hoặc version không còn khớp.

### 14.4. Transactional outbox

Nếu transition cập nhật database và cần phát event ra message broker, hai thao tác này không tự động atomic nếu nằm ở hai hệ thống khác nhau.

Transactional outbox lưu event cần phát trong cùng transaction với state update. Một publisher riêng gửi outbox record đến broker và đánh dấu đã gửi.

### 14.5. Exactly-once và thực tế giao nhận

Nhiều hệ thống message cung cấp at-least-once delivery. Workflow nên thiết kế idempotent handler, event deduplication và transactional state update thay vì giả định event chỉ đến đúng một lần.

### 14.6. State commit và action ngoài hệ thống

Một HTTP request hoặc thao tác thanh toán không thể tự động nằm trong database transaction cục bộ. Cần thiết kế trạng thái trung gian, idempotency key, timeout và reconciliation để xử lý trường hợp kết quả bên ngoài không rõ ràng.

## 15. Persistence và khôi phục workflow

Workflow dài hạn cần lưu state và context để có thể tiếp tục sau khi process restart.

### 15.1. Dữ liệu cần lưu

Một workflow instance có thể lưu:
- Instance ID.
- Workflow definition ID và version.
- Current state.
- Context data.
- Active timers.
- Pending events hoặc subscriptions.
- Attempt và retry metadata.
- Parent/child instance IDs.
- Version hoặc revision.
- Timestamps.
- Error và correlation metadata.

### 15.2. Checkpoint

Checkpoint là trạng thái đã được lưu bền vững tại một thời điểm. Runtime có thể khôi phục instance từ checkpoint và tiếp tục chờ event hoặc chạy step kế tiếp.

### 15.3. Restart recovery

Khi runtime khởi động lại:
1. Tải instance chưa kết thúc.
2. Kiểm tra workflow definition version.
3. Khôi phục context và state.
4. Khôi phục timer hoặc subscription.
5. Phát hiện action đang chạy dở.
6. Áp dụng chính sách resume, retry hoặc reconcile.
7. Tiếp tục xử lý event.

Không nên tự động chạy lại mọi action đang ở trạng thái RUNNING nếu action có side effect và không có idempotency.

### 15.4. Event sourcing

Một số hệ thống lưu chuỗi event thay vì chỉ lưu snapshot state. Current state được dựng lại bằng cách replay event.

Event sourcing hỗ trợ audit và temporal reconstruction nhưng đòi hỏi event schema ổn định, migration và snapshot để tránh replay quá lâu.

### 15.5. Snapshot và history

Snapshot giảm chi phí replay. Lịch sử event vẫn cần được giữ theo chính sách lưu trữ và bảo mật. Cần xác định dữ liệu nào có thể xóa hoặc ẩn danh sau thời hạn.

## 16. Versioning workflow và migration state

Workflow definition có thể thay đổi trong khi các instance cũ vẫn đang chạy. Đây là vấn đề quan trọng của workflow dài hạn.

### 16.1. Definition version

Mỗi workflow definition nên có ID và version bất biến sau khi phát hành:

~~~text
workflow orderProcess version 3 {
  ...
}
~~~

Instance mới dùng version hiện tại. Instance cũ có thể tiếp tục dùng version đã khởi chạy hoặc được migrate theo chính sách.

### 16.2. Thay đổi state

Các thay đổi có thể gồm:
- Thêm state.
- Bỏ state.
- Đổi tên state.
- Thêm hoặc xóa transition.
- Đổi guard.
- Đổi action.
- Đổi context schema.
- Đổi retry hoặc timeout policy.

Không phải thay đổi nào cũng tương thích với instance đang chạy.

### 16.3. Đổi tên state

Nếu instance đang lưu state PAYMENT_PENDING và definition mới đổi tên thành WAITING_FOR_PAYMENT, runtime cần alias hoặc migration mapping. Nếu không, instance cũ không thể resolve current state.

### 16.4. Thêm state mới

Thêm state có thể tương thích với instance cũ nếu instance cũ không bao giờ ở state đó. Nhưng event mới hoặc transition mới có thể thay đổi cách xử lý instance cũ nếu definition được cập nhật tại chỗ.

### 16.5. Migration function

Có thể định nghĩa migration từ version cũ sang mới:

~~~text
migration orderProcess from 2 to 3 {
  mapState PAYMENT_PENDING -> WAITING_FOR_PAYMENT
  renameContextField paymentRef -> paymentId
}
~~~

Migration cần kiểm tra state và context có thể chuyển đổi, đồng thời giữ lịch sử nguồn để audit.

### 16.6. Pinning và rolling upgrade

Có thể pin instance vào definition version đã tạo ra nó. Cách này giảm rủi ro nhưng cần duy trì runtime tương thích nhiều version. Rolling migration cần quy trình và quan sát rõ.

## 17. Invariant và tính hợp lệ của trạng thái

Invariant là điều kiện phải luôn đúng trong một state hoặc trên toàn bộ machine.

Ví dụ:

~~~text
invariant state == PAID implies paymentId != null
invariant state == FULFILLED implies shipmentId != null
invariant retryCount >= 0
~~~

### 17.1. State invariant

State invariant chỉ cần đúng khi instance ở state tương ứng. Khi transition vào state, runtime hoặc validator kiểm tra điều kiện.

### 17.2. Global invariant

Global invariant đúng trong mọi state:

~~~text
invariant orderId != null
invariant total >= 0
~~~

### 17.3. Transition invariant

Một transition có thể có precondition và postcondition:

~~~text
transition WAITING_FOR_PAYMENT -> PAID
  on payment.accepted
  require event.amount == total
  ensure paymentId == event.paymentId
~~~

Precondition kiểm tra trước biến đổi; postcondition kiểm tra trạng thái sau biến đổi.

### 17.4. Kiểm tra invariant ở đâu?

Invariant có thể được kiểm tra:
- Khi tạo instance.
- Trước transition.
- Sau transition.
- Trước commit.
- Khi khôi phục instance.
- Trong validation hoặc test.

Với dữ liệu quan trọng, kiểm tra ở runtime hoặc persistence boundary giúp bảo vệ khỏi client hoặc worker không tuân thủ.

### 17.5. Invariant và dữ liệu bất đồng bộ

Nếu nhiều task cập nhật context đồng thời, invariant có thể bị vi phạm do race. Cần transaction, locking hoặc command serialization ở cấp instance.

## 18. Statechart và ngữ nghĩa transition phức tạp

State machine đơn giản có thể không đủ cho workflow có nhiều nhánh và trạng thái lồng nhau.

### 18.1. Statechart

Statechart mở rộng state machine bằng:
- Composite state.
- Parallel region.
- History state.
- Entry/exit action.
- Internal transition.
- Event hierarchy.

### 18.2. Transition priority

Nếu nhiều transition cùng khớp, có thể ưu tiên:
1. Transition cụ thể nhất ở state con.
2. Transition ở state cha.
3. Transition có priority cao hơn.
4. Default transition.

Thứ tự này cần được định nghĩa trong DSL, không nên phụ thuộc vào thứ tự duyệt AST.

### 18.3. Event propagation

Event có thể được xử lý ở substate, sau đó bubble lên parent nếu không có handler. Một transition ở parent có thể rời toàn bộ composite state.

### 18.4. Completion transition

Khi tất cả state con đạt final state, composite state có thể phát completion event hoặc tự động chuyển tiếp. Cần xác định completion có chạy entry/exit action hay không.

### 18.5. Internal event queue

Event phát ra trong lúc đang xử lý transition có thể được xếp hàng để xử lý sau commit. Điều này tránh re-entrant transition làm state machine thay đổi giữa lúc action đang chạy.

## 19. Sub-workflow và trạng thái cha-con

Một workflow có thể gọi workflow con để tái sử dụng quy trình.

~~~text
workflow processOrder(order) {
  step payment {
    call workflow collectPayment(order)
  }

  step shipping {
    call workflow arrangeShipping(order)
  }
}
~~~

### 19.1. Parent-child instance

Workflow cha lưu child instance ID và trạng thái của từng workflow con. Parent có thể chờ child hoàn thành, thất bại hoặc bị hủy.

### 19.2. Completion mapping

Kết quả child có thể được ánh xạ thành event của parent:

~~~text
on child.completed -> PAYMENT_COMPLETED
on child.failed -> PAYMENT_FAILED
~~~

### 19.3. Cancellation propagation

Khi parent bị cancel, runtime có thể gửi cancellation đến child. Child cần có chính sách dọn dẹp và compensation riêng.

### 19.4. Failure isolation

Một child thất bại không nhất thiết làm parent thất bại ngay. Parent có thể retry, chạy nhánh thay thế hoặc chuyển sang manual review.

### 19.5. Deadlock và dependency cycle

Workflow lồng nhau có thể tạo vòng chờ. Validator hoặc runtime cần phát hiện dependency cycle hoặc giới hạn độ sâu gọi workflow.

## 20. Bảo mật và quyền chuyển trạng thái

Transition có thể làm thay đổi dữ liệu hoặc kích hoạt hành động quan trọng. Không phải mọi actor đều được phép thực hiện mọi transition.

### 20.1. Actor và role

Có thể mô hình hóa actor:

~~~text
transition SUBMITTED -> APPROVED
  on approve
  when currentActor.hasRole("APPROVER")
~~~

Nhưng danh tính và role cần lấy từ security context đáng tin cậy, không từ payload tùy ý.

### 20.2. Authorization trước transition

Runtime cần xác thực actor và kiểm tra quyền trước khi thực hiện action. Nếu không đủ quyền, transition bị từ chối và có thể ghi audit event.

### 20.3. Separation of duties

Một số quy trình yêu cầu người tạo không được tự phê duyệt. Guard có thể kiểm tra:

~~~text
when currentActor.id != request.createdBy
  and currentActor.hasRole("APPROVER")
~~~

### 20.4. State tampering

Không nên cho client gửi trực tiếp target state để cập nhật database. Client gửi command hoặc event hợp lệ; runtime kiểm tra transition graph rồi mới ghi state.

### 20.5. Audit trail

Các transition nhạy cảm cần ghi:
- Actor.
- Source state.
- Target state.
- Trigger hoặc command.
- Thời điểm.
- Correlation ID.
- Kết quả guard hoặc lý do từ chối.
- Version của workflow definition.

Không ghi secret hoặc toàn bộ payload nhạy cảm nếu không cần.

## 21. Quan sát và vận hành state machine

Một workflow có thể tồn tại lâu và chạy trên nhiều worker. Người vận hành cần biết instance nào đang chờ, đang lỗi hoặc bị kẹt.

### 21.1. State dashboard

Dashboard có thể tổng hợp số instance theo state:

| State | Số instance |
| --- | ---: |
| RUNNING | 120 |
| WAITING_FOR_PAYMENT | 43 |
| RETRY_WAIT | 8 |
| COMPLETED | 980 |
| FAILED | 12 |

Các con số chỉ minh họa. Dashboard cần bộ lọc theo workflow version, tenant, thời gian và loại lỗi.

### 21.2. State duration

Thời gian ở một state giúp phát hiện quy trình bị kẹt. Ví dụ, WAITING_FOR_PAYMENT quá 30 phút có thể cần cảnh báo hoặc timeout.

### 21.3. Transition metrics

Có thể đo:
- Số lần transition.
- Tỷ lệ guard false.
- Transition bị từ chối.
- Retry count.
- Thời gian action.
- Tỷ lệ lỗi.
- Số instance ở trạng thái quá lâu.

### 21.4. Correlation và trace

Mỗi workflow instance nên có correlation ID để liên kết log, trace, event và action. Transition record nên chỉ rõ state trước/sau và event gây ra thay đổi.

### 21.5. Stuck workflow

Một instance có thể bị kẹt do timer mất, event không đến hoặc action đang chạy vô hạn. Công cụ vận hành cần phát hiện:
- Không có heartbeat.
- Timer quá hạn.
- Pending action quá lâu.
- State không có outgoing transition khả thi.
- Event nằm trong dead-letter queue.

### 21.6. Manual repair

Có thể cung cấp thao tác vận hành để retry, resume hoặc đưa instance sang trạng thái xử lý thủ công. Các thao tác này phải có authorization, reason, audit và kiểm tra invariant. Không nên cho phép sửa state tùy ý mà bỏ qua transition contract.

## 22. Kiểm thử trạng thái và chuyển tiếp

State machine có thể được kiểm thử bằng unit test, model-based test, property-based test và integration test.

### 22.1. Transition test

Mỗi transition cần test:
- Đúng source state.
- Đúng trigger.
- Guard true.
- Guard false.
- Target state.
- Action được gọi đúng.
- Context được cập nhật.
- Entry/exit action đúng thứ tự.

### 22.2. Invalid transition test

Kiểm tra event không được phép ở state hiện tại:
- Event không có transition.
- Transition có guard false.
- State đích không tồn tại.
- Actor không có quyền.
- Event thuộc instance khác.

### 22.3. State invariant test

Sau mỗi transition, xác minh global và state invariant. Kiểm tra cả khi action lỗi hoặc transaction rollback.

### 22.4. Path coverage

Có thể kiểm thử các đường đi quan trọng:
- Happy path.
- Rejection path.
- Cancellation path.
- Timeout path.
- Retry path.
- Permanent failure path.
- Compensation path.

Không nhất thiết phải duyệt mọi chuỗi event có thể có, vì số đường đi có thể tăng rất nhanh.

### 22.5. Model-based testing

Tạo model tham chiếu đơn giản rồi sinh chuỗi event. So sánh state machine runtime với model để tìm sai khác.

### 22.6. Property-based testing

Sinh ngẫu nhiên event và context hợp lệ/không hợp lệ, sau đó kiểm tra invariant như:
- Final state không tự quay về state hoạt động.
- Không có transition đến state chưa khai báo.
- Payment không thể được ghi nhận hai lần.
- State PAID luôn có payment reference.
- Instance version tăng đúng sau commit.

### 22.7. Time-based testing

Dùng fake clock để kiểm tra timeout, deadline và retry backoff. Kiểm tra timer cũ không kích hoạt transition sau khi state đã thay đổi.

### 22.8. Concurrency testing

Phát hai event đồng thời cho cùng instance và xác minh chỉ một transition hợp lệ được commit, hoặc cả hai được xử lý theo thứ tự được đặc tả.

### 22.9. Persistence recovery test

Dừng runtime giữa các bước, khởi động lại và xác minh instance tiếp tục đúng state, context, timer và retry metadata.

## 23. Ví dụ DSL hoàn chỉnh: quy trình phê duyệt đơn hàng

Giả sử cần xây dựng quy trình phê duyệt đơn hàng có kiểm tra, phê duyệt, thanh toán và hủy.

~~~text
workflow orderApproval(order: Order) version 1 {
  context {
    reviewerId: UserId?
    paymentId: PaymentId?
    rejectionReason: String?
    retryCount: Integer = 0
  }

  initial state DRAFT

  state SUBMITTED
  state UNDER_REVIEW
  state APPROVED
  state WAITING_FOR_PAYMENT
  state PAID
  state REJECTED
  state CANCELLED
  state PAYMENT_FAILED

  final state PAID
  final state REJECTED
  final state CANCELLED

  invariant order.total >= 0
  invariant state == PAID implies paymentId != null

  transition DRAFT -> SUBMITTED
    on submit
    when order.items.count() > 0
    do recordSubmission(order.id)

  transition SUBMITTED -> UNDER_REVIEW
    on reviewStarted
    when currentActor.hasRole("REVIEWER")
    do assignReviewer(currentActor.id)

  transition UNDER_REVIEW -> APPROVED
    on reviewCompleted
    when event.decision == APPROVE
    do recordReviewer(event.reviewerId)

  transition UNDER_REVIEW -> REJECTED
    on reviewCompleted
    when event.decision == REJECT
    do saveRejectionReason(event.reason)

  transition APPROVED -> WAITING_FOR_PAYMENT
    on paymentRequested
    do createPaymentRequest(order.id, order.total)

  transition WAITING_FOR_PAYMENT -> PAID
    on payment.accepted
    when event.orderId == order.id
      and event.amount == order.total
    do setPaymentId(event.paymentId)

  transition WAITING_FOR_PAYMENT -> PAYMENT_FAILED
    on payment.declined
    do recordPaymentFailure(event.reason)

  transition DRAFT -> CANCELLED
    on cancel

  transition SUBMITTED -> CANCELLED
    on cancel

  transition APPROVED -> CANCELLED
    on cancel
}
~~~

Đây là ví dụ cú pháp minh họa. Một DSL cụ thể có thể yêu cầu khai báo event, context, action và security policy ở các phần riêng.

### 23.1. Luồng thành công

~~~text
DRAFT
  |
  | submit
  v
SUBMITTED
  |
  | reviewStarted
  v
UNDER_REVIEW
  |
  | reviewCompleted(decision = APPROVE)
  v
APPROVED
  |
  | paymentRequested
  v
WAITING_FOR_PAYMENT
  |
  | payment.accepted
  v
PAID
~~~

### 23.2. Luồng từ chối

Nếu reviewer gửi decision REJECT, transition đi từ UNDER_REVIEW sang REJECTED. Workflow ghi reason và kết thúc theo final state.

### 23.3. Luồng thanh toán thất bại

Nếu payment.declined đến, workflow chuyển sang PAYMENT_FAILED. Từ đây có thể bổ sung transition retry hoặc yêu cầu người dùng chọn phương thức khác. Nếu cho phép retry, PAYMENT_FAILED có thể không phải final state.

### 23.4. Kiểm tra guard

Nếu event payment.accepted có orderId khác hoặc amount không bằng order.total, guard false. Runtime cần xác định event bị từ chối, đưa vào unmatched event queue hay ghi nhận security/business diagnostic.

### 23.5. Tính idempotent

Nếu payment.accepted được giao hai lần, lần thứ hai đến khi state đã là PAID. Runtime không nên ghi payment hoặc phát OrderPaid lần nữa. Có thể dùng event ID, payment ID và state guard để deduplicate.

### 23.6. Lịch sử transition

Một execution có thể lưu:

| Sequence | From | Event | To |
| ---: | --- | --- | --- |
| 1 | DRAFT | submit | SUBMITTED |
| 2 | SUBMITTED | reviewStarted | UNDER_REVIEW |
| 3 | UNDER_REVIEW | reviewCompleted | APPROVED |
| 4 | APPROVED | paymentRequested | WAITING_FOR_PAYMENT |
| 5 | WAITING_FOR_PAYMENT | payment.accepted | PAID |

Lịch sử nên kèm timestamp, actor, definition version và correlation ID.

## 24. Thiết kế semantics cho transition trong DSL

Một DSL cần đặc tả chính xác cách runtime xử lý transition để người viết workflow dự đoán được kết quả.

### 24.1. Event dispatch

Quy định event được gửi đến:
- Một instance cụ thể.
- Tất cả instance đang subscribe.
- Một aggregate hoặc business key.
- Một workflow type.

Không nên để event được broadcast tùy tiện nếu payload có thể làm thay đổi nhiều instance.

### 24.2. Candidate selection

Runtime tìm transition có source state và trigger phù hợp. Sau đó đánh giá guard theo context và event payload.

### 24.3. Ambiguity

Nếu nhiều transition cùng hợp lệ, DSL có thể:
- Báo lỗi cấu hình tĩnh nếu có thể phát hiện.
- Dùng priority.
- Cho phép parallel transition.
- Từ chối event tại runtime.

Quy tắc cần ổn định và có diagnostics.

### 24.4. Atomicity

Định nghĩa thời điểm state và context được commit. Nếu action thất bại, runtime rollback, retry hoặc chuyển sang error handling theo policy.

### 24.5. Re-entrant event

Event phát sinh trong transition có được xử lý ngay hay xếp hàng? Xếp hàng thường dễ kiểm soát hơn vì tránh transition lồng nhau làm thay đổi state giữa chừng.

### 24.6. Final state

Quy định final state có nhận event tiếp theo không, có cho phép reopen không và workflow instance được lưu giữ bao lâu.

### 24.7. Undefined behavior

Không nên để trường hợp event không khớp, guard lỗi hoặc action timeout trở thành hành vi ngầm. Mọi trường hợp cần có kết quả, diagnostic và chính sách phục hồi.

## 25. Những lỗi thiết kế thường gặp

**Dùng status field thay cho state machine.** Một chuỗi trạng thái có thể bị cập nhật tùy tiện và tạo chuyển đổi bất hợp lệ. Hãy khai báo transition graph và kiểm tra ở runtime.

**Khai báo state nhưng không có initial state rõ ràng.** Instance có thể bắt đầu ở trạng thái không xác định. Hãy chỉ định initial state hoặc quy tắc khởi tạo duy nhất.

**Không phân biệt final success và final failure.** Báo cáo không thể phân biệt hoàn tất nghiệp vụ với bị từ chối hoặc hủy. Hãy mô hình hóa kết quả cuối theo nhu cầu.

**Guard có side effect.** Guard có thể bị đánh giá nhiều lần và làm thay đổi hệ thống. Hãy giữ guard thuần, chuyển side effect sang action.

**Nhiều transition cùng khớp.** Kết quả phụ thuộc thứ tự triển khai. Hãy bảo đảm guard loại trừ nhau hoặc định nghĩa priority.

**Không xử lý event trùng.** Message redelivery có thể lặp side effect. Hãy dùng idempotency key, event ID và state validation.

**Không kiểm tra event đến sai thứ tự.** Event cũ có thể đưa instance về trạng thái không hợp lệ. Hãy dùng version, sequence hoặc transition guard.

**Action ngoài hệ thống không có timeout.** Workflow có thể ở RUNNING vô hạn. Hãy định nghĩa timeout, retry và reconciliation.

**Nhầm cancellation với compensation.** Dừng workflow không tự hoàn tác side effect đã xảy ra. Hãy mô hình hóa compensation nghiệp vụ.

**Không lưu state bền vững.** Runtime restart có thể làm mất instance hoặc chạy lại action. Hãy lưu checkpoint, context và timer.

**Đổi definition khi instance đang chạy mà không migration.** Instance có thể tham chiếu state hoặc context không còn tồn tại. Hãy version workflow và định nghĩa chính sách migration.

**Cho phép sửa state trực tiếp từ client.** Người dùng có thể bỏ qua transition và invariant. Hãy gửi command/event và để runtime kiểm tra.

**Không kiểm thử concurrency.** Hai event đồng thời có thể cùng vượt qua guard rồi commit xung đột. Hãy dùng versioning hoặc serialization và test race.

## 26. Quy trình xây dựng state và transition cho workflow DSL

Có thể triển khai theo trình tự:

### Bước 1: Mô hình hóa vòng đời nghiệp vụ

Liệt kê các giai đoạn có ý nghĩa, điều kiện bắt đầu, điều kiện hoàn tất và các nhánh từ chối, hủy hoặc lỗi.

### Bước 2: Phân biệt state với data

Chỉ đưa các chế độ ảnh hưởng đến hành vi vào state. Các giá trị như số lần thử, mã thanh toán và lý do lỗi nên nằm trong context.

### Bước 3: Xác định event và command

Đặt tên sự kiện theo điều đã xảy ra, command theo yêu cầu thực hiện. Xác định payload và correlation key.

### Bước 4: Khai báo transition graph

Với mỗi transition, xác định source, trigger, guard, target và action. Xác định rõ final state và internal transition.

### Bước 5: Định nghĩa semantics của guard/action

Guard nên thuần. Action cần có timeout, retry, idempotency và error policy. Định nghĩa entry/exit behavior và thứ tự commit.

### Bước 6: Xác định concurrency

Quy định event ordering, optimistic version, parallel region, join và cancellation propagation.

### Bước 7: Thiết kế persistence và recovery

Lưu instance state, context, timers, definition version và lịch sử transition. Xác định cách resume sau restart.

### Bước 8: Thiết kế versioning và migration

Đặt version cho definition và event schema. Tạo mapping cho state/context nếu cần chuyển instance cũ.

### Bước 9: Thêm security và observability

Kiểm tra actor permission, audit transition, correlation, state duration và cảnh báo instance bị kẹt.

### Bước 10: Kiểm thử model và runtime

Test từng transition, invalid event, invariant, timeout, retry, duplicate, concurrency, recovery và end-to-end workflow.

## 27. Kết luận

Trạng thái mô tả giai đoạn hiện tại của workflow hoặc đối tượng nghiệp vụ; chuyển tiếp quy định cách hệ thống đi từ trạng thái này sang trạng thái khác khi nhận event và thỏa guard. State machine cung cấp mô hình rõ ràng cho initial state, final state, event, guard, action và transition. Workflow DSL có thể mở rộng mô hình đó bằng entry/exit action, state phân cấp, parallel region, timer, retry, compensation và sub-workflow.

Một runtime đáng tin cậy cần xử lý event trùng và sai thứ tự, bảo vệ invariant, commit state và context nhất quán, lưu bền vững instance và khôi phục được sau restart. Definition và event cần version để workflow dài hạn tiếp tục hoạt động khi ngôn ngữ thay đổi. Bảo mật, audit, observability và kiểm thử concurrency cũng là phần thiết yếu của mô hình trạng thái.

Hãy mô hình hóa những giai đoạn thực sự làm thay đổi hành vi thành state, biểu diễn điều kiện bằng guard thuần và đặt side effect vào action có chính sách phục hồi rõ ràng. Khi transition graph và runtime semantics được định nghĩa minh bạch, workflow trở nên dễ dự đoán, kiểm thử, vận hành và mở rộng.


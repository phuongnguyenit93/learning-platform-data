# Điều kiện chuyển trạng thái

## Điều kiện chuyển trạng thái trong DSL quy trình là gì?

Ngôn ngữ chuyên miền dùng để mô tả quy trình (workflow DSL) biểu diễn một công việc gồm các trạng thái, sự kiện, bước xử lý và quan hệ điều khiển. Một quy trình có thể mô tả vòng đời đơn hàng, quy trình phê duyệt, xử lý hồ sơ, cấp quyền, triển khai phần mềm hoặc điều phối nhiều dịch vụ.

Trong một workflow, **trạng thái (state)** cho biết đối tượng hoặc tiến trình đang ở giai đoạn nào. **Chuyển trạng thái (state transition)** là việc chuyển từ trạng thái hiện tại sang trạng thái kế tiếp khi một điều kiện được thỏa mãn. Điều kiện đó thường được gọi là guard, transition condition hoặc predicate.

Ví dụ, đơn hàng có thể đi qua các trạng thái:

~~~text
Draft -> Submitted -> Approved -> Paid -> Fulfilled
                    \
                     -> Rejected
~~~

Không phải đơn hàng nào cũng được chuyển từ Submitted sang Approved. Chỉ khi hồ sơ hợp lệ, người phê duyệt có quyền và giới hạn nghiệp vụ được đáp ứng, transition mới được phép xảy ra.

Một khai báo trong workflow DSL có thể trông như sau:

~~~text
TRANSITION submitOrder
  FROM Draft
  TO Submitted
  ON SubmitRequested
  WHEN order.items.isNotEmpty
   AND customer.isActive
  DO validateOrder()
~~~

Trong ví dụ này:

- FROM xác định trạng thái nguồn.
- TO xác định trạng thái đích.
- ON mô tả sự kiện kích hoạt.
- WHEN mô tả điều kiện cần đúng để transition được phép.
- DO mô tả hành động gắn với transition.

Cú pháp thực tế tùy DSL. Một ngôn ngữ có thể dùng when, guard, if, condition hoặc biểu thức khai báo khác. Điều quan trọng là semantics phải phân biệt rõ sự kiện, điều kiện, trạng thái và hành động.

Điều kiện chuyển trạng thái giúp workflow kiểm soát luồng công việc theo dữ liệu và ngữ cảnh thực tế. Nó ngăn một tiến trình đi vào trạng thái không hợp lệ, hỗ trợ phân nhánh, xử lý ngoại lệ và thể hiện quy tắc nghiệp vụ ngay trong mô hình quy trình.

## Phân biệt state, event, guard, action và invariant

Các thành phần này liên quan chặt chẽ nhưng có vai trò khác nhau.

| Thành phần | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| State | Tiến trình hiện đang ở đâu? | Submitted |
| Event | Điều gì vừa xảy ra hoặc được yêu cầu? | ApprovalReceived |
| Guard / condition | Có được phép chuyển tiếp không? | amount <= approvalLimit |
| Transition | Từ state nào sang state nào? | Submitted -> Approved |
| Action | Cần làm gì khi transition xảy ra? | recordApproval() |
| Invariant | Điều gì phải luôn đúng trong state hoặc process? | Approved order phải có approver |
| Timeout | Khi nào một state hoặc task đã chờ quá lâu? | ApprovalPending quá 2 ngày |
| Compensation | Làm sao bù trừ một tác động đã xảy ra? | releaseReservedInventory() |

### State

State mô tả một trạng thái có ý nghĩa trong vòng đời workflow. Nó có thể là Draft, Submitted, Approved, Rejected, Running, Suspended hoặc Completed.

State nên thể hiện một điều kiện nghiệp vụ ổn định. Ví dụ, PaymentAuthorized có nghĩa thanh toán đã được cấp phép; nó không chỉ có nghĩa một hàm authorizePayment đã được gọi.

### Event

Event là tín hiệu khiến workflow xem xét một hoặc nhiều transition. Event có thể đến từ người dùng, timer, message queue, hệ thống bên ngoài hoặc một bước nội bộ.

Ví dụ:
- SubmitRequested.
- PaymentCaptured.
- DocumentVerified.
- ApprovalDenied.
- TimeoutElapsed.
- ExternalServiceFailed.

Event cho biết một điều đã xảy ra hoặc một yêu cầu đã được phát ra. Guard quyết định event đó có đủ điều kiện để làm thay đổi state hay không.

### Guard

Guard là biểu thức Boolean được đánh giá trong một context xác định. Guard không tự thay đổi state và thông thường không nên có side effect.

Ví dụ:

~~~text
WHEN order.total <= approver.limit
 AND order.riskLevel != "HIGH"
~~~

Nếu guard đúng, transition đủ điều kiện được chọn. Nếu guard sai, workflow vẫn ở state hiện tại hoặc xem xét transition khác.

### Action

Action là công việc được thực hiện khi transition được chọn hoặc khi vào/rời state. Action có thể cập nhật dữ liệu, gửi thông báo, gọi service, tạo task hoặc phát event.

Action cần có quy tắc thực thi và xử lý lỗi rõ ràng. Không nên dùng action để thay thế guard, vì điều đó khiến quyết định chuyển trạng thái chỉ được biết sau khi đã thực hiện side effect.

### Invariant

Invariant là điều kiện phải luôn đúng trong một phạm vi. State invariant phải đúng khi workflow đang ở state đó; process invariant có thể phải đúng trong toàn bộ vòng đời.

Ví dụ:
- Một order ở Paid phải có payment reference.
- Một hồ sơ ở Approved phải có người phê duyệt.
- Một workflow không thể đồng thời ở Completed và Cancelled.
- Số tiền hoàn không vượt số tiền đã thu.

Guard quyết định một transition có được phép xảy ra tại thời điểm cụ thể. Invariant xác định tính hợp lệ của trạng thái hoặc dữ liệu sau các thao tác.

## Cấu trúc của một transition

Một transition thường cần các thành phần sau:

~~~text
Transition
  id
  sourceState
  targetState
  trigger
  guard
  priority
  actions
  retryPolicy
  timeoutPolicy
  metadata
~~~

Không phải DSL nào cũng cần tất cả trường. Một transition đơn giản có thể chỉ có source, target, event và guard. Workflow phức tạp có thể cần priority, retry, timeout, compensation và metadata.

### Source state và target state

Source state xác định transition chỉ được xét khi process đang ở state nào. Target state xác định state mới nếu transition hoàn tất.

Một transition có thể là self-transition, tức source và target cùng một state. Self-transition có thể dùng để xử lý event lặp, cập nhật dữ liệu hoặc khởi động lại một phần hoạt động. Cần quy định nó có chạy exit/entry action hay không.

### Trigger

Trigger xác định thời điểm hoặc sự kiện khiến engine đánh giá transition. Có thể là:
- Event cụ thể.
- Completion của task.
- Timer.
- Message từ hệ thống khác.
- Điều kiện trở nên đúng.
- Lệnh do người dùng hoặc API gửi.

Trigger và guard nên được tách riêng. Event ApprovalReceived có thể đến nhưng guard amount <= limit vẫn sai; workflow không được tự động phê duyệt chỉ vì event đã xuất hiện.

### Guard expression

Guard có thể tham chiếu:
- Dữ liệu process.
- Dữ liệu của entity nghiệp vụ.
- Kết quả task trước.
- Identity và role của actor.
- Thời gian và deadline.
- Context môi trường được phép.
- Kết quả của các bước xác minh.

Ví dụ:

~~~text
WHEN invoice.status == "VALID"
 AND invoice.total > 0
 AND actor.hasRole("FINANCE_APPROVER")
~~~

### Priority và thứ tự lựa chọn

Nếu nhiều transition cùng source state và cùng trigger, có thể có nhiều guard đúng. DSL cần xác định cách lựa chọn:
- Các guard phải loại trừ lẫn nhau.
- Dùng priority rõ ràng.
- Dùng thứ tự khai báo.
- Báo lỗi nếu có nhiều transition cùng hợp lệ.
- Cho phép nondeterministic choice nếu semantics hỗ trợ.

Với workflow nghiệp vụ, lựa chọn mơ hồ thường nên bị phát hiện khi validate model hoặc khi chạy, thay vì âm thầm chọn transition đầu tiên.

### Transition actions

Action có thể chạy trước, trong hoặc sau khi cập nhật state. DSL cần mô tả thứ tự này và quy tắc rollback nếu action thất bại.

Một mô hình có thể phân biệt:
- prepare: kiểm tra hoặc chuẩn bị tài nguyên.
- transition action: thực hiện công việc gắn với quyết định.
- commit: ghi state mới.
- after-commit action: phát notification hoặc công việc bất đồng bộ.

Cách tổ chức phụ thuộc transaction model của engine.

## Guard và trigger: khác nhau ở thời điểm nào?

Trigger và guard thường bị nhập làm một vì cả hai đều có thể xuất hiện trong một câu lệnh when. Tuy nhiên, chúng trả lời hai câu hỏi khác nhau.

- Trigger: điều gì khiến engine xem xét transition?
- Guard: khi được xem xét, transition có đủ điều kiện không?

Ví dụ:

~~~text
TRANSITION approve
  FROM Submitted
  TO Approved
  ON ApprovalRequested
  WHEN document.isComplete
   AND actor.canApprove(document)
~~~

ApprovalRequested là trigger. document.isComplete và actor.canApprove là guard.

### Event-triggered transition

Engine nhận event rồi tìm transition tương ứng. Event có thể được giữ lại nếu process chưa ở state có thể xử lý nó, hoặc bị từ chối theo policy.

Cần quy định:
- Event không phù hợp state hiện tại có bị bỏ qua hay lưu pending?
- Event có được xử lý lại sau khi state thay đổi không?
- Duplicate event có được deduplicate không?
- Event đến sai thứ tự được xử lý ra sao?
- Event hết hạn có bị loại bỏ không?

### Condition-triggered transition

Một số workflow hỗ trợ transition khi một biểu thức trở thành true, không cần event tường minh.

Ví dụ:

~~~text
WHEN inventory.availableQuantity >= order.quantity
  TRANSITION WaitingForStock -> ReadyToFulfill
~~~

Engine phải xác định khi nào đánh giá lại biểu thức: sau mỗi update liên quan, theo polling, theo subscription hoặc tại một checkpoint. Nếu không có cơ chế kích hoạt lại, guard có thể trở thành true nhưng transition không bao giờ được xét.

### Timer-triggered transition

Timer có thể kích hoạt timeout hoặc nhắc việc:

~~~text
TRANSITION escalateApproval
  FROM ApprovalPending
  TO Escalated
  AFTER 2 DAYS
  WHEN approval.status == "PENDING"
~~~

Guard vẫn cần kiểm tra trạng thái hiện tại vì approval có thể đã hoàn tất trước khi timer được xử lý. Timer event đến muộn không được tự động làm workflow chuyển sai.

### Completion-triggered transition

Khi task hoặc subprocess hoàn tất, engine có thể phát event completion. Guard có thể kiểm tra kết quả:

~~~text
ON VerificationCompleted(result)
WHEN result.score >= requiredScore
  TO Verified
~~~

Nếu task thất bại, một transition khác có thể đưa process sang RetryPending hoặc ManualReview.

## Biểu thức điều kiện trong workflow DSL

Guard thường là biểu thức Boolean nhưng có thể dựa trên một type system và context phong phú.

### So sánh

Các toán tử phổ biến:

- == và !=.
- <, <=, >, >=.
- IN và NOT IN.
- MATCHES hoặc pattern matching.
- IS NULL và IS NOT NULL.
- BEFORE và AFTER cho thời gian.
- CONTAINS cho collection hoặc chuỗi.

Ví dụ:

~~~text
WHEN order.total >= 1000000
 AND order.currency == "VND"
 AND order.items.size() > 0
~~~

DSL cần quy định so sánh giữa các kiểu khác nhau, cách xử lý null và phép so sánh chuỗi theo locale/collation.

### Logic Boolean

Guard có thể kết hợp điều kiện bằng AND, OR và NOT:

~~~text
WHEN customer.isActive
 AND (order.total < 5000000 OR actor.hasRole("SENIOR_APPROVER"))
 AND NOT order.isFlagged
~~~

Cần xác định precedence của toán tử và hỗ trợ ngoặc để tránh cách hiểu mơ hồ.

### Collection predicates

Một guard có thể kiểm tra phần tử trong collection:

~~~text
WHEN order.items.any(item => item.quantity > 0)
 AND order.items.all(item => item.isValid)
~~~

Các phép any, all, none, count và contains cần semantics rõ khi collection rỗng hoặc có phần tử null.

Ví dụ, all trên collection rỗng thường có thể trả true theo logic phổ quát, nhưng DSL nên quy định thay vì để người dùng suy đoán.

### Kiểm tra trạng thái và kết quả task

Guard có thể kiểm tra trạng thái của subprocess hoặc task:

~~~text
WHEN tasks["identity-check"].status == "COMPLETED"
 AND tasks["identity-check"].result.verified == true
~~~

Cần phân biệt task chưa được tạo, đang chạy, hoàn tất, thất bại và bị hủy. Truy cập result của task chưa hoàn tất có thể là lỗi hoặc trả về Optional value tùy DSL.

### Điều kiện dựa trên actor

Workflow có thể phụ thuộc vào người thực hiện:

~~~text
WHEN actor.isAuthenticated
 AND actor.hasPermission("invoice.approve")
 AND actor.id != invoice.createdBy
~~~

Quyền phải được xác thực tại thời điểm thực hiện transition. Không nên chỉ tin một giá trị role do client gửi trong payload.

### Điều kiện thời gian

Có thể kiểm tra deadline, thời gian làm việc hoặc khoảng thời gian:

~~~text
WHEN clock.now() < approval.deadline
 AND calendar.isBusinessDay(clock.today())
~~~

Time-dependent guard cần có clock và timezone được xác định rõ để có thể kiểm thử và tái lập. Nếu engine đánh giá lại guard nhiều lần, clock có thể thay đổi giữa các lần đánh giá.

## Ngữ nghĩa Boolean, null và giá trị chưa xác định

Không phải mọi guard đều luôn trả về true hoặc false. Một field có thể chưa được cung cấp, một service chưa trả kết quả hoặc dữ liệu có thể null.

DSL cần chọn một mô hình rõ ràng.

### Boolean hai giá trị

Trong mô hình đơn giản, mỗi guard trả true hoặc false. Giá trị thiếu có thể bị chuyển thành false hoặc gây lỗi evaluation.

Ưu điểm là transition selection dễ hiểu. Tuy nhiên, nếu ép mọi giá trị chưa biết thành false, hệ thống có thể che giấu dữ liệu chưa sẵn sàng.

### Three-valued logic

Một số DSL dùng TRUE, FALSE và UNKNOWN. UNKNOWN có thể xuất hiện khi so sánh với null hoặc dữ liệu chưa có.

Một chính sách an toàn thường là chỉ cho phép transition khi guard trả TRUE. FALSE và UNKNOWN đều không cho phép transition, nhưng diagnostics hoặc logs nên phân biệt hai trường hợp.

### Evaluation error

Lỗi truy cập dữ liệu, chia cho zero hoặc gọi function thất bại có thể được xem là evaluation error. Cần xác định:
- Transition bị coi là không đủ điều kiện?
- Process chuyển sang error state?
- Engine retry evaluation?
- Lỗi được phát ra cho caller?
- Có transition xử lý lỗi riêng không?

Không nên âm thầm biến mọi evaluation error thành false nếu điều đó khiến workflow mắc kẹt mà không có diagnostics.

### Optional và missing values

Có thể dùng phép truy cập an toàn hoặc default:

~~~text
WHEN applicant.address?.country == "VN"
~~~

hoặc:

~~~text
WHEN applicant.riskScore ?? 0 < 30
~~~

Cú pháp minh họa; DSL phải định nghĩa rõ null coalescing và optional navigation. Default trong guard cần được dùng có chủ đích vì nó có thể làm dữ liệu thiếu trở thành một giá trị hợp lệ giả tạo.

## Điều kiện chuyển trạng thái và invariant

Guard kiểm tra một transition cụ thể. Invariant bảo vệ tính hợp lệ của state hoặc toàn bộ process.

Ví dụ workflow thanh toán:

~~~text
STATE Paid {
  INVARIANT payment.reference IS NOT NULL
  INVARIANT payment.amount == order.total
}
~~~

Transition từ Authorized sang Paid có thể có guard:

~~~text
WHEN payment.captureResult == "SUCCESS"
 AND payment.capturedAmount == order.total
~~~

Guard kiểm tra liệu transition có được thực hiện tại thời điểm đó. Invariant kiểm tra trạng thái Paid sau khi transition xảy ra.

### Entry invariant và exit condition

Một state có thể có:
- Entry condition: điều kiện phải đúng khi vào state.
- State invariant: phải luôn đúng khi đang ở state.
- Exit condition: điều kiện cần đúng khi rời state.

Ví dụ ApprovalPending yêu cầu có approver được chỉ định. State invariant có thể yêu cầu deadline chưa bị xóa. Exit condition có thể yêu cầu approval decision đã tồn tại.

### Process invariant

Process invariant áp dụng trên nhiều state:

- Tổng số tiền đã hoàn không vượt số tiền đã thu.
- Không có hai approval cùng cấp cho cùng một hồ sơ.
- Mỗi resource được reserve phải được release hoặc consume.
- Một process chỉ có một kết quả terminal.
- Tenant của event phải trùng tenant của process.

Invariant có thể được kiểm tra khi commit transition hoặc tại các checkpoint. Với invariant quan trọng về bảo mật và tài chính, cần kiểm tra ở server/runtime boundary chứ không chỉ dựa vào editor validation.

### Transition invariant

Một số điều kiện chỉ cần đúng trong lúc chuyển:

- Actor phải có quyền.
- Process version phải khớp.
- Event chưa được xử lý trước đó.
- Tài nguyên cần thiết đã được reserve.
- Không có transition cạnh tranh đã commit.

Các điều kiện này thường được kiểm tra ngay trước commit để tránh race condition.

## Ví dụ workflow phê duyệt đơn hàng

Giả sử một đơn hàng có các state Draft, Submitted, Approved, Rejected, Paid và Fulfilled.

~~~text
WORKFLOW OrderApproval {
  STATE Draft
  STATE Submitted
  STATE Approved
  STATE Rejected
  STATE Paid
  STATE Fulfilled

  TRANSITION submit
    FROM Draft
    TO Submitted
    ON SubmitRequested
    WHEN order.items.size() > 0
     AND customer.isActive
    DO validateOrder()

  TRANSITION approve
    FROM Submitted
    TO Approved
    ON ApprovalGranted
    WHEN actor.hasRole("APPROVER")
     AND actor.id != order.createdBy
     AND order.total <= actor.approvalLimit

  TRANSITION reject
    FROM Submitted
    TO Rejected
    ON ApprovalDenied
    WHEN actor.hasRole("APPROVER")
     AND rejection.reason.isNotEmpty

  TRANSITION pay
    FROM Approved
    TO Paid
    ON PaymentCaptured
    WHEN payment.status == "CAPTURED"
     AND payment.amount == order.total

  TRANSITION fulfill
    FROM Paid
    TO Fulfilled
    ON FulfillmentCompleted
    WHEN shipment.status == "DELIVERED"
}
~~~

Các điều kiện phản ánh nhiều loại quy tắc:
- submit kiểm tra dữ liệu và trạng thái khách hàng.
- approve kiểm tra role, separation of duties và hạn mức.
- reject yêu cầu lý do từ chối.
- pay kiểm tra trạng thái và số tiền thanh toán.
- fulfill kiểm tra kết quả giao hàng.

Một quy trình thực tế còn cần kiểm tra actor identity từ context đáng tin cậy, idempotency của event thanh toán, timeout và xử lý lỗi bên ngoài.

### Bảng transition

| State nguồn | Event | Guard chính | State đích |
|---|---|---|---|
| Draft | SubmitRequested | Có item, khách hàng active | Submitted |
| Submitted | ApprovalGranted | Có quyền, trong hạn mức | Approved |
| Submitted | ApprovalDenied | Có quyền, có lý do | Rejected |
| Approved | PaymentCaptured | Thanh toán thành công, đúng số tiền | Paid |
| Paid | FulfillmentCompleted | Giao hàng thành công | Fulfilled |

Bảng này có thể dùng làm tài liệu cho người thiết kế, nhưng engine cần một biểu diễn thực thi có type và source mapping.

## Nhiều transition cùng đủ điều kiện

Một state có thể có nhiều transition cùng chờ một event hoặc cùng được đánh giá khi điều kiện thay đổi.

Ví dụ:

~~~text
STATE Submitted {
  ON ReviewCompleted:
    WHEN riskScore >= 80 -> ManualReview
    WHEN riskScore < 80 AND amount <= autoLimit -> Approved
    WHEN riskScore < 80 AND amount > autoLimit -> SeniorApproval
}
~~~

Nếu các guard loại trừ nhau, chỉ một transition có thể được chọn. Nếu chúng có thể cùng đúng, cần semantics rõ.

### Guard disjointness

Hai guard là disjoint nếu không thể cùng đúng trong cùng context. Ví dụ amount < 100 và amount >= 100.

Một static analyzer có thể chứng minh một số điều kiện đơn giản loại trừ nhau. Với biểu thức phức tạp hoặc function tùy ý, không phải lúc nào cũng chứng minh được.

### Priority

Có thể đặt priority:

~~~text
TRANSITION emergencyReview
  FROM Submitted
  TO ManualReview
  ON ReviewCompleted
  PRIORITY 100
  WHEN riskScore >= 80

TRANSITION autoApprove
  FROM Submitted
  TO Approved
  ON ReviewCompleted
  PRIORITY 10
  WHEN riskScore < 80
~~~

Engine xét transition có priority cao trước. Cần quy định priority bằng nhau, guard evaluation error và việc guard thấp hơn có được đánh giá nếu guard cao hơn UNKNOWN hay không.

### First-match semantics

Một DSL có thể chọn transition đầu tiên có guard đúng theo thứ tự khai báo. Cách này đơn giản nhưng thứ tự file trở thành một phần semantics. Refactor hoặc sắp xếp lại khai báo có thể làm thay đổi hành vi.

Nếu dùng first-match, thứ tự cần được thể hiện trong tài liệu và tooling phải giúp người dùng thấy transition nào thắng.

### Ambiguous transition

Nếu nhiều transition cùng hợp lệ và không có priority hoặc ordering rule, engine có thể báo ambiguous transition. Đây thường là hành vi an toàn hơn việc chọn ngẫu nhiên.

Diagnostic nên liệt kê các transition cạnh tranh và guard đã đánh giá true, kèm source location.

## Transition theo điều kiện và decision node

Một số workflow có decision node tách việc đánh giá điều kiện khỏi transition.

~~~text
Submitted
    |
    v
Decision: riskScore?
    |
    +-- < 30 ------> AutoApprove
    |
    +-- 30..79 ----> ManagerReview
    |
    +-- >= 80 -----> ManualInvestigation
~~~

Decision node có thể có:
- Một tập branch với guard.
- Default branch.
- Priority hoặc ordering.
- Quy tắc xử lý UNKNOWN.
- Diagnostic khi không có branch nào phù hợp.

### Exclusive gateway

Exclusive gateway chọn đúng một nhánh. Các guard nên loại trừ nhau hoặc có priority rõ. Nếu không có nhánh phù hợp, workflow có thể đi vào default path hoặc error handling.

### Inclusive gateway

Inclusive gateway có thể chọn nhiều nhánh nếu nhiều guard đúng. Các nhánh được kích hoạt đồng thời hoặc theo một semantics cụ thể. Cần xác định cách đồng bộ khi các nhánh hoàn tất.

### Parallel gateway

Parallel gateway kích hoạt tất cả nhánh độc lập. Nó không phải là phép lựa chọn theo guard, dù mỗi nhánh sau đó có thể có transition riêng.

### Default branch

Default branch được dùng khi không guard nào đúng. Nó có thể đưa process đến ManualReview, WaitingForInput hoặc Rejected. Default branch không nên che giấu lỗi dữ liệu hoặc evaluation error trừ khi DSL quy định rõ.

## Thứ tự đánh giá guard và tính thuần (purity)

Guard thường được đánh giá nhiều lần, có thể sau mỗi event hoặc khi process được phục hồi. Vì vậy, guard nên là biểu thức thuần (pure expression): cùng input và cùng context thì cho cùng kết quả, không tạo side effect.

Ví dụ guard phù hợp:

~~~text
WHEN order.total > approvalLimit
 AND customer.status == "ACTIVE"
~~~

Guard không nên thực hiện:
- Gửi email.
- Ghi database.
- Trừ inventory.
- Gọi API tạo payment.
- Tăng counter nghiệp vụ.
- Thay đổi process data.

Những việc đó thuộc action.

### Vì sao guard cần pure?

Nếu guard gửi request đến service ngoài rồi engine đánh giá lại do retry, side effect có thể xảy ra nhiều lần. Nếu guard phụ thuộc random hoặc thời gian không được kiểm soát, cùng một process snapshot có thể chọn transition khác nhau.

Pure guard giúp:
- Dễ kiểm thử.
- Dễ cache evaluation nếu context không đổi.
- Dễ khôi phục process.
- Dễ giải thích vì sao transition được chọn.
- Tránh side effect khi có nhiều candidate transition.

### Function metadata

Nếu DSL cho phép gọi function trong guard, function registry có thể khai báo metadata:

~~~text
FUNCTION isEligible(customer)
  PURE
  DETERMINISTIC
  RETURNS Boolean
~~~

Function gọi dữ liệu bên ngoài có thể được mô hình hóa như task hoặc service activity trước đó, sau đó guard kiểm tra kết quả đã được lưu vào process context.

### Time và nondeterminism

Nếu cần kiểm tra deadline, nên dùng một timestamp đã được ghi nhận hoặc clock được inject vào evaluation context. Tránh gọi system clock tùy tiện ở nhiều lần đánh giá khiến kết quả thay đổi không kiểm soát.

## Transition actions và thứ tự commit

Guard xác định transition có hợp lệ hay không; action thực hiện công việc gắn với transition. Thứ tự giữa action và state update ảnh hưởng tính nhất quán.

Một mô hình đơn giản:

~~~text
1. Receive event
2. Load process snapshot
3. Find candidate transitions
4. Evaluate guards
5. Select one transition
6. Execute transition actions
7. Validate target state invariants
8. Commit state and data
9. Publish outgoing events
~~~

Tuy nhiên, nếu action có side effect bên ngoài, transaction database không thể tự rollback toàn bộ. Cần xác định execution model phù hợp.

### Prepare trước commit

Một số action có thể chạy trước commit để kiểm tra hoặc chuẩn bị:
- Validate external reference.
- Reserve resource.
- Calculate quote.
- Verify signature.

Nếu prepare thất bại, transition không commit. Nếu prepare tạo reservation, cần compensation khi commit thất bại.

### Commit state

State, process data và event record thường cần được ghi nhất quán. Có thể dùng transaction hoặc optimistic concurrency control. Không nên cập nhật state trước rồi mới ghi dữ liệu bắt buộc nếu điều đó tạo state không hợp lệ.

### After-commit action

Notification, webhook hoặc task không ảnh hưởng tính hợp lệ cốt lõi có thể chạy sau commit. Transactional outbox giúp ghi event cùng transaction với state rồi publish bất đồng bộ.

### Action failure

Cần quy định khi action thất bại:
- Giữ state cũ.
- Retry action.
- Chuyển sang error state.
- Thực hiện compensation.
- Đánh dấu transition pending.
- Yêu cầu can thiệp thủ công.

Không nên để workflow báo đã chuyển state nếu action bắt buộc chưa hoàn tất mà semantics yêu cầu action đó phải thành công trước commit.

## Tính nguyên tử và race condition

Hai event có thể đến gần như đồng thời và cùng cố chuyển một process khỏi state hiện tại. Ví dụ, PaymentCaptured và CancelRequested cùng được xử lý trong lúc order đang Approved.

Nếu cả hai worker cùng đọc state Approved, cả hai có thể đánh giá guard true và cố commit state khác nhau.

### Optimistic concurrency

Process có version tăng sau mỗi commit:

~~~text
ProcessSnapshot
  id
  state
  version
  data
~~~

Transition commit chỉ thành công nếu version hiện tại vẫn bằng version đã đọc. Nếu version thay đổi, worker phải reload và đánh giá lại event theo state mới.

### Serialization per process

Một cách khác là xử lý event tuần tự theo process ID. Điều này đơn giản hóa state transition nhưng có thể giới hạn throughput nếu một process nhận nhiều event.

### Idempotency

Event có thể được gửi lặp do retry mạng hoặc message broker. Mỗi event nên có ID ổn định; engine ghi nhận event đã xử lý để không commit cùng transition nhiều lần.

Action bên ngoài cũng cần idempotency key nếu có thể được retry.

### Exactly-once và at-least-once

Trong hệ thống phân tán, bảo đảm exactly-once end-to-end thường khó. Workflow engine thường dùng at-least-once delivery kết hợp idempotent processing, deduplication và transactional state update.

Không nên dựa vào việc event chỉ đến một lần. Transition condition và action phải an toàn trước duplicate theo contract.

## Timeout và deadline là điều kiện chuyển trạng thái

Workflow thường phải phản ứng khi một state hoặc task chờ quá lâu.

Ví dụ:

~~~text
STATE ApprovalPending {
  TIMEOUT 48 HOURS
  ON TIMEOUT
    WHEN approval.status == "PENDING"
    -> Escalated
}
~~~

Timeout có thể:
- Chuyển sang state Escalated.
- Tạo reminder.
- Hủy task.
- Gửi process đến ManualReview.
- Đánh dấu SLA breach.
- Kích hoạt compensation.

### Timeout không phải guard duy nhất

Timer event chỉ cho biết thời gian chờ đã hết. Guard cần kiểm tra process vẫn ở state liên quan và điều kiện chưa được giải quyết.

Ví dụ, timer cho approval có thể đến sau khi approval đã hoàn tất. Nếu engine không kiểm tra current state và version, timer cũ có thể chuyển một process đã Approved sang Escalated.

### Deadline tuyệt đối và duration

Cần phân biệt:
- Duration: chờ 48 giờ từ lúc vào state.
- Absolute deadline: phải hoàn tất trước một timestamp.
- Business duration: 2 ngày làm việc, không tính ngày nghỉ.
- Calendar event: đến một thời điểm theo timezone.

Business calendar và timezone cần được xác định để tránh kết quả khác nhau giữa môi trường.

### Timer persistence

Timer cần được lưu bền vững để process vẫn được đánh thức sau restart. Timer event nên gắn với process ID, state instance hoặc token ID để engine nhận diện timer nào còn hiệu lực.

Nếu process rời state trước hạn, timer cần bị hủy hoặc khi đến hạn phải tự xác minh rằng nó vẫn áp dụng.

## Retry, error transition và compensation

Một transition có thể thất bại vì service tạm thời không khả dụng, dữ liệu không hợp lệ hoặc điều kiện nghiệp vụ không còn đúng.

### Retry policy

Retry policy có thể quy định:

~~~text
RETRY
  MAX_ATTEMPTS 5
  INITIAL_DELAY 2 SECONDS
  BACKOFF EXPONENTIAL
  MAX_DELAY 1 MINUTE
  JITTER true
~~~

Retry phù hợp với lỗi tạm thời như timeout hoặc throttling. Không nên retry lỗi vĩnh viễn như invalid input hoặc permission denied.

### Error state

Workflow có thể có state riêng:
- Failed.
- RetryPending.
- ManualIntervention.
- CompensationPending.
- Compensated.

Một transition lỗi có thể được mô tả:

~~~text
ON PaymentFailed(error)
  WHEN error.isRetryable -> RetryPending
  WHEN error.isPermanent -> PaymentRejected
~~~

Cần xác định error taxonomy và mapping từ lỗi connector sang domain error.

### Compensation

Trong workflow dài, các bước trước đó có thể đã commit side effect. Nếu bước sau thất bại, transaction rollback không thể hoàn tác mọi hệ thống bên ngoài.

Compensation là hành động nghiệp vụ bù trừ:
- Release inventory reservation.
- Cancel shipment request.
- Refund payment.
- Revoke temporary access.

Compensation không nhất thiết khôi phục đúng trạng thái vật lý ban đầu. Ví dụ refund tạo một giao dịch mới thay vì xóa payment đã capture.

### Saga

Một saga gồm các bước có hành động bù trừ tương ứng:

~~~text
ReserveInventory
      |
      v
CapturePayment
      |
      v
CreateShipment
      |
      v
CompleteOrder
~~~

Nếu CreateShipment thất bại, workflow có thể refund payment rồi release inventory. Guard quyết định compensation nào phù hợp với trạng thái và kết quả từng bước.

### Compensation condition

Không phải mọi lỗi đều cần compensation. Có thể chỉ bù trừ khi side effect đã hoàn tất:

~~~text
WHEN payment.captureStatus == "CAPTURED"
 AND shipment.status == "FAILED"
 -> RefundPayment
~~~

Cần ghi nhận trạng thái compensation để tránh chạy lặp hoặc bỏ sót.

## State hierarchy và điều kiện chuyển trạng thái lồng nhau

Workflow lớn có thể có state lồng nhau để tái sử dụng quy tắc chung.

Ví dụ:

~~~text
STATE OrderProcessing {
  STATE Payment {
    STATE Pending
    STATE Authorized
    STATE Captured
  }

  STATE Fulfillment {
    STATE Waiting
    STATE Picking
    STATE Shipped
  }
}
~~~

Một transition ở cấp cha có thể áp dụng cho nhiều state con, ví dụ CancelRequested. Cần quy định:
- Transition ở cấp con hay cấp cha được ưu tiên.
- Guard của state cha có được đánh giá trước không.
- Entry/exit action của ancestor chạy thế nào.
- History state có được khôi phục không.
- Transition từ state con sang ngoài hierarchy có exit action nào.

### Internal và external transition

External transition rời state rồi vào state đích, có thể chạy exit/entry action. Internal transition xử lý event bên trong state mà không rời state cha.

Cùng source và target có thể tạo semantics khác nhau nếu state hierarchy tồn tại. DSL cần biểu diễn rõ loại transition hoặc định nghĩa một quy tắc mặc định.

### History state

History state cho phép quay lại state con trước đó khi một composite state được mở lại. Guard có thể quyết định có khôi phục history hay bắt đầu lại từ initial child.

History cần được lưu bền vững nếu workflow phải phục hồi sau restart.

## Parallel state và điều kiện đồng bộ

Một workflow có thể chạy nhiều nhánh đồng thời, ví dụ xác minh danh tính, kiểm tra tín dụng và kiểm tra tồn kho.

~~~text
STATE Review {
  PARALLEL {
    identityCheck
    creditCheck
    inventoryCheck
  }

  WHEN allCompleted -> Ready
  WHEN anyRejected -> Rejected
}
~~~

Điều kiện chuyển tiếp có thể phụ thuộc:
- Tất cả nhánh hoàn tất.
- Một nhánh thất bại.
- Một tập con hoàn tất.
- Timeout.
- Kết quả tổng hợp.

### Join condition

Join condition xác định khi nào các nhánh song song được coi là đủ để tiếp tục. Ví dụ all-of, any-of hoặc quorum.

Nếu dùng any-of, cần xử lý các nhánh còn lại: hủy, tiếp tục nền hay bù trừ. Nếu dùng quorum, cần xác định kết quả khi không đủ nhánh trước deadline.

### Race giữa nhánh

Hai nhánh có thể hoàn tất gần như đồng thời và cùng kích hoạt transition. Engine cần đồng bộ việc join và bảo đảm transition chỉ commit một lần.

### Partial failure

Một nhánh thất bại không nhất thiết làm toàn workflow thất bại. DSL có thể cho phép fallback hoặc manual review. Guard cần xem trạng thái từng nhánh và policy tổng hợp.

## Điều kiện chuyển trạng thái dựa trên dữ liệu bên ngoài

Workflow có thể cần thông tin từ API, message broker hoặc hệ thống khác. Guard nên đọc dữ liệu đã được đưa vào process context qua một activity có kiểm soát.

Ví dụ:

~~~text
TASK verifyCredit
  CALL creditService.check(applicant.id)
  STORE result AS creditResult

TRANSITION accept
  FROM CreditReview
  TO Accepted
  ON CreditCheckCompleted
  WHEN creditResult.score >= 700
~~~

Cách này giúp tách side effect và network I/O khỏi guard.

### Snapshot của dữ liệu

Nếu guard đọc dữ liệu bên ngoài trực tiếp mỗi lần đánh giá, cùng event có thể cho kết quả khác nhau khi service thay đổi. Nên lưu kết quả hoặc version của dữ liệu đã dùng để quyết định.

### Staleness

Dữ liệu có thể hết hạn. Guard có thể yêu cầu:
- Result có timestamp trong giới hạn.
- Source version khớp.
- Verification chưa bị revoke.
- External status vẫn valid.

Nếu cần refresh, workflow nên chạy activity mới rồi đánh giá guard trên kết quả mới.

### Timeout và service failure

Không nên coi timeout của external service là kết quả nghiệp vụ false. Đó là lỗi kỹ thuật hoặc trạng thái chưa biết. Workflow có thể chuyển sang RetryPending hoặc WaitingForExternalService.

### Event correlation

Event từ hệ thống ngoài cần được correlate với process ID hoặc business key đã xác thực. Không được để event của một order cập nhật process của order khác chỉ vì payload chứa một ID không được kiểm chứng.

## Authorization trong điều kiện chuyển trạng thái

Một số transition chỉ được thực hiện bởi actor có quyền.

Ví dụ:

~~~text
TRANSITION approveInvoice
  FROM Submitted
  TO Approved
  ON ApproveRequested
  WHEN actor.authenticated
   AND actor.hasPermission("invoice.approve")
   AND actor.id != invoice.createdBy
~~~

Authorization guard có thể kiểm tra:
- Identity đã xác thực.
- Role hoặc permission.
- Scope của resource.
- Separation of duties.
- Tenant membership.
- Giới hạn theo số tiền hoặc loại nghiệp vụ.
- Trạng thái delegation hoặc approval chain.

### Kiểm tra quyền tại thời điểm commit

Quyền có thể bị thu hồi giữa lúc guard được đánh giá và transition được commit. Với thao tác nhạy cảm, cần kiểm tra quyền gần thời điểm commit hoặc dùng một authorization decision có version/expiry rõ.

### Không tin context do client tự khai

Actor identity, tenant và permission phải đến từ context đáng tin cậy của runtime hoặc authorization service. Client có thể gửi yêu cầu và metadata, nhưng không được tự xác định mình có role nào.

### Audit decision

Đối với transition quan trọng, audit có thể ghi:
- Actor.
- Transition ID.
- Process ID.
- Decision outcome.
- Policy version.
- Thời điểm.
- Correlation ID.

Không nhất thiết ghi toàn bộ dữ liệu nhạy cảm được dùng trong guard.

## Lựa chọn transition trong engine

Một engine cần một thuật toán xác định để xử lý event và các candidate transition.

Một pipeline khái quát:

~~~text
Receive event
    |
    v
Load current process snapshot
    |
    v
Find transitions for current state and event
    |
    v
Check transition eligibility
    |
    v
Evaluate guards
    |
    v
Resolve priority / ambiguity
    |
    v
Validate authorization and invariants
    |
    v
Execute prepare actions
    |
    v
Commit state transition
    |
    v
Run after-commit actions
    |
    v
Persist outcome and emit events
~~~

### Candidate selection

Engine trước tiên lọc transition theo source state và trigger. Không cần đánh giá mọi guard của mọi transition trong toàn workflow.

### Guard evaluation context

Một context có thể gồm:

~~~text
TransitionContext
  processSnapshot
  currentState
  incomingEvent
  actor
  clock
  serviceResults
  tenantContext
  schemaVersion
~~~

Context cần bất biến trong một lần evaluation để các guard được so sánh trên cùng dữ liệu. Nếu dữ liệu thay đổi, engine cần tạo snapshot mới và đánh giá lại.

### No matching transition

Nếu không transition nào phù hợp, engine có thể:
- Bỏ qua event theo policy.
- Lưu event pending.
- Báo invalid transition.
- Chuyển sang error handler.
- Đánh dấu event không liên quan.
- Đợi một điều kiện hoặc event khác.

Không nên mặc định mọi event không khớp đều là lỗi fatal. Một số event có thể hợp lệ nhưng đến trước thời điểm workflow sẵn sàng.

### Guard evaluation error

Cần phân biệt:
- Không có candidate.
- Candidate có guard false.
- Guard unknown.
- Guard ném lỗi.
- Nhiều guard cùng true.
- Transition bị từ chối bởi authorization.
- Commit thất bại do concurrency.

Diagnostics và logs cần giữ các loại outcome này riêng.

## DSL syntax và mô hình dữ liệu cho guard

Một DSL có thể dùng cú pháp khai báo:

~~~text
TRANSITION release
  FROM QualityCheck
  TO Released
  ON InspectionCompleted
  WHEN inspection.result == "PASS"
   AND inspection.defectCount == 0
  PRIORITY 20
  DO publishArtifact()
~~~

Parser có thể tạo model:

~~~text
TransitionDeclaration
  id: Identifier
  source: StateReference
  target: StateReference
  trigger: TriggerExpression
  guard: Optional<BooleanExpression>
  priority: Optional<Integer>
  actions: List<ActionDeclaration>
  sourceSpan: SourceSpan
~~~

Guard expression nên dùng AST riêng với các node có kiểu:

~~~text
BooleanExpression
  Comparison
  LogicalAnd
  LogicalOr
  LogicalNot
  FunctionCall
  PropertyAccess
  Literal
  CollectionPredicate
  OptionalAccess
~~~

### Static type checking

Compiler cần xác nhận guard có kiểu Boolean hoặc kiểu condition được DSL hỗ trợ. Biểu thức số hoặc string đơn lẻ không nên tự động được coi là truthy nếu ngôn ngữ không định nghĩa coercion.

Ví dụ sai:

~~~text
WHEN order.total
~~~

Nếu total là Decimal, guard phải so sánh với một giá trị hoặc dùng predicate rõ:

~~~text
WHEN order.total > 0
~~~

### Name resolution

Property access cần resolve theo schema của process context. Nếu order.approvalLimt bị typo, language server có thể báo unknown property trước khi workflow chạy.

### Source mapping

Mỗi guard node nên giữ source span để runtime error hoặc explain decision có thể chỉ về biểu thức gốc. Điều này giúp người vận hành biết điều kiện nào đã chặn transition.

### Function allowlist

Nếu guard được lưu hoặc gửi từ nguồn không tin cậy, function call phải được resolve qua registry được phép. Không nên cho expression gọi method tùy ý trên object runtime.

## Tích hợp với state machine và workflow patterns

Điều kiện chuyển trạng thái là nền tảng của state machine. Workflow DSL có thể hỗ trợ các pattern như sequence, choice, parallel split, synchronization, event wait, retry và compensation.

### Sequence

Các bước chạy lần lượt. Guard có thể quyết định có tiếp tục bước kế tiếp hay chuyển sang nhánh khác.

### Choice

Một decision node chọn nhánh dựa trên các guard. Cần xử lý nhiều guard cùng đúng và default branch.

### Parallel split và join

Nhiều nhánh được kích hoạt đồng thời. Join condition quyết định khi nào tiến trình có thể tiếp tục.

### Event wait

Process chờ event bên ngoài. Trigger và correlation policy quyết định event nào được nhận.

### Retry loop

Một task có thể quay lại trạng thái retry khi lỗi tạm thời và số lần thử chưa vượt giới hạn. Guard kiểm tra retry count, error class và deadline.

### Compensation

Khi một bước sau thất bại, workflow có thể chạy các action bù trừ dựa trên những bước đã commit.

### Human task

Transition có thể phụ thuộc vào quyết định của người dùng, deadline, quyền và separation of duties. Event từ giao diện cần được xác thực và idempotent.

## Persistence và phục hồi workflow

Workflow dài có thể tồn tại qua nhiều giờ, ngày hoặc tháng. State, process data, timer và event cần được lưu bền vững.

### Lưu state và version

Một process record có thể chứa:
- Process ID.
- Current state hoặc active tokens.
- Process data.
- Version.
- Last processed event ID.
- Pending timers.
- Active task IDs.
- Correlation metadata.

### Event history

Event history giúp tái dựng vì sao workflow đến state hiện tại. Có thể lưu:
- Event received.
- Candidate transitions.
- Guard outcomes theo policy.
- Transition selected.
- State committed.
- Action outcomes.
- Retry hoặc compensation.

Không nhất thiết lưu mọi giá trị guard nếu chúng nhạy cảm. Có thể lưu decision code, policy version và reference đến dữ liệu audit được bảo vệ.

### Recovery

Sau restart, engine tải process snapshot, khôi phục timer và task, rồi tiếp tục xử lý event. Guard cần được đánh giá trên context đã được persist hoặc dữ liệu được version hóa để không thay đổi kết quả ngoài dự kiến.

### Replay

Replay event có thể hữu ích cho debug và migration. Nhưng replay side effect thực tế là nguy hiểm. Cần chế độ simulation hoặc dry-run, và action bên ngoài phải bị chặn hoặc thay bằng mock.

### Durable timer

Timer phải được lưu cùng state/version hoặc có token riêng. Khi process chuyển state, timer cũ phải bị hủy hoặc trở thành stale. Khi timer event được xử lý, engine xác minh lại state trước khi commit.

## Versioning và thay đổi workflow definition

Workflow definition có thể thay đổi trong khi nhiều process đang chạy. Một process được tạo theo version cũ có thể cần tiếp tục theo semantics cũ.

Cần xác định:
- Process instance có pin definition version không?
- Có tự động migrate sang version mới không?
- State cũ bị xóa hoặc đổi tên thì xử lý thế nào?
- Guard expression thay đổi có ảnh hưởng process đang chờ không?
- Timer và task đang chạy được ánh xạ ra sao?
- Event schema có tương thích không?

### Definition version pinning

Một cách an toàn là gắn mỗi process instance với workflow definition version tại thời điểm khởi tạo. Process tiếp tục theo version đó cho đến khi hoàn tất hoặc được migrate có chủ đích.

### Migration

Migration có thể đổi state mapping, process data hoặc pending activity. Nó cần kiểm tra invariant của workflow đích và lưu audit. Không nên chỉ đổi tên state trong database mà không xử lý timer, task và event đang chờ.

### Guard semantics version

Nếu function, type system hoặc null semantics thay đổi, cùng guard expression có thể trả kết quả khác. Workflow version cần bao gồm semantics hoặc dependency version có ảnh hưởng đến decision.

## Diagnostics và giải thích quyết định chuyển trạng thái

Khi transition không xảy ra, người vận hành cần biết nguyên nhân.

Một decision record có thể gồm:

~~~text
TransitionDecision
  processId
  eventId
  currentState
  candidateTransitions[]
  guardResults[]
  selectedTransition
  outcome
  reasonCode
  definitionVersion
  processVersion
  timestamp
~~~

Ví dụ explain output:

~~~text
Event: ApprovalGranted
Current state: Submitted

Candidate: approveStandard
  Guard: order.total <= actor.approvalLimit
  Result: false

Candidate: approveSenior
  Guard: actor.hasRole("SENIOR_APPROVER")
  Result: true

Selected: approveSenior
Target state: Approved
~~~

### Diagnostic khi guard false

Guard false không nhất thiết là lỗi. Tuy nhiên, nếu event không thể được xử lý vì một điều kiện thiếu, engine có thể cung cấp reason code như:
- MISSING_REQUIRED_DATA.
- ACTOR_NOT_AUTHORIZED.
- LIMIT_EXCEEDED.
- DEADLINE_EXPIRED.
- EXTERNAL_RESULT_PENDING.

Không nên luôn trả toàn bộ dữ liệu nội bộ ra client. Explain cần tôn trọng quyền truy cập và masking.

### Guard trace

Với workflow phức tạp, có thể ghi cây evaluation:

~~~text
AND
  customer.isActive = true
  OR
    order.total < 1000 = false
    actor.isSupervisor = true
  RESULT = true
~~~

Guard trace hữu ích khi debug, nhưng có thể chứa dữ liệu nhạy cảm. Cần policy lưu giữ, redaction và quyền xem.

### Observability

Metrics có thể theo dõi:
- Số transition được xét.
- Số transition thành công.
- Guard false/unknown/error count.
- Ambiguous decision count.
- Event không khớp state.
- Timeout và retry count.
- Transition latency.
- Compensation failure.
- Process stuck duration.

Metric labels nên là transition category hoặc workflow version đã kiểm soát, không phải process ID hay raw business key.

## Tích hợp với IDE và Language Server

Một workflow DSL có thể cung cấp hỗ trợ tĩnh để người thiết kế phát hiện lỗi trước khi chạy.

Các tính năng hữu ích:
- Completion cho state name, event và process property.
- Hover giải thích kiểu và semantics của guard.
- Diagnostics cho target state không tồn tại.
- Kiểm tra guard không trả Boolean.
- Cảnh báo transition không thể đạt tới.
- Phát hiện state không có đường thoát.
- Phát hiện guard luôn false hoặc transition bị che bởi priority cao hơn.
- Kiểm tra nhiều transition có thể cùng đúng.
- Go to definition từ state reference.
- Find references cho event và state.
- Preview state graph và decision branches.

### Static reachability

Compiler có thể xây graph từ state và transition để phát hiện state không thể đạt tới từ initial state. Tuy nhiên, graph reachability không chứng minh guard có thể đúng. Một edge có thể tồn tại nhưng guard luôn false.

### Guard satisfiability

Với biểu thức đơn giản, analyzer có thể phát hiện mâu thuẫn như amount > 100 AND amount < 50. Với function tùy ý hoặc dữ liệu ngoài, không thể luôn chứng minh.

Diagnostics nên phân biệt:
- Definitely unreachable.
- Possibly unreachable.
- Unknown because of dynamic data.
- Guard may overlap with another transition.

### Visual state graph

Editor có thể hiển thị state graph với:
- State nodes.
- Transition edges.
- Guard labels.
- Event triggers.
- Priority.
- Terminal states.
- Timeout and error paths.

Chọn một edge có thể mở guard expression trong source. Chọn state có thể hiển thị entry/exit action và invariant.

## Kiểm thử điều kiện chuyển trạng thái

Guard và transition cần được kiểm thử độc lập, tích hợp và theo các tình huống cạnh tranh.

### Unit test cho guard

Mỗi guard nên có các trường hợp:
- Điều kiện đúng.
- Điều kiện sai.
- Null hoặc missing data.
- Boundary value.
- Kiểu dữ liệu không hợp lệ.
- Evaluation error.
- Timezone và deadline boundary.
- Actor có và không có permission.

Ví dụ với limit:

~~~text
WHEN order.total <= approvalLimit
~~~

Cần test total nhỏ hơn, bằng và lớn hơn limit, cùng trường hợp một trong hai giá trị bị thiếu.

### Transition test

Kiểm tra:
- State nguồn đúng thì transition được xét.
- State nguồn sai thì transition không chạy.
- Event đúng trigger.
- Guard false giữ nguyên state.
- Guard true chuyển đúng target.
- Action chạy đúng thứ tự.
- Invariant target được kiểm tra.
- Event duplicate không tạo side effect lặp.
- No-match xử lý theo policy.

### Decision table testing

Với nhiều điều kiện, decision table giúp bao phủ tổ hợp quan trọng:

| Customer active | Amount within limit | Approver role | Kết quả |
|---|---|---|---|
| Yes | Yes | Yes | Approve |
| Yes | No | Yes | Senior review |
| Yes | Yes | No | Reject or wait |
| No | Any | Any | Block submission |

Không cần kiểm thử mọi tổ hợp nếu số điều kiện rất lớn, nhưng cần bao phủ các nhánh và boundary có ý nghĩa.

### Property-based testing

Có thể sinh process data và event ngẫu nhiên để kiểm tra invariant:
- Không thể vào Paid nếu payment chưa captured.
- Không thể vào Approved nếu actor không có quyền.
- Process không có hai terminal state đồng thời.
- Một event ID chỉ được commit tối đa một lần.
- Mọi transition giữ state invariant.
- Retry count không vượt giới hạn.

### Concurrency test

Gửi đồng thời:
- Hai approval event.
- PaymentCaptured và CancelRequested.
- Hai timer event giống nhau.
- Event cũ và event mới theo thứ tự đảo.
- Hai worker xử lý cùng process version.

Kiểm tra optimistic locking, deduplication, idempotency và state consistency.

### Recovery và replay test

Restart engine khi process đang chờ timer, task bên ngoài hoặc compensation. Xác nhận process khôi phục đúng state, không mất event và không lặp side effect ngoài policy.

Replay nên chạy trong môi trường mô phỏng và không thực hiện external action thật.

### Model-based testing

Có thể tạo một state machine tham chiếu đơn giản rồi so sánh execution trace của workflow engine. Cách này giúp phát hiện khác biệt giữa semantics đặc tả và runtime implementation.

## Những lỗi thiết kế thường gặp

### Nhập trigger và guard làm một

Event đến không có nghĩa điều kiện nghiệp vụ đã đúng. Tách trigger khỏi guard để decision có thể được kiểm soát và giải thích.

### Đưa side effect vào guard

Guard có thể được đánh giá nhiều lần. Gửi email hoặc gọi payment trong guard dễ tạo side effect lặp. Giữ guard thuần và đặt công việc vào action/task.

### Không định nghĩa hành vi với null

Dữ liệu thiếu có thể khiến guard trả kết quả khó đoán hoặc lỗi runtime. Quy định Boolean/three-valued logic và xử lý UNKNOWN.

### Có nhiều transition cùng hợp lệ

Nếu không có priority, disjoint guard hoặc ambiguity error, engine có thể chọn nhánh không ổn định. Cần semantics lựa chọn rõ.

### Chỉ kiểm tra quyền ở UI

Client có thể bị giả mạo hoặc quyền bị thu hồi. Authorization phải được xác minh ở runtime và gần thời điểm commit.

### Không kiểm soát event duplicate

Message broker có thể gửi lại event. Không có deduplication và idempotency, một transition có thể chạy nhiều lần.

### Không đồng bộ state update

Hai worker có thể cùng chuyển một process từ state cũ. Dùng version, lock hoặc serialization per process.

### Timer không kiểm tra state hiện tại

Timer cũ có thể đến sau khi process đã rời state. Khi xử lý timeout, cần xác minh state/version và timer token.

### Không có compensation

Workflow nhiều hệ thống có thể đã tạo side effect trước khi bước sau thất bại. Cần xác định compensation và trạng thái theo dõi.

### Thay đổi workflow definition không có versioning

Process cũ có thể được đánh giá bằng guard mới hoặc state mapping không còn tương thích. Pin version hoặc migrate có kiểm soát.

### Không giải thích vì sao transition bị chặn

Người vận hành chỉ thấy process đứng yên mà không biết guard nào false. Cần decision record và diagnostics có kiểm soát quyền.

### Kiểm thử chỉ happy path

Boundary, null, duplicate event, timeout, concurrency và recovery thường là nơi lỗi nghiêm trọng xuất hiện. Cần test theo decision table và invariant.

## Quy trình thiết kế điều kiện chuyển trạng thái cho workflow DSL

Một quy trình thiết kế có thể đi theo các bước:

1. **Mô hình hóa state:** xác định trạng thái có ý nghĩa nghiệp vụ, initial state và terminal state.
2. **Liệt kê event và trigger:** xác định nguồn, payload, correlation và thời điểm kích hoạt.
3. **Định nghĩa guard:** viết predicate thuần trên process context, actor và kết quả task.
4. **Xác định invariant:** quy định điều gì phải đúng khi vào, ở trong và rời state.
5. **Định nghĩa action:** tách side effect khỏi guard và xác định thứ tự prepare/commit/after-commit.
6. **Quy định lựa chọn:** guard disjoint, priority, first-match hoặc ambiguity error.
7. **Xác định null/error semantics:** Boolean, UNKNOWN, missing data và evaluation failure.
8. **Bổ sung timeout và retry:** deadline, timer persistence, retryable error và giới hạn thử lại.
9. **Thiết kế concurrency:** process version, optimistic locking, idempotency và event deduplication.
10. **Thiết kế compensation:** mô tả hành động bù trừ và điều kiện kích hoạt.
11. **Kiểm soát authorization:** identity, permission, tenant scope và separation of duties.
12. **Thiết kế persistence/versioning:** process snapshot, event history, definition version và migration.
13. **Cung cấp diagnostics:** explain decision, guard outcome, source mapping và audit.
14. **Tích hợp tooling:** static analysis, state graph, completion và transition preview.
15. **Kiểm thử:** guard boundary, decision table, invariants, concurrency, recovery và replay.

Mỗi transition nên có một hợp đồng dễ đọc: state nguồn, trigger, guard, target, priority, action, lỗi có thể xảy ra và hành vi khi không đủ điều kiện. Với transition quan trọng, cần ghi rõ authorization, idempotency và yêu cầu transaction.

## Kết luận

Điều kiện chuyển trạng thái quyết định khi nào một workflow được phép đi từ state hiện tại sang state tiếp theo. Trong workflow DSL, transition thường kết hợp state nguồn, trigger, guard, state đích và action. Trigger khiến engine xem xét transition; guard đánh giá dữ liệu và ngữ cảnh; action thực hiện công việc sau khi transition được chọn; invariant bảo vệ tính hợp lệ của state và process.

Một thiết kế đáng tin cậy cần định nghĩa rõ kiểu và semantics của guard, xử lý null và UNKNOWN, phân biệt evaluation error, kiểm soát nhiều transition cùng hợp lệ và giữ guard thuần để tránh side effect. Runtime phải xử lý transaction, concurrency, duplicate event, timeout, retry, compensation, authorization, persistence và versioning.

Tooling như static analysis, state graph, diagnostics và explain decision giúp người thiết kế hiểu vì sao một transition có thể hoặc không thể xảy ra. Kiểm thử guard, decision table, invariant, race condition và recovery giúp bảo đảm workflow tiếp tục đúng trong cả tình huống bình thường lẫn lỗi. Khi các quy tắc này được đặc tả rõ, workflow DSL có thể mô tả quy trình nghiệp vụ phức tạp theo cách dễ đọc, kiểm tra và vận hành ổn định.

# Theo dõi tiến trình

Trong một ngôn ngữ miền đặc thù mô tả quy trình (Process DSL hoặc Workflow DSL), một định nghĩa thường mô tả các bước cần thực hiện, điều kiện rẽ nhánh, tác vụ song song, thời hạn và điểm chờ con người. Khi quy trình được khởi chạy, engine tạo một execution cụ thể và điều phối các bước theo mô hình đó. Người dùng và hệ thống vận hành cần biết execution đang ở đâu, đã hoàn thành phần nào, còn việc gì phải làm, có đang chờ dữ liệu hay phê duyệt không và khi nào quy trình có thể kết thúc.

**Theo dõi tiến trình** (*progress tracking*) là khả năng ghi nhận, tính toán và trình bày trạng thái thực hiện của một process instance theo thời gian. Nó liên kết định nghĩa quy trình với execution runtime, step, task, event, checkpoint và kết quả để trả lời các câu hỏi như: quy trình đang chạy, hoàn tất, thất bại hay bị tạm dừng; bước nào đã xong; nhánh nào đang chờ; tiến độ tổng thể được xác định theo quy tắc nào; và ai hoặc thành phần nào cần hành động tiếp theo.

Ví dụ một DSL xử lý đơn hàng:

~~~text
process FulfillOrder(order: Order) {
    step ValidateOrder {
        validate order;
    }

    step ReserveInventory {
        reserveInventory(order);
    }

    parallel Fulfillment {
        branch Payment {
            capturePayment(order);
        }
        branch Shipment {
            createShipment(order);
        }
    }

    humanTask ConfirmDelivery {
        assign to order.owner;
        wait for deliveryConfirmation;
    }

    step CompleteOrder {
        markCompleted(order);
    }
}
~~~

Khi process instance chạy, màn hình theo dõi có thể cho biết `ValidateOrder` và `ReserveInventory` đã hoàn tất, hai nhánh `Payment` và `Shipment` đang chạy hoặc một nhánh đã xong, còn `ConfirmDelivery` đang chờ người phụ trách xác nhận. Sau khi xác nhận được nhận và `CompleteOrder` kết thúc, instance mới chuyển sang trạng thái hoàn tất.

Theo dõi tiến trình không đơn thuần là hiển thị một thanh phần trăm. Process có thể có nhánh, vòng lặp, bước tùy chọn, retry, tác vụ chờ con người và thời gian chờ không xác định. Một con số 70% chỉ có ý nghĩa khi DSL hoặc runtime định nghĩa rõ cách tính. Trong nhiều trường hợp, trạng thái hiện tại, bước đang chờ và các mốc đã hoàn thành hữu ích hơn một tỷ lệ phần trăm thiếu cơ sở.

## 1. Theo dõi tiến trình là gì?

Theo dõi tiến trình là việc quan sát một process instance trong suốt vòng đời thực thi và duy trì một biểu diễn có thể truy vấn về trạng thái hiện tại cùng lịch sử chuyển trạng thái.

Một hệ thống progress tracking thường cần:

- Nhận diện process definition và phiên bản đã tạo instance.
- Định danh từng process instance và các step/task con.
- Ghi nhận trạng thái của instance, step, branch và task.
- Thu thập event khi execution bắt đầu, chuyển trạng thái, hoàn thành hoặc thất bại.
- Tính tiến độ theo cấu trúc và semantics của process.
- Lưu trạng thái đủ bền vững để tiếp tục theo dõi sau restart.
- Cung cấp API, dashboard hoặc notification cho người dùng và hệ thống khác.
- Giữ lịch sử để điều tra, audit và phân tích thời gian xử lý.

### Progress khác status

Status cho biết một đối tượng đang ở trạng thái nào, ví dụ `RUNNING`, `WAITING` hoặc `COMPLETED`. Progress thường mô tả mức độ hoàn thành của một công việc có nhiều phần. Một instance có status `RUNNING` có thể có progress 20%, 80% hoặc không xác định được phần trăm.

### Progress khác duration

Duration cho biết đã mất bao lâu hoặc thời gian dự kiến còn lại. Một process chạy 10 phút không nhất thiết hoàn thành 50% nếu một bước cuối có thể mất vài giờ. Thời gian đã trôi qua không phải là thước đo tiến độ trừ khi mô hình quy trình định nghĩa rõ cách ước lượng.

### Progress khác health

Health phản ánh execution có đang hoạt động bình thường không, ví dụ có lỗi, backlog, heartbeat cũ hoặc dependency mất kết nối. Một instance có thể đang ở 80% nhưng unhealthy do một nhánh retry liên tục; cũng có thể healthy nhưng đang chờ người dùng phê duyệt.

## 2. Vì sao process DSL cần theo dõi tiến trình?

### Hiển thị trạng thái cho người sử dụng

Người khởi tạo quy trình muốn biết yêu cầu đã được tiếp nhận, đang xử lý, cần bổ sung thông tin hay đã hoàn tất. Thông tin này giúp giảm việc hỏi thủ công và tạo trải nghiệm minh bạch.

### Điều phối công việc

Operator có thể phát hiện task đang chờ quá lâu, nhánh bị lỗi, worker không còn heartbeat hoặc queue tăng bất thường để điều phối lại.

### Quản lý SLA và deadline

Process có thể có thời hạn tổng thể hoặc thời hạn cho từng task. Tracking cung cấp dữ liệu để xác định instance có nguy cơ trễ, đã vi phạm SLA hay cần escalation.

### Phục hồi và tiếp tục thực thi

Khi engine restart, checkpoint và state cho biết bước nào đã hoàn tất, bước nào đang chờ và bước nào có thể được tiếp tục. Progress tracking vì vậy có quan hệ trực tiếp với persistence và recovery.

### Phân tích bottleneck

Lịch sử trạng thái và timestamp cho thấy bước nào thường mất nhiều thời gian, queue nào bị nghẽn hoặc loại task nào thường phải retry.

### Audit và trách nhiệm

Với quy trình nghiệp vụ quan trọng, tổ chức cần biết ai phê duyệt, ai thực hiện task, khi nào trạng thái đổi và process definition version nào được dùng.

## 3. Các cấp đối tượng cần theo dõi

Một process thường có nhiều cấp cấu trúc. Theo dõi chỉ ở cấp instance có thể không đủ để giải thích tiến trình.

| Cấp | Đối tượng | Thông tin thường theo dõi |
|---|---|---|
| Definition | Định nghĩa process | Tên, version, cấu trúc và policy tiến độ. |
| Instance | Một lần chạy process | Status, start/end time, progress summary. |
| Scope | Nhóm bước hoặc block | Status tổng hợp, child scopes. |
| Step | Một bước trong định nghĩa | Status, start/end, retry, output reference. |
| Task | Công việc được giao hoặc thực thi | Assignee, queue, deadline, completion. |
| Branch | Nhánh trong parallel/race flow | Trạng thái từng nhánh và join condition. |
| Event | Sự kiện runtime | Sequence, timestamp, source và correlation. |
| Checkpoint | Điểm lưu trạng thái | State version, position và dữ liệu phục hồi. |

### Definition và instance

Definition là mô hình quy trình được khai báo trong DSL. Instance là một lần chạy cụ thể của definition. Một definition có thể tạo hàng nghìn instance; mỗi instance cần ID riêng và gắn với đúng definition version.

### Step và task

Step là phần tử cấu trúc trong process definition. Task là công việc runtime được thực hiện bởi worker, service hoặc người dùng. Một step có thể tạo nhiều task, ví dụ gửi yêu cầu đến nhiều hệ thống hoặc chia công việc cho nhiều người.

### Scope

Scope nhóm một phần quy trình, như transaction scope, subprocess hoặc parallel block. Scope có thể có status tổng hợp từ các child step và quy tắc xử lý lỗi riêng.

### Event và checkpoint

Event ghi nhận điều đã xảy ra; checkpoint lưu trạng thái cần thiết để phục hồi. Event history và checkpoint bổ sung cho nhau nhưng không thay thế nhau.

## 4. Vòng đời của process instance

Một process instance thường trải qua nhiều trạng thái từ lúc được tạo đến khi kết thúc.

Ví dụ state model:

~~~text
CREATED -> READY -> RUNNING -> COMPLETED
                       |
                       +-> WAITING -> RUNNING
                       |
                       +-> FAILED
                       |
                       +-> CANCELLED
                       |
                       +-> SUSPENDED -> RUNNING
~~~

Các trạng thái gợi ý:

| Status | Ý nghĩa |
|---|---|
| `CREATED` | Instance đã được tạo nhưng chưa bắt đầu điều phối. |
| `READY` | Đủ điều kiện bắt đầu hoặc đã được đưa vào queue. |
| `RUNNING` | Engine đang thực hiện một hoặc nhiều bước. |
| `WAITING` | Đang chờ event, timer, external response hoặc human task. |
| `SUSPENDED` | Bị tạm dừng theo yêu cầu hoặc policy. |
| `COMPLETED` | Quy trình kết thúc thành công theo semantics của definition. |
| `FAILED` | Quy trình kết thúc do lỗi không được xử lý. |
| `CANCELLED` | Instance bị hủy theo yêu cầu hoặc policy. |
| `TIMED_OUT` | Deadline tổng thể hoặc giới hạn thực thi đã hết. |
| `COMPENSATING` | Đang chạy các bước bù trừ sau lỗi hoặc hủy. |
| `COMPENSATED` | Quá trình bù trừ đã hoàn tất. |

State model thực tế có thể gộp hoặc bổ sung trạng thái. Cần xác định trạng thái terminal nào không thể chuyển tiếp và trạng thái nào có thể resume.

### State transition

Mọi chuyển trạng thái nên có điều kiện rõ ràng. Ví dụ `WAITING -> RUNNING` chỉ xảy ra khi event chờ đã được nhận và xác thực. `FAILED -> RUNNING` không nên tự xảy ra trừ khi hệ thống có semantics retry/restart rõ.

### Terminal state

`COMPLETED`, `FAILED` và `CANCELLED` thường là terminal. `COMPENSATING` chưa phải terminal vì engine còn thực hiện công việc. Nếu cho phép reopen hoặc restart, cần phân biệt instance cũ với một attempt hoặc execution mới.

### Pause và suspend

Pause có thể chỉ dừng scheduler trong thời gian ngắn; suspend có thể lưu trạng thái để tiếp tục sau. DSL/runtime cần xác định timer có tiếp tục chạy trong thời gian suspend hay không.

## 5. Vòng đời của step và task

Mỗi step có state machine riêng. Instance có thể `RUNNING` trong khi một step `WAITING` và một step khác trong parallel branch `COMPLETED`.

Ví dụ:

~~~text
PENDING -> READY -> RUNNING -> COMPLETED
                       |
                       +-> WAITING -> RUNNING
                       |
                       +-> RETRYING -> RUNNING
                       |
                       +-> FAILED
                       |
                       +-> SKIPPED
                       |
                       +-> CANCELLED
~~~

Các trạng thái phổ biến:

- `PENDING`: chưa đủ điều kiện chạy.
- `READY`: dependencies đã hoàn tất và step có thể chạy.
- `RUNNING`: worker đang thực hiện.
- `WAITING`: chờ event, resource hoặc human input.
- `RETRYING`: chuẩn bị thực hiện lại sau lỗi.
- `COMPLETED`: step hoàn tất theo contract.
- `FAILED`: step thất bại và không còn retry tự động.
- `SKIPPED`: step được bỏ qua theo branch condition hoặc policy.
- `CANCELLED`: step bị hủy.
- `COMPENSATING`: đang chạy action bù trừ.

### Một step có thể có nhiều attempt

Nếu task lỗi rồi retry, không nên ghi đè lịch sử attempt cũ. Step có thể có trạng thái tổng thể `RUNNING` hoặc `RETRYING`, còn mỗi attempt có ID, start/end time, error và kết quả riêng.

### Task được giao cho người dùng

Human task có thể chuyển từ `READY` sang `ASSIGNED`, `CLAIMED`, `IN_PROGRESS`, `COMPLETED` hoặc `EXPIRED`. Cần ghi assignee, nhóm, thời hạn và thời điểm hoàn thành.

### Completion contract

Step chỉ được đánh dấu `COMPLETED` khi điều kiện hoàn tất của nó đã được thỏa mãn. Việc worker trả về không lỗi chưa chắc đủ nếu cần xác nhận dữ liệu đã commit hoặc external operation đã được xác nhận.

## 6. Mô hình dữ liệu theo dõi tiến trình

Một mô hình runtime có thể gồm các record sau:

~~~text
ProcessInstance
  instanceId
  definitionId
  definitionVersion
  status
  startedAt
  updatedAt
  completedAt
  progress
  currentScopes[]
  stateVersion

StepExecution
  stepExecutionId
  instanceId
  stepDefinitionId
  parentScopeId
  status
  startedAt
  completedAt
  attemptCount
  outputReference

TaskExecution
  taskId
  stepExecutionId
  taskType
  assignee
  status
  dueAt

ProgressSnapshot
  instanceId
  completedUnits
  totalUnits
  percentage
  calculationPolicy
  calculatedAt
~~~

Đây là mô hình khái niệm. Có thể lưu dưới dạng relational tables, document records, event stream hoặc kết hợp. Điều quan trọng là phân biệt definition identity, runtime execution identity và attempt identity.

### Stable IDs

Step definition ID phải ổn định giữa các lần deploy nếu cần liên kết lịch sử. Không nên chỉ dùng vị trí step trong danh sách vì thêm một step phía trước có thể làm thay đổi index. Step execution ID định danh lần thực hiện cụ thể; attempt ID định danh một lần thử.

### State version

`stateVersion` tăng khi trạng thái instance được cập nhật. Nó hỗ trợ optimistic concurrency và giúp client biết snapshot có mới hơn hay không.

### Progress snapshot là dữ liệu dẫn xuất

Percentage thường có thể tính từ step state và progress policy. Nếu lưu snapshot để truy vấn nhanh, cần ghi calculation policy/version và thời điểm tính; không nên coi snapshot là nguồn sự thật độc lập với event/state.

## 7. Event model cho progress tracking

Một cách phổ biến để duy trì lịch sử là ghi event khi process hoặc step thay đổi.

Các event ví dụ:

~~~text
ProcessCreated
ProcessStarted
StepReady
StepStarted
StepWaiting
StepCompleted
StepFailed
StepRetryScheduled
TaskAssigned
TaskClaimed
TaskCompleted
BranchJoined
ProcessSuspended
ProcessResumed
ProcessCompleted
ProcessFailed
ProcessCancelled
~~~

Một event nên có:

- `eventId`: ID duy nhất.
- `instanceId`: process instance liên quan.
- `stepExecutionId` hoặc `taskId` nếu áp dụng.
- `sequence`: thứ tự trong instance hoặc partition.
- `eventType`: loại sự kiện.
- `occurredAt`: thời điểm sự kiện xảy ra.
- `recordedAt`: thời điểm event được lưu.
- `actor` hoặc `source`: người/worker/service tạo event.
- `correlationId` và `causationId`: liên kết luồng nghiệp vụ.
- `payload`: dữ liệu cần thiết cho event.

### Event time và processing time

`occurredAt` có thể đến từ worker hoặc external system; `recordedAt` là thời điểm event store nhận được. Hai thời điểm có thể khác do mạng, clock skew hoặc queue. Dùng sequence hoặc causal ordering khi cần xác định thứ tự logic.

### Event append-only

Event lịch sử thường không bị sửa trực tiếp. Nếu có sai sót, có thể ghi correction event hoặc administrative event. Cách này giữ audit trail và hỗ trợ rebuild projection.

### Duplicate event

Worker hoặc message broker có thể gửi lại event. Event consumer cần idempotency theo event ID hoặc operation ID để không tăng progress hai lần.

## 8. Tính phần trăm tiến độ

Phần trăm tiến độ hữu ích khi người dùng cần một tín hiệu tổng quan, nhưng cách tính phải phù hợp với cấu trúc process.

### Đếm step hoàn tất

Với quy trình tuần tự gồm các step có trọng số bằng nhau:

~~~text
progress = completedSteps / totalSteps * 100
~~~

Ví dụ 3 trong 5 step đã hoàn tất thì progress là 60%. Cách tính này dễ hiểu nhưng không phù hợp nếu một step nhỏ và một step lớn có effort rất khác nhau.

### Trọng số step

Có thể gán weight cho từng step:

~~~text
step ValidateOrder weight 1;
step ReserveInventory weight 2;
step CapturePayment weight 3;
step CreateShipment weight 4;
~~~

Nếu các step đầu hoàn tất, progress được tính bằng tổng trọng số hoàn thành chia tổng trọng số. Trọng số là ước lượng do người thiết kế hoặc chủ quy trình cung cấp; nó không tự động phản ánh thời gian thực tế.

### Progress theo milestone

Một process có thể định nghĩa milestone nghiệp vụ như `OrderValidated`, `PaymentCaptured`, `ShipmentCreated` và `Delivered`. Milestone có thể hữu ích hơn phần trăm vì nó thể hiện kết quả mà người dùng hiểu được.

### Progress theo đơn vị công việc

Với batch process, có thể tính số record đã xử lý trên tổng số record. Ví dụ 800/1.000 đơn hàng đã được nhập dữ liệu. Cần phân biệt processed, succeeded, failed và skipped.

### Progress theo sub-process

Một step có thể chứa subprocess nhiều cấp. Parent progress có thể tổng hợp child progress theo weight, nhưng phải tránh đếm trùng cùng một công việc ở nhiều cấp.

### Không biết tổng số công việc

Với stream vô hạn hoặc process chờ điều kiện dừng, tổng units không xác định. Khi đó percentage không có ý nghĩa; nên hiển thị trạng thái, số item đã xử lý hoặc thông tin throughput.

## 9. Weighted progress và lựa chọn trọng số

Một công thức tổng quát:

\[
P = \frac{\sum_i w_i c_i}{\sum_i w_i} \times 100\%
\]

Trong đó:

- (w_i) là trọng số của work unit (i).
- (c_i) là mức hoàn thành của unit, thường từ 0 đến 1.
- (P) là phần trăm tổng hợp.

Ví dụ có ba step với weight lần lượt 1, 3 và 6. Step thứ nhất hoàn tất, step thứ hai đang hoàn thành 50%, step cuối chưa bắt đầu:

\[
P = \frac{1(1) + 3(0.5) + 6(0)}{1+3+6} \times 100 = 25\%
\]

### Chọn weight theo effort

Weight có thể dựa trên effort ước lượng, số lượng work item, chi phí xử lý hoặc giá trị milestone. Cần chọn một cách có ý nghĩa và giữ nhất quán trong một process version.

### Tránh weight tùy tiện

Nếu các step có weight không được giải thích, percentage có thể tạo cảm giác chính xác giả. Người dùng có thể hiểu 80% là đã hoàn thành 80% thời gian hoặc công sức dù công thức chỉ là ước lượng.

### Weight theo dữ liệu runtime

Với batch, weight có thể dựa trên số record thực tế. Nếu tổng record thay đổi khi process chạy, progress có thể giảm dù không có công việc nào bị hoàn tác. Cần định nghĩa denominator có được phép thay đổi không và UI giải thích ra sao.

### Đóng băng progress policy

Progress calculation policy nên gắn với process definition version. Nếu đổi weight khi instance đang chạy, percentage lịch sử có thể thay đổi mà không có event công việc mới. Có thể pin policy lúc instance start hoặc tạo event migration có giải thích.

## 10. Progress trong nhánh điều kiện

Process thường có nhánh `if/else`, switch hoặc gateway. Không phải mọi step trong definition đều được thực hiện ở một instance.

Ví dụ:

~~~text
if order.total >= 1000 {
    requireManagerApproval;
} else {
    autoApprove;
}
~~~

Nếu `order.total` là 500, nhánh `autoApprove` được chọn còn `requireManagerApproval` bị bỏ qua. Nếu mẫu số vẫn tính cả hai nhánh như hai step bắt buộc, progress sẽ không bao giờ đạt 100%.

### Eligible work units

Mẫu số cần tính các work unit thực sự được chọn hoặc có khả năng tham gia theo semantics của instance. Step trong nhánh không được chọn có thể có trạng thái `NOT_APPLICABLE` hoặc `SKIPPED`.

### Skipped không phải failed

Một step bị bỏ qua vì condition false có thể là kết quả hợp lệ. Không nên xem nó như lỗi hoặc công việc chưa hoàn tất.

### Branch selection event

Nên ghi event thể hiện branch nào được chọn và điều kiện quyết định. Điều này giúp progress projection biết nhánh nào thuộc phạm vi instance.

### Re-evaluation

Nếu process cho phép thay đổi dữ liệu làm branch được đánh giá lại, cần xác định liệu nhánh đã chọn có thể đổi sau khi bắt đầu hay không. Việc đổi nhánh có thể cần compensation và progress correction.

## 11. Progress trong vòng lặp

Vòng lặp tạo nhiều iteration của cùng một step definition. Cần phân biệt step definition với step execution của từng iteration.

Ví dụ:

~~~text
for each item in order.items {
    processItem(item);
}
~~~

Nếu có 100 item và 65 item đã xử lý xong, progress theo item có thể là 65%. Tuy nhiên, mỗi item có thể có thời gian xử lý khác nhau và lỗi có thể được retry.

### Iteration identity

Mỗi iteration cần ID hoặc key ổn định, chẳng hạn item ID. Không nên dùng index nếu danh sách có thể được sắp xếp lại hoặc chèn phần tử.

### Dynamic collection

Nếu item được thêm trong lúc process chạy, tổng work units có thể tăng. Cần quy định collection được snapshot lúc start hay được đọc động.

### Loop không biết trước số lần

Với `while` loop hoặc event-driven loop, không có denominator cố định. Hiển thị số iteration, throughput hoặc current condition thường hợp lý hơn phần trăm.

### Retry iteration

Một item xử lý thất bại rồi retry không nên được tính như hai item. Progress cần dựa trên logical work unit, còn attempts là thông tin riêng.

### Partial completion

Batch có thể có một số item thành công, một số item lỗi và một số item đang chờ. Progress nên hiển thị breakdown thay vì chỉ một con số tổng.

## 12. Progress trong tác vụ song song

Parallel block chạy nhiều branch đồng thời. Một parent scope chỉ hoàn tất khi join condition được thỏa mãn.

Ví dụ:

~~~text
parallel Fulfillment {
    branch Payment {
        capturePayment(order);
    }
    branch Shipment {
        createShipment(order);
    }
    branch Notification {
        sendConfirmation(order);
    }
}
join all;
~~~

### Tổng hợp theo branch

Nếu ba branch có weight bằng nhau, hai branch hoàn tất có thể tương ứng 66,7% của parallel block. Nếu branch có effort khác nhau, cần weight hoặc progress policy riêng.

### Join all

Parent chỉ hoàn tất khi mọi branch bắt buộc hoàn tất. Branch lỗi có thể làm parent fail hoặc kích hoạt compensation theo policy.

### Join any

Parent có thể tiếp tục khi một branch hoàn tất. Các branch còn lại có thể bị cancel hoặc tiếp tục chạy nền. Progress phải phản ánh semantics của join, không đợi các branch đã bị cancel.

### Quorum join

Một số process yêu cầu tối thiểu (k) trong (n) branch thành công. Progress có thể dựa trên số branch đã đáp ứng quorum và trạng thái branch còn lại. Cần hiển thị rõ điều kiện hoàn tất.

### Branch failure

Nếu một branch fail nhưng các branch khác vẫn chạy, parent có thể ở `RUNNING`, `DEGRADED` hoặc `FAILING` tùy model. Không nên tự động đánh dấu parent failed trước khi join/error policy được xử lý.

### Race và cancellation

Với race gateway, branch thắng có thể làm branch khác bị cancel. Branch bị cancel không nhất thiết là failure. Progress projection cần biết cancellation là hệ quả hợp lệ của race.

## 13. Progress của human task

Human task thường có thời gian chờ dài và trạng thái khác với service task.

Một lifecycle có thể là:

~~~text
CREATED -> READY -> ASSIGNED -> CLAIMED -> IN_PROGRESS -> COMPLETED
                         |          |
                         |          +-> RELEASED -> READY
                         +-> EXPIRED
~~~

### Assignment

Task có thể được giao cho một user, role hoặc group. Progress view cần cho biết task đang được giao cho ai hoặc nhóm nào theo quyền truy cập.

### Claim và start

Trong một số hệ thống, task được đưa vào inbox trước khi có người claim. Khi claim, task có owner cụ thể; khi start, người đó bắt đầu xử lý. Các mốc này có thể được dùng để tính thời gian chờ và thời gian làm việc.

### Completion

Human task có thể yêu cầu form submission, attachment, approval hoặc một decision. Task chỉ hoàn tất khi dữ liệu được xác thực và lưu bền vững.

### Delegation và reassignment

Task có thể được chuyển người xử lý. Lịch sử cần ghi assignee trước/sau, actor và lý do. Reassignment không nên làm mất thời gian chờ đã tích lũy.

### Deadline và escalation

Task có thể có `dueAt`, reminder và escalation policy. Dashboard có thể phân biệt chưa đến hạn, sắp đến hạn và quá hạn.

### Privacy

Không phải mọi người xem process đều được biết tên người xử lý hoặc nội dung form. Progress API cần áp dụng quyền theo task và dữ liệu.

## 14. Progress của timer, event wait và external callback

Một process có thể dừng để chờ thời gian hoặc sự kiện bên ngoài.

Ví dụ:

~~~text
wait for paymentConfirmation timeout 24h;
~~~

Trong thời gian chờ, process có thể ở `WAITING`. Thông tin hữu ích gồm event đang chờ, thời điểm bắt đầu chờ, deadline, thời gian còn lại ước tính và cách xử lý timeout.

### Timer state

Timer có thể là scheduled, fired, cancelled hoặc expired. Cần ghi thời điểm dự kiến và thực tế, timezone và clock source.

### Event correlation

External event cần được ghép với đúng process instance và wait state. Correlation key nên ổn định và không chỉ dựa trên dữ liệu có thể trùng.

### Duplicate callback

External system có thể gửi callback nhiều lần. Event consumer cần idempotency để một callback không hoàn tất task hoặc tăng progress nhiều lần.

### Late event

Event có thể đến sau timeout. DSL cần quy định event đến muộn bị bỏ qua, được xem xét thủ công hay mở một nhánh xử lý bù.

### Waiting không phải idle vô hạn

Process ở `WAITING` vẫn có thể khỏe mạnh nếu đang chờ điều kiện hợp lệ. Cần phân biệt waiting bình thường với stuck state, nơi event đáng lẽ đã đến nhưng không có phản hồi trong giới hạn.

## 15. Milestone và stage-based progress

Milestone là mốc nghiệp vụ thể hiện một kết quả có ý nghĩa trong process. Nó thường dễ hiểu hơn phần trăm step hoàn thành.

Ví dụ:

~~~text
milestone OrderAccepted;
milestone PaymentConfirmed;
milestone ShipmentDispatched;
milestone DeliveryConfirmed;
~~~

Một timeline có thể hiển thị:

~~~text
Order accepted       [Completed]
Payment confirmed    [Completed]
Shipment dispatched  [In progress]
Delivery confirmed   [Pending]
~~~

### Milestone semantics

Milestone nên có điều kiện đạt rõ ràng, có thể dựa trên event, output hoặc trạng thái của scope. Không nên đánh dấu milestone hoàn thành chỉ vì một step có tên tương tự đã chạy.

### Milestone có thể không tuần tự

Một số process có thể đạt nhiều milestone song song hoặc theo thứ tự khác nhau. UI nên thể hiện dependency thay vì ép mọi milestone vào một tuyến tính giả.

### Stage

Stage có thể nhóm nhiều step thành giai đoạn như `Validation`, `Approval`, `Fulfillment`. Stage progress được tổng hợp từ child steps hoặc milestone theo policy.

### Milestone rollback

Nếu process có compensation hoặc re-open, một milestone có thể bị invalidated hoặc chuyển sang trạng thái compensated. Lịch sử cần giữ thời điểm đạt ban đầu và event làm thay đổi trạng thái.

## 16. Ước lượng thời gian còn lại

Estimated Time Remaining (ETR) có thể hữu ích nhưng thường không chắc chắn.

Một cách ước lượng đơn giản:

\[
ETR = \frac{1-P}{P} \times T_{elapsed}
\]

Trong đó (P) là progress dạng tỷ lệ từ 0 đến 1. Công thức này giả định tốc độ tiến triển gần như ổn định, nên có thể sai với process có bước cuối dài hoặc waiting time không dự đoán được.

### Historical duration

Có thể ước lượng thời gian của từng step dựa trên các instance trước cùng process version, resource type và workload tương tự.

### Queue time và execution time

Tách thời gian chờ trong queue, thời gian worker thực thi và thời gian chờ external/human. Nếu chỉ lấy duration tổng, khó xác định bottleneck.

### Percentile estimate

Thay vì chỉ hiển thị một giá trị, có thể cung cấp khoảng dự kiến dựa trên p50/p90 của lịch sử. Cần nói rõ đây là ước lượng, không phải deadline cam kết.

### Process chưa có đủ lịch sử

Với process version mới hoặc loại input hiếm, ETR có thể không đáng tin. UI nên hiển thị “chưa đủ dữ liệu để ước lượng” thay vì tạo số giả chính xác.

### Waiting time

Human approval hoặc external callback có thể chiếm phần lớn thời gian và khó dự đoán. Mô hình ước lượng cần tách waiting time khỏi processing time.

## 17. Tiến trình có thể tăng, giảm hoặc không xác định

Một thanh progress truyền thống thường tăng từ 0 đến 100%, nhưng process thực tế có thể phức tạp hơn.

### Monotonic progress

Progress monotonic chỉ tăng hoặc giữ nguyên. Nó phù hợp khi tập work units cố định và không có rollback.

### Non-monotonic progress

Progress có thể giảm khi thêm item mới, phát hiện lại work hoặc rollback một bước. Nếu cho phép, UI cần giải thích nguyên nhân thay đổi.

### Indeterminate progress

Khi không biết tổng work hoặc đang chờ một sự kiện không xác định thời điểm, hiển thị trạng thái đang xử lý/chờ thay vì percentage.

### Progress có thể đạt 100% trước terminal state?

Nếu mọi work unit nghiệp vụ đã hoàn tất nhưng process còn bước cleanup hoặc audit, progress có thể là 100% trong khi instance chưa `COMPLETED`. Nên định nghĩa 100% chỉ khi process đạt terminal success hoặc tách `workProgress` và `lifecycleStatus`.

### Failed process

Một instance fail ở 80% không có nghĩa 80% quy trình thành công. Có thể hiển thị `80% work completed before failure` cùng trạng thái `FAILED`, không nên chỉ hiển thị một thanh 80% màu xanh.

## 18. Progress trong subprocess và hierarchical process

Một process có thể gọi subprocess hoặc tạo scope lồng nhau.

Ví dụ:

~~~text
process FulfillOrder {
    call ValidateCustomer;
    call ProcessPayment;
    call PrepareShipment;
    call NotifyCustomer;
}
~~~

Mỗi subprocess có instance hoặc execution scope riêng, nhưng parent cần tổng hợp trạng thái.

### Parent-child linkage

Subprocess cần lưu parent instance ID và parent step execution ID. Điều này giúp điều hướng từ parent đến child và truy vấn tiến độ tổng thể.

### Aggregate status

Parent có thể `RUNNING` khi child đang chạy; `WAITING` khi child chờ human task; `FAILED` khi child lỗi không được xử lý. Quy tắc aggregate cần được định nghĩa.

### Aggregate progress

Parent có thể tính progress từ subprocess weight hoặc milestone. Không nên cộng progress của parent step và toàn bộ child step cùng lúc nếu chúng đại diện cùng công việc, vì sẽ double-count.

### Nhiều cấp nesting

Với process lồng sâu, API có thể trả summary ở cấp parent và cho phép truy vấn chi tiết từng child. Không nên tải toàn bộ cây execution lớn cho mọi request dashboard.

## 19. Retry, timeout và compensation trong progress

Retry và compensation ảnh hưởng cách hiểu tiến độ.

### Retry

Một step fail tạm thời có thể retry. Logical step vẫn chưa hoàn tất cho đến khi một attempt thành công hoặc policy kết luận fail cuối cùng.

Progress có thể hiển thị:

~~~text
ReserveInventory
  status: RETRYING
  attempts: 2
  lastError: INVENTORY_SERVICE_TIMEOUT
  nextRetryAt: 10:05:30
~~~

### Timeout

Timeout có thể áp dụng cho step, task hoặc toàn process. Khi timeout, engine có thể fail, retry, escalate, chạy fallback hoặc compensation. Tracking cần cho biết timeout nào đã xảy ra và policy xử lý ra sao.

### Compensation

Trong saga/process có side effect, lỗi ở bước sau có thể kích hoạt action bù trừ cho các bước trước. Khi đó progress có thể chuyển sang `COMPENSATING`; không nên tiếp tục hiển thị như đang đi về phía hoàn thành bình thường.

### Attempt progress và logical progress

Attempt progress phản ánh lần thử hiện tại. Logical progress phản ánh step đã hoàn tất hay chưa. Nếu step retry ba lần rồi thành công, nó chỉ đóng góp một work unit hoàn thành.

### Retry delay

Trong backoff, step có thể ở `RETRYING` hoặc `WAITING_RETRY`. UI nên hiển thị thời điểm retry tiếp theo và số lần đã thử, nếu người xem có quyền.

## 20. Checkpoint và phục hồi tiến trình

Theo dõi tiến trình cần tồn tại qua restart, crash hoặc deploy mới. Checkpoint lưu đủ trạng thái để engine biết tiếp tục từ đâu.

Một checkpoint có thể chứa:

- Process instance ID và definition version.
- State version hoặc event sequence đã áp dụng.
- Current scope và program counter/workflow position.
- Trạng thái step/task/branch.
- Variables hoặc reference đến process data.
- Timer và subscription đang chờ.
- Retry metadata và deadline.
- Pending external operation ID.
- Compensation state nếu có.

### Snapshot và event history

Có thể lưu snapshot định kỳ và replay event từ snapshot đến hiện tại. Snapshot giảm thời gian phục hồi; event history giữ lịch sử và khả năng tái dựng.

### Exactly-once không phải giả định mặc định

Message hoặc worker có thể xử lý lại sau crash. Step có side effect cần idempotency key hoặc operation ledger. Progress event phải chống duplicate để một action không bị tính hoàn thành hai lần.

### Checkpoint consistency

Checkpoint cần được ghi nhất quán với event hoặc operation state liên quan. Nếu engine ghi `StepCompleted` nhưng chưa lưu output cần thiết, recovery có thể bỏ qua bước và làm process thiếu dữ liệu.

### Definition version pinning

Instance đang chạy thường cần tiếp tục theo semantics của definition version lúc khởi tạo. Nếu muốn migrate sang version mới, phải có migration plan và event ghi nhận thay đổi.

## 21. Persistence và event projection

Một kiến trúc tracking có thể dùng event log làm nguồn lịch sử và tạo projection phục vụ truy vấn.

~~~mermaid
flowchart TD
    A[Process Engine] --> B[Execution Events]
    B --> C[Durable Event Store]
    C --> D[Progress Projector]
    D --> E[Instance State View]
    D --> F[Step / Task View]
    D --> G[Metrics and Timeline]
    E --> H[Progress API]
    F --> H
    G --> H
    H --> I[Dashboard / Client]
~~~

### Event store

Event store lưu event append-only theo instance hoặc partition. Nó là cơ sở cho audit và rebuild projection.

### Projection

Projector tiêu thụ event và cập nhật bảng hoặc document có trạng thái hiện tại. Dashboard truy vấn projection thay vì replay toàn bộ event mỗi lần.

### Eventual consistency

Projection có thể chậm hơn engine. API cần trả `asOfSequence`, `updatedAt` hoặc state version để client biết dữ liệu được cập nhật đến đâu.

### Rebuild projection

Nếu projection bị lỗi hoặc schema thay đổi, có thể rebuild từ event history. Projector cần idempotent và có thể chạy lại.

### Snapshot retention

Không phải mọi event kỹ thuật cần giữ mãi. Cần retention policy phân biệt audit events, detailed trace, progress snapshots và metrics aggregate.

## 22. API theo dõi tiến trình

API cần cung cấp cả summary và detail, đồng thời hỗ trợ truy vấn trạng thái mới nhất và lịch sử.

Ví dụ response summary:

~~~json
{
  "instanceId": "proc-1042",
  "definition": {
    "id": "FulfillOrder",
    "version": "7"
  },
  "status": "RUNNING",
  "progress": {
    "mode": "WEIGHTED",
    "completedUnits": 5,
    "totalUnits": 8,
    "percentage": 62.5,
    "calculatedAt": "2026-11-15T10:05:00Z"
  },
  "currentSteps": [
    {
      "stepId": "CapturePayment",
      "status": "RUNNING"
    },
    {
      "stepId": "ConfirmDelivery",
      "status": "WAITING"
    }
  ],
  "stateVersion": 42
}
~~~

Đây là response minh họa. Contract thực tế cần định nghĩa timezone, numeric precision, nullability, pagination và cách biểu diễn progress không xác định.

### Summary endpoint

Trả status, progress, current step, start time, deadline và last update. Phù hợp với list view hoặc dashboard.

### Detail endpoint

Trả step tree, branch, task, retry và milestone. Có thể phân trang hoặc tải theo scope.

### Timeline endpoint

Trả event history theo cursor hoặc sequence. Không nên tải toàn bộ event stream cho một request.

### Subscribe/push updates

Client có thể nhận update qua WebSocket, Server-Sent Events hoặc message subscription. Cần có sequence/cursor để client phục hồi nếu mất kết nối.

### Conditional requests

API có thể hỗ trợ ETag hoặc state version để client chỉ lấy dữ liệu mới khi state đã đổi. Điều này giảm polling và tải server.

### Cancellation và control API

Theo dõi là read operation; pause, resume, cancel hoặc retry là control operation. Nên tách endpoint, permission và audit của các thao tác điều khiển khỏi API đọc tiến trình.

## 23. Giao diện hiển thị tiến trình

UI cần chọn cách trình bày phù hợp với người xem và cấu trúc process.

### Progress bar

Phù hợp với process có tổng work units xác định và calculation policy ổn định. Nên kèm label như `5/8 bước` để người dùng hiểu cơ sở phần trăm.

### Step list

Hiển thị từng step với trạng thái, thời gian bắt đầu/kết thúc, người phụ trách và thông tin lỗi. Hữu ích với quy trình có thứ tự rõ.

### Timeline

Hiển thị event theo thời gian: bắt đầu, chờ, retry, hoàn tất, phê duyệt. Timeline giúp điều tra và hiểu thời gian chờ.

### Workflow graph

Với branch và parallel flow, graph có thể cho thấy nhánh nào hoàn tất, đang chạy hoặc bị lỗi. Cần có cách hiển thị dễ hiểu khi graph lớn.

### Milestone view

Phù hợp với người dùng nghiệp vụ cần biết các mốc lớn hơn là chi tiết runtime.

### Task inbox

Human task có thể được hiển thị trong inbox với assignee, due date, priority và trạng thái.

### Unknown/indeterminate state

Nếu không thể tính percentage, UI nên hiển thị `Đang chờ xác nhận` hoặc `Đang xử lý` thay vì 0% hoặc 100% giả.

### Accessibility

Không chỉ dùng màu để phân biệt completed, failed và waiting. Cần icon, text label, keyboard navigation và screen reader description.

## 24. Notification và cập nhật thời gian thực

Progress có thể được đẩy đến client khi event quan trọng xảy ra.

Các event đáng gửi notification:

- Process started hoặc completed.
- Process failed hoặc timed out.
- Human task được giao hoặc sắp đến hạn.
- Task cần input từ người dùng.
- Critical branch failed.
- Process chuyển sang compensation.
- SLA có nguy cơ bị vi phạm.

### Tránh notification quá nhiều

Không nhất thiết gửi thông báo cho mỗi internal step hoặc heartbeat. Có thể gộp event, chỉ gửi transition quan trọng hoặc cho phép subscription theo instance, owner và severity.

### Ordering và replay

Client có thể nhận event trễ hoặc trùng. Message cần sequence và event ID; client có thể deduplicate và yêu cầu replay từ cursor cuối cùng.

### Notification preference

Người dùng có thể chọn email, in-app hoặc webhook theo loại event. Cần giữ notification delivery status riêng với process status; email gửi thất bại không có nghĩa process fail.

## 25. SLA, deadline và escalation

Process DSL có thể khai báo SLA ở cấp instance, stage hoặc task.

Ví dụ:

~~~text
humanTask ManagerApproval {
    assign to role.Manager;
    due within 4 hours;
    escalate to role.Director when overdue;
}
~~~

### Business calendar

Deadline có thể tính theo giờ làm việc, ngày nghỉ và timezone thay vì thời gian liên tục. Cần xác định calendar version và timezone được dùng.

### SLA clock

SLA clock có thể pause khi chờ khách hàng hoặc khi instance bị suspended. Policy cần quy định trạng thái nào dừng đồng hồ.

### Warning threshold

Có thể phát cảnh báo khi đã sử dụng 80% thời gian SLA hoặc khi estimated completion vượt deadline.

### Escalation

Khi task quá hạn, hệ thống có thể gửi reminder, chuyển assignee hoặc tạo incident. Escalation event cần được ghi trong history.

### SLA outcome

SLA có thể đạt, vi phạm hoặc chưa xác định do dữ liệu thiếu. Không nên suy ra SLA breach chỉ từ việc process đang chạy lâu nếu chưa xét calendar, pause và policy.

## 26. Progress và workflow orchestration

Progress tracking là một phần của orchestration runtime nhưng không nên thay thế scheduler hoặc execution state machine.

### Scheduler

Scheduler quyết định step nào đủ điều kiện chạy và worker nào nhận việc. Tracking ghi nhận ready/start/complete và thời gian chờ.

### Worker

Worker thực thi task và gửi result/event. Worker cần xác thực execution token, step identity và attempt để event được gắn đúng instance.

### Queue

Queue time có thể là bottleneck dù task chưa bắt đầu. Tracking nên tách `READY` hoặc `QUEUED` khỏi `RUNNING`.

### External service

Step gọi service ngoài có thể chờ response. Ghi external correlation ID giúp liên kết progress với hệ thống downstream.

### State machine

Runtime state machine xác định transition hợp lệ. Progress projector tiêu thụ transition hoặc event để tạo summary. Không nên cho UI tự suy luận status từ tên step hoặc thứ tự trong DSL.

## 27. Quan sát tiến trình và observability

Progress tracking tập trung vào trạng thái nghiệp vụ của instance. Observability cung cấp dữ liệu kỹ thuật để hiểu hiệu năng và lỗi của runtime.

### Logs

Log ghi sự kiện chi tiết, error và context. Cần có `instanceId`, `stepExecutionId`, `attemptId` và `correlationId` để truy vấn.

### Metrics

Các metric hữu ích:

- Số instance theo status.
- Số step đang chạy hoặc chờ.
- Throughput instance hoàn tất mỗi phút/giờ.
- Queue depth và queue wait time.
- Step execution duration theo loại.
- Retry rate và failure rate.
- Human task age và overdue count.
- SLA compliance rate.
- Progress update lag.
- Event processing lag.

### Distributed tracing

Trace có thể nối process engine với service call, database và worker. Span nên chứa instance/step identity nhưng tránh đưa dữ liệu cá nhân hoặc payload nhạy cảm vào attribute.

### Business observability

Metrics nghiệp vụ có thể gồm số đơn hàng đã xử lý, số hồ sơ đang chờ duyệt hoặc tỷ lệ process hoàn tất đúng hạn. Cần tách khỏi metric runtime như CPU, latency và queue depth.

### Stuck detection

Một instance có thể bị stuck nếu không có event tiến triển trong thời gian bất thường, dù status vẫn `RUNNING`. Detection có thể dựa trên last progress event, heartbeat, expected duration và current wait reason.

### Heartbeat

Worker hoặc long-running activity có thể gửi heartbeat để chứng minh còn hoạt động. Heartbeat không đồng nghĩa progress tăng; nó chỉ cho biết worker vẫn sống hoặc còn kiểm soát execution.

## 28. Security và quyền truy cập progress data

Process progress có thể tiết lộ thông tin khách hàng, trạng thái giao dịch, người phê duyệt, dữ liệu nội bộ hoặc logic nghiệp vụ.

### Instance-level authorization

Caller chỉ được xem instance thuộc tenant, project hoặc phạm vi được cấp quyền. Biết instance ID không đủ để có quyền đọc.

### Field-level visibility

Người dùng có thể được xem status nhưng không được xem input payload, secret, internal error hoặc tên người xử lý. API cần áp dụng field-level policy ở server.

### Control permissions

Quyền đọc progress khác quyền pause, resume, cancel, retry hoặc reassign task. Control operation cần authorization riêng và audit.

### Sensitive payload

Không nên lưu toàn bộ process variable vào event log nếu chỉ cần reference hoặc summary. Cần redaction, encryption, access log và retention policy.

### Multi-tenant isolation

Partition key, event query, cache và subscription phải bảo đảm dữ liệu instance của tenant này không lẫn sang tenant khác.

### Audit

Ghi nhận ai xem hoặc điều khiển process nếu policy yêu cầu, nhất là với workflow có dữ liệu nhạy cảm hoặc phê duyệt quan trọng.

## 29. Tính nhất quán và xử lý race condition

Nhiều worker có thể cập nhật các step cùng lúc. Progress projection cần tránh mất update hoặc tính trùng.

### Optimistic concurrency

Mỗi instance có state version. Update chỉ được áp dụng nếu version hiện tại khớp expected version; nếu không, transaction cần reload và xử lý lại.

### Event sequence

Sequence number theo instance hoặc partition giúp phát hiện event đến sai thứ tự hoặc bị thiếu. Nếu event đến ngoài thứ tự, projector có thể buffer hoặc rebuild phần trạng thái liên quan.

### Idempotent projection

Projector cần lưu event ID đã xử lý hoặc dùng offset/transaction phù hợp để duplicate không làm tăng completed count lần nữa.

### Concurrent branches

Hai branch hoàn tất gần như đồng thời có thể cùng cập nhật parent progress. Cần atomic update hoặc projection tuần tự theo event stream.

### Read consistency

Dashboard có thể đọc projection eventual-consistent. UI nên hiển thị thời điểm cập nhật hoặc state version để người dùng biết snapshot có thể trễ so với engine.

### Terminal state race

Một event `ProcessCompleted` có thể cạnh tranh với `ProcessCancelled` hoặc timeout. State machine cần quy định transition thắng theo sequence, compare-and-set hoặc cancellation policy; không thể để trạng thái cuối phụ thuộc race ngẫu nhiên.

## 30. API query và phân trang

Process có thể có hàng nghìn step execution hoặc hàng triệu event. API cần hỗ trợ truy vấn theo cấp và pagination.

### List instances

Filter theo status, definition, owner, created time, tenant và SLA state. Cần giới hạn page size và hỗ trợ cursor.

### Get instance summary

Trả trạng thái tổng, progress summary, current step và timestamps.

### Get step tree

Trả step/scope hierarchy. Có thể hỗ trợ `depth`, `includeBranches` hoặc `includeTasks` để giới hạn payload.

### Get event timeline

Trả event theo sequence hoặc time range, với cursor để lấy trang tiếp theo.

### Subscribe

Subscription có thể theo instance ID hoặc filter. Cần authorization khi tạo subscription và khi phát từng event.

### State version và ETag

Client có thể gửi `If-None-Match` hoặc expected version để giảm tải khi state không đổi. API cần bảo đảm version đại diện đúng snapshot trả về.

## 31. Ví dụ DSL khai báo tracking policy

Một process DSL có thể cho phép khai báo milestone, weight, visibility và SLA.

~~~text
process FulfillOrder(order: Order) {
    progress {
        mode = weighted;
        expose = [status, milestones, currentStep, percentage];
        milestone OrderValidated after ValidateOrder;
        milestone PaymentCaptured after CapturePayment;
        milestone ShipmentCreated after CreateShipment;
        milestone Delivered after ConfirmDelivery;
    }

    step ValidateOrder weight 1 {
        validate order;
    }

    step ReserveInventory weight 2 {
        reserveInventory(order);
    }

    step CapturePayment weight 3 {
        capturePayment(order);
    }

    step CreateShipment weight 3 {
        createShipment(order);
    }

    humanTask ConfirmDelivery weight 1 {
        assign to order.owner;
        due within 48 hours;
    }
}
~~~

Đây là cú pháp minh họa, không phải cú pháp của một engine cụ thể. Một implementation cần định nghĩa:

- `weight` có áp dụng cho step bị skip không.
- Milestone có thể bị invalidate hay không.
- Human task bắt đầu tính progress khi ready, assigned hay completed.
- Percentage có tính step đang chạy một phần không.
- `expose` kiểm soát dữ liệu hiển thị cho API hay chỉ là metadata UI.
- SLA tính theo calendar nào và có pause khi waiting không.

### Tách progress policy khỏi execution logic

Progress policy nên mô tả cách quan sát và tổng hợp. Không nên để một phép tính phần trăm thay đổi semantics điều phối của process. Step vẫn được scheduler chạy theo dependency và condition; progress projector chỉ đọc các sự kiện runtime để tính summary.

## 32. Ví dụ tính progress bằng dữ liệu runtime

Giả sử process có các work unit:

| Step | Weight | Status | Completion fraction |
|---|---:|---|---:|
| ValidateOrder | 1 | COMPLETED | 1.0 |
| ReserveInventory | 2 | COMPLETED | 1.0 |
| CapturePayment | 3 | RUNNING | 0.5 |
| CreateShipment | 3 | PENDING | 0.0 |
| ConfirmDelivery | 1 | PENDING | 0.0 |

Tổng weight là 10. Weighted progress:

\[
P = \frac{1 + 2 + 3(0.5)}{10} \times 100 = 45\%
\]

Nếu step đang chạy không có completion fraction đáng tin cậy, có thể tính theo trạng thái nhị phân: chỉ completed step được tính. Khi đó progress là 30%. Hai con số đều có thể đúng theo policy khác nhau; UI phải cho biết phương pháp đang dùng.

### Completion fraction

Một step có thể cung cấp progress nội bộ nếu bản thân nó xử lý nhiều work units. Ví dụ import 500 record, đã xử lý 250 record thì step có completion fraction 0.5. Runtime cần xác thực fraction nằm trong miền hợp lệ và xác định denominator có ổn định không.

### Không cộng progress lồng nhau hai lần

Nếu step `ImportData` có weight 5 và subprocess con gồm các task có tổng weight 5, parent không được tính cả step 5 lẫn child 5 như hai phần việc độc lập. Có thể dùng child progress để xác định completion fraction của parent step.

## 33. Java: mô hình hóa progress snapshot

Một implementation Java có thể biểu diễn trạng thái step và policy tiến độ riêng.

~~~java
enum ExecutionStatus {
    PENDING,
    READY,
    RUNNING,
    WAITING,
    RETRYING,
    COMPLETED,
    FAILED,
    SKIPPED,
    CANCELLED
}

record StepProgress(
    String stepExecutionId,
    String stepDefinitionId,
    ExecutionStatus status,
    double weight,
    double completionFraction
) {}

record ProgressSnapshot(
    String instanceId,
    String definitionVersion,
    double completedWeight,
    double totalWeight,
    Double percentage,
    long stateVersion
) {}
~~~

`percentage` dùng `Double` nullable để biểu diễn indeterminate progress. Trong API production có thể dùng decimal hoặc integer basis points để kiểm soát rounding và tránh floating-point artifacts.

### Tính weighted progress

~~~java
static double weightedProgress(List<StepProgress> steps) {
    double total = 0.0;
    double completed = 0.0;

    for (StepProgress step : steps) {
        if (step.status() == ExecutionStatus.SKIPPED) {
            continue; // chỉ hợp lệ nếu policy loại skipped khỏi denominator
        }

        double weight = step.weight();
        double fraction = Math.max(0.0,
            Math.min(1.0, step.completionFraction()));

        total += weight;
        completed += weight * fraction;
    }

    if (total == 0.0) {
        return 0.0;
    }

    return completed / total * 100.0;
}
~~~

Đây là ví dụ minh họa. Quy tắc loại `SKIPPED`, xử lý failed/cancelled, branch không được chọn và denominator động phải đến từ progress policy của process, không nên bị hard-code tùy tiện trong hàm tổng quát.

### Cập nhật snapshot an toàn

Progress projector nên xử lý event theo ID và sequence, rồi ghi state cùng version trong một transaction hoặc một cơ chế bảo đảm tương đương. Nếu event bị duplicate, completed weight không được cộng thêm lần nữa.

## 34. Kiểm thử progress tracking

Progress tracking cần được kiểm thử ở cả state machine, event processing, phép tính và API.

### State transition tests

Kiểm tra các chuyển trạng thái hợp lệ và từ chối chuyển trạng thái không hợp lệ. Ví dụ `COMPLETED -> RUNNING` không nên xảy ra nếu definition không hỗ trợ reopen.

### Sequential process tests

Xác nhận step hoàn tất theo thứ tự, progress tăng theo policy và instance chỉ completed khi mọi điều kiện terminal được thỏa.

### Branch tests

Kiểm tra nhánh được chọn, nhánh không được chọn, join all, join any, quorum và cancellation.

### Loop tests

Kiểm tra iteration identity, dynamic collection, retry một item và denominator thay đổi.

### Parallel concurrency tests

Cho nhiều branch hoàn tất đồng thời, xác nhận parent status và progress không mất update hoặc tính trùng.

### Human task tests

Kiểm tra assignment, claim, reassignment, completion, expiry, escalation và quyền xem.

### Event idempotency tests

Gửi cùng event nhiều lần và xác nhận projection chỉ áp dụng một lần.

### Recovery tests

Restart engine giữa step, sau side effect nhưng trước checkpoint, trong retry hoặc khi chờ callback. Xác nhận process tiếp tục đúng và progress không lùi sai.

### Progress formula tests

Kiểm tra weight, skipped, failed, indeterminate, partial step, branch và rounding. So sánh snapshot với expected result theo policy.

### API and authorization tests

Kiểm tra pagination, cursor, ETag, state version, tenant isolation và field-level visibility.

## 35. Những lỗi thiết kế thường gặp

**Dùng số step hoàn tất chia tổng step cho mọi process.** Công thức này sai với branch, loop, optional step và subprocess. Cần progress policy hiểu cấu trúc runtime.

**Coi thời gian đã trôi qua là phần trăm hoàn thành.** Process có waiting time và step duration khác nhau; elapsed time không tự phản ánh work done.

**Tính cả mọi nhánh không được chọn vào mẫu số.** Instance có thể không bao giờ đạt 100%. Cần trạng thái `NOT_APPLICABLE` hoặc branch-aware denominator.

**Đếm retry như công việc mới.** Một step retry nhiều lần vẫn là một logical work unit. Attempts phải được theo dõi riêng.

**Coi skipped là failed.** Step bị bỏ qua hợp lệ theo điều kiện không phải lỗi.

**Đánh dấu parent hoàn tất khi worker trả về.** Cần chờ commit, join condition hoặc postcondition cần thiết.

**Không gắn event với instance/step version.** Event trễ hoặc sai instance có thể cập nhật nhầm tiến trình.

**Không chống duplicate event.** Message redelivery có thể làm progress tăng nhiều lần.

**Lưu percentage nhưng không lưu policy.** Khi công thức thay đổi, số liệu lịch sử không thể giải thích.

**Để progress giảm mà không có giải thích.** Denominator động hoặc rollback có thể làm phần trăm giảm; cần hiển thị nguyên nhân và policy.

**Đưa toàn bộ event vào một API response.** Instance lớn có thể tạo payload khổng lồ. Cần summary, detail và timeline pagination.

**Nhầm waiting với stuck.** Chờ callback hoặc phê duyệt có thể là trạng thái hợp lệ; cần deadline và heartbeat để phân biệt.

**Không phân biệt process status với notification delivery.** Email thất bại không có nghĩa process thất bại.

**Cho phép mọi người điều khiển instance chỉ vì xem được progress.** Read permission và control permission phải tách riêng.

## 36. Quy trình triển khai progress tracking cho process DSL

Một quy trình thực tế có thể gồm:

1. **Xác định người xem:** người khởi tạo, người xử lý, operator, quản lý và auditor.
2. **Định nghĩa execution identity:** process instance, scope, step execution, task và attempt ID.
3. **Định nghĩa state machine:** trạng thái instance/step/task, transition và terminal state.
4. **Thiết kế event contract:** event type, sequence, timestamp, actor, correlation và idempotency.
5. **Xác định progress semantics:** step count, weighted, milestone, work-unit hoặc indeterminate.
6. **Xử lý cấu trúc flow:** branch, loop, parallel join, subprocess, skip và compensation.
7. **Thiết kế human task:** assignment, claim, due date, escalation và completion.
8. **Thiết kế persistence:** event store, snapshot, checkpoint, projection và recovery.
9. **Xây progress API:** summary, step detail, timeline, subscription và state version.
10. **Thiết kế UI:** progress bar, step list, graph, milestone, timeline và task inbox.
11. **Tích hợp SLA/notification:** business calendar, deadline, escalation và delivery tracking.
12. **Thiết kế observability:** logs, metrics, traces, heartbeat và stuck detection.
13. **Thiết kế security:** tenant isolation, field visibility, read/control permission và retention.
14. **Kiểm thử:** concurrency, duplicate event, branch, retry, recovery, calculation và API.

## 37. Checklist cho một process instance đang chạy

Khi xem hoặc điều tra một instance, cần có thể xác định:

- Instance thuộc definition và version nào?
- Status hiện tại là gì và transition gần nhất xảy ra khi nào?
- Step/scope nào đang chạy, chờ, retry hoặc lỗi?
- Có branch song song nào chưa join không?
- Có step bị skip hoặc không áp dụng không?
- Human task đang được giao cho ai và deadline nào?
- Event hoặc callback nào đang được chờ?
- Progress percentage được tính theo policy nào?
- Tổng work units có cố định hay có thể thay đổi?
- Progress snapshot được cập nhật đến sequence nào?
- Có retry, compensation hoặc timeout nào đã xảy ra?
- Checkpoint mới nhất có đủ để phục hồi không?
- Instance có heartbeat hoặc event tiến triển gần đây không?
- SLA còn bao lâu hoặc đã vi phạm chưa?
- Người xem có quyền truy cập dữ liệu và thao tác điều khiển nào?
- Có thể truy vết từ summary đến step, event và log tương ứng không?

## 38. Kết quả cần có sau khi thiết kế theo dõi tiến trình

Một cơ chế progress tracking hoàn chỉnh cho process DSL thường cung cấp:

- **Execution identity model:** definition/version, instance, scope, step, task và attempt identity.
- **State machine:** lifecycle của process, step, branch và human task.
- **Event contract:** event ID, sequence, timestamp, actor, causality và idempotency.
- **Progress policy:** count, weighted progress, work-unit progress, milestones và indeterminate mode.
- **Flow semantics:** branch, loop, parallel join, subprocess, skip, retry và compensation.
- **Checkpoint/recovery model:** snapshot, event replay, state version và definition version pinning.
- **Persistence/projection:** event store, current-state view, timeline và rebuild strategy.
- **API contract:** summary, detail, timeline, subscription, pagination và conditional read.
- **User experience:** progress bar, step list, graph, milestone, task inbox và notification.
- **SLA model:** deadline, business calendar, pause, warning và escalation.
- **Observability:** logs, metrics, distributed trace, heartbeat và stuck detection.
- **Security/governance:** authorization, tenant isolation, redaction, audit và retention.
- **Test suite:** state transition, concurrency, duplicate event, branch, loop, recovery, formula và API security.

Theo dõi tiến trình giúp biến một process instance đang chạy thành trạng thái có thể quan sát, giải thích và điều phối. Thiết kế tốt cần tách lifecycle status khỏi percentage, định danh rõ instance/step/task/attempt, ghi event có thứ tự và xử lý duplicate, đồng thời định nghĩa progress policy phù hợp với branch, loop, parallel flow và human task. Checkpoint cùng persistence bảo đảm tiến trình có thể tiếp tục sau sự cố; API và UI trình bày summary, milestone, timeline và bước đang chờ theo đúng quyền. Khi progress được tính từ dữ liệu runtime có version và evidence, thay vì suy đoán từ thời gian hoặc số dòng trong DSL, người dùng có thể hiểu chính xác quy trình đã đạt đến đâu và hệ thống vận hành có thể phát hiện sớm điểm nghẽn, lỗi và nguy cơ vi phạm SLA.

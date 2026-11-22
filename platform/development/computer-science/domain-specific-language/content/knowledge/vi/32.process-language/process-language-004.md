# Tác vụ tự động

## 1. Tác vụ tự động trong DSL quy trình là gì?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) dùng để mô tả quy trình, **tác vụ tự động (automated task)** là một đơn vị công việc được hệ thống thực hiện theo định nghĩa và điều kiện kích hoạt đã khai báo. Tác vụ có thể chạy khi quy trình đến một bước, khi một sự kiện xuất hiện, theo lịch, khi dữ liệu thay đổi hoặc khi một tác vụ phụ thuộc hoàn tất.

Ví dụ, quy trình xử lý đơn hàng:

~~~text
process "Order fulfillment"
  task ValidateOrder
  task ReserveInventory
  task ChargePayment
  task SendConfirmation
~~~

Người thiết kế mô tả công việc cần làm; runtime chịu trách nhiệm lập lịch, cấp dữ liệu, thực thi, theo dõi trạng thái và xử lý lỗi.

Một tác vụ tự động có thể kiểm tra hoặc chuyển đổi dữ liệu, gọi service/API, tạo tài liệu, gửi thông báo, cập nhật trạng thái nghiệp vụ, chạy chương trình được cho phép, đưa message vào queue hoặc khởi chạy một quy trình con.

Tác vụ tự động khác với thao tác thủ công của người dùng. Một bước chờ phê duyệt có thể cần người dùng thực hiện, trong khi tác vụ gửi email sau khi phê duyệt có thể chạy tự động.

Một DSL quy trình tốt cần mô tả rõ tác vụ làm gì, khi nào chạy, nhận dữ liệu nào, tạo kết quả gì, phụ thuộc vào đâu và xử lý thế nào khi thành công, thất bại hoặc bị hủy.

## 2. Phân biệt task, process, workflow và job

Các thuật ngữ thường được dùng gần nhau nhưng có phạm vi khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Task | Một đơn vị công việc | Kiểm tra địa chỉ giao hàng |
| Process | Quy trình nghiệp vụ gồm nhiều bước | Xử lý đơn hàng |
| Workflow | Mô tả luồng và quan hệ điều khiển | Validate → Reserve → Charge |
| Job | Một lần chạy hoặc yêu cầu thực thi cụ thể | Chạy báo cáo doanh thu ngày 15 |
| Worker | Thành phần thực hiện task/job | Worker xử lý message trong queue |
| Scheduler | Thành phần quyết định khi nào công việc chạy | Đồng bộ dữ liệu mỗi giờ |

Một task definition có thể được dùng nhiều lần. Mỗi lần thực thi tạo một task instance hoặc job instance với input, trạng thái, thời điểm và kết quả riêng.

~~~text
Task definition: GenerateInvoice

Instance A:
  orderId = ORD-100
  status = COMPLETED

Instance B:
  orderId = ORD-101
  status = RUNNING
~~~

Không nên đồng nhất định nghĩa tác vụ với một lần chạy cụ thể. Việc tách hai khái niệm giúp theo dõi lịch sử, retry và chạy song song.

## 3. Mô hình tổng quát của một automated task

Một task definition có thể gồm:

~~~text
task "GenerateInvoice" {
  input:
    orderId: OrderId

  trigger:
    on process.step("PaymentConfirmed").completed

  execute:
    invoiceService.generate(orderId)

  output:
    invoiceId: InvoiceId

  timeout: 30 seconds
  retry:
    maximumAttempts: 3
}
~~~

Đây là cú pháp minh họa. Các khái niệm chính gồm:

- **Identity:** ID và tên ổn định.
- **Input:** dữ liệu task cần.
- **Trigger:** sự kiện hoặc điều kiện khởi chạy.
- **Execution:** handler hoặc action được gọi.
- **Output:** kết quả task tạo ra.
- **Dependencies:** các task phải hoàn tất trước.
- **Policy:** timeout, retry, concurrency và failure behavior.
- **Lifecycle:** trạng thái và thời điểm bắt đầu/kết thúc.
- **Observability:** log, metric, trace và audit.

Một task definition nên khai báo đủ thông tin để runtime thực thi mà không phải suy đoán quy tắc nghiệp vụ quan trọng.

## 4. Định danh và mô tả tác vụ

### 4.1 Task ID

Task ID là định danh ổn định dùng trong dependency, log, history và quản trị.

~~~text
task id: order.generate-invoice
name: "Generate invoice"
~~~

ID nên duy nhất trong phạm vi đã định nghĩa, chẳng hạn một process package hoặc namespace. Không nên dùng label hiển thị làm khóa nếu label có thể đổi hoặc được dịch.

### 4.2 Description, owner và version

Description giải thích mục đích, điều kiện nghiệp vụ và kết quả mong đợi. Metadata có thể gồm nhóm nghiệp vụ, team sở hữu, ngày hiệu lực, version, nguồn quản lý và nhãn kiểm toán.

### 4.3 Task type

Có thể phân loại:

- Automated task: chạy tự động.
- User task: chờ người dùng thực hiện.
- Service task: gọi dịch vụ.
- Script task: chạy đoạn mã được kiểm soát.
- Timer task: chờ đến thời điểm hoặc khoảng thời gian.
- Event task: phản ứng với event.
- Subprocess task: khởi chạy quy trình con.

Tên loại phụ thuộc DSL và engine. Cần định nghĩa semantics thay vì chỉ dựa vào label.

## 5. Trigger và điều kiện khởi chạy

Trigger xác định khi nào một task đủ điều kiện bắt đầu.

### 5.1 Theo luồng quy trình

~~~text
step "PaymentConfirmed"
  on complete:
    run GenerateInvoice
~~~

Đây là cách phổ biến khi tác vụ là một phần của luồng tuần tự.

### 5.2 Theo sự kiện

~~~text
task "UpdateCustomerProfile"
  trigger:
    on event CustomerAddressChanged
~~~

Event có thể đến từ process, message broker hoặc hệ thống bên ngoài. Cần xác định event identity, schema và cách xử lý event trùng.

### 5.3 Theo lịch

~~~text
task "DailyReconciliation"
  trigger:
    every day at 02:00
    timezone: "Asia/Ho_Chi_Minh"
~~~

Lịch cần quy định timezone, daylight saving time nếu có, cách xử lý thời điểm bị bỏ qua hoặc lặp lại và hành vi khi scheduler ngừng hoạt động.

### 5.4 Theo điều kiện dữ liệu

~~~text
task "EscalateOverdueInvoice"
  trigger:
    when invoice.status == OVERDUE
      and invoice.daysPastDue >= 7
~~~

Điều kiện có thể được kiểm tra khi dữ liệu thay đổi, theo lịch polling hoặc bởi rule engine. Cần xác định thời điểm đánh giá và tránh kích hoạt lặp vô hạn.

### 5.5 Theo completion của task khác

~~~text
task "PublishReport"
  trigger:
    after GenerateReport.completed
~~~

Trigger này tạo dependency trực tiếp. Nếu task trước thất bại hoặc bị hủy, task sau cần chính sách rõ.

### 5.6 Trigger kết hợp

~~~text
trigger:
  on event OrderSubmitted
  when order.total > 0
~~~

DSL phải xác định điều kiện được đánh giá trên payload event hay trạng thái hiện tại, và event có được lưu chờ nếu điều kiện chưa đúng hay không.

## 6. Input và output của task

Task cần hợp đồng dữ liệu rõ để tránh phụ thuộc vào biến toàn cục hoặc trạng thái ngầm.

### 6.1 Input declaration

~~~text
task "SendReceipt"
  input:
    orderId: OrderId required
    locale: Locale optional default "vi-VN"
~~~

Input declaration nên xác định tên, kiểu, required/optional, default, ràng buộc miền, nguồn dữ liệu và quy tắc null/missing.

### 6.2 Typed input

Sử dụng kiểu miền như OrderId, Money, CustomerId hoặc Date thay vì truyền mọi thứ dưới dạng string. Typed input giúp kiểm tra sớm và tránh nhầm lẫn giữa các giá trị cùng biểu diễn.

### 6.3 Output declaration

~~~text
task "GenerateInvoice"
  output:
    invoiceId: InvoiceId
    artifactPath: Path
~~~

Output cần xác định kiểu, tính bắt buộc và cách lưu. Không nên trả về object lớn nếu các task sau chỉ cần một ID hoặc reference.

### 6.4 Output mapping

~~~text
on success:
  process.invoiceId = result.invoiceId
~~~

Mapping nên rõ ràng và kiểm tra kiểu. Tránh ghi đè field quan trọng bằng output không hợp lệ.

### 6.5 Immutable input snapshot

Một task nên nhận snapshot input nhất quán. Nếu dữ liệu nguồn thay đổi giữa lúc task đọc nhiều field, kết quả có thể trộn nhiều phiên bản. Có thể dùng version, transaction hoặc snapshot model để xác định trạng thái input.

### 6.6 Sensitive input

Password, token hoặc dữ liệu cá nhân cần được đánh dấu nhạy cảm. Không ghi chúng vào log, trace hoặc task history dưới dạng nguyên văn.

## 7. Dependency giữa các tác vụ

Một task có thể cần kết quả từ task khác.

~~~text
ValidateOrder
      |
      v
ReserveInventory
      |
      v
ChargePayment
      |
      v
GenerateInvoice
      |
      v
SendReceipt
~~~

Dependency xác định quan hệ cần hoàn tất trước khi task tiếp theo bắt đầu.

### 7.1 Dependency tuần tự

~~~text
task ChargePayment
  dependsOn: ReserveInventory
~~~

Task B chỉ chạy khi Task A đạt trạng thái được dependency policy chấp nhận, thường là thành công.

### 7.2 Dependency song song

~~~text
ValidateOrder
    |
    +----> CheckFraud
    |
    +----> CalculateShipping
~~~

Sau khi xác nhận đơn hàng, hai tác vụ độc lập có thể chạy song song.

### 7.3 Join

~~~text
task ConfirmOrder
  dependsOn:
    - CheckFraud
    - CalculateShipping
~~~

Engine cần định nghĩa điều kiện join: tất cả phải thành công, chỉ cần một kết quả, hay theo quorum.

### 7.4 Dependency graph

~~~text
      A
     / \
    B   C
     \ /
      D
~~~

Các task có thể được biểu diễn thành directed acyclic graph (DAG) nếu không cho phép vòng lặp. DAG giúp runtime tìm task có thể chạy đồng thời và phát hiện dependency cycle.

### 7.5 Dependency cycle

Nếu A phụ thuộc B và B phụ thuộc A, không task nào có thể bắt đầu. Compiler hoặc workflow validator nên phát hiện cycle trước khi triển khai, trừ khi DSL có semantics vòng lặp được khai báo rõ.

### 7.6 Dependency theo kết quả

~~~text
after CheckFraud:
  if result == CLEAR:
    run ChargePayment
  else:
    run ManualReview
~~~

Nên dùng outcome có kiểu hoặc enum thay vì so sánh chuỗi tự do.

## 8. Scheduling và hàng đợi thực thi

Scheduler quyết định task đủ điều kiện nào được gửi đến worker và khi nào.

### 8.1 Immediate và delayed execution

Task có thể được đưa vào queue ngay khi trigger thỏa mãn hoặc được lên lịch sau một khoảng thời gian:

~~~text
run Reminder after 24 hours
~~~

### 8.2 Cron-like schedule

Task chạy theo lịch định kỳ. Cần quản lý timezone, lịch nghỉ, thời điểm chạy bị bỏ lỡ và các lần chạy trùng.

### 8.3 Queue

~~~text
Trigger
  |
  v
Create task instance
  |
  v
Queue
  |
  v
Worker
  |
  v
Result
~~~

Queue tách producer tạo công việc khỏi worker thực hiện. Nó hỗ trợ buffering và phân phối tải, nhưng cần giới hạn kích thước, visibility timeout, dead-letter policy và backpressure.

### 8.4 Priority và fairness

Task có thể có priority để xử lý công việc quan trọng trước. Cần tie-breaker ổn định và cơ chế tránh task priority thấp bị đói tài nguyên.

### 8.5 Concurrency limit

Có thể giới hạn số instance đồng thời theo toàn hệ thống, process definition, tenant, task type hoặc resource key. Ví dụ, chỉ một task đồng bộ dữ liệu cho cùng một customer được chạy tại một thời điểm.

### 8.6 Worker pool

Worker pool giới hạn số thread hoặc process thực thi. Không nên tạo thread không giới hạn theo số task được enqueue.

## 9. Task state và lifecycle

Task instance có vòng đời riêng:

~~~text
CREATED
   |
   v
QUEUED
   |
   v
RUNNING
   |
   +------> SUCCEEDED
   |
   +------> FAILED
   |
   +------> CANCELLED
   |
   +------> TIMED_OUT
~~~

Một số engine còn có trạng thái RETRY_WAIT, PAUSED, SKIPPED hoặc COMPENSATING.

| Trạng thái | Ý nghĩa |
|---|---|
| CREATED | Instance đã được tạo |
| QUEUED | Đang chờ worker |
| RUNNING | Worker đang thực thi |
| RETRY_WAIT | Đang chờ lần thử tiếp theo |
| SUCCEEDED | Hoàn tất và output được chấp nhận |
| FAILED | Thất bại sau khi áp dụng retry policy |
| CANCELLED | Bị yêu cầu dừng |
| TIMED_OUT | Vượt thời hạn |
| COMPENSATING | Đang chạy hành động bù |

Các trạng thái kết thúc cần được xác định rõ. Một task đã SUCCEEDED không nên tự chuyển thành RUNNING lần nữa nếu không tạo attempt hoặc instance mới theo semantics.

## 10. Retry và backoff

Tác vụ tự động có thể thất bại vì mạng, service tạm thời không sẵn sàng, giới hạn rate hoặc lỗi hạ tầng.

~~~text
retry:
  maximumAttempts: 4
  initialDelay: 2 seconds
  backoff: exponential
  maximumDelay: 1 minute
~~~

### 10.1 Retryable và non-retryable errors

Có thể retry timeout tạm thời, HTTP 503, mất kết nối ngắn hạn hoặc rate limit nếu có retry-after phù hợp.

Thường không nên retry tự động input sai schema, thiếu quyền, resource không tồn tại vĩnh viễn hoặc business rule từ chối. Phân loại lỗi cần dựa trên contract của service.

### 10.2 Exponential backoff

Thời gian chờ có thể tăng theo số lần thử:

\[
d_n = \min(d_{\max}, d_0 \times 2^n)
\]

Trong đó d0 là delay ban đầu, n là số lần retry đã thực hiện và dmax là giới hạn.

### 10.3 Jitter

Thêm độ ngẫu nhiên có kiểm soát vào backoff giúp nhiều worker không cùng retry tại một thời điểm, tránh tạo tải đột biến.

### 10.4 Maximum attempts và retry budget

Cần định nghĩa maximumAttempts bao gồm lần chạy đầu tiên hay chỉ số lần retry. Một hệ thống cũng có thể giới hạn tổng số retry trong một khoảng thời gian hoặc theo service để tránh retry storm.

### 10.5 Retry và trạng thái

Mỗi attempt nên có số thứ tự, thời điểm, lỗi và thời gian chạy. Task instance chỉ chuyển sang FAILED cuối cùng khi policy đã hết cơ hội retry hoặc gặp lỗi không thể retry.

## 11. Idempotency và xử lý chạy lặp

Một task có thể được thực hiện nhiều lần do retry, message redelivery, worker crash hoặc người vận hành chạy lại.

**Idempotency** là tính chất mà việc thực hiện lại cùng một thao tác không tạo thêm tác động ngoài kết quả đã định.

Ví dụ:

- Đặt order.status = PAID có thể idempotent nếu kiểm tra trạng thái và version.
- Cộng thêm 100 vào balance thường không idempotent nếu chạy lặp.
- Gửi email có thể tạo nhiều email nếu không có deduplication.

### 11.1 Idempotency key

~~~text
key = processInstanceId + taskId + orderId
~~~

Service nhận request dùng key để nhận biết yêu cầu trùng.

### 11.2 Exactly-once và thực tế phân tán

Trong hệ thống phân tán, bảo đảm exactly-once end-to-end thường khó. Nhiều hệ thống dùng at-least-once delivery kết hợp idempotent handler và deduplication.

### 11.3 Deduplication store

Có thể lưu idempotency key cùng trạng thái xử lý và kết quả. Việc lưu key và side effect cần được phối hợp transaction nếu không muốn tạo khoảng trống giữa hai thao tác.

### 11.4 Payload conflict

Nếu cùng key nhưng payload khác nhau, service nên phát hiện conflict thay vì trả lại kết quả cũ một cách im lặng.

## 12. Timeout và cancellation

Timeout giới hạn thời gian một task được phép chạy:

~~~text
task "FetchExchangeRate"
  timeout: 5 seconds
~~~

Khi quá thời hạn, engine đánh dấu attempt timed out và có thể yêu cầu worker dừng. Task nên nhận cancellation token hoặc signal và kiểm tra tại các điểm phù hợp. Với I/O, dùng API có timeout hoặc cancellation thực sự.

Timeout ở client không chứng minh service bên ngoài chưa xử lý request. Nếu worker đã gửi request, retry vẫn cần idempotency.

Nếu process bị hủy, task con có thể nhận tín hiệu hủy theo policy. Một số tác vụ có thể được phép hoàn tất hoặc chạy compensation trước khi kết thúc process.

Timeout, cancellation do người dùng và lỗi nghiệp vụ là các outcome khác nhau. Cần giữ nguyên nguyên nhân trong task history.

## 13. Xử lý lỗi và failure policy

Một tác vụ có thể thất bại khi không thể khởi tạo handler, input không hợp lệ, dependency chưa sẵn sàng, service ngoài trả lỗi, worker mất kết nối, output sai schema hoặc lưu kết quả thất bại.

### 13.1 Fail fast

Dừng process ngay khi một task quan trọng thất bại. Phù hợp khi các bước sau không còn ý nghĩa nếu thiếu kết quả.

### 13.2 Continue on error

Một số task độc lập có thể thất bại nhưng process vẫn tiếp tục. Ví dụ gửi một bản thông báo phụ thất bại không nhất thiết phải hủy báo cáo chính.

### 13.3 Error route

~~~text
task "GenerateInvoice"
  on failure:
    run NotifyOperations
    route to InvoiceFailed
~~~

### 13.4 Dead-letter queue

Task hoặc message đã hết retry có thể được chuyển sang dead-letter queue để điều tra và xử lý thủ công.

### 13.5 Error classification

Nên phân loại transient infrastructure error, permanent infrastructure error, validation error, business rejection, authorization error, timeout, cancellation và internal defect.

Phân loại giúp quyết định retry, alert và compensation.

### 13.6 Error context

Task history nên giữ error code, message an toàn, attempt, timestamp, correlation ID và nguồn lỗi. Không ghi secret hoặc payload nhạy cảm không cần thiết.

## 14. Compensation và saga

Một quy trình nhiều bước có thể đã tạo side effect trước khi bước sau thất bại.

~~~text
ReserveInventory
       |
       v
ChargePayment
       |
       v
CreateShipment
~~~

Nếu CreateShipment thất bại sau khi đã charge payment, hệ thống có thể cần refund payment và release inventory.

### 14.1 Compensation task

~~~text
task "ChargePayment"
  compensate:
    run RefundPayment
~~~

Compensation là hành động nghiệp vụ bù, không nhất thiết khôi phục chính xác trạng thái trước đó. Refund có thể cần phí, thời gian xử lý hoặc trạng thái riêng.

### 14.2 Saga

Saga là mẫu phối hợp một quy trình phân tán gồm nhiều local transaction và hành động bù tương ứng.

~~~text
ReserveInventory
       |
       v
ChargePayment
       |
       v
CreateShipment
       |
       +---- failure
                |
                v
          RefundPayment
                |
                v
          ReleaseInventory
~~~

Thông thường, compensation được thực hiện theo thứ tự ngược với các bước đã thành công, nhưng quy tắc cụ thể phụ thuộc nghiệp vụ.

Compensation cũng có thể thất bại. Cần retry, trạng thái chờ xử lý, cảnh báo và quy trình can thiệp thủ công.

Rollback trong một transaction cục bộ có thể hoàn tác thay đổi chưa commit. Compensation trong saga là một tác vụ mới, có thể có tác động riêng và không bảo đảm đưa thế giới về trạng thái cũ tuyệt đối.

## 15. Concurrency và đồng bộ tài nguyên

Task có thể chạy đồng thời nếu không có dependency hoặc xung đột tài nguyên.

~~~text
Start process
    |
    +----> CheckCredit
    |
    +----> ValidateAddress
    |
    +----> CalculateShipping
              |
              v
           Join all
              |
              v
          ConfirmOrder
~~~

Chạy song song giảm thời gian tổng thể khi các task độc lập.

### 15.1 Race condition

Hai task cùng cập nhật một field có thể ghi đè kết quả của nhau. Cần xác định ownership, thứ tự hoặc cơ chế đồng bộ.

### 15.2 Lock và resource key

~~~text
concurrency:
  key: order.id
  maximum: 1
~~~

Lock cần timeout, lease hoặc cơ chế fencing để tránh lock bị giữ mãi khi worker chết.

### 15.3 Optimistic concurrency

~~~sql
UPDATE orders
SET status = 'PAID', version = version + 1
WHERE id = :id AND version = :expectedVersion
~~~

Nếu không có dòng nào được cập nhật, dữ liệu đã thay đổi và task cần đọc lại hoặc xử lý conflict.

### 15.4 Parallelism và thứ tự kết quả

Nếu output tổng hợp từ nhiều task, cần quy định thứ tự hoặc cách merge để kết quả deterministic. Không nên dựa vào thời điểm worker hoàn tất.

### 15.5 Giới hạn concurrency

Giới hạn đồng thời theo tenant hoặc service giúp tránh một tenant chiếm toàn bộ worker hoặc làm quá tải dependency ngoài.

## 16. Lập lịch định kỳ và xử lý thời gian

~~~text
task "DailySummary"
  schedule:
    cron: "0 0 2 * * *"
    timezone: "Asia/Ho_Chi_Minh"
~~~

### 16.1 Timezone và daylight saving time

Không nên dùng timezone mặc định của máy làm semantics ngầm. Ở vùng có daylight saving time, một thời điểm địa phương có thể bị bỏ qua hoặc xuất hiện hai lần. Scheduler cần quy định chạy, bỏ qua hay chọn một occurrence.

### 16.2 Missed execution

Nếu scheduler ngừng hoạt động, khi khởi động lại có thể chạy bù tất cả lần bị lỡ, chỉ chạy lần gần nhất, bỏ qua các lần cũ hoặc tạo một task tổng hợp.

### 16.3 Overlapping runs

Nếu lần chạy trước chưa hoàn tất khi lịch tiếp theo đến, policy có thể là:

- Allow overlap.
- Skip new run.
- Queue new run.
- Cancel previous run.
- Replace with latest.

Chính sách phụ thuộc tính chất tác vụ và khả năng idempotency.

### 16.4 Clock source

Với timeout và lịch quan trọng, dùng clock phù hợp và tránh giả định đồng hồ máy luôn chính xác. Có thể cần đồng bộ thời gian và lưu timestamp UTC cùng timezone nghiệp vụ.

## 17. Event-driven task và message handling

~~~text
on event PaymentSettled
  run GenerateReceipt
~~~

### 17.1 Event schema

Event nên có event ID, event type, timestamp, correlation ID, schema version và payload.

### 17.2 At-least-once delivery

Message broker có thể gửi lại event khi consumer không xác nhận thành công. Handler cần idempotency hoặc deduplication.

### 17.3 Ordering

Event có thể đến sai thứ tự hoặc trễ. Nếu thứ tự quan trọng, cần sequence number, aggregate version hoặc partition key.

### 17.4 Poison message

Một event luôn gây lỗi có thể được retry vô hạn. Cần retry limit và dead-letter handling.

### 17.5 Outbox pattern

Khi cập nhật database và phát event, outbox pattern giúp ghi thay đổi nghiệp vụ và event vào cùng transaction cục bộ, sau đó publisher gửi event. Cách này giảm nguy cơ dữ liệu đã commit nhưng event không được phát.

### 17.6 Event replay

Replay event có thể tái tạo state hoặc chạy lại task. Cần version, idempotency và phân biệt replay với event mới.

## 18. Task con và subprocess

~~~text
task "OnboardCustomer"
  execute:
    start process CustomerOnboarding
      input customerId = current.customerId
~~~

### 18.1 Input và output mapping

Process con cần nhận input tường minh. Không nên phụ thuộc vào toàn bộ context của process cha nếu không có hợp đồng. Kết quả process con có thể được trả về task cha qua output schema.

### 18.2 Lifecycle relation

Cần xác định process cha có chờ process con hay không, có thể tiếp tục khi child đang chạy không và child có bị hủy khi parent dừng không.

### 18.3 Correlation và fan-out/fan-in

Lưu parent process ID, child process ID và correlation ID để theo dõi toàn bộ chuỗi. Một task có thể tạo nhiều child tasks cho từng item rồi tổng hợp kết quả; cần giới hạn số child và định nghĩa hành vi khi một phần child thất bại.

## 19. Task trong DSL và runtime handler

DSL thường mô tả task bằng một tên hoặc capability; runtime ánh xạ nó đến implementation.

~~~text
task "GenerateInvoice"
  handler: invoice.generate
  input:
    orderId: OrderId
~~~

Registry có thể ánh xạ invoice.generate đến InvoiceGenerationHandler.

### 19.1 Tách định nghĩa và implementation

DSL mô tả hợp đồng nghiệp vụ. Handler triển khai chi tiết bằng Java, service hoặc adapter.

### 19.2 Handler contract

~~~java
public interface TaskHandler<I, O> {
    TaskDescriptor descriptor();

    O execute(I input, TaskContext context)
        throws TaskExecutionException;
}
~~~

TaskContext có thể cung cấp cancellation token, logger và correlation ID, configuration snapshot, resource resolver, deadline, progress reporter và capability được cấp.

### 19.3 Handler registration

Handler có thể được đăng ký tường minh hoặc phát hiện qua plugin/provider. Cần kiểm tra task ID, version và capability trước khi chạy.

### 19.4 Không cho DSL gọi class tùy ý

Không nên cho file quy trình chỉ định một class name bất kỳ rồi phản chiếu và thực thi. Dùng registry hoặc allowlist để kiểm soát implementation có thể được gọi.

### 19.5 Handler version

Một process instance dài hạn có thể được tạo bằng handler version cũ. Runtime cần chính sách giữ version, migrate instance hoặc xử lý tương thích khi triển khai phiên bản mới.

## 20. Configuration của task

~~~text
task "SyncCustomer"
  handler: customer.sync
  timeout: 20 seconds
  retry:
    maximumAttempts: 3
  concurrency:
    maximum: 5
  input:
    source: customer
~~~

### 20.1 Static và dynamic settings

Handler name, schema hoặc resource type thường là cấu hình cần xác định khi deploy. Timeout hoặc retry có thể cho phép thay đổi động nếu runtime hỗ trợ.

### 20.2 Configuration validation

Compiler hoặc deployer nên kiểm tra handler tồn tại, input schema tương thích, retry count không âm, timeout hợp lệ, dependency hợp lệ, capability được cấp và output mapping đúng kiểu.

### 20.3 Secret references

Credential nên được tham chiếu qua secret provider, không nhúng trực tiếp trong task definition.

### 20.4 Effective configuration

Task history nên lưu các policy quan trọng đã áp dụng như timeout, retry policy và handler version để có thể giải thích một lần chạy.

## 21. Security và quyền thực thi

Automated task có thể chạy không cần người dùng đang tương tác. Vì vậy, quyền của task cần được kiểm soát chặt.

### 21.1 Least privilege và service identity

Mỗi handler chỉ nên có quyền cần thiết. Task gửi email không cần quyền đọc toàn bộ database. Task có thể chạy dưới service account hoặc identity riêng; cần phân biệt người khởi tạo process với identity dùng để thực thi task.

### 21.2 Authorization theo từng action

Kiểm tra quyền khi đăng ký process chưa đủ nếu task chạy sau nhiều giờ hoặc quyền đã thay đổi. Với thao tác nhạy cảm, có thể cần kiểm tra quyền lại khi thực thi.

### 21.3 Input validation

Không tin cậy payload event, file hoặc dữ liệu từ task trước. Validate schema và business constraints trước khi thực hiện side effect.

### 21.4 Script task

Nếu DSL cho phép script, cần sandbox hoặc runtime cô lập với giới hạn file, network, process, reflection và tài nguyên. Chạy script trong class loader riêng không tự tạo sandbox bảo mật.

### 21.5 Audit

Ghi nhận process và task instance ID, handler và version, initiator và service identity, thời điểm và outcome, resource đã tác động ở mức cần thiết và correlation ID. Không ghi credential hoặc dữ liệu nhạy cảm không cần thiết.

## 22. Observability: log, metric và trace

Task tự động thường chạy nền, không có người dùng nhìn trực tiếp. Hệ thống cần cung cấp cách quan sát.

### 22.1 Structured logging

Log nên có trường:

~~~text
processInstanceId
taskInstanceId
taskDefinitionId
attempt
tenantId
correlationId
status
duration
errorCode
~~~

Không cần log toàn bộ input/output nếu chúng chứa dữ liệu nhạy cảm.

### 22.2 Metrics

Các metric hữu ích gồm số task theo trạng thái, queue depth, task duration, success/failure rate, retry count, timeout count, cancellation count, worker utilization, dead-letter count và age của task đang chờ.

### 22.3 Distributed tracing

~~~text
Process: OrderFulfillment
   |
   +-- Task: ReserveInventory
   |      +-- HTTP: Inventory API
   |
   +-- Task: ChargePayment
          +-- HTTP: Payment API
~~~

### 22.4 Correlation ID và progress

Correlation ID giúp nối các log và trace thuộc cùng process hoặc business transaction. Khi tạo process con hoặc phát event, cần truyền correlation theo contract.

Task dài có thể báo progress theo phase hoặc số lượng item. Progress không thay thế trạng thái terminal; một task báo 90% rồi timeout vẫn phải được ghi nhận là timeout.

## 23. Versioning và thay đổi task definition

Task definition có thể thay đổi sau khi process instance đã được khởi chạy.

### 23.1 Definition version

Mỗi phiên bản process/task nên có identity hoặc version rõ. Task instance lưu version đã dùng khi được tạo.

### 23.2 Existing instances

Khi deploy process definition mới, các instance đang chạy có thể tiếp tục theo definition cũ, được migrate sang definition mới, chỉ migrate ở checkpoint an toàn hoặc bị dừng theo chính sách.

### 23.3 Handler compatibility

Handler mới cần đọc input của instance cũ nếu runtime cho phép instance cũ tiếp tục. Nếu không, cần giữ handler version cũ hoặc migrate dữ liệu.

### 23.4 Schema evolution và migration

Input/output schema có thể thêm field optional, nhưng xóa hoặc đổi kiểu field có thể phá compatibility. Migration nên có điều kiện áp dụng, version nguồn/đích, cách chuyển state, cách xử lý task đang RUNNING, kế hoạch rollback/compensation và audit record.

## 24. Testing automated tasks

Task cần được kiểm thử ở cấp handler và cấp process.

### 24.1 Unit test

Kiểm tra handler với input và dependency giả lập: input hợp lệ, input thiếu hoặc sai kiểu, kết quả thành công, service lỗi, timeout, cancellation và idempotency.

### 24.2 Contract test

Xác nhận handler đăng ký đúng ID, khai báo input/output schema, tuân thủ timeout và cancellation contract, không sửa input bất biến, trả output hợp lệ và xử lý lỗi theo quy ước.

### 24.3 Workflow integration test

Chạy process với nhiều task và xác nhận dependency/join đúng, task song song không xung đột, output mapping chính xác, error route được chọn đúng và compensation chạy khi cần.

### 24.4 Retry test

Giả lập lỗi transient ở các attempt đầu và thành công ở attempt sau. Kiểm tra số lần gọi, backoff và idempotency.

### 24.5 Crash recovery test

Dừng worker sau khi nhận task rồi khởi động lại. Xác nhận lease, queue và task state được phục hồi mà không tạo side effect trùng ngoài ý muốn.

### 24.6 Scheduler test

Kiểm tra timezone, missed execution, overlapping runs và daylight saving policy bằng clock giả lập thay vì chờ thời gian thật.

### 24.7 Load test

Kiểm tra queue, worker pool, concurrency limit, backpressure và hành vi khi dependency ngoài chậm.

## 25. Những sai lầm thường gặp

### Task không có input/output contract

Handler phụ thuộc vào biến toàn cục hoặc dữ liệu ngầm, gây khó kiểm thử và khó thay đổi.

**Cách khắc phục:** khai báo input/output có kiểu và mapping rõ.

### Retry mọi lỗi

Lỗi validation hoặc authorization thường không tự biến mất khi thử lại.

**Cách khắc phục:** phân loại lỗi và chỉ retry lỗi transient.

### Không có idempotency

Message redelivery hoặc worker crash có thể gửi email, trừ tiền hoặc tạo tài liệu nhiều lần.

**Cách khắc phục:** idempotency key, deduplication và transaction phù hợp.

### Timeout nhưng worker vẫn chạy

Đánh dấu task timeout không tự dừng code hoặc lời gọi I/O.

**Cách khắc phục:** truyền cancellation signal và dùng API hỗ trợ timeout/cancel.

### Chạy song song không xét shared state

Task có thể ghi đè dữ liệu hoặc đọc snapshot không nhất quán.

**Cách khắc phục:** phân tích dependency, resource key và concurrency policy.

### Không định nghĩa failure route

Process bị treo hoặc dừng ở trạng thái không rõ khi task thất bại.

**Cách khắc phục:** quy định retry, continue, fail, compensate và manual intervention.

### Coi compensation là rollback

Hành động bù có thể thất bại hoặc tạo tác động mới.

**Cách khắc phục:** mô hình hóa compensation như task riêng có trạng thái, retry và audit.

### Không lưu handler/definition version

Khó tái lập kết quả của process instance cũ sau khi deploy.

**Cách khắc phục:** lưu version và schema tương ứng trên từng instance.

### Thiếu observability

Task nền thất bại mà không có correlation ID hoặc trạng thái dễ tra cứu.

**Cách khắc phục:** structured logs, metrics, trace và task history.

## 26. Quy trình thiết kế tác vụ tự động

Khi thêm một task vào DSL quy trình, có thể thực hiện:

1. **Xác định mục tiêu:** task giải quyết công việc nghiệp vụ nào?
2. **Chọn trigger:** theo bước, event, lịch hay điều kiện dữ liệu?
3. **Định nghĩa identity:** ID ổn định, tên và version.
4. **Khai báo input/output:** kiểu, required, default và mapping.
5. **Xác định dependency:** tuần tự, song song, join hoặc process con.
6. **Chọn handler:** capability đã đăng ký và được cho phép.
7. **Định nghĩa policy:** timeout, retry, backoff và concurrency.
8. **Xác định idempotency:** xử lý chạy lặp và message redelivery.
9. **Thiết kế failure path:** fail, continue, error route hoặc compensation.
10. **Quản lý state:** lifecycle, attempt và terminal outcome.
11. **Kiểm soát quyền:** identity, capability và secret.
12. **Thiết kế observability:** log, metric, trace và progress.
13. **Xác định versioning:** definition, handler và schema.
14. **Viết test:** unit, contract, integration, crash recovery và load.

## 27. Ví dụ tổng hợp: tự động xử lý đơn hàng

Giả sử một DSL mô tả quy trình:

~~~text
process "OrderFulfillment" {
  input:
    orderId: OrderId

  task "ValidateOrder" {
    handler: order.validate
    input:
      orderId: process.orderId
    timeout: 10 seconds
  }

  parallel {
    task "CheckFraud" {
      handler: risk.check-order
      input:
        orderId: process.orderId
      timeout: 5 seconds
      retry:
        maximumAttempts: 2
    }

    task "CalculateShipping" {
      handler: shipping.quote
      input:
        orderId: process.orderId
    }
  }

  task "ReserveInventory" {
    handler: inventory.reserve
    dependsOn:
      - ValidateOrder
      - CheckFraud
      - CalculateShipping
    idempotencyKey: process.id + ":reserve"
    timeout: 20 seconds
    retry:
      maximumAttempts: 3
      backoff: exponential
    compensate:
      handler: inventory.release
  }

  task "ChargePayment" {
    handler: payment.charge
    dependsOn: ReserveInventory
    idempotencyKey: process.id + ":payment"
    timeout: 15 seconds
    retry:
      maximumAttempts: 2
    compensate:
      handler: payment.refund
  }

  task "GenerateInvoice" {
    handler: invoice.generate
    dependsOn: ChargePayment
  }

  task "SendReceipt" {
    handler: notification.send-receipt
    dependsOn: GenerateInvoice
    on failure:
      route to NotificationPending
  }
}
~~~

Đây là cú pháp khái niệm, không phải grammar của một engine cụ thể.

### 27.1 Bắt đầu process

Một event OrderSubmitted tạo process instance với orderId và definition version cụ thể.

### 27.2 Validate và chạy song song

ValidateOrder phải hoàn tất trước các bước cần dữ liệu hợp lệ. Sau đó CheckFraud và CalculateShipping có thể chạy song song vì chúng đọc dữ liệu và tạo kết quả riêng.

### 27.3 Join và reserve

ReserveInventory chỉ chạy khi các dependency cần thiết hoàn tất. Idempotency key giúp tránh reserve lặp nếu worker retry.

### 27.4 Charge payment

Payment handler dùng idempotency key riêng. Nếu timeout xảy ra sau khi nhà cung cấp đã xử lý charge, lần retry không được tạo giao dịch thứ hai.

### 27.5 Compensation

Nếu một bước sau charge thất bại nghiêm trọng, process có thể refund payment và release inventory theo saga policy. Các compensation có trạng thái và history riêng.

### 27.6 Notification

Nếu gửi receipt thất bại, process có thể tiếp tục ở trạng thái NotificationPending để retry hoặc can thiệp thủ công, tùy yêu cầu nghiệp vụ.

### 27.7 Theo dõi

Task history ghi process ID, task ID, attempt, handler version, trạng thái, thời gian và correlation ID. Người vận hành có thể tìm bước bị lỗi và lý do.

## 28. Câu hỏi tự kiểm tra

1. Tác vụ tự động khác process, workflow, job và worker như thế nào?
2. Một task definition cần mô tả những thành phần nào?
3. Trigger theo bước, event, lịch và điều kiện dữ liệu khác nhau ra sao?
4. Vì sao input/output cần kiểu và schema rõ?
5. Dependency graph và join giúp điều phối task như thế nào?
6. Scheduler, queue và worker pool có vai trò gì?
7. Các trạng thái chính trong task lifecycle là gì?
8. Khi nào nên retry và khi nào không nên retry?
9. Exponential backoff và jitter giúp giảm retry storm ra sao?
10. Idempotency key xử lý message redelivery như thế nào?
11. Timeout và cancellation có bảo đảm side effect bên ngoài đã dừng không?
12. Phân biệt fail-fast, continue-on-error, error route và dead-letter queue.
13. Compensation và saga khác rollback database như thế nào?
14. Concurrency limit và resource key giúp tránh race condition ra sao?
15. Scheduler cần xử lý timezone và missed execution như thế nào?
16. Event-driven task cần quản lý duplicate, ordering và schema version ra sao?
17. Vì sao DSL nên ánh xạ task qua handler registry thay vì class name tùy ý?
18. Những thông tin nào cần có trong task history và trace?
19. Versioning ảnh hưởng process instance đang chạy như thế nào?
20. Cần kiểm thử crash recovery và retry để phát hiện loại lỗi nào?

Tác vụ tự động biến mô tả quy trình thành công việc có thể thực thi và theo dõi. Khi trigger, input/output, dependency, scheduling, retry, idempotency, failure policy và quyền thực thi được định nghĩa rõ, DSL quy trình có thể điều phối các công việc nền một cách ổn định, có thể giải thích và dễ vận hành.

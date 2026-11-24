# Theo dõi tiến độ, tỷ lệ thành công và chi phí theo job

Hệ thống xử lý nền có thể nhận hàng nghìn hoặc hàng triệu job, chạy chúng trên worker, container, VM hoặc serverless function rồi trả kết quả sau một khoảng thời gian. Chỉ biết queue còn bao nhiêu message hoặc worker đang chạy bao nhiêu process chưa đủ để trả lời các câu hỏi vận hành: job nào đang chậm, đã hoàn thành bao nhiêu phần, tỷ lệ thành công thực sự là bao nhiêu, retry đang tiêu tốn bao nhiêu tài nguyên và một job hoàn tất có giá bao nhiêu.

Muốn theo dõi chính xác, cần coi **job là một thực thể nghiệp vụ có định danh và vòng đời riêng**. Mỗi job cần trạng thái, mốc thời gian, tiến độ, số lần thử, kết quả và thông tin tài nguyên được sử dụng. Dữ liệu này phải liên kết được với queue, worker, function invocation, container/VM và billing record. Khi đó, đội vận hành có thể theo dõi từ lúc job được tiếp nhận đến khi có kết quả cuối, phân biệt lỗi tạm thời với lỗi cuối cùng và tính chi phí theo công việc đã hoàn thành.

Bài học này trình bày mô hình dữ liệu và trạng thái job, cách đo tiến độ và success rate, cách ghi nhận retry/partial failure, cách phân bổ compute cost theo job, cách xây dashboard và cảnh báo, cùng quy trình đối soát dữ liệu để vận hành batch workload có thể đo lường được.

## 1. Phân biệt job, task, attempt và message

Các khái niệm này thường bị dùng thay thế nhau nhưng không cùng ý nghĩa:

- **Job:** công việc nghiệp vụ mà người dùng hoặc hệ thống yêu cầu hoàn thành, ví dụ xử lý một lô hóa đơn hoặc tạo báo cáo tháng.
- **Task/item:** đơn vị nhỏ hơn nằm trong job, ví dụ một hóa đơn, một file hoặc một bản ghi.
- **Attempt:** một lần thực thi job hoặc task. Một job có thể có nhiều attempt do retry.
- **Message:** thông điệp được queue hoặc event bus giao cho consumer. Một message có thể đại diện cho cả job, một task hoặc một batch item.
- **Worker invocation:** một lần worker, container hoặc function được gọi để xử lý công việc.
- **Execution:** khoảng thời gian thực tế mà một process/function thực hiện một attempt hoặc một phần của attempt.

Ví dụ, job tạo báo cáo tháng 11/2026 xử lý 1 triệu bản ghi. Hệ thống chia dữ liệu thành 100 partition. Mỗi partition là một task; mỗi task có thể được retry một hoặc nhiều lần. Worker invocation có thể xử lý một task hoặc một batch gồm nhiều task.

Nếu chỉ đếm message, ta có thể đếm 100 message được publish dù một số task được retry nhiều lần. Nếu chỉ đếm invocation, ta có thể đếm 110 lần chạy dù chỉ có 100 task cuối cùng thành công. Vì vậy cần giữ quan hệ rõ ràng giữa job, task, attempt và invocation.

### Mô hình quan hệ

~~~mermaid
flowchart TD
    J["Job"] --> T1["Task / partition 1"]
    J --> T2["Task / partition 2"]
    J --> T3["Task / partition N"]
    T1 --> A11["Attempt 1"]
    T1 --> A12["Attempt 2 (retry)"]
    T2 --> A21["Attempt 1"]
    A11 --> I1["Worker invocation"]
    A12 --> I2["Worker invocation"]
    A21 --> I3["Worker invocation"]
    I1 --> R1["Resource usage"]
    I2 --> R2["Resource usage"]
    I3 --> R3["Resource usage"]
~~~

Job là đơn vị để báo cáo tiến độ nghiệp vụ và chi phí tổng. Task giúp theo dõi tiến độ chi tiết. Attempt giúp giải thích retry và lỗi. Invocation cùng resource usage giúp đối chiếu tài nguyên compute.

## 2. Định nghĩa vòng đời job

Một job cần có state machine rõ ràng. Trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| CREATED | Job đã được tạo nhưng chưa được chấp nhận vào hàng đợi |
| QUEUED | Job đã được chấp nhận và đang chờ worker |
| SCHEDULED | Hệ thống đã chọn thời điểm hoặc worker dự kiến chạy |
| RUNNING | Có attempt đang thực thi |
| RETRY_WAIT | Attempt thất bại tạm thời và job chờ retry |
| PARTIALLY_SUCCEEDED | Một phần task đã thành công, phần còn lại chưa hoàn tất hoặc thất bại |
| SUCCEEDED | Job hoàn tất theo tiêu chí nghiệp vụ |
| FAILED | Job đã kết thúc với lỗi không thể tự phục hồi hoặc hết retry |
| CANCEL_REQUESTED | Đã nhận yêu cầu hủy nhưng chưa xác nhận dừng |
| CANCELED | Job đã dừng theo yêu cầu |
| TIMED_OUT | Job hoặc deadline tổng đã hết thời gian cho phép |
| EXPIRED | Job quá hạn trước khi bắt đầu hoặc không còn hợp lệ |

Không phải hệ thống nào cũng cần mọi trạng thái. Quan trọng là định nghĩa trạng thái có ý nghĩa nhất quán, chuyển trạng thái hợp lệ và điều kiện kết thúc rõ ràng.

### Trạng thái không phải log message

Không nên suy ra trạng thái cuối bằng cách tìm chuỗi log như "done" hoặc "error". Log có thể bị thiếu, đến trễ hoặc lặp. Trạng thái cần được lưu trong nguồn dữ liệu có thẩm quyền, có timestamp, version hoặc sequence để tránh ghi đè sai thứ tự.

### Chuyển trạng thái hợp lệ

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> RUNNING
    RUNNING --> PARTIALLY_SUCCEEDED
    PARTIALLY_SUCCEEDED --> RUNNING
    RUNNING --> FAILED
    QUEUED --> CANCELED
    RUNNING --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> CANCELED
    QUEUED --> EXPIRED
~~~

Một job đã SUCCEEDED không nên tự chuyển lại RUNNING do một event cũ đến muộn. Nếu nghiệp vụ cần chạy lại, tạo job mới hoặc một generation mới có liên kết với job trước. Cách này giữ lịch sử và tránh làm sai báo cáo success rate.

### State transition phải nguyên tử

Nếu hai worker cùng nhận một job do duplicate delivery, cả hai không được cùng cập nhật trạng thái và ghi kết quả mà không có coordination. Có thể dùng:
- Conditional update theo state hiện tại.
- Optimistic concurrency với version.
- Lease/lock có thời hạn.
- Unique constraint cho attempt hoặc idempotency key.
- Transaction ghi kết quả và trạng thái hoàn tất.

Trạng thái job cần phản ánh công việc thực tế, không chỉ việc message đã được ack.

## 3. Thiết kế dữ liệu theo dõi job

Một record job có thể lưu:

| Trường | Mục đích |
|---|---|
| job_id | Định danh duy nhất của job |
| job_type | Loại nghiệp vụ hoặc loại pipeline |
| tenant_id / owner | Chủ thể hoặc team sở hữu, theo chính sách dữ liệu |
| status | Trạng thái hiện tại |
| created_at | Thời điểm tạo |
| accepted_at | Thời điểm hệ thống chấp nhận |
| started_at | Thời điểm bắt đầu xử lý lần đầu |
| completed_at | Thời điểm kết thúc cuối cùng |
| deadline_at | Hạn hoàn tất |
| progress_current | Số đơn vị đã hoàn thành |
| progress_total | Tổng đơn vị dự kiến |
| progress_unit | Item, file, record, partition hoặc đơn vị khác |
| success_count | Số task/item thành công |
| failure_count | Số task/item thất bại |
| retry_count | Số lần retry |
| attempt_count | Tổng attempt |
| result_ref | Tham chiếu kết quả hoặc artifact |
| error_code | Mã lỗi cuối hoặc lỗi gần nhất |
| version | Phiên bản state để chống ghi đè |
| correlation_id | Liên kết log, trace và workflow |

Không phải mọi job đều biết tổng số item ngay từ đầu. Với job streaming hoặc crawl dữ liệu chưa biết kích thước, progress_total có thể null và UI nên hiển thị tiến độ indeterminate thay vì bịa phần trăm.

### Bảng attempt

Lưu attempt riêng giúp tính retry và chi phí:

| Trường | Ý nghĩa |
|---|---|
| attempt_id | Định danh lần thử |
| job_id / task_id | Job hoặc task cha |
| attempt_number | Số thứ tự attempt |
| worker_id | Worker hoặc execution environment |
| started_at / ended_at | Khoảng thời gian thực thi |
| outcome | Success, transient failure, permanent failure, timeout, canceled |
| error_code | Mã lỗi |
| retryable | Có được retry theo policy không |
| resource_ref | ID invocation, pod, container hoặc VM |
| cpu_time | CPU time nếu đo được |
| memory_peak | Peak memory |
| gpu_time | Thời gian accelerator nếu có |
| bytes_read / bytes_written | Lượng dữ liệu |
| cost_estimate | Chi phí ước lượng, nếu tính được |

Không ghi đè attempt cũ khi retry. Mỗi attempt là một sự kiện lịch sử riêng.

### Lưu lịch sử sự kiện

Có thể lưu bảng job hiện tại và bảng event append-only:
- JobCreated.
- JobQueued.
- JobStarted.
- ProgressUpdated.
- AttemptFailed.
- RetryScheduled.
- TaskCompleted.
- JobCompleted.
- JobCanceled.

Bảng current state phục vụ truy vấn nhanh; event history giúp audit, dựng lại tiến độ và điều tra sai lệch. Cần có sequence/version để xử lý event đến trễ hoặc duplicate.

## 4. Đo tiến độ job

Tiến độ cần phản ánh lượng công việc đã hoàn thành so với tổng công việc dự kiến.

Nếu các item có khối lượng tương đương:

\[
Progress(\%) = \frac{CompletedItems}{TotalItems} \times 100
\]

Ví dụ job có 2.000 file, 1.500 file đã hoàn tất:

\[
Progress = \frac{1500}{2000} \times 100 = 75\%
\]

Đây là tiến độ theo số item. Nếu mỗi file có kích thước hoặc thời gian xử lý rất khác nhau, 75% số file không có nghĩa 75% tổng công việc hoặc 75% thời gian còn lại.

### Tiến độ có trọng số

Nếu từng item có khối lượng khác nhau, dùng trọng số:

\[
Progress(\%) =
\frac{\sum_{i \in completed} w_i}
{\sum_{i \in all} w_i} \times 100
\]

Trọng số có thể là:
- Số byte cần xử lý.
- Số record.
- Số trang.
- Số frame.
- Estimated CPU units.
- Điểm complexity đã hiệu chuẩn.

Chọn trọng số phải dựa trên workload. Số byte phù hợp với file transfer nhưng có thể không phản ánh độ khó khi giải nén hoặc phân tích nội dung.

### Tiến độ theo stage

Job nhiều giai đoạn có thể báo cáo từng stage:
1. Download input.
2. Validate.
3. Transform.
4. Persist output.
5. Publish result.

Có thể gán trọng số cho từng stage, ví dụ 10%, 10%, 55%, 20%, 5%. Khi đó tiến độ tổng là tổng trọng số các stage đã hoàn tất cộng phần tiến độ của stage đang chạy.

Trọng số cần được hiệu chuẩn bằng thời gian hoặc effort lịch sử. Nếu stage transform chiếm 80% thời gian nhưng chỉ được gán 20%, phần trăm sẽ tăng nhanh rồi đứng lâu, gây hiểu nhầm.

### Không cộng trùng tiến độ khi retry

Nếu task hoàn tất ở attempt 1 nhưng message được giao lại do ack thất bại, attempt 2 không được cộng thêm lần nữa. Progress nên dựa trên task identity và trạng thái kết quả cuối, không dựa trên số attempt thành công.

Dùng unique task ID hoặc idempotency key để chỉ ghi nhận một lần hoàn thành nghiệp vụ.

### Tiến độ có thể giảm không?

Với job xử lý một tập dữ liệu cố định, progress thường nên đơn điệu tăng. Tuy nhiên, nếu tổng số item được phát hiện thêm trong quá trình scan hoặc một bước validation loại bỏ item, mẫu số có thể thay đổi và phần trăm có thể giảm.

Cần chọn một trong các cách:
- Chốt total trước khi bắt đầu.
- Hiển thị completed / discovered và cho biết total còn thay đổi.
- Tách phase discovery và processing.
- Đánh dấu progress là estimate khi total chưa ổn định.

Không âm thầm thay đổi mẫu số khiến người dùng tưởng job bị lùi tiến độ.

### ETA (thời gian còn lại)

Nếu tốc độ xử lý tương đối ổn định:

\[
ETA \approx \frac{RemainingWork}{ObservedThroughput}
\]

Ví dụ còn 3.000 record và tốc độ trung bình gần đây là 100 record/giây:

\[
ETA \approx 30\ seconds
\]

Dùng moving average hoặc percentile theo cửa sổ thời gian để tránh ETA nhảy mạnh. ETA nên là ước lượng, đặc biệt khi item size, retry hoặc dependency latency biến động.

## 5. Theo dõi tiến độ ở job, task và attempt

Ba cấp độ cung cấp ba góc nhìn:

- **Job-level:** trạng thái nghiệp vụ tổng, progress, deadline, kết quả và cost tổng.
- **Task-level:** task nào đang chờ, chạy, retry, thành công hoặc lỗi.
- **Attempt-level:** lần thực thi nào tiêu tốn bao nhiêu thời gian/tài nguyên và thất bại vì lý do gì.

Dashboard chỉ hiển thị job-level có thể không giải thích vì sao job chậm. Task-level giúp tìm partition bị kẹt; attempt-level cho biết lỗi lặp ở worker, zone hoặc dependency nào.

### Các timestamp quan trọng

- created_at.
- accepted_at.
- enqueued_at.
- dequeued_at.
- started_at.
- heartbeat_at.
- progress_updated_at.
- attempt_ended_at.
- retry_scheduled_at.
- completed_at.

Từ đó có thể tính:
- Admission delay = accepted_at - created_at.
- Queue wait = started_at - enqueued_at.
- Execution duration = attempt_ended_at - started_at.
- Retry wait = next_attempt_started_at - previous_attempt_ended_at.
- End-to-end duration = completed_at - created_at.
- Deadline slack = deadline_at - completed_at.

Cần định nghĩa timezone thống nhất và đồng bộ clock giữa producer, queue, worker và database. Clock skew có thể tạo duration âm hoặc thứ tự sự kiện sai.

## 6. Định nghĩa tỷ lệ thành công đúng cách

Không có một success rate duy nhất phù hợp mọi mục tiêu. Cần ghi rõ mẫu số, khoảng thời gian và cách tính retry.

### Final job success rate

Tính trên các job đã đi tới trạng thái cuối trong cohort được chọn:

\[
FinalSuccessRate =
\frac{SucceededJobs}
{SucceededJobs + FailedJobs + TimedOutJobs + CanceledJobs}
\times 100
\]

Có thể loại canceled do người dùng khỏi mẫu số nếu mục tiêu là đo chất lượng xử lý kỹ thuật, nhưng phải công bố quy tắc. Không đưa job đang chạy vào mẫu số nếu muốn đo kết quả cuối; nếu không, success rate sẽ bị thấp giả tạo trong giờ tải cao.

### First-attempt success rate

Đo tỷ lệ job/task thành công ngay lần đầu:

\[
FirstAttemptSuccessRate =
\frac{JobsSucceededOnFirstAttempt}
{JobsWithAtLeastOneAttempt}
\times 100
\]

Chỉ số này cho biết độ ổn định ban đầu và mức độ phụ thuộc retry.

### Eventual success rate

Đo tỷ lệ job cuối cùng thành công sau khi cho phép retry trong policy:

\[
EventualSuccessRate =
\frac{JobsEventuallySucceeded}
{EligibleJobsWhoseRetryWindowClosed}
\times 100
\]

Cần đợi retry window đóng hoặc job đạt trạng thái cuối. Nếu tính quá sớm, job đang retry có thể bị phân loại sai.

### Task success và partial success

Với job gồm nhiều task:

\[
TaskSuccessRate =
\frac{SuccessfulTasks}
{CompletedTasks + FailedTasks}
\times 100
\]

Job có thể PARTIALLY_SUCCEEDED nếu nghiệp vụ cho phép hoàn tất một phần. Cần xác định:
- Có bao nhiêu task tối thiểu để job được chấp nhận?
- Task lỗi có thể bỏ qua không?
- Có cần xuất danh sách failed item?
- Kết quả có thể dùng được không?
- Ai quyết định job partial success là thành công hay thất bại?

Không tính job partial thành success hoàn toàn nếu nghiệp vụ yêu cầu tất cả item phải xử lý.

### On-time success rate

Nếu có deadline:

\[
OnTimeSuccessRate =
\frac{JobsSucceededBeforeDeadline}
{EligibleTerminalJobs}
\times 100
\]

Một job hoàn tất sau deadline có thể là technical success nhưng business SLA failure. Nên theo dõi riêng final success và on-time success.

## 7. Phân biệt lỗi, retry và kết quả cuối

Retry có thể cải thiện eventual success nhưng che giấu chất lượng ban đầu và làm tăng cost.

### Phân loại kết quả attempt

- **Success:** attempt hoàn tất và kết quả hợp lệ.
- **Transient failure:** lỗi tạm thời có khả năng phục hồi, ví dụ throttling hoặc network reset.
- **Permanent failure:** input không hợp lệ hoặc lỗi nghiệp vụ không thể tự sửa bằng retry.
- **Timeout:** attempt vượt execution deadline.
- **Canceled:** bị hủy theo yêu cầu hoặc policy.
- **Unknown outcome:** worker mất kết nối sau side effect, chưa biết tác vụ đã commit hay chưa.

Unknown outcome đặc biệt quan trọng. Không retry mù quáng nếu side effect có thể đã xảy ra. Cần idempotency key, transaction record hoặc reconciliation.

### Retry metrics

Theo dõi:
- Attempts per job.
- Retry count per task.
- First-attempt failure rate.
- Retry success rate.
- Retry exhaustion rate.
- Dead-letter count.
- Duplicate delivery count.
- Retry delay.
- Cost spent on failed attempts.

Một job cuối cùng thành công sau 5 lần retry vẫn chỉ là một job thành công, nhưng có 5 attempt và có thể tốn gấp nhiều lần tài nguyên.

### Backoff và retry budget

Dùng exponential backoff có cap và jitter để tránh nhiều worker retry cùng lúc. Giới hạn số attempt, tổng retry age hoặc tổng retry budget. Permanent failure nên được đưa vào trạng thái lỗi cuối hoặc DLQ thay vì lặp vô hạn.

### Idempotency và duplicate

Queue thường cung cấp at-least-once delivery trong nhiều cấu hình. Consumer có thể nhận cùng message nhiều lần. Dùng:
- Idempotency key theo business operation.
- Unique constraint hoặc conditional write.
- Inbox/deduplication record.
- Transaction ghi kết quả và trạng thái.
- Outbox khi cần phát event sau commit.

Không dùng attempt_id làm idempotency key cho nghiệp vụ vì mỗi retry có attempt_id mới. Key cần ổn định qua các lần giao lại.

## 8. Đo chi phí theo job

Chi phí theo job nên tính toàn bộ tài nguyên đã tiêu thụ để tạo ra kết quả, bao gồm cả attempt thất bại, retry và overhead được phân bổ.

Một mô hình tổng quát:

\[
JobCost =
ComputeCost + StorageCost + NetworkCost +
AcceleratorCost + OrchestrationCost + SharedCost
\]

Tùy kiến trúc, có thể thêm database, queue, observability, license và data transfer.

### Compute cost

Với VM/Node tính theo thời gian cấp phát:

\[
ComputeCost =
\sum_{r} BillableHours_r \times EffectiveRate_r
\]

Nếu job chia sẻ node với nhiều workload, cần phân bổ node cost theo CPU/memory request, actual usage hoặc capacity reserved.

Với function/container tính theo resource-time:

\[
ComputeCost =
CPUTime \times CPUUnitRate +
MemoryTime \times MemoryUnitRate
\]

Chỉ dùng công thức này nếu provider thực sự có meter riêng cho CPU và memory. Một số dịch vụ tính theo cấu hình instance hoặc request/duration khác.

### Cost per successful job

\[
CostPerSuccessfulJob =
\frac{TotalAllocatedJobCost}
{SuccessfulJobs}
\]

Nếu muốn đo chi phí để hoàn thành đúng hạn:

\[
CostPerOnTimeJob =
\frac{TotalAllocatedJobCost}
{OnTimeSuccessfulJobs}
\]

Cần đồng bộ cùng time window, workload scope, currency và cost basis. Nếu job chưa kết thúc, cost hiện tại chỉ là estimate.

### Retry cost

Tổng cost phải cộng tất cả attempt:

\[
JobCost = \sum_{a=1}^{n} AttemptCost_a + AllocatedOverhead
\]

Không chỉ tính attempt cuối thành công. Nếu attempt đầu chạy 10 phút rồi timeout, attempt sau chạy 2 phút và thành công, cả 12 phút resource-time có thể phát sinh phí.

### Queue wait không nhất thiết là compute charge

Thời gian job nằm trong queue thường không tiêu thụ compute worker, nhưng có thể phát sinh queue/storage charge hoặc chi phí giữ warm capacity. Phân biệt:
- Queue wait.
- Worker execution.
- Provisioned idle capacity.
- Retry delay.
- Orchestration state duration.

Nếu worker VM luôn chạy và chờ job, phần idle cost cần được phân bổ vào workload theo policy.

## 9. Phân bổ chi phí shared resource

Nhiều job cùng chạy trên một worker pool hoặc Kubernetes node. Billing provider có thể chỉ ghi chi phí theo VM/node-hour, không ghi trực tiếp cost theo job. Cần chọn allocation driver.

| Resource | Driver phân bổ gợi ý |
|---|---|
| Shared VM/node CPU | CPU-seconds hoặc CPU request-time |
| Shared VM/node memory | Memory working-set-time hoặc memory request-time |
| GPU worker | GPU-seconds, VRAM allocation hoặc device-time |
| Object storage | Bytes stored × retention duration |
| Data transfer | Bytes read/written theo job |
| Queue | Message count/bytes hoặc operation count |
| Database | Query time, transaction time hoặc resource usage |
| Orchestration | State transition, execution duration hoặc fixed share |
| Monitoring/logging | Log/trace bytes theo job hoặc service share |

### CPU và memory allocation

Với worker xử lý nhiều job đồng thời, có thể đo CPU time theo process/container hoặc cgroup. Memory phức tạp hơn vì nhiều job có thể chia sẻ cache và heap. Có thể dùng memory request-time hoặc working set estimate theo từng worker, nhưng phải công bố đây là allocation model.

Không cộng toàn bộ RSS của worker cho từng job đang chạy vì sẽ đếm trùng. Nếu không thể đo memory riêng theo job, dùng driver hợp lý và đánh dấu độ chính xác.

### Phân bổ idle capacity

Nếu worker pool giữ capacity dự phòng để đáp ứng latency hoặc availability, phần idle cost có thể được phân bổ:
- Theo tỷ trọng peak capacity từng workload.
- Theo CPU/memory reservation.
- Theo tỷ trọng usage.
- Thành platform overhead chung.

Chọn policy ổn định để các kỳ báo cáo so sánh được. Không thay đổi driver mỗi tháng chỉ để làm một workload trông rẻ hơn.

## 10. Gắn cost với job qua correlation và resource telemetry

Để liên kết job với chi phí, cần truyền định danh qua các lớp:

job_id → task_id → attempt_id → worker_id → invocation_id / pod_uid / container_id / vm_id → billing meter.

### Metadata tối thiểu

Mỗi log/trace/metric event nên có khi phù hợp:
- job_id.
- task_id.
- attempt_id.
- job_type.
- tenant/team hoặc cost_center.
- worker_id.
- execution environment.
- region/zone.
- function version hoặc image digest.
- correlation_id/trace_id.

Không đưa job_id làm label cho metric có cardinality lớn nếu backend metrics không hỗ trợ. Hàng triệu job sẽ tạo hàng triệu time series. Dùng job_id trong structured log, trace hoặc bảng fact; metric tổng hợp theo job_type, queue, status và environment.

### Context propagation

Khi job gọi function khác hoặc publish message mới, giữ correlation ID và business job ID trong message metadata. Không dựa vào thread-local hoặc process memory vì công việc có thể đi qua queue, worker khác hoặc execution environment khác.

### Resource mapping

Với container, lưu pod UID và container ID cùng attempt. Với VM worker, ghi worker process ID và thời gian thực thi. Với serverless, lưu invocation/request ID theo khả năng provider. Sau đó đối chiếu resource telemetry với billing export theo resource ID/SKU/time window.

## 11. Ví dụ cấu trúc bảng theo dõi

Có thể thiết kế các bảng logic như sau:

~~~sql
CREATE TABLE jobs (
    job_id           VARCHAR(128) PRIMARY KEY,
    job_type         VARCHAR(80) NOT NULL,
    status           VARCHAR(32) NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    accepted_at      TIMESTAMP,
    started_at       TIMESTAMP,
    completed_at     TIMESTAMP,
    deadline_at      TIMESTAMP,
    progress_current BIGINT,
    progress_total   BIGINT,
    progress_unit    VARCHAR(32),
    success_count    BIGINT DEFAULT 0,
    failure_count    BIGINT DEFAULT 0,
    retry_count      BIGINT DEFAULT 0,
    version          BIGINT NOT NULL
);

CREATE TABLE job_attempts (
    attempt_id       VARCHAR(128) PRIMARY KEY,
    job_id           VARCHAR(128) NOT NULL,
    task_id          VARCHAR(128),
    attempt_number   INTEGER NOT NULL,
    started_at       TIMESTAMP,
    ended_at         TIMESTAMP,
    outcome          VARCHAR(32),
    error_code       VARCHAR(80),
    worker_id        VARCHAR(128),
    resource_ref     VARCHAR(256),
    cpu_seconds      DECIMAL(18,6),
    memory_gib_sec   DECIMAL(18,6),
    bytes_read       BIGINT,
    bytes_written    BIGINT
);
~~~

Đây là schema minh họa. Production cần index theo job_id, status, created_at, job_type và partition theo thời gian nếu volume lớn. Cần retention phù hợp, encryption, quyền truy cập và chính sách xóa dữ liệu.

### Cập nhật tiến độ an toàn

Khi task hoàn thành, cập nhật task result và aggregate progress trong transaction hoặc qua event consumer có deduplication. Không tăng progress_current mỗi lần nhận message nếu message có thể được giao lại.

Có thể dùng unique key theo job_id và task_id để bảo đảm mỗi task chỉ được ghi nhận kết quả cuối một lần. Nếu job chia partition, cần lưu trạng thái từng partition để có thể tính lại aggregate khi event bị mất hoặc đến trễ.

## 12. Dashboard theo dõi job

Dashboard nên phục vụ ba nhóm người dùng: người yêu cầu job, đội vận hành và đội quản lý chi phí.

### Dashboard người dùng/nghiệp vụ

Hiển thị:
- Job ID và loại job.
- Trạng thái hiện tại.
- Progress và đơn vị đo.
- Số item thành công/thất bại/đang xử lý.
- ETA nếu có đủ dữ liệu.
- Thời điểm bắt đầu và dự kiến hoàn tất.
- Kết quả hoặc link tải artifact.
- Hành động hủy hoặc retry nếu được phép.

Không hiển thị phần trăm giả khi total chưa biết. Có thể hiển thị "đã xử lý 2.400 item" thay cho 60%.

### Dashboard vận hành

Hiển thị theo job type, queue và worker pool:
- Jobs queued/running/retry_wait.
- Oldest queued job age.
- Queue wait p50/p95/p99.
- Execution duration p50/p95/p99.
- Jobs succeeded/failed/timed out.
- First-attempt và eventual success rate.
- Retry count và retry exhaustion.
- Partial success.
- DLQ depth.
- Worker concurrency và utilization.
- Deadline miss và throughput.

### Dashboard chi phí

Hiển thị:
- Total job cost.
- Cost per successful job.
- Cost per on-time job.
- Cost theo job_type/tenant/team.
- Compute, storage, network, accelerator và shared cost.
- Cost do retry/failure.
- Cost estimate cho job đang chạy.
- Actual cost đã reconcile với billing.
- Unallocated cost và confidence level.

Nên cho phép drill-down từ tháng → job type → job → task → attempt để điều tra chi phí.

## 13. Metric và cảnh báo cần có

### Metric tiến độ và throughput

- jobs_created_total.
- jobs_queued.
- jobs_running.
- jobs_succeeded_total.
- jobs_failed_total.
- tasks_completed_total.
- tasks_failed_total.
- job_progress_ratio.
- job_queue_wait_seconds.
- job_execution_seconds.
- job_end_to_end_seconds.
- completed_items_per_second.

Metric dạng counter nên tăng đơn điệu; gauge dùng cho trạng thái hiện tại như số job đang chạy. Histogram phù hợp cho duration và queue wait.

### Metric chất lượng

- first_attempt_success_rate.
- eventual_success_rate.
- on_time_success_rate.
- retry_attempts_per_job.
- partial_success_jobs.
- dead_letter_jobs.
- duplicate_task_events.
- job_timeout_total.

Success rate thường được tính trong query/dashboard từ counter hoặc fact table theo cohort, không nên phát một gauge không có mẫu số rõ ràng.

### Metric chi phí

- job_cost_estimated.
- job_cost_actual.
- job_compute_seconds.
- job_cpu_seconds.
- job_memory_gib_seconds.
- job_gpu_seconds.
- job_bytes_processed.
- job_retry_cost.
- cost_per_successful_job.

Không nhất thiết mọi metric cost được phát trực tiếp từ worker. Có thể tính ở pipeline FinOps bằng cách join attempt telemetry với billing export.

### Alert ví dụ

- Job queued quá lâu so với SLA.
- Job running không có heartbeat trong thời gian cho phép.
- Success rate giảm dưới ngưỡng.
- Retry rate tăng bất thường.
- DLQ tăng liên tục.
- On-time success giảm.
- Cost per successful job vượt baseline.
- Một job tiêu thụ tài nguyên vượt budget.
- Unallocated cost vượt tỷ lệ cho phép.
- Job chạy lâu hơn p99 baseline hoặc deadline.

Alert cần có window, threshold, owner và runbook. Tránh cảnh báo chỉ vì một job có duration dài nếu loại job đó vốn được thiết kế chạy nhiều giờ.

## 14. Phát hiện job bị treo và tiến độ không cập nhật

Một job có trạng thái RUNNING nhưng không có tiến độ mới chưa chắc bị treo; có thể đang xử lý một item lớn hoặc chờ dependency.

Dùng heartbeat hoặc lease:
- Worker cập nhật heartbeat định kỳ.
- Scheduler phát hiện heartbeat quá hạn.
- Job/task được đánh dấu suspect.
- Hệ thống kiểm tra lease và trạng thái attempt.
- Nếu worker thực sự mất, attempt được kết thúc và task được retry theo policy.

Không chỉ dựa vào heartbeat để kết luận job thất bại. Worker có thể bị pause hoặc network partition. Cần lease expiry, fencing token hoặc attempt generation để ngăn worker cũ tiếp tục ghi sau khi task đã được giao lại.

### Progress heartbeat

Heartbeat có thể chứa:
- attempt_id.
- worker_id.
- last_progress_at.
- current_item hoặc checkpoint.
- lease_expiry.
- worker health.

Không ghi heartbeat quá thường xuyên nếu job có hàng triệu task; chọn chu kỳ phù hợp và dùng batch update hoặc heartbeat riêng khỏi progress event.

### Stale progress

Một job có thể còn heartbeat nhưng progress không đổi. Điều tra:
- Item hiện tại có quá lớn?
- Worker có chờ API/database?
- Có lock contention?
- Có queue consumer pause?
- Có memory pressure hoặc CPU throttling?
- Checkpoint có bị lỗi?
- Job có đang chờ điều kiện nghiệp vụ?

Dùng execution trace và dependency metrics để xác định thay vì tự động retry liên tục.

## 15. Xử lý partial success và kết quả cuối

Job batch thường có thể thành công một phần. Cần mô hình kết quả rõ:
- All-or-nothing.
- Partial success được chấp nhận.
- Partial success cần người vận hành xử lý.
- Có thể retry failed items.
- Có thể bỏ qua một số item theo rule nghiệp vụ.

Ví dụ job nhập 10.000 bản ghi, 9.950 hợp lệ và 50 bị từ chối do dữ liệu sai. Nếu nghiệp vụ cho phép nhập phần hợp lệ, job có thể kết thúc PARTIALLY_SUCCEEDED cùng file lỗi. Nếu nghiệp vụ yêu cầu toàn bộ hoặc không gì cả, cần rollback/compensation hoặc đánh dấu FAILED.

### Báo cáo kết quả

Nên lưu:
- Total items discovered.
- Items attempted.
- Items succeeded.
- Items permanently failed.
- Items skipped.
- Items retried.
- Items pending.
- Error summary theo mã.
- Artifact kết quả và danh sách lỗi.

Không chỉ lưu một error message tổng hợp; người dùng cần biết item nào thất bại và có thể sửa/retry ra sao.

### Retry failed items

Có thể tạo child job hoặc retry task trong cùng job generation. Cần giữ liên kết:
- parent_job_id.
- original_task_id.
- retry_job_id hoặc attempt_id.
- failure reason.
- operator/action nếu retry thủ công.

Khi retry một phần, progress tổng cần phản ánh số task đã hoàn tất cuối cùng, không cộng lại task đã thành công ở lần trước.

## 16. Tính ETA và dự báo hoàn tất

ETA hữu ích khi job có tổng khối lượng biết trước và tốc độ xử lý đủ ổn định.

Công thức đơn giản:

\[
ETA = \frac{RemainingUnits}{AverageUnitsPerSecond}
\]

Có thể dùng throughput trong cửa sổ gần đây thay vì từ lúc bắt đầu để phản ánh tốc độ hiện tại. Nhưng cửa sổ quá ngắn khiến ETA nhiễu; cửa sổ quá dài phản ứng chậm khi tải thay đổi.

### Job có nhiều stage

Tính ETA theo stage:
- Thời gian còn lại stage hiện tại.
- Thời gian stage tiếp theo dựa trên historical duration.
- Thời gian finalize/publish.
- Retry hoặc backoff dự kiến.

Không cộng ETA từng task song song như thể chúng chạy tuần tự. Với N worker xử lý đồng thời, throughput tổng cần đo từ số task hoàn tất trên toàn job.

### Job không biết total

Với crawl hoặc stream:
- Hiển thị throughput và elapsed time.
- Hiển thị số item đã phát hiện.
- Hiển thị trạng thái "đang khám phá" hoặc "không xác định tổng".
- Không hiển thị ETA nếu không có ước lượng đáng tin.

Có thể hiển thị range ETA thay vì một con số chính xác giả tạo.

## 17. Ví dụ: theo dõi job xử lý hóa đơn

Một job xử lý 50.000 hóa đơn theo batch. Mỗi hóa đơn là một task. Hệ thống có 20 worker.

Sau 10 phút:
- 32.000 task thành công.
- 1.000 task thất bại tạm thời và đang retry.
- 500 task thất bại vĩnh viễn.
- 16.500 task chưa có kết quả cuối.
- 200 attempt đã retry thành công trong số các task trước đó.

Nếu progress dựa trên task cuối cùng đã hoàn tất:

\[
Progress = \frac{32{,}000 + 500}{50{,}000} \times 100 = 65\%
\]

Tùy nghiệp vụ, failed permanent có thể được tính là "đã xử lý" về tiến độ nhưng không phải thành công. Vì vậy dashboard nên tách:
- Processed: 32.500.
- Succeeded: 32.000.
- Failed: 500.
- Pending/retry: 17.500.

Success rate trên các task đã có kết quả cuối:

\[
TaskSuccessRate =
\frac{32{,}000}{32{,}000 + 500} \times 100
\approx 98.46\%
\]

Không đưa 17.500 task pending vào mẫu số này. Đồng thời cần báo cáo first-attempt success rate và eventual success rate riêng.

Giả sử tổng cost đã phân bổ cho job đến thời điểm đó là 42 đơn vị tiền. Đây là estimate vì job chưa hoàn tất. Khi job kết thúc, tổng cost là 60 và có 49.500 hóa đơn được chấp nhận:

\[
CostPerAcceptedInvoice = \frac{60}{49{,}500}
\approx 0.001212
\]

Nếu 500 hóa đơn lỗi vĩnh viễn không được chấp nhận, mẫu số không nên là 50.000. Báo cáo có thể thêm cost per attempted invoice để đánh giá toàn bộ workload.

## 18. Ví dụ: tính chi phí attempt và retry

Một task được xử lý qua ba attempt:

| Attempt | Kết quả | Compute cost | Storage/network cost |
|---|---|---:|---:|
| 1 | Timeout sau 90 giây | 0,030 | 0,004 |
| 2 | Dependency throttling sau 30 giây | 0,010 | 0,002 |
| 3 | Success sau 45 giây | 0,015 | 0,003 |
| **Tổng** |  | **0,055** | **0,009** |

Tổng cost task:

\[
0.055 + 0.009 = 0.064
\]

Nếu chỉ tính attempt thành công, cost sẽ là 0,018 và đánh giá thấp hơn thực tế khoảng 72% trong ví dụ này. Cost retry phải được gắn về job/task gốc.

Khi nhiều task chạy song song, cộng cost từng attempt và phân bổ overhead của orchestration/worker pool theo policy. Không lấy toàn bộ chi phí node cho từng task.

## 19. Đối soát job telemetry với billing

Billing export thường ghi usage theo resource, SKU, region và khoảng thời gian. Nó không nhất thiết chứa job_id. Cần dùng telemetry để phân bổ.

Quy trình:
1. Thu attempt start/end và resource identity.
2. Thu CPU/memory/GPU/storage/network usage theo attempt nếu có.
3. Lấy billing usage theo resource ID/SKU/time window.
4. Chia usage theo attempt hoặc workload allocation driver.
5. Cộng cost retry và shared overhead.
6. So sánh tổng phân bổ với billing total.
7. Ghi phần chưa phân bổ và sai lệch.

### Đối chiếu theo resource và thời gian

Nếu một VM worker xử lý 20 job đồng thời, billing chỉ có một dòng instance-hour. Có thể phân bổ theo CPU-seconds của từng job; phần idle và system overhead được phân bổ riêng. Nếu chỉ dựa vào wall-clock duration, job chờ I/O có thể bị tính quá nhiều CPU cost.

### Cost estimate và actual

Trong khi job đang chạy, cost estimate có thể dùng resource usage telemetry và rate hiện hành. Sau khi billing export finalized, cập nhật actual. Gắn nhãn:
- estimated.
- reconciled.
- provisional.
- final.

Không hiển thị estimated như invoice final. Billing data có thể đến trễ hoặc điều chỉnh do discount, credit và rounding.

### Sai lệch cần điều tra

- Worker bị terminate trước khi ghi attempt end.
- Billing record đến trễ.
- VM chạy ngoài thời gian job.
- Nhiều job dùng chung worker.
- Retry attempt không có correlation ID.
- Resource phụ như disk, NAT hoặc log chưa được phân bổ.
- Meter tính theo provisioned time thay vì actual CPU time.
- Cost commitment/discount được phân bổ ở cấp account.

Báo cáo cần có tỷ lệ cost được phân bổ và tỷ lệ unallocated để người xem biết độ tin cậy.

## 20. Retention, bảo mật và quyền truy cập dữ liệu job

Job telemetry có thể chứa thông tin khách hàng, file reference, error message hoặc business metadata. Cần:
- Chỉ lưu dữ liệu cần thiết.
- Không ghi payload nhạy cảm vào log.
- Mã hóa dữ liệu lưu trữ và truyền tải.
- Phân quyền theo tenant/team.
- Giới hạn ai có thể xem result artifact.
- Đặt retention cho job detail, attempt và log.
- Xóa hoặc ẩn danh dữ liệu theo policy.
- Audit thao tác cancel, retry và redrive.

Không cho người dùng xem stack trace hoặc internal resource ID nếu không cần. UI có thể hiển thị error code và hướng xử lý, còn chi tiết kỹ thuật chỉ dành cho operator.

### Cardinality và chi phí observability

Không tạo metric label cho từng job_id hoặc task_id ở quy mô lớn. Dùng:
- Metrics tổng hợp theo job_type, queue, status, region và worker pool.
- Structured logs để truy vấn job cụ thể.
- Trace cho một số execution hoặc sampling phù hợp.
- Fact table/warehouse để tính unit cost và cohort success.

Log và trace cũng có chi phí ingest/retention; instrumentation nên đủ để điều tra nhưng không phát payload khổng lồ ở mọi item.

## 21. Quy trình vận hành và điều tra một job

Khi người dùng báo job chậm hoặc thất bại:

1. Tìm job theo job_id.
2. Xem trạng thái, created/accepted/started và deadline.
3. Kiểm tra progress, total và last_progress_at.
4. Xem task nào đang pending hoặc failed.
5. Mở attempt history của task lỗi.
6. Kiểm tra error code, worker, region và dependency.
7. Xác định lỗi transient, permanent hay unknown outcome.
8. Kiểm tra retry budget, DLQ và duplicate.
9. Kiểm tra CPU, memory, queue wait và dependency latency.
10. Xem cost estimate và cost do retry.
11. Quyết định retry task, retry job, cancel hoặc manual reconciliation.
12. Sau xử lý, ghi outcome và nguyên nhân gốc.

Không retry toàn job chỉ vì một task lỗi nếu các task khác đã tạo side effect không thể lặp. Retry theo task hoặc partition và dùng idempotency.

### Runbook cho job stuck

- Xác nhận heartbeat và lease.
- Kiểm tra worker còn sống hay mất kết nối.
- Kiểm tra attempt có còn quyền ghi không.
- Kiểm tra queue visibility/ack state.
- Kiểm tra dependency timeout.
- Đối chiếu progress event mới nhất.
- Nếu lease hết hạn, fencing worker cũ trước khi giao lại.
- Ghi attempt failure reason.
- Retry theo budget hoặc chuyển DLQ.
- Kiểm tra kết quả và deduplicate sau recovery.

## 22. Quy trình xây dựng hệ thống theo dõi job

1. **Định nghĩa job:** business purpose, owner, input/output và deadline.
2. **Định nghĩa task:** đơn vị nhỏ, key, partition và retry boundary.
3. **Thiết kế state machine:** trạng thái, transition và terminal state.
4. **Thiết kế schema:** job, task, attempt và event history.
5. **Chọn progress model:** item count, weighted work hoặc stage progress.
6. **Định nghĩa success:** first-attempt, eventual, partial và on-time.
7. **Instrument worker:** start/end, heartbeat, progress, resource usage và outcome.
8. **Truyền correlation:** job/task/attempt/resource IDs qua queue và worker.
9. **Thiết kế idempotency:** duplicate delivery, retry và side effect.
10. **Thu billing:** usage quantity, SKU, resource ID và effective rate.
11. **Chọn cost allocation:** direct, shared, idle và retry overhead.
12. **Xây dashboard:** business progress, operations health và unit cost.
13. **Đặt alert:** stale progress, queue age, failure, retry và cost anomaly.
14. **Reconcile:** so allocated cost với billing total.
15. **Rà soát:** cập nhật baseline, thresholds và retention theo workload.

## 23. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Đếm invocation thay cho job | Retry làm job count bị phóng đại | Dùng job_id và attempt_id riêng |
| Tính progress theo message ack | Ack không đồng nghĩa nghiệp vụ hoàn tất | Cập nhật khi task result được commit |
| Cộng progress mỗi lần retry thành công | Progress vượt 100% | Deduplicate theo task identity |
| Đưa job đang chạy vào mẫu số success rate | Success rate giảm giả tạo | Dùng terminal cohort và công bố window |
| Gộp first-attempt và eventual success | Che giấu chất lượng ban đầu | Báo cáo hai chỉ số riêng |
| Coi partial success là success toàn phần | Báo cáo sai kết quả nghiệp vụ | Định nghĩa accepted outcome |
| Bỏ qua retry cost | Unit cost thấp giả tạo | Cộng mọi attempt và overhead |
| Gán toàn bộ VM cost cho mỗi job | Đếm trùng chi phí | Phân bổ shared node theo driver |
| Dùng job_id làm metric label | Cardinality và cost metrics tăng mạnh | Dùng log/trace/fact table |
| Dùng heartbeat làm bằng chứng hoàn tất | Job có thể sống nhưng không tiến triển | Theo dõi progress và lease |
| Không xử lý event đến trễ | State bị lùi hoặc ghi đè | Version/sequence và conditional update |
| Không đồng bộ time window | Cost và output lệch kỳ | Chuẩn hóa UTC và cohort |
| Gọi estimate là actual | Quyết định ngân sách sai | Gắn trạng thái provisional/reconciled/final |

## 24. Checklist production

### Job model và progress
- [ ] Có job_id ổn định và job_type.
- [ ] Job, task, attempt và invocation được phân biệt.
- [ ] State machine có transition và terminal state rõ.
- [ ] Có task identity để chống cộng tiến độ trùng.
- [ ] Progress có unit, total và quy tắc khi total chưa biết.
- [ ] Weighted progress được hiệu chuẩn nếu item không đồng đều.
- [ ] ETA được đánh dấu là estimate.

### Success và reliability
- [ ] Có định nghĩa first-attempt success rate.
- [ ] Có định nghĩa eventual success rate.
- [ ] Job running không nằm sai trong mẫu số terminal success.
- [ ] Partial success có quy tắc nghiệp vụ.
- [ ] Retry và attempt được lưu riêng.
- [ ] Có idempotency và deduplication.
- [ ] Có heartbeat, lease và fencing khi cần.
- [ ] Có DLQ, retry budget và runbook redrive.

### Cost và observability
- [ ] Mọi attempt có thời gian và resource reference.
- [ ] Retry cost được cộng vào job.
- [ ] Shared resource có allocation driver.
- [ ] Idle capacity và orchestration overhead được xử lý.
- [ ] Có cost per successful job và on-time job.
- [ ] Cost estimate được phân biệt với billing actual.
- [ ] Có đối soát tổng allocation với billing export.
- [ ] Có tỷ lệ unallocated cost.
- [ ] Metrics không dùng job_id cardinality cao.
- [ ] Logs/traces có correlation ID.
- [ ] Dashboard theo job type, status, queue và cost.
- [ ] Alert cho stale progress, queue age, retry, failure và cost anomaly.

### Governance
- [ ] Có owner và deadline cho từng job type.
- [ ] Có retention và access policy cho job/attempt data.
- [ ] Có audit cho cancel/retry/redrive.
- [ ] Có quy trình điều tra job stuck.
- [ ] Có baseline và lịch review success rate/unit cost.

## Kết luận

Theo dõi job hiệu quả cần một định danh ổn định và mô hình dữ liệu tách job, task, attempt với worker invocation. Tiến độ nên dựa trên task hoàn tất hoặc khối lượng có trọng số, không dựa trên số message được giao hay số lần retry. Success rate cần tách first-attempt, eventual, partial và on-time outcome, với mẫu số chỉ gồm cohort đã đủ điều kiện kết thúc. Chi phí theo job phải cộng mọi attempt, retry và phần shared resource được phân bổ theo policy; billing export là cơ sở đối chiếu actual, còn telemetry giúp phân bổ và giải thích. Khi kết hợp state machine, progress event, heartbeat/lease, correlation ID, dashboard và reconciliation, đội vận hành có thể biết job đang ở đâu, kết quả có đáng tin hay không và mỗi kết quả hoàn tất đang tiêu tốn bao nhiêu tài nguyên.

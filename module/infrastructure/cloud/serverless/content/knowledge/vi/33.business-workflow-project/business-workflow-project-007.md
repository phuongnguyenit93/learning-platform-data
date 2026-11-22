# Kiểm thử workflow bị hủy, retry và hết hạn chờ

Workflow nghiệp vụ thường kéo dài qua nhiều function invocation, message delivery và lần chờ callback. Một workflow có thể đang chờ khách hàng phê duyệt, đang gọi payment provider, retry một bước bị throttling hoặc hết thời hạn chờ đối tác. Vì vậy, kiểm thử workflow không thể chỉ xác minh đường chạy thành công; cần chứng minh hệ thống xử lý đúng khi workflow bị hủy, một bước thất bại nhiều lần, timer hết hạn hoặc nhiều tín hiệu đến cùng lúc.

Trong serverless, function invocation có thể bị dừng vì timeout, scale-in hoặc lỗi runtime. Việc một invocation kết thúc không đồng nghĩa workflow đã bị hủy. Trạng thái workflow phải được lưu bền vững và được điều phối bằng state machine, workflow engine hoặc database có kiểm soát transition. Cancellation, retry và wait expiry là các quyết định nghiệp vụ cần được xử lý rõ ràng, có idempotency và có thể kiểm chứng.

Bài học tập trung vào cách kiểm thử ba nhóm hành vi: hủy workflow và các tác dụng phụ cần bù trừ; retry có giới hạn cho từng bước; và hết hạn khi workflow đang chờ timer hoặc callback. Ví dụ dùng một quy trình xử lý đơn hàng gồm kiểm tra tồn kho, giữ thanh toán, chờ phê duyệt và tạo lệnh giao hàng, nhưng các nguyên tắc áp dụng cho Java serverless workflow nói chung.

## 1. Workflow khác một function invocation

Function invocation là một lần thực thi code có thời hạn. Workflow là tiến trình nghiệp vụ có trạng thái, có thể kéo dài lâu hơn một invocation và tiếp tục qua nhiều lần chạy.

Ví dụ quy trình xử lý đơn hàng:

1. Nhận yêu cầu tạo đơn.
2. Kiểm tra tồn kho.
3. Giữ hoặc xác nhận thanh toán.
4. Chờ người quản lý phê duyệt nếu đơn vượt ngưỡng.
5. Tạo lệnh giao hàng.
6. Gửi thông báo hoàn tất.

Mỗi bước có thể chạy trong một Java function riêng hoặc một activity của workflow engine. Giữa các bước, workflow có thể chờ vài phút hoặc vài ngày.

Do đó:

- Dừng function không tự động hủy workflow.
- Hủy workflow không tự động hoàn tác payment hoặc shipment đã được tạo.
- Retry một activity không có nghĩa chạy lại toàn bộ workflow từ đầu.
- Hết thời gian chờ cần một transition bền vững, không chỉ là một thread sleep kết thúc.
- Một message cancellation hoặc timer event có thể được giao lặp.

Workflow cần có execution ID, state, current step, deadline, attempt metadata và lịch sử transition để phục hồi sau khi runtime bị thay thế.

## 2. Mô hình trạng thái và kết quả kết thúc

Nên phân biệt trạng thái đang chạy, trạng thái chờ, trạng thái đang xử lý yêu cầu hủy và trạng thái terminal.

Một state model tham khảo:

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> WAITING
    WAITING --> RUNNING
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> RUNNING
    RUNNING --> CANCEL_REQUESTED
    WAITING --> CANCEL_REQUESTED
    RETRY_WAIT --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> COMPENSATING
    COMPENSATING --> CANCELLED
    COMPENSATING --> COMPENSATION_FAILED
    TIMED_OUT --> COMPENSATING
    COMPENSATING --> TIMED_OUT
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    WAITING --> TIMED_OUT
    RUNNING --> TIMED_OUT
~~~

Ý nghĩa:

| Trạng thái | Ý nghĩa |
|---|---|
| RUNNING | Workflow đang thực hiện một bước |
| WAITING | Đang chờ timer, callback hoặc tín hiệu bên ngoài |
| RETRY_WAIT | Một bước thất bại tạm thời và đang chờ lần thử tiếp |
| CANCEL_REQUESTED | Đã nhận yêu cầu hủy, cần dừng hoặc phối hợp bước đang chạy |
| COMPENSATING | Đang hoàn tác các tác dụng phụ có thể bù trừ |
| SUCCEEDED | Các bước bắt buộc đã hoàn tất |
| FAILED | Workflow thất bại theo policy |
| CANCELLED | Hủy hoàn tất theo contract |
| TIMED_OUT | Deadline hoặc thời hạn chờ đã hết |
| COMPENSATION_FAILED | Không hoàn tất được bù trừ; cần reconciliation hoặc can thiệp |

Có thể lưu terminal reason riêng, ví dụ USER_CANCELLED, APPROVAL_EXPIRED hoặc WORKFLOW_DEADLINE. Nhờ vậy hệ thống không cần tạo một trạng thái mới cho mọi nguyên nhân kết thúc.

Một workflow không nên được đánh dấu CANCELLED ngay khi API nhận yêu cầu hủy nếu payment hoặc shipment vẫn đang chạy. Trạng thái CANCEL_REQUESTED cho biết yêu cầu đã được ghi nhận; trạng thái terminal chỉ được đặt khi workflow đã đạt điều kiện kết thúc theo contract.

Nếu deadline hết và workflow không có side effect cần bù trừ, có thể chuyển thẳng sang TIMED_OUT. Nếu cần compensation, giữ terminal reason là WORKFLOW_DEADLINE, chuyển qua COMPENSATING rồi mới kết thúc ở TIMED_OUT. Nếu compensation thất bại, dùng COMPENSATION_FAILED và giữ nguyên terminal reason để reconciliation biết workflow timeout vì lý do nào.

## 3. Thiết kế dữ liệu workflow để kiểm thử

Một bảng execution có thể lưu:

~~~sql
CREATE TABLE workflow_executions (
    workflow_id          VARCHAR(128) PRIMARY KEY,
    tenant_id            VARCHAR(128) NOT NULL,
    workflow_type        VARCHAR(128) NOT NULL,
    workflow_version     VARCHAR(64) NOT NULL,
    status               VARCHAR(32) NOT NULL,
    current_step         VARCHAR(128) NULL,
    terminal_reason      VARCHAR(64) NULL,
    version              BIGINT NOT NULL DEFAULT 0,
    cancel_requested_at  TIMESTAMP NULL,
    deadline_at          TIMESTAMP NULL,
    created_at           TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL,
    completed_at         TIMESTAMP NULL
);
~~~

Lịch sử transition nên được lưu riêng để điều tra:

~~~sql
CREATE TABLE workflow_history (
    history_id       VARCHAR(128) PRIMARY KEY,
    workflow_id      VARCHAR(128) NOT NULL,
    from_status      VARCHAR(32) NULL,
    to_status        VARCHAR(32) NOT NULL,
    step_name        VARCHAR(128) NULL,
    reason_code      VARCHAR(64) NULL,
    attempt          INTEGER NULL,
    occurred_at      TIMESTAMP NOT NULL,
    correlation_id   VARCHAR(128) NULL
);
~~~

Bảng wait có thể lưu token và deadline:

~~~sql
CREATE TABLE workflow_waits (
    wait_id          VARCHAR(128) PRIMARY KEY,
    workflow_id      VARCHAR(128) NOT NULL,
    wait_token       VARCHAR(128) NOT NULL,
    wait_type        VARCHAR(64) NOT NULL,
    status           VARCHAR(24) NOT NULL,
    expires_at       TIMESTAMP NOT NULL,
    completed_at     TIMESTAMP NULL,
    UNIQUE (workflow_id, wait_token)
);
~~~

Các schema trên là ví dụ quan hệ. Nếu dùng workflow engine managed, engine có thể lưu execution history và timer state thay cho các bảng này. Dù vậy, ứng dụng vẫn cần định danh business operation và lưu các trạng thái ngoài engine khi có yêu cầu tra cứu hoặc đối soát.

## 4. Cancellation là yêu cầu, không phải nút tắt process

Một API có thể cho caller yêu cầu hủy:

~~~http
POST /v1/workflows/wf-918/cancel
Authorization: Bearer <access-token>
Idempotency-Key: cancel-req-72
Content-Type: application/json

{
  "reason": "customer_request"
}
~~~

Response có thể là:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "workflowId": "wf-918",
  "status": "CANCEL_REQUESTED"
}
~~~

202 có nghĩa hệ thống đã nhận yêu cầu và sẽ xử lý; không khẳng định tất cả side effect đã được hoàn tác. Nếu workflow đã terminal, API nên trả kết quả hiện tại theo contract, ví dụ SUCCEEDED hoặc CANCELLED, thay vì giả vờ hủy thành công.

Cancellation command cần:

- Xác thực caller và quyền trên workflow.
- Ghi nhận yêu cầu bằng transaction.
- Dùng idempotency key để caller retry không tạo nhiều yêu cầu.
- Kiểm tra trạng thái terminal.
- Phát tín hiệu cho worker hoặc workflow engine.
- Trả trạng thái rõ ràng để caller polling hoặc nhận callback.

Không dùng thao tác kill process như cơ chế cancellation nghiệp vụ. Runtime có thể dừng function, nhưng điều đó không biết cần void payment, giải phóng inventory hay thông báo cho đối tác.

## 5. Cancellation hợp tác trong Java

Một worker đang thực hiện bước dài cần kiểm tra cancellation tại các điểm an toàn. Có thể dùng token nội bộ:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean(false);

    public void requestCancellation() {
        requested.set(true);
    }

    public boolean isCancellationRequested() {
        return requested.get();
    }

    public void throwIfCancellationRequested() {
        if (isCancellationRequested()) {
            throw new WorkflowCancellationException();
        }
    }
}
~~~

Ví dụ trong một bước xử lý nhiều phần:

~~~java
public void processOrder(
        Order order,
        CancellationToken cancellation) {

    validateOrder(order);
    cancellation.throwIfCancellationRequested();

    reserveInventory(order);
    cancellation.throwIfCancellationRequested();

    authorizePayment(order);
    cancellation.throwIfCancellationRequested();

    createShipmentRequest(order);
}
~~~

Đây chỉ là cancellation token trong một execution environment. Serverless function có thể bị dừng đột ngột và token trong memory không tồn tại sau restart. Vì vậy, nguồn sự thật phải là trạng thái bền vững trong workflow engine/database; worker cần đọc hoặc nhận cancellation signal từ nguồn đó.

Không kiểm tra cancellation giữa một cặp thao tác không thể tách rời nếu điều đó để lại trạng thái nghiệp vụ không nhất quán. Đặt checkpoint tại ranh giới an toàn sau khi side effect đã được ghi nhận.

## 6. Cancellation race với hoàn tất

Một race phổ biến:

- Worker đang hoàn tất bước cuối.
- Caller gửi cancellation cùng lúc.
- Hai transaction cùng cố chuyển workflow sang terminal state.

Chỉ một transition được thắng. Dùng optimistic version hoặc conditional update:

~~~sql
UPDATE workflow_executions
SET status = 'CANCEL_REQUESTED',
    cancel_requested_at = CURRENT_TIMESTAMP,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workflow_id = ?
  AND version = ?
  AND status IN ('RUNNING', 'WAITING', 'RETRY_WAIT');
~~~

Nếu số row cập nhật bằng 0, trạng thái đã thay đổi hoặc version không còn mới. Đọc lại execution và quyết định trả trạng thái hiện tại.

Transition thành công cũng cần điều kiện:

~~~sql
UPDATE workflow_executions
SET status = 'SUCCEEDED',
    completed_at = CURRENT_TIMESTAMP,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workflow_id = ?
  AND version = ?
  AND status = 'RUNNING'
  AND cancel_requested_at IS NULL;
~~~

Nếu cancellation thắng trước, worker không thể ghi SUCCEEDED bằng version cũ. Nếu success đã commit trước, cancellation phải trả kết quả đã hoàn tất.

Không chỉ kiểm tra trạng thái trong Java rồi mới update; check và transition phải atomic tại database hoặc được workflow engine tuần tự hóa.

## 7. Bù trừ side effect bằng Saga

Cancellation không thể xóa lịch sử của các hệ thống bên ngoài. Nếu workflow đã giữ hàng, authorize payment hoặc tạo shipment, cần các hành động bù trừ.

Ví dụ Saga:

| Bước đã thực hiện | Hành động bù trừ có thể có |
|---|---|
| Reserve inventory | Release reservation |
| Authorize payment | Void authorization |
| Capture payment | Refund payment nếu contract cho phép |
| Create shipment | Cancel shipment hoặc yêu cầu carrier intercept |
| Send notification | Thường không thể thu hồi; gửi thông báo đính chính nếu cần |

Bù trừ không phải rollback database. Đó là một business action mới, có thể thất bại và cần retry riêng.

~~~mermaid
flowchart TD
    A[Reserve inventory] --> B[Authorize payment]
    B --> C[Wait for approval]
    C -->|Approved| D[Create shipment]
    C -->|Cancelled / expired| X[Start compensation]
    D --> E[Workflow succeeded]
    X --> F[Void payment authorization]
    F --> G[Release inventory]
    G --> H[Mark cancelled or timed out]
~~~

Thứ tự bù trừ thường đảo ngược các bước đã hoàn thành, nhưng thứ tự thực tế phải dựa trên dependency nghiệp vụ. Nếu payment đã capture, refund có thể là asynchronous và không thể hoàn tất ngay.

Mỗi compensation action phải idempotent. Nếu worker crash sau khi provider thực hiện refund nhưng trước khi workflow ghi nhận kết quả, lần retry không được refund lần hai.

## 8. Phân biệt retry, compensation và replay

Ba hành động này có mục đích khác nhau:

- **Retry:** thực hiện lại cùng một bước sau lỗi tạm thời.
- **Compensation:** tạo hành động nghiệp vụ để bù trừ side effect của bước đã thành công.
- **Replay:** chạy lại lịch sử hoặc một phần workflow theo mục đích vận hành, thường cần kiểm soát version và idempotency.

Ví dụ payment authorization trả 503 trước khi có kết quả: retry có thể phù hợp nếu dùng cùng provider idempotency key hoặc tra cứu operation. Nếu payment đã authorize nhưng khách hàng hủy đơn: thực hiện void authorization là compensation, không retry authorization. Nếu cần rebuild một projection từ lịch sử event: đó là replay và cần namespace/target phù hợp.

Không dùng retry để thay thế compensation. Không replay toàn bộ workflow để xử lý một bước lỗi nếu các side effect trước đó đã xảy ra.

## 9. Phân loại lỗi trước khi retry

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Transient | Network reset, 503 tạm thời, throttling | Retry có giới hạn |
| Permanent | Input invalid, business rule từ chối | Dừng và chuyển FAILED |
| Authorization | 401/403 do identity hoặc policy | Không retry cùng credential |
| Conflict | Optimistic lock hoặc trạng thái thay đổi | Đọc state mới; retry có điều kiện |
| Ambiguous outcome | Timeout sau khi provider có thể đã xử lý | Tra cứu operation hoặc retry với idempotency key |
| Deadline exceeded | Không còn đủ thời gian cho lần thử mới | Dừng retry và kết thúc/reconcile |
| Cancellation | Caller đã yêu cầu hủy | Không retry bước bị hủy; chạy compensation nếu cần |

HTTP status chỉ là một tín hiệu. Ví dụ 429 thường cần tôn trọng Retry-After; 500 có thể do bug cố định và không nên retry vô hạn. Error classifier phải dựa trên contract của từng dependency.

## 10. Exponential backoff, jitter và giới hạn retry

Một retry policy thường có:

- Max attempts, bao gồm lần gọi đầu.
- Initial delay.
- Multiplier.
- Maximum delay.
- Maximum elapsed time.
- Per-attempt timeout.
- Retryable error classifier.
- Jitter.
- Overall workflow deadline.

Công thức exponential backoff:

~~~text
cap(n) = min(maxDelay, initialDelay × multiplier^(n - 1))
actualDelay(n) = random(0, cap(n))
~~~

Full jitter giúp nhiều workflow không retry cùng thời điểm. Nếu provider trả Retry-After, không retry sớm hơn thời gian provider yêu cầu.

Ví dụ:

| Attempt | Backoff cap | Delay ngẫu nhiên |
|---:|---:|---:|
| 1 | 200 ms | 0–200 ms |
| 2 | 400 ms | 0–400 ms |
| 3 | 800 ms | 0–800 ms |
| 4 | 1.600 ms | 0–1.600 ms |
| 5 | 2.000 ms | 0–2.000 ms |

Sau max attempts, workflow chuyển sang trạng thái xử lý lỗi, DLQ hoặc compensation theo loại bước. Không giữ function sống chỉ để sleep hàng phút; dùng durable timer, queue delay hoặc workflow engine.

## 11. Retry theo từng bước, không chạy lại toàn workflow

Workflow có checkpoint và state bền vững. Nếu bước gửi email thất bại sau khi payment và shipment đã thành công, không được chạy lại payment và shipment.

Lưu step execution:

~~~sql
CREATE TABLE workflow_steps (
    workflow_id       VARCHAR(128) NOT NULL,
    step_name         VARCHAR(128) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    idempotency_key   VARCHAR(256) NOT NULL,
    next_attempt_at   TIMESTAMP NULL,
    last_error_code   VARCHAR(64) NULL,
    started_at        TIMESTAMP NULL,
    completed_at      TIMESTAMP NULL,
    PRIMARY KEY (workflow_id, step_name)
);
~~~

Khi retry:

1. Đọc workflow và step state.
2. Xác nhận workflow chưa cancelled/terminal/deadline exceeded.
3. Claim đúng step bằng version/lease.
4. Dùng cùng idempotency key cho cùng logical operation.
5. Gọi dependency với timeout còn lại.
6. Lưu kết quả và transition step trong transaction.
7. Chỉ chuyển sang bước tiếp theo khi step đã commit thành công.

Nếu workflow engine managed đã hỗ trợ retry per-state, tránh bọc thêm retry loop không giới hạn trong Java activity. Tính tổng số attempt giữa engine và HTTP client để không nhân request ngoài dự kiến.

## 12. Idempotency cho side effect và compensation

Retry có thể gọi lại một operation đã thành công nhưng response bị mất. Vì vậy mỗi side effect cần một identity ổn định.

Ví dụ key:

~~~text
workflowId + stepName + businessOperationVersion
~~~

Cùng logical operation phải dùng cùng key ở mọi attempt. Với compensation, dùng key riêng nhưng ổn định, ví dụ workflowId + compensatePaymentAuthorization.

Các nguyên tắc:

- Gửi provider idempotency key nếu API hỗ trợ.
- Lưu provider request ID và outcome.
- Dùng unique constraint trong database cho business operation.
- Nếu outcome không rõ, tra cứu trước khi tạo operation mới.
- Không tạo key mới mỗi lần retry.
- Giữ record đủ lâu bao phủ retry, redrive và reconciliation window.

Idempotency ngăn side effect trùng trong phạm vi contract của provider. Nó không tự đảm bảo exactly-once giữa nhiều hệ thống.

## 13. Wait state và durable timer

Workflow có thể cần chờ:

- Người quản lý duyệt đơn.
- Khách hàng xác nhận.
- Đối tác gửi webhook.
- Đến thời điểm giao hàng.
- Một khoảng delay trước lần retry.
- Một sự kiện khác xuất hiện.

Không dùng Thread.sleep hoặc giữ function invocation mở trong thời gian chờ dài. Ghi wait state bền vững và để workflow engine/timer service đánh thức execution.

Một wait record cần có:

- workflow ID.
- wait token duy nhất.
- wait type.
- created_at và expires_at.
- trạng thái WAITING/COMPLETED/EXPIRED/CANCELLED.
- correlation ID cho callback.
- version/fencing token nếu có nhiều consumer.

Timer event có thể đến trễ hoặc lặp. Handler phải kiểm tra wait token và trạng thái hiện tại trước khi thực hiện transition.

## 14. Hết hạn chờ khác timeout của function

Các khái niệm này cần tách biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Function timeout | Giới hạn thời gian một invocation được chạy |
| Step timeout | Giới hạn thời gian một activity/bước được phép thực hiện |
| Wait expiry | Thời hạn chờ callback/tín hiệu |
| Workflow deadline | Hạn cuối cho toàn bộ tiến trình nghiệp vụ |
| Lease expiry | Thời điểm quyền claim một công việc hết hạn |
| Queue visibility/ack deadline | Thời gian message tạm không được giao lại hoặc phải được acknowledge theo provider |

Function timeout không nên tự động được hiểu là workflow timeout. Một worker có thể timeout nhưng workflow vẫn còn deadline và có thể retry. Wait expiry có thể xảy ra khi không có function nào đang chạy. Workflow deadline bao trùm thời gian chạy, retry và chờ.

Đặt các mốc thời gian nhất quán. Ví dụ tổng workflow deadline là 24 giờ; thời gian chờ phê duyệt là 4 giờ; mỗi activity có timeout 30 giây và tối đa 4 attempts. Không để retry kéo dài vượt deadline workflow.

## 15. Xử lý callback đến muộn và timer trùng

Giả sử workflow chờ approval đến 17:00. Callback approved đến lúc 17:02, sau khi wait đã hết hạn. Không nên tự động chấp nhận callback muộn nếu business rule đã chuyển workflow sang compensation hoặc terminal timeout.

Callback nên chứa:

~~~json
{
  "workflowId": "wf-918",
  "waitToken": "approval-7f2",
  "eventId": "approval-event-31",
  "decision": "APPROVED",
  "occurredAt": "2026-11-17T16:58:00Z"
}
~~~

Handler kiểm tra:

- Caller có quyền gửi callback cho workflow này.
- waitToken khớp wait hiện tại.
- eventId chưa được xử lý.
- Workflow vẫn ở trạng thái WAITING.
- Thời điểm nhận theo clock tin cậy chưa vượt expires_at.
- Callback thuộc đúng tenant và approval request.

Dùng một transaction/conditional update để callback và timer expiry tranh quyền transition. Chỉ một bên thắng. Bên thua đọc state hiện tại và ghi nhận late/duplicate signal, không chạy side effect lần nữa.

### Quy tắc biên thời gian

Cần định nghĩa chính xác callback có hợp lệ khi received_at nhỏ hơn hay bằng expires_at. Ví dụ chọn:

~~~text
callback accepted when database_received_at < expires_at
wait expired when database_now >= expires_at
~~~

Dùng clock của database hoặc workflow engine thay vì clock tùy ý của từng worker. Scheduler có thể phát timer trễ; handler vẫn phải kiểm tra expires_at và không dựa vào thời điểm message timer đến.

## 16. Java: tính delay retry có thể kiểm thử

Để test jitter không cần chờ thật, tách phép tính delay khỏi phần sleep và inject nguồn random.

~~~java
import java.time.Duration;
import java.util.random.RandomGenerator;

public record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay,
        Duration maxElapsed) {

    public RetryPolicy {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }
        if (initialDelay == null || initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay == null
                || maxDelay.compareTo(initialDelay) < 0
                || maxElapsed == null
                || maxElapsed.isNegative()
                || maxElapsed.isZero()) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
    }
}

public final class RetryDelay {

    private RetryDelay() {}

    public static Duration fullJitter(
            RetryPolicy policy,
            int failedAttempt,
            RandomGenerator random) {

        if (failedAttempt < 1
                || failedAttempt >= policy.maxAttempts()) {
            throw new IllegalArgumentException("Invalid failed attempt");
        }

        long initial = policy.initialDelay().toMillis();
        long maximum = policy.maxDelay().toMillis();
        long cap = initial;

        for (int i = 1; i < failedAttempt && cap < maximum; i++) {
            cap = cap > maximum / 2 ? maximum : cap * 2;
        }

        cap = Math.min(cap, maximum);
        long delay = random.nextLong(cap + 1);
        return Duration.ofMillis(delay);
    }
}
~~~

Đoạn code chỉ tính delay; workflow engine hoặc scheduler chịu trách nhiệm tạo timer bền vững. Không gọi Thread.sleep để chờ dài trong function. Cần kiểm tra duration không vượt deadline còn lại trước khi lên lịch attempt tiếp theo.

Unit test có thể inject random generator giả luôn trả giá trị biên để xác minh delay bằng 0 và bằng cap. Có thể dùng fake clock để kiểm tra maxElapsed mà không chờ thời gian thực.

## 17. Java: transition cancellation có điều kiện

Một command service nên cập nhật state theo điều kiện thay vì đọc rồi ghi không khóa.

~~~java
public enum CancelResult {
    ACCEPTED,
    ALREADY_REQUESTED,
    ALREADY_TERMINAL,
    NOT_FOUND
}

public final class WorkflowCancellationService {

    private final WorkflowRepository repository;

    public WorkflowCancellationService(
            WorkflowRepository repository) {
        this.repository = repository;
    }

    public CancelResult requestCancel(
            String workflowId,
            String tenantId,
            String reason,
            String idempotencyKey) {

        var result = repository.requestCancellation(
                workflowId, tenantId, reason, idempotencyKey);

        return result;
    }
}
~~~

Repository cần thực hiện conditional update và ghi outbox trong cùng transaction. Một dispatcher riêng đọc outbox và gửi signal có thể retry. Nếu publish thất bại sau khi transaction commit, cancellation vẫn được lưu và dispatcher sẽ gửi lại; API không phụ thuộc vào một network call nằm ngoài transaction.

Ví dụ này không chứa chi tiết SQL vì repository phụ thuộc database. Contract quan trọng là trạng thái và outbox commit nguyên tử; signal không được chỉ tồn tại trong memory của API function.

## 18. Kiểm thử cancellation

Kiểm thử cần xác minh cả trạng thái và side effect.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hủy workflow chưa bắt đầu | Không chạy step tiếp theo; chuyển CANCELLED theo policy |
| Hủy khi WAITING | Timer/callback cũ không thể tiếp tục workflow |
| Hủy khi activity đang chạy | Ghi CANCEL_REQUESTED; activity dừng tại checkpoint an toàn |
| Hủy sau reserve inventory | Release reservation đúng một lần |
| Hủy sau payment authorization | Void authorization hoặc ghi trạng thái cần reconciliation |
| Hủy sau payment capture | Chạy refund theo policy; không giả định rollback |
| Hủy sau khi shipment tạo | Gọi cancel/intercept nếu khả thi; lưu outcome |
| Hủy hai lần cùng key | Idempotent, không tạo hai compensation |
| Hủy đồng thời với success | Chỉ một terminal transition thắng |
| Hủy khi workflow đã terminal | Trả trạng thái hiện tại, không đổi lịch sử |
| Worker crash sau khi nhận cancel | Workflow vẫn giữ CANCEL_REQUESTED và được worker khác tiếp tục |
| Compensation thất bại | COMPENSATION_FAILED hoặc trạng thái cần xử lý thủ công |

Cần kiểm tra không có bước mới nào được khởi chạy sau khi cancellation đã thắng transition. Nếu activity không thể dừng ngay, phải xác minh nó không ghi đè terminal state và compensation/reconciliation vẫn được kích hoạt.

## 19. Kiểm thử retry

| Kịch bản | Kết quả mong đợi |
|---|---|
| Thành công attempt đầu | Không retry |
| Transient error rồi thành công | Chỉ retry step lỗi |
| Permanent error | Dừng ngay, chuyển FAILED |
| Đạt max attempts | Không có attempt dư |
| Hết max elapsed | Không lên lịch attempt mới |
| Backoff đạt cap | Delay không vượt maxDelay |
| Full jitter | Delay nằm trong khoảng 0..cap |
| Retry-After | Không thử lại sớm hơn thời điểm provider yêu cầu |
| Timeout sau side effect | Cùng idempotency key hoặc tra cứu provider trước retry |
| Worker crash sau provider success | Recovery không tạo side effect trùng |
| Retry lồng nhiều tầng | Tổng attempts bị giới hạn và đo được |
| Compensation lỗi transient | Retry compensation độc lập với forward step |
| Workflow đã cancel | Không retry forward action |
| Workflow deadline đã hết | Không bắt đầu attempt mới |

Test phải xác minh attempt count, state history, next_attempt_at và số lần gọi dependency. Chỉ kiểm tra cuối cùng workflow SUCCEEDED là chưa đủ; có thể có nhiều request thừa hoặc side effect trùng trước khi đạt kết quả.

## 20. Kiểm thử wait expiry và callback

| Kịch bản | Kết quả mong đợi |
|---|---|
| Callback đến trước deadline | WAITING chuyển sang RUNNING/next state |
| Callback đến đúng ranh giới | Tuân theo quy tắc < hoặc <= đã công bố |
| Callback đến sau deadline | Không tiếp tục workflow; ghi late signal |
| Timer đến đúng hạn | Wait chuyển EXPIRED và workflow xử lý timeout |
| Timer đến trễ | Vẫn expire dựa trên expires_at |
| Timer giao hai lần | Chỉ một transition thành công |
| Callback gửi hai lần | Event ID deduplicate |
| Callback và timer đồng thời | Một transaction thắng; bên còn lại không tạo side effect |
| Wait đã bị cancel | Callback/timer cũ không làm sống lại workflow |
| Timer của wait token cũ | Bị bỏ qua |
| Scheduler outage | Reconciliation tìm wait đã quá hạn và xử lý bù |
| Clock worker lệch | Quyết định vẫn dựa trên clock tin cậy của DB/engine |

### Kiểm thử không phụ thuộc sleep thật

Dùng fake clock hoặc workflow test harness để tiến thời gian đến ngay trước, đúng tại và ngay sau deadline. Điều này nhanh, ổn định và cho phép test các race condition mà không phải chờ nhiều phút hoặc nhiều giờ.

## 21. Race condition cần chủ động tạo

Một số lỗi chỉ xuất hiện khi tín hiệu đến đồng thời:

- Cancel command và success event.
- Timer expiry và approval callback.
- Hai retry worker cùng claim một step.
- Lease hết hạn khi worker cũ vẫn đang chạy.
- Compensation retry và workflow redrive.
- Provider response đến sau khi caller timeout.
- Duplicate event trong lúc database failover.

Có thể dùng barrier/latch trong integration test để đồng bộ hai thread, sau đó kiểm tra database state và số lần side effect. Trong test serverless integration, gửi hai message cùng workflow ID vào hai execution environment và xác minh conditional update/unique constraint hoạt động.

Không dùng sleep ngẫu nhiên để hy vọng tạo race. Hãy tạo điểm đồng bộ có chủ đích để test lặp lại được.

## 22. Kiểm thử durable workflow sau restart

Một workflow phải phục hồi từ trạng thái đã lưu khi function hoặc worker bị dừng.

Kiểm thử:

1. Bắt đầu workflow và hoàn tất một vài step.
2. Để workflow ở WAITING hoặc RETRY_WAIT.
3. Dừng process/worker hoặc kết thúc invocation.
4. Khởi động worker mới.
5. Khôi phục execution từ state store/workflow engine.
6. Xác minh step đã hoàn tất không chạy lại side effect.
7. Xác minh timer và retry schedule vẫn còn.
8. Xác minh cancellation signal chưa xử lý vẫn được tiếp tục.

Nếu state chỉ nằm trong Java heap, workflow sẽ mất khi execution environment bị thay thế. Durable state phải tồn tại ngoài process.

## 23. Provider workflow engines

Các nền tảng có dịch vụ điều phối riêng, nhưng semantics cụ thể khác nhau:

| Nền tảng | Dịch vụ thường dùng | Khả năng cần kiểm tra |
|---|---|---|
| AWS | Step Functions, Lambda, EventBridge | Retry/Catch, timeout, wait state, callback task token, execution history |
| Google Cloud | Workflows, Cloud Run functions, Pub/Sub | Retry policy, callback/call semantics, execution deadline, event delivery |
| Azure | Durable Functions, Azure Functions, Service Bus | Durable timer, external event, orchestration replay, retry và cancellation behavior |
| Framework độc lập | Temporal hoặc workflow engine tương đương | Durable timer, activity retry, cancellation scope, compensation và history |

Không giả định một API cancel có semantics giống nhau giữa các engine. Một số engine có thể đánh dấu execution cancelled trong khi activity bên ngoài vẫn tiếp tục cho đến khi nhận cancellation signal hoặc timeout. Đọc tài liệu phiên bản đang triển khai và kiểm thử adapter cụ thể.

### Workflow replay và deterministic code

Một số durable engine replay lịch sử orchestration để tái dựng state. Code orchestration cần tuân theo yêu cầu deterministic của engine; không gọi trực tiếp random, current time hoặc network trong phần orchestration nếu engine yêu cầu các thao tác đó đi qua activity/API được hỗ trợ. Đặt side effect trong activity có idempotency.

## 24. Quan sát cancellation, retry và expiry

Metric và log nên phân biệt ba nhóm:

**Cancellation**
- Cancel requests accepted/rejected.
- Thời gian từ CANCEL_REQUESTED đến terminal.
- Số compensation thành công/thất bại.
- Workflow bị cancel nhưng activity còn chạy.
- Số cancellation race với success.

**Retry**
- Attempts theo step và error class.
- Retry success rate.
- Exhausted attempts.
- Backoff delay và remaining deadline.
- Retry amplification theo dependency.

**Wait expiry**
- Số wait đang mở.
- Wait age và expired count.
- Timer delivery lag.
- Late callback count.
- Duplicate timer/callback count.
- Wait bị stuck sau scheduler outage.

Log nên chứa workflowId, stepName, attempt, waitToken hoặc signal ID đã được kiểm soát, transition version và correlation ID. Không đưa token bí mật hoặc payload nhạy cảm vào log. Metric label phải có cardinality thấp; workflow ID dùng trong log/trace.

## 25. Quy trình kiểm thử trong CI và môi trường tích hợp

Một bộ test hiệu quả có nhiều lớp:

1. **Unit tests:** classifier, backoff, transition guard và deadline math.
2. **State-machine tests:** mọi transition hợp lệ và transition bị cấm.
3. **Repository integration tests:** conditional update, transaction, unique constraint và outbox.
4. **Workflow engine tests:** durable timer, retry, callback và cancellation semantics.
5. **Provider contract tests:** HTTP status, Retry-After, callback signature và provider request lookup.
6. **Fault injection:** crash trước/sau side effect, timeout, duplicate delivery và dependency outage.
7. **Concurrency tests:** cancel/success, callback/expiry và double claim.
8. **Recovery tests:** restart worker, scheduler outage, DLQ redrive và reconciliation.

Trong CI, unit/state-machine tests chạy nhanh ở mọi pull request. Integration test với provider thật hoặc emulator chạy ở pipeline phù hợp, dùng account/project test và budget giới hạn. Không dùng payment hoặc shipment production để kiểm thử compensation.

## 26. Những lỗi kiểm thử thường gặp

- **Chỉ test happy path:** không phát hiện cancel/retry/expiry race; tạo test failure window.
- **Coi invocation timeout là workflow cancel:** state có thể vẫn RUNNING; phân biệt hai lifecycle.
- **Đánh dấu CANCELLED ngay khi nhận yêu cầu:** side effect có thể chưa được bù trừ; dùng CANCEL_REQUESTED.
- **Retry toàn workflow:** payment hoặc shipment có thể chạy lặp; retry theo step/checkpoint.
- **Retry mọi exception:** lỗi permanent lặp vô ích; phân loại error.
- **Không có idempotency cho compensation:** refund hoặc release có thể chạy hai lần; dùng key riêng ổn định.
- **Dùng Thread.sleep cho wait dài:** giữ invocation và không durable; dùng timer/workflow wait.
- **Timer handler không kiểm tra wait token:** timer cũ có thể làm workflow tiến sai; kiểm tra token/version.
- **Chấp nhận callback muộn:** workflow đã timeout nhưng bị hồi sinh; kiểm tra deadline bằng clock tin cậy.
- **Dùng clock của từng worker:** clock skew gây quyết định khác nhau; dùng DB/engine time.
- **Không kiểm thử race:** hai transition terminal có thể cùng xảy ra; dùng conditional update.
- **Không test restart:** state trong memory mất; kiểm thử phục hồi từ durable store.
- **Chồng nhiều lớp retry:** attempts bị nhân lên; xác định retry owner và budget.
- **Không theo dõi compensation failure:** đơn hàng có thể ở trạng thái nghiệp vụ không nhất quán; alert và reconciliation.

## 27. Checklist thiết kế bài test

Trước khi đưa workflow vào production, xác minh:

- [ ] Mỗi workflow có execution ID, version và state bền vững.
- [ ] Cancellation command idempotent và được authorize.
- [ ] CANCEL_REQUESTED khác CANCELLED.
- [ ] Side effect đã xảy ra có compensation hoặc reconciliation plan.
- [ ] Compensation có idempotency key riêng.
- [ ] Retry classifier phân biệt transient, permanent và ambiguous outcome.
- [ ] Max attempts, max elapsed và workflow deadline được giới hạn.
- [ ] Retry chỉ chạy lại step cần thiết.
- [ ] Wait state dùng durable timer, không giữ function ngủ.
- [ ] Callback và timer có token/identity ổn định.
- [ ] Late callback và duplicate timer được xử lý.
- [ ] Race giữa cancellation, success và expiry được test.
- [ ] Restart không làm mất workflow state.
- [ ] Metric/log có thể giải thích transition và retry.
- [ ] Có reconciliation cho compensation hoặc activity không rõ kết quả.

## 28. Ghi nhớ

Workflow bị hủy, retry và hết hạn chờ là các transition nghiệp vụ có tác động đến side effect. Cancellation nên bắt đầu bằng CANCEL_REQUESTED, sau đó dừng an toàn và chạy compensation nếu cần. Không đồng nhất việc function invocation kết thúc với việc workflow đã bị hủy.

Retry cần phân loại lỗi, backoff có jitter, max attempts, max elapsed và deadline. Chỉ retry step lỗi; dùng idempotency cho forward action và compensation. Wait dài phải dùng durable timer, còn callback và timer cần token cùng conditional transition để xử lý duplicate, late arrival và race tại deadline.

Kiểm thử tốt phải tạo được các tình huống crash, duplicate, callback trễ, timer trùng, cancel/success đồng thời và worker restart bằng fake clock cùng fault injection. Khi trạng thái được lưu bền vững, transition có điều kiện và side effect có idempotency, Java serverless workflow có thể phục hồi đúng sau lỗi mà không lặp tác dụng phụ hoặc hồi sinh một tiến trình đã kết thúc.


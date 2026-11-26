# Reject hoặc delay request mới trong Spring Batch

## 1. Khi thêm request chỉ làm hệ thống chậm và dễ lỗi hơn

Một dịch vụ dữ liệu chạy Spring Batch nhận lệnh xử lý file từ API và scheduler. Bình thường bốn worker có thể hoàn tất khoảng 40 file/phút. Khi đối tác gửi đột ngột 1.500 file, manager tiếp tục khởi chạy job, mỗi job tạo nhiều partition và worker cố đọc/ghi PostgreSQL. Số connection đang dùng chạm trần, lock wait tăng, hàng đợi broker kéo dài, retry nối tiếp retry. Sau 20 phút, ít file hoàn tất hơn khi hệ thống chỉ nhận một lượng công việc vừa sức.

Ở thời điểm đó, câu hỏi quan trọng **không** phải “có thể tạo thêm bao nhiêu thread?” mà là:

> **Khi hệ thống đã đến giới hạn an toàn, một request mới nên bị từ chối ngay hay được nhận để xử lý trễ hơn? Ai chịu trách nhiệm bảo đảm request không mất hoặc không chạy hai lần?**

Đó là bài toán **admission control** và **backpressure**.

Bài **“Reject hoặc delay request mới”** thuộc chương **Backpressure** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module giúp mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán; người học đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế.

Sau bài, bạn có thể:

1. Phân biệt **reject**, **delay**, **queue**, **throttle**, **retry** và **pause consumer**.
2. Chọn chính sách cho API, scheduler, manager, partition handler, worker và broker theo cùng một ngân sách tài nguyên.
3. Trả HTTP `429/503` và `Retry-After` đúng nghĩa, không nhầm `202 Accepted` với `JobExecution.COMPLETED`.
4. Xây **bounded executor** và hiểu hạn chế của một semaphore/queue chỉ tồn tại trong một JVM.
5. Thiết kế **durable job-request queue** có idempotency key, lease, retry, expiry, dead-letter và fencing khi cần.
6. Áp backpressure cho remote partitioning/chunking mà không làm hỏng checkpoint hoặc xử lý trùng.
7. Đặt timeout, backoff/jitter, công bằng theo tenant và SLO về thời gian chờ.
8. Viết kiểm thử quá tải, crash, double submit và recovery với business reconciliation.

**Phiên bản ví dụ:** Java 17+, Spring Batch 5.2.x, Spring Boot 3.x, Spring JDBC, HikariCP và PostgreSQL. Có đoạn dành cho Spring Batch Integration/remote worker và broker; các API/behavior phụ thuộc phiên bản, transport và cấu hình triển khai. Nguyên tắc chung áp dụng cho Spring Batch 6.x, nhưng phải đối chiếu API và cách điều phối thực tế thay vì copy cấu hình 5.x không kiểm chứng.

## 2. Vì sao một queue không giới hạn không phải backpressure?

Giả sử phía gửi tạo request ở tốc độ `\lambda=100` request/giây, trong khi hệ thống chỉ hoàn tất `\mu=40` request/giây. Nếu vẫn chấp nhận mọi request:

\[
\Delta Q \approx (\lambda-\mu)\,\Delta t
\]

Sau 60 giây, backlog có thể tăng khoảng `(100-40)×60=3.600` request (ước lượng khi rate gần như ổn định và không có lỗi). Mỗi request còn chiếm metadata, memory, queue storage, message, log và thời gian quan sát.

~~~mermaid
flowchart LR
    A["Producer: 100 req/s"] --> Q["Unbounded queue +60 req/s"]
    Q --> M["Manager / dispatcher"]
    M --> W["Workers: 40 req/s"]
    W --> D[(Database / downstream)]
~~~

**Queue chỉ dịch chuyển thời điểm thực thi.** Nó không tạo ra năng lực xử lý mới. Nếu tốc độ nhận liên tục vượt tốc độ phục vụ, backlog, queue age và thời gian chờ tăng cho đến khi một tài nguyên khác cạn.

Trong hệ thống tương đối ổn định, định luật Little:

\[
L=\lambda W
\]

với `L` là số request trung bình trong hệ thống, `\lambda` throughput thực tế và `W` thời gian một request nằm trong hệ thống. Công thức mô tả quan hệ trung bình ở trạng thái ổn định; **không dùng để tính chính xác một burst, một queue đang tăng vô hạn hoặc hệ thống có retry storm**.

### Bốn kiểu phản ứng khi downstream không theo kịp

| Chiến lược | Hành vi | Khi nào phù hợp |
|---|---|---|
| **Reject immediately** | Không nhận công việc mới; trả lỗi tạm thời với hướng dẫn retry | Năng lực hết, request có thể gửi lại, không có durable queue được cam kết |
| **Accept and delay durably** | Ghi yêu cầu vào storage bền vững rồi trả receipt; xử lý sau | Công việc phải được giữ lại, chấp nhận queue wait và có cơ chế recovery |
| **Pause/throttle upstream** | Chậm nhận request/giảm polling/consumer concurrency hoặc hạn chế producer | Có thể điều khiển nguồn và không cần thải bỏ dữ liệu |
| **Shed lower-priority work** | Từ chối/hoãn các việc ít quan trọng theo SLA | Có các cấp ưu tiên minh bạch và giới hạn fairness |

**Một request bị từ chối không nên được ghi nhận là một job đã nhận.** Ngược lại, một request đã được chấp nhận để xử lý trễ cần có một **durable ownership record** và trạng thái có thể tra cứu ngay cả khi API process crash.

## 3. Ý nghĩa chính xác của reject, delay và retry

### 3.1. Reject: chưa nhận nghĩa vụ xử lý

Ví dụ một API nhận yêu cầu khởi chạy batch, hiện không còn capacity hoặc đã hết quota. API trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json

{"code":"ADMISSION_LIMIT","message":"Capacity temporarily unavailable"}
~~~

Response chỉ minh họa **protocol**. `Retry-After: 30` là gợi ý thử lại sau khoảng 30 giây, **không phải cam kết** hệ thống sẽ nhận ngay khi hết 30 giây. Client cần exponential backoff, jitter, retry budget và idempotency key.

Trong HTTP:

- `429 Too Many Requests` thường phù hợp khi một client/tenant vượt rate hoặc quota.
- `503 Service Unavailable` thường phù hợp khi service chung tạm không đủ capacity hoặc dependency outage; cũng có thể kèm `Retry-After`.
- `409 Conflict` phù hợp khi request mâu thuẫn với state/business rule, **không** thay thế `429` cho overload.
- `400/422` dùng cho dữ liệu không hợp lệ tùy API contract; **không** retry như lỗi tải.
- Với cùng idempotency key và **cùng nội dung**, ưu tiên trả receipt/trạng thái của yêu cầu trước nếu nó đã được nhận; đừng tạo job thứ hai chỉ vì client retry.

### 3.2. Delay: đã nhận nghĩa vụ, chưa thực thi

Một hệ thống có durable queue có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /batch-requests/8b2f...
Content-Type: application/json

{
  "requestId": "8b2f...",
  "state": "QUEUED",
  "message": "Accepted for later processing"
}
~~~

`202 Accepted` **không có nghĩa job đã `COMPLETED`**. Nó chỉ nên được trả sau khi yêu cầu đã được lưu/đăng hàng bền vững theo contract. API cần cung cấp endpoint xem trạng thái, cơ chế hủy nếu có và thời hạn/SLO dự kiến. Nếu durable persistence thất bại, không được trả `202` rồi giữ request chỉ trong JVM.

### 3.3. Retry: một lần cố gắng mới, không phải admission mới

Client retry cùng logical request cần **cùng idempotency key**. Nếu đã có receipt thì trả về receipt cũ hoặc trạng thái tương ứng, không tự tạo `JobInstance` mới. Worker retry một chunk hoặc broker redelivery là cơ chế **phục hồi execution đã nhận**, khác với client gửi **một job mới**.

**Không retry vô hạn:** nếu 100 worker cùng bị Hikari timeout rồi thử lại ngay, hàng chờ connection và DB lock chỉ tăng. Chọn bounded attempts, exponential backoff + jitter, retryable classification và quan sát DLQ/FAILED requests.

## 4. Chọn reject hay delay theo contract và tài nguyên

Không có một chính sách phù hợp cho mọi nhóm công việc:

| Bối cảnh | Nên ưu tiên | Ràng buộc cần ghi rõ |
|---|---|---|
| API preview không quan trọng, người gọi có thể retry | **Reject** khi quota/capacity hết | HTTP 429/503, Retry-After, idempotency |
| File kế toán bắt buộc phải xử lý | **Durable delay** trong budget | Receipt, queue TTL, alert nếu quá hạn, idempotent worker |
| Job chỉ có giá trị trước cutoff thời gian | Delay **có deadline** hoặc reject khi không còn cơ hội hoàn tất | Tránh trả 202 rồi hết hạn âm thầm |
| Scheduler chạy mỗi đêm, không muốn overlap | Delay lịch chạy mới hoặc coalesce theo business key | Phân biệt skip trùng lịch và bỏ mất business input |
| Một tenant tạo quá nhiều job | Rate limit/quota riêng tenant | Fairness, không cho tenant ấy chiếm toàn bộ queue |
| PostgreSQL bị lock/WAL/IO bão hòa | Giảm worker concurrency và hạn chế admission | Pool/DB telemetry, không chỉ CPU |
| Broker bị outage | Chỉ accept nếu lưu bền vững độc lập được | Outbox hoặc durable request table; nếu không, reject |
| Input nguồn phát được lại | Throttle producer hoặc pause poller | Offset/checkpoint/lease ownership đúng |

### 4.1. Ba điều kiện trước khi trả 202

1. **Persisted:** request và input reference/snapshot được ghi đủ bền vững để một process khác khôi phục.
2. **Discoverable:** có request ID/idempotency key để caller tra cứu sau timeout hoặc API crash.
3. **Recoverable:** một dispatcher/worker có thể nhận việc sau khi node chết; có deadline/retry/failure state và monitoring.

Nếu thiếu một điều kiện, đừng quảng bá “đã nhận chắc chắn” chỉ vì lệnh `executor.execute(...)` hoặc `messageChannel.send(...)` trả về thành công.

### 4.2. Hai cách delay rất khác nhau

~~~text
Delay trong memory:
HTTP -> ThreadPoolExecutor.queue -> worker task
       (process crash => queue mất)

Delay bền vững:
HTTP -> DB transactional acceptance/outbox -> committed receipt
     -> dispatcher/broker -> worker -> JobRepository/Business DB
       (process crash => hệ thống có thể phục hồi)
~~~

Memory queue có thể đủ cho tác vụ phụ không quan trọng, nhưng **không phải durable job queue**. Broker durable cũng cần xét message persistence, publisher confirms, ACK/redelivery, retention và cách kết nối với request record.

## 5. Đặt admission control ở đúng tầng

~~~mermaid
flowchart LR
    C[API clients / scheduler] --> A["Admission: quota, deadline, capacity"]
    A -->|Reject| R["429 / 503"]
    A -->|Durable accept| Q[(Request store / durable queue)]
    Q --> M["Manager dispatcher"]
    M --> P["Partition manager"]
    P --> B[(Request broker)]
    B --> W["Workers: bounded concurrency"]
    W --> D[(Business DB)]
    W --> J[(Shared JobRepository)]
    D --> H["Capacity signals / feedback"]
    J --> H
    H -.-> A
    H -.-> M
~~~

### 5.1. API edge/scheduler

Chịu trách nhiệm xác thực, idempotency, tenant quota, request deadline và quyết định **nhận nghĩa vụ hay từ chối**. Nếu scheduler nhận lịch nhưng không thể chạy ngay, cần lưu schedule request/receipt chứ không chỉ log “scheduled”.

### 5.2. Manager/job launcher

Giới hạn số `JobExecution` active, số manager partition steps, số partition requests in-flight và tần suất gửi vào broker. Một `JobLauncher` được gọi thành công **không có nghĩa còn capacity tại writer**. Nếu manager đã được chấp nhận nhưng chưa launch, giữ request ở trạng thái `QUEUED` thay vì tạo hàng nghìn `JobExecution` `STARTED` chỉ để chờ.

### 5.3. Worker/executor

Giới hạn số thread xử lý chunk/partition, queue nội bộ và các request đang chạy. Nếu executor reject một task của **job đã được nhận**, phải chuyển lỗi/requeue có kiểm soát về durable request lifecycle; **không được coi đó là reject của client ban đầu và bỏ quên partition**.

### 5.4. Broker/poller

Giới hạn consumer concurrency, prefetch/in-flight delivery và tốc độ dispatch/ack. Pause consumer hoặc giảm prefetch có thể giữ workload trong durable queue thay vì đẩy vào memory/DB. Nhưng đặc điểm `pause`/`nack`/`requeue` khác nhau giữa RabbitMQ, Kafka và JMS; kiểm tra phiên bản/adapter thực tế.

### 5.5. Database/business resource

Đo active connection, Hikari pending, JDBC acquire latency, DB CPU/IO/WAL, lock wait, transaction duration, retry/rollback. **Không dùng `CPU < 50%` làm chứng cứ có thể nhận thêm job**: bottleneck có thể là WAL/fsync, disk, hot rows, quota của API downstream hoặc broker.

## 6. Admission budget: bốn trần khác nhau

Một hệ thống cần phân biệt:

- **Active execution budget:** số job/partition/chunk đang chạy đồng thời.
- **In-flight message budget:** request đã phát vào transport nhưng chưa có kết quả/ACK theo contract.
- **Pending queue budget:** số request đã được nhận bền vững nhưng đang chờ.
- **Resource budget:** kết nối DB, CPU, heap, network, disk/WAL, downstream QPS.

Đặt `maxActive=8` không có nghĩa `maxQueue=8`; có thể cho 8 job chạy và 100 job chờ nếu có durable queue và deadline phù hợp. Nhưng điều đó **không** cho phép 100 active `JobExecution` đứng đợi ở worker không giới hạn.

### 6.1. Ví dụ ngân sách nhiều pod

Giả sử 6 worker pod, mỗi pod tối đa 4 partition executions, Hikari business pool max 10:

\[
E_{\mathrm{max}}\le 6\times4=24
\]

\[
C_{\mathrm{workerPools,max}}\le 6\times10=60
\]

Hai giá trị **khác nhau**. Một execution có thể dùng cursor connection và writer transaction connection tách biệt; `REQUIRES_NEW` hoặc metadata pool có thể dùng thêm. Phải tính manager, metadata DB, API pods, rolling surge và các service chung khi lập DB connection budget.

Nếu throughput không tăng từ 12 lên 24 executions vì database lock, **giảm execution budget** có thể làm throughput hiệu quả tăng và p95 latency giảm. Hàng đợi admission cần phản ánh năng lực bền vững, không lấy max thread count làm năng lực DB.

### 6.2. Rate limit và concurrency limit không thay thế nhau

Rate limit kiểu token bucket bảo vệ **lượng request mới mỗi giây/phút**. Concurrency limit bảo vệ **số công việc đang chiếm tài nguyên**. Hai job cùng được nhận trong một giây có thể chạy 2 giây và 2 giờ; rate limit đơn thuần không đảm bảo active jobs dưới ngưỡng.

| Loại giới hạn | Ví dụ | Bảo vệ điều gì |
|---|---|---|
| Token bucket | 10 requests/s, burst 20 | Tần suất và burst đầu vào |
| Semaphore | 4 active jobs per pod | Concurrent long-running work |
| Durable queue capacity | Tối đa 500 accepted QUEUED | Storage/queue age và lời hứa xử lý |
| Tenant quota | A tối đa 3 active, 30 queued | Fairness |
| Deadline/age | Không nhận job nếu không thể hoàn tất trước cutoff | SLO/giá trị kinh doanh |
| Consumer prefetch | Không giao quá nhiều request cho một consumer | Không tập trung in-flight trong một process |

Với nhiều pod, **một Semaphore Java trên mỗi pod không phải global limiter**; nếu muốn giới hạn toàn cụm, phải dùng shared coordinator/DB atomic claim, distributed rate limiter hoặc broker/worker scheduler có ownership rõ.

## 7. Reject ngay bằng bounded executor: ví dụ Java

Đối với việc **không cần durable acceptance**, có thể giới hạn task in-process bằng `ThreadPoolTaskExecutor`:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BoundedExecutorConfiguration {

    @Bean("batchWorkExecutor")
    public ThreadPoolTaskExecutor batchWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-work-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        return executor;
    }
}
~~~

Executor này có tối đa **4 task chạy** và **8 task chờ trong memory queue** ở một thời điểm điển hình. Khi saturated, `execute` có thể ném `TaskRejectedException` của Spring hoặc một `RejectedExecutionException` tùy lớp gọi. Tên pool, queue capacity và shutdown policy là giá trị **thí nghiệm**, không phải khuyến nghị cố định cho production.

Một cách wrap admission và chỉ nhận task nếu có slot:

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import org.springframework.core.task.TaskExecutor;

public final class LocalTaskAdmission {
    private final TaskExecutor executor;
    private final Semaphore inFlightSlots;

    public LocalTaskAdmission(TaskExecutor executor, int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.executor = executor;
        this.inFlightSlots = new Semaphore(maxInFlight);
    }

    public boolean trySubmit(Runnable task) {
        if (!inFlightSlots.tryAcquire()) {
            return false; // Không block request thread.
        }
        try {
            executor.execute(() -> {
                try {
                    task.run();
                } finally {
                    inFlightSlots.release();
                }
            });
            return true;
        } catch (RejectedExecutionException ex) {
            // Executor chưa nhận task, trả slot.
            inFlightSlots.release();
            return false;
        }
    }
}
~~~

`maxInFlight` phải phù hợp với số running + queued executor tasks; đừng tạo semaphore 1.000 slot trong khi executor queue 8 rồi tin có thể tiếp nhận 1.000 task. Với executor ở trên, có thể dùng `maxInFlight=12` nếu task **chỉ nằm trong process** và rủi ro mất queue được chấp nhận.

**Quan trọng về correctness:**

1. `trySubmit(true)` chỉ nghĩa executor process hiện tại **đã nhận task**, **không** phải business job đã được ghi durable hoặc đã hoàn tất.
2. `finally` giải phóng slot nếu task ném exception; application vẫn cần quan sát lỗi trong worker, không coi `trySubmit` thành công là job success.
3. Nếu executor/worker process crash sau khi nhận, task trong memory có thể mất.
4. Nếu dùng cùng code để gọi `JobLauncher` **bất đồng bộ**, slot có thể được nhả khi launcher trả về trong khi job vẫn đang chạy; phải giữ permit theo **lifecycle completion thực**, không theo dispatch completion.
5. `AbortPolicy` trả lỗi rõ; **`CallerRunsPolicy`** có thể vô tình đẩy job chạy trên HTTP request thread hoặc manager dispatcher và phá latency/transaction assumptions. Chỉ dùng CallerRuns khi chấp nhận rõ chi phí và đã test.

Vì thế, ví dụ này **không** được dùng như một API `202 Accepted` cho batch quan trọng. Đối với công việc phải bảo toàn khi server restart, cần lưu receipt/request trước khi giao cho executor.

## 8. Nhận rồi delay an toàn: durable request ledger

Một phương án dễ kiểm chứng khi API và worker chia sẻ PostgreSQL là lưu **request receipt** trong một bảng có trạng thái và idempotency key. Dispatcher sẽ đọc công việc đã được nhận khi còn capacity; không cần giữ hàng nghìn thread chờ.

### 8.1. Schema minh họa

~~~sql
CREATE TABLE batch_requests (
    request_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         TEXT NOT NULL,
    idempotency_key   TEXT NOT NULL,
    payload_sha256    TEXT NOT NULL,
    job_name          TEXT NOT NULL,
    input_snapshot    TEXT NOT NULL,
    state             TEXT NOT NULL
        CHECK (state IN
            ('QUEUED', 'CLAIMED', 'RUNNING',
             'COMPLETED', 'FAILED', 'EXPIRED', 'CANCELLED')),
    priority          SMALLINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    available_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at       TIMESTAMPTZ,
    owner_id          TEXT,
    claim_token       UUID,
    lease_until       TIMESTAMPTZ,
    attempts          INTEGER NOT NULL DEFAULT 0,
    job_execution_id  BIGINT,
    last_error_code   TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX idx_batch_requests_queue
    ON batch_requests (priority DESC, available_at, created_at, request_id)
    WHERE state = 'QUEUED';

CREATE INDEX idx_batch_requests_lease
    ON batch_requests (lease_until)
    WHERE state = 'CLAIMED';
~~~

Ví dụ dùng PostgreSQL hỗ trợ `gen_random_uuid()` (trên các phiên bản cũ có thể cần extension/config tương ứng). Tên state là **contract ứng dụng minh họa**, không phải `BatchStatus` chính thức của Spring Batch. `request_id` là ID của **lệnh được nhận**, còn `job_execution_id` là ID metadata của một lần chạy job; không nên trộn hai khái niệm.

**Các ràng buộc quan trọng:**

- `tenant_id + idempotency_key` là unique trong phạm vi client/tenant.
- `payload_sha256` là fingerprint từ **request đã được canonicalize** theo quy ước ổn định; không dùng hash để thay thế validation.
- `input_snapshot` phải trỏ vào dữ liệu bất biến hoặc có cutoff/version chính thức.
- `deadline_at` giúp không nhận lời xử lý một công việc đã hết giá trị.
- `owner_id` và `claim_token` dùng cho ownership/fencing; chỉ lưu token mà không kiểm tra ở resource khi ghi **chưa phải fencing**.
- `attempts` đếm thử nhận/dispatch theo contract, **không** nên đồng nhất với `JobExecution` hay số chunk retries.

### 8.2. Admission transaction và idempotency

Một flow chấp nhận mới có thể là:

~~~mermaid
flowchart TD
    A[HTTP POST + Idempotency-Key] --> B{Request key đã tồn tại?}
    B -->|Có| C{Payload hash giống?}
    C -->|Có| D[Trả receipt/status cũ]
    C -->|Không| E[409 Conflict: key tái sử dụng khác payload]
    B -->|Chưa| F{Quota/queue capacity còn?}
    F -->|Không| G[429 hoặc 503, không persist nghĩa vụ mới]
    F -->|Có| H[Atomic capacity reservation + INSERT ledger]
    H -->|COMMIT thành công| I[202 Accepted + requestId]
    H -->|Fail/rollback| J[Không xác nhận 202; caller retry cùng key]
~~~

**Kiểm tra `SELECT count(*)` rồi `INSERT` không phải strict quota** nếu nhiều API pod làm đồng thời: tất cả đều có thể nhìn thấy count dưới giới hạn rồi cùng nhận vượt capacity. Nếu yêu cầu trần chính xác, cần **một phép kiểm tra/giữ slot có tính nguyên tử** (row lock/counter transaction, database queue admission reservation hoặc distributed limiter có chính sách phục hồi).

Ví dụ về **atomic quota reservation** dùng một counter row có sẵn:

~~~sql
CREATE TABLE batch_admission_capacity (
    queue_name       TEXT PRIMARY KEY,
    max_queued       INTEGER NOT NULL CHECK (max_queued > 0),
    queued_count     INTEGER NOT NULL DEFAULT 0
        CHECK (queued_count >= 0)
);

INSERT INTO batch_admission_capacity(queue_name, max_queued)
VALUES ('payments', 500);

-- Chỉ được gọi trong transaction nhận request mới.
UPDATE batch_admission_capacity
SET queued_count = queued_count + 1
WHERE queue_name = 'payments'
  AND queued_count < max_queued
RETURNING queued_count, max_queued;
~~~

Nếu không trả row, queue đã đầy hoặc tên quota không hợp lệ. Sau khi reserve thành công, trong **cùng transaction** ghi vào `batch_requests` với unique idempotency key; nếu insert không thực sự tạo request mới (race/duplicate), phải **rollback reservation hoặc giải phóng slot trong transaction** trước khi trả receipt cũ. Khi dispatcher chuyển yêu cầu khỏi `QUEUED` sang active, phải giảm `queued_count` trong **cùng transaction quản lý state**, với invariant đúng theo thiết kế.

**Một counter duy nhất có thể trở thành hot row** ở throughput rất cao. Lựa chọn production khác gồm quota buckets/shards, broker-limiter chuyên dụng hoặc ước lượng queue depth kèm headroom; phải ghi rõ cái nào **strict**, cái nào **best effort**. Không tự thêm một quota table rồi mặc định đã giải quyết mọi vấn đề concurrency.

### 8.3. Xử lý trường hợp API commit xong nhưng client không thấy 202

~~~text
Client POST /batch-requests key=K
API ghi request K, COMMIT thành công
Mạng đứt trước HTTP response
Client không biết request đã được nhận hay chưa
Client POST lại cùng K/payload
API tìm receipt K và trả trạng thái hiện có
~~~

Không dùng `run.id` mới hoặc random `JobParameters` khi cùng request được gửi lại; nếu làm vậy, bạn đã chuyển một lần gửi lại HTTP thành **một batch job mới**, gây nguy cơ duplicate. Nếu cùng key nhưng payload khác, trả lỗi business conflict theo contract và báo điều tra.

### 8.4. Broker publish cũng có ranh giới lỗi

Nếu transaction ghi `batch_requests` đã commit mà API ngay lập tức publish message, process có thể crash **giữa commit DB và publish**:

~~~text
BEGIN
  INSERT batch_requests
COMMIT
  <<crash>>
broker.publish() chưa xảy ra
~~~

Để không bỏ quên request, dùng một trong các mô hình **khôi phục được**:

1. **Dispatcher poll DB** lấy requests `QUEUED`, nên không phụ thuộc message được publish ngay tại API.
2. **Transactional outbox** ghi request và outbox event trong cùng DB transaction, relay đẩy message tới broker có retry/dedupe.
3. Transport có transaction/integration được kiểm chứng phù hợp, vẫn cần xét crash, ACK và end-to-end idempotency.

Không gọi `broker.publish()` sau `COMMIT` rồi tuyên bố hai thao tác là atomic chỉ vì chúng xuất hiện liên tiếp trong một method Java.

## 9. Dispatcher claim requests không giữ DB transaction khi job chạy

Dispatcher có thể claim một số lượng nhỏ `QUEUED` requests bằng PostgreSQL `FOR UPDATE SKIP LOCKED`. Dùng **transaction ngắn** để claim; không giữ `SELECT FOR UPDATE` mở suốt hàng phút/giờ batch job chạy.

### 9.1. Claim một lô nhỏ có lease

~~~sql
WITH picked AS (
    SELECT request_id
    FROM batch_requests
    WHERE state = 'QUEUED'
      AND available_at <= now()
      AND (deadline_at IS NULL OR deadline_at > now())
    ORDER BY priority DESC, available_at, created_at, request_id
    LIMIT :claimLimit
    FOR UPDATE SKIP LOCKED
)
UPDATE batch_requests AS r
SET state = 'CLAIMED',
    owner_id = :dispatcherId,
    claim_token = gen_random_uuid(),
    lease_until = now() + INTERVAL '5 minutes',
    attempts = r.attempts + 1,
    updated_at = now()
FROM picked AS p
WHERE r.request_id = p.request_id
RETURNING
    r.request_id, r.input_snapshot,
    r.job_name, r.claim_token, r.attempts;
~~~

**Câu SQL là một claim transaction**, chưa phải toàn bộ workflow. Giới hạn `:claimLimit` phải theo active capacity, không lấy 1.000 request chỉ vì queue có 1.000 row nếu chỉ có bốn worker slots. Bản ghi `CLAIMED` chưa được tính là job `RUNNING` cho tới khi có thông tin launch/ownership cụ thể.

`SKIP LOCKED` hữu ích trong **work queue** vì các dispatcher bỏ qua request đang được transaction khác claim, **không** phù hợp để scan full business input rồi im lặng bỏ những row bị khóa. Queue state/lease phải được kiểm tra lại sau crash, không để request `CLAIMED` bị bỏ quên mãi.

### 9.2. Chuyển state và bảo vệ claim token

Một update chỉ cho owner hiện tại đổi trạng thái:

~~~sql
UPDATE batch_requests
SET state = 'RUNNING',
    job_execution_id = :jobExecutionId,
    lease_until = :nextLeaseUntil,
    updated_at = now()
WHERE request_id = :requestId
  AND state = 'CLAIMED'
  AND claim_token = :claimToken
  AND owner_id = :dispatcherId;
~~~

Nếu `update count=0`, dispatcher đã mất ownership hoặc request thay state; **không tiếp tục launch** như thể claim vẫn thuộc mình. Tuy nhiên, giữa việc kiểm tra claim và tạo `JobExecution`, process vẫn có thể crash. Cần thiết kế idempotent launch/reconciliation theo `JobInstance`, hoặc transaction/coordination đủ mạnh để không có hai launcher thực thi cùng một work unit sai contract.

**Không mặc định một claim token trong bảng request sẽ ngăn stale worker ghi business DB.** Fencing thực phải được kiểm tra tại **resource có side effect** hoặc kết hợp business idempotency/unique key, nếu không stale worker có thể vẫn commit dù đã mất lease.

### 9.3. Lease expiry không được biến thành duplicate launch tự động

Ví dụ batch job chạy 40 phút còn claim lease chỉ 5 phút. Nếu không heartbeat/renew, dispatcher khác sẽ nghĩ request đã mất và launch lại. Khi thiết kế:

- Claim lease ngắn cho **dispatch**, sau đó chuyển `RUNNING` và theo dõi `JobRepository`/heartbeat phù hợp.
- Không reclaim một `RUNNING` request chỉ vì HTTP pod restart; kiểm tra `JobExecution` thực tế và worker còn sống.
- Nếu job cần nhiều giờ, dùng heartbeat/lease renewal có fencing hoặc coordinator có thông tin execution.
- Hết hạn lease chỉ là **tín hiệu cần reconcile**, không phải bằng chứng business transaction đã rollback.
- Worker/manager cũ có thể tiếp tục sau network partition; phải bảo vệ duplicate side effect.

### 9.4. Completion và quota release phải có invariant

Khi request hoàn tất hoặc fail vĩnh viễn, cập nhật state và capacity accounting chính xác **một lần**, dựa trên state transition có điều kiện (ví dụ `RUNNING → COMPLETED`). Không dùng `finally { queuedCount-- }` trong một process nếu request có thể đã bị chuyển owner.

Nếu dùng hai counter `queued_count` và `running_count`, hãy định nghĩa rõ transition nào tăng/giảm từng counter và cập nhật nguyên tử; có quy trình **reconcile ledger state với quota** sau crash/bug. Một counter sai khiến API reject mãi dù queue trống, hoặc nhận quá tải khi queue đầy.

## 10. Spring Batch JobInstance: tránh launch trùng khi nhận lại request

Một request đã được chấp nhận **không đồng nghĩa** một `JobExecution` đã tồn tại. Dispatcher khi có capacity mới tạo/chạy execution. Mối liên hệ:

~~~text
HTTP requestId + tenant + idempotencyKey
            |
            v
Durable batch_requests row (QUEUED)
            |
        dispatcher claim
            v
Spring Batch JobInstance
    jobName + identifying JobParameters
            |
            v
JobExecution (một attempt)
            |
            v
StepExecutions / partitions / chunks
~~~

### 10.1. Identifying parameters phải ổn định

Ví dụ Spring Batch 5.2.x:

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

// Method thuộc class quản lý mapping request -> JobParameters.
public JobParameters toJobParameters(
        String snapshotKey, String requestId) {
    return new JobParametersBuilder()
            .addString("snapshotKey", snapshotKey, true)
            .addString("batchRequestId", requestId, true)
            .toJobParameters();
}
~~~

Đây là **method minh họa**, không tự launch job. `batchRequestId` giúp cùng request luôn quy về cùng identifying parameters khi dispatcher retry. Tùy nghiệp vụ, có thể chọn `snapshotKey` hay một business run key làm identity, nhưng phải có policy rõ cho **cùng snapshot được yêu cầu chạy nhiều lần**. Không vô thức thêm timestamp hoặc `run.id` thay đổi ở mỗi retry vì nó tạo `JobInstance` khác.

### 10.2. Exception từ JobLauncher không phải luôn là “reject”

`JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException`, `JobRestartException` hoặc `JobParametersInvalidException` phản ánh **trạng thái/lifecycle của job**, không đồng nhất với hết capacity. Nếu dispatcher retry sau mất kết nối:

1. Tìm ledger row đã nhận bằng idempotency key.
2. Dò `JobRepository` với đúng job name/identifying parameters.
3. Nếu job đã `COMPLETED`, đối soát business output rồi cập nhật receipt; không launch một instance khác.
4. Nếu đang chạy, theo dõi execution và ownership; không tạo bản sao.
5. Nếu `FAILED`/`STOPPED`, dùng cơ chế restart phù hợp, input snapshot/partition plan ổn định.
6. Nếu chưa có execution, thực hiện launch có giới hạn concurrency với recovery cho khoảng crash.

**Không sửa trực tiếp `BATCH_JOB_EXECUTION.STATUS`/`BATCH_STEP_EXECUTION.STATUS` để “mở slot” hoặc ép một job hoàn tất.** Metadata có version/context/transaction semantics, và một worker cũ có thể vẫn đang chạy.

### 10.3. Bản ghi accepted và StepExecution là hai loại tiến độ

Một dashboard có thể cho biết:

| Request ledger | Spring Batch metadata | Ý nghĩa cần hiển thị |
|---|---|---|
| `QUEUED` | Chưa tạo JobExecution | Đã nhận để xử lý sau |
| `CLAIMED` | Chưa launch hoặc launch chưa rõ outcome | Dispatcher đang nhận quyền; có thể cần reconcile |
| `RUNNING` | JobExecution đang chạy | Đang xử lý; hiển thị tiến độ theo StepExecution |
| `RUNNING` | JobExecution `FAILED` | Ledger cần được reconciled/đưa retry hoặc FAILED |
| `COMPLETED` | JobExecution `COMPLETED` | Hoàn tất theo workflow; còn business reconciliation nếu contract đòi |
| `FAILED` | JobExecution thất bại/không thể restart | Cần operator/client action theo policy |
| `EXPIRED` | Chưa launch | Hết deadline, không tự xóa request mà không thông báo |

Đừng lấy `status=RUNNING` trong ledger làm nguồn sự thật duy nhất nếu `JobRepository` cho thấy execution đã kết thúc, và cũng đừng lấy broker ACK làm bằng chứng nghiệp vụ đã hoàn thành.

## 11. Throttle/reject khi đang dùng remote partitioning

Một manager partition step có thể tạo nhiều worker `StepExecution`, sau đó dispatch chúng qua broker/`PartitionHandler`. Nếu manager gửi 10.000 requests nhưng chỉ có 20 worker slots, **broker sẽ tồn đọng 9.980 message** hoặc adapter có thể buffer chúng. Điều đó có thể phù hợp khi queue bền vững, nhưng phải theo dõi queue age, TTL và recovery; không coi `gridSize` hoặc số request dispatch là số worker thật đang chạy.

~~~mermaid
flowchart TB
    M[Manager JobExecution] --> P[Partitioner: plan/metadata]
    P --> H["PartitionHandler: bounded dispatch"]
    H --> Q[(Durable broker queue)]
    Q --> C["Consumers: limited concurrency/prefetch"]
    C --> W["Worker StepExecutions"]
    W --> B[(Business DB)]
    W --> J[(Shared JobRepository)]
    B -.-> L["DB pressure signals"]
    J -.-> L
    L -.-> H
~~~

### 11.1. Ở manager: giới hạn **số công việc in-flight**

Một `TaskExecutorPartitionHandler` dùng thread pool cần số thread/queue có giới hạn. Với **remote** `MessageChannelPartitionHandler` hoặc wiring Spring Integration, hãy kiểm soát manager dispatch rate, poller, outbound channel và số request unacknowledged theo **khả năng của transport đang dùng**. Không áp một API `setThrottleLimit(...)` của phiên bản/framework cũ vào bất kỳ topology nào mà chưa kiểm chứng.

Nếu handler nhận `TaskRejectedException` khi dispatch một partition đã được tạo:

- Đó là **lỗi nội bộ cần phục hồi**, không phải một client request mới chưa được nhận.
- Không bỏ `StepExecution` giữa chừng hoặc đánh dấu `COMPLETED`.
- Manager phải dừng/gửi lại theo policy, giữ correlation của **chính partition execution** và không tạo bản ghi business trùng.
- Nếu cần delay lâu, bền vững hóa request ở broker/ledger và chọn retry/lease rõ.

### 11.2. Ở worker: hạn chế nhận message trước khi có capacity

Với messaging, cơ chế kiểm soát tốt có thể là:

- Giảm số consumer concurrent trên mỗi pod.
- Giảm prefetch/`max.poll.records` hoặc mức request in-flight phù hợp broker.
- Tạm ngừng poller/listener khi dependency bão hòa (nếu framework/broker hỗ trợ và recovery được thiết kế).
- Dùng bounded internal executor, tránh async dispatch hàng nghìn nhiệm vụ sau khi đã ACK message.
- Chỉ ACK theo contract **sau những bước được bảo vệ**; không ACK trước rồi quên thực thi khi executor reject.

**Đừng dùng `Thread.sleep(10_000)` trong broker listener đang giữ DB transaction** để “delay request”: nó chiếm thread/connection và có thể làm consumer group timeout, kéo dài lock, không tạo backpressure thật. Nếu cần delay, dùng broker retry/delay/scheduler hoặc cập nhật `available_at` ở durable queue, rồi **trả quyền xử lý**.

### 11.3. Remote chunking khác remote partitioning

Trong **remote chunking**, manager đọc item, gửi từng chunk tới worker. Nếu worker chậm, manager có thể tiếp tục đọc/gửi quá nhanh và buffer payload trong memory/broker. Điều cần giới hạn là **chunk in-flight**, queue depth và manager reader pace; mỗi chunk cần correlation, idempotency và checkpoint/reply handling phù hợp.

Trong **remote partitioning**, worker tự đọc theo `ExecutionContext`; manager không nên đồng nhất một partition request với một chunk. Mỗi `StepExecution` có checkpoint/restart riêng, và admission thường áp ở số partitions/jobs active.

### 11.4. Parallel steps và multi-threaded step

Với multi-threaded chunk step trong **một `StepExecution`**, giới hạn số chunk threads qua bounded `TaskExecutor` và xem reader/writer thread safety. `@StepScope` tạo instance theo **StepExecution**, không theo mỗi chunk thread. Với parallel flows, hai step khác nhau có thể cạnh tranh DB pool và update cùng bảng; nên tính **concurrency tổng** thay vì chỉ từng step.

## 12. Từ chối/hoãn khi downstream lỗi: tránh retry storm

Nếu service từ 40 requests/s giảm còn 5 requests/s vì database lock, cùng lúc nhiều client/worker thấy timeout. Nếu mọi nơi retry ngay, arrival rate **sau retry** có thể lớn hơn nguồn request gốc nhiều lần.

~~~mermaid
flowchart TD
    A[DB chậm / lock wait / outage] --> B[Worker timeout]
    B --> C[Retry ngay không giới hạn]
    C --> D[Queue/threads/connections tăng]
    D --> E[DB càng khó phục hồi]
    E --> B
~~~

### 12.1. Exponential backoff + jitter

Một policy mẫu:

\[
d_n = \min(d_{\max},d_0\,2^n)
\]

Trong đó `n` là số lần retry sau thất bại; thêm jitter ngẫu nhiên vào khoảng chờ để các client không retry cùng lúc. Phải có **max attempts**, **max elapsed time** và **deadline**; nếu hết budget, chuyển `FAILED`/DLQ có quan sát.

Ví dụ minh họa **retry schedule**, không phải giá trị chuẩn:

| Thử lại | Trễ cơ sở | Có jitter | Quyết định |
|---|---:|---|---|
| Lần 1 | 1 s | Có | Nếu là lỗi transient và chưa quá deadline |
| Lần 2 | 2 s | Có | Thử lại idempotent work |
| Lần 3 | 4 s | Có | Có thể giảm concurrency/downstream pressure |
| Lần 4 | 8 s | Có | Không vượt max elapsed/attempts |
| Hết budget | Không tự retry | — | FAILED/DLQ, thông báo, điều tra |

**Không retry một PostgreSQL transaction đã aborted** sau deadlock/statement error bằng cách gọi lại cùng statement bên trong transaction. Phải rollback rồi retry một đơn vị transaction phù hợp, với writer idempotent.

### 12.2. Lỗi nào nên retry?

| Tín hiệu | Có thể retry? | Cần kiểm tra |
|---|---|---|
| HTTP `429` từ upstream | Có giới hạn và theo `Retry-After` | API idempotency và deadline |
| HTTP `503` do overload | Có giới hạn/backoff, có thể giảm concurrency | Service đang phục hồi hay outage kéo dài |
| Hikari acquisition timeout | Không retry vô hạn | Pool pending, long transactions, DB locks |
| PostgreSQL `40P01` deadlock | Thường có, sau rollback | Thứ tự khóa, hot rows, bounded retries |
| PostgreSQL `40001` serialization failure | Thường có, toàn transaction | Isolation semantics |
| PostgreSQL `23505` unique violation | Tùy business contract, thường không retry mù | Duplicate hợp lệ hay payload conflict |
| Dữ liệu không hợp lệ | Không | Validate, quarantine/fail |
| Mất kết nối khi COMMIT | Outcome có thể chưa biết | Tra business key/reconcile trước phát lại |

### 12.3. Circuit breaker và admission

Circuit breaker có thể ngăn **mở thêm tác vụ mới** khi downstream lỗi, giúp phục hồi thay vì tiếp tục dồn tải. Nhưng:

- Nó không thay thế durable request ledger: việc bị breaker reject cần được client retry hoặc được lưu.
- Breaker mở không cho phép làm mất `StepExecution` đang active.
- Half-open probes phải giới hạn, không tạo burst 100 worker cùng thử.
- Đóng breaker dựa trên tín hiệu đủ tin cậy, tránh đóng/mở liên tục (flapping).

## 13. Deadline, TTL và queue SLO: delay không thể vô hạn

Nếu API trả `202`, request có thể chờ 2 giây, 2 phút hoặc 2 giờ. Phải có **queue SLO** và deadline rõ:

- **Queue wait p95/p99:** bao lâu từ accepted → execution started?
- **Age of oldest queued item:** request lâu nhất chưa được claim.
- **Time-to-completion:** từ client accepted → business outcome.
- **Deadline miss rate:** bao nhiêu job không còn cơ hội hoàn tất trước cutoff?
- **Expired count:** số request hết hạn khi còn `QUEUED`.

### 13.1. TTL ở broker không tự cập nhật trạng thái business

Message TTL hết hạn có thể làm broker drop/route DLQ theo cấu hình, **không** tự cập nhật `batch_requests.state` hay `JobRepository`. Nếu application trả `202` rồi message biến mất vì TTL, đó là **vi phạm nghĩa vụ xử lý** trừ khi API contract định nghĩa expiry và thông báo chính xác.

Trong durable DB queue, một sweeper có thể đánh dấu expired requests **chỉ khi chưa bắt đầu**:

~~~sql
UPDATE batch_requests
SET state = 'EXPIRED',
    updated_at = now(),
    last_error_code = 'START_DEADLINE_EXCEEDED'
WHERE state = 'QUEUED'
  AND deadline_at IS NOT NULL
  AND deadline_at <= now()
RETURNING request_id;
~~~

Nếu có quota counter, transition `QUEUED→EXPIRED` phải release queued slot **trong cùng transaction**. Cần thông báo caller/monitoring; không xóa row lập tức khiến client retry không tìm được receipt. Deadline **cho phép bắt đầu** khác với deadline **bắt buộc hoàn tất**, và chính sách khi job đang `RUNNING` quá hạn phải xác định riêng.

### 13.2. Queueing delay không thể ước lượng từ length một cách chắc chắn

Ví dụ có 500 job chờ, hệ thống trung bình hoàn thành 50 job/phút. `500/50 = 10` phút là **ước tính thô chỉ khi job sizes tương đối đồng đều, capacity ổn định và queue ưu tiên không đổi**. Nếu một job có thể chạy 30 giây và job khác 5 giờ, số lượng pending không mô tả đủ backlog.

Trong production nên theo dõi **estimated work units**, input bytes/rows, loại job, tenant/priority và historical service-time distributions. Nếu không thể bảo đảm deadline, nên trả về **không có ETA chắc chắn** thay vì hứa “job xong sau 10 phút”.

## 14. Fairness: bảo vệ tenant và request quan trọng

Một queue FIFO toàn cụm có thể bị một tenant tạo job khổng lồ chiếm hết capacity. Một queue priority chỉ chọn priority cao nhất cũng có thể khiến priority thấp **starve** mãi.

### Các chính sách có thể kết hợp

- **Per-tenant active quota:** mỗi tenant chỉ có một số job đang chạy.
- **Per-tenant queued quota:** giới hạn backlog mà một tenant được phép chiếm.
- **Weighted fair scheduling:** phân chia lượt theo trọng số tenant/class.
- **Aging:** request chờ lâu có thể tăng cơ hội được xử lý.
- **Reserved slots:** giữ một ít capacity cho job điều hành/khôi phục quan trọng.
- **Deadline-aware selection:** chỉ ưu tiên job còn có thể hoàn tất, không đơn thuần dựa vào timestamp.

### Mối nguy của priority queue

~~~sql
ORDER BY priority DESC, available_at, created_at
~~~

Một `ORDER BY` như trên (dùng ở claim query phần 9) có thể **starve priority thấp** nếu workload priority cao liên tục. Cần test tải nhiều tenant và ưu tiên để quyết định có dùng aging/weighted fair queue hay không. Đừng tăng `priority` của mọi request rồi kỳ vọng fairness tự xuất hiện.

### Không trộn business urgency với retry attempts

Một request được retry năm lần không tự động quan trọng hơn request mới theo business SLA. Nếu retry luôn được ưu tiên cao nhất, một nhóm poison jobs có thể chiếm toàn bộ worker capacity. Có **retry budget/poison handling** và tách retry queue khi cần.

## 15. Tín hiệu overload và điều khiển capacity không bị rung lắc

Không nên dùng một metric duy nhất để đóng/mở admission. Cần đọc **dòng chảy từ đầu vào đến đầu ra**:

| Tín hiệu | Có thể chỉ ra | Cảnh báo diễn giải sai |
|---|---|---|
| `accepted_rate`, `rejected_rate` | Áp lực đầu vào, quota | Tăng `rejected_rate` khi load test là bình thường nếu chính sách đúng |
| `queue_depth`, `oldest_queue_age` | Backlog tích lũy | Depth thấp nhưng job rất lớn vẫn nghẽn |
| `active_jobs`, `active_partitions` | Concurrent workload | Active cao chưa chắc DB bão hòa |
| `completed_unique_business_rate` | Throughput có ích | `writeCount` có thể tính cả duplicate/rollback |
| Hikari active/idle/pending, acquire p95 | Chờ pool/connection hold | Active=max nhưng pending=0 có thể vẫn bình thường |
| PostgreSQL `Lock`/`IO`/WAL waits | Nút thắt DB | Không quy mọi chậm thành thiếu connection |
| Broker redelivery/queue age/DLQ | Backlog/retry/failure | ACK không chứng minh business commit |
| CPU/GC/memory, thread queues | Áp lực worker JVM | CPU thấp khi thread chờ DB vẫn là overload |
| p95/p99 job wall-time | SLA thực tế | Job sizes/tenant mix có thể thay đổi |

### 15.1. Hysteresis và cooldown

Giả sử admission đóng ngay khi Hikari pending ≥ 10 và mở ngay khi pending ≤ 9. Metric dao động 9/10 có thể tạo **flapping**, khiến producer retry burst liên tục. Thay vào đó:

~~~text
NORMAL
  nếu pending cao + DB latency xấu trong vài cửa sổ
  -> DEGRADED: giảm active budget và hạn chế admission

DEGRADED
  nếu đã dưới ngưỡng an toàn trong nhiều cửa sổ
  -> RAMP_UP: mở lại từ từ

RAMP_UP
  nếu throughput/latency ổn định
  -> NORMAL
  nếu áp lực tăng
  -> DEGRADED
~~~

Sử dụng **ngưỡng vào/ra khác nhau**, thời gian quan sát và tăng tải từ từ. Đây là **policy ứng dụng**, không phải state machine có sẵn của Spring Batch. Nếu nhiều API pod tự ra quyết định độc lập, chúng có thể cùng mở lại và tạo burst; global admission budget/feedback nên có một cách phối hợp rõ.

### 15.2. Adaptive concurrency không được giả định giúp mọi job

Có thể điều chỉnh concurrency dựa trên p95 latency, pending, DB lock và completed throughput. Nhưng Spring Batch job có **thời lượng rất khác nhau**, nên controller phản ứng quá nhanh có thể làm job bị cắt/requeue và tạo overhead. Ưu tiên thay đổi **số job mới được nhận/khởi chạy** hoặc số partitions sắp dispatch thay vì hủy các chunk đang commit.

Mục tiêu là **bảo vệ downstream và làm queue wait có thể dự báo**, không phải đẩy active thread count lên cao nhất.

## 16. Từ admission decision đến HTTP response: ví dụ Spring Boot

Một API nên tách **chính sách admission** khỏi HTTP controller để test được reject/accept/idempotency mà không cần khởi chạy batch job thật trong thread HTTP.

### 16.1. Các outcome có tên rõ ràng

~~~java
import java.util.UUID;

public record SubmitBatchRequest(
        String jobName, String snapshotKey) {}

public sealed interface AdmissionResult
        permits Accepted, Rejected, KeyConflict {}

public record Accepted(UUID requestId, String state)
        implements AdmissionResult {}

public record Rejected(
        int httpStatus, long retryAfterSeconds, String reason)
        implements AdmissionResult {}

public record KeyConflict(String reason)
        implements AdmissionResult {}

public interface DurableAdmissionService {
    AdmissionResult submit(
            String tenantId, String idempotencyKey,
            SubmitBatchRequest request);
}
~~~

Các public type Java trên nên **tách thành file tên tương ứng**; code block trình bày chung để xem contract nhanh. `DurableAdmissionService` là interface, **chưa có implementation**: implementation production phải sử dụng transaction/ledger/atomic capacity reservation ở phần 8, handle duplicate fingerprint, expiry và các race conditions.

### 16.2. Controller ánh xạ đúng reject và accepted receipt

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/batch-requests")
public class BatchRequestController {
    private final DurableAdmissionService admission;

    public BatchRequestController(DurableAdmissionService admission) {
        this.admission = admission;
    }

    @PostMapping
    public ResponseEntity<?> submit(
            @RequestHeader("X-Tenant-Id") String tenantId,
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody SubmitBatchRequest body) {

        AdmissionResult result = admission.submit(tenantId, key, body);
        if (result instanceof Accepted accepted) {
            URI statusLocation = URI.create(
                    "/batch-requests/" + accepted.requestId());
            Map<String, String> receipt = Map.of(
                    "requestId", accepted.requestId().toString(),
                    "state", accepted.state());
            if ("COMPLETED".equals(accepted.state())) {
                // Replay một request cũ đã hoàn tất: trả trạng thái hiện có.
                return ResponseEntity.ok()
                        .location(statusLocation)
                        .body(receipt);
            }
            return ResponseEntity.accepted()
                    .location(statusLocation)
                    .body(receipt);
        }
        if (result instanceof KeyConflict conflict) {
            return ResponseEntity.status(HttpStatus.CONFLICT)
                    .body(Map.of("code", "IDEMPOTENCY_KEY_CONFLICT",
                                 "message", conflict.reason()));
        }
        if (result instanceof Rejected rejected) {
            return ResponseEntity.status(rejected.httpStatus())
                    .header(HttpHeaders.RETRY_AFTER,
                            Long.toString(rejected.retryAfterSeconds()))
                    .body(Map.of("code", "CAPACITY_LIMIT",
                                 "message", rejected.reason()));
        }
        throw new IllegalStateException("Unsupported admission result");
    }
}
~~~

Đây là **HTTP controller skeleton**, không phải toàn bộ service: cần xác thực tenant từ **trusted identity context** thay vì tin mù quáng `X-Tenant-Id` do client tự khai, validate `jobName/snapshotKey`, body size, request signature và quota config. `Rejected.httpStatus` từ service phải được giới hạn các HTTP status hợp lệ (`429`/`503` theo chính sách); `retryAfterSeconds` là số không âm được tính/thẩm định từ policy. Không trả `202` trước khi ledger transaction commit.

Trong ví dụ, request đã `COMPLETED` trả `200 OK` kèm receipt hiện có thay vì giả như đang chờ xử lý; các state `QUEUED`/`RUNNING` vẫn có thể trả `202` theo contract. Tùy API, một `FAILED`/`EXPIRED` receipt cũ có thể được trả bằng `200` kèm state và chi tiết lỗi, không mặc định một HTTP retry tự launch job mới. Mọi mapping cần được kiểm thử cùng idempotency policy.

### 16.3. Test được mà không khởi chạy job

Với API đã tách service, unit/controller tests có thể mock `DurableAdmissionService` để xác minh:

- `Accepted` trả `202`, `Location`, request ID/state.
- `Rejected(429, 30, ...)` trả `429` và `Retry-After: 30`.
- `Rejected(503, 10, ...)` trả `503`, không tạo receipt giả.
- `KeyConflict` trả `409`, không retry như lỗi capacity.
- Request thiếu idempotency key bị từ chối/validation error.

Mock test **không** chứng minh server đã ghi durable queue hoặc quota strict; phải có integration tests với PostgreSQL và nhiều API instances ở phần sau.

## 17. Unit test bounded executor: thật sự reject khi đã đầy

Đừng dùng `Thread.sleep(100)` rồi hy vọng queue đã đầy: CI có thể chạy nhanh/chậm khiến kết quả flaky. Dùng latch để giữ task đang chạy, sau đó submit một task vào queue và kiểm tra request kế tiếp bị từ chối.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class LocalTaskAdmissionTest {

    @Test
    void rejectsThirdTaskWhenOneRunsAndOneIsQueued()
            throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1);
        executor.initialize();

        LocalTaskAdmission gate = new LocalTaskAdmission(executor, 2);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            assertThat(gate.trySubmit(() -> {
                entered.countDown();
                try {
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Test barrier timeout");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            })).isTrue();

            assertThat(entered.await(5, TimeUnit.SECONDS)).isTrue();
            assertThat(gate.trySubmit(() -> {})).isTrue();
            assertThat(gate.trySubmit(() -> {})).isFalse();
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Test trên giả định `LocalTaskAdmission` từ phần 7 cùng package/import. Nó kiểm tra **một JVM, một bounded executor**, chưa kiểm tra distributed admission. Một test bổ sung nên kiểm tra permit được trả khi task lỗi; test khác kiểm tra executor reject do queue đầy ngay cả khi semaphore còn slot (cấu hình lệch) không gây **permit leak**.

### 17.1. Vì sao kiểm thử quá tải phải kiểm tra dữ liệu?

Nếu producer gọi API 1.000 lần và hệ thống trả 202 cho 500 request, 429 cho 500 request, test cần xác minh:

1. Đúng **500 receipt** đã commit vào ledger (theo giả định quota/capacity ban đầu).
2. Không có receipt cho những request bị 429, trừ khi trước đó đã tồn tại cùng idempotency key.
3. Khi dispatcher chạy, mỗi receipt đi tới đúng một **logical business outcome** hoặc trạng thái lỗi/expired rõ ràng.
4. Không có `JobExecution` trôi nổi không liên kết với receipt.
5. Sau crash/restart, cả 500 accepted requests còn discoverable và recoverable.

**Không chỉ assert HTTP status**: một bug có thể trả 202 mà chưa persist request, hoặc trả 429 sau khi đã persist rồi khiến client retry tạo double submit.

## 18. Kiểm thử distributed admission và durable delay

Sử dụng PostgreSQL Testcontainers hoặc một DB staging tương đương **đúng isolation/unique constraint**. Với broker integration, dùng transport thực tế hoặc Testcontainers của broker đã chọn. Test trong memory không bắt được race giữa hai API pods.

### 18.1. Atomic quota race

Giả sử queue trống và `max_queued=10`. Tạo 50 concurrent API calls với **50 idempotency keys khác nhau**, đồng bộ bằng barrier, cùng một tenant:

~~~text
Test input: 50 parallel requests
Capacity: 10 queued slots
Expected:
  10 new ACCEPTED receipts (nếu không có consumer đang claim)
  40 capacity REJECTED responses
  queued_count = COUNT(batch_requests WHERE state='QUEUED') = 10
  0 request accepted nhưng không có ledger row
~~~

Nếu có dispatcher đang chạy đồng thời, queue slots có thể được giải phóng; khi đó **không cứng expected accepted=10**. Để kiểm tra strict atomic admission, test phải **tạm ngừng dispatcher** và giữ queue/DB state cố định. Sau đó mới test riêng trường hợp dispatcher claim đồng thời với admission để xác nhận counter invariant.

### 18.2. Idempotency race

Cho 20 requests **cùng tenant, cùng idempotency key và cùng payload** đến đồng thời. Expected:

- Có **một** request ledger row.
- Cùng một `requestId` được trả cho các retries đã được nhận thành công (có thể lần đầu thất bại kết nối nhưng sau đó tra cứu được).
- Quota `queued_count` tăng **tối đa một lần** cho logical request.
- Không tạo nhiều `JobInstance` từ một HTTP idempotency key.

Lặp lại với cùng key nhưng payload khác: kết quả phải là **conflict business**, không phải 202 cho một công việc tùy ý. Trường hợp concurrent insert conflict phải được kiểm tra bằng unique constraint **thật**.

### 18.3. API crash ở từng mốc

| Fault injection point | Kỳ vọng |
|---|---|
| Trước quota reservation | Không nhận request mới |
| Sau reservation nhưng trước INSERT/COMMIT | Rollback cả quota và request, không rò slot |
| Sau INSERT nhưng trước COMMIT | Rollback/không xác nhận 202 |
| Sau COMMIT nhưng trước HTTP response | Caller retry cùng key, lấy lại receipt |
| Sau COMMIT nhưng trước broker publish | Poller/outbox khôi phục và dispatch được |
| Sau claim nhưng trước launch | Lease expiry/reconcile, không mất request |
| Launch thành công nhưng trước ghi `job_execution_id` | Tìm lại `JobInstance` qua identifying parameters, không launch mới sai |
| Worker business commit nhưng metadata/ACK chưa tới | Writer idempotent, replay an toàn |
| Old owner tiếp tục sau reclaim | Fencing/idempotency ngăn double side effect |

**Bắt buộc ghi rõ đã tiêm lỗi trước/sau COMMIT thật.** Crash trong JDBC `executeBatch` khác crash sau database đã xác nhận COMMIT. Kết nối đứt đúng lúc COMMIT có thể tạo **unknown outcome**; phải đối soát business keys chứ không suy theo exception.

### 18.4. Queue expiry và retry policy

Test:

- Request `QUEUED` hết `deadline_at` được chuyển `EXPIRED` và release quota đúng một lần.
- Request đang `RUNNING` quá deadline không bị auto-xóa khỏi metadata một cách mù quáng.
- Poison request không retry vô hạn, có `FAILED`/DLQ/alert rõ.
- Client retry sau 429 theo cùng key không tạo duplicate khi một lần thử trước đó được accept nhưng mất response.
- Worker crash/reconnect không làm request `CLAIMED` bị bỏ quên mãi.
- Priority cao liên tục không làm low-priority requests chết đói nếu fairness là requirement.

### 18.5. Race giữa hai dispatchers

Chạy hai dispatcher instances đồng thời claim queue 100 requests:

- Mỗi claim token chỉ thuộc một owner hợp lệ tại thời điểm claim.
- Một request không bị hai dispatcher launch như hai logical jobs.
- `FOR UPDATE SKIP LOCKED` giúp claim không trùng trong cùng transaction, nhưng **lease hết hạn hoặc crash giữa claim/launch vẫn cần recovery/fencing**.
- Lấy `request_id`/`JobInstance` làm correlation; broker message ID không phải business idempotency key.
- Tổng accepted receipts và completed/failed/expired/cancelled ledger rows luôn có invariant kiểm tra được.

Đừng chỉ đếm “100 messages được gửi”; phải so **100 unique request IDs**, active `JobExecution` và business output, bao gồm sau restart.

## 19. Observability: đo admission theo nguồn và kết quả

Một service có thể có `accepted_rate` cao mà business throughput bằng không vì tất cả request đều `QUEUED`. Vì vậy phải quan sát **đầu vào, hàng chờ, đang chạy, downstream và completion** trên cùng timeline.

### 19.1. Bộ metric tối thiểu

| Metric | Đơn vị | Câu hỏi |
|---|---|---|
| `admission.requests.accepted` | requests/s | API có đang nhận thêm nghĩa vụ xử lý? |
| `admission.requests.rejected` với `reason` | requests/s | Reject vì tenant quota, global overload hay deadline? |
| `admission.duplicate_replayed` | requests/s | Client retry cùng idempotency key bao nhiêu lần? |
| `batch.queue.depth` | requests | Có bao nhiêu việc đã nhận còn chờ? |
| `batch.queue.oldest_age` | giây | Việc lâu nhất còn phải đợi bao lâu? |
| `batch.queue.wait` p50/p95/p99 | giây | Accepted → execution started trễ bao nhiêu? |
| `batch.active.jobs/partitions` | count | Có bao nhiêu execution thực sự đang tiêu thụ tài nguyên? |
| `batch.completed.business_keys` | unique keys/s | Có bao nhiêu kết quả nghiệp vụ hợp lệ đã commit? |
| `batch.retry.rate` / `dead_letter.count` | attempts, messages | Lỗi đang làm tăng load thực hay không? |
| `batch.deadline_miss` | requests/s hoặc tỷ lệ | Có bao nhiêu request hết giá trị trước lúc chạy? |
| Hikari `active/idle/pending/acquire_p95` | connections, ms | DB pool đang tắc hay dùng hợp lý? |
| Broker `redelivery/queue_age/consumer_count` | messages, giây | Downstream có đang chậm nhận message? |
| DB lock/WAL/IO/CPU | metrics DB | Nút thắt nằm ở resource nào? |

### 19.2. Query read-only cho ledger

~~~sql
WITH counts AS (
    SELECT
        count(*) FILTER (WHERE state = 'QUEUED') AS queued,
        count(*) FILTER (WHERE state = 'CLAIMED') AS claimed,
        count(*) FILTER (WHERE state = 'RUNNING') AS running,
        count(*) FILTER (WHERE state = 'FAILED') AS failed,
        count(*) FILTER (WHERE state = 'EXPIRED') AS expired,
        min(created_at) FILTER (WHERE state = 'QUEUED')
            AS oldest_queued_created_at
    FROM batch_requests
)
SELECT queued, claimed, running, failed, expired,
       EXTRACT(EPOCH FROM (now() - oldest_queued_created_at))
           AS oldest_queued_age_seconds
FROM counts;
~~~

Khi không còn request `QUEUED`, `oldest_queued_age_seconds` là `NULL`; dashboard nên hiển thị rõ “no queued items” thay vì biến thành một độ trễ âm hoặc giá trị 0 gây hiểu lầm. Truy vấn minh họa **toàn bảng**; ở tải lớn nên dùng metrics/counters/indexing/reconciliation phù hợp, không quét ledger triệu row mỗi giây.

### 19.3. Dò metadata và business outcome

Khi một ledger row ghi `RUNNING` quá lâu, xem `job_execution_id` đã gắn với `JobExecution` nào và trạng thái `StepExecution`/partition còn hoạt động hay đã lỗi. So trạng thái này với output ở business DB.

**Không dùng `writeCount` để khẳng định đã có từng ấy row mới được commit** nếu writer thực hiện `ON CONFLICT DO NOTHING` hoặc chunk bị retry. Với job yêu cầu tính đúng, so unique business keys và checksum/aggregate trên immutable snapshot.

### 19.4. Tag có cardinality kiểm soát

Time-series metric nên tag bởi `jobName`, `workerRole`, `tenantTier` (nếu cardinality giới hạn), `errorCategory` và `poolName`. `requestId`, `jobExecutionId`, `partitionName` chi tiết hơn phù hợp trong structured logs/traces; không để mỗi request tạo một label time series giữ nhiều tháng.

**Phân biệt queue age và execution latency:** hàng chờ có thể tăng dù worker xử lý mỗi job rất nhanh nhưng không có đủ slots; hoặc queue gần rỗng nhưng một job đơn lẻ chạy rất lâu. Cả hai phải có cảnh báo khác nhau.

## 20. Capacity planning: chọn lượng việc được nhận dựa trên SLO

Giả sử một loại job tương đối đồng nhất, hệ thống đo được có thể hoàn tất **6 job/phút** ở concurrency an toàn và job mới có deadline bắt đầu trong 15 phút. Nếu hiện đã có 120 job chờ, một ước lượng FIFO rất thô:

\[
W_{\mathrm{queue}}\approx\frac{120}{6}=20\ \mathrm{phút}
\]

Nếu không tăng năng lực bền vững, **tiếp tục nhận vào một queue 15-phút-SLO là không trung thực**. Có thể reject, phân loại ưu tiên, chuyển workload sang cửa sổ khác hoặc thông báo không thể bảo đảm deadline.

### 20.1. Vì sao không dùng một “maxQueue=1.000” bất biến?

Queue capacity hiệu quả còn phụ thuộc:

- Mỗi request tốn 1 giây hay 1 giờ.
- Input bytes/records/partition skew và SQL complexity.
- Số worker/pod thật đang ready, DB capacity và resource budget.
- Tỷ lệ lỗi/retry/poison job.
- Deadline và fairness theo tenant.
- Chi phí giữ queue/storage và thời gian lưu receipt.

Một chính sách thực tế có thể giới hạn **cả số request và estimated work units**. Nếu estimate không chắc, ưu tiên thận trọng và giám sát sai lệch giữa estimated vs actual service time.

### 20.2. Tách ba trạng thái khi giảm tải

| Chính sách | Ý nghĩa | Hệ quả |
|---|---|---|
| **Stop admission** | Không nhận request mới | Client nhận 429/503, accepted requests cũ vẫn còn |
| **Pause dispatch** | Không launch job mới từ queue | Hàng chờ tăng/giữ nguyên, active jobs tiếp tục |
| **Gracefully drain** | Không nhận/dispatch mới, chờ job/chunk active hoàn tất | Giúp deploy/shutdown, nhưng cần timeout và checkpoint |

Khi PostgreSQL outage, có thể phải stop dispatch trước để không tạo thêm lỗi; nhưng nếu durable request ledger cũng ở cùng PostgreSQL và không ghi được, API **không thể nhận durable** và phải reject/503. Không trả 202 vì “sẽ ghi lại sau” nếu bản thân cơ chế lưu bền vững chưa hoạt động.

### 20.3. Client API và operator cần thông tin gì?

Một response/status endpoint nên hiển thị:

~~~text
requestId: id của logical request
state: QUEUED / RUNNING / COMPLETED / FAILED / EXPIRED
acceptedAt: thời điểm server nhận bền vững
startedAt: thời điểm job thật bắt đầu (nếu có)
completedAt: thời điểm outcome cuối (nếu có)
retryable: có nên gửi lại không, và bằng key nào
errorCategory: phân loại lỗi, không lộ secret
jobExecutionId: tham chiếu debug nếu được phân quyền
~~~

**Không công bố ETA chắc chắn từ queue position** nếu không có service-time model đáng tin cậy. Với dữ liệu nhạy cảm, endpoint phải giới hạn caller chỉ xem receipt thuộc tenant/identity được phép.

## 21. Runbook production khi hệ thống bắt đầu từ chối hoặc trì hoãn hàng loạt

### Bước 1 — Xác định overload ở đâu

Đọc `accepted_rate`, `rejected_rate` theo reason, queue depth/oldest age, active jobs/partitions, DB pool, broker age, business completion rate và job wall-clock. Xác nhận đây là **load spike**, **DB slowdown**, **worker thiếu**, **broker outage**, **metadata lỗi** hay **poison retries**.

### Bước 2 — Kiểm tra nghĩa vụ đã nhận

Tìm durable ledger rows `QUEUED/CLAIMED/RUNNING`; so với broker messages và `JobRepository`. Không xóa queue hoặc đổi `status=COMPLETED` bằng tay. Phân biệt:

- Request **chưa nhận** (429/503, không có receipt).
- Request **đã nhận nhưng chưa launch** (QUEUED).
- Request **đã claim nhưng chưa rõ launch** (CLAIMED).
- Request **đang chạy hoặc đã kết thúc** theo `JobRepository` (RUNNING/completed/failed).

### Bước 3 — Kiểm tra cơ chế phối hợp quota

Nếu queue trống nhưng API vẫn reject, xem quota counter có bị lệch ledger không. Nếu queue vượt trần, xem atomic reservation có bị bypass hoặc transaction release slot sai không. Một bug counter cần **reconcile có kiểm soát** theo database state, không dùng một script `UPDATE queued_count=0` khi vẫn có pending requests.

### Bước 4 — Giảm tải an toàn

Tạm giảm active concurrency/consumer prefetch hoặc pause dispatch mới theo policy; để job đang commit hoàn tất/rollback. Nếu client vẫn retry 429/503, cung cấp backoff/Retry-After và hướng dẫn không dùng retry storm. Không tăng Hikari pool ngay khi DB lock/WAL đang bão hòa.

### Bước 5 — Tìm downstream bottleneck

- `Hikari pending` cao: xem connection hold, long transaction, cursor, `REQUIRES_NEW`.
- PostgreSQL `Lock` wait: xác định hot rows/transactions blockers, rút ngắn transaction hoặc phân write ownership.
- WAL/IO/CPU cao: tối ưu writer SQL, chunk size, index, pool/concurrency.
- Broker queue age tăng nhưng DB rảnh: kiểm tra consumer registration, routing, auth, worker startup.
- Worker CPU/GC cao: tối ưu processor, giảm parallelism hoặc tăng tài nguyên theo kết quả benchmark.
- Metadata `JobRepository` chậm: đo DB connections/locking và số partition requests/updates, không bỏ metadata để chạy nhanh.

### Bước 6 — Chặn retry storm và poison queue

Đặt max attempts, backoff/jitter, DLQ/FAILED state và monitoring cho workload lỗi vĩnh viễn. Lỗi data validation không được retry vô hạn; deadlock/retry transient cần rollback và idempotency. Tránh cho request lỗi liên tục chiếm toàn bộ worker pool.

### Bước 7 — Reconcile crash/lease và restart đúng job

Đối với `CLAIMED` lease đã hết, xác minh dispatcher cũ có launch `JobExecution` chưa trước khi reclaim. Đối với `RUNNING` mà worker chết, xác minh StepExecution/JobInstance và worker stale ownership; dùng Spring Batch restart với identifying parameters/input snapshot giữ nguyên. Không launch lại như job mới với random `run.id`.

### Bước 8 — Mở lại admission từ từ

Sau khi downstream phục hồi, giảm queue bằng lượng worker phù hợp ngân sách; mở admission theo từng bước và theo dõi DB lock/WAL/pool, oldest queue age, completion rate. Dùng hysteresis/cooldown để tránh cùng lúc tất cả clients và workers tăng tải.

### Bước 9 — Đối soát và báo cáo cho caller

Xác minh **unique business keys, checksum/tổng nghiệp vụ và ledger state** của tất cả requests đã accepted. Với expired/rejected/failed requests, có trạng thái trả về và thông báo rõ cho operator/client. Không dùng số `202` hoặc số message đã ACK làm tỷ lệ job hoàn tất.

### Bước 10 — Bổ sung regression và capacity plan

Lưu root cause, request rates, service capacity, p95 queue wait, retry counts, counter drift và DB/broker bottleneck; thêm test mô phỏng đúng sự cố. Cập nhật giới hạn tenant/global và quy tắc scale (kể cả rolling surge), không chỉ tăng timeout để che vấn đề.

## 22. Ma trận kiểm thử reject/delay trước production

| Kịch bản | Tạo điều kiện | Tiêu chí đạt |
|---|---|---|
| Bounded local executor | 1 running, 1 queued, request thứ ba | Reject nhanh, không permit leak |
| Quota strict | 50 API calls đồng thời, queue max 10, dispatcher pause | Không quá 10 accepted receipts mới |
| Duplicate cùng key/payload | 20 calls cạnh tranh | Một ledger row và một quota reservation |
| Duplicate cùng key khác payload | Tái sử dụng key | `409`/business conflict, không giấu sai dữ liệu |
| Queue full | Đạt trần có kiểm chứng | `429/503` theo policy, không persist nghĩa vụ mới |
| API crash trước COMMIT | Kill process staging | Request và reservation rollback cùng nhau |
| API crash sau COMMIT | Mất HTTP response | Client retry cùng key nhận receipt cũ |
| DB commit nhưng broker publish mất | Ngắt relay | Poller/outbox phục hồi, không bỏ request |
| Hai dispatcher cùng claim | 100 queued rows | Không claim duplicate tại transaction boundary |
| Lease hết khi manager còn sống | Delay artificial quá lease | Không launch trùng work unit trái contract |
| Stale worker sau reclaim | Worker cũ trở lại | Side effect idempotent/fenced |
| Broker redelivery | Kill consumer trước ACK | Same logical work, output không nhân đôi |
| Poison job | Payload luôn lỗi vĩnh viễn | Bounded attempts, FAILED/DLQ và alert |
| Deadline trước khi start | Request chờ quá hạn | EXPIRED có thông báo và release quota |
| Deadline khi RUNNING | Job kéo dài | Policy riêng, không xóa metadata tùy tiện |
| Hikari pool cạn | Worker concurrency cao | Backpressure, hạn chế retry storm |
| DB row-lock contention | Nhiều writer chạm hot key | Throttle đúng root cause, output đúng |
| Tenant fairness | Tenant A tạo burst, B có ít jobs | B không bị starve nếu fairness contract đòi |
| Rolling deploy | Pod cũ và mới cùng tồn tại | Không vượt DB connection/active budget |
| Worker restart | Job commit trước ACK rồi crash | Replay đúng checkpoint, business idempotent |
| Long soak | Arrival rate > service rate nhiều phút | Queue budget/deadline hoạt động, không OOM |
| Recovery ramp | Từ overload về ổn định | Không flapping hoặc tạo thundering herd |

### Anti-pattern đặc biệt nguy hiểm

- Trả `202` khi request chỉ được lưu trong `ConcurrentLinkedQueue`/in-memory executor.
- Trả `429` **sau khi đã persist** request mà không trả receipt khi client retry.
- Dùng `SELECT count(*)` + `INSERT` trên nhiều API pods để tuyên bố strict global queue cap.
- Dùng `CallerRunsPolicy` trên HTTP/manager thread mà không hiểu transaction/call latency.
- Sleep trong transaction hoặc broker listener để “giảm tải”.
- ACK broker trước khi có durable handoff, rồi executor reject task.
- Gắn quota permit vào **thời gian dispatch** khi công việc chạy async hàng giờ.
- Dùng `run.id` mới mỗi lần HTTP retry, biến một logical request thành nhiều JobInstances.
- Coi message TTL/DLQ là business request tự động hoàn thành/expired.
- Không dọn `CLAIMED` sau crash hoặc auto-reclaim `RUNNING` mà không xem worker cũ.
- Đóng/mở admission mỗi giây theo một metric thiếu hysteresis.
- Bỏ unique business key hoặc giảm durability để tăng throughput trong incident.

## 23. Checklist thiết kế và vận hành

- [ ] Đã phân biệt **reject chưa nhận** và **delay đã nhận bền vững**.
- [ ] `202 Accepted` chỉ được trả sau khi request/receipt đã commit hoặc durable handoff thành công theo contract.
- [ ] Client dùng idempotency key ổn định; duplicate cùng key và payload khác được phát hiện.
- [ ] API có `429`/`503`/`Retry-After` đúng nghĩa, có retry budget và jitter.
- [ ] Không biến HTTP retry thành `JobInstance` mới với timestamp hoặc `run.id` ngẫu nhiên.
- [ ] Phân biệt rate-limit, active execution budget, in-flight messages và durable queue capacity.
- [ ] Với multi-pod, capacity/quota strict được cập nhật **nguyên tử và trên shared coordinator**.
- [ ] Queue có max size/work units, age SLO, deadline, expiry policy và failure visibility.
- [ ] Có tenant/priority fairness khi nhiều loại công việc dùng chung worker pool.
- [ ] Dispatcher claim bằng transaction ngắn; không giữ lock DB trong lúc batch job chạy.
- [ ] `SKIP LOCKED` chỉ dùng cho queue/claim có cơ chế recovery, không lặng lẽ bỏ business input cần đối soát.
- [ ] Claim/lease/reclaim có xử lý stale owner; fencing được kiểm tra tại nơi có side effect nếu cần.
- [ ] Quota counter được release đúng một lần và có reconciliation procedure.
- [ ] Broker durable/persistence/ACK/retry/DLQ/TTL contract đã được kiểm thử.
- [ ] Worker executor/queue có giới hạn, không sleep trong DB transaction để delay.
- [ ] Remote partitioning giữ nguyên shared `JobRepository`, partition names và `StepExecution` correlation khi overload.
- [ ] Remote chunking giới hạn chunk in-flight; manager reader không làm buffer phình vô hạn.
- [ ] Multi-threaded step đã đánh giá reader/writer thread safety; `@StepScope` không được hiểu sai là per-thread.
- [ ] Business writer idempotent; duplicate request/ACK không tạo thêm effect không được phép.
- [ ] Có retry/backoff/jitter/max attempts và phân loại transient vs permanent.
- [ ] Hikari business/metadata pool, PostgreSQL lock/WAL/IO và broker queue age được đo.
- [ ] Không dùng CPU worker làm metric duy nhất quyết định scale/admission.
- [ ] Controller/readiness/status endpoint không leak secrets hay thông tin tenant khác.
- [ ] Có metrics accepted/rejected, queued/claimed/running, oldest age, completed unique business rate.
- [ ] Admission controller có hysteresis/cooldown, recovery ramp có kiểm soát.
- [ ] Đã thử crash ngay trước/sau DB commit, publish và HTTP response.
- [ ] Đã thử concurrent duplicate idempotency key và strict capacity race trên DB thật.
- [ ] Đã thử long soak với arrival rate vượt capacity để xác nhận không OOM hoặc mất request.
- [ ] Có runbook xử lý counter drift, lease orphan, stale worker và unknown commit outcome.
- [ ] Sau restart có thể đối soát business output bằng unique keys/checksum, không chỉ `writeCount`.

## 24. Bài tập thực hành

### Bài tập 1 — Chọn giữa reject và delay

Một hệ thống có thể phục vụ 30 batch requests/phút trong điều kiện ổn định. Một tenant gửi 600 requests trong hai phút, mỗi request phải bắt đầu trong 10 phút sau khi được chấp nhận. Hãy:

1. Ước lượng backlog nếu tiếp nhận hết 600 requests.
2. Đưa ra chính sách reject ngay hay durable delay với max queue/deadline.
3. Nêu HTTP status/`Retry-After` và thông tin receipt cần có.
4. Giải thích tại sao chỉ tăng queue capacity không tăng service capacity.

**Gợi ý:** Phân biệt **start deadline** và **completion deadline**; cùng một batch request có thể mất nhiều phút sau lúc bắt đầu mới hoàn tất.

### Bài tập 2 — Viết bounded executor và test race

Sử dụng `LocalTaskAdmission` phần 7 với executor 2 running threads, queue 3 task và semaphore max-in-flight 5. Dùng `CountDownLatch` giữ hai task đang chạy, xếp thêm ba task, xác minh task thứ sáu bị reject **ngay**, không block. Cho một task ném exception và xác nhận permit được giải phóng.

### Bài tập 3 — HTTP 202 sau durable commit

Implement `DurableAdmissionService` trên PostgreSQL. Khi nhận một request mới:

- Xác thực tenant/idempotency key và canonical payload.
- Kiểm tra duplicate key; cùng payload trả receipt cũ, khác payload báo conflict.
- Reserve strict queue slot và ghi `batch_requests` **trong cùng transaction**.
- Chỉ sau COMMIT mới trả `202`.
- Khi đầy quota, trả `429`/`503` mà không tạo accepted receipt.

Tiêm crash sau INSERT trước COMMIT và sau COMMIT trước HTTP response. Với cả hai, chứng minh client retry cùng key không làm mất hoặc tạo trùng logical request.

### Bài tập 4 — Atomic queue capacity với nhiều API pods

Trên PostgreSQL staging, tạo capacity tối đa 10, tạm dừng mọi dispatcher. Dùng 50 concurrent HTTP requests với unique keys, kiểm tra **tối đa 10 accepted** và quota count khớp số hàng `QUEUED`. Sau đó chạy hai dispatchers claim đồng thời và tiếp tục 50 submissions; kiểm tra invariant kể cả lúc queued slot được giải phóng.

### Bài tập 5 — Claim, lease và stale owner

Dùng query `FOR UPDATE SKIP LOCKED` phần 9 với hai dispatcher. Cho dispatcher A claim một row rồi crash trước launch; đảm bảo lease expiry/reconciler tìm lại work. Tiếp đó tạo tình huống dispatcher A chỉ **mất mạng nhưng không chết**, B reclaim và launch; bổ sung kiểm tra `claim_token`/`JobInstance` và business idempotency để không có hai effect trái contract.

### Bài tập 6 — Retry-After và jitter

Client nhận `429 Retry-After: 30` khi gửi một yêu cầu có idempotency key K. Viết retry policy có max attempts/max elapsed time và jitter, không tạo K mới ở mỗi lần. Khi API trả `503` vì PostgreSQL outage, chỉ retry có giới hạn; khi trả `409` do K đã dùng cho payload khác, **không retry** như lỗi overload.

### Bài tập 7 — Remote partitioning bị nghẽn

Manager tạo 32 partitions, broker có 32 messages, worker pool chỉ cho phép 4 partitions chạy đồng thời, PostgreSQL Hikari business pool max 8/pod. Thiết kế cơ chế giới hạn in-flight/prefetch và tính DB budget khi scale 4 → 12 pods. So với việc manager dispatch toàn bộ và worker ACK trước khi thực thi.

**Yêu cầu:** Không được bỏ `StepExecution` nếu worker executor reject một task; phải có recovery từ broker/ledger/metadata.

### Bài tập 8 — Long wait và deadline

Queue có 300 accepted requests; một số request `deadline_at` đã trôi qua nhưng vẫn `QUEUED`. Viết sweeper chỉ chuyển đúng requests thành `EXPIRED`, release quota đúng một lần và giữ receipt có thể tra cứu. Giải thích vì sao không được dùng cùng SQL tự động xóa `RUNNING` jobs.

### Bài tập 9 — Priority starvation

Cho tenant A gửi liên tục priority 10 trong khi tenant B có 100 requests priority 1. Dùng claim query `ORDER BY priority DESC` để tái hiện B bị chờ vô hạn trong một kịch bản tải đủ lớn. Thiết kế weighted fair scheduling hoặc aging, kiểm tra SLO queue age cho cả hai tenants.

### Bài tập 10 — Adaptive backpressure

Trên staging, đặt bộ metric Hikari pending/DB transaction p95/completed business rate. Tạo tải 1 → 4 → 8 → 16 workers; xác định khi nào throughput dừng tăng nhưng pending/lock tăng. Thiết kế state machine `NORMAL → DEGRADED → RAMP_UP` với ngưỡng vào/ra khác nhau và cooldown. Kiểm tra không xảy ra flapping khi metric dao động gần ngưỡng.

### Bài tập 11 — Broker outage sau acceptance

API lưu request và trả `202` nhưng broker outage 10 phút. So sánh phương án **API publish trực tiếp sau COMMIT** với **transactional outbox/DB dispatcher**. Kill API process trước publish và chứng minh phương án đã chọn có thể phục hồi, không bỏ request accepted.

### Bài tập 12 — Runbook sự cố thực tế

Một hệ thống sau khi autoscale 6 → 18 worker pods bắt đầu ghi:

~~~text
HikariPool - Connection is not available, request timed out
Broker oldest_queue_age = 27m
PostgreSQL wait_event_type = Lock
Retry requests/s tăng nhanh
HTTP 202 vẫn được trả cho mọi request
~~~

Viết runbook xác định **nghĩa vụ đã accepted**, blocker/connection budget, chính sách stop admission/pause dispatch, giảm concurrency và retry storm. Sau khi phục hồi, restart cùng `JobInstance` và đối soát **tập khóa nghiệp vụ**. Giải thích vì sao tăng `maximumPoolSize` hoặc trả mọi request `202` không phải cách giải quyết tổng quát.

### Tự kiểm tra

- Reject request khác delay request ở nghĩa vụ nào?
- Khi nào HTTP `429` phù hợp hơn `503`?
- Vì sao `202 Accepted` không chứng minh `JobExecution.COMPLETED`?
- Vì sao `SELECT count(*)` rồi `INSERT` không bảo đảm strict quota trên nhiều pod?
- Vì sao một semaphore trong mỗi JVM không tạo giới hạn toàn cụm?
- Vì sao broker ACK không chứng minh business commit?
- `FOR UPDATE SKIP LOCKED` có nên dùng để bỏ qua record trong job đối soát đầy đủ không?
- Vì sao lease hết hạn không chứng minh worker cũ đã chết?
- Khi nào `CallerRunsPolicy` có thể tạo overload ngược về HTTP/manager thread?
- Vì sao retry sau mất kết nối khi COMMIT cần idempotency/reconciliation?
- Làm sao đo queue SLO khi có job nhỏ và job rất lớn?
- Làm sao phân biệt trạng thái `QUEUED`, `RUNNING` trong ledger với `BatchStatus` của Spring Batch?

## 25. Tổng kết

**Reject hoặc delay request mới** là một quyết định **về nghĩa vụ xử lý và ngân sách tài nguyên**, không đơn thuần là chọn một queue hay tăng thread count.

- **Reject:** khi hệ thống chưa thể nhận công việc, trả trạng thái rõ (`429`/`503` và retry guidance); không tạo nghĩa vụ accepted giả.
- **Durable delay:** nếu đã hứa nhận, phải lưu receipt/queue bền vững, tra cứu được, có idempotency, deadline, dispatcher recovery, lease/fencing và monitoring.
- **Backpressure nhiều tầng:** điều tiết API/scheduler, manager job/partition dispatch, broker in-flight, worker executor và database theo **capacity thực**, không dựa vào một chỉ số CPU hay `gridSize`.
- **Recovery:** same logical request phải dẫn tới cùng `JobInstance`/business effect đúng nghĩa; crash trước/sau commit, lost ACK và stale worker không được làm mất/trùng dữ liệu.
- **Kiểm chứng:** đo accepted/rejected rate, queue age, completed unique business rate, Hikari/DB pressure; thử strict quota race, overload dài, retry storm, broker outage và restart.

Khi tài nguyên đã bão hòa, **từ chối rõ ràng hoặc trì hoãn có kiểm soát và có thể khôi phục** giúp hệ thống hoàn tất nhiều công việc *đúng* hơn là nhận vô hạn rồi để mọi worker cùng chờ và retry. Mục tiêu cuối cùng là **throughput bền vững, latency có giới hạn theo SLO và dữ liệu chính xác sau mọi lần chạy lại**.

# Pause khi downstream quá tải trong Spring Batch

Một Spring Batch job xử lý 8 triệu bản ghi trong cửa sổ 2 giờ. Manager chia dữ liệu thành 40 partition, có 12 worker chạy đồng thời và mỗi worker gọi một dịch vụ chấm điểm trước khi ghi kết quả. Khi dịch vụ downstream tăng latency từ 100 ms lên 5 giây và trả về HTTP 429, 12 worker tiếp tục đọc item, giữ transaction và JDBC connection trong lúc chờ; số lần retry tăng, pool hết connection, rồi cả job **FAILED**. Đội vận hành bấm “Pause”, nhưng implementation chỉ gọi `Thread.sleep(30000)` trong `ItemProcessor`. Kết quả là throughput giảm về gần 0, trong khi database locks và các worker threads vẫn bị giữ.

Vấn đề không chỉ là thời điểm tạm dừng: **pause phải đặt đúng chỗ, có trạng thái quan sát được và có đường resume an toàn**. Trong Spring Batch, API `JobOperator.stop(...)` dùng để **yêu cầu dừng một JobExecution có kiểm soát**; nó không phải nút giảm tốc vô hình trong một chunk transaction. Đối với Kafka/Rabbit listeners hoặc outbox dispatchers, “pause” lại mang ý nghĩa khác. Trộn các nghĩa này làm dễ mất work, phát lại message hoặc phá checkpoint.

Bài học **“Pause khi downstream quá tải”** thuộc chương **Backpressure** của module **SPRING_BATCH_SCALING_OPERATIONS**, hướng tới mở rộng Spring Batch cho dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Các ví dụ dùng Spring Batch **5.2.x**, Spring Framework **6.x**, Java **17+** và, ở phần thông điệp, API Spring Kafka/Spring AMQP tương ứng. Mã minh họa chỉ thể hiện những thành phần cần thiết; bean hạ tầng, schema và bảo mật operator phải được bổ sung theo hệ thống thật. **Không có lời hứa “pause ngay lập tức” hoặc “exactly-once” chỉ từ một API.**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **backpressure, throttle, pause, drain, graceful stop, retry, restart** và **circuit breaker**.
2. Nhận diện downstream overload bằng số liệu: 429/503, timeout, p95/p99, pending/active permits, connection pool, queue lag và committed throughput.
3. Chọn vị trí **ngừng nhận việc mới** thay vì ngủ trong `ItemReader`/`ItemProcessor`/`ItemWriter` đang giữ transaction.
4. Giải thích ý nghĩa `JobOperator.stop(executionId)`, trạng thái `STOPPING`/`STOPPED` và `restart(executionId)` của Spring Batch 5.2.
5. Thiết kế pause/resume với **hysteresis, cooldown, minimum dwell time** và admission controller có owner.
6. Tách giới hạn **concurrency**, **requests/s**, **retry budget** và **backlog/queue capacity**.
7. Cấu hình listener Kafka pause/resume mà vẫn duy trì polling/heartbeats; hiểu Rabbit listener stop/start và unacked messages.
8. Giữ work bền vững khi dừng remote chunking/partitioning, xử lý mất ACK/reply và stale worker.
9. Thực hiện HTTP calls ngoài JDBC transaction khi cần, với deadline, idempotency key và outbox/inbox.
10. Đo recovery và kiểm thử crash để biết một lần pause không tạo duplicate hoặc bỏ sót business effect.
11. Lập runbook vận hành để pause, drain, resume có kiểm chứng thay vì restart cả job mù.
12. Đánh giá SLA dựa trên **thời gian pause + drain + backlog catch-up + reconciliation**.

## 2. Pause không phải một cơ chế duy nhất

| Cơ chế | Ý nghĩa | Work đang chạy | Khi nào dùng |
| --- | --- | --- | --- |
| **Throttle / rate limit** | Giảm số việc nhận hoặc requests/s | Thường để hoàn tất | Downstream chậm nhưng còn capacity |
| **Pause admission** | Không nhận **work mới** | Cho inflight work drain hoặc hoàn tất có giới hạn | Backlog/429 tăng, cần ngừng gây thêm tải |
| **Pause consumer** | Listener tạm ngưng nhận records từ broker | Phụ thuộc container, ack/offset/prefetch | Kafka/Rabbit-driven ingestion |
| **Drain** | Chờ work đã nhận xong hoặc đến timeout | Vẫn xử lý phần đang có | Trước stop/redeploy/chuyển ownership |
| **Graceful stop Job** | Yêu cầu Spring Batch dừng tại điểm có thể dừng | Không ngắt ngay code tùy ý đang chạy | Finite batch job cần restart từ checkpoint |
| **Circuit breaker OPEN** | Chặn call mới tới dependency lỗi | Đang inflight xử lý theo policy | Giảm tải khi tỷ lệ failure vượt ngưỡng |
| **Retry with backoff** | Thử lại một operation thất bại | Có thể giữ worker slot | Lỗi transient, có bounded budget |
| **Hard kill JVM/pod** | Chấm dứt process cưỡng bức | Work chưa xong bị cắt | Chỉ là biện pháp cuối; cần recovery |

**Pause** trong bài này là một **trạng thái điều phối**, không phải `Thread.sleep()`. Tùy kiến trúc, lệnh pause sẽ làm một trong hai việc: **ngừng phát/nhận thêm work** hoặc **yêu cầu Step dừng có kiểm soát và sau đó restart**.

### 2.1. Ba cấp điều khiển phải tách biệt

- **Job-level:** dừng một JobExecution finite bằng `JobOperator`, chờ `STOPPED` rồi restart **cùng JobInstance**.
- **Queue/listener-level:** tạm dừng consumer hoặc giảm prefetch/concurrency để broker giữ backlog có kiểm soát, không làm mất offset/ACK.
- **Service/HTTP-level:** admission gate, rate limiter, circuit breaker và retry budget để không gửi request khi dependency thiếu capacity.

Một tổ chức có thể dùng cả ba cấp. Nhưng **pause Kafka listener không tự pause Spring Batch job** đã chạy; `JobOperator.stop` cũng không tự suspend một Spring Kafka consumer độc lập.

### 2.2. Sơ đồ điều phối

~~~mermaid
flowchart TD
    S["Scheduler / Operator"] --> PA["Pause Policy Controller"]
    PA --> A["Admission Gate"]
    PA --> J["Spring Batch JobOperator"]
    PA --> K["Kafka / Rabbit Listener Control"]
    A --> Q["Durable Backlog / Snapshot Manifest"]
    Q --> W["Worker / Partition / Chunk"]
    W --> D["Downstream HTTP / DB / Broker"]
    D --> M["Error rate + p99 + queue/pool metrics"]
    M --> PA
    J --> R[("JobRepository")]
    K --> Q
    R --> W
    PA --> O["Audit reason + epoch + TTL + resume owner"]
~~~

Điểm then chốt: **một controller phải có ranh giới trách nhiệm rõ**, không âm thầm can thiệp vào mọi Step. Các thao tác liên quan job và middleware phải được điều phối theo công nghệ cụ thể.

## 3. Vì sao phải ngừng upstream trước khi downstream sụp đổ?

Giả sử manager tiếp nhận 400 items/s nhưng downstream chỉ xử lý ổn định 100 items/s. Sau 15 phút:

\[
\Delta Q \approx (400-100)\times 900 = 270{,}000\ \text{items}.
\]

Đây là mô hình backlog giản lược, giả định work được giữ bền vững và rate ổn định. Nếu 270.000 items chỉ ở một executor queue RAM, crash có thể mất task references; nếu ở broker/manifest/DB work table, có cơ hội phục hồi theo protocol.

Khi downstream chậm, nếu upstream tiếp tục nhận việc:

1. In-flight work và queue age tăng.
2. Worker giữ nhiều JDBC connections, HTTP sockets và memory hơn.
3. Timeout/429/503 phát sinh.
4. Retry tăng tải thực (retry amplification), khiến downstream phục hồi càng chậm.
5. Một số workers rollback; JobRepository metadata và broker ACK/reply thêm contention.
6. Các deadline SLA bị vượt mà không có thời gian khôi phục.

**Backpressure là feedback loop giúp downstream còn khả năng hồi phục.** Tối ưu “tối đa item đã read” trong khi “item đã commit” không tăng chỉ làm hệ thống bận hơn.

### 3.1. Dấu hiệu nào đáng đưa vào quyết định?

| Signal | Điều có thể xảy ra | Không đủ để kết luận |
| --- | --- | --- |
| HTTP `429` + `Retry-After` | Quota/rate đã vượt hoặc bị hạn chế | Downstream đã hỏng hoàn toàn |
| HTTP `503` | Service tạm không khả dụng/quá tải | Mọi request đều an toàn để retry |
| p99 từ 100 ms lên 5 s | Tail latency tăng mạnh | Chắc chắn nguyên nhân là network |
| Request timeout tăng | Dependency chậm/mất kết nối | Request ở đích chắc chắn chưa được xử lý |
| Hikari `pending` tăng | Workers chờ JDBC connections | Chỉ cần tăng pool là hết lỗi |
| Broker `unacked` tăng | Messages đang được consumers giữ | Business writes đã commit |
| Queue age tăng | Backlog không được drain kịp | Chỉ có thêm pods mới cải thiện |
| Job `rollbackCount` tăng | Chunk transactions bị rollback nhiều | Tất cả rollback do cùng downstream |
| Committed items/s giảm | Throughput có ích giảm | CPU là nút thắt |

Nên kết hợp signal từ **downstream + producer + business success rate**; một metric đơn lẻ có thể tạo false positive và pause không cần thiết.

## 4. Đặt điểm pause ở đâu?

**Nguyên tắc:** pause tại **ranh giới admission trước khi resource đắt tiền được chiếm**, không đặt một vòng chờ không giới hạn bên trong transaction chunk.

| Điểm pause | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **Trước scheduler/JobLauncher** | Không khởi chạy Job mới; dễ áp dụng | Không ảnh hưởng Job đã chạy |
| **Trước partition dispatch** | Không phát thêm partition work | Local manager đã submit trước đó khó “rút lại” task |
| **Trước broker consume/poll** | Backlog ở broker thay vì heap | Phải giữ heartbeat/ACK/liveness đúng |
| **Trước HTTP phase ngoài DB TX** | Không giữ JDBC connection khi đợi | Cần durable state giữa DB và network |
| **Giữa hai finite batch executions** | Restart theo JobRepository checkpoint | Không phải pause ngay trong chunk đang xử lý |
| **Ngay trong ItemProcessor của chunk** | Dễ viết | Có thể giữ DB transaction/connection/locks trong lúc chờ |
| **Sau khi ghi DB, trước checkpoint** | Hầu như không có lợi | Tăng crash window và lock hold; tránh |

### 4.1. Anti-pattern: ngủ trong chunk transaction

~~~java
// ANTI-PATTERN: ItemProcessor được gọi trong chunk transaction
public ScoredRow process(SourceRow item) throws Exception {
    while (downstreamIsOverloaded()) {
        Thread.sleep(5_000);
    }
    return scoreClient.score(item);
}
~~~

Đây **không** phải pause an toàn: transaction chunk có thể đang mở, resource state đã được mượn và worker thread bị chặn. Nếu 40 workers đều ngủ, chúng có thể tiêu thụ hết pool hoặc không phản hồi stop signal kịp thời.

### 4.2. Pattern: tạm ngừng phase ngoài transaction

~~~text
TX ngắn #1:
  claim workId + generation token (nếu cần)
  COMMIT

NO JDBC TX:
  check gate/permit before HTTP request
  if PAUSED: leave work in durable PENDING/DEFERRED state
  else: call downstream with timeout + stable idempotency key

TX ngắn #2:
  persist response (validate generation token)
  COMMIT

Batch:
  read immutable READY snapshot, chunk write DB, checkpoint
~~~

Đây là **workflow/eventual consistency**, không phải một transaction toàn bộ. Cần TTL, lease renewal/fencing và reconciliation nếu process chết giữa claim và persist. Điểm quan trọng là lúc chờ permit, **không giữ JDBC transaction**.

## 5. Chọn cơ chế theo kiến trúc Spring Batch

| Kiến trúc | Pause có thể dùng | Cần đặc biệt chú ý |
| --- | --- | --- |
| Finite single-threaded chunk step | Yêu cầu `JobOperator.stop`, đợi `STOPPED`, restart | Không ngắt code user ngay tức thì; checkpoint/reader |
| Multi-threaded step | Graceful stop + bounded executor/admission | Nhiều chunks in-flight, reader/writer thread-safety |
| Parallel steps | Điều phối stop toàn JobExecution; per-flow admission nếu tự thiết kế | Mỗi Step có trạng thái khác nhau; drain time |
| Local partitioning | Stop manager/job; giữ partition plan/ExecutionContext | TaskExecutor có thể đã queue nhiều worker tasks |
| Remote partitioning | Stop/reduce dispatch theo handler/controller; worker liveness | Manager stop không chắc đã dừng mọi remote worker |
| Remote chunking | Ngừng gửi chunk requests, broker backlog/ACK đúng | Manager reader checkpoint khác worker business commits |
| Kafka-driven ingestion | Listener container `pause()/resume()` | Poll/heartbeat/offset/consumer group |
| RabbitMQ-driven ingestion | Stop/start listener container hoặc giảm consumer concurrency | Prefetched/unacked messages và requeue policy |
| Durable outbox dispatcher | Ngừng claim/publish work mới, giữ pending rows | Không đụng tới business transaction đã commit |

Một cấu hình Step có thể **hỗ trợ stop/restart kỹ thuật** nhưng không có nút pause tức thời. Đừng hiển thị `PAUSED` cho JobExecution ngay khi mới gửi yêu cầu `stop`; chỉ đánh dấu **pause requested / stopping** cho đến khi JobRepository xác nhận trạng thái đủ điều kiện.

## 6. JobOperator.stop không tương đương pause/resume trong RAM

Trong Spring Batch 5.2, API `JobOperator.stop(long executionId)` **gửi tín hiệu yêu cầu dừng** một JobExecution đang chạy. Đây là yêu cầu cooperative, không phải lệnh kill thread ngay tại chỗ.

Ví dụ vận hành:

~~~java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchStopService {

    private final JobOperator jobOperator;

    public BatchStopService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        // Chỉ trả về thông tin yêu cầu stop được tiếp nhận.
        // Không tuyên bố JobExecution đã STOPPED tại đây.
        return jobOperator.stop(executionId);
    }

    public long restartStoppedOrFailed(long executionId)
            throws Exception {
        // Chỉ gọi sau khi xác minh status/recovery policy.
        // Restart JobInstance cũ, không tạo identifying run.id mới.
        return jobOperator.restart(executionId);
    }
}
~~~

`JobOperator` có thể ném các exception chuyên biệt khi execution không tồn tại, không chạy hoặc không restart được. Ví dụ dùng `throws Exception` để rút gọn chữ ký; code production phải xử lý các trường hợp cụ thể, log audit và bảo vệ endpoint khỏi truy cập trái phép.

### 6.1. State machine thực tế

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING: JobExecution STARTED
    RUNNING --> STOP_REQUESTED: Operator requests stop
    STOP_REQUESTED --> DRAINING: Framework checks cooperative stop
    DRAINING --> STOPPED: Checkpoint + lifecycle updates succeed
    STOP_REQUESTED --> RUNNING: Not yet observed / request failure
    STOPPED --> RESTARTING: Operator verifies and restarts
    RESTARTING --> RUNNING: New JobExecution, same JobInstance
    RUNNING --> FAILED: Non-retryable failure
    FAILED --> RESTARTING: After recovery checks
~~~

`STOP_REQUESTED`, `DRAINING`, `RESTARTING` ở sơ đồ là **trạng thái điều phối/quan sát do ứng dụng định nghĩa**, không phải các giá trị `BatchStatus` của Spring Batch. Các trạng thái framework đáng chú ý gồm `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `FAILED`, `COMPLETED`, `UNKNOWN`.

Không cố gắng chuyển một JobExecution `COMPLETED` thành “stopped” để chạy lại; restart của completed job theo mặc định không phải hành vi mong muốn.

### 6.2. Vì sao stop có thể không ngay lập tức?

- Worker đang ở trong business code không trả quyền điều khiển cho framework.
- SQL query hoặc HTTP request đang block, không có timeout hợp lý.
- Chunk size quá lớn khiến giao dịch hoàn tất lâu.
- TaskExecutor đã submit nhiều tasks và chưa drain.
- Remote worker mất kết nối nhưng vẫn thực thi; manager không biết kết quả.
- Metadata repository không khả dụng để cập nhật status.
- Reader/ItemStream không hợp lệ khi checkpoint/restart.

Spring Batch documentation nói rõ graceful stop **không force interrupt** đoạn user code một cách an toàn. Cần đặt network deadlines, bounded chunk duration và worker liveness trước khi dùng stop như một biện pháp bảo vệ SLA.

### 6.3. Khi nào restart?

Trước khi `jobOperator.restart(executionId)`:

1. Xác minh JobExecution thật sự `STOPPED` hoặc `FAILED` và phù hợp restart contract.
2. Xác minh không còn worker cũ đang commit business effects, đặc biệt remote partitioning.
3. Đảm bảo identifying `JobParameters`, input snapshot, partition names không thay đổi.
4. Kiểm tra `ExecutionContext`/checkpoint và metadata DB vẫn nhất quán.
5. Nếu business DB và JobRepository khác local transaction, đối soát các item đã commit chưa được checkpoint.
6. Đảm bảo downstream đã có headroom và gate không còn ở trạng thái PAUSED.
7. Giữ idempotency keys cho external API/broker.
8. Ghi lại ai/điều kiện nào cho phép resume.

**Không đổi `run.id`** để “restart nhanh” vì có thể tạo **JobInstance mới** và xử lý lại toàn bộ work.

## 7. Pause không phải lời hứa stop ở đúng một item

Spring Batch chunk step có commit interval, ví dụ `chunk(200)`. Nếu operator request stop khi chunk thứ 41 đang chạy, framework có thể cho chunk này hoàn tất rồi cập nhật status trước khi dừng. Code user bị block sẽ khiến stop chậm. Với multi-threaded step, nhiều chunks có thể đồng thời đang in-flight.

### 7.1. Ranh giới an toàn cần đạt

- Không nhận thêm work ngoài giới hạn/không mở transaction mới theo phương án đã chọn.
- Work đang chạy đã commit/rollback theo transaction semantics thực.
- `StepExecution` và `ExecutionContext` được persist đủ để restart.
- Không còn request ngoài hệ thống với trạng thái **không biết đã thành công hay chưa** nếu chưa có reconciliation.
- Nếu worker bị kill, JobRepository có thể còn status `STARTED`; phải điều tra liveness, không sửa metadata mù.

### 7.2. Cấu hình Step chunk và timeout

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;

@Bean
public Step scoredWorkerStep(
        JobRepository repository,
        PlatformTransactionManager businessTx,
        ItemReader<ScoredRow> reader,
        ItemWriter<ScoredRow> writer) {

    DefaultTransactionAttribute attrs =
            new DefaultTransactionAttribute();
    attrs.setTimeout(30);

    return new StepBuilder("scoredWorker", repository)
            .<ScoredRow, ScoredRow>chunk(200, businessTx)
            .reader(reader)
            .writer(writer)
            .transactionAttribute(attrs)
            .build();
}
~~~

`ScoredRow`, beans reader/writer và `@Bean` import được định nghĩa trong ứng dụng. Timeout 30 giây chỉ minh họa; nó **không tự ngắt socket HTTP** nếu user code đang block. Nếu item cần gọi HTTP, nên tách call khỏi transaction hoặc có client deadline đủ ngắn và sự bảo vệ idempotency.

## 8. HTTP 429/503: pause dựa trên quota và phục hồi có điều kiện

Downstream HTTP thường phát overload qua:

- `429 Too Many Requests`: quota/rate limiting; có thể kèm `Retry-After`.
- `503 Service Unavailable`: service không sẵn sàng; có thể kèm Retry-After.
- Network timeout/connection refused: không xác định remote effect nếu request đã gửi.
- p99 latency tăng liên tục trước khi lỗi tăng.
- Tỷ lệ error budget đang cạn, concurrency permits đã đầy.

Không tự coi mọi `5xx` là nên retry mãi. Một `POST` tạo charge có thể đã thành công ở server dù client nhận timeout; **retry cần stable idempotency key** hoặc tra cứu trạng thái trước khi phát lại.

### 8.1. Policy ngưỡng và chống “flapping”

Một policy tham khảo (ngưỡng **giả định**, phải hiệu chuẩn từ SLO):

- **HEALTHY:** downstream 429 dưới 0,5%, p95 dưới 250 ms, queue age ổn.
- **DEGRADED:** 429 trên 2% trong 3 cửa sổ liên tiếp **hoặc** p95 trên 1 giây; giảm admission xuống 50%.
- **PAUSED:** 429 trên 10%/503 trên 5% trong 2 cửa sổ liên tiếp **hoặc** circuit breaker OPEN; ngừng nhận work mới.
- **PROBING:** sau cooldown tối thiểu 30 giây, chỉ cho một số request thăm dò với bounded budget.
- **RECOVERING:** sau 3 cửa sổ ổn định, mở dần 10% → 25% → 50% → 100% capacity.
- **MANUAL HOLD:** operator buộc pause vì maintenance/incidents; không tự resume khi metrics cải thiện.

Các ngưỡng trên chỉ minh họa cách xây **hysteresis**. Không dùng một request thành công để resume toàn cluster, không pause/resume qua lại mỗi giây và không vượt quota đã được đối tác thông báo.

~~~mermaid
stateDiagram-v2
    [*] --> HEALTHY
    HEALTHY --> DEGRADED: overload warning sustained
    DEGRADED --> PAUSED: high error or breaker OPEN
    PAUSED --> PROBING: cooldown expires
    PROBING --> RECOVERING: bounded probes succeed
    PROBING --> PAUSED: failures recur
    RECOVERING --> HEALTHY: stable windows + headroom
    RECOVERING --> PAUSED: overload returns
    HEALTHY --> MANUAL_HOLD: operator pause
    DEGRADED --> MANUAL_HOLD: operator pause
    PAUSED --> MANUAL_HOLD: operator pause
    MANUAL_HOLD --> PROBING: explicit operator release
~~~

Đây là **state machine của admission controller**, không phải `BatchStatus`. Recovery phải gắn với business work durably queued, không làm mất work khi đổi state.

### 8.2. Retry-After không phải “sleep trong transaction”

`Retry-After` có thể là số giây hoặc HTTP date. Một client cần parse hợp lệ, đặt trần cooldown, kiểm soát clock skew và áp dụng **ngoài transaction**. Nếu server yêu cầu chờ 120 giây nhưng Job chỉ còn 30 giây SLA, quyết định đúng có thể là **stop** với trạng thái vận hành rõ, không giữ worker chờ vô hạn.

## 9. Tính ngân sách: lúc nào pause giúp hệ thống phục hồi?

Giả sử 24 worker threads và downstream chỉ cho 8 HTTP calls đồng thời, latency trung bình 0,4 giây:

\[
R_{\mathrm{HTTP,\ ideal}}\approx\frac{8}{0.4}=20\ \mathrm{requests/s}.
\]

Nếu mỗi item cần một call và upstream tạo 150 items/s, backlog tăng xấp xỉ:

\[
(150-20)\times60 = 7{,}800\ \mathrm{items/min}.
\]

Pause upstream admission giúp **ngừng tăng backlog**, nhưng không làm backlog đang có biến mất. Để drain 78.000 items còn tồn với throughput 20 items/s lý tưởng:

\[
T_{\mathrm{drain}}\approx\frac{78{,}000}{20}
=3{,}900\ \mathrm{s}\approx65\ \mathrm{phút}.
\]

Đây chỉ là ước tính khi một request/item, không có retries hoặc chia sẻ API quota. Khi có latency p99 cao, worker crash, validation/publish và over-quota, thời gian thực sẽ dài hơn.

### 9.1. Pause và rate limit bổ sung cho nhau

Một **concurrency limiter** có thể giữ 8 in-flight nhưng không khống chế requests/s nếu latency giảm. Một **rate limiter** 20 requests/s có thể vẫn tạo quá nhiều in-flight nếu latency tăng mạnh. Nếu downstream có cả hai quota, cần **cả hai cơ chế**, và chúng phải có tổng ngân sách theo max pods/rolling update.

Ví dụ: 4 pods × local `Semaphore(2)` = 8 in-flight tại steady state. Nếu rolling update có thêm 2 pods, 6 × 2 = 12, vượt ngân sách. Cần static budget dựa trên max concurrent replicas hoặc distributed quota controller.

### 9.2. Câu hỏi before pause

- Có phải downstream thật sự quá tải, hay writer đang đợi Hikari pool/DB locks?
- Lỗi là transient hay data validation?
- Backlog có durable không?
- Stop finite job có khả năng đạt SLA hơn giảm concurrency không?
- Có worker đang giữ resource quá lâu trong lúc chờ?
- Circuit breaker/retry có đang nhân tải?
- Work có idempotency/reconciliation nếu bị phát lại?
- Khi resume, **ai** cấp phép và giới hạn initial ramp-up là bao nhiêu?


## 10. Admission policy bền vững, có owner và epoch

Với nhiều pods, một flag `volatile boolean paused` trong từng JVM không đủ:

- Mỗi pod có thể thấy trạng thái khác nhau.
- Khi rolling deployment, pod mới có thể mặc định `RUNNING` dù toàn cluster đang hold.
- Khi operator tắt pause, một pod lỗi có thể dùng cache cũ quá lâu.
- Sau crash, trạng thái manual hold có thể mất.
- Không có audit ai đã pause, tại sao, bao lâu hoặc điều kiện nào cho resume.
- Retry của cùng một lệnh có thể ghi trạng thái đảo đi đảo lại nếu không idempotent.

### 10.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE downstream_admission_policy (
    policy_name VARCHAR(100) PRIMARY KEY,
    mode VARCHAR(20) NOT NULL
        CHECK (mode IN (
            'RUNNING', 'DEGRADED', 'PAUSED', 'MANUAL_HOLD')),
    max_inflight INTEGER NOT NULL CHECK (max_inflight >= 0),
    max_rate_per_second INTEGER NOT NULL
        CHECK (max_rate_per_second >= 0),
    generation BIGINT NOT NULL DEFAULT 0,
    reason VARCHAR(400) NOT NULL,
    changed_by VARCHAR(120) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cooldown_until TIMESTAMPTZ,
    CHECK (
        mode <> 'PAUSED'
        OR max_inflight = 0
    )
);
~~~

Đây là **một mẫu dữ liệu điều phối**, không phải schema Spring Batch chính thức. `generation` là version tăng đơn điệu giúp phát hiện stale policy/cached state; nó **không tự hoạt động như fencing token** đối với business writer nếu writer không kiểm tra generation trong transaction của mình.

Nếu job của bạn có nhiều downstream (HTTP scoring, payment, database analytics), nên có **policy riêng theo dependency và workload**; không dừng mọi job khi chỉ một API phụ bị chậm.

### 10.2. Cập nhật pause bằng optimistic concurrency

~~~sql
UPDATE downstream_admission_policy
SET mode = 'PAUSED',
    max_inflight = 0,
    generation = generation + 1,
    reason = :reason,
    changed_by = :operator,
    changed_at = NOW(),
    cooldown_until = :cooldownUntil
WHERE policy_name = :policyName
  AND generation = :expectedGeneration
  AND mode <> 'MANUAL_HOLD';
~~~

Nếu update count là 0, operator phải đọc lại policy; có thể người khác đã sửa trạng thái hoặc policy đang manual hold. Không cố ghi đè vô điều kiện.

**Production cần:**

1. Authentication/authorization cho pause/resume endpoints.
2. Audit history **append-only** riêng nếu compliance yêu cầu (một row hiện tại chỉ lưu trạng thái mới nhất).
3. Idempotency key cho mỗi command nếu hệ thống nhận lệnh qua broker/API.
4. TTL/expiry cho **tín hiệu quá tải** nếu chính sách cho phép, nhưng **manual hold không tự hết**.
5. Distributed rate/in-flight limiter thực sự; một row policy **không đồng nghĩa** có limiter toàn cluster.
6. Đọc policy theo cache TTL ngắn và fail-safe rõ nếu DB policy unavailable.

### 10.3. Read gate trước durable claim

~~~java
public record AdmissionView(
        String mode,
        long generation,
        int maxInflight,
        int maxRatePerSecond) {

    public boolean mayAdmit() {
        return ("RUNNING".equals(mode)
                || "DEGRADED".equals(mode))
                && maxInflight > 0
                && maxRatePerSecond > 0;
    }
}
~~~

Đây là DTO trong application code. Hàm `mayAdmit()` chỉ kiểm tra **policy có cho phép nhận work mới không**; nó chưa cấp token, chưa bảo đảm quota concurrency và rate. Để thực thi quota, dùng thêm semaphore/token bucket/atomic distributed admission ở downstream boundary.

### 10.4. Thời điểm trạng thái pause có hiệu lực

Nếu một dispatcher đọc policy `RUNNING` rồi, ngay sau đó operator chuyển `PAUSED`, dispatcher có thể vẫn claim thêm một item. Đó là **in-flight race** bình thường nếu contract là cooperative pause.

Nếu business đòi **không claim thêm item nào sau thời điểm pause commit**, phải dùng protocol mạnh hơn, ví dụ:

- Serialize các admissions và policy transition trên một coordinator atomic.
- Gắn `generation` vào claim; transaction claim kiểm tra cùng generation và mode theo lock/version đã chốt.
- Có cơ chế fencing để công việc từ generation cũ không được thực thi sau epoch chuyển nếu yêu cầu.
- Đo thời gian “pause request → last work admitted” như một SLO riêng.

Không tuyên bố “pause tức thì trên toàn cluster” chỉ vì tất cả pods polling flag mỗi giây.

## 11. Java: tạm ngừng dispatcher mà không giữ JDBC transaction

Một pattern phù hợp cho **outbox/durable work dispatcher** là polling theo nhịp hữu hạn: kiểm tra policy, claim một work item trong transaction ngắn, publish/call network **ngoài transaction**, rồi persist kết quả trong transaction ngắn khác.

~~~java
import java.util.Optional;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class OutboxDispatchLoop {

    private final AdmissionPolicyReader admission;
    private final WorkLeaseService leases;
    private final ExternalPublisher publisher;

    public OutboxDispatchLoop(
            AdmissionPolicyReader admission,
            WorkLeaseService leases,
            ExternalPublisher publisher) {
        this.admission = admission;
        this.leases = leases;
        this.publisher = publisher;
    }

    @Scheduled(fixedDelay = 1_000)
    public void dispatchOnce() {
        AdmissionView policy = admission.current();
        if (!policy.mayAdmit()) {
            // Không claim thêm work; không mở transaction rồi sleep.
            return;
        }

        Optional<WorkClaim> candidate = leases.claimNext();
        if (candidate.isEmpty()) {
            return;
        }

        WorkClaim claim = candidate.get();

        try {
            // Có request deadline, stable idempotency key
            // và shared rate/concurrency limiter riêng.
            publisher.publish(
                    claim.payload(),
                    claim.idempotencyKey());

            leases.markSent(claim.workId(), claim.leaseToken());
        } catch (TransientDownstreamException ex) {
            leases.deferWithBackoff(
                    claim.workId(), claim.leaseToken(), ex);
        }
    }
}
~~~

`AdmissionPolicyReader`, `WorkClaim`, `WorkLeaseService`, `ExternalPublisher` và `TransientDownstreamException` là **hợp đồng ứng dụng phải triển khai**, không phải Spring Batch built-ins. Cần bật scheduling, có Spring-managed bean và cấu hình executor/scheduler phù hợp. Một scheduled poller không thay thế được `ItemReader`/`JobRepository` của finite batch step; nó là **phase dispatching bên ngoài chunk**.

### 11.1. Ranh giới transaction trong WorkLeaseService

~~~java
@Service
public class WorkLeaseService {

    private final WorkClaimDao dao;

    public WorkLeaseService(WorkClaimDao dao) {
        this.dao = dao;
    }

    @Transactional("businessTxManager")
    public Optional<WorkClaim> claimNext() {
        // SELECT ... FOR UPDATE SKIP LOCKED
        // kiểm tra claim chưa hết TTL, tăng generation/lease token,
        // lưu CLAIMED và lease expiry rồi COMMIT.
        return dao.claimNextWithLease();
    }

    @Transactional("businessTxManager")
    public void markSent(long id, long expectedLeaseToken) {
        // UPDATE ... WHERE id=:id AND lease_token=:token
        // updateCount phải bằng 1, nếu không -> stale publisher.
        dao.markSentIfOwner(id, expectedLeaseToken);
    }

    @Transactional("businessTxManager")
    public void deferWithBackoff(
            long id, long expectedLeaseToken,
            TransientDownstreamException ex) {
        // Release/extend retry_after với bounded attempts;
        // không ghi status FAILED vĩnh viễn chỉ vì HTTP 429.
        dao.deferIfOwner(id, expectedLeaseToken, ex);
    }
}
~~~

**Transaction thực sự kết thúc sau mỗi service method** nếu được gọi qua Spring proxy và không có outer transaction. `publisher.publish()` nằm **giữa** hai transaction, không giữ JDBC connection trong lúc chờ HTTP/broker. `@Transactional("businessTxManager")` phải dùng manager đúng datasource mà DAO sử dụng.

Nếu đang gọi từ một chunk `@Transactional` bên ngoài, pattern này **không còn đảm bảo network ngoài transaction**. Hãy đặt dispatcher thành một bean/process/phase được kích hoạt sau commit và không gọi nó từ active chunk transaction.

### 11.2. Vì sao lease token và idempotency đều cần?

Hai khái niệm giải quyết hai vấn đề:

- **Lease/fencing token**: ngăn worker cũ ghi `SENT` hoặc kết quả khi nó đã mất quyền sở hữu work item.
- **Idempotency key**: ngăn hệ thống bên ngoài áp dụng business effect hai lần khi request đã thành công nhưng response bị mất.

Một lease hết hạn không thể tự “thu hồi” HTTP request đang được remote server xử lý. Vì vậy cần **cả fencing ở local DB lẫn idempotency/reconciliation ở downstream**.

### 11.3. Mô hình pause không giữ DB connection

~~~mermaid
sequenceDiagram
    participant C as Admission Controller
    participant P as Dispatcher
    participant DB as Business DB
    participant API as Downstream
    C->>P: PAUSED / generation=8
    P->>C: Read policy
    P-->>P: Return without claim
    Note over P,DB: Không mở JDBC transaction chờ permit
    C->>P: RECOVERING / generation=9
    P->>C: Read policy + acquire quota
    P->>DB: TX: claim one work item, COMMIT
    P->>API: Request outside DB TX
    API-->>P: Response
    P->>DB: TX: persist state, COMMIT
~~~

Khi pause, các work items **chưa claim** vẫn tồn tại trong outbox/durable queue. Các items đã claim cần được drain hoặc có lease expiry và retry handling rõ.

## 12. Kafka: pause listener container mà vẫn duy trì polling

Với Spring Kafka, listener containers cung cấp `pause()` và `resume()`. Theo tài liệu chính thức:

- `pause()` yêu cầu consumer ngừng nhận records ở ranh giới poll/container xử lý, **không nhất thiết tức thì**.
- Container **vẫn gọi `poll()`** trong trạng thái paused để duy trì cơ chế consumer group, tránh rebalance chỉ vì ngừng fetch records theo cách container hỗ trợ.
- `isPauseRequested()` cho biết lệnh pause đã được yêu cầu.
- `isContainerPaused()` (Spring Kafka 3.x) cho biết các consumer instances trong container thực sự đã paused. Một số tài liệu phiên bản cũ dùng thuật ngữ `isConsumerPaused()`; khi viết code, đối chiếu API của đúng version đang triển khai.
- `pauseImmediate` (khi được cấu hình) có thể pause sau record hiện tại thay vì sau toàn bộ batch records từ poll trước; các records còn lại có thể giữ trong memory, tùy container/version.
- Khi resume, tiếp tục nhận records; cần kiểm tra offset/ACK, rebalance, transaction và consumer liveness.

### 12.1. Code điều khiển qua KafkaListenerEndpointRegistry

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaInputPauseService {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaInputPauseService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestPause(String listenerId) {
        MessageListenerContainer container =
                requireContainer(listenerId);
        container.pause();
    }

    public void requestResume(String listenerId) {
        MessageListenerContainer container =
                requireContainer(listenerId);
        container.resume();
    }

    public boolean fullyPaused(String listenerId) {
        return requireContainer(listenerId).isContainerPaused();
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer c =
                registry.getListenerContainer(id);
        if (c == null) {
            throw new IllegalArgumentException(
                    "Unknown Kafka listener ID: " + id);
        }
        return c;
    }
}
~~~

Listener tương ứng phải được đăng ký có `id`, chẳng hạn `@KafkaListener(id = "source-ingest", topics = "source-events")`, và registry phải chứa container ấy. Lệnh trên tác động **container trong JVM hiện tại**; trong deployment nhiều pods phải dùng policy/controller tới từng instance hoặc cơ chế Kafka-specific coordination, không tự suy một lời gọi sẽ pause toàn cluster.

### 12.2. Pause records khác stop consumer process

Một kỹ thuật thô là `Thread.sleep()` ngay trong Kafka listener callback. Nếu callback chặn quá lâu so với `max.poll.interval.ms` và container không thể poll đúng lúc, consumer có thể bị coi là không còn tiến triển, dẫn tới rebalance/duplicate redelivery. Dùng container-level pause để polling được duy trì theo contract.

Một số biến thể Spring Kafka có `pauseImmediate`; hãy kiểm thử **lúc nào pause có hiệu lực** với record listener/batch listener, batch size và acknowledgment mode thật. Không ACK/commit offset cho item chưa được ghi bền vững chỉ để làm queue lag nhìn thấp.

### 12.3. Ví dụ điều kiện resume Kafka

Một chiến lược:

1. Downstream ổn định qua ít nhất N cửa sổ.
2. Dành lại HTTP quota cho các services khác.
3. Cho phép 10% consumer capacity rồi quan sát 429/p99.
4. Nếu khỏe, tăng dần concurrency/consumer capacity theo phép đo.
5. Kiểm tra consumer lag đang giảm, không chỉ số polling tăng.
6. Khi broker redeliver/consumer rebalance, writer idempotent.

Không resume toàn bộ consumers đồng thời sau 10 phút outage nếu downstream chưa đủ headroom cho backlog catch-up.

## 13. RabbitMQ: tạm dừng ingestion bằng listener lifecycle

Với Spring AMQP, có thể tìm container theo `id` qua `RabbitListenerEndpointRegistry` và điều khiển `stop()` / `start()`:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class RabbitInputPauseService {

    private final RabbitListenerEndpointRegistry registry;

    public RabbitInputPauseService(
            RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestStopConsuming(String listenerId) {
        MessageListenerContainer c = requireContainer(listenerId);
        c.stop();
    }

    public void requestStartConsuming(String listenerId) {
        MessageListenerContainer c = requireContainer(listenerId);
        c.start();
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer c =
                registry.getListenerContainer(id);
        if (c == null) {
            throw new IllegalArgumentException(
                    "Unknown Rabbit listener ID: " + id);
        }
        return c;
    }
}
~~~

Đây là **stop/start listener container**, không phải một tính năng pause y hệt Kafka. Theo tài liệu Spring AMQP, mặc định khi stop, container có thể xử lý các **prefetched messages** còn tồn trước khi dừng. Một số phiên bản/container có tùy chọn `forceStop` để dừng sau message hiện tại và **requeue** các prefetched messages; lựa chọn cụ thể phải kiểm tra theo version/lifecycle implementation.

### 13.1. Prefetch và unacked là một phần của pause budget

Nếu có 8 consumers, `prefetch=20`, tối đa khoảng 160 deliveries có thể ở trạng thái chưa ACK trong mô hình đơn giản per-consumer prefetch. Khi downstream chậm, dừng nhận mới **không làm 160 work items đang inflight biến mất**.

Cần chọn:

- Ack sau khi business effect bền vững theo protocol.
- `prefetch` đủ thấp để giảm memory và drain time.
- Quota downstream theo số request thật, không chỉ consumer count.
- DLQ/backoff cho poison messages.
- Idempotent consumer vì message có thể được giao lại khi worker crash.
- Xác nhận container `isRunning()`/consumer counts theo trạng thái thật, không chỉ “stop request đã gửi”.

### 13.2. Không nhầm Rabbit stop với Spring Batch stop

Nếu Rabbit listener tạo JobInstances, stop listener chỉ ngăn **khởi tạo thêm jobs** từ messages mới; nó không tự dừng các JobExecutions đã được launch. Nếu listener nhận chunk requests của remote chunking, stop quá sớm khi manager còn đợi replies có thể khiến job chờ/fail; phải điều phối **ingress pause, drain, stop** theo cả hai bên.

## 14. Remote chunking và remote partitioning khi pause

### 14.1. Remote chunking

Trong remote chunking, manager đọc item, tạo `ChunkRequest` và gửi qua middleware cho workers xử lý/ghi; workers gửi `ChunkResponse`/reply. Một pause tại middleware phải xét **manager reader/checkpoint** lẫn **worker transaction/reply**:

~~~mermaid
sequenceDiagram
    participant M as Manager Chunk Step
    participant Q as Request Broker
    participant W as Remote Worker
    participant D as Business DB
    participant R as JobRepository
    M->>Q: Publish ChunkRequest #92
    Q->>W: Deliver #92
    W->>D: Write + COMMIT
    W-->>Q: Response / ACK
    Q-->>M: Reply #92
    M->>R: Update manager checkpoint
    Note over M,W: Pause mới chỉ ngừng request mới
    Note over M,Q: #92 vẫn phải được ack/correlate hoặc recover
~~~

Nếu pause worker listeners trước khi manager ngừng publish, request queue tăng. Nếu manager chờ sync replies trong worker outage, step có thể timeout/fail. Nếu mất reply sau DB commit, chunk có thể được gửi lại. **Không coi queue rỗng hoặc checkpoint đã tiến riêng lẻ là bằng chứng exactly-once**.

Thứ tự điều phối tham khảo:

1. Ngừng **admission của chunk requests mới** theo cơ chế manager phù hợp, không sửa nội bộ Step tùy tiện.
2. Để chunks đã gửi hoàn tất hoặc timeout rõ.
3. Nhận và correlate replies, cập nhật metadata như contract.
4. Drain unacked/unreplied/leased work; quan sát timeout và errors.
5. Mới dừng workers/consumer containers nếu phải chuyển sang trạng thái stop.
6. Khi resume, so business effects và replay safely theo existing JobInstance.

### 14.2. Remote partitioning

Trong remote partitioning, **mỗi worker tự đọc partition input** và có `StepExecution` riêng. Manager gửi `StepExecutionRequest`, worker lấy context và ghi dữ liệu.

Pause worker dispatch hoặc requests mới **không rollback partition đã commit các chunk trước**. Nếu manager mất kết nối, worker có thể vẫn chạy. Trước khi phát lại request của cùng partition sau pause, kiểm tra:

- `JobRepository` cho cùng `StepExecutionId` và partition key.
- Worker liveness/lease generation.
- Input snapshot và immutable partition manifest.
- Output rows đã commit, writer idempotency.
- Reply/ACK redelivery và fencing nếu hai worker generations có thể cùng tồn tại.

### 14.3. Pause không làm partition chạy dở tự “ngủ an toàn”

Một worker đang trong chunk không thể tự trả resource chỉ vì manager đã ghi flag PAUSED. Nếu nó gọi API bên trong chunk và HTTP timeout tới 2 phút, nó có thể giữ JDBC resources cho tới khi request kết thúc. Cần thiết kế code **bounded operations + cooperative stop checkpoints**, không suy pause là thread suspension.

### 14.4. Phân biệt năng lực thực thi và partition plan

Có thể giảm executor concurrency từ 12 xuống 4 giữa các JobExecutions theo chính sách vận hành, nhưng **không chia lại partition keys/ExecutionContext** của cùng JobInstance chỉ để phù hợp worker count mới. `gridSize` là hint, không phải “số item đang chạy” hoặc một distributed pause switch. Giữ ranges/manifest cố định để restart không bỏ sót hoặc trùng work.

## 15. Backpressure không được làm hỏng tính nhất quán transaction

Một item được read nhưng chưa commit không thể bị đánh dấu “đã xử lý” chỉ vì downstream đang PAUSED. Các ranh giới cần xét:

| Resource | Khi pause | Khi resume |
| --- | --- | --- |
| JDBC chunk transaction | Để commit/rollback theo policy, không sleep vô hạn | Reopen transaction mới nếu còn work |
| JobRepository checkpoint | Persist theo lifecycle, không sửa status thủ công | Restart cùng JobInstance và context |
| External HTTP POST | Có thể đã thành công trước timeout | Dùng same idempotency key/tra trạng thái |
| Kafka consumer offset | Không commit offset cho unprocessed record | Reprocess/dedupe theo offset+business key |
| Rabbit ACK | ACK khi work đã bền theo protocol | Requeue/redelivery có thể xảy ra |
| Outbox row | Giữ `NEW`/`RETRY_WAIT` bền vững | Reclaim khi lease/nextAttempt đủ điều kiện |
| Remote StepExecution | In-flight worker có thể đang ghi | Liveness/fencing trước re-dispatch |
| File/object output | Không tự rollback theo JDBC | Temp version/commit marker và reconciliation |

### 15.1. Transaction manager và JobRepository có thể khác nhau

Nếu chunk business writer dùng datasource A, còn `JobRepository` lưu checkpoint ở datasource B, **hai local transactions không tự atomic**. Một crash khi pause/stop gần commit có thể để lại:

- Business đã commit nhưng checkpoint cũ ⇒ replay/duplicate nguy cơ.
- Checkpoint tiến nhưng business chưa commit ⇒ missing output nguy cơ.

Writer idempotent bảo vệ replay, nhưng **không tự sửa item bị bỏ qua do checkpoint tiến sai**. Reconciliation phải phát hiện cả duplicate lẫn missing. Không di chuyển JobRepository sang database khác chỉ để “giải phóng connection pool” mà bỏ qua recovery contract.

### 15.2. Tình huống nguy hiểm: pause rồi giữ transaction

~~~text
BEGIN chunk transaction
  UPDATE some_rows
  downstream overloaded
  wait until RUNNING (30 minutes)
  UPDATE more_rows
COMMIT
~~~

Trong 30 phút chờ, JDBC connection, row locks, timeout budget hoặc worker thread có thể vẫn bị giữ. Nếu database tự abort vì timeout, code có thể retry ngay và lại chờ — **tự tạo retry storm**.

Thiết kế nên chia thành:

~~~text
DB transaction ngắn: ghi durable request/outbox
COMMIT

No DB transaction: pause admission / wait / retry downstream
No DB transaction: HTTP call + deadline + idempotency

DB transaction ngắn: persist downstream result/ACK state
COMMIT

Batch chunk đọc READY snapshot và commit output
~~~

Bất cứ bước nào sau crash đều có durable state để replay/reconcile. Đây là eventual-consistency protocol, không phải atomic toàn hệ thống; cần versioned work IDs và state transitions rõ.


## 16. Resume theo từng mức, không đồng loạt xả backlog

Sau 20 phút downstream outage, broker/outbox có thể chứa hàng trăm nghìn items chờ. Nếu resume tất cả consumers/pods ngay, hệ thống có thể chuyển tức thời từ PAUSED sang overload lần hai.

Một **ramp-up có phản hồi** thường an toàn hơn:

| Giai đoạn | Capacity tham khảo | Điều kiện tiến tiếp |
| --- | ---: | --- |
| MANUAL_HOLD/PAUSED | 0 work mới | Root cause xác định, cooldown xong |
| PROBING | 1–2 requests in-flight | Probe có deadline, không vượt quota |
| RECOVERING 1 | 10% budget batch | p95, 429, timeout và backlog drain ổn |
| RECOVERING 2 | 25% | 2–3 cửa sổ metrics khỏe liên tiếp |
| RECOVERING 3 | 50% | Pool/CPU/locks và downstream SLO ổn |
| RECOVERING 4 | 75% | Headroom cho online/other jobs |
| RUNNING | 100% **ngân sách đã cấp** | Error budget còn đủ, không tăng retry storm |

Các mức trên là **giả định minh họa**. 100% nghĩa là 100% phần capacity được giao cho batch **sau khi trừ online traffic/reserve**, không phải 100% connections hoặc requests/s toàn hệ thống.

### 16.1. Hysteresis và minimum dwell time

Một controller có thể yêu cầu:

- Chỉ pause khi threshold xấu liên tục N cửa sổ.
- Sau pause, chờ tối thiểu M giây để downstream ổn định.
- Sau resume, giữ mỗi capacity level ít nhất K giây để đo.
- Chỉ tăng nếu **committed throughput tăng mà error/latency không tăng quá giới hạn**.
- Nếu 429 trở lại, giảm capacity hoặc quay PAUSED ngay theo policy.
- Nếu manual hold còn active, **tuyệt đối không tự resume**.

Không chỉ nhìn “HTTP 200 tăng” khi probe rate rất thấp; cần so **error ratio, p95/p99, rate thực, queue lag và consumer/business success** trong các cửa sổ có ý nghĩa thống kê.

### 16.2. Có cần tăng số pods khi resume?

Tăng pods có thể có ích khi downstream đã đủ headroom và bottleneck nằm ở CPU/worker throughput. Nhưng nếu downstream API quota toàn cluster không đổi, tăng pods chỉ làm mỗi pod cần ít permits hơn hoặc phải được global limiter quản lý.

Ví dụ API budget cho batch là 18 in-flight. Với 6 pods, mỗi pod 3 permits vừa đủ. Nếu rollout có 9 pods đồng thời mà mỗi pod vẫn 3 permits, trần thành 27. Dù CPU dư, quota đã bị vi phạm. **Ramping phải kiểm soát max concurrent pods/consumers**, không chỉ số task trong một JVM.

### 16.3. SLA sau pause

Giả sử còn 480.000 items, downstream có thể xử lý thực tế 200 committed items/s sau hồi phục:

\[
T_{\mathrm{catchup}}\ge\frac{480{,}000}{200}
=2{,}400\ \mathrm{s}=40\ \mathrm{phút}.
\]

Nếu SLA còn 35 phút, job **không thể** hoàn tất theo throughput đo được, ngay cả khi hệ thống bình thường. Quyết định cần là thay SLA/cửa sổ, tăng quota có phê duyệt, giảm work hợp lệ hoặc thực hiện runbook chậm, **không tăng retry vô hạn**.

Thời gian hoàn tất thực cần cộng **drain/restart overhead, p99 variability, retry, validation, publish, reconciliation**.

## 17. Circuit breaker, rate limiter, bulkhead: vai trò khác nhau

| Cơ chế | Kiểm soát | Ví dụ |
| --- | --- | --- |
| Circuit breaker | Có nên **gửi call** khi dependency lỗi nhiều? | OPEN khi 503/timeout vượt threshold |
| Rate limiter | Số requests trong một khoảng thời gian | 80 req/s batch budget |
| Semaphore/bulkhead | Số requests đang in-flight | 18 concurrent calls |
| Retry + backoff | Khi nào thử lại một call thất bại? | Tối đa 3 attempts, exponential + jitter |
| Timeout/deadline | Call được phép chờ bao lâu? | Connect 1 s, overall 4 s |
| Pause policy | Có nhận **work mới** hay không? | PAUSED khi overload kéo dài |
| JobOperator.stop | Có yêu cầu **dừng JobExecution** không? | Dừng finite job và restart sau phục hồi |
| Durable queue | Work chưa được xử lý nằm ở đâu? | Kafka topic, Rabbit queue, DB outbox |

Một circuit breaker OPEN **không tự dừng item đang được đọc vào chunk**. Nếu breaker ném exception và Spring Batch retry ngay trên nhiều workers, có thể tạo vòng lặp. Cần phối hợp breaker với admission pause, retry classification và Step failure/stop policy.

### 17.1. Retry amplification

Giả sử một HTTP client retry 3 lần, worker chunk retry lại item 3 lần và broker redeliver chunk 2 lần. Trong tình huống bất lợi, một operation logic có thể dẫn đến nhiều call hơn tưởng tượng. Không được nhân ba con số đó rồi tuyên bố chính xác cho mọi path, nhưng đây là dấu hiệu **nested retry ownership** chưa rõ.

Hãy ghi trong contract:

- HTTP retry cho lỗi nào và bao nhiêu attempts?
- Spring Batch retry cho item/transaction errors nào?
- Broker redelivery cho transport failure nào?
- Circuit breaker có chặn retry storms không?
- Tất cả attempts của một operation có dùng **cùng idempotency key** không?
- Global cap/quota tính **attempts thật** hay chỉ unique items?

### 17.2. HTTP Retry-After và data correctness

Nếu một `POST` bị timeout, không chắc remote side effect chưa xảy ra. Retry dù tuân `Retry-After` vẫn có thể tạo duplicate nếu thiếu idempotency. Rate limit giải quyết **tải**, không giải quyết **tính đúng đắn**.

Một API không hỗ trợ idempotency cần có trạng thái trung gian `UNKNOWN` và reconciliation (query trạng thái giao dịch, ledger đối soát, manual review) trước khi phát lại request.

## 18. Monitoring: làm sao biết đã pause thật?

Một lệnh “pause accepted” chỉ là ý định. Cần các metric xác nhận hành vi hệ thống sau lệnh.

| Nhóm | Metric/điểm quan sát | Điều cần xác nhận |
| --- | --- | --- |
| Controller | `admission_mode`, generation, reason, changed_at, owner | Policy đã commit, không bị race |
| Operator | stop request ID, JobExecutionId, status, elapsed STOPPING | Job đã thật sự STOPPED chưa? |
| Dispatcher | new claims/s, active leases, failed claims, stale tokens | Pause có chặn claims mới? |
| Kafka | pause requested, consumer paused, poll frequency, lag | Container paused nhưng còn poll heartbeat |
| Rabbit | listener running/consumer count, ready/unacked | Consumers đã dừng sau drain? |
| Remote Batch | StepExecution per partition, active worker generations, reply lag | Worker cũ còn chạy không? |
| JDBC | Hikari active/idle/pending, connection hold p99 | DB connections có được trả khi pause? |
| HTTP | request/s, in-flight, 429/503, p95/p99, timeout | Downstream có giảm tải? |
| Retry | retry attempts, backoff time, breaker OPEN | Tải retry có thực giảm? |
| Backlog | age p95/p99, size, drain ETA | Có nguy cơ hết retention/disk? |
| Correctness | unique business keys, duplicates, missing, outbox pending | Pause/replay có làm sai data? |
| SLA | remaining time, expected catch-up, recovery buffer | Resume có kịp cửa sổ batch? |

Tên metric là **đề xuất**, không phải tất cả đều có sẵn mặc định trong Micrometer/Spring Batch. Cần instrument theo component/version thực. Không dùng business key hoặc JobExecutionId làm high-cardinality metric label nếu gây bùng nổ time series; đặt IDs trong logs/traces có retention phù hợp.

### 18.1. Phân biệt pause đã request và pause đã effective

Một dashboard hữu ích có ít nhất:

~~~text
Policy mode:              PAUSED
Pause request age:        8s
New admissions/s:         0
Active leases:            5 -> 3 -> 1 -> 0
Kafka isPauseRequested:   true
Kafka isContainerPaused:  true
Rabbit active consumers:  0
Batch JobExecution:       STOPPING -> STOPPED
Hikari pending:           0
Downstream in-flight:     2 -> 0
Broker ready backlog:     still growing from other producers
~~~

Ví dụ giả định; **một triển khai không nhất thiết dùng cả Kafka và Rabbit**. Chính khả năng tách các tín hiệu này giúp phân biệt “đã gửi lệnh” với “work đã drain”.

### 18.2. Cảnh báo pause quá lâu

Nếu một dependency bị PAUSED 30 phút, không có alert, backlog có thể vượt retention hoặc SLA. Cần alert:

- `pause_duration` lớn hơn ngưỡng vận hành.
- `active_inflight` không giảm dù pause request đã lâu.
- `queue_oldest_age` gần TTL/retention.
- `job_STOPPING_duration` quá dài.
- `retry_attempts/s` tăng dù pause policy đang đóng admission.
- `outbox_pending_age` vượt event delivery SLO.
- `latency_p99` xấu lại trong RECOVERING.
- `resume_ramp_step` bị reset liên tục (flapping).
- Không có operator owner/manual hold reason.

## 19. Truy vấn JobRepository chỉ đọc trước khi restart

Ví dụ Spring Batch JDBC metadata schema mặc định:

~~~sql
SELECT
    je.JOB_INSTANCE_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME,
    se.LAST_UPDATED
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
WHERE je.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY se.STEP_NAME, se.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

Dùng query để xem worker partitions nào đã `COMPLETED`, `FAILED`, `STOPPED` hoặc còn `STARTED`. Không cộng tất cả `READ_COUNT` qua nhiều JobExecutions rồi gọi đó là unique business items: retry/restart có thể đọc lại cùng item.

### 19.1. JobExecution status và run identity

~~~sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    STATUS,
    EXIT_CODE,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID = :jobInstanceId
ORDER BY JOB_EXECUTION_ID;
~~~

Nếu operator dùng `JobOperator.restart(failedOrStoppedExecutionId)` đúng cách, lần chạy mới thuộc cùng JobInstance. Nếu thay identifying `run.id` hoặc `snapshotId`, có thể tạo JobInstance khác và xử lý lại toàn bộ input theo lịch sử mới.

### 19.2. Không sửa BATCH_* như một nút pause

~~~sql
-- ANTI-PATTERN: Không dùng đoạn này để "pause"
UPDATE BATCH_STEP_EXECUTION
SET STATUS = 'STOPPED'
WHERE STEP_EXECUTION_ID = :stepExecutionId;
~~~

Sửa status không chặn worker đang chạy, không flush reader state, không rollback DB chunk, không ACK/requeue message. Thậm chí có thể phá optimistic locking/version consistency. Với `STARTED` stale sau hard kill, phải xác minh liveness, transactions và recovery plan; Spring Batch documentation nêu manual correction có thể là lựa chọn trong một số crash scenarios, nhưng **phải theo quy trình có phê duyệt và bằng chứng**, không sửa mù.

## 20. Fault-injection: chứng minh pause/resume không làm mất work

| Tình huống | Mô phỏng | Tiêu chí nghiệm thu |
| --- | --- | --- |
| Downstream trả 429 kéo dài | Fake service `429 + Retry-After` | Admission giảm rồi pause, requests/s không vượt quota |
| HTTP p99 tăng | Delay 5–30 s | Không giữ DB transaction chờ dài; stop có deadline |
| Circuit breaker OPEN | 100% timeout trong window | Không retry storm; pause work mới |
| Downstream phục hồi chập chờn | Alternate 200/503 | Hysteresis chống flapping, ramp-up từng mức |
| Manual hold khi metrics healthy | Operator bật hold | Không auto resume cho tới explicit release |
| Policy DB unavailable | Block policy reads | Fail-safe theo contract, audit; không fail-open vô ý |
| Concurrent pause/resume commands | Hai operators cùng generation | Optimistic update phát hiện conflict |
| Rolling update surge | Start old+new pods | Global permits/rate không vượt quota |
| JobOperator.stop giữa chunk | Stop request ở chunk thứ 20 | Chunk commit/rollback, status cuối và checkpoint hợp lệ |
| Long blocking HTTP in processor | Inject timeout | Chứng minh timeout/deadline và cảnh báo STOPPING kéo dài |
| Kill worker sau DB commit | Crash trước repository update/reply | Writer idempotent và reconciliation |
| Remote request duplicate | Redeliver same StepExecutionRequest | Worker ownership/fencing ngăn double effect |
| Kafka pause trong lúc poll | Pause khi records đang xử lý | Poll heartbeat, offsets/ACK đúng, resume không mất item |
| Rabbit stop với prefetch > 1 | Stop khi có unacked | Drain hoặc requeue đúng contract |
| Dispatcher crash sau publish | Kill trước mark SENT | Outbox retry + consumer dedupe |
| Queue retention exhaustion | Giảm retention trong test | Alert/escalate, không mất silent required work |
| Resume 100% cùng lúc | Burst canary | Test bắt overload; chuyển sang ramp-up |
| Stop manager khi workers chưa xong | Remote manager stop | Không tưởng rằng tất cả workers đã ngừng; liveness check |
| Executor rejects pending task | Queue đầy | Work còn trong durable plan và restart được |
| SLA gần hết | Pause vượt recovery buffer | Controller báo miss ETA, không tuyên bố completed |

### 20.1. Integration test một finite batch job

~~~text
Given:
  source snapshot v42 có 10.000 items, partition plan immutable;
  chunk size 100; writer idempotent;
  JobRepository và business datasource được xác định rõ.

When:
  chạy 2 partitions;
  downstream bắt đầu trả 429;
  operator request JobOperator.stop(executionId);
  đợi trạng thái dừng thực tế theo timeout hợp lý;
  downstream hồi phục rồi restart cùng JobInstance.

Then:
  không có work mới ngoài drain contract sau pause request;
  StepExecution/ExecutionContext cho biết checkpoint hợp lệ;
  các items đã commit trước stop không bị xóa;
  các items còn lại được xử lý sau restart;
  output final == clean run trên cùng snapshot;
  không có duplicate external business effects.
~~~

Nếu JobRepository và business DB khác managers, bổ sung fault injection **business commit trước checkpoint** và **checkpoint tiến trước business commit**. Writer idempotent chỉ giải quyết replay; cần reconciliation tìm missing output nếu checkpoint đã tiến sai.

### 20.2. Test Kafka listener pause/resume

~~~text
1. Publish N messages có business keys duy nhất vào test topic.
2. Cho listener xử lý và commit một phần theo ACK/transaction policy.
3. Gọi listener container.pause().
4. Đợi isContainerPaused() thật, không chỉ isPauseRequested().
5. Kiểm tra container còn poll theo contract và không gọi listener cho records mới.
6. Resume; xác minh đủ N business effects.
7. Gây rebalance/worker crash để kiểm thử redelivery.
8. So unique keys/versions, không chỉ số offsets.
~~~

### 20.3. Test Rabbit stop/start

~~~text
1. Publish N messages vào durable queue.
2. Set prefetch > 1; giữ một số messages unacked.
3. Stop container và theo dõi consumer cancellation/drain/requeue.
4. Restart container sau khi downstream khỏe.
5. Verify N unique business effects và không mất messages.
6. Test forceStop behavior nếu deployment sử dụng option đó.
~~~

Hãy kiểm chứng semantics theo **phiên bản Spring AMQP và broker** thực tế. Không dùng giả định Kafka `pause()` cho Rabbit `stop()` như thể chúng giống nhau.

## 21. Runbook sản xuất: pause, drain, resume

### 21.1. Pha A — Phát hiện và quyết định

1. Ghi incident ID, thời điểm, downstream dependency, JobInstance/JobExecution và snapshot.
2. Xác định overload thật bằng 429/503, p95/p99, in-flight, DB pool và committed throughput.
3. Xác định traffic online, các jobs khác và quota batch hiện tại.
4. Phân loại `DEGRADED` hay `PAUSED`, xác định ngưỡng và cooldown.
5. Nếu manual hold, ghi operator/owner, reason, expiry policy và điều kiện explicit release.
6. Xác định **điểm chặn work mới**: scheduler, dispatcher, broker listener hoặc yêu cầu stop JobExecution.
7. Không gửi lệnh “stop all” mù nếu remote manager còn chờ replies.

### 21.2. Pha B — Thực thi pause/drain

8. Commit policy PAUSED với generation/audit.
9. Ngừng admission/producer hoặc pause listener theo đúng transport.
10. Nếu finite batch cần dừng, gọi `JobOperator.stop(executionId)` và đánh dấu request state.
11. Theo dõi inflight tasks, leases, HTTP requests, unacked messages và `STOPPING` duration.
12. Đợi các chunk đang chạy commit/rollback hoặc xử lý timeout theo recovery protocol.
13. Xác minh `StepExecution`/`ExecutionContext` đã được persist, không tự sửa status.
14. Đảm bảo durable backlog còn trong broker/DB/snapshot, không bị mất trong executor queue RAM.
15. Xác minh Hikari pending và downstream request rate giảm thật.
16. Với worker còn chạy lâu, điều tra owner/generation/fencing trước khi kích hoạt replacement.

### 21.3. Pha C — Resume an toàn

17. Xác nhận downstream đã có headroom và cooldown/hysteresis conditions đạt.
18. Xác nhận không còn manual hold hoặc đã được owner release.
19. Đối soát work đã commit nhưng chưa checkpoint/ACK; giữ stable idempotency keys.
20. Chọn resume policy: listener resume, dispatcher gate mở dần, hoặc restart finite JobInstance.
21. Với JobOperator, restart đúng execution khi trạng thái cho phép; không thêm identifying run.id.
22. Mở capacity 10%, 25%, 50%, 75%, 100% **theo số liệu**, không qua một timer mù.
23. Theo dõi 429/503, p95/p99, Hikari, broker lag, retry amplification và backlog ETA.
24. Nếu downstream xấu lại, đóng admission sớm và giữ work bền vững.
25. Sau khi hoàn tất, so business key/version/totals với clean snapshot và external side effects.
26. Ghi closure và điều chỉnh alert/retry/concurrency budgets theo bài học incident.

### 21.4. Nếu quá tải không hồi phục kịp SLA

Đừng giữ JobExecution ở `STOPPING` vô thời hạn chỉ để tránh báo trễ. Escalate theo runbook: dự báo ETA với tốc độ commit thực, giữ output chưa publish, xin quota bổ sung nếu được phép, thay cửa sổ SLA hoặc tiến hành recovery được kiểm soát. Một **JobExecution FAILED/STOPPED có khả năng restart an toàn** tốt hơn một dashboard báo “processing” nhưng không có work hữu ích.

## 22. Những hiểu nhầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “Pause chỉ là `Thread.sleep` trong ItemProcessor.” | Sleep trong chunk có thể giữ JDBC TX/locks và chặn stop. |
| “`JobOperator.stop` là kill ngay lập tức.” | Cooperative request, chỉ dừng khi framework có thể lấy lại control. |
| “Pause Kafka ngừng toàn bộ polling.” | Spring Kafka container tiếp tục poll để duy trì group theo contract. |
| “`isPauseRequested()` nghĩa đã paused hoàn toàn.” | Cần kiểm tra `isContainerPaused()` ở Spring Kafka 3.x. |
| “Rabbit listener stop giống Kafka pause.” | Rabbit stop/start có drain/requeue prefetched semantics khác. |
| “Pause listener làm JobExecution đã chạy dừng lại.” | Listener và JobOperator là hai control planes khác nhau. |
| “Ngừng dispatch tức không còn worker đang chạy.” | In-flight work cần drain/lease/reply reconciliation. |
| “PAUSED thì không cần giữ input bền.” | Durable backlog/snapshot là tiền đề resume. |
| “HTTP 429 thì retry thật nhanh.” | Tuân quota/Retry-After, bounded budget và idempotency. |
| “Circuit breaker OPEN tự pause JobRepository.” | Breaker chặn call, không quản lý JobExecution lifecycle. |
| “Semaphore 5 nghĩa toàn cluster có 5 in-flight.” | Mỗi JVM có 5; phải tính max replicas/rolling surge. |
| “Rate limit 20/s tương đương 20 in-flight.” | Hai giới hạn có đơn vị khác. |
| “Stop xong được phép tạo run.id mới để chạy tiếp.” | Thay identifying params có thể tạo JobInstance mới. |
| “Batch STOPPED nghĩa mọi remote worker đã chết.” | Có thể còn stale workers; cần liveness/ownership. |
| “Publisher confirm chứng minh consumer exactly-once.” | ACK/publish khác business idempotency. |
| “Checkpoint là đủ chống duplicate.” | Business DB và metadata có thể commit độc lập. |
| “Outbox bảo đảm message không bao giờ bị gửi lại.” | Publish thành công nhưng chưa mark SENT sẽ redeliver. |
| “Resume 100% là cách nhanh nhất giải quyết backlog.” | Burst có thể gây overload lần nữa. |
| “Downstream p99 đã giảm một lần là auto resume.” | Cần hysteresis, cooldown và manual hold policy. |
| “PAUSED 20 phút không cần alert.” | Có nguy cơ backlog retention/SLA expiry. |

## 23. Checklist trước production

- [ ] Có định nghĩa rõ pause ở cấp scheduler, Batch job, consumer hay HTTP phase.
- [ ] Admission point đặt **ngoài transaction/DB lock** trong đường chờ dài.
- [ ] Không dùng `Thread.sleep` hoặc unbounded wait trong `ItemProcessor`/`ItemWriter`.
- [ ] `JobOperator.stop` được hiểu là cooperative, có timeout/monitoring `STOPPING`.
- [ ] Restart dùng cùng JobInstance/identifying JobParameters và immutable snapshot.
- [ ] Partition names, worker step names và `ExecutionContext` không drift.
- [ ] Admission state có owner, reason, generation/audit và manual hold rules.
- [ ] Policy/controller có hysteresis, cooldown và minimum dwell time.
- [ ] Pause request, effective pause và drain-complete là trạng thái quan sát **khác nhau**.
- [ ] API limiter tính cả requests/s, in-flight và rolling deployment surge.
- [ ] HTTP timeout/Retry-After/overall deadline và stable idempotency key được cấu hình.
- [ ] Retry layers có một owner/budget chung, tránh amplification.
- [ ] Kafka pause/resume kiểm tra `isContainerPaused` (Spring Kafka 3.x), poll/rebalance/offset semantics.
- [ ] Rabbit stop/start đã kiểm thử prefetched/unacked/requeue behavior.
- [ ] Remote chunking manager/worker requests/replies có correlation và duplicate handling.
- [ ] Remote partitioning workers có liveness/fencing trước re-dispatch cùng partition.
- [ ] Durable backlog/manifest/outbox tồn tại khi worker/manager chết.
- [ ] Worker claim/lease expiry và generation conflicts được xử lý.
- [ ] Business writer idempotent theo business key/version.
- [ ] Nếu repository và writer khác datasource, reconciliation bắt cả duplicate lẫn missing.
- [ ] Committed throughput/p99/queue age/429/503/Hikari pending/STOPPING duration được theo dõi.
- [ ] Recovery ramp-up theo phase có thể rollback về PAUSED khi metric xấu.
- [ ] SLA tính cả pause duration, catch-up, validation và publish.
- [ ] Có failure drills trước/sau DB commit, mất ACK/reply, crash/rolling update.
- [ ] Không đổi `BATCH_*` statuses trực tiếp để mô phỏng pause.
- [ ] Manual hold không tự resume nếu chưa được operator cho phép.
- [ ] Output downstream chỉ được publish sau reconciliation theo policy.

## 24. Câu hỏi tự kiểm tra

1. Vì sao `Thread.sleep` trong processor chunk có thể khiến Hikari pool hết connection?
2. Khác nhau giữa pause admission, graceful stop JobExecution và Kafka listener pause?
3. `JobOperator.stop(executionId)` trả về có nghĩa JobExecution đã `STOPPED` chưa?
4. Khi nào nên dùng `JobOperator.restart(executionId)` thay vì tạo `run.id` mới?
5. Vì sao một worker remote còn `STARTED` sau khi manager mất kết nối?
6. Ba tín hiệu nào giúp xác nhận một pause thực sự hiệu lực?
7. Spring Kafka container làm gì với `poll()` khi paused?
8. `isPauseRequested()` khác `isContainerPaused()` thế nào ở Spring Kafka 3.x?
9. Rabbit listener stop có thể còn xử lý prefetched messages không?
10. Tại sao broker ACK và business DB commit không tự atomic?
11. Cần gì để work đã được claim nhưng dispatcher chết không bị mất?
12. Lease/fencing token khác idempotency key ở đâu?
13. Tại sao một manual hold không nên tự động hết khi p95 giảm?
14. Hysteresis giải quyết hiện tượng gì?
15. Cách nào để ngăn rolling update làm vượt global API quota?
16. Nếu API 8 in-flight, latency trung bình 0,4 giây, throughput lý tưởng tối đa khoảng bao nhiêu request/s?
17. Nếu upstream 150 items/s còn downstream chỉ 20 items/s, backlog tăng bao nhiêu trong một phút?
18. Vì sao tăng worker threads khi API `429` tăng có thể làm tình hình tệ hơn?
19. Nếu JobRepository và business DB commit độc lập, crash lúc pause có nguy cơ nào?
20. Tại sao idempotent writer không tự chữa missing rows khi checkpoint đã tiến sai?
21. Tại sao outbox dispatcher cần mark SENT sau publish nhưng vẫn có thể gửi trùng?
22. Một controller chỉ lưu boolean `paused` ở mỗi pod có vấn đề gì?
23. Trong ramp-up, nên tăng capacity theo timer hay theo committed throughput và error budget?
24. Nếu còn 480.000 items với throughput thực 200 items/s, tối thiểu cần bao lâu để catch up?
25. Khi nào JobExecution nên fail/stop rõ ràng thay vì chờ downstream vô hạn?

**Gợi ý:** (1) Chờ bên trong transaction/worker giữ resources. (2) Ba control planes: admission, Batch lifecycle, broker consumption. (3) Không, chỉ là yêu cầu dừng. (4) Sau xác minh trạng thái STOPPED/FAILED, snapshot/context và liveness. (5) Worker cũ có thể còn chạy/không ghi được status. (6) Admission rate xuống 0, in-flight drain, status/container thực. (7) Vẫn poll theo contract để duy trì group. (8) Requested vs actual. (9) Có, tùy forceStop/prefetch/container. (10) Hai resource transaction domains. (11) Durable lease TTL/retry state. (12) Ownership local vs chống duplicate effect tại đích. (13) Operator ownership và bảo trì chưa kết thúc. (14) Tránh flapping. (15) Shared limiter hoặc per-pod budget dựa max simultaneous pods. (16) `8/0.4=20/s`. (17) `(150-20)×60=7.800`. (18) Retry amplification/quota bão hòa. (19) Business commit nhưng checkpoint cũ, hoặc checkpoint tiến trước business. (20) Item bị bỏ qua không được replay. (21) Crash sau publish trước SENT. (22) Không consistent, mất audit/state khi restart. (23) Theo số liệu và hysteresis. (24) `480.000/200=2.400s=40 phút` chưa tính overhead. (25) Khi quá recovery budget/SLA hoặc work không có bounded deadline.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Advanced Metadata Usage: Stopping a Job](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): `JobOperator.stop` là cooperative stop, status/restart và crash handling.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ItemStream`, `ExecutionContext`, checkpoint.
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): multi-threaded step, partitioning và `throttleLimit` deprecated từ 5.0.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata transactions và isolation.
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): `stop`/`restart`.
- [Spring Kafka — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): `pause()`/`resume()`, polling trong trạng thái paused và `pauseImmediate`; kiểm tra `isContainerPaused()` theo API Spring Kafka 3.x.
- [Spring Kafka 3.3 — MessageListenerContainer API](https://docs.spring.io/spring-kafka/docs/3.3.10/api/org/springframework/kafka/listener/MessageListenerContainer.html): `isPauseRequested()` và `isContainerPaused()`.
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html): `pauseImmediate`, `pollTimeoutWhilePaused` và consumer container behavior.
- [Spring AMQP — Container Management](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/container-management.html): listener registry, `start`/`stop` và `forceStop`.
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `prefetchCount`, shutdown/forceStop behavior.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundary và `@Transactional`.
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): bounded executor và shutdown behavior.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): in-flight deliveries/unacked trong Rabbit.
- [Kubernetes — Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory pressure và worker crash conditions.

**Điểm cốt lõi:** **Pause khi downstream quá tải phải ngừng nhận work mới tại ranh giới an toàn, chứ không giữ thread/JDBC transaction để ngủ.** Với finite Spring Batch job, dùng **cooperative stop → kiểm tra `STOPPED` và checkpoint → restart cùng JobInstance** khi cần. Với message-driven workers, dùng **Kafka listener pause/resume hoặc Rabbit listener lifecycle** đúng semantics, nhưng vẫn xử lý inflight, ACK/reply, redelivery và remote worker ownership. Một admission policy bền vững có hysteresis, quota toàn cluster, retry budget, outbox/idempotency và ramp-up theo metrics mới giúp job phục hồi mà không mất dữ liệu hoặc gây overload lặp lại.

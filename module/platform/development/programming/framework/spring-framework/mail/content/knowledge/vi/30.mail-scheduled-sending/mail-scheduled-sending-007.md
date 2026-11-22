# Chọn batch size và khoảng polling trong Spring Framework Mail

Trong ứng dụng Spring, một mô hình gửi email bền vững thường ghi yêu cầu gửi vào **database outbox**, sau đó dùng scheduler/worker lấy những yêu cầu đến hạn để gửi qua `JavaMailSender`. Hai thông số quan trọng trong thiết kế này là **batch size** (số công việc tối đa được claim trong mỗi lượt) và **polling interval** (nhịp scheduler kiểm tra công việc mới đến hạn).

Hai con số nhỏ này ảnh hưởng trực tiếp đến thời gian chờ, lưu lượng truy vấn database, số công việc đang giữ lease, tốc độ sử dụng SMTP quota và rủi ro gửi trùng khi process lỗi. Tăng batch size không tự động tăng tốc SMTP; giảm interval không chữa được provider throttling. Ngược lại, batch quá nhỏ và polling quá chậm có thể khiến worker rảnh trong khi thư cần gửi bị tồn đọng.

**Mục tiêu:** lựa chọn batch size và interval dựa trên SLO, tốc độ sinh job, độ trễ SMTP, concurrency, provider quota, database capacity và khả năng recovery, thay vì sao chép một bộ số cố định.

Bài học trình bày cách tính, các mẫu triển khai Spring Scheduling/PostgreSQL, bounded executor, claim/lease, retry, metrics, tình huống tải cao và quy trình tuning thực tế. Tất cả số liệu cụ thể chỉ nhằm minh họa mô hình.

## 1. Batch size và polling interval áp dụng ở đâu?

```text
Business transaction
        |
        +--> Update business data
        +--> Insert mail_outbox job
        |
        v
COMMIT
        |
        v
Durable outbox
        |
        v
@Scheduled poller
        |
        +--> Find due jobs
        +--> Claim at most batchSize
        +--> Mark owner/lease
        |
        v
Bounded worker pool
        |
        +--> Check eligibility/expiry
        +--> Load prepared HTML/attachments
        +--> Build MimeMessage
        +--> Apply rate/concurrency limits
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP submission outcome
        |
        +--> SUBMITTED
        +--> RETRY_WAIT
        +--> FAILED
        +--> AMBIGUOUS
```

Ở đây **batch size = số outbox jobs mỗi lần claim**, không phải số recipients trên một email hay số MIME messages truyền qua một kết nối SMTP. Một job có thể là một email cho một người, nhưng đó là quyết định model nghiệp vụ.

**Polling interval = nhịp đọc/claim due jobs**. Nó không phải delay giữa hai lần gọi `JavaMailSender.send(...)`, không phải retry backoff và không tự động giới hạn số email gửi cho mỗi recipient.

## 2. Tách các tham số liên quan

| Tham số | Đơn vị | Tác dụng |
| --- | --- | --- |
| `batchSize` | jobs/lượt | Số jobs tối đa mỗi lần claim |
| `pollDelay` | giây/ms | Khoảng cách giữa các lượt kiểm tra theo scheduler |
| `sendConcurrency` | tasks | Số SMTP attempts chạy đồng thời |
| `maxInFlight` | jobs | Số jobs đã claim nhưng chưa hoàn tất |
| `queueCapacity` | tasks | Số tasks đang chờ trong executor |
| `providerRate` | messages/s hoặc recipients/min | Hạn mức SMTP provider |
| `leaseDuration` | giây/phút | Thời hạn sở hữu một job |
| `retryBackoff` | giây/phút | Lịch thử lại khi có lỗi |
| `sendTimeout` | giây | Giới hạn transport connect/read/write |

Không gộp các tham số này thành một khái niệm "tốc độ gửi". Tăng batch size chỉ tăng tốc độ **cấp việc** nếu poller là bottleneck. Khi SMTP hoặc provider quota mới là bottleneck, tăng batch có thể gây quá nhiều in-flight jobs.

## 3. Triệu chứng batch size quá nhỏ

Giả sử một poller lấy 1 job mỗi giây, trong khi database có 10.000 jobs chờ và hệ thống SMTP có thể xử lý 50 jobs/giây. Nếu không có cơ chế lấy thêm việc, poller chỉ cấp ra khoảng 1 job/giây.

Hậu quả:

- SMTP workers rảnh dù outbox `READY` có nhiều jobs.
- Queue age tăng.
- Một campaign hoàn thành rất chậm.
- Tỷ lệ database query trên mỗi email cao.
- Tăng số send threads không cải thiện throughput.

Batch nhỏ có ưu điểm: giữ ít lease, ít memory, dễ phục hồi khi crash và giảm nguy cơ starvation. Không nên tăng batch chỉ vì "muốn nhanh hơn"; phải xác định poller thực sự đang thiếu năng lực cấp việc.

## 4. Triệu chứng batch size quá lớn

Giả sử poller claim 1.000 jobs, executor có 10 threads, mỗi SMTP attempt mất trung bình 4 giây:

```text
1,000 jobs / 10 workers = 100 waves
100 waves × 4 seconds ≈ 400 seconds
```

Đây là phép ước lượng đơn giản khi mỗi wave có cùng thời lượng. Job cuối có thể chờ vài phút mới bắt đầu gửi. Nếu `leaseDuration=60s`, nhiều jobs hết lease ngay trong executor queue, dẫn đến:

- Worker khác reclaim cùng notification.
- Duplicate processing hoặc duplicate email.
- Memory/queue pressure.
- Crash recovery khó kiểm soát.
- Chiến dịch bulk chiếm capacity của transactional mail.
- Số `PROCESSING` lớn nhưng throughput không tăng.

**Nguyên tắc:** không claim quá xa trước thời điểm task thật sự có worker slot và đủ thời gian giữ lease an toàn.

## 5. Vì sao poll quá nhanh cũng tốn kém?

Giả sử 20 ứng dụng cùng poll mỗi 20 ms:

```text
1 instance: 50 polls/s
20 instances: 1,000 polls/s
```

Nếu hệ thống chỉ có vài emails/phút, gần như mọi query trả 0 jobs nhưng vẫn tiêu tốn DB round trip, connection pool, CPU và scheduler wake-ups.

Polling nhanh có thể cần cho SLO độ trễ thấp, nhưng phải đo empty poll rate. Nếu nhu cầu phát hiện rất nhanh mà lượng gửi thấp, một cơ chế **event/broker wake-up + periodic reconciliation poll** có thể phù hợp hơn.

Event wake-up chỉ nên là tín hiệu gợi ý; nếu nó bị mất, periodic poll vẫn phải tìm ra durable outbox jobs.

## 6. Vì sao poll quá chậm làm tăng latency?

Trong tình huống lý tưởng: poller chạy với chu kỳ thực tế ổn định `I`, email jobs xuất hiện tương đối đều giữa các lần poll và không có backlog:

\[
E[T_{\mathrm{detection}}]\approx I/2
\]

| Poll period thực tế | Độ trễ phát hiện trung bình gần đúng | Chờ tối đa gần đúng |
| --- | ---: | ---: |
| 100 ms | 50 ms | 100 ms |
| 500 ms | 250 ms | 500 ms |
| 1 s | 500 ms | 1 s |
| 5 s | 2,5 s | 5 s |
| 30 s | 15 s | 30 s |
| 60 s | 30 s | 60 s |

Đây chỉ là **thời gian chờ phát hiện**. Tổng thời gian từ business event đến SMTP accepted còn bao gồm transaction commit, queue wait, rendering, rate limiter và transport duration. Khi có backlog lớn, độ trễ có thể vượt `I` rất xa.

OTP với TTL ngắn và newsletter có deadline trong vài giờ không cần cùng một polling interval.

## 7. Đặt SLO trước khi tuning

Một hệ thống nên trả lời:

1. Mốc bắt đầu đo: business event commit, `nextAttemptAt`, hay request accepted?
2. Mốc kết thúc đo: job claimed, first SMTP attempt, hay SMTP relay accepted?
3. P95/P99 latency cần đạt là bao nhiêu cho từng loại email?
4. Tốc độ sinh jobs trung bình và đỉnh là bao nhiêu?
5. SMTP provider quota tính theo message hay recipient?
6. SMTP attempt duration P50/P95/P99 bao nhiêu?
7. Độ lớn MIME/attachment và I/O biến động ra sao?
8. Có bao nhiêu app instances, SMTP worker threads và DB connections?
9. Backlog được phép tích lũy đến mức nào?
10. Email có business deadline hoặc token expiry không?

Không dùng "email đã vào Inbox" làm SLO của riêng poller: `JavaMailSender.send(...)` thành công xác nhận submission theo transport, không chứng minh downstream delivery.

## 8. Tốc độ cấp việc lý thuyết

Với batch size `B` và chu kỳ poll hiệu dụng `I_eff` giây:

\[
R_{\mathrm{claim}}\leq \frac{B}{I_{\mathrm{eff}}}
\]

Ví dụ:

```text
batchSize = 20 jobs
effectivePollCycle = 2 seconds

Claim supply ≈ 10 jobs/s
```

Công thức chỉ cho giới hạn cấp việc khi có đủ jobs và query đủ nhanh. Nó không khẳng định mỗi poll luôn claim đúng B jobs.

Tốc độ SMTP thực còn bị giới hạn bởi concurrency, latency, provider và tài nguyên đọc template/attachment.

## 9. Throughput bị giới hạn bởi mắt xích chậm nhất

Mô hình đơn giản:

\[
R_{\mathrm{effective}}\lesssim
\min\left(R_{\mathrm{claim}},\frac{C}{S},R_{\mathrm{provider}},R_{\mathrm{storage}},R_{\mathrm{DB}}\right)
\]

Trong đó `C` là concurrency SMTP attempts, `S` là thời gian trung bình mỗi attempt tính bằng giây.

Ví dụ:

```text
batchSize                  40 jobs
effectivePollCycle         2 seconds
poller supply              ~20 jobs/s

SMTP concurrency            8
mean SMTP attempt           2 seconds
sender capacity            ~4 attempts/s

provider limit              6 messages/s
```

Mắt xích chậm nhất ở ví dụ là sender ~4 attempts/s. Tăng batch từ 40 lên 100 không nâng throughput lên 50 jobs/s.

Cẩn trọng với **đơn vị**: một SMTP message có thể chứa nhiều recipients, trong khi quota của provider có thể tính theo recipients/minute. Không so sánh hai đại lượng trực tiếp nếu chưa quy đổi.

## 10. Tính ngược từ arrival rate

Gọi `λ` là số jobs phát sinh mỗi giây trong khoảng xét. Để backlog không tăng mãi ở trạng thái ổn định, long-run processing capacity cần lớn hơn `λ`:

\[
R_{\mathrm{effective}} > \lambda
\]

Ví dụ:

```text
Peak arrival        8 jobs/s
Claim capacity     10 jobs/s
SMTP capacity      12 jobs/s
Provider capacity  15 messages/s
```

Tốc độ có thể bị poller giới hạn ở 10 jobs/s và chỉ còn khoảng nhỏ để hấp thụ burst/retries. Headroom phù hợp phải đo từ workload thật, không có tỷ lệ an toàn cứng cho mọi hệ thống.

## 11. Little's Law và backlog

Ở trạng thái ổn định, Little's Law:

\[
L = \lambda W
\]

Trong đó `L` là số jobs trung bình trong hệ thống/queue theo phạm vi đo, `λ` là throughput bình quân, và `W` là thời gian trung bình trong phạm vi đó.

Nếu một queue có throughput 10 jobs/s và queue wait bình quân 3s, số jobs đang chờ bình quân gần 30 theo các giả định thích hợp.

Tăng batch size không tự làm giảm `W` nếu SMTP đã là bottleneck. Nó có thể chỉ chuyển backlog từ trạng thái `READY` trong database sang `PROCESSING`/executor queue.

## 12. fixedDelay, fixedRate và cron khác nhau

Spring Scheduling hỗ trợ:

- `fixedDelay`: lượt kế tiếp bắt đầu sau một khoảng delay kể từ **khi lượt trước hoàn tất**.
- `fixedRate`: cố gắng lập lịch theo nhịp giữa các lần bắt đầu, tùy scheduler/executor runtime.
- `cron`: kích hoạt ở những thời điểm calendar được chỉ định.

Ví dụ method poll mất 300ms, fixed delay 1s:

```text
Poll #1 start  0.0s
Poll #1 end    0.3s
Poll #2 start  1.3s
Poll #2 end    1.6s
Poll #3 start  2.6s
```

Với poller tuần tự:

\[
I_{\mathrm{eff}}\approx I_{\mathrm{configured}}+T_{\mathrm{poll}}
\]

Nếu `poll()` gửi toàn bộ batch đồng bộ, thời gian thực thi có thể dài hàng chục giây. Khi đó configured fixed delay 1s không đồng nghĩa bắt đầu mỗi giây. Fixed rate cũng không chữa provider throttling hay thiếu worker capacity.

## 13. Spring @Scheduled poller cơ bản

```java
@Configuration
@EnableScheduling
public class MailSchedulingConfiguration {
}
```

```java
@Component
public class MailOutboxPoller {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxPoller(
            MailOutboxDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.dispatch.poll-delay:PT1S}"
    )
    public void poll() {
        dispatcher.dispatchDue();
    }
}
```

Cấu hình ứng dụng:

```yaml
app:
  mail:
    dispatch:
      poll-delay: PT1S
      batch-size: 20
      max-in-flight: 40
      lease-duration: PT2M
```

`app.mail.dispatch.*` là **properties do ứng dụng tự xây**, không phải tính năng outbox tự động có sẵn trong `spring-boot-starter-mail`. Các durations nên có đơn vị rõ, ví dụ ISO `PT1S`.

## 14. Gửi trong poller hay giao sang worker?

**Cách A: poller gửi đồng bộ cả batch.**

```text
@Scheduled poll()
    claim B jobs
    for each job:
        render, send, update status
    return
    wait fixedDelay
```

Ưu điểm đơn giản, nhưng chu kỳ poll bị buộc vào SMTP latency. Một attempt treo có thể làm job mới đến hạn chờ lâu.

**Cách B: poller claim nhanh rồi giao cho bounded workers.**

```text
@Scheduled poll()
    calculate available slots
    atomic claim <= available slots
    submit jobs to bounded executor
    return quickly

Worker:
    load content, SMTP send, update status
```

Cách B thường tách nhịp poll khỏi network duration tốt hơn, nhưng phải có `maxInFlight`, bounded queue, lease, ownership và recovery. Không được claim hàng nghìn jobs chỉ để xếp chúng trong memory.

## 15. Batch thực tế nên phụ thuộc capacity

Một giới hạn:

\[
B_{\mathrm{claim}} \leq
\min(B_{\mathrm{configured}},K_{\mathrm{available}},B_{\mathrm{safeLease}},B_{\mathrm{policy}})
\]

Ví dụ:

```text
Configured batch          50
Idle worker slots          6
Free bounded queue slots   4
Safe new in-flight        10
Actual claim              <= 10
```

Nếu không muốn giữ job chờ sau khi claim, lấy tối đa 6. Nếu cho phép queue bounded, lease phải đủ dài hoặc được gia hạn thích hợp.

**Batch size là giới hạn trên, không phải chỉ tiêu bắt buộc mỗi poll.**

## 16. Rate limit độc lập với batch size

Provider có thể giới hạn số messages/giây, recipients/phút, số connections đồng thời và daily quota. Tăng send threads có thể làm tăng 421/4xx throttling.

Khi nhiều instances dùng chung một SMTP account, limiter nằm riêng trong mỗi JVM có thể làm tổng volume vượt quota. Cần global/shared rate coordination hoặc ngân sách được chia theo instance.

Recipient frequency cap (một người nhận tối đa N marketing emails trong một cửa sổ) cũng khác rate limit của provider. Poller không được lách consent/suppression chỉ vì SMTP còn capacity.

## 17. Một schema PostgreSQL outbox

```sql
CREATE TABLE mail_outbox (
    id               UUID PRIMARY KEY,
    notification_id  UUID NOT NULL UNIQUE,
    category         VARCHAR(40) NOT NULL,
    status           VARCHAR(30) NOT NULL,
    next_attempt_at  TIMESTAMPTZ NOT NULL,
    priority         INTEGER NOT NULL DEFAULT 0,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    locked_by        VARCHAR(100),
    lease_until      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Các trạng thái có thể gồm `READY`, `PROCESSING`, `RETRY_WAIT`, `SUBMITTED`, `FAILED`, `AMBIGUOUS`, `CANCELLED`, `EXPIRED`.

Query chỉ đọc jobs:

```sql
SELECT id
FROM mail_outbox
WHERE status IN ('READY', 'RETRY_WAIT')
  AND next_attempt_at <= NOW()
ORDER BY priority DESC, next_attempt_at, created_at, id
LIMIT :batch_size;
```

Nếu có nhiều pollers, **SELECT rồi gửi không đủ để chống trùng**. Hai instances có thể cùng thấy một row. Cần claim nguyên tử với locking/lease hoặc broker có ownership/ack semantics.

## 18. Atomic claim với FOR UPDATE SKIP LOCKED

Ví dụ PostgreSQL dùng một query claim và update trạng thái:

```sql
WITH eligible AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('READY', 'RETRY_WAIT')
        AND next_attempt_at <= NOW()
    )
    OR (
        status = 'PROCESSING'
        AND lease_until < NOW()
    )
    ORDER BY priority DESC, next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'PROCESSING',
    locked_by = :worker_id,
    lease_until =
        NOW() + (:lease_seconds * INTERVAL '1 second'),
    attempt_count = attempt_count + 1,
    updated_at = NOW()
FROM eligible
WHERE job.id = eligible.id
RETURNING job.id, job.attempt_count, job.lease_until;
```

Những named parameters được binding bởi repository. Claim transaction nên:

1. Chọn tối đa B records hợp lệ.
2. Bỏ qua rows mà transaction khác đang lock.
3. Chuyển chúng sang `PROCESSING`, ghi owner/lease/attempt.
4. Trả về đúng rows đã claim.
5. **Commit nhanh** trước khi render hoặc gửi SMTP.

`FOR UPDATE SKIP LOCKED` xử lý tranh chấp khóa **trong transaction claim**; `lease_until` và `locked_by` duy trì ownership **sau khi transaction đã commit**. Chúng không phải một cơ chế.

## 19. Không giữ DB transaction qua SMTP

Anti-pattern:

```text
BEGIN TRANSACTION
    SELECT 100 jobs FOR UPDATE
    for each job:
        JavaMailSender.send(...)
        update status
COMMIT
```

Hậu quả:

- Khóa DB rows và connections lâu.
- Timeout network làm transaction kéo dài.
- Rollback DB không rollback email đã gửi.
- Một batch có thể chứa email đã accepted nhưng DB status vẫn chưa commit.
- Contention tăng khi nhiều pollers chạy.

Cách làm nên là:

```text
Transaction #1: claim jobs, assign lease, COMMIT

Outside DB transaction:
    Render MIME and submit SMTP

Transaction #2 per job:
    Record outcome with ownership/version check, COMMIT
```

Nếu cần đồng bộ với nghiệp vụ, **insert mail intent/outbox cùng business transaction**. SMTP side effect vẫn chạy sau commit.

## 20. Index để poll jobs đến hạn

Ví dụ:

```sql
CREATE INDEX idx_mail_outbox_due
ON mail_outbox (
    next_attempt_at,
    priority DESC,
    created_at
)
WHERE status IN ('READY', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_lease
ON mail_outbox (lease_until)
WHERE status = 'PROCESSING';
```

Index phù hợp phụ thuộc actual query plan, tỷ lệ statuses và kích thước bảng. Query có `OR`/`ORDER BY` có thể không tận dụng mọi cột như mong đợi. Theo dõi scan count, buffer reads, update/WAL overhead và lock contention.

Không giảm poll interval khi database query vốn đã slow do thiếu index; điều đó chỉ nhân thêm tải.

## 21. Properties record với kiểu dữ liệu rõ

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.dispatch")
public record MailDispatchProperties(
    int batchSize,
    Duration pollDelay,
    int maxInFlight,
    Duration leaseDuration
) {}
```

Đăng ký:

```java
@Configuration
@EnableConfigurationProperties(MailDispatchProperties.class)
public class MailDispatchConfiguration {
}
```

Khi startup, cần validate `batchSize > 0`, `maxInFlight > 0`, durations dương, lease phù hợp với timeout thực tế và executor capacity. Có thể dùng Bean Validation theo dependency/version project.

Không im lặng chấp nhận batch size 0 hoặc poll delay âm khiến worker không chạy đúng.

## 22. Repository contract cho claim

```java
public record ClaimedMailJob(
    UUID jobId,
    UUID notificationId,
    int attemptNo,
    String workerId,
    Instant leaseUntil
) {}
```

```java
public interface MailOutboxRepository {

    List<ClaimedMailJob> claimDue(
        int maxCount,
        String workerId,
        Duration leaseDuration
    );

    void releaseIfOwned(ClaimedMailJob job);
}
```

Các types là hợp đồng do ứng dụng định nghĩa. Implementation `claimDue` phải dùng transaction ngắn và atomic SQL claim. `releaseIfOwned` chỉ trả trạng thái khi owner/attempt vẫn khớp.

Nếu dùng `@Transactional`, bảo đảm call đi qua Spring proxy hoặc dùng `TransactionTemplate`; tự gọi `@Transactional` method trong cùng object có thể không kích hoạt proxy transaction theo cấu hình mặc định.

## 23. Bounded dispatcher dùng Semaphore

Ví dụ dispatcher không claim quá số in-flight slots:

```java
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Semaphore;

import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;

@Service
public class MailOutboxDispatcher {

    private final MailOutboxRepository repository;
    private final MailSubmissionWorker worker;
    private final TaskExecutor executor;
    private final MailDispatchProperties settings;
    private final Semaphore slots;
    private final String workerId = UUID.randomUUID().toString();

    public MailOutboxDispatcher(
            MailOutboxRepository repository,
            MailSubmissionWorker worker,
            TaskExecutor executor,
            MailDispatchProperties settings) {
        this.repository = repository;
        this.worker = worker;
        this.executor = executor;
        this.settings = settings;
        this.slots = new Semaphore(settings.maxInFlight());
    }

    public void dispatchDue() {
        int reserved = 0;

        while (reserved < settings.batchSize()
                && slots.tryAcquire()) {
            reserved++;
        }

        if (reserved == 0) {
            return;
        }

        List<ClaimedMailJob> jobs;

        try {
            jobs = repository.claimDue(
                reserved, workerId, settings.leaseDuration()
            );
        } catch (RuntimeException exception) {
            slots.release(reserved);
            throw exception;
        }

        slots.release(reserved - jobs.size());

        for (ClaimedMailJob job : jobs) {
            try {
                executor.execute(() -> {
                    try {
                        worker.process(job);
                    } finally {
                        slots.release();
                    }
                });
            } catch (TaskRejectedException exception) {
                slots.release();
                repository.releaseIfOwned(job);
            }
        }
    }
}
```

Đây là **mẫu minh họa giới hạn capacity**, không phải worker library hoàn chỉnh:

- `claimDue` phải có transaction/lease đúng.
- Nếu executor reject và `releaseIfOwned` cũng lỗi, lease recovery là fallback.
- `worker.process` phải ghi status/retry hoặc có recovery.
- Semaphore là in-memory per instance, không thay global SMTP quota.
- Khi process crash, semaphore mất nhưng durable jobs phải được reclaim.
- Nếu nhiều threads có thể gọi `dispatchDue` đồng thời, cần thiết kế serialization/capacity phù hợp.
- Nếu dispatcher crash sau claim nhưng trước task submission, jobs phục hồi sau lease expiry.

Điểm cốt lõi: **acquire capacity trước khi claim** và luôn release permits khi task kết thúc.

## 24. ThreadPoolTaskExecutor cũng phải bounded

```java
@Bean(name = "mailSubmissionExecutor")
public ThreadPoolTaskExecutor mailSubmissionExecutor() {
    ThreadPoolTaskExecutor executor =
        new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(12);
    executor.setThreadNamePrefix("smtp-mail-");
    executor.initialize();

    return executor;
}
```

Với 8 worker threads và queue 12, một `maxInFlight` khoảng 20 có thể phù hợp về **số tasks tối đa**, nhưng vẫn phải xét lease, SMTP size và quota.

Cảnh báo:

- Executor queue không giới hạn dễ gây memory pressure.
- `CallerRunsPolicy` có thể khiến SMTP chạy trong scheduler hoặc request thread; dùng có chủ đích.
- In-memory tasks không thay durable outbox.
- Claim phải tương ứng slots thực, không tương ứng số CPU cores mơ hồ.

## 25. Worker gửi mail và lưu trạng thái

Ví dụ pseudocode gần Java:

```java
public void process(ClaimedMailJob claim) {
    UUID notificationId = claim.notificationId();

    if (!eligibility.permitsSendingNow(notificationId)) {
        states.markSuppressedIfOwned(claim);
        return;
    }

    try {
        PreparedMail mail = contents.loadPrepared(notificationId);
        smtpDelivery.submit(mail);
        states.markSubmittedIfOwned(claim);
    } catch (TemporaryMailFailure exception) {
        states.scheduleRetryIfOwned(claim, exception);
    } catch (PermanentMailFailure exception) {
        states.markFailedIfOwned(claim, exception);
    } catch (AmbiguousMailFailure exception) {
        states.markAmbiguousIfOwned(claim, exception);
    }
}
```

`eligibility`, `states`, `contents`, `smtpDelivery` và các exception types là abstractions của ứng dụng. Không phải `JavaMailSender` mặc định trả ra một enum outcome.

Không được catch mọi SMTP exception rồi giả định chắc chắn server chưa nhận message. Kết quả có thể **AMBIGUOUS** nếu response bị mất sau khi relay có thể đã chấp nhận DATA.

## 26. Lease duration phải cân với in-flight

Nếu claim 100 jobs, có 10 workers, SMTP P95 là 3s và lease 30s, jobs cuối có thể chỉ bắt đầu khi lease gần hết.

Các giải pháp:

- Claim gần thời điểm task bắt đầu.
- Giảm `batchSize` hoặc `maxInFlight`.
- Giới hạn executor queue depth.
- Chọn lease theo worst expected processing time.
- Gia hạn lease khi thực thi lâu, nếu có cơ chế heartbeat.
- Kiểm tra ownership khi bắt đầu và khi cập nhật status.
- Thiết kế recovery cho worker crash.

Lease quá dài cũng không tốt: khi worker chết, job bị giữ lâu trước reclaim. Không có con số lease thích hợp cho mọi hệ thống.

## 27. Fencing stale owners

Worker A có thể hết lease rồi worker B reclaim job. Nếu A tỉnh lại, nó không được ghi đè trạng thái B đang sở hữu.

```sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    locked_by = NULL,
    lease_until = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND status = 'PROCESSING'
  AND locked_by = :worker_id
  AND attempt_count = :claimed_attempt;
```

Nếu affected rows bằng 0, owner/attempt đã đổi. Không update mù quáng theo job ID.

Fencing bảo vệ **database state**, không thể hoàn tác một SMTP submission worker A đã thực hiện. Đây là lý do cần idempotency, lease management và xử lý ambiguous attempts.

## 28. Polling interval không phải retry interval

Khi provider trả temporary failure, không nên đưa job về READY và để poller chạy lại nó mỗi 100ms.

```text
SMTP temporary error
        |
        v
Classify + exponential backoff + jitter
        |
        v
status=RETRY_WAIT
nextAttemptAt=now + backoff
        |
        v
Poller chỉ claim khi đến hạn
```

Ví dụ công thức:

\[
d_n=\min(d_{\max},d_0\cdot2^{n-1})+\mathrm{jitter}
\]

Một poller chạy mỗi giây có thể hoàn toàn phù hợp với job retry sau hai phút, bởi điều kiện `nextAttemptAt` là cơ chế quyết định eligibility.

Không dùng `Thread.sleep` lâu bên trong SMTP worker để chờ retry; lưu lại lịch trong DB và giải phóng capacity.

## 29. SMTP submission outcome khác delivery

| Trạng thái | Ý nghĩa |
| --- | --- |
| `READY` | Có job đến hạn, chưa claim |
| `PROCESSING` | Worker sở hữu lease và đang làm |
| `SUBMITTED` | SMTP transport/relay báo thành công |
| `RETRY_WAIT` | Chờ thời điểm retry |
| `FAILED` | Không retry theo policy |
| `AMBIGUOUS` | Chưa biết chắc server đã nhận hay chưa |
| `DELIVERED` | Có bằng chứng downstream từ provider theo định nghĩa nguồn |

`JavaMailSender.send(...)` thành công không có nghĩa người nhận đã thấy thư trong Inbox. Provider còn có thể filter, defer hoặc bounce.

Một SMTP timeout sau DATA có thể xảy ra khi relay đã tiếp nhận nhưng client không thấy final response. Retry có nguy cơ gửi trùng. Batch/poll không tự bảo đảm exactly-once delivery.

## 30. Nhiều instances và tổng poll load

Giả sử mỗi instance batch 20, poll mỗi giây, có 5 instances:

```text
5 instances × 20 jobs/poll × 1 poll/s
≈ 100 jobs/s claim supply upper bound
```

Đây không phải throughput được bảo đảm. Database atomic claim, SMTP rate và tổng concurrency mới quyết định thực tế.

Khi autoscale:

- Tổng DB poll queries tăng.
- Tổng `maxInFlight` tăng.
- Per-JVM rate limiter có thể vượt global provider quota.
- Các instances có thể poll đồng thời gây spikes.
- Jobs cần ownership/lease IDs để tra cứu.
- Priority/fairness cần nhất quán giữa workers.

Có thể chọn một leader poller hoặc nhiều pollers với atomic claims. Leader giảm query duplication nhưng tạo điểm phải failover; nhiều pollers tăng scalability nhưng cần rate coordination. Chọn theo quy mô và HA goals.

## 31. Fairness giữa OTP và newsletter

Nếu một campaign tạo hàng chục nghìn jobs, một poller đơn giản `ORDER BY priority DESC` có thể chiếm hết slots hoặc khiến category ưu tiên thấp bị starvation.

Các chiến lược:

- Queues riêng theo security/transactional/marketing.
- Reserved worker capacity cho high-priority mail.
- Batch quotas theo category.
- Weighted fair scheduling.
- Provider budgets phân tách theo loại mail khi phù hợp.
- Deadline-aware processing.
- Limiting per tenant/campaign.

Không chỉ tăng batch để cải thiện OTP latency khi newsletter đang chiếm hết sender threads. Tách queue/capacity thường hiệu quả hơn.

## 32. Một batch không đồng nghĩa một MIME message

Với 1.000 recipients:

- 1.000 jobs mỗi job một recipient.
- 100 jobs mỗi job 10 recipients.
- 1 job với 1.000 recipients.

Ba cách có cùng số recipient nhưng batch size DB, provider quota và khả năng theo dõi bounce/consent khác nhau.

Nếu cần personalization, unsubscribe và per-recipient delivery tracking, một notification logic theo recipient thường dễ điều hành hơn, dù số jobs lớn hơn. Không so sánh batch theo job với quota theo recipient nếu chưa chuẩn hóa đơn vị.

## 33. Adaptive polling khi rỗng và khi có backlog

Một chiến lược:

```text
Empty polls repeatedly
       |
       v
Increase idle delay (bounded)
       |
       v
New job wake-up OR next periodic poll
       |
       v
Jobs available and worker capacity free
       |
       v
Use shorter busy delay / bounded drain
```

Ví dụ cấu hình app-specific:

```yaml
app:
  mail:
    dispatch:
      idle-poll-delay: PT5S
      busy-poll-delay: PT0.5S
      batch-size: 25
```

Đây không phải chức năng tự xuất hiện từ `@Scheduled(fixedDelayString=...)`. Muốn thay đổi interval động, có thể dùng `TaskScheduler` hoặc worker loop được thiết kế riêng.

Không giảm busy delay vô hạn khi worker đã đầy hoặc provider bị outage: lúc đó polling thêm chỉ tốn DB.

## 34. Jitter khi nhiều instances đồng loạt polling

Nếu nhiều instances cùng khởi động:

```text
Instance A: 0s, 1s, 2s, 3s
Instance B: 0s, 1s, 2s, 3s
Instance C: 0s, 1s, 2s, 3s
```

DB có thể thấy nhiều claims cùng thời điểm. Có thể dùng startup staggering hoặc một chút jitter cho lịch polling; trong khi SQL atomic claim vẫn đảm bảo an toàn.

Jitter chỉ làm mượt load, không thay thế index/locking và không được làm vi phạm SLO phát hiện job.

## 35. Cron, timezone và scheduled_at

Nếu job có `nextAttemptAt` trong tương lai:

- Lưu thời điểm thực bằng UTC/`Instant`.
- Tính quiet hours theo `ZoneId` của người nhận nếu nghiệp vụ yêu cầu.
- Xử lý DST (giờ lặp/thiếu) khi quy đổi local schedule.
- Kiểm tra expiry/deadline trước submit.
- Giữ application/database clock đủ đồng bộ cho time comparisons.

Ví dụ job due lúc 09:00:01 có thể bị phát hiện gần 09:01 nếu polling mỗi phút. Tối ưu interval không sửa lỗi timezone, lịch đến hạn bị tính sai hoặc business state thay đổi.

## 36. Backlog khi provider outage

Trong SMTP outage:

```text
SMTP 421 / connection failures increase
          |
          v
Worker attempts slow / fail
          |
          v
RETRY_WAIT and READY backlog increase
          |
          v
Poller still queries frequently
```

Tăng batch trong trường hợp này có thể làm nhiều jobs bị claim rồi lại retry, tạo storm. Nên:

1. Phân loại temporary/permanent/configuration errors.
2. Giảm rate và concurrency theo provider cooldown.
3. Lưu `nextAttemptAt` cho retry.
4. Dùng jitter để tránh retry đồng loạt.
5. Giữ job trong durable store, không đẩy vô hạn vào memory.
6. Quan sát backlog tuổi và business deadline.
7. Cân nhắc circuit breaker để ngừng claim cho provider đang lỗi.

Một provider outage không được chữa bằng cách poll DB nhanh hơn.

## 37. Metrics cho poller và sender

| Metric gợi ý | Câu hỏi trả lời |
| --- | --- |
| `mail_poll_total` | Đã poll bao nhiêu lượt? |
| `mail_poll_empty_total` | Tỷ lệ poll rỗng? |
| `mail_poll_duration_seconds` | Query/dispatch mất bao lâu? |
| `mail_claim_batch_size` | Mỗi poll claim được bao nhiêu? |
| `mail_ready_count` | Có bao nhiêu jobs chờ? |
| `mail_oldest_due_age_seconds` | Job đến hạn lâu nhất bao nhiêu tuổi? |
| `mail_processing_count` | Bao nhiêu jobs đang có lease? |
| `mail_expired_lease_total` | Bao nhiêu jobs bị reclaim? |
| `mail_send_inflight` | Bao nhiêu attempts đang xử lý? |
| `mail_smtp_duration_seconds` | SMTP attempt P50/P95/P99? |
| `mail_submission_total` | Outcome theo provider/category? |
| `mail_retry_scheduled_total` | Retry tăng bao nhiêu? |
| `mail_executor_rejected_total` | Executor có quá tải? |
| `mail_provider_throttle_total` | Provider đang throttling? |

Tên metric là ví dụ do ứng dụng định nghĩa, **không phải metrics Spring Mail mặc định**.

Phải phân biệt backlog `READY` đang đến hạn, `RETRY_WAIT` chưa đến hạn và `PROCESSING` chưa hết lease. Gộp tất cả sẽ khiến operator hiểu sai tình trạng.

Không dùng email address hoặc notification ID làm metric label vì PII và high cardinality.

## 38. Structured logs và correlation

Mỗi email logic nên có `notificationId` ổn định; mỗi attempt có `attemptId`.

```json
{
  "event": "mail.outbox.claimed",
  "notificationId": "N-2105",
  "attemptId": "A2",
  "workerId": "mail-worker-3",
  "claimBatchSize": 12,
  "status": "PROCESSING",
  "leaseUntil": "2026-11-12T10:05:00Z"
}
```

Khi SMTP thành công:

```json
{
  "event": "mail.smtp.submitted",
  "notificationId": "N-2105",
  "attemptId": "A2",
  "provider": "primary-smtp",
  "smtpDurationMs": 742,
  "outcome": "SUBMITTED"
}
```

Traces có thể mất context khi đi qua outbox/worker sau commit. Correlation ID bền vững giúp nối business event, poller, SMTP attempt và provider event.

Không ghi password, OTP, raw MIME body hoặc attachment contents vào telemetry.

## 39. Hai bài toán ví dụ

### Ví dụ A: OTP cần phát hành nhanh

Giả sử total submit P95 target là 3 giây, SMTP P95 khoảng 1,1 giây, prepare/update khoảng 0,3 giây. Phần ngân sách còn lại cho detection/queue/rate delay chỉ khoảng 1,6 giây, theo phép ước lượng giản lược.

Polling 5 giây có thể làm riêng detection delay P95 gần 4,75 giây trong mô hình arrival đều, không đạt mục tiêu. Cần interval thấp hơn hoặc wake-up mechanism, với điều kiện DB/SMTP có đủ capacity.

Batch không nhất thiết phải lớn: chỉ cần đủ đưa due jobs cho các worker slots rảnh. OTP cũng cần TTL và anti-abuse; không gửi token đã hết hạn chỉ để "clear backlog".

### Ví dụ B: chiến dịch 36.000 emails trong 2 giờ

Tốc độ trung bình tối thiểu lý thuyết:

\[
36{,}000/(2\cdot3600)=5\ \text{jobs/s}
\]

Nếu provider chỉ cho phép 3 messages/s, không bộ batch/interval nào giúp hoàn thành đúng hai giờ mà vẫn tôn trọng quota. Phải thay đổi kế hoạch hoặc năng lực provider hợp lệ.

Nếu sender capacity là 8 jobs/s, batch 40 mỗi chu kỳ thực tế 5 giây cấp khoảng 8 jobs/s, có thể thiếu headroom cho retries và bất thường. Tuning phải dựa trên P95 và peak traffic, không chỉ giá trị trung bình đẹp.

## 40. Load tests và integration tests

**Unit tests:**

- `batchSize=0` hoặc delay âm không được chấp nhận.
- Không có free slots thì không claim DB.
- Batch configured 20 nhưng chỉ 5 permits thì claim <=5.
- Claim được 2/5 rows phải release 3 permits thừa.
- Executor reject task thì release permit, durable job vẫn được recovery.
- Job chưa tới `nextAttemptAt` không được claim.
- Worker hoàn tất hoặc ném lỗi đều giải phóng capacity.

**Database integration tests:**

- Hai pollers cạnh tranh cùng rows không cùng claim một ownership.
- `SKIP LOCKED` xử lý records đang khóa.
- Batch limit được tôn trọng.
- Expired lease được reclaim.
- Stale owner không ghi đè kết quả của owner mới.
- Race giữa cancel/expire và claim không làm gửi không hợp lệ.
- Query plan ổn với bảng nhiều rows đã xử lý.

**SMTP integration tests:**

- GreenMail hoặc SMTP capture server nhận đúng số messages trong happy path.
- Lỗi tạm thời được lưu `RETRY_WAIT` với backoff.
- Không làm mất jobs khi SMTP server tạm offline.
- DB state failure sau SMTP accepted được xử lý theo duplicate policy.
- Rate limiter không vượt quota mô phỏng.
- Không dựa vào `send()` success để báo delivered.

**Load tests:**

- Workload idle, steady, burst và provider outage.
- Kích thước message nhỏ/lớn, attachment I/O.
- Multi-instance autoscaling.
- Crash/restart khi đã claim.
- Metrics P50/P95/P99 queue age, SMTP duration, DB claim time.
- Trạng thái lease expirations và executor rejects.

Không chạy load test bằng email recipients production để tránh spam, quota và rò dữ liệu.

## 41. Tuning theo vòng lặp có kiểm soát

1. Đo baseline traffic: arrival rate, batch, effective poll cycle, concurrency và quota.
2. Tạo workload đại diện, gồm retries và attachments lớn.
3. Xác định bottleneck: poller supply, SMTP threads, provider, storage hay DB.
4. Nếu poller supply thấp trong khi worker rảnh, tăng batch vừa phải hoặc giảm interval.
5. Nếu empty polls rất nhiều, tăng idle interval hoặc dùng wake-up.
6. Nếu worker đầy/provider throttled, không claim thêm chỉ vì backlog tăng.
7. Giới hạn maxInFlight, queue depth và lease validity.
8. Theo dõi P95/P99 latency, expired leases, rejection và DB load.
9. Kiểm tra nhiều instances làm thay đổi tổng poll rate thế nào.
10. Test outage/recovery trước khi áp dụng production.
11. Thay đổi từng nhóm thông số để xác định nguyên nhân.
12. Duy trì headroom, theo dõi sau deploy và rollback khi metrics xấu.

Không auto-tune chỉ dựa trên backlog length. Backlog tăng có thể do provider outage, lúc đó tăng batch chỉ làm thêm in-flight/failed attempts.

## 42. Runbook nhanh khi có sự cố

| Triệu chứng | Kiểm tra | Hướng xử lý |
| --- | --- | --- |
| READY backlog tăng, worker rảnh | Poll interval thực tế, batch, SQL time | Tối ưu claim/batch/interval |
| READY backlog tăng, worker luôn đầy | SMTP P95, quota, render I/O | Nâng capacity hợp lệ hoặc pacing |
| Nhiều poll rỗng | Empty ratio, app instance count | Tăng idle delay, wake-up |
| PROCESSING nhiều, lease hết | In-flight, executor queue, SMTP timeout | Giảm claim, quản lý lease |
| Nhiều SMTP 421/4xx | Provider quota/cooldown | Giảm rate, backoff |
| Transactional chậm khi marketing lớn | Category fairness, shared pool | Tách queue/budget |
| Một email gửi trùng | Claim race, stale owner, ambiguous send | Atomic claim, fencing, reconcile |
| DB CPU/query tăng sau scale-out | Poll volume, query plan, locks | Adjust interval/index/coordination |
| Job không bao giờ được gửi | `nextAttemptAt`, expiry, suppression, owner | Phân loại state và điều tra |
| SMTP accepted nhưng khách chưa nhận | Provider delivery/bounce events | Không coi polling là delivery evidence |

## 43. Những anti-pattern cần tránh

| Sai lầm | Hệ quả |
| --- | --- |
| Chọn batch 1.000 để "gửi nhanh" | Lease expiry, memory pressure, duplicates |
| Poll 10ms dù gần như luôn rỗng | DB query storm |
| Dùng batch size làm SMTP rate limiter | Provider throttling |
| Dùng interval cấu hình như actual cycle | Capacity ước lượng sai |
| `SELECT` rồi gửi không claim nguyên tử | Nhiều instances gửi trùng |
| Giữ DB transaction qua SMTP | Long locks, DB rollback không rollback mail |
| Claim nhiều hơn executor capacity | Tasks chờ, hết lease |
| Dùng in-memory queue làm nguồn công việc | Mất jobs khi process restart |
| Retry mỗi poll không có backoff | Retry storm |
| Lease rất dài để che bottleneck | Crash recovery chậm |
| Không fencing owner đã hết lease | Stale update ghi sai status |
| Không ưu tiên OTP so với newsletter | Security mail bị chậm |
| Coi `send()` thành công là delivered | Báo cáo sai |
| Coi timeout là chắc chắn chưa gửi | Duplicate sau retry |
| Dùng raw recipient làm metric label | PII và cardinality rất cao |
| Chỉ xem average mà bỏ P95/P99 | Bỏ qua tail latency và expiry |

## 44. Ví dụ bộ cấu hình **để thử nghiệm**, không phải chuẩn chung

```yaml
app:
  mail:
    dispatch:
      batch-size: 20
      poll-delay: PT1S
      max-in-flight: 20
      lease-duration: PT2M
      max-attempts: 5
```

Chỉ có ý nghĩa sau khi kiểm tra:

- Workload peak và mail size.
- SMTP provider rate/concurrency quota.
- Worker pool và bounded queue phù hợp.
- Lease vượt duration cần thiết hoặc có renewal.
- DB claim queries không quá tải.
- Backoff/circuit breaker cho provider failures.
- Deadline và suppression được kiểm tra trước submit.
- Category fairness không làm OTP chậm.
- P95/P99 đáp ứng SLO bằng đo lường thực.

Ứng dụng gửi một email/phút có thể cần bộ số hoàn toàn khác ứng dụng gửi hàng chục nghìn email/giờ.

## 45. Checklist triển khai

1. Định nghĩa rõ đơn vị batch là **outbox job**, không nhầm recipients.
2. Xác định SLO từ commit/due tới SMTP accepted.
3. Đo arrival peak, SMTP duration và provider quota.
4. Chọn bounded worker pool, maxInFlight và lease trước khi tăng batch.
5. Coi batchSize là **trần**, claim theo capacity còn trống.
6. Hiểu `fixedDelay` khác `fixedRate` và đo poll cycle thật.
7. Dùng atomic claim/lease/owner fencing, transaction ngắn.
8. Không gửi SMTP dưới DB lock.
9. Tách retry backoff khỏi polling interval.
10. Có global provider rate coordination khi chạy nhiều instances.
11. Giữ category fairness giữa transactional và bulk mail.
12. Đo empty poll, claim time, ready age, in-flight, expired lease và SMTP outcomes.
13. Test concurrency, outage, restart và ambiguous send.
14. Tuning từng biến từ metrics, không copy blindly.
15. Giữ durable status và notification ID xuyên mọi attempts.

## 46. Ghi nhớ

- Batch size quyết định **số jobs tối đa được claim trong một lượt**.
- Polling interval quyết định **nhịp phát hiện jobs đến hạn**.
- Chúng khác sender concurrency, provider rate limit và retry interval.
- Claim supply xấp xỉ `batchSize / effectivePollCycle` khi luôn đủ jobs.
- Throughput thực bị giới hạn bởi SMTP latency/concurrency, provider, DB và storage.
- Với `fixedDelay`, chu kỳ thực tế bao gồm thời gian chạy poll method.
- Batch quá nhỏ có thể để worker rảnh; batch quá lớn gây queueing và lease expiry.
- Poll quá nhanh tạo database load; poll quá chậm làm detection latency tăng.
- Claim theo available capacity, không dồn vô hạn jobs vào executor.
- `FOR UPDATE SKIP LOCKED` giúp nhiều pollers claim an toàn trong transaction ngắn.
- Lease cần owner/version guard và recovery, không phải DB lock giữ mãi.
- Retry dùng `nextAttemptAt` + backoff/jitter, không gửi lại sau mỗi poll.
- Multi-instance làm tăng tổng poll load và global quota pressure.
- SMTP timeout sau DATA có thể AMBIGUOUS, dẫn đến duplicate khi retry.
- Monitoring cần tách READY, RETRY_WAIT chưa đến hạn và PROCESSING leases.
- Chọn số theo SLO, peak volume và load tests thực tế.

**Nguyên tắc cốt lõi:** Hãy chọn **batch size đủ lớn để lấp đầy capacity đang rảnh nhưng không lớn tới mức claim jobs trước khi có thể xử lý**, và chọn **polling interval đủ ngắn để đạt detection-latency SLO nhưng không gây polling load vô ích**. Spring Framework Mail outbox vận hành tốt nhờ atomic claim, bounded in-flight, SMTP quota control, retry scheduling và observability — không phải nhờ một số batch hoặc nhịp SELECT lớn nhất.

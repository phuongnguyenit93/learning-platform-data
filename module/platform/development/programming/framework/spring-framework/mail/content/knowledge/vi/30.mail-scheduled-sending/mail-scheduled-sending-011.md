# Theo dõi job gửi và các lần chạy

Trong **Spring Framework Mail**, một tính năng gửi email có thể bắt đầu từ một business event, HTTP request hoặc một công việc chạy theo lịch. Ở hệ thống có **@Scheduled**, nhiều workers, transactional outbox và retry, việc thấy log “đã chạy job” không đủ để kết luận mọi email được gửi đúng. Một scheduler run có thể xử lý hàng trăm mail events, một event có thể được thử qua SMTP nhiều lần, và một lần SMTP trả thành công không chứng minh message đã vào hộp thư người nhận.

**Theo dõi job gửi và các lần chạy** nhằm ghi nhận lịch sử thực thi một cách có thể kiểm chứng: job nào được kích hoạt, thực sự chạy khi nào, trên instance nào, claim được bao nhiêu sự kiện, xử lý thành công bao nhiêu, lỗi ở đâu, có job nào bị kẹt hoặc không chạy theo lịch không, và cần retry những gì.

Bài học thuộc chương **Lập lịch gửi** trong chủ đề **Spring Framework Mail**. Nội dung đi từ mô hình job/run/outbox/attempt, trạng thái, database schema, Spring Scheduling, distributed coordination, transaction boundaries đến Micrometer, structured logs, tracing, Prometheus, dashboard, cảnh báo, khôi phục và kiểm thử.

Những nguyên tắc quan trọng:

- **Job definition** không phải **job run**; một run không phải một email.
- **Mail event** không phải **SMTP attempt**; retry có thể tạo nhiều attempts cho một event.
- Run thành công có thể chỉ cho biết **dispatcher hoàn thành công việc**, không đồng nghĩa mọi email được delivered.
- Cần phân biệt scheduled time, actual start, queue delay, run duration và SMTP send-call duration.
- Với nhiều worker, cần atomic outbox claims/lease; chỉ có @Scheduled không bảo đảm độc quyền giữa các nodes.
- Crash sau khi SMTP relay đã chấp nhận message nhưng trước khi cập nhật database có thể tạo **duplicate window**.
- Metrics để xem xu hướng; logs/trace để điều tra; durable run và attempt records để đối soát sau crash.

## 1. Bốn đơn vị theo dõi khác nhau

| Đơn vị | Mô tả | Ví dụ |
| --- | --- | --- |
| **Job definition** | Định nghĩa lịch/dispatcher | mail-outbox-dispatcher |
| **Job run** | Một execution cụ thể | run-001 |
| **Mail event** | Ý định gửi bền vững từ nghiệp vụ | ORDER_CONFIRMED:1001 |
| **SMTP attempt** | Một lần thử gửi qua JavaMailSender | attempt-003 |

Sơ đồ:

~~~text
Job: mail-outbox-dispatcher
       |
       +--- Run R1
       |       |
       |       +--- Event A -> Attempt A1 -> success
       |       +--- Event B -> Attempt B1 -> retryable error
       |       +--- Event C -> Attempt C1 -> success
       |
       +--- Run R2
               |
               +--- Event B -> Attempt B2 -> success
               +--- Event D -> Attempt D1 -> success
~~~

Một run xử lý nhiều mail events; một event có thể được xử lý qua nhiều runs; mỗi event có thể có nhiều SMTP attempts.

### 1.1. Định nghĩa job

Có thể gồm cron/fixedDelay, timezone, batch size, concurrency, enabled flag và routing policy.

### 1.2. Định danh run

Mỗi lần scheduler thực sự bắt đầu một execution, cấp runId mới. Nếu chạy lại thủ công, đó cũng là một execution khác.

### 1.3. Định danh event

MailEventId phải ổn định qua retry cho cùng ý định gửi. Business idempotency giúp tránh tạo nhiều events từ một nghiệp vụ trùng lặp.

### 1.4. Định danh attempt

Mỗi lần thực sự gọi SMTP transport có attemptId, provider, thời gian bắt đầu/kết thúc và kết quả riêng.

## 2. Vì sao log Start/Finish đơn giản dễ gây hiểu nhầm?

Ví dụ:

~~~java
@Scheduled(fixedDelayString = "5000")
public void sendPending() {
    log.info("Mail job started");

    for (MailJob job : repository.findPending()) {
        mailSender.send(buildMessage(job));
    }

    log.info("Mail job finished");
}
~~~

Code không có runId, không đo thời gian, không biết processed count, không ghi lịch sử attempts, không phân biệt không có việc với lỗi database. Nếu sender ném exception, log finished không chạy. Nếu hai instances cùng SELECT PENDING, cả hai có thể gửi cùng một mail event.

Cần thiết kế một cơ chế theo dõi có ranh giới và trạng thái rõ ràng.

## 3. Kiến trúc theo dõi end-to-end

~~~text
Cron / fixedDelay / manual trigger
                |
                v
       Record job run STARTED
                |
                v
      Optional scheduler lock
                |
                v
   Atomic claim eligible outbox rows
                |
                v
    Validate / Render / Build MIME
                |
                v
       Create SMTP attempt
                |
                v
      JavaMailSender.send(...)
                |
        +-------+-------+
        |       |       |
     Success  Failure  Unknown
        |       |       |
        v       v       v
   Outbox state transition
                |
                v
      Finalize run summary
                |
                v
       Metrics / logs / traces
~~~

Mỗi bước phục vụ câu hỏi khác nhau. Scheduler có thể hoàn tất việc enqueue vào durable queue trước khi SMTP chạy; khi đó phải nói rõ run đã hoàn thành **enqueuing**, không phải sending.

## 4. Các ID cần có

Một quy ước:

~~~text
jobName     = mail-outbox-dispatcher
runId       = UUID for one execution
mailEventId = durable UUID for one business intent
attemptId   = UUID for one SMTP submission
workerId    = node/process instance alias
traceId     = distributed tracing context
~~~

Không trộn các IDs:

- RunId dùng để xem một execution của lịch.
- MailEventId dùng đối soát retry của một ý định gửi.
- AttemptId dùng chẩn đoán lần SMTP cụ thể.
- WorkerId dùng phát hiện instance lỗi.
- TraceId dùng nối các bước trong telemetry, không thay business id.

**Không đưa runId, mailEventId, attemptId hay recipient vào metric labels**: các giá trị này có cardinality rất lớn và có thể liên kết tới thông tin riêng tư.

## 5. Vòng đời của job run

Một state machine gợi ý:

~~~text
SCHEDULED (nếu hệ thống lưu planned triggers)
      |
      v
STARTING
      |
      +-- cannot acquire lock -> SKIPPED
      |
      v
RUNNING
      |
      +-- no due events -> SUCCEEDED_EMPTY
      |
      +-- all work done -> SUCCEEDED
      |
      +-- mixed outcomes -> PARTIAL
      |
      +-- infrastructure error -> FAILED
      |
      +-- cancelled -> CANCELLED
      |
      +-- crash / no heartbeat -> STALE
~~~

Các trạng thái là **quy ước do ứng dụng thiết kế**, không phải enum mặc định của JavaMailSender.

### 5.1. SUCCEEDED_EMPTY không phải lỗi

Run tìm đúng queue và không có mail event đến hạn là một lần chạy hợp lệ. Nó giúp phân biệt scheduler còn sống với scheduler không chạy.

### 5.2. PARTIAL có ngữ nghĩa theo hợp đồng

Nếu run đã gửi 80 thư và đưa 20 thư vào RETRY_WAIT, có thể ghi PARTIAL. Nếu contract của run chỉ là “xử lý đúng mỗi event và cập nhật state”, một run cũng có thể SUCCEEDED về mặt điều phối. Điều quan trọng là **định nghĩa status công khai và hiển thị counters**.

### 5.3. STALE không chứng minh SMTP chưa gửi

Một process crash không kịp ghi kết quả có thể đã gửi thành công một phần. Không replay toàn run dựa trên status STALE.

### 5.4. Skipped trigger có thể không tạo run

Nếu ShedLock chặn method trước khi code bên trong chạy, không có run record được tạo trong method. Muốn đo skipped triggers, instrument tầng scheduler/lock provider.

## 6. Vòng đời của mail event

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- submit success --> SENT
   |
   +-- known temporary error --> RETRY_WAIT
   |
   +-- permanent error --> FAILED
   |
   +-- ambiguous SMTP result --> UNKNOWN_OUTCOME
   |
   +-- lease expired --> RECOVERY_ELIGIBLE
~~~

RECOVERY_ELIGIBLE có thể suy từ PROCESSING và claim_until đã hết.

### 6.1. SENT là mốc submission

JavaMailSender.send trả bình thường thường cho thấy lời gọi transport hoàn tất theo kết quả phía client. Nó **không chứng minh inbox delivery hoặc read**.

### 6.2. RETRY_WAIT có thời điểm riêng

nextAttemptAt là thời điểm mail event có thể được thử lại, không phải lịch cron của scheduler.

### 6.3. UNKNOWN_OUTCOME phải tách khỏi failure chắc chắn

SMTP client có thể đã truyền DATA nhưng mất final response, nên relay có thể đã chấp nhận message. Retry có nguy cơ gửi trùng.

## 7. Ví dụ timeline và số đếm

~~~text
10:00 Run R1 starts
10:01 R1 claims A, B, C
10:02 A attempt 1 -> success
10:03 B attempt 1 -> temporary failure
10:04 C attempt 1 -> success
10:05 R1 -> PARTIAL

10:06 Run R2 -> no due events -> SUCCEEDED_EMPTY

10:07 Run R3 claims B after retry deadline
10:08 B attempt 2 -> success
10:09 R3 -> SUCCEEDED
~~~

Tổng: **3 runs**, **3 unique mail events**, **4 SMTP attempts**, **3 mail events submit thành công cuối cùng** và **1 attempt lỗi tạm thời**.

Không thể gọi 4 attempts là 4 emails delivered.

## 8. Job definition và cấu hình lịch

Một bảng tùy chọn:

~~~sql
CREATE TABLE mail_job_definition (
    job_name VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_type VARCHAR(32) NOT NULL,
    cron_expression VARCHAR(120),
    timezone_id VARCHAR(64),
    batch_size INTEGER NOT NULL DEFAULT 50,
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    config_version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Schema minh họa cho PostgreSQL. Nếu lịch được viết bằng @Scheduled annotation và cấu hình source, bảng này không phải yêu cầu bắt buộc.

### 8.1. Lưu version hoặc snapshot

Khi đổi cron, batch size hoặc concurrency, dữ liệu version giúp giải thích vì sao runs cũ xử lý khác.

### 8.2. Enabled và maintenance

Cảnh báo missed run cần phân biệt job bị tắt có chủ đích với việc scheduler chết.

### 8.3. Timezone

Lịch 09:00 theo Asia/Ho_Chi_Minh không tương đương 09:00 UTC. Luôn chọn timezone theo yêu cầu nghiệp vụ.

## 9. Database schema cho job runs

~~~sql
CREATE TABLE mail_job_run (
    run_id UUID PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    status VARCHAR(32) NOT NULL,
    trigger_type VARCHAR(32) NOT NULL,
    scheduled_for TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    last_progress_at TIMESTAMPTZ,
    instance_id VARCHAR(128),
    config_version INTEGER,
    claimed_count INTEGER NOT NULL DEFAULT 0,
    submit_success_count INTEGER NOT NULL DEFAULT 0,
    submit_failure_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    error_category VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mail_run_by_start
    ON mail_job_run(job_name, started_at DESC);

CREATE INDEX idx_mail_run_stale
    ON mail_job_run(status, heartbeat_at);
~~~

### 9.1. planned và actual là hai mốc

scheduled_for chỉ nên lưu khi scheduler thật sự cung cấp planned fire time. Nếu chỉ biết started_at, đừng làm tròn nó để bịa scheduled_for.

### 9.2. Heartbeat khác progress

Một worker có thể gửi heartbeat nhưng kẹt trên SMTP socket. last_progress_at giúp biết gần đây có event nào thực sự tiến lên hay không.

### 9.3. Counters phải định nghĩa ổn định

submit_success_count có thể đếm số attempts thành công hoặc số events hoàn tất; phải chọn một nghĩa và đặt tên rõ. Ví dụ trong bài dùng **attempt success trong phạm vi run**.

## 10. Lưu outbox events và SMTP attempts

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    business_event_key VARCHAR(200) NOT NULL,
    mail_kind VARCHAR(64) NOT NULL,
    recipient_ref VARCHAR(200) NOT NULL,
    payload_ref VARCHAR(300) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_owner VARCHAR(128),
    claim_until TIMESTAMPTZ,
    claim_version BIGINT NOT NULL DEFAULT 0,
    last_run_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_mail_intent
    ON mail_outbox(business_event_key, mail_kind, recipient_ref);

CREATE INDEX idx_mail_ready
    ON mail_outbox(status, next_attempt_at);

CREATE TABLE mail_send_attempt (
    attempt_id UUID PRIMARY KEY,
    mail_event_id UUID NOT NULL REFERENCES mail_outbox(id),
    run_id UUID REFERENCES mail_job_run(run_id),
    attempt_number INTEGER NOT NULL,
    provider_alias VARCHAR(64),
    outcome VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_ms BIGINT,
    error_category VARCHAR(64),
    smtp_reply_code VARCHAR(16),
    UNIQUE(mail_event_id, attempt_number)
);

CREATE INDEX idx_mail_attempt_event
    ON mail_send_attempt(mail_event_id, attempt_number);
~~~

### 10.1. Outbox và run có quan hệ nhiều lần

last_run_id chỉ thể hiện execution gần nhất; attempt table giúp biết các lần gửi đã xảy ra trước đó.

### 10.2. attempt_number phải cấp nguyên tử

Không tính MAX(attempt_number)+1 ngoài transaction mà không kiểm soát race. Dùng atomic counter/locking hoặc unique constraints với retry transaction phù hợp.

### 10.3. Không đưa MIME body vào bảng observability

payload_ref trỏ tới snapshot/content được quản lý theo chính sách privacy và retention. Run/attempt records chỉ cần metadata vận hành.

## 11. Các mốc thời gian và thời lượng

Cần phân biệt:

- **scheduledFor:** thời điểm dự kiến kích hoạt.
- **triggerObservedAt:** thời điểm scheduler nhận ra lịch đến hạn.
- **startedAt:** bắt đầu execution.
- **finishedAt:** kết thúc execution.
- **lastProgressAt:** lần có tiến độ gần nhất.
- **nextScheduledFor:** lần dự kiến tiếp theo nếu scheduler cung cấp.
- **nextAttemptAt:** retry deadline của mail event.
- **relayAcceptedAt:** mốc được quan sát hoặc đối soát khi relay chấp nhận, nếu có.

### 11.1. Scheduler lag

Nếu planned timestamp thật sự tồn tại:

~~~text
scheduler_lag = startedAt - scheduledFor
~~~

Nếu không có scheduledFor, hãy ghi actual execution mà không giả metric lag.

### 11.2. Dùng System.nanoTime cho elapsed time

Trong một JVM, nanoTime hoặc Micrometer Timer thích hợp đo duration. Không trừ nanoTime từ hai hosts.

### 11.3. Timestamp từ nhiều node

Dùng Instant hoặc database time để lưu lịch sử, đồng thời kiểm soát clock skew giữa nodes.

## 12. @Scheduled: fixedDelay, fixedRate và cron

~~~java
@Scheduled(fixedDelayString = "5000")
public void pollAfterPreviousCompletion() {
    // ...
}

@Scheduled(fixedRateString = "5000")
public void pollAtRegularRate() {
    // ...
}

@Scheduled(
        cron = "0 */5 * * * *",
        zone = "Asia/Ho_Chi_Minh"
)
public void pollEveryFiveMinutes() {
    // ...
}
~~~

- **fixedDelay:** một khoảng chờ sau execution trước kết thúc.
- **fixedRate:** nhịp đặt mục tiêu theo chu kỳ; thực tế có thể chịu scheduler executor và thời gian chạy.
- **cron:** các mốc thời gian theo lịch; cần zone rõ.
- **@Scheduled:** kích hoạt theo từng application instance, không tự cung cấp distributed mutex.

### 12.1. Cron với DST

Trong timezone có daylight saving, giờ địa phương có thể bị bỏ qua hoặc lặp. Nếu cần mỗi business date đúng một execution có ý nghĩa nghiệp vụ, dùng period key/unique constraint riêng.

### 12.2. Job được chạy thủ công

Manual trigger cũng nên tạo run với trigger_type=manual và audit thông tin người thực hiện theo quyền hạn.

## 13. Missed runs và catch-up

Giả sử job dự kiến chạy 10:00, 10:05, 10:10 nhưng ứng dụng ngừng 09:58–10:12.

### 13.1. @Scheduled không tự lưu từng missed tick

Một @Scheduled method thông thường không có durable trigger history để phát lại toàn bộ các mốc trong thời gian process dừng.

### 13.2. Outbox polling có thể tự catch up về workload

Một run sau restart có thể lấy các mail events vẫn PENDING hoặc RETRY_WAIT đã tới hạn. Không nhất thiết phải chạy bù ba cron executions.

### 13.3. Daily digest và báo cáo theo kỳ khác

Nếu mỗi business date cần một digest riêng, phải theo dõi period keys và catch-up policy để không bỏ ngày hoặc gửi hai lần.

### 13.4. Quartz hoặc job scheduler chuyên dụng

Một scheduler có job store/misfire handling như Quartz có thể cung cấp dữ liệu scheduledFireTime hoặc misfire policy. Khi dùng, map đúng thông tin đó vào run tracker; không mặc định Spring @Scheduled đơn giản có những semantics ấy.

## 14. Ghi run record trước khi xử lý

Khi scheduler bắt đầu:

~~~text
runId       = new UUID
jobName     = mail-outbox-dispatcher
status      = RUNNING
triggerType = scheduled
startedAt   = current database time
instanceId  = mail-worker-node-3
~~~

Ghi run record trong **transaction ngắn, đã commit** trước khi claim/send. Nếu worker chết, record RUNNING còn đó để sweeper phát hiện STALE.

### 14.1. Ghi finish bằng transaction khác

Run finish được cập nhật sau summary. Không giữ transaction open xuyên qua SMTP network call.

### 14.2. Tách tracker khỏi business transaction

Nếu dispatcher rollback vì lỗi, vẫn muốn có run failure record. Một JobRunTracker Spring bean riêng có transaction độc lập là mô hình hữu ích.

### 14.3. Không tạo một run cho mỗi email

Một run là một lần scheduler/dispatcher execution; mail event/attempt mới là đơn vị cho email cụ thể.

## 15. Java model cho run summary

~~~java
public record DispatchSummary(
        int claimed,
        int submittedSuccessfully,
        int submitFailures,
        int unknownOutcomes,
        int skipped,
        int unfinished
) {
    public boolean isEmpty() {
        return claimed == 0;
    }

    public boolean hasProblems() {
        return submitFailures > 0
                || unknownOutcomes > 0
                || unfinished > 0;
    }
}
~~~

### 15.1. Định nghĩa groups không trùng

Ví dụ trên giả sử submitFailures và unknownOutcomes là hai nhóm tách biệt. Nếu một số liệu đếm unknown là subtype failure, phải điều chỉnh tổng hợp để không double count.

### 15.2. claimed không nhất thiết bằng attempts

Một event sau claim có thể bị suppress, hết hạn, lỗi render trước send hoặc worker crash. Một event cũng có thể có nhiều attempts nếu policy cho retry nội bộ.

### 15.3. Summary trong memory không đủ sau crash

Durable outbox và attempt records giúp tái dựng phần lịch sử khi run chưa ghi finish.

## 16. Một scheduled orchestrator có tracker

~~~java
import java.util.UUID;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledMailDispatchJob {

    private final JobRunTracker runs;
    private final MailOutboxDispatcher dispatcher;

    public ScheduledMailDispatchJob(
            JobRunTracker runs,
            MailOutboxDispatcher dispatcher
    ) {
        this.runs = runs;
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "5000")
    public void execute() {
        UUID runId = runs.begin(
                "mail-outbox-dispatcher",
                "scheduled"
        );

        try {
            DispatchSummary summary =
                    dispatcher.dispatch(runId);

            runs.finish(runId, summary);
        } catch (RuntimeException ex) {
            runs.fail(runId, "unexpected_dispatch_error");
            throw ex;
        }
    }
}
~~~

**JobRunTracker** và **MailOutboxDispatcher** là các service ứng dụng tự xây dựng, không phải API mặc định của Spring Framework Mail.

### 16.1. begin và finish phải persist riêng

Một run start transaction được commit trước dispatch; finish ghi sau khi dispatcher kết thúc.

### 16.2. Nếu runs.fail cũng lỗi?

Trong production, cần bảo vệ root cause: nếu database outage khiến cả dispatcher và tracker fail, structured logs/tracing phải giữ được lỗi gốc và lỗi secondary. Đoạn code trên minh họa happy/error flow cơ bản.

### 16.3. Không replay toàn run khi finish lỗi

Một số email có thể đã gửi rồi. Recovery phải dựa trên event-level state và attempt history.

## 17. JobRunTracker và @Transactional

~~~java
import java.util.UUID;

public interface JobRunTracker {
    UUID begin(String jobName, String triggerType);

    void finish(UUID runId, DispatchSummary summary);

    void fail(UUID runId, String errorCategory);

    void heartbeat(UUID runId);
}
~~~

Implementation có thể dùng repository/JDBC và **@Transactional(propagation = REQUIRES_NEW)** trong Spring bean riêng.

### 17.1. Lý do transaction độc lập

Nếu database transaction của một mail event bị rollback, lịch sử run start/failure vẫn cần tồn tại.

### 17.2. Spring AOP self-invocation

Một method @Transactional được gọi nội bộ từ cùng instance có thể không đi qua proxy, nên transaction semantics không như dự kiến. Dùng bean riêng hoặc TransactionTemplate.

### 17.3. Tránh giữ DB transaction trong lúc gửi

SMTP có thể chậm, timeout hoặc mất kết nối. Giữ row locks/connection trong lúc send làm tăng contention và không cung cấp rollback SMTP.

## 18. SQL ghi begin và finish

Tạo run:

~~~sql
INSERT INTO mail_job_run (
    run_id,
    job_name,
    status,
    trigger_type,
    started_at,
    heartbeat_at,
    last_progress_at,
    instance_id,
    updated_at
)
VALUES (
    :run_id,
    :job_name,
    'RUNNING',
    :trigger_type,
    now(),
    now(),
    now(),
    :instance_id,
    now()
);
~~~

Kết thúc:

~~~sql
UPDATE mail_job_run
SET status = :final_status,
    finished_at = now(),
    heartbeat_at = now(),
    claimed_count = :claimed,
    submit_success_count = :success,
    submit_failure_count = :failure,
    unknown_count = :unknown,
    skipped_count = :skipped,
    updated_at = now()
WHERE run_id = :run_id
  AND status = 'RUNNING';
~~~

### 18.1. Kiểm tra affectedRows

Nếu UPDATE trả 0, run có thể đã bị recovery chuyển STALE hoặc bị thao tác khác cập nhật. Không ghi đè vô điều kiện.

### 18.2. Định nghĩa finalStatus rõ

Một run không có việc → SUCCEEDED_EMPTY. Run xử lý đầy đủ không lỗi → SUCCEEDED. Run có kết quả pha trộn → PARTIAL. Run lỗi hạ tầng không thể điều phối → FAILED. Đây là ví dụ policy cần phù hợp kiến trúc thực tế.

## 19. Heartbeat và phát hiện run STALE

~~~sql
UPDATE mail_job_run
SET heartbeat_at = now(),
    updated_at = now()
WHERE run_id = :run_id
  AND status = 'RUNNING';
~~~

### 19.1. Heartbeat không chứng minh có tiến độ

Một heartbeat thread có thể sống trong khi worker bị treo ở SMTP. Cần quan sát last_progress_at và active attempts.

### 19.2. Không gia hạn vô hạn

Cần overall run deadline, SMTP timeouts và watchdog. Một run không có tiến độ không nên giữ RUNNING mãi.

### 19.3. STALE sweeper

Một process định kỳ phát hiện run RUNNING với heartbeat quá hạn. Nhưng không tự đổi tất cả mail events thuộc run thành PENDING vì một số đã có SMTP success.

### 19.4. Run heartbeat khác outbox lease

Run heartbeat phục vụ tracking execution; per-event lease phục vụ quyền xử lý một outbox job. Hai cơ chế không thay thế nhau.

## 20. Distributed lock và skipped triggers

Khi có nhiều instances, @Scheduled có thể chạy ở tất cả nodes. Hai chiến lược:

| Chiến lược | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| Scheduler distributed lock | Một scheduled execution | Một node được thực thi lượt điều phối |
| Atomic per-row outbox claim | Mỗi event | Nhiều nodes claim các events khác nhau |

### 20.1. ShedLock và telemetry skip

Một @SchedulerLock có thể bỏ qua invocation không lấy được lock. Nếu code ghi run nằm bên trong method, invocation bị skip có thể không có run record. Cần metric ở tầng lock acquisition/trigger nếu muốn đếm chính xác skips.

### 20.2. Scheduler lock không thay row ownership

Nếu dispatcher chỉ enqueue task rồi thả lock trong lúc outbox rows vẫn PENDING, node khác có thể lấy cùng rows. Cần claim bền vững.

### 20.3. Lock acquired chưa phải email sent

Lock chỉ bảo vệ quyền điều phối; không cho biết SMTP attempt đã bắt đầu hoặc hoàn tất.

## 21. Claim outbox rows và gắn runId

Ví dụ PostgreSQL:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY_WAIT')
        AND next_attempt_at <= now()
    )
    OR (
        status = 'PROCESSING'
        AND claim_until < now()
    )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox m
SET status = 'PROCESSING',
    claim_owner = :worker_id,
    claim_until = now() + INTERVAL '90 seconds',
    claim_version = m.claim_version + 1,
    last_run_id = :run_id,
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING
    m.id,
    m.claim_version,
    m.last_run_id;
~~~

### 21.1. Claim/commit trước SMTP

Database transaction chọn/update/commit các rows, rồi mới thực hiện JavaMailSender.send. Không giữ row lock trong khi network call.

### 21.2. SKIP LOCKED không bảo đảm FIFO tuyệt đối

Những rows bị transaction khác khóa có thể bị bỏ qua. Nếu email yêu cầu strict ordering, cần logic ordering/partitioning riêng.

### 21.3. Expired lease không đồng nghĩa unsent

Worker có thể đã gửi qua SMTP nhưng crash trước update SENT. Recovery phải xét unknown/duplicate window.

### 21.4. Fencing khi update

Khi ghi SENT/RETRY_WAIT, cần check owner/claim_version/token tương ứng để stale worker không cập nhật đè state mới.

## 22. Theo dõi SMTP attempt

Ngay trước send tạo attempt record:

~~~text
attemptId   = UUID
mailEventId = durable event ID
runId       = current execution ID
provider    = actual selected provider
outcome     = STARTED
startedAt   = current timestamp
~~~

Khi send kết thúc, cập nhật outcome, duration, error category, provider reply code khi biết.

### 22.1. Ghi STARTED có giá trị sau crash

Nếu process mất trước finish, có attempt record chưa terminal, giúp đối soát thay vì biến mất khỏi lịch sử.

### 22.2. Đừng tự coi STARTED quá hạn là unsent

Relay có thể đã chấp nhận message. Attempt chưa có finishedAt là thông tin chưa đầy đủ, không phải bằng chứng chưa gửi.

### 22.3. Lỗi render không phải SMTP failure

Nếu dựng MimeMessage thất bại trước send, ghi prepare failure riêng; không tăng counter actual SMTP attempts.

## 23. Retry có thể trải qua nhiều job runs

~~~text
Event E:
  Run R1 / Attempt 1 -> SMTP 421 -> RETRY_WAIT
  Run R2 -> event not due, not selected
  Run R3 / Attempt 2 -> read timeout -> UNKNOWN_OUTCOME
  Run R4 -> reconciliation / policy decision
~~~

### 23.1. Run frequency khác retry frequency

Một scheduler chạy mỗi 5 giây không có nghĩa mỗi event được gửi lại mỗi 5 giây. nextAttemptAt và backoff kiểm soát retry.

### 23.2. Classify errors

AUTH/certificate/invalid recipient thường không nên retry dồn dập. SMTP 4xx tạm thời có thể phù hợp backoff. Timeout sau DATA cần đánh giá duplicate risk.

### 23.3. Terminal failure

Khi quá maxAttempts hoặc deadline, event chuyển FAILED; run dashboard phải có counter terminal failure riêng.

## 24. Những crash windows quan trọng

| Điểm crash | Run | Event/attempt | Rủi ro |
| --- | --- | --- | --- |
| Trước begin commit | Không có record | Chưa claim | Không có run |
| Sau begin, trước claim | RUNNING | PENDING | Run STALE |
| Sau claim, trước send | RUNNING | PROCESSING | Recovery sau lease |
| Trong template render | RUNNING | PROCESSING | Preparation fail/crash |
| Sau DATA, trước final reply | RUNNING | Attempt incomplete | Unknown SMTP acceptance |
| Sau send success, trước SENT | RUNNING | PROCESSING | Retry có thể gửi trùng |
| Sau SENT, trước finish run | RUNNING | SENT | Không resend chỉ vì run status |
| Sau finish | Terminal | Các event states riêng | Lịch sử run hoàn tất |

### 24.1. Không replay toàn FAILED run

Run có thể đã gửi thành công nhiều email. Replay toàn bộ danh sách mà không kiểm tra outbox state sẽ gửi trùng.

### 24.2. Durable states là nguồn quyết định

Retry dựa trên mail event/attempt history, claim lease, status và nextAttemptAt, không dựa vào một metric counter đơn lẻ.

## 25. Metrics tối thiểu

| Metric gợi ý | Loại | Ý nghĩa |
| --- | --- | --- |
| mail.scheduler.runs | Counter | Runs theo job/outcome |
| mail.scheduler.run.duration | Timer | Execution duration |
| mail.scheduler.trigger.lag | Timer | Planned-to-actual start |
| mail.scheduler.lock.skipped | Counter | Skipped due to lock |
| mail.outbox.claimed | Counter | Events claimed |
| mail.outbox.ready.count | Gauge | Events due now |
| mail.outbox.pending.count | Gauge | Pending workload |
| mail.outbox.oldest.pending.age | Gauge | Oldest pending age |
| mail.outbox.retry.wait.count | Gauge | Scheduled retries |
| mail.outbox.expired.leases | Gauge | Work with stale ownership |
| mail.smtp.submit.attempts | Counter | Actual sends attempted |
| mail.smtp.submit.call.duration | Timer | Caller-observed submit time |
| mail.smtp.submit.unknown | Counter | Unknown outcomes |
| mail.event.terminal.failures | Counter | Failed events |
| mail.event.to.relay.acceptance | Timer | Business-to-submit latency |

Đây là metric names do ứng dụng tự thiết kế; Spring Boot Actuator không mặc định sinh toàn bộ chúng.

### 25.1. Đừng double count

Nếu JavaMailSender wrapper và worker code cùng tăng submit attempt counter, dashboard bị thổi phồng. Chọn một nơi duy nhất instrument mỗi sự kiện.

### 25.2. Metric tags hữu hạn

Dùng job alias, mail_kind, provider_alias, outcome, error_category thuộc allowlist. Không dùng runId, mailEventId, recipient, Subject hoặc raw exception text.

## 26. Micrometer Timer cho run

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class ObservedRunExecutor {

    private final MeterRegistry registry;

    public ObservedRunExecutor(MeterRegistry registry) {
        this.registry = registry;
    }

    public DispatchSummary execute(
            String jobName,
            java.util.function.Supplier<DispatchSummary> task
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            DispatchSummary summary = task.get();

            if (summary.hasProblems()) {
                outcome = "partial";
            }

            return summary;
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.scheduler.run.duration",
                            "job", jobName,
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.scheduler.runs",
                    "job", jobName,
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

### 26.1. Timer ghi cả failure

finally giúp duration/count không bị mất khi task ném exception. Một metrics implementation chỉ ghi sau thành công sẽ làm dashboard thiên lệch.

### 26.2. Crash có thể bỏ qua finally

Nếu process bị kill, in-process timer chưa chắc được ghi/export. Durable run record và STALE recovery vẫn cần.

### 26.3. Không gọi run duration là SMTP duration

Run có thể bao gồm claim, render, build, send và state updates. Nếu cần xác định bottleneck, đo các giai đoạn riêng.

## 27. Timer cho JavaMailSender.send

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class TimedSmtpSubmitter {

    private final JavaMailSender sender;
    private final MeterRegistry registry;

    public TimedSmtpSubmitter(
            JavaMailSender sender,
            MeterRegistry registry
    ) {
        this.sender = sender;
        this.registry = registry;
    }

    public void submit(
            MimeMessage message,
            String mailKind
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "kind", mailKind,
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.smtp.submit.attempts",
                    "kind", mailKind,
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

### 27.1. Caller-observed latency

JavaMailSender.send có thể gồm DNS, TCP, TLS, AUTH, MIME serialization, attachment I/O, DATA transfer và server reply. Không đồng nhất nó với thời gian SMTP server xử lý thuần.

### 27.2. Failure khác unknown outcome

Trong wrapper, failure chỉ là exception phía caller. Tầng durable attempt phải phân loại trường hợp có thể đã được relay chấp nhận.

### 27.3. Không gửi hai lần để đo

Instrumentation phải bọc đúng **một** send side effect, không để handler và wrapper cùng gọi sender.send cho một message.

## 28. Structured logs cho run và attempt

Run start:

~~~json
{
  "event": "mail.job_run.started",
  "jobName": "mail-outbox-dispatcher",
  "runId": "run-001",
  "instanceAlias": "worker-a",
  "triggerType": "scheduled",
  "startedAt": "2026-11-12T08:00:00Z"
}
~~~

Run finish:

~~~json
{
  "event": "mail.job_run.finished",
  "runId": "run-001",
  "status": "PARTIAL",
  "durationMs": 3700,
  "claimed": 20,
  "submittedSuccessfully": 18,
  "submitFailures": 1,
  "unknownOutcomes": 1
}
~~~

SMTP attempt:

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "runId": "run-001",
  "mailEventId": "event-42",
  "attemptId": "attempt-3",
  "providerAlias": "smtp-primary",
  "outcome": "failure",
  "errorCategory": "timeout",
  "durationMs": 10010
}
~~~

### 28.1. Không log full MIME

Nội dung email có thể chứa PII, token, invoice, reset link hoặc attachment. Logs chỉ cần IDs, aliases và kết quả đủ để điều tra.

### 28.2. Không dùng raw exception message làm label

Provider reply text có thể chứa recipient, host và chuỗi tùy biến; nên map thành error_category hữu hạn và chỉ giữ diagnostic text khi đã sanitize phù hợp.

## 29. Tracing và async boundaries

~~~text
mail.scheduler.run
       |
       +-- mail.outbox.claim
       |
       +-- mail.event.process
       |       |
       |       +-- mail.template.render
       |       +-- mail.mime.prepare
       |       +-- mail.smtp.submit
       |
       +-- mail.event.process
               |
               +-- mail.smtp.submit
~~~

### 29.1. Một run có thể quá lớn cho một trace

Nếu mỗi run xử lý hàng chục nghìn emails, cân nhắc trace riêng per event và dùng span links hoặc correlation fields để nối với run.

### 29.2. Trace ID không thay business ID

Trace context có sampling/retention và có thể bị đứt qua outbox, nên runId/mailEventId vẫn cần cho durable history.

### 29.3. Không nhét body vào trace

Trace attributes cũng được backend lưu. Tránh recipient, SMTP credential, message body và token trong attributes.

## 30. Dashboard cơ bản

| Panel | Câu hỏi |
| --- | --- |
| Last run status | Job mới nhất kết thúc thế nào? |
| Last actual start | Scheduler còn hoạt động? |
| Next expected trigger | Mốc lịch sắp tới, nếu biết |
| Run duration p50/p95/p99 | Job có chậm bất thường? |
| Runs by status | Có FAILED/PARTIAL/EMPTY? |
| Claimed jobs/run | Dispatcher có lấy được việc? |
| SMTP attempts by outcome | Transport có lỗi? |
| Ready backlog | Có bao nhiêu việc đến hạn? |
| Retry backlog | Bao nhiêu việc đang backoff? |
| Oldest pending age | Có job bị starvation? |
| Expired leases | Worker có mất quyền/crash? |
| Terminal failed events | Mail nào cần xử lý thủ công? |
| Event-to-relay time | End-to-end latency tới submit |

### 30.1. Dashboard phải có count và ratio

p95 từ 3 runs có ý nghĩa khác p95 từ 3000 runs. Hiển thị sample count để tránh kết luận sai.

### 30.2. SUCCEEDED_EMPTY nhưng backlog cao là tín hiệu bất thường

Có thể claim query, eligibility filter, route hoặc lease logic có vấn đề.

### 30.3. Pending count không đủ

Một mail event duy nhất có thể bị kẹt rất lâu. Oldest pending age và deadline misses quan trọng hơn số tổng trong nhiều tình huống.

## 31. Prometheus queries

Giả sử Micrometer Counter xuất ra:

~~~text
mail_scheduler_runs_total{
  job="mail-outbox-dispatcher",
  outcome="success"
}
~~~

Tốc độ chạy:

~~~promql
sum by (job, outcome) (
  rate(mail_scheduler_runs_total[15m])
)
~~~

Failure ratio:

~~~promql
sum by (job) (
  increase(
    mail_scheduler_runs_total{outcome="failure"}[1h]
  )
)
/
sum by (job) (
  increase(mail_scheduler_runs_total[1h])
)
~~~

Nếu Timer bật histogram, p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (job, le) (
    rate(
      mail_scheduler_run_duration_seconds_bucket[1h]
    )
  )
)
~~~

### 31.1. Đừng giả định buckets luôn xuất hiện

Phải cấu hình Micrometer histogram hoặc SLO buckets phù hợp. Tên Prometheus series tùy registry/naming conventions.

### 31.2. Không average p95 của từng pod

Để có p95 toàn hệ thống, tổng hợp histogram buckets rồi tính quantile; trung bình p95 không phải p95 toàn bộ samples.

### 31.3. Không có run thì denominator bằng 0

Dashboard cần thể hiện no data/no samples thay vì tự coi đó là success rate 100%.

## 32. Cảnh báo missed run và scheduler lag

Một job có thể:

- Không có trigger do process down.
- Có trigger nhưng bị distributed lock skip.
- Bắt đầu nhưng lỗi database.
- Bắt đầu và không có việc.
- Chạy nhưng quá lâu.
- Chạy rồi crash trước finish.

### 32.1. Missing khác skipped và empty

**Missing:** không quan sát thấy execution. **Skipped:** trigger có nhưng policy/lock không cho chạy. **Empty:** execution đã chạy, không có việc. **Failed:** execution có lỗi.

### 32.2. Cảnh báo dựa trên expected schedule thật

Nếu chỉ có startedAt trong @Scheduled method, không nên bịa scheduledFor để tính scheduler lag. Khi có scheduler cung cấp planned fire timestamp, có thể đo actual-start minus planned-start.

### 32.3. Maintenance windows

Nếu job được disable theo kế hoạch, alert no-run cần suppress theo configuration để tránh nhiễu.

## 33. Cảnh báo stuck, backlog và unknown outcome

Những tín hiệu quan trọng:

- RUNNING quá deadline.
- Heartbeat quá cũ hoặc không có progress.
- expired leases tăng.
- ready backlog tăng dù scheduler vẫn chạy.
- oldest pending age vượt SLO.
- RETRY_WAIT tăng do rate limit.
- AUTH/TLS failure tăng.
- SMTP unknown outcomes tăng sau DATA timeout.
- FAILED terminal events không được xử lý.

### 33.1. Không tăng worker để chữa mọi vấn đề

Nếu provider đang throttling, thêm workers có thể làm tình hình tệ hơn. Phân tích error categories và rate limits trước khi scale.

### 33.2. Unknown outcome liên quan correctness

Một message có thể đã được relay chấp nhận. Retry nhanh có thể tạo duplicate, không chỉ tiêu tốn tài nguyên.

### 33.3. Heartbeat mà không có progress vẫn cần điều tra

Job có thể đang chờ network hoặc deadlock dù health endpoint vẫn báo chạy.

## 34. Kiểm thử orchestration bằng JUnit và Mockito

~~~java
import static org.mockito.Mockito.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class ScheduledMailDispatchJobTest {

    @Test
    void recordsRunSummary() {
        JobRunTracker runs = mock(JobRunTracker.class);
        MailOutboxDispatcher dispatcher =
                mock(MailOutboxDispatcher.class);

        UUID runId = UUID.randomUUID();

        when(runs.begin(
                "mail-outbox-dispatcher",
                "scheduled"
        )).thenReturn(runId);

        DispatchSummary summary =
                new DispatchSummary(5, 5, 0, 0, 0, 0);

        when(dispatcher.dispatch(runId))
                .thenReturn(summary);

        ScheduledMailDispatchJob job =
                new ScheduledMailDispatchJob(
                        runs,
                        dispatcher
                );

        job.execute();

        verify(dispatcher).dispatch(runId);
        verify(runs).finish(runId, summary);
        verify(runs, never()).fail(
                eq(runId),
                anyString()
        );
    }
}
~~~

### 34.1. Test failure branch

Cho dispatcher ném RuntimeException và xác nhận runs.fail được gọi, exception không bị nuốt.

### 34.2. Test empty run

Cho claimed=0 và xác nhận tracker nhận summary để map sang SUCCEEDED_EMPTY.

### 34.3. Không chứng minh distributed correctness bằng mock đơn luồng

Unit test trên không kiểm tra database locks hoặc concurrent claims; cần integration tests riêng.

## 35. Test Micrometer không cần SMTP

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

class ObservedRunExecutorTest {

    @Test
    void recordsPartialOutcome() {
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry();

        ObservedRunExecutor executor =
                new ObservedRunExecutor(registry);

        DispatchSummary result =
                executor.execute(
                        "mail-outbox-dispatcher",
                        () -> new DispatchSummary(
                                3, 2, 1, 0, 0, 0
                        )
                );

        assertTrue(result.hasProblems());

        Counter runs = registry
                .find("mail.scheduler.runs")
                .tag("job", "mail-outbox-dispatcher")
                .tag("outcome", "partial")
                .counter();

        assertNotNull(runs);
        assertEquals(1.0, runs.count(), 0.0001);
    }
}
~~~

Nếu cần kiểm thử duration chính xác, dùng Micrometer **MockClock** thay vì Thread.sleep với ngưỡng chặt gây flaky CI.

## 36. Integration test với PostgreSQL và crash recovery

Nếu production dùng **FOR UPDATE SKIP LOCKED**, nên dùng PostgreSQL thực trong môi trường test, ví dụ Testcontainers, vì H2/mock có thể không có semantics tương đương.

~~~text
Insert 100 PENDING outbox records
Start worker A and B concurrently
Each calls claimBatch in own transaction
Commit
Assert claimed row sets do not overlap
Assert claim ownership and version correct
~~~

### 36.1. Dùng latch/barrier

CountDownLatch/CyclicBarrier tạo cạnh tranh thật; không chạy A rồi B tuần tự và gọi đó là concurrency test.

### 36.2. Test stale ownership

A claim version 1, lease expires, B claim version 2. A update SENT bằng version 1 phải ảnh hưởng 0 rows.

### 36.3. Test SMTP crash window

Fake transport trả success nhưng database update SENT không được commit. Recovery phải tuân thủ policy, không tự gửi lại toàn run mù quáng.

### 36.4. Test run STALE

Tạo RUNNING record rồi giả lập process crash, sau heartbeat timeout sweeper đánh dấu STALE. Những events đã SENT vẫn giữ state của chúng.

## 37. Ma trận kiểm thử các tình huống

| Tình huống | Expected behavior |
| --- | --- |
| Cron theo zone | Chạy đúng timezone |
| App restart bỏ missed ticks | Outbox events đến hạn vẫn được xử lý |
| Manual trigger | Có runId riêng và audit |
| Job disabled | Không báo missed run giả |
| Distributed lock busy | Skip, không gửi trùng |
| Empty outbox | SUCCEEDED_EMPTY |
| Database lỗi | FAILED hoặc error state đúng |
| Một số events retry | Run summary theo contract |
| Worker crash giữa run | STALE, recovery riêng từng event |
| Heartbeat sống nhưng không progress | Alert stuck |
| Hai workers claim đồng thời | Không cùng active ownership |
| Lease expired | Stale update bị chặn |
| nextAttemptAt tương lai | Không retry sớm |
| SMTP send success | Attempt success phía caller |
| AUTH invalid | Không retry dồn dập |
| SMTP 421 temporary | Backoff phù hợp |
| Timeout sau DATA | UNKNOWN_OUTCOME |
| Failover provider | Attribution theo attempt |
| Timer failure | Ghi mẫu trong finally |
| PII trong payload | Không log/tag ngoài policy |

## 38. Runbook khi job không chạy

1. Xác nhận job enabled, cron/fixedDelay và timezone.
2. Kiểm tra last run status, last start và expected trigger nếu có.
3. Kiểm tra app instances, scheduler executor, thread saturation.
4. Kiểm tra ShedLock/lock provider và skipped triggers.
5. Kiểm tra database kết nối và quyền ghi run records.
6. Kiểm tra outbox ready count, status filter và nextAttemptAt.
7. Nếu claimed=0 nhưng ready>0, kiểm tra claim query và lease.
8. Nếu claimed>0 nhưng attempts=0, xem validation/render/MIME preparation.
9. Nếu attempts thất bại, phân loại AUTH/TLS/connect/rate_limit/recipient.
10. Nếu RUNNING lâu, xem heartbeat và last_progress_at.
11. Nếu worker crash, đối soát SENT/PROCESSING/UNKNOWN_OUTCOME.
12. Chỉ retry những events eligible theo policy; không replay toàn run.

### 38.1. Không đổi SENT thành PENDING tùy tiện

Nếu SMTP đã accept, resend có thể tạo duplicate. Manual resend là một nghiệp vụ riêng cần audit.

### 38.2. Quyền truy cập và dữ liệu cá nhân

Run history cần metadata, không cần password, token, full HTML, recipient address hoặc attachment. Nếu phải tra một event cụ thể, dùng ID và hệ thống có phân quyền.

## 39. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Log Start/Finish không runId | Khó đối soát | Durable run ID |
| Run là một email | Sai đơn vị | Tách definition/run/event/attempt |
| Mark SENT khi enqueue async | Báo success sớm | Ack theo SMTP outcome |
| Chỉ ghi attempts thành công | Mất lỗi/timeout | STARTED + terminal outcome |
| Retry đếm thành event mới | Sai unique counts | Stable mailEventId |
| @Scheduled làm distributed mutex | Multi-node duplicate | Lock/atomic row claim |
| Giữ DB transaction khi send | Contention | Claim/commit trước SMTP |
| Không heartbeat/recovery | Stuck RUNNING | STALE sweeper |
| Heartbeat không progress | Health giả | Last progress/deadline |
| Replay toàn run FAILED | Duplicate | Retry từng outbox event |
| Timeout sau DATA retry mù | Duplicate risk | UNKNOWN_OUTCOME |
| Chỉ nhìn pending_count | Bỏ starvation | Oldest pending age |
| Recipient/eventId làm metric tag | PII/high cardinality | Low-cardinality labels |
| nanoTime giữa nodes | Sai duration | Timestamp/clock đúng |
| Bịa scheduledFor | Lag giả | Planned trigger thật |
| SUCCEEDED được gọi delivered | Sai SLA | Submission vs downstream |
| Mockito DB dùng để chứng minh SKIP LOCKED | Bỏ race condition | Database integration test |
| Thread.sleep test duration | Flaky CI | Fake clock/MockClock |

## 40. Câu hỏi thường gặp

**1. Job gửi mail có phải một email không?**

Không. Job là lịch/điều phối; run là execution; event là ý định gửi; attempt là một lần gửi SMTP.

**2. Một run cần lưu gì?**

RunId, jobName, trigger, startedAt, finishedAt, status, instanceId, counters và lỗi được phân loại. Nếu cần scheduler lag, phải có planned fire timestamp đáng tin.

**3. Run không có mail nào có phải lỗi không?**

Không. Khi query outbox thành công và không có sự kiện đến hạn, SUCCEEDED_EMPTY là kết quả hợp lệ.

**4. Run FAILED có nghĩa tất cả email chưa gửi không?**

Không. Một số events có thể đã gửi thành công trước lỗi. Không replay cả run.

**5. @Scheduled tự lưu durable run history không?**

Không theo mô hình tracker này. Có thể dùng application run table hoặc scheduler/job framework phù hợp.

**6. @Scheduled tự tránh nhiều pods chạy trùng không?**

Không. Mỗi instance có scheduler riêng; cần distributed coordination hoặc atomic row claims.

**7. ShedLock có thay outbox không?**

Không. Scheduler lock và per-event durable state giải quyết hai lớp khác nhau.

**8. Vì sao cần eventId và attemptId riêng?**

Một mail event có thể retry nhiều lần, mỗi lần một attempt với kết quả riêng.

**9. nextAttemptAt có giống cron schedule không?**

Không. Cron quyết định dispatcher thức dậy; nextAttemptAt quyết định một event được phép retry khi nào.

**10. Run success có nghĩa email đã vào inbox không?**

Không. JavaMailSender.send success chỉ phản ánh transport submission, không bảo đảm downstream delivery/read.

**11. Timeout có chắc chắn relay chưa accept không?**

Không. Mất final response sau DATA có thể tạo unknown outcome.

**12. Heartbeat có chứng minh job còn tiến độ không?**

Không chắc. Theo dõi thêm last progress, active attempts và deadlines.

**13. Vì sao không dùng recipient làm metric tag?**

Đây là PII và có cardinality lớn. Dùng correlation IDs trong log/database có phân quyền.

**14. Test tracker mà không gửi SMTP thật được không?**

Có. Mockito cho sender/dispatcher, SimpleMeterRegistry cho metrics, SMTP capture server cho integration tests.

**15. Test SKIP LOCKED bằng H2 có đủ không?**

Không nên giả định. Dùng PostgreSQL nếu production dựa vào semantics PostgreSQL.

**16. Quartz hay Spring Batch có thể giúp run tracking không?**

Có trong những mô hình phù hợp, nhưng vẫn cần nối execution với outbox events và SMTP attempts; chúng không tự cung cấp inbox delivery tracking.

**17. Nếu scheduler mất tick khi restart thì sao?**

Outbox polling sau restart có thể xử lý các events đến hạn. Nếu cần chạy bù từng kỳ nghiệp vụ, phải có durable period keys.

**18. Khi nào cần manual resend?**

Khi nghiệp vụ yêu cầu và đã đối soát trạng thái cũ; không chỉ đổi SENT về PENDING.

**19. Pending count thấp có nghĩa không có backlog nguy hiểm không?**

Không. Một event có thể kẹt lâu. Cần oldest pending age và deadline misses.

**20. Run success rate có giống SMTP success rate không?**

Không. Một cái đo executions, một cái đo transport attempts. Đơn vị và phạm vi khác nhau.

## 41. Ghi nhớ về theo dõi job gửi và các lần chạy

**Một hệ thống Spring Framework Mail được lập lịch tốt phải theo dõi riêng job definition, job run, mail event và SMTP attempt.** Cần cấp runId cho mỗi lần thực thi, ghi timestamps/status/counters, dùng mailEventId ổn định qua retry và attemptId mới cho mỗi lời gọi transport. Run thành công, SMTP send success và inbox delivery là **ba khái niệm khác nhau**.

Ghi run begin/finish trong transactions ngắn, theo dõi heartbeat và last progress để phát hiện STALE. Khi chạy nhiều nodes, dùng atomic outbox claims/lease và distributed coordination phù hợp; không giữ database transaction trong lúc SMTP send. Khi relay có thể đã accept DATA nhưng client không nhận response, ghi **UNKNOWN_OUTCOME** và tránh retry mù.

Kết hợp durable run/outbox/attempt history với **Micrometer Timer/Counter**, structured logging, tracing, dashboard và alerts về missed runs, expired leases, retry backlog, oldest pending age và terminal failures. Kiểm thử orchestration bằng JUnit/Mockito, metrics bằng SimpleMeterRegistry/MockClock, và concurrency trên database phù hợp.

Mục tiêu không chỉ là biết scheduler đã chạy, mà còn trả lời được **run nào đã làm việc gì, event nào đã được thử gửi, vì sao có lỗi, kết quả có chắc chắn không và công việc nào cần xử lý tiếp** — một cách có thể kiểm chứng, tránh gửi trùng và không làm lộ dữ liệu email.

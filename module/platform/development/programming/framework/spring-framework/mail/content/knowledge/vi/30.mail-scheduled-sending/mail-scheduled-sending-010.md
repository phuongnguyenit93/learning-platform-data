# Thay đổi lịch mà không làm mất yêu cầu đang chờ

Trong ứng dụng dùng **Spring Framework Mail**, một email có thể không được gửi ngay khi sự kiện nghiệp vụ xảy ra. Hệ thống có thể gửi bản tin vào thứ Hai hằng tuần, nhắc thanh toán sau ba ngày, gửi tổng hợp cuối ngày hoặc cho phép người dùng hẹn giờ nhận thông báo.

Vấn đề xuất hiện khi **lịch gửi thay đổi trong lúc đã có những yêu cầu đang chờ**. Nếu lập trình viên chỉ hủy tác vụ cũ rồi tạo tác vụ mới trong bộ nhớ, những email đã được xếp lịch có thể biến mất. Nếu cập nhật toàn bộ thời gian gửi trong database mà không phân biệt trạng thái, email đang retry có thể bị đẩy lùi vô hạn hoặc email đã được worker nhận có thể bị gửi trùng.

Ví dụ:

~~~text
09:00  Khách hàng đã tạo 800 yêu cầu gửi thông báo lúc 10:00.
09:20  Quản trị viên đổi lịch thành 11:00.
09:21  Một worker đang xử lý 20 yêu cầu.
09:22  30 yêu cầu khác đang chờ retry vì SMTP 451.

Yêu cầu thiết kế:
  - Không âm thầm xóa 800 yêu cầu đã tồn tại.
  - Không tạo 800 yêu cầu mới trùng nội dung.
  - Những yêu cầu nào được dời phải có quy tắc rõ ràng.
  - Những yêu cầu đã gửi hoặc đang gửi không bị sửa tùy tiện.
  - Sau khi ứng dụng restart, trạng thái vẫn phục hồi được.
~~~

**Nguyên tắc cốt lõi:** **lịch phát sinh công việc** và **các yêu cầu gửi đã được tạo** là hai thực thể khác nhau. Thay đổi cron, giờ gửi hoặc tần suất không tự động đồng nghĩa phải xóa rồi tái tạo mọi mail job.

Bài học này tập trung vào cách thiết kế lịch gửi có thể thay đổi an toàn với Spring, database/outbox, `@Scheduled`, `TaskScheduler` hoặc Quartz, đặc biệt là giữ nguyên những yêu cầu đang chờ, tránh race condition và hỗ trợ kiểm toán.

## 1. Phân biệt lịch, lần kích hoạt và yêu cầu gửi

Một hệ thống gửi thư theo lịch thường có ba lớp:

| Lớp | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Schedule definition** | Khi nào và theo quy tắc nào cần tạo công việc? | Mỗi thứ Hai lúc 09:00, timezone Asia/Ho_Chi_Minh |
| **Schedule occurrence** | Một lần kích hoạt cụ thể của lịch là lần nào? | Bản tin tuần 2026-W46 |
| **Mail request/job** | Cần gửi email nào cho ai và trạng thái hiện tại? | Newsletter cho subscriber 123 đang `PENDING` |

Một mô hình:

~~~mermaid
flowchart TD
    A["Schedule definition v3"] --> B["Schedule occurrence"]
    B --> C["Durable mail requests / outbox"]
    C --> D["Due job dispatcher"]
    D --> E["SMTP/API sender"]
    E --> F["Provider events"]
    A -. "Thay đổi lịch" .-> G["Schedule definition v4"]
    G --> H["Future occurrences"]
~~~

Đường thay đổi từ lịch v3 sang v4 **không mặc nhiên xóa** các hàng đã được lưu trong outbox.

### 1.1. Lịch định kỳ khác lịch của một email cụ thể

**Lịch định kỳ:** tạo một nhóm email theo một chu kỳ:

~~~text
Every Monday 09:00
  -> occurrence: weekly-digest:2026-W46
  -> tạo 10.000 mail requests
~~~

Nếu đổi sang thứ Ba, câu hỏi là lịch mới áp dụng cho **những tuần chưa phát sinh occurrence** hay có dời cả nhóm job đã được tạo?

**Lịch một lần:** người dùng tạo một email dự kiến gửi lúc 09:00 ngày mai:

~~~text
request-abc:
  sendAt = 2026-11-13T02:00:00Z
  state = PENDING
~~~

Nếu người dùng đổi sang 11:00, thông thường cập nhật `sendAt` của chính request này; không cần xóa request cũ rồi tạo ID mới.

### 1.2. Lịch điều phối không phải là email đã gửi

Các mốc phải được phân biệt:

~~~text
Schedule triggered
    |
    v
Mail job persisted
    |
    v
Job eligible for sending
    |
    v
Worker claims job
    |
    v
SMTP/API submission attempted
    |
    v
SUBMITTED / RETRY_WAIT / FAILED_FINAL / UNKNOWN
~~~

Một cron vừa kích hoạt không chứng minh email đã được gửi. Ngược lại, một SMTP submission lỗi có thể để lại job cần retry mà không liên quan tới việc lịch cron có thay đổi hay không.

## 2. Vì sao cách hủy rồi tạo lại có thể làm mất mail?

Một cách làm đơn giản nhưng rủi ro:

~~~java
scheduledFuture.cancel(false);
scheduledFuture = taskScheduler.schedule(
        () -> mailSender.send(message),
        newTrigger);
~~~

Với đoạn code này, lịch nằm trong `ScheduledFuture` và bộ nhớ JVM. Các rủi ro:

- **Restart:** ứng dụng mất những tác vụ chỉ tồn tại trong memory.
- **Thay đổi lịch:** cancel task cũ có thể loại bỏ luôn công việc mà task đó đại diện.
- **Race:** task cũ có thể đã bắt đầu, `cancel(false)` không thu hồi email đã gửi.
- **Nhiều replica:** mỗi instance có thể tạo tác vụ tương tự, dẫn đến gửi trùng.
- **Không có audit:** khó biết có bao nhiêu yêu cầu từng chờ, ai đã sửa lịch và ảnh hưởng những email nào.
- **Không có retry bền vững:** exception SMTP có thể khiến công việc thất bại mà không còn thông tin để thử lại.

`TaskScheduler` và `ScheduledFuture` vẫn hữu ích để **đánh thức bộ điều phối**, nhưng không nên là nơi duy nhất lưu những yêu cầu gửi nghiệp vụ quan trọng.

### 2.1. Cron expression không phải hàng đợi

~~~java
@Scheduled(cron = "0 0 9 * * MON")
void sendWeeklyDigest() {
    // ...
}
~~~

Annotation `@Scheduled` giúp chạy method theo lịch cấu hình; nó không tự lưu một bảng những email pending để phục hồi sau crash. Nếu ứng dụng thay cron, restart hoặc deploy giữa lúc một lượt gửi dài đang chạy, việc giữ/khôi phục các yêu cầu còn lại là trách nhiệm của ứng dụng.

### 2.2. Không dùng danh sách recipient trong RAM làm nguồn sự thật

~~~java
List<String> pendingRecipients = loadRecipients();
// Đổi lịch -> hủy task cũ -> danh sách biến mất khi process dừng.
~~~

Với email quan trọng, nên ghi một **durable mail request** hoặc outbox row trước khi giao cho worker, bao gồm định danh nghiệp vụ, thời gian gửi, trạng thái và thông tin cần để retry.

## 3. Chọn chính sách thay đổi lịch trước khi viết code

Không có một quy tắc duy nhất đúng cho mọi sản phẩm. Cần công bố rõ **lịch mới áp dụng tới đâu**.

| Chính sách | Yêu cầu đã tạo | Yêu cầu chưa tạo | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **KEEP_EXISTING** | Giữ nguyên giờ gửi đã cam kết | Dùng lịch mới | Bản tin tuần, nhắc việc đã hẹn |
| **MOVE_UNSTARTED** | Chỉ dời job chưa từng attempt và chưa bị worker claim | Dùng lịch mới | Người dùng sửa giờ gửi một lần |
| **CANCEL_UNSENT** | Chuyển job đủ điều kiện sang `CANCELLED` có audit | Không phát sinh theo lịch cũ | Hủy chiến dịch theo yêu cầu rõ ràng |
| **REPLAN_FUTURE_OCCURRENCES** | Giữ các occurrence đã phát sinh; tính lại tương lai | Dùng cron/timezone mới | Lịch định kỳ thay đổi tần suất |
| **REVIEW_IN_FLIGHT** | Giữ/điều tra job đang gửi hoặc outcome không rõ | Theo lịch mới | Thay đổi lớn, rủi ro gửi trùng |

Tên chính sách trong bảng là **quy ước gợi ý của ứng dụng**, không phải enum được Spring Mail cung cấp sẵn.

### 3.1. KEEP_EXISTING — an toàn mặc định cho lịch định kỳ

~~~text
09:00  Weekly digest occurrence W46 đã tạo 2.000 requests.
09:10  Admin đổi lịch chạy từ thứ Hai sang thứ Ba.

W46 đã tạo:
  2.000 requests vẫn tồn tại, theo thời điểm/điều kiện đã định.

Những occurrence chưa phát sinh:
  Dùng lịch thứ Ba.
~~~

Ưu điểm: không thay đổi lời hứa về các job đã tồn tại, không phải sửa hàng loạt dữ liệu. Đặc biệt hữu ích khi schedule chỉ là **nguồn phát sinh các công việc**.

### 3.2. MOVE_UNSTARTED — đổi giờ gửi của job đang chờ

~~~text
Request #A:
  state=PENDING
  attempts=0
  sendAt=10:00

User đổi lịch:
  sendAt=11:00

Request #A:
  ID giữ nguyên
  state=PENDING
  attempts=0
  sendAt=11:00
  có audit rescheduled
~~~

Không tạo request #B nếu cùng một yêu cầu nghiệp vụ. Giữ ID/correlation giúp tránh gửi hai email và giúp support tra cứu lịch sử.

### 3.3. CANCEL_UNSENT không phải “mất yêu cầu”

Khi người dùng thật sự hủy, không nên xóa row không để lại dấu vết:

~~~text
PENDING -> CANCELLED
reason=USER_CANCELLED_CAMPAIGN
actor=admin-17
changedAt=...
~~~

Row và audit event vẫn tồn tại theo retention policy. Một email đã `SUBMITTED` không thể “hủy gửi” chỉ bằng cách đổi trạng thái trong database.

### 3.4. Các câu hỏi phải được sản phẩm quyết định

Trước khi thay lịch:

1. Lịch mới áp dụng **chỉ các lần phát sinh trong tương lai** hay cả job đã tạo?
2. Job đã qua giờ gửi nhưng chưa worker claim có được dời không?
3. Job `RETRY_WAIT` sau một SMTP error có tiếp tục retry theo backoff cũ không?
4. Job đã bắt đầu `SUBMITTING` có được yêu cầu hủy không?
5. Email có thời hạn hiệu lực như OTP có được gửi nếu giờ mới vượt thời hạn không?
6. Khi đổi timezone hoặc cron, một occurrence đã tạo có được tạo lại không?
7. Người dùng có được xem trước số lượng job sẽ bị tác động và được hoàn tác không?

Những quyết định này là **business contract**, không thể suy ra chỉ từ `@Scheduled` hay `CronTrigger`.

## 4. Mô hình dữ liệu bền vững

Để minh họa, giả định ứng dụng dùng PostgreSQL, Spring Boot 3 và Java 17+. Schema thực tế cần phù hợp nghiệp vụ, indexes, partition và migration strategy.

### 4.1. Bảng lịch

~~~sql
CREATE TABLE mail_schedule (
    id                UUID PRIMARY KEY,
    tenant_id         VARCHAR(80) NOT NULL,
    schedule_kind     VARCHAR(30) NOT NULL,
    cron_expression   VARCHAR(200),
    timezone_id       VARCHAR(100) NOT NULL,
    one_time_at       TIMESTAMPTZ,
    next_fire_at      TIMESTAMPTZ,
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    version           BIGINT NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong đó:

- `schedule_kind` có thể là `ONE_TIME` hoặc `RECURRING`;
- `cron_expression` là quy tắc phát sinh occurrence;
- `timezone_id` lưu **IANA timezone** như `Asia/Ho_Chi_Minh`, không chỉ offset `+07:00`;
- `next_fire_at` là mốc tiếp theo được tính và lưu để scheduler quét;
- `version` hỗ trợ optimistic concurrency control và audit thay đổi.

**Không lưu SMTP password/OAuth token trong bảng lịch**. Lịch có thể tham chiếu sender profile ID, còn credential nằm trong cấu hình bảo mật của provider adapter.

### 4.2. Bảng yêu cầu gửi

~~~sql
CREATE TABLE mail_request (
    id                UUID PRIMARY KEY,
    schedule_id       UUID REFERENCES mail_schedule(id),
    schedule_version  BIGINT,
    occurrence_key    VARCHAR(150),
    recipient_key     VARCHAR(150) NOT NULL,
    tenant_id         VARCHAR(80) NOT NULL,
    mail_type         VARCHAR(80) NOT NULL,
    payload_ref       VARCHAR(300) NOT NULL,
    state             VARCHAR(40) NOT NULL,
    scheduled_at      TIMESTAMPTZ NOT NULL,
    next_attempt_at   TIMESTAMPTZ,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(120),
    lease_until       TIMESTAMPTZ,
    cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mail_request_due
    ON mail_request (scheduled_at, next_attempt_at, state);

CREATE INDEX idx_mail_request_schedule_state
    ON mail_request (schedule_id, schedule_version, state);
~~~

`payload_ref` trỏ đến dữ liệu render/template/attachment đã được lưu an toàn; không nhất thiết chứa raw email body trong hàng job. `recipient_key` là định danh nội bộ đã kiểm soát, không phải địa chỉ email làm metric label.

Một unique key phù hợp cho lịch định kỳ:

~~~sql
CREATE UNIQUE INDEX uq_mail_request_occurrence_recipient
ON mail_request (
    schedule_id,
    occurrence_key,
    recipient_key
)
WHERE schedule_id IS NOT NULL
  AND occurrence_key IS NOT NULL;
~~~

Unique constraint này chống tạo lặp **cùng một logical occurrence cho cùng recipient**. `occurrence_key` phải được xác định ổn định theo nghiệp vụ, ví dụ `weekly-digest:2026-W46`. Không nên chỉ ghép `schedule_version` vào unique key vì sau khi sửa lịch, cùng một occurrence có thể bị tạo lại ở version mới và **lọt qua deduplication**.

Đối với một request đơn lẻ không có `schedule_id`, nên có `idempotency_key` hoặc unique business key riêng; partial index phía trên không bao phủ mọi trường hợp.

### 4.3. Audit thay đổi lịch

~~~sql
CREATE TABLE mail_schedule_audit (
    id               UUID PRIMARY KEY,
    schedule_id      UUID NOT NULL,
    old_version      BIGINT NOT NULL,
    new_version      BIGINT NOT NULL,
    actor_id         VARCHAR(120) NOT NULL,
    change_policy    VARCHAR(50) NOT NULL,
    old_definition   JSONB NOT NULL,
    new_definition   JSONB NOT NULL,
    affected_jobs    BIGINT NOT NULL,
    changed_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong production, audit có thể cần request ID, reason, approver, dry-run impact và phân quyền truy cập. Không log đầy đủ recipient/secret/payload nếu không cần.

### 4.4. Phân biệt scheduled_at và next_attempt_at

Đây là hai thời điểm **khác nhau**:

- `scheduled_at`: thời điểm nghiệp vụ yêu cầu mail không được gửi sớm hơn.
- `next_attempt_at`: thời điểm transport retry có thể thực hiện sau lỗi.

Ví dụ:

~~~text
scheduled_at    = 10:00
attempt-1       = 10:01 -> SMTP 451
next_attempt_at = 10:06
state           = RETRY_WAIT
~~~

Nếu admin đổi lịch chiến dịch sang 11:00, không mặc định ghi đè `next_attempt_at=11:00` cho mọi job. Điều đó thay đổi chính sách retry và có thể khiến mail chưa gửi bị trì hoãn theo cách không mong muốn.

Một job đủ điều kiện được lấy khi cả giới hạn nghiệp vụ và backoff đều cho phép:

~~~text
scheduled_at <= now
AND (next_attempt_at IS NULL OR next_attempt_at <= now)
AND state thuộc PENDING / RETRY_WAIT
~~~

## 5. State machine của mail request

Một flow ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: due + atomic claim
    PENDING --> CANCELLED: authorized cancel
    PENDING --> PENDING: reschedule
    CLAIMED --> SUBMITTING: begin send
    CLAIMED --> PENDING: safe lease recovery
    SUBMITTING --> SUBMITTED: transport accepted
    SUBMITTING --> RETRY_WAIT: retryable failure
    SUBMITTING --> FAILED_FINAL: permanent failure
    SUBMITTING --> UNKNOWN: uncertain outcome
    RETRY_WAIT --> CLAIMED: backoff complete
    RETRY_WAIT --> FAILED_FINAL: retry limit
    SUBMITTED --> [*]
    FAILED_FINAL --> [*]
    CANCELLED --> [*]
    UNKNOWN --> [*]
~~~

State machine này mang tính minh họa, cần định nghĩa rõ “terminal” cho ứng dụng. `SUBMITTED` là trạng thái transport đã nhận, không phải provider delivered; sau đó có thể có delivery events riêng.

### 5.1. Quy tắc reschedule theo trạng thái

| Trạng thái | Có nên tự động dời `scheduled_at`? | Lý do |
| --- | --- | --- |
| `PENDING`, chưa attempt, chưa claim | Có, nếu policy `MOVE_UNSTARTED` | Chưa bắt đầu side effect |
| `RETRY_WAIT` | Mặc định không | Retry schedule là quyết định sau attempt |
| `CLAIMED` | Không sửa tùy tiện | Worker đã sở hữu job/lease |
| `SUBMITTING` | Không bảo đảm hủy/dời | SMTP side effect có thể đang diễn ra |
| `SUBMITTED` | Không | Email đã nộp cho transport |
| `UNKNOWN` | Không retry/dời mù | Có thể provider đã chấp nhận |
| `FAILED_FINAL` | Không | Cần lệnh khôi phục riêng |
| `CANCELLED` | Không tự hồi sinh | Hủy có chủ đích và audit |

Đừng chỉ kiểm tra `sent = false` rồi sửa mọi job; trường boolean đó không phân biệt retry, claim, unknown hay cancelled.

### 5.2. Không đặt “send time” trong một trường bị nhiều actor ghi

Sai:

~~~text
nextSendAt = business schedule time
nextSendAt = retry backoff time
nextSendAt = worker lease expiry
~~~

Một trường bị dùng cho ba ý nghĩa sẽ tạo lỗi khi admin đổi lịch. Tốt hơn:

~~~text
scheduled_at
next_attempt_at
lease_until
~~~

Mỗi giá trị có owner và transition rule riêng.

## 6. Thay đổi lịch một lần bằng transaction

Giả sử một lịch một lần đã tạo các request `PENDING` chưa attempt. Người dùng đổi giờ gửi từ 10:00 sang 11:00, và chính sách là `MOVE_UNSTARTED`.

Một transaction cần:

1. Khóa/cập nhật schedule đúng version.
2. Đổi `scheduled_at` của **chỉ job đủ điều kiện**.
3. Giữ ID, payload, recipient và audit.
4. Commit cùng lúc để worker không nhìn thấy trạng thái nửa cũ nửa mới.

### 6.1. Ví dụ SQL PostgreSQL

~~~sql
BEGIN;

SELECT version
FROM mail_schedule
WHERE id = :schedule_id
FOR UPDATE;

-- Application xác minh version vừa đọc bằng expected_version.

UPDATE mail_schedule
SET one_time_at = :new_send_at,
    next_fire_at = :new_send_at,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :schedule_id
  AND version = :expected_version;

-- Chỉ dời những request chưa từng gửi thử hoặc bị claim,
-- và còn là yêu cầu có lịch tương lai.
UPDATE mail_request
SET scheduled_at = :new_send_at,
    schedule_version = :new_version,
    updated_at = CURRENT_TIMESTAMP
WHERE schedule_id = :schedule_id
  AND schedule_version = :expected_version
  AND state = 'PENDING'
  AND attempt_count = 0
  AND lease_owner IS NULL
  AND scheduled_at > CURRENT_TIMESTAMP;

-- INSERT mail_schedule_audit với số rows đã đổi.

COMMIT;
~~~

Đây là **mẫu giải thích transaction**, không phải script có thể copy chạy độc lập: application phải kiểm tra row count/version, gán `:new_version`, insert audit cùng transaction và rollback khi có conflict. PostgreSQL dùng row locks và điều kiện `WHERE` được đánh giá phù hợp khi update cạnh tranh.

**Giới hạn quan trọng:** cập nhật tất cả job của một lịch về **cùng một `new_send_at` chỉ đúng với one-time schedule** hoặc một nhóm job cùng occurrence đã được chỉ định. Với cron định kỳ, không được dời toàn bộ job của nhiều tuần về cùng một giờ!

### 6.2. Đừng ghi đè next_attempt_at của retry jobs

Ví dụ SQL trên cố ý chỉ chọn `state = 'PENDING'` và `attempt_count = 0`. Các job `RETRY_WAIT` giữ backoff của mình. Nếu sản phẩm yêu cầu dời cả retry jobs, phải có một policy được phê duyệt, ví dụ tính:

~~~text
eligible_at = max(new_business_send_at, existing_retry_backoff_at)
~~~

nhưng vẫn phải cân nhắc retry limit, deadline và ý nghĩa những attempt đã xảy ra. Không dùng một câu SQL update toàn bộ chỉ vì `status != 'SUBMITTED'`.

### 6.3. Trường hợp giờ mới ở quá khứ

Nếu admin đổi 11:00 thành 09:00 trong khi hiện tại 10:00:

- **Send immediately:** job sẽ eligible ngay.
- **Reject:** API từ chối thời gian trong quá khứ.
- **Next valid occurrence:** với lịch định kỳ, tính mốc tiếp theo.

Chọn policy rõ ràng. Không tự âm thầm “sửa về now” nếu người dùng mong muốn lịch chính xác.

## 7. Ví dụ Spring service với optimistic version

Ví dụ Java ở mức kiến trúc, repository implementation dùng JPA/JdbcTemplate tùy dự án:

~~~java
public enum ReschedulePolicy {
    KEEP_EXISTING,
    MOVE_UNSTARTED,
    CANCEL_UNSENT
}

public record RescheduleCommand(
        UUID scheduleId,
        long expectedVersion,
        Instant newSendAt,
        ReschedulePolicy policy,
        String actorId,
        String reason) {
}

public record RescheduleResult(
        UUID scheduleId,
        long newVersion,
        int affectedJobs) {
}
~~~

Service:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailScheduleService {
    private final MailScheduleRepository schedules;
    private final MailRequestRepository requests;
    private final ScheduleAuditRepository audits;
    private final Clock clock;

    public MailScheduleService(
            MailScheduleRepository schedules,
            MailRequestRepository requests,
            ScheduleAuditRepository audits,
            Clock clock) {
        this.schedules = schedules;
        this.requests = requests;
        this.audits = audits;
        this.clock = clock;
    }

    @Transactional
    public RescheduleResult changeOneTimeSchedule(
            RescheduleCommand command) {

        MailSchedule schedule = schedules.lockById(
                command.scheduleId()).orElseThrow();

        if (schedule.version() != command.expectedVersion()) {
            throw new ScheduleVersionConflictException();
        }
        schedule.requireKind("ONE_TIME");

        Instant now = clock.instant();
        long oldVersion = schedule.version();
        long newVersion = oldVersion + 1;
        int affected;

        switch (command.policy()) {
            case KEEP_EXISTING -> affected = 0;
            case MOVE_UNSTARTED -> affected =
                    requests.moveNeverAttemptedFutureJobs(
                            schedule.id(),
                            oldVersion,
                            newVersion,
                            now,
                            command.newSendAt());
            case CANCEL_UNSENT -> affected =
                    requests.cancelNeverAttemptedFutureJobs(
                            schedule.id(), oldVersion, now);
            default -> throw new IllegalArgumentException(
                    "Unsupported policy");
        }

        schedules.updateOneTimeDefinition(
                schedule.id(),
                oldVersion,
                command.newSendAt());

        audits.record(
                schedule.id(),
                oldVersion,
                newVersion,
                command.policy().name(),
                affected,
                command.actorId(),
                command.reason(),
                now);

        return new RescheduleResult(
                schedule.id(), newVersion, affected);
    }
}
~~~

Các interface/repository/exceptions trong ví dụ là **code ứng dụng minh họa**, không phải API có sẵn của Spring Mail. Repository cần:

- đảm bảo `lockById` thực hiện `SELECT ... FOR UPDATE` hoặc cơ chế locking tương đương;
- cập nhật `version` bằng điều kiện version cũ, kiểm tra affected row count;
- cập nhật request bằng điều kiện state/attempt/lease và trả số hàng thực sự bị thay đổi;
- ghi audit trong cùng DB transaction;
- kiểm tra authorization tenant/actor trước khi sửa lịch;
- ngăn thời gian gửi mới vi phạm deadline hoặc quiet hours.

Đối với `KEEP_EXISTING` trong ví dụ, lịch một lần được cập nhật nhưng job đã tạo không dời; cách này chỉ có ý nghĩa nếu kiến trúc phân biệt các occurrence chưa phát sinh với job cũ. Nếu lịch một lần đã hoàn toàn materialized, business API nên giải thích rõ “chỉ sửa cấu hình lịch” không làm thay đổi email đã hẹn. Không gắn một policy có semantics vô nghĩa vào UI chỉ để đủ enum.

### 7.1. Kiểm tra version để chống ghi đè nhau

Hai quản trị viên cùng mở trang lịch ở version 4:

~~~text
Admin A thấy version 4 -> đổi sang 11:00.
Admin B thấy version 4 -> đổi sang 13:00.

Admin A commit version 5.
Admin B gửi expectedVersion=4 -> nhận 409 Conflict.
~~~

Không âm thầm cho B ghi đè A. API có thể trả lịch mới và yêu cầu người dùng xác nhận lại.

### 7.2. Một request reschedule cần idempotent

Client có thể timeout sau khi server đã commit:

~~~text
Client POST /reschedule
Server COMMIT thành công
Network timeout trước response
Client retry POST /reschedule
~~~

Nếu request retry không có cách nhận diện, hệ thống có thể tạo hai audit events hoặc thay đổi version lần nữa. Nên chấp nhận một `idempotency_key` cho thao tác thay đổi lịch, lưu kết quả cùng transaction và trả kết quả cũ khi client retry cùng key.

Optimistic version bảo vệ khỏi overwrite, nhưng **idempotency key** giúp phục hồi những kết quả HTTP chưa chắc chắn. Hai cơ chế bổ sung nhau.

## 8. Race condition giữa admin và mail worker

Tình huống nguy hiểm:

~~~text
T1 Worker đọc job #A (scheduled_at=10:00, PENDING).
T2 Admin đổi scheduled_at của #A thành 11:00.
T3 Worker vẫn gửi job #A lúc 10:00.
~~~

Nếu worker chỉ `SELECT` rồi gửi sau một thời gian dài, việc admin đổi lịch có thể không còn hiệu lực. Cần cơ chế **atomic claim** hoặc **lease**, không chỉ đọc row rồi làm việc.

### 8.1. Atomic claim với PostgreSQL

~~~sql
WITH due AS (
    SELECT id
    FROM mail_request
    WHERE state IN ('PENDING', 'RETRY_WAIT')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (
          next_attempt_at IS NULL
          OR next_attempt_at <= CURRENT_TIMESTAMP
      )
    ORDER BY scheduled_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_request AS m
SET state = 'CLAIMED',
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM due
WHERE m.id = due.id
RETURNING m.*;
~~~

Ý nghĩa:

- `FOR UPDATE SKIP LOCKED` giúp nhiều worker claim các row khác nhau.
- Update state/lease diễn ra trong cùng một transaction.
- Worker chỉ nhận job đủ điều kiện về `scheduled_at` và `next_attempt_at`.
- Admin reschedule chỉ cập nhật job còn `PENDING`, chưa attempt và chưa claim.

Trong PostgreSQL, các row update cạnh tranh được khóa và điều kiện được kiểm tra dưới semantics transaction phù hợp. Nếu admin khóa/cập nhật job trước, worker sau đó nhìn thời gian mới và không claim sớm. Nếu worker claim trước, admin không còn coi job đó là `PENDING` để dời. Điều này tạo ranh giới nhất quán về **job nào đã bắt đầu thực thi**.

### 8.2. Không giữ DB transaction mở trong suốt SMTP send

Không nên:

~~~text
BEGIN
SELECT ... FOR UPDATE
SMTP connect/send (có thể chờ hàng chục giây)
UPDATE job
COMMIT
~~~

Giữ row lock/DB connection trong khi gọi mạng có thể gây lock contention, deadlock gián tiếp và cạn connection pool. Tốt hơn:

1. Claim một batch ngắn trong DB transaction.
2. Commit lease.
3. Kiểm tra trạng thái và gửi SMTP ngoài transaction.
4. Ghi kết quả attempt bằng transaction mới, dùng worker ownership/fencing token.

Giữa bước 1 và 3 vẫn có race với yêu cầu hủy. Worker nên kiểm tra lại `cancel_requested` trước khi bắt đầu side effect, nhưng **không thể bảo đảm thu hồi email đang nộp cho SMTP** nếu yêu cầu hủy đến sát thời điểm gửi.

### 8.3. Lease và fencing token

Một worker có thể crash sau khi claim. Khi lease hết hạn, job cần được recover. Tuy nhiên, worker cũ có thể chỉ bị pause lâu rồi chạy tiếp.

Ví dụ:

~~~text
Worker A claim job #A (lease=1).
Worker A bị pause.
Lease hết hạn.
Worker B recover và claim (lease=2).
Worker A tỉnh lại và cố ghi SUBMITTED.
~~~

Nên có `lease_version` hoặc claim token được tăng mỗi lần claim:

~~~sql
UPDATE mail_request
SET state = 'SUBMITTED',
    lease_owner = NULL,
    lease_until = NULL
WHERE id = :job_id
  AND lease_version = :expected_lease_version
  AND state = 'SUBMITTING';
~~~

Nếu row count bằng 0, worker cũ không còn quyền cập nhật trạng thái. **Fencing trong database ngăn ghi đè trạng thái**, nhưng không thể ngăn một SMTP request đã phát ra khỏi mạng. Cần tiếp tục dựa trên idempotency, attempt history và xử lý kết quả `UNKNOWN`.

### 8.4. Đừng tự reset mọi SUBMITTING về PENDING

Nếu worker chết **sau khi SMTP server đã chấp nhận message nhưng trước khi DB commit**, job vẫn có thể nằm ở `SUBMITTING`. Tự reset tất cả job này để retry ngay có thể gửi email trùng.

Nên có policy cho outcome không chắc chắn:

- đợi provider event hoặc tra provider message ID nếu API hỗ trợ;
- đánh dấu `UNKNOWN` và đưa vào reconciliation;
- cân nhắc retry theo tính chất email, deadline, nguy cơ duplicate;
- ghi attempt ID và correlation ID để điều tra.

SMTP thuần không cung cấp exactly-once delivery end-to-end; không được hứa rằng một transaction DB đủ để bảo đảm gửi đúng một lần.

## 9. Lịch định kỳ: version hóa thay vì sửa hàng loạt

Ví dụ bản tin hàng tuần:

~~~text
Schedule v1:
  MON 09:00 Asia/Ho_Chi_Minh

Occurrence W46 đã tạo:
  5.000 mail requests.

Admin thay lịch:
  TUE 10:00 Asia/Ho_Chi_Minh
  Schedule v2
~~~

Với chính sách `REPLAN_FUTURE_OCCURRENCES`:

- occurrence W46 đã tạo vẫn có identity và request riêng;
- schedule definition chuyển sang v2;
- `next_fire_at` được tính lại cho các occurrence tương lai;
- không xóa những request W46 đang pending/retry;
- occurrence key được kiểm soát để tránh cùng tuần tạo lần thứ hai nếu business contract chỉ có một bản tin/tuần.

### 9.1. Occurrence key là gì?

Nếu bài toán là “một bản tin cho mỗi tuần ISO”:

~~~text
scheduleId=weekly-newsletter-tenant-a
occurrenceKey=2026-W46
~~~

Nếu chuyển từ thứ Hai sang thứ Ba trong cùng tuần, vẫn là occurrence W46; không tạo thêm một đợt gửi mới chỉ vì fire time khác.

Nếu business contract là “mọi lần cron kích hoạt, kể cả hai lần trong một ngày đều là sự kiện riêng”, occurrence key có thể dựa trên một scheduled fire ID được lưu bền vững. **Quy tắc nhận diện occurrence phải khớp nghiệp vụ**, không thể áp `week number` cho mọi cron.

### 9.2. Không lấy schedule version làm phần duy nhất để chống trùng

Sai:

~~~text
unique(schedule_id, schedule_version, recipient_id)
~~~

Nếu đổi version, cùng một recipient có thể nhận lại cùng nội dung occurrence. Nên dùng:

~~~text
unique(schedule_id, occurrence_key, recipient_key)
~~~

và duy trì schedule version như metadata/audit. Khi cần cho phép gửi lại một occurrence có chủ đích, tạo một **resend operation ID** được kiểm soát và audit riêng, không lách unique bằng thay version.

### 9.3. Tạo occurrence và cập nhật con trỏ trong một transaction

Scheduler chạy nhiều instance:

~~~text
Replica A thấy schedule đến hạn.
Replica B cũng thấy schedule đến hạn.
~~~

Nếu cả hai tự tạo job, số email có thể tăng gấp đôi. Thiết kế:

1. Lock schedule row hoặc claim schedule lease.
2. Đọc version và `next_fire_at` hiện tại.
3. Tạo occurrence key và persist occurrence.
4. Tạo/incrementally enqueue requests với unique constraint.
5. Tính và ghi `next_fire_at` mới.
6. Commit.

Nếu tạo hàng chục nghìn requests, không nhất thiết insert toàn bộ trong một transaction quá lớn; có thể lưu **occurrence** một lần và cho generator phân batch theo cursor với idempotency key trên từng recipient.

Quan trọng là **không cập nhật next_fire_at như đã tạo xong khi thực tế chưa ghi được bất kỳ durable occurrence nào**.

### 9.4. Cập nhật lịch đồng thời với scheduler tick

Nếu admin đổi cron trong lúc scheduler sắp fire, cần một quy tắc serialization:

~~~text
Admin transaction:
  lock schedule row -> update version/next_fire_at

Scheduler transaction:
  lock same row -> check version/due -> create occurrence
~~~

Hai transaction không nên tự đọc một snapshot cron cũ rồi cùng commit những quyết định không tương thích. DB locking/version check tạo thứ tự rõ ràng:

- scheduler thắng trước: occurrence cũ đã được tạo, admin xử lý theo policy đã công bố;
- admin thắng trước: scheduler dùng version mới và `next_fire_at` mới;
- không âm thầm xóa occurrence đã commit.

## 10. @Scheduled nên đánh thức dispatcher, không chứa toàn bộ backlog

Một hướng đơn giản trong Spring Boot:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Dispatcher:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailDispatchTick {
    private final DueMailJobService jobs;

    public MailDispatchTick(DueMailJobService jobs) {
        this.jobs = jobs;
    }

    @Scheduled(
        fixedDelayString = "${app.mail.dispatch-delay:PT5S}")
    public void dispatchDueJobs() {
        jobs.claimAndDispatchDueBatch(50);
    }
}
~~~

`DueMailJobService` là service của ứng dụng, phải thực hiện claim transaction/lease và gửi bằng sender thích hợp. `@Scheduled` chỉ kích hoạt việc quét DB **đã lưu bền vững**.

Tại sao cách này giúp thay đổi lịch an toàn?

- Giờ gửi nằm trong `mail_request.scheduled_at`, không nằm hoàn toàn trong annotation.
- Khi admin đổi lịch, transaction cập nhật schedule/jobs theo policy.
- Tick tiếp theo chỉ claim những job đã đến hạn.
- Khi process restart, các row pending vẫn trong database.
- Nếu một tick bị bỏ lỡ, tick sau có thể tiếp tục tìm job đến hạn.

### 10.1. @Scheduled không tự đồng bộ đa instance

Nếu deploy ba replicas, method `@Scheduled` có thể chạy trên cả ba. Điều đó không nhất thiết sai nếu claim bằng SQL atomic `SKIP LOCKED`, nhưng sẽ sai nếu mỗi replica gọi:

~~~java
repository.findAllDueJobs()
        .forEach(job -> sender.send(job));
~~~

mà không có claim/lease/idempotency.

### 10.2. Thay đổi interval dispatcher khác thay đổi lịch nghiệp vụ

`app.mail.dispatch-delay=PT5S` kiểm soát **tần suất quét**. Thay thành `PT10S` có thể cần restart/refresh scheduler tùy cấu hình Spring; nó **không** đổi giờ gửi đã lưu trong `scheduled_at`.

Đừng trộn hai khái niệm:

~~~text
Dispatch interval: cứ 5 giây nhìn DB một lần.
Business schedule: gửi email vào 10:00 ngày 15/11.
~~~

Việc đổi interval là thay đổi nhịp làm việc của worker; việc đổi business schedule cần cập nhật dữ liệu nghiệp vụ.

## 11. TaskScheduler và việc hủy task an toàn

`TaskScheduler` hữu ích khi cần đăng ký các trigger động trong JVM. Tuy nhiên, nếu tác vụ được tạo chỉ bằng `ScheduledFuture`, restart có thể làm mất nó.

Một pattern an toàn hơn:

~~~text
Database:
  mail_schedule + durable mail_request

TaskScheduler:
  chỉ đánh thức dispatcher hoặc đánh thức để tính occurrence

Khi schedule thay đổi:
  1. Commit new schedule version vào DB.
  2. Refresh/re-register JVM trigger nếu cần.
  3. Trigger mới đọc lại DB trước khi materialize work.
  4. Job đã tồn tại vẫn nằm trong DB.
~~~

Ngay cả nếu `ScheduledFuture.cancel(false)` trả về thành công, nó không chứng minh task cũ chưa tạo job hoặc chưa gọi SMTP. Nếu callback đã bắt đầu, cần dùng schedule version check và idempotent occurrence generation.

### 11.1. Cancel của ScheduledFuture không phải cancel email

~~~java
boolean cancelled = scheduledFuture.cancel(false);
~~~

Giá trị trả về chỉ liên quan trạng thái future theo semantics Java concurrency. Nó không tự:

- xóa mail đã được nộp SMTP;
- rút lại email đã tạo trong database;
- hủy retry job;
- cập nhật audit;
- chặn một worker khác.

Vì vậy API người dùng “hủy yêu cầu gửi” phải tác động tới **durable mail_request** với trạng thái và điều kiện phù hợp.

## 12. Quartz với JDBC JobStore

Với hệ thống có lịch phức tạp, nhiều node và yêu cầu persist trigger, **Quartz** là một lựa chọn. `JDBC JobStore` có thể lưu jobs/triggers vào database và hỗ trợ clustering theo cấu hình, giảm phụ thuộc vào một JVM.

Nhưng cần phân biệt:

- **Quartz job/trigger:** mô tả thời điểm chạy logic.
- **Application mail request:** yêu cầu gửi riêng của từng người nhận, có dữ liệu/status/retry.

Thay Quartz trigger không tự cập nhật hoặc xóa đúng những mail requests đã materialized. Nếu business yêu cầu dời những job pending, vẫn cần chính sách ở tầng ứng dụng.

### 12.1. Reschedule một cron trigger

Ví dụ Quartz API:

~~~java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.TriggerBuilder;
import org.quartz.TriggerKey;

public class QuartzScheduleUpdater {
    private final Scheduler quartz;

    public QuartzScheduleUpdater(Scheduler quartz) {
        this.quartz = quartz;
    }

    public void update(
            TriggerKey triggerKey,
            JobKey jobKey,
            String cron,
            String timeZoneId) throws Exception {

        CronScheduleBuilder schedule =
                CronScheduleBuilder.cronSchedule(cron)
                        .inTimeZone(TimeZone.getTimeZone(timeZoneId))
                        .withMisfireHandlingInstructionDoNothing();

        CronTrigger replacement = TriggerBuilder.newTrigger()
                .withIdentity(triggerKey)
                .forJob(jobKey)
                .withSchedule(schedule)
                .build();

        quartz.rescheduleJob(triggerKey, replacement);
    }
}
~~~

Ví dụ dùng `withMisfireHandlingInstructionDoNothing()` chỉ để thể hiện **một lựa chọn** misfire: bỏ các lần fire đã lỡ và tính mốc tiếp theo. **Không chọn mặc định cho tất cả use case.** Hóa đơn, báo cáo hoặc cảnh báo bắt buộc có thể cần catch-up đã được thiết kế rõ; marketing có thể bỏ qua một đợt quá hạn.

Khi production có cả bảng `mail_schedule` và Quartz JobStore, cần quyết định cái nào là **source of truth**. Việc update hai database/store không trong cùng transaction có thể tạo trạng thái lệch; cần outbox/reconciliation hoặc một cơ chế đồng bộ có kiểm soát.

### 12.2. Misfire có thể trông giống mất yêu cầu

“Misfire” thường là trường hợp trigger lỡ thời điểm chạy vì scheduler tạm dừng, node restart hoặc quá tải. Có thể:

- chạy bù một số occurrence;
- bỏ qua occurrence quá hạn;
- tạo một lần fire bù rồi tiếp tục.

Chọn sai misfire policy có thể làm bản tin bị gửi dồn sau outage hoặc bỏ qua sự kiện quan trọng. Hãy định nghĩa ở tầng nghiệp vụ:

~~~text
Missed marketing newsletter:
  có thể skip nếu campaign đã hết thời hạn.

Missed monthly invoice:
  cần tạo đủ invoice/email cần thiết, có thể gửi trễ.

Missed OTP:
  không gửi nếu token đã hết hạn.
~~~

Không dùng một misfire policy chung cho mọi loại email.

## 13. Múi giờ, DST và thay đổi timezone

Lịch gửi thường được nhập bằng **giờ địa phương**, nhưng database/worker cần so sánh thời điểm tuyệt đối.

Ví dụ:

~~~text
Người dùng chọn:
  09:00 Asia/Ho_Chi_Minh ngày 15/11/2026

Lưu:
  timezone_id=Asia/Ho_Chi_Minh
  local_send_time=09:00 (nếu cần hiển thị/quy tắc)
  scheduled_at=<Instant UTC đã tính>
~~~

Không nên chỉ lưu chuỗi `2026-11-15 09:00` mà không biết timezone, vì hai tenant ở vùng khác nhau có thể muốn nhận ở các thời điểm UTC khác nhau.

### 13.1. DST làm một số thời gian không tồn tại hoặc lặp

Ở một số timezone, khi chuyển sang giờ mùa hè:

- 02:30 có thể **không tồn tại** trong ngày chuyển giờ;
- 01:30 có thể xảy ra **hai lần** khi đồng hồ lùi.

Nếu lịch định kỳ là “02:30 mỗi ngày” cần một policy:

- bỏ qua thời điểm không tồn tại;
- dời sang thời điểm hợp lệ kế tiếp;
- chọn offset đầu/offset sau ở thời gian trùng;
- hoặc một quy tắc domain riêng.

Không dùng offset cố định `+07:00` cho tenant ở `America/New_York` và nghĩ nó tương đương timezone quanh năm.

### 13.2. Đổi timezone là thay đổi semantic

“Mỗi ngày 09:00 Asia/Ho_Chi_Minh” sang “mỗi ngày 09:00 Europe/Paris” làm thay đổi UTC fire time. Đây là **thay đổi lịch**, cần version và policy đối với pending occurrences.

Nếu người dùng chỉ đổi **timezone hiển thị**, không được tự sửa `scheduled_at` của job đã hẹn. Phân biệt:

~~~text
DISPLAY_TIMEZONE_CHANGED
SCHEDULE_TIMEZONE_CHANGED
~~~

### 13.3. Dùng Clock trong code

~~~java
import java.time.Clock;
import java.time.Instant;

Instant now = clock.instant();
~~~

Inject `Clock` cho phép kiểm thử những trường hợp trước/sau mốc lịch mà không dùng `Thread.sleep(...)` và không phụ thuộc thời gian thực của máy CI.

Với cron, dùng `ZoneId` và thư viện parser tương thích phiên bản Spring/Quartz để tính lần fire tiếp theo; không tự cộng `Duration.ofDays(1)` cho lịch “09:00 mỗi ngày” ở timezone có DST.

## 14. Quiet hours, consent và deadline khi dời lịch

Thay đổi giờ gửi có thể làm email rơi vào khung giờ không được phép hoặc vượt thời hạn hiệu lực.

### 14.1. Quiet hours

Ví dụ chính sách marketing:

~~~text
Không gửi khuyến mãi từ 22:00 đến 08:00 theo giờ tenant.
~~~

Nếu admin dời chiến dịch từ 20:00 sang 23:00, ứng dụng cần:

- từ chối thời gian mới;
- hoặc tự đề xuất giờ hợp lệ tiếp theo;
- hoặc hiển thị rõ policy được áp dụng.

Không âm thầm vi phạm quiet hours chỉ vì row đã `PENDING`.

### 14.2. Consent có thể thay đổi trong thời gian chờ

Một recipient đăng ký bản tin lúc job được tạo, nhưng unsubscribe trước khi đến giờ gửi:

~~~text
10:00 Job newsletter được xếp lịch cho 16:00.
11:00 Recipient unsubscribe.
16:00 Worker chuẩn bị gửi.
~~~

Worker phải **kiểm tra lại eligibility/opt-out** tại điểm gửi theo policy; việc job đã tồn tại không biến nó thành quyền gửi vĩnh viễn. Khi không còn đủ điều kiện, ghi `SUPPRESSED` hoặc `CANCELLED_BY_POLICY` có audit thay vì xóa vô dấu vết.

### 14.3. Expiry/deadline

Một email OTP có `expires_at`:

~~~text
created_at    10:00
scheduled_at  10:01
expires_at    10:05
~~~

Nếu lịch bị dời sang 11:00, gửi email chứa OTP đã hết hạn là vô ích và gây khó hiểu. Nên:

- từ chối lệnh reschedule nếu vi phạm;
- hoặc chuyển job sang trạng thái expired/cancelled theo policy;
- hoặc phát hành yêu cầu OTP mới nếu business use case cho phép.

Không gia hạn token bảo mật chỉ bằng cách sửa `scheduled_at` mà không đi qua quy trình xác thực phù hợp.

## 15. Nội dung email: snapshot hay render tại thời điểm gửi?

Khi một request phải chờ nhiều giờ, dữ liệu có thể thay đổi.

Ví dụ email hóa đơn được hẹn gửi lúc 09:00 nhưng admin đổi thành 15:00. Trong thời gian đó:

- thông tin người nhận có thể đổi;
- số tiền hoặc trạng thái invoice có thể được điều chỉnh;
- template có thể lên version mới;
- link/token có thể hết hạn;
- attachment có thể bị dọn theo retention.

Hai lựa chọn:

| Cách | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **Snapshot nội dung khi tạo job** | Gửi đúng nội dung đã cam kết; dễ audit | Có thể lỗi thời, token hết hạn, tốn storage |
| **Render tại lúc gửi** | Dùng dữ liệu mới nhất, dễ đổi template | Thay đổi nội dung so với lúc lập lịch, thiếu dữ liệu nếu bản ghi đã xóa |

Không có lựa chọn tuyệt đối đúng. Cần phân loại theo nghiệp vụ:

- Hóa đơn có thể cần snapshot tài liệu đã phát hành.
- Newsletter có thể render theo campaign đã duyệt.
- OTP/token cần gắn với thời hạn và quy tắc tái phát hành.
- Thông báo trạng thái có thể cần kiểm tra trạng thái hiện tại trước gửi để tránh nội dung sai.

### 15.1. Không để attachment tạm hết hạn trước giờ mới

Nếu job chứa `payload_ref` tới file tạm:

~~~text
File retention: 24h
Reschedule job: từ 12h tới 72h
~~~

Worker sẽ không còn file khi tới giờ gửi. Trước khi reschedule cần kiểm tra **lifetime** của payload/attachment và quyền truy cập. Có thể dùng durable object storage với retention phù hợp, hoặc chính sách render/regen an toàn khi cần.

### 15.2. Template version nên được audit

Nếu content được render tại thời điểm gửi, lưu template ID/version hoặc rule lựa chọn version. Khi email thực tế khác bản preview lúc người dùng đặt lịch, support cần biết nguyên nhân.

Không tạo metric label riêng cho mỗi dynamic template version; chi tiết này thích hợp ở job/audit event store.

## 16. Khi đổi lịch giữa một campaign lớn

Một campaign có 500.000 người nhận, trong đó 300.000 mail requests còn pending. Một transaction update tất cả row có thể:

- khóa nhiều row trong thời gian dài;
- làm worker chờ;
- gây WAL/replication lag;
- gây deadlock hoặc timeout;
- khiến giao diện quản trị bị chặn lâu.

Đổi lịch quy mô lớn cần một **rescheduling operation** bền vững:

~~~text
reschedule_operation:
  operationId=op-123
  scheduleId=campaign-88
  oldVersion=4
  newVersion=5
  policy=MOVE_UNSTARTED
  status=IN_PROGRESS
  rowsPlanned=300000
  rowsChanged=...
  cursor=...
~~~

### 16.1. Chuyển trạng thái theo batch

Ví dụ:

1. Ghi version mới và tạo reschedule operation.
2. Tạm dừng claim mới **thuộc scope cần di chuyển** hoặc thêm điều kiện effective-version trên dispatcher.
3. Cập nhật job đủ điều kiện theo batch nhỏ, có cursor và idempotency.
4. Ghi tiến độ/affected count; không xóa job.
5. Khi hoàn tất, mở lại dispatcher cho scope đó.
6. Báo kết quả thực tế: moved, skipped vì claimed/sent, retry, invalid, cancelled.

**Cần có giao thức đồng bộ thật sự** giữa pause/reschedule/dispatch, không chỉ một biến boolean trong RAM. Có thể dùng schedule-level state trong DB, lease hoặc rule claim theo schedule version để nhiều pod đều tuân thủ.

### 16.2. Không giả định “đã sửa 100%”

Trong lúc operation chạy, một số job có thể:

- vừa được worker claim trước ranh giới cutover;
- đã submitted;
- bước vào retry;
- hết hạn;
- bị unsubscribe/cancel.

Dashboard nên hiển thị:

~~~text
Requested reschedule: 300.000
Moved:                298.740
Skipped in-flight:        110
Skipped submitted:        900
Skipped retry:            250
~~~

Số liệu chỉ minh họa. Mỗi nhóm có lý do và dữ liệu audit; không báo “thành công 300.000” nếu chỉ 298.740 thực sự thay giờ.

### 16.3. Đảm bảo resume khi process crash

Nếu reschedule operation là một job bền vững, process có thể restart rồi tiếp tục từ cursor. Batch phải idempotent: chạy lại cùng batch không được cộng giờ hai lần hoặc đổi sai schedule version.

Không dùng:

~~~text
scheduled_at = scheduled_at + INTERVAL '1 hour'
~~~

lặp lại vô điều kiện sau crash, vì có thể thành **+2 giờ**. Tốt hơn dùng giá trị đích xác định theo operation, hoặc điều kiện `schedule_version = oldVersion` để một row chỉ được di chuyển một lần.

## 17. Khôi phục sau downtime và missed schedules

Giả sử server ngừng hoạt động 45 phút, trong khi có nhiều job tới hạn.

Khi ứng dụng chạy lại:

~~~text
Pending rows trong DB: vẫn còn.
Dispatcher tick: tìm scheduled_at <= now.
Worker: claim và xử lý theo deadline/policy.
~~~

Đó là lợi ích của durable job store: **yêu cầu không biến mất chỉ vì một lần tick bị bỏ lỡ**.

### 17.1. Catch up hay skip?

Không phải mọi email quá hạn đều nên gửi:

| Loại email | Policy có thể phù hợp |
| --- | --- |
| Hóa đơn quan trọng | Catch up, ghi nhận trễ |
| Xác nhận đơn | Catch up khi vẫn có ý nghĩa |
| OTP hết hạn | Không gửi mã đã hết hạn |
| Daily digest | Có thể gộp hoặc skip theo product rule |
| Quảng cáo có thời hạn | Skip nếu campaign expired |
| Nhắc hẹn | Không gửi thông báo “sắp diễn ra” sau khi sự kiện kết thúc |

Không coi việc **có row pending** là lý do để gửi bất kỳ nội dung nào, bất kể thời hạn và consent.

### 17.2. Không tạo lại cùng occurrence khi restart

Scheduler có thể quét `next_fire_at` quá khứ và cố tạo occurrence nhiều lần sau mỗi restart. Unique occurrence key và transaction sẽ ngăn tạo cùng job hai lần.

Một incident cần được ghi:

~~~text
Missed occurrence identified.
Occurrence already exists -> no-op / reconcile missing recipients.
Occurrence not created -> materialize according to catch-up policy.
~~~

Không chỉ cập nhật `next_fire_at = now + interval` và bỏ qua các occurrence cũ mà chưa biết liệu chúng là nghiệp vụ bắt buộc hay có thể skip.

## 18. API quản trị thay đổi lịch an toàn

Một API có thể yêu cầu:

~~~http
PATCH /api/mail-schedules/98b.../timing
If-Match: "version-7"
Idempotency-Key: 5db2...
Content-Type: application/json

{
  "newSendAt": "2026-11-15T04:00:00Z",
  "policy": "MOVE_UNSTARTED",
  "reason": "Chuyển chiến dịch sang buổi chiều"
}
~~~

Đây là giao diện minh họa, không phải API Spring Mail mặc định. Backend cần:

- kiểm tra quyền quản trị lịch đúng tenant;
- validate timestamp, timezone, cron, deadline, quiet hours;
- xác minh version hiện tại (optimistic concurrency);
- kiểm tra idempotency key;
- tính **preview impact**;
- thực hiện transaction hoặc tạo batch operation;
- trả kết quả gồm số job moved/skipped;
- ghi audit actor, before/after, reason.

### 18.1. Preview trước khi commit

Ví dụ giao diện:

~~~text
Bạn đang thay đổi giờ gửi từ 10:00 thành 11:00.

Các yêu cầu:
  620 chưa xử lý, có thể dời
   30 đang retry, sẽ giữ lịch retry cũ
   20 đang xử lý, không thể bảo đảm thu hồi
  130 đã submitted, không thay đổi

Chính sách: chỉ dời các yêu cầu chưa bắt đầu.
~~~

Preview là ảnh chụp tại một thời điểm. Đến lúc commit, số lượng có thể thay đổi do workers; backend phải trả **affected count thực tế** và lý do skipped, không coi preview là kết quả cam kết.

### 18.2. API cần phân biệt update với cancel

Không gộp:

~~~text
PUT /schedule/{id} { enabled: false }
~~~

với “hủy tất cả email pending” nếu chưa có contract rõ. Tắt lịch có thể chỉ nghĩa **không tạo occurrence mới**, còn cancel pending là thao tác riêng.

Ví dụ:

~~~text
DISABLE_SCHEDULE: dừng phát sinh mới.
CANCEL_UNSENT: hủy những job còn đủ điều kiện.
RESCHEDULE_UNSTARTED: dời những job chưa bắt đầu.
~~~

Mỗi action nên có quyền, policy, audit và thông báo cho người dùng tương ứng.

## 19. Tình huống có nhiều worker và thay đổi lịch

Một timeline:

~~~text
09:59:58 Worker A claim job #101.
09:59:59 Admin đổi lịch từ 10:00 sang 11:00.
10:00:00 Worker B quét job due.

Job #101:
  đã CLAIMED trước cutover, không được dời tự động.

Job #102:
  vẫn PENDING khi admin transaction khóa/update.
  scheduled_at chuyển thành 11:00.

Worker B:
  thấy #102 chưa đến hạn, không gửi.
~~~

Nếu worker A chưa thực sự gửi, sản phẩm có thể bổ sung `cancel_requested` và pre-send check để cố ngăn. Nhưng không được hứa **100% hủy được in-flight mail** vì SMTP side effect có thể bắt đầu giữa lúc check và gửi.

### 19.1. Không để retry worker lách giờ mới

Một lỗi:

~~~text
Main queue dùng scheduled_at.
Retry queue chỉ dùng next_attempt_at.
Admin dời scheduled_at sang 11:00.
Retry worker gửi lúc 10:06 dù policy muốn giữ tất cả đến 11:00.
~~~

Nếu product policy áp dụng giờ mới cho cả retries, dispatcher phải kiểm tra:

~~~text
now >= scheduled_at AND now >= next_attempt_at
~~~

Nhưng quyết định có áp dụng giờ mới cho retry jobs hay không phải được làm rõ trước. Đừng vô tình thay đổi ngữ nghĩa retry.

### 19.2. Không cho scheduler tạo job mới trong khi đang reschedule cùng occurrence

Nếu materializer và admin operation chạy đồng thời, cần row lock/version/operation status để tạo ra một thứ tự nhất quán. Không chỉ “đặt thêm một thread lock” trên từng JVM: nhiều replicas không chia sẻ Java `synchronized` hoặc `ReentrantLock`.

## 20. Metrics, audit và alert

Các chỉ số hữu ích:

| Metric đề xuất | Mục đích |
| --- | --- |
| `mail_schedule_changes_total` | Số lần đổi lịch theo policy/result |
| `mail_reschedule_jobs_moved_total` | Số job thực sự được dời |
| `mail_reschedule_jobs_skipped_total` | Số job không thể dời, phân loại lý do |
| `mail_reschedule_operation_duration_seconds` | Thời gian hoàn thành operation |
| `mail_pending_jobs` | Số job đang chờ |
| `mail_oldest_eligible_pending_age_seconds` | Job đủ điều kiện nhưng chưa được claim lâu nhất |
| `mail_submission_attempts_total` | Số lần thử transport |
| `mail_jobs_expired_total` | Job quá deadline bị loại theo policy |
| `mail_schedule_occurrence_deduplicated_total` | Những lần materializer phát hiện occurrence đã tồn tại |
| `mail_claim_lease_expired_total` | Số lease cần recovery |
| `mail_unknown_submission_total` | Các attempt không xác định kết quả |

Đây là những tên **ứng dụng có thể tự instrument**, không phải tất cả metric Spring Framework Mail tự cung cấp.

### 20.1. Nhãn có giới hạn

Có thể dùng:

~~~text
mail_type=otp|invoice|newsletter|order_confirmation
policy=keep_existing|move_unstarted|cancel_unsent
result=success|conflict|validation_failed|partial
skip_reason=claimed|submitted|retry_wait|expired|cancelled
~~~

Không đưa job ID, tenant ID có cardinality lớn, recipient email, raw reason hoặc nội dung thư làm metric label. Chi tiết theo job/tenant ở audit database có phân quyền.

### 20.2. Dashboard rescheduling

Một màn hình:

~~~text
Schedule: Campaign 88
Current version: 5
Old timing: 10:00
New timing: 11:00

Operation status: COMPLETED
Eligible before:  50.000
Moved:            49.200
Skipped in-flight:   250
Skipped retry:       300
Skipped other:       250

Pending at new time: 49.200
Old pending remaining: review 300 (retry policy)
~~~

Những con số mang tính minh họa. Dashboard nên hiển thị thời điểm cập nhật và **số lượng thực tế**, không chỉ số lượng preview.

### 20.3. Cảnh báo

- Reschedule operation `IN_PROGRESS` quá lâu hoặc không tiến triển.
- Schedule enabled nhưng nhiều occurrence đến hạn không được materialize.
- Pending backlog vẫn tăng sau khi lịch được thay.
- Một nhóm job bị dời nhưng bị dispatcher gửi **trước `scheduled_at`**.
- Tỷ lệ attempt unknown hoặc duplicate tăng sau cutover.
- Không có sự kiện audit cho thay đổi lịch quan trọng.
- Email quá deadline vẫn được submit.

Điều tra cần có job/occurrence/operation correlation ID, nhưng không dump toàn bộ email body hay secret vào log.

## 21. Kiểm thử với Clock cố định và worker cạnh tranh

Test thay lịch phải kiểm tra **dữ liệu còn tồn tại và không bị gửi sai giờ**, không chỉ kiểm tra HTTP trả 200.

### 21.1. Unit test policy

Với `Clock.fixed(...)`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T03:00:00Z"),
        ZoneOffset.UTC);
~~~

Test cases:

1. `PENDING`, `attempt_count=0`, chưa claim → đổi giờ thành công.
2. `RETRY_WAIT` → giữ lịch retry theo `MOVE_UNSTARTED`.
3. `CLAIMED` → không dời, có skipped count.
4. `SUBMITTED` → không dời hoặc “gửi lại”.
5. `UNKNOWN` → không retry mù.
6. Lịch version đã đổi → conflict, không ghi đè.
7. Request reschedule lặp cùng idempotency key → trả kết quả cũ.
8. Giờ mới quá deadline/quiet hours → validation theo policy.
9. `KEEP_EXISTING` → pending jobs không đổi.
10. `CANCEL_UNSENT` → chuyển trạng thái, không xóa row.

### 21.2. Integration test với database thật

Các thao tác `SELECT ... FOR UPDATE SKIP LOCKED` và transaction isolation cần được kiểm tra bằng PostgreSQL/test container cùng loại DB production. Mock repository không đủ chứng minh race safety.

Một test concurrency quan trọng:

~~~text
Transaction A: admin reschedule.
Transaction B: worker claim cùng job.

Chạy nhiều lần với thứ tự xen kẽ:
  - A commit trước -> B không claim job khi giờ mới chưa đến.
  - B claim trước -> A skip job CLAIMED.

Không có trạng thái:
  job mất khỏi DB;
  job vừa bị dời vừa được coi chưa claim để gửi ngay;
  một occurrence tạo hai mail requests cùng recipient.
~~~

### 21.3. Test crash/restart

Kịch bản:

1. Tạo 100 pending mail jobs.
2. Reschedule một phần theo policy.
3. Dừng process giữa reschedule batch hoặc sau khi DB commit.
4. Khởi động lại worker/scheduler.
5. Xác minh pending jobs vẫn tồn tại.
6. Operation resume idempotent, không cộng giờ hai lần.
7. Worker chỉ claim những job đến hạn.
8. Duplicate occurrence request bị unique constraint chặn.

### 21.4. Test SMTP bằng GreenMail/Mailpit

Gửi thử qua SMTP server giả lập:

- trước giờ mới: mailbox không có message tương ứng;
- sau giờ mới: job được submit theo chính sách;
- worker retry không tạo thêm logical job;
- một job cancelled không được gửi;
- lỗi SMTP tạm thời không xóa job;
- attempt state được ghi rõ khi simulated timeout.

Nếu workflow chạy async, chờ điều kiện với timeout thay vì `Thread.sleep(...)`. Negative assertion “không gửi” phải đợi cho đến khi worker tick/claim có thể xảy ra và application đạt trạng thái quan sát được; chỉ kiểm tra mailbox rỗng ngay lúc đầu chưa đủ.

### 21.5. Test cron và DST

Các tình huống:

- Đổi từ thứ Hai sang thứ Ba trong cùng tuần, không tạo hai occurrence nếu contract một newsletter/tuần.
- Đổi timezone làm fire time UTC thay đổi đúng.
- Thời điểm DST gap/overlap theo rule được công bố.
- Downtime bỏ lỡ hai occurrences: catch-up/skip đúng theo mail type.
- Một schedule disabled không tạo occurrence mới, nhưng pending cũ giữ nguyên nếu policy yêu cầu.

### 21.6. Dọn test fixtures

Test tích hợp nên dọn:

- SMTP test mailbox/server;
- mail schedule/occurrence/request/attempt/audit rows thuộc test;
- background workers và retry tasks;
- file attachment tạm;
- leases và job state;
- tài nguyên container/port.

Không purge hàng đợi/mailbox dùng chung khi các test chạy song song; dùng ID/namespace riêng.

## 22. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ lưu lịch trong `ScheduledFuture` | Restart mất tác vụ chờ | Durable schedule/job store |
| Hủy cron cũ đồng nghĩa xóa mọi pending | Mất yêu cầu không chủ đích | Tách definition và requests |
| Xóa job cũ rồi tạo job mới khi đổi giờ | Gửi trùng, mất audit/ID | Cập nhật job đủ điều kiện tại chỗ |
| UPDATE tất cả job `sent=false` | Đụng retry, claimed, unknown | State machine + điều kiện cụ thể |
| Đổi `next_attempt_at` như đổi business schedule | Backoff sai, có thể trì hoãn vô hạn | Tách scheduled_at và retry time |
| Dời mọi occurrence định kỳ về một giờ | Trộn các chu kỳ khác nhau | Version schedule và occurrence-specific policy |
| Dùng schedule version trong unique key thay occurrence | Đổi lịch tạo duplicate | Stable occurrence key + recipient |
| Không locking/version check giữa admin và worker | Gửi sớm hoặc mất update | Transaction + atomic claim |
| Giữ DB lock suốt SMTP call | Lock contention, cạn kết nối | Claim/commit, send, ack |
| Reset mọi `SUBMITTING` sau crash | Có thể gửi trùng | UNKNOWN/reconciliation |
| Nhiều pod `@Scheduled` đọc cùng row | Duplicate dispatch | SKIP LOCKED/lease/dedup |
| Quên timezone/DST | Lệch giờ hoặc lặp occurrence | ZoneId + policy DST |
| Đổi lịch sau khi OTP hết hạn | Thông báo vô ích | Deadline validation |
| Không kiểm tra marketing opt-out lúc gửi | Gửi cho người đã hủy đăng ký | Revalidate consent at dispatch |
| Reschedule 500.000 rows một transaction | Lock quá lâu, khó phục hồi | Versioned batch operation |
| Batch reschedule bằng `scheduled_at + interval` lặp lại | Crash/retry cộng giờ nhiều lần | Absolute target + version guard |
| Chỉ đo số cron ticks | Không biết mail pending bị mất/chậm | Job backlog, age, audit metrics |
| Không audit ai đổi lịch | Khó giải thích và khôi phục | Before/after, actor, policy, counts |
| Dùng Quartz misfire DoNothing cho email bắt buộc | Bỏ mất occurrence nghiệp vụ | Catch-up/skip theo mail type |

## 23. Tình huống tổng hợp: đổi giờ gửi bản tin tuần

Một tenant đang có:

~~~text
Schedule: weekly-newsletter-tenant-a
Rule v4: MON 09:00 Asia/Ho_Chi_Minh
Occurrence: 2026-W46

Mail requests đã tạo cho W46:
  8.000 PENDING
    100 CLAIMED
     80 RETRY_WAIT
    820 SUBMITTED
~~~

Quản trị viên muốn đổi sang **TUE 10:00**.

### 23.1. Bước 1 — Chọn semantics

Nếu chỉ muốn lịch mới áp dụng từ tuần sau:

~~~text
Policy = REPLAN_FUTURE_OCCURRENCES

W46 đã tạo:
  giữ các request và trạng thái như cũ

W47 trở đi:
  tính theo TUE 10:00
~~~

Đây thường là lựa chọn ít bất ngờ nhất cho lịch định kỳ.

Nếu muốn dời một phần W46 đã tạo, sản phẩm phải cho chọn **occurrence cụ thể** cùng `MOVE_UNSTARTED`, không cập nhật toàn bộ lịch nhiều tuần.

### 23.2. Bước 2 — Preview tác động

~~~text
Target occurrence: 2026-W46
Eligible PENDING never attempted: 8.000
In-flight: 100
Retry: 80
Already submitted: 820

Proposed:
  Move 8.000 requests to new instant.
  Keep in-flight/ retry / submitted unchanged.
~~~

Preview có thể thay đổi do worker đang chạy. API commit phải trả actual counts.

### 23.3. Bước 3 — Thực hiện cutover

1. Xác thực quyền và version schedule.
2. Commit schedule version v5 và operation ID.
3. Nếu cần batch move, chặn claim mới thuộc scope W46 trong thời gian chuyển.
4. Dời những job `PENDING`/chưa attempt, giữ request ID.
5. Ghi audit moved/skipped.
6. Gỡ rào chắn dispatcher và tính lại `next_fire_at`.

Worker chỉ gửi khi cả `scheduled_at` và retry eligibility đạt. Không gửi lại `SUBMITTED` chỉ vì lịch đổi.

### 23.4. Bước 4 — Xác minh

Sau cutover:

- Đủ mail request rows, không có request bị xóa âm thầm.
- Số moved thực tế khớp audit.
- Các job moved không bị gửi trước giờ mới.
- Retry jobs tuân thủ policy đã công bố.
- Không tạo occurrence W46 lần hai.
- Backlog và metrics phản ánh trạng thái đúng.

**Kết luận tình huống:** thay đổi giờ của **schedule definition** và thay đổi giờ của **đã materialized mail requests** là hai thao tác khác nhau. Chỉ khi sản phẩm yêu cầu cả hai thì mới làm cả hai, với transaction, state filtering và audit rõ ràng.

## 24. Checklist trước production

### Kiến trúc

- [ ] Schedule definition và durable mail request là hai thực thể riêng.
- [ ] Có occurrence identity ổn định cho lịch định kỳ.
- [ ] Mail job có unique/idempotency key phù hợp nghiệp vụ.
- [ ] Pending jobs tồn tại qua restart/deploy.
- [ ] Worker claim bằng DB locking/lease an toàn đa replica.

### Thay đổi lịch

- [ ] Có policy rõ: KEEP_EXISTING, MOVE_UNSTARTED, CANCEL_UNSENT hoặc replan future occurrences.
- [ ] UI/API preview số job có thể bị tác động.
- [ ] Chỉ sửa job đủ điều kiện theo state/attempt/claim.
- [ ] Retry time, deadline và scheduled time được tách.
- [ ] Có optimistic version, idempotency key và audit.
- [ ] Batch operation có thể resume nếu số lượng rất lớn.

### Tính đúng đắn

- [ ] Không xóa pending job chỉ vì đổi cron/trigger.
- [ ] Không tạo lại cùng occurrence khi đổi version.
- [ ] Không coi SMTP timeout luôn đồng nghĩa chưa gửi.
- [ ] In-flight/submitted không bị cập nhật tùy tiện.
- [ ] Các job đã cancelled không tự xuất hiện trở lại.
- [ ] Consent, quiet hours, token expiry được kiểm tra khi dispatch.
- [ ] Payload/attachment còn tồn tại tới lúc gửi.

### Thời gian và vận hành

- [ ] Lưu timezone IANA và timestamps UTC/Instant đúng.
- [ ] Có policy rõ cho DST gap/overlap và downtime misfire.
- [ ] Theo dõi backlog, oldest eligible age, moved/skipped và unknown results.
- [ ] Có runbook xử lý stuck reschedule hoặc worker lease.
- [ ] Có kiểm thử concurrency/restart/time shift với DB thật.
- [ ] Có kiểm thử SMTP sandbox và cleanup tài nguyên.

## 25. Những điều cần nhớ

- **Thay đổi lịch gửi không được mặc định đồng nghĩa xóa những yêu cầu đã chờ.**
- Tách **schedule definition**, **occurrence** và **durable mail request**.
- Với lịch định kỳ, thường nên **giữ các occurrence đã tạo**, chỉ tính lại tương lai.
- Với lịch một lần, nếu người dùng thực sự muốn đổi giờ, có thể dời **job `PENDING` chưa bắt đầu** mà vẫn giữ ID.
- Những job `RETRY_WAIT`, `CLAIMED`, `SUBMITTING`, `SUBMITTED` hoặc `UNKNOWN` có semantics khác nhau; không update hàng loạt bằng `sent=false`.
- `@Scheduled` hoặc `TaskScheduler` có thể kích hoạt dispatcher nhưng **không phải kho lưu pending jobs**.
- Quartz/JDBC JobStore giúp persist trigger, nhưng không tự quản lý đúng business mail requests.
- Atomic claim, optimistic version, unique occurrence key và audit bảo vệ trước race condition và duplicate.
- `scheduled_at`, `next_attempt_at` và `lease_until` phải có nghĩa riêng.
- Không thể rút lại một SMTP submission đã xảy ra chỉ bằng cách cancel task hay update database.
- Lịch mới cần tôn trọng timezone/DST, quiet hours, consent, deadline và tuổi thọ payload.
- Với số lượng job lớn, dùng rescheduling operation có thể resume, không khóa toàn bộ bảng quá lâu.

Thực hành đáng tin cậy trong Spring Framework Mail là để **database lưu yêu cầu gửi**, scheduler chỉ xác định khi nào phát sinh hoặc đánh thức công việc, và worker chỉ claim những yêu cầu thực sự đã đến hạn. Khi người dùng đổi lịch, hệ thống thay đổi **đúng phạm vi được phép**, giữ trạng thái của các yêu cầu đang chờ, ghi nhận những job không thể dời và có khả năng tiếp tục sau lỗi hoặc restart. Nhờ đó, thay đổi giờ gửi trở thành một thao tác nghiệp vụ có thể kiểm soát, không phải một hành động vô tình làm mất hoặc gửi trùng email.

### Tài liệu tham khảo

- **Spring Framework Reference — Task Execution and Scheduling:** `@Scheduled`, `TaskScheduler` và `Trigger`.
- **Spring Framework API — CronTrigger, CronExpression:** lập lịch và tính thời điểm kích hoạt tiếp theo.
- **Spring Framework Reference — Transaction Management:** `@Transactional` và transaction boundaries.
- **Spring Data JPA Reference:** optimistic/pessimistic locking và `@Version` khi dùng JPA.
- **Spring Framework Reference — Email:** `JavaMailSender` và transport submission.
- **Quartz Scheduler Documentation:** `CronTrigger`, `Scheduler.rescheduleJob`, JDBC JobStore, clustering, misfire instructions.
- **PostgreSQL Documentation:** `SELECT ... FOR UPDATE SKIP LOCKED`, conditional UPDATE, unique indexes và transaction isolation.
- **Java Platform — java.time:** `Instant`, `Clock`, `ZoneId` và `ZonedDateTime`.
- **RFC 5321 — Simple Mail Transfer Protocol:** submission outcomes và giới hạn bảo đảm khi gửi SMTP.
- **Tài liệu ESP đang sử dụng:** rate limits, delivery events, provider idempotency và khả năng truy vấn submission khi kết quả không chắc chắn.

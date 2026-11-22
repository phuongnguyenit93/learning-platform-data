# Kiểm thử retry và dead letter

Một ứng dụng gửi email bằng **Spring Framework Mail** không chỉ cần biết cách gọi `JavaMailSender.send(...)`. Trong môi trường thực tế, quá trình gửi có thể gặp SMTP timeout, server trả lỗi tạm thời, provider giới hạn lưu lượng, worker bị dừng giữa chừng hoặc database thất bại khi ghi kết quả. Với email quan trọng, ứng dụng cần **thử lại có kiểm soát (retry)**, và khi không thể tự khôi phục, phải đưa công việc vào trạng thái **dead letter** để theo dõi, điều tra hoặc xử lý thủ công.

Kiểm thử riêng một hàm tính số giây backoff chưa đủ để xác minh toàn bộ cơ chế hoạt động. **Kiểm thử tích hợp** cần nối các thành phần thật trong phạm vi kiểm soát: cấu hình Spring, repository, database/outbox, worker, transaction và bộ lập lịch retry. Lớp gửi SMTP có thể được thay bằng một **test double có thể điều khiển lỗi** để xác minh luồng database một cách quyết định; sau đó thêm một bộ test riêng với **SMTP server thử nghiệm** để xác minh giao thức và mapping lỗi transport.

Bài học này hướng dẫn cách thiết kế và kiểm thử **retry và dead letter** cho Spring Framework Mail, bao gồm mô hình trạng thái, Testcontainers/PostgreSQL, lỗi tạm thời và vĩnh viễn, `UNKNOWN` sau khi kết quả submission không rõ, giới hạn số lần thử, backoff, concurrency, crash recovery, dead-letter replay, kiểm tra side effects và giám sát vận hành.

## 1. Mục tiêu của kiểm thử tích hợp

Sau bài học, người học có thể kiểm thử rằng:

1. Một yêu cầu gửi email được lưu bền vững trong outbox.
2. Worker claim đúng job đang đến hạn và không gửi job chưa đến hạn.
3. Khi SMTP submission thất bại tạm thời, job chuyển sang `RETRY_WAIT` với thời điểm thử lại hợp lệ.
4. Khi đến hạn, worker dùng lại **message key** nhưng tạo **attempt ID** mới.
5. Khi một lần thử thành công, job chuyển sang `SMTP_ACCEPTED` và không bị gửi lại bởi lịch retry thông thường.
6. Khi lỗi vĩnh viễn, job chuyển sang `DEAD_LETTER` mà không lặp vô hạn.
7. Khi hết **retry budget**, job cũng chuyển sang dead letter, cùng lý do cuối và lịch sử attempt.
8. Khi outcome không rõ do timeout sau SMTP DATA, job được giữ ở `UNKNOWN` để reconciliation, không retry mù.
9. Hai worker cùng chạy không claim đồng thời một job khả dụng.
10. Việc restart ứng dụng không làm mất lịch retry hoặc bản ghi dead letter.
11. Khi lưu kết quả thất bại, ứng dụng không giả định có thể resend an toàn.
12. Có thể replay có kiểm soát từ dead letter mà không xóa lịch sử hoặc gây gửi trùng tùy tiện.

Đây là kiểm thử **quy trình gửi và lưu trạng thái**, không phải chứng minh thư đã đến Inbox. `SMTP_ACCEPTED` chỉ có nghĩa SMTP relay/provider đã chấp nhận submission theo contract tương ứng; delivery, spam filtering và việc người nhận đọc thư là các bước khác.

## 2. Bức tranh hệ thống cần kiểm thử

Một kiến trúc dùng transactional outbox:

```text
HTTP / business event
         |
         v
Business service + DB transaction
         |
         +--> Business data
         |
         +--> email_outbox(PENDING)
         |
         v
      COMMIT
         |
         v
Outbox worker / scheduler
         |
         +--> Claim due row + lease
         |
         +--> Create email_attempt
         |
         v
Mail submission gateway
         |
         +--> JavaMailSender / SMTP
         |
         +--> Provider API (nếu có)
         |
         v
Submission outcome
         |
         +--> SMTP_ACCEPTED
         |
         +--> RETRY_WAIT
         |
         +--> DEAD_LETTER
         |
         +--> UNKNOWN -> reconciliation
```

Không phải mọi sản phẩm cần triển khai hết các trạng thái này, nhưng **tên và ý nghĩa trạng thái phải rõ ràng**. Nếu chỉ có một cờ `sent=true/false`, test khó phân biệt giữa “chưa được thử”, “đang retry”, “hết lượt thử”, và “có thể đã được SMTP nhận nhưng ứng dụng không biết”.

### 2.1. Tách email logic, attempt và delivery

| Khái niệm | Ví dụ | Giữ nguyên qua retry? |
|---|---|---|
| Business event ID | `order-123-paid` | Thường có |
| Application message key | `msg-a817` | **Có**, nếu là cùng email logic |
| Attempt ID | `attempt-1`, `attempt-2` | **Không**; mỗi lần thử có ID riêng |
| RFC Message-ID | `<...@mail.example>` | Có thể khác khi tạo MIME mới |
| SMTP queue/provider message ID | `provider-id-...` | Gắn với submission do provider xác định |
| Delivery event ID | `evt-...` | Gắn với một webhook event |

**Retry** của cùng một email logic giữ application message key. Một yêu cầu gửi lại mới do người dùng chủ động tạo có thể là email logic mới. Phải phân biệt để không biến retry thành việc tạo hàng loạt outbox rows.

### 2.2. Dead letter là gì?

**Dead letter** là nơi lưu công việc mà quy trình xử lý tự động đã quyết định **không tiếp tục thử ngay bằng retry thông thường**. Trong triển khai queue có thể là **dead-letter queue (DLQ)**; trong triển khai outbox database có thể là trạng thái `DEAD_LETTER` kèm bảng chi tiết `mail_dead_letter`.

Nó không đồng nghĩa email chắc chắn không thể gửi trong mọi hoàn cảnh. Dead letter có thể phát sinh vì:
- lỗi dữ liệu/địa chỉ gửi không hợp lệ;
- SMTP server trả lỗi vĩnh viễn đã được phân loại;
- chính sách loại bỏ một recipient;
- đã dùng hết số attempt hoặc quá deadline;
- job không thể render template và cần sửa input;
- người vận hành quyết định dừng để điều tra.

Một dead-letter entry nên cho biết **message key, nguyên nhân an toàn để ghi log, lần lỗi cuối, số attempt và thời gian**, thay vì chỉ có một chuỗi “Failed”.

## 3. Mô hình trạng thái cần xác nhận bằng test

```text
PENDING
   |
   v
SENDING  <-----------------------+
   |                            |
   +--> SMTP_ACCEPTED           |
   |                            |
   +--> RETRY_WAIT --------------+
   |
   +--> DEAD_LETTER
   |
   +--> UNKNOWN
          |
          v
     Reconciliation / operator decision
          |
          +--> SMTP_ACCEPTED
          +--> RETRY_WAIT (nếu an toàn)
          +--> DEAD_LETTER / manual review
```

| Trạng thái | Ý nghĩa | Hành vi worker thường gặp |
|---|---|---|
| `PENDING` | Chưa thử gửi | Có thể claim khi đến hạn |
| `SENDING` | Đã claim và đang thực hiện attempt | Chỉ worker sở hữu lease được cập nhật |
| `RETRY_WAIT` | Lỗi có thể retry; chờ `next_attempt_at` | Không claim trước hạn |
| `SMTP_ACCEPTED` | Submission được upstream chấp nhận | Không retry submission của job này |
| `DEAD_LETTER` | Ngừng retry tự động, chờ chính sách khác | Không được worker thường claim |
| `UNKNOWN` | Không thể xác định chắc chắn upstream đã nhận chưa | Reconcile, không resend vô điều kiện |

Có thể thêm `DELIVERED`, `BOUNCED` hoặc `COMPLAINED` khi hệ thống nhận webhook của provider. Chúng thuộc **delivery lifecycle**, cần phân biệt với **submission retry** đang được kiểm thử.

### 3.1. Những bất biến quan trọng

Integration tests nên bảo vệ những bất biến:

- Một message key biểu diễn một email logic.
- Mỗi attempt của một message key có số thứ tự duy nhất.
- Job `SMTP_ACCEPTED` hoặc `DEAD_LETTER` không quay lại `SENDING` vì scheduler chạy lại.
- `attempt_count` chỉ tăng khi một attempt thực sự được bắt đầu/claim theo contract.
- `RETRY_WAIT` luôn có `next_attempt_at` hợp lệ và chưa được claim sớm.
- Khi đạt max attempts, không có attempt vượt quá ngân sách.
- Dead letter được ghi bền vững, cùng transaction với thay đổi trạng thái.
- Không có hai worker hiện hành sở hữu cùng lease token.
- Một failure không được làm mất message key và lịch sử attempts.
- Một outcome `UNKNOWN` không bị biến thành `FAILED` chắc chắn nếu không có bằng chứng.

Test không chỉ assert “status cuối đúng”; nên assert cả **số lần gọi gateway, attempt history, lịch retry và dead-letter record**.

## 4. Phân loại lỗi trước khi quyết định retry

Không nên dùng một câu `catch (Exception e) { retry(); }` cho mọi lỗi.

| Nhóm lỗi | Ví dụ | Quyết định thông thường |
|---|---|---|
| **Transient / retryable** | SMTP 421/451 tại giai đoạn chưa tiếp nhận message, lỗi network được xác định an toàn | Chờ backoff, thử lại trong ngân sách |
| **Permanent / non-retryable** | Địa chỉ không hợp lệ, dữ liệu template sai không thể tự sửa, lỗi relay từ chối xác định | Chuyển dead letter hoặc workflow xử lý ngay |
| **Configuration/auth** | Sai SMTP credentials, TLS hostname/certificate sai | Không retry dồn dập; cảnh báo/sửa cấu hình |
| **Unknown outcome** | Mất kết nối sau khi gửi DATA, không rõ relay đã chấp nhận chưa | `UNKNOWN` và reconciliation |
| **Provider deferred delivery** | Provider đã nhận submission, server đích tạm hoãn | Để provider xử lý delivery retry, không resubmit ngay |

SMTP `4xx` thường chỉ lỗi tạm thời, `5xx` thường chỉ lỗi vĩnh viễn, nhưng cần xét **command phase**, enhanced status code, reply text và chính sách provider. Một timeout không có nghĩa chắc chắn chưa được chấp nhận.

### 4.1. Không đưa mọi exception của Spring vào một nhóm

Spring Mail có thể ném `MailSendException`, `MailAuthenticationException`, `MailPreparationException` hoặc exception khác, trong đó nested cause có thể là `MessagingException` hay lỗi socket/TLS.

Một classifier trong production cần trả về một loại kết quả an toàn để worker quyết định. Unit test của classifier kiểm tra logic phân loại; **integration test** kiểm tra quyết định đó được ghi bền vững đúng vào outbox và dead-letter storage.

### 4.2. Tách phân loại lỗi khỏi worker

Có thể thiết kế:

```java
public enum FailureKind {
    TRANSIENT,
    PERMANENT,
    UNKNOWN
}

public final class SubmissionFailure
        extends RuntimeException {

    private final FailureKind kind;
    private final String safeCode;

    public SubmissionFailure(
            FailureKind kind,
            String safeCode) {
        super(safeCode);
        this.kind = kind;
        this.safeCode = safeCode;
    }

    public FailureKind kind() {
        return kind;
    }

    public String safeCode() {
        return safeCode;
    }
}
```

`safeCode` là mã lỗi đã chuẩn hóa (ví dụ `SMTP_TEMPORARY_451`), **không phải toàn bộ `ex.getMessage()`** có thể chứa thông tin SMTP/recipient nhạy cảm.

Mô hình này cho phép các test tạo lỗi giả lập có loại rõ ràng, không cần phụ thuộc cách một SMTP library tạo stack trace. Sau đó cần có test riêng để đảm bảo adapter map lỗi SMTP thật vào đúng `FailureKind`.

## 5. Chọn hai lớp kiểm thử tích hợp bổ sung nhau

Một bộ test có độ tin cậy cao nên chia:

### Lớp A — Workflow integration với database thật và submission gateway điều khiển được

- Khởi động Spring application context có worker/repository/transaction thực tế.
- Dùng PostgreSQL trong Testcontainers hoặc database cùng loại production.
- Thay **rìa SMTP** bằng test gateway có kịch bản `ACCEPTED`, `TRANSIENT`, `PERMANENT`, `UNKNOWN`.
- Kiểm tra status, attempts, lease, nextAttemptAt và dead letter bằng SQL.
- Điều khiển `Clock` để test lịch retry mà không `sleep`.

Lớp này chứng minh **workflow Spring + persistence + retry/dead letter** vận hành cùng nhau. Nó **không** tự chứng minh SMTP transport thật phân loại response 451 đúng.

### Lớp B — SMTP transport integration với server thử nghiệm

- Dùng một SMTP server test (ví dụ GreenMail, Mailpit hoặc server hỗ trợ cấu hình responses) được phép dùng trong CI.
- Cấu hình `JavaMailSenderImpl` trỏ tới endpoint test.
- Test kết nối, MIME submission và response hợp lệ.
- Với lỗi 4xx/5xx, dùng **fault-injecting SMTP server** hoặc một harness có khả năng trả reply tại đúng giai đoạn.
- Test adapter chuyển response/exceptions thành `FailureKind` tương ứng.

Lớp này chứng minh **biên mạng/SMTP** hoạt động, nhưng không nhất thiết cần khởi động toàn bộ hệ thống queue hoặc retry worker.

### 5.1. Vì sao không dùng SMTP provider thật cho mọi test?

Provider thật có:
- quota, chính sách chống spam, rate limit;
- latency và sự cố khó tái hiện;
- nguy cơ phát email ra ngoài;
- credential/secret;
- event delivery bất đồng bộ không dự đoán được;
- các lỗi 4xx/5xx không dễ kích hoạt theo ý muốn.

Dùng provider thật cho một số smoke/E2E tests được kiểm soát, không làm nó thành dependency của toàn bộ bộ kiểm thử tích hợp.

## 6. Mô hình dữ liệu PostgreSQL để kiểm thử

Một schema minh họa:

```sql
CREATE TABLE mail_outbox (
    message_key UUID PRIMARY KEY,
    recipient VARCHAR(320) NOT NULL,
    subject TEXT NOT NULL,
    plain_text TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_error_code VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_mail_attempt_count
        CHECK (attempt_count >= 0),
    CONSTRAINT chk_mail_outbox_status
        CHECK (status IN (
            'PENDING', 'SENDING', 'RETRY_WAIT',
            'SMTP_ACCEPTED', 'DEAD_LETTER', 'UNKNOWN'
        ))
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE TABLE mail_send_attempt (
    attempt_id UUID PRIMARY KEY,
    message_key UUID NOT NULL
        REFERENCES mail_outbox(message_key),
    attempt_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(32) NOT NULL,
    error_code VARCHAR(120),
    provider_message_id VARCHAR(255),
    CONSTRAINT uq_mail_attempt_number
        UNIQUE (message_key, attempt_number)
);

CREATE TABLE mail_dead_letter (
    message_key UUID PRIMARY KEY
        REFERENCES mail_outbox(message_key),
    failed_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL,
    final_reason VARCHAR(120) NOT NULL,
    operator_note TEXT
);
```

Schema này chỉ nhằm minh họa một design có thể dùng để kiểm thử:
- `mail_outbox` lưu email logic và trạng thái hiện tại.
- `mail_send_attempt` lưu từng lần thử.
- `mail_dead_letter` lưu lý do dừng retry tự động.
- Partial index giúp worker tìm job đến hạn.
- Unique constraint giúp không có hai attempt cùng số thứ tự cho một message key.

Trong production, nội dung email và recipient là dữ liệu có thể nhạy cảm: cân nhắc mã hóa, hạn chế quyền truy cập, retention và chỉ lưu template reference/snapshot khi phù hợp. Test fixtures phải dùng địa chỉ giả và nội dung không nhạy cảm.

### 6.1. Tạo job trong transaction nghiệp vụ

Outbox item ban đầu:

```sql
INSERT INTO mail_outbox (
    message_key, recipient, subject, plain_text,
    status, attempt_count, next_attempt_at,
    created_at, updated_at
)
VALUES (
    :messageKey, :recipient, :subject, :plainText,
    'PENDING', 0, :now, :now, :now
);
```

Nếu email gắn với sự kiện nghiệp vụ có tính duy nhất, cần constraint nghiệp vụ riêng như `(business_event_id, notification_type)` để tránh hai yêu cầu logic trùng. `message_key` là identity của email, không tự đảm bảo idempotency của mọi API gọi vào.

### 6.2. Không xóa row khi hết retry

Khi job dead letter, giữ outbox row và attempts để:
- điều tra các lần thử;
- đối chiếu provider logs;
- xác định lý do cuối cùng;
- phục hồi theo quy trình được duyệt;
- thống kê số công việc không xử lý được.

Xóa job rồi chỉ giữ một dòng error log có thể làm mất thông tin cần cho support và audit.

## 7. Atomic claim: hai worker không được gửi cùng job

Một worker phải claim job đang đến hạn **theo cách atomic**. Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED` trong một transaction ngắn:

```sql
WITH next_job AS (
    SELECT message_key
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox o
SET status = 'SENDING',
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    attempt_count = attempt_count + 1,
    updated_at = :now
FROM next_job n
WHERE o.message_key = n.message_key
RETURNING
    o.message_key,
    o.recipient,
    o.subject,
    o.plain_text,
    o.attempt_count,
    o.lease_token;
```

Thao tác claim phải được commit **trước khi gọi SMTP**. Không giữ transaction database mở suốt một network call có thể kéo dài hoặc timeout.

Trong cùng transaction claim, nên tạo `mail_send_attempt` ứng với attempt mới. Nếu ghi attempt thất bại, cả claim nên rollback để không có job `SENDING` nhưng thiếu attempt history.

### 7.1. Lease token và fencing

Khi worker ghi kết quả, kiểm tra lease token:

```sql
UPDATE mail_outbox
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

Nếu số dòng cập nhật bằng 0, có thể worker đã mất quyền sở hữu job. Fencing bảo vệ **database state**, nhưng **không thu hồi được SMTP submission** mà worker cũ đã gửi. Vì vậy, test concurrency phải nhìn cả trạng thái database và số lần gateway được gọi.

### 7.2. Lease hết hạn không chứng minh SMTP chưa gửi

Một worker có thể gửi thành công nhưng bị crash trước khi ghi `SMTP_ACCEPTED`. Nếu chỉ vì lease hết hạn mà tự chuyển job về `PENDING` rồi gửi ngay, có nguy cơ gửi trùng.

Với job `SENDING` hết lease, thiết kế bảo thủ:
- ghi nhận attempt là nghi vấn;
- chuyển `UNKNOWN` hoặc phân loại theo bằng chứng;
- đối soát với SMTP/provider;
- chỉ retry khi có quyết định theo chính sách rủi ro.

Một job được claim rồi process crash **trước khi bắt đầu gửi** có thể được xử lý khác nếu hệ thống có bằng chứng bền vững, nhưng không nên suy ra từ lease expiry đơn thuần.

## 8. Retry policy: quyết định phải quan sát và kiểm thử được

Thiết kế policy nhận loại lỗi, số attempt và thời gian, trả về quyết định rõ ràng:

```java
import java.time.Duration;
import java.time.Instant;

public enum NextState {
    RETRY_WAIT,
    DEAD_LETTER,
    UNKNOWN
}

public record RetryDecision(
    NextState state,
    Instant nextAttemptAt,
    String reasonCode
) {}

public final class MailRetryPolicy {

    private final int maxAttempts;

    public MailRetryPolicy(int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be positive"
            );
        }
        this.maxAttempts = maxAttempts;
    }

    public RetryDecision decide(
            FailureKind kind,
            int attemptNumber,
            Instant now,
            String safeCode) {

        if (kind == FailureKind.UNKNOWN) {
            return new RetryDecision(
                NextState.UNKNOWN, null, safeCode
            );
        }

        if (kind == FailureKind.PERMANENT
                || attemptNumber >= maxAttempts) {
            return new RetryDecision(
                NextState.DEAD_LETTER, null, safeCode
            );
        }

        long waitSeconds =
            2L << Math.min(attemptNumber - 1, 12);

        return new RetryDecision(
            NextState.RETRY_WAIT,
            now.plus(Duration.ofSeconds(waitSeconds)),
            safeCode
        );
    }
}
```

Với `maxAttempts=3` và lỗi transient liên tục:
- Attempt 1: `RETRY_WAIT`, chờ 2 giây.
- Attempt 2: `RETRY_WAIT`, chờ 4 giây.
- Attempt 3: `DEAD_LETTER`, không có attempt 4.

Đây là backoff **deterministic** phục vụ minh họa. Production nên cân nhắc max delay, jitter, rate limit, deadline và `Retry-After` khi provider HTTP API có hỗ trợ. Trong integration test, nên inject clock và nguồn jitter hoặc dùng test policy dự đoán được để tránh kết quả ngẫu nhiên.

### 8.1. Đếm attempt như thế nào?

Trong ví dụ, `attempt_count` tăng khi claim tạo một attempt mới. Không tăng lần nữa ở bước xử lý lỗi. Nếu test dùng cách đếm khác (ví dụ `retry_count` là số lần retry sau lần đầu), kết quả max-attempts sẽ lệch một đơn vị.

Hãy ghi rõ:
- `attempt_count=0`: chưa thử.
- `attempt_count=1`: đã bắt đầu lần gửi đầu.
- `attempt_count=3`: đã dùng đủ ba attempt.

**Đừng để một lỗi off-by-one khiến policy cho phép attempt 4 khi maxAttempts=3.**

### 8.2. Deadline và retry budget

Ngoài số lần thử, có thể có thời hạn:
- email xác minh không còn hữu ích khi token hết hạn;
- cảnh báo khẩn cấp có deadline ngắn;
- hóa đơn có thể chờ lâu hơn;
- provider có quota hoặc rate limit riêng.

Integration test nên có ca:
- chưa hết số lần nhưng đã vượt deadline;
- đến hạn retry nhưng recipient bị suppress;
- worker dừng khi tổng retry budget đã cạn;
- không lập lịch một attempt vào thời điểm sau khi link hết hiệu lực.

## 9. Tách gateway gửi để test workflow mà không dùng SMTP provider thật

Một lớp abstraction mỏng:

```java
import java.util.UUID;

public record OutboundMail(
    UUID messageKey,
    String recipient,
    String subject,
    String plainText
) {}

public interface MailSubmissionGateway {
    void submit(OutboundMail mail);
}
```

Production adapter dùng Spring Mail:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringMailSubmissionGateway
        implements MailSubmissionGateway {

    private final JavaMailSender sender;
    private final MailFailureClassifier classifier;

    public SpringMailSubmissionGateway(
            JavaMailSender sender,
            MailFailureClassifier classifier) {
        this.sender = sender;
        this.classifier = classifier;
    }

    @Override
    public void submit(OutboundMail mail) {
        try {
            MimeMessage mime = sender.createMimeMessage();
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, false, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), false);

            mime.setHeader(
                "X-Application-Message-Key",
                mail.messageKey().toString()
            );

            sender.send(mime);
        } catch (MailException | MessagingException ex) {
            throw classifier.classify(ex);
        }
    }
}
```

`MailFailureClassifier` là thành phần do ứng dụng định nghĩa: nó map Spring/Jakarta Mail exceptions thành `SubmissionFailure` với `FailureKind` phù hợp. Không gom mọi `MailException` thành transient; timeout sau DATA có thể là `UNKNOWN`.

**Điểm test-double:** ở workflow integration, thay `MailSubmissionGateway` bằng phiên bản scripted để điều khiển kết quả. Repository, transaction, retry policy và worker vẫn chạy thật.

### 9.1. Không mock repository khi mục tiêu là integration persistence

Nếu cả `MailSubmissionGateway` lẫn repository đều là mock, test chỉ chứng minh chuỗi lời gọi trong code, chưa chứng minh:
- transaction commit;
- unique constraint;
- atomic claim;
- dead-letter row tồn tại;
- retry due-time query;
- crash/restart persistence.

Với test tích hợp retry/dead letter, repository và database nên là thành phần thật. Chỉ thay **biên ngoài** mà bạn cần điều khiển để tạo kết quả xác định.

## 10. Worker orchestration và ranh giới transaction

Một worker có thể làm theo các bước:

1. `claimDue(now)`: transaction ngắn, đổi job sang `SENDING`, cấp lease, tăng attempt count và tạo attempt.
2. `gateway.submit(...)`: network I/O **ngoài transaction claim**.
3. Khi thành công: transaction ngắn, kết thúc attempt và đổi job sang `SMTP_ACCEPTED`.
4. Khi thất bại: áp dụng retry policy rồi trong transaction lưu outcome + `RETRY_WAIT`, `DEAD_LETTER` hoặc `UNKNOWN`.
5. Scheduler quét jobs đến hạn hoặc consumer nhận tín hiệu từ queue.

Ví dụ orchestration:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

public final class MailOutboxProcessor {

    private final MailOutboxRepository repository;
    private final MailSubmissionGateway gateway;
    private final MailRetryPolicy retryPolicy;
    private final Clock clock;

    public MailOutboxProcessor(
            MailOutboxRepository repository,
            MailSubmissionGateway gateway,
            MailRetryPolicy retryPolicy,
            Clock clock) {
        this.repository = repository;
        this.gateway = gateway;
        this.retryPolicy = retryPolicy;
        this.clock = clock;
    }

    public boolean processOne() {
        Instant now = clock.instant();

        Optional<ClaimedMail> candidate =
            repository.claimDue(now);

        if (candidate.isEmpty()) {
            return false;
        }

        ClaimedMail job = candidate.get();

        try {
            gateway.submit(job.mail());
            repository.markAccepted(
                job.messageKey(),
                job.leaseToken(),
                job.attemptId(),
                clock.instant()
            );
        } catch (SubmissionFailure ex) {
            RetryDecision decision = retryPolicy.decide(
                ex.kind(),
                job.attemptNumber(),
                clock.instant(),
                ex.safeCode()
            );

            repository.recordFailure(
                job.messageKey(),
                job.leaseToken(),
                job.attemptId(),
                decision,
                clock.instant()
            );
        }

        return true;
    }
}
```

Các kiểu `MailOutboxRepository` và `ClaimedMail` là contract do ứng dụng định nghĩa; phương thức repository phải được triển khai với SQL/transaction tương ứng. Ví dụ minh họa **cách chia trách nhiệm**, không tuyên bố là toàn bộ production implementation.

### 10.1. Contract của repository

```java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface MailOutboxRepository {

    Optional<ClaimedMail> claimDue(Instant now);

    void markAccepted(
        UUID messageKey,
        UUID leaseToken,
        UUID attemptId,
        Instant now
    );

    void recordFailure(
        UUID messageKey,
        UUID leaseToken,
        UUID attemptId,
        RetryDecision decision,
        Instant now
    );
}

public record ClaimedMail(
    UUID messageKey,
    UUID leaseToken,
    UUID attemptId,
    int attemptNumber,
    OutboundMail mail
) {}
```

Yêu cầu cho implementation:
- `claimDue` chọn job bằng query atomic, transaction ngắn.
- Tạo `attemptId` và attempt history trong cùng transaction claim.
- `markAccepted` cập nhật attempt và outbox **cùng transaction**, yêu cầu đúng lease token.
- `recordFailure` cập nhật attempt và job cùng transaction; với dead letter ghi thêm bảng `mail_dead_letter` trong transaction đó.
- Việc cập nhật không tìm thấy lease hợp lệ phải báo xung đột, không im lặng ghi đè trạng thái.
- Không để exception của database bị bắt bởi nhánh `SubmissionFailure` vì đó là lỗi hạ tầng ghi state, cần xử lý riêng.

### 10.2. Dead-letter commit phải atomic

Ví dụ ý tưởng xử lý decision `DEAD_LETTER`:

```text
BEGIN
  verify row status=SENDING AND lease_token=current
  UPDATE mail_send_attempt
     SET outcome='FAILED', error_code=...
  UPDATE mail_outbox
     SET status='DEAD_LETTER', lease_token=NULL,
         last_error_code=..., updated_at=...
  INSERT INTO mail_dead_letter(...)
COMMIT
```

Nếu `INSERT mail_dead_letter` thất bại, transaction phải rollback để không có trạng thái outbox nói dead letter nhưng thiếu chi tiết.

Với broker DLQ ngoài database, có thêm bài toán atomicity giữa database và broker. Không nên coi `publish to DLQ` rồi `ack source message` là atomic nếu không có cơ chế transaction/outbox/broker guarantee phù hợp. Integration test cần bao phủ trường hợp process crash giữa các bước.

## 11. Môi trường test với PostgreSQL Testcontainers

Mục đích là chạy với database có hành vi transaction/locking gần production, đặc biệt khi dùng `FOR UPDATE SKIP LOCKED` và partial indexes đặc thù PostgreSQL.

Ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Các phiên bản cần thống nhất với dependency management của dự án. Ví dụ dùng Testcontainers khi Docker/runtime container có sẵn trong CI. Không cần một SMTP provider thật cho workflow tests.

### 11.1. Khởi tạo container và datasource

```java
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class MailOutboxRetryIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }

    @Autowired JdbcTemplate jdbc;
}
```

Trong dự án thật, class test sẽ có thêm các bean `MailOutboxProcessor`, `MailOutboxRepository`, retry policy và test gateway. Schema nên được tạo qua migration chính thức như Flyway/Liquibase hoặc script kiểm soát; không hardcode tạo bảng trong mọi test method.

### 11.2. Không dùng @Transactional bao toàn bộ test một cách vô tình

Nếu một test method có `@Transactional` và transaction cuối test bị rollback, nó có thể **không phản ánh transaction boundaries thực** của worker. Nếu claim/send/outcome được gọi trong transaction của test mà chưa commit, worker thread hoặc connection khác có thể không nhìn thấy job.

Với integration test cần kiểm tra durability:
- để application service tự quản lý transaction;
- tạo test fixture và commit trước khi chạy worker;
- query trạng thái từ connection/transaction độc lập khi cần;
- làm sạch dữ liệu giữa các test;
- đừng dùng rollback của test để giả lập việc app commit.

### 11.3. Chỉ định schema test rõ ràng

Ví dụ:
- Dùng migration production trong test profile, nếu migration đủ an toàn.
- Hoặc migration test tương đương với schema thật.
- Tránh dùng H2 để kết luận PostgreSQL `SKIP LOCKED` hoạt động chính xác.
- Nếu database production khác PostgreSQL, dùng hệ tương ứng thay vì giả định tính chất khóa giống nhau.

## 12. Test gateway có kịch bản lỗi

Một test double đơn giản có thể trả thành công hoặc ném `SubmissionFailure` theo thứ tự. Nó **không gửi email ra ngoài**.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;

public final class ScriptedMailGateway
        implements MailSubmissionGateway {

    public enum Outcome {
        ACCEPTED,
        TRANSIENT,
        PERMANENT,
        UNKNOWN
    }

    private final Deque<Outcome> script = new ArrayDeque<>();
    private final List<OutboundMail> submissions =
        new ArrayList<>();

    public synchronized void plan(Outcome... outcomes) {
        script.clear();
        submissions.clear();
        script.addAll(Arrays.asList(outcomes));
    }

    @Override
    public synchronized void submit(OutboundMail mail) {
        submissions.add(mail);

        if (script.isEmpty()) {
            throw new AssertionError(
                "No scripted SMTP outcome remaining"
            );
        }

        Outcome next = script.removeFirst();

        switch (next) {
            case ACCEPTED -> {
                return;
            }
            case TRANSIENT -> throw new SubmissionFailure(
                FailureKind.TRANSIENT, "SMTP_TEMP_451"
            );
            case PERMANENT -> throw new SubmissionFailure(
                FailureKind.PERMANENT, "SMTP_PERM_550"
            );
            case UNKNOWN -> throw new SubmissionFailure(
                FailureKind.UNKNOWN, "SMTP_RESULT_UNKNOWN"
            );
        }
    }

    public synchronized int invocationCount() {
        return submissions.size();
    }

    public synchronized List<OutboundMail> submitted() {
        return List.copyOf(submissions);
    }
}
```

Ở production, không có một gateway tự trả outcome như vậy. Nó là **điểm kiểm soát failure injection của test**. Việc `UNKNOWN` được giả lập không có nghĩa mọi timeout thật đều là unknown; classifier riêng phải được kiểm thử theo giao thức.

### 12.1. Vì sao fail khi hết script?

Nếu gateway mặc định thành công khi script trống, một test lỗi có thể lặng lẽ gửi thêm attempt ngoài dự kiến mà vẫn pass. Việc ném `AssertionError` khi hết kịch bản giúp phát hiện một số lời gọi thừa.

Tuy nhiên, nếu chạy test song song hoặc nhiều worker dùng chung gateway, cần thiết kế kịch bản theo message key/thread an toàn. Tránh một shared deque global làm kết quả flaky.

### 12.2. Bean test riêng và @Primary

Với Spring context:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
public class MailGatewayTestConfiguration {

    @Bean
    @Primary
    ScriptedMailGateway scriptedMailGateway() {
        return new ScriptedMailGateway();
    }
}
```

`ScriptedMailGateway` implements `MailSubmissionGateway`, nên bean được đánh dấu `@Primary` có thể được inject vào processor thay cho production adapter. Import test configuration bằng `@Import(MailGatewayTestConfiguration.class)` nếu cần.

Nếu dự án có bean wiring khác, hãy kiểm tra context chỉ có một gateway được chọn cho worker; tránh để sender thật hoạt động trong background scheduler của test.

## 13. Điều khiển thời gian để test retry không dùng sleep

Một test retry không nên làm:

```java
Thread.sleep(5000);
worker.processOne();
```

Cách đó:
- làm CI chậm;
- dễ flaky theo tải CPU;
- khó mô phỏng nhiều attempt;
- có thể đụng timing của scheduler thật;
- không kiểm tra rõ `next_attempt_at`.

Thay bằng **clock có thể điều khiển**:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableTestClock extends Clock {

    private final AtomicReference<Instant> now;
    private final ZoneId zone;

    public MutableTestClock(Instant initial) {
        this(
            new AtomicReference<>(initial),
            ZoneOffset.UTC
        );
    }

    private MutableTestClock(
            AtomicReference<Instant> now,
            ZoneId zone) {
        this.now = now;
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableTestClock(now, newZone);
    }

    @Override
    public Instant instant() {
        return now.get();
    }

    public void advance(Duration duration) {
        now.updateAndGet(t -> t.plus(duration));
    }

    public void reset(Instant instant) {
        now.set(instant);
    }
}
```

Test có thể gọi `clock.advance(Duration.ofSeconds(2))` để mô phỏng “đã tới hạn” mà không chờ 2 giây thật.

### 13.1. Cung cấp Clock bean

Trong cấu hình test:

```java
@Bean
MutableTestClock mutableTestClock() {
    return new MutableTestClock(
        Instant.parse("2026-11-12T08:00:00Z")
    );
}

@Bean
@Primary
Clock testClock(MutableTestClock clock) {
    return clock;
}
```

Nếu Spring app có `Clock` bean thật, cần đảm bảo test clock được inject đúng vào worker/retry policy. Không dùng `Instant.now()` rải rác trong repository và worker nếu muốn test deterministic.

### 13.2. Disable scheduler khi test gọi worker trực tiếp

Trong integration tests, nên gọi `processor.processOne()` theo ý định của test. Nếu `@Scheduled` cũng chạy, nó có thể claim job bất ngờ, khiến assertion không ổn định.

Tách phần schedule trigger khỏi processor, rồi tắt trigger trong test profile (theo property có điều kiện mà ứng dụng tự định nghĩa). Đừng chỉ giả định một property chung của Spring luôn vô hiệu hóa mọi `@Scheduled` do ứng dụng đã khai báo.

## 14. Kịch bản 1 — Lỗi transient rồi gửi thành công

Ví dụ max attempts = 3:

```text
T0: PENDING
 |
 +-- processOne()
 |   -> attempt 1: TRANSIENT
 |   -> RETRY_WAIT; next=T0+2s
 |
 +-- processOne() ngay: không claim
 |
 +-- advance clock 2s
 |   -> attempt 2: TRANSIENT
 |   -> RETRY_WAIT; next=T0+2s+4s
 |
 +-- advance clock 4s
     -> attempt 3: ACCEPTED
     -> SMTP_ACCEPTED
```

Các assertion cần có:
- Gateway được gọi đúng 3 lần.
- Cả 3 submissions có **cùng message key**.
- Attempt IDs/số attempt khác nhau.
- Trạng thái sau hai lỗi là `RETRY_WAIT`.
- `next_attempt_at` đúng theo policy.
- Không có attempt sớm.
- Trạng thái cuối là `SMTP_ACCEPTED`.
- Không có dead-letter entry.
- Scheduler gọi thêm sau thành công không gửi lại.

### 14.1. Test theo hợp đồng repository thực

Trong một project đã có `MailOutboxRepository`, có thể viết:

```java
@Test
void transientFailuresAreRetriedThenAccepted() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.ACCEPTED
    );

    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("RETRY_WAIT");
    assertThat(queries.attemptCount(key))
        .isEqualTo(1);

    // Chưa tới hạn thì không claim/gửi.
    assertThat(processor.processOne()).isFalse();
    assertThat(gateway.invocationCount()).isEqualTo(1);

    clock.advance(Duration.ofSeconds(2));
    assertThat(processor.processOne()).isTrue();
    assertThat(queries.attemptCount(key))
        .isEqualTo(2);

    clock.advance(Duration.ofSeconds(4));
    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("SMTP_ACCEPTED");
    assertThat(queries.attemptCount(key))
        .isEqualTo(3);
    assertThat(queries.deadLetterCount(key))
        .isZero();

    assertThat(gateway.invocationCount())
        .isEqualTo(3);

    assertThat(gateway.submitted())
        .extracting(OutboundMail::messageKey)
        .containsOnly(key);

    assertThat(processor.processOne()).isFalse();
}
```

`fixtures` và `queries` là **test fixture/query helpers do dự án định nghĩa**, không phải API của Spring. Chúng phải ghi/đọc từ PostgreSQL thật. Code minh họa cấu trúc test; cần ghép với repository implementation và Spring wiring của ứng dụng.

### 14.2. Kiểm tra thời điểm retry bằng SQL

Đừng chỉ kiểm tra status:

```sql
SELECT status, attempt_count, next_attempt_at
FROM mail_outbox
WHERE message_key = :messageKey;
```

Test nên so sánh `next_attempt_at` với clock và delay policy. Nếu không, implementation có thể đặt `RETRY_WAIT` nhưng lịch retry ở quá khứ khiến worker thử lại liên tục.

## 15. Kịch bản 2 — Hết max attempts thì dead letter

Giả sử max attempts = 3 và SMTP luôn trả lỗi transient:

```text
Attempt 1: TRANSIENT -> RETRY_WAIT
Attempt 2: TRANSIENT -> RETRY_WAIT
Attempt 3: TRANSIENT -> DEAD_LETTER
Attempt 4: KHÔNG ĐƯỢC XẢY RA
```

Các assertion:
- `attempt_count=3`.
- Ba attempt rows tồn tại.
- Outbox status `DEAD_LETTER`.
- Dead-letter record đúng message key, final reason và failed_at.
- `next_attempt_at` không còn khiến worker claim job.
- Không phát sinh attempt thứ 4 dù gọi worker lặp lại.
- Không xóa message hoặc lịch sử attempts.

Ví dụ test:

```java
@Test
void maxAttemptsMovesJobToDeadLetter() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.TRANSIENT
    );

    assertThat(processor.processOne()).isTrue();

    clock.advance(Duration.ofSeconds(2));
    assertThat(processor.processOne()).isTrue();

    clock.advance(Duration.ofSeconds(4));
    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("DEAD_LETTER");
    assertThat(queries.attemptCount(key))
        .isEqualTo(3);
    assertThat(queries.deadLetterCount(key))
        .isEqualTo(1);
    assertThat(queries.finalDeadLetterReason(key))
        .isEqualTo("SMTP_TEMP_451");

    assertThat(gateway.invocationCount()).isEqualTo(3);
    assertThat(processor.processOne()).isFalse();
}
```

**Đừng chỉ assert dead-letter record tồn tại**: nếu job vẫn ở `RETRY_WAIT`, scheduler có thể gửi thêm lần thứ tư dù bảng DLQ có row.

### 15.1. Hết deadline trước max attempts

Có thể test một trường hợp khác:
- maxAttempts = 5;
- email xác minh hết hiệu lực sau 10 phút;
- mới dùng 2 attempts nhưng retry tiếp theo sẽ đến sau deadline.

Policy nên chuyển job theo quy tắc nghiệp vụ (ví dụ `DEAD_LETTER` với `EXPIRED_NOTIFICATION`) thay vì gửi link không còn dùng được. Đừng mặc định số attempt là giới hạn duy nhất.

## 16. Kịch bản 3 — Lỗi vĩnh viễn chuyển dead letter ngay

Một lỗi permanent được xác định rõ không cần chạy đủ max attempts.

```text
PENDING
   |
   v
Attempt 1: PERMANENT
   |
   v
DEAD_LETTER
```

Ví dụ:

```java
@Test
void permanentFailureGoesToDeadLetterImmediately() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.PERMANENT
    );

    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("DEAD_LETTER");
    assertThat(queries.attemptCount(key))
        .isEqualTo(1);
    assertThat(queries.deadLetterCount(key))
        .isEqualTo(1);

    assertThat(gateway.invocationCount())
        .isEqualTo(1);

    assertThat(processor.processOne()).isFalse();
}
```

Lưu ý: không nên mặc định mọi `MailSendException` đều permanent. Bài test này giả lập **một lỗi đã được classifier xác nhận permanent**; kiểm tra classifier với SMTP thật là một bài test riêng.

### 16.1. Địa chỉ không hợp lệ trước SMTP

Nếu lỗi validation xảy ra **trước khi worker tạo attempt gửi**, mô hình trạng thái có thể khác:
- nghiệp vụ từ chối tạo outbox row;
- hoặc outbox được tạo nhưng dead letter với reason `INVALID_RECIPIENT`;
- attempt_count có thể bằng 0 nếu chưa hề thử SMTP.

Test phải theo contract đã định nghĩa; đừng tăng attempt_count tùy tiện chỉ để các trường hợp trông giống nhau.

## 17. Kịch bản 4 — UNKNOWN không được retry mù

Trường hợp khó:

```text
Worker                     SMTP relay
  |---- MIME DATA ----------->|
  |---- end-of-DATA --------->|
  |                           | accepted/enqueued
  |<--- connection lost ------X
  |
  +-- Timeout / IOException
  |
  +-- Không biết relay đã nhận thư chưa
```

Nếu app retry ngay, có thể gửi hai email. Khi outcome không rõ, policy nên lưu `UNKNOWN`, chờ reconciliation hoặc quyết định nghiệp vụ có ghi nhận rủi ro duplicate.

Test:

```java
@Test
void unknownSubmissionDoesNotAutoRetry() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.UNKNOWN
    );

    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("UNKNOWN");
    assertThat(queries.attemptCount(key))
        .isEqualTo(1);
    assertThat(queries.deadLetterCount(key))
        .isZero();

    clock.advance(Duration.ofDays(1));

    assertThat(processor.processOne()).isFalse();
    assertThat(gateway.invocationCount())
        .isEqualTo(1);
}
```

Không nhất thiết đưa `UNKNOWN` vào dead letter ngay vì đây là trạng thái **cần biết thêm thông tin**, không phải bằng chứng submission thất bại. Hệ thống có thể có một reconciliation queue riêng.

### 17.1. Khi nào UNKNOWN có thể chuyển sang retry?

Chỉ khi:
- provider/API cung cấp idempotency key đảm bảo theo contract;
- log/provider xác nhận chưa tiếp nhận;
- hoặc policy nghiệp vụ có lựa chọn chấp nhận rủi ro duplicate và theo dõi rõ.

Test phải xác minh quyết định reconciliation được ghi bền vững trước khi chuyển `UNKNOWN` sang `RETRY_WAIT`.

### 17.2. Lỗi database sau khi SMTP accepted

Một ca đặc biệt:
1. `gateway.submit(...)` trả thành công.
2. `repository.markAccepted(...)` gặp database outage.
3. Job vẫn ở `SENDING` và lease hết hạn.

Bài test cần mô phỏng **lỗi persist kết quả sau side effect**, không chỉ lỗi `gateway.submit`. Đây là nơi workflow dễ gửi trùng.

Cách an toàn là ghi nhận job có thể đã accepted và reconciliation; không biến tất cả lease-expired rows thành pending ngay. Nếu cần, dùng gateway/protocol có idempotency được hỗ trợ hoặc một cơ chế audit/đối soát.

## 18. Kịch bản 5 — Job chưa đến hạn không bị claim

Integration test nên tạo hai jobs:
- `A`: `RETRY_WAIT` với `next_attempt_at` trong tương lai.
- `B`: `PENDING` và đang đến hạn.

Kỳ vọng:
- Worker chọn B.
- A giữ nguyên attempt_count.
- Sau khi clock tiến đến hạn của A, worker mới chọn A.
- Không có vòng lặp bận khiến CPU liên tục query cùng một job chưa tới hạn.

Test nên dùng database thật vì query `WHERE next_attempt_at <= :now` và index/datetime semantics là phần quan trọng của hệ thống.

### 18.1. Biên thời gian chính xác

Thêm ca `next_attempt_at == now` phải được phép claim nếu quy ước là `<=`. Nếu code dùng `<`, job có thể bị chậm đến chu kỳ quét sau. Quy định rõ kiểu timestamp (UTC/`TIMESTAMPTZ`) và xử lý sai lệch đồng hồ giữa nodes.

### 18.2. Jitter cần được kiểm soát trong test

Production backoff có jitter để tránh nhiều worker thử lại cùng lúc. Với integration test, inject một nguồn random có seed cố định hoặc một `RetryDelayStrategy` giả lập, rồi assert phạm vi/thời điểm theo contract.

Không dùng `Math.random()` trực tiếp trong code sản xuất nếu điều đó làm test không thể dự đoán thời điểm due; cũng không nên assert một số giây cố định khi chính sách thực tế có jitter.

## 19. Kịch bản 6 — Hai worker chạy đồng thời

Concurrency là lý do mạnh để dùng **PostgreSQL thật** thay vì chỉ mock repository.

Giả sử một job `PENDING` và hai worker cùng `claimDue(now)`.

```text
Worker A                 PostgreSQL              Worker B
   |                         |                        |
   |-- claimDue ------------>|<----------- claimDue --|
   |                         |                        |
   |<-- leaseToken=A --------|------ no job --------->|
   |                         |                        |
   +-- submit SMTP           |                        |
   +-- markAccepted -------->|                        |
```

Kỳ vọng:
- Một worker nhận job, worker còn lại không.
- Tổng số gateway submissions là 1.
- `attempt_count=1`.
- Một attempt history row.
- Status cuối phù hợp.
- Không có hai lease owners đồng thời.

### 19.1. Test dùng barrier/latch thay vì Thread.sleep

Trong test có thể dùng:
- `CountDownLatch` để đồng bộ thời điểm hai worker bắt đầu claim;
- `ExecutorService` có hai thread;
- `Future.get(...)` với timeout hợp lý;
- query database sau khi cả hai hoàn tất.

Mẫu khung:

```java
CountDownLatch start = new CountDownLatch(1);
ExecutorService executor = Executors.newFixedThreadPool(2);

try {
    Callable<Boolean> task = () -> {
        start.await();
        return processor.processOne();
    };

    Future<Boolean> first = executor.submit(task);
    Future<Boolean> second = executor.submit(task);

    start.countDown();

    boolean a = first.get(10, TimeUnit.SECONDS);
    boolean b = second.get(10, TimeUnit.SECONDS);

    assertThat((a ? 1 : 0) + (b ? 1 : 0))
        .isEqualTo(1);

    assertThat(gateway.invocationCount())
        .isEqualTo(1);
} finally {
    executor.shutdownNow();
}
```

Thời gian chờ trong `Future.get` là **timeout bảo vệ test khỏi treo**, không phải sleep để “chờ retry”. Một test concurrency nghiêm túc nên kiểm soát được các transaction/connection để hai worker thật sự cạnh tranh cùng job. Nếu chạy tuần tự quá nhanh, test vẫn có thể pass nhưng không gây ra tranh chấp như dự định.

### 19.2. Lease expiry trong khi gửi

Một trường hợp nguy hiểm:
- Worker A claim job và chậm trước khi ghi kết quả.
- Lease hết hạn.
- Worker B bắt đầu xử lý lại.
- Worker A hoàn tất SMTP rồi cố ghi kết quả.

Test cần xác nhận:
- Update của A với lease token cũ bị từ chối.
- Database không bị trạng thái cũ ghi đè.
- Hệ thống có cơ chế xử lý nguy cơ **duplicate submission**, vì fencing DB không thể ngăn SMTP bên ngoài đã nhận message.

Không tự cho phép B resend ngay chỉ vì A mất lease nếu không có chính sách xử lý outcome chưa xác định.

## 20. Kịch bản 7 — Khởi động lại ứng dụng không mất retry

Một lỗi trong production chỉ xuất hiện sau restart:
- retry được tính bằng `ScheduledFuture` trong bộ nhớ;
- không lưu `next_attempt_at`;
- process restart làm mất lịch.

Integration test nên:
1. Insert job.
2. Chạy attempt đầu, nhận lỗi transient.
3. Xác nhận `RETRY_WAIT` và `next_attempt_at` đã commit.
4. Tạo worker/service instance mới hoặc restart Spring context có kiểm soát.
5. Giữ **cùng PostgreSQL database**.
6. Tiến clock tới thời gian due.
7. Chạy worker mới và xác nhận attempt 2 được thực hiện.

Không dùng một `@Scheduled` event trong bộ nhớ như nguồn sự thật duy nhất. Database hoặc broker durable phải giữ trạng thái retry.

### 20.1. Test khác: ứng dụng crash giữa claim và gửi

Mô phỏng:
- Job chuyển `SENDING` với lease.
- Worker dừng trước khi gọi gateway.
- Sau khi lease hết hạn, recovery policy kiểm tra dữ liệu bền vững.

Nếu hệ thống có bằng chứng chắc chắn chưa gọi gateway, có thể retry. Nếu không chắc chắn, giữ `UNKNOWN` để giảm rủi ro gửi trùng. Test phải dựa vào **dữ liệu thật có thể quan sát**, không dựa vào giả định rằng mọi job `SENDING` đều chưa được gửi.

### 20.2. Test lỗi transaction rollback

Thử làm `recordFailure` phát sinh database constraint error giữa chừng. Kỳ vọng:
- Không commit trạng thái `DEAD_LETTER` nếu insert dead-letter record thất bại.
- Lịch sử attempt không bị ghi nửa chừng nếu thiết kế yêu cầu atomicity.
- Có tín hiệu vận hành để phát hiện lỗi persist outcome.

Đây là kiểm thử tích hợp transaction, không thể suy ra từ test Mockito chỉ verify hai method đã được gọi.

## 21. Kịch bản 8 — Dead-letter replay an toàn

Dead letter không phải “thư mục chứa những email cần gửi lại tất cả”. Replay có thể dẫn đến gửi trùng hoặc lặp lỗi vĩnh viễn nếu không có quy trình kiểm soát.

Một workflow có thể là:

```text
DEAD_LETTER
     |
     v
Operator reviews reason / recipient / template
     |
     v
Fix root cause + authorize replay
     |
     +--> Requeue same logical message
     |    with new attempt (when policy permits)
     |
     +--> Create a new logical notification
          with explicit relationship (when business requires)
```

Cần quy định:
- ai được replay;
- khi nào được replay;
- có giữ message key hay tạo email mới;
- có giữ lịch sử attempts hay không;
- có reset budget không;
- có cần xác minh recipient vẫn hợp lệ không;
- có cần kiểm tra provider suppression/bounce không;
- trường hợp `UNKNOWN` phải reconciliation trước khi cho replay.

### 21.1. Assertions cho replay

- Không có replay tự động từ worker thường.
- Chỉ endpoint/command được phân quyền mới requeue.
- Có audit record: actor, time, reason, original message key.
- Replay không xóa attempt history/dead-letter history.
- Nếu replay cùng email logic, attempt_number tiếp tục tăng thay vì trùng unique key.
- Có quy tắc riêng cho retry budget sau replay.
- Replay hai lần bằng cùng request key không tạo hai jobs.
- Recipient đã bị suppress/opt-out không tự được phép gửi lại.

### 21.2. Không reset attempt_count một cách âm thầm

Nếu reset attempt_count về 0 nhưng vẫn giữ các attempt cũ, ý nghĩa đếm trở nên mâu thuẫn. Có thể thiết kế:
- `attempt_count` là tổng số attempt suốt đời message, không reset;
- `retry_cycle` hoặc `replay_generation` đếm các lượt replay được phê duyệt;
- budget áp dụng theo generation với số attempt riêng.

Mô hình nào cũng được nếu được định nghĩa rõ và integration tests bảo vệ invariant.

## 22. SMTP integration test với local test server

Test database workflow dùng scripted gateway chưa chứng minh `JavaMailSenderImpl` nói chuyện SMTP đúng. Một bộ test nhỏ riêng nên gửi vào **SMTP sandbox**.

Các lựa chọn:
- **GreenMail**: thư viện Java SMTP/IMAP/POP3 test server, thuận tiện cho Spring/Jakarta Mail integration.
- **Mailpit/MailHog**: công cụ nhận email thử nghiệm qua SMTP, có giao diện/API quan sát message.
- **Programmable SMTP fake**: server hoặc protocol proxy có thể chủ động trả lỗi `421`, `451`, `550`, đóng kết nối hoặc timeout tại một phase cụ thể.
- **Provider sandbox**: dùng khi cần kiểm thử contract provider thật, có quota và ràng buộc riêng.

Chọn công cụ phù hợp với điều cần chứng minh. Một SMTP sink chỉ chấp nhận thư rất tốt cho happy path, nhưng **không nhất thiết hỗ trợ giả lập mọi lỗi SMTP**.

### 22.1. Ví dụ gửi vào GreenMail để xác minh SMTP thật

Ví dụ ý tưởng trong test integration có dependency GreenMail phù hợp phiên bản Jakarta Mail của dự án:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.assertj.core.api.Assertions.assertThat;

class SmtpSubmissionIntegrationTest {

    @Test
    void realJavaMailSenderCanSubmitToTestServer()
            throws Exception {

        GreenMail smtp = new GreenMail(ServerSetupTest.SMTP);
        smtp.start();

        try {
            JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

            sender.setHost("127.0.0.1");
            sender.setPort(smtp.getSmtp().getPort());

            var message = sender.createMimeMessage();
            var helper = new MimeMessageHelper(
                message, false, "UTF-8"
            );

            helper.setFrom("no-reply@example.com");
            helper.setTo("qa@example.net");
            helper.setSubject("Kiểm thử retry");
            helper.setText("Xin chào từ SMTP test server.", false);

            sender.send(message);

            assertThat(smtp.getReceivedMessages())
                .hasSize(1);
        } finally {
            smtp.stop();
        }
    }
}
```

Port/test setup cụ thể cần được chọn để tránh xung đột khi chạy test song song; tham khảo API của phiên bản GreenMail đang dùng để cấp port ngẫu nhiên hoặc cách ly server instance. Ví dụ trên minh họa **happy path SMTP**, không chứng minh SMTP 451/550 hoặc dead-letter policy.

### 22.2. Kiểm thử reply 451 hoặc 550 bằng fault-injection

Muốn test lỗi SMTP thật, cần một server có thể chủ động:

```text
Client                      SMTP test relay
  |---- EHLO ---------------->|
  |<--- 250 ------------------|
  |---- MAIL FROM ----------->|
  |<--- 250 ------------------|
  |---- RCPT TO ------------->|
  |<--- 451 Temporary failure |
```

Và:

```text
Client                      SMTP test relay
  |---- RCPT TO ------------->|
  |<--- 550 No such user -----|
```

Test cần xác minh:
- Jakarta Mail/Spring ném exception nào;
- nested SMTP reply/code có sẵn không;
- classifier map đúng transient/permanent;
- không log recipient/token ngoài chính sách.

Nếu giả lập disconnect sau DATA, kết luận có thể là `UNKNOWN`. Không nên chỉ nhìn một `SocketException` rồi khẳng định relay đã hoặc chưa chấp nhận message.

### 22.3. Tránh nhầm tầng retry

Khi provider đã accepted submission rồi báo delivery deferred, **provider** thường tự retry giao đến MX đích. Worker không nên resubmit ngay chỉ vì event deferred. Trong test, cần phân biệt:
- **submission retry** do Spring worker quản lý;
- **delivery retry** do provider/MTA quản lý.

Một webhook `deferred` không nên kích hoạt `JavaMailSender.send(...)` lần thứ hai cho message đã được accepted.

## 23. Test dead-letter queue của broker khi không dùng DB-only

Nếu hệ thống dùng RabbitMQ, Kafka hoặc broker khác, khái niệm dead letter có semantics riêng. Không nên áp dụng trực tiếp `mail_dead_letter` SQL rồi cho rằng broker đã vận hành đúng.

### 23.1. RabbitMQ và DLX

Với RabbitMQ:
- Message có thể được dead-letter khi bị reject/nack không requeue, hết TTL hoặc vượt policy liên quan.
- Dead-letter exchange (DLX) và routing key phải cấu hình đúng.
- Một message có thể bị broker chuyển tới queue khác; cần kiểm tra broker config và consumer ack.
- Tránh vòng lặp DLQ → main queue → DLQ không có giới hạn.

Integration test với RabbitMQ Testcontainers có thể:
1. Publish job vào source queue.
2. Consumer xử lý fail theo policy.
3. Kiểm tra message xuất hiện ở DLQ.
4. Kiểm tra source queue không còn job được xử lý.
5. Kiểm tra metadata/attempt count hoặc headers theo contract.
6. Replay có điều kiện và kiểm tra dedupe.

### 23.2. Kafka và DLT

Với Kafka, dead-letter topic (DLT) thường do consumer framework/policy chuyển các records không xử lý được sang topic riêng. Cần kiểm tra:
- số lần retry và backoff;
- topic/partition/headers;
- offset commit;
- idempotency khi consumer bị restart;
- lỗi publish DLT;
- phân quyền replay.

Kafka không mặc định có chính xác semantics giống RabbitMQ DLX. Dùng chính broker và framework listener container tương ứng trong integration test.

### 23.3. Atomicity giữa DB, SMTP và broker

Không có một transaction đơn giản bao trùm cả:
- database transaction;
- SMTP submission không thể rollback;
- broker ack/publish;
- webhook delivery.

Một test tốt không cần hứa **exactly-once email delivery**. Nó phải chứng minh hệ thống **ghi trạng thái bền vững, giảm duplicate, có idempotency và xử lý được kết quả không rõ** theo contract thiết kế.

## 24. Kiểm thử quan sát vận hành và alert

Retry/dead letter không chỉ là thuật toán. Khi có sự cố, đội vận hành phải biết chuyện gì đã xảy ra.

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| `mail_outbox_pending` | Số job chưa được thử |
| `mail_outbox_retry_wait` | Số job đang chờ retry |
| `mail_outbox_unknown` | Số job cần reconciliation |
| `mail_dead_letter_total` | Tổng số job bị dead letter theo lý do |
| `mail_submit_attempts_total` | Lượt submission theo provider/outcome |
| `mail_retry_delay_seconds` | Phân bố khoảng chờ |
| `mail_outbox_oldest_age_seconds` | Phát hiện backlog lâu |
| `mail_lease_expired_total` | Cảnh báo worker/timeout bất thường |
| `mail_send_duplicate_suspected_total` | Theo dõi sự kiện nghi gửi trùng |

Structured log minh họa:

```json
{
  "event": "mail.dead_letter",
  "messageKey": "msg-123",
  "attemptId": "att-3",
  "attemptNumber": 3,
  "reasonCode": "SMTP_TEMP_451",
  "status": "DEAD_LETTER",
  "retryOwner": "outbox-worker"
}
```

Không cần log toàn bộ MIME, địa chỉ người nhận, authentication credentials hoặc attachment bytes để trace.

### 24.1. Kiểm tra phát sự kiện dead letter đúng một lần

Nếu ứng dụng tạo domain event/metric khi job chuyển dead letter:
- một dead-letter transition chỉ nên tạo một sự kiện nghiệp vụ theo idempotency policy;
- webhook/worker retry không làm phát lại sự kiện vô hạn;
- log/metric không được dùng làm nguồn duy nhất xác định trạng thái;
- nếu event được gửi ra broker, dùng transactional outbox nếu cần bảo đảm không mất event khi DB commit.

Integration test có thể assert event record được ghi đúng trong database trước khi worker chuyển sang trạng thái cuối. Kiểm thử tính chính xác của metric exporter là lớp khác.

### 24.2. Cảnh báo theo mức độ ưu tiên

Ví dụ:
- Bất kỳ `UNKNOWN` nào kéo dài quá ngưỡng có thể cần reconciliation.
- Dead letters liên tục tăng do `SMTP_AUTH_FAILURE` là tín hiệu cấu hình/secret bị lỗi.
- Retry queue tăng nhưng không có success có thể cho biết provider outage.
- Dead letter tăng do recipient invalid có thể yêu cầu làm sạch dữ liệu.
- Backlog già hơn SLA cần cảnh báo.

Test integration có thể kiểm tra query/nguồn dữ liệu để hệ thống giám sát lấy số liệu đúng; không cần gửi thông báo cảnh báo tới kênh thật trong mỗi test.

## 25. Tách test fixture và giữ suite deterministic

### 25.1. Isolation giữa các test

Nếu dùng cùng database container, mỗi test cần làm sạch state phù hợp:

```sql
TRUNCATE TABLE
    mail_dead_letter,
    mail_send_attempt,
    mail_outbox
RESTART IDENTITY CASCADE;
```

Chỉ dùng trong **database test đã được xác nhận**, không bao giờ chạy cleanup như vậy trên production. Với nhiều class test chạy song song, nên dùng schema/container riêng hoặc chiến lược isolation rõ ràng.

Không để test trước có job `RETRY_WAIT` làm test sau nhận job bất ngờ. Reset scripted gateway và test clock trước mỗi case.

### 25.2. Đảm bảo database schema có migration

Không nên tạo schema ad hoc khác production để test pass. Nếu production dùng Flyway/Liquibase:
- chạy migrations tương ứng trên PostgreSQL test container;
- thực thi repository thật;
- kiểm tra index, unique constraints, transaction boundaries;
- chỉ dùng extra test data để tạo kịch bản, không sửa quy tắc schema.

### 25.3. Dùng dữ liệu giả

Dùng:
- `customer@example.net`;
- `no-reply@example.com`;
- `ORD-TEST-001`;
- message key UUID mới cho mỗi case;
- plaintext không chứa dữ liệu cá nhân thật.

Không dùng SMTP password, reset token hoặc recipient thật trong fixtures. Nếu môi trường test có cấu hình provider, thiết kế để gateway fake **không thể vô tình chuyển sang sender thật**.

### 25.4. Không phụ thuộc vào thời gian wall clock

Khi test tới hạn retry, so sánh `Instant` theo test clock. Tránh `Thread.sleep`. Khi kiểm thử concurrency, dùng barrier/latch và bounded timeouts, không dùng chờ ngẫu nhiên.

Nếu production policy có jitter, inject deterministic strategy vào test. Điều này không làm giảm ý nghĩa integration test của database/worker.

## 26. Ma trận test nên có

| Kịch bản | Kết quả mong đợi |
|---|---|
| Job mới, SMTP accepted ngay | `SMTP_ACCEPTED`, 1 attempt, không DL |
| Lỗi transient rồi accepted | `RETRY_WAIT` → `SMTP_ACCEPTED`, đúng lịch |
| Gọi worker trước `next_attempt_at` | Không claim, không gửi |
| Đúng biên thời gian due | Được claim theo quy tắc `<=` |
| Transient liên tục tới max attempts | `DEAD_LETTER`, không có attempt vượt ngưỡng |
| Permanent failure attempt đầu | Dead letter ngay |
| Dữ liệu invalid trước gửi | Không gửi hoặc dead letter theo contract, không retry vô hạn |
| Unknown submission outcome | `UNKNOWN`, không auto resend |
| Provider deferred sau accepted | Không tạo submission mới |
| Hai worker claim cùng job | Chỉ một lease/attempt/gateway submission |
| Lease cũ ghi outcome sau khi hết hạn | Fencing từ chối stale update |
| DB outage sau SMTP accepted | Không tự coi an toàn để resend |
| Dead-letter insert fail | Transaction rollback, không commit trạng thái lệch |
| Restart giữa hai lần retry | `RETRY_WAIT` bền vững, attempt tiếp vẫn chạy |
| Restart lúc `SENDING` | Recovery theo policy, không resend mù |
| Replay không phân quyền | Bị từ chối, không đổi trạng thái |
| Replay được phép | Có audit, không mất attempt history |
| Replay request trùng | Không tạo hai lần replay ngoài ý muốn |
| Nhiều recipients/partial success | Không retry nguyên danh sách mà gửi trùng recipient đã accepted |
| Thay đổi retry budget | Áp dụng theo config, không sai số attempt |
| SMTP 451/550 từ test relay | Adapter phân loại theo command/context |
| SMTP success qua test server | `JavaMailSenderImpl` submit được MIME, không gửi Internet |
| Dead letter đã tồn tại | Ghi idempotent/constraint không tạo bản ghi trùng |

Ma trận này là công cụ chọn test cases cho **tích hợp retry và dead letter**. Các ca concurrency/recovery khó mô phỏng cần hạ tầng test tương ứng; không nên chỉ mock repository rồi ghi nhận “đã kiểm thử tích hợp”.

## 27. Những hiểu lầm thường gặp

### “JUnit verify send được gọi ba lần là đủ”

Không. Phải chứng minh trạng thái database, thời điểm retry, attempt history và dead letter được ghi đúng. Ba lời gọi mock không phản ánh transaction hoặc lịch retry thực.

### “Mọi MailException đều nên retry”

Không. Lỗi template, credential, certificate hoặc recipient có thể cần sửa nguyên nhân. Timeout không rõ kết quả phải có trạng thái riêng.

### “Dead letter nghĩa là xóa job khỏi hệ thống”

Không. Nên giữ lịch sử/metadata phục vụ đối soát và replay; DLQ/bảng dead letter là điểm giữ và điều tra, không phải thùng rác vô danh.

### “Max attempts = 3 nghĩa là ba lần retry sau lần đầu”

Không nếu contract đếm tổng số attempt. Cần xác định rõ attempt_count và test off-by-one.

### “Cứ lease hết hạn là chắc worker chưa gửi”

Không. Worker có thể đã gửi nhưng chưa ghi kết quả, hoặc đang bị treo sau side effect SMTP. Cần reconciliation/chính sách xử lý duplicate.

### “Testcontainers PostgreSQL là unit test”

Không. Dùng database thật trong container là integration test. Đây chính là điều cần khi kiểm tra transaction, locking và query due-time.

### “GreenMail pass thì provider thật cũng chắc pass”

Không. SMTP test server xác nhận đường code/giao thức theo môi trường kiểm soát. Provider thật còn TLS policy, quota, AUTH, reputation và routing riêng.

### “SMTP accepted là delivered”

Không. Đó là mốc submission. Delivery có thể còn deferred/bounced và provider có thể retry ở tầng khác.

### “Chỉ cần @Retryable quanh send là có độ tin cậy”

Không. Retry in-memory có thể mất khi process restart, che outcome `UNKNOWN` và tạo gửi trùng. Với email quan trọng cần persistence, budgets và observability.

### “Có message key thì SMTP tự dedupe”

Không. Generic SMTP không cam kết idempotency theo custom header. Message key giúp trace, không biến gửi email thành exactly-once.

## 28. Bài tập thực hành

### Bài 1 — Schema và trạng thái

Tạo ba bảng `mail_outbox`, `mail_send_attempt` và `mail_dead_letter` trong PostgreSQL Testcontainers. Chèn một job `PENDING` rồi query trạng thái từ connection khác sau commit.

### Bài 2 — Transient retry

Tạo scripted gateway trả `TRANSIENT` rồi `ACCEPTED`. Chạy processor, advance clock đúng delay và xác nhận 2 attempts cùng message key, trạng thái cuối `SMTP_ACCEPTED`.

### Bài 3 — Dead letter sau max attempts

Đặt maxAttempts=3 và cả ba lần đều `TRANSIENT`. Chứng minh job chuyển `DEAD_LETTER`, có một dead-letter entry và không thể tạo attempt 4.

### Bài 4 — Permanent failure

Cho gateway trả `PERMANENT` ở lần đầu. Xác nhận dead letter ngay, error code được lưu an toàn và không có retry schedule.

### Bài 5 — Unknown outcome

Cho gateway trả `UNKNOWN`. Tiến clock một ngày rồi chạy worker. Chứng minh không có submission mới và job vẫn chờ reconciliation.

### Bài 6 — Due time

Tạo hai job với `next_attempt_at` khác nhau. Xác minh worker chỉ chọn job đến hạn; test cả trường hợp due-time bằng chính xác `now`.

### Bài 7 — Concurrency

Dùng hai worker cùng PostgreSQL và latch/barrier để tranh claim một job. Xác nhận một attempt, một lease, một gateway submission.

### Bài 8 — Lease fencing

Mô phỏng worker A hết lease rồi worker B có lease mới. Cho A cố gọi `markAccepted` với token cũ; phải bị từ chối mà không ghi đè trạng thái.

### Bài 9 — Crash/restart

Sau lần transient đầu tiên, tạo processor instance mới trên cùng database. Chạy lại khi clock tới hạn và xác nhận lịch retry còn nguyên.

### Bài 10 — Atomic dead-letter transaction

Làm insert `mail_dead_letter` thất bại có chủ đích trong transaction test. Xác nhận update trạng thái và attempt outcome không bị commit nửa chừng.

### Bài 11 — SMTP fault injection

Dùng SMTP server test có thể trả `451` ở `RCPT TO` và `550` ở một case khác. Kiểm tra adapter phân loại lỗi, không chỉ test scripted gateway.

### Bài 12 — Timeout sau DATA

Mô phỏng relay có thể đã accepted nhưng connection mất trước response. Ghi `UNKNOWN` và thiết kế bài test reconciliation trước khi resend.

### Bài 13 — Dead-letter replay

Thiết kế API/command replay có kiểm tra quyền và audit. Test replay request trùng không tạo hai job; lịch sử attempts không bị xóa.

### Bài 14 — Provider deferred

Giả lập webhook `deferred` sau khi submission đã `SMTP_ACCEPTED`. Xác nhận app cập nhật delivery status nếu có, **không gọi JavaMailSender.send thêm lần nữa**.

### Bài 15 — Retry budget theo deadline

Với email xác minh hết hạn sau 10 phút, mô phỏng provider outage 15 phút. Dù chưa hết max attempts, test job được dừng theo deadline và không gửi link hết hạn.

### Bài 16 — Quan sát và bảo mật

Với một dead letter `SMTP_AUTH_FAILURE`, kiểm tra structured event/metric chứa message key, attempt number và safe code nhưng không có SMTP password, full MIME body hoặc token xác minh.

## 29. Tổng kết

**Kiểm thử retry và dead letter** trong Spring Framework Mail phải đi xa hơn việc mock `send(...)` rồi đếm số lời gọi. Mục tiêu là chứng minh **toàn bộ workflow bền vững**: một email logic được lưu trong outbox, worker claim đúng job, mỗi attempt được ghi nhận, lỗi transient được lên lịch retry, lỗi permanent/hết ngân sách được lưu dead letter, và kết quả `UNKNOWN` được giữ lại để reconciliation.

Cách tiếp cận thực tế:

1. Dùng **PostgreSQL Testcontainers** hoặc database tương ứng production để kiểm tra transaction, unique constraints, claim và lease.
2. Điều khiển tầng SMTP bằng **scripted gateway** ở workflow tests; dùng SMTP test relay/fault injection trong một bộ transport integration test riêng.
3. Inject **Clock** và chiến lược delay để xác minh due-time/backoff chính xác mà không `Thread.sleep`.
4. Test cả **success path, transient, permanent, max attempts, UNKNOWN, crash recovery, concurrency, atomic dead-letter commit và replay**.
5. Không đồng nhất `SMTP_ACCEPTED` với `DELIVERED` và không resubmit khi provider đã accepted nhưng đang deferred.
6. Bảo vệ **message key, attempt history, dead-letter reason và audit**, hạn chế nội dung nhạy cảm trong log.
7. Không tuyên bố exactly-once SMTP: khi submission outcome chưa rõ, cần phân định rủi ro duplicate và có reconciliation/approval.

Một bộ integration test tốt cho retry và dead letter không chỉ đảm bảo worker “thử lại đủ lần”. Nó chứng minh rằng hệ thống **không làm mất công việc, không lặp vô hạn, không gửi lại khi không an toàn và để lại bằng chứng vận hành rõ ràng khi phải dừng xử lý tự động**.

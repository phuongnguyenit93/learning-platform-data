# Xây worker retry với trạng thái và dead letter

Một ứng dụng **Spring Framework Mail** có thể gửi email ngay trong HTTP request bằng **JavaMailSender.send(...)**. Cách này phù hợp để học API, nhưng dễ gặp vấn đề khi SMTP chậm, provider giới hạn tốc độ, worker bị restart, người dùng nhấn gửi lại hoặc hệ thống cần biết chính xác notification đang chờ, đã được nộp SMTP hay phải xử lý thủ công.

Trong **dự án thực hành** này, chúng ta xây một **email delivery worker** sử dụng **Spring Boot, Spring Mail, Spring JDBC và PostgreSQL**. Ứng dụng lưu ý định gửi vào một **transactional outbox**, worker claim job bằng transaction ngắn, gửi MIME mail qua JavaMailSender, ghi kết quả vào state machine, retry lỗi được chứng minh chưa được provider chấp nhận, đồng thời chuyển lỗi vĩnh viễn hoặc hết ngân sách retry sang **dead letter**. Khi SMTP timeout khiến không biết kết quả, job vào **UNKNOWN** để đối soát, không tự gửi trùng.

Bài học không chỉ mô tả khái niệm. Nội dung bao gồm cấu trúc project, schema SQL, Java records, repository, service, scheduler, retry policy, mã gửi SMTP, ví dụ REST tạo notification, hướng dẫn chạy cục bộ, unit/integration tests, quan sát và quy trình xử lý dead-letter queue (DLQ).

> **Nguyên tắc kỹ thuật:** **ACCEPTED** là server SMTP/provider đã chấp nhận submission theo phản hồi mà ứng dụng nhận được, **không đồng nghĩa email đã được giao đến Inbox**. Khi một lần gửi có kết quả không rõ (**UNKNOWN**), việc retry mù có thể gửi trùng. Dead letter là nơi giữ công việc **có thể kiểm tra và xử lý lại**, không phải chỗ xóa dữ liệu hoặc lời bảo đảm exactly-once.

## 1. Mục tiêu của dự án

Sau bài thực hành, hệ thống dự kiến có thể:

1. Nhận một yêu cầu gửi mail với **business idempotency key**.
2. Lưu **notification job** bền vững mà không gửi SMTP trong database transaction.
3. Claim job chưa đến hạn, có **lease token** để chống worker cũ ghi đè kết quả.
4. Giới hạn số lần thử, dùng **exponential backoff + jitter** khi lỗi retryable.
5. Giữ trạng thái rõ nghĩa: **PENDING, IN_FLIGHT, RETRY_WAIT, ACCEPTED, UNKNOWN, DEAD_LETTER, CANCELLED, EXPIRED**.
6. Tách lỗi permanent, lỗi cấu hình, lỗi transient và kết quả SMTP mơ hồ.
7. Lưu **attempt history**, lý do chuyển trạng thái và timestamps.
8. Đưa jobs không thể xử lý tự động sang **dead letter**, cho phép operator xem và replay có điều kiện.
9. Hạn chế việc hai replicas cùng submit một job và cô lập email nhạy cảm.
10. Đo backlog, tuổi công việc, retry, dead letter và các tình huống provider bị lỗi.

### Phạm vi

Để giữ trọng tâm, phiên bản tham khảo sử dụng **PostgreSQL làm durable job store**, không bắt buộc Kafka hoặc RabbitMQ. **Dead letter** được biểu diễn bằng trạng thái cùng bảng lưu lịch sử, không nhất thiết là một queue vật lý riêng. Khi mở rộng sang broker, các nguyên tắc về idempotency, trạng thái và kiểm soát UNKNOWN vẫn giữ nguyên.

Các đoạn code là **mẫu triển khai có hợp đồng rõ**, cần bổ sung cấu hình bí mật, migration, authorization, policy và các phần được đánh dấu trước khi vận hành thật. Chúng không thay thế kiểm thử chạy trên môi trường dự án.

## 2. Tại sao không gọi SMTP trực tiếp trong nghiệp vụ?

Ví dụ ban đầu:

~~~java
@PostMapping("/orders/{id}/confirm")
public ResponseEntity<String> confirm(@PathVariable String id) {
    orderService.confirm(id);
    mailSender.send(messageFor(id));
    return ResponseEntity.ok("confirmed");
}
~~~

Những tình huống có thể xảy ra:

| Sự cố | Kết quả có thể |
| --- | --- |
| Order commit, SMTP unavailable | Order đã xác nhận nhưng email chưa gửi |
| SMTP chậm 15 giây | HTTP request bị kéo dài hoặc timeout |
| Client retry HTTP vì không nhận response | Có thể enqueue/gửi lại |
| JVM chết sau order commit, trước send | Ý định gửi bị mất |
| Provider accepted rồi response bị mất | Retry có thể gây trùng |
| Nhiều requests cùng gửi | Quota/rate limit bị vượt |

### Mô hình đề xuất

~~~text
                 API / Business Event
                         |
                         v
                 Notification Service
                         |
                 BEGIN TRANSACTION
                         |
               +---------+---------+
               |                   |
               v                   v
          Business update     Insert outbox row
               |                   |
               +---------+---------+
                         |
                      COMMIT
                         |
                         v
                    HTTP response

             Separate scheduled worker(s)
                         |
                         v
                 Claim due job (DB)
                         |
                         v
                 Rate / policy checks
                         |
                         v
                   JavaMailSender
                         |
               +---------+----------+
               |         |          |
               v         v          v
           ACCEPTED  RETRY_WAIT    UNKNOWN
                         |          |
                         v          v
                       PENDING   Reconcile
                         |
                         v
                  DEAD_LETTER if exhausted
~~~

Nếu business data và outbox cùng transaction manager/database, thay đổi nghiệp vụ và ý định gửi được commit/rollback atomically. **SMTP vẫn nằm ngoài transaction đó**; worker phải phân loại kết quả và tránh gửi trùng.

## 3. Trạng thái và ý nghĩa

| State | Ý nghĩa | Có tự động chọn để gửi? |
| --- | --- | --- |
| **PENDING** | Job được tạo, chưa có attempt | Có, khi đến available_at |
| **IN_FLIGHT** | Worker đã claim, đang sở hữu lease/attempt | Không cho worker khác claim khi lease còn hợp lệ |
| **RETRY_WAIT** | Lỗi có thể retry, chờ backoff | Có, khi tới next_attempt_at |
| **ACCEPTED** | Provider/server đã xác nhận nhận submission | Không gửi lại tự động |
| **UNKNOWN** | Không biết message đã accepted chưa | Không tự retry; cần đối soát |
| **DEAD_LETTER** | Không thể tiếp tục tự động: permanent, hết tries hoặc policy | Không; chỉ xử lý/replay có kiểm soát |
| **EXPIRED** | Job vượt hạn thời gian nghiệp vụ | Không |
| **CANCELLED** | Có quyết định hủy ý định gửi | Không |

### State machine

~~~text
  CREATE
    |
    v
  PENDING ---------------------> CANCELLED / EXPIRED
    |
    | atomic claim + lease
    v
  IN_FLIGHT
    |
    +---- SMTP accepted -------------------> ACCEPTED
    |
    +---- proven retryable failure --------> RETRY_WAIT
    |                                         |
    |                                         | due time
    |                                         v
    |                                       IN_FLIGHT
    |
    +---- permanent / attempts exhausted ---> DEAD_LETTER
    |
    +---- ambiguous SMTP outcome -----------> UNKNOWN
    |
    '-- lease expired / crash -------------> UNKNOWN

  UNKNOWN -- reviewed, proven not accepted --> controlled retry
  UNKNOWN -- evidence accepted ------------> ACCEPTED
  UNKNOWN -- cannot reconcile / policy ----> DEAD_LETTER for review

  DEAD_LETTER -- approved replay ----------> PENDING (new generation)
~~~

Đường từ **UNKNOWN** về PENDING chỉ hợp lệ khi có bằng chứng/phê duyệt theo chính sách. Không tự xem việc một worker chết là chứng cứ SMTP không nhận message: worker có thể chết sau khi provider accepted và trước khi ghi kết quả.

### State là dữ liệu, không chỉ log

Nếu chỉ in **"retrying..."** trong log rồi không lưu trạng thái, JVM restart sẽ không biết job đã thử mấy lần hoặc có đang UNKNOWN không. State phải nằm trong database hoặc durable queue với semantics rõ ràng.

## 4. Bốn định danh không nên trộn lẫn

~~~text
businessKey        = ORDER:1528:CONFIRMED:customer-7
notificationId     = UUID của một logical notification
attemptId          = UUID của một lần thử SMTP
providerMessageId  = ID provider trả lại, nếu có
~~~

- **businessKey** giúp ngăn enqueue hai notification logic giống nhau từ một event.
- **notificationId** là khóa của outbox job, ổn định qua retries.
- **attemptId** thay đổi cho từng transport attempt.
- **providerMessageId** hỗ trợ tra cứu/reconciliation nếu provider có cung cấp.

**Header Message-ID của email** không phải khóa bảo đảm dedup toàn SMTP. Hai lần submit cùng Message-ID vẫn có thể tạo hai email. Không nhầm Message-ID với notificationId.

## 5. Chuẩn bị môi trường

Một stack tham khảo:

- **Java 17+**.
- **Spring Boot 3.x** với Jakarta Mail.
- **spring-boot-starter-mail**.
- **spring-boot-starter-jdbc**.
- **spring-boot-starter-web** cho API demo.
- **spring-boot-starter-validation** nếu muốn validate DTO.
- **PostgreSQL** làm outbox store.
- **Flyway** hoặc công cụ migration được chọn.
- **JUnit 5**, Spring Boot Test, Testcontainers và SMTP test fixture cho phần kiểm thử.

Không cần gọi một tài khoản email thật để hoàn tất logic worker. Có thể dùng SMTP server thử nghiệm cô lập nhận thư mà không relay ra Internet.

### Cấu trúc source gợi ý

~~~text
src/main/java/com/example/mailworker/
  MailWorkerApplication.java
  api/
    NotificationController.java
    CreateNotificationRequest.java
  domain/
    DeliveryState.java
    MailJob.java
    AttemptResult.java
  persistence/
    MailOutboxRepository.java
    JdbcMailOutboxRepository.java
  service/
    NotificationEnqueueService.java
    DeliveryWorker.java
    RetryPolicy.java
    SubmissionClassifier.java
    DeadLetterService.java
  transport/
    MailTransport.java
    SpringMailTransport.java
  config/
    MailWorkerProperties.java

src/main/resources/
  application.yml
  db/migration/
    V1__mail_worker.sql

src/test/java/com/example/mailworker/
  RetryPolicyTest.java
  MailWorkerIntegrationTest.java
  MailTransportTest.java
~~~

Các đường dẫn này là **ví dụ cấu trúc** của project học tập, không phải yêu cầu tạo thêm file trong nhiệm vụ viết bài hiện tại.

## 6. Dependencies

Một đoạn Maven **pom.xml** minh họa khi parent Spring Boot đã được quản lý bằng BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong một số phiên bản Flyway mới, PostgreSQL support nằm trong module **flyway-database-postgresql** riêng; dự án phải bổ sung module phù hợp dependency graph đã chọn. Không tự đoán rằng một pom fragment ở trên là dự án chạy độc lập: cần parent/BOM, plugins, Java target và cấu hình build tương ứng.

## 7. PostgreSQL schema: outbox và attempt history

Một schema bền vững giúp phân loại và đối soát:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    business_key VARCHAR(250) NOT NULL,
    recipient_address VARCHAR(320) NOT NULL,
    sender_profile VARCHAR(100) NOT NULL,
    subject TEXT NOT NULL,
    plain_body TEXT NOT NULL,
    html_body TEXT,
    state VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    lease_owner VARCHAR(120),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    provider_message_id VARCHAR(250),
    last_error_code VARCHAR(120),
    last_error_summary TEXT,
    dead_letter_reason VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ,
    CONSTRAINT uq_mail_outbox_business
        UNIQUE (tenant_id, business_key),
    CONSTRAINT ck_mail_outbox_attempts
        CHECK (attempt_count >= 0 AND max_attempts > 0),
    CONSTRAINT ck_mail_outbox_state CHECK (
        state IN (
            'PENDING', 'IN_FLIGHT', 'RETRY_WAIT',
            'ACCEPTED', 'UNKNOWN', 'DEAD_LETTER',
            'EXPIRED', 'CANCELLED'
        )
    )
);

CREATE INDEX idx_mail_outbox_due
ON mail_outbox (next_attempt_at, id)
WHERE state IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_lease
ON mail_outbox (lease_until)
WHERE state = 'IN_FLIGHT';

CREATE INDEX idx_mail_outbox_dead
ON mail_outbox (updated_at, id)
WHERE state = 'DEAD_LETTER';

CREATE TABLE mail_attempt (
    id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_outbox(id),
    attempt_number INTEGER NOT NULL,
    lease_token UUID NOT NULL,
    provider VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(50) NOT NULL,
    error_code VARCHAR(120),
    error_summary TEXT,
    provider_message_id VARCHAR(250),
    CONSTRAINT uq_mail_attempt_number
        UNIQUE (notification_id, attempt_number)
);

CREATE INDEX idx_mail_attempt_notification
ON mail_attempt (notification_id, attempt_number DESC);

CREATE TABLE mail_dead_letter_audit (
    id UUID PRIMARY KEY,
    notification_id UUID NOT NULL REFERENCES mail_outbox(id),
    action VARCHAR(40) NOT NULL,
    from_state VARCHAR(40),
    to_state VARCHAR(40),
    operator_id VARCHAR(120) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### Vài điểm về schema

- **UNIQUE (tenant_id, business_key)** ngăn tạo hai notification giống nhau theo quy tắc nghiệp vụ. Không dùng recipient address làm unique key duy nhất: một người có thể hợp lệ nhận nhiều notifications.
- **next_attempt_at** hỗ trợ scheduler lấy jobs đến hạn.
- **lease_owner + lease_token + lease_until** biểu diễn quyền sở hữu tạm thời và fencing.
- **attempt_count** tăng khi claim một attempt, không phải mỗi lần poll.
- **mail_attempt** giúp phân biệt nhiều lần thử và lỗi của từng lần.
- **DEAD_LETTER** vẫn giữ record; bảng audit chỉ bổ sung lịch sử thao tác quản trị.
- **recipient_address/body** là dữ liệu nhạy cảm, cần bảo vệ quyền truy cập, encryption/retention; production có thể lưu **opaque reference** thay vì nội dung đầy đủ.

### Không để schema quyết định mọi business policy

Ví dụ max_attempts=5 là mặc định minh họa. OTP có thể có TTL và số lần thử nhỏ hơn; email hóa đơn có chính sách khác. **Không đổi trạng thái ở DB một cách tùy ý** ngoài transition service/repository được kiểm soát.

## 8. Cấu hình ứng dụng Spring Boot

Ví dụ **application.yml** dùng thông số minh họa:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/maildemo
    username: maildemo
    password: example-local-only
  flyway:
    enabled: true
  mail:
    host: 127.0.0.1
    port: 3025
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000

app:
  mail-worker:
    enabled: true
    poll-delay-ms: 1000
    max-jobs-per-poll: 10
    lease-seconds: 45
    base-retry-seconds: 10
    max-retry-seconds: 600
    max-attempts: 5
~~~

**Mật khẩu database và SMTP host** chỉ dành cho local demo. Production phải dùng secret manager/environment injection, TLS certificate verification, verified From identity và một mail provider được ủy quyền. Nếu gửi tới SMTP cổng 587, phải cấu hình authentication và STARTTLS theo hợp đồng; **không gửi username/password qua kết nối không được bảo vệ**.

### Timeout liên quan tới lease

Nếu SMTP có connection timeout 5 giây, read/write timeout 10 giây, một attempt vẫn có thể kéo dài hơn 10 giây do nhiều bước SMTP, DNS, attachments hoặc provider chậm. **Lease 45 giây chỉ là ví dụ**, không phải chứng minh an toàn. Production phải chọn giới hạn tổng thời gian I/O có kiểm soát, heartbeat/lease extension hoặc xử lý các attempts quá hạn thành UNKNOWN khi còn nghi ngờ server đã accepted.

### Đặt các parameters trong cấu hình typed

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail-worker")
public record MailWorkerProperties(
        boolean enabled,
        long pollDelayMs,
        int maxJobsPerPoll,
        long leaseSeconds,
        long baseRetrySeconds,
        long maxRetrySeconds,
        int maxAttempts
) {
    public Duration lease() {
        return Duration.ofSeconds(leaseSeconds);
    }
}
~~~

Đăng ký properties bằng **@EnableConfigurationProperties(MailWorkerProperties.class)** hoặc **@ConfigurationPropertiesScan**. Đối với một dự án thật, thêm Bean Validation cho số dương và quan hệ min/max. Cấu hình YAML dùng tên kebab-case, Spring Boot binding ánh xạ về record components tương ứng.

## 9. Bootstrap Spring Boot và scheduler

~~~java
package com.example.mailworker;

import com.example.mailworker.config.MailWorkerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
@EnableConfigurationProperties(MailWorkerProperties.class)
public class MailWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MailWorkerApplication.class, args);
    }
}
~~~

Scheduler chạy theo chu kỳ, còn repository quyết định **job nào đã đến hạn và chưa thuộc lease khác**. Không cần giữ một thread đang ngủ cho mỗi notification.

### Scheduler không phải distributed leader

Nếu deploy bốn replicas với **@EnableScheduling**, mỗi replica đều chạy scheduler. Điều này **không tự gây trùng** khi claim được xây atomic, nhưng cần tránh mỗi replica tự vượt quota provider và cần giới hạn concurrency/batch size trên toàn cụm.

## 10. Tạo notification: idempotent enqueue

Một API có thể nhận yêu cầu:

~~~json
{
  "businessKey": "ORDER:ORD-1528:CONFIRMED:customer-7",
  "recipient": "customer@example.test",
  "subject": "Xác nhận đơn ORD-1528",
  "plainText": "Đơn ORD-1528 đã được xác nhận.",
  "html": "<p>Đơn <strong>ORD-1528</strong> đã được xác nhận.</p>"
}
~~~

Trong ví dụ production, **tenantId và From/senderProfile không được tin trực tiếp từ client chưa xác thực**. Tenant phải lấy từ authentication context; sender profile được giới hạn theo tenant/purpose.

### API nên nói rõ “queued”, chưa phải “sent”

~~~text
POST /notifications
  -> 202 Accepted
  -> { notificationId, state: "PENDING" }
~~~

**HTTP 202 Accepted ở API ứng dụng** nghĩa server đã chấp nhận yêu cầu để xử lý, **không phải SMTP 250 accepted**. Đừng trả lời người dùng “đã giao thư thành công” khi chưa có attempt.

### PostgreSQL insert chống trùng

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, business_key,
    recipient_address, sender_profile,
    subject, plain_body, html_body,
    state, attempt_count, max_attempts,
    next_attempt_at, expires_at
)
VALUES (
    :id, :tenantId, :businessKey,
    :recipient, :senderProfile,
    :subject, :plainBody, :htmlBody,
    'PENDING', 0, :maxAttempts,
    :availableAt, :expiresAt
)
ON CONFLICT (tenant_id, business_key) DO NOTHING;
~~~

Sau insert, nếu xung đột, đọc job cũ theo tenant/businessKey và trả cùng ID **chỉ nếu yêu cầu logic tương thích**. Nếu một caller tái sử dụng businessKey nhưng gửi payload/người nhận khác, nên trả **idempotency conflict**, không âm thầm báo thành công như thể cùng yêu cầu.

### Transactional outbox cùng nghiệp vụ

~~~text
BEGIN
   UPDATE orders SET status = 'CONFIRMED' ...
   INSERT INTO mail_outbox (...) ON CONFLICT DO NOTHING
COMMIT
~~~

Với business DB và outbox cùng PostgreSQL/transaction manager, notification intent tồn tại cùng thay đổi order. Nếu ứng dụng chỉ là mail service nhận API, transaction enqueue chỉ bảo đảm outbox được lưu, không tự bảo đảm transaction của một service khác.

### Không gửi ngay trong enqueue transaction

~~~java
@Transactional
public UUID enqueue(...) {
    UUID id = repository.insert(...);
    // Không gọi mailSender.send(...) ở đây.
    return id;
}
~~~

Nếu network I/O nằm trong DB transaction, lock giữ lâu và vẫn không có atomic commit với SMTP. Worker là boundary riêng.

## 11. Định nghĩa dữ liệu Java cho worker

~~~java
import java.time.Instant;
import java.util.UUID;

public enum DeliveryState {
    PENDING,
    IN_FLIGHT,
    RETRY_WAIT,
    ACCEPTED,
    UNKNOWN,
    DEAD_LETTER,
    EXPIRED,
    CANCELLED
}

public record ClaimedMailJob(
        UUID id,
        String tenantId,
        String recipient,
        String senderProfile,
        String subject,
        String plainBody,
        String htmlBody,
        int attemptCount,
        int maxAttempts,
        Instant expiresAt,
        UUID leaseToken,
        Instant leaseUntil
) {
}
~~~

**attemptCount** ở đây là số lần attempt thực sự đã bắt đầu, không phải số lần quota/controller từ chối job. Nếu job chưa được phép gửi vì quota, nên reschedule nó mà không tăng attempt count.

### Phân biệt claim và beginAttempt

Một quy trình chặt:

1. **Claim:** PENDING/RETRY_WAIT → IN_FLIGHT, cấp lease token; chưa gửi.
2. **Preflight:** kiểm tra expiry, sender, content, quota.
3. **Begin attempt:** ghi mail_attempt và tăng attempt_count trong transaction.
4. **Submit:** gọi SMTP ngoài transaction.
5. **Finalize:** update state, attempt outcome nếu còn đúng lease token.

Điểm số 3 giúp đo attempts chính xác. Nếu worker chết **sau beginAttempt nhưng trước submit**, hệ thống vẫn không biết tuyệt đối đã gọi transport chưa trừ khi có cơ chế ghi chứng cứ đáng tin, nên lease recovery có thể chọn UNKNOWN một cách bảo thủ.

## 12. Claim một job atomically với SKIP LOCKED

Đây là bước then chốt chống hai workers lấy cùng job ở cùng thời điểm. Dùng **PostgreSQL CTE + FOR UPDATE SKIP LOCKED**:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE state IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= :now
      AND (expires_at IS NULL OR expires_at > :now)
      AND attempt_count < max_attempts
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS job
SET state = 'IN_FLIGHT',
    lease_owner = :workerId,
    lease_token = :leaseToken,
    lease_until = :leaseUntil,
    updated_at = :now
FROM candidate
WHERE job.id = candidate.id
RETURNING
    job.id, job.tenant_id,
    job.recipient_address,
    job.sender_profile,
    job.subject, job.plain_body,
    job.html_body, job.attempt_count,
    job.max_attempts, job.expires_at,
    job.lease_token, job.lease_until;
~~~

### Vì sao SKIP LOCKED?

Hai workers đồng thời tìm cùng job:

~~~text
Worker A locks job 101.
Worker B sees job 101 locked -> skips it.
Worker B claims job 102.
~~~

Đây là pattern queue-like phù hợp cho PostgreSQL khi có nhiều consumers. Điều kiện quan trọng: **SELECT và UPDATE phải thực thi trong cùng statement/transaction**. Nếu app SELECT id ở một transaction rồi UPDATE không điều kiện ở transaction khác, vẫn có race.

### Claim transaction phải ngắn

Không giữ DB transaction/row lock trong lúc gọi SMTP. Claim xong thì commit. Thời gian network I/O diễn ra ngoài transaction để không làm cạn connection pool và gây lock contention.

### Claim không tăng attempt_count

Ở SQL trên, attempt_count giữ nguyên. Đây là thiết kế có chủ đích vì quota có thể từ chối job trước khi bắt đầu SMTP. Worker sẽ gọi **beginAttempt** riêng khi chuẩn bị submit.

### Expired jobs sẽ không được claim nhưng vẫn cần chuyển state

Điều kiện expires_at > now ngăn jobs hết hạn đi vào attempt. Nhưng những rows PENDING/RETRY_WAIT đã hết hạn vẫn phải được housekeeping chuyển sang **EXPIRED** để báo cáo rõ, không được bỏ lại vô hạn.

## 13. Repository JDBC: claim có lease token

Một triển khai minh họa dùng **NamedParameterJdbcTemplate**:

~~~java
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcMailOutboxRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public JdbcMailOutboxRepository(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<ClaimedMailJob> claimNext(
            String workerId,
            Instant now,
            Duration lease
    ) {
        UUID leaseToken = UUID.randomUUID();
        Instant leaseUntil = now.plus(lease);

        String sql = """
                WITH candidate AS (
                    SELECT id
                    FROM mail_outbox
                    WHERE state IN ('PENDING', 'RETRY_WAIT')
                      AND next_attempt_at <= :now
                      AND (expires_at IS NULL OR expires_at > :now)
                      AND attempt_count < max_attempts
                    ORDER BY next_attempt_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE mail_outbox AS job
                SET state = 'IN_FLIGHT',
                    lease_owner = :worker,
                    lease_token = :token,
                    lease_until = :until,
                    updated_at = :now
                FROM candidate
                WHERE job.id = candidate.id
                RETURNING job.*
                """;

        var params = new MapSqlParameterSource()
                .addValue("now", Timestamp.from(now))
                .addValue("worker", workerId)
                .addValue("token", leaseToken)
                .addValue("until", Timestamp.from(leaseUntil));

        List<ClaimedMailJob> jobs = jdbc.query(
                sql, params,
                (rs, rowNum) -> new ClaimedMailJob(
                        rs.getObject("id", UUID.class),
                        rs.getString("tenant_id"),
                        rs.getString("recipient_address"),
                        rs.getString("sender_profile"),
                        rs.getString("subject"),
                        rs.getString("plain_body"),
                        rs.getString("html_body"),
                        rs.getInt("attempt_count"),
                        rs.getInt("max_attempts"),
                        rs.getTimestamp("expires_at") == null
                                ? null
                                : rs.getTimestamp("expires_at")
                                    .toInstant(),
                        rs.getObject("lease_token", UUID.class),
                        rs.getTimestamp("lease_until").toInstant()
                )
        );

        return jobs.stream().findFirst();
    }
}
~~~

**JdbcMailOutboxRepository.claimNext(...)** được gọi từ một Spring bean khác để transaction proxy có hiệu lực. Không dùng self-invocation trong cùng class rồi mặc định **@Transactional** sẽ tạo transaction.

### Claim không đủ để bảo đảm không gửi trùng tuyệt đối

Nếu SMTP call chạy lâu hơn lease, một worker khác có thể thu hồi job. Recovery phải phân biệt **IN_FLIGHT timeout** với **PENDING**: không lấy job cũ và gửi lại ngay vì server có thể đã nhận. Phần sau thiết kế recovery đưa lease hết hạn sang UNKNOWN trước, giúp chặn duplicate tự động.

### Chú ý clock

Ví dụ dùng **Instant.now(...)** của ứng dụng. Với nhiều hosts, clock skew có thể làm lease/cửa sổ xử lý sai. Production có thể dùng DB time nhất quán hoặc giám sát NTP/time synchronization, đồng thời không đặt lease quá ngắn.

## 14. Ghi nhận bắt đầu attempt trong transaction riêng

Claim mới chỉ cấp quyền xử lý; worker có thể phát hiện quota chưa sẵn sàng và trả job về lịch chờ **mà chưa có SMTP attempt**. Chỉ khi sắp gọi transport, ta tăng **attempt_count** và tạo dòng **mail_attempt**.

Một SQL thực hiện atomically:

~~~sql
WITH bumped AS (
    UPDATE mail_outbox
    SET attempt_count = attempt_count + 1,
        updated_at = :now
    WHERE id = :notificationId
      AND state = 'IN_FLIGHT'
      AND lease_token = :leaseToken
      AND lease_until > :now
      AND attempt_count < max_attempts
    RETURNING attempt_count
)
INSERT INTO mail_attempt (
    id, notification_id, attempt_number,
    lease_token, provider, started_at, outcome
)
SELECT
    :attemptId,
    :notificationId,
    bumped.attempt_count,
    :leaseToken,
    :provider,
    :now,
    'STARTED'
FROM bumped
RETURNING attempt_number;
~~~

Nếu không có row trả về, worker **không được gửi**: lease có thể hết hạn, token đã bị thay hoặc đã đạt max_attempts. Đừng bỏ qua kết quả update chỉ vì đang có một MimeMessage sẵn trong memory.

### Tại sao tăng attempts lúc bắt đầu, không phải khi kết thúc?

Giả sử worker gửi SMTP rồi JVM chết trước khi ghi result. Nếu chỉ tăng attempt_count sau khi gửi, database vẫn nghĩ chưa từng attempt và có thể gửi lại vô hạn. Tạo attempt record trước external side effect ít nhất cho biết hệ thống **đã bắt đầu đường gửi**.

### Có phải BEGIN ATTEMPT chứng minh SMTP đã gọi?

Không. Worker có thể chết ngay sau khi transaction ghi STARTED, trước khi thực sự gọi SMTP. Khi recovery, ta có một vùng không chắc chắn. Chọn **UNKNOWN** là an toàn hơn tự tin gửi lại; có thể bổ sung stage marker/telemetry nhưng không nên tuyên bố exactly-once.

### Chặn đếm quota wait là attempts

Nếu quota controller trả **NO_PERMIT**, repository chuyển **IN_FLIGHT → RETRY_WAIT** và cập nhật next_attempt_at mà **không tăng attempt_count**. Nếu không, jobs có thể vào dead letter chỉ vì chờ quota, dù chưa hề thử gửi.

## 15. Hoàn tất attempt bằng fencing token

Sau SMTP, worker cần cập nhật state. Nhưng nếu lease đã hết và recovery/operator đã thay đổi job, worker cũ không được ghi đè.

Ví dụ:

~~~sql
UPDATE mail_outbox
SET state = :targetState,
    provider_message_id = :providerMessageId,
    last_error_code = :errorCode,
    last_error_summary = :safeSummary,
    next_attempt_at = COALESCE(
        :nextAttemptAt, next_attempt_at
    ),
    dead_letter_reason = :deadLetterReason,
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    accepted_at = CASE
        WHEN :targetState = 'ACCEPTED'
        THEN :now
        ELSE accepted_at
    END,
    updated_at = :now
WHERE id = :notificationId
  AND state = 'IN_FLIGHT'
  AND lease_token = :leaseToken;
~~~

Chỉ khi affected rows = **1**, mới coi finalization đã ghi thành công. Trong cùng transaction, cập nhật dòng **mail_attempt** tương ứng:

~~~sql
UPDATE mail_attempt
SET finished_at = :now,
    outcome = :attemptOutcome,
    error_code = :errorCode,
    error_summary = :safeSummary,
    provider_message_id = :providerMessageId
WHERE id = :attemptId
  AND notification_id = :notificationId
  AND lease_token = :leaseToken
  AND outcome = 'STARTED';
~~~

Nếu attempt update không ảnh hưởng đúng một row, transaction cần rollback và báo conflict. Không được có một transaction commit trạng thái ACCEPTED nhưng history không nhất quán chỉ vì swallowed exception.

### Fencing token giải quyết điều gì?

~~~text
10:00 Worker A claimed token A.
10:01 Lease expired / operator changed state.
10:02 Worker A receives an old SMTP response.
10:02 Worker A tries UPDATE WHERE token=A.
10:02 Affected rows=0 -> cannot overwrite newer state.
~~~

Tuy nhiên fencing **không ngăn một external side effect đã xảy ra**. Nếu worker A đã submit thành công, update DB bị từ chối không thể “rút lại email”. Bởi vậy recovery của expired IN_FLIGHT cần chính sách UNKNOWN.

### Repository nên có các operations tường minh

~~~java
public interface MailJobStore {

    java.util.Optional<ClaimedMailJob> claimNext(
            String workerId,
            java.time.Instant now,
            java.time.Duration lease
    );

    java.util.UUID beginAttempt(
            ClaimedMailJob job,
            String provider,
            java.time.Instant now
    );

    void releaseWithoutAttempt(
            ClaimedMailJob job,
            java.time.Instant nextAt,
            String reason
    );

    void finishAttempt(
            ClaimedMailJob job,
            java.util.UUID attemptId,
            AttemptResolution resolution,
            java.time.Instant now
    );

    int quarantineExpiredLeases(java.time.Instant now);
    int expireUnsentJobs(java.time.Instant now);
}
~~~

Mỗi operation cập nhật DB phải thực thi dưới transaction phù hợp. Khi cần phối hợp outbox/attempt trong cùng commit, nên đặt boundary ở **repository service bean** rõ ràng, không gọi self-invocation rồi tin rằng Spring proxy luôn tự kích hoạt.

## 16. Định nghĩa kết quả gửi độc lập với provider

Code business không nên dựa trực tiếp vào raw exception text của SMTP để quyết định next state. Tạo một hợp đồng normalized:

~~~java
public enum SubmissionKind {
    ACCEPTED,
    RETRYABLE_NOT_ACCEPTED,
    PERMANENT_NOT_ACCEPTED,
    UNKNOWN
}

public record SubmissionResult(
        SubmissionKind kind,
        String providerMessageId,
        String reasonCode,
        String safeSummary
) {
    public static SubmissionResult accepted(String providerId) {
        return new SubmissionResult(
                SubmissionKind.ACCEPTED, providerId, null, null
        );
    }

    public static SubmissionResult unknown(
            String reasonCode
    ) {
        return new SubmissionResult(
                SubmissionKind.UNKNOWN, null,
                reasonCode, "Submission outcome requires review"
        );
    }
}

public interface MailTransport {
    SubmissionResult submit(ClaimedMailJob job);
}
~~~

**RETRYABLE_NOT_ACCEPTED** chỉ dùng khi có bằng chứng đáng tin rằng server **chưa chấp nhận nội dung**. Với một lỗi SMTP tổng quát, không tự suy diễn chỉ từ thông báo “timeout”.

### Các loại lỗi

| Lỗi | Ý nghĩa | Kết quả an toàn |
| --- | --- | --- |
| Không thể kết nối trước SMTP dialogue | Chưa gửi DATA | RETRYABLE_NOT_ACCEPTED nếu chứng minh đúng stage |
| Provider trả 4xx rõ trước acceptance | Từ chối tạm thời | RETRYABLE_NOT_ACCEPTED theo provider contract |
| Địa chỉ người nhận không hợp lệ được xác định chắc | Không thể gửi với dữ liệu này | PERMANENT_NOT_ACCEPTED |
| SMTP auth sai | Cấu hình/provider issue | Pause lane, alert; không retry storm |
| Template thiếu biến bắt buộc | Lỗi render | Dead letter hoặc review trước SMTP |
| Mất response sau DATA | Server có thể accepted | UNKNOWN |
| API trả success với provider message ID | Submission accepted | ACCEPTED |
| Worker chết khi đang gửi | Không thể biết hoàn tất hay chưa | UNKNOWN khi lease recovery |

### Phân biệt lỗi của SMTP và lỗi trước SMTP

Nếu parser template ném exception **trước khi MailTransport.submit(...)**, không có SMTP attempt. Không đánh dấu UNKNOWN cho một lỗi format xác định; xử lý **PREPARATION_FAILED / DEAD_LETTER** theo policy. Ngược lại, nếu socket reset khi send đang diễn ra, một exception chung không chứng minh nội dung chưa được server nhận.

## 17. Adapter JavaMailSender với cách phân loại thận trọng

Ví dụ dưới đây sử dụng MIME multipart khi có HTML và plain text alternative. Nó minh họa chính sách bảo thủ: **send trả về bình thường → ACCEPTED**, lỗi SMTP không đủ chứng cứ → UNKNOWN.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SpringMailTransport implements MailTransport {

    private final JavaMailSender sender;
    private final SenderProfileResolver senderProfiles;

    public SpringMailTransport(
            JavaMailSender sender,
            SenderProfileResolver senderProfiles
    ) {
        this.sender = sender;
        this.senderProfiles = senderProfiles;
    }

    @Override
    public SubmissionResult submit(ClaimedMailJob job) {
        final MimeMessage mime = sender.createMimeMessage();

        try {
            String from = senderProfiles.verifiedFrom(
                    job.senderProfile(), job.tenantId()
            );

            boolean withHtml = job.htmlBody() != null
                    && !job.htmlBody().isBlank();

            MimeMessageHelper helper = new MimeMessageHelper(
                    mime, withHtml, "UTF-8"
            );
            helper.setFrom(from);
            helper.setTo(job.recipient());
            helper.setSubject(job.subject());

            if (withHtml) {
                helper.setText(
                        job.plainBody(), job.htmlBody()
                );
            } else {
                helper.setText(job.plainBody());
            }
        } catch (MessagingException | IllegalArgumentException e) {
            // Lỗi compose xác định trước khi gọi SMTP.
            return new SubmissionResult(
                    SubmissionKind.PERMANENT_NOT_ACCEPTED,
                    null,
                    "MAIL_COMPOSITION_FAILED",
                    "Invalid mail payload"
            );
        }

        try {
            sender.send(mime);

            // SMTP transport không bảo đảm ID do provider cấp.
            return SubmissionResult.accepted(null);

        } catch (MailAuthenticationException e) {
            return new SubmissionResult(
                    SubmissionKind.PERMANENT_NOT_ACCEPTED,
                    null,
                    "SMTP_AUTH_CONFIGURATION",
                    "SMTP credentials/configuration must be reviewed"
            );
        } catch (MailException e) {
            // Không giả định mọi MailException nghĩa là chưa accepted.
            return SubmissionResult.unknown(
                    "SMTP_OUTCOME_AMBIGUOUS"
            );
        }
    }
}

public interface SenderProfileResolver {
    String verifiedFrom(String profile, String tenantId);
}
~~~

### Vì sao không tự động retry MailException?

**MailSendException** có thể bao gồm một hoặc nhiều nguyên nhân, thậm chí partial failures khi gửi cho nhiều recipients. Nếu không biết SMTP stage và acceptance outcome, việc cho tất cả vào RETRY_WAIT có nguy cơ trùng. Ví dụ chọn UNKNOWN để bảo toàn an toàn; production có thể xây classifier provider-specific và thêm paths **RETRYABLE_NOT_ACCEPTED** khi có chứng cứ.

### Lỗi authentication là vấn đề toàn provider

Ví dụ đưa một job vào permanent/quarantine là hợp lý để không retry vô hạn, nhưng nếu toàn bộ SMTP credentials vừa hết hạn, **không nên đẩy hàng trăm nghìn jobs vào DLQ trong vài phút**. Cần circuit breaker/provider-pause và alert, giữ những jobs còn lại trong trạng thái chưa-attempt cho tới khi cấu hình được sửa.

### Verified From không được lấy từ input tự do

**SenderProfileResolver** phải ánh xạ senderProfile/tenant tới địa chỉ đã được cấu hình và xác minh. Không dùng field From do người dùng chưa được ủy quyền nhập để gửi dưới danh nghĩa tenant khác.

### Hạn chế của adapter minh họa

Code trên chưa thực hiện quota limiting, template registry, attachment streaming, delivery webhooks, SPF/DKIM/DMARC setup hoặc recipient suppression. Những bước đó thuộc các service riêng trước/ngoài transport; **không nên đưa tất cả business logic vào JavaMailSender adapter**.

## 18. Preparation stage: validation trước khi tiêu attempt

Một worker production có thể xác nhận:

1. Recipient đã được validate và còn eligible.
2. Tenant/purpose được phép gửi tới recipient.
3. Sender profile tồn tại và được verified.
4. Plain/HTML có nội dung theo template policy.
5. Subject không chứa CR/LF injection.
6. Attachments có loại/kích thước phù hợp provider quota.
7. Notification chưa hết thời hạn hoặc bị hủy.
8. Template revision/model snapshot đã được pin và hợp lệ.

### Phân loại validation failures

~~~text
PERMANENT_INVALID_RECIPIENT
TENANT_SCOPE_VIOLATION
TEMPLATE_REQUIRED_VARIABLE_MISSING
ATTACHMENT_TOO_LARGE
SUPPRESSED_RECIPIENT
EXPIRED_TOKEN
SENDER_PROFILE_NOT_VERIFIED
~~~

Không nhất thiết mọi lý do đều dẫn tới DLQ: suppressed recipient có thể thành CANCELLED, expired token thành EXPIRED, còn template model lỗi cần review. Điều quan trọng là **không gọi SMTP để phát hiện một lỗi deterministic có thể kiểm tra trước đó**.

### Không render lại dữ liệu nghiệp vụ tùy ý ở mỗi retry

Ví dụ hóa đơn đã chốt với tổng tiền 250.000 VND. Nếu worker retry hôm sau và lấy **latest order total**, email có thể dùng giá mới. Nên pin model snapshot hoặc rendered content theo policy, và giữ cùng template revision trong một logical notification.

## 19. Exponential backoff và jitter

Một worker không nên retry ngay lập tức sau mỗi lỗi, đặc biệt khi provider bị throttling. Backoff có thể tính:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó:

- \(d_0\) là khoảng chờ ban đầu.
- \(d_{\max}\) là khoảng chờ tối đa.
- \(n\) là số thứ tự attempt đã thất bại.

**Jitter** làm lệch thời điểm retry của các jobs để tránh cùng thức dậy gây spike.

| Attempt vừa thất bại | Delay cơ sở (d0 = 10s) | Khoảng 50–100% jitter |
| --- | --- | --- |
| 1 | 10 giây | 5–10 giây |
| 2 | 20 giây | 10–20 giây |
| 3 | 40 giây | 20–40 giây |
| 4 | 80 giây | 40–80 giây |
| 5 | 160 giây | 80–160 giây |

Các khoảng trên chỉ để giải thích thuật toán; OTP và email có hạn dùng ngắn cần deadline policy riêng, không bắt buộc theo schedule này.

### Vì sao không retry cùng lúc?

Giả sử provider lỗi trong 2 phút và 100.000 jobs dùng:

~~~text
Fixed retry every 30 seconds:
  100.000 jobs wake at roughly same time
  -> enormous burst
  -> more throttling and backlog
~~~

Jitter + distributed rate limit giúp giảm đồng bộ hóa giữa các worker, nhưng **không loại bỏ quota bottleneck** nếu tải bình quân vẫn vượt khả năng provider.

## 20. RetryPolicy Java có thể unit test

Tách quyết định retry thành một class không biết SMTP hoặc database:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.function.DoubleSupplier;

public record RetryDecision(
        DeliveryState nextState,
        Instant nextAttemptAt,
        String reasonCode
) {
}

public final class RetryPolicy {

    private final Duration initialDelay;
    private final Duration maxDelay;
    private final DoubleSupplier randomFraction;

    public RetryPolicy(
            Duration initialDelay,
            Duration maxDelay,
            DoubleSupplier randomFraction
    ) {
        if (initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay.compareTo(initialDelay) < 0) {
            throw new IllegalArgumentException("Invalid retry delays");
        }
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
        this.randomFraction = randomFraction;
    }

    public RetryDecision afterRetryableFailure(
            int completedAttempts,
            int maxAttempts,
            Instant now,
            Instant expiresAt
    ) {
        if (completedAttempts >= maxAttempts) {
            return new RetryDecision(
                    DeliveryState.DEAD_LETTER,
                    null,
                    "ATTEMPTS_EXHAUSTED"
            );
        }

        long delay = initialDelay.toMillis();
        long cap = maxDelay.toMillis();

        for (int i = 1; i < completedAttempts; i++) {
            // Nhân 2 an toàn khi đã tới giới hạn.
            delay = delay >= cap / 2
                    ? cap
                    : Math.min(cap, delay * 2);
        }

        double fraction = Math.max(
                0.0, Math.min(1.0, randomFraction.getAsDouble())
        );
        long jittered = Math.max(
                1L, (long) (delay * (0.5 + fraction * 0.5))
        );
        Instant nextAt = now.plusMillis(jittered);

        if (expiresAt != null && !nextAt.isBefore(expiresAt)) {
            return new RetryDecision(
                    DeliveryState.EXPIRED,
                    null,
                    "RETRY_WOULD_EXCEED_DEADLINE"
            );
        }

        return new RetryDecision(
                DeliveryState.RETRY_WAIT,
                nextAt,
                "TRANSIENT_NOT_ACCEPTED"
        );
    }
}
~~~

### Cách khởi tạo trong Spring

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryPolicyConfig {

    @Bean
    RetryPolicy retryPolicy(MailWorkerProperties p) {
        return new RetryPolicy(
                Duration.ofSeconds(p.baseRetrySeconds()),
                Duration.ofSeconds(p.maxRetrySeconds()),
                () -> ThreadLocalRandom.current().nextDouble()
        );
    }
}
~~~

Với unit tests, truyền **() -> 0.0** hoặc **() -> 1.0** để dự đoán delay. Cần validate base/max trên config và tránh giá trị Duration quá lớn gây overflow khi đổi thành milliseconds.

### Số lần thử tối đa

Nếu **max_attempts=5**:

~~~text
Attempt 1: fail -> RETRY_WAIT
Attempt 2: fail -> RETRY_WAIT
Attempt 3: fail -> RETRY_WAIT
Attempt 4: fail -> RETRY_WAIT
Attempt 5: fail -> DEAD_LETTER
~~~

Nếu lỗi xảy ra trước khi gọi SMTP (quá quota, missing template), không tự tăng số lần thử của transport. Nếu outcome UNKNOWN, job không tự chuyển RETRY_WAIT nên không dùng công thức trên để lặp.

## 21. Tôn trọng thời điểm retry từ provider

Một số ESP HTTP APIs trả **429 Too Many Requests** và có thể đưa ra **Retry-After**. SMTP dùng các reply codes riêng, ví dụ 4xx là temporary failure trong một số giai đoạn; không tự xem SMTP 4xx là HTTP 429.

### Quy tắc kết hợp backoff và provider feedback

~~~text
local backoff -> 10 seconds
provider says retry after -> 60 seconds

next_attempt_at = max(local backoff, provider retry time)
~~~

Nhưng nếu notification hết hạn trước 60 giây, phải quyết định **EXPIRED** hoặc chính sách nghiệp vụ khác, không tiếp tục gửi OTP đã hết hiệu lực.

### Provider temporary reply không phải lúc nào cũng an toàn để retry

Cần biết giai đoạn SMTP và số recipients được server chấp nhận. Khi gửi cho nhiều recipients, có thể có **partial recipient acceptance**; retry cả message vô điều kiện có thể khiến một số người nhận trùng. Bài demo nên gửi **một người nhận/logical notification** để giảm mức độ phức tạp.

### Không tăng tốc bằng cách bỏ qua throttling

Nếu provider đang giới hạn 10 recipients/s, cấu hình 100 threads không giải quyết; cần pacing và global limiter. Retry storm vừa gây thêm chi phí vừa có thể làm provider kéo dài thời gian hạn chế.

## 22. Quy tắc ra quyết định sau SubmissionResult

Worker map outcome sang state:

| SubmissionResult | Điều kiện bổ sung | State kế tiếp |
| --- | --- | --- |
| **ACCEPTED** | Response accepted hợp lệ | ACCEPTED |
| **RETRYABLE_NOT_ACCEPTED** | Attempts còn, deadline đủ | RETRY_WAIT |
| **RETRYABLE_NOT_ACCEPTED** | Đã đạt max_attempts | DEAD_LETTER |
| **RETRYABLE_NOT_ACCEPTED** | Retry sẽ quá hạn | EXPIRED |
| **PERMANENT_NOT_ACCEPTED** | Data/recipient không thể sửa tự động | DEAD_LETTER hoặc CANCELLED theo policy |
| **UNKNOWN** | Không có bằng chứng acceptance/rejection | UNKNOWN |
| **Không được permit** | Chưa beginAttempt | RETRY_WAIT nhưng không tăng attempts |

### Retry không phải catch-all

Không nên:

~~~java
try {
    sender.send(mime);
} catch (Exception e) {
    queue.enqueueAgain(job); // có thể gửi trùng!
}
~~~

### Error classification nên là chính sách riêng

Mã lỗi và mô tả an toàn:

~~~text
SMTP_CONNECT_REFUSED_PRE_DATA
SMTP_TEMPORARY_REJECTION
SMTP_PERMANENT_RECIPIENT_REJECTION
SMTP_AUTH_CONFIG_ERROR
INVALID_TEMPLATE_MODEL
INVALID_RECIPIENT
SMTP_OUTCOME_AMBIGUOUS
WORKER_LEASE_EXPIRED
MAX_ATTEMPTS_EXCEEDED
EXPIRED_NOTIFICATION
~~~

Không lưu nguyên exception stack trace chứa recipient/SMTP credentials vào **last_error_summary**. Log chi tiết ở nơi có phân quyền/retention; database state chỉ cần reason code đủ để ra quyết định.

## 23. Tạo AttemptResolution để finalization nhất quán

~~~java
import java.time.Instant;

public record AttemptResolution(
        DeliveryState targetState,
        Instant nextAttemptAt,
        String providerMessageId,
        String errorCode,
        String safeSummary,
        String deadLetterReason
) {
    public static AttemptResolution accepted(String providerId) {
        return new AttemptResolution(
                DeliveryState.ACCEPTED,
                null,
                providerId,
                null,
                null,
                null
        );
    }

    public static AttemptResolution unknown(String code) {
        return new AttemptResolution(
                DeliveryState.UNKNOWN,
                null,
                null,
                code,
                "Submission requires reconciliation",
                null
        );
    }

    public static AttemptResolution deadLetter(String code) {
        return new AttemptResolution(
                DeliveryState.DEAD_LETTER,
                null,
                null,
                code,
                "Manual review required",
                code
        );
    }
}
~~~

Service ánh xạ:

~~~java
public AttemptResolution resolve(
        SubmissionResult submission,
        ClaimedMailJob job,
        int completedAttempts,
        java.time.Instant now,
        RetryPolicy policy
) {
    return switch (submission.kind()) {
        case ACCEPTED -> AttemptResolution.accepted(
                submission.providerMessageId()
        );
        case UNKNOWN -> AttemptResolution.unknown(
                submission.reasonCode()
        );
        case PERMANENT_NOT_ACCEPTED ->
                AttemptResolution.deadLetter(
                        submission.reasonCode()
                );
        case RETRYABLE_NOT_ACCEPTED -> {
            RetryDecision d = policy.afterRetryableFailure(
                    completedAttempts,
                    job.maxAttempts(),
                    now,
                    job.expiresAt()
            );

            yield new AttemptResolution(
                    d.nextState(),
                    d.nextAttemptAt(),
                    null,
                    d.reasonCode(),
                    "Retry policy applied",
                    d.nextState() == DeliveryState.DEAD_LETTER
                            ? d.reasonCode()
                            : null
            );
        }
    };
}
~~~

Phương thức **resolve(...)** minh họa một function của application service; không phải API Spring. **completedAttempts** phải được lấy từ **beginAttempt** sau increment, không dùng số attempts cũ từ snapshot claim nếu không sẽ lệch giới hạn.

### Khi result mapping là EXPIRED

Nếu retry time lớn hơn deadline, chuyển EXPIRED và ghi lý do rõ. Một email OTP đã hết hạn không nên được đưa vào DLQ chỉ để operator bấm replay token cũ; người dùng nên có flow tạo token mới.

## 24. DeliveryWorker: nối claim, quota, transport và state

Để giữ rõ ranh giới, worker cần bốn nhóm dependencies:

- **MailJobStore**: claim, beginAttempt, release và finish với token.
- **PreflightValidator**: kiểm tra nội dung, recipient, purpose, expiry.
- **MailPermitGate**: nhận quyền attempt theo rate/quota.
- **MailTransport**: submit SMTP.
- **RetryPolicy / resolver**: quyết định state sau kết quả.

Các interface bổ sung:

~~~java
import java.time.Instant;

public enum PreflightOutcome {
    ELIGIBLE,
    PERMANENT_INVALID,
    CANCELLED_BY_POLICY,
    EXPIRED
}

public record PreflightDecision(
        PreflightOutcome outcome,
        String reasonCode
) {
}

public interface PreflightValidator {
    PreflightDecision check(
            ClaimedMailJob job,
            Instant now
    );
}

public record PermitResult(
        boolean allowed,
        Instant nextEligibleAt,
        String reason
) {
}

public interface MailPermitGate {
    PermitResult tryAcquire(ClaimedMailJob job);
}
~~~

### Worker không tự retry trong vòng lặp sleep

Worker nên **xử lý một job đến khi ghi trạng thái kết quả**, sau đó trả về. Nếu cần retry, next_attempt_at sẽ quyết định lần sau job xuất hiện trong query claim.

### Ví dụ service

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public final class DeliveryWorker {

    private final MailJobStore jobs;
    private final MailPermitGate permits;
    private final PreflightValidator preflight;
    private final MailTransport transport;
    private final RetryPolicy retryPolicy;
    private final Clock clock;

    public DeliveryWorker(
            MailJobStore jobs,
            MailPermitGate permits,
            PreflightValidator preflight,
            MailTransport transport,
            RetryPolicy retryPolicy,
            Clock clock
    ) {
        this.jobs = jobs;
        this.permits = permits;
        this.preflight = preflight;
        this.transport = transport;
        this.retryPolicy = retryPolicy;
        this.clock = clock;
    }

    public boolean processOne(
            String workerId,
            Duration lease
    ) {
        Optional<ClaimedMailJob> selected =
                jobs.claimNext(
                        workerId,
                        clock.instant(),
                        lease
                );

        if (selected.isEmpty()) {
            return false;
        }

        ClaimedMailJob job = selected.get();
        Instant now = clock.instant();

        PreflightDecision check = preflight.check(job, now);
        if (check.outcome() != PreflightOutcome.ELIGIBLE) {
            jobs.finishWithoutAttempt(
                    job,
                    mapPreflight(check),
                    now
            );
            return true;
        }

        PermitResult permit = permits.tryAcquire(job);
        if (!permit.allowed()) {
            Instant next = permit.nextEligibleAt();
            if (next == null) {
                next = now.plusSeconds(30);
            }
            jobs.releaseWithoutAttempt(
                    job, next, permit.reason()
            );
            return true;
        }

        UUID attemptId = jobs.beginAttempt(
                job, "primary-smtp", now
        );
        int completedAttempts = job.attemptCount() + 1;

        SubmissionResult submitted;
        try {
            submitted = transport.submit(job);
        } catch (RuntimeException e) {
            // Không thể biết side effect đã xảy ra
            // nếu transport bất ngờ ném exception.
            submitted = SubmissionResult.unknown(
                    "TRANSPORT_UNEXPECTED_FAILURE"
            );
        }

        AttemptResolution resolution = resolveOutcome(
                submitted,
                job,
                completedAttempts,
                clock.instant()
        );

        jobs.finishAttempt(
                job,
                attemptId,
                resolution,
                clock.instant()
        );

        return true;
    }

    private AttemptResolution mapPreflight(
            PreflightDecision check
    ) {
        return switch (check.outcome()) {
            case PERMANENT_INVALID ->
                    AttemptResolution.deadLetter(
                            check.reasonCode()
                    );
            case CANCELLED_BY_POLICY ->
                    new AttemptResolution(
                            DeliveryState.CANCELLED,
                            null, null,
                            check.reasonCode(),
                            "Notification cancelled by policy",
                            null
                    );
            case EXPIRED ->
                    new AttemptResolution(
                            DeliveryState.EXPIRED,
                            null, null,
                            check.reasonCode(),
                            "Notification expired",
                            null
                    );
            case ELIGIBLE -> throw new IllegalStateException(
                    "Eligible preflight cannot be finalized"
            );
        };
    }

    private AttemptResolution resolveOutcome(
            SubmissionResult result,
            ClaimedMailJob job,
            int completedAttempts,
            Instant now
    ) {
        return switch (result.kind()) {
            case ACCEPTED ->
                    AttemptResolution.accepted(
                            result.providerMessageId()
                    );
            case UNKNOWN ->
                    AttemptResolution.unknown(
                            result.reasonCode()
                    );
            case PERMANENT_NOT_ACCEPTED ->
                    AttemptResolution.deadLetter(
                            result.reasonCode()
                    );
            case RETRYABLE_NOT_ACCEPTED -> {
                RetryDecision next =
                        retryPolicy.afterRetryableFailure(
                                completedAttempts,
                                job.maxAttempts(),
                                now,
                                job.expiresAt()
                        );
                yield new AttemptResolution(
                        next.nextState(),
                        next.nextAttemptAt(),
                        null,
                        next.reasonCode(),
                        "Transient send failure",
                        next.nextState() == DeliveryState.DEAD_LETTER
                                ? next.reasonCode()
                                : null
                );
            }
        };
    }
}
~~~

**Lưu ý phạm vi code:** **MailJobStore.finishWithoutAttempt(...)** được dùng thêm cho preflight và cần được khai báo/triển khai trong interface repository ở phần 15 (bổ sung method với job, resolution, now). **beginAttempt** ở ví dụ này trả UUID attemptId, còn attempt count mới được lấy bằng job.attemptCount()+1 theo giả định **một claim có tối đa một beginAttempt** và repository dùng phép tăng atomic đã mô tả. Ở production, nên trả luôn **AttemptStarted(attemptId, attemptNumber)** từ database để tránh lệ thuộc vào snapshot trong bộ nhớ.

### Worker cần xử lý lỗi ghi database

Nếu **finishAttempt** không ghi được kết quả sau khi SMTP accepted, không được chạy lại transport trong cùng method chỉ vì DB lỗi. Recovery sẽ thấy expired IN_FLIGHT/STARTED và xử lý theo UNKNOWN. Database failure cần retry **persisting result** khi còn lease hợp lệ, có giới hạn/telemetry; không phát sinh một email mới.

### Permit gate phải là quota phân tán nếu nhiều replicas

Một **Semaphore** trên từng JVM chỉ giới hạn local concurrency, không hạn chế aggregate rate của 10 pods cùng dùng một SMTP account. Hãy dùng distributed limiter hoặc quota allocator khi provider quota áp chung.

### Worker phải trả job sau quota denial

Trong đoạn minh họa, **releaseWithoutAttempt** ghi RETRY_WAIT + nextAt rồi bỏ lease. Nó không tăng attempts; điều này giúp email không chết chỉ vì chờ đến window quota tiếp theo.

## 25. Bổ sung hoàn chỉnh contract MailJobStore

Trong dự án thật, interface nên gom các thao tác cùng tên:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface MailJobStore {

    Optional<ClaimedMailJob> claimNext(
            String workerId,
            Instant now,
            Duration lease
    );

    UUID beginAttempt(
            ClaimedMailJob job,
            String provider,
            Instant now
    );

    void releaseWithoutAttempt(
            ClaimedMailJob job,
            Instant nextAt,
            String reason
    );

    void finishWithoutAttempt(
            ClaimedMailJob job,
            AttemptResolution resolution,
            Instant now
    );

    void finishAttempt(
            ClaimedMailJob job,
            UUID attemptId,
            AttemptResolution resolution,
            Instant now
    );

    int quarantineExpiredLeases(Instant now);

    int expireUnsentJobs(Instant now);
}
~~~

Interface này là hợp đồng đầy đủ hơn so với bản rút gọn ở phần 15. Khi chép code vào một project Java, chỉ giữ **một định nghĩa MailJobStore**; các đoạn trước được trình bày tuần tự để giải thích từng bước, không phải nhiều file interface trùng tên.

### Quy tắc triển khai chung

Mỗi method phải xác minh **job.id + lease_token + state** trong câu UPDATE. Nếu kết quả là zero rows, không âm thầm xem là thành công; tạo lỗi **STALE_LEASE**/conflict để điều tra. Tránh nhận recipient, body, state hoặc lease token từ input API của người dùng khi thực hiện chuyển trạng thái.

### Begin attempt và finish phải có transaction

Một method cập nhật mail_outbox và mail_attempt phải commit/rollback cùng nhau. Nếu UPDATE outbox thành công nhưng INSERT/UPDATE attempt thất bại, transaction phải rollback.

## 26. Scheduler giới hạn lượng công việc mỗi lần poll

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailWorkerScheduler {

    private final DeliveryWorker worker;
    private final MailWorkerProperties properties;

    public MailWorkerScheduler(
            DeliveryWorker worker,
            MailWorkerProperties properties
    ) {
        this.worker = worker;
        this.properties = properties;
    }

    @Scheduled(fixedDelay = 1000)
    public void tick() {
        if (!properties.enabled()) {
            return;
        }

        int limit = Math.max(
                1, properties.maxJobsPerPoll()
        );
        String workerId = "mail-node-1";

        for (int i = 0; i < limit; i++) {
            boolean found = worker.processOne(
                    workerId, properties.lease()
            );
            if (!found) {
                return;
            }
        }
    }
}
~~~

**workerId** trong ví dụ là placeholder. Production cần một ID riêng theo instance/process/replica, không dùng cùng hard-coded string cho nhiều nodes. **fixedDelay = 1000** chỉ là ví dụ; muốn lấy từ application properties có thể dùng fixedDelayString và property expression được cấu hình đúng.

### Đừng chạy nhiều SMTP attempts trong một transaction scheduler

Không annotate tick() là **@Transactional**. Mỗi claim, begin và finalize dùng transaction DB ngắn; SMTP I/O ở ngoài. Nếu sender chậm, scheduler run có thể lâu, nhưng không được giữ DB lock trong toàn bộ tick.

### Parallelism

Scheduler trên chỉ xử lý tối đa N jobs **tuần tự** mỗi tick. Khi muốn parallelism, thêm một bounded executor và giới hạn số attempts đồng thời; nhưng chỉ claim job khi đã có năng lực thực thi, tránh claim 500 jobs rồi để chúng ngồi chờ cho tới khi hết lease.

### Rate và concurrency là hai giới hạn riêng

Giới hạn 8 worker threads không có nghĩa tối đa 8 emails/s, còn token bucket 10 recipients/s không giới hạn số I/O đang mở. Provider có thể giới hạn cả connections và rate; cần phối hợp hai cơ chế.

## 27. Tại sao cần lease và heartbeat?

Một worker có thể crash hoặc bị kill giữa lúc SMTP I/O:

~~~text
10:00:00 Worker A claims job, lease_until=10:00:45
10:00:02 A records attempt STARTED
10:00:03 A starts SMTP DATA
10:00:10 JVM/process crashes
10:00:45 Lease expires
~~~

Nếu job bị bỏ mãi ở IN_FLIGHT, hệ thống mất khả năng theo dõi. Nhưng nếu chuyển thẳng sang PENDING rồi gửi, rất có thể gửi trùng nếu server đã accepted trước crash.

### Cách xử lý an toàn

**Lease expired → UNKNOWN**. Một reconciliation service/operator xem provider logs và attempt record trước khi quyết định cho retry.

### Heartbeat/lease extension

Với những operations dài (attachments lớn, provider timeout cao), có thể gia hạn lease:

~~~sql
UPDATE mail_outbox
SET lease_until = :newLeaseUntil,
    updated_at = :now
WHERE id = :notificationId
  AND state = 'IN_FLIGHT'
  AND lease_token = :leaseToken
  AND lease_until > :now;
~~~

Heartbeat không biến SMTP thành transaction exactly-once. Nếu worker chết sau provider accepted, vẫn có UNKNOWN. Nhưng heartbeat giúp tránh lease timeout giả khi worker còn sống và đang tiến hành một attempt hợp lệ.

### Không hồi sinh lease đã hết bằng cách đơn giản

Nếu lease đã hết và recovery đổi job sang UNKNOWN, worker cũ không nên update lease lại chỉ vì vẫn đang chạy. Điều kiện **state='IN_FLIGHT' AND lease_token đúng AND lease_until>now** ngăn hành vi này.

## 28. Recovery job IN_FLIGHT quá hạn

Một scheduled recovery job kiểm tra:

~~~sql
UPDATE mail_outbox
SET state = 'UNKNOWN',
    last_error_code = 'WORKER_LEASE_EXPIRED',
    last_error_summary =
        'Attempt outcome unknown after lease expiry',
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE state = 'IN_FLIGHT'
  AND lease_until <= :now
RETURNING id, lease_token;
~~~

Ở ví dụ, **lease_token được giữ lại trên hàng UNKNOWN** để đối chiếu attempt history; worker cũ không thể finalize vì điều kiện yêu cầu state IN_FLIGHT. Khi replay/reconcile, transition service có thể xóa/thay token trong một transaction mới có audit.

### Ghi attempt outcome cùng recovery

Sau khi xác định jobs đổi sang UNKNOWN, cập nhật những attempts còn STARTED có cùng notificationId/leaseToken thành:

~~~text
outcome = UNKNOWN_LEASE_EXPIRED
finished_at = recovery time
error_code = WORKER_LEASE_EXPIRED
~~~

Tốt nhất chạy update outbox + attempt cùng **một transaction**, dựa trên danh sách rows trả về hoặc một CTE thích hợp. Đừng chỉ update outbox rồi để các attempts STARTED tồn tại vĩnh viễn mà không có runbook đối soát.

### Recovery cần xử lý crash trước beginAttempt

Một job có thể IN_FLIGHT nhưng chưa có attempt record vì worker chết trước beginAttempt. Khi đó **có thể** chứng minh app chưa submit nếu luồng thực thi bảo đảm không có đường gửi trước beginAttempt. Tuy nhiên để đơn giản và an toàn, bản demo đưa expired IN_FLIGHT sang UNKNOWN rồi đánh dấu **NO_ATTEMPT_RECORDED**, cho operator/reconciliation service quyết định có thể đưa về PENDING hay không.

### Hai scheduler recovery có chạy đồng thời được không?

Có thể nếu câu UPDATE có điều kiện state IN_FLIGHT và transaction được kiểm soát. Một job chỉ được chuyển state bởi một transaction; các callbacks về sau phải dùng optimistic locking/fencing để không double transition.

## 29. Housekeeping: expired jobs và retry budget

Không chỉ xử lý leases quá hạn, phải quét jobs hết business deadline:

~~~sql
UPDATE mail_outbox
SET state = 'EXPIRED',
    last_error_code = 'NOTIFICATION_EXPIRED',
    updated_at = :now
WHERE state IN ('PENDING', 'RETRY_WAIT')
  AND expires_at IS NOT NULL
  AND expires_at <= :now;
~~~

### Tại sao không đánh dấu IN_FLIGHT là EXPIRED ngay?

Một IN_FLIGHT có thể đã gửi trước expiry và chỉ đang chờ SMTP response. Nếu tự đổi thành EXPIRED, worker không thể cập nhật acceptance và state trở nên mơ hồ. Với jobs đã bắt đầu attempt, cần chờ kết quả hoặc đưa UNKNOWN sau lease timeout; không dùng deadline để suy luận server chưa accepted.

### Jobs đạt max_attempts mà còn RETRY_WAIT

Do bug/crash hoặc migration, có thể có row RETRY_WAIT với attempt_count >= max_attempts. Housekeeping nên chuyển nó sang DEAD_LETTER với reason **ATTEMPTS_EXHAUSTED**, không bỏ lại vì claim query sẽ luôn loại.

### Housekeeping không tự xóa dữ liệu

EXPIRED và DEAD_LETTER là trạng thái cần audit. Việc archive/purge histories thuộc retention policy, không phải hoạt động mặc định của retry worker.

## 30. Dead letter là gì trong dự án này?

Trong hệ thống dùng broker, **dead-letter queue (DLQ)** thường là một queue/topic chứa messages không xử lý được theo policy. Trong dự án dùng PostgreSQL, ta chọn cách đơn giản hơn: **mail_outbox.state = DEAD_LETTER** cùng reason, timestamps, attempt history và audit.

Hai mô hình có chung mục tiêu:

- Giữ lại notification thất bại thay vì drop im lặng.
- Phân loại lý do thất bại.
- Không retry vô hạn một lỗi deterministic.
- Có thể review, sửa dữ liệu/cấu hình và quyết định replay.
- Giữ được lịch sử đã thử và evidence của provider.

### Những trường hợp đi vào dead letter

| Lý do | Ví dụ | Có nên replay tự động? |
| --- | --- | --- |
| **MAX_ATTEMPTS_EXHAUSTED** | Đã có N transient failures được chứng minh | Không, cần review/điều chỉnh |
| **INVALID_RECIPIENT** | Địa chỉ email sai và được xác định chắc | Không, trừ khi sửa recipient hợp lệ |
| **TEMPLATE_MODEL_INVALID** | Biến bắt buộc thiếu | Không, cần sửa producer/template |
| **SENDER_PROFILE_INVALID** | From không được verify | Không, cần sửa cấu hình |
| **ATTACHMENT_POLICY_VIOLATION** | Tệp quá lớn/bị chặn | Không, cần thay nội dung theo policy |
| **UNKNOWN_UNRESOLVED** | Không đối soát được attempt mơ hồ | Không tự động; nguy cơ gửi trùng |
| **TENANT_POLICY_REJECTION** | Tenant không được gửi loại email đó | Không, cần quyền/phê duyệt |

### Khi nào không nên dead letter?

**NO_PERMIT vì quota đang hết** thường dẫn đến chờ lịch/quota mới, không nên tiêu hết max_attempts và vào DLQ ngay. **OTP hết hạn** phù hợp EXPIRED hơn, vì replay một OTP đã chết không có ích. **Suppression/opt-out** thường là CANCELLED/SUPPRESSED, không phải một technical failure cần khắc phục.

### DLQ không phải cơ chế xóa

Một record DEAD_LETTER vẫn có thể chứa recipient, body, link hoặc tài liệu nhạy cảm. Phải có RBAC, encryption, retention và công cụ redact. Không phát dead-letter payload thô lên một dashboard công khai.

## 31. Dead-letter record và metadata để điều tra

Để operator hiểu vấn đề, một record cần đủ thông tin:

~~~text
notification_id
tenant_id
business_key / purpose
recipient_ref (redacted in UI)
state = DEAD_LETTER
dead_letter_reason
attempt_count / max_attempts
first_created_at
last_attempt_at
last_error_code
last_provider
provider_message_id, if any
template_revision, if applicable
safe payload hash / content version
~~~

Thông tin chi tiết hơn nằm trong **mail_attempt**. Ví dụ:

| Attempt | Thời điểm | Provider | Outcome | Code |
| --- | --- | --- | --- | --- |
| 1 | 10:00 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 2 | 10:01 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 3 | 10:03 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 4 | 10:07 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 5 | 10:15 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |

Sau attempt 5, **DEAD_LETTER / ATTEMPTS_EXHAUSTED**. Nhìn lịch sử này sẽ thấy vấn đề là throttling hoặc provider reject liên tục, khác hẳn địa chỉ nhận sai.

### Đừng nhét stack trace đầy đủ vào DB

Stack traces và raw SMTP diagnostics có thể chứa địa chỉ, hostname nội bộ, credentials hoặc nội dung message. Có thể lưu **errorCode + sanitized summary + opaque trace reference**; nếu cần logs chi tiết, dùng nơi có bảo vệ và TTL.

## 32. Truy vấn danh sách dead letter để xử lý

~~~sql
SELECT
    id,
    tenant_id,
    business_key,
    dead_letter_reason,
    attempt_count,
    max_attempts,
    last_error_code,
    updated_at
FROM mail_outbox
WHERE state = 'DEAD_LETTER'
ORDER BY updated_at ASC
LIMIT 100;
~~~

Đây là query cho trang operator có pagination. **Không trả plain_body, html_body hoặc recipient_address đầy đủ** cho mọi nhân viên theo mặc định.

### Tính toán nhóm lỗi

~~~sql
SELECT
    dead_letter_reason,
    COUNT(*) AS jobs
FROM mail_outbox
WHERE state = 'DEAD_LETTER'
GROUP BY dead_letter_reason
ORDER BY jobs DESC;
~~~

Nếu nhiều jobs đột ngột vào DEAD_LETTER với **SMTP_AUTH_CONFIGURATION**, có thể là sự cố chung của account; không nên replay từng job khi credentials vẫn sai.

### Dùng dashboard để biết tuổi DLQ

Một dead-letter backlog đã kéo dài ba tuần khác một job vừa thất bại. Cần thêm **oldest dead-letter age** và phân nhóm theo purpose/provider/tenant khi triển khai metrics, nhưng tránh cardinality cao bằng recipient IDs.

## 33. Chính sách replay: không chỉ đặt lại PENDING

Một nút “Replay all dead letters” không có kiểm soát có thể gây gửi trùng, vi phạm consent hoặc tạo retry storm.

### Điều kiện trước replay

1. Actor được authentication/authorization theo tenant và purpose.
2. Biết **reason** và nguyên nhân đã được xử lý.
3. Kiểm tra job không **ACCEPTED** và không còn UNKNOWN chưa đối soát.
4. Kiểm tra recipient hiện vẫn eligible, consent/suppression.
5. Kiểm tra deadline và token/link còn hiệu lực.
6. Đảm bảo content/template model đúng, không chứa URL đã bị revoke.
7. Xác định replay cùng payload hay cần tạo notification mới.
8. Chọn batch size, rate/quota budget và lịch replay.
9. Ghi audit với operator, reason, previous attempts.

### Replay cùng notification ID

Với job DEAD_LETTER do **proven failures trước acceptance**, nếu payload không đổi, có thể:

- Giữ **notificationId** và **businessKey**.
- Giữ toàn bộ **mail_attempt** history.
- **Không reset attempt_count về 0**.
- Tăng **max_attempts** có kiểm soát, ví dụ từ 5 lên 7.
- Đưa state về PENDING và next_attempt_at có lịch.
- Ghi audit về số lần thử được cấp thêm.

Lý do: bảng **mail_attempt UNIQUE(notification_id, attempt_number)** sẽ bị xung đột nếu reset về 0; giữ attempt numbering tăng giúp history nhất quán.

### Replay thay đổi payload/recipient

Nếu phải sửa địa chỉ, đổi nội dung hóa đơn hoặc tạo link/token mới, đây có thể là **notification mới**. Có thể thêm cột **replay_of_notification_id**/correlation đến bản cũ và tạo new ID + business key có nghĩa. Không sửa một notification đã accepted và ghi đè nội dung như thể nó luôn đúng.

### SQL replay minh họa

~~~sql
UPDATE mail_outbox
SET state = 'PENDING',
    max_attempts = :newMaxAttempts,
    next_attempt_at = :scheduledAt,
    dead_letter_reason = NULL,
    last_error_code = NULL,
    last_error_summary = NULL,
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE id = :notificationId
  AND state = 'DEAD_LETTER'
  AND attempt_count < :newMaxAttempts
  AND (expires_at IS NULL OR expires_at > :now);
~~~

**Đây là SQL minh họa dưới transaction điều phối**, không phải API mở cho người dùng chạy. Chỉ thực hiện nếu job đã được review, reason hợp lệ, template/recipient policy đã được xác nhận và audit được insert **trong cùng transaction**. Đếm affected rows = 1 để tránh replay hai lần do double-click.

### Vì sao không replay UNKNOWN bằng SQL này?

Điều kiện bắt đầu là **state='DEAD_LETTER'**. Nếu một job UNKNOWN bị operator chuyển thành DEAD_LETTER chỉ để “dọn màn hình”, việc replay vẫn phải kiểm tra lịch sử UNKNOWN. Không cho phép dùng việc đổi nhãn trạng thái để lách chính sách chống gửi trùng.

## 34. Audit khi replay hoặc discard

Một transition quản trị:

~~~text
action: REPLAY
notificationId: ...
oldState: DEAD_LETTER
newState: PENDING
oldMaxAttempts: 5
newMaxAttempts: 7
operator: ops-user-17
reason: SMTP provider recovered and prior errors proven pre-acceptance
time: ...
~~~

Nếu operator quyết định không gửi nữa:

~~~text
action: CANCEL
oldState: DEAD_LETTER
newState: CANCELLED
reason: recipient requested opt-out
~~~

### Audit trong cùng transaction

Khi đổi trạng thái:

~~~sql
INSERT INTO mail_dead_letter_audit (
    id, notification_id,
    action, from_state, to_state,
    operator_id, reason
)
VALUES (
    :auditId, :notificationId,
    :action, :fromState, :toState,
    :operator, :reason
);
~~~

Nếu update state thành công nhưng audit insert thất bại, **rollback toàn transaction**. Không cho một thao tác đặc quyền được lưu nhưng không còn dấu vết.

### Bulk replay cần giới hạn

Với 10.000 dead letters, không thực hiện 10.000 UPDATE→PENDING và lập tức mở 10.000 SMTP connections. Có thể xếp replay vào các time windows, dùng scheduler/limiter chung, theo dõi batch progress và cơ chế dừng.

### Idempotency của thao tác replay

Một request replay có thể bị client retry. Dùng operator action ID/request idempotency key hoặc state compare-and-set. Nếu cùng action được nhận hai lần, chỉ thực thi một transition và không cấp thêm retry budget hai lần.

## 35. UNKNOWN: nơi khó nhất của retry worker

**UNKNOWN** khác **RETRY_WAIT**: có thể server đã accepted email.

~~~text
SMTP session
    |
    +-- MAIL FROM accepted
    +-- RCPT TO accepted
    +-- DATA accepted, body transferred
    +-- server commits message
    '-- response lost before client receives it
                 |
                 v
              UNKNOWN
~~~

Nếu worker retry như thể chưa gửi, người nhận có thể nhận hai bản giống nhau. Vấn đề không được giải quyết bằng việc giữ cùng **Message-ID**; SMTP không bảo đảm dedup theo header này.

### Reconciliation workflow

~~~text
UNKNOWN job
    |
    v
Check provider request/message ID if available
    |
    +-- Confirmed accepted ------> ACCEPTED
    |
    +-- Proven not accepted -----> Controlled retry
    |
    '-- Cannot determine --------> Manual risk decision
                                     |
                        +------------+-----------+
                        |                        |
                        v                        v
                     Hold / close          Explicit resend
                     with audit            accepting dup risk
~~~

### Với SMTP thuần có giới hạn thông tin

SMTP sender có thể không có provider query API để hỏi server đã accepted chưa. Khi không có chứng cứ, cần quyết định theo business importance và khả năng người nhận bị ảnh hưởng. Ví dụ một báo cáo nội bộ có thể chấp nhận nguy cơ trùng có kiểm soát, trong khi email tạo hóa đơn/mã đăng nhập cần chính sách chặt chẽ hơn.

### Message-ID chỉ để correlation

Ghi Message-ID vào attempts có thể hữu ích khi tìm mail logs, nhưng không dùng nó như idempotency token bảo đảm. Trong trường hợp provider hỗ trợ idempotency API riêng, dùng đúng semantics, TTL và scope của provider đó.

### UNKNOWN không phải DEAD_LETTER mặc định

Có thể giữ UNKNOWN để điều tra; nếu SLA/quy trình yêu cầu đóng case không xác minh được, chuyển sang DEAD_LETTER với reason **UNKNOWN_UNRESOLVED** nhưng không tự replay. History phải giữ cờ đã từng UNKNOWN.

## 36. Repository transaction cho beginAttempt và finishAttempt

Đoạn Java sau triển khai hai bước quan trọng bằng **NamedParameterJdbcTemplate**, dựa trên bảng ở phần 7. Các method có **@Transactional** và được gọi từ worker qua **Spring bean**, không phải self-invocation.

~~~java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcMailAttemptWriter {

    private final NamedParameterJdbcTemplate jdbc;

    public JdbcMailAttemptWriter(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public StartedAttempt beginAttempt(
            ClaimedMailJob job,
            String provider,
            Instant now
    ) {
        UUID attemptId = UUID.randomUUID();
        String sql = """
            WITH bumped AS (
                UPDATE mail_outbox
                SET attempt_count = attempt_count + 1,
                    updated_at = :now
                WHERE id = :id
                  AND state = 'IN_FLIGHT'
                  AND lease_token = :token
                  AND lease_until > :now
                  AND attempt_count < max_attempts
                RETURNING attempt_count
            )
            INSERT INTO mail_attempt (
                id, notification_id, attempt_number,
                lease_token, provider, started_at, outcome
            )
            SELECT
                :attemptId, :id, bumped.attempt_count,
                :token, :provider, :now, 'STARTED'
            FROM bumped
            RETURNING attempt_number
            """;

        var params = new MapSqlParameterSource()
                .addValue("id", job.id())
                .addValue("token", job.leaseToken())
                .addValue("now", Timestamp.from(now))
                .addValue("provider", provider)
                .addValue("attemptId", attemptId);

        var rows = jdbc.query(
                sql,
                params,
                (rs, rowNum) -> rs.getInt("attempt_number")
        );
        if (rows.size() != 1) {
            throw new IllegalStateException(
                    "Lease lost or retry budget exhausted"
            );
        }

        return new StartedAttempt(
                attemptId, rows.get(0)
        );
    }

    @Transactional
    public void finishAttempt(
            ClaimedMailJob job,
            StartedAttempt attempt,
            AttemptResolution result,
            Instant now
    ) {
        String updateJob = """
            UPDATE mail_outbox
            SET state = :state,
                next_attempt_at = CASE
                    WHEN :state = 'RETRY_WAIT'
                    THEN CAST(:nextAt AS timestamptz)
                    ELSE next_attempt_at
                END,
                provider_message_id = :providerMessageId,
                last_error_code = :errorCode,
                last_error_summary = :summary,
                dead_letter_reason = :deadReason,
                accepted_at = CASE
                    WHEN :state = 'ACCEPTED'
                    THEN :now
                    ELSE accepted_at
                END,
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                updated_at = :now
            WHERE id = :id
              AND state = 'IN_FLIGHT'
              AND lease_token = :token
            """;

        var params = new MapSqlParameterSource()
                .addValue("state", result.targetState().name())
                .addValue("nextAt", result.nextAttemptAt() == null
                        ? null
                        : Timestamp.from(result.nextAttemptAt()))
                .addValue(
                        "providerMessageId",
                        result.providerMessageId()
                )
                .addValue("errorCode", result.errorCode())
                .addValue("summary", result.safeSummary())
                .addValue("deadReason", result.deadLetterReason())
                .addValue("now", Timestamp.from(now))
                .addValue("id", job.id())
                .addValue("token", job.leaseToken())
                .addValue("attemptId", attempt.attemptId());

        int changed = jdbc.update(updateJob, params);
        if (changed != 1) {
            throw new IllegalStateException(
                    "Stale lease: cannot finalize mail attempt"
            );
        }

        String updateHistory = """
            UPDATE mail_attempt
            SET outcome = :state,
                finished_at = :now,
                error_code = :errorCode,
                error_summary = :summary,
                provider_message_id = :providerMessageId
            WHERE id = :attemptId
              AND notification_id = :id
              AND lease_token = :token
              AND outcome = 'STARTED'
            """;

        changed = jdbc.update(updateHistory, params);
        if (changed != 1) {
            throw new IllegalStateException(
                    "Attempt history conflict"
            );
        }
    }
}

public record StartedAttempt(
        UUID attemptId,
        int attemptNumber
) {
}
~~~

### Vì sao trả StartedAttempt thay vì chỉ UUID?

Worker cần biết **attemptNumber thực tế sau transaction**. Nếu code lấy job.attemptCount()+1 từ snapshot cũ trong một thiết kế phức tạp, có nguy cơ lệch số attempt sau migration/recovery. Trả về attemptNumber từ PostgreSQL là chắc chắn hơn.

### Ghép vào worker

Trong một triển khai cuối cùng, **MailJobStore.beginAttempt(...)** có thể được nâng thành:

~~~java
StartedAttempt beginAttempt(
        ClaimedMailJob job,
        String provider,
        Instant now
);
~~~

và worker dùng:

~~~java
StartedAttempt started = jobs.beginAttempt(
        job, "primary-smtp", clock.instant()
);

SubmissionResult submission = transport.submit(job);

AttemptResolution resolution = resolveOutcome(
        submission,
        job,
        started.attemptNumber(),
        clock.instant()
);

jobs.finishAttempt(
        job,
        started,
        resolution,
        clock.instant()
);
~~~

Các excerpts trước của **MailJobStore** trả UUID để dễ giới thiệu. Đây là **biến thể nâng cấp** dùng số attempt từ database; chọn **một kiểu contract thống nhất** khi triển khai, không giữ đồng thời hai method cùng tên khác return type trong Java.

### Lỗi JDBC khi finalize sau SMTP accepted

Nếu DB unavailable sau khi server accepted, **finishAttempt** thất bại. Worker không được gọi transport lần nữa trong catch; nó cần retry **chỉ việc ghi kết quả** khi còn lease hợp lệ, hoặc để recovery đưa job sang UNKNOWN và đối soát. **Không kết luận** vì DB chưa có ACCEPTED nên email chưa được provider nhận.

### Không mở transaction xuyên SMTP

Trong trình tự đúng:

~~~text
Transaction A: claim -> COMMIT
Transaction B: beginAttempt -> COMMIT
No DB transaction: call SMTP
Transaction C: finishAttempt -> COMMIT
~~~

Đây là reason quan trọng nhất khiến hệ thống cần trạng thái và retry policy: không thể commit SMTP đồng thời với database theo cách đơn giản của một transaction JDBC.

## 37. Release claim khi quota không cho phép

Nếu job đã claim nhưng chưa beginAttempt, một limiter có thể nói **WAIT**. Khi đó trả job về RETRY_WAIT mà không tăng số lần thử:

~~~sql
UPDATE mail_outbox
SET state = 'RETRY_WAIT',
    next_attempt_at = :nextAt,
    last_error_code = :reasonCode,
    last_error_summary = 'Waiting for send permit',
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE id = :id
  AND state = 'IN_FLIGHT'
  AND lease_token = :token;
~~~

**Không ghi mail_attempt** vì chưa có attempt thực tế. Operator có thể xem reason_code = QUOTA_WAIT, nhưng đây không phải một technical SMTP failure.

### Permit gate và max_attempts

~~~text
attempt_count=0, state=PENDING
  -> claim -> no permit
attempt_count=0, state=RETRY_WAIT
  -> claim next window -> permit granted
  -> beginAttempt -> attempt_count=1
~~~

Số lần chờ quota không làm job bị DEAD_LETTER khi max_attempts=5.

### Hạn chế cấp permit trước khi claim

Nếu cấp global token trước khi biết job có claim thành công, nhiều workers có thể lấy permits rồi không dùng, làm throughput thấp. Nếu claim trước, cần release claim nhanh khi không có permit. Một scheduler tốt có thể dùng quota capacity để giới hạn số claim và có permit reservation/release semantics rõ ràng.

## 38. Finalize preflight failure không có attempt

Một job có thể bị từ chối **trước SMTP** vì nội dung không hợp lệ:

~~~sql
UPDATE mail_outbox
SET state = :targetState,
    dead_letter_reason = :deadReason,
    last_error_code = :code,
    last_error_summary = :safeSummary,
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE id = :id
  AND state = 'IN_FLIGHT'
  AND lease_token = :token;
~~~

Không tạo **mail_attempt** cho lỗi này. Nếu muốn tracking tất cả processing operations, có thể tạo bảng **mail_processing_event** riêng để phân biệt **validation decision** với **transport attempt**.

### Vì sao phân biệt như vậy?

Một hệ thống đánh dấu mọi validation failure thành SMTP attempt sẽ đưa số liệu attempts/quota/cost sai. Khi điều tra 1.000 dead letters do template bug, số **mail_send_attempts** có thể bằng 0, trong khi số **mail_preflight_failures** bằng 1.000. Phân loại này giúp quyết định sửa template thay vì tăng SMTP quota.

## 39. Trạng thái trong database và dead-letter queue vật lý

Trong một hệ thống lớn, có thể chuyển từ PostgreSQL outbox sang broker:

~~~text
Outbox/CDC
    |
    v
Broker main topic/queue
    |
    v
Mail consumer
    |
    +-- Success -> ack
    +-- Transient -> delayed retry topic/queue
    '-- Permanent -> dead-letter topic/queue
                           |
                           v
                      Operator review
~~~

### DLQ của broker không tự chứa đủ lịch sử

Một RabbitMQ DLX hoặc Kafka DLQ thường chứa message và metadata routing, nhưng không tự cho biết email đã được SMTP accepted hay chưa. Vẫn cần **notificationId, attempt history, submission outcome, idempotency** trong application-level store.

### Retry queue không phải nơi giữ UNKNOWN để auto resend

Nếu một attempt UNKNOWN được publish vào delayed retry topic như một lỗi tạm thời, consumer mới có thể gửi trùng. Hãy phân loại UNKNOWN riêng và chỉ ra khỏi trạng thái này khi có evidence/risk decision.

### Đừng ack trước khi lưu durable result

Nếu consumer nhận job, SMTP accepted, rồi broker message ack nhưng database chưa lưu ACCEPTED, audit có thể sai. Nếu ack quá muộn, broker redeliver có thể gây trùng. Vì SMTP nằm ngoài transaction broker/DB, vẫn cần một flow bảo thủ với durable state/reconciliation; không có thao tác ack đơn giản nào giải quyết exactly-once email.

## 40. Chạy bản thực hành với PostgreSQL và SMTP sink cục bộ

Để không gửi email ra Internet, có thể dùng **PostgreSQL** cùng một SMTP test sink như **Mailpit**. Ví dụ **docker-compose.yml**:

~~~yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: maildemo
      POSTGRES_USER: maildemo
      POSTGRES_PASSWORD: example-local-only
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U maildemo -d maildemo"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - maildemo-pg:/var/lib/postgresql/data

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "3025:1025"
      - "8025:8025"

volumes:
  maildemo-pg:
~~~

Chạy:

~~~bash
docker compose up -d
~~~

Mailpit lắng nghe SMTP tại **localhost:3025**, web UI thử nghiệm tại **http://localhost:8025** theo port mapping minh họa. Địa chỉ này dành cho local development, **không bật open relay/public SMTP sink ra Internet**. Production nên pin image versions/digests và quản lý database credentials/secrets theo policy; không dùng password demo trong production.

### Luồng thực hành

1. Khởi động PostgreSQL và Mailpit.
2. Tạo Spring Boot project với dependencies ở phần 6.
3. Đưa schema ở phần 7 vào migration.
4. Cấu hình datasource/SMTP/scheduler.
5. Triển khai repository, worker và transport theo contracts đã trình bày.
6. Insert một notification hợp lệ.
7. Quan sát state PENDING → IN_FLIGHT → ACCEPTED.
8. Kiểm tra email được lưu trong Mailpit UI.
9. Dừng Mailpit, thử các tình huống lỗi và quan sát UNKNOWN/retry theo classifier.
10. Chạy test concurrency, replay và expired leases trước khi tin worker trong production.

### Chèn một notification đơn giản bằng SQL

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, business_key,
    recipient_address, sender_profile,
    subject, plain_body, html_body,
    state, next_attempt_at, max_attempts
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    'demo-tenant',
    'LAB:WELCOME:customer-7',
    'customer@example.test',
    'demo-verified-profile',
    'Chào mừng',
    'Chào bạn! Đây là email thực hành.',
    '<p>Chào bạn! <strong>Đây là email thực hành.</strong></p>',
    'PENDING',
    CURRENT_TIMESTAMP,
    5
);
~~~

**Chú ý:** **SenderProfileResolver** phải có mapping nội bộ từ demo-verified-profile sang địa chỉ From hợp lệ trong test sink. Dữ liệu recipient example.test chỉ dành cho thử nghiệm; Mailpit không chuyển thư tới recipient thật.

### Xem state

~~~sql
SELECT
    id, state, attempt_count, next_attempt_at,
    last_error_code, dead_letter_reason
FROM mail_outbox
WHERE business_key = 'LAB:WELCOME:customer-7';
~~~

Với SMTP sink hoạt động và worker đầy đủ, state có thể thành ACCEPTED. Khi sink tắt, adapter SpringMailTransport bảo thủ ở phần 17 có thể đưa sang UNKNOWN, không phải RETRY_WAIT, vì adapter chưa chứng minh chính xác lỗi xảy ra trước DATA. Muốn test nhánh retryable, dùng **FakeMailTransport** có outcome được xác định rõ.

## 41. Unit test RetryPolicy

Jitter ngẫu nhiên làm thời điểm retry không cố định. Đó là lý do constructor nhận **DoubleSupplier**, cho phép test deterministic.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class RetryPolicyTest {

    private final Instant now =
            Instant.parse("2026-01-01T00:00:00Z");

    private final RetryPolicy policy = new RetryPolicy(
            Duration.ofSeconds(10),
            Duration.ofMinutes(10),
            () -> 1.0 // full calculated delay
    );

    @Test
    void firstRetryWaitsTenSeconds() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        1, 5, now, null
                );

        assertEquals(
                DeliveryState.RETRY_WAIT,
                decision.nextState()
        );
        assertEquals(
                now.plusSeconds(10),
                decision.nextAttemptAt()
        );
    }

    @Test
    void thirdAttemptUsesFortySecondBackoff() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        3, 5, now, null
                );

        assertEquals(
                now.plusSeconds(40),
                decision.nextAttemptAt()
        );
    }

    @Test
    void maxAttemptsTransitionsToDeadLetter() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        5, 5, now, null
                );

        assertEquals(
                DeliveryState.DEAD_LETTER,
                decision.nextState()
        );
        assertEquals(
                "ATTEMPTS_EXHAUSTED",
                decision.reasonCode()
        );
    }

    @Test
    void retryBeyondDeadlineBecomesExpired() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        2, 5,
                        now,
                        now.plusSeconds(15)
                );

        assertEquals(
                DeliveryState.EXPIRED,
                decision.nextState()
        );
    }
}
~~~

Những test này chỉ đánh giá chính sách thời gian/trạng thái. Chúng không khẳng định SMTP đã gửi hoặc database đã commit. **Có thể test jitter minimum** bằng supplier () -> 0.0 và kiểm tra khoảng 50% delay.

## 42. FakeMailTransport cho test retry và dead letter

Để mô phỏng kết quả đáng tin mà không gọi provider thật, tạo một fake trả outcomes theo thứ tự:

~~~java
import java.util.ArrayDeque;
import java.util.List;
import java.util.Queue;

public final class FakeMailTransport implements MailTransport {

    private final Queue<SubmissionResult> results;
    private int calls;

    public FakeMailTransport(
            List<SubmissionResult> results
    ) {
        this.results = new ArrayDeque<>(results);
    }

    @Override
    public SubmissionResult submit(ClaimedMailJob job) {
        calls++;
        SubmissionResult result = results.poll();
        if (result == null) {
            throw new IllegalStateException(
                    "No fake result configured"
            );
        }
        return result;
    }

    public int calls() {
        return calls;
    }
}
~~~

### Test scenario: 2 failures rồi accepted

~~~text
Fake outcomes:
  RETRYABLE_NOT_ACCEPTED
  RETRYABLE_NOT_ACCEPTED
  ACCEPTED

Expected DB history:
  attempt 1 -> RETRY_WAIT (future nextAttemptAt)
  attempt 2 -> RETRY_WAIT
  attempt 3 -> ACCEPTED

Assertions:
  same notification ID
  three unique attempt IDs
  attempt_count = 3
  no dead-letter row
  no fourth SMTP submission
~~~

### Test scenario: max attempts

~~~text
Fake outcomes:
  5 × RETRYABLE_NOT_ACCEPTED

Expected:
  final state = DEAD_LETTER
  reason = ATTEMPTS_EXHAUSTED
  attempt_count = 5
  no more automatic claims
~~~

### Test scenario: invalid payload

~~~text
Preflight returns PERMANENT_INVALID.

Expected:
  state = DEAD_LETTER
  attempt_count = 0
  fake transport calls = 0
~~~

### Test scenario: no quota

~~~text
Permit gate refuses for 60 seconds.

Expected:
  state = RETRY_WAIT
  next_attempt_at = now + 60 sec
  attempt_count unchanged
  transport calls = 0
~~~

Để chạy các scenarios qua thời gian giả lập, inject **Clock** thay vì gọi **Instant.now()** trực tiếp ở mọi service. Khi thời gian trong test nhảy đến nextAttemptAt, worker mới claim tiếp.

## 43. Integration test PostgreSQL: hai workers không claim cùng job

Một bài test quan trọng là hai consumers cùng đọc:

~~~text
Given:
  DB có 1 PENDING job
  Worker A và Worker B gọi claimNext đồng thời

When:
  Both use FOR UPDATE SKIP LOCKED in one SQL statement

Then:
  Exactly one worker obtains the job
  Other returns empty
  State = IN_FLIGHT
  One lease token exists
~~~

### Test dùng Testcontainers

Có thể chạy PostgreSQL Testcontainer và apply migration thực tế; không dùng H2 để mô phỏng **FOR UPDATE SKIP LOCKED** vì SQL/locking semantics không giống.

Pseudocode:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CountDownLatch start = new CountDownLatch(1);

Callable<Optional<ClaimedMailJob>> claim = () -> {
    start.await();
    return repository.claimNext(
            UUID.randomUUID().toString(),
            fixedClock.instant(),
            Duration.ofSeconds(45)
    );
};

Future<Optional<ClaimedMailJob>> left =
        pool.submit(claim);
Future<Optional<ClaimedMailJob>> right =
        pool.submit(claim);

start.countDown();
var a = left.get();
var b = right.get();

assertEquals(
        1,
        (a.isPresent() ? 1 : 0)
        + (b.isPresent() ? 1 : 0)
);
pool.shutdown();
~~~

Đoạn trên chỉ minh họa phần concurrency của một JUnit test; cần setup repository, database migration, test transaction boundaries, imports, cleanup và timeout trong project test. Chú ý nếu test method chạy dưới một transaction chưa commit của thread khác, worker threads có thể không nhìn thấy seeded row; cần seed và commit trước khi release latch.

### Test nhiều jobs

Với 100 PENDING jobs và 10 workers:

~~~text
Expected:
  each job claimed at most once per active lease
  no duplicate lease token for the same active job
  no DB deadlocks due to claim ordering
  workers can process other jobs while one row is locked
~~~

**SKIP LOCKED** phù hợp để phân phối jobs nhưng không bảo đảm fairness tuyệt đối giữa tenants/purposes. Nếu có nhiều luồng ưu tiên, cần scheduling/budget riêng.

## 44. Fault injection: crash sau SMTP accepted

Đây là test phân biệt một worker an toàn với một retry loop nguy hiểm.

~~~text
1. Worker claims N-101.
2. beginAttempt writes attempt 1 STARTED.
3. Fake provider records email ACCEPTED.
4. Simulate process crash before finishAttempt writes DB.
5. Lease expires.
6. Recovery transitions N-101 to UNKNOWN.
7. Scheduler must not claim N-101 automatically.
8. Operator/provider reconciliation confirms accepted.
9. Record ACCEPTED without sending again.
~~~

Expected:

- **FakeMailTransport call count = 1**.
- Outbox **UNKNOWN** sau lease recovery.
- Job không được chọn bởi query claim PENDING/RETRY_WAIT.
- Sau reconciliation, state ACCEPTED và attempt history ghi đủ evidence.
- Không tạo notificationId mới, không gửi trùng.

### Test đối chứng: crash trước beginAttempt

Nếu worker claim rồi crash trước khi beginAttempt, recovery có thể xác minh không có attempt record và cho phép requeue theo policy được xác thực. Demo bảo thủ có thể vẫn chuyển UNKNOWN; đó là trade-off availability để hạn chế trùng.

### Test database unavailable khi finalize

Nếu server accepted nhưng JDBC update thất bại, worker không được gọi transport lại. Có thể retry transaction ghi outcome khi còn lease; nếu không, UNKNOWN và đối soát. Fake injection nên xác nhận số submission không tăng.

### Test hai workers và lease hết hạn

Worker A bắt đầu SMTP rất chậm, lease hết; recovery chuyển UNKNOWN. Worker B không được claim job đó lại tự động. Nếu A sau đó nhận accepted, finalization bằng stale token/state không được ghi đè UNKNOWN; operator/reconciler mới cập nhật có audit.

## 45. Monitoring: đo trạng thái thay vì chỉ đếm send()

Nếu dashboard chỉ có số lần **JavaMailSender.send(...)** được gọi, ứng dụng không biết backlog đang tăng, OTP sắp hết hạn hay dead letters bị bỏ quên.

| Metric logic | Kiểu | Ý nghĩa |
| --- | --- | --- |
| **mail_outbox_jobs** | Gauge | Số jobs theo state/purpose |
| **mail_outbox_oldest_pending_age_seconds** | Gauge | Tuổi job PENDING/RETRY_WAIT cũ nhất |
| **mail_worker_claims_total** | Counter | Lần claim thành công/thất bại |
| **mail_worker_stale_lease_total** | Counter | Worker finalize với lease không còn hợp lệ |
| **mail_attempts_total** | Counter | Số attempts theo provider/result |
| **mail_attempt_duration_seconds** | Timer | Thời gian transport submit |
| **mail_retry_scheduled_total** | Counter | Số retries được lên lịch theo reason |
| **mail_retry_delay_seconds** | Timer/Histogram | Delay dự kiến trước lần thử tiếp |
| **mail_dead_letter_total** | Counter | Jobs chuyển vào DLQ theo reason |
| **mail_dead_letter_backlog** | Gauge | Jobs đang DEAD_LETTER |
| **mail_unknown_backlog** | Gauge | Jobs đang UNKNOWN |
| **mail_lease_expired_total** | Counter | Lease hết hạn được recovery |
| **mail_notification_expired_total** | Counter | Notifications hết business TTL |
| **mail_quota_denied_total** | Counter | Jobs không được permit |
| **mail_replay_actions_total** | Counter | Replay/manual actions theo outcome |

Những tên này là **đề xuất metrics do ứng dụng tự triển khai**, không phải metrics có sẵn mặc định từ Spring Mail. Prometheus exporters có thể bổ sung hậu tố **_total**, tùy meter registry.

### Ví dụ Micrometer

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class MailWorkerMetrics {

    private final MeterRegistry registry;

    public MailWorkerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAttempt(
            String provider,
            String result,
            long elapsedNanos
    ) {
        registry.counter(
                "mail_attempts",
                "provider", provider,
                "result", result
        ).increment();

        registry.timer(
                "mail_attempt_duration",
                "provider", provider,
                "result", result
        ).record(elapsedNanos, java.util.concurrent.TimeUnit.NANOSECONDS);
    }
}
~~~

Để dùng ví dụ Micrometer, cần dependency **spring-boot-starter-actuator** hoặc meter registry setup tương ứng. Không gắn raw exception text, recipient email, business key hoặc notificationId vào metric labels vì có thể gây high cardinality và lộ thông tin.

### Alert quan trọng

- **UNKNOWN backlog tăng**: có thể có ambiguous outcomes hoặc recovery issues; cần đối soát, không bật automatic retry.
- **DEAD_LETTER backlog tăng**: có lỗi template, provider config hoặc retry policy quá nghiêm.
- **Oldest pending age cao**: scheduler/quota/SMTP đang chậm.
- **Lease expired tăng**: worker crash, lease quá ngắn hoặc SMTP timeout.
- **Retry storm**: nhiều jobs nhận cùng transient failure, cần circuit breaker/backoff.
- **SMTP auth errors hàng loạt**: pause provider lane và kiểm tra secrets.

### Structured logs

Ví dụ:

~~~text
event=mail_attempt_finalized
notification_id=opaque-id
attempt_number=3
tenant_tier=business
provider=primary
old_state=IN_FLIGHT
new_state=RETRY_WAIT
error_code=SMTP_TEMP_REJECT
retry_at=2026-01-01T10:15:00Z
~~~

Không log raw HTML, plain text, OTP/token hoặc SMTP credentials. Dùng opaque IDs để tra trong database với quyền phù hợp.

## 46. Bảo mật, privacy và operational controls

Một retry worker có quyền gửi email là một thành phần nhạy cảm: nếu bị lạm dụng, nó có thể gửi spam, lấy cắp dữ liệu hoặc làm xấu reputation của domain.

### Các biện pháp cần có

1. **API authentication:** không cho anonymous request tạo bất kỳ sender/recipient nào.
2. **Tenant authorization:** tenant không được truy cập/replay job của tenant khác.
3. **Verified sender profile:** From/Reply-To chỉ lấy từ cấu hình đã xác minh.
4. **Recipient policy:** consent, suppression, bounce, unsubscribe theo purpose.
5. **Encryption:** TLS với provider, encryption cho DB/object storage phù hợp.
6. **Secret management:** không đưa SMTP password vào code, Git, logs.
7. **Template trust:** tránh server-side template injection và HTML injection.
8. **URL/token TTL:** link xác minh phải do service tin cậy tạo và có hạn.
9. **Audit:** replay, cancel, reconcile, quota override đều có actor/reason.
10. **Rate limiting:** ngăn tenant hoặc account bị abuse.
11. **Retention:** nội dung mail, attempts, DLQ và logs có thời gian lưu riêng.
12. **Webhook verification:** nếu nhận feedback provider, cần chữ ký/replay protection.

### Dead-letter UI không nên trả body mặc định

Một trang operator có thể hiển thị:

~~~text
Notification: 8a...
Tenant: tenant-7
Purpose: ORDER_RECEIPT
Recipient: c***@example.test
State: DEAD_LETTER
Error: TEMPLATE_MODEL_INVALID
Attempts: 0 / 5
Created: ...
~~~

Chỉ khi có quyền và lý do nghiệp vụ, operator mới mở nội dung được redact/đầy đủ. Không biến DLQ thành một bảng dễ dàng download PII của mọi email thất bại.

### Không dùng manual replay như backdoor chống suppression

Nếu người dùng đã unsubscribe marketing sau khi email ban đầu thất bại, thao tác replay phải **kiểm tra lại suppression/consent hiện tại**, không gửi dựa vào trạng thái consent cũ.

### Transport config cần được kiểm tra

Ví dụ Spring Mail cần connection/read/write timeout, TLS/auth và certificate verification phù hợp. Không bật raw SMTP protocol debug trên production nếu logs có thể chứa credentials, địa chỉ hoặc nội dung nhạy cảm.

## 47. Runbook: provider unavailable và backlog tăng

### Triệu chứng

~~~text
mail_outbox_oldest_pending_age_seconds increases
mail_attempts_total{result=UNKNOWN} increases
mail_retry_scheduled_total increases
SMTP connection errors / timeouts spike
~~~

### Các bước xử lý

1. Xác minh provider/network/TLS/auth thay vì mặc định lỗi quota.
2. Kiểm tra còn gửi được qua test account/canary có kiểm soát không.
3. Pause lane hoặc mở circuit breaker nếu lỗi hệ thống, tránh retry storm.
4. Kiểm tra các attempts đã **ACCEPTED**, **UNKNOWN** và **proven not accepted**.
5. Điều chỉnh backoff, retry budget và distributed rate limit.
6. Không chuyển toàn bộ UNKNOWN sang PENDING để “thử lại”.
7. Đánh dấu expired OTP/deadlines theo policy.
8. Khi provider phục hồi, drain backlog với tốc độ được phép.
9. Xác minh không tạo duplicate notifications và attempt history đầy đủ.

### Những jobs có thể tự retry

Chỉ những jobs **RETRY_WAIT** với lỗi đã được xác nhận không accepted và còn deadline/retry budget. Các jobs UNKNOWN cần đối soát; DEAD_LETTER cần operator action; EXPIRED/CANCELLED/ACCEPTED không tự enqueue lại.

### Không tăng vô hạn workers

Nếu provider còn cho 10 recipients/s mà backlog 100.000, thêm 100 workers không làm hoàn tất trong vài giây. Cần chọn admission/priority/backlog strategy và đo thời gian drain.

### Sau sự cố

Phân tích nguyên nhân, thời gian outage, số jobs bị ảnh hưởng theo state, số người nhận có thể đã bị gửi trùng và khả năng đối soát. Bổ sung fault-injection tests nếu thiếu.

## 48. Runbook: dead letters tăng đột biến

**Bước 1 — Nhóm theo reasonCode.**

~~~sql
SELECT dead_letter_reason, COUNT(*)
FROM mail_outbox
WHERE state = 'DEAD_LETTER'
GROUP BY dead_letter_reason
ORDER BY COUNT(*) DESC;
~~~

**Bước 2 — Xác minh nguyên nhân.** Nếu đa số là TEMPLATE_MODEL_INVALID, không mở SMTP connections hay tăng max_attempts; sửa producer/template. Nếu đa số là SMTP_AUTH_CONFIGURATION, có thể secret rotation hoặc sender verification issue.

**Bước 3 — Xác định phạm vi.** Tenant, purpose, template revision, provider, khoảng thời gian. Đừng replay hàng loạt chỉ vì một lỗi đã biến mất.

**Bước 4 — Phân nhóm eligibility.** Có những jobs đã hết hạn, recipient bị suppression hoặc nội dung đã thay đổi. Chỉ chọn những jobs hợp lệ cho replay.

**Bước 5 — Dry run.** Một hệ thống mature có thể cung cấp chế độ kiểm tra replay eligibility mà chưa đổi state, trả số lượng lý do chặn và ước lượng traffic.

**Bước 6 — Replay canary.** Chọn ít jobs an toàn trước, tăng dần theo quota/SLO, có khả năng pause batch.

**Bước 7 — Audit.** Lưu actor, số jobs, policy, lý do, old/new attempts, kết quả.

### Dead-letter đã được replay nhưng lại fail

Nếu chưa sửa root cause, jobs có thể quay lại DEAD_LETTER. Đừng cứ tăng max_attempts thêm. Cần theo dõi **replay success rate** và dừng khi lỗi cùng loại tái xuất hiện.

### Không xóa mọi dead letters sau khi fix

Có thể archive theo retention, nhưng cần giữ audit/evidence tối thiểu để biết đã có những email nào chưa được gửi và vì sao. Xóa sạch DLQ để dashboard “xanh” có thể che mất sự cố.

## 49. Những sai lầm dễ gặp khi xây retry worker

### Lỗi 1 — Retry mọi exception của JavaMailSender

**Hậu quả:** SMTP server có thể đã accepted trước khi response mất; việc retry gửi trùng.

**Sửa:** phân biệt **proven not accepted** với **UNKNOWN**, đối soát trước retry khi kết quả mơ hồ.

### Lỗi 2 — Dùng Message-ID để nghĩ SMTP sẽ dedup

**Hậu quả:** hai submissions cùng Message-ID vẫn có thể được giao hai lần.

**Sửa:** business notification key, attempt history, provider-specific idempotency nếu có.

### Lỗi 3 — Đưa SMTP send vào @Transactional

**Hậu quả:** DB lock kéo dài và vẫn không atomic với SMTP.

**Sửa:** outbox transaction ngắn, worker submission bên ngoài.

### Lỗi 4 — SELECT PENDING rồi UPDATE không điều kiện

**Hậu quả:** hai workers cùng chọn một notification.

**Sửa:** atomic claim với **SKIP LOCKED** hoặc compare-and-set.

### Lỗi 5 — Không dùng fencing token khi finalize

**Hậu quả:** worker đã hết lease ghi đè trạng thái mới.

**Sửa:** WHERE state='IN_FLIGHT' AND lease_token=...; affected rows phải là 1.

### Lỗi 6 — Hết lease là tự retry

**Hậu quả:** worker cũ có thể đã submit thành công trước crash.

**Sửa:** expired IN_FLIGHT → UNKNOWN để đối soát.

### Lỗi 7 — Tăng attempt_count khi quota denied

**Hậu quả:** job vào DLQ dù chưa từng được SMTP submit.

**Sửa:** phân biệt claim/permit và beginAttempt.

### Lỗi 8 — Không có attempt history

**Hậu quả:** không biết job đã thử bao nhiêu lần, lỗi nào và qua provider nào.

**Sửa:** lưu attemptId, attemptNumber, timestamps, result, provider ID, error code.

### Lỗi 9 — Gọi send() lại khi DB finalize thất bại

**Hậu quả:** đã accepted nhưng DB lỗi dẫn tới duplicate send.

**Sửa:** retry chỉ ghi result khi còn token, hoặc UNKNOWN/reconciliation.

### Lỗi 10 — Retry fixed delay đồng bộ toàn cụm

**Hậu quả:** retry storm sau outage.

**Sửa:** exponential backoff, jitter và distributed quota rate limiter.

### Lỗi 11 — Không tôn trọng business deadline

**Hậu quả:** OTP/link đã hết hạn vẫn được gửi.

**Sửa:** expiresAt, expiry checks, retry decision theo deadline.

### Lỗi 12 — Dead letter chỉ là log error

**Hậu quả:** jobs biến mất, không thể review hoặc replay.

**Sửa:** lưu durable state + reason + history + audit.

### Lỗi 13 — Replay tất cả jobs bằng một nút

**Hậu quả:** vượt quota, duplicate, gửi vào recipient đã opt-out.

**Sửa:** RBAC, eligibility recheck, canary/batch replay và rate control.

### Lỗi 14 — Reset attempt_count về 0 khi replay

**Hậu quả:** mất lịch sử, conflict UNIQUE(attempt_number), khó kiểm toán.

**Sửa:** giữ attempts, nâng max_attempts có kiểm soát hoặc tạo notification mới có lineage.

### Lỗi 15 — Cho replay UNKNOWN sau khi đổi tên thành DEAD_LETTER

**Hậu quả:** lách chính sách chống gửi trùng.

**Sửa:** bảo toàn ambiguous-attempt history; kiểm tra evidence trước mọi replay.

### Lỗi 16 — Không tách permanent và transient

**Hậu quả:** invalid address hoặc template lỗi bị retry vô hạn.

**Sửa:** classifier có reason codes và terminal decisions.

### Lỗi 17 — Auth lỗi toàn provider nhưng đưa mọi job vào DLQ

**Hậu quả:** DLQ ngập trong khi nguyên nhân là một secret.

**Sửa:** provider-level pause/circuit breaker và alert; giữ jobs chưa attempt.

### Lỗi 18 — Không giới hạn worker/connection

**Hậu quả:** tài nguyên và provider quota bị quá tải.

**Sửa:** bounded executor, semaphore, distributed rate limit.

### Lỗi 19 — Claim một batch lớn hơn năng lực gửi

**Hậu quả:** leases hết hạn ngay khi jobs còn ngồi đợi.

**Sửa:** claim theo actual worker/permit capacity; heartbeat khi cần.

### Lỗi 20 — Chỉ đo số email ACCEPTED

**Hậu quả:** không thấy pending age, unknown backlog và dead letters.

**Sửa:** metrics theo state, reason, latency và deadline.

### Lỗi 21 — Log raw body/OTP khi DLQ

**Hậu quả:** lộ PII, token và thông tin nội bộ.

**Sửa:** metadata/safe error codes, quyền truy cập và retention.

### Lỗi 22 — Sender profile nhận tùy ý từ API

**Hậu quả:** giả danh domain, vi phạm verified identity.

**Sửa:** allowlist sender profile theo tenant và purpose.

### Lỗi 23 — Coi ACCEPTED là email đã tới Inbox

**Hậu quả:** báo cáo giao hàng sai; bounce/delivery cần hệ thống khác.

**Sửa:** phân biệt SMTP acceptance với provider delivery feedback.

### Lỗi 24 — Retry job cũ bằng dữ liệu nghiệp vụ mới

**Hậu quả:** nội dung hóa đơn/link/mã khác nhau giữa attempts.

**Sửa:** pin template revision và model/render snapshot theo policy.

### Lỗi 25 — Tạo Dead Letter queue nhưng không có operator flow

**Hậu quả:** hàng nghìn jobs chết không ai xử lý.

**Sửa:** dashboard, reasons, ownership, SLAs, replay/cancel và audit.

## 50. Tình huống thực hành và câu hỏi

### A. Hai replicas cùng poll một job

**Đầu vào:** hai workers thấy PENDING cùng thời điểm.

**Câu hỏi:** cơ chế nào bảo đảm chỉ một claim thành công?

**Hướng giải:** PostgreSQL **FOR UPDATE SKIP LOCKED** trong cùng statement UPDATE...RETURNING, mỗi claim có lease token riêng. Unit/integration test với hai concurrent calls.

### B. Worker claim rồi quota hết

**Đầu vào:** job đã IN_FLIGHT nhưng permit gate từ chối.

**Câu hỏi:** có nên tăng attempt_count?

**Hướng giải:** không. **releaseWithoutAttempt** chuyển RETRY_WAIT với nextAt, không ghi mail_attempt.

### C. SMTP trả lỗi có thể retry trước DATA

**Đầu vào:** provider xác nhận chưa accepted nội dung.

**Câu hỏi:** trạng thái nào?

**Hướng giải:** **RETRY_WAIT** nếu còn attempts và deadline; dùng backoff+jitter. Nếu hết tries, **DEAD_LETTER**.

### D. Timeout sau DATA

**Đầu vào:** sender không nhận được final response.

**Câu hỏi:** có tự retry không?

**Hướng giải:** **UNKNOWN**; đối soát hoặc risk decision có audit trước resubmit.

### E. Worker chết trước finalize

**Đầu vào:** attempt STARTED, provider có thể accepted, lease hết.

**Hướng giải:** expired IN_FLIGHT → UNKNOWN, không claim lại tự động.

### F. Template thiếu biến mã đơn

**Đầu vào:** preflight fail trước SMTP.

**Hướng giải:** **DEAD_LETTER** hoặc review theo policy; không tăng transport attempts và không gọi sender.

### G. OTP hết hạn trong lúc chờ retry

**Đầu vào:** nextAttemptAt nằm sau expiresAt.

**Hướng giải:** **EXPIRED**; không gửi token đã chết, người dùng cần flow tạo mã mới.

### H. Đạt 5/5 attempts

**Đầu vào:** cả năm lỗi được chứng minh chưa accepted.

**Hướng giải:** **DEAD_LETTER / ATTEMPTS_EXHAUSTED**, giữ history, không tự retry vô hạn.

### I. Operator muốn tăng max_attempts từ 5 lên 7

**Đầu vào:** job DEAD_LETTER do transient pre-acceptance failures, provider phục hồi.

**Hướng giải:** kiểm tra eligibility và bằng chứng, giữ attempt_count=5, update max_attempts=7, PENDING và audit; không reset attempts.

### J. Recipient đã unsubscribe trước replay

**Đầu vào:** marketing job DEAD_LETTER cũ.

**Hướng giải:** suppression/consent hiện tại thắng; không replay mail marketing đã opt-out.

### K. Stale worker cố ghi ACCEPTED

**Đầu vào:** A có token cũ, job đã đổi sang UNKNOWN.

**Hướng giải:** finalize with WHERE state='IN_FLIGHT' AND lease_token=A ảnh hưởng 0 rows, báo stale result. Reconciliation xử lý evidence.

### L. Database down sau khi SMTP accepted

**Đầu vào:** send() trả thành công, finishAttempt JDBC lỗi.

**Hướng giải:** không gửi lại. Retry persistence nếu có thể trong lease; sau crash/expiry xử lý UNKNOWN và đối soát.

### M. SMTP auth sai cho mọi job

**Đầu vào:** hàng trăm jobs cùng gặp MailAuthenticationException.

**Hướng giải:** pause provider lane/circuit breaker, alert và sửa secret; không đốt hết attempts với từng job.

### N. Một email có 3 recipients

**Đầu vào:** gửi một MimeMessage cho To/Cc nhiều người.

**Hướng giải:** partial success và quota phức tạp; bài demo nên dùng một recipient/logical notification. Nếu mở rộng, lưu per-recipient outcomes và không retry recipients đã accepted.

### O. DLQ tăng sau khi publish template mới

**Đầu vào:** nhiều TEMPLATE_MODEL_INVALID.

**Hướng giải:** sửa producer/template, review pinned revisions, không tăng worker hoặc SMTP quota; replay chỉ jobs hợp lệ.

### P. Có 1.000 jobs dead-letter và bấm replay all

**Đầu vào:** provider chỉ cho 20 recipients/s.

**Hướng giải:** dry run, canary, bounded batch/rate, maintain audit và khả năng pause. Không gửi 1.000 attempts cùng lúc.

### Q. Client POST /notifications lại vì timeout

**Đầu vào:** cùng businessKey được gửi hai lần.

**Hướng giải:** **UNIQUE (tenant_id, business_key)** và trả cùng notification ID nếu payload tương đương; nếu khác, idempotency conflict.

### R. Email đã accepted nhưng provider báo bounce

**Đầu vào:** outbox ACCEPTED, webhook hard bounce.

**Hướng giải:** không tự đổi thành retry SMTP; cập nhật delivery status/suppression qua hệ thống feedback riêng, cân nhắc recipient verification.

### S. Message-ID giống nhau trong hai attempts

**Đầu vào:** app reuse cùng header Message-ID.

**Hướng giải:** không đủ để ngăn duplicate; cần state machine, attempts và reconciliation.

### T. Mất hết logs sau restart

**Đầu vào:** worker chết, không có console log cũ.

**Hướng giải:** outbox + mail_attempt + audit vẫn cho biết job đã ở state gì, có token/attempt nào và phải xử lý thế nào. Logs chỉ bổ sung observability, không thay durable state.

## 51. Lộ trình triển khai theo từng milestone

Để xây được worker thay vì chỉ đọc ví dụ, có thể chia bài thực hành thành các mốc:

### Milestone 1 — Lưu durable notification

- Tạo PostgreSQL migration.
- Viết enqueue service theo **tenant + businessKey**.
- Test hai POST giống nhau chỉ tạo một job.
- Trả **PENDING** và notificationId; chưa có SMTP.

**Điều kiện hoàn thành:** restart ứng dụng không làm mất job và duplicate enqueue không tạo hai rows.

### Milestone 2 — Worker claim một job

- Viết atomic claim SQL với SKIP LOCKED.
- Cấp leaseToken và leaseUntil.
- Chạy hai workers cùng claim một job.
- Kiểm tra chỉ một claim thành công.

**Điều kiện hoàn thành:** không có hai leases active trên cùng notification tại một thời điểm.

### Milestone 3 — Thêm transport và attempt history

- Viết SpringMailTransport.
- BeginAttempt trước SMTP.
- Finalize state với leaseToken.
- Dùng Mailpit/SMTP fixture để nhận mail.
- Quan sát PENDING → IN_FLIGHT → ACCEPTED.

**Điều kiện hoàn thành:** mỗi attempt được ghi đúng number/outcome; accepted không bị tự resend.

### Milestone 4 — Retry policy

- Giới hạn maxAttempts.
- Thêm exponential backoff + jitter.
- Kiểm tra expiresAt.
- Test fake transport thất bại hai lần rồi thành công.
- Test lỗi thứ N đưa vào DEAD_LETTER.

**Điều kiện hoàn thành:** không có tight retry loop, nextAttemptAt được lưu trong DB và worker không bị giữ thread sleep.

### Milestone 5 — UNKNOWN và recovery

- Quét expired IN_FLIGHT leases.
- Đưa về UNKNOWN, không auto retry.
- Inject crash after send/DB update failure.
- Thêm thao tác reconciliation có audit.

**Điều kiện hoàn thành:** fake provider đã accepted một email nhưng client không nhận response vẫn chỉ có **một transport submission** tự động.

### Milestone 6 — Dead letter và operator workflow

- List dead letters theo reason.
- Xem attempt history an toàn, có redact PII.
- Replay có authorization, audit, state CAS và maxAttempts budget.
- Canary replay với quota gate.
- Cancel jobs không còn hợp lệ.

**Điều kiện hoàn thành:** operator không thể replay ACCEPTED/UNKNOWN chưa đối soát và không thể bỏ qua suppression/expiry.

### Milestone 7 — Monitoring và production hardening

- Metrics backlog, age, unknown, dead letter, retries.
- Rate/concurrency limit.
- Provider-level pause/circuit breaker.
- Secure sender profiles, secrets, TLS, retention.
- Test multi-replica, provider outage, quota exhaustion.

**Điều kiện hoàn thành:** có thể phát hiện lỗi, dừng sending an toàn và phục hồi có kiểm soát.

## 52. Checklist trước khi coi worker sẵn sàng cho production

### State machine và database

- **PENDING, IN_FLIGHT, RETRY_WAIT, ACCEPTED, UNKNOWN, DEAD_LETTER, EXPIRED, CANCELLED** được định nghĩa rõ.
- Mọi transition được validate; không ghi state tùy ý từ API.
- Enqueue có business idempotency key và unique constraint.
- Claim atomic, có lease owner/token và fencing.
- BeginAttempt ghi history bền vững trước SMTP.
- Finalization và attempt history cùng transaction.
- Expired IN_FLIGHT không auto retry.
- Terminal statuses không bị scheduler tự claim lại.
- DB migrations/indexes/retention được quản lý.

### Retry và dead letter

- Retry chỉ cho **proven not accepted transient** hoặc trường hợp provider có semantics an toàn.
- UNKNOWN được tách khỏi RETRY_WAIT.
- Max attempts không bị vượt bởi race/restart.
- Backoff+jitter và retry-after theo provider.
- Quota denied không tiêu attempts.
- Expired OTP/token không được gửi muộn.
- DLQ giữ reason và lịch sử; không tự xóa.
- Manual replay có RBAC, audit, eligibility và rate limit.
- Replay không reset attempt numbering làm mất lịch sử.
- Replay UNKNOWN phải có reconciliation/risk approval.

### SMTP và nội dung

- JavaMailSender timeout/TLS/auth được cấu hình đúng.
- Sender profile đã xác minh theo tenant.
- Recipient được validate/suppression/consent theo purpose.
- Plain/HTML dùng cùng model/template revision.
- Không log SMTP secrets, OTP hoặc raw message.
- Attachment size và MIME encoding được kiểm soát.
- Không nhầm SMTP accepted với delivered.

### Scaling và observability

- Worker concurrency hữu hạn; claims phù hợp năng lực thật.
- Global/distributed rate limit cho provider quota chung.
- Có alert pending age, retry storm, UNKNOWN, DLQ growth.
- Có metrics theo provider/purpose/result, không lộ PII.
- Scheduler multi-replica không double claim.
- Provider outage không tạo send loop.
- Có runbook pause/replay/cancel/reconcile.
- Load test trên sandbox/fake provider, không spam người thật.

### Testing

- Unit test RetryPolicy và boundary maxAttempts/expiry.
- Unit test preflight invalid/consent/recipient.
- Integration test claim concurrency với PostgreSQL thật.
- Test no permit không tăng attempts.
- Test SMTP accepted → ACCEPTED.
- Test proven transient → RETRY_WAIT và retry sau nextAt.
- Test permanent failure → DEAD_LETTER.
- Test DB failure after SMTP accepted → UNKNOWN, không resend.
- Test crash/lease expiry → UNKNOWN.
- Test replay authorization, audit và state compare-and-set.
- Test unknown reconciliation và duplicate protection.

## 53. Tổng kết kiến trúc cần ghi nhớ

~~~text
Enqueue
  -> write durable PENDING job
  -> dedup by tenant + business key
  -> no SMTP inside business transaction

Claim
  -> SELECT ... FOR UPDATE SKIP LOCKED
  -> IN_FLIGHT with lease token
  -> commit DB transaction

Preflight + quota
  -> validate recipient/template/deadline
  -> if no permit: reschedule WITHOUT attempt

BeginAttempt
  -> increment attempt_count
  -> insert STARTED history
  -> commit BEFORE external SMTP call

Submit
  -> JavaMailSender
  -> outside DB transaction

Finalize
  -> compare state + lease token
  -> update outbox + history atomically

ACCEPTED
  -> no automatic retry
  -> not equal delivered/read

RETRYABLE_NOT_ACCEPTED
  -> exponential backoff + jitter
  -> retry until max attempts / deadline

UNKNOWN
  -> reconcile first, do not blind resend

DEAD_LETTER
  -> durable holding state with reason/history
  -> manual reviewed replay or cancel
  -> not an automatic retry queue

EXPIRED
  -> don't send stale OTP/links

Lease expired
  -> UNKNOWN, not PENDING

Replay
  -> RBAC + audit + compare-and-set
  -> preserve attempt numbers
  -> recheck suppression, deadline and content

Horizontal scale
  -> atomic claims + distributed quota controls

Transactional outbox
  -> durable intent
  != exactly-once SMTP delivery
~~~

**Xây worker retry với trạng thái và dead letter** là bước chuyển từ một lời gọi **JavaMailSender.send(...)** đơn lẻ sang một cơ chế gửi email bền vững, có thể quan sát và phục hồi khi gặp sự cố. Trong dự án thực hành này, PostgreSQL lưu outbox và lịch sử attempts; worker sử dụng **SKIP LOCKED** để claim, **lease token** để tránh ghi đè bởi worker cũ, **backoff+jitter** để retry các lỗi đã được chứng minh chưa accepted, và **DEAD_LETTER** để giữ lại công việc cần điều tra. Điểm quan trọng nhất là phân biệt **RETRY_WAIT** với **UNKNOWN**: SMTP timeout hoặc JVM crash không tự chứng minh email chưa được gửi. Khi bổ sung đối soát, manual replay có audit, giới hạn quota, expiry và tests mô phỏng crash sau acceptance, hệ thống có thể mở rộng mà hạn chế gửi trùng và không đánh mất khả năng giải thích **notification nào đã được thử, vào lúc nào, kết quả gì và cần hành động tiếp theo ra sao**.

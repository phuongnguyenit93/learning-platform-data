# Mail command và message key

Trong Spring Framework Mail, lời gọi `JavaMailSender.send(...)` giúp ứng dụng nộp một email cho SMTP server. Nhưng một hệ thống production phải trả lời nhiều câu hỏi hơn: email đó phát sinh từ nghiệp vụ nào, ai cần nhận, đã được xếp lịch chưa, worker nào đang gửi, đã thử lại bao nhiêu lần, và điều gì xảy ra khi **cùng một yêu cầu được nhận hai lần**?

Giả sử ứng dụng phát sự kiện `OrderConfirmed`:

~~~text
OrderConfirmed(eventId=evt-123, orderId=A123)
    |
    v
Consumer tạo yêu cầu gửi email xác nhận
    |
    +-- Lần 1: INSERT mail job thành công
    |           nhưng consumer crash trước khi ack broker
    |
    +-- Lần 2: broker giao lại cùng evt-123
                consumer chạy thêm một lần
~~~

Nếu mỗi lần handler chạy đều tạo một mail job mới, người mua có thể nhận hai email xác nhận. Nếu lại dùng khóa quá rộng như `order-A123`, email hóa đơn hoặc email giao hàng của cùng đơn có thể bị chặn nhầm là trùng.

**Mail command** và **message key** là hai thành phần nền tảng để giải quyết những vấn đề đó:

- **Mail command** mô tả một *ý định gửi* theo nghiệp vụ: tenant, người nhận, loại thông báo, template, payload, thời gian gửi và định danh nguồn.
- **Message key** xác định duy nhất *một yêu cầu gửi logic* trong phạm vi đã quy định; mọi lần xử lý lại cùng yêu cầu phải dùng lại khóa này.
- **Durable mail job/outbox** lưu yêu cầu và trạng thái trong database, cho phép worker gửi hoặc retry độc lập với HTTP request hay broker consumer.

**Giới hạn quan trọng:** message key giúp chống tạo trùng logical job. Nó **không tự bảo đảm exactly-once SMTP delivery**. Database và SMTP không chung transaction; khi SMTP đã nhận thư nhưng ứng dụng mất phản hồi, việc retry vẫn có thể gửi trùng. Thiết kế production cần nêu rõ ranh giới này.

## 1. Tách command khỏi email MIME và transport

Một hệ thống có thể tổ chức:

~~~mermaid
flowchart LR
    A["Business event / API"] --> B["MailCommand"]
    B --> C["Command gateway"]
    C --> D["Durable mail outbox"]
    D --> E["Mail worker"]
    E --> F["MimeMessage + JavaMailSender"]
    F --> G["SMTP / provider"]
    G --> H["Delivery events"]
~~~

| Khối | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| Business service | Xác định sự kiện và nhu cầu gửi | Gọi SMTP trong transaction nghiệp vụ rồi coi đã an toàn |
| Mail command | Mô tả ý định gửi có cấu trúc | Giữ kết nối SMTP hoặc stream sống |
| Command gateway | Validate, deduplicate, persist request | Gửi lại khi thấy duplicate |
| Outbox/job store | Giữ trạng thái, lịch, retry, audit | Xóa yêu cầu khi restart |
| Worker | Claim job, render MIME, gọi transport | Tạo message key mới theo từng attempt |
| Provider event handler | Chuẩn hóa delivery/bounce/complaint | Coi mọi submitted email là delivered |

`MimeMessage` là đối tượng của Jakarta Mail chứa header, body và MIME parts. Nó có thể mutable, phụ thuộc `Session` và resource attachment. **Không nên dùng nguyên `MimeMessage` làm command nghiệp vụ** hoặc coi `MimeMessage.getMessageID()` là khóa idempotency của hệ thống.

## 2. Phân biệt các loại định danh

Trong quá trình gửi có nhiều ID với ý nghĩa riêng:

| Định danh | Ví dụ | Phạm vi |
| --- | --- | --- |
| Business event ID | `evt-123` | Một sự kiện nghiệp vụ |
| Message key | `order-confirmation:evt-123:recipient-9` | Một logical mail intent |
| Mail job ID | `job-91b...` | Một bản ghi outbox |
| Attempt ID | `attempt-4ea...` | Một lần thử SMTP/API |
| RFC Message-ID | `<opaque@mailer.example>` | Header trong email MIME |
| Provider message ID | `provider-abc...` | Submission/delivery tại ESP |
| Correlation/trace ID | `trace-8c2...` | Theo dõi request/log |

### 2.1. Message key khác job ID

~~~text
messageKey = order-confirmation:evt-123:recipient-9
jobId      = 7f84f55a-...
~~~

Job ID có thể được tạo khi lưu row lần đầu. Khi broker giao lại `evt-123`, command phải mang **cùng message key** để gateway trả về job ID cũ, không tạo job mới.

Không tạo message key bằng `UUID.randomUUID()` ngay trong consumer mỗi lần sự kiện được nhận. Random UUID thích hợp cho **job ID**, hoặc cho **event ID được tạo và lưu đúng một lần tại nguồn**.

### 2.2. Message key khác RFC Message-ID

~~~java
MimeMessage mime = mailSender.createMimeMessage();
// Đặt From, To, Subject, Content...
mime.saveChanges();
String mimeId = mime.getMessageID();
~~~

`Message-ID` là header theo Internet Message Format. Jakarta Mail có thể sinh nó khi save/serialize; khi retry tạo MIME mới, giá trị có thể khác. Nhà cung cấp cũng có thể xử lý header theo chính sách riêng.

**Không dùng giá trị này làm khóa chính của yêu cầu gửi trước khi enqueue.** Email receiver không mặc định bỏ email trùng chỉ vì hai message có cùng header Message-ID.

### 2.3. Provider ID có thể chỉ xuất hiện sau submission

ESP có thể trả về ID để đối chiếu delivery webhook. SMTP thuần không phải lúc nào cũng cung cấp message ID ở dạng ứng dụng có thể đọc. Một job retry qua hai provider có thể nhận hai provider IDs.

Nên lưu mapping:

~~~text
tenantId + messageKey
    -> mailJobId
        -> attemptId #1 -> providerMessageId A
        -> attemptId #2 -> providerMessageId B
~~~

### 2.4. Correlation ID phục vụ tracing

Một HTTP request có thể tạo ba mail commands; một job có thể retry trong nhiều trace. Vì vậy correlation ID không tự là logical mail key. Chúng có thể được liên kết, nhưng **không thay thế nhau**.

## 3. Một MailCommand nên chứa gì?

Ví dụ command:

~~~text
MailCommand {
  tenantId:          tenant-17
  messageKey:        order-confirmation:evt-123:recipient-9
  sourceEventId:     evt-123
  mailType:          ORDER_CONFIRMATION
  recipientId:       recipient-9
  recipientAddress:  alice@example.net
  senderProfile:     TX_PRIMARY
  templateId:        order-confirmation
  payloadRef:        order-snapshot:A123:v1
  notBefore:         2026-11-12T10:00:00Z
  expiresAt:         null
}
~~~

| Trường | Ý nghĩa | Lưu ý production |
| --- | --- | --- |
| `tenantId` | Chủ sở hữu và ranh giới dữ liệu | Phải xác thực/ủy quyền |
| `messageKey` | Khóa idempotency | Ổn định khi retry |
| `sourceEventId` | Sự kiện nguồn | Giúp audit/correlation |
| `mailType` | Loại thông báo | Enum có giới hạn |
| `recipientId` | Định danh người nhận | Có thể an toàn hơn email trong key |
| `recipientAddress` | Địa chỉ SMTP | PII, cần bảo vệ khi lưu |
| `senderProfile` | Cấu hình sender | Không chứa SMTP password |
| `templateId` | Định danh template | Phải thuộc allowlist |
| `payloadRef` | Reference tới snapshot/render inputs | Có retention/lifetime |
| `notBefore` | Không gửi trước thời điểm này | Dùng `Instant` |
| `expiresAt` | Không gửi sau deadline | Quan trọng với OTP |

### 3.1. Immutable value object trong Java 17+

~~~java
package com.example.mail.command;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record MailCommand(
        UUID tenantId,
        String messageKey,
        UUID sourceEventId,
        UUID recipientId,
        String recipientAddress,
        MailType mailType,
        SenderProfile senderProfile,
        String templateId,
        String payloadRef,
        Instant notBefore,
        Instant expiresAt) {

    public MailCommand {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(messageKey);
        Objects.requireNonNull(recipientId);
        Objects.requireNonNull(recipientAddress);
        Objects.requireNonNull(mailType);
        Objects.requireNonNull(senderProfile);
        Objects.requireNonNull(templateId);
        Objects.requireNonNull(payloadRef);
        Objects.requireNonNull(notBefore);

        if (messageKey.isBlank() || messageKey.length() > 240) {
            throw new IllegalArgumentException(
                    "Invalid message key");
        }
        if (recipientAddress.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient is required");
        }
        if (expiresAt != null && !expiresAt.isAfter(notBefore)) {
            throw new IllegalArgumentException(
                    "Expiration must be after notBefore");
        }
    }
}
~~~

Các enum:

~~~java
public enum MailType {
    ORDER_CONFIRMATION,
    INVOICE,
    PASSWORD_RESET,
    OTP,
    NEWSLETTER,
    PROMOTION
}

public enum SenderProfile {
    TX_PRIMARY,
    MARKETING_PRIMARY
}
~~~

Đây là mẫu dữ liệu; gateway còn phải kiểm tra cú pháp email, tenant membership, policy cho từng sender, template authorization, giới hạn size và consent.

`record` giúp tránh sửa các field references sau khi tạo nhưng **không tự làm cho `Map`, `List`, `byte[]` hoặc entity mutable bên trong bất biến sâu**. Nếu command chứa collection, tạo immutable copy; với payload lớn, dùng immutable snapshot/reference.

### 3.2. Command không phải SMTP request

`MailCommand` chỉ mô tả một ý định. Các bước xây `MimeMessage`, thêm `From`, `Subject`, `Content-ID`, attachment và gọi `JavaMailSender` thuộc worker/transport adapter. Điều này giúp thay provider hoặc đổi cách render mà không biến command thành đối tượng phụ thuộc vào kết nối sống.

## 4. Thiết kế message key theo nghiệp vụ

Một message key tốt có các tính chất:

1. **Stable:** cùng business intent luôn tạo cùng key.
2. **Đủ phân biệt:** không nhập nhằng giữa các loại mail/recipient/occurrence.
3. **Tenant scoped:** không để tenant khác chặn nhầm.
4. **Không phụ thuộc retry:** attempt 1 và attempt 5 có cùng key.
5. **Không phụ thuộc pod, timestamp xử lý hay random mới.**
6. **Không chứa OTP, reset token, email người nhận hoặc PII không cần thiết.**
7. **Có contract phiên bản:** thuật toán đổi phải xử lý idempotency window cũ.

Ví dụ:

~~~text
(tenantId, messageKey)

messageKey =
    mailType + ":" + businessEventId + ":" + recipientId
~~~

Với các thành phần có định dạng cố định như UUID và enum, dấu `:` dễ sử dụng. Nếu key được ghép từ chuỗi tự do có thể chứa delimiter, cần length-prefix/canonical serialization để tránh hai bộ dữ liệu khác nhau cho cùng một chuỗi.

### 4.1. Một factory không sử dụng thời gian hiện tại

~~~java
import java.util.Objects;
import java.util.UUID;

public final class MailKeys {
    private MailKeys() {}

    public static String orderConfirmed(
            UUID eventId,
            UUID recipientId) {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(recipientId);
        return "order-confirmation:"
                + eventId + ":" + recipientId;
    }

    public static String invoiceIssued(
            UUID invoiceEventId,
            UUID recipientId) {
        Objects.requireNonNull(invoiceEventId);
        Objects.requireNonNull(recipientId);
        return "invoice:"
                + invoiceEventId + ":" + recipientId;
    }
}
~~~

Caller:

~~~java
String key = MailKeys.orderConfirmed(
        event.id(),
        customer.id());
~~~

Điều kiện tiên quyết: `event.id()` đã được sinh **một lần và lưu bền vững** tại nguồn nghiệp vụ. Nếu producer gán ID mới ở mỗi lần publish cùng event, consumer không thể tự biết chúng là một ý định.

### 4.2. Những khóa sai thường gặp

~~~java
// Sai: đổi sau mỗi lần consumer retry.
String key1 = UUID.randomUUID().toString();

// Sai: đổi sau mỗi giây, dù cùng event.
String key2 = "order:" + orderId + ":" + Instant.now();

// Sai: mọi email khác loại của đơn đều trùng key.
String key3 = "order:" + orderId;

// Sai: đưa bí mật vào database index/log.
String key4 = "otp:" + otpValue + ":" + emailAddress;
~~~

Đừng dùng subject/body hash làm identity chính. Hai yêu cầu hợp lệ có thể có cùng nội dung; cùng một ý định retry cũng có thể được render bằng template version khác tùy chính sách.

### 4.3. Namespace và unique scope

~~~text
Tenant A: invoice:evt-12:recipient-8
Tenant B: invoice:evt-12:recipient-8
~~~

Hai chuỗi giống nhau có thể là hai yêu cầu hợp lệ ở hai tenant khác nhau. Vì vậy database thường ràng buộc:

~~~sql
UNIQUE (tenant_id, message_key)
~~~

Tenant ID phải lấy từ context đáng tin, không chỉ từ một field request tự do.

### 4.4. Template version có nên nằm trong key?

Thường **không nên** đưa template version vào identity nếu cùng business event/recipient chỉ được gửi một lần. Nếu template v1 được nâng lên v2 sau một deployment, cùng event cũ có thể bị handler mới tạo key khác và gửi lần hai.

Version template nên được lưu như **metadata của command/payload**, còn thay đổi identity khi có **ý định gửi mới được phê duyệt**.

## 5. Một recipient hay nhiều recipient?

Định nghĩa logical intent phải nhất quán.

### 5.1. Một command cho một recipient

~~~text
OrderConfirmed event E
    -> Recipient A: key=order-confirmation:E:A
    -> Recipient B: key=order-confirmation:E:B
    -> Recipient C: key=order-confirmation:E:C
~~~

Mỗi recipient có job và trạng thái riêng. Ưu điểm:

- kiểm tra suppression/consent theo người nhận;
- retry không cần gửi lại cả nhóm;
- theo dõi bounce/delivery riêng;
- tránh lộ danh sách người nhận qua To/Cc;
- tránh nhập nhằng partial SMTP acceptance.

### 5.2. Một MIME message gửi cho nhiều người

Với một email chứa To, Cc và Bcc, logical intent có thể là **một nhóm recipients**. Khi đó, command phải mô tả chính xác danh sách, và payload fingerprint cần tính cả recipient identity theo quy tắc đã định.

SMTP có thể chấp nhận một số recipient nhưng từ chối người khác. `MailSendException` không luôn có nghĩa mọi người nhận đều chưa được gửi. Nếu business cần retry/delivery chính xác tới từng người, cân nhắc **per-recipient jobs** hoặc một bảng recipient-outcome riêng.

### 5.3. Newsletter theo occurrence

Ví dụ:

~~~text
scheduleId    = weekly-newsletter
occurrenceKey = 2026-W46
recipientId   = subscriber-9
messageKey    = newsletter:2026-W46:subscriber-9
~~~

Khi generator crash rồi chạy lại, cùng occurrence và subscriber vẫn tạo cùng key. Tuần sau có occurrence key mới và được gửi hợp lệ.

Không dùng `scheduleVersion` làm thành phần duy nhất phân biệt occurrence: đổi cron/template có thể khiến cùng một bản tin tuần bị tạo hai lần.

## 6. Retry, resend, reschedule là ba nghiệp vụ khác nhau

| Tình huống | Có phải cùng ý định gửi? | Xử lý message key |
| --- | --- | --- |
| Broker redelivery cùng event | Có | Giữ nguyên |
| HTTP retry sau timeout | Có | Giữ nguyên |
| Worker SMTP retry 4xx | Có | Giữ nguyên |
| Đổi provider trong failover | Có | Giữ nguyên |
| Người dùng sửa giờ hẹn khi job chưa bắt đầu | Có, nếu policy cho phép | Giữ key, sửa lịch có version |
| Người dùng yêu cầu gửi lại một hóa đơn đã gửi | Ý định mới | Resend operation key mới |
| Người dùng yêu cầu OTP/challenge mới | Ý định mới | Challenge ID mới |
| Newsletter tuần kế tiếp | Ý định mới | Occurrence key mới |

### 6.1. Resend hợp lệ

Nếu hóa đơn đã gửi có:

~~~text
messageKey=invoice:evt-issued-1:recipient-9
state=SUBMITTED
~~~

Người dùng bấm **Gửi lại** một tuần sau. Nếu dùng lại key cũ, gateway sẽ trả job đã submitted và không phát sinh email mới. Hãy tạo một *resend intent* riêng:

~~~text
ResendRequested(requestId=resend-789)
messageKey=invoice-resend:resend-789:recipient-9
~~~

`resend-789` phải được tạo và lưu **một lần cho yêu cầu resend**, để HTTP retry của chính thao tác resend vẫn dùng key này.

### 6.2. OTP và password reset

Đừng dùng `otp:userId` cho mọi lần phát OTP. Một challenge mới nên có challenge ID mới và message key mới. Nhưng retry cùng challenge phải giữ key cũ. Không đặt mã OTP thực tế trong key, header hoặc log.

### 6.3. Reschedule giữ key

Nếu một job chưa bắt đầu được dời từ 10:00 sang 11:00, nên cập nhật `scheduled_at` với state/expected-version precondition và audit, **không tạo job ID và message key mới**.

Đừng tự coi gửi lại `MailCommand` với cùng key nhưng `notBefore` khác là lệnh sửa lịch. Submit command và reschedule job là hai API khác nhau, cần contract rõ.

## 7. Duplicate cùng key nhưng payload khác

Ví dụ nguy hiểm:

~~~text
Request A:
  key=invoice:evt-123:recipient-9
  recipient=alice@example.net
  invoiceAmount=100

Request B:
  key=invoice:evt-123:recipient-9
  recipient=bob@example.net
  invoiceAmount=900
~~~

Nếu repository gặp key đã tồn tại rồi trả success mà **không kiểm tra payload**, một bug nghiêm trọng bị che giấu.

Quy tắc:

- **Cùng key, cùng ý định và các trường bất biến tương đương:** trả job cũ, không tạo job mới.
- **Cùng key nhưng khác trường bất biến:** báo `IDEMPOTENCY_CONFLICT`, không cập nhật âm thầm.

### 7.1. Fingerprint là trợ giúp, không phải identity duy nhất

Có thể lưu:

~~~text
payload_fingerprint =
    SHA-256(canonical immutable command fields)
~~~

Điều kiện:

- serialization deterministic, thứ tự fields cố định;
- dùng UTF-8, timezone/Instant ổn định;
- loại trừ trace ID, attempt count, createdAt động;
- có version của canonicalization để nâng cấp an toàn;
- không giả định hash thay authorization/validation;
- cân nhắc HMAC hoặc so sánh các IDs đã bảo vệ nếu payload nhạy cảm/entropy thấp.

Đặc biệt, các trường **cố ý cho sửa** (như `scheduled_at` thông qua reschedule API) không nên làm duplicate retry bị báo conflict chỉ vì bản ghi hiện tại đã được chỉnh lịch. Có thể lưu **original command fingerprint** bất biến riêng với **mutable job scheduling state**.

### 7.2. Không cập nhật lại job khi trùng key

Một upsert như:

~~~sql
ON CONFLICT (tenant_id, message_key)
DO UPDATE SET
    state = 'PENDING',
    recipient_address = EXCLUDED.recipient_address;
~~~

là nguy hiểm: một event lặp có thể đặt lại job `SUBMITTED` thành `PENDING` và gửi lại; hoặc thay recipient của job cũ.

Idempotent insert nên **DO NOTHING rồi đọc job cũ và so sánh**. Lệnh sửa request là workflow riêng có phân quyền, state precondition và audit.

## 8. Lưu command thành durable outbox

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id                  UUID PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    message_key         VARCHAR(240) NOT NULL,
    source_event_id     UUID,
    mail_type           VARCHAR(80) NOT NULL,
    recipient_id        UUID NOT NULL,
    recipient_address   VARCHAR(320) NOT NULL,
    sender_profile      VARCHAR(80) NOT NULL,
    template_id         VARCHAR(120) NOT NULL,
    payload_ref         VARCHAR(400) NOT NULL,
    command_fingerprint VARCHAR(128) NOT NULL,
    state               VARCHAR(40) NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ,
    lease_owner         VARCHAR(120),
    lease_until         TIMESTAMPTZ,
    lease_version       BIGINT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_outbox_tenant_message
        UNIQUE (tenant_id, message_key)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (state, scheduled_at, next_attempt_at);

CREATE INDEX idx_mail_outbox_tenant_created
    ON mail_outbox (tenant_id, created_at DESC);
~~~

Đây là schema minh họa, chưa bao gồm encryption/partition/retention phù hợp production. `recipient_address` và `payload_ref` có thể là dữ liệu nhạy cảm, cần quyền truy cập và thời hạn lưu.

### 8.1. Unique constraint là rào chắn chống duplicate

Cách check-then-insert:

~~~java
if (!repository.existsByMessageKey(key)) {
    repository.save(newJob);
}
~~~

không đủ khi hai thread cùng chạy:

~~~text
Thread A: SELECT key -> missing
Thread B: SELECT key -> missing
Thread A: INSERT
Thread B: INSERT
~~~

Ràng buộc `UNIQUE (tenant_id, message_key)` tại DB thực thi tính duy nhất dưới cạnh tranh và giữa nhiều application replicas.

### 8.2. Bảng attempt

~~~sql
CREATE TABLE mail_attempt (
    id                  UUID PRIMARY KEY,
    mail_job_id         UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_number      INTEGER NOT NULL,
    provider            VARCHAR(80) NOT NULL,
    transport_result    VARCHAR(40) NOT NULL,
    provider_message_id VARCHAR(200),
    error_class         VARCHAR(60),
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    UNIQUE (mail_job_id, attempt_number)
);
~~~

Một mail job có thể có nhiều attempts; không dùng attempt ID thay cho message key.

### 8.3. Tách trạng thái job khỏi delivery

Ví dụ:

~~~text
PENDING -> CLAIMED -> SUBMITTING -> SUBMITTED
                                   |
                                   +-- sau đó provider webhook
                                       DELIVERED / BOUNCED / COMPLAINT
~~~

Nếu SMTP/API adapter ném exception:

~~~text
SUBMITTING -> RETRY_WAIT
            -> FAILED_FINAL
            -> UNKNOWN
~~~

`SUBMITTED` chỉ thể hiện transport acceptance theo contract đang dùng. Không mặc định mọi accepted message đã vào Inbox.

## 9. Atomic insert và xử lý trùng

Với PostgreSQL:

~~~sql
INSERT INTO mail_outbox (
    id,
    tenant_id,
    message_key,
    source_event_id,
    mail_type,
    recipient_id,
    recipient_address,
    sender_profile,
    template_id,
    payload_ref,
    command_fingerprint,
    state,
    scheduled_at,
    expires_at
)
VALUES (
    :id,
    :tenant_id,
    :message_key,
    :source_event_id,
    :mail_type,
    :recipient_id,
    :recipient_address,
    :sender_profile,
    :template_id,
    :payload_ref,
    :command_fingerprint,
    'PENDING',
    :scheduled_at,
    :expires_at
)
ON CONFLICT (tenant_id, message_key)
DO NOTHING
RETURNING id;
~~~

Gateway:

1. Nếu insert trả `id`, trả `CREATED`.
2. Nếu không có row trả về, query theo `(tenant_id, message_key)`.
3. So sánh original command fingerprint/immutable fields.
4. Nếu tương đương, trả `ALREADY_EXISTS` với **job ID cũ** và current status.
5. Nếu khác, trả **conflict**.

Trong PostgreSQL `READ COMMITTED`, một statement `SELECT` tiếp theo thường có thể thấy row đã commit gây xung đột. Vẫn cần xử lý race hiếm gặp như row bị xóa đồng thời bằng retry có giới hạn, chứ không tự sinh key mới.

### 9.1. EnqueueResult

~~~java
import java.util.UUID;

public record EnqueueResult(
        UUID jobId,
        EnqueueOutcome outcome,
        String currentState) {
}

public enum EnqueueOutcome {
    CREATED,
    ALREADY_EXISTS
}
~~~

`IDEMPOTENCY_CONFLICT` có thể là exception/application error riêng. Trả `ALREADY_EXISTS` cho request khác nội dung là sai.

### 9.2. Với mọi trạng thái, duplicate không reset job

| Trạng thái hiện có | Command cùng key, cùng payload | Hành vi |
| --- | --- | --- |
| `PENDING` | Có | Trả job ID cũ |
| `RETRY_WAIT` | Có | Không xóa retry/backoff |
| `CLAIMED` / `SUBMITTING` | Có | Không gọi SMTP lần nữa |
| `SUBMITTED` | Có | Không gửi lại |
| `FAILED_FINAL` | Có | Không âm thầm hồi sinh |
| `CANCELLED` / `SUPPRESSED` | Có | Không thay state |
| `UNKNOWN` | Có | Không retry mù |
| Bất kỳ trạng thái | Không cùng payload | Báo conflict |

Retry thủ công, hủy job, gửi lại email hoặc thay giờ gửi phải có API riêng và audit.

## 10. Transactional outbox

Tình huống:

~~~text
Business transaction:
  Order status = CONFIRMED
  Email confirmation request = PENDING
~~~

Nếu business update trong DB rồi gọi SMTP trực tiếp:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orderRepository.confirm(id);
    mailSender.send(message);
}
~~~

có thể xảy ra:

- SMTP accepted nhưng DB rollback;
- DB commit thành công nhưng process crash trước SMTP;
- SMTP timeout không rõ đã accepted chưa;
- HTTP client retry tạo hai lượt gửi.

**SMTP không tham gia DB transaction.** Annotation `@Transactional` không thể rút lại một email đã được nộp SMTP.

### 10.1. Ghi order và outbox trong cùng DB transaction

~~~mermaid
sequenceDiagram
    participant API as Order service
    participant DB as Business DB / outbox
    participant W as Mail worker
    participant S as SMTP relay
    API->>DB: BEGIN
    API->>DB: UPDATE order status
    API->>DB: INSERT mail_outbox by messageKey
    API->>DB: COMMIT
    W->>DB: Claim due job
    W->>S: Submit MimeMessage
    S-->>W: Accepted / error / unknown
    W->>DB: Record attempt and state
~~~

Khi business entity và mail outbox cùng transactional datasource, chúng có thể commit atomically. Nếu ở hai database khác nhau, `@Transactional` đơn giản không tạo atomic commit giữa cả hai; cần source outbox/event relay hoặc cơ chế nhất quán khác.

### 10.2. Service minh họa

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {
    private final OrderRepository orders;
    private final MailCommandGateway gateway;

    public OrderConfirmationService(
            OrderRepository orders,
            MailCommandGateway gateway) {
        this.orders = orders;
        this.gateway = gateway;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        OrderConfirmed event =
                orders.confirmAndReturnStableEvent(orderId);

        MailCommand command =
                MailCommands.forOrderConfirmed(event);

        gateway.enqueue(command);
    }
}
~~~

`OrderConfirmed`, `OrderRepository`, `MailCommands` và `MailCommandGateway` là code ứng dụng minh họa, không phải API có sẵn của Spring Mail. Event ID phải stable qua retry của lệnh confirm order. Gateway phải insert outbox **cùng transaction** và **không gọi SMTP**.

### 10.3. Gateway khác SMTP adapter

~~~java
public interface MailCommandGateway {
    EnqueueResult enqueue(MailCommand command);
}
~~~

`enqueue` thành công chỉ nghĩa command **được lưu** hoặc **đã tồn tại**. Worker mới là nơi gọi `JavaMailSender.send(...)`. API không được trả “đã delivered” chỉ vì enqueue thành công.

## 11. Worker claim và concurrency

Message key chống tạo duplicate job, nhưng hai worker vẫn có thể **cùng gửi một job** nếu chỉ SELECT rồi send.

### 11.1. Atomic claim bằng PostgreSQL

~~~sql
WITH due AS (
    SELECT id
    FROM mail_outbox
    WHERE state IN ('PENDING', 'RETRY_WAIT')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (
          next_attempt_at IS NULL
          OR next_attempt_at <= CURRENT_TIMESTAMP
      )
      AND (
          expires_at IS NULL
          OR expires_at > CURRENT_TIMESTAMP
      )
    ORDER BY scheduled_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS m
SET state = 'CLAIMED',
    lease_owner = :worker_id,
    lease_until =
        CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    lease_version = lease_version + 1,
    updated_at = CURRENT_TIMESTAMP
FROM due
WHERE m.id = due.id
RETURNING m.*;
~~~

`SKIP LOCKED` giúp mỗi worker claim những row khác nhau. Sau claim, transaction commit, worker mới thực hiện SMTP. Không giữ DB row lock suốt một lần gọi mạng dài.

### 11.2. Lease và fencing token

Ví dụ:

~~~text
Worker A claim job (lease_version=8).
Worker A bị pause.
Lease hết hạn.
Worker B claim job (lease_version=9).
Worker A tỉnh lại và cố ghi SUBMITTED.
~~~

Nên update có điều kiện:

~~~sql
UPDATE mail_outbox
SET state = :new_state,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :job_id
  AND lease_owner = :worker_id
  AND lease_version = :expected_lease_version
  AND state = 'SUBMITTING';
~~~

Nếu affected rows = 0, worker mất quyền ghi trạng thái. **Fencing trong DB chỉ ngăn stale updates**, không ngăn được SMTP request mà worker cũ đã phát ra. Đây là lý do cần policy cho kết quả uncertain.

### 11.3. Không giữ transaction qua SMTP

~~~text
Transaction A:
  Claim job + commit.

Network phase:
  Prepare MIME, send via SMTP/API.

Transaction B:
  Record attempt and resulting state + commit.
~~~

Nếu worker chết giữa network phase và transaction B, DB có thể chưa biết kết quả thật. Dùng attempt history, lease expiry detection và reconciliation; không tự reset mọi `SUBMITTING` về `PENDING`.

## 12. Retry không đổi message key

~~~text
jobId=job-1
messageKey=invoice:evt-7:recipient-9

attempt-1 -> SMTP 451
attempt-2 -> timeout
attempt-3 -> accepted
~~~

Sau cả ba lần:

~~~text
logical jobs = 1
SMTP attempts = 3
message key = giữ nguyên
~~~

`attempt_number` và `provider_message_id` là metadata của lần gửi, không phải một phần của message key.

### 12.1. Các outcome quan trọng

| Kết quả | Ý nghĩa | Xử lý |
| --- | --- | --- |
| `ACCEPTED` | SMTP/API chấp nhận theo contract | Đánh dấu submitted |
| `RETRYABLE_FAILURE` | Lỗi phù hợp thử lại | Backoff và retry có giới hạn |
| `PERMANENT_FAILURE` | Không nên retry tự động | Failed final/quarantine |
| `UNKNOWN` | Không biết transport đã nhận chưa | Reconciliation hoặc policy thủ công |
| `PARTIAL` | Một số recipients được chấp nhận | Xử lý recipient-level nếu cần |

### 12.2. Rủi ro double SMTP submission

~~~text
T1 Worker gửi message K.
T2 SMTP server trả 250 accepted.
T3 Worker crash trước khi DB ghi SUBMITTED.
T4 Recovery thấy trạng thái chưa terminal.
T5 Worker retry cùng K.
~~~

Vẫn chỉ một job trong DB nhưng provider có thể nhận **hai email**. Không có exactly-once SMTP phổ quát chỉ nhờ unique key. Biện pháp giảm rủi ro:

- lưu attempt IDs và thời điểm;
- nhận diện `UNKNOWN` thay vì khẳng định NOT_SENT;
- tra provider message ID/event nếu hỗ trợ;
- chỉ dùng provider idempotency token khi **tài liệu provider bảo đảm semantics phù hợp**;
- cân nhắc deadline và tính nhạy cảm của mail type;
- thiết kế email sao cho duplicate không trực tiếp thực hiện lại giao dịch.

### 12.3. Backoff, expiry và suppression

Một worker production cần kiểm tra:

- `next_attempt_at` và max attempts;
- error class (network, auth, recipient reject, quota);
- `expires_at` (OTP/token có thể hết hạn);
- consent/unsubscribe marketing ngay trước gửi;
- suppression từ hard bounce/complaint theo chính sách;
- trạng thái cancel và quyền gửi của sender.

Khi job không còn đủ điều kiện, đánh dấu `SUPPRESSED`, `EXPIRED` hoặc `FAILED_FINAL` theo hợp đồng ứng dụng, không xóa request vô dấu vết.

## 13. Tạo MimeMessage từ command

Worker sẽ lấy command snapshot và render:

~~~text
Durable MailRequest
    -> resolve SenderProfile
    -> load payload/template snapshot
    -> re-check recipient eligibility
    -> render text/plain + text/html
    -> optional attachment / inline resource
    -> create MimeMessage
    -> JavaMailSender.send(...)
~~~

### 13.1. Ví dụ composer

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MimeComposer {
    public MimeMessage compose(
            JavaMailSender sender,
            String from,
            String to,
            String subject,
            String plain,
            String html,
            String safeCorrelationId)
            throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom(from);
        helper.setTo(to);
        helper.setSubject(subject);
        helper.setText(plain, html);

        if (safeCorrelationId != null) {
            mime.setHeader(
                    "X-Correlation-Id",
                    safeCorrelationId);
        }

        return mime;
    }
}
~~~

`X-Correlation-Id` là header tùy chọn, không phải SMTP idempotency protocol. Giá trị phải được validate, không chứa CR/LF, PII hoặc secret, và không được tin là provider sẽ giữ nguyên.

### 13.2. Có nên đưa message key vào header?

Một hệ thống có thể thêm:

~~~text
X-Notification-Ref: notif-7e32...
~~~

để đối chiếu raw email với job. Nên dùng một **opaque correlation token** thay vì business message key chứa order ID/recipient ID. Header có thể bị chuyển tiếp, lưu lại hoặc bị provider bỏ. Không có chuẩn SMTP phổ quát tự dedupe theo `X-Message-Key`.

### 13.3. Render lúc enqueue hay lúc send?

| Cách | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Snapshot nội dung khi enqueue | Tính bất biến, audit dễ | Tốn storage, token có thể hết hạn |
| Render khi send | Dùng trạng thái mới nhất | Nội dung có thể khác preview, dữ liệu có thể đổi/xóa |

Với hóa đơn, snapshot tài liệu đã phát hành thường quan trọng. Với thông báo trạng thái, có thể cần kiểm tra lại business state. Với OTP, phải bảo đảm token còn hiệu lực ở lúc gửi.

Message key nhận diện ý định; **chính sách snapshot/version** xác định nội dung của ý định đó qua retry.

## 14. Scheduling và message key

Một yêu cầu có thể được lên lịch:

~~~text
messageKey  = scheduled-notice:request-abc:recipient-9
scheduledAt = 2026-11-13T03:00:00Z
expiresAt   = 2026-11-13T04:00:00Z
~~~

Nếu người dùng đổi giờ gửi từ 10:00 sang 11:00 nhưng vẫn là **cùng một yêu cầu**, hãy:

1. Kiểm tra owner/tenant.
2. Kiểm tra `PENDING` chưa claim/attempt và expected version.
3. Cập nhật `scheduled_at` trong transaction.
4. Giữ nguyên job ID và message key.
5. Ghi audit old/new time.

Đừng cấu tạo key bằng timestamp của một job có thể đổi giờ:

~~~text
Bad:  notification:recipient-9:2026-11-13T10:00
Good: notification:request-abc:recipient-9
~~~

Khi timestamp thay đổi, khóa bad tạo nguy cơ lưu hai job cùng ý định.

### 14.1. Command submit khác command reschedule

Một API gửi lại `MailCommand` với cùng key nhưng giờ mới không nên tự sửa job. Tách:

~~~text
EnqueueMail(MailCommand)
RescheduleMail(jobId, expectedVersion, newTime)
CancelMail(jobId, expectedVersion, reason)
RequestResend(originalJobId, resendRequestId)
~~~

Mỗi thao tác có quyền, state machine và audit riêng.

### 14.2. Occurrence của lịch định kỳ

Với bản tin mỗi tuần:

~~~text
scheduleId    = weekly-newsletter
occurrenceKey = 2026-W46
recipientId   = subscriber-9
messageKey    = newsletter:2026-W46:subscriber-9
~~~

Nếu admin đổi thứ Hai sang thứ Ba trong cùng tuần, không nên tạo occurrence W46 thứ hai khi business contract chỉ cho phép **một bản tin/tuần**. Unique key phải dựa trên identity của occurrence, không dựa trên thời điểm thực thi cron.

## 15. API HTTP và Idempotency-Key

Ví dụ:

~~~http
POST /api/notifications
Idempotency-Key: req-9d31e...
Content-Type: application/json

{
  "mailType": "ORDER_CONFIRMATION",
  "recipientId": "recipient-9",
  "businessEventId": "evt-123",
  "templateId": "order-confirmation"
}
~~~

Đây là API do ứng dụng thiết kế, không phải endpoint sẵn có của Spring Mail.

### 15.1. Khi key do client cung cấp

Server phải:

- xác thực principal và tenant;
- kiểm tra key format/length;
- ràng buộc key với operation/route/tenant;
- lưu request fingerprint và response bền vững;
- trả kết quả cũ khi retry cùng key/payload;
- trả conflict nếu cùng key nhưng payload khác;
- có retention window công bố;
- rate-limit để tránh tạo vô hạn keys.

**Idempotency-Key không phải token xác thực.** Biết/đoán key không cấp quyền đọc job thuộc tenant khác.

### 15.2. Phản hồi phù hợp

| Tình huống | Response gợi ý |
| --- | --- |
| New job created | `202 Accepted` + job ID |
| Cùng key/payload | `200 OK` hoặc `202 Accepted` với job ID cũ |
| Cùng key/payload khác | `409 Conflict` |
| Dữ liệu không hợp lệ | `400 Bad Request` |
| Không được phép dùng sender/tenant | Response phân quyền phù hợp |

`202 Accepted` có nghĩa job đã được tiếp nhận theo contract, **không có nghĩa SMTP đã accepted hoặc người nhận đã đọc**. Có thể cung cấp `GET /notifications/{jobId}` để xem trạng thái, với tenant authorization.

## 16. Broker consumer và hai tầng idempotency

Broker thường có semantics at-least-once:

~~~text
Broker event E
  -> consumer tạo mail job K và COMMIT
  -> consumer crash trước khi ACK E
  -> broker giao lại E
  -> INSERT K bị unique constraint chặn
  -> trả job cũ
  -> ACK E
~~~

Phân biệt:

- **Ingestion idempotency:** event/HTTP retry không tạo trùng mail job.
- **Dispatch coordination:** nhiều worker không claim cùng row đồng thời, retry SMTP có policy rõ.

Không đồng nhất hai tầng này. Một unique key trong outbox không ngăn hoàn toàn việc worker gửi SMTP hai lần sau crash.

### 16.1. Commit trước ack

Consumer nên ack event sau khi outbox insert/lookup đã **commit**. Ack trước commit có thể làm mất yêu cầu khi process crash. Nếu ack sau commit bị mất, event redelivery sẽ được xử lý nhờ unique key.

### 16.2. Không dùng broker offset làm key mặc định

Kafka partition/offset hoặc RabbitMQ delivery tag là metadata transport, có thể thay đổi khi republish/chuyển topic. Message key nên theo business intent ổn định xuyên các lần replay.

## 17. Multi-tenant isolation và quyền gửi

Trong SaaS, một command không được phép chọn:

~~~text
tenantId = tenant-b
senderProfile = tenant-b-private-sender
payloadRef = tenant-b-invoice
~~~

chỉ vì client đưa các giá trị đó vào JSON. Gateway cần xác minh:

- tenant từ authenticated context;
- recipient thuộc tenant hoặc được phép liên hệ;
- sender/From domain đã được tenant cấp quyền;
- payload/template thuộc phạm vi tenant;
- status và audit không lộ thông tin tenant khác;
- unique scope là `(tenant_id, message_key)`.

### 17.1. Message key không thay thế rate-limit

Một client có thể tạo hàng triệu commands với key khác nhau. Idempotency chỉ chặn **lặp cùng ý định**, không chặn spam/abuse. Production còn cần quota, max pending, consent, fair scheduling, payload size limits và provider capacity management.

### 17.2. Không đưa key chứa PII vào metrics

Sai:

~~~text
mail_jobs_created_total{message_key="invoice:evt-1:alice@example.net"}
~~~

Metrics nên có tags hữu hạn như:

~~~text
mail_type=invoice|otp|newsletter
sender_profile=tx_primary|marketing_primary
result=created|duplicate|conflict
~~~

Job ID/key phục vụ log chi tiết và DB queries có phân quyền, không làm Prometheus label tăng theo từng request.

## 18. Retention và idempotency horizon

Nếu xóa toàn bộ mail jobs sau 7 ngày, event cũ được redeliver vào ngày thứ 8 có thể tạo lại job vì key không còn trong unique index.

Phải định nghĩa:

- event hoặc HTTP retry có thể quay lại sau bao lâu?
- trong bao lâu phải chặn cùng business intent?
- khi nào một resend là một intent mới?
- bao lâu được phép giữ metadata vì quyền riêng tư?

Một lựa chọn là giữ **idempotency tombstone**:

~~~text
tenantId
messageKey
originalCommandFingerprint
finalOutcome
createdAt / retentionUntil
~~~

và xóa body/attachment/recipient snapshot sớm hơn nếu policy cho phép.

Không thể bảo đảm dedupe lâu hơn **horizon lưu vết** nếu mọi key đã bị xóa. Ngược lại, giữ dữ liệu cá nhân vĩnh viễn để chống trùng cũng không thích hợp. Phải thiết kế retention theo nhu cầu nghiệp vụ và quy định áp dụng.

### 18.1. Không tái sử dụng cùng key cho intent mới

Nếu đã kết thúc idempotency window và một operation cần được lặp hợp lệ, nên dùng **operation/occurrence ID mới**, thay vì cố recycle một key cũ có semantics không rõ.

### 18.2. Thay thuật toán tạo key

Khi thay key format v1 sang v2:

~~~text
v1: ORDER:evt-123:recipient-9
v2: order-confirmation:evt-123:recipient-9
~~~

cùng event có thể tạo hai keys khác nhau. Cần migration/version compatibility hoặc mapping/tombstone để replay event cũ vẫn nhận ra logical intent; không âm thầm deploy thuật toán mới giữa lúc replay window còn mở.

## 19. Metrics và audit

Nên phân biệt các đơn vị:

| Metric đề xuất | Đơn vị |
| --- | --- |
| `mail_command_received_total` | Lần gateway nhận command |
| `mail_job_created_total` | Logical jobs mới |
| `mail_command_duplicate_total` | Command trùng được nhận diện |
| `mail_command_conflict_total` | Cùng key, khác payload |
| `mail_outbox_pending` | Jobs còn pending |
| `mail_oldest_eligible_age_seconds` | Tuổi job đủ điều kiện nhưng chưa claim |
| `mail_submission_attempts_total` | SMTP/API attempts |
| `mail_unknown_submission_total` | Attempts chưa rõ kết quả |
| `mail_worker_lease_expired_total` | Jobs cần recovery |

Tên metrics là gợi ý để instrument, không phải tất cả đều do Spring Mail tự phát.

### 19.1. Đừng đếm retry thành mail mới

~~~text
1 logical job
3 SMTP attempts
1 submitted outcome
~~~

Dashboard phải thể hiện jobs created = 1, attempts = 3. Nếu broker giao event thêm một lần, commands received có thể tăng, duplicate count tăng, nhưng jobs created vẫn = 1.

### 19.2. Log metadata an toàn

~~~text
event=mail_command_duplicate
mailType=ORDER_CONFIRMATION
senderProfile=tx_primary
jobRef=job-752
result=ALREADY_EXISTS
~~~

Không log password, OTP, token, raw body, attachment hoặc recipient không cần thiết. Message key có thể mang business ID; dùng opaque job reference trong những log có phạm vi xem rộng.

### 19.3. Alerts

- Tỷ lệ message-key conflict tăng sau deployment.
- Duplicate events tăng bất thường do broker redelivery.
- Backlog tăng dù SMTP attempt rate thấp.
- UNKNOWN submission và expired leases tăng.
- Số attempts cao bất thường trên mỗi logical job.
- Tombstone/idempotency metadata được purge quá sớm.

Khi drill-down tenant hoặc message key, backend vẫn phải kiểm tra quyền truy cập.

## 20. Unit test tạo key

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class MailKeysTest {

    @Test
    void sameIntentProducesSameKey() {
        UUID eventId = UUID.randomUUID();
        UUID recipientId = UUID.randomUUID();

        assertEquals(
                MailKeys.orderConfirmed(eventId, recipientId),
                MailKeys.orderConfirmed(eventId, recipientId));
    }

    @Test
    void differentRecipientsProduceDifferentKeys() {
        UUID eventId = UUID.randomUUID();
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();

        assertNotEquals(
                MailKeys.orderConfirmed(eventId, first),
                MailKeys.orderConfirmed(eventId, second));
    }

    @Test
    void mailTypesDoNotShareKey() {
        UUID eventId = UUID.randomUUID();
        UUID recipientId = UUID.randomUUID();

        assertNotEquals(
                MailKeys.orderConfirmed(eventId, recipientId),
                MailKeys.invoiceIssued(eventId, recipientId));
    }
}
~~~

Các test trên xác minh factory, chưa chứng minh event ID thật bền vững hay database unique hoạt động dưới concurrency.

### 20.1. Test validation của command

Nên kiểm tra:

- key null/rỗng/quá dài → từ chối;
- tenant, recipient, type, template thiếu → từ chối;
- deadline không lớn hơn notBefore → từ chối;
- recipient không thuộc tenant → từ chối ở gateway;
- sender không được phép theo mail type → từ chối;
- payloadRef cross-tenant → từ chối;
- input chứa CR/LF bất hợp lệ trong header value → không đưa thẳng vào `MimeMessage`.

## 21. Integration test với database và SMTP giả lập

### 21.1. Cùng command enqueue hai lần

~~~text
enqueue(K, payload P) -> CREATED, job-1
enqueue(K, payload P) -> ALREADY_EXISTS, job-1

Assert:
  mail_outbox có đúng một row (tenant,K).
  không có SMTP call khi enqueue.
~~~

### 21.2. Hai transaction đồng thời

Với PostgreSQL/Testcontainers, cho hai threads cùng enqueue K (dùng barrier/latch):

~~~text
Thread A: INSERT K
Thread B: INSERT K

Expected:
  một insert CREATED
  caller còn lại ALREADY_EXISTS
  chỉ một row tồn tại
~~~

Mock repository không chứng minh được unique constraint và transaction isolation thật. Khi test concurrency, tránh dựa hoàn toàn vào `Thread.sleep(...)`.

### 21.3. Cùng key khác payload

~~~text
enqueue(K, recipient=A) -> CREATED
enqueue(K, recipient=B) -> CONFLICT
~~~

Assert row cũ giữ nguyên recipient, payload và state; không reset `SUBMITTED` thành `PENDING`.

### 21.4. Broker redelivery sau commit

1. Consumer insert outbox K, commit.
2. Giả lập crash trước broker ack.
3. Broker giao lại event gốc.
4. Consumer tạo cùng K.
5. DB trả job cũ, không tạo một yêu cầu nữa.

### 21.5. Worker contention và lease recovery

- Hai workers không claim cùng job đồng thời.
- `lease_version` ngăn stale worker ghi state.
- Job scheduled ở tương lai không được gửi trước.
- `CANCELLED` hoặc `SUPPRESSED` không được gửi.
- Crash sau SMTP accepted nhưng trước DB commit được phân loại uncertain, không retry mù.

### 21.6. SMTP outcomes

Test với GreenMail/Mailpit hoặc fake SMTP:

- accepted;
- lỗi kết nối trước gửi;
- 4xx tạm thời;
- 5xx vĩnh viễn theo provider policy;
- timeout sau khi server có thể đã nhận data;
- partial recipient rejection nếu ứng dụng hỗ trợ multi-recipient.

Không assert exactly-once SMTP khi không có provider contract. Test phải chứng minh **hệ thống xử lý trạng thái uncertain theo policy đã chọn**.

### 21.7. Cleanup

Test phải dọn outbox rows, attempts, mailbox, broker events, worker tasks và attachment files thuộc fixture. Không purge tài nguyên dùng chung khi test chạy song song.

## 22. Một kịch bản production đầy đủ

Sự kiện:

~~~text
OrderConfirmed:
  eventId    = evt-123
  tenantId   = tenant-17
  orderId    = order-456
  customerId = recipient-9
~~~

Command:

~~~text
messageKey    = order-confirmation:evt-123:recipient-9
mailType      = ORDER_CONFIRMATION
senderProfile = TX_PRIMARY
templateId    = order-confirmation
payloadRef    = order-snapshot:order-456:v2
~~~

### 22.1. Bình thường

~~~text
T1 Business event committed.
T2 Consumer tạo command K.
T3 Gateway INSERT outbox K -> job-1 PENDING.
T4 Worker claim job-1.
T5 Worker render MIME, submit SMTP.
T6 SMTP accepted.
T7 DB lưu attempt và job-1 SUBMITTED.
T8 Provider delivery event có thể đến sau đó.
~~~

### 22.2. Broker giao lại

~~~text
T9 Broker redeliver evt-123.
T10 Consumer tạo lại cùng K.
T11 Unique constraint tìm job-1.
T12 Gateway trả ALREADY_EXISTS.
T13 Không có job-2.
~~~

### 22.3. SMTP timeout sau DATA

~~~text
T5 Worker submit SMTP.
T6 Server có thể đã nhận message.
T7 Client timeout trước khi thấy kết quả.
T8 Worker ghi UNKNOWN và attempt metadata.
T9 Reconciliation hoặc retry policy quyết định bước tiếp theo.
~~~

Message key vẫn bảo đảm chỉ một **logical job**. Nó không thể nói liệu provider đã nhận thư hay chưa.

### 22.4. Người dùng yêu cầu resend

~~~text
ResendRequested(requestId=resend-789)
messageKey=order-confirmation-resend:resend-789:recipient-9
~~~

Đây là ý định hợp lệ mới, với key mới. Retry HTTP của chính thao tác resend vẫn phải dùng `resend-789`, không tạo thêm key khác.

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Dùng random UUID mới làm key mỗi lần handler chạy | Broker redelivery tạo job trùng | Stable business event ID |
| Dùng order ID cho mọi loại email | Confirmation chặn invoice | Key có mail type/intent |
| Đưa OTP/recipient email vào key | Rò rỉ bí mật/PII | Opaque IDs |
| Dùng RFC Message-ID thay business key | Sinh muộn, không ổn định | Tách MIME ID và message key |
| Check-then-insert không có unique DB | Race giữa workers | Unique constraint atomic |
| Duplicate upsert reset PENDING | Email đã gửi được gửi lại | DO NOTHING + compare |
| Không kiểm tra payload conflict | Bug bị che, sai người nhận | Fingerprint + 409 conflict |
| Attempt number làm key | Retry tạo logical job mới | Một key cho mọi attempts |
| Timestamp làm key của job có thể reschedule | Đổi lịch tạo duplicate | Stable request ID |
| Gửi SMTP trong business transaction | DB rollback không thu hồi mail | Transactional outbox |
| Coi `@Transactional` cho exactly-once SMTP | Sai guarantee | UNKNOWN/reconciliation |
| Hai workers SELECT rồi send không lock | Cùng row gửi hai lần | Atomic claim + lease |
| Mất lease thì retry mù | Có thể gửi trùng | Fencing + uncertainty policy |
| Một MIME nhiều recipients không theo dõi partial | Retry gửi lại người đã nhận | Per-recipient outcome |
| Xóa tombstone quá sớm | Event cũ tạo job mới | Retention theo horizon |
| Dùng key làm metric label | Cardinality lớn, lộ dữ liệu | Bounded labels |
| Nhận tenantId không qua authorization | Cross-tenant access | Tenant context đáng tin |
| API enqueue báo Delivered | Sai nghĩa trạng thái | Accepted/Submitted/Delivered riêng |
| Gửi lại chủ động nhưng dùng key cũ | Không tạo email resend | Resend operation ID mới |

## 24. Checklist triển khai

### Business command

- [ ] MailCommand có contract rõ và bất biến về ý định gửi.
- [ ] Message key dựa trên business event/request ID được lưu bền vững.
- [ ] Key phân biệt mail type, recipient, occurrence và tenant đúng scope.
- [ ] Retry/redelivery giữ key; resend intent mới có key mới.
- [ ] Key không chứa OTP, password, token hoặc PII không cần thiết.

### Persistence

- [ ] Có `UNIQUE (tenant_id, message_key)` hoặc cơ chế atomic tương đương.
- [ ] Duplicate cùng command trả job cũ; khác command báo conflict.
- [ ] Không reset job state khi upsert duplicate.
- [ ] Business DB/outbox transaction có atomicity đúng.
- [ ] Có retention/idempotency tombstone phù hợp.

### Worker và SMTP

- [ ] Atomic claim, lease/fencing token cho workers đa replica.
- [ ] Retry attempts tách khỏi logical jobs.
- [ ] SMTP send ngoài DB transaction dài.
- [ ] Có backoff, deadline, suppression và cancel policy.
- [ ] Có UNKNOWN/reconciliation, không hứa exactly-once SMTP.
- [ ] Có recipient-level handling khi message nhiều người nhận.

### Bảo mật và vận hành

- [ ] Tenant, sender, recipient, template và payload được authorize.
- [ ] SMTP credentials chỉ ở secret configuration, không ở command.
- [ ] Metrics tách commands, jobs, attempts và provider events.
- [ ] Không dùng message key/job ID làm high-cardinality metrics labels.
- [ ] Có audit, tracing, dashboard backlog/error và retention.

### Kiểm thử

- [ ] Unit test key ổn định và phân biệt business intents.
- [ ] Integration test DB unique dưới concurrency.
- [ ] Test duplicate vs payload conflict.
- [ ] Test broker redelivery sau commit.
- [ ] Test worker claim/lease và crash recovery.
- [ ] Test SMTP timeout/UNKNOWN và không giả định exactly-once.
- [ ] Test reschedule giữ identity, resend sinh intent mới.

## 25. Những điều cần nhớ

- **Mail Command** là mô hình của một ý định gửi theo nghiệp vụ, **message key** là định danh idempotency của ý định đó.
- Message key phải được tạo ở nơi hiểu **business event/request**, không phải nơi tạo MIME hay gọi SMTP.
- **Cùng một intent retry phải dùng cùng key; một resend mới có key mới.**
- Tenant, mail type, event/occurrence và recipient thường cần tham gia xác định scope.
- Job ID, attempt ID, RFC Message-ID và provider message ID có mục đích riêng.
- **Unique database constraint** chống duplicate job an toàn hơn check-then-insert đơn giản.
- Cùng key/payload trả job cũ; cùng key nhưng payload khác phải báo conflict.
- **Transactional outbox** giúp lưu yêu cầu gửi cùng dữ liệu nghiệp vụ; worker gửi sau commit.
- Atomic claim và lease giảm xử lý trùng giữa workers nhưng không loại bỏ mọi rủi ro double SMTP submission.
- `JavaMailSender.send(...)` trả bình thường là submission theo transport contract, **không chắc inbox delivered**.
- Khi kết quả SMTP không rõ, cần trạng thái **UNKNOWN**, reconciliation và policy retry có kiểm soát.
- Retention/tombstone, multi-tenant authorization, bảo vệ dữ liệu và metrics có giới hạn cardinality là một phần của thiết kế.

Trong một hệ thống Spring Framework Mail đáng tin cậy, **message key là hợp đồng idempotency của nghiệp vụ**, không chỉ là một chuỗi UUID đặt trong email header. Khi kết hợp command rõ ràng, stable key, unique DB constraint, transactional outbox, worker claim và xử lý retry minh bạch, ứng dụng có thể tiếp nhận lại cùng một yêu cầu mà không làm phình hàng đợi, đồng thời hiểu rõ giới hạn thực tế của việc chống gửi trùng ở tầng SMTP.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và transport exceptions.
- **Spring Framework Reference — Transaction Management:** `@Transactional` và transaction boundaries.
- **Spring Integration Reference:** message channels, broker integration và error handling khi áp dụng.
- **Spring Data JPA Reference:** optimistic locking, `@Version` và persistence.
- **Jakarta Mail API — MimeMessage:** `Message-ID`, MIME headers, `saveChanges()` và serialization.
- **RFC 5322 — Internet Message Format:** `Message-ID` và header syntax.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP submission, recipient acceptance và lỗi.
- **PostgreSQL Documentation:** unique constraints, `ON CONFLICT`, `FOR UPDATE SKIP LOCKED`, transaction isolation.
- **Micrometer/Prometheus Documentation:** Counter, Timer, Gauge và giới hạn tag cardinality.
- **Tài liệu ESP thực tế đang dùng:** provider message IDs, webhook events, partial recipient results và idempotency API nếu có.

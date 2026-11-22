# Data retention cho nội dung và metadata email trong Spring Framework Mail

Khi một ứng dụng gửi email bằng **Spring Framework Mail**, thông điệp không chỉ tồn tại trong lời gọi `JavaMailSender.send(...)`. Trước khi gửi, ứng dụng có thể lưu yêu cầu vào transactional outbox, render template, giữ HTML và attachment. Sau khi SMTP relay nhận thư, hệ thống tiếp tục lưu trạng thái, mã phản hồi, provider message ID, bounce, complaint, lịch retry và log. Những dữ liệu này giúp vận hành nhưng có thể chứa **thông tin cá nhân, dữ liệu giao dịch, tài liệu hoặc mã xác thực nhạy cảm**.

Vì vậy, hệ thống production cần thiết kế **data retention**: dữ liệu nào được phép lưu, mục đích lưu, giữ bao lâu, ai có quyền truy cập, lúc nào xóa/vô danh hóa, cách xử lý bản sao trong log/backup/provider và bằng chứng cleanup.

> **Không giữ toàn bộ nội dung email chỉ vì tiện debug; cũng không xóa dữ liệu cần thiết trước khi hoàn thành retry, đối soát hoặc nghĩa vụ hợp lệ.** Phân biệt vòng đời nội dung, metadata, dấu vết vận hành và hồ sơ phải giữ theo căn cứ phù hợp.

`JavaMailSender` là abstraction gửi email của Spring. **Spring Mail không tự quản lý retention xuyên suốt database, object storage, SMTP provider, log và backup.** Những thành phần như `RetentionPolicy`, `MailCleanupWorker` và các bảng SQL bên dưới là mẫu thiết kế ứng dụng, không phải API mặc định của Spring.

## 1. Data retention nghĩa là gì?

Data retention là tập hợp quy tắc xác định:

1. **Thu thập:** chỉ dữ liệu cần cho chức năng và mục đích đã định.
2. **Thời hạn:** bao lâu và tính từ sự kiện nào.
3. **Quyền truy cập:** những service, role nào được phép xử lý.
4. **Kết thúc:** xóa, vô danh hóa, tổng hợp hoặc chuyển sang kho được phê duyệt.
5. **Ngoại lệ:** legal hold, tranh chấp, kiểm toán và nghĩa vụ hợp lệ.
6. **Bằng chứng:** làm thế nào biết cleanup đã hoàn thành.

Retention khác **backup**: backup là phương tiện phục hồi, không phải quyền giữ vô hạn. Retention cũng khác **lịch gửi**: `scheduledAt` xác định khi nào được submit, còn `purgeAfter` xác định thời điểm dữ liệu đủ điều kiện bị loại bỏ.

### Những câu hỏi cần có đáp án

- Có cần giữ body sau khi SMTP relay accepted?
- Cần full recipient email address hay một ID cùng status?
- Attachment phải tồn tại tới khi nào để retry không thất bại?
- `SUBMISSION_UNKNOWN` có thể xóa như `SUBMITTED` không?
- Khi có yêu cầu xóa dữ liệu, queue, DLQ, log, provider và backup xử lý ra sao?
- Suppression list được giữ thế nào để không gửi lại người đã unsubscribe?
- Ai có quyền đặt/gỡ legal hold và phạm vi giữ lại tới đâu?

**Không có một TTL cố định đúng cho mọi tổ chức.** Các mốc thời gian trong ví dụ chỉ minh họa; thời hạn thực tế phải dựa vào mục đích, loại dữ liệu, mức độ rủi ro, hợp đồng và quy định áp dụng với ý kiến của người chịu trách nhiệm pháp lý/quyền riêng tư khi cần.

## 2. Nội dung, metadata và dữ liệu vận hành

| Nhóm | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Body content | Plain text, HTML | Có thể chứa PII, hóa đơn, OTP, reset link |
| Subject | Tên người, kết quả xét duyệt | Có thể tự tiết lộ thông tin nhạy cảm |
| Headers | From, To, Cc, Bcc, Reply-To | Định danh và quan hệ liên lạc |
| SMTP envelope | MAIL FROM, RCPT TO | Có thể khác địa chỉ trong header |
| Raw MIME | Toàn bộ message, multipart | Thường chứa body, headers và attachment |
| Attachments | PDF, ảnh, hồ sơ, CSV | Có thể chứa tài liệu mật hoặc dữ liệu cá nhân |
| Template model | Tên, mã đơn, số tiền, token | Có thể nhạy cảm ngang hoặc hơn body |
| Delivery metadata | Provider, attempt ID, SMTP code, timestamp | Hữu ích vận hành nhưng vẫn có thể liên kết cá nhân |
| Provider events | Accepted, deferred, bounce, complaint | Chứa địa chỉ nhận, lý do từ chối |
| Audit records | Ai đặt lịch/gửi/hủy/đổi quyền | Cần kiểm soát truy cập và retention |
| Logs/traces/metrics | Exceptions, correlations | Dễ vô tình sao chép body hoặc secret |
| Suppression | Unsubscribe, complaint, hard bounce | Cần lưu đủ để ngăn gửi sai |
| Queue/cache/DLQ | Serialized payload, retry data | Bản sao khó phát hiện khi xóa |
| Backups/snapshots | DB/object versions | Bản sao độc lập với dữ liệu hoạt động |

**Metadata không đồng nghĩa dữ liệu vô hại.** Địa chỉ nhận, subject và thời điểm gửi có thể tiết lộ người đó đang dùng loại dịch vụ nào. Không định nghĩa retention “chỉ body là dữ liệu cá nhân, còn metadata giữ mãi”.

### Dữ liệu có thể được sao chép nhiều lần

~~~mermaid
flowchart LR
    A["Business event"] --> B["Outbox DB"]
    B --> C["Template render"]
    C --> D["Raw MIME / attachment storage"]
    D --> E["JavaMailSender / SMTP"]
    E --> F["Provider queue / events"]
    B --> G["Logs / traces"]
    E --> G
    F --> H["Event inbox / projection"]
    B --> I["DB backups"]
    D --> J["Object versions / backups"]
    H --> I
~~~

Xóa row trong `mail_outbox` **không tự xóa** object lưu HTML/MIME/attachment, DLQ, provider copy, log/APM hay backup. Retention phải có **data inventory và ownership** cho từng nơi chứa.

## 3. Gắn retention với mục đích

Các mục đích thường gặp:

1. **Hoàn tất gửi:** giữ payload đến khi submit thành công, lỗi cuối hoặc hết hạn.
2. **Retry:** cần payload, failure category và `nextAttemptAt`.
3. **Đối soát:** cần provider attempt ID khi chưa rõ kết quả.
4. **Hỗ trợ người dùng:** cần status, reason và metadata tối thiểu.
5. **Ngăn gửi ngoài ý muốn:** cần suppression/consent có scope phù hợp, không cần raw body cũ.
6. **Kiểm toán:** có thể cần dấu vết sự kiện, không nhất thiết cả email.
7. **Nghĩa vụ pháp lý/hợp đồng:** có thể cần giữ một chứng từ hoặc hồ sơ theo quy định.
8. **Analytics:** thường chỉ cần số liệu tổng hợp hoặc đã giảm định danh.

### Ví dụ theo loại email

| Loại | Dữ liệu thường nhạy cảm | Hướng thiết kế |
| --- | --- | --- |
| OTP/reset | Mã/token ngắn hạn | Không giữ plaintext quá cần thiết; purge khi hết hiệu lực |
| Xác nhận đơn hàng | Địa chỉ, sản phẩm, mã đơn | Lưu trạng thái gửi riêng; chứng từ có vòng đời nghiệp vụ riêng |
| Hóa đơn | Tài liệu và số tiền | Không xem SMTP transcript là hồ sơ kế toán chính |
| Marketing | Email address, tracking, campaign | Tôn trọng consent/suppression, giảm raw per-recipient body |
| Security alert | Thông tin đăng nhập, sự kiện bất thường | Giới hạn nội dung và người xem |
| Support mail | Nội dung tự do, tài liệu đính kèm | Retention theo ticket và data classification |

Một chứng từ nghiệp vụ có thể cần giữ lâu theo căn cứ hợp lệ, nhưng điều đó **không kéo theo** việc SMTP transcript, payload retry và bản HTML đều phải giữ cùng thời gian.

## 4. Retention inventory và policy version

| Trường | Ý nghĩa |
| --- | --- |
| `dataset` | Body, raw MIME, attachment, outbox, provider event, log |
| `purpose` | Mục đích xử lý |
| `classification` | Mức độ nhạy cảm |
| `dataOwner` | Chủ sở hữu nghiệp vụ |
| `systemOwner` | Nhóm vận hành storage |
| `retentionTrigger` | CreatedAt, terminalAt, caseClosedAt... |
| `retentionPeriod` | Thời gian được phê duyệt |
| `deletionMethod` | Delete, anonymize, aggregate, cryptographic erasure |
| `exceptions` | Legal hold, dispute, audit |
| `backupHandling` | Backup TTL và quy trình restore |
| `providerHandling` | Provider-side controls/commitments |
| `policyVersion` | Phiên bản quy tắc |
| `evidence` | Bằng chứng cleanup |

Đổi TTL trong source code nhưng không cập nhật policy, hoặc đổi policy nhưng không xử lý các bản ghi cũ, tạo ra sự không nhất quán khó giải thích. Vì vậy, mỗi record hoặc retention decision nên xác định được **phiên bản policy** đã dùng.

### Ma trận retention minh họa

| Dataset | Mốc bắt đầu | Khi có thể xóa | Dữ liệu tối thiểu có thể giữ |
| --- | --- | --- | --- |
| Unsent payload | Khi tạo yêu cầu | Khi không còn pending/retry/unknown và hết cửa sổ cần thiết | State, stop reason |
| Rendered HTML/text | Render/submit | Khi không còn cần resend hoặc support content | Template ID/hash/version |
| Raw MIME | Lúc tạo/capture | Sau mục đích kiểm tra/đối soát hợp lệ | Hash và metadata cần thiết |
| Attachment staged | Upload/stage | Sau khi mọi job tham chiếu kết thúc, hết hold/retention | Hash, type, ID |
| SMTP attempts | Khi attempt kết thúc | Sau thời gian hỗ trợ/đối soát | Số liệu tổng hợp |
| Provider webhook | Khi nhận event | Sau khi projection/audit cần thiết đã lưu | Event type, reason chuẩn hóa |
| Detailed debug log | Khi ghi | TTL log ngắn theo policy | Metric tổng hợp |
| Suppression | Unsubscribe/bounce/complaint | Theo mục đích ngăn gửi và quy định áp dụng | Định danh/flag tối thiểu |
| Backup | Khi tạo snapshot | Theo backup policy được duyệt | Bằng chứng snapshot hết hiệu lực |

Đây là **mẫu thiết kế**, không phải lịch giữ dữ liệu mang tính pháp lý. Đặc biệt suppression có thể cần tồn tại đủ lâu để tôn trọng lựa chọn ngừng nhận, nhưng phải giảm thông tin cá nhân và kiểm soát quyền sử dụng.

## 5. TTL tính từ sự kiện nào?

Một lỗi nguy hiểm là dùng cùng truy vấn:

~~~sql
DELETE FROM mail_outbox
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '14 days';
~~~

Nó có thể xóa email đặt lịch sau vài tháng **trước thời điểm được gửi**. Một email đang retry hoặc `SUBMISSION_UNKNOWN` cũng có thể bị xóa khi chưa đối soát.

Phân biệt các timestamp:

| Timestamp | Nghĩa |
| --- | --- |
| `createdAt` | Yêu cầu được lưu |
| `scheduledAt` | Thời điểm được phép gửi |
| `lastAttemptAt` | Lần submit gần nhất |
| `submittedAt` | Relay accepted theo bằng chứng có được |
| `terminalAt` | Kết thúc vòng tự động |
| `reconciledAt` | Hoàn tất đối soát unknown outcome |
| `caseClosedAt` | Kết thúc ticket/tranh chấp liên quan |
| `contentPurgeAfter` | Thời điểm được xóa payload |
| `metadataPurgeAfter` | Thời điểm được xóa metadata |
| `legalHold` | Cờ/record ngoại lệ cần quyết định riêng |

Một policy thường tính `contentPurgeAfter = terminalAt + period`, nhưng **không gán terminalAt khi job vẫn cần gửi, retry hoặc đối soát**.

### Email được đặt lịch xa

~~~text
Created:              2026-11-12
scheduledAt:          2027-01-15
status:               PENDING
Content policy:       keep until terminal, then + 14 days
~~~

Đến tháng 12/2026, payload vẫn phải tồn tại để submit tháng 1/2027. Không được xóa chỉ vì đã tạo hơn 14 ngày.

### Hủy lịch

Một lịch `CANCELLED` trước khi gửi có thể purge content sớm hơn mail đã SUBMITTED, nhưng vẫn cần giữ metadata trạng thái hủy trong cửa sổ audit/support nếu chính sách yêu cầu.

## 6. Tách vòng đời content khỏi metadata

~~~text
CREATE / PENDING / SCHEDULED
          |
          v
RETRY / PROCESSING (payload needed)
          |
          v
TERMINAL / RECONCILED
    |                  |
    v                  v
Short content TTL      Separate metadata TTL
    |                  |
Delete body/MIME       Delete/anonymize
and attachments        attempt/status records
~~~

Content purge phải xét nhiều nơi:

- `plain_text_body`, `html_body`, `subject`.
- `template_data_json`, rendered preview.
- Raw MIME và `attachment_storage_key`.
- Serialized queue/DLQ payload.
- Debug/error messages chứa nội dung.
- Cache và bản xuất cho support/analytics.

Metadata cũng phải có TTL; không giữ toàn bộ recipient address và status mãi. Có thể hard delete, pseudonymize hoặc tổng hợp, tùy quyền và mục đích.

**Pseudonymization không tự bằng anonymization.** Một HMAC của email vẫn có thể liên kết các sự kiện nếu key hoặc bảng đối chiếu còn tồn tại. Không tuyên bố đã xóa hoàn toàn danh tính chỉ vì thay email bằng hash.

## 7. Retention theo trạng thái gửi

| Trạng thái ứng dụng | Cần payload? | Cách xử lý |
| --- | --- | --- |
| PENDING | Có, để gửi tương lai | Chưa purge |
| PROCESSING | Có thể đang sử dụng | Không purge khi còn active lease |
| RETRY_PENDING | Có | Giữ đến khi hết retry/expiry |
| SUBMISSION_UNKNOWN | Có thể cần đối soát | Giữ evidence có hạn và reconcile |
| SUBMITTED | Có thể không cần raw content | Purge body sau cửa sổ cần thiết |
| FAILED_PERMANENT | Không tự retry cùng dữ liệu | Purge sau support/review window |
| CANCELLED | Không cần gửi | Purge sớm nếu không có hold |
| EXPIRED | Không còn hữu ích | Purge token/body sớm |
| DEAD_LETTER | Có thể được review/replay | TTL riêng, không giữ vô hạn |
| QUARANTINED | Nội dung có thể độc hại | Storage cô lập và retention riêng |

Đây là các trạng thái ứng dụng tự thiết kế. Spring Mail không có sẵn `SUBMISSION_UNKNOWN` hoặc `DEAD_LETTER`.

`JavaMailSender.send()` trả về bình thường thường chỉ chứng minh **SMTP relay accepted submission**, không phải thư tới Inbox. Nếu provider đã accepted và tiếp tục retry downstream, ứng dụng không cần giữ full body mãi chỉ để chờ event `DELIVERED`.

### Trường hợp kết quả không xác định

~~~text
Application                 SMTP relay
     |---- DATA + end ----->|
     |                       | may already accept
     |<--- response lost ----X
     |
     v
SUBMISSION_UNKNOWN
~~~

Không xóa attempt metadata ngay vì thiếu final response; sẽ mất khả năng đối soát. Nhưng cũng không giữ payload vô hạn: xác định reconciliation deadline, escalation và cách đóng record có audit.

## 8. OTP, reset link và nội dung nhạy cảm

Email OTP/reset có thể chứa secret ngắn hạn. Cần:

- Tránh lưu token plaintext nếu có thiết kế khác an toàn.
- Không log hoặc đưa token vào exception text.
- Chỉ worker được quyền gửi mới được đọc payload.
- Mã hóa dữ liệu at rest theo policy.
- Kết nối content TTL với `expiresAt` thực của token.
- Không gửi token đã hết hiệu lực.
- Xóa bản sao plaintext sớm sau khi không cần send/retry.

Một phương án là tạo token gần lúc dispatch nếu workflow và bảo mật cho phép, nhưng không sinh token mới tùy tiện cho mỗi SMTP retry: có thể khiến người dùng nhận nhiều mã không nhất quán. Việc xóa một trường token khỏi database không loại bỏ token đã xuất hiện trong rendered HTML, queue, provider hoặc log.

## 9. Metadata gửi mail: giữ đúng mức cần thiết

Metadata phục vụ vận hành có thể là:

~~~text
notificationId
tenantKey
providerKey
messageCategory
templateVersion
attemptNumber
smtpPhase
normalizedSmtpCode
failureCategory
submittedAt
providerEventType
~~~

Hạn chế giữ full To/Cc/Bcc, raw subject, raw SMTP transcript, provider error text không redaction, body hoặc attachment filename chứa PII.

### Event metadata ví dụ

~~~json
{
  "notificationId": "notif-184",
  "tenantKey": "tenant-01",
  "providerKey": "smtp-primary",
  "attempt": 1,
  "result": "SUBMITTED",
  "submittedAt": "2026-11-12T10:00:05Z",
  "smtpCode": "250",
  "templateVersion": "receipt-v3"
}
~~~

Đây là sanitized event nhưng `tenantKey` và `notificationId` vẫn có thể tái liên kết tới một cá nhân; áp dụng ACL và retention phù hợp.

### Provider webhook

Provider có thể gửi accepted, deferred, delivered, bounced hoặc complained. Một pipeline:

1. Xác minh signature và provider/account scope.
2. Lưu raw event vào inbox bền vững để dedup/retry.
3. Cập nhật delivery projection idempotently.
4. Xóa raw event theo TTL sau xử lý/đối soát.
5. Giữ normalized summary trong thời gian hỗ trợ được duyệt.

Provider event `DEFERRED` không tự là lý do giữ full MIME hay gửi một bản SMTP mới khi provider đã accepted và đang retry.

## 10. Luồng production từ gửi đến xóa

Một lifecycle đầy đủ:

~~~mermaid
flowchart TD
    A["Create notification"] --> B["Persist outbox and payload reference"]
    B --> C["Scheduled / due"]
    C --> D["Claim and send via JavaMailSender"]
    D --> E{"Submission outcome?"}
    E -- "Temporary" --> F["RETRY_PENDING"]
    F --> C
    E -- "Accepted" --> G["SUBMITTED"]
    E -- "Permanent" --> H["FAILED_PERMANENT"]
    E -- "Uncertain" --> I["SUBMISSION_UNKNOWN"]
    I --> J["Reconcile"]
    J --> G
    J --> H
    G --> K["Terminal or completed retention trigger"]
    H --> K
    K --> L{"Hold / reference / policy check"}
    L -- "Not eligible" --> M["Keep and re-evaluate"]
    L -- "Eligible" --> N["Purge content and objects"]
    N --> O["Retain minimal metadata until its deadline"]
    O --> P["Delete or anonymize metadata"]
~~~

Điểm quan trọng là **bộ cleanup không làm thay vai trò của dispatcher**. Dispatcher quyết định đã gửi, retry hay dừng; cleanup dựa trên trạng thái đã được xác nhận và policy để xác định dữ liệu nào không còn phải giữ.

### Tránh cleanup quá sớm

Nếu một job `PENDING` còn lịch trong tương lai, bộ cleanup không thể chỉ xem `createdAt`. Nếu email có `PROCESSING` với lease active, không được xóa attachment đang được đọc. Nếu job `SUBMISSION_UNKNOWN`, không được xóa mọi correlation trước thời hạn đối soát.

### Tránh cleanup quá muộn

Nếu email đã `CANCELLED`, `EXPIRED` hoặc `SUBMITTED` và không có nghĩa vụ giữ body, raw MIME có thể được purge trước metadata. Nếu tổ chức giữ body 10 năm “cho chắc” nhưng không còn mục đích cụ thể, dữ liệu nhạy cảm và rủi ro breach tăng mà không mang lại lợi ích tương xứng.

## 11. Retention policy dưới dạng dữ liệu

Không nên rải các biểu thức như `plusDays(30)` trong controller, worker, webhook consumer và cleanup job. Một policy service duy nhất giúp thực thi nhất quán:

~~~java
package com.example.mail.retention;

import java.time.Duration;

public record RetentionRules(
        String policyVersion,
        Duration contentAfterTerminal,
        Duration metadataAfterTerminal,
        Duration unknownOutcomeReviewWindow,
        Duration rawEventAfterProcessed,
        Duration quarantineAfterDecision) {
    public RetentionRules {
        if (contentAfterTerminal.isNegative()
                || metadataAfterTerminal.isNegative()
                || unknownOutcomeReviewWindow.isNegative()
                || rawEventAfterProcessed.isNegative()
                || quarantineAfterDecision.isNegative()) {
            throw new IllegalArgumentException(
                    "Negative retention period");
        }
    }
}
~~~

Đây là **type ứng dụng**, không phải `org.springframework.mail` API. Duration chỉ thể hiện khoảng thời gian; nếu policy theo **tháng lịch**, phải dùng phép tính lịch và timezone đúng, không mặc định `Duration.ofDays(30)` bằng một tháng.

### Ví dụ cấu hình minh họa

~~~yaml
app:
  mail:
    retention:
      policy-version: example-v1
      transactional-content-after-terminal: P7D
      transactional-metadata-after-terminal: P90D
      raw-provider-event-after-processed: P14D
      unknown-outcome-review-window: P7D
      cleanup-batch-size: 100
~~~

**Những con số trong YAML chỉ là ví dụ để minh họa cấu hình, không phải đề xuất thời hạn tối ưu hoặc yêu cầu pháp luật.** Trong triển khai thật, có thể có nhiều chính sách theo category, tenant, classification và căn cứ lưu giữ. Không cho một cờ cấu hình môi trường tự ý xóa dữ liệu ngoài phạm vi policy được phê duyệt.

### Quyết định giữ theo nhiều điều kiện

~~~text
RetentionPolicy =
    dataset
  + business category
  + data classification
  + jurisdiction/contract if applicable
  + lifecycle state
  + retention trigger
  + legal holds / special cases
  + policy version
~~~

Nên lưu dấu vết chính sách nào được sử dụng khi tính `purgeAfter`. Nếu policy đổi, có một tiến trình được kiểm soát để xét các records cũ, tránh mỗi worker tự tính thời gian khác nhau.

## 12. Database schema: payload và metadata tách riêng

Một thiết kế quan hệ có thể tách `mail_notification`, `mail_payload`, `mail_attempt` và `mail_retention_hold`. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_notification (
    id                     UUID PRIMARY KEY,
    tenant_id              VARCHAR(100) NOT NULL,
    category               VARCHAR(50) NOT NULL,
    recipient_ref          VARCHAR(200),
    status                 VARCHAR(50) NOT NULL,
    scheduled_at           TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL,
    terminal_at            TIMESTAMPTZ,
    content_purge_after    TIMESTAMPTZ,
    metadata_purge_after   TIMESTAMPTZ,
    policy_version         VARCHAR(100),
    current_generation     BIGINT NOT NULL DEFAULT 0,
    retention_hold         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE mail_payload (
    notification_id        UUID PRIMARY KEY,
    encrypted_subject      BYTEA,
    encrypted_plain_body   BYTEA,
    encrypted_html_body    BYTEA,
    encrypted_template_data BYTEA,
    object_storage_key     VARCHAR(500),
    content_sha256         VARCHAR(64),
    payload_state          VARCHAR(50) NOT NULL,
    updated_at             TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_mail_payload_notification
        FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id)
);

CREATE TABLE mail_attempt (
    id                     UUID PRIMARY KEY,
    notification_id        UUID NOT NULL,
    provider_key           VARCHAR(100) NOT NULL,
    attempt_number         INTEGER NOT NULL,
    status                 VARCHAR(50) NOT NULL,
    normalized_error       VARCHAR(100),
    smtp_code              VARCHAR(20),
    started_at             TIMESTAMPTZ NOT NULL,
    completed_at           TIMESTAMPTZ,
    CONSTRAINT fk_mail_attempt_notification
        FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id),
    CONSTRAINT unique_attempt
        UNIQUE (notification_id, attempt_number)
);

CREATE TABLE mail_retention_hold (
    id                     UUID PRIMARY KEY,
    notification_id        UUID NOT NULL,
    case_reference         VARCHAR(250) NOT NULL,
    scope                  VARCHAR(100) NOT NULL,
    hold_started_at        TIMESTAMPTZ NOT NULL,
    hold_released_at       TIMESTAMPTZ,
    approved_by            VARCHAR(150) NOT NULL,
    CONSTRAINT fk_mail_hold_notification
        FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id)
);

CREATE INDEX idx_mail_content_purge
    ON mail_notification(content_purge_after)
    WHERE content_purge_after IS NOT NULL;

CREATE INDEX idx_mail_metadata_purge
    ON mail_notification(metadata_purge_after)
    WHERE metadata_purge_after IS NOT NULL;
~~~

Schema này **mang tính minh họa**, chưa bao gồm mọi index, tenant key, encryption metadata, event inbox, object references, version tracking hay deletion audit của production. `retention_hold` boolean giúp đọc nhanh nhưng không nên là nguồn quyết định duy nhất nếu hệ thống có nhiều hold với scope riêng. Phải đọc bảng hold hoặc cơ chế có thẩm quyền.

### Vì sao không lưu tất cả trong một row?

Tách payload khỏi metadata giúp:

- Xóa body sớm nhưng giữ trạng thái gửi.
- Giới hạn quyền đọc plaintext: dispatcher đọc payload, support dashboard chỉ xem metadata.
- Không buộc mọi query/report tải blob lớn.
- Giảm rủi ro để lộ nội dung khi xuất CSV hỗ trợ khách hàng.
- Dùng lifecycle/retention riêng cho attachment object.

Nhược điểm: phức tạp hơn khi purge tham chiếu ngoài database; cần giao thức cleanup có thể retry an toàn.

### Cẩn trọng với mã hóa trong ứng dụng

Các cột `encrypted_*` chỉ biểu diễn ý tưởng. Không dùng mã hóa tự viết hoặc lưu key cạnh ciphertext. Cần:

- AEAD hoặc cơ chế được chuyên gia bảo mật phê duyệt.
- Key management, rotation và access policies.
- Xác định tenant/context binding nếu sử dụng associated data.
- Không log plaintext khi render/decrypt.
- Chính sách retention đối với key và key versions.

Mã hóa at rest **không thay thế deletion**, vì bản sao trong cache/log/provider có thể vẫn ở plaintext.

## 13. Tính purgeAfter tại thời điểm chuyển trạng thái

Một policy có thể tính deadlines khi job chuyển sang terminal, nhưng chỉ sau khi có bằng chứng kết thúc:

~~~java
package com.example.mail.retention;

import java.time.Duration;
import java.time.Instant;

public record RetentionDeadlines(
        Instant contentPurgeAfter,
        Instant metadataPurgeAfter,
        String policyVersion) {
}

public final class MailRetentionCalculator {

    public RetentionDeadlines afterTerminal(
            Instant terminalAt,
            RetentionRules rules) {

        if (terminalAt == null) {
            throw new IllegalArgumentException(
                    "Terminal timestamp required");
        }
        return new RetentionDeadlines(
                terminalAt.plus(rules.contentAfterTerminal()),
                terminalAt.plus(rules.metadataAfterTerminal()),
                rules.policyVersion());
    }
}
~~~

Không gọi `afterTerminal()` khi `status=PENDING`, `RETRY_PENDING` hoặc khi vẫn có unknown attempt. Một yêu cầu xóa theo quyền riêng tư cũng có thể có một **deadline khác**; cần giải quyết theo căn cứ và ngoại lệ hợp lệ, không chỉ dùng thời hạn sau terminal.

### Giữ metadata lâu hơn content?

Có thể, nếu mục đích support, đối soát, dispute hoặc audit thực sự cần. Nếu không có mục đích, không tự chọn retention metadata dài chỉ vì dung lượng nhỏ.

### Đừng dùng `createdAt` thay thế `terminalAt`

Một message có thể tạo từ lâu và gửi muộn hoặc retry qua nhiều ngày. Cleanup cần biết khi nào việc xử lý kết thúc, không suy đoán từ ngày enqueue.

## 14. Một phép xóa content có điều kiện trong database

Trước khi purge, worker phải kiểm tra:

1. `content_purge_after <= now`.
2. Job đã ở trạng thái kết thúc được phép.
3. Không có active attempt hoặc lease.
4. Không có `SUBMISSION_UNKNOWN` chưa được đối soát.
5. Không có legal hold áp dụng cho content.
6. Không có dữ liệu/tham chiếu vẫn được các job khác dùng.
7. Worker đang giữ quyền cleanup hợp lệ, có transaction/fencing.

Một truy vấn chọn ứng viên ở PostgreSQL:

~~~sql
SELECT n.id
FROM mail_notification AS n
WHERE n.content_purge_after <= CURRENT_TIMESTAMP
  AND n.status IN (
      'SUBMITTED', 'FAILED_PERMANENT',
      'CANCELLED', 'EXPIRED', 'SUPPRESSED'
  )
  AND n.retention_hold = FALSE
  AND NOT EXISTS (
      SELECT 1
      FROM mail_retention_hold AS h
      WHERE h.notification_id = n.id
        AND h.hold_released_at IS NULL
        AND h.scope IN ('CONTENT', 'ALL')
  )
ORDER BY n.content_purge_after
LIMIT 100
FOR UPDATE OF n SKIP LOCKED;
~~~

`FOR UPDATE SKIP LOCKED` giúp nhiều cleanup workers không chọn cùng row **trong một transaction**, nhưng không tự xử lý object storage và không thay thế việc kiểm tra active references. Danh sách terminal status chỉ là ví dụ; `DEAD_LETTER` và `SUBMISSION_UNKNOWN` cần policy riêng. Để đảm bảo không xóa dữ liệu đang được worker gửi, các transaction state transition/claim cũng phải đồng bộ với chính row/version mà cleanup kiểm tra.

### Transaction boundary quan trọng

Không giữ database transaction mở trong lúc xóa 10 GB attachment qua network. Thay vào đó:

1. Trong transaction ngắn, claim và ghi `PURGE_PENDING` hoặc tạo deletion work item.
2. Commit.
3. Xóa external objects idempotently, có retry.
4. Ghi kết quả, xóa/clear payload reference trong transaction riêng.
5. Chỉ đặt `CONTENT_PURGED` khi tất cả thành phần bắt buộc đã được xử lý hoặc có bằng chứng xác nhận.

Nếu object delete thành công nhưng DB update thất bại, retry delete phải an toàn. Nếu DB đã xóa reference nhưng object chưa xóa, dữ liệu sẽ trở thành **orphan object** khó truy tìm; cần lưu deletion manifest và kiểm soát thứ tự.

## 15. Deletion manifest và giao thức hai pha

Vì database và object store không cùng transaction ACID, có thể dùng **deletion manifest**:

~~~text
mail_deletion_task
  id
  notificationId
  tenantId
  payloadObjectKeys[]
  requestedAt
  policyVersion
  status = READY / IN_PROGRESS / RETRY / COMPLETED / FAILED
  attemptCount
  nextAttemptAt
  lastErrorCategory
  completedAt
~~~

Luồng:

~~~mermaid
flowchart TD
    A["Retention worker evaluates eligibility"] --> B["DB transaction: snapshot refs + claim deletion"]
    B --> C["Deletion task durable"]
    C --> D["Delete external objects idempotently"]
    D --> E{"All objects removed?"}
    E -- "No" --> F["Retry with backoff / alert"]
    F --> D
    E -- "Yes" --> G["DB transaction: clear content rows and refs"]
    G --> H["Mark task completed + evidence"]
~~~

### Tại sao cần lưu object keys trước khi xóa row?

Nếu row `mail_payload` bị xóa trước, cleanup worker không còn biết raw MIME/attachment nằm ở key nào. Một manifest bền vững giúp retry sau restart mà không cần phục hồi row đã xóa.

### Xử lý “object not found”

Trong một deletion workflow idempotent, `NotFound` có thể được xem là **object không còn tại key/version đó**, nhưng phải chắc chắn request đang nhắm đúng object do ứng dụng sở hữu và không bị sai key/tenant. Không xem mọi HTTP error là thành công: `AccessDenied`, network timeout hoặc KMS error cần retry/alert.

### Chỉ xóa object thuộc sở hữu

Không lấy key từ payload người dùng rồi gửi lệnh xóa tùy ý. Kiểm tra tenant, bucket/prefix, version và sở hữu của resource trước khi purge. Với object được nhiều notification dùng chung, phải có reference counting hoặc ownership model đáng tin cậy, tránh xóa một attachment vẫn còn được job khác tham chiếu.

## 16. Spring cleanup worker theo batch

Spring có thể dùng `@Scheduled` để kích hoạt cleanup định kỳ, nhưng bản thân annotation **không quyết định record nào được phép xóa**. Worker cần truy vấn chính sách, claim một batch và thực hiện xóa an toàn.

~~~java
package com.example.mail.retention;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class MailRetentionPoller {

    private final MailDeletionService deletionService;

    public MailRetentionPoller(
            MailDeletionService deletionService) {
        this.deletionService = deletionService;
    }

    @Scheduled(fixedDelayString = "PT1M")
    public void scheduleDuePurges() {
        deletionService.scheduleDueBatch(100);
    }
}
~~~

`MailDeletionService` là ứng dụng tự triển khai. Tùy phiên bản Spring, có thể dùng duration string phù hợp hoặc thuộc tính cấu hình riêng; bật scheduling bằng `@EnableScheduling` ở cấu hình ứng dụng nếu chưa có.

### Ranh giới trách nhiệm

`scheduleDueBatch(100)` nên làm việc ngắn:

1. Kiểm tra retention policy và legal hold.
2. Claim tối đa 100 bản ghi theo DB transaction.
3. Tạo deletion tasks bền vững.
4. Commit và kết thúc poll.

Một hoặc nhiều deletion executors xử lý object store bên ngoài transaction. Không để một vòng xóa external objects kéo dài nhiều giờ trong duy nhất scheduler thread.

### Pseudocode orchestration

~~~java
package com.example.mail.retention;

import java.util.List;

public final class MailDeletionService {

    private final MailRetentionRepository repository;

    public MailDeletionService(MailRetentionRepository repository) {
        this.repository = repository;
    }

    public void scheduleDueBatch(int maxItems) {
        // Method repository thực hiện transaction ngắn:
        // claim rows eligible, recheck hold/lease, ghi manifest.
        List<String> taskIds =
                repository.createDeletionTasks(maxItems);

        // Không gọi object-store network delete ở đây.
        // Executors độc lập sẽ xử lý các task đã persist.
        if (taskIds.isEmpty()) {
            return;
        }
    }
}
~~~

`MailRetentionRepository` là interface ứng dụng, không phải Spring Data repository có sẵn. Code dùng `String` task ID minh họa; production nên có typed IDs và outcome state, metric/error handling.

### Cấu hình giới hạn

Một cleanup worker cũng cần:

- Batch size có giới hạn.
- Số deletion requests/second theo object storage contract.
- Retry budget và backoff với jitter.
- Timeout cho network operations.
- Max concurrent deletions.
- Alert khi backlog purge tăng.
- Idempotent delete và dedup manifest.
- Phân quyền chỉ cho xóa các object liên quan mail retention.

**Không dùng quyền admin toàn bucket** nếu worker chỉ cần xóa một namespace và những object versions được phép.

## 17. Worker gửi và worker xóa phải phối hợp bằng state

Giả sử một email được đặt lịch gửi lúc 09:00, cleanup thấy cột `content_purge_after` của payload đã đến hạn vì phép tính TTL cũ. Nếu bộ cleanup không kiểm tra status/lease, có thể xóa body ngay khi mail worker đang mở stream attachment.

### Bất biến cần có

~~~text
Cannot purge content while:
  notification is dispatchable
  or active submission attempt exists
  or unknown submission outcome requires content
  or a retention hold applies
  or another live job references the same object
~~~

Một cách đồng bộ là dùng **state transition và row version** ở database:

- Send worker claim `PENDING -> PROCESSING` trong transaction.
- Cleanup worker claim `terminal -> PURGE_PENDING` trong transaction.
- Cả hai kiểm tra status/generation.
- Chỉ một transition hợp lệ thắng; transaction nào thua không được tiếp tục bằng snapshot cũ.

### Không chỉ kiểm tra trạng thái một lần rồi xóa

~~~text
T0 cleanup reads status=SUBMITTED
T1 an operator authorized reopens/replays notification
T2 cleanup deletes payload based on T0 snapshot
~~~

Nếu replay là use case hợp lệ, nó phải đi qua state/ownership transaction, ví dụ tạo một notification **mới** hoặc block reopening trong lúc `PURGE_PENDING`. Không để operator sửa status trực tiếp ngoài state machine.

### Không khóa database khi gọi SMTP hoặc object store

Database transaction không thể bảo đảm rollback một email đã submit hoặc phục hồi object đã xóa. Dùng durable jobs/manifest và các bước idempotent; không giữ row lock suốt cả lời gọi mạng.

## 18. Thứ tự xóa content và metadata

Nếu metadata bị xóa trước content, có thể tạo orphan object. Một thứ tự phổ biến:

1. Quyết định xóa và snapshot object references.
2. Đánh dấu payload không còn được cấp cho dispatcher/support (logical retirement).
3. Xóa các external objects có version xác định.
4. Xác nhận external deletion hoặc ghi kết quả/exception.
5. Xóa content columns hoặc row.
6. Giữ minimal metadata cho tới deadline riêng.
7. Sau đó xóa/vô danh hóa metadata và quan hệ phụ thuộc.

### Logical retirement

Trong khi xóa đang diễn ra, một API có thể không nên tiếp tục trả body. Một cờ `payload_state=PURGE_PENDING` giúp chặn access mới; nếu deletion task lỗi, người vận hành có thể retry an toàn mà không “phục hồi” nội dung cho luồng gửi.

### Quan hệ với audit

Hồ sơ audit ghi rằng một deletion task hoàn tất không cần lưu raw nội dung đã xóa. Có thể ghi:

~~~json
{
  "event": "mail_content_purged",
  "notificationKey": "notif-184",
  "policyVersion": "example-v1",
  "reason": "RETENTION_EXPIRED",
  "completedAt": "2027-01-20T00:00:00Z",
  "objectsDeleted": 2
}
~~~

Nhưng audit `notificationKey` vẫn có thể liên kết người dùng, vì vậy **audit log cũng cần retention** và quyền truy cập. Không giữ email body/hash có khả năng nhận diện như một “bằng chứng xóa” không cần thiết.

## 19. Hard delete, soft delete và anonymize

Các phương pháp có mục tiêu khác nhau:

| Phương pháp | Dữ liệu còn tồn tại? | Dùng khi |
| --- | --- | --- |
| Soft delete | Có; chỉ thay trạng thái/ẩn UI | Cần cửa sổ undo, không phải xóa cuối |
| Hard delete | Row/object thực sự bị loại khỏi active storage | Hết mục đích/retention, không có hold |
| Pseudonymize | Có thể tái liên kết với key/nguồn khác | Cần giảm rủi ro trong analytics |
| Anonymize | Không còn khả năng nhận diện hợp lý theo ngữ cảnh | Dùng cho số liệu tổng hợp không cần cá nhân |
| Aggregate | Giữ tổng số/tỷ lệ thay cho records | Dashboard hiệu suất dài hạn |
| Cryptographic erasure | Hủy key làm ciphertext không giải mã được | Một công cụ phụ thuộc kiến trúc/key isolation |

Soft delete **không phải** xóa dữ liệu cuối cùng. Nếu người dùng yêu cầu xóa theo quy trình hợp lệ, chỉ đặt `deleted=true` trong bảng không đủ nếu raw content vẫn đọc được từ admin query hoặc backups.

### Không hard delete khi vẫn có nhiệm vụ giữ hợp lệ

Đối với records có legal hold hoặc nghĩa vụ lưu trữ, có thể phải giới hạn truy cập, không sử dụng ngoài mục đích và hoãn deletion phần có căn cứ giữ lại. Cần ghi rõ **trường nào, hồ sơ nào, căn cứ nào**, không đặt một cờ giữ toàn tenant vô hạn vì tiện triển khai.

### Anonymize phải có thiết kế riêng

Xóa địa chỉ email nhưng giữ `customerId`, `orderId`, template có tên bệnh viện hoặc một idempotency key có cấu trúc định danh vẫn có thể làm dữ liệu tái nhận diện được. Phải xem cả **các khóa liên kết** và dữ liệu phụ trợ.

## 20. Cryptographic erasure: hữu ích nhưng không phải phép màu

Một mô hình dùng key riêng theo tenant hoặc tập dữ liệu để mã hóa payload. Khi key bị hủy theo quy trình, ciphertext còn lại có thể không giải mã được:

~~~text
Per-tenant / per-data-group encryption key
               |
               v
Encrypted mail body and attachment objects
               |
               v
Key lifecycle: active -> rotated -> eligible for destruction
~~~

Nhưng phải chú ý:

- Nếu một key dùng cho cả dữ liệu cần giữ và cần xóa, hủy key sẽ làm mất luôn dữ liệu hợp lệ.
- Nếu plaintext đã xuất hiện trong logs, caches, exports hoặc provider storage, hủy key của database không xử lý các bản đó.
- KMS có backup/recovery/key rotation semantics riêng; phải xác minh “destroyed” thực sự nghĩa gì trong provider.
- Một số bản sao key có thể tồn tại ngoài vòng kiểm soát hoặc còn cached.
- Không tự gọi mọi phương pháp crypto-shred là đáp ứng mọi yêu cầu xóa của luật.

**Cryptographic erasure là một công cụ hỗ trợ retention**, cần phối hợp xóa vật lý, quản lý key scope và audit.

## 21. Attachment object lifecycle và versioning

Attachment thường nằm ở S3-compatible storage, Azure Blob, GCS hoặc một object store nội bộ. Các dịch vụ có **object versioning, replication, lifecycle và delete marker** khác nhau.

### Khi object store bật versioning

Một thao tác `DELETE objectKey` có thể chỉ tạo delete marker hoặc ẩn latest version; các object versions cũ vẫn tồn tại. Nếu mục tiêu là xóa thực sự theo retention, cần hiểu:

- Có bao nhiêu version?
- Có object lock/retention policy nào cản deletion?
- Có replication sang vùng khác không?
- Cần xóa version cụ thể hay cả nhóm versions?
- Lifecycle expiration áp dụng cho current/noncurrent versions ra sao?
- Có inventory để chứng minh object không còn khả dụng không?

Không viết một cleanup method chỉ xóa current key rồi báo “đã loại bỏ mọi bản sao” nếu versioning/replication vẫn giữ nội dung.

### Tham chiếu dùng chung

Một file hóa đơn có thể được nhiều notification tham chiếu:

~~~text
invoice-object-v3
   |--> reminder-email-1
   |--> receipt-email-2
   |--> resend-request-3
~~~

Không xóa object khi notification đầu tiên đã hết TTL nếu hai notification còn cần nó. Có thể:

- Lưu object theo owner là **chứng từ nghiệp vụ** và cho mail chỉ mượn reference.
- Dùng reference tracking với trạng thái live references.
- Tạo immutable delivery copy với lifecycle riêng khi cần.

Đặc biệt, nếu object thực chất thuộc hệ thống tài liệu của doanh nghiệp, mail retention worker không nên có quyền xóa **chứng từ gốc**; chỉ xóa bản sao do mail pipeline sở hữu.

### Object key không nên tiết lộ PII

Tránh key kiểu `attachments/user-email@example.org/invoice.pdf`. Dùng identifier không mang thông tin nhạy cảm, phân quyền theo tenant/resource và lưu tên gốc như metadata có TTL phù hợp.

## 22. Raw MIME và bản lưu troubleshooting

Raw MIME hữu ích khi debug lỗi encoding, header, DKIM hoặc attachment, nhưng là một trong các dạng lưu trữ nhiều dữ liệu nhất.

### Những câu hỏi trước khi lưu raw MIME

1. Có thực sự cần raw MIME cho mọi email không, hay chỉ một nhóm sự cố?
2. Có thể chỉ lưu MIME hash, renderer version và sanitized SMTP response không?
3. Raw MIME có token/secret hoặc tài liệu nhạy cảm không?
4. Người nào được xem, và việc xem có audit không?
5. Có giới hạn kích thước và thời hạn rõ không?
6. Có khả năng xóa bản debug trước TTL khi được yêu cầu không?

Một phương án là chỉ bật **diagnostic capture có thời hạn** cho một incident đã phê duyệt, không mặc định dump toàn bộ email vào filesystem hoặc tracing.

### Nội dung trong exception

`MailException` hoặc Jakarta Mail nested exception có thể chứa recipient address và phản hồi SMTP. Không log toàn bộ object exception vào một nơi ai cũng truy cập, cũng không ghi subject/body trong exception message do ứng dụng tự tạo. Dùng normalized failure category, SMTP code, phase và correlation ID.

### Raw MIME không nhất thiết là bản sao gốc tuyệt đối

Nếu ứng dụng xây dựng MIME bằng `MimeMessageHelper` hoặc serialize `MimeMessage.writeTo(...)`, dữ liệu có thể khác một bản capture thật tại provider sau khi provider thêm headers, DKIM và thay đổi transport. Không tuyên bố giữ “bản gốc đầy đủ” nếu chỉ giữ bản render trước submit.

## 23. Template data và rendered content có vòng đời khác nhau

Một hệ thống có thể không lưu rendered HTML mà chỉ giữ:

~~~json
{
  "templateKey": "invoice-notice",
  "templateVersion": "v3",
  "model": {
    "invoiceId": "inv-184",
    "customerName": "Example User"
  }
}
~~~

Nhưng `model` vẫn chứa dữ liệu cá nhân. Xóa `htmlBody` mà giữ nguyên `templateModel` không giảm đáng kể dữ liệu được lưu. Mặt khác, nếu chỉ lưu tham chiếu `invoiceId`, worker vẫn cần truy cập dữ liệu nghiệp vụ đúng quyền và đúng version tại lúc send.

### Một phân tầng hữu ích

- **Template definition:** mã nguồn template chung; retention theo lifecycle phần mềm, không xóa chỉ vì một message hết hạn.
- **Template version reference:** metadata của message; thường giữ đủ để audit.
- **Template model snapshot:** dữ liệu cụ thể người nhận; content retention.
- **Rendered HTML/plain text:** content retention.
- **Business record gốc:** lifecycle riêng của hệ thống đơn hàng/hóa đơn.

Không để mail cleanup worker xóa cả record nghiệp vụ gốc chỉ vì email chứa một ID tham chiếu tới record đó.

## 24. Dead-letter queue là một kho dữ liệu cần retention

Một job không gửi được có thể bị đẩy vào DLQ để điều tra và replay. Nếu serialized event chứa body hoặc attachment URL, DLQ trở thành một **bản sao nhạy cảm**.

### Rủi ro

- DLQ giữ vĩnh viễn vì không có consumer.
- Payload có OTP/reset link đã hết hạn.
- Nhân viên hỗ trợ có quyền tải toàn bộ message.
- Replay cũ gửi lại email không còn hợp lệ.
- DLQ export sang bucket khác mà không có TTL.

### Chính sách nên có

1. TTL, quota và owner cho từng DLQ/topic.
2. Chỉ lưu payload tối thiểu hoặc reference tới object kiểm soát retention.
3. Khi raw body bị purge, invalidation hoặc xóa DLQ copy liên quan.
4. Replay phải revalidate consent, recipient, token expiry, provider policy.
5. Ghi audit khi operator replay hoặc purge.
6. Không gửi lại mail `SUBMITTED` hoặc `SUBMISSION_UNKNOWN` chỉ vì nó còn ở DLQ.

### Dùng event reference thay vì duplicate body

Thay vì đưa toàn bộ MIME vào queue:

~~~json
{
  "notificationId": "notif-184",
  "attemptId": "attempt-2",
  "eventType": "RETRY_READY"
}
~~~

Worker truy xuất payload có phân quyền từ storage chỉ khi thực sự gửi. Sau khi content bị purge, event cũ phải được bỏ qua hoặc chuyển trạng thái theo policy; không tự phục hồi body từ một queue backup.

## 25. Logs, traces và metrics cũng là dữ liệu có thời hạn

Một log thường phát sinh ngoài bảng mail:

~~~text
2026-11-12 ERROR send failed to alice@example.org
subject="Your verification code is 123456"
SMTP reply: ...
~~~

Ngay cả khi message body đã bị xóa khỏi outbox, một dòng log như trên vẫn lộ địa chỉ và OTP. Vì vậy, thiết kế retention phải gồm **log pipeline, APM, distributed tracing, error monitoring, exports, support bundles và các bản ghi local trên container**.

### Mẫu structured log phù hợp hơn

~~~json
{
  "event": "mail_submission_failed",
  "notificationId": "notif-184",
  "attemptId": "att-2",
  "provider": "smtp-primary",
  "failureKind": "SMTP_AUTH",
  "smtpPhase": "AUTH",
  "smtpCode": "535",
  "retryable": false
}
~~~

`notificationId` vẫn có thể tái liên kết tới recipient bằng hệ thống nội bộ và cần ACL/TTL. Không đưa body, subject, raw recipient, reset URL hay SMTP AUTH transcript vào log.

### Retention ở nhiều hệ thống

| Nơi | Retention cần kiểm soát |
| --- | --- |
| Application stdout/stderr | Container log rotation và log agent |
| Centralized logs | Index lifecycle, hot/warm/archive, deletion |
| Distributed tracing | Trace retention và attribute sanitization |
| Error tracking | Stored exception, breadcrumbs, request payload |
| APM profiling | Heap dumps, stack traces, sampled transactions |
| Metrics | Label data và retention theo monitoring backend |
| Support export | File CSV/ZIP, shared links, expiration |
| Local temp files | MIME cache, debug dumps, crash artifacts |

Với metrics, nên dùng label hữu hạn như `provider`, `category`, `failureKind`, `region`. Tránh recipient, subject, notification UUID hoặc idempotency key làm Prometheus label vì vừa rò dữ liệu vừa gây cardinality cao.

### Log TTL không thay redaction

Một log chứa OTP và được giữ 1 ngày vẫn có thể bị truy cập trái phép trong 1 ngày đó. **Giảm dữ liệu ở điểm ghi** luôn quan trọng hơn chỉ dựa vào TTL.

## 26. Provider-side retention và hợp đồng xử lý dữ liệu

Khi Spring Mail submit qua SMTP relay, message đi ra khỏi hệ thống kiểm soát trực tiếp của ứng dụng. Relay/provider có thể giữ:

- Hàng đợi message trước và trong lúc chuyển phát.
- Body/attachments trong các cơ chế retry nội bộ.
- Delivery events, SMTP logs hoặc bounce records.
- Diagnostic copies hoặc backup.
- Dữ liệu tracking, unsubscribe và complaint theo tính năng.

Do đó, **xóa dữ liệu ở ứng dụng không đồng nghĩa nhà cung cấp đã xóa mọi bản sao**.

### Các câu hỏi cần làm rõ với provider

1. Provider có lưu full message body sau accepted không? Trong trường hợp nào?
2. Thời hạn queue/retry và body retention là gì?
3. Có thể bật/tắt message archiving hoặc event data capture không?
4. Delivery event/webhook có chứa full recipient hoặc payload không?
5. Có API xóa message data, recipient profile hoặc event history không?
6. Khi yêu cầu deletion, provider xử lý backups và replicated data thế nào?
7. Có nghĩa vụ giữ dữ liệu độc lập hoặc ngoại lệ hợp đồng nào không?
8. Region/data residency của việc lưu mail và diagnostic data là gì?
9. Khi đổi nhà cung cấp, dữ liệu cũ được xử lý ra sao?
10. Provider có cung cấp bằng chứng deletion hoặc chính sách retention công khai không?

Không giả định mọi provider có API xóa một email đã được SMTP accepted. SMTP không cung cấp cơ chế phổ quát để thu hồi hoặc xóa một message đã được chuyển tới mailbox người nhận. Yêu cầu deletion có thể phải phân biệt **dữ liệu trong account/provider** với **bản thư ở recipient mailbox ngoài quyền quản lý**.

### Giới hạn việc thu thập provider events

Nếu chỉ cần biết `DELIVERED` hay `BOUNCED`, không nhất thiết lưu toàn bộ webhook request nhiều năm. Có thể:

- Verify và dedup event ngay khi nhận.
- Chuẩn hóa về event type, reason và timestamp.
- Ghi projection trạng thái.
- Xóa raw event theo retention ngắn.

Nếu provider webhook chứa raw SMTP headers hoặc recipient address, xem đó là dữ liệu cần bảo vệ, không phải một “event kỹ thuật vô hại”.

### Không tự mở tính năng archive khi chưa có mục đích

Một provider có thể cung cấp message activity search hoặc full-content archive. Tính năng hữu ích cho điều tra nhưng kéo dài nơi chứa bản sao. Chỉ bật khi có use case, policy, quyền truy cập và quy trình xóa tương ứng.

## 27. Suppression list: giữ tối thiểu nhưng không gửi lại sai

Một người unsubscribe email marketing hoặc báo complaint. Nếu xóa toàn bộ dấu vết ngay, hệ thống có thể quên lựa chọn đó và **tiếp tục gửi thông điệp không mong muốn**.

### Phân biệt nhóm suppression

| Reason | Phạm vi có thể áp dụng | Dữ liệu cần giữ |
| --- | --- | --- |
| Unsubscribe marketing | Một category/list/tenant theo lựa chọn | Định danh tối thiểu và cờ opt-out |
| Complaint | Có thể chặn marketing hoặc rộng hơn theo policy | Reason, nguồn event, thời điểm |
| Hard bounce | Recipient/mailbox không giao được theo bằng chứng | Địa chỉ/identity đã chuẩn hóa và trạng thái |
| Administrative block | Theo policy nội bộ | Owner, lý do, phiên bản quyết định |
| Temporary bounce | Không nhất thiết suppression vĩnh viễn | Trạng thái tạm, expiry và retry logic |

Không áp dụng một boolean `blocked` cho mọi loại email mà không phân biệt scope: unsubscribe newsletter khác với email bảo mật bắt buộc. Nhưng với một mailbox được xác nhận không tồn tại, việc thử lại OTP vào đó cũng không có ích.

### Privacy và suppression có thể cùng tồn tại

Một thiết kế có thể giảm thông tin tới:

~~~text
tenantKey
normalizedRecipientIdentity / controlled pseudonym
categoryScope
suppressionReason
effectiveAt
policyVersion
~~~

Không cần giữ raw email body đã khiến người nhận complaint. Nếu suppression dùng HMAC của email, hãy nhớ:

- HMAC có thể hỗ trợ so khớp để không gửi lại.
- Việc giữ key cho phép liên kết và có thể vẫn được coi là dữ liệu cá nhân tùy hoàn cảnh.
- Cần kiểm soát quyền đọc/calculate, rotation và domain normalization.
- Không dùng hash thô không có key như lời khẳng định vô danh hóa.

Quyết định retention đối với suppression cần được xác định bằng mục đích ngăn gửi, lựa chọn người dùng và yêu cầu áp dụng, không sao chép TTL của outbox body.

## 28. Consent và preference data khác message history

Một hệ thống có thể muốn biết “người này được phép nhận marketing hay không” mà không cần lịch sử tất cả email đã gửi.

Tách các mô hình:

~~~text
mail_preference
  recipientKey
  tenant
  category
  allowed / optedOut
  source / timestamp

mail_notification
  notificationId
  recipientRef
  category
  status
  scheduledAt

mail_payload
  notificationId
  encrypted subject/body
~~~

Nếu một notification hết retention, preference record không nhất thiết bị xóa cùng lúc: nó có mục đích và căn cứ riêng. Ngược lại, không nên giữ toàn bộ danh sách email đã gửi chỉ để chứng minh preference hiện tại.

### Audit consent

Khi cần chứng minh consent/opt-out, giữ sự kiện hoặc bằng chứng tối thiểu theo policy. Tránh sao chép raw HTML marketing hoặc tracking pixels vào mỗi consent event. Nếu dữ liệu được thu thập từ form, cần chú ý version nội dung được chấp nhận và thời điểm, không chỉ lưu một boolean không có ngữ cảnh.

## 29. Yêu cầu xóa dữ liệu: thực hiện có kiểm soát

Một yêu cầu xóa theo quyền riêng tư không nên dẫn tới một lệnh SQL xóa tất cả ngay mà không kiểm tra phạm vi và căn cứ giữ lại.

Các bước thường gặp:

1. Xác thực người yêu cầu và quyền đối với dữ liệu.
2. Xác định data subject/tenant/recipient identities liên quan.
3. Liệt kê nơi dữ liệu tồn tại: outbox, payload, attempts, provider events, logs, object storage, suppression, backups, exports.
4. Xác định nghĩa vụ/căn cứ giữ lại hoặc legal hold đúng phạm vi.
5. Dừng xử lý hoặc giảm quyền truy cập khi cần trong quá trình xử lý.
6. Lên lịch deletion/anonymization tasks idempotent.
7. Điều phối với provider/processor ngoài nếu có quyền và nghĩa vụ yêu cầu.
8. Ghi kết quả từng dataset và ngoại lệ.
9. Xử lý deferred/failed tasks, retry và báo cáo.
10. Giữ bằng chứng hoàn thành **không chứa lại dữ liệu đã xóa**.

### Không tự xóa các thông tin cần thiết để xử lý yêu cầu

Có thể cần một record tối thiểu của deletion request: request ID, action status, dataset completed/exception reason và thời điểm. Tuy nhiên record này cũng phải có quyền/TTL; không dùng một bản copy đầy đủ raw email làm “bằng chứng đã xóa”.

### Xử lý nội dung đang pending

Nếu yêu cầu xóa khiến recipient không còn đủ điều kiện nhận mail, những job `PENDING/RETRY_PENDING` có thể cần **CANCELLED/SUPPRESSED** trước khi purge payload. Nếu một job đang `PROCESSING`, phải xử lý race với worker; không đơn giản xóa body dưới tay worker rồi trả lời đã hoàn tất.

### Không tuyên bố xóa ở recipient mailbox

Ứng dụng có thể xóa bản sao của mình và gửi yêu cầu tương ứng tới provider nếu tính năng/hợp đồng cho phép. Nó thường không thể xóa một email đã đến một mailbox ngoài phạm vi quản lý. Phản hồi cho người yêu cầu phải phân biệt phạm vi xóa thực tế và những hạn chế đó.

## 30. Legal hold và retention exception

Một vụ tranh chấp hoặc nghĩa vụ lưu giữ có thể yêu cầu tạm hoãn deletion của một nhóm dữ liệu.

### Thiết kế hold có phạm vi

~~~text
caseId: dispute-184
scope: EMAIL_METADATA
dataset: mail_attempt
subject: notification group X
start: 2026-11-12
owner: approved compliance role
status: ACTIVE
~~~

Không mặc định một hold cho “mọi email của mọi tenant” khi chỉ cần một record giao dịch.

### Quy trình

1. Chỉ role được ủy quyền mới tạo/gỡ hold.
2. Ghi case ID, mục đích, phạm vi, ngày tạo và approver.
3. Cleanup worker đọc hold **tại thời điểm claim deletion**.
4. Hold áp dụng đúng dataset: có thể giữ metadata mà vẫn được xóa raw body không liên quan.
5. Khi hold được release, tính lại eligibility và thực hiện cleanup.
6. Audit việc tạo/gỡ và truy cập dữ liệu bị giữ.

Một field `retention_hold=true` có thể là cache để tối ưu query, nhưng cần một **nguồn sự thật** có đủ scope và lý do. Nếu hold bị gỡ, không đồng nghĩa phải ngay lập tức xóa mọi record; vẫn xét retention gốc và các hold khác.

### Legal hold không là lý do mở quyền rộng

Dữ liệu đang hold vẫn cần encryption, role-based access, audit và giới hạn sử dụng. Giữ vì một tranh chấp không tự cho phép bộ phận marketing xem hoặc dùng lại nội dung.

## 31. Quy trình xóa dữ liệu và xử lý concurrency

Một yêu cầu xóa, cleanup định kỳ và SMTP worker có thể cùng tác động lên một notification:

~~~text
T0  user requests erasure
T1  application marks recipient/job as no longer eligible
T2  cleanup claims payload deletion
T3  mail dispatcher sees stale PENDING snapshot
T4  dispatcher attempts to read payload
~~~

**Nếu chỉ kiểm tra consent lúc tạo yêu cầu gửi**, worker có thể tiếp tục gửi sau lúc người dùng đã rút quyền. Cần:

- Revalidate permissions/status ngay trước dispatch.
- Atomic status transition khi cancel/purge.
- Fencing/generation để worker cũ không ghi state dựa trên snapshot stale.
- Phân biệt job đã được SMTP accepted (không thể thu hồi chắc chắn) với job chưa gửi.
- Không cho replay/restore làm sống lại một yêu cầu đã purge.

### Một trạng thái hữu ích

`ERASURE_PENDING` có thể chặn việc truy cập payload mới, trong khi cleanup theo dõi các thành phần. Nhưng nếu đang có legal hold, job có thể ở trạng thái `ERASURE_PARTIAL` với các datasets bị hoãn theo lý do hợp lệ. State model này phải được mô tả rõ và không che giấu những nghĩa vụ còn tồn đọng.

## 32. Backups: giữ dữ liệu đã xóa không phải là phục hồi thành công

Database/object backup giúp phục hồi hệ thống sau sự cố, nhưng cũng có thể chứa raw email, attachments và suppression records.

Một chính sách retention cần nói rõ:

- Backup được giữ bao lâu.
- Có immutable snapshots/object versions nào tồn tại.
- Khi nào snapshot tự bị loại theo lifecycle.
- Ai có quyền restore/export.
- Có thể thực hiện deletion ở bản backup hay phải để hết hạn một cách kiểm soát.
- Restore có thể làm dữ liệu đã xóa xuất hiện lại không.
- Có bằng chứng backup expired/securely retired không.

### Restore và “resurrection”

~~~text
Day 1: Notification N is created
Day 5: Body of N is deleted under retention
Day 6: Backup from Day 2 is restored
Risk: N's body reappears in active database
~~~

Vì vậy, sau restore cần **replay deletion journal/tombstones** và các trạng thái suppression/cancel/erasure mới hơn snapshot, trước khi mở worker gửi email hoặc cho support truy cập dữ liệu restored.

### Mẫu restore-safe workflow

1. Restore vào môi trường cách ly có quyền giới hạn.
2. Không cho SMTP dispatch, analytics export hoặc user-facing access ngay.
3. Nạp deletion journal và policy hiện hành.
4. Reapply các deletion/anonymization/cancellation records cần thiết.
5. Đối soát legal holds và quyền truy cập.
6. Xác minh dữ liệu đã purge không bị mở lại.
7. Chỉ sau đó đưa workload vào phục vụ.

Nếu bản deletion journal cũng bị rollback cùng snapshot, workflow không thể phân biệt dữ liệu cần xóa. Vì thế cần **một nguồn lưu các quyết định deletion đủ bền vững/độc lập** trong phạm vi bảo mật được duyệt.

## 33. Deletion tombstone và journal

Một tombstone giúp bảo đảm bản ghi bị xóa không được import, restore hoặc replay trở lại trạng thái hoạt động.

~~~json
{
  "resourceKey": "notif-184",
  "action": "ERASE_CONTENT",
  "policyVersion": "example-v1",
  "decisionAt": "2026-11-12T10:00:00Z",
  "completedAt": "2026-11-12T10:05:00Z"
}
~~~

**Chú ý:** tombstone cũng có thể là dữ liệu cá nhân nếu `resourceKey` liên kết user. Cần TTL, quyền, key management và mục đích rõ; không biến deletion ledger thành kho danh tính lưu vô hạn. Một hệ thống có thể lưu deletion action identifiers không thể truy ngược dễ dàng, hoặc lưu record tối thiểu theo nghĩa vụ audit.

### Các trường hợp cần replay

- Restore database snapshot cũ.
- Khôi phục object version/replication.
- Queue message bị redeliver.
- Import DLQ cũ.
- Rehydrate cache.
- Khôi phục analytics pipeline hoặc data lake.

Không cho `mailSender.send()` chạy trên một record được restore mà chưa xác minh nó không bị hủy/xóa/hết hạn trong các sự kiện mới hơn.

## 34. Caches, temp files và bản sao trong memory

Một số dữ liệu không nằm trong database chính nhưng vẫn cần kiểm soát:

- Redis cache chứa rendered HTML, recipient hoặc template model.
- Local `/tmp` MIME/attachment file.
- Thumbnails/previews.
- In-memory queue hoặc long-running worker.
- HTTP request/response recording.
- Retry serialization trong broker.
- Heap dumps và crash reports.

### Redis TTL

Đặt TTL phù hợp với purpose nhưng không coi Redis eviction là hình thức secure deletion tuyệt đối trong mọi cấu hình persistence/replication. Nếu Redis có RDB/AOF/backups, dữ liệu có thể tồn tại trong snapshot; cần xét toàn bộ lifecycle của cache.

### Local disk

Nếu render attachment vào file tạm, dùng thư mục quyền hạn chế, tên file không tiết lộ PII, cleanup trong `finally` khi phù hợp và một sweeper cho file mồ côi sau crash. Container restart không luôn đảm bảo xóa dữ liệu trên persistent volume.

### Memory và heap dumps

Một chuỗi plaintext token trong heap có thể bị ghi vào dump phục vụ chẩn đoán. Giới hạn quyền tạo/tải heap dump, cấu hình retention và tránh giữ object nhạy cảm lâu trong cache. Xóa database không thể làm sạch heap dump đã xuất trước đó.

## 35. Một mô hình xóa theo dataset thay vì xóa mọi thứ

Khi một notification hết hạn retention, hệ thống không nhất thiết xóa tất cả thành phần cùng ngày. Có thể mô hình hóa từng dataset:

~~~text
MAIL_CONTENT
  subject/body/template model
  raw MIME and preview
  content object references

MAIL_ATTACHMENT
  message-specific immutable objects
  scan result and temporary copies

MAIL_OPERATIONAL
  SMTP attempts / normalized errors
  provider message IDs
  notification state

MAIL_SECURITY
  suppression / opt-out
  abuse complaint indicator

MAIL_AUDIT
  allowed audit events
  legal holds and deletion evidence
~~~

Các dataset có retention/owner riêng, và deletion engine kiểm tra điều kiện của **từng phần**. Trường hợp user yêu cầu xóa content nhưng có nghĩa vụ giữ suppression tối thiểu, system có thể purge body/raw MIME và giữ đúng opt-out marker theo căn cứ áp dụng.

### Không để policy dataset “rò” sang bảng nghiệp vụ

Ví dụ `invoiceId` xuất hiện trong email và hệ thống kế toán. Quyết định purge `MAIL_CONTENT` **không được xóa bản invoice chính thức**. Cần dữ liệu tham chiếu rõ ai là owner và khi nào mail pipeline chỉ mượn immutable object từ hệ thống khác.

## 36. Dùng chính sách theo version và migration có kiểm soát

Giả sử ban đầu metadata retention là một khoảng dài, sau đó policy được rút ngắn. Những record cũ có `metadata_purge_after` đã được tính theo policy cũ.

Các câu hỏi:

- Quy định mới áp dụng hồi tố hay chỉ cho dữ liệu mới?
- Các legal holds đang có có ảnh hưởng không?
- Cần xóa ngay một lượng lớn record cũ hay phân batch để không ảnh hưởng database?
- Có downstream analytics/export dùng dữ liệu chuẩn bị bị xóa không?
- Có báo cáo quyết định và approval trước khi thay đổi không?

### Cách rollout

1. Đặt policy version mới ở configuration được kiểm soát.
2. Dry-run tính số record sẽ thay đổi deadline theo từng dataset.
3. Đánh giá legal hold, active jobs, support và backup implications.
4. Tính lại deadlines bằng migration riêng có idempotency.
5. Chạy cleanup có rate limit và batch sizes.
6. Quan sát backlog, storage cost, failures và deletion audit.
7. Xác minh số record còn tồn/không còn tồn sau rollout.

Không dùng một câu SQL `DELETE` hàng trăm triệu records ngay trong giờ cao điểm vì có thể khóa bảng, tạo replication lag hoặc làm đầy transaction log. Với hệ thống lớn, chọn chunked delete, partition drop phù hợp và chiến lược index/storage vacuum cụ thể.

## 37. Partition và dữ liệu lớn

Với volume email rất cao, `mail_attempt` hoặc `provider_event` có thể chứa hàng triệu record mỗi ngày. Xóa từng row có thể tốn tài nguyên.

### Time partitioning

Ví dụ một bảng event chia partition theo tháng:

~~~text
mail_provider_event_2026_09
mail_provider_event_2026_10
mail_provider_event_2026_11
~~~

Khi một partition đã **hoàn toàn** hết hạn và không chứa legal hold hay record cần giữ, có thể drop/detach partition theo runbook để giảm chi phí cleanup. Nhưng nếu mỗi record có TTL khác nhau hoặc hold kéo dài, một partition có thể **không được xóa toàn bộ**.

### Partition key phải phù hợp retention trigger

Nếu retention dựa trên `processedAt` nhưng partition theo `receivedAt`, một event nhận tháng 9 và xử lý tháng 11 có thể cần giữ quá tháng 10. Không drop partition chỉ vì ngày nhận đã cũ. Thiết kế partition và retention policy phải được đối chiếu từ đầu.

### Thực hiện ngoài giờ cao điểm

Data cleanup không nên gây outage gửi email. Đặt:

- Batch size.
- Lock wait timeout.
- Rate limit cho DELETE/object operations.
- Resource isolation giữa cleanup và SMTP dispatch.
- Giám sát DB replication lag, storage I/O và query latency.

Nếu cleanup gây ảnh hưởng, có thể giảm tốc hoặc pause tác vụ **có kiểm soát**, ghi backlog/vi phạm SLA deletion và khắc phục nguyên nhân. Không “tắt cleanup vĩnh viễn” mà không xử lý nghĩa vụ retention.

## 38. Access control sau khi đã giữ dữ liệu

Retention là câu hỏi **giữ bao lâu**, nhưng cần song hành với **ai có quyền đọc trong thời gian giữ**.

| Vai trò | Quyền cần cân nhắc |
| --- | --- |
| Mail dispatcher | Đọc payload của job đang được phép gửi |
| Template renderer | Đọc model đủ để render, không cần toàn bộ lịch sử |
| Support agent | Xem status/reason đã làm sạch; body chỉ khi có quyền/mục đích |
| Security responder | Xem dữ liệu diagnostic theo case/audit |
| Analytics pipeline | Đọc số liệu tổng hợp hoặc dữ liệu giảm định danh |
| Retention worker | Xóa object/row đã được phê duyệt, không cần SMTP credentials |
| Provider webhook consumer | Ghi event/status, không cần quyền đọc raw content |
| Admin | Quyền đặc biệt có audit và time-bound access |

### Một chính sách thực tiễn

- Encryption at rest và TLS in transit.
- Row/tenant authorization tại API và database layer khi phù hợp.
- Secrets tách giữa sender, cleanup và provider event worker.
- Không lưu plaintext body trong log hoặc tracing.
- Truy cập raw MIME cần role và audit.
- Quarantine content có quyền nghiêm ngặt hơn thông thường.
- Object storage access dùng short-lived scoped credentials khi có thể.

**Mã hóa và ACL không thay việc xóa đúng hạn**. Chúng giảm rủi ro trong giai đoạn dữ liệu vẫn cần được giữ.

## 39. Chứng minh deletion đã hoàn tất

Không đủ khi cleanup method trả “success” trong log. Cần biết:

- Database row/column đã thực sự được xóa hoặc anonymize.
- External object versions đã được xử lý theo chính sách.
- Queue/DLQ/caches có bản sao nào còn không.
- Provider deletion request có được accepted/confirmed không, nếu áp dụng.
- Backup snapshots đã hoặc sẽ hết hạn theo vòng đời nào.
- Legal hold có làm deferred một phần nào không.
- Deletion audit record đã được lưu nhưng không tái tạo thông tin nhạy cảm.

### Một mô hình kết quả

~~~java
public enum DeletionOutcome {
    COMPLETED,
    PARTIALLY_COMPLETED,
    DEFERRED_BY_HOLD,
    RETRY_PENDING,
    FAILED_REQUIRES_REVIEW
}

public record DeletionProgress(
        String deletionTaskId,
        DeletionOutcome outcome,
        int objectCount,
        int completedObjectCount,
        String lastFailureCategory) {
}
~~~

Một lần gọi xóa DB thành công nhưng object store trả access denied phải là **PARTIALLY_COMPLETED** hoặc **RETRY_PENDING**, không được báo hoàn tất. Điều tương tự khi provider không xác nhận deletion trong phạm vi hợp đồng được yêu cầu.

### Bằng chứng tối thiểu

Không tạo một report xóa chứa lại toàn bộ recipient, subject, body và attachment. Thường chỉ cần task ID, dataset, loại thao tác, timestamp, policy version, số lượng object và trạng thái; những trường có khả năng liên kết cá nhân vẫn phải có TTL/ACL.

## 40. Giám sát retention và deletion

Retention là công việc nền cần SLO/alert rõ, không nên chạy âm thầm suốt nhiều tháng.

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `mail_retention_candidates_total` | Số bản ghi đủ điều kiện theo policy |
| `mail_retention_due_objects` | Số đối tượng đã quá deadline nhưng chưa xóa |
| `mail_retention_oldest_overdue_seconds` | Thời gian quá hạn lâu nhất |
| `mail_content_purged_total` | Số payload content purge thành công |
| `mail_metadata_purged_total` | Số metadata rows được xóa/anonymize |
| `mail_deletion_tasks_total` | Task tạo/hoàn thành/lỗi theo trạng thái |
| `mail_deletion_retry_total` | Xóa retry vì network/permission |
| `mail_deletion_failures_total` | Lỗi theo storage/dataset/category |
| `mail_retention_hold_active` | Số hold đang hiệu lực |
| `mail_retention_hold_deferred_total` | Số task không được xóa vì hold |
| `mail_retention_bytes_deleted_total` | Dung lượng đã loại khỏi storage theo nguồn được kiểm chứng |
| `mail_orphan_objects_detected` | Object không còn reference hợp lệ |
| `mail_deletion_manifest_pending` | Deletion manifests chưa hoàn tất |
| `mail_restore_redeletion_pending` | Record cần áp lại deletion sau restore |
| `mail_retention_policy_version` | Phiên bản policy đang áp dụng nếu hệ thống biểu diễn được bằng nhãn hữu hạn |

Các tên metric trên là **ví dụ cần tự triển khai** bằng Micrometer/Actuator hoặc monitoring platform; Spring Mail không tự xuất chúng.

### Tránh cardinality và PII

Chọn label `dataset`, `storageType`, `policyVersion`, `outcome`, `failureCategory`. Không dùng raw recipient email, notification UUID, object key hoặc case ID làm Prometheus labels.

### Cảnh báo đáng hành động

| Alert | Hậu quả có thể có | Hướng xử lý |
| --- | --- | --- |
| Content quá hạn tăng liên tục | Cleanup worker ngừng hoặc query sai | Xem scheduler, DB locks và eligibility |
| Object deletions thất bại | AccessDenied, KMS, versioning, network | Kiểm tra permission và deletion manifest |
| Metadata đã xóa nhưng object vẫn còn | Orphan/leak | Reconcile object storage và manifest |
| Retention hold tăng không giảm | Hold không được review/release | Audit owner/case |
| Provider event raw tồn tại quá TTL | Event cleanup không chạy | Kiểm tra event inbox và projection |
| Xóa payload của PENDING job | Bug nghiêm trọng | Cô lập cleanup, bảo vệ dispatch |
| Sau restore xuất hiện lại dữ liệu đã xóa | Missing tombstone replay | Cô lập restored workload, reapply deletions |
| Quarantine tăng quá dung lượng | Scan/retention lỗi hoặc spam wave | Bảo vệ storage, xem scanner |

Đừng chỉ đo “đã xóa bao nhiêu”. Cần biết **còn bao nhiêu đã quá hạn**, vì một cleanup job chạy thành công 100 objects mỗi ngày vẫn có thể thua xa 10.000 objects đến hạn mỗi ngày.

## 41. Runbook: cleanup chậm hoặc ngừng chạy

Nếu `mail_retention_oldest_overdue_seconds` tăng:

1. Xem scheduler có chạy và log category đã chuẩn hóa.
2. Kiểm tra batch query, index và DB locks.
3. Xem deletion manifest đang READY, RETRY hay FAILED.
4. Phân biệt record do legal hold với record thực sự overdue.
5. Kiểm tra object store API quota, permission, versioning và replication.
6. Kiểm tra backup/lifecycle hoặc data export ngoài hệ thống chính.
7. Đo tốc độ đến hạn so với throughput purge.
8. Tăng concurrency/batch có kiểm soát, không làm ảnh hưởng mail dispatcher.
9. Xác minh state/lease và tenant scope trước khi replay một cleanup task.
10. Ghi incident, phạm vi dữ liệu bị giữ quá hạn và thời điểm khắc phục.

### Không sửa bằng xóa hàng loạt thiếu điều kiện

Một query `DELETE WHERE created_at < ...` bỏ qua state và hold có thể xóa email chưa gửi, dữ liệu đang đối soát hoặc tài liệu cần giữ. Khi cleanup backlog lớn, ưu tiên **đúng dữ liệu** trước **số lượng xóa nhanh**.

## 42. Runbook: phát hiện nội dung đã xóa nhưng tồn tại ở object storage

Một database row có thể đã xóa nhưng attachment vẫn còn:

1. Xác định object key/version qua deletion manifest hoặc storage inventory.
2. Xem notification/payload đã bị đánh dấu `CONTENT_PURGED` chưa.
3. Kiểm tra object có live references từ email/tài liệu khác không.
4. Xác nhận tenant/bucket ownership và legal hold.
5. Kiểm tra object versioning/replication/lifecycle.
6. Retry deletion có giới hạn và idempotent.
7. Ghi kết quả thực cho từng object/version.
8. Nếu không thể xóa, escalate với owner/nhà cung cấp.
9. Cập nhật metrics orphan/outstanding deletion.
10. Sửa transaction ordering để không mất object references trước khi tạo manifest.

Không tự chạy lệnh xóa mọi object cùng prefix nếu chưa biết prefix đó còn chứa dữ liệu của job khác.

## 43. Runbook: người dùng yêu cầu xóa nhưng có legal hold

Một yêu cầu xóa có thể chỉ hoàn thành một phần vì một số record cần giữ theo căn cứ xác định:

1. Xác thực requester và phạm vi dữ liệu.
2. Liệt kê datasets và các holds đang áp dụng.
3. Kiểm tra hold có căn cứ, chủ sở hữu và scope đúng.
4. Xóa/anonymize những phần không nằm trong hold.
5. Hạn chế quyền truy cập dữ liệu bị hold, không dùng cho mục đích khác.
6. Ghi kết quả theo dataset: completed, deferred, ineligible và lý do.
7. Thông báo trạng thái theo quy trình và yêu cầu áp dụng, không nói “đã xóa tất cả” nếu chưa đúng.
8. Khi hold được release, tự động hoặc theo workflow chạy lại eligibility.
9. Lưu audit tối thiểu, không giữ toàn bộ nội dung làm bằng chứng.

**Không dùng legal hold như cờ bỏ qua mọi retention vô thời hạn** nếu thực tế chỉ cần một số metadata cho một vụ việc.

## 44. Runbook: khôi phục database từ backup cũ

Sau restore:

1. Cô lập network/SMTP sender và không mở ứng dụng cho user ngay.
2. Xác nhận timestamp của snapshot.
3. Lấy deletion journal/tombstones và state transition mới hơn snapshot.
4. Áp lại các cancel/expiry/suppression/erasure quyết định cần thiết.
5. Đánh giá attachment objects và cache restored.
6. Không tự replay toàn bộ `PENDING` nếu có thể đã SUBMITTED sau snapshot.
7. Đối soát provider message IDs/outcomes nếu có.
8. Kiểm tra các legal holds hiện hành.
9. Chạy validation các records/datasets đã purge không xuất hiện trở lại.
10. Chỉ khi hoàn tất mới cho worker và UI hoạt động theo runbook.

Việc restore đúng bytes của backup không đồng nghĩa **restored data hợp lệ để được dùng lại**. Đặc biệt không được gửi lại email mà người dùng đã hủy, token đã hết hạn hoặc email đã được provider accepted.

## 45. Unit test: retention deadline phải tính đúng mốc

Một trong các lỗi đơn giản nhưng nguy hiểm nhất là tính deadline theo `createdAt` thay vì `terminalAt`. Có thể kiểm thử `MailRetentionCalculator` bằng JUnit 5:

~~~java
package com.example.mail.retention;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class MailRetentionCalculatorTest {

    private final MailRetentionCalculator calculator =
            new MailRetentionCalculator();

    private final RetentionRules exampleRules =
            new RetentionRules(
                    "example-v1",
                    Duration.ofDays(7),
                    Duration.ofDays(90),
                    Duration.ofDays(3),
                    Duration.ofDays(14),
                    Duration.ofDays(7));

    @Test
    void computesDeadlinesFromTerminalTime() {
        Instant terminal =
                Instant.parse("2026-11-20T02:00:00Z");

        RetentionDeadlines result =
                calculator.afterTerminal(terminal, exampleRules);

        assertEquals(terminal.plus(Duration.ofDays(7)),
                result.contentPurgeAfter());
        assertEquals(terminal.plus(Duration.ofDays(90)),
                result.metadataPurgeAfter());
        assertEquals("example-v1", result.policyVersion());
    }

    @Test
    void cannotScheduleCleanupWithoutTerminalTime() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.afterTerminal(null, exampleRules));
    }
}
~~~

Đây là **unit test logic thời gian** theo ví dụ; nó chưa chứng minh một cleanup worker thực sự tránh xóa `PENDING` hoặc tôn trọng legal hold. Các ràng buộc đó phải được kiểm thử ở repository/state transition.

### Unit test theo loại dữ liệu

Với nhiều loại mail:

~~~text
OTP body:
  terminalAt + approved OTP-content period

Transactional metadata:
  terminalAt + approved support/ops period

Provider raw webhook:
  processedAt + approved event period

Pending future schedule:
  no content purge deadline until valid terminal transition
~~~

Các khoảng giữ cần lấy từ retention policy do tổ chức phê duyệt, không hardcode thành một mặc định cho mọi tenant/category trong test.

## 46. Integration test: không xóa email còn cần gửi

Test sử dụng database có transaction/locking đủ gần production:

~~~text
Given:
  mail notification status = PENDING
  scheduledAt = next month
  createdAt = long ago
  mail payload exists

When:
  retention cleanup runs

Then:
  notification remains PENDING
  payload remains available to dispatcher
  no deletion task is created
~~~

Biến thể:

- `PROCESSING` với active lease.
- `RETRY_PENDING` với `nextAttemptAt` ở tương lai.
- `SUBMISSION_UNKNOWN` với reconciliation case mở.
- `SUBMITTED` nhưng content purge deadline chưa đến.
- `CANCELLED` và content deadline đã đến.
- `EXPIRED` với token cần loại sớm.

Không chỉ assert `payload_state` trong DB. Nếu external object đã bị xóa nhầm nhưng row vẫn còn, test chỉ dựa trên DB sẽ bỏ sót lỗi nghiêm trọng.

## 47. Integration test: database và object store không cùng transaction

Một test failure injection cho deletion manifest:

### Tình huống A — object delete thất bại

~~~text
1. DB transaction creates deletion task.
2. Object store returns transient 503.
3. Task becomes RETRY_PENDING.
4. mail_payload is not marked CONTENT_PURGED.
5. Retry occurs with backoff.
6. Object delete later succeeds.
7. Payload metadata is cleared.
8. Task becomes COMPLETED.
~~~

Kiểm tra task không bị mất qua worker restart và không tạo nhiều manifest cho cùng decision.

### Tình huống B — object delete xong, DB update thất bại

~~~text
1. Deletion task references object version V.
2. Object V is deleted successfully.
3. DB connection drops before completion update.
4. Worker restarts.
5. It retries delete V idempotently.
6. It verifies object V is absent.
7. DB status becomes CONTENT_PURGED / COMPLETED.
~~~

Không báo FAILED_PERMANENT chỉ vì một lần delete trả NotFound sau khi lần trước đã xóa xong, nhưng phải xác minh object key/version đúng và provider semantics phù hợp.

### Tình huống C — database xóa trước manifest

Đây là lỗi cần **test để ngăn**:

~~~text
1. mail_payload row deleted.
2. Process crashes before deletion task/object key persisted.
3. External object remains without reference.
~~~

Thiết kế đúng phải tạo durable manifest **trước khi đánh mất references**, hoặc có inventory/reconciliation đủ mạnh để tìm orphan objects.

## 48. Integration test: legal hold, concurrency và restore

### Legal hold

- Record đủ TTL nhưng có hold `CONTENT`: không xóa body.
- Record chỉ hold `METADATA`: xử lý content theo policy và scope cụ thể.
- Nhiều holds: gỡ một hold không xóa khi hold khác vẫn active.
- Hold được tạo đồng thời cleanup claim: state transition/lock bảo đảm không xóa trái quyết định hợp lệ.
- Hold được release: record trở lại eligible nếu đã quá deadline.

### Worker concurrency

- Hai cleanup instances cùng chạy: chỉ một task claim mỗi resource.
- Cleanup cùng lúc SMTP worker chuẩn bị send: không thể xóa payload của job active.
- Operator tạo replay/hủy trong lúc cleanup: không để status và payload trái nhau.
- Worker cũ hết lease không được ghi `CONTENT_PURGED` nếu generation thay.

### Restore

1. Tạo dữ liệu N, snapshot.
2. Chạy retention xóa N và ghi tombstone.
3. Restore snapshot cũ trong môi trường cô lập.
4. Chạy deletion replay/reconciliation.
5. Xác minh content của N không thể sử dụng trở lại.
6. Xác minh SMTP dispatcher không được tự gửi N.

Đây là bài kiểm tra **restore workflow**, không chỉ backup job success.

## 49. Ma trận kiểm thử retention

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| R01 | `PENDING` tạo lâu nhưng lịch ở tương lai | Không purge payload |
| R02 | `RETRY_PENDING` chưa hết window | Không purge payload |
| R03 | `PROCESSING` còn lease | Không purge |
| R04 | `SUBMISSION_UNKNOWN` chưa đối soát | Giữ evidence theo window |
| R05 | `SUBMITTED` đủ content TTL | Purge body/subject/template model đã quy định |
| R06 | Metadata TTL dài hơn body TTL | Giữ đúng metadata tối thiểu |
| R07 | `CANCELLED` trước SMTP | Có thể purge sớm theo policy |
| R08 | `EXPIRED` chứa OTP | Không gửi lại; content bị loại đúng hạn |
| R09 | `DEAD_LETTER` còn payload | Có TTL; không giữ vô hạn |
| R10 | Legal hold CONTENT | Không xóa body đang hold |
| R11 | Legal hold METADATA | Không xóa metadata; content xử lý theo scope |
| R12 | Hai holds cùng resource | Gỡ một hold không bỏ hold còn lại |
| R13 | Policy version thay đổi | Deadlines được migrate theo quyết định |
| R14 | Retry xóa object gặp 503 | Manifest được giữ và retry có backoff |
| R15 | Object đã xóa rồi DB update lỗi | Retry idempotent tới COMPLETED |
| R16 | Object không tồn tại tại đúng version | Không retry vô hạn nếu đủ bằng chứng đã xóa |
| R17 | Object delete AccessDenied | Không đánh dấu COMPLETED |
| R18 | Object store có nhiều versions | Xử lý theo versioning/retention rules |
| R19 | Object có replication | Báo đúng phạm vi đã xóa/chưa xóa |
| R20 | Attachment dùng chung còn live refs | Không xóa object của job khác |
| R21 | Attachment chỉ là reference tới chứng từ gốc | Không xóa chứng từ thuộc hệ thống khác |
| R22 | Raw MIME trong debug store | Có TTL/ACL và cleanup độc lập |
| R23 | Provider webhook raw hết TTL | Chỉ giữ projection cần thiết |
| R24 | DLQ lưu serialized body | Retention xóa/invalidate bản copy |
| R25 | Log chứa token do bug | Redaction và incident xử lý bản đã ghi |
| R26 | Metrics label chứa recipient | Không chấp nhận thiết kế label |
| R27 | Redis cache chứa rendered body | Invalidate/TTL và xét persistence snapshot |
| R28 | Local temp file sau crash | Sweeper và permission xử lý |
| R29 | Data subject erasure request | Tasks được phát tới đúng datasets |
| R30 | Provider không hỗ trợ deletion API | Báo giới hạn, không tuyên bố đã xóa ở provider |
| R31 | Mail đã tới recipient mailbox | Không tuyên bố có thể thu hồi bên nhận |
| R32 | Suppression record giữ tối thiểu | Không lỡ gửi lại marketing đã opt out |
| R33 | Metadata có HMAC email | Vẫn có policy, key access và TTL |
| R34 | Backup restore trước deletion | Tombstone replay bảo vệ dữ liệu |
| R35 | Two cleanup workers cùng claim | Không tạo double-deletion state race |
| R36 | Purge job và send worker cạnh tranh | State transition ngăn dùng payload đã xóa |
| R37 | Quarantine có file nhiễm | Không được release qua đường cleanup |
| R38 | Case hold release | Cleanup thực hiện lại khi đủ điều kiện |
| R39 | Batch rất lớn | Không tạo DB outage hoặc phá SMTP SLO |
| R40 | Audit deletion record | Có bằng chứng tối thiểu và TTL của chính audit |

Bộ test cần phân biệt **unit test policy**, **integration test database/object store** và **test quy trình backup/restore/provider**. Mock object store trả success không chứng minh một provider thật đã xóa noncurrent versions hoặc replicated data.

## 50. Những sai lầm thường gặp

### 50.1. Chỉ xóa mail body mà giữ raw MIME

Raw MIME thường chứa toàn bộ body và attachments. Xóa cột HTML nhưng giữ MIME source trong bucket debug không đạt mục tiêu giảm dữ liệu.

### 50.2. Coi metadata là dữ liệu không nhạy cảm

Full recipient email, subject, time, bounce reason có thể liên kết tới cá nhân. Cần giảm dữ liệu và TTL riêng.

### 50.3. Tính TTL từ `createdAt` cho job ở tương lai

Email scheduled xa có thể bị xóa trước khi gửi. Cần deadline theo state/retention trigger, không chỉ ngày tạo.

### 50.4. Xóa `PROCESSING` hoặc `RETRY_PENDING`

Worker còn cần payload. Cleanup cần state/lease check và đồng bộ với dispatcher.

### 50.5. Xóa `SUBMISSION_UNKNOWN` quá sớm

Mất dữ liệu để đối soát một attempt có thể đã accepted. Cần reconciliation window và reason.

### 50.6. Giữ mọi dead letter vô hạn

DLQ là kho bản sao thông điệp. Cần retention, quota và workflow purge/review.

### 50.7. Đưa OTP vào error log

Log TTL ngắn vẫn có nguy cơ lộ. Giảm dữ liệu ở điểm ghi; xử lý lịch sử log bị lộ theo incident workflow.

### 50.8. Xóa database rồi quên object storage

Raw MIME/attachment tiếp tục tồn tại mà không còn reference. Dùng durable deletion manifest và object inventory.

### 50.9. Gọi xóa object một lần rồi đánh dấu hoàn tất

Network, permission, versioning hoặc replication có thể khiến object còn tồn tại. Cần xác nhận và trạng thái partial/retry.

### 50.10. Xóa attachment dùng chung của job khác

Cần sở hữu resource rõ hoặc reference tracking. Mail cleanup không được xóa chứng từ gốc của hệ thống kế toán.

### 50.11. Dùng soft delete thay cho xóa cuối

Một cờ `deleted` chỉ ẩn khỏi UI; raw body vẫn trong database và backup.

### 50.12. Coi HMAC email là hoàn toàn vô danh

Nếu vẫn liên kết được nhờ key/nguồn khác, dữ liệu chưa nhất thiết anonymous.

### 50.13. Xóa suppression để “xóa mọi dữ liệu”

Có thể khiến hệ thống gửi marketing lại cho người đã opt out. Cần policy giải quyết cân bằng giữa quyền riêng tư và nghĩa vụ không gửi.

### 50.14. Dùng một legal hold boolean không có scope

Giữ mọi dữ liệu vô thời hạn, khó audit. Cần record hold có owner, case, phạm vi và quy trình release.

### 50.15. Không đưa log/APM vào data inventory

Raw SMTP transcript, recipient và body có thể tồn tại ngoài database rất lâu.

### 50.16. Nhầm provider data deletion với SMTP recall

Xóa metadata trong provider không có nghĩa có thể lấy lại email đã giao vào mailbox người nhận.

### 50.17. Bỏ qua versioning khi xóa object

Delete marker có thể chỉ ẩn latest object trong khi noncurrent versions còn tồn tại.

### 50.18. Restore backup làm dữ liệu đã xóa sống lại

Phải có deletion journal/tombstone và restore-safe reconciliation trước khi mở lại worker/UI.

### 50.19. Mở quyền đọc raw mail cho mọi support agent

Dữ liệu giữ lâu càng tăng nguy cơ lộ. Chỉ cấp quyền theo use case, thời gian và audit.

### 50.20. Chạy `DELETE` hàng loạt không batch trên bảng lớn

Có thể làm chậm database, replication lag hoặc ảnh hưởng SMTP dispatch. Dùng batch/partition có điều kiện.

### 50.21. Không kiểm tra backup và replication retention

Active database đã xóa nhưng snapshot/replica/export còn nội dung. Phải mô tả rõ phạm vi và nghĩa vụ trong từng môi trường.

### 50.22. Dùng một TTL chung cho body, events và audit

Mỗi dataset có mục đích và trạng thái khác nhau. Một TTL chung có thể quá dài cho OTP nhưng quá ngắn cho metadata cần đối soát.

### 50.23. Coi “cleanup task thành công” là “mọi bản sao đã xóa”

Task có thể chỉ xử lý một dataset. Ghi outcome theo component và chứng minh phạm vi thực tế.

### 50.24. Không có người sở hữu retention

Khi cleanup lỗi, không ai biết ai được phép điều chỉnh policy hoặc giải quyết hold. Cần owner và runbook rõ.

## 51. Checklist production cho data retention

### Data inventory và policy

- [ ] Có danh sách mọi nơi lưu body, subject, MIME, attachment, metadata và provider events.
- [ ] Mỗi dataset có purpose, owner, classification, retention trigger và period.
- [ ] Các mốc TTL được phê duyệt theo nghĩa vụ áp dụng, không chọn số tùy tiện.
- [ ] Có `policyVersion` và quy trình thay đổi policy.
- [ ] Có phân biệt content retention với metadata retention.
- [ ] Có quy tắc riêng cho OTP, transactional, marketing, support và attachments.
- [ ] Có cơ chế xử lý legal hold/ngoại lệ có phạm vi.
- [ ] Có mô tả provider-side retention và giới hạn deletion.

### Database và object storage

- [ ] Không purge khi PENDING/PROCESSING/RETRY_PENDING còn cần payload.
- [ ] Có reconciliation window cho SUBMISSION_UNKNOWN.
- [ ] Có `terminalAt` và deadline xóa đúng trigger.
- [ ] Có index/query chọn dữ liệu đến hạn không ảnh hưởng dispatcher.
- [ ] Có deletion manifest bền vững trước khi mất object references.
- [ ] External delete idempotent, có retry/backoff và trạng thái partial.
- [ ] Có xử lý object versions, replication và object lock khi áp dụng.
- [ ] Không xóa attachment còn được job hoặc hệ thống khác tham chiếu.
- [ ] Có cơ chế kiểm soát race giữa gửi, hủy, legal hold và cleanup.
- [ ] Có cleanup cho dead-letter queue và quarantine.

### Bảo mật, quyền riêng tư và dữ liệu phụ trợ

- [ ] Body/template model chứa token được giảm tối đa và mã hóa phù hợp.
- [ ] Logs/traces/metrics không chứa raw content hoặc secret.
- [ ] Support access tới raw MIME bị giới hạn và audit.
- [ ] Data subject deletion workflow có thể truy vết các datasets và ngoại lệ.
- [ ] Suppression giữ thông tin tối thiểu theo scope và policy.
- [ ] Backup/lifecycle/restore không làm sống lại dữ liệu đã bị xóa.
- [ ] Caches, temp files và heap dumps có TTL/retention.
- [ ] Audit/deletion journal cũng có quyền truy cập và retention riêng.

### Vận hành và kiểm thử

- [ ] Cleanup chạy theo batch có timeout, concurrency và quota.
- [ ] Có metric `oldestOverdue`, remaining candidates và failed deletions.
- [ ] Có alert khi overdue backlog tăng hoặc object deletion lỗi.
- [ ] Có test không xóa pending/future/unknown/held records.
- [ ] Có test external delete fail rồi retry/finish.
- [ ] Có test object sharing/versioning theo provider đang dùng.
- [ ] Có test race cleanup vs dispatch và legal hold creation.
- [ ] Có test backup restore + tombstone replay.
- [ ] Có runbook xử lý overdue, orphan objects, hold và erasure requests.

Checklist là hướng thiết kế và vận hành. Nó **không thay kiểm thử thực tế, privacy review hoặc đánh giá nghĩa vụ pháp lý áp dụng**.

## 52. Ví dụ lifecycle: email xác nhận thanh toán

Giả sử hệ thống gửi biên nhận sau khi thanh toán:

~~~text
2026-11-12 10:00  Payment transaction commits
                  Outbox notification created
                  Payload references receipt snapshot v3

2026-11-12 10:00  Mail worker submits via SMTP
                  Relay accepted, status=SUBMITTED

2026-11-12 10:05  Provider event says DELIVERED
                  Projection updated

Later              Content retention window expires
                  Renderer data / mail-specific MIME
                  and temporary attachments are purged

Later still        Metadata retention expires
                  Attempt and recipient links are
                  deleted/anonymized as policy requires
~~~

### Điều cần giữ tách biệt

- **Biên nhận gốc:** có thể thuộc hệ thống kế toán với vòng đời riêng.
- **Mail-specific copy:** đối tượng do mail worker tạo để gửi, retention riêng.
- **SMTP attempt:** provider key, code và timestamp, support retention.
- **Consent/suppression:** preference data có lifecycle riêng.
- **Backup/journal:** cần quy trình không hồi sinh mail payload sau purge.

Không để mail retention vô tình xóa hóa đơn chính thức vì cùng dùng một `storageKey`.

## 53. Ví dụ lifecycle: OTP đã hết hạn

~~~text
10:00  OTP created, valid until 10:05
10:00  Mail outbox queued
10:01  SMTP provider unavailable
10:03  Retry pending
10:06  Worker resumes
       OTP expired -> do not submit
       status=EXPIRED
       plaintext token/body content purge eligible
       limited operational metadata may remain
~~~

Điểm quan trọng:

1. Retry không được vượt token expiry.
2. Xóa hoặc bảo vệ plaintext token sau khi không còn cần gửi.
3. Không lưu token vào exception/log để debug outage.
4. Không tự tạo OTP mới từ cleanup worker; nghiệp vụ xác thực quyết định mã mới.
5. Một record `EXPIRED` có thể giữ reason ngắn hạn để hỗ trợ, không cần giữ mã.

## 54. Ví dụ lifecycle: khi người dùng unsubscribe marketing

~~~text
Day 1: Marketing email submitted
Day 2: Recipient opts out
Day 2: Preference/suppression updated
Day 3: Old marketing body reaches purge deadline
Day 3: Body removed; minimal opt-out remains
Day 4: New campaign attempts to enqueue
Day 4: Consent/suppression gate prevents submission
~~~

Nếu xóa toàn bộ suppression vào Day 3 cùng email body, Day 4 hệ thống có thể gửi lại thông điệp không mong muốn. Đây là ví dụ vì sao **retention của nội dung gửi** và **retention của lựa chọn ngừng nhận** phải tách nhau, trong phạm vi mục đích và quy định áp dụng.

## 55. Câu hỏi tự kiểm tra

**1. Khi `JavaMailSender.send()` hoàn thành, có nên xóa ngay mọi dữ liệu email không?**

Không có quy tắc chung. Có thể purge body sớm nếu không còn cần resend/reconciliation và không có hold; metadata/attempt history có thể cần giữ một thời gian khác.

**2. Metadata email có thể là dữ liệu cá nhân không?**

Có. Recipient address, subject, thời gian và mối quan hệ liên lạc có thể nhận diện hoặc liên kết tới một người.

**3. Vì sao không dùng `createdAt + 7 days` cho mọi payload?**

Email có thể được đặt lịch sau nhiều tháng hoặc đang retry/đối soát. TTL phải dựa vào state và retention trigger thích hợp.

**4. Vì sao nên tách `mail_payload` và `mail_notification`?**

Để xóa nội dung sớm nhưng vẫn giữ trạng thái vận hành tối thiểu, đồng thời phân quyền đọc body tách khỏi metadata.

**5. Một email `SUBMISSION_UNKNOWN` có nên bị xóa ngay khi worker nhận exception không?**

Không. Cần giữ correlation/evidence theo cửa sổ đối soát có giới hạn, vì SMTP relay có thể đã accepted.

**6. Vì sao không giữ DLQ vô hạn?**

DLQ có thể chứa payload, OTP hoặc attachment như outbox; cần TTL, quota, quyền truy cập và quy trình purge.

**7. Nếu body được xóa khỏi DB nhưng raw MIME còn trong object store thì sao?**

Mục tiêu content deletion chưa hoàn thành. Cần deletion manifest và xử lý đúng object/version.

**8. Vì sao object store delete có thể chưa xóa mọi dữ liệu?**

Versioning, replication, delete markers, object lock hoặc backup có thể vẫn giữ các bản sao.

**9. Xóa mềm có được coi là xóa cuối cùng không?**

Không. Soft delete chỉ ẩn hoặc đánh dấu record; plaintext vẫn có thể tồn tại.

**10. Có cần ghi audit khi xóa dữ liệu không?**

Có thể cần bằng chứng hoàn thành, nhưng chỉ giữ thông tin tối thiểu và áp dụng retention cho audit.

**11. Legal hold nên giữ mọi email của tenant vô thời hạn?**

Không mặc định. Cần hold có owner, case, phạm vi dataset và cơ chế release.

**12. Có nên xóa suppression khi xóa body của email marketing không?**

Không tự động. Suppression có mục đích ngăn gửi lại và policy riêng, nhưng vẫn phải giảm dữ liệu cá nhân.

**13. Hash email address có tự động trở thành anonymous không?**

Không. Nếu còn có thể liên kết hoặc tra ngược qua key/nguồn khác, đó có thể vẫn là dữ liệu cá nhân.

**14. Có thể xóa email khỏi mailbox người nhận sau khi SMTP đã gửi không?**

Thông thường không bằng Spring Mail hoặc SMTP. Ứng dụng chỉ kiểm soát những bản sao trong phạm vi của mình và provider theo hợp đồng/tính năng hỗ trợ.

**15. Vì sao phải xem cả log/APM khi thực hiện retention?**

Vì exception, debug trace hoặc support export có thể chứa body/recipient/secret dù DB đã purge.

**16. Vì sao backup restore cần deletion journal?**

Snapshot cũ có thể đưa dữ liệu đã xóa quay lại. Journal/tombstone giúp áp lại các quyết định deletion trước khi mở workload.

**17. Có thể dùng cryptographic erasure thay cho mọi tác vụ xóa không?**

Không. Nó chỉ có tác dụng với ciphertext được bảo vệ bởi key phù hợp; không xử lý bản plaintext trong logs, provider hoặc exports.

**18. Cleanup có nên chạy cùng transaction với object store delete không?**

Không nên giữ DB transaction mở trong lúc gọi network. Dùng manifest bền vững và các bước idempotent.

**19. Khi object delete trả timeout, có nên đánh dấu hoàn tất không?**

Không. Trạng thái chưa chắc chắn; cần kiểm tra và retry an toàn.

**20. Chứng minh một record đã xóa bằng cách nào?**

Kết hợp kết quả database, object inventory/version, deletion tasks, provider confirmation (nếu có), backup lifecycle và audit tối thiểu phù hợp.

**21. Nếu người dùng hủy một email đặt lịch, cleanup có được xóa content không?**

Sau khi hủy hợp lệ và không còn khả năng dispatch/hold, có thể purge theo policy. Cần giữ trạng thái hủy và xử lý race với worker.

**22. Nếu retention policy đổi, có nên xóa ngay mọi record cũ?**

Không tự động. Cần xác định quy tắc áp dụng hồi tố, hold, impact và migration có kiểm soát.

**23. Vì sao cần metric “dữ liệu quá hạn còn tồn” ngoài “dữ liệu đã xóa”?**

Vì hệ thống có thể xóa liên tục nhưng backlog overdue vẫn tăng. Số records quá hạn đo việc tuân thủ deadline thực tế.

**24. Làm sao tránh deletion worker xóa chứng từ nghiệp vụ được email tham chiếu?**

Phân định ownership giữa mail-specific copies và documents gốc; dùng references/permissions và không cho mail cleanup xóa tài nguyên ngoài phạm vi.

**25. Data retention có chỉ là một cron `DELETE` không?**

Không. Nó gồm classification, policy version, quyền truy cập, state-aware deadlines, deletion orchestration, legal hold, provider/backup handling, audit, monitoring và restore-safe controls.

## Kết luận

**Data retention cho nội dung và metadata email trong Spring Framework Mail là một thiết kế production xuyên suốt vòng đời dữ liệu, không phải một câu lệnh dọn bảng.** `JavaMailSender` đảm nhiệm SMTP submission; ứng dụng phải xác định body, subject, template model, raw MIME, attachments, attempts, provider events, suppression, logs và backups cần tồn tại trong bao lâu và vì mục đích gì.

Hãy **tách retention của content khỏi metadata**, tính deadline theo trạng thái và sự kiện phù hợp, không xóa payload còn `PENDING`, `PROCESSING`, `RETRY_PENDING` hoặc `SUBMISSION_UNKNOWN` chưa được giải quyết. Dùng cleanup batch có state/lease guard, durable deletion manifest cho database và object storage, idempotent retries, kiểm soát object versions và shared references. Tôn trọng legal hold có phạm vi, xử lý yêu cầu xóa theo dữ liệu thực sự tồn tại, giữ suppression tối thiểu để không gửi lại trái lựa chọn và thiết kế backup restore không hồi sinh dữ liệu đã purge.

Cuối cùng, **đo cả lượng dữ liệu quá hạn chưa xóa**, kiểm thử các failure windows, hạn chế quyền đọc dữ liệu đang được giữ và không tuyên bố xóa ở provider/recipient ngoài khả năng kiểm soát. Một retention policy tốt vừa bảo đảm email còn đủ dữ liệu để gửi và đối soát, vừa giảm tối đa lượng thông tin nhạy cảm còn tồn tại khi mục đích sử dụng đã kết thúc.

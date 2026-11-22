# Chọn lưu toàn bộ message hay chỉ lưu metadata

Trong **Spring Framework Mail**, email có thể chỉ là một thông báo ngắn cho khách hàng, nhưng cũng có thể là biên nhận thanh toán, bằng chứng một yêu cầu hỗ trợ, tài liệu được đối tác gửi vào mailbox hoặc một thông điệp có attachment rất lớn. Khi thiết kế hệ thống gửi/nhận thư, một quyết định quan trọng là: **lưu toàn bộ message gồm headers, body, MIME parts và attachments, hay chỉ lưu metadata để tra cứu và vận hành?**

Lưu toàn bộ có thể giúp **xem lại, phân tích lỗi, tái xử lý hoặc kiểm toán nội dung**, nhưng làm tăng chi phí, phạm vi dữ liệu nhạy cảm và yêu cầu kiểm soát bảo mật. Chỉ lưu metadata giúp dữ liệu nhỏ, dễ query và ít rủi ro lưu nội dung hơn, nhưng có thể **không đủ để dựng lại email đúng như thời điểm gửi/nhận**, nhất là khi template, dữ liệu nghiệp vụ hoặc file đính kèm đã thay đổi.

Trong thực tế, nhiều hệ thống cần **thiết kế kết hợp**: metadata có cấu trúc trong database, snapshots hoặc raw MIME đặt trong object storage có kiểm soát khi mục đích nghiệp vụ đòi hỏi. Cần quyết định riêng cho **outbound** (email do ứng dụng tạo và gửi qua SMTP) và **inbound** (email nhận từ mailbox IMAP/POP3 hoặc provider).

Bài này giải thích các lựa chọn, tiêu chí quyết định, cấu trúc dữ liệu, tính toàn vẹn, rủi ro PII, chi phí, lưu attachment, transactional outbox, failure recovery và kiểm thử.

## 1. Thế nào là toàn bộ message?

Một email theo RFC 5322/MIME có thể bao gồm:

~~~text
Message headers
  From / To / Cc / Reply-To
  Subject / Date / Message-ID
  References / In-Reply-To
  Content-Type / MIME-Version
  Received / DKIM-Signature / custom headers

MIME body
  multipart/mixed
    multipart/alternative
      text/plain
      text/html
    multipart/related
      inline image with Content-ID
    attachment: invoice.pdf
    attachment: report.csv
~~~

Một số dữ liệu liên quan lại nằm **ngoài** raw MIME:

- SMTP envelope sender và recipients, nhất là các Bcc recipients.
- Tài khoản/provider thật sự được sử dụng để gửi.
- SMTP reply code và lịch sử send attempts.
- Provider message ID và webhooks delivered/bounced/deferred.
- Tenant, business event và người dùng chịu trách nhiệm gửi.
- Quyết định authorization/consent và retry policy.

Vì vậy, **lưu full MIME không có nghĩa đã lưu đầy đủ toàn bộ lịch sử vận chuyển**. Nếu muốn trả lời vì sao một email không tới người nhận, vẫn cần metadata attempts và provider feedback.

### Raw MIME, bản sao bytes và khả năng dựng lại

Ba khái niệm thường bị nhầm:

1. **Raw MIME serialization:** tập headers + body/attachments đã được serialize ra một representation như file `.eml`.
2. **Original captured bytes:** chính xác chuỗi byte tại điểm nhận/gửi được xác định; cần capture đúng boundary.
3. **Reconstructible content:** template ID/version, body snapshot, dữ liệu nghiệp vụ và object references có thể dựng lại email có nội dung tương đương.

Một `MimeMessage.writeTo(outputStream)` có thể tạo representation sử dụng được, nhưng nếu message đã được parse rồi serialize, các bytes có thể khác gốc do line endings, header folding, boundaries hoặc encoding. Không gọi một bản reconstruct là bản gốc byte-for-byte nếu chưa có bằng chứng capture.

## 2. Metadata-only lưu những gì?

Metadata mô tả message mà không lưu toàn bộ body/attachment:

~~~json
{
  "mailJobId": "mail-981",
  "tenantId": "tenant-42",
  "direction": "OUTBOUND",
  "purpose": "PAYMENT_RECEIPT",
  "recipientContactId": "contact-77",
  "templateId": "PAYMENT_RECEIPT",
  "templateVersion": 4,
  "providerId": "relay-a",
  "submissionStatus": "SUBMITTED",
  "attemptCount": 2,
  "providerMessageId": "provider-msg-981",
  "submittedAt": "2026-11-12T12:00:00Z"
}
~~~

Có thể thêm:

- Business event ID hoặc order/payment reference.
- From/sender profile ID.
- Recipient count hoặc hashed identifiers.
- Mailbox account ID, folder và IMAP UID với inbound.
- MIME type, estimated bytes, attachment count.
- Content checksum, object storage reference nếu có.
- Retry deadline, error category và correlation ID.
- Retention, classification và tenant scope.

**Metadata-only không hẳn ẩn danh.** Email address, subject, Message-ID, recipient ID và một số error text vẫn có thể là dữ liệu cá nhân. Cần bảo vệ chúng theo chính sách.

## 3. Bốn chiến lược lưu trữ

| Mô hình | Lưu gì? | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **Metadata-only** | IDs, headers cần thiết, trạng thái, attempts | Nhẹ, query dễ, ít lưu body | Không replay nguyên content nếu nguồn mất |
| **Structured snapshot** | Metadata + text/HTML/domain snapshot + attachment references | Có thể dựng content ổn định | MIME serialization có thể khác |
| **Full raw MIME** | Metadata + file `.eml` chứa headers/body/attachments | Hữu ích cho forensic và reparse | Dữ liệu nhạy cảm, lớn, khó retention |
| **Hybrid/tiered** | Metadata DB + snapshot + raw khi cần | Cân bằng audit và hiệu năng | Phức tạp về lifecycle và consistency |

Một sơ đồ lựa chọn:

~~~mermaid
flowchart TD
    A["Mail event / received email"] --> B["Metadata DB record"]
    A --> C{"Retention/content policy"}
    C -->|"Chỉ trạng thái"| D["Metadata-only"]
    C -->|"Cần dựng lại"| E["Versioned snapshot"]
    C -->|"Cần nguyên MIME"| F["Encrypted raw .eml"]
    E --> G["Optional attachment storage"]
    F --> G
    B --> H["Search, attempts, audit"]
~~~

Không nhất thiết lưu cả snapshot và raw cho mọi message. Một tenant có 1.000.000 email marketing mỗi ngày có nhu cầu rất khác inbox nhận hợp đồng pháp lý.

## 4. Phải tách outbound và inbound

**Outbound:** ứng dụng sở hữu dữ liệu nguồn, template và logic gửi.

~~~text
Domain event -> mail outbox -> renderer
  -> MimeMessage -> JavaMailSender -> SMTP
~~~

Nếu nghiệp vụ chỉ cần biết đã cố gửi và trạng thái provider, metadata có thể đủ. Nếu email phải có nội dung đúng tại thời điểm tạo, cần snapshot hoặc version của dữ liệu/template/file.

**Inbound:** nội dung từ bên ngoài qua IMAP, POP3 hoặc provider inbound API.

~~~text
Mailbox / inbound provider
  -> raw message -> MIME parser
  -> metadata -> validation -> business job
~~~

Nếu ứng dụng chỉ lưu metadata và mailbox xóa thư, có thể mất body/attachment cần cho parser mới, điều tra khiếu nại hoặc xem lại ticket. Raw MIME hoặc structured content snapshot có thể cần thiết hơn inbound.

Nhưng inbound raw là **untrusted input**: HTML nguy hiểm, mã độc, malformed MIME, attachment quá lớn hoặc thông tin cá nhân phải được xử lý và bảo vệ.

## 5. Mục tiêu nghiệp vụ quyết định mức lưu

| Nhu cầu | Metadata-only | Snapshot | Raw MIME |
| --- | --- | --- | --- |
| Đếm mail đã enqueue | Đủ | Đủ | Không cần |
| Theo dõi SMTP failures | Đủ nếu có attempts | Đủ | Raw không thay attempts |
| Tìm theo job/provider ID | Đủ | Đủ | Cần index metadata |
| Xem email gửi tới khách hàng | Thường không đủ | Thường đủ | Đủ nếu giữ được |
| Tái gửi đúng thông tin biên nhận | Không nếu domain data đổi | Phù hợp | Có thể phù hợp |
| Điều tra MIME boundary/charset | Thiếu | Có thể thiếu | Phù hợp |
| Reparse inbound sau khi sửa parser | Không đủ | Tùy snapshot | Phù hợp |
| Kiểm chứng attachment gốc | Không nếu file mất | Có nếu file bất biến | Có nếu raw còn nguyên |
| Tối thiểu hóa PII | Thuận lợi | Cần policy | Rủi ro rộng hơn |
| Chứng minh delivered | Không tự đủ | Không | Raw cũng không đủ |

Bảng trên không phải tuyên bố mọi yêu cầu kiểm toán cần raw MIME. Cần xác định **quy định cụ thể, bằng chứng cần chứng minh, thời gian lưu và quyền truy cập** trước khi chọn.

## 6. Khi nào metadata-only là đủ?

Ví dụ email “báo cáo xử lý xong” chỉ dẫn người dùng tới dashboard, và thông tin báo cáo luôn có thể xem ở nguồn nghiệp vụ.

Có thể lưu:

~~~text
jobId
businessEventId
tenantId
recipientContactId
purpose
templateId/version
queuedAt
attemptCount
status
providerId
providerMessageId
failureCategory
~~~

Lợi ích:

- Không nhân bản body, PII và attachment.
- Dữ liệu nhỏ, dễ index và sao lưu.
- Truy cập vận hành không cần quyền xem nội dung thư.
- Ít rủi ro nếu metadata database bị lộ hơn so với lưu full body (nhưng vẫn nhạy cảm).
- Quản lý retention ít phức tạp hơn.

**Điều kiện quan trọng:** nếu worker cần retry sau nhiều giờ/ngày, phải chắc nguồn content còn tồn tại và có thể dựng lại theo đúng policy. Nếu source đã đổi hoặc file đã xóa, metadata-only sẽ không giúp dựng lại email cũ.

## 7. Khi nào structured snapshot hữu ích?

Biên nhận thanh toán có thể cần giữ:

~~~json
{
  "eventId": "payment-981-confirmed",
  "templateId": "PAYMENT_RECEIPT",
  "templateVersion": 4,
  "locale": "vi-VN",
  "recipientSnapshotId": "recipient-snapshot-981",
  "receiptSnapshotId": "receipt-snapshot-981",
  "attachmentObjectKey": "receipts/tenant-42/981-v1.pdf"
}
~~~

Snapshot phản ánh các giá trị tại thời điểm event, tránh đọc giá tiền, tên khách hàng hoặc trạng thái đơn hàng đã thay đổi nhiều ngày sau.

Cần định nghĩa:

- Template version và rendering locale.
- Immutable business snapshot/data version.
- Attachment version và checksum.
- Recipient semantics: địa chỉ lúc enqueue hay lúc send?
- Tính hợp lệ tại send time: consent, token expiry, tenant suspension.
- Thời hạn giữ dữ liệu và cách xóa.

Snapshot giúp **reconstruct content**, nhưng không bảo đảm cùng MIME header folding, boundary hoặc Message-ID.

## 8. Khi nào cần full raw MIME?

Những tình huống raw có giá trị:

- Nhận email hỗ trợ khách hàng và muốn xem lại original content.
- Nhận tài liệu/hợp đồng, cần reparse hoặc điều tra file lỗi.
- Kiểm tra vấn đề charset, inline image, Content-ID, multipart nesting.
- Cần phân tích raw headers phục vụ troubleshooting.
- Có yêu cầu lưu một artifact message tại điểm nhận/gửi được xác định.
- Muốn tái chạy MIME parser sau khi sửa logic.
- Cần kiểm chứng một attachment đã thực sự được nhận.

Nhưng raw MIME **không tự bảo đảm**:

- Tính xác thực người gửi.
- Giao dịch đã commit.
- SMTP relay đã accept.
- Email đã vào inbox người nhận.
- Người nhận đã mở thư.
- Bcc/envelope recipient đã được lưu đầy đủ.

Nếu raw MIME chứa DKIM-Signature, cần kiểm tra chữ ký theo cách độc lập; sự tồn tại của header không chứng minh chữ ký hợp lệ.

## 9. Dung lượng và chi phí thực tế

Một MIME có thể gồm:

~~~text
Plain text: 4 KiB
HTML: 12 KiB
Inline logo: 80 KiB
Invoice.pdf: 8 MiB
Report.zip: 20 MiB
~~~

Những file nhị phân được MIME base64 encode thường tăng đáng kể kích thước so với raw binary, thêm headers/boundaries và line wrapping.

Chi phí lưu raw không chỉ là object size:

- Số bản replication/backup.
- Object versions.
- KMS/encryption operations.
- Network egress khi tải phục vụ điều tra.
- Antivirus scanning.
- Index hoặc extracted-content cache.
- Retention/legal hold.
- Dữ liệu nhân bản nếu vừa giữ raw MIME vừa giữ attachments tách riêng.

Một ước lượng dung lượng:

~~~text
estimated_bytes =
    messages_per_day
    × mean_serialized_bytes
    × retention_days
    × replication_factor
    + attachments_copied
    + object_versions
    + indexes
~~~

Phải dựa trên phân phối size thực và các đuôi lớn, không chỉ average. Một số message hàng trăm MiB có thể chi phối chi phí.

## 10. Full MIME trong DB hay object storage?

| Tiêu chí | Database BLOB | Object storage |
| --- | --- | --- |
| Cùng transaction với metadata DB | Có thể, nếu cùng DB | Không mặc định |
| Phù hợp nhiều file lớn | Thường kém thuận lợi | Thường tốt hơn |
| Backup/replication | BLOB làm DB nặng | Storage policy độc lập |
| Search metadata | Dễ qua DB columns | Cần DB/index riêng |
| Retention | Theo schema/jobs | Lifecycle + DB coordination |
| Truy cập theo tenant | DB authorization | IAM + application authorization |
| Consistency | DB transaction | Cần state machine/checksum |
| Chi phí dữ liệu lớn | Có thể cao | Thường có storage tiers |

Với body nhỏ và nhu cầu nhất quán đơn giản, một DB column có thể đủ. Với raw MIME/attachments lớn, **metadata trong DB + encrypted object storage** thường dễ mở rộng hơn.

Tuy nhiên, object storage không có chung ACID transaction với DB. Phải xử lý tình huống object đã tồn tại nhưng DB commit lỗi, hoặc DB pointer đã commit nhưng object chưa sẵn sàng.

## 11. Bảo mật và PII không phải lựa chọn phụ

Một message có thể chứa:

- Email recipient, tên, địa chỉ, số điện thoại.
- Mã OTP hoặc reset-password URL.
- Dữ liệu thanh toán/hóa đơn.
- Hình ảnh, file tài chính và tài liệu cá nhân.
- Bản HTML có remote tracking URL.
- Headers có địa chỉ IP hoặc dữ liệu hạ tầng.
- Attachment nguy hiểm.

Nếu giữ full MIME:

1. Dùng encryption at rest/in transit và quản lý KMS.
2. Hạn chế quyền đọc/giải mã theo tenant/purpose.
3. Ghi audit mỗi lần xem/download/replay.
4. Sanitize HTML trước khi hiển thị và hạn chế remote resource.
5. Malware scan và quarantine attachment đáng ngờ.
6. Không ghi raw MIME vào log, metrics hoặc tracing.
7. Có retention, data deletion và backup policy rõ ràng.
8. Không cho phép truy cập object storage trực tiếp chỉ bằng một storage key suy đoán.
9. Không lưu vô hạn các token hoặc link còn hiệu lực.
10. Cân nhắc access approval cho forensic/legal hold.

**Metadata cũng có thể là PII**, nên không tự coi metadata-only là dữ liệu công khai.


## 12. Chọn chính sách theo mail purpose

Không nên dùng một flag `storeFullMessage=true` cho tất cả email.

| Loại thư | Lựa chọn thường hợp lý | Lưu ý |
| --- | --- | --- |
| OTP | Metadata tối thiểu | Không giữ mã OTP plaintext lâu |
| Password reset | Metadata + token reference được bảo vệ | Reset URL rất nhạy cảm và có TTL |
| Biên nhận thanh toán | Versioned snapshot và attachment bất biến | Phải phản ánh đúng số tiền/thời điểm |
| Thông báo vận hành | Metadata, attempts và failure audit | Không cần nhân bản production payload |
| Marketing | Metadata/consent audit, template version | Volume lớn, suppression và retention riêng |
| Inbound support | Structured content/attachment, raw MIME có TTL nếu cần | Xem lại mail và reprocess parser |
| Inbound hợp đồng | Raw MIME + extracted files theo yêu cầu cụ thể | Integrity, provenance, quarantine |
| Bounce/DSN | Normalized metadata + raw ngắn hạn khi điều tra | Liên kết provider ID và suppression |

Đây là khuyến nghị kỹ thuật để bắt đầu, không phải thời hạn lưu trữ pháp lý. Một tổ chức cần xác định retention theo jurisdiction, hợp đồng, dữ liệu và purpose.

Có thể mô tả bằng custom configuration:

~~~yaml
app:
  mail:
    retention:
      payment-receipt:
        metadata-days: 1095
        snapshot-days: 1095
        raw-mime-days: 0
      inbound-support:
        metadata-days: 365
        snapshot-days: 180
        raw-mime-days: 30
      password-reset:
        metadata-days: 30
        snapshot-days: 0
        raw-mime-days: 0
~~~

Namespace này do ứng dụng định nghĩa, Spring Boot không tự xóa message theo những thuộc tính này. Các con số chỉ minh họa.

## 13. Một schema metadata trung tâm

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_record (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    direction VARCHAR(16) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    business_event_id VARCHAR(160),
    recipient_reference VARCHAR(160),
    sender_profile_id VARCHAR(160),
    mailbox_account_id VARCHAR(160),
    mailbox_folder VARCHAR(240),
    imap_uid_validity BIGINT,
    imap_uid BIGINT,
    rfc_message_id VARCHAR(512),
    provider_message_id VARCHAR(512),
    template_id VARCHAR(160),
    template_version INTEGER,
    storage_policy VARCHAR(40) NOT NULL,
    raw_object_key VARCHAR(1024),
    snapshot_object_key VARCHAR(1024),
    content_sha256 VARCHAR(64),
    content_bytes BIGINT,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_or_received_at TIMESTAMP WITH TIME ZONE,
    retention_until TIMESTAMP WITH TIME ZONE
);
~~~

Schema chỉ là tham khảo; kiểu UUID, time zone, indexes và constraints cần phù hợp DB thật. Thực tế có thể tách inbound và outbound:

- `tenant_id`, `purpose` và `direction` giúp áp quyền và retention.
- `business_event_id` liên kết domain event/outbox.
- `mailbox_account_id`, `imap_uid_validity`, `imap_uid` xác định IMAP occurrence.
- `provider_message_id` phục vụ provider feedback.
- `template_version` giúp tái dựng nội dung phù hợp thời điểm.
- `raw_object_key`/`snapshot_object_key` trỏ tới artifact nếu policy lưu.
- `content_sha256`/`content_bytes` giúp kiểm tra lưu trữ và integrity.
- `retention_until` là dữ liệu chỉ đạo cleanup; không tự thực thi TTL.

Không dùng `Message-ID` làm business unique key tuyệt đối vì header có thể thiếu, trùng hoặc bị giả mạo.

## 14. Tách message, attempt, artifact và attachment

~~~mermaid
flowchart LR
    A["mail_record"] --> B["mail_send_attempt"]
    A --> C["mail_artifact"]
    A --> D["mail_attachment"]
    A --> E["mail_delivery_feedback"]
    C --> F["Encrypted object storage"]
    D --> F
~~~

Một cách tổ chức:

~~~text
mail_record
  mailId, tenantId, purpose, status, storagePolicy

mail_artifact
  artifactId, mailId, artifactType
  objectKey, objectVersion, sha256, bytes
  captureMethod, retentionUntil

mail_attachment
  attachmentId, mailId, storageKey
  safeFilename, declaredContentType, detectedContentType
  bytes, sha256, scanStatus

mail_send_attempt
  attemptId, mailId, providerId, accountId
  startedAt, outcome, smtpReplyCategory

mail_delivery_feedback
  eventId, mailId, eventType, sourceVerified
~~~

Tách records cho phép query status mà không load raw MIME, bảo vệ quyền xem artifact, giữ provider feedback lâu hơn raw khi cần và quản lý attachment độc lập.

Không tự giả định một `mail_record` có attachment hoặc raw artifact; với metadata-only, chúng có thể không tồn tại.

## 15. Lưu raw MIME ở thời điểm nào?

Outbound có các giai đoạn:

~~~text
Business event
  -> Mail intent/outbox
  -> Template render
  -> MimeMessage headers/body/attachments
  -> MIME serialization
  -> SMTP submission
  -> Provider delivery processing
~~~

**Lưu mail intent:** là dữ liệu nhỏ, có thể commit trong business transaction, nhưng chưa có full MIME.

**Lưu sau render/preparation:** có prepared MIME artifact để phân tích hoặc retry nội dung ổn định, nhưng bytes chưa chắc giống bản relay nhận nếu transport sửa headers/encoding.

**Lưu sau SMTP submission:** có thể gắn artifact với attempt, nhưng không tự chứng minh actual wire bytes/delivery; cần provider response/ID riêng.

Nếu raw MIME chứa OTP/token, một chính sách có thể cấm lưu content dù kỹ thuật có khả năng làm vậy.

### Không quên thời điểm nhận inbound

Với IMAP/provider inbound, nếu cần original byte-level source, nên capture tại điểm nhận phù hợp hoặc dùng raw-download API của provider. Re-serialize `MimeMessage` sau khi parse là **serialized reconstruction**, có thể khác nguyên bản.

## 16. Java: xuất một MimeMessage ra stream

~~~java
import java.io.IOException;
import java.io.OutputStream;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

public void writePreparedMime(
        MimeMessage message,
        OutputStream output)
        throws IOException, MessagingException {

    message.saveChanges();
    message.writeTo(output);
}
~~~

Đây là minh họa tạo **prepared MIME representation**. `saveChanges()` có thể thay đổi headers theo lifecycle; cần gọi theo contract của ứng dụng thay vì luôn làm trước/sau send mà không cân nhắc.

Một anti-pattern khi attachment lớn:

~~~java
ByteArrayOutputStream out =
        new ByteArrayOutputStream();

message.writeTo(out);

byte[] allBytes = out.toByteArray();
~~~

Cách này giữ toàn bộ serialized MIME trong RAM, có thể copy thêm buffer. Production nên stream qua output có quota/byte counter tới storage hoặc file staging có kiểm soát.

Nếu hệ thống đòi chứng cứ raw wire bytes, không đánh đồng `writeTo` với SMTP packet capture hay provider receipt.

## 17. Một abstraction cho artifact storage

~~~java
public enum MailArtifactType {
    PREPARED_MIME,
    CAPTURED_RAW_MIME,
    STRUCTURED_SNAPSHOT,
    ATTACHMENT
}
~~~

~~~java
public interface MailArtifactStore {

    StoredArtifact save(
            UUID mailId,
            MailArtifactType type,
            InputStreamSource source,
            long maxBytes);

    InputStream open(
            UUID mailId,
            UUID artifactId,
            AuthenticatedActor actor);

    void scheduleDeletion(
            UUID artifactId,
            Instant retentionUntil);
}
~~~

Những type như `StoredArtifact` và `AuthenticatedActor` do ứng dụng định nghĩa. Một implementation phải:

- Kiểm tra size tối đa thực tế khi streaming.
- Dùng object key do hệ thống cấp, không dùng raw user filename.
- Bảo vệ tenant authorization ngay cả khi có object key.
- Lưu object version/size/checksum.
- Ghi access audit khi xem raw.
- Cleanup theo retention/legal hold.
- Tránh gửi presigned URL thời hạn dài cho client không được phép.

Object key không phải password, nhưng có thể là dữ liệu nhạy cảm và không được coi như capability bỏ qua authorization.

## 18. Ranh giới transaction DB và object storage

Object storage không tự tham gia transaction của database.

~~~text
PUT object
INSERT mail_artifact pointer
COMMIT
~~~

Nếu PUT thành công nhưng DB commit lỗi, còn **orphan object**. Nếu đảo thứ tự:

~~~text
INSERT pointer
COMMIT
PUT object
~~~

thì khi PUT lỗi, DB có **dangling reference**.

Một lifecycle tham khảo:

~~~mermaid
flowchart TD
    A["Create content"] --> B["Upload to staging object"]
    B --> C["Verify bytes/checksum"]
    C --> D["DB transaction: artifact READY"]
    D --> E{"Commit success?"}
    E -->|"Yes"| F["Consumer may read"]
    E -->|"No"| G["Orphan cleanup"]
    B --> H["Staging TTL cleanup"]
~~~

Điều kiện:

1. Không publish artifact `READY` trước khi object có thể đọc lại.
2. Khi DB rollback, dọn orphan bằng TTL/reconciler.
3. Khi storage upload lỗi, không mark READY.
4. Với retries, kiểm soát object version/idempotent key.
5. Nếu object bị xóa bất ngờ, xử lý missing reference thay vì NPE.
6. Không xóa file khi còn mail job active cần retry.
7. Không giữ DB transaction mở trong lúc upload file lớn.

Nếu cần tạo artifact sau khi business outbox commit, có thể dùng trạng thái `WAITING_FOR_ARTIFACT`, sau đó worker chuẩn bị content/snapshot rồi chuyển `READY_TO_SEND`. Chỉ send SMTP sau khi dữ liệu cần thiết đã có.

## 19. Checksums và artifact version

Một artifact record có thể có:

~~~text
artifactId: artifact-981
mailId: mail-981
artifactType: CAPTURED_RAW_MIME
objectKey: mail/tenant-42/981/raw.eml
objectVersion: v17
sha256: 64-hex-character digest
bytes: 12984321
captureMethod: provider-raw-download
capturedAt: 2026-11-12T12:00:00Z
~~~

Checksum giúp phát hiện byte đọc lại khác với byte đã ghi nhận, hoặc upload thiếu. Version giúp tránh worker lấy nhầm attachment đã bị thay.

**Checksum không tự chứng minh ai là người gửi hoặc SMTP có gửi thật.** Nó cũng không phải chữ ký số, không tự chứng minh tính hợp pháp của nội dung. Muốn nonrepudiation/forensic, cần ký hoặc chain-of-custody theo yêu cầu.

Không dùng hash như khóa duy nhất của business message. Hai email có thể cùng content mà khác recipient/event. Content-addressable dedup xuyên tenant còn có nguy cơ rò dữ liệu và phức tạp khi một tenant yêu cầu xóa.

## 20. IMAP inbound: capture trước khi folder đóng

Với Spring Integration Mail, receiver có thể cung cấp Jakarta Mail `Message`/`MimeMessage`. Một số nội dung được đọc lazy qua folder/session.

~~~text
ImapMailReceiver
  -> discover UID + folder
  -> capture metadata/raw/content theo policy
  -> durable persist
  -> ack/move/mark mail
  -> business queue
~~~

Không chuyển một live `MimeMessage` vào một queue xử lý sau nhiều giờ rồi giả định folder còn mở. Nếu cần replay, capture raw hoặc các thành phần có giá trị bền vững **trước khi session bị đóng**, trong giới hạn size và bảo mật.

Để tránh duplicate inbound, có thể định danh bằng tuple:

~~~text
mailboxAccountId
+ folderId
+ uidValidity
+ uid
~~~

IMAP UID phải gắn với UIDVALIDITY; Message-ID có thể giả mạo/trùng/thiếu. Nhưng dù định danh chính xác, **UID vẫn không chứa body/attachment**. Nếu source email bị expunge mà ứng dụng chỉ lưu UID/subject, không thể khôi phục file gốc.

Không đánh dấu/xóa mail trước durable capture nếu điều đó khiến message biến mất khỏi search/retry.


## 21. Outbox intent và raw MIME là hai quyết định khác nhau

Một transactional outbox job thường là **ý định gửi**:

~~~text
BEGIN DB transaction
  update order/payment
  insert mail_outbox intent
COMMIT

worker
  claim job
  load approved content/attachment
  render MIME
  submit SMTP
  record outcome
~~~

Không có yêu cầu kỹ thuật rằng outbox phải lưu full serialized MIME. Một job có thể tham chiếu:

~~~json
{
  "mailJobId": "mail-981",
  "templateId": "ORDER_CONFIRMATION",
  "templateVersion": 3,
  "recipientRef": "contact-77",
  "businessSnapshotRef": "order-snapshot-981",
  "attachmentRefs": []
}
~~~

Nếu template và snapshot version cố định, worker có thể tạo nội dung hợp lệ sau khi restart. Nếu payload chứa mutable domain reference mà dữ liệu đã đổi, sẽ có semantic drift.

### Raw MIME có giúp exactly-once không?

Không. Worker có thể:

~~~text
send MIME -> SMTP accepts -> worker crash
 -> DB status chưa SUBMITTED -> retry same MIME
~~~

Provider có thể gửi trùng. Giữ raw giúp nội dung ổn định giữa attempts nhưng **không tạo transaction chung với SMTP** hoặc một universal idempotency key trên receiving MX.

### Replay còn phụ thuộc quyền và thời hạn

Nếu job chờ 2 ngày:

- OTP có thể đã hết hạn.
- Recipient marketing có thể unsubscribe.
- Tenant có thể bị khóa.
- Sender domain có thể không còn verified.
- Tài liệu được yêu cầu xóa.
- Attachment có thể vượt retention.

Do đó phải tách **content snapshot policy** khỏi **send-time eligibility policy**.

## 22. Chọn metadata cho trạng thái và delivery feedback

Nếu mục tiêu là vận hành, cần dữ liệu có cấu trúc ngay cả khi raw MIME được lưu.

Một attempt record:

~~~text
attemptId
mailJobId
providerId
senderAccountId
attemptNumber
startedAt
finishedAt
submissionOutcome
failureCategory
smtpReplyCode
providerMessageId
~~~

Một delivery feedback record:

~~~text
providerEventId
providerMessageId
mailJobId
recipientReference
eventType: DELIVERED / BOUNCED / DEFERRED / COMPLAINED
occurredAt
receivedAt
sourceVerified
~~~

`JavaMailSender.send(...)` trả thành công chỉ cho biết transport không báo lỗi ở thời điểm submit; **không chứng minh delivered hay read**.

Nếu một provider dùng webhook, cần verify signature/source, dedupe event và map đúng tenant/account. Không tin raw tenant ID trong webhook nếu chưa xác minh.

Giữ raw MIME không tự cung cấp những event này. Việc phân tách records giúp giữ metadata/audit lâu hơn content khi cần.

## 23. Một message gửi cho nhiều người nhận

Một `MimeMessage` có thể có nhiều To/Cc/Bcc recipients. Vấn đề lưu trữ:

- Raw MIME headers không nhất thiết lưu Bcc envelope.
- Cùng một message có thể bị SMTP chấp nhận cho một số recipients và từ chối số còn lại.
- Retry cả message có thể gửi trùng cho recipient đã accept.
- Người nhận không được phép biết nhau không nên lộ trong To/Cc chung.
- Retention hoặc yêu cầu xóa dữ liệu có thể khác giữa recipients.

Với transactional notification cá nhân hóa, **một mail job/recipient** thường giúp:

- Theo dõi trạng thái riêng.
- Áp suppression/consent đúng.
- Dedupe/retry độc lập.
- Dễ liên kết provider feedback.
- Giữ recipient snapshot/metadata theo đúng chính sách.

Nếu dùng một MIME nhiều người, lưu thêm recipient-level attempt state; không coi raw To/Cc là toàn bộ SMTP envelope.

## 24. Content-ID và inline images

Một email HTML có thể chứa:

~~~html
<img src="cid:logo-123" alt="Logo">
~~~

MIME sẽ có một part mang `Content-ID` tương ứng. Nếu chỉ lưu HTML string mà không giữ inline image bytes/reference, giao diện xem lại hoặc retry có thể hiển thị ảnh hỏng.

Các lựa chọn:

- Raw MIME: giữ multipart structure và inline assets trong artifact.
- Structured snapshot: giữ HTML + map Content-ID → immutable object key.
- Metadata-only: không xem lại nội dung; chỉ cho phép nếu use case không cần render.

Tương tự, `multipart/alternative` chứa cả `text/plain` và `text/html` có thể biểu diễn cùng nội dung ở hai dạng. Đừng tái tạo chỉ HTML rồi tuyên bố đã lưu nguyên message.

Một content snapshot đầy đủ cho replay cần quy định cả text/plain, HTML, inline assets, attachments, charset và locale.

## 25. Quản lý attachment riêng

Schema attachment minh họa:

~~~sql
CREATE TABLE mail_attachment (
    id UUID PRIMARY KEY,
    mail_id UUID NOT NULL,
    tenant_id VARCHAR(120) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    object_version VARCHAR(160),
    filename_safe VARCHAR(255),
    content_type_declared VARCHAR(200),
    content_type_detected VARCHAR(200),
    sha256 VARCHAR(64) NOT NULL,
    byte_length BIGINT NOT NULL,
    scan_status VARCHAR(40) NOT NULL,
    retention_until TIMESTAMP WITH TIME ZONE
);
~~~

Các điểm quan trọng:

- Tên file là untrusted input; sanitize và không dùng làm storage path.
- `Content-Type` do người gửi khai báo chưa chứng minh định dạng.
- Cần giới hạn size, part count, nested MIME depth.
- Malware scanning/quarantine theo policy.
- Streaming thay cho `readAllBytes()` không giới hạn.
- Raw object và extracted attachments có thể bị nhân bản dữ liệu.
- Không xóa attachment khi outbox job còn cần retry.
- Không cho tenant khác đọc object chỉ bằng key.

Nếu muốn deduplicate attachments theo content hash, cần chính sách quyền và xóa dữ liệu cẩn thận để tránh cross-tenant information leakage.

## 26. Metadata-only và khả năng phục hồi

Giả sử một outbox job được tạo:

~~~text
jobId: mail-981
templateId: INVOICE
invoiceId: invoice-981
status: PENDING
~~~

Nhưng trước khi worker gửi, hóa đơn đã bị cập nhật và object PDF cũ được dọn. Khi đó, chỉ lưu invoice ID **không đủ** để gửi nội dung đã được phê duyệt lúc enqueue.

Giải pháp phụ thuộc hợp đồng:

- Pin invoice version và giữ immutable snapshot.
- Tạo PDF object bền vững trước khi job `READY`.
- Lưu template/version và dữ liệu event cần thiết.
- Đặt TTL hoặc cancel job nếu content không còn hợp lệ.
- Nếu nghiệp vụ cho phép đọc latest state, ghi rõ behavior.

Cần phân biệt:

**Metadata-only:** chỉ mô tả event và status; không chứa đủ dữ liệu dựng lại.

**Reconstructible metadata:** references đến những nguồn khác được cam kết còn tồn tại và có version.

**Snapshot:** dữ liệu nội dung đã được cố định.

**Raw MIME:** một representation message đã serialize/capture.

Gọi mọi thứ là “metadata” khiến người phát triển tưởng có thể replay khi thực tế không thể.

## 27. Privacy và data minimization theo từng trường

Ngay cả một metadata table có thể tiết lộ nhiều thứ:

~~~text
recipient = user@example.org
subject = Ket qua xet nghiem ...
messageId = ...
tenantId = ...
providerError = ...
~~~

Thay vì giữ tất cả, có thể:

- Lưu `recipientContactId` và resolve theo quyền.
- Lưu purpose/subject category thay vì subject text.
- Lưu hash/HMAC address khi chỉ cần correlation, kèm key management.
- Phân tách encrypted contact data khỏi operational status.
- Redact tokens khỏi exception reason.
- TTL cho headers raw và provider metadata chứa PII.
- Giữ business event reference thay vì trích toàn body.

**Hash đơn thuần của địa chỉ email không luôn ẩn danh**, vì có thể đoán theo dictionary. Khi dùng HMAC hoặc pseudonymization cũng cần bảo vệ key và xem kết quả vẫn có thể là dữ liệu cá nhân tùy quy định.

## 28. Encryption và key lifecycle

Khi lưu full MIME hoặc snapshot:

1. Dữ liệu nên được truyền qua TLS.
2. Storage có encryption at rest, thường quản lý bởi KMS.
3. IAM giới hạn đối tượng nào được decrypt/download.
4. Data key/tenant key và rotation cần chính sách rõ.
5. Logs/backups không được để lộ raw content.
6. Khi retention hết, lifecycle xóa cả objects và versions phù hợp.
7. Legal hold có quyền hạn riêng, được audit.
8. Temporary files/staging phải có TTL và quyền tối thiểu.

Nếu dùng encryption cấp ứng dụng, phải bảo đảm worker còn có quyền decrypt khi retry, nhưng các tài khoản support không tự có quyền xem nội dung. Key rotation không được làm mất khả năng giải mã các artifacts chưa hết retention.

Đối với dữ liệu nhiều tenant, cân nhắc encryption keys và access boundaries riêng theo tenant hoặc nhóm dữ liệu, tùy mức cô lập cần thiết.

## 29. Retention thực sự liên quan nhiều bản sao

Một email có thể tồn tại ở:

~~~text
mail_record metadata
mail_artifact raw .eml
mail_attachment extracted files
search index / extracted text
cache / thumbnail
temporary staging object
backup / replica
provider mailbox
SMTP provider logs
application logs
~~~

Khi ra quyết định “giữ raw 30 ngày”, phải biết **30 ngày áp vào bản sao nào**. Xóa `mail_artifact` row không tự xóa object/version và không xóa nội dung đã copy vào search index.

Một retention engine có thể:

- Tìm artifacts quá hạn.
- Kiểm tra legal hold và active retry references.
- Đưa vào deletion queue có audit.
- Xóa object versions/derivatives theo policy.
- Cập nhật state `DELETED` hoặc tombstone.
- Xử lý retry nếu storage delete tạm lỗi.
- Giữ metadata tối thiểu nếu có cơ sở.
- Kiểm tra backup retention riêng.

### Xóa theo yêu cầu người dùng

Nếu có yêu cầu xóa dữ liệu, phải xác định đối tượng nào là nội dung riêng tư, bản sao nào được giữ hợp pháp và các job retry còn đang tham chiếu nội dung đó. Không để một outbox worker tiếp tục gửi message bị yêu cầu hủy chỉ vì raw MIME vẫn còn trong storage.

## 30. Legal hold và điều tra nội bộ

Một số tổ chức có quy trình legal hold đối với nội dung liên quan vụ việc đang điều tra. Khi đó:

- Policy retention thường có ngoại lệ do bộ phận có thẩm quyền quyết định.
- Không cho mọi user đặt legal hold tùy ý.
- Ghi người/phòng ban và lý do tạo hold.
- Đặt quyền đọc artifact tách biệt với quyền vận hành gửi email.
- Audit export/download.
- Duy trì integrity/version.
- Có quy trình kết thúc hold và resume retention.
- Không lẫn lộn legal hold với “giữ forever” không có căn cứ.

Đây là yêu cầu quản trị dữ liệu, không phải một property Spring Mail. Ứng dụng cung cấp primitives, còn chính sách phải được phê duyệt theo bối cảnh thực.

## 31. Search index và tìm nội dung

Raw MIME BLOB không tự search được nội dung theo nhu cầu support.

Có thể index:

- Mail job ID, business event ID, tenant.
- Provider message ID.
- Direction, purpose, time range.
- Recipient reference theo quyền.
- Normalized subject category.
- Attachment metadata.
- Optional extracted text theo policy.

Nhưng một full-text index body tạo **bản sao dữ liệu nhạy cảm**. Khi raw/snapshot bị xóa hoặc quyền bị thu hồi, index và caches phải cập nhật tương ứng.

Không để một shared search index trả snippet tenant A cho user tenant B chỉ vì application chỉ check tenant ở lúc mở chi tiết mà không lọc query.

## 32. Người dùng xem lại raw email thế nào?

Một viewer cần:

~~~text
Authorized support agent
  -> check tenant / ticket access
  -> fetch metadata
  -> request normalized body
  -> sanitize HTML / block remote resources
  -> render trong isolated viewer
  -> audit access
~~~

Khi tải file `.eml`:

- Dùng server-side streaming hoặc URL ký ngắn hạn với quyền.
- Không cho URL public indefinite.
- Đặt Content-Type/Content-Disposition an toàn.
- Không tự mở attachment nguy hiểm trong trình duyệt.
- Có scan/quarantine state.
- Rate limit download.
- Log actor, purpose và artifact ID.

Việc lưu full MIME hữu ích cho điều tra, nhưng không đồng nghĩa mọi nhân viên có quyền xem raw content.

## 33. Monitoring chiến lược lưu trữ

| Metric | Ý nghĩa |
| --- | --- |
| `mail_storage_metadata_count` | Số record metadata |
| `mail_storage_raw_mime_bytes` | Dung lượng raw MIME |
| `mail_storage_snapshot_bytes` | Dung lượng snapshot |
| `mail_storage_attachment_bytes` | Dung lượng attachment |
| `mail_storage_upload_failure_total` | Upload thất bại |
| `mail_storage_checksum_mismatch_total` | Integrity failure |
| `mail_storage_missing_object_total` | Dangling reference |
| `mail_storage_orphan_object_total` | Object chưa có DB reference |
| `mail_storage_cleanup_failure_total` | Xóa thất bại |
| `mail_storage_retention_overdue_count` | Artifact quá hạn còn tồn tại |
| `mail_storage_quarantine_count` | Artifact bị cách ly |
| `mail_storage_artifact_read_total` | Lượt xem/tải artifact |
| `mail_storage_replay_failure_total` | Replay không đọc được content |

Metrics label nên dùng purpose, direction, artifact type, storage tier, error category. Không đưa raw subject, recipient email hoặc object key chứa PII vào label.

Cần cảnh báo khi DB record `READY` nhưng object không tồn tại, checksum mismatch, storage gần quota, orphan staging tăng hoặc retention cleanup không chạy.

## 34. Một kiến trúc tham khảo cho production

~~~mermaid
flowchart TD
    A["Business outbox / inbound receiver"] --> B["Policy resolver theo purpose"]
    B --> C["Metadata record"]
    B --> D{"Content policy"}
    D -->|"Metadata"| E["Không lưu body"]
    D -->|"Snapshot"| F["Immutable snapshot"]
    D -->|"Raw MIME"| G["Bounded MIME capture"]
    F --> H["Encrypted object storage"]
    G --> H
    H --> I["Checksum + version"]
    I --> J["Artifact READY"]
    C --> K["Attempts / provider feedback"]
    J --> L["Authorized replay / viewer"]
    K --> M["Audit / monitoring"]
    L --> M
~~~

Các ranh giới:

- **Policy:** quyết định dữ liệu nào phải giữ và thời hạn.
- **Metadata DB:** phục vụ tra cứu trạng thái/attempts và quyền.
- **Artifact storage:** giữ content lớn có size caps, checksum, encryption.
- **Mail transport:** SMTP/IMAP operations; không giao dịch nguyên tử với DB/object store.
- **Business authorization:** xác minh tenant, recipient, consent và quyền replay.
- **Lifecycle:** cleanup, restore, quarantine, legal hold và reconciliation.
- **Observability:** phát hiện mất object, thiếu content, backlog và truy cập trái phép.

Mô hình này không có nghĩa ứng dụng nhỏ phải triển khai mọi thành phần ngay. Nhưng khi quyết định metadata-only hay full raw, cần xác định rõ những khả năng nào được cam kết cho lần retry, lần kiểm toán và lần xóa dữ liệu về sau.


## 35. Cách đưa ra quyết định khi bắt đầu một dự án

Thay vì bắt đầu bằng câu hỏi “có nên lưu full MIME không?”, hãy xác định **kết quả cần đạt**:

| Câu hỏi | Nếu câu trả lời là “Có” | Tác động thiết kế |
| --- | --- | --- |
| Cần xem lại chính xác nội dung customer đã gửi? | Có | Cần content snapshot hoặc raw inbound |
| Cần điều tra MIME/headers gốc? | Có | Cân nhắc raw source capture tại điểm phù hợp |
| Có thể tái tạo body từ immutable snapshot? | Có | Structured snapshot có thể đủ |
| Có attachment không thể lấy lại từ nguồn? | Có | Phải giữ attachment/raw trong storage bền vững |
| Email chứa token nhạy cảm có TTL ngắn? | Có | Ưu tiên metadata tối thiểu |
| Chỉ cần đối soát gửi thành công/bounce? | Có | Metadata/attempt/provider feedback thường đủ |
| Có yêu cầu retained communication theo quy định? | Có | Thiết kế nội dung/retention/access đúng phạm vi |
| Volume lên tới hàng triệu mail/ngày? | Có | Tính storage/network/backup/retention sớm |
| Mailbox inbound có thể bị expunge? | Có | Capture nội dung cần thiết trước acknowledgment |
| Nhiều tenant dùng chung hạ tầng? | Có | Tenant isolation trên DB, object và search |
| Cần replay sau khi template/DB thay đổi? | Có | Pin template/snapshot/attachment versions |
| Có nhu cầu delete/retention phức tạp? | Có | Tách metadata, snapshot, raw và derivative lifecycle |

Nếu mục tiêu chỉ là đối soát submission, không nên tự động lưu raw có thể chứa credential hoặc PII. Nếu nghiệp vụ cần chứng minh **nội dung cụ thể của một bản gửi**, metadata-only thường không đủ.

### Ba câu hỏi chốt

1. **Nếu xóa content ngay hôm nay, ngày mai hệ thống có mất khả năng thực hiện nghiệp vụ đã hứa không?**
2. **Nếu giữ content, ai được xem và trong bao lâu?**
3. **Nếu nội dung thay đổi giữa hai attempts, điều đó có vi phạm hợp đồng email không?**

Trả lời ba câu này trước khi tối ưu kích thước lưu trữ.

## 36. Chiến lược theo giai đoạn trưởng thành

**Giai đoạn nhỏ:** một ứng dụng gửi vài email thông báo, content đơn giản.

- Lưu outbox metadata và idempotency key.
- Pin template ID/version, business snapshot khi cần.
- Không lưu raw MIME nếu không có use case.
- Lưu attempts/retries để không mất công việc khi restart.

**Giai đoạn có inbound và attachments:**

- Tách object storage cho raw/content/attachment cần giữ.
- Enforce MIME size limits và malware scanning.
- Dùng UID/idempotency cho inbound.
- Quản lý object reference và retention.

**Giai đoạn multi-tenant/compliance:**

- Content policy theo purpose và tenant.
- KMS/IAM/audit access.
- Artifact versions/checksum.
- Cleanup/reconciliation/legal hold.
- Search index được phân quyền.
- Monitoring storage, orphan objects và deletion.

Không nhất thiết bỏ mô hình đơn giản chỉ để áp kiến trúc phức tạp. Nhưng khi retention/audit/replay là cam kết sản phẩm, cần có thiết kế bền vững ngay từ đầu.

## 37. Kiểm thử metadata-only

Test không chỉ xem một database row được insert. Cần kiểm tra contract mà metadata-only hứa:

1. Khi business transaction commit, metadata/job được persist.
2. Khi rollback, không có outbox intent.
3. Khi SMTP thất bại, attempts và failure category được lưu.
4. Khi job retry, content có thể resolve theo snapshot/reference contract.
5. Nếu source content đã hết hạn, job được chuyển state hợp lệ thay vì gửi sai.
6. Khi provider webhook đến, mapping về đúng job/tenant.
7. Không lưu raw body/token trong log, status hoặc retry metadata.
8. Retention cleanup xóa những trường không còn được phép giữ.

Ví dụ test:

~~~java
@Test
void mailIntentKeepsTemplateVersion() {

    MailIntent intent =
            mailService.planPaymentReceipt(
                    paymentId
            );

    assertEquals(
            4,
            intent.templateVersion()
    );

    assertNotNull(
            intent.businessSnapshotRef()
    );
}
~~~

`MailIntent` và `mailService` là abstraction do ứng dụng tự định nghĩa. Test kiểm tra một yêu cầu thiết kế cụ thể, không phải API sẵn có của Spring.

### Test thiếu reference

~~~text
Given: outbox job PENDING
And: snapshot object đã bị xóa nhầm
When: worker cố resolve content
Then: không gửi email rỗng
And: trạng thái lỗi/storage incident được ghi
And: retry hoặc manual action theo policy
~~~

Nếu metadata-only chỉ lưu references, cần chứng minh các references sống đủ lâu cho retry window và bản version không bị thay.

## 38. Kiểm thử raw MIME và snapshot

Một integration test có thể dựng `MimeMessage` bằng Jakarta Mail:

~~~java
@Test
void storesPreparedMimeArtifact()
        throws Exception {

    MimeMessage mime =
            new MimeMessage(
                    Session.getInstance(
                            new Properties()
                    )
            );

    mime.setFrom(
            "sender@example.test"
    );
    mime.setRecipients(
            Message.RecipientType.TO,
            "recipient@example.test"
    );
    mime.setSubject(
            "Hóa đơn tháng 11", "UTF-8"
    );
    mime.setText(
            "Nội dung thử nghiệm", "UTF-8"
    );

    mime.saveChanges();

    StoredArtifact artifact =
            artifactService.storePreparedMime(
                    mailId, mime
            );

    assertTrue(
            artifact.byteLength() > 0L
    );
    assertNotNull(
            artifact.sha256()
    );
}
~~~

Các class `StoredArtifact`, `artifactService` là ứng dụng tự định nghĩa. Những import cần thiết tùy test: `jakarta.mail.Session`, `jakarta.mail.Message`, `jakarta.mail.internet.MimeMessage` và `java.util.Properties`.

Đây là test **artifact storage/serialization**, không chứng minh actual SMTP wire bytes hoặc delivery. Bài test cần thêm readback bằng strict parser hoặc byte comparison theo contract capture.

### Test multipart và inline asset

Dựng MIME có:

- Plain text và HTML alternatives.
- Inline image `Content-ID`.
- PDF attachment nhỏ.
- Filename Unicode.
- Nested multipart.
- MIME header đặc biệt.

Sau store/readback, kiểm tra những thành phần cần bảo tồn theo policy. Nếu contract là byte-for-byte capture, so byte stream đã capture; nếu contract là semantic snapshot, so subject/body/attachment contents và metadata có ý nghĩa.

## 39. Kiểm thử object/DB consistency

Một số failure injection quan trọng:

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Storage PUT lỗi giữa stream | Không mark READY, dọn staging |
| PUT xong nhưng DB rollback | Reconciler xóa orphan |
| DB pointer commit nhưng object không đọc được | Alert và trạng thái lỗi rõ |
| SHA-256 khác khi readback | Không gửi/replay artifact bị hỏng |
| Worker crash giữa upload | Staging TTL cleanup |
| Retry upload cùng mail ID | Không overwrite nhầm version |
| Attachment bị xóa sớm | Retry job fail có kiểm soát |
| Legal hold active | Cleanup không xóa trái policy |
| Retention tới hạn | Xóa raw, derivatives và metadata theo policy |
| Object được nhiều jobs tham chiếu | Không xóa khi còn live reference |
| Cross-tenant read | Bị chặn ở application và storage boundary |
| Malware scan chưa xong | Không phục vụ file chưa được phép |

Nên dùng một object store thử nghiệm và database test trong integration tests. Không chạy automated tests trên production bucket hoặc xóa dữ liệu thật.

### Không trộn content QA với storage tests

Storage integration test xác nhận object bytes, references, transactional state và cleanup hoạt động như contract. Việc đánh giá câu chữ email/template là một loại test khác. Một bài có raw artifact lưu đúng vẫn có thể gửi nội dung sai nếu business renderer sai.

## 40. Kiểm thử inbound retention và recovery

Một test inbound với IMAP test server (ví dụ GreenMail nếu dự án dùng) có thể thực hiện:

~~~text
1. Seed một MIME mail vào test INBOX.
2. Receiver lấy account/folder/UID metadata.
3. Capture content/raw theo policy.
4. Commit ingestion record và artifact reference.
5. Simulate mailbox message deleted/expunged.
6. Business reprocessor đọc artifact, không phụ thuộc mailbox.
7. Poll lại cùng UID namespace không tạo duplicate.
~~~

Các điều cần chú ý:

- Folder/session lifecycle của `MimeMessage`.
- UID/UIDVALIDITY khi server cung cấp.
- MIME parser và file size bounds.
- No mark/delete trước durable capture khi retry phụ thuộc thư.
- Reprocess không sinh hai business side effects.
- Tài nguyên test cô lập, không dùng inbox cá nhân/production.

Nếu policy metadata-only inbound, test cần thể hiện rõ những gì **không được hỗ trợ**, ví dụ không có chức năng xem raw attachment sau khi mailbox bị expunge.

## 41. Kiểm thử bảo mật truy cập raw

Các tình huống:

- Support agent tenant A không tải được raw mail tenant B.
- Không có quyền raw-download thì chỉ xem metadata được phép.
- URL ký hết hạn không thể dùng lại.
- HTML có remote image không tự được tải khi preview.
- Attachment chưa qua scan không được download công khai.
- Object key path traversal không điều khiển storage path.
- Audit ghi actor và mục đích download.
- Service account xử lý retry được đọc snapshot cần thiết nhưng không có quyền quản trị mọi bucket.
- Một raw message có reset token bị che/lưu ngắn hạn đúng policy.
- Delete request làm derived indexes/caches được dọn đúng chính sách.

Đây là các kiểm thử authorization/data lifecycle; không nên chỉ unit test một phương thức `canRead()` rồi coi toàn bộ object store IAM đã được bảo vệ.

## 42. Những sai lầm kiến trúc thường gặp

### 42.1. Lưu full MimeMessage như một Java object trong database

`MimeMessage` không phải entity serialization ổn định cho durable storage. Có thể gắn với folder/session, chứa streams và internal state. Nên lưu một **serialized MIME artifact** hoặc một snapshot DTO có schema version.

### 42.2. Chỉ lưu Message-ID và nghĩ có thể tìm lại body

Header Message-ID không phải durable content address của provider và có thể bị trùng/giả. Nếu mailbox xóa, content có thể mất.

### 42.3. Lưu raw MIME nhưng không lưu SMTP envelope/attempts

Bcc, provider account, retry outcomes và delivery events có thể không có trong MIME. Vẫn phải lưu metadata vận hành.

### 42.4. Gọi MimeMessage.writeTo là bằng chứng bytes gốc

Serialization có thể thay đổi headers/boundaries/encoding. Phải xác định capture point và artifact type.

### 42.5. Lưu một byte[] lớn trong outbox DB

Làm tăng backup, memory, DB I/O và nguy cơ lộ PII. Với file lớn, dùng object storage có policy.

### 42.6. Chỉ lưu metadata nhưng template/file mutable

Worker retry có thể dựng nội dung khác. Pin snapshot/attachment version nếu cần.

### 42.7. Lưu hết email vô hạn vì “phòng khi cần”

Dữ liệu nhạy cảm và chi phí tích lũy; cần purpose/retention được phê duyệt.

### 42.8. Xóa raw object mà quên index/thumbnail/cache

Dữ liệu vẫn còn trong bản sao dẫn xuất. Cleanup phải bao phủ derivatives.

### 42.9. Database trỏ vào object chưa upload xong

Worker có thể gặp missing/corrupt artifact. Dùng staging và trạng thái READY sau xác nhận storage.

### 42.10. PUT object xong, DB rollback, không cleanup

Tạo orphan storage tốn chi phí và có thể tồn tại quá retention.

### 42.11. Dùng checksum như chứng minh sender authenticity

Checksum chỉ xác minh integrity so với giá trị tham chiếu; không tự chứng minh danh tính hoặc delivery.

### 42.12. Hiển thị raw HTML trực tiếp

Có thể gây tracking hoặc nội dung độc hại. Dùng sanitizer/sandbox và quyền truy cập.

### 42.13. Tin filename/Content-Type của attachment

Metadata do sender cung cấp là untrusted; cần content validation và scanning.

### 42.14. Dùng object key như authorization token

Biết key không được đồng nghĩa có quyền đọc. Cần IAM/application authz.

### 42.15. Dedupe raw attachments xuyên tenant không kiểm soát

Có nguy cơ inference và sai chính sách xóa. Bảo vệ ownership và lifecycle.

### 42.16. Tưởng có raw MIME là retry không gửi trùng

SMTP accepted rồi worker crash vẫn có thể resend. Outbox không tạo exactly-once.

### 42.17. Không recheck consent/token validity khi replay

Content cũ có thể không còn được phép gửi dù bytes không đổi.

### 42.18. Chỉ monitoring số bytes lưu

Cần theo dõi orphan, checksum mismatch, access và retention compliance.

### 42.19. Không phân biệt prepared MIME và captured original

Dễ tuyên bố sai về giá trị chứng cứ. Ghi rõ capture method/version/time.

### 42.20. Không định nghĩa yêu cầu khôi phục trước khi chọn metadata-only

Lúc sự cố mới phát hiện file đã mất hoặc body không còn reconstruct được.

## 43. Câu hỏi tình huống

**Câu 1.** Chỉ cần đếm email đã gửi và xem lỗi SMTP. Có cần full MIME không?

Thông thường không. Metadata job/attempt/provider feedback đủ cho mục tiêu này nếu không có yêu cầu xem lại body.

**Câu 2.** Biên nhận cần phản ánh đúng số tiền khi thanh toán, còn order có thể thay đổi. Nên lưu gì?

Một immutable snapshot của giao dịch, template version và receipt/attachment version phù hợp.

**Câu 3.** Inbound mail có attachment, provider xóa INBOX sau 7 ngày. Chỉ lưu subject và UID có đủ cho reprocess sau một tháng không?

Không. Cần capture nội dung/attachment cần thiết trước thời điểm bị xóa.

**Câu 4.** Gọi `mime.writeTo(out)` có chắc xuất bytes giống hệt SMTP server nhận không?

Không. Phải xác định capture boundary và các thay đổi serialization/transport.

**Câu 5.** Có raw MIME nhưng không có provider message ID, có chứng minh email delivered không?

Không. Raw không thay submission/delivery feedback.

**Câu 6.** Bcc recipient có chắc nằm trong raw MIME headers không?

Không. SMTP envelope và MIME headers khác nhau; Bcc thường không được giữ như To.

**Câu 7.** Object upload thành công nhưng DB commit thất bại. Điều gì còn lại?

Có thể có orphan object; cần reconciliation/cleanup.

**Câu 8.** DB trỏ tới raw MIME, nhưng PUT object thất bại. Làm sao tránh worker đọc nhầm?

Không mark artifact READY cho tới khi object tồn tại và được xác nhận; có trạng thái staging/error.

**Câu 9.** Một SHA-256 digest xác minh điều gì?

Nó giúp kiểm tra bytes hiện có giống bytes được hash, không tự chứng minh origin/authenticity.

**Câu 10.** Lưu raw MIME của OTP nhiều năm để debug có hợp lý không?

Thường không phù hợp với nguyên tắc tối thiểu hóa dữ liệu; cần chính sách TTL và tránh giữ token plaintext.

**Câu 11.** Full-text search trên email body có liên quan retention không?

Có. Nó tạo derived copy, phải bảo vệ/xóa theo policy.

**Câu 12.** Attachment object nằm trong local temp của web pod, outbox worker chạy pod khác. Có bền vững không?

Không. Cần storage accessible, versioned và giữ qua retry window.

**Câu 13.** Có nên store raw MIME cho mọi email marketing chỉ vì có thể không tốn nhiều trong tuần đầu?

Cần tính volume, long-term retention, privacy và nhu cầu thực; không tự động.

**Câu 14.** Mailbox inbound chỉ cần tạo ticket và không có yêu cầu xem lại body. Metadata-only có được không?

Có thể, nhưng phải chắc business input đã được persist ở nguồn khác trước khi mailbox bị ack/xóa, và việc thiếu raw được chấp nhận.

**Câu 15.** Muốn cho support xem email, có thể render nguyên HTML từ `MimeMessage` không?

Không nên. HTML inbound là untrusted; cần sanitize, hạn chế remote content và kiểm tra quyền.

**Câu 16.** Template thay đổi giữa hai lần retry. Có thể gửi nội dung khác không?

Có nếu chỉ resolve latest template. Dùng versioned template/snapshot khi cần content consistency.

**Câu 17.** Một tenant yêu cầu xóa email; raw object đã xóa nhưng attachment thumbnail vẫn còn. Đã hoàn tất chưa?

Chưa, cần xử lý derived copies/indexes/backups theo policy.

**Câu 18.** Lưu full MIME có ngăn SMTP duplicate khi worker crash sau acceptance không?

Không. Durable content và exactly-once submission là hai vấn đề khác nhau.

## 44. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Email inbound / outbound"] --> B["Mục đích + data classification"]
    B --> C{"Cần giữ nội dung?"}
    C -->|"Không"| D["Metadata + attempts"]
    C -->|"Có"| E{"Cần raw MIME nguyên dạng?"}
    E -->|"Không"| F["Versioned content snapshot"]
    E -->|"Có"| G["Raw MIME capture"]
    F --> H["Encrypted object storage"]
    G --> H
    H --> I["Artifact checksum + version + READY"]
    D --> J["Retention + authorization"]
    I --> J
    J --> K["Search / replay / audit có kiểm soát"]
    K --> L["Cleanup + reconcile"]
~~~

Các nguyên tắc quan trọng:

1. **Metadata-only, snapshot, raw MIME và hybrid là những mô hình khác nhau**; phải xác định mục tiêu trước khi chọn.
2. **Raw MIME không bao gồm toàn bộ envelope, attempts và delivery feedback**; vẫn cần metadata có cấu trúc.
3. **Outbound thường có nguồn dựng message**, nhưng nếu template/domain data thay đổi, metadata-only có thể không replay được nội dung cũ.
4. **Inbound phụ thuộc nguồn ngoài**, nên cần capture dữ liệu quan trọng trước khi mailbox xóa/đóng session.
5. **`MimeMessage.writeTo` là serialization tại một điểm**, không tự chứng minh original wire bytes.
6. **Attachment và inline assets cần lifecycle riêng**, không chỉ lưu HTML/body text rồi coi như full content.
7. **Object storage giúp lưu content lớn nhưng không có DB ACID chung**, cần staging, READY state và orphan cleanup.
8. **Checksum/version giúp kiểm tra integrity**, không thay chữ ký hoặc chứng minh delivery.
9. **Raw MIME chứa dữ liệu nhạy cảm**, nên cần encryption, least privilege, audit, malware scanning và TTL.
10. **Metadata cũng có PII**, cần data minimization và quyền truy cập phù hợp.
11. **Retention phải bao phủ copies, indexes, caches và backups**, không chỉ xóa một DB row.
12. **Outbox lưu durable intent**, không bắt buộc lưu raw MIME và không tự bảo đảm exactly-once SMTP.
13. **Send-time policy phải được kiểm tra lại khi retry/replay**, nhất là consent, token expiry và tenant status.
14. **Hệ thống nhiều tenant cần cách ly storage/search/authz**, không dựa vào object key như quyền truy cập.
15. **Kiểm thử theo contract**: readback, checksum, DB/object consistency, recovery, retention và cross-tenant access.
16. **Chính sách theo purpose quan trọng hơn một flag toàn cục**, đặc biệt với OTP, payment receipt và inbound documents.

Trong Spring Framework Mail, lựa chọn giữa lưu toàn bộ message và chỉ lưu metadata là **quyết định về khả năng phục hồi nội dung, mức dữ liệu cần chịu trách nhiệm bảo vệ và cam kết kiểm toán**. Nếu chỉ cần theo dõi job, retry và delivery status, metadata có cấu trúc thường là đủ. Nếu cần dựng lại nội dung tại thời điểm sự kiện, nên lưu versioned snapshot và attachment bất biến. Nếu phải điều tra header/MIME hoặc reparse thư inbound, raw MIME có thể cần thiết nhưng phải có capture point, encryption, retention và quyền truy cập rõ ràng. Thiết kế bền vững nhất là giữ **đúng dữ liệu cần thiết, ở đúng nơi, trong đúng khoảng thời gian**, và xác định rõ những gì hệ thống có thể hoặc không thể khôi phục sau sự cố.




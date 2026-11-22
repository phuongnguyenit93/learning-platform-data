# Log toàn bộ message và dữ liệu người nhận trong Spring Framework Mail

Trong Spring Framework Mail, lỗi vận hành rất phổ biến là **log nguyên văn toàn bộ email và danh sách người nhận** nhằm “debug cho nhanh”. Một đoạn như `log.info("sending mail: {}", message)` hoặc lệnh `mimeMessage.writeTo(System.out)` có thể vô tình đưa tên, địa chỉ, subject, HTML body, token xác thực, hóa đơn, attachment và các MIME headers vào hệ thống log. Nguy hiểm hơn, log có thể được sao chép sang nhiều nơi: console của container, agent thu thập logs, APM, lưu trữ tập trung, dịch vụ hỗ trợ, dashboard, hệ thống cảnh báo và bản export gửi cho bên thứ ba.

Đây không chỉ là vấn đề log quá dài. **Email là dữ liệu nghiệp vụ và thường chứa dữ liệu cá nhân hoặc bí mật; log là một môi trường lưu trữ và phân phối riêng với quyền truy cập, thời hạn lưu, backup và mức bảo vệ có thể khác hẳn database gốc.** Khi dữ liệu bị đưa vào log, việc thu hồi thường khó hơn nhiều so với xóa một bản ghi trong ứng dụng.

Bài học phân tích nguyên nhân, đường rò rỉ và cách thiết kế **structured, minimal, privacy-aware logging** khi sử dụng `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper`, Jakarta Mail, Spring Boot, Spring Integration và các worker/outbox. Đồng thời cung cấp ví dụ mã Java, trường hợp lỗi SMTP, logging khi async/retry, trace/MDC, cách kiểm thử và runbook xử lý sự cố.

## 1. Anti-pattern cần nhận diện

Ví dụ gửi thư:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("security@example.test");
mail.setTo("customer@example.test");
mail.setSubject("Mã đăng nhập");
mail.setText("Mã của bạn là 482917");

log.info("Sending email: {}", mail);

mailSender.send(mail);
```

`SimpleMailMessage` có thể chứa trực tiếp các trường email. Không được coi `toString()` của message là một serialization an toàn dành cho log.

Một ví dụ nguy hiểm rõ hơn với MIME:

```java
MimeMessage mime = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setTo("customer@example.test");
helper.setSubject("Bản sao hóa đơn");
helper.setText(
    "Hóa đơn của bạn",
    "<p>Thông tin thanh toán của khách hàng</p>"
);

// Tránh: ghi toàn bộ MIME, cả headers và các parts.
mime.writeTo(System.out);

mailSender.send(mime);
```

`MimeMessage.writeTo(...)` tạo dữ liệu MIME dùng cho truyền thư, **không phải một bản log đã được ẩn thông tin**. Nó có thể đưa payload, attachments mã hóa, inline resources và headers ra output stream.

Những thao tác không nên xuất hiện trong logging thông thường:

- `log.info("{}", mailMessage)` hoặc stringify DTO chứa body.
- `log.debug("mime={}", mimeMessage)` khi không kiểm soát implementation `toString`.
- `mimeMessage.writeTo(System.out)` hoặc ghi vào file log.
- Log `getContent()`, `getSubject()`, `getAllRecipients()`, `getFrom()` nguyên văn.
- Log `getFailedMessages()` mà không giới hạn keys/values.
- Log raw request JSON có HTML, recipient arrays và attachment URLs.
- Bật Jakarta Mail session debug trên toàn hệ thống rồi quên tắt.

**Mặc định an toàn:** log kết quả và định danh nội bộ cần thiết để điều tra, không log nội dung email.

## 2. Những lớp dữ liệu có thể bị lộ

| Thành phần | Ví dụ | Rủi ro |
| --- | --- | --- |
| To/Cc/Bcc | Địa chỉ người nhận | PII, tiết lộ nhóm nhận, đối tác |
| From/Reply-To | Danh tính hoặc mailbox nội bộ | Sơ đồ tổ chức, thông tin liên lạc |
| Subject | “Kết quả xét nghiệm”, “Đơn hàng #...” | Có thể chứa dữ liệu nhạy cảm |
| Plain text | Nội dung thông báo | PII, secret, số tiền, mã |
| HTML | Template + dữ liệu khách hàng | Nội dung nhạy cảm và tracking URLs |
| OTP/reset link | Mã, token, magic link | Nguy cơ chiếm tài khoản |
| Attachments | PDF, CSV, ảnh | Hồ sơ, hóa đơn, hợp đồng |
| Inline resources | CID images | Dữ liệu không cần thiết và dung lượng lớn |
| MIME headers | Message-ID, custom headers | Correlation ID, routing, metadata cá nhân |
| SMTP envelope | MAIL FROM/RCPT TO | Có thể chứa toàn bộ recipients kể cả Bcc |
| Exception messages | Address bị từ chối, SMTP reply | PII, thông tin server/provider |
| Trace baggage/MDC | Email, tenant, request ID | Tự động lan truyền tới nhiều logs |
| Provider response | Queue ID, rejection text | Có thể chứa recipient hoặc message metadata |

Không nên phân loại “subject là vô hại”. Chủ đề email có thể tự nó tiết lộ sự kiện nghiệp vụ riêng tư: giao dịch thất bại, yêu cầu hỗ trợ pháp lý, tình trạng sức khỏe hoặc thông tin nhân sự.

Một email “không có attachment” vẫn có thể chứa credentials, authentication token và địa chỉ liên lạc.

## 3. Tại sao log có phạm vi rủi ro khác database?

Dữ liệu gốc thường có schema, phân quyền theo user, encryption và retention gắn với quy trình nghiệp vụ. Log có thể đi qua:

```text
Spring application
      |
      +--> stdout/container logs
      |
      +--> log shipper / agent
      |
      +--> central log platform
      |
      +--> APM / trace store
      |
      +--> alerts / chat integrations
      |
      +--> support export / incident attachment
      |
      +--> backup / archive
```

Ngay cả khi truy cập log được kiểm soát, số hệ thống và nhân sự có quyền xem log có thể rộng hơn quyền truy cập email gốc. Payload đã nằm trong logs còn bị nhân bản thành dashboards, screenshots, tickets hoặc bản download.

**Không dùng log như kho lưu email.** Nếu nghiệp vụ cần giữ bản sao email đã gửi, xây một storage/audit artifact có retention, encryption và access control phù hợp; không dump MIME sang log.

## 4. Mục tiêu logging thực sự là gì?

Khi email bị lỗi, operator thường muốn biết:

1. Thông báo nghiệp vụ nào bị ảnh hưởng?
2. Đã tạo job chưa?
3. Đang ở giai đoạn prepare, queue hay SMTP?
4. Đã thử gửi bao nhiêu lần?
5. Provider/account nào xử lý?
6. Lỗi tạm thời hay vĩnh viễn?
7. Có thể retry không, và khi nào?
8. SMTP relay đã accepted message chưa?
9. Có provider delivery/bounce event không?
10. Có liên quan tới một tenant/category cụ thể không?

Phần lớn câu hỏi này **không cần raw email body hoặc địa chỉ đầy đủ**. Chúng cần notification ID, attempt ID, status transitions, failure class, latency và provider correlation.

Thay vì log “đã gửi email gì cho ai”, log “notification nào, attempt nào, giai đoạn nào, outcome gì”.

## 5. Phân biệt ba loại định danh

| ID | Ý nghĩa | Có nên log? |
| --- | --- | --- |
| `notificationId` | Một email logic đã được yêu cầu | Thường có, dưới dạng opaque ID nội bộ |
| `attemptId` | Một lần thử SMTP cụ thể | Thường có |
| `businessEventId` | Sự kiện phát sinh email | Theo policy, tránh nội dung nhạy cảm |
| MIME `Message-ID` | Header của email | Theo yêu cầu correlation và privacy |
| Provider queue/message ID | Identifier do provider cung cấp | Có kiểm soát, chỉ nếu provider trả |
| Trace ID/span ID | Theo dõi thực thi | Có, không gắn PII làm span name |
| Recipient correlation token | HMAC/pseudonym hóa địa chỉ | Chỉ khi thật cần, có quản trị key |

`notificationId` và `attemptId` là hai định danh quan trọng để nối lịch sử retry mà không cần log recipient address.

MIME `Message-ID` không bảo đảm exactly-once; provider ID cũng không phải bằng chứng email đã delivered nếu event chưa xác nhận.

## 6. Một hợp đồng structured logging tối thiểu

Mỗi sự kiện log có thể dùng schema:

```json
{
  "event": "mail.smtp.submit.completed",
  "notificationId": "N-1001",
  "attemptId": "A3",
  "mailCategory": "TRANSACTIONAL",
  "provider": "smtp-primary",
  "stage": "SMTP_SUBMISSION",
  "outcome": "SUBMITTED",
  "durationMs": 742,
  "timestamp": "2026-11-12T11:20:00Z"
}
```

Không có:

- Raw recipient address.
- Full subject.
- Body HTML/plain.
- Attachment bytes hoặc filesystem path.
- OTP/magic link.
- SMTP password.
- Access/refresh token.

Một event lỗi:

```json
{
  "event": "mail.smtp.submit.failed",
  "notificationId": "N-1001",
  "attemptId": "A4",
  "mailCategory": "TRANSACTIONAL",
  "provider": "smtp-primary",
  "failureClass": "SMTP_TEMPORARY",
  "smtpReplyCode": "451",
  "outcome": "RETRY_WAIT",
  "nextAttemptAt": "2026-11-12T11:25:00Z"
}
```

`failureClass` và reply code được chuẩn hóa; không log trực tiếp toàn bộ lời nhắn của remote SMTP server vì nó có thể chứa recipient hoặc thông tin tùy ý.

## 7. Xây whitelist thay vì blacklist

Hai cách tiếp cận:

**Blacklist:**

```text
Serialize mọi field của MailJob
    |
    +--> loại password, token, recipient?
    |
    v
Log phần còn lại
```

Cách này dễ hỏng khi DTO được thêm field mới như `resetUrl`, `secretAttachmentKey` hoặc `bccAddresses` mà blacklist chưa biết.

**Whitelist:**

```text
Chọn event name
   |
   +--> notificationId
   +--> attemptId
   +--> category (low cardinality)
   +--> provider alias
   +--> status/outcome
   +--> duration/error class
   |
   v
Structured logger
```

Chỉ các field được phê duyệt mới vào log, bất kể DTO mở rộng thế nào.

**Không dùng reflection để log toàn bộ object** rồi hy vọng masking layer bắt hết mọi nhạy cảm.

## 8. Java code: log an toàn quanh JavaMailSender

Một service minh họa dùng Spring Mail:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import java.time.Duration;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

@Service
public class SafeMailSubmissionService {

    private static final Logger log =
        LoggerFactory.getLogger(SafeMailSubmissionService.class);

    private final JavaMailSender sender;
    private final Clock clock;
    private final MailFailureClassifier failures;

    public SafeMailSubmissionService(
            JavaMailSender sender,
            Clock clock,
            MailFailureClassifier failures) {
        this.sender = sender;
        this.clock = clock;
        this.failures = failures;
    }

    public void submit(PreparedMail prepared, UUID attemptId) {
        Instant started = clock.instant();

        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(prepared.senderAddress());
            helper.setTo(prepared.recipientAddress());
            helper.setSubject(prepared.subject());
            helper.setText(
                prepared.plainText(),
                prepared.htmlText()
            );

            sender.send(message);

            log.info(
                "event=mail.smtp.submitted notificationId={} attemptId={} "
                    + "category={} durationMs={}",
                prepared.notificationId(),
                attemptId,
                prepared.category(),
                Duration.between(
                    started, clock.instant()
                ).toMillis()
            );
        } catch (MessagingException | MailException exception) {
            MailFailureCategory failure =
                failures.classify(exception);

            log.warn(
                "event=mail.smtp.failed notificationId={} attemptId={} "
                    + "category={} failureClass={}",
                prepared.notificationId(),
                attemptId,
                prepared.category(),
                failure.name()
            );

            throw new MailSubmissionFailure(
                prepared.notificationId(),
                attemptId,
                failure,
                exception
            );
        }
    }
}
```

`PreparedMail`, `MailFailureClassifier`, `MailFailureCategory` và `MailSubmissionFailure` là các types do ứng dụng tự thiết kế. Ví dụ chỉ minh họa cách chọn log fields. Repository/outbox phải ghi trạng thái và retry policy riêng.

**Điểm quan trọng:** `exception` được dùng để classify, nhưng **không truyền `exception` làm argument cuối của `log.warn(...)`** hoặc gọi `exception.getMessage()` để log raw SMTP text. Những dữ liệu đó cần xử lý theo chính sách log riêng.

Trong production, nếu cần stack trace phục vụ debugging, nên tạo cơ chế diagnostics hạn chế quyền và đã đánh giá khả năng dữ liệu nhạy cảm trong exception/cause chain; không mặc định mọi stack trace đều an toàn.

## 9. Vì sao exception stack trace cũng có thể lộ PII?

Các exception liên quan tới mail có thể chứa:

- Recipient address bị SMTP từ chối.
- `InternetAddress` hiển thị trong message.
- Subject hoặc context trong exception do ứng dụng tự tạo.
- SMTP server response có địa chỉ người nhận.
- Nested provider-specific exception.
- Map failed messages có key là mail objects.

Ví dụ không nên:

```java
try {
    sender.send(message);
} catch (MailException exception) {
    log.error(
        "SMTP failed for recipient={} message={}",
        recipient,
        message,
        exception
    );
}
```

Nó có thể log recipient, message và cả nested exception.

Ví dụ tốt hơn:

```java
try {
    sender.send(message);
} catch (MailException exception) {
    MailFailureCategory category =
        classifier.classify(exception);

    log.warn(
        "event=mail.smtp.failed notificationId={} "
            + "attemptId={} category={}",
        notificationId,
        attemptId,
        category.name()
    );

    throw exception;
}
```

Nên có xử lý lỗi ở worker/outbox để cập nhật `RETRY_WAIT`, `FAILED` hoặc `AMBIGUOUS`. Không nuốt exception để API vô tình báo thành công.

## 10. JavaMailSender và MimeMessage là dữ liệu, không phải đối tượng log

`JavaMailSender` gửi một `MimeMessage`; `MimeMessageHelper` giúp đặt recipient, subject, HTML và attachment. Những đối tượng này có thể tham chiếu tới:

- Body content.
- MIME headers.
- Attachment resources.
- File paths.
- InputStreamSource/JavaMail DataSource.
- Thông tin template và sender.

Dù implementation `toString()` tại một phiên bản chỉ in class name, **không nên dựa vào hành vi tình cờ của `toString()`** làm biện pháp bảo vệ. Một wrapper, record, custom serializer, logging encoder hoặc developer sau này có thể thay đổi lượng thông tin được in.

Tránh `log.debug("prepared={}", preparedMail)` khi `PreparedMail` là Java record chứa raw body và recipient: `record.toString()` thường bao gồm field values.

Chỉ log opaque ID và phân loại được whitelist.

## 11. Không dùng writeTo làm logging

`MimeMessage.writeTo(OutputStream)` có thể serialize MIME để gửi hoặc lưu bản sao, gồm:

```text
From: ...
To: ...
Subject: ...
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=...

--boundary
Content-Type: text/html; charset=UTF-8

... raw HTML body ...

--boundary
Content-Type: application/pdf
Content-Transfer-Encoding: base64

... base64 attachment bytes ...
```

Base64 **không phải mã hóa bảo mật**. Ai có quyền truy cập log có thể decode attachment.

Một đoạn như:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
mimeMessage.writeTo(out);
log.debug("mail.raw={}", out.toString(StandardCharsets.UTF_8));
```

vừa đưa dữ liệu nhạy cảm vào log, vừa có thể tạo bản copy MIME rất lớn trong heap. Không dùng nó cho logging; nếu cần kiểm thử MIME, hãy dùng SMTP capture server trong test, không ghi full payload vào CI logs.

## 12. Spring Boot/Jakarta Mail debug: nguy cơ khác với application logs

Ngoài `log.info` của ứng dụng còn có protocol debug từ Jakarta Mail/Angus Mail hoặc mail provider. Các lựa chọn nguy hiểm trong production:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
```

Hoặc:

```java
Session session = ...;
session.setDebug(true);
```

Các ví dụ trên bật dạng debug của Jakarta Mail Session khi được áp vào session/transport phù hợp. Provider/phiên bản quyết định chi tiết thông tin xuất ra, nhưng có thể bao gồm transcript SMTP, server replies, envelope recipients, headers và/hoặc MIME payload. Không coi cơ chế debug là đã được redaction an toàn.

Trong một số client/provider, debug AUTH có thể được che mặc định; điều đó **không phải lời bảo đảm** che toàn bộ mail addresses, body hoặc secret trên mọi phiên bản.

Không bật session debug toàn cục trong production chỉ để điều tra một notification.

## 13. Phân biệt log level DEBUG với Session debug

Các cơ chế khác nhau:

| Cơ chế | Dùng cho | Rủi ro |
| --- | --- | --- |
| SLF4J `log.debug(...)` | Application log statements | Lộ dữ liệu nếu fields không whitelist |
| Logback/Log4j2 logger levels | Bật/tắt từng package | Library có thể in protocol/headers |
| Jakarta Mail `Session.setDebug(true)` | Protocol/debug output của mail session | Có thể lộ transcript/payload |
| `mail.debug=true` | JavaMail debug property | Có thể xuất dữ liệu ngoài cấu trúc log |
| HTTP request/response logging | Web filters/interceptors | Lộ body chứa recipients/template fields |
| APM request capture | Observability agent | Sao chép payload/headers ra trace |
| Global exception logging | ControllerAdvice/filter/worker | Throwable message/cause có thể chứa PII |
| Raw MIME archival | Lưu bằng `writeTo` | Cần storage/access/retention riêng; không phải log |

Tắt `logging.level.*=DEBUG` chưa chắc đã tắt `Session.setDebug(true)` nếu session debug ghi ra một output stream khác.

Khi incident xảy ra, phải kiểm tra **tất cả nguồn log**, không chỉ logger của `MailService`.

## 14. Cấu hình mặc định: không bật mail protocol debug

Một cấu hình production điển hình:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
      "[mail.debug]": false

logging:
  level:
    root: INFO
    com.example.mail: INFO
```

Đây là ví dụ cấu hình minh họa. `com.example.mail` phải thay bằng package của dự án. Giữ timeouts để tránh jobs treo vô hạn; không dùng debug để che lỗi timeout.

`mail.debug=false` không tự bảo vệ khỏi logging dữ liệu do code application, APM hoặc framework filters. Các log statements vẫn phải tuân theo allowlist.

## 15. Một bảng phân loại dữ liệu trước khi log

| Field | Logging mặc định | Hướng xử lý |
| --- | --- | --- |
| Event name | Cho phép | Enum/string cố định |
| Notification ID | Thường cho phép | Opaque identifier, scoped access |
| Attempt ID | Cho phép | Opaque, low-sensitivity |
| Mail category | Cho phép | Enum low cardinality |
| Template key/version | Có điều kiện | Chỉ khi không tiết lộ loại hồ sơ nhạy cảm |
| Provider alias | Cho phép | Tên hạ tầng không chứa secret |
| Status/outcome | Cho phép | Enum |
| Duration/size bucket | Cho phép | Không chứa nội dung |
| SMTP reply code | Có điều kiện | Chỉ code đã parse/validate |
| Recipient count | Có điều kiện | Không phải địa chỉ |
| Recipient address | **Không mặc định** | Chỉ trong secure record nếu thật cần |
| Recipient display name | Không | PII |
| Subject | Không | Có thể nhạy cảm |
| Plain/HTML body | Không | Nội dung/secret |
| OTP/reset URL | **Không** | Secret |
| Attachment filename/path | Không mặc định | Có thể chứa PII và đường dẫn nội bộ |
| Attachment content | **Không** | File nhạy cảm |
| Raw MIME headers | Không | Chứa recipient/correlation/PII |
| Raw SMTP response | Không mặc định | Parse class/code an toàn |
| SMTP password/OAuth token | **Không bao giờ** | Secret |
| Throwable `getMessage()` | Không mặc định | Có thể chứa recipient |

Tính “được log” là quyết định có scope: một debug environment dùng dữ liệu tổng hợp khác với production logs chứa user data.

## 16. Pseudonymization: khác masking và anonymization

Một nhu cầu điều tra có thể là: “Tất cả attempts tới cùng recipient có bị lỗi không?” Có ba lựa chọn:

1. Tra cứu bằng `notificationId` và join trong database có quyền truy cập.
2. Ghi một **opaque recipient ID** đã tồn tại trong application model.
3. Nếu thực sự cần correlation mà không có ID, dùng **HMAC có key bí mật** trên địa chỉ đã normalize theo policy.

Không nên:

```text
recipientHash = SHA256(emailAddress)
```

Email addresses thường có không gian tìm kiếm đoán được. Hash không có secret có thể bị dictionary attack dễ hơn dự kiến. HMAC với key được bảo vệ làm giảm rủi ro này, nhưng **không biến thông tin thành hoàn toàn vô danh**.

### Masking cũng chưa đủ

Ví dụ:

```text
n***@example.test
```

vẫn có thể tiết lộ domain, độ dài và pattern; nếu mailbox hiếm thì vẫn nhận dạng được. Masking có thể hữu ích cho UI có quyền nhưng không nên mặc định mọi masked value an toàn cho logs phổ rộng.

## 17. HMAC recipient token ở mức thiết kế

Một interface có thể định nghĩa:

```java
public interface RecipientCorrelation {

    String tokenFor(String normalizedEmail);
}
```

Implementation an toàn cần:

- Canonicalization phù hợp domain/provider/ứng dụng.
- Secret key lấy từ secret manager; không hardcode.
- HMAC-SHA-256 hoặc thuật toán phù hợp.
- Key rotation/version.
- Scope có cân nhắc theo tenant/environment.
- Không log input raw trong error path.
- Retention ngắn và quyền truy cập hẹp.
- Không dùng token làm căn cứ authentication hoặc quyền truy cập.

Ví dụ event khi thật cần:

```json
{
  "event": "mail.provider.bounced",
  "notificationId": "N-1001",
  "recipientCorrelation": "v2:78e...opaque",
  "failureClass": "HARD_BOUNCE"
}
```

Chuỗi token trên chỉ là placeholder. Với nhiều hệ thống, **không cần log recipient token**: notification ID và store có access control đã đủ để điều tra.

## 18. MDC chỉ nên chứa metadata an toàn

MDC hỗ trợ đưa correlation context vào log:

```java
import org.slf4j.MDC;

public void processJob(MailJob job) {
    try (
        MDC.MDCCloseable id = MDC.putCloseable(
            "notificationId",
            job.notificationId().toString()
        )
    ) {
        process(job);
    }
}
```

MDC có thể được log encoder tự thêm vào **mọi dòng log** của thread. Do đó không đặt vào MDC:

- `recipientEmail`.
- `subject`.
- `otp`.
- Raw `tenantName` hoặc dữ liệu người dùng tự cung cấp.
- Authentication bearer token.
- Full request payload.

Nếu cần tenant correlation, dùng ID opaque đã được phân loại phù hợp với quyền truy cập log và tránh đưa tenant ID thành metric label có cardinality lớn.

### Thread pool và cleanup

Spring `@Async`/`ThreadPoolTaskExecutor` tái sử dụng threads. Nếu tự `MDC.put` mà không `remove`/`clear`, context của email A có thể bị gắn nhầm sang log email B. Dùng try/finally hoặc `MDCCloseable` để dọn đúng key sau mỗi job.

## 19. Tracing không phải nơi lưu recipient/body

Micrometer Observation/tracing có thể tạo spans như:

```text
mail.outbox.claim
      |
      v
mail.template.render
      |
      v
mail.mime.prepare
      |
      v
mail.smtp.submit
```

Attributes có thể cho phép:

```text
mail.category = TRANSACTIONAL
mail.provider = primary
mail.outcome = SUBMITTED
mail.failure_class = NONE
```

Tránh:

```text
span.name = "Send OTP to alice@example.test"
mail.recipient = alice@example.test
mail.subject = Password reset for ...
mail.body = ...
```

Span attributes, baggage và links có thể xuất tới APM SaaS khác hệ thống logs. Sampling không giải quyết an toàn nếu 1% traces vẫn chứa OTP hoặc raw recipient.

Không sử dụng raw customer address làm span name, metric tag hoặc trace baggage.

## 20. Structured logging: tránh CRLF/log injection

Dữ liệu từ email hoặc SMTP server có thể chứa ký tự điều khiển. Nếu nối trực tiếp thành log string:

```java
log.warn(
    "SMTP failure: " + smtpServerResponse
);
```

một phần nội dung không tin cậy có thể tạo log lines giả hoặc làm hỏng parser, tùy encoder.

Biện pháp:

- Không log raw remote text nếu chỉ cần status code/failure class.
- Dùng structured JSON encoder có escaping phù hợp.
- Whitelist và giới hạn độ dài field.
- Chuẩn hóa enum/status code từ trusted classifier.
- Không cho arbitrary header/subject làm `event` hoặc `message` name.
- Không tin `X-Request-ID` do client đưa vào mà chưa validate format/length.

**SLF4J parameterized logging là thói quen tốt cho format**, nhưng nó không tự redact PII. Việc loại bỏ sensitive fields phải xảy ra trước khi gọi logger.

## 21. Exception classifier thay raw SMTP text

Một classifier có thể trả enum:

```java
public enum MailFailureCategory {
    SMTP_TEMPORARY,
    SMTP_PERMANENT,
    SMTP_AUTHENTICATION,
    SMTP_TLS,
    SMTP_CONNECT_TIMEOUT,
    SMTP_READ_TIMEOUT,
    SMTP_WRITE_TIMEOUT,
    MIME_PREPARATION,
    STORAGE,
    UNKNOWN,
    AMBIGUOUS
}
```

Interface:

```java
public interface MailFailureClassifier {
    MailFailureCategory classify(Throwable throwable);
}
```

Classifier xét exception type, nested causes và thông tin protocol đáng tin, nhưng **log result enum**, không log nguyên cause chain vào hệ thống log phổ rộng.

SMTP status code ví dụ `421`, `451`, `550` có thể hữu ích nếu parse được chính xác. Không suy luận mọi SMTP 5xx đều chứa cùng một recipient reason hoặc mọi timeout đều chứng minh email chưa submit.

Nếu có thể timeout sau DATA, outcome có thể `AMBIGUOUS`, cần đối soát trước retry vì gửi lại có nguy cơ duplicate.

## 22. MailSendException có thể giữ failed messages

Trong Spring Mail, một số lỗi gửi có thể chứa ánh xạ những message không gửi được với exception tương ứng. Ví dụ xử lý `MailSendException#getFailedMessages()`.

Không làm:

```java
catch (MailSendException exception) {
    log.error(
        "All failed messages: {}",
        exception.getFailedMessages()
    );
}
```

Map có thể chứa đối tượng mail làm key và exception message làm value; stringify toàn bộ không phải một log summary đã ẩn thông tin.

Nếu cần đếm lỗi:

```java
catch (MailSendException exception) {
    int failedCount =
        exception.getFailedMessages().size();

    log.warn(
        "event=mail.smtp.batch_failed batchId={} "
            + "failedCount={}",
        batchId,
        failedCount
    );

    throw exception;
}
```

Đây là ví dụ chỉ log số lượng và batch opaque ID. Không lấy map key/value đưa trực tiếp vào event. Nếu cần retry từng message, phải thiết kế notification/attempt IDs ngay từ application, không dựa vào việc stringify đối tượng mail.

## 23. Batch failure và partial success

Gửi một batch nhiều messages có thể tạo trạng thái không đồng nhất:

```text
Batch:
  N-1 -> accepted
  N-2 -> temporary failure
  N-3 -> unknown / not attempted
```

Nếu log:

```text
batch failed: full message list = ...
```

vừa lộ recipients, vừa không mô tả được chính xác từng outcome. Tốt hơn lưu per-notification attempt state trong database và log:

```json
{
  "event": "mail.batch.completed",
  "batchId": "B-4002",
  "attemptedCount": 3,
  "submittedCount": 1,
  "temporaryFailureCount": 1,
  "unknownCount": 1
}
```

Một exception ở mức batch không tự chứng minh tất cả messages đều chưa gửi. Thông tin cần thiết để retry nên lấy từ outbox và provider evidence.

## 24. Không log tất cả recipients của một MIME message

Một email có nhiều recipients:

```text
To: customer@example.test
Cc: finance@example.test
Bcc: audit@example.test
```

Nếu log `message.getAllRecipients()`:

- Có thể lộ cả Bcc recipients.
- Tạo danh sách liên hệ nhạy cảm trong hệ thống logs.
- Không có thêm giá trị lớn nếu đã có notification ID và routing metadata.
- Dễ bị xuất ra dashboard hoặc alert channel.

Thay vì địa chỉ:

```java
log.info(
    "event=mail.message.prepared notificationId={} "
        + "recipientCount={} attachmentCount={}",
    notificationId,
    totalRecipientCount,
    attachmentCount
);
```

Ngay cả `recipientCount` và `attachmentCount` cần có lý do nghiệp vụ; với nhóm người nhận rất nhỏ hoặc đặc thù, counts cũng có thể tiết lộ metadata. Chỉ log nếu nó phục vụ vận hành.

## 25. Attachment metadata có thể chứa dữ liệu nhạy cảm

Filename ví dụ:

```text
invoice-customer-name-2026.pdf
medical-report-user-id.pdf
disciplinary-case-employee-name.pdf
```

Không log filename/raw storage key, vì chúng có thể chứa PII hoặc business identifiers. Với object storage, URL có chữ ký còn có thể là capability truy cập tệp trong thời hạn nhất định.

Nên log:

```text
attachmentCount = 2
totalAttachmentBytesBucket = "1MiB-5MiB"
artifactLoadDurationMs = 184
failureClass = STORAGE_TIMEOUT
```

Nếu cần điều tra một artifact cụ thể, dùng opaque `artifactId` đã được kiểm soát và tra cứu metadata trong storage có quyền riêng.

**Không log Base64 attachment bytes:** Base64 chỉ mã hóa biểu diễn, không bảo vệ bí mật.

## 26. HTML email có thể chứa nhiều dữ liệu hơn text nhìn thấy

HTML email thường chứa:

- Customer name.
- Order ID, item lines và số tiền.
- Link có token xác thực.
- Pixel/URL có recipient identifier.
- CSS/inline image URLs.
- QR code hoặc barcode.
- Hidden metadata, CID references.

Ghi `html` vào DEBUG log có thể tiết lộ các giá trị không xuất hiện khi operator chỉ nhìn preview.

Template variables không được xem là an toàn chỉ vì HTML được build ở server. Nếu cần kiểm tra template rendering, dùng dữ liệu tổng hợp trong test; production chỉ ghi template key/version đã được phân loại và rendering outcome.

## 27. HTTP request logging có thể lộ email trước cả bước gửi

Một endpoint:

```http
POST /api/notifications/email
Content-Type: application/json

{
  "to": ["customer@example.test"],
  "subject": "Kết quả giao dịch",
  "html": "<p>Thông tin nhạy cảm</p>"
}
```

Ngay cả nếu mail service không log gì, request logging filter có thể ghi toàn bộ body.

Kiểm tra:

- `CommonsRequestLoggingFilter` hoặc custom request logging.
- HTTP wiretap/client logging.
- Spring MVC interceptors/AOP request/response logging.
- API gateway access logs với body capture.
- Reverse proxy và service mesh debug settings.
- Error handler in raw request payload.
- APM instrumentation thu request bodies.

**Không bật body logging cho endpoint gửi email production**. Nếu cần request correlation, log request ID, actor ID đã xác thực, operation ID và outcome, không log JSON thô.

## 28. Spring Integration Message headers cũng có thể mang PII

Trong Spring Integration Mail:

```java
Message<String> outbound =
    MessageBuilder.withPayload(htmlBody)
        .setHeader(MailHeaders.TO, recipients)
        .setHeader(MailHeaders.SUBJECT, subject)
        .build();
```

Một handler/debugger log `Message<?>` nguyên vẹn có thể làm lộ:

- Payload HTML/text.
- `mail_to`, `mail_cc`, `mail_bcc`.
- `mail_from` và `mail_replyTo`.
- Subject.
- Header ứng dụng chứa customer metadata.

Không log toàn bộ Spring Integration `MessageHeaders`, cũng không đẩy raw message vào DLQ rồi mở logging toàn payload ở mọi bước. Có thể log `messageId` hoặc business `notificationId` và event classification.

Nếu cần DLQ để xử lý lại, lưu payload bền vững trong storage được phân quyền; quan sát DLQ qua IDs, không qua raw email trong log.

## 29. Log đúng từng giai đoạn pipeline

Một pipeline:

```text
Business transaction
      |
      v
Outbox intent
      |
      v
Preparation/render
      |
      v
MimeMessage build
      |
      v
SMTP submission
      |
      v
Provider events
```

Có thể log:

| Stage | Event mẫu | Fields phù hợp |
| --- | --- | --- |
| Outbox created | `mail.outbox.created` | notificationId, category |
| Worker claim | `mail.outbox.claimed` | notificationId, attemptId, workerId |
| Rendering | `mail.render.completed` | templateVersion, durationMs |
| MIME prepared | `mail.mime.prepared` | recipientCount, size bucket |
| SMTP submit | `mail.smtp.submitted` | provider, attemptId, durationMs |
| Temporary error | `mail.smtp.retry_scheduled` | failureClass, nextAttemptAt |
| Permanent error | `mail.smtp.failed` | failureClass |
| Ambiguous outcome | `mail.smtp.ambiguous` | attemptId, stage |
| Provider delivered | `mail.provider.delivered` | providerEventId/opaque notificationId |
| Provider bounced | `mail.provider.bounced` | normalized bounce class |
| Suppressed | `mail.notification.suppressed` | category, policy reason code |

Không cần subject/body/recipient cho hầu hết sự kiện trên.

## 30. Trace ID có thể thay đổi qua outbox

HTTP request và outbox worker có thể cách nhau nhiều phút hoặc chạy trên process khác. Không bắt buộc giữ một HTTP trace span mở tới lúc mail được giao.

Dùng:

```text
businessEventId
notificationId
attemptId
providerMessageId (nếu có)
```

để correlation bền vững. Trace/span IDs giúp xem từng execution, nhưng không thay thế notification/attempt ledger.

Không đưa `emailAddress` vào trace baggage để đi qua async boundaries. Baggage có thể bị forward qua network headers và lưu trong observability systems.

## 31. Thiết kế LogEvent DTO chỉ có trường cho phép

Một mẫu record:

```java
public record MailSendLogEvent(
    String event,
    UUID notificationId,
    UUID attemptId,
    String category,
    String provider,
    String outcome,
    String failureClass,
    long durationMs
) {}
```

Không chứa:

```java
// Không phải fields của MailSendLogEvent:
String recipientEmail;
String subject;
String plainText;
String htmlText;
byte[] attachment;
String smtpPassword;
```

Dùng một event class giới hạn fields giúp các team có contract chung, giảm nguy cơ người viết tính năng mới log tùy ý `PreparedMail`.

Dù `MailSendLogEvent` có `toString()` ít dữ liệu hơn, vẫn cần chính sách mapping và phân quyền đối với fields được phép. Với `category`, `provider`, `outcome`, ưu tiên enums hoặc values được whitelist.

## 32. Structured logging API không tự động an toàn

SLF4J parameterized logging:

```java
log.info(
    "event=mail.submitted notificationId={} attemptId={}",
    notificationId,
    attemptId
);
```

là một pattern tốt. Nhưng pattern này vẫn rò dữ liệu:

```java
log.info(
    "mail to={} subject={}",
    recipientAddress,
    subject
);
```

Dùng JSON encoder cũng chỉ giúp máy đọc/escape dữ liệu, **không tự phân loại hay redact PII**.

Bảo vệ phải dựa vào:

- Field allowlist.
- Code reviews và test logging.
- Static patterns/lint rules khi phù hợp.
- Centralized policy và access control.
- Retention và incident response.

## 33. Khi nào log recipient có thể được phép?

Có một số use case như điều tra abuse hoặc legal/compliance audit cần thông tin xác định recipient. Nhưng đó nên là **truy xuất có kiểm soát**, không phải INFO logs rộng rãi:

1. Có mục đích nghiệp vụ và quyền truy cập rõ.
2. Truy xuất từ database/secure audit record có ACL.
3. Ghi lại actor, lý do và thời điểm truy cập.
4. Giới hạn dữ liệu trả về.
5. Không copy dữ liệu sang channels không được bảo vệ.
6. Có retention/encryption phù hợp.
7. Có thủ tục xóa/redact theo yêu cầu hợp lệ.

Nếu một incident cần xem full MIME, lưu bản chụp chỉ trong secure diagnostic artifact store theo quy trình được phê duyệt, có TTL và audit access. Không bật raw logging trên toàn bộ producer.

## 34. Debugging an toàn với dữ liệu tổng hợp

Thay vì dùng email người dùng thật:

```text
To: test-recipient@example.test
Subject: SMTP fixture
Body: Synthetic test content
Attachment: fake-document.pdf
```

Kết hợp:

- GreenMail/Mailpit hoặc SMTP capture server.
- Template fixtures không có PII.
- Synthetic recipient addresses trong reserved test domains.
- Unit tests cho HTML/MIME parts.
- Integration tests kiểm tra attachment bytes và headers.
- Mock provider failures khi cần.

Trên môi trường test, raw MIME có thể được dùng làm test artifact nếu không chứa dữ liệu thật và quyền truy cập phù hợp; **tránh để artifacts thử nghiệm tự động bị upload ra hệ thống log công khai**.

Đây là cách kiểm tra chính xác MIME structure mà không cần bật debug production.

## 35. Một sự cố thường gặp: mail thiếu attachment

Operator muốn nhìn toàn bộ MIME vì khách báo không có PDF. Trước khi log raw MIME, hãy kiểm tra:

1. Prepared artifact ID tồn tại không?
2. Content size và checksum metadata có đúng?
3. Attachment count ở prepared manifest?
4. `MimeMessageHelper.addAttachment(...)` có được gọi không?
5. Resource có mở được stream mới mỗi lần?
6. Có read timeout hoặc storage error khi send?
7. SMTP capture test với fixture có tái hiện?
8. Provider có giới hạn kích thước hoặc attachment policy?
9. MIME tree có đúng multipart mode?
10. Có provider event hoặc recipient client stripping attachment không?

Ghi log an toàn:

```json
{
  "event": "mail.mime.prepared",
  "notificationId": "N-1001",
  "attachmentCount": 1,
  "attachmentBytesBucket": "1MiB-5MiB",
  "mimeBuildDurationMs": 83
}
```

Không cần log raw PDF bytes hoặc filename mang tên khách hàng.

## 36. Một sự cố khác: SMTP báo unknown recipient

SMTP server có thể trả text chứa email address. Ví dụ concept:

```text
550 5.1.1 <customer@example.test> unknown user
```

Không in nguyên reply text ra log chung:

```java
log.warn("SMTP response={}", serverReply);
```

Thay vào đó parse/normalize:

```text
smtpReplyCode = 550
enhancedStatus = 5.1.1
failureClass = PERMANENT_RECIPIENT
notificationId = N-1001
```

Mã enhanced status có thể vắng mặt hoặc provider-specific. Nếu parser không tin cậy dữ liệu, ghi `UNKNOWN` thay vì cố log raw text. Chi tiết recipient có thể tra từ notification store theo quyền khi cần điều tra.

## 37. Retry loops có thể nhân bản PII trong log

Nếu mỗi attempt đều log full message, một job retry 10 lần có thể tạo 10 bản chứa cùng subject/body/attachment references.

```text
Attempt A1 -> full MIME logged
Attempt A2 -> full MIME logged
Attempt A3 -> full MIME logged
...
Attempt A10 -> full MIME logged
```

Lỗi tạm thời ở provider có thể khiến log volume tăng nhanh khi hàng nghìn jobs cùng retry. Đây vừa là nguy cơ dữ liệu cá nhân, vừa là chi phí lưu trữ và sự cố vận hành.

Thay bằng log một sự kiện gọn theo attempt:

```json
{
  "event": "mail.retry.scheduled",
  "notificationId": "N-1001",
  "attemptId": "A3",
  "failureClass": "SMTP_TEMPORARY",
  "nextAttemptAt": "2026-11-12T11:30:00Z",
  "retryCount": 3
}
```

Không dùng `Thread.sleep` lâu trong sender worker chỉ để chờ retry; lưu `nextAttemptAt` trong outbox.

## 38. Sampling là kiểm soát lưu lượng, không phải ẩn danh

Một số hệ thống chỉ log 1% mail messages để giảm kích thước. Nhưng nếu 1% còn chứa raw OTP hoặc hợp đồng, vẫn có rủi ro nghiêm trọng.

Sampling không thay thế:

- Data minimization.
- Encryption/access control.
- Field allowlist.
- Retention.
- Authorized diagnostic workflow.

Áp dụng sampling sau khi log event đã được thiết kế an toàn, chủ yếu để giảm noise và chi phí telemetry. Với audit/critical state transitions, sampling có thể còn làm mất bằng chứng cần giữ; phân biệt audit store với operational logs.

## 39. Metrics không chứa recipient/subject

Micrometer metrics có thể:

```text
mail.smtp.submission.total{
  category="transactional",
  provider="primary",
  outcome="submitted"
}
```

Không nên:

```text
mail.smtp.submission.total{
  recipient="customer@example.test",
  subject="Payment for order ..."
}
```

Vì:

- PII vào monitoring backend.
- Cardinality rất cao.
- Chi phí và hiệu năng TSDB xấu đi.
- Nhạy cảm hơn cả logs có TTL ngắn.
- Metadata có thể tồn tại qua nhiều dashboard/export.

Nếu cần xem một notification cụ thể, tra cứu logs theo opaque ID hoặc dùng database query có quyền; metrics chỉ aggregate.

## 40. Log retention và quyền truy cập

Một logging policy thực dụng cần nêu:

- Ai được đọc log của production mail service?
- Có separation giữa developers, support và security personnel?
- Logs được mã hóa trong transit và at rest không?
- Retention bao lâu, có tier/archive nào?
- Log agent có gửi dữ liệu sang SaaS/region nào?
- Có quyền export/download/search rộng không?
- Ai quản lý retention và deletion?
- Có backup/snapshot copies không?
- Logs bị gắn vào incident tickets/chat messages bằng cách nào?
- Có định kỳ kiểm tra field schema/sensitive leakage không?

Mục tiêu là **giảm thời gian và phạm vi tồn tại của metadata**, không giữ mọi thứ “phòng khi cần”. Quy định pháp lý/phân loại dữ liệu phải theo chính sách và bối cảnh thực tế của tổ chức, không tự giả định một thời hạn chung.

## 41. Tránh trùng dữ liệu trong audit và log

Một hệ thống tốt có hai lớp:

**Operational logs**

```text
event, notificationId, attemptId, stage, outcome,
duration, failure class, provider
```

**Secure business/audit store**

```text
notification ID, recipient reference,
template/content version, reason, actor,
consent/eligibility decision, status transition
```

Chỉ audit store nên chứa dữ liệu định danh khi cần và được bảo vệ theo quyền. Operational logs dùng opaque IDs để join khi truy vấn được ủy quyền.

Không đẩy nguyên JSON audit record có chứa recipient vào INFO logs vì như vậy đã phá lớp phân quyền.

## 42. Đừng để lỗi logging làm hỏng gửi mail

Một anti-pattern khác là serialize MIME để log **trước khi gửi**:

```java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
mime.writeTo(bytes);
logger.info("{}", bytes.toString());
sender.send(mime);
```

Nếu file lớn, thao tác logging có thể:

- Làm tăng memory và GC.
- Đọc InputStreamSource quá sớm.
- Kéo dài thời gian gửi.
- Gây lỗi do attachment stream không repeatable.
- Tạo công việc I/O không cần thiết.
- Tiết lộ nội dung.

Logging nên rẻ, tối thiểu và không can thiệp đến MIME lifecycle. Nếu một hệ thống log/telemetry mất kết nối, email worker phải có policy rõ về có tiếp tục hay không; các audit bắt buộc có thể cần durable local transaction, không tùy tiện bỏ qua.

## 43. Sử dụng debug session chỉ trong quy trình được kiểm soát

Khi thực sự cần protocol-level diagnostics:

1. Xác định chính xác lỗi cần điều tra.
2. Ưu tiên cấu hình connection/read/write timeouts, exception classifier và provider logs.
3. Tái hiện trên test server với synthetic message.
4. Nếu vẫn cần debug production, xin approval theo quy định.
5. Chỉ bật trong phạm vi nhỏ nhất có thể, có TTL/owner/ticket.
6. Bảo đảm không chứa raw body, tokens hoặc credentials theo mức kiểm soát yêu cầu.
7. Tách output khỏi log platform phổ rộng và hạn chế access.
8. Tắt sau khi chẩn đoán, xác minh cấu hình đã rollback.
9. Kiểm tra mọi bản sao/export có thể đã phát sinh.
10. Lưu audit ai bật, khi nào và vì sao.

**Không bật `Session.setDebug(true)` bằng một feature flag không có giới hạn thời gian và quyền phê duyệt.** Đặc biệt tránh bật trên tất cả instances trong một đợt SMTP outage.

## 44. Khi đã lỡ log full mail: xử lý như một sự cố dữ liệu

Runbook ưu tiên:

1. **Ngừng phát sinh rò rỉ**: tắt code path/session debug/HTTP body logging.
2. **Xác định phạm vi**: khoảng thời gian, service/instance, log platform, dashboards, alerts và exports.
3. **Phân loại dữ liệu**: địa chỉ, nội dung, OTP/token, tài liệu, secrets, attachment bytes.
4. **Hạn chế truy cập**: tạm siết log readers và chia sẻ incident attachments.
5. **Bảo toàn bằng chứng cần thiết** theo quy trình security/incident trước khi thay đổi lưu trữ.
6. **Xử lý bản sao**: log shipper, archive, search index, backup, tickets, chat integrations.
7. **Thu hồi/rotate secrets** nếu credentials hoặc active authentication tokens bị lộ.
8. **Đánh giá nghĩa vụ thông báo/tuân thủ** theo chính sách và yêu cầu pháp lý áp dụng.
9. **Kiểm tra remediation**: chỉ log event whitelist, test không còn dữ liệu nhạy cảm.
10. **Postmortem**: nguyên nhân, thời gian phơi lộ, blast radius, guard rails.

Đừng chỉ xóa một file log cục bộ rồi kết luận dữ liệu đã biến mất: logs có thể đã được thu thập và nhân bản sang hệ thống khác. Việc xóa cũng phải theo quy trình xử lý chứng cứ và retention hợp lệ.

## 45. Testing: bảo đảm không có dữ liệu nhạy cảm trong log

Một test hữu ích là tạo một notification **hoàn toàn tổng hợp** chứa các marker đặc trưng:

```text
recipient = secret-recipient@example.test
subject   = UNIQUE-SUBJECT-XYZ
body      = SECRET-TOKEN-ABC123
attachment filename = PRIVATE-DOC-987.pdf
```

Chạy code path gửi hoặc lỗi SMTP rồi capture logs của service dưới test. Assert rằng log **không chứa** các markers đó, và vẫn chứa notification ID/outcome.

Ví dụ với Logback `ListAppender` (phụ thuộc implementation):

```java
@Test
void doesNotLogRecipientOrMessageBody() {
    String recipient = "secret-recipient@example.test";
    String token = "SECRET-TOKEN-ABC123";

    // Configure ListAppender against the logger under test.
    // Invoke safe mail submission with a mocked sender.
    // Collect formatted messages in a test-only buffer.

    String capturedLog = collectFormattedLogs();

    assertFalse(capturedLog.contains(recipient));
    assertFalse(capturedLog.contains(token));
    assertTrue(capturedLog.contains("mail.smtp."));
}
```

`collectFormattedLogs()` là helper thuộc test suite; ví dụ minh họa assertions, không phải một JUnit utility có sẵn.

Nên kiểm thử cả **success và failure paths**, đặc biệt nested exceptions, `MailSendException`, HTTP request logging, async MDC cleanup và provider response parsing.

## 46. Test SMTP message mà không làm bẩn operational logs

Dùng GreenMail/Mailpit hoặc test SMTP server:

```text
JUnit test
    |
    v
Prepare synthetic MimeMessage
    |
    v
JavaMailSender
    |
    v
GreenMail SMTP capture
    |
    v
Assert subject/body/attachment in test
```

Test có thể kiểm tra:

- `MimeMessage` có To/Subject đúng.
- HTML/plain alternative hợp lệ.
- Attachment filename/bytes hợp với fixture.
- Không có Bcc leak.
- SMTP attempt state đúng.
- Không log full message ở runtime.
- Provider-like failure được phân loại an toàn.

Test server lưu message trong test environment, **khác với việc log raw MIME ở production**. Không sử dụng mailbox/recipient thật hoặc bản sao user attachments trong CI.

## 47. Các test tình huống đặc biệt

Một bộ kiểm thử nên bao gồm:

1. Subject chứa tên khách hàng không có trong logs.
2. Body chứa reset token không xuất hiện trong logs.
3. `MailSendException` có nested recipient error nhưng log chỉ có failure class.
4. Bcc array không lọt vào log.
5. Filename chứa họ tên không được ghi.
6. SMTP server response có ký tự xuống dòng được normalize/truncate.
7. HTTP filter không log raw notification JSON.
8. Spring Integration message không bị log bằng `toString`.
9. MDC của email A không dính sang email B trên cùng thread.
10. APM span attributes không có recipient/subject/token.
11. Worker retry 5 lần không nhân bản MIME ở log.
12. Provider webhook không log toàn bộ raw payload nhạy cảm.
13. Unit tests và integration tests dùng test domain/secret giả.
14. Logging pipeline failure không làm worker silently succeed.
15. Khi session debug bị bật ngoài ý muốn, detection/guardrail cảnh báo.

Cần dùng fixtures tổng hợp để test tránh tạo rò rỉ ngay trong pipeline CI.

## 48. Static checks và code review

Code review có thể tìm các pattern rủi ro:

```text
log.info("{}", mail)
log.debug("{}", preparedMail)
log.error("SMTP error", exception)
mimeMessage.writeTo(System.out)
session.setDebug(true)
mail.debug=true
log.info("to={} subject={}", ...)
requestLoggingFilter.includePayload=true
```

Không phải mọi occurrence đều chắc chắn sai trong mọi context, nhưng chúng nên được review theo threat model và log access.

Một quy tắc phát triển hiệu quả:

> Trước khi thêm một field vào log, hãy giải thích câu hỏi vận hành nào cần field đó và vì sao một opaque identifier không đủ.

Có thể xây lint/static pattern checks, logging schema review hoặc automated tests; nhưng việc review cần hiểu ngữ cảnh, không chỉ search/replace mã nguồn.

## 49. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Thay thế |
| --- | --- | --- |
| Log `SimpleMailMessage` nguyên object | Có thể lộ recipient/body | Log notification ID/outcome |
| Dump `MimeMessage.writeTo` vào console | Lộ MIME/attachment | Test SMTP capture với fixture |
| Bật `mail.debug=true` ở production | Transcript có thể lộ | Scoped diagnostics |
| Log `MailSendException#getFailedMessages()` | Có thể lộ failed message keys | Count/classification |
| Log exception message/cause thô | Remote replies chứa PII | Normalized error class/code |
| Log To/Cc/Bcc recipients | Lộ contact lists/Bcc | Opaque notification ID |
| Log subject vì “chỉ metadata” | Subject vẫn có PII | Template category/version có kiểm soát |
| Log HTML/attachments khi rendering fail | Lộ token/file contents | Render error class + artifact ID |
| Log raw request JSON | Rò trước SMTP | Request ID/status |
| Log Spring Integration Message headers | Lộ mail_to, mail_bcc, payload | Allowlisted event fields |
| Hash email bằng SHA-256 trần | Có thể bị dictionary attack | Opaque ID hoặc HMAC có secret nếu cần |
| Dùng mask địa chỉ như anonymization | Vẫn suy đoán được | Data minimization |
| Đưa email vào MDC/baggage | Lan truyền sang mọi telemetry | Opaque correlation IDs |
| Đưa recipient/subject vào metric label | PII, high cardinality | Enum tags |
| Sampling raw MIME 1% | Vẫn rò dữ liệu thật | Redaction trước sampling |
| Chỉ tắt DEBUG package | Session debug có thể vẫn bật | Kiểm tra từng cơ chế |
| Xóa local log sau sự cố | Bản sao vẫn tồn tại | Incident containment trên toàn pipeline |
| Giữ logs vô hạn “để điều tra” | Tăng blast radius | Retention và ACL |
| Unit test log bằng dữ liệu thật | Rò vào CI artifacts | Synthetic fixtures |

## 50. Lộ trình triển khai logging an toàn

1. **Lập danh mục mail data**: body, subject, recipients, headers, files, tokens.
2. **Xác định sự kiện vận hành** cần logs/metrics/traces thật sự.
3. **Thiết kế allowlist field schema** theo event/stage.
4. **Dùng notificationId và attemptId** làm correlation chính.
5. **Tách lỗi theo failure class**, không ghi raw exception text.
6. **Tắt protocol/session debug mặc định** trên production.
7. **Kiểm tra HTTP logging và APM instrumentation** để tránh request body capture.
8. **Không log Spring Integration Message hoặc MailMessage nguyên object**.
9. **Không log MIME hoặc attachment bytes**, kể cả Base64.
10. **Thiết kế secure audit/diagnostic store** khi thật sự cần dữ liệu xác định recipient.
11. **Áp quyền và retention** cho logs/telemetry/exports.
12. **Kiểm thử success, retries, failures và nested exceptions** bằng synthetic markers.
13. **Theo dõi thay đổi logging configuration** và cảnh báo bật debug bất thường.
14. **Định nghĩa incident runbook** cho trường hợp đã lỡ lộ dữ liệu.
15. **Đào tạo support/operator** tra notification ID qua công cụ có phân quyền thay vì yêu cầu copy raw email vào ticket.

## 51. Checklist trước khi deploy

- [ ] Không có `mimeMessage.writeTo` sang console/log.
- [ ] Không log full `SimpleMailMessage`/`MimeMessage`/`PreparedMail`.
- [ ] Không log full To/Cc/Bcc/Subject/HTML/plain text.
- [ ] Không log OTP/reset URLs/credentials/attachments.
- [ ] `mail.debug` và session debug mặc định tắt.
- [ ] Exception logging không in recipient trong SMTP replies.
- [ ] Log statements dùng allowlist fields.
- [ ] MDC được dọn sau task, không có PII.
- [ ] Trace attributes và metric labels không có email addresses.
- [ ] HTTP request logging không capture mail body.
- [ ] Spring Integration logging không serialize toàn bộ Message.
- [ ] Retry logs chỉ có attempt ID/outcome/next retry.
- [ ] Bcc không lộ trong log hoặc public MIME headers.
- [ ] Log access, retention, encryption và export được kiểm soát.
- [ ] Có test synthetic secret markers không xuất hiện trong logs.
- [ ] Có runbook thu hồi/debug/incident khi dữ liệu lỡ bị ghi.

## 52. Ghi nhớ

- Email message là **nội dung nghiệp vụ**, không phải log event an toàn.
- To/Cc/Bcc, Subject, HTML, plain text, headers, attachment và provider replies đều có thể chứa PII/secret.
- `MimeMessage.writeTo(...)` serialize MIME, không có redaction.
- `mail.debug`/`Session.setDebug(true)` có thể ghi protocol traffic ngoài SLF4J logger.
- `MailSendException` và nested exceptions cần được xử lý bằng sanitized error classification.
- `record.toString()` của DTO chứa email body là nguồn rò rỉ phổ biến.
- Log tối thiểu `notificationId`, `attemptId`, stage, category, provider, outcome và duration.
- Whitelist mạnh hơn blacklist vì DTO có thể thêm field nhạy cảm.
- Masking không tương đương anonymization; SHA-256 không có secret trên email có thể bị đoán.
- MDC, tracing, APM, metrics và HTTP body logging đều là đường xuất dữ liệu.
- Sampling không an toàn nếu nội dung được lấy mẫu vẫn chứa raw secrets.
- Logs cần retention, access control và quy trình export riêng.
- Dùng GreenMail/Mailpit và synthetic fixtures để phân tích MIME trong test.
- Khi đã lỡ log dữ liệu người nhận, xử lý theo incident runbook trên toàn log pipeline, không chỉ xóa local file.
- Correlation bằng opaque IDs vẫn cho phép điều tra failure, retries và delivery mà không cần lưu toàn bộ email.

**Nguyên tắc cốt lõi:** Trong Spring Framework Mail production, hãy **log vòng đời gửi mail, không log chính email**. Thiết kế structured events theo allowlist, nối sự kiện bằng notification/attempt IDs, phân loại lỗi thay vì in raw exception, giới hạn protocol debug và giữ dữ liệu người nhận trong nguồn lưu trữ có quyền phù hợp. Một hệ thống có thể quan sát tốt cả SMTP success, retry, bounce và outage mà không sao chép nội dung riêng tư của người nhận vào hàng triệu dòng log.

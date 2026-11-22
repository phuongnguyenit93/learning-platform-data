# Không ghi password hoặc nội dung nhạy cảm vào log khi dùng Spring Framework Mail

Khi một email gửi thất bại, phản ứng tự nhiên của lập trình viên là bật `DEBUG`, in toàn bộ exception, nội dung `MimeMessage` hoặc thông tin cấu hình SMTP để tìm nguyên nhân. Những thao tác này có thể giúp chẩn đoán nhanh trong môi trường thử nghiệm, nhưng cũng có nguy cơ đưa **mật khẩu SMTP, token đăng nhập, địa chỉ email, mã OTP, liên kết đặt lại mật khẩu, nội dung thư và tệp đính kèm** vào hệ thống log.

Log thường được tập trung về nhiều nơi: stdout của container, file trên máy chủ, log collector, hệ thống quan sát tập trung, kho lưu dài hạn, bảng điều khiển hỗ trợ và bản sao lưu. Một chuỗi bí mật vô tình được ghi có thể bị sao chép sang các hệ thống này, nằm ngoài phạm vi kiểm soát của ứng dụng ban đầu và tồn tại lâu hơn thời hạn sử dụng của nó.

**Nguyên tắc cốt lõi: chỉ ghi dữ liệu đủ để chẩn đoán trạng thái gửi, không ghi thông tin xác thực hoặc nội dung riêng tư.** Cần chủ động loại bỏ dữ liệu nhạy cảm ngay tại nơi tạo log; redaction ở bước thu thập chỉ là lớp phòng vệ bổ sung.

Trong ngữ cảnh Spring Framework Mail, bài này trình bày cách thiết kế log an toàn cho `JavaMailSender`, `MimeMessageHelper`, Jakarta Mail, SMTP transport, queue worker và retry. Mục tiêu là vẫn phân tích được lỗi mà không biến hệ thống log thành nơi lưu bản sao của email.

## 1. Những loại dữ liệu không nên có trong log

Một email chứa nhiều lớp dữ liệu. Không phải mọi trường đều có cùng mức nhạy cảm, nhưng nhiều trường dễ bị đánh giá thấp.

| Nhóm | Ví dụ | Rủi ro nếu xuất hiện trong log |
|---|---|---|
| **Thông tin xác thực SMTP** | Password, app password, OAuth access/refresh token, API key | Tài khoản gửi thư bị chiếm dụng, lạm dụng quota, gửi thư giả mạo |
| **Mã hoặc liên kết xác thực** | OTP, magic link, reset-password token, verification URL có token | Người đọc log có thể sử dụng mã hoặc chiếm luồng xác thực |
| **Nội dung thư** | `text/plain`, `text/html`, template variables | Lộ dữ liệu cá nhân, đơn hàng, hồ sơ, thông tin kinh doanh |
| **Headers** | `To`, `Cc`, `Bcc`, `Reply-To`, `Subject` | Lộ danh tính, mối liên hệ, chủ đề trao đổi, danh sách Bcc |
| **Attachment** | PDF hóa đơn, CSV, XLSX, ảnh inline, tên file | Lộ dữ liệu tài chính, khách hàng hoặc tài liệu nội bộ |
| **Đường dẫn/URL** | `file://...`, URL có signed token, đường dẫn storage | Lộ cấu trúc nội bộ hoặc khả năng truy cập tài nguyên |
| **Lỗi từ provider** | SMTP reply text, exception cause, diagnostic dump | Có thể chứa địa chỉ, tên miền, phần header hoặc dữ liệu do bên ngoài kiểm soát |
| **Định danh liên kết** | Message-ID, correlation ID, job ID | Có thể cho phép liên kết các bản ghi hoặc nhận diện đối tượng nếu thiết kế không cẩn thận |

Một số thông tin **có thể ghi có kiểm soát**: mã lỗi chuẩn hóa, loại tác vụ, thời gian gửi, số lần retry, tên provider ở mức danh mục, trạng thái `SUBMITTED`/`FAILED` và một ID nội bộ ngẫu nhiên dùng để tra cứu.

Không nên coi địa chỉ email là thông tin vô hại. Ví dụ, chỉ nhìn vào danh sách người nhận và subject cũng có thể suy ra mối quan hệ giữa người dùng, doanh nghiệp và một quy trình nhạy cảm. Ngay cả khi ứng dụng có nhu cầu hỗ trợ khách hàng, địa chỉ email không cần xuất hiện trong mọi log của mail worker.

## 2. Thiết kế log theo mô hình dữ liệu tối thiểu

Hãy đặt câu hỏi: *Khi có sự cố, người vận hành cần biết điều gì để hành động?*

Thông thường, một bản ghi chẩn đoán đủ dùng có thể gồm:

- ID công việc gửi email, dạng không mang PII.
- Loại email theo danh mục đã định nghĩa, ví dụ `ORDER_CONFIRMATION`.
- Giai đoạn xử lý: `QUEUED`, `PREPARING`, `SMTP_SUBMITTING`, `SUBMITTED` hoặc `FAILED`.
- Mã lỗi hoặc nhóm lỗi đã chuẩn hóa, ví dụ `SMTP_AUTH`, `SMTP_TIMEOUT`, `SMTP_REJECTED`.
- Số attempt và thời lượng xử lý.
- Thời điểm xử lý và tên instance/worker ở mức phù hợp.

Ví dụ một sự kiện log có cấu trúc:

```json
{
  "event": "mail_submission_failed",
  "mailJobId": "b6c821d5-7e8d-41ea-9a04-7e28e84def21",
  "mailType": "ORDER_CONFIRMATION",
  "attempt": 2,
  "stage": "SMTP_SUBMISSION",
  "failureClass": "SMTP_TIMEOUT",
  "retryable": true,
  "elapsedMs": 5032
}
```

Đoạn log này không cần password, recipient address, subject hoặc HTML body để nhận biết một vấn đề timeout. Khi tra cứu sâu hơn, người có quyền có thể dùng `mailJobId` để xem metadata trong hệ thống nghiệp vụ, theo quyền và quy trình riêng.

### Ví dụ log không nên viết

```java
// Sai: đưa secret vào log.
log.info("SMTP config: username={}, password={}", username, password);

// Sai: có thể lộ dữ liệu cá nhân và token.
log.debug("Sending mail to={}, subject={}, html={}",
        recipient, subject, htmlBody);

// Sai: metadata trong object có thể chứa mọi field khi toString().
log.info("Outgoing mail request: {}", mailRequest);

// Nguy hiểm nếu cause/provider text chứa dữ liệu nhạy cảm.
log.error("Mail failed for {}: {}", recipient, exception.getMessage());
```

### Ví dụ an toàn hơn

```java
log.info(
        "mail event={} jobId={} kind={} attempt={}",
        "submitted",
        job.id(),
        job.kind().name(),
        job.attempt());

log.warn(
        "mail event={} jobId={} failureClass={} retryable={}",
        "submission_failed",
        job.id(),
        failureClass.name(),
        retryable);
```

Điều kiện của ví dụ là `job.id()` là ID nội bộ không thể đảo ngược thành token/PII, còn `kind` và `failureClass` là các enum hữu hạn. Nếu job ID chứa email hoặc số tài khoản, bản thân nó cũng không an toàn để log.

## 3. Không ghi SMTP password, app password hoặc access token

Spring Boot có thể cấu hình SMTP với các thuộc tính `spring.mail.*`:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
```

Các placeholder trên là tên biến môi trường minh họa. Không ghi giá trị bí mật trực tiếp vào file cấu hình commit lên repository. Đối với môi trường production, nên dùng secret manager hoặc cơ chế quản lý secret của nền tảng.

**Đọc được secret không đồng nghĩa được phép ghi secret vào log.** Không nên log object `Environment`, toàn bộ `Properties` hoặc `JavaMailSenderImpl` chỉ để kiểm tra xem biến môi trường đã được inject chưa.

### Cách chẩn đoán thiếu cấu hình mà không lộ giá trị

Khi nghi ngờ cấu hình SMTP chưa có:

```java
boolean credentialConfigured =
        password != null && !password.isBlank();

log.info(
        "mail smtpCredentialConfigured={} hostConfigured={} tlsRequired={}",
        credentialConfigured,
        smtpHost != null && !smtpHost.isBlank(),
        startTlsRequired);
```

Thậm chí tên account đăng nhập SMTP cũng không nhất thiết cần log. Nếu vận hành cần phân biệt tài khoản gửi, dùng một alias cố định như `primary-outbound` hoặc `transactional` thay vì in username đầy đủ.

Một biến `passwordPresent=true` chỉ chứng minh chuỗi cấu hình có giá trị, **không chứng minh credentials hợp lệ**. Nếu server từ chối AUTH, ghi nhóm lỗi `SMTP_AUTHENTICATION_FAILED` và xác minh secret qua quy trình quản trị, không sao chép secret vào log.

### SMTP AUTH có thể truyền nhiều loại credential

Tùy provider, hệ thống có thể dùng:

- Username và app password.
- SMTP password dành riêng cho dịch vụ.
- OAuth 2.0 access token qua cơ chế SMTP AUTH tương ứng.
- SMTP relay dựa trên network policy và identity.
- API key nếu ứng dụng dùng một mail provider adapter thay vì SMTP.

Tất cả secret này đều phải được che chắn. Việc access token có hạn ngắn không khiến việc log token trở nên an toàn; log có thể được đọc ngay khi token còn hiệu lực.

## 4. Cẩn trọng khi bật Jakarta Mail debug

Jakarta Mail cung cấp khả năng debug để chẩn đoán phiên SMTP. Với nhiều triển khai, cấu hình `mail.debug=true` làm tăng lượng thông tin giao thức được xuất ra; `mail.debug.auth` điều khiển việc có hiển thị thông tin liên quan AUTH trong debug output hay không.

Đặc biệt:

- **Không bật `mail.debug.auth=true` trong production.**
- Không bật `mail.debug=true` chỉ vì một email bị lỗi mà chưa đánh giá dữ liệu có thể được ghi.
- Không giả định mọi dữ liệu debug đều đi qua SLF4J và redaction filter của ứng dụng; tùy phiên bản Jakarta Mail/Angus Mail, debug output có thể đi tới stream riêng.
- Không chụp raw protocol transcript rồi đính kèm vào ticket hỗ trợ khi chưa kiểm tra nội dung.

Ví dụ cấu hình production:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": false
      "[mail.debug.auth]": false
```

Trong thực tế, các cấu hình trên có thể nằm cùng các thuộc tính host/port/TLS. Khi chẩn đoán, cấu hình tăng mức debug nên có thời hạn sử dụng, phạm vi nhỏ và được phê duyệt theo chính sách vận hành.

### Vì sao chỉ tắt auth debug là chưa đủ?

`mail.debug.auth=false` là lớp bảo vệ quan trọng đối với credential khi có protocol debug, nhưng **không thay thế chính sách không log nội dung mail**. Các dòng giao thức và server reply vẫn có thể chứa địa chỉ người gửi/người nhận, tên server và thông tin metadata khác. Một số proxy/gateway hoặc lớp network tracing có thể tạo bản ghi riêng ngoài kiểm soát của cờ này.

Không nên đưa bất kỳ mật khẩu hoặc token thật nào vào quá trình “thử xem debug log đã che chưa” trên môi trường production.

### Khi thật sự cần protocol troubleshooting

Một quy trình thận trọng:

1. Tái hiện trên môi trường test bằng tài khoản thử có thể thu hồi, không dùng thư khách hàng.
2. Xác định câu hỏi cụ thể: DNS, kết nối TCP, TLS, SMTP AUTH, MAIL FROM, RCPT TO hay DATA.
3. Chỉ bật loại log cần thiết trong thời gian ngắn.
4. Xác nhận đầu ra không chứa secret, recipient hoặc message body trước khi chia sẻ.
5. Tắt debug và kiểm tra cấu hình đã quay về trạng thái an toàn.
6. Xóa bản ghi thử theo retention, thu hồi test credentials nếu chúng từng bị tiết lộ.

Trong production, ưu tiên đo SMTP return code nhóm, latency, lỗi kết nối và trạng thái retry mà không thu transcript đầy đủ.

## 5. Không ghi raw MimeMessage hoặc MIME body

`MimeMessage` có thể chứa:

- `text/plain` và `text/html`.
- Subject, From, To, Cc, Bcc.
- Content-ID của ảnh inline.
- PDF, CSV, XLSX và file đính kèm khác.
- MIME boundaries, headers, transfer encoding.

Nếu gọi `MimeMessage.writeTo(OutputStream)` rồi log kết quả, ứng dụng có thể tạo một bản sao hoàn chỉnh của email trong logs:

```java
// KHÔNG sử dụng cách này để debug production.
ByteArrayOutputStream buffer = new ByteArrayOutputStream();
message.writeTo(buffer);
log.debug("Raw outgoing message: {}",
        buffer.toString(StandardCharsets.UTF_8));
```

Ngay cả khi attachment được encode base64, nội dung vẫn có thể được giải mã và không hề được ẩn danh. **Base64 là encoding, không phải mã hóa bảo mật.**

### Không log HTML sau khi render template

Đối với template email:

```java
String html = templateRenderer.render("reset-password", variables);
```

`html` có thể chứa tên người dùng, đường dẫn chứa token, OTP, số tiền hoặc dữ liệu nhạy cảm khác. Nếu cần kiểm tra template:

```java
log.debug(
        "mail templateRendered={} version={} jobId={}",
        "PASSWORD_RESET",
        templateVersion,
        jobId);
```

Không ghi `variables` nếu chúng bao gồm thông tin cá nhân hoặc secret. Cũng không nên serialise toàn bộ DTO template thành JSON rồi để log collector tự “lọc” sau đó; dữ liệu đã đi qua các tầng không cần thiết.

### Attachment có thể nhạy cảm từ cả nội dung đến tên file

Không log:

```java
log.debug("Attachment bytes: {}", Arrays.toString(invoicePdf));
log.debug("Attachment location: {}", fileSystemPath);
log.debug("Full attachment: {}", Base64.getEncoder()
        .encodeToString(invoicePdf));
```

Nếu cần đo kích thước để chẩn đoán `message too large`:

```java
log.info(
        "mail attachmentCount={} totalAttachmentBytes={} jobId={}",
        attachmentCount,
        totalAttachmentBytes,
        jobId);
```

Ngay cả filename có thể chứa họ tên, mã khách hàng hoặc số hợp đồng. Tùy nhu cầu, log loại MIME theo danh mục đã kiểm soát (`application/pdf`) và kích thước thay vì tên file gốc.

## 6. Headers cũng là dữ liệu nhạy cảm

Nhiều nhóm chỉ che HTML body nhưng vẫn ghi toàn bộ headers:

```text
From: notifications@example.org
To: customer@example.net
Bcc: hidden-recipient@example.net
Subject: Xác nhận giao dịch riêng tư của khách hàng
Message-ID: <...>
```

Headers cho biết ai liên hệ với ai, loại giao dịch và đôi khi đường đi qua các mail server. Header `Bcc` đặc biệt nhạy cảm vì có thể tiết lộ người nhận ẩn.

**Không dùng `message.getAllHeaders()` hoặc `message.getRecipients(...)` làm dữ liệu log mặc định.** Nhiều exception SMTP liên quan địa chỉ không hợp lệ cũng có thể chứa recipient trong message text hoặc object nested.

### Phân biệt identifier dùng để tra cứu

Nên tạo `mailJobId` ở tầng ứng dụng:

```java
UUID mailJobId = UUID.randomUUID();
```

Trong log, chỉ sử dụng ID này để liên kết:

```text
mail jobId=... stage=QUEUED
mail jobId=... stage=SMTP_SUBMITTING
mail jobId=... stage=SUBMITTED
```

Không dùng nguyên văn recipient email, reset token hoặc tên người dùng làm ID. `Message-ID` của email có thể hữu ích cho hỗ trợ provider nhưng không cần xuất hiện trong mọi log và có thể được coi là dữ liệu cần kiểm soát truy cập.

## 7. Exception và stack trace có thể làm lộ dữ liệu

Một cách log phổ biến:

```java
log.error("Cannot send mail", ex);
```

Không có nghĩa nó luôn an toàn. Throwable có thể chứa:

- SMTP response trả lại địa chỉ recipient.
- Tên host/username của tài khoản gửi.
- Tên file attachment hoặc đường dẫn filesystem.
- Lỗi template kèm biến và nội dung bị render.
- Thông tin từ nested exception của provider.
- Các custom exception có `toString()` chứa payload.

Vì vậy, không nên xuất toàn bộ exception tree vào log có khả năng được truy cập rộng rãi. Với sự cố cần stack trace, cân nhắc luồng diagnostic riêng với dữ liệu được lọc, quyền truy cập giới hạn và thời hạn lưu ngắn.

### Đừng log nguyên chuỗi ex.getMessage()

Ví dụ:

```java
catch (MailException ex) {
    log.error("Mail error: {}", ex.getMessage()); // Có thể lộ metadata.
}
```

Không có bảo đảm rằng `getMessage()` không chứa dữ liệu nhận dạng. Thông báo lỗi của transport có thể được tạo từ phản hồi SMTP server; không nên coi nó là chuỗi tin cậy để log.

### Cẩn trọng với MailSendException.getFailedMessages()

`MailSendException` có thể cung cấp thông tin về các message gửi lỗi. Map này có thể có `MimeMessage` làm key và exception làm value. Không nên log nguyên map:

```java
// Không log vì key/value có thể tiết lộ nội dung và địa chỉ.
log.error("Failed messages: {}", ex.getFailedMessages());
```

Nếu cần thống kê, có thể lấy **số lượng** failed messages mà không in key/value:

```java
int failedCount = ex.getFailedMessages().size();
log.warn("mail failureCount={} jobId={}", failedCount, jobId);
```

Không phải mọi lỗi SMTP đều được biểu diễn bằng cùng cấu trúc exception. Hãy thiết kế một bộ phân loại lỗi dựa trên các trường đã được allowlist và không trả nguyên raw provider message vào logging layer.

## 8. Phân loại lỗi thành mã an toàn

Đối với dashboard, log và retry, ứng dụng nên chuyển exception thành một **error category có tập giá trị hữu hạn**.

Ví dụ:

```java
package com.example.mail;

public enum SafeMailFailure {
    AUTHENTICATION,
    CONNECTION,
    TIMEOUT,
    RECIPIENT_REJECTED,
    PROVIDER_THROTTLED,
    MESSAGE_TOO_LARGE,
    MIME_PREPARATION,
    UNKNOWN
}
```

Đây là danh mục do ứng dụng thiết kế, không phải enum có sẵn của Spring Mail. Khi exception không cung cấp đủ dữ liệu đáng tin cậy để phân loại, dùng `UNKNOWN` và giữ chẩn đoán chi tiết ở nơi được bảo vệ.

### Phân loại theo type thay vì message text

Ví dụ một bộ phân loại tối giản:

```java
package com.example.mail;

import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailParseException;

public final class MailFailureClassifier {

    public SafeMailFailure classify(MailException ex) {
        if (ex instanceof MailAuthenticationException) {
            return SafeMailFailure.AUTHENTICATION;
        }
        if (ex instanceof MailParseException) {
            return SafeMailFailure.MIME_PREPARATION;
        }
        return SafeMailFailure.UNKNOWN;
    }
}
```

Ví dụ cố ý **không** đọc `ex.getMessage()` để suy ra lỗi. Trong production, có thể mở rộng bằng SMTP status code và kiểu exception đã biết của phiên bản provider/Jakarta Mail đang sử dụng; tránh regex tùy tiện trên nội dung trả về của server.

Một lỗi phân loại là `UNKNOWN` vẫn có thể được đo đếm và báo động. Không cần hy sinh bảo mật bằng cách in toàn bộ protocol transcript chỉ để chia nhỏ thêm nhóm lỗi.

## 9. Ví dụ gửi mail có log an toàn trong Spring Boot

Ví dụ sau dùng `JavaMailSender` và `MimeMessageHelper` để gửi email sau khi đã được hệ thống nghiệp vụ xác thực, với log chỉ chứa ID, loại email, outcome và thời lượng.

```java
package com.example.mail;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SafeMailService {

    private static final Logger log =
            LoggerFactory.getLogger(SafeMailService.class);

    private final JavaMailSender sender;
    private final MailFailureClassifier classifier;

    public SafeMailService(
            JavaMailSender sender,
            MailFailureClassifier classifier) {
        this.sender = sender;
        this.classifier = classifier;
    }

    public void send(
            UUID jobId,
            MailKind kind,
            String recipient,
            String subject,
            String plainText) {

        long startedNanos = System.nanoTime();
        log.info(
                "mail stage=SMTP_SUBMITTING jobId={} kind={}",
                jobId, kind.name());

        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, false, StandardCharsets.UTF_8.name());

            helper.setFrom("notifications@example.org");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(plainText, false);

            sender.send(message);

            log.info(
                    "mail stage=SUBMITTED jobId={} kind={} elapsedMs={}",
                    jobId,
                    kind.name(),
                    (System.nanoTime() - startedNanos) / 1_000_000);
        } catch (MessagingException ex) {
            log.warn(
                    "mail stage=FAILED jobId={} kind={} failureClass={}",
                    jobId, kind.name(), SafeMailFailure.MIME_PREPARATION);
            throw new IllegalStateException(
                    "Unable to prepare mail message", ex);
        } catch (MailException ex) {
            SafeMailFailure failure = classifier.classify(ex);
            log.warn(
                    "mail stage=FAILED jobId={} kind={} failureClass={}",
                    jobId, kind.name(), failure.name());
            throw ex;
        }
    }
}
```

Trong ví dụ:

- `recipient`, `subject` và `plainText` chỉ được dùng để dựng message, không đi vào log.
- `jobId` phải do ứng dụng tạo độc lập với địa chỉ người nhận.
- `MailKind` là enum do ứng dụng định nghĩa như `PASSWORD_RESET` hoặc `ORDER_CONFIRMATION`; không nhận tùy ý từ người dùng.
- Thời lượng được đo bằng `System.nanoTime()`, phù hợp với elapsed time.
- `SUBMITTED` biểu thị Spring Mail gửi thành công theo phản hồi từ tầng submission, không phải bằng chứng email đã được deliver.
- Exception được **rethrow** để tầng retry/job có thể xử lý, nhưng tầng trên cũng phải tuân thủ chính sách log an toàn. Một global exception handler log toàn bộ cause chain có thể làm lộ dữ liệu mà service trên đã cố tránh.

Nếu chỉ cần text mail đơn giản, `SimpleMailMessage` cũng dùng được, nhưng việc không log body/password vẫn là yêu cầu tương tự. Với HTML/attachment, bật multipart mode và dùng `addInline`/`addAttachment` thay vì serialize MIME vào log.

### Một bộ phân loại là Spring bean

Nếu dùng dependency injection như trên, có thể đánh dấu bộ phân loại là component:

```java
import org.springframework.stereotype.Component;

@Component
public final class MailFailureClassifier {
    public SafeMailFailure classify(MailException ex) {
        if (ex instanceof MailAuthenticationException) {
            return SafeMailFailure.AUTHENTICATION;
        }
        if (ex instanceof MailParseException) {
            return SafeMailFailure.MIME_PREPARATION;
        }
        return SafeMailFailure.UNKNOWN;
    }
}
```

Trong mã thật, tổ chức các import đầy đủ và dùng một định nghĩa duy nhất của lớp. Hai đoạn trên minh họa cách tách gửi mail khỏi phân loại lỗi; không cần tạo nhiều phiên bản của `MailFailureClassifier`.

## 10. Dữ liệu nhạy cảm có thể đi vào log qua toString()

Ngay cả khi người viết không log `password` trực tiếp, một DTO hoặc record có `toString()` sinh tự động có thể vô tình xuất mọi field:

```java
public record MailRequest(
        String recipientEmail,
        String subject,
        String htmlBody,
        String resetToken) {
}
```

Với record Java, `toString()` mặc định biểu diễn các thành phần. Câu lệnh:

```java
log.debug("mailRequest={}", mailRequest);
```

có thể ghi cả `resetToken` và `htmlBody`.

### Không dựa vào masking của một object tùy ý

Một lớp có thể override `toString()`:

```java
public final class OutgoingMailCommand {

    private final UUID jobId;
    private final String recipient;
    private final String body;

    // Constructor/getters lược bỏ cho ngắn gọn.

    @Override
    public String toString() {
        return "OutgoingMailCommand{jobId=" + jobId + "}";
    }
}
```

Cách này giảm rủi ro khi object vô tình được format, nhưng **không thay thế quy tắc chỉ log các field đã được allowlist**. Một logger hoặc framework serializer khác có thể dùng reflection/getter để truy cập field dù `toString()` an toàn.

Với Lombok `@Data` hoặc `@ToString`, cần xem xét `@ToString.Exclude` cho secret, nhưng lựa chọn an toàn hơn là không log toàn bộ command có dữ liệu riêng tư ngay từ đầu.

## 11. Không log request body hoặc template context theo thói quen

Ứng dụng có thể có endpoint:

```text
POST /api/mail/send
```

Payload có thể chứa recipient, subject, HTML body, attachment reference hoặc token. Một HTTP logging filter ghi toàn bộ body trước khi service chạy có thể làm lộ dữ liệu dù service gửi mail không có câu lệnh `log.debug`.

Các điểm cần kiểm soát:

1. HTTP filter/access log: tránh ghi query string nếu URL chứa token; không ghi request body mặc định.
2. Controller advice: không đưa DTO nguyên bản vào error response hay exception message.
3. AOP interceptor: tránh log toàn bộ method arguments/return values cho method xử lý mail.
4. Template renderer: không log toàn bộ variable map.
5. Serialization/debugger: không tự động dump object có recipient/token/body.
6. Tracing instrumentation: chỉ đặt thuộc tính an toàn; không thêm message body làm span attribute.

### Ví dụ interceptor rủi ro

```java
// Anti-pattern: có thể biến mọi tham số thành nội dung log.
@Around("execution(* com.example.mail..*(..))")
public Object traceAll(ProceedingJoinPoint pjp) throws Throwable {
    log.debug("arguments={}", Arrays.toString(pjp.getArgs()));
    return pjp.proceed();
}
```

Nếu cần AOP/tracing, chỉ ghi tên operation và ID đã được xác nhận không chứa PII. Tránh áp dụng generic argument logging trên các package như `auth`, `mail` và `payment`.

## 12. MDC và correlation ID: truy vết không cần nội dung

MDC cho phép gắn metadata ngắn vào những dòng log cùng một luồng xử lý:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
             MDC.putCloseable("mailJobId", job.id().toString())) {

    log.info("mail stage=STARTED kind={}", job.kind().name());
    mailProcessor.process(job);
    log.info("mail stage=FINISHED");
}
```

Ưu điểm là mọi dòng có thể dùng chung `mailJobId` mà không phải truyền recipient hoặc subject. Tuy nhiên cần tuân thủ:

- Chỉ đưa ID nội bộ không chứa bí mật vào MDC.
- Xóa MDC bằng `close()` hoặc `finally` để thread pool không mang ngữ cảnh của job cũ sang job mới.
- Với `@Async`, MDC không tự động truyền đúng qua mọi executor/thread. Nếu cần copy context, dùng `TaskDecorator` có chọn lọc và chỉ copy allowlisted fields.
- Không đưa raw JWT, session cookie, OTP, email address hoặc full URL có query string vào MDC.

### Async context propagation cần được kiểm soát

Nếu một request thread đang giữ MDC với dữ liệu không phù hợp rồi `TaskDecorator` copy toàn bộ map sang worker, bí mật có thể lan thêm vào log mail. Thay vào đó, tạo context cho worker từ `mailJobId` và các trường an toàn, hoặc filter kỹ các khóa trước khi truyền.

Không dùng correlation ID được lấy nguyên văn từ request header không đáng tin cậy mà không kiểm tra định dạng và giới hạn độ dài; đầu vào tùy ý có thể làm nhiễu log hoặc mang dữ liệu không được phép.

## 13. Metrics: đo lỗi mà không tạo nhãn nhạy cảm

Micrometer và Spring Boot Actuator có thể đo hiệu năng gửi thư bằng counter và timer mà không cần log payload. Ví dụ:

```java
registry.counter(
        "mail.submission.attempts",
        "kind", kind.name(),
        "outcome", "failed",
        "failure", failure.name())
        .increment();
```

Những nhãn an toàn thường có tập giá trị nhỏ:

| Nhãn | Nên dùng? | Lý do |
|---|---|---|
| `kind=PASSWORD_RESET` | Có, nếu enum giới hạn | Nhóm nghiệp vụ hữu hạn |
| `outcome=accepted/failed` | Có | Trạng thái chuẩn hóa |
| `failure=AUTHENTICATION` | Có | Phân loại lỗi hữu hạn |
| `provider=primary/backup` | Có thể | Alias do ứng dụng kiểm soát |
| `recipient_email=...` | Không | PII và cardinality cao |
| `subject=...` | Không | Có thể chứa nội dung nhạy cảm |
| `job_id=...` | Không làm metric tag | Cardinality rất cao; dùng log/tracing |
| `exception_message=...` | Không | Có thể lộ dữ liệu và tạo vô số series |
| `tenant_id=...` | Cân nhắc kỹ | Có thể là ID nhạy cảm/cardinality cao |

Metric `mail.submission.attempts` đo **số lần thử**, không phải số email duy nhất: retry có thể làm một job phát sinh nhiều attempts. Nên có metric riêng cho job được enqueue, job submitted, failed permanently và expired.

Không được đặt raw email body hoặc SMTP password vào metric exemplar, span attribute, log annotation hay dashboard tooltip chỉ vì đó “không phải log”.

## 14. Logging configuration an toàn trong Spring Boot

Một cấu hình ứng dụng thường hướng đến INFO/WARN ở production và tránh protocol debug:

```yaml
logging:
  level:
    root: INFO
    org.springframework.mail: WARN
    jakarta.mail: WARN
    org.eclipse.angus.mail: WARN

spring:
  mail:
    properties:
      "[mail.debug]": false
      "[mail.debug.auth]": false
```

Tên logger cụ thể có thể thay đổi theo phiên bản thư viện Jakarta Mail/Angus Mail và logging bridge. Kiểm tra implementation thực tế; đừng giả định cài log level là đủ để tắt debug output ghi thẳng ra `PrintStream`.

### Cấu hình không nên bật vô thời hạn

Tránh để:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
      "[mail.debug.auth]": true
```

trong cấu hình production. Không bật `TRACE` cho toàn bộ `org.springframework` chỉ để điều tra một lỗi SMTP, vì trace từ các thành phần khác có thể chứa thông tin request, security context hoặc template variables.

### Actuator và endpoint cấu hình

Actuator có thể cung cấp thông tin môi trường, configprops và loggers. Các endpoint này phải được bảo vệ bằng network policy, authentication và authorization; không mở rộng exposure chỉ để chẩn đoán mail. Spring Boot hiện đại có cơ chế làm mờ giá trị nhạy cảm ở một số endpoint, nhưng không nên xem đó là lý do để xuất cấu hình mật khẩu một cách rộng rãi.

Ví dụ cấu hình giới hạn endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Các giá trị này phụ thuộc phiên bản Boot đang dùng; hãy đối chiếu tài liệu phiên bản để bảo đảm không có endpoint riêng hoặc extension bỏ qua chính sách masking. Điều quan trọng là không để bất kỳ đường truy cập HTTP nào tiết lộ secret thông qua configuration dump.

## 15. Redaction: lớp bảo vệ bổ sung, không phải giải pháp duy nhất

Redaction hoặc masking có thể che một số mẫu giá trị trước khi log được lưu trữ. Ví dụ một hệ thống log collector có thể che key `password` hoặc `authorization`. Tuy nhiên:

- SMTP password có thể xuất hiện dưới dạng chuỗi base64 trong AUTH transcript.
- Token có thể nằm trong URL với tên parameter khác nhau.
- Body HTML có thể chứa nội dung không theo mẫu cố định.
- Secret có thể bị URL-encode, JSON-escape hoặc chia thành nhiều dòng.
- Exception của provider có thể dùng cách biểu diễn không nằm trong regex đã cấu hình.

Do đó, không có một regex universal có thể làm an toàn toàn bộ log chứa email.

### Ưu tiên allowlist thay vì blocklist

**Allowlist logging:** chỉ tạo event log từ những field đã được xác định an toàn, ví dụ `jobId`, `kind`, `stage`, `failureClass`.

**Blocklist redaction:** nhận toàn bộ dữ liệu rồi cố gắng che `password`, `token` hoặc email address.

Allowlist ngăn dữ liệu không được phép đi vào pipeline ngay từ đầu; blocklist chỉ cố xử lý sau khi đã nhận dữ liệu. Kết hợp cả hai có giá trị phòng thủ nhiều lớp, nhưng allowlist nên là nguyên tắc chính.

### Tránh hash trực tiếp địa chỉ email để “ẩn danh”

Hash không salt hoặc salt chung của email có thể bị suy đoán bằng dictionary vì không gian email có cấu trúc và nhiều địa chỉ phổ biến. Nếu thật sự cần đối chiếu một địa chỉ giữa các sự kiện, cân nhắc một định danh nội bộ hoặc HMAC với khóa được quản lý, thay vì đưa hash đơn giản vào mọi log.

Ngay cả identifier đã được pseudonymize vẫn có thể là dữ liệu cá nhân trong một số bối cảnh. Áp dụng chính sách quyền truy cập và retention phù hợp.

## 16. Tách log vận hành khỏi audit nghiệp vụ

Log và audit không phải cùng một loại dữ liệu:

- **Operational log:** giúp phát hiện SMTP timeout, số lần retry, worker bị lỗi, elapsed time.
- **Business audit:** ghi nhận ai kích hoạt gửi một email, lý do nghiệp vụ, trạng thái xử lý và quyền liên quan.

Audit có thể cần lưu recipient hoặc dữ liệu giao dịch để đáp ứng nghiệp vụ, nhưng nên nằm trong hệ thống có schema, quyền truy cập và retention riêng; không nhất thiết sao chép các trường này vào log tập trung.

Ví dụ audit metadata:

```text
MailJob
  id: UUID
  type: ORDER_CONFIRMATION
  businessRef: internal order id
  state: SUBMITTED
  createdAt: timestamp
  submittedAt: timestamp
  attemptCount: 2
  lastFailureClass: SMTP_TIMEOUT
```

Nếu nhân viên hỗ trợ cần xem recipient hoặc subject, ứng dụng có thể cung cấp màn hình tra cứu có phân quyền dựa trên `MailJob`, không cần cho họ quyền xem toàn bộ raw log.

### Phân biệt SUBMITTED và DELIVERED

`JavaMailSender.send(...)` trả về thành công thường có nghĩa việc submission với SMTP server đã được chấp nhận. Điều này **không bảo đảm đã giao tới mailbox**. Nếu provider cung cấp webhook giao thư/bounce, ghi nhận như các event khác với quyền và retention thích hợp; không dùng log để tự suy đoán rằng thư đã được đọc.

## 17. Log trong retry, queue và transactional outbox

Khi gửi mail bất đồng bộ, một yêu cầu có thể chạy qua nhiều lần retry. Nếu log toàn bộ command mỗi lần, nội dung nhạy cảm bị nhân bản nhiều lần.

Thay vào đó, mỗi attempt có thể ghi:

```text
mail jobId=... kind=ORDER_CONFIRMATION attempt=1
     stage=SMTP_SUBMITTING

mail jobId=... kind=ORDER_CONFIRMATION attempt=1
     stage=FAILED failureClass=SMTP_TIMEOUT retryable=true

mail jobId=... kind=ORDER_CONFIRMATION attempt=2
     stage=SMTP_SUBMITTING

mail jobId=... kind=ORDER_CONFIRMATION attempt=2
     stage=SUBMITTED
```

Những dòng này giúp biết tổng attempts, nhóm lỗi, trạng thái cuối cùng mà không chứa recipient/subject/body.

### Đừng log payload của outbox

Transactional outbox thường lưu JSON event hoặc job payload. Một số event có thể chứa recipient, template variables, attachment references hoặc token:

```java
// Không in toàn bộ record outbox.
log.debug("Processing outbox record: {}", outboxEvent);
```

Chỉ log ID, event type đã được allowlist, status và attempt count. Đối với payload có secret, cần hạn chế cả việc lưu payload ở dạng plaintext trong outbox; cân nhắc lưu tham chiếu đến dữ liệu được bảo vệ và áp dụng retention.

### Không log quá nhiều lần khi retry

Một exception có thể được log ở repository, worker, retry scheduler, async handler và global exception handler. Nếu mỗi tầng đều log đầy đủ cause chain, một sự cố đơn lẻ tạo nhiều bản sao dữ liệu và làm tăng noise.

Quy ước hữu ích:

1. Tầng thấp trả lỗi có kiểu/cause cho tầng gọi.
2. Tầng sở hữu job phân loại lỗi, cập nhật trạng thái và quyết định retry.
3. Chỉ một tầng chịu trách nhiệm ghi **operational failure event**.
4. Metrics đếm theo outcome/attempt.
5. Chẩn đoán nhạy cảm được quản lý qua kênh riêng khi thật sự cần.

## 18. Logging cho SMTP lỗi xác thực, rate limit và recipient

Các loại lỗi SMTP cần thông tin khác nhau. Không cần mở protocol dump cho tất cả.

| Tình huống | Log an toàn gợi ý | Không nên log |
|---|---|---|
| Sai SMTP credentials | `failureClass=AUTHENTICATION`, provider alias | Password, AUTH transcript, access token |
| SMTP timeout | `failureClass=TIMEOUT`, duration, retry attempt | Toàn bộ session debug, body |
| Provider rate limit | `failureClass=THROTTLED`, retryable, delay | Raw server reply chứa dữ liệu không tin cậy |
| Recipient bị từ chối | `failureClass=RECIPIENT_REJECTED`, count | Địa chỉ email đầy đủ trong log tập trung |
| MIME parsing lỗi | `failureClass=MIME_PREPARATION`, template ID/version | Raw MIME hoặc HTML body |
| Attachment quá lớn | `failureClass=MESSAGE_TOO_LARGE`, byte count | Nội dung file, tên file riêng tư |
| DNS/TLS lỗi | `failureClass=CONNECTION` hoặc `TLS_FAILURE` | Full config dump, keystore password |

Khi thật sự cần mã phản hồi SMTP để xác định retry, lấy code số hoặc enum đã chuẩn hóa ở tầng adapter. Không log nguyên SMTP response string, vì nội dung có thể bao gồm địa chỉ người nhận hoặc dữ liệu do server kiểm soát.

### Lưu ý về log từ thư viện bên thứ ba

Một SDK mail provider có thể log request/response HTTP, including authorization header, nếu bật HTTP wire logging. Spring Mail dùng SMTP nhưng kiến trúc có thể kết hợp SMTP, REST provider và network proxy.

Đảm bảo cấu hình log an toàn ở tất cả lớp: HTTP client, SMTP transport, mail worker, proxy/sidecar, gateway và collector. Chặn một log statement ở service không đủ nếu thư viện thấp hơn vẫn dump request.

## 19. Kiểm thử để phòng ngừa secret lọt vào log

Có thể viết test đưa các chuỗi giả nhưng dễ nhận diện vào thông tin nhạy cảm, thực hiện đường xử lý lỗi và xác nhận hệ thống **không ghi** những chuỗi đó.

Ví dụ sentinel test:

```text
fake SMTP password: TEST_SECRET_SMTP_DO_NOT_LOG
fake reset token:   TEST_RESET_TOKEN_DO_NOT_LOG
fake recipient:     private-recipient@example.invalid
fake HTML marker:   TEST_PRIVATE_BODY_DO_NOT_LOG
```

Không sử dụng secret thật trong test. Thông tin test nên thuộc domain `example.invalid` hoặc được sinh giả.

### Kiểm tra bằng Logback ListAppender

Ví dụ phác thảo cho một service có logger riêng:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class SafeMailLoggingTest {

    @Test
    void shouldNotExposeMailSecretsInApplicationLogs() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                SafeMailService.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            // Dùng mock sender gây lỗi và input giả có sentinel.
            // triggerMailFailureWithFakeSecrets();

            String logs = appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .reduce("", (a, b) -> a + "\n" + b);

            assertFalse(logs.contains("TEST_SECRET_SMTP_DO_NOT_LOG"));
            assertFalse(logs.contains("TEST_RESET_TOKEN_DO_NOT_LOG"));
            assertFalse(logs.contains("private-recipient@example.invalid"));
            assertFalse(logs.contains("TEST_PRIVATE_BODY_DO_NOT_LOG"));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
```

Đây là **bộ khung minh họa**, không phải test chạy độc lập: dự án cần mock sender và thực hiện lời gọi gây lỗi trước khi assert. Test trên chỉ bắt log được gửi qua logger của `SafeMailService`. Nó không chứng minh rằng Jakarta Mail debug output hoặc thư viện thứ ba không xuất dữ liệu sang stdout/stderr; để kiểm tra toàn tuyến cần test thêm collector, container logs và mọi output stream có thể dùng.

### Các trường hợp test quan trọng

| Tình huống | Điều cần kiểm tra |
|---|---|
| SMTP AUTH failure | Không log password/token, ngay cả ở error handler |
| SMTP timeout với nested exception | Không log raw exception message có recipient |
| HTML template chứa OTP | Không log body hoặc template variable map |
| PDF attachment bị lỗi | Không log byte, base64 hoặc file path nhạy cảm |
| Queue retry nhiều lần | Mỗi attempt chỉ có metadata allowlisted |
| `mail.debug` vô tình bật | Cấu hình production chặn hoặc cảnh báo |
| Global exception handler | Không tự dump full command/cause chain |
| `@Async` worker dùng MDC | Không rò context giữa hai jobs |
| Log collector/forwarder | Không làm hiện lại field bị che ở tầng ứng dụng |
| Request/HTTP client logging | Không log body, authorization hay signed URL |

Test có thể kết hợp static scanning để phát hiện một số anti-pattern như `log.info("password..."` hoặc `log.debug("body=..."`, nhưng static scanning không nhận diện hết trường hợp log object/toString và protocol debug. Cần phòng vệ ở thiết kế và cấu hình runtime.

## 20. Kiểm soát log ở môi trường production

Ngăn secret đi vào log là bước đầu tiên. Log đã được tạo vẫn cần được bảo vệ:

- Chỉ người có trách nhiệm mới được quyền đọc logs.
- Phân quyền theo service/environment; không cho mọi developer truy cập mọi log chứa metadata người dùng.
- Mã hóa đường truyền và storage của hệ thống log.
- Thiết lập retention ngắn phù hợp cho operational logs.
- Kiểm soát export/download logs và lưu vết truy cập.
- Không tự động gửi raw logs vào chat/ticket hoặc kênh hỗ trợ bên ngoài.
- Áp dụng DLP/redaction ở collector như lớp bảo vệ bổ sung.
- Rà soát cấu hình debug khi deploy, đặc biệt các giá trị override bằng environment variable.

### Log sampling

Với lượng email lớn, có thể sampling các sự kiện thành công để giảm chi phí. Tuy nhiên, không nên sampling khiến các lỗi quan trọng hoặc cảnh báo bảo mật bị mất hoàn toàn. Một cách tiếp cận:

- Metrics đếm đầy đủ số attempts và outcomes.
- Log `SUBMITTED` ở mức phù hợp hoặc sampling theo quy định.
- Log lỗi với metadata an toàn và mã phân loại, có thể rate limit theo nhóm.
- Dùng `mailJobId` để tra cứu trạng thái chính xác ở job store khi cần.

Sampling không làm dữ liệu nhạy cảm trở nên an toàn. Một log có password vẫn là sự cố dù chỉ được sample 1%.

## 21. Ứng phó khi phát hiện mật khẩu hoặc nội dung nhạy cảm đã bị log

Nếu một người phát hiện credentials hoặc nội dung mail nhạy cảm trong logs, cần xử lý như sự cố lộ dữ liệu, không chỉ là “dọn một dòng debug”.

### 21.1. Khoanh vùng ngay

1. Tắt cấu hình phát sinh log nhạy cảm và triển khai bản sửa.
2. Xác định loại secret/data đã lộ, thời điểm đầu/cuối, số lượng bản ghi và nơi đã được gửi.
3. Hạn chế truy cập hoặc tạm dừng chia sẻ hệ thống log liên quan nếu cần.
4. Không sao chép secret sang ticket, chat hoặc email để thông báo sự cố.

### 21.2. Thu hồi/luân chuyển secret

Nếu SMTP password, app password, API key hoặc OAuth token bị lộ:

- Thu hồi hoặc rotate credential theo cơ chế provider.
- Cập nhật secret manager và rolling deployment an toàn.
- Kiểm tra hoạt động gửi bất thường, quota và các session đang hoạt động.
- Không giả định “đã xóa log thì mật khẩu vẫn an toàn”, vì log có thể đã được đọc hoặc sao chép.

Đối với reset token/OTP đã lộ, cần đánh giá việc vô hiệu hóa token/challenge theo quyền và chính sách nghiệp vụ, không chỉ xóa bản ghi log.

### 21.3. Xử lý bản sao log

Log có thể nằm ở:

```text
Application process
    -> stdout / file
    -> node/container logging
    -> collector/agent
    -> central index
    -> export / alert / ticket
    -> archive / backup
```

Cần kiểm tra các bản sao theo quy trình của tổ chức. Việc xóa khỏi dashboard không nhất thiết xóa khỏi archive hoặc snapshot. Tránh đưa thêm dữ liệu nhạy cảm vào quá trình tìm kiếm bằng cách paste nguyên token vào mọi query nếu hệ thống còn ghi lại search history.

### 21.4. Đánh giá tác động và thông báo

Tùy dữ liệu và phạm vi, đội bảo mật/pháp chế có thể cần đánh giá nghĩa vụ thông báo theo chính sách và quy định áp dụng. Lưu một incident record tối thiểu, không chứa bản sao password hoặc toàn bộ email. Sau khắc phục, bổ sung test và guardrail để tránh tái diễn.

## 22. Những lỗi thường gặp khi chẩn đoán mail

| Hiện tượng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| SMTP password xuất hiện khi bật debug | Protocol debug/auth debug được bật | Tắt, rotate secret, giới hạn scope |
| Log có token reset password | Template variables hoặc rendered HTML bị in | Log template ID/version, không log variables/body |
| Log có danh sách Bcc | Dump raw MimeMessage hoặc headers | Chỉ ghi jobId và recipient count khi cần |
| File PDF bị log dưới dạng base64 | Serialize attachment để debug | Log kích thước và MIME type |
| Logs chứa email người nhận | Exception message/provider reply hoặc `toString()` | Phân loại lỗi thành enum an toàn |
| DTO có `toString()` lộ dữ liệu | Ghi nguyên object ở INFO/DEBUG | Allowlist field, không log command |
| Chỉ service log an toàn nhưng collector vẫn lộ | HTTP/SMTP wire logger hoặc tracing | Kiểm soát toàn bộ pipeline |
| MDC mang jobId cũ | Không clear ThreadLocal sau task | `putCloseable`/`finally` |
| Metrics tạo hàng triệu series | Dùng recipient/jobId làm label | Chỉ dùng low-cardinality tags |
| Không phân biệt timeout và auth failure | Chỉ lưu message text thay vì category | Safe failure classifier |
| Cần debug nhưng không biết gửi thư nào | Không có correlation ID/job store | Dùng mailJobId, tracing metadata an toàn |
| Email gửi lỗi bị log nhiều lần | Mỗi layer ghi nguyên exception | Quy ước một tầng log operational event |
| Sau xóa log vẫn còn secret | Log đã được forward hoặc backup | Incident response, rotation, kiểm tra các bản sao |

## 23. Checklist áp dụng vào dự án

Trước khi triển khai một luồng gửi email mới, đội dự án nên xác định:

1. **Nguồn secret:** SMTP credentials lấy từ secret manager hoặc cấu hình được bảo vệ; không hard-code và không log.
2. **Logging surface:** service, controller, filter, AOP, executor, provider SDK, Jakarta Mail debug, proxy và collector đều được xem xét.
3. **Metadata được phép:** jobId, mailType enum, attempt, status, failureClass, elapsedMs.
4. **Dữ liệu không log:** recipient, subject, password/token, MIME body, attachment byte và signed URL.
5. **Exception:** không tự in `getMessage()`/cause chain ở mọi tầng; có cơ chế phân loại lỗi an toàn.
6. **Debug policy:** protocol debug tắt mặc định; chẩn đoán tăng mức log phải ngắn hạn và có phạm vi.
7. **MDC/tracing:** chỉ dùng ID không chứa PII, dọn context sau task.
8. **Metrics:** tag có cardinality thấp; không dùng recipient/jobId làm label.
9. **Audit:** metadata nghiệp vụ nhạy cảm được lưu trong hệ thống có phân quyền, không nhét vào operational log.
10. **Kiểm thử:** có sentinel test giả lập secret trên các đường lỗi điển hình và kiểm tra runtime output khi phù hợp.
11. **Retention:** log được lưu và cấp quyền đúng mức cần thiết; không biến log thành kho chứa bản sao của email.
12. **Incident response:** có cách thu hồi credentials, vô hiệu hóa token và xử lý bản sao log khi phát hiện rò rỉ.

## 24. Câu hỏi thường gặp

**Có nên log `spring.mail.password` để kiểm tra Spring Boot đã đọc đúng cấu hình?** Không. Chỉ kiểm tra credential có được cấu hình hay chưa, hoặc xác minh bằng một kết nối thử có kiểm soát. Giá trị secret không cần xuất hiện trong log.

**`mail.debug=true` có an toàn nếu `mail.debug.auth=false`?** Không thể xem là an toàn tuyệt đối. Cờ auth debug giúp tránh in credential của một số luồng AUTH, nhưng protocol log vẫn có thể chứa metadata nhạy cảm và có nhiều nguồn logging khác nhau. Không bật lâu dài trong production.

**Có thể log toàn bộ `MimeMessage` rồi xóa vài trường không?** Không nên. Cấu trúc MIME có thể chứa body, attachment và nhiều header; lọc sau khi dump rất dễ bỏ sót. Hãy log metadata do ứng dụng tự xây dựng.

**Log email address có luôn bị cấm không?** Nó là dữ liệu cá nhân và có thể cần thiết trong vài quy trình hỗ trợ có phân quyền. Tuy nhiên, operational log mặc định không cần địa chỉ đầy đủ. Nếu có yêu cầu nghiệp vụ hợp lệ, giới hạn mục đích, truy cập và retention thay vì ghi vào mọi dòng.

**Có nên hash recipient trước khi log không?** Hash đơn giản không tự làm dữ liệu vô danh. Dùng ID nội bộ hoặc thiết kế pseudonymization phù hợp, có đánh giá quyền riêng tư, thay vì mặc định hash email bằng SHA-256 rồi xem là an toàn.

**Có thể log subject không?** Không nên mặc định. Subject có thể chứa mã đơn, tên người dùng, giao dịch hoặc thông tin riêng tư. Dùng template ID/mail type thay thế.

**Tại sao exception stack trace cũng có thể nguy hiểm?** Throwable, nested cause và SMTP reply có thể chứa địa chỉ, đường dẫn hoặc giá trị do bên ngoài kiểm soát. Chỉ in stack trace qua kênh được phê duyệt hoặc sau khi kiểm soát dữ liệu.

**Nếu cần tìm người nhận của một mail job thì làm sao?** Dùng `mailJobId` tra cứu bản ghi trong hệ thống nghiệp vụ có phân quyền và audit, không mở rộng operational log để chứa recipient.

**`MailSendException.getFailedMessages()` có nên log không?** Không. Map có thể chứa `MimeMessage` và exception, nên dễ làm lộ nội dung. Nếu cần thống kê, lấy số phần tử hoặc outcome đã chuẩn hóa.

**Có thể log kích thước attachment không?** Thường được, nếu kích thước không tự tiết lộ thông tin nhạy cảm trong bối cảnh cụ thể. Không log byte, base64 và filename đầy đủ nếu không cần.

**Không log password thì làm sao chẩn đoán lỗi AUTH?** Ghi `failureClass=AUTHENTICATION`, provider alias, instance, thời điểm và attempt. Kiểm tra credentials trong secret manager và thử kết nối có kiểm soát.

**`@Async` có khiến MDC an toàn hơn không?** Không. MDC là thread context. Nếu không clear hoặc copy toàn bộ context, worker có thể mang dữ liệu của request/job khác. Chỉ truyền khóa an toàn và dọn trong `finally`.

**Log có password nhưng chỉ được giữ một ngày có chấp nhận được không?** Không. Secret có thể bị truy cập ngay trong một ngày đó và được nhân bản. Retention ngắn không thay thế việc ngăn lộ từ đầu.

**Base64 trong log có được xem là đã mã hóa an toàn không?** Không. Base64 giải mã dễ dàng. Dữ liệu MIME attachment ở dạng base64 vẫn là dữ liệu gốc có thể khôi phục.

**Có nên log tất cả sự kiện thành công của từng email không?** Tùy nhu cầu; metrics tổng hợp và job store thường đủ cho nhiều trường hợp. Nếu log per-job, chỉ dùng metadata allowlist, áp retention và sampling hợp lý.

**Gửi SMTP thành công có nghĩa email đã tới inbox?** Không. Đó thường chỉ là submission thành công. Delivery, bounce hoặc complaint cần dữ liệu từ provider/gateway riêng.

**Nếu secret đã lọt vào log thì cần làm gì?** Ngừng nguồn phát log, khoanh vùng bản sao, thu hồi/rotate credentials, đánh giá token đã lộ và thực hiện incident response theo chính sách; không chỉ xóa một dòng trong dashboard.

## 25. Tài liệu kỹ thuật liên quan

- **Spring Framework Mail:** `JavaMailSender`, `MimeMessageHelper`, `MailException`, `MailAuthenticationException` và `MailSendException`.
- **Spring Boot Externalized Configuration:** `spring.mail.*`, secret injection và cấu hình môi trường.
- **Jakarta Mail / Eclipse Angus Mail:** `Session`, SMTP transport, `mail.debug` và `mail.debug.auth`; hành vi cụ thể cần đối chiếu phiên bản đang dùng.
- **SLF4J và Logback:** structured logging, MDC, appenders, filter và configuration.
- **Micrometer / Spring Boot Actuator:** counter, timer, metrics endpoint và giới hạn tag cardinality.
- **OpenTelemetry:** span attributes, event attributes và quyền riêng tư trong distributed tracing.
- **OWASP Logging Cheat Sheet:** nguyên tắc tránh log dữ liệu bí mật, chống log injection và kiểm soát truy cập bản ghi.
- **Operational security guidelines:** quản lý secret, rotation, retention, auditing và incident response phù hợp môi trường triển khai.

---

**Ghi nhớ:** chẩn đoán email không cần ghi password, access token, OTP, recipient, subject, HTML body, raw `MimeMessage` hoặc attachment vào log. Hãy dùng `mailJobId` và mã trạng thái/lỗi đã chuẩn hóa; tắt protocol/auth debug trong production; kiểm soát exception, `toString()`, MDC, tracing và log collector; đo số liệu bằng metrics. Khi phát hiện dữ liệu nhạy cảm đã xuất hiện trong log, xử lý như một sự cố bảo mật và thu hồi secret phù hợp. **Log nên giúp tìm nguyên nhân gửi lỗi, không được trở thành bản sao của email và tài khoản SMTP.**

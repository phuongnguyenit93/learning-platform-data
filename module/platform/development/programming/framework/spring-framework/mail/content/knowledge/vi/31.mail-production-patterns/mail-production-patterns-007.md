# Provider adapter và chiến lược fallback

## 1. Bài toán production: gửi email mà không khóa chặt vào một nhà cung cấp

Trong ứng dụng dùng **Spring Framework Mail**, con đường đơn giản nhất để gửi email là cấu hình một `JavaMailSender` rồi gọi `send(...)`. Nhưng khi hệ thống lớn lên, một SMTP endpoint duy nhất có thể trở thành điểm nghẽn:

- Nhà cung cấp tạm ngừng dịch vụ hoặc gặp sự cố mạng.
- Tài khoản bị giới hạn tốc độ, quota hoặc số kết nối đồng thời.
- Email bảo mật cần mức ưu tiên khác với email marketing.
- Một nhà cung cấp hỗ trợ feedback API/webhook tốt, nhà cung cấp khác chỉ cung cấp SMTP/DSN.
- Các khách hàng/tenant có yêu cầu về vùng xử lý dữ liệu, sender domain hoặc hợp đồng khác nhau.
- Hệ thống muốn chuyển đổi nhà cung cấp theo đợt, chạy canary, hoặc có tuyến dự phòng khi primary không sử dụng được.

Nếu code nghiệp vụ tự gọi thẳng một vendor SDK hoặc `JavaMailSenderImpl` ở khắp nơi, mọi lần chuyển nhà cung cấp sẽ đòi hỏi sửa nhiều module. Nghiêm trọng hơn, việc viết `try { send(A); } catch (...) { send(B); }` mà không biết kết quả gửi ở A có thể tạo **hai email** cho người nhận.

**Provider adapter** giải quyết vấn đề phụ thuộc kỹ thuật: ứng dụng gọi một contract ổn định, còn adapter biết cách giao tiếp SMTP hoặc HTTP API với từng nhà cung cấp.

**Fallback strategy** giải quyết vấn đề lựa chọn: khi provider được chọn không khả dụng, hệ thống có được đổi provider không, đổi trong điều kiện nào, còn đúng chính sách dữ liệu và sender identity không, và có thể chứng minh thư chưa được nhận ở đường trước hay không.

~~~text
Business event / Notification service
                |
                v
          Durable mail outbox
                |
                v
           Routing policy
          (type/region/tenant)
                |
                v
       Provider capability filter
                |
                v
           Attempt planner
                |
           +----+------+
           |           |
           v           v
      SMTP adapter   HTTP API adapter
           |           |
           v           v
       Provider A    Provider B
           |           |
           +-----+-----+
                 |
                 v
       Normalized submission result
                 |
     +-----------+------------+
     |           |            |
     v           v            v
  ACCEPTED    REJECTED      UNKNOWN
                 |            |
                 v            v
          Retry/fallback    Reconcile
             if safe         before resend
                 |
                 v
      Attempt history + telemetry
~~~

> **Giới hạn quan trọng:** Adapter và fallback **không tạo exactly-once delivery** cho SMTP. Một timeout sau khi message được nộp có thể để lại kết quả không rõ; đổi sang provider khác ngay lúc này có thể gửi trùng. Production design phải mô hình hóa trạng thái `UNKNOWN`, idempotency và reconciliation thay vì coi mọi exception là “chưa gửi”.

## 2. Phân biệt adapter, router, fallback và retry

Các khái niệm này liên quan nhau nhưng không thay thế nhau.

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Provider adapter** | Chuyển contract nội bộ sang SMTP hoặc API cụ thể; chuẩn hóa outcome | `SmtpMailProviderAdapter`, `HttpMailProviderAdapter` |
| **Provider registry** | Tra cứu adapter và capability theo provider ID | `smtp-vn-tx-a` → SMTP adapter |
| **Routing policy** | Xác định tập provider *được phép* theo category/region/tenant/identity | Email `SECURITY/EU` → EU critical pool |
| **Selection policy** | Chọn provider trong tập hợp hợp lệ dựa trên priority/weight/quota/health | Chọn primary còn capacity |
| **Retry policy** | Quyết định có thử lại một operation sau lỗi tạm thời hay không | Backoff 30 s, max 5 attempts |
| **Fallback policy** | Quyết định được đổi sang provider khác hay không | A thất bại trước submission, B đã được phê duyệt |
| **Circuit breaker** | Tạm ngăn gọi provider đang suy giảm | A open circuit trong một khoảng |
| **Outbox/attempt store** | Lưu ý định gửi và lịch sử từng lần nộp | `PENDING`, `SENDING`, `ACCEPTED`, `UNKNOWN` |
| **Feedback adapter** | Chuẩn hóa delivery/bounce/complaint webhook/DSN từ provider | `hard_bounce` → central suppression |

### 2.1. Retry khác fallback

~~~text
Attempt #1 -> provider A -> DEFINITE_RETRYABLE_FAILURE

Retry:
  Attempt #2 -> provider A

Fallback:
  Attempt #2 -> provider B
~~~

Fallback **thường tạo một attempt mới**, nên vẫn chịu giới hạn retry/deadline, không được miễn trừ `max_attempts` chỉ vì chọn provider khác.

### 2.2. Fallback khác load balancing

**Load balancing** chia *những message mới* giữa nhiều provider hợp lệ để giảm tải. **Fallback** đổi tuyến sau khi có tín hiệu provider đầu không thể phục vụ một yêu cầu cụ thể. Một policy có thể kết hợp cả hai, nhưng cần audit được:

~~~text
routeReason = PRIMARY_SELECTED
routeReason = WEIGHTED_SELECTION
routeReason = PRIMARY_CIRCUIT_OPEN
routeReason = APPROVED_FALLBACK_AFTER_PRE_SUBMISSION_FAILURE
~~~

Không gộp mọi nguyên nhân vào `provider_used=B` rồi không biết B được chọn vì thuật toán chia tải hay do sự cố A.

### 2.3. “Provider available” chưa có nghĩa “provider eligible”

Một nhà cung cấp có thể online nhưng không đáp ứng:

- Yêu cầu xử lý dữ liệu trong khu vực đã được phê duyệt.
- Sender identity, From domain và DKIM verification.
- Loại email (`SECURITY`/`TRANSACTIONAL`/`MARKETING`).
- Kích thước MIME message, attachment type, số recipient.
- Tenant permission, contract/quota.
- Yêu cầu TLS/authentication, logging, retention.

**Thứ tự đúng:** xác định **tập provider được phép** trước, sau đó mới xét health, quota và cách chọn. Không cho circuit breaker hoặc thuật toán “rẻ nhất” vượt qua policy bảo mật.

## 3. Một số tình huống khiến fallback phải rất thận trọng

### 3.1. Lỗi xảy ra trước khi gửi DATA

~~~text
App -> SMTP A: connect
        X connection refused

No SMTP message submission occurred.
~~~

Nếu xác định chắc chắn **chưa nộp message** cho A, ứng dụng có thể xét provider B theo policy, deadline và capacity. Tuy nhiên exception từ JavaMail/Jakarta Mail có thể không luôn cung cấp stage đã được chuẩn hóa; adapter cần ghi rõ khả năng xác định giai đoạn và dùng kết quả `UNKNOWN` khi không chắc.

### 3.2. SMTP trả lỗi 5xx cho recipient

~~~text
App -> SMTP A: RCPT TO:<invalid@example.net>
A   -> App: 550 user unknown
~~~

Đây thường là một lỗi recipient vĩnh viễn. Đổi sang B không biến địa chỉ sai thành đúng và có thể tạo spam/suppression violation. Đừng fallback tự động cho mọi lỗi 5xx.

### 3.3. Timeout sau SMTP DATA

~~~text
App -> SMTP A: DATA
App -> SMTP A: [complete MIME body]
A   -> App: [connection drops before final response]
~~~

Ứng dụng **không biết** A đã accepted hay chưa. Nếu B được gọi ngay:

~~~text
A may deliver email
B may also deliver email
          |
          v
        Duplicate
~~~

`Message-ID` có ích để correlation, nhưng không có hợp đồng SMTP phổ quát rằng relay sẽ loại trùng theo header này.

### 3.4. SMTP accepted nhưng commit database thất bại

~~~text
A accepts message -> send(...) returns
                   |
                   v
DB update markAccepted fails
                   |
                   v
Outbox appears due after lease expires
                   |
                   v
Blind retry through A/B -> duplicate possible
~~~

Transactional outbox giúp commit *ý định gửi* cùng dữ liệu nghiệp vụ, nhưng không tạo distributed transaction giữa DB và SMTP. Cần quy trình đối soát cho “accepted nhưng chưa lưu state” hoặc cửa sổ không chắc chắn tương đương.

### 3.5. Provider HTTP API có idempotency key

Một số nhà cung cấp API HTTP có thể hỗ trợ idempotency key để lặp lại request cùng key mà không tạo submission mới, nhưng đây là **khả năng riêng của từng API và hợp đồng cụ thể**:

- Khóa có hiệu lực trong bao lâu?
- Cùng key nhưng payload khác sẽ bị xử lý ra sao?
- Key được scope theo account, endpoint hay tenant?
- Retry sau timeout có trả lại provider message ID cũ không?

Không giả định mọi provider HTTP đều có tính năng đó, hoặc idempotency API đồng nghĩa email đã tới inbox.

## 4. Xác định contract chung trước khi viết từng adapter

Một contract tốt phải vừa đủ chung để domain không biết vendor, vừa không xóa mất các khác biệt quan trọng giữa SMTP và HTTP API.

### 4.1. Command nghiệp vụ khác wire request

Một use case có thể chuẩn bị:

~~~text
MailDeliveryCommand
  deliveryId
  tenantId
  category
  region
  recipient
  sendingIdentity
  templateKey + templateVersion
  renderedBody / immutable model reference
  attachments (durable references)
  businessDeadline
  idempotencyKey
~~~

Đây là dữ liệu nghiệp vụ được validation và authorize, không phải SMTP envelope hay vendor-specific JSON. Adapter sẽ nhận một **request đã được chuẩn bị và kiểm tra đủ điều kiện** rồi xây wire message tương ứng.

### 4.2. Tránh adapter quyết định chính sách nghiệp vụ

Không đặt rule kiểu “nếu khách ở EU thì không được gửi qua US” rải rác trong từng vendor adapter. Tầng router/policy chịu trách nhiệm điều kiện xử lý dữ liệu, còn adapter kiểm tra lại capability kỹ thuật và không được gửi khi yêu cầu vượt giới hạn rõ ràng.

Nếu adapter A tự cho phép một route mà adapter B tự cấm, khó kiểm tra toàn bộ chính sách và có thể phát sinh lỗi khi fallback.

### 4.3. Vòng đời một delivery

~~~text
PREPARED
   |
   v
PENDING  ----> ROUTE_SELECTED
                 |
                 v
             ATTEMPTING
                 |
       +---------+----------+---------------+
       |                    |               |
       v                    v               v
     ACCEPTED           DEFINITE_FAIL     UNKNOWN
       |                    |               |
       v                    v               v
  Mark accepted       RETRY or FAILED   RECONCILE/HOLD
                            |
                            v
                     Approved fallback?
                       |          |
                      Yes         No
                       |          |
                       v          v
                  New attempt   Wait/terminal
~~~

Trong mô hình này, `ACCEPTED` nghĩa nhà cung cấp đã **nhận submission**, chưa bảo đảm delivered-to-inbox. Bounce, complaint và delivery feedback là trạng thái khác theo dõi sau submission.

## 5. Thiết kế kết quả trả về có thể phân loại

Không trả một `boolean sent` vì `false` không diễn đạt được sự khác nhau giữa lỗi vĩnh viễn, lỗi tạm thời và kết quả không rõ.

Một kiểu kết quả minh họa:

~~~java
package com.example.mail.provider;

import java.time.Instant;

public enum SubmissionOutcome {
    ACCEPTED,           // Provider accepted submission.
    DEFINITE_REJECTED,  // Provider definitely did not accept it.
    UNKNOWN             // Submission result cannot be proven.
}

public enum RejectionKind {
    TRANSIENT,
    PERMANENT,
    POLICY,
    CAPACITY,
    UNCLASSIFIED
}

public record ProviderSubmissionResult(
        String providerId,
        SubmissionOutcome outcome,
        RejectionKind rejectionKind,
        String safeCode,
        String providerMessageId,
        Instant observedAt) {
}
~~~

Đây là các type do **ứng dụng thiết kế**, không phải API có sẵn của Spring Mail. Với Java, những top-level `public` enum/record phải đặt ở các tệp nguồn riêng.

Các invariant có thể đặt tại factory/constructor:

- `ACCEPTED` không gắn `RejectionKind.PERMANENT`.
- `DEFINITE_REJECTED` chỉ được dùng khi có bằng chứng provider **chưa nhận submission**.
- `UNKNOWN` không bị rút gọn thành transient error.
- `providerMessageId` có thể `null`, nhất là với SMTP thuần.
- `safeCode` lấy từ danh mục hữu hạn, không từ raw exception hoặc body người dùng.

### 5.1. Outcome và mailbox delivery status là hai tầng khác nhau

~~~text
Submission:
  ACCEPTED by provider A
        |
        v
Provider later:
  delivered / deferred / hard-bounced / complained
~~~

Đừng cập nhật `outbox.status=FAILED` chỉ vì một webhook `deferred` khi provider vẫn đang thử giao. Tách submission history với downstream delivery feedback và áp dụng event ordering/idempotency phù hợp.

## 6. Interface MailProviderAdapter và dữ liệu đầu vào

Một interface nội bộ có thể hỗ trợ cả SMTP và HTTP API:

~~~java
package com.example.mail.provider;

public interface MailProviderAdapter {

    String providerId();

    ProviderCapabilities capabilities();

    ProviderSubmissionResult submit(
            PreparedMailSubmission request);
}
~~~

`PreparedMailSubmission` là **một lần nộp mail đã qua routing và validation**. Nó không nhận lại thông tin từ một HTTP request chưa được authorize để tự chọn provider.

### 6.1. PreparedMailSubmission

Ví dụ Java 17 record:

~~~java
package com.example.mail.provider;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record PreparedMailSubmission(
        UUID deliveryId,
        UUID attemptId,
        String recipient,
        String fromAddress,
        String replyToAddress,
        String subject,
        String plainText,
        String htmlText,
        String idempotencyKey,
        List<AttachmentRef> attachments,
        Instant deadline) {

    public PreparedMailSubmission {
        if (deliveryId == null || attemptId == null
                || recipient == null || recipient.isBlank()
                || fromAddress == null || fromAddress.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required prepared mail data");
        }
        attachments = attachments == null
                ? List.of()
                : List.copyOf(attachments);
    }
}

public record AttachmentRef(
        String displayName,
        String contentType,
        String storageKey,
        String versionId,
        long contentLength) {
}
~~~

Những record cần ở tệp Java riêng nếu đều khai báo `public`. Constructor trên chỉ kiểm tra một số dữ liệu cơ bản; production còn cần validate email addresses bằng parser thích hợp, kiểm tra header injection, authorized recipient/tenant, sender identity, MIME content, max size, attachment access và business deadline.

### 6.2. Không truyền InputStream đang mở qua queue

Nếu gửi bất đồng bộ và có retry, command không nên giữ `InputStream`, `MimeMessage` hoặc `MultipartFile` từ request HTTP:

~~~text
HTTP request uploads file
           |
           v
Secure storage
  object key + immutable version + checksum
           |
           v
Outbox contains attachment reference
           |
           v
Worker resolves source at send attempt
~~~

Stream và file tạm theo scope request không bền qua process restart. `AttachmentRef` cần chỉ tới nội dung **còn hiệu lực và đọc lại được** trong thời hạn attempt/retry. Nếu file lớn, ưu tiên `FileSystemResource` từ snapshot bất biến hoặc một `InputStreamSource` mở stream mới trên mỗi lần đọc; không materialize toàn bộ file vào heap chỉ để truyền qua adapter.

### 6.3. ProviderCapabilities

~~~java
package com.example.mail.provider;

import java.util.Set;

public record ProviderCapabilities(
        String providerId,
        Set<String> allowedRegions,
        Set<String> allowedMailCategories,
        Set<String> verifiedSendingIdentityIds,
        long maxMessageBytes,
        int maxRecipientsPerSubmission,
        boolean supportsIdempotentSubmit,
        boolean hasDeliveryFeedback) {
}
~~~

Các capability do vận hành/adapter thiết lập **theo contract thật** của provider. Đừng suy từ hostname `smtp-eu.example.net` rằng dữ liệu luôn được xử lý/lưu trong EU. Region approval phải căn cứ chính sách và hợp đồng xử lý dữ liệu thực tế, bao gồm logs, backup, webhook và subprocessors nếu áp dụng.

### 6.4. Không nên cố che hết khác biệt provider

Một abstraction dễ gây hiểu nhầm:

~~~java
boolean sendEmail(String to, String subject, byte[] bytes);
~~~

Nó không thể biểu diễn:

- HTTP 202 accepted nhưng chưa delivered.
- SMTP timeout sau DATA, kết quả UNKNOWN.
- Partial recipient failures.
- Provider API idempotency key và lifetime.
- Feedback event correlation.
- Provider bị từ chối do From identity chưa verify.
- Quota, attachment size và giới hạn vùng.

Adapter có thể thống nhất **đầu vào và outcome chính**, nhưng vẫn cần metadata/capability riêng có kiểm soát.

### 6.5. Định danh recipient và gửi theo từng delivery

Một `PreparedMailSubmission` nên đại diện cho **một recipient** khi ứng dụng cần tracking/fallback chính xác. Với message có nhiều địa chỉ:

~~~text
one MIME:
  To A, B, C
  SMTP relay accepts A, rejects B, defers C
~~~

Kết quả không còn là một boolean đơn giản. Spring Mail/Jakarta Mail có thể cung cấp thông tin recipient failure tùy exception/transport, nhưng adapter vẫn phải chuẩn hóa từng recipient. Cách đơn giản hơn cho notification quan trọng là tạo ba **delivery records** và xử lý độc lập theo recipient.

## 7. SMTP provider adapter bằng JavaMailSender

Một SMTP adapter dùng `org.springframework.mail.javamail.JavaMailSender` có thể tách đường SMTP khỏi domain. Tầng cấu hình tạo **một sender cho mỗi provider/identity phù hợp**, không thay host/credential trên singleton trước từng lần gửi.

### 7.1. Skeleton SMTP adapter

~~~java
package com.example.mail.provider.smtp;

import java.time.Clock;
import java.util.Objects;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import com.example.mail.provider.MailProviderAdapter;
import com.example.mail.provider.PreparedMailSubmission;
import com.example.mail.provider.ProviderCapabilities;
import com.example.mail.provider.ProviderSubmissionResult;
import com.example.mail.provider.RejectionKind;
import com.example.mail.provider.SubmissionOutcome;

public final class SmtpMailProviderAdapter
        implements MailProviderAdapter {

    private final String id;
    private final JavaMailSender sender;
    private final ProviderCapabilities capabilities;
    private final Clock clock;

    public SmtpMailProviderAdapter(
            String id,
            JavaMailSender sender,
            ProviderCapabilities capabilities,
            Clock clock) {
        this.id = Objects.requireNonNull(id);
        this.sender = Objects.requireNonNull(sender);
        this.capabilities = Objects.requireNonNull(capabilities);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public String providerId() {
        return id;
    }

    @Override
    public ProviderCapabilities capabilities() {
        return capabilities;
    }

    @Override
    public ProviderSubmissionResult submit(
            PreparedMailSubmission request) {

        if (request.deadline() != null
                && !clock.instant().isBefore(request.deadline())) {
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.DEFINITE_REJECTED,
                    RejectionKind.POLICY,
                    "DELIVERY_DEADLINE_EXPIRED",
                    null,
                    clock.instant());
        }

        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom(request.fromAddress());
            helper.setTo(request.recipient());
            if (request.replyToAddress() != null) {
                helper.setReplyTo(request.replyToAddress());
            }
            helper.setSubject(request.subject());

            if (request.htmlText() != null) {
                helper.setText(
                        request.plainText() == null
                                ? ""
                                : request.plainText(),
                        request.htmlText());
            } else {
                helper.setText(
                        request.plainText() == null
                                ? ""
                                : request.plainText());
            }

            // Bản tối thiểu chỉ hỗ trợ text/html không attachment.
            // Attachment adapter cần dùng multipart=true và
            // attach resource đã resolve theo storageKey/versionId.
            if (!request.attachments().isEmpty()) {
                return new ProviderSubmissionResult(
                        id,
                        SubmissionOutcome.DEFINITE_REJECTED,
                        RejectionKind.POLICY,
                        "ATTACHMENT_HANDLER_NOT_CONFIGURED",
                        null,
                        clock.instant());
            }

            sender.send(message);
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.ACCEPTED,
                    null,
                    "SMTP_ACCEPTED",
                    null,
                    clock.instant());
        } catch (MessagingException ex) {
            // MIME build failed before calling send.
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.DEFINITE_REJECTED,
                    RejectionKind.PERMANENT,
                    "MIME_PREPARATION_FAILED",
                    null,
                    clock.instant());
        } catch (MailException ex) {
            // A generic MailException alone is insufficient to
            // prove whether the relay accepted DATA.
            return new ProviderSubmissionResult(
                    id,
                    SubmissionOutcome.UNKNOWN,
                    RejectionKind.UNCLASSIFIED,
                    "SMTP_OUTCOME_UNCLASSIFIED",
                    null,
                    clock.instant());
        }
    }
}
~~~

**Đây là minh họa về contract và phân loại an toàn**, không phải SMTP classifier production hoàn chỉnh. Khối `catch(MessagingException)` bao lỗi tạo MIME *trước* `send` trong đoạn code này; nếu một ứng dụng đưa các operation sau submission vào cùng `try`, không được kết luận mọi `MessagingException` là pre-send. `MailException` từ `send` được xử lý bảo thủ là `UNKNOWN` cho tới khi có classifier đáng tin theo cause/protocol stage.

### 7.2. Tạo MIME với attachment cần multipart

Một adapter production nên xây dựng MIME sau khi đã resolve nguồn attachment:

~~~java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom(identity.fromAddress());
helper.setTo(request.recipient());
helper.setSubject(request.subject());
helper.setText(request.plainText(), request.htmlText());

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(immutableInvoicePath),
        "application/pdf");

sender.send(message);
~~~

`FileSystemResource` cho phép đọc file khi MIME serialization cần, tránh chủ động gọi `Files.readAllBytes`. File phải tồn tại và không thay đổi tới khi `send` hoàn tất; với job async, không xóa file tạm ở scope request trước khi worker gửi.

Với nguồn remote, `InputStreamSource.getInputStream()` phải mở **stream mới mỗi lần**, vì Jakarta Mail có thể đọc nhiều lần. Một `InputStreamResource` bọc stream single-use thường không phù hợp cho attachment lớn cần đọc lại.

### 7.3. Mỗi adapter có cấu hình SMTP riêng

Ví dụ factory cho một SMTP endpoint:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost(smtpHost);
sender.setPort(587);
sender.setUsername(smtpUser);
sender.setPassword(smtpPassword);
sender.setDefaultEncoding("UTF-8");

Properties props = new Properties();
props.setProperty("mail.smtp.auth", "true");
props.setProperty("mail.smtp.starttls.enable", "true");
props.setProperty("mail.smtp.starttls.required", "true");
props.setProperty("mail.smtp.ssl.checkserveridentity", "true");
props.setProperty("mail.smtp.connectiontimeout", "5000");
props.setProperty("mail.smtp.timeout", "15000");
props.setProperty("mail.smtp.writetimeout", "20000");
sender.setJavaMailProperties(props);
~~~

Các timeout tính bằng millisecond; giá trị chỉ minh họa. Với SMTP implicit TLS (thường port 465), cần cấu hình `mail.smtp.ssl.enable` và endpoint đúng. Không tắt certificate/hostname verification trên production chỉ để tránh một lỗi cấu hình.

Credentials phải lấy từ secret manager/runtime configuration, không ghi trong log. Với provider dùng OAuth2, cần cơ chế xác thực tương ứng thay vì mặc định password.

### 7.4. Không thay host/password trong mỗi request

Đoạn sau nguy hiểm với multi-thread:

~~~java
// Không nên: singleton sender được nhiều worker chia sẻ.
sender.setHost(selectedProvider.host());
sender.setUsername(selectedProvider.username());
sender.setPassword(selectedProvider.password());
sender.send(message);
~~~

Worker A và B có thể thay cấu hình xen kẽ, khiến cùng message dùng sai endpoint hoặc credential. Tạo sender/adapter riêng theo provider identity, cấu hình một lần, sau đó tra qua registry.

### 7.5. Vì sao SMTP adapter không trả providerMessageId?

`JavaMailSender.send` không có API chung trả về **ID submission do provider cấp**. MIME `Message-ID` có thể được tạo/lưu trên message để truy vết, nhưng không phải provider ID và không bảo đảm deduplication. Một số nhà cung cấp có thể thêm header, lưu log hoặc cung cấp feedback API; adapter chỉ điền `providerMessageId` khi có bằng chứng từ hợp đồng cụ thể.

## 8. HTTP email API adapter: đặc điểm khác SMTP

Một provider có thể nhận JSON qua HTTPS, ví dụ:

~~~text
POST /v1/messages
Authorization: Bearer <secret>
Idempotency-Key: <stable-business-key>   [only if supported]
Content-Type: application/json

{
  "from": "...",
  "to": ["..."],
  "subject": "...",
  "html": "..."
}
~~~

Đây là **mẫu khái niệm**, không phải endpoint hay schema của một hãng xác định. Cần tham chiếu tài liệu API chính thức của từng nhà cung cấp khi triển khai adapter.

### 8.1. Transport client abstraction

Để test được mà không phụ thuộc SDK vendor, có thể tạo:

~~~java
package com.example.mail.provider.http;

import java.util.Map;

public interface ProviderHttpClient {

    ProviderHttpResponse postMail(
            String providerId,
            PreparedHttpMailRequest request);
}

public record PreparedHttpMailRequest(
        String from,
        String to,
        String subject,
        String html,
        String text,
        String idempotencyKey) {
}

public record ProviderHttpResponse(
        int statusCode,
        String safeProviderCode,
        String providerMessageId,
        Map<String, String> allowedMetadata) {
}
~~~

`ProviderHttpClient` là API **do ứng dụng tự định nghĩa**. Khi viết client thực, cần:

- TLS và hostname validation.
- Credential per-provider account.
- Connection/read/write timeout.
- Giới hạn response bytes.
- Chính sách retry của HTTP client **không tự động gửi lại POST** khi kết quả mơ hồ.
- Xử lý 429/`Retry-After` theo hợp đồng provider.
- Kiểm tra 2xx nghĩa gì: `202 Accepted` có thể chỉ là queue accepted.
- Không log request body hoặc bearer token.

### 8.2. Không gom mọi HTTP 5xx thành “chắc chắn chưa gửi”

Giả sử client POST đã tới server, server tạo submission nhưng fail khi phản hồi:

~~~text
Client -> Provider: POST /messages
Provider: creates submission ID P1
Provider -> Client: timeout / connection reset
~~~

Đây là `UNKNOWN` nếu không có idempotency/reconciliation chứng minh kết quả. Một HTTP 502 từ proxy cũng không tự nói upstream đã tạo job hay chưa. Tương tự SMTP, adapter cần phân biệt:

| Kết quả HTTP | Ý nghĩa an toàn |
| --- | --- |
| 200/201/202 theo contract | Provider accepted submission/request; chưa chắc đã giao inbox |
| 400 validation xác định | Có thể `DEFINITE_REJECTED` nếu API cam kết không tiếp nhận |
| 401/403 | Cấu hình quyền/credential lỗi, không blind retry |
| 429 | Capacity/throttling; có thể retry theo policy và provider semantics |
| 5xx | Có thể tạm thời nhưng submission outcome có thể UNKNOWN |
| Network timeout/reset sau khi POST | UNKNOWN trừ khi có idempotency/reconcile |

Không dùng `if (status >= 500) fallback(B)` như một quy tắc tuyệt đối.

### 8.3. Khung adapter HTTP tối thiểu

~~~java
package com.example.mail.provider.http;

import java.time.Clock;

public final class HttpApiMailProviderAdapter
        implements MailProviderAdapter {

    private final String providerId;
    private final ProviderHttpClient client;
    private final ProviderCapabilities capabilities;
    private final Clock clock;

    public HttpApiMailProviderAdapter(
            String providerId,
            ProviderHttpClient client,
            ProviderCapabilities capabilities,
            Clock clock) {
        this.providerId = providerId;
        this.client = client;
        this.capabilities = capabilities;
        this.clock = clock;
    }

    @Override
    public String providerId() {
        return providerId;
    }

    @Override
    public ProviderCapabilities capabilities() {
        return capabilities;
    }

    @Override
    public ProviderSubmissionResult submit(
            PreparedMailSubmission mail) {

        PreparedHttpMailRequest payload =
                new PreparedHttpMailRequest(
                        mail.fromAddress(),
                        mail.recipient(),
                        mail.subject(),
                        mail.htmlText(),
                        mail.plainText(),
                        capabilities.supportsIdempotentSubmit()
                                ? mail.idempotencyKey()
                                : null);

        try {
            ProviderHttpResponse response =
                    client.postMail(providerId, payload);

            if (response.statusCode() == 202) {
                return new ProviderSubmissionResult(
                        providerId,
                        SubmissionOutcome.ACCEPTED,
                        null,
                        "HTTP_ACCEPTED",
                        response.providerMessageId(),
                        clock.instant());
            }

            // Các status còn lại bắt buộc phải map
            // theo hợp đồng API provider cụ thể.
            return new ProviderSubmissionResult(
                    providerId,
                    SubmissionOutcome.UNKNOWN,
                    RejectionKind.UNCLASSIFIED,
                    "HTTP_UNMAPPED_RESPONSE",
                    response.providerMessageId(),
                    clock.instant());
        } catch (RuntimeException ex) {
            // Không khẳng định provider chưa nhận POST.
            return new ProviderSubmissionResult(
                    providerId,
                    SubmissionOutcome.UNKNOWN,
                    RejectionKind.UNCLASSIFIED,
                    "HTTP_OUTCOME_UNCLASSIFIED",
                    null,
                    clock.instant());
        }
    }
}
~~~

Đoạn code dùng `202` làm **ví dụ cho một hợp đồng giả định**. Khi áp dụng thực tế cần thêm validated request, timeout classification, vendor-specific 2xx/error bodies, attachment handling, idempotency semantics và security policy. Không copy chung một mã `HTTP_UNMAPPED_RESPONSE` làm quyết định retry cuối cùng mà không có adapter chuyên biệt.

### 8.4. HTTP API và SMTP có thể cùng nằm trong registry

Sử dụng một interface không có nghĩa mọi adapter cùng hành vi. `capabilities.supportsIdempotentSubmit()` là tín hiệu quan trọng cho orchestrator: retry cùng provider qua API có idempotency key có thể an toàn hơn retry SMTP khi outcome UNKNOWN, **nếu** key còn hiệu lực và provider bảo đảm hành vi theo hợp đồng.

## 9. Provider registry: quản lý adapter theo định danh ổn định

Khi có nhiều provider, tránh truyền adapter cụ thể vào mỗi service nghiệp vụ:

~~~java
// Khó mở rộng:
public OrderService(SmtpProviderA a, HttpProviderB b) {
    ...
}
~~~

Thay vào đó, một registry ánh xạ `providerId` đến adapter:

~~~java
package com.example.mail.provider;

import java.util.Collection;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class MailProviderRegistry {

    private final Map<String, MailProviderAdapter> byId;

    public MailProviderRegistry(
            Collection<MailProviderAdapter> adapters) {

        this.byId = Map.copyOf(
                adapters.stream().collect(Collectors.toMap(
                        MailProviderAdapter::providerId,
                        Function.identity())));

        if (byId.isEmpty()) {
            throw new IllegalStateException(
                    "No configured mail providers");
        }
    }

    public MailProviderAdapter require(String providerId) {
        MailProviderAdapter adapter = byId.get(providerId);
        if (adapter == null) {
            throw new IllegalArgumentException(
                    "Unknown providerId");
        }
        return adapter;
    }
}
~~~

`Collectors.toMap` không cho phép cùng một provider ID xuất hiện hai lần nếu không có merge function, nhờ đó phát hiện cấu hình trùng khi khởi tạo. `Map.copyOf` tránh để các worker vô tình sửa registry bằng một mutable map chia sẻ.

### 9.1. Bean registry với Spring

~~~java
@Configuration
public class ProviderRegistryConfiguration {

    @Bean
    MailProviderRegistry mailProviderRegistry(
            List<MailProviderAdapter> adapters) {
        return new MailProviderRegistry(adapters);
    }
}
~~~

Các adapter có thể là bean cấu hình riêng. Nếu có vài chục endpoint, tạo adapter từ `@ConfigurationProperties` hoặc một config service versioned có validation. Với credential rotation, cân nhắc **thay adapter/sender instance theo phiên bản config** và xử lý in-flight attempts; không mutate nhiều field trên sender đồng thời.

### 9.2. Tách provider ID khỏi identity ID

~~~text
providerId = smtp-eu-a
identityId = eu-transactional
From       = receipts@example.com
DKIM d=    = example.com
~~~

Một provider có thể phục vụ nhiều sending identities; một identity có thể được verify trên nhiều provider. Nếu một endpoint SMTP dùng envelope sender hoặc account cấu hình riêng theo identity, có thể cần adapter instance/transport configuration riêng cho từng cặp provider–identity.

Không cho public API nhận `providerId` rồi truy cập credential của provider bất kỳ. Provider selection phải đi qua chính sách nội bộ đã kiểm tra tenant, region và category.

## 10. Routing policy: tạo tập provider được phép

Một chính sách production không nên dựa vào một chuỗi if/else chỉ xét provider health. Trước tiên xác định **candidate allowlist** theo các điều kiện được phê duyệt.

### 10.1. Ví dụ ma trận

| Khu vực | Loại email | Primary | Approved secondary | Lưu ý |
| --- | --- | --- | --- | --- |
| VN | SECURITY | `smtp-vn-security-a` | `smtp-vn-security-b` | Ưu tiên deadline, quota riêng |
| VN | TRANSACTIONAL | `smtp-vn-tx-a` | `api-vn-tx-b` | Cùng sender identity đã verify |
| VN | MARKETING | `api-vn-bulk-a` | Không mặc định | Consent, campaign window |
| EU | SECURITY | `smtp-eu-security-a` | `api-eu-security-b` | Residency policy trước health |
| EU | TRANSACTIONAL | `api-eu-tx-a` | `smtp-eu-tx-b` | Size, DKIM, feedback support |
| EU | MARKETING | `api-eu-bulk-a` | `api-eu-bulk-b` | Quota/bounce suppression |

Các tên trên là **logical IDs minh họa**, không xác nhận vị trí xử lý thật của nhà cung cấp nào. Chỉ cho provider vào bảng sau khi được đánh giá về hợp đồng, sender identity, region/data policy, API/SMTP limits và khả năng vận hành.

### 10.2. Model policy

~~~java
package com.example.mail.routing;

import java.util.List;

public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}

public enum DeliveryRegion {
    VN,
    EU,
    OTHER
}

public record RoutingContext(
        String tenantId,
        MailCategory category,
        DeliveryRegion region,
        String sendingIdentityId,
        long estimatedMessageBytes) {
}

public record ApprovedRoute(
        String policyVersion,
        String primaryProviderId,
        List<String> approvedFallbackIds,
        String reason) {
}
~~~

Java yêu cầu mỗi `public` top-level type ở file tương ứng. Đây là model ứng dụng; route có thể bổ sung priority, cost tier, feedback requirement, tenant/account restrictions và kênh gửi.

### 10.3. Phân biệt region từ dữ liệu đáng tin cậy

Không dùng:

~~~text
recipient.endsWith(".eu") -> route EU
recipient.endsWith(".com") -> route US
~~~

Domain email không chứng minh vị trí người nhận. Nguồn dữ liệu phù hợp có thể là residency policy của tenant, địa chỉ đã xác minh, vùng deployment hoặc hợp đồng khách hàng.

Nếu region không rõ hoặc hai nguồn mâu thuẫn, đưa delivery vào trạng thái cần xác minh hoặc dùng default **đã được phê duyệt**; không tự chọn provider rẻ nhất hoặc khỏe nhất ngoài phạm vi dữ liệu.

### 10.4. Candidate eligibility filter

Một provider chỉ được xem là có thể chọn nếu:

~~~text
providerId is in approved route policy
AND tenant is permitted to use provider/account
AND region is allowed for the full data path
AND category is supported
AND sending identity is verified
AND required TLS/auth/capabilities are available
AND estimated message size <= allowed provider limit
AND recipient count is within limit
AND provider has capacity and acceptable health
~~~

Với SMTP size, đầu vào 10 MiB có thể tạo MIME message lớn hơn đáng kể vì Base64, headers và multipart boundaries. Cần ước lượng kích thước **sau encoding** và có ngưỡng an toàn, không chỉ so size tệp nhị phân với quota tổng message.

### 10.5. Thứ tự ưu tiên của policy

Một thứ tự minh họa:

~~~text
1. Validate business command and recipient
2. Check consent, suppression, deadline
3. Resolve trusted region, category, tenant
4. Validate identity and contractual eligibility
5. Build approved provider candidate set
6. Apply capability/size constraints
7. Consider circuit, quota, capacity and priority
8. Select provider and persist decision
9. Call selected adapter
~~~

Đừng chọn provider theo latency trước, rồi phát hiện nó không được phép xử lý dữ liệu hoặc không verify From domain.

## 11. Chiến lược fallback an toàn

Không nên khai báo fallback là `catch(anyException) => try secondary`. Một policy cần đồng thời trả lời:

1. **Provider secondary có được phép cho delivery này không?**
2. **Attempt trước chắc chắn không được accepted hay chưa?**
3. **Lỗi có phải loại có ích khi đổi provider không?**
4. **Delivery còn trong deadline, chưa suppress và còn quota không?**
5. **Số attempt còn lại bao nhiêu, có risk duplicate không?**
6. **Adapter secondary có hỗ trợ sender identity/attachment đúng không?**

### 11.1. Decision matrix

| Kết quả primary | Loại lỗi | Fallback ngay? | Hành vi đề xuất |
| --- | --- | --- | --- |
| Không kết nối được, chắc chắn chưa submit | Transient network | Có thể | Chọn secondary hợp lệ, ghi attempt mới |
| Circuit breaker đang open *trước* khi gọi primary | No submission | Có thể | Chọn secondary trong allowlist |
| Provider hết quota trước submission | Capacity | Có thể | Secondary còn quota hoặc schedule |
| Recipient bị reject vĩnh viễn | Permanent | Không mặc định | FAILED/suppression theo policy |
| Sender identity chưa verify | Policy/config | Không tự động | Sửa cấu hình; chỉ B nếu B hợp lệ và policy cho phép |
| Message vượt provider size limit | Permanent/capability | Không mù quáng | Chọn B chỉ khi B hỗ trợ cùng nội dung và route hợp lệ |
| SMTP accepted | Accepted | Không | Ghi accepted, chờ feedback |
| Timeout sau SMTP DATA | Unknown | Không mù quáng | Reconcile, xem duplicate tolerance |
| HTTP POST timeout | Unknown | Không mù quáng | Nếu có idempotency contract: retry cùng provider/key hoặc query status |
| DB ghi trạng thái accepted thất bại | Unknown local state | Không | Reconcile trước resend |
| SMTP auth fail hàng loạt | Configuration | Không mặc định | Alert, rotate secret/credential |

### 11.2. Dừng đúng khi không có secondary hợp lệ

~~~text
Primary A unavailable
        |
        v
Approved secondary B?
       / \
     Yes  No
      |    |
      v    v
Eligible? HOLD / RETRY / alert
     / \
   Yes No
    |   |
    v   v
 Check prior  NO_ELIGIBLE_PROVIDER
 outcome      (not cross-region fallback)
    |
    v
 Safe to resubmit?
    |          |
   Yes         No
    |          |
    v          v
 Attempt B   UNKNOWN / reconciliation
~~~

**Fail-closed không nhất thiết là sự cố bảo mật:** nếu delivery có yêu cầu xử lý tại EU mà tất cả provider EU đều unavailable, việc tạm giữ delivery còn an toàn hơn tự chuyển sang một nhà cung cấp ngoài vùng không được phê duyệt.

### 11.3. Fallback chỉ khi có bằng chứng pre-submission

Không phải mọi timeout đều UNKNOWN: connect refused hoặc circuit open **trước khi gửi payload** có thể có bằng chứng chưa submit. Nhưng adapter phải cung cấp bằng chứng hoặc phân loại đáng tin; nếu chỉ bắt `MailSendException` chung mà không có stage, mặc định nên xử lý thận trọng.

Một API adapter có thể cung cấp `FailureStage`:

~~~java
public enum SubmissionStage {
    PREPARE,
    CONNECT,
    AUTHENTICATE,
    ENVELOPE,
    DATA,
    PROVIDER_RESPONSE,
    PERSIST_RESULT,
    UNDETERMINED
}
~~~

Stage chỉ hữu ích nếu thực sự quan sát được từ transport/SDK. Không gán `CONNECT` cho mọi `IOException` chỉ để mở đường fallback.

### 11.4. Không đổi provider để bỏ qua suppression

Nếu A từ chối vì complaint/suppression, việc gửi qua B không phải “khắc phục outage”. Cần chính sách suppression **ở tầng ứng dụng**, bao phủ toàn bộ các provider mà cùng recipient/tenant có thể sử dụng.

Với marketing, kiểm tra consent/unsubscribe trước chọn provider. Với email giao dịch/bảo mật, cũng cần chính sách riêng cho địa chỉ không hợp lệ, blocklist hoặc regulatory restrictions. Một suppression event từ A có thể phải ảnh hưởng B.

### 11.5. Pin route hay re-evaluate ở mỗi attempt?

Hai mô hình:

**Pin provider/route trên delivery:**

~~~text
delivery D1 -> route V1 -> provider A
retry #2   -> same provider A
~~~

Ưu điểm: audit đơn giản; tránh đổi provider ngoài ý muốn. Nhược điểm: phải có cơ chế fallback explicit khi A outage lâu.

**Re-evaluate ở mỗi attempt:**

~~~text
delivery D1 -> attempt #1 -> route V1, provider A
retry #2    -> route V2 -> provider B
~~~

Ưu điểm: phục hồi khi config/quota thay đổi. Nhược điểm: phải ghi **policy version và reason theo từng attempt**, và bảo đảm route mới vẫn tuân thủ consent, region, identity. Không random lại provider mà không giải thích.

### 11.6. Failover vs failback

**Failover** chuyển traffic từ A sang B vì A không sử dụng được. **Failback** đưa traffic mới trở lại A sau phục hồi. Không nên chuyển tới lui liên tục (flapping) khi health chập chờn:

- Dùng cooldown và health window ổn định.
- Chỉ đưa một phần lưu lượng canary về primary trước.
- Đảm bảo quota đã hồi phục.
- Giữ webhook/feedback ingestion của provider B cho các email đã submit trước failback.
- Không đổi provider của những delivery đã `ACCEPTED` chỉ vì primary vừa khỏe trở lại.

## 12. Attempt planner và policy engine

Một thành phần riêng nên quyết định việc chọn provider cho **một attempt mới**. Nó không thực hiện network IO và có thể được test bằng table-driven inputs.

Ví dụ dữ liệu:

~~~java
public record PreviousAttempt(
        String providerId,
        SubmissionOutcome outcome,
        RejectionKind rejectionKind,
        SubmissionStage lastObservedStage) {
}

public record AttemptDecision(
        String providerId,
        String policyVersion,
        String reason) {
}
~~~

### 12.1. Skeleton logic có thể kiểm thử

~~~java
public final class FallbackPlanner {

    public AttemptDecision selectNext(
            ApprovedRoute route,
            PreviousAttempt previous,
            Set<String> currentlyEligible,
            int attemptsRemaining) {

        if (attemptsRemaining <= 0) {
            throw new IllegalStateException("Attempts exhausted");
        }

        if (previous == null) {
            String primary = route.primaryProviderId();
            if (currentlyEligible.contains(primary)) {
                return new AttemptDecision(
                        primary, route.policyVersion(), "PRIMARY");
            }

            // Primary was not attempted; eligible secondary allowed.
            return firstEligibleFallback(route, currentlyEligible);
        }

        if (previous.outcome() == SubmissionOutcome.ACCEPTED
                || previous.outcome() == SubmissionOutcome.UNKNOWN) {
            throw new IllegalStateException(
                    "Cannot blindly resubmit ambiguous or accepted mail");
        }

        if (previous.rejectionKind() == RejectionKind.PERMANENT
                || previous.rejectionKind() == RejectionKind.POLICY) {
            throw new IllegalStateException(
                    "Permanent or policy rejection blocks fallback");
        }

        return firstEligibleFallback(route, currentlyEligible);
    }

    private AttemptDecision firstEligibleFallback(
            ApprovedRoute route,
            Set<String> eligible) {

        return route.approvedFallbackIds().stream()
                .filter(eligible::contains)
                .findFirst()
                .map(id -> new AttemptDecision(
                        id, route.policyVersion(), "APPROVED_FALLBACK"))
                .orElseThrow(() -> new IllegalStateException(
                        "No eligible fallback provider"));
    }
}
~~~

Đây là **policy skeleton rút gọn**; còn thiếu kiểm tra retry deadline, loại lỗi transient có thực sự cải thiện khi đổi provider, quota, circuit, tenant, identity, idempotency guarantee và SMTP stage. `currentlyEligible` phải là tập đã được **router kiểm tra policy**, không phải danh sách do caller/HTTP request tự nhập.

Với hệ thống lớn, nên dùng kiểu kết quả `HOLD`, `RETRY_SAME`, `FALLBACK`, `FAILED`, `RECONCILE` thay vì throw `IllegalStateException` cho mọi trường hợp; exception ở trên chỉ giúp ví dụ tập trung vào việc **không chọn B cho ACCEPTED/UNKNOWN**.

### 12.2. Không retry vô hạn ở tầng SDK

Nếu HTTP SDK đã tự retry POST ba lần, Spring Retry advice retry hai lần, rồi outbox worker retry năm lần, một delivery có thể phát ra số submission nhiều hơn dự kiến. Cần định nghĩa:

~~~text
durable_attempt_count = number of provider submission attempts
network_retries_per_attempt = tightly controlled
max_attempts = global business policy
~~~

Nếu SDK ẩn các HTTP retries, phải xem tài liệu để tắt hoặc điều chỉnh; nếu không, audit số attempt ở DB có thể không khớp với số request provider thực nhận.

## 13. Transactional outbox và lịch sử từng provider attempt

Fallback là một quyết định quan trọng đối với tính đúng đắn. Nếu provider đầu tiên đã được gọi nhưng chỉ ghi route sau khi `send(...)` trả về, một crash có thể xóa mất bằng chứng đã nộp thư qua provider nào.

Với email quan trọng, nên dùng **durable outbox** kết hợp **attempt history**:

~~~text
Business service
      |
      v
BEGIN DB transaction
   - save business change
   - insert outbox delivery PENDING
COMMIT
      |
      v
Worker claims due delivery
      |
      v
Resolve policy + select eligible provider
      |
      v
BEGIN DB transaction
   - record provider attempt STARTED
   - set delivery PROCESSING + claim token
COMMIT
      |
      v
Provider adapter.submit(...)
      |
      v
BEGIN DB transaction
   - record normalized outcome
   - mark ACCEPTED / RETRY / FAILED / UNKNOWN
COMMIT
~~~

Network call nằm **ngoài transaction giữ row lock**; worker dùng lease/claim token để bảo vệ state khi xử lý lâu.

### 13.1. Schema delivery

~~~sql
CREATE TABLE mail_delivery (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_key VARCHAR(180) NOT NULL,
    recipient_address VARCHAR(320) NOT NULL,
    category VARCHAR(30) NOT NULL,
    data_region VARCHAR(30) NOT NULL,
    identity_id VARCHAR(100) NOT NULL,
    template_key VARCHAR(150) NOT NULL,
    template_version VARCHAR(80),
    body_reference VARCHAR(500),
    attachment_manifest_reference VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at TIMESTAMPTZ,
    selected_provider_id VARCHAR(120),
    route_policy_version VARCHAR(100),
    claim_token UUID,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    smtp_accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, business_key)
);

CREATE INDEX ix_mail_delivery_due
    ON mail_delivery(status, next_attempt_at);

CREATE INDEX ix_mail_delivery_lease
    ON mail_delivery(status, lease_until);
~~~

`business_key` đại diện cho **ý định gửi một delivery** được tạo từ nghiệp vụ, phải được thiết kế có scope theo recipient/operation. Nếu cùng một đơn hàng cần gửi hai thông báo hợp lệ khác nhau, key phải phân biệt chúng; nếu worker retry cùng thông báo, key phải ổn định.

Các tham chiếu body/attachment phải trỏ đến dữ liệu có thể truy xuất bền vững khi worker restart; nếu chứa PII, cần mã hóa, giới hạn quyền và retention. Đừng lưu credential hoặc secret vendor trong outbox.

### 13.2. Schema attempt history

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL REFERENCES mail_delivery(id),
    attempt_no INT NOT NULL,
    provider_id VARCHAR(120) NOT NULL,
    sending_identity_id VARCHAR(120) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    selection_reason VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(250),
    outcome VARCHAR(30) NOT NULL DEFAULT 'STARTED',
    rejection_kind VARCHAR(40),
    failure_stage VARCHAR(60),
    safe_error_code VARCHAR(100),
    provider_message_id VARCHAR(250),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(delivery_id, attempt_no)
);

CREATE INDEX ix_mail_attempt_provider
    ON mail_delivery_attempt(provider_id, started_at DESC);
~~~

Với mỗi attempt, cần biết:

- Đã chọn provider nào, bằng route version nào.
- Có đủ điều kiện fallback không, và lý do.
- Đã gọi network chưa hay bị từ chối ở preflight.
- Trạng thái submission: `STARTED`, `ACCEPTED`, `DEFINITE_REJECTED`, `UNKNOWN`.
- Có provider message ID theo contract thật không.
- Lỗi xảy ra ở stage nào, có mã lỗi an toàn gì.

Nếu system cần phân biệt “attempt được chọn nhưng chưa gọi provider” với “đã bắt đầu gọi”, thêm trường `transport_started_at` hoặc state `PREPARED`/`IN_FLIGHT`. Điều này giúp đối soát crash:

~~~text
Record STARTED committed
    |
    +-- crash before HTTP/SMTP call
    |     -> no submission actually happened
    |
    +-- crash during HTTP/SMTP call
          -> submission may or may not have been accepted
~~~

Không thể chỉ nhìn database row `STARTED` sau crash và khẳng định provider đã nhận hay chưa.

### 13.3. Atomic claim

Ví dụ PostgreSQL:

~~~sql
WITH due AS (
    SELECT id
    FROM mail_delivery
    WHERE status IN ('PENDING', 'RETRY')
      AND next_attempt_at <= now()
      AND (deadline_at IS NULL OR deadline_at > now())
    ORDER BY next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_delivery AS m
SET status = 'PROCESSING',
    claim_token = :claim_token,
    lease_owner = :worker_id,
    lease_until = now() + INTERVAL '2 minutes',
    attempt_count = m.attempt_count + 1,
    updated_at = now()
FROM due
WHERE m.id = due.id
RETURNING m.id, m.attempt_count, m.tenant_id,
          m.data_region, m.category, m.identity_id;
~~~

Thực hiện claim trong một transaction ngắn, ghi attempt row với `attempt_no` vừa tăng, commit trước network call. `SKIP LOCKED` giúp tránh nhiều worker cùng claim một row đang bị khóa; cần index và concurrency policy phù hợp.

### 13.4. Fencing token khi lưu outcome

Sau khi adapter trả `ACCEPTED`:

~~~sql
UPDATE mail_delivery
SET status = 'ACCEPTED',
    smtp_accepted_at = now(),
    claim_token = NULL,
    lease_owner = NULL,
    lease_until = NULL,
    selected_provider_id = :provider_id,
    route_policy_version = :policy_version,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

Nếu update count bằng 0, worker có thể đã mất lease hoặc một worker khác đã reclaim. **Không cưỡng ép ghi đè row** chỉ vì lời gọi mạng trước đó thành công. Phải lưu/điều tra state conflict, vì email có thể đã được accepted.

Đối với attempt history, ghi kết quả và delivery state trong cùng transaction khi có thể. Với `UNKNOWN`, không đưa row trở lại `RETRY` như một thao tác mặc định; cần reconciliation hoặc retry strategy có cân nhắc rủi ro trùng.

### 13.5. Lease expiry có nghĩa gì?

~~~text
T0 worker A claims
T1 worker A starts SMTP send
T2 lease expires due to long timeout
T3 worker B claims same delivery
T4 worker A receives SMTP accepted
~~~

Fencing token ngăn A ghi đè state của B, nhưng **không tự ngăn hai lần gửi SMTP**. Cần:

- Worker concurrency/lease timeout phù hợp thời gian gửi lớn nhất.
- Heartbeat/lease extension có kiểm tra claim token.
- Không reclaim mù những message có attempt outcome không chắc chắn.
- Business idempotency và đối soát provider khi có khả năng.
- Giám sát số expired leases để điều chỉnh timeout/capacity.

### 13.6. Không giữ transaction mở qua network IO

Không nên:

~~~text
BEGIN transaction
  SELECT FOR UPDATE
  JavaMailSender.send (may take 30 seconds)
  UPDATE delivery
COMMIT
~~~

Cách này giữ connection/locks quá lâu, tăng deadlock và làm giảm khả năng scale. Thay bằng các transaction ngắn để claim và persist outcome, còn SMTP/API nằm ngoài.

## 14. Fallback là state transition được kiểm soát

Một sơ đồ trạng thái:

~~~text
PENDING
   |
   v
PROCESSING (attempt A)
   |
   +--> ACCEPTED --------------------> terminal submission success
   |
   +--> DEFINITE_REJECTED
   |        |
   |        +--> permanent/policy --> FAILED
   |        |
   |        +--> transient/capacity
   |                 |
   |                 v
   |              ROUTE_REEVALUATION
   |                 |
   |           +-----+------+
   |           |            |
   |           v            v
   |       eligible B      no eligible B
   |           |            |
   |           v            v
   |         RETRY        HOLD/RETRY/FAILED
   |           |
   |           v
   |      PROCESSING (attempt B)
   |
   +--> UNKNOWN ---------------------> RECONCILE/HOLD
~~~

Không tạo attempt B trong cùng một `catch` mà chưa có durable attempt record. Nếu JVM crash ngay sau khi A throw nhưng trước khi B send, database phải biết **attempt A đã xảy ra** và B có được lên lịch hay chưa.

### 14.1. Retry scheduling

Một policy minh họa:

\[
d_n=\min(d_{\mathrm{max}},d_0 2^{n-1})
\]

Với `d_0=30 giây`, max 15 phút và jitter:

| Attempt lỗi | Delay cơ sở trước attempt kế tiếp |
| --- | --- |
| 1 | 30 s |
| 2 | 60 s |
| 3 | 120 s |
| 4 | 240 s |
| 5 | Dừng nếu max_attempts=5 |

Đây không phải mặc định của Spring Mail. Loại email quyết định deadline: reset password có thể vô ích sau khi token hết hạn; newsletter có thể chờ đến campaign window tiếp theo.

### 14.2. Retry same provider hay fallback khác provider?

| Tình huống | Retry same | Fallback |
| --- | --- | --- |
| A tạm rate limit, B còn capacity và eligible | Có thể sau Retry-After | Có thể nếu outcome chắc chắn chưa accepted |
| DNS/connect A unavailable | Có thể sau backoff | Có thể chọn B ngay hoặc theo delay |
| B là provider cùng account/region nhưng quota chung | Có thể vô ích | Có thể không cải thiện |
| A invalid recipient | Không nên | Không nên |
| A timeout sau DATA | Có duplicate risk | Càng cần thận trọng |
| API A có idempotency token còn hiệu lực | Có thể retry cùng key | Chuyển B không hưởng idempotency token A |
| A đã ACCEPTED | Không | Không |

### 14.3. Retry-After không phải bảo đảm message chưa được tạo

Với HTTP provider, `429 Too Many Requests` thông thường là capacity response; nhưng vẫn phải tuân thủ hợp đồng endpoint, proxy và cách provider xử lý request. Đọc `Retry-After`, giới hạn tổng attempts và không tự động coi retry-eligible là fallback-safe trong mọi trường hợp.

## 15. Ranh giới idempotency và duplicate risk

Idempotency không phải một toggle đơn giản. Có nhiều cấp:

1. **Business idempotency:** cùng order event/recipient chỉ tạo một delivery intent.
2. **Outbox claim idempotency:** nhiều workers không cùng update một row.
3. **Provider submission idempotency:** lặp lại một API request không tạo nhiều submissions, *nếu provider hỗ trợ*.
4. **Recipient delivery uniqueness:** người nhận chỉ thấy một email; SMTP thuần **không có bảo đảm exactly-once**.
5. **Feedback event idempotency:** webhook redelivery không làm cập nhật trạng thái/suppression hai lần.

### 15.1. Idempotency key theo business operation

Ví dụ:

~~~text
tenant=T1
order=O42
recipient=U99
notification=ORDER_CONFIRMED
version=1

businessKey = "T1:O42:U99:ORDER_CONFIRMED:v1"
~~~

Đây là dạng minh họa. Không đặt số ID nhạy cảm hoặc raw email vào một header/log công khai; production có thể dùng UUID hoặc opaque/hash key được quản lý.

Nếu cùng đơn hàng cần gửi một notification khác sau đó, key phải khác. Nếu retry một delivery đã tạo, key phải giữ nguyên.

### 15.2. Adapter HTTP có idempotency

Nếu provider hỗ trợ, một HTTP adapter có thể gửi:

~~~text
Idempotency-Key: stable-key-for-delivery-D1
~~~

Khi timeout, **retry tới cùng account/provider với cùng key** có thể trả lại kết quả cũ thay vì tạo message mới. Tuy nhiên, chỉ an toàn trong phạm vi TTL và endpoint contract. Key này không tự dùng được khi chuyển sang provider B.

### 15.3. SMTP và Message-ID

MIME header:

~~~text
Message-ID: <opaque-delivery-D1@mail.example.com>
~~~

giúp tìm mail trong log hoặc thread, nhưng SMTP server không bắt buộc deduplicate cùng Message-ID. Một adapter cũng có thể không kiểm soát hoàn toàn header do library/relay tạo. Vì vậy không tuyên bố “cùng Message-ID = không thể gửi trùng”.

### 15.4. Unknown-state reconciliation

Một work item `UNKNOWN` nên có:

~~~text
deliveryId
attemptId
providerId
providerMessageId (if available)
idempotencyKey (if provider supports)
lastKnownStage
requestStartedAt
errorCode
reconciliationDeadline
~~~

Quy trình:

1. Kiểm tra adapter/provider có status lookup hoặc submission logs không.
2. Nếu biết chắc đã accepted, cập nhật submission state và đợi feedback.
3. Nếu biết chắc chưa accepted, có thể lên lịch retry/fallback.
4. Nếu vẫn UNKNOWN, quyết định theo business tolerance: chờ operator, retry cùng key theo contract, hoặc chấp nhận rủi ro duplicate có audit.

Không đồng nhất `UNKNOWN` với `FAILED` để dashboard “sạch”, và không tự động gửi lại tất cả `UNKNOWN` khi scheduler chạy.

## 16. Circuit breaker, rate limiter và bulkhead theo provider

Fallback chỉ hoạt động tốt nếu hệ thống **không tiếp tục dồn request** vào provider đang lỗi. Ba cơ chế thường đi cùng nhau:

- **Circuit breaker:** tạm thời không gọi một provider đang có tỷ lệ lỗi cao.
- **Rate limiter/quota manager:** hạn chế số message/recipient/request hoặc byte theo hợp đồng.
- **Bulkhead:** cô lập worker/connection capacity để một provider chậm không chiếm hết tài nguyên của các provider khác.

~~~text
Due mail delivery
        |
        v
Eligible candidates by policy
        |
        v
Per-provider circuit breaker
        |
        +--> OPEN -> do not call
        |
        v
Rate limiter / quota reservation
        |
        +--> No capacity -> schedule later or eligible alternative
        |
        v
Bulkhead / concurrency permit
        |
        +--> Exhausted -> backpressure
        |
        v
Adapter.submit(...)
        |
        v
Normalized outcome + metrics
~~~

### 16.1. Circuit breaker không phải bằng chứng email thất bại

Khi circuit của provider A mở, nghĩa là hệ thống **quyết định không thử gọi A** trong khoảng hiện tại. Một delivery mới có thể được route tới B vì A chưa được gọi, nếu B eligible. Không nên tăng `provider_submission_attempts` của A như thể đã có SMTP request, và không đánh dấu một email `FAILED` chỉ vì circuit open.

Nếu A mở circuit giữa các attempt, phải xem outcome của attempt cũ trước khi chọn B. Một attempt A đã `UNKNOWN` vẫn cần reconciliation; circuit open **không chứng minh** A chưa nhận message trước đó.

### 16.2. Cấu hình circuit theo loại lỗi

Không phải tất cả `4xx` hay `5xx` đều là provider outage:

| Lỗi | Có nên tính vào circuit provider? |
| --- | --- |
| Connect timeout/network failure | Có thể |
| SMTP relay 421 service unavailable | Có thể |
| HTTP 5xx tăng mạnh | Có thể, theo hợp đồng |
| Recipient invalid (SMTP 550 user unknown) | Không nên dùng để mở circuit chung |
| Template thiếu biến | Không phải lỗi provider |
| Attachment quá lớn | Là lỗi capability/policy |
| Credential sai toàn account | Cần xử lý config/alert, có thể disable route |
| Caller thiếu consent | Không liên quan provider health |

Nếu tính mọi invalid recipient vào circuit breaker, một chiến dịch gửi tới danh sách địa chỉ kém chất lượng có thể làm hệ thống nghĩ SMTP provider đang hỏng và chuyển traffic vô ích sang B.

### 16.3. Per-provider rate limit

Một provider có thể quy định:

~~~text
max 100 messages/minute
max 5 concurrent connections
max 20 MiB per MIME message
max 50 recipients per message
~~~

Các con số trên **chỉ minh họa**. Việc cho 20 worker cùng gọi `submit` không bảo đảm throughput tăng nếu provider có quota thấp.

Rate limiter cần phù hợp đơn vị giới hạn thực tế:

- Request per second.
- Recipient per minute.
- Email per account/day.
- Connection concurrency.
- Kích thước message.
- Mức tốc độ riêng cho region, domain hoặc dedicated pool.

Nếu cả primary và secondary cùng dùng **một account/quota ở tầng provider**, việc chuyển sang secondary hostname có thể không tăng capacity.

### 16.4. Reserved capacity cho email quan trọng

Hệ thống có 100 token gửi/phút nhưng campaign marketing có thể tạo 10.000 job. Nếu marketing dùng hết token, OTP/reset password sẽ trễ. Cần:

~~~text
Critical / security queue -> reserved capacity
Transactional queue       -> normal reserved / weighted
Marketing queue           -> bulk capacity, pausable
~~~

Tách queue mà không tách quota ở provider có thể chưa đủ. Có thể dùng account/IP pool riêng hoặc một limiter chung hiểu thứ tự ưu tiên, tùy provider.

### 16.5. Jitter chống retry storm

Khi SMTP outage, hàng nghìn delivery có thể cùng chuyển `RETRY`. Nếu tất cả retry sau đúng 30 giây, provider vừa phục hồi có thể bị dồn request ngay:

~~~text
Without jitter:
  10,000 jobs retry at 12:00:30

With jitter:
  jobs spread across permitted retry window
~~~

Áp dụng exponential backoff, random jitter có giới hạn và per-provider concurrency. Không để retry từ tầng SDK, circuit, worker và scheduler cộng dồn không kiểm soát.

## 17. Sender identity: không chỉ đổi endpoint SMTP

Một provider adapter thường có một hoặc nhiều **sending identities** được verify. Nếu fallback tới một provider chưa được cho phép gửi với `From`/DKIM domain của message, server có thể từ chối hoặc email thất bại SPF/DKIM/DMARC.

### 17.1. Các địa chỉ khác nhau

Một email có nhiều khái niệm:

| Trường | Vai trò |
| --- | --- |
| Header `From` | Danh tính người nhận nhìn thấy |
| `Reply-To` | Nơi người đọc trả lời |
| Envelope `MAIL FROM` | Đường nhận bounce/DSN và SPF identity |
| `Return-Path` | Thường được hệ nhận ghi dựa trên envelope sender |
| DKIM `d=` | Domain ký xác thực nội dung/header |
| Sender provider account | Credential/API key đã được cấp quyền gửi |

`MimeMessageHelper.setFrom(...)` đặt Header From, không bảo đảm SMTP envelope sender hoặc Return-Path được cấu hình theo ý muốn. Với Jakarta Mail SMTP transport, `mail.smtp.from` có thể ảnh hưởng envelope sender; nhưng không sửa thuộc tính transport singleton theo từng request nếu nhiều worker đang dùng.

### 17.2. Ma trận identity/provider

| Provider | Identity | From domain | Verified? | Eligible fallback? |
| --- | --- | --- | --- | --- |
| `smtp-vn-a` | `vn-security` | `example.com` | Yes | Primary |
| `api-vn-b` | `vn-security` | `example.com` | Yes | Có thể |
| `smtp-us-c` | `vn-security` | `example.com` | Yes | Không nếu policy vùng cấm |
| `api-vn-bulk` | `vn-security` | `example.com` | No | Không |

Verified sender domain chỉ là **một điều kiện**. Region, category, tenant, quota và content policy vẫn phải thỏa.

### 17.3. SPF, DKIM, DMARC khi failover

Trước khi bật provider B làm dự phòng:

1. Xác minh Header From domain được provider B hỗ trợ.
2. Cấu hình DKIM keys/selector theo hướng dẫn B.
3. Kiểm tra SPF nếu provider sử dụng envelope identity trong domain của tổ chức.
4. Kiểm tra DMARC alignment đối với Header From.
5. Cấu hình bounce domain/Return-Path nếu cần.
6. Gửi thử tới mailbox test, kiểm tra authentication results.
7. Đối chiếu complaint/bounce routing trên B.

Không chỉ thử `JavaMailSender.testConnection()` hoặc HTTP `/health` rồi kết luận sender identity đủ điều kiện. Kết nối thành công không có nghĩa provider cho phép gửi từ domain cụ thể.

### 17.4. Tenant isolation

Trong ứng dụng nhiều tenant:

- Tenant A không được dùng provider account hoặc From domain của tenant B.
- Adapter registry không lộ API key/SMTP password qua public request.
- Routing context phải được xác thực bằng domain data đã kiểm soát.
- Fallback không được tự đổi tenant identity.
- Feedback webhook phải map event về đúng tenant/delivery/attempt.
- Audit/metrics có RBAC phù hợp.

Nếu một provider phục vụ nhiều tenant, cần tách identity, suppression/quota và data access theo policy.

## 18. Feedback adapter: bounces, delivery events và complaints

Provider submit thành công chỉ là một giai đoạn. Sau đó nhà cung cấp có thể phát sự kiện:

- `QUEUED` hoặc `ACCEPTED`.
- `DELIVERED` / recipient server accepted.
- `DEFERRED` / temporary delivery delay.
- `HARD_BOUNCE` hoặc final failure.
- `SPAM_COMPLAINT`.
- `UNSUBSCRIBE` nếu là luồng marketing.

Tầng **feedback adapter** chuyển các payload riêng của vendor thành một schema nội bộ.

### 18.1. Mô hình sự kiện chuẩn hóa

~~~java
package com.example.mail.feedback;

import java.time.Instant;
import java.util.UUID;

public enum DeliveryFeedbackKind {
    PROVIDER_ACCEPTED,
    RECEIVER_ACCEPTED,
    DEFERRED,
    HARD_BOUNCE,
    SOFT_BOUNCE_FINAL,
    COMPLAINT,
    UNKNOWN
}

public record NormalizedProviderFeedback(
        String providerId,
        String providerEventId,
        String providerMessageId,
        UUID deliveryId,
        UUID attemptId,
        String recipient,
        DeliveryFeedbackKind kind,
        String safeCode,
        Instant eventTime) {
}
~~~

Đây là type tự định nghĩa. Không phải provider nào cũng có `providerMessageId`, và một provider có thể sinh nhiều events cho cùng một submission.

### 18.2. Correlation cần nhiều lớp ID

| ID | Ai cấp | Dùng cho |
| --- | --- | --- |
| `deliveryId` | Ứng dụng | Một ý định gửi tới recipient |
| `attemptId` | Ứng dụng | Một lần submission qua một provider |
| `providerId` | Registry | Namespace của provider |
| `providerMessageId` | Provider nếu hỗ trợ | Nối feedback với attempt |
| `providerEventId` | Provider | Deduplicate webhook event |
| RFC `Message-ID` | MIME | Truy vết/threading phụ trợ, không chứng minh idempotency |

Khi fallback từ A sang B, lưu **hai attempt records riêng**. Không ghi đè providerMessageId của A bằng ID B. Event từ A có thể đến muộn sau khi B đã được chọn; cần correlation theo provider/attempt.

### 18.3. Xác minh webhook

Một webhook handler nên:

~~~text
HTTP request
    |
    v
Verify provider signature + timestamp
    |
    v
Enforce request/attachment size
    |
    v
Normalize with provider-specific adapter
    |
    v
Resolve delivery + attempt + recipient
    |
    v
Persist event idempotently
    |
    v
Update delivery feedback projection
~~~

Không tin payload do bên ngoài tự khai provider/account/tenant mà không qua signature/credential và mapping đã phê duyệt.

### 18.4. Event tới không theo thứ tự

Ví dụ:

~~~text
12:01 provider emits delivered
12:02 provider emits deferred for an earlier attempt
12:03 application receives delivered
12:04 application receives delayed deferred
~~~

Không để một event `DEFERRED` cũ ghi đè trạng thái đã `DELIVERED` nếu provider contract và timestamps chứng minh nó thuộc thời điểm trước. Cần event history và state projection có luật chuyển trạng thái.

### 18.5. Suppression xuyên provider

Nếu A báo `HARD_BOUNCE` cho recipient R, một policy trung tâm có thể chặn các lần gửi kế tiếp tới R ở cả A và B khi phù hợp. Nếu chỉ trông vào suppression list riêng của A, fallback B có thể tiếp tục gửi tới địa chỉ lỗi hoặc vi phạm complaint policy.

### 18.6. SMTP DSN không giống provider API webhook

Với SMTP thuần, ứng dụng có thể cần mailbox nhận bounce qua envelope sender/Return-Path. DSN có thể mang MIME `multipart/report` và `message/delivery-status`. Không có một API Spring Mail duy nhất làm toàn bộ việc correlation/bounce cho nhiều nhà cung cấp; phải triển khai inbound adapter, parser, validation và mapping tới delivery theo policy.

## 19. Chính sách chuyển nhà cung cấp theo đợt (migration/canary)

Fallback sau outage và **chuyển nhà cung cấp có kế hoạch** là hai workflow khác nhau:

~~~text
Current provider A
       |
       v
New provider B approved (identity + feedback + region)
       |
       v
Route policy V2: 5% of eligible new deliveries -> B
       |
       v
Observe health/delivery feedback
       |
       v
Increase 5% -> 25% -> 50% -> 100%
       |
       v
Keep A webhook/DSN ingestion for prior sends
~~~

### 19.1. Sticky routing

Một delivery mới nên được gán provider theo một khóa ổn định:

~~~text
bucket = stableHash(deliveryId) % 100

0..4   -> provider B
5..99  -> provider A
~~~

Nếu mỗi lần retry random lại, một delivery có thể bị nộp cho nhiều provider ngoài ý muốn và rất khó đối soát. Sticky routing giữ lựa chọn ổn định, còn **fallback** là quyết định được ghi rõ khi có lý do hợp lệ.

Nếu canary theo tenant, phải bảo đảm tenant đúng quyền/region và thử nghiệm không vô tình phá giới hạn dữ liệu.

### 19.2. Điều kiện tăng lưu lượng

Theo dõi:

- Submission acceptance rate theo provider.
- Latency p95/p99 và timeout rate.
- SMTP 4xx/5xx hoặc HTTP response taxonomy.
- Throttle/quota và circuit breaker transitions.
- Complaint/hard bounce và sender reputation.
- Feedback webhook completeness và event lag.
- Queue age/SLO của security/transactional.
- Chi phí và khả năng support.

Đừng tăng traffic chỉ vì provider B trả 202 nhanh; deliverability có thể kém dù API submission nhanh.

### 19.3. Rollback an toàn

Khi rollback từ B về A:

- Route **delivery mới** theo policy cũ/phiên bản rollback.
- Không nộp lại những email B đã accepted.
- Những attempt B ở `UNKNOWN` vẫn cần reconciliation.
- Giữ credentials/webhook endpoint B đủ lâu để nhận bounce/delivery feedback đến muộn.
- Lưu policy version và selection reason cho mỗi attempt.
- Kiểm tra A còn quota/identity verification trước khi chuyển lưu lượng lớn trở lại.

Một kế hoạch rollback thiếu feedback ingestion sẽ khiến hệ thống mất khả năng biết các email đã gửi qua B về sau bị bounce hay delivered.

## 20. Quan sát adapter và fallback trong production

Khi nhiều adapter cùng được dùng, dashboard phải trả lời:

- Provider nào đang nhận bao nhiêu lượt submission?
- Vì sao fallback tăng, từ primary nào sang secondary nào?
- Một attempt thất bại dứt khoát hay UNKNOWN?
- Provider nào đang chạm rate limit hoặc circuit open?
- Queue nào bị chậm, và email có vượt business deadline không?
- Provider B có bounce/complaint cao hơn A sau canary không?
- Có bao nhiêu email cần reconciliation vì kết quả submission mơ hồ?

### 20.1. Metrics đề xuất

| Metric logic | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `mail_provider_attempts_total` | Counter | Số attempt thực sự bắt đầu gửi |
| `mail_provider_outcomes_total` | Counter | Accepted/definite rejected/unknown theo provider |
| `mail_provider_send_duration_seconds` | Timer/Histogram | Thời gian transport call |
| `mail_route_selections_total` | Counter | Chọn provider theo category/region/reason |
| `mail_fallback_decisions_total` | Counter | Fallback được duyệt/bị chặn và lý do |
| `mail_provider_rate_limited_total` | Counter | Throttle/capacity refusals |
| `mail_provider_circuit_open` | Gauge | Circuit breaker state theo provider |
| `mail_provider_inflight` | Gauge | Submission đang xử lý |
| `mail_outbox_due` | Gauge | Delivery tới hạn chưa được gửi |
| `mail_outbox_oldest_due_age_seconds` | Gauge | Tuổi delivery đến hạn lâu nhất |
| `mail_submission_unknown_current` | Gauge | Bao nhiêu attempt đang cần đối soát |
| `mail_feedback_events_total` | Counter | Bounce, complaint, delivered events |
| `mail_feedback_lag_seconds` | Histogram | Độ trễ từ submission tới feedback |
| `mail_state_commit_failures_total` | Counter | SMTP/API outcome có nhưng DB commit lỗi |

### 20.2. Micrometer instrumentation

~~~java
package com.example.mail.ops;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class MailProviderMetrics {

    private final MeterRegistry registry;

    public MailProviderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordOutcome(
            String providerId,
            SubmissionOutcome outcome,
            String normalizedCode) {

        Counter.builder("mail.provider.outcomes")
                .tag("provider", providerId)
                .tag("outcome", outcome.name())
                .tag("code", normalizedCode)
                .register(registry)
                .increment();
    }
}
~~~

`normalizedCode` phải đến từ **danh mục hữu hạn**, ví dụ `SMTP_PRE_SUBMISSION_CONNECT_ERROR`, `SMTP_UNKNOWN`, `HTTP_RATE_LIMIT`; không dùng raw exception message hoặc HTTP response body làm metric label.

### 20.3. Không đưa PII hoặc ID tùy ý vào tag

Tránh:

~~~text
mail_provider_outcomes_total{
  recipient="alice@example.com",
  deliveryId="uuid-every-message",
  error="Raw exception stack..."
}
~~~

Nhãn như vậy tạo một time series cho mỗi message, khiến chi phí lưu metrics tăng và có nguy cơ lộ dữ liệu người dùng. Dùng provider ID hữu hạn, region, category, outcome và safe code. Internal delivery ID thích hợp trong structured log/trace được bảo vệ.

### 20.4. Structured log của route và attempt

~~~json
{
  "event": "mail.provider.attempt.completed",
  "deliveryId": "opaque-delivery-uuid",
  "attemptId": "opaque-attempt-uuid",
  "providerId": "smtp-vn-tx-a",
  "routePolicyVersion": "routing-v4",
  "routeReason": "PRIMARY",
  "category": "TRANSACTIONAL",
  "region": "VN",
  "outcome": "UNKNOWN",
  "safeCode": "SMTP_RESPONSE_TIMEOUT",
  "elapsedMillis": 12345
}
~~~

Không log credential, raw email recipient, subject, body, attachment và secret token. Nếu region/tenant được coi là nhạy cảm theo policy, giới hạn quyền xem log và retention.

### 20.5. Prometheus và dashboard

Nếu Spring Boot có Actuator và Micrometer registry Prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: when-authorized
~~~

Endpoint thường được expose tại `/actuator/prometheus` khi cấu hình security cho phép. Không công khai endpoint management chứa metrics nội bộ ra Internet.

PromQL minh họa (với metric name/labels khớp output thực tế):

~~~promql
# Attempt outcomes theo provider trong 5 phút
sum by (provider, outcome) (
  rate(mail_provider_outcomes_total[5m])
)

# Unknown submissions đang chờ đối soát
max(mail_submission_unknown_current)

# Tuổi backlog đến hạn lớn nhất
max(mail_outbox_oldest_due_age_seconds)
~~~

Nếu mỗi replica đều query cùng database và export một gauge global backlog, **không cộng chúng bằng sum** vì sẽ đếm trùng. Dùng một authoritative collector hoặc aggregation đúng scope, và metric freshness để phân biệt queue rỗng với lỗi truy vấn collector.

### 20.6. Alert theo mức độ tác động

| Alert | Cần kiểm tra |
| --- | --- |
| Security email vượt deadline | Quota, queue age, provider primary/secondary |
| Fallback tăng bất thường | Primary health/circuit/credential |
| Unknown outcomes tăng | SMTP timeout sau DATA, HTTP POST timeout, DB commit failure |
| Secondary cũng bị throttle | Cả pool thiếu capacity, giảm bulk traffic |
| Verified sender rejected | DKIM/From/account config, secret rotation |
| Feedback webhook không tới | Signature, provider endpoint, replay/queue |
| Bounce/complaint tăng sau migration | Deliverability, domain reputation, consent |
| Không còn provider đủ điều kiện | Policy version, region restriction, tenant permission |

Không alert chỉ theo queue depth: cần tuổi job, throughput và tỷ lệ lỗi. Một hàng đợi 500 email có thể bình thường trong chiến dịch marketing, nhưng 10 email reset password chờ quá deadline đã là sự cố.

## 21. Bảo mật và bảo vệ dữ liệu trong provider adapter

Provider adapter là một ranh giới quyền hạn vì nó truy cập SMTP credential/API token và có thể thấy nội dung email đầy đủ. Thiết kế production cần xét:

### 21.1. Credential handling

- Mỗi provider/account dùng secret reference riêng; không lưu vào mail outbox.
- Inject credential qua secret manager hoặc runtime secret.
- Không log `JavaMailSenderImpl` configuration nếu log chứa password.
- Rotate key/password có quy trình kiểm tra và chuyển instance phù hợp.
- Không để code HTTP request chọn trực tiếp vendor credential.
- Dùng quyền tối thiểu cho API key: gửi email cần thiết, không cấp quyền rộng hơn khi không cần.

### 21.2. TLS và xác minh endpoint

SMTP cần STARTTLS bắt buộc hoặc implicit TLS theo endpoint, bật hostname/certificate validation. HTTPS API phải xác minh certificate, giới hạn redirect, request size và timeout. Không tắt TLS validation chỉ vì môi trường staging có chứng chỉ không đúng; hãy sửa trust/certificate.

### 21.3. Sender spoofing và header injection

Các trường `From`, `Reply-To` và recipient phải được resolve từ identity đã được ứng dụng cho phép, không tin trực tiếp địa chỉ bất kỳ do user truyền lên. Validate header fields, tránh CR/LF injection và chỉ cho phép sender domain đã verify.

### 21.4. Data residency end-to-end

Tên route `eu-provider-a` không chứng minh dữ liệu được xử lý trong EU. Cần kiểm tra:

- Nhà cung cấp xử lý body/attachment ở đâu.
- Logs và backup của họ đặt ở đâu.
- Webhook/feedback được lưu/truyền tới vùng nào.
- Data processors/subprocessors liên quan.
- Outbox database, object storage và metrics/log của chính ứng dụng.
- Thỏa thuận xử lý dữ liệu và quyền truy cập support.

Fallback sang vùng khác có thể vi phạm chính sách dù endpoint khác đang khỏe. Khi không có tuyến hợp lệ, nên `HOLD`/alert thay vì bypass residency.

### 21.5. Attachment, size và khả năng lộ dữ liệu

Nếu adapter phải lấy attachment từ object storage, chỉ dùng **immutable authorized reference** thuộc tenant/delivery. Không tải một URL tùy ý do request đưa vào (rủi ro SSRF). Giới hạn tổng byte, MIME depth, attachment type và timeout. Với file tạm, dùng thư mục riêng có quota/ACL và dọn sau khi gửi đồng bộ hoàn tất.

Không đưa raw MIME hoặc attachment bytes vào exception, retry queue, DLQ, trace hoặc metric tags. Nếu cần replay, dùng encrypted durable payload reference cùng retention/authorization.

### 21.6. Quota abuse

Nếu một public API cho phép chọn category `SECURITY` hoặc provider ID bất kỳ, attacker có thể tiêu hết quota ưu tiên hoặc gửi qua identity/vùng không đúng. Category phải phát sinh từ một use case đáng tin cậy, quota đặt theo tenant và business operation.

### 21.7. Quyền operator redrive

Người vận hành có quyền xem trạng thái không mặc nhiên có quyền gửi lại mail. Một action redrive phải kiểm tra:

1. Operator authentication/authorization.
2. Phạm vi tenant, message type, region.
3. Suppression/consent và business deadline.
4. Kết quả attempt cũ có UNKNOWN/ACCEPTED không.
5. Payload/attachment còn được phép truy cập và chưa hết retention.
6. Audit actor, reason, timestamp và policy version.

Không để một nút “Retry all FAILED” gửi lại cả password-reset token đã hết hạn hoặc email có kết quả SMTP UNKNOWN.

## 22. Kiểm thử adapter độc lập với vendor

Vì adapter contract dùng chung, phần lớn routing/fallback logic có thể kiểm thử bằng **fake adapters** trả những outcome xác định, không phải kết nối SMTP thật trong mọi unit test.

### 22.1. Fake adapter có thể điều khiển outcome

~~~java
public final class FakeMailProviderAdapter
        implements MailProviderAdapter {

    private final String id;
    private final ProviderCapabilities capabilities;
    private final ProviderSubmissionResult nextResult;
    private int submitCalls;

    public FakeMailProviderAdapter(
            String id,
            ProviderCapabilities capabilities,
            ProviderSubmissionResult nextResult) {
        this.id = id;
        this.capabilities = capabilities;
        this.nextResult = nextResult;
    }

    @Override
    public String providerId() {
        return id;
    }

    @Override
    public ProviderCapabilities capabilities() {
        return capabilities;
    }

    @Override
    public ProviderSubmissionResult submit(
            PreparedMailSubmission request) {
        submitCalls++;
        return nextResult;
    }

    public int submitCalls() {
        return submitCalls;
    }
}
~~~

Fake này chỉ phục vụ **unit test đơn luồng**. Nếu test concurrency, dùng thread-safe counters và record outcomes theo attempt; không dùng một mutable fake không đồng bộ rồi suy kết luận concurrency của production.

### 22.2. Unit test không fallback khi UNKNOWN

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class FallbackPlannerTest {

    @Test
    void refusesToFallbackAfterUnknownSubmission() {

        ApprovedRoute route = new ApprovedRoute(
                "routing-v4",
                "smtp-a",
                List.of("smtp-b"),
                "TRANSACTIONAL_VN");

        PreviousAttempt previous = new PreviousAttempt(
                "smtp-a",
                SubmissionOutcome.UNKNOWN,
                RejectionKind.UNCLASSIFIED,
                SubmissionStage.DATA);

        FallbackPlanner planner = new FallbackPlanner();

        assertThatThrownBy(() -> planner.selectNext(
                route, previous,
                Set.of("smtp-a", "smtp-b"), 3))
                .isInstanceOf(IllegalStateException.class);
    }
}
~~~

Test này minh họa invariant quan trọng: **kết quả unknown không tự biến thành quyền gửi lại qua B**. Với API production trả decision object, test nên assert `RECONCILE` thay vì exception.

### 22.3. Unit test approved fallback

~~~java
@Test
void choosesApprovedSecondaryWhenPrimaryWasNotAttempted() {

    ApprovedRoute route = new ApprovedRoute(
            "routing-v4",
            "smtp-a",
            List.of("smtp-b"),
            "TRANSACTIONAL_VN");

    FallbackPlanner planner = new FallbackPlanner();
    AttemptDecision next = planner.selectNext(
            route,
            null,
            Set.of("smtp-b"),
            3);

    assertThat(next.providerId()).isEqualTo("smtp-b");
    assertThat(next.reason()).isEqualTo("APPROVED_FALLBACK");
}
~~~

Ở đây primary **chưa được gọi**, nên không có nguy cơ double submission từ attempt A. Test còn cần xác nhận provider không có trong allowlist, sai region/identity hoặc hết quota **không được chọn**.

### 22.4. Test cùng một delivery, hai worker

Với PostgreSQL/Testcontainers:

1. Insert delivery `PENDING`.
2. Hai worker cùng claim.
3. Assert chỉ một worker lấy được row khi lease hợp lệ.
4. Assert `attempt_count=1` và đúng một attempt record `STARTED`.
5. Worker A ghi `ACCEPTED` bằng claim token hiện tại.
6. Worker B/stale worker thử ghi kết quả bằng token khác → update count 0.

Test bằng H2/mock repository không chứng minh chính xác `FOR UPDATE SKIP LOCKED`, isolation và row locking trên PostgreSQL.

### 22.5. Test network success nhưng state commit fail

Kịch bản:

~~~text
Fake provider A returns ACCEPTED
          |
          v
DB markAccepted throws
          |
          v
Expected:
  - no immediate submit through B
  - record/alert state-commit ambiguity
  - preserve provider A attempt metadata
  - reconcile before any resend
~~~

Đây là cửa sổ lỗi khác với provider trả `UNKNOWN` nhưng có thể dẫn tới duplicate tương tự. Một hệ thống chỉ test adapter `submit` ném exception sẽ bỏ sót tình huống này.

### 22.6. Test SMTP adapter với fake SMTP server

Có thể dùng GreenMail, Mailpit hoặc programmable SMTP test server để kiểm tra:

- Kết nối, STARTTLS/AUTH theo môi trường test.
- MIME body HTML/plain text và attachment.
- From/Reply-To và header encoding.
- SMTP accepted thành công.
- Recipient 5xx, temporary 4xx, connection drop.
- Timeout sau DATA dẫn tới outcome không chắc chắn.

Mailpit/GreenMail thông thường phù hợp kiểm tra nhận MIME, nhưng không nhất thiết hỗ trợ giả lập mọi lỗi giai đoạn protocol; nếu cần timeout sau DATA hoặc nhiều loại 4xx/5xx, dùng fake SMTP có programmable responses.

### 22.7. Test HTTP adapter qua fake server

Các trường hợp cần cover:

| Phản hồi giả lập | Kỳ vọng |
| --- | --- |
| API accepted có provider ID | Outcome `ACCEPTED`, lưu external ID |
| HTTP 400 validation chắc chắn không submit | `DEFINITE_REJECTED`, safe code |
| HTTP 401/403 | Config/auth incident, không retry vô hạn |
| HTTP 429 có Retry-After | Schedule có giới hạn theo contract |
| HTTP 5xx sau khi server đã tạo submission | Outcome `UNKNOWN` nếu không có bằng chứng |
| HTTP POST timeout | Không blind fallback; xem idempotency |
| Cùng idempotency key replay | Theo đúng hợp đồng provider mock |
| Body chứa token/PII | Logs/metrics không lộ payload |

Khi test vendor SDK, xác định nó có tự retry POST hay không. Nếu có, test cần tính cả số request thực sự phát ra, không chỉ một lần gọi method `submit` của adapter.

### 22.8. Test policy và security

Test matrix tối thiểu:

- VN security không được tự chuyển sang US nếu region policy cấm.
- EU marketing không dùng verified identity của tenant khác.
- Provider A khỏe nhưng không hỗ trợ category vẫn không eligible.
- Fallback B thiếu DKIM/From verification bị chặn.
- Message lớn hơn provider size limit không được nộp.
- Recipient đã suppress không được gửi qua provider khác.
- Deadline đã hết không được fallback.
- Attempt đã ACCEPTED không được gửi lại.
- Attempt UNKNOWN đòi reconciliation theo policy.
- Không có provider eligible → `NO_ELIGIBLE_PROVIDER`/HOLD, không default tùy tiện.

### 22.9. Test webhook feedback

- Provider A webhook không qua được verifier của provider B.
- Một provider event ID bị gửi lại chỉ lưu một event.
- Event tới muộn vẫn correlate đúng attempt A dù route hiện tại đã đổi sang B.
- `DEFERRED` không làm ghi đè sai `DELIVERED`.
- Hard bounce verified cập nhật central suppression đúng phạm vi.
- Complaint của marketing không được hiểu như HTTP submission failure.

Đừng dùng SMTP production hoặc recipient công cộng để tạo lỗi trong test tự động.

## 23. Runbook: primary provider outage

Giả sử ứng dụng gửi thông báo giao dịch tại khu vực VN qua SMTP A; B là HTTP provider dự phòng đã được phê duyệt.

~~~text
09:00  SMTP A connection failure increases
09:01  Circuit breaker begins rejecting new calls to A
09:02  New unsubmitted work routes to eligible B
09:03  Pre-submission definite failures from A may fallback to B
09:04  Existing A UNKNOWN attempts remain for reconciliation
09:05  B quota usage grows, bulk traffic may be paused
09:10  A starts recovering
09:20  Controlled failback canary begins
~~~

### 23.1. Bước 1 — Xác minh loại sự cố

Kiểm tra:

- Network/TLS/DNS/SMTP authentication hay provider 4xx/5xx?
- Primary chỉ lỗi một region/account hay toàn provider?
- Có deploy/secret rotation/route policy change gần thời điểm lỗi?
- Adapter đang trả `DEFINITE_REJECTED` hay `UNKNOWN`?
- Delivery nào đã accepted trước khi circuit mở?

Đừng đổi provider ngay khi dashboard có vài timeout mà chưa biết liệu A đã nhận SMTP DATA hay không.

### 23.2. Bước 2 — Kiểm tra B đủ điều kiện

Xác nhận:

1. B đã được policy allowlist cho đúng category/tenant/region.
2. From/DKIM/Return-Path trên B đã verify.
3. B hỗ trợ MIME/attachment size và recipient count.
4. B còn quota/concurrency.
5. B nhận được delivery feedback và webhook signature đã cấu hình.
6. Data policy và retention của B đã được chấp thuận.

Nếu B không thỏa, **HOLD và alert** vẫn tốt hơn ép gửi trái policy.

### 23.3. Bước 3 — Tách work mới và attempts cũ

| Nhóm | Hành động |
| --- | --- |
| Work PENDING, chưa gọi provider | Chọn B nếu eligible |
| Attempt A definite failure trước submission | Có thể tạo attempt B theo retry/fallback policy |
| Attempt A accepted | Không nộp B |
| Attempt A unknown | Reconcile, không blind send B |
| A connection/auth configuration invalid | Sửa cấu hình đồng thời cho phép chọn B nếu policy hợp lệ |
| Delivery quá deadline hoặc recipient suppress | Dừng theo policy, không gửi muộn |

### 23.4. Bước 4 — Điều phối capacity

Theo dõi B in-flight, throttle, send duration, quota và error rate. Nếu B không có đủ công suất cho cả marketing và security, tạm dừng bulk hoặc dùng reserved capacity hợp đồng cho phép. Đừng tăng thread pool từ 8 lên 80 trong khi B chỉ cho 10 connections: lỗi 429/421 có thể nhiều hơn.

### 23.5. Bước 5 — Xác nhận phục hồi

Không kết luận “xong” chỉ vì A đã mở cổng TCP trở lại. Cần:

- Thử gửi canary qua A với identity phù hợp.
- Quan sát acceptance, latency, 4xx/5xx và DKIM/authentication.
- Kiểm tra queue age và backlog giảm.
- Xác nhận B không tiếp tục bị throttle.
- Tiếp tục ingest webhook của B cho những mail đã accepted.
- Reconcile và triage những attempt UNKNOWN còn tồn đọng.
- Lưu incident timeline và các route decisions có liên quan.

## 24. Runbook: tỷ lệ UNKNOWN tăng

UNKNOWN là một trong những trạng thái khó nhất vì **không thể biết email có thể đã tới người nhận hay chưa** chỉ từ exception ở client.

### 24.1. Tìm nguyên nhân

Các dấu hiệu thường gặp:

- SMTP timeout/reset khi đang gửi DATA.
- Provider HTTP POST mất kết nối sau khi server đã tiếp nhận request.
- Adapter process bị kill trong khoảng network call.
- Database commit result thất bại sau submission accepted.
- SDK retry ẩn tạo nhiều request nhưng app chỉ ghi một attempt.

### 24.2. Khoanh vùng theo provider và stage

~~~text
UNKNOWN count rising
        |
        v
Group by provider / transport / observed stage
        |
        +--> HTTP API with idempotency
        |        |
        |        v
        |    Query status / retry same key within contract
        |
        +--> SMTP after DATA
        |        |
        |        v
        |    Provider logs/DSN if available
        |
        +--> DB commit failure
                 |
                 v
             Inspect attempt history + provider evidence
~~~

Không chỉ thấy `MailSendException` rồi chọn B. Nếu có bằng chứng A đã accepted, cập nhật state và chờ feedback; nếu provider xác nhận chưa có submission, có thể retry/fallback. Nếu không thể xác minh, chọn phương án theo duplicate tolerance của nghiệp vụ và audit lý do.

### 24.3. Tại sao loại email ảnh hưởng quyết định?

Email đặt lại mật khẩu hoặc OTP có deadline ngắn; retry muộn có thể khiến người dùng nhận token hết hạn. Email hóa đơn có thể chấp nhận gửi lại có cảnh báo hoặc dùng download portal, nhưng gửi trùng hóa đơn có thể làm người dùng hiểu nhầm. Marketing có rủi ro complaint nếu duplicate. Không áp một quy tắc resend `UNKNOWN` chung cho tất cả.

### 24.4. Đóng incident

Trước khi đóng, cần biết:

- Bao nhiêu UNKNOWN đã được xác định ACCEPTED.
- Bao nhiêu được xác định definite failure.
- Bao nhiêu còn unresolved và policy xử lý tiếp.
- Có duplicate recipients đã được xác nhận không.
- Có cần thay timeout/lease, SDK retry hoặc database availability không.

## 25. Runbook: chuyển provider nhưng deliverability giảm

Một provider API có thể trả `202 Accepted` rất nhanh nhưng tỷ lệ vào inbox thấp hơn provider cũ. Nguyên nhân có thể thuộc **sender identity, DNS, content, reputation hoặc feedback processing** chứ không phải network adapter.

### 25.1. Checklist điều tra

1. SPF/DKIM/DMARC authentication có pass và align với Header From không?
2. Bounce domain/Return-Path đã cấu hình đúng provider B chưa?
3. Feedback webhook B có nhận và verify được không?
4. Có suppression/consent được đồng bộ giữa A/B không?
5. Domain/IP pool B đã warm up theo chính sách vận hành chưa?
6. Transactional và marketing traffic có đang dùng chung reputation/quota không?
7. Attachment/MIME encoding có thay đổi khi chuyển adapter không?
8. Provider B có spam/complaint hoặc hard bounce rate tăng theo recipient domain không?

### 25.2. Đừng sửa bằng cách resend tất cả

Nếu provider B đã accepted message nhưng feedback chưa tới, resend qua A có thể tạo duplicate. Đầu tiên phải xác định đường ingest feedback, trạng thái provider và event lag.

Khi quyết định rollback, chỉ route **delivery mới** về A theo policy; những attempt B đã accepted vẫn cần giữ lịch sử và đường webhook cho đến khi hết thời hạn feedback/retention phù hợp.

## 26. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `catch(Exception)` rồi gửi B ngay | Duplicate khi A accepted nhưng timeout | Chuẩn hóa definite/unknown, reconcile |
| Một method `boolean send()` cho mọi transport | Mất thông tin rejection/unknown/feedback | Typed submission result |
| Router chỉ xét provider health | Gửi sai vùng, sai tenant hoặc From | Eligibility trước health |
| Domain email `.eu` → region EU | Sai nguồn dữ liệu khu vực | Dùng tenant/residency policy đáng tin |
| Dùng một sender singleton và đổi host/password | Race condition, sai account | Per-provider/identity adapter instance |
| Suy HTTP 5xx chắc chắn không tạo message | Duplicate POST request | Idempotency/status lookup/UNKNOWN |
| Suy SMTP Message-ID bảo đảm exactly-once | Gửi trùng | Coi ID là correlation, không dedupe guarantee |
| Fallback khi SMTP đã accepted | Gửi hai bản mail | Terminal submission success, chờ feedback |
| Retry mọi 5xx/permanent recipient failure | Retry vô ích, reputation kém | Classify stage/error/recipient |
| Secondary chưa DKIM/From verified | Provider reject hoặc DMARC fail | Pre-approve identities |
| Chọn fallback ngoài region vì khỏe hơn | Vi phạm data policy | Fail-closed region/tenant constraints |
| Chia nhiều SMTP endpoint cùng quota rồi coi độc lập | Throttle vẫn tăng | Hiểu account-level quota/pool |
| Retry SDK + advice + outbox cùng lúc | Attempt count mất kiểm soát | Chính sách retry một nguồn, giới hạn tổng |
| Lưu route chỉ sau `send` | Crash làm mất chứng cứ provider đã gọi | Persist attempt trước network |
| Giữ DB transaction qua SMTP | Lock lâu, deadlocks/throughput thấp | Claim/commit và outcome/commit ngắn |
| Claim token nhưng không idempotent side effect | Worker cũ vẫn có thể gây gửi trùng | Leases + reconciliation + provider guarantees |
| `UNKNOWN` tự đổi `RETRY` ngay | Duplicate risk | Hold/reconcile |
| Không lưu provider ID theo attempt | Không đối soát webhook sau fallback | Immutable attempt history |
| Tắt webhook B ngay khi rollback | Mất bounce/delivery feedback muộn | Giữ ingress feedback theo retention |
| Gửi marketing qua security pool | OTP chậm, reputation/quota bị ảnh hưởng | Reserved capacity, identities riêng |
| Logging nguyên API response/attachment | Lộ token/PII | Sanitize, safe error code |
| Redrive toàn DLQ | Gửi token hết hạn hoặc email đã accepted | Authorization, eligibility, audit |
| Tổng hợp gauge toàn DB trên mọi replica | Dashboard nhân số backlog | Correct aggregation/collector |
| Test happy path với một provider | Không phát hiện lỗi failover/race | Fake provider + SMTP/API failure tests |

### 26.1. Nên xử lý “unknown outcome” ở đâu?

Không nên để mỗi adapter tự âm thầm retry/fallback cho đến khi được `ACCEPTED`. Adapter báo một kết quả có bằng chứng; **orchestrator/reconciliation service** quyết định tiếp theo. Nhờ vậy policy có thể xét loại email, region, attempts, duplicate tolerance và lịch sử business operation.

### 26.2. Khi provider B không có delivery feedback

Một route có thể vẫn phù hợp cho email không cần tracking sâu, nhưng không nên chọn nó cho workflow **bắt buộc có bounce/complaint compliance** nếu không có cơ chế thay thế. Capability phải phản ánh giới hạn đó; không giả định JavaMailSender tự cung cấp delivery status.

### 26.3. Khi một email có nhiều recipient

SMTP có thể chấp nhận một phần recipient. Nếu dùng một `PreparedMailSubmission` chung cho nhiều người nhận, outcome phải phân biệt per-recipient acceptance/rejection, và fallback không được resend cho những recipient đã accepted. Với notification quan trọng, **một delivery per-recipient** thường đơn giản hơn và dễ audit.

## 27. Câu hỏi thường gặp

**“Spring Framework Mail có sẵn provider adapter và fallback không?”**  
`JavaMailSender` cung cấp abstraction để gửi email, nhưng Spring Mail không tự xây một hệ thống multi-provider routing/fallback đầy đủ. Ứng dụng cần policy, registry, attempt state và feedback integration.

**“Có thể dùng hai JavaMailSender bean không?”**  
Có. Dùng `@Qualifier` hoặc một registry để tra sender theo provider ID. Cần tách cấu hình host/credential và không mutate sender dùng chung theo request.

**“Provider adapter có phải là Strategy Pattern không?”**  
Có thể kết hợp **Adapter Pattern** để che chi tiết giao tiếp SMTP/HTTP, và **Strategy Pattern** để chọn thuật toán/nhà cung cấp. Nhưng tên pattern không tự giải quyết race, exactly-once, quota và data compliance.

**“Fallback và retry khác nhau thế nào?”**  
Retry là một attempt mới; fallback là chuyển sang provider khác theo policy. Một fallback thường cũng được tính vào tổng attempt, không tự miễn `max_attempts`.

**“Có nên fallback nếu MailSendException xuất hiện?”**  
Không dựa duy nhất vào exception class. Phải biết lỗi ở stage nào và provider có thể đã accepted hay chưa. Nếu không chắc, coi outcome UNKNOWN rồi reconcile.

**“SMTP accepted nghĩa inbox delivered?”**  
Không. Relay đã chấp nhận message không đồng nghĩa mail nằm trong inbox. Bounces, filtering và provider feedback thuộc giai đoạn tiếp theo.

**“Nếu timeout sau DATA thì chắc chắn chưa gửi?”**  
Không. SMTP relay có thể đã nhận message nhưng response cuối bị mất. Gửi lại qua B có thể tạo duplicate.

**“HTTP 202 có nghĩa người nhận đã nhận mail?”**  
Không nhất thiết. Thông thường đây là yêu cầu đã được provider nhận/xếp hàng theo contract; chưa chứng minh server người nhận đã chấp nhận.

**“HTTP API idempotency key có bảo đảm gửi một lần mãi mãi?”**  
Không. Key có scope, TTL và hành vi theo hợp đồng provider. Sau expiry hoặc khi đổi provider, bảo đảm có thể không còn áp dụng.

**“Một provider B có thể dự phòng cho A nếu dùng cùng From không?”**  
Chỉ khi B có quyền gửi danh tính đó và các điều kiện SPF/DKIM/DMARC, envelope sender, tenant, region và quota đáp ứng. Cùng chuỗi From không tạo quyền sử dụng.

**“Nên chuyển B ngay khi circuit A open?”**  
Với delivery **mới chưa submit**, có thể nếu B eligible. Với delivery có attempt A trước đó UNKNOWN, circuit open không làm rủi ro duplicate biến mất.

**“Nên route theo TLD của recipient không?”**  
Không. `.com`/`.vn` không xác nhận địa điểm thực tế hay nghĩa vụ residency. Dùng dữ liệu region/tenant được xác minh.

**“Có nên load balance 50/50 để luôn sẵn dự phòng?”**  
Có thể nếu cả A/B hợp lệ và có đủ quota, sender identity, feedback, reputation. Weighted routing nên có version và stable bucket, không random lại qua mỗi retry.

**“Provider A và B dùng chung quota có ích gì?”**  
Có thể có lợi về endpoint/network redundancy, nhưng không giải quyết giới hạn account-level quota. Cần hiểu tài nguyên nào thực sự độc lập.

**“Khi nào dừng retry?”**  
Khi hết attempts/deadline, lỗi permanent, payload/source không còn phù hợp hoặc không có eligible provider. Với UNKNOWN cần policy riêng về reconciliation/duplicate risk.

**“Dùng transactional outbox có đảm bảo exactly-once?”**  
Không với SMTP thuần. Outbox bảo đảm ý định gửi được commit cùng nghiệp vụ, nhưng không giao dịch nguyên tử được với SMTP/API provider.

**“Có cần lưu route version không?”**  
Có ích để audit. Khi routing policy thay đổi, mỗi attempt cần biết provider và phiên bản policy đã dẫn tới quyết định đó.

**“Có nên lưu raw vendor response?”**  
Chỉ khi có nhu cầu và cơ chế bảo vệ phù hợp. Response có thể chứa recipient, message body, token hoặc PII; ưu tiên safe error code, provider message ID đã kiểm soát và trace có retention.

**“ProviderMessageId và MIME Message-ID có giống nhau không?”**  
Không nhất thiết. ProviderMessageId là ID nhà cung cấp cấp, còn MIME Message-ID là email header; adapter nên lưu riêng, không giả định SMTP trả provider ID.

**“Webhook đến trễ sau fallback xử lý thế nào?”**  
Map theo provider ID và attempt ID, giữ immutable history; không ghi đè attempt A bằng kết quả của B. Cần ordering/idempotency cho event.

**“Có nên tự động resend khi webhook báo deferred?”**  
Không mặc định. Provider có thể vẫn đang retry delivery nội bộ; gửi thêm một submission có nguy cơ tạo trùng.

**“Một hard bounce từ A có cần chặn B?”**  
Thường cần suppression chung theo policy và bằng chứng feedback đã xác minh. Nếu chỉ dùng blocklist của A, B có thể tiếp tục gửi tới địa chỉ lỗi.

**“Có thể lưu MailProviderAdapter trong database không?”**  
Không lưu object Java/credential trực tiếp như một config row. Lưu provider ID, policy/version, capability metadata và secret reference; registry khởi tạo adapter runtime từ cấu hình đã kiểm soát.

**“Có nên lấy adapter theo provider ID từ HTTP request?”**  
Không nếu request không có quyền. Router quyết định từ validated business context, tenant, category, region; caller không được vượt policy bằng một string.

**“Nếu provider B không hỗ trợ attachment lớn thì sao?”**  
Không fallback mù. Capability filter phải loại B trước submission; có thể gửi link tải an toàn theo nghiệp vụ hoặc giữ/fail rõ.

**“Rate limiting nên theo provider hay category?”**  
Theo đúng tầng quota thật của provider, đồng thời có reserved capacity/category nếu cần. Một limiter category riêng chưa đủ khi mọi category dùng chung một account quota.

**“Có nên lưu mọi error thành DLQ?”**  
Không. Lỗi transient còn deadline/attempt có thể retry; lỗi permanent chuyển terminal; lỗi UNKNOWN cần đối soát; quarantine cần quyền riêng. DLQ thường dành cho những work item đã dừng retry tự động.

**“Làm sao test fallback mà không gửi mail thật?”**  
Dùng fake adapters trả typed outcomes; unit test planner, rồi integration test SMTP/HTTP bằng fake servers. Không cần gửi tới người nhận công cộng.

## 28. Checklist triển khai production

### Provider contract và adapter

1. Định nghĩa `MailProviderAdapter` với request đã được chuẩn bị, không có dữ liệu chưa authorize.
2. Dùng `ProviderSubmissionResult` tách `ACCEPTED`, `DEFINITE_REJECTED` và `UNKNOWN`.
3. Không dùng một `boolean sent` để che đi kết quả không rõ.
4. Tách `providerMessageId` khỏi MIME `Message-ID`.
5. Adapter SMTP và HTTP API có classifier/lỗi đặc thù; không ép chúng vào một mã `catch-all retry`.
6. Chuẩn hóa provider ID, safe error code và stage cho log/metrics.
7. Khởi tạo credential/transport riêng theo provider/sending identity; không mutate shared sender theo request.
8. Không để HTTP client/SDK tự retry POST không kiểm soát.

### Routing policy

9. Xác định category, tenant, region, identity và deadline từ nguồn đáng tin.
10. Tạo **tập provider được phép** trước khi xét health/latency/cost.
11. Định nghĩa primary và approved fallbacks tường minh.
12. Không route theo email TLD hoặc provider ID do user tự nhập.
13. Kiểm tra verified identity, DKIM/From domain, TLS, size, capability và quota.
14. Khi không còn eligible provider, HOLD/alert thay vì chuyển ngoài policy.
15. Route/policy có version, audit và test ma trận.

### Fallback và retry

16. Fallback chỉ khi provider trước **chắc chắn chưa accepted** hoặc business policy đã xử lý risk đặc biệt.
17. Không fallback khi đã `ACCEPTED`.
18. Không fallback mù khi `UNKNOWN` sau SMTP DATA/HTTP POST timeout.
19. Không retry permanent invalid recipient/suppression/expired token.
20. Retry có max attempts, deadline, backoff, jitter và capacity control.
21. Không để provider SDK, Spring advice và outbox cùng retry vô hạn.
22. Phân biệt first-time route, load balancing, fallback và failback trong selection reason.
23. Giữ attempt IDs, provider IDs và route versions bất biến trong history.

### Durable state và idempotency

24. Tạo một delivery intent bền vững theo business operation/recipient.
25. Ghi attempt STARTED/provider trước network call.
26. Không giữ DB transaction/row lock trong lúc SMTP/API network IO.
27. Claim atomically, dùng lease + fencing token.
28. Xử lý crash window khi transport accepted nhưng DB commit lỗi.
29. Có `UNKNOWN` và reconciliation workflow.
30. Nếu API provider hỗ trợ idempotency, dùng key ổn định trong phạm vi TTL/contract.
31. Không tuyên bố SMTP thuần bảo đảm exactly-once.

### Feedback và bảo mật

32. Nhận và xác minh webhook/DSN theo provider.
33. Correlate feedback theo provider + attempt/delivery + recipient.
34. Deduplicate provider events và xử lý event đến trễ/không theo thứ tự.
35. Có central suppression phù hợp khi bounce/complaint.
36. Kiểm soát PII trong mail body, attachment, logs và DLQ.
37. Mọi storage key/attachment reference phải được tenant-authorize.
38. Thực hiện credential rotation, TLS/hostname validation và RBAC/redrive audit.
39. Duy trì feedback ingestion khi rollback provider.

### Vận hành và kiểm thử

40. Có metrics provider attempts/outcomes, fallback, quota, circuit, unknown và outbox age.
41. Cảnh báo security email trễ, UNKNOWN tăng và no eligible provider.
42. Test adapter SMTP/HTTP trong môi trường giả lập, không gửi mail thật.
43. Test ma trận policy category × region × tenant × identity.
44. Test timeout sau DATA/HTTP POST và DB commit failure sau ACCEPTED.
45. Test concurrency, claim/lease, stale outcome và duplicate protection.
46. Test webhook redelivery/bounce/correlation sau fallback.
47. Có runbook primary outage, UNKNOWN, failed migration và redrive.
48. Canary/rollback dùng route version và sticky assignment.

## 29. Sơ đồ kiến trúc tổng kết

~~~text
                         Business events
                       order / account / billing
                                 |
                                 v
                        Notification service
                                 |
                                 v
                        Durable mail outbox
                                 |
                                 v
                      Worker atomic claim
                                 |
                                 v
                    Business and security policy
                   consent / tenant / data region
                                 |
                                 v
                        Provider router
                    eligible set + route version
                                 |
                                 v
                      Provider selection
                  priority / health / quota / cost
                                 |
                                 v
                    Persist STARTED attempt
                                 |
                +----------------+------------------+
                |                                   |
                v                                   v
        SMTP provider adapter                 HTTP API adapter
        JavaMailSender                        Vendor API client
                |                                   |
                v                                   v
            SMTP relay                          API endpoint
                |                                   |
                +----------------+------------------+
                                 |
                                 v
                    Normalized submission result
                                 |
                 +---------------+------------------+
                 |               |                  |
                 v               v                  v
              ACCEPTED     DEFINITE_REJECTED      UNKNOWN
                 |               |                  |
                 |               v                  v
                 |         Failure classifier   Reconciliation
                 |               |                  |
                 |        +------+-------+          |
                 |        |              |          |
                 |        v              v          |
                 |     RETRY          FAILED/HOLD    |
                 |        |              |          |
                 |        v              |          |
                 |   Fallback policy      |          |
                 |        |              |          |
                 |        v              |          |
                 |   Approved new attempt |          |
                 |        |              |          |
                 +--------+--------------+----------+
                                 |
                                 v
                    Attempt history + durable state
                                 |
             +-------------------+------------------+
             |                   |                  |
             v                   v                  v
         Monitoring          Audit/ops          Feedback adapter
       SLO, metrics,         redrive            webhook/DSN
        alerting                |                  |
                                |                  v
                                |          Bounce/complaint events
                                |                  |
                                +------------------+
                                           |
                                           v
                                    Central suppression
~~~

### Những nguyên tắc cốt lõi

- **Adapter** che chi tiết transport, **router** quyết định nhà cung cấp hợp lệ, **fallback policy** quyết định có được đổi sau lỗi hay không.
- Một provider **khỏe** chưa chắc **được phép** xử lý delivery.
- `ACCEPTED` chỉ nói nhà cung cấp đã nhận submission, không phải inbox delivery.
- `UNKNOWN` phải được coi là trạng thái có khả năng gây duplicate, không đơn giản là retryable failure.
- Một fallback hợp lệ phải được ghi thành **attempt mới với provider/policy/reason rõ ràng**.
- **Transactional outbox không tạo exactly-once SMTP**; cần idempotency, lease và reconciliation.
- **Circuit breaker/limiter** bảo vệ capacity nhưng không được vượt region/tenant/identity policy.
- **Feedback webhook/DSN** phải được giữ qua các lần chuyển provider để không mất thông tin bounce và complaint.
- **Bảo mật thông tin email và credential** là một phần của thiết kế provider adapter, không chỉ một cấu hình phụ.

## Kết luận

**Provider adapter và chiến lược fallback** là một mẫu thiết kế production quan trọng cho ứng dụng Spring Framework Mail có nhu cầu sử dụng nhiều SMTP relay hoặc kết hợp nhà cung cấp HTTP email API. Một kiến trúc vững chắc tách contract gửi mail khỏi vendor SDK, quản lý adapter qua registry, áp dụng routing policy có version và lưu đầy đủ từng attempt bằng outbox bền vững.

Điểm khác biệt giữa một giải pháp chạy được và một giải pháp đủ tin cậy để vận hành là **chất lượng quyết định khi thất bại**: hệ thống phải biết lỗi nào xảy ra trước khi submission, khi nào provider đã chấp nhận, khi nào kết quả không rõ và khi nào việc đổi provider có thể gây gửi trùng hoặc vi phạm policy. Khi bổ sung idempotency, rate limiting, circuit breaker, sender identity verification, feedback correlation, quan sát và redrive có audit, fallback trở thành một cơ chế phục hồi được kiểm soát thay vì một lệnh gửi lại mù quáng.

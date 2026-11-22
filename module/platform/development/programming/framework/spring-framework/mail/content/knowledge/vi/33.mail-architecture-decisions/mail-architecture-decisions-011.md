# Đặt ranh giới phần Spring Mail trong hệ thống lớn

## 1. Câu hỏi kiến trúc quan trọng hơn việc gọi send()

Trong một ứng dụng Spring Boot nhỏ, gửi email xác nhận có thể chỉ là:

~~~java
simpleMailMessage.setTo(customerEmail);
simpleMailMessage.setSubject("Đã tạo đơn hàng");
simpleMailMessage.setText("Cảm ơn bạn đã mua hàng.");
mailSender.send(simpleMailMessage);
~~~

Khi hệ thống lớn lên, cùng một nhu cầu gửi email xuất hiện ở nhiều nơi: đặt hàng, thanh toán, quản lý tài khoản, bảo mật, CRM, marketing, hỗ trợ khách hàng, xử lý hóa đơn, báo cáo và các batch jobs. Mỗi nơi có chính sách khác nhau về nội dung, người nhận, quyền gửi, retry và thời hạn.

Nếu tất cả service đều biết cấu hình SMTP, trực tiếp tạo `MimeMessage` và quyết định cách retry, hệ thống dễ gặp:

- Logic gửi email bị sao chép trên nhiều module.
- Đội nghiệp vụ phải hiểu `MessagingException` hoặc `MailSendException` để xử lý đơn hàng.
- Một provider outage làm chậm request checkout hoặc giữ transaction database.
- Thay SMTP provider đòi sửa nhiều service.
- Template email, unsubscribe và sender authorization không thống nhất.
- Email được gửi cho giao dịch đã rollback hoặc bỏ sót khi một process chết.
- Retry gây gửi trùng và khó xác định email thực sự đã được provider chấp nhận hay chưa.
- Multi-tenant quota, bảo mật dữ liệu và theo dõi delivery không có nơi chịu trách nhiệm.

Vì vậy, bài toán **“Đặt ranh giới phần Spring Mail trong hệ thống lớn”** không chỉ hỏi nên đặt `JavaMailSender` vào package nào, mà là:

> **Thành phần nào biết quy tắc nghiệp vụ cần thông báo? Thành phần nào quyết định thông báo hợp lệ? Thành phần nào chịu trách nhiệm gửi qua SMTP? Trạng thái gửi được lưu ở đâu, và ai chịu trách nhiệm khi thất bại?**

Một ranh giới tốt làm rõ những câu hỏi đó và giúp các bộ phận thay đổi độc lập.

## 2. Spring Framework Mail cung cấp những gì và không cung cấp những gì?

Spring Mail chủ yếu đưa ra abstraction và công cụ cho **outbound email submission**:

| Thành phần | Vai trò |
|---|---|
| `MailSender` | Interface gửi các `SimpleMailMessage` |
| `JavaMailSender` | Mở rộng cho MIME message và Jakarta Mail |
| `JavaMailSenderImpl` | Implementation điển hình của Spring |
| `MimeMessageHelper` | Hỗ trợ To/From/Subject/body/attachment/inline MIME |
| `MailException` và các subtype | Phân loại một số lỗi ở API Spring Mail |
| Jakarta Mail `MimeMessage`/`Session` | Mô hình MIME và giao tiếp transport bên dưới |

Spring Boot có thể giúp cấu hình một `JavaMailSender` mặc định từ `spring.mail.*` nếu các điều kiện auto-configuration được thỏa mãn.

Nhưng **Spring Mail core không tự cung cấp một notification platform hoàn chỉnh**. Nó không tự:

- Xác định đơn hàng nào cần email.
- Kiểm tra consent, quiet hours hay suppression list.
- Lập lịch gửi bền vững qua restart.
- Bảo đảm atomicity giữa database nghiệp vụ và SMTP.
- Lưu trạng thái outbox, attempts, provider delivery events.
- Bảo đảm exactly-once email delivery.
- Quản lý fairness, provider quota và tenant budgets.
- Quản lý vòng đời template, locale, branding và audit.
- Tạo một inbound mailbox processor chỉ từ `JavaMailSender`.

**Kết luận kiến trúc:** đặt Spring Mail ở tầng **infrastructure/transport adapter**. Phần orchestration và chính sách notification thuộc ứng dụng hoặc một bounded context riêng, không nên nhét vào `JavaMailSenderImpl` hay `MimeMessageHelper`.

## 3. Năm tầng trách nhiệm nên phân biệt

~~~text
┌────────────────────────────────────────────────────────┐
│ 1. Business domain / application                       │
│  OrderPaid, UserRegistered, InvoiceIssued              │
└───────────────────────────┬────────────────────────────┘
                            │ business intent/event
                            v
┌────────────────────────────────────────────────────────┐
│ 2. Notification policy and orchestration               │
│  Who? Why? Which channel? Consent? Priority? Deadline? │
└───────────────────────────┬────────────────────────────┘
                            │ authorized email intent
                            v
┌────────────────────────────────────────────────────────┐
│ 3. Durable delivery workflow                           │
│  Outbox, schedule, status, lease, idempotency, retry    │
└───────────────────────────┬────────────────────────────┘
                            │ claim + dispatch decision
                            v
┌────────────────────────────────────────────────────────┐
│ 4. Mail transport adapter (Spring Mail)                │
│  MimeMessageHelper, JavaMailSender, SMTP TLS/auth       │
└───────────────────────────┬────────────────────────────┘
                            │ SMTP submission
                            v
┌────────────────────────────────────────────────────────┐
│ 5. Provider + delivery/feedback                        │
│  SMTP accepted, bounce, webhook, message trace         │
└────────────────────────────────────────────────────────┘
~~~

Không nhất thiết tạo năm microservices. **Ranh giới logic** có thể là năm packages/modules trong một monolith. Điều quan trọng là chiều phụ thuộc và ownership, không phải số lượng repository hay Kubernetes deployments.

| Tầng | Sở hữu | Không nên sở hữu |
|---|---|---|
| Domain | Quy tắc đặt hàng, tài khoản, hóa đơn; sự kiện nghiệp vụ | SMTP host/password, MIME headers |
| Notification application | Recipient eligibility, template selection, channel policy | Socket/TLS implementation |
| Durable workflow | Trạng thái job, claim/lease, retry/expiry, attempt history | Business transaction cụ thể của mọi domain |
| Transport adapter | Xây MIME, cấu hình SMTP, gọi `JavaMailSender`, mô tả outcome | Quy tắc “đơn hàng này đã được thanh toán?” |
| Provider feedback | Accepted reference, bounce/delivery events | Tự ý thay đổi trạng thái đơn hàng mà không qua domain policy |

## 4. Chọn ranh giới theo mục tiêu thay đổi

Một ranh giới có chất lượng khi **hai loại thay đổi độc lập** không buộc nhau phải sửa:

- Thay SMTP provider không cần sửa `OrderService`.
- Đổi template hóa đơn không cần sửa kết nối SMTP hoặc quota gate.
- Đổi business rule “chỉ gửi email khi thanh toán settled” không cần sửa MIME builder.
- Đổi retry/backoff không cần chạm code tạo đơn hàng.
- Đổi cách lưu attachment không cần khiến domain biết `ByteArrayResource`.
- Bật một email API thay cho SMTP không cần thay đổi toàn bộ request DTO của ứng dụng.

Đây là một ứng dụng của **dependency inversion**: domain và orchestration phụ thuộc vào các contract do ứng dụng kiểm soát; transport adapter triển khai contract đó.

Không nên định nghĩa public interface nghiệp vụ bằng class của transport framework:

~~~java
// Không phù hợp làm contract domain/application công khai:
void notifyCustomer(MimeMessage message);
void notifyCustomer(JavaMailSender sender);
void notifyCustomer(MessagingException previousError);
~~~

Thay bằng contract mô tả **ý định nghiệp vụ** hoặc **delivery command** có dữ liệu cần thiết:

~~~java
void requestOrderReceipt(
        OrderId orderId,
        CustomerId customerId);
~~~

Hoặc ở ranh giới notification:

~~~java
NotificationRequestResult request(
        NotificationIntent intent);
~~~

Tên `OrderId`, `CustomerId`, `NotificationIntent` là types ứng dụng tự định nghĩa. Chúng không xuất phát từ Spring Mail.

## 5. Phân biệt business event với email command

Một business event mô tả **điều đã xảy ra**, không mô tả tất cả cách gửi:

~~~text
OrderPaid(orderId, customerId, paidAt, version)
~~~

Một notification intent mô tả **mong muốn thông báo đã được xác định**:

~~~text
NotificationIntent(
  eventKey,
  recipientRef,
  templateKey=ORDER_RECEIPT,
  locale,
  channel=EMAIL,
  scheduledAt,
  priority
)
~~~

Một mail delivery job mô tả **đầu việc kỹ thuật**:

~~~text
MailDeliveryJob(
  notificationId,
  providerAccountId,
  senderProfileId,
  renderedContentRef,
  status=PENDING,
  availableAt
)
~~~

Không nên cho domain publish một event tên `SendSmtpMessage` mỗi khi chuyển trạng thái order. Điều đó làm domain lệ thuộc kênh email. Event `OrderPaid` có thể còn được dùng để gửi push notification, cập nhật analytics hoặc khởi tạo invoice.

Ngược lại, một hệ thống notification có thể không cần event bus cho mọi email. Với flow nhỏ, application service tạo một notification intent trực tiếp vẫn hợp lý. Quan trọng là **contract biểu đạt mục đích nghiệp vụ và giữ MIME/SMTP ở bên trong adapter**.

## 6. Ranh giới “đã yêu cầu gửi” và “đã gửi” là khác nhau

Một yêu cầu gửi email thường đi qua:

~~~text
BUSINESS_EVENT
      |
      v
NOTIFICATION_REQUESTED
      |
      v
PENDING / SCHEDULED
      |
      v
CLAIMED / PROCESSING
      |
      v
SMTP_SUBMITTED
      |
      +-- Provider delivery event -> DELIVERED
      +-- Provider bounce event   -> BOUNCED
~~~

`JavaMailSender.send(...)` thành công thường cho biết client đã hoàn thành submission tới SMTP server theo protocol, **không chứng minh email vào inbox** của người nhận. Một số providers có delivery webhooks; một số chỉ cung cấp server logs hoặc không cung cấp tín hiệu chắc chắn.

Vì vậy API cần diễn đạt trung thực:

~~~json
{
  "notificationId": "opaque-notification-583",
  "state": "QUEUED",
  "acceptedForProcessing": true
}
~~~

thay vì trả:

~~~json
{
  "emailDelivered": true
}
~~~

ngay sau khi ghi outbox hoặc sau khi `send()` return.

Một thiết kế lớn thường tách **notification job state**, **submission attempts** và **provider delivery state** nếu nghiệp vụ cần trạng thái chính xác.

## 7. Vẽ dependency rule để tránh framework lấn vào domain

Một sơ đồ module trong modular monolith:

~~~text
com.example.orders
  ├─ domain/
  └─ application/
         |
         | publishes domain event / calls NotificationPort
         v
com.example.notifications
  ├─ api/           Intent, command, query
  ├─ application/   Policy, orchestration, state transitions
  ├─ domain/        Notification model
  └─ spi/           MailDeliveryPort
         ^
         | implemented by
         |
com.example.mail.smtp
  ├─ SpringSmtpMailAdapter
  ├─ MimeMessageFactory
  └─ SmtpConfiguration
~~~

Một nguyên tắc thực dụng:

> **Không import `org.springframework.mail.*` hoặc `jakarta.mail.*` từ domain/application nghiệp vụ**, trừ khi ứng dụng đang chủ ý làm một công cụ quản trị MIME/mail transport.

Ràng buộc này có thể được củng cố bằng module boundaries, package-private implementations, dependency checks hoặc architecture tests. Tên package cụ thể không quan trọng; **trách nhiệm** và chiều dependency mới là điều cần giữ.

## 8. Port–adapter: giữ API ứng dụng độc lập với SMTP

Ở tầng application/notification, định nghĩa interface theo **capability cần sử dụng**, không theo constructor của `JavaMailSenderImpl`:

~~~java
package com.example.notifications.spi;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record OutboundEmail(
        String senderProfileId,
        List<String> recipients,
        String subject,
        String textBody,
        String htmlBody,
        List<EmailAttachmentRef> attachments,
        Map<String, String> safeTags) {
}

public record EmailAttachmentRef(
        String displayFilename,
        String mediaType,
        String storageReference,
        String contentVersion) {
}

public record MailSubmissionReceipt(
        String transportAttemptId,
        String providerReference,
        Instant submittedAt) {
}

public interface MailDeliveryPort {
    MailSubmissionReceipt submit(
            OutboundEmail message);
}
~~~

Đây là **contract minh họa** do ứng dụng sở hữu, không phải type Spring Mail. Trong hệ thống thực nên dùng types mạnh hơn thay vì mọi trường đều là `String` (ví dụ `SenderProfileId`, `RecipientAddress`, `NotificationId`), validate dữ liệu ở boundary và tránh truyền các tags không có schema.

### Tại sao không expose MimeMessage?

Nếu `MailDeliveryPort.submit(...)` nhận `MimeMessage`:

- Caller phải biết MIME nesting, header encoding và Jakarta Mail dependencies.
- Thay transport bằng HTTP email API sẽ khó hơn vì contract lệ thuộc SMTP/MIME.
- Unit test nghiệp vụ phải khởi tạo mail session.
- Kiểm soát Bcc, sender authorization và attachments có thể bị phân tán.

`OutboundEmail` mô tả **email đã được phép gửi** theo góc nhìn notification orchestration. Adapter chuyển nó thành MIME/HTTP payload theo transport cụ thể.

### Tránh contract quá lớn

Một port chứa 50 trường SMTP-specific sẽ trở thành abstraction chỉ đổi tên:

~~~text
smtpHost, smtpPort, smtpUsername, smtpPassword,
startTls, debug, connectionTimeout, mimeBoundary, ...
~~~

Những trường đó phải thuộc **provider profile/infrastructure configuration**, không phải dữ liệu trong mọi notification command.

## 9. Spring Mail adapter triển khai port

Ví dụ một SMTP adapter tập trung xây MIME, attachment và gửi:

~~~java
package com.example.mail.smtp;

import com.example.notifications.spi.MailDeliveryPort;
import com.example.notifications.spi.OutboundEmail;
import com.example.notifications.spi.MailSubmissionReceipt;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.time.Clock;
import java.util.UUID;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringSmtpMailAdapter
        implements MailDeliveryPort {

    private final JavaMailSender sender;
    private final SenderProfileResolver senderProfiles;
    private final AttachmentStorage attachments;
    private final Clock clock;

    public SpringSmtpMailAdapter(
            JavaMailSender sender,
            SenderProfileResolver senderProfiles,
            AttachmentStorage attachments,
            Clock clock) {
        this.sender = sender;
        this.senderProfiles = senderProfiles;
        this.attachments = attachments;
        this.clock = clock;
    }

    @Override
    public MailSubmissionReceipt submit(OutboundEmail request) {
        SenderProfile profile =
                senderProfiles.resolveAuthorized(
                        request.senderProfileId());
        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, true, "UTF-8");

            helper.setFrom(profile.fromAddress());
            helper.setTo(request.recipients().toArray(String[]::new));
            helper.setSubject(request.subject());
            if (request.htmlBody() != null) {
                helper.setText(
                        request.textBody() == null
                                ? "" : request.textBody(),
                        request.htmlBody());
            } else {
                helper.setText(request.textBody(), false);
            }

            for (var attachment : request.attachments()) {
                byte[] bytes = attachments.readBounded(
                        attachment.storageReference(),
                        attachment.contentVersion());

                helper.addAttachment(
                        attachment.displayFilename(),
                        new ByteArrayResource(bytes),
                        attachment.mediaType());
            }

            sender.send(message);

            return new MailSubmissionReceipt(
                    UUID.randomUUID().toString(),
                    null, // SMTP chung không phải lúc nào có provider ID.
                    clock.instant());

        } catch (MessagingException ex) {
            throw new MailPreparationFailure(
                    "MIME_PREPARATION_FAILED", ex);
        } catch (MailException ex) {
            throw new MailTransportFailure(
                    "SMTP_SUBMISSION_FAILED", ex);
        }
    }
}
~~~

`SenderProfileResolver`, `AttachmentStorage`, `SenderProfile`, `MailPreparationFailure` và `MailTransportFailure` là abstractions/exceptions ứng dụng tự định nghĩa. `AttachmentStorage.readBounded` được giả định kiểm tra quyền/version/kích thước trước khi đọc bytes. Ví dụ này ưu tiên làm rõ **boundary** hơn là cung cấp một module có thể copy biên dịch độc lập.

### Những bổ sung bắt buộc cho implementation production

- `MailTransportFailure` không tự phân loại temporary/permanent/unknown; application cần classifier theo SMTP phase và provider response.
- `UUID.randomUUID()` ở đây là ID nhận diện receipt minh họa, **không phải idempotency key được provider công nhận**. Nên dùng attempt ID đã được tạo/lưu từ workflow trước submission.
- Adapter cần bảo đảm sender profile thuộc tenant/route đã được authorization ở application layer, có thể kiểm tra phòng vệ tại adapter.
- Các địa chỉ, header, filename và body phải qua validation phù hợp.
- Không đọc attachment không giới hạn vào RAM cho job lớn; có thể dùng nguồn có thể mở lại hoặc file-backed.
- Không leak raw `MimeMessage`/`MessagingException` ra domain.
- Không đồng nhất khi `send(...)` thành công với delivery cuối cùng.
- Nếu transport dùng HTTP API thay SMTP, tạo adapter khác triển khai cùng capability contract, nhưng vẫn phải map outcome đúng semantics của API đó.

## 10. Cấu hình SMTP phải được cô lập ở infrastructure

Trong Spring Boot, cấu hình đơn giản:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 15000
      mail.smtp.writetimeout: 15000
~~~

Các giá trị thời gian và endpoint trên chỉ là ví dụ, không phải cấu hình của provider cụ thể. Secret thật phải đến từ secret manager/runtime injection, không được commit vào source.

Ranh giới đúng:

~~~text
orders/application:
  requestOrderReceipt(orderId)

notifications/application:
  chooseTemplateAndRecipient(...)
  enqueue(...)

mail/infrastructure:
  read spring.mail.*
  create JavaMailSender
  submit MIME message
~~~

Không nên làm:

~~~java
// OrderService biết SMTP host và password là smell rõ ràng.
@Value("${spring.mail.host}")
String smtpHost;

@Value("${spring.mail.password}")
String smtpPassword;
~~~

Đặt tên class `EmailService` rồi cho tất cả business modules import class đó chưa chắc là một boundary tốt. Hãy kiểm tra: interface có mô tả **yêu cầu thông báo** hay đang cho business layer điều khiển transport/raw MIME?

### Nhiều SMTP providers

Khi có nhiều tuyến gửi, nên dùng các sender/adapter được cấu hình riêng, với `@Qualifier` hoặc registry rõ ràng; không thay đổi host/username/password trên một `JavaMailSenderImpl` singleton đang được nhiều thread dùng. Provider routing là **chính sách application**, còn kết nối/authentication thuộc **adapter/configuration**.

## 11. Tách template rendering khỏi SMTP transport

Template không chỉ là `String subject` và `String html`. Nó còn có:

- Template key và version.
- Ngôn ngữ/locale.
- Branding theo tenant.
- Variables từ business data.
- HTML escaping/sanitization.
- Plain-text fallback.
- Quy tắc legal footer/opt-out.
- A/B testing hoặc biến thể.

Một luồng rõ ràng:

~~~text
OrderPaid event
     |
     v
Select template key ORDER_RECEIPT
     |
     v
Resolve locale + approved tenant brand
     |
     v
Load safe template variables
     |
     v
Render subject + plain text + HTML
     |
     v
Validate content and store snapshot/version
     |
     v
MailDeliveryPort.submit(...)
~~~

**Ai sở hữu template?** Có thể là Notification module, Marketing Content service, hoặc một domain cụ thể (ví dụ hóa đơn pháp lý bắt buộc giữ nội dung bất biến). Quyết định dựa trên ownership nội dung và lifecycle, nhưng **không buộc transport adapter phải biết cách tính thuế, trạng thái đơn hàng hoặc quyền truy cập tài khoản**.

### Template động và retry

Khi một mail job retry sau 2 giờ, template/dữ liệu có thể đã thay đổi. Hai lựa chọn:

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Snapshot rendered content ở lúc tạo intent | Nội dung ổn định giữa các attempts | Lưu nhiều PII, phải bảo vệ retention |
| Render ở thời điểm submit | Có thể phản ánh thông tin mới nhất | Template và dữ liệu thay đổi khiến nội dung khác |

Chọn theo nghiệp vụ. **Hóa đơn đã phát hành** thường cần nội dung/version đáng tin cậy; **nhắc lịch hẹn** có thể cần xác minh lịch hiện tại trước khi gửi. Nếu render động, cần policy về việc nội dung đã được xét duyệt, nguồn dữ liệu và idempotency.

## 12. Attachment thuộc content boundary, không thuộc domain transport

Đối với file PDF/CSV/XLSX:

~~~text
Domain/Application:
  invoiceId, documentVersion
          |
          v
Document service:
  produces approved PDF
          |
          v
Attachment storage:
  payloadRef, mediaType, displayFilename
          |
          v
Mail adapter:
  ByteArrayResource / FileSystemResource
  MimeMessageHelper.addAttachment(...)
~~~

Đừng để `OrderService` phải biết `ByteArrayResource` hoặc `MimeMessageHelper`. Ngược lại, mail transport không cần biết cách tính tổng tiền hóa đơn.

Với tệp lớn, mail adapter cần nguồn có thể mở lại stream và giới hạn kích thước; dùng `ByteArrayResource` phù hợp cho payload vừa phải trong bộ nhớ. **Một request từ domain không nên chứa SMTP MIME bytes raw nếu đó là nội dung có thể lưu bằng secure storage reference.**

Các ranh giới cần kiểm soát:

- Quyền truy cập attachment theo tenant và job.
- Payload version/immutability.
- Max bytes và chống file nguy hiểm.
- Filename hiển thị an toàn; không lộ storage path.
- MIME content type đúng nội dung.
- Thời hạn giữ payload cho retries.
- Xóa dữ liệu theo retention sau khi không còn cần thiết.

## 13. Notification policy: ai được gửi tới ai?

Tầng Spring Mail **không tự quyết định** một thông báo có hợp pháp/hợp lệ cho người nhận hay không. Notification policy cần trả lời:

1. Email này thuộc loại transactional, security, service hay marketing?
2. Người nhận có địa chỉ được xác minh/chấp nhận theo quy tắc sản phẩm không?
3. Có suppression list, unsubscribe hoặc bounced-address history không?
4. Tenant được phép dùng sender profile/domain nào?
5. Có quiet hours hoặc giới hạn thời gian gửi không?
6. Nội dung có hết hạn nếu đợi quá lâu (OTP, password reset link) không?
7. Có cần ưu tiên email bảo mật hơn batch marketing?
8. Có nên chuyển sang channel khác khi email không phù hợp?

**Policy thuộc ứng dụng/notification orchestration**, nhưng adapter vẫn nên có phòng vệ kỹ thuật: không cho caller chọn arbitrary SMTP endpoint, credentials, raw From hoặc headers chưa được duyệt.

Một mail job được đặt lịch tuần trước không tự động giữ quyền gửi hôm nay. Với notification chịu ràng buộc consent/suppression, cần **đánh giá lại eligibility trước submission** theo quy tắc đã thống nhất.

## 14. Ranh giới transaction: database nghiệp vụ không rollback SMTP

Một lỗi kiến trúc rất thường gặp:

~~~java
@Transactional
public void payOrder(OrderId orderId) {
    orderRepository.markPaid(orderId);
    mailSender.send(buildEmail(orderId));
}
~~~

Ở đây, nếu SMTP success rồi transaction database rollback, khách hàng có thể nhận email “đã thanh toán” dù order không được lưu ở trạng thái paid. Nếu SMTP chậm, transaction giữ database connection/locks lâu không cần thiết. Nếu SMTP lỗi, business transaction có thể rollback dù thanh toán đã hợp lệ — đây có thể là hành vi hoàn toàn sai với nghiệp vụ.

Không thể xem `JavaMailSender.send(...)` là một phần của ACID transaction với database bằng cách đặt nó trong method `@Transactional`.

### Một kiến trúc ổn định hơn: transactional outbox

~~~text
BEGIN DATABASE TRANSACTION
  Update business aggregate
  Insert notification intent/outbox row
COMMIT
        |
        v
Dispatcher reads committed outbox row
        |
        v
Rate/eligibility checks
        |
        v
SMTP submission outside business transaction
        |
        v
Persist attempt/status
~~~

Nhờ đó:

- Nếu transaction rollback, cả business update và outbox intent đều không tồn tại.
- Nếu transaction commit và app crash ngay sau đó, outbox row vẫn còn.
- Nếu SMTP outage, nghiệp vụ chính không phải giữ network connection hoặc rollback.
- Scheduler có thể retry sau restart.
- Hệ thống có audit để biết notification đã được yêu cầu và xử lý tới đâu.

### Ví dụ application service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderPaymentApplication {
    private final OrderRepository orders;
    private final NotificationOutbox outbox;

    public OrderPaymentApplication(
            OrderRepository orders,
            NotificationOutbox outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmPayment(OrderId orderId) {
        Order order = orders.confirmPayment(orderId);
        outbox.insertIfAbsent(
                NotificationIntent.orderPaid(
                        order.id(),
                        order.customerId(),
                        order.paymentVersion()));
    }
}
~~~

Các classes `OrderRepository`, `NotificationOutbox`, `OrderId`, `NotificationIntent` là abstractions ứng dụng. `insertIfAbsent` cần unique constraint/UPSERT với idempotency key; không đủ nếu chỉ kiểm tra `exists` trước rồi insert không có cơ chế chống race.

### Khi business data và outbox nằm ở hai databases?

Không thể tự nhận tính nguyên tử chỉ vì hai repository methods đều có `@Transactional` nếu chúng dùng transaction managers/databases khác nhau. Các lựa chọn:

- Lưu outbox cạnh source business transaction và dùng CDC/event relay đáng tin.
- Một event log/transaction boundary chung phù hợp.
- Cơ chế phối hợp và reconciliation được thiết kế rõ khi không thể atomic.

Không gắn nhãn “transactional outbox” cho hai network writes độc lập rồi mặc định không bao giờ mất event.

## 15. @TransactionalEventListener(AFTER_COMMIT) không thay durable outbox

Một event listener sau commit:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderPaid(OrderPaid event) {
    notificationGateway.requestReceipt(event.orderId());
}
~~~

có thể giúp tránh gửi email trước khi transaction commit. Nhưng đây thường vẫn là một listener chạy trong **process hiện tại**:

~~~text
Order DB commit succeeds
   |
   +-- Process crashes before listener can persist intent
   |
Notification request is lost
~~~

Listener sau commit phù hợp với **best-effort notification** khi mất một event được chấp nhận hoặc có cơ chế reconciliation khác. Đối với thông báo có yêu cầu không bỏ sót, cần ghi **intent/outbox trong cùng transaction** hoặc một mô hình durable event relay tương đương.

Tương tự, `@Async` không tự khiến event trở thành durable. Nó chỉ chuyển thời điểm thực thi sang một executor và có thể mất work khi process chết.

### Giữ ranh giới nhất quán

Nếu có outbox:

~~~text
Transactional business event
   -> durable outbox
   -> asynchronous notification processor
   -> Spring Mail adapter
~~~

Nếu dùng listener best-effort:

~~~text
Transactional business event
   -> AFTER_COMMIT listener
   -> notification policy
   -> Spring Mail
~~~

Hãy **nêu rõ guarantee** của luồng tương ứng trong ADR hoặc service contract; không mô tả hai luồng có độ tin cậy như nhau.

## 16. Ranh giới retry: ai quyết định được phép thử lại?

Một `MailException` có thể là:

- Sai cấu hình hoặc xác thực SMTP.
- Provider từ chối tạm thời.
- Người nhận không hợp lệ.
- Mất kết nối trước hoặc sau khi provider nhận DATA.
- Lỗi dựng MIME/attachment xảy ra trước transport.
- Không thể xác định outcome ở client do timeout.

**Adapter** biết ngữ cảnh kỹ thuật như SMTP response, transport phase và provider-specific codes. **Workflow/application** biết số attempts, business deadline, loại email, đã có provider feedback hay chưa và có thể chấp nhận duplicate không.

Vì vậy phân quyền hợp lý:

~~~text
Transport adapter:
  classify technical outcome
    ACCEPTED
    TEMPORARY_REJECTED
    PERMANENT_REJECTED
    AUTH_OR_CONFIGURATION_ERROR
    UNKNOWN_OUTCOME
          |
          v
Delivery workflow:
  decide retry, pause, fail, expire, reconcile
  based on attempts, deadline, business priority
~~~

Không nên để `OrderService` bắt mọi `MailException` và gọi `mailSender.send(...)` ba lần trong một vòng lặp. Domain không đủ thông tin để quyết định SMTP accepted hay unknown và có thể gây gửi trùng.

### Ví dụ contract technical outcome

~~~java
public enum SubmissionOutcomeKind {
    ACCEPTED,
    REJECTED_TEMPORARY,
    REJECTED_PERMANENT,
    ROUTE_UNAVAILABLE,
    UNKNOWN
}

public record SubmissionOutcome(
        SubmissionOutcomeKind kind,
        String safeReasonCode,
        String providerReference) {
}
~~~

Contract này có thể phù hợp hơn `throws MailException` ở ranh giới notification workflow. Nhưng adapter không được suy đoán sai rằng mọi exception là temporary. Nếu không chắc liệu server đã accepted, trả `UNKNOWN` và để workflow xử lý thận trọng.

## 17. SMTP outcome UNKNOWN: ranh giới không thể làm nguyên tử

Một tình huống:

~~~text
Worker claims job #583
    |
    v
SMTP sends DATA
    |
    v
Provider accepts message
    |
    v
Network breaks before client observes final reply
    |
    v
Worker sees exception
    |
    v
Database still says PROCESSING
~~~

Nếu worker sau nhìn lease timeout rồi gửi lại ngay, người nhận có thể nhận hai email. `FOR UPDATE SKIP LOCKED`, `@Transactional` và `@Async` không giải quyết được atomicity giữa database và SMTP.

Các lựa chọn:

1. Lưu attempt identity và trạng thái `UNKNOWN` khi chưa rõ kết quả.
2. Đối soát provider message trace nếu có.
3. Dùng provider idempotency feature **chỉ khi provider thật sự cung cấp và cam kết semantics** đó.
4. Giữ business idempotency key để tránh tạo trùng intent ban đầu.
5. Có quy tắc retry/failover theo rủi ro duplicate của từng notification type.
6. Không nhầm header `Message-ID` với một exactly-once delivery guarantee.

Đây là ranh giới quan trọng giữa **thông báo có thể xử lý at-least-once** và **giao email chính xác một lần** — yêu cầu thứ hai thường không thể cam kết bằng SMTP thuần trong điều kiện failure thực tế.

### Mô tả guarantee trung thực

Một service contract có thể nói:

> “Mọi notification intent đã commit sẽ được duy trì trong outbox và thử gửi theo retry policy. Có khả năng duplicate khi provider outcome không chắc chắn; hệ thống lưu attempts và có quy trình đối soát.”

Điều này rõ ràng và an toàn hơn lời hứa “gửi đúng một email, không bao giờ mất hay trùng” mà không có cơ chế chứng minh.

## 18. Ranh giới scheduler và state machine

Nếu một email phải gửi 09:00, Spring Mail không cần biết lịch nghiệp vụ. Dispatcher có thể lưu:

~~~text
notification_id
status = PENDING
scheduled_at = 2026-11-15T09:00:00Z
available_at = 2026-11-15T09:00:00Z
attempt_count = 0
expires_at = nullable
~~~

Một state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: due and owner acquired
    PENDING --> CANCELLED: cancel before submission
    PENDING --> EXPIRED: deadline passed
    CLAIMED --> PROCESSING: record attempt
    CLAIMED --> PENDING: safe release
    PROCESSING --> SUBMITTED: provider accepted
    PROCESSING --> RETRY: classified temporary rejection
    PROCESSING --> FAILED: permanent error
    PROCESSING --> UNKNOWN: ambiguous outcome
    RETRY --> CLAIMED: next available time
    UNKNOWN --> SUBMITTED: reconciliation confirmed
    UNKNOWN --> RETRY: approved replay policy
~~~

Những status này là enum **ứng dụng tự định nghĩa**. Không có `PENDING`, `RETRY` hay `UNKNOWN` như một lifecycle job mặc định trong `JavaMailSender`.

### scheduledAt và availableAt không giống nhau

- `scheduled_at`: thời điểm nghiệp vụ mong muốn gửi, nên giữ để đo độ trễ.
- `available_at` hoặc `next_attempt_at`: thời điểm sớm nhất được retry/defer vì quota, lỗi hoặc policy.

Khi provider lỗi, dời `available_at` chứ không xóa lịch gốc. Khi job quá hạn (ví dụ OTP), workflow quyết định `EXPIRED` thay vì gửi muộn một nội dung không còn hợp lệ.

### Scheduler chỉ là người đánh thức

Spring `@Scheduled` hoặc Quartz có thể kích hoạt dispatcher, nhưng **database/outbox là nguồn trạng thái bền vững**. Không tạo hàng nghìn `ScheduledFuture` chỉ trong RAM rồi coi đó là durable scheduling.

## 19. Multi-worker claim và ownership của workflow

Nếu hệ thống có nhiều replicas, mỗi replica có thể chạy scheduler. Hai worker không được cùng xử lý một job theo cách không kiểm soát:

~~~text
Worker A -> SELECT PENDING job #583
Worker B -> SELECT PENDING job #583
Worker A -> SMTP send
Worker B -> SMTP send
~~~

Một phương án PostgreSQL là atomic claim với `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH selected AS (
    SELECT id
    FROM notification_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND available_at <= CURRENT_TIMESTAMP
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE notification_outbox AS job
SET status = 'CLAIMED',
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM selected
WHERE job.id = selected.id
RETURNING job.id, job.claim_token;
~~~

Lệnh claim chạy trong **transaction ngắn**. Không giữ transaction và row lock suốt network SMTP call. Khi lưu kết quả, update phải kiểm tra `claim_token` và expected state để tránh stale worker ghi đè.

### Lease hết hạn không có nghĩa chưa gửi

Khi worker crash sau SMTP accepted nhưng trước DB update, job có thể trông như đang PROCESSING với lease expired. Recovery cần biết attempt có thể đã bắt đầu, không tự gửi lại mà không xem xét `UNKNOWN` và policy.

### Tách concurrency control và rate limit

`ThreadPoolTaskExecutor.maxPoolSize` giới hạn số worker đồng thời; nó không tự giới hạn số messages/second hoặc daily recipient quota. Workflow/dispatcher cần rate admission riêng khi cùng provider account bị nhiều tenants/services chia sẻ.

## 20. Ranh giới API: nhận yêu cầu gửi, không nhận raw SMTP command

Với một Notification Service riêng, API nên tiếp nhận một **ý định thông báo đã được xác thực**:

~~~http
POST /internal/notifications
Content-Type: application/json
Idempotency-Key: ORDER_PAID-583-v1

{
  "type": "ORDER_RECEIPT",
  "businessRef": "ORDER-583",
  "channel": "EMAIL",
  "locale": "vi-VN",
  "scheduledAt": "2026-11-15T09:00:00+07:00"
}
~~~

Server dựa trên identity của caller để xác định tenant, quyền đối với `businessRef`, loại notification được phép gửi, recipient và sender profile đã duyệt. Không nên để client tùy ý:

~~~json
{
  "smtpHost": "10.0.0.1",
  "smtpPort": 25,
  "smtpPassword": "anything",
  "from": "admin@example.com",
  "unlimitedRetries": true
}
~~~

Đây vừa là vi phạm domain boundary vừa có thể biến notification endpoint thành relay/SSRF surface.

### Response đồng bộ nên có semantics nào?

Khi API đã lưu notification intent:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "notificationId": "notif-opaque-583",
  "status": "QUEUED"
}
~~~

`202 Accepted` trong ví dụ nói rằng **yêu cầu đã được nhận để xử lý**, không phải SMTP delivered. Nếu một API lựa chọn submit SMTP đồng bộ, contract phải nói rõ đó là synchronous submission và vẫn không khẳng định inbox delivery.

### Idempotency key không được dùng lại tùy tiện

Một retry HTTP sau timeout có thể lặp cùng `Idempotency-Key` để lấy lại kết quả. Nhưng gửi lại hóa đơn theo yêu cầu hợp lệ lần hai có thể cần event/version key khác. Định nghĩa phạm vi unique theo tenant/type/business event, không cấm vĩnh viễn mọi email cùng người nhận.

## 21. Event contract: business không nên phát MIME bytes

Một event để Notification Service tiêu thụ:

~~~json
{
  "eventId": "evt-583-1",
  "eventType": "OrderPaid",
  "aggregateId": "ORDER-583",
  "aggregateVersion": 7,
  "tenantRef": "tenant-opaque",
  "occurredAt": "2026-11-12T09:00:00Z"
}
~~~

Một event **không nhất thiết** phải chứa email address, HTML body hoặc attachment bytes. Notification worker có thể lấy dữ liệu cần thiết qua một approved read model hoặc snapshot trong event/outbox, tùy consistency/retention yêu cầu.

Các câu hỏi khi thiết kế event:

- Event có **identity** ổn định để chống xử lý lặp không?
- Nó có version/schema để consumer nâng cấp độc lập không?
- Người tiêu thụ có đủ dữ liệu mà không phải gọi ngược domain bằng N+1 network requests không?
- Dữ liệu có bị thay đổi trước thời điểm render không?
- Event chứa dữ liệu nhạy cảm nào và lưu trong broker bao lâu?
- Nếu Notification Service down nhiều ngày, nó có thể replay từ nguồn nào?
- Nếu event đến sai thứ tự, worker sẽ phản ứng thế nào?

Không mặc định broker bảo đảm exactly-once business side effects; consumer vẫn phải idempotent. Nếu chỉ publish event sau database commit mà không có durable outbox, vẫn có cửa sổ crash giữa commit và publish.

## 22. Chọn cùng process, module riêng hay microservice riêng?

Ranh giới **logic** không buộc phải là ranh giới **deployment**. Các mức tách thường gặp:

| Phương án | Khi phù hợp | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Tách package trong một app | Ứng dụng nhỏ, một team | Thực hiện nhanh, ít hạ tầng | Boundary dễ bị xuyên qua |
| Modular monolith | Nhiều modules, vẫn chung deployment | Kiểm soát dependency, transaction/outbox dễ hơn | Scale/deploy vẫn chung |
| Worker process tách từ cùng codebase | SMTP workload khác web workload | Scale/shutdown độc lập, giảm ảnh hưởng HTTP | Cần queue/outbox và ownership |
| Notification microservice | Nhiều product teams/channels, cần vận hành riêng | API/SLA/scale độc lập, centralized policy | Network, broker, dữ liệu/chủ quyền, distributed failure |
| Managed email platform | Team không muốn tự vận hành sâu | Hạ tầng gửi/bounce/reputation có thể được cung cấp | Vendor semantics, quota, data governance, lock-in |

Không có một kiến trúc đúng cho mọi tổ chức. Dùng các tiêu chí:

1. Số lượng business teams cùng phụ thuộc notification.
2. Tần suất thay template/policy/provider.
3. Khối lượng và biến động email traffic.
4. Yêu cầu SLA/observability/audit.
5. Nhu cầu cô lập bảo mật và secrets.
6. Khả năng vận hành broker, outbox, queue và deployment độc lập.
7. Ranh giới dữ liệu giữa tenants/regions.
8. Chi phí latency, độ phức tạp và incident coordination.

### Khi nào không nên tách microservice ngay?

Nếu chỉ một ứng dụng gửi vài loại email và team chưa có hạ tầng messaging/observability vững, tạo một Email Service network hop có thể tăng lỗi mà không tạo giá trị tương xứng. Một **modular monolith** với `NotificationPort`, outbox và `SpringSmtpMailAdapter` thường cho phép thay đổi sau này mà không cần lập tức vận hành service mới.

### Khi nào nên tách?

Nếu nhiều đội liên tục sao chép SMTP credentials, templates, delivery logic; traffic batch làm ảnh hưởng HTTP latency; hoặc security/compliance yêu cầu chỉ một workload có quyền truy cập mail secrets, có lý do rõ ràng để tách deployment. Khi tách, giữ API/event contract bền vững thay vì chuyển nguyên các entity JPA/MimeMessage qua HTTP.

## 23. Đừng nhầm “shared Java library” với “central notification service”

Một thư viện dùng chung:

~~~text
mail-common.jar
  +-- buildMime(...)
  +-- send(...)
~~~

có thể loại bỏ một số code lặp, nhưng **mỗi application vẫn tự**:

- Cấu hình credentials.
- Gửi trực tiếp provider và tiêu thụ account quota.
- Quyết định retry và thời điểm gửi.
- Lưu logs/status, nếu có.
- Áp consent và suppression.
- Deploy khi thư viện thay đổi.

Ngược lại, một notification service tập trung hóa có thể sở hữu orchestration, quota, outbox, secrets và delivery tracking. Nhưng nó thêm network boundary, idempotency contract, backlog và vận hành queue.

**Quyết định chia sẻ code và chia sẻ runtime không giống nhau.** Không gọi một JAR chung là “mail platform” nếu quyền/nguồn trạng thái vẫn phân tán giữa nhiều apps.

### Khi nào shared library vẫn hữu ích?

Với các ứng dụng cần gửi thông báo local có kiểm soát, library có thể cung cấp:

- Typed `NotificationClient`.
- Validation cho request schemas.
- OpenTelemetry correlation.
- Một số helper MIME/attachment ở tầng infrastructure.
- Convention về safe reason codes.

Nhưng library không nên ép business services phụ thuộc trực tiếp `JavaMailSenderImpl` chỉ để có một wrapper gọi `send()`.

## 24. Ai sở hữu recipient resolution?

Một email gửi hóa đơn cần địa chỉ người nhận. Có nhiều lựa chọn:

**A. Domain application xác định recipient:**

~~~text
InvoiceIssued
   -> domain produces approved recipient reference
   -> NotificationIntent
~~~

Ưu điểm: domain biết rõ ai có quyền nhận hóa đơn. Rủi ro: email address bị snapshot có thể cũ hoặc lộ qua event.

**B. Notification application đọc một directory/profile service:**

~~~text
InvoiceIssued(customerId)
   -> query customer contact preferences
   -> resolve email address
~~~

Ưu điểm: tách PII khỏi event, địa chỉ có thể cập nhật. Rủi ro: đọc dữ liệu sau thời gian trì hoãn có thể trỏ tới người không còn liên quan hoặc bị access denied, gây khác biệt so với sự kiện gốc.

### Quy tắc thực dụng

- **Domain** xác định **đối tượng được phép nhận** theo nghiệp vụ (customer/account/participant).
- **Notification policy** xác định **địa chỉ/kênh có thể dùng** và preference hiện tại.
- **Transport adapter** chỉ nhận **địa chỉ đã được phê duyệt** và thực hiện submission.

Đối với tài liệu nhạy cảm, cần binding của người nhận tới giao dịch/version đã phát hành. Không cho adapter đọc bảng customer chung rồi tự quyết định người nhận bất kỳ.

## 25. Multi-tenancy: boundary bảo mật và quota phải đi cùng nhau

Một Notification Service phục vụ nhiều tenant cần những trường:

~~~text
tenantId
notificationId
businessEventKey
templateKey
senderProfileId
providerAccountId
recipientRef
status
~~~

Trước khi chuyển sang SMTP:

~~~text
Trusted caller/claim
    |
    v
Resolve tenant from authenticated context
    |
    v
Validate business reference ownership
    |
    v
Check sender profile and template permissions
    |
    v
Apply tenant + provider account quotas
    |
    v
Submit through approved provider adapter
~~~

Không tin `tenantId` hoặc `smtpHost` từ request của caller nếu chưa authorization. Một tenant không được phép chọn sender profile của tenant khác hoặc ép workload gửi từ một account quản trị.

### Scope quota và scope secret có thể khác nhau

Hai credentials có thể thuộc cùng một provider account và chia quota. Credential rotation không tự reset quota. Nếu tenant A/B dùng chung account, cần account-wide gate ngoài tenant gates; nếu dùng account độc lập, không gộp nhầm quota.

### Tránh leak dữ liệu qua observability

Không dùng recipient email, subject, raw MIME hoặc message body làm metric label. Với rất nhiều tenants, `tenantId` trên mọi time series cũng tạo cardinality cao. Có thể tổng hợp theo tier/lane/provider rồi tra ID chi tiết ở hệ audit được phân quyền.

## 26. Tách outbound gửi mail và inbound đọc hộp thư

`JavaMailSender` được thiết kế cho **gửi** mail. Đọc hộp thư qua IMAP/POP3 cần Jakarta Mail `Store`/`Folder` hoặc Spring Integration Mail inbound adapters.

Hai luồng khác nhau:

~~~text
Outbound:
  Business event
      -> Notification workflow
      -> Spring Mail/SMTP adapter
      -> Provider

Inbound:
  Provider mailbox
      -> IMAP/POP3 receiver
      -> Dedup/checkpoint
      -> Message validation/security
      -> Inbound business command/event
~~~

Không nên cho inbound parser gọi trực tiếp các repository nghiệp vụ tùy ý sau khi đọc body email. Email là dữ liệu **không tin cậy**; cần xác thực sender/workflow, chống spoofing, validate attachment, idempotency và mapping tới command có authorization.

### Vì sao có thể tách deployment?

Inbound receiver cần IMAP connection lifecycle, UID/UIDVALIDITY checkpoints, folder state và reconnect policy, trong khi outbound dispatcher cần SMTP quota và submission attempts. Chúng có failure modes và scaling khác nhau.

Nếu hệ thống chỉ gửi mail, đừng tạo inbound service không cần thiết. Nếu có inbound xử lý yêu cầu, ít nhất nên tách **module và credentials** rõ ràng; không dùng chung một “MailService” với mọi quyền đọc/ghi mailbox.

## 27. Phân chia ownership cho từng concern

Một bảng trách nhiệm giúp các nhóm không đẩy lỗi qua lại:

| Concern | Đội hoặc bounded context nên sở hữu | Contract cần rõ |
|---|---|---|
| Điều kiện business để gửi | Domain team | Business event/notification request |
| Người nhận theo nghiệp vụ | Domain + profile policy | Recipient reference/eligibility |
| Consent/suppression | Notification/consent authority | Check ở thời điểm gửi |
| Template/locale/branding | Content/notification team | Version, variables, approval |
| Tạo PDF/tài liệu | Document/domain service | Immutable payload ref, MIME type |
| Outbox/attempt lifecycle | Notification platform | Status, retries, idempotency |
| SMTP credentials/TLS | Mail infrastructure/platform | Secret access, rotation |
| Provider quota/fairness | Delivery operations/platform | Account/tenant rate budgets |
| Delivery/bounce webhooks | Provider integration | Verified event and correlation |
| SLO/alerts | Platform + product owner | SLO theo loại thông báo |
| Incident replay | Delivery operations có policy | Approval, audit, duplicate risk |

Đây là một đề xuất ownership, không phải sơ đồ tổ chức bắt buộc. Trong tổ chức nhỏ, một team có thể sở hữu nhiều hàng; điều cần tránh là không ai chịu trách nhiệm vì logic bị rải ở mọi service.

## 28. Phạm vi lỗi (blast radius) và bulkhead isolation

Một hệ thống lớn thường có nhiều loại email:

~~~text
SECURITY        OTP, password reset, login alert
TRANSACTIONAL   Order receipt, payment confirmation
OPERATIONAL     Error report, system notification
BULK            Newsletter, campaign
~~~

Nếu tất cả dùng một FIFO queue và một executor chung, 100.000 bulk jobs có thể làm OTP chờ quá lâu. Nếu một provider bị treo, các threads bị giữ có thể gây nghẽn cả HTTP requests.

Để hạn chế blast radius:

1. Tách **notification lanes** theo SLA/loại nội dung.
2. Dùng bounded executor/queues và backpressure.
3. Áp quota theo **provider account** và **tenant**.
4. Giới hạn SMTP concurrency riêng từng account/route.
5. Dùng ưu tiên và fair scheduling, không chỉ FIFO đơn giản.
6. Đặt timeout connect/read/write, retry backoff và circuit breaker.
7. Không để bulk provider outage làm rollback domain transactions.
8. Giữ durable intents khi quota/provider không khả dụng.

Tách `ThreadPoolTaskExecutor` cho mail so với tác vụ báo cáo là hữu ích, nhưng **không tạo quota toàn cụm**. Cùng một account có thể được 10 pods gọi đồng thời; cần shared rate admission khi provider quota áp ở account scope.

### Đừng quá tin “tách service” là tách lỗi hoàn toàn

Hai microservices vẫn có thể chia một database connection pool, Redis quota store, provider account hoặc tenant budget. Tách deployment giúp hạn chế một số lỗi, nhưng blast radius thật sự phụ thuộc **shared resources** và failure isolation của chúng.

## 29. Security boundary: không phải service nào cũng biết SMTP secret

Trong hệ thống lớn, quyền đọc SMTP password/API token nên chỉ cấp cho workload cần thực sự submit email.

~~~text
Order service       -> no SMTP credential
Billing service     -> no SMTP credential
Notification API    -> possibly no direct SMTP credential
Mail dispatcher     -> mail-specific credential
Provider callback   -> webhook verification secret
~~~

Các lớp bảo vệ:

- Secret manager và workload identity/permissions.
- Network egress chỉ tới SMTP/API endpoints đã phê duyệt.
- TLS, hostname verification và version policy phù hợp.
- Sender/domain verification, SPF/DKIM/DMARC ở provider/domain.
- Không cho caller tùy ý đặt `From`, `Reply-To` hoặc endpoint.
- RBAC với template, payload, mail job và support tools.
- Audit việc đổi sender profile, credential và quota policy.
- Không log raw message, SMTP AUTH payload hay token.
- Rotation và revoke có quy trình tránh gián đoạn không cần thiết.

### Tránh credential trong outbox

Outbox chỉ nên lưu:

~~~text
senderProfileId=ORDERS
providerAccountId=primary-prod
~~~

thay vì:

~~~text
smtpPassword=...
oauthAccessToken=...
~~~

Worker đọc secret tại runtime theo profile đã được authorization. Nếu rotate key, các job đang chờ không bị buộc giữ secret cũ trong database.

### Provider failover phải tôn trọng quyền sender

Một `From` được verified ở Provider A chưa chắc được phép gửi qua B. Khi failover, application kiểm tra sender eligibility và policy; infrastructure adapter kết nối route B với credentials riêng. Không tự động “thay host” khi account A lỗi và gửi cùng From qua B bất chấp SPF/DKIM/DMARC.

## 30. Delivery feedback là một inbound event boundary riêng

Nếu provider có webhook báo `delivered`, `bounced`, `complained` hoặc `deferred`:

~~~text
Email provider
     |
     v
Webhook endpoint
     |
     v
Verify signature / timestamp / replay protection
     |
     v
Normalize provider event
     |
     v
Correlate to provider message / submission attempt
     |
     v
Idempotently update delivery state
     |
     v
Business events only when policy requires
~~~

Không cho một HTTP webhook public cập nhật thẳng `orders.status` chỉ vì payload có một `orderId`. Provider events có thể lặp, tới sai thứ tự, bị delay hoặc bị giả mạo nếu thiếu xác thực.

Những trường cần xem:

| Trường | Lý do |
|---|---|
| Provider event ID | Dedup callback |
| Provider message/attempt ID | Correlation |
| Event type | Delivered, bounced, deferred, complaint |
| Provider event time | Thời điểm được provider báo |
| Received time | Thời điểm ứng dụng nhận |
| Verified sender/signature | Xác thực nguồn |
| Tenant/account scope | Ngăn cập nhật sai tenant |

### Một email nhiều người nhận

Nếu một SMTP submission gồm nhiều To/Cc/Bcc, delivery/bounce có thể khác nhau theo từng recipient. Một job-level `delivered=true` có thể không đủ; cân nhắc recipient-level outcome storage. Nhưng không phải mọi provider cung cấp feedback per recipient; hệ thống cần trạng thái `NOT_TRACKED` hoặc null khi không có evidence, không tự suy luận giao thành công.

## 31. Quan sát theo ý định, lần gửi và delivery

Một bộ chỉ số hữu ích cho vận hành:

| Metric | Trả lời câu hỏi |
|---|---|
| `notification_intent_created_total` | Bao nhiêu yêu cầu hợp lệ được tạo? |
| `notification_outbox_ready` | Có bao nhiêu job tới giờ chưa gửi? |
| `notification_oldest_due_age_seconds` | Job trễ nhất đã chờ bao lâu? |
| `mail_submission_attempt_total` | Có bao nhiêu lần thực sự gọi provider? |
| `mail_submission_accepted_total` | Provider accepted bao nhiêu lần? |
| `mail_submission_failure_total` | Thất bại ở phase nào? |
| `mail_unknown_outcome_total` | Bao nhiêu lần cần đối soát? |
| `mail_quota_denied_total` | Bao nhiêu lần bị giới hạn bởi quota? |
| `mail_provider_throttle_total` | Provider phản hồi throttling bao nhiêu lần? |
| `mail_delivery_event_total` | Bao nhiêu delivered/bounced nếu có tracking? |
| `mail_notification_expired_total` | Bao nhiêu intent hết thời hạn? |
| `mail_dispatch_lag_seconds` | Mất bao lâu từ lịch đến lần attempt? |

**Không gọi số `mailSender.send(...)` không ném exception là “delivered count”**. Nó chỉ đại diện cho submission accepted theo semantics adapter.

### Trace xuyên các boundaries

~~~text
trace/span: OrderPayment.confirm
      |
      v
eventId / notificationId
      |
      v
Outbox claim
      |
      v
submissionAttemptId
      |
      v
providerReference (if available)
      |
      v
provider callback (possibly hours later)
~~~

Traces không luôn tồn tại lâu bằng thời gian chờ email; cần correlation IDs lưu bền vững trong database/attempt history. Không đặt recipient email, subject hoặc raw MIME vào telemetry attributes nếu không có chính sách bảo vệ phù hợp.

### Log theo reason code an toàn

~~~text
event=mail_submission_failed
notificationId=opaque-id
attemptId=opaque-attempt
providerProfile=PRIMARY
phase=SMTP_DATA
reasonCode=SMTP_OUTCOME_UNKNOWN
tenantTier=BUSINESS
~~~

Không mặc định log nguyên `MailException.getMessage()`: SMTP provider có thể echo recipient hoặc details khác.

## 32. SLO của Notification Platform không thể chỉ là SMTP uptime

Các mục tiêu thường gặp:

- Phần trăm email giao dịch **được bắt đầu submit** trong N giây sau `scheduled_at`.
- Tuổi tối đa của OTP nằm trong outbox.
- Tỷ lệ submission accepted, phân theo provider/lane.
- Thời gian phát hiện và xử lý AUTH/TLS failures.
- Tỷ lệ notification jobs bị expire.
- Tỷ lệ feedback callbacks được tiêu thụ idempotently.

**Delivery into inbox** chịu ảnh hưởng provider và receiving server; chỉ định nghĩa SLO delivery nếu có dữ liệu/khả năng đo phù hợp. Không khẳng định inbox delivery dựa trên SMTP accepted.

Ví dụ hai mức SLO:

~~~text
Orchestration SLO:
  99.9% transactional jobs begin a permitted attempt
  within 60 seconds of scheduledAt,
  excluding explicitly delayed provider quota windows.

Submission SLO:
  99.5% eligible attempts receive a definitive
  accepted/rejected outcome within 30 seconds.
~~~

Các giá trị chỉ để minh họa cách viết một contract; **không phải SLA khuyến nghị chung**. Cần thống nhất cách đo, khoảng thời gian, loại trừ, deadline và mức độ bảo đảm trước khi áp dụng.

### Alert theo backlog age

Một hệ thống có SMTP error rate bằng 0 vẫn có thể không gửi mail khi quota gate liên tục từ chối. Hãy theo dõi **demand, admission và submission** song song. Một outbox chứa hàng triệu jobs tương lai không hẳn là sự cố; backlog **đã tới hạn** và đang quá SLA mới cần cảnh báo.

## 33. Kiểm thử đúng từng ranh giới

Một kiến trúc tốt giúp mỗi loại test có mục tiêu rõ:

| Boundary | Test cần chứng minh |
|---|---|
| Business → Intent | Đúng event, recipient role, không tạo trùng intent |
| Intent → Notification policy | Consent, sender authorization, locale, template selection |
| Notification → Outbox | Commit/rollback atomic cùng business DB |
| Outbox → Dispatcher | Claim đúng, không gửi trước lịch, idempotent, lease/fencing |
| Dispatcher → Rate gate | Quota tenant/account, denied defer, no SMTP attempt |
| Renderer → OutboundEmail | Nội dung, template version, HTML escape, attachment references |
| OutboundEmail → SMTP adapter | MIME headers, To/Cc/Bcc, attachments, text/HTML |
| SMTP adapter → Provider | TLS, AUTH, timeouts, known reply codes, partial/unknown outcomes |
| Provider webhook → State | Signature validation, dedup, out-of-order events |
| SLO/operations | Metrics, backlog age, incident and recovery |

### Domain unit test không cần SMTP

~~~java
@Test
void paidOrderCreatesOneReceiptIntent() {
    // Fake repository + fake outbox.
    orderApplication.confirmPayment(orderId);
    verify(outbox, times(1)).insertIfAbsent(
            argThat(intent ->
                    intent.templateKey()
                            .equals("ORDER_RECEIPT")));
}
~~~

Đoạn test chỉ minh họa intent; `verify`, `times`, `argThat` là các helpers từ thư viện mocking như Mockito. Dù SMTP server đang down, domain unit test vẫn phải chạy offline.

### MIME adapter test không cần mail thật

Với `JavaMailSenderImpl.createMimeMessage()` và `MimeMessageHelper` có thể dựng MIME trong memory, đọc `BodyPart.getFileName()` và content type để xác minh đúng. SMTP integration test dùng một sink/test server như Mailpit/GreenMail và dữ liệu giả.

### Architecture test

Có thể dùng architecture rules:

~~~text
orders.domain must not depend on org.springframework.mail
orders.application must not depend on jakarta.mail
notifications.api must not expose JavaMailSender
mail.smtp may depend on notifications.spi
~~~

Các quy tắc này có thể được thực thi bằng module structure, ArchUnit hoặc kiểm tra dependencies tự động. Đừng biến test thành blacklist mọi từ “mail” trong package; mục tiêu là ngăn **framework/transport type** lấn vào contract nghiệp vụ.

## 34. Contract testing khi notification là một microservice

Khi domain service gọi Notification Service qua HTTP hoặc message bus, boundary nằm ở network và schema. Không nên chia sẻ một JPA entity hoặc `MimeMessage` làm payload contract vì:

- Schema bên trong thay đổi theo persistence/transport.
- Một consumer cũ có thể không hiểu field bắt buộc mới.
- Tạo vòng phụ thuộc build/deploy giữa nhiều teams.
- Dữ liệu nhạy cảm có thể bị vô tình serialize.

Nên có **versioned contract**:

~~~json
{
  "schemaVersion": 2,
  "notificationType": "ORDER_RECEIPT",
  "eventId": "evt-583-v7",
  "businessRef": "ORDER-583",
  "recipientRef": "customer-opaque-101",
  "templateVersion": "2026-11",
  "requestedAt": "2026-11-12T09:00:00Z"
}
~~~

Những câu hỏi quan trọng:

1. Field mới có default rõ ràng không?
2. Có consumer cũ vẫn nhận event version trước không?
3. Unknown notification types được từ chối/quarantine thế nào?
4. Có áp retry khi schema invalid không, hay coi là permanent?
5. EventId có chống duplicate delivery của broker không?
6. Notification data có được xóa/ẩn danh theo retention policy không?
7. Sender authorization có được xác minh lại tại service, thay vì tin mọi field?

### Contract test nên xem hành vi, không chỉ JSON shape

Một test producer/consumer nên chứng minh:

~~~text
Valid ORDER_RECEIPT event
  -> notification accepted and queued

Same eventId delivered twice
  -> one business notification intent

Unsupported schema version
  -> explicit rejection/quarantine with reason

Unauthorized tenant sender profile
  -> no SMTP submission
~~~

Khi schema thay đổi, dùng additive/evolution strategy có kiểm soát; không thay giá trị trường đã có một cách phá tương thích rồi hy vọng mọi services deploy cùng lúc.

## 35. Migration: từ gửi trực tiếp tới ranh giới rõ ràng

Một ứng dụng đã tồn tại có thể chứa:

~~~text
OrderService -> JavaMailSender
UserService -> JavaMailSender
BillingService -> JavaMailSender
CampaignJob -> JavaMailSender
~~~

Không nhất thiết phải tách microservice trong một release. Có thể chuyển dần qua các giai đoạn:

### Giai đoạn A: bao một adapter có contract rõ

Đầu tiên tạo:

~~~text
NotificationPort
  requestOrderReceipt(...)
  requestPasswordReset(...)

SpringSmtpMailAdapter
  send(outboundEmail)
~~~

Ứng dụng vẫn gửi đồng bộ nếu đó là hành vi hiện tại, nhưng business code không còn import `JavaMailSender` và `MimeMessageHelper`.

### Giai đoạn B: thống nhất notification policy

Chuyển template selection, sender profile, consent/eligibility và recipient resolution về notification application module. Tránh sửa toàn bộ flow cùng lúc; có thể ưu tiên một loại email có ít rủi ro.

### Giai đoạn C: bổ sung durable outbox

Cho các email cần độ tin cậy, thay direct send bằng `enqueue` trong transaction nghiệp vụ. Thêm dispatcher, status, attempt history, idempotency key và hạn chế concurrency/rate.

### Giai đoạn D: tách worker process khi cần

Chạy mail dispatcher ở worker deployment khác HTTP app, với cùng codebase hoặc module riêng. Lúc này outbox/API contract đã giúp tách operational responsibility.

### Giai đoạn E: tách Notification Service nếu có business case

Khi traffic và team ownership yêu cầu, thay local module calls bằng durable integration contract. Đừng tạo network service rồi mới tìm cách chuyển `MimeMessage` qua API; giữ request types thuần ứng dụng.

### Giai đoạn F: vận hành đa provider và delivery feedback

Thêm provider routing/qualifiers, quota theo account/tenant, delivery webhook, dashboard và runbooks khi sản phẩm có nhu cầu. Không phải hệ thống nào cũng cần mọi tính năng ngay từ ngày đầu.

## 36. Chuyển đổi không gây gửi trùng khi chạy song song

Một migration dễ mắc sai:

~~~text
Old code:
  OrderService directly sends email

New code:
  OrderPaid event also creates outbox job

During rollout:
  Same order triggers BOTH paths -> two emails
~~~

Để tránh:

1. Chọn notification type và ownership của mỗi path.
2. Dùng feature flag hoặc routing rule xác định **chỉ một nguồn có quyền phát intent** cho một business event.
3. Cấp business event/idempotency key ổn định.
4. Lưu migration version hoặc source reference nếu cần đối soát.
5. Trước khi bật new path, kiểm tra old path đã bị disable cho cùng scope.
6. Dùng shadow mode **không submit SMTP** khi so sánh template/payload.
7. Theo dõi accepted submissions và duplicate business references trong rollout.

Không chỉ dựa vào việc phát hai event cùng `Message-ID` để kỳ vọng mail client tự deduplicate.

### Cutover với các jobs đang chờ

Nếu old scheduler có jobs pending, cần kế hoạch:

- Chuyển dữ liệu sang outbox mới hay để old worker drain?
- Trạng thái terminal/processing của old jobs có được đối soát?
- Jobs đã begin submission nhưng chưa rõ outcome có bị replay không?
- Tenant/route và template versions có thay đổi giữa hệ thống cũ/mới?
- Có thời điểm ngừng old producer/worker chính xác không?

Đây là một **data migration + workflow migration**, không chỉ là đổi dependency injection.

## 37. Cách viết Architecture Decision Record (ADR)

Một quyết định ranh giới lớn nên được ghi lại để team khác hiểu rationale và trade-offs. Mẫu:

~~~markdown
# ADR-012: Spring Mail chỉ nằm trong outbound transport adapter

## Context
- Nhiều domains gửi email qua cùng SMTP provider.
- Tầng nghiệp vụ đang phụ thuộc Jakarta Mail classes.
- Cần retry bền vững và quota theo account.

## Decision
- Domain phát typed business events / notification intents.
- Notification module sở hữu policy, outbox và job state.
- Mail infrastructure adapter triển khai MailDeliveryPort
  với JavaMailSender + MimeMessageHelper.
- Worker submit SMTP ngoài domain DB transaction.
- Provider feedback cập nhật delivery state qua verified adapter.

## Consequences
- Tăng số abstractions và database jobs.
- Cần worker, metrics và incident runbook.
- Giảm coupling của domain với SMTP.
- Không bảo đảm exactly-once SMTP; UNKNOWN cần reconciliation.

## Alternatives considered
- Tiếp tục gọi JavaMailSender trực tiếp.
- Shared SMTP utility library.
- Tách Notification Service độc lập ngay.

## Review triggers
- Traffic vượt account quota thường xuyên.
- Nhiều teams cần policy/scale độc lập.
- Provider change hoặc compliance boundary mới.
~~~

Không nhất thiết dùng đúng số ADR-012; đó là ví dụ cách ghi. Một ADR nên nêu:

- **Quyết định**: boundary cụ thể, loại dependency bị cấm/được cho phép.
- **Lý do**: vấn đề cần giải quyết và quality attributes.
- **Đánh đổi**: chi phí vận hành, latency và độ tin cậy.
- **Phương án không chọn**: và lý do.
- **Tín hiệu xem xét lại**: khi quy mô hoặc nhu cầu thay đổi.

Một bản ADR chỉ nói “dùng microservice vì clean architecture” mà không định nghĩa ownership, trạng thái, retries và failure modes là chưa đủ cho implementation.

## 38. Decision matrix: một số kiến trúc tham chiếu

### Kiến trúc A — Ứng dụng đơn nhỏ, email best-effort

~~~text
Business service
   -> NotificationPort
   -> SMTP adapter
~~~

Phù hợp khi email không quan trọng và việc mất một notification sau crash có thể chấp nhận. Cần mô tả guarantee, không tự nhận outbox durability. Có thể vẫn dùng `@TransactionalEventListener(AFTER_COMMIT)` để tránh gửi trước commit nhưng không thay thế queue bền vững.

### Kiến trúc B — Modular monolith, email nghiệp vụ quan trọng

~~~text
Business transaction
   -> business data + outbox in same database
   -> dispatcher
   -> MailDeliveryPort
   -> Spring Mail adapter
~~~

Phù hợp với nhiều hệ thống Spring đang phát triển. Giữ transaction đơn giản và code boundary rõ; có thể tách worker deployment về sau.

### Kiến trúc C — Multi-team platform

~~~text
Order/Billing/Identity services
         |
         v
Durable events / Notification API
         |
         v
Notification service
  policy + templates + outbox
         |
         v
Delivery workers per provider/lane
  +-- SMTP adapter
  +-- HTTP mail API adapter
         |
         v
Provider feedback / delivery state
~~~

Phù hợp khi policy vận hành, SLA, scaling hoặc security yêu cầu service riêng. Đánh đổi là network failure, schema versioning, outbox ở producer và duplicate event handling.

### Kiến trúc D — Managed notification platform

~~~text
Business intent
   -> validated notification adapter
   -> external managed notification API
~~~

Có thể giảm việc tự xây template/rate/delivery tracking tùy năng lực vendor. Tuy nhiên application vẫn cần idempotency, durable intent nếu quan trọng, authorization, privacy, secret handling và contract được bảo vệ trước vendor-specific behavior.

## 39. Các tiêu chí để quyết định service boundary

Sử dụng các câu hỏi cụ thể:

| Câu hỏi | Dấu hiệu nên giữ module | Dấu hiệu nên tách service/worker |
|---|---|---|
| Ai sở hữu? | Cùng một team | Nhiều team muốn release độc lập |
| Có cần transaction chung? | Business + outbox trong cùng DB | Có durable event contract và ownership rõ |
| Độ lớn traffic? | Thấp, ổn định | Batch/spike lớn ảnh hưởng request path |
| Provider credentials? | Cùng app là đủ an toàn | Cần workload secret isolation |
| SLA? | Best effort | Cần lane riêng, worker scale và 24/7 ops |
| Template changes? | Thưa, cùng release | Thường xuyên, nhiều sản phẩm |
| Multi-channel? | Chỉ vài email | Email, push, SMS, in-app với shared policy |
| Provider? | Một cấu hình đơn giản | Nhiều accounts/routes/quota và delivery events |
| Operational maturity? | Chưa có durable broker/platform | Đã có queue, tracing, incident ownership |

**Đừng quyết định chỉ bằng số dòng code email.** Một adapter 100 dòng có thể cần tách deployment vì security/SLA, trong khi hàng nghìn template lines có thể vẫn nằm trong modular monolith nếu team và lifecycle thống nhất.

## 40. Những anti-pattern khi đặt ranh giới Spring Mail

### 40.1. Domain service trực tiếp tạo MimeMessage

~~~java
@Service
public class OrderService {
    private final JavaMailSender sender;
    // ...
}
~~~

Domain bắt đầu phụ thuộc SMTP framework, khó thay provider và khó unit test offline. Di chuyển MIME construction vào infrastructure adapter, domain tạo intent hoặc gọi typed notification port.

### 40.2. EmailService làm mọi việc

Một `EmailService` vừa query order, tính thuế, kiểm tra consent, render template, điều khiển SMTP, retry và cập nhật trạng thái giao hàng sẽ thành **god object**. Tách responsibilities theo policy, workflow, renderer và transport adapter.

### 40.3. Public API nhận SMTP host/password

Caller có thể tạo relay/SSRF hoặc lạm dụng credentials. Provider profile được phê duyệt phải được server xác định và lưu secret ở infrastructure.

### 40.4. Đặt @Transactional quanh send()

SMTP không rollback theo database. Gửi trong domain transaction có thể gây email cho giao dịch rollback và giữ locks lâu. Dùng outbox nếu notification cần atomic intent.

### 40.5. Coi @Async là durable messaging

Executor queue trong RAM có thể mất khi process restart. `@Async` giúp non-blocking request path nhưng không thay persistence, retries và ownership.

### 40.6. Coi AFTER_COMMIT listener bảo đảm không mất event

Sau DB commit, process vẫn có thể crash trước khi listener ghi request gửi. Nếu không chấp nhận bỏ sót, cần transactional outbox/event relay bền vững.

### 40.7. Domain tự retry MailException

Domain không biết SMTP phase, provider accepted hay chưa. Retry mù có thể gây duplicate. Adapter phân loại technical outcome, workflow áp policy retry.

### 40.8. Gửi lại mọi PROCESSING sau lease timeout

Lease expiry không chứng minh provider chưa accepted. Cần attempt history, `UNKNOWN` và reconciliation.

### 40.9. Coi SMTP accepted là inbox delivered

Đã submit không đồng nghĩa người nhận nhìn thấy thư. Delivery feedback là một integration boundary riêng khi có evidence.

### 40.10. Truyền MimeMessage qua broker

Đây là coupling giữa messaging contract và Jakarta Mail serialization. Broker event nên dùng typed intent/reference/version, không buộc consumers cùng MIME implementation.

### 40.11. Shared mail-common.jar nhưng mỗi service giữ credential

Một library không tập trung hóa quota, secrets hoặc trạng thái. Cần quyết định rõ shared runtime có cần hay không; library chỉ là tái sử dụng code.

### 40.12. Tách microservice sớm rồi dùng synchronous HTTP cho mọi email

Một request checkout phải chờ Notification Service rồi SMTP có thể làm tăng latency và lỗi dây chuyền. Với email không cần tức thời, prefer durable enqueue và trả `202 Accepted`/job ID theo contract.

### 40.13. Để transport adapter quyết định business recipient

SMTP adapter không nên tự query “khách nào đã thanh toán?” hoặc chọn người nhận dựa vào dữ liệu không được authorization. Domain/notification policy quyết định đối tượng, adapter chỉ gửi tới danh sách đã duyệt.

### 40.14. Để business service đọc SMTP exception raw

`MessagingException`/`MailSendException` là technical details. Không ép business retry/compensation logic phụ thuộc text exception của provider.

### 40.15. Template logic nằm trong JavaMailSender wrapper

Khi marketing đổi nội dung, infrastructure deployment bị sửa; dễ làm sender/locale/consent rối. Đưa template policy/rendering vào notification/content module.

### 40.16. Lưu credentials và HTML payload trong outbox không kiểm soát

Credential phải đến từ secret store; payload phải tuân thủ encryption/RBAC/retention. Với file lớn, lưu storage reference đã kiểm soát.

### 40.17. Một executor/queue FIFO cho mọi tenant và loại email

Bulk campaigns có thể làm OTP chậm. Cần lanes, fairness, quotas và concurrency isolation dựa trên SLA.

### 40.18. Tăng maxPoolSize thay cho rate limiting

Concurrency không phải messages/second, recipients/day hay per-tenant budget. Shared account quota cần shared admission theo scope thực tế.

### 40.19. Provider webhook cập nhật trực tiếp domain state

Public callback cần verify signature, idempotency, correlation và authorization. Map technical delivery event sang domain event được phê duyệt nếu business cần.

### 40.20. Dùng Message-ID làm exactly-once key

`Message-ID` có thể giúp correlation, không đảm bảo SMTP/provider/mail client sẽ loại trùng. Business idempotency và attempt state vẫn cần.

### 40.21. Migration bật cả old direct sender lẫn new outbox

Một business event tạo hai đường gửi gây duplicate. Có routing/feature flag có ownership, shadow mode không submit và cutover audit.

### 40.22. Đưa tenant ID tự khai báo vào quota key

Caller có thể giả tenant hoặc dùng budget của người khác. Resolve tenant từ authenticated context và kiểm tra sender/account mapping.

### 40.23. Không định nghĩa ai xử lý incident và replay

Service bị lỗi nhưng không có owner cho `UNKNOWN`, DLQ, outbox replay hoặc credential rotation. Cần runbook và quyền thao tác với audit.

### 40.24. Tạo quá nhiều abstraction không có lý do

Một app chỉ có hai email đơn giản không nhất thiết cần 12 services, broker, workflow engine và provider routing phức tạp. Tạo **boundary logic nhỏ, rõ** trước; thêm infrastructure khi có yêu cầu thật.

## 41. Runbook: provider outage ảnh hưởng nhiều domain

Giả sử provider SMTP chính ngừng hoạt động, trong khi Order, Identity và Billing cùng có mail đang chờ.

~~~text
Provider outage
      |
      v
Transport detects repeated connection/timeouts
      |
      v
Technical error classification
      |
      v
Circuit breaker / reduced rate
      |
      v
Durable outbox retains notification intents
      |
      v
Ops dashboard shows backlog age by lane
      |
      v
Recovery or approved provider failover
~~~

Các bước:

1. Kiểm tra network/DNS/TLS/auth, phân biệt outage và config/credential sai.
2. Xem provider status và account quota/concurrency.
3. Xác nhận outbox không ngừng nhận intent hợp lệ.
4. Tạm dừng bulk lane nếu cần bảo vệ queue và ngân sách gửi.
5. Đặt retry backoff/jitter; không vòng lặp SMTP nóng.
6. Kiểm tra `UNKNOWN` outcomes trước khi replay/failover.
7. Nếu chuyển route, xác minh sender verification và quota của tuyến mới.
8. Giám sát backlog drain, expired messages và accepted throughput.
9. Đối soát các job ảnh hưởng SLA quan trọng, đặc biệt OTP hết hạn.
10. Ghi post-incident: nguồn lỗi, blast radius, mất/trùng intent, cải tiến policies.

**Domain requests không nên đồng loạt fail chỉ vì SMTP outage** khi notification được thiết kế bất đồng bộ và không phải điều kiện bắt buộc để hoàn tất nghiệp vụ. Tuy nhiên có những flow thật sự cần chứng minh kênh liên lạc đã sẵn sàng; trường hợp đó phải được mô hình hóa thành business precondition riêng, không lẫn với `send()` bên trong transaction.

### Khi notification service hoàn toàn unavailable

Với modular monolith, business service vẫn có thể ghi outbox cùng DB. Với microservices, producer cần durable event/outbox hoặc cơ chế queue có guarantee rõ. Nếu Notification API trả timeout, caller không thể đơn giản suy ra “request chưa được lưu”; dùng idempotency key và query status/consumer dedup.

## 42. Runbook: người dùng báo email sai nội dung

Đây là incident thuộc **content/notification boundary**, không nhất thiết là SMTP:

1. Xác định notificationId, template key/version và business event reference.
2. Kiểm tra người nhận theo business authorization.
3. Xem snapshot hay render-on-send đã được chọn.
4. So sánh nội dung có nguồn từ dữ liệu cũ, template bug hoặc locale/branding sai.
5. Không chỉnh raw SMTP provider config để sửa một lỗi template.
6. Quyết định có gửi bản sửa hay không, theo chính sách rủi ro duplicate/PII.
7. Ghi audit và triển khai regression test ở đúng module renderer/policy.

Ví dụ: hóa đơn số tiền sai vì tax calculation lỗi phải được sửa ở business/document domain, không phải đổi `MimeMessageHelper.setText(...)` để “vá” số tiền chỉ trong email.

### Khi người nhận không đúng

Đây có thể là sự cố bảo mật/riêng tư, không chỉ là lỗi notification:

- Dừng route/job nếu cần.
- Xem recipient resolution và tenant authorization.
- Xác định loại dữ liệu đã gửi và scope ảnh hưởng.
- Bảo toàn audit phù hợp, thực hiện incident response theo quy định tổ chức.
- Không log raw recipient/body rộng rãi khi điều tra.

Thiết kế boundary tốt giúp truy tìm: sai recipient từ domain, directory/profile policy, template variable hay từ transport envelope mapping.

## 43. Checklist nghiệm thu ranh giới Spring Mail

| Tiêu chí | Bằng chứng |
|---|---|
| Domain không import Jakarta Mail/Spring Mail | Architecture dependency test |
| Business event và email command khác nhau | Contract docs và typed request |
| Provider config chỉ ở adapter/workload cần thiết | Secret/RBAC review |
| Template/consent không ở SMTP adapter | Module ownership/code structure |
| Email intent đáng tin ghi cùng business commit | Transaction/outbox integration test |
| Retry thuộc workflow, technical error thuộc adapter | Failure classification tests |
| UNKNOWN không bị gửi lại mù | Crash-window tests |
| Multi-worker không cùng claim đơn giản | DB concurrency/lease tests |
| Quota account/tenant được bảo vệ | Distributed admission/load tests |
| MIME/attachment đúng | Offline MIME tests và SMTP sink |
| Delivery feedback được verify/dedup | Webhook integration tests |
| API không nói delivered ngay khi queued | Contract/response tests |
| Mọi thay đổi sender/profile có authorization | Security tests |
| Observability tách demand/attempt/delivery | Dashboards và alert rehearsal |
| Không log credentials/raw MIME/PII không cần thiết | Log policy review |
| Có owner incident/replay | Runbook và phân quyền |
| Migration không chạy hai đường gửi cùng lúc | Feature flag/cutover tests |
| Bounded queues và timeout | Load/failure tests |

### Quy trình kiểm tra kiến trúc theo một notification thực tế

Chọn một loại mail, ví dụ xác nhận thanh toán:

~~~text
Payment committed
   |
   v
Find notification intent
   |
   v
Find policy/template decision
   |
   v
Find durable job + status
   |
   v
Find submission attempt
   |
   v
Find SMTP adapter/config
   |
   v
Find provider feedback (if any)
~~~

Nếu một bước không có nguồn sự thật, ownership hoặc cách quan sát, đó có thể là dấu hiệu boundary đang thiếu. Không nhất thiết có một microservice ở mỗi bước.

## 44. Câu hỏi thường gặp

**Spring Mail nên nằm ở tầng nào?** Thông thường trong **infrastructure/transport adapter**. Business domain/application nên giao tiếp bằng notification intent/port do ứng dụng định nghĩa, không dùng trực tiếp `JavaMailSender` hoặc `MimeMessage`.

**Có phải mọi dự án đều cần Notification Service riêng?** Không. Modular monolith với boundaries rõ, outbox khi cần và adapter SMTP riêng thường đủ. Tách service khi team ownership, scale, security hoặc SLA mang lại lợi ích lớn hơn chi phí vận hành.

**Một EmailService trong package service đã đủ boundary chưa?** Chưa chắc. Nếu nó vừa chứa business rules, template, SMTP, retry và account policy thì chỉ gom logic vào một god object. Boundary cần tách trách nhiệm và chiều phụ thuộc.

**Có nên đưa `JavaMailSender` vào OrderService thông qua constructor injection?** Không nên khi muốn ranh giới domain độc lập transport. Inject `NotificationPort` hoặc tạo intent qua application layer.

**Domain nên phát `OrderPaid` hay `SendReceiptEmail`?** `OrderPaid` mô tả event nghiệp vụ và cho nhiều consumer dùng. `SendReceiptEmail` có thể là command nội bộ của notification workflow sau khi policy quyết định gửi; không nên nhét SMTP command vào domain event khi chưa có lý do.

**Có nên chuyển `MimeMessage` qua Kafka/RabbitMQ?** Thông thường không. Dùng schema sự kiện/notification request có version và references; worker dựng MIME tại transport boundary.

**Dùng shared mail-common.jar có thay thế Notification Service không?** Không. Shared library tái sử dụng code nhưng không tự tập trung hóa credentials, quota, retry state hoặc trách nhiệm vận hành.

**Tại sao phải có outbox nếu đã có `@Async`?** `@Async` đưa việc làm vào executor trong process; nó không bảo đảm còn job sau crash. Durable outbox lưu ý định gửi ở database/broker có quy tắc phục hồi.

**`@TransactionalEventListener(AFTER_COMMIT)` có đủ không?** Đủ cho một số flow best-effort, nhưng có thể mất thông báo nếu process chết sau DB commit trước khi listener ghi intent. Notification quan trọng cần durable mechanism.

**Có nên gửi email đồng bộ trong API không?** Có thể khi nghiệp vụ thực sự yêu cầu biết SMTP submission outcome ngay, lưu lượng thấp và chấp nhận latency/failure. Nhưng đa số thông báo không cần chờ SMTP để hoàn tất business request; durable enqueue và status query thường ổn định hơn.

**HTTP 202 Accepted khi gửi mail có nghĩa thư vào inbox không?** Không. Nó có thể chỉ là nhận yêu cầu. Contract phải phân biệt QUEUED, SUBMITTED, DELIVERED và UNKNOWN.

**Khi `JavaMailSender.send()` không lỗi thì có thể set DELIVERED không?** Không. Chỉ biết submission đã hoàn tất theo góc nhìn client/SMTP. Delivery cần provider feedback hoặc evidence phù hợp.

**Adapter hay workflow quyết định retry?** Adapter phân loại kỹ thuật/transport outcome; workflow dùng deadline, attempt count, loại notification, tenant priority và duplicate risk để quyết định.

**Vì sao cần trạng thái UNKNOWN?** Khi network mất sau SMTP DATA, provider có thể đã accepted nhưng client không thấy xác nhận. Retry mù có nguy cơ tạo email trùng.

**Không dùng SMTP Message-ID để deduplicate được sao?** Header `Message-ID` là correlation, không phải bảo đảm receiver/provider sẽ loại thư trùng. Business idempotency key và attempts vẫn cần.

**Business transaction đã dùng `@Transactional`, email gửi trong đó có rollback không?** Không. SMTP không tham gia ACID transaction của database. Nên lưu intent qua outbox rồi gửi sau commit.

**Nếu Notification Service down, business service nên làm gì?** Tùy contract. Với async durable integration, producer lưu event/outbox và tiếp tục nếu email không phải điều kiện đồng bộ. Với synchronous API, cần timeout, idempotency và cơ chế truy vấn trạng thái để không tạo duplicate.

**Ai nên chọn template?** Notification/content policy hoặc domain sở hữu nội dung đã phê duyệt, tùy business ownership. Transport SMTP chỉ nên gửi nội dung đã được rendering/validation.

**Ai xác định recipient?** Domain xác định đối tượng được phép nhận; notification policy resolve địa chỉ, preference và suppression phù hợp; adapter gửi theo địa chỉ đã được authorization.

**Có nên lưu rendered HTML trong outbox?** Tùy use case. Snapshot giúp giữ nội dung ổn định nhưng chứa PII và cần encryption/retention; render-on-send cần rules về version và dữ liệu thay đổi.

**Attachment PDF nên được tạo ở MailAdapter không?** Thường không. Document/domain service tạo file và cung cấp approved payload reference; adapter quyết định cách nạp dữ liệu thành MIME attachment.

**Có nên cho tenant chọn SMTP From tùy ý không?** Không. Chọn sender profile đã được phê duyệt, verified sender/domain và quota scope đúng.

**Multi-tenant cần quota ở đâu?** Notification dispatcher/rate gate theo account và tenant, với shared state khi nhiều replicas. Không để business service tự triển khai một token bucket riêng mà không điều phối account-wide quota.

**Tách hai ThreadPoolTaskExecutor đã đảm bảo cô lập mail chưa?** Chỉ giúp cô lập một phần thread contention. Vẫn cần backpressure, bounded queue, provider rate/concurrency control và quota state theo scope thật.

**Inbound email có thuộc cùng MailAdapter không?** Có thể cùng repo nhưng nên tách module và privileges. Outbound SMTP submission khác inbound IMAP/POP3 reading về protocols, checkpoints, retries và trust boundary.

**Delivery webhook có thể ghi thẳng vào bảng orders không?** Không nên. Xác minh callback, correlate/dedup rồi để business application tự quyết định có hành động gì từ event đã xác thực.

**Khi có nhiều provider, có nên một JavaMailSenderImpl thay đổi host theo từng job?** Tránh cấu hình mutable singleton chia sẻ giữa threads. Dùng sender/adapters riêng và route registry/qualifiers có policy.

**Khi nào cần microservice riêng cho template?** Khi content lifecycle, approval, localization hoặc nhiều product teams cần release độc lập. Nếu không, một notification/content module vẫn có boundary tốt.

**Có nên dùng một queue duy nhất cho OTP và newsletter?** Có thể nếu workload nhỏ và có fairness/SLA controls, nhưng ở scale lớn thường cần lanes, reserved capacity hoặc điều phối công bằng để tránh bulk starvation.

**Làm sao chứng minh ranh giới đúng?** Bằng architecture dependency tests, business unit tests không cần SMTP, contract tests, outbox recovery tests, MIME adapter tests, provider/feedback integration tests và runbook ownership.

**Có cần event-driven architecture cho từng email không?** Không nhất thiết. Một command call có type rõ và outbox có thể đủ. Event bus hữu ích khi có nhiều consumers, independent deployment hoặc durable processing nhu cầu lớn; nó cũng thêm vận hành/consistency concerns.

**Có nên dùng broker delayed messages thay DB scheduler?** Có thể nếu broker hỗ trợ semantics cần thiết, nhưng vẫn phải quản lý trạng thái job, cancellation, retries, expiry và idempotency. Một delayed message không tự giải quyết SMTP exactly-once.

**Nếu thay SMTP bằng HTTP email API có cần sửa nghiệp vụ?** Với port–adapter đúng, phần lớn domain/application contracts giữ nguyên. Provider-specific feature có thể đòi bổ sung capability model nhưng không nên làm domain biết trực tiếp HTTP headers/API keys.

**Nếu email là điều kiện tuân thủ bắt buộc thì có nên gửi trước khi hoàn tất giao dịch?** Cần mô hình business state phù hợp (ví dụ PENDING_NOTIFICATION/REQUIRES_ACK) và contract cụ thể về bằng chứng đã gửi/giao. Không giả định gọi `mailSender.send()` trong database transaction tạo ra một cam kết pháp lý.

**Có nên centralize mọi thông báo cả marketing lẫn security?** Có thể chia sẻ infrastructure và state patterns, nhưng ranh giới privacy, consent, sender reputation, rate quota và SLA có thể khác nhau. Cần policy/lanes/ownership đủ rõ; centralized service không đồng nghĩa một FIFO queue và một credential.

**Làm sao tránh dependency cycle?** Domain không gọi adapter, adapter implement application port. Notification service nhận event/command từ domain, nếu cần dữ liệu truy vấn qua contract phù hợp; không import trực tiếp entity của mọi domain.

**Nếu support cần gửi lại email thì ai có quyền?** Notification operations/workflow, với authorization, audit, lý do và checks để tránh gửi trùng. Không cho support UI gọi thẳng `JavaMailSender` bỏ qua policy.

**Có nên lưu toàn bộ raw SMTP transcript để audit?** Thường không. Raw transcript có thể chứa PII và secret. Lưu attempt status, reason code, provider reference, timestamps và dữ liệu tối thiểu theo retention.

## 45. Ví dụ kiến trúc end-to-end: email xác nhận thanh toán

Giả sử một hệ thống bán hàng cần gửi xác nhận sau khi thanh toán được ghi nhận.

### Bước 1: domain commit trạng thái thanh toán và intent

~~~text
OrderService.confirmPayment(ORDER-583)
  |
  +-- Mark order paid
  +-- Insert outbox event OrderPaid(ORDER-583, version=7)
  +-- Commit same database transaction
~~~

Nếu transaction rollback, không có email intent cho giao dịch đó. Nếu commit, outbox entry còn tồn tại qua process restart.

### Bước 2: notification processor nhận event

~~~text
OrderPaid event
  |
  +-- Deduplicate by (eventType, aggregateId, version)
  +-- Validate customer/recipient relationship
  +-- Determine type=ORDER_RECEIPT
  +-- Choose locale=vi-VN
  +-- Resolve approved sender profile=BILLING
  +-- Render template version=2026-11
  +-- Store approved payload/reference
  +-- Create delivery job PENDING
~~~

Nếu consumer nhận event hai lần vì broker redelivery, unique key ngăn tạo thêm intent. Nếu nhận event version cũ khi invoice thay đổi, policy xác định liệu cần gửi hay bỏ qua.

### Bước 3: dispatcher gửi email theo capacity

~~~text
MailJob status=PENDING
  |
  +-- Check scheduledAt/expiry
  +-- Claim with lease
  +-- Revalidate recipient suppression if applicable
  +-- Resolve account and tenant quota
  +-- Acquire bounded concurrency slot
  +-- Record submission attempt
  +-- Call MailDeliveryPort.submit(...)
~~~

Dispatcher không cần biết logic order payment ngoài những approved fields đã được notification application cung cấp.

### Bước 4: Spring Mail adapter dựng MIME

~~~java
MimeMessage mime = javaMailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, true, "UTF-8");

helper.setFrom("billing@example.test");
helper.setTo("customer@example.test");
helper.setSubject("Thanh toán thành công");
helper.setText(
        "Đơn hàng đã được thanh toán.",
        "<p>Đơn hàng <strong>ORDER-583</strong>"
                + " đã được thanh toán.</p>");

helper.addAttachment(
        "invoice-ORDER-583.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf");

javaMailSender.send(mime);
~~~

Đây là đoạn minh họa transport, giả định dữ liệu người nhận, sender, HTML và bytes đã được xác minh từ các tầng trước. Trong production, adapter không hardcode các giá trị nghiệp vụ như trên. `ByteArrayResource` được chọn vì PDF fixture vừa phải; tài liệu lớn nên dùng nguồn phù hợp để tránh giữ nhiều byte arrays.

### Bước 5: workflow lưu submission outcome

~~~text
SMTP accepted:
  attempt.status=ACCEPTED
  job.status=SUBMITTED
  submitted_at=...

Temporary reject:
  attempt.status=REJECTED_TEMPORARY
  job.status=RETRY
  next_attempt_at=...

Ambiguous result:
  attempt.status=UNKNOWN
  job.status=UNKNOWN
  reconciliation required
~~~

Không có response nào mặc định gán `DELIVERED` chỉ vì `send()` return. Các transitions cần kiểm tra claim token/status khi ghi database để worker cũ không overwrite trạng thái mới.

### Bước 6: provider feedback được xử lý riêng

~~~text
Verified provider webhook
  -> correlate provider message/attempt reference
  -> idempotently record delivered/bounced event
  -> update delivery projection
  -> notify business only if business rule requires
~~~

Nhờ đó một sự cố delivery không làm rối logic `OrderPaid` vốn đã commit. Các nghiệp vụ đặc biệt như “phải xác nhận người dùng thật sự nhận được tài liệu” cần workflow/business confirmation riêng, không suy luận từ SMTP.

### Các test tối thiểu cho ví dụ

| Test | Điều cần xác nhận |
|---|---|
| Order transaction rollback | Không có notification intent đã commit |
| Order commit và app crash | Outbox còn, có thể tiếp tục |
| Event redelivery | Chỉ một intent cho event/version |
| Template missing | Job preparation failure, không submit SMTP |
| Provider temporarily unavailable | Retry/defer bền vững |
| Client timeout after DATA | UNKNOWN, không resend mù |
| Duplicate provider callback | Một delivery state effect |
| Wrong tenant sender profile | Không gọi JavaMailSender |
| Load 10x bulk traffic | Transactional lane vẫn trong SLA |
| Adapter swap SMTP → HTTP | Domain application unit tests không đổi |

## 46. Tổng kết

**Đặt ranh giới Spring Mail trong hệ thống lớn** là quyết định xác định **ai sở hữu intent, policy, state, transport và feedback**, thay vì chỉ di chuyển một lệnh `mailSender.send()` sang class khác.

Một kiến trúc có ranh giới rõ thường trông như sau:

~~~text
Business/domain services
  (events and authorized business intents)
                  |
                  v
Notification application
  (recipient, consent, template, locale, priority)
                  |
                  v
Durable outbox / notification workflow
  (scheduled state, idempotency, claim, retry, audit)
                  |
                  v
Rate, tenant and sender policy
                  |
                  v
MailDeliveryPort
                  |
                  v
Spring Mail infrastructure adapter
  (JavaMailSender, MimeMessageHelper, SMTP, TLS/auth)
                  |
                  v
Email provider
                  |
                  v
Verified provider feedback (if available)
  (delivery events, bounce, correlation, projection)
~~~

Những nguyên tắc trọng tâm:

1. **Spring Mail là transport capability**, không phải domain model hay notification workflow.
2. **Dùng typed intent/port thay vì phơi bày `MimeMessage`** trong domain hoặc contract liên service.
3. **Nội dung, recipient và consent thuộc policy/business boundaries**; SMTP adapter chỉ gửi nội dung đã được phê duyệt.
4. **Ghi intent bền vững cùng business commit khi không được phép bỏ sót**, thay vì kỳ vọng `@Async` hoặc `AFTER_COMMIT` tự bảo đảm durability.
5. **Phân biệt QUEUED, SUBMITTED và DELIVERED**, có trạng thái UNKNOWN cho kết quả SMTP không chắc chắn.
6. **Retry là orchestration policy**, classification là trách nhiệm technical adapter; không để domain tự gọi lại SMTP khi lỗi.
7. **Cô lập SMTP credentials, quota và failure blast radius**, đặc biệt với nhiều tenants, providers và traffic lanes.
8. **Tách ranh giới logic trước khi tách deployment**; modular monolith có thể là lựa chọn rất tốt nếu chưa có lý do vận hành microservice.
9. **Định nghĩa ownership, metrics, runbook và contract tests**, vì ranh giới không chỉ tồn tại trong package structure.
10. **Giữ con đường tiến hóa**: có thể bắt đầu bằng adapter trong cùng app, thêm outbox/worker rồi tách Notification Service khi scale/ownership thật sự yêu cầu.

Một kiến trúc thành công giúp Order, Billing, Identity và các domain khác tập trung vào nghiệp vụ của mình; Notification workflow kiểm soát sự hợp lệ và trạng thái; còn Spring Mail có thể thay đổi cách xây MIME, dùng SMTP provider khác hoặc cải thiện timeout mà **không buộc toàn bộ hệ thống phải hiểu cơ chế gửi email**.

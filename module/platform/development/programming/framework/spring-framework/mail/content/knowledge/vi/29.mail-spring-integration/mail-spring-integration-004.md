# Mapping payload và header sang MimeMessage trong Spring Integration Mail

Trong Spring Integration, dữ liệu đi qua channel được đóng gói thành `org.springframework.messaging.Message<T>` với hai phần: **payload** (nội dung) và **headers** (metadata). Khi một flow gửi email, các dữ liệu này phải được chuyển thành thông tin email như To, From, Subject, Reply-To, nội dung plain text/HTML và các MIME parts như attachment hoặc inline image.

Điểm dễ nhầm: **Spring Integration Message không phải Jakarta Mail MimeMessage**. Hai loại đối tượng cùng tên “message” nhưng thuộc hai tầng:

- `org.springframework.messaging.Message<T>` là thông điệp chuyển giữa integration endpoints.
- `org.springframework.mail.MailMessage` là interface biểu diễn các thuộc tính email đơn giản; `SimpleMailMessage` là implementation phổ biến.
- `jakarta.mail.internet.MimeMessage` là message MIME với header, body, multipart, attachment và nội dung phù hợp email.
- `JavaMailSender` là abstraction Spring dùng để tạo và gửi `MimeMessage` qua SMTP.
- `MailSendingMessageHandler` là outbound handler của Spring Integration, nhận Spring messages rồi ủy quyền gửi cho Spring Mail.

Bài học tập trung vào **mapping từ Spring payload/headers sang email thật**, cách dùng `MailHeaders` và transformer, ý nghĩa của header override, cách dựng MIME khi email phức tạp, mapping chiều inbound và kiểm thử kết quả bằng SMTP test server.

## 1. Bản đồ luồng outbound

~~~text
Business event / NotificationRequest
                |
                v
           Message<?>
                |
                +--> payload
                |      String, byte[], MailMessage, DTO
                |
                +--> MessageHeaders
                       mail_to, mail_from, mail_subject...
                |
                v
        Validate / Transform / Enrich
                |
                v
       MailSendingMessageHandler
           hoặc custom handler
                |
                v
           JavaMailSender
                |
                v
       MIME message / SMTP
                |
                v
       SMTP submission server
~~~

Flow có thể dùng sẵn một handler để gửi text đơn giản, hoặc custom handler để dựng MIME multipart. Cấu hình SMTP nằm ở `JavaMailSender`; mapping payload/headers nằm ở Spring Integration flow và các transformer/service activator.

## 2. Spring Message có những gì?

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> integrationMessage =
    MessageBuilder.withPayload(
            "Đơn hàng của bạn đã được xác nhận."
        )
        .setHeader("notificationId", "N-123")
        .setHeader("category", "TRANSACTIONAL")
        .build();
~~~

Trong ví dụ:

- Payload là body text dự kiến.
- `notificationId` và `category` là metadata nội bộ.
- Các header mặc định như message ID/timestamp phục vụ framework.
- Chưa có recipient, sender hoặc subject để gửi email.
- Không có quy tắc “mọi Spring header trở thành MIME header”.

Để gửi, application cần thêm những mail attributes được phép hoặc biến payload thành một `MailMessage`/`MimeMessage` phù hợp.

## 3. Phân biệt ba lớp header

| Tầng | Dạng dữ liệu | Ví dụ |
| --- | --- | --- |
| Spring Integration headers | Key/value của `MessageHeaders` | `mail_to`, `notificationId` |
| MIME email headers | Header trong message gửi tới mailbox | `To:`, `Subject:`, `Content-Type:` |
| SMTP envelope | Commands cho transport | `MAIL FROM`, `RCPT TO` |

Một Spring header `mail_to` có thể được handler dùng làm recipients cho email. Kết quả MIME có thể mang header To, còn transport dùng RCPT TO trong phiên SMTP. Nhưng đây không phải ánh xạ 1:1 tuyệt đối: Bcc recipients có thể được đưa vào SMTP envelope mà header Bcc không xuất hiện trên email mà người nhận khác thấy.

**Không bao giờ copy toàn bộ Spring MessageHeaders thành MIME headers.** Chúng có thể chứa tenant ID, trace baggage, internal URLs, OAuth tokens hoặc metadata không dành cho người nhận.

## 4. Những thành phần chính của Spring Integration Mail

| Thành phần | Vai trò |
| --- | --- |
| `MailSendingMessageHandler` | Nhận message từ outbound channel và gửi qua Spring Mail |
| `MailHeaders` | Các constant names cho metadata email |
| `MailReceivingMessageSource` | Tạo integration messages từ mailbox |
| `ImapMailReceiver` | Nhận qua IMAP |
| `Pop3MailReceiver` | Nhận qua POP3 |
| `ImapIdleChannelAdapter` | Nhận biến động mailbox qua IMAP IDLE khi server hỗ trợ |
| `DefaultMailHeaderMapper` | Ánh xạ MIME headers của inbound message sang Spring headers |
| `MailToStringTransformer` | Chuyển incoming mail content thành String khi phù hợp |
| `JavaMailSender` | Spring Mail interface để tạo/gửi MIME |
| `MimeMessageHelper` | Helper xây MIME, HTML, attachments và inline resources |

Module này không tự quản lý business consent, suppression, durable outbox hoặc sender authorization. Chúng thuộc chính sách của application.

## 5. Dependencies và tương thích phiên bản

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mail</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-mail"
    implementation "org.springframework.integration:spring-integration-mail"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

Nên dùng dependency management của Spring Boot để chọn Spring Framework, Spring Integration, Jakarta Mail implementation tương thích. Spring Boot 3/Spring Framework 6 dùng `jakarta.mail.*`, trong khi các thế hệ cũ dùng `javax.mail.*`. Không trộn namespace.

Spring Integration Mail là module bổ sung, không phải một tính năng `receive()` hoặc mapping toàn diện tự xuất hiện chỉ vì project có `spring-boot-starter-mail`.

## 6. MailHeaders trong mapping outbound

Các constant phổ biến thuộc `org.springframework.integration.mail.MailHeaders`:

| Constant | Header key | Vai trò |
| --- | --- | --- |
| `MailHeaders.TO` | `mail_to` | To recipients |
| `MailHeaders.CC` | `mail_cc` | Cc recipients |
| `MailHeaders.BCC` | `mail_bcc` | Bcc recipients |
| `MailHeaders.FROM` | `mail_from` | From |
| `MailHeaders.REPLY_TO` | `mail_replyTo` | Reply-To |
| `MailHeaders.SUBJECT` | `mail_subject` | Subject |
| `MailHeaders.ATTACHMENT_FILENAME` | `mail_attachmentFilename` | Attachment filename trong trường hợp được hỗ trợ |
| `MailHeaders.CONTENT_TYPE` | `mail_contentType` | Content type liên quan mail |
| `MailHeaders.MULTIPART_MODE` | `mail_multipartMode` | Thông tin multipart trong trường hợp hỗ trợ |

Trong outbound text mapping, sáu trường được sử dụng phổ biến nhất là **To, Cc, Bcc, From, Reply-To và Subject**.

Nên dùng constants thay vì gõ string để tránh typo. `mail_replyTo` khác `mail_reply_to`.

### Spring MessageHeaders.CONTENT_TYPE không phải MailHeaders.CONTENT_TYPE

`MessageHeaders.CONTENT_TYPE` dùng key `contentType` của Spring Messaging. `MailHeaders.CONTENT_TYPE` dùng key `mail_contentType`. Chúng khác nhau về nguồn và ý nghĩa.

Một Spring message mang `contentType=application/json` không tự động trở thành MIME email `application/json`, cũng không tự chuyển JSON thành body hữu ích.

## 7. Cấu hình JavaMailSender cho outbound handler

Ví dụ Spring Boot `application.yml`:

~~~yaml
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
~~~

`JavaMailSender` dùng các cấu hình này để kết nối SMTP. Không put password hoặc access token vào Spring message headers. SMTP credentials thuộc cấu hình hạ tầng/secret manager, không thuộc business event.

`spring.mail.*` chỉ giải quyết transport config, không thực hiện payload-to-MIME mapping thay flow.

## 8. Kết nối MailSendingMessageHandler vào channel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
public class MailIntegrationConfig {

    @Bean
    public MessageChannel outboundMail() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "outboundMail")
    public MessageHandler mailSendingHandler(
            JavaMailSender sender) {
        return new MailSendingMessageHandler(sender);
    }
}
~~~

Ý nghĩa:

- `outboundMail` là một Spring Integration channel.
- Handler gắn với channel nhận messages và thực hiện gửi.
- Handler ủy quyền transport cho `JavaMailSender`.
- `DirectChannel` thường gọi handler trên thread gửi message.
- Một `ExecutorChannel` hay broker-backed flow có timing/error semantics khác.

Handler không tự biến mọi Java object thành email đẹp: payload type phải thuộc những dạng mapping được hỗ trợ hoặc phải được biến đổi trước.

## 9. String payload + mail headers cho plain-text email

Một producer tạo integration message:

~~~java
import org.springframework.integration.mail.MailHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> email =
    MessageBuilder.withPayload(
            "Xin chào, đơn hàng #A123 đã xác nhận."
        )
        .setHeader(
            MailHeaders.TO,
            new String[] {"buyer@example.net"}
        )
        .setHeader(
            MailHeaders.FROM,
            "orders@example.com"
        )
        .setHeader(
            MailHeaders.SUBJECT,
            "Xác nhận đơn hàng #A123"
        )
        .build();

outboundMail.send(email);
~~~

`outboundMail` là `MessageChannel` đã inject theo bean name trong ứng dụng. Với outbound handler và String payload:

~~~text
Spring Message<String>
   |
   +--> payload ----------> mail text
   +--> mail_to ----------> recipient To
   +--> mail_from --------> sender From
   +--> mail_subject -----> Subject
   |
   v
MailSendingMessageHandler
   |
   v
JavaMailSender / SMTP
~~~

Đây là trường hợp đơn giản, không phải giải pháp tự động cho HTML alternative hay nhiều attachments.

## 10. Spring MailMessage có thể mang sẵn email fields

`org.springframework.mail.MailMessage` là abstraction email đơn giản. Ví dụ `SimpleMailMessage`:

~~~java
SimpleMailMessage payload = new SimpleMailMessage();

payload.setFrom("orders@example.com");
payload.setTo("buyer@example.net");
payload.setSubject("Thông báo");
payload.setText("Nội dung thông báo");
~~~

`MailSendingMessageHandler` có chiến lược xử lý payload đã là Spring `MailMessage`.

Ưu điểm:

- Các thuộc tính mail được đặt trong một object có interface cụ thể.
- Dễ unit test các fields.
- Phù hợp mail text đơn giản.
- Giữ mapping application tường minh trước transport.

Nhưng cần hiểu **priority giữa payload fields và Integration headers**.

## 11. Header override có thể làm thay đổi MailMessage

Ví dụ payload:

~~~java
SimpleMailMessage payload = new SimpleMailMessage();
payload.setTo("original@example.net");
payload.setFrom("orders@example.com");
payload.setSubject("Subject ban đầu");
payload.setText("Nội dung");
~~~

Flow lại gắn:

~~~java
Message<SimpleMailMessage> message =
    MessageBuilder.withPayload(payload)
        .setHeader(
            MailHeaders.TO,
            new String[] {"override@example.net"}
        )
        .setHeader(
            MailHeaders.SUBJECT,
            "Subject mới"
        )
        .build();
~~~

Spring Integration Mail outbound mapping cho phép các `MailHeaders` tương ứng **ghi đè giá trị MailMessage**. Do vậy recipient và subject thực tế có thể là giá trị từ headers, không phải payload object trước mapping.

### Rủi ro

- Người nhận bị chuyển sang địa chỉ khác ngoài ý định.
- Header upstream không tin cậy thay From/To.
- Test chỉ kiểm tra payload nhưng bỏ qua message SMTP server nhận.
- Hai nhóm phát triển không biết field nào có quyền ưu tiên.

**Khuyến nghị:** chỉ định một source of truth cho mỗi field. Nếu dùng mail headers làm overrides, tạo chúng ở một lớp validation/header enrichment duy nhất có quyền quyết định.

## 12. Header enrichment với business DTO

Giả sử dữ liệu ban đầu:

~~~java
public record NotificationRequest(
    String recipientAddress,
    String subject,
    String body
) {}
~~~

Một mapper có thể tạo message:

~~~java
public Message<String> mapToOutbound(
        NotificationRequest request) {

    validateRecipient(request.recipientAddress());

    return MessageBuilder.withPayload(request.body())
        .setHeader(
            MailHeaders.TO,
            new String[] {request.recipientAddress()}
        )
        .setHeader(
            MailHeaders.FROM,
            "notifications@example.com"
        )
        .setHeader(
            MailHeaders.SUBJECT,
            request.subject()
        )
        .build();
}
~~~

`validateRecipient` là hàm application cần triển khai; ví dụ không cung cấp toàn bộ implementation.

Quy trình:

1. Validate dữ liệu và quyền gửi.
2. Render body theo template/version.
3. Chuẩn hóa recipients.
4. Đặt mail headers từ nguồn đáng tin.
5. Chuyển payload thành dạng handler hỗ trợ.
6. Gửi qua channel.
7. Ghi nhận transport outcome.

Một header enricher trong Spring Integration cũng có thể dùng SpEL tính header values từ payload. Nhưng **chỉ enrich headers chưa đủ** nếu payload vẫn là DTO mà outbound handler không biết cách render.

## 13. Khi nào dùng ObjectToStringTransformer?

Tài liệu Spring Integration có đề cập `ObjectToStringTransformer` cho payload có `toString()` chính xác là nội dung mail cần gửi.

Nhưng với DTO nghiệp vụ:

~~~java
public record InvoiceEvent(
    String customerEmail,
    String invoiceId,
    long amount
) {}
~~~

`toString()` thường tạo dạng:

~~~text
InvoiceEvent[customerEmail=..., invoiceId=..., amount=...]
~~~

Đây không phải email mong muốn và có thể làm lộ internal fields. Thay vì dùng `toString()` tùy tiện, hãy render:

~~~java
String plain = templateRenderer.renderPlain(invoiceEvent);
String html = templateRenderer.renderHtml(invoiceEvent);
~~~

Rồi chuyển thành String payload cho text mail, hoặc dựng MIME cho email có HTML/multipart.

## 14. Byte array payload được map thành attachment

Spring Integration Mail hỗ trợ một số mapping khi payload là `byte[]`: dữ liệu có thể được coi là attachment. Trường `MailHeaders.ATTACHMENT_FILENAME` là bắt buộc trong trường hợp mapping kiểu này.

Ví dụ:

~~~java
byte[] reportBytes = loadReportFixture();

Message<byte[]> email =
    MessageBuilder.withPayload(reportBytes)
        .setHeader(
            MailHeaders.TO,
            new String[] {"reports@example.net"}
        )
        .setHeader(
            MailHeaders.FROM,
            "reporting@example.com"
        )
        .setHeader(
            MailHeaders.SUBJECT,
            "Báo cáo"
        )
        .setHeader(
            MailHeaders.ATTACHMENT_FILENAME,
            "report.csv"
        )
        .setHeader(
            MailHeaders.CONTENT_TYPE,
            "text/csv"
        )
        .build();
~~~

Đây là ví dụ metadata khi dùng attachment payload. Behavior chi tiết với content type/multipart phụ thuộc handler/version. Với nhiều attachments hoặc HTML alternative, nên dựng MIME riêng.

### Tại sao byte[] cần cân nhắc?

- Giữ toàn bộ attachment trong heap.
- Payload qua message broker có thể lớn.
- GC và serialization cost tăng.
- Retry có thể copy bytes nhiều lần.
- Không thể diễn đạt trực quan nhiều files và metadata phức tạp.

Với file lớn, lưu durable artifact ở object storage và truyền immutable reference qua outbox/message bus sẽ phù hợp hơn.

## 15. MimeMessage và MailMessage không giống nhau

Spring `SimpleMailMessage` implements `org.springframework.mail.MailMessage`. Nhưng `jakarta.mail.internet.MimeMessage` không phải subtype của interface này.

Vì vậy, không nên mặc định rằng gửi một `Message<MimeMessage>` vào `MailSendingMessageHandler` sẽ nhận tất cả header overrides theo đúng logic `MailMessage` hoặc được xử lý đồng nhất trên mọi phiên bản.

Đối với email nhiều MIME parts, cách dễ kiểm soát là:

- Dùng `MailSendingMessageHandler` cho payload types được Spring Integration version hiện tại hỗ trợ.
- Dùng custom Spring Integration service activator gọi `JavaMailSender` để dựng và gửi `MimeMessage` tường minh khi nội dung phức tạp.

Đừng lẫn Spring Integration `Message<?>` (routing unit) với Jakarta Mail `MimeMessage` (email format). Mối quan hệ của chúng phải được định nghĩa bằng transformer/adapter rõ ràng.

## 16. Khi nào nên dựng MimeMessage thủ công?

Sử dụng `MimeMessageHelper` nếu email cần:

- HTML cùng plain-text alternative.
- Multipart/alternative và multipart/mixed.
- PDF hoặc CSV attachments.
- Inline images qua CID.
- Unicode display names/subject.
- Custom MIME headers.
- Reply-To rõ ràng.
- Attachment streaming.
- Content-ID và Content-Disposition.

~~~text
Notification DTO
       |
       v
Render subject / plain / HTML
       |
       v
MimeMessageHelper
  - setFrom / setTo / setReplyTo
  - setSubject
  - setText(plain, html)
  - addAttachment / addInline
       |
       v
MimeMessage
       |
       v
JavaMailSender.send(...)
~~~

Spring Integration vẫn có thể làm routing, filtering, orchestration và error handling; chỉ phần MIME construction được giao cho adapter chuyên biệt.

## 17. Model đã chuẩn bị cho email phức tạp

Ví dụ:

~~~java
public record PreparedMail(
    UUID notificationId,
    String sender,
    List<String> to,
    List<String> cc,
    List<String> bcc,
    String replyTo,
    String subject,
    String plainText,
    String htmlText,
    List<PreparedAttachment> attachments
) {}
~~~

~~~java
public record PreparedAttachment(
    String storageKey,
    String fileName,
    String contentType
) {}
~~~

Các model là DTO tự thiết kế, không phải API sẵn có của Spring Integration.

Điểm quan trọng:

1. DTO chứa business data đã được validate.
2. Không chứa SMTP username/password/OAuth token.
3. Không chứa `MimeMessage` sống trong memory để serialize qua broker.
4. Không chứa `InputStream` mở sẵn.
5. Attachment references phải đọc lại được khi retry.
6. Sender/recipient phải được kiểm tra quyền trước khi gửi.
7. Content có thể cần template version và expiresAt.

## 18. Service activator gửi MIME tường minh

Một custom handler nhận `PreparedMail` từ channel:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.InputStreamSource;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class RichMailServiceActivator {

    private final JavaMailSender sender;
    private final ArtifactStore artifacts;

    public RichMailServiceActivator(
            JavaMailSender sender,
            ArtifactStore artifacts) {
        this.sender = sender;
        this.artifacts = artifacts;
    }

    @ServiceActivator(inputChannel = "richOutboundMail")
    public void send(PreparedMail prepared) {

        MimeMessage mime = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(prepared.sender());
            helper.setTo(prepared.to().toArray(String[]::new));

            if (!prepared.cc().isEmpty()) {
                helper.setCc(prepared.cc().toArray(String[]::new));
            }

            if (!prepared.bcc().isEmpty()) {
                helper.setBcc(prepared.bcc().toArray(String[]::new));
            }

            if (prepared.replyTo() != null) {
                helper.setReplyTo(prepared.replyTo());
            }

            helper.setSubject(prepared.subject());
            helper.setText(
                prepared.plainText(),
                prepared.htmlText()
            );

            for (PreparedAttachment attachment
                    : prepared.attachments()) {

                InputStreamSource source =
                    artifacts.openRepeatable(
                        attachment.storageKey()
                    );

                helper.addAttachment(
                    attachment.fileName(),
                    source,
                    attachment.contentType()
                );
            }

            mime.setHeader(
                "X-App-Notification-ID",
                prepared.notificationId().toString()
            );
        } catch (MessagingException exception) {
            throw new IllegalStateException(
                "Cannot construct mail MIME",
                exception
            );
        }

        sender.send(mime);
    }
}
~~~

Contract storage:

~~~java
public interface ArtifactStore {
    InputStreamSource openRepeatable(String key);
}
~~~

`InputStreamSource` phải cung cấp stream mới có thể đọc lại, không trả cùng một stream đã bị consume. Trong code production cần xác thực storage key, limit attachment bytes, xử lý I/O errors và phân loại SMTP failures.

Phương thức `send` này có một ranh giới rõ: **PreparedMail DTO được ánh xạ thành MimeMessage qua code tường minh**. Các Spring headers không được chép tự động ra MIME, tránh lộ metadata nội bộ.

## 19. Vẫn có thể dùng internal headers để routing

Một `Message<PreparedMail>` có thể chứa:

~~~text
notificationId = N-123
mailCategory   = TRANSACTIONAL
tenantId       = tenant-A
priority       = HIGH
providerId     = smtp-primary
traceId        = ...
~~~

Các headers này có ích để:

- Chọn sender adapter.
- Áp provider quota.
- Điều phối high-priority notifications.
- Correlate logs/spans.
- Kiểm tra deadline.
- Routing sang error channel.
- Deduplicate business events.

Nhưng không nên đưa raw `tenantId`, trace baggage hoặc internal security metadata vào MIME. Nếu cần một custom correlation MIME header, sử dụng opaque ID đã được whitelist và xem xét privacy.

Trong handler tùy biến:

~~~java
@ServiceActivator(inputChannel = "richOutboundMail")
public void handle(Message<PreparedMail> message) {
    PreparedMail mail = message.getPayload();
    String category =
        (String) message.getHeaders().get("mailCategory");

    // Validate category and business policy.
    richMailSender.send(mail, category);
}
~~~

`richMailSender` là abstraction của ứng dụng. Header có thể null hoặc không đúng kiểu, nên code thực tế cần xử lý an toàn trước cast.

## 20. Một nguồn sự thật cho mỗi mail field

| Field | Nguồn nên quản lý | Vì sao |
| --- | --- | --- |
| To | Recipient resolver/consent policy | Tránh gửi nhầm |
| Cc/Bcc | Business authorization | Tránh data leak |
| From | Verified sender account config | Tránh sender spoofing |
| Reply-To | Support/ticket routing policy | Phản hồi đúng nơi |
| Subject | Template renderer/version | Nội dung nhất quán |
| Plain/HTML | Content renderer | Escape/charset đúng |
| Attachments | Prepared artifact manifest | Repeatable bytes và security |
| Notification ID | Durable outbox | Correlation qua retry |
| SMTP credentials | Secret manager | Không đưa vào message |
| Provider/account | Infrastructure routing | Quota và phân quyền |

Một message từ API không nên tự được phép set `MailHeaders.FROM` hoặc `MailHeaders.BCC` mà không có authorization. Nếu không, endpoint outbound có thể bị lợi dụng để gửi từ alias không được phép hoặc gửi bản sao tới người ngoài.

## 21. MIME Reply-To và From là hai thứ khác nhau

Ví dụ:

~~~text
From: Notifications <notifications@example.com>
Reply-To: Support <support@example.com>
To: buyer@example.net
Subject: Xác nhận đơn hàng
~~~

`MailHeaders.FROM` và `MailHeaders.REPLY_TO` riêng biệt; `MimeMessageHelper` cũng có setters riêng.

Provider có thể yêu cầu From trùng account/verified domain hoặc cần send-as permission. AUTH thành công không đồng nghĩa mọi From address đều được phép. Đặt Reply-To chỉ hướng người nhận reply, **không** tự tạo inbound mailbox reader.

## 22. Bcc và SMTP envelope

Bcc không phải một public header bắt buộc trong MIME đã phát tới các recipients.

~~~text
Integration header:
  mail_bcc = ["audit@example.net"]

SMTP envelope:
  RCPT TO:<audit@example.net>

Delivered MIME:
  Bcc header thường không xuất hiện
~~~

Nếu test chỉ kiểm tra `getRecipients(BCC)` trên message đã nhận, có thể không thấy Bcc và kết luận sai. Khi cần xác minh recipient ẩn, kiểm tra SMTP test server envelope hoặc mailbox capture phù hợp.

Không copy `mail_bcc` sang custom header vì sẽ làm lộ danh sách recipient ẩn.

## 23. HTML không chỉ là một String chứa thẻ HTML

Payload:

~~~text
<h1>Xin chào</h1>
~~~

nếu đi qua text mapping đơn giản có thể được gửi như plain text. Việc đặt `contentType=text/html` ở Spring Messaging layer không tự tạo đầy đủ MIME HTML/alternative structure trong mọi handler.

Tạo MIME tường minh:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("buyer@example.net");
helper.setSubject("Chào mừng");

helper.setText(
    "Xin chào, cảm ơn bạn đã đăng ký.",
    "<html><body><h1>Xin chào</h1>"
        + "<p>Cảm ơn bạn đã đăng ký.</p>"
        + "</body></html>"
);

sender.send(mime);
~~~

`setText(plain, html)` giúp tạo nội dung alternative. Khi có attachment, cấu trúc có thể được bọc bởi các multipart containers, nên top-level không còn là `text/html`.

## 24. Cấu trúc MIME khi có nhiều phần

~~~text
MimeMessage
  |
  +--> multipart/mixed
          |
          +--> multipart/related
          |       |
          |       +--> multipart/alternative
          |       |       +--> text/plain
          |       |       +--> text/html
          |       |
          |       +--> image/png
          |               Content-ID: <logo>
          |
          +--> application/pdf
                  Content-Disposition: attachment
                  filename=invoice.pdf
~~~

Cấu trúc cụ thể phụ thuộc `MimeMessageHelper` multipart mode và implementation. Không test bằng cách giả định boundary hoặc order raw MIME luôn giống nhau. Tìm parts theo type/disposition/Content-ID/filename.

Đây là lý do các nhu cầu rich email không nên bị ép vào một tập String headers đơn giản.

## 25. Inline image cần Content-ID

~~~java
helper.setText(
    "<html><body>"
        + "<img src=\"cid:brandLogo\">"
        + "<p>Xin chào!</p>"
        + "</body></html>",
    true
);

helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
~~~

Attachment inline và HTML phải tham chiếu cùng ID. `ClassPathResource` phù hợp tài nguyên nằm trong classpath/JAR. Không luôn dùng `getFile()` với classpath resource trong executable JAR; có thể phải dùng input stream.

Nên đặt HTML text trước khi add inline theo cách dùng của `MimeMessageHelper`.

## 26. Charset và Unicode trong mapping

Subject và body tiếng Việt cần encoding hợp lệ:

~~~text
Subject: Xác nhận thanh toán – Đơn hàng #123
Body: Xin chào, hóa đơn của bạn đã sẵn sàng.
~~~

`MimeMessageHelper(..., "UTF-8")` giúp chuẩn hóa việc dựng message. Khi đọc lại bằng Jakarta Mail:

~~~java
assertEquals(
    "Xác nhận thanh toán – Đơn hàng #123",
    received.getSubject()
);
~~~

`getSubject()` trả giá trị đã giải mã. Raw MIME header có thể chứa encoded-word như `=?UTF-8?...?=` nên không phù hợp để so sánh trực tiếp với String Unicode.

Chỉ vì Spring MessageHeaders chứa một String Unicode không có nghĩa MIME charset đã được cấu hình đúng. Việc encoding thuộc bước mapping sang MIME.

## 27. Attachment name và resource lifecycle

Một attachment có ít nhất:

- Filename.
- Content-Type.
- Content-Disposition.
- Content transfer encoding.
- Dữ liệu bytes thực tế.
- Size/retention policy trong application.

Với byte-array mapping, `MailHeaders.ATTACHMENT_FILENAME` xác định tên file. Với custom MIME builder, `helper.addAttachment(...)` nhận filename và resource.

Tránh:

~~~java
InputStream stream = storage.open(key);

InputStreamSource source = () -> stream;
~~~

Đây là non-repeatable stream. Nếu Jakarta Mail yêu cầu đọc lần hai, content có thể rỗng/lỗi.

Tốt hơn:

~~~java
InputStreamSource source = () -> storage.open(key);
~~~

Mỗi lần `getInputStream()` phải trả stream mới tới cùng immutable artifact. `ByteArrayResource` phù hợp file nhỏ đã trong memory; với file lớn, lưu durable artifact và stream từ storage.

## 28. Message-ID, notification ID và trace ID

Một notification có thể có nhiều IDs:

| ID | Vai trò |
| --- | --- |
| Spring `MessageHeaders.ID` | Định danh message ở integration layer |
| `notificationId` | Business/outbox identity của email logic |
| MIME `Message-ID` | Header email |
| Provider queue/message ID | Do SMTP/ESP cung cấp nếu có |
| Trace ID/span ID | Quan sát execution |

Chúng không tự bằng nhau. Không dùng Spring Message ID làm idempotency key xuyên nhiều attempts nếu mỗi retry tạo message mới. `notificationId` nên giữ nguyên trong durable outbox.

Một custom MIME header có thể dùng opaque ID:

~~~java
mime.setHeader(
    "X-App-Notification-ID",
    prepared.notificationId().toString()
);
~~~

Cần xem privacy trước khi thêm; provider có thể không giữ header. MIME Message-ID tự nó không bảo đảm SMTP deduplication.

## 29. Header injection và validation

Một sender nếu lấy toàn bộ mail headers từ untrusted API input có thể gặp:

- CRLF/header injection.
- Invalid addresses.
- Unauthorized From/send-as.
- Bcc exfiltration.
- Subject/body quá lớn.
- Header values mang credential hoặc internal metadata.
- Mail relay abuse.
- Open redirect hoặc URL không an toàn trong HTML.

Hãy dùng API setter của Spring/Jakarta Mail thay vì nối raw header strings và validate theo business policy. Header mapper chỉ làm chuyển đổi dữ liệu, không tự hiểu người dùng có quyền gửi thư dưới địa chỉ nào.

Một policy nên:

~~~text
Business request
       |
       v
Validate recipients / consent
       |
       v
Resolve authorized sender
       |
       v
Render content
       |
       v
Map approved mail fields
       |
       v
Outbound mail handler
~~~

Không dùng generic “copy all headers” từ HTTP request tới SMTP.

## 30. Mapping inbound là một trường hợp khác

Spring Integration Mail có inbound receivers như `ImapMailReceiver` và `Pop3MailReceiver`. Khi nhận email, adapter có thể đưa raw `MimeMessage` vào payload.

Khi cấu hình `DefaultMailHeaderMapper`, một số thông tin MIME headers được ánh xạ sang Spring Integration `MessageHeaders`.

Ví dụ MIME:

~~~text
From: alice@example.net
To: support@example.com
Subject: Cần hỗ trợ đơn hàng
Content-Type: text/plain; charset=UTF-8

Xin chào, tôi cần hỗ trợ.
~~~

Kết quả mapped message minh họa:

~~~text
payload = "Xin chào, tôi cần hỗ trợ."
headers:
  mail_from = "alice@example.net"
  mail_to = ["support@example.com"]
  mail_subject = "Cần hỗ trợ đơn hàng"
  mail_contentType = "text/plain; charset=UTF-8"
~~~

Đây là trường hợp text mail với mapper được cấu hình; không mặc định tất cả inbound mail trở thành String.

## 31. DefaultMailHeaderMapper ánh xạ những field nào?

| Inbound Spring header | Nội dung |
| --- | --- |
| `mail_from` | From dạng String |
| `mail_to` | To addresses dạng String array |
| `mail_cc` | Cc addresses |
| `mail_bcc` | Bcc nếu original MIME có |
| `mail_replyTo` | Reply-To |
| `mail_subject` | Subject |
| `mail_receivedDate` | Ngày nhận nếu có |
| `mail_size` | Size nếu có |
| `mail_lineCount` | Số dòng nếu có |
| `mail_expunged` | Message expunged flag |
| `mail_raw` | Original mail headers map |
| `mail_contentType` | Content type của email gốc |
| `contentType` | Content type của Spring payload sau mapping |

Phân biệt `mail_contentType` và `contentType` rất quan trọng khi MIME có multipart/attachment và mapper chuyển payload sang bytes.

Một header inbound thiếu không chứng minh field luôn tồn tại: không phải mọi email hoặc provider cung cấp cùng metadata.

## 32. Inbound payload có thể là String, byte[] hoặc MimeMessage

Theo receiver/mapping configuration:

- Không cung cấp header mapper: raw `MimeMessage` thường là payload.
- Với `text/*` và mapper: payload có thể là `String`.
- Với embedded `Part`/`Multipart`: payload có thể được render thành `byte[]` để tránh serialize non-serializable Jakarta Mail parts.
- Khi `embeddedPartsAsBytes=false`, receiver có thể đưa Multipart object theo cấu hình.
- Với content type lạ, payload có thể là `byte[]` với `contentType=application/octet-stream`.

Vì vậy code sau không an toàn nếu chưa kiểm tra type:

~~~java
String body = (String) message.getPayload();
~~~

Một consumer robust phải phân nhánh theo type hoặc dùng MIME-aware transformer. Không lấy byte[] multipart rồi dùng new String(bytes, UTF-8) và kỳ vọng trở thành email text đúng.

## 33. MailToStringTransformer có công dụng gì?

`MailToStringTransformer` có thể chuyển nội dung email inbound thành String theo cơ chế của Spring Integration.

~~~text
IMAP inbound
      |
      v
MailToStringTransformer
      |
      v
String payload
      |
      v
Business parser / classifier
~~~

Nó hữu ích khi use case chỉ cần text. Nhưng không phải:

- HTML sanitizer tổng quát.
- Antivirus scanner.
- Bộ parse mọi attachment.
- Chứng minh danh tính của sender.
- Cơ chế bảo đảm business idempotency.

Nếu cần giữ hình ảnh/attachments hoặc MIME nested parts, nên xử lý raw MIME/Part với giới hạn tài nguyên và tạo một inbound DTO đã chuẩn hóa.

## 34. IMAP folder lifecycle và lazy MimeMessage

Một số IMAP messages đọc nội dung lazy từ server. Với Spring Integration receiver, cấu hình `autoCloseFolder` và mapping có thể ảnh hưởng thời điểm folder được đóng.

~~~text
Mail receiver
     |
     v
MimeMessage payload (may have lazy content)
     |
     v
ExecutorChannel / asynchronous handler
     |
     v
Folder already closed?
     |
     +--> Attachment/body read may fail
~~~

Một số phiên bản Spring Integration hỗ trợ closeable resource header khi không tự đóng folder. Downstream chịu trách nhiệm đóng resource sau khi đọc xong.

Ý tưởng:

~~~java
Closeable closeable =
    StaticMessageHeaderAccessor.getCloseableResource(
        integrationMessage
    );

try {
    // Consume MIME contents while mailbox resource is alive.
} finally {
    if (closeable != null) {
        closeable.close();
    }
}
~~~

Cần imports `java.io.Closeable` và accessor Spring Integration tương ứng version. Nếu flow phải đưa inbound content qua broker, nên materialize/parsing thành DTO bytes/text có giới hạn trước khi đóng folder, thay vì serialize một live `MimeMessage` hoặc `Multipart` phụ thuộc connection.

## 35. Đừng forward raw inbound headers sang outbound

Luồng nguy hiểm:

~~~text
Untrusted inbound email
  mail_from = attacker@example.net
  mail_to = some-user@example.net
  mail_replyTo = arbitrary@example.net
        |
        v
Copy all inbound headers
        |
        v
Outbound mail adapter
~~~

Kẻ gửi có thể điều khiển From/Reply-To và đôi khi header khác. Nếu ứng dụng copy chúng thành outbound headers, có thể gửi mail dưới danh tính sai hoặc rò dữ liệu.

Hướng an toàn:

1. Parse và validate inbound mail.
2. Xác định ticket/business context qua dữ liệu đáng tin.
3. Tạo outbound DTO mới.
4. Chọn sender và recipients bằng application policy.
5. Chỉ copy nội dung cho phép, đã sanitize/escape.
6. Dựng MIME mới hoặc mapping mail headers từ nguồn đã kiểm soát.

Header From là dữ liệu do sender khai báo, không đủ để xác thực một yêu cầu nghiệp vụ nhạy cảm.

## 36. Mapping và SMTP error là hai tầng khác

| Lỗi | Giai đoạn | Phản ứng phù hợp |
| --- | --- | --- |
| DTO payload chưa được transform | Mapping | Sửa transformer/type contract |
| Không có `mail_to` | Validation/mapping | Validate recipient |
| Thiếu attachment filename | Attachment mapping | Đặt `MailHeaders.ATTACHMENT_FILENAME` |
| HTML hiển thị nguyên thẻ | MIME preparation | Tạo HTML part đúng |
| Multipart cast thành String | Inbound mapping | Type-aware MIME parsing |
| Không đọc được attachment | Resource/MIME | Kiểm tra storage/stream |
| SMTP AUTH sai | Transport | Sửa credential/mechanism |
| SMTP 421 tạm thời | Transport | Retry/backoff phù hợp |
| SMTP timeout sau DATA | Ambiguous transport | Đối soát, đề phòng duplicate |
| Provider bounce | Downstream delivery | Xử lý provider events, không đổ lỗi mapping |

Không retry vô hạn toàn bộ pipeline vì một DTO không hỗ trợ hoặc template lỗi vĩnh viễn. Cần phân loại preparation/mapping failures và SMTP submission failures riêng.

## 37. Channels, async và transaction boundaries

Với `DirectChannel`, handler thường chạy cùng thread caller. Với `ExecutorChannel` hoặc broker-backed flow, message có thể được xử lý bất đồng bộ.

Hệ quả:

- `MessageChannel.send(...)` true không chứng minh SMTP đã gửi.
- Exception có thể chuyển sang error channel/log thay vì caller.
- Trace/MDC context cần propagation phù hợp.
- Broker có thể redeliver cùng logical message.
- Retry có thể khiến SMTP submit nhiều lần.
- In-memory queue không phải durable source of truth.

Với email quan trọng:

~~~text
Business transaction
      |
      v
Durable outbox
      |
      v
Worker claim
      |
      v
Prepare/map content
      |
      v
Mail integration channel
      |
      v
Mail handler -> JavaMailSender
      |
      v
Record SUBMITTED/RETRY_WAIT/AMBIGUOUS
~~~

Không giữ database transaction qua SMTP network calls. `JavaMailSender.send(...)` thành công cho biết submission theo transport contract, không chứng minh người nhận đã thấy thư.

## 38. Retry và idempotency qua mapping

Một notification nên có ID ổn định:

~~~text
notificationId=N-123
     |
     +--> attempt A1: timeout
     +--> attempt A2: transient rejection
     +--> attempt A3: accepted
~~~

Mapping nên sử dụng cùng prepared content/version ở những attempts lặp lại nếu nghiệp vụ yêu cầu nội dung không đổi.

`MessageHeaders.ID` có thể thay đổi giữa các messages/attempts; nó không phải business idempotency key. Cũng không dựa vào MIME `Message-ID` để bảo đảm SMTP server deduplicate.

Khi SMTP timeout sau DATA, client không chắc server đã nhận chưa; đừng báo chắc chắn NOT_SENT. Đánh dấu AMBIGUOUS theo policy và cân nhắc reconciliation trước retry.

## 39. Kiểm thử unit mapping

Một test mapper:

~~~java
@Test
void mapsDtoToMailTextAndHeaders() {
    NotificationRequest request = new NotificationRequest(
        "buyer@example.net",
        "Xác nhận đơn hàng",
        "Đơn hàng đã được xác nhận."
    );

    Message<String> mapped = mapper.mapToOutbound(request);

    assertEquals(
        "Đơn hàng đã được xác nhận.",
        mapped.getPayload()
    );

    assertArrayEquals(
        new String[] {"buyer@example.net"},
        (String[]) mapped.getHeaders().get(MailHeaders.TO)
    );

    assertEquals(
        "Xác nhận đơn hàng",
        mapped.getHeaders().get(MailHeaders.SUBJECT)
    );

    assertEquals(
        "notifications@example.com",
        mapped.getHeaders().get(MailHeaders.FROM)
    );
}
~~~

`mapper` là component ứng dụng, không phải API có sẵn. Đây là unit test **dữ liệu trước outbound handler**, không chứng minh SMTP server nhận gì.

Ngoài ra nên test header precedence: payload `SimpleMailMessage` có subject/to A, Integration headers đặt B, rồi xem message cuối theo behavior thực của handler/version.

## 40. SMTP integration test để kiểm chứng mapping cuối

Dùng GreenMail hoặc SMTP capture server:

~~~text
JUnit / Spring Integration flow
          |
          v
MessageBuilder + MailHeaders
          |
          v
MailSendingMessageHandler
          |
          v
JavaMailSender
          |
          v
GreenMail
          |
          v
Captured MimeMessage[]
          |
          v
Assertions on actual MIME
~~~

Ví dụ assertions sau khi server test đã start, sender trỏ tới loopback và flow được gọi:

~~~java
assertTrue(greenMail.waitForIncomingEmail(5000, 1));

MimeMessage[] captured = greenMail.getReceivedMessages();
assertEquals(1, captured.length);

MimeMessage received = captured[0];

assertEquals(
    "Xác nhận đơn hàng",
    received.getSubject()
);

assertEquals(
    "buyer@example.net",
    ((InternetAddress) received.getRecipients(
        jakarta.mail.Message.RecipientType.TO
    )[0]).getAddress()
);

assertTrue(received.isMimeType("text/plain"));
assertTrue(
    ((String) received.getContent()).contains(
        "Đơn hàng đã được xác nhận."
    )
);
~~~

Đọc **message phía SMTP test server**, không chỉ assert lại Spring MessageHeaders ban đầu. Khi thử rich MIME, duyệt parts để tìm plain/HTML và attachments; không ép top-level Multipart thành String.

## 41. Kiểm thử rich MIME/attachments

Với custom MimeMessage sender, nên kiểm tra:

- From/To/Cc/Reply-To.
- Subject tiếng Việt đã giải mã.
- Plain-text và HTML alternative.
- Multipart structure hợp lý.
- Inline image Content-ID tương ứng HTML `cid:...`.
- Attachment filename, Content-Type và byte content.
- Header Bcc không bị lộ ngoài ý muốn.
- Custom correlation ID là opaque identifier.
- Không gửi duplicate ngoài dự kiến.
- Retry dùng artifact còn đọc được.

Một helper tìm text part:

~~~java
static String findTextPart(
        jakarta.mail.Part part,
        String wantedType) throws Exception {

    if (jakarta.mail.Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        return null;
    }

    if (part.isMimeType(wantedType)) {
        Object content = part.getContent();
        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        jakarta.mail.Multipart mp =
            (jakarta.mail.Multipart) part.getContent();

        for (int i = 0; i < mp.getCount(); i++) {
            String value = findTextPart(
                mp.getBodyPart(i),
                wantedType
            );

            if (value != null) {
                return value;
            }
        }
    }

    return null;
}
~~~

Đây là helper test cho MIME tương đối đơn giản; production inbound parser cần thêm giới hạn nesting, part count, decoded bytes và xử lý nested `message/rfc822`.

## 42. Kiểm thử inbound header mapping

Nếu application đọc Inbox:

1. Khởi động test SMTP + IMAP server.
2. Gửi một email có From, To, Subject, MIME body/attachment.
3. Cấu hình `ImapMailReceiver` và `DefaultMailHeaderMapper` khi cần.
4. Đọc Spring message inbound được phát ra.
5. Kiểm tra `mail_from`, `mail_subject` và `mail_to`.
6. Xác minh payload type đúng cho text hoặc multipart.
7. Kiểm tra `mail_contentType` khác `contentType` trong trường hợp tương ứng.
8. Đóng folder/closeable resource theo receiver lifecycle.
9. Kiểm tra malformed email và content limit.
10. Không dùng IMAP integration test như bằng chứng deliverability production.

Inbound mapping và outbound mapping là hai contract riêng. Đừng coi chúng là phép biến đổi đối xứng rồi forward headers nguyên vẹn.

## 43. Monitoring và correlation

Những observations hữu ích:

~~~text
notification.validate
       |
       v
mail.payload.transform
       |
       v
mail.header.map
       |
       v
mail.mime.prepare
       |
       v
mail.smtp.submit
       |
       v
mail.outbox.update
~~~

Theo dõi:

- Unsupported payload type/mapping failure count.
- Missing mail headers count.
- MIME preparation duration.
- Attachment load errors.
- SMTP submission duration và failure class.
- Queue age, retry rate, provider throttling.
- Message size distribution.
- Outcomes SUBMITTED, FAILED và AMBIGUOUS.

`notificationId` trong structured logs giúp nối các stages. Không dùng recipient email, subject hoặc attachment path làm metric label; chúng có thể lộ PII và làm cardinality tăng.

## 44. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách thay thế |
| --- | --- | --- |
| Coi Spring `Message<?>` là `MimeMessage` | Sai boundary | Dùng transformer/adapter rõ |
| Copy mọi Spring header sang email | Lộ metadata nội bộ | Whitelist MIME headers |
| Gắn `contentType=text/html` và kỳ vọng HTML full | MIME body không đúng | Dựng MimeMessageHelper |
| Dùng `toString()` của DTO | Body khó đọc, lộ fields | Render template |
| Coi byte[] là text body | Mapping thành attachment | Chọn payload đúng |
| Quên filename khi byte[] attachment | Handler không đủ metadata | `MailHeaders.ATTACHMENT_FILENAME` |
| Cùng field có giá trị khác trong payload và header | Override bất ngờ | Một source of truth |
| Cho upstream tùy ý đặt From/Bcc | Data leak/open relay | Authorized sender resolver |
| Truyền một InputStream đã mở | Attachment có thể rỗng | Repeatable source |
| Serialize raw MimeMessage/Part vào broker | Connection/serialization lỗi | Prepared DTO + refs |
| Forward raw inbound headers | Spoofing/routing sai | Validate/remap |
| Bcc được ghi vào custom public header | Lộ người nhận ẩn | Giữ Bcc trong envelope |
| Coi channel.send thành delivered | Status sai | Submission/delivery riêng |
| Dựa vào Message-ID để exactly-once | SMTP không bảo đảm dedup | Business idempotency |
| Mock sender rồi gọi SMTP integration test | Không thử transport/MIME | SMTP capture test |
| Không xử lý IMAP folder lifecycle | Attachment read lỗi/rò connection | Close resource đúng |

## 45. Lộ trình triển khai

1. **Xác định loại email**: plain text, HTML hoặc MIME phức tạp.
2. **Thiết kế payload model** và định nghĩa headers bắt buộc.
3. **Chọn nguồn dữ liệu đáng tin** cho To, From, Reply-To và Subject.
4. **Validate recipient và sender authorization** trước mapping.
5. **Dùng MailSendingMessageHandler** cho mapping đơn giản được hỗ trợ.
6. **Dùng transformer** khi payload ban đầu là DTO nghiệp vụ.
7. **Dùng custom MimeMessage builder** với HTML/attachment/inline.
8. **Không copy raw headers** từ request/inbound message tới outgoing MIME.
9. **Lưu notification ID bền vững** và artifact references khi cần retry.
10. **Phân loại mapping failure** khác SMTP transport errors.
11. **Nếu xử lý inbound**, cấu hình DefaultMailHeaderMapper có chủ đích.
12. **Xử lý inbound theo payload type**, không cast tùy tiện.
13. **Giữ IMAP resource alive khi parse lazy content**, rồi đóng đúng.
14. **Kiểm thử bằng SMTP capture** để xác minh MIME thực tế.
15. **Theo dõi metrics/logs** nhưng tránh dữ liệu nhạy cảm trong telemetry.

## 46. Ghi nhớ

- Spring Integration `Message<?>` khác Jakarta Mail `MimeMessage`.
- Payload chứa nội dung, headers chứa metadata của pipeline.
- `MailSendingMessageHandler` dùng `JavaMailSender` để thực hiện outbound sending.
- Các `MailHeaders` phổ biến gồm TO, CC, BCC, FROM, REPLY_TO và SUBJECT.
- Header mapping có thể ghi đè giá trị đã có trong Spring `MailMessage`.
- String payload phù hợp plain-text mail đơn giản.
- Byte[] payload có thể được map thành attachment và cần filename.
- DTO nghiệp vụ cần transformer, không dựa vào `toString()` tùy tiện.
- HTML/alternative/attachments/inline cần MIME builder rõ ràng.
- `MessageHeaders.CONTENT_TYPE` và `MailHeaders.CONTENT_TYPE` không phải một key.
- Không phải mọi Spring header sẽ hoặc nên trở thành MIME header.
- Bcc không được lộ qua custom public headers.
- Unicode cần được mã hóa đúng tại MIME layer.
- Inbound `DefaultMailHeaderMapper` khi cấu hình có thể map MIME headers sang Spring headers.
- Inbound payload có thể là MimeMessage, String, bytes hoặc Multipart tùy settings.
- Không serialize sống một `MimeMessage`/`Part` phụ thuộc IMAP connection.
- Correlation ID, Spring Message ID, MIME Message-ID và provider queue ID là các ID khác nhau.
- SMTP accepted không đồng nghĩa delivered hoặc opened.
- Kiểm thử mapping cuối bằng cách đọc MIME mà SMTP test server thực sự nhận.

**Nguyên tắc cốt lõi:** Xem Spring Integration Message là **đơn vị điều phối nội bộ**, còn MimeMessage là **định dạng email ngoài hệ thống**. Với plain text có thể map String payload và các MailHeaders được hỗ trợ. Với HTML, multipart và attachment, nên chuẩn hóa dữ liệu rồi dựng MIME tường minh qua JavaMailSender/MimeMessageHelper. Chỉ đưa những trường được phép ra email và giữ internal metadata trong application boundary.

## 47. Tài liệu tham khảo

- Spring Integration Mail Support: https://docs.spring.io/spring-integration/reference/mail.html
- Spring Integration MailHeaders API: https://docs.spring.io/spring-integration/api/org/springframework/integration/mail/MailHeaders.html
- Spring Framework Email Support: https://docs.spring.io/spring-framework/reference/integration/email.html

Đối chiếu các API và options theo phiên bản Spring Boot/Spring Integration đang sử dụng, đặc biệt khi dự án nâng major version.

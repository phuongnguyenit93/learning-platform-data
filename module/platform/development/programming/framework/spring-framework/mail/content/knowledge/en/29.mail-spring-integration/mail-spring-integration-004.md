# Mapping Payload and Headers to MimeMessage in Spring Integration Mail

In Spring Integration, data flowing through channels is wrapped in `org.springframework.messaging.Message<T>` with two parts: **payload** (the content) and **headers** (metadata). When a flow sends an email, this data must be converted into email fields such as To, From, Subject, Reply-To, plain-text/HTML content, and MIME parts like attachments or inline images.

A common point of confusion: **a Spring Integration Message is not a Jakarta Mail MimeMessage**. Two object types share the name "message" but belong to two different layers:

- `org.springframework.messaging.Message<T>` is the message passed between integration endpoints.
- `org.springframework.mail.MailMessage` is the interface representing simple email properties; `SimpleMailMessage` is the common implementation.
- `jakarta.mail.internet.MimeMessage` is the MIME message with headers, body, multipart sections, attachments, and email-formatted content.
- `JavaMailSender` is Spring's abstraction for creating and sending `MimeMessage` over SMTP.
- `MailSendingMessageHandler` is Spring Integration's outbound handler, which receives Spring messages and delegates sending to Spring Mail.

This lesson focuses on **mapping from Spring payloads/headers to actual emails**, using `MailHeaders` and transformers, the implications of header overrides, building MIME for complex emails, inbound-side mapping, and verifying results with an SMTP test server.

## 1. Outbound Flow Map

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
             or custom handler
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

The flow can use a built-in handler for simple text or a custom handler to assemble multipart MIME. SMTP settings live on `JavaMailSender`; payload/header mapping lives in the Spring Integration flow and its transformers/service activators.

## 2. What Does a Spring Message Contain?

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> integrationMessage =
    MessageBuilder.withPayload(
            "Your order has been confirmed."
        )
        .setHeader("notificationId", "N-123")
        .setHeader("category", "TRANSACTIONAL")
        .build();
~~~

In this example:

- The payload is the intended text body.
- `notificationId` and `category` are internal metadata.
- Default headers such as message ID/timestamp serve the framework.
- There is no recipient, sender, or subject yet to send an email.
- There is no rule that "every Spring header becomes a MIME header".

To send, the application must add permitted mail attributes or convert the payload into an appropriate `MailMessage`/`MimeMessage`.

## 3. Distinguishing Three Header Layers

| Layer | Data Shape | Example |
| --- | --- | --- |
| Spring Integration headers | `MessageHeaders` key/value pairs | `mail_to`, `notificationId` |
| MIME email headers | Headers inside the message sent to a mailbox | `To:`, `Subject:`, `Content-Type:` |
| SMTP envelope | Commands for transport | `MAIL FROM`, `RCPT TO` |

A Spring header `mail_to` can be used by the handler as email recipients. The resulting MIME message can carry a To header, while transport uses `RCPT TO` in the SMTP session. However, this is not an absolute 1:1 mapping: Bcc recipients can be placed into the SMTP envelope without a Bcc header appearing in the email seen by other recipients.

**Never copy all Spring MessageHeaders into MIME headers.** They may contain tenant IDs, trace baggage, internal URLs, OAuth tokens, or metadata not meant for recipients.

## 4. Key Components of Spring Integration Mail

| Component | Role |
| --- | --- |
| `MailSendingMessageHandler` | Receives messages from an outbound channel and sends via Spring Mail |
| `MailHeaders` | Constant names for email metadata |
| `MailReceivingMessageSource` | Produces integration messages from a mailbox |
| `ImapMailReceiver` | Receives via IMAP |
| `Pop3MailReceiver` | Receives via POP3 |
| `ImapIdleChannelAdapter` | Receives mailbox changes via IMAP IDLE when supported by the server |
| `DefaultMailHeaderMapper` | Maps MIME headers of inbound messages into Spring headers |
| `MailToStringTransformer` | Converts incoming mail content to String when appropriate |
| `JavaMailSender` | Spring Mail interface for creating/sending MIME |
| `MimeMessageHelper` | Helper for building MIME, HTML, attachments, and inline resources |

This module does not manage business consent, suppression, durable outboxes, or sender authorization on its own. Those belong to application policy.

## 5. Dependencies and Version Compatibility

Maven example:

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

Use Spring Boot's dependency management to select compatible Spring Framework, Spring Integration, and Jakarta Mail implementations. Spring Boot 3/Spring Framework 6 uses `jakarta.mail.*`, while older generations use `javax.mail.*`. Do not mix namespaces.

Spring Integration Mail is an additional module, not a `receive()` feature or comprehensive mapping that appears automatically simply because the project includes `spring-boot-starter-mail`.

## 6. MailHeaders in Outbound Mapping

Common constants in `org.springframework.integration.mail.MailHeaders`:

| Constant | Header Key | Role |
| --- | --- | --- |
| `MailHeaders.TO` | `mail_to` | To recipients |
| `MailHeaders.CC` | `mail_cc` | Cc recipients |
| `MailHeaders.BCC` | `mail_bcc` | Bcc recipients |
| `MailHeaders.FROM` | `mail_from` | From |
| `MailHeaders.REPLY_TO` | `mail_replyTo` | Reply-To |
| `MailHeaders.SUBJECT` | `mail_subject` | Subject |
| `MailHeaders.ATTACHMENT_FILENAME` | `mail_attachmentFilename` | Attachment filename in supported cases |
| `MailHeaders.CONTENT_TYPE` | `mail_contentType` | Mail-related content type |
| `MailHeaders.MULTIPART_MODE` | `mail_multipartMode` | Multipart information in supported cases |

In outbound text mapping, the six most commonly used fields are **To, Cc, Bcc, From, Reply-To, and Subject**.

Use constants instead of typing raw strings to avoid typos. `mail_replyTo` differs from `mail_reply_to`.

### Spring MessageHeaders.CONTENT_TYPE Is Not MailHeaders.CONTENT_TYPE

`MessageHeaders.CONTENT_TYPE` uses Spring Messaging's `contentType` key. `MailHeaders.CONTENT_TYPE` uses `mail_contentType`. They differ in origin and meaning.

A Spring message carrying `contentType=application/json` does not automatically become an `application/json` MIME email, nor does it automatically turn JSON into a useful email body.

## 7. Configuring JavaMailSender for the Outbound Handler

Spring Boot `application.yml` example:

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

`JavaMailSender` uses these properties to connect to SMTP. Never put passwords or access tokens into Spring message headers. SMTP credentials belong to infrastructure configuration/secret managers, not business events.

`spring.mail.*` only solves transport configuration; it does not perform payload-to-MIME mapping for the flow.

## 8. Wiring MailSendingMessageHandler to a Channel

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

Meaning:

- `outboundMail` is a Spring Integration channel.
- The handler bound to the channel receives messages and sends them.
- The handler delegates transport to `JavaMailSender`.
- `DirectChannel` normally invokes the handler on the message-sending thread.
- An `ExecutorChannel` or broker-backed flow has different timing and error semantics.

The handler does not automatically turn every Java object into a well-formatted email: the payload type must match a supported mapping form or be transformed beforehand.

## 9. String Payload + Mail Headers for Plain-Text Email

A producer builds an integration message:

~~~java
import org.springframework.integration.mail.MailHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> email =
    MessageBuilder.withPayload(
            "Hello, order #A123 has been confirmed."
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
            "Order #A123 confirmation"
        )
        .build();

outboundMail.send(email);
~~~

`outboundMail` is a `MessageChannel` injected by bean name in the application. With the outbound handler and a `String` payload:

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

This is the simple case, not an automatic solution for HTML alternatives or multiple attachments.

## 10. Spring MailMessage Can Carry Pre-Built Email Fields

`org.springframework.mail.MailMessage` is the simple email abstraction. Example `SimpleMailMessage`:

~~~java
SimpleMailMessage payload = new SimpleMailMessage();

payload.setFrom("orders@example.com");
payload.setTo("buyer@example.net");
payload.setSubject("Notification");
payload.setText("Notification content");
~~~

`MailSendingMessageHandler` has a strategy for handling payloads that are already a Spring `MailMessage`.

Advantages:

- Email properties are held in an object with a concrete interface.
- Easy to unit test fields.
- Fits simple text emails.
- Keeps application mapping explicit before transport.

However, you must understand **precedence between payload fields and Integration headers**.

## 11. Header Overrides Can Modify MailMessage

Payload example:

~~~java
SimpleMailMessage payload = new SimpleMailMessage();
payload.setTo("original@example.net");
payload.setFrom("orders@example.com");
payload.setSubject("Initial subject");
payload.setText("Content");
~~~

Yet the flow attaches:

~~~java
Message<SimpleMailMessage> message =
    MessageBuilder.withPayload(payload)
        .setHeader(
            MailHeaders.TO,
            new String[] {"override@example.net"}
        )
        .setHeader(
            MailHeaders.SUBJECT,
            "New subject"
        )
        .build();
~~~

Spring Integration Mail outbound mapping allows matching `MailHeaders` to **override MailMessage values**. Consequently, the actual recipient and subject may come from headers rather than the pre-mapping payload object.

### Risks

- Recipients get switched to another address unintentionally.
- Untrusted upstream headers alter From/To.
- Tests check only the payload while missing what the SMTP server actually receives.
- Two development teams disagree on which field takes precedence.

**Recommendation:** designate one source of truth for each field. If mail headers are used as overrides, generate them in a single validation/header-enrichment layer with clear authority.

## 12. Header Enrichment with a Business DTO

Suppose the initial data is:

~~~java
public record NotificationRequest(
    String recipientAddress,
    String subject,
    String body
) {}
~~~

A mapper can build the message:

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

`validateRecipient` is an application method you implement; the example does not provide its full implementation.

Process:

1. Validate data and sending permissions.
2. Render body by template/version.
3. Normalize recipients.
4. Set mail headers from a trusted source.
5. Convert payload to a handler-supported type.
6. Send over the channel.
7. Record the transport outcome.

A header enricher in Spring Integration can also use SpEL to compute header values from the payload. However, **enriching headers alone is not enough** if the payload remains a DTO that the outbound handler does not know how to render.

## 13. When Should You Use ObjectToStringTransformer?

Spring Integration documentation mentions `ObjectToStringTransformer` for payloads whose `toString()` is literally the exact email body to send.

However, for a business DTO:

~~~java
public record InvoiceEvent(
    String customerEmail,
    String invoiceId,
    long amount
) {}
~~~

`toString()` typically produces:

~~~text
InvoiceEvent[customerEmail=..., invoiceId=..., amount=...]
~~~

This is not the desired email and can leak internal fields. Instead of calling `toString()` indiscriminately, render:

~~~java
String plain = templateRenderer.renderPlain(invoiceEvent);
String html = templateRenderer.renderHtml(invoiceEvent);
~~~

Then convert into a `String` payload for plain-text mail, or construct MIME for emails with HTML/multipart.

## 14. Byte Array Payloads Mapped to Attachments

Spring Integration Mail supports mapping when the payload is `byte[]`: the data can be treated as an attachment. `MailHeaders.ATTACHMENT_FILENAME` is required for this mapping mode.

Example:

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
            "Report"
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

This is a metadata example for attachment payloads. Detailed behavior with content types/multipart depends on the handler/version. For multiple attachments or an HTML alternative, construct MIME explicitly.

### Why Does byte[] Require Caution?

- Holds the entire attachment in heap memory.
- Payloads crossing a message broker can become large.
- GC and serialization costs rise.
- Retries can copy byte arrays repeatedly.
- Cannot intuitively represent multiple files and complex metadata.

For large files, storing durable artifacts in object storage and passing immutable references through the outbox/message bus is more appropriate.

## 15. MimeMessage and MailMessage Are Not the Same

Spring's `SimpleMailMessage` implements `org.springframework.mail.MailMessage`. However, `jakarta.mail.internet.MimeMessage` is not a subtype of this interface.

Therefore, do not assume sending a `Message<MimeMessage>` into `MailSendingMessageHandler` will receive all header overrides under the same `MailMessage` logic or behave identically across all versions.

For multi-part MIME emails, the easiest approach to control is:

- Use `MailSendingMessageHandler` for payload types supported by your current Spring Integration version.
- Use a custom Spring Integration service activator calling `JavaMailSender` to build and send `MimeMessage` explicitly when content is complex.

Do not confuse Spring Integration `Message<?>` (a routing unit) with Jakarta Mail `MimeMessage` (an email format). Their relationship must be defined by an explicit transformer/adapter.

## 16. When Should You Build MimeMessage Manually?

Use `MimeMessageHelper` if the email needs:

- HTML alongside a plain-text alternative.
- `multipart/alternative` and `multipart/mixed`.
- PDF or CSV attachments.
- Inline images via CID.
- Unicode display names/subjects.
- Custom MIME headers.
- Explicit Reply-To.
- Attachment streaming.
- Content-ID and Content-Disposition.

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

Spring Integration can still handle routing, filtering, orchestration, and error handling; only MIME construction is handed to the specialized adapter.

## 17. Prepared Model for Complex Emails

Example:

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

These models are custom-designed DTOs, not built-in Spring Integration APIs.

Key points:

1. The DTO contains validated business data.
2. It does not hold SMTP username/password/OAuth tokens.
3. It does not hold a live `MimeMessage` in memory to serialize through a broker.
4. It does not hold an already-open `InputStream`.
5. Attachment references must be re-readable on retry.
6. Sender/recipient permissions must be checked before sending.
7. Content may require a template version and `expiresAt`.

## 18. Service Activator for Explicit MIME Sending

A custom handler receives `PreparedMail` from a channel:

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

Storage contract:

~~~java
public interface ArtifactStore {
    InputStreamSource openRepeatable(String key);
}
~~~

`InputStreamSource` must supply a fresh re-readable stream, never returning the same already-consumed stream. In production code, validate storage keys, limit attachment bytes, handle I/O errors, and classify SMTP failures.

This `send` method has a clear boundary: **the `PreparedMail` DTO is mapped into `MimeMessage` by explicit code**. Spring headers are not automatically copied to MIME, preventing internal metadata leaks.

## 19. Internal Headers Can Still Be Used for Routing

A `Message<PreparedMail>` may contain:

~~~text
notificationId = N-123
mailCategory   = TRANSACTIONAL
tenantId       = tenant-A
priority       = HIGH
providerId     = smtp-primary
traceId        = ...
~~~

These headers are useful to:

- Select the sender adapter.
- Apply provider quotas.
- Dispatch high-priority notifications.
- Correlate logs/spans.
- Check deadlines.
- Route to an error channel.
- Deduplicate business events.

However, do not put raw `tenantId`, trace baggage, or internal security metadata into MIME. If a custom correlation MIME header is required, use an allowlisted opaque ID and review privacy implications.

In a custom handler:

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

`richMailSender` is an application abstraction. A header may be null or an unexpected type, so real code must handle it safely before casting.

## 20. One Source of Truth for Each Mail Field

| Field | Authoritative Source | Why |
| --- | --- | --- |
| To | Recipient resolver/consent policy | Avoid sending to wrong recipient |
| Cc/Bcc | Business authorization | Avoid data leaks |
| From | Verified sender account config | Avoid sender spoofing |
| Reply-To | Support/ticket routing policy | Route replies properly |
| Subject | Template renderer/version | Consistent content |
| Plain/HTML | Content renderer | Proper escaping/charset |
| Attachments | Prepared artifact manifest | Repeatable bytes and security |
| Notification ID | Durable outbox | Correlation across retries |
| SMTP credentials | Secret manager | Keep out of messages |
| Provider/account | Infrastructure routing | Quota and authorization |

A message arriving from an API should not be allowed to set `MailHeaders.FROM` or `MailHeaders.BCC` without authorization. Otherwise, the outbound endpoint could be abused to send from unauthorized aliases or exfiltrate copies externally.

## 21. MIME Reply-To and From Are Two Different Things

Example:

~~~text
From: Notifications <notifications@example.com>
Reply-To: Support <support@example.com>
To: buyer@example.net
Subject: Order confirmation
~~~

`MailHeaders.FROM` and `MailHeaders.REPLY_TO` are separate; `MimeMessageHelper` also has separate setters.

Providers may require From to match the account/verified domain or require send-as permission. Successful AUTH does not imply every From address is permitted. Setting Reply-To only directs recipient replies; it **does not** automatically create an inbound mailbox reader.

## 22. Bcc and the SMTP Envelope

Bcc is not a required public header in the MIME delivered to recipients.

~~~text
Integration header:
  mail_bcc = ["audit@example.net"]

SMTP envelope:
  RCPT TO:<audit@example.net>

Delivered MIME:
  Bcc header normally does not appear
~~~

If a test only checks `getRecipients(BCC)` on the received message, it may not see Bcc and draw the wrong conclusion. When verifying hidden recipients, inspect the SMTP test server envelope or an appropriate mailbox capture.

Never copy `mail_bcc` into a custom header, as that exposes hidden recipients.

## 23. HTML Is Not Just a String Containing HTML Tags

Payload:

~~~text
<h1>Hello</h1>
~~~

if passed through simple text mapping, may be sent as plain text. Setting `contentType=text/html` at the Spring Messaging layer does not automatically build a full MIME HTML/alternative structure in every handler.

Build MIME explicitly:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("buyer@example.net");
helper.setSubject("Welcome");

helper.setText(
    "Hello, thank you for signing up.",
    "<html><body><h1>Hello</h1>"
        + "<p>Thank you for signing up.</p>"
        + "</body></html>"
);

sender.send(mime);
~~~

`setText(plain, html)` creates the alternative content. When attachments exist, the structure may be wrapped in multipart containers, so the top-level part is no longer `text/html`.

## 24. MIME Structure When Multiple Parts Exist

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

The exact structure depends on `MimeMessageHelper`'s multipart mode and implementation. Do not test by assuming MIME boundaries or raw part ordering always stay identical. Locate parts by type/disposition/Content-ID/filename.

This is why rich email requirements should not be forced into a simple set of String headers.

## 25. Inline Images Require Content-ID

~~~java
helper.setText(
    "<html><body>"
        + "<img src=\"cid:brandLogo\">"
        + "<p>Hello!</p>"
        + "</body></html>",
    true
);

helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
~~~

The inline attachment and HTML must reference the same ID. `ClassPathResource` suits resources packaged in the classpath/JAR. Do not rely on calling `getFile()` for classpath resources inside an executable JAR; an input stream may be required.

Set the HTML text before calling `addInline`, following `MimeMessageHelper` usage conventions.

## 26. Charset and Unicode in Mapping

Vietnamese subjects and bodies require valid encoding:

~~~text
Subject: Xác nhận thanh toán – Đơn hàng #123
Body: Xin chào, hóa đơn của bạn đã sẵn sàng.
~~~

`MimeMessageHelper(..., "UTF-8")` standardizes message construction. When reading back with Jakarta Mail:

~~~java
assertEquals(
    "Xác nhận thanh toán – Đơn hàng #123",
    received.getSubject()
);
~~~

`getSubject()` returns the decoded value. Raw MIME headers may contain encoded-words such as `=?UTF-8?...?=`, making them unsuitable for direct comparison with a Unicode String.

Merely having a Unicode String in Spring `MessageHeaders` does not mean MIME charset is configured properly. Encoding belongs to the MIME mapping step.

## 27. Attachment Names and Resource Lifecycle

An attachment has at least:

- Filename.
- Content-Type.
- Content-Disposition.
- Content transfer encoding.
- Actual byte data.
- Size/retention policy in the application.

With byte-array mapping, `MailHeaders.ATTACHMENT_FILENAME` specifies the filename. With a custom MIME builder, `helper.addAttachment(...)` takes the filename and resource.

Avoid:

~~~java
InputStream stream = storage.open(key);

InputStreamSource source = () -> stream;
~~~

This is a non-repeatable stream. If Jakarta Mail needs to read it a second time, the content may be empty or fail.

Better:

~~~java
InputStreamSource source = () -> storage.open(key);
~~~

Each `getInputStream()` call must return a fresh stream to the same immutable artifact. `ByteArrayResource` fits small files already in memory; for large files, persist durable artifacts and stream from storage.

## 28. Message-ID, Notification ID, and Trace ID

A notification may carry several IDs:

| ID | Role |
| --- | --- |
| Spring `MessageHeaders.ID` | Identifies the message at the integration layer |
| `notificationId` | Business/outbox identity of the logical email |
| MIME `Message-ID` | Email header |
| Provider queue/message ID | Supplied by SMTP/ESP if available |
| Trace ID/span ID | Execution observability |

They are not automatically equal. Never use Spring Message ID as an idempotency key across attempts if each retry builds a new message. `notificationId` should remain constant in a durable outbox.

A custom MIME header can carry an opaque ID:

~~~java
mime.setHeader(
    "X-App-Notification-ID",
    prepared.notificationId().toString()
);
~~~

Review privacy before adding it; providers might not preserve the header. A MIME `Message-ID` by itself does not guarantee SMTP deduplication.

## 29. Header Injection and Validation

A sender that pulls all mail headers from untrusted API input can suffer from:

- CRLF/header injection.
- Invalid addresses.
- Unauthorized From/send-as.
- Bcc exfiltration.
- Oversized subject/body.
- Header values carrying credentials or internal metadata.
- Mail relay abuse.
- Open redirects or unsafe URLs in HTML.

Use Spring/Jakarta Mail setter APIs rather than concatenating raw header strings, and validate against business policy. A header mapper only transforms data; it does not know which addresses a user is permitted to send under.

A policy should follow:

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

Do not use a generic "copy all headers" from an HTTP request to SMTP.

## 30. Inbound Mapping Is a Different Case

Spring Integration Mail provides inbound receivers such as `ImapMailReceiver` and `Pop3MailReceiver`. When receiving email, the adapter can place the raw `MimeMessage` as the payload.

When `DefaultMailHeaderMapper` is configured, certain MIME header fields are mapped into Spring Integration `MessageHeaders`.

MIME example:

~~~text
From: alice@example.net
To: support@example.com
Subject: Need order support
Content-Type: text/plain; charset=UTF-8

Hello, I need support.
~~~

Illustrative mapped message result:

~~~text
payload = "Hello, I need support."
headers:
  mail_from = "alice@example.net"
  mail_to = ["support@example.com"]
  mail_subject = "Need order support"
  mail_contentType = "text/plain; charset=UTF-8"
~~~

This is the text-mail case with a configured mapper; do not assume every inbound email becomes a `String`.

## 31. Which Fields Does DefaultMailHeaderMapper Map?

| Inbound Spring Header | Content |
| --- | --- |
| `mail_from` | From as a String |
| `mail_to` | To addresses as a String array |
| `mail_cc` | Cc addresses |
| `mail_bcc` | Bcc if present in original MIME |
| `mail_replyTo` | Reply-To |
| `mail_subject` | Subject |
| `mail_receivedDate` | Received date if available |
| `mail_size` | Size if available |
| `mail_lineCount` | Line count if available |
| `mail_expunged` | Message expunged flag |
| `mail_raw` | Original mail headers map |
| `mail_contentType` | Content type of the original email |
| `contentType` | Content type of the Spring payload after mapping |

Distinguishing `mail_contentType` from `contentType` is critical when MIME has multipart/attachments and the mapper converts the payload to bytes.

A missing inbound header does not prove the field always exists: not all emails or providers supply identical metadata.

## 32. Inbound Payloads Can Be String, byte[], or MimeMessage

Depending on receiver/mapping configuration:

- Without a header mapper: raw `MimeMessage` is typically the payload.
- With `text/*` and a mapper: payload may be `String`.
- With embedded `Part`/`Multipart`: payload may be rendered into `byte[]` to avoid serializing non-serializable Jakarta Mail parts.
- When `embeddedPartsAsBytes=false`, the receiver may deliver a `Multipart` object per configuration.
- With unfamiliar content types, payload may be `byte[]` with `contentType=application/octet-stream`.

Therefore, the following code is unsafe without checking types:

~~~java
String body = (String) message.getPayload();
~~~

A robust consumer must branch on type or use a MIME-aware transformer. Do not take a multipart `byte[]`, call `new String(bytes, UTF-8)`, and expect valid email text.

## 33. What Is MailToStringTransformer Used For?

`MailToStringTransformer` can convert inbound email content into a `String` according to Spring Integration's mechanism.

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

It is useful when the use case only needs text. However, it is not:

- A general-purpose HTML sanitizer.
- An antivirus scanner.
- A parser for every attachment.
- Proof of sender identity.
- A guarantee of business idempotency.

If images/attachments or nested MIME parts must be preserved, process raw `MIME`/`Part` with resource limits and build a normalized inbound DTO.

## 34. IMAP Folder Lifecycle and Lazy MimeMessage

Some IMAP messages fetch content lazily from the server. With Spring Integration receivers, `autoCloseFolder` and mapping configuration affect when the folder closes.

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

Some Spring Integration versions provide a closeable resource header when the folder is not closed automatically. Downstream code is responsible for closing the resource after reading.

Idea:

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

You need `java.io.Closeable` imports and the Spring Integration accessor matching your version. If the flow must pass inbound content through a broker, materialize/parse it into a bounded DTO of bytes/text before closing the folder rather than serializing a connection-dependent live `MimeMessage` or `Multipart`.

## 35. Do Not Forward Raw Inbound Headers to Outbound

Dangerous flow:

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

Senders can control From/Reply-To and sometimes other headers. If the application copies them as outbound headers, it can send mail under the wrong identity or leak data.

Safe approach:

1. Parse and validate the inbound email.
2. Determine ticket/business context from trusted data.
3. Build a fresh outbound DTO.
4. Select sender and recipients via application policy.
5. Copy only allowed content after sanitization/escaping.
6. Build fresh MIME or map mail headers from controlled sources.

The From header is sender-declared data, insufficient to authenticate a sensitive business request.

## 36. Mapping and SMTP Errors Are Two Different Layers

| Error | Stage | Appropriate Response |
| --- | --- | --- |
| Untransformed DTO payload | Mapping | Fix transformer/type contract |
| Missing `mail_to` | Validation/mapping | Validate recipient |
| Missing attachment filename | Attachment mapping | Set `MailHeaders.ATTACHMENT_FILENAME` |
| HTML renders as raw tags | MIME preparation | Build proper HTML part |
| Multipart cast to String | Inbound mapping | Type-aware MIME parsing |
| Unreadable attachment | Resource/MIME | Check storage/stream |
| Invalid SMTP AUTH | Transport | Fix credentials/mechanism |
| Temporary SMTP 421 | Transport | Appropriate retry/backoff |
| SMTP timeout after DATA | Ambiguous transport | Reconcile, guard against duplicates |
| Provider bounce | Downstream delivery | Handle provider events, do not blame mapping |

Do not infinitely retry the entire pipeline because of an unsupported DTO or permanently broken template. Classify preparation/mapping failures separately from SMTP submission failures.

## 37. Channels, Asynchrony, and Transaction Boundaries

With `DirectChannel`, the handler usually runs on the caller thread. With `ExecutorChannel` or broker-backed flows, messages can be processed asynchronously.

Consequences:

- `MessageChannel.send(...)` returning true does not prove SMTP sent the mail.
- Exceptions may route to an error channel/log instead of the caller.
- Trace/MDC context requires explicit propagation.
- Brokers can redeliver the same logical message.
- Retries can cause SMTP to submit multiple times.
- In-memory queues are not a durable source of truth.

For critical emails:

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

Do not hold a database transaction open across SMTP network calls. `JavaMailSender.send(...)` succeeding reports submission per transport contract, not that the recipient saw the email.

## 38. Retries and Idempotency Across Mapping

A notification should have a stable ID:

~~~text
notificationId=N-123
     |
     +--> attempt A1: timeout
     +--> attempt A2: transient rejection
     +--> attempt A3: accepted
~~~

Mapping should use the same prepared content/version across repeated attempts if business rules require unchanged content.

`MessageHeaders.ID` can change across messages/attempts; it is not a business idempotency key. Likewise, do not rely on MIME `Message-ID` to guarantee SMTP server deduplication.

When SMTP times out after DATA, the client cannot be sure whether the server accepted it; do not report `NOT_SENT` with certainty. Mark `AMBIGUOUS` per policy and consider reconciliation before retrying.

## 39. Unit Testing Mapping

A mapper test:

~~~java
@Test
void mapsDtoToMailTextAndHeaders() {
    NotificationRequest request = new NotificationRequest(
        "buyer@example.net",
        "Order confirmation",
        "Your order has been confirmed."
    );

    Message<String> mapped = mapper.mapToOutbound(request);

    assertEquals(
        "Your order has been confirmed.",
        mapped.getPayload()
    );

    assertArrayEquals(
        new String[] {"buyer@example.net"},
        (String[]) mapped.getHeaders().get(MailHeaders.TO)
    );

    assertEquals(
        "Order confirmation",
        mapped.getHeaders().get(MailHeaders.SUBJECT)
    );

    assertEquals(
        "notifications@example.com",
        mapped.getHeaders().get(MailHeaders.FROM)
    );
}
~~~

`mapper` is an application component, not a built-in API. This is a unit test of **data before the outbound handler**; it does not prove what an SMTP server receives.

Additionally, test header precedence: a `SimpleMailMessage` payload with subject/to A and Integration headers setting B, then observe the final message per the actual handler/version behavior.

## 40. SMTP Integration Test to Verify Final Mapping

Using GreenMail or an SMTP capture server:

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

Example assertions after the test server has started, the sender points to loopback, and the flow has been invoked:

~~~java
assertTrue(greenMail.waitForIncomingEmail(5000, 1));

MimeMessage[] captured = greenMail.getReceivedMessages();
assertEquals(1, captured.length);

MimeMessage received = captured[0];

assertEquals(
    "Order confirmation",
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
        "Your order has been confirmed."
    )
);
~~~

Read the **message on the SMTP test server side**, not just re-asserting initial Spring `MessageHeaders`. When testing rich MIME, traverse parts to locate plain/HTML and attachments; do not cast a top-level `Multipart` to `String`.

## 41. Testing Rich MIME/Attachments

With a custom `MimeMessage` sender, verify:

- From/To/Cc/Reply-To.
- Decoded Vietnamese Subject.
- Plain-text and HTML alternatives.
- Reasonable multipart structure.
- Inline image Content-ID matching HTML `cid:...`.
- Attachment filename, Content-Type, and byte contents.
- Bcc header not unintentionally leaked.
- Custom correlation ID is an opaque identifier.
- No unexpected duplicates sent.
- Retries use still-readable artifacts.

A helper to find a text part:

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

This is a test helper for relatively simple MIME; a production inbound parser also needs nesting depth limits, part counts, decoded byte limits, and nested `message/rfc822` handling.

## 42. Testing Inbound Header Mapping

If the application reads an Inbox:

1. Start test SMTP + IMAP servers.
2. Send an email with From, To, Subject, and MIME body/attachment.
3. Configure `ImapMailReceiver` and `DefaultMailHeaderMapper` as needed.
4. Read the emitted inbound Spring message.
5. Verify `mail_from`, `mail_subject`, and `mail_to`.
6. Verify the payload type is right for text or multipart.
7. Verify `mail_contentType` differs from `contentType` in the relevant cases.
8. Close the folder/closeable resource per receiver lifecycle.
9. Test malformed emails and content limits.
10. Do not use IMAP integration tests as proof of production deliverability.

Inbound mapping and outbound mapping are two separate contracts. Do not treat them as symmetric transforms and forward headers intact.

## 43. Monitoring and Correlation

Useful observations:

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

Track:

- Unsupported payload type/mapping failure count.
- Missing mail headers count.
- MIME preparation duration.
- Attachment load errors.
- SMTP submission duration and failure class.
- Queue age, retry rate, and provider throttling.
- Message size distribution.
- Outcomes `SUBMITTED`, `FAILED`, and `AMBIGUOUS`.

`notificationId` in structured logs links the stages. Do not use recipient email, subject, or attachment path as metric labels; they can expose PII and inflate cardinality.

## 44. Common Anti-Patterns

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| Treating Spring `Message<?>` as `MimeMessage` | Wrong boundary | Use explicit transformer/adapter |
| Copying all Spring headers into email | Leaks internal metadata | Allowlist MIME headers |
| Setting `contentType=text/html` expecting full HTML | Invalid MIME body | Build with `MimeMessageHelper` |
| Using DTO's `toString()` | Unreadable body, leaks fields | Render a template |
| Treating byte[] as a text body | Mapped as attachment | Choose the right payload |
| Forgetting filename on byte[] attachment | Handler lacks metadata | `MailHeaders.ATTACHMENT_FILENAME` |
| Different values for same field in payload and header | Unexpected overrides | Single source of truth |
| Letting upstream arbitrarily set From/Bcc | Data leak/open relay | Authorized sender resolver |
| Passing an already-opened InputStream | Attachment may be empty | Repeatable source |
| Serializing raw MimeMessage/Part into broker | Connection/serialization failure | Prepared DTO + refs |
| Forwarding raw inbound headers | Spoofing/wrong routing | Validate/remap |
| Writing Bcc into a custom public header | Exposes hidden recipients | Keep Bcc in the envelope |
| Treating channel.send as delivered | Wrong status | Separate submission/delivery |
| Relying on Message-ID for exactly-once | SMTP does not guarantee dedup | Business idempotency |
| Mocking sender and calling it an SMTP integration test | Fails to test transport/MIME | SMTP capture test |
| Ignoring IMAP folder lifecycle | Attachment read error/connection leak | Close resources properly |

## 45. Implementation Roadmap

1. **Identify the email type**: plain text, HTML, or complex MIME.
2. **Design the payload model** and define required headers.
3. **Select trusted data sources** for To, From, Reply-To, and Subject.
4. **Validate recipients and sender authorization** before mapping.
5. **Use MailSendingMessageHandler** for supported simple mappings.
6. **Use a transformer** when the initial payload is a business DTO.
7. **Use a custom MimeMessage builder** for HTML/attachments/inline images.
8. **Never copy raw headers** from requests/inbound messages to outgoing MIME.
9. **Persist durable notification IDs** and artifact references when retries are needed.
10. **Classify mapping failures** separately from SMTP transport errors.
11. **If handling inbound**, configure `DefaultMailHeaderMapper` deliberately.
12. **Handle inbound by payload type**, never casting arbitrarily.
13. **Keep IMAP resources alive while parsing lazy content**, then close properly.
14. **Test with SMTP capture** to verify actual MIME.
15. **Track metrics/logs** while keeping sensitive data out of telemetry.

## 46. Takeaways

- Spring Integration `Message<?>` differs from Jakarta Mail `MimeMessage`.
- Payload carries content; headers carry pipeline metadata.
- `MailSendingMessageHandler` uses `JavaMailSender` to perform outbound sending.
- Common `MailHeaders` include `TO`, `CC`, `BCC`, `FROM`, `REPLY_TO`, and `SUBJECT`.
- Header mapping can override values already present in Spring `MailMessage`.
- `String` payloads suit simple plain-text mail.
- `byte[]` payloads can be mapped as attachments and require a filename.
- Business DTOs need a transformer; do not rely on arbitrary `toString()`.
- HTML/alternatives/attachments/inline images require an explicit MIME builder.
- `MessageHeaders.CONTENT_TYPE` and `MailHeaders.CONTENT_TYPE` are not the same key.
- Not every Spring header will or should become a MIME header.
- Bcc must never leak via custom public headers.
- Unicode must be encoded properly at the MIME layer.
- Inbound `DefaultMailHeaderMapper`, when configured, maps MIME headers into Spring headers.
- Inbound payloads can be `MimeMessage`, `String`, bytes, or `Multipart` depending on settings.
- Never live-serialize a `MimeMessage`/`Part` tied to an IMAP connection.
- Correlation ID, Spring Message ID, MIME Message-ID, and provider queue ID are distinct IDs.
- SMTP accepted does not equal delivered or opened.
- Test final mapping by inspecting the MIME actually received by an SMTP test server.

**Core principle:** Treat a Spring Integration Message as an **internal orchestration unit**, and `MimeMessage` as the **external email format**. For plain text, you can map a `String` payload and supported `MailHeaders`. For HTML, multipart, and attachments, normalize data and build MIME explicitly via `JavaMailSender`/`MimeMessageHelper`. Only emit permitted fields into the email and keep internal metadata inside the application boundary.

## 47. References

- Spring Integration Mail Support: https://docs.spring.io/spring-integration/reference/mail.html
- Spring Integration MailHeaders API: https://docs.spring.io/spring-integration/api/org/springframework/integration/mail/MailHeaders.html
- Spring Framework Email Support: https://docs.spring.io/spring-framework/reference/integration/email.html

Cross-check APIs and options against the exact Spring Boot/Spring Integration version in use, especially when upgrading major versions.

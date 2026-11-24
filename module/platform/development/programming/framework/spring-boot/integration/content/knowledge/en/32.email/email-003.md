# SimpleMailMessage and MimeMessageHelper in Spring Boot

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot applications connect systems through HTTP clients, databases, caches, message brokers, and Spring Integration adapters. A common integration requirement is **sending notification emails**: order confirmations, reconciliation notices, reports, or operational alerts. Here, email is an external side effect much like an HTTP call or publishing a message; therefore, configuration, data contracts, transactions, failures, deduplication, testing, and observability must all be controlled.

Spring supports sending email via **`JavaMailSender`**, using Jakarta Mail to build messages and connect over SMTP. Two key tools:

- **`SimpleMailMessage`**: represents a **plain-text** email with sender, recipients, subject, and simple text body.
- **`MimeMessageHelper`**: helps construct a `MimeMessage` with **HTML, plain-text alternatives, CC/BCC, file attachments, multipart content, and inline images**.

This lesson belongs to the **Email** chapter and focuses directly on **`SimpleMailMessage` and `MimeMessageHelper`**. After this lesson, you can:

1. Configure `spring.mail.*` and inject a Spring Boot-managed `JavaMailSender`.
2. Send plain-text emails using `SimpleMailMessage`.
3. Build HTML emails, plain-text alternatives, attachments, and inline resources with `MimeMessageHelper`.
4. Distinguish **MIME composition** from **SMTP transmission** and understand what the send outcome means.
5. Build a safe email adapter: timeouts, TLS, validation, templates, retries, and idempotency.
6. Integrate email with SQL/outbox/message brokers without assuming distributed transactions.
7. Write unit/integration tests without sending real emails and monitor operational quality.

> **Important limitation:** `JavaMailSender.send(...)` completing without an exception generally means only that the SMTP server **accepted processing the message during that send session**. It does **not** guarantee the email reached the final mailbox, bypassed spam filters, or was read by the recipient.

## 1. Email-Sending Model in an Integration Flow

An order-notification flow may comprise these steps:

~~~mermaid
flowchart LR
    A["Order changes status"] --> B["Application service"]
    B --> C["SQL transaction"]
    C --> D["Order + notification outbox"]
    D --> E["Outbox relay / broker"]
    E --> F["Email worker"]
    F --> G{"Message"}
    G -->|"Plain text"| H["SimpleMailMessage"]
    G -->|"HTML/attachment"| I["MimeMessageHelper"]
    H --> J["JavaMailSender"]
    I --> J
    J --> K["SMTP relay"]
    K --> L["Mail provider / recipient"]
    F -.-> M["Logs + metrics + retry/DLQ"]
~~~

Each component owns a distinct responsibility:

| Component | Role | What It Does Not Provide |
| --- | --- | --- |
| `JavaMailSender` | Sends mail using SMTP settings | Final delivery, exactly-once |
| `SimpleMailMessage` | `text/plain` email payload | HTML, attachments, MIME multipart |
| `MimeMessage` | MIME-formatted message | Business policies and retries |
| `MimeMessageHelper` | Conveniently builds MIME, handles encoding and multipart | Template sanitization, antivirus |
| SMTP relay/provider | Accepts and forwards emails | Confirmation that the user read it |
| Email application adapter | Maps business data to an email | Durability without an outbox |
| Outbox/broker | Persists send intent and enables re-processing | Duplicate prevention without a business key |

**Why should email be an adapter?** Domain services should express intent like `sendOrderConfirmation(orderId)` rather than assembling HTML, SMTP headers, and MIME attachments directly. When you swap SMTP providers or redesign an email, business logic keeps its contract.

## 2. Installing the Dependency and Auto-Configuration

Spring Boot supports **MailSender auto-configuration** when matching mail libraries and settings like `spring.mail.host` are present. In a standard Gradle Groovy DSL project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The starter brings in Spring Mail and Jakarta Mail needed for SMTP sending. When conditions are satisfied and no custom `JavaMailSender` bean is declared by the application, Boot can auto-configure a `JavaMailSenderImpl` from `spring.mail.*`.

**You do not need to manually instantiate `JavaMailSenderImpl` for ordinary SMTP sending.** Declaring a custom bean can cause parts of the default configuration to back off; you then become responsible for host, port, credentials, session, timeouts, and lifecycle.

Key classes:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import jakarta.mail.internet.MimeMessage;
~~~

From Spring Framework 6 / Spring Boot 3 onward, mail APIs use **`jakarta.mail.*`** rather than `javax.mail.*` as in older examples. Do not mix both namespaces in the same project.

### 2.1. Which Bean Is Injected?

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class MailTransportProbe {

    private final JavaMailSender mailSender;

    public MailTransportProbe(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
~~~

If you encounter `No qualifying bean of type JavaMailSender`, first verify the starter, `spring.mail.host` (or supported JNDI mail session config), auto-configuration conditions, and whether the app defines another custom mail bean.

Spring `MailSender` is the simple email-sending interface, whereas `JavaMailSender` extends it for MIME/Jakarta Mail. Whenever attachments or HTML are needed, inject `JavaMailSender`.

## 3. Configuring spring.mail.*: Host, Port, TLS, and Timeouts

Example for a system whose SMTP relay supports **STARTTLS on port 587**:

~~~yaml
# application.yml
spring:
  mail:
    host: ${SMTP_HOST:smtp.example.org}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
      "[mail.debug]": false

notifications:
  mail:
    from: ${NOTIFICATION_FROM:no-reply@example.org}
~~~

`smtp.example.org` and `no-reply@example.org` are **illustrative addresses only**. In production, URLs, usernames, passwords, and sender addresses must come from operations/provisioning. Never place real passwords in source code or logs.

| Property | Role | Notes |
| --- | --- | --- |
| `spring.mail.host` | SMTP server | Relay DNS/hostname |
| `spring.mail.port` | SMTP port | Depends on STARTTLS vs implicit TLS |
| `spring.mail.username/password` | SMTP authentication | Load from secret manager/env |
| `spring.mail.default-encoding` | Default charset | UTF-8 for Vietnamese content |
| `mail.smtp.auth` | Require SMTP authentication | Depends on relay |
| `mail.smtp.starttls.enable` | Start plain SMTP then upgrade via STARTTLS | Not the same as implicit TLS |
| `mail.smtp.starttls.required` | Refuse sending if STARTTLS is unavailable | Useful when TLS is mandatory |
| `mail.smtp.connectiontimeout` | Socket connect timeout, in **milliseconds** | Belongs to Jakarta Mail provider |
| `mail.smtp.timeout` | SMTP response read timeout, milliseconds | Not an end-to-end deadline |
| `mail.smtp.writetimeout` | Socket write timeout, milliseconds | Not total job timeout |
| `mail.debug` | Detailed protocol logging | **Disable in production** if data exposure is a risk |

The `"[mail.smtp.auth]"` YAML syntax represents **an intact map key** inside `spring.mail.properties`. `mail.smtp.*` keys belong to the Jakarta Mail provider; exact names and units must be verified against the provider in use.

### 3.1. Port 587 STARTTLS vs Port 465 Implicit TLS

These two configurations are not arbitrarily interchangeable:

- **587/STARTTLS**: initiates an SMTP session and upgrades to TLS. Set `mail.smtp.starttls.enable=true` and `required=true` when the relay requires it.
- **465/implicit TLS (SMTPS)**: TLS begins immediately upon connecting. Configure SSL appropriately, usually `mail.smtp.ssl.enable=true`, alongside the matching port.

Never simply change `port: 587` to `465` while leaving all STARTTLS properties unchanged. Follow your SMTP provider's documentation and verify certificates and hostnames; never disable certificate validation to bypass TLS errors.

### 3.2. Why Are Timeouts Needed?

An email-sending task may execute inside an HTTP request, scheduled job, or broker consumer. Without finite transport timeouts, worker threads can stay pinned indefinitely if the SMTP relay drops connectivity.

Distinguish:

1. **Connection timeout**: waiting to establish the connection.
2. **Read timeout**: waiting for SMTP responses.
3. **Write timeout**: waiting to write the request/email.
4. **Application deadline**: total time for a business operation, covering queuing, template rendering, retries, and sending.
5. **Delivery latency**: time from SMTP acceptance to mailbox arrival (outside the scope of a single `send` call).

Do not set huge timeouts to mask an unresponsive relay. When sending batches, cap concurrency and retry counts to avoid exhausting thread pools.

### 3.3. Startup Connection Testing

Some Spring Boot setups support `spring.mail.test-connection=true` to probe the mail server at startup. This enables fail-fast detection when SMTP is unreachable, yet it can also prevent **the entire application from starting** solely due to a temporary notification-service outage.

For critical apps that must still serve other APIs when SMTP is down, verify SMTP via health indicators/monitoring and outbox retries rather than making mail connectivity a hard startup gate.

## 4. SimpleMailMessage: Plain-Text Emails

`SimpleMailMessage` is built for **plain-text** emails; it holds fields such as from, to, cc, bcc, replyTo, sentDate, subject, and text. It has no MIME multipart structure for files or HTML.

Service example:

~~~java
// PlainTextNotificationService.java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PlainTextNotificationService {

    private final JavaMailSender mailSender;

    public PlainTextNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderReceived(
            String recipient,
            String orderId) {

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.org");
        message.setTo(recipient);
        message.setSubject("Order receipt confirmation");
        message.setText(
                "We have received order " + orderId
                + ".\nYou will receive further updates once processing completes.");

        mailSender.send(message);
    }
}
~~~

Here the sender address is hardcoded **strictly for illustration**. In production, bind `notifications.mail.from` via `@ConfigurationProperties` and verify the address is permitted by the SMTP provider. `orderId` must originate from trusted business logic; never pass unvalidated user input directly into subjects or bodies.

**Key points to remember:**

- `setText(...)` produces `text/plain` content and **does not render HTML**.
- `setTo(...)` accepts multiple addresses; never reuse recipient lists across tenants.
- `setCc(...)` / `setBcc(...)` serve different recipient visibility roles.
- `setReplyTo(...)` sets the reply-to address, which differs from the SMTP envelope sender.
- `mailSender.send(message)` can throw `MailException` if preparation or sending fails.

### 4.1. Avoid Reusing a Mutable Message Across Sends

`SimpleMailMessage` is a **mutable** data bean. Never declare a singleton `SimpleMailMessage` and let threads concurrently mutate `to`/`subject` and send it—recipient A could receive content intended for B.

Instead, create **a fresh message object per send intent**. If you want to copy static defaults from a template instance, Spring provides a copy constructor, though you must still ensure addresses and content for each request are completely updated.

### 4.2. When to Choose SimpleMailMessage

Suitable for:

- Short internal alerts needing no formatting.
- Notification emails with few fields and no attachments.
- Plain-text notifications in simple workflows.
- Messages that must remain readable across nearly all mail clients, including constrained devices.

Unsuitable when HTML, inline images, multipart content, or attachments are required. Never pass `<b>Order</b>` into `SimpleMailMessage.setText(...)` expecting mail clients to render bold text.

## 5. MimeMessage and MimeMessageHelper: Rich Emails

`MimeMessage` is Jakarta Mail's MIME-structured email representation. It can contain multiple body parts and metadata. `MimeMessageHelper` simplifies constructing and formatting a `MimeMessage`.

Typical steps:

1. Call `JavaMailSender.createMimeMessage()`.
2. Instantiate `MimeMessageHelper` with the appropriate multipart mode and charset.
3. Set From/To/Subject, plain-text content, and HTML content.
4. Add attachments or inline resources as needed.
5. Call `JavaMailSender.send(mimeMessage)`.

Simple HTML example with a plain-text alternative:

~~~java
// RichNotificationService.java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RichNotificationService {

    private final JavaMailSender mailSender;

    public RichNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmed(
            String recipient,
            String orderId) throws MessagingException {

        MimeMessage mimeMessage = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                true,
                StandardCharsets.UTF_8.name());

        helper.setFrom("no-reply@example.org");
        helper.setTo(recipient);
        helper.setSubject("Order confirmed");

        String plainText =
                "Order " + orderId + " has been confirmed.";

        // Static HTML for illustration; dynamic values must be escaped
        // by a template engine with HTML injection protection.
        String htmlText =
                "<html><body><h2>Order confirmed</h2>"
                + "<p>Please check details in your account.</p>"
                + "</body></html>";

        helper.setText(plainText, htmlText);
        mailSender.send(mimeMessage);
    }
}
~~~

In this example, `plainText` includes the ID while `htmlText` stays static so unescaped values are not injected into HTML. A production template can render the ID inside HTML using standard HTML escaping.

**Note:** `MimeMessageHelper.setText(plainText, htmlText)` builds a **`multipart/alternative`** message so the mail client picks the best representation; it does not send two separate emails. Calling `setText(htmlText, true)` produces HTML content without a plain-text fallback.

### 5.1. When Do You Need Multipart?

Common constructors:

~~~java
// Email needing only plain text or HTML, no attachments:
new MimeMessageHelper(mimeMessage, "UTF-8");

// Multipart email, needing attachments / inline assets:
new MimeMessageHelper(mimeMessage, true, "UTF-8");

// Explicit multipart mode selection:
new MimeMessageHelper(
        mimeMessage,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

Passing `true` is a convenient constructor enabling multipart with the helper's default mode. When an email combines HTML, inline images, and attachments, `MULTIPART_MODE_MIXED_RELATED` creates the combined structure; mail clients vary slightly in interpretation, so test across your primary clients.

| Requirement | SimpleMailMessage | MimeMessageHelper |
| --- | --- | --- |
| Plain text | Yes | Yes |
| UTF-8, Vietnamese subjects | Yes via sender config | Yes via explicit charset |
| HTML | No | Yes |
| Plain text + HTML alternative | No | Yes |
| Attachments | No | Yes |
| Embedded image / cid inline | No | Yes |
| Custom MIME headers | Not intended | Yes via MimeMessage/Jakarta Mail |
| SMTP sending | `JavaMailSender.send(...)` | `JavaMailSender.send(...)` |

### 5.2. Charset and Vietnamese Subjects

Use `UTF-8` for HTML and plain text to prevent broken accents such as “Xác nhận đơn hàng”. If the application aggregates content from multiple systems, standardize Unicode normalization and template encodings. With `MimeMessageHelper`, set the charset explicitly or verify `spring.mail.default-encoding` is configured.

Never hand-encode MIME subjects or Base64 bodies via custom string concatenation; `MimeMessageHelper` and Jakarta Mail handle compliant encoding.

## 6. Sending Emails with Attachments

Example sending a PDF invoice generated in the business layer. Here `pdfBytes` contains **real PDF bytes** supplied by another service; this example does not generate the PDF itself.

~~~java
// InvoiceEmailService.java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceEmailService {

    private final JavaMailSender mailSender;

    public InvoiceEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("invoices@example.org");
        helper.setTo(recipient);
        helper.setSubject("Invoice " + invoiceNumber);
        helper.setText(
                "Your invoice has been issued.",
                "<p>Your invoice has been issued.</p>");

        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

Key points:

- `ByteArrayResource` lets Jakarta Mail re-read attachment bytes from memory while assembling MIME. It suits moderate files, **not very large files**.
- `addAttachment(filename, InputStreamSource, contentType)` accepts a display filename and data source. Choose the right content type so mail clients recognize it.
- Keep filenames safe: never blindly trust user-supplied filenames or embed real filesystem paths.
- Enforce size limits **before** MIME encoding: Base64/MIME encoding inflates email size beyond the raw bytes.
- Never attach reports, ID scans, or financial records without a clear purpose, authorization checks, and security policies.
- Consider malware scanning on user-uploaded attachments before sending and enforce an allowlist of permitted file types.

When reading attachments from files or streams, keep the source accessible **until the message is sent**. Single-read `InputStreamSource` implementations fail if JavaMail needs to read the stream more than once. `ByteArrayResource` and appropriate Spring resources handle repeated reads cleanly.

### 6.1. Do Not Load Huge Files into byte[]

For large reports, you can:

- Generate an expiring, authorized, audited download link instead of an attachment.
- Store the file in secure object storage and email a time-limited signed URL instead of the file.
- Use controlled file storage and `FileSystemResource` if size permits.
- Define quotas, size caps, and post-send cleanup.

Avoid using email as a transport for huge sensitive payloads when a better-controlled exchange channel exists.

## 7. Inline Images with Content-ID (cid)

HTML emails can reference inline images via `cid:...`:

~~~html
<html>
  <body>
    <h2>System notification</h2>
    <img src="cid:brand-logo" alt="Brand logo" width="120">
  </body>
</html>
~~~

In Java:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.setText(
        "System notification",
        "<h2>System notification</h2>"
            + "<img src=\"cid:brand-logo\" alt=\"Brand logo\">");

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png");
~~~

This snippet assumes `mail/brand-logo.png` actually exists on the classpath and `helper` is a `MimeMessageHelper` with multipart enabled. If the file is missing, handle resource errors cleanly in the application adapter.

**Recommended order:** call `setText(...)` before `addInline(...)`, because MIME part ordering affects how mail clients resolve inline resources. `addInline` attaches the Content-ID; the HTML references `cid:brand-logo` instead of arbitrary web URLs.

Inline images do not render identically across all mail clients. Many clients block images under security settings, so always include alt text and plain-text copy so the email remains understandable without images.

## 8. Designing Email Templates and Data Contracts

An order email may need to be sent in multiple languages. Never let a controller, Kafka consumer, or Quartz job build HTML via string concatenation.

A minimal input contract:

~~~java
// OrderConfirmationNotice.java
public record OrderConfirmationNotice(
        String notificationId,
        String orderId,
        String recipientEmail,
        String localeTag) {
}
~~~

Each field must follow explicit rules:

| Field | Responsibility | Notes |
| --- | --- | --- |
| `notificationId` | Notification idempotency/reconciliation key | Stable across retries and redeliveries |
| `orderId` | Business reference | Include in body only after authorization checks |
| `recipientEmail` | Permitted recipient address | Validated; never leak across tenants |
| `localeTag` | Selects language/template | Whitelist supported locales only |
| Template version | Approved content version | Keeps audit trail for replay when needed |
| Attachment reference | Attached resource (if any) | Enforces quotas, permissions, and expiration |

Isolate template rendering inside a dedicated service, such as a `MailTemplateRenderer` returning `RenderedMail(plainText, htmlText, subject)`. The SMTP adapter then concerns itself solely with rendered output and destination.

### 8.1. Preventing HTML Injection and Template Injection

Never interpolate user-supplied text into HTML via unescaped concatenation. For instance, a product name containing `<script>` or HTML tags can break email layout, expose content, or introduce interactive risks in weak mail clients/renderers.

Use a template engine with HTML escaping enabled by default or apply explicit context-aware escaping. Distinguish HTML text nodes, HTML attributes, and URLs—each context has different escaping/allowlist rules. Never let users edit raw template source or execute arbitrary template expressions.

**HTML emails are not trusted web pages.** Avoid scripts, embedded forms, or suspicious links; mail clients may also strip unsafe CSS/HTML.

### 8.2. Templates Should Include a Plain-Text Version

Even with polished HTML, many mail apps favor `text/plain` for accessibility or security. `helper.setText(plainText, htmlText)` supplies both versions, improving readability and compatibility.

A helpful email has a clear subject, a trustworthy sender, copy that avoids prompting users to open suspicious files, support/reply details, and an unsubscribe mechanism when classified as marketing mail under applicable regulations.

## 9. Exceptions and the True Meaning of Send Results

Spring Mail wraps sending/parsing/auth failures under the `MailException` hierarchy, for example:

- `MailAuthenticationException`: failed to authenticate with the SMTP provider.
- `MailSendException`: failure while sending one or more messages.
- `MailParseException` / `MailPreparationException`: failed to build a valid message.
- `MailException`: base type caught at boundaries when needed.

Additionally, when **building a MimeMessage** through `MimeMessageHelper`, a checked `MessagingException` may be thrown; this occurs **before** or during content preparation and should not be conflated with an SMTP outage.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(JavaMailSender sender, String recipient) {

    MimeMessage message = sender.createMimeMessage();

    try {
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.org");
        helper.setTo(recipient);
        helper.setSubject("Notification");
        helper.setText("Plain content", "<p>HTML content</p>");
    } catch (MessagingException exception) {
        throw new MailPreparationException(
                "Could not build a valid email", exception);
    }

    // MailException may be thrown while sending.
    sender.send(message);
}
~~~

Separating preparation from sending clarifies error categories:

| Error Category | Examples | Action |
| --- | --- | --- |
| Configuration/operations | Wrong SMTP host, TLS, password | Alert, fix config; no rapid infinite retries |
| Address/content contract | Invalid email address, broken template, missing attachment | Fix data/template; route to manual handling if needed |
| Transient | SMTP 4xx, network timeout, overloaded relay | Bounded retry with exponential backoff/jitter |
| Recipient policy error | Rejected address, invalid domain | Classify permanent vs temporary per provider |
| Uncertain send outcome | Connection lost after relay may have accepted | Retrying risks duplicates; reconcile/lock by business key |
| Post-SMTP-accept delivery failure | Bounced or caught by spam filter | Observe via webhooks/DSNs/provider API if available |

### 9.1. SMTP Send Success Does Not Mean the Email Arrived

A realistic timeline:

~~~mermaid
sequenceDiagram
    participant W as Email worker
    participant S as SMTP relay
    participant P as Provider/MTA
    participant R as Recipient mailbox
    W->>S: Send MIME message
    S-->>W: 250 accepted/queued
    Note over W: JavaMailSender.send can return normally
    S->>P: Forward later
    alt Accepted
        P->>R: Deliver
    else Bounce / reject
        P-->>S: Delivery failure
    end
~~~

Model business states such as **PENDING → SMTP_ACCEPTED → DELIVERED/BOUNCED** when the provider emits corresponding events. Never claim `DELIVERED` simply because `JavaMailSender.send(...)` did not throw.

Some SMTP relays do not expose final delivery tracking. If your problem domain requires legal or business proof of recipient delivery, pick a provider with event callbacks and store appropriate state history.

## 10. SQL Transactions, Outboxes, and Duplicate Sending

Sending email directly inside an order transaction is risky:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    mailSender.send(buildMessage(orderId));
}
~~~

Tricky failure scenario:

1. The SMTP relay accepts the email.
2. The SQL transaction later rolls back due to an error or deadlock.
3. The recipient receives a confirmation email for an uncommitted order.

Conversely, committing SQL first and calling mail outside the transaction means an SMTP failure can leave an order confirmed with no email sent. JDBC and SMTP do not share an ACID transaction by default.

### 10.1. Transactional Outbox

A more reliable architecture:

~~~mermaid
flowchart LR
    A["Order confirmed"] --> B["SQL transaction"]
    B --> C["Update orders"]
    B --> D["Insert notification_outbox"]
    D --> E["Worker / broker consumer"]
    E --> F["JavaMailSender"]
    F --> G["SMTP provider"]
    E -.-> H["Retry/Backoff/DLQ"]
    E -.-> I["Status + attempt_count"]
~~~

Illustrative outbox table:

~~~sql
CREATE TABLE notification_outbox (
    id UUID PRIMARY KEY,
    notification_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    recipient_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (notification_type, aggregate_id, recipient_hash)
);
~~~

The unique constraint here is only a **business-rule suggestion**: if a user can legitimately receive multiple notifications of the same type for one order, include a version/sequence or event ID in the key. Never apply that constraint blindly when valid resends are part of the contract.

Workflow:

1. Inside the SQL transaction, update order state and insert the outbox record.
2. Workers claim PENDING rows using proper atomic/locking mechanisms.
3. Render the email and call SMTP with finite timeouts.
4. When SMTP accepts, record `SMTP_ACCEPTED` with timestamp/attempt metadata.
5. On transient errors, increment attempt count and set `next_attempt_at`.
6. On permanent errors or exhausted retries, transition to manual handling or dead-letter.
7. When delivery webhooks arrive, update `DELIVERED`/`BOUNCED` using authenticated, idempotent handlers.

### 10.2. Is Exactly-Once Email Realistic?

With SMTP, if connectivity drops after sending and before the app persists success, the worker **cannot tell whether the relay received it**. Retrying may produce a second email. Thus end-to-end exactly-once cannot be guaranteed solely with `JavaMailSender` and a DB unique constraint.

Distinguish:

- **At-least-once attempt:** retries to minimize missed notifications, accepting duplicate risk.
- **At-most-once attempt:** avoids duplicates at the risk of dropping notices during indeterminate errors.
- **Exactly-once business intent:** persists a single notification intent in the outbox, though SMTP transmission may still repeat.
- **Provider idempotency:** using an API with idempotency keys strengthens guarantees; plain SMTP has no equivalent idempotency contract.

Do not substitute `Message-ID` or `traceId` for atomic deduplication. Choose a strategy based on notification criticality; for example, an order confirmation may tolerate occasional duplicates, whereas an email carrying an activation code or action link must strictly govern token validity.

## 11. Asynchronous Sending and Load Limits

Do not let HTTP controllers wait on SMTP when sending is not part of the response contract and can take seconds. Options:

| Sending Mode | Pros | Risks |
| --- | --- | --- |
| Synchronous in HTTP request | Simple, immediate SMTP feedback | High latency, timeouts, tight coupling |
| `@Async`/executor | Faster HTTP responses | If purely in-memory, tasks lost on crash |
| Spring Integration mail adapter or flow | Separates sources, channels, and processing | In-memory channels are not durable by default |
| Broker + email consumer | Buffering and retry/redelivery | Consumers need idempotency, DLQ, visibility |
| SQL transactional outbox + worker | Send intent commits atomically with business state | Requires claiming, retries, monitoring |

Regardless of approach, enforce limits on:

- SMTP-sending thread pool / concurrency.
- Emails per minute matching provider quotas.
- Body/attachment sizes and recipient counts.
- Retry attempts and total retry duration.
- Recovery rate after an outage to prevent an email "thundering herd."
- Per-tenant quotas and delegated sending rights.

An in-memory queue does not preserve messages across restarts; if the business requires reliable delivery, use a durable broker or SQL outbox.

### 11.1. Do Not Create Multiple JavaMailSenders Just to Send in Parallel

A single `JavaMailSender` configured in the Spring context can be used concurrently by many requests; **each send must instantiate its own `MimeMessage`/`SimpleMailMessage`**. Never share a mutable `MimeMessage` across threads.

SMTP providers enforce their own quotas and connection limits. Enlarging thread pools does not help when the provider throttles throughput—it can trigger 429/rate-limit errors or account locks.

## 12. Email Security and Personal Data

Email carries sensitive data across multiple servers. Therefore:

- **Credentials:** store `SMTP_PASSWORD` and API keys in a secret manager; never write them to logs, full stack traces, or repositories.
- **TLS:** require appropriate encrypted sessions and verify certificates/hostnames.
- **From identity:** use provider-verified addresses; configure SPF, DKIM, and DMARC per domain and mail operations.
- **Recipients:** validate formats and authorization; avoid exposing recipients in CC when BCC or separate emails are required.
- **Attachments:** restrict file types/sizes, scan for malware, and verify access; avoid system paths or secrets in filenames.
- **HTML:** escape dynamic data, constrain template syntax, and protect against phishing links.
- **Logs/traces:** avoid logging raw email addresses unnecessarily; use hashing/redaction or access-controlled audit stores.
- **Access control:** never expose an API sending arbitrary content to arbitrary user-supplied addresses without abuse controls, quotas, and authorization.
- **Unsubscribe/consent:** marketing emails carry legal and provider-policy opt-in/opt-out obligations; never conflate them with transactional emails.

SMTP is not end-to-end confidential by default. STARTTLS protects hops that support it, yet does not ensure only the final recipient can read the contents. When transmitting highly sensitive data, send a **non-sensitive notice** linking into an authenticated portal instead.

## 13. Testing SimpleMailMessage Without Sending Real Mail

To verify message construction logic, mock `JavaMailSender` and capture the sent object:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class PlainTextNotificationServiceTest {

    @Test
    void sendsPlainTextConfirmation() {
        JavaMailSender sender = mock(JavaMailSender.class);
        PlainTextNotificationService service =
                new PlainTextNotificationService(sender);

        service.sendOrderReceived(
                "customer@example.org", "ORD-42");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals(
                "customer@example.org",
                sent.getTo()[0]);
        assertEquals(
                "Order receipt confirmation",
                sent.getSubject());
    }
}
~~~

This test opens no network sockets. It checks `to` and `subject`, and can be expanded to assert `from`, text, CC/BCC, and that **each invocation allocates a distinct message object**. Mockito is included in the standard Spring Boot test starter; configure appropriate test dependencies.

### 13.1. Testing MimeMessageHelper Without Real SMTP

`JavaMailSender.createMimeMessage()` normally builds a `MimeMessage` backed by a Jakarta Mail `Session`. In unit tests, return an in-memory `MimeMessage` and inspect it after sending:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class RichNotificationServiceTest {

    @Test
    void createsMimeMessageWithRecipientAndSubject()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage mimeMessage =
                new MimeMessage(Session.getInstance(
                        new Properties()));

        when(sender.createMimeMessage()).thenReturn(mimeMessage);

        RichNotificationService service =
                new RichNotificationService(sender);

        service.sendOrderConfirmed(
                "customer@example.org", "ORD-42");

        verify(sender).send(mimeMessage);

        assertEquals(
                "customer@example.org",
                ((InternetAddress)
                        mimeMessage.getRecipients(
                                jakarta.mail.Message.RecipientType.TO)[0])
                        .getAddress());
        assertEquals(
                "Order confirmed",
                mimeMessage.getSubject());
    }
}
~~~

You can extend MIME parsing to inspect `multipart/alternative`, `text/html`, and attachment content types/filenames/bytes. Still, this test **does not verify SMTP authentication, TLS, wire encoding, quotas, or delivery events**.

### 13.2. Integration Testing with a Fake SMTP Server

Use **GreenMail, Wiser/SubEthaSMTP, or an SMTP capture server** running in the test context on a dedicated port without relaying mail to the Internet.

Workflow:

1. Start the SMTP test server on a dynamic/dedicated port.
2. Point `spring.mail.host` and `spring.mail.port` to the test server.
3. Call the service to send plain text and MIME messages.
4. Retrieve received messages from the server and parse subject, recipients, body parts, and attachments.
5. Simulate 4xx/5xx responses, timeouts, or authentication failures to test retry and error classification.
6. Stop the server after tests to avoid resource leaks or accidentally falling back to production SMTP.

When testing against a real provider, use a sandbox/test account with explicit authorization; never send automated test emails to real users.

### 13.3. Contract Tests to Include

| Scenario | What to Verify |
| --- | --- |
| Plain text | Correct from/to/subject/text, UTF-8 |
| HTML alternative | Both `text/plain` and `text/html` present |
| Attachments | Correct filename/content-type/bytes, within quota |
| Inline images | Content-ID matches `cid:`, resource exists |
| Malformed email | Rejected with clear cause, not sent |
| SMTP timeout | Bounded retry or outbox state transition |
| SMTP auth failure | No tight retry loop; alert raised |
| Broker redelivery | No duplicate notification intent created |
| SQL rollback | Outbox/email intent does not commit if order rolls back |
| SMTP accepted then worker crashes | On replay, duplicate risk handled per policy |
| Multi-tenant | No cross-tenant content or recipient leakage |
| Bounce/delivery webhook | Authenticated and idempotent state update |

## 14. Observing the Mail-Sending Flow

An email-sending application should measure **behavior at each boundary**:

| Metric or Event | Meaning |
| --- | --- |
| Notification intent created | Business logic decided an email must be sent |
| Outbox pending / oldest age | Backlog size and dwell time |
| SMTP send attempts | Every send attempt |
| SMTP accepted count | Times relay confirmed acceptance |
| SMTP errors by class | Auth/TLS/network/timeout/recipient |
| Retry and dead-letter count | Whether recovery flows are functioning |
| Delivery/bounce count (if available) | Downstream results after SMTP acceptance |
| End-to-end notification latency | From send intent to SMTP accept/delivery per contract |

With Micrometer Observation, you can instrument a synchronous SMTP call:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public void sendObserved(
        JavaMailSender sender,
        ObservationRegistry registry,
        SimpleMailMessage message) {

    Observation.createNotStarted(
                    "integration.email.smtp.send", registry)
            .lowCardinalityKeyValue(
                    "template", "order-confirmation")
            .lowCardinalityKeyValue(
                    "transport", "smtp")
            .observe(() -> sender.send(message));
}
~~~

This observation measures **the duration of the `send` call**, not delivery time to the mailbox. When sending fails, `observe(...)` records the exception through configured handlers. If delivery callbacks exist, instrument them separately.

Suitable tags include bounded values like `template`, `transport`, and `outcome`. **Never put recipient emails, message IDs, `orderId`, or `notificationId` into metric labels**; they have unbounded cardinality and/or expose personal data. Store such identifiers in access-controlled audit logs for per-event reconciliation.

### 14.1. Monitoring Deliverability and Credential Maintenance

Beyond application metrics, monitor:

- Bounce rates, complaint rates, and sender domain reputation when supported by the provider.
- Quotas, rate limits, and SMTP account suspension/lock events.
- Certificate expiration dates, endpoint changes, and credential rotation schedules.
- SPF/DKIM/DMARC alignment per operational configuration.
- Average message sizes and attachment counts.
- Outbox backlog growth during provider outages.

A service reporting `health=UP` does not prove emails are being delivered. If a health indicator probes SMTP and the provider suffers an outage, decide whether that should fail **readiness for the entire application** or only notification health, avoiding unnecessary cascading failures.

## 15. Common Errors and How to Handle Them

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Cannot inject `JavaMailSender` | Missing starter/host config or excluded auto-config | Dependencies and `spring.mail.*` |
| SMTP auth failed | Wrong username/password or auth policy | Secrets, account, TLS; never log passwords |
| Production timeouts | Missing connect/read/write timeouts or SMTP outage | Configure finite timeouts and inspect network/provider |
| Port 465 fails to connect | Using STARTTLS when provider requires implicit TLS | Configure `mail.smtp.ssl.enable` for port 465 |
| Garbled Vietnamese accents | Non-UTF-8 charset | `spring.mail.default-encoding` and MimeMessageHelper charset |
| Raw HTML tags shown | Used `SimpleMailMessage` or `setText` without HTML flag | Use `MimeMessageHelper` and HTML alternative |
| Missing images in email | Wrong CID, `addInline` before `setText`, or client blocks images | Inspect MIME structure, resource, and alt text |
| Empty or broken attachment | Single-read stream or deleted file before send | Use repeatable resource and manage lifecycle |
| Email too large | Attachments exceed SMTP provider cap | Enforce quota or send secure download link |
| `send()` succeeds but mail not received | Relay only accepted; later bounced/spam/blocked | Check delivery events and provider logs |
| Duplicate emails on retry | No outbox/idempotency or indeterminate SMTP outcome | Unique send intent, bounded retries, reconciliation |
| Email sent despite SQL rollback | SMTP called inside uncommitted transaction | Transactional outbox / post-commit scheduling |
| HTTP API slow due to mail | Sent synchronously on request thread | Outbox + async worker/broker |
| No metrics | Transport/worker uninstrumented or missing registry | Observation/Actuator and dashboards |
| Recipient list leaked | Used CC instead of individual sends or BCC | Review privacy and recipient policy |

## 16. Pre-Deployment Checklist

- [ ] `spring.mail.host/port/username/password` configured via secure sources.
- [ ] Correct STARTTLS vs implicit TLS mode chosen, with certificate/hostname verified.
- [ ] Connect/read/write timeouts and concurrency/quota limits configured.
- [ ] `SimpleMailMessage` chosen for plain text, `MimeMessageHelper` for HTML/multipart/attachments.
- [ ] UTF-8 used and plain-text alternative provided for HTML emails.
- [ ] Template engine escapes dynamic inputs; no untrusted HTML injected.
- [ ] Attachments enforce size, type, authorization, and resource lifecycle limits.
- [ ] Sender/recipient addresses validated; no cross-tenant recipient leakage.
- [ ] Never call SMTP inside an SQL transaction expecting shared rollback.
- [ ] For durable delivery, notification outbox, worker, retry/DLQ, and idempotency policy are in place.
- [ ] SMTP acceptance distinguished from delivered/bounced/read.
- [ ] Unit tests cover plain-text/MIME and integration tests use an SMTP capture server.
- [ ] Metrics track attempts/accepts/deliveries, backlog, and failures without email/ID tags.
- [ ] Procedures exist for secret rotation, reputation/bounce monitoring, and provider outage recovery.

**Key takeaway:** `SimpleMailMessage` fits simple plain-text notices; `MimeMessageHelper` builds MIME emails with HTML, text alternatives, attachments, and inline resources. Both send via `JavaMailSender`. Reliable email delivery depends not only on the message-building API, but also on **SMTP configuration, security, transaction boundaries, outbox/idempotency, retries, testing, and delivery observability**.

## References

- [Spring Boot — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html): auto-configuration, `spring.mail.*`, `JavaMailSender`, and timeouts.
- [Spring Framework — Email](https://docs.spring.io/spring-framework/reference/integration/email.html): `SimpleMailMessage`, `MimeMessageHelper`, HTML/attachments.
- [Spring Framework API — SimpleMailMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mail/SimpleMailMessage.html): fields and plain-text capabilities.
- [Spring Framework API — MimeMessageHelper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mail/javamail/MimeMessageHelper.html): constructors, multipart modes, `setText`, `addAttachment`, `addInline`.
- [Spring Framework API — JavaMailSender](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mail/javamail/JavaMailSender.html): sending `SimpleMailMessage`/`MimeMessage`.
- [Jakarta Mail — SMTP Transport](https://eclipse-ee4j.github.io/angus-mail/docs/SMTP-Transport.html): SMTP transport properties, TLS, and timeouts.

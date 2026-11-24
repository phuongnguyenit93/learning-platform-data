# Building a MailService with a Clear Contract

In a Spring application, many business flows may need to send email: registration confirmation, order notifications, password resets, invoices, or reports. If every controller and service injects `JavaMailSender` directly and builds `MimeMessage` on its own, SMTP configuration, error handling, and recipient rules end up duplicated across many places.

A **MailService** centralizes mail-sending operations and provides a **clear contract** for callers. This contract must answer:

- What data does the application need to supply to request a send?
- Who is responsible for choosing the From address and SMTP configuration?
- How are text/HTML contents represented?
- When the method returns normally, what is guaranteed?
- When sending fails, how does the service report the error?
- Does the service send synchronously or merely accept a job into a queue?
- Who is responsible for validation, retries, logging, and status tracking?

A good design lets the business layer simply say **"send this notification to this recipient"**, while keeping Spring Mail, Jakarta Mail, and SMTP details inside the implementation.

## 1. Where does MailService sit in the application?

A common layout:

~~~text
Controller / Event handler / Scheduler
                 |
                 v
       Application service
                 |
                 v
             MailService
          (application port)
                 |
                 v
        SmtpMailService
       (infrastructure adapter)
                 |
                 v
          JavaMailSender
                 |
                 v
           SMTP server
~~~

The components have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| **Controller / event handler** | Receives requests or events and calls the appropriate use case |
| **Application service** | Determines when to send, selects business data and recipients |
| **MailService contract** | Defines the input data, behavior, and errors callers can rely on |
| **SmtpMailService** | Converts the request into a MIME message and calls Spring Mail |
| **JavaMailSender** | Sends the message over the configured transport |
| **SMTP provider** | Accepts the message, applies sending policies, and relays it onward |

MailService should not query the entire database itself to guess content, nor should the controller know the SMTP host, password, or how MIME parts are constructed. The business layer prepares the data to send; the adapter is responsible for turning that data into an email.

### 1.1. Why not call JavaMailSender directly everywhere?

If multiple classes call it directly:

~~~java
@Service
class OrderService {
    private final JavaMailSender mailSender;
    // Build MimeMessage and configure From/Subject/Body manually.
}

@Service
class AccountService {
    private final JavaMailSender mailSender;
    // Duplicate email creation and sending logic.
}

@RestController
class SupportController {
    private final JavaMailSender mailSender;
    // Send mail directly from the controller again.
}
~~~

Issues quickly appear:

- Different places set different From or Reply-To addresses.
- Some places send HTML while others send text without a fallback.
- Charset, timeout, or attachment configurations become inconsistent.
- SMTP errors are caught and handled in different ways.
- Unit tests have to mock infrastructure APIs across multiple layers.
- When switching from SMTP to an HTTP API email provider, many business classes must be updated.

A centralized MailService creates a single point to enforce shared policies and change how sending works without forcing every caller to know transport details.

## 2. A clear contract must describe behavior, not just a method name

An interface with only:

~~~java
public interface MailService {
    void send();
}
~~~

is not yet a useful contract. Callers do not know whom to send to, what content to send, how errors are represented, or when the operation is considered complete.

The contract should describe at least four areas:

1. **Input:** recipient, subject, body, content type, and required metadata.
2. **Policy:** From address, encoding, recipient limits, HTML and attachment handling.
3. **Completion:** whether the method sends synchronously or accepts an asynchronous job.
4. **Failure:** validation errors, MIME preparation, SMTP authentication, connection issues, or provider rejection.

Example of a synchronous contract:

~~~java
public interface MailService {
    /**
     * Sends an email through the configured transport.
     *
     * When the method returns normally, the sender has completed
     * message submission according to the transport contract.
     * This does not confirm that the message reached the Inbox or was read.
     *
     * Throws MailServiceException if the message cannot be prepared or sent.
     */
    void send(OutgoingMail mail);
}
~~~

Callers can rely on this rule to decide whether to record status, surface errors, or perform retries according to policy.

## 3. Choosing an API for MailService

There are multiple levels of abstraction. No single signature fits every application; what matters is that the API expresses actual needs and does not leak infrastructure details.

### 3.1. Specialized business API

If the application has a few fixed email types, you can define methods per use case:

~~~java
public interface OrderMailService {
    void sendOrderConfirmation(OrderConfirmationMailData data);
    void sendShippingUpdate(ShippingUpdateMailData data);
}
~~~

Advantages:

- Callers cannot arbitrarily send any subject/body.
- Method names express business intent.
- Each email type has its own data model.
- Easy to bind templates, locales, and recipient rules to each use case.

The drawback is that the interface can grow rapidly when the application has many email types. Specialized methods can also share a generic sending component underneath.

### 3.2. Generic mail-sending API

A module that needs to send many message types can use:

~~~java
public interface MailService {
    void send(OutgoingMail mail);
}
~~~

`OutgoingMail` is a command with a specific contract. It is not an arbitrary HTML string, nor does it contain a `MimeMessage` object. Callers supply application-level data; the implementation is responsible for creating the message.

Advantages:

- One implementation can serve many use cases.
- Logic for setting recipients, subject, body, and encoding can be reused.
- Easy to swap the SMTP adapter for a provider adapter if semantics are preserved.

The risk is that a generic API can become a "send any content" gateway without validation and caller control. Therefore, do not expose a public endpoint accepting a raw `OutgoingMail` from external users without policy checks.

### 3.3. Combining both layers

In larger applications, a combined approach is often clearer:

~~~text
OrderNotificationService
        |
        | OrderConfirmationMailData
        v
MailTemplateRenderer
        |
        | plain text + HTML
        v
MailService (generic application port)
        |
        v
SmtpMailService
        |
        v
JavaMailSender
~~~

The specialized use case decides **when to send and what data is allowed to be sent**. The generic MailService simply receives a prepared email. This preserves business semantics while avoiding duplicated MIME/SMTP code.

## 4. Designing an immutable input model

A mail-sending request should be structured data rather than a long parameter list:

~~~java
public record MailBody(
        String plainText,
        String html) {
}

public record OutgoingMail(
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String replyTo,
        String subject,
        MailBody body,
        String correlationId) {
}
~~~

This example only shows the shape. A real contract should validate data upon object creation.

### 4.1. MailBody: specifying supported content clearly

A transactional email should normally have plain text and may have HTML:

~~~java
import java.util.Objects;

public record MailBody(
        String plainText,
        String html) {

    public MailBody {
        if (plainText == null || plainText.isBlank()) {
            throw new IllegalArgumentException(
                    "plainText must not be blank");
        }

        if (html != null && html.isBlank()) {
            html = null;
        }
    }

    public boolean hasHtml() {
        return html != null;
    }
}
~~~

This contract enforces the rule: **plain text is always required**, and HTML is optional. If HTML is present, the adapter sends two alternatives; otherwise, the adapter sends simple plain text. This ensures every email has a readable fallback.

If the product has a valid case for sending HTML only, you can relax this rule, but document the behavior when plain text is missing. Do not let an implementation auto-generate text by stripping HTML tags in an uncontrolled way and call that a good fallback.

### 4.2. OutgoingMail: recipients and metadata

~~~java
import java.util.List;
import java.util.Objects;

public record OutgoingMail(
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String replyTo,
        String subject,
        MailBody body,
        String correlationId) {

    public OutgoingMail {
        to = immutableAddresses(to, "to");
        cc = immutableAddresses(cc, "cc");
        bcc = immutableAddresses(bcc, "bcc");

        if (to.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one To recipient is required");
        }

        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "subject must not be blank");
        }
        rejectHeaderBreaks(subject, "subject");

        if (replyTo != null) {
            requireNonBlank(replyTo, "replyTo");
            rejectHeaderBreaks(replyTo, "replyTo");
        }

        Objects.requireNonNull(body, "body");
    }

    private static List<String> immutableAddresses(
            List<String> addresses,
            String fieldName) {
        Objects.requireNonNull(addresses, fieldName);
        List<String> copy = List.copyOf(addresses);
        copy.forEach(address -> {
            requireNonBlank(address, fieldName + " address");
            rejectHeaderBreaks(address, fieldName + " address");
        });
        return copy;
    }

    private static void requireNonBlank(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }

    private static void rejectHeaderBreaks(String value, String name) {
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    name + " must not contain CR/LF");
        }
    }
}
~~~

Decisions in this example:

- `to` is required and must contain at least one address.
- `cc` and `bcc` can be empty lists.
- `replyTo` is optional.
- `subject` is required and must not contain CR/LF to prevent header injection.
- `body` must exist and follow the plain-text fallback rule.
- `List.copyOf` creates a snapshot preventing list mutation after the command is created.
- `correlationId` helps link logs/tracing with business context; it is not a secret or proof of idempotency.

These checks are only **basic validation**. They do not prove that the mailbox exists, that the recipient is authorized to receive the content, or that the domain is allowed to send. Those rules belong to the business layer and mail policy.

### 4.3. Why not put From in the request?

For a typical application, the `From` address is a system policy:

~~~yaml
app:
  mail:
    from: no-reply@example.com
    reply-to: support@example.com
~~~

If every caller can freely choose `From`, an endpoint could be abused to send emails impersonating someone else. It is better for the adapter to read From from controlled configuration. If there are multiple valid sender identities, use an allowlisted enum/value object or policy rather than accepting arbitrary addresses from public requests.

### 4.4. Why not put JavaMailSender or MimeMessage in the contract?

Avoid:

~~~java
public interface MailService {
    void send(MimeMessage message);
}
~~~

or:

~~~java
public interface MailService {
    JavaMailSender sender();
}
~~~

These signatures couple callers to Jakarta Mail/Spring Mail. When changing providers or content packaging, the business layer must also change. The contract should express **the intent to send an email**, not internal library objects.

## 5. Implementing MailService with JavaMailSender

Once the contract and model exist, the SMTP adapter converts the request into a `MimeMessage`.

### 5.1. Interface

~~~java
public interface MailService {
    void send(OutgoingMail mail);
}
~~~

### 5.2. Implementation

~~~java
package com.example.mail.infrastructure;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SmtpMailService implements MailService {
    private final JavaMailSender sender;
    private final String fromAddress;
    private final String defaultReplyTo;

    public SmtpMailService(
            JavaMailSender sender,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.mail.reply-to:}") String defaultReplyTo) {
        this.sender = sender;
        this.fromAddress = fromAddress;
        this.defaultReplyTo = defaultReplyTo;
    }

    @Override
    public void send(OutgoingMail mail) {
        MimeMessage mime = sender.createMimeMessage();

        try {
            boolean multipart = mail.body().hasHtml();
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime,
                    multipart,
                    StandardCharsets.UTF_8.name()
            );

            helper.setFrom(fromAddress);
            helper.setTo(mail.to().toArray(String[]::new));

            if (!mail.cc().isEmpty()) {
                helper.setCc(mail.cc().toArray(String[]::new));
            }
            if (!mail.bcc().isEmpty()) {
                helper.setBcc(mail.bcc().toArray(String[]::new));
            }

            String replyTo = mail.replyTo() != null
                    ? mail.replyTo()
                    : defaultReplyTo;
            if (replyTo != null && !replyTo.isBlank()) {
                helper.setReplyTo(replyTo);
            }

            helper.setSubject(mail.subject());

            if (mail.body().hasHtml()) {
                helper.setText(
                        mail.body().plainText(),
                        mail.body().html()
                );
            } else {
                helper.setText(mail.body().plainText());
            }
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not prepare MIME message",
                    mail.correlationId(),
                    ex
            );
        }

        try {
            sender.send(mime);
        } catch (MailException ex) {
            throw new MailSubmissionException(
                    "Mail transport could not submit the message",
                    mail.correlationId(),
                    ex
            );
        }
    }
}
~~~

In this code:

1. `JavaMailSender` is injected via constructor; it is an infrastructure dependency.
2. `From` comes from configuration, not arbitrarily from the caller.
3. `To`, `Cc`, `Bcc`, and `Reply-To` are set from the validated request.
4. `MimeMessageHelper` builds plain text or multipart alternative.
5. UTF-8 charset handles Vietnamese content.
6. MIME preparation errors and transport send errors are converted into MailService exception types.

`MimeMessageHelper` methods can throw `MessagingException`, so the preparation block is handled separately. `JavaMailSender.send(...)` can throw Spring's `MailException`; this error is classified as a submission error.

This is an example for **Spring Boot 3.x / Spring Framework 6**, using the `jakarta.mail` namespace. Applications on older Spring generations must use the API/package matching their running version.

### 5.3. Naming exceptions meaningfully

You can define an exception hierarchy:

~~~java
public abstract class MailServiceException extends RuntimeException {
    private final String correlationId;

    protected MailServiceException(
            String message,
            String correlationId,
            Throwable cause) {
        super(message, cause);
        this.correlationId = correlationId;
    }

    public String correlationId() {
        return correlationId;
    }
}
~~~

Message preparation error:

~~~java
public final class MailPreparationException
        extends MailServiceException {

    public MailPreparationException(
            String message,
            String correlationId,
            Throwable cause) {
        super(message, correlationId, cause);
    }
}
~~~

Mail submission error:

~~~java
public final class MailSubmissionException
        extends MailServiceException {

    public MailSubmissionException(
            String message,
            String correlationId,
            Throwable cause) {
        super(message, correlationId, cause);
    }
}
~~~

In a Java project, each public class in this example should live in its own file. You can add validation or provider-specific error types if callers genuinely need to distinguish them; there is no need to create an exception class for every minor cause.

## 6. Success contract: what does "sent" mean?

One of the most important parts of the contract is defining **success**.

With a synchronous interface:

~~~java
mailService.send(mail);
~~~

if the method returns normally, it usually means:

- the application built the message;
- Spring Mail completed the transport call;
- the transport did not report a synchronous error during submission.

It does **not** prove:

- the email reached the Inbox;
- the message avoided spam or quarantine;
- the mailbox still exists;
- the recipient opened or read the message;
- attachments were downloaded.

The SMTP server can accept the message and then continue processing, relaying, or returning a bounce later. If the product needs delivery tracking, a separate provider event, DSN, or webhook mechanism is required.

### 6.1. Do not name the state DELIVERED too early

If the service only calls `JavaMailSender`, reasonable states might be:

| State | Meaning |
| --- | --- |
| `CREATED` | Send request was created in the application layer |
| `SUBMITTING` | Send attempt is in progress |
| `SUBMITTED` | Transport completed submission without error |
| `SUBMISSION_FAILED` | Submission attempt reported an error |
| `DELIVERED` | Provider confirmed delivery per provider event/contract |
| `BOUNCED` | Provider reported the message bounced |

Do not use `DELIVERED` just because `send(...)` did not throw an exception. Accurate state naming prevents dashboards, retries, and customer support from drawing wrong conclusions.

### 6.2. What if you need the message ID?

`JavaMailSender.send(...)` returns `void`. Some providers have their own message IDs or status lookup APIs, but you cannot assume every SMTP server returns a uniform ID through the Spring Mail interface.

If the business needs tracking, you can:

- attach the application's correlation ID to logs/jobs;
- configure a listener or provider-specific integration to retrieve the ID when supported;
- store a mapping between the application job ID and the provider message ID;
- receive webhooks/DSNs to update post-submission status.

Do not generate a UUID yourself and call it an SMTP message ID. An application-generated ID can aid tracing, but it differs from the ID issued by the transport/provider.

## 7. Error and retry contract

Callers need to know which errors are reported and who decides on retries. A good interface must not swallow exceptions:

~~~java
public void send(OutgoingMail mail) {
    try {
        sender.send(mime);
    } catch (MailException ex) {
        log.warn("Mail submission failed", ex);
        // Do not return normally if the send attempt failed.
        throw new MailSubmissionException(
                "Mail submission failed",
                mail.correlationId(),
                ex
        );
    }
}
~~~

This illustrates the idea; a real implementation should avoid logging the same exception twice if an upper layer also logs it. What matters is **never catching an error, logging only, and continuing as if it succeeded**.

### 7.1. Classifying errors

| Error group | Examples | Handling approach |
| --- | --- | --- |
| Invalid input | Missing To, blank Subject, header containing CR/LF | Reject request; fix data, do not retry as-is |
| MIME preparation | Part creation error, unreadable resource | Check content/resource; retry only if root cause may change |
| Authentication | Wrong or expired credentials | Fix secret/provider permissions; continuous retries will not help |
| Transient connection | Timeout, server temporarily unavailable | Can retry with backoff and limit |
| Provider policy | Disallowed sender/domain or rejected content | Fix policy or data; do not retry indefinitely |
| Unknown outcome | Connection lost after transmitting data but before final response | Account for risk that the message was received and retries may duplicate |

Not every `MailException` is retryable. Inspect the specific exception, root cause, job state, and provider contract.

### 7.2. Who is responsible for retries?

For direct synchronous sending, the caller can decide to display an error or switch to another workflow. For critical transactional emails, retries should be managed by a **job processor/queue** rather than looping send calls directly inside an HTTP request.

One way to layer it:

~~~text
OrderService
    |
    v
MailJobPublisher
    |
    v
Queue / Outbox
    |
    v
MailWorker
    |
    v
MailService.send(...)
    |
    v
SMTP transport
~~~

The worker decides:

- marking the job successful after the transport finishes;
- scheduling transient errors for retry with backoff;
- moving permanent errors to a terminal state or dead-letter queue;
- recording attempt count and cause;
- retaining attachments/artifacts if retries still need them.

MailService can still keep a synchronous contract inside the worker. This clarifies the difference between **sending an email** and **accepting an email-sending job**.

## 8. Distinguishing send() from enqueue()

A common design mistake is having a method named `send(...)` that actually just pushes a message into a queue and returns. Callers think the email has been submitted to SMTP, when only a job was persisted.

If there is a queue, use a distinct contract:

~~~java
public interface MailJobPublisher {
    MailJobId enqueue(OutgoingMail mail);
}
~~~

Example ID:

~~~java
public record MailJobId(String value) {
}
~~~

Two distinct behaviors:

| Method | When returning normally | Possible errors |
| --- | --- | --- |
| `MailService.send(mail)` | Transport call completed per sender contract | MIME preparation, SMTP, provider |
| `MailJobPublisher.enqueue(mail)` | Job accepted by queue/outbox per storage contract | Queue unavailable, DB failure, validation |

A successful `enqueue` does not mean the email was sent. The job may sit waiting, be retried, be canceled, or ultimately fail. The API and states must reflect this difference.

### 8.1. Why not just add @Async to send()?

For example:

~~~java
@Async
public void send(OutgoingMail mail) {
    sender.send(...);
}
~~~

The caller returns as soon as the task is handed to the executor (if dispatch succeeds), without knowing whether the transport has completed. If the method returns `void`, errors raised on the asynchronous thread also cannot be caught by the caller in the normal way.

`@Async` can be useful for background tasks, but the contract should express it explicitly:

~~~java
@Async
public CompletableFuture<MailSubmissionResult> sendAsync(
        OutgoingMail mail) {
    // ...
}
~~~

Even a future only reports the outcome of an in-process task; it does not replace a durable queue, retries after restart, or delivery webhooks. For transactional emails, a job/outbox is usually easier to control than an in-memory executor.

## 9. Separating template rendering from mail sending

MailService does not need to know how to build HTML from order data. You can extract a renderer:

~~~java
public interface MailContentRenderer {
    MailBody renderOrderConfirmation(
            OrderConfirmationMailData data,
            Locale locale);
}
~~~

Application service:

~~~java
public class OrderNotificationService {
    private final MailContentRenderer renderer;
    private final MailService mailService;

    public OrderNotificationService(
            MailContentRenderer renderer,
            MailService mailService) {
        this.renderer = renderer;
        this.mailService = mailService;
    }

    public void notifyOrderConfirmed(Order order, Customer customer) {
        OrderConfirmationMailData data =
                OrderConfirmationMailData.from(order, customer);

        MailBody body = renderer.renderOrderConfirmation(
                data,
                Locale.forLanguageTag("vi-VN")
        );

        OutgoingMail mail = new OutgoingMail(
                List.of(customer.email()),
                List.of(),
                List.of(),
                null,
                "Order confirmation " + order.publicReference(),
                body,
                "order-confirmed-" + order.id()
        );

        mailService.send(mail);
    }
}
~~~

This is an example of responsibility flow:

- Order service knows which order was just confirmed.
- The mapper creates selected email data.
- The renderer creates plain text and HTML.
- MailService sends the rendered content.

The `Order`, `Customer`, and `OrderConfirmationMailData` types are illustrative business models. Do not let the renderer query repositories itself or decide which customer receives the email.

### 9.1. Using one MailService interface for both plain and HTML

Because `MailBody` already represents both content forms, MailService does not need separate methods such as:

~~~java
sendPlainText(...);
sendHtml(...);
sendPlainAndHtml(...);
~~~

unless each type has different business behavior. A body model with required plain text and optional HTML can cleanly express all three cases:

| Body | Result |
| --- | --- |
| Plain text only | Sends text/plain |
| Plain text + HTML | Sends multipart/alternative |
| Plain text + blank/null HTML | Sends plain text per normalization rule |

Avoid using a boolean like `isHtml` alongside a generic body string if it makes it hard for callers to tell how content is interpreted. A clearly named data type is easier to read and extend.

## 10. SMTP configuration belongs to infrastructure

A MailService contract should not require callers to pass host, port, username, or password on every send. Those values belong to environment configuration.

Example `application.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
    reply-to: ${MAIL_REPLY_TO:support@example.com}
~~~

Spring Boot can auto-configure `JavaMailSender` when the mail starter and appropriate mail properties are present. `app.mail.from` and `app.mail.reply-to` are application-defined properties; the implementation reads them to enforce policy.

### 10.1. Do not put secrets in models or logs

Do not design:

~~~java
new OutgoingMail(
        smtpUsername,
        smtpPassword,
        smtpHost,
        ...
);
~~~

Credentials are managed by the runtime environment or a secret manager. Callers supply only message data. This allows rotating secrets without updating every call site or queued payload.

Do not log:

- SMTP passwords, OAuth tokens, or API keys;
- entire bodies containing personal data;
- full recipient lists unless needed for tracing;
- attachment bytes or file contents.

You may log the correlation ID, email type, status, and sanitized error code.

### 10.2. Multiple sender identities

If the application has multiple From addresses, such as billing and support, do not let callers pass arbitrary addresses:

~~~java
public enum MailSenderProfile {
    GENERAL,
    BILLING,
    SUPPORT
}
~~~

A policy maps profiles to configured addresses:

~~~java
public interface MailSenderIdentityResolver {
    String resolve(MailSenderProfile profile);
}
~~~

The caller chooses the profile per use case; the adapter only uses allowlisted addresses. Verify that these addresses/domains are authorized by the SMTP provider.

## 11. Validation at the right layer

Validation should be divided by meaning:

| Check | Appropriate layer | Example |
| --- | --- | --- |
| Order exists and is confirmed | Domain/application | Do not send confirmation mail for invalid orders |
| User is authorized to receive notification | Application/security policy | Do not let clients send to arbitrary addresses |
| At least one To recipient exists | Model/contract | `OutgoingMail` constructor |
| Subject does not contain CR/LF | Model/contract | Block header injection |
| Address has valid syntax | Boundary/adapter or value object | Parse address before building MIME |
| From belongs to an allowed sender identity | Configuration/policy | Prevent spoofing arbitrary addresses |
| Link uses an allowed host | Application/renderer | Do not accept arbitrary external URLs |
| SMTP credentials are valid | Infrastructure/runtime | Secret manager and provider |

Do not lump everything into one giant method. For instance, checking whether a user is allowed to receive an invoice is a business rule; checking whether the MIME helper can construct a header is an infrastructure detail.

### 11.1. Syntax-checking an email address does not verify the mailbox exists

A syntactically valid string does not prove:

- the domain accepts email;
- the mailbox exists;
- the user controls the mailbox;
- the destination server will accept the message.

You can use a proper parser for syntax checks, but confirming an account address usually requires a verification flow. Do not call a simple regex "email verification", and do not send probe emails to test every address before business rules allow it.

### 11.2. Preventing MailService abuse

If MailService is invoked from an API, you need to:

- authenticate the caller;
- check that recipients relate to the account/transaction;
- rate-limit requests;
- cap recipient count and content size;
- control From/Reply-To;
- avoid letting users supply raw HTML or headers;
- apply appropriate anti-spam and audit policies.

A generic MailService is very useful inside the application, but it must not turn into an open relay via a REST API.

## 12. Testing MailService

A clear contract allows unit tests without a live SMTP connection. You can mock `JavaMailSender` and verify that the adapter constructs the right MIME message.

### 12.1. Testing request validation

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OutgoingMailTest {
    @Test
    void rejectsMailWithoutToRecipient() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OutgoingMail(
                        List.of(),
                        List.of(),
                        List.of(),
                        null,
                        "Subject",
                        new MailBody("Body", null),
                        "correlation-1"
                )
        );
    }

    @Test
    void rejectsLineBreakInSubject() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OutgoingMail(
                        List.of("alice@example.net"),
                        List.of(),
                        List.of(),
                        null,
                        "Hello\r\nBcc: victim@example.net",
                        new MailBody("Body", null),
                        "correlation-2"
                )
        );
    }
}
~~~

These tests verify input rules at the model level; no Spring context or SMTP is required.

### 12.2. Testing the adapter with a mocked JavaMailSender

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.internet.MimeMessage;
import jakarta.mail.Session;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class SmtpMailServiceTest {
    @Test
    void createsMessageWithExpectedHeaders() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties()));
        when(sender.createMimeMessage()).thenReturn(mime);

        MailService service =
                new SmtpMailService(sender, "no-reply@example.com", "");

        OutgoingMail request = new OutgoingMail(
                List.of("alice@example.net"),
                List.of("team@example.com"),
                List.of(),
                null,
                "Notification A123",
                new MailBody("Order confirmed.", null),
                "order-A123"
        );

        service.send(request);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());

        MimeMessage sent = captor.getValue();
        assertEquals("Notification A123", sent.getSubject());
        assertEquals(
                "alice@example.net",
                sent.getRecipients(
                        jakarta.mail.Message.RecipientType.TO)[0].toString()
        );
        assertEquals(
                "team@example.com",
                sent.getRecipients(
                        jakarta.mail.Message.RecipientType.CC)[0].toString()
        );
    }
}
~~~

This is an illustrative example. The `SmtpMailService` constructor and imports must match the project's implementation; the test can use a helper to parse addresses if exact comparison is needed. Because the sender is mocked, this test verifies that the message is built and passed to the sender, not that SMTP actually accepts the mail.

### 12.3. Testing submission failures

~~~java
doThrow(new MailSendException("SMTP unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));

assertThrows(
        MailSubmissionException.class,
        () -> service.send(request)
);
~~~

This test confirms that the adapter does not swallow errors and that the caller sees the exception defined by the application contract.

### 12.4. Integration testing with a fake SMTP server

To test real connections and MIME output, you can use Mailpit or GreenMail in a test environment:

1. Start the SMTP test server.
2. Configure the application to point to the test host/port.
3. Call MailService with a sample request.
4. Verify the test server receives the message.
5. Inspect From, To, Cc, Subject, charset, plain text, HTML, and attachments.
6. Test errors when the server stops or credentials are wrong.

Never use production SMTP in unit tests; tests should never send real emails to customers.

## 13. Logging, tracing, and observability

A MailService used across many places needs traceability without exposing content.

Useful log fields:

~~~text
event=mail_submission
correlationId=order-confirmed-A123
mailType=ORDER_CONFIRMATION
transport=smtp
result=SUBMITTED
durationMs=342
~~~

On failure:

~~~text
event=mail_submission
correlationId=order-confirmed-A123
result=FAILED
exceptionType=MailSendException
retryableCandidate=true
~~~

`retryableCandidate` should only be a preliminary classification based on exception/root cause, not a guarantee that every error in that group will be retried.

### 13.1. Do not implicitly use correlation ID as an idempotency key

A correlation ID links logs belonging to the same business flow. It does not by itself prevent sending two emails. To prevent duplicate jobs, you need:

- a stable event/job ID;
- a unique constraint or idempotency store if required;
- durably persisted processing state;
- retry rules and unknown-outcome handling.

If an order event is emitted twice, a generic MailService cannot know on its own that it is the same notification unless the contract carries a business key and the orchestration layer performs deduplication.

### 13.2. Metrics to monitor

| Metric | Meaning |
| --- | --- |
| `mail_send_attempts_total` | Number of send attempts |
| `mail_submission_success_total` | Number of transport completions without error |
| `mail_submission_failures_total` | Number of send errors |
| `mail_submission_duration_seconds` | Duration of the send operation |
| `mail_queue_depth` | Number of queued jobs if a queue exists |
| `mail_retry_total` | Number of retries |
| `mail_bounce_total` | Number of bounces received from the provider if integrated |

Do not use email addresses, subjects, or individual correlation IDs as metric labels because cardinality can grow unbounded. Metrics should be labeled by mail type, provider, or outcome at a controlled granularity.

## 14. Reference package structure

A small module can be organized as:

~~~text
com.example.mail
  application/
    MailService.java
    OutgoingMail.java
    MailBody.java
    MailServiceException.java
    MailPreparationException.java
    MailSubmissionException.java
  infrastructure/
    SmtpMailService.java
    MailConfiguration.java
  template/
    MailContentRenderer.java
    ThymeleafMailContentRenderer.java
  notification/
    OrderNotificationService.java
    OrderConfirmationMailData.java
~~~

Package names may differ depending on architecture. What to preserve:

- Contracts and models sit where callers can depend on them without knowing the SMTP implementation.
- The Spring Mail adapter resides in infrastructure.
- The template renderer builds the body and does not send via SMTP.
- The business use case decides when and to whom to send.

For a small application, there is no need to create excessive packages/interfaces. You can start with a concrete service and extract a contract when multiple callers exist, independent testing is needed, or the transport might change.

## 15. Anti-patterns to avoid

| Anti-pattern | Problem | Better design |
| --- | --- | --- |
| Controller calls `JavaMailSender` directly | HTTP layer depends on mail infrastructure | Controller calls application use case |
| `MailService.send(to, subject, body)` with long parameter lists | Hard to extend and easy to mix up order | Use a request model with named fields |
| Passing `MimeMessage` through a business interface | Leaks Jakarta Mail/Spring Mail | Use application-level models |
| Letting callers set arbitrary From | Allows sender spoofing | From from config or sender profile allowlist |
| Catching `MailException` and only logging | Caller thinks sending succeeded | Throw exception per contract |
| Calling `send` when it actually only enqueues | Unclear completion semantics | Use a separate `enqueue` method |
| Using `@Async void` without observing errors | Caller does not know task outcome | Future or durable job contract |
| MailService querying entities arbitrarily | Mixes business logic and infrastructure | Caller prepares data |
| Passing entire entities to templates | Exposes fields, lazy loading | Dedicated DTO/model for email |
| Sharing a mutable message object across threads | Race conditions, wrong recipient/body | Immutable request and fresh message each time |
| Retrying every error | Repeats credential/policy errors, may duplicate | Classify errors and use bounded backoff |
| Naming send status DELIVERED | Confuses SMTP submission with Inbox delivery | Use SUBMITTED; base delivery on provider events |
| Logging full body/recipients | Leaks personal data | Log ID, mail type, and minimal status |

## 16. Extending the contract with attachments

If MailService needs to support file attachments, do not rush to add a `List<File>` to the request holding arbitrary local paths. You must define:

- display filename;
- content type;
- source of bytes/resource;
- size limits;
- resource ownership and lifecycle;
- cleanup handling after success or failure;
- how artifacts are retained when a job needs retries.

Example simple model for attachment bytes:

~~~java
public record MailAttachment(
        String fileName,
        String contentType,
        byte[] content) {

    public MailAttachment {
        Objects.requireNonNull(fileName, "fileName");
        Objects.requireNonNull(contentType, "contentType");
        Objects.requireNonNull(content, "content");
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
~~~

Defensive copying prevents callers from mutating bytes after the request is created. However, this keeps the entire file on the heap; for large files or asynchronous sending, use artifact storage with clear keys/versions and access permissions.

Do not hold an open `InputStream` inside a request model across a queue or serialize it to JSON. A stream has a lifecycle and read state; it is not an immutable payload suited for queued work.

## 17. When should you split into multiple interfaces?

One generic service may suffice for a small module. As requirements grow, you can split:

~~~java
public interface MailService {
    void send(OutgoingMail mail);
}

public interface MailJobPublisher {
    MailJobId enqueue(OutgoingMail mail);
}

public interface MailContentRenderer {
    MailBody render(
            String templateId,
            Object model,
            Locale locale);
}
~~~

However, do not create an interface just so every class has one method without a meaningful boundary. A good criterion is **which capability does the caller need to depend on?**

- Caller sending immediately: depends on `MailService`.
- Caller creating a background job only: depends on `MailJobPublisher`.
- Use case building content: depends on `MailContentRenderer`.
- Worker sending jobs: depends on `MailService` and an artifact provider if needed.

Splitting interfaces enables independent testing and adapter replacement; too many layers without clear contracts only obscure the call flow.

## 18. End-to-end scenario: sending an order confirmation

Suppose an order is confirmed. The business layer has the data:

~~~text
orderNumber = A123
customerEmail = alice@example.net
customerName = Nguyen An
total = 220000 VND
~~~

Synchronous flow:

1. `OrderService` completes order confirmation rules.
2. `OrderNotificationService` builds the content model containing only the data to send.
3. `MailContentRenderer` produces plain text and HTML from the model.
4. `OutgoingMail` packages To, Subject, Body, and correlation ID.
5. `MailService.send(...)` is called.
6. `SmtpMailService` builds the MIME message and uses `JavaMailSender`.
7. If the method returns normally, the application layer records **SUBMITTED** per the contract; if an exception occurs, it classifies the error.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant N as OrderNotificationService
    participant R as MailContentRenderer
    participant M as MailService
    participant S as JavaMailSender
    participant P as SMTP provider

    O->>N: orderConfirmed(order)
    N->>R: render(model, locale)
    R-->>N: plainText + html
    N->>M: send(OutgoingMail)
    M->>S: create MimeMessage
    M->>S: send(message)
    S->>P: SMTP submission
    P-->>S: response
    S-->>M: return / MailException
    M-->>N: normal return / MailServiceException
~~~

If the product does not want the HTTP request to wait on SMTP, the use case can write an outbox/job record and return **ACCEPTED_FOR_PROCESSING** along with a job ID. A worker executes the same synchronous send contract in a later step. Do not use the same word "sent" for two different milestones.

## 19. Contract checklist before implementation

Before writing the implementation, specify clearly:

| Question | Decision needed |
| --- | --- |
| What does the caller pass? | Request model with recipients, subject, body, and metadata |
| What format does the body have? | Plain text required, HTML optional, or another rule |
| Who chooses From? | Configuration or sender identity policy |
| Are To/Cc/Bcc/Reply-To supported? | Clear rules and recipient count limits |
| Is the method synchronous or asynchronous? | `send` completes transport or `enqueue` accepts a job |
| What does success mean? | Submission completed, not assumed delivery |
| How are errors reported? | Validation, preparation, submission, and retry policy |
| Who decides retries? | Caller/job processor; do not blindly retry all exceptions |
| Who builds the content? | Renderer receiving a prepared model |
| Who owns attachments? | Clear resource lifecycle and cleanup |
| What is logged? | Correlation ID, mail type, result; avoid PII/secrets |
| Where is it tested? | Model, mocked adapter, and SMTP integration tests |

## 20. Key things to remember

- **MailService is an application contract**, not a place for every caller to access SMTP directly.
- Use a request model with clearly named fields instead of a method with many hard-to-read parameters.
- Keep requests immutable to avoid changing recipients/body after handing off to another thread or queue.
- From and SMTP details should be controlled by configuration/policy.
- Separate the renderer/template from sending for independent testing and maintenance.
- For HTML emails, include a plain-text alternative and use MIME properly.
- A synchronous `send` method only indicates the transport completed submission; it does not confirm Inbox delivery.
- If it only enqueues, name it accordingly and return a job ID so callers know the work was only accepted.
- Do not swallow exceptions; classify errors and let the appropriate layer decide retries.
- Do not log secrets or full email bodies.

A good MailService does not need dozens of methods. It needs a **contract clear enough that callers know what to provide, what to expect, and how to handle failures**. When the contract is separated from the Spring Mail implementation, the application can change SMTP providers, template rendering approaches, or background job execution without forcing all business logic to change with it.

### References

- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender`, and `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** mail starter, `JavaMailSender` auto-configuration, and `spring.mail.*`.
- **Jakarta Mail API:** `MimeMessage`, `Message`, `Multipart`, and mail exceptions.
- **Spring Framework — Task Execution and Scheduling:** executors and `@Async`.
- **Java API — Records, `List.copyOf`, and immutable value types:** designing stable request models.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP submission operations and server responses.
- **RFC 2045–2049 — MIME:** plain text, HTML, multipart, and attachments.

# SimpleMailMessage for Text-Only Emails

In **Spring Framework Mail**, `SimpleMailMessage` is the class that lets an application describe a **plain-text** email using familiar properties such as sender, recipients, subject, and body. When you only need to send simple notifications like "Account created", "Order is being processed", or "Report completed", this is usually the most approachable entry point to Spring's mail API.

Short example:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("customer@example.net");
message.setSubject("Registration successful");
message.setText("Hello! Your account has been created.");

mailSender.send(message);
~~~

The snippet has two components with distinct roles:

- **`SimpleMailMessage`:** an object holding **the information of a single email**; by itself it opens no network connection and does not send anything.
- **`MailSender` or `JavaMailSender`:** the component that performs the send operation using the application's configured mail transport.

This lesson walks from the object structure of `SimpleMailMessage` to a practical Spring Boot example, how address fields work, the limitations of plain text, and how to handle common scenarios.

## 1. Where Does SimpleMailMessage Fit in Spring Mail?

`SimpleMailMessage` belongs to the package:

~~~java
import org.springframework.mail.SimpleMailMessage;
~~~

Two key interfaces:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.javamail.JavaMailSender;
~~~

The usage relationship is typically described as follows:

~~~text
Application / NotificationService
    |
    | build message data
    v
SimpleMailMessage
    |
    | pass to send(...)
    v
MailSender (interface)
    ^
    |
JavaMailSender (interface, extends MailSender)
    ^
    |
JavaMailSenderImpl (common SMTP implementation)
    |
    v
SMTP server / email provider
~~~

**`MailSender`** provides the methods to send `SimpleMailMessage`. **`JavaMailSender`** extends that interface and adds `MimeMessage` support for complex content. Therefore, if a service only sends plain text, depending on `MailSender` is enough at the API level; if the same service also needs to create MIME emails, use `JavaMailSender`.

In a Spring Boot application using the mail starter and suitable configuration, the sender bean is typically auto-configured for injection into services. In plain Spring Framework or custom setups, you must provide the appropriate implementation.

### 1.1. Message Data and the Send Action Are Two Responsibilities

Consider two lines:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
mailSender.send(message);
~~~

The first line **merely instantiates an object in memory**. At that moment, no SMTP connection exists. The second line asks the sender to execute the sending process. Separating these two responsibilities makes content construction easy to test and allows changing transport configuration without rewriting header, recipient, and body assembly code.

`SimpleMailMessage` is a **mutable** object; setters modify the state of that object itself. Therefore, you should normally create **a new instance for each email to be sent** rather than reusing the same object across multiple requests or threads.

## 2. Properties Supported by SimpleMailMessage

A plain-text email can include the following fields:

| Property | Typical API | Meaning |
| --- | --- | --- |
| Sender display address | `setFrom(String from)` | Address shown in the `From` field |
| Reply destination | `setReplyTo(String replyTo)` | Suggested address when the recipient clicks Reply |
| Primary recipients | `setTo(String... to)` | One or more `To` addresses |
| Carbon copy recipients | `setCc(String... cc)` | `Cc` addresses |
| Blind carbon copy recipients | `setBcc(String... bcc)` | `Bcc` addresses |
| Sent date | `setSentDate(Date date)` | Timestamp declared in the message |
| Subject | `setSubject(String subject)` | Email subject line |
| Body | `setText(String text)` | Plain-text body |

`SimpleMailMessage` also provides corresponding getters such as `getFrom()`, `getTo()`, `getSubject()`, and `getText()` to read configured values.

These address properties differ from interacting directly with the SMTP protocol. For instance, `setFrom(...)` declares the sender of **the message**, whereas the address used in the **SMTP envelope** may be affected by the sender implementation or provider configuration. Do not assume from `setFrom` alone that you have chosen the entire delivery route or bounce-receiving address.

### 2.1. `setFrom(...)`: Sender Address

~~~java
message.setFrom("no-reply@example.com");
~~~

This address normally appears in the email's `From` header. The application must use a domain and account authorized to send under provider policies. Some SMTP providers only permit verified addresses or domains; supplying an arbitrary address does not guarantee server acceptance.

Extract the application's default address into configuration instead of repeating it in every sending method:

~~~yaml
app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
~~~

This is an **application-defined** property that must be read and passed to `setFrom`. Spring Boot does not automatically apply it to every email.

### 2.2. `setTo(...)`, `setCc(...)`, and `setBcc(...)`: Recipient Groups

~~~java
message.setTo("alice@example.net");
message.setCc("manager@example.net");
message.setBcc("audit@example.net");
~~~

Standard semantics:

- **To:** primary recipients.
- **Cc:** copied recipients; addresses are generally visible to other recipients.
- **Bcc:** blind-copied recipients; should not be exposed in copies delivered to other recipients.

Multiple addresses can be specified:

~~~java
message.setTo(
    "alice@example.net",
    "bob@example.net"
);

message.setCc(new String[] {
    "teamlead@example.net",
    "observer@example.net"
});
~~~

**Privacy note:** using `To` or `Cc` for a customer list can expose their addresses to one another. Using `Bcc` may fit some needs, yet personal transactional notifications should generally create a separate email per recipient to avoid mixing personal content, delivery status, and retry handling.

### 2.3. `setReplyTo(...)`: Reply Destination Address

~~~java
message.setFrom("notification@example.com");
message.setReplyTo("support@example.com");
~~~

When the reader clicks **Reply**, their mail client typically uses `Reply-To` if present; otherwise it falls back to `From`. `Reply-To` does not change the SMTP address used for delivery failure notices (bounces), does not create a receiving mailbox by itself, and does not guarantee users will reply.

In this example, the email is sent under `notification@example.com`, while replies are directed to `support@example.com`. That support address must exist and be configured to receive mail for replies to reach their destination.

### 2.4. `setSubject(...)`: Subject Line

~~~java
message.setSubject("Order #A123 has been confirmed");
~~~

The subject should be concise, clear about the business context, and free of secret data such as OTP codes, password-reset tokens, or sensitive details. Although email clients can support Unicode subjects, encoding characters on the wire is still handled by the mail library and charset/encoding settings.

### 2.5. `setText(...)`: Plain Text

~~~java
message.setText("""
    Hello,

    Your order A123 has been recorded.
    Our processing team will provide the next status update.

    Best regards,
    Support Team
    """);
~~~

The body is a regular `String`. Newlines and whitespace are placed into the message body appropriately when Spring/Jakarta Mail constructs the message. Clear paragraphs, short sentences, full URLs, and sensible line spacing generally make text emails easy to read on mobile devices.

If you call:

~~~java
message.setText("<h1>Welcome!</h1>");
~~~

Recipients will see literal text like `<h1>Welcome!</h1>`, **not a rendered HTML heading**, because `SimpleMailMessage` is for plain text.

### 2.6. `setSentDate(...)`: Message Timestamp

~~~java
import java.util.Date;

message.setSentDate(new Date());
~~~

This field represents the sent date and time at the email header level. It is not a scheduling mechanism; setting a future date does **not** make Spring Mail wait until that time before submitting the message to SMTP.

If you need scheduled sending, use a scheduler, queue/job, or operational workflow responsible for triggering the send at the right time.

## 3. Complete Example in Spring Boot

Suppose a Spring Boot application has a service that sends a plain-text notification when an account is created.

### 3.1. Declaring the Dependency

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The starter provides the components needed for a Spring Boot application to use Spring Mail along with the corresponding Jakarta Mail libraries. In a plain Spring Framework project, you can configure dependencies and the sender bean manually without the starter.

### 3.2. Configuring the SMTP Server

Example `application.yml` for an SMTP server using STARTTLS:

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

Explanation:

| Configuration | Role |
| --- | --- |
| `spring.mail.host` / `port` | Provider's SMTP address and port |
| `spring.mail.username` / `password` | Authentication credentials if required by the SMTP provider |
| `spring.mail.default-encoding` | Default encoding for content/messages when the sender creates MIME |
| `mail.smtp.starttls.enable` | Enables upgrading the SMTP connection via STARTTLS |
| `mail.smtp.starttls.required` | Requires TLS upgrade to succeed |
| Timeouts | Time limits for connecting, reading, and writing data |
| `app.mail.from` / `reply-to` | Application-specific values passed to setters |

Port `587` is a common choice for STARTTLS, but always verify your provider's actual configuration. If the provider uses implicit TLS from the start on port `465`, connection settings differ (such as appropriate SSL properties). Never disable TLS verification or blindly copy examples across every provider.

**Never commit SMTP passwords to the repository.** Production environments should supply credentials via environment variables or a secrets manager. Even when sending simple plain-text emails, delivery still depends on transport configuration and domain permissions on the SMTP provider.

### 3.3. Creating the Notification Service

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {
    private final JavaMailSender mailSender;
    private final String from;
    private final String replyTo;

    public AccountMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from,
            @Value("${app.mail.reply-to}") String replyTo) {
        this.mailSender = mailSender;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendWelcome(String recipient, String displayName) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setReplyTo(replyTo);
        message.setTo(recipient);
        message.setSubject("Welcome to the application");
        message.setText("""
            Hello %s,

            Your account has been created successfully.
            If you need help, you can reply to this email.

            Best regards,
            Application Team
            """.formatted(displayName));

        mailSender.send(message);
    }
}
~~~

In this example:

1. Spring injects `JavaMailSender` into the constructor.
2. `From` and `Reply-To` values come from configuration.
3. Each call to `sendWelcome(...)` creates **a new `SimpleMailMessage`**.
4. The service assigns recipient, subject, and plain-text body.
5. `mailSender.send(message)` submits the message through the configured sending mechanism.

This example focuses on API usage. In real services, the calling layer must determine who is authorized to receive emails, validate input data, rate-limit sending, and handle outcomes or failures per business requirements.

### 3.4. Using It in Business Logic

A registration service can call:

~~~java
accountMailService.sendWelcome(
    "new-user@example.net",
    "Nguyễn An"
);
~~~

This works for small programs or operations that do not require decoupling email delivery. However, **creating an account** and **transmitting an email over SMTP** are two operations that can fail independently. For systems requiring high reliability, emit an event or persist the send request to a queue/outbox for a worker to process afterward.

## 4. Limitations of SimpleMailMessage: Text Only, No Complex MIME

`SimpleMailMessage` is convenient for simple emails, but has no API to construct HTML content, attachments, inline images, or alternative parts.

| Requirement | Is `SimpleMailMessage` suitable? | Commonly used tool |
| --- | --- | --- |
| Sending a plain-text paragraph | **Yes** | `SimpleMailMessage` + `MailSender` |
| Sending multiple lines and URLs | **Yes** | `setText(...)` |
| Setting From, To, Cc, Bcc, Reply-To | **Yes** | Corresponding setters |
| Sending Vietnamese subjects and bodies | **Yes**, via mail sender encoding | Sender configured with UTF-8 |
| Content rendered as HTML | **No** | `MimeMessage` + `MimeMessageHelper` |
| Sending both plain text and HTML alternative | **No** | `MimeMessageHelper.setText(plainText, htmlText)` |
| Attaching PDF or ZIP files | **No** | `MimeMessageHelper.addAttachment(...)` |
| Embedding images via `cid:...` | **No** | `MimeMessageHelper.addInline(...)` |
| Setting custom headers directly | **Not via this class's simple API** | `MimeMessage` |
| Reading mail from an inbox | **No** | Separate mail-receiving mechanism |

Note: a plain-text email is still transported as an Internet-standard email message; saying "no MIME" here simply means `SimpleMailMessage` **does not provide a model for building multipart emails or complex MIME structures**. Spring/Jakarta Mail may still generate appropriate MIME headers such as `Content-Type: text/plain; charset=UTF-8` when sending.

### 4.1. When Should You Switch to `MimeMessageHelper`?

If the email requires things like "send a PDF invoice with a description", "display an HTML confirmation button", or "provide both text and HTML versions", switch to `MimeMessage`:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Order details");
helper.setText(
    "Your order has been confirmed.",
    "<html><body><h1>Order Confirmation</h1></body></html>"
);

mailSender.send(mime);
~~~

Passing `true` when creating the helper enables multipart support; `setText(plainText, htmlText)` sets both content versions. When inline resources or attachments are needed, add them with the helper's dedicated methods.

Never try to create HTML emails by placing HTML tag strings into `SimpleMailMessage.setText(...)`: email clients receive plain text and have no instruction to render it as HTML.

## 5. Sending One Email vs. Multiple Emails

`MailSender` supports sending one or multiple `SimpleMailMessage` instances. With `JavaMailSender`, you can also call the same overloads for this message type.

### 5.1. Sending One Email

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("alice@example.net");
message.setFrom("no-reply@example.com");
message.setSubject("Report");
message.setText("The report has been generated.");

mailSender.send(message);
~~~

### 5.2. Sending Multiple Separate Messages

~~~java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("no-reply@example.com");
first.setTo("alice@example.net");
first.setSubject("Notification for Alice");
first.setText("Hello Alice.");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("no-reply@example.com");
second.setTo("bob@example.net");
second.setSubject("Notification for Bob");
second.setText("Hello Bob.");

mailSender.send(first, second);
~~~

Here, each recipient gets a separate message, enabling personalized content and reducing the risk of exposing others' addresses. However, the multi-message overload **does not provide an all-or-nothing transaction guarantee**: a failure partway through can occur after some messages have already been sent. Therefore, the system should track status per request, especially when retries exist.

### 5.3. Using a Message Template Object and Copy Constructor

If many emails share configuration, `SimpleMailMessage` supports creating a copy from another instance:

~~~java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("no-reply@example.com");
template.setReplyTo("support@example.com");
template.setSubject("System notification");

SimpleMailMessage message = new SimpleMailMessage(template);
message.setTo("alice@example.net");
message.setText("Hello Alice.");

mailSender.send(message);
~~~

The idea is to keep a shared template of common details, then copy it and fill in per-email fields. Avoid reusing a single mutable `SimpleMailMessage` directly and repeatedly changing `To` and `Text` across concurrent tasks. If a shared template is used, ensure it is completely initialized and never mutated while other threads copy from it.

## 6. Writing Readable Plain-Text Emails

Plain text has no CSS, HTML tables, or graphical buttons; readability depends on how the text is structured.

### 6.1. Example Order Confirmation Email

~~~text
Hello Nguyễn An,

Your order #A123 has been recorded.

Summary:
- Order ID: A123
- Status: Processing
- Order date: 12/11/2026

You can view progress at:
https://example.com/orders/A123

If you need assistance, reply to this email.

Best regards,
Customer Support Team
~~~

Points to remember:

- Put essential details at the top; some email clients only display a few preview lines.
- Use short paragraphs, bullet points, and blank lines when presenting lots of information.
- Include full URLs instead of assuming clickable HTML link text is available.
- Clearly state the support address or channel so readers know what to do next.
- Avoid embedding excessive personal data, verification codes, or sensitive tokens in body, subject, and logs.

### 6.2. When Data Contains Unicode Characters

Example:

~~~java
message.setSubject("Xác nhận yêu cầu hỗ trợ");
message.setText("Xin chào Nguyễn An,\nYêu cầu của bạn đã được ghi nhận.");
~~~

Java `String` supports Unicode; the mail sender and underlying library handle encoding text and headers for email transmission. For Vietnamese emails, configure encoding explicitly, such as `spring.mail.default-encoding: UTF-8` in Spring Boot.

If recipients see garbled characters like `Ã` or undecoded quoted-printable strings, check the charset and headers when the email is sent. Never manually Base64-encode the whole string passed to `message.setText(...)`, because the setter expects **plain text content**, not a manually encoded string.

## 7. Handling Errors When Sending with SimpleMailMessage

Sending can fail due to network connectivity, unavailable SMTP servers, invalid authentication, rejected recipients, or configuration issues.

Spring uses the `MailException` hierarchy (unchecked) and several subclasses:

| Exception | General meaning |
| --- | --- |
| `MailAuthenticationException` | Problem during mail authentication |
| `MailSendException` | Error during the sending process |
| `MailPreparationException` | Error while preparing the mail message |
| `MailException` | Common base class for Spring Mail errors |

Example service recording errors at the sending boundary:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {
    private static final Logger log =
            LoggerFactory.getLogger(ReportMailService.class);

    private final JavaMailSender sender;

    public ReportMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendReport(String recipient, String reportId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("reports@example.com");
        message.setTo(recipient);
        message.setSubject("Report is ready");
        message.setText(
                "Report " + reportId + " has been generated successfully.");

        try {
            sender.send(message);
            log.info("SMTP submission completed for reportId={}", reportId);
        } catch (MailException ex) {
            log.error("SMTP submission failed for reportId={}", reportId, ex);
            throw ex;
        }
    }
}
~~~

The code uses `reportId` as correlation info, avoiding dumping recipient addresses and full email bodies into logs. Rethrowing the exception informs the caller of the failure; in a real product, you can persist job status and enqueue for processing per requirements.

### 7.1. What Does a Successful Send Call Mean?

If `sender.send(message)` returns normally, we know the send call through the sender finished without throwing a synchronous exception. With SMTP, that outcome generally indicates the provider accepted **the message submission**, and **does not prove** the email reached the Inbox, was read, or was not bounced later by downstream systems.

To track the true status of an email after submission, you need mechanisms outside this simple API, such as:

- delivered/bounced event webhooks from the email provider;
- Delivery Status Notifications (DSN), a bounce mailbox, or a bounce-handling service;
- job status persisted in a database when the system uses a queue.

`SimpleMailMessage` has no fields to manage these business states by itself.

### 7.2. Not Every Error Should Be Retried

SMTP has `4xx` responses for many temporary conditions and `5xx` for many cases requiring a fix before resending. However, JavaMailSender may report a general exception while the SMTP reply code is nested deep inside the root cause, if present at all.

Do not classify blindly as "every `MailSendException` is retryable" or "every `MailAuthenticationException` is a permanent wrong password". Inspect the actual cause, SMTP code if available, provider, and protocol phase. Timeouts after message data has been transmitted can also leave an **uncertain state as to whether the server accepted the message**; retrying risks duplicate delivery.

For critical requests, attach a **business ID**, store attempt counts and per-recipient outcomes, and use bounded backoff alongside application-level deduplication.

## 8. Synchronous vs. Asynchronous Sending

By default, a regular `mailSender.send(message)` call runs on the calling thread and waits for the corresponding send operation to finish or fail.

~~~mermaid
flowchart LR
    A["Account registration"] --> B["Account service"]
    B --> C["Create SimpleMailMessage"]
    C --> D["JavaMailSender.send"]
    D --> E["SMTP provider"]
    E -. "Synchronous send result" .-> B
~~~

This is simple, yet can slow down HTTP requests if SMTP responds slowly. For high-volume or high-reliability systems:

~~~mermaid
flowchart LR
    A["Account registration"] --> B["Save business data"]
    B --> C["Save mail job / outbox"]
    C --> D["Queue or worker"]
    D --> E["Create SimpleMailMessage"]
    E --> F["JavaMailSender.send"]
    F --> G["SMTP provider"]
    D --> H["Status / retry"]
~~~

`SimpleMailMessage` **does not depend on synchronous or asynchronous invocation**: it remains purely message data. A worker can use the exact same `send(...)` API to submit the message. Using `@Async` also does not automatically provide a queue durable across restarts, retry schedules, or duplicate-send prevention; those capabilities must be designed separately.

## 9. Testing Services That Send SimpleMailMessage

Because content is wrapped in a simple data object, you can test message-building logic without connecting to a real SMTP server.

### 9.1. Unit Testing with a Mock Sender

Assuming the service receives `JavaMailSender` via constructor, you can use Mockito to capture the object passed to `send(...)`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class AccountMailServiceTest {

    @Test
    void sendsWelcomeAsPlainText() {
        JavaMailSender sender = mock(JavaMailSender.class);
        AccountMailService service =
                new AccountMailService(
                        sender,
                        "no-reply@example.com",
                        "support@example.com");

        service.sendWelcome("customer@example.net", "Nguyễn An");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage message = captor.getValue();
        assertEquals("no-reply@example.com", message.getFrom());
        assertEquals("support@example.com", message.getReplyTo());
        assertEquals("customer@example.net", message.getTo()[0]);
        assertEquals(
                "Welcome to the application",
                message.getSubject());
        assertEquals(true, message.getText().contains("Nguyễn An"));
    }
}
~~~

This style of test verifies that the service **builds the right data and calls the sender**, but does not test a real SMTP server, encoding after conversion to MIME, or delivery status. The service name in the example matches the class defined earlier; the project needs JUnit Jupiter and Mockito in test dependencies.

### 9.2. Integration Testing with a Mock SMTP Server

Tools like **Mailpit** or **GreenMail** allow the application to send emails to a test server and inspect the received content:

1. Configure host/port to point to the test SMTP server.
2. Invoke the service that builds `SimpleMailMessage`.
3. Inspect the email recorded in the test tool.
4. Check the `From`, `To`, `Reply-To`, `Subject`, and `Content-Type` headers of the received message.
5. Check the text content and Unicode character rendering.

Using a mock SMTP server avoids sending test emails to real customers. You should only conclude that the integration test successfully simulated **the submission flow**, not that it verified inbox delivery with a production provider.

## 10. Common Pitfalls

### 10.1. Using the Same SimpleMailMessage for Multiple Requests

~~~java
// Unsuitable if multiple requests share a mutable instance.
private final SimpleMailMessage sharedMessage = new SimpleMailMessage();

public void send(String to, String text) {
    sharedMessage.setTo(to);
    sharedMessage.setText(text);
    sender.send(sharedMessage);
}
~~~

Two concurrent requests can overwrite each other's address/body. Create a new object per request or copy an effectively immutable template:

~~~java
public void send(String to, String text) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("no-reply@example.com");
    message.setTo(to);
    message.setText(text);
    sender.send(message);
}
~~~

### 10.2. Putting HTML into `setText(...)` and Expecting It to Render

~~~java
message.setText("<strong>Important</strong>");
~~~

That content remains plain text. If you need HTML, switch to `MimeMessageHelper` and use `setText(html, true)` or `setText(plainText, htmlText)`.

### 10.3. Letting Users Supply Arbitrary Recipients Without Validation

A public endpoint letting outsiders call:

~~~text
POST /send-mail
to = any address
subject = any string
body = any content
~~~

can easily become a spam-sending tool. Tie sending actions to specific business workflows, authenticate/authorize callers, validate data, rate-limit, and prevent users from arbitrarily choosing `From`. When handling addresses, use the appropriate JavaMail APIs to validate syntax and let the library handle headers rather than concatenating SMTP/header lines from input strings.

### 10.4. Forgetting to Configure Timeouts

Without proper timeouts, a send attempt to a troubled SMTP provider can hang longer than expected, slowing requests or tying up worker threads. Configure connection/read/write timeouts tailored to system requirements and retry policies.

### 10.5. Equating Send Success with Email Delivery

A successful `send(...)` call generally indicates the SMTP server accepted responsibility for handling the message at the protocol level; it does not confirm the recipient saw it. Important transactional systems should record "submitted to mail service" in internal state where appropriate, rather than falsely showing that the recipient definitely received it.

### 10.6. Confusing Reply-To with the Bounce Address

`setReplyTo("support@example.com")` directs human reply actions. It does not configure the SMTP envelope reverse-path and does not guarantee bounces are routed there. Tracking bounces normally requires provider configuration, DSN, or webhooks.

## 11. Quick Comparison with MimeMessage

| Criterion | `SimpleMailMessage` | `MimeMessage` / `MimeMessageHelper` |
| --- | --- | --- |
| Complexity | Minimal API, easy to read | More structural options |
| Content | Plain text | Text, HTML, and multipart |
| Sender/Recipient/Reply-To | Yes | Yes |
| Cc/Bcc | Yes | Yes |
| Unicode subjects | Supported via sender/encoding | Supported via MIME library |
| Attachments | No | Yes |
| Inline images | No | Yes |
| Custom headers | Limited | Can manipulate directly on `MimeMessage` |
| Good fit for | Simple notification OTPs (avoid unnecessary secrets), text notifications, internal alerts | HTML marketing emails, PDF invoices, multipart emails |

You do not need to switch to MIME merely because an email has multiple lines or contains Vietnamese. `SimpleMailMessage` handles basic text well. The reason to move to MIME comes primarily from **formatting and attachment requirements**.

## 12. Combined Scenario: Task Completion Notification System

Suppose an application has a report-generation workflow. When a report finishes, the system wants to send a text email to the requester:

~~~text
From: reports@example.com
Reply-To: support@example.com
To: customer@example.net
Subject: November report is ready

Hello,

The November report has been generated successfully.
You can open the management page to download the report.

If you need assistance, reply to this email.
~~~

Implementation flow:

1. **Report service** identifies who should receive it and the completed report ID.
2. **Notification service** creates a new `SimpleMailMessage`, sets addresses, subject, and text body.
3. **Mail sender** injected by Spring calls `send(message)` to submit the email to the SMTP provider.
4. **Orchestration layer** records submission status and classifies errors if needed.
5. If business rules require resending, a **worker or queue** manages retries by job ID rather than reusing the same mutable instance.
6. If you later want to attach a PDF, switch content construction to **`MimeMessageHelper`**, while keeping the notification intent from Report service intact.

Self-check questions when reading code:

- Where is `SimpleMailMessage` created fresh, and is it ever shared across threads?
- Where do `From`, `To`, `Reply-To`, and subject come from, and do they match sending permissions and business rules?
- Does `setText(...)` hold genuine plain-text content or HTML mistakenly sent as text?
- Where are encoding, SMTP timeouts, and credentials configured?
- If the sender throws an error, how does the application handle it, and is there a duplicate-send risk on retry?

Understanding `SimpleMailMessage` accurately means understanding **a simple email data model**: populate a plain-text message with setters, pass it to `MailSender`/`JavaMailSender` to send, and let external mechanisms handle SMTP configuration, status tracking, security, and retries. It serves as a solid foundation before diving deeper into `MimeMessage` and multipart email structures.

### APIs and Reference Documentation

- **Spring Framework — `org.springframework.mail.SimpleMailMessage`:** constructor, copy constructor, and `setFrom`, `setTo`, `setCc`, `setBcc`, `setReplyTo`, `setSubject`, `setText`, and `setSentDate` methods.
- **Spring Framework — `MailSender`:** interface for sending `SimpleMailMessage`.
- **Spring Framework — `JavaMailSender` and `MimeMessageHelper`:** extensions for MIME, HTML, and attachments.
- **Spring Boot — Mail support / `spring.mail.*`:** auto-configuring the sender and SMTP connection properties.

# JavaMailSender and MimeMessage Creation Capabilities

## 1. What Problem Does JavaMailSender Solve?

In a Java application using **Spring Framework Mail**, the need to send email usually starts with business information: recipients, subject, content, images, and attachments. To turn that information into a valid email, the application needs an API to create messages, set headers, encode content, and communicate with a mail-sending system.

**`JavaMailSender`** is Spring's interface for sending mail through **Jakarta Mail**. It provides two core capabilities:

1. **Creating a `MimeMessage`** so the application can proactively build emails with a MIME structure.
2. **Sending a `MimeMessage` or preparing and sending a message** through a configured mail transport, typically SMTP.

`MimeMessage` is Jakarta Mail's message type capable of representing plain-text email, HTML, multiple content versions, inline resources, and attachments. `JavaMailSender` is not an SMTP server, not a user-facing mail composer UI, and does not by itself guarantee that a message is read by the recipient. It is the **application-side integration point** between Spring business logic and Jakarta Mail's email creation/transport mechanism.

Examples of scenarios requiring `JavaMailSender`:

- Sending account verification emails with links and HTML templates.
- Sending PDF invoices accompanied by a text message.
- Sending reports with HTML tables and a logo displayed inline in the content.
- Sending dual-version `text/plain` and `text/html` emails so mail clients can choose the appropriate rendering.
- Creating or reading back a MIME message from an `.eml` source for authorized business processing.

If you only need a few lines of plain text without attachments, Spring also provides `SimpleMailMessage`; when MIME capabilities are required, `JavaMailSender.createMimeMessage()` is the natural starting point.

## 2. Placing JavaMailSender in the Spring Mail Architecture

The related classes have distinct roles:

| Component | Role | Owned by? |
| --- | --- | --- |
| `MailSender` | Spring contract for sending `SimpleMailMessage` | Spring Framework |
| `JavaMailSender` | Extends `MailSender`, creates and sends `MimeMessage`; supports `MimeMessagePreparator` | Spring Framework |
| `JavaMailSenderImpl` | Common implementation, manages configuration and invokes Jakarta Mail transport | Spring Framework |
| `MimeMessage` | MIME message object containing headers/body and parts | Jakarta Mail |
| `MimeMessageHelper` | Helper class for setting To/Cc/Bcc, Subject, text/HTML, inline resources, and attachments | Spring Framework |
| `MimeMessagePreparator` | Callback that prepares a `MimeMessage` provided by the sender | Spring Framework |
| `Session` / `Transport` | Configures environment and transports mail via Jakarta Mail mechanisms | Jakarta Mail |
| SMTP server/provider | Accepts, authenticates, and relays mail per protocol/policy | Email infrastructure |

Overview diagram:

~~~mermaid
flowchart LR
    A["Spring business service"] --> B["JavaMailSender"]
    B --> C["createMimeMessage()"]
    C --> D["MimeMessage"]
    E["MimeMessageHelper or MimeMessagePreparator"] --> D
    D --> F["send(...)"]
    F --> G["Jakarta Mail Transport"]
    G --> H["SMTP Server / email provider"]
    H --> I["Delivery infrastructure"]
~~~

In a typical Spring Boot application, the mail starter together with `spring.mail.*` configuration can provide a `JavaMailSender` bean. In a plain Spring Framework application, you can declare a `JavaMailSenderImpl` bean according to the project's configuration style.

A key distinction: **`JavaMailSender` is an interface**, while **`JavaMailSenderImpl` is an implementation**. Services should depend on the interface so transports, configurations, or test doubles can be swapped easily.

## 3. Core API of JavaMailSender

`JavaMailSender` inherits `SimpleMailMessage`-sending capabilities from `MailSender` and adds MIME-specific operations.

| Representative method | Purpose | Accurate interpretation of the outcome |
| --- | --- | --- |
| `createMimeMessage()` | Creates a new `MimeMessage` | Only creates an object for composing; **does not send an email yet** |
| `createMimeMessage(InputStream)` | Creates/parses a `MimeMessage` from serialized MIME data | Suitable for reading a source containing a complete message, such as `.eml` |
| `send(MimeMessage)` | Sends a prepared message | Triggers mail transport; may throw `MailException` |
| `send(MimeMessage...)` | Sends multiple messages | Does not implicitly guarantee atomicity for the entire batch |
| `send(MimeMessagePreparator)` | Lets the sender create a message, invoke the preparation callback, and send | Convenient when encapsulating construction and sending |
| `send(MimeMessagePreparator...)` | Prepares and sends multiple messages | Must handle partial-success / partial-failure cases |
| `send(SimpleMailMessage)` | Sends a simple plain-text email | Part of the `MailSender` contract inherited by `JavaMailSender` |

This API **does not provide an Inbox view, received-mail search, or user draft management**. It serves the server-side email composition/sending path. Receiving and reading mail generally require other APIs, such as other parts of Jakarta Mail or provider-specific APIs.

### 3.1. How Does createMimeMessage() Differ from send()?

Consider the lifecycle:

~~~text
JavaMailSender
    |
    +-- createMimeMessage()
    |       |
    |       +-- Initial MimeMessage
    |               |
    |               +-- setFrom, setTo, setSubject, setText...
    |               +-- add MIME parts if needed
    |               |
    |               +-- send(message)
    |                       |
    |                       +-- Jakarta Mail transport
    |                               |
    |                               +-- SMTP submission
    |
    +-- createMimeMessage(InputStream)
            |
            +-- parse message from source MIME data
~~~

When calling `createMimeMessage()`, the application **does not open an SMTP connection merely because this method was called**, and there are no recipients or body yet until the developer assigns them. Sending only occurs when `send(...)` is called or an equivalent sending workflow is triggered.

This has the following consequences:

- You can prepare, inspect headers, add attachments, or serialize the message before sending.
- You can detect MIME construction errors before the network-sending stage.
- You must not conclude "sent successfully" merely because a `MimeMessage` was created.
- You should not reuse the same `MimeMessage` object and mutate it concurrently from multiple threads; each send attempt should create its own message with that attempt's data.

### 3.2. What Can a MimeMessage Contain?

A MIME message consists of **headers**, a **body**, and possibly multiple child nodes in a `multipart` structure.

Example of a text-only message:

~~~text
MimeMessage
├── From: reports@example.com
├── To: lan@example.net
├── Subject: Weekly report
└── text/plain; charset=UTF-8
    "Weekly report is ready."
~~~

Example of a message with text, HTML, an inline image, and a PDF:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   │       <img src="cid:weekly-logo">
    │   └── image/png
    │       Content-ID: <weekly-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="weekly-report.pdf"
~~~

This is an **illustrative structure**; the exact tree depends on how `MimeMessageHelper` is used, the multipart mode, and the order/manner in which components are added. `multipart/alternative` expresses alternative versions of the same content, `multipart/related` groups a body with related resources, and `multipart/mixed` typically combines a body with independent attachments.

## 4. Creating a Simple MimeMessage with MimeMessageHelper

`MimeMessage` belongs to Jakarta Mail and provides direct APIs for setting fields. However, Spring offers **`MimeMessageHelper`** to make common operations concise, especially when charsets, HTML, or multipart are needed.

Example service sending a text email with Spring Framework 6 and the `jakarta.mail.*` package:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationMailer {

    private final JavaMailSender mailSender;

    public AccountNotificationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false, // No multipart needed for simple plain text.
                StandardCharsets.UTF_8.name());

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");
        helper.setText("Hello " + displayName
                + ", your account is ready.", false);

        mailSender.send(message);
    }
}
~~~

Step-by-step explanation:

1. **Inject dependency** `JavaMailSender` via constructor; the service does not depend on the `JavaMailSenderImpl` class.
2. **Create message** via `mailSender.createMimeMessage()`. No email has been sent yet.
3. **Create helper** with `multipart=false` and charset `UTF-8` to compose a plain-text message.
4. **Set fields** `From`, `To`, `Subject`, and body using `helper`.
5. **Call send** so Jakarta Mail performs transport through the configured server.

In `helper.setText(body, false)`, the `false` argument means **plain text**. Passing `true` represents the content as **HTML**. For simple text, `SimpleMailMessage` can be used; this example uses `MimeMessage` to explain the API and allow easy future expansion.

In a real application, `recipient` must be validated per the business contract, `displayName` must be handled appropriately, and the `From` address must be authorized by the SMTP system. The example above does not build a public endpoint allowing anyone to send to arbitrary addresses.

### 4.1. Can You Manipulate MimeMessage Directly?

Yes. Example with Jakarta Mail:

~~~java
MimeMessage message = mailSender.createMimeMessage();
message.setFrom(new jakarta.mail.internet.InternetAddress(
        "notifications@example.com"));
message.setRecipients(
        jakarta.mail.Message.RecipientType.TO,
        jakarta.mail.internet.InternetAddress.parse("lan@example.net"));
message.setSubject("Notification", "UTF-8");
message.setText("Notification content", "UTF-8");

mailSender.send(message);
~~~

Setters on `MimeMessage` can throw `MessagingException`; the example assumes it sits inside a method that declares or handles the exception appropriately. Note that `MimeMessage` does not require `MimeMessageHelper`, but when the message structure gets complex, the helper makes managing multipart, charsets, and resources much easier.

## 5. Creating an HTML Email with a Plain-Text Fallback

Many transactional emails need HTML formatting while still providing a plain-text version. Some mail readers do not render HTML, or users disable HTML due to security/accessibility policies.

The message should have `multipart/alternative`:

~~~text
multipart/alternative
├── text/plain
│   "Order #A102 has been confirmed."
└── text/html
    "<p>Order <strong>#A102</strong> has been confirmed.</p>"
~~~

With `MimeMessageHelper` initialized in multipart mode, you can create both versions:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Order confirmation");

String plainText = "Order #A102 has been confirmed.";
String htmlText =
        "<p>Order <strong>#A102</strong> has been confirmed.</p>";

helper.setText(plainText, htmlText);

mailSender.send(message);
~~~

The `setText(String plainText, String htmlText)` method creates **two versions of the same content** per MIME semantics. This is cleaner than manually adding two independent body parts to `multipart/mixed`, where clients might misinterpret them and render both.

If only HTML is needed, a shorter form is:

~~~java
helper.setText(
        "<p>The order has been <strong>confirmed</strong>.</p>",
        true);
~~~

The `true` argument requests an HTML content type. It **does not automatically add a plain-text version**: if you want both, use the two-string overload.

### 5.1. Valid MIME HTML Does Not Mean Every Client Renders It Identically

Email clients may strip complex CSS, JavaScript, forms, or remote images. Even when `Content-Type: text/html` is valid, HTML mail must still be designed for target email clients. For user-provided data, escape and insert it into templates safely; never concatenate arbitrary HTML and treat it as trusted content.

Furthermore, the HTML string is the **body**; content inside it is not used to replace `From`/`To`/`Subject` fields located in the message headers.

## 6. Creating Attachments and Inline Images in One MimeMessage

When sending an email with a PDF and a logo displayed inside the HTML, a single `text/html` body is not enough. You need MIME relationships among the body, embedded images, and attachments.

Spring provides these operations:

- `MimeMessageHelper.addAttachment(...)` to add an independent attached file.
- `MimeMessageHelper.addInline(...)` to add a resource with a `Content-ID` referenced in HTML via `cid:...`.
- `MULTIPART_MODE_*` modes to choose how MIME containers are organized.

Example service creating an email with text, HTML, a PNG logo, and a PDF:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WeeklyReportMailer {

    private final JavaMailSender mailSender;

    public WeeklyReportMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            Resource logoPng,
            Resource reportPdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Weekly report");

        String plain = "Weekly report is ready."
                + " See the attached PDF file.";

        String html = "<p>Weekly report is <strong>ready</strong>.</p>"
                + "<img src=\"cid:weekly-logo\" alt=\"Logo\">"
                + "<p>See the attached PDF file.</p>";

        helper.setText(plain, html);
        helper.addInline("weekly-logo", logoPng, "image/png");
        helper.addAttachment("weekly-report.pdf", reportPdf);

        mailSender.send(message);
    }
}
~~~

**Important details:**

**Multipart mode.** `MULTIPART_MODE_MIXED_RELATED` typically creates an outer `multipart/mixed` to separate attachments from the body, and an inner `multipart/related` for the body and inline resources. The `text/plain` and `text/html` parts continue to be organized in an `alternative` relationship.

**Content-ID.** In the HTML, `src="cid:weekly-logo"` must match the ID `weekly-logo` passed to `helper.addInline(...)`. MIME may generate a `Content-ID: <weekly-logo>` header; the angle brackets are header notation and are not part of the `cid:` string in HTML.

**Call order.** Call `setText(...)` before `addInline(...)` when building HTML with embedded images, so the HTML body part exists at the time the inline resource is added.

**Data source.** `Resource` must provide readable data. With `InputStreamSource`, some serialization/sending steps may need to open the stream multiple times; do not pass a stream that has already been consumed and cannot be reopened. You can use a file resource or `ByteArrayResource` if the size is controlled and appropriate for the deployment.

**Attachments.** The filename `weekly-report.pdf` is the display name shown to the recipient, not necessarily the server file path. Never let the client choose an arbitrary server path to send as a file; the backend must verify access permissions and size limits.

### 6.1. Multipart Modes in MimeMessageHelper

| Mode | Primary purpose | Cases to note |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Does not create a multipart tree for inline/attachments | Suitable for simple messages not needing multiple MIME parts |
| `MULTIPART_MODE_MIXED` | A single `multipart/mixed` container | Rendering of inline resources may vary across clients |
| `MULTIPART_MODE_RELATED` | A `multipart/related` container | Relationship between body and attachments may be interpreted differently |
| `MULTIPART_MODE_MIXED_RELATED` | `mixed` wrapping `related` | Generally suitable when the body has inline images and the email has attachments |

No single tree structure fits every client perfectly. If an email renders differently across applications, inspect the actual MIME content and choose a structure compatible with your target clients.

### 6.2. When Should You Inspect the Generated MIME Tree?

If an email arrives but the PDF disappears or the logo shows as a broken image, inspect the entire MIME tree, not just the HTML string:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png [inline] Content-ID=<weekly-logo>
    └── application/pdf [attachment] filename=weekly-report.pdf
~~~

Check `Content-Type`, `Content-ID`, `Content-Disposition`, charset, filename, and boundaries of each part. If an image is placed in an unrelated branch, or a PDF is treated as an alternative to HTML, clients may display the message unexpectedly.

## 7. MimeMessagePreparator: Creating and Sending in One Callback

Besides calling `createMimeMessage()` and then `send(message)`, `JavaMailSender` supports **`MimeMessagePreparator`**. The callback receives a `MimeMessage` already created by the sender so business code can populate its content:

~~~java
package com.example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class PasswordChangedMailer {

    private final JavaMailSender mailSender;

    public PasswordChangedMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient) {
        mailSender.send(mimeMessage -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mimeMessage, false, "UTF-8");

            helper.setFrom("security@example.com");
            helper.setTo(recipient);
            helper.setSubject("Password changed");
            helper.setText(
                    "Your account password has just been changed.",
                    false);
        });
    }
}
~~~

Here:

1. `JavaMailSender` creates a new `MimeMessage`.
2. The callback is invoked to set the fields.
3. Once the callback completes, the sender executes the send operation.
4. If the callback or transport fails, the Spring API reports the error via the appropriate mail exception hierarchy.

The advantage of this approach is that message creation and sending happen in a single service call, reducing the risk of forgetting `send(...)`. The downside is that if you want to hold onto the object to inspect it across multiple steps before sending, creating `MimeMessage` directly is usually clearer.

Do not mistake `MimeMessagePreparator` for a background job or an automatic retry feature. The callback runs synchronously as part of the send call; async execution, queuing, or retries require separate mechanisms.

### 7.1. Which Style to Choose?

| Usage style | Example | Choose when |
| --- | --- | --- |
| Create first, then send | `MimeMessage m = sender.createMimeMessage(); ...; sender.send(m);` | You need to inspect, add parts across multiple steps, or serialize before sending |
| Use preparator | `sender.send(message -> { ... });` | Preparation is simple and fits cleanly inside one callback |
| Use simple message | `sender.send(simpleMailMessage);` | Plain-text email without complex MIME parts |

These are all ways of using the same Spring Mail transport foundation. Choose the one that best fits code readability, extensibility, and business boundaries.

## 8. createMimeMessage(InputStream): Reading Back an Existing MIME Message

Most examples use the no-arg `createMimeMessage()` to compose an email from scratch. However, `JavaMailSender` also provides:

~~~java
MimeMessage createMimeMessage(InputStream contentStream);
~~~

Its purpose is **creating a `MimeMessage` from already-serialized MIME message data**, such as an `.eml` source containing headers and body:

~~~text
From: reports@example.com
To: lan@example.net
Subject: Report
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Report is ready.
~~~

Example illustrating loading a source message:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

// Assume JavaMailSender mailSender is available in scope.
try (InputStream source = Files.newInputStream(Path.of("sample.eml"))) {
    MimeMessage parsed = mailSender.createMimeMessage(source);
    System.out.println(parsed.getContentType());
}
~~~

This snippet must be placed in a method declaring or handling `IOException` and `MessagingException` appropriately. It **does not send an email**. Sending only occurs if the code proceeds to call `mailSender.send(parsed)`.

A major distinction: the `InputStream` argument here is **the entire email in MIME format**, not just the raw bytes of a PDF you want to attach. If you want to attach a PDF, create a regular `MimeMessage` and use `MimeMessageHelper.addAttachment(...)` or the corresponding MIME APIs.

When reloading an existing message, pay attention to the data source, headers, processing permissions, and integrity. Resending an old email—especially a digitally signed message or one with specific transport headers—can cause business issues. This is a message parsing/creation capability, not a safe auto-forward feature for every situation.

## 9. Configuring JavaMailSender in Spring Boot and Plain Spring Framework

### 9.1. Spring Boot: Auto-Configuration When Conditions Are Met

In typical Spring Boot applications, the `spring-boot-starter-mail` dependency and mail configuration can create a `JavaMailSender` bean. Example SMTP submission configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: account-from-secure-configuration
    password: secret-from-secure-configuration
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

The `username`/`password` values are illustrative strings, not real credentials. In deployed environments, obtain credentials from environment variables or a secrets store, and ensure the `From` address is authorized to send.

Meaning of the properties:

- `host` and `port` specify the SMTP endpoint. Port 587 is commonly used for submission with STARTTLS.
- `mail.smtp.auth` enables SMTP authentication according to mechanisms supported by the provider.
- `mail.smtp.starttls.enable` requests upgrading the connection via STARTTLS when advertised by the server; `required` forces TLS to be established successfully.
- `connectiontimeout`, `timeout`, and `writetimeout` are in milliseconds, preventing I/O operations from hanging indefinitely when the server or network has issues.

Providers using port 465 typically require TLS from the very start of the connection (*implicit TLS*), unlike STARTTLS on port 587. Do not change the port number while keeping the same protocol assumptions; configure according to the provider's documentation.

### 9.2. Plain Spring Framework: Declaring JavaMailSenderImpl Manually

When not using Spring Boot auto-configuration, you can create the bean directly:

~~~java
package com.example.mailconfig;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

    @Bean
    JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.net");
        sender.setPort(587);
        sender.setUsername("account-from-secure-configuration");
        sender.setPassword("secret-from-secure-configuration");
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

This code illustrates the configuration mechanism. In real projects, host, user, and password values must come from secure environment-managed configuration rather than being hardcoded in source. `setDefaultEncoding("UTF-8")` affects the default encoding when creating `MimeMessage` via this implementation, though individual templates still need appropriate encoding consistent with how content is built.

Do not instantiate a new `JavaMailSenderImpl` every time you send an email. A centrally configured Spring bean ensures consistent server policies, timeouts, and transport settings. Conversely, **each email needs its own `MimeMessage`** so recipient, header, and body state do not mix across sends.

## 10. Message Creation and Sending Are Two Different Failure Stages

With `JavaMailSender`, distinguish the stages:

~~~mermaid
flowchart TD
    A["createMimeMessage"] --> B["Set headers and body / multipart"]
    B --> C{"MIME preparation succeeded?"}
    C -->|No| D["Message creation error"]
    C -->|Yes| E["JavaMailSender.send"]
    E --> F{"SMTP accepted?"}
    F -->|No| G["Connection, auth, sender, recipient, or data error"]
    F -->|Yes| H["Server accepted for processing"]
    H --> I["Later delivery / separate status reporting"]
~~~

Different errors should be handled at the appropriate place:

| Failure point | Example | Information to record |
| --- | --- | --- |
| Creating `MimeMessage`/helper | Invalid address, multipart/attachment build error, `MessagingException` | Request ID, related field, root cause; avoid logging full sensitive data |
| SMTP connection | DNS, timeout, server unavailable | Endpoint, timestamp, timeout type, retryability |
| Auth/TLS | Invalid credentials, TLS not supported per policy | Security/configuration error category, do not log secrets |
| `MAIL FROM`/`RCPT TO` | Unauthorized address, rejected recipient | Reply code and affected recipient set |
| `DATA`/after DATA | Message exceeds limit, content rejected, connection dropped | Final response or uncertain status |
| After server acceptance | Bounce, spam policy, delivery delay | Track status via provider signals or DSN |

### 10.1. MessagingException and MailException

Jakarta Mail operations such as `MimeMessage#setSubject` or `MimeMessageHelper#setText` can declare **`MessagingException`** (checked). When calling `JavaMailSender.send(...)`, Spring primarily represents send errors through the **`MailException`** family (runtime), for example:

- `MailAuthenticationException`: authentication issues with the server.
- `MailSendException`: one or more messages failed to send, depending on the situation.
- `MailParseException`: message parsing/preparation errors reported through the mail abstraction.
- `MailPreparationException`: errors during message preparation, such as in a preparator callback.

Do not wrap all code in `catch (MessagingException)` and assume every SMTP send failure is handled. Conversely, catching only `MailException` does not replace handling checked exceptions when constructing messages manually.

### 10.2. Does Success in send Mean Delivered?

`mailSender.send(message)` returning normally usually means the submission operation was completed by the mail transport according to the response it received. It **does not guarantee** the email appeared in the Inbox, escaped spam filtering, or was opened by the recipient. Over SMTP, a server can return `250` after `DATA` and continue relaying afterward.

For business workflows needing tracking, distinguish:

1. `CREATED`: the message has been prepared in the application.
2. `SUBMISSION_ACCEPTED`: the provider/SMTP server accepted it for processing.
3. `DELIVERED` or `BOUNCED`: delivery status evidence exists from an authoritative system.
4. `OPENED`: if valid tracking data exists, this remains only a signal dependent on specific technology/policies, never inferred directly from SMTP.

The status names above are business design examples, **not built-in enums in `JavaMailSender`**.

### 10.3. Sending Multiple MimeMessages Does Not Automatically Become an Atomic Transaction

With:

~~~java
mailSender.send(messageOne, messageTwo, messageThree);
~~~

one or more messages may have been accepted by the server before an error occurred. You cannot use a database transaction rollback to recall emails already accepted by SMTP. When retrying, you need to know which messages succeeded, and account for connection drops leaving uncertain results.

For important business emails, recording send requests in a database/queue and processing them via a worker (e.g., an outbox) helps manage retries, tracking, and reduces the risk of lost requests. This is an application-layer design, not a default feature of `JavaMailSender`.

## 11. Inspecting a MimeMessage Before Sending

Because `createMimeMessage()` returns an object you can work with, you can **serialize** it in a test environment to inspect the MIME structure:

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

// Shortened example; assume JavaMailSender mailSender exists.
MimeMessage message = mailSender.createMimeMessage();
message.setFrom(new jakarta.mail.internet.InternetAddress(
        "reports@example.com"));
message.setRecipients(
        jakarta.mail.Message.RecipientType.TO,
        jakarta.mail.internet.InternetAddress.parse("lan@example.net"));
message.setSubject("Report", "UTF-8");
message.setText("Report content", "UTF-8");

message.saveChanges();
try (OutputStream output =
             Files.newOutputStream(Path.of("message-sample.eml"))) {
    message.writeTo(output);
}

// Only send when the business logic explicitly requests it:
// mailSender.send(message);
~~~

The example assumes the code resides in a method handling/declaring I/O exceptions and `MessagingException`. `saveChanges()` updates necessary changes before writing MIME output; `writeTo(...)` serializes into data resembling an `.eml` file. **Writing to a file does not mean sending over SMTP.**

You can observe:

- `From`, `To`, `Cc`, `Subject`, and MIME headers;
- `Content-Type` at the root and per part;
- `multipart/alternative`, `multipart/related`, `multipart/mixed`;
- `Content-ID` of inline images and `cid:...` in HTML;
- `Content-Disposition: attachment`, filename, and charset.

Do not commit or share real `.eml` files containing private emails, tokens, or internal attachments. When inspecting the SMTP protocol, protocol traces can also contain sensitive information, so enable debugging only in a controlled manner.

### 11.1. A Case Requiring Distinction Between MIME and SMTP

The application sends an HTML email; `JavaMailSender.send(...)` completes, yet the recipient sees the literal line:

~~~text
<p>Hello <strong>Lan</strong></p>
~~~

This may be a **Content-Type** error on the body (`text/plain` instead of `text/html`), not an SMTP error. Check the `helper.setText(html, true)` call and the actual MIME data before/after sending. If the MIME output is correct but the client still renders it wrong, examine client policies and intermediary systems next.

Another case: the SMTP server rejects `RCPT TO` with a relay-permission error. In that case, fixing the HTML or changing the multipart mode will not solve the root cause; inspect account configuration, sender/recipient domains, and SMTP policies.

## 12. Common Confusions

**"Creating a MimeMessage means an SMTP connection has been opened?"**  
No. `createMimeMessage()` creates a message for composing; connection/transport happens when sending or when explicit connection operations are performed.

**"JavaMailSender only sends plain text?"**  
No. It can send `MimeMessage` objects containing HTML, alternative text, inline resources, and attachments. `SimpleMailMessage` is the simpler class meant for plain-text emails.

**"To send an HTML email, do I need to concatenate MIME boundary strings manually?"**  
No. `MimeMessageHelper` and Jakarta Mail build the MIME structure; manually creating boundary strings easily breaks encoding or part relationships.

**"Using setText(html, true) automatically includes a plain-text fallback?"**  
No. That only sets an HTML body. To have plain text and HTML coexist in `multipart/alternative`, use the `setText(plainText, htmlText)` overload with an appropriate multipart helper.

**"Does attaching a file mean using createMimeMessage(InputStream)?"**  
No. That overload reads **an existing MIME message**. Individual files are added via MIME APIs, typically `MimeMessageHelper.addAttachment(...)`.

**"Are the From header and SMTP MAIL FROM always identical?"**  
Not necessarily. The `From:` header is part of `MimeMessage`; the SMTP envelope sender may be determined by the mail transport from configuration/message settings and can differ from the displayed sender header, such as when using a dedicated bounce address.

**"send returning normally means the recipient has read the email?"**  
No. The message may only have been accepted by the SMTP server for processing; delivery and read status are separate later steps.

**"Using MimeMessagePreparator automatically sends in the background with retries?"**  
No. The callback prepares content inline within the send call; queuing, async execution, and retries must be designed independently.

## 13. Scenario Example from Business Logic to Complete Email

Suppose a project management system sends a weekly report. The business layer has a report ID, verified recipients, a PDF file, and an HTML template. An implementation can divide responsibilities as follows:

~~~text
ReportService
  ├── Verify permission to receive the report
  ├── Build content data (plain text / HTML)
  ├── Load PDF and logo from authorized sources
  └── Call WeeklyReportMailer
        ├── javaMailSender.createMimeMessage()
        ├── new MimeMessageHelper(... MIXED_RELATED ...)
        ├── setFrom / setTo / setSubject
        ├── setText(plain, html)
        ├── addInline(logo)
        ├── addAttachment(report.pdf)
        └── javaMailSender.send(message)
              └── Jakarta Mail SMTP transport
                    └── SMTP server accepts the message
~~~

This design makes clear:

- **Business service** decides *who may receive* and *what content is allowed to be sent*.
- **`JavaMailSender`** provides the message and triggers the send operation.
- **`MimeMessage`** is the email representation that can be inspected, serialized, and extended with MIME parts.
- **`MimeMessageHelper`** helps construct well-formed emails without manually managing boundaries/encoding.
- **Jakarta Mail and the SMTP provider** handle protocol, authentication, and the acceptance/relay step.

Clearly understanding the two operations **creating a `MimeMessage`** and **sending a `MimeMessage`** helps applications control content, inspect structure, handle errors at the right stage, and scale from simple text to HTML, inline images, or attachments. That is the central role of `JavaMailSender` in the Spring Framework Java Mail API.

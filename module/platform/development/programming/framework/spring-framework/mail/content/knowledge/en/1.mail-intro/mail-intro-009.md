# Components You Will Encounter in a Mail-Sending Module

In a Java application, email-sending functionality typically appears in workflows such as registration confirmation, password recovery, order notifications, or report delivery. With **Spring Framework Mail**, we can build this capability using a set of components with clear responsibilities: receiving requests from business logic, generating message content, constructing email messages, connecting to a mail server, and handling outcomes.

This lesson introduces a **map of the components** commonly found in a mail-sending module. The goal is to understand what each component does, how they collaborate, which components Spring provides, and which components the application builds itself. A small module does not need to have every class listed; architecture should grow incrementally according to real requirements.

## 1. What Does a Mail-Sending Module Actually Do?

An "email sending" action comprises several distinct stages:

1. **Request origination:** business logic decides whom to notify and for what reason.
2. **Data preparation:** retrieves recipient addresses, subject, data to populate message templates, and attachments if any.
3. **Message composition:** chooses plain-text, HTML, or multipart (MIME) messages.
4. **Message transmission:** uses a mail library to hand off the message to an SMTP server or another mail-sending service.
5. **Result recording:** records the send operation, classifies errors, and performs retries/monitoring when needed.

Typical flow diagram:

~~~mermaid
flowchart LR
    A["Business event / API / scheduled job"] --> B["Mail application service"]
    B --> C["Recipient data + content template"]
    C --> D["Create email: text or MIME"]
    D --> E["JavaMailSender"]
    E --> F["SMTP server / email provider"]
    F --> G["Recipient's mail server"]
    B -. "Record results, errors" .-> H["Log / status / metric"]
~~~

**Important distinction:** when the mail-sending method returns successfully, this normally only means the application handed the message off to the sending server and the server accepted that operation. It **does not guarantee** the email reached the inbox, was read, or avoided being classified as spam. Statuses such as delivered, bounced, and complained usually require dedicated feedback mechanisms from the provider.

## 2. Components Commonly Present in the Module

| Component | Role | Example | Required? |
| --- | --- | --- | --- |
| **Trigger source** | Decides when a message must be sent | Account registration, payment event, scheduled job | Must have a trigger source, though not necessarily a REST API |
| **Request/command or event** | Carries send information, decoupled from the calling protocol | `SendWelcomeEmailCommand`, `OrderPaidEvent` | Recommended when business logic is complex |
| **Application service** | Orchestrates the sending workflow, selects message type, and handles outcomes | `NotificationMailService` | Usually present |
| **Templates and template data** | Generates content suited to context, language, and branding | `welcome.html`, user name, confirmation URL | Depending on needs |
| **Message builder/composer** | Turns content into a standard email message | `SimpleMailMessage`, `MimeMessageHelper` | Present in some form |
| **Mail sender / transport adapter** | Sends the message to the mail server | `JavaMailSender`, `JavaMailSenderImpl` | Yes when using Spring Mail via SMTP |
| **SMTP config and sender identity** | Supplies host, port, authentication, encryption, From | `spring.mail.*`, `app.mail.from` | Yes when using SMTP |
| **Error and status tracking** | Knows which send failed and why | Logs, metrics, job status | Should be present |
| **Queue / worker / outbox** | Decouples sending from requests and supports reprocessing | Message broker, job queue | Depending on scale and reliability |
| **Testing and mock mail environment** | Verifies content and sending flow safely | Mock sender, Mailpit, GreenMail | Should be present in the project |

For a simple feature such as sending an internal notification, a service calling `JavaMailSender` directly is enough. When there are multiple message types, multiple providers, or a requirement not to lose send requests, you can add a composer, gateway, queue, and outbox.

## 3. Core Classes and Interfaces of Spring Mail

Spring provides the mail-sending API, whereas storing templates, deciding when to send, and handling business rules are typically designed by the application.

### 3.1. `MailSender` and `JavaMailSender`

- **`MailSender`** is the simple abstraction for plain-text messages in the form of `SimpleMailMessage`.
- **`JavaMailSender`** extends `MailSender` and adds the ability to create and send `MimeMessage`. This is the interface typically injected into services in modern Spring applications.
- **`JavaMailSenderImpl`** is the common SMTP implementation provided by Spring. When using Spring Boot with proper mail configuration, Boot can auto-create the sender bean; when using plain Spring Framework, the application can configure a `JavaMailSenderImpl` bean manually.

Viewing the relationship from a usage perspective:

~~~text
MailSender (interface)
  └── JavaMailSender (interface)
        └── JavaMailSenderImpl (SMTP implementation)

NotificationMailService
  └── depends on JavaMailSender, not directly on the implementation
~~~

Key takeaway: **services should depend on the interface** so configuration is easy to change and can be replaced with a fake implementation during testing.

### 3.2. `SimpleMailMessage`: Plain-Text Email

Spring's `SimpleMailMessage` suits simple text emails. It has fields such as sender, recipients, CC, BCC, subject, and plain-text body. This is **not** the message type meant for HTML or attached files.

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("customer@example.net");
message.setSubject("Registration confirmation");
message.setText("Your account has been created.");

mailSender.send(message);
~~~

### 3.3. `MimeMessage` and `MimeMessageHelper`: HTML, Multipart, Attachments

`MimeMessage` belongs to **Jakarta Mail** (`jakarta.mail.internet.MimeMessage`) and represents a MIME-standard email message. It supports HTML content, alternative parts (text/HTML), inline images, and file attachments.

`MimeMessageHelper` belongs to **Spring** (`org.springframework.mail.javamail.MimeMessageHelper`) and makes configuring `MimeMessage` easier: setting recipients, subject, encoding, text/HTML, and attachments.

~~~java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Your invoice");
helper.setText(
    "Your invoice is ready. Please see the attached content.",
    "<h1>Your invoice is ready</h1><p>Thank you.</p>"
);
helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);

mailSender.send(mime);
~~~

The example above sets alternative text and HTML bodies while attaching a PDF. This code requires a `pdfBytes` variable containing PDF data and handling `MessagingException` (the checked exception declared when configuring MIME). With `ByteArrayResource`, the file data already resides in memory; large files should be handled with appropriate storage strategies and size limits.

| Need | Commonly used component |
| --- | --- |
| Text-based notification | `SimpleMailMessage` + `JavaMailSender` |
| HTML content | `MimeMessage` + `MimeMessageHelper` |
| Alternative text and HTML | `MimeMessageHelper.setText(plainText, htmlText)` |
| File attachment | `MimeMessageHelper.addAttachment(...)` |
| Image displayed inside content | `MimeMessageHelper.addInline(...)` |

## 4. Components Built by the Application Itself

### 4.1. Trigger: Who Decides to Send?

A mail-sending module does not know on its own when a user just registered or an order was paid. That signal usually comes from:

- **Controller/API:** receives an authenticated request; suited for manual triggers or internal tools.
- **Application/domain service:** invokes mail sending after a business operation such as creating an account.
- **Event consumer:** receives a `UserRegistered` or `OrderPaid` event from another system.
- **Scheduler/batch job:** sends daily reports or scheduled reminders.
- **Queue worker:** processes send requests persisted in a queue.

A system that uses only an event consumer is still a complete mail-sending module even without a controller. Do not expose a public endpoint allowing outsiders to freely specify recipients and content, as it can easily be abused for spam.

### 4.2. DTOs, Commands, and Business Data

A command expresses the **intent to send** at the application level, such as `SendPasswordResetEmail(userId, resetLink)`. Normally, business logic supplies data (address, name, notification type, transaction ID); the mail service handles choosing templates and building the message.

Distinguish two levels of data:

- **Business data:** user ID, order ID, confirmation URL, desired language.
- **Email protocol data:** From, To, Subject, text/HTML body, attachments.

Domain services should not manually concatenate HTML strings, SMTP parameters, or retry logic. Doing so causes template or provider changes to unnecessarily impact business logic.

### 4.3. Template Renderer: Who Generates the Content?

If an email type has only a few lines, the service can build text content directly. If there are many email types or multi-language requirements, separate templates into dedicated resources:

~~~text
src/main/resources/
  templates/
    mail/
      welcome.html
      order-confirmed.html
      password-reset.html
~~~

A template engine like Thymeleaf can merge data into HTML before the composer creates a `MimeMessage`. Pass curated data, escape untrusted values appropriately for HTML/URL contexts, and never concatenate raw user input directly into markup. For important emails, also provide a plain-text version to support clients that do not render HTML.

### 4.4. Mail Application Service: The Central Orchestrator

The service receives the send request, performs basic validation, chooses how to construct the message, and invokes the sender. For a small module, it can be written directly as follows:

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendText(String to, String subject, String content) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(content);
        mailSender.send(message);
    }
}
~~~

The code above focuses on the **role of the component** and does not yet handle caller authentication, recipient address validation, duplicate-send prevention, retries, or status management. Those concerns belong in appropriate separate classes or are added when needed.

When SMTP may need to be swapped for a provider HTTP API, you can define an application-level interface such as `MailGateway` and supply an `SmtpMailGateway` implementation. When there is only one simple SMTP channel, injecting `JavaMailSender` directly remains reasonable.

## 5. Connection and Email Provider Configuration

### 5.1. Dependency

With **Spring Boot**, the commonly used starter is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The starter brings Spring Mail components and the required Jakarta Mail libraries into the application. Spring Boot supports configuring `JavaMailSender` via `spring.mail.*` properties when auto-configuration conditions are satisfied. In an application using plain Spring Framework, declare the mail dependency and configure the sender manually.

### 5.2. Example Configuration for SMTP Using STARTTLS

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
~~~

Meaning of the property groups:

| Configuration | Meaning |
| --- | --- |
| `host`, `port` | SMTP server and connection port |
| `username`, `password` | Authentication credentials as required by the provider |
| `mail.smtp.auth` | Enable SMTP authentication |
| `mail.smtp.starttls.enable` | Allow upgrading the SMTP connection to TLS using STARTTLS |
| `mail.smtp.starttls.required` | Require STARTTLS to succeed, avoiding continuing on an unencrypted connection |
| Timeouts | Limit connection, read, and write wait times to prevent indefinite hangs |
| `app.mail.from` | Application-managed From address, which must be permitted by the provider |

The example above uses port 587 following the common STARTTLS setup; actual values must follow the provider. When using SMTPS over port 465, direct TLS settings such as `mail.smtp.ssl.enable` must be configured according to provider guidelines. Do not blindly copy security properties between the two connection modes.

**Do not store SMTP passwords in source code or committed files.** They can be read from environment variables or a secret manager. In addition, the From address and sending domain usually require verification with the provider; putting an arbitrary address in code does not mean the server will accept sending on its behalf.

### 5.3. SMTP Server, Provider, and Message Delivery to Inbox

`JavaMailSenderImpl` sends emails through an SMTP server. The SMTP server may be self-operated by the organization or managed by a transactional email provider. Providers often additionally handle queuing, relaying, bounce feedback, and domain authentication support via SPF/DKIM/DMARC.

Distinguish clearly:

- **SMTP transport:** technical communication for submitting a message.
- **Mail provider:** the system that actually relays and tracks messages, potentially offering dashboards/webhooks/APIs.
- **Mail client:** Gmail, Outlook, or the app the recipient uses to view messages.

Spring Mail mainly addresses the **creation and sending** side. It does not build an inbox itself, manage bounces, guarantee Inbox delivery, or provide durable send history.

## 6. How Classes Are Organized in a Project

A structure that can be applied once a module has multiple email types:

~~~text
src/main/java/com/example/mail/
  api/
    MailAdminController.java          # Optional: internal API
    SendMailRequest.java              # Input and validation
  application/
    NotificationMailService.java      # Orchestrates sending workflow
    MailCommand.java                  # Send intent
  template/
    MailTemplateRenderer.java         # Generates text/HTML
  transport/
    SmtpMailGateway.java              # Wraps JavaMailSender interaction
  config/
    MailConfiguration.java            # Only when custom config is needed
  worker/
    MailJobConsumer.java              # Optional: consumes jobs from queue
src/main/resources/
  application.yml
  templates/mail/
~~~

This is an **illustrative structure**, not mandatory Spring package names. If there is no API, omit `api/`; if Spring Boot already configures the sender properly, do not recreate `MailConfiguration`; if the service is only a few lines, there is no need to extract `SmtpMailGateway` yet.

Principles for choosing boundaries:

| Class/component | What should it know? | What should it not take on? |
| --- | --- | --- |
| Business service / event producer | Why sending is needed, which business data is involved | SMTP host, port, MIME structure |
| Application mail service | Who receives, which email type, orchestration flow | Managing SMTP sockets directly |
| Template renderer | Presentation content and display variables | Retry policies, SMTP passwords |
| Composer / transport adapter | How to build and send messages per protocol | Business decisions on whether an email arises |
| Infrastructure config | SMTP host, security, credentials, timeouts | Email content for individual business cases |

## 7. Synchronous, Asynchronous, and Queued Sending

### 7.1. Synchronous Sending

~~~text
HTTP request → Business processing → mailService.send(...) → SMTP → HTTP response
~~~

The advantage is simplicity and easy traceability; suitable for internal tools or low traffic. The drawback is that the request must wait for the SMTP operation. If SMTP is slow or disrupted, the business flow can slow down or fail along with it.

### 7.2. Sending via Worker/Queue

~~~text
HTTP request → Save business data + create send request → Response
                                          ↓
                                     Queue / Job
                                          ↓
                                    Mail worker → SMTP
~~~

In this architecture, the request handler **records the job**, while a worker actually performs sending. A queue frees the request thread and provides a place for retries, rate limiting, or prioritized processing. If the send request must accompany a business transaction, a **transactional outbox** is an option: save the send event in the same transaction and let another process dispatch it, reducing the chance that business updates succeed while the mail request is lost.

Asynchronous sending does not automatically mean "the message was delivered". The API can return a status of **accepted for processing** and provide an ID for lookup; this status differs from **submitted to SMTP** and **delivered to mailbox**.

### 7.3. Retries and Duplicate Messages

Transient network errors or SMTP error codes may require retrying with backoff. However, if the server received the message while the client timed out before reading the response, retrying can produce **duplicate messages**. Therefore, critical systems need a request/event ID, application-side deduplication mechanisms, a maximum retry count, and a final status or dead-letter queue.

Do not retry all errors indefinitely. Invalid credentials, invalid recipient addresses, or provider policy violations usually require fixing configuration/data first, whereas transient errors can be retried.

## 8. Send Results, Exceptions, and Operational Observability

Errors in Spring Mail can be represented by the `MailException` (unchecked) hierarchy along with specific types such as `MailAuthenticationException`, `MailSendException`, or `MailPreparationException`. For MIME, creating/configuring messages can throw Jakarta Mail's `MessagingException`. Separate **message preparation**, **authentication**, **connection**, and **SMTP rejection** errors to decide how to handle them.

Useful information to record for each request:

- Business ID or send request ID, template type, creation timestamp, and attempt timestamp;
- processing status such as PENDING, PROCESSING, SUBMITTED, FAILED; normalized error code and attempt count;
- provider call duration, retry count, failure rate, and pending backlog size.

Avoid logging SMTP passwords, password reset tokens, sensitive message bodies, or full email addresses unnecessarily. If the provider offers bounce/delivery webhooks, you can update status **after submission** based on those events.

## 9. Testing Each Boundary

Different components lead to different testing approaches:

| Part to test | Appropriate approach | What to observe |
| --- | --- | --- |
| Application service | Mock/fake `JavaMailSender` or gateway | Was send called with the right recipients, subject, and content |
| Template renderer | Render template with sample dataset | Content/escaping, missing variables, locale/language |
| MIME composer | Build `MimeMessage` without sending over the Internet | Multipart layout, content type, attachments, encoding |
| SMTP connectivity | Mock SMTP server in local/test environment (e.g., Mailpit or GreenMail) | Application connects, authenticates, and submits messages |
| Worker/queue | Integration test with jobs and statuses | Retries, duplicate handling, attempt limits |

In development, a mock SMTP server lets you inspect emails without sending real messages to customers. Unit tests should also not depend directly on external SMTP services since they are both slow and prone to instability.

## 10. Common Misconceptions When Reading Mail-Sending Code

| Misconception | Accurate understanding |
| --- | --- |
| "Having `spring-boot-starter-mail` means you can send right away." | You still need a configured sender, available host/provider, credentials, connectivity, and a valid From address. |
| "`SimpleMailMessage` can send HTML." | It is meant for plain text; use MIME to create HTML and attachments. |
| "`MimeMessageHelper` is a mail-sending server." | It only helps construct the message; `JavaMailSender` does the sending. |
| "A mail-sending module must always have a REST controller." | It can be triggered from business services, events, schedulers, or workers. |
| "Not throwing an exception means the recipient read the message." | That confirms neither delivery nor read receipt. |
| "Enabling `@Async` gives you a reliable queue." | `@Async` only runs work on another thread; it does not by itself provide durable storage or retries across restarts. |
| "Just retry every SMTP error." | Errors must be categorized, capped, and handled for duplicate-send risks. |

## 11. Putting the Components Together in a Concrete Scenario

Suppose the application needs to send a confirmation message after a user registers:

1. **User service** completes registration and emits a `SendWelcomeEmailCommand` with the user ID and required details.
2. **NotificationMailService** selects the "welcome" template, obtains the recipient email, and builds data for the template.
3. **Template renderer** generates text/HTML parts. Content includes the user's name properly escaped.
4. **Composer** creates a `MimeMessage`, adds subject, From, To, and body using `MimeMessageHelper`.
5. **`JavaMailSender`** submits the message to the SMTP provider over the configured connection.
6. **Result recording mechanism** persists whether the attempt succeeded or failed; a worker/queue handles follow-up if the architecture requires retries.

Through this example, three main groups can be identified when reading any mail module's code:

- **Application decides what to send, to whom, and when**: triggers, commands, application services, templates.
- **Spring/Jakarta turns the request into an email and sends it**: `SimpleMailMessage` or `MimeMessage`, `MimeMessageHelper`, `JavaMailSender`.
- **Infrastructure ensures the operation runs reliably**: SMTP configuration, provider, timeouts, status tracking, queues/retries, and monitoring as needed.

Grasping the boundaries among these groups will make reading project structure easier and help you know exactly where to make changes when requirements arise to update message templates, add attachments, switch SMTP servers, or upgrade the sending mechanism.

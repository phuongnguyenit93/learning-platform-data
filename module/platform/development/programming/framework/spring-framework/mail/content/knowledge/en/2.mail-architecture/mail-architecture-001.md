# Message User Agent (MUA) and Where Users Compose Emails

## 1. What Is an MUA and Why Does Understanding Its Role Matter?

In email architecture, a **Message User Agent (MUA)**, also commonly called a **Mail User Agent**, is the component that users interact with to **compose, request sending, read, reply to, forward, and manage emails**. The MUA is the touchpoint between humans and the email system. The word "agent" describes its role of acting on the user's behalf to perform mail operations; it does not mean an AI agent.

Some familiar examples:

- **Desktop email clients:** Mozilla Thunderbird, Microsoft Outlook in email client mode, Apple Mail.
- **Mobile email apps:** the Mail or Gmail app on mobile devices.
- **Webmail:** the compose interface of Gmail, Outlook in a browser, or an enterprise webmail system.
- **Custom-built email UIs:** a "Contact Us", "Send Report", or "Compose Notification" screen in an application; depending on the architecture, this UI plays a composition role similar to an MUA, while the backend performs the sending step.

The core function of an MUA in this lesson is **where the sender prepares a message before handing it off to the mail transport infrastructure**. Users see recipient addresses, subject, body, and attachments; whereas the SMTP protocol, relay servers, MX records, and mail stores typically operate in the layers behind it.

> **Key takeaway:** Users **compose** an email in an MUA; the MUA or a backend acting on behalf of the MUA **submits** the email to a sending service; mail servers then **relay and deliver** the message to the recipient's mailbox. These three actions are distinct steps.

## 2. Where Does the MUA Sit in Email Architecture?

A general model:

~~~mermaid
flowchart LR
    U["Sender"] --> A["MUA: where the email is composed"]
    A -->|"Submit mail via SMTP or API/HTTPS"| S["MSA: accepts outgoing mail"]
    S --> T["MTA: relays mail"]
    T --> D["Destination mail system: receives and stores mail"]
    D --> R["Recipient's MUA"]
    R --> V["Recipient reads mail"]
~~~

Common acronyms you will encounter:

| Component | Full Name | Main Responsibility | Relationship to MUA |
| --- | --- | --- | --- |
| **MUA** | Message/Mail User Agent | User interface and logic for user email operations | Where the user composes or reads mail |
| **MSA** | Mail Submission Agent | Accepts outgoing mail from applications, checks sending policies, and hands it off to the mail system | Receiving endpoint for send requests from an MUA or backend |
| **MTA** | Mail Transfer Agent | Routes and relays mail between mail systems over SMTP | Usually does not interact directly with end users |
| **MDA** | Mail Delivery Agent | Delivers mail to the destination mailbox/mail store | Prepares mail so the recipient can access it |
| **Mail store / mailbox** | Mail store / mailbox | Stores received mail, sent mail, and drafts depending on the system | Accessed by the MUA to display and manage mail |

This is a model of **logical roles**, not necessarily five separate programs or five separate servers. A single email service can combine MSA, MTA, storage, and APIs on the same platform. Webmail can also use HTTPS from the browser to the backend instead of having the browser connect directly via SMTP.

When a recipient opens an email, the MUA can retrieve data via **IMAP**, **POP3**, or a provider's **API/HTTPS**. Those protocols serve mailbox access, whereas SMTP primarily serves mail submission and transport.

## 3. What Exactly Does a User Compose in an MUA?

A compose screen typically consists of the following fields:

| Screen Field | Meaning | When Building the Email Message |
| --- | --- | --- |
| **From** | Displayed sender identity | Usually becomes the `From` header; the sending account/domain must be authorized by the system |
| **To** | Primary recipients | `To` header and addresses to be delivered to |
| **Cc** (Carbon copy) | Copy recipients visible to other recipients | `Cc` header and addresses to be delivered to |
| **Bcc** (Blind carbon copy) | Hidden copy recipients | Delivery recipients, but Bcc information is not exposed in copies sent to other recipients |
| **Subject** | Summary topic of the content | `Subject` header |
| **Body** | Plain text or HTML content | One or more body parts of the message |
| **Attachments** | Attached files | Packaged as MIME parts |
| **Reply-To** | Preferred address when the recipient chooses "Reply" | `Reply-To` header, which can differ from `From` |

Example of a user composing an email:

~~~text
From:      System Notifications <notifications@example.com>
To:        lan@example.net
Cc:        team@example.net
Bcc:       quan@example.org
Subject:   Weekly report is ready

Hi Lan,

The weekly report has been compiled. Please see the attached file.

Best regards,
Operations Team

Attachment: weekly-report.pdf
~~~

When sending, the system needs to deliver the message to Lan, the Cc group, **and** Quan. However, regular recipients **do not see** Quan's Bcc address in the message headers they receive. Bcc should not be misunderstood as an anonymization mechanism from the mail server itself: the delivery infrastructure still must know which addresses need to receive the message.

### 3.1. A Draft Is Not Yet a Sent Email

While the user types the subject and body, the data may still reside only in application memory. If the MUA has a "Save draft" feature, the application may store the data in a draft store or database. No delivery request has to happen at this stage.

Depending on the platform, a user can:

1. Compose and save drafts multiple times.
2. Attach or remove files.
3. Choose **Send** or schedule sending.
4. Receive a notification that the application has accepted the request.
5. View the send result, or receive a delivery failure email later.

When an MUA displays "Sent", it usually means the send operation was accepted for processing by the application or provider; it **does not by itself prove** that the email reached the Inbox, was opened, or was read.

### 3.2. An Email Is More Than a Display String

An outgoing message has **headers** (metadata), a **body**, and possibly multiple **MIME** parts. MIME (Multipurpose Internet Mail Extensions) supports character encoding, HTML content, multiple content representations, and attachments.

Illustrative example of a plain-text message after being constructed:

~~~text
From: Notifications <notifications@example.com>
To: lan@example.net
Subject: Weekly report
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hi Lan,
The weekly report is ready.
~~~

This is a **structural illustration**, not a complete capture of every real-world email. Sending applications and mail servers can also add headers such as `Date`, `Message-ID`, and tracing information.

If a message contains both text and HTML content, the MUA can use `multipart/alternative` to provide two ways to display it. If there are attachments, the message can use `multipart/mixed`; each file becomes a MIME part with a filename, content type, and suitably encoded data. Users do not need to write these MIME boundaries manually: mail libraries typically generate them.

## 4. From Clicking "Send" to Leaving the MUA

Consider an example of a user sending from a desktop email client:

~~~mermaid
sequenceDiagram
    actor User as User
    participant MUA as MUA
    participant MSA as Submission Server
    participant MTA as Relay Server
    participant Box as Recipient Mailbox

    User->>MUA: Enter To, Subject, Body, attachments
    MUA->>MUA: Create draft and MIME structure
    User->>MUA: Click Send
    MUA->>MSA: Submit message, authenticate if needed
    MSA-->>MUA: Accept or reject request
    MSA->>MTA: Hand off accepted message
    MTA->>Box: Transport and deliver
    Note over MUA,Box: Acceptance by MSA does not guarantee the mail was read
~~~

### 4.1. Submission and Relay Are Different

SMTP is used in both **mail submission** and **mail relay**, but the connection roles differ:

- **Submission:** the MUA or sending application connects to the outgoing mail acceptance service (MSA). A common configuration is SMTP submission on port **587** with STARTTLS; many providers support port **465** with TLS from the start. The connection usually requires authentication per the provider's policy.
- **Relay / transfer:** mail servers forward messages to other servers, typically over SMTP port **25**. Users do not need to connect directly to every recipient's MX server.
- **Reading mail:** the recipient's MUA uses a mailbox access protocol/API, such as IMAP over TLS on port **993** or a webmail interface over HTTPS.

These port numbers are common defaults, not immutable rules: a provider may impose its own connection and authentication requirements. The MUA must use the exact configuration of the mail system in use.

### 4.2. Message Headers and the SMTP "Envelope" Are Not the Same Thing

Readers see fields such as `From` and `To` in the message headers. During SMTP transport, the system also uses the **SMTP envelope** to know the bounce return address and the delivery destinations:

~~~text
MAIL FROM:<bounce@example.com>
RCPT TO:<lan@example.net>
RCPT TO:<team@example.net>
RCPT TO:<quan@example.org>
DATA
From: notifications@example.com
To: lan@example.net
Cc: team@example.net
Subject: Weekly report

Message body...
.
~~~

The example shows:

- `MAIL FROM` is the envelope address used for sending/bounce reporting; it can differ from the `From` header the reader sees.
- Each `RCPT TO` identifies a delivery destination. This list can include Bcc recipients.
- The headers displayed to Lan and the team do not need to contain Quan's Bcc address.
- SMTP is a message transfer protocol; the lines above only illustrate the conversation session and omit handshakes, authentication, TLS, and many other details.

Confusing these two layers often leads to the question: "Why does SMTP still need RCPT TO when the email already has a To field?" The reason is that **headers serve message presentation**, while the **envelope serves delivery routing**.

## 5. Traditional MUAs, Webmail, and Application UIs

Not every place with a "Compose email" button connects to SMTP the same way.

### Case A: Desktop Email Client

For example, Thunderbird displays a composer, manages drafts, packages MIME, and connects to a configured submission server. In this case, the desktop app is a fairly classic MUA.

~~~text
User → Thunderbird (MUA) → SMTP submission (MSA) → mail system
~~~

### Case B: Webmail in a Browser

With Gmail or a webmail system, the browser displays the compose form. When Send is clicked, the frontend typically calls the provider's backend over **HTTPS**. The backend then performs the necessary steps for the message to be accepted into the transport service; the browser does not necessarily open an SMTP connection.

~~~text
User → Webmail UI → HTTPS → mail backend → transport system
~~~

Thus, the **MUA experience** can span both a web interface and a service backend. You should not equate "MUA" solely with an installed desktop application or assume that every Send button calls SMTP directly from the browser.

### Case C: "Send Notification" Form in a Spring Application

An internal system has a form where employees enter recipient addresses, a subject, and a body. The frontend provides the composition experience; the Spring application receives the request, determines an authorized sender identity, builds a MIME message, and calls an SMTP service or email API.

~~~text
User
   ↓ composes message
Frontend: Send Notification page
   ↓ HTTPS, form data
Spring Backend: validates and builds message
   ↓ JavaMailSender / mail sending service
MSA or email provider
   ↓
Recipient
~~~

In this case, **Spring Mail provides programmatic capabilities to build and send emails on the server side**, while whatever the user sees must be built by the application or a webmail product. Spring Framework Mail itself is neither a compose UI nor a mailbox hosting service.

## 6. How Does Spring Framework Mail Relate to an MUA?

Spring Framework provides mail APIs such as `MailSender`, `JavaMailSender`, `SimpleMailMessage`, and `MimeMessageHelper`.

| API / Class | Purpose | Relationship to Composition |
| --- | --- | --- |
| `SimpleMailMessage` | Represents a simple plain-text email | Sets recipients, sender, subject, text body |
| `MailSender` | Simple mail-sending contract in Spring | Sends `SimpleMailMessage` instances |
| `JavaMailSender` | Spring API integrating Jakarta Mail for MIME messages | Creates `MimeMessage` and sends emails, including HTML/attachments |
| `MimeMessage` | Jakarta Mail MIME message | Carries headers, body, and content parts |
| `MimeMessageHelper` | Convenient helper for populating `MimeMessage` | Sets To/Cc/Bcc, Subject, text/HTML, attachments, etc. |

**Separation of responsibilities to keep clear:**

1. **Frontend or MUA** captures the user's composition intent.
2. **Business backend** decides the authorized sender, allowed recipients, content, and sending timing.
3. **Spring Mail/Jakarta Mail** constructs the message and connects to the configured sending infrastructure.
4. **Mail server/provider** accepts, routes, and performs delivery.

Sometimes a Spring application **has no direct human composer**, such as when sending account verification emails or error alerts when a job runs. These are application-generated automated emails. Architecturally, Spring code acts as a **message generation and submission component**, without turning the entire backend into a human-facing MUA.

### 6.1. Spring Example: Backend Receives Composed Content and Sends a Text Email

The following example uses Spring Framework 6 / Jakarta Mail with a service injected with `JavaMailSender`. The `From` address is predefined by the system; user-supplied values should only be processed after authentication, authorization, and input validation in the calling layer.

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendComposedMessage(
            String recipient,
            String subject,
            String body) {

        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    false,
                    StandardCharsets.UTF_8.name());

            helper.setFrom("notifications@example.com");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(body, false); // false = plain text, not HTML

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Unable to prepare email message", ex);
        }
    }
}
~~~

In the example:

- The user **composes** `recipient`, `subject`, and `body` in a UI provided by the application.
- The service creates a `MimeMessage` and maps authorized data into the email structure.
- `MimeMessageHelper` handles building headers and content, including setting UTF-8.
- `JavaMailSender.send(...)` requests the mail infrastructure to send the message; sending errors from Spring are typically represented by exceptions in the `MailException` hierarchy (runtime), in addition to `MessagingException` when preparing the message.
- The example does not create a compose UI, an email account, or a receiving mailbox. Running it in practice requires configuring `JavaMailSender` and a valid SMTP service.

In a **Spring Boot** application, a sample configuration for SMTP submission might look like:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: username-from-secure-config
    password: password-from-secure-config
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
~~~

This is a structural configuration example, not a working SMTP account. In real deployments, obtain credentials from environment variables or a secret management system, use an authentication method supported by the provider, and ensure the `From` address is authorized to send. `spring.mail.*` is a convenient configuration mechanism of **Spring Boot**; in a plain Spring Framework application, developers may need to declare a `JavaMailSenderImpl` bean and equivalent configuration.

### 6.2. When HTML and Attachments Are Needed

For HTML content, you can use `helper.setText(html, true)`; for both plain-text and HTML versions, use the method overload that supports both content versions. For attachments, create `MimeMessageHelper` in multipart mode and add the attachment from an appropriate data source. Conceptual example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, StandardCharsets.UTF_8.name());

helper.setFrom("notifications@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Weekly report");
helper.setText(
        "The weekly report is ready.",
        "<p>The weekly report is <strong>ready</strong>.</p>");
helper.addAttachment("weekly-report.pdf", pdfResource);

mailSender.send(message);
~~~

The illustration assumes `pdfResource` is a valid `InputStreamSource`/`Resource` created from a report file owned by the application. For stream-based attachments, the data source must satisfy Jakarta Mail's re-readability requirement when needed. The application must also limit sizes, validate content/filenames, and never automatically attach arbitrary files based on a client-supplied path.

**Note:** Using HTML for rich formatting does not mean an MUA or receiving client will execute JavaScript from an email. Many email clients strictly filter HTML, CSS, remote images, and active content. For transactional emails, you should provide a plain-text version and avoid relying on web features that are not consistently supported.

## 7. Boundary Between User-Entered Content and Sender Identity

An MUA may allow users to choose a sending account or alias, but the backend and mail server must still enforce policy. For example, a public form should not let any visitor arbitrarily assign:

~~~text
From: ceo@company.example
~~~

if they do not have permission to use that identity. The `From` header is only one part of the message; SMTP account authentication, permission to send from the domain, provider policies, and sending-domain protection mechanisms (SPF, DKIM, DMARC) all participate in determining the message's validity and trustworthiness.

For a "Contact Us" form, a common design is:

- `From`: a verified or system-managed address, such as `contact-form@example.com`.
- `Reply-To`: the contact's address, after validating format and usage policy.
- `To`: an internal support mailbox configured by the server.
- `Subject` and `Body`: content sanitized/validated before creating the email.

This approach allows the recipient to click "Reply" to respond directly to the contact while keeping the sending identity within authorized bounds.

### Key Points When Designing a Composition UI

| Concern | How to Handle |
| --- | --- |
| **Input data** | Limit length, number of addresses, attachment size; reject invalid values before building the message |
| **Sending permissions** | Define which users/jobs may send to which recipient groups; do not trust permissions claimed by the frontend |
| **Headers and identity** | Populate sensitive fields like `From` from configuration or verified identities; use library APIs instead of concatenating header strings manually |
| **HTML** | Escape data when building HTML and control templates; do not insert arbitrary user HTML into emails as trusted content |
| **Attachments** | Validate file type, size, content, and access permissions; do not expose or log sensitive data |
| **SMTP credentials** | Store on the backend and in an appropriate secret source; use TLS and an authentication mechanism accepted by the provider |
| **Bulk sending / resending** | Apply rate limiting and business-level deduplication, especially when retrying after a timeout |
| **Send status** | Distinguish between "request accepted", "accepted by SMTP", "delivered", and "read by recipient" |

In high-volume sending systems, clicking Send in the MUA or frontend may only enqueue a job. A backend worker then calls the provider. This does not change the MUA's position in the model: **where the email is composed remains at the start of the flow**, while delivery is a downstream process.

## 8. Common Misconceptions

**"Is the MUA the SMTP server?"**  
No. The MUA serves the user and prepares/requests sending mail; the SMTP server in the MSA/MTA role accepts, validates, and transfers mail. A single product may integrate multiple roles, but they remain distinct responsibilities.

**"Once an email is composed, is it already sent?"**  
No. Text may exist only in a form or draft. Sending is a separate step that can succeed, be rejected, or require deferred processing.

**"Does webmail have no MUA because the browser doesn't speak SMTP?"**  
No. Webmail still provides MUA functionality. The browser-to-backend connection can use HTTPS; SMTP is handled by the service behind it.

**"Does Spring Framework Mail automatically create a Gmail-like Compose UI?"**  
No. Spring Mail is an API for developers to build and send messages. If users need to type and manage drafts, the application must provide the corresponding UI and business logic.

**"Is an address in `To` enough for the mail transfer server?"**  
No. SMTP also uses envelope recipients (`RCPT TO`). The delivery list can include Cc/Bcc addresses, while headers determine most of the information the reader sees.

**"Does a successful send mean the recipient read the email?"**  
No. A submission server's acceptance response, delivery reports, and read status are different signals; read status generally cannot be reliably inferred from SMTP.

## 9. Tracing a Scenario End-to-End

Suppose a project management system has a "Send weekly report to team" button.

1. **The user selects recipients and composes a note.** This is the MUA-like experience; the frontend may save drafts.
2. **The user clicks Send.** The frontend sends the form data over HTTPS to the Spring backend.
3. **The backend validates the request.** The system verifies the caller has permission to send the report, selects an authorized `From` address, and fetches the appropriate PDF.
4. **Spring Mail builds the message.** `JavaMailSender` with `MimeMessageHelper` sets To/Cc/Bcc, Subject, body, MIME, and attachment.
5. **The system submits the mail.** SMTP submission or an email API service accepts the request, authenticates, and enforces sending policies.
6. **The mail infrastructure transfers the message.** Transfer servers route it to the recipient's system; the message may be accepted, deferred, rejected, or filtered.
7. **The recipient opens their mailbox.** Their MUA accesses the mailbox and displays the subject, body, and attachment.

Here, **one MUA or composition UI appears on the sender's side**; **another MUA appears on the recipient's side**. Spring Framework Mail sits at the backend step that constructs and submits the message, bridging the user experience with the email infrastructure. Understanding this boundary helps you design the right UI, APIs, SMTP configuration, error handling, and interpretation of send status.

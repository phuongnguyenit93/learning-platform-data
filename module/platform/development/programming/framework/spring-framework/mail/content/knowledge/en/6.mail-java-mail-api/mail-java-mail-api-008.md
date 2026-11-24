# Checking Message State Before Sending

A Spring application can create a `MimeMessage` object, set recipients, subject, HTML body, and attachments, and then call `JavaMailSender.send(...)`. If a recipient is missing, the subject is blank, content is malformed, or an attachment is inaccessible, an error can occur right at send time; sometimes the send request even has to be reprocessed. Therefore, **checking message state before sending** helps catch certain errors early at the boundary between business code and email infrastructure.

We must understand the exact meaning of **state** here: `MimeMessage` has no built-in flag meaning "ready", "sent", or "delivered". This object is **a data model of a MIME message**. Before sending, the application can check **the completeness and validity of required fields**, **content preparation readiness**, and **business rules**. After sending, the application must manage processing status and delivery tracking through other mechanisms.

This lesson focuses on what can be observed and verified **prior to the send call** when using **Spring Framework Mail and the Jakarta Mail API**, while explaining the boundaries of each check.

## 1. "Message State" Can Have Three Different Meanings

In an email-sending system, people often use the same word *status* for three distinct questions:

| Question | Related data | Can it be known before sending? |
| --- | --- | --- |
| **Is the message finished preparing?** | Sender, recipients, Subject, body, MIME parts, attachments, and business rules | **Mostly checkable**, via application data and message APIs |
| **Has the message been submitted to the SMTP server?** | Execution outcome of `JavaMailSender.send(...)`, SMTP reply, connection/auth errors | **Not yet**, because the send operation has not happened |
| **Has the message reached the recipient?** | Bounces, delivery events, status at the provider, receiving system | **No**, even after `send(...)` returns normally |

For example, a message may have a sender and recipient but no body. It can be considered **not ready per product requirements**. Conversely, a message with complete data that serializes to MIME cleanly can still be rejected by the SMTP server because the account is not permitted to send or because of recipient policies.

A helpful mental model:

~~~mermaid
flowchart LR
    A["Business data"] --> B["Create MimeMessage"]
    B --> C["Pre-send checks"]
    C -->|"Meets requirements"| D["JavaMailSender.send"]
    C -->|"Missing/invalid data"| E["Reject send request creation"]
    D --> F["SMTP relay accepts or returns error"]
    F --> G["Later delivery and feedback"]
~~~

Pre-send checks sit at node **C**. They help reduce errors detectable early, rather than replacing steps **D**, **F**, or **G**.

## 2. Lifecycle of a MimeMessage Before and After Sending

When using `JavaMailSender`:

1. Call `createMimeMessage()` to create a new MIME message.
2. Populate fields using `MimeMessageHelper` or directly via `MimeMessage`.
3. Validate business data and the headers/recipients that were set.
4. Optionally call `saveChanges()` to finalize certain MIME headers when inspecting/serializing the message.
5. Call `send(message)` to connect to the configured SMTP server and submit the email.
6. The application records the send outcome, manages retries, and tracks downstream delivery events if needed.

An **application-layer** state diagram could be named as follows:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: Create send request
    DRAFT --> PREPARED: Build MIME and validate data
    DRAFT --> INVALID: Validation failed
    PREPARED --> SUBMITTING: Call JavaMailSender.send
    SUBMITTING --> ACCEPTED: SMTP submission succeeded
    SUBMITTING --> FAILED: Send error or uncertain outcome
    ACCEPTED --> DELIVERED: Evidence from provider
    ACCEPTED --> BOUNCED: Bounce feedback received
~~~

**`DRAFT`, `PREPARED`, `SUBMITTING`, `ACCEPTED`, `DELIVERED`, and `BOUNCED` are application-defined state names**, not built-in enums or properties on `MimeMessage`. A simple application sending mail immediately may not need to persist this full lifecycle; systems with queues or audit requirements typically need dedicated state tracking.

### There Is No Standard `message.isSent()` Method

Jakarta Mail `Message` and `MimeMessage` provide getters/setters for content and metadata. They do not provide a standard getter that can assert an email was received by the SMTP server or reached an Inbox.

A few APIs that commonly cause confusion:

- `getSentDate()` reads **the sent date recorded in the message header** if present; this value may have been set by the application itself. It **does not prove** SMTP sent it successfully.
- `getMessageID()` reads the `Message-ID` header if present. This ID is often generated when finalizing the message, yet **having an ID does not mean the message was sent**.
- `getFlags()` belongs to message flags like `SEEN`, `ANSWERED`, or `FLAGGED` when working with messages in a mail folder; it is **not a measure of SMTP sending status**.
- `getSize()` may return `-1` when size is unknown; you cannot use a "valid" size value to infer deliverability.

Name pre-send checks clearly: **`validatePreparedMessage`**, **`checkMailRequest`**, or **`verifyMessageMetadata`**, rather than calling them `isSent`.

## 3. Fields Worth Inspecting Before Sending

To evaluate whether a notification email is ready, first define **product rules**: who the email must go to, which sender is allowed, what content is required, and what data must be protected.

Only then read fields from the message.

| What to inspect | Commonly used API | What can be concluded |
| --- | --- | --- |
| Displayed sender | `getFrom()` | Whether a sender address has been assigned to the object |
| To recipients | `getRecipients(Message.RecipientType.TO)` | Whether addresses exist in the To field |
| Cc recipients | `getRecipients(Message.RecipientType.CC)` | Which copied addresses are present |
| Bcc recipients | `getRecipients(Message.RecipientType.BCC)` | Which blind-copied addresses are present |
| All recipients | `getAllRecipients()` | Whether at least one destination address visible to Jakarta Mail exists |
| Subject | `getSubject()` | Subject value returned by the library |
| Reply address | `getReplyTo()` | Whether the Reply-To header has been set |
| Content type | `getContentType()`, `isMimeType(...)` | Current MIME descriptor or body type represented by the library |
| Timestamp on message | `getSentDate()` | Time header, **not a send outcome** |
| Message identifier | `getMessageID()` | Header ID if already generated/set, **not a delivery receipt** |

Many getters can return **`null`** when a field has not been set; MIME getters can also throw `MessagingException` when inspecting the message. Validation code must handle both cases.

**There is no universal set of "required" fields across all systems.** For instance, an automated notification email may not need `Reply-To`; a transactional email may require To and Subject matching a template; an internal Bcc mail may follow different rules. Define the validation contract based on the email's purpose.

## 4. Checking Sender and Recipients

### 4.1. The Sender Must Belong to an Authorized Identity

An application may call:

~~~java
helper.setFrom("notice@example.org");
~~~

And then read back:

~~~java
Address[] from = message.getFrom();
~~~

If `from == null` or the array is empty, the message may not have a displayed sender assigned per the application's contract. However, **`From` in MIME differs from the envelope sender address** used in SMTP `MAIL FROM`. Jakarta Mail/the SMTP provider may apply separate rules to the envelope sender; the provider may even rewrite or reject an unverified From address.

Hence, checking address syntax is only part of the picture. The application must also know which sending addresses are **permitted by the SMTP account or provider**. Actual permission to send is only confirmed by the service/infrastructure side.

### 4.2. Checking That Recipients Exist

With a constructed message, you can read:

~~~java
Address[] recipients = message.getAllRecipients();

if (recipients == null || recipients.length == 0) {
    throw new IllegalArgumentException(
            "Email requires at least one recipient"
    );
}
~~~

`getAllRecipients()` aggregates destination addresses across `TO`, `CC`, and `BCC` in the message. If business rules require at least one explicit **To** recipient, inspect `TO` directly rather than only the combined array.

An email with Bcc recipients and no To recipient may suit certain notification scenarios, yet many apps block that pattern to curb misdirected sends. That is an application-defined rule.

### 4.3. Checking Address Syntax with InternetAddress

Jakarta Mail provides `InternetAddress` to parse and check address **syntax**. Example function requiring a single mailbox address:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public static InternetAddress parseOneMailbox(String raw)
        throws AddressException {

    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException(
                "Email address cannot be blank"
        );
    }

    InternetAddress[] addresses =
            InternetAddress.parse(raw, true);

    if (addresses.length != 1) {
        throw new IllegalArgumentException(
                "Only one email address is allowed"
        );
    }

    InternetAddress address = addresses[0];
    address.validate();
    return address;
}
~~~

`parse(..., true)` enables strict parsing, and `validate()` checks structural validity within the scope supported by Jakarta Mail.

**Validating an address does not verify that the mailbox exists.** A syntactically valid address can still belong to a domain that does not accept mail, a nonexistent mailbox, a disabled account, or one rejected by the provider. Probing or MX lookups do not yield an absolute guarantee of deliverability either.

For emails built from user input, validate addresses **upon receiving the input** and re-check critical conditions before sending if the data could have changed.

## 5. Checking Subject and Message Content

### 5.1. Is the Subject Prepared Correctly?

`getSubject()` returns the Subject string in an application-friendly form. Example:

~~~java
String subject = message.getSubject();

if (subject == null || subject.isBlank()) {
    throw new IllegalArgumentException(
            "Notification email must have a Subject"
    );
}
~~~

Jakarta Mail may encode Unicode Subjects into MIME encoded-words when building the message. **The application should check the logical content of the Subject**, such as "Order confirmation A102", rather than comparing against a specific raw header string like `=?UTF-8?B?...?=`.

Be careful if the Subject is built from external data: enforce business length limits, avoid embedding sensitive tokens, and prevent improper control characters (especially CR/LF) from entering hand-crafted headers. Use the `setSubject(...)` API instead of concatenating raw header lines.

### 5.2. Is the MIME Content-Type Appropriate?

For a simple message:

~~~java
helper.setText("Your order has been confirmed.", false);
~~~

The body is typically built as plain text. If the application sets:

~~~java
helper.setText("<p>Your order has been confirmed.</p>", true);
~~~

the body is configured as HTML content. You can inspect it with:

~~~java
boolean isPlain = message.isMimeType("text/plain");
boolean isHtml = message.isMimeType("text/html");
String contentType = message.getContentType();
~~~

However, emails with attachments typically have **`multipart/mixed`** at the outer level; HTML emails with inline images may have **`multipart/related`** and nested parts inside. Consequently, `message.isMimeType("text/html")` can return `false` even when **a nested child part** contains HTML. Looking only at the outer Content-Type neither proves the entire structure is right nor confirms the body is non-empty.

### 5.3. Do Not Treat Content-Type as Proof of a Non-Empty Body

Some APIs may expose a default Content-Type value even when the body has not been fully populated. Likewise, `getContent()` may decode/read content, construct multipart objects, or access underlying data sources.

When business logic only needs to ensure the content string is non-empty, the simplest and clearest way is **validating inputs before placing them into the message**:

~~~java
static String requireBody(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(
                "Email body cannot be blank"
        );
    }
    return text;
}
~~~

Then call:

~~~java
helper.setText(requireBody(body), false);
~~~

For templated HTML, validate input data, the rendering step, and the resulting HTML before adding it to the message. A valid `text/html` header does not mean the HTML matches UI expectations, is properly escaped, or contains all required business data.

## 6. Handling Multipart and Attachments

A message with attachments can consist of multiple MIME parts:

~~~mermaid
flowchart TD
    A["MimeMessage"] --> B["multipart/mixed"]
    B --> C["Body: text/plain or text/html"]
    B --> D["Attachment: invoice.pdf"]
    B --> E["Attachment: terms.txt"]
~~~

When using `MimeMessageHelper`:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText("<p>Your invoice</p>", true);
helper.addAttachment("invoice.pdf", invoiceResource);
~~~

The `MimeMessage` object describes the MIME structure, yet **whether the file content is readable** still depends on `invoiceResource`. The file could be deleted, have permissions changed, or become corrupted between preparation and serialization.

Validate the attachment source before adding it to the message:

~~~java
import org.springframework.core.io.Resource;
import java.io.IOException;

static void requireAttachment(Resource resource)
        throws IOException {

    if (resource == null
            || !resource.exists()
            || !resource.isReadable()) {
        throw new IllegalArgumentException(
                "Attachment cannot be read"
        );
    }

    long size = resource.contentLength();
    long maxBytes = 10L * 1024 * 1024;

    if (size <= 0 || size > maxBytes) {
        throw new IllegalArgumentException(
                "Invalid file size"
        );
    }
}
~~~

This is merely **an illustrative rule** for a resource expected to be a regular file. Some stream-based data sources do not know their length upfront, or do not support being read multiple times. In real applications, choose a `Resource`/`InputStreamSource` compatible with Jakarta Mail and provider limits; specifically, attachment sources should be re-readable when the library performs serialization.

Additional product-dependent considerations:

- Total email size after MIME encoding can be **larger** than the original file size, especially with Base64.
- Attachment filenames must be normalized, avoiding paths or unintended control characters.
- User-supplied MIME types may not match the actual file contents.
- Malware scanning and allowed-file-type checks are security responsibilities of the application or dedicated scanning services.
- For mutable resources, checking `exists()` before sending **does not guarantee** it still exists when the program actually reads the data.

Thus, checking message metadata and checking attachment resources complement each other.

## 7. Role of saveChanges() Before Sending

`MimeMessage.saveChanges()` is an important Jakarta Mail method. On a newly constructed message, it can update required MIME headers, such as content-structure metadata or `Message-ID`. It also allows the build/serialization process to surface certain previously hidden errors.

Example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setTo("an@example.net");
helper.setFrom("notice@example.org");
helper.setSubject("New notification");
helper.setText("Hello!", false);

// Finalize MIME changes so headers can be inspected.
message.saveChanges();

String messageId = message.getMessageID();
String contentType = message.getContentType();
~~~

### saveChanges() Does Not Send the Email

This call:

- **Does not connect to the SMTP relay merely by being called.**
- **Does not perform SMTP authentication or transmit mail over the network.**
- **Does not guarantee all attachments will be readable at later send time.**
- **Does not prove the recipient exists or that the email is deliverable.**

It is a **MIME message preparation/update** operation, not a send action.

### Is Calling saveChanges() Manually Required?

Normally **no**, if the goal is simply sending a regular `MimeMessage` via `JavaMailSender.send(...)`. The sender implementation is responsible for preparing the message appropriately prior to transmission.

Calling `saveChanges()` is useful when you want to **inspect finalized headers, export MIME in tests, or prepare the message in a separate phase**. However, it can mutate metadata; do not treat calling it repeatedly as a completely side-effect-free check.

A `Message-ID` may be generated or modified during preparation. Therefore, if the system needs an idempotency key or stable send-request ID, generate **an application-layer ID** (e.g., an outbox record ID) rather than treating `Message-ID` as the sole business key.

## 8. Complete Example: Validating Before Calling JavaMailSender.send()

The example below sends a text email in a Spring Boot application. The workflow separates **input validation**, **message creation**, **pre-send metadata inspection**, and **sending**.

### 8.1. Spring Boot Configuration

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Illustrative configuration:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000

app.mail.from=${APP_MAIL_FROM}
~~~

`smtp.provider.example` is only an explanatory hostname; replace it with the actual server provided by your email service. Environment variables avoid putting SMTP passwords into source code. TLS and authentication parameters must match the provider's exact requirements.

### 8.2. Mail-Sending Service

~~~java
import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NoticeMailService {

    private final JavaMailSender mailSender;
    private final String configuredFrom;

    public NoticeMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String configuredFrom) {

        this.mailSender = mailSender;
        this.configuredFrom = configuredFrom;
    }

    public void sendNotice(
            String recipient,
            String subject,
            String body) throws MessagingException {

        // 1. Validate business requirements before creating MIME.
        InternetAddress toAddress = requireOneAddress(recipient);
        InternetAddress fromAddress =
                requireOneAddress(configuredFrom);

        String safeSubject = requireText(subject, "Subject");
        String safeBody = requireText(body, "Body");

        // 2. Create a MimeMessage for this send request.
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(toAddress);
        helper.setSubject(safeSubject);
        helper.setText(safeBody, false);

        // 3. Review assigned metadata before sending.
        verifyPreparedMessage(message);

        // 4. Submit the message to SMTP transport.
        mailSender.send(message);
    }

    private static String requireText(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    label + " cannot be blank"
            );
        }
        return value;
    }

    private static InternetAddress requireOneAddress(String value)
            throws AddressException {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Email address cannot be blank"
            );
        }

        InternetAddress[] parsed =
                InternetAddress.parse(value, true);

        if (parsed.length != 1) {
            throw new IllegalArgumentException(
                    "Only one email address is allowed"
            );
        }

        parsed[0].validate();
        return parsed[0];
    }

    private static void verifyPreparedMessage(
            MimeMessage message) throws MessagingException {

        Address[] from = message.getFrom();
        if (from == null || from.length == 0) {
            throw new IllegalStateException(
                    "Missing From field"
            );
        }

        Address[] recipients = message.getAllRecipients();
        if (recipients == null || recipients.length == 0) {
            throw new IllegalStateException(
                    "No recipients"
            );
        }

        String subject = message.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new IllegalStateException(
                    "Missing Subject"
            );
        }
    }
}
~~~

**Significance of this organization:**

- Code before `createMimeMessage()` validates **input data** against mail-sending requirements.
- `MimeMessageHelper` converts those values into a MIME structure, where Subject can contain Vietnamese or Unicode.
- `verifyPreparedMessage(...)` checks several **assigned fields**. This function does not check the entire MIME structure or SMTP outcome.
- `mailSender.send(message)` performs the actual send. It can throw Spring mail exceptions; MIME build/read errors may appear as nested causes.

This example does not yet include a queue and retry mechanism. In systems needing high reliability, the service can record the send request and hand it off to a background sender process. That does not change the principle of validating data right before sending.

### Why Not Only Inspect MimeMessage After Building It?

If you only read `getAllRecipients()`, `getSubject()`, and `getFrom()`, the application will **not detect** an empty body or a broken attachment in all cases. That is why the example also checks `body` and business data **before calling setters**.

A solid validation suite typically has **two layers**:

1. **Business data layer:** source values, required content, allowed recipient list, size limits, and content type.
2. **Email object layer:** fields assigned to `MimeMessage`, MIME structure, and serializability when special requirements apply.

The two validation layers answer different questions and together help prevent failures.

## 9. Can You Verify Message Serializability?

Sometimes you want to know whether a newly built MIME object can be exported to raw MIME data, such as while developing an HTML feature with multiple attachments.

Jakarta Mail provides `writeTo(OutputStream)`. In a **test environment with dummy data**, you can try:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

static byte[] serializeForTest(MimeMessage message)
        throws MessagingException, IOException {

    message.saveChanges();

    ByteArrayOutputStream out =
            new ByteArrayOutputStream();

    message.writeTo(out);
    return out.toByteArray();
}
~~~

If successful, the returned bytes are the MIME representation of the message at test time. That lets you inspect:

- Prepared header fields.
- `Content-Type` and boundaries of `multipart` regions.
- Serialized `text/plain`, `text/html`, images, and attachments.
- Certain errors when the library accesses underlying data sources.

However, **this operation has costs and side effects to consider**:

- `saveChanges()` can update metadata.
- `writeTo(...)` may have to read every attachment completely.
- `ByteArrayOutputStream` holds the entire email in RAM, unsuitable for large messages or as a mandatory check on every production email.
- Raw messages can contain personal info, tokens, or file data. Never dump those full bytes into logs.
- A data source changing after the serialization test can still fail during the real send.

Therefore, **pre-send serialization is a diagnostic/testing tool**, not a delivery guarantee and not needed on every request. For production, control input resources, configure SMTP properly, and handle send errors.

## 10. APIs Commonly Mistaken for Send Status

### 10.1. getSentDate()

~~~java
Date sentDate = message.getSentDate();
~~~

The sent date header can be set manually by the developer or added by the library during preparation/sending. If `sentDate != null`, that **only indicates the message has a valid Date value**, not that the SMTP relay received the message.

A message created yesterday can carry yesterday's `Date` without ever having been sent. A successfully sent message may also require further processing before reaching the recipient.

### 10.2. getMessageID()

~~~java
String messageId = message.getMessageID();
~~~

`Message-ID` is an identifier for the message in the email ecosystem, typically formatted like:

~~~text
<some-id@example.org>
~~~

Note: the string above illustrates structure only. It is not a business sequence number or an SMTP server receipt. When the library builds/updates a message, this header can appear before sending, and providers may sometimes rewrite metadata. **Having a Message-ID does not mean DELIVERED**.

### 10.3. getFlags()

~~~java
jakarta.mail.Flags flags = message.getFlags();
~~~

Flags such as `SEEN`, `ANSWERED`, and `FLAGGED` are primarily used when working with messages stored in a mail folder. They do not represent SMTP submission progress from a Spring application.

Never use `SEEN` to conclude "the recipient read the email" on a newly built `MimeMessage` object. Flag data has meaning inside a mail store with server support, not as a read receipt for outgoing mail.

### 10.4. getSize()

~~~java
int size = message.getSize();
~~~

The result can be `-1` if the size is unknown. For emails with multipart and attachments, the actual size after MIME encoding can differ from the sum of raw file bytes. Do not use `getSize()` as the sole criterion for confirming a message is valid or within SMTP provider limits.

If the system enforces size limits, combine input caps, encoding-expansion estimates, and provider policies; the sending system must still handle cases where the server rejects a message for being too large.

## 11. Should Checking Message-ID, Date, and Headers Be Mandatory?

Do not require every message to have a `Message-ID` or `Date` **before calling `send(...)`** if the application uses the standard `JavaMailSender` sending path. These fields can be added or updated by the library in the final preparation step.

A more useful **contract checklist** typically includes:

- Sender and recipient addresses are determined by business rules.
- Subject and body are generated without unnecessary sensitive data.
- Content types and MIME parts match the intended message.
- Attachment sources are accessible, size-bounded, and comply with security policies.
- Values derived from external data are validated/sanitized.
- The application has error recording, duplicate prevention, and retries if the business flow requires them.

If you need to store `Message-ID` for log correlation, decide when to capture the ID and account for headers being modified. Separate it from the send request's business ID, such as `notificationId` or `outboxId`, to manage resends consistently.

## 12. Checking Send Readiness Differs from Checking SMTP Connectivity

A complete `MimeMessage` does not prove the SMTP relay is operational. Other problems can arise:

| Stage | Error example | Where detected |
| --- | --- | --- |
| Data preparation | Empty To, blank Subject, missing body, missing attachment | Input/metadata checks |
| MIME construction | Header or data source cannot be built/serialized validly | Jakarta Mail API during preparation/serialization |
| SMTP connection | Wrong host/port, DNS error, blocked connection, timeout | When connecting to the SMTP server |
| SMTP security | STARTTLS failed, untrusted certificate, wrong auth mechanism | Inside the SMTP session |
| Submission | SMTP server rejects sender/recipient or message | When executing `send(...)` |
| Post-submission delivery | Nonexistent recipient address, bounce, spam block | Provider and receiving system |

If using `JavaMailSenderImpl`, `testConnection()` allows **probing connectivity to the server** per configuration at call time. Understand, however:

- This is a **network-connecting** operation, distinct from inspecting message state.
- Being able to connect does not prove a specific sender/recipient or content will be accepted by SMTP.
- A successful check at time A does not guarantee a send session at time B will succeed.
- Do not call connection testing per email to replace real `send(...)` error handling; doing so opens extra connections and does not eliminate unexpected failures.

Thus, evaluating **message readiness** and evaluating **SMTP availability** are two separate responsibilities.

## 13. Application-Managed State with Queues or Outboxes

An e-commerce system may need to guarantee that invoice-sending requests are not lost when the mail server is temporarily down. In that case, the application typically persists a send request to a database or queue and lets a background worker process it.

Example **application-defined** data model:

~~~text
notification_id: 7fb2...
recipient: buyer@example.net
template: invoice-ready
template_data: ...
status: PENDING
attempt_count: 0
created_at: ...
~~~

The worker picks up the request, creates `MimeMessage`, validates it, and attempts to send:

~~~mermaid
flowchart TD
    A["PENDING"] --> B["Build and validate MimeMessage"]
    B -->|"Invalid data"| C["INVALID"]
    B -->|"Valid"| D["Call JavaMailSender.send"]
    D -->|"Server accepted request"| E["SUBMITTED"]
    D -->|"Retryable error"| F["RETRY_WAITING"]
    D -->|"Config/permanent error"| G["FAILED"]
    F --> B
    E -->|"Delivery event received"| H["DELIVERED"]
    E -->|"Bounce event received"| I["BOUNCED"]
~~~

`PENDING`, `INVALID`, `SUBMITTED`, `RETRY_WAITING`, `FAILED`, `DELIVERED`, and `BOUNCED` here are **application-designed values**, not part of `MimeMessage`.

Naming states `SUBMITTED` or `ACCEPTED_BY_RELAY` can be more accurate than `SENT` when the system only knows the SMTP relay accepted the request. Reaching `DELIVERED` normally requires reliable information from the email service or recipient infrastructure, and cannot be inferred from pre-send message checks.

### Retries and Duplicate-Send Risk

A difficult scenario: the application transmitted the message and the SMTP relay may have accepted it, yet the connection dropped before the client read the final reply. The application does not know for sure whether the message was received. When retrying, the email may be sent a second time.

Consequently, an `UNKNOWN` status or reconciliation mechanism may be needed in critical systems. Stable business keys, retry limits, and transaction/outbox management reduce operational errors, yet **SMTP itself does not provide an exactly-once guarantee to the application merely by calling `send(...)`**.

## 14. Errors and Exceptions in Pre-Send Validation

Distinguish data errors from technical errors:

**Data errors:**

~~~java
throw new IllegalArgumentException(
        "Subject cannot be blank"
);
~~~

Or internal state errors:

~~~java
throw new IllegalStateException(
        "MimeMessage has no recipients"
);
~~~

These are errors proactively raised by the application when the defined contract is not met.

**MIME API errors:** Jakarta Mail methods can throw `MessagingException` or `AddressException`, such as while building headers, parsing addresses, or manipulating MIME data. These generally map to an "unable to prepare message" outcome aligned with your application workflow.

**Sending errors:** `JavaMailSender.send(...)` uses Spring Mail's exception hierarchy such as `MailException`, including `MailAuthenticationException` and `MailSendException` depending on the situation. These occur during sending and may wrap exceptions from Jakarta Mail or network infrastructure.

Do not collapse all exceptions into one "message not ready" outcome, because **a missing address** differs from **an overloaded SMTP server**. Accurate classification helps the system decide when to fix data, fix configuration, or retry.

### Avoiding Flooding Logs with Sensitive Data

When reporting pre-send errors, you can record request ID, message type, error code, and failing step. Do not write the entire `MimeMessage` or raw MIME representation into production logs: bodies, headers, and attachments may contain personal data, tokens, and user documents.

## 15. Commonly Misunderstood Scenarios

### Scenario A — Having a Message-ID Means It Was Sent?

No. An unsent `MimeMessage` can already have a `Message-ID` after `saveChanges()`. This header describes the message, not an SMTP receipt or delivery status.

### Scenario B — getSentDate() Having a Value Means the Email Arrived?

No. That is timestamp metadata in the header. It can be set prior to sending. Delivery status requires separate evidence.

### Scenario C — getAllRecipients() Being Non-Empty Means the Address Exists?

No. The API only returns addresses attached to the message. `InternetAddress.validate()` also primarily checks **syntax**, not the existence of remote mailboxes.

### Scenario D — isMimeType("text/html") Returning False Means the Email Has No HTML?

Not necessarily. The message may be `multipart/mixed` or `multipart/related` at the outer level and contain a `text/html` part inside.

### Scenario E — saveChanges() Completing Means SMTP Has No Errors?

No. `saveChanges()` only prepares the MIME message; it does not connect to or authenticate with the SMTP relay.

### Scenario F — A Single validatePreparedMessage() Function Is Always Enough?

Not for complex messages. A metadata checker can miss template data issues, file sizes and readability, recipient constraints, or later network errors. Validate source data and business conditions alongside message field state.

### Scenario G — Isn't Reusing One Message Multiple Times More Convenient?

Usually, create **a fresh `MimeMessage` for each send request** to prevent leaking recipients, Subject, content, or attachments across different emails. `MimeMessage` has mutable state; sharing one object across independent sending flows easily causes bugs and ambiguous outcomes. When emailing multiple people, choose a message-creation and recipient-list strategy that fits your business requirements.

## 16. Practice Exercises

**Exercise 1.** A `MimeMessage` has `From`, `Subject`, and an HTML body, but `getAllRecipients()` returns `null`. Should `send(...)` be called?

**No**, if the application contract requires at least one recipient. Populate appropriate To/Cc/Bcc addresses before sending.

**Exercise 2.** After calling `saveChanges()`, `getMessageID()` has a value. Can the DB status be updated to `DELIVERED` yet?

**Not yet.** Message-ID is only a header identifier. You must perform sending and obtain appropriate delivery evidence.

**Exercise 3.** A `MimeMessage` has `Content-Type: multipart/mixed`. Can you conclude there is no HTML?

**No.** A nested child part may be `text/html`, or there may be multiple nested multipart layers.

**Exercise 4.** The address `someone@example.org` passes syntax checks. Does that guarantee the email will not bounce?

**No.** Valid syntax does not prove the mailbox exists, the receiving domain is configured, or the recipient accepts the email.

**Exercise 5.** An attachment existed during validation but was deleted before send time. Where does the error happen?

It can occur when Jakarta Mail reads the content to serialize and send. Earlier `exists()` checks are only point-in-time observations. Manage resource lifecycles and handle file-read errors.

**Exercise 6.** `mailSender.send(message)` returns normally. Can you conclude the user read the email?

**No.** That is only the result of sending/submitting to SMTP infrastructure. Mailbox status and user opens are separate pieces of information.

## 17. Mental Model to Remember

**Checking message state before sending** means checking **message data and structure on the application side**: addresses, Subject, body, MIME parts, and attachments against the business contract. Spring Framework Mail lets you inspect certain fields via `MimeMessage` and `MimeMessageHelper`; Jakarta Mail also provides `saveChanges()` when preparing headers or serializing the message.

Remember three boundaries:

1. **Message is ready**: the application has verified the conditions required by the email's purpose.
2. **SMTP accepted the send request**: the outcome after executing `JavaMailSender.send(...)` and handling any errors that arise.
3. **Email was delivered/read**: requires separate signals or evidence from delivery infrastructure and the recipient.

No single `MimeMessage.isSent()` method can replace these three layers. Building clear pre-send checks catches errors early and makes the sending flow easy to trace, while send and delivery states must be managed across the application and email infrastructure layers.


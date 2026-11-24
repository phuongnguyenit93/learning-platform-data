# Application-Set Headers and Conflict Risks

When using **Spring Framework Mail**, an application can explicitly set the sender, recipients, subject, reply address, and **custom headers** to categorize or trace emails. However, an email does not contain only application-created headers. Jakarta Mail, SMTP servers, email providers, and relay servers can also **generate, append, normalize, or alter headers** at different stages.

If an application overwrites a header owned by another layer, creates duplicate occurrences of a single-value field, or writes invalid values, the email may be misparsed, rejected, routed to spam, or lose correlation tracking. Worse, placing untrusted user input directly into headers exposes the application to **email header injection**.

This lesson focuses on three questions:

1. Which headers should an application set **itself, and via which APIs**?
2. Which headers should be left to **Spring/Jakarta Mail or mail infrastructure**?
3. How do you avoid **value conflicts, duplicate headers, data leaks, and syntax errors**?

## 1. What Are Email Headers?

An email message has **message headers** at the top and a **body** below, separated by a blank line. Headers include fields like `From`, `To`, `Subject`, `Date`, and `Message-ID`. For MIME emails, headers also describe content structure via `MIME-Version`, `Content-Type`, and related fields.

Conceptual raw email example:

```eml
From: Store <notifications@example.org>
To: customer@example.net
Reply-To: support@example.org
Subject: Order confirmed
Date: Thu, 12 Nov 2026 08:00:00 +0000
Message-ID: <sample-123@example.org>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000

Your order has been confirmed.
```

This message only illustrates structure. In practice, many headers and content encodings are generated automatically by the library or sending server. Never assemble those lines manually by string concatenation to send mail.

### Distinguishing Message Headers from the SMTP Envelope

**Message headers** are part of the email content delivered to recipients. The **SMTP envelope** consists of the addresses used during the SMTP session to route the message:

```text
SMTP envelope:
    MAIL FROM:<bounces@example.org>
    RCPT TO:<customer@example.net>

Message headers:
    From: Store <notifications@example.org>
    To: customer@example.net
    Reply-To: support@example.org
    Subject: Order confirmed
```

The two sets of information are related yet **not identical**:

- The `From` header shows recipients the apparent sender identity inside the email.
- SMTP `MAIL FROM` is the envelope sender address, typically used to receive delivery-failure notifications.
- `To`/`Cc` headers control display, whereas `RCPT TO` holds the addresses actually submitted in the SMTP session.
- **Bcc** recipients appear in the envelope, yet normally do not appear in headers of copies delivered to other recipients.

Therefore, adding a `Return-Path` or `To` header by concatenating strings **is not the proper way to control the envelope**. Use the mail-sending API and corresponding SMTP configuration instead.

## 2. Who Manages Each Kind of Header?

There is no single "header creator" across an email's entire journey.

```text
Spring Application
   |
   | Chooses From, To, Subject, Reply-To;
   | adds permitted application headers
   v
JavaMailSender + MimeMessageHelper + Jakarta Mail
   |
   | Builds MIME structure, formats headers,
   | encodes Unicode, generates required fields
   v
SMTP submission / email provider
   |
   | Verifies sending rights, may normalize,
   | adds provider headers and signs DKIM
   v
Intermediate MTA / receiving MTA
   |
   | Adds Received and transport metadata;
   | verifies authentication and applies policy
   v
Receiving mail server / mailbox
   |
   | Records outcome, may add
   | Authentication-Results and other traces
   v
Recipient mail client
```

A practical division of responsibility:

| Field | Primary Role | Preferred Usage in Spring Applications |
| --- | --- | --- |
| `From` | Displayed author/sender identity | `MimeMessageHelper.setFrom(...)` with an authorized address |
| `To`, `Cc`, `Bcc` | Recipients in each group | `setTo(...)`, `setCc(...)`, `setBcc(...)` |
| `Reply-To` | Suggested reply destination address | `setReplyTo(...)` |
| `Subject` | Message subject | `setSubject(...)` |
| `Sender` | Transmitting agent identity when distinct from author where appropriate | Set only if you understand exact semantics and provider policy |
| `Date` | Message creation/origination date | Usually let library set it; customize only for specific needs |
| `Message-ID` | Standards-based message identifier | Usually let library/infrastructure generate it; do not use as sole business ID |
| `MIME-Version` | Indicates MIME-formatted message | Managed by Jakarta Mail |
| `Content-Type`, `Content-Transfer-Encoding`, `Content-Disposition` | Media type, transfer encoding, and MIME part disposition | Use `MimeMessageHelper`, `setText(...)`, `addAttachment(...)` |
| `Received` | Server-hop transport trace | Added by MTAs; application must never spoof |
| `Return-Path` | Usually added at final delivery from envelope sender | Control envelope via proper transport config, not manual header |
| `DKIM-Signature` | Domain authentication signature | Usually added by sending service/MTA signer after content stabilizes |
| `Authentication-Results` | Authentication check outcome at receiving system | Added by authoritative verifying systems |
| Application headers like `X-App-Event-ID` | Metadata for correlation and custom categorization | May use `MimeMessage.setHeader(...)` with validated values |

This is a **role-based ownership guide**, not an absolute prohibition against touching standard fields. Specialized workflows may require setting some of them; in those cases, understand the RFC rules, library behavior, and SMTP provider policies.

## 3. Headers the Application Can Actively Set

### 3.1. Use Dedicated APIs for Standard Fields

In Spring Mail, applications should use `MimeMessageHelper` for fields with well-defined semantics:

```java
helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setReplyTo("support@example.org");
helper.setSubject("Order confirmation");
helper.setText("Your order has been confirmed.", false);
```

These APIs let the library handle addresses, international characters, header formatting, and MIME structure properly. When addresses or content come from users, the application must still validate business data and sending permissions; convenience APIs do not replace input control.

For `Bcc`, use `helper.setBcc(...)`. Manually adding a `Bcc: ...` line to a raw message string can leak a visible header unintentionally or desynchronize it from envelope recipients.

### 3.2. Custom Headers for Metadata

Transactional email systems may need to link a message back to the event that triggered it. Example:

```text
X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000
X-App-Notification-Type: order-confirmation
X-App-Environment: production
```

These fields can help:

- Correlate a sent email with a business request in your system.
- Identify notification types when inspecting raw messages or test-environment copies.
- Attach a correlation key between application logs and sending-service logs when the service preserves and returns custom headers.
- Support internal workflows that agree explicitly on header names and meanings.

**Not every SMTP provider preserves or echoes custom headers in webhooks.** Some providers offer dedicated metadata/tagging APIs that are more reliable. If a workflow depends on reading back a header, check the provider's contract and documentation.

#### Is the `X-` Prefix Mandatory?

No. The `X-` prefix is a **long-standing convention** for custom headers. There is no rule requiring every custom field to start with `X-`; modern extensibility guidance even discourages defaulting to `X-` for all new fields.

You can choose clearly scoped names such as `App-Event-ID` or `X-App-Event-ID` depending on system conventions and provider support. More important than the prefix:

1. The name does not collide with standard fields or provider-reserved headers.
2. Producers and consumers agree on format and meaning.
3. Values contain no secrets or data that should not be exposed to recipients.
4. Headers are set through controlled APIs rather than raw email string assembly.

### 3.3. Standard Headers That May Be Set for Business Needs

Not every standard header is always generated automatically. Certain fields can be specified by the application **when a clear requirement exists**:

| Header | Appropriate Scenario | Notes |
| --- | --- | --- |
| `Reply-To` | Sender wants replies routed to support | Distinct from `From`; use helper |
| `Auto-Submitted: auto-generated` | Marks automated messages per proper semantics | Does not guarantee every client suppresses auto-replies or spam checks |
| `List-ID` | Identifies a true mailing list | Do not misuse for transactional emails |
| `List-Unsubscribe` | Provides an unsubscribe address or URL for eligible mail streams | Set only when an active unsubscribe mechanism exists |
| `List-Unsubscribe-Post` | Provides one-click unsubscribe per corresponding convention | Requires proper endpoint/workflow; header alone is not enough |
| `In-Reply-To`, `References` | Email continues an existing thread | Built from valid Message-IDs of related messages |

For example, a `List-Unsubscribe` header pointing to a dead URL degrades user experience and can violate receiving-system expectations. Likewise, requesting read receipts via a header does not turn an "open" event into reliable proof.

## 4. What Are Header Conflict Risks?

A **header conflict** occurs when two components set the same field with conflicting values or expectations, or when a field is placed at the wrong level, duplicated, or malformed.

Suppose an application manually sets:

```text
Content-Type: text/plain; charset=UTF-8
```

and then calls `helper.setText(html, true)` to build HTML. If application code or the library changes `Content-Type` to `text/html`, their expectations clash. If the header ends up duplicated with two conflicting values, email clients may interpret it inconsistently.

Typical forms of conflict:

- **Two writers setting the same field:** app sets `Date` or `Message-ID`, then the library or provider regenerates it.
- **Duplicated single-value field:** calling `addHeader` repeatedly on a field meant to appear only once.
- **Mismatch with body:** declaring `charset`, `Content-Type`, or `Content-Transfer-Encoding` that contradicts the actual bytes.
- **Conflict with sender policy:** app sets `From` outside identities authorized for the SMTP account.
- **Conflict with authentication signing:** mutating signed headers/body breaks DKIM verification.
- **Misrepresented metadata:** manually setting `Received` or `Authentication-Results` as though created by a trusted server.
- **Provider rewriting:** provider replaces `Message-ID`, injects tracking tags, or strips a custom header.
- **Structure-breaking input:** strings containing CR/LF injected into header names or values.

Not every conflict throws an exception on the application side. Some surface only when the email reaches the receiving server or mail client, making them harder to diagnose.

## 5. `setHeader` vs. `addHeader`

In Jakarta Mail, `MimeMessage` exposes direct header manipulation methods:

```java
mimeMessage.setHeader("X-App-Event-ID", eventId);
mimeMessage.addHeader("X-App-Tag", "notification");
mimeMessage.addHeader("X-App-Tag", "order");
```

Core semantics:

| API | Effect | When to Use |
| --- | --- | --- |
| `setHeader(name, value)` | Sets the header value; replaces existing values with the same name | An application header needing **one definitive value** |
| `addHeader(name, value)` | Adds another value/occurrence of the header | Only when the field's syntax and semantics permit multiple occurrences |
| `getHeader(name)` | Retrieves existing header values | Reading data in a controlled context |
| `removeHeader(name)` | Removes headers by name | Only when you truly own that field and understand the impact |

**Header names are case-insensitive in email semantics.** `X-App-Event-ID` and `x-app-event-id` are not two separate fields.

### 5.1. When Is Duplicating Headers Dangerous?

Consider this code:

```java
mimeMessage.addHeader("Subject", "Order received");
mimeMessage.addHeader("Subject", "Reset your password");
```

This risks emitting multiple semantically conflicting `Subject` headers. A mail client might pick the first, pick the last, reject the message, or display something unexpected. For `Subject`, call `helper.setSubject(...)` **once with the final value**.

Similarly, `From` and `Message-ID` have strict syntax rules and must never use `addHeader` like a tag list. When multiple recipients are needed, use address-list APIs rather than arbitrarily repeating `To`.

However, **not every repeated header is invalid**. For instance, each server along the delivery path can prepend a new `Received` line. That is valid trace behavior, though the application itself should never fabricate those lines.

### 5.2. What If Metadata Has Multiple Values?

For application metadata, instead of arbitrarily emitting multiple same-named headers:

```text
X-App-Tag: invoice
X-App-Tag: priority
```

you can define a single format:

```text
X-App-Tags: invoice, priority
```

or use two distinct, clearly named fields:

```text
X-App-Notification-Type: invoice
X-App-Processing-Class: priority
```

Pick one approach and define parsing rules on both producer and consumer sides. Comma-separated lists **are not implicitly valid for every header**; they must follow the contract of the custom field defined by your application.

## 6. Why You Should Not Manually Edit MIME Headers

For a plain-text-only email, the body may be described by:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
```

Yet for an email containing HTML and a PDF attachment, the structure can look like:

```text
Top-level message:
    Content-Type: multipart/mixed; boundary=...
        |
        +-- multipart/alternative; boundary=...
        |       |
        |       +-- text/plain; charset=UTF-8
        |       |
        |       +-- text/html; charset=UTF-8
        |
        +-- application/pdf
            Content-Transfer-Encoding: base64
            Content-Disposition: attachment; filename=...
```

Each MIME part can have its own `Content-Type` and `Content-Transfer-Encoding`. Overwriting the **outermost** `Content-Type` to `text/html` just because you want "an HTML email" can break the entire multipart tree or make attachments unreadable.

**The right way in Spring:** use `MimeMessageHelper` to build content:

```java
helper.setText(
    "Plain text content.",
    "<p><strong>HTML</strong> content.</p>"
);
helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

To combine text/HTML and attachments, initialize the helper in an appropriate multipart mode. The library manages boundaries and per-part MIME headers.

Avoid code like this:

```java
// Wrong approach: arbitrarily overwriting Content-Type
mimeMessage.setHeader("Content-Type", "text/html");

// Then using helper to build multipart/attachment
helper.addAttachment("invoice.pdf", resource);
```

The final call can cause the library to reorganize the MIME tree, leaving the manually set header out of sync with the body. Mutating raw serialized messages via string replacement afterward is even riskier.

### Charset and Transfer Encoding Must Also Match

If a part holds UTF-8 Vietnamese text while the application declares `charset=US-ASCII`, recipients will see corrupted characters. If bytes are Base64-encoded while the header says `quoted-printable`, mail clients will decode with the wrong algorithm.

Never manually Base64-encode a `String`, set it as text, and force `Content-Transfer-Encoding: base64`; that easily causes **double encoding**. Hand raw logical content to Jakarta Mail and let the library choose appropriate transfer encodings.

## 7. Conflicts with `Date`, `Message-ID`, and Infrastructure-Generated Headers

### 7.1. `Message-ID` Is Not a Business Event ID

`Message-ID` is the email message's standards-formatted identifier. The library or server may generate this value while finalizing/sending the message. Some providers also assign their own **provider message ID** in delivery-tracking systems.

Suppose an application processes order `ORD-2026-105` and produces two independent emails:

```text
Business event: ORD-2026-105
   |
   +-- order confirmation email ----> Message-ID A
   |
   +-- invoice email ---------------> Message-ID B
```

If an email is retried, the system may emit a new message with a different `Message-ID`. Therefore:

- Use a **business event ID** or **notification ID** in your database to track status and enforce idempotency per application policy.
- You may add a custom header like `X-App-Event-ID` to correlate emails with events.
- Store the provider ID or SMTP queue ID separately when provided.
- Never assume `Message-ID` stays immutable across all provider layers or matches the ID returned by webhooks.

If you manually set `Message-ID` and then the library runs `saveChanges()` or a provider reprocesses the email, the final value may differ from expectations. Leave it to the library/infrastructure unless you have a clear protocol requirement and know exactly how they handle it.

### 7.2. `Date` and Time Zones

`Date` is a standard header holding the timestamp formatted in email date-time syntax. `MimeMessage` and infrastructure may populate or adjust this field.

Business timestamps such as `createdAt`, `orderConfirmedAt`, or `processedAt` should be stored separately in your system. Never rely on `Date` as the sole proof of when an order occurred, because it belongs to the email message and can differ from business-event timing.

### 7.3. `Received` and `Authentication-Results` Belong to Different Trust Boundaries

MTAs **prepend** `Received` as mail passes through them; receiving systems may add `Authentication-Results` reporting SPF, DKIM, and DMARC checks. Conceptual example:

```text
Received: from relay.example.org by mx.example.net ...
Authentication-Results: mx.example.net; dkim=pass ...
```

Mail-sending applications **must never set these fields to claim** which servers a message traversed or that it passed authentication. Receiving systems enforce strict trust boundaries around trace/authentication metadata because sender-supplied headers can be forged.

### 7.4. `Return-Path` Is a Consequence of the Envelope Sender

`Return-Path` in a delivered email typically reflects the **SMTP envelope sender** at final delivery. Calling:

```java
mimeMessage.setHeader("Return-Path", "bounces@example.org");
```

does not guarantee bounces will route to that address. The envelope sender is negotiated at the SMTP layer and may be controlled by your provider.

With Jakarta Mail SMTP transport, properties such as `mail.smtp.from` control the envelope sender when supported by the endpoint, subject to provider rules; never use raw headers as a substitute. When using an API-based mail provider or managed relay, configure return-path/bounce domains through the provider's official mechanisms.

### 7.5. `DKIM-Signature` and Message Modification Order

DKIM signs specific headers and the body for domain authentication. If a message is modified **after signing**, the signature can fail depending on which fields were signed and canonicalization rules.

```text
Application builds MIME message
        |
        v
Library finalizes headers/body
        |
        v
Provider / MTA signs DKIM
        |
        v
SMTP relay -> receiving system verifies DKIM
```

Hence, never attach `DKIM-Signature` manually as a custom label, and never alter signed headers or body content at an intermediate relay. DKIM signing belongs in the sending infrastructure where domains, keys, and policies are managed.

## 8. Header Injection: Risks of Untrusted Input

Email headers are lines formatted as `Field-Name: value`. If an application interpolates external input directly into raw headers without blocking newline characters, an attacker can attempt to inject **new headers** or alter message structure.

Conceptual danger example:

```text
X-App-Customer-Name: Alice
Bcc: unknown-recipient@example.net
```

If `Alice` actually came from user input containing a newline followed by `Bcc: ...`, unsafe raw header assembly treats it as two separate fields. Likewise, injecting a blank line pushes subsequent text into the body. Actual exploitability depends on the library and serialization layer; **never rely on the mail client's parser as your application's defense**.

### Prevention Rules

1. **Never build raw headers via string concatenation** from external input.
2. **Never let users choose header names**; hardcode an allowed list of header names in code.
3. **Constrain values** to expected structures: UUIDs, event codes, enums, or short tracking codes.
4. **Reject CR, LF, and inappropriate control characters** in values placed into custom headers.
5. Use dedicated Jakarta Mail/Spring APIs for addresses, subjects, and content; never inject values into multi-line `Header: value` strings.
6. Enforce length limits to avoid bloated logs or inconsistent provider behavior.
7. Attach only necessary metadata; never put secrets or sensitive PII into headers.

This is another reason to use **typed values** rather than free-form strings. For instance, `UUID#toString()` emits a simple deterministic character set, and a `NotificationType` enum has a finite, easily controlled set of values.

## 9. Spring Boot Example: Setting Custom Headers Safely

This section uses **Spring Boot and Spring Framework Mail** with `JavaMailSender`. The goal is to send a transactional email with `From`, `To`, `Reply-To`, `Subject`, and two custom correlation headers, leaving technical headers to Jakarta Mail/the provider.

### 9.1. Dependency and Configuration

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Illustrative `application.yml` for SMTP submission over port 587:

```yaml
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
    from: ${MAIL_FROM_ADDRESS}
    reply-to: ${MAIL_REPLY_TO_ADDRESS}
```

This assumes an SMTP server supporting STARTTLS and authentication on port 587. Endpoints using implicit TLS on 465 require different settings. Credentials must come from runtime environment variables or secrets, never hardcoded in source control.

### 9.2. Setting Headers According to Ownership

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

@Service
public class OrderNotificationMailService {

    private static final String HEADER_EVENT_ID = "X-App-Event-ID";
    private static final String HEADER_TYPE = "X-App-Notification-Type";

    private final JavaMailSender mailSender;
    private final String fromAddress;
    private final String replyToAddress;

    public OrderNotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.mail.reply-to}") String replyToAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
        this.replyToAddress = replyToAddress;
    }

    public void sendOrderConfirmed(
            String recipientAddress,
            UUID notificationId
    ) {
        mailSender.send(message -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    StandardCharsets.UTF_8.name()
            );

            // Standard message headers: use dedicated APIs.
            helper.setFrom(fromAddress);
            helper.setTo(recipientAddress);
            helper.setReplyTo(replyToAddress);
            helper.setSubject("Your order has been confirmed");
            helper.setText(
                    "Hello. Your order has been confirmed.",
                    false
            );

            // Application metadata: fixed names, typed values.
            message.setHeader(HEADER_EVENT_ID, notificationId.toString());
            message.setHeader(HEADER_TYPE, "order-confirmation");
        });
    }
}
```

Design rationale:

- `MimeMessageHelper` handles standard headers and text content.
- Both custom headers use **constant names**, never arbitrary form or query parameters.
- `notificationId` is a `UUID`; its string representation cannot contain newlines to inject headers.
- `order-confirmation` is a known constant.
- Code **never manually sets** `Message-ID`, `Date`, `Received`, `Return-Path`, `DKIM-Signature`, or MIME encoding headers.
- Values like `recipientAddress`, `fromAddress`, and `replyToAddress` still require business-workflow validation and system configuration checks.

`JavaMailSender.send(MimeMessagePreparator)` lets you prepare `MimeMessage` via a callback. Inside the callback, use `MimeMessageHelper` for standard fields and `message.setHeader(...)` for custom metadata. On send, the library/provider completes the remaining protocol details.

In plain Spring Framework, configure an equivalent `JavaMailSender` and Jakarta Mail implementation; `MimeMessage` handling follows the exact same principles.

### 9.3. When You Must Validate a Free-Form Custom Header Value

Suppose the system accepts a short upstream campaign code. This metadata needs to be preserved, yet the input is **not** a strongly typed UUID. Apply a character allowlist:

```java
import java.util.regex.Pattern;

private static final Pattern SAFE_CAMPAIGN_KEY =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

private static String requireSafeCampaignKey(String value) {
    if (value == null || !SAFE_CAMPAIGN_KEY.matcher(value).matches()) {
        throw new IllegalArgumentException("Invalid campaign key");
    }
    return value;
}
```

And set only the application-owned field:

```java
message.setHeader(
        "X-App-Campaign-Key",
        requireSafeCampaignKey(campaignKey)
);
```

This regex is an **example application-code policy**, not universal syntax for all email headers. Another field format may require different validation, yet must still block control characters and unexpected syntax.

### 9.4. Same Email with HTML and an Attachment

To add HTML and a PDF, do not manually update `Content-Type` afterward. Instead, initialize the helper in multipart mode:

```java
import org.springframework.core.io.ByteArrayResource;

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

helper.setFrom(fromAddress);
helper.setTo(recipientAddress);
helper.setSubject("Your invoice");
helper.setText(
        "Your invoice is attached to this email.",
        "<p><strong>Your invoice</strong> is attached to this email.</p>"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

message.setHeader("X-App-Event-ID", notificationId.toString());
```

These lines represent the message-building body, assuming `message`, `fromAddress`, `recipientAddress`, `pdfBytes`, and `notificationId` are in scope. The library handles `multipart`, `boundary`, transfer encodings, and attachment headers.

**Never call `message.setHeader("Content-Type", "text/html")` to "fix" an email after adding an attachment.** The outermost message's `Content-Type` must reflect the multipart container, not just the inner HTML part.

## 10. Reading the Output: Which Headers Can Change After Sending?

Distinguish three perspectives when inspecting an email:

1. **Before sending:** the `MimeMessage` in the application holds the fields set by code; some automatic headers are not yet finalized.
2. **After SMTP submission:** the sending server may add trace entries, queue IDs, rewrite fields per policy, or apply DKIM signing.
3. **Inside the mailbox:** the message may have traversed multiple MTAs and gained `Received`, `Authentication-Results`, or service-specific metadata.

For example, the same email may evolve as follows:

```text
Application creates:
  From: notifications@example.org
  X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000

Library/provider finalizes:
  Date: ...
  Message-ID: ...
  MIME-Version: ...
  Content-Type: ...

Sending/receiving servers add:
  Received: ...
  DKIM-Signature: ...
  Authentication-Results: ...
```

Do not assume every field is added at the exact same hop in every system. For instance, a sending service might sign DKIM at a different point in its pipeline.

### Are Application Headers Trustworthy Evidence?

An `X-App-Event-ID` generated by your own outbound app is useful for **correlation**. However, if your application ingests inbound emails from the Internet and trusts that header to grant access, release funds, or confirm actions, an external sender can **forge the header value**.

Headers carried inside email are sender-controlled data. To authenticate a message or authorize sensitive operations, rely on genuine evidence such as verified identities, cryptographic signatures, single-use tokens, backend permissions, or dedicated verification flows. A custom header by itself **is not an authentication token**.

## 11. Security and Privacy: Never Put Secrets in Headers

Headers are easily viewed via "Show original", "View source", or server logs. When an email is forwarded, many headers travel along with the message. Some providers also index metadata and surface it in dashboards.

Therefore, **never place in headers**:

- SMTP passwords, API keys, access tokens, refresh tokens, or cookies.
- Session authentication details.
- Unnecessary personal data such as ID numbers, payment details, medical diagnoses, or confidential content.
- Query strings carrying password-reset tokens or private access links merely for tracking.
- Long internal payloads that cause logs or providers to store more data than intended.

Prefer **opaque IDs** such as random UUIDs and store mappings to sensitive details inside an access-controlled database. Even opaque IDs can be read by recipients, so include them only when genuinely useful.

### Headers Can Be Altered or Stripped

Some receiving and sending systems strip custom headers, normalize casing, fold lines, or append extra values. If a server workflow reads headers, make sure you:

1. Clearly define the producer and consumer.
2. Do not rely on unspecified header ordering.
3. Handle missing or multi-valued headers gracefully.
4. Never assume providers return the exact raw MIME bytes your application built.
5. Keep backend correlation keys and provider events when stronger tracking guarantees are needed.

## 12. Common Failure Scenarios

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Email shows two different Subjects | Calling `addHeader("Subject", ...)` multiple times | Use `MimeMessageHelper.setSubject(...)` |
| Replies go to the wrong address | Wrong `Reply-To`, conflicting with config | Use `setReplyTo(...)` and verify addresses |
| Attachment fails to open | Manually overwriting `Content-Type` or `Content-Transfer-Encoding` | Let Jakarta Mail build MIME; use `addAttachment(...)` |
| Raw HTML tags appear as text | Header/part set to `text/plain` while body is HTML | Use `setText(html, true)` or text/HTML alternative |
| Rejected despite SMTP AUTH | `From` not within authorized senders/domains | Use a verified address, review provider policy |
| Corrupted Vietnamese text | Declared charset mismatches text bytes | Use UTF-8 consistently, check data source |
| Custom header missing in mailbox | Provider or relay normalized or stripped it | Inspect raw message and provider docs |
| `Message-ID` differs from app ID | Library or provider generated/rewrote message ID | Store a separate business ID and map provider IDs |
| DKIM fails after email edit | Headers/body modified after signing | Finalize message before signing; audit relays |
| Header leaks internal data | Payload/secret placed in metadata | Use non-sensitive IDs, restrict fields |
| Unintended Bcc generated | External input interpolated into raw headers with CR/LF | Use typed APIs, allowlist names, validate values |
| Message arrives with broken multipart | Boundaries or part headers edited manually | Let `MimeMessageHelper` construct multipart structure |

### Scenario 1: A Service and a Library Both Set `Subject`

```java
helper.setSubject("Order notification");
mimeMessage.addHeader("Subject", "General notification");
```

This code lets two sources write to the same field. In clean design, **one layer owns the final value**; other layers pass parameters or return text for that layer to set the header. Avoid libraries acting as hidden decorators that append another `Subject`.

### Scenario 2: Application Manually Sets `Message-ID` to Prevent Duplicates

Code derives `Message-ID` from an order ID and submits the same message multiple times. This does not guarantee deduplication: an MTA/provider may treat each submission as a new send, and the ID may be rewritten.

To prevent duplicate sends, persist request state in the backend using a **notification ID/idempotency key** and implement an appropriate retry strategy. Headers only aid observability; they do not replace business state.

### Scenario 3: Trying to Change `Return-Path` to Capture Bounces

The application calls `setHeader("Return-Path", ...)`, yet bounces still do not arrive at the desired address.

The reason is that delivery relies on the **SMTP envelope sender** or the provider's bounce/return-path settings. Update the configuration that owns the envelope instead of adding a header with a similar name.

### Scenario 4: Using Custom Headers to Tag Email Types

The application sets:

```text
X-App-Notification-Type: account-verification
X-App-Event-ID: 550e8400-e29b-41d4-a716-446655440000
```

This is sensible when header names are controlled and values hold no sensitive data. It does not alter the standard meaning of `From`, `To`, `Subject`, or MIME fields. If your provider has a dedicated tagging system for analytics, check whether you should use its metadata API rather than relying solely on custom headers.

### Scenario 5: DKIM Signer and a Relay Both Modify the Footer

The provider signs DKIM, and then an internal relay appends a promotional footer to the body after signing. When the receiving server verifies the signature, body verification can fail because the content changed.

The architectural fix is finalizing content and footers **before signing**, or re-signing at an authorized hop. Never try to "fix" it by injecting a fake `DKIM-Signature` line.

## 13. Header Design Conventions for Spring Projects

When multiple services send email, agree on a simple contract:

| Header Group | Owner | Convention |
| --- | --- | --- |
| `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject` | Mail-sending service or single builder class | Set via `MimeMessageHelper` |
| `Content-Type`, `Content-Transfer-Encoding`, `boundary`, and attachment headers | Jakarta Mail / MIME helper | Driven by content APIs; never overwrite manually |
| `Date`, `Message-ID`, `MIME-Version` | Library / sending infrastructure per config | Never use as business keys |
| `Received`, `Return-Path`, `Authentication-Results`, `DKIM-Signature` | Transport, receiving, and auth infrastructure | Never fabricate in application code |
| `X-App-Event-ID` | Business service issuing notification ID | UUID; at most one clear value |
| `X-App-Notification-Type` | Business service selecting notification type | Enum / fixed constant |
| Other specialized standard headers | Owner understanding business & provider requirements | Set only when corresponding mechanism is active |

A maintainable code flow:

```text
Business event
     |
     v
Mail request:
   recipients, sender, replyTo,
   subject, body, notificationId, type
     |
     v
Mail composer (single place building MimeMessage)
   |
   +-- MimeMessageHelper: standard headers + MIME body
   |
   +-- MimeMessage.setHeader: validated metadata
     |
     v
JavaMailSender
     |
     v
SMTP server / provider / MTAs
```

This avoids an interceptor, a template renderer, and a business service all mutating `From`, `Subject`, or `Content-Type` in unpredictable order.

When extending headers, explicitly determine **whether the application owns that header**, **whether it belongs on the top-level message or a MIME part**, and **whether another component might overwrite it**. Also verify whether the final value is actually visible to recipients or provider webhooks.

## 14. Key Takeaways in Three Questions

**Can an application add its own headers?** Yes. For example, a UUID `X-App-Event-ID` can be added via `MimeMessage.setHeader(...)`. However, custom headers are visible inside the email and may be altered by intermediate systems; never treat them as trusted authentication.

**Why shouldn't you manually set `Content-Type`, `Message-ID`, or `Return-Path` arbitrarily?** Because they play specific protocol roles usually managed by the mail library or mail infrastructure. Setting them manually can conflict with MIME structure, ID generation, or the SMTP envelope.

**How do you avoid conflicts?** Use `MimeMessageHelper` for standard fields and content, restrict `setHeader` to metadata truly owned by the application, constrain header names and values, understand email headers versus the envelope, and avoid mutating messages after infrastructure signs or normalizes them.

In Spring Framework Mail, the safest design is to **explicitly own only the headers your application genuinely needs**, delegating encoding, MIME packaging, transport tracing, and email authentication to the layers responsible for them.

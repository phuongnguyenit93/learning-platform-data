# Preventing Header Injection When Sending Email with Spring Framework Mail

When an application sends email, most developers focus on the SMTP host, port, TLS, HTML content, and attachments. However, a class of security bugs occurs right at the step of **constructing message headers**: user-controlled data is placed into `Subject`, `From`, `To`, `Reply-To`, or another MIME header without proper validation.

**Email header injection** occurs when an attacker causes data intended strictly as a **field's value** to be interpreted as **one or more new header fields**, or alters the boundary between headers and the message body. Typical techniques exploit `CR` and `LF` newline characters in input data, sometimes combined with other email syntax nuances.

In a Spring Framework Mail application, the most important defense is **never manually concatenating raw email/SMTP messages from untrusted strings**, using only the structured APIs of `MimeMessageHelper`/Jakarta Mail, validating input data for the **header context**, restricting which fields users are allowed to control, and guarding low-level API call sites.

This lesson explains the attack mechanics, commonly affected surfaces, Java/Spring Mail examples, testing strategies, and the limits of related protections such as SPF, DKIM, DMARC, and SMTP authentication.

## 1. What are email headers?

An email has two main logical sections: **headers** and **body**, separated by a blank line under the Internet Message format.

Illustrative example:

```text
From: Example <no-reply@example.org>
To: alice@example.net
Subject: Order confirmation
Date: Thu, 12 Nov 2026 09:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Thank you for your order.
```

Headers describe who sent the message, who receives it, the subject, timestamp, and how to interpret the content. The body contains plain text, HTML, or MIME multipart structures. A mail-sending application may also emit `Reply-To`, `Cc`, `Bcc`, `Message-ID`, `Content-ID`, `Content-Disposition`, and extension fields.

Header lines follow email-specific syntax. A typical header looks like:

```text
Field-Name: field value
```

Traditionally, lines terminate with the `CRLF` pair (carriage return + line feed). A new line starting with a field name and colon can be interpreted as another header. Meanwhile, a continuation line starting with whitespace can be a **folded header**; valid folding must be performed by the header serializer, never typed arbitrarily by users.

### Common headers and impact levels

| Header | Purpose | Risk if controlled |
|---|---|---|
| `Subject` | Message subject | Injecting fake headers, corrupting subject, or altering structure |
| `From` | Displayed sender | Spoofing sender identity or bypassing sender policies |
| `To` / `Cc` / `Bcc` | Recipients | Adding unintended recipients, leaking addresses, or unauthorized sending |
| `Reply-To` | Reply destination | Diverting customer replies to another mailbox |
| `Content-Type` | Content type/MIME boundary | Changing how mail clients interpret the body |
| `Content-Disposition` | Inline or attachment, filename | Corrupting attachment metadata or injecting extra headers |
| `Content-ID` | Inline resource ID | Misreferencing parts or manipulating MIME structure |
| Custom `X-*` headers | Correlation, tracking, routing | Injecting new headers if the app concatenates strings directly |

Some headers above can be populated by the application with validated data; most **should not be chosen arbitrarily by clients**.

## 2. How does header injection happen?

Consider code that builds raw headers manually:

```java
// Anti-pattern: never use this to build real emails to send.
String rawMessage =
        "To: customer@example.net\r\n"
      + "Subject: " + userSubject + "\r\n"
      + "Content-Type: text/plain; charset=UTF-8\r\n"
      + "\r\n"
      + body;
```

Here, `userSubject` is meant to be only a single-line Subject value. If an attacker supplies a string containing `\r\n`, that value can cause a parser to transition onto another header line.

Illustrative payload:

```text
Order confirmation\r\n
Bcc: unexpected@example.invalid
```

When concatenated into the raw message, it can produce:

```text
To: customer@example.net
Subject: Order confirmation
Bcc: unexpected@example.invalid
Content-Type: text/plain; charset=UTF-8

Message body
```

This illustrates the risk of **string concatenation into raw headers**. A specific mail-sending implementation may reject malformed headers or determine SMTP envelope recipients independently from display headers; thus **adding a `Bcc` header does not always make SMTP deliver to that address**. Still, if the system derives recipients from manipulated headers, or builds SMTP envelopes from tainted data, unintended delivery becomes a real risk.

The outcome of injection depends on how the app constructs messages, parsers, libraries, and transports. In every case, user-controlled data **must never have the ability to alter header structure**.

### Distinguishing CR and LF

- `\r` is carriage return (CR, U+000D).
- `\n` is line feed (LF, U+000A).
- `\r\n` is the CRLF pair used as a line terminator in Internet Message syntax.
- Some libraries/devices also normalize non-standard newlines. Therefore, input validation should reject both `\r` and `\n` whenever they appear in **user-supplied header values**, not only the exact `\r\n` sequence.

Do not simply replace `"\r\n"` with an empty string and let data pass through: inputs can still contain standalone `\r`, standalone `\n`, tabs, other control characters, or visually misleading Unicode forms.

## 3. Why is this an SMTP security issue?

Applications are typically authorized to send email through a verified SMTP account. If user input alters recipients or displayed metadata, attackers can abuse that account's reputation and quota.

Consequences can include:

1. Sending additional messages to unauthorized recipients if recipient generation is affected.
2. Causing spoofing or confusion via `From`/`Reply-To` to divert replies elsewhere.
3. Altering `Content-Type` or MIME structure so mail clients process content unexpectedly.
4. Producing messages rejected by servers, breaking the sending pipeline or causing application-layer denial of service.
5. Disclosing data if emails go to a third-party mailbox or debug logs capture injected headers.
6. Making logs and audits fail to reflect the business-approved recipient/subject accurately.

Header injection is a form of **output injection into email syntax**, distinct from SQL injection or HTML injection. All three involve untrusted input, yet their representations and defenses differ.

### Commonly overlooked trust boundaries

Input does not come solely from a Subject field on a form. It can also appear in:

- Customer names inserted into `From` or `To` display names.
- Customer-entered `Reply-To` addresses.
- Attachment filenames taken from uploads.
- Campaign names or product names inserted into `Subject`.
- Template variables coming from a database or partner systems.
- Metadata synced from CRMs, CMSs, webhooks, or queues.
- `X-Correlation-ID` headers copied verbatim from HTTP requests.
- User-supplied `Content-ID` or parts of `Content-Type`.

Data stored in a database **does not automatically become trusted data**. If its origin was a user or external system, treat it according to the final sink boundary.

## 4. Defense-in-depth principles

A solid anti-header-injection design typically includes these layers:

| Layer | Measure | Purpose |
|---|---|---|
| API design | Do not accept raw MIME/SMTP headers from clients | Reduces attack surface |
| Input validation | Block CR/LF and control chars in header values | Prevents unintended line breaks |
| Typed parsing | Use `InternetAddress` for mailboxes | Avoids manual address splitting/joining |
| Message creation | Use `MimeMessageHelper` and Jakarta Mail | Lets the library encode, fold, and serialize |
| Sender policy | Fixed/verified `From`, controlled `Reply-To` | Prevents spoofing and redirection |
| MIME handling | Use `addInline` / `addAttachment`, never hand-write `Content-*` | Prevents part structure tampering |
| Authorization | Verify who can send to whom, and for what purpose | Prevents abuse even with valid addresses |
| Rate limiting and quotas | Cap send requests | Reduces spam and DoS |
| Safe logging | Log IDs/error categories, never raw inputs/headers | Avoids spreading payloads and PII |
| Testing | Test CR, LF, CRLF, and abnormal inputs | Catches regressions |

No single layer replaces all others. `MimeMessageHelper` avoids manual header serialization, yet does not decide whether a user is allowed to set `Reply-To` or email an arbitrary address.

## 5. Never concatenate raw emails or SMTP commands as Strings

The following patterns carry risk:

```java
// Wrong: manually concatenating raw MIME from untrusted data.
String header = "Subject: " + request.subject() + "\r\n";

// Wrong: manually building SMTP envelope addresses from unchecked input.
String smtpCommand = "RCPT TO:<" + request.recipient() + ">\r\n";

// Wrong: manually building MIME part headers.
String disposition =
        "Content-Disposition: attachment; filename=\"" +
        request.filename() + "\"\r\n";
```

Beyond CRLF/header injection, this approach easily breaks charsets, header folding, MIME boundaries, binary transfer encoding, and filename encoding.

Instead, work through the API:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("no-reply@example.org");
helper.setTo(validatedRecipient);
helper.setSubject(validatedSubject);
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");

mailSender.send(message);
```

This snippet assumes `validatedRecipient` and `validatedSubject` already passed context-specific checks. For multipart messages, `MimeMessageHelper` builds the needed MIME structure and Jakarta Mail handles serialization; the application never adds `\r\n` or writes SMTP `DATA` commands itself.

**Do not rely entirely on assuming “the current library will surely reject bad input”.** Validation/encoding behavior can vary across library versions and low-level APIs. Reject header values containing control chars before passing them to the library.

## 6. Validation for single-line header values

User-supplied values placed into standard header fields should be validated as **single-line text**. A defensive policy can:

- Require non-null and non-empty after trimming.
- Bound length to curb abuse and client errors.
- Reject `CR`, `LF`, and control characters.
- Reject Unicode line separators such as `U+2028` and `U+2029` when used as display fields.
- Reject Unicode bidirectional control characters when spoofing risks apply to the product.
- Never log rejected raw inputs verbatim.

### 6.1. A reusable validator

```java
package com.example.mail.security;

import java.util.Objects;

public final class MailHeaderValues {

    private MailHeaderValues() {
    }

    public static String singleLine(
            String fieldName,
            String raw,
            int maxLength) {

        Objects.requireNonNull(fieldName, "fieldName");
        if (raw == null) {
            throw new IllegalArgumentException(
                    fieldName + " must not be null");
        }

        String value = raw.strip();
        if (value.isEmpty() || value.length() > maxLength) {
            throw new IllegalArgumentException(
                    fieldName + " has invalid length");
        }

        for (int offset = 0; offset < value.length();) {
            int cp = value.codePointAt(offset);

            boolean forbidden =
                    Character.isISOControl(cp)
                    || cp == 0x2028      // LINE SEPARATOR
                    || cp == 0x2029      // PARAGRAPH SEPARATOR
                    || (cp >= 0x202A && cp <= 0x202E)
                    || (cp >= 0x2066 && cp <= 0x2069);

            if (forbidden) {
                throw new IllegalArgumentException(
                        fieldName + " contains unsafe characters");
            }

            offset += Character.charCount(cp);
        }

        return value;
    }
}
```

This policy is intentionally strict: tabs or control characters inside header inputs are rejected. That does not mean every rejected character causes injection in every mail client; it reduces risk for values expected to span only one line.

`Character.isISOControl` covers CR, LF, and other control characters. Bidirectional control characters are additionally blocked to reduce visual spoofing risks. If a product needs to support a special character set, design per-field policies matching business needs instead of dropping validation altogether.

### 6.2. Why reject rather than silently repair?

Suppose the input is:

```text
New order\r\nBcc: audit@example.invalid
```

If code merely strips `\r\n`, the value becomes `New orderBcc: audit@example.invalid`. It no longer opens a new header, yet its semantics were altered and it may show up in customer-facing messages.

For structured fields or security-relevant data, **rejecting invalid input** and requiring correction is easier to govern. If the product requires whitespace normalization (such as collapsing multiple spaces into one), define it explicitly and still validate afterward.

Never use this header validator on email bodies: `text/plain` and `text/html` bodies legitimately contain newlines. Each input sink needs context-appropriate protection.

## 7. Validating recipient addresses with `InternetAddress`

Email addresses have specific syntax, not merely “any string with an `@`”. Jakarta Mail provides `InternetAddress` to parse and validate mailbox syntax.

Example:

```java
package com.example.mail.security;

import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailAddresses {

    private MailAddresses() {
    }

    public static InternetAddress singleMailbox(
            String raw) throws AddressException {

        String value = MailHeaderValues.singleLine(
                "recipient", raw, 320);

        InternetAddress address = new InternetAddress(value, true);
        address.validate();

        if (address.isGroup()
                || address.getAddress() == null
                || !value.equals(address.getAddress())) {
            throw new AddressException(
                    "Expected a single mailbox address");
        }

        return address;
    }
}
```

In this example, the policy accepts **one plain mailbox address**, rejecting strings like `"Alice <alice@example.net>"` or multi-address lists. If an API truly supports display names or recipient lists, parse that structure explicitly with the right API and check authorization for every mailbox.

`InternetAddress.validate()` is a **syntax** check; it does not check whether the mailbox exists, whether the domain accepts mail, or whether the user is allowed to send to that address. Recipient lists, domains, tenants, and consent remain application-layer policies.

### 7.1. Never let a Subject field decide `To`, `Cc`, `Bcc`

For instance, an invoice-sending API might accept:

```json
{
  "invoiceId": "2f86c36d-028a-47c0-9e7b-9307bb46e14f"
}
```

The application retrieves the verified recipient from the invoice record instead of letting the client pass all of:

```json
{
  "to": "...",
  "cc": "...",
  "bcc": "...",
  "from": "...",
  "replyTo": "...",
  "headers": {"...": "..."}
}
```

Reducing input control prevents both header injection and out-of-scope email abuse. For newsletter or list-sending systems, you still need permission checks, recipient caps, quotas, and consent policies.

### 7.2. Recipient lists should be typed collections

If the application permits sending to multiple addresses, do not accept a CSV string and concatenate it:

```java
// Avoid manual concatenation.
String to = String.join(",", recipientsFromRequest);
```

Instead, validate every element:

```java
List<InternetAddress> parsed = recipients.stream()
        .map(raw -> {
            try {
                return MailAddresses.singleMailbox(raw);
            } catch (AddressException ex) {
                throw new IllegalArgumentException(
                        "Invalid recipient address");
            }
        })
        .toList();

helper.setTo(parsed.toArray(InternetAddress[]::new));
```

This is a Java 17+ example; `recipients` must be length-bounded and authorized before calling. Duplicate addresses should not be added multiple times unless business rules require it.

## 8. Protecting `Subject` and Unicode display names

`Subject` often combines fixed text with a business field:

```java
String subject = "Order " + order.getDisplayCode();
```

If `getDisplayCode()` comes from external input, validate it before placing it in a header even if the field was already saved in the database.

```java
String orderCode = MailHeaderValues.singleLine(
        "orderCode", order.getDisplayCode(), 80);
String subject = MailHeaderValues.singleLine(
        "subject", "Order confirmation " + orderCode, 200);

helper.setSubject(subject);
```

If an order code may contain only digits, Latin letters, and hyphens, enforcing a stricter domain rule is even better. Do not rely on a generic text validator instead of domain validation when an exact format exists.

### 8.1. Unicode is not injection

A Vietnamese email subject such as `"Thông báo đã nhận đơn hàng"` is valid data. Never try to prevent header injection by stripping all non-ASCII characters; that breaks legitimate content without addressing the root cause of raw string concatenation.

`MimeMessageHelper` lets you configure the charset so Jakarta Mail encodes Unicode headers according to standards:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");
helper.setSubject("Xác nhận đơn hàng của bạn");
```

The application should never manually construct encoded-words like `=?UTF-8?B?...?=` for `Subject`. Nor should it insert newlines manually to fold long lines; the library owns encoding and folding.

### 8.2. Sender display names

A display name like “Dịch vụ Khách hàng” should be validated as single-line and attached to `InternetAddress` via the API:

```java
String displayName = MailHeaderValues.singleLine(
        "senderName", "Dịch vụ Khách hàng", 120);

InternetAddress sender = new InternetAddress(
        "no-reply@example.org",
        displayName,
        "UTF-8");
helper.setFrom(sender);
```

In multi-tenant systems, never let tenants supply arbitrary unverified `From` addresses. Sending addresses must belong to identities/domains permitted by the provider and enterprise policy.

## 9. Separating control of `From` and `Reply-To`

Users should not be allowed to change `From` arbitrarily just because the email originates from the system. A safer design:

- `From` comes from verified sender configuration.
- `Reply-To`, when supported by a feature, must be parsed and authorized for that purpose.
- `To` comes from valid business recipients.
- `Cc`/`Bcc` are set only by explicit rules, never parsed out of a `Subject`/body string.

Example:

```java
helper.setFrom("support@example.org");
helper.setTo(customerAddress);
helper.setReplyTo("support@example.org");
```

If a contact form wants replies to go directly to the form submitter, it might allow a validated address in `Reply-To`. However, assess risks of impersonation, emailing third parties, or abusing auto-responders.

A cautious design sets `Reply-To` to a company-controlled support mailbox while storing the user's contact address in the authorized business system. Not every “syntactically valid” address is permitted as a reply destination.

### Never add `Return-Path` manually

`Return-Path` relates to the envelope/transport return path and is normally added by the receiving MTA according to the sending system's rules. Never let clients control `Return-Path` via custom headers. To configure the envelope sender/bounce address, use official SMTP provider or Jakarta Mail transport features under controlled policy.

## 10. Blocking injection via custom headers

Custom headers can record correlation IDs or reconciliation metadata:

```java
message.setHeader("X-Correlation-ID", jobId.toString());
```

If header names or values are taken verbatim from requests, risk rises:

```java
// Anti-pattern.
message.addHeader(request.headerName(), request.headerValue());
```

`MimeMessage.setHeader(...)` and `addHeader(...)` are low-level APIs. Do not assume they perform all authorization and field-semantics checks needed by your application.

### 10.1. Header names must be allowlisted

To prevent clients from requesting `Bcc`, `From`, or `Content-Type`, never expose an “add arbitrary header” API to users. Use fixed field names in code:

```java
public static final String CORRELATION_HEADER = "X-Correlation-ID";

message.setHeader(
        CORRELATION_HEADER,
        jobId.toString());
```

If multiple headers are genuinely needed, place them in a system-managed enum/catalog. RFC header names have their own syntax; a conservative regex for internal custom names might be `^[A-Za-z0-9-]+$`, yet a **field-name allowlist** remains far more important than a generic regex.

### 10.2. Header values must be strongly typed

Example UUID-typed correlation ID:

```java
UUID correlationId = UUID.fromString(request.correlationId());
message.setHeader("X-Correlation-ID", correlationId.toString());
```

The code does not take an arbitrary raw string and turn it into a header. If a user submits a string containing newlines or extra fields, `UUID.fromString(...)` rejects it.

If a custom header holds free-form text, use the single-line validator and proper API encoding/serialization. Never concatenate strings containing `\r\n` into multiple headers manually.

### 10.3. Be careful with `Message-ID` and `Content-ID`

`Message-ID` identifies a message; `Content-ID` references inline MIME parts. Never construct them from untrusted user strings or inject arbitrary payloads between `<...>`.

For inline images, use:

```java
helper.setText(
        "<p>Logo:</p><img src=\"cid:brand-logo\" alt=\"Logo\">",
        true);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

`brand-logo` is an application-controlled `Content-ID`, not arbitrary client data. If multiple dynamic images are needed, generate safe identifiers inside the application and ensure they match `cid:...` references in HTML.

## 11. Attachment filenames and MIME parameter injection

Attachment filenames are typically represented in MIME parameters such as `filename` on `Content-Disposition`. If an external filename contains quotes, semicolons, control characters, or paths, raw header concatenation can corrupt the structure:

```java
// Do not build Content-Disposition like this.
String rawHeader = "Content-Disposition: attachment; filename=\""
        + userFilename + "\"\r\n";
```

A dangerous filename can also leak server paths or cause errors when recipients save the file. Generate display names from controlled data and let the API build the MIME part.

Example:

```java
String filename = "invoice-" + invoiceNumber + ".pdf";
filename = MailHeaderValues.singleLine(
        "filename", filename, 160);

if (filename.indexOf('/') >= 0
        || filename.indexOf('\\') >= 0) {
    throw new IllegalArgumentException(
            "Filename must not contain path separators");
}

helper.addAttachment(
        filename,
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf");
```

In the example, `invoiceNumber` should also be validated per domain rules (only permitted letters/digits and separators) rather than relying solely on the final check. Never use `Path.toString()` or local file paths as attachment names.

If filenames contain Unicode, mail libraries can encode parameters using appropriate mechanisms; mail clients vary in compatibility. Do not manually embed encoded-words or raw CRLF into filenames to “fix” compatibility issues.

## 12. Do not confuse header injection with HTML injection

The two data types are handled in two different contexts:

```java
// Header: must be a single-line value, using mail APIs.
helper.setSubject(validatedSubject);

// HTML body: needs escaping per HTML/template context.
helper.setText(renderedHtml, true);
```

Preventing header injection **does not replace HTML escaping**. If a user enters:

```html
<img src="https://external.example.invalid/tracker">
```

and the application inserts it directly into HTML, that is an HTML/template content issue, not CRLF creating a new header. Use a template engine with context-aware escaping and control permitted URLs/HTML.

Conversely, HTML-escaping `<`, `>`, and `&` in `Subject` is insufficient against CR/LF header injection. Apply each defense where it belongs:

| Data | Boundary | Appropriate measure |
|---|---|---|
| `Subject` | Email header value | Single-line validation + `setSubject` |
| `From`/`To`/`Reply-To` | Mailbox/address | Single-line validation + `InternetAddress` + authorization |
| Display name | Address header phrase | Validation + API name encoding |
| Filename | MIME parameter | Filename policy + `addAttachment` |
| `Content-ID` | MIME identifier | App-generated ID + `addInline` |
| HTML body | HTML markup | Template escaping + URL policy |
| Text body | Plain text | Business length/content limits; newlines permitted |
| Raw MIME | Message structure | Never accept from clients; library serializes |

A single “sanitize all strings” call that strips special characters can both break valid data and still be insufficient for individual contexts.

## 13. Spring Mail example: a service building emails safely

Suppose an application sends registration confirmation emails. Clients may pass only required registration details; recipients and sending addresses come from verified sources. The service never accepts arbitrary header lists.

### 13.1. Defining request and business data

```java
package com.example.mail;

import java.util.UUID;

public record RegistrationMailCommand(
        UUID registrationId,
        String recipientEmail,
        String customerName,
        String confirmationCode) {
}
```

This record illustrates an internal payload created by an application service, **not a DTO to bind straight from an HTTP request** without authorization checks. Fields like `confirmationCode` need dedicated formatting rules and must never be logged.

### 13.2. Service constructing `MimeMessage`

```java
package com.example.mail;

import com.example.mail.security.MailAddresses;
import com.example.mail.security.MailHeaderValues;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailService {

    private final JavaMailSender sender;
    private final String verifiedFrom;

    public RegistrationMailService(
            JavaMailSender sender,
            @Value("${app.mail.verified-from}") String verifiedFrom) {
        this.sender = sender;
        this.verifiedFrom = verifiedFrom;
    }

    public void sendConfirmation(RegistrationMailCommand command)
            throws MessagingException {

        InternetAddress to =
                MailAddresses.singleMailbox(command.recipientEmail());
        InternetAddress from =
                MailAddresses.singleMailbox(verifiedFrom);

        String customerName = MailHeaderValues.singleLine(
                "customerName", command.customerName(), 120);

        // A business code may have a stricter policy.
        String confirmationCode = MailHeaderValues.singleLine(
                "confirmationCode", command.confirmationCode(), 80);
        String subject = MailHeaderValues.singleLine(
                "subject", "Registration confirmation", 200);

        String plainText = """
                Hello %s,

                Your confirmation code: %s
                Do not share this code with others.
                """.formatted(customerName, confirmationCode);

        // Dynamic data in HTML must be escaped separately.
        String html = """
                <html lang="en">
                  <body>
                    <p>Hello %s,</p>
                    <p>Confirmation code: <strong>%s</strong></p>
                    <p>Do not share this code with others.</p>
                  </body>
                </html>
                """.formatted(
                escapeHtml(customerName),
                escapeHtml(confirmationCode));

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom(from);
        helper.setTo(to);
        helper.setSubject(subject);
        helper.setText(plainText, html);

        sender.send(message);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
```

Here:

- `From` comes from verified sender configuration.
- `To` is validated as a syntactically valid single mailbox.
- `Subject` is a single-line string decided by the application.
- Customer name is never placed arbitrarily into headers; it is validated and escaped for the body context.
- `helper.setText(plainText, html)` builds alternative bodies without raw MIME concatenation.
- `JavaMailSender` handles serializing and sending the message.

This example demonstrates the sending flow and does not replace secure verification-code design: confirmation codes must come from a strong generator with expiration, attempt limits, revocation state, and no log exposure. For complex HTML, use a template engine with auto-escaping rather than building HTML with `String.formatted(...)`.

**Note:** `MimeMessageHelper(message, false, charset)` disables multipart and is unsuitable when sending both `text/plain` and `text/html` via `setText(plain, html)`. The example uses `true` to create multipart structure; if you need control over part nesting, choose an explicit multipart mode as shown next.

### 13.3. Explicitly choosing a multipart mode

To send both plain text and HTML, construct the helper in multipart mode:

```java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom(from);
helper.setTo(to);
helper.setSubject(subject);
helper.setText(plainText, html);
sender.send(message);
```

`MULTIPART_MODE_MIXED_RELATED` supports multipart layouts when alternative bodies, inline resources, and attachments are needed. For emails without attachments, you can pick another suitable mode—never build `multipart/alternative` via raw string concatenation.

## 14. Controlling inputs at the API boundary

Validation in the mail service is an important safeguard, yet the API accepting inputs must also restrict what can be requested.

### 14.1. Do not accept objects with arbitrary `headers` fields

Avoid an API like:

```json
{
  "smtpServer": "...",
  "from": "...",
  "to": "...",
  "subject": "...",
  "headers": {
    "Any-Header": "Any-Value"
  },
  "rawMime": "..."
}
```

Unless you are building a specialized mail relay service with strict controls, this API grants far too much authority to clients. Instead, accept business fields:

```json
{
  "orderId": "31b72f8d-621a-4420-aa06-a3de7fe10c92"
}
```

The application service verifies access rights to the order, derives the permitted recipient, and selects a fixed template, subject, and `From`/`Reply-To`.

### 14.2. Bean Validation is only one layer

You can add constraints on DTOs:

```java
public record ContactFormRequest(
        @NotBlank
        @Size(max = 120)
        String displayName,

        @NotBlank
        @Email
        String replyEmail,

        @NotBlank
        @Size(max = 5000)
        String message) {
}
```

Annotations like `@Email` and `@Size` help check format and length, yet **do not replace single-line validation, address parsing, and `Reply-To` authorization**. An email annotation/regex may allow many spec-valid forms that violate your product's internal policy.

### 14.3. Enforce input checks where data is used

A field may travel through multiple layers:

```text
HTTP request
   |
   v
Validation DTO
   |
   v
Application service / database
   |
   v
Mail job / event
   |
   v
Mail worker
   |
   v
MimeMessageHelper / Jakarta Mail
```

Controller validation returns errors early, yet the mail worker should still validate outbound header data because jobs might arrive from other sources, legacy stored data, or external events. Never treat queue data as “already trusted” solely because it came from inside the network.

## 15. Handling errors: fail closed and do not send

When an invalid header value is detected, the standard response is **not creating/sending that message**.

Example:

```java
try {
    String subject = MailHeaderValues.singleLine(
            "subject", userSuppliedSubject, 200);
    helper.setSubject(subject);
} catch (IllegalArgumentException ex) {
    audit.recordRejectedMailInput(mailJobId, "SUBJECT_INVALID");
    throw new InvalidMailInputException(
            "Mail request contains invalid header data");
}
```

In public APIs, return an appropriate validation error response rather than echoing the raw invalid value or stack trace. In queue workers, transition unfixable jobs to a permanent failure state; never infinitely retry an unchanging injection payload.

### Distinguishing data errors from temporary SMTP errors

| Error type | Retry? | How to handle |
|---|---|---|
| `Subject` contains newline | Not automatically | Reject input, fix source |
| Recipient contains control chars | Not automatically | Reject/mark invalid |
| Custom header name not in allowlist | No | Do not add header |
| MIME part filename violates policy | Not automatically | Reject/normalize per policy |
| SMTP timeout | Possibly | Retry with backoff/deadline |
| SMTP rate limit 4xx | Possibly | Slow down per provider policy |
| SMTP AUTH failure | Do not retry blindly | Check credentials/configuration |

Never turn `InvalidMailInputException` into a “temporary SMTP” error and re-enqueue it indefinitely. It is a policy or data error, not network infrastructure.

## 16. Logging and monitoring when header injection is detected

Suspected injection inputs may contain email addresses, tokens, or personal data. Never log raw payloads:

```java
// Do not do this:
log.warn("Rejected suspicious subject: {}", rawSubject);
```

Emit a normalized event:

```java
log.warn(
        "mail_input_rejected jobId={} field={} reason={}",
        jobId,
        "subject",
        "UNSAFE_HEADER_CONTROL_CHARACTER");
```

You can also track metrics:

| Metric | Meaning |
|---|---|
| `mail.header_validation.rejected` | Count of blocked invalid header values |
| `mail.recipient_validation.failed` | Count of email addresses failing policy |
| `mail.send.attempts` | Count of sends actually initiated |
| `mail.send.rejected_by_policy` | Count of jobs rejected before SMTP |
| `mail.smtp.submit_failed` | Count of infrastructure/provider submission errors |

Keep tags low-cardinality: `field=subject/from/to/reply_to` and `reason=control_char/invalid_address/unauthorized_sender`. Never put raw subjects, recipients, arbitrary job IDs, payloads, or exception messages into metric labels.

If rejected inputs spike suddenly, the system may be experiencing injection probing or an integration bug. Detection should trigger investigation and rate limiting—never printing raw payloads into logs for analysis.

## 17. Testing protection against CRLF header injection

Tests should verify both validation rejections and that constructed emails contain no unexpected fields. Prefer dummy values and never send to real SMTP.

### 17.1. Unit tests for header values

JUnit 5 example:

```java
package com.example.mail.security;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MailHeaderValuesTest {

    @Test
    void rejectsCrLfAndStandaloneNewlines() {
        String[] inputs = {
                "Order\r\nBcc: unexpected@example.invalid",
                "Order\nBcc: unexpected@example.invalid",
                "Order\rBcc: unexpected@example.invalid",
                "Order\u2028Bcc: unexpected@example.invalid",
                "Order\u2029Bcc: unexpected@example.invalid"
        };

        for (String input : inputs) {
            assertThrows(
                    IllegalArgumentException.class,
                    () -> MailHeaderValues.singleLine(
                            "subject", input, 200));
        }
    }

    @Test
    void acceptsVietnameseSubject() {
        String subject = "Xác nhận đơn hàng tháng Mười Một";

        assertEquals(
                subject,
                MailHeaderValues.singleLine(
                        "subject", subject, 200));
    }

    @Test
    void rejectsNullOrBlank() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.singleLine(
                        "subject", null, 200));
        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.singleLine(
                        "subject", "  ", 200));
    }
}
```

This test only exercises the validator function. An integration test should build messages through the project's actual mail service and ensure no extra input-injected headers appear.

### 17.2. Unit tests for mailboxes

```java
import static org.junit.jupiter.api.Assertions.*;
import jakarta.mail.internet.AddressException;
import org.junit.jupiter.api.Test;

class MailAddressesTest {

    @Test
    void acceptsSingleMailbox() throws Exception {
        assertEquals(
                "alice@example.net",
                MailAddresses.singleMailbox(
                        "alice@example.net").getAddress());
    }

    @Test
    void rejectsInjectedAdditionalHeader() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailAddresses.singleMailbox(
                        "alice@example.net\r\nBcc: extra@example.invalid"));
    }

    @Test
    void rejectsMailboxListInSingleMailboxField() {
        assertThrows(
                AddressException.class,
                () -> MailAddresses.singleMailbox(
                        "alice@example.net, bob@example.net"));
    }
}
```

Depending on parser paths, the exact exception may be `AddressException` or a policy exception; application tests should verify the exact error contract and ensure unchecked input never reaches the sending library.

### 17.3. Checking headers after constructing `MimeMessage`

You can use an in-memory `Session` without an SMTP connection:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.springframework.mail.javamail.MimeMessageHelper;

Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);

MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8");
helper.setFrom("no-reply@example.org");
helper.setTo("alice@example.net");
helper.setSubject(
        MailHeaderValues.singleLine(
                "subject", "Registration confirmation", 200));
helper.setText("Test content", false);
message.saveChanges();

// In tests, iterate over application-permitted headers and
// confirm no headers were generated from invalid input.
```

For end-to-end tests, use a fake/recording mail sender or an SMTP sink like Mailpit. Never use production accounts to test CRLF payloads and never send test data to real customer mailboxes.

### 17.4. Cases to cover

| Case | Expectation |
|---|---|
| `Subject` containing `\r\nBcc:...` | Rejected before SMTP |
| `Subject` containing standalone `\n` or `\r` | Rejected |
| `Subject` containing Unicode line separator | Rejected per policy |
| Valid Vietnamese `Subject` | Sent properly after encoding |
| Recipient containing CRLF | Rejected |
| Recipient containing multiple mailboxes when single allowed | Rejected |
| `Reply-To` outside policy | Rejected |
| Client-supplied custom header name | Not accepted or blocked by allowlist |
| Filename containing CRLF | Rejected |
| Filename containing path separator | Rejected per policy |
| Plain-text body containing newlines | Remains valid |
| HTML body containing user input | Escaped per HTML context |
| Job replayed from queue with stale data | Validation still runs in worker |
| Invalid header encountered during retry | Marked as data failure, never retried endlessly over SMTP |

## 18. Header injection is not automatically blocked by SPF, DKIM, or DMARC

Email authentication mechanisms serve different goals:

| Mechanism | What does it solve? | Replaces header input validation? |
|---|---|---|
| SMTP AUTH | Client is allowed to use the SMTP submission server | No |
| STARTTLS / implicit TLS | Protects the SMTP connection per configuration | No |
| SPF | Checks authorized sending sources for the envelope domain | No |
| DKIM | Cryptographic signature verifying certain headers/body per signing policy | No |
| DMARC | Alignment policy based on SPF/DKIM and the `From` domain | No |
| Header validation + structured API | Prevents input from opening extra fields or altering structure | Yes, directly targets it |

A message produced by an SMTP-authenticated backend can still carry unauthorized content or headers if the application put them in the message. DKIM will happily sign that malformed message; a signature does not prove `Subject` or `Reply-To` were authorized by users.

Therefore, header injection prevention must happen **before the message is serialized and sent**, not solely at the DNS authentication or mail gateway layer.

## 19. Distinguishing header injection and SMTP command injection

These two issues are related yet exist at different layers:

**Header injection** alters the structure or fields inside an Internet Message, such as opening an extra header from `Subject`.

**SMTP command injection** attempts to turn unintended data into SMTP protocol commands, such as tampering with `MAIL FROM`, `RCPT TO`, or `DATA` when an application hand-rolls a raw socket protocol.

`JavaMailSender`/Jakarta Mail executes SMTP transport via structured APIs, helping avoid building protocol commands from strings. Still, the application must validate inputs and sending permissions.

Never treat “using an authenticated SMTP connection” as a sufficient security boundary. The SMTP server does not know which user in your application was permitted to create an email or redirect `Reply-To`.

## 20. Common errors and remediation

| Symptom | Possible cause | Remediation |
|---|---|---|
| Unexpected `Bcc` field appears | Data concatenated into raw MIME/headers | Stop concatenating headers, check for CRLF |
| `Subject` contains strange lines | Input contained newlines/control chars | Reject non-single-line values |
| Out-of-scope recipients | `To`/`Cc`/`Bcc` taken from client without authorization | Pull recipients from authorized business records |
| `Reply-To` points to unwanted mailbox | Users allowed to set arbitrary `Reply-To` | Parse address and enforce policy |
| Unicode headers display broken | Manual encoding/folding | Use UTF-8 charset and Jakarta Mail serialization |
| Filename breaks MIME | Manual `Content-Disposition` concatenation | Use `addAttachment` and filename policy |
| User content becomes a new header | Raw message concatenation with CRLF | Validation and typed APIs |
| Not blocked after stripping `\r\n` | Standalone CR/LF or other controls remain | Check code points and fail closed |
| Syntactically valid email with spoofed sender | Uncontrolled `From`/`Reply-To` | Verified senders and authorization |
| Queue retries bad-header job forever | Invalid input classified as temporary SMTP error | Move job to permanent validation failure |
| Logs contain full injection payload | Logging raw subject/exceptions | Log field/reason codes, never raw input |
| Checked only in controller, replay still fails | Validation skipped in worker | Validate where MIME is constructed |
| Email has DKIM yet wrong headers | Confusing domain auth with input validation | Validate message before signing/sending |

### Procedure when suspicious input is detected

1. Halt creating messages from data identified as invalid.
2. Record a rejection event with `jobId`, field name, and standardized error type; never record the raw value.
3. Distinguish ordinary typing errors from repeated attack patterns.
4. Rate-limit and check authorization of the requesting source.
5. Inspect other email-creation paths (admin panels, queue workers, import tools, webhooks).
6. If unintended emails were already sent, treat it as an appropriate mail-sending/data-exposure incident, checking provider logs and recipient permissions.
7. Add tests to prevent recurrence.

## 21. Key principles to remember

1. Never let clients submit raw MIME or an arbitrary header map unless business rules strictly require it.
2. Never concatenate `Subject`, `From`, `To`, `Reply-To`, `Content-Type`, or `Content-Disposition` with strings.
3. For user-supplied header values, enforce single-line text and reject CR/LF/control characters.
4. Parse mailboxes with `InternetAddress`; add authorization, sender verification, and recipient policies.
5. Use `MimeMessageHelper` to set standard headers, text/HTML, inline images, and attachments.
6. Let Jakarta Mail handle charset encoding and line folding; never insert newlines manually into Unicode Subjects.
7. For custom headers, use fixed/allowlisted field names and typed values, never arbitrary raw strings.
8. Treat data from databases, queues, and partners as untrusted at the MIME-building boundary.
9. Reject bad input instead of trying to send anyway; never infinitely retry validation errors.
10. Avoid logging injection payloads/recipients/subjects and track rejections with safe metrics.
11. Test CRLF, standalone CR/LF, Unicode separators, attachment names, and multiple recipients.
12. Never confuse SPF/DKIM/DMARC, TLS, or SMTP AUTH with header input validation.

## 22. Frequently asked questions

**What is header injection?** It is when data intended to stay inside a single header value gets interpreted as a new header or alters the header/body boundary, commonly via CRLF when an application concatenates raw emails.

**Is blocking the `\r\n` sequence alone enough?** No. Reject standalone CR, standalone LF, and control chars unsuitable for single-line header values. Avoid relying on a single string replacement.

**Should Vietnamese be banned in Subject?** No. Vietnamese is valid content; use UTF-8 and Jakarta Mail's header encoding/folding APIs.

**If I already use `MimeMessageHelper`, do I still need validation?** Yes. The helper offers a structured API, yet does not enforce authorization, sender policies, `Reply-To` rules, or app-specific length/syntax rules. Low-level APIs can also bypass business checks.

**Should I use a simple email regex like `.+@.+`?** Do not treat that as complete validation. Use a mailbox parser such as `InternetAddress`, policy validation, and permission checks.

**Why shouldn't `Subject` be concatenated into a raw string?** Because newlines in input can be parsed as boundaries between headers. `helper.setSubject(...)` separates values from message structure far better.

**Should customers be allowed to choose the `From` email?** Only if the system has sender/domain verification and clear authorization. Usually, use a verified `From` address from configuration.

**Does `Reply-To` carry risks?** Yes. Even without opening a new header, an out-of-policy `Reply-To` can trick recipients into sending sensitive replies to an attacker-controlled address.

**Does Bcc injection always send extra emails?** Not necessarily. SMTP envelope recipients may be separate from display headers, and transports may strip or ignore `Bcc` headers. Still, never rely on that to allow unauthorized header tampering.

**Can attachment filenames come from users?** Yes, if validated against a filename policy removing path separators/control chars and attached via `MimeMessageHelper.addAttachment(...)`. Avoid building `Content-Disposition` manually.

**Is an `X-Correlation-ID` header safe?** If the name is application-fixed and the value is a typed ID like a validly generated/parsed UUID, risk is low. Never accept arbitrary names/values from requests.

**Can `Subject` be saved to the database and sent later without re-validating?** Do not assume stored data is always safe. Workers should validate header outputs when constructing messages, especially since jobs can originate from imports, webhooks, or older code versions.

**How does header injection differ from HTML injection?** Header injection manipulates email header syntax; HTML injection alters markup in the body. Separate escaping/validation strategies are needed for each context.

**Do SMTP AUTH or DKIM stop header injection?** No. They authenticate the sending client or domain/signature, without checking whether business inputs were safely placed into headers.

**When injection is detected, should the full payload be logged for investigation?** Not by default. Payloads can contain addresses or sensitive data; log the field, error category, job ID, and needed metadata, and handle detailed diagnostics through access-controlled workflows.

**Do tests require a real SMTP server?** No. Validators can be unit-tested in plain Java; MIME can be built with an in-memory Jakarta Mail `Session` or tested via fake senders/SMTP sinks. Never send test payloads to real mailboxes.

## 23. Related technical references

- **Spring Framework Mail:** `JavaMailSender` and `MimeMessageHelper`, especially `setSubject`, `setTo`, `setReplyTo`, `addInline`, and `addAttachment`.
- **Jakarta Mail / Angus Mail:** `InternetAddress`, `MimeMessage`, header APIs, and MIME serialization.
- **RFC 5322 — Internet Message Format:** header field syntax, folding, and CRLF.
- **RFC 6532 — Internationalized Email Headers:** handling internationalized headers.
- **RFC 2045–2049 — MIME:** media types, encoding, and multipart structures.
- **RFC 2183 — Content-Disposition:** inline/attachment metadata and filenames.
- **OWASP Input Validation Cheat Sheet:** typed validation and allowlists.
- **OWASP Logging Cheat Sheet:** avoiding logging secrets, mitigating log injection, and managing sensitive data.
- **Spring Boot Validation:** Bean Validation in DTOs and enforcing data checks at application boundaries.

---

**Takeaway:** preventing header injection means ensuring **user data can never become email structure**. Never concatenate raw headers/SMTP commands; reject CR/LF/control characters in header values; parse addresses with `InternetAddress`; restrict who can alter `From`, `To`, `Reply-To`, and custom headers; and use `MimeMessageHelper`/Jakarta Mail to construct messages. Also test HTTP, database, and queue worker paths, because untrusted data can enter the mail pipeline from many different sources.

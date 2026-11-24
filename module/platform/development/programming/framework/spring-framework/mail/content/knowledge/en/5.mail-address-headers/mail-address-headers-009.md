# Header Injection and Input Validation

A Spring application can send emails using user-supplied data: contact addresses, sender names, subjects, reply text, order IDs, or attachment filenames. If that data is placed into an **email header** without validation, an attacker can attempt to inject newline characters so that one value is interpreted as multiple header fields. This is **email header injection**, commonly discussed alongside **CRLF injection**.

For example, a "Subject" field on a contact form should only become the value of the **Subject** header. Yet if an application builds header lines via string concatenation without checking input, a value containing a newline sequence can cause the trailing portion to be parsed as a new header.

In **Spring Framework Mail**, the primary defense is **explicitly defining which input fields are allowed to affect which headers, validating input per field type, and letting Jakarta Mail/Spring Mail construct the message structure**. The email library builds standards-compliant messages; the application remains responsible for controlling recipient authorization, sender addresses, custom values, and externally supplied content.

## 1. Where Do Email Headers Live?

An Internet message format email consists of a **header block**, a **blank line**, and a **body**. Example:

~~~text
From: support@example.org
To: customer@example.net
Reply-To: helpdesk@example.org
Subject: Request confirmation
Date: Thu, 12 Nov 2026 08:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

We have received your request.
~~~

The **From**, **To**, **Reply-To**, **Subject**, and **Content-Type** lines are headers. The blank line marks the boundary between headers and body.

At the email format level, lines are separated by the **CRLF** control sequence:

- **CR** (carriage return): `\r`, byte `0x0D`.
- **LF** (line feed): `\n`, byte `0x0A`.
- **CRLF**: `\r\n`, used to terminate a line per Internet message format.

An email's body can contain multiple lines of text. However, **input intended for a single-line header value** must never control where a header line ends and a new header begins.

### Headers Are Not the SMTP Envelope

Distinguish message structure from the SMTP transport protocol:

~~~text
SMTP envelope:
  MAIL FROM:<mailer@example.org>
  RCPT TO:<customer@example.net>

SMTP DATA:
  From: support@example.org
  To: customer@example.net
  Subject: Request confirmation

  Email content...
~~~

- **MAIL FROM / RCPT TO** are commands and addresses at the SMTP envelope layer.
- **From / To / Cc / Bcc / Reply-To / Subject** are fields tied to the message and sending behavior; some addresses are used by the library to derive envelope recipients.
- **MIME headers** such as Content-Type or Content-Disposition describe the structure and presentation of content parts.

Header injection targets how the **message header block** is constructed or parsed. It is related to—though distinct from—manipulating SMTP commands, manipulating recipients, or HTML injection in the body.

## 2. How Does Header Injection Happen?

Suppose a system manually builds a raw email like this:

~~~java
String rawMessage =
        "From: support@example.org\r\n"
      + "To: support-team@example.org\r\n"
      + "Subject: " + userInput + "\r\n"
      + "\r\n"
      + "Customer inquiry";
~~~

If **userInput** is a valid subject such as **Order support needed**, the result is a normal Subject.

However, if input contains a newline followed by text resembling a header field:

~~~text
Order support needed\r\nBcc: unexpected@example.net
~~~

the concatenated raw message can become:

~~~text
From: support@example.org
To: support-team@example.org
Subject: Order support needed
Bcc: unexpected@example.net

Customer inquiry
~~~

This illustrates **how syntax changes when an application concatenates strings unsafely**; it does not mean every library, SMTP server, or email client will accept or deliver the injected header. Actual behavior depends on parsers, normalization, libraries, and downstream controls.

The issue lies at the trust boundary: **the user is permitted to supply the content of Subject, not header structure or an extra Bcc**.

### Why Is `\r\n` Particularly Dangerous in Headers?

In a Java string, `\r` and `\n` produce CR and LF characters. When a system concatenates that string directly into the header region of a raw message, CRLF can terminate the current line, causing subsequent data to be parsed as a new field.

Newlines can enter from many sources:

- A textarea or HTTP request containing literal newline characters.
- Data imported from CSVs, webhooks, logs, or external services.
- Values that underwent URL or JSON decoding.
- Values loaded back from a database storing untrusted input.
- A header copied from an inbound email into a newly constructed email.

Hence, **data read from a database is not automatically safe**. Always inspect its origin and how it enters the final email.

### What Consequences Can Header Injection Cause?

Depending on the application and message-building pipeline, impacts can include:

1. **Adding or altering recipient headers** if the system parses injected headers and uses them for delivery.
2. **Spoofing displayed metadata**, such as sender name, Reply-To, or subject in certain pipelines.
3. **Corrupting MIME structure**, breaking how clients receive, render, or parse the email.
4. **Bypassing business logic**, such as sending order details outside an approved list if recipient determination has flaws.
5. **Corrupting logs or reports**, when control characters are echoed unsafely in mail-event logs.

Never assume a specific payload will always "sneak an email through": many implementations block newlines in headers, ignore recipients from injected headers, or reject malformed messages. The principle is **never let untrusted input dictate email structure**.

## 3. Fields That Require Attention

Not all fields in an email share the same validation rules. First determine **where the data goes**.

| Data | Example | Risk or Required Control |
| --- | --- | --- |
| **To / Cc / Bcc** | Recipient addresses | Reject unexpected multiple addresses, unauthorized display names, or unauthorized recipients |
| **From** | Sending address | Prevent users from claiming an organizational sender identity without authorization |
| **Reply-To** | Customer email for replies | Parse strictly as a single mailbox, rejecting newlines or unintended addresses |
| **Subject** | Inquiry title, order label | Block CR/LF and control characters; enforce length limits |
| **Display name (personal name)** | "Nguyễn An" | Check control characters, length, and rendering; let the library encode the header |
| **Custom header** | X-Request-Id | Never let external callers pick arbitrary header names or inject newlines in values |
| **MIME filename** | invoice.pdf | Avoid control characters, path segments, excessive length, and metadata leaks; use attachment APIs |
| **Plain-text body** | Support inquiry text | Newlines may be valid; keep separated from the header block |
| **HTML body** | Marketing email, HTML notice | Contextually escape/sanitize HTML; header validation does not protect HTML |

A common mistake is applying **a single generic "sanitize" function** to every field. Stripping newlines works for Subject yet ruins multi-line body text. Conversely, allowing newlines in a textarea does not justify allowing newlines in Subject.

## 4. Distinguishing Related Attack Types

### 4.1. Header Injection

Aims to alter header structure or values via input breaking out of a single field's bounds. The classic indicator is **CRLF** inside a value meant to be single-line.

### 4.2. SMTP Command Injection

Aims to alter commands at the SMTP protocol layer, such as commands manipulating the envelope or issued command sequence. This is a different layer from Internet message headers.

When using **JavaMailSender/Jakarta Mail**, the library typically generates SMTP commands. Never build raw SMTP sessions from user-supplied address strings. Even so, business-layer recipient authorization remains necessary: a syntactically valid address may still be an unauthorized recipient.

### 4.3. HTML Injection in the Body

If an email is sent as HTML:

~~~java
helper.setText(html, true);
~~~

then **html** is parsed as markup. Interpolating raw user input directly allows injecting HTML tags and attributes that alter rendered content. The defense is **contextual HTML escaping** or a template engine with proper escaping; if limited HTML is intentionally allowed, apply an explicit sanitizer policy.

Blocking **`\r\n`** in Subject does not stop HTML injection in the body. Conversely, HTML escaping does not replace CRLF validation in headers.

### 4.4. Sender Name and Address Spoofing

An email might display **“Accounting Department”** even though the actual address is an unrelated mailbox. This can mislead readers even without CRLF injection.

Therefore, applications must distinguish **display names** from **actual addresses**, and enforce which addresses are permitted in **From**, **Reply-To**, and **To/Cc/Bcc**.

## 5. Input Control Principles: Validate by Destination

A sound strategy applies as soon as external data enters any structurally significant field.

### 5.1. Accept Only One Mailbox When Only One Is Needed

If a **contact email** field expects a single address, never let a user enter:

~~~text
an@example.net, other@example.net
~~~

and pass that string to an API that parses recipient lists.

Likewise, variants with delimiters, display names, comments, or legacy syntax may be accepted by email parsers in some contexts, yet your application **does not have to accept everything a parser understands**. For a single-address input box, policy may require **a single bare mailbox without a display name**.

### 5.2. Reject CR, LF, and Control Characters in Single-Line Headers

Fields such as Subject, sender labels, display names, and custom codes should:

- Reject **CR** and **LF** characters coming from user input.
- Reject inappropriate control characters such as **NUL** and C0/C1 control characters per policy.
- Enforce length limits; avoid accepting megabytes in Subject.
- Apply field-specific rules: a request ID may allow only UUID/ASCII, whereas Subject may allow Vietnamese diacritics and emojis.
- Return clear validation errors rather than silently "fixing" dangerous input and pretending the user entered valid data.

**Note:** email standards allow long headers to be **folded** per RFC rules, and Unicode names/subjects can be encoded into transport-safe forms. That **does not mean** you should accept raw CRLFs from users. Let Jakarta Mail generate folding and encoding from validated values.

### 5.3. Do Not Rely on "Stripping `\r` and `\n`" Alone

Code like the following is not a complete policy:

~~~java
String cleaned = input.replace("\r", "").replace("\n", "");
~~~

It can turn malicious input into an unintended concatenated string and ignores other control characters, length limits, and invalid states. In many cases, **rejecting invalid input** is cleaner: the user is prompted to fix the subject, and the system never sends silently altered data.

You may normalize whitespace or trim fields where permitted, provided **validation runs before or alongside normalization** and never mutates invalid input into a different recipient.

### 5.4. Do Not Use an Overly Simple Regex to "Validate All Email Addresses"

A regex like:

~~~regex
.+@.+
~~~

is inadequate for parsing address syntax in real-world scenarios. Conversely, a massive regex attempting to cover the entire email RFC is hard to maintain and still cannot replace a dedicated parser.

In Java, use **jakarta.mail.internet.InternetAddress** to parse and validate addresses, then **enforce additional business rules**: a single mailbox, no display name if the field expects bare addresses, no control characters, appropriate length, and an allowed domain/recipient.

**Valid syntax does not mean the mailbox exists**, does not prove ownership, and does not guarantee the SMTP server will accept the email.

### 5.5. Limit Length, Count, and Sending Authority

Validation should also cover:

- Length bounds for Subject, display name, filename, and custom header values.
- Limits on recipients per request, total email size, and sending rate.
- Authority over sender/recipient addresses: ordinary users must not set Bcc to arbitrary addresses unless business rules allow it.
- Domain or account allowlists if the application sends only within a defined scope.
- Consistency between a verified profile address and the address supplied in a request.

These limits mitigate mail-service abuse even when input contains no CRLFs.

## 6. Using Spring Mail APIs to Avoid String-Built Headers

Spring Framework Mail is typically used through **JavaMailSender** and **MimeMessageHelper**, which expose methods tailored to specific fields:

~~~java
helper.setFrom("noreply@example.org");
helper.setTo("support@example.org");
helper.setReplyTo("customer@example.net");
helper.setSubject("Support request");
helper.setText("Response details", false);
~~~

The benefit is passing **field values** to the library rather than manually concatenating:

~~~text
From: ...
To: ...
Subject: ...

Body...
~~~

The library handles Internet message formatting, MIME, encoding, and transport delivery.

However, **field-specific APIs do not verify business validity**. For instance, a recipient setter may accept a syntactically valid yet unauthorized address; an oversized Subject or control character may behave differently across library versions. Thus, **input validation and authorization must still live in the application**.

### APIs to Recognize

| API | Appropriate Use |
| --- | --- |
| **MimeMessageHelper.setTo(...)** | Sets primary recipients |
| **setCc(...) / setBcc(...)** | Sets carbon-copy / blind-copy recipients |
| **setFrom(...)** | Sets sender address, optionally with display name |
| **setReplyTo(...)** | Sets reply destination address |
| **setSubject(...)** | Sets message subject |
| **setText(..., false)** | Sets plain-text body |
| **setText(..., true)** | Sets HTML body |
| **addAttachment(...)** | Creates attachment part with corresponding MIME metadata |
| **MimeMessage.setHeader(...)** | Sets a header directly; requires strict control of name and value |

Never switch from **setSubject()** to **setHeader("Subject", manuallyConcatenatedData)** just to bypass helper validation or encoding.

## 7. Spring Boot Example: Contact Form Sending to a Fixed Support Mailbox

Suppose a website has a contact form with:

- **email**: customer address for staff replies.
- **name**: customer name.
- **subject**: inquiry title.
- **message**: multi-line message body.

The application must only send to **support@example.org**. Users cannot choose To, Cc, Bcc, or From. The customer's email appears in **Reply-To** only after being validated as a single mailbox.

### 7.1. Request Model

~~~java
public record ContactRequest(
        String email,
        String name,
        String subject,
        String message
) {}
~~~

Do not let clients submit **from**, **to**, **bcc**, or **mailHeaders** fields in the request if the business flow does not use them. DTO design is a vital step in reducing the surface for untrusted input to influence email structure.

### 7.2. Mail Service with Per-Field Validation

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ContactMailService {

    private final JavaMailSender mailSender;

    public ContactMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(ContactRequest request) throws MessagingException {
        if (request == null) {
            throw new IllegalArgumentException("Missing contact request");
        }

        String replyTo = requireSingleMailbox(request.email());
        String name = requireSingleLine(request.name(), "Name", 100);
        String subject = requireSingleLine(
                request.subject(), "Subject", 160
        );
        String body = requireBody(request.message());

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        helper.setFrom("noreply@example.org");
        helper.setTo("support@example.org");
        helper.setReplyTo(replyTo);
        helper.setSubject("Contact: " + subject);

        helper.setText(
                "Customer name: " + name + "\n"
                + "Contact email: " + replyTo + "\n\n"
                + body,
                false
        );

        mailSender.send(message);
    }

    private static String requireSingleMailbox(String raw) {
        String value = requireSingleLine(
                raw, "Email", 254
        );

        try {
            InternetAddress[] addresses =
                    InternetAddress.parse(value, true);

            if (addresses.length != 1) {
                throw new IllegalArgumentException(
                        "Only one email address is allowed"
                );
            }

            InternetAddress address = addresses[0];
            address.validate();

            // Allow only a single bare mailbox without display name
            // or address list.
            if (address.getPersonal() != null
                    || !value.equals(address.getAddress())) {
                throw new IllegalArgumentException(
                        "Email must be a single mailbox address"
                );
            }

            return address.getAddress();
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid email address", ex
            );
        }
    }

    private static String requireSingleLine(
            String raw, String field, int maxCodePoints
    ) {
        if (raw == null) {
            throw new IllegalArgumentException(
                    field + " must not be blank"
            );
        }

        // Check original input before trimming.
        boolean invalidControl = raw.codePoints().anyMatch(
                cp -> Character.isISOControl(cp)
                        || cp == 0x2028
                        || cp == 0x2029
        );

        if (invalidControl) {
            throw new IllegalArgumentException(
                    field + " contains control or line-break characters"
            );
        }

        String value = raw.strip();

        if (value.isEmpty()
                || value.codePointCount(0, value.length()) > maxCodePoints) {
            throw new IllegalArgumentException(
                    field + " is blank or exceeds allowed length"
            );
        }

        return value;
    }

    private static String requireBody(String raw) {
        if (raw == null || raw.isBlank()
                || raw.length() > 20_000) {
            throw new IllegalArgumentException(
                    "Body is empty or too long"
            );
        }

        return raw;
    }
}
~~~

In this example, **requireSingleLine** rejects control characters before placing input into a single-line header. It also checks **U+2028** and **U+2029**, Unicode line/paragraph separators at the display layer, to avoid confusing line breaks in UIs or logs. This is an **application input policy**, not a claim that those Unicode characters are equivalent to CRLF in SMTP syntax.

**InternetAddress.parse(..., true)** invokes strict parsing; **validate()** performs additional Jakarta Mail syntax checks. The check **value.equals(address.getAddress())** restricts this example to a bare mailbox rather than a display name or list. Syntax validation must still be paired with domain policies, ownership verification, and SMTPUTF8 checks if internationalized addresses are supported.

### 7.3. Why Not Use the Customer's Email as From?

A flawed design often looks like:

~~~java
helper.setFrom(request.email());
~~~

This lets the customer dictate your organization's sending identity. Even if the input is syntactically valid, placing it in **From** can cause the email to be flagged as spoofed or fail SPF, DKIM, DMARC, and provider policies.

The pattern in the example:

~~~java
helper.setFrom("noreply@example.org");
helper.setReplyTo(replyTo);
~~~

keeps **From** as a system-controlled address and **Reply-To** as the validated customer address. When staff click Reply, email clients typically pre-fill Reply-To, satisfying the "reply to the contact" need without altering sender identity.

**Reply-To is also a workflow-influencing header.** Allowing a customer to set Reply-To does not mean any user can place arbitrary addresses into every email or abuse it to redirect sensitive notifications. Business policies must still be explicit.

### 7.4. Why Does the Customer Name Go in the Body?

In this example, **name** is presented as plain text:

~~~text
Customer name: Nguyễn An
Contact email: an@example.net

I need help with my order...
~~~

The name is not injected into the **From** header. If you truly need a header display name, use the **personal name** API on `MimeMessageHelper`/`InternetAddress` after validating the value. The library handles header character encoding; never build strings like **"From: " + name + " <...>"**.

### 7.5. Why Is the Body Allowed to Have Newlines?

Form content may look like:

~~~text
Hello,

I encountered an error during checkout.
Order ID: 1234

Please assist.
~~~

This is a valid multi-line body. With **helper.setText(body, false)**, the string goes into the plain-text body; newlines in the body do not declare new headers, provided the library constructs the message properly and the application never splices body text into raw headers.

The body still needs size limits, sensitive-data checks, automation safeguards, and anti-abuse controls; those controls are distinct from banning CRLF in headers.

## 8. Validating To, Cc, and Bcc Addresses for Your Use Case

Recipient fields are where header injection directly impacts **who receives an email**.

### 8.1. One Address vs. an Address List

If an **invoice-sending** feature targets only one customer, parse a single address and call:

~~~java
helper.setTo(validatedRecipient);
~~~

If a **group announcement** allows multiple recipients, never accept an arbitrary string and treat it as a safe list. Define a structured list DTO:

~~~java
public record GroupMailRequest(
        java.util.List<String> recipients,
        String subject,
        String message
) {}
~~~

Then:

1. Limit the number of items.
2. Validate each item as a single bare mailbox.
3. Deduplicate items under an explicit policy.
4. Verify the sender is authorized to mail that address set.
5. Convert the approved list to an address array for **setTo** or the corresponding API.

Example:

~~~java
String[] addresses = request.recipients().stream()
        .map(ContactMailService::validatedMailbox)
        .distinct()
        .toArray(String[]::new);

helper.setTo(addresses);
~~~

This **illustrates list-processing principles**, not a drop-in snippet for the class above: `validatedMailbox` simply represents a single-address validator. In production, use a consistent validator and enforce recipient-count limits before building the message.

### 8.2. Do Not Let Clients Set Internal Bcc Arbitrarily

A system may need to Bcc a compliance archive mailbox. If that is a fixed organizational rule, set it in server configuration:

~~~java
helper.setBcc("audit@example.org");
~~~

Never accept an arbitrary **bcc** field from a public request and forward it into the send call, because a completely valid address can still be an unauthorized data recipient. **Header validation only blocks malformed input; authorization decides who may receive content.**

### 8.3. Bcc and Security Boundaries

Normally, Jakarta Mail sends Bcc as envelope recipients without exposing those addresses in To/Cc headers seen by other recipients. Still:

- Bcc does not replace access control over message content.
- Manually building a raw Bcc header can expose addresses or corrupt syntax.
- Sending-system logs may still record Bcc addresses for operations.
- Bcc recipients can reveal themselves by replying.

Therefore, never use Bcc as an authorization mechanism or to protect confidential documents.

## 9. Subject and Display Name: Single-Line Values That Still Need Unicode

A valid subject can contain Vietnamese:

~~~text
Subject: Xác nhận đặt hàng tháng 11
~~~

A sender name can also be:

~~~text
Nguyễn An
~~~

There is no reason to strip all non-ASCII characters. The right approach is validating **control characters and field limits**, then letting the library encode headers per MIME/Internet message standards.

### 9.1. Header Folding Is the Library's Job

Long headers can be wrapped across multiple lines according to **folding** rules defined in email standards. Valid folding follows strict syntax; continuation lines begin with leading whitespace and belong to the same header.

This differs from input containing:

~~~text
Valid subject\r\nBcc: ...
~~~

Here, input deliberately injects a line break followed by another header name. Applications must never let users control folding or spawn new headers from a Subject field.

Libraries like Jakarta Mail handle encoding and folding when assembling the message. Never insert `"\r\n"` into Subject values to "format nicely."

### 9.2. Display Name Differs from Email Address

Example of an address combining personal name and mailbox:

~~~text
"Nguyễn An" <an@example.net>
~~~

This structure differs from a bare mailbox string:

~~~text
an@example.net
~~~

If a form asks only for "Email," enforce bare mailboxes only. If it also asks for "Display Name," store it in a separate field and use personal-name APIs. Never concatenate name and address via raw string templates without handling quotes, control characters, and parser semantics.

### 9.3. Visually Confusing Characters

Beyond CRLF, display names can include bidirectional control characters, invisible characters, or sequences that mislead on copy/paste. These do not necessarily create new headers, yet can make an address or display name look different from the underlying data.

For identity-sensitive fields, applications can enforce additional Unicode policies, display the actual address beside the name, or rely on verified identifiers. **Do not conflate every Unicode display issue with CRLF injection**; their defenses and impacts differ.

## 10. Custom Headers: Use Only Application-Defined Field Names

Applications sometimes add metadata to correlate send events:

~~~text
X-Request-Id: 7e3d02ec-38b1-4e28-b0ef-c8546feac80a
~~~

A sound approach uses **a fixed header name in code** and **a server-generated value from structured data**:

~~~java
java.util.UUID requestId = java.util.UUID.randomUUID();
message.setHeader("X-Request-Id", requestId.toString());
~~~

This uses the low-level **MimeMessage.setHeader** API without reading the header name from the request. The value is a server-generated UUID, giving it a strictly bounded format.

A far riskier pattern is:

~~~java
message.setHeader(request.headerName(), request.headerValue());
~~~

If a public API lets users pick arbitrary header names and values, attackers can attempt to inject or overwrite system-significant fields such as **From**, **Reply-To**, **Subject**, **Content-Type**, or mail-routing metadata. Even when the library blocks CRLF, **semantic header tampering** remains a risk.

If business requirements truly demand partially user-influenced custom headers, enforce:

- A fixed allowlist of header names or a mapping from business keys.
- Type-specific value validation—never raw header snippets.
- Protection preventing overrides of infrastructure or authentication fields.
- Limits on header length and count.
- Authorization and audit logging when modifying sensitive metadata.

Headers like **Date**, **Message-ID**, and MIME metadata follow strict rules; leave them to the library or sending component unless there is a justified requirement.

## 11. Attachment Filenames and MIME Headers Are Also Structured Data

When sending attachments, the message may contain:

~~~text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64
~~~

If a filename comes from a customer, it too is untrusted input entering **MIME header parameters**. Never build such headers manually like:

~~~java
String disposition =
        "attachment; filename=\"" + uploadedName + "\"";
message.setHeader("Content-Disposition", disposition);
~~~

A name with double quotes, control characters, or path syntax can alter how parsers interpret the parameter depending on encoding and decoding behavior.

In Spring Mail, use the attachment API:

~~~java
helper.addAttachment(
        safeFilename,
        new org.springframework.core.io.FileSystemResource(filePath)
);
~~~

The library handles creating the MIME part, Content-Disposition, and required encoding. The application should still:

1. Enforce display filenames with safe length and allowed characters.
2. Prevent internal file paths or secrets from leaking into filenames.
3. Never use untrusted filenames to construct filesystem read/write paths.
4. Validate file type and size per business rules.
5. Send only files the current user is authorized to access.

**A syntactically valid filename does not mean the file is safe**, and MIME encoding is not malware protection.

## 12. When Data Comes from Received Emails

A system may read customer emails and generate forwards, tickets, or auto-replies. Header data from **received emails** must also be treated as untrusted:

- The **Subject** header may contain unusual values or MIME encoding.
- The **From** header may be spoofed or carry a misleading display name.
- **Reply-To** may differ from From.
- An email may contain duplicate headers or unexpected structure.
- Attachment names, Content-IDs, and MIME parameters may hold anomalous values.

If an application reads **Subject** from an inbound message and sets it as the Subject of an outbound email, validate it as fresh untrusted input. If it uses **Reply-To** from an inbound message as the recipient of an auto-reply, enforce policies against replying to inappropriate addresses and auto-reply loops.

Never copy an entire raw header block from a customer email into a new email. To quote metadata in the body, render it as contextually escaped text or attach the original message using proper MIME encapsulation.

### Raw Header Reading vs. Parsed Fields

Jakarta Mail provides APIs for parsed fields. However, parsed structured data **does not imply authorization or business trustworthiness**. For example, an address in From may parse cleanly while belonging to an impersonator.

To establish sender authenticity, rely on receiving-infrastructure email authentication (SPF/DKIM/DMARC), trust policies, and business verification flows.

## 13. Layered Validation: DTO, Validation, Mail Builder, Transport

A Spring application sending email from requests can structure its layers as follows:

~~~text
HTTP request / webhook / database
             |
             v
        Input DTO
             |
             v
    Per-field validation
    - single mailbox for Reply-To
    - single line for Subject
    - length bounds for name/body
    - recipient authorization
             |
             v
      Mail composition
    - server-configured From
    - server-determined To
    - parsed Reply-To
    - validated Subject
    - body via setText
             |
             v
  JavaMailSender / Jakarta Mail
             |
             v
     SMTP transport / provider
~~~

Do not validate only in the controller while allowing schedulers, event consumers, or batch imports to call a mail service accepting raw headers directly. Every internal message-building API must have a clear contract on validated inputs or perform validation at its own boundary.

A design can wrap **parsed addresses** and **validated subjects** in dedicated types, reducing the chance of passing body text into Subject. Still, those types must only be constructed through validation paths—renaming a variable does not make data trustworthy.

## 14. Test Cases to Include When Building Mail Features

When developing mail-sending features, test both normal values and anomalous inputs. The table below describes **expected application behavior**—scenarios to verify in development, not output from a test run here.

| Input | Field | Expected Outcome |
| --- | --- | --- |
| **Order confirmation** | Subject | Accepted |
| **Thông báo tháng 11** | Subject | Accepted, preserving Vietnamese characters |
| Value containing **`\r`** or **`\n`** | Subject | Rejected before message construction |
| Value containing **NUL** | Subject | Rejected |
| Subject exceeding length limit | Subject | Rejected with an appropriate error message |
| **an@example.net** | Single email | Parsed into a single mailbox |
| Two comma-separated addresses | Single email | Rejected if form allows only one mailbox |
| String with display name | Single email | Rejected if policy allows bare mailboxes only |
| Address outside permitted scope | To/Bcc | Rejected despite valid syntax |
| Multi-paragraph text with newlines | Plain-text body | Line breaks preserved in body |
| String with special HTML characters | HTML body | Escaped/sanitized per template and context |
| Filename with control characters | Filename | Rejected or handled per defined filename policy |

Inspect **generated messages** in a test SMTP server or mail-capture tool, focusing on the header/body boundary and actual recipient list. Never send attack-like test payloads to external mailboxes or addresses you do not control.

Additional cases worth testing: long Unicode strings, display names with diacritics, JSON inputs decoded multiple times, requests including an undeclared Bcc field not present in the DTO, and verifying that validation failures prevent calling **mailSender.send(...)**.

## 15. Common Pitfalls

### 15.1. Believing Jakarta Mail Alone Eliminates the Need for Validation

Using typed APIs reduces raw syntax errors. Yet the library does not know whether a customer is permitted to send to **finance@example.org**. Validation, authorization, and recipient limits are the application's responsibility.

### 15.2. Checking Only for an `@` Character in Addresses

A string containing **`@`** is not necessarily a valid mailbox. Parse and validate according to input type, then apply address policies and ownership verification where needed.

### 15.3. Stripping All Newlines Across the Entire Request

Valid email bodies can be multi-line. Reject newlines in **single-line headers** while preserving legitimate newlines in **plain-text bodies**. Apply field-specific policies.

### 15.4. Trusting All Data Stored in the Database

Stored data may have originated from earlier user input saved verbatim. When placed into headers of a new email, it crosses a **trust boundary** and must be validated for its new context.

### 15.5. Letting Users Arbitrarily Specify To or Bcc

A syntactically valid address can still be an unauthorized recipient. Business rules must dictate who receives what information. For a support contact form, **To** should be server-configured rather than taken from public input.

### 15.6. Manually Building Content-Disposition Lines for Filenames

Filenames are MIME parameters with specific quoting and encoding rules. Use **addAttachment** and validate the filename before passing it to the API.

### 15.7. Assuming HTML Escaping Prevents Header Injection

HTML escaping protects HTML contexts only. It does not check CRLF in Subject or recipient syntax. Each output context requires its own controls.

### 15.8. Normalizing Anomalous Input into Valid Values

Mutations like stripping newlines, removing commas, or arbitrarily truncating strings can silently alter recipients or subjects without the user realizing it. For structurally significant fields, **reject invalid input** and ask the caller to correct it.

## 16. Frequently Asked Questions

**Should all Unicode characters in Subject be blocked?**

No. Subject can legitimately contain Vietnamese and many other languages. Validate control characters, length, and policy-defined display risks; leave standard header encoding to the library.

**What if a Subject contains a newline because a user pressed Enter?**

For a Subject field defined as single-line, reject it or prompt the user to fix it. If the UI needs multi-line descriptions, place that input in a separate **body** field.

**Is blocking `\r\n` enough for security?**

Blocking CRLF addresses a core mechanism of header injection, yet is not the whole picture: address syntax, recipient lists, spoofing, custom headers, MIME filenames, data limits, and sending authorization all matter. Enforce per-field and business-level controls.

**Does `InternetAddress.validate()` verify that an email exists?**

No. It performs library-level syntax checks—not mailbox ownership, account existence, or deliverability.

**Why not set the customer's email as From for easier replies?**

Because From represents sender identity and can conflict with email domain authentication policies. Keep From tied to your system's domain/account and use a validated **Reply-To** when staff should reply to the customer's address.

**Is adding a custom `"X-Correlation-Id"` header dangerous?**

Not inherently. When the field name is fixed in code and the value is server-generated or strictly validated without overriding sensitive headers, custom headers are helpful for correlation. Risk arises when external input arbitrarily controls header names and contents.

**Can you assume `send()` returning without error means all recipients are safe and received the email?**

No. Completion of the sending API does not prove recipients read the email, nor does it prove the initial recipient list met business policy. Validating authorized recipients must happen before calling send.

**What if a template engine is used?**

Template engines help build bodies—especially HTML—yet do not automatically prevent header injection when data flows into From, Reply-To, or Subject. Separate body escaping rules from header validation rules.

## 17. Key Takeaways for Building Emails with Spring Framework Mail

**Email headers are structured data.** Values like Subject, Reply-To, or filename must never decide where headers end or introduce new fields. The classic failure pattern is interpolating untrusted data containing **CRLF** into raw email strings.

To handle this properly in a Spring application:

- **Define authority boundaries:** server controls From and internal recipients; user-editable fields are explicitly scoped.
- **Validate by data type:** mailboxes need parsing and single-address policy; Subject/display names reject control characters; multi-line bodies follow separate rules.
- **Use dedicated APIs:** JavaMailSender/MimeMessageHelper and Jakarta Mail handle headers, MIME, and transport; never concatenate raw headers from requests.
- **Protect other contexts:** escape/sanitize HTML, validate attachment names and data, and keep logs free of leaks or misleading control characters.
- **Separate syntax from authorization:** a technically valid address may still be unauthorized to receive an email.

Understanding the differences between **headers**, **body**, **MIME parts**, and the **SMTP envelope** shows exactly where input controls belong. Keeping those boundaries intact lets users submit normal contact details without ever altering system mail structure or recipient lists.

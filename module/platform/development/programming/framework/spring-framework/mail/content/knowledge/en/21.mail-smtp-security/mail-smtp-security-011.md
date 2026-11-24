# Do Not Trust Data to Build Headers, Addresses, and Templates

An application sending email with **Spring Framework Mail** may receive data from registration forms, APIs, event queues, databases, or partner systems. That data often appears in **recipients**, **Subject**, **Reply-To**, **display names**, **MIME headers**, **HTML content**, **links**, **attachment filenames**, and **template names**. If untrusted strings are used directly to drive email structure, the system can be abused to send mail to the wrong person, spoof information, inject headers, produce dangerous HTML, or access unintended resources.

The central rule is **do not trust input data to build mail structure**. Input from users or external systems should only be *data* that is validated and placed into permitted positions. Components that decide behavior—sending addresses, valid recipient lists, notification types, selected templates, trusted URLs, and MIME metadata—must be determined by **application policy**.

Spring provides **JavaMailSender**, **MimeMessageHelper**, and **Jakarta Mail** classes to construct structured emails. Using the right APIs avoids manually assembling raw SMTP/MIME, yet **does not replace validation, authorization, HTML escaping, and template control**. This lesson explains each trust boundary, complete with Java examples and test cases.

## 1. Identifying where data enters an email

A transactional email can be assembled from many sources:

~~~text
HTTP request / message broker / webhook
                  |
                  v
            Untrusted data
                  |
          +-------+--------+---------+----------+
          |                |         |          |
          v                v         v          v
      Addresses         Subject    Template    Attachment
      To/Reply-To                  variables    filename/path
          |                |         |          |
          +-------+--------+---------+----------+
                  |
                  v
           Mail composition
                  |
                  v
        MimeMessageHelper / Jakarta Mail
                  |
                  v
              SMTP server
~~~

The fields have different names, yet share the same issue: **external strings may be deciding the structure or behavior of a message wielding the system's mail-sending authority**.

| Position | Example input | Risk if trusted directly | Appropriate guardrail |
| --- | --- | --- | --- |
| **To/Cc/Bcc** | API-submitted email | Sending to wrong person, abuse as open mail relay | Authorization, address parsing, business allowlist, rate limits |
| **From/Sender** | Client-desired value | Brand spoofing or unauthorized account | Fixed/verified sending address |
| **Reply-To** | Form reply email | Redirecting replies to someone else or header injection | Mailbox validation; use only when business rules allow |
| **Subject** | Order name, user name | Line break/header injection if concatenated raw | Length limit, reject control chars, use setter |
| **Custom headers** | Correlation ID, campaign | Header injection, data leakage | Server-generated values, format validation |
| **Template name** | `request.template` | Rendering unintended templates, accessing other template files | Enum/allowlist, server-side mapping |
| **Template variables** | `displayName`, `comment` | HTML/script injection or phishing links | Context-specific escaping, per-field validation |
| **Links in HTML** | Partner-supplied URL | Spoofed links, malicious schemes | Server-side HTTPS and domain/route policy |
| **Attachment filename** | Upload filename | Broken headers, path traversal if used as path | Safe display name; resource resolved independently |
| **Attachment bytes** | Uploaded file | Malicious content or wrong format | Size limits, file inspection, malware policy |

**Validation cannot be separated from context.** A string containing newlines is reasonable in a text description, yet unsuitable for a `Subject` header. A syntactically valid URL may still be dangerous if it points to an unauthorized domain. A syntactically valid email address may still be unauthorized for the application to mail.

## 2. Distinguishing headers, SMTP envelope, and body content

An email is not merely a text string with `To`, `Subject`, and then the body.

- **SMTP envelope** specifies sender/recipients during mail transfer, via commands such as `MAIL FROM` and `RCPT TO`.
- **MIME/RFC message headers** hold fields like `From`, `To`, `Subject`, `Reply-To`, `Date`, `Message-ID`, and `Content-Type`.
- **Message body** contains plain text, HTML, or MIME multipart/attachments.

Illustrative example:

~~~text
SMTP envelope:
    MAIL FROM:<bounce@example.test>
    RCPT TO:<customer@example.test>

Message headers:
    From: Orders <orders@example.test>
    To: customer@example.test
    Reply-To: support@example.test
    Subject: Order confirmation ORD-1528
    MIME-Version: 1.0
    Content-Type: text/plain; charset=UTF-8

Message body:
    Order ORD-1528 has been confirmed.
~~~

**The `To` header is not a protection for envelope recipients.** A system can put a valid `To` header yet accidentally use a different recipient when transferring mail, or vice versa. In normal Spring Mail flows, Jakarta Mail derives envelope recipients from the message, yet the application must still govern addresses before calling the sender.

### Control characters can break header boundaries

Header lines are separated by protocol rules. If untrusted strings are concatenated into raw MIME, **carriage return** and **line feed** (CR, LF) characters can alter how a string is parsed into header lines.

Illustrative payload showing the concept of header injection:

~~~text
Order confirmation
Bcc: unexpected@example.test
~~~

If application code concatenates the payload into a raw header without proper handling, the newline sequence may be interpreted as a new header. That is **email header injection**. This lesson does not assume every Jakarta Mail version is exploitable by the same payload; the issue is **never letting untrusted values decide header boundaries**.

### Structured APIs do not mean input is authorized

A setter like:

~~~java
helper.setTo(recipient);
~~~

lets the library handle addresses through its API instead of the app concatenating raw headers. Yet it **does not know whether the caller has permission to email that recipient**. If an API lets users pick any address and sends mail under the company domain, the application can become an email-broadcasting tool even without header injection.

Therefore, security requires both:

1. **Structural safety:** build messages via dedicated APIs, validate data types, and reject control characters in sensitive places.
2. **Business authorization:** callers may only trigger notification types to recipients and sender addresses permitted by business rules.

## 3. Never manually concatenate raw emails or SMTP commands

A dangerous practice is building emails by string concatenation:

~~~java
String rawMessage =
        "From: " + from + "\r\n"
        + "To: " + recipient + "\r\n"
        + "Subject: " + request.subject() + "\r\n"
        + "\r\n"
        + request.body();
~~~

This snippet lets input data participate directly in header structure. It also omits many MIME details such as header encoding, line folding, multipart boundaries, and content-transfer-encoding.

Likewise, never build SMTP commands manually:

~~~java
String command = "RCPT TO:<" + request.recipient() + ">";
~~~

Spring Mail/Jakarta Mail already provide protocol-handling APIs. If an application builds raw SMTP commands from input, protocol-boundary bugs can be far worse than malformed emails.

### Using `MimeMessageHelper`

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, false, "UTF-8");

helper.setFrom("notifications@example.test");
helper.setTo(validatedRecipient);
helper.setSubject(validatedSubject);
helper.setText(plainTextBody, false);

mailSender.send(mimeMessage);
~~~

Here:

- **From** is decided by the server.
- **validatedRecipient** must pass validation and authorization.
- **validatedSubject** must pass header input policy.
- **plainTextBody** is text content, not a raw header string.
- **MimeMessageHelper** handles message construction.

For HTML/multipart emails, the helper also provides overloads for HTML, inline resources, and attachments; never add boundaries in strings yourself.

## 4. Policy for handling strings used in headers

For **Subject**, display names, correlation IDs, or custom header values, define explicit policies:

1. Decide whether the field may be blank.
2. Bound length per business requirements.
3. Reject CR, LF, NUL, and disallowed control characters.
4. Do not silently mutate data in ways that disguise dangerous payloads.
5. Pass only checked values into structured header APIs.

### A Java helper to reject control characters

~~~java
import java.util.Objects;

public final class MailHeaderValues {

    private MailHeaderValues() {
    }

    public static String requiredSingleLine(
            String value,
            String fieldName,
            int maxLength
    ) {
        Objects.requireNonNull(fieldName, "fieldName");
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " must not be blank"
            );
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                    fieldName + " exceeds allowed length"
            );
        }

        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (Character.isISOControl(ch)) {
                throw new IllegalArgumentException(
                        fieldName + " contains control characters"
                );
            }
        }

        return value.strip();
    }
}
~~~

Example usage for `Subject`:

~~~java
String safeSubject = MailHeaderValues.requiredSingleLine(
        request.subject(),
        "subject",
        200
);
helper.setSubject(safeSubject);
~~~

**The 200-character limit is an example policy**, not a mandatory RFC limit for `Subject`. Applications may choose other product-specific bounds; mail libraries handle header encoding/folding separately. This helper primarily demonstrates **rejecting control characters** and bounding input.

### Do not apply the same rule to the body

Plain-text bodies may contain line breaks, tabs, or multiple paragraphs. Applying a single-line helper to the body would break legitimate content. Validate each field according to its target context:

~~~text
Header Subject:      disallow CR/LF
MIME display name:   disallow control chars, validate length
Correlation ID:      narrow server-generated format
Plain text body:     allow newlines and appropriate text characters
HTML body:           escape for HTML context
~~~

Do not simply strip strange characters to “clean” input, as that can alter business meaning and turn malicious input into another hard-to-spot value. For headers, **rejecting invalid input** is usually clearer than trying to repair untrusted strings.

## 5. Validating email addresses with Jakarta Mail

Email syntax is more complex than any string containing an `@` sign. Jakarta Mail provides **InternetAddress** to parse and validate addresses under implementation-supported rules.

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

InternetAddress[] addresses =
        InternetAddress.parse(inputAddress, true);

if (addresses.length != 1) {
    throw new IllegalArgumentException(
            "Exactly one email address must be provided"
    );
}

InternetAddress address = addresses[0];
address.validate();
~~~

This snippet parses the address under Jakarta Mail's supported syntax; it **does not prove the mailbox exists**, that the domain has an MX record, or that the sender is authorized to use it.

### Policy for a single-mailbox input field

Suppose an API has a **recipientEmail** field accepting only a plain mailbox address—no display names, address groups, or comma-separated lists:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailAddressPolicy {

    private MailAddressPolicy() {
    }

    public static InternetAddress requireSingleMailbox(String input) {
        String value = MailHeaderValues.requiredSingleLine(
                input,
                "recipientEmail",
                320
        );

        try {
            InternetAddress[] parsed =
                    InternetAddress.parse(value, true);
            if (parsed.length != 1) {
                throw new IllegalArgumentException(
                        "Only one mailbox may be provided"
                );
            }

            InternetAddress address = parsed[0];
            if (address.isGroup()) {
                throw new IllegalArgumentException(
                        "Group addresses are not accepted"
                );
            }
            address.validate();

            String mailbox = address.getAddress();
            int at = mailbox == null ? -1 : mailbox.lastIndexOf('@');
            if (at < 1 || at >= mailbox.length() - 1) {
                throw new IllegalArgumentException(
                        "Mailbox must have local-part and domain"
                );
            }
            if (address.getPersonal() != null
                    || !value.equals(mailbox)) {
                throw new IllegalArgumentException(
                        "Plain email address only, without display name or comment"
                );
            }

            return address;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid email address syntax",
                    ex
            );
        }
    }
}
~~~

**This policy is intentionally narrower than all RFC-valid email variants.** The goal is a plain-mailbox API field, not supporting every email header syntax. If the product must support quoted local-parts, internationalized email addresses, internal domains, or SMTPUTF8, define exact requirements, test your Jakarta Mail/provider version, and design matching validation instead of relying solely on a hand-rolled regex.

### Sample inputs to classify

| Input | Expected result in plain-mailbox field | Reason |
|---|---|---|
| `customer@example.test` | Accept if authorized | Single mailbox |
| `customer+orders@example.test` | May accept | Plus tags are normally valid local-part syntax |
| `Customer Name <customer@example.test>` | Reject per this policy | API accepts plain addresses only, no display name |
| `first@example.test, second@example.test` | Reject | Field permits only one mailbox |
| `customer@example.test` with CR/LF | Reject | Control characters |
| `group: first@example.test;` | Reject | Group addresses unsuitable |
| Internationalized domain address | Per defined policy/provider | Requires checking IDN/SMTPUTF8 support |
| `user@example.test` unrelated to the order | Reject at authorization layer | Valid syntax alone is insufficient to send |

**Never use a short email regex as your sole security guarantee.** A hand-crafted regex can both reject valid addresses and miss cases needing control. Use library parsers, application mailbox policies, and authorization.

### Validation does not replace deliverability

`InternetAddress.validate()` primarily checks syntax per implementation. It does not check:

- Whether the recipient verified ownership of the email.
- Whether the recipient is suppressed or unsubscribed.
- Whether the domain or mailbox still exists.
- Whether the SMTP server accepts the recipient.
- Whether that notification content is permitted for that person.

Those require business policies, address verification, SMTP/provider feedback, and recipient list management.

## 6. To, Cc, Bcc, and controlling sending permissions

Never accept an address list from a client and pass it straight into **`helper.setTo(...)`**, **`setCc(...)`**, or **`setBcc(...)`** without checks.

A safer flow:

~~~text
Request / Business Event
           |
           v
Check whether user is authorized to create notification?
           |
           v
Query recipients from trusted business data
           |
           v
Check consent / status / tenant boundary
           |
           v
Parse each mailbox, reject invalid
           |
           v
Apply dedup policy and group into To/Cc/Bcc
           |
           v
MimeMessageHelper.setTo/setCc/setBcc
~~~

### Authorization matters more than letting users type addresses

Example API:

~~~text
POST /orders/ORD-1528/send-confirmation
~~~

The caller passes an order ID. The server should look up the order, check access permissions, and retrieve the recipient email from the **verified order/customer record**. Never let the client substitute an arbitrary email and send messages on the system's behalf.

If business logic allows adding new recipients, require explicit verification/permissions and limit which email types can be sent. For instance, an “invite a colleague” form needs anti-spam, rate limits, and anti-spoofing—it must never leverage the backend's invoice-sending privileges.

### Deduplication has no single universal rule

If the same address appears in `To`, `Cc`, and `Bcc`, the system needs a deterministic policy:

- Keep a single copy in the highest-priority group.
- Reject the request to require clean input.
- Deduplicate by recipient ID rather than raw email string comparison.

Do not blindly lowercase entire emails for deduplication without understanding local-part rules; domains are case-insensitive, while local-parts have protocol nuances and providers enforce different alias rules. Do not strip plus tags or dots using one provider's rules unless business requirements explicitly define it.

### Bcc is a privacy boundary

**Bcc** is used to avoid exposing hidden recipients to other recipients. Serious mistakes include:

- Putting the entire Bcc list into the `To` field.
- Rendering the Bcc list into the body or template.
- Logging raw recipient lists in broadly accessible logs.
- Using a custom email API that mishandles Bcc headers.

When emailing many independent customers, consider **one message per recipient** to avoid address exposure and simplify tracking/deduplication. Do not rely solely on Bcc for campaigns with strict personalization and privacy needs.

### Using typed address APIs

~~~java
InternetAddress to = MailAddressPolicy.requireSingleMailbox(
        trustedRecipientEmail
);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setTo(to);
helper.setFrom("orders@example.test");
helper.setSubject("Order confirmation");
helper.setText("Your order has been confirmed.");
~~~

Separating **trustedRecipientEmail** from authorized business data and **InternetAddress** parsing clarifies two control layers: **permitted to send** and **syntactically valid address**.

## 7. From, Sender, Reply-To, and anti-spoofing

One of the easiest mistakes to turn into an abuse vulnerability is using a user-supplied address as **From** on mail sent from a corporate SMTP account.

Example to avoid:

~~~java
helper.setFrom(request.email());
~~~

If this is a contact form, an attacker can enter anyone's address and make the system emit emails appearing to come from them. Beyond spoofing risks, another person's domain may fail SPF/DKIM/DMARC alignment, causing messages to be flagged as spam or rejected.

### Choose From from trusted configuration

~~~java
private static final String MAIL_FROM =
        "support@example.test";

helper.setFrom(MAIL_FROM);
~~~

If the product has multiple tenants/domains authorized for sending, selecting `From` must pass through a provider-verified **sender identity allowlist**, never taken arbitrarily from requests.

### When users need to receive replies

A contact form can use:

~~~java
helper.setFrom("contact-form@example.test");
helper.setReplyTo(
        MailAddressPolicy.requireSingleMailbox(
                submittedContactEmail
        )
);
~~~

This separates the actual sender from the reply destination. However, **`Reply-To` is also an abusable header**: validate the address and use it only when business rules allow. If it is an unverified user-supplied address, the email body should state “reply address provided by form submitter” rather than asserting ownership.

### Never let requests control the envelope sender arbitrarily

The **`MAIL FROM`** address in the SMTP envelope relates to bounce/return-path handling and may be set via transport/provider config. It does not always match the visible **`From`** header.

Never use request-supplied transport parameters or SMTP properties to override the envelope sender, SMTP host, username, or return-path. Those are infrastructure and sender-identity configurations governed by server policy.

### Display names must not be concatenated raw either

Display names must be built with encoding-aware APIs rather than string concatenation like:

~~~java
String rawFrom = request.displayName()
        + " <support@example.test>";
~~~

Example using `InternetAddress` with a charset:

~~~java
import jakarta.mail.internet.InternetAddress;
import java.nio.charset.StandardCharsets;

String displayName = MailHeaderValues.requiredSingleLine(
        configuredBrandName,
        "brandName",
        120
);

InternetAddress from = new InternetAddress(
        "support@example.test",
        displayName,
        StandardCharsets.UTF_8.name()
);

helper.setFrom(from);
~~~

The example assumes both the sending address and brand name come from trusted configuration; the constructor can throw a checked exception, so the enclosing method must declare or handle it. The library handles encoding personal names per email header rules. Validating control characters remains an independent defense layer.

## 8. Custom headers, Message-ID, and correlation IDs

A system may add headers for tracking:

~~~java
message.setHeader(
        "X-Notification-ID",
        validatedNotificationId
);
~~~

There are two parts here:

- **Header name** should be a constant or chosen from a fixed server-defined set.
- **Header value** should follow a narrow format, such as a UUID, not a free-form user string.

Do not write:

~~~java
message.setHeader(
        request.headerName(),
        request.headerValue()
);
~~~

Just because `MimeMessage` exposes `setHeader` does not mean clients can choose arbitrary headers. Users might attempt to tamper with `Return-Path`, `Reply-To`, `Content-Type`, or other system headers, causing spoofing or breaking MIME structure.

### Using server-generated UUIDs

~~~java
import java.util.UUID;

UUID notificationId = UUID.randomUUID();
message.setHeader(
        "X-Notification-ID",
        notificationId.toString()
);
~~~

If the ID is persisted in an outbox and reused across retries, keep the **notification ID stable**. This header aids correlation; it **does not prevent duplicate SMTP sends on its own** and does not replace database/provider idempotency.

### Message-ID is not an authorization mechanism

**Message-ID** is an identifier for email processing/threading/tracing, not proof that a message was sent by an authorized party. Even when a message has a valid `Message-ID` header, SPF/DKIM/DMARC and proper identity policies are still needed; nor should `Message-ID` be treated as proof that SMTP accepted or delivered the message.

### Keep sensitive data out of headers

Headers may be saved in provider logs, displayed in an email client's “Show original” view, or pass through multiple intermediaries. Never put password-reset tokens, OTPs, API keys, bearer tokens, sensitive internal addresses, or unnecessary PII into custom headers, `Message-ID`, or correlation IDs.

## 9. Template data is not template source

An HTML email can be rendered with **Thymeleaf**, FreeMarker, Mustache, or another template engine. Two concepts must remain separate:

1. **Template source**: structure managed by developers containing HTML, conditions, and template expressions.
2. **Template data**: values such as recipient name, product name, shipping address, or notes.

### Safe usage pattern

~~~text
Fixed and reviewed template source
            |
            v
TemplateEngine + Context
            ^
            |
Validated, context-escaped data model
            |
            v
HTML/plain text email
~~~

Example:

~~~java
Context context = new Context(locale);
context.setVariable("recipientName", recipientName);
context.setVariable("orderNumber", orderNumber);

String html = templateEngine.process(
        "mail/order-confirmed",
        context
);
~~~

Here, the template name is a server-defined constant; **recipientName** is data placed in the `Context`. The template engine evaluates expressions belonging to the template source rather than evaluating characters inside `recipientName` as template source code.

### Dangerous pattern: building template source from input

Thought pattern to avoid:

~~~java
String rawTemplate =
        "<html><body><p>" + request.displayName()
        + "</p></body></html>";
~~~

If this string is used as final HTML, user data can become markup. If it is fed into a template engine as **template source** and evaluated, data can influence template syntax/bindings processed by the engine.

These are two distinct risks:

- **HTML injection:** data is interpreted as email markup.
- **Server-side template injection (SSTI):** untrusted data is used as template syntax or source evaluated by the engine.

Not every string containing template symbols automatically causes SSTI. When a string is a **Context data value** rendered with proper escaping, those symbols typically display as literal text. Risk arises when the application **assembles template source dynamically**, enables dynamic expression evaluation, or re-processes rendered output as a new template.

## 10. Thymeleaf: use `th:text` for text data

An HTML template might look like:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Order confirmation</h1>

  <p>
    Hello,
    <strong th:text="${mail.displayName}">friend</strong>.
  </p>

  <p>
    Order number:
    <span th:text="${mail.orderNumber}">ORD-000</span>
  </p>

  <p th:text="${mail.customerNote}">
    Order note.
  </p>
</body>
</html>
~~~

**`th:text`** renders values as text content and applies proper HTML escaping. For example, a name containing less-than/greater-than signs or tag-like strings will not become new HTML tags just because a user typed them.

### Avoid `th:utext` with user data

Thymeleaf provides **`th:utext`** to output unescaped HTML. Example:

~~~html
<div th:utext="${mail.customerNote}"></div>
~~~

Do not use it for customer notes, usernames, or untrusted content. If the data contains markup, that markup gets injected into the email instead of displaying as plain text.

Email clients have varying HTML filters, and many block scripts. Yet **never rely on the email client's filter as your sole security barrier**. Malicious markup can still create phishing links, deceptive layouts, tracking images, or inappropriate content.

### When rich text from users is genuinely required

Some products allow users to compose formatted text, such as admin announcements or messages with bold/italic/links.

In that case:

1. Define the input format clearly (Markdown, a structured rich-text document model, or restricted HTML).
2. Convert using a trustworthy parser.
3. **Sanitize HTML against an allowlist** of permitted tags/attributes/protocols.
4. Control link and image URLs.
5. Test across multiple email clients.

Do not write custom regexes to “strip scripts” and assume HTML is safe. HTML has many encodings and attributes; use a dedicated HTML sanitizer designed for the task.

### Do not pass full entities into template context

If you pass an entire JPA entity or complex domain object into `Context`:

~~~java
context.setVariable("user", userEntity);
~~~

the template might inadvertently access sensitive fields, lazy associations, or unrelated data. Prefer a narrow mail model:

~~~java
public record OrderConfirmedMailModel(
        String displayName,
        String orderNumber,
        String customerNote,
        String actionUrl
) {
}
~~~

A dedicated model constrains which fields can appear in the email, simplifies template reviews, and avoids direct coupling to database entities.

## 11. HTML escaping does not mean a URL is safe

In HTML emails, applications often include an action button:

~~~html
<a th:href="${mail.actionUrl}">View order</a>
~~~

The template engine may escape special attribute characters, yet **escaping does not validate URL schemes, domains, or access rights**. A URL can still send users to an untrusted site if it is syntactically valid while pointing to an attacker's domain.

### What to enforce for URLs

- Accept only appropriate schemes, typically **HTTPS** for action links.
- Host must match an **exact** allowlist, never substring matching.
- Disallow userinfo in URLs when unnecessary.
- Enforce port/path rules per policy.
- Never use a client-supplied URL as the base domain for password resets.
- Check for open redirects on target endpoints.
- Keep sensitive tokens out of unintended logs, referrers, or analytics.

### Example action URL policy

~~~java
import java.net.URI;
import java.util.Locale;
import java.util.Set;

public final class MailActionUrlPolicy {

    private static final Set<String> ALLOWED_HOSTS = Set.of(
            "app.example.test",
            "accounts.example.test"
    );

    private MailActionUrlPolicy() {
    }

    public static URI requireTrustedHttpsUrl(String rawUrl) {
        if (rawUrl == null || rawUrl.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing action URL"
            );
        }

        final URI uri;
        try {
            uri = URI.create(rawUrl);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Invalid URL",
                    ex
            );
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException(
                    "Only HTTPS is accepted"
            );
        }
        if (uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException(
                    "URL must not contain userinfo"
            );
        }

        String host = uri.getHost();
        if (host == null
                || !ALLOWED_HOSTS.contains(
                        host.toLowerCase(Locale.ROOT)
                )) {
            throw new IllegalArgumentException(
                    "Host is not in allowlist"
            );
        }
        if (uri.getPort() != -1 && uri.getPort() != 443) {
            throw new IllegalArgumentException(
                    "Port is not permitted"
            );
        }

        return uri;
    }
}
~~~

This example intentionally supports only ASCII hostnames in the allowlist. If internationalized domain names are needed, apply proper IDNA/canonicalization rules. A real system can also restrict **path prefixes**, query parameter types, fragments, and redirect targets by notification type.

### Do not check hosts with `endsWith` without a separator

Pattern to avoid:

~~~java
if (url.contains("example.test")) {
    // Allow.
}
~~~

The following values also contain `example.test`:

~~~text
https://example.test.attacker.invalid/
https://attacker.invalid/redirect?next=example.test
~~~

Using **`URI.getHost()`** and an exact host allowlist prevents this naive mistake. If subdomains are allowed, enforce separator-aware rules and ensure subdomain ownership is trusted; also protect against DNS rebinding/SSRF if URLs are fetched server-side.

### Build URLs from server config, not arbitrary `Host` headers

Another mistake is generating password-reset links using a domain taken directly from unvalidated HTTP `Host` or forwarded host headers:

~~~text
https://<request-host>/reset-password?token=...
~~~

If proxies/backends trust a client-controlled `Host` header, emails can contain links to an attacker's domain. Use a configured **public base URL**, or a tenant domain verified against an allowlist. This mitigates **password-reset link poisoning**.

## 12. Template names and fragments must follow an allowlist

Never let clients control the template filename:

~~~java
String html = templateEngine.process(
        request.templateName(),
        context
);
~~~

Depending on the resolver and setup, untrusted template names can access unintended templates, cause path resolution errors, or leak internal template contents. With engines supporting dynamic expression evaluation, letting clients supply expressions adds further risk.

### Select templates via enum or business event

~~~java
public enum NotificationType {
    ORDER_CONFIRMED,
    PASSWORD_RESET,
    ACCOUNT_ACTIVATED
}
~~~

~~~java
public final class MailTemplateCatalog {

    private MailTemplateCatalog() {
    }

    public static String pathFor(NotificationType type) {
        return switch (type) {
            case ORDER_CONFIRMED -> "mail/order-confirmed";
            case PASSWORD_RESET -> "mail/password-reset";
            case ACCOUNT_ACTIVATED -> "mail/account-activated";
        };
    }
}
~~~

~~~java
String templatePath =
        MailTemplateCatalog.pathFor(command.notificationType());

String html = templateEngine.process(templatePath, context);
~~~

The application must derive **`NotificationType`** from an authorized business action. If a request passes the enum directly, you must still verify the user has permission to trigger that notification type. Enums eliminate arbitrary template names; **they do not provide authorization on their own**.

### Never evaluate user-submitted expressions

Dangerous practices include:

- Letting users supply template engine expressions evaluated with server privileges.
- Injecting user-supplied HTML into a template source and re-rendering it.
- Building fragment names by concatenating input into template expression syntax.
- Letting external webhooks choose arbitrary template file paths.

For richly formatted data to render, store it strictly as data and use an application-controlled template structure. If the product is an admin template editor, it requires sandboxing, expression restrictions, and isolated data permissions—a broader security problem than normal mail sending.

### Template versions and snapshotted data

Transactional emails needing retries may render after the original event happened. If templates or business data change, the same notification could produce different content across retries. Storing the **template code/version** and required snapshot data explains exactly what was sent.

Never rely on “swapping templates on retry” to create unexpected side effects. Retrying the same notification and intentionally resending should follow separate contracts.

## 13. Do not let user content dictate HTML structure

Beyond classic XSS, email HTML content can be abused to mislead recipients about message origin, trick them into clicking another domain, or leak data.

### Case where a product name contains markup

Suppose a marketplace product is named:

~~~text
<strong>Special discount</strong>
~~~

If the application concatenates it straight into HTML:

~~~java
String html = "<p>Product: " + productName + "</p>";
~~~

the name becomes markup. If passed as a variable rendered via **`th:text`**, less-than/greater-than characters are escaped as text; the recipient sees the literal name rather than product-injected HTML.

### Dynamic CSS and attributes also carry risks

Fields such as:

~~~html
<div style="background-image: url(...)">
<a href="...">
<img src="...">
~~~

do not have the same semantics as plain text. Beyond escaping quotes, you must validate permitted **protocols, hosts, and CSS/HTML attribute values**. For transactional emails, keep HTML structure/CSS inside trusted templates and use variables only for controlled display values.

Never let user input define entire **`style`**, **`href`**, **`src`**, or script contents without dedicated validation. Email clients strip, rewrite, or allow different elements; never gamble security on client behavior.

### Displayed URLs and target URLs must match

An email might display:

~~~text
Click to sign in at app.example.test
~~~

while the HTML tag points to a different domain if `href` came from a request. This creates phishing risk even when the HTML contains no scripts.

Derive both the label and the URL from one trusted action model; never let users pair a brand label with an unauthorized URL.

### Sanitizers differ from encoders

**Encoders/escaping** convert text data into a safe representation for a specific context (HTML text or attribute). An **HTML sanitizer** takes an intentional HTML document and strips/rewrites disallowed parts.

If users only enter ordinary names or notes, **escape as text**. Use a sanitizer only when the product explicitly permits HTML/rich text. Trying to “sanitize” all input at the database layer often corrupts data and does not replace output escaping.

## 14. Plain text and HTML share one data contract

An email can contain both `text/plain` and `text/html`:

~~~java
helper.setText(plainText, htmlText);
~~~

Both versions should render from the **same validated/normalized mail model**:

~~~text
Trusted Order Mail Model
          |
          +--> HTML template (escaped text, trusted URLs)
          |
          '--> Plain template (complete essential content)
          |
          v
    MimeMessageHelper.setText(plain, html)
~~~

Related mistakes include:

- HTML uses a validated URL while plain text uses a raw URL from the request.
- HTML hides invalid fields while plain text inserts unchecked strings.
- HTML uses the model's recipient name while plain text concatenates directly from the HTTP request.
- HTML puts important content inside an image while plain text lacks an explanation.

Plain text does not suffer HTML injection the same way HTML does, yet can still carry **phishing links, false information, or sensitive data** if input is unauthorized.

### Length limits and confidential data

For a **`customerNote`** field in the body:

- Set a reasonable length limit to prevent oversized emails.
- Define whether newlines/tabs are allowed.
- Keep tokens, passwords, payment card details, or internal data out of templates unless truly required.
- Filter sensitive data at the source rather than hoping the template won't display it.

Length validation ensures stability and prevents resource abuse; **escaping** at the rendering point handles the special meaning of HTML characters.

## 15. Attachment filenames must not become system paths

File uploads often provide a client-declared filename. If the application uses that name as a server path:

~~~java
Path path = uploadDirectory.resolve(
        request.originalFilename()
);
~~~

a name containing path separators or directory traversal sequences can make the application access files outside the intended directory without proper controls.

**Attachment filename** and **storage resource path** must be separated into two concepts:

- **Storage key/path**: generated by the server, used to locate stored and verified file bytes.
- **Display filename**: name shown to the recipient; strictly MIME metadata, not a filesystem path.

### Example separating storage key and display name

~~~java
public record ValidatedAttachment(
        String displayFilename,
        String contentType,
        Resource resource
) {
}
~~~

~~~java
helper.addAttachment(
        attachment.displayFilename(),
        attachment.resource(),
        attachment.contentType()
);
~~~

The record merely represents data *after* the upload/attachment policy layer has checked it; it does not validate files by itself. The `Resource` must be chosen by the service via a trusted ID or storage key, never resolved directly from a client-supplied filename.

### Constraining filenames used in MIME

A safe display name can follow these rules:

- No CR/LF or control chars.
- No absolute paths or path separators.
- No directory traversal segments.
- Appropriate length and extension.
- Does not reveal filesystem paths, internal usernames, or unnecessary PII.
- No misleading patterns, such as double extensions masquerading file types.

Example minimal filename filter for application-generated filenames:

~~~java
public final class AttachmentNames {

    private AttachmentNames() {
    }

    public static String requireSimpleName(String input) {
        String name = MailHeaderValues.requiredSingleLine(
                input,
                "filename",
                180
        );

        if (name.equals(".") || name.equals("..")
                || name.contains("/")
                || name.contains("\\")
                || name.contains("..")) {
            throw new IllegalArgumentException(
                    "Filename must not contain paths"
            );
        }
        return name;
    }
}
~~~

**This is a simple filename policy example**, not a comprehensive filter covering every Unicode hazard, OS filename quirk, reserved name, or extension issue. For user-uploaded files, generate display names from normalized metadata and use server-controlled storage keys.

### Upload MIME `Content-Type` is untrusted too

An HTTP upload may declare:

~~~text
Content-Type: image/png
filename="logo.png"
~~~

Yet the actual bytes might not be a PNG. Using `FileTypeMap` to infer from extensions does not verify file contents either. If the system allows forwarding uploaded files into emails:

1. Enforce a file-type allowlist.
2. Cap individual file sizes and total email size.
3. Check extensions, MIME metadata, and file signatures/formats based on risk.
4. Scan for malware per policy.
5. Derive the MIME type from trusted server-side inspection.
6. Attach only `Resource` objects authorized for access.

Do not slap `application/pdf` into headers for an arbitrary file to make it look like a PDF; `Content-Type` describes data, it does not convert bytes.

### ZIP archives, Office documents, and complex content

A ZIP archive can contain dangerous files or decompress to huge sizes. Office documents can contain active content or macros depending on format. Validation may need to inspect internal structure based on risk rather than merely checking the file extension.

Never extract user-submitted archives into a shared directory without checking archive path traversal, bounding total uncompressed size, and limiting nesting depth. That is part of the security boundary before a file becomes a valid attachment.

## 16. Inline images, resource URLs, and SSRF risk

In HTML emails, images may be:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

or:

~~~html
<img src="https://static.example.test/logo.png" alt="Logo">
~~~

A **CID image** is attached as an inline MIME resource; a **remote image** is fetched by the email client from a URL when permitted. Each carries different risks.

### Never fetch arbitrary URLs from requests

Dangerous example:

~~~java
URL remote = new URL(request.logoUrl());
byte[] content = remote.openStream().readAllBytes();
~~~

If the backend can reach internal networks, a user-controlled URL can cause **server-side request forgery (SSRF)** or download massive payloads. Never blindly turn user-supplied URLs into inline image bytes.

If the product genuinely requires fetching external images:

- Enforce hostname and scheme allowlists.
- Resolve DNS and block private/loopback/link-local addresses matching your network model.
- Validate redirect targets, not only the initial URL.
- Set timeouts, size caps, content-type checks, and redirect limits.
- Never forward internal credentials/cookies to external URLs.
- Consider an isolated/sandboxed image-fetching service.

A simpler approach for transactional emails is using a **fixed logo `Resource`** from the classpath or trusted object storage rather than unverified upload URLs.

### Content-ID decided by the server

~~~java
helper.setText(plainBody, htmlBody);
helper.addInline(
        "brand-logo",
        trustedLogoResource,
        "image/png"
);
~~~

HTML must reference **`cid:brand-logo`** exactly. Never let users pick arbitrary `Content-ID` values, manipulate raw MIME body parts, or override a resource's `Content-Type`/`Content-Disposition`. The `multipart/related` structure should stay under helper and mail composer control.

## 17. SMTP credentials and transport policy are server configuration

Although this lesson focuses on headers, addresses, and templates, trust boundaries do not stop there. **SMTP host, port, username, password, TLS mode, and connection timeouts** must never be user request parameters.

Example Spring Boot configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Timeouts are in milliseconds and illustrative only; tune them to your provider and deployment reality. **Enable TLS/STARTTLS and verify hostnames** per server support; never disable certificate verification to fix configuration errors.

Credentials should come from a secret manager, secure environment injection, or your organization's secrets mechanism—never hard-coded in repositories. Avoid logging session properties containing usernames/passwords or AUTH payloads.

### Never let requests choose the SMTP server

Example to avoid:

~~~java
sender.setHost(request.smtpHost());
sender.setUsername(request.smtpUser());
sender.setPassword(request.smtpPassword());
~~~

That hands transport control of the application over to users. Beyond unauthorized sending, it can open connections to unintended hosts, leak credentials, or subvert TLS policies.

If a product truly offers a “bring your own SMTP” feature, that is a dedicated administrative capability needing authentication, host checks, secret storage, tenant authorization, and egress policies—never arbitrary parameters on a transactional send endpoint.

### Domain authentication and deliverability

Verified `From` addresses alongside SPF/DKIM/DMARC reduce spoofing and improve deliverability. Still, these mechanisms cannot replace input controls inside the application:

- SPF/DKIM/DMARC do not decide whether a user is authorized to email someone else's invoice.
- DKIM-signing a message with malicious content does not make that content safe.
- Proper header encoding does not stop phishing links.

Therefore, enforce both **sender/domain identity** at the SMTP/provider layer and **business/content integrity** at the application layer.

## 18. Designing an email flow with clear trust boundaries

A manageable architecture splits into four layers:

~~~text
HTTP API / Webhook / Domain Event
             |
             v
       Authorization Layer
       - user/tenant permissions
       - event/recipient policy
             |
             v
       Mail Data Preparation
       - query trusted business data
       - normalize/validate fields
       - build server-controlled links
       - select template code from allowlist
             |
             v
       Mail Composition Layer
       - parse mailbox
       - safe headers/from/reply-to
       - render HTML + plain template
       - choose validated attachments
             |
             v
       JavaMailSender / SMTP Provider
       - credentials/TLS/timeouts
       - logging and delivery tracking
~~~

### Responsibilities per layer

| Layer | What does it know? | What must it NOT trust? |
| --- | --- | --- |
| API/Event handler | Who requested the action, which event occurred | Client-chosen sender addresses, template paths, SMTP hosts |
| Business service | Orders, accounts, recipient rights | Permissions inferred solely from an email string |
| Mail preparation | Data eligible for the notification | Raw URLs, raw HTML, and raw attachment paths |
| Mail composer | Template code, header policy, MIME structure | Unnormalized/unauthorized fields |
| Transport | SMTP config, identity, TLS | Request users choosing credentials/hosts |

### Example: DTO between business service and mail composer

~~~java
public record OrderConfirmedNotice(
        String recipientEmail,
        String displayName,
        String orderNumber,
        String actionUrl,
        String customerNote
) {
}
~~~

**`OrderConfirmedNotice`** must not be bound straight from a public HTTP request and passed directly to the mail composer. It must be built by the business service after verifying which tenant owns the order, who the recipient is, and which content is valid.

If notifications flow through a queue/outbox, this record can be snapshotted data tagged with an event ID, version, and explicit read permissions. Workers must verify queue data comes from an authorized source before using it.

## 19. Spring example: sending email with fixed sender, validated recipient, and fixed template

The service below shows how to connect the validation layers in an email flow:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.net.URI;
import java.util.Locale;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class SecureOrderMailComposer {

    private static final String FROM =
            "orders@example.test";
    private static final String REPLY_TO =
            "support@example.test";
    private static final String TEMPLATE =
            "mail/order-confirmed";

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public SecureOrderMailComposer(
            JavaMailSender mailSender,
            TemplateEngine templateEngine
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    public void send(OrderConfirmedNotice notice)
            throws MessagingException {

        // Data already authorized by business service;
        // composer still validates format before building MIME.
        InternetAddress recipient =
                MailAddressPolicy.requireSingleMailbox(
                        notice.recipientEmail()
                );

        String orderNumber =
                MailHeaderValues.requiredSingleLine(
                        notice.orderNumber(),
                        "orderNumber",
                        80
                );

        URI actionUri =
                MailActionUrlPolicy.requireTrustedHttpsUrl(
                        notice.actionUrl()
                );

        String displayName = notice.displayName() == null
                || notice.displayName().isBlank()
                ? "friend"
                : notice.displayName().strip();

        String note = notice.customerNote() == null
                ? ""
                : notice.customerNote();

        // Validate body fields per product size limits.
        if (displayName.length() > 160 || note.length() > 2000) {
            throw new IllegalArgumentException(
                    "Email body data exceeds maximum length"
            );
        }

        OrderConfirmedMailModel model =
                new OrderConfirmedMailModel(
                        displayName,
                        orderNumber,
                        note,
                        actionUri.toASCIIString()
                );

        Context context = new Context(Locale.forLanguageTag("en-US"));
        context.setVariable("mail", model);

        // Template code is a server constant.
        String html = templateEngine.process(TEMPLATE, context);

        String plain = "Hello " + displayName
                + "\nOrder " + orderNumber
                + " has been confirmed."
                + "\nView order: " + actionUri.toASCIIString();

        String subject =
                MailHeaderValues.requiredSingleLine(
                        "Order confirmation " + orderNumber,
                        "subject",
                        200
                );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom(FROM);
        helper.setReplyTo(REPLY_TO);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plain, html);

        mailSender.send(message);
    }
}
~~~

**`OrderConfirmedMailModel`** is the record shown earlier. The example assumes an existing Thymeleaf template named **`mail/order-confirmed`** using **`th:text`** to render `displayName`, `orderNumber`, and `customerNote`, and **`th:href`** for the validated `actionUrl`.

Points to remember:

- **`FROM`/`REPLY_TO`/`TEMPLATE`** never come from requests.
- **`recipient`** is parsed under single-mailbox policy in addition to business authorization.
- **`Subject`** is bounded and rejects control chars.
- **`actionUrl`** is accepted only after passing HTTPS/host policy.
- **`displayName`/`customerNote`** are template text data, never HTML source.
- **HTML and plain text** share the same model/data source.
- **`JavaMailSender`** uses server-side transport configuration.

### Why doesn't the composer guarantee sending authorization on its own?

The composer merely accepts `OrderConfirmedNotice` and enforces structural rules. If a public API allows users to construct that record with an arbitrary `recipientEmail`, it can still be abused. **Authorization must happen before creating the notice**, based on order ID, tenant ID, and the actual business recipient. That boundary cannot be replaced by an email-parsing function.

### Production adjustments to consider

The minimal example may need to expand with:

- Using a dedicated template/model for both plain text and HTML instead of string-concatenating plain text.
- Pulling locale/timezone from verified user preferences.
- Sending via `AFTER_COMMIT` events or a transactional outbox when notifications depend on transactions.
- Rendering content and submitting via a queue/worker when async/durable retries are needed.
- Setting `mailFrom`/`Reply-To` from verified sender identity configuration per environment/tenant.
- Recording opaque correlation IDs and safe submission states.
- Checking recipient lists, suppression/unsubscribes, and rate limits.
- Configuring SMTP timeouts and observing provider errors.

## 20. Security when using FreeMarker or other template engines

The principle of **trusted template source + untrusted data model** applies to every engine. Exact escaping syntax differs.

### With FreeMarker

Configure templates with HTML output format and auto-escaping suited to the FreeMarker version used in your project. Once the right output format is enabled, ordinary interpolations in supported contexts are HTML-escaped.

Do not let users supply:

- FTL source for the server to render with application privileges.
- Dynamic expressions to evaluate inside FreeMarker.
- Template names/paths resolved against the filesystem or classpath.

If the product offers a template editor, that is a dedicated feature requiring separate permissions and sandboxing policies—not the ordinary transactional mail path.

### With Mustache or logic-less engines

Many logic-less engines have distinct syntax for escaped vs. unescaped interpolations. Check your actual configuration and avoid unescaped forms for user data. Never assume Thymeleaf syntax rules apply to Mustache.

### With prebuilt HTML templates without an engine

If an email uses a static HTML fragment and replaces tokens via Java string replacement, ensure data is encoded specifically for the **exact context**:

~~~text
HTML text node
HTML attribute value
URL attribute
CSS property
JavaScript context (should not be used in emails)
~~~

A generic “escapeHTML” helper does not necessarily make URLs safe, and text-node escaping must not be assumed sufficient for CSS or URL contexts. For transactional emails, using a template engine and a clean data model is usually much easier to maintain safely than raw string replacement.

## 21. Never treat the database as proof that data is trusted

A common misconception is: “This value is already stored in the database, so it's safe to put in an email.” False.

Example:

1. A user registers with a display name containing markup.
2. The app saves the raw name into the database.
3. Days later, a scheduled job reads that name to send an email.
4. The renderer concatenates the name into HTML without escaping.

Even though the name was read from the database, its original provenance was untrusted input. That is **stored injection**.

### Track data provenance, not just current storage location

| Current source | What can it be trusted for? | What must still be checked? |
| --- | --- | --- |
| JPA entity | Persisted business data | Provenance, recipient permissions, escaping |
| Message broker event | System-emitted event | Sender authentication, schema/version, authorization |
| Internal service response | Data from another system | API contract, tenant boundary, validation |
| Configuration properties | Operator-managed settings | Secret handling, verified senders, URL allowlists |
| CSV import | Data from imported files | Header/body validation, addresses, injection, sizes |
| User input | User-supplied data | Per-field validation and authorization |

**“Internal” does not mean “trusted for every use”.** A microservice might store a username valid for a web screen that still needs HTML escaping when inserted into an email. Every sink needs its own controls.

## 22. Logs, exceptions, and observability must not leak data

When mail sending fails, developers often enable debugging or log the full message. While useful for investigating SMTP, this risks exposing:

- Recipient addresses, transaction details, and usernames.
- Password-reset links, OTPs, and magic login links.
- Attachment filenames or contents.
- SMTP authentication details.
- Raw MIME headers containing correlation or internal info.

### Minimal logging by notification ID

Example structured log:

~~~text
event=mail_submission_failed
notification_id=ab41...
event_type=ORDER_CONFIRMED
smtp_provider=primary
error_class=MailSendException
status=UNKNOWN
attempt=2
~~~

This suffices to correlate mail jobs with business events and provider logs without logging message contents. If deep investigation is required, enable extra logging briefly under strict access controls using test data or redacted payloads.

### Never return verbatim exceptions to clients

If a user lacks permission to email a recipient, the API can return a generic business error:

~~~text
403 Forbidden: Not permitted to perform this action.
~~~

Never return raw SMTP transcripts, credentials, hidden recipient addresses, or stack traces containing mail models to unauthenticated callers.

When validation fails, return stable error codes (such as `INVALID_RECIPIENT`, `INVALID_SUBJECT`, `UNAUTHORIZED_NOTIFICATION`, `UNTRUSTED_ACTION_URL`) while logging technical details at the appropriate access tier.

### Auditing key decisions

For critical notification systems, record:

- Who or which event requested the notification.
- Recipient ID and tenant scope.
- Selected template code/version.
- Verified sender identity.
- Correlation ID and attempt outcome.
- Reason for rejecting invalid headers/URLs/attachments.

There is no need to record raw dangerous payloads in audit logs just for analysis; record the violation category, field name, and a carefully designed hash if correlation is needed.

## 23. Testing input boundaries

Validation needs tests at the parser, policy, composer, and MIME integration layers. These tests should use dummy data—never send real mail to external addresses.

### Testing rejection of newlines in Subject

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class MailHeaderValuesTest {

    @Test
    void rejectsCarriageReturnAndLineFeed() {
        String injected =
                "Order confirmation\r\nBcc: unexpected@example.test";

        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.requiredSingleLine(
                        injected,
                        "subject",
                        200
                )
        );
    }

    @Test
    void rejectsControlCharacter() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.requiredSingleLine(
                        "Invoice\u0000Draft",
                        "subject",
                        200
                )
        );
    }
}
~~~

This test confirms the policy **rejects invalid input** before reaching the header API. It does not need to test whether a particular Jakarta Mail version would accept that payload.

### Testing single-mailbox recipient fields

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MailAddressPolicyTest {

    @Test
    void acceptsOneMailbox() {
        assertEquals(
                "customer@example.test",
                MailAddressPolicy
                        .requireSingleMailbox("customer@example.test")
                        .getAddress()
        );
    }

    @Test
    void rejectsAddressListInSingleField() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailAddressPolicy.requireSingleMailbox(
                        "a@example.test, b@example.test"
                )
        );
    }

    @Test
    void rejectsDisplayNameWhenOnlyMailboxIsAllowed() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailAddressPolicy.requireSingleMailbox(
                        "Someone <customer@example.test>"
                )
        );
    }
}
~~~

This parser/validation test **does not test authorization**. Add business service tests confirming user A cannot request sending user B's invoice even when B's email is syntactically valid.

### Testing URLs accept only trusted hosts

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MailActionUrlPolicyTest {

    @Test
    void acceptsApprovedHttpsUrl() {
        assertEquals(
                "app.example.test",
                MailActionUrlPolicy.requireTrustedHttpsUrl(
                        "https://app.example.test/orders/ORD-1528"
                ).getHost()
        );
    }

    @Test
    void rejectsLookalikeHost() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailActionUrlPolicy.requireTrustedHttpsUrl(
                        "https://app.example.test.attacker.invalid/"
                )
        );
    }

    @Test
    void rejectsOtherSchemes() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailActionUrlPolicy.requireTrustedHttpsUrl(
                        "javascript:alert(1)"
                )
        );
    }
}
~~~

This tests a **product allowlist**, not a universal URL validator. If your product needs URLs with path parameters, redirects, or multiple tenant domains, tests should reflect that policy.

### Testing escaping in HTML templates

One way to test at the template layer:

1. Use a mail model whose `displayName` contains less-than, greater-than, and quote characters.
2. Render with the actual Thymeleaf template using **`th:text`**.
3. Parse the rendered HTML.
4. Assert the user string appears as a text node, never becoming a new HTML element.
5. Assert the `actionUrl` link still points to the permitted host.

Do not look solely for one fixed escaped string in raw HTML when the template engine may encode valid characters in multiple equivalent ways. Checking **DOM semantics** ensures the test verifies what actually matters: user data cannot become HTML structure.

### Testing that mail is not sent when validation/authorization fails

A service test should assert:

~~~text
Given: user does not own the order
When: requesting to send an invoice for that order
Then: authorization error
And: do not call JavaMailSender
And: do not create a new outbox notification
~~~

Security tests checking only CRLF strings are insufficient. A completely valid email address unrelated to the business record must also be rejected.

### Testing MIME headers after serialization

With a valid message:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.test");
helper.setTo(
        MailAddressPolicy.requireSingleMailbox(
                "customer@example.test"
        )
);
helper.setSubject("Order confirmation");
helper.setText(
        "Your order has been confirmed.",
        "<p>Your order has been confirmed.</p>"
);

message.saveChanges();
~~~

Then use Jakarta Mail APIs to inspect:

- **`From`** matches the verified sender.
- **`Recipient`** matches the target recipient.
- **`Subject`** matches the normalized string.
- **`Content-Type`** of bodies/parts is right.
- No unexpected `Bcc` headers exist.
- Attachments and inline resources sit in the proper multipart relationship if present.

Do not compare entire raw messages byte-for-byte because **`Message-ID`**, boundaries, header folding, and transfer encoding may be auto-generated. Use a MIME parser to verify actual structure.

## 24. Common security mistakes

### Mistake 1 — Using `request.subject()` directly to build raw headers

CR/LF sequences can alter header boundaries when code builds MIME manually.

**Fix:** reject control characters and use `MimeMessageHelper.setSubject` instead of raw header concatenation.

### Mistake 2 — API allowing users to enter any `To` address

A syntactically valid email may still be an unauthorized recipient.

**Fix:** enforce authorization against business entities; pull recipients from authorized records and apply rate limits.

### Mistake 3 — Taking `From` from a contact form

Users can impersonate someone else, causing spoofing and broken DMARC alignment.

**Fix:** `From` is a verified sender identity; `Reply-To` is validated when business rules need it.

### Mistake 4 — Letting clients send arbitrary custom header names

Input may attempt to tamper with system headers or MIME structure.

**Fix:** header names are constants/allowlists; header values follow narrow schemas and length limits.

### Mistake 5 — Using `th:utext` for `customerNote`

Data can become HTML markup instead of plain text.

**Fix:** use `th:text`, or a dedicated sanitizer when rich text is truly needed.

### Mistake 6 — Escaping HTML and then trusting any URL

A URL can be properly quoted/escaped yet still point to an unauthorized website.

**Fix:** validate schemes, hosts, and routes using a dedicated URL policy.

### Mistake 7 — Generating password-reset URLs from the `Host` header

Link domains can be attacker-controlled if proxies do not validate `Host`/`X-Forwarded-Host`.

**Fix:** server-configured public base URLs or verified tenant domains.

### Mistake 8 — User-supplied template paths

The application may render unintended templates or fail path resolution.

**Fix:** use enums and catalog mappings, never raw template paths.

### Mistake 9 — Allowing users to input template expressions

Expressions may be evaluated by the engine under server privileges/context if unisolated.

**Fix:** user text is strictly `Context` data; never expose template source/evaluation APIs to untrusted input.

### Mistake 10 — Trusting upload filenames when building paths

Path traversal or sensitive filenames can influence which files get read.

**Fix:** server-generated storage keys; filenames are validated display metadata only.

### Mistake 11 — Trusting upload `Content-Type`

Clients can declare `image/png` even when bytes are not PNG.

**Fix:** allowlists, format checks, and malware policies; MIME types derived from verified data.

### Mistake 12 — Fetching images from arbitrary request-supplied URLs

Backends risk SSRF or downloading oversized payloads.

**Fix:** use static resources; if fetching is required, enforce egress/URL/redirect/size policies.

### Mistake 13 — Using the same validation for `Subject` and body

Newlines are invalid in headers yet legitimate in text bodies.

**Fix:** context-specific validation; escaping at output points.

### Mistake 14 — Logging full SMTP sessions or raw MIME

Logs can expose PII, reset tokens, transaction details, and credentials.

**Fix:** log notification IDs and error categories; restrict debugging with real data.

### Mistake 15 — Believing DKIM makes email content safe

DKIM proves a cryptographic signature/domain relationship per standard, not that template data or URLs are benign.

**Fix:** pair identity verification with authorization, validation, and content escaping.

### Mistake 16 — Thinking database-stored input is automatically safe

Original user data may still contain markup or header-like text.

**Fix:** preserve input policies on read, escape properly at display time, and verify permissions before sending.

## 25. Practice scenarios

### Scenario A — Subject input containing newlines

An API receives a `Subject` whose first line is an order name and whose next line looks like a `Bcc` header.

**Question:** if using `MimeMessageHelper.setSubject`, can validation be skipped?

**Answer:** no. Structured setters help the library build headers via the right API, yet the application still needs a header policy: reject control characters, cap length, and prevent input from altering semantics. Never assemble raw MIME from input.

### Scenario B — Syntactically valid address belonging to another customer

User A can view their own order and submits user B's email to the send-invoice API.

**Question:** will `InternetAddress.validate()` stop this?

**Answer:** no. Valid email syntax does not prove authorization to receive the invoice. The service must pull the recipient from the authorized order or enforce explicit delegation workflows.

### Scenario C — `From` taken from form submitter's email

A contact form collects an email and the backend sets it as `From` on the email to support.

**Question:** what is the risk?

**Answer:** users can spoof senders. Set `From` to the product's verified address, and use a validated `Reply-To` if replies are needed.

### Scenario D — Display name containing less-than and greater-than signs

A customer uses a display name resembling an HTML tag.

**Question:** should all less-than/greater-than signs be rejected?

**Answer:** not necessarily. Display names in the body can be kept as data and rendered via `th:text` for HTML escaping. If used in headers, also enforce control-char/length policies and let Jakarta Mail encode the header properly.

### Scenario E — Order note containing HTML

`CustomerNote` is passed to `th:utext` to preserve line breaks.

**Question:** is that safe?

**Answer:** no if the note is untrusted. Use `th:text` with appropriate CSS/templates to render line breaks, or a dedicated sanitizer if business rules permit rich text. Never use `th:utext` just to preserve newlines.

### Scenario F — Action URL pointing to an unfamiliar domain

A webhook sends an HTTPS URL whose host is not in the allowlist.

**Question:** is escaping the HTML attribute enough?

**Answer:** no. HTTPS and attribute escaping do not guarantee a trusted destination. URLs must be generated or validated against server-side host/route policies.

### Scenario G — Lookalike domain

The URL is **`https://app.example.test.attacker.invalid/`**.

**Question:** is checking `contains("app.example.test")` enough?

**Answer:** no. Parse the URI and check the hostname against an exact allowlist. If subdomains are allowed, use separator-aware rules and explicit domain ownership governance.

### Scenario H — Template name coming from API

A client sends **`templateName=mail/admin/internal-report`** to an endpoint permitted only to send order confirmations.

**Question:** is it the template engine's job to check whether the user is allowed to use that template?

**Answer:** no. The application must map authorized business events to fixed templates. Never grant clients arbitrary template file selection.

### Scenario I — Template containing user-entered interpolation syntax

A user enters a string resembling a Thymeleaf expression, stored in `displayName`.

**Question:** will that string always be executed by the template engine?

**Answer:** not if it is strictly a `Context` data value rendered as text. Risk arises when the application embeds it into template source or re-evaluates rendered output as an expression. Keep source and data strictly separate.

### Scenario J — Uploaded filename containing paths

A client sends `originalFilename` with path segments. The backend uses it directly in `uploadDirectory.resolve(...)`.

**Question:** what is the risk?

**Answer:** path traversal or unintended file access. Storage keys must be server-generated; display filenames are validated separately.

### Scenario K — Attachment named `.pdf` whose bytes are not PDF

An upload supplies an invoice filename ending in `.pdf` with `Content-Type: application/pdf`.

**Question:** can the client's MIME type be trusted?

**Answer:** no. Client-declared extensions and headers do not prove content. Inspect signatures/formats, allowlists, and malware policies as required.

### Scenario L — Logo fetched from a user-supplied URL

The backend downloads a URL and embeds it as an inline image in the email.

**Question:** why does the risk go beyond HTML injection?

**Answer:** the server risks SSRF reaching internal hosts, downloading massive payloads, or leaking credentials if redirects/egress are uncontrolled. Use trusted resources or strict fetch policies.

### Scenario M — Emailing many customers via Bcc

A job sends personalized notifications to 500 people using a single message.

**Question:** should the Bcc list be rendered into the template so recipients know who else is listed?

**Answer:** no. Bcc is a hidden list. For independent notifications, one message per recipient usually gives better privacy, send-status tracking, and deduplication.

### Scenario N — A secondary system writes customer names to the database

Later, a scheduled job builds HTML by string concatenation with `customerName`.

**Question:** is the data safe because it was read from the database?

**Answer:** no. Original provenance may still be untrusted input. Apply context-appropriate HTML escaping when rendering.

### Scenario O — Logs containing reset tokens

When SMTP fails, the worker prints the full MIME message and `actionUrl` containing a password-reset token.

**Question:** how should this be handled?

**Answer:** log notification IDs, error categories, and statuses; restrict debug access and redact tokens and sensitive data. Never let account login/recovery secrets appear in logs.

### Scenario P — Users choosing their own SMTP host

A notification API accepts arbitrary `smtpHost`, `smtpUsername`, and `smtpPassword`.

**Question:** is this just a convenience setting?

**Answer:** no for an ordinary transactional API. It hands over control of transport and network connections. If per-tenant SMTP is truly supported, build a separate admin feature with authentication, secret storage, host/egress/TLS validation, and tenant permissions.

## 26. Data-protection workflow before sending email

~~~text
1. Receive request / event
        |
        v
2. Authenticate source and verify business permissions
        |
        v
3. Retrieve permitted recipients and sender identity
        |
        v
4. Parse/validate mailboxes, subject, custom header values
        |
        v
5. Select template from server enum/catalog
        |
        v
6. Prepare minimal mail model
        |
        +--> Validate required fields
        +--> Enforce size limits
        +--> Build URLs from trusted domains
        +--> Filter unnecessary sensitive data
        |
        v
7. Render
        |
        +--> HTML with context-aware escaping
        '--> Plain text from same business data
        |
        v
8. Prepare MIME
        |
        +--> From/Reply-To/To via dedicated APIs
        +--> Fixed header names, checked values
        +--> Verified Resource + filename + content type
        |
        v
9. Send via JavaMailSender with trusted SMTP config
        |
        v
10. Record status and errors safely
        |
        v
11. Track provider delivery/bounces when needed
~~~

### A code review checklist

- **Identity:** Are `From`/`Reply-To` controlled by the server, never taken arbitrarily from requests?
- **Authorization:** Is the caller authorized to send that mail type to the exact recipient?
- **Address:** Is every mailbox parsed, validated, and constrained by policy?
- **Header:** Do `Subject`/custom headers reject CR/LF/control chars and enforce length limits?
- **Template:** Do template sources/paths come from a trusted catalog?
- **Model:** Did you avoid passing entire entities with sensitive fields into `Context`?
- **HTML:** Is user data rendered via `th:text` or an appropriate escaping mechanism?
- **URL:** Are action URLs built/validated against HTTPS and host/route policies?
- **Attachment:** Are `Resource` objects fetched from trusted storage keys, with filenames/MIME types verified?
- **Transport:** Are SMTP credentials/TLS/hosts managed server-side?
- **Logs:** Do logs avoid recording OTPs/tokens/PII/raw SMTP credentials?
- **Tests:** Have injection, unauthorized recipients, spoofed URLs, and attachment path traversal been tested?

These questions serve as a safety design guide, not an automated security certification tool. For critical mail flows, threat modeling, integration testing, and organizational security reviews remain essential.

## 27. Key principles to remember

~~~text
Untrusted input -> never build arbitrary header structure
Valid email syntax -> does not guarantee permission to send
From and SMTP identity -> server-controlled
Reply-To -> validate and use only per business rules
Header values -> reject control chars, enforce length limits
Template source -> trusted code/catalog
User text -> data, not template expressions
HTML text -> context-appropriate escaping
HTML links -> escape attributes + validate URLs
Attachment filename -> metadata, not storage paths
Client Content-Type -> not proof of file format
SMTP config -> secrets/TLS/host server-controlled
Error logs -> minimal metadata, no leaked tokens or sensitive content
~~~

**Not trusting data to build headers, addresses, and templates** is how *trust boundaries* are applied across every step of email construction in Spring Framework Mail. **`MimeMessageHelper`** and **`InternetAddress`** help manipulate MIME structures and addresses through proper APIs, yet they do not decide who is allowed to send, which sender identity applies, or which URLs and templates are trustworthy. Pass untrusted data through per-field validation and authorization, keep sender/header/template structures under application control, use context-aware HTML escaping, and attach only verified files. When these boundaries are clearly designed, the system reduces header injection, spoofing, template/HTML injection, and SSRF risks while establishing a testable, operable foundation for transactional email flows.

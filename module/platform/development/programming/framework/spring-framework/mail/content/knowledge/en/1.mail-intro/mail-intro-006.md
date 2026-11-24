# Plain Text, HTML, and Multipart Messages in Spring Framework Mail

Sending an email from a Java application is not just pushing a string of characters to an SMTP server. The application must decide **in what format the recipient will view the content**, whether there is a fallback for mail readers that do not support HTML, and how images or attachments are packaged. Spring Framework Mail provides APIs for both simple plain-text emails and richly structured MIME emails.

In this lesson, we build plain-text messages, HTML messages, messages with two content versions, and multipart messages containing inline images and attachments. The examples use Spring Boot for convenient configuration, though the two core APIs—`JavaMailSender` and `MimeMessageHelper`—belong to Spring Framework Mail.

## 1. Distinguishing Message Content Types

An email is described by headers (such as `From`, `To`, `Subject`, `Content-Type`) and a body. The `Content-Type` header tells the mail reader how to interpret the body. Common types include:

| Content type | Typical `Content-Type` | Characteristics | When to use |
| --- | --- | --- | --- |
| Plain text | `text/plain; charset=UTF-8` | Text only; line breaks and URLs are rendered per mail client | OTPs, short alerts, system notices, readable fallback |
| HTML | `text/html; charset=UTF-8` | Contains HTML tags, links, colors, and layout; rendering varies across email clients | Welcome emails, invoices, structured notifications |
| Alternative | `multipart/alternative` | Contains **multiple representations of the same content**, typically plain text and HTML | HTML emails needing a fallback across diverse clients |
| Related | `multipart/related` | Groups content with related resources, e.g., images referenced via `cid:...` | Logos or images displayed directly inside HTML content |
| Mixed | `multipart/mixed` | Groups independent parts, typically message body and attachments | Sending PDFs, spreadsheets, or documents alongside body text |

**Important distinction:** "multipart" refers to a *MIME structure with multiple parts*, not sending a message to multiple recipients. `To`/`Cc`/`Bcc` control recipients; `multipart/*` describes how content is packaged.

For example, a notification email with a PDF and a logo can have this conceptual structure:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   └── image/png; Content-ID: <brandLogo>  (inline)
└── application/pdf                      (attachment)
```

The actual MIME tree may vary by library, but the three relationships to remember are: **alternative = alternate representations**, **related = resources tied to content**, **mixed = accompanying parts/files**.

## 2. Preparing Spring Mail

With Spring Boot and Maven, add the dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Spring Boot manages the corresponding dependency version via the project's BOM/parent. For an application using Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Declare SMTP settings in `src/main/resources/application.properties` (parameters are illustrative only; replace with your actual SMTP server):

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
```

`spring.mail.*` creates/configures a `JavaMailSender` bean when the starter and valid settings are present. SMTP username and password should come from environment variables or a secret manager; do not commit credentials to source code. Port `587` with STARTTLS is just one common configuration: some providers use different ports, TLS modes, and authentication mechanisms.

Important classes:

- `JavaMailSender`: creates and sends `MimeMessage`; also supports `SimpleMailMessage`.
- `SimpleMailMessage`: simple model for **plain-text-only** emails.
- `jakarta.mail.internet.MimeMessage`: MIME message object supporting HTML, multiple parts, and attached resources.
- `MimeMessageHelper`: Spring API for manipulating `MimeMessage`, such as `setText`, `addAttachment`, and `addInline`, with less direct Jakarta Mail code.

The examples below use imports from `jakarta.mail.*` (Spring Framework 6+/Spring Boot 3+) and Java 17+.

## 3. Sending Plain-Text Emails with `SimpleMailMessage`

When only a plain-text notification is needed, `SimpleMailMessage` is the clearest approach:

```java
package example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PlainTextMailService {
    private final JavaMailSender mailSender;

    public PlainTextMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOtp(String recipient, String otp) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Account verification code");
        message.setText(
            "Hello,\n\n"
            + "Your verification code is: " + otp + "\n"
            + "This code is only valid for the specified duration.\n\n"
            + "If you did not request this, you may ignore this email."
        );

        mailSender.send(message);
    }
}
```

`setText(...)` here takes a **plain-text string**, so characters like `<strong>` or `<a>` will not turn into HTML. Use `\n` for line breaks; do not write HTML tags manually. In a real application, OTP codes must be generated, time-limited, and verified securely in the business layer; the mail-sending part only handles delivering the content.

The advantages of plain text are simplicity, good readability with assistive technologies, and minimal susceptibility to HTML rendering quirks. The limitations are no rich formatting, no inline images, and no attachments via `SimpleMailMessage`.

If you still want a **plain-text-only** email but need special MIME headers or attachments, switch to `MimeMessage` rather than trying to extend `SimpleMailMessage`.

## 4. Sending HTML Emails with `MimeMessageHelper`

To send an HTML body, use `MimeMessage` and set the `html=true` flag:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlMailService {
    private final JavaMailSender mailSender;

    public HtmlMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            StandardCharsets.UTF_8.name()
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String html = """
            <!doctype html>
            <html lang="vi">
              <body>
                <h1>Welcome!</h1>
                <p>Your account has been created successfully.</p>
                <p><a href="https://example.com/account">Open account</a></p>
              </body>
            </html>
            """;

        helper.setText(html, true);
        mailSender.send(message);
    }
}
```

At `helper.setText(html, true)`, the second argument indicates **HTML**, causing the body to be packaged with `Content-Type: text/html`. Conversely, `helper.setText(html, false)` sends the string as plain text and HTML tags may appear literally.

The constructor `new MimeMessageHelper(message, "UTF-8")` sets the encoding, sufficient for a simple single-HTML-body example. `UTF-8` ensures Vietnamese diacritics display properly in both content and subjects. An email containing only `text/html` **does not automatically include** a `text/plain` fallback.

### Notes When Writing HTML for Email

Email HTML is not processed the same way as web pages in a browser:

- Many email clients restrict external CSS, JavaScript, forms, and interactive features; prefer simple HTML structure, inline CSS, and clear links.
- Use meaningful text even when images are blocked; add `alt` attributes to images.
- Use full URLs (e.g. `https://example.com/account`), avoiding relative paths like `/account`.
- Do not concatenate untrusted data directly into HTML. For instance, customer names containing `<`, `>`, or quotes must be contextually escaped; using a template engine is more practical.
- Keep content readable on small screens. Use clear headings, short paragraphs, and recognizable links.

## 5. Sending Both Plain Text and HTML with `multipart/alternative`

An HTML email should have a plain-text version expressing **the same message**. The mail reader selects the appropriate part based on its capabilities and user preferences. With Spring, use the `setText(plainText, htmlText)` overload:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AlternativeMailService {
    private final JavaMailSender mailSender;

    public AlternativeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotice(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        // multipart=true is required when providing alternative body parts.
        MimeMessageHelper helper = new MimeMessageHelper(
            message, true, StandardCharsets.UTF_8.name()
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order update");

        String plainText = "Order " + orderCode
            + " has been received.\n"
            + "View details: https://example.com/orders";

        // In a real application, escape variables when inserting into HTML.
        String htmlText = """
            <html><body>
              <h2>Order has been received</h2>
              <p>View your order details in your account.</p>
              <p><a href="https://example.com/orders">View order</a></p>
            </body></html>
            """;

        helper.setText(plainText, htmlText);
        mailSender.send(message);
    }
}
```

The two arguments of `setText(plainText, htmlText)` are **not** two separate emails, nor is the HTML part appended after the text part. They are two representations of one content body in MIME. You must initialize `MimeMessageHelper` in multipart mode (`true` or a `MULTIPART_MODE_*` constant); if the helper is not in multipart mode, this two-string overload does not work.

In the example above, the order code is placed in the plain-text version. If also displaying that code in HTML, use an escaping template as in section 8 to avoid injecting unsafe content. The two versions do not have to match character-for-character, but should contain equivalent key information and links, especially deadlines, amounts, warnings, and required actions.

The core structure can be understood as:

```text
multipart/alternative
├── text/plain  → "Order has been received..."
└── text/html   → "<h2>Order has been received</h2>..."
```

When Spring uses combined multipart mode for attachments as well, `multipart/alternative` can be nested inside a `related`/`mixed` part. Those remain alternative representations of the same message body.

## 6. Multipart Messages with Inline Images and Attachments

A promotional email or transaction notification might need a **logo displayed directly inside the HTML** and an **attached PDF for download**. These are two different cases:

- **Inline**: the resource is referenced in HTML using `cid:<content-id>`; on the MIME side there is a matching `Content-ID` header.
- **Attachment**: the resource appears as an attached file, typically with `Content-Disposition: attachment` and a filename.

Use `MULTIPART_MODE_MIXED_RELATED` so Spring builds the appropriate structure for body content, inline resources, and attachments.

Suppose two files already exist in the application:

```text
src/main/resources/
└── mail/
    ├── brand-logo.png
    └── huong-dan.pdf
```

Service example:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MultipartMailService {
    private final JavaMailSender mailSender;

    public MultipartMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendGuide(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("User guide");

        String plainText = """
            Hello!

            We are sending you the user guide in the attached file.
            Visit https://example.com/support if you need assistance.
            """;

        String htmlText = """
            <!doctype html>
            <html lang="vi">
              <body>
                <img src="cid:brandLogo" alt="Brand logo" width="120">
                <h2>User guide</h2>
                <p>Please check the attached PDF for step-by-step instructions.</p>
                <p><a href="https://example.com/support">Support center</a></p>
              </body>
            </html>
            """;

        // Set the body before adding inline resources.
        helper.setText(plainText, htmlText);

        helper.addInline(
            "brandLogo",
            new ClassPathResource("mail/brand-logo.png"),
            "image/png"
        );

        helper.addAttachment(
            "huong-dan.pdf",
            new ClassPathResource("mail/huong-dan.pdf")
        );

        mailSender.send(message);
    }
}
```

Analyzing each important call:

1. `MULTIPART_MODE_MIXED_RELATED` creates the MIME layout suited for body, inline items, and attachments. Multipart mode should only be enabled when the content needs it.
2. `setText(plainText, htmlText)` adds two body representations so readers have a fallback.
3. `addInline("brandLogo", ...)` sets the image's content ID; the `src="cid:brandLogo"` attribute in HTML must match this ID **exactly**. You should call `setText` **before** `addInline` to improve compatibility across email clients.
4. `addAttachment("huong-dan.pdf", ...)` adds a file for the recipient to download. The first parameter is the displayed filename; `ClassPathResource` points to a resource on the classpath.
5. `mailSender.send(message)` hands the message off to the mail-sending system. This call does not guarantee the email reached the inbox: the receiving server may still filter, defer, or reject it.

Other overloads of `addAttachment` and `addInline` accept `File`, `InputStreamSource`, or other data sources. With streams, ensure they can be re-read when the library builds MIME; do not pass an already-consumed `InputStream` to the sending process.

### Why Might Inline Images Still Not Appear?

Some clients block loading/displaying images by security policy, alter the MIME structure, or do not support `related` packaging as expected. Therefore, always include `alt` text and keep core information in text; a logo should only supplement readability.

Images attached via `cid:...` are not the same as Internet image links (`https://...`). With `cid`, image data is attached as a related MIME part; with a remote URL, the mail reader may need to fetch additional data over the network.

## 7. Choosing the Appropriate API and Structure

| Need | API and how content is set | Result |
| --- | --- | --- |
| Text-only OTP | `SimpleMailMessage#setText(text)` | Simple plain-text message |
| HTML-only message | `MimeMessageHelper#setText(html, true)` | HTML body, no plain-text auto-generated |
| HTML message with fallback | Multipart helper + `setText(plain, html)` | Two content versions |
| HTML with embedded image | Multipart helper + `addInline(id, resource, type)` | Body and related resource |
| Message with PDF | Multipart helper + `addAttachment(name, resource)` | Body and attached file |
| Inline image, PDF, and fallback combined | `MULTIPART_MODE_MIXED_RELATED` + all three calls | Corresponding nested MIME |

A common point of confusion: `helper.setText(html, true)` and `helper.setText(plain, html)` are **two different overloads**. In the single-string plus boolean overload, `true` means "the input is HTML". In the two-string overload, the first string is plain text and the second is HTML, requiring the helper to be in multipart mode.

### Multipart Modes of `MimeMessageHelper`

| Mode | Meaning |
| --- | --- |
| `MULTIPART_MODE_NO` | Do not create multipart |
| `MULTIPART_MODE_MIXED` | Use `multipart/mixed` as the general container |
| `MULTIPART_MODE_RELATED` | Use `multipart/related` for interrelated parts |
| `MULTIPART_MODE_MIXED_RELATED` | Combines a `mixed` container with a nested `related` container; useful when having both body/images and attachments |

The default mode when using the `multipart=true` constructor is `MULTIPART_MODE_MIXED_RELATED` in common Spring Framework versions. When explicit structure is desired, passing the mode constant as shown above helps code readers understand the intent.

## 8. Generating Dynamic HTML with Templates

Embedding long HTML directly in Java is only suitable for small examples. In real applications, templates separate email layout from business processing and handle escaping user data. One option is **Thymeleaf**.

If not already present, add the dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Place the template at `src/main/resources/templates/mail/welcome.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
  <body>
    <h1>Welcome!</h1>
    <p>Hello <strong th:text="${customerName}">Customer</strong>,</p>
    <p>Your account is ready.</p>
    <p><a th:href="${accountUrl}">Access account</a></p>
  </body>
</html>
```

The `${...}` expressions on attributes in a real template are Spring/Thymeleaf expressions evaluated when generating content. Java side:

```java
import java.util.Locale;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

// templateEngine is provided by Spring via appropriate dependency/configuration.
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", customerName);
context.setVariable("accountUrl", "https://example.com/account");
String html = templateEngine.process("mail/welcome", context);

// Then call helper.setText(plainText, html) in a multipart MimeMessageHelper.
```

`th:text` escapes HTML-significant characters when inserting names or dynamic content. For link attributes, validate/restrict destination URLs on the application side; HTML escaping does not replace URL validation. Avoid `th:utext` for unsanitized data because it injects raw HTML.

If content is sent in multiple languages, you can create separate templates, use `MessageSource`, and generate corresponding plain text. Do not assume that converting HTML to plain text by stripping tags will produce a readable fallback: links, tables, buttons, and emphasis may lose meaning.

## 9. Recipient Addresses, Encoding, and Responsibility Boundaries

`setTo`, `setCc`, and `setBcc` on `MimeMessageHelper` control recipients:

```java
helper.setTo("customer@example.com");
helper.setCc("support@example.com");
helper.setBcc("audit@example.com");
```

`Cc` recipients receive a copy and are visible to other recipients; `Bcc` recipients normally do not appear in the disclosed recipient list. Adding multiple recipients does not create "multipart". When emailing multiple people who need privacy, consider sending individually instead of placing everyone in `To`.

UTF-8 encoding should be applied consistently in mail configuration and when creating the helper to prevent broken Vietnamese characters. Spring/Jakarta Mail handles encoding headers and bodies according to MIME standards; do not manually insert `Content-Type` or encoding headers when using the helper.

In a mail-sending service, distinguish three stages:

1. **Content generation**: build plain text/HTML, choose appropriate versions, sanitize data.
2. **MIME packaging**: select multipart mode, attach inline resources, attachments, and headers.
3. **Sending via SMTP**: transmit the MIME message to the configured sending server.

`MessagingException` generally relates to manipulating/packaging `MimeMessage`. Errors from the Spring Mail layer during sending may appear as `MailException` subtypes, such as authentication or send failures. Do not swallow errors and report success.

## 10. Common Errors and How to Identify Them

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Recipient sees raw `<h1>` tags | Sent HTML as plain text | Use `helper.setText(html, true)` or `setText(plain, html)` |
| HTML message has no text version | Only called `setText(html, true)` | Supply plain text separately and use the two-string overload |
| Error when calling `setText(plain, html)` | Helper does not have multipart enabled | Initialize with `true` or an appropriate multipart mode |
| Logo image does not display | Mismatched `cid:` ID, wrong MIME order, client blocking images | Check ID; call `setText` before `addInline`; include `alt` |
| Attachment not found | Wrong classpath path or file not packaged into application | Verify location under `src/main/resources` and resource name |
| Broken Vietnamese diacritics | Inconsistent encoding | Use UTF-8 when creating helper, configuration, and templates |
| SMTP authentication error | Wrong user/password, auth mechanism, or provider requirement | Check SMTP/TLS settings and credentials |
| Sent mail does not reach inbox | Spam filtering, receiving server policy, domain config, or delivery status | Check SMTP server logs, bounces, and SPF/DKIM/DMARC setup |

**Distinguishing "send" errors from "delivery" errors:** `JavaMailSender#send(...)` may finish after the SMTP server accepts the message, yet the message may still be rejected or classified afterward. Critical systems must track delivery/bounce statuses according to the SMTP provider's capabilities rather than treating a successful API call as proof that the user read the message.

### Some Operational Principles

- Limit attachment sizes according to SMTP and application policies; some servers reject large messages.
- Do not send passwords or unnecessary sensitive data in email bodies. For verification links, enforce expiration and usage rules on the server side.
- Avoid logging full email bodies, OTPs, bulk recipient addresses, or secret SMTP credentials.
- When sending at high volume, consider queues and controlled retries. Blind retries can cause duplicates if the server received the message before a response connection dropped.
- For emails from an organization's domain, configure SPF, DKIM, and DMARC appropriately to improve authentication and sending reputation.
- Test rendering across target email clients; the same HTML can look different in Gmail, Outlook, and mobile apps.

## 11. Applying to a Complete Scenario

Suppose you need to send a "Getting Started Guide" email to a new user with these requirements: readable even with HTML disabled, includes a logo, includes an attached guide PDF, and has a support link. A sound implementation is:

1. Write the **plain-text version** containing the greeting, purpose, and support URL.
2. Create the **HTML version** with equivalent content, an email-client-friendly layout, and `alt` attributes for images.
3. Use `MimeMessageHelper` in `MULTIPART_MODE_MIXED_RELATED` mode.
4. Call `setText(plainText, htmlText)` to include the alternative representations.
5. Call `addInline("brandLogo", ...)` and reference `cid:brandLogo` in the HTML.
6. Call `addAttachment("huong-dan.pdf", ...)`.
7. Send with `JavaMailSender#send`, recording SMTP handling results according to application requirements.

The `MultipartMailService` example in section 6 illustrates this entire process. Simply omit `addInline` if there are no inline images; omit `addAttachment` if no PDF is needed; and if only sending a few lines of text, `SimpleMailMessage` in section 3 remains the cleanest choice.

When working with Spring Framework Mail, choose the API based on **the content format the recipient needs**: `SimpleMailMessage` for simple plain text; `MimeMessageHelper` for HTML, alternative representations, inline images, and attachments. Understanding the `alternative`, `related`, and `mixed` relationships helps design messages that are easier to read, more compatible, and easier to extend as mail-sending features evolve.

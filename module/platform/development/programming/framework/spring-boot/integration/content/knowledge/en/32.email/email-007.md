# Email Templates, Localization, and Character Encoding

## 1. Why Does Email Need Templates, Localization, and Encoding Together?

In a **Spring Boot Integration** application, email is often the final step of a business flow: account confirmation, password reset, order notification, invoice delivery, or operational alerts. Recipients must receive the **right content, in the right language, with the right characters**, regardless of the environment used by the SMTP server or mail reader.

These three concerns serve distinct roles:

| Component | Problem Solved | Example |
| --- | --- | --- |
| **Template** | Separates presentation structure from business logic. | A `welcome.html` template taking a user's name and confirmation link. |
| **Localization (i18n)** | Selects translations and formats dates, times, and amounts for the recipient. | “Xác nhận tài khoản” for `vi`; “Confirm account” for `en`. |
| **Character encoding** | Represents and transmits Vietnamese diacritics, special characters, and emojis over MIME/SMTP. | “Trần Ánh”, “Đơn hàng”, “🎉” do not turn into question marks or garbled characters. |

Do not embed raw HTML, translations, and SMTP configuration inside the same mail-sending method. A typical flow is:

~~~mermaid
flowchart LR
    A[Application emits event] --> B[Select recipient and Locale]
    B --> C[Load localized messages]
    C --> D[Render template with data]
    D --> E[Build MIME: text/plain and text/html, UTF-8]
    E --> F[JavaMailSender]
    F --> G[SMTP and recipient mailbox]
~~~

Here, **Spring Boot** configures SMTP and creates `JavaMailSender`; **Thymeleaf** builds the HTML part; **MessageSource** retrieves localized phrases by `Locale`; **Jakarta Mail** builds the MIME content and headers. The examples below follow Spring Boot 3+ style with `jakarta.mail`.

## 2. Preparing Dependencies and Configuration

With Maven, you need the mail-sending dependency and the template engine:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
</dependencies>
~~~

Example `application.properties`:

~~~properties
spring.mail.host=smtp.example.net
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

spring.messages.basename=messages/email
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

app.mail.from=no-reply@example.net
~~~

`SMTP_USERNAME` and `SMTP_PASSWORD` are supplied through environment variables or a secret management system; never place real passwords in source control. The address `smtp.example.net` is only an example and must be replaced with your system's SMTP provider. The configuration above uses STARTTLS on port 587; servers using implicit TLS on port 465 require corresponding SSL/TLS settings per provider. Timeouts prevent mail-sending threads from hanging indefinitely during network issues.

When using Thymeleaf with Spring Boot auto-configuration, HTML templates are looked up in `src/main/resources/templates/` by default. Clearly decide who owns the `From` address, sender display name, brand name, and each language version.

## 3. Organizing Mail Templates and Language Resources

A simple, extensible structure for multiple email types:

~~~text
src/main/resources/
├── templates/
│   └── mail/
│       └── welcome.html
└── messages/
    ├── email.properties
    └── email_vi.properties
~~~

`email.properties` acts as the default English bundle when no specific translation is found. Example:

~~~properties
mail.from.name=Example Shop
mail.welcome.subject=Welcome to Example Shop
mail.welcome.title=Welcome!
mail.welcome.greeting=Hello {0},
mail.welcome.intro=Please confirm your email address to activate your account.
mail.welcome.action=Confirm account
mail.welcome.signature=The Example Shop team
mail.welcome.plain=Hello {0}. Confirm your account at: {1}
~~~

`email_vi.properties` holds the Vietnamese translation:

~~~properties
mail.from.name=Cửa hàng Ví Dụ
mail.welcome.subject=Chào mừng bạn đến với Cửa hàng Ví Dụ
mail.welcome.title=Chào mừng bạn!
mail.welcome.greeting=Xin chào {0},
mail.welcome.intro=Vui lòng xác nhận địa chỉ email để kích hoạt tài khoản của bạn.
mail.welcome.action=Xác nhận tài khoản
mail.welcome.signature=Đội ngũ Cửa hàng Ví Dụ
mail.welcome.plain=Xin chào {0}. Hãy xác nhận tài khoản tại: {1}
~~~

Both files must be saved as **UTF-8**. With `spring.messages.basename=messages/email`, `MessageSource` resolves these keys by `Locale`. Parameters `{0}`, `{1}` are substituted at render time, avoiding manual string concatenation. If a translation uses `MessageFormat`-style placeholders, single quotes inside the translation may need to be escaped as `''`; test English sentences containing apostrophes.

An HTML template `templates/mail/welcome.html`:

~~~html
<!doctype html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org"
      th:lang="${#locale.language}">
<head>
    <meta charset="UTF-8">
    <title th:text="#{mail.welcome.subject}">Welcome</title>
</head>
<body>
    <h1 th:text="#{mail.welcome.title}">Welcome!</h1>
    <p th:text="#{mail.welcome.greeting(${customerName})}">Hello</p>
    <p th:text="#{mail.welcome.intro}">Please confirm your account.</p>
    <p>
        <a th:href="${confirmationUrl}"
           th:text="#{mail.welcome.action}">Confirm account</a>
    </p>
    <p th:text="#{mail.welcome.signature}">The team</p>
</body>
</html>
~~~

In Thymeleaf, `#{...}` looks up a localized message, `${customerName}` reads a variable from `Context`, and `#{mail.welcome.greeting(${customerName})}` passes the name into parameter `{0}` of the translation. `th:text` automatically HTML-escapes names and user-supplied text. Do not use `th:utext` for untrusted data; injecting raw HTML into a message can create malicious links or forged content. Links in `th:href` still require URLs validated and generated by the application from a trusted domain.

In practice, keep HTML emails concise and use layout tables or inline CSS when compatibility across many mail clients is needed. Do not rely on JavaScript since most email clients do not execute scripts.

## 4. Choosing Locale by Recipient, Not by Server

`Locale` should come from the user's chosen language or account profile. Only when that choice is absent should you consider request hints such as `Accept-Language`, and then apply the system's supported-language policy.

Example for an application supporting Vietnamese and English:

~~~java
private static Locale supportedLocale(String languageTag) {
    Locale requested = Locale.forLanguageTag(
            languageTag == null ? "" : languageTag);
    if ("en".equals(requested.getLanguage())) {
        return Locale.ENGLISH;
    }
    return Locale.forLanguageTag("vi");
}
~~~

`en-US` and `en-GB` both resolve to English; `vi-VN` and unsupported values resolve to Vietnamese under this example policy. Do not default to the operating system's `Locale.getDefault()`: the same email could switch languages when deployed to a different server. In asynchronous flows using `@Async`, queues, or Spring Integration, never assume `LocaleContextHolder` still holds the Locale from an HTTP request; carry the language code inside the send command or event payload.

For dates, times, and monetary amounts, string translation alone is not enough:

- Use `DateTimeFormatter` with `Locale` and the **recipient's time zone or an agreed time zone**; the same `Instant` displays differently across regions.
- Use `NumberFormat`/`DecimalFormat` by Locale while preserving the **actual transaction currency**; do not switch an amount to USD simply because the user selected English.
- Translate link alt text, sender display names, error notices, and the plain-text version too. Avoid assembling sentences from translated fragments, which breaks word order across languages.

## 5. Building HTML and Plain-Text Emails with JavaMailSender

Here is an example service for account confirmation emails. The `confirmationUrl` parameter must be generated server-side by the application using HTTPS and a sufficiently strong, expiring token. The example focuses on rendering and content encoding; in a real system, validate recipients and input data in the business layer.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.UnsupportedEncodingException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.MessageSource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final MessageSource messageSource;
    private final String fromAddress;

    public WelcomeMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            MessageSource messageSource,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.messageSource = messageSource;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(
            String recipient,
            String customerName,
            String preferredLanguage,
            URI confirmationUrl) {

        Locale locale = supportedLocale(preferredLanguage);
        Context context = new Context(locale);
        context.setVariable("customerName", customerName);
        context.setVariable("confirmationUrl", confirmationUrl.toString());

        String html = templateEngine.process("mail/welcome", context);
        String plain = messageSource.getMessage(
                "mail.welcome.plain",
                new Object[] { customerName, confirmationUrl.toString() },
                locale);
        String subject = messageSource.getMessage(
                "mail.welcome.subject", null, locale);
        String senderName = messageSource.getMessage(
                "mail.from.name", null, locale);

        MimeMessage mime = mailSender.createMimeMessage();
        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name());
            helper.setFrom(fromAddress, senderName);
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(plain, html);
        } catch (MessagingException | UnsupportedEncodingException ex) {
            throw new IllegalStateException("Cannot compose welcome email", ex);
        }

        mailSender.send(mime);
    }

    private static Locale supportedLocale(String languageTag) {
        Locale requested = Locale.forLanguageTag(
                languageTag == null ? "" : languageTag);
        return "en".equals(requested.getLanguage())
                ? Locale.ENGLISH
                : Locale.forLanguageTag("vi");
    }
}
~~~

In this example:

1. `Context(locale)` binds the Locale to the template; `MessageSource` uses the same Locale for the subject, sender name, and plain-text version.
2. `templateEngine.process("mail/welcome", context)` reads `templates/mail/welcome.html`; data such as `customerName` are only rendering variables.
3. `MimeMessageHelper` receives charset `UTF-8` to build Vietnamese-capable content and headers. `setFrom(fromAddress, senderName)` supports accented characters in the sender display name.
4. `setText(plain, html)` creates both **text/plain** and **text/html** parts in one MIME message; the mail client chooses the appropriate format. `MULTIPART_MODE_MIXED_RELATED` allows a multipart structure including related content and attachments if needed later.
5. `mailSender.send` invokes SMTP. MIME-building errors are wrapped as an application exception; Spring Mail transport exceptions (such as `MailSendException`) still need to be handled by the sending layer's retry/monitoring mechanism.

Never send HTML alone: plain text supports constrained readers, accessibility modes, certain email filters, and diagnostics. Both versions must carry the same meaning, links, and language.

## 6. UTF-8 and MIME Structure: Understanding It Correctly to Avoid Garbled Diacritics

SMTP transmits messages in MIME format. Separating **Unicode strings in Java** from **encoded bytes on the wire** is the key to diagnosing encoding issues.

| Location | Correct Handling | Common Mistake |
| --- | --- | --- |
| `.properties` and `.html` files | Save as UTF-8; `spring.messages.encoding=UTF-8`. | Saving files with the wrong encoding before rendering, producing `?` or `Ã¡`. |
| `Subject` header | Call `helper.setSubject(subject)` on a helper configured with UTF-8. | Inserting raw Unicode strings into raw headers without MIME encoding. |
| `From` display name | `helper.setFrom(email, displayName)`; the library encodes the Unicode name. | Manually concatenating `From: Accented Name <mail@...>`. |
| Text and HTML bodies | `helper.setText(plain, html)` with UTF-8 charset. | Only putting `<meta charset="UTF-8">` in HTML while MIME declares a different charset. |
| Special characters in HTML | `th:text` escapes content; `th:href` builds attributes from validated URLs. | Interpolating user data directly into markup or URLs. |
| Mailbox address | Validate syntax and SMTP support; prefer ASCII local-parts when feasible. | Confusing Unicode in display names with `SMTPUTF8` requirements for the email address itself. |

A message can have a logical structure like this (illustrative only; actual MIME boundaries are generated by Jakarta Mail):

~~~text
Subject: [MIME-encoded header when needed]
From: [encoded display name] <no-reply@example.net>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=...

  multipart/related
    multipart/alternative
      text/plain; charset=UTF-8
      text/html; charset=UTF-8
~~~

Subject lines and display names may appear as `=?UTF-8?B?...?=` or `=?UTF-8?Q?...?=` in raw headers per RFC 2047; mail readers decode them back to Unicode characters. For body parts, JavaMail may select `quoted-printable` or `base64` as `Content-Transfer-Encoding`. That is normal; do not manually Base64-encode or add RFC 2047 prefixes before calling the helper.

`Content-Type: ...; charset=UTF-8` on each MIME part is what governs decoding. `<meta charset>` helps some HTML viewers, but **does not replace** the MIME declaration. Never convert strings via `getBytes()` or `new String(bytes)` without specifying a charset when handling template files or external data yourself.

If sending attachments, call `helper.addAttachment(...)` after setting the body parts, using `InputStreamSource`/`ByteArrayResource` and an appropriate MIME type. Do not derive filenames directly from untrusted user input; large files are usually better served via access-controlled download links than direct attachments.

## 7. Designing a Safe and Maintainable Integration Flow

**Separating data, content, and transport** makes it easy to scale from account confirmation emails to invoices, OTPs, and status notifications. Pass a send-request object containing `recipient`, `templateKey`, `locale`, and validated variables into the service rather than building HTML inside controllers. Each template needs versioning or change control when legal text, links, or branding change.

In a system using queues or Spring Integration:

1. The business transaction records the order state and an email-send event (an outbox when durability is required).
2. A worker reads the event and picks the template and language from the data stored with the event/recipient.
3. The worker composes MIME and sends over SMTP; records status, attempt count, error codes, and correlation IDs.
4. Retries on transient errors with backoff; defines a deduplication key so two emails are not sent when a worker or SMTP retries after a timeout.

`JavaMailSender.send(...)` is an I/O operation that can be slow or fail; SMTP errors must not corrupt an already committed business transaction. At the same time, SMTP accepting an email does not guarantee inbox placement: monitor bounces, complaints, or provider webhooks if required by the business.

For confirmation/password-reset links, generate HTTPS URLs on a configured domain using short-lived, single-use tokens, and never log tokens. For promotional emails, separate transactional from marketing content and manage consent and unsubscribe mechanisms as required. For personal data, limit sensitive details in subjects and preview text since those may appear on lock screens.

## 8. Testing and Troubleshooting

Test at two layers: **rendering/MIME** without a real SMTP server, and **integration sending** through a test SMTP server (such as GreenMail or a provider sandbox). Minimum test suite:

| Test Case | Expected Result |
| --- | --- |
| Name “Trần Thị Ánh”, `vi` locale | Subject, sender display name, HTML, and plain text all render with full accents. |
| `en-US` and `en-GB` | Selects English keys; no Vietnamese phrases leak outside specific data fields. |
| `fr-FR` or no preference | Applies the Vietnamese fallback policy defined in `supportedLocale`. |
| Name containing `<b>`, `&`, or quotes | HTML renders literal text without producing unintended HTML tags. |
| Translation missing a key | Detects untranslated keys or falls back to the base bundle; validate full key coverage at release. |
| Confirmation link with query parameters | Valid `href`, properly encoded, still pointing to the approved domain. |
| Inspect MIME after test send | Finds both `text/plain` and `text/html`; text parts declare UTF-8. |
| SMTP timeout or transient error | Logged/metered and retried per policy; no uncontrolled duplicate emails. |

When inspecting with Jakarta Mail, `mimeMessage.getSubject()` typically returns the **decoded** Unicode value, whereas `getHeader("Subject")` returns the raw encoded header. For multipart messages, traverse the MIME parts to check the charset of `text/plain` and `text/html`; the root `Content-Type` header is usually only `multipart/*`.

Specific diagnostic pointers:

- **Characters turn into `Ã¡`, `á»`, or `?`**: check the raw bytes of the resource files, `MessageSource` configuration, and MIME charset; the corruption usually occurs before sending.
- **HTML is fine but Subject/From is broken**: check how headers are set; do not manually concatenate headers or hand-encode Base64.
- **Looks right in a browser but broken in email**: email clients support limited HTML/CSS; check the plain-text version, absolute HTTPS URLs, and inline CSS.
- **Worker sends in the wrong language**: check whether `Locale` is passed along with the job; do not rely on request-thread state.
- **Duplicate emails sent**: check idempotency keys, send confirmation checkpoints, and timeout scenarios after SMTP has already accepted the message.

## 9. Practical Guidelines

For Spring Boot email integrations, a complete implementation includes **HTML templates**, **plain-text bodies**, **UTF-8-encoded translation bundles**, **explicitly chosen Locales**, **UTF-8 MIME charsets**, and **realistic test scenarios with Vietnamese text**. When expanding to additional languages, adding a bundle and verifying translations is far smoother than editing Java code for every sentence. Separating message composition from transport also makes error handling, retries, and observability consistent across the integration flow.

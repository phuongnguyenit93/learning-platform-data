# Generating Stable Content-IDs Within a Message

When sending HTML emails with images displayed directly inside the body, applications typically use **inline resources**. A common example is a company logo, status icon, or illustration placed between paragraphs. The HTML references the image using an address of the form `cid:...`, while the email contains a MIME part with the matching `Content-ID` header.

What matters is that both sides use **the exact same identifier**. If the template generates `cid:logo-a` while the MIME part is given `Content-ID: <logo-b>`, the mail client cannot link the image to its display location. If two different images share the same Content-ID within the same message, the result also becomes ambiguous.

In Spring Framework Mail, `MimeMessageHelper.addInline(...)` attaches an inline resource to the message. The application must generate Content-IDs consistently within a message, pass that exact value to both the template and the helper, and ensure distinct inline parts have separate IDs.

This lesson explains CID structure, uniqueness scope, per-message ID generation, usage with Thymeleaf and `MimeMessageHelper`, and common mistakes when an email has multiple inline images.

## 1. What is Content-ID?

**Content-ID** is a MIME header used to identify a content part within a message. For an inline image, the MIME part may contain:

```text
Content-Type: image/png
Content-ID: <logo-7c9f2a@example.org>
Content-Disposition: inline
Content-Transfer-Encoding: base64
```

The HTML in the body references that part:

```html
<img src="cid:logo-7c9f2a@example.org" alt="Company logo"/>
```

The two representations correspond as follows:

| Location | Illustrative value | Role |
| --- | --- | --- |
| MIME part header | `Content-ID: <logo-7c9f2a@example.org>` | Identifier of the part |
| HTML attribute | `src="cid:logo-7c9f2a@example.org"` | Reference to the part by Content-ID |

`cid:` is the **Content-ID URI** scheme. The mail client reads the HTML, looks up the referenced CID, and links it to the MIME part with the matching Content-ID.

### Which identifiers differ from Content-ID?

| Identifier | Scope and purpose |
| --- | --- |
| **Content-ID** | Identifies a MIME body part, such as an inline image |
| **Message-ID** | Identifies the entire email message |
| **Content-Location** | May indicate content location or a related URI in certain MIME structures |
| **Filename** | Display/save filename, typically in Content-Disposition |
| **CID URI** | How HTML references a MIME part via Content-ID |
| **HTTPS URL** | Resource fetched over the network from a web address |

For example, an email might have:

```text
Message-ID: <message-123@example.org>

Part 1:
  Content-Type: text/html; charset=UTF-8

Part 2:
  Content-Type: image/png
  Content-ID: <logo-456@example.org>
  Content-Disposition: inline
```

Message-ID identifies the **entire message**; Content-ID identifies the **part containing the logo**. Do not use Message-ID as the CID for every image in the email.

## 2. How must Content-ID be stable and unique?

Two requirements must hold simultaneously:

1. **Stable within a message:** the value used in the HTML must match the exact value attached to the MIME part.
2. **Unique:** each distinct inline resource needs its own Content-ID; under MIME rules, Content-ID values are required to be globally unique.

RFC 2392 specifies that Content-ID is used to reference MIME body parts and requires Content-ID values to be globally unique. In application practice, an easy approach is to generate an ID with a sufficiently strong random component and a domain controlled by your system.

Example:

```text
logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org
```

This value can be used in:

```text
HTML:
  src="cid:logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org"

MIME:
  Content-ID: <logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org>
```

### Why not use one fixed CID for all emails?

Example:

```java
private static final String LOGO_CID = "logo@example.org";
```

This constant ensures the HTML and MIME part within a single send can share the ID. However, if applied identically to every email, the Content-ID value repeats across different messages, failing the format's global uniqueness requirement.

A better option is to **generate a fresh CID per message**, then reuse that exact value everywhere within that message:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
```

If the same logo is referenced in three places in the HTML, all three places use the same `logoCid`, and the message only needs one MIME part containing the logo.

### "Stable" does not mean fixed across all emails

In this lesson, stable means:

- Generate the ID exactly once for each inline resource in the message.
- Store that value in the mail model/context or a local variable during message construction.
- Reuse the exact same value when rendering HTML and calling `addInline`.
- Do not regenerate IDs independently in two separate layers.

For the next message, a new CID can be generated. If business requirements demand regenerating the exact same message across retries, you can combine a unique notification ID with the resource name to produce a deterministic ID. In that case, ensure the notification ID is unique across the required scope and never put personal data or secrets into the CID.

## 3. Structure of Content-ID and CID URI

In a MIME header, Content-ID is represented in message-id format, typically enclosed in angle brackets:

```text
Content-ID: <logo-550e8400@mail.example.org>
```

In HTML, the CID reference omits the angle brackets and adds the `cid:` scheme:

```html
<img src="cid:logo-550e8400@mail.example.org" alt="Logo"/>
```

With `MimeMessageHelper`, pass the Content-ID value **without angle brackets and without the `cid:` prefix**. The helper formats the MIME header accordingly.

Example:

```java
String contentId = "logo-550e8400@mail.example.org";

helper.addInline(
        contentId,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

In HTML:

```html
<img src="cid:logo-550e8400@mail.example.org" alt="Logo"/>
```

Do not pass:

```java
// Do not add angle brackets:
helper.addInline(
        "<logo-550e8400@mail.example.org>",
        resource,
        "image/png"
);

// Do not add cid: to the argument:
helper.addInline(
        "cid:logo-550e8400@mail.example.org",
        resource,
        "image/png"
);
```

Because the helper may wrap the value in angle brackets automatically, passing the wrong format risks producing malformed headers or causing the CID in HTML not to match the MIME part.

### Use simple characters

Generate IDs using simple ASCII characters, such as:

- Latin letters.
- Digits.
- Hyphens `-`.
- Dots `.`.
- An `@` sign separating the local part and domain.

Avoid whitespace, line breaks, angle brackets, quotes, and control characters. CID URIs have specific escaping rules when special characters are present; using a simple token reduces the risk of complex encoding/decoding issues.

Do not derive CIDs directly from filenames, customer names, or request input. Generate identifiers on the backend using application-controlled rules.

## 4. Relationship between CID and multipart/related

Inline images typically reside in a `multipart/related` MIME structure. One part contains the HTML, and the remaining parts hold the images referenced by the HTML.

```text
MimeMessage
└── multipart/related
    ├── text/html; charset=UTF-8
    │     |
    │     +-- <img src="cid:logo-...@mail.example.org">
    │     +-- <img src="cid:banner-...@mail.example.org">
    │
    ├── image/png
    │     Content-ID: <logo-...@mail.example.org>
    │
    └── image/jpeg
          Content-ID: <banner-...@mail.example.org>
```

Each image has its own MIME part and Content-ID. HTML uses the CID URI to link to the matching part.

### Inline resource vs. regular attachment

| Characteristic | Inline resource | Attachment |
| --- | --- | --- |
| Purpose | Displayed inside HTML content | Opened or downloaded separately by recipient |
| Spring API | `addInline(...)` | `addAttachment(...)` |
| Typical disposition header | `inline` | `attachment` |
| HTML reference | `src="cid:..."` | Usually not needed |
| Content-ID | Needed for HTML reference | May exist but not normally required for file download |

An image can be embedded inline and displayed inside HTML; a PDF invoice is typically an attachment. Do not use `addAttachment` and expect `cid:...` to locate the image automatically. Use the inline API for resources referenced by the HTML.

### Do you need to set the multipart/related header manually?

No. When using `MimeMessageHelper`, choose the appropriate multipart mode and call `setText`/`addInline`. The helper and Jakarta Mail manage the part structure and boundaries.

Example for an HTML email with inline images:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        StandardCharsets.UTF_8.name()
);
```

If the email has both inline images and regular file attachments, use the mode that supports mixed/related:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);
```

Choose the mode based on the content structure to send; do not manually assign `Content-Type: multipart/related` via `setHeader`.

## 5. Generate Content-ID once in the mail-building layer

The most important implementation rule is to **generate the ID in one place and pass it everywhere it is needed**.

Do not let the template generate one value while the service calling `addInline` generates another UUID. The template engine should not decide MIME part identities on its own.

A clear flow:

```text
Mail composer
    |
    | generate logoCid once
    |
    +----------------------+
    |                      |
    v                      v
Template context       MimeMessageHelper
logoCid = value        addInline(value, resource)
    |                      |
    v                      v
src="cid:value"        Content-ID: <value>
    |                      |
    +----------+-----------+
               |
               v
       Consistent MIME message
```

Example:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";

context.setVariable("logoCid", logoCid);

String html = templateEngine.process(
        "mail/notification",
        context
);

helper.setText(plainText, html);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

The `logoCid` value is created before rendering, then reused when attaching the resource. This guarantees that the string in the HTML and the MIME part match.

### Why generate the CID before rendering the template?

The template needs the value to produce `src="cid:..."`. If the CID is generated only after HTML rendering, the application would have to patch the HTML string or re-render it. Both approaches complicate the flow and are error-prone.

Treat the CID as part of the **internal mail model**: the renderer receives the assigned ID and the template simply uses it; the mail composer uses the same ID to create the inline part.

## 6. Spring Boot + Thymeleaf + MimeMessageHelper example

This example sends an HTML notification email with an inline logo. The CID is generated once in the service and passed to both the template and the helper.

### 6.1. Resource layout

```text
src/main/resources/
├── templates/
│   └── mail/
│       └── notification.html
└── mail/
    └── logo.png
```

`notification.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<body>
  <header>
    <img th:src="'cid:' + ${logoCid}"
         alt="Company logo"
         width="120"
         height="40"/>
  </header>

  <h1 th:text="${title}">Notification</h1>
  <p>Hello <span th:text="${customerName}">Customer</span>.</p>
  <p th:text="${message}">Notification message.</p>
</body>
</html>
```

Thymeleaf receives `logoCid` as a data value. The `th:src` expression constructs the CID URL from the fixed `cid:` prefix and the backend-supplied value. Text fields use `th:text` to HTML-escape the data.

### 6.2. SMTP configuration

Example `application.yml` with an SMTP submission server supporting STARTTLS:

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
```

The placeholders are supplied from environment variables or a secure configuration source. Port 587/STARTTLS is only an example; host, TLS, and authentication method must match your actual SMTP provider.

### 6.3. Service that generates one CID and reuses it

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.fromAddress = fromAddress;
    }

    public void sendNotification(
            String recipient,
            String customerName,
            String title,
            String body
    ) throws MessagingException {

        // Generate the CID once for this message's inline image.
        String logoCid = "logo-" + UUID.randomUUID()
                + "@mail.example.org";

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("logoCid", logoCid);
        context.setVariable("customerName", customerName);
        context.setVariable("title", title);
        context.setVariable("message", body);

        String html = templateEngine.process(
                "mail/notification",
                context
        );

        String plain = "Hello " + customerName + ".\n"
                + title + "\n"
                + body;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject(title);

        // Set the body first, then attach the inline resource.
        helper.setText(plain, html);
        helper.addInline(
                logoCid,
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        mailSender.send(message);
    }
}
```

In this example:

1. `logoCid` is generated once using a UUID and an application-controlled domain.
2. The same value is placed in `Context` before template rendering.
3. The generated HTML references `cid:` plus that value.
4. `helper.addInline(...)` receives that exact CID value, the resource, and the `image/png` media type.
5. The helper is created in `MULTIPART_MODE_RELATED` mode because the email has HTML and an inline image.
6. `setText(...)` is called before `addInline(...)`, following the recommended usage for inline resources.

`customerName`, `title`, and `body` in the example must be validated according to business rules. The template uses `th:text` to render them as text. The domain `mail.example.org` is illustrative only; in deployment, use a domain controlled by your organization.

## 7. Multiple inline resources in the same message

If an email has a logo, banner, and status icon, each resource needs its own CID:

```text
HTML:
  <img src="cid:logo-...@mail.example.org">
  <img src="cid:banner-...@mail.example.org">
  <img src="cid:status-...@mail.example.org">

MIME parts:
  Content-ID: <logo-...@mail.example.org>
  Content-ID: <banner-...@mail.example.org>
  Content-ID: <status-...@mail.example.org>
```

Java example:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
String bannerCid = "banner-" + UUID.randomUUID()
        + "@mail.example.org";
String statusCid = "status-" + UUID.randomUUID()
        + "@mail.example.org";

context.setVariable("logoCid", logoCid);
context.setVariable("bannerCid", bannerCid);
context.setVariable("statusCid", statusCid);

String html = templateEngine.process("mail/summary", context);

helper.setText(plainText, html);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addInline(
        bannerCid,
        new ClassPathResource("mail/banner.jpg"),
        "image/jpeg"
);
helper.addInline(
        statusCid,
        new ClassPathResource("mail/status-check.png"),
        "image/png"
);
```

Each CID is generated independently. Never share one ID across three different images.

### One resource referenced multiple times

If the logo appears in both the header and footer, both HTML tags can use the same CID:

```html
<header>
  <img src="cid:logo-123@mail.example.org" alt="Logo"/>
</header>

<footer>
  <img src="cid:logo-123@mail.example.org" alt="Logo"/>
</footer>
```

Only one MIME part with the matching Content-ID is needed. This avoids creating unnecessary duplicate content parts.

Rules:

- **Same resource, multiple display locations:** use the same CID.
- **Different resources:** use separate CIDs.
- **Each new message:** generate a fresh set of CIDs according to the chosen uniqueness scope.

## 8. Organizing CIDs into a mail model

When a template has many inline images, avoid scattering UUID generation across multiple methods. You can create a model representing the inline resources:

```java
import java.util.UUID;

public record InlineContentIds(
        String logo,
        String banner,
        String status
) {
    public static InlineContentIds create() {
        return new InlineContentIds(
                createId("logo"),
                createId("banner"),
                createId("status")
        );
    }

    private static String createId(String name) {
        return name + "-" + UUID.randomUUID()
                + "@mail.example.org";
    }
}
```

When building the message:

```java
InlineContentIds ids = InlineContentIds.create();

context.setVariable("logoCid", ids.logo());
context.setVariable("bannerCid", ids.banner());
context.setVariable("statusCid", ids.status());

String html = templateEngine.process("mail/summary", context);
helper.setText(plainText, html);

helper.addInline(
        ids.logo(),
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addInline(
        ids.banner(),
        new ClassPathResource("mail/banner.jpg"),
        "image/jpeg"
);
helper.addInline(
        ids.status(),
        new ClassPathResource("mail/status-check.png"),
        "image/png"
);
```

`InlineContentIds` serves as the central place managing IDs. When adding a new image to the template, this model is extended alongside the resource-attachment code. This prevents the template from referencing a CID while the composer forgets to add the corresponding part.

### Should you use a Map?

A Map can be used when the number of resources varies by template:

```java
Map<String, String> contentIds = new LinkedHashMap<>();
contentIds.put(
        "logo",
        "logo-" + UUID.randomUUID() + "@mail.example.org"
);
contentIds.put(
        "banner",
        "banner-" + UUID.randomUUID() + "@mail.example.org"
);
```

However, the Map should be built in a single layer and passed verbatim to both renderer and composer. Never let the template infer CIDs from filenames while Java code applies a different rule.

## 9. Generating deterministic CIDs to support retry and replay

Generating a random UUID per message is simple and suitable for most emails. However, some systems want to **re-render the same notification with the same CID**, for example to compare outputs or reconstruct a message from a stored event.

In that case, you can build a deterministic CID from:

- A unique `notificationId` issued by the backend.
- A stable resource key such as `logo`, `banner`, or `invoice-stamp`.
- An application-controlled domain.

Example:

```java
String logoCid = "logo-" + notificationId
        + "@mail.example.org";
```

Conditions for this approach to be safe:

1. `notificationId` has sufficiently strong uniqueness across all issued messages.
2. One notification may have multiple resources, so each resource has a distinct key.
3. Never reuse a notification ID for two independent messages if you want global Content-ID uniqueness.
4. Never use personal information or secret tokens as CID components.
5. IDs are constructed from format-constrained data containing no control characters.

If the notification ID is a UUID, the result might be:

```text
logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org
banner-550e8400-e29b-41d4-a716-446655440000@mail.example.org
```

The two resources have different IDs because their key parts differ. If the notification is retried with the same ID, the CID is reproduced identically.

### Random UUID or deterministic ID?

| Requirement | Suitable approach |
| --- | --- |
| Every send is a new message, no need to reproduce CIDs | Random UUID once per message |
| Retries must reconstruct the same MIME structure with stable CIDs | Unique notification ID + resource key |
| Multiple HTML locations reference the same image | Share the image's CID within the message |
| Multiple distinct images in the same message | One CID per image |
| Wanting one fixed CID across all emails | Does not satisfy global uniqueness requirements |

Note: stable CIDs do not make email sending idempotent. Preventing duplicate sends requires notification state/idempotency keys and retry policies at the business layer. Content-ID only identifies a MIME part.

## 10. Generating CIDs independently of filenames

Filenames and Content-IDs serve different purposes:

```text
Filename:
  logo-company.png

Content-ID:
  logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org
```

A filename helps identify a resource or supply a display name. Content-ID is the linking key between HTML and the MIME part. They do not have to be the same.

Example:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";

helper.addInline(
        logoCid,
        new ClassPathResource("mail/brand-mark.png"),
        "image/png"
);
```

In HTML, reference `cid:` plus `logoCid`. The physical filename `brand-mark.png` does not need to appear in the CID.

### Do not use filenames as CIDs

Avoid:

```java
String contentId = file.getName();
helper.addInline(contentId, file);
```

Two emails or two resources can share the name `logo.png`; filenames can also contain spaces, Unicode, or characters needing escaping. Using a filename as the CID increases collision risk and conflates two separate concepts.

## 11. Verifying consistency between HTML and MIME parts

A message valid with respect to CID linking must satisfy:

1. Every CID referenced in the HTML has a matching MIME part.
2. Each referenced MIME part has a Content-ID matching the CID URI after applying URI rules.
3. Each distinct resource has its own Content-ID.
4. The resource has the right `Content-Type`, such as `image/png` or `image/jpeg`.
5. The part is placed in an appropriate related MIME structure, typically `multipart/related`.
6. The source bytes remain readable throughout message serialization.

Example message with two images:

```text
HTML references:
  cid:logo-a1@mail.example.org
  cid:banner-b2@mail.example.org

Inline MIME parts:
  Content-ID: <logo-a1@mail.example.org>
  Content-Type: image/png

  Content-ID: <banner-b2@mail.example.org>
  Content-Type: image/jpeg
```

Example error:

```text
HTML:
  <img src="cid:logo-a1@mail.example.org">

MIME:
  Content-ID: <logo-b2@mail.example.org>
```

HTML looks for `logo-a1`, but the message only has part `logo-b2`. The mail client cannot resolve the image from that reference.

### Referencing a nonexistent CID

If a template contains:

```html
<img src="cid:bannerCid" alt="Banner"/>
```

but the composer does not call `addInline` for that CID, the image will be missing. To reduce errors, manage the inline resource list with a shared model and build the template context from that same model.

### MIME part exists but is not referenced by HTML

The reverse can also happen: the composer adds a logo, but the template never uses the CID. The part remains in the message, increasing size without any visual effect. Keep the resource list aligned with what the template needs and avoid adding unused images.

## 12. Call order in MimeMessageHelper

When using inline resources, the common order recommended by Spring is:

1. Create `MimeMessage`.
2. Create `MimeMessageHelper` in the appropriate multipart mode.
3. Set From, To, and Subject.
4. Render or prepare the HTML content.
5. Call `setText(...)` to set the body.
6. Call `addInline(...)` for each resource.
7. Call `JavaMailSender.send(...)`.

Example:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setFrom(fromAddress);
helper.setTo(recipient);
helper.setSubject(subject);

String logoCid = createLogoCid();
context.setVariable("logoCid", logoCid);
String html = templateEngine.process("mail/notification", context);

helper.setText(plainText, html);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
```

Calling `setText` sets the body so the helper can construct the related structure; `addInline` then adds the parts referenced by the body. If inline resources are added first and `setText` is called afterward, some multipart structures may be reorganized and cause images not to render as expected.

**Do not manually modify boundaries or top-level Content-Type** after the helper creates the structure. Boundaries and part headers are managed by Jakarta Mail.

## 13. Emails with both inline resources and attachments

An email can contain:

- An HTML body.
- An inline logo referenced by CID.
- A PDF attachment for the recipient to download.

Diagram:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── text/html; charset=UTF-8
    │   │     └── <img src="cid:logo-...">
    │   └── image/png
    │         └── Content-ID: <logo-...>
    └── application/pdf
          └── Content-Disposition: attachment
```

Example:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
context.setVariable("logoCid", logoCid);

String html = templateEngine.process("mail/invoice", context);

helper.setFrom(fromAddress);
helper.setTo(recipient);
helper.setSubject("Your invoice");
helper.setText(
        "Your invoice is attached to this email.",
        html
);

helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

mailSender.send(message);
```

Here:

- CID applies only to the inline logo.
- The PDF is added with `addAttachment`, needing no HTML CID.
- `MULTIPART_MODE_MIXED_RELATED` supports structures with related content and attachments.
- `setText(plain, html)` provides both plain-text and HTML versions.
- `logoCid` passes the exact same value to both the template and the helper.

## 14. Handling multiple renders and retries

An asynchronous email-sending system may render in a worker and retry when SMTP is temporarily unavailable. You must decide when CIDs are generated.

### Generating CIDs on each send attempt

If each retry creates a new `MimeMessage` and generates a new UUID, the HTML and MIME parts within that attempt still match. This is simple when CID is not used as a business identifier and raw messages do not need to be compared across attempts.

### Keeping CIDs per notification

If you need to reconstruct the same message, generate the CID from the notification ID and asset key. On retry, the same notification reproduces the same CID. Conditions:

- Notification IDs are never reused for different messages.
- Asset keys distinguish between resources.
- Template versions and inline resource lists are also kept consistent if exact replay is required.

### Do not share a mutable CID map across messages

Wrong example:

```java
// Avoid: a map shared across all sends and mutated.
private final Map<String, String> contentIds = new HashMap<>();
```

If two emails are built concurrently and mutate the map, one email's template could receive the other's CID or resources could be mapped incorrectly. Create a separate CID map per message or per render request.

### Do not use CID for deduplication

Two sends of the same notification having the same CID will not stop SMTP from accepting two messages. Conversely, two sends with different CIDs do not imply two distinct business operations. Use `notificationId`, send state, and application-layer idempotency policies to manage retries.

## 15. Common errors when generating Content-IDs

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Logo does not display | CID in HTML differs from MIME part Content-ID | Create one CID variable and reuse it in both places |
| One image displays in place of another | Two resources share the same Content-ID | Generate a separate CID per resource |
| Template references `cid:logo`, helper gets `logo.png` | Confusing CID with filename | Use a dedicated CID token, never the filename as CID |
| Header has double angle brackets | Passing `<...>` to `addInline` when helper wraps it | Pass the bare Content-ID |
| HTML contains `cid:cid:...` | Argument already has `cid:` prefix and template adds it again | Helper receives bare ID; HTML adds `cid:` once |
| Resource added but never referenced | Template uses a different CID or omits the image | Sync model/template/composer asset lists |
| CID is consistent in template but wrong in message | Template and helper generate IDs separately | Generate once in the mail composer |
| Image sent as a file attachment | Using `addAttachment` instead of `addInline` | Use `addInline` and related structure |
| Fixed CID repeats across emails | Using an app-wide constant for all messages | Use UUID or a unique notification ID |
| Image fails to show in some clients | Differences in MIME mode, CID, or client support | Check raw MIME and test target clients |
| Email grows unnecessarily large | Adding the same image as multiple MIME parts | Reuse one CID for the same resource |
| Resource unreadable at send time | One-shot stream source or deleted file | Use a re-readable Resource and preserve source lifecycle |
| External image link blocked | Client blocks loading external images | Use inline resource where appropriate, or accept client image policy |

### Mistake 1: generating the CID twice

```java
context.setVariable(
        "logoCid",
        "logo-" + UUID.randomUUID() + "@mail.example.org"
);

String html = templateEngine.process("mail/notification", context);

// Wrong: generating a different UUID for the MIME part.
String mimeCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";

helper.setText(html, true);
helper.addInline(
        mimeCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

Two different UUIDs prevent HTML from finding the MIME part. Create a single `logoCid` variable and pass it to both the context and `addInline`.

### Mistake 2: using the same CID for multiple images

```java
helper.addInline(
        "image@mail.example.org",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addInline(
        "image@mail.example.org",
        new ClassPathResource("mail/banner.jpg"),
        "image/jpeg"
);
```

Two MIME parts contend for the same identifier. Assign separate `logo-...` and `banner-...` IDs.

### Mistake 3: passing `cid:` into the helper

```java
// Wrong way to pass:
helper.addInline(
        "cid:logo-123@mail.example.org",
        resource,
        "image/png"
);
```

The helper expects the Content-ID, while `cid:` is the HTML scheme. Fix:

```java
String logoCid = "logo-123@mail.example.org";
helper.addInline(logoCid, resource, "image/png");

// HTML:
String src = "cid:" + logoCid;
```

### Mistake 4: using a filename as the CID

```java
helper.addInline("logo.png", resource, "image/png");
```

String-wise, some libraries/clients may handle this value, but it does not establish a sound uniqueness convention. Filenames can repeat or change. Use an independent, namespaced ID.

### Mistake 5: calling `addInline` before `setText`

If the helper must restructure the multipart hierarchy when setting the body later, the inline part may no longer sit where the HTML reference expects. Under standard usage, set text/HTML first, then add inline resources.

## 16. Inspecting raw MIME when images do not display

When an email arrives in a mailbox but the logo is missing, view **Show original / View source** or the receiving system's raw message viewer.

An expected structure:

```text
Content-Type: multipart/related; boundary="rel-123"

--rel-123
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <img src="cid:logo-123@mail.example.org" alt="Logo">
  </body>
</html>

--rel-123
Content-Type: image/png
Content-ID: <logo-123@mail.example.org>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0KGgo...

--rel-123--
```

The base64 string above is only an illustrative leading snippet, not a complete image.

Inspection steps:

1. Check whether the top-level MIME structure has the appropriate related part.
2. Locate the HTML part and read the `src="cid:..."` value.
3. Find the MIME part with the matching `Content-ID`.
4. Verify the image's `Content-Type` matches its actual format.
5. Check `Content-Disposition` and transfer encoding bytes.
6. If CIDs match yet the image still fails to show, inspect resource bytes, MIME nesting, and mail client behavior.

Do not inspect only the outermost headers. If the message is `multipart/mixed`, the related section may sit inside a nested MIME child part.

### Checking in code before sending

You can structure data so templates cannot be built without resource IDs:

```java
public record InlineAsset(
        String contentId,
        Resource resource,
        String contentType
) {}
```

An `InlineAsset` keeps three pieces together: ID, byte source, and media type. The renderer takes `contentId` from the asset list to populate the context; the composer uses that same list to call `addInline`. This reduces the risk of configuring templates and MIME parts independently.

## 17. Content-ID and privacy

Content-IDs typically appear in raw MIME and can be seen when recipients view the message source. Therefore:

- Do not use email addresses or usernames as CIDs unnecessarily.
- Do not embed access tokens, reset tokens, or personal data in CIDs.
- Do not treat CIDs as a security or access-control mechanism.
- Use a random identifier or non-sensitive technical code.
- Avoid putting internal details such as filesystem paths or bucket names in CIDs.

A CID is merely a way to identify a MIME part. Recipients do not need to know which database notification an ID maps to.

### CID is not an image-protection URL

Inline images are carried inside the message. Recipients do not need to call a public endpoint to load CID images. However, if an email also includes external images via HTTPS URLs, those images may be fetched by the mail client from a server and generate requests carrying access-time information. The two mechanisms have distinct traits:

| Mechanism | Where is the image data? | When is it fetched? |
| --- | --- | --- |
| CID inline | Inside the MIME message | Already delivered with the email |
| HTTPS URL | On a web server/CDN | When the mail client loads the URL; may be blocked/proxied/cached |

Choose the mechanism based on size, user experience, privacy, and compatibility. Content-ID does not encrypt or protect image content from the email recipient.

## 18. Mail client compatibility

CID inline is supported by many mail clients, though rendering still depends on:

- The `multipart/related` structure and position of the HTML part.
- Whether the Content-ID in HTML matches the MIME header.
- Whether `Content-Type` and image bytes match a valid format.
- Image dimensions and how the client handles inline images.
- Client content-filtering rules and security policies.
- HTML email CSS/layout.

Do not design emails where an inline image is the sole source of critical information. Always include meaningful `alt` text and put main content in text. Example:

```html
<img src="cid:logo-123@mail.example.org"
     alt="Company name"
     width="120"
     height="40"/>
```

If the logo fails to render, readers can still understand the message from `alt` and the surrounding text.

### Can you use the same image as both CID and attachment?

You can create two MIME parts or organize content by separate purposes, though it is rarely necessary. If the same resource must appear in the body and be separately downloadable, consider whether a single inline part suffices for client UX. Never assume `addInline` automatically creates an additional standalone attachment.

If file download is a hard requirement, add a clearly named attachment via `addAttachment` while keeping the inline part for display. This can increase message size because the data is duplicated.

## 19. Design rules for Content-ID

| Rule | Implementation |
| --- | --- |
| ID generation | Generate once in the mail composer for each inline resource |
| Scope | Globally unique per Content-ID rules; use UUID or a unique notification ID |
| Same resource, multiple places | Use the same CID across all HTML references |
| Different resources | Assign separate CIDs |
| `addInline` argument | Pass bare ID, no `cid:` and no angle brackets |
| HTML reference | Use `src="cid:" + contentId` |
| Media type | Specify explicitly when format is known, e.g., `image/png` |
| MIME mode | Choose `MULTIPART_MODE_RELATED` or `MULTIPART_MODE_MIXED_RELATED` appropriately |
| Order | Set body with `setText` before calling `addInline` |
| CID characters | Use only simple backend-generated characters |
| Retry/replay | Choose per-attempt UUID or deterministic notification-based ID as required |
| Security | Never embed tokens, PII, or secrets in Content-ID |
| Verification | Cross-check HTML CID URIs against each MIME part's Content-ID |

## 20. Practice scenarios

### Scenario A: the same logo appears in header and footer

The template has two `<img>` tags using the same logo image.

**Approach:** generate one `logoCid`, use it for both `src="cid:..."` attributes, and add only one MIME part via `addInline(logoCid, ...)`.

### Scenario B: email has a distinct logo and banner

**Approach:** generate separate `logoCid` and `bannerCid`; put both into the context; call `addInline` twice with the matching CIDs.

### Scenario C: logo does not display even though `addInline` ran

**Approach:** inspect raw MIME and compare `src` in HTML against the part's `Content-ID`. If they match, check MIME nesting, media type, and resource bytes.

### Scenario D: retrying the same notification

The system wants to replay the exact same model and template.

**Approach:** if deterministic CIDs are needed, derive the ID from the unique notification ID and resource key. Keep template version, asset mapping, and required data per retention policy. This does not replace email-sending idempotency.

### Scenario E: two concurrent emails share the same template

**Approach:** the template can be shared, but the CID map and context must be per-message. Never store active CIDs in a shared mutable singleton variable.

### Scenario F: template has a hardcoded `cid:logo`

**Approach:** for a single message in isolation, it can link; however, using the same constant across every message does not satisfy global uniqueness. Generate per-message CIDs and pass them into the template.

## 21. Conclusion

Content-ID is the bridge between a `cid:` slot in HTML and the MIME part containing the inline resource. For images to render properly, **the value must be generated once and used consistently in both the template and `MimeMessageHelper.addInline(...)`**. Each distinct resource needs its own ID; the same image referenced multiple times can share one ID. Generate a fresh CID per message using a UUID or a unique notification ID combined with an asset key, using an application-controlled domain.

In Spring Framework Mail, choose the right multipart mode, render the HTML with the CID passed into the context, call `setText(...)` before `addInline(...)`, and let Jakarta Mail generate headers and boundaries. Inspecting raw MIME when images fail to display will pinpoint whether the fault lies in CID mapping, MIME structure, media type, or resource bytes.

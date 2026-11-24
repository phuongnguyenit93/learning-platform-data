# multipart/related for HTML and inline resources

In a **Spring Framework Mail** application, an HTML email can display text, tables, buttons, and images. However, if the HTML code contains `<img src="logo.png">`, the recipient's email program cannot automatically read the `logo.png` file from the application server. To send images **along with the message** and reference them directly inside HTML, you need the appropriate MIME structure: **`multipart/related`** and **Content-ID (CID)**.

This lesson explains how MIME organizes HTML content and inline resources, how `JavaMailSender` and `MimeMessageHelper` build the corresponding message, how to combine them with plain text or attachments, and why the same email may render differently across mail-reading applications.

## 1. What is MIME and why does HTML need multipart/related?

**MIME (Multipurpose Internet Mail Extensions)** extends the email format to carry multiple types of data: plain text, HTML, images, PDFs, and multiple content parts within one message. Those parts are described by headers such as `Content-Type`, `Content-ID`, `Content-Disposition`, and `Content-Transfer-Encoding`.

A simple text-only email usually uses:

```text
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hello, this is the email body.
```

A simple HTML email can use `text/html`. However, when HTML references **images attached inside the message itself** rather than fetched from a website, we need to tell the mail reader: “This HTML part and these images are related to each other; this image corresponds to that reference.”

`multipart/related` does exactly that:

- It is a **MIME container** holding multiple interrelated body parts.
- One part serves as the **root content** (usually HTML or a `multipart/alternative` containing HTML).
- Other parts hold **related resources**, such as a PNG logo, JPEG photo, or illustration referenced by HTML via `cid:...`.
- The email application can combine the parts to render a single piece of content.

**Do not equate “inline” with “attaching an attachment”.** An inline resource is a part serving presentation within the body; an ordinary attachment is opened or downloaded separately by the user. Both are MIME parts, yet they usually belong in different containers.

## 2. Distinguishing related, alternative, and mixed

Three `multipart` subtypes very often appear together:

| MIME subtype | Meaning | Typical case |
|---|---|---|
| `multipart/alternative` | Multiple versions of **the same content**, ordered from simpler to richer formatting | The same message has `text/plain` and `text/html`. |
| `multipart/related` | One primary content along with **dependent resources** to display that content | HTML references a logo via `cid:brand-logo`. |
| `multipart/mixed` | Multiple independent components bundled into one message | Email body and an attached PDF invoice file. |

Example structure with only HTML and an inline logo:

```text
multipart/related
├── text/html                     (root content)
│   └── <img src="cid:brand-logo">
└── image/png                     (inline resource)
    └── Content-ID: <brand-logo>
```

If you want both a **plain text version** as fallback and an **HTML version** for rich display:

```text
multipart/related
├── multipart/alternative          (root content)
│   ├── text/plain
│   └── text/html                  (references cid:brand-logo)
└── image/png                      (Content-ID: <brand-logo>)
```

If the email also has a PDF to download:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html              (references cid:brand-logo)
│   └── image/png                  (inline logo)
└── application/pdf                (invoice attachment)
```

This nesting helps the email application distinguish **the logo belonging to the HTML content** from **the PDF as an attachment**.

> `multipart/related` solves the relationship between HTML and resources; `multipart/alternative` solves multiple ways to present the same content; `multipart/mixed` solves packaging independent parts. They do not replace one another and can be nested.

## 3. Content-ID and cid: syntax linking HTML to images

At the core of an HTML email with inline images is the pair **`Content-ID` in the MIME part** and **`cid:...` in HTML**.

In HTML:

```html
<img src="cid:brand-logo" alt="Brand logo" width="160">
```

In the MIME part containing the image:

```text
Content-Type: image/png
Content-ID: <brand-logo>
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

[base64-encoded PNG data]
```

The mail-reading program sees `src="cid:brand-logo"`, looks up the part with `Content-ID: <brand-logo>`, and uses that part's image data to render.

Points to remember:

1. **Matching identifier:** `cid:brand-logo` must reference `Content-ID: <brand-logo>` accurately. The part inside angle brackets of the header corresponds to the value after `cid:`.
2. **No angle brackets in HTML:** write `src="cid:brand-logo"`, not `src="cid:<brand-logo>"`.
3. **Content-ID differs from Message-ID:** `Message-ID` identifies the entire email; `Content-ID` identifies a single MIME part.
4. **Content-ID differs from filename:** the name `logo.png` is merely descriptive of the file and cannot replace CID when HTML needs to locate the exact image.
5. **Each resource uses a separate CID:** avoid reusing the same CID for different images in the same message. When manually constructing MIME, use a unique identifier valid per message-id syntax; `MimeMessageHelper` supports setting CIDs via `addInline(...)`.
6. **CID can be used in various URL attributes** in HTML if supported by the mail client, though `<img src="cid:...">` is the most common case. Support for CSS backgrounds, SVG, and other advanced techniques varies unevenly.

The `Content-Disposition: inline` header suggests to the mail client that the content should be displayed alongside the body. **It does not create a link from HTML to the image** if a matching CID is missing. Conversely, some email clients still display inline resources in the attachment list; this is a client UI difference, not necessarily a MIME error.

### Inline differs from images loaded via URL

Two examples look similar in the UI yet operate by different mechanisms:

```html
<!-- Image is inside the message, referenced by Content-ID -->
<img src="cid:brand-logo" alt="Logo">

<!-- Image is loaded from an external HTTP/HTTPS address -->
<img src="https://cdn.example.com/mail/logo.png" alt="Logo">
```

| Criterion | CID inline | External URL |
|---|---|---|
| Image data | Packaged inside the email as a MIME part. | Mail client may have to fetch from an external server. |
| Network dependence when recipient opens mail | Can be displayed from received message data; still subject to client policy. | Requires URL access and depends on remote image loading capability/policy. |
| Email size | Increases because the image is sent with the message and usually encoded for transport. | Email payload may be smaller, but requires reliable image hosting. |
| Rendering reliability | Depends on how the mail client handles `multipart/related` and CID. | Depends on external image blocking policy, proxies, tracking protection, and network connectivity. |
| URL in HTML | `cid:brand-logo` | `https://...` |

Data URIs such as `src="data:image/png;base64,..."` are yet another mechanism; many email clients impose limits or lack solid support. For images that must be sent along with the message, CID inside `multipart/related` is generally the clearer approach.

## 4. Raw MIME of an HTML email with an inline logo

Look at the following illustrative structure. Boundary strings and Base64 content are shortened for readability, **not** a message designed to be sent directly:

```text
From: no-reply@example.com
To: user@example.net
Subject: Welcome
MIME-Version: 1.0
Content-Type: multipart/related;
 boundary="rel-001";
 type="multipart/alternative"

--rel-001
Content-Type: multipart/alternative; boundary="alt-001"

--alt-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Welcome to the application.

--alt-001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html>
  <body>
    <h1>Welcome!</h1>
    <img src="cid:brand-logo" alt="Logo">
  </body>
</html>

--alt-001--

--rel-001
Content-Type: image/png; name="logo.png"
Content-ID: <brand-logo>
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

[encoded PNG data, abbreviated]

--rel-001--
```

Reading from outside to inside:

- The `Content-Type: multipart/related` header declares that the message consists of related parts.
- Boundary `rel-001` separates the **root content** and the **inline image**.
- The root content is `multipart/alternative`, containing text/plain first and text/html second. The client can pick whichever version it supports.
- HTML contains `cid:brand-logo`; the PNG image in the other part has the header `Content-ID: <brand-logo>`.
- `Content-Transfer-Encoding: base64` describes how the image's bytes are represented inside the message; this encoding **is not security encryption**.

Real MIME messages follow required newline, boundary, encoding, and header syntax. In a Spring application, let Jakarta Mail generate those details rather than concatenating MIME strings after an illustrative template.

## 5. Building multipart/related with Spring Framework Mail

In Spring, the primary tools are:

- `JavaMailSender` creates and sends `MimeMessage`;
- `MimeMessageHelper` helps set sender/recipient info, HTML content, alternative text, inline resources, and attachments;
- `ClassPathResource`, `FileSystemResource`, or `ByteArrayResource` provides file/image data to the helper.

With Spring Boot, add the mail starter (e.g., Gradle Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

An illustrative SMTP configuration for a submission server using STARTTLS:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Provide `SMTP_USERNAME` and `SMTP_PASSWORD` via environment variables or a secret store; never commit real credentials to a repository. If using Spring Framework without Boot, configure `JavaMailSenderImpl`, SMTP properties, and the appropriate Jakarta Mail dependency yourself.

### 5.1. Preparing images in resources

Place the logo on the application's classpath:

```text
src/
  main/
    java/
      com/example/mail/WelcomeMailService.java
    resources/
      mail/
        logo.png
      application.yml
```

When packaged as a JAR, `src/main/resources/mail/logo.png` can usually be read with:

```java
new ClassPathResource("mail/logo.png")
```

Do not use local machine paths like `C:\project\src\main\resources\...`. Classpath paths work more reliably when running in a JAR, container, or other deployment environments.

### 5.2. Sending HTML + plain text + inline logo

Example using Spring Boot 3.x / Spring Framework 6.x with `jakarta.mail.*` imports:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "brand-logo";

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        // Explicitly choose related structure: HTML part and inline image are linked.
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String plainText =
            "Welcome to the application!\n"
            + "We are glad to have you join us.";

        String htmlText = """
            <!DOCTYPE html>
            <html lang="en">
              <body>
                <img src="cid:brand-logo"
                     alt="Brand logo"
                     width="160"
                     style="display:block;border:0">
                <h1>Welcome!</h1>
                <p>We are glad to have you join us.</p>
              </body>
            </html>
            """;

        // Set the content BEFORE adding inline resources.
        helper.setText(plainText, htmlText);

        // Content-ID of the image part will correspond to cid:brand-logo.
        helper.addInline(
            LOGO_CID,
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        mailSender.send(message);
    }
}
```

Analyzing the key lines:

1. `createMimeMessage()` creates an email object capable of holding MIME multipart, unlike `SimpleMailMessage` which is only for simple text messages.
2. `MULTIPART_MODE_RELATED` tells the helper to build a `multipart/related` MIME container.
3. `helper.setText(plainText, htmlText)` builds plain text and HTML content versions for the client to choose from. The HTML version contains `cid:brand-logo`.
4. `helper.addInline("brand-logo", ..., "image/png")` adds a MIME part with the matching Content-ID. Spring/Jakarta Mail handles reading the resource and representing the image content.
5. `mailSender.send(message)` sends the message over configured SMTP; a successful call does not mean the message has arrived in the Inbox.

**Order is critical:** per `MimeMessageHelper` usage, call `setText(...)` **before** `addInline(...)`. This helps produce the proper MIME part structure and avoids cases where some mail clients fail to resolve inline images.

### 5.3. Why use text/plain and text/html together?

Not every mail client renders HTML the same way. In some cases emails are read in plain text mode, forwarded through text-only systems, or served to assistive technologies. With:

```java
helper.setText(
    "Hello, thank you for registering.",
    "<p>Hello, <strong>thank you for registering.</strong></p>"
);
```

Spring creates two versions belonging to `multipart/alternative`. This is **the same content expressed in two ways**, not two emails. The plain text version should preserve full business information; do not just write “Please view the HTML version”.

If only HTML is needed, you can call `helper.setText(htmlText, true)`; when using inline CIDs, you still need a `multipart/related` container and must call `addInline(...)` after setting text.

## 6. When to use MULTIPART_MODE_RELATED vs. MIXED_RELATED?

`MimeMessageHelper` offers multiple multipart modes. When working with HTML and inline assets, two modes are most important to understand clearly:

| Helper mode | Primary structure | When to use |
|---|---|---|
| `MULTIPART_MODE_RELATED` | `multipart/related` on the main content | Email only has HTML/plain text and related inline resources. |
| `MULTIPART_MODE_MIXED_RELATED` | Outermost `multipart/mixed`, inner `multipart/related` | Email has HTML + inline assets **and** independent attachments, such as a PDF. |

In Spring, constructors using `multipart=true` usually select the combined `MULTIPART_MODE_MIXED_RELATED`. Choosing the specific mode constant in examples helps readers understand the intended MIME structure.

### 6.1. Example with inline logo and attached PDF invoice

Suppose the application has already produced a `pdfBytes` byte array from invoice generation:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class InvoiceMailSender {
    private final JavaMailSender mailSender;

    public InvoiceMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");
        helper.setText(
            "Your invoice is attached as a PDF.",
            """
            <html><body>
              <img src="cid:invoice-logo" alt="Logo" width="120">
              <p>Your invoice is attached as a PDF.</p>
            </body></html>
            """
        );

        helper.addInline(
            "invoice-logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Here, **the logo** sits inside the `related` group alongside HTML, while **the PDF** is an attachment of `mixed`. `ByteArrayResource` creates a fresh input stream from the byte array whenever reading is required; this is helpful because the mail library may need to read the resource data multiple times while preparing and sending the message.

Do not wrap an already-exhausted single `InputStream` into a single-read data source. If the image/file is retrieved from an external service or memory, provide an `InputStreamSource` capable of opening a new stream on each call or store the content in a `ByteArrayResource` when size permits.

### 6.2. Multiple inline images can be sent

Simply give each image a distinct CID and reference it accurately in HTML:

```html
<img src="cid:header-logo" alt="Logo" width="120">
<p>Your new notification</p>
<img src="cid:notice-banner" alt="Notification illustration" width="480">
```

```java
helper.setText(plainText, htmlText);
helper.addInline(
    "header-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
helper.addInline(
    "notice-banner",
    new ClassPathResource("mail/banner.jpg"),
    "image/jpeg"
);
```

Set the Content-Type accurately to match the real image data; do not label a JPEG file as `image/png` just to reuse the same configuration snippet.

## 7. How to choose the inline resource source

`MimeMessageHelper.addInline(...)` has several overloads. Choosing the right data source keeps email behavior reliable both in development and when packaged.

| Source | Example | Notes |
|---|---|---|
| `ClassPathResource` | `new ClassPathResource("mail/logo.png")` | Suitable for logos or static images packaged inside the application. |
| `FileSystemResource` | `new FileSystemResource(path)` | Suitable for files on disk or volumes; control path/read permissions and avoid hardcoded local paths. |
| `ByteArrayResource` | `new ByteArrayResource(imageBytes)` | Suitable for images generated or downloaded into a byte array; avoid holding overly large images in RAM. |
| Custom `InputStreamSource` | Source able to open a new stream per read | Must ensure each `getInputStream()` call returns a fresh, independent stream. |

Example creating a logo from existing byte data:

```java
byte[] imageBytes = loadGeneratedPng(); // Illustrative business method
helper.addInline(
    "generated-chart",
    new ByteArrayResource(imageBytes),
    "image/png"
);
```

In the corresponding HTML:

```html
<img src="cid:generated-chart" alt="Summary chart">
```

The `loadGeneratedPng()` method in this example represents where the image is generated, not a built-in Spring API. Regardless of source, the content must be valid image data of an appropriate size for email.

## 8. Common errors and how to identify them

### 8.1. Logo turns into a broken image icon

Common causes:

- HTML references `cid:company-logo` while `addInline("brand-logo", ...)` was called.
- HTML uses a local file path such as `src="./logo.png"`, or a path `/static/logo.png` that only makes sense on a web server.
- The `mail/logo.png` resource does not exist on the classpath at runtime.
- The MIME part has invalid data format, wrong `Content-Type`, or the client does not support that image format.
- Improper MIME part creation order: adding inline before setting content with `setText(...)`.
- A specific email client does not render the used structure as expected.

To separate content bugs from structural bugs, inspect the **MIME source** of the received email: is there an actual image part, what is its `Content-ID`, does `src="cid:..."` match, and is the image inside `multipart/related` alongside HTML?

### 8.2. Image is displayed as an attachment

Some mail clients show an attachment icon even when an image is already rendered inline. Distinguish between:

- **Does not appear in HTML and shows up as an attachment:** check CID, `related` container, image subtype, and multipart structure.
- **Displays properly in HTML yet still shows an attachment icon:** this may simply be how the email software presents MIME parts; there is no way to guarantee every client hides that icon completely.

`Content-Disposition: inline` is a handling hint, not a mandate forcing every email application to render identically.

### 8.3. Only text appears without HTML, or both appear together

With `multipart/alternative`, the mail reader is expected to pick the appropriate version. If the MIME structure is nested incorrectly or a client lacks good support, it may display an unintended version.

Check the order of parts—`text/plain` before `text/html` inside the `alternative` container—then verify whether that container sits inside `related` as intended. Avoid building nested multiparts via string concatenation, as boundaries and headers easily break.

### 8.4. Image works on a web page yet fails to render in email

Web browsers and email clients follow different rule sets. Many clients strip JavaScript, restrict CSS, block remote resource loading, or enforce special policies for SVG, animated images, background images, and uncommon formats. CID does not guarantee all clients support every HTML/CSS feature.

For important transactional emails, prefer simple HTML, common PNG/JPEG images, sensible explicit dimensions, meaningful `alt` text, and provide a text version.

### 8.5. Errors accessing resources or sending MIME

Some problems are unrelated to SMTP:

- `MessagingException` can occur while building/modifying MIME.
- Spring's `MailException` can be thrown when `mailSender.send(...)` hits a sending failure.
- Image data source cannot be opened or was already consumed, causing part creation/sending to fail.
- Oversized images or attachments cause the message to exceed provider limits or exhaust memory.

Distinguish **MIME preparation errors**, **SMTP connection/authentication errors**, and **downstream delivery errors**; they occur at different layers and require different handling.

## 9. Size, security, and accessibility

### 9.1. Do not embed overly large resources

Images in emails are usually represented in Base64, making transmitted data larger than the original binary data (typically increasing by around one-third, excluding headers and line breaks). Embedding too many high-resolution images can cause messages to:

- be rejected by servers for exceeding size limits;
- load/forward slowly or get clipped by some mail-reading applications;
- incur high bandwidth and storage costs;
- be hard to read on mobile devices.

Optimize resolution, compress images appropriately, and embed only genuinely necessary resources. For large files meant for downloading, consider attachments or secure links per business requirements.

### 9.2. CID is not a security mechanism

`multipart/related` only packages content. It **does not provide end-to-end encryption** and does not authenticate the sender by itself. TLS for SMTP connections, sending permission controls, and domain configuration (SPF, DKIM, DMARC) are separate concerns.

Do not embed confidential information into images or HTML without proper justification for sharing it. If generating HTML content from user data, escape data properly or use a template engine with safe handling. Avoid fetching arbitrary HTML from untrusted sources and sending it verbatim.

### 9.3. Use alt text and plain text versions

Important information should not appear only inside images. For instance, verification codes, deadlines, or payment details must exist as text because images may be hidden or fail to render.

A decorative image:

```html
<img src="cid:decorative-line" alt="" width="480">
```

An informational image:

```html
<img src="cid:service-status"
     alt="Service is operating normally"
     width="240">
```

Even better, include the message “Service is operating normally” as real text right beside the image, so everyone can read it even if the image never loads.

## 10. Self-check workflow when sending HTML with inline assets

During development, you can send a test email to mail clients representing your user base and check:

1. **HTML content:** do headings, paragraphs, links, and images appear as intended?
2. **CID:** does the value after `cid:` in HTML match the image's `Content-ID`?
3. **Structure:** is the image inside `multipart/related` with the root content; if there is a PDF, is it in the appropriate `mixed` group?
4. **Part creation order:** was `setText(...)` called before `addInline(...)`?
5. **Alternative version:** when viewing plain text, is all primary information present?
6. **Accessibility:** do important images have appropriate `alt` text, and is the content still understandable when images are blocked?
7. **Size:** is the message size after MIME encoding within SMTP limits?

If a specific client renders an image improperly, inspect the **source of the actually received email** and compare against the expected structure rather than looking only at the initial HTML code. Only after confirming valid MIME should you investigate client-specific rendering differences.

## 11. Practice exercises

### Exercise 1: One HTML, two inline images

Requirement: create a welcome email with a logo at the top and a banner at the bottom. Both images are packaged inside the email.

Hint:

```html
<h2>Welcome new member</h2>
<img src="cid:welcome-logo" alt="Logo" width="120">
<p>Thank you for joining.</p>
<img src="cid:welcome-banner" alt="Welcome banner" width="480">
```

Call `helper.setText(plainText, htmlText)` and then add the two corresponding parts using `addInline("welcome-logo", ...)` and `addInline("welcome-banner", ...)`. Each part has the Content-Type matching its image.

### Exercise 2: Adding an invoice to a message with a logo

An email has HTML content referencing a logo and an `invoice.pdf` file for the recipient to download. Choose between `MULTIPART_MODE_RELATED` and `MULTIPART_MODE_MIXED_RELATED` and sketch the MIME tree.

**Suggested answer:** choose `MULTIPART_MODE_MIXED_RELATED`; the outer layer is `multipart/mixed`, the inner part is `multipart/related` (HTML and logo) alongside an independent `application/pdf` part.

### Exercise 3: Find the Content-ID bug

HTML:

```html
<img src="cid:brand-banner" alt="Banner">
```

Java:

```java
helper.setText(plainText, htmlText);
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/banner.png"),
    "image/png"
);
```

**Issue:** the CID in HTML is `brand-banner`, whereas the CID created via `addInline(...)` is `brand-logo`. Fix one side so the two identifiers match. The file name `banner.png` does not determine the CID link.

### Exercise 4: When the recipient cannot see the image

The email was sent, text shows up, yet the logo does not appear. Analyze step-by-step: whether the source file exists, whether the helper uses multipart, whether `setText` was placed before `addInline`, whether the MIME part has the right Content-ID, and whether the client has its own image-display policy.

This is an exercise in analyzing MIME structure and how clients consume resources; a successful SMTP send only confirms that the server accepted the message at a given step.

## 12. Review questions

**1. How does `multipart/related` differ from `multipart/alternative`?** Related links a primary content part with dependent resources; alternative provides multiple alternative versions of the same content, such as plain text and HTML.

**2. Why not use `src="/images/logo.png"` to display an inline logo?** That path usually only has meaning in the application's web environment or server; the email client has no information to open that file inside the message. You must send the resource and reference it by CID, or use a valid external URL if choosing network-loaded images.

**3. Which header links an image to `cid:logo`?** `Content-ID: <logo>` on the MIME part containing the image.

**4. Can `addAttachment(...)` replace `addInline(...)`?** No. An attachment is an independently attached part; `addInline` sets the Content-ID and appropriate structure for HTML to reference that content.

**5. When should `MULTIPART_MODE_MIXED_RELATED` be used?** When the email has both inline resources serving HTML and independent attachments such as a PDF.

**6. Why call `setText(...)` before `addInline(...)`?** So `MimeMessageHelper` constructs the primary content structure first, then adds related MIME parts in a way mail clients can resolve CIDs more reliably.

**7. Why include a `text/plain` version?** It enables recipients to access the content when HTML is not displayed or the recipient prefers plain text mode.

## 13. Summary

When an HTML email needs to use images embedded directly inside the message, use **`multipart/related`** to group HTML with inline resources, and use **`Content-ID` + `cid:...`** to link each image accurately. In Spring Framework Mail, `MimeMessageHelper` helps create this structure via `MULTIPART_MODE_RELATED`, `setText(...)`, and `addInline(...)`.

If the message also has a plain text version, additionally use `multipart/alternative`. If there are independent attachments, choose `MULTIPART_MODE_MIXED_RELATED` to separate related content from attachments. Even with valid MIME structure, rendering still depends on the mail client; therefore, important content should exist as text and images should have appropriate alternative descriptions.

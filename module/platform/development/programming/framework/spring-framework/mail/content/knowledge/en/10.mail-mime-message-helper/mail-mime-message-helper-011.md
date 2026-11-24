# Handling the order of addInline and setText

In **Spring Framework Mail**, `MimeMessageHelper` helps create HTML emails, insert images displayed right inside the content, and send attachments without assembling each MIME part manually. However, a common mistake is **calling `addInline(...)` before `setText(...)`**. The email may still be sent successfully, yet images referenced by `cid:...` fail to display in some mail-reading applications, or appear as attached files.

The most important practical rule is:

> **Create the message body with `helper.setText(...)` first; only then add all inline resources with `helper.addInline(...)`.**

This is also the order noted by the Spring API documentation because rebuilding the body structure can affect how some mail clients resolve related resources. This lesson explains why, how to use it properly with HTML emails or HTML with a plain-text version, how to add multiple images and attachments, and how to diagnose when images still do not display even after following the order.

## 1. The problem: an HTML email with a logo in the body

Suppose the system sends a welcome email:

```html
<!DOCTYPE html>
<html lang="en">
  <body>
    <img
      src="cid:company-logo"
      alt="Company logo"
      width="160"
    >
    <h1>Welcome!</h1>
    <p>Your account has been created successfully.</p>
  </body>
</html>
```

This HTML snippet does not contain image data directly. The value `cid:company-logo` means: **find a MIME part of the email whose `Content-ID` matches `company-logo`** and display that part's image data.

A MIME part containing the logo might carry headers like:

```text
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

[PNG image content encoded for transport]
```

Two components must match:

| Location | Value |
|---|---|
| HTML | `src="cid:company-logo"` |
| MIME header | `Content-ID: <company-logo>` |
| Java API | `helper.addInline("company-logo", resource, "image/png")` |

The string `company-logo` in `addInline(...)` is the **Content-ID**, not a filename, path, Java variable name, or the `Message-ID` of the entire message.

A `cid:...` reference differs from `src="https://cdn.example.com/logo.png"`. With an external URL, the mail client may need to fetch the image from a web server. With CID, the image is packaged **inside the email** and can be used by the mail client to render HTML, depending on its support and display policies.

## 2. setText(...) and addInline(...) do two different things

### 2.1. setText(...) creates the root content

`MimeMessageHelper` provides several ways to set content:

```java
// Plain text:
helper.setText("Hello!");

// HTML only:
helper.setText("<p>Hello!</p>", true);

// Same content in two versions:
helper.setText(
    "Hello! Please confirm your account.",
    "<p>Hello! <strong>Please confirm your account.</strong></p>"
);
```

Meaning:

- `setText(String)` sets plain-text content.
- `setText(String, boolean)` allows specifying the content is HTML when the second parameter is `true`.
- `setText(String plainText, String htmlText)` creates **two alternative versions** of the same content, usually inside `multipart/alternative`.

These operations can set up or update the root content section and the structure of MIME body parts. When combined with inline resources, the order in which parts are constructed therefore has practical significance.

### 2.2. addInline(...) adds related resources

Example:

```java
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

This call adds a part containing the image and attaches a `Content-ID` for HTML to reference. `MimeMessageHelper` and Jakarta Mail handle representing binary data as appropriate MIME content.

Several overloads of `addInline(...)` allow passing:

- `File` when the image sits on the filesystem;
- `Resource` or `InputStreamSource` when the image is read from the classpath, a byte array, or another data source;
- `contentType` when needing to specify the MIME type explicitly.

To embed content images into HTML, **both the HTML content and the inline part must exist and be linked by CID**. Calling `addInline(...)` alone does not make the image automatically appear on screen.

### 2.3. Why must setText be called first?

Picture `MimeMessageHelper` building a MIME tree. When calling `setText(...)`, the helper sets up the root content section, potentially creating `text/html`, `text/plain`, or a `multipart/alternative` group. When calling `addInline(...)`, the helper adds the related image part into the appropriate MIME group.

If you add the image first and **only afterward rebuild the body with `setText(...)`**, some mail-reading apps may have trouble determining which part is the root content, which are related resources, or how to resolve parts in the created structure.

Therefore, **Spring recommends calling `addInline(...)` after `setText(...)`**. Do not assume the wrong order always throws an exception or always drops the image part; issues usually manifest in **how mail clients display** the email after it has been sent.

## 3. Comparing wrong code and right code

### 3.1. Order not to use

```java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setTo("alice@example.net");
helper.setSubject("Welcome");

// Do not add inline before creating the HTML body:
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

String html = """
    <html><body>
      <img src="cid:company-logo" alt="Logo">
      <p>Hello!</p>
    </body></html>
    """;

helper.setText(html, true);
mailSender.send(mimeMessage);
```

The issue **does not lie in the SMTP call** or a wrong image ID (in the example above the two IDs match). The issue is the order of operations on the MIME body: the resource is added before the main body is finalized.

Such code might work on some clients yet display incorrectly on others. Do not use “it works on my machine” as proof that a MIME creation order is safe across all mail readers.

### 3.2. Recommended order

```java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("alice@example.net");
helper.setSubject("Welcome");

String html = """
    <html><body>
      <img src="cid:company-logo" alt="Logo">
      <p>Hello!</p>
    </body></html>
    """;

// 1. Set up the root content.
helper.setText(html, true);

// 2. Add resources referenced by the HTML content.
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

// 3. Send after finalizing the parts.
mailSender.send(mimeMessage);
```

The order should follow this flow:

```text
createMimeMessage()
       |
       v
new MimeMessageHelper(... multipart ...)
       |
       v
setFrom / setTo / setSubject / setReplyTo
       |
       v
Create or render HTML content
       |
       v
setText(plainText, htmlText)
or setText(htmlText, true)
       |
       v
addInline(cid1, resource1, type1)
       |
       v
addInline(cid2, resource2, type2)
       |
       v
addAttachment(...) if any
       |
       v
JavaMailSender.send(mimeMessage)
```

Basic headers such as `From`, `To`, `Subject` do not necessarily have to be set in a fixed order relative to one another. **The ordering relationship to remember is: `setText` before `addInline`; finalize MIME before sending.**

## 4. Complete Spring Boot example: HTML + plain text + inline image

The example below uses **Spring Boot 3.x, Spring Framework 6.x, and Java 17+**. With Spring Framework 6, email objects use the `jakarta.mail` namespace.

### 4.1. Dependency

If using Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

The starter provides `JavaMailSender` auto-configuration for typical SMTP cases when `spring.mail.*` is configured appropriately.

### 4.2. SMTP configuration

`application.yml` illustrating port 587 and STARTTLS:

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

The two variables `SMTP_USERNAME` and `SMTP_PASSWORD` are supplied from the environment/secret store; do not commit real credentials to the repository. Port and TLS mechanism must follow the SMTP provider's documentation.

### 4.3. Placing the logo in resources

Project structure:

```text
src/main/
├── java/com/example/mail/WelcomeMailService.java
└── resources/
    ├── application.yml
    └── mail/
        └── logo.png
```

`ClassPathResource("mail/logo.png")` is suitable when the logo is packaged inside the JAR. Do not use an absolute path to the source directory on a developer's machine.

### 4.4. Mail-sending service

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "company-logo";

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        // Multipart allows using inline images and text/html.
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String safeName = HtmlUtils.htmlEscape(displayName);

        String plainText =
            "Hello " + displayName
            + ",\nWelcome to the application.";

        String htmlText = """
            <!DOCTYPE html>
            <html lang="en">
              <body>
                <img src="cid:company-logo"
                     alt="Company logo"
                     width="160"
                     style="display:block;border:0">
                <h1>Hello, %s!</h1>
                <p>Welcome to the application.</p>
              </body>
            </html>
            """.formatted(safeName);

        // STEP 1: Create text/plain and text/html.
        helper.setText(plainText, htmlText);

        // STEP 2: Only add inline after setText.
        Resource logo = new ClassPathResource("mail/logo.png");
        helper.addInline(LOGO_CID, logo, "image/png");

        // STEP 3: Send the prepared message.
        mailSender.send(message);
    }
}
```

In the example:

1. `MimeMessage` holds email content/headers and MIME structures.
2. `MULTIPART_MODE_RELATED` instructs the helper to use a `multipart/related` group for HTML and dependent resources.
3. `setText(plainText, htmlText)` creates two content versions, where HTML references `cid:company-logo`.
4. `addInline(LOGO_CID, logo, "image/png")` creates the image part with the corresponding Content-ID.
5. `ClassPathResource` supplies logo data and can be read when the application is packaged as a JAR.
6. `mailSender.send(message)` hands the mail to the SMTP server; a successful call does not prove the mail entered the Inbox.

**User data appearing in HTML should be escaped.** `HtmlUtils.htmlEscape(displayName)` avoids inserting special characters directly into HTML. With many complex templates, use a template engine supporting appropriate escaping and finish rendering before calling `setText(...)`.

## 5. Why must a multipart mode be chosen?

A `MimeMessageHelper` constructor without multipart enabled may fit sending plain text or simple HTML, but is **not suitable when wanting to add inline resources via `addInline(...)`**.

Text-only example:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, "UTF-8");

helper.setText("Hello!");
```

Example needing inline:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
    );
```

Or you can use the constructor:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");
```

In Spring, the constructor with `multipart=true` uses a default multipart mode suited to common cases, including supporting both inline resources and attachments. If wanting to specify the MIME structure explicitly in code, pass a mode constant.

Modes to distinguish:

| Mode | Main structure | Case |
|---|---|---|
| `MULTIPART_MODE_NO` | Does not use multipart | Plain text/plain or simple HTML email needing no inline/attachment. |
| `MULTIPART_MODE_RELATED` | `multipart/related` | HTML with inline resources such as logos, banners. |
| `MULTIPART_MODE_MIXED` | `multipart/mixed` | Multiple parts grouped together; depending on client, less suitable for complex HTML-inline relationships. |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` wrapping `multipart/related` | Email with HTML/inline and standalone attachments. |

**Enabling multipart is a necessary condition; it does not replace calling `setText` before `addInline`.**

## 6. MIME tree explaining the ordering issue

### 6.1. HTML and logo only

The desired structure can be pictured as:

```text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:company-logo">
    └── image/png
        ├── Content-ID: <company-logo>
        └── Content-Disposition: inline
```

Here, HTML plays the role of **root content**; the PNG image is a related resource. `multipart/related` helps the mail client understand that the image serves to display the HTML content.

### 6.2. HTML, plain text, and logo

If using `helper.setText(plainText, htmlText)`:

```text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    │       └── <img src="cid:company-logo">
    └── image/png
        └── Content-ID: <company-logo>
```

`multipart/alternative` contains two **presentations of the same content**. `multipart/related` links the content containing HTML with the image. A mail client supporting HTML can choose `text/html`, while a client preferring plain text can use `text/plain`.

### 6.3. Adding a PDF attachment as well

When having both an inline logo and a PDF invoice:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   │       └── <img src="cid:company-logo">
    │   └── image/png
    │       └── Content-ID: <company-logo>
    └── application/pdf
        └── Content-Disposition: attachment
```

With this type, you can use `MULTIPART_MODE_MIXED_RELATED` and follow the order:

```text
setText(plainText, htmlText)
     ↓
addInline("company-logo", logo, "image/png")
     ↓
addAttachment("invoice.pdf", pdf, "application/pdf")
     ↓
send(...)
```

In essence `addAttachment(...)` and `addInline(...)` have different purposes: attachments are standalone components to download/open, while inline resources are referenced by HTML for display. **Do not use `addAttachment(...)` to replace `addInline(...)` for CID images.**

## 7. Example HTML + inline logo + PDF attachment

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient, byte[] invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");

        String plain = "Your PDF invoice is in the attached file.";
        String html = """
            <html>
              <body>
                <img src="cid:invoice-logo" alt="Logo" width="120">
                <p>Your PDF invoice is in the attached file.</p>
              </body>
            </html>
            """;

        // 1. Create the content first.
        helper.setText(plain, html);

        // 2. Create the image related to HTML.
        helper.addInline(
            "invoice-logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        // 3. Add standalone attachment.
        helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(invoicePdf),
            "application/pdf"
        );

        mailSender.send(message);
    }
}
```

`invoicePdf` is a byte array of the PDF generated from other business logic. Do not load overly large files into memory without checking message size limits, load capacity, and SMTP provider conditions. MIME usually encodes binary data for transport, increasing message size relative to the original file.

## 8. Multiple inline images: put all text before any addInline

An attractive marketing or notification email may have a logo, a chart, and a banner:

```html
<!DOCTYPE html>
<html lang="en">
  <body>
    <img src="cid:brand-logo" alt="Logo" width="140">
    <h1>Activity report</h1>
    <p>Here is the latest summary information.</p>
    <img src="cid:weekly-chart" alt="Activity chart" width="480">
    <img src="cid:footer-banner" alt="Contact support" width="480">
  </body>
</html>
```

Corresponding code:

```java
helper.setText(plainText, htmlText);

helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

helper.addInline(
    "weekly-chart",
    new ByteArrayResource(chartPngBytes),
    "image/png"
);

helper.addInline(
    "footer-banner",
    new ClassPathResource("mail/footer.jpg"),
    "image/jpeg"
);

mailSender.send(message);
```

There is no rule requiring calling one `setText(...)` before **each** `addInline(...)`. Normally, **call setText once to finalize the body**, then add each inline part sequentially with its own CID.

Things to keep right:

- Each `cid:...` in HTML has a matching part.
- Content-IDs of different images must not collide within the message.
- `image/png`, `image/jpeg` must accurately reflect the data.
- Do not re-edit the HTML body after starting to add inline parts unless there is a reason and you understand the MIME structure.
- Image data comes from a resource readable when Jakarta Mail needs to use it.

## 9. Render templates before calling setText

For applications with many email templates, the HTML part should be generated first by a template engine such as **Thymeleaf** or **FreeMarker**. Example flow:

```text
Business data
        |
        v
Template engine -> Complete HTML with cid:company-logo
        |
        v
helper.setText(plainText, htmlText)
        |
        v
helper.addInline("company-logo", imageResource, "image/png")
        |
        v
mailSender.send(message)
```

Pseudo-flow in Java:

```java
// renderHtml(...) is an application-implemented function using a template engine.
String html = renderHtml(templateData);
String plain = renderPlainText(templateData);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_RELATED,
    "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo(recipient);
helper.setSubject("Notification");

helper.setText(plain, html); // Finalize body.
helper.addInline("company-logo", logoResource, "image/png");

mailSender.send(message);
```

**Do not** render part of the HTML, call `setText(...)`, add images, and then call `setText(...)` again with new HTML containing changes. The later call can update/recreate the body and make the MIME structure unpredictable for mail clients.

If you need to decide how many images exist before rendering, handle that at the template-data layer, build the HTML and the resource list, then **call setText once and addInline for the entire list**.

Example object model:

```java
record InlineAsset(
    String cid,
    org.springframework.core.io.Resource resource,
    String contentType
) {}
```

Building flow:

```java
String html = renderHtml(data);
helper.setText(plainText, html);

for (InlineAsset asset : inlineAssets) {
    helper.addInline(
        asset.cid(),
        asset.resource(),
        asset.contentType()
    );
}
```

Ensure `inlineAssets` is sourced reliably, CIDs are valid, and HTML references them properly; do not allow arbitrary input data to specify sensitive file paths on the server.

## 10. Which Resource is suitable for addInline?

`MimeMessageHelper.addInline(...)` accepts image data sources in many forms. Choose a source fitting where the image is created and its re-readability.

| Source | Example | When to use |
|---|---|---|
| `ClassPathResource` | `new ClassPathResource("mail/logo.png")` | Static images in JAR/resources. |
| `FileSystemResource` | `new FileSystemResource(file)` | File sits on the filesystem and the application has read permission. |
| `ByteArrayResource` | `new ByteArrayResource(imageBytes)` | Image is dynamically generated or downloaded and held in a byte array. |
| Custom `InputStreamSource` | Source opening a fresh stream on read | Image is provided from storage or a streaming source readable multiple times. |

### 10.1. Resource must be able to open a fresh stream

Jakarta Mail may need to re-read data when calculating or transmitting MIME. Therefore an `InputStreamSource` used with `addInline(...)` should return **a fresh `InputStream` every time `getInputStream()` is called**.

`ClassPathResource`, `FileSystemResource`, and `ByteArrayResource` usually satisfy this requirement.

Avoid wrapping a single-use input stream in `InputStreamResource` and assuming the library can re-read it indefinitely:

```java
// Caution: this stream might only be readable once.
InputStream stream = storage.open("mail/logo.png");
InputStreamResource resource = new InputStreamResource(stream);
helper.addInline("company-logo", resource, "image/png");
```

If the image is small and there is no source that reopens streams, load the data into a byte array before sending:

```java
byte[] imageBytes = storage.loadBytes("mail/logo.png");
helper.setText(plainText, htmlText);
helper.addInline(
    "company-logo",
    new ByteArrayResource(imageBytes),
    "image/png"
);
```

`storage.loadBytes(...)` is an illustrative function implemented by the application. Do not load overly large images into RAM without size limits.

### 10.2. Content-Type must be correct

Example:

```java
helper.addInline("logo", pngResource, "image/png");
helper.addInline("banner", jpegResource, "image/jpeg");
```

Do not use `image/png` for a JPEG file just because the initial sample code used PNG. Mail clients can rely on MIME headers and content to decide how to display; wrong metadata increases the risk of broken images.

### 10.3. Resource name is not Content-ID

Suppose the file is `mail/logo-company-2026.png`. You can still use:

```java
helper.addInline(
    "header-logo",
    new ClassPathResource("mail/logo-company-2026.png"),
    "image/png"
);
```

HTML needs `src="cid:header-logo"`, not `cid:logo-company-2026.png`, unless you deliberately use that exact string as the CID. **Filename and CID are two independent identifiers.**

## 11. Common errors when order is wrong or MIME is inconsistent

| Symptom | Possible cause | Direction to handle |
|---|---|---|
| Email sends successfully yet image does not display | `addInline` ran before `setText`; MIME tree not as intended | Create body first, then add inline; inspect actual received raw MIME. |
| Broken image icon shown | `cid:...` does not match `Content-ID` | Compare ID in HTML with the first parameter of `addInline`. |
| Image shows only as an attachment | Unsuitable multipart mode or different mail client interpretation | Use `MULTIPART_MODE_RELATED` or `MIXED_RELATED`, verify Content-ID and MIME nesting. |
| Only text visible, no HTML visible | `setText(html)` did not enable HTML flag or wrong overload used | Use `setText(html, true)` or `setText(plain, html)`. |
| Error on addInline | Helper created in non-multipart mode | Create helper with multipart enabled. |
| Image read error on send | Resource does not exist, stream already exhausted, no read permission | Use suitable resource, ensure fresh streams can be opened. |
| Image only fails when running as JAR | Used local/source path instead of classpath | Put image into resources and use `ClassPathResource`. |
| Image duplicated/wrong image shown | Duplicate CID across parts or sharing same reference | Assign unique CID to each resource, reference properly. |
| Image blocked in some mail clients | Email client policy or unsupported format/CSS | Use PNG/JPEG, simple HTML, `alt`, and a plain-text version. |
| MIME body appears altered | Called `setText(...)` again after `addInline(...)` | Finalize HTML first, then call setText once and add inline parts. |
| Image disappears on forwarded messages | Receiving/forwarding client alters MIME structure | Check raw source of forwarded copy; do not assume structure is preserved. |

**Ordering errors do not necessarily throw exceptions.** That is why you need to understand the MIME source of received emails, not just check whether `send(...)` reported an error.

## 12. How to read raw MIME to diagnose

When you need to determine why an inline image does not render, open “Show original”, “View source”, “View raw message”, or the mail client's equivalent feature.

An **illustrative** structure may look like this (Base64 abbreviated):

```text
From: no-reply@example.com
To: alice@example.net
Subject: Welcome
MIME-Version: 1.0
Content-Type: multipart/related; boundary="rel-001"

--rel-001
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <img src="cid:company-logo" alt="Logo">
    <p>Hello!</p>
  </body>
</html>

--rel-001
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

[BASE64_PNG_DATA]

--rel-001--
```

How to read it:

1. `Content-Type: multipart/related` says the parts are related.
2. `boundary="rel-001"` is the separator string between message parts; the library generates appropriate boundaries itself.
3. The `text/html` part has `src="cid:company-logo"`.
4. The image part has matching `Content-ID: <company-logo>`.
5. `Content-Disposition: inline` hints the image part is used in the body.
6. Base64 data is content encoded for transport, **not a security mechanism**.

Real MIME messages have strict requirements for CRLF, header encoding, content-transfer-encoding, and boundaries. Let Jakarta Mail create those parts; do not concatenate MIME strings manually from the illustrative example.

**Steps to isolate:**

- **Image part missing:** check whether `addInline` was actually called, the resource exists, and the code called `setText` again after adding the image.
- **Image part exists but CID differs:** fix the `addInline` parameter or `cid:` value in HTML to match.
- **CID right yet nesting unsuitable:** use an appropriate multipart mode and the order `setText` before `addInline`.
- **MIME right yet only one client fails:** weigh display limits, image format, HTML/CSS, and mail client policy.
- **All clients fail:** inspect MIME source as well as exceptions during preparation/sending and the actual image data.

## 13. Distinguishing MIME construction errors from SMTP errors

There are two groups of errors often lumped together:

**MIME construction / display errors:**

- `setText(...)`, `addInline(...)`, or `addAttachment(...)` used in the wrong order/type.
- Wrong CID or Content-Type.
- Unopenable resource.
- Structure of `multipart/related`, `alternative`, `mixed` not as intended.
- Mail client does not render the resource as expected.

**Transport or delivery errors:**

- Cannot connect to SMTP host or wrong port/TLS.
- SMTP AUTH failed.
- Server rejected sender/recipient.
- Server rejected message due to size or content policy.
- Message bounced or blocked downstream after server acceptance.

Do not try to fix an undisplayed image by changing the SMTP password if the message was already received with all MIME parts intact. Conversely, the order of `setText`/`addInline` does not solve an SMTP port connection refusal error.

The application may encounter `MessagingException` while preparing MIME or `MailException` from Spring Mail while sending. Even without exceptions, the mail client can still display differently from expectations.

## 14. Common misconceptions

### “With the right CID, the order of addInline and setText does not matter”

**Incorrect.** CID is the link between HTML and image, while `setText(...)` determines the body and corresponding MIME structure. Spring recommends adding inline **after** setting text to avoid differences when clients resolve related parts.

### “addInline automatically inserts the img tag into HTML”

**No.** `addInline(...)` only adds the resource. HTML must include the matching `src="cid:..."` itself.

### “setText(html) is enough to send HTML”

When using `setText(String)`, the content may be treated as **text/plain**. Use `setText(html, true)` or `setText(plain, html)` when wanting HTML.

### “An email with a logo must use addAttachment”

**No.** A logo inside the body needs `addInline(...)`. PDFs for users to download usually use `addAttachment(...)`.

### “Must call setText once for each inline image”

**No.** Usually you only need to build the complete content once, then call `addInline(...)` for each image with its own CID.

### “You can use a file path in img src”

`src="C:\projects\mail\logo.png"` or `src="/static/logo.png"` has no meaning to a receiving mailbox. To embed images, use CID and a MIME part, or use an external HTTPS URL if choosing network-loaded images.

### “Base64 data URI is always simpler than CID”

Do not assume so. Many email clients restrict or do not fully support `data:` URIs in HTML. For images inside the message, `multipart/related` and CID are a clearer MIME mechanism.

### “Every mail client hides inline images from the attachment list”

No. Some clients may display logos as attachments even if the image also renders in the body. If CID and MIME structure are already right, that may just be a UI difference of the mail client.

### “Sending without throwing an exception means the logo is guaranteed to appear”

No. `send(...)` is a transfer operation at the application/SMTP layer. Rendering HTML is the responsibility of the receiving mail client.

## 15. Scenarios requiring careful handling

### 15.1. Changing template or language after adding images

Suppose the service calls:

```java
helper.setText(htmlVi, true);
helper.addInline("company-logo", logo, "image/png");

// Later discovers the recipient prefers English:
helper.setText(htmlEn, true);
```

This is an error-prone design because the body is updated after inline was added. Decide language/render template **first**:

```java
String html = language.equals("en") ? htmlEn : htmlVi;
helper.setText(html, true);
helper.addInline("company-logo", logo, "image/png");
```

If the system has many template conditions, organize into steps: “select template → render → setText → addInline → send”.

### 15.2. An image part might be missing due to business data

For example, an email with an optional banner. Do not write HTML always containing `cid:promo-banner` and then skip `addInline` when there is no image.

Solution: build HTML according to the list of actually available resources; add an `img` tag with CID only if a matching resource actually exists. Once rendering is done, call `setText` and add the exact inline assets used.

### 15.3. Same template sent to many people

You can reuse the **template** and **logo resource**, but create a separate `MimeMessage` for each personalized message. Do not let multiple workers concurrently modify one `MimeMessage` or `MimeMessageHelper` object while sending, as it can mix up recipients and body parts.

```text
for each recipient:
    createMimeMessage()
    new MimeMessageHelper(...)
    render user-specific HTML
    setText(...)
    addInline(...)
    send(...)
```

Sending to multiple people in the same MIME message is a different problem; if content is personalized, explicitly design privacy and per-recipient tracking.

### 15.4. CID and HTML content safety

Do not let user data directly control:

- `Content-ID` containing abnormal characters or newlines;
- filesystem paths used as inline resources;
- HTML containing scripts or untrusted resources;
- mail headers concatenated from unchecked values.

Use a template engine with default escaping or escape data when inserting into HTML, choose CIDs from application-defined values, and load resources only from authorized sources. HTML emails should have `alt` for images and a plain-text version for important information.

## 16. Practice exercises

### Exercise 1: Reorder the lines

Given the code snippet:

```java
helper.addInline(
    "logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

helper.setText(
    "<html><body><img src=\"cid:logo\"></body></html>",
    true
);
```

Fix the order following Spring's recommendation.

**Hint:** move `setText(...)` before `addInline(...)`. Ensure the helper was created in multipart mode.

### Exercise 2: Find the CID error

HTML:

```html
<img src="cid:header-logo" alt="Logo">
```

Java:

```java
helper.setText(htmlText, true);
helper.addInline(
    "footer-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

**Error:** `cid:header-logo` does not match the first parameter of `addInline(...)`, which is `footer-logo`. Fix one side so both values align.

### Exercise 3: Add inline image and PDF

The email needs a logo and a PDF invoice. Choose the multipart mode, write the calling order:

1. `setText(plainText, htmlText)`;
2. `addInline("logo", ...)`;
3. `addAttachment("invoice.pdf", ...)`;
4. `send(message)`.

**Suggested answer:** `MULTIPART_MODE_MIXED_RELATED` for the related group holding HTML/logo and the standalone PDF part.

### Exercise 4: Resource from a one-time stream

You receive an image `InputStream` from storage and wrap it with `InputStreamResource`. The mail library may read data multiple times during preparation and sending. Explain why this approach is error-prone and switch to a source capable of opening fresh streams or `ByteArrayResource` for moderately sized images.

### Exercise 5: Issue occurring on only one mail client

The email landed in the Inbox of two applications, but one app displays the logo and the other shows only an attachment. Inspect raw MIME, check `multipart/related`, `Content-ID`, `cid:...`, and `Content-Type`; then assess support differences between the two mail clients.

### Exercise 6: Building email from a template

The application uses an HTML template with a logo and an optional banner. Design a processing chain including:

- retrieving business data and deciding which assets appear;
- rendering complete HTML, while creating a plain-text version;
- calling `setText(plain, html)`;
- adding each image via `addInline(...)` with chosen CIDs;
- calling `send(...)` after finalizing MIME.

### Self-check questions

1. Why must `setText(...)` come before `addInline(...)`?
2. How does the first parameter of `addInline(...)` relate to `src="cid:..."`?
3. How does `Content-ID` differ from `Message-ID`?
4. When having both inline and attachment, which mode expresses the structure well?
5. Why is `ByteArrayResource` usually more suitable than a read-once input stream?
6. If `send(...)` succeeds yet images do not appear, should you check the SMTP password or MIME structure first?
7. Can you call `setText(...)` once and `addInline(...)` multiple times?

**Hints:** (1) so the main content/MIME tree is set up before adding related resources; (2) identifiers must match; (3) Content-ID identifies a MIME part, Message-ID identifies the message; (4) MIXED_RELATED; (5) can be read multiple times; (6) MIME and mail client; (7) yes, with a separate CID for each image.

## 17. Summary

To create HTML emails containing inline resources in **Spring Framework Mail**, enable an appropriate multipart mode, **finalize the HTML or HTML/plain-text content first using `MimeMessageHelper.setText(...)`, and only then call `MimeMessageHelper.addInline(...)`** for each resource. `cid:...` used in HTML must match the Content-ID of the image part; the resource source must be readable and the Content-Type must be accurate.

When the email also has attachments, `MULTIPART_MODE_MIXED_RELATED` keeps HTML and related images in one group while attachments sit in a separate part. If images still fail to display, inspect the actual received MIME source and support differences across mail clients. **The order `setText → addInline → send` is a small rule yet very important for HTML emails with inline images to work more reliably across many mail-reading apps.**


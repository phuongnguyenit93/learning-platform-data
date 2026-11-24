# Referencing inline resources from HTML via cid

## 1. What problem do inline resources and cid solve?

In HTML emails, applications often need to display logos, icons, illustrations, or other resources alongside the content. One method is putting an HTTP/HTTPS URL inside the HTML tag; another method is **attaching the resource as a MIME part related to the HTML content** and referencing that resource via **Content-ID**, often shortened to **cid**.

With **Spring Framework Mail**, the **MimeMessageHelper** class supports this through the **addInline(...)** method. HTML contains a reference such as:

~~~html
<img src="cid:brandLogo" alt="Brand logo">
~~~

Then Java creates a MIME part containing the image data and attaches the matching Content-ID:

~~~java
helper.addInline("brandLogo", new ClassPathResource("mail/brand-logo.png"));
~~~

When an email client reads the message and supports the related MIME structure, it can find the MIME part carrying Content-ID **brandLogo** to display right at the img tag position. **There is no need to load the image from a public URL** as with remote images, though that **does not guarantee every email client will display the image**: clients can block images, alter HTML, or support CID differently.

Key points of the lesson:

- **cid:** is a form of reference from HTML content to a resource with a **Content-ID** in the same MIME message.
- **addInline(...)** places the resource into the message and sets Content-ID so the client can look it up.
- **multipart/related** describes the relationship between the main HTML part and inline resources depending on it.
- **setText(...) before addInline(...)** is the recommended order with MimeMessageHelper.
- An inline resource **differs** from an ordinary file attachment and also **differs** from images loaded from an external website.

## 2. Three ways to include images in HTML emails

Suppose an order-confirmation email has a brand logo. There are three common ways:

| Method | Syntax in HTML | Advantages | Limitations |
|---|---|---|---|
| **Image from external URL** | img src="https://..." | Does not increase MIME size much; image content served by web server/CDN | Clients may block remote images; requires accessible URL; has privacy and image-load tracking issues |
| **Inline image via CID** | img src="cid:brandLogo" | Image sits inside the email itself, no public HTTP URL needed to fetch content | Larger email; depends on MIME/client; can still be blocked from display |
| **Data URI image** | img src="data:image/png;base64,..." | Embeds data directly in HTML | Many email clients offer limited support or strip it; lengthens HTML; not a default compatible choice |

With Spring Mail, the CID method is convenient when the image is a small, fixed resource that needs to be packaged with the message. It is very common for logos or icons in notification emails. However, **CID images are not a guarantee of display across all mail-reading apps**; emails still need fallback text content.

### How does CID differ from an HTTP URL?

~~~text
HTML using URL:
  <img src="https://static.example.com/logo.png">
                         |
                  Email client loads image via HTTPS

HTML using CID:
  <img src="cid:brandLogo">
                 |
         Finds MIME part with matching Content-ID
                 |
         Reads image data sitting in the same email
~~~

CID is an **internal link inside the email message**, not a Spring MVC API endpoint, not a local file path on the recipient's machine, and not an HTTP URL that an ordinary browser can access directly.

## 3. How are Content-ID and the cid: expression related?

MIME identifies a content part by the **Content-ID** header. For example, the image part may have headers:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Disposition: inline
Content-ID: <brandLogo>
~~~

The HTML part references the image with:

~~~html
<img src="cid:brandLogo" alt="Logo">
~~~

Distinguish:

| Location | Value | Meaning |
|---|---|---|
| In HTML | **cid:brandLogo** | The cid URL scheme pointing to a MIME body part inside the email. |
| In Spring API | **addInline("brandLogo", resource)** | Registers content linked to Content-ID brandLogo. |
| In MIME header | **Content-ID: <brandLogo>** | Identifier of the content part; in headers usually enclosed in angle brackets. |

**Do not pass the cid: prefix or angle brackets into the contentId parameter** of the addInline method. In this example, the parameter string is **brandLogo**, while HTML adds **cid:** itself.

For complex Content-IDs, standard MIME IDs usually take a form similar to a message identifier and must ensure proper syntax/escaping. In generated email content, use simple, stable IDs unique within the scope of the message, such as **brandLogo** or **invoiceIcon**. If using an ID containing characters with special meaning in URLs, the cid reference must be appropriately URL-encoded rather than arbitrarily concatenated.

## 4. MIME structure of HTML and inline images

An HTML email with inline images is not just an HTML string. It is usually represented using **multipart/related**:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

**multipart/related** indicates that MIME parts are related to one another. Here the HTML part is the content to display, and the image/png part is the resource HTML needs to render completely.

### Raw MIME for visualization

~~~text
From: notifications@example.com
To: customer@example.net
Subject: Example
MIME-Version: 1.0
Content-Type: multipart/related; boundary="related_001"

--related_001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html>
  <body>
    <p>Welcome!</p>
    <img src="cid:brandLogo" alt="Company logo">
  </body>
</html>

--related_001
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline

... base64-encoded image bytes ...

--related_001--
~~~

The example only illustrates structure; **... base64-encoded image bytes ...** is not valid image data. In practice, Jakarta Mail automatically generates boundaries, headers, encodings, and appropriate transport data. Do not assemble raw MIME like this manually for sending in production.

### multipart/related, multipart/alternative, and multipart/mixed differ

| MIME subtype | Relationship between parts | Case |
|---|---|---|
| **multipart/related** | Related parts that can reference one another | HTML and CID images |
| **multipart/alternative** | Alternative representations of the same content | Plain text and HTML |
| **multipart/mixed** | Components traveling together | Email content and ordinary attached files |

When an email has plain text, HTML, inline images, and attachments, subtypes are usually **nested**:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   │       └── <img src="cid:brandLogo">
    │   └── image/png; Content-ID: <brandLogo>
    └── application/pdf; attachment
~~~

The tree above represents **logical relationships**. The actual MIME structure may differ slightly depending on multipart mode and library version. Do not require the root Content-Type to necessarily be multipart/related when there are attachments or a plain-text alternative.

## 5. Preparing Spring Boot to send HTML emails

In a Spring Boot application using Java 21, the common dependency is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example SMTP configuration over submission port 587 with STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: account@example.com
    password: REPLACE_WITH_SECRET
    default-encoding: UTF-8
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
~~~

The host address and account are for illustration only. In real environments, SMTP passwords/tokens must be sourced from environment variables or a secret manager; do not store them directly in the repository. Port and TLS mode settings must match the provider: port 465 usually uses implicit TLS instead of STARTTLS.

**Spring Boot** can auto-configure the **JavaMailSender** bean from appropriate settings. **Spring Framework Mail** provides **MimeMessageHelper** and the MIME API; CID packaging is created when the application builds the message, not as an option in spring.mail.host.

Illustrative image resource placed at:

~~~text
src/
└── main/
    └── resources/
        └── mail/
            └── brand-logo.png
~~~

Because it belongs to the resources directory, the file can be accessed with **ClassPathResource("mail/brand-logo.png")**, even when the application is packaged as a JAR, provided the resource is included on the classpath at build time.

## 6. Complete example: inline image with addInline

Below is a service using **JavaMailSender**, **MimeMessageHelper**, and **ClassPathResource**. The email contains both a plain-text version and an HTML version, where the HTML version references the image via CID.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "brandLogo";
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String plainText = """
                Hello!

                Your account is ready.
                Visit https://example.com/account to view your information.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <img
                      src="cid:brandLogo"
                      alt="Brand logo"
                      width="140">
                    <h2>Hello!</h2>
                    <p>Your account is ready.</p>
                    <p>
                      <a href="https://example.com/account">
                        View account information
                      </a>
                    </p>
                  </body>
                </html>
                """;

        // Set the text/HTML content first.
        helper.setText(plainText, htmlText);

        // Then add the MIME part that HTML references via cid:brandLogo.
        ClassPathResource logo =
                new ClassPathResource("mail/brand-logo.png");
        helper.addInline(LOGO_CID, logo, "image/png");

        mailSender.send(message);
    }
}
~~~

The example assumes the SMTP sender is configured, the sender is authorized to use **notifications@example.com**, and the **mail/brand-logo.png** resource actually exists on the classpath. The **LOGO_CID** string must match the value after **cid:** in the HTML's src attribute.

### Analysis of key lines

**createMimeMessage():** Creates a MimeMessage object to build the email content.

**MULTIPART_MODE_MIXED_RELATED:** Selects a multipart mode supporting HTML content, related resources, and attachments if needed later. Depending on usage, the email may contain multiple nested MIME layers.

**UTF-8:** Enables displaying accented Vietnamese content and supports appropriate header/body encoding.

**setText(plainText, htmlText):** Creates two alternative representations for the same message. The plain-text version can be read independently if the client does not display HTML or images.

**addInline("brandLogo", logo, "image/png"):** Adds the PNG image data into a MIME body part with the matching Content-ID. The third parameter specifies the exact media type of the image, helping the mail client process the content part.

**send(message):** Submits the prepared message to the email sending infrastructure. Initial success at the SMTP stage does not prove the image is displayed on every client or that all mail entered the Inbox.

## 7. Why must setText be called before addInline?

With **MimeMessageHelper**, calling **setText(...)** can set or replace the message body and certain internal multipart structures. If attaching inline resources before setting the body, some MIME structures might not be created in the relationship the email client expects.

**Recommended order:**

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, MimeMessageHelper.MULTIPART_MODE_RELATED, "UTF-8"
);

helper.setFrom("sender@example.com");
helper.setTo("recipient@example.net");
helper.setSubject("Notification");

// 1. Set HTML first.
helper.setText(
        "<p>Hello!</p><img src=\"cid:logo\" alt=\"Logo\">",
        true
);

// 2. Add the inline resource afterward.
helper.addInline(
        "logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

This is how to create an HTML email with an inline image without needing an alternative plain-text version. In applications notifying many kinds of email clients, **include plain text as well** via the **setText(plainText, htmlText)** overload.

Do not do it in reverse order:

~~~java
// Order to avoid in real applications.
helper.addInline("logo", logoResource, "image/png");
helper.setText(htmlText, true);
~~~

This is an important note about API usage, not a condition of cid URL syntax. CID still means a reference to Content-ID; the issue lies in how the library constructs the MIME tree when methods are called in sequence.

## 8. Choosing a multipart mode for inline images

**MimeMessageHelper** provides multipart modes used when initializing the helper:

| Mode | Meaning | When to consider |
|---|---|---|
| **MULTIPART_MODE_NO** | Does not use multipart structure | Single-part text/HTML email, adding no inline resources or attachments. |
| **MULTIPART_MODE_MIXED** | Creates multipart/mixed structure | Suitable for body and attachments, though inline relationships may not be optimal on every client. |
| **MULTIPART_MODE_RELATED** | Creates multipart/related | HTML email with inline resources, when an outer mixed structure is not needed. |
| **MULTIPART_MODE_MIXED_RELATED** | Combines mixed and related layers | General choice when having both inline resources and attachments. |

The **true** mode in constructor **MimeMessageHelper(message, true, encoding)** requests enabling multipart, using a default multipart mode of the helper. When needing a predictable structure, explicitly specify the appropriate mode as in the examples above.

### When to choose RELATED?

For an HTML email with only a logo, you can use:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
~~~

When adding a PDF file for users to download, the structure usually needs **mixed** to distinguish attachments from HTML content and related images:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Choosing the MIME subtype can affect how email clients interpret attachments and inline content. Do not use **MULTIPART_MODE_NO** and expect **addInline** to create related resources properly.

## 9. Overloads of addInline

**MimeMessageHelper** has different ways to accept resource sources. Depending on the case, you can use File, Resource, or InputStreamSource alongside Content-Type.

### 9.1. File on the filesystem

~~~java
import java.io.File;

File logoFile = new File("/opt/app/assets/brand-logo.png");
helper.addInline("brandLogo", logoFile);
~~~

The example assumes the file exists at that location. This is a filesystem path on the machine **running the application**, not a path the email client will open. The file data is placed into the email as a MIME part when the message is prepared/sent.

**Limitation:** the file might not exist in a Docker container or production server. When packaging static images with the application, using ClassPathResource is usually easier to port across environments.

### 9.2. Resource on the classpath

~~~java
import org.springframework.core.io.ClassPathResource;

ClassPathResource logo =
        new ClassPathResource("mail/brand-logo.png");

helper.addInline("brandLogo", logo, "image/png");
~~~

**ClassPathResource** accesses the resource from the classpath. This approach fits fixed logos packaged in the application's **src/main/resources** folder.

### 9.3. ByteArrayResource for image data in memory

Suppose an image is generated from a chart-rendering service and the application holds a valid PNG byte array:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pngBytes = generatePngBytes(); // Function provided by the application.

helper.addInline(
        "chartImage",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

The snippet assumes **generatePngBytes()** returns valid PNG content; this is a hypothetical function to illustrate the data source, not a built-in Spring API.

**ByteArrayResource** allows reopening an InputStream from the byte data when needed. This is useful because Jakarta Mail may read the data source while serializing the message or performing transport.

### 9.4. Resource and content type

If the library cannot accurately determine the resource type from the filename or the data source has no filename, use the overload with media type:

~~~java
helper.addInline("brandLogo", resource, "image/png");
~~~

The media type must match the actual data, such as **image/png**, **image/jpeg**, or **image/gif** as appropriate. Do not set **image/png** for JPEG bytes just because of an extension or assumed content.

## 10. Important note about InputStreamSource

An inline resource does not just need to be **openable once**. When building a MimeMessage, the library may request reading the data multiple times depending on how it encodes, serializes, and sends.

Therefore, the object passed to **addInline** should be capable of providing a **fresh InputStream** each time requested. Commonly suitable choices:

- **ClassPathResource** pointing to an existing classpath file.
- **FileSystemResource** pointing to a readable file.
- **ByteArrayResource** wrapping a byte array remaining in memory.

Conversely, **InputStreamResource** usually wraps an already-open stream and is unsuitable if the same stream must be read again. Where the source has only a single InputStream, read the data into a size-bounded byte[] first, or store it in a durable location and supply a re-openable Resource.

Example of not relying on a one-time stream:

~~~java
// InputStream openable only once: risks failure when the library re-reads.
InputStream stream = remoteClient.openLogoStream();
InputStreamResource oneShot = new InputStreamResource(stream);
helper.addInline("brandLogo", oneShot, "image/png");
~~~

A more stable model is using ByteArrayResource:

~~~java
byte[] logoBytes = loadLogoBytesSafely();
ByteArrayResource repeatable = new ByteArrayResource(logoBytes);
helper.addInline("brandLogo", repeatable, "image/png");
~~~

The functions **remoteClient.openLogoStream()** and **loadLogoBytesSafely()** are conceptual. In production, limit file size, handle network timeouts, and validate the resource source before placing it into an email. Do not read a resource from an arbitrary user-entered URL without control, as it can cause **SSRF** or resource abuse.

## 11. Multiple inline images in the same email

Each resource needs a **distinct Content-ID** so HTML can reference it accurately. Example of an email with a logo and a support icon:

~~~html
<!doctype html>
<html lang="en">
  <body>
    <header>
      <img src="cid:brandLogo" alt="Logo" width="160">
    </header>
    <h2>Invoice has been issued</h2>
    <p>Contact support if you need more information.</p>
    <footer>
      <img src="cid:supportIcon" alt="Support icon" width="24">
    </footer>
  </body>
</html>
~~~

Preparation code:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
helper.addInline(
        "supportIcon",
        new ClassPathResource("mail/support-icon.png"),
        "image/png"
);
~~~

**Do not use the same Content-ID for two different images** in the same MIME tree requiring clear references. Clients may pick the wrong part or fail to display as intended.

There is no need to create one MimeMessage per image: multiple inline resources can coexist inside **one email** and are grouped in multipart/related.

### How to name Content-IDs?

Practical suggestions:

- Use names distinguishing roles, for example **brandLogo**, **invoiceChart**, **supportIcon**.
- Keep values consistent between HTML and the addInline method.
- Do not put secrets or personally identifiable data into IDs.
- For systems rendering templates from multiple sources, manage IDs centrally to avoid collisions.
- If needing IDs following specific Content-ID syntax, use valid ID generation and encode cid references appropriately.

## 12. Email with both inline images and file attachments

**Inline resources** and **attachments** carry different meanings. A logo used directly in HTML should be added via **addInline(...)**. A PDF file for the recipient to download should be added via **addAttachment(...)**.

Example:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.File;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailSender {

    private final JavaMailSender sender;

    public InvoiceMailSender(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(String recipient, File invoicePdf)
            throws MessagingException {
        MimeMessage mimeMessage = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");

        String plainText = "The invoice is attached in this email.";
        String htmlText = """
                <html lang="en">
                  <body>
                    <img src="cid:brandLogo" alt="Brand logo">
                    <p>The invoice is attached in this email.</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );
        helper.addAttachment("invoice.pdf", invoicePdf);

        sender.send(mimeMessage);
    }
}
~~~

In the example, **invoicePdf** must be a real, valid file that the recipient has the right to view. Do not send one person's invoice to another person. For sensitive files, consider encryption requirements, access rights, and storage policies; MIME and CID do not create end-to-end security on their own.

### Can an inline attachment still appear in the reader UI?

Some email clients may display inline resources in the attachment list or use another presentation, even though the MIME part is set to **Content-Disposition: inline** and has a Content-ID. That is client-side behavior, not necessarily a mail-sending bug. The difference between inline and attachment is **intent and MIME structure**, not a uniform UI guarantee.

## 13. Using CID in HTML templates

In real applications, emails are usually rendered from Thymeleaf, FreeMarker, or a template engine. HTML can then contain fixed CID references:

~~~html
<table role="presentation">
  <tr>
    <td>
      <img
        src="cid:brandLogo"
        alt="Brand"
        width="160">
    </td>
  </tr>
  <tr>
    <td>
      <h2>Account notification</h2>
      <p>Notification content rendered from template.</p>
    </td>
  </tr>
</table>
~~~

The service must ensure every **cid:brandLogo** reference has a matching MIME part added via the helper. If another template does not use the logo, you can skip adding unnecessary resources to reduce message size.

### Attaching dynamic data

If the email contains the recipient's name, order code, or links, render the data into the template using **context-appropriate escaping**. Do not directly concatenate user content into HTML because data may contain special characters or unintended HTML structure.

CID only solves **referencing resources inside MIME**; it does not sanitize HTML data, control external URLs, or prevent a template from containing malicious links.

If generating CIDs dynamically from input data, validate and encode appropriately. In most use cases, it is better to keep a fixed list of application-managed IDs, such as **brandLogo** and **productPhoto**.

## 14. MIME and email client behavior

In practice, HTML emails must work across many email clients with varying HTML/CSS support. A message with valid MIME can still display differently depending on device, client, and security policy.

A few notes:

- **Images can be blocked from display**, even when embedded inline. **alt** attributes and text content not solely dependent on images are needed.
- **CSS in email has limits**. Do not expect JavaScript or browser APIs to load or modify content.
- **cid paths** in the img src attribute are the most common method. Do not assume every client supports CID identically in CSS background-image.
- **Overly large images** increase message size and may load slowly or exceed SMTP server limits.
- **Image formats** like PNG/JPEG are generally easier to support than some newer formats or SVG images whose handling varies across clients.
- **An image in an email does not guarantee it was viewed**. Successful send status does not mean the client opened/displayed the image part.

### Fallback when the logo is not visible

Do not put important information such as verification codes, amounts, payment deadlines, or action links **only inside images**. Even when the logo is not displayed, the email must still convey the core content.

For example, instead of displaying just an image saying “Order completed”, include lines of text as well:

~~~html
<img src="cid:brandLogo" alt="Brand logo" width="160">
<h2>Your order has been completed</h2>
<p>Please log in to view details.</p>
~~~

With equivalent content in the **text/plain** part, users reading email in text mode still receive the message without needing images.

## 15. Why does CID affect email size?

Images added with addInline are part of the MIME content. Binary data is usually represented via **Content-Transfer-Encoding**, for example base64, when transmitted in email. This encoding makes the message content larger than the original byte size of the image, not counting MIME headers and boundaries.

Conceptual example:

~~~text
PNG logo on disk
       |
       v
MIME part image/png + Content-ID
       |
       v
Transcoded for email protocol (usually base64)
       |
       v
Total MimeMessage size increases
~~~

Design consequences:

1. Optimize logos and images before packaging.
2. Limit the number of inline images and the size of each image.
3. Consider remote images for large content, while understanding visibility and privacy risks.
4. Read the message size limits of the SMTP/ESP used.
5. Avoid embedding the same image data multiple times under multiple Content-IDs when not truly needed.

Base64 in MIME is **transport encoding**, not security encryption. Anyone with access to the raw email can still decode the image content.

## 16. Common errors when referencing CID

| Symptom | Possible cause | Direction to handle |
|---|---|---|
| HTML shows a broken image icon | HTML uses **cid:brandLogo** but no MIME part matches Content-ID | Check CID values in HTML and addInline, inspect raw MIME. |
| Using **cid:brandLogo** as addInline parameter | Wrong ID value passed; addInline needs the ID without the cid: prefix | Call **addInline("brandLogo", resource)**. |
| Image does not display when added to email | Helper is not in an appropriate multipart mode | Create helper with **MULTIPART_MODE_RELATED** or **MIXED_RELATED**. |
| Image displays as an attachment | MIME tree/disposition or client handling differs from expectation | Check multipart/related, Content-ID, Content-Type, and the specific client. |
| Image disappears after changing HTML content | Called addInline before setText, altering multipart structure | Put **setText(...) before addInline(...)**. |
| Classpath file not found | Resource is missing from JAR or wrong classpath | Check **src/main/resources/mail/** location and filename. |
| Attachment/inline fails when sending | Resource no longer readable, stream closed, or read-once only | Use a re-openable Resource; do not use uncontrolled one-shot streams. |
| Email client cannot identify image type | Wrong Content-Type or Resource lacks filename | Use the appropriate **addInline(contentId, source, contentType)** overload. |
| Two images swapped or wrong one picked | Two parts share the same Content-ID | Assign a unique ID to each resource. |
| Image missing on only one client | Client blocks images or does not support specific structure/CSS | Keep plain-text/alt fallback and test client capabilities. |
| Sending rejected by SMTP for being too large | Too many inline images or overly heavy resources | Optimize images, reduce resources, check provider limits. |
| Using a local URL in HTML | Writing **src="C:\\assets\\logo.png"** or a server file path | Use **cid:** with addInline or a valid HTTPS URL. |
| Email sends successfully yet goes to Spam | Sending reputation, domain authentication, or receiving content/policy issues | Investigate SMTP/ESP, SPF/DKIM/DMARC, and destination mail system; CID does not fix this. |

## 17. Observing the raw message to understand actual references

During development, send an email to an SMTP test inbox or test mail server and inspect **Show original / View source / Raw message** to observe headers and MIME parts.

Important details to verify:

1. The HTML part has **img src="cid:..."** with the exact ID name.
2. There is a MIME body part containing the matching **Content-ID**.
3. The body part has a valid **Content-Type**, for example **image/png**.
4. The HTML and resource parts are grouped in an appropriate **multipart/related** relationship.
5. If plain text exists, **multipart/alternative** holds two equivalent content versions.
6. If there is a downloadable file, that part is represented as an attachment, not confused with inline images.
7. The resource exists and binary data is written completely into raw MIME.

Example raw MIME usually contains:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline
~~~

Not all headers necessarily appear in the exact order above; mail transports and clients may normalize or reorder headers. What to recognize is the **logical link between cid in HTML and Content-ID of the MIME part**.

**Data note:** Raw emails can contain recipient addresses, confirmation links, tokens, personal content, and attachments. Open or save them only in authorized environments; do not copy sensitive data into logs or public error-tracking systems.

## 18. CID and security when handling resources

Inline resources often seem harmless because they are just logos or illustrations. However, the application must still control data put into emails.

**File sources:** If loading a resource from a user-supplied path, prevent path traversal and access to files outside the allowed scope. For static files, use ClassPathResource from a fixed path defined by the application.

**URL sources:** If having to fetch an image from an external URL and put it into MIME, restrict domains, destination networks, size, and fetch duration to prevent SSRF and worker exhaustion. Do not grant freedom for a URL in a request to make the application fetch arbitrary internal network resources.

**File content:** Verify actual data type, size, format, and usage rights. Do not rely solely on extensions when setting Content-Type.

**Personal data:** Do not use the same email for multiple people if the content contains images, charts, or encoded information specific to one person. Inline images do not alter a recipient's right to read content.

**Logging and retention:** Do not log MIME bodies, sensitive image base64, OTPs, or password-reset links. If the system stores messages for retry, manage lifecycle and access permissions for data/attachments.

## 19. Pattern for reusing inline resources in an application

When multiple email types use the same logo, consolidate the CID name and resource path into a shared component. For example:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MailBranding {

    public static final String LOGO_CID = "brandLogo";

    private MailBranding() {
    }

    public static void addBrandLogo(MimeMessageHelper helper)
            throws MessagingException {
        helper.addInline(
                LOGO_CID,
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );
    }
}
~~~

A service can use:

~~~java
String htmlText = """
        <html lang="en">
          <body>
            <img src="cid:brandLogo" alt="Brand logo">
            <p>New notification from the system.</p>
          </body>
        </html>
        """;

helper.setText(
        "New notification from the system.",
        htmlText
);
MailBranding.addBrandLogo(helper);
~~~

Here the **brandLogo** value in HTML and **MailBranding.LOGO_CID** must be kept consistent. In large projects, templates can receive the CID value from a constant or shared model, instead of repeating the string in many places.

If multiple brands or multiple tenants use different logos, route to a resource configured/approved per tenant. Do not just swap the CID name; the application must also ensure the right file and resource usage permissions.

## 20. When to use CID and when not to?

**CID fits when:**

- HTML email needs a small logo/icon packaged with the content.
- You do not want to rely on a public URL when the email client renders the image section.
- The system already has a stable resource readable at send time.
- The MIME size increase compared to HTML using only HTTP links is acceptable.
- Content still has a fallback option when images are blocked.

**Consider another solution when:**

- There are many large images, because message size could exceed provider limits.
- Resources update frequently without needing a fixed snapshot saved in every email.
- Compatibility is needed with email clients that do not support CID images well.
- Image load tracking or CDN delivery is required, and using remote images is permitted privacy-wise.
- Content truly needs the user to download it: use attachments, do not use addInline just to mimic downloadable files.

Choose the method based on **content purpose**, **compatibility**, **size limits**, **security**, and **operational requirements** rather than just picking shorter code.

## 21. Summary

In **Spring Framework Mail**, for HTML to reference an embedded resource via CID, the application needs two matching parts:

1. **HTML** references the resource using **cid:contentId** syntax, for example **img src="cid:brandLogo"**.
2. **MimeMessageHelper** adds the resource with matching Content-ID via **addInline("brandLogo", resource, "image/png")**.

The message must use an **appropriate MIME multipart mode**, usually based on **multipart/related**; when there are plain text and attached files, **multipart/alternative** and **multipart/mixed** can be nested. When using MimeMessageHelper, **set content with setText(...) first, then call addInline(...)**; also use a re-readable resource and an accurate media type.

CID packages images with the email for clients to locate by Content-ID, but does not replace text/alt fallbacks, does not guarantee display on every email client, and does not secure content on its own. Properly understanding the **HTML cid → MIME Content-ID → resource data** link is the foundation for creating HTML emails with reliable inline images in Spring Framework Mail.

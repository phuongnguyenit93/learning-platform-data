# cid URL and Content-ID

An order notification email often includes a logo, icon, or illustration directly inside the HTML part. If an application only puts a website image path in the `src` attribute, the email client may have to fetch the image from the Internet when the recipient opens the email. Another approach is to **embed the image data directly inside the message** and reference it from the HTML using a `cid:` address.

This mechanism relies on two linked components:

- **Content-ID** is a MIME header that identifies a content part, such as a PNG image attached inline.
- **cid URL** is the address used inside the HTML content to reference the MIME part with the matching Content-ID.

In **Spring Framework Mail**, `MimeMessageHelper.addInline(...)` adds an inline resource and sets its Content-ID. The HTML body can use `<img src="cid:...">` to display the image. The key requirement is that **the Content-ID value in the MIME part and the value after the `cid:` prefix in the HTML must match**.

This lesson explains the MIME structure, how to generate CIDs, how to use `MimeMessageHelper` and `JavaMailSender`, resource considerations, testing, and common mistakes when sending emails with inline images.

## 1. What is an inline resource?

An email can contain multiple MIME parts: plain text, HTML, images, and file attachments. An **inline resource** is a resource placed inside the message so the message body can reference and display it at a specific position.

Example of an email with a logo:

~~~html
<html>
  <body>
    <h2>Your order is confirmed</h2>
    <img src="cid:brand-logo" alt="Company logo">
    <p>Thank you for your purchase.</p>
  </body>
</html>
~~~

Here `cid:brand-logo` is neither a website URL nor a file path on the server. It is a **reference to a MIME part** with the matching Content-ID inside the same message.

In the message, the image part can have headers like:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brand-logo>
Content-Disposition: inline
~~~

The line `Content-ID: <brand-logo>` identifies the image part. The HTML part references it with `cid:brand-logo`, omitting the header's angle brackets.

~~~mermaid
flowchart LR
    A["HTML body"] -->|"src = cid:brand-logo"| B["Content-ID: <brand-logo>"]
    B --> C["MIME part containing logo.png"]
    C --> D["Email client renders inline image"]
~~~

The image is sent along with the email as part of the MIME content. The recipient does not need access to an internal file path on the application server to obtain the image.

## 2. What is Content-ID?

**Content-ID** is a MIME header used to identify a content part within a message. Its value is typically formatted like a message-id enclosed in angle brackets:

~~~text
Content-ID: <brand-logo>
~~~

For HTML emails, the email client can look up the MIME part whose Content-ID is referenced by a `cid:` URL.

Example:

| Location | Value |
| --- | --- |
| Image MIME header | `Content-ID: <brand-logo>` |
| HTML attribute | `src="cid:brand-logo"` |
| Value passed to `addInline` | `brand-logo` |

In the `MimeMessageHelper.addInline(contentId, ...)` API, pass the **ID** as the argument. Do not add the `cid:` prefix and generally do not manually add angle brackets. The helper generates the appropriate MIME header.

### 2.1. Content-ID must match the cid URL

Suppose the helper adds an image with the ID:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png"
);
~~~

The HTML must reference it accurately:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

If the HTML writes `cid:company-logo` while the MIME part carries Content-ID `brand-logo`, the email client will not find the matching resource. The image may show up as broken or remain hidden.

**Do not include angle brackets in the HTML URL**:

~~~html
<!-- Correct -->
<img src="cid:brand-logo" alt="Logo">

<!-- Do not use header format inside a cid URL -->
<img src="cid:<brand-logo>" alt="Logo">
~~~

Angle brackets belong to the Content-ID header representation, whereas a cid URL references the ID value according to URL syntax.

### 2.2. Choosing unique IDs

A single message can contain multiple inline images:

~~~text
brand-logo
product-image
footer-banner
~~~

Each part needs a distinct ID so it can be referenced accurately. Following Content-ID conventions, use unique identifiers; when sending high volumes of email, avoid a generic ID that could collide across processing systems or when messages are aggregated.

You can generate an ID using a UUID:

~~~java
String contentId = "logo-" + UUID.randomUUID();
~~~

If you want a domain-qualified identifier, you can use a message-id-like value such as `logo-uuid@mail.example.org`, making sure reserved characters are properly represented when forming the cid URL. For simple application examples, a safe ASCII token such as `logo-550e8400-e29b-41d4-a716-446655440000` is usually easier to interpolate and verify.

Do not use arbitrary filenames as IDs if the names contain spaces, special characters, or might collide. Content-ID is the identifier of a **MIME part**, not a display filename.

## 3. How does a cid URL work?

`cid:` is a URL scheme used to reference content that has a Content-ID inside the message. Example:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

The email client parses the HTML, recognizes the cid URL, and looks up the matching MIME part in the message structure. If it finds an image part with the matching Content-ID, it can use those image bytes to render the image.

The linkage can be visualized as:

~~~text
HTML part:
  <img src="cid:brand-logo">

Related image part:
  Content-Type: image/png
  Content-ID: <brand-logo>
  Content-Disposition: inline
  [image data]
~~~

### 3.1. A cid URL is not an HTTP URL

Two different ways of referencing images:

~~~html
<!-- Image loaded from a website -->
<img src="https://cdn.example.org/images/logo.png" alt="Logo">

<!-- Image embedded in the message -->
<img src="cid:brand-logo" alt="Logo">
~~~

With an HTTPS URL, the email client may have to fetch the image from an external server. With CID, the image data is already inside the MIME message, so the client does not need to call a website to retrieve that image.

CID does not mean the image is encrypted or secret. The image content is still inside the email and can be saved or extracted by the recipient like any other MIME part.

### 3.2. Special characters in Content-ID

According to cid URL syntax, the referenced value must follow URL rules and use percent-encoding for special characters when necessary. To avoid discrepancies across libraries and email clients, choose Content-IDs that are short, stable within a message, and composed of safe ASCII characters such as letters, digits, hyphens, or dots.

If you use an ID containing characters that require percent-encoding, make sure the cid URL in the HTML represents the same ID according to the corresponding rules. Do not arbitrarily encode the entire header string or include angle brackets in the URL.

## 4. Relationship between multipart/related and inline resources

CID images are typically sent in a `multipart/related` MIME structure. This structure represents a group of interrelated parts: a root part, usually HTML, and the resources referenced by that HTML part.

Conceptual diagram:

~~~text
multipart/related
├── text/html
│   └── <img src="cid:brand-logo">
└── image/png
    ├── Content-ID: <brand-logo>
    └── Content-Disposition: inline
~~~

HTML is the primary content part; the image is a related resource. The Content-ID information allows the email client to match the HTML reference to the image data.

### 4.1. When both plain text and HTML are present

Transactional emails often want to provide a plain-text fallback alongside an HTML version with a logo. In that case, the structure can nest multipart containers:

~~~text
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html
│       └── <img src="cid:brand-logo">
└── image/png
    └── Content-ID: <brand-logo>
~~~

Depending on how the message is built and the multipart mode, the outer structure may differ or add `multipart/mixed` if the message also includes file attachments. What matters logically is that the HTML references an image within the same message and the image part carries the matching Content-ID.

`MimeMessageHelper` provides multipart modes to support common structures. For HTML with inline images and optional attachments, `MULTIPART_MODE_MIXED_RELATED` is typically an appropriate choice.

### 4.2. Inline vs. regular attachment

| Characteristic | Inline resource | Attachment |
| --- | --- | --- |
| Purpose | Displayed inside the body, typically referenced by HTML via CID | For the recipient to open or download as a file |
| Typical header | `Content-Disposition: inline` | `Content-Disposition: attachment` |
| HTML reference | `src="cid:..."` | Usually no reference needed |
| Spring API | `addInline(...)` | `addAttachment(...)` |
| Examples | Logo, in-email icons | PDF invoice, spreadsheet |

An inline part is still attached data in the message in the MIME sense, but its display role differs from a downloadable file attachment.

## 5. Using MimeMessageHelper.addInline(...)

In Spring Mail, `MimeMessageHelper` provides `addInline` overloads to add a resource to the message and attach a Content-ID to it.

Common usage forms:

~~~java
helper.addInline("brand-logo", resource);
~~~

or explicitly specifying the MIME content type:

~~~java
helper.addInline(
        "brand-logo",
        resource,
        "image/png"
);
~~~

The first argument is the **Content-ID** for the HTML to reference. The second argument is the content resource, typically a `Resource` or `InputStreamSource`. The third argument, when using the corresponding overload, is the MIME content type of the resource.

### 5.1. Creating the helper in multipart mode

Simple example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

The `true` parameter enables multipart mode. When you need explicit control over structures involving inline images, you can select the mode:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);
~~~

`MULTIPART_MODE_MIXED_RELATED` supports messages with related content and optional external attachments. For a simple HTML message with inline images, the standard multipart constructor is also usually sufficient.

### 5.2. Set HTML first, then add inline resources

Call order matters with `MimeMessageHelper`. You should **call `setText(...)` first, then call `addInline(...)`**:

~~~java
helper.setText(
        "<html><body>"
        + "<img src=\"cid:brand-logo\" alt=\"Logo\">"
        + "<p>Your order is confirmed.</p>"
        + "</body></html>",
        true
);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png"
);
~~~

If `addInline` is called before `setText`, certain body-setting operations may alter the multipart structure and affect previously added parts. Spring documentation recommends setting the text first and adding inline elements afterward to avoid compatibility issues.

### 5.3. Do not pass the cid: prefix to addInline

Correct example:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
~~~

Corresponding HTML:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Do not write:

~~~java
helper.addInline("cid:brand-logo", logoResource, "image/png");
~~~

Because `addInline` expects the **Content-ID**, whereas `cid:` is the URL scheme used by the HTML to reference it.

## 6. Complete example: sending an HTML email with an inline logo

Suppose the logo file is located at:

~~~text
src/main/resources/mail/images/logo.png
~~~

The application has the Spring Boot Mail starter and SMTP configured.

### 6.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

### 6.2. Mail sending service

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InlineImageMailService {

    private final JavaMailSender mailSender;

    public InlineImageMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(String recipient)
            throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient address must not be blank"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        String contentId = "brand-logo-" + UUID.randomUUID();

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject("Your order is confirmed");

        String html = """
                <html>
                  <body>
                    <div>
                      <img src="cid:%s"
                           alt="Company logo"
                           width="160">
                    </div>
                    <h2>Your order is confirmed</h2>
                    <p>Thank you for your purchase.</p>
                  </body>
                </html>
                """.formatted(contentId);

        // Set the body before adding inline resources.
        helper.setText(html, true);

        ClassPathResource logo =
                new ClassPathResource("mail/images/logo.png");

        helper.addInline(contentId, logo, "image/png");

        mailSender.send(message);
    }
}
~~~

This example assumes the logo actually exists on the classpath and `From` is permitted by the SMTP provider. `UUID.randomUUID()` prevents reusing the same ID across multiple sends. The CID is placed into the HTML and passed as the argument to `addInline`, so both sides always match.

### 6.3. What happens when sending?

1. `createMimeMessage()` creates a new message.
2. `MimeMessageHelper` is initialized in multipart mode.
3. The application generates a Content-ID for the image.
4. `setText(html, true)` sets the HTML body containing the `cid:...` URL.
5. `addInline(...)` adds the image bytes and the matching Content-ID header.
6. `JavaMailSender.send(message)` dispatches the message through the configured SMTP server.

When the email client processes the message, it searches for the image among the related MIME parts by Content-ID. If the image exists, the CID matches, and the client supports inline display, the logo can appear right inside the body.

## 7. Using Resources from classpath, filesystem, or memory

`addInline` needs a data source that Jakarta Mail can read when serializing the message. Spring provides useful `Resource` types.

| Source | Example | Best suited for |
| --- | --- | --- |
| `ClassPathResource` | `new ClassPathResource("mail/images/logo.png")` | Static images packaged with the application. |
| `FileSystemResource` | `new FileSystemResource(path)` | Files saved by the application at a controlled location. |
| `ByteArrayResource` | `new ByteArrayResource(imageBytes)` | Content already read and validated in memory. |
| `InputStreamSource` | A source creating a new stream on each call | Integrating custom re-readable data sources. |

### 7.1. ClassPathResource

This is a clean choice for logos or icons managed by the application:

~~~java
Resource logo =
        new ClassPathResource("mail/images/logo.png");

helper.addInline("brand-logo", logo, "image/png");
~~~

The path is resolved from the classpath, typically corresponding to a file under `src/main/resources` when running the project. Do not use a Windows path or an absolute path from a developer machine as the CID; Content-ID is unrelated to where the file lives on the server.

### 7.2. FileSystemResource

If the image lives outside the classpath, you can use `FileSystemResource`:

~~~java
Resource image =
        new FileSystemResource("/srv/app/mail/logo.png");

helper.addInline("brand-logo", image, "image/png");
~~~

The path is merely an example on a Linux environment. In a real application, the file must reside in a storage area the application is permitted to read. Never pass an arbitrary path directly from a request into `FileSystemResource`; validate access permissions and file storage location beforehand.

### 7.3. ByteArrayResource

If the image has already been read into a byte array and validated beforehand:

~~~java
byte[] imageBytes = loadApprovedImage();

Resource image = new ByteArrayResource(imageBytes);

helper.addInline("brand-logo", image, "image/png");
~~~

`ByteArrayResource` works well for bounded-size data that can be read repeatedly. Monitor size carefully to avoid holding large images in memory concurrently across many emails.

### 7.4. InputStreamSource must be re-readable

The MIME construction or sending process may read the data source more than once. Therefore, `InputStreamSource.getInputStream()` should supply **a new stream on every invocation**, if the source type supports it.

Do not open a single `InputStream`, drain it, and reuse it across multiple operations. Single-use stream resources can cause empty attachments or errors when the provider serializes the message.

Resources such as `ClassPathResource`, `FileSystemResource`, and `ByteArrayResource` are generally more suitable because their implementations can reopen the content.

## 8. Content-Type of inline images

Content-ID only identifies **which part** is referenced; Content-Type indicates **what kind of content that data is**.

Example:

| Image type | Content-Type |
| --- | --- |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| GIF | `image/gif` |
| SVG | `image/svg+xml` |

For common raster images like PNG or JPEG, declare the exact MIME type:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
~~~

If the file is actually JPEG but declared as `image/png`, the email client may fail to decode it properly. Do not rely solely on a user-supplied filename extension; the MIME type should be determined from verified content or from a trusted resource source.

### Do not trust client-declared Content-Type

When uploading a file, a client may send an inaccurate `Content-Type` header. If the application copies that value straight into the MIME part, it can misdescribe the data. Verify the file type using an appropriate mechanism, inspect the content, and accept only permitted types.

File identification by magic bytes also has limitations; it should be combined with file-type policies, size checks, and content scanning where appropriate.

## 9. Are CID URLs and Content-IDs public paths?

No. A CID only has meaning within the scope of the message containing that MIME part. For example, `cid:brand-logo` cannot be pasted into a browser to access an image on a website.

If a recipient forwards the email or a mail app archives the message, the inline resource may be preserved inside the forwarded message. However, a CID is not a durable address that external applications can access independently.

Distinguish between:

| Value | Can be opened directly in a browser? | Scope |
| --- | --- | --- |
| `https://cdn.example.org/logo.png` | Yes, if the server is public and reachable | Web resource |
| `cid:brand-logo` | Not as a standalone web URL | Current MIME message |
| `file:///srv/app/logo.png` | Not a valid URL for an email recipient to access server files | Local machine/host |
| `/static/logo.png` | Lacks host context for external recipients | Relative path |

Do not put local paths or relative URLs into an email's `src` attribute and expect recipients to see the file. Embed the resource via CID or use a public HTTPS URL aligned with your remote-image display policy.

## 10. CID, remote images, or attached images: which to choose?

There are three common ways to show images in emails:

| Approach | Where is the image data stored? | Advantages | Limitations |
| --- | --- | --- | --- |
| CID inline | Inside the MIME message | No need to fetch images from a website when opening mail; suited for logos/small images | Increases email size; requires MIME client support |
| HTTPS remote image | On a server/CDN | Smaller email; image can be updated on the server | Clients may block remote images; triggers a request when loaded |
| Regular attachment | Inside the message, attachment disposition | Recipient can download the file | Not necessarily displayed at a position inside the HTML |

CID is useful for **logos, icons, and small illustrations that need to travel with the content**. For large photos or frequently changing content, remote images from a CDN may be a better fit if privacy policies and target clients allow them. For PDFs or downloadable documents, use `addAttachment`.

Do not embed an entire photo gallery or large files into every email when the recipient only needs a small logo. Every inline image makes the message larger.

### 10.1. CID does not guarantee clients will always show images

Email clients may enforce their own policies: disabling images, restricting MIME types, or presenting inline content differently. Therefore, always provide a meaningful `alt` attribute:

~~~html
<img src="cid:brand-logo" alt="Company logo">
~~~

Important content should never exist solely inside images. For instance, order numbers, statuses, and instructions must appear as actual text in the body.

### 10.2. CID is not an absolute privacy protection mechanism

CID images are transmitted inside the message; recipients can save them. CID avoids a remote image-fetch request when opening the email, but it does not prevent recipients from sharing the message or extracting data. Do not place secrets or unnecessary personal data in inline images.

## 11. Multiple inline resources in the same message

An email may require a logo, a status icon, and a product image:

~~~java
String logoId = "logo-" + UUID.randomUUID();
String statusId = "status-" + UUID.randomUUID();
String productId = "product-" + UUID.randomUUID();

String html = """
        <html>
          <body>
            <img src="cid:%s" alt="Logo">
            <h2>Your order is confirmed</h2>
            <img src="cid:%s" alt="Confirmed">
            <p>Product:</p>
            <img src="cid:%s" alt="Product image">
          </body>
        </html>
        """.formatted(logoId, statusId, productId);

helper.setText(html, true);

helper.addInline(
        logoId,
        new ClassPathResource("mail/images/logo.png"),
        "image/png"
);

helper.addInline(
        statusId,
        new ClassPathResource("mail/images/confirmed.png"),
        "image/png"
);

helper.addInline(
        productId,
        productImageResource,
        "image/jpeg"
);
~~~

This example assumes `productImageResource` is already declared and is a re-readable resource. Each image has its own Content-ID, and each URL in the HTML references the exact ID of the corresponding image.

Manage IDs in variables or a small data structure instead of retyping strings in multiple places. This reduces typos and helps tests verify that every referenced CID has a matching MIME part.

## 12. Combining inline resources with a PDF attachment

An email can display an inline logo while also attaching a PDF invoice. Example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

String logoId = "logo-" + UUID.randomUUID();

helper.setFrom("billing@example.org");
helper.setTo(recipient);
helper.setSubject("Your invoice");

String html = """
        <html>
          <body>
            <img src="cid:%s" alt="Company logo" width="140">
            <h2>Your invoice is ready</h2>
            <p>Please see the attached PDF file.</p>
          </body>
        </html>
        """.formatted(logoId);

helper.setText(
        "Your invoice is ready. Please see the attached PDF file.",
        html
);

helper.addInline(
        logoId,
        new ClassPathResource("mail/images/logo.png"),
        "image/png"
);

helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf"
);

mailSender.send(message);
~~~

This example assumes `invoiceResource` is a valid `InputStreamSource`/`Resource` that is readable during sending and contains a generated, verified PDF. Choose the appropriate multipart mode and follow the order of setting text before inline resources.

Conceptual model:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │       └── <img src="cid:logo-id">
│   └── image/png
│       └── Content-ID: <logo-id>
└── application/pdf
    └── Content-Disposition: attachment
~~~

The exact MIME structure is constructed by the helper and Jakarta Mail. The diagram illustrates the roles of the parts: HTML references the inline image, while the PDF is a separate attachment.

## 13. Checking whether a message has the right Content-ID

In a development environment, you can inspect the headers of a MIME message:

~~~java
String[] contentIds = message.getHeader("Content-ID");
~~~

For multipart messages, the image's Content-ID lives on the **image part**, not necessarily at the outer message level. Therefore, calling only `message.getHeader("Content-ID")` is not enough to find all inline resources.

You can traverse the multipart structure using the Jakarta Mail API to inspect each part:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;

static void inspectParts(MimeMessage message)
        throws Exception {

    Object content = message.getContent();

    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            BodyPart part = multipart.getBodyPart(i);

            String contentType = part.getContentType();
            String disposition = part.getDisposition();
            String[] ids = part.getHeader("Content-ID");

            System.out.println("Part: " + contentType);
            System.out.println("Disposition: " + disposition);

            if (ids != null) {
                for (String id : ids) {
                    System.out.println("Content-ID: " + id);
                }
            }

            // A multipart can be nested inside another part.
            Object nested = part.getContent();
            if (nested instanceof Multipart nestedMultipart) {
                inspectMultipart(nestedMultipart);
            }
        }
    }
}

static void inspectMultipart(Multipart multipart)
        throws Exception {

    for (int i = 0; i < multipart.getCount(); i++) {
        BodyPart part = multipart.getBodyPart(i);

        System.out.println("Part: " + part.getContentType());

        String[] ids = part.getHeader("Content-ID");
        if (ids != null) {
            for (String id : ids) {
                System.out.println("Content-ID: " + id);
            }
        }

        Object nested = part.getContent();
        if (nested instanceof Multipart nestedMultipart) {
            inspectMultipart(nestedMultipart);
        }
    }
}
~~~

This is an illustrative inspection example that can be simplified depending on the actual structure; in production code, avoid repeatedly reading entire streams or printing sensitive content. Verification should confirm:

- The HTML contains the expected CID.
- A MIME part exists with the matching Content-ID.
- The part's MIME type is the expected image type.
- The disposition matches the inline intent.
- The resource has data and can be serialized.

Do not rely on whether an outer-level header has Content-ID to conclude that the inline image was added properly.

## 14. Common errors when using cid URLs and Content-ID

### 14.1. Mismatch between Content-ID and cid URL

**Wrong:**

~~~java
helper.addInline("brand-logo", logo, "image/png");
~~~

~~~html
<img src="cid:company-logo" alt="Logo">
~~~

The two IDs differ, so the client cannot find the image. Use the same `contentId` variable for both the HTML and `addInline`.

### 14.2. Passing cid: into the addInline argument

**Wrong:**

~~~java
helper.addInline("cid:brand-logo", logo, "image/png");
~~~

**Correct:**

~~~java
helper.addInline("brand-logo", logo, "image/png");
~~~

`cid:` belongs to the URL in HTML; the helper parameter is the Content-ID.

### 14.3. Putting angle brackets in src

**Wrong:**

~~~html
<img src="cid:<brand-logo>" alt="Logo">
~~~

**Correct:**

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Angle brackets appear in the Content-ID header as `<brand-logo>`; do not copy the raw header syntax into the cid URL.

### 14.4. Calling addInline before setText

Setting the body after adding inline resources can alter the multipart structure and prevent the inline part from being preserved as expected.

**Solution:** call `setText(...)` first, then `addInline(...)`, and finally send the message.

### 14.5. Not enabling multipart

If the helper is created in non-multipart mode:

~~~java
new MimeMessageHelper(message, false, "UTF-8");
~~~

then adding an inline resource does not fit the required message structure and can throw an error. Enable multipart or choose an explicit multipart mode.

### 14.6. Confusing attachments with inline resources

Using `addAttachment` creates a downloadable file attachment, which is not the proper way for HTML to reference an image via CID. Use `addInline` for resources referenced by the body.

### 14.7. Incorrect MIME type

A PNG file declared as `image/jpeg` can cause clients to decode it incorrectly. Determine the MIME type from verified content rather than blindly trusting client upload metadata.

### 14.8. Resource is no longer readable

A `Resource` might exist when creating the message but become unavailable when Jakarta Mail serializes it. Use a resource with a clear lifecycle and re-readability; handle I/O errors in the sending workflow.

### 14.9. Using a single-use InputStream

A stream that has already been drained cannot automatically rewind. Use a resource that can open a fresh stream, such as `ClassPathResource` or `ByteArrayResource`, or an `InputStreamSource` implemented to return a new stream each time.

### 14.10. Duplicate CIDs across multiple images

If multiple parts share the same Content-ID, reference resolution can become ambiguous. Generate a unique ID for each image in the message and use a single source of truth to build both the HTML and the inline resource list.

### 14.11. Oversized images

Inline images increase message size; binary data transferred through MIME may be Base64-encoded, making the transmitted payload larger than the original file. Resize and optimize images before sending, and respect provider limits.

### 14.12. Expecting images to always display in all email clients

Clients may disable images, lack support for a format, or present them differently. Include `alt` text, keep important information in text, and test across target mail applications.

## 15. Testing emails with inline resources

You can test at multiple layers without sending real mail out to the Internet.

### 15.1. Unit testing message construction

Replace `JavaMailSender` with a mock/fake to capture the generated `MimeMessage` and assert:

- Subject, From, and To are set properly.
- The HTML body contains `src="cid:..."`.
- The image MIME part has a Content-ID matching the value in HTML.
- Content-Type is `image/png` or the expected type.
- The message is built in multipart mode.

For nested multipart messages, tests should traverse parts rather than assuming the image always resides at a fixed index in the outer multipart.

### 15.2. Integration testing with an SMTP test server

An SMTP server used for testing can receive emails and let you inspect the raw MIME. This is a good way to verify:

- MIME boundaries are generated properly.
- `Content-ID` is on the image part.
- `Content-Disposition` reflects inline intent.
- The HTML references the right cid URL.
- The image has valid data bytes and the proper content type.

The SMTP test server should be configured specifically for the test environment, never using production credentials and never forwarding test mail to real recipients.

### 15.3. Checking on email clients

After verifying the MIME, open test messages on target clients. Check that the logo renders at the right size, alt text is meaningful, the layout does not rely solely on images, and other attachments still work.

A message that is structurally valid in MIME does not guarantee every client will render it the same way. Visual testing remains necessary when images play an important role.

## 16. Privacy and performance of inline resources

Inline CID has several operational characteristics to consider:

- **Size:** images are sent in every email; sending the same logo to thousands of recipients multiplies transmitted volume by the message count.
- **Memory:** when building many messages in parallel, image bytes and MIME payloads can consume significant memory.
- **Caching:** inline images belong to each individual message; there is no shared CDN caching mechanism like with remote URLs.
- **Privacy:** avoids triggering remote image-load requests upon opening mail the way remote images typically do, though the email itself still contains the image and recipients can extract it.
- **Displayability:** clients may still block or withhold images due to their own policies.
- **Licensing and data:** only embed images the application is licensed to use and that are appropriate for the recipient.

For small shared logos, CID is often convenient. For large product photos, animations, or galleries, consider CDN URLs and a remote-image loading policy rather than embedding everything inside the message.

## 17. Practice questions

**Question 1.** If you call `helper.addInline("brand-logo", logo, "image/png")`, how should the HTML reference it?

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

The value after `cid:` must match the Content-ID created by the helper.

**Question 2.** Should you pass `cid:brand-logo` to `addInline`?

No. `addInline` takes the Content-ID, while the `cid:` prefix only appears in the URL inside the HTML body.

**Question 3.** Why is the header `Content-ID: <brand-logo>` while the HTML is `cid:brand-logo`?

MIME headers represent Content-ID inside angle brackets. The cid URL references the ID without putting the angle brackets into the URL.

**Question 4.** Can you put `src="/images/logo.png"` in an email so recipients load the image from the Spring app?

You should not. A relative path has no website host for external recipients. Use CID or an absolute HTTPS URL managed by the application.

**Question 5.** Can you call `addAttachment("logo.png", logo)` and then reference `cid:logo`?

Not automatically. Regular attachments do not establish the corresponding CID contract. Use `addInline` and reference the matching Content-ID.

**Question 6.** Why should `setText` be called before `addInline`?

Because the helper organizes the multipart structure when setting the body. Adding inline resources after the body is set prevents text-setting operations from altering the structure holding those resources.

**Question 7.** An email has a logo and a status icon. Can the two images share the same Content-ID?

No. Each inline part needs its own ID so the URL reference is unambiguous.

**Question 8.** Is `cid:brand-logo` a URL that can be opened in a browser?

No. It references a MIME part inside the current message, not a standalone web resource.

**Question 9.** Does setting `Content-Type: image/png` guarantee the data is a PNG?

No. The header only describes the content type. The application must validate the image bytes or obtain the data from a trusted source before declaring it.

**Question 10.** Does `send(...)` returning normally prove that the recipient sees the logo?

No. It only reflects that the send operation was accepted by the SMTP relay based on the response received. Display also depends on the actual MIME, the client, and image-display policies.

## 18. Mental model

To send inline images in Spring Framework Mail, connect three parts:

~~~mermaid
flowchart TD
    A["HTML body"] --> B["src = cid:logo-id"]
    C["MimeMessageHelper.addInline"] --> D["Content-ID: <logo-id>"]
    D --> E["MIME part image/png"]
    B --> F["Email client matches CID with MIME part"]
    E --> F
    G["JavaMailSender.send(message)"] --> F
~~~

Key principles:

1. **Content-ID identifies the MIME part** containing the inline image or resource.
2. **The cid URL references the Content-ID** from HTML; the value after `cid:` must match the added ID.
3. **`addInline` takes the ID, not the `cid:` prefix**; the helper is responsible for creating the Content-ID header.
4. **The message needs appropriate multipart mode.** For inline resources, enable multipart and choose the right mode.
5. **Set the body first, then add inline resources.** Use `setText(...)` before `addInline(...)`.
6. **The resource must be readable during serialization.** Prefer sources that can open new streams, declare the right Content-Type, and control size.
7. **Inline is not the same as a regular attachment.** Use `addInline` for images referenced by HTML; use `addAttachment` for downloadable files.
8. **CID is not a public URL.** It only has meaning inside the message containing the MIME part.
9. **Do not rely solely on images.** Provide alt text and express important information as text.
10. **Test both MIME and real clients.** Verify Content-ID, cid URL, MIME type, image data, and actual display.

In a Spring email, `MimeMessageHelper` links the HTML body with inline resources; Jakarta Mail packages the parts inside a MIME structure; `JavaMailSender` sends the entire message over SMTP. When the Content-ID and cid URL match, the email client can locate the embedded image and display it at the intended position within the HTML content.

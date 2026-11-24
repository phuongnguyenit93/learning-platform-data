# Order of Creating HTML and Adding Resources

## 1. What is an inline resource in an HTML email?

In **Spring Framework Mail**, an application can send HTML emails containing logos, icons, signature images, or illustrations displayed directly inside the body. These resources are commonly called **inline resources**: the image is packaged as a separate MIME body part, and the HTML references that part using a **Content-ID (CID)** address.

Example HTML:

~~~html
<img src="cid:company-logo" alt="Company logo">
~~~

When creating the MIME message, the application needs to add an image part with a Content-ID matching `company-logo`. The email client combines the HTML part with the image part to display the image directly inside the message body.

~~~text
HTML Email
   |
   | <img src="cid:company-logo">
   |
   v
MIME message
   |
   +-- text/html body part
   |      |
   |      +-- references cid:company-logo
   |
   +-- image/png body part
          |
          +-- Content-ID: <company-logo>
          +-- Content-Disposition: inline
          +-- image data
~~~

The key point of this lesson is the **order of operations when using MimeMessageHelper**:

1. Build the HTML string containing the `cid:...` references.
2. Call `MimeMessageHelper.setText(...)` to set the HTML body (and text/plain if applicable).
3. Call `MimeMessageHelper.addInline(...)` to add the resources referenced by the HTML.
4. If there are downloadable attachments, add them with `addAttachment(...)`.
5. Send the message using `JavaMailSender`.

Spring's API documentation emphasizes **calling addInline after setText**. If inline resources are added before setting the body, some mail readers may fail to resolve CID references properly because the multipart structure was not initialized in the expected order.

## 2. Distinguishing inline resources and attachments

Both inline resources and attachments are MIME body parts, but their display purposes differ:

| Characteristic | Inline resource | Attachment |
|---|---|---|
| Purpose | Displayed directly inside the HTML body | For the recipient to download or open separately |
| HTML reference | Typically uses `src="cid:..."` | No HTML reference needed |
| Content-ID | Present so HTML links to the part | Usually not needed |
| Content-Disposition | Typically `inline` | Typically `attachment` |
| Spring API | `addInline(...)` | `addAttachment(...)` |
| Examples | Logo, signature image, embedded diagram | PDF invoice, Excel file, document |

An image added with `addAttachment("logo.png", resource)` does not automatically become an image rendered inside the HTML. Conversely, an image added with `addInline("company-logo", resource)` does not necessarily appear as a regular attachment in every email client.

If an email includes both a logo displayed in the body and a PDF for the recipient to download, create **two separate parts**: an inline image with a CID and an attachment with a filename.

## 3. Why must setText be called before addInline?

`MimeMessageHelper` does more than assign an HTML string to a field. When working in multipart mode, the helper creates and manages the MIME tree, including content parts and related resources.

When `setText(html, true)` is called first, the helper already knows the HTML body and can set up the related MIME section. Then `addInline(...)` attaches the image part into the appropriate multipart region so clients can resolve `cid:` references.

Recommended order:

~~~text
Create MimeMessage
      |
      v
Create MimeMessageHelper (multipart = true)
      |
      v
Build HTML String containing cid:logo
      |
      v
helper.setText(html, true)
      |
      v
helper.addInline("logo", logoResource)
      |
      v
mailSender.send(message)
~~~

Example of an order to avoid:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addInline("logo", logoResource); // Called too early
helper.setText(html, true);
~~~

Do not rely on a specific email client still displaying the image when the order is reversed. Follow the sequence recommended by Spring so the MIME structure stays consistent.

**Note:** The HTML string must be constructed before `setText` because it contains the CIDs that the body references. However, **attaching the resource to the MimeMessage** via `addInline` must happen after `setText` has been called.

## 4. Complete example: HTML referencing a logo via CID

Suppose the logo is packaged on the classpath:

~~~text
src/main/resources/
└── mail/
    └── images/
        └── company-logo.png
~~~

Service that builds the email:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class BrandedMailService {
    private final JavaMailSender mailSender;

    public BrandedMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name());

        String html = """
                <!doctype html>
                <html lang="en">
                  <head><meta charset="UTF-8"></head>
                  <body>
                    <div>
                      <img src="cid:company-logo"
                           alt="Company logo"
                           width="160">
                    </div>
                    <h1>Welcome!</h1>
                    <p>Your account is ready.</p>
                  </body>
                </html>
                """;

        helper.setFrom("welcome@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome to our service");

        // 1. Set the HTML content first.
        helper.setText(html, true);

        // 2. Then add the resource referenced by the HTML.
        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/company-logo.png"));

        mailSender.send(message);
    }
}
~~~

In this example:

- `true` in `MimeMessageHelper` enables multipart mode.
- The HTML uses `src="cid:company-logo"`.
- `addInline("company-logo", ...)` uses the same ID, without the `cid:` prefix.
- `ClassPathResource` reads the image packaged inside the application.
- `setText(...)` is called before `addInline(...)`.

**The Content-ID must match exactly** between the HTML and the `contentId` parameter passed to the helper. If the HTML references `cid:company-logo` while the code calls `addInline("logo", ...)`, the email client cannot find the matching part and the image may be missing.

## 5. Order when the email has text/plain, HTML, and inline images

HTML emails should usually include a **text/plain** version to support email clients that do not render HTML. When calling `MimeMessageHelper.setText(plainText, htmlText)`, the helper creates alternative parts for the same content.

Example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String plainText = """
        Hello!
        This is a notification regarding your account.
        """;

String htmlText = """
        <html lang="en">
          <body>
            <img src="cid:brand-mark" alt="Brand">
            <h1>Hello!</h1>
            <p>This is a notification regarding your account.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
helper.addInline(
        "brand-mark",
        new ClassPathResource("mail/images/brand-mark.png"));
~~~

The order remains:

1. Prepare both the plain-text and HTML strings.
2. Call `setText(plainText, htmlText)`.
3. Call `addInline(...)` for each resource referenced by the HTML.
4. Send the message.

Inline images are referenced only from the HTML body. The text/plain version does not need and should not contain `cid:` URIs as if they were ordinary text links.

### Conceptual MIME structure

With multipart alternative and inline resources, the MIME tree may nest multiple layers:

~~~text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     |
  |     |     +-- text/plain
  |     |     +-- text/html
  |     |
  |     +-- image/png
  |           Content-ID: <brand-mark>
  |
  +-- application/pdf
        Content-Disposition: attachment
~~~

This is a conceptual diagram of MIME relationships. The exact nesting depends on the multipart mode and how the helper builds the message; do not write tests assuming every part always sits at the same index in the outermost multipart.
## 6. Adding multiple inline resources

An email can contain multiple images: header logo, product photo, social icons, and signature. Each resource has its own Content-ID, and the HTML must reference the matching ID.

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String html = """
        <html lang="en">
          <body>
            <img src="cid:brand-logo" alt="Brand" width="140">
            <h1>Your order</h1>
            <img src="cid:product-photo"
                 alt="Product photo"
                 width="240">
            <p>
              <img src="cid:support-icon"
                   alt=""
                   width="20">
              Contact support if you need help.
            </p>
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/brand-logo.png"));
helper.addInline(
        "product-photo",
        new ClassPathResource("mail/images/product-photo.jpg"));
helper.addInline(
        "support-icon",
        new ClassPathResource("mail/images/support-icon.png"));

mailSender.send(message);
~~~

The order stays the same: **setText first, all addInline calls after**. You do not need to call setText again after each image. When adding a new resource, also add the HTML tag referencing its matching CID.

ID management rules:

- Each distinct image payload should have its own Content-ID in the message.
- If the same image is used multiple times in the HTML, you can reuse the same CID so those locations reference the same part.
- Never use one CID for two different images in the same message.
- IDs should be simple, stable within the message, and free of spaces or special characters.
- Do not put filenames or filesystem paths into CIDs; a CID is a MIME identifier, not a file-read path.

## 7. Using dynamic Content-IDs when rendering HTML from templates

With a template engine, CIDs can be generated in code and passed into the model. What matters is that **the exact same value** is used in both places:

1. The HTML produces `src="cid:<id>"`.
2. `addInline("<id>", resource)` uses that exact `<id>`.

Example with a fixed CID:

~~~java
String logoCid = "brand-logo";
String html = """
        <html><body>
          <img src="cid:%s" alt="Brand">
        </body></html>
        """.formatted(logoCid);

helper.setText(html, true);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/images/brand-logo.png"));
~~~

If multiple emails are built independently, you can use a unique ID per message:

~~~java
import java.util.UUID;

String logoCid = "logo-" + UUID.randomUUID();
String html = """
        <html><body>
          <img src="cid:%s" alt="Brand">
        </body></html>
        """.formatted(logoCid);

helper.setText(html, true);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/images/brand-logo.png"));
~~~

Dynamic CIDs are not mandatory if messages are isolated and fixed IDs do not cause collisions. The advantage of dynamic IDs is reducing the risk of two parts accidentally sharing a Content-ID when a message is assembled from multiple modules or template fragments.

### Example with Thymeleaf

The template can accept a CID variable:

~~~html
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<body>
  <img th:src="'cid:' + ${logoCid}"
       alt="Brand"
       width="140">
  <h1 th:text="${title}">Notification</h1>
</body>
</html>
~~~

The renderer sets the variable and builds the HTML first:

~~~java
String logoCid = "brand-logo";

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("logoCid", logoCid);
context.setVariable("title", "Welcome!");

String html = templateEngine.process("mail/welcome", context);

helper.setText(html, true);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/images/brand-logo.png"));
~~~

**Do not add inline resources before rendering or before setText.** You can prepare the Resource object early, but attaching it to the MimeMessage via addInline must happen only after setText. This keeps the code reflecting the proper order and easier to read when a template has many CIDs.

## 8. Choosing the right Resource

Spring provides several Resource types to read image content. Choose based on storage location and data lifecycle:

| Resource | Data source | Suitable use case |
|---|---|---|
| `ClassPathResource` | File packaged in classpath/JAR | Fixed logos, icons, or brand graphics |
| `FileSystemResource` | File on the filesystem | Images stored in an application-managed directory |
| `ByteArrayResource` | Byte array in memory | Images already loaded/transformed with bounded size |
| `InputStreamSource` | Supplies stream on demand | Integrating data sources capable of reopening streams |

### ClassPathResource

~~~java
Resource logo = new ClassPathResource("mail/images/logo.png");
helper.addInline("logo", logo);
~~~

Classpath paths generally do not have a leading slash. The resource is read from the classpath and continues to work when the application is packaged as a JAR, without assuming a physical file exists in the working directory.

### FileSystemResource

~~~java
Resource chart = new FileSystemResource(
        "/var/app/mail-assets/monthly-chart.png");
helper.addInline("monthly-chart", chart);
~~~

The filesystem path must exist and the runtime must have read permissions. In containers, this path must be mounted or created inside the container filesystem. Never take a user-submitted path directly and open it arbitrarily; restrict access to directories managed by the application.

### ByteArrayResource

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] imageBytes = imageService.createSmallPreview();
helper.addInline(
        "preview-image",
        new ByteArrayResource(imageBytes),
        "image/png");
~~~

ByteArrayResource is suitable when the image is already available as a byte array and its size is controlled. For large images, holding all bytes on the heap can increase memory pressure; prefer file-backed Resources or a re-openable stream source.

### InputStreamSource must be able to open streams properly

The overload taking InputStreamSource requires the source to supply a stream for the library to read. Some serialization flows may need to open the stream more than once. Therefore, the source should create a **new InputStream on each getInputStream() call**; never reuse a drained or closed stream.

~~~java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

byte[] imageBytes = imageService.createSmallPreview();
InputStreamSource source =
        () -> new ByteArrayInputStream(imageBytes);

helper.addInline("preview-image", source, "image/png");
~~~

This example keeps the byte array in memory while creating a fresh stream on each request. For file sources, ClassPathResource or FileSystemResource is usually clearer and more convenient.

**Avoid InputStreamResource backed by a single already-opened InputStream** if the library may read the resource multiple times. A one-shot source may already be exhausted or closed on the next read, causing errors during message serialization.

## 9. Specifying the right Content-Type for resources

Inline images need the proper media type, such as:

| Format | Content-Type |
|---|---|
| PNG | `image/png` |
| JPEG/JPG | `image/jpeg` |
| GIF | `image/gif` |
| SVG | `image/svg+xml` |
| WebP | `image/webp` |

For overloads taking a Resource, the helper usually infers the content type from the filename or FileTypeMap. For uncommon formats or sources without a reliable filename, provide the content type explicitly:

~~~java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

Do not declare a JPEG image as image/png simply because the file ends with .png; the content type must reflect **the actual byte format**. If the header says image/png while the data is JPEG, some clients may fail to display the image.

### SVG and compatibility

SVG is a vector image format, but SVG support across email clients is uneven. Some clients block or do not render inline SVGs for security or compatibility reasons. For emails that need broad display support, PNG or JPEG are usually safer choices. If using SVG, test on target clients and avoid embedding scripts or untrusted content.

### Resources are not HTML fragments

`addInline` is meant for resource payloads such as images, not as a way to inject an HTML snippet into the body. To include HTML content, render it into the HTML string before calling setText; only binaries/resources referenced by CID should be added via addInline.
## 10. Combining inline images and attachments in the same email

A confirmation email can display a logo inside the HTML and attach a PDF invoice. Be sure to distinguish them clearly:

- Logo: referenced by HTML via CID, added with `addInline`.
- PDF invoice: downloaded by the recipient, added with `addAttachment`.

Example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String html = """
        <html lang="en">
          <body>
            <img src="cid:invoice-brand" alt="Company" width="140">
            <h1>Your invoice</h1>
            <p>The PDF invoice is attached to this email.</p>
          </body>
        </html>
        """;

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Electronic invoice");

// Set the body first.
helper.setText(html, true);

// Add the inline resource referenced by HTML.
helper.addInline(
        "invoice-brand",
        new ClassPathResource("mail/images/invoice-brand.png"));

// Add the file for the recipient to download.
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource("/var/app/invoices/invoice-2026-001.pdf"));

mailSender.send(message);
~~~

`addAttachment` can be called after setting the content and inline resources. The attachment filename is display metadata for the recipient; it is not a Content-ID and must not be used in `src="cid:..."`.

For messages with multiple part types, the helper creates a multipart structure separating related content from file attachments. Let the helper manage that structure unless your application has special MIME requirements needing direct Jakarta Mail usage.

## 11. Render HTML from templates before attaching resources

In real applications, HTML usually comes from Thymeleaf, FreeMarker, or another template engine. Processing order should split into two phases:

1. **Render content**: build the complete HTML string with image tags already carrying CIDs.
2. **Compose MIME**: call setText with the rendered HTML, then addInline each resource by CID.

Example with a renderer:

~~~java
public record InlineImage(
        String contentId,
        org.springframework.core.io.Resource resource,
        String contentType) {
}

public record RenderedMail(
        String subject,
        String html,
        java.util.List<InlineImage> inlineImages) {
}
~~~

The renderer can return both the HTML and the list of resources to attach:

~~~java
public RenderedMail renderWelcome(String customerName) {
    String logoCid = "welcome-logo";

    Context context = new Context(Locale.forLanguageTag("vi-VN"));
    context.setVariable("customerName", customerName);
    context.setVariable("logoCid", logoCid);

    String html = templateEngine.process("mail/welcome", context);

    InlineImage logo = new InlineImage(
            logoCid,
            new ClassPathResource("mail/images/logo.png"),
            "image/png");

    return new RenderedMail(
            "Welcome",
            html,
            java.util.List.of(logo));
}
~~~

The mail composer consumes the result:

~~~java
public void sendRendered(
        String recipient,
        RenderedMail rendered) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, true, StandardCharsets.UTF_8.name());

    helper.setFrom("welcome@example.com");
    helper.setTo(recipient);
    helper.setSubject(rendered.subject());

    // Phase 1: build the MIME body from rendered HTML.
    helper.setText(rendered.html(), true);

    // Phase 2: attach all inline resources after setText.
    for (InlineImage inlineImage : rendered.inlineImages()) {
        helper.addInline(
                inlineImage.contentId(),
                inlineImage.resource(),
                inlineImage.contentType());
    }

    mailSender.send(message);
}
~~~

The two records are application-defined DTOs, not built-in Spring types. This design keeps the template renderer unaware of MimeMessageHelper, while the mail composer does not have to parse HTML tags to guess which images to attach.

### Verifying the contract between template and resource list

If the template references `cid:welcome-logo` yet the renderer fails to include a resource with Content-ID `welcome-logo` in the list, the email may send successfully without displaying the image. Conversely, having a resource in the list that is never referenced by the HTML bloats the message for no benefit.

In tests, you can check:

- Every CID in the template has a matching resource.
- No two distinct resources share the same CID.
- No unused resources are included if policy requires size optimization.
- Each MIME part has a Content-Type matching its image bytes.

This is a contract between the **template** and the **mail composer**; SMTP servers do not typically verify that every CID in HTML has a matching image part.

## 12. Common errors when order or CID is wrong

| Symptom | Possible cause | Resolution |
|---|---|---|
| Email sends successfully but image is missing | CID in HTML mismatches contentId | Use the exact same ID in src and addInline |
| Image appears as a standalone attachment | Used addAttachment instead of addInline | Switch to addInline for images shown inside HTML |
| Image disappears when calls are reordered | addInline called before setText | Call setText first, then addInline |
| IllegalStateException on addInline | Helper created in non-multipart mode | Create MimeMessageHelper with multipart=true or proper mode |
| ResourceNotFoundException/IOException | Wrong classpath/filesystem path or missing read permission | Check resource path and runtime permissions |
| Image has right name yet does not display | Content-Type mismatches byte format | Specify exact image/png, image/jpeg, etc. |
| Image shows only inside IDE | File outside classpath when packaged as JAR | Put image under resources and use ClassPathResource |
| Email is unusually large | Oversized image or same image embedded multiple times | Resize/compress and reuse CIDs appropriately |
| Template has CID but part is missing | Renderer forgot to add resource to list | Check template-to-resource mapping |
| Images mixed up across messages | Reusing mutable MimeMessage or faulty resource mapping | Create a separate message and mapping per email |

### Common ordering mistake

Avoid:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addInline("logo", logoResource);
helper.setText(html, true);
~~~

Recommended:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(html, true);
helper.addInline("logo", logoResource);
~~~

The difference is when the helper creates the multipart body. Following Spring's guidance, inline resources must be added **after the text body has been set** so mail readers can resolve CIDs properly.

## 13. Inspecting the MIME message without sending via SMTP

When images fail to display, you can inspect the built message before calling JavaMailSender.send. Use Jakarta Mail to examine MIME parts and Content-IDs:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;
import jakarta.mail.Session;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String html = """
        <html><body>
          <img src="cid:test-logo" alt="Logo">
        </body></html>
        """;

helper.setText(html, true);
helper.addInline(
        "test-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

message.saveChanges();

ByteArrayOutputStream output = new ByteArrayOutputStream();
message.writeTo(output);

Session session = Session.getInstance(new Properties());
MimeMessage parsed = new MimeMessage(
        session,
        new ByteArrayInputStream(output.toByteArray()));

Object content = parsed.getContent();
if (content instanceof Multipart multipart) {
    // Traverse body parts and locate the part with Content-ID.
}
~~~

This example serializes and re-parses the message to verify the **actual MIME**, not merely helper invocations. For nested multipart messages, traverse recursively:

~~~java
static void inspectPart(Part part) throws Exception {
    String[] contentIds = part.getHeader("Content-ID");
    if (contentIds != null) {
        System.out.println("Content-ID: " + contentIds[0]);
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            inspectPart(multipart.getBodyPart(i));
        }
    }
}
~~~

Invoke:

~~~java
inspectPart(parsed);
~~~

This inspection snippet only illustrates traversing parts and printing Content-IDs in a test environment. Never log full email bodies or sensitive data in production logs. When verifying the image part, you can also check isMimeType("image/png"), Content-Disposition, and Content-ID after parsing.

**Do not assume the image part sits at a fixed index.** When a message has text/plain, text/html, inline images, and attachments, MIME can nest multiple multiparts. Traversing recursively or searching by media type/Content-ID is far more reliable.
## 14. CID inline images or external URL images?

There are two common ways for HTML emails to display images:

1. **CID inline image**: the application packages the image as a MIME part and HTML references it with `cid:...`.
2. **Remote image**: HTML references the HTTPS URL of an image on an external server.

| Criterion | CID inline | Remote image URL |
|---|---|---|
| Image data | Stored inside email MIME | Fetched from a server when client renders |
| Requires addInline | Yes | No |
| Email size | Increases with image size and transfer encoding | Smaller because it only holds a URL |
| Network needed when opening | No need to download image from external website | Requires client access to the URL |
| Privacy | Does not trigger image-fetch requests to image server on open | May expose open time, IP, or request details |
| Displayability | Depends on email client's CID support | Remote images may be blocked by client policy |

Remote image:

~~~html
<img src="https://cdn.example.com/mail/logo.png"
     alt="Company"
     width="140">
~~~

CID image:

~~~html
<img src="cid:company-logo"
     alt="Company"
     width="140">
~~~

Remote images keep emails lighter, though recipients may have to allow loading external images. Image-fetch requests can also be used to track opens; consider privacy and organizational policies. CID images increase MIME size, yet do not depend on an image server when opening the email.

**No approach guarantees every email client will show images.** Clients can hide inline images, restrict image types, or enforce their own security policies. For logos or important graphics, provide alt text and ensure essential information remains readable when images do not display.

### Do not use data URIs as a universal alternative

Some web pages embed images directly using data URI URLs:

~~~html
<img src="data:image/png;base64,..." alt="Logo">
~~~

Data URI support across email clients is inconsistent; many clients strip or refuse to display them. With Spring Mail, when embedded images with better compatibility are needed, use CID and addInline via the MIME structure.

### Prefer img tags for inline images

Images in CSS backgrounds, pseudo-elements, or complex CSS layouts may not be supported consistently by email clients. For logos, icons, or product photos, an `img` tag with `src="cid:..."`, `alt`, and explicit dimensions is usually much more compatible.

## 15. Optimizing image size and display

Inline resources are packaged inside the MIME message, so image bytes increase email size. Binary data is typically transfer-encoded, such as Base64, making the transmitted payload larger than the original image file.

Recommended practices:

- Resize images to their actual display dimensions; do not embed a 4000-pixel image if the email displays it 140 pixels wide.
- Compress PNG/JPEG appropriately for the content; flat logos suit optimized PNG, while photographs generally suit JPEG.
- Avoid embedding multiple copies of the same image under different CIDs if they can reference the same part.
- Only add resources actually used by the HTML.
- Use meaningful alt text for informative images; decorative images can use empty alt text.
- Declare reasonable width/height so the layout shifts less whether images load or are blocked.
- Check the total MIME size of the entire message, including body, inline resources, and attachments.

Decorative image example:

~~~html
<img src="cid:divider-image" alt="" width="600">
~~~

Informative image example:

~~~html
<img src="cid:product-photo"
     alt="White mechanical keyboard"
     width="240">
~~~

If images are hidden, alt text helps recipients understand the content. For decorative images, empty alt prevents screen readers from announcing an unnecessary filename or description.

### Image size and email limits

Suppose an email has an 80 KB logo, a 450 KB product photo, and a 2 MB PDF attachment. The sum of raw source bytes is not the final email size: images and PDFs may be Base64-encoded, and MIME also adds headers, boundaries, text bodies, and other parts. Always leave headroom below provider limits.

Do not check only the size of each individual inline file. A template with many small images or a loop generating images per item can still push the total message past the limit.

## 16. Securing paths and resource sources

Inline resources typically come from the classpath, filesystem, or storage. Ensure the application attaches only resources it is authorized to read and send:

- **Never use user-supplied paths directly** to construct a FileSystemResource; doing so can allow reading files outside permitted directories.
- If users select images, store them in managed storage and map via validated IDs instead of trusting client-sent paths.
- For images fetched from URLs, validate scheme, hostname, IP address, and redirects per policy; never fetch arbitrary URLs from requests due to SSRF risk.
- Enforce file size limits, true MIME types, and resource counts.
- Never allow arbitrary SVG/HTML content to execute in an email context without proper sanitization.
- Never log image bytes, storage access tokens, or signed URLs containing secrets.

Unsafe example:

~~~java
// Never take an arbitrary filesystem path from a request.
Resource image = new FileSystemResource(request.imagePath());
helper.addInline("user-image", image);
~~~

A safer design is to accept an **asset ID**, verify access permissions, and then retrieve the Resource from a managed service:

~~~java
Resource image = assetService.getReadableInlineImage(
        authenticatedUser,
        request.assetId());

helper.setText(html, true);
helper.addInline("user-image", image, "image/png");
~~~

The method and service names in the example are application-defined abstractions. What matters is that authorization checks and data-source restrictions happen **before the resource is attached to the email**.

## 17. Testing call order and Content-IDs

Tests for inline resources should verify at least three things:

1. The HTML body is set and contains the referenced CID.
2. The MIME message has a resource part with the matching Content-ID.
3. The part has a Content-Type matching the image content.

One way to test is to create a MimeMessage in memory, serialize it, and parse it back. No SMTP server is needed:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

class InlineResourceMimeTest {
    @Test
    void containsHtmlReferenceAndMatchingInlinePart() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setText(
                "<html><body><img src=\"cid:test-logo\" "
                        + "alt=\"Logo\"></body></html>",
                true);
        helper.addInline(
                "test-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        message.saveChanges();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        message.writeTo(output);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(output.toByteArray()));

        assertThat(parsed.getContent()).isInstanceOf(Multipart.class);
        assertThat(findPart(parsed, "test-logo", "image/png"))
                .isTrue();
    }

    private static boolean findPart(
            Part part,
            String expectedContentId,
            String expectedMimeType) throws Exception {
        String[] ids = part.getHeader("Content-ID");
        if (ids != null && ids.length > 0
                && ids[0].contains(expectedContentId)
                && part.isMimeType(expectedMimeType)) {
            return true;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                if (findPart(child, expectedContentId, expectedMimeType)) {
                    return true;
                }
            }
        }
        return false;
    }
}
~~~

This test assumes the test image file exists on the classpath at `mail/images/logo.png`. It checks the message after serialization/parsing, so it can catch cases where the helper fails to create the expected inline part. The lookup method traverses nested multiparts rather than relying on a fixed index.

If you only mock JavaMailSender and verify `send(message)`, that test does not prove Content-IDs and MIME parts are valid. Inspect the built MimeMessage or use an SMTP test server when you need to verify the full protocol output.

### Checking how many times resources are added

For templates with multiple images, you can use a test model listing expected resources and assert that every CID appearing in the HTML has exactly one MIME part. If the same CID is referenced multiple times in HTML, only one matching part is needed; if two distinct resources use the same CID, the test should fail.

## 18. Operational checklist when building emails with inline resources

The sequence below is an easy-to-read, error-resistant implementation pattern:

1. Prepare business data and verify access rights for each image.
2. Select resources from the classpath or managed storage.
3. Generate a unique Content-ID for each distinct image in the message.
4. Render the HTML with image tags using `src="cid:<content-id>"`.
5. Create the MimeMessage.
6. Create MimeMessageHelper in multipart mode.
7. Set From, To, Subject, and any required headers.
8. Call `setText(html, true)` or `setText(plain, html)`.
9. Call `addInline(contentId, resource, contentType)` for each image.
10. Call `addAttachment(...)` for files the recipient needs to download.
11. Send the message using JavaMailSender.
12. If rendering issues occur, serialize/parse MIME and verify CIDs and Content-Types.

~~~text
Validate recipient and assets
          |
          v
Choose resources + generate CIDs
          |
          v
Render HTML with cid references
          |
          v
Create MimeMessage + multipart helper
          |
          v
setText(plain/html)
          |
          v
addInline(resource by CID)
          |
          v
addAttachment(downloadable files)
          |
          v
JavaMailSender.send()
~~~

## 19. Frequently asked questions

**Can I call addInline before setText if the email still displays fine in Gmail?** Do not rely on the behavior of a single client. Spring recommends calling addInline after setText so mail readers can resolve CIDs properly.

**Is multipart=true required?** Yes. Inline resources require a multipart message. Create MimeMessageHelper with an appropriate multipart mode; the boolean true constructor is a common choice.

**Does the CID in HTML need angle brackets?** In HTML, use `cid:company-logo`. Pass `company-logo` to addInline. The helper handles formatting Content-ID in the MIME header; do not add angle brackets in HTML yourself.

**Must the resource name and Content-ID be identical?** No. The filename describes the resource; Content-ID is the identifier HTML references. They just need to be mapped consistently in code.

**Can the same image appear multiple times in the HTML?** Yes. Multiple locations can reference the same CID and share a single MIME part.

**Can multiple inline resources be added?** Yes. Call addInline once for each Content-ID/resource, all after setText.

**Can addInline be used for a PDF?** Technically a resource can be attached to MIME with a CID, but PDFs are usually better suited as attachments. Use inline only if target email clients and business logic have explicit inline PDF rendering; do not treat it like an inline image.

**Will images appear if the recipient uses a text-only mail client?** No. Text/plain does not render CID images; ensure important information is still included in the text version.

**Can an image be fetched from a URL and passed directly to addInline?** addInline accepts Resource/DataSource/InputStreamSource, not arbitrary URLs with automatic safe fetching. If downloading images from external sources, enforce SSRF, redirect, host, size, MIME type, and access controls before creating the Resource.

**What happens if setText is called a second time after addInline?** Avoid designing such a flow. Finalize the body once before adding inline resources; if content must change, rebuild the message/helper in a clear sequence.

## 20. Principles to remember

An inline resource is a MIME part with a **Content-ID** referenced by HTML via a `cid:...` URI. In Spring Framework Mail, build HTML containing the CIDs, call **MimeMessageHelper.setText(...) first**, and only then call **addInline(...)** for each resource. For downloadable files, use addAttachment separately.

Keep Content-IDs matching exactly between the template and the helper, use reliably readable Resources, specify the right Content-Type, secure image sources, and optimize payload size. When diagnosing issues, inspect MIME after serialization/parsing and locate parts by Content-ID rather than assuming fixed part indices.

**Core order: render HTML → setText → addInline → addAttachment (if any) → send.** This yields HTML emails with embedded images that are clean, testable, and better supported across email clients.

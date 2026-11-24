# Purpose of Inline Resources in HTML Emails

## 1. What is an inline resource?

An HTML email can contain images, icons, or other resources that need to appear directly inside the message body. For example, an order confirmation email may display a brand logo at the top of the message, product photos next to order details, or a small chart in a report section.

One way to do this is to **embed the resource inside the email message itself as a MIME part related to the HTML part**, and then have the HTML reference that part. In email terminology, this is commonly called an **inline resource**. In Spring Framework Mail, the **MimeMessageHelper** class supports adding inline resources through the **addInline(...)** method.

Example of HTML referencing a logo:

~~~html
<img src="cid:brandLogo" alt="Brand logo">
~~~

Corresponding Java code to add the image:

~~~java
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

Here, **cid:brandLogo** is a reference from the HTML to a MIME part with the matching **Content-ID**. The image is packaged inside the email; an email client can read that part and display it in place of the img tag when it supports this type of content.

Inline resources are typically used for logos, icons, small illustrations, or charts that need to travel with the message body. They avoid requiring the email to load that image from an external URL. However, **being inline does not guarantee every email client will always display the image**: clients may block images, restrict HTML, or present MIME parts differently.

## 2. Why do HTML emails need inline resources?

A plain-text email can convey information without images. However, some messages benefit from visuals to aid reading and recognition:

- **Brand logos** help recipients identify the sender.
- **Status icons** help distinguish success, warning, or informational states.
- **Product images** help recipients recognize the item being referenced.
- **Charts or illustrations** help summarize a report.
- **Small diagrams** can explain a workflow or status.
- **Signature images** may be used in some notification templates, provided equivalent text information is still included.

For example, an order confirmation email might have a header section like:

~~~text
+-----------------------------------+
|            Brand logo             |
|                                   |
|      Your order is confirmed      |
|                                   |
|      Order ID: ORD-2026-015       |
|      Status: Processing           |
|                                   |
|           [View order]            |
+-----------------------------------+
~~~

The logo can be embedded inline so it stays with the message. Content such as the order ID, status, and action must still be real text/HTML—never turn all important information into a single image.

### Main purposes

| Purpose | Example | Benefit |
|---|---|---|
| Identification | Logo at the top of the email | Keeps brand imagery inside the message content |
| Illustration | Product photo or diagram | Helps the recipient understand the referenced item |
| Visualization | Small chart in a report | Allows quick reading of a trend |
| Status | Warning or completion icon | Aids status recognition |
| Layout | Small decorative graphic | Adds visual emphasis to the HTML template |

Not every email needs inline images. For a simple notification such as an OTP code or a short confirmation message, text-only content can be clearer and lighter. Add images only when they serve a specific purpose and have a fallback when images are not displayed.

## 3. Three ways to include images in HTML emails

There are three common ways for an HTML email to use images:

| Approach | Example in HTML | Where is the image data stored? | Characteristics |
|---|---|---|---|
| **Remote image** | img src="https://static.example.com/logo.png" | On a web server/CDN | Email client needs to access the URL to fetch the image |
| **Inline resource via CID** | img src="cid:brandLogo" | In a MIME part of the email | HTML references the part via Content-ID |
| **Data URI** | img src="data:image/png;base64,..." | Embedded directly in the HTML string | Inconsistent support across email clients, longer HTML |

### Remote image

~~~html
<img
  src="https://static.example.com/email/brand-logo.png"
  alt="Brand logo">
~~~

The image is hosted on a website or CDN. The email only contains the URL. When the recipient opens the message, the email client may fetch the image from that server.

**Advantages:**

- Does not significantly increase the MIME size of the email.
- Allows updating the image on the server without resending the email.
- Suitable for large banners or multiple images.
- Can leverage CDNs and caching.

**Limitations:**

- Email clients may block remote images or require the recipient to allow loading them.
- URLs can expire, change, or the image server may experience downtime.
- Image loading may disclose access information, IP addresses, or open timestamps, depending on how clients and proxies behave.
- If the URL contains tokens or personal identifiers, loading the image may leak data through logs or intermediary systems.

### Inline resource via CID

~~~html
<img src="cid:brandLogo" alt="Brand logo">
~~~

The image is attached inside the MIME structure and given a Content-ID. The email client looks up the matching part when rendering the HTML.

**Advantages:**

- Does not require the email client to fetch that image from an external website.
- The image travels with the message and does not depend on whether the image URL remains active later.
- Useful for small logos or icons that need to be packaged with the email.
- Preserves the exact version of the image at the time of sending.

**Limitations:**

- Increases the email size.
- Depends on the email client's MIME/CID support.
- Some clients still block or fail to display the image.
- The image may appear in the attachment list depending on how the client presents it.

### Data URI

~~~html
<img
  src="data:image/png;base64,iVBORw0KGgo..."
  alt="Icon">
~~~

The image data is embedded directly in the src attribute. This approach does not require a separate MIME part, but support across email clients is inconsistent. It also makes the HTML longer and harder to manage. For emails that need broad compatibility, **CID or remote images are usually more predictable choices**, depending on the goal.

## 4. How is an inline resource different from an attachment?

Both inline resources and attachments can be represented as MIME parts, but their intended usage differs:

- An **inline resource** is referenced by the HTML content to be displayed directly inside the message body.
- An **attachment** is a file the recipient can open or download independently, such as a PDF invoice.

Example:

~~~html
<html lang="en">
  <body>
    <img src="cid:brandLogo" alt="Brand logo">
    <h2>Your Invoice</h2>
    <p>The PDF invoice is attached to this email.</p>
  </body>
</html>
~~~

In Java:

~~~java
helper.setText(plainText, htmlText);

// The image is referenced by the HTML to be displayed inside the body.
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);

// The PDF is an attachment for the recipient to download.
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);
~~~

| Criterion | Inline resource | Attachment |
|---|---|---|
| Purpose | Display alongside HTML | Provide a standalone file |
| Helper API | **addInline(...)** | **addAttachment(...)** |
| HTML reference | Typically uses **cid:** | No HTML reference needed |
| Content-ID | Used to link with HTML | Not normally required |
| Content-Disposition | Typically intended as inline | Typically attachment |
| Examples | Logo, icon, illustration | PDF, CSV, document |

Some email clients may still display inline resources in the attachment area or allow recipients to view them separately. That is a difference in how the client presents them; the application should still declare the proper MIME intent.

## 5. Content-ID and the cid: syntax

For HTML to reference an inline image, two matching pieces are needed:

1. **The HTML** contains a URL using the cid scheme, such as **cid:brandLogo**.
2. **The MIME part** contains the image data and a matching **Content-ID** header, typically represented in the header with angle brackets.

Example of the part:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline
~~~

HTML:

~~~html
<img src="cid:brandLogo" alt="Brand logo">
~~~

In Spring:

~~~java
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

**The contentId parameter of addInline is brandLogo**, without the **cid:** prefix and without manually adding angle brackets. The HTML is responsible for writing **cid:brandLogo** in the src attribute.

Use simple, meaningful IDs that are unique within the message, such as **brandLogo**, **invoiceChart**, or **supportIcon**. If a Content-ID contains special characters, it must follow identifier syntax and proper URL reference encoding; do not concatenate arbitrary user input into a CID.

### A CID is not a website URL

The string **cid:brandLogo** is not an HTTP path, not a local filesystem path, and not a Spring MVC endpoint. It is an internal email content reference used to link the HTML part with the corresponding MIME part.

If the email client cannot find a part with the matching Content-ID, the image may fail to display. When that happens, inspect both the HTML and the raw MIME rather than looking only at the Java code.

## 6. multipart/related represents the relationship between HTML and images

Emails with inline images typically use a **multipart/related** structure. This subtype describes MIME parts that are related to one another: the main HTML part references auxiliary resources such as images.

Diagram:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

Conceptual MIME example:

~~~text
MIME-Version: 1.0
Content-Type: multipart/related; boundary="related_001"

--related_001
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <h2>Welcome</h2>
    <img src="cid:brandLogo" alt="Logo">
  </body>
</html>

--related_001
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline

... encoded image data ...

--related_001--
~~~

This is an illustrative structural example, not complete MIME content to send directly. Jakarta Mail generates the necessary boundaries, headers, and encoding. Do not manually concatenate raw MIME strings when you can use MimeMessageHelper.

### When the email has both plain text and HTML

If the application wants to support both HTML and plain-text readers, the body typically uses a **multipart/alternative** structure. When inline images are added, a nested structure may appear:

~~~text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    │       └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

If the email also has regular file attachments, there may be an outer **multipart/mixed** wrapper:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png; Content-ID: <brandLogo>
    └── application/pdf; attachment
~~~

These are logical relationship diagrams. The actual MIME tree may vary depending on the multipart mode and how Jakarta Mail constructs the message. What matters is understanding that:

- **alternative** holds alternative representations of the same content.
- **related** holds the main content and the resources referenced by that content.
- **mixed** holds independent parts bundled in the same email, such as the body and attachments.

## 7. Benefits of inline resources for content reliability

With remote images, the email client has to fetch the image from an external server. If the server goes down, the URL changes, or the client blocks remote images, the graphic may disappear.

With inline images, the image bytes are sent inside the email. Thus the content does not need to contact an external image server to retrieve that part. This is helpful when:

- The email is a notification record that needs to be archived and displayed later.
- The logo needs to preserve its exact version at the time the email was sent.
- Recipients frequently read mail in environments with restricted access to external resources.
- The resource is small and rarely changes, such as a logo or icon.

However, distinguish between **a resource being present in the email** and **a resource being allowed to display by the client**. A client may still ask the user to permit viewing images, enforce security policies, or display the MIME part as an attachment.

Therefore, inline resources reduce reliance on fetching external URLs; they do not guarantee display in all clients.

## 8. Benefits for consistency and archiving

A remote image can be replaced at the same URL. When a recipient reopens an old email, they may see a new image if the server updated the file. With inline images, the image content is already packaged inside the email at send time.

Example:

~~~text
At send time:
  Email A + logo version 1
        |
        v
  Recipient saves email
        |
        v
At a later time:
  Website updates logo to version 2
        |
        v
  Email A still contains logo version 1 data
~~~

This is beneficial when **historical consistency** is needed: older messages retain the imagery sent with them, as long as the mailbox still stores the full MIME content.

This consistency is especially useful for reports, illustrated invoices, status notifications, or archival documents. However, if images contain dynamic data, packaging images into every email also increases storage size and data-management responsibility. Only inline resources that truly need to stay fixed with the message.

## 9. Privacy benefits and trade-offs

Remote images can trigger HTTP requests when an email client loads them. Depending on the infrastructure, those requests may expose information such as access time, IP address, or a tracking identifier. Some email clients proxy or cache images, so observed data does not directly reflect user behavior.

Inline resources do not require an HTTP request to an image website to fetch data that is already inside the email. This can reduce one source of tracking from remote image loading.

Even so:

- Email clients and mailbox systems still process the message and may store its data.
- Mail delivery providers still have transport and recipient information.
- Inline content can contain sensitive data if the application renders such data into an image.
- Recipients can download, save, or forward the image along with the email.
- An email may be scanned by security gateways and anti-malware systems.

Therefore, **inline is not encryption** and is not an access-control mechanism either. If an image contains personal data, the application must control recipients, access permissions, retention periods, and what content is allowed to be shown.

## 10. When should you use inline resources?

Inline is a good fit when an image plays a supporting role in the content and should be packaged with the email:

### Brand logo

A small logo in the header or footer helps recipients identify the sender. If the logo is a stable asset, ClassPathResource can load it from resources packaged in the application.

### Status icon

A small icon can support completion, warning, or attention-required notices. However, the status must also be stated in text such as **"Completed"** or **"Action required"** so users do not rely solely on color or icons.

### Summary chart

A report email can include a small PNG chart generated at send time. Inline keeps the chart tied to the email's data snapshot. For large or interactive charts, provide a link to an access-controlled dashboard instead.

### Short illustration

A small graphic helps explain an action or product. If the image does not render, alt text and descriptive copy must still convey the main point.

### Decorative assets

Small background images or motifs can be used, but use caution: CSS background images are not uniformly supported across email clients. Never put important information inside a decorative image.

## 11. When should you not use inline resources?

You should not embed every image into every email. Other options fit certain cases better:

| Case | Option to consider | Reason |
|---|---|---|
| Large banners or many product photos | Remote image/CDN | Reduces the size of each email |
| Graphics that need updates after sending | Remote image | Content can be updated on the server, if privacy policies allow |
| Images that are simply files for download | Attachment | Download intent is clearer |
| Images non-essential to the content | Omit the image | Keeps the email light and less dependent on rendering |
| Content expressible as text | Plain text/HTML text | Easier to read, search, and access |
| Interactive charts or large dashboards | Link to a protected web app | Email is not a full interactive environment |
| Very large images or high image count | Secure download link or CDN | Avoids exceeding message size limits |

A practical rule of thumb: **use inline for small, purposeful assets that must travel with the content; use attachments for standalone files; use remote images when content should load from the web and display/privacy trade-offs are acceptable.**

## 12. Using MimeMessageHelper to add inline resources

In Spring Framework Mail, **MimeMessageHelper** provides the API for adding inline resources. A basic example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcome(
        JavaMailSender mailSender,
        String recipient
) throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("welcome@example.com");
    helper.setTo(recipient);
    helper.setSubject("Welcome");

    String plainText = """
            Hello!

            Your account has been created successfully.
            Visit https://example.com/account to view your details.
            """;

    String htmlText = """
            <html lang="en">
              <body>
                <img src="cid:brandLogo"
                     alt="Brand logo"
                     width="160">
                <h2>Welcome!</h2>
                <p>Your account has been created successfully.</p>
                <p>
                  <a href="https://example.com/account">
                    View account details
                  </a>
                </p>
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

    mailSender.send(message);
}
~~~

Example assumptions:

- The application has a **JavaMailSender** bean configured with valid SMTP settings.
- The file **mail/brand-logo.png** is on the classpath, for example under **src/main/resources/mail/**.
- The From address is permitted by the mail provider.
- The resource is a valid PNG file of appropriate size.

### Step-by-step explanation

1. **createMimeMessage()** creates a MIME message object.
2. **MimeMessageHelper(..., MULTIPART_MODE_RELATED, UTF-8)** creates a helper with a multipart/related structure suitable for HTML and inline resources.
3. **setFrom**, **setTo**, and **setSubject** configure the basic headers.
4. **setText(plainText, htmlText)** creates two alternative representations of the body.
5. **addInline("brandLogo", resource, "image/png")** adds the image part with the matching Content-ID.
6. **send(message)** submits the message to the mail transport.

### Why should setText be called before addInline?

With MimeMessageHelper, setting the body can create or alter the internal multipart structure. Therefore, the recommended order is:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brandLogo", logoResource, "image/png");
~~~

Adding inline resources before setting the body can produce an unexpected multipart structure on some code paths. Always keep the order **setText first, addInline after**.

## 13. Choosing the right multipart mode

MimeMessageHelper provides multipart modes to describe how the content is organized:

| Mode | General purpose | Common use case |
|---|---|---|
| **MULTIPART_MODE_NO** | No multipart created | Simple single-part email |
| **MULTIPART_MODE_MIXED** | multipart/mixed structure | Body with regular attachments |
| **MULTIPART_MODE_RELATED** | multipart/related structure | HTML with inline resources |
| **MULTIPART_MODE_MIXED_RELATED** | Combines mixed and related layers | Email with both inline resources and attachments |

If the email only has HTML and a CID logo, you can use **MULTIPART_MODE_RELATED**. If the email has both inline images and a PDF attachment, **MULTIPART_MODE_MIXED_RELATED** is typically considered.

The constructor with a boolean:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
~~~

enables multipart using the helper's default mode. When you need explicit control over the structure for inline resources and attachments, specify the exact mode.

Do not use **MULTIPART_MODE_NO** and expect addInline to build an appropriate MIME tree automatically. The MIME structure must support parts related to the body.

## 14. Choosing an inline resource source

The addInline method accepts different sources depending on the overload. Some common choices:

### ClassPathResource

Suitable for fixed logos or icons packaged with the application:

~~~java
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

The runtime path is relative to the classpath root; do not include **src/main/resources** in the resource name.

### FileSystemResource

Suitable when the image is stored on the filesystem:

~~~java
helper.addInline(
        "reportChart",
        new FileSystemResource(chartPath),
        "image/png"
);
~~~

The file must exist, be readable, and remain intact while sending. Do not use arbitrary paths from user requests without checking permissions and access scope.

### ByteArrayResource

Suitable when the image is generated dynamically and already in memory:

~~~java
byte[] pngBytes = chartRenderer.renderPng();

helper.addInline(
        "reportChart",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

ByteArrayResource can provide a fresh stream from the same data, which is convenient for repeated reads. However, large images or many concurrent emails can increase heap pressure.

### Custom InputStreamSource

If the storage source provides an API to open a fresh stream, you can pass an InputStreamSource:

~~~java
InputStreamSource logoSource =
        () -> objectStorage.openStream(bucket, objectKey);

helper.addInline("brandLogo", logoSource, "image/png");
~~~

**objectStorage.openStream(...)** is an illustrative application API. Each call to getInputStream() must return a new stream reading the same version of the data. Avoid wrapping an already-opened, consumed InputStream in a source and assuming it can be read again.

## 15. Content-Type, filename, and image size

When adding an inline resource, specify the correct media type:

| Data | Common Content-Type |
|---|---|
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| GIF | **image/gif** |
| WebP | **image/webp**; verify client support |
| SVG | **image/svg+xml**; carefully verify client support and security policies |

Do not declare **image/png** for JPEG data just because the filename ends in .png. Content-Type is metadata telling the client how to process the data; it does not turn mismatched bytes into a valid image.

### Size optimization

Inline images are packaged inside the email. Binary data is typically base64-encoded during MIME transmission, increasing the encoded part size by roughly one-third, not counting headers, boundaries, and other content.

Illustrative estimate:

~~~text
Original PNG image:       300 KB
Estimated base64 part:    about 400 KB
MIME headers/boundaries:  slight additional overhead
Total message:            also includes body and other attachments
~~~

These are estimates, not exact sizes for every message.

Best practices:

- Use images sized appropriately for their display dimensions.
- Compress images before sending.
- Avoid embedding the same image multiple times under multiple Content-IDs unnecessarily.
- Limit the number of inline images in a single message.
- Check the SMTP/ESP message size limits.
- For large images, consider remote images or a secure download link.

## 16. Inline resources and email client compatibility

Email clients do not all handle HTML and MIME identically. Even when the MIME has a valid Content-ID, an image may still fail to appear because:

- The client blocks images under its security policy.
- The client does not process the multipart/related structure as expected.
- The HTML references the wrong CID or the MIME part is missing Content-ID.
- The Content-Type is wrong or the image bytes are corrupted.
- The client displays the inline part in the attachment area.
- Surrounding CSS/HTML is stripped or altered.

Therefore, inline resources should always have **alt text**:

~~~html
<img
  src="cid:brandLogo"
  alt="Brand logo"
  width="160">
~~~

Alt text helps when images fail to load and also helps screen-reader users understand the image's role. If an image is purely decorative, an empty alt can be used depending on context; do not use alt text as a substitute for a critical block of content.

### Do not put critical information only inside images

Do not create a single image containing:

- OTP or verification codes.
- Invoice numbers or amounts due.
- Payment due dates or expiration dates.
- Links or actions the user must take.
- Legal notices or important warnings.

Such content must be real text in the email. Images should only support the presentation.

## 17. Inline resources and accessibility

Emails with inline images still need to be designed so users can understand the content without relying on visuals.

**Key principles:**

1. Use alt text that accurately describes the meaning of the image.
2. Do not use color or icons as the sole way to convey status.
3. Keep headings, descriptions, and actions as real text/links.
4. Provide a plain-text alternative using **setText(plainText, htmlText)**.
5. Ensure a logical reading order when images do not display.
6. Use appropriate image dimensions so small-screen layouts do not break.

Example:

~~~html
<img src="cid:successIcon" alt="Completed">
<h2>Your request has been processed</h2>
<p>You can view the result in your account.</p>
<a href="https://example.com/requests">View request</a>
~~~

Even if the image does not appear, the heading and paragraph still convey the status. A descriptive link label tells the user what action to take.

### Plain text must carry the same meaning

~~~java
helper.setText(
        """
        Your request has been processed.
        View the result at https://example.com/requests
        """,
        htmlText
);
~~~

The text version does not need to describe every decorative detail of the images, but it must preserve the business information and key URLs. This serves as a fallback for clients that do not render HTML or users who choose plain-text view.

## 18. Privacy: inline is not encryption

One reason to choose CID is to reduce reliance on image-loading requests to an external server. With remote images, loading can generate observable data about open times or connection details, depending on email clients, proxies, and caches.

Inline resources live inside the MIME message, so there is no need to fetch the image from an external website. However, that **does not mean the email content is end-to-end encrypted**:

- SMTP servers and transport systems still process the message.
- Mailboxes storing the email may retain the image data as well.
- Recipients can download, save, or forward the image.
- Security gateways may scan the content.
- Sensitive data drawn into an image can still be read just like message text.

If an image contains customer-specific data, verify recipient authorization and avoid sending a single email to multiple recipients. CID is simply a mechanism for linking resources in MIME.

## 19. Securing image sources and dynamic data

If images come from a dynamic source, validate both the source and the data:

### Files on the filesystem

- Read only from permitted directories.
- Never use raw file paths supplied directly by users.
- Guard against path traversal and symbolic links.
- Verify the recipient is authorized to view the image.

### Images from remote storage

- Use credentials with least privilege.
- Enforce size and download timeouts.
- Pin a version or snapshot if consistent data is required.
- Do not fetch arbitrary URLs from requests to prevent SSRF.
- Close streams and handle network errors properly.

### Images generated from user data

- Escape text when rendering HTML.
- Do not place untrusted content into SVG/HTML that may contain active markup.
- Validate image types and limit pixel dimensions and byte size.
- Scan or sanitize images according to application policy.
- Do not log sensitive image bytes or tokens.

A PNG whose file format has been verified can still contain private information. Media-type validation and data authorization are two separate steps.

## 20. Multiple inline resources in one email

An email can contain multiple inline images. Each image requires its own Content-ID:

~~~html
<html lang="en">
  <body>
    <header>
      <img src="cid:brandLogo" alt="Brand logo" width="150">
    </header>
    <h2>Monthly Report</h2>
    <img src="cid:revenueChart" alt="Monthly revenue chart">
    <p>Revenue is summarized in the report.</p>
    <img src="cid:supportIcon" alt="Support icon" width="24">
  </body>
</html>
~~~

Java:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
helper.addInline(
        "revenueChart",
        new ByteArrayResource(chartPngBytes),
        "image/png"
);
helper.addInline(
        "supportIcon",
        new ClassPathResource("mail/support-icon.png"),
        "image/png"
);
~~~

The Content-IDs **brandLogo**, **revenueChart**, and **supportIcon** must match the part after **cid:** in the HTML. Do not reuse the same ID for different image payloads within the same message.

If a template does not use a particular image, omit adding that part to save space. If images are added dynamically by email type, manage the list of CIDs and resources centrally so templates never reference a missing ID.

## 21. Combining inline resources with attachments

An email can contain both images displayed inside the HTML and a standalone file:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("reports@example.com");
helper.setTo(recipient);
helper.setSubject("Your Report");
helper.setText(
        "The report is attached. The chart is included in the HTML body.",
        """
        <html lang="en">
          <body>
            <img src="cid:reportChart" alt="Report chart">
            <p>The detailed report is attached as a PDF.</p>
          </body>
        </html>
        """
);

helper.addInline(
        "reportChart",
        new ByteArrayResource(chartPngBytes),
        "image/png"
);
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);

mailSender.send(message);
~~~

This is an illustrative example; **recipient**, **chartPngBytes**, and **reportPath** must be produced and validated beforehand. The PDF file and the image must belong to the same report, and the recipient must be authorized to view both.

**MULTIPART_MODE_MIXED_RELATED** is typically appropriate when you need to group related resources for HTML alongside standalone attachments. The exact MIME structure is generated by the helper/Jakarta Mail; do not assume every email client will present inline parts and attachments in the exact same way.

## 22. Common errors when using inline resources

| Symptom | Possible cause | Resolution |
|---|---|---|
| Image missing, broken image icon shown | HTML CID mismatches Content-ID or MIME part is missing | Compare cid in HTML with addInline and raw MIME |
| Passing **cid:brandLogo** to addInline | Content-ID passed with cid prefix | Pass only **brandLogo** |
| Image appears as an attachment | Client presents MIME part its own way or structure is improper | Check multipart/related, Content-ID, and Content-Disposition |
| Inline resource lost after setText | Calling addInline before setting the body | Call setText first, addInline after |
| Cannot add inline resource | Helper does not have multipart enabled | Use MULTIPART_MODE_RELATED or MIXED_RELATED |
| Image corrupted or renders incorrectly | Wrong Content-Type or invalid image bytes | Verify actual format and media type |
| Resource not found | Wrong classpath path or file not packaged | Check src/main/resources and resource name |
| Remote image fails to load | Expired URL, client blocks remote images, or server error | Check URL; consider CID if image is small and must travel with mail |
| Email too large | Embedding too many images or oversized images | Optimize images, reduce part count, or use remote images |
| Image renders in one client, not another | Differences in HTML/MIME support or image policies | Keep alt text and text copy; test on target clients |
| Graphic lacks description for screen readers | Missing alt text | Add meaningful alt or empty alt if purely decorative |
| Dark logo disappears in dark mode | Image unsuitable for dark backgrounds | Use suitable assets or a background layout with contrast |

### How to inspect raw MIME

When diagnosing issues, send a test message to an SMTP test inbox and view **Show original**, **View source**, or the raw message. Look for:

1. The HTML part containing **src="cid:brandLogo"**.
2. A MIME part with **Content-ID: <brandLogo>**.
3. The correct **Content-Type**, such as **image/png**.
4. An appropriate **multipart/related** relationship between the HTML and the image.
5. Complete encoded image data transmitted intact.

Headers may appear in a different order; what matters is the relationship between the HTML and the image part. Raw messages may contain addresses, tokens, personal data, or files; view/store them only in authorized environments and never copy sensitive content into public logs.

## 23. Performance and size limits

Inline resources increase the size of every email. If the same logo is embedded in thousands of emails, the image data is transmitted repeatedly in every single message. This can increase:

- Outbound and inbound bandwidth.
- MIME serialization and transmission time.
- Memory usage when building many messages concurrently.
- Storage usage inside mailboxes.
- Risk of exceeding the SMTP provider's message size limit.

### Base64 size estimate

Binary image data is typically represented using base64 in MIME. The base64 part size is usually about one-third larger than the raw data, excluding headers and line breaks. Thus, a 600 KB image can produce roughly an 800 KB base64 part before adding the body and other parts.

This is a design estimate, not an exact measurement for every email. Total size depends on encoding, number of images, attachments, and transport.

### Consider remote images when appropriate

If an email has many product photos or large banners, remote images from a CDN can significantly reduce per-message size. In return, clients may block images, URLs may change, and image requests may have privacy implications. The choice should be based on purpose, audience, and data policies.

## 24. Testing emails with inline resources

Do not rely solely on opening the HTML in a web browser. Browsers do not process MIME emails the way email clients do.

A practical testing workflow:

1. Create a sample message with plain text, HTML, and one CID image.
2. Send it to an SMTP test server or sandbox.
3. Inspect the raw MIME to confirm Content-ID, Content-Type, and multipart/related.
4. Open the message on the email clients recipients actually use.
5. Test with images blocked and verify the alt text.
6. Test in light/dark mode and on small screens.
7. Check message size and how the client displays the image in the attachment list.
8. Check the plain-text alternative to ensure core content is complete.

If the email contains private data, use test data. Never send real reports or invoices to unauthorized recipients just to check rendering.

### Code tests do not replace client tests

Unit tests can verify that a service calls addInline with the expected Content-ID and resource. Integration tests can inspect the MIME parts after serialization. However, only opening the message in target email clients confirms the real rendering experience.

## 25. Choosing inline resources by goal

| Goal | Suitable option | Things to note |
|---|---|---|
| Fixed logo in message | CID with ClassPathResource | Preserves logo version, check dark mode |
| Small icon | CID or simple text/icon | Do not rely solely on color/shape for status |
| Snapshot chart | CID with ByteArrayResource | Check size and data content |
| Large banner | Remote image/CDN | Client may block; include alt text |
| User-downloadable file | Attachment | Set proper filename and Content-Type |
| Interactive dashboard | Link to web app | Enforce authentication and access control |
| Unnecessary decorative graphic | Can be omitted | Keeps email lighter and easier to read |

There is no single approach that fits every email type. Determine whether an image genuinely helps the recipient understand or take action, then weigh size, compatibility, and privacy.

## 26. Key takeaways

**Inline resources in HTML emails** are payloads packaged as MIME parts and referenced by the HTML part, typically via **cid:** and **Content-ID**. In Spring Framework Mail, **MimeMessageHelper.addInline(...)** adds the resource, and a **multipart/related** structure represents the relationship between the HTML part and the images.

Inline resources are useful for logos, icons, illustrations, and small charts that need to travel with the email. They reduce dependence on fetching images from external servers and preserve the image version at send time. In return, emails become larger and still depend on the client's MIME/HTML handling. Inline is not a regular attachment, not a remote URL, and not an encryption mechanism.

When implementing, choose the right resource source, use unique Content-IDs, set the proper multipart mode, call **setText(...) before addInline(...)**, declare the accurate Content-Type, and keep alt text alongside a plain-text alternative. **The purpose of an inline resource is to support email content right where it needs to appear, while keeping the message understandable even when images are not displayed.**

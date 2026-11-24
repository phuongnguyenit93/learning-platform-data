# Distinguishing Attachments from Inline Resources

When sending an email with Spring Framework Mail, a message can contain multiple types of content: plain text, HTML, images, PDFs, spreadsheets, or other documents. Some files are sent for the recipient to download as standalone documents; some resources are embedded to display directly inside the HTML section. These two purposes are commonly called **attachments** and **inline resources**.

Spring provides two corresponding APIs in **MimeMessageHelper**:

~~~java
helper.addAttachment(
        "invoice.pdf",
        pdfResource,
        "application/pdf"
);

helper.addInline(
        "companyLogo",
        logoResource,
        "image/png"
);
~~~

**addAttachment(...)** adds a standalone attachment, typically with a filename and Content-Disposition set to **attachment**. **addInline(...)** adds a resource referenced by the email body, typically via **Content-ID** and a **cid:** URL in HTML.

The difference lies in **intended usage and how MIME describes the relationship between parts**. Both are data packaged inside an email; both can be represented as MIME parts and sent in the same SMTP call. However, how recipients locate and use them differs.

## 1. Two different display purposes

Imagine a report email containing a logo and a PDF file:

~~~text
Email
├── HTML Body
│   ├── Report Title
│   ├── Logo displayed inside body
│   └── Message text
└── Attachment
    └── report.pdf
~~~

The logo is placed directly inside the HTML body. The recipient sees the logo while reading the email, provided the client supports inline resources. The PDF is a separate document; the recipient can open or save the file from the attachment list.

| Question | Attachment | Inline resource |
| --- | --- | --- |
| Primary purpose | Send a standalone file for the recipient to open or download | Supply a resource for the email body, usually HTML |
| Spring API | **addAttachment(...)** | **addInline(...)** |
| Typical metadata | **Content-Disposition: attachment** | **Content-Disposition: inline** |
| Link identifier | Filename | **Content-ID** |
| HTML reference | Usually none needed | **cid:contentId** |
| Typical MIME container | **multipart/mixed** | **multipart/related** |
| Examples | Invoice PDF, CSV, ZIP | Logo, illustration, chart inside HTML |

An email client may display an inline image in the attachment area or allow saving that image. That is client presentation behavior. It does not change the intent when the application builds the message: the image is added for HTML to reference, whereas the PDF is added as a standalone document.

## 2. What is an attachment?

An **attachment** is a MIME part sent along with an email so the recipient can open or save it as a separate file. Typically, the part has:

- **Content-Type** describing the data type.
- **Content-Disposition: attachment** hinting that it should be presented as an attached file.
- **filename** providing a suggested filename to the recipient.
- **Content-Transfer-Encoding** describing how data is represented in the message, typically Base64 for binary data.

Example of a PDF part:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

[encoded-PDF-data]
~~~

The bracketed data section is an illustrative placeholder, not real PDF content.

The recipient does not need an HTML tag to find this file. Email clients identify the part via MIME headers and present it as an attachment.

### 2.1. Using addAttachment in Spring Mail

To send an attachment, create a **MimeMessage** and a **MimeMessageHelper** in multipart mode:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("billing@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Your invoice");
helper.setText(
        "Hello,\nPlease see the attached invoice.",
        false
);

helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);

mailSender.send(message);
~~~

In this example:

- **createMimeMessage()** creates the MIME message.
- **MULTIPART_MODE_MIXED** allows combining the body and independent parts such as attachments.
- **setText(...)** sets the email body.
- **addAttachment(...)** adds the PDF with a filename and MIME type.
- **send(...)** sends the entire message, including body and attachment.

**SimpleMailMessage** does not support attachments. When you need to send files, complex HTML, or inline resources, use `MimeMessage`.

### 2.2. Filename is not a file path

The first parameter of `addAttachment` is the display name for the recipient:

~~~java
helper.addAttachment(
        "invoice-2026-001.pdf",
        pdfResource,
        "application/pdf"
);
~~~

It is not a storage path on the sending machine and does not require the application to create a physical file with that exact name. Even if data comes from a byte array, the filename is passed separately.

Do not use internal paths like **C:\app\private\invoice.pdf** as the filename because it can expose filesystem layout and create an inappropriate name for the recipient.

## 3. What is an inline resource?

An **inline resource** is a MIME part added to a message so another content part can reference it. The most common case is HTML using a **cid:** URL to display an image.

HTML example:

~~~html
<html>
  <body>
    <h1>Welcome!</h1>
    <img src="cid:companyLogo" alt="Company logo">
    <p>Thank you for signing up.</p>
  </body>
</html>
~~~

This HTML snippet references a MIME part with a matching Content-ID. If the message lacks that part, the client has no inline data to resolve the reference.

### 3.1. Content-ID connects HTML to the MIME part

An image part might have headers:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <companyLogo>
Content-Transfer-Encoding: base64

[PNG-image-data]
~~~

In HTML:

~~~html
<img src="cid:companyLogo" alt="Company logo">
~~~

The logical value **companyLogo** must match. Angle brackets in the header are how Content-ID is formatted in MIME; in helper calls and `cid:` URLs, you normally use only the identifier value.

Java:

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

There is no need to pass **<companyLogo>** into the `contentId` parameter. Let Spring Mail format the header per MIME syntax.

### 3.2. Using addInline in Spring Mail

A message with HTML and an inline image:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("user@example.net");
helper.setSubject("Notification");

String html = """
        <html>
          <body>
            <p>Hello!</p>
            <img src="cid:companyLogo"
                 alt="Company logo"
                 width="160">
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

Here:

- **setText(html, true)** declares the body as HTML.
- **addInline(...)** adds the image to the message and sets Content-ID.
- **src="cid:companyLogo"** points to the embedded image.
- **MULTIPART_MODE_RELATED** expresses the relationship between HTML and related resources.

### 3.3. Call setText before addInline

With `MimeMessageHelper`, set the body using **setText(...)** before adding inline resources:

~~~java
helper.setText(html, true);
helper.addInline("companyLogo", logoResource, "image/png");
~~~

This ordering is recommended by Spring Mail because some email clients are sensitive to how MIME parts are arranged. It lets the helper establish the content first and then add the resources referenced by that content.

Avoid reversing the order unless there is a clear reason:

~~~java
helper.addInline("companyLogo", logoResource, "image/png");
helper.setText(html, true);
~~~

### 3.4. Inline does not guarantee the image will appear

Email clients may hide images, choose the plain-text version, lack support for an image format, or show inline parts in the attachment area. A proper MIME structure helps clients understand intent, though it cannot fully control the receiving app's UI and rendering policies.

Therefore, provide **alt text**, keep critical information in text form, and test on target clients.

## 4. Distinguishing Content-Disposition: attachment vs. inline

**Content-Disposition** is a MIME header suggesting how a part should be presented.

Attachment example:

~~~text
Content-Disposition: attachment; filename="report.pdf"
~~~

Inline example:

~~~text
Content-Disposition: inline
Content-ID: <reportLogo>
~~~

Meaning:

- **attachment**: the part is provided as a standalone file for the recipient to open or download.
- **inline**: the part can be displayed alongside the content, if the message structure and client support it.

However, looking only at Content-Disposition is insufficient to determine how a part will actually render. For inline images, the **multipart/related** relationship and **Content-ID** matter greatly. For attachments, filename and MIME type help the client identify the document.

A part with disposition `inline` can still be listed by a client as an attachment. A part with disposition `attachment` can also be downloaded and opened outside the email. The header expresses the sender's intent; the client decides final presentation.

## 5. multipart/mixed and multipart/related

Two common MIME subtypes when sending attachments and inline resources are **multipart/mixed** and **multipart/related**.

### 5.1. multipart/mixed for independent parts

When an email has a body and an attached PDF, the structure is typically:

~~~text
multipart/mixed
├── text/plain
└── application/pdf
    └── Content-Disposition: attachment
~~~

The parts are independent components of the same message. The PDF does not need to be referenced by HTML.

### 5.2. multipart/related for content and related resources

When an email has HTML and an inline logo:

~~~text
multipart/related
├── text/html
│   └── <img src="cid:companyLogo">
└── image/png
    └── Content-ID: <companyLogo>
~~~

The HTML and image work together to form one complete piece of content. The image part is not merely an independent document; it is referenced by the HTML.

### 5.3. Combining both attachments and inline resources

A report email with HTML, a logo, and a PDF can be organized as follows:

~~~text
multipart/mixed
├── multipart/related
│   ├── text/html
│   │   └── <img src="cid:companyLogo">
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

The **multipart/related** branch holds the HTML together with the image. The PDF is an independent part inside the root **multipart/mixed**.

This is why Spring provides **MULTIPART_MODE_MIXED_RELATED**: creating a mixed outer structure and a related branch for content with inline resources.

### 5.4. When both plain text and HTML are present

An email can provide both representations:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │       └── <img src="cid:companyLogo">
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Plain text and HTML are alternative versions of the same content; the inline image serves the HTML version. The PDF remains an independent attachment.

The diagram above shows common MIME relationships. The exact tree and boundaries are generated by the mail library and can vary by message configuration and provider version.

## 6. Choosing a multipart mode in MimeMessageHelper

Spring Framework provides common modes:

| Mode | Meaning | Suitable scenario |
| --- | --- | --- |
| **MULTIPART_MODE_NO** | No multipart created | Email without attachments or inline parts |
| **MULTIPART_MODE_MIXED** | Root `multipart/mixed` | Body and independent attachments |
| **MULTIPART_MODE_RELATED** | Root `multipart/related` | HTML with inline resources |
| **MULTIPART_MODE_MIXED_RELATED** | Mixed root with nested related branch | HTML, inline resources, and attachments |

Example with only a PDF attachment:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);
~~~

Example with only HTML and a logo:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
~~~

Example with HTML, a logo, and a PDF:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Convenient boolean constructor:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

In Spring Framework, **true** enables multipart using the default mode **MULTIPART_MODE_MIXED_RELATED**. When you want to express structural intent explicitly, using the named mode constant is easier to read.

## 7. Complete example: email with inline logo and PDF attachment

Suppose an application sends a report to a manager. The HTML body includes a logo and an introduction; the PDF is a separate file to download.

### 7.1. Resource layout

~~~text
src/main/resources/
└── mail/
    └── logo.png
~~~

The PDF is generated by a reporting service and returned as `byte[]`:

~~~java
byte[] reportPdf = reportGenerator.generate(month);
~~~

### 7.2. Email sending code

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {

    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            byte[] reportPdf
    ) throws MessagingException {

        if (reportPdf == null || reportPdf.length == 0) {
            throw new IllegalArgumentException(
                    "PDF report content must not be empty"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("reports@example.org");
        helper.setTo(recipient);
        helper.setSubject("Monthly report");

        String plainText =
                "The monthly report is ready. "
                + "Please see the attached PDF file.";

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:companyLogo"
                         alt="Company logo"
                         width="150">
                    <h1>Monthly report</h1>
                    <p>Your report has been generated.</p>
                    <p>Please see the attached PDF file.</p>
                  </body>
                </html>
                """;

        // Set body first.
        helper.setText(plainText, htmlText);

        // Logo is referenced in HTML via cid:companyLogo.
        helper.addInline(
                "companyLogo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        // PDF is a standalone file to download.
        helper.addAttachment(
                "monthly-report.pdf",
                new ByteArrayResource(reportPdf),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

This example assumes **reportPdf** contains valid PDF bytes, the logo exists on the classpath, and `recipient` has been validated per business rules. **ByteArrayResource** is used for the in-memory PDF; **ClassPathResource** is used for the static logo.

### 7.3. Analyzing the result

| Component | How it is created | Purpose |
| --- | --- | --- |
| Plain text | **setText(plainText, htmlText)** | Fallback content for non-HTML clients |
| HTML | Second argument of `setText` | Email layout |
| Logo | **addInline("companyLogo", ...)** | Rendered inside HTML via `cid:` |
| PDF | **addAttachment("monthly-report.pdf", ...)** | Standalone file for download |
| To/Subject/From | Corresponding setters | Message metadata |

Recipients can see the logo in the HTML section and the PDF in the attachment list. If a client displays only plain text, the recipient still reads the core information without seeing the logo.

### 7.4. Why not use addAttachment for the logo?

If you use:

~~~java
helper.addAttachment(
        "logo.png",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Spring creates an attachment part intended for downloading. HTML containing **src="cid:companyLogo"** will not automatically locate this part because no matching Content-ID was configured in the `addInline` way.

If the goal is displaying an image inside HTML, use **addInline** with the matching Content-ID. If the goal is providing an image for the recipient to download, use **addAttachment**.

## 8. Example sending only an attachment, no inline resources

A notification email may contain only plain text and a PDF:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setTo("customer@example.net");
helper.setSubject("Payment receipt");
helper.setText(
        "Your receipt is attached to this email.",
        false
);

helper.addAttachment(
        "receipt.pdf",
        new ByteArrayResource(receiptBytes),
        "application/pdf"
);

mailSender.send(message);
~~~

Here there is no HTML referencing a CID. The PDF is purely an attached file. **MULTIPART_MODE_RELATED** is unnecessary because there are no related parts linked to render content.

## 9. Example with only an inline resource, no standalone attachment

A welcome email may use only HTML and a logo:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setTo("user@example.net");
helper.setSubject("Welcome");

String html = """
        <html>
          <body>
            <h1>Welcome!</h1>
            <img src="cid:welcomeLogo"
                 alt="Logo"
                 width="160">
            <p>Thank you for signing up.</p>
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "welcomeLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

There is no need for `addAttachment` if there is no standalone document for the recipient to download. The logo is already a MIME part, used as a resource by the HTML.

## 10. Multiple attachments and multiple inline resources in one email

An email can contain many types of parts. For example, a report with a logo, an inline chart, a PDF, and a CSV:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addInline(
        "salesChart",
        new ByteArrayResource(chartPngBytes),
        "image/png"
);

helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

helper.addAttachment(
        "details.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

HTML:

~~~html
<html>
  <body>
    <img src="cid:companyLogo" alt="Logo">
    <h2>Revenue</h2>
    <img src="cid:salesChart" alt="Revenue chart">
    <p>The PDF and CSV files are attached.</p>
  </body>
</html>
~~~

Conceptual structure:

~~~text
multipart/mixed
└── multipart/related
    ├── text/html
    │   ├── cid:companyLogo
    │   └── cid:salesChart
    ├── image/png
    │   └── Content-ID: <companyLogo>
    └── image/png
        └── Content-ID: <salesChart>
    ├── application/pdf
    │   └── Content-Disposition: attachment
    └── text/csv
        └── Content-Disposition: attachment
~~~

The diagram above illustrates logical relationships only. The concrete MIME parts are organized by the helper according to its multipart structure. Every inline resource needs a unique Content-ID and the HTML must reference the right ID. Standalone attachments need no CID.

## 11. Can the same Resource be used for both purposes?

At the data level, the same byte source can be used to create an inline part or an attachment. However, **each added part needs the API reflecting its exact purpose**.

For example, if the application wants both to display a logo inside HTML and to offer the logo file as a separate download, it can add two parts:

~~~java
ClassPathResource logo =
        new ClassPathResource("mail/logo.png");

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        logo,
        "image/png"
);

helper.addAttachment(
        "company-logo.png",
        logo,
        "image/png"
);
~~~

This creates two MIME parts from the same data source: one related to HTML and one standalone part. The email becomes larger because the image data may be packaged twice. Do this only when business rules genuinely require both uses.

Some clients already show inline parts in the attachment list even with only `addInline`; thus, if the goal is merely displaying an image, do not add a second attachment just to "make sure the recipient sees the image".

## 12. Comparison with external images over HTTPS

Another option is placing an external image URL in the HTML:

~~~html
<img
  src="https://assets.example.org/images/company-logo.png"
  alt="Company logo">
~~~

Then the application does not need to embed image bytes into the MIME message. The email client can fetch the image when the recipient opens the email, if client policy allows.

| Criterion | Inline CID | HTTPS image |
| --- | --- | --- |
| Image data | Embedded inside the message | Hosted on an external server |
| Internet access needed when opening mail | No external fetch needed | Usually required |
| Email size | Increases by image size and MIME encoding | Usually smaller |
| Updating image | Each email carries the copy at send time | Can be updated at the server URL |
| Privacy | No external image fetch request | Request can generate an access signal |
| Blocking risk | Clients can still hide inline parts | Clients may block remote image loading |
| Reference in HTML | Uses `cid:` | Uses URL |

Inline CID fits when you want images carried along with the message, such as logos or report charts. HTTPS URLs fit when images are large, change independently, or you want smaller emails. Consider privacy and email clients' remote-content loading policies.

## 13. MIME type and filename: each purpose still needs accurate metadata

Whether attachment or inline resource, a MIME part needs the right content type.

| Data | Commonly used MIME type |
| --- | --- |
| PDF | **application/pdf** |
| CSV | **text/csv; charset=UTF-8** |
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| GIF | **image/gif** |
| Plain text | **text/plain; charset=UTF-8** |
| HTML | **text/html; charset=UTF-8** |

For attachments, the filename helps the recipient identify the file:

~~~java
helper.addAttachment(
        "invoice.pdf",
        pdfResource,
        "application/pdf"
);
~~~

For inline resources, Content-ID is the crucial link:

~~~java
helper.addInline(
        "invoiceLogo",
        logoResource,
        "image/png"
);
~~~

An inline image might carry a filename or name metadata in MIME depending on how the library creates the part, yet **HTML finds the part by Content-ID**, not by filename.

MIME types do not convert data. If the actual bytes are JPEG while declaring `image/png`, clients may fail to render it properly. Declare according to the actual format.

## 14. Size and performance

Both attachments and inline resources increase email size because their data is packaged inside the MIME message.

For Base64-encoded binary data, the encoded size is typically about **4/3 of the original data**, excluding line breaks, headers, and boundaries. Thus, a 6 MB file produces more than 6 MB of transport data.

Points to consider:

- Limit the size of each attachment.
- Limit total email size.
- Limit the number of attachments and inline images.
- Optimize logos and charts before embedding.
- Avoid sending high-resolution images when displayed at small dimensions.
- Consider heap usage with `ByteArrayResource`.
- Check message size limits of your SMTP provider and receiving systems.

For large files, you can use `FileSystemResource` instead of holding an entire `byte[]` on the heap, or provide a time-limited download link. However, `FileSystemResource` does not guarantee zero-buffer memory usage across the entire sending pipeline; evaluate actual implementations and providers.

## 15. Security when sending attachments and inline resources

Both types of parts can contain sensitive data. Marking data as inline or attachment does not make it inherently safer.

### 15.1. Check recipient authorization

Before sending, verify the recipient is authorized to view the document or image. Never take a document ID from a request and send its content without verifying the relationship between the document, user, and business context.

### 15.2. Check file source and MIME type

If the file comes from an upload or external storage:

- Verify the actual format, not just the extension.
- Enforce size limits before reading the whole file into memory.
- Allow only policy-permitted file types.
- Scan for malware if required.
- Check read permissions and permission to send the document.

### 15.3. Filename and Content-ID are not places for secrets

Filenames may be visible to recipients. Content-ID appears in MIME headers and HTML. Never put internal paths, access tokens, passwords, or sensitive metadata into these two fields.

### 15.4. Never concatenate MIME headers manually

Do not construct raw headers by string-concatenating untrusted data:

~~~java
message.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + userFilename + "\""
);
~~~

Use **addAttachment** or **addInline** so the library handles MIME metadata. Filenames still need validation per application policy.

### 15.5. Dynamic HTML must be escaped

If HTML emails include user-supplied names or content, escape appropriately for the HTML context or use a template engine with proper escaping. Content-ID does not protect the HTML section from HTML injection.

### 15.6. Base64 is not security encryption

Base64 is an encoding for transporting binary data in MIME. Anyone with the email can decode the file or image. If content requires protection, use document encryption or an authenticated download channel per requirements, rather than relying on whether a file is an attachment or inline.

## 16. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| PDF missing from file list | `addAttachment` not called or message is not multipart | Use `MimeMessageHelper` in multipart mode |
| Image not rendered in HTML | Missing CID part or mismatched ID | Use `addInline` and align `cid:` |
| Used `addAttachment` for logo and HTML cannot find it | Attachment lacks the expected Content-ID | Use `addInline` for HTML-referenced images |
| Used `addInline` for PDF when recipient wants to download | API expresses inline intent | Use `addAttachment` |
| HTML renders raw `<img>` tag | `setText(..., false)` or body is not HTML | Use `setText(html, true)` |
| Inline image listed as attachment | Email client presentation behavior | Inspect MIME; accept UI differences if structure is valid |
| Message too large | Too many files/images or high-resolution images | Optimize and limit total size |
| Corrupted attachment | Wrong MIME type or data pre-encoded in Base64 | Pass raw bytes and declare the right type |
| Garbled filename | Special characters or overly long filename | Validate name and let the library encode headers |
| Inline image unreadable | Wrong resource path or non-repeatable stream | Use a valid, re-openable resource |
| Email fails to reach inbox | Delivery error, bounce, or spam | Distinguish SMTP acceptance from delivery |

### 16.1. HTML has cid without calling addInline

Example of a missing part:

~~~html
<img src="cid:logo" alt="Logo">
~~~

If the code never calls:

~~~java
helper.addInline("logo", logoResource, "image/png");
~~~

then the email has no data identified as **logo** for the client to find. The `img` tag is only a reference.

### 16.2. Calling addInline with a different Content-ID

Wrong:

~~~java
helper.addInline("brandLogo", logoResource, "image/png");
~~~

HTML:

~~~html
<img src="cid:companyLogo">
~~~

They must match:

~~~java
helper.addInline("companyLogo", logoResource, "image/png");
~~~

### 16.3. Not enabling multipart

If the helper is created with `multipart=false` or mode `NO`, there is no proper structure for separate parts. Choose the mode based on content types.

### 16.4. Calling setText after addInline

Call `setText` before `addInline` as recommended by Spring Mail to minimize differences across email clients.

### 16.5. Assuming SMTP send success means the image rendered

SMTP accepting the message is only one milestone. The receiving client still parses MIME, picks a body, and decides whether to display images. Inspect raw MIME in an SMTP capture server and test on target clients when needed.

## 17. Testing attachments and inline resources

Message parts can be verified in development without sending to real mailboxes.

### 17.1. Testing attachments

Verify:

- The message is multipart.
- An attachment part exists.
- The filename is correct.
- The Content-Type is correct.
- Decoded part bytes match the source data.

### 17.2. Testing inline resources

Verify:

- HTML contains **src="cid:..."**.
- A MIME part exists with the matching Content-ID.
- The part has the expected content type.
- The message uses `multipart/related` or an appropriate mixed/related structure.
- The body is set before calling `addInline`.

### 17.3. Using an SMTP capture server

An SMTP capture server receives emails in a test environment so you can inspect:

- Message headers.
- MIME tree.
- Attachment filenames.
- Content-IDs.
- HTML and plain-text contents.
- Message size.

This is the right way to determine whether a bug stems from application MIME generation or final client rendering. Never use real user mailboxes for automated tests.

### 17.4. Do not assert against fixed boundaries

MIME boundaries are typically generated automatically. Tests should validate content and structure via parsers/APIs rather than assuming a fixed boundary string or a single Base64 line-wrapping layout.

## 18. Choosing the API based on requirements

| Requirement | API to use | Typical multipart mode |
| --- | --- | --- |
| Send PDF for download | **addAttachment** | **MIXED** |
| Send CSV for download | **addAttachment** | **MIXED** |
| Display logo in HTML | **addInline** | **RELATED** |
| Display chart in HTML | **addInline** | **RELATED** |
| HTML with logo and PDF attachment | **addInline + addAttachment** | **MIXED_RELATED** |
| Plain text and HTML in one message | **setText(plain, html)** | Per required multipart structure |
| Multiple independent attachments | Multiple **addAttachment** calls | **MIXED** |
| Multiple CID-referenced HTML images | Multiple **addInline** calls with unique IDs | **RELATED** or **MIXED_RELATED** |

This is a common selection guide. The exact mode also depends on whether the message has alternative bodies, inline resources, and other parts.

## 19. Frequently asked questions

**1. Are attachments and inline resources completely different file types?**

No. Both can be images, PDFs, or other content types packaged as MIME parts. The primary difference is intended use and how the part is linked/presented in the message.

**2. Can addAttachment be used to display an image inside HTML?**

Do not rely on `addAttachment` for that purpose. If HTML references via `cid:`, use `addInline` to create the part with the matching Content-ID.

**3. Does addInline make images appear in every email client?**

No. Clients may hide images, choose plain text, or handle MIME differently. Test on target clients and keep essential information in text form.

**4. Is Content-ID the image filename?**

No. Content-ID is an identifier for HTML to locate the part. Filename and Content-ID can differ.

**5. Why is multipart/related needed?**

Because HTML and inline images are related parts forming one complete body. `multipart/related` describes that relationship to MIME clients.

**6. When is multipart/mixed needed?**

When a message contains independent parts, usually a body alongside attachments. If related resources are also present, mixed can wrap the related branch.

**7. Can both addInline and addAttachment be used in one email?**

Yes. Choose **MULTIPART_MODE_MIXED_RELATED**, set the body, add inline resources, and then add attachments.

**8. Is send needed for each file?**

No. Add all parts to a single `MimeMessage` and call `send` once.

**9. Can an inline image show up in the attachment list?**

Possibly, depending on the email client. `Content-Disposition: inline` is a presentation hint, not a mandate enforced on every client's UI.

**10. Do CID images increase email size?**

Yes. Image data is packaged inside the message and usually Base64-encoded, increasing transport size.

**11. Should every image be embedded via CID?**

Not necessarily. For logos or images that must travel with the message, CID works well. For large images or content updated independently, HTTPS URLs may be better if remote image policies are acceptable.

**12. Can a PDF be attached using ByteArrayResource?**

Yes. Wrap `byte[]` in `ByteArrayResource` and pass it to `addAttachment` with filename and MIME type.

**13. Does SimpleMailMessage support attachments or inline resources?**

No. Use `MimeMessage` and `MimeMessageHelper`.

**14. Does a successful send guarantee the recipient downloaded the file or saw the image?**

No. SMTP acceptance, delivery, rendering, and recipient actions are separate milestones.

## 20. Key takeaways when distinguishing attachments from inline resources

An **attachment** is an independent file added via **MimeMessageHelper.addAttachment(...)**, typically with a filename and **Content-Disposition: attachment**. An **inline resource** is a resource referenced by the body, usually added via **addInline(...)**, carrying a **Content-ID** and located by HTML via a **cid:** URL.

In MIME structure, **multipart/mixed** typically holds independent parts like the body and PDFs; **multipart/related** groups HTML with images referenced by that HTML. When an email has both inline images and standalone downloadable documents, **MULTIPART_MODE_MIXED_RELATED** organizes both purposes inside the same message.

Choose the API based on how recipients need to use the data: use `addAttachment` for downloadable files and `addInline` for HTML-referenced resources; set the body before adding inline resources, specify accurate MIME types, and control filenames, sizes, file sources, and recipient permissions. Email clients can still render differently, so critical information should remain in text and message structures should be tested in a test environment.

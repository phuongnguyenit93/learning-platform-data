# Naming Resources and Content Types

## 1. What is an inline resource?

In **Spring Framework Mail**, an HTML email can display an image directly inside the message body, such as a company logo, status icon, or invoice illustration. The recipient sees the image alongside the content without having to load it from an external URL. This approach is commonly called an **inline resource** or **inline image**.

An email with inline images typically uses a **Content-ID (CID)**. The HTML references the image using a `cid:...` URL, while the image is packaged as a separate MIME part inside the same email. Example:

~~~html
<p>Your report is ready.</p>
<img src="cid:brand-logo" alt="Company logo">
~~~

In the MIME message, the image part has a matching `Content-ID` header:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <brand-logo>
~~~

When an email client processes `src="cid:brand-logo"`, it locates the MIME part with `Content-ID: <brand-logo>` to display the image bytes at that position.

Spring provides `MimeMessageHelper.addInline(...)` to add inline resources. Three pieces of information must be distinguished:

| Information | Role | Example |
| --- | --- | --- |
| **Content-ID** | Identifier of the MIME part for HTML reference | `brand-logo` |
| **Resource name** | Descriptive name of the data source, often resembling a filename | `brand-logo.png` |
| **Content-Type** | Media type of the bytes inside the MIME part | `image/png` |

These three values are not interchangeable. Setting the proper resource name and content type helps the email client know **which part is referenced by HTML** and **what content type the bytes inside should be interpreted as**.

## 2. Distinguishing Content-ID, resource name, and Content-Type

### 2.1. Content-ID: the name used in the cid URL

**Content-ID** is the identifier of a MIME body part. With `MimeMessageHelper`, pass the ID as the first argument to `addInline`:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png");
~~~

The HTML must use the same ID:

~~~html
<img src="cid:brand-logo" alt="Company logo">
~~~

Spring/Jakarta Mail will generate a MIME header of the form:

~~~text
Content-ID: <brand-logo>
~~~

In the string passed to `addInline` and the value after `cid:`, you generally **do not write angle brackets**. The `<` and `>` characters belong to the MIME header representation of `Content-ID`:

| Where it appears | Value |
| --- | --- |
| `contentId` argument of `addInline` | `brand-logo` |
| HTML `src` | `cid:brand-logo` |
| MIME header after serialization | `Content-ID: <brand-logo>` |

If you manually add angle brackets to the ID passed to the helper, the header may be formatted unexpectedly or fail to match the CID URL. Pass a clean identifier and use it consistently in the HTML.

### 2.2. Resource name: descriptive name of the data source

The resource name can be a filename or a descriptive data name, for example:

- `brand-logo.png`
- `invoice-stamp.jpg`
- `status-icon.gif`

In overloads that accept a `name` argument, Spring uses this name when creating the DataSource for the resource. That name **is not the Content-ID**: HTML does not reference it via `cid:brand-logo.png` unless the Content-ID itself was set to that exact string.

Example:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png",
        "brand-logo.png");
~~~

In this call:

- `brand-logo` is the Content-ID.
- `logoResource` supplies the bytes.
- `image/png` is the MIME content type.
- `brand-logo.png` is the name of the data source.

The resource name may be used by providers or mail clients as part/filename metadata when representing the content. Specific display behavior depends on the implementation and client; do not rely on this name to create a standalone downloadable file. If the recipient needs an attachment with a clear display filename, use `addAttachment(...)`.

### 2.3. Content-Type: MIME type of the data

**Content-Type** describes the type of data packaged inside the MIME part. For images:

| Image type | MIME Content-Type |
| --- | --- |
| PNG | `image/png` |
| JPEG/JPG | `image/jpeg` |
| GIF | `image/gif` |
| WebP | `image/webp` |
| SVG | `image/svg+xml` |

The file extension and content type must match the actual bytes. For example, renaming a JPEG file to `logo.png` does not turn JPEG content into PNG.

In emails, PNG, JPEG, and GIF are generally the more common choices. SVG and WebP support can vary by client and security policy; if broad compatibility is needed, test your target client group and consider converting images to PNG/JPEG.

Do not use `application/octet-stream` for an image when the image type is already known. Some clients will not recognize that part as an image to display inline. A wrong content type can also prevent the image from rendering or cause it to be treated as a file attachment.

## 3. MimeMessageHelper addInline API

`MimeMessageHelper` provides overloads accepting data from a `DataSource` or `InputStreamSource`. Common forms:

~~~java
helper.addInline(contentId, dataSource);
helper.addInline(contentId, dataSource, contentType);

helper.addInline(contentId, inputStreamSource, contentType);
helper.addInline(contentId, inputStreamSource, contentType, name);
~~~

| Argument | Meaning |
| --- | --- |
| `contentId` | ID of the MIME part, referenced by HTML via `cid:...` |
| `dataSource` | Source supplying bytes and metadata to Jakarta Mail |
| `inputStreamSource` | Source opening an InputStream to read the resource bytes |
| `contentType` | MIME type such as `image/png` |
| `name` | Descriptive name of the DataSource, typically a filename like `brand-logo.png` |

### 3.1. Using Spring's Resource

`org.springframework.core.io.Resource` implements `InputStreamSource`, so it can be passed directly into `addInline` overloads:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource logo = new ClassPathResource("mail/brand-logo.png");

helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

`ClassPathResource` reads resources packaged on the classpath, for example:

~~~text
src/main/resources/
└── mail/
    └── brand-logo.png
~~~

The path passed to `ClassPathResource` is relative to the classpath. When the application is packaged as a JAR, the resource can still be read from the classpath without assuming it exists as a standalone file on disk.

### 3.2. Using FileSystemResource

If the image resides in a filesystem directory managed by the application:

~~~java
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource logo = new FileSystemResource(
        "/opt/mail-assets/brand-logo.png");

helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

The path in the example is illustrative. In production, the directory must be explicitly configured and granted permissions. Never take an absolute path directly from a user request and pass it into `FileSystemResource`, as that could allow reading files outside the intended data area.

### 3.3. Using ByteArrayResource for in-memory data

If the image bytes are already in memory, you can use `ByteArrayResource`:

~~~java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

byte[] logoBytes = loadLogoBytesFromTrustedStorage();
Resource logo = new ByteArrayResource(logoBytes);

helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

`ByteArrayResource` opens a fresh stream from its byte array. This is a good choice when the data has already been read into memory and its size is bounded. Do not load unboundedly large images onto the heap solely to send emails.

## 4. Rules for choosing Content-IDs

Content-IDs should be stable within a single message and must match the CID URL in the HTML exactly.

### 4.1. Use meaningful and unique IDs

Example:

~~~java
helper.addInline("company-logo", logo, "image/png", "company-logo.png");
helper.addInline("invoice-stamp", stamp, "image/png", "invoice-stamp.png");
helper.addInline("status-icon", statusIcon, "image/gif", "status-icon.gif");
~~~

HTML:

~~~html
<img src="cid:company-logo" alt="Logo">
<img src="cid:invoice-stamp" alt="Invoice stamp">
<img src="cid:status-icon" alt="Status">
~~~

Each ID should describe the purpose of the image and not be duplicated within the same email. If multiple images share the same Content-ID, clients may pick the wrong part or fail to display properly.

### 4.2. Avoid characters that cause trouble in CID URLs

Choose simple IDs with no whitespace, angle brackets, or character sequences requiring percent-encoding. Example:

~~~text
company-logo
invoice-stamp
status-icon-2026
~~~

Do not pass an entire file path as the Content-ID:

~~~java
// Avoid: a path is not a CID identifier.
helper.addInline("/opt/mail-assets/brand-logo.png", logo, "image/png");
~~~

Content-ID is a MIME identifier, not a filename or a server URL. If an ID contains special characters allowed by Message-ID syntax, the CID URL must be expressed according to the corresponding URI rules; in typical applications, using short, simple ASCII IDs avoids errors.

### 4.3. Generate unique IDs when needed

If an email is assembled from multiple independent components and needs to avoid collisions, you can generate an ID with a unique suffix:

~~~java
String contentId = "logo-" + java.util.UUID.randomUUID();
helper.addInline(contentId, logo, "image/png", "brand-logo.png");

String html = "<img src=\"cid:" + contentId + "\" alt=\"Logo\">";
helper.setText(plainText, html);
~~~

This example illustrates using the same variable for both the helper and the HTML. For a static template with just one logo, a fixed ID like `company-logo` is often simpler. A UUID does not make the image more secure; it simply reduces the risk of ID collisions when multiple resources are generated dynamically.

## 5. Setting the exact Content-Type

Content-Type should describe **the actual byte format**, not merely the filename extension.

### 5.1. Declare the content type explicitly

~~~java
helper.addInline("brand-logo", logoPng, "image/png", "brand-logo.png");
helper.addInline("avatar", avatarJpeg, "image/jpeg", "avatar.jpg");
helper.addInline("animated-status", statusGif, "image/gif", "status.gif");
~~~

When using the three-argument overload, the resource name is not passed explicitly:

~~~java
helper.addInline("brand-logo", logoPng, "image/png");
~~~

In this case, the data source must still be readable; the helper uses the content type to build the MIME part, while the source name is taken from the DataSource created for the resource according to the overload/implementation.

### 5.2. Do not guess content type solely from the filename

A file named `image.png` is not guaranteed to contain a valid PNG. If a file comes from an upload or external source:

1. Check the maximum allowed size before reading all bytes.
2. Check format signatures (magic bytes) or use an image-processing library to detect the true type.
3. Permit only the required set of formats such as PNG/JPEG/GIF.
4. Attempt to decode the image if business requirements need to ensure structurally valid data.
5. Choose Content-Type from the verification result rather than trusting the MIME header sent by the client directly.

The goal is to prevent non-image bytes from being labeled `image/png`, or malicious/invalid content from entering emails.

### 5.3. SVG and less-compatible formats

SVG is an XML-based vector image format with rich expressive power. Some mail clients may block or refuse to render inline SVGs due to security policies and compatibility concerns. If you need logos to render across many clients, PNG or JPEG are usually more predictable choices.

WebP may also not be uniformly supported across all clients and versions. If you use SVG/WebP, test real emails on your target applications and provide an appropriate fallback. Do not assume `image/svg+xml` or `image/webp` guarantees client rendering.

## 6. Complete example: adding an inline logo to an HTML email

The example below uses `ClassPathResource` and `MimeMessageHelper`:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailer {

    private final JavaMailSender mailSender;

    public ReportMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReportReady(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your report is ready");

        Resource logo = new ClassPathResource("mail/brand-logo.png");

        String plainText = "Your report is ready.";
        String html = """
                <html lang="en">
                  <body>
                    <p>Your report is ready.</p>
                    <img src="cid:brand-logo"
                         alt="Company logo"
                         width="160"
                         style="display:block;width:160px;height:auto;">
                  </body>
                </html>
                """;

        // Set the body before adding inline resources.
        helper.setText(plainText, html);

        helper.addInline(
                "brand-logo",
                logo,
                "image/png",
                "brand-logo.png");

        mailSender.send(message);
    }
}
~~~

The image file is located at:

~~~text
src/main/resources/mail/brand-logo.png
~~~

Roles of the values in the example:

| Value | Role |
| --- | --- |
| `"brand-logo"` in `addInline` | Content-ID of the image part |
| `cid:brand-logo` in HTML | Reference to the part with that Content-ID |
| `logo` | Resource supplying the PNG bytes |
| `"image/png"` | MIME Content-Type |
| `"brand-logo.png"` | Descriptive name of the data source |
| `MULTIPART_MODE_MIXED_RELATED` | Structure suited for a body with inline resources and optional attachments |

**Call order matters:** set the body with `setText(...)` before calling `addInline(...)`. This lets the helper build the related MIME structure properly and avoids errors from creating the inline part before the HTML part referencing it exists.

This example sends only the inline logo. If you also need to attach a standalone PDF, you can follow up with `helper.addAttachment("report.pdf", reportResource)` on the same multipart helper.

## 7. MIME tree of an email with inline resources

An HTML email with a plain-text fallback and an inline logo typically has this conceptual structure:

~~~text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain; charset=UTF-8
    │   └── text/html; charset=UTF-8
    │       <img src="cid:brand-logo">
    └── image/png
        Content-ID: <brand-logo>
        Content-Disposition: inline
~~~

If the message has both inline resources and standalone attachments, the tree typically has an outer `multipart/mixed`:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   │       <img src="cid:brand-logo">
    │   └── image/png
    │       Content-ID: <brand-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="report.pdf"
~~~

This is a typical structure illustrating the relationships among parts; the exact tree depends on the multipart mode and how the message is constructed. `multipart/related` groups the body with resources referenced by the body; `multipart/alternative` holds alternative versions of the content; `multipart/mixed` groups independent parts such as attachments.

## 8. Distinguishing addInline and addAttachment

Both methods add a MIME part, but their purposes differ:

| API | Meaning | How recipients typically see it |
| --- | --- | --- |
| `addInline(contentId, ...)` | Resource referenced from the body via `cid:...` | Image appears right inside the HTML content if supported by the client |
| `addAttachment(name, ...)` | Standalone file attached to the message | Appears in the attachment list for the recipient to download/open |

Example:

~~~java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png",
        "brand-logo.png");

helper.addAttachment(
        "report.pdf",
        new ClassPathResource("reports/report.pdf"));
~~~

HTML references only the logo:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

The PDF does not need a CID because it is a standalone attachment. Adding `report.pdf` with `addInline` without any `cid:...` reference may prevent the part from being handled as expected. Conversely, using `addAttachment` for the logo usually causes the image to appear as a downloadable file instead of in its place in the body.

## 9. InputStreamSource must be readable at send time

`MimeMessageHelper.addInline` accepts an `InputStreamSource`. Note the contract of this source: MIME construction/serialization may request opening a stream multiple times. Therefore, **each call to `getInputStream()` should provide a fresh stream readable from the start**.

Commonly suitable sources:

| Source | Characteristics |
| --- | --- |
| `ClassPathResource` | Reopens the resource from the classpath |
| `FileSystemResource` | Reopens the file at a permitted path |
| `ByteArrayResource` | Supplies a fresh stream from in-memory bytes |
| Custom `InputStreamSource` implementation | Must guarantee streams can be reopened per contract |
| `InputStreamResource` backed by an open stream | Typically single-read; unsuitable if MIME processing needs to reopen |

Avoid creating an `InputStream`, draining it, and wrapping it in a source that returns the same consumed stream. If data comes from a one-shot stream, read it into a bounded buffer to build a `ByteArrayResource`, or use a storage source capable of reopening.

Simple custom source example:

~~~java
byte[] bytes = loadAndValidateImage();
InputStreamSource source = () -> new ByteArrayInputStream(bytes);
~~~

Each time `getInputStream()` is called, the lambda creates a new `ByteArrayInputStream` from the start of the byte array. Bound the size before holding bytes in memory.

## 10. Common errors in naming and content types

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| HTML has `cid:brand-logo` but image does not show | Content-ID passed to helper does not match | Read the `Content-ID` header in raw MIME |
| Image appears as an attachment | Mistakenly used `addAttachment` or client handles inline parts its own way | Inspect `Content-Disposition` and the MIME tree |
| Image part has a name but HTML cannot find it | Confusing resource name with Content-ID | Compare `cid:...` with `Content-ID`, not with filename |
| Image fails to decode | Content-Type does not match bytes | Determine actual image format, inspect MIME headers |
| Image downloads as an unknown file type | Used `application/octet-stream` or missing proper media type | Set `image/png`, `image/jpeg`, etc. based on bytes |
| Only one of several images displays | Duplicate CID or one CID is wrong | Give each part a unique ID; check every reference |
| Image has no data | Empty resource, wrong path, or missing read permission | Check data source and size |
| Stream error on send | Single-use source or closed stream | Use a re-readable Resource or buffer bytes |
| SVG image does not display in some clients | Client does not support or blocks SVG | Choose PNG/JPEG fallback and test clients |
| Image renders in one client but disappears in another | Differences in MIME/HTML support or image policies | Inspect raw MIME and test target clients |

### 10.1. Mismatched Content-ID

Erroneous example:

~~~java
helper.addInline("company-logo", logo, "image/png");
~~~

while the HTML writes:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

The two strings differ, so the client cannot find the part. Use a single constant or variable:

~~~java
String logoId = "company-logo";
helper.addInline(logoId, logo, "image/png");
String html = "<img src=\"cid:" + logoId + "\" alt=\"Logo\">";
~~~

### 10.2. Setting the wrong content type

If the bytes are JPEG yet declared as `image/png`, clients may fail to decode them properly. Derive the content type from actual format detection, not solely from the filename or a request MIME header.

### 10.3. Confusing resource name with attachment filename

The `name` argument of `addInline` overloads helps describe the DataSource; it does not turn an inline resource into a standalone downloadable attachment. If the requirement is for the recipient to download a file with a specific name, use:

~~~java
helper.addAttachment("invoice.pdf", invoiceResource);
~~~

and let the helper manage `Content-Disposition: attachment` for that part.

### 10.4. Calling addInline before setText

Follow this order:

~~~java
helper.setText(plainText, html);
helper.addInline("brand-logo", logo, "image/png", "brand-logo.png");
~~~

The body is set first so the helper can organize inline parts associated with the HTML. Adding inline parts too early may cause some MIME structures or clients to behave unexpectedly.

## 11. Inspecting the generated MIME message

In a test environment, you can serialize `MimeMessage` to an `.eml` file to check names, CIDs, and Content-Type:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

String logoId = "brand-logo";
Resource logo = new ClassPathResource("mail/brand-logo.png");
String html = "<p>Your report is ready.</p>"
        + "<img src=\"cid:" + logoId + "\" alt=\"Logo\">";

helper.setFrom("reports@example.com");
helper.setTo("test@example.net");
helper.setSubject("Inline resource check");
helper.setText("Your report is ready.", html);
helper.addInline(logoId, logo, "image/png", "brand-logo.png");

message.saveChanges();
try (OutputStream output =
             Files.newOutputStream(Path.of("inline-preview.eml"))) {
    message.writeTo(output);
}
~~~

This example assumes appropriate imports for `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path`, and handling of `IOException`/`MessagingException`. This snippet only writes the message to a file; **it does not send an email** because `mailSender.send(message)` is not called.

In the raw MIME, check:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <brand-logo>
~~~

Headers may appear in a different order or include extra parameters, but the meaning should align:

- `Content-ID` must match the CID URL in the HTML.
- `Content-Type` must describe the image bytes.
- `Content-Disposition` indicates the part is intended for inline use.
- Part bytes must be non-empty and form a valid image.

For real emails, raw MIME may contain sensitive data or private content. Export and save test files only in authorized locations, use sample recipients/images, and delete data per retention policy.

## 12. Testing through an SMTP sink and mail clients

Inspecting raw MIME alone does not guarantee every mail client renders identically. A useful testing workflow:

1. Use a small sample PNG image on the classpath.
2. Build a message with a fixed Content-ID, accurate content type, and clear resource name.
3. Send to a local SMTP sink such as Mailpit/MailHog instead of customer mailboxes.
4. View the received message and inspect MIME parts and HTML CID references.
5. Open the email in Gmail, Outlook, and Apple Mail among your product's supported clients.
6. Test with external images blocked, while verifying whether CID images are displayed per client behavior.
7. Test multiple images in the same message to catch duplicate CIDs or wrong references.

An SMTP sink confirms the application sent the email to the test environment and lets you inspect MIME. It does not prove how a production provider or every client will render the image.

## 13. Security and managing inline resources

Inline images are still data embedded in the email. Manage their source and size:

- Only use resources from the classpath, controlled directories, or storage systems the application is authorized to access.
- If users upload images, validate byte formats, enforce size limits, and sanitize/process images before sending.
- Do not trust client-supplied filenames or Content-Types.
- Do not read arbitrary paths from requests.
- Do not embed images containing sensitive information into emails if the recipient is not authorized to view them.
- Use IDs that do not contain personal data or tokens.
- Watch total MIME size after encoding; attachments/inline images make emails larger than the original raw files.
- Avoid using images to convey exclusive information; always provide text or meaningful alt text.

Content-ID is only a **MIME identifier**, not an authentication mechanism or access code. Never place secrets, access tokens, or personal information into a CID assuming the ID is protected.

## 14. Frequently asked questions

**"Is Content-ID the image filename?"**  
No. Content-ID is the identifier referenced by HTML via `cid:...`. Filename/resource name is separate metadata.

**"Why does the helper take `brand-logo` while the header has angle brackets?"**  
That is the MIME header representation `Content-ID: <brand-logo>`. In HTML use `cid:brand-logo`, without angle brackets.

**"Can Content-Type be inferred from the file extension?"**  
An extension is a hint, not proof. For uploaded data, detect the actual byte format and allow only supported types.

**"Can the resource name differ from the Content-ID?"**  
Yes. For example, Content-ID can be `company-logo` while the resource name is `brand-logo.png`. HTML must use the CID, not the resource name, unless both values are intentionally set to the same string.

**"Is it okay to use `image/png` for a JPEG file?"**  
No. Content-Type must describe the actual format. Misdeclaring it can prevent clients from decoding or displaying it properly.

**"Can the same CID be used for two images?"**  
No. Each inline part in a message needs a distinct identifier so HTML references are unambiguous.

**"Does `addInline` automatically insert the image into HTML?"**  
No. The helper adds the MIME part; the HTML must still contain `<img src="cid:...">` referencing the matching Content-ID.

**"Can HTTPS URLs be used instead of CID?"**  
Images can be embedded from external URLs, though clients may block loading or proxy them. CID packages images inside the message; the two approaches have different characteristics and trade-offs.

**"Can a single-read resource be used?"**  
Avoid using it directly if sending/serialization needs to open the stream multiple times. Use a re-readable Resource or buffer bounded bytes into a `ByteArrayResource`.

**"Are SVG images suitable for all mail clients?"**  
No. Some clients block or fail to render SVG. For broad compatibility, consider PNG/JPEG and test on target clients.

## 15. Takeaways for naming resources and content types

A valid inline resource needs three consistent values:

~~~text
HTML:
  <img src="cid:brand-logo">
                 |
                 | same Content-ID
                 v
MIME part:
  Content-ID: <brand-logo>
  Content-Type: image/png
  Content-Disposition: inline
  DataSource name: brand-logo.png
  Body: valid PNG bytes
~~~

In Spring Framework Mail, use `MimeMessageHelper.addInline(contentId, resource, contentType, name)` when you want to explicitly specify the ID, byte source, MIME type, and resource name. Keep **Content-ID** matching the CID URL in the HTML, choose **Content-Type** based on actual byte format, and treat **resource name** as descriptive metadata. Combining these three elements properly with a multipart structure and a re-readable stream source keeps inline images cleanly packaged, easy to verify, and more compatible across email applications.

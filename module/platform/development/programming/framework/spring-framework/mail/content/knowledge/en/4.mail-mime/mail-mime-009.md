# MIME: Content-Disposition `inline` and `attachment` in Spring Framework Mail

An email can contain plain text, HTML, images appearing right inside the message body, and files for the recipient to download. To describe each such part, email systems use **MIME (Multipurpose Internet Mail Extensions)**. One particularly important header is **`Content-Disposition`**: it provides a hint to the mail-reading application on how to present a MIME part, typically **`inline`** (displayed alongside the content) or **`attachment`** (handled as an attached file).

In **Spring Framework Mail**, you usually do not need to assemble MIME headers by hand. `JavaMailSender`, `MimeMessage`, and `MimeMessageHelper` allow creating multi-part messages, attaching documents via `addAttachment(...)`, and adding inline resources via `addInline(...)`. To use them properly, you need to understand how `Content-Disposition` interacts with `Content-Type`, `Content-ID`, and the `multipart/*` structure.

## 1. What is a MIME part and what is Content-Disposition used for?

An ordinary email has a header section and a body. When an email uses MIME, the body can be split into multiple **parts**; each part has its own headers describing content type, encoding, and presentation.

Example of a part that is a PDF file:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK... (abbreviated base64 content)
```

Three headers serve different roles:

| Header | Question answered | Example |
|---|---|---|
| `Content-Type` | What type of data is inside the part? | `application/pdf`, `image/png`, `text/html; charset=UTF-8` |
| `Content-Disposition` | How should the mail-reading application present the part? | `inline` or `attachment`; may include `filename` |
| `Content-Transfer-Encoding` | How is the content represented for transmission over email? | `base64`, `quoted-printable` |
| `Content-ID` | Does this part have an identifier for another part of the message to reference? | `<brand-logo>`, referenced by `cid:brand-logo` |

`Content-Disposition` is **not a file format** and does not determine the actual content of the data. Nor is it a binding command for every mail client: a mail-reading application may apply its own rules for security, file type, or user experience reasons.

The header has typical syntax:

```text
Content-Disposition: inline
Content-Disposition: attachment; filename="report.pdf"
Content-Disposition: inline; filename="chart.png"
```

The two values `inline` and `attachment` are **disposition types**. `filename` is an optional parameter helping suggest a name when saving the data part to a file. An inline part does not necessarily need a file name; an attachment part may be previewed directly in the UI without downloading.

## 2. `inline`: content suggested to display alongside the message

`Content-Disposition: inline` indicates that the part is intended to be displayed directly within the context of viewing the message, when content type and mail client policy allow.

Common scenarios:

- A logo image in an HTML email, displayed via `<img src="cid:brand-logo">`.
- A chart image embedded in a report email, avoiding reliance on external Internet image URLs.
- A text part that the mail-reading application chooses to display immediately when opening the message.

Example MIME part of a PNG image:

```text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <brand-logo>
Content-Transfer-Encoding: base64

iVBORw0KGgoAAA... (abbreviated image data)
```

For the image to appear at the desired spot in HTML, the HTML section of the email can contain:

```html
<p>Welcome!</p>
<img src="cid:brand-logo" alt="Company logo" width="120">
```

The `cid:brand-logo` portion in HTML points to the part carrying the header `Content-ID: <brand-logo>`. This is a **content identifier**, not an HTTP URL and not a file path on the sender's machine. The name `brand-logo` only needs to match consistently between the HTML part and the corresponding MIME part.

**Note:** setting `Content-Disposition: inline` alone **does not make an image magically appear at any spot in HTML**. To insert content at a specific position, HTML must reference the part via `cid:...` and the message must organize the parts in an appropriate MIME structure. Some mail clients may still list inline images in the “attachments” list or block rendering certain content types.

### Why do inline images sometimes still show up as files?

Email reading systems vary widely: webmail browsers, desktop apps, mobile apps, and security filters. Software may:

1. Not support `cid:` resources well for a certain display mode.
2. Fail to find a `Content-ID` matching the HTML.
3. Block certain MIME types such as SVG or executable content.
4. Display every part carrying a file name in a secondary area, even when disposition is `inline`.
5. Apply custom rules for `multipart/related` structures.

Therefore, **`inline` expresses rendering intent**, without guaranteeing every mail client renders identically. For messages needing consistent display, use common PNG/JPEG images, simple HTML, and add alternative text via `alt`.

## 3. `attachment`: content suggested to be handled as an attached file

`Content-Disposition: attachment` indicates that the part should normally be listed and handled as a separate file. Mail clients may offer a preview, opening with a suitable application, or downloading.

Example:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-2026.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK... (abbreviated PDF data)
```

In this example:

- `application/pdf` describes the content type.
- `attachment` expresses attachment intent.
- `filename="invoice-2026.pdf"` supplies the display name or default name when saving.
- `base64` is how binary data is represented in email; it is **not secret encryption**.

A PDF file may still be previewed directly inside the email window by the mail client. That is a client feature and does not contradict `attachment` disposition. Conversely, a part marked `inline` might not be rendered directly if the client lacks support.

### How do `filename` and `name` differ?

Sometimes a MIME part has both:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
```

`name` is a parameter of `Content-Type` commonly seen in older messages; `filename` is a parameter of `Content-Disposition` intended for file names. In modern software, pass the name via the attachment API and let the MIME library encode the appropriate headers. Never concatenate these headers manually from user data.

File names with accents, spaces, or special characters must be represented per corresponding MIME encoding standards; decoding behavior varies by client. Test Unicode file names on your target clients. Avoid putting system paths like `C:\Users\...\invoice.pdf` into filename: recipients usually only need the file name, and exposing server directory structure is unnecessary.

## 4. Direct comparison of `inline` and `attachment`

| Criterion | `inline` | `attachment` |
|---|---|---|
| Purpose | Suggests rendering within the message viewing context | Suggests presenting as a separate file |
| Typical cases | Logos, charts, resources of an HTML email | PDF invoices, CSV reports, contract documents |
| `Content-Disposition` | `inline` | `attachment` |
| Need `filename`? | Not required | Recommended when data is a downloadable file |
| Need `Content-ID`? | When the part needs to be referenced via `cid:` | Usually not needed |
| How HTML points to the resource | `src="cid:..."` when Content-ID is present | Usually not referenced inside HTML |
| Spring Mail API | `MimeMessageHelper.addInline(...)` | `MimeMessageHelper.addAttachment(...)` |
| Actual rendering | Depends on mail client and MIME structure | May be previewed directly inside the mail client |
| Guarantees security? | No; merely presentation metadata | No; files still need type and content controls |

An easy rule of thumb: if the resource is **part of the HTML email's presentation**, use inline and Content-ID; if the resource is **a file the recipient needs to view, save, or process separately**, use attachment.

## 5. How does Content-Disposition work with `multipart/*`?

An HTML email with an inline image and an attached PDF is not just three parts placed side by side. The `multipart/*` structure tells the client which parts are display alternatives of the same content, which parts relate to HTML, and which parts are supplementary files.

Three important multipart types:

| Type | Meaning |
|---|---|
| `multipart/alternative` | Multiple alternative versions of **the same content** (e.g., text/plain and text/html); client picks the suitable version |
| `multipart/related` | One primary content along with resources needed to display it (e.g., HTML and CID images) |
| `multipart/mixed` | Message holding independent parts grouped together, typically message body and attached files |

An **illustrative** MIME tree for an email with plain text, HTML, logo, and PDF:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   │       (contains <img src="cid:brand-logo">)
    │   └── image/png
    │       Content-ID: <brand-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment; filename="invoice.pdf"
```

How to read the structure:

- `alternative` lets the mail-reading app choose the HTML or plain text version based on capabilities and user settings.
- `related` links the HTML content with the inline image; the image has a `Content-ID` matching the `cid:` reference.
- `mixed` adds the independent PDF file to the same email.

This is a typical logical structure, **not a mandatory header ordering for every message emitted by every library version**. Exact ordering and nesting can differ depending on multipart mode and how the message was built. What matters is that parts have the right relationships and receiving software can choose a sensible display version.

### Why not just use `multipart/mixed` for everything?

If all parts are placed at the same level inside `multipart/mixed`, clients may treat the logo image as an extra file rather than an HTML resource. `multipart/related` clearly expresses the relationship between primary content and supporting resources, improving the likelihood of accurate rendering across clients.

In Spring, `MimeMessageHelper` supports multiple multipart modes. `MULTIPART_MODE_MIXED_RELATED` fits when an email has **both inline resources and attachments**: it organizes parts in a mixed-and-related model. `MULTIPART_MODE_RELATED` fits emails needing HTML and inline resources; `MULTIPART_MODE_MIXED` can be useful for simple attachment cases or specific compatibility needs. The final choice should account for the mail clients your system serves.

## 6. Creating an email with both an inline image and a PDF attachment in Spring Mail

Spring Framework provides `JavaMailSender`; for Spring Boot applications, usually add the dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

The application also needs an SMTP submission server configured via `spring.mail.host`, `spring.mail.port`, credentials, and appropriate TLS properties. Using inline/attachment is a MIME formatting matter; it **does not replace** SMTP connection configuration.

### Example invoice-sending service

The example below receives pre-built PNG and PDF data as `byte[]`, builds plain text and HTML bodies, embeds the logo via `cid:`, and adds the invoice as an attachment.

```java
package com.example.notification;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public InvoiceMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendInvoice(
            String recipient,
            byte[] logoPng,
            byte[] invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Your invoice");

        String plainText = "Thank you for your purchase. "
                + "Please see the attached PDF invoice.";

        String htmlText = """
                <!doctype html>
                <html>
                  <body>
                    <p><img src="cid:brand-logo"
                            alt="Store logo" width="120"></p>
                    <h2>Thank you for your purchase!</h2>
                    <p>The PDF invoice is attached to this email.</p>
                  </body>
                </html>
                """;

        // Set the content before adding inline resources.
        helper.setText(plainText, htmlText);

        helper.addInline(
                "brand-logo",
                new ByteArrayResource(logoPng),
                "image/png");

        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(invoicePdf),
                "application/pdf");

        mailSender.send(message);
    }
}
```

What to understand from the example:

1. `MimeMessage` allows an email to hold multiple MIME parts. `SimpleMailMessage` does not provide a way to create MIME structures with HTML and attachments like this.
2. `MULTIPART_MODE_MIXED_RELATED` is specified explicitly for the scenario having both an inline logo and a PDF attachment.
3. `setText(plainText, htmlText)` builds two content versions. Recipients using HTML-capable clients see HTML; plain-text-only clients still receive the main information.
4. `addInline("brand-logo", ...)` adds an image with a content ID corresponding to `cid:brand-logo`. **Do not pass `< >` brackets into the `contentId` parameter**; the helper handles header formatting.
5. `addAttachment("invoice.pdf", ...)` supplies the file name and PDF data so the library builds the attachment part.
6. `ByteArrayResource` permits re-reading byte data when Jakarta Mail needs to prepare or transmit MIME content. For large files, choose file/re-openable stream resources to avoid loading everything into RAM.
7. `mailSender.send(message)` submits the email to the configured SMTP server. Success at this step does not guarantee the message has reached the final mailbox.

The code uses Java text blocks (`"""`), requiring a Java version supporting text blocks. The `jakarta.mail` API corresponds to modern Spring Framework (Spring 6+, Spring Boot 3+); older projects may use the `javax.mail` namespace and must import per the actual version.

### Why call `setText(...)` before `addInline(...)`?

With `MimeMessageHelper`, the recommended order is **setting text/HTML content first, then adding inline resources**. Some mail clients are sensitive to MIME part ordering, and the helper's organization can change when text is set. Keeping this order helps inline images stay linked to HTML reliably.

Attachments can be added after creating content and inline resources. If an email has multiple images, use unique content IDs within the message (`brand-logo`, `summary-chart`, ...) and reference them accordingly in HTML.

## 7. Related Spring Mail APIs

`MimeMessageHelper` offers multiple overloads to consume resources from bytes, files, classpath, or `DataSource`.

| API | Purpose | Characteristics |
|---|---|---|
| `setText(String text, boolean html)` | Sets body as plain text or HTML | `true` is HTML, `false` is plain text |
| `setText(String plainText, String htmlText)` | Supplies both text/plain and text/html | Helps the client pick the appropriate version |
| `addInline(String contentId, InputStreamSource source, String contentType)` | Creates an inline resource | Content ID can be referenced by HTML via `cid:` |
| `addInline(String contentId, Resource resource)` | Inline resource from Spring `Resource` | Must be able to infer suitable content type; for ambiguous cases, use the overload with content type |
| `addAttachment(String attachmentFilename, InputStreamSource source, String contentType)` | Adds attachment with name and MIME type | Useful when data comes from memory or storage |
| `addAttachment(String attachmentFilename, File file)` | Attaches file from filesystem | File must exist and remain readable at send time |
| `addAttachment(String attachmentFilename, DataSource dataSource)` | Attaches Jakarta Activation data | Useful when integrating with other MIME/Jakarta Mail sources |

Example loading a logo from classpath and an existing PDF on the filesystem:

```java
import java.io.File;
import org.springframework.core.io.ClassPathResource;

helper.setText(
        "<p>This month's report: <img src='cid:company-logo'></p>",
        true);

helper.addInline(
        "company-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png");

helper.addAttachment(
        "monthly-report.pdf",
        new File("/srv/reports/monthly-report.pdf"));
```

The path `mail/logo.png` in the example is a resource packaged inside the application. `/srv/reports/monthly-report.pdf` is only an example of a server file path. Never concatenate paths from user input straight into `new File(...)`; control which files are allowed to be attached and handle errors when a file does not exist.

### Note on `InputStreamSource` and single-read data

A resource passed to the helper must be able to supply a fresh `InputStream` each time it is needed. Jakarta Mail may request reading data multiple times during message creation, size calculation, or sending. Passing a single already-opened stream can result in empty data or errors on reuse.

Safe example with data already in memory:

```java
byte[] pdfBytes = /* obtained from PDF generation service */;
helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
```

For large data, `FileSystemResource`, files on disk, or an `InputStreamSource` opening fresh streams from storage may be more appropriate. Account for delivery timing: the file/stream must remain accessible when the transport reads the data, especially when sending asynchronously.

## 8. Reading MIME headers: distinguishing examples

### Example A: ordinary PDF attachment

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
Content-Transfer-Encoding: base64

JVBERi0... 
```

The message has a `contract.pdf` file; clients typically show the file name with view/download actions.

### Example B: inline image referenced by HTML

```text
Content-Type: image/png
Content-ID: <chart-01>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0...
```

HTML contains `<img src="cid:chart-01">`. Clients supporting MIME related can place the image at the referenced spot inside the message body.

### Example C: image marked inline without a CID

```text
Content-Type: image/jpeg
Content-Disposition: inline; filename="photo.jpg"
Content-Transfer-Encoding: base64

/9j/4AAQ...
```

The header expresses a wish to display the image directly. However, if HTML lacks a reference and the message lacks the right structure, clients may render the image as a separate part, list it like a file, or omit it. `inline` does not replace `Content-ID` when embedding an image at an HTML location.

### Example D: data with `Content-ID` yet marked attachment

```text
Content-Type: image/png
Content-ID: <figure-02>
Content-Disposition: attachment; filename="figure.png"
```

`Content-ID` is an identifier, while `Content-Disposition` is a presentation hint. They are **two independent headers**. Some clients may render content differently when HTML references `cid:figure-02` yet the part is marked attachment. If the goal is an image inside the message body, use `addInline(...)` and `multipart/related` instead of creating conflicting settings.

### Example E: a part without Content-Disposition

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
```

Not every part has `Content-Disposition`. The email's main text part can be displayed as the message body by clients based on `Content-Type` and position in the MIME tree, even when the disposition header is absent.

## 9. File names, Unicode characters, and Content-Type

File names in headers can contain Vietnamese characters or spaces, such as `"Báo cáo tháng 11.pdf"`. In actual MIME messages, the library may encode header parameters for safe transmission and standards compatibility. You should pass a **validated Java file-name string** to `addAttachment(...)` and let the library handle MIME representation, rather than concatenating `Content-Disposition` strings yourself.

Two design principles:

- **File name is metadata, not a safe path.** Use a valid basename, strip control characters and path separators when names come from users; never use file names to decide storage access permissions.
- **MIME type must reflect actual data.** When exact info is available, pass `application/pdf`, `image/png`, `text/csv`, etc. via the `contentType` overload. Never assume a file is definitely safe just because of its declared extension or MIME type.

For inline images, if an SVG file contains active content, some clients may block it or handle it unpredictably. PNG or JPEG are usually more compatible choices for logos and illustrations. For documents and reports, PDF files generally work better as attachments.

### Base64 makes emails larger

Binary files in email are usually transmitted using `Content-Transfer-Encoding: base64`. Base64 increases transmitted data size (by roughly one-third, excluding line breaks and headers), so the mail service's attachment limit may be lower than the raw binary size you expect to send.

When needing to send very large files, consider sending a **permission-controlled, time-limited download link** instead of embedding all data into the email. Clearly define access permissions and link lifetime.

## 10. Common mistakes when integrating Spring Mail

| Symptom | Possible causes | How to resolve |
|---|---|---|
| HTML renders yet logo shows a broken icon | `cid:` does not match `Content-ID`, wrong MIME part order, or client blocked it | Use matching content ID in HTML and `addInline`; call `setText` before `addInline` |
| Logo is listed in the files list | Client shows inline resources as files or multipart structure is unsuitable | Use `MULTIPART_MODE_MIXED_RELATED`; test on target clients |
| PDF shows up inside the body instead of a downloadable file | Part has unintended disposition or structure | Use `addAttachment`; inspect MIME source |
| Attachment is empty or sending throws stream error | `InputStreamSource` can only be read once, file modified/deleted before send | Use `ByteArrayResource` or a re-openable stream source; manage file lifecycle |
| Accented file name is garbled | Varying header/Unicode encoding support across clients | Use helper APIs, set right charset, test with target clients |
| `text/plain` part renders alongside HTML | Client treats parts as independent contents | Use `setText(plainText, htmlText)` to create an alternative structure |
| File blocked or renamed upon receipt | Security filters, org policy, restricted file types | Check MIME type, send/receive policies, and allowed file types |
| Oversized message rejected | Base64 and multipart overhead, SMTP/server limit | Measure real packaged size; reduce size or send a link |
| Mail sent successfully yet recipient sees no attachment | Client filtering/quarantine, broken MIME structure, or intermediary system | Check MIME source, logs, and provider post-submission events |

To troubleshoot errors, distinguish two phases: **building the MIME message** and **sending over SMTP**. An exception in `MimeMessageHelper` can occur before opening an SMTP connection; conversely, SMTP AUTH failures or timeouts can occur after the MIME message is completely built.

### Inspecting MIME source when debugging

Many mail clients offer “View original”, “Show source”, or “View message headers”. With proper access, you can inspect:

1. `Content-Type` headers of the message and each part.
2. Structure and boundaries of `multipart/mixed`, `related`, `alternative`.
3. `Content-Disposition` of attachments and inline resources.
4. `Content-ID` compared against `cid:` URLs in HTML.
5. `filename`, MIME type, and actual size.

In development, you can use an SMTP sink like Mailpit to inspect test emails. Avoid printing full MIME sources of emails containing personal data, tokens, OTPs, or sensitive attachments into shared logs.

## 11. Security when sending inline resources and attachments

`Content-Disposition` is only a presentation directive. Using `attachment` **does not make a file safe**, and using `inline` **does not make content more trustworthy**.

Areas to control in the application:

1. **Attachment data source:** only allow reading files the business process is authorized to send. Prevent path traversal when file names or paths are influenced by user input.
2. **Size and content type:** enforce per-file and total-email limits; restrict dangerous file types per organizational policy.
3. **Sensitive data control:** invoices, reports, and internal images can hold private information; verify recipients and authorization workflows before sending.
4. **HTML injection:** escape or safely sanitize user-supplied text before placing into the HTML body; never concatenate unvalidated data into HTML tags or attributes.
5. **Unique and controlled CIDs:** do not reuse the same content ID for different parts in one message; avoid constructing `cid:` directly from unvalidated input.
6. **Formats with active content:** some clients block SVG, scripts, or executable files. Do not rely on `inline` to bypass the receiving app's security policies.
7. **Resource lifecycle:** if a worker sends emails asynchronously, attachment data must remain available until the message is actually sent.

TLS on the SMTP connection protects **the transport path from the application to the submission server** per configuration; it does not replace content access control and does not automatically provide end-to-end encryption for the entire email.

## 12. Selection scenarios

| Business requirement | Suggested MIME implementation |
|---|---|
| Registration confirmation email with logo | HTML + `addInline` logo using `cid:`; include plain text version |
| Sending a PDF invoice and logo | `setText(plain, html)` + `addInline(logo)` + `addAttachment(invoice.pdf)` |
| Sending a CSV report to the data team | Short body + `addAttachment(report.csv, ..., "text/csv")` |
| Sending a photo for recipient to download, no need in body | `addAttachment(photo.jpg, ..., "image/jpeg")` |
| Sending product photos inside promotional content | `addInline` with unique `Content-ID` per photo and HTML references |
| Sending large files or docs needing dynamic access control | Consider an authorized download link instead of attaching everything |

An email can contain **both inline and attachment** parts. Each part's nature is decided individually; there is no rule saying “having inline forbids attaching documents” or vice versa.

## 13. Frequently asked questions

**Do I need to write `Content-Disposition: inline` manually when using `addInline`?** Usually no. `MimeMessageHelper` creates the matching MIME part and sets required metadata, including Content-ID. Use helper APIs to avoid manual header mistakes.

**Why does `cid:logo` appear in HTML yet no image renders?** Content-ID might mismatch, the part might not have been added, content type might be wrong, MIME structure might be broken, or the mail client restricts rendering. Do not assume merely adding a `cid:` URL automatically ships the image data.

**Can a file marked `inline` be downloaded?** Yes. Many mail clients still let recipients save or download inline-displayed content. Disposition is a presentation hint, not an access permission.

**Can a file marked `attachment` be displayed directly inside the email?** Yes. Some clients preview PDFs/images inline in the UI even when the part has attachment disposition.

**Can I rely solely on the `.pdf` extension to set `Content-Type`?** You should not. Extensions supplied by senders or users may not reflect real content; determine actual data and appropriate MIME type, especially for uploaded files.

**Can HTML be attached as a file?** Yes, if that is a business requirement, though you must consider active-content risks and file filtering policies. Normally, HTML meant to display as the message body should use `setText(html, true)` rather than attaching an HTML file.

**Is `Content-ID` needed for a PDF attachment?** In most cases, no. `Content-ID` is mainly useful when a part must be referenced from another part of the message; independent attachments only need a proper filename and MIME type.

**Does the message body have `Content-Disposition`?** It may or may not. Primary `text/plain`/`text/html` content is usually identified by `Content-Type` and position in the MIME tree; lacking disposition does not turn content into an attachment.

## 14. Related standards documents

- **RFC 2045–2049 (MIME):** MIME concepts, content types, multipart, content encoding, and related headers.
- **RFC 2183 (Content-Disposition):** defines disposition and parameters such as `filename`.
- **RFC 2392 (Content-ID and MID URLs):** describes how to reference MIME content via the `cid:` scheme.
- **RFC 2231:** mechanism for representing certain MIME parameters, including extended character sets and lengths.
- **Spring Framework Mail, `MimeMessageHelper`:** API for building `MimeMessage` with text/HTML, inline resources, attachments, and multipart modes.

---

When composing emails with Spring Framework Mail, remember three points: **`Content-Disposition: inline` signals intent to render the part alongside the message, `Content-Disposition: attachment` signals intent to handle the part as a separate file, and `Content-ID` is how HTML references a specific resource via `cid:`**. Final rendering still depends on `Content-Type`, `multipart/*` structure, and the mail client. In Spring applications, using `MimeMessageHelper.addInline(...)` and `addAttachment(...)` with an appropriate multipart mode expresses those relationships clearly.

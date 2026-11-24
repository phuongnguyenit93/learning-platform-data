# Adding Attachments Without Breaking Alternative

## 1. The Problem: An Email Needs Plain Text, HTML, and an Attachment

A business email often needs two ways to present the same content:

- **Plain text** so it is readable in clients that do not render HTML, text-only modes, or accessibility tools.
- **HTML** to provide formatting, tables, links, and a more readable layout.

In some cases, the email also needs an attached file such as an invoice PDF, spreadsheet, or report. Then, the goal is to send **both content versions and the attachment in the same MIME message**:

~~~text
Email
├── Plain text content
├── HTML content
└── Attached PDF file
~~~

However, at the MIME layer, plain text and HTML are not two independent parts for the recipient to always display side by side. They are **two alternative versions** of the same content, typically placed inside `multipart/alternative`. The PDF file is an independent part of the email, so it must be placed in an appropriate container layer, typically an outer `multipart/mixed`.

If parts are assembled with the wrong structure, email clients may:

- Display only plain text or only HTML in an unintended way.
- Treat the attachment as an alternative content version instead of an attached file.
- Skip a body part when selecting an alternative.
- Show the content while losing the file, or show the file without the expected body.

Spring Framework Mail provides **`MimeMessageHelper`** to manage this structure. You can call `setText(plainText, htmlText)` to create the alternative, and then call `addAttachment(...)` to add an independent file without manually constructing MIME boundaries.

> **Principle:** Plain text and HTML belong in `multipart/alternative` because they are alternative versions. Attachments belong in `multipart/mixed` because they are independent additions to the email.

## 2. Understand Both Multipart Types Before Adding Attachments

### 2.1. multipart/alternative: Alternative Versions of the Same Content

`multipart/alternative` contains multiple representations of the same information. For example:

~~~text
multipart/alternative
├── text/plain; charset=UTF-8
└── text/html; charset=UTF-8
~~~

The mail client selects the version that matches its capabilities and display policy. By MIME convention, alternatives are ordered from the less rich form to the richer form; hence plain text usually precedes HTML.

Example content:

**Plain text**

~~~text
November invoice is ready.
Order code: INV-2026-1101
Please see details in the attached document.
~~~

**HTML**

~~~html
<p>November invoice is <strong>ready</strong>.</p>
<p>Order code: <strong>INV-2026-1101</strong></p>
<p>Please see details in the attached document.</p>
~~~

The two contents may differ in presentation, but must convey the same important information. HTML should not contain an entirely different notice from the plain text version.

### 2.2. multipart/mixed: Independent Parts in One Email

`multipart/mixed` groups independent parts of an email. One part can be the main body, and another part an attachment:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf
    Content-Disposition: attachment
    filename="invoice.pdf"
~~~

In this structure:

- The first part is the main content, organized as alternatives.
- The second part is an independent PDF that can be downloaded or opened separately.
- The client understands that the PDF is an attached document rather than another version of the body.

This is the essential structure when sending HTML and plain text together with attachments.

### 2.3. Why Not Put the PDF Inside multipart/alternative?

`multipart/alternative` has the semantics: each part is an alternative rendering of the same content. An invoice PDF is an **accompanying file**, not an alternative display format for the HTML or plain text body.

If the PDF is placed as a direct sibling inside alternative:

~~~text
multipart/alternative
├── text/plain
├── text/html
└── application/pdf
~~~

a client might treat the PDF as another alternative to choose from. That does not accurately express an email with a body and an attached file. The clearer approach is to put alternative inside an outer `multipart/mixed`.

## 3. How Does MimeMessageHelper Create Alternative?

Spring provides the overload:

~~~java
helper.setText(plainText, htmlText);
~~~

When the helper is initialized in multipart mode, this call creates a `multipart/alternative` with two body parts:

1. `text/plain` for the text version.
2. `text/html` for the HTML version.

Example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(
        "The report is ready.",
        "<p>The report is <strong>ready</strong>.</p>");
~~~

The `true` parameter in the constructor means **enable multipart**, not that the content is HTML. The two arguments of `setText(plain, html)` are what define the two content versions.

If you only call:

~~~java
helper.setText(htmlText, true);
~~~

the helper sets a single HTML body. It does not automatically generate an equivalent plain text version. To have alternatives, use the two-string overload.

### 3.1. Explicit Multipart Mode Constructor

For an email with only alternative and attachments, you can choose:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");
~~~

`MULTIPART_MODE_MIXED` creates a `multipart/mixed` root. The main content can be placed inside it, and attachments are added as independent parts. When `setText(plainText, htmlText)` is called, the main content part is organized as alternative.

The boolean constructor:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
~~~

is a shorter form when you do not need to pick a specific mode; Spring uses the helper's default multipart mode. When reading or maintaining code, using explicit mode constants helps readers clearly understand the intended MIME structure.

### 3.2. When Is MULTIPART_MODE_MIXED_RELATED Needed?

If the email only has plain text, HTML, and a PDF attachment, `MULTIPART_MODE_MIXED` usually expresses the need accurately.

If the email also has **inline images referenced via CID** in HTML, you need to group the body with the inline resources using `multipart/related`, while keeping attachments independent on the outside. In that case use:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

Conceptual structure:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │       <img src="cid:brand-logo">
│   └── image/png
│       Content-ID: <brand-logo>
└── application/pdf
    Content-Disposition: attachment
    filename="invoice.pdf"
~~~

This mode is appropriate when the same email has both **inline images** and **attachments**. Do not choose it merely because there is a PDF file; choose the structure based on the MIME parts actually present in the email.

## 4. Adding Attachments Without Losing Alternative

With `MimeMessageHelper`, the typical sequence is:

1. Create `MimeMessage`.
2. Create the helper in multipart mode.
3. Set addresses, subject, and plain/HTML content.
4. Add attachments using `addAttachment(...)`.
5. Call `JavaMailSender.send(message)`.

Example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("lan@example.net");
helper.setSubject("November Invoice");

String plainText = """
        November invoice is ready.
        Invoice code: INV-2026-1101
        Please see the attached PDF file.
        """;

String htmlText = """
        <html lang="en">
          <body>
            <p>November invoice is <strong>ready</strong>.</p>
            <p>Invoice code: <strong>INV-2026-1101</strong></p>
            <p>Please see the attached PDF file.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
helper.addAttachment("invoice-2026-1101.pdf", invoiceResource,
        "application/pdf");

mailSender.send(message);
~~~

In the example:

- `MULTIPART_MODE_MIXED` creates the container holding the body and attachment.
- `setText(plainText, htmlText)` creates the alternative pair.
- `addAttachment(...)` adds the PDF as an independent part.
- `send(message)` sends the exact message modified by the helper.

`invoiceResource` is a valid `InputStreamSource`/`Resource` providing the PDF bytes. This example assumes the resource has already been created and validated. Both text and HTML content share UTF-8 encoding.

### 4.1. Why Call setText Before addAttachment?

Setting the body first and then adding attachments keeps the code sequence clear:

~~~java
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource, "application/pdf");
~~~

The helper manages the root multipart and child parts. Calling the API in this order clarifies which is the main body and which is the independent file.

Avoid operating directly on `MimeMessage` to replace the entire content after the helper has built the multipart. For example:

~~~java
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource);

// Do not do this after the helper has built the multipart structure:
message.setText("A new body");
~~~

The last statement can replace the message content and wipe out the multipart/attachment structure created by the helper. Once you begin using the helper, continue modifying content through the helper; do not overwrite the entire message content with another API.

## 5. addAttachment Overloads and Data Sources

`MimeMessageHelper` supports adding attachments from multiple source types. Common forms:

~~~java
helper.addAttachment(attachmentFilename, dataSource);
helper.addAttachment(attachmentFilename, inputStreamSource);
helper.addAttachment(attachmentFilename, inputStreamSource, contentType);
~~~

| Argument | Meaning |
| --- | --- |
| `attachmentFilename` | Filename the recipient sees in the email |
| `dataSource` | Data source providing bytes and content type |
| `inputStreamSource` | Source capable of opening an `InputStream` to read data |
| `contentType` | MIME type such as `application/pdf` or `text/csv` |

### 5.1. Using Spring Resource

`Resource` in Spring also implements `InputStreamSource`, so it can be passed directly:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource invoice = new ClassPathResource(
        "mail/invoices/invoice-2026-1101.pdf");

helper.addAttachment(
        "invoice-2026-1101.pdf",
        invoice,
        "application/pdf");
~~~

If the file is placed under `src/main/resources`:

~~~text
src/main/resources/
└── mail/
    └── invoices/
        └── invoice-2026-1101.pdf
~~~

`ClassPathResource` can read resources from the classpath even when the application is packaged as a JAR. For external files managed by the application, `FileSystemResource` can be used. Never take arbitrary file paths from a request and attach them; check access permissions and restrict the storage directory.

### 5.2. Using ByteArrayResource When Data Is in Memory

If the PDF has already been generated as a byte array:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pdfBytes = pdfGenerator.createInvoicePdf(invoice);
ByteArrayResource pdf = new ByteArrayResource(pdfBytes);

helper.addAttachment(
        "invoice.pdf",
        pdf,
        "application/pdf");
~~~

`ByteArrayResource` provides a fresh stream from in-memory data. This approach is convenient for moderately sized files with size limits enforced. For large documents, avoid loading all bytes onto the heap if the application can use a resource/file/stream capable of re-reading appropriately.

### 5.3. InputStreamSource Must Be Re-Openable

During MIME message serialization and sending, the mail library may need to read attachment data. Therefore, `InputStreamSource.getInputStream()` should return **a fresh stream positioned at the start of the data on every call**.

Suitable sources typically include:

| Source | Characteristic |
| --- | --- |
| `ClassPathResource` | Re-opens resource from classpath |
| `FileSystemResource` | Re-opens accessible file |
| `ByteArrayResource` | Opens a new stream from a byte array |
| Custom `InputStreamSource` | Must create a new stream each time |
| `InputStreamResource` wrapping an opened stream | Usually single-read only; may fail if transport needs to re-read |

Do not read an entire stream and return the already-consumed stream on the next call. If data arrives only from a single-use source, read it into a bounded buffer as a `ByteArrayResource` or save it to a controlled temporary area and provide a re-openable resource.

Custom source example:

~~~java
byte[] bytes = loadPdfBytesWithSizeLimit();
InputStreamSource source = () -> new ByteArrayInputStream(bytes);

helper.addAttachment("report.pdf", source, "application/pdf");
~~~

Each time the helper/transport requests a stream, the lambda creates a new `ByteArrayInputStream` from the start of the array. Control the size of `bytes` before holding them in memory.

### 5.4. Choosing a Content-Type Matching the Bytes

| File type | MIME Content-Type |
| --- | --- |
| PDF | `application/pdf` |
| CSV | `text/csv; charset=UTF-8` |
| Excel Open XML | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| Word Open XML | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| ZIP | `application/zip` |

Do not pick the content type solely from the filename extension if the data comes from user uploads. Detect the actual byte format, restrict allowed file types, and use the matching content type. A wrong MIME type can cause recipients to open the file in the wrong application or cause clients to mishandle the attachment.

## 6. Multiple Attachments in the Same Email

A multipart helper can attach multiple files:

~~~java
helper.setText(plainText, htmlText);

helper.addAttachment("invoice.pdf", invoicePdf, "application/pdf");
helper.addAttachment("terms.pdf", termsPdf, "application/pdf");
helper.addAttachment("details.csv", detailsCsv, "text/csv; charset=UTF-8");

mailSender.send(message);
~~~

The files are independent parts in the `multipart/mixed` root. They are not alternatives of the body. Attachment filenames should be meaningful, contain no system paths, and never be taken verbatim from untrusted input.

When sending multiple files:

- Limit file count and total size.
- Verify each source is readable.
- Use safe filenames and corresponding content types.
- Avoid attaching one recipient's data to another recipient's email.
- Consider secure download links instead of sending large files.

## 7. When an Email Has Alternative, Inline Images, and Attachments

A complex email may include:

- Plain text version.
- HTML version.
- Logo or icon embedded inline via CID.
- Independent PDF for the recipient to download.

At this point choose `MULTIPART_MODE_MIXED_RELATED`:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Electronic Invoice");

String plainText = """
        Invoice INV-2026-1101 is ready.
        Please see the attached PDF file.
        """;

String htmlText = """
        <html lang="en">
          <body>
            <p><img src="cid:brand-logo" alt="Logo" width="140"></p>
            <p>Invoice <strong>INV-2026-1101</strong> is ready.</p>
            <p>Please see the attached PDF file.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png",
        "brand-logo.png");

helper.addAttachment(
        "invoice-2026-1101.pdf",
        invoicePdf,
        "application/pdf");

mailSender.send(message);
~~~

Order:

1. Select mixed-related mode.
2. Set alternative using `setText(plainText, htmlText)`.
3. Add the inline image referenced by HTML via `cid:brand-logo`.
4. Add the PDF as an independent attachment.
5. Send the message.

Conceptual MIME structure:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   │       <img src="cid:brand-logo">
│   └── image/png
│       Content-ID: <brand-logo>
│       Content-Disposition: inline
└── application/pdf
    Content-Disposition: attachment
    filename="invoice-2026-1101.pdf"
~~~

This is a model for understanding part relationships; header details and boundaries are generated by Jakarta Mail. `multipart/related` groups HTML with the images it references; `multipart/alternative` holds the text/HTML versions; the outermost `multipart/mixed` holds independent parts like the PDF.

## 8. Why Let MimeMessageHelper Manage the MIME Tree?

You can work directly with Jakarta Mail's `MimeMultipart` and `MimeBodyPart`, but you must manage everything manually:

- Root multipart and subtype.
- Alternative multipart and body part ordering.
- Related relationship between HTML and CID images.
- Attachment `Content-Disposition` and filename.
- `Content-Type`, charset, transfer encoding, and boundaries.
- Calling `saveChanges()` and serializing appropriately.

One mistake when calling `message.setContent(...)` can overwrite the structure built by the helper or earlier code. Once you choose `MimeMessageHelper`, continue adding content through the helper's APIs:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brand-logo", logo, "image/png");
helper.addAttachment("invoice.pdf", invoice, "application/pdf");
~~~

You do not need to generate boundary strings or assemble MIME via string concatenation. Jakarta Mail handles serializing the parts and boundaries from the object structure.

### 8.1. When Should You Build MimeMultipart Manually?

Only consider building it manually when the application has special MIME requirements the helper cannot satisfy, such as custom multi-level nesting or modifying an existing message format. In that case, you need a solid understanding of the Jakarta Mail API, MIME subtypes, part order, and raw message inspection. Do not mix both management styles on the same message: one part managed by the helper, and another part replacing the entire content.

## 9. Common Mistakes When Adding Attachments

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Attachment does not appear | Helper created in non-multipart mode | Initialize multipart mode before adding files |
| Only one body visible, alternative lost | Used `setText(html, true)` instead of `setText(plain, html)` | Create both content versions |
| Attachment replaces HTML/plain | Placed attachment in the wrong place inside MIME alternative | Use mixed root with alternative as body |
| Body lost after adding file | Called `message.setText`/`setContent` after helper built multipart | Do not overwrite full content; use helper consistently |
| File has a name but cannot open | Empty resource, corrupted bytes, or wrong content type | Check source, bytes, and MIME type |
| Stream error on send | Source can only open once or stream already closed | Use re-openable Resource/InputStreamSource |
| Unexpected filename | Confused resource name with attachment name | Pass filename to the `attachmentFilename` argument |
| PDF displays as text | Wrong Content-Type | Use `application/pdf` for valid PDF bytes |
| Only one of several files missing | Corresponding source failed or part creation errored | Validate each resource before sending |
| Email too large or rejected by provider | Total MIME exceeds server limit | Reduce size, compress reasonably, or use download links |

### 9.1. Forgetting to Enable Multipart

Incorrect code:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource, "application/pdf");
~~~

`false` means do not create multipart. When multiple MIME parts are needed, initialize the helper in multipart mode:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");
~~~

### 9.2. Creating Only an HTML Body Without a Plain Alternative

Code:

~~~java
helper.setText(htmlText, true);
helper.addAttachment("invoice.pdf", invoiceResource);
~~~

This can send HTML with an attachment if the helper is multipart, but **there is no alternative plain text version**. If both formats are required, use:

~~~java
helper.setText(plainText, htmlText);
~~~

### 9.3. Calling message.setText After Adding Attachments

Code to avoid:

~~~java
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource);
message.setText("New content");
~~~

`message.setText` can replace the content the helper organized into a multipart structure. When updating the body, update it via the helper before sending; avoid overwriting the root content after attachments have been added.

### 9.4. Using addInline Instead of addAttachment

`addInline` is for resources referenced by the HTML body via `cid:...`. A downloadable PDF should normally use `addAttachment`. Using the wrong API can cause clients to display the file in an unintended way.

### 9.5. Sending an Exhausted InputStream

If `InputStreamSource` returns the same already-consumed stream, Jakarta Mail may hit EOF when serializing the part. Use `ClassPathResource`, `FileSystemResource`, `ByteArrayResource`, or a custom source that creates a new stream on every read.

## 10. Inspecting the MIME Structure Before Sending

In a test environment, you can serialize `MimeMessage` to an `.eml` file to inspect the root multipart, alternative, and attachment:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("test@example.net");
helper.setSubject("Testing alternative and attachment");
helper.setText(
        "The report is ready.",
        "<p>The report is <strong>ready</strong>.</p>");
helper.addAttachment(
        "report.pdf",
        new ClassPathResource("mail/report.pdf"),
        "application/pdf");

message.saveChanges();
try (OutputStream output =
             Files.newOutputStream(Path.of("mail-preview.eml"))) {
    message.writeTo(output);
}
~~~

This snippet assumes imports for `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path`, `ClassPathResource`, and handling of `IOException`/`MessagingException`. It only writes the message to a file; **it does not send an email** because `mailSender.send(message)` is not called.

In raw MIME, look for these signs:

~~~text
Content-Type: multipart/mixed; boundary="..."

--...
Content-Type: multipart/alternative; boundary="..."

--...
Content-Type: text/plain; charset=UTF-8

The report is ready.
--...
Content-Type: text/html; charset=UTF-8

<p>The report is <strong>ready</strong>.</p>
--...
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64
~~~

This is an **illustrative excerpt with boundaries and bytes omitted**, not a complete raw email. Exact headers and encoding may vary with Jakarta Mail. Verify:

- Root is `multipart/mixed`.
- Body contains `multipart/alternative`.
- Both `text/plain` and `text/html` parts exist.
- Attachment has `Content-Disposition: attachment` and a sensible filename.
- Attachment Content-Type matches the byte format.

Do not assert a specific boundary value; boundaries are generated and managed by Jakarta Mail.

## 11. Testing Through an SMTP Sink

An `.eml` file proves the message object serializes, but does not test how servers and clients handle it end-to-end. You can use a local SMTP sink such as Mailpit/MailHog to:

1. Run the application with a local profile pointing to the SMTP sink.
2. Send a message containing plain text, HTML, and a sample PDF.
3. Open the sink UI to confirm the body and file were received.
4. Inspect raw MIME and check root/alternative/attachment.
5. Download the PDF from the sink and verify bytes match the test document.
6. Open the email on target mail clients to verify presentation.

Do not send test emails to customers or public addresses without a clear purpose and controlled environment. An SMTP sink confirms the application sends to a test environment; it does not prove production providers will accept every file or that all mail clients will render identically.

### 11.1. Verify Both Alternatives

Do not only look at HTML in the sink UI. Check raw MIME for both:

~~~text
text/plain; charset=UTF-8
text/html; charset=UTF-8
~~~

Plain text needs essential information such as invoice code, status, and instructions to view the document. HTML may look nicer, but should not hold exclusive details missing from the plain text version.

### 11.2. Verify Attachments

- Filename displays correctly for the business purpose.
- Content-Type matches the data.
- Bytes open properly in an appropriate application.
- Size fits within system and provider limits.
- Files are never mixed up between one recipient and another.
- Files containing sensitive data are never attached to an email sent to the wrong address.

## 12. Managing Attachment Size and Security

Attachments increase total email size. With MIME transfer encodings such as Base64, the transmitted size is typically larger than the original binary data (roughly one-third larger, excluding headers and boundaries). Thus, a 20 MB PDF file can push an email past provider limits even if the raw file is under an upload limit.

Before adding an attachment:

- Set limits on file count and total size.
- Verify the recipient's authorization for each document.
- Detect the actual format rather than trusting client-supplied filenames or MIME headers.
- Generate safe attachment filenames without system paths or control characters.
- Do not attach executable files or file types prohibited by system policy.
- For large documents, consider time-limited, access-controlled download links instead of attaching.
- Do not log raw bytes or full emails containing sensitive data.

An example size check when bytes are already available:

~~~java
private static final long MAX_ATTACHMENT_BYTES = 10L * 1024 * 1024;

static ByteArrayResource asPdf(byte[] bytes) {
    if (bytes == null || bytes.length == 0
            || bytes.length > MAX_ATTACHMENT_BYTES) {
        throw new IllegalArgumentException("Attachment size is not allowed");
    }
    // In practice, verify the bytes are a valid PDF before using.
    return new ByteArrayResource(bytes);
}
~~~

The `10 MiB` limit is only an application policy example; the right limit depends on the SMTP provider, receiving systems, and remaining headroom after MIME encoding.

## 13. Separating Body Templates from the Attachment Step

In larger applications, it is good practice to separate responsibilities:

~~~text
InvoiceService
   |
   v
InvoiceDocumentService
   | generate PDF / check permissions and size
   v
InvoiceEmailContent
   | plainText + htmlText + attachment resource
   v
InvoiceMailer
   | MimeMessageHelper
   | setText(plain, html)
   | addAttachment(...)
   v
JavaMailSender.send(message)
~~~

The content-building service does not need to know the SMTP host. The mail-sending service should not decide on its own whether a user is authorized to view a PDF; authorization checks must occur before generating and attaching the file.

An internal DTO can describe an attachment:

~~~java
public record MailAttachment(
        String filename,
        InputStreamSource content,
        String contentType) {
}
~~~

The mailer can accept a prepared list of attachments:

~~~java
helper.setText(plainText, htmlText);

for (MailAttachment attachment : attachments) {
    helper.addAttachment(
            attachment.filename(),
            attachment.content(),
            attachment.contentType());
}
~~~

This is an illustrative structure; validate the list, filenames, content types, and access permissions at the appropriate layer before calling the mailer. Each `InputStreamSource` must support repeatable stream opening.

## 14. Frequently Asked Questions

**"Does `setText(plainText, htmlText)` automatically add attachments?"**  
No. It creates alternative content versions. Use `addAttachment(...)` to add independent files.

**"Why should attachments go inside multipart/mixed?"**  
Because attachments are independent additions. `multipart/alternative` means alternative versions of the same content; putting a file there does not express the right intent.

**"Can I send HTML and a PDF without plain text?"**  
Yes. Use a single HTML body and an attachment inside multipart. However, if a plain text fallback is required, use `setText(plainText, htmlText)`.

**"Can I use `new MimeMessageHelper(message, true, "UTF-8")`?"**  
Yes. That enables multipart with the helper's default mode. If you want to explicitly show a mixed root for alternative + attachments, you can use `MULTIPART_MODE_MIXED`.

**"When there are inline images and a PDF, which mode should be used?"**  
`MULTIPART_MODE_MIXED_RELATED` is usually appropriate: related groups the body and CID images, and the outer mixed holds independent attachments.

**"Do I need to create MimeMultipart and boundaries manually?"**  
Not when using `MimeMessageHelper`. The helper and Jakarta Mail manage the MIME tree and boundaries. Avoid mixing manual content management with the helper.

**"Can I call addAttachment before setText?"**  
Set the body first and then add attachments so the code stays clear and the helper structure remains consistent. Avoid overwriting message content after the helper has built the parts.

**"Why can't the file be opened even though the email was sent?"**  
Check the resource bytes, content type, filename, transfer encoding, and provider limits. SMTP accepting a message does not prove the embedded file is valid.

**"Can I use InputStreamResource for an attachment?"**  
Only if the source satisfies the stream openings required by Jakarta Mail. An already-opened or single-use consumed stream may not be readable again. Re-openable resources or `ByteArrayResource` are usually easier to control.

**"If there is only a PDF, is multipart/alternative still needed?"**  
No. `multipart/mixed` can contain a single simple body and an attachment. Only create alternative when actually providing multiple content versions.

## 15. Remembering the Structure and Sequence

For an email with plain text, HTML, and an attachment:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    └── application/pdf (attachment)
~~~

For an email that also includes an inline image:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html (cid reference)
    │   └── image/png (inline)
    └── application/pdf (attachment)
~~~

In Spring Framework Mail, the standard implementation is:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");

helper.setText(plainText, htmlText);
helper.addAttachment("report.pdf", reportResource, "application/pdf");

mailSender.send(message);
~~~

If there are CID images, switch to `MULTIPART_MODE_MIXED_RELATED` and call `addInline(...)` after setting the body. **Do not replace the root content after the helper has built the multipart**. Preserving proper alternative and mixed semantics lets mail clients choose the suitable body version while still receiving independent attachments with the right name and content type.

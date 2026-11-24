# Attaching from ByteArrayResource

In Spring Framework Mail, you can send an attachment without creating a temporary file on disk. If the application already has the file content as a **byte[]**, wrap that byte array in a **ByteArrayResource** and pass it to **MimeMessageHelper.addAttachment(...)**.

This approach fits data generated directly in memory or retrieved from a source that already returns bytes, such as a newly generated PDF invoice, a CSV report, a processed image, a document read from a database, or content downloaded from object storage. The application can place the data directly into a MIME part of the email without writing a physical file first.

Core example:

~~~java
byte[] pdfBytes = pdfGenerator.generate(invoice);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Where:

- **pdfBytes** is the raw bytes of the PDF file.
- **ByteArrayResource** supplies the data as a Spring Resource for the mail library to read.
- **invoice.pdf** is the display name of the attachment.
- **application/pdf** is the MIME type describing the data.
- **addAttachment(...)** adds an independent MIME part to the message.

The key point to remember is to **pass the raw bytes to ByteArrayResource; do not convert the bytes to Base64 yourself before calling addAttachment**. Jakarta Mail handles the appropriate MIME content encoding when serializing the email.

## 1. What is ByteArrayResource?

**ByteArrayResource** is an implementation of Spring **Resource** used to represent data already available in a byte array. It is especially useful when the data source is not a file on the filesystem but content currently residing in memory.

~~~java
byte[] content = "Hello from memory".getBytes(StandardCharsets.UTF_8);

ByteArrayResource resource = new ByteArrayResource(content);
~~~

This resource allows Spring APIs accepting **InputStreamSource** to access the data. When reading is needed, it provides an InputStream backed by the stored byte array.

You can visualize it as:

~~~text
byte[]
  |
  v
ByteArrayResource
  |
  | getInputStream()
  v
InputStream
  |
  v
MimeMessageHelper.addAttachment(...)
  |
  v
MIME attachment part
  |
  v
JavaMailSender.send(...)
~~~

### 1.1. Why not pass byte[] directly to addAttachment?

The **MimeMessageHelper** API accepts a data source compatible with **InputStreamSource** in its common overloads. `byte[]` itself does not implement this interface.

Therefore, an adapter is needed:

~~~java
ByteArrayResource resource = new ByteArrayResource(fileBytes);
helper.addAttachment("document.pdf", resource);
~~~

ByteArrayResource acts as the bridge between the byte array in the application and an API accepting an InputStream source.

### 1.2. ByteArrayResource is not a temporary file

When using:

~~~java
new ByteArrayResource(pdfBytes)
~~~

the application does not create a file on disk. The data remains in the memory of the Java process.

This avoids creating temporary files, choosing a temp directory, managing read/write permissions, and deleting files after sending. In exchange, the application must account for heap memory, the size of the byte array, and when the data is released.

### 1.3. Comparing Resource types

| Resource | Represents | Suitable use cases |
| --- | --- | --- |
| **ByteArrayResource** | Data already in byte[] | PDFs/CSVs/images generated or loaded into memory |
| **ClassPathResource** | Resources on the classpath | Logos, document templates, static files packaged with the application |
| **FileSystemResource** | Files on the filesystem | Report files already created and saved on disk |
| **InputStreamResource** | An existing InputStream | Special stream sources, requiring attention to lifecycle |
| **UrlResource** | Resources via URL | Controlled URL access scenarios |

No single Resource is best in every situation. Choose based on the data source and how the library needs to read it.

## 2. addAttachment and MimeMessageHelper overloads

**MimeMessageHelper** provides overloads to add attachments. Two common forms:

~~~java
helper.addAttachment(
        "invoice.pdf",
        inputStreamSource
);
~~~

and:

~~~java
helper.addAttachment(
        "invoice.pdf",
        inputStreamSource,
        "application/pdf"
);
~~~

Parameters:

1. **attachmentFilename**: the filename suggested to the recipient when downloading or saving the attachment.
2. **inputStreamSource**: the byte source capable of providing an InputStream.
3. **contentType**: the MIME type of the content, e.g. `application/pdf` or `text/csv; charset=UTF-8`.

With ByteArrayResource:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

When the file type is known, passing an explicit contentType helps the message describe the data clearly. If you use the overload without contentType, Spring/Jakarta Mail may rely on detection mechanisms or default values; the exact behavior also depends on how the resource and file type map are configured.

### 2.1. An attachment is a MIME part

An email with an attachment typically uses a multipart structure, for example:

~~~text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-001"

--mixed-001
Content-Type: text/plain; charset=UTF-8

Please see the attached invoice.

--mixed-001
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

[encoded-PDF-data]

--mixed-001--
~~~

The **[encoded-PDF-data]** part is an illustrative placeholder, not actual PDF data.

An attachment is described by the MIME part headers:

- **Content-Type** indicates the data type.
- **Content-Disposition: attachment** hints to the client to present this part as an attachment.
- **filename** provides the display name.
- **Content-Transfer-Encoding** describes how bytes are represented in the message, typically base64 for binary data.

A Spring application does not need to concatenate boundaries or construct those headers manually as strings. Let MimeMessageHelper and Jakarta Mail build the MIME part.

### 2.2. Multipart must be enabled

A simple email can be created with **SimpleMailMessage**, but this type does not support attachments. To attach files, you must create a **MimeMessage** and a **MimeMessageHelper** in multipart mode.

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);
~~~

**MULTIPART_MODE_MIXED** is suitable for email content and independent attachments. If the email also includes HTML and inline images, **MULTIPART_MODE_MIXED_RELATED** can be used to represent the related branch alongside attachments.

Convenient constructor:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

In Spring Framework, `true` enables multipart using the default mode **MULTIPART_MODE_MIXED_RELATED**. When only standard attachments are needed, explicitly choosing **MULTIPART_MODE_MIXED** makes the intent clearer.

## 3. Basic example: sending an email with a PDF from byte[]

Suppose the application has generated a PDF invoice in memory and received a `byte[]` from a service:

~~~java
byte[] pdfBytes = pdfGenerator.generate(invoice);
~~~

Email sending service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalArgumentException(
                    "PDF content must not be empty"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");
        helper.setText(
                "Hello,\n"
                + "Please see the attached PDF invoice.",
                false
        );

        ByteArrayResource pdfResource =
                new ByteArrayResource(pdfBytes);

        helper.addAttachment(
                "invoice.pdf",
                pdfResource,
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

This code assumes `mailSender` is configured by Spring and `pdfBytes` is valid PDF data produced by a source the application trusts. In a real system, `recipient` must be validated per business rules and file size must have a limit.

### 3.1. Execution flow

1. Verify the byte data is not null and not empty.
2. Create a MimeMessage.
3. Initialize MimeMessageHelper with multipart mode.
4. Set From, To, Subject, and the email body.
5. Wrap `byte[]` in a ByteArrayResource.
6. Call addAttachment with the filename and MIME type.
7. Call `mailSender.send(message)` to send the entire email.

A single `send` call sends the message containing both the body and the attachment. There is no need to call `send` separately for the file.

### 3.2. Why is a filename still needed if the resource is just a byte[]?

A byte array contains no filename information. It is only raw data.

The display name is supplied separately:

~~~java
helper.addAttachment(
        "invoice-2026-001.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

That name is placed into MIME metadata so the email client can display it and suggest a name when the recipient saves the file. It is not a file path on the sending machine and does not mean the application created a physical file with that name.

## 4. Creating byte[] from in-memory generated content

ByteArrayResource is useful when the data source is generated inside the application itself. For example, a PDF report produced by a document generation component.

~~~java
public interface InvoicePdfGenerator {
    byte[] generate(Invoice invoice);
}
~~~

A document generation library may write content to an **OutputStream**. We use **ByteArrayOutputStream** to capture the content in memory:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;

public byte[] generatePdf(Invoice invoice) throws IOException {
    try (ByteArrayOutputStream output =
                 new ByteArrayOutputStream()) {

        pdfDocumentWriter.write(invoice, output);

        return output.toByteArray();
    }
}
~~~

**pdfDocumentWriter.write(...)** represents the API of the PDF library used by the project. It writes PDF bytes into the output stream. **toByteArray()** returns a byte array containing the written content.

Flow:

~~~text
Invoice
   |
   v
PDF generator
   |
   v
ByteArrayOutputStream
   |
   | toByteArray()
   v
byte[]
   |
   v
ByteArrayResource
   |
   v
MimeMessageHelper.addAttachment()
~~~

There is no need to write the PDF file to disk if the application only needs to send it right after creation and its size fits comfortably in memory.

### 4.1. Memory cost when using ByteArrayOutputStream

**toByteArray()** creates a resulting byte array. During creation, the internal buffer of ByteArrayOutputStream and the returned array may coexist for a period of time. Afterward, ByteArrayResource holds a reference to the byte array, while MIME generation may require additional buffers or data representations.

Therefore, a large file can consume significantly more heap than the final file size. Do not look only at the file size to estimate peak memory.

For small or medium reports, this approach is straightforward. For large files, consider generating the file in storage or using a suitable streaming source instead of keeping multiple copies on the heap.

## 5. ByteArrayResource and InputStreamSource: why re-readability matters

**InputStreamSource** is the abstraction used by Spring to supply an InputStream. Mail APIs may need to access the data while building or serializing the MIME message.

A suitable data source must be capable of providing a fresh stream when requested according to the API contract. **ByteArrayResource** is a convenient choice because it is backed by an existing byte array and can create a new ByteArrayInputStream to re-read the same data.

~~~java
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);

InputStream first = resource.getInputStream();
InputStream second = resource.getInputStream();
~~~

The two calls create independent streams reading from the same underlying data. Reading the first stream to completion does not consume the read cursor of the second stream.

### 5.1. Comparison with InputStreamResource

**InputStreamResource** typically represents an already-provided InputStream. This source is generally considered read-once; once the stream has been consumed or closed, the same data cannot be re-opened by default.

| Characteristic | ByteArrayResource | InputStreamResource |
| --- | --- | --- |
| Data source | `byte[]` in memory | An existing InputStream |
| Re-openable | Can create a new stream from the byte array | Usually cannot re-read the same stream |
| Memory cost | Keeps the entire byte array | May avoid keeping all data on the heap, depending on source |
| Suitable for | Small/medium content already in RAM | Special, one-shot, or already-managed stream sources |
| Use for MIME mail sending | Usually convenient because it is re-readable | Requires caution regarding lifecycle and re-readability |

Example you might encounter:

~~~java
InputStreamResource resource =
        new InputStreamResource(inputStream);

helper.addAttachment("report.pdf", resource);
~~~

This approach can fail if the mail provider needs to access the resource multiple times. Do not choose InputStreamResource merely assuming streams always save memory; you must understand the mail API and how the stream source behaves.

### 5.2. ByteArrayResource does not automatically copy data

When creating:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);
~~~

the resource uses the byte array passed in. If another thread mutates the array contents while the email is being built or sent, the attached data may change unexpectedly.

If you need to isolate the data from the caller, you can make a defensive copy:

~~~java
byte[] stableBytes = pdfBytes.clone();

ByteArrayResource resource =
        new ByteArrayResource(stableBytes);
~~~

In return, cloning allocates an extra copy in memory. Only use it when you need to protect immutability or avoid sharing a mutable byte array. For large files, copying also increases heap pressure.

## 6. Choosing the right MIME type for byte[]

The MIME type describes the content of the attachment. It does not convert the data into the corresponding format.

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

The data passed in must actually be a PDF.

| File type | MIME type |
| --- | --- |
| PDF | **application/pdf** |
| CSV | **text/csv; charset=UTF-8** |
| TXT | **text/plain; charset=UTF-8** |
| JSON | **application/json** |
| ZIP | **application/zip** |
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| XML | **application/xml** or **text/xml** depending on purpose |
| Unknown binary data | **application/octet-stream** |

CSV attachment example:

~~~java
byte[] csvBytes = csvContent.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

PNG image example:

~~~java
helper.addAttachment(
        "chart.png",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

### 6.1. Do not trust user-declared MIME types

If the file comes from an upload, the client might send a Content-Type that does not match the actual data. For instance, non-PDF content claiming `application/pdf`.

The MIME type describes the part to the recipient; it is not a file verification mechanism. The application should verify the actual format according to policy, enforce size limits, and restrict allowed file types.

### 6.2. When is application/octet-stream used?

If the data type cannot be determined or you want to present it as generic binary content, **application/octet-stream** is the commonly used type.

However, if you know the data is PDF, CSV, or PNG, declare the specific type. An accurate type helps email clients and receiving security systems handle it properly.

### 6.3. Do not Base64-encode byte[] before creating the resource

Do not do this:

~~~java
byte[] encoded = Base64.getEncoder().encode(pdfBytes);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(encoded),
        "application/pdf"
);
~~~

Here the part data is the byte sequence of a Base64 string, not the original PDF bytes. Jakarta Mail may encode the part data again for transport, resulting in the recipient recovering a file containing Base64 text instead of a PDF.

The right way:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

The mail library handles Content-Transfer-Encoding automatically. Supply the original raw bytes of the file.

## 7. Naming the attachment when the source is just byte[]

A byte array has no filename. The filename is passed in **addAttachment**:

~~~java
helper.addAttachment(
        "monthly-report.pdf",
        new ByteArrayResource(reportBytes),
        "application/pdf"
);
~~~

This name becomes information in the MIME header, typically in **Content-Disposition: attachment; filename=...**. It is only the suggested name for the recipient when saving the file, not a path on the sending machine.

### 7.1. The display name is not a storage file path

Do not use an absolute server path as the filename. Doing so can leak filesystem structure or produce an undesirable display name. Choose a short, meaningful name containing only metadata meant to be public.

### 7.2. Controlling the filename

If the name is derived from external data, restrict:

- Length.
- Control characters such as CR/LF.
- Path characters `/` and `\`.
- Confusing or OS-incompatible names.
- Special characters that could affect how headers are parsed.
- Sensitive data in the filename, such as customer names or internal codes that must not be disclosed.

Jakarta Mail handles header quoting and encoding via the MIME API, but that does not replace the application's filename policy. Never concatenate Content-Disposition as a raw string.

### 7.3. Unicode filenames

A Vietnamese name such as **báo-cáo-tháng-11.pdf** may require MIME-standard header encoding. When using **addAttachment(filename, resource, contentType)**, pass the filename as the API value and let the library handle header representation.

Unicode filename rendering depends on the email client and receiving system. If broad compatibility is needed, short ASCII names are usually easier to handle; if preserving Unicode is required, test on target clients.

## 8. Sending multiple attachments from ByteArrayResource instances

An email can contain multiple files. Call **addAttachment** multiple times before sending:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);

helper.addAttachment(
        "chart.png",
        new ByteArrayResource(pngBytes),
        "image/png"
);

mailSender.send(message);
~~~

Conceptual structure:

~~~text
multipart/mixed
├── text/plain
│   └── "The documents are attached."
├── application/pdf
│   └── invoice.pdf
├── text/csv
│   └── orders.csv
└── image/png
    └── chart.png
~~~

A message with multiple MIME parts is still **one email**. There is no need to call `mailSender.send` after each attachment.

### 8.1. Iterating over a list of files

If the business logic has a list of documents:

~~~java
public record MailAttachment(
        String filename,
        byte[] content,
        String contentType
) {}
~~~

Each file can be added:

~~~java
for (MailAttachment attachment : attachments) {
    helper.addAttachment(
            attachment.filename(),
            new ByteArrayResource(attachment.content()),
            attachment.contentType()
    );
}
~~~

This is an example of the data structure. Before adding to the message, the application must verify that the list does not exceed limits on count, total size, filenames, and access permissions for each document.

### 8.2. Limiting total size

If there are 10 files of 5 MB each, the raw data alone is already about 50 MB. When transmitted via MIME, binary data is typically Base64-encoded, further increasing size; there are also headers, boundaries, and the email body.

Do not limit only individual files while forgetting the total size of the whole message. SMTP providers usually impose a message size limit, and that limit may apply to the data after encoding.

An email-sending policy can limit the size per file, total bytes across all attachments, number of attachments, and total message size after estimating overhead.

## 9. Example: CSV generated in memory and sent

A CSV report can be generated from a list of data:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

public byte[] createCsv(List<OrderRow> rows) {
    StringBuilder csv = new StringBuilder();
    csv.append("order_id,total,status\n");

    for (OrderRow row : rows) {
        csv.append(row.orderId()).append(',')
           .append(row.total()).append(',')
           .append(row.status()).append('\n');
    }

    return csv.toString().getBytes(StandardCharsets.UTF_8);
}
~~~

This example simplifies CSV escaping. In a real application, if fields contain commas, quotes, or newlines, use a proper CSV library rather than direct string concatenation.

After creating `byte[]`:

~~~java
byte[] csvBytes = createCsv(rows);

helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

The content is UTF-8 encoded. If recipients open it with a spreadsheet program, UTF-8 detection may depend on the software; there may be BOM or format requirements per receiving system, though a BOM should not be added mechanically if the data contract does not call for it.

### 9.1. CSV containing user-entered data

If a CSV has fields starting with characters like `=`, `+`, `-`, or `@`, some spreadsheet programs may interpret the content as a formula when opened. This is **CSV formula injection**, separate from MIME attachments.

If the CSV is sent to be opened in spreadsheets, you need a policy to sanitize untrusted data fields based on the receiving tool and business requirements. Wrapping `byte[]` in a ByteArrayResource does not make CSV content safer.

## 10. Example: PDF generated from an invoice

Suppose a service generates PDFs using a dedicated component:

~~~java
public interface PdfGenerator {
    byte[] generateInvoice(Invoice invoice);
}
~~~

Orchestration service:

~~~java
@Service
public class InvoiceNotificationService {

    private final PdfGenerator pdfGenerator;
    private final InvoiceMailService mailService;

    public InvoiceNotificationService(
            PdfGenerator pdfGenerator,
            InvoiceMailService mailService
    ) {
        this.pdfGenerator = pdfGenerator;
        this.mailService = mailService;
    }

    public void notifyCustomer(Invoice invoice) throws MessagingException {
        byte[] pdf = pdfGenerator.generateInvoice(invoice);

        mailService.sendInvoice(
                invoice.getCustomerEmail(),
                invoice.getNumber(),
                pdf
        );
    }
}
~~~

Mail service:

~~~java
@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes
    ) throws MessagingException {

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalArgumentException("Empty PDF");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Invoice " + invoiceNumber);
        helper.setText(
                "Hello,\n"
                + "Invoice " + invoiceNumber
                + " is sent in the attached file.",
                false
        );

        helper.addAttachment(
                "invoice-" + invoiceNumber + ".pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

This is an illustrative example. In a real system, `invoiceNumber` must be sanitized before use in the filename or subject, `recipient` must be validated, and PDF bytes must come from a trusted source.

### 10.1. Is it necessary to write the PDF to disk before sending?

No, if the PDF is already in `byte[]` and its size is suitable. ByteArrayResource lets you place the data directly into the MIME part.

If the application needs to store the PDF copy for another purpose, such as user downloads from a portal or long-term archiving, it can both save to storage and send the email. Those two requirements are independent; sending an email should not be the sole reason the system has to create a temporary file.

## 11. Combining ByteArrayResource with HTML content

An attachment can accompany HTML:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("manager@example.net");
helper.setSubject("Monthly report");

helper.setText(
        "<html><body>"
      + "<h2>Report is ready</h2>"
      + "<p>Please download the attached CSV file.</p>"
      + "</body></html>",
        true
);

helper.addAttachment(
        "monthly-report.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);

mailSender.send(message);
~~~

**MULTIPART_MODE_MIXED** here allows the body and attachment to be independent parts. If the HTML also references inline images via **cid:**, use the **MULTIPART_MODE_MIXED_RELATED** structure and add inline resources with **addInline**.

Do not confuse an attachment from ByteArrayResource with an inline resource:

- **addAttachment** is for separately downloadable files.
- **addInline** is for resources referenced by HTML via Content-ID.
- Both can use the same ByteArrayResource source, but their MIME semantics and APIs differ.

## 12. Attaching from database data or object storage

An application may store file content in a database as a BLOB or fetch it from object storage.

### 12.1. Reading bytes from a database

Example:

~~~java
byte[] documentBytes = documentRepository
        .findContentById(documentId)
        .orElseThrow();

helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(documentBytes),
        "application/pdf"
);
~~~

The repository returning `byte[]` is illustrative. In a real system, check file size, database data type, how BLOBs are loaded, and whether the driver materializes the entire content onto the heap.

If the document is large, reading the entire BLOB into `byte[]` can increase memory pressure. A different storage strategy or streaming may be needed.

### 12.2. Reading data from object storage

If the storage SDK returns `byte[]`:

~~~java
byte[] objectBytes = storageClient.downloadAsBytes(objectKey);

helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(objectBytes),
        "application/pdf"
);
~~~

This approach is simple, though it loads the entire object into memory before sending.

If the SDK provides a large stream, consider downloading to a managed temporary file or using an InputStreamSource capable of opening a new stream as requested by Jakarta Mail. Never pass a one-shot stream assuming the library only reads it once.

### 12.3. Access permissions and data sources

Before placing a document into an email, the application needs to determine:

- Is the current user authorized to receive this document?
- Does the document belong to the right order or customer?
- Is the data in a finalized state?
- Are virus scans or file-type checks needed?
- Is the file permitted to be emailed under storage policy?

A technically readable resource does not mean the application is authorized to send it to any recipient.

## 13. Memory management and performance

ByteArrayResource is very convenient, but it keeps all data on the heap. For small files, that is usually simple. For large files or many concurrent emails, careful consideration is needed.

### 13.1. Baseline cost

Suppose the original file has size **N bytes**. When using ByteArrayResource:

1. The original `byte[]` occupies roughly N bytes on the heap.
2. If a defensive copy is made, there are another ~N bytes.
3. If the source is built with ByteArrayOutputStream, the internal buffer and `toByteArray` result may coexist temporarily.
4. MIME transport may encode and buffer the content, incurring additional memory.
5. Base64 is roughly **4/3 of the original data**, excluding CRLF, headers, and boundaries.

This is an estimation model, not an exact allocation guarantee across every library version.

For example, 20 emails sent concurrently, each with a 10 MB attachment. The raw bytes alone could occupy around 200 MB if each email holds a separate copy of the data; MIME encoding and other buffers can increase that further.

### 13.2. Avoid holding byte[] for too long

After sending completes and no references remain, `byte[]` can be reclaimed by the garbage collector. However, if the application keeps attachments in caches, collections, or long-lived objects, the data continues occupying heap.

Some guidelines:

- Keep `byte[]` only within the necessary scope.
- Never dump entire file contents into logs.
- Avoid storing `byte[]` in singletons or static collections without a clear reason.
- Limit the number of emails with large attachments sent concurrently.
- Enforce size limits before materializing files into `byte[]`.
- Monitor heap, GC, and queues when sending mail in bulk.

### 13.3. When should you use FileSystemResource?

If a large file has already been created on disk, **FileSystemResource** may be more appropriate:

~~~java
helper.addAttachment(
        "large-report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);
~~~

The resource reads from the file on demand as required by the library rather than requiring the application to hold the entire `byte[]` upfront. Still, creating the MimeMessage and transport may buffer data; do not assume FileSystemResource guarantees zero-memory end-to-end streaming.

### 13.4. When should you use an object storage link instead of an attachment?

For very large documents or many files, sending a time-limited download link can reduce email size. This approach requires designing proper access control, expiration, authentication, logging, and link revocation.

This is an architectural alternative to attachments. If business rules require the recipient to have the document directly in the email and the provider allows it, an attachment may still be the right choice.

## 14. Error handling when creating and sending attachments

Errors can occur at multiple stages:

| Stage | Error example | Meaning |
| --- | --- | --- |
| Data generation | PDF generator failure | No file bytes available to send |
| Source loading | `byte[]` is null or empty | Attachment has no valid content |
| MIME creation | Invalid name or MIME metadata | Cannot construct part properly |
| Resource reading | Data source fails to provide stream | MIME serialization fails |
| SMTP sending | Timeout, AUTH error, recipient rejected | Server did not accept message as requested |
| Post-delivery | Bounce, spam, or recipient policy | SMTP accept does not guarantee inbox placement |

**MimeMessageHelper.addAttachment** may throw **MessagingException** when the MIME structure cannot be established. **JavaMailSender.send** may throw various **MailException** subtypes when sending fails. Errors in the PDF generator or storage belong to the file-producing data layer.

Separate these categories to apply appropriate retry strategies.

### 14.1. Do not blindly retry the entire business generation and sending flow

Suppose the PDF was generated successfully and an SMTP timeout occurs. If you retry the entire invoice-creation transaction, you might create duplicate invoices or other side effects. Separate:

- Generating or retrieving the exact document to send.
- Building the message.
- Sending the email.
- Persisting status and retrying by event ID or business key.

If the SMTP outcome is unknown because the connection dropped after the server may have received DATA, retrying could create duplicate emails. SMTP does not guarantee exactly-once delivery.

### 14.2. Logging errors without exposing file contents

Logs can record an appropriate invoice ID or job ID, document type name, byte size, MIME type, error code or exception type, retry count, and timestamp.

Never log full `byte[]`, PDF contents, tokens, personal data, or SMTP authentication credentials.

### 14.3. Handling optional attachments

If business rules allow an email without a file when the document is not yet ready, express that explicitly:

~~~java
if (pdfBytes != null && pdfBytes.length > 0) {
    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );
}
~~~

If the attachment is mandatory, do not silently skip a null/empty file and send the email as if the invoice were attached. Raise a business error or transition the task to a state waiting for document generation.

## 15. Security of data in attachments

An attachment can contain more sensitive information than the email body. Using ByteArrayResource does not replace security controls.

### 15.1. Verify recipient authorization for the document

Before sending, verify that the recipient is authorized to receive the file. Do not take a document ID from a request and send the corresponding file without access control checks.

### 15.2. Validate file type and size

If the file comes from an upload or external source, validate the actual file type rather than just the extension; enforce size limits before reading all bytes; apply malware scanning if required by policy; allow only business-approved formats.

### 15.3. Filenames must not contain sensitive data

Filenames may be visible to the recipient. Never include internal paths, system usernames, storage directories, secrets, or internal metadata in the filename.

### 15.4. Base64 is not security encryption

MIME typically uses base64 to represent binary data, but anyone with the email can decode it. If a document requires protection, use document encryption or an authenticated download channel per business requirements; do not rely on base64.

### 15.5. Storage limits and retention

After an email is sent, the attachment may persist in the recipient's mailbox and intermediate mail systems under their policies. Clearing `byte[]` from the heap or deleting temporary files does not recall already-sent copies.

Consider which data is permitted in email, retention durations, and how to handle data deletion requests under organizational policy.

## 16. Comparing ByteArrayResource with other options

| Criterion | ByteArrayResource | FileSystemResource | ClassPathResource |
| --- | --- | --- | --- |
| Source | `byte[]` | File on disk | Classpath resource |
| Needs physical file? | No | Yes | Not necessarily after packaging |
| Data on heap | Entire `byte[]` kept on heap | Does not require materializing whole file upfront at Resource layer | Depends on how resource is read |
| Re-readable | Yes, from the byte array | Usually can re-open file | Usually can re-open resource |
| Suitable for | Content generated in memory | Large reports already saved | Logos, static application files |

**InputStreamResource** is another option, though you must understand its one-shot nature. Do not replace ByteArrayResource with an InputStreamResource wrapping an already-read or closed stream.

### 16.1. Choosing by data source

- Newly generated in-memory file, small/medium size: **ByteArrayResource**.
- Report file already saved on the filesystem: **FileSystemResource**.
- Logo or document template packaged with the application: **ClassPathResource**.
- Stream source that can be re-opened per contract: an appropriate **InputStreamSource**.
- Very large documents: consider storage and a download/sending workflow designed for streaming or controlled links.

## 17. Separating file generation and mail sending responsibilities

A maintainable service structure may look like:

~~~text
InvoiceApplicationService
       |
       v
InvoicePdfGenerator
       |
       v
byte[] PDF
       |
       v
InvoiceMailService
       |
       +-- MimeMessage
       +-- MimeMessageHelper
       +-- ByteArrayResource
       +-- addAttachment(...)
       |
       v
JavaMailSender
~~~

The PDF generator does not need to know about SMTP. The mail service does not need to know how to calculate totals or lay out PDF pages. Each component can be tested independently.

~~~java
public interface InvoicePdfGenerator {
    byte[] generate(Invoice invoice);
}

public interface InvoiceMailer {
    void send(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes
    ) throws MessagingException;
}
~~~

This separation allows swapping the PDF library or changing the byte source without modifying MIME-building logic.

### 17.1. Do not let SMTP prolong database transactions

If the PDF is generated from order data, define appropriate transaction boundaries. One transaction can capture a data snapshot and update status; generating the PDF and sending the email can run after commit if they do not need to be inside that transaction.

SMTP is an external system and cannot be rolled back along with the database. For critical emails needing durable retries, consider an outbox/queue instead of holding a database transaction open while waiting to send.

### 17.2. ByteArrayResource does not decide when sending occurs

ByteArrayResource only represents data. It does not run asynchronously on its own, create queues, manage retries, or know whether a transaction has committed. Those decisions belong to the orchestration service or worker.

## 18. Testing attachments from byte[]

Multiple layers can be tested without sending emails to real mailboxes.

### 18.1. Testing the source data

For PDFs, verify `byte[]` is non-null/non-empty and generated from a valid document. For CSVs, verify encoding and contents. For images, verify the actual format.

### 18.2. Inspecting the MIME message

Use tests with MimeMessage or an SMTP capture server to confirm:

- The message is multipart.
- There is an attachment part.
- The filename is correct.
- The Content-Type is correct.
- The data after MIME decoding matches the source bytes.
- The body still contains the expected content.

Do not depend on random boundary strings or assume Base64 will wrap lines in a fixed way.

### 18.3. Testing error cases

Scenarios that can be tested independently:

- Null `byte[]`.
- Empty `byte[]`.
- File exceeding size limit.
- Invalid filename.
- Disallowed MIME type.
- Mail sender throwing an exception.
- Resource failing to supply data.
- SMTP server rejecting the message due to size.

These are test scenarios applicable to the project. Specific testing must be executed in a dedicated testing phase.

## 19. Common mistakes when using ByteArrayResource

| Mistake | Cause | Solution |
| --- | --- | --- |
| Cannot call addAttachment with `byte[]` | `byte[]` is not an InputStreamSource | Wrap in ByteArrayResource |
| Email has no attachment | Message was not created in multipart mode or addAttachment was not called | Use multipart MimeMessageHelper |
| Downloaded file is corrupted | Bytes were Base64-encoded before wrapping in resource, or wrong MIME type/bytes | Pass raw bytes and declare the right type |
| Wrong filename | Filename was not explicitly passed | Use an overload accepting attachmentFilename |
| MIME type is `application/octet-stream` | ContentType was not declared or could not be detected | Pass explicit MIME type when known |
| Sending large files causes OutOfMemoryError | Whole `byte[]` and buffers occupy heap | Enforce size limits, reduce concurrency, use another storage/resource |
| Error while reading stream | Used a one-shot source that cannot be re-opened | Use ByteArrayResource or a source capable of creating new streams |
| Data changed before sending | Mutable `byte[]` shared with another thread | Use an immutable snapshot or defensive copy when needed |
| Filename leaks internal path | Used a path as the attachment name | Set a dedicated display name, never a path |
| Wrong document sent | Did not verify recipient's authorization for the document | Perform authorization before building the message |
| SMTP rejects oversized message | Total size after MIME exceeds limit | Limit file/total message size or use a download link |

## 20. Frequently asked questions

**1. What is ByteArrayResource used for when sending mail?**

It wraps `byte[]` data into a Spring Resource capable of supplying an InputStream, matching the **MimeMessageHelper.addAttachment(...)** overload that accepts InputStreamSource.

**2. Do I need to write byte[] to a file before attaching?**

No. If the data is already in memory and its size is suitable, you can use ByteArrayResource directly.

**3. Do I need to Base64-encode beforehand?**

No. Pass raw bytes. Jakarta Mail handles Content-Transfer-Encoding when building the MIME message.

**4. Why does addAttachment need a filename?**

ByteArrayResource only carries data; it does not inherently know what filename the recipient should see. The filename is passed separately through the API.

**5. Can I attach multiple ByteArrayResource instances?**

Yes. Call `addAttachment` multiple times before calling `send`. Each call adds another MIME part.

**6. Can ByteArrayResource be used for CSV?**

Yes. Convert the CSV content to `byte[]` using UTF-8 and call `addAttachment` with **text/csv; charset=UTF-8**.

**7. Can ByteArrayResource be read multiple times?**

Yes. It is backed by a byte array and can provide a new InputStream from that data. This is a convenience compared to a read-once stream.

**8. Should ByteArrayResource be used for a 100 MB file?**

Usually this requires very careful consideration. The data must sit on the heap and MIME building may use extra buffers. Large files should use a more appropriate storage/reading method while also respecting SMTP provider limits.

**9. Does ByteArrayResource set Content-Type automatically?**

Do not rely on it to determine every format. If you know the file type, pass `contentType` explicitly in `addAttachment`.

**10. Does ByteArrayResource set filename automatically?**

No. Pass the filename separately via `addAttachment`.

**11. Can SimpleMailMessage send attachments?**

No. Use MimeMessage and MimeMessageHelper with multipart mode.

**12. Can the same byte[] be used for an attachment and an inline image?**

You can create resources from `byte[]` for both `addAttachment` and `addInline`, but the two operations have different MIME semantics. Attachments are for separately downloaded files; inline resources require a Content-ID for HTML references.

**13. Does ByteArrayResource automatically protect data from being modified?**

Do not treat it as an immutable copy of `byte[]`. If the array is shared and modified, the read content may change. You can clone when an independent snapshot is needed, but account for additional memory.

**14. Does a successful send prove the file reached the inbox?**

No. SMTP accepting the message is one milestone; afterward, bounces, spam filtering, size limits, or receiving system policies can still occur.

## 21. Key takeaways when attaching from ByteArrayResource

**ByteArrayResource** lets Spring Mail attach content already in **byte[]** without creating a physical file. Create a **MimeMessage**, initialize **MimeMessageHelper** in multipart mode, wrap the data in **ByteArrayResource**, and call **addAttachment(filename, resource, contentType)**.

Pass raw bytes and let Jakarta Mail handle Base64; set the filename and MIME type accurately; control size, data source, recipient permissions, and byte array lifecycle. ByteArrayResource has the advantage of re-reading from memory, but it is not suitable by default for very large files because all data resides on the heap and MIME generation can allocate additional memory.

When a document is already on disk or too large, consider **FileSystemResource** or a different storage/streaming strategy. Whichever Resource you choose, attaching remains one part of **MimeMessage**; sending mail, retries, and transaction management are separate responsibilities of the application layer.

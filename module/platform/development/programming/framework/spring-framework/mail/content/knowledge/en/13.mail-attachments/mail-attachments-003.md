# Attaching from InputStreamSource

## 1. What is InputStreamSource?

In **Spring Framework Mail**, when an email needs to attach a file, the application does not necessarily have to read the entire file into a byte array before creating the message. Spring provides the **InputStreamSource** abstraction to describe a source capable of opening an **InputStream** on demand.

The interface resides in the **org.springframework.core.io** package and has a simple contract:

~~~java
package org.springframework.core.io;

import java.io.IOException;
import java.io.InputStream;

public interface InputStreamSource {
    InputStream getInputStream() throws IOException;
}
~~~

This is a conceptual signature for learning; the application uses Spring's built-in interface rather than redeclaring it.

The key point is that **InputStreamSource describes how to obtain a stream, not an already-opened stream itself**. This is useful when the library needs to read the content at MIME serialization or email sending time. A proper implementation should return **a fresh InputStream for each call to getInputStream()**.

Spring emphasizes this requirement because APIs like JavaMail may need to read the content multiple times while building and sending the attachment. If the application only passes in an already-opened stream and that stream has already been read or closed, subsequent reads may fail.

### How does InputStreamSource differ from InputStream?

| Type | Meaning | Lifecycle |
|---|---|---|
| **InputStream** | An open stream for reading bytes | Has a current read position; usually needs closing; usually cannot be re-read from the start |
| **InputStreamSource** | An object providing a method to open a stream | Can create a new stream when requested |
| **Resource** | Spring's richer abstraction for resources | Extends InputStreamSource, adding information like description, existence/readability, and access methods depending on implementation |

Example:

~~~java
InputStream stream = Files.newInputStream(path);
~~~

This snippet opens a concrete stream. Meanwhile:

~~~java
InputStreamSource source = () -> Files.newInputStream(path);
~~~

The second snippet describes how to open a stream from a file. Each call to **source.getInputStream()** requests opening a new stream from that path.

## 2. Why does Spring Mail accept InputStreamSource?

**MimeMessageHelper** supports adding attachments via methods such as:

~~~java
helper.addAttachment(String attachmentFilename, InputStreamSource inputStreamSource);
helper.addAttachment(
        String attachmentFilename,
        InputStreamSource inputStreamSource,
        String contentType
);
~~~

The first method lets the helper infer the content type from the resource or filename when possible. The second method lets the application explicitly specify the **Content-Type**, such as **application/pdf**.

Overall flow:

~~~text
Application selects file / data
          |
          v
    InputStreamSource
    (how to open stream)
          |
          v
MimeMessageHelper.addAttachment(...)
          |
          v
MIME body part created for attachment
          |
          v
JavaMailSender.send(message)
          |
          v
Jakarta Mail reads data and writes message
          |
          v
SMTP transport
~~~

Benefits of this abstraction:

- **No need to open streams prematurely** just to pass them to the helper.
- **Decouples data sources from MIME structure**: files can come from the classpath, filesystem, memory, or a storage service.
- **Supports re-reading** if the source provides a fresh stream each time.
- **Avoids manual MIME assembly**: Spring and Jakarta Mail handle headers, boundaries, encoding, and attachments.
- **Easy to swap sources** without rewriting the entire mail-sending logic.

InputStreamSource does not send files by itself and does not verify access permissions. It only supplies data for the MIME layer to consume when needed.

## 3. Flow for creating attachments with MimeMessageHelper

To attach a file, an application typically creates a **MimeMessage**, enables multipart mode on **MimeMessageHelper**, and calls **addAttachment(...)**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendReport(JavaMailSender mailSender, String recipient)
        throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            "UTF-8"
    );

    helper.setFrom("reports@example.com");
    helper.setTo(recipient);
    helper.setSubject("Monthly report");
    helper.setText("The monthly report is attached to this email.");

    helper.addAttachment(
            "monthly-report.pdf",
            new ClassPathResource("reports/monthly-report.pdf"),
            "application/pdf"
    );

    mailSender.send(message);
}
~~~

Example assumptions:

- The application already has a properly configured **JavaMailSender** bean.
- The resource **reports/monthly-report.pdf** exists on the classpath.
- The SMTP provider allows this sender address and message size.

Explanation:

1. **createMimeMessage()** creates a new MIME object.
2. **MimeMessageHelper(message, true, "UTF-8")** enables multipart and uses UTF-8 for relevant text/headers.
3. **setFrom**, **setTo**, **setSubject**, and **setText** configure the email metadata and body.
4. **addAttachment(...)** adds a MIME part with a display filename and data source.
5. **send(message)** hands the prepared message to the mail transport.

The **true** parameter enables multipart mode. If the helper is created in non-multipart mode and `addAttachment` is called, the message structure lacks a place to hold attachments and the operation may fail.

## 4. Choosing the right addAttachment overload

Spring Mail provides common overloads:

~~~java
helper.addAttachment("report.pdf", inputStreamSource);
helper.addAttachment("report.pdf", inputStreamSource, "application/pdf");
~~~

| Parameter | Meaning |
|---|---|
| **attachmentFilename** | The filename visible to the recipient in their email client |
| **inputStreamSource** | A source capable of opening an InputStream to read attachment data |
| **contentType** | The MIME media type of the content, e.g. `application/pdf` or `image/png` |

Example:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);
~~~

Specify the content type explicitly when the source does not provide a useful filename, the file type cannot be reliably inferred, or the application wants explicit control over MIME metadata. **The Content-Type must match the actual data**, not merely the filename submitted by a user.

The **attachmentFilename** is the display name in the message, not a path for Jakarta Mail to locate a file. The data source determines which bytes are read. Thus you can read data from a filesystem file while setting the display name to **invoice.pdf**.

## 5. Using ClassPathResource for files packaged with the application

When static files are stored in **src/main/resources**, **ClassPathResource** can be used:

~~~text
src/
└── main/
    └── resources/
        └── mail/
            ├── terms.pdf
            └── brand-guide.pdf
~~~

Code:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.addAttachment(
        "terms-and-conditions.pdf",
        new ClassPathResource("mail/terms.pdf"),
        "application/pdf"
);
~~~

**ClassPathResource** is suitable for resources packaged with the application. When running from a JAR, resources can still be read from the classpath; the application does not need to assume the file lives in a directly accessible filesystem directory.

Points to note:

- The path passed to ClassPathResource is typically relative to the classpath root, e.g. **mail/terms.pdf**.
- Do not include the **src/main/resources** prefix in the runtime path.
- The filename and case must match the packaged resource.
- Do not use ClassPathResource for files uploaded by users into a runtime directory outside the classpath.

If the resource is missing from the built artifact, read errors may occur when the helper or mail transport requests to open the stream. Successful compilation does not prove the resource is present in the JAR.

## 6. Using FileSystemResource for files on the server

If the file resides on the filesystem, **FileSystemResource** is an option:

~~~java
import org.springframework.core.io.FileSystemResource;
import java.nio.file.Path;

Path reportPath = Path.of("/var/app/reports/monthly-report.pdf");
FileSystemResource report = new FileSystemResource(reportPath);

helper.addAttachment(
        "monthly-report.pdf",
        report,
        "application/pdf"
);
~~~

FileSystemResource supplies a stream by opening the file at the configured path. For large files, this avoids reading the entire content into a byte array before creating the attachment.

However, the path must exist and the application process must have read permission. In addition:

- Do not take an arbitrary filesystem path from an HTTP request and pass it directly to FileSystemResource.
- Verify the path lies inside an allowed directory; consider path traversal and symbolic links.
- The file must remain present and not be replaced or deleted while sending.
- If multiple threads could overwrite the file concurrently, use distinct names/versions or immutable snapshots to avoid sending content different from what was validated.

## 7. Using ByteArrayResource when data is already in memory

If the application already has a byte array, such as a PDF generated by a reporting library, it can wrap it with **ByteArrayResource**:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pdfBytes = createInvoicePdf();

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

**ByteArrayResource** is a Resource implementation backed by a byte array and can provide a fresh stream reading from the beginning on each open. It is a convenient choice for moderately sized content already in memory.

The limitation is that the data already occupies memory. If many large emails are created concurrently, each byte array and serialized MIME part can significantly increase heap pressure. Do not read a very large file into `byte[]` just because `addAttachment` accepts InputStreamSource.

### Creating an InputStreamSource with a lambda

You can provide a source that opens a new stream yourself:

~~~java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

byte[] pdfBytes = createInvoicePdf();

InputStreamSource source =
        () -> new ByteArrayInputStream(pdfBytes);

helper.addAttachment("invoice.pdf", source, "application/pdf");
~~~

Each time **getInputStream()** is called, the lambda creates a new **ByteArrayInputStream** starting at the first byte. This is the key property that makes the source re-readable.

For simple cases, **new ByteArrayResource(pdfBytes)** is usually easier to read. Lambdas are helpful when you need custom logic for opening the source.

## 8. Crucial contract: each call must yield a fresh stream

This is the most error-prone point when working with InputStreamSource.

**An InputStream has read state.** After reading to the end, the next read does not automatically rewind to the first byte. If a stream is closed, it cannot be reused to read data. During MIME construction and sending, Jakarta Mail may request to open attachment data via DataSource more than once.

Therefore, an InputStreamSource implementation should return **a new stream readable from the start** every time it is called.

### Proper implementation

~~~java
InputStreamSource source = () -> Files.newInputStream(reportPath);
~~~

Each call opens a new stream from the file, provided the file still exists and is readable.

Or:

~~~java
InputStreamSource source = () -> new ByteArrayInputStream(bytes);
~~~

Each call creates a new stream from the same byte array.

### Bug-prone implementation

~~~java
InputStream stream = Files.newInputStream(reportPath);
InputStreamSource source = () -> stream;
~~~

Here every call returns **the exact same InputStream**. After the first read, the stream may be at EOF or closed. A subsequent read will yield no expected data or throw an IOException.

Do not hold onto an open stream and wrap it in a lambda pretending the source is re-openable. **InputStreamSource is a stream-creation abstraction, not a way to rename a one-shot stream.**

## 9. Why is InputStreamResource often unsuitable for attachments?

Spring has an **InputStreamResource** class, but not every class implementing InputStreamSource can be safely read multiple times.

**InputStreamResource** typically represents an already-opened InputStream. It is designed for single-read resources; subsequent calls may return an already-consumed stream or fail to re-open. Some execution paths even throw errors when attempting to read the resource a second time.

Example requiring caution:

~~~java
InputStream opened = remoteService.openInvoiceStream();
InputStreamResource oneShot = new InputStreamResource(opened);

helper.addAttachment("invoice.pdf", oneShot, "application/pdf");
~~~

This snippet passes an already-opened stream to the helper. If MIME creation requires reading the source again, the stream has no remaining data or is closed. It also makes the stream lifecycle harder to manage.

**Prefer re-openable sources:**

- **ByteArrayResource** for moderately sized data already in memory.
- **ClassPathResource** for files packaged inside the application.
- **FileSystemResource** for re-readable files on the filesystem.
- A **custom InputStreamSource** that opens a fresh stream from object storage, a database, or another source.

If you only receive a single stream from an external API, consider reading it into `byte[]` with a size limit or spooling it to a temporary file to provide a re-openable source.

## 10. Example of writing a custom InputStreamSource for a file

When you want to explicitly represent opening a new file stream each time, you can write a small implementation:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.core.io.InputStreamSource;

public final class PathInputStreamSource implements InputStreamSource {

    private final Path path;

    public PathInputStreamSource(Path path) {
        this.path = path;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        return Files.newInputStream(path);
    }
}
~~~

Usage:

~~~java
Path reportPath = Path.of("/var/app/reports/report.pdf");
InputStreamSource source = new PathInputStreamSource(reportPath);

helper.addAttachment("report.pdf", source, "application/pdf");
~~~

Each time **getInputStream()** is called, the implementation asks the operating system to open a new file handle. This class is useful for illustrating the contract; in ordinary applications, you can use **FileSystemResource** directly to avoid unnecessary classes.

### Controlling file stability

Opening a fresh stream does not by itself guarantee the file content remains unchanged between reads. If another process overwrites the file during sending, two opens could read different contents. For important attachments:

1. Use a unique filename for each report generation.
2. Finish writing the file before creating the source.
3. Do not modify the file throughout the sending period.
4. Only delete temporary files after the send call completes and the resource is no longer needed.

## 11. Fetching attachments from a storage service or external system

In real applications, files may reside in object storage, a document service, or a database. InputStreamSource helps decouple storage location from MIME construction.

Example of a storage service providing a stream-opening operation:

~~~java
InputStreamSource source = () -> objectStorage.openStream(
        bucketName,
        objectKey
);

helper.addAttachment(
        "customer-report.pdf",
        source,
        "application/pdf"
);
~~~

**objectStorage.openStream(...)** is a hypothetical storage system API, not a Spring API. The key requirement is that each call returns a new stream reading the exact same object version.

### Considerations when opening streams from remote storage

- **Re-readable:** the source must open a new request/stream when requested again.
- **Same data version:** if the object can change, pin the version or use an immutable key throughout the send process.
- **Timeouts:** opening a stream can hang due to network issues; enforce timeouts and handle errors.
- **Permissions:** credentials used to fetch the file must follow least privilege.
- **Size:** check the size before sending so you do not build a message exceeding SMTP/ESP limits.
- **Closing connections:** each stream must be properly managed and closed after being read.

Never build a source by fetching data from an arbitrary user-supplied URL. Having the server access uncontrolled URLs can lead to **SSRF**, reading internal resources, or bandwidth abuse.

## 12. When the source can only be opened once: byte array or temporary file?

Some APIs return a one-shot InputStream, such as an HTTP client response body or a stream from a file-generating process. Passing this stream directly to the helper can violate the re-readability requirement.

There are two common strategies:

### Strategy A — Read into a byte array

~~~java
byte[] content;

try (InputStream input = remoteClient.openDocument(documentId)) {
    content = input.readAllBytes();
}

InputStreamSource repeatable = new ByteArrayResource(content);
helper.addAttachment("document.pdf", repeatable, "application/pdf");
~~~

Advantages:

- Data resides in memory and can be opened multiple times.
- Simple code with easy lifecycle control over the source stream.
- Suitable for small/medium files with clear size limits.

Limitations:

- The entire file occupies heap memory.
- Multiple concurrent attachments can cause memory pressure.
- **readAllBytes()** has no size cap; do not use it directly on untrusted sources or potentially very large files.

In production, check the size beforehand or use a bounded reader to reject oversized files.

### Strategy B — Write to a temporary file

~~~java
Path tempFile = Files.createTempFile("mail-attachment-", ".pdf");

try (InputStream input = remoteClient.openDocument(documentId)) {
    Files.copy(input, tempFile, StandardCopyOption.REPLACE_EXISTING);
}

InputStreamSource repeatable = () -> Files.newInputStream(tempFile);
helper.addAttachment("document.pdf", repeatable, "application/pdf");

// Keep tempFile available until send(message) completes.
~~~

This example illustrates the lifecycle; add `try/finally` to delete the temporary file after sending or upon error handling. Do not delete the file immediately after **addAttachment(...)** if the transport has not read the content yet.

Advantages:

- Does not hold entire large files on the heap.
- The file can be re-opened from the beginning.
- Easy to compute checksums or scan contents before sending.

Limitations:

- Requires disk space and a temporary-file cleanup policy.
- Requires directory permissions, safe filenames, and protection against concurrent access.
- Must guarantee the file is not deleted before the mail transport finishes reading it.

### Which strategy to choose?

| Size and source | Usually appropriate choice |
|---|---|
| Logo or small file already in `byte[]` | **ByteArrayResource** |
| Static file inside the application | **ClassPathResource** |
| Large file already on disk | **FileSystemResource** |
| Remote object with a fresh-stream API | **Custom InputStreamSource** |
| One-shot remote response, small/medium file | Bounded read into **ByteArrayResource** |
| One-shot remote response, large file | Spool to temp file, then re-open via InputStreamSource |

## 13. Attachment filename and Content-Type

These two pieces of information are used by email clients to display and handle the file:

- **Filename**: the display name for the recipient, e.g. **invoice-2026.pdf**.
- **Content-Type**: the MIME media type, e.g. **application/pdf**, **image/png**, **text/csv**.

Example:

~~~java
helper.addAttachment(
        "invoice-2026.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf"
);
~~~

### A filename is not a filesystem path

Do not pass full paths or arbitrary user-supplied values as the filename:

~~~java
// Do not directly use a user-controlled upload value.
helper.addAttachment(upload.getOriginalFilename(), resource);
~~~

An original filename may contain paths, control characters, or misleading names. Generate a safe display name from business data or sanitize it per application rules. Example:

~~~java
String attachmentName = "invoice-" + validatedInvoiceNumber + ".pdf";
~~~

In this example, **validatedInvoiceNumber** must be a validated code containing no control characters or path components.

### Content-Type must reflect actual data

Do not blindly trust the file extension provided by a user. A file named **report.pdf** is not guaranteed to be a valid PDF. You should:

1. Verify the data source and access permissions.
2. Determine the format according to application rules or check file signatures when needed.
3. Restrict the MIME types allowed to be sent.
4. Set the corresponding Content-Type.
5. Scan for malware or apply file-checking policies per system requirements.

Content-Type is only MIME metadata; it does not turn a malformed file into a valid file nor protect recipients from malicious content.

## 14. Combining attachments with HTML and plain text

An email can contain plain text, HTML, and an attached file together. In this case, **MimeMessageHelper** helps build the proper MIME structure:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendInvoice(
        JavaMailSender sender,
        String recipient,
        Path invoicePath
) throws MessagingException {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("billing@example.com");
    helper.setTo(recipient);
    helper.setSubject("Your invoice");
    helper.setText(
            "Your invoice is attached. Please log in to view details.",
            "<html lang=\"en\"><body>"
                    + "<h2>Your invoice</h2>"
                    + "<p>Your invoice is attached to this email.</p>"
                    + "</body></html>"
    );

    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(invoicePath),
            "application/pdf"
    );

    sender.send(message);
}
~~~

This example assumes **invoicePath** is an already-created, readable file that persists during sending. **MimeMessageHelper** in multipart mode enables combining the body with attachments; if adding inline resources, select an appropriate multipart mode such as **MULTIPART_MODE_MIXED_RELATED**.

Conceptual MIME structure:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    └── application/pdf
        └── Content-Disposition: attachment
~~~

This is a conceptual diagram. The exact MIME tree built by the helper/Jakarta Mail may vary by multipart mode and include a **multipart/related** layer when inline images are present.

## 15. Multiple attachments in one email

You can call **addAttachment(...)** multiple times on the same helper:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);

helper.addAttachment(
        "terms.pdf",
        new ClassPathResource("mail/terms.pdf"),
        "application/pdf"
);

helper.addAttachment(
        "summary.csv",
        new ClassPathResource("mail/summary.csv"),
        "text/csv"
);
~~~

Each call adds a separate MIME part to the same message. Recipients will see the files under the configured attachment names.

### Notes when adding multiple files

- Calculate the **total size** of all attachments along with the body, headers, and MIME encoding overhead.
- Avoid creating too many large byte arrays simultaneously.
- Verify recipient permissions for each file, not just for the email overall.
- Assign distinct, clear, non-confusing filenames.
- Specify the content type for each file.
- Prepare error handling before sending in case one source is unreadable.

If attachments come from multiple sources, you can store a list of objects describing filename, content type, and InputStreamSource, then iterate over the list to call the helper. However, this list should be validated beforehand and every source must still be able to open a stream at send time.

## 16. Managing stream and resource lifecycles

**Do not open an InputStream yourself and leave it unclosed** just to pass it to the helper. When using InputStreamSource, let the source be responsible for opening streams on demand and ensure each stream's lifecycle is properly managed.

Some principles:

- Do not open a stream in a controller and pass it down through multiple business layers.
- Do not close resources before the mail transport finishes reading.
- Do not delete a temporary file immediately after calling `addAttachment`; keep it until **send(...)** finishes or fails.
- For remote sources, every open must have appropriate timeouts and access permissions.
- Do not share a stateful InputStream across multiple sends or threads.
- If the same source is used for multiple emails, make sure it can open fresh streams and the data does not change between sends.

### Example keeping a temporary file until send completes

~~~java
Path tempFile = Files.createTempFile("invoice-", ".pdf");

try {
    try (InputStream input = documentService.openInvoice(invoiceId)) {
        Files.copy(
                input,
                tempFile,
                StandardCopyOption.REPLACE_EXISTING
        );
    }

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            "UTF-8"
    );
    helper.setTo(recipient);
    helper.setFrom("billing@example.com");
    helper.setSubject("Invoice");
    helper.setText("The invoice is attached.");
    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(tempFile),
            "application/pdf"
    );

    // The send call must complete before the temporary file is deleted.
    mailSender.send(message);
} finally {
    Files.deleteIfExists(tempFile);
}
~~~

This is a synchronous example, assuming **documentService.openInvoice(...)** returns an InputStream and `mailSender.send(...)` finishes submitting the message before returning. If the application offloads sending to a background task, the file must persist until the task actually finishes; it cannot be deleted immediately upon enqueuing.

In a multi-worker environment, manage temp file permissions, unique filenames, orphan file cleanup when a process crashes, and temp directory disk usage.

## 17. Attachment size and performance

Using InputStreamSource **does not mean the entire sending process always streams with constant memory**. Jakarta Mail may read data and encode/serialize the message when sending; SMTP servers also enforce message size limits. A large file can increase memory usage, send latency, and queue size.

Contributing factors:

1. **Original file size**.
2. **MIME transfer encoding**: binary data is usually base64-encoded, making the encoded representation larger than the raw data.
3. **Number of attachments** and total size.
4. **Number of emails sent concurrently**.
5. **SMTP/ESP quotas** and destination mail server limits.
6. **Transport implementation** and application heap/disk resources.

### Size estimation

Base64 typically increases binary data by about one-third, excluding CRLF, headers, and MIME boundaries. Thus, a 9 MB file can occupy around 12 MB for the base64 section in the message before adding other content. This is a budgeting estimate, not an exact size for every email.

If files are large or there are many recipients, consider sending a **secure download link** instead of attaching directly. Links require HTTPS, access controls, expiration, and proper revocation capability; never use a public URL as a substitute for data protection.

### Size limits must come from the provider

Spring Framework Mail does not enforce a universal limit applicable to all SMTP servers. Providers may restrict:

- Total email size.
- Individual file size.
- Number of attachments.
- Sending rate and total volume.
- Number of recipients per message.

The application should check upfront to reject or choose an alternative delivery method rather than waiting for SMTP to fail at the end of the workflow.

## 18. Error handling when the attachment source cannot be read

Errors can happen at several stages:

| Stage | Error example | Investigation direction |
|---|---|---|
| Source preparation | File does not exist, read permission denied | Check paths, classpath, and permissions |
| Opening stream | `InputStreamSource.getInputStream()` throws IOException | Inspect storage source, remote connection, file lifecycle |
| Reading stream | Truncated data, remote stream timeout | Check source logs, size, and checksum |
| Building MIME | Invalid headers, filename, or content type | Check helper and metadata |
| SMTP submission | Message too large, relay rejected, connection error | Check MailException and SMTP response |
| After SMTP acceptance | Destination mailbox bounce or quarantine | Check ESP events and recipient-side policies |

In Spring Mail, sending failures may surface under the **MailException** hierarchy, such as **MailSendException**. When working with MimeMessageHelper/Jakarta Mail, MIME preparation errors can arise as **MessagingException**; source read errors may appear in the root cause or be wrapped by the sending layer.

Example isolating source errors before invoking the sender:

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;

try {
    mailSender.send(message);
} catch (MailException ex) {
    // Log notification ID, attempt ID, and a safe cause.
    // Check whether SMTP already accepted the data before retrying.
    throw ex;
}
~~~

Do not retry indefinitely on missing sources, corrupted files, or permission errors. For timeouts after sending DATA, the state may be ambiguous: the server may have accepted the email even though the application did not receive the response. Retrying without reconciliation can cause duplicate sends.

## 19. Security when sending attachments

Attachments may contain invoices, reports, records, or personal data. **InputStreamSource only helps supply bytes; it does not enforce who is authorized to receive those bytes.**

Steps to consider:

1. **Business authorization check:** is the recipient permitted to view this file?
2. **Source verification:** is the file retrieved from the right record/account/tenant?
3. **Size limits:** prevent oversized files from exhausting memory or quotas.
4. **Format verification:** validate the actual data type rather than blindly trusting user-supplied filenames or MIME types.
5. **Malware scanning:** apply scanning procedures according to file type and organizational policy.
6. **Safe filenames:** strip paths, control characters, or misleading names.
7. **Log protection:** never write file contents, OTPs, tokens, or sensitive information to ordinary logs.
8. **Storage lifecycle:** delete temporary files on time and comply with retention policies.

### Avoiding path traversal

Do not use user-supplied paths directly:

~~~java
// Unsafe if userPath comes from an uncontrolled request.
FileSystemResource resource = new FileSystemResource(userPath);
~~~

Instead, look up the file via a validated business ID, resolve it within the allowed directory, and verify the real path resides inside the intended storage root. Do not check only string prefixes against the root directory, because symbolic links can escape outside the scope.

### Prevent cross-tenant data leaks

In multi-customer/multi-tenant systems, verify that the resource belongs to the right tenant before creating the InputStreamSource. A source that cleanly opens a file belonging to another user is still a critical authorization vulnerability.

## 20. Example sending an attachment from in-memory generated data

Suppose the application generates a PDF report via an export library and receives a byte array:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendGeneratedReport(
        JavaMailSender sender,
        String recipient,
        byte[] pdfBytes
) throws MessagingException {
    if (pdfBytes == null || pdfBytes.length == 0) {
        throw new IllegalArgumentException("PDF has no data");
    }

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("reports@example.com");
    helper.setTo(recipient);
    helper.setSubject("Report is ready");
    helper.setText("The PDF report is attached to this email.");
    helper.addAttachment(
            "report.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );

    sender.send(message);
}
~~~

This code assumes **pdfBytes** was produced from a trusted source with appropriate size limits. Checking `length > 0` only catches empty arrays; it does not prove the byte array is a valid PDF. If the data comes from a user or external service, validate the format per application policy.

## 21. Example sending a large file from the filesystem

If a large report is already generated on disk, you can pass a FileSystemResource to avoid reading the whole file into a byte array:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;

Path reportPath = reportGenerator.createReportFile();

helper.addAttachment(
        "annual-report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);

mailSender.send(message);
~~~

**reportGenerator.createReportFile()** is a hypothetical application API. The file must exist, be readable, and not be deleted/modified while the transport uses the source. For temporary files, manage cleanup after the send call finishes and provide orphan file cleanup if the process terminates abnormally.

FileSystemResource reduces the need to hold a byte array of the entire file in application code, but it does not guarantee that Jakarta Mail or the SMTP transport avoids extra memory buffers during serialization and sending.

## 22. Verifying MIME and attachment generation

During development, you can inspect the message before real delivery by creating a **MimeMessage** with a test Jakarta Mail Session and verifying the MIME part contents. Goals to check:

- Is the attachment count correct?
- Is the filename accurate and free of unintended paths?
- Does Content-Type reflect the right format?
- Is the full data read completely?
- Does the plain text/HTML body remain intact alongside the attachment?
- Can the source open a fresh stream when requested again?

A simple InputStreamSource can be tested for open count:

~~~java
AtomicInteger openCount = new AtomicInteger();
byte[] bytes = "sample".getBytes(StandardCharsets.UTF_8);

InputStreamSource source = () -> {
    openCount.incrementAndGet();
    return new ByteArrayInputStream(bytes);
};

InputStream first = source.getInputStream();
InputStream second = source.getInputStream();

// Both streams are distinct objects and both read from the beginning.
~~~

This is an example of testing the source contract, not SMTP testing. Verifying message submission and delivery requires an integration test with an SMTP test server or appropriate sandbox.

There is no need to open real customer files or send emails to production recipients to verify MIME structure.

## 23. Common mistakes when using InputStreamSource

| Symptom | Common cause | Solution |
|---|---|---|
| Empty or truncated attachment | Source returns an already-exhausted stream | Open a fresh stream on each call |
| IOException or stream-closed error | Passing a one-shot InputStream via InputStreamResource | Use ByteArrayResource, FileSystemResource, or a re-openable source |
| Classpath file not found | Wrong runtime path or resource not packaged | Check `src/main/resources` and classpath path |
| Server file unreadable | Wrong path or filesystem permissions | Verify path and process permissions |
| Inconsistent old/new attachment content | File modified between opens | Use immutable snapshots/versions |
| Send error due to missing multipart | Helper created with `multipart=false` | Enable multipart when initializing MimeMessageHelper |
| Strange filename displayed | Invalid or unnormalized filename | Use a safe, clear display name |
| File opens in wrong application | Incorrect Content-Type | Determine media type from actual format |
| Email exceeds limit | Large file or too many attachments | Check quotas, optimize file, or send a secure download link |
| High heap usage under concurrent sends | Reading many large files into `byte[]` | Use repeatable disk/remote sources and limit concurrency |
| Temp file missing during background send | Deleting file immediately after enqueue | Keep file until the worker completes |
| Duplicate email retries | Timeout after SMTP may have received message | Log attempts and reconcile state before retrying |
| Wrong tenant's file sent | Missing authorization check before creating source | Verify ownership and tenant-level permissions |

## 24. Choosing an InputStreamSource by scenario

| Attachment source | Suggested choice | Reason |
|---|---|---|
| Static file in JAR | **ClassPathResource** | Reads from classpath, independent of working directory |
| File on server disk | **FileSystemResource** | Re-opens file by path |
| Existing byte array, moderate size | **ByteArrayResource** | Creates fresh streams from memory |
| Source able to open fresh streams | Custom **InputStreamSource** | Controls how data is fetched |
| One-shot HTTP response stream | Bounded read into `byte[]` or spool to temp file | Never reuse a consumed stream |
| Versioned object storage with fresh-stream API | **InputStreamSource** opening stream by version | Can re-read the exact same data |
| Large file already on disk | **FileSystemResource** | Avoids holding another large byte array in application code |

No single option is best for every case. Balance size, re-readability, resource lifecycle, data stability, latency, and memory/disk consumption.

## 25. Key takeaways

**InputStreamSource** is Spring's abstraction for supplying an InputStream on demand. In Spring Framework Mail, **MimeMessageHelper.addAttachment(...)** accepts InputStreamSource to build the MIME part for an attachment. Applications can use **ClassPathResource**, **FileSystemResource**, **ByteArrayResource**, or a custom implementation depending on the data source.

The most important principle is that **each call to getInputStream() must be able to return a fresh stream reading from the beginning**. Avoid wrapping an already-opened InputStream or a one-shot source like **InputStreamResource** and assuming it can be read multiple times. For large sources, prefer re-opening from files or object storage; for small/medium in-memory data, ByteArrayResource is simple and convenient.

When sending attachments, enable multipart, provide the right filename and Content-Type, keep the source available throughout the sending process, enforce size/access controls, and handle errors at the Spring Mail layer. **InputStreamSource solves how bytes are supplied to MIME; the application remains responsible for ensuring those bytes are accurate, safe, and authorized for the recipient.**

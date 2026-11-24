# Streaming Attachments When Possible

## 1. Why Are Large Attachments a Performance Problem?

In **Spring Framework Mail**, an application may send PDF invoices, CSV reports, statements, images, or attached documents using `JavaMailSender` and `MimeMessageHelper`. For small files, reading the entire content into a byte array and attaching it to the email is straightforward. However, for large files or many emails sent concurrently, that approach can cause spikes in **heap memory, GC time, SMTP wait time, and transmitted data volume**.

An example that easily creates memory pressure:

~~~java
byte[] attachmentBytes = Files.readAllBytes(reportPath);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setTo("customer@example.com");
helper.setFrom("reports@example.com");
helper.setSubject("Report");
helper.setText("See attached report.");
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(attachmentBytes),
        "application/pdf");

mailSender.send(message);
~~~

`Files.readAllBytes` allocates an array holding the **entire file in the heap**. If a 40 MiB report is sent concurrently by 20 workers, the raw byte arrays alone can occupy roughly 800 MiB, excluding Spring/Jakarta Mail objects, network buffers, MIME encoding, and application data.

A generally better option is using a resource that opens a **fresh InputStream from the file** when the SMTP transport reads the content:

~~~java
FileSystemResource attachment =
        new FileSystemResource(reportPath);

helper.addAttachment(
        "report.pdf",
        attachment,
        "application/pdf");
mailSender.send(message);
~~~

Here, the application does not have to actively read the whole file into a `byte[]` before attaching it to the MIME message. The mail library can open a stream from the file while preparing/serializing the content.

> **Key point:** "Streaming attachments" in this lesson means **supplying content via streams without materializing the entire payload into the heap before sending**. It does **not** guarantee that the entire Spring → Jakarta Mail → SMTP server pipeline uses zero buffers, never re-reads the stream, or has O(1) memory footprint across all versions/transports. Always test and measure on your actual stack.

## 2. Which Layers Does an Attachment Pass Through?

Typical path:

~~~text
Business request / scheduled job
                |
                v
Report generator / disk / object storage
                |
                v
Spring Resource / InputStreamSource / DataSource
                |
                v
MimeMessageHelper.addAttachment(...)
                |
                v
Jakarta Mail MIME part / DataHandler
                |
                v
MIME serialization + Base64 / transfer encoding
                |
                v
JavaMailSender / SMTP transport
                |
                v
SMTP server / relay
~~~

The application controls how data is initially read, while MIME creation and SMTP writing belong to the library and transport provider. At least three constraints must be understood:

1. **Memory:** Reading a file into a byte array incurs heap cost proportional to file size. Using files/streams can avoid that materialization step.
2. **Network:** Binary email attachments are usually Base64-encoded, significantly increasing wire payload size.
3. **SMTP/provider:** Mail servers may reject emails exceeding size limits or time out, even if the application streams very efficiently.

### 2.1. MIME Contains More Than the Raw File

A message with HTML, plain text, and an attachment can have this structure:

~~~text
MimeMessage (multipart/mixed)
├── multipart/alternative
│   ├── text/plain; charset=UTF-8
│   └── text/html; charset=UTF-8
└── application/pdf
    ├── Content-Disposition: attachment; filename="report.pdf"
    └── Content-Transfer-Encoding: base64
~~~

Real structures may nest `multipart/related` or other parts when using inline resources; do not rigidly assume only a single MIME tree layout exists.

### 2.2. Why Can a 20 MiB File Become a Message Larger Than 20 MiB?

Base64 represents three bytes of data using four characters, meaning a baseline size of roughly \(4/3\) times the binary file, before line wrapping, MIME boundaries, headers, HTML/text, and SMTP overhead.

Estimated examples:

| Binary Data | Approx. Raw Base64 | Actual Message Size |
| --- | --- | --- |
| 1 MiB | 1.33 MiB | Larger than 1.33 MiB due to wrapping/headers |
| 10 MiB | 13.33 MiB | Larger than 13.33 MiB |
| 25 MiB | 33.33 MiB | Larger than 33.33 MiB |
| 50 MiB | 66.67 MiB | Larger than 66.67 MiB |

These are **estimates, not exact SIZE numbers**: the MIME standard typically wraps Base64 into short lines, adding extra bytes. A message also contains multiple parts and metadata. If a provider limits **the entire message** to 25 MiB, you cannot attach a 25 MiB binary file and expect SMTP to accept it.

### 2.3. Streaming Does Not Eliminate SMTP Limits

Suppose an SMTP server accepts at most a 20 MiB message. A 19 MiB input file can still exceed the limit after Base64 and MIME overhead. Workers should check the **estimated final size** before making the SMTP call, though the authoritative verdict still rests with the server/provider.

Do not compute the threshold with a single formula and treat it as a guarantee. For multipart messages with Unicode filenames, HTML, inline images, or content using other transfer encodings, add reasonable overhead and handle SMTP rejections.

## 3. Attachment Data Sources in Spring

`MimeMessageHelper` provides attachment overloads accepting `File`, `InputStreamSource`, or `DataSource` depending on the case. In Spring Framework, `Resource` extends `InputStreamSource`, so many `Resource` implementations work directly.

| Source | Characteristics | When Suitable | Things to Watch |
| --- | --- | --- | --- |
| `FileSystemResource` | Opens a stream from file on each request | Large files already on disk | File must exist until send finishes |
| `PathResource` | Source from `Path`, able to open fresh streams | Files on the filesystem | Read permissions, temp deletion, symlinks |
| `ByteArrayResource` | Retains entire `byte[]` in heap | Small files or data already in memory | Heap cost scales with size |
| `InputStreamResource` | Usually wraps an already-opened stream | Some read-once APIs | **Unsuitable** for attachment sources needing repeated reads |
| Custom `InputStreamSource` | Factory opening a fresh stream when called | Object storage, stable generated content | Must open fresh streams and manage lifetime |
| `jakarta.activation.DataSource` | Provides stream, content type, name | Deep integration with Jakarta Mail | Must implement contract and close streams properly |

For large files on disk, **`FileSystemResource` or `PathResource` is usually the clearest and lowest-risk choice**. If data comes from HTTP, S3/object store, or a database, you may need a flow that spools it into a size-bounded temporary file before sending.

### 3.1. ByteArrayResource: Simple, but Uses Heap

~~~java
byte[] bytes = reportGenerator.toByteArray();
helper.addAttachment(
        "report.csv",
        new ByteArrayResource(bytes),
        "text/csv");
~~~

Pros: stable data, can be re-read via new streams from the same byte array. Cons: **the entire byte array already resides in the heap**, even though the method is named `getInputStream`.

`ByteArrayResource` fits small data, such as a few KiB or an array already returned by another API. No need to ban it outright; choose based on real sizes and concurrency.

### 3.2. InputStreamResource: Why Is It Prone to Bugs?

Avoid the following:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    helper.addAttachment(
            "report.pdf",
            new InputStreamResource(input),
            "application/pdf");
}

mailSender.send(message);
~~~

There are at least two bugs:

1. `try-with-resources` closes the stream **before** `send` actually needs to read it.
2. An `InputStreamResource` wrapping a single stream usually **cannot be re-read**. Jakarta Mail may need to read a part more than once when determining content, encoding, or serializing.

In Spring, the `InputStreamSource` contract for MIME attachments requires **each call to `getInputStream()` to return a fresh stream**, because JavaMail may invoke it multiple times. A single-use source violates this assumption.

### 3.3. FileSystemResource: Short Example

~~~java
import org.springframework.core.io.FileSystemResource;

import java.nio.file.Path;

Path reportPath = Path.of("/data/reports/invoice-123.pdf");
FileSystemResource resource = new FileSystemResource(reportPath);

helper.addAttachment(
        "invoice.pdf",
        resource,
        "application/pdf");
mailSender.send(message);
~~~

`FileSystemResource` lets the library open streams when needed. However, it **does not freeze the file's contents**: if another worker modifies/deletes the file between message preparation and transport read, the email can fail or send unintended content.

Use a finalized, immutable file source, retain ownership, and do not delete it until `send` finishes.

## 4. Critical Rule: Sources Must Be Re-readable

For attachments, many developers assume opening a stream once and "attaching" it to the message is enough. However, MIME data may be accessed multiple times. Therefore, the content source should have these properties:

- **Fresh stream:** each call to `getInputStream()` creates an independent stream.
- **Stable bytes:** reads within the same delivery must yield identical content without silently changing versions.
- **Available until send completes:** do not close or delete the source before serialization completes.
- **Bounded resource usage:** limit size, open connections, and read duration.
- **Safe close:** opened streams are closed by the consumer or by the provider layer as required by the contract.

A simple custom `InputStreamSource` backed by a file:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.core.io.InputStreamSource;

public final class RepeatableFileSource implements InputStreamSource {

    private final Path file;

    public RepeatableFileSource(Path file) {
        this.file = file;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        return Files.newInputStream(file);
    }
}
~~~

Each call to `getInputStream` opens a new file descriptor. This is an educational adapter; in typical applications, `FileSystemResource` already behaves similarly and does not need to be reimplemented.

**Do not implement**:

~~~java
InputStream in = remoteApi.openStream();
InputStreamSource bad = () -> in;  // returns the same stream on the second read
~~~

Such a source can return an exhausted or closed stream when Jakarta Mail accesses it again, causing empty attachments or hard-to-reproduce `IOException`s.

### 4.1. Re-readable Does Not Mean Safe If the File Changes

For example:

~~~text
T1: report.pdf version A
T2: MimeMessageHelper references report.pdf
T3: a separate process overwrites report.pdf with version B
T4: SMTP transport reads report.pdf
~~~

The email may contain version B instead of version A. For financial reports or invoices, maintain a consistent snapshot: a uniquely named immutable temp file, or object storage with an immutable version/ETag ensuring every stream open reads the exact same version.

## 5. Pattern for Attaching Files with JavaMailSender

Synchronous service example:

~~~java
package com.example.mail;

import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.FileSystemResource;
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
            Path immutableReportFile) throws MessagingException {

        if (!Files.isRegularFile(immutableReportFile)
                || !Files.isReadable(immutableReportFile)) {
            throw new IllegalArgumentException(
                    "Report attachment is unavailable");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Monthly report");
        helper.setText(
                "Please see the attached report.",
                "<p>Please see the attached report.</p>");

        helper.addAttachment(
                "report.pdf",
                new FileSystemResource(immutableReportFile),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

This snippet shows **how to attach an existing file**. It is not a complete file-security check: production code must restrict where `Path` originates, verify read authorization, prevent symlinks/path traversal per policy, and validate size and content type.

### 5.1. Name Attachments for Their Purpose

`attachmentFilename` is the name **the recipient will see**, distinct from the filesystem path:

~~~java
helper.addAttachment(
        "monthly-report-11.pdf",            // display filename
        new FileSystemResource(path),      // internal source
        "application/pdf");               // declared MIME type
~~~

Do not use internal paths directly as attachment names (e.g., `C:\\private\\reports\\customer-123.pdf`), as that can leak system structure. For user-supplied filenames, sanitize/strip control characters, CR/LF, and path separators; never trust a filename as proof of content type.

### 5.2. Attachments Differ from Inline Resources

`MimeMessageHelper.addAttachment(...)` is for files the reader can download/view as attachments. `addInline(contentId, ...)` is typically for logos or embedded images referenced in HTML via `cid:...`:

~~~java
helper.setText(
        "<p>Monthly report</p><img src=\"cid:brand-logo\" />",
        true);
helper.addInline(
        "brand-logo",
        new FileSystemResource(logoFile),
        "image/png");
~~~

Inline resources can also be encoded and enlarge the message. For large images, do not inline them merely because they can be streamed; consider image optimization or linked hosting compliant with security/email client policies.

## 6. From HTTP, Object Storage, or Report Generators to a Temp File

Not every attachment already lives on the filesystem. Applications may pull data from:

- Object storage such as S3 or an equivalent service.
- PDF, CSV, or XLSX generation systems.
- An internal service returning content over HTTP.
- Database blobs or document stores.
- User-uploaded files that have passed validation.

In those cases, a pragmatic strategy is **reading the source buffer-by-buffer and writing to a size-bounded temporary file**, then sending via `FileSystemResource`. This is not end-to-end streaming, yet it avoids holding the entire attachment in the heap throughout sending.

~~~text
Remote source / report generator
                  |
                  | InputStream / OutputStream
                  v
           Bounded copy loop
             buffer 8 KiB
                  |
                  v
       Temporary file on local disk
                  |
                  v
         FileSystemResource
                  |
                  v
        MimeMessageHelper
                  |
                  v
        JavaMailSender.send(...)
                  |
                  v
     Delete temp after send finishes
~~~

### 6.1. Why Not Use InputStream.readAllBytes?

Example to avoid with unbounded sources:

~~~java
try (InputStream input = remoteStorage.open(objectKey)) {
    byte[] bytes = input.readAllBytes();
    helper.addAttachment(
            "report.zip",
            new ByteArrayResource(bytes),
            "application/zip");
}
~~~

`readAllBytes` can bloat the heap, exceed quotas, or trigger `OutOfMemoryError` if a response is larger than expected. A `Content-Length` header from an external source is also insufficient protection, as it may be missing, wrong, or altered.

Replace it with a copy loop enforcing a **hard limit on actual bytes read**.

### 6.2. Bounded Spool: Creating a Temp File Within Quota

Helper example using Java 17+:

~~~java
package com.example.mail.attachment;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.springframework.core.io.InputStreamSource;

public final class AttachmentStager {

    private AttachmentStager() {
    }

    /**
     * Source must be authorized by the application before reaching here.
     * temporaryDirectory is a private, non-public directory.
     */
    public static Path stageBounded(
            InputStreamSource source,
            Path temporaryDirectory,
            long maxBytes) throws IOException {

        if (maxBytes <= 0) {
            throw new IllegalArgumentException(
                    "maxBytes must be positive");
        }

        Path staged = Files.createTempFile(
                temporaryDirectory, "mail-attachment-", ".tmp");
        boolean completed = false;

        try (InputStream in = source.getInputStream();
             OutputStream out = Files.newOutputStream(
                     staged,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING)) {

            byte[] buffer = new byte[8192];
            long total = 0;
            int read;

            while ((read = in.read(buffer)) != -1) {
                if (read == 0) {
                    continue;
                }
                if (read > maxBytes - total) {
                    throw new IOException(
                            "Attachment exceeds configured byte limit");
                }
                out.write(buffer, 0, read);
                total += read;
            }

            completed = true;
            return staged;
        } finally {
            if (!completed) {
                Files.deleteIfExists(staged);
            }
        }
    }
}
~~~

Characteristics:

- The copy buffer is only about 8 KiB, not the size of the entire file.
- Enforces **actual** bytes read, rather than trusting headers.
- Closes both input and output when copying finishes or fails.
- Deletes incomplete temp files on copy errors, including when exceeding `maxBytes`.
- Returns the snapshot file path only after all data is written.

In practice, checking permissions on `temporaryDirectory`, filesystem quotas, free space, and source limits belongs to the staging management layer. If a cleanup error occurs alongside a read error, capture both the root cause and cleanup failure (Java try-with-resources supports suppressed exceptions; the `finally` here is simplified).

For untrusted files, verify MIME/content, signatures, and malware per policy after staging. `maxBytes` only bounds size; it does **not** prove the file is safe.

### 6.3. Sending the Temp File and Deleting After `send` Returns

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.InputStreamSource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class StagedMailService {

    private final JavaMailSender mailSender;
    private final Path tempDirectory;

    public StagedMailService(
            JavaMailSender mailSender, Path tempDirectory) {
        this.mailSender = mailSender;
        this.tempDirectory = tempDirectory;
    }

    public void sendAttachment(
            String recipient,
            InputStreamSource source) throws IOException, MessagingException {

        long limit = 15L * 1024 * 1024; // Example: max 15 MiB input.
        Path staged = AttachmentStager.stageBounded(
                source, tempDirectory, limit);

        try {
            MimeMessage mime = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom("reports@example.com");
            helper.setTo(recipient);
            helper.setSubject("Attached report");
            helper.setText(
                    "Please see the attached file.",
                    "<p>Please see the attached file.</p>");
            helper.addAttachment(
                    "report.pdf",
                    new FileSystemResource(staged),
                    "application/pdf");

            mailSender.send(mime);
        } finally {
            Files.deleteIfExists(staged);
        }
    }
}
~~~

`JavaMailSender.send` in this example is a **synchronous** call: once it returns or throws an exception, it does not continue reading the stream in the background under standard usage contracts. Thus, the staging layer can delete the file in `finally`.

**However, never copy this lifecycle as-is into an async flow** if `send` is only scheduled to run later: the file may be deleted before the worker opens it. The asynchronous case is covered in the next section.

Additionally, `Files.deleteIfExists` can fail due to permissions or open file descriptors. Production systems need logs/metrics for cleanup failures and a TTL-based sweeper for orphaned files after crashes.

### 6.4. Do Not Download Temp Files from Arbitrary URLs

If the source is a user-supplied URL, never do this directly:

~~~java
URL url = URI.create(userInput).toURL();
InputStreamSource source = url::openStream;
~~~

This path can lead to **SSRF**, accessing internal IPs, metadata services, localhost resources, or redirects to other hosts. Instead, read only from an authorized storage catalog or via a client enforcing host/scheme allowlists, redirect limits, connect/read timeouts, size limits, and tenant authorization.

With object stores, use tenant-authorized keys/versions and an application-controlled storage client rather than fetching an arbitrary URL from an HTTP request.

## 7. Sending Directly from Object Storage Using a Repeatable Stream

If object storage supports opening a fresh stream to the same data version, you can provide a custom `InputStreamSource` **without writing a temp file**:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.InputStreamSource;

public final class VersionedObjectSource
        implements InputStreamSource {

    private final ObjectStorageClient storage;
    private final String bucket;
    private final String objectKey;
    private final String versionId;

    public VersionedObjectSource(
            ObjectStorageClient storage,
            String bucket,
            String objectKey,
            String versionId) {
        this.storage = storage;
        this.bucket = bucket;
        this.objectKey = objectKey;
        this.versionId = versionId;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        // Each call must return a fresh remote stream
        // from the same immutable object version.
        return storage.openVersion(
                bucket, objectKey, versionId);
    }
}
~~~

`ObjectStorageClient` and `openVersion` are **hypothetical application abstractions**, not built-in Spring or S3 APIs with that exact signature. The approach:

1. Authorize that the tenant/requester has read permission for the object.
2. Obtain a version ID or immutable content reference.
3. Check size metadata, content type, and checksum when available.
4. Return a fresh stream on each `getInputStream` call for that exact version.
5. Enforce request timeouts, retry limits, connection pool limits, and close response streams.
6. Ensure the stream remains accessible until MIME serialization finishes.

Attaching to the message:

~~~java
InputStreamSource content = new VersionedObjectSource(
        storage, bucket, objectKey, versionId);

helper.addAttachment(
        "monthly-report.pdf",
        content,
        "application/pdf");
mailSender.send(message);
~~~

### 7.1. Drawbacks of Direct Remote Streaming

This approach saves temporary disk space, but introduces new problems:

- Jakarta Mail may **read the stream multiple times**; each read may open an HTTP request and download the same object again.
- Remote connection timeouts can interrupt SMTP serialization mid-stream.
- The object might be deleted or credentials expire between reads.
- A download failure mid-`DATA` can leave the SMTP outcome ambiguous.
- Network source and SMTP output couple two services; slowness in one ties up the other's connections longer.
- If the object store client itself buffers the entire response, this strategy still misses the memory goal.

Therefore, for critical transactional emails or large files needing retries, **spooling to a quota-bounded temp file** is often easier to control than direct remote streaming, despite the extra disk I/O.

### 7.2. When Is Remote Streaming Appropriate?

Consider it when:

- File size is known and small-to-moderate relative to mail policy thresholds.
- The object is immutable, versioned, and explicitly authorized.
- The storage client genuinely streams without buffering the whole payload.
- Stream opening latency is stable and low.
- The system bounds concurrency, timeouts, and retries.
- The Jakarta Mail stack in use has been tested with re-readable sources.

Do not choose it merely because an API uses `InputStream`. Measure memory, stream open count, and actual send times under load.

## 8. Attachments Created by PDF/CSV Renderers

Many mail services generate report files **right inside the request**:

~~~java
byte[] pdf = invoiceGenerator.generatePdfBytes(order);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdf),
        "application/pdf");
~~~

If `generatePdfBytes` already allocates a huge array, switching to `InputStreamSource` afterward **cannot reclaim memory from the rendering phase**. You must change the renderer interface to **write to an OutputStream** or file.

### 8.1. Generating Directly to a File

Illustrative abstraction:

~~~java
public interface InvoiceRenderer {
    void writePdf(InvoiceData invoice, OutputStream output)
            throws IOException;
}
~~~

A worker can do:

~~~java
Path staged = Files.createTempFile(
        privateTempDirectory, "invoice-", ".pdf");
try {
    try (OutputStream out = Files.newOutputStream(staged)) {
        renderer.writePdf(invoiceData, out);
    }

    long inputBytes = Files.size(staged);
    if (inputBytes > attachmentPolicy.maxInputBytes()) {
        throw new IOException("Generated invoice exceeds mail limit");
    }

    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(staged),
            "application/pdf");
    mailSender.send(message);
} finally {
    Files.deleteIfExists(staged);
}
~~~

`renderer`, `invoiceData`, `privateTempDirectory`, `attachmentPolicy`, `helper`, and `message` are hypothetical application components. This illustrates a synchronous service snippet, not a standalone program.

Note: because the example checks size **after rendering**, it can still consume too much disk before detecting the limit. If the renderer can output very large data or untrusted input, use a **bounded OutputStream**, per-job disk quotas, and a hard stop during rendering as soon as the limit is exceeded.

### 8.2. Large CSVs: Write Line by Line Instead of Building One Giant String

Avoid:

~~~java
String csv = rows.stream()
        .map(this::toCsvLine)
        .collect(Collectors.joining("\\n"));
byte[] all = csv.getBytes(StandardCharsets.UTF_8);
~~~

With millions of rows, the resulting string and byte array can be huge. Use a `BufferedWriter` writing line by line instead:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        staged, StandardCharsets.UTF_8)) {
    writer.write("orderId,amount,status");
    writer.newLine();

    for (OrderRow row : rows) {
        writer.write(csvEncoder.encode(row));
        writer.newLine();
    }
}
~~~

`csvEncoder` must escape commas, quotes, and newlines per CSV rules; if the file will be opened in spreadsheet software and contains user input, also handle CSV/formula injection per policy. For very large datasets, `rows` should be an iterator/cursor/batch rather than a list holding the entire dataset.

CSVs fit the "incremental generation → temp file → attachment" model well when the renderer supports incremental output.

## 9. File Lifecycle During Asynchronous Mail Sending

In production systems, emails are commonly sent via `@Async`, message brokers, or outbox workers. A frequent bug is creating a temp attachment in an HTTP request, passing the path to a worker, and **deleting the file when the request finishes**.

Example to avoid:

~~~java
public void createAndQueueReport() throws IOException {
    Path temp = generateReportToTempFile();
    try {
        asyncSender.sendLater(temp); // only schedules, has not read file yet
    } finally {
        Files.deleteIfExists(temp); // too early!
    }
}
~~~

If `sendLater` actually runs on another thread, the file may already be gone before the worker builds the MIME content. The bug can appear intermittently depending on scheduler timing, letting integration tests pass while production fails.

### 9.1. Approach 1: Create and Delete the File Within the Same Worker

Preferred when report generation is fast enough and the worker has access to the data:

~~~text
Business transaction
   |
   +--> Store outbox: reportId + recipientId
   |
   v
COMMIT
   |
   v
Async/outbox worker
   |
   +--> Authorize report
   +--> Generate immutable temp file
   +--> Build MIME from FileSystemResource
   +--> JavaMailSender.send
   +--> Record outcome
   +--> Delete temp in finally
~~~

Skeleton example:

~~~java
@Service
public class AsyncReportMailWorker {

    private final ReportStagingService staging;
    private final JavaMailSender mailSender;
    private final DispatchResultService results;

    public AsyncReportMailWorker(
            ReportStagingService staging,
            JavaMailSender mailSender,
            DispatchResultService results) {
        this.staging = staging;
        this.mailSender = mailSender;
        this.results = results;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendReport(ReportJob job) {
        Path temp = null;
        try {
            temp = staging.createImmutableReport(job.reportId());

            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom("reports@example.com");
            helper.setTo(job.recipient());
            helper.setSubject("Report generated");
            helper.setText("See attached report.");
            helper.addAttachment(
                    "report.pdf",
                    new FileSystemResource(temp),
                    "application/pdf");

            mailSender.send(message);
            results.recordSmtpAccepted(job.deliveryId());
            return CompletableFuture.completedFuture(null);
        } catch (Exception ex) {
            results.recordDispatchError(job.deliveryId(), ex);
            return CompletableFuture.failedFuture(ex);
        } finally {
            if (temp != null) {
                staging.deleteOrScheduleCleanup(temp);
            }
        }
    }
}
~~~

`ReportStagingService`, `ReportJob`, and `DispatchResultService` are **application-implemented abstractions**. This snippet illustrates **temp file ownership inside the worker**; for production, separate SMTP failures from database `SENT` update errors, since SMTP may have accepted the message even if recording status failed. Also handle cleanup exceptions separately so they do not mask the original error.

Note: `@Async` works through Spring proxies; self-invocation within the same bean may not run asynchronously. `@Async` and `Future` also **do not automatically make work survive process restarts**. For critical emails, persist a durable outbox/job and have workers recover after crashes.

### 9.2. Approach 2: Pre-Stage in Object Storage and Fetch in the Worker

For reports too CPU-intensive to regenerate on every worker retry:

~~~text
Report service
  |
  +--> Generate report once
  +--> Upload immutable object version
  +--> Save objectKey/versionId in outbox
  |
  v
Mail worker
  |
  +--> Resolve authorized object version
  +--> Stage bounded temp file or repeatable stream
  +--> Send via SMTP
  +--> Record outcome
  +--> Cleanup local temp
~~~

Do not push an open `InputStream` onto a message queue. A stream is a resource bound to a process/connection, not a durable payload that can be serialized and restored. Store an **immutable reference** such as an object key/version ID, plus checksum/size metadata if needed.

### 9.3. When Temp Files Must Survive Across Multiple Retries

An explicit ownership model is required:

| Source | Appropriate Lifecycle |
| --- | --- |
| Pre-existing immutable file on shared storage | Keep until delivery completes/policy TTL |
| Temp file created privately inside worker | Delete in `finally` after attempt |
| Object storage version | Keep until retry deadline/retention expires; reopen per attempt |
| Staging file shared among workers | Requires lease/refcount/ownership; never delete while in use |

Do not rely on `deleteOnExit()` as your main cleanup strategy: it only runs under certain JVM shutdown conditions and does not handle forced crashes, runtime disk quotas, or files living across days.

### 9.4. Crashes and Orphan Cleanup

Because `finally` does not run if a process is killed, temp files can remain on disk. A periodic sweeper can:

1. Scan **only the application's dedicated staging directory**.
2. Inspect only files carrying valid staging identifiers/manifests.
3. Cross-check job/lease status and file age.
4. Avoid deleting files currently processed by workers or needed for retries.
5. Delete expired files and emit cleanup metrics.

Do not deploy a cleanup job using `Files.walk(/tmp)` that deletes indiscriminately, as it can affect other applications' files or files still in use.

## 10. Concurrency and Resource Limits

Streaming reduces heap pressure **per attachment**, but does not eliminate the need to cap how many emails are sent concurrently.

Suppose each email carries a 60 MiB file. If 50 workers stage to disk concurrently:

\[
\mathrm{staging\ disk\ budget} \approx 50 \times 60\ \mathrm{MiB}
= 3000\ \mathrm{MiB}
\]

That excludes metadata, partially written files, retrying jobs, and files awaiting cleanup. If the filesystem only has 1 GiB free, the system will hit `No space left on device` even with plenty of heap.

### 10.1. Limiting Active Sending Workers

Illustrative Spring `ThreadPoolTaskExecutor` configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class MailExecutorConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.initialize();
        return executor;
    }
}
~~~

These are **illustrative** parameters, not defaults suitable for every application. With large attachments, 8 workers can already exceed disk quotas or SMTP concurrency if each worker holds multiple files/connections. Measure:

- P95/p99 durations for file creation, SMTP sending, and cleanup.
- Average/maximum attachment sizes.
- Remaining staging disk space and per-worker quotas.
- Concurrency allowed by the provider.
- Number of open object storage and SMTP connections.
- Error/timeout rates as concurrency increases.

The executor queue must also be bounded. When jobs are already durably persisted in an outbox, there is no need to push millions of tasks into an in-memory executor queue; workers can claim batches according to available capacity.

### 10.2. Backpressure for Large Attachments

One policy:

~~~text
Job due
   |
   v
Attachment limit check
   |
   +--> Too large -> reject / link-based delivery
   |
   v
Acquire staging + SMTP capacity
   |
   +--> No capacity -> leave PENDING/RETRY, schedule later
   |
   v
Stage -> send -> cleanup -> release capacity
~~~

When capacity is unavailable, keep the job in a valid waiting state or return an explicit overload error before accepting the job. **Do not claim batches of jobs and sleep for long periods inside workers**, as that expires leases and increases duplicate risk.

### 10.3. RAM Must Still Be Monitored

Even when the source is a file:

- Jakarta Mail may retain buffers or MIME metadata.
- HTML renderers may create large strings.
- Very large files may be materialized by third-party libraries for checksums, scanning, or encoding.
- TLS/socket buffers and attachment parsing consume memory.
- JVM GC and concurrent workers can create spikes.

Do not conclude from the name `FileSystemResource` that memory will always stay constant. Use profilers/heap metrics and realistic load benchmarks.

## 11. SMTP Timeouts and Size Limits

Even an attachment read via streams must travel over an **SMTP connection subject to timeouts and message size limits**. In Spring Boot with an SMTP transport supporting Jakarta Mail properties, you can configure:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 20000
      "[mail.smtp.writetimeout]": 30000
~~~

Values are in milliseconds and purely illustrative. Configure them based on network, provider, attachment size, and SLA. For implicit TLS, configure `mail.smtp.ssl.enable` for the matching endpoint and port instead of applying STARTTLS mechanically.

### 11.1. The Three Timeouts Are Not Identical

| Property | What Does It Protect? |
| --- | --- |
| `mail.smtp.connectiontimeout` | Waiting to establish the TCP connection |
| `mail.smtp.timeout` | Waiting to read data/responses from the SMTP server |
| `mail.smtp.writetimeout` | Socket write wait time (depends on transport implementation) |

Setting timeouts prevents infinite hangs, but **does not guarantee** every network/remote-source call stops instantaneously or that the worker frees immediately when a Future times out. Some implementations use auxiliary threads to enforce write timeouts; verify behavior and resource cost on the transport you run.

If streams come from an object store over HTTP, **the storage client's timeouts must be configured separately**; SMTP timeouts do not cover fetching attachments from external services.

### 11.2. SMTP SIZE and Provider Limits

SMTP servers may advertise the `SIZE` extension and cap message bodies/overall messages by policy. Providers may also limit:

- Message size after MIME encoding.
- Total recipients or attachments per email.
- Prohibited MIME types/extensions.
- Size of an individual attachment.
- Throughput, hourly/daily quotas, or connection counts.

Applications should validate sizes **before calling send** to avoid wasting time building/sending messages guaranteed to exceed limits, while still handling SMTP rejections.

### 11.3. An Overhead Estimation Function

For a binary file, an approximate formula is:

\[
\mathrm{base64Bytes}(n) = 4 \left\lceil \frac{n}{3} \right\rceil
\]

To estimate a real email, you must also add line breaks, headers, text/HTML content, MIME boundaries, and other attachments. Therefore, **never subtract a fixed constant like 100 bytes from the SMTP limit and assume validity**.

For example, if internal policy sets max message size at 20 MiB, set single-attachment input limits well below 20 MiB, leaving a safe buffer for MIME overhead and other parts. Then verify real messages against a test SMTP sink.

### 11.4. Do Not Retry Infinitely on Server Size Rejections

If the SMTP server returns a terminal error because the message is too large, retrying with the exact same attachment usually accomplishes nothing. Instead:

1. Record a structured error code, such as `SMTP_MESSAGE_TOO_LARGE`.
2. Move the job to `FAILED`/dead-letter or choose an alternative delivery channel per business rules.
3. Notify users or operators without exposing sensitive data.
4. If appropriate, generate an authorized download link instead of an attachment.

A bare `MailSendException` alone is insufficient to distinguish transient vs. permanent; inspect the SMTP response/cause and failure stage.

## 12. When Should You Send a Link Instead of an Attachment?

Streaming reduces application memory, yet the email still carries all encoded data over SMTP. For large reports or highly private data, **sending a document download link** is sometimes better than attaching a file.

| Option | Pros | Cons |
| --- | --- | --- |
| Small attachment | Recipient has a copy right in the email | Increases size, subject to mail server limits |
| File via `FileSystemResource` | Avoids loading full file into heap before send | Still transfers all bytes over SMTP |
| Direct remote repeatable stream | Can avoid temp files | Multiple remote fetches; network coupling |
| Spool temp file then send | Stable, easy to bound and re-read | Consumes disk quota, needs cleanup |
| Download link from storage/portal | Lightweight email, easy access control and updates | Recipient must open link; links may expire |

### 12.1. Access-Controlled Links

An email might contain:

~~~html
<p>Monthly report is ready.</p>
<p>
  <a href="https://portal.example.com/reports/123">
    View and download report
  </a>
</p>
~~~

This is an illustrative URL. For sensitive documents:

- Require user authentication and authorization checks upon download.
- Or use short-lived signed URLs scoped strictly to the exact object/version and purpose.
- Avoid placing sensitive information inside URLs whenever possible.
- Account for URLs appearing in forwarded emails, browser history, proxy/CDN logs, or link previews.
- Set sensible expirations; for reports needing multi-day access, an authenticated portal usually fits better than single-use tokens.
- Ensure links use HTTPS with download/rate limits and auditing as needed.

**Do not automatically switch every attachment to a link** if recipients require offline files, compliance mandates attaching the file, or infrastructure blocks portal access. Choose based on business agreements and recipient capabilities.

### 12.2. Size-Based Selection Rules

An internal policy might look like:

~~~text
File size <= configured small threshold
    -> ByteArrayResource acceptable if data already in memory

File moderate and stored on disk
    -> FileSystemResource or PathResource

File remote, moderate size, requires stable snapshot
    -> Stage bounded temp file and send

File large / uncertain size / near provider limit
    -> Reject attachment or offer authenticated download link
~~~

There is no universal threshold for "small," "moderate," or "large" files across all applications. A system with 2 GiB heap and 50 workers differs from one with 16 GiB heap and 2 workers. Thresholds must be configured and measured.

## 13. Securing Attachments in Streaming Flows

Attachments often carry valuable data: invoices, contracts, customer details, tokens, internal reports. When moving to files/streams, protect **source reading, staging, sending, and cleanup**.

### 13.1. Verify Authorization Before Opening Sources

Suppose a request includes `reportId`. That value alone is **insufficient** to allow reading a file:

~~~text
Authenticated user / tenant
              |
              v
Authorize(reportId, tenantId, action=SEND_REPORT)
              |
              v
Resolve immutable object version / trusted file
              |
              v
Stage + send
~~~

Never concatenate request values directly into paths:

~~~java
// Unsafe if reportId is user-controlled:
Path file = Path.of("/reports/" + reportId + ".pdf");
~~~

This can lead to path traversal/symlink issues or reading another tenant's report if checks are missing. Use an authorized repository lookup to obtain a trusted object reference.

### 13.2. Temp Files Must Live in a Private Area

A staging directory should:

- Not sit inside a static web root or file-server-exposed directory.
- Have permissions/ACLs restricted to the service account.
- Have disk quotas/monitoring and cleanup policies.
- Not be shared uncontrollably with other users' tasks.
- Not expose personal data or secrets in filenames.
- Avoid following arbitrary symlinks; if any flow handles files from untrusted directories, handle race/TOCTOU risks appropriately.

`Files.createTempFile` generates hard-to-collide names and creates fresh files, yet **does not replace directory controls and access permissions**. In multi-tenant environments or with local attackers, consider filesystem sandboxing and dedicated ownership.

### 13.3. Validate File Type and Content

Declaring `Content-Type: application/pdf` in the application does not prove the bytes are actually a PDF. For user-uploaded files or untrusted sources, you may need:

- Business-level MIME/file-type allowlists.
- Magic-byte/actual format verification.
- Malware scanning and quarantine before sending.
- Blocking executables or dangerous attachments per policy.
- Limits on file count and total email size.
- Never decompressing archives without bounds; defend against ZIP bombs.
- Safe attachment names without newlines/control characters.

Do not treat reading via a stream as a content "sanitization" step. Streaming is strictly an I/O and memory management strategy.

### 13.4. Securing the SMTP Channel

Even when temp files are protected on disk, outbound payloads travel over SMTP. For servers requiring authentication:

- Require STARTTLS or use implicit TLS matching the endpoint.
- Enable hostname/certificate verification.
- Never log passwords, access tokens, or attachment contents.
- Enforce timeouts.
- Never send to arbitrary recipients from unauthorized requests.

Production examples must pull credentials from environment variables, secret files, or a secret manager, never hardcoded in source or Docker images.

### 13.5. Never Log Binary Data or Raw MIME

Never do:

~~~java
log.debug("attachment={}", Arrays.toString(bytes));
log.debug("mime={}", mimeMessage.getContent());
~~~

Such logs can exhaust storage, leak data, or trigger unintended reads/serialization. Log safe metadata instead:

~~~text
event=mail.attachment.staged
deliveryId=opaque-uuid
attachmentType=pdf
attachmentBytes=1832401
sourceKind=object-storage
stagingDurationMs=310
~~~

Never use attachment filenames, PII-containing object keys, or delivery IDs as **metric labels**, as they cause high cardinality and data leaks.

## 14. Monitoring Memory, Disk, and Streaming Duration

If you switch from `ByteArrayResource` to `FileSystemResource` and only verify that emails "succeed," you cannot evaluate performance gains. Measure both source and destination stages:

| Metric | Meaning |
| --- | --- |
| `mail_attachment_input_bytes` | Input size of each attachment |
| `mail_attachment_count` | Number of files per message |
| `mail_attachment_staging_duration_seconds` | Time to copy/generate into temp file |
| `mail_attachment_staging_inflight` | Jobs currently occupying staging disk |
| `mail_attachment_staging_disk_bytes` | Staging disk capacity currently used |
| `mail_attachment_rejected_total` | Rejected attachments by reason |
| `mail_attachment_cleanup_failed_total` | Temp file deletion failure count |
| `mail_smtp_send_duration_seconds` | Duration of `JavaMailSender.send` |
| `mail_smtp_failure_total` | Send failures by finite taxonomy |
| `jvm_memory_used_bytes` | Heap/non-heap observed by JVM/Micrometer |
| `jvm_gc_pause_seconds` | Signals of GC pressure |

### 14.1. Metric Cardinality

Labels should belong to finite value sets:

~~~text
attachment_type=pdf|csv|xlsx|other
source_kind=file|object_storage|generated
result=accepted|too_large|io_error|mime_error
~~~

Do not attach `recipient`, `filePath`, `objectKey`, or `deliveryId` to every series. Use access-controlled structured logs/traces to investigate individual deliveries.

### 14.2. Measuring the Full Pipeline

~~~text
T0  authorize file / validate metadata
T1  start generate or fetch
T2  staging finished
T3  create MIME / attach resource
T4  SMTP send begins
T5  SMTP send returns/errors
T6  outbox result committed
T7  temporary file removed
~~~

From these you can measure:

- `T2 - T1`: file generation/fetch time.
- `T5 - T4`: SMTP transport time.
- `T6 - T0`: job processing time until commit.
- `T7 - T2`: staging file lifetime.

Do not lump everything into a single "SMTP duration" number. If object storage downloads slowly, raising SMTP timeouts will not fix the root cause.

### 14.3. Evaluating Heap Under Concurrency

Benchmark example:

~~~text
Case A: readAllBytes + ByteArrayResource
  20 parallel mails, attachment 20 MiB each

Case B: FileSystemResource
  20 parallel mails, attachment 20 MiB each

Observe:
  peak heap used
  GC pause
  per-mail SMTP duration
  throughput
  staging disk usage
  failure/timeout count
~~~

Use the same workload, message body, and SMTP sink for both cases. Do not assert results before measuring, as frameworks and transports may maintain their own buffers. When using temp files, include disk I/O and cleanup costs.

## 15. Testing Streaming Attachments

Three complementary testing levels exist:

1. **Source contract unit tests:** multiple `getInputStream` calls must return readable streams with identical content.
2. **MIME tests:** attachments have the expected filename, content type, and bytes after serialization.
3. **SMTP integration tests:** a mock server receives moderately large messages intact without corruption, never touching production SMTP.

### 15.1. Testing InputStreamSource Repeatability

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.InputStreamSource;

import static org.assertj.core.api.Assertions.assertThat;

class AttachmentSourceTest {

    @Test
    void createsFreshStreamForEachRead() throws Exception {
        byte[] expected = "Test content"
                .getBytes(StandardCharsets.UTF_8);
        AtomicInteger opens = new AtomicInteger();

        InputStreamSource source = () -> {
            opens.incrementAndGet();
            return new ByteArrayInputStream(expected);
        };

        byte[] first;
        byte[] second;
        try (InputStream a = source.getInputStream();
             InputStream b = source.getInputStream()) {
            assertThat(a).isNotSameAs(b);
            first = a.readAllBytes();
            second = b.readAllBytes();
        }

        assertThat(first).isEqualTo(expected);
        assertThat(second).isEqualTo(expected);
        assertThat(opens.get()).isEqualTo(2);
    }
}
~~~

This is a contract test; using a small array in a **test** is appropriate. It does not prove every read from remote object storage returns identical data; for storage, verify version pinning and retries.

### 15.2. Testing Bounded Staging

Scenarios:

| Input | Expected |
| --- | --- |
| Smaller than `maxBytes` | Creates temp file with exact bytes |
| Equal to `maxBytes` | Accepted per policy |
| Larger than `maxBytes` | Throws controlled error, deletes partial temp file |
| `InputStream` throws `IOException` mid-read | Leaves no fake complete file behind |
| Irregular `InputStream` returning many chunks | Total bytes still enforced accurately |
| Storage metadata claims small size, stream is larger | Blocked based on actual bytes read |
| Missing disk write permission | Records staging failure, skips SMTP |
| Delete fails | Metrics/sweeper handle orphaned file |

Never use unbounded streams in tests without timeouts; use bounded synthetic sources for reproducibility.

### 15.3. Testing MIME with Jakarta Mail

A multipart email can be traversed recursively to find a part with a specific filename:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeAttachmentTestSupport {

    public static Part findAttachment(
            Part part, String filename) throws Exception {

        if (filename.equals(part.getFileName())) {
            return part;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                Part result = findAttachment(child, filename);
                if (result != null) {
                    return result;
                }
            }
        }
        return null;
    }
}
~~~

This is a test helper for known, size-bounded messages, not a full untrusted MIME parser. After locating the part, the test can open `getInputStream`, read a small fixture, and compare bytes. Avoid byte-for-byte raw MIME comparisons because boundaries, `Date`, `Message-ID`, and transfer encoding can vary across runs.

### 15.4. SMTP Integration Tests with Mailpit/GreenMail

A test SMTP sink such as Mailpit or GreenMail lets you:

- Send through a real `JavaMailSender`.
- Inspect attachment names and content types.
- Retrieve raw MIME or `MimeMessage` if supported by the tool.
- Verify the message was not truncated and decoded bytes match the fixture.
- Measure send times for fixed-size files.

Example integration scenario:

~~~text
Create 5 MiB fixture with known checksum
  |
  v
Write immutable temp file
  |
  v
Attach via FileSystemResource
  |
  v
Send to local SMTP test server
  |
  v
Read captured message / attachment part
  |
  v
Compare decoded bytes or checksum
  |
  v
Assert temp file cleaned up
~~~

With a 5 MiB file, you do not have to retain both the fixture and the captured attachment in the heap of the same test if measuring memory. You can compare checksums via streams to avoid skewing benchmark results.

An SMTP sink only proves the test server received the message. It does not prove Gmail/Outlook will accept the file, nor does it test spam filters or production SMTP provider size limits.

### 15.5. Testing Async Cleanup

Scenario reproducing a common bug:

~~~text
Request stages file
Request submits async job
Request scope ends
Worker begins later
Expected: file still available or worker restages from stable source
Worker sends
Expected: cleanup after completion
~~~

If the architecture moves ownership into the worker, test that:

- The file is not deleted before the worker reads it.
- The file is deleted after `send` succeeds.
- The file is deleted when `send` throws an exception and the outcome is recorded properly.
- If the process crashes, the sweeper cleans up orphaned files after TTL.
- Two workers do not use and delete a shared file without a lease/refcount.

Do not rely on fixed `Thread.sleep` calls to test async flows; use Awaitility, event latches, or outbox states with timeouts.

## 16. Common Pitfalls When "Streaming" Attachments

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `OutOfMemoryError` when sending large files | `readAllBytes`, `ByteArrayOutputStream`, or renderer buffers everything | Switch to streams/files; measure heap across the whole pipeline |
| Attachment has 0 bytes | Using a single-use stream that was already consumed | Use `FileSystemResource` or an `InputStreamSource` opening fresh streams |
| `Stream closed` during send | Closed `InputStream` before Jakarta Mail read it | Keep source alive until `send` finishes |
| `FileNotFoundException` in async worker | Request deleted temp file before worker started | Stage inside worker or transfer ownership explicitly |
| Sent file differs from expected version | File overwritten between compose and send | Use immutable snapshots/object versions |
| Remote storage called multiple times | Jakarta Mail opens the stream multiple times | Stage a temp file or account for remote re-read cost |
| SMTP sends very slowly despite low heap | Slow disk/network reads, mail provider throttling | Measure each stage, quotas, and send duration |
| SMTP returns size-limit error | MIME/Base64 made message larger than source file | Estimate message size, cap input files, or switch to links |
| Staging disk fills up | Many workers creating temp files or cleanup failing | Disk quotas, concurrency limits, TTL sweeper |
| Retry creates duplicates | SMTP accepted but DB update failed | `UNKNOWN`/reconciliation, idempotency where supported by provider |
| Wrong attachment name or path leak | Passing internal path as display filename | Use safe display names; sanitize filenames |
| File has `.pdf` extension but is invalid | Trusted filename/content-type without inspecting bytes | Validate content, policy, and scan for malware when needed |
| Errors fetching via HTTP from user URL | SSRF, timeouts, or unexpected redirects | Use controlled storage client, allowlists/authorization |
| Incomplete file gets sent | Started sending before generator closed output | Complete staging before adding attachment |
| Cleanup error masks SMTP exception | `finally` throws a second exception | Handle/log cleanup separately and preserve root cause |
| Works locally, fails in production | Different SMTP/TLS/attachment policy limits | Test staging/provider; enforce safe internal limits |

### 16.1. "Attachment Stream Closed" After Using Try-With-Resources

Problem:

~~~java
InputStream stream = storage.open(...);
try (stream) {
    helper.addAttachment(
            "file.pdf",
            new InputStreamResource(stream),
            "application/pdf");
}
mailSender.send(message);
~~~

`addAttachment` **does not mean** the library immediately read and buffered all bytes at call time. After `try`, the stream closes, yet MIME content still needs to be read during `send`.

Fix:

~~~java
FileSystemResource resource =
        new FileSystemResource(stagedFile);
helper.addAttachment("file.pdf", resource, "application/pdf");
mailSender.send(message);
~~~

Or use an `InputStreamSource` capable of opening a **fresh remote stream** on each call, if version/data stability and latency are under control.

### 16.2. Assuming InputStreamResource Automatically Saves Heap

`InputStreamResource` does not mean a factory creating fresh streams. It normally holds an already-opened stream that may only be read once. Switching from `ByteArrayResource` to `InputStreamResource` without understanding the contract can trade an OOM error for a MIME/closed-stream error rather than being a safe optimization.

If you already have a file, use `FileSystemResource`. If you do not yet have a file and data is generated/fetched once, stage into a bounded file and use a re-readable source.

### 16.3. Deleting Files Before SMTP Transport Serializes

The bug can show up in flows like:

~~~text
createMimeMessage
helper.addAttachment(file)
delete(file)
mailSender.send(message)   <-- file missing
~~~

There is no guarantee `addAttachment` eagerly loaded bytes into the MIME part. Keep the source file intact until `mailSender.send` completes. With async flows, pay close attention to thread/process boundaries.

### 16.4. Not Knowing Whether Failure Occurred at the Source or SMTP

For example:

~~~text
Object storage read fails mid-stream
  |
  v
Jakarta Mail MIME serialization fails
  |
  v
MailException or nested IOException
~~~

Do not automatically label every such error as "SMTP server rejected recipient." Record phases such as `ATTACHMENT_FETCH`, `ATTACHMENT_STAGE`, `MIME_BUILD`, `SMTP_SEND`, and `STATE_UPDATE` when identifiable.

If a source error happens after SMTP `DATA` has started transmitting, the relay's outcome can become ambiguous. Retries need duplicate-prevention policies similar to other SMTP network errors.

## 17. Design Pattern for Emails with Large Attachments

Example application sending daily reports to a group of customers:

~~~text
Scheduler
   |
   v
Create report request (not binary payload)
   |
   v
Database transaction
  - save report metadata
  - insert mail outbox PENDING
   |
   v
Outbox dispatcher
   |
   v
Worker claims one delivery
   |
   +--> Resolve authorized immutable report version
   |
   +--> Inspect size/type/recipient policy
   |
   +--> Choose:
   |       A. Small file already in memory
   |          -> ByteArrayResource
   |       B. File on disk
   |          -> FileSystemResource
   |       C. Remote file
   |          -> bounded temp stage or repeatable source
   |       D. Too large
   |          -> secure download link / terminal policy
   |
   +--> Build MIME and validate attachment metadata
   |
   +--> SMTP send with TLS and timeouts
   |
   +--> Persist SENT / RETRY / FAILED / UNKNOWN
   |
   +--> Cleanup temporary resources
   |
   v
Metrics + attempt history + alerts
~~~

### 17.1. Business State and File State

Separate them:

| Delivery Status | File Source Status | Action |
| --- | --- | --- |
| `PENDING` | Report not generated yet | Worker generates when its turn comes |
| `PROCESSING` | Temp file being created | Do not send while data is incomplete |
| `PROCESSING` | Immutable temp ready | Build MIME and send |
| `RETRY` | Temp cleaned up; object version remains | Re-stage temp on next attempt |
| `SENT` | Temp no longer needed | Delete per retention; keep report if business requires |
| `FAILED` | Object/reference retained for investigation | Clean up temp; persist error code and audit |
| `UNKNOWN` | SMTP outcome unclear | Reconcile before resending |

Never store an `InputStream`, file descriptor, or reference to a temp path **existing only inside one container** in the outbox as if a worker after restart could read it. The outbox should store durable object IDs and versions, and workers re-stage on each new attempt.

### 17.2. Storing Checksums and Content Lengths for Reconciliation

If files must not change across retries, store:

~~~text
report_version_id
declared_content_length
sha256_checksum
mime_type
safe_display_filename
~~~

When staging, read the stream and compute the digest buffer by buffer; upon completion, compare the checksum against trusted metadata if available. This detects wrong versions or tampered data. However:

- A SHA-256 checksum does not replace access control or malware scanning.
- Computing a digest costs I/O/CPU and may require one pass over the data.
- For remote sources, metadata must come from a trusted source; never trust a user-supplied checksum as proof of authenticity.
- Never log file contents for reconciliation.

## 18. Frequently Asked Questions

**"Does Spring Framework Mail support streaming attachments?"**  
`MimeMessageHelper` accepts `Resource`/`InputStreamSource`/`DataSource`, allowing content to be supplied via streams rather than requiring a pre-loaded `byte[]`. However, whether the transport buffers or re-reads depends on the Jakarta Mail implementation and SMTP path.

**"Does using FileSystemResource always guarantee O(1) memory?"**  
That cannot be guaranteed for the whole pipeline. It avoids an application-allocated upfront array of all bytes, yet renderers, the MIME layer, transfer encoding, network libraries, and concurrent workers can still use substantial memory.

**"Why can JavaMail call getInputStream multiple times?"**  
To prepare/serialize MIME content and handle encoding, implementations may read content more than once. Therefore, the `InputStreamSource` contract for attachments requires returning a fresh stream each time rather than reusing a consumed stream.

**"Can InputStreamResource be used for large attachments?"**  
Usually not when it wraps a read-once stream. `FileSystemResource` or a custom repeatable `InputStreamSource` is better suited. If the source can only be read once, spool it once into a temporary file.

**"Is ByteArrayResource always wrong?"**  
No. For small files or data already existing as `byte[]`, it is simple and re-readable. The issue is memory consumption when files are large or concurrency is high.

**"If an object lives on S3, can I open a stream directly?"**  
Yes, if the storage client opens a fresh stream each time, the file is pinned to a stable version, access permissions are valid, and latency/timeouts are bounded. Test carefully because Jakarta Mail may open it multiple times and trigger multiple downloads.

**"Why spool to a temp file if I already have an InputStream?"**  
Because many HTTP/DB streams are read-once and may vanish or expire before SMTP needs to re-read them. A temp file provides a stable, repeatable snapshot at the cost of disk I/O.

**"Should I use try-with-resources for streams?"**  
Yes for streams the application opens and processes directly, such as when copying to a temp file. Do not close a stream intended for later use before `send` runs. With `FileSystemResource`, streams are normally opened when the library needs to read.

**"Can a temp file be deleted right after helper.addAttachment?"**  
No. `addAttachment` attaches the content source; it does not guarantee MIME has already been serialized. Keep the file until `JavaMailSender.send` finishes; for async flows, the file must live until the worker completes.

**"Why use @Async if sending attachments is still slow?"**  
`@Async` moves work off the caller thread so requests do not wait on SMTP, but it does not speed up file creation or network transfer, nor does it make jobs durable. You need a bounded executor or outbox/queue to manage capacity and retries.

**"SMTP limits messages to 25 MB—can I send a 25 MB file?"**  
Usually unsafe to assume. MIME/Base64 expands the message beyond the source file, plus headers, HTML, and other attachments. Set a lower input limit and measure/test against the provider.

**"Can I send a 500 MB attachment using streaming?"**  
Streaming reduces heap usage, yet does not remove email limits. A 500 MB file far exceeds typical email provider policies and is unsuitable as an email attachment. Consider authorized download links instead.

**"Is sending a download link always safer than an attachment?"**  
Not automatically. Links can be forwarded, leaked in logs, or expire. Sensitive data requires portal auth or tightly scoped/timed signed URLs plus auditing.

**"If the application sends 20 emails with the same file, must it create 20 copies?"**  
Not necessarily. A shared immutable source file can be used with each send opening its own stream. However, manage ownership, concurrent reads, and do not delete the file while another worker uses it. For per-recipient personal data, avoid accidental cross-sharing.

**"If reading a remote stream fails, does that mean SMTP definitely did not receive the email?"**  
Not always. If the failure occurs while MIME is already streaming into SMTP and the client misses the final response, the outcome may be ambiguous. Record the stage/outcome and use retry policies accounting for possible duplicates.

**"Should attachments be stored in a database BLOB and streamed out?"**  
It depends on architecture. Database BLOBs can work, yet add storage pressure and DB I/O. If the ORM loads the entire BLOB into the heap, wrapping it in an `InputStreamSource` afterward still fails to save memory. True streaming APIs and repeatable/snapshot contracts are required.

**"How can I verify streaming actually saved memory?"**  
Using the same workload and file sizes, compare peak heap/GC, send duration, disk I/O, and throughput between `readAllBytes` and `FileSystemResource`. One small test message succeeding does not prove optimization under high concurrency.

**"Should InputStreamSource open a user-provided URL directly?"**  
Never directly. Arbitrary URLs risk SSRF or redirects to internal infrastructure. Use authorized file sources and a client enforcing host, protocol, redirect, timeout, and size limits.

**"Is DeleteOnExit enough to clean up all temp files?"**  
No. Files can linger long before the JVM stops, and forced crashes bypass shutdown hooks. Use `finally`, quotas, and a TTL/ownership-based sweeper.

**"Should I call CompletableFuture.get immediately after submitting mail?"**  
Only if the caller truly must wait. Calling `get` immediately inside an HTTP request defeats async benefits. For important deliveries, return a job ID and track durable state in an outbox.

**"Does a mock mail server prove the file will reach Gmail/Outlook?"**  
No. It only verifies SMTP submission and MIME content in a test environment. Real providers add size limits, content filtering, malware checks, and deliverability policies.

## 19. Streaming Attachment Implementation Checklist

### Choosing the Data Source

1. Identify average and maximum attachment sizes plus concurrent email count.
2. When files already exist on disk, prefer `FileSystemResource` or `PathResource` over `Files.readAllBytes` for large files.
3. For small data already in `byte[]`, `ByteArrayResource` can still fit well.
4. Never use single-use `InputStreamResource` for attachments that may be read multiple times.
5. For custom `InputStreamSource`s, return a fresh stream on **every call**.
6. Ensure reads for the same delivery see identical content/an immutable version.
7. If a source can only be read once, stage it to a byte-bounded temp file before sending.

### Resource Limits

8. Enforce max attachment bytes and max message size policies accounting for MIME/Base64 overhead.
9. Enforce size by actual bytes read, not solely by trusting `Content-Length`.
10. Enforce staging directory quotas and concurrent worker limits.
11. Configure timeouts for both SMTP **and** remote storage clients.
12. If files approach/exceed provider limits, consider authorized download links.
13. Never build an entire report in a `ByteArrayOutputStream` and then claim to "stream" it if the goal is reducing heap.

### Lifecycle and Reliability

14. Attach files only after output generation has finished and closed.
15. Keep source files intact and unmodified until `JavaMailSender.send` finishes.
16. With `@Async`, create and clean up temp files inside the worker or transfer ownership cleanly.
17. Never persist open streams or container-local temp paths as durable job payloads.
18. Provide `finally` cleanup plus a sweeper for files orphaned after crashes.
19. Use an outbox/state store when durable retries are needed, and separate SMTP acceptance from DB state commits.
20. Accept that plain SMTP does not guarantee exactly-once delivery; handle ambiguous outcomes.

### Security

21. Verify tenant and report read permissions before opening files/objects.
22. Never stream from arbitrary user-supplied URLs or filesystem paths.
23. Use a private staging directory with appropriate ACLs/permissions.
24. Validate file types, filenames, sizes, and scan for malware per policy.
25. Send over SMTP with proper TLS; never log credentials, file bytes, or raw MIME.
26. Control retention and access permissions on object storage/temp files.

### Testing and Observability

27. Test that repeated `getInputStream` calls return fresh streams with identical bytes.
28. Test staging size-limit breaches, mid-stream errors, and cleanup.
29. Test MIME filenames, content types, attachment bytes, and Unicode handling.
30. Test with an SMTP sink or container, never production SMTP.
31. Test async file lifetimes and worker retries after restarts.
32. Measure peak heap, GC pauses, SMTP duration, staging disk usage, and throughput.
33. Configure metrics/alerts when staging fills up, cleanup fails, or SMTP size limits reject messages.

## 20. Decision Flowchart

~~~text
Need to send an attachment via Spring Mail?
                 |
                 v
       Is an attachment truly needed?
         |                 |
        Yes                No
         |                 |
         v                 v
    Check size        Send link to authorized
    and policy           portal/storage
         |
         v
   File too large / exceeds message limit?
         |                 |
        Yes                No
         |                 |
         v                 v
    Use link or       File already on disk?
    fail clearly          |             |
                         Yes            No
                          |             |
                          v             v
                  FileSystemResource  Can source open
                          |           fresh streams?
                          |             |         |
                          |            Yes        No
                          |             |         |
                          |             v         v
                          |         Versioned   Stage bounded
                          |         stream      temp file
                          |             |         |
                          +-------------+---------+
                                        |
                                        v
                           Limit concurrent sending
                                        |
                                        v
                            Build MIME + addAttachment
                                        |
                                        v
                               JavaMailSender.send
                                        |
                          +-------------+-------------+
                          |                           |
                          v                           v
                       Success                    Exception
                          |                           |
                          v                           v
                  SMTP_ACCEPTED               Classify outcome
                          |                           |
                          +-------------+-------------+
                                        |
                                        v
                            Record state and cleanup
~~~

The diagram above illustrates a decision workflow **before** sending. When the source is object storage, direct streaming should be chosen only if versioning/read-repeatability, network timeouts, and reliability are verified; otherwise, staging to a temp file has fewer moving parts.

## 21. Practical Summary

When optimizing attachments for Spring Framework Mail, three rules deliver the most value:

**1. Avoid allocating a large byte array unnecessarily.** For existing files, `FileSystemResource` is usually better than `Files.readAllBytes` plus `ByteArrayResource`.

**2. Sources must be re-readable and survive until send finishes.** `InputStreamSource` must open a fresh stream per read; never attach a single-use `InputStreamResource` and close it before sending. For read-once sources, spool to a controlled temp file.

**3. Streaming does not bypass SMTP limits.** Files are still encoded into MIME, uploaded over the network, and subject to provider quotas and timeouts. If a file is too large, sending a secure download link usually makes more sense than raising memory/timeouts further.

### Short Cheat-Sheet Example

~~~java
// Instead of:
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(Files.readAllBytes(reportPath)),
        "application/pdf");

// For large existing files, prefer:
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf");

// Keep reportPath stable until after:
mailSender.send(message);
~~~

**Conclusion:** "Streaming attachments when possible" does not mean swapping one `Resource` type in a single line of Java and assuming performance is solved. A durable design must address **file sources, multi-read stream capability, immutable snapshots, worker lifecycles, heap/disk/concurrency limits, MIME/Base64 overhead, SMTP timeouts, and data security**. By choosing appropriately among file resources, bounded staging, repeatable remote streams, or download links, a Spring Framework Mail application can handle large attachments reliably without sacrificing correctness or operability.

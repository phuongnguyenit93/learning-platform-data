# Closing an `InputStream` Before the Sender Finishes Reading It

In **Spring Framework Mail**, an easy-to-miss mistake is **closing the `InputStream` holding an attachment or inline image right after building the `MimeMessage`, before `JavaMailSender` actually reads the bytes**. The application can construct the message without errors, only for `IOException`, `MessagingException`, `MailSendException`, or an empty, missing, or unreadable attachment to show up at send time. This bug commonly appears when scoping `try-with-resources` too tightly, passing `InputStreamResource` to `MimeMessageHelper`, handing sending off to `@Async`, or building a message from a temp file and deleting the file before transport consumes it.

Key point to remember: **building the MIME structure does not necessarily mean every MIME part's bytes have been read**. Jakarta Mail may read the payload when the message is serialized, encoded, or submitted to the SMTP transport. Some data sources can be asked for a stream **multiple times**. Therefore, seeing `helper.addAttachment(...)` return without error does not prove the attachment is still readable at send time.

This lesson analyzes the root cause, stream ownership models, which `Resource` types to use and avoid, effects of `@Async` and retries, choosing `ByteArrayResource` or `FileSystemResource`, building sources that open a fresh stream each time, complete Java/Spring examples, testing strategies, and a production troubleshooting checklist.

## 1. Typical Failure: `addAttachment` Succeeds, `send` Fails

Suppose a user uploads a PDF for the application to email. The developer opens a stream, hands it to the helper, and closes it right after configuring the message:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public void prepareAttachment(
        MimeMessageHelper helper,
        Path pdfPath
) throws Exception {

    try (InputStream input =
                 Files.newInputStream(pdfPath)) {

        // WRONG: InputStreamResource holds an already-open stream.
        helper.addAttachment(
                "invoice.pdf",
                new InputStreamResource(input),
                "application/pdf"
        );
    } // input is already closed here.

    // SMTP has not necessarily read the attachment yet.
}
```

Then:

```java
mailSender.send(mimeMessage);
```

When transport tries to read the attachment, the source is no longer valid. Depending on how MIME is built and when reading occurs, failures may include:

- `java.io.IOException: Stream closed`.
- `jakarta.mail.MessagingException` caused by a stream read error.
- `org.springframework.mail.MailSendException` wrapping the Jakarta Mail cause.
- Attachment read errors surfacing inside a background task rather than on the HTTP request.
- A message sent with an incorrect or missing attachment if custom error handling mishandles the failure or substitutes empty bytes.

Do not key off a single exact exception message: wording varies across JDKs, Jakarta Mail providers, storage backends, and execution phases.

**The root bug is a resource lifecycle error**, not a missing `flush()` or needing `Thread.sleep(...)`.

## 2. Real Timeline of a MIME Email

A typical lifecycle:

```text
T1: Open InputStream for attachment
            |
            v
T2: Create MimeMessage
            |
            v
T3: MimeMessageHelper.addAttachment(...)
            |
            v
T4: Close InputStream  <--- fails if stream still needs to be read
            |
            v
T5: mailSender.send(message)
            |
            v
T6: Jakarta Mail serializes MIME parts
            |
            v
T7: DataHandler / DataSource requests attachment bytes
            |
            v
T8: SMTP transport writes encoded content
```

For some sources, content may be read at a point other than T7, or even read more than once to compute headers/transfer encodings or re-serialize. Do not treat the diagram above as a strict mandatory order across every JavaMail implementation. What matters is that **a gap can exist between attaching the data source and consuming its bytes**.

If the stream closed or the temp file was deleted during that gap, the message can no longer be read reliably.

### Two Conditions That Must Hold

For attachments to work reliably:

1. **Data must remain present and accessible** until the send process needing it finishes.
2. **The MIME source must allow opening a fresh stream when the library asks**, unless a specific API has a verified different contract.

Merely keeping a stream open longer partially satisfies the first condition; it **does not solve the case where the same stream already reached EOF or is read a second time**.

## 3. What Is `InputStreamSource` For?

In Spring Core, `InputStreamSource` describes an object capable of supplying an `InputStream`:

```java
import java.io.IOException;
import java.io.InputStream;

public interface InputStreamSource {
    InputStream getInputStream() throws IOException;
}
```

The idea is not “hand the library an already-open stream”, but **hand it a factory that can supply a stream** when needed.

With `MimeMessageHelper.addAttachment(...)` and `addInline(...)`, Jakarta Mail may retrieve the source multiple times. A proper implementation must return **a fresh stream readable from byte zero** on every `getInputStream()` call.

```text
InputStreamSource.getInputStream() -> stream A, position 0
InputStreamSource.getInputStream() -> stream B, position 0
InputStreamSource.getInputStream() -> stream C, position 0
```

Never return the same `InputStream` instance sitting at EOF or already closed.

### Why Does the Helper Not Read All Bytes Immediately?

Reading every attachment inside `addAttachment` consumes memory and time upfront; for large files or storage-backed sources, deferred reading makes sense. Jakarta Mail models MIME via `DataHandler`/`DataSource`; payload bytes are pulled during serialization or transport.

That is why a helper call “not throwing an exception” does not guarantee the attachment is valid.

## 4. `InputStream` and `InputStreamSource` Are Different

| Type | Meaning | Risk When Used for MIME |
|---|---|---|
| `InputStream` | A single open read session with a cursor | Can be closed or exhausted to EOF |
| `InputStreamSource` | A provider of read sessions | Must be implemented to return fresh streams on demand |
| `InputStreamResource` | Wraps an already-open `InputStream` | Usually single-use; unsuitable for multi-read attachments |
| `ByteArrayResource` | Wraps in-memory bytes; fresh stream per read | Reliable for small/medium payloads, raises heap usage |
| `FileSystemResource` | Wraps a file path to open fresh streams as needed | File must stay present and unchanged while sending |
| Jakarta Activation `DataSource` | Supplies MIME data, content type/name | `getInputStream()` must also follow a proper lifecycle |

A common mistake is reasoning:

> “`InputStreamResource` implements `InputStreamSource`, so it works anywhere an `InputStreamSource` is expected.”

In Java type terms, it compiles. Yet **MIME usage requires a repeatable source**, whereas `InputStreamResource` represents an already-opened single-use stream. Implementing the interface does not satisfy the lifecycle contract.

## 5. Complete Example of the Wrong Approach

```java
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class BrokenAttachmentMailer {

    private final JavaMailSender mailSender;

    public BrokenAttachmentMailer(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            Path invoicePath
    ) throws Exception {

        MimeMessage message =
                mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        message,
                        true,
                        "UTF-8"
                );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Invoice");
        helper.setText("Invoice is attached.");

        try (InputStream input =
                     Files.newInputStream(invoicePath)) {

            helper.addAttachment(
                    "invoice.pdf",
                    new InputStreamResource(input),
                    "application/pdf"
            );
        }

        // Stream is already closed. Jakarta Mail may read later.
        mailSender.send(message);
    }
}
```

The bug is not only `try-with-resources`. Even moving `mailSender.send(message)` inside the `try` block still leaves `InputStreamResource` unable to satisfy multiple reads.

Adding `input.mark(0)` or `input.reset()` is not a general fix either: not all streams support mark/reset, payloads may be too large, and one shared stream is not equivalent to independent read sessions.

## 6. Fix 1: `ByteArrayResource` for Small, Bounded Attachments

For small, strictly bounded attachments, read the bytes into memory **before closing the stream**, then wrap them in `ByteArrayResource`:

```java
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendSmallInvoice(
        JavaMailSender sender,
        Path invoicePath,
        String recipient
) throws Exception {

    // Use only after enforcing file size bounds.
    byte[] attachment = Files.readAllBytes(invoicePath);

    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(
                    message,
                    true,
                    "UTF-8"
            );

    helper.setFrom("billing@example.org");
    helper.setTo(recipient);
    helper.setSubject("Invoice");
    helper.setText("See the attached file.");

    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(attachment),
            "application/pdf"
    );

    sender.send(message);
}
```

Why does this work?

- `ByteArrayResource` holds a byte array independent of the closed stream.
- Every time the library calls `getInputStream()`, the resource creates a new `ByteArrayInputStream` starting at index zero.
- There is no dependency on the closed file handle from `try`.
- Attachment contents stay stable throughout sending, provided the app does not mutate the backing byte array.

### Important Limit: Memory

`Files.readAllBytes(...)` is unsuitable by default for large or untrusted files. For example, 50 concurrent jobs each holding a 20 MB attachment consume around 1 GB of raw attachment bytes alone before MIME encoding and other objects.

Use this approach only when:

- A strict **maximum attachment size** is enforced.
- Inputs were validated/scanned per policy.
- Heap and concurrency headroom are sufficient.
- Hundreds of raw attachment buffers are not queued in RAM.

For large files, use a source that **opens fresh streams from storage on demand** instead of holding everything on the heap.

## 7. Bounded Reads Instead of `readAllBytes` for Untrusted Data

When uploaded file sizes are untrusted, checking size metadata alone is not enough. Files can change or streams can yield more bytes than declared.

Bounded reader example:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

public final class LimitedBytes {

    public static byte[] readAtMost(
            InputStream input,
            long maxBytes
    ) throws IOException {

        if (maxBytes < 0L) {
            throw new IllegalArgumentException(
                    "maxBytes must be nonnegative"
            );
        }

        ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        byte[] buffer = new byte[8192];
        long total = 0L;
        int read;

        while ((read = input.read(buffer)) != -1) {
            total += read;

            if (total > maxBytes) {
                throw new IOException(
                        "Attachment exceeds allowed size"
                );
            }

            output.write(buffer, 0, read);
        }

        return output.toByteArray();
    }
}
```

Usage:

```java
byte[] bytes;

try (InputStream input = storage.openInput(ref)) {
    bytes = LimitedBytes.readAtMost(
            input,
            2L * 1024 * 1024
    );
}

// InputStream is closed, yet bytes remain intact.
ByteArrayResource resource =
        new ByteArrayResource(bytes);

helper.addAttachment(
        "report.pdf",
        resource,
        "application/pdf"
);

sender.send(message);
```

`storage.openInput` is an application-defined abstraction. Production code must separately handle empty streams, timeouts, malicious uploads, and post-encoding MIME sizes.

`readAtMost` reduces unbounded-read risk; it **does not** by itself verify malware scans, authorization, or SMTP size limits after Base64 encoding.

## 8. Fix 2: `FileSystemResource` for Files with Stable Lifecycles

If the attachment already sits on disk at a stable path, use `FileSystemResource`:

```java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;

Path reportPath =
        Path.of("/app/mail-attachments/report-2026.pdf");

FileSystemResource resource =
        new FileSystemResource(reportPath);

helper.addAttachment(
        "report.pdf",
        resource,
        "application/pdf"
);

mailSender.send(message);
```

`FileSystemResource` opens a fresh stream each time one is requested. There is no need to manually open and hold an `InputStream` when adding the attachment.

However, the file must remain intact **until Jakarta Mail finishes reading it**. Do not delete, rename, or overwrite the file prematurely.

### When Is This Safe?

- The file was written completely before sending.
- The worker has permission to read the file.
- The file is not cleaned up before `send` completes.
- No other producer overwrites the same path.
- If sending asynchronously, the file exists on the executing worker, not just the HTTP server.
- Across retries, the attachment version stays accessible per retention policy.

A local path inside Pod A **does not automatically exist inside Pod B**. With queues or multiple replicas, use object storage or properly configured shared storage; never push temporary local paths onto a broker expecting another worker to open them.

## 9. Mistakes with Temporary Files and Premature Cleanup

Example:

```java
Path temporaryPdf =
        Files.createTempFile("invoice-", ".pdf");

try {
    generatePdf(temporaryPdf);

    MimeMessage message =
            buildMessageWithFile(temporaryPdf);

    // Async send: merely submits a task to the executor.
    mailExecutor.execute(
            () -> mailSender.send(message)
    );
} finally {
    Files.deleteIfExists(temporaryPdf);
}
```

This creates a race:

```text
HTTP thread                        Mail worker
    |                                  |
    +-- create temp file               |
    +-- schedule send ---------------->|
    +-- delete temp file               |
    |                             starts later
    |                             opens attachment
    |                                  X file missing
```

Even when an OS permits unlinking an open file, behavior differs across platforms and open timing. Never rely on Windows/Linux file-locking quirks for correctness.

### How to Fix

- Move attachments to **durable storage** before enqueueing.
- Queue only `attachmentId`, `storageKey`, and `version`.
- Have the worker open the source when actually sending.
- Base cleanup on retention and job state, not on when the HTTP method returns.
- For temp files genuinely used for a single synchronous send, clean up only after `send` returns and no further reads remain.

## 10. Fix 3: `InputStreamSource` Returning a Fresh Stream Each Time

When data resides in storage or must stream from a path, use a factory:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamSource;

Path path = Path.of("/data/reports/statement.pdf");

InputStreamSource source = new InputStreamSource() {
    @Override
    public InputStream getInputStream()
            throws IOException {
        return Files.newInputStream(path);
    }
};

helper.addAttachment(
        "statement.pdf",
        source,
        "application/pdf"
);

mailSender.send(message);
```

Key point: every call to `getInputStream()` creates **a brand-new stream** via `Files.newInputStream(path)`.

It can be written concisely with a lambda:

```java
InputStreamSource source =
        () -> Files.newInputStream(path);

helper.addAttachment(
        "statement.pdf",
        source,
        "application/pdf"
);
```

This does not mean leaving file handles open forever. The MIME provider opens a stream **when needed**, and the reading implementation closes it per its contract. Your code should not prematurely close a stream before the consumer finishes.

### Factories Must Still Guarantee Stable Data

If each open of a path reads a newer version, MIME can become inconsistent across reads. For retries or multi-worker setups, prefer **immutable/versioned objects** over mutable paths.

## 11. A Factory for Object Storage

When attachments live in S3-compatible storage, blob stores, database LOBs, or another store abstraction, build a repeatable stream source:

```java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.InputStreamSource;

public final class StoredAttachmentSource
        implements InputStreamSource {

    private final AttachmentStore store;
    private final String objectKey;
    private final String version;

    public StoredAttachmentSource(
            AttachmentStore store,
            String objectKey,
            String version
    ) {
        this.store = store;
        this.objectKey = objectKey;
        this.version = version;
    }

    @Override
    public InputStream getInputStream()
            throws IOException {

        return store.openReadStream(
                objectKey,
                version
        );
    }
}

public interface AttachmentStore {

    InputStream openReadStream(
            String objectKey,
            String version
    ) throws IOException;
}
```

`AttachmentStore` is an application-defined interface. If an object storage SDK throws custom exceptions, adapt them to `IOException` per policy or build a matching custom `DataSource`.

Example:

```java
InputStreamSource source =
        new StoredAttachmentSource(
                attachmentStore,
                attachment.objectKey(),
                attachment.version()
        );

helper.addAttachment(
        attachment.safeFilename(),
        source,
        attachment.contentType()
);

mailSender.send(message);
```

### Storage Contract Requirements

- Every `openReadStream` returns a fresh stream from byte zero.
- Object version does not change mid-send.
- Workers are authorized to read the object.
- Access tokens do not expire before the worker runs.
- Read timeouts, size limits, and cleanup are enforced.
- Client-supplied object keys cannot cross tenant boundaries.
- Mid-stream read errors propagate rather than silently returning EOF.

A source that opens fresh streams yet **lacks stable data** still risks corruption if Jakarta Mail re-reads it.

## 12. `InputStreamResource` Is a Common Trap

Spring's `InputStreamResource` wraps **an already-opened stream**:

```java
InputStream input = Files.newInputStream(path);

InputStreamResource resource =
        new InputStreamResource(input);
```

It is meant for APIs consuming a **single-use stream** in one explicit pass. MIME attachments/inline assets require a source that can be retrieved multiple times.

Therefore:

| Usage | Assessment |
|---|---|
| `new InputStreamResource(input)` then `addAttachment` | Avoid |
| `new ByteArrayResource(bytes)` then `addAttachment` | Usually suitable for small/bounded bytes |
| `new FileSystemResource(path)` then `addAttachment` | Suitable if file exists and stays immutable long enough |
| `InputStreamSource` opening fresh stream each call | Suitable when storage supports it |
| `InputStreamSource` returning the same `InputStream` every call | Unsuitable |
| Custom repeatable `DataSource` | Suitable when fine-grained MIME/content-type control is needed |

If you hit `Stream closed` and spot `InputStreamResource` on the attachment path, check that first.

## 13. Do Not Merely Move `try-with-resources` Below `send`

A commonly suggested tweak:

```java
try (InputStream input = Files.newInputStream(path)) {
    helper.addAttachment(
            "report.pdf",
            new InputStreamResource(input),
            "application/pdf"
    );

    mailSender.send(message);
}
```

Compared to closing before `send`, this prevents premature closure in one simple scenario. Yet it **still fails the contract of supplying a fresh stream when Jakarta Mail reads multiple times**.

If the stream is read to the end on the first pass, the second pass hits EOF even though the stream is still open.

**The true fix is supplying a repeatable source**, not merely stretching a `try` block.

## 14. When Is `try-with-resources` Actually Right?

`try-with-resources` is completely right when your code **reads the entire payload into an independent representation** before closing the stream:

```java
byte[] bytes;

try (InputStream input = storage.openReadStream(ref)) {
    bytes = LimitedBytes.readAtMost(input, maxBytes);
}

// From here on, there is zero dependency on input.
InputStreamSource repeatable =
        new ByteArrayResource(bytes);
```

Or when your code runs an operation that **synchronously finishes consuming the stream inside the scope**, per the receiving API's explicit contract. Never apply that assumption mechanically to Jakarta Mail MIME sources.

### Who Closes the Stream?

When an API takes an `InputStreamSource`/`DataSource`, the consumer calls `getInputStream()` and is generally responsible for closing the streams it opens per its read path. The provider supplying the source must ensure each fresh stream has a valid lifecycle and never close it before the consumer finishes.

When writing custom `DataSource`s, wrappers, or low-level MIME code, verify and test exact ownership rather than assuming every framework closes every stream in every path.

## 15. `addInline` Suffers the Exact Same Bug

Not only attachments. Inline images using `Content-ID` can also be read lazily:

```html
<html>
  <body>
    <p>Hello!</p>
    <img src="cid:brand-logo" alt="Logo"/>
  </body>
</html>
```

Code should use a repeatable source:

```java
MimeMessage message =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Notification");

helper.setText(
        "Hello!",
        "<p>Hello!</p>"
      + "<img src=\"cid:brand-logo\" alt=\"Logo\"/>"
);

helper.addInline(
        "brand-logo",
        new FileSystemResource(
                Path.of("/app/assets/logo.png")
        ),
        "image/png"
);

mailSender.send(message);
```

Calling `setText(...)` before `addInline(...)` is the recommended safe order when constructing related MIME trees with `MimeMessageHelper`. The logo file must stay present until sending finishes, and with distributed workers it must be accessible to whichever worker runs.

If an inline image is read from a closed stream, the same failure occurs, manifesting in clients as missing images or failed MIME serialization.

## 16. Attachment Streams in `@Async`: Even Higher Risk

A dangerous pattern:

```java
public void handleUpload(MultipartFile upload) {
    try (InputStream input = upload.getInputStream()) {

        mailAsyncService.sendLater(
                new InputStreamResource(input)
        );

    } catch (IOException ex) {
        throw new IllegalStateException(ex);
    }
}
```

If `sendLater` uses `@Async`:

```java
@Async("mailExecutor")
public void sendLater(
        InputStreamSource attachment
) {
    MimeMessage message =
            buildMessage(attachment);

    mailSender.send(message);
}
```

The caller closes the stream when the scope exits while the async task may not even have started. This is a **resource lifetime outliving request lifetime** bug.

Another variant: a `MultipartFile`/`Part` backed by an HTTP request temp file. Once the request ends, the servlet container cleans up temp files, leaving the delayed worker with nothing.

### Clear Rule

**Never pass `InputStream`, `InputStreamResource`, servlet `Part`, or request-scoped upload resources across async/queue boundaries.**

Instead:

1. Accept the upload.
2. Validate permissions, size, and content policy.
3. Persist data to storage with proper retention.
4. Commit the attachment reference/notification job.
5. Pass the **ID/reference** to the worker.
6. Have the worker open the data source from storage at execution time.

## 17. Safer Producer–Worker Design

A lightweight command:

```java
public record MailJob(
        String notificationId,
        String recipientRef,
        String templateKey,
        String attachmentId,
        String attachmentVersion
) {
}
```

In the request handler:

```java
public MailReceipt requestMail(
        MultipartFile upload,
        MailRequest request
) throws IOException {

    StoredAttachment stored =
            attachmentStorage.saveValidated(
                    upload,
                    request.tenantRef()
            );

    MailJob job = new MailJob(
            ids.newNotificationId(),
            request.recipientRef(),
            "invoice-ready",
            stored.id(),
            stored.version()
    );

    outboxRepository.insertPending(job);

    return new MailReceipt(
            job.notificationId(),
            "QUEUED"
    );
}
```

`MailReceipt`, `MailRequest`, `StoredAttachment`, `attachmentStorage`, and `outboxRepository` are illustrative components. In production, define commit and transaction boundaries between object storage and database, handle orphaned objects or missing-file jobs, and return `QUEUED` only once durability guarantees hold.

Worker:

```java
public void processJob(String notificationId) {

    MailJob job = outboxRepository.claim(notificationId);

    StoredAttachment attachment =
            attachmentStorage.findAuthorized(
                    job.attachmentId(),
                    job.attachmentVersion()
            );

    MimeMessage message = mailSender.createMimeMessage();

    // Build helper, subject, body, recipient...

    InputStreamSource source = () ->
            attachmentStorage.openReadStream(
                    attachment.id(),
                    attachment.version()
            );

    helper.addAttachment(
            attachment.safeFilename(),
            source,
            attachment.contentType()
    );

    mailSender.send(message);
}
```

This is architectural Java pseudocode: `helper` and injected services must be wired cleanly in real code, alongside exception handling and attempt-outcome finalization. The main point is **the worker builds MIME from a source valid at send time**, never receiving an open stream from the HTTP thread.

## 18. Passing Resources Over a Queue Is Wrong Both Technically and Data-Wise

An `InputStream` is not a durable queue payload:

- You cannot serialize an open read session into a meaningful queue record.
- It may depend on a single process's file descriptor.
- It may depend on an expiring token.
- It may only be readable once.
- After a restart, workers cannot resume the read cursor.
- Across replicas, other workers do not own the socket/file handle.
- There is no version check if the attachment mutates.

A durable queue record should contain:

```json
{
  "notificationId": "notif-421",
  "attachmentRef": "attachment-918",
  "attachmentVersion": "v3",
  "recipientRef": "recipient-31",
  "templateKey": "invoice-ready"
}
```

Never embed raw attachment bytes unless there is a clear design reason, strict size bounds, and broker support. Avoid putting short-lived presigned URLs into long-lived queues; store object key/version and obtain fresh credentials when the worker runs.

## 19. Multiple Reads Are a Real MIME Requirement

An improperly implemented source:

```java
InputStream opened = Files.newInputStream(path);

InputStreamSource broken = () -> opened;
```

Every `getInputStream()` call returns the exact same object.

What happens:

```text
First getInputStream():
  reads bytes 0..N, reaches EOF

Second getInputStream():
  same stream already at EOF
  returns no bytes, or throws if closed
```

Proper source:

```java
InputStreamSource repeatable =
        () -> Files.newInputStream(path);
```

Each call returns a separate stream:

```text
read #1 -> new stream, bytes 0..N
read #2 -> new stream, bytes 0..N
read #3 -> new stream, bytes 0..N
```

**The goal is repeatable data**, not assuming the library always calls `getInputStream()` exactly twice. Read counts vary by library version, MIME tree, and serialization steps.

## 20. `ByteArrayDataSource` and Custom `DataSource`

Besides `InputStreamSource`, Jakarta Mail/Activation has `DataSource` for supplying MIME content. Implementations handle name, content type, and input streams.

For example, `ByteArrayDataSource` (from the Jakarta Mail implementation) fits when data is already in memory:

```java
import jakarta.mail.util.ByteArrayDataSource;

byte[] pdfBytes = generateSmallPdf();

ByteArrayDataSource dataSource =
        new ByteArrayDataSource(
                pdfBytes,
                "application/pdf"
        );
```

If low-level MIME code uses `DataHandler`:

```java
import jakarta.activation.DataHandler;
import jakarta.mail.internet.MimeBodyPart;

MimeBodyPart part = new MimeBodyPart();
part.setDataHandler(new DataHandler(dataSource));
part.setFileName("invoice.pdf");
```

With `MimeMessageHelper`, prefer `addAttachment` overloads over constructing raw MIME structures directly unless specialized needs require it.

### Custom `DataSource`s Must Also Return Repeatable Data

A custom `DataSource` whose `getInputStream()` returns a single-use stream triggers the exact bug discussed here. Regardless of API, the source contract must match how Jakarta Mail consumes streams.

Keep library namespaces consistent: modern Spring projects use `jakarta.mail.*` and `jakarta.activation.*`; legacy code may use `javax.mail.*`. Never mix the two namespaces in the same code.

## 21. `setContent`/`saveChanges` Do Not Guarantee All Bytes Were Read

Another misconception:

```java
helper.addAttachment("report.pdf", source);
message.saveChanges();

// Assuming the file can be deleted after saveChanges is unsafe.
Files.delete(path);

mailSender.send(message);
```

`MimeMessage.saveChanges()` prepares/updates necessary headers such as `Message-ID` and MIME state per implementation; it **is not a promise that all attachments were eagerly loaded into an in-memory snapshot inside the message object**.

Similarly:

- `createMimeMessage()` does not read files.
- `addAttachment(...)` does not prove the file was serialized.
- `setContent(...)` does not guarantee all attachments were loaded from storage.
- `saveChanges()` does not turn lazy sources into immutable snapshots.

To verify data is readable, actually serialize MIME or send through a test transport—and still keep sources valid until real sending finishes.

## 22. Testing with a Mocked `JavaMailSender` Can Miss This Bug

Example:

```java
verify(mailSender).send(any(MimeMessage.class));
```

This test proves only that the service invoked `send`. Mockito mocks neither serialize MIME nor read attachment streams.

Thus a test can stay green even when:

- The stream is closed.
- The temp file was deleted.
- `InputStreamSource` returns a single-use stream.
- The attachment has zero bytes.
- The MIME content type is wrong.
- Inline images have mismatched CIDs.

**To test attachment lifecycles, tests must trigger actual byte reads**, not just verify Java method calls.

## 23. Testing That `InputStreamSource` Is Repeatable

Simple factory test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.InputStreamSource;

@Test
void attachmentSourceIsRepeatable() throws Exception {
    Path path = tempDir.resolve("sample.pdf");

    byte[] expected = new byte[] {
            0x25, 0x50, 0x44, 0x46
    };

    Files.write(path, expected);

    InputStreamSource source =
            () -> Files.newInputStream(path);

    byte[] first;
    byte[] second;

    try (InputStream a = source.getInputStream()) {
        first = a.readAllBytes();
    }

    try (InputStream b = source.getInputStream()) {
        second = b.readAllBytes();
    }

    assertThat(first).isEqualTo(expected);
    assertThat(second).isEqualTo(expected);
}
```

`tempDir` is JUnit 5's `@TempDir` declared on the test class, e.g.:

```java
@org.junit.jupiter.api.io.TempDir
Path tempDir;
```

This test confirms the factory yields data repeatedly; it does not yet verify MIME structure or SMTP transport.

### Testing the Single-Use Source Case

A fixture can deliberately return the same `InputStream` after closing it. Expect the subsequent read to throw or fail to return the prior bytes. The goal is demonstrating why `InputStreamResource` is the wrong choice without tying assertions to a single exact exception message.

## 24. Testing Real MIME Serialization Without Sending Email to the Internet

A solid approach is building the `MimeMessage` and calling `writeTo(...)` to force Jakarta Mail to serialize its contents:

```java
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayOutputStream;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

@Test
void serializesAttachmentAfterSourceIsBuilt()
        throws Exception {

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(
                    message,
                    true,
                    "UTF-8"
            );

    helper.setFrom("sender@example.org");
    helper.setTo("recipient@example.net");
    helper.setSubject("Test attachment");
    helper.setText("See attachment");

    byte[] expected = {
            1, 2, 3, 4, 5
    };

    helper.addAttachment(
            "bytes.bin",
            new ByteArrayResource(expected),
            "application/octet-stream"
    );

    message.saveChanges();

    ByteArrayOutputStream output =
            new ByteArrayOutputStream();

    message.writeTo(output);

    assertThat(output.toByteArray())
            .isNotEmpty();
}
```

This is a JUnit 5 + AssertJ test example; include appropriate `@Test`/`assertThat` imports. The test confirms MIME serializes; to prove attachment bytes are intact, parse the serialized message and walk the MIME tree comparing **decoded attachment bytes**, rather than comparing raw MIME text which varies in Base64 wrapping, boundaries, and headers.

### Why Serializing Twice Is Useful

When a source is built to be repeatable, serialize the exact same message twice into two separate `ByteArrayOutputStream`s and verify both contain the right attachment bytes. This catches sources returning single-use streams.

Do not require the raw bytes of both full MIME outputs to be byte-identical if headers/boundaries/timestamps vary; compare the decoded attachment bytes.

## 25. Walking the MIME Tree to Inspect Attachments

Attachments can live inside `multipart/mixed` or nested multiparts. Never assume “the attachment is always at `bodyPart` index 1”.

Example helper extracting attachments by filename:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

public final class MimeAttachmentReader {

    public static List<byte[]> findByFilename(
            Part part,
            String filename
    ) throws Exception {

        List<byte[]> found = new ArrayList<>();
        visit(part, filename, found);
        return found;
    }

    private static void visit(
            Part part,
            String filename,
            List<byte[]> found
    ) throws Exception {

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int index = 0;
                    index < multipart.getCount();
                    index++) {

                visit(
                        multipart.getBodyPart(index),
                        filename,
                        found
                );
            }
            return;
        }

        if (filename.equals(part.getFileName())) {
            try (InputStream in = part.getInputStream()) {
                found.add(in.readAllBytes());
            }
        }
    }
}
```

Test usage:

```java
MimeMessage parsed = new MimeMessage(
        jakarta.mail.Session.getInstance(
                new java.util.Properties()
        ),
        new java.io.ByteArrayInputStream(
                output.toByteArray()
        )
);

List<byte[]> attachments =
        MimeAttachmentReader.findByFilename(
                parsed,
                "bytes.bin"
        );

assertThat(attachments).hasSize(1);
assertThat(attachments.get(0))
        .isEqualTo(expected);
```

This illustrative snippet checks a fixed filename. In real apps, handle MIME nesting, encoded filenames, limits, and non-attachment parts that happen to carry filenames.

## 26. Integration Testing with an SMTP Test Server

`MimeMessage.writeTo(...)` tests serialization, yet a real send path also exercises:

- SMTP connection.
- TLS/AUTH per config.
- Runtime transport serialization.
- Exception mapping through `JavaMailSenderImpl`.
- Worker scheduling/retries.

Use **GreenMail**, **Mailpit**, or an isolated SMTP test server to receive test mail without relaying to the Internet.

Scenario:

1. Build MIME with attachments/inline resources.
2. Call `mailSender.send(message)` against the SMTP test server.
3. Retrieve the message from the test server.
4. Parse MIME and assert filename, content type, decoded bytes, and CIDs.
5. Verify sender/recipient/subject.
6. Test both premature stream closure and repeatable resources.
7. Test multiple sends/retries if policy allows.

Tests need no production credentials or real recipients. Use dummy test data, enforce size caps, and clean up resources afterward.

### Bugs Often Masked by Mocks

A Mockito `verify(send(...))` test never triggers attachment reads. An SMTP test server or `MimeMessage.writeTo` exposes lifecycle bugs at the right boundary.

## 27. Testing `@Async` to Reproduce the Race

A good test does not rely on `Thread.sleep(100)` hoping the worker runs after the caller. Use a `CountDownLatch` to enforce ordering:

```text
HTTP/request thread:
  open stream
  submit async task
  close stream
  signal worker

Worker:
  wait on latch
  build/serialize MIME
  observe stream closed or missing temp file
```

Then update the implementation to **persist the attachment and pass an attachment reference**, verifying the worker still reads all bytes after the request scope finishes.

Assertions:

- Under the broken approach, the attachment stream is invalid.
- Under the fixed approach, the worker opens a fresh stream and reads every byte.
- No request-scoped `InputStream` appears in the job payload.
- Retries can reopen the attachment.
- Cleanup removes files/objects only after retention/deadlines.
- If the worker crashes, the job survives because object storage still holds the attachment.

## 28. Retries Must Rebuild Messages or Keep Sources Repeatable

A notification may retry on transient SMTP errors. Keeping a single `MimeMessage` from the first attempt backed by single-use sources and reusing it can fail to read the attachment on retry.

Troublesome example:

```java
MimeMessage message = buildOnceUsingStream();

try {
    sender.send(message);
} catch (MailException firstError) {
    // Never blindly retry using the same message/single-use streams.
    sender.send(message);
}
```

The issue is not just `InputStream`. If SMTP accepted the message yet the reply was lost, retrying immediately can also cause **duplicate sends**. Classify outcomes:

| Outcome | Meaning | Handling Direction |
|---|---|---|
| `SMTP_ACCEPTED` | Transport confirmed acceptance | Do not retry merely awaiting a delivery webhook |
| `KNOWN_REJECTED` | Provider explicitly rejected | Retry depending on error class |
| `UNKNOWN` | Uncertain whether accepted | Reconcile or retry cautiously |
| `EXPIRED` | Notification no longer valid | Do not send |

A reliable worker typically:

1. Claims the notification ID.
2. Creates a fresh attempt ID.
3. Loads templates and attachment references from durable storage.
4. **Builds a fresh `MimeMessage` for the attempt**, using repeatable sources.
5. Sends within timeouts/quotas.
6. Persists accepted/rejected/unknown outcomes.
7. Schedules backed-off retries when permitted.

Keeping source data stable across attempts matters more than keeping one `MimeMessage` object in memory.

## 29. How Long Must the Attachment Source Exist?

Think in four milestones:

```text
REQUEST ACCEPTED
      |
      v
JOB QUEUED
      |
      v
ATTEMPT STARTED
      |
      v
SMTP SUBMISSION FINISHED
      |
      v
JOB FINALIZED / RETRY WINDOW ENDS
```

For a single synchronous send, the source must remain readable until `send` finishes.

With queues/retries, data must remain at least until:

- The email is accepted and MIME no longer needs rebuilding, or
- The job is cancelled/expired/permanently failed and retention allows cleanup.

If content inspection/reconciliation is required by compliance, retain longer in storage with dedicated policies. Do not keep all attachments forever by default.

**Never tie attachment lifetime to HTTP request lifetime** when jobs execute asynchronously.

## 30. Cleaning Up Temp Files Properly in Synchronous Sends

If a temp file exists strictly for a single synchronous send, clean up after `send` finishes:

```java
Path temp = Files.createTempFile(
        "mail-report-",
        ".pdf"
);

try {
    renderReportTo(temp);

    MimeMessage message =
            buildWithFileSystemResource(temp);

    mailSender.send(message);

} finally {
    Files.deleteIfExists(temp);
}
```

`buildWithFileSystemResource` is an application-defined helper; it must use a source that opens fresh streams from the file and build a valid message.

This is appropriate only when:

- `send` is genuinely synchronous and finishes all MIME reads before returning.
- No background worker retains the message.
- No deferred retry reuses the path.
- No provider callback needs attachment access.
- Cleanup failures are handled/monitored properly.

If the source is queued for later sending, **never** delete the file inside the producer's `finally` block like this.

## 31. Should `FileSystemResource` Be Used for User-Uploaded Files?

Yes, with additional safeguards:

- Store files in a controlled directory; never use client filenames directly as paths.
- Enforce tenant and notification authorization.
- Cap file sizes and allowed types.
- Scan content per policy.
- Ensure files are completely written and immutable before queueing jobs.
- Restrict process permissions and enforce retention-based cleanup.
- Never log absolute paths containing sensitive data.
- If workers run on other nodes, ensure storage is accessible via object keys/versions.
- Prevent symbolic links or path traversal from pointing workers outside allowed directories.
- Monitor disk quotas and pending file counts.

`FileSystemResource` solves **opening fresh streams**, not security or data lifecycles by itself.

## 32. Filename, `Content-Type`, and MIME Data

An attachment with valid bytes can still be unusable if metadata is wrong.

Verify:

- `attachmentFilename` is a sanitized display name, not a full path.
- `contentType` follows policy rather than blindly trusting client input.
- PDFs use `application/pdf` once verified valid.
- Inline images have `Content-ID` matching `cid:...` in HTML.
- Text/HTML charsets are configured (e.g., UTF-8).
- MIME tree fits, e.g. `MULTIPART_MODE_MIXED_RELATED` when combining attachments and inline resources.
- Attachment bytes are non-empty if the domain forbids empty files.

Example:

```java
helper.setText(
        "Plain text alternative.",
        "<p>See the attached file.</p>"
);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Unicode filenames must be tested across your JavaMail/Spring versions and target mail clients if cross-client compatibility is required.

## 33. Should Every `InputStream` Opened by the Application Be Closed?

Yes, for streams **the application opens and consumes directly**:

```java
try (InputStream input = Files.newInputStream(path)) {
    byte[] bytes = LimitedBytes.readAtMost(
            input, maxBytes
    );
    // Process bytes.
}
```

However, when the application supplies a **factory** for the library to open streams later:

```java
InputStreamSource source =
        () -> Files.newInputStream(path);
```

no stream is open yet when creating the factory for your code to close upfront. The consumer opens read sessions via the API and manages the lifecycle of returned streams per its implementation.

**Never write “close all streams before returning”** if the library needs to read those exact streams after your method returns.

## 34. MIME Data May Be Read More Than Once: Why Does This Matter?

A system may:

- Call `saveChanges()` to update headers.
- Serialize MIME to a byte stream.
- Log/test by writing MIME to an output stream.
- Submit MIME over SMTP.
- Retry attempts from the same source.
- Generate a preview/test copy from the content.

Each step can trigger another read. If a source works only once, subsequent steps fail even after the first succeeded.

Thus the key rule is not “wait 2 seconds before closing the stream”, but:

> **For `MimeMessageHelper` attachments/inline parts, supply a data source that returns a fresh `InputStream` starting from byte zero every time it is requested.**

Each individual stream closes once its consumer finishes; the underlying data source stays alive long enough.

## 35. Never Use `available()` to Check If an Attachment Has Data

A diagnostic mistake:

```java
if (input.available() == 0) {
    throw new IllegalStateException("Empty file");
}
```

`InputStream.available()` estimates bytes readable without blocking right now, **not total file size**. Zero does not mean EOF/empty, and positive values do not prove the stream is intact.

To verify:

- Read bytes within a size bound.
- Check the actual byte count read.
- For repeatable sources, open a fresh stream when needed.
- Test MIME serialization and decoded attachments.
- Never rely on `available()` or `markSupported()` for correctness.

## 36. Error Mapping: `Stream closed` Is Not SMTP Rejected

An attachment read error occurs **before the SMTP request completes**, often before MIME bytes even finish transmitting. Distinguish:

| Group | Examples | Meaning |
|---|---|---|
| Source data failure | File not found, stream closed, object expired | Cannot build/read attachment properly |
| MIME serialization failure | Invalid MIME part, encoding/content handler failure | Message never serialized cleanly |
| SMTP transport failure | AUTH/TLS/connect timeout | Connection or authentication failed |
| SMTP provider rejection | Invalid recipient, policy, throttling | Provider returned a rejection |
| Unknown submission | Connection dropped at ambiguous stage | Cannot tell whether provider accepted |

Never map everything to `MAIL_SEND_FAILED` and endlessly retry with the same broken stream object.

If the source file was permanently deleted, retries cannot recreate it. Workers must transition the job to a data-fix or permanent-failure state per policy instead of retrying every second.

## 37. Observability: Log Enough Without Exposing Attachments

Useful fields:

```text
notificationId = notif-421
attemptId = attempt-421-02
attachmentRef = att-918
attachmentVersion = v3
sourceType = OBJECT_STORAGE
errorCategory = ATTACHMENT_STREAM_CLOSED
stage = MIME_SERIALIZATION
providerRoute = transactional-primary
```

Never log:

- Attachment contents.
- Sensitive filenames containing personal names.
- Absolute paths containing identifying data.
- S3/bucket credentials or presigned URLs.
- Bodies/OTPs/tokens.
- Raw SMTP AUTH exchanges.

Safe log example:

```java
log.warn(
        "Mail attachment read failed: "
      + "notificationId={}, attemptId={}, "
      + "attachmentRef={}, stage={}, category={}",
        notificationId,
        attemptId,
        attachmentRef,
        "MIME_SERIALIZATION",
        "SOURCE_UNAVAILABLE"
);
```

When stack traces are needed, keep them in access-restricted diagnostic logs with short retention. Never put raw `IOException.getMessage()` into metric labels or audit records because paths and metadata can be sensitive.

## 38. Metrics to Spot Stream and Attachment Issues

Illustrative metrics:

| Metric | Meaning |
|---|---|
| `mail_attachment_open_total` | Stream opens from attachment storage |
| `mail_attachment_open_failure_total` | Failed source opens |
| `mail_attachment_read_failure_total` | Failed stream reads |
| `mail_attachment_bytes_read_total` | Total actual bytes read |
| `mail_mime_serialization_failure_total` | Failed MIME serializations |
| `mail_send_attempt_total` | Started SMTP attempts |
| `mail_send_accepted_total` | SMTP acceptances |
| `mail_outbox_pending` | Pending jobs |
| `mail_outbox_oldest_age_seconds` | Age of oldest pending job |

These names are suggestions; not all metrics exist out of the box in Spring Mail.

Tags can use bounded enums like `sourceType`, `stage`, and `errorCategory`. Never use `attachmentId`, filenames, paths, or recipient emails as metric tags due to cardinality and privacy.

### Diagnostic Signals

```text
mail_mime_serialization_failure_total rises
mail_attachment_read_failure_total rises
smtp accepted rate drops
  -> inspect InputStreamSource/resource lifecycle

mail_attachment_open_failure_total rises
  -> storage availability/credentials/retention

mail_outbox_pending grows, attachment errors stable
  -> worker/SMTP throughput/backpressure may be bottleneck
```

## 39. Runbook: `Stream closed` in Production

### Step 1 — Isolate Attachment/Inline

Check whether the exception involves `getInputStream`, `DataHandler`, `DataSource`, `MimeMessageHelper.addAttachment`, or `addInline`.

### Step 2 — Identify the Data Source

- `ByteArrayResource`?
- `InputStreamResource`?
- `FileSystemResource`?
- Custom `InputStreamSource`?
- Object storage `DataSource`?
- Request-scoped `MultipartFile`?

If you see `InputStreamResource` or a factory returning the same stream, target that first.

### Step 3 — Find When It Closes/Deletes

Look for `try-with-resources`, `finally`, temp file cleanup, upload request completion, object storage retention, and cancellations.

### Step 4 — Trace Async Boundaries

HTTP request → `@Async`, queues, outboxes, scheduled jobs, or cross-replica workers. Is an open stream or local path crossing the boundary?

### Step 5 — Verify Repeatability

Call `getInputStream()` multiple times on a test source, read bytes, and compare contents. Test `MimeMessage.writeTo` or send through an SMTP test server.

### Step 6 — Fix According to Size and Storage

- Small/bounded files: `ByteArrayResource`.
- Stable local files: `FileSystemResource`.
- Object storage/queues: store references and use a factory opening fresh streams.
- Retries: rebuild MIME from durable storage.

### Step 7 — Triage Prior Impacts

Never bulk-resend if some attempts have `UNKNOWN` outcomes. Inspect states/attempts, determine whether source failures happened before or after SMTP acceptance where evidence exists, and apply controlled retries.

### Step 8 — Monitor Recovery

Confirm attachment read failures drop, MIME serialization succeeds, SMTP acceptance rate recovers, queue age shrinks, and duplicate messages do not spike.

## 40. Other Anti-Patterns

| Anti-Pattern | Consequence | Alternative |
|---|---|---|
| `new InputStreamResource(openStream)` for attachments | Single-use; risks early close/EOF | `ByteArrayResource` or fresh-open source |
| Closing stream right after `addAttachment` | Fails when sender reads later | Repeatable source, proper lifecycle |
| Moving `send` inside `try` only | Still fails on multiple reads | Each `getInputStream` opens a fresh stream |
| Using `InputStreamSource () -> sameStream` | Second read hits EOF | Factory opens fresh stream |
| Deleting temp file right after enqueueing | Worker cannot find file | Durable storage and retention |
| Passing `MultipartFile` over `@Async` | Request temp resource expires | Persist upload, pass attachment ID |
| Putting local absolute path onto broker | Other pod replicas lack the file | Object key/version |
| Reading huge files with `readAllBytes` | OOM/high heap | Streaming source and size policy |
| Resource reads different version per open | Inconsistent MIME | Immutable/versioned object |
| Calling `saveChanges` then deleting file | Content may still be lazy | Keep data until send/retry lifecycle ends |
| Mockito `verify(send)` as sole test | Never reads attachments | MIME serialization / test SMTP server |
| Retrying with same single-use message | EOF or duplicate sends | Rebuild per attempt, classify outcomes |
| Using `available()==0` to check empty files | False positives | Real reads / byte counts |
| Logging full MIME on failure | Leaks PII/OTP/attachments | Structured metadata and redaction |
| Missing timeouts/storage retention | Hung streams or premature deletion | Bounds, retention, monitoring |

## 41. Implementation Checklist

1. Identified who opens, reads, and closes every `InputStream`.
2. No single-use `InputStreamResource` used for MIME attachments/inline assets.
3. `InputStreamSource.getInputStream()` returns a fresh stream from byte zero every time.
4. Source bytes remain unchanged across opens within an attempt.
5. Files/objects survive until submission completes and across the retry window.
6. No open streams cross `@Async`, queue, or process boundaries.
7. Queued jobs store attachment ID/object key/version, never file handles.
8. Workers load sources and build MIME per attempt.
9. Small files use `ByteArrayResource` only after enforcing size caps.
10. Large files use repeatable streaming sources with concurrency limits.
11. Attachment size is checked at ingest and read time.
12. Filenames/content types are sanitized and validated.
13. Inline CIDs match the HTML body.
14. Local files are never cleaned up before `send` completes.
15. Across replicas, workers can access shared storage.
16. Object storage credentials/URLs are never logged or kept in long-lived queues.
17. Retry data stays intact; new attempts build fresh messages.
18. Source errors, MIME errors, SMTP rejections, and `UNKNOWN` outcomes are distinguished.
19. Unit tests open the source twice and compare bytes.
20. Tests serialize via `MimeMessage.writeTo` and inspect the MIME tree.
21. Integration tests run against an SMTP test server, never production.
22. Async tests reproduce request cleanup and delayed worker execution.
23. Metrics/alerts cover attachment open/read/serialize failures.
24. A runbook defines retry triage to avoid duplicates.
25. Storage retention deletes data per policy rather than keeping everything forever.

## 42. Key Takeaways

- `MimeMessageHelper.addAttachment(...)` does not necessarily read the entire attachment when called.
- Jakarta Mail may open the stream during serialization/sending and may read it more than once.
- `InputStreamResource` wraps an already-open stream and is not a suitable repeatable source for MIME attachments.
- **An `InputStreamSource` used with MIME should return a fresh `InputStream` from the start on every call.**
- `ByteArrayResource` suits small, bounded payloads; data no longer depends on the initial stream.
- `FileSystemResource` can open fresh streams, provided the file stays present and stable.
- For object storage, use a source factory opening fresh streams by object key/version.
- `try-with-resources` is not bad; closing a resource while a consumer still needs it—or passing a single-use resource to a repeatable API—is the bug.
- `@Async` and queues amplify risk because producers close request streams before workers run.
- Never pass `MultipartFile`, open streams, or temp file handles across durable queues.
- `saveChanges()` does not guarantee every MIME attachment was snapshotted into memory.
- Mocking `JavaMailSender.send` alone never tests reading attachment bytes; use `writeTo` or an SMTP test server.
- On retry, rebuild the message from durable data instead of reusing single-use streams.
- `Stream closed` is a source/MIME failure, not automatically an SMTP provider rejection.
- Never blind-retry when the submission outcome could be `UNKNOWN`.
- Log enough for investigation without recording raw attachments, presigned URLs, or secrets.

**Conclusion:** The mistake of **closing an `InputStream` before the sender finishes reading it** stems from confusing “attached to `MimeMessage`” with “attachment bytes already consumed”. In Spring Framework Mail, supply **repeatable data sources**, preserve sources across the full send/retry lifecycle, and pass **durable references** rather than open streams across asynchronous boundaries. Following these rules keeps attachments and inline images working reliably even when Jakarta Mail reads lazily, re-reads, runs on another replica, or recovers after failures.

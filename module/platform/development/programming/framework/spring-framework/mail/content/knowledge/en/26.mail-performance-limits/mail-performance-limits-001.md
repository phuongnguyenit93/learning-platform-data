# MIME Creation Overhead and Attachment Encoding

When sending a short plain-text email, a Spring Framework Mail application typically only needs to create a `MimeMessage`, set the addresses, subject, and body, and then call `JavaMailSender.send(...)`. However, if the email includes HTML, inline images, multiple PDF files, or large attachments, the cost no longer lies solely in a single send call. The application must construct the MIME structure, read the data sources, encode each part to conform to email protocols, transmit a larger byte payload than the original files over SMTP, and wait for the mail server to accept it.

**MIME creation overhead and attachment encoding** must be viewed across four resources simultaneously: **CPU, memory, I/O, and worker hold time**. For example, a 25 MiB PDF, when transmitted using Base64 with standard MIME line wrapping, can produce roughly 34.2 MiB of encoded content for the attachment alone. If dozens of emails are sent concurrently, each containing a PDF of that size, the bottleneck could lie in PDF generation, holding `byte[]` arrays, disk reads, Base64 encoding, bandwidth, or SMTP server limits.

This lesson in the **Performance and Limits** chapter of **Spring Framework Mail** explains the MIME lifecycle, how to estimate message sizes, the differences between `Resource` types, situations that cause duplicate data copies in the heap, concurrency-limiting strategies, and how to measure performance without leaking email contents.

## 1. Learning Objectives

After completing this lesson, learners should be able to:

1. Describe the path from application content to `MimeMessage` and SMTP `DATA`.
2. Estimate the size expansion when attachments use Base64 and MIME line folding.
3. Distinguish between **source file size**, **serialized MIME size**, and **bytes on the wire**.
4. Explain why creating a `MimeMessageHelper` does not necessarily mean all attachments have already been read or encoded.
5. Choose between `ByteArrayResource`, `FileSystemResource`, and `InputStreamSource` based on data characteristics.
6. Avoid holding multiple copies of large files in the heap or holding unusable streams.
7. Identify message size, attachment count, and concurrency limits before sending.
8. Design instrumentation sufficient to distinguish CPU, I/O, SMTP, and GC bottlenecks.
9. Recognize the trade-offs between sending one message to multiple recipients versus multiple separate messages.
10. Avoid optimizations that reduce reliability, leak information, or cause duplicate emails.

## 2. Lifecycle of Creating and Sending a MIME Message

An HTML email with attachments typically goes through these steps:

```text
Business data
    |
    v
Render text / HTML template
    |
    v
Create MimeMessage + MimeMessageHelper
    |
    +--> Create multipart containers
    +--> Set headers / plain text / HTML
    +--> Attach InputStreamSource or Resource
    |
    v
Prepare / serialize MIME
    |
    +--> Read attachment/inline bytes
    +--> Encode (often Base64 for binary)
    +--> Write boundary / headers / CRLF
    |
    v
SMTP connection / EHLO / AUTH / MAIL / RCPT
    |
    v
SMTP DATA: transfer MIME bytes
    |
    v
Wait for final SMTP response
```

The steps above may interleave or be executed differently by the library depending on the implementation. In particular, `MimeMessageHelper.addAttachment(...)` mainly **attaches the content source to the MIME part**; do not assume that at this exact call all bytes have already been loaded, Base64-encoded, and stored in a `String`.

When `JavaMailSenderImpl` hands the message over to the Jakarta Mail transport, the MIME is prepared/serialized for sending; attachments may be read when streaming the content out. How the data source is supplied therefore directly affects memory usage, read count, latency, and retry capability.

### Distinguishing Performance Measurement Phases

| Phase | Main Work | Common Costs |
| --- | --- | --- |
| **Generate** | Generate PDF/CSV/images or fetch files from storage | CPU, heap, disk, network |
| **Render** | Build text and HTML using templates | CPU, allocations, data queries |
| **Compose** | Create `MimeMessage`, MIME tree, and headers | Object allocation, validation |
| **Encode/serialize** | Read bytes, encode attachments, build MIME wire representation | CPU, read I/O, output bytes |
| **Submit** | Connect and transmit over SMTP | Network latency, bandwidth, timeout |
| **Record outcome** | Update status in the database | Short transaction/I/O |

Measuring only the duration of `new MimeMessageHelper(...)` will miss the cost of reading and encoding attachments during `send`. Measuring only `send` may lump together serialization, network I/O, and waiting on the SMTP server.

## 3. MIME Is a Container, Not Just HTML

An email with two content alternatives, inline images, and attachments typically has this structure:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   ├── image/png; disposition=inline
    │   └── image/jpeg; disposition=inline
    ├── application/pdf; disposition=attachment
    └── text/csv; disposition=attachment
```

Each MIME part may carry:

- `Content-Type` and parameters such as charset or name.
- `Content-Transfer-Encoding`.
- `Content-Disposition` and filename.
- `Content-ID` for inline parts.
- The data payload represented in the appropriate encoding.
- Boundaries and CRLF to separate it from other parts.

Thus, the message size is not simply:

```text
html.length + attachmentFile.length
```

but also depends on the charset, transfer encoding, headers, number of parts, boundaries, filenames, and how the library serializes them.

## 4. Why Do Binary Attachments Usually Use Base64?

MIME must represent binary data in a form suitable for email systems. Base64 converts every group of three bytes into four ASCII characters. Files such as PDF, PNG, JPEG, XLSX, and ZIP typically have binary content and are sent as a MIME part with:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64
```

Key points:

- Base64 **is an encoding, not compression**.
- Base64 **is not security encryption**; anyone with the raw MIME can decode the content.
- Base64 **increases the size** of the transmitted bytes.
- Specifying `Content-Type: application/pdf` does not mean the file is reduced in size or validated as a valid PDF.
- Each attachment is typically a separate MIME part, incurring its own overhead.

### Base64 Size Formula Before Line Folding

For `N` input bytes, the number of Base64 characters is:

\[
B(N) = 4\left\lceil\frac{N}{3}\right\rceil
\]

For example, 3 bytes require 4 characters; 4 bytes require 8 characters because the final group is padded.

If `N` is sufficiently large and divisible by 3, the approximate factor is:

\[
\frac{B(N)}{N}\approx\frac{4}{3}=1.3333.
\]

That means Base64 alone increases the size by about **33.3%** over the source bytes. For small files, padding can make the ratio even higher.

## 5. MIME Line Folding Increases the Size Further

Base64 in MIME is typically split into lines, with a maximum line length of 76 characters per standard MIME representation. Lines are separated by `CRLF` (2 bytes).

For a sufficiently large group:

```text
57 bytes of original data
       |
       v
76 Base64 characters
       |
       v
76 characters + 2-byte CRLF
       |
       v
78 bytes of MIME content
```

Approximate factor:

\[
\frac{78}{57}\approx 1.3684.
\]

For large files, **the folded Base64 body size is typically about 36.8% larger** than the original file. The MIME part's headers and boundaries are added on top of this.

### Practical Estimation Formula

Let `C=4×ceil(N/3)` be the number of Base64 characters. If each line is at most 76 characters, the approximate number of lines is `L=ceil(C/76)`. The estimate including line endings is:

\[
E(N)\approx C+2L.
\]

This is an **estimate** because how the library places the trailing CRLF of a part, the next boundary, and other metadata bytes can cause the actual size to differ slightly.

### Reference Size Table

| Binary Size | Unfolded Base64 | MIME Base64 with CRLF, approx. | Approx. Overhead |
| --- | ---: | ---: | ---: |
| 1 MiB | 1.33 MiB | 1.37 MiB | 0.37 MiB |
| 5 MiB | 6.67 MiB | 6.84 MiB | 1.84 MiB |
| 10 MiB | 13.33 MiB | 13.68 MiB | 3.68 MiB |
| 20 MiB | 26.67 MiB | 27.37 MiB | 7.37 MiB |
| 25 MiB | 33.33 MiB | 34.21 MiB | 9.21 MiB |

`MiB` is `1,048,576` bytes, different from `MB` which is `1,000,000` bytes. This is the **estimated size of the Base64 attachment body**, excluding the rest of the email, some headers/boundaries, and SMTP framing.

**Do not take a provider's "25 MB attachment" limit and assume you can send an exact 25 MB source file.** The provider may limit the total message size after encoding; the threshold, measurement method, and overhead must be checked in the provider's documentation.

## 6. How Many Bytes Will a Message with Multiple Attachments Have?

Suppose:

- An 8 MiB PDF.
- A 2 MiB PNG image.
- A 1 MiB CSV file.
- Text/HTML content totaling about 100 KiB before encoding.

The three attachments total 11 MiB binary. If each file is Base64-encoded with MIME folding, the attachment bodies alone are roughly:

\[
11\times 1.3684\approx 15.05\ \text{MiB}.
\]

Adding the HTML/text, MIME part headers, boundaries, filenames, inline data, and anything the relay requires, the message can exceed 15 MiB.

When a message is near a server threshold:

1. Do not just add up the original file sizes.
2. Calculate a conservative upper bound for the large parts.
3. Reserve a buffer for MIME headers/body.
4. For borderline cases, serialize a **test message using dummy data** to measure actual bytes, then test against an SMTP test server.
5. Still handle `SIZE` or `552` errors returned by the provider, because a client estimate is not a guarantee that the server will accept it.

## 7. Inline Images Also Have Attachment-Like Overhead

A logo added with:

```java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
```

can become a Base64 binary part inside `multipart/related`. Even though the mail client renders the logo **inside the HTML**, the image bytes still travel with the message:

```html
<img src="cid:brand-logo" alt="Brand">
```

If the same 500 KiB image is embedded into 20,000 separate emails, the byte volume at the SMTP layer can be substantial:

```text
500 KiB source image
      x Base64 + folding (~1.368)
      x 20,000 messages
      = approx. 13.1 GiB encoded inline-image payload
```

That is just the image alone, excluding the body and other parts. For high-volume emails, optimizing image size, using the right format, and avoiding unnecessary assets can be more effective than optimizing a few lines of Java.

**Switching inline images to externally hosted images** can reduce the SMTP payload, but shifts the cost to HTTP requests, depends on whether the client loads images, and introduces issues around privacy/tracking, expiring URLs, host security, and offline experience. This is a product trade-off, not a "free" optimization.

## 8. Base64 Is Not the Only Cost for Text Content

`text/plain` and `text/html` can use:

- `7bit`, if the content is suitable.
- `quoted-printable`, often convenient when most characters are ASCII and only a few bytes need encoding.
- `base64`, depending on content and implementation.
- Other representations if SMTP capabilities and configuration allow.

A long HTML email with many Unicode characters can produce a wire payload significantly different from Java's `String.length()`. `String.length()` counts UTF-16 code units, not UTF-8 bytes, and not MIME bytes.

For example:

```java
String text = "Hóa đơn số 123 – cảm ơn bạn";

int utf16CodeUnits = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
```

These two numbers can differ. MIME encoded bytes are yet a third number.

In most emails with large PDFs/images, Base64 attachments make up the bulk of the payload; however, in campaigns of hundreds of thousands of HTML-only emails, template size, inline CSS, and tracking URLs also significantly affect total bandwidth.

## 9. ByteArrayResource: Simple, but Consider Heap Usage

In Spring, `ByteArrayResource` is very convenient for data already in memory:

```java
byte[] pdfBytes = pdfGenerator.generate(orderId);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Benefits:

- No need to create temporary files.
- `getInputStream()` returns a new `ByteArrayInputStream`, allowing the data to be re-read.
- Easy to write unit tests with `assertArrayEquals` on decoded content.
- Suitable for small attachments or APIs that already return `byte[]`.

However, in this case, **the entire PDF is already in the heap** as a `byte[]` before being added to the message.

If each PDF is 20 MiB and 20 sending tasks are each holding their own array, the raw PDF arrays alone can hold around 400 MiB of heap, not counting:

- Input data for the PDF generator.
- Buffers and objects used during PDF generation.
- HTML/text rendering and the MIME tree.
- Buffers used during serialization or I/O.
- Copies if the code uses `toByteArray()` or copies arrays.
- Request data, DB entities, worker queues, and logging.

### Does ByteArrayResource Always Duplicate the byte[]?

Do not claim that `new ByteArrayResource(pdfBytes)` **always** copies the entire array. The primary issue is that the application **has already created a large array** to represent the file. Other steps before and after may continue to allocate buffers or copies, depending on the implementation.

For example:

```java
ByteArrayOutputStream output = new ByteArrayOutputStream();
pdfGenerator.writeTo(output);

byte[] pdf = output.toByteArray();
ByteArrayResource resource = new ByteArrayResource(pdf);
```

Here, `ByteArrayOutputStream` has an internal buffer; `toByteArray()` allocates a new array. While both objects remain alive, two byte regions can coexist. That cost is **due to how the data is produced**, not standalone proof that `MimeMessageHelper` keeps a full Base64 copy in the heap.

## 10. FileSystemResource: Avoid Actively Holding the Entire File in Memory

When an attachment already exists on the filesystem, you can pass a resource instead of reading the file into an array:

```java
Path pdfPath = Paths.get("/safe-mail-temp", "invoice-123.pdf");

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(pdfPath),
        "application/pdf"
);
```

With `FileSystemResource`, the library can open a stream to read the file when emitting MIME data. This approach **does not force the application to actively hold the entire file in a `byte[]`**.

### Data Flow Comparison

```text
ByteArrayResource
-----------------
Generate PDF -> byte[] in heap
                      |
                      v
             ByteArrayResource
                      |
                      v
                MIME serialization
                      |
                      v
                    SMTP

FileSystemResource
------------------
Generate PDF -> file on disk
                      |
                      v
               FileSystemResource
                      |
                      v
           Stream/read during MIME output
                      |
                      v
                    SMTP
```

The difference is not just "files are faster than arrays." Both have trade-offs:

| Criterion | `ByteArrayResource` | `FileSystemResource` |
| --- | --- | --- |
| Source data | Already in `byte[]` | Located on the filesystem |
| Heap before send | Can be large depending on file size | Usually does not need an array holding the whole file |
| Extra I/O | No disk read needed during transmission | Requires filesystem reads |
| Re-readability | Good while the array is alive | Good if the file still exists and is unmodified |
| Lifecycle | Tied to object/GC | Must manage files and access permissions |
| Best suited for | Small attachments, in-memory data | Large attachments, pre-generated or temp-stored files |
| Risks | Heap pressure, holding many `byte[]` | Disk space exhaustion, missing files, premature cleanup |

**Neither resource type is always better.** If the original data source is already a stable file, reading the whole thing into a `byte[]` just to create an email can be an unnecessary allocation. If it is only a small payload of a few KiB, creating a temp file just to avoid an array can add unnecessary I/O and complexity.

### How Long Must a Temporary File Exist?

`addAttachment(...)` usually does not mean the attachment has been completely read. Therefore:

```java
Path file = generatePdfToTempFile();
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(file),
        "application/pdf"
);
Files.delete(file);  // Wrong: may delete before serialize/send.
```

Before the worker sends the message, the file may need to be read later. The temporary file must be kept long enough for the serialize/send process to finish or until the system decides not to send anymore; how it is managed depends on the task lifecycle and retry mechanism.

## 11. InputStreamSource: The Critical Requirement Is Re-readability

`MimeMessageHelper.addAttachment(...)` supports `InputStreamSource`. This interface has a method returning an `InputStream`, but you must understand Spring Mail / Jakarta Mail's expectation: **the data source should allow opening a fresh stream each time it is requested**.

Example of a source that creates a stream from a file:

```java
InputStreamSource source = () ->
        Files.newInputStream(
                Paths.get("/safe-mail-temp", "invoice-123.pdf")
        );

helper.addAttachment(
        "invoice.pdf",
        source,
        "application/pdf"
);
```

Each call to `getInputStream()` opens a new stream. That differs from holding a single pre-opened stream:

```java
InputStream alreadyOpen = Files.newInputStream(path);

InputStreamSource problematic = () -> alreadyOpen;

// Not recommended: subsequent reads may receive a consumed/closed stream.
helper.addAttachment(
        "invoice.pdf",
        problematic,
        "application/pdf"
);
```

### Why Might Jakarta Mail Need Multiple Reads?

MIME preparation, `saveChanges()`, `writeTo(...)`, and transport sending may interact with the data at different times. Some cases need to inspect the content type, encoding, or serialize repeatedly during tests/retries.

Therefore, a read-once source can:

- Work on one code path and fail on another.
- Return a stream already at EOF, producing an empty attachment.
- Throw an exception because the stream is already closed.
- Make retries difficult if the worker has already consumed the data.

`InputStreamResource` typically represents an already-opened stream that is single-use; it should not be treated as an automatically re-readable resource. If multiple streaming passes are needed, use `FileSystemResource`, `ByteArrayResource`, or an `InputStreamSource` that opens a new stream on demand.

## 12. Do Not Equate Streaming with "Zero Memory"

Streaming avoids holding the entire file in a single array, but **it does not mean SMTP sending uses no memory**.

Even when using `FileSystemResource`:

- Jakarta Mail and Java may maintain read/write buffers.
- TLS sockets have their own buffers.
- MIME objects and headers still reside on the heap.
- Template rendering may produce large `String`s.
- Some providers/layers may buffer or transform data.
- The library may read the resource multiple times depending on the execution path.

The practical goal is to **reduce memory that scales linearly with the total size of pending files**:

```text
Uncontrolled:
heap ~ attachment bytes x concurrent tasks + other buffers

Reasonable streaming:
heap ~ MIME objects + bounded buffers x concurrent tasks
       (attachment is read from an off-heap source when needed)
```

This is a conceptual model, not an exact formula for the allocation behavior of every Spring/Jakarta Mail version. Measure with real workloads and the actual implementation.

## 13. Example: MailComposer Using FileSystemResource

A simple way to organize this is a composer that builds the content and attaches an existing file:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public final class InvoiceMailComposer {

    private final JavaMailSender sender;

    public InvoiceMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage compose(
            String recipient,
            String orderCode,
            String plain,
            String escapedHtml,
            Path invoicePdf
    ) throws MessagingException {

        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Invoice for order " + orderCode);
        helper.setText(plain, escapedHtml);
        helper.addAttachment(
                "invoice.pdf",
                new FileSystemResource(invoicePdf),
                "application/pdf"
        );

        return message;
    }
}
```

The `plain` and `escapedHtml` parameters are assumed to have been prepared safely. In production, render HTML using a template engine with context-appropriate escaping; do not concatenate raw user input directly into HTML.

### Sending Service and Lifecycle Management

```java
public final class InvoiceMailService {

    private final JavaMailSender sender;
    private final InvoiceMailComposer composer;

    public InvoiceMailService(
            JavaMailSender sender,
            InvoiceMailComposer composer
    ) {
        this.sender = sender;
        this.composer = composer;
    }

    public void submit(
            String recipient,
            String orderCode,
            String plain,
            String html,
            Path pdfFile
    ) throws MessagingException {

        MimeMessage message = composer.compose(
                recipient, orderCode, plain, html, pdfFile
        );
        sender.send(message);
    }
}
```

The service above is a minimal example for synchronous single-send execution. If the file is generated inside the task, cleanup must be handled using `try/finally` **after the call that reads the file has completed** and aligned with the retry lifecycle. If sending asynchronously, never delete the file immediately after submitting the task to an executor.

## 14. Generating Large Attachments: Use a Stream/File Output Path When Possible

Suppose the application generates a PDF. There are two hypothetical APIs:

```java
byte[] pdf = pdfGenerator.generateToByteArray(report);
```

and:

```java
pdfGenerator.writeTo(report, outputStream);
```

If the document generator supports writing to an `OutputStream`, you can consider:

```java
Path pdfFile = Files.createTempFile(
        "mail-invoice-", ".pdf");

try (OutputStream output =
             Files.newOutputStream(pdfFile)) {
    pdfGenerator.writeTo(report, output);
}

// Worker keeps the file until send/retry policy completes.
```

The benefit is that you are not forced to keep the entire PDF in a `byte[]`. In return, you take on extra I/O and temporary file management responsibility.

**Operational note:** the file path must reside in an allowed directory, have restricted permissions, disk space quotas, and cleanup on task success or failure. If the service runs in a container with ephemeral disk, files can be lost on restart; durable storage is needed if send requests must survive crashes.

## 15. Resources from Object Storage or External Services

When an attachment lives in object storage, you might consider:

```java
InputStreamSource source = () ->
        objectStorage.openStream(storageKey);
```

This is an illustrative abstraction; `objectStorage` and `storageKey` are defined by the application. To be safe:

1. `openStream(...)` must create a **fresh stream** on every call.
2. The data must remain accessible when the worker serializes the message.
3. Have timeouts, size limits, and a retry policy for fetching the content.
4. Do not use a short-lived signed URL as the sole dependency for a task processed hours later.
5. Enforce explicit authentication/authorization for the object.
6. Consider checksums or version IDs to prevent the file from changing between two reads.
7. Do not log signed URLs/tokens in exceptions or diagnostics.

### Remote Streams Are Not Free

Using a remote stream can reduce heap usage, but it adds network requests and latency **before or during SMTP send**. If the source is read multiple times, object storage may be downloaded multiple times. If storage networking is slow, the SMTP worker can be held open for a long time even though the bottleneck is not the mail server.

Measure **fetch source** time and **SMTP submit** time separately. If a file is reused repeatedly, a bounded cache or managed local copy can help, but must balance disk space, consistency, and security requirements.

## 16. When to Attach a File vs. When to Send a Link

For very large reports, you can choose to send a download link instead of attaching the file:

| Approach | Pros | Cons |
| --- | --- | --- |
| MIME attachment | Recipients can save the file with the email; convenient offline | Base64 overhead, message size limits, bandwidth |
| HTTPS download link | Small email; can manage versions and download permissions | Depends on Internet, link expiration, UX, and auth |
| Small attachment + link to full version | Offers offline summary while keeping size down | Increases content design complexity |

Do not automatically convert a sensitive attachment into a public URL just to optimize SMTP. Links should have appropriate authentication/authorization, expiration, revocation, rate limiting, and access logging. Emails can be forwarded; bearer signed URLs inside emails must be evaluated for forwarding risk.

If business rules mandate attaching an immutable invoice, replacing it with a link may not be compliant. Performance must not violate the system's archival and legal requirements.

## 17. Estimating Size Before Calling JavaMailSender

An application should avoid building and sending messages that are guaranteed to violate policy. You can check:

- Single-attachment limit.
- Total raw attachment bytes limit.
- Number of attachments.
- Estimated size after MIME encoding.
- Maximum size allowed by the provider.
- Size of HTML content and inline resources.

Example of a utility estimating Base64 overhead with lines up to 76 characters:

```java
public final class MimeSizeEstimate {

    private MimeSizeEstimate() {}

    public static long base64MimeBytes(long rawBytes) {
        if (rawBytes < 0) {
            throw new IllegalArgumentException(
                    "rawBytes must be non-negative");
        }

        // ceil(rawBytes / 3), without adding 2 to rawBytes
        // to avoid overflow on large values.
        long groups = rawBytes / 3;
        if (rawBytes % 3 != 0) {
            groups = Math.addExact(groups, 1);
        }

        long encodedChars = Math.multiplyExact(groups, 4);

        // ceil(encodedChars / 76)
        long lines = encodedChars / 76;
        if (encodedChars % 76 != 0) {
            lines = Math.addExact(lines, 1);
        }

        long lineEndings = Math.multiplyExact(lines, 2);
        return Math.addExact(encodedChars, lineEndings);
    }

    public static long estimateAttachments(
            Collection<Long> fileSizes
    ) {
        long total = 0;
        for (long size : fileSizes) {
            total = Math.addExact(
                    total,
                    base64MimeBytes(size)
            );
        }
        return total;
    }
}
```

This value **estimates the Base64 attachment content with one CRLF per line**. It does not include headers, MIME boundaries, text/HTML, other parts, or SMTP framing. For messages with multiple files, each part has its own overhead. For files sent using a different transfer encoding, an appropriate model is needed rather than applying Base64 to every part.

### Preflight Example for Files on Disk

```java
long pdfBytes = Files.size(pdfPath);
long logoBytes = Files.size(logoPath);

long encodedAttachmentEstimate =
        MimeSizeEstimate.estimateAttachments(
                List.of(pdfBytes, logoBytes)
        );

long estimatedMessageBytes = Math.addExact(
        encodedAttachmentEstimate,
        configuredOverheadReserveBytes
);

if (estimatedMessageBytes > maxConfiguredMessageBytes) {
    throw new MailPayloadTooLargeException(
            "Estimated MIME message exceeds policy limit"
    );
}
```

`configuredOverheadReserveBytes` and `maxConfiguredMessageBytes` are **application-defined** values; `MailPayloadTooLargeException` is also an illustrative domain exception. There is no fixed MIME reserve number that is accurate for every email.

A large message close to the limit should have handling options before creating attachments:

1. Notify or apply a rejection policy.
2. Switch to sending an authorized link if the product allows it.
3. Condense/change the document format if it does not alter business semantics.
4. Split into multiple notifications if policy permits and recipients understand it.

**Do not automatically split a file across multiple emails** if recipients are not informed or if splitting breaks the meaning of the document.

## 18. Measuring Actual Serialized MIME Size

An application can measure the serialized size of a `MimeMessage` in tests, without having to keep a full raw dump in memory just to count bytes.

An `OutputStream` that counts bytes written:

```java
import java.io.IOException;
import java.io.OutputStream;

public final class CountingOutputStream extends OutputStream {

    private long count;

    @Override
    public void write(int value) throws IOException {
        count = Math.addExact(count, 1);
    }

    @Override
    public void write(byte[] bytes, int offset, int length)
            throws IOException {
        if (bytes == null) {
            throw new NullPointerException("bytes");
        }
        if (offset < 0 || length < 0
                || offset > bytes.length - length) {
            throw new IndexOutOfBoundsException();
        }
        count = Math.addExact(count, length);
    }

    public long count() {
        return count;
    }
}
```

Measuring with **dummy fixture** data:

```java
MimeMessage message = buildTestMessage();
message.saveChanges();

CountingOutputStream counting = new CountingOutputStream();
message.writeTo(counting);

long actualSerializedMimeBytes = counting.count();
System.out.println(
        "Serialized test MIME bytes: "
                + actualSerializedMimeBytes
);
```

`buildTestMessage()` is application-provided test message builder code. This approach avoids a large `ByteArrayOutputStream`, however:

- It **still has to read attachments and encode MIME**, consuming CPU/I/O.
- It may touch the resource and generate/update headers.
- It does not prove the server will accept the message.
- It does not include all SMTP envelope bytes, commands, TLS framing, or relay-side modifications.
- If called before a real send, it may cause attachments to be read **an extra time**.

Therefore, **do not serialize every production email twice just to measure its size**. Use estimates on the live sending path and sample raw serialized sizes in tests/benchmarks.

## 19. Limits from SMTP Servers and Providers

Providers may limit:

- Maximum message size after encoding.
- Number of recipients per message.
- Number of messages per connection or per time window.
- Number of concurrent SMTP connections.
- Send rate per account, domain, or IP.
- Restricted attachment types/filenames.
- Maximum duration of SMTP connections and transactions.

Some SMTP servers advertise `SIZE` in EHLO; however, **actual limit enforcement and responses are decided by the server**. The application must still handle send errors defensively.

For example:

```text
S: 250-SIZE 26214400
S: 250 8BITMIME
```

The number in this example is an illustrative capability byte count, **not a universal limit of Spring Mail or SMTP**. Before sending the message into `DATA`, the transport/provider may reject based on its known or computed size limit. Even after receiving the data, the server can still reject due to policy.

### Do Not Rely on Client Estimates as Delivery Guarantees

If an estimate is 24.9 MiB and the provider states "25 MB", it can still exceed the limit because:

- MB differs from MiB.
- MIME headers/boundaries have not been counted.
- HTML and inline images have not been added.
- The message gets transformed or has headers added.
- The provider computes size using its own policy.

It is better to pick an **application threshold lower than the provider threshold**, measure with test data, and handle errors returned by the server. The specific safety margin must be decided by business/provider requirements.

## 20. How Much CPU Does Base64 Cost?

To encode a binary file, the encoder must read the input bytes and produce the Base64 representation. CPU cost generally scales with the data volume:

\[
\text{Encode work} \propto \text{attachment bytes}.
\]

In addition to encoding itself, there are:

- Reading from filesystem/object storage.
- Writing encoded bytes to the stream.
- Copying through buffers.
- Formatting line endings and MIME boundaries.
- TLS encryption when using SMTP/TLS.
- Operating system/network stack overhead.

Do not cite a figure like "Base64 always takes 5 ms/MB" without measuring on the actual hardware, JDK version, and real data. On one machine, encoding CPU may be negligible compared to the network. On a system sending thousands of emails with attachments, cumulative CPU can become a bottleneck.

### CPU-Bound vs. I/O-Bound?

| Symptom | Likely Cause |
| --- | --- |
| High CPU, fast SMTP server response | Rendering/encoding/formatting or PDF generation |
| High disk reads, moderate CPU | Attachment files reside on slow disk |
| Network egress near limit | Large MIME payloads or too many emails |
| Busy workers but low CPU | Waiting on SMTP/socket/storage I/O |
| Increasing GC pauses, high heap usage | Holding many `byte[]` arrays, templates, or buffers |
| Queue growing despite spare CPU/heap | Concurrency limits, SMTP throttling, or locks |

Metrics must be examined together rather than concluding a root cause from a single metric.

## 21. Calculating Total Bandwidth of an Email Campaign

An email with a 10 MiB source attachment generates about 13.68 MiB of Base64 MIME payload. If sent to 100 recipients as **100 separate messages**, the attachment payload alone is nearly:

```text
13.68 MiB/message x 100 messages
    = 1,368 MiB
    = approx. 1.34 GiB
```

That excludes HTML, headers, other attachments, and protocol overhead. That is why per-recipient individual emails can consume far more bandwidth than a single message sent to multiple recipients.

However, **one message for multiple recipients** has trade-offs:

- To/Cc can expose the recipient list.
- Bcc must be handled properly to preserve privacy.
- One failing recipient can fail the entire message when partial sends are not allowed.
- Per-recipient retries are harder.
- Per-recipient personalized content cannot simply reuse one shared message.
- Per-message recipient count limits still apply.

Do not batch all recipients into a single email just to save bandwidth if doing so corrupts content, compromises privacy, or complicates retry handling.

## 22. Sending One MimeMessage to Many Recipients vs. Many MimeMessages

Comparison:

```text
Option A: one message, multiple recipients
  MIME payload is submitted once in an SMTP transaction
  RCPT TO A
  RCPT TO B
  RCPT TO C
  DATA [MIME]

Option B: multiple separate messages
  RCPT TO A -> DATA [MIME_A]
  RCPT TO B -> DATA [MIME_B]
  RCPT TO C -> DATA [MIME_C]
```

In a single SMTP transaction, `DATA` can be shared across multiple envelope recipients accepted by the server. That **may** save bytes transmitted to the first-hop server. However, when sending separately:

- Content can be personalized.
- It is easy to track `notificationId` and per-recipient errors.
- Other recipients' addresses do not have to be exposed.
- Individual retries carry less risk of duplicates.

A sound architecture does not optimize solely for SMTP bytes, but also accounts for reliability, privacy, and business semantics.

## 23. Does Batch Sending Reduce MIME Overhead?

`JavaMailSender.send(MimeMessage...)` allows sending multiple messages:

```java
MimeMessage first = buildFirstMessage();
MimeMessage second = buildSecondMessage();
MimeMessage third = buildThirdMessage();

mailSender.send(first, second, third);
```

`JavaMailSenderImpl` can reuse the SMTP transport within a single batch call when conditions allow, reducing repeated connection/authentication overhead. However, **each message still needs to serialize its own MIME content**. If all three contain the same 10 MiB attachment, passing them in one `send(...)` array does not automatically eliminate reading/encoding/transmitting the attachment three times.

Other trade-offs:

- One failing message can cause the method to throw `MailSendException` with `failedMessages`.
- Some messages in the batch may already have been sent before the exception occurred.
- Retrying the entire batch risks duplicates.
- Holding multiple `MimeMessage` objects simultaneously can increase heap usage if they reference large byte arrays.
- Server connection and rate limits still apply.

Batching is suitable for reducing protocol overhead when helpful, but it must be combined with per-message tracking and size/memory limits.

## 24. Do Not Cache a Whole MimeMessage to Save CPU

A tempting idea when sending many emails with the same template is to cache a built `MimeMessage` and just swap the recipient:

```java
MimeMessage shared = composeCommonMessage();

for (String recipient : recipients) {
    shared.setRecipients(
            Message.RecipientType.TO,
            recipient
    );
    sender.send(shared);
}
```

This pattern is error-prone:

- `MimeMessage` is a mutable object.
- Headers such as `Message-ID` and recipients can be altered.
- Concurrent tasks can race on the same instance.
- `Bcc`/`To` can be mixed up between two recipients.
- Personalized content and private tokens can leak into another email.
- Retries and per-recipient statuses become hard to correlate.

**Reuse parsed/cached templates**, valid logo/fixture sources, configuration, and appropriate immutable data; but create a **separate MimeMessage for each notification** whenever content or recipients differ. Caching an outbound MIME object is not a safe default optimization.

## 25. Template Performance and MIME Performance Are Two Separate Concerns

An HTML email may go through:

```text
Load template
   |
   v
Parse / cache template representation
   |
   v
Render HTML with model
   |
   v
Build MimeMessage
   |
   v
Encode and send MIME parts
```

If the system spends most of its time before calling `MimeMessageHelper`, replacing `ByteArrayResource` with `FileSystemResource` may not noticeably improve latency. If most of the time is spent waiting on the SMTP socket, optimizing Thymeleaf expressions may likewise make no visible difference.

### Optimizing at the Right Layer

- Load/parse templates with caching as designed by the template engine.
- Do not re-fetch logo resources over the network for every email when a suitable local/cached source exists.
- Query the database only for the fields needed for the notification.
- Prepare immutable DTOs; do not pass lazy-loaded JPA entities to workers.
- Render once per notification/attempt when appropriate.
- Build the `MimeMessage` after the final recipients and content are known.
- Do not render/encode attachments that policy already knows will exceed limits.

**Do not cache HTML already populated with a user's name, token, or private details** and reuse it for another recipient. Caching template structure is different from caching personalized render output.

## 26. Concurrent Workers and Memory Pressure

If there are `W` workers and each worker holds an average of `M` MiB of attachments in memory, that dataset alone can reach:

\[
\text{Heap attachment working set}\approx W\times M.
\]

For example:

| Concurrent Workers | Attachment Held in Heap per Worker | Total Source Arrays, Excluding Overhead |
| ---: | ---: | ---: |
| 2 | 10 MiB | 20 MiB |
| 8 | 10 MiB | 80 MiB |
| 16 | 20 MiB | 320 MiB |
| 32 | 20 MiB | 640 MiB |

This is an extremely simplified estimate, **not an exact prediction of RSS/JVM heap**. A single worker may hold multiple copies of a file, template objects, PDF buffers, and library memory. Furthermore, queues can also hold references to unprocessed `byte[]` arrays.

### A Queue Holding DTOs vs. a Queue Holding byte[]

Compare:

```java
record MailTaskA(
        UUID notificationId,
        String recipient,
        byte[] attachmentBytes
) {}
```

with:

```java
record MailTaskB(
        UUID notificationId,
        String recipient,
        String attachmentStorageKey
) {}
```

Suppose the queue holds 1,000 tasks, and each task A carries an independent 10 MiB array. Total referenced attachments can approach **10,000 MiB (about 9.77 GiB)**, far exceeding many applications' heaps. A queue of task B holds only metadata and a storage key, though the worker must fetch the attachment at execution time and handle cases where the source is missing or changed.

**Do not put large byte arrays into an unbounded executor queue.** Separate durable job metadata from payloads, bound queues/concurrency, and load files only when it is actually their turn to be processed.

## 27. Configuring a Dedicated Executor for Mail Workloads

Spring example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.ThreadPoolExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfig {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
```

The numbers `2/4/20` are illustrative values, **not a universal optimal configuration**. For small attachments, the bottleneck may be the SMTP provider; for large PDFs, disk/heap/bandwidth may be more constraining.

### Why Not Increase the Pool Indefinitely?

Each additional worker can:

- Read files.
- Serialize/Base64-encode.
- Open and hold an SMTP connection.
- Hold buffers and network sockets.
- Contend for bandwidth with other workers.
- Trigger server throttling or `421/4xx` responses.

Increasing workers from 4 to 40 when the provider only allows 5 concurrent connections may not increase throughput proportionally, and instead only increases errors, retries, and memory pressure.

### When the Queue Is Full

`AbortPolicy` throws an error when the executor cannot accept more tasks. This is better than silently dropping mail, provided the application can **handle the rejection**.

`CallerRunsPolicy` can cause the task to execute on the calling thread under overload. If the calling thread is handling an HTTP request or holding an open transaction, the impact on latency and transaction boundaries can be severe. Do not use this policy mechanically as "automatic backpressure."

`DiscardPolicy` or `DiscardOldestPolicy` can lose tasks if there is no durable job record. For business emails, weigh the consequences of losing notifications before choosing them.

## 28. Using an Outbox When Send Requests Must Not Be Lost

An in-memory executor queue is not a durable queue. If the process restarts, unexecuted tasks can be lost. For critical emails, a transactional outbox can be used:

```text
Business transaction
    |
    +-- UPDATE order
    +-- INSERT mail_notification(PENDING,
    |       templateKey, recipientId, storageKey)
    |
    v
COMMIT
    |
    v
Mail worker claim notification
    |
    v
Load/render/build MIME on demand
    |
    v
SMTP submit (without holding DB TX long)
    |
    v
Update outcome in separate short TX
```

For large attachments, **do not stuff Base64 blobs into the outbox row** just to simplify queuing if doing so bloats the database, redo/WAL logs, backups, and network traffic. You can store metadata and a reference to durable object storage.

However, referencing external storage has two requirements:

1. The content must still exist and remain accessible when the worker runs, even after restarts.
2. The content must match the exact version approved at the time of the business event; do not arbitrarily read a modified version of the file.

If the source file is created alongside the business transaction, you must design the file creation/saving order and handle cases where the DB rolls back after the object upload succeeded (or vice versa). Object storage does not automatically participate in ACID database transactions.

## 29. Do Not Hold a Database Transaction Across Long SMTP Sends

An anti-pattern:

```java
@Transactional
public void sendInvoice(UUID notificationId) {
    MailNotification notification =
            repository.findById(notificationId).orElseThrow();

    MimeMessage message = composeWithLargeAttachment(notification);
    javaMailSender.send(message); // Network I/O inside a DB transaction.

    notification.markSubmitted();
}
```

With large attachments, this method can hold a JDBC connection and locks for a long time while reading files, Base64-encoding, sending over the network, and waiting on SMTP.

Split it into:

1. **Short claim transaction** to pick up the notification.
2. **Build/encode/send SMTP** outside the DB transaction.
3. **Short outcome transaction** to record `SUBMITTED`, `RETRY_WAIT`, `FAILED`, or `UNKNOWN`.

SMTP does not roll back together with the database. If the server already accepted the message and the worker crashes before updating status, a retry can cause duplicates. An outbox guarantees send requests are not lost, but does not provide exactly-once SMTP delivery.

## 30. Latency and Bandwidth: An Estimation Model

If a message has `S` serialized MIME bytes and the connection achieves an effective application throughput of `R` bytes/second, the **approximate minimum** data transfer time is:

\[
T_{\text{transfer}}\approx\frac{S}{R}.
\]

Total send time:

\[
T_{\text{send}}\approx
T_{\text{connect/auth}}
+T_{\text{read/encode}}
+T_{\text{transfer}}
+T_{\text{server response}}.
\]

These phases can overlap because serialization and network streaming can happen sequentially per buffer or in a pipeline. The formula is only for **separating sources of latency**, not necessarily summing to the exact millisecond.

### Illustrative Example

An email has about 20 MiB of serialized MIME. If measured effective throughput is 2 MiB/second, the `DATA` transfer portion alone can take around 10 seconds, excluding connection setup, reading sources, encoding, and the server response.

With a pool of workers sending concurrently over a single constrained uplink, each worker may receive a smaller share of bandwidth. Adding more workers does not create additional physical bandwidth.

## 31. SMTP Timeouts Must Match Heavy Workloads

In Spring Boot:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 30000
      "[mail.smtp.writetimeout]": 30000
```

This is an example configuration; durations are in milliseconds. They have different scopes:

| Property | Meaning |
| --- | --- |
| `mail.smtp.connectiontimeout` | Wait limit for establishing connection |
| `mail.smtp.timeout` | Wait limit for reading data/responses from the socket |
| `mail.smtp.writetimeout` | Wait limit for writing data to the socket |

For large attachments, `writetimeout` deserves special attention; a timeout that is too short for the network/server characteristics can cut off transmission mid-flight. However, increasing timeouts indefinitely also ties up workers for a long time, grows queues, and delays failure detection.

**A timeout after SMTP DATA may have already reached the server creates an ambiguous outcome.** Do not automatically retry the entire message without considering duplicate risk and proof of acceptance.

## 32. Backpressure by Size, Not Just Task Count

Two tasks can differ dramatically:

```text
Task A: 20 KiB HTML, no attachments
Task B: 3 PDFs x 20 MiB
```

A pool allowing 10 concurrent tasks may be fine if all tasks are A, yet overload disk/network/heap if all tasks are B. Limiting only the task count does not capture the full cost.

You can use:

- Bounded queues.
- Separate worker classes for large vs. small emails.
- A semaphore to limit how many large attachments are encoding concurrently.
- Rate limits by bytes/second or provider quota.
- Queues with priority/fairness so very large emails do not monopolize all workers.
- Admission control before generating files and MIME.

### Example Semaphore for Large-Attachment Tasks

```java
public final class LargeMailGate {

    private final Semaphore permits = new Semaphore(2);

    public void runLargeMail(Runnable action)
            throws InterruptedException {

        permits.acquire();
        try {
            action.run();
        } finally {
            permits.release();
        }
    }
}
```

This enforces a limit of **2 concurrent large jobs within one process**, not a cluster-wide quota. If multiple instances run, coordinate with provider limits and job distribution mechanisms; a per-instance local semaphore does not automatically create a shared rate limit.

Do not hold a DB transaction or HTTP request open for long while waiting for a permit. Admission/scheduling should happen at the worker level, with send requests stored in a queue/outbox under a clear policy.

## 33. When Source Files Change Between Compose and Send

A `FileSystemResource` or remote `InputStreamSource` typically references data read **on demand**. This helps memory, but introduces a consistency problem:

```text
T0  Worker creates MimeMessage, attaches FileSystemResource(file.pdf)
T1  Another process overwrites file.pdf
T2  JavaMailSender starts serializing
T3  Email receives the new content instead of T0 content
```

Or the file is deleted at T1 and sending fails at T2.

Solutions:

- Use immutable/unique file paths per notification.
- For object storage, reference a version ID rather than a mutable key that can be overwritten.
- Keep the source alive until the attempt completes and in accordance with the retry policy.
- Use checksums/digests when data-authority consistency checks are required.
- Do not try to share a temp file with the same name across multiple workers.

**Streaming does not eliminate the need for a logical snapshot of data.** For invoices or legal documents, the bytes must match the confirmed event. If every retry regenerates a PDF from changing live data, the recipient may receive different content under the same notification ID.

## 34. Cleaning Up Temporary Files at the Right Time

When attachments are created on disk:

```text
Generate file
     |
     v
Persist reference / enqueue
     |
     v
Worker open stream and submit
     |
     v
Record outcome
     |
     +-- success -> retention policy -> cleanup
     +-- retry   -> keep file/source long enough
     +-- fail    -> cleanup per policy
     +-- unknown -> do not delete yet if reconciliation is still needed
```

A temp file can be orphaned if the process crashes before `finally`. Therefore, cleanup should also include a periodic metadata-driven sweep rather than relying solely on a `finally` block inside a single request.

Operational rules:

1. Unique file path per notification/attempt.
2. Restricted filesystem permissions to prevent other users from reading the data.
3. Never use a raw unvalidated filename received directly from a user as a path.
4. Enforce disk quotas and alerts when nearing capacity.
5. Configure TTL/garbage collection aligned with notification states.
6. Have a recovery plan when a worker restarts or storage no longer holds the file.
7. Do not log paths containing sensitive IDs or private filenames into public logs.

If the system stores documents in durable object storage, local temp files may not be needed; however, account for latency and how many times the object is downloaded during serialization.

## 35. Accurately Observing the Cost of Each Step

A single `mail_send_duration` metric makes it hard to tell where a performance issue lies. Split it out:

| Metric | Unit | Purpose |
| --- | --- | --- |
| `mail_render_duration` | ms | Template cost |
| `mail_attachment_generation_duration` | ms | PDF/CSV generation |
| `mail_compose_duration` | ms | Attaching MIME parts and headers |
| `mail_serialize_duration` | ms | Sampled in tests/benchmarks |
| `mail_smtp_submit_duration` | ms | Duration of `JavaMailSender.send` |
| `mail_attachment_source_bytes` | bytes | Total source file size |
| `mail_estimated_mime_bytes` | bytes | Upper/approx estimate before send |
| `mail_attachment_count` | count | Number of attachments/notification |
| `mail_queue_depth` | count | Pending tasks |
| `mail_inflight_tasks` | count | Currently running tasks |
| `mail_submission_failure_total` | count | Send failures by category |
| `mail_unknown_outcome_total` | count | Ambiguous SMTP outcomes |
| `mail_outbox_oldest_age` | seconds | Age of oldest pending task |

`mail_smtp_submit_duration` may include **MIME serialization, attachment reads, and network**. Do not label it "network time" unless those layers are instrumented separately.

### Metric Labels That Should Be Bounded

You can group by:

- Mail class: `transactional`, `bulk`.
- Attachment size bucket: `0`, `<1MiB`, `1-10MiB`, `>10MiB`.
- Outcome: `submitted`, `failed`, `unknown`.
- Controlled SMTP provider alias or route.

Never put `recipientEmail`, `notificationId`, `subject`, real filenames, or URL tokens into metric labels. Those fields both create privacy risks and cause high cardinality.

## 36. Using Logging/Tracing Without Recording Sensitive Data

An event log sufficient for investigation:

```text
event=mail_submission
notificationId=N-361-A
mailClass=transactional
attachmentCount=2
sourceBytesBucket=10-20MiB
estimatedMimeBytesBucket=20-30MiB
composeDurationMs=12
smtpSubmitDurationMs=8450
attempt=1
outcome=SUBMITTED
```

Do not log:

```java
logger.info("Message={}", mimeMessage);
message.writeTo(System.out);
```

Raw MIME can contain names, email addresses, Bcc, reset tokens, HTML, and attachments. If raw MIME is needed to investigate byte-level bugs, prefer dummy fixtures in tests; for production there must be a dedicated process covering scope, approval, encryption, access, and retention period.

File sizes, storage paths, and MIME types can also reveal business details; consider bucketed values and internal identifiers when exporting to dashboards.

## 37. Benchmarking Properly: Separate CPU, I/O, and SMTP

A useful benchmark must clearly define the scope being measured:

**Benchmark A — Composer**

- Create `MimeMessage` and attach headers, text, and attachment resources.
- Do not serialize or send over SMTP.
- Measure object allocation, CPU time, and latency.
- Conclusions apply only to object construction cost.

**Benchmark B — MIME serialization**

- Use dummy fixtures with fixed-size attachments.
- Call `message.writeTo(countingOutputStream)`.
- Measure duration, CPU, output byte count, and source reads.
- Do not use SMTP; separate from network bandwidth.

**Benchmark C — SMTP submit to a local server**

- Send messages via `JavaMailSenderImpl` to an SMTP test server.
- Measure total latency from the sender and bytes received by the server.
- Avoid dependencies on production providers.
- Can compare small/large payloads and message counts.

**Benchmark D — End-to-end workload**

- Create notifications, render, load files, and send to a rate-limited SMTP sandbox.
- Measure queue lag, throughput, CPU, heap/GC, disk/network, and errors.
- Use test data and appropriate quotas/permissions.

Results A, B, C, and D can differ vastly. Running only one measurement and blaming everything on "Base64 is slow" leads to unsupported conclusions.

## 38. Designing a Performance Measurement Matrix

| Scenario | Attachment | Resource | Concurrency | Target |
| --- | --- | --- | ---: | --- |
| S01 | None | — | 1 | Text/HTML baseline |
| S02 | 1 KiB | ByteArrayResource | 1 | Part/header overhead |
| S03 | 1 MiB | ByteArrayResource | 1 | Low-scale CPU/heap |
| S04 | 10 MiB | ByteArrayResource | 1 | Large Base64 payload |
| S05 | 10 MiB | FileSystemResource | 1 | Compare heap vs. disk I/O |
| S06 | 10 MiB | FileSystemResource | 8 | Concurrent read/encode/send |
| S07 | 2 x 10 MiB | FileSystemResource | 4 | Multiple attachments |
| S08 | 20 KiB inline image | ClassPathResource | 50 | Repeated resource cost |
| S09 | 10 MiB remote | Fresh InputStreamSource | 4 | Object-storage fetch cost |
| S10 | 10 MiB | Mixed attachments | Queue burst | Backpressure and p95/p99 |

Measure at least:

- Throughput: messages/second and MIME bytes/second.
- Latency: p50, p95, p99 of render/submit.
- Heap used/peak, allocation rate, and GC pauses.
- CPU utilization.
- Disk read throughput and network egress.
- Queue depth, rejections, and retry counts.
- Timeout errors, rate limits, and unknown outcomes.

### Conditions for Meaningful Comparisons

- Warm up the JVM/JIT before capturing results.
- Use the same JDK, libraries, hardware, and provider/test server settings.
- Run multiple iterations; do not draw conclusions from a single cold run.
- Keep fixture sizes and contents equivalent.
- Measure whether resources sit in the OS page cache or require disk reads.
- Never allow benchmarks to send emails to real users.
- Distinguish sustained steady-state load from a short burst.

For Java microbenchmarks, JMH is a better tool than a hand-written `System.nanoTime()` loop lacking warmup and forking. However, benchmarking the full SMTP pipeline requires additional integration/load tests, because microbenchmarks do not reflect server/network behavior.

## 39. Testing Encoding Cost with Synthetic Random Attachments

Do not use real documents for benchmarking. You can generate synthetic binary fixtures of a fixed size:

```java
byte[] bytes = new byte[1024 * 1024];
new SecureRandom().nextBytes(bytes);

MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("perf@example.org");
helper.setTo("sink@example.net");
helper.setSubject("Attachment size test");
helper.setText("Synthetic message.");
helper.addAttachment(
        "synthetic.bin",
        new ByteArrayResource(bytes),
        "application/octet-stream"
);

message.saveChanges();
CountingOutputStream output = new CountingOutputStream();
message.writeTo(output);

long mimeBytes = output.count();
```

`SecureRandom` in the example generates dummy bytes. For pure performance benchmarks, random generation must happen **outside the serialization timing section**, otherwise results include the cost of random generation.

To measure memory for `FileSystemResource`, create fixture files of matching sizes before the benchmark and reuse the same data across runs. Do not time temporary file creation together with `writeTo` unless the explicit goal is end-to-end measurement.

## 40. Testing Base64 Size with Boundary Values

Small values are easy to verify:

| Source Bytes `N` | Base64 Chars `4×ceil(N/3)` | Notes |
| ---: | ---: | --- |
| 0 | 0 | No content |
| 1 | 4 | With padding |
| 2 | 4 | With padding |
| 3 | 4 | One complete group |
| 4 | 8 | Two groups, last group padded |
| 57 | 76 | One full MIME line |
| 58 | 80 | Requires an extra line |
| 114 | 152 | Two 76-character lines |

In tests, you can assert the **estimate** rather than trying to match exact SMTP envelope byte counts:

```java
assertEquals(
        6L,
        MimeSizeEstimate.base64MimeBytes(1)
);

assertEquals(
        78L,
        MimeSizeEstimate.base64MimeBytes(57)
);

assertEquals(
        84L,
        MimeSizeEstimate.base64MimeBytes(58)
);
```

For 1 byte, the estimate counts 4 characters and 2 CRLF bytes; a raw Base64 encoder may output only 4 characters when no trailing CRLF is needed. For 58 bytes, 80 Base64 characters are split across two lines, so the estimate is 84 bytes.

**Do not treat the estimation formula as an absolute byte-exact check for every implementation.** Compare against `writeTo(...)` with fixtures on the actual library in use if you want to verify a specific size model.

## 41. Unit Tests and Integration Tests Complement Each Other

**Unit tests** can verify:

- The composer attaches files with the right MIME type and disposition.
- `FileSystemResource` is referenced instead of allocating a `byte[]` if required by the architecture.
- Dummy files have the exact bytes read through `MimeMessage` after serialization.
- Size estimates and rejection policies when exceeding quotas.
- Retry policies classify timeouts/oversize/4xx/5xx clearly.

**Integration tests** can verify:

- Messages sent to an SMTP test server serialize successfully.
- The server rejects oversized messages in simulated scenarios.
- SMTP timeouts and errors are recorded properly by the application.
- Multiple attachments in `multipart/mixed` are not lost.
- Queues apply backpressure and workers are not spawned unboundedly.

**Load tests** reveal throughput, memory/GC, and latency under many concurrent notifications. Never use a single unit test `assertDoesNotThrow(sender.send(...))` to conclude a system handles heavy load.

## 42. Common Issues and Root Causes

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Message exceeds limit even though source file is not too large | Base64 + MIME overhead | Estimate full message and add reserve |
| Heap spikes when queue has many tasks | Tasks hold large `byte[]` arrays | Queue metadata/storage keys; limit concurrency |
| Temp file deleted before sending | Resource is only read during serialization | Manage file lifecycle until end of attempt |
| Attachment empty on second send | Source returns an already-consumed stream | Fresh `InputStream` each time; avoid single-use |
| High CPU when sending large files | PDF generation/encoding/serialization/TLS | Measure each layer separately; optimize actual bottleneck |
| SMTP workers busy but CPU low | Waiting on network/provider/storage | Check latency, timeouts, provider quotas |
| Adding workers slows down sending | Throttling, disk/network contention | Limit concurrency; add backpressure |
| `FileSystemResource` saves little heap | Template/PDF builder still holds large buffers | Optimize the whole pipeline and measure allocations |
| `send(messages)` still consumes many bytes | Each message serializes its own attachment | Evaluate payload and recipient semantics |
| Retrying email creates duplicates | Ambiguous timeout/partial SMTP outcome | Tracking, `UNKNOWN`, provider reconciliation |
| Byte estimate differs from SMTP size | Headers, boundaries, CRLF, framing | Use estimate with reserve and test serialization |
| Benchmark varies between runs | JIT, page cache, GC, network | Warmup, repeat, isolate measured variables |
| Raw MIME leaks in logs | Dumping for performance debugging | Metrics/summaries only; dummy test fixtures |
| Outbox grows too large | Storing blobs/Base64 directly in DB rows | Metadata + durable storage if appropriate |
| Remote file changes after compose | Mutable source | Versioned/immutable objects |

## 43. Pre-Deployment Optimization Checklist

### Size and Encoding

- [ ] Enforce a source-byte limit per attachment.
- [ ] Enforce limits on total attachments and MIME part count.
- [ ] Calculate Base64 + folding + header/body reserve estimates.
- [ ] Distinguish MB vs. MiB when checking against provider limits.
- [ ] Handle SMTP rejections caused by message size.

### Memory and Data Sources

- [ ] Never place large `byte[]` arrays into unbounded queues.
- [ ] Use appropriate resources: small byte arrays or re-readable files/streams.
- [ ] Files/objects are not deleted or overwritten before sending finishes.
- [ ] Enforce quotas for temp disk and object storage.
- [ ] Implement cleanup/retention when tasks succeed or fail.
- [ ] Have restart/retry handling for critical notifications.

### Execution and Throughput

- [ ] Limit workers/connections according to the SMTP provider.
- [ ] Bound queues and define backpressure/rejection policies.
- [ ] Never hold DB transactions across long SMTP I/O.
- [ ] Configure appropriate connect/read/write timeouts.
- [ ] Never blindly retry when the SMTP outcome is `UNKNOWN`.
- [ ] Consider size-based scheduling for heavy jobs.

### Observability and Security

- [ ] Separate render/compose/serialize/send timings.
- [ ] Measure attachment bytes, MIME estimates, queue depth, and GC.
- [ ] Use dummy fixtures in benchmarks.
- [ ] Never log raw MIME, recipients, Bcc, tokens, or attachments.
- [ ] Configure alerts when queue lag, oversize rejections, or SMTP throttling spike.

## 44. Self-Practice Scenarios

### Scenario A — 25 MiB PDF and a 25 MB Provider Limit

The application checks `Files.size(pdfPath)`, sees 25 MiB, and decides to send.

**Question:** Why might it fail?

**Hint:** Base64 folding can expand the PDF part to roughly 34.2 MiB, and MIME headers/body make it even larger. In addition, 25 MB and 25 MiB are not equal. Preflight size checks and handling server rejections are required.

### Scenario B — Queue Holding 500 Files of 10 MiB as byte[]

Tasks are created directly inside HTTP requests and pushed into an executor queue.

**Question:** What is the consequence?

**Hint:** The file arrays alone can retain roughly 5,000 MiB of heap, excluding other objects. Store notification metadata/storage keys instead, use bounded queues, and load files when the worker executes.

### Scenario C — Using FileSystemResource, but the File Is Deleted Too Early

A controller creates a temp file, calls an `@Async` method, and immediately deletes the file.

**Question:** Why might the worker fail?

**Hint:** The attachment may only be read during serialization/sending on the worker. The resource must stay intact until the task has actually finished reading it.

### Scenario D — Sending the Same PDF to 10,000 Users

The system creates 10,000 `MimeMessage` instances, each attaching the same PDF.

**Question:** Is Base64 encoded only once?

**Hint:** You cannot assume that. Each message needs its own serialized MIME and `DATA`; batch sending does not automatically deduplicate attachments across messages. You can consider sharing an immutable file source while never sharing mutable `MimeMessage` instances, and also evaluate privacy/personalization.

### Scenario E — Increasing Workers from 4 to 40 Lowers Throughput

**Hint:** The provider may be throttling, socket/network/disk contention increases, more workers hold more buffers/heap, and retries rise. Measure connections, quotas, queues, GC, network, and SMTP responses.

### Scenario F — Attachment Fails on Retry

The first send succeeds, but the second attempt produces an empty file because `InputStreamSource` returns the same stream.

**Hint:** The source must open a new stream each time. Use `ByteArrayResource` for small data or `FileSystemResource`/re-readable sources for stable files.

### Scenario G — Timeout After DATA

A worker has sent almost all of a large email and receives no final response.

**Hint:** You cannot assume the server did not receive it; mark `UNKNOWN`, reconcile with the provider when possible, and avoid blindly re-sending the entire message immediately.

### Scenario H — Turning Invoices into Public URLs

The engineering team wants to drop attachments to save bandwidth.

**Hint:** Links can reduce SMTP size, but must enforce authentication/authorization, TTL, auditing, and revocation. Never turn sensitive documents into public object URLs, especially when law/business rules require storing the file with the email.

## 45. Key Principles to Remember

1. **Creating MIME objects, serializing MIME, and sending over SMTP are separate phases.** Do not lump all costs into one operation.
2. **Base64 increases content bytes by about 33.3%;** MIME line folding typically increases large file payloads by about **36.8%** before headers/boundaries.
3. **ByteArrayResource fits data already in memory; FileSystemResource can avoid holding the entire file in the heap.**
4. **InputStreamSource must open a fresh stream on demand;** single-read streams break retries and serialization.
5. **Streaming does not mean zero RAM:** MIME trees, templates, network/TLS buffers, and libraries still allocate memory.
6. **Preflight sizing must account for encoded bytes and reserve**, not just `Files.size()`.
7. **Do not keep temp files shorter than the send lifecycle**, and do not let mutable files change between compose and send.
8. **Increasing concurrency does not guarantee higher throughput**, especially under SMTP/network or heap/GC limits.
9. **Batching can reduce connection overhead, but does not automatically shrink per-message attachment bytes.**
10. **An outbox makes send requests durable; it does not turn SMTP into exactly-once delivery.**
11. **Do not log raw MIME/attachments to measure performance**; use metadata and dummy fixtures.
12. **Benchmark each layer and measure the overall workload** before choosing an optimization.

## 46. Conclusion

MIME creation and attachment encoding overhead in Spring Framework Mail is not just the execution time of `MimeMessageHelper`. When sending emails with images, PDFs, and multiple attachments, the application must manage MIME parts, read data sources, Base64-encode and fold lines, transmit more bytes than the original files, and keep workers occupied throughout SMTP submission. For large files, **Base64 and MIME folding can increase attachment transmission size by about 36.8%** before counting other headers and body parts.

To implement this effectively, measure render, compose, serialize, and send separately; use `ByteArrayResource` when small data truly needs to stay in memory, and consider files or re-readable streams for large data. Before sending, enforce policies checking attachment count/size and estimate encoded MIME size with a reserve margin. Under high task volume, bound concurrency and queues according to real resources, manage files/object storage stably, avoid deleting sources prematurely, and never hold database transactions during SMTP file transfers.

Most importantly, performance optimizations **must not trade off reliability or security**: never reuse mutable messages across recipients, never blindly retry when SMTP outcomes are unknown, never turn sensitive files into public links, and never dump raw MIME into logs. Combining appropriate resources, preflight policies, observability, and controlled benchmarks keeps attachment-heavy mail systems stable as scale grows.

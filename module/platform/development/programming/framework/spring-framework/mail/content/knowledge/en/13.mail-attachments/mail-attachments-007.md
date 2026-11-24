# File Sizes and Message Limits in Spring Framework Mail

When sending emails with attachments, an application must control two distinct things: **the size of each individual file** and **the size of the entire email after MIME packaging**. An 8 MB PDF does not necessarily produce an 8 MB email. Binary data is typically Base64-encoded, MIME adds headers and boundaries, and the body may contain HTML, plain text, and inline images. Therefore, the final message can be considerably larger than the sum of the original file sizes.

In Spring Framework Mail, `MimeMessageHelper` provides methods such as `addAttachment(...)` to place files into an email. The helper constructs the MIME structure, but **it does not automatically enforce size limits tailored to your SMTP provider, does not replace file-upload validation, and does not guarantee the receiving server will accept the email**. The application must implement a size-control step before sending.

This lesson focuses on measuring and limiting attachments, estimating MIME overhead, handling large files, managing memory, configuring provider-aligned thresholds, and integrating checks into the `JavaMailSender` workflow.

## 1. Distinguishing file size from email size

Suppose an application sends an invoice email consisting of:

- An HTML body of about 90 KB.
- A plain-text body of about 2 KB.
- A 6 MB PDF file.
- A 100 KB inline logo image.
- A 1.5 MB JPEG receipt image.

There are at least three numbers to track:

1. **File size**: the original file size on the filesystem or object storage.
2. **Part size**: the size of each part after being placed into the MIME structure and transfer-encoded.
3. **Message size**: the total size of the serialized MIME message, including headers, body, boundaries, and all attachment/inline parts.

Illustrative diagram:

~~~text
Content sources
  |
  +--> HTML body: 90 KB
  +--> Plain text: 2 KB
  +--> Original PDF: 6 MB
  +--> Inline logo: 100 KB
  +--> Receipt image: 1.5 MB
           |
           v
     MimeMessageHelper
           |
           v
     MIME message
       - message headers
       - multipart boundaries
       - text/plain part
       - text/html part
       - image parts
       - application/pdf part
       - transfer-encoding overhead
           |
           v
       SMTP submission
           |
           v
     SMTP relay / ESP
~~~

If you only sum original file sizes, the application may underestimate the final message. If you only measure HTML, the application misses nearly all attachments. If you only measure the final MIME, the application knows the email is too large but struggles to tell which file caused the issue. A sound workflow measures both individual components and the overall total.

### Types of limits not to confuse

| Limit | Applies to | Control example |
| --- | --- | --- |
| Per-file size | A specific attachment | PDF max 10 MB |
| Total raw file size | All selected files | Total attachments max 15 MB |
| MIME message size | Entire packaged email | Serialized message max per internal budget |
| Attachment count | Number of attachment MIME parts | Max 5 files |
| Recipient count | To/Cc/Bcc or envelope recipients | Per SMTP provider quota |
| HTML size | Markup content | Prevents oversized templates or clipping |
| Provider limits | SMTP/API policies | Message size, attachment size, recipient count |
| Application limits | Business rules and system resources | Quotas per tenant, email type, or user |

These limits must be checked independently. An email can remain below the total message limit yet violate a per-attachment limit; conversely, every individual file may be valid yet together push the message over the threshold.

## 2. Why do attachments make emails larger than the original files?

MIME is the format used to package multiple content types inside an email. A binary attachment is typically transmitted using `Content-Transfer-Encoding: base64`.

Base64 converts every group of 3 input bytes into 4 output characters. The baseline size grows by roughly 4/3, or about 33.3%, before accounting for line breaks and MIME headers.

Estimation formula:

~~~text
base64Length = 4 × ceil(originalBytes / 3)
~~~

For example, a file of 6,000,000 bytes:

~~~text
Base64 length
  = 4 × ceil(6,000,000 / 3)
  = 8,000,000 ASCII characters
~~~

When MIME wraps Base64 data onto lines of bounded length (typically 76 characters), CRLF line endings are added. In addition, each part has its own headers such as `Content-Type`, `Content-Disposition`, `Content-Transfer-Encoding`, separating boundaries, and other metadata.

### Base64 estimation helper

~~~java
public final class AttachmentSizeEstimator {

    private AttachmentSizeEstimator() {}

    public static long base64Length(long originalBytes) {
        if (originalBytes < 0) {
            throw new IllegalArgumentException("Size must not be negative");
        }

        return 4L * ((originalBytes + 2L) / 3L);
    }

    public static long base64WithLineBreaks(long originalBytes) {
        long encodedBytes = base64Length(originalBytes);
        long lineCount = (encodedBytes + 75L) / 76L;

        // Estimate CRLFs between lines, excluding trailing CRLF.
        long crlfBytes = Math.max(0L, lineCount - 1L) * 2L;
        return encodedBytes + crlfBytes;
    }
}
~~~

The example above is an **estimate for a single Base64 part**, not an exact measurement of the entire email. Some text parts may use quoted-printable or 7bit; the library decides transfer encoding based on content and configuration. Do not mechanically apply a 4/3 multiplier to HTML bodies.

### Quick mental estimates

| Original file | Baseline Base64 (approx.) | Meaning |
| ---: | ---: | --- |
| 100 KB | 133.4 KB | Excludes CRLFs and MIME headers |
| 1 MB | 1.34 MB | A single attachment can grow substantially |
| 5 MB | 6.67 MB | Total message also includes body and other parts |
| 10 MB | 13.34 MB | May exceed some common message limits |

This table only illustrates Base64 ratios in decimal MB; actual size depends on MIME serialization. Providers may measure messages in their own way, so do not treat this table as a delivery guarantee.

## 3. Reading file size before creating MimeMessage

For files on the filesystem, use `Files.size(path)`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path invoice = Path.of("/data/invoices/invoice-2026-001.pdf");
long fileBytes = Files.size(invoice);
~~~

`Files.size(...)` reads file metadata without loading the entire content into the heap. This is simple and efficient when the attachment source is a file on disk.

If the file is managed by a Spring `Resource`, you can use `contentLength()` when the resource supports a reliable size:

~~~java
Resource resource = new ClassPathResource("mail/terms.pdf");
long bytes = resource.contentLength();
~~~

However, not every `Resource` knows its length upfront. For some streams or dynamic data sources, `contentLength()` may be unsuitable or require reading the content. When an exact count is needed, you can read the stream using a buffer:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public final class ResourceSizer {

    private ResourceSizer() {}

    public static long count(Resource resource) throws IOException {
        long total = 0L;
        byte[] buffer = new byte[8192];

        try (InputStream input = resource.getInputStream()) {
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
            }
        }

        return total;
    }
}
~~~

Stream counting avoids allocating a byte array as large as the file. However, ensure the resource can open a fresh stream when the sending step begins. Never reuse a single `InputStream` that has already been read to EOF for both preflight and the attachment.

### Keep measurements as long

File sizes can exceed the range of `int`. Use `long` for bytes, running totals, and budgets:

~~~java
long maxAttachmentBytes = 10L * 1024 * 1024;
long totalAttachmentBytes = 0L;

for (Path path : files) {
    totalAttachmentBytes += Files.size(path);
}
~~~

When summing multiple files, consider overflow if data could come from untrusted sources or large counts. Real applications typically cap the file count and per-file size before summing.

## 4. Setting limits per file and for total attachments

Do not rely solely on a total limit. One huge file can strain memory, virus scanning, or timeouts even if the other files are small.

Example policy:

- Maximum 10 MB per attachment.
- Maximum 15 MB total raw files.
- Maximum 5 attachments.
- Only allow PDF, PNG, and JPEG for invoice emails.
- Total MIME message must stay below the provider's configured budget with a safety margin.

These numbers are examples only. Actual quotas must be based on your SMTP provider, email type, and system resources.

### Example validating a file list

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class AttachmentPolicy {

    private final long maxFileBytes;
    private final long maxTotalBytes;
    private final int maxFiles;

    public AttachmentPolicy(
            long maxFileBytes,
            long maxTotalBytes,
            int maxFiles) {
        this.maxFileBytes = maxFileBytes;
        this.maxTotalBytes = maxTotalBytes;
        this.maxFiles = maxFiles;
    }

    public long validate(List<Path> files) throws IOException {
        if (files == null || files.size() > maxFiles) {
            throw new IllegalArgumentException(
                "Too many attachments");
        }

        long total = 0L;

        for (Path path : files) {
            long size = Files.size(path);

            if (size > maxFileBytes) {
                throw new IllegalArgumentException(
                    "An attachment exceeds the per-file limit");
            }

            if (size > maxTotalBytes - total) {
                throw new IllegalArgumentException(
                    "Attachments exceed the total size limit");
            }

            total += size;
        }

        return total;
    }
}
~~~

The condition `size > maxTotalBytes - total` prevents overflowing past the limit before detecting it. However, this is only a size check. Before sending, the application must also verify the file lies in an allowed storage region, its actual content type, and its security scan status.

## 5. Creating an email with attachments using MimeMessageHelper

`SimpleMailMessage` is only for basic text emails. When attachments are needed, use `MimeMessage` with `MimeMessageHelper`.

Example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.File;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailer {

    private final JavaMailSender mailSender;

    public InvoiceMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, File invoice)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");
        helper.setText(
            "Please see your invoice in the attached file.",
            false
        );

        helper.addAttachment(
            invoice.getName(),
            new FileSystemResource(invoice)
        );

        mailSender.send(message);
    }
}
~~~

The `true` parameter in the `MimeMessageHelper` constructor enables multipart, allowing attachments to be added. The helper builds the MIME parts and handles required headers.

The snippet above illustrates attaching a file; production code must check per-file limits, total MIME size, and file policies before calling `send`. Do not wait for the provider to reject the message to discover a user uploaded an oversized file.

### Using Resource instead of File

Spring supports `Resource`:

~~~java
helper.addAttachment(
    "terms-and-conditions.pdf",
    new ClassPathResource("mail/terms-and-conditions.pdf")
);
~~~

Or a file in managed storage:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(invoicePath)
);
~~~

The attachment display name should be controlled separately. Never use a raw filesystem path as the filename sent to the recipient; use only a sanitized filename free of path separators and control characters.

## 6. Measuring the full MIME message before sending

Measuring raw files is useful for checking individual attachments. However, to know how large the constructed message is, serialize the `MimeMessage` after adding all content and attachments.

Jakarta Mail provides `MimeMessage.writeTo(OutputStream)`. You can write to a stream that only counts bytes rather than buffering the whole message into a byte array.

### CountingOutputStream

~~~java
import java.io.OutputStream;

public final class CountingOutputStream extends OutputStream {

    private long count;

    @Override
    public void write(int value) {
        count++;
    }

    @Override
    public void write(byte[] buffer, int offset, int length) {
        if (length < 0) {
            throw new IndexOutOfBoundsException();
        }
        count += length;
    }

    public long getCount() {
        return count;
    }
}
~~~

### Serializer to measure MIME

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;

public final class MimeMessageSizer {

    private MimeMessageSizer() {}

    public static long serializedBytes(MimeMessage message)
            throws MessagingException, IOException {
        message.saveChanges();

        CountingOutputStream output = new CountingOutputStream();
        message.writeTo(output);

        return output.getCount();
    }
}
~~~

Calling `saveChanges()` finalizes the headers and MIME metadata managed by Jakarta Mail prior to serialization.

### Why is this measurement close to the actual message?

It includes elements that individual file measurements omit:

- Message headers.
- Headers of each MIME part.
- Multipart boundaries.
- Plain-text and HTML content.
- Inline images.
- Attachments after transfer encoding.
- Other MIME metadata.

However, this is the size of the **serialized message at the time of measurement**, which does not necessarily equal the exact byte count measured by the SMTP server. SMTP transport also involves framing, DATA termination, dot-stuffing for lines starting with a dot, and potentially added headers. Providers may also apply their own accounting rules.

Therefore, use the serialized size as a preflight estimate with a safety margin; do not treat it as a guarantee that the server will accept the email.

### Be careful with read-once DataSources

`writeTo(...)` may read attachment contents to serialize them. If a `DataSource` uses a single-read stream, the measurement step can consume the stream before `send(...)` runs.

Prefer `FileSystemResource`, `ClassPathResource`, or an `InputStreamSource` capable of opening a fresh stream on each read. Never create a single `InputStream` and return that same stream for every call.

## 7. Complete preflight example before sending

The example below combines raw file limits, file count checks, and serialized MIME measurement:

~~~java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class DocumentMailer {

    private static final long MAX_FILE_BYTES = 10L * 1024 * 1024;
    private static final long MAX_TOTAL_FILE_BYTES = 15L * 1024 * 1024;
    private static final long MAX_MIME_BYTES = 20L * 1024 * 1024;
    private static final int MAX_FILE_COUNT = 5;

    private final JavaMailSender mailSender;

    public DocumentMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String subject,
            String body,
            List<Path> attachments)
            throws IOException, MessagingException {

        validateAttachmentFiles(attachments);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("documents@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(body, false);

        for (Path path : attachments) {
            helper.addAttachment(
                safeDisplayName(path),
                new FileSystemResource(path)
            );
        }

        long mimeBytes = MimeMessageSizer.serializedBytes(message);

        if (mimeBytes > MAX_MIME_BYTES) {
            throw new IllegalArgumentException(
                "The complete email exceeds the configured message budget");
        }

        mailSender.send(message);
    }

    private void validateAttachmentFiles(List<Path> files)
            throws IOException {
        if (files == null || files.size() > MAX_FILE_COUNT) {
            throw new IllegalArgumentException(
                "Attachment count exceeds the configured limit");
        }

        long total = 0L;

        for (Path path : files) {
            if (path == null || !Files.isRegularFile(path)) {
                throw new IllegalArgumentException(
                    "Attachment is not a regular file");
            }

            long size = Files.size(path);

            if (size > MAX_FILE_BYTES) {
                throw new IllegalArgumentException(
                    "An attachment exceeds the per-file limit");
            }

            if (size > MAX_TOTAL_FILE_BYTES - total) {
                throw new IllegalArgumentException(
                    "Attachments exceed the total file size limit");
            }

            total += size;
        }
    }

    private String safeDisplayName(Path path) {
        Path name = path.getFileName();
        return name == null ? "attachment" : name.toString();
    }
}
~~~

The limits in this example are illustrative values. A real application should read them from configuration rather than hard-coding them in the service. `safeDisplayName` is also a simplified example; if the filename comes from a user, normalize and strip control characters, path separators, and invalid names before use.

This example does not yet implement actual MIME type verification, malware scanning, tenant quotas, or file read-permission authorization. Those are necessary steps depending on the attachment source and security requirements.

## 8. SMTP provider message limits

Each SMTP relay or Email Service Provider (ESP) may enforce different limits:

- Total message size.
- Individual attachment size.
- Total attachment size.
- Number of attachments.
- Number of recipients per message.
- Header size or header count.
- Sending rate and concurrent connections.
- Daily/monthly total sending volume.
- Allowed MIME types or file extensions.

There is no single universal limit across all SMTP servers. One provider may limit messages to 10 MB, another to 25 MB, or another threshold; receiving mailbox providers also have their own policies. Read the documentation for **the provider you are using**, check your account settings, and confirm how they measure size.

### SMTP DATA limits and the SIZE extension

SMTP may advertise the `SIZE` extension in its `EHLO` response, indicating the server's declared message size limit. The client/transport may use this information during sending depending on the implementation and library version.

However:

- Not every server advertises `SIZE`.
- The advertised server value may differ from account-level or policy limits.
- A provider may reject based on total message size or additional rules.
- The final receiving server may enforce a lower limit than the outbound relay.
- An email accepted by a relay can still bounce or be rejected at a later hop.

Therefore, the application should maintain its own budget and still handle SMTP replies during actual sending.

### Setting the budget lower than the provider limit

Suppose a provider states a 25 MB decimal message limit. Do not set the application budget to exactly 25 MB, because MIME overhead, added headers, and counting differences can push the message over the limit.

A policy might include a margin, such as an internal 20 MB budget. This is illustrative only; choose values from provider documentation and real measurements.

## 9. Configuring limits by environment and provider

Separate budgets from source code:

~~~yaml
app:
  mail:
    attachments:
      max-file-bytes: 10485760
      max-total-bytes: 15728640
      max-count: 5
    message:
      max-serialized-bytes: 20971520
~~~

Create a configuration class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailAttachmentProperties(
    AttachmentLimits attachments,
    MessageLimits message
) {
    public record AttachmentLimits(
        long maxFileBytes,
        long maxTotalBytes,
        int maxCount
    ) {}

    public record MessageLimits(
        long maxSerializedBytes
    ) {}
}
~~~

Register the configuration using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` as appropriate for your application.

You can use profiles to tune per environment:

- Local/test: small limits to catch errors quickly, SMTP test server.
- Staging: limits close to production and testing provider sandboxes.
- Production: limits aligned with the SMTP/ESP contract, with a safety margin.
- Tenant-specific: separate limits if contracts or account policies differ.

Never let the client send an arbitrary `maxFileBytes` value to decide the actual limit. Thresholds must be server-managed.

## 10. Validating uploaded files before turning them into attachments

If an attachment originates from a user upload, checking before sending the email is only **the second line of defense**. Validate the file right at the upload boundary:

1. Check request size and individual file size.
2. Limit file count and total bytes per user/tenant.
3. Check extensions against a business allowlist.
4. Inspect file signatures/magic bytes or use a content-detection library; do not trust the `Content-Type` sent by the browser.
5. Sanitize filenames to contain no path traversal, CR/LF, or control characters.
6. Store files in a non-executable storage area.
7. Scan for malware per security requirements.
8. Limit time and resources when processing complex archives, PDFs, or images.
9. Allow the email service to attach only files that have passed the required inspection status.

### Do not trust file extensions

A file named `invoice.pdf` is not necessarily a PDF. A sender could rename an executable or other content to `.pdf`. Checking extensions is useful for policy and UX, but actual content verification is still required.

For example, with PDFs, verify the MIME type using a content-inspection library and/or appropriate signatures. Do not rely solely on `Files.probeContentType(path)`, as its results depend on the OS and MIME database configuration.

### Controlling the display name

The attachment filename is display data inside the email `Content-Disposition` header. Before passing a filename to the helper:

- Extract the basename; never send an absolute path.
- Strip CR, LF, and control characters.
- Limit length.
- Prevent filenames from containing internal details like server paths or usernames.
- Use a name understandable to the recipient.

`MimeMessageHelper` has overloads supporting filename encoding, but that does not replace input sanitization.

## 11. Large files, streaming, and memory

Do not read every attachment into `byte[]` just to check its size or send an email:

~~~java
byte[] file = Files.readAllBytes(path);
helper.addAttachment("large.pdf", new ByteArrayResource(file));
~~~

This keeps the entire file on the heap. When multiple workers send large files concurrently, required memory can spike quickly. For instance, 20 workers each loading a 10 MB file already need about 200 MB just for the raw file arrays, before counting Base64, MIME buffers, object overhead, and the rest of the application.

Prefer a resource capable of opening streams:

~~~java
helper.addAttachment(
    "large-report.pdf",
    new FileSystemResource(path)
);
~~~

When using resources/streams, keep in mind:

- The resource must remain present and readable throughout serialization and sending.
- If a preflight step serializes MIME and then sending serializes it again, the resource must be able to open a fresh stream.
- Do not delete temporary files before `send(...)` completes.
- If the file lives on object storage, use a resource adapter with fresh-stream opening and proper timeouts.
- Control concurrent worker count to avoid overloading disk, network, and heap.

Streaming reduces the need to keep the original file in a byte array, though it does not mean the entire sending pipeline is always zero-copy or bufferless. Jakarta Mail and the SMTP transport may still use buffers and perform encoding during serialization.

### Decoupling file processing from the HTTP flow

If a user uploads a file and the application sends the email directly inside the request, the request has to wait for upload, scanning, MIME serialization, and SMTP submission. For large files, consider:

~~~text
HTTP upload
    |
    v
Validate size / type / permission
    |
    v
Store file + metadata
    |
    v
Create notification/outbox record
    |
    v
Return response
    |
    v
Mail worker
    |
    +--> load attachment resource
    +--> recheck size and status
    +--> build MIME message
    +--> preflight serialized size
    +--> JavaMailSender.send(...)
    |
    v
Record attempt / provider result
~~~

The worker can limit concurrency, retry with backoff, and handle errors without holding an HTTP request open for a long time.

## 12. When to send a link instead of an attachment

Not every file needs to be attached directly. For large documents, you can send a download link if the system provides secure access controls.

| Scenario | What to consider |
| --- | --- |
| Small PDF invoice that the recipient needs to save immediately | An attachment may be convenient |
| Report of tens of MB | An authenticated download link is usually more suitable |
| Large photo set | Album/download page or object storage link |
| Document containing personal data | Authenticated link with permission checks and auditing |
| File that needs updates after sending | Link to the current document rather than a fixed attachment |
| File must be archived verbatim with the email | Attachment may be appropriate if within limits |

A secure download link requires:

- HTTPS.
- Server-side access permission checks.
- Properly scoped and time-limited tokens if using signed URLs.
- Avoiding predictable sequential IDs or personal data in the URL.
- Ability to revoke or expire when the document is no longer authorized for download.
- Access logging aligned with privacy policies.
- Avoiding sensitive side effects on a plain GET if link scanners can prefetch it.

A download link is not automatically better than an attachment. If the recipient needs an immutable copy attached to their email record or needs to work offline, an attachment may be the better choice.

## 13. Do attachments and inline images both increase message size?

Yes. Both attachments and inline images are packaged as MIME parts. The primary difference is how they are referenced and displayed:

- Attachments usually have `Content-Disposition: attachment` so email clients display them as downloadable files.
- Inline images usually have a `Content-ID` and are referenced by HTML via `cid:...`, typically inside a `multipart/related` section.
- Both embed file data inside MIME unless using a remote URL.
- Both may require Base64 transfer encoding.

Inline image example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);

helper.setText(
    "View content in the email.",
    "<html><body><img src=\\"cid:logo\\"></body></html>"
);

helper.addInline(
    "logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
~~~

Attachment example:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(invoicePath)
);
~~~

In both cases, when controlling total message size, measure the serialized MIME after all parts have been added.

### Remote image URLs vs. inline images

If HTML contains:

~~~html
<img src="https://static.example.com/banner.jpg" alt="Banner">
~~~

then MIME contains only the markup and URL; the image file is not inside the message. That reduces message size, though the image may be blocked by email clients, fetched through a proxy, or fail to render. Manage remote assets separately and never place essential information solely inside an image.

## 14. Limits by email category and tenant

An application may send multiple kinds of emails:

- OTP or security notices: typically need no attachments.
- Order confirmations: may attach a small invoice.
- Operational reports: may need CSV/PDF.
- Newsletters: usually use remote or inline images.
- Support emails: may attach screenshots.

Do not apply a single budget to all email types when their needs differ. Policies can be defined by template or message category:

| Email type | Max attachment count | Max single file | Max total MIME |
| --- | ---: | ---: | ---: |
| OTP/security | 0 | 0 | 200 KB |
| Transactional notice | 2 | 5 MB | 8 MB |
| Invoice | 1 | 10 MB | 15 MB |
| Operations report | 5 | 10 MB | 20 MB |
| Newsletter | Per asset strategy | Per asset policy | Per ESP |

These numbers are illustrative only. If a tenant uses its own SMTP account, the budget may vary by contract and provider. Never allow tenants to raise limits above system policy.

A policy layer can take `MailCategory`, `tenantId`, and attachment metadata, and return the applicable limits. Do not place provider/tenant selection logic inside `MimeMessageHelper`; the helper should simply build the message according to decisions from the business/infrastructure layer.

## 15. Handling errors when a message exceeds limits

When a provider rejects a message as too large, the error may occur at SMTP DATA or as an API error depending on the service. Error codes and response messages differ across providers. Never hard-code a single SMTP code for all size-exceeded cases.

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Message rejected immediately on send | Total MIME exceeds provider limit | Measure serialized MIME, shrink files, or switch to a link |
| One file rejected even though total email is small | Exceeds per-attachment limit or disallowed format | Check each file and policy |
| Slow sending or timeout | Large file, slow network, slow server processing | Limit size, timeouts, queues, and concurrency |
| `OutOfMemoryError` during bulk sends | Reading files into byte arrays or too many concurrent workers | Use Resource/streams and limit concurrency |
| Email accepted by relay but bounces later | Final destination system has tighter limits or policies | Monitor bounces/events from ESP |
| Corrupted attachment | Consumed stream, mutated file, or malformed MIME part | Use re-readable resources and check file snapshots |
| Garbled attachment filename | Wrong filename encoding or unnormalized input name | Use helper and sanitize filename |
| File has valid extension yet fails to open | Actual content mismatches extension | Check MIME/signatures and scan files |

### Does retrying help with size errors?

If the message does not change, retrying will not resolve a size-limit rejection. You must change the content: shrink images, compress/resize, drop unnecessary attachments, or switch to a download link.

If a timeout occurs during SMTP DATA, the outcome may be uncertain: the relay may have received the message while the client missed the final reply. Blind retrying can cause duplicate emails. Store delivery/attempt IDs and reconcile with the provider whenever possible.

## 16. Monitoring sizes without logging sensitive data

Record measurements to identify which templates or email categories frequently approach the budget:

~~~json
{
  "deliveryId": "delivery-2026-001",
  "template": "invoice-email",
  "attachmentCount": 1,
  "attachmentBytes": 6291456,
  "htmlBytes": 82100,
  "serializedMimeBytes": 8543000,
  "maxMimeBytes": 20000000,
  "preflight": "accepted"
}
~~~

Useful metrics:

- Byte count of each attachment.
- Total raw file bytes.
- HTML/plain-text bytes.
- Serialized MIME bytes.
- Attachment count and recipient count.
- Rate of messages blocked by preflight.
- Rate of SMTP rejections due to size.
- Serialization and sending duration.
- Number of pending jobs in the queue.

Never log file contents, Base64 payloads, full HTML, or personal data just to measure sizes. If file correlation is needed, log an internal file ID or a controlled hash instead of the content.

## 17. Testing attachment limits

Policy logic can be tested without an SMTP server. Example with JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class AttachmentPolicyTest {

    @Test
    void rejectsTooManyAttachments() {
        AttachmentPolicy policy =
            new AttachmentPolicy(1024, 4096, 2);

        assertThrows(
            IllegalArgumentException.class,
            () -> policy.validate(List.of(
                Path.of("a.pdf"),
                Path.of("b.pdf"),
                Path.of("c.pdf")
            ))
        );
    }
}
~~~

This test requires fixture files to exist if the policy calls `Files.size`; in real tests, create temporary files with known contents and sizes. Also verify:

- Files at the exact limit are accepted.
- Files larger than the limit are rejected.
- Sum of files exceeding the threshold is rejected.
- Attachment counts exceeding the limit are rejected.
- Missing files or non-regular files are handled properly.
- Serialized MIME exceeding the budget is rejected before calling the sender.
- Resources remain re-readable after the measurement step.
- Messages still carry intact attachments after sending through an SMTP test server.

### Inspecting MIME with an SMTP test server

Unit tests only verify policy logic. Integration tests can send emails to a local SMTP test server and then read the raw message to confirm:

- `Content-Type` and multipart boundaries.
- Attachment filename and MIME type.
- `Content-Transfer-Encoding`.
- Decoded attachment data has the same hash as the original file.
- Serialized size is close to the preflight measurement.
- Email clients receive the expected message structure.

Never use production SMTP in unit tests. Never send fixtures containing real data to user mailboxes.

## 18. Notes when using Spring Boot and Jakarta Mail

### Timeouts are not size limits

Properties:

~~~properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
~~~

control socket operation durations; they do not set attachment or MIME size limits. A 30 MB file can still be sent if the provider allows it and timeouts suffice; conversely, a 1 MB file can fail due to network issues or policy.

### spring.servlet.multipart is not a mail attachment limit

Spring Boot has multipart properties for HTTP uploads, such as per-file and request upload limits. These control data **entering the application via HTTP**, and do not automatically limit emails sent outbound via `JavaMailSender`.

If a file is uploaded and then attached, enforce checks at both boundaries:

1. Upload request: request/file limits, count, permissions, and content.
2. Mail send: attachment limits, total MIME size, provider policy, and quotas.

Never treat an upload property as proof that all outbound emails fit within SMTP limits.

### Do not accept user-controlled file paths directly

If a request includes a file path, never construct a `FileSystemResource` arbitrarily from that string. Users could attempt to access files outside the allowed directory. Accept a file ID, look up metadata in application-managed storage, and verify the sender has permission to attach that file.

## 19. Decision flow when attachments are present

Before sending an email with attachments, you can follow this flow:

~~~text
Receive email send request
        |
        v
Determine email category and policy
        |
        v
Verify file access permissions
        |
        v
Check count / per-file size / total file size
        |
        v
Check type, filename, malware status
        |
        v
Create MimeMessage + MimeMessageHelper
        |
        v
Add body, inline parts, and attachments
        |
        v
Serialize MIME to measure total message
        |
        v
Within budget with margin?
        |
      +---+---+
      |       |
     No      Yes
      |       |
      v       v
Optimize /    JavaMailSender.send()
download link       |
/ reject            v
             Save submission result
~~~

If the budget is exceeded, the application should return a clear business error or switch to a download-link approach. Never send anyway just to "see if the provider accepts it" when the application already knows the message exceeds its own threshold.

## 20. Key takeaways

When working with attachments in Spring Framework Mail, manage both individual files and the entire email together:

- Measure original files with `Files.size(...)` or stream counting; use `long` for bytes.
- Set limits per file, for total attachments, and for file count.
- Remember Base64 expands binary data by roughly one-third, before MIME overhead.
- Build the complete `MimeMessage` and serialize via `writeTo(...)` into a counting stream for preflight measurement.
- Treat serialized MIME as a close estimate of the sent message, not an exact guarantee of SMTP wire size or provider quota accounting.
- Use `MimeMessageHelper` and `Resource` to attach files; prefer sources that can open fresh streams.
- Avoid loading large files into `byte[]` just to measure or send; control worker concurrency and resource lifecycles.
- Validate files right at the upload boundary: access permissions, actual type, filename, scanning, and quotas.
- Set budgets by provider, tenant, and email category, leaving a safety margin.
- For large files, consider authenticated download links instead of attachments.
- Monitor size metrics and provider errors without logging sensitive content.

`MimeMessageHelper` adds files to emails with the proper MIME structure, while size limits remain the responsibility of the application layer and operational configuration. By validating raw files, measuring the final message, and enforcing budgets before `JavaMailSender.send(...)`, the system can catch oversized emails early, reduce SMTP errors, and protect resources when sending many emails concurrently.

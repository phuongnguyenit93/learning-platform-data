# Message Size Limits and In-Memory Data

In **Spring Framework Mail**, a short notification email typically takes only a few KiB. However, emails containing PDF reports, multiple inline images, large HTML bodies, or dozens of attachments can cause the application to consume massive heap, temporary disk space, and bandwidth. A 10 MiB source file does not equal a 10 MiB MIME email: data is usually Base64-encoded, packaged into multiple MIME parts, and augmented with headers and boundaries. When hundreds of `@Async` tasks hold attachments in `byte[]`, the application can run out of memory before the SMTP relay receives a single message.

This problem has **two independent yet related limits**:

1. **Outbound email size:** limits imposed by the application, SMTP submission server, mail provider, and destination mail server on the packaged message.
2. **In-memory application data:** bytes retained by Java in uploaded files, HTML strings, attachment arrays, MIME objects, buffers, task queues, and active workers.

There is no universal maximum size across all SMTP systems. `JavaMailSender` and `MimeMessageHelper` do not automatically define size policies, throttle resources, or handle provider rejections for you. This lesson covers how to estimate MIME sizes, control attachments, avoid large objects in the heap, design workers/outboxes, measure, retry, and test these limits.

## 1. Source File Size Differs from MIME Email Size

An email with attachments typically has this structure:

~~~text
RFC 5322 message
├── Header: From, To, Subject, Date, Message-ID...
└── MIME body
    └── multipart/mixed
        ├── multipart/alternative
        │   ├── text/plain
        │   └── text/html
        ├── attachment: application/pdf
        │   └── base64 encoded content
        └── inline image: image/png
            └── base64 encoded content
~~~

Total message size can include:

- Email headers and individual MIME part headers.
- Encoded Unicode subjects and filenames.
- Both plain text and HTML; if both are sent, both count.
- Source attachments after transfer encoding.
- Inline images and other resources.
- MIME boundaries, line breaks, `Content-Type`, and `Content-Disposition`.
- Data added by the library or transport when constructing the message.

Therefore, the **raw attachment limit** and the **total serialized MIME message limit** must be named, measured, and validated separately.

For example, an 8 MiB PDF, a 3 MiB CSV file, and a 200 KiB inline logo do not produce an email of only around 11.2 MiB. MIME encoding and metadata make the wire message larger.

## 2. Limits Can Appear at Multiple Layers

~~~mermaid
flowchart LR
    A["HTTP upload / Report generator"] --> B["Spring Mail application"]
    B --> C["JavaMailSender"]
    C --> D["SMTP submission relay"]
    D --> E["Provider relay"]
    E --> F["Receiving MX"]
    F --> G["Mailbox"]
~~~

| Layer | Common Limit | What Happens When Exceeded |
| --- | --- | --- |
| Reverse proxy / API gateway | HTTP body size | Request blocked before Spring MVC |
| Spring multipart parser | File size / request size | Upload rejected |
| Business mail policy | File size, attachment count, MIME budget | Rejected before creating mail job |
| JVM | Heap, threads, queues, file descriptors | Rising GC, OOM, task rejection |
| Temporary disk | Upload staging, generated reports | Unable to create/read files |
| SMTP submission relay | Max message size | SMTP rejects submission |
| Provider | Size, quota, content policy | Reject or defer |
| Receiving server | Message size, mailbox/policy | Bounce or downstream rejection |

One relay may accept a message while the destination mail server still rejects it due to a lower limit. Conversely, the Spring application's own limit should be conservative enough to avoid sending right near the provider's threshold and hitting errors.

**Do not assume a provider allowing 25 MiB files means a 25 MiB MIME message is always accepted.** Some services state total message limits, while others publish attachment limits or use different MB units. Always verify the exact contract of the system in use.

## 3. MB, MiB, and Bytes

| Unit | Byte Count |
| --- | ---: |
| 1 kB | 1,000 |
| 1 MB | 1,000,000 |
| 1 KiB | 1,024 |
| 1 MiB | 1,048,576 |

In code, limits should use `long` and explicit names:

~~~java
private static final long MIB = 1024L * 1024L;

private static final long MAX_RAW_ATTACHMENT_BYTES =
        8L * MIB;

private static final long MAX_ESTIMATED_MIME_BYTES =
        18L * MIB;
~~~

The values 8 MiB and 18 MiB in this example only illustrate an application policy; they are not default values or guarantees from Spring/providers.

Avoid naming a variable `maxEmailSize` if it is unclear whether it measures raw files, HTML, full MIME, or an HTTP request.

## 4. How Much Does Base64 Expand Attachments?

Many MIME attachments use **Content-Transfer-Encoding: base64**. Every 3 source bytes are represented as 4 ASCII characters. For `N` source bytes:

\[
\mathrm{Base64Chars}(N)=4\left\lceil \frac{N}{3}\right\rceil
\]

This is roughly a 33% increase before line breaks. MIME Base64 is typically folded into lines of at most 76 characters with CRLF. An estimation formula for the transmitted payload is:

\[
\mathrm{ApproxWireBytes}(N)
=
4\left\lceil \frac{N}{3}\right\rceil
+
2\left\lceil \frac{4\lceil N/3\rceil}{76}\right\rceil
\]

This is an **estimate for the body of one Base64 MIME attachment**. It excludes boundaries, part headers, subject, HTML body, and other parts.

| Source File | Approx. Raw Base64 | Approx. With CRLF |
| --- | --- | --- |
| 1 MiB | 1.33 MiB | 1.37 MiB |
| 5 MiB | 6.67 MiB | 6.84 MiB |
| 10 MiB | 13.33 MiB | 13.68 MiB |
| 15 MiB | 20 MiB | 20.53 MiB |

**Consequence:** a 15 MiB source file can exceed a 20 MiB total message limit right after encoding. If users ask "why can't a 15 MiB file be sent when the provider says 20 MiB?", this is the first cause to check.

## 5. Separating Wire Size from Heap Size

A 10 MiB source file can produce an SMTP message over 13 MiB. However, Java heap usage does not necessarily equal 13 MiB. It can be larger or smaller depending on the processing path.

Example where the application creates multiple objects itself:

~~~text
MultipartFile
  -> getBytes(): byte[10 MiB]
  -> Arrays.copyOf(): byte[10 MiB]
  -> Base64 String: encoded content
  -> MimeMessage / DataSource
  -> Mail task queue holds reference
  -> Jakarta Mail serialization buffers
~~~

When processing via `FileSystemResource`, the application is not forced to hold the entire file in a byte array upfront. Still, this **does not promise zero-copy**: libraries, renderers, transports, and the network stack may still buffer.

What needs control is **peak retained data** across requests, workers, and queues, not just input file size.

## 6. Does Spring Mail Automatically Block Oversized MIME Messages?

A mail sending snippet:

~~~java
MimeMessage message =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message, true, "UTF-8"
        );

helper.setFrom("reports@example.org");
helper.setTo("recipient@example.org");
helper.setSubject("Monthly report");

helper.setText(
        "Attached report.",
        "<p>Attached report.</p>"
);

helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportFile)
);

mailSender.send(message);
~~~

There is not a single line here guaranteeing the final message stays below provider limits. `MimeMessageHelper` builds MIME parts; `JavaMailSender` sends them over the mail transport.

**Do not assume a property named `spring.mail.max-message-size` exists and that Spring Boot will enforce size for every SMTP provider.** The application must enforce its own policy and still handle provider rejections.

Normally, check sizes from **attachment and body metadata** before building/sending the message, using headroom instead of waiting for SMTP to reject.

## 7. What Is the SMTP SIZE Extension?

Some SMTP servers advertise the **SIZE** capability when a client sends `EHLO`:

~~~text
C: EHLO app.example.org
S: 250-mail.provider.example
S: 250-SIZE 20971520
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
~~~

This is an illustrative exchange. Servers may report limits in bytes or support the extension according to their implementation.

However:

- Not every server advertises `SIZE`.
- Limits may vary by account/endpoint.
- A message below `SIZE` can still be rejected for other policies.
- Downstream servers behind a relay may enforce lower limits.
- Clients can encounter rejections mid-transfer.

Therefore, **SMTP SIZE does not replace application-side validation**, nor does it guarantee final delivery after the initial relay accepts it.

## 8. Classifying Message Size Errors

An SMTP response might be:

~~~text
552 5.3.4 Message size exceeds fixed maximum message size
~~~

This is only an illustrative example; exact codes and messages vary by provider. A `5xx` error generally indicates the request should not be blindly retried, whereas some `4xx` errors may be transient.

| Category | Example | Handling |
| --- | --- | --- |
| Hard message size rejection | MIME exceeds limit | Do not retry same payload indefinitely |
| Temporary SMTP failure | Relay temporarily unavailable | Retry with backoff |
| SMTP timeout | Unclear whether relay received it | Handle `UNKNOWN` outcome |
| Attachment missing | File deleted or bad path | Fix storage/lifecycle handling |
| Attachment IO failure | Unable to read data source | Classify IO error and retry if appropriate |
| Downstream size bounce | Destination server rejects after submit | Handle bounce/delivery feedback |

`JavaMailSender` can throw `MailException` wrapping a Jakarta Mail cause. Do not simply search for the substring `"too large"` in every exception; classify by reply codes, enhanced status codes, and provider contract messages.

### Do Not Turn Hard Limits into Retry Storms

If a message is known to exceed a fixed limit, retrying every 30 seconds with the exact same MIME will not shrink it. Instead, send a download link, reduce attachments, alter the content, or mark the job for intervention.

## 9. Common Attachment Sources

Spring Mail supports multiple content sources:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes)
);
~~~

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(verifiedFile)
);
~~~

~~~java
helper.addAttachment(
        "invoice.pdf",
        inputStreamSource,
        "application/pdf"
);
~~~

| Source | Pros | Things to Watch |
| --- | --- | --- |
| `ByteArrayResource` | Simple, fits small `byte[]` | Retains entire file in heap |
| `FileSystemResource` | Can open streams on demand | File must exist until send completes |
| `InputStreamSource` | Custom stream-opening logic | Every call must return a valid stream |
| Durable storage key | Queue/outbox holds tiny metadata | Worker must resolve and fetch from storage |
| Temp file | Reduces RAM retention | Must manage disk quotas, TTL, cleanup |

Switching `ByteArrayResource` to `FileSystemResource` can reduce application-held heap, but only helps if upstream and downstream steps do not call `Files.readAllBytes` or serialize the entire attachment into RAM anyway.

## 10. ByteArrayResource and getBytes()

An anti-pattern for large files:

~~~java
byte[] uploaded =
        multipartFile.getBytes();

helper.addAttachment(
        multipartFile.getOriginalFilename(),
        new ByteArrayResource(uploaded)
);
~~~

`MultipartFile.getBytes()` loads the entire upload into a `byte[]`. `ByteArrayResource` retains a reference to that byte array. While a job sits in a queue or is held by a future/callback, that data stays alive in the heap.

For small, strictly bounded files, this can be reasonable. For multi-MiB files, hundreds of jobs, and multiple retries, it is a major source of memory pressure.

### Capacity Example

Suppose 500 pending jobs each retain a 12 MiB `byte[]` attachment:

\[
500 \times 12\ \mathrm{MiB} = 6000\ \mathrm{MiB}
\]

The byte arrays alone total roughly 5.86 GiB, excluding Strings, MIME objects, heap overhead, and active workers. Even an executor with just 4 threads **can still run out of memory due to 500 queued payloads**.

### Do Not Manually Base64-Encode to a String Unnecessarily

~~~java
String encoded =
        Base64.getMimeEncoder()
                .encodeToString(pdfBytes);
~~~

The result allocates another huge object. When using `MimeMessageHelper.addAttachment`, Jakarta Mail normally performs appropriate transfer encoding during serialization. Pre-encoding manually can create unnecessary copies or double-encode if attached incorrectly.

## 11. InputStreamResource and Read-Once Streams

A common bug:

~~~java
InputStream opened =
        multipartFile.getInputStream();

helper.addAttachment(
        "report.pdf",
        new InputStreamResource(opened),
        "application/pdf"
);
~~~

The data source used by Jakarta Mail may need to open a stream multiple times, such as when inspecting MIME and then serializing/sending. An `InputStreamResource` wrapping an already-opened stream **does not guarantee a fresh stream** once the original stream has been consumed or closed.

Consequences can include:

- Empty or truncated attachments.
- Exceptions because the stream was already read.
- Failures after the HTTP request has already finished.
- Retries unable to re-read the data.

A re-readable source:

~~~java
InputStreamSource source = () ->
        Files.newInputStream(
                storedAttachmentPath
        );

helper.addAttachment(
        "report.pdf",
        source,
        "application/pdf"
);
~~~

In this example, `storedAttachmentPath` must be a path validated and managed by the application. Each call to `getInputStream()` creates a fresh stream. Still, the file must remain present and unmodified between reads.

## 12. FileSystemResource: Benefits and Limits

A worker can reference large files via the filesystem:

~~~java
Path trustedPath =
        storage.resolveAuthorizedPath(attachmentId);

FileSystemResource resource =
        new FileSystemResource(
                trustedPath.toFile()
        );

helper.addAttachment(
        "monthly-report.pdf",
        resource
);
~~~

`storage.resolveAuthorizedPath` is an illustrative application method, not built into Spring. It must verify tenant/actor authorization and prevent path traversal outside the storage root.

Benefit: no need to call `Files.readAllBytes` yourself. Limits:

- Files still consume disk/I/O.
- Jakarta Mail may still buffer during processing.
- The file could be deleted before the worker starts.
- Other replicas/pods may not see local paths.
- The file could change between validation and sending.
- If many workers read large files concurrently, disk and network can still saturate.

**FileSystemResource does not automatically provide durability, size limits, or authorization.**

## 13. HTTP Upload Limits and SMTP Limits Are Separate Layers

With Spring Boot, you can bound multipart HTTP requests:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 8MB
      max-request-size: 12MB
~~~

These properties apply to HTTP multipart uploads; **they do not automatically limit messages sent out by `JavaMailSender`**.

A report generated directly on the server never passes through HTTP upload, yet still requires a mail size policy. An 8 MiB file accepted by HTTP does not guarantee the resulting email stays under a 12 MiB MIME limit.

Additional limits may be needed at the API gateway, reverse proxy, controller/application layer, and managed storage. Do not rely solely on `MultipartFile.getSize()` or `Content-Length` if clients stream data and could report inaccurate metadata.

## 14. Designing a Multi-Tier MailSizePolicy

A policy should validate at minimum:

- Number of attachments.
- Size of each raw attachment.
- Total raw attachment size.
- Size of plain text and HTML.
- Inline images and metadata.
- Projected MIME message size after encoding.
- Total in-flight resources.
- Temporary disk quotas and retention.

A hypothetical example:

~~~text
Max attachments:           5
Max single attachment:     8 MiB
Max total raw attachments: 12 MiB
Max HTML UTF-8 content:  512 KiB
Estimated MIME budget:    18 MiB
~~~

Numbers are purely illustrative. If the provider enforces a lower total message limit, reduce the budget. If an attachment is a sensitive report, policy might permit only a download link instead of sending the file.

**Check total bytes and part count together.** Thousands of tiny few-byte files still generate substantial MIME metadata and overhead.

## 15. Example MIME Estimation in Java

~~~java
import java.util.List;

public final class MailSizePolicy {

    private static final long MIB = 1024L * 1024L;
    private static final long MAX_SINGLE = 8 * MIB;
    private static final long MAX_RAW_TOTAL = 12 * MIB;
    private static final long MAX_ESTIMATED = 18 * MIB;
    private static final long MIME_HEADROOM =
            256 * 1024L;
    private static final int MAX_ATTACHMENTS = 5;

    public void requireAllowed(
            List<AttachmentMeta> files,
            long textBytes) {

        if (textBytes < 0 || textBytes > MIB) {
            throw new MailSizeException(
                    "Body exceeds limit"
            );
        }

        if (files.size() > MAX_ATTACHMENTS) {
            throw new MailSizeException(
                    "Too many attachments"
            );
        }

        long rawTotal = 0;
        long estimated = Math.addExact(
                textBytes, MIME_HEADROOM
        );

        for (AttachmentMeta file : files) {
            long raw = file.byteLength();

            if (raw < 0 || raw > MAX_SINGLE) {
                throw new MailSizeException(
                        "Attachment exceeds limit"
                );
            }

            rawTotal = Math.addExact(
                    rawTotal, raw
            );

            estimated = Math.addExact(
                    estimated,
                    approximateBase64Bytes(raw)
            );
        }

        if (rawTotal > MAX_RAW_TOTAL
                || estimated > MAX_ESTIMATED) {
            throw new MailSizeException(
                    "Estimated email exceeds MIME budget"
            );
        }
    }

    private static long approximateBase64Bytes(long n) {
        // n is already bounded by MAX_SINGLE.
        long encodedChars = 4L * ((n + 2L) / 3L);
        long lines = (encodedChars + 75L) / 76L;

        return Math.addExact(
                encodedChars,
                Math.multiplyExact(2L, lines)
        );
    }

    public record AttachmentMeta(
            String storageKey,
            String filename,
            long byteLength) {
    }
}
~~~

`MailSizeException` is an application-defined exception. `MIME_HEADROOM` is only an **illustrative reserve**, not a MIME-standard guaranteed upper bound.

Limitations of this calculation:

- Text bodies may use quoted-printable or another transfer encoding.
- Subjects, filenames, and Unicode headers may expand beyond raw lengths.
- Inline images must be counted.
- MIME boundaries and provider serialization may differ.
- Files can change after metadata is read.
- Providers may enforce lower limits.

Thus, this is a **preflight estimate**, not proof the message will always be accepted by the relay. When a hard upper bound is needed, measure serialization in a way matching the real pipeline while still handling SMTP rejections.

## 16. String.length() Is Not Byte Length

In Java:

~~~java
int chars = html.length();
~~~

`String.length()` counts UTF-16 code units, not UTF-8 bytes. Accented Vietnamese characters, emojis, and other symbols can occupy multiple bytes.

For small bounded bodies:

~~~java
long utf8Bytes =
        html.getBytes(
                StandardCharsets.UTF_8
        ).length;
~~~

This call allocates a new byte array. For very large HTML, avoid creating an extra copy just to measure; enforce input/rendering limits and use streaming encoders/counters when truly needed.

Raw UTF-8 byte count still differs from MIME serialized bytes: transfer encoding, line endings, and headers further alter total size.

## 17. Measuring Serialized MIME Size in Tests

For **small, bounded** emails, you can count bytes after serialization:

~~~java
MimeMessage message =
        mailSender.createMimeMessage();

// Build the complete message.

message.saveChanges();

ByteArrayOutputStream out =
        new ByteArrayOutputStream();

message.writeTo(out);

long serializedBytes = out.size();
~~~

**Do not put this on the production hot path for large attachments.** `ByteArrayOutputStream` retains all MIME bytes in RAM, potentially creating a huge copy while `MimeMessage`/resources are also still alive.

A counting stream without retaining full output:

~~~java
public final class CountingOutputStream
        extends OutputStream {

    private long bytes;

    @Override
    public void write(int value) {
        bytes = Math.addExact(bytes, 1);
    }

    @Override
    public void write(
            byte[] data,
            int off,
            int len) {
        bytes = Math.addExact(bytes, len);
    }

    public long count() {
        return bytes;
    }
}
~~~

~~~java
message.saveChanges();

CountingOutputStream counter =
        new CountingOutputStream();

message.writeTo(counter);

long serializedBytes = counter.count();
~~~

A counting stream avoids retaining the whole output, yet **serialization still reads the data** and Jakarta Mail may buffer internally. If you subsequently call `mailSender.send`, sources must be re-openable; measuring can add CPU/disk I/O and send latency. Changing headers or resources between measuring and sending can also change the final size.

## 18. Do Not Hold Large byte[] in Async Commands

An example unsuitable for bulk mail:

~~~java
public record SendReportCommand(
        String recipient,
        byte[] reportPdf) {
}
~~~

~~~java
@Async("mailExecutor")
public void sendReport(SendReportCommand command) {
    helper.addAttachment(
            "report.pdf",
            new ByteArrayResource(
                    command.reportPdf()
            )
    );

    mailSender.send(message);
}
~~~

If 200 commands wait in the executor simultaneously, the queue retains 200 PDF arrays. `@Async` does not make data disappear; it merely moves sending onto another thread when invoked through the Spring proxy.

A lower-heap design:

~~~java
public record SendReportCommand(
        UUID jobId,
        String recipientContactId,
        String attachmentStorageKey) {
}
~~~

The worker looks up the key in managed storage and opens a stream when preparing the message. The queue holds only small IDs/metadata. For retries or restarts, storage must have durability and proper access controls, not just an HTTP request's temp file.

## 19. Do Not Expect Temp Files to Outlive the Request

A race condition:

~~~text
HTTP request:
  receives MultipartFile
  saves temp file
  schedules @Async send(tempPath)
  request ends
  cleanup deletes file

Mail worker:
  starts after request ends
  opens tempPath
  FileNotFoundException
~~~

Similarly, `MultipartFile.getInputStream()` can return a stream that becomes invalid once the request finishes. Never pass raw request streams to a worker assuming they remain usable indefinitely.

A better flow:

~~~mermaid
flowchart TD
    A["HTTP upload / report generated"] --> B["Check size policy"]
    B --> C["Save to managed storage"]
    C --> D["Create mail job with storage key"]
    D --> E["Worker reads job"]
    E --> F["Open resource when sending"]
    F --> G["JavaMailSender.send"]
    G --> H["Record status / retry"]
    H --> I["Cleanup per retention"]
~~~

If a job may retry over several hours, attachments must remain available until the job finishes per policy. Across multiple replicas, an object store or shared storage fits better than a single container's local `/tmp`.

## 20. Streaming Upload Staging with a Byte Cap

An example moving large files into a managed staging area without retaining the entire content in the heap:

~~~java
public StoredAttachment stage(
        InputStream source,
        String originalName) throws IOException {

    Path target = Files.createTempFile(
            stagingRoot,
            "mail-",
            ".upload"
    );

    long written = 0;

    try (OutputStream out =
            Files.newOutputStream(target)) {

        byte[] buffer = new byte[64 * 1024];
        int n;

        while ((n = source.read(buffer)) != -1) {
            written = Math.addExact(written, n);

            if (written > maxFileBytes) {
                throw new AttachmentTooLargeException();
            }

            out.write(buffer, 0, n);
        }

        return new StoredAttachment(
                target,
                sanitizeFilename(originalName),
                written
        );

    } catch (IOException | RuntimeException error) {
        Files.deleteIfExists(target);
        throw error;
    }
}
~~~

`stagingRoot`, `maxFileBytes`, `StoredAttachment`, `sanitizeFilename`, and `AttachmentTooLargeException` belong to the application implementation, not Spring APIs. Callers must manage `source`'s lifecycle and ensure `target` sits in a dedicated directory with appropriate permissions and space quotas.

Principles:

- Do not blindly trust client-sent `Content-Length`.
- Enforce limits while reading.
- Never use client filenames directly as paths.
- Clean up on failure.
- Validate permissions and file types per policy.
- If jobs must survive restarts, promote from staging to durable storage before acknowledging acceptance.

### ZIP Bombs and Content Validation

A tiny ZIP file can expand into massive data when decompressed. If a workflow unpacks archives before sending, bound total decompressed bytes, entry count, directory depth, and processing resources. File extensions do not prove the actual content is a PDF/PNG/ZIP.

## 21. Managing Attachment Storage Across Retries

An outbox job might hold only:

~~~json
{
  "mailJobId": "job-123",
  "purpose": "REPORT_READY",
  "recipientContactId": "contact-77",
  "attachmentStorageKey": "reports/tenant-42/report-981",
  "attachmentBytes": 5242880,
  "status": "RETRY"
}
~~~

Do not stuff Base64 PDFs into outbox payloads. The database should store metadata and references where appropriate.

Clarify:

- Which tenant owns the storage object.
- Who is authorized to download or send the file.
- Whether an immutable version/checksum prevents content drift across retries.
- Which worker replicas have read access.
- When cleanup runs based on final job status and TTL.
- How to handle missing or unreadable storage objects.
- How to avoid orphaned attachments when the job-creation transaction rolls back.

### Do Not Treat a Local Path as a Durable Reference

If a job is created on pod A and processed on pod B, a local path can be meaningless. For a durable outbox, storage keys must resolve across the appropriate infrastructure with a lifecycle independent of requests.

## 22. Executor Queue Capacity Is Not Memory Capacity

Example:

~~~java
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
~~~

Numbers are illustrative. `queueCapacity=100` limits **the number of waiting tasks**, not total retained bytes.

If the queue holds 100 commands each carrying a 20 MiB `byte[]`, raw data totals roughly 2,000 MiB. If the queue holds 100 IDs and storage keys, memory usage differs dramatically.

### Rejection Policies Do Not Automatically Guarantee Latency

When the queue is full, the executor can reject tasks. With `CallerRunsPolicy`, tasks can run directly on the caller thread, forcing HTTP requests to wait on SMTP. Define saturation behavior explicitly rather than raising queue size indefinitely.

For critical notifications, a persisted outbox/job table and bounded workers fit better than an in-memory queue holding file bytes.

## 23. Measuring and Bounding Total In-Flight Memory

An approximate model:

\[
M_{\mathrm{peak}} \approx
M_{\mathrm{base}}
+ M_{\mathrm{queued}}
+ M_{\mathrm{active}}
+ M_{\mathrm{other}}
\]

Where:

- `M_base`: application heap when no emails are sending.
- `M_queued`: queued payloads/references.
- `M_active`: MIME, encoders, buffers, and objects of active sending workers.
- `M_other`: requests, caches, and other application components.

This formula is directional. It does not fully account for native/direct memory, thread stacks, page caches, or every transient allocation.

If 6 workers retain an average of 30 MiB of related objects per send, active work alone uses ~180 MiB. If the queue simultaneously holds 300 file byte arrays of 5 MiB each, queued raw bytes add ~1,500 MiB.

**Shrinking payloads kept in the queue is usually far more effective than continually raising heap size.**

### Weighted Memory Budget

You can design a permit gate:

~~~text
Mail worker resource budget: 256 MiB
Job A expected memory: 32 MiB
Job B expected memory: 64 MiB
Job C expected memory: 16 MiB
~~~

Dispatch work only when total estimated resource usage fits within budget. This is an application policy, not a default feature of `JavaMailSender`. Estimates need headroom because raw file size is not peak heap.

## 24. Heap Is Not the Only Resource

| Resource | Consumption Source | Symptoms |
| --- | --- | --- |
| Java heap | `byte[]`, strings, MIME objects, queues | GC pauses, `OutOfMemoryError` |
| Temp disk | Multipart staging, generated reports | Out-of-space errors, cannot create files |
| File descriptors | File streams, sockets | Cannot open more resources |
| Threads | Blocking SMTP sends | Pool exhaustion, slow requests |
| Network | Uploads, object fetches, SMTP transfers | Timeouts, falling throughput |
| CPU | Report rendering, MIME encoding | Rising latency |
| Native/direct memory | TLS/socket buffers | Process memory pressure |

Increasing `-Xmx` does not fix provider hard size limits, full disks, socket leaks, or slow networks. Never rely on `OutOfMemoryError` as a mechanism to reject oversized files; the JVM may already be unstable.

## 25. Backpressure When Mail Generation Outpaces Sending

Suppose the system creates 200 mail jobs/minute while the provider and network handle only 30/minute:

~~~text
Producer: 200 jobs/minute
Consumer: 30 jobs/minute
Backlog growth: 170 jobs/minute
~~~

If each job retains large file data in RAM, heap climbs rapidly. If the outbox stores only storage keys, heap is safer, yet database/object storage still grows.

Combine:

- Bounded queues.
- Worker concurrency limits.
- Per-provider rate/quota limiters.
- Pre-enqueue size limits.
- Backpressure/admission control.
- Durable retry schedules.
- TTLs and cleanup.
- Separate lanes for small/sensitive emails vs. heavy reports.

If an HTTP API returns `202 Accepted`, clarify whether the send intent has been **durably persisted** or sits only in executor RAM. Never claim durable acceptance before persistence succeeds.

## 26. Oversized Messages: Handling Options

~~~mermaid
flowchart TD
    A["Mail command"] --> B["Check files/count/body"]
    B --> C{"Exceeds raw policy?"}
    C -->|"Yes"| D["Reject / download link"]
    C -->|"No"| E["Estimate MIME + headroom"]
    E --> F{"Exceeds message budget?"}
    F -->|"Yes"| D
    F -->|"No"| G["Build MIME and send"]
    G --> H{"SMTP result"}
    H -->|"Accepted"| I["Record successful submission"]
    H -->|"Hard size reject"| J["Stop retrying same payload"]
    H -->|"Temporary"| K["Retry per policy"]
~~~

Options:

1. Reject oversized attachment requests with a clear error.
2. Let users reduce file size or count.
3. Optimize reports/images without altering business data.
4. Send a **protected download link** instead of an attachment.
5. Use a dedicated file-transfer service if large file delivery is the primary requirement.

Do not truncate raw PDF/XLSX bytes to "fit" the limit; the file will break. Do not automatically split one file across multiple emails if the product lacks proper assembly, encryption, and tracking mechanisms.

## 27. Sending a Download Link Instead of an Attachment

An email can notify the user:

~~~text
Your report is ready.
Please sign in to download it at:
https://app.example.org/reports/{reportId}
~~~

The URL is illustrative. Benefits:

- Reduces MIME size.
- Avoids loading whole files into mail workers.
- Enables access control and expiration enforcement.
- Allows revoking or updating access permissions.
- Reduces size-rejection rates.

In return, you must protect the URL:

- Enforce tenant- and user-scoped authentication/authorization.
- Never let guessable IDs grant download access.
- When using signed URLs, keep scope and TTL tightly bounded.
- Do not send long-lived tokens.
- Enforce file retention and auditing.
- Validate content type and payload on download.

Do not solve memory issues by placing sensitive files onto an unrestricted public URL.

## 28. Inline Images and Base64 HTML Also Consume Size

An inline image via CID:

~~~html
<img src="cid:brandLogo" alt="Logo">
~~~

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

The image becomes a separate MIME part and counts toward total message size. Calling `helper.setText(...)` before adding inline resources follows `MimeMessageHelper` usage guidance.

Embedding data URIs directly in HTML:

~~~html
<img src="data:image/png;base64,...">
~~~

can bloat HTML Strings, increasing memory and transfer size; mail clients may also block or handle them inconsistently. Do not assume data URIs are optimal just because no separate attachment appears.

Remote image URLs keep full image bytes out of the MIME body, yet carry distinct risks around privacy, tracking, and mail clients blocking image loading.

## 29. Generating PDF or Excel Reports via Streams

A report generator might return:

~~~java
byte[] pdf =
        reportService.generatePdf(reportId);
~~~

If followed by `Arrays.copyOf`, a Base64 String, and `ByteArrayResource`, multiple large copies of the file can coexist.

When supported by the library, write directly to a managed file/output stream:

~~~java
try (OutputStream out =
        Files.newOutputStream(reportPath)) {

    reportService.writePdf(
            reportId,
            out
    );
}
~~~

Once the file is durably saved and passes policy checks, workers can use a re-readable resource. Still, not every PDF/Excel library truly streams: some retain a large document model in RAM. Measure real peak heap and check the exact API in use rather than trusting method names.

Compression is not a default silver bullet: PDF, JPEG, PNG, and XLSX are often already compressed; re-compressing saves little while costing CPU and sometimes triggering malware-scanner or recipient compatibility issues.

## 30. Ensuring Attachments Do Not Change Across Retries

Suppose an outbox job sends a report on its first attempt, then retries an hour later. If the storage key points to a mutable file, content may change between sends even though the job ID stays the same.

For critical transactional emails, use:

- Immutable object versions.
- File checksums/hashes.
- Metadata for raw bytes and content type.
- An idempotency key for the send intent.
- Retention ensuring the file survives across retries.

Do not let a retry send a different document while logging it under the same logical message. If business rules require sending an updated version, create a new intentional send/version.

## 31. Monitoring Size and Memory

| Metric | Question |
| --- | --- |
| `mail_attachment_raw_bytes` | How large are the source files? |
| `mail_attachment_count` | How many MIME attachments are included? |
| `mail_estimated_mime_bytes` | How large is the projected message? |
| `mail_size_rejected_total` | How many requests were blocked by policy? |
| `mail_provider_size_rejected_total` | How many SMTP size rejections occurred? |
| `mail_active_send_count` | How many sends are currently running? |
| `mail_worker_queue_size` | How many tasks are waiting? |
| `mail_oldest_pending_age_seconds` | How old is the oldest backlog item? |
| `jvm_memory_used_bytes` | How much heap/memory is in use? |
| `mail_temp_storage_bytes` | How much disk staging space is used? |
| `mail_send_duration_seconds` | How slow are SMTP sends? |

You can add labels for purpose, account, and size bucket. Never put recipient addresses, attachment filenames, or full storage keys into metric labels, as that risks data exposure and high cardinality.

### Alert When

- Size rejections spike.
- GC pauses/heap climb alongside bulk email traffic.
- Temporary storage nears capacity.
- SMTP write timeouts rise for large emails.
- Attachment files remain orphaned past TTL.
- Worker queue age climbs for security emails.
- Provider limit changes trigger widespread failures.

A successful SMTP submission does not mean the message landed in the inbox; a receiving MX may still reject it later. Maintain bounce/delivery tracking if required by business rules.

## 32. Testing Size Policies

A unit test can operate on metadata without creating multi-MiB real files:

~~~java
@Test
void rejectsLargeAttachment() {
    MailSizePolicy policy =
            new MailSizePolicy();

    List<MailSizePolicy.AttachmentMeta> files =
            List.of(
                    new MailSizePolicy.AttachmentMeta(
                            "reports/job-1",
                            "large.pdf",
                            9L * 1024 * 1024
                    )
            );

    assertThrows(
            MailSizeException.class,
            () -> policy.requireAllowed(
                    files,
                    1024L
            )
    );
}
~~~

Cover:

- 0-byte files.
- Files at the exact threshold.
- Files 1 byte over the threshold.
- Multiple files whose sum exceeds the threshold.
- Part count exceeding the limit.
- Overly long HTML/plain bodies.
- Negative, invalid, and overflow values.
- Headroom near the total MIME budget.
- Proper counting of inline attachments.

Policy tests do not require starting an SMTP relay.

## 33. Testing MIME and SMTP Rejections

### Unit/Component Tests

Use a real `MimeMessage` and mock `JavaMailSender` to inspect MIME structure, charset, subject/recipients, and attachment metadata. With small fixtures, serialize to count bytes as shown earlier.

### SMTP Integration Tests

Use GreenMail/Mailpit/a test server able to simulate size rejections, or a controlled provider sandbox. Tests should verify:

- Small messages are accepted.
- Oversized messages are rejected.
- Error classifiers recognize the size-failure category accurately.
- Workers do not retry hard rejections infinitely.
- Jobs transition to states needing intervention or payload changes.
- File sources/streams are properly closed and cleaned up.

Do not assume every SMTP test server simulates provider quotas/sizes by default; you may need to configure it or use a fake transport for controlled responses.

### Load Tests

Using synthetic data, run many jobs with large attachments and measure:

- Peak heap/GC.
- Active send concurrency.
- Temporary disk usage.
- Open file descriptors.
- SMTP latency/timeouts.
- Queue depth and oldest job age.

When queues hold only storage keys, heap should not grow linearly with total raw attachment bytes across all waiting jobs the way queues holding `byte[]` do.

## 34. Common Implementation Mistakes

### 34.1. Treating Raw File Bytes as MIME Bytes

Base64, CRLF, headers, and MIME boundaries make the total message larger than the source file.

### 34.2. Assuming JavaMailSender Enforces Hard Size Limits Automatically

Applications need their own policies and must still handle provider rejections.

### 34.3. Calling MultipartFile.getBytes for Every File

It allocates byte arrays in the heap. With large files or high request rates, this creates significant pressure.

### 34.4. Putting byte[] Inside @Async Tasks or Outbox Payloads

Queues retain all data, inflating heap/database size. Use storage keys.

### 34.5. Manually Base64-Encoding into a String Passed to MimeMessage

This can create large copies, double encoding, and broken transfer semantics.

### 34.6. Using InputStreamResource with an Already-Opened Stream

Does not guarantee re-readability when Jakarta Mail needs the stream multiple times.

### 34.7. Deleting HTTP Temp Files Immediately After Scheduling a Worker

The worker may not have read the file yet. Use proper managed storage/lifecycles.

### 34.8. Measuring MIME with ByteArrayOutputStream on Every Production Message

Creates a serialized copy in RAM and increases CPU/I/O.

### 34.9. Simply Increasing Xmx When Workers Slow Down

Does not fix SMTP size limits, full disks, network bottlenecks, or unbounded queues.

### 34.10. Treating QueueCapacity as a Total Memory Budget

Task count does not say how many bytes each task holds.

### 34.11. Retrying Permanent Size Rejections

The exact same payload will remain too large. Shrink size or change delivery approach.

### 34.12. Confusing HTTP Multipart Limits with SMTP Limits

They are two independent layers, and backend-generated files never pass through the HTTP multipart parser.

### 34.13. Limiting File Count Without Limiting Total Bytes

Multiple large files combined can still exceed provider size limits.

### 34.14. Limiting Total Bytes Without Limiting File Count

Thousands of tiny parts still create heavy metadata overhead.

### 34.15. Using FileSystemResource Without Path/Permission Controls

Risks reading unintended files, path traversal, missing files, or mid-flight modifications.

### 34.16. Treating SMTP SIZE as a Delivery Guarantee

`SIZE` advertisement does not guarantee every downstream relay/recipient will accept the message.

### 34.17. Writing Attachment Bytes to Logs

Risks leaking sensitive data and filling log storage. Log minimal metadata only.

### 34.18. Letting Heavy Reports Monopolize All Workers

Password-reset and transactional emails can stall. Use bounded concurrency and prioritization.

## 35. Practical Scenarios

**Scenario A — SMTP provider caps total message at 20 MiB.** Should you send a 15 MiB source PDF?

Do not assume it will succeed. Base64 with CRLF already takes roughly 20.53 MiB, before counting MIME metadata/body.

**Scenario B — An 8 MiB API upload passes, yet SMTP rejects on size.** Why?

HTTP multipart limits validate the raw upload; MIME serialization expands the final message size.

**Scenario C — 500 queued @Async jobs, each carrying a 12 MiB byte[].** What is the risk?

Roughly 6,000 MiB of raw byte arrays can be retained in the heap. Use storage keys and bounded queues.

**Scenario D — FileSystemResource reports file not found.** Why?

The temp file was deleted, the path is wrong, the file does not exist on another replica, or permissions are invalid.

**Scenario E — Attachment succeeds on first send, fails with stream error on retry.** Root cause?

`InputStreamSource` does not open a fresh stream; the old stream is already consumed/closed.

**Scenario F — Provider returns a hard size rejection.** Should you retry as-is?

No. Shrink the content, switch to a download link, or mark the job non-retryable.

**Scenario G — No attachments, yet HTML embeds large Base64 images.** Does that count toward message size?

Yes. Data URIs bloat the HTML and MIME body.

**Scenario H — Only 8 small workers, yet heap still runs out.** What should you check?

The queue may retain large byte arrays, in addition to objects and buffers held by active workers.

**Scenario I — Outbox retries on another pod, attachment sits in the previous pod's /tmp.** Result?

The file may not exist. Use durable shared/object storage.

**Scenario J — Relay accepts the email, yet the recipient never sees the file.** What could cause this?

A receiving MX has a lower size/policy limit and bounces later; SMTP accepted is not delivered.

## 36. Mental Model

~~~mermaid
flowchart TD
    A["Mail request"] --> B["Authorization + recipient policy"]
    B --> C["Check files/count/size"]
    C --> D["Store attachment in managed storage"]
    D --> E["Job holds storage key only"]
    E --> F["Bounded mail worker"]
    F --> G["Estimate MIME + headroom"]
    G --> H{"Within budget?"}
    H -->|"No"| I["Reject / download link"]
    H -->|"Yes"| J["Open re-readable stream"]
    J --> K["MimeMessageHelper"]
    K --> L["JavaMailSender"]
    L --> M{"SMTP result"}
    M -->|"Accepted"| N["Mark submitted"]
    M -->|"Hard size rejection"| O["Stop retrying same payload"]
    M -->|"Transient / unknown"| P["Retry / reconcile"]
    N --> Q["Cleanup per retention"]
    O --> Q
    P --> F
~~~

Core principles:

1. **Raw attachment size differs from MIME message size.** Base64 usually expands by roughly one third, and CRLF/headers/HTML add more.
2. **No single SMTP size limit applies to every provider or mailbox.** Enforce an internal policy with headroom.
3. **`JavaMailSender` and `MimeMessageHelper` are not automatic memory/size control systems.**
4. **Validate per-file, total bytes, attachment count, HTML, and estimated MIME** before sending.
5. **Distinguish wire bytes from heap bytes.** One file can exist in multiple copies in RAM.
6. **Avoid placing large `byte[]` in async queues/outboxes**; use IDs and storage references.
7. **Attachment sources must be re-readable and outlive** sending and retries.
8. **HTTP upload limits are not SMTP limits** and do not guard backend-generated files.
9. **Counting MIME via `ByteArrayOutputStream` fits only small payloads/tests**; keep it off hot paths for large messages.
10. **Bound queues, in-flight memory, and concurrency**, rather than only increasing heap.
11. **Do not infinitely retry hard size rejections with the same payload**; consider authorized download links.
12. **Monitor heap, GC, disk, MIME size, timeouts, and queue age** in production.
13. **SMTP accepted differs from delivered**; downstream servers can still reject for size/policy.

In Spring Framework Mail, performance for emails with attachments depends on both **wire size** and **how the application retains data in memory**. A sound pipeline rejects or redirects oversized messages, reads attachments from suitable sources, keeps queue payloads small, and bounds storage/workers explicitly. As a result, a few heavy reports will not exhaust heap, stall SMTP, or disrupt critical emails across the entire system.

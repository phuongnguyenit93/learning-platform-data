# Separating Content Preparation from Sending in Spring Framework Mail

In a Spring application, sending email is more than calling `JavaMailSender.send(...)`. Before a message reaches an SMTP relay, the system may need to read business data, look up templates, render HTML/plain text, generate a PDF, download images from object storage, resize images, validate attachments, assemble MIME, and decide whether the recipient is still eligible to receive the message.

If all of that work is combined into one synchronous call on an HTTP request or a single worker, steps competing for CPU, RAM, I/O, and SMTP connections contend for the same resources. A slow PDF generation can tie up a sending thread; conversely, SMTP throttling can back up thousands of content-rendering tasks. On a request timeout or process restart, the application also risks losing in-flight state or sending duplicates.

**Separating content preparation from sending** is a design that splits the pipeline into two groups of work with distinct resource profiles:

- **Preparation:** generates and normalizes the data needed to send an email, including templates, plain text, HTML, documents, and attachment references.
- **Submission:** takes the prepared content, builds a `MimeMessage` when needed, enforces sending policies, calls `JavaMailSender`, and records the SMTP outcome.

This separation does not require two separate microservices. A single Spring application can use two worker pools, two durable job types, or two stages of the same outbox. What matters is keeping **responsibility boundaries, durable state, resource limits, and retry policies** explicit.

## 1. Why separate them?

Consider an invoice-sending workflow:

~~~text
HTTP request
     |
     v
Read order + customer
     |
     v
Render HTML template
     |
     v
Generate invoice PDF
     |
     v
Read logo/images and attachments
     |
     v
Build MimeMessage
     |
     v
SMTP connect / TLS / AUTH / DATA
     |
     v
Record outcome
     |
     v
HTTP response
~~~

If everything runs on the request thread, end-to-end latency equals the sum of every step. SMTP may time out at the very end, leaving the user waiting even though order confirmation already succeeded. If you try to retry the entire workflow, the system may regenerate the PDF and reload images repeatedly even though only SMTP suffered a transient error.

Splitting the two stages produces a different pipeline:

~~~text
Business transaction
        |
        v
Durable preparation job
        |
        v
Preparation worker
   - Load snapshot/template
   - Render HTML/plain
   - Generate document
   - Persist stable artifact references
        |
        v
READY_TO_SEND
        |
        v
SMTP submission worker
   - Check eligibility and deadline
   - Build MIME from prepared artifacts
   - Apply provider rate limit
   - JavaMailSender.send(...)
        |
        v
SUBMITTED / RETRY_WAIT / FAILED / AMBIGUOUS
~~~

When SMTP encounters an issue, the system can retry the send step without re-rendering content from scratch, provided the prepared data is durable and readable again.

## 2. Two work groups with different resource profiles

| Dimension | Content Preparation | SMTP Submission |
| --- | --- | --- |
| Primary work | Render templates, generate PDFs, process images, read storage | Connect, TLS/AUTH, transfer MIME over the network |
| Dominant resources | CPU, RAM, disk/object storage I/O | Sockets, network, SMTP quota, timeouts |
| Latency profile | Depends on document/template size | Depends on relay, network, throttling |
| Common errors | Broken template, missing file, PDF service failure | AUTH/TLS, 4xx/5xx, connection/read/write timeout |
| Retry | Can retry preparation or fix data | Retry transport only when appropriate |
| Parallelism | Based on CPU, memory, and storage capacity | Based on provider rate/concurrency |
| Output | Prepared content/manifest and references | Submission outcome and provider ID if available |
| Proof of success | Artifacts are durably persisted | Server/transport reports submission accepted |
| Deadline | When content must be ready | When the message is still valid to send |

If the same executor and concurrency apply to everything, one group can stall the other. With separation, you can scale up preparation workers without opening extra SMTP connections, or throttle SMTP send rates during provider rate limiting without blocking content preparation.

## 3. Sensible boundary between preparation and sending

There is no single cut point for every system. Three common levels exist:

| Separation style | What does preparation produce? | What does submission do? | Best suited for |
| --- | --- | --- | --- |
| **Logical separation** | Model + rendered strings within the same task | Builds MIME and sends immediately | Low volume, small preparation cost |
| **Durable prepared manifest** | Plain/HTML + stable attachment references | Builds MIME right before sending and submits | Important emails, retries, large files |
| **Prebuilt MIME artifact** | MIME serialized into a durable `.eml` file | Reads MIME, configures transport/envelope, sends | Byte-level snapshots, specialized pipelines |

This article uses **durable prepared manifest** as the main example because it cleanly separates responsibilities and retries. Preparation persists enough data for another worker to reconstruct the message; the SMTP stage does not have to re-invoke heavy work.

Note that in Jakarta Mail, some MIME work and attachment stream reads can happen **at send/serialization time**, not just when calling `MimeMessageHelper`. Therefore, "created a `MimeMessage`" does not mean all attachment bytes have been materialized, and passing a `MimeMessage` through a queue is not a good durability mechanism.

## 4. Simple synchronous approach and its limits

Example of a service written directly:

~~~java
@Service
public class InvoiceMailService {

    private final JavaMailSender sender;
    private final InvoicePdfService pdfService;
    private final InvoiceTemplateService templates;

    public InvoiceMailService(
            JavaMailSender sender,
            InvoicePdfService pdfService,
            InvoiceTemplateService templates) {
        this.sender = sender;
        this.pdfService = pdfService;
        this.templates = templates;
    }

    public void sendInvoice(UUID invoiceId) throws Exception {
        byte[] pdf = pdfService.generate(invoiceId);
        String html = templates.renderHtml(invoiceId);
        String plain = templates.renderPlain(invoiceId);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo("customer@example.net");
        helper.setSubject("Your invoice");
        helper.setText(plain, html);

        helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdf),
            "application/pdf"
        );

        sender.send(message);
    }
}
~~~

This is an illustrative example; the invoice preparation services are application abstractions. The issue is not that the code is "wrong", but that:

- The method holds the thread while rendering the PDF and waiting on the network.
- The PDF is held in RAM as a `byte[]`.
- An SMTP failure may force re-running all of preparation.
- An HTTP request may time out while SMTP is still processing.
- There is no durable state recording when content preparation finished.
- If executed inside a database transaction, it risks holding connections/locks for too long.
- There are no separate concurrency policies for rendering and SMTP.

For a handful of small emails, this approach can still be simple and reasonable. Introduce a two-stage pipeline only when reliability, throughput, isolation, or preparation cost truly warrants it.

## 5. Standardizing the two data models: intent and prepared content

A **mail intent** describes a business requirement, not an SMTP message:

~~~java
public record MailIntent(
    UUID notificationId,
    UUID businessEventId,
    String recipientId,
    String recipientAddress,
    MailCategory category,
    String templateKey,
    String templateVersion,
    Instant createdAt,
    Instant expiresAt
) {}
~~~

Example `MailCategory`:

~~~java
public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    OPERATIONAL,
    MARKETING
}
~~~

A **prepared content manifest** describes the prepared output:

~~~java
public record PreparedMail(
    UUID notificationId,
    String recipientAddress,
    String senderAddress,
    String subject,
    String plainText,
    String htmlText,
    List<PreparedAttachment> attachments,
    String templateVersion,
    Instant preparedAt
) {}
~~~

~~~java
public record PreparedAttachment(
    String storageKey,
    String fileName,
    String contentType,
    long sizeBytes,
    String checksumSha256
) {}
~~~

The records above are application-defined DTOs, not built-in Spring Mail classes. Production versions may also need Reply-To, Cc, language, inline assets, consent snapshot, business version, or sensitivity classification.

**Never put SMTP passwords, OAuth tokens, JavaMailSender, open InputStreams, or raw MimeMessages into records stored in a queue/outbox.**

## 6. Business transactions only persist send intent

An important rule: persist the send request in the same business transaction, and **do not** render documents or call SMTP inside that transaction.

~~~java
@Service
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final MailIntentRepository mailIntents;

    public OrderConfirmationService(
            OrderRepository orders,
            MailIntentRepository mailIntents) {
        this.orders = orders;
        this.mailIntents = mailIntents;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.getRequired(orderId);
        order.confirm();
        orders.save(order);

        mailIntents.insertIfAbsent(
            MailIntentFactory.forOrderConfirmation(order)
        );
    }
}
~~~

`MailIntentRepository` and `MailIntentFactory` are application abstractions. `insertIfAbsent` should rely on a unique business idempotency key so the same event does not create multiple notifications.

~~~text
BEGIN TRANSACTION
    Update order state
    Insert mail intent / outbox row
COMMIT
               |
               v
        Worker executes later
~~~

Do not hold a transaction containing business updates while:

- Downloading data from remote storage.
- Rendering a PDF.
- Calling SMTP.
- Sleeping for backoff.
- Waiting on a rate limiter.

If the transaction rolls back, the outbox record rolls back with it, avoiding sending an email for uncommitted business state.

## 7. State machine for the two stages

An illustrative state machine:

~~~text
PENDING_PREPARATION
         |
         v
     PREPARING
         |
         +-- success --> READY_TO_SEND
         |
         +-- transient error --> PREP_RETRY_WAIT
         |                           |
         |                           +--> PREPARING
         |
         +-- permanent error --> PREP_FAILED

READY_TO_SEND
         |
         v
       SENDING
         |
         +-- SMTP accepted --> SUBMITTED
         |
         +-- transient error --> SEND_RETRY_WAIT
         |                          |
         |                          +--> SENDING
         |
         +-- permanent error --> SEND_FAILED
         |
         +-- uncertain outcome --> AMBIGUOUS
~~~

Every project does not need these exact enum names, but it must clearly distinguish:

- **Preparation failed**: content is not ready to send.
- **Ready to send**: durable artifacts/references exist.
- **Send failed**: SMTP transport encountered an error.
- **Send accepted**: server/transport confirmed submission.
- **Uncertain outcome**: risk of having submitted even though the client timed out.

Do not use a single `sent=false` flag for all states, because operators will not know whether to fix a template, wait on a provider, or reconcile duplicates.

## 8. What does a preparation worker do?

A typical preparation worker:

1. Claims an intent in `PENDING_PREPARATION` using a lease or transaction guard.
2. Reads the appropriate business data snapshot.
3. Selects template version, locale, and content to produce.
4. Renders subject, plain text, and HTML.
5. Generates or fetches attachments/inline assets if needed.
6. Validates format, size, and scan results per policy.
7. Persists files/documents so they remain readable after a restart.
8. Writes the `PreparedMail` manifest and transitions state to `READY_TO_SEND`.
9. Commits status and releases the lease.
10. On error, records category/attempt count and schedules a preparation retry.

Do not require preparation workers to have SMTP credentials or permission to connect to the SMTP relay. Separating infrastructure privileges reduces risk exposure: the renderer may need business data/storage read access, while the sender needs SMTP network/credentials.

## 9. Example contracts for preparation

~~~java
public interface MailPreparationService {
    PreparedMail prepare(MailIntent intent);
}
~~~

~~~java
public interface PreparedMailRepository {
    void saveReady(PreparedMail prepared);
    PreparedMail getReady(UUID notificationId);
}
~~~

~~~java
public interface PreparedArtifactStore {
    String put(
        String proposedKey,
        InputStream input,
        String contentType
    ) throws IOException;

    InputStream open(String key) throws IOException;
}
~~~

These interfaces are abstractions for designing boundaries; they are not Spring Mail APIs.

An implementation of `MailPreparationService` can use a template engine (Thymeleaf, FreeMarker, or another solution) and a document generation service. The worker only invokes the preparation port and knows nothing about MIME transport.

### Do not render from an arbitrarily mutating model

If a worker reads the "latest" data several minutes later, the email content may no longer reflect the original business event. For invoices or order confirmations, determine the appropriate snapshot or version explicitly when the event is emitted.

## 10. Example preparation service producing a manifest

~~~java
@Service
public class InvoicePreparationService
        implements MailPreparationService {

    private final InvoiceSnapshotRepository invoices;
    private final InvoiceTemplateRenderer renderer;
    private final PdfGenerator pdfGenerator;
    private final PreparedArtifactStore artifacts;

    public InvoicePreparationService(
            InvoiceSnapshotRepository invoices,
            InvoiceTemplateRenderer renderer,
            PdfGenerator pdfGenerator,
            PreparedArtifactStore artifacts) {
        this.invoices = invoices;
        this.renderer = renderer;
        this.pdfGenerator = pdfGenerator;
        this.artifacts = artifacts;
    }

    @Override
    public PreparedMail prepare(MailIntent intent) {
        InvoiceSnapshot snapshot = invoices.getForEvent(
            intent.businessEventId()
        );

        RenderedMail rendered = renderer.render(
            intent.templateKey(),
            intent.templateVersion(),
            snapshot
        );

        GeneratedArtifact generated =
            pdfGenerator.generateInvoice(snapshot);

        // Store persists bytes durably and returns stable reference.
        String key;
        try (InputStream input = generated.openStream()) {
            key = artifacts.put(
                "mail/" + intent.notificationId() + "/invoice.pdf",
                input,
                "application/pdf"
            );
        } catch (IOException exception) {
            throw new MailPreparationException(
                "Cannot persist invoice artifact",
                exception
            );
        }

        PreparedAttachment attachment = new PreparedAttachment(
            key,
            "invoice.pdf",
            "application/pdf",
            generated.sizeBytes(),
            generated.sha256()
        );

        return new PreparedMail(
            intent.notificationId(),
            intent.recipientAddress(),
            "billing@example.com",
            rendered.subject(),
            rendered.plainText(),
            rendered.htmlText(),
            List.of(attachment),
            intent.templateVersion(),
            Instant.now()
        );
    }
}
~~~

`InvoiceSnapshot`, `GeneratedArtifact`, `RenderedMail`, `MailPreparationException`, and the repository/renderer classes are application-defined. `GeneratedArtifact.openStream()` must return a valid stream for that read; `PreparedArtifactStore.put` must complete a durable write before returning the key.

The example highlights preparation and storage logic rather than building a full PDF library. In production, inject a `Clock` for time-based testing, persist consistent snapshots/versions, and validate artifact policies before marking READY.

## 11. Do not keep prepared data only in RAM

If preparation finishes and passes a `PreparedMail` containing large byte arrays into an in-memory executor queue, a process crash loses the result. Keeping many attachment bytes on the heap also increases garbage collection pressure and out-of-memory risk.

A durable strategy:

~~~text
Preparation worker
   |
   +--> Render plain/HTML
   |
   +--> Persist PDF/inline assets to object storage
   |
   +--> Save manifest + artifact references in DB
   |
   v
READY_TO_SEND
   |
   v
SMTP worker reads manifest
   |
   +--> Opens fresh streams from artifact storage
   |
   +--> Constructs MIME
   |
   +--> Sends over SMTP
~~~

For small text bodies, storing subject/plain/html directly in the database can be reasonable. For large PDFs/images, storing objects with immutable keys, checksums, and a retention policy prevents database/outbox payload bloat.

Do not store an ephemeral container's temporary filesystem path and expect a worker on another instance to read it.

## 12. Artifacts must survive and remain readable after a restart

A prepared reference is only safe for retries if:

- The artifact resides in storage accessible to the worker.
- The reference does not depend on the creating thread/process.
- Access permissions and storage credentials match.
- The stream can be reopened multiple times.
- The file is not silently modified after preparation.
- The artifact does not expire during the retry window.
- Size/checksum metadata is sufficient to detect mismatches.
- Cleanup does not delete the file before all attempts finish.

With object storage, a versioned or content-addressed key prevents one path from being overwritten with new content while an older job is still waiting.

Example:

~~~text
mail-artifacts/
  tenant-42/
    notification-abc/
      invoice-v1.pdf
      inline-logo-v3.png
~~~

File/key names must be constructed from validated, authorized IDs. Do not concatenate arbitrary paths from user input, and do not store public URLs containing secrets in the outbox.

## 13. DB transactions and object storage do not commit atomically together

A system may use PostgreSQL for manifests and object storage for PDFs. The two systems typically do not participate in the same ACID transaction.

Failure windows:

~~~text
Upload PDF success
       |
       X  Process crash before DB READY
       |
       v
Artifact orphaned in storage
~~~

Or:

~~~text
DB READY stored too early
       |
       X  PDF upload fails
       |
       v
Sender reads missing artifact
~~~

A practical strategy:

1. Create the artifact using a key tied to the notification/version.
2. Complete the upload and verify required metadata/digest.
3. Persist the manifest and `READY_TO_SEND` in a DB transaction.
4. If the DB commit fails, the artifact may become orphaned.
5. Run a cleanup/reconciler for objects not referenced by any manifest after a grace period.
6. Never publish READY before the artifact is readable.

If you use a temporary key and promote it to a final key, understand the atomicity semantics of the storage service. Never assume object-storage rename is transactional like a local filesystem.

## 14. Build MimeMessage at send time

A convenient pattern is **not passing `MimeMessage` objects through a queue**. Instead, the sender receives `PreparedMail` and builds a fresh message for each SMTP attempt.

~~~java
@Service
public class PreparedMailSmtpAdapter {

    private final JavaMailSender sender;
    private final PreparedArtifactStore artifacts;

    public PreparedMailSmtpAdapter(
            JavaMailSender sender,
            PreparedArtifactStore artifacts) {
        this.sender = sender;
        this.artifacts = artifacts;
    }

    public void send(PreparedMail prepared)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(prepared.senderAddress());
        helper.setTo(prepared.recipientAddress());
        helper.setSubject(prepared.subject());
        helper.setText(
            prepared.plainText(),
            prepared.htmlText()
        );

        for (PreparedAttachment attachment
                : prepared.attachments()) {

            InputStreamSource source = () ->
                artifacts.open(attachment.storageKey());

            helper.addAttachment(
                attachment.fileName(),
                source,
                attachment.contentType()
            );
        }

        message.setHeader(
            "X-App-Notification-ID",
            prepared.notificationId().toString()
        );

        sender.send(message);
    }
}
~~~

This snippet uses `org.springframework.core.io.InputStreamSource`. With `InputStreamSource`, calling `getInputStream()` must return a fresh, readable stream. `PreparedArtifactStore.open` in the example must uphold that contract. `MimeMessageHelper.addAttachment` has an overload accepting `InputStreamSource` and a content type.

The snippet assumes the manifest has already been validated and only illustrates the happy path. In production, handle missing artifacts, stream I/O, SMTP error classification, and message size limits. A successful `send` only means **SMTP submission**, not that the provider delivered the email to the Inbox.

## 15. Why must resource streams be repeatable?

Jakarta Mail may read the attachment stream when serializing the message, and some execution paths may read the source more than once. Here is an unsafe example:

~~~java
InputStream oneShot = remoteStorage.open(key);

InputStreamSource badSource = () -> oneShot;
helper.addAttachment(
    "report.pdf",
    badSource,
    "application/pdf"
);
~~~

Every `getInputStream` call returns the same stream, already partially read or closed. After the first pass, the attachment can be empty, truncated, or throw an exception.

The proper approach:

~~~java
InputStreamSource goodSource = () ->
    remoteStorage.open(key);
~~~

Each call opens **a new stream from the same immutable artifact**. An in-memory example for small files:

~~~java
byte[] bytes = readSmallFixture();
InputStreamSource source = new ByteArrayResource(bytes);
~~~

`ByteArrayResource` provides a fresh stream over an existing byte array; however, holding many large files as byte arrays consumes heap. For large files, prefer a re-openable storage stream or durable file resource rather than an `InputStreamResource` wrapping an already opened stream.

## 16. A MimeMessage does not necessarily hold all bytes yet

A common misconception is that after calling:

~~~java
helper.addAttachment("invoice.pdf", source, "application/pdf");
~~~

the entire PDF has already been copied into the `MimeMessage`. In reality, with `DataSource`/`InputStreamSource` implementations, the content may be read when Jakarta Mail serializes/sends.

This has two consequences:

1. The resource must remain present and readable until sending finishes.
2. Part of the I/O for loading attachments still occurs during the **submission phase**, even though document generation finished during preparation.

If you need to completely isolate artifact-reading network I/O from SMTP send time, you can materialize resources in bounded local staging or prebuild MIME into a durable artifact. However, you must account for extra disk, memory, and cleanup; do not waste unbounded resources just to make a two-stage diagram look tidy.

## 17. Are prebuilt MIME artifacts appropriate?

Some systems want preparation to emit a full `.eml` MIME message so retries send the exact same bytes. This is a specialized option with trade-offs.

**Advantages:**

- MIME bytes are generated once.
- Byte size after encoding can be measured upfront.
- Easy to retain a snapshot of the final payload.
- The sender may have less rendering work to do.

**Challenges:**

- Envelope recipients are separate SMTP metadata, not just `To`/`Cc`/`Bcc` headers.
- `Date`/`Message-ID` headers may change when using certain sending APIs depending on implementation.
- MIME serialization and reloading must remain compatible.
- Prebuilt MIME files can be very large.
- Enforcing privacy, encryption, and retention is harder.
- An older raw message may no longer be valid with respect to consent or deadlines.

If you choose this route, establish an explicit contract for MIME bytes, envelope recipients, transport, queue metadata, and idempotency. Do not assume Java serialization of `MimeMessage` is a stable format for outbox storage.

For most applications, **prepared manifest + immutable attachment references + MIME construction at send time** is a much more manageable boundary.

## 18. Email size and memory budgets

The size of an email sent over SMTP is not equal to the sum of the raw file sizes. MIME headers, boundaries, content transfer encoding, and Base64 increase payload size.

With Base64, binary image/attachment data after encoding typically grows by roughly 4/3 before line and MIME overhead. Thus, a 12 MiB file does not mean the email sent over SMTP is only 12 MiB.

A preparation policy can check:

- Number of attachments.
- Total raw bytes.
- Estimated MIME encoded size.
- HTML size.
- Inline image dimensions and byte sizes.
- Provider max message size.
- Business-specific budget.

If the exact limit depends on the provider, you may need to measure serialized MIME using a byte-counting mechanism at an appropriate step. Do not use HTML `String.length()` as UTF-8 or SMTP byte size, because Java `String.length()` counts UTF-16 code units.

### Do not keep all attachments in RAM

Suppose each email has an 8 MiB PDF and 50 preparation tasks run concurrently. If each task holds at least one PDF `byte[]`, those alone occupy roughly 400 MiB, before accounting for objects, templates, images, encoded buffers, and GC overhead.

A sound design typically:

- Bounds concurrency according to a memory budget.
- Streams files to storage instead of accumulating everything on the heap when possible.
- Stores large files by reference.
- Avoids copying byte arrays multiple times.
- Monitors heap/GC and working-set memory.
- Enforces a per-email size cap before the SMTP worker attempts delivery.

## 19. Separate worker pools for preparation and submission

Because the two stages have different characteristics, do not force them to share one executor:

~~~text
Preparation queue
       |
       v
CPU / render worker pool
       |
       v
Durable READY_TO_SEND
       |
       v
SMTP submission queue
       |
       v
Network / provider-limited worker pool
~~~

Spring can configure two executors for short in-process asynchronous tasks:

~~~java
@Configuration
@EnableAsync
public class MailExecutorsConfiguration {

    @Bean(name = "mailPreparationExecutor")
    public ThreadPoolTaskExecutor preparationExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("mail-prepare-");
        pool.initialize();
        return pool;
    }

    @Bean(name = "mailSubmissionExecutor")
    public ThreadPoolTaskExecutor submissionExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(30);
        pool.setThreadNamePrefix("mail-submit-");
        pool.initialize();
        return pool;
    }
}
~~~

These values are illustrative, not optimal default configurations. Size them based on CPU, memory, SMTP throughput, and provider quotas.

**Note:** `ThreadPoolTaskExecutor` is an in-process task runner, not a durable queue. A process restart can lose tasks sitting in the executor queue. For important emails, an outbox/database or broker must remain the **durable source of work**, while the executor only serves as processing capacity per worker instance.

## 20. Bounded queues and backpressure

A dangerous configuration is a producer generating thousands of tasks per second with only a few sender threads and an unbounded in-memory queue. Consequences:

- Heap grows.
- Long GC pauses.
- Critical emails wait behind campaigns.
- Jobs live in memory and are lost on process crash.
- Queue latency rises even though SMTP appears error-free.
- Executor overload makes retry timing unpredictable.

Backpressure means the upstream layer knows the downstream layer is not ready and **stops pushing unbounded workload**.

With a durable outbox:

1. Poll/claim batches sized to the pool's real capacity.
2. Limit how many `PROCESSING` jobs currently hold leases.
3. When the pool is full, stop claiming or safely return jobs to waiting state.
4. Do not drop jobs simply because the executor rejects submission.
5. Do not hold database locks while waiting on sends.
6. When the provider throttles, reduce concurrency/rate before increasing poll batch size.

Avoid accidentally using `CallerRunsPolicy` on an HTTP request path, which forces preparation/SMTP sending back onto the request thread synchronously. It can be useful inside some intentional worker loops, provided you understand its effects on latency and transaction boundaries.

## 21. Applying separate limits to each worker group

Preparation concurrency is usually constrained by:

- CPU cores and rendering cost.
- Memory for templates, PDFs, and images.
- Object storage/database read throughput.
- Connection counts to content services.
- File sizes and attachment counts.

Submission concurrency is usually constrained by:

- SMTP provider quota.
- Maximum allowed concurrent connections.
- Send rate per account/domain.
- MIME size and network bandwidth.
- SMTP timeouts and retry backoff.

A rough estimate can use the relationship:

~~~text
concurrency ≈ throughput × average service time
~~~

For example, suppose an average SMTP attempt takes 1 second; with 10 busy send slots, theoretical throughput is around 10 attempts/second before accounting for quota, jitter, network, and other bottlenecks. This is not a guarantee that the provider allows 10 emails/second.

Do not increase thread counts to overcome provider rate limits. Rate limiting and concurrency must remain two separate mechanisms.

## 22. Scheduler claiming due jobs

A poller can select jobs by status and due time:

~~~sql
SELECT id
FROM mail_outbox
WHERE status = 'PENDING_PREPARATION'
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

The preparation worker claims and sets a lease inside a short transaction, then commits before rendering.

Send poller:

~~~sql
SELECT id
FROM mail_outbox
WHERE status IN ('READY_TO_SEND', 'SEND_RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

This is illustrative PostgreSQL SQL. Production queries need lease conditions, tenant prioritization, deadlines, suppression checks, and appropriate indexes. `PREPARING`/`SENDING` rows left by crashed workers must be reclaimed after lease expiration according to policy.

`FOR UPDATE SKIP LOCKED` helps multiple pollers avoid claiming the same row locked by another transaction. After claiming, commit quickly; never hold database row locks across rendering or SMTP network calls.

## 23. Preparation retries and SMTP retries must differ

A preparation error might be:

- Template data temporarily unavailable.
- Temporary object storage failure.
- Overloaded PDF generator.
- Missing template key/version.
- Disallowed attachment.
- Malformed business data.

An SMTP error might be:

- Connection timeout before submission.
- SMTP relay temporarily busy or throttling.
- Authentication/TLS configuration error.
- Recipient rejection.
- Message size policy rejection.
- Timeout after DATA with an uncertain outcome.

Do not use a catch-all retry across the entire pipeline:

~~~text
Try:
    render PDF
    build MIME
    send SMTP
On any error:
    repeat everything
~~~

If SMTP fails after a PDF was already generated cleanly, re-rendering wastes CPU and can produce an attachment differing from the original data. If a template is permanently invalid, SMTP retries will not help.

Separate policies:

| Error | Stage | Typically appropriate reaction |
| --- | --- | --- |
| Template not found | Prepare | `PREP_FAILED`, fix configuration/data |
| Storage timeout | Prepare | `PREP_RETRY_WAIT`, backoff |
| File exceeds limit | Prepare | `PREP_FAILED` or switch delivery method |
| Transient SMTP 421 | Send | `SEND_RETRY_WAIT`, backoff + jitter |
| Wrong SMTP auth credentials | Send | Alert, do not hot-retry |
| SMTP rejects message size | Send | `SEND_FAILED`; content must change |
| Timeout after DATA | Send | `AMBIGUOUS`, reconcile before retrying |

Each job must have stage-specific max attempts and business deadlines. Preparation retry count does not have to equal SMTP retry count.

## 24. Idempotency when two workers process concurrently

This can happen:

~~~text
Worker A claims N-123
        |
        v
Worker A renders PDF and uploads
        |
        X  Worker A crashes
        |
        v
Lease expires
        |
        v
Worker B reclaims N-123
        |
        v
Worker B renders PDF again
~~~

To limit duplicate side effects:

- Give every notification a stable ID.
- Make artifact keys idempotent/versioned.
- Persist prepared manifests with conditional updates or optimistic versioning.
- Only allow a worker to mark READY while it still holds a valid lease/ownership.
- Clean up orphaned or duplicate artifacts.
- Check checksum/content version if preparation repeats.

The send stage is even harder: the SMTP relay may accept a message and the worker may crash before recording `SUBMITTED`. An outbox alone does not guarantee exactly-once email delivery. Distinguish **job idempotency** (not enqueueing duplicates) from **transport idempotency** (whether the provider actually deduplicates).

MIME `Message-ID` is not an idempotency mechanism guaranteed by all SMTP servers.

## 25. Ensuring content snapshot consistency

Suppose a customer updates their address or an order changes after the event occurs.

Three options:

1. **Snapshot at the business event:** store required data alongside the intent. Best for receipts/confirmations representing state at the moment of the event.
2. **Snapshot at preparation:** record the snapshot/version used; if sending retries, do not re-render with newer data.
3. **Recompute at send time:** suitable for some notifications needing the latest data, though content may shift between retries.

For transactional confirmation or invoice emails, explicitly define the content version and avoid sending a different version on each retry just because the source data changed.

For scheduled reminder emails whose value changes over time, the send worker should check the latest business state to decide whether to cancel or refresh the job rather than blindly sending a stale snapshot.

### Template version must also be pinned

If a job is created today and prepared after a new template version is deployed, you must define which template the job uses. Storing `templateKey` and `templateVersion` makes content reproducible and helps investigate discrepancies.

Do not treat a template change as a reason to re-render every pending prepared email unless there is an explicit migration or invalidation policy.

## 26. Eligibility can change after preparation

A marketing email is prepared at 09:00, the user unsubscribes at 09:30, and the worker sends at 11:00. Even though it is READY, sending at 11:00 may no longer be permitted.

Therefore, the send worker must verify conditions **still valid at submission time**:

- Consent/preferences and suppression.
- Business deadline/expiry.
- Whether the recipient is still valid.
- Whether a token or workflow was revoked.
- Whether the campaign was paused/cancelled.
- Whether the provider account is disabled or in cooldown.

~~~text
Prepared at 09:00
      |
      v
READY_TO_SEND
      |
      +-- Recipient unsubscribed at 09:30
      |
      v
Send worker at 11:00
      |
      v
Recheck eligibility
      |
      +--> CANCELLED / SUPPRESSED
~~~

Do not invert this by always re-rendering everything right before send; only check the states that policy requires to be fresh.

## 27. TTL and business deadlines

Some emails lose value very quickly:

- OTP or password-reset tokens.
- Action confirmations required within a short time window.
- Reminders before an event start time.
- Coupons or promotions with an expiration date.

A job should carry `expiresAt` when the business requires it. Completing preparation does not guarantee the recipient should still receive the email.

Pre-submission conditions:

~~~text
now < expiresAt
AND job is READY or SEND_RETRY_WAIT
AND recipient remains eligible
AND provider budget is available
AND prepared artifacts are readable
~~~

If the next retry falls past expiry, stop instead of sending an expired email. For OTPs, do not generate a new token merely because SMTP retried if doing so breaks the original verification flow.

Artifact retention must be at least as long as the allowed retry/reconciliation window, plus a cleanup safety margin. Never let an object lifecycle rule delete an attachment while the outbox job is still READY/RETRY_WAIT.

## 28. Prioritizing transactional email during large campaigns

If a marketing campaign generates tens of thousands of prepared messages, they can saturate the send pool and delay OTPs or invoices.

Organizational approaches:

- Separate queues/batches per category.
- Separate rate budgets for transactional and marketing mail.
- Priority scheduling with starvation prevention.
- Appropriate SMTP accounts/providers per email type if policy permits.
- Caps on preparation jobs per campaign.
- Reserved capacity for high-priority emails.
- Tracking queue age and business deadlines by category.

Do not rely solely on a priority integer if workers keep draining a massive marketing queue. Enforce real capacity allocation and prevent starvation in both directions.

### Do not share the same thread pool for PDF generation and OTP sending

A heavy PDF generation task can occupy CPU/heap for a long time. If OTPs share the same executor, they wait even when SMTP is idle. Separating pools gives OTP sending dedicated capacity even when the preparation queue is overloaded.

## 29. Observability across the two stages

Measure the right latency components:

~~~text
Business event
     |
     +--> time waiting for preparation
     |
     +--> preparation duration
     |
     +--> time waiting for SMTP submission
     |
     +--> SMTP duration
     |
     +--> provider delivery delay (if available)
~~~

Suggested spans/metrics:

| Metric or span | Meaning |
| --- | --- |
| `mail.prepare.queue_wait` | Wait time before preparation starts |
| `mail.prepare.duration` | Duration to build content/artifacts |
| `mail.prepare.failures` | Failures by preparation failure class |
| `mail.prepared_artifact.bytes` | Size of persisted artifacts |
| `mail.send.queue_wait` | Time from READY until attempt starts |
| `mail.smtp.submit.duration` | Duration of the SMTP transport call |
| `mail.send.attempts` | Actual send attempt count |
| `mail.send.retry_wait` | Scheduled backoff duration |
| `mail.outbox.oldest_ready_age` | Age of oldest ready job |
| `mail.executor.rejected` | Executor overload |
| `mail.storage.open.failures` | Failed to open prepared artifact |

These are application-defined example names, not default Spring Mail metrics.

Logs need `notificationId` across stages, a distinct `attemptId` per SMTP send, `templateVersion`, category, provider, stage/outcome, and timestamps. Never log raw SMTP passwords, recipient email addresses as metric tags, HTML bodies, file bytes, or reset tokens.

### Tracing across async boundaries

The HTTP request trace and the outbox worker trace may differ. Use a stable `notificationId`, `businessEventId`, or span links for correlation. Do not keep an HTTP span open for hours waiting for delivery.

## 30. Sample structured logs

Preparation completed:

~~~json
{
  "event": "mail.preparation.completed",
  "notificationId": "N-123",
  "category": "TRANSACTIONAL",
  "templateVersion": "invoice-v2",
  "attachmentCount": 1,
  "artifactBytes": 245600,
  "preparationMs": 438,
  "status": "READY_TO_SEND"
}
~~~

Send attempt:

~~~json
{
  "event": "mail.smtp.attempt.completed",
  "notificationId": "N-123",
  "attemptId": "N-123-A2",
  "provider": "primary-smtp",
  "smtpDurationMs": 820,
  "outcome": "SUBMITTED",
  "status": "SUBMITTED"
}
~~~

If the provider queue ID is unknown, do not fabricate a placeholder value. For exceptions, log normalized error classes/codes and correlation IDs rather than printing raw MIME or stack traces containing sensitive data into broadly accessible logs.

### Distinguish accepted from delivered

When `JavaMailSender.send(...)` completes normally, the application may mark `SUBMITTED` under the transport contract. Only mark `DELIVERED` upon receiving a trustworthy provider delivery signal, not because MIME assembly finished.

## 31. Security when splitting the pipeline

The two stages may require different infrastructure permissions:

| Permission | Preparation worker | SMTP worker |
| --- | --- | --- |
| Read business data | Yes, as needed | Typically only reads prepared manifest |
| Render template/PDF | Yes | Typically no |
| Write prepared artifacts | Yes | Typically read-only |
| Read prepared attachments | Yes when creating/validating | Yes when sending |
| SMTP credentials | Not needed | Yes |
| Outbound SMTP network | Not needed | Yes |
| Update job status | Preparation states only | Send states only |
| Access provider event API | Not necessarily | Per dedicated integration |

Do not store SMTP tokens inside prepared manifests or queue payloads. Restrict tenant access on artifact storage and protect data at rest and in transit.

Prepared HTML, PDFs, and recipients can contain PII; apply appropriate retention policies, encryption, access control, and auditing. Users exercising rights to modify or delete data can affect prepared artifacts; design cancellation/cleanup to meet legal and business requirements.

## 32. When should you use @Async?

`@Async` is a convenient tool for running a task on another thread, but it does not by itself create a durable pipeline.

Simple example:

~~~java
@Service
public class MailPreparationTask {

    private final MailPreparationService preparation;

    public MailPreparationTask(
            MailPreparationService preparation) {
        this.preparation = preparation;
    }

    @Async("mailPreparationExecutor")
    public CompletableFuture<PreparedMail> prepare(
            MailIntent intent) {

        PreparedMail result = preparation.prepare(intent);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

This offloads the thread, but:

- The task queue usually lives in RAM.
- A process crash can lose tasks.
- Spring proxy/self-invocation rules can prevent `@Async` from actually running asynchronously.
- Exceptions in async tasks must be handled and persisted.
- The application still needs job state to retry after a restart.
- Do not wrap a long HTTP transaction around awaiting the result.

For critical transactional mail, `@Async` can act as an executor for a worker that **already fetched a job from a durable store**, not as the sole source of truth for mail requests.

## 33. Submission workers should not wait long via Thread.sleep

An example not to use for durable retries:

~~~java
try {
    sender.send(message);
} catch (MailException ex) {
    Thread.sleep(60_000);
    sender.send(message);
}
~~~

Sleeping holds a thread and can hold a DB transaction if called inside the wrong boundary. During an SMTP provider outage, many sleeping threads shrink capacity.

Instead:

~~~text
SMTP temporary error
         |
         v
Classify + compute backoff/jitter
         |
         v
Persist SEND_RETRY_WAIT + nextAttemptAt
         |
         v
Release worker thread
         |
         v
Poller resumes when due
~~~

If the provider requires a cooldown, the retry timestamp must not be earlier than that policy. Enforce max attempts and deadlines. For an `AMBIGUOUS` outcome after DATA, retrying can produce duplicates; require an explicit decision.

## 34. A two-stage worker example

The orchestration classes here are Java-like pseudocode illustrating transaction and I/O boundaries.

Preparation worker:

~~~java
public void processPreparation(UUID notificationId) {
    MailIntent intent = stateService.claimPreparation(
        notificationId
    );

    try {
        // No database transaction is held for rendering/storage I/O.
        PreparedMail prepared = preparation.prepare(intent);

        // Separate short transaction to persist manifest and READY.
        stateService.markReady(notificationId, prepared);
    } catch (TransientPreparationException ex) {
        stateService.schedulePreparationRetry(
            notificationId, ex
        );
    } catch (PermanentPreparationException ex) {
        stateService.markPreparationFailed(
            notificationId, ex
        );
    }
}
~~~

Submission worker:

~~~java
public void processSubmission(UUID notificationId) {
    PreparedMail prepared = stateService.claimReadyForSend(
        notificationId
    );

    if (!eligibility.isAllowedNow(notificationId)) {
        stateService.markSuppressed(notificationId);
        return;
    }

    try {
        // Rendering and durable artifact generation are already done.
        smtpAdapter.send(prepared);

        stateService.markSubmitted(notificationId);
    } catch (TransientSmtpException ex) {
        stateService.scheduleSendRetry(notificationId, ex);
    } catch (AmbiguousSmtpException ex) {
        stateService.markAmbiguous(notificationId, ex);
    } catch (PermanentSmtpException ex) {
        stateService.markSendFailed(notificationId, ex);
    }
}
~~~

Classes such as `stateService`, `eligibility`, `smtpAdapter`, and the exception types belong to application design. Note that `markSubmitted` can fail after the server already accepted the message, risking a duplicate retry when the lease is reclaimed. That is why outbox-driven SMTP usually achieves at-least-once attempt semantics rather than guaranteed exactly-once delivery.

Implement state transitions using short transactions and conditional status/version updates so a stale worker cannot overwrite a newer worker's result after its lease expires.

## 35. Failure modes by stage

| Incident | Preparation | Submission | How to handle |
| --- | --- | --- | --- |
| Template does not exist | Failed | Not run | Mark `PREP_FAILED`, fix template |
| PDF generator temporarily slow | Retry | Not run | Backoff in preparation |
| Storage upload succeeded, DB failed | Orphaned artifact | Not run | Cleanup/reconciliation |
| Artifact deleted after READY | Done | Unreadable | Investigate retention; possibly reprepare |
| Wrong SMTP AUTH credentials | Done | Failed | Fix credentials; do not hot-retry |
| Transient SMTP 421 | Done | Retry | Backoff + jitter |
| SMTP size exceeded | Done | Rejected | Adjust content; do not resend unchanged |
| SMTP timeout after DATA | Done | AMBIGUOUS | Provider reconciliation/duplicate policy |
| Process crash during PREPARING | May be incomplete | No | Reclaim lease, idempotent artifacts |
| Process crash after SMTP accepted | Done | DB outcome unsaved | Duplicate send risk |
| Recipient unsubscribes before send | Done | Should not submit | Suppress/cancel |
| Email expired | May be done | Should not submit | Cancel/expire |

A failure state may require re-preparation if an artifact is no longer valid; however, never let preparation retries silently regenerate different content for a finalized transactional email without policy approval.

## 36. Performance and reliability testing

You can structure the test suite in layers:

### Unit tests

- Preparation produces correct plain/HTML and attachment manifests.
- Template version is pinned.
- Send worker does not invoke the renderer.
- Sender opens a fresh stream per attachment.
- Eligibility/expiry checks run before SMTP.
- State transitions and retry policies match each stage.

### Integration tests with database and object storage

- Intent/outbox row is inserted in the same business transaction.
- Transaction rollback does not leave a send job.
- Prepared manifests/attachments remain readable by a different worker process.
- Two preparation workers cannot own the same job simultaneously.
- Upload success followed by DB commit failure does not publish READY.
- Worker crash/lease expiry triggers reclaim.
- Artifact cleanup does not delete files for active jobs.
- Concurrent workers do not submit above account limits.

### SMTP integration tests

Use GreenMail or an SMTP capture server:

1. Prepare an email with PDF/HTML.
2. Persist the manifest and attachment.
3. Invoke the submission worker using a real `JavaMailSender`.
4. Read the MIME message received by the server.
5. Verify subject, recipient, body, and attachment filename/bytes.
6. Confirm outbox transitions to `SUBMITTED`.
7. For transient failures, verify retries reuse the same prepared artifact.
8. For timeout after DATA, confirm the `AMBIGUOUS` policy.
9. Never hit production providers or real addresses in CI.

### Load/performance tests

Measure preparation throughput, send throughput, queue wait, heap/GC, storage read latency, SMTP duration, and backlog separately. Build workloads mixing lightweight emails and large PDFs/images; testing only a few KB of plain text hides production memory pressure.

## 37. Anti-patterns to avoid

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| Rendering PDF and sending SMTP in HTTP transaction | Long-held threads/DB locks | Intent + two-stage workers |
| Sharing one pool for CPU rendering and SMTP I/O | Workloads block one another | Separate capacity |
| Re-rendering everything on every SMTP retry | Wastes CPU and may drift data | Persist prepared artifacts |
| Queue holding live `MimeMessage` in RAM | Not durable, awkward resource lifecycle | Serializable manifest + refs |
| Storing whole large PDFs in DB/outbox JSON | Huge payloads, GC/DB pressure | Durable object references |
| Storing ephemeral container temp paths | Other workers cannot read them | Shared durable storage |
| Using a one-shot `InputStream` for attachments | Empty attachment or read error | Repeatable stream source |
| Marking READY before upload completes | Missing artifact at send stage | Persist artifacts first, then READY |
| Assuming DB and object store commit atomically | Orphaned or missing files | Reconciler/cleanup and status ordering |
| Treating executor queue as a durable queue | Jobs lost on restart | Outbox/broker |
| Unbounded queues | Heap overflow and rising latency | Bounded queues/backpressure |
| Claiming more jobs than executor capacity | Leases expire before execution | Claim batches sized to capacity |
| Increasing SMTP threads without checking quota | Provider throttling | Rate/concurrency limits |
| Retrying all errors across both stages | Retry storms, looping permanent errors | Stage-specific classifier |
| Retrying post-DATA timeout as definitely unsent | Duplicate emails | `AMBIGUOUS`/reconciliation |
| Not pinning snapshot/template version | Email changes across retries | Immutable prepared content |
| Skipping unsubscribe recheck after READY | Sending disallowed mail | Recheck at send time |
| Deleting artifacts immediately after a failed submit | Missing files on retry | Lifecycle-aligned retention |
| Calling SMTP accepted "delivered" | Inaccurate reporting | Separate provider delivery events |
| Logging raw HTML/attachments/tokens | Data exposure | Structured IDs and redaction |

## 38. Step-by-step rollout roadmap

A Spring project can adopt this incrementally:

1. **Profile the current send path**: identify render time, file I/O, SMTP latency, and request latency.
2. **Define `MailIntent`** with stable notification IDs and business event IDs.
3. **Persist intents in the business transaction** when send requests require durability.
4. **Separate `MailPreparationService`** from SMTP transport.
5. **Design a `PreparedMail` manifest** holding subject/plain/HTML and immutable artifact refs.
6. **Store large files in durable storage** with checksums, sizes, versions, and retention.
7. **Add a two-stage state machine** with leases and conditional updates.
8. **Create preparation workers** sized for CPU/memory concurrency.
9. **Create SMTP workers** with dedicated capacity and rate limits.
10. **Build `MimeMessage` at send time** from the manifest and repeatable streams.
11. **Apply stage-specific retry/backoff** without redundantly re-rendering on transient SMTP errors.
12. **Check eligibility/deadlines before sending** even when content is already prepared.
13. **Track queue wait and processing times separately** to locate bottlenecks.
14. **Test crashes, retries, orphaned storage, SMTP ambiguity, and concurrency**.
15. **Add cleanup and retention** for artifacts no longer referenced by active jobs.

You do not need microservices right away. A monolith with two worker pools and a durable outbox achieves most of the benefits as long as job ownership and failure recovery are well designed.

## 39. Key takeaways

- Preparation and SMTP submission have distinct resource profiles, failure modes, and retry policies.
- Separating stages keeps PDF/template rendering from stalling SMTP workers and keeps SMTP throttling from forcing content re-renders.
- Never send directly inside a business database transaction when high reliability is required.
- A durable outbox/queue is the source of truth; `@Async` only switches threads and does not provide durability.
- `PreparedMail` should be a manifest containing text and artifact references, not a live `MimeMessage` sitting in RAM.
- Attachment resources must be able to open a fresh stream for each read/attempt.
- MIME assembly may still read attachments during the send stage; understand lazy stream behavior.
- Artifacts and manifests must be persisted in a safe order, with cleanup for orphaned objects.
- Snapshots and template versions must be managed so retries do not silently alter the email.
- Recipient preferences and deadlines can change after preparation and must be rechecked before sending.
- Separate pools, bounded queues, rate limits, and backpressure keep CPU, memory, and SMTP quotas under control.
- Preparation retries differ from SMTP retries; never replay the whole pipeline when only network delivery failed.
- Timeouts after DATA can be `AMBIGUOUS`; retrying carries duplicate risk.
- Queue wait, preparation duration, artifact I/O, and SMTP duration should be measured separately.
- `SUBMITTED` means the relay/transport accepted the message as observed; it does not prove `DELIVERED`.
- Worker crashes and restarts require lease recovery, idempotency, and reconcilable state.

**Core principle:** Let **preparation workers produce reusable content that survives restarts**, and let **submission workers assemble MIME and deliver via SMTP within quota, deadline, and retry policies**. This boundary enables Spring Framework Mail to handle large attachments or high email volumes without CPU rendering, storage I/O, and outbound network sends dragging one another down, while making failures far easier to observe and recover from.

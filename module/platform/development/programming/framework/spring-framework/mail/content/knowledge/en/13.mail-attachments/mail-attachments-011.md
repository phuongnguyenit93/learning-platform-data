# Deleting Temporary Files After Sending or Failure

In **Spring Framework Mail**, an email may attach a PDF, CSV, image, or document generated during business processing. Many applications create these files in a temporary directory and use `MimeMessageHelper.addAttachment(...)` to send them. Once sending finishes, temporary files must be cleaned up to avoid consuming disk space, retaining personal data too long, or filling up the filesystem.

The issue is not just calling `Files.delete(...)`. The application must determine **who owns the file**, **when the library no longer needs to read the file**, **what happens when sending fails**, and **whether the file must be kept for retries**. Deleting too early can yield an empty attachment or cause sending to fail. Deleting only on success leaves orphaned files behind after exceptions. Deleting right after the first attempt in a retry-enabled system leaves the worker with no data for retries.

Fundamental principle:

> A temporary file created for a send must have a clear owner and a well-defined end of lifecycle. For synchronous sending, clean up the file in `finally` after the send call finishes. For asynchronous sending or retries, clean up only after the job completes per retention policy.

## 1. Lifecycle of a temporary attachment

A workflow sending an email with an attachment typically includes these steps:

1. Generate the file content (such as an invoice PDF).
2. Write bytes to a temporary file with a unique name.
3. Create `MimeMessage` and declare the attachment using a `Resource` pointing to the file.
4. Call `JavaMailSender.send(...)`.
5. When the synchronous send operation completes, delete the temporary file if no longer needed.
6. If deletion fails, record it for retry cleanup; do not let cleanup failure mask the send result.

~~~mermaid
flowchart TD
    A["Generate attachment content"] --> B["Create unique temporary file"]
    B --> C["Write bytes to file"]
    C --> D["Create MimeMessage + addAttachment"]
    D --> E["JavaMailSender.send"]
    E --> F{"Send call finished?"}
    F -->|Success| G["Run cleanup"]
    F -->|Exception| G
    G --> H{"File deleted?"}
    H -->|Yes| I["End file lifecycle"]
    H -->|No| J["Log safely / record cleanup retry"]
~~~

**The cleanup point is after `send(...)` returns or throws an exception**, not immediately after `addAttachment(...)`. Spring Mail/Jakarta Mail's send method typically performs transport synchronously within that call; while building and transmitting MIME, the library may need to read the resource. Deleting before the send call finishes can make the data unavailable.

This assumes the sender executes synchronously like standard `JavaMailSenderImpl`. If the application wraps the sender with a custom asynchronous mechanism, determine when the future/callback actually finishes reading the attachment before cleaning up.

## 2. Why delete on both success and failure?

Temporary files can contain personal data or business information: invoices, reports, customer addresses, transaction figures. If left behind, a file can:

- grow temp directory disk usage over time;
- be read by processes or accounts with filesystem access;
- appear in backups, snapshots, or monitoring tools;
- cause new file creation to fail when the disk fills up;
- expose data past the job's processing lifetime.

For example, a service generates 100 PDFs per hour at 5 MB each. Without cleanup, disk usage grows by roughly 500 MB per hour (excluding overhead). In container environments with constrained filesystems, this can halt file creation or impact other components.

### 2.1. Send succeeds

When `sender.send(mime)` returns normally, the synchronous transport has completed the submission operation per the sender's contract. If the attachment was created solely for that send and is not needed elsewhere, the temporary file can be deleted right afterward.

Note: **send success does not mean the email reached the Inbox or the recipient downloaded the file**. `JavaMailSender` usually only tells you the send/submission operation raised no synchronous errors. Temporary files can be cleaned up once the transport has finished consuming the bytes, without waiting for the recipient to open the email.

### 2.2. Send fails

Errors can occur when:

- creating or writing the file fails;
- the resource is unreadable;
- building the MIME message fails;
- the SMTP host is unreachable;
- SMTP authentication fails;
- the server rejects the recipient or content;
- the connection times out during sending.

For a synchronous send without retries, the temporary file must also be deleted on every exception path. If cleanup is only placed after `send(...)`, the deletion line will not execute when `send` throws an exception.

## 3. Using try/finally to guarantee cleanup

Java provides `try/finally` to run cleanup regardless of whether the sending block exits normally or throws an exception.

Example:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TemporaryFileCleanup {
    private static final Logger log =
            LoggerFactory.getLogger(TemporaryFileCleanup.class);

    public void process(Path tempFile) throws IOException {
        try {
            // Read or send the file.
            sendAttachment(tempFile);
        } finally {
            try {
                Files.deleteIfExists(tempFile);
            } catch (IOException cleanupException) {
                log.warn(
                        "Could not delete temporary attachment file",
                        cleanupException
                );
            }
        }
    }

    private void sendAttachment(Path path) {
        // Perform synchronous send operation.
    }
}
~~~

`finally` executes when the `try` block exits, even on exceptions. `Files.deleteIfExists(...)` deletes the file if it still exists; if it was already deleted beforehand, it does not fail merely because the file is gone.

In this example, the cleanup exception is logged and not rethrown so it **does not mask the original send error**. If sending succeeded yet cleanup failed, do not automatically report "email send failed" just because the temporary file could not be deleted; message submission and file cleanup are two independent outcomes.

### 3.1. Avoid letting cleanup exceptions mask send errors

An error-prone pattern:

~~~java
try {
    sender.send(mime);
} finally {
    Files.delete(tempFile); // May throw IOException.
}
~~~

If `sender.send(...)` throws `MailException` while `Files.delete(...)` also throws `IOException`, the exception from `finally` can become the exception seen by the caller, losing the original send error context.

There are two ways to manage this:

- **Record cleanup failures separately** and do not throw them as send failures; suitable when the email was already submitted and a janitor can retry cleanup later.
- **Use try-with-resources** with a `close()`-implementing resource; Java attaches close exceptions as `suppressed exceptions` if the primary block already failed. However, design it so a close failure after a successful send is not misinterpreted as a send failure that triggers duplicate sends.

## 4. Complete example: create temp PDF, send, and delete

Suppose the application already has PDF bytes generated from invoice data. We write the bytes to a temporary file, attach via `FileSystemResource`, and delete the file in `finally`:

~~~java
package com.example.mail.application;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private static final Logger log =
            LoggerFactory.getLogger(InvoiceMailService.class);

    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes)
            throws IOException, MessagingException {

        Path tempFile = Files.createTempFile("invoice-", ".pdf");
        String tempId = tempFile.getFileName().toString();

        try {
            Files.write(tempFile, pdfBytes);

            MimeMessage mime = sender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom("billing@example.com");
            helper.setTo(recipient);
            helper.setSubject("Invoice " + invoiceNumber);
            helper.setText(
                    "Your invoice is attached to this email."
            );
            helper.addAttachment(
                    "Hóa đơn " + invoiceNumber + ".pdf",
                    new FileSystemResource(tempFile.toFile()),
                    "application/pdf"
            );

            sender.send(mime);
        } finally {
            try {
                Files.deleteIfExists(tempFile);
            } catch (IOException cleanupException) {
                // Record cleanup separately; do not turn a cleanup error
                // into a conclusion that the email was not submitted.
                log.warn(
                        "Could not clean temporary invoice file: {}",
                        tempId,
                        cleanupException
                );
            }
        }
    }
}
~~~

Execution flow:

1. `Files.createTempFile(...)` creates a unique temporary file in the OS default temporary directory.
2. `Files.write(...)` writes the PDF content.
3. `FileSystemResource` supplies the file to `MimeMessageHelper`.
4. `addAttachment(...)` adds the MIME part with a display name and content type.
5. `sender.send(mime)` performs the synchronous send.
6. Regardless of whether writing, MIME building, or sending fails, `finally` attempts to delete the file.

The filename on disk is generated separately by the OS, e.g. `invoice-8349271.pdf`; the display name shown to the recipient is `Hóa đơn INV-2026-001.pdf`. Separating the two avoids leaking internal storage names and allows Unicode display names.

### 4.1. Why create the file before the try block?

`Files.createTempFile(...)` must return a `Path` before `finally` can delete it. If file creation fails, there is no file to clean up and the exception propagates. Once the path is created, all file writing, MIME building, and sending steps reside inside `try` so `finally` guarantees cleanup.

If `Files.write(...)` fails partway through, the file may already exist; `finally` still attempts to remove it.

### 4.2. Using a dedicated application temp directory

Files can be created in a dedicated managed directory:

~~~java
Path tempDirectory = Path.of("/var/app/mail-tmp");
Files.createDirectories(tempDirectory);

Path tempFile = Files.createTempFile(
        tempDirectory,
        "invoice-",
        ".pdf"
);
~~~

A dedicated directory helps:

- restrict where the application creates files;
- configure permissions for the service user;
- track disk usage and file ages;
- run orphan cleanup jobs by prefix/TTL;
- avoid accidentally deleting temp files of other processes.

On Windows, Linux, and containers, filesystem permissions are configured differently. Ensure the directory is accessible only to the application account and authorized reader processes. For sensitive documents, consider encrypted volumes and appropriate retention.

## 5. Using a helper to manage temporary files

If multiple services need the same file creation and cleanup rules, lifecycle management can be encapsulated in a small class. This class creates the file, exposes `Path`, and cleans up when closed:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class TemporaryAttachment implements AutoCloseable {
    private static final Logger log =
            LoggerFactory.getLogger(TemporaryAttachment.class);

    private final Path path;
    private final String cleanupId;

    private TemporaryAttachment(Path path) {
        this.path = path;
        this.cleanupId = path.getFileName().toString();
    }

    public static TemporaryAttachment create(
            Path directory,
            String prefix,
            String suffix) throws IOException {
        Files.createDirectories(directory);
        Path path = Files.createTempFile(directory, prefix, suffix);
        return new TemporaryAttachment(path);
    }

    public Path path() {
        return path;
    }

    @Override
    public void close() {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            log.warn(
                    "Could not clean temporary attachment: {}",
                    cleanupId,
                    ex
            );
        }
    }
}
~~~

Usage:

~~~java
try (TemporaryAttachment temp =
             TemporaryAttachment.create(
                     Path.of("/var/app/mail-tmp"),
                     "invoice-",
                     ".pdf")) {

    Files.write(temp.path(), pdfBytes);

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");
    helper.setTo(recipient);
    helper.setSubject("Invoice");
    helper.setText("Please see the attached file.");
    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(temp.path().toFile())
    );

    sender.send(mime);
}
~~~

When exiting the `try` block, Java invokes `close()` even on exceptions. In this example, `close()` catches deletion errors and logs them so it does not alter a completed send result. If an organization wants cleanup failures to be monitorable errors, the helper can emit an event/metric or create a cleanup task instead of silently ignoring them.

**Never use this helper to manage user-uploaded source files or files owned by another workflow.** It should own only temporary files it created itself. If given an existing `Path` from outside, never automatically delete it on close unless ownership is explicitly transferred.

## 6. Should ByteArrayResource be used instead of temporary files?

Not every attachment needs to be written to the filesystem. If content is already in memory and small/medium in size, it can be attached directly:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Advantages:

- creates no temporary files;
- requires no filesystem cleanup;
- fits existing, size-bounded byte data.

Disadvantages:

- all bytes occupy heap memory for the object's lifetime;
- many concurrent emails with large attachments can cause memory pressure;
- if queues/jobs need retries across restarts, an in-memory byte array is not durable storage.

### 6.1. Choosing by size and data source

| Source/characteristic | Usually suitable approach |
| --- | --- |
| Small PDF already in a byte array | `ByteArrayResource` |
| File already created on the filesystem | `FileSystemResource` |
| Static file packaged in the application | `ClassPathResource` |
| Large file, re-openable multiple times | Resource/`InputStreamSource` with clear read lifecycle |
| File needing retries across restarts | Object storage or durable spool with ID/version |
| Data living only for one synchronous send | Byte array or temp file, depending on memory limits |

Choosing a resource does not change the principle: if creating a temp file, define the owner and cleanup timing; if using in-memory bytes, enforce size limits and know when references are released.

## 7. When is it safe to delete the file after send?

With `JavaMailSenderImpl` and standard Jakarta Mail transport, `send(...)` runs synchronously: when the method returns or throws, that call is finished. This is the appropriate milestone to delete a file used only for that send.

However, inspect the architecture if:

- the sender is a custom wrapper that merely enqueues the send and returns immediately;
- the service uses `@Async` and passes the file path to another executor;
- a callback or publisher has not finished serializing MIME yet;
- the resource is reused by another task after sending;
- the system must retain the file for retries or incident investigation.

### 7.1. Do not delete immediately after addAttachment

Do not do this:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(tempFile.toFile())
);

Files.deleteIfExists(tempFile); // Too early.
sender.send(mime);
~~~

`addAttachment` configures the part and data source; depending on when the provider reads the resource, bytes may not have been consumed yet. The file must remain present throughout the sending process.

### 7.2. Do not delete immediately when the producer enqueues an async job

Suppose a producer creates a file and enqueues it:

~~~java
queue.add(new MailJob(tempFile.toString(), recipient));
Files.deleteIfExists(tempFile); // Worker may not have read the file yet.
~~~

The worker receives a path to an already-deleted file. If the producer and worker run on two different machines or containers, a local path might not even exist on the worker machine to begin with.

In an asynchronous model, **the producer must not delete the file after enqueuing** if the job still needs it. Cleanup responsibility belongs to the job/artifact lifecycle manager after the worker completes or the job is cancelled/expired.

## 8. Asynchronous sending and retries: how long to keep the file?

A send attempt can fail transiently. If an email needs retries, deleting the attachment in the `finally` block of **each attempt** leaves subsequent attempts with no file to read.

Distinguish:

- **Cleanup after a single attempt:** appropriate only if there are no retries or the data can be safely regenerated.
- **Cleanup after terminal state:** appropriate for retryable queues; delete only once the job completes, is cancelled, or exhausts its retry policy.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING
    PROCESSING --> SUBMITTED: sender completes without error
    PROCESSING --> RETRY_WAIT: retryable error
    RETRY_WAIT --> PROCESSING: retry time reached
    PROCESSING --> FAILED_FINAL: retries exhausted or permanent error
    SUBMITTED --> CLEANUP
    FAILED_FINAL --> CLEANUP
    CLEANUP --> [*]
~~~

`SUBMITTED` indicates the sender completed the submission operation; it does not assert Inbox delivery. If the provider sends a bounce webhook later, that is a separate delivery state and does not mean the initial send's temp PDF must be kept.

### 8.1. Jobs should reference durable artifacts

If workers may run after the producer process stops, do not rely on temporary files in the producer's OS temp directory. One option is storing attachments in object storage or a durable spool area:

~~~text
Producer
  |
  +--> generate file -> upload artifact with key/version
  |
  +--> enqueue MailJob:
          jobId
          recipient
          subject
          artifactKey
          artifactVersion
  |
Worker
  |
  +--> fetch exact artifact version
  +--> build MimeMessage
  +--> send
  +--> update job status
  |
Cleanup policy
  |
  +--> delete artifact when job is terminal and retention allows
~~~

Payloads only carry the artifact's ID or key, never local paths. Artifacts require restricted access permissions and immutable versions so retries always read the exact same file.

### 8.2. Do not delete files while retries remain possible

Example:

~~~text
Job J-100:
  status = RETRY_WAIT
  attempts = 1
  attachmentKey = invoices/2026/INV-100.pdf
  retryAt = 2026-11-12T10:05:00Z
~~~

In the `RETRY_WAIT` state, the file/artifact must still be retained. Only when:

- submission succeeded and the job needs no retries;
- the job was cancelled by business rules;
- attempts are exhausted and it is marked `FAILED_FINAL`;
- or retention expires per policy;

can cleanup delete the artifact. If the system allows manual retries after `FAILED_FINAL`, decide whether to retain the file during support windows or require regenerating the artifact.

### 8.3. A send failure does not always tell whether SMTP received the message

If the client loses connection after transmitting the content but before receiving the final response, the application may not know whether the server accepted the email. Retrying can create duplicate emails.

This is an **idempotency and send-state** problem, not solved by keeping or deleting the file. Jobs need stable IDs, attempt counts, timestamps, and statuses. If the provider supports idempotency keys or message ID lookups, use them per their contract. With raw SMTP, never promise exactly-once delivery based solely on a queue.

## 9. Cleaning up temp files when the application crashes

`finally` runs when Java control flow exits a try block normally, including via exceptions. However, it is not guaranteed to run when:

- the process is forcefully killed;
- the machine/container loses power or is terminated immediately;
- the JVM crashes;
- the node is reclaimed before cleanup runs;
- the filesystem suffers a critical failure.

Therefore, production systems may need a **janitor job** to find and clean up orphaned temporary files after a period of time.

### 9.1. Dedicated directory and identifying prefixes

Example:

~~~text
/var/app/mail-tmp/
  invoice-a83f....pdf
  report-1b29....csv
  attachment-7e10....zip
~~~

Delete only files that:

- reside inside the dedicated directory managed by the mail service;
- carry the application's identifying prefix/metadata;
- are older than the configured TTL;
- are not referenced by any active job;
- are not locked or in use by another worker if the OS or app needs to check.

Never run recursive deletion on the machine's shared system temp directory. That could delete files belonging to other applications or users.

### 9.2. Simple janitor example

A scheduled job can delete files older than a threshold inside the **dedicated mail temp directory**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailTempJanitor {
    private static final Logger log =
            LoggerFactory.getLogger(MailTempJanitor.class);

    private final Path tempDirectory =
            Path.of("/var/app/mail-tmp");

    private final Duration maxAge = Duration.ofHours(24);

    @Scheduled(fixedDelayString = "PT1H")
    public void removeOldFiles() {
        if (!Files.isDirectory(tempDirectory)) {
            return;
        }

        Instant cutoff = Instant.now().minus(maxAge);

        try (Stream<Path> files = Files.list(tempDirectory)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName()
                            .toString().startsWith("mail-"))
                    .forEach(path -> deleteIfExpired(path, cutoff));
        } catch (IOException ex) {
            log.warn("Could not scan mail temporary directory", ex);
        }
    }

    private void deleteIfExpired(Path path, Instant cutoff) {
        try {
            Instant modifiedAt = Files.getLastModifiedTime(path).toInstant();
            if (modifiedAt.isBefore(cutoff)) {
                Files.deleteIfExists(path);
            }
        } catch (IOException ex) {
            log.warn("Could not clean an old mail temporary file", ex);
        }
    }
}
~~~

For the job to run, the application must enable scheduling with appropriate configuration (e.g. `@EnableScheduling`). This example is only a basic janitor, **insufficient for every retry system**: if a valid job can wait longer than 24 hours, the janitor could delete a file that is still needed. Production should check job/artifact state before deleting, or use a storage lifecycle policy tied to managed state/retention.

### 9.3. Controlling paths and symlinks

If a path is retrieved from a job or database, never concatenate arbitrary strings onto the temp directory:

~~~java
Path candidate = tempDirectory.resolve(untrustedName).normalize();
if (!candidate.startsWith(tempDirectory.normalize())) {
    throw new SecurityException("Invalid temporary file path");
}
~~~

This check catches basic path traversal cases. In environments where others might create symlinks or modify the filesystem concurrently, add access permission policies, real file-type checks, and platform-appropriate safe filesystem operations. A better approach is storing an **application-generated opaque ID** instead of accepting external path names.

## 10. Do not confuse deleting a file with secure physical erasure

`Files.deleteIfExists(path)` asks the filesystem to remove the file entry. That **does not guarantee the bytes are overwritten or physically gone** immediately from the storage device. With SSDs, copy-on-write filesystems, snapshots, backups, or distributed storage, removing a filename does not mean data cannot be recovered.

If attachments contain sensitive information:

- restrict read permissions on the temp directory;
- use encrypted volumes/storage at an appropriate level;
- limit retention windows and backup/snapshot exposure;
- minimize sensitive data written to files;
- apply deletion/retention mechanisms meeting legal and organizational policies;
- never log file bytes, contents, or paths containing personal info.

Do not write custom byte-overwriting functions before deletion and claim "secure delete" across all filesystems. That cannot be guaranteed on SSDs, journaling filesystems, snapshots, or platform-managed storage.

## 11. Managing multiple temporary files in a single email

An email can have multiple attachments:

~~~java
List<Path> temporaryFiles = new ArrayList<>();
~~~

If creating files one by one, ensure **every created file is cleaned up**, even if creating the third file fails after the first two were already created.

Example:

~~~java
List<Path> temporaryFiles = new ArrayList<>();

try {
    Path invoice = createTemporaryInvoice();
    temporaryFiles.add(invoice);

    Path detail = createTemporaryDetail();
    temporaryFiles.add(detail);

    Path terms = createTemporaryTerms();
    temporaryFiles.add(terms);

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");

    helper.setTo(recipient);
    helper.setSubject("Order documents");
    helper.setText("The documents are attached.");

    helper.addAttachment(
            "Invoice.pdf",
            new FileSystemResource(invoice.toFile())
    );
    helper.addAttachment(
            "Details.xlsx",
            new FileSystemResource(detail.toFile())
    );
    helper.addAttachment(
            "Terms.pdf",
            new FileSystemResource(terms.toFile())
    );

    sender.send(mime);
} finally {
    for (Path path : temporaryFiles) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            log.warn("Could not clean a temporary mail attachment", ex);
        }
    }
}
~~~

This example assumes the `createTemporary...` methods return created files and a `log` logger exists. Each path is added to the list right after successful creation, so if a subsequent creation step fails, earlier files are still cleaned up in `finally`.

A helper managing multiple attachments can reduce code duplication, provided it ensures:

- it only tracks files owned by the helper;
- it never deletes source files owned by the caller;
- it never skips already-created files when a data-write step fails;
- it records cleanup failures without masking send errors;
- it never cleans up files still needed for retries.

## 12. When temporary files are created from an InputStream

Content can be received from a stream source and written to a file:

~~~java
Path tempFile = Files.createTempFile("attachment-", ".bin");
try {
    try (InputStream input = sourceStream) {
        Files.copy(
                input,
                tempFile,
                StandardCopyOption.REPLACE_EXISTING
        );
    }

    // Use tempFile as attachment and send.
} finally {
    try {
        Files.deleteIfExists(tempFile);
    } catch (IOException ex) {
        log.warn("Could not clean temporary attachment", ex);
    }
}
~~~

`InputStream` must be closed after copying. The temporary file is retained until the sender finishes reading the resource. If the stream is read-once, writing to a file lets the worker re-read the file as needed, though if retries span restarts, the file must live on durable storage rather than a process temp directory.

With Spring resources, understand whether an `InputStreamSource` can be opened multiple times. A source supplying a stream only once does not fit every MIME processing path, because providers may need to re-open it while serializing or measuring content.

## 13. Handling cleanup errors separately from send errors

An email send operation and a file deletion operation have two independent outcomes:

| Send | Cleanup | Meaning | Action |
| --- | --- | --- | --- |
| Succeeded | Succeeded | Mail submitted; file cleaned up | Done |
| Failed | Succeeded | Mail attempt failed; file cleaned up | Classify send error, retry per policy |
| Succeeded | Failed | Mail submitted; file left behind | Log cleanup failure and re-clean; avoid resending just for cleanup |
| Failed | Failed | Mail attempt failed; file left behind | Record both errors; cleanup job/ops handles file |

### 13.1. Why should a cleanup failure not trigger an email retry?

Suppose:

1. The SMTP server accepts the email and `sender.send(...)` returns.
2. `Files.deleteIfExists(...)` fails due to permissions or a locked file.
3. The service throws a generic exception.
4. The caller misinterprets it as a send failure and retries.

The result can be **two identical emails**, even though the only error was cleanup. Therefore, store submission status separately from cleanup status. If cleanup fails, emit a metric/log/cleanup record; never change `SUBMITTED` to `FAILED_TO_SEND`.

### 13.2. Do not log sensitive data

Logs should contain:

~~~text
mailJobId=job-812
attachmentId=att-44
cleanupResult=FAILED
errorType=AccessDeniedException
~~~

Avoid logging:

- full file bytes;
- invoice or report contents;
- tokens or authentication credentials;
- full paths containing customer names/sensitive record IDs unnecessarily;
- full email bodies.

An application-generated random ID is sufficient to trace temp files in most situations.

## 14. Testing cleanup on send success and failure

Two baseline branches should be tested:

1. When the sender returns normally, the temporary file no longer exists.
2. When the sender throws an exception, the temporary file is still cleaned up.

One way to test is extracting file creation and sending into a service using a dedicated temp directory. JUnit provides `@TempDir` to manage directories in tests:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;

class TemporaryInvoiceMailServiceTest {
    @TempDir
    Path tempDirectory;

    @Test
    void removesTemporaryFileAfterSuccessfulSend() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        TemporaryInvoiceMailService service =
                new TemporaryInvoiceMailService(sender, tempDirectory);

        Path created = service.createAndSend("customer@example.net");

        assertFalse(Files.exists(created));
        verify(sender).send(org.mockito.ArgumentMatchers.any(
                jakarta.mail.internet.MimeMessage.class));
    }

    @Test
    void removesTemporaryFileWhenSendFails() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        doThrow(new MailSendException("SMTP unavailable"))
                .when(sender).send(
                        org.mockito.ArgumentMatchers.any(
                                jakarta.mail.internet.MimeMessage.class));

        TemporaryInvoiceMailService service =
                new TemporaryInvoiceMailService(sender, tempDirectory);

        Path created = service.createAndSend("customer@example.net");

        assertFalse(Files.exists(created));
    }
}
~~~

This test is an **illustrative skeleton**: to inspect the path after the method throws an exception, the service can accept a test callback/observer or extract a trackable file-creating component. A cleaner test design passes a fake `TemporaryAttachmentStore` recording created paths, then asserts the file does not exist after each branch. Do not catch the exception and assume a path was returned when the method could not return due to throwing.

### 14.1. Extracting the store for clear testing

Example interface:

~~~java
public interface TemporaryAttachmentStore {
    Path create(String prefix, String suffix) throws IOException;
    void deleteQuietly(Path path);
}
~~~

The service receives the store via its constructor. In tests, a real store can use `@TempDir` and retain the last path; a fake store can record create/delete calls. This keeps cleanup testing independent of system directories or filename guessing.

### 14.2. Testing file creation and write errors too

Beyond SMTP errors, test:

- temp directory missing or lacking write permission;
- filesystem out of disk space;
- file write failing partway through;
- unreadable resource;
- oversized attachment;
- file deletion permission denied or file locked.

If the file was never created, there is nothing to delete. If the file was created yet partially written, cleanup must still run. If cleanup fails, there must be observability and handling for orphaned files.

## 15. Notes on large files and system resources

For large attachments, using temp files usually reduces heap pressure compared to holding all bytes in a `byte[]`, in exchange for requiring filesystem management:

- cap maximum allowed size per file;
- cap total attachment size per email;
- set quotas for the temp directory;
- monitor free disk space, file count, and file age;
- clean up orphaned files by TTL;
- limit concurrent workers processing attachments;
- enforce timeouts for generation and sending.

For example, if 20 workers concurrently create 50 MB files, temp space demand can exceed 1 GB. Even though every send eventually deletes its file, enough space is still required for concurrent active sends.

If the provider limits total message size, add Base64 overhead and MIME headers. When files exceed limits, consider sending an authenticated, time-limited download URL instead of an attachment.

## 16. When temporary files contain sensitive data

Invoices, statements, personal reports, and internal documents can contain data requiring protection. Deleting files after sending is one part of the data lifecycle, but does not replace other controls.

### 16.1. Directory permissions

- Use a dedicated application directory.
- Allow only the service account to create/read files.
- Never store temp files in public web directories or externally synced folders.
- Never grant broad read access to all users on the host.
- In containers, review volume mounts and in-container user permissions.

### 16.2. Random filenames

`Files.createTempFile` generates unique names, reducing collision and name-guessing risks. Never construct names like:

~~~java
Path path = tempDirectory.resolve(
        "invoice-" + customerName + ".pdf");
~~~

Customer names can contain unsafe characters, leak information, and create hard-to-control paths. Use a fixed prefix, file-type suffix, and let the API generate the random segment.

### 16.3. Deletion does not equal secure physical erasure

File deletion commands do not guarantee data is gone from SSDs, snapshots, or backups. When high security is required:

- encrypt volumes or storage;
- minimize sensitive data written to disk;
- apply retention to backups and snapshots;
- use storage supporting crypto-erasure where available;
- never claim secure erasure based solely on `Files.deleteIfExists`.

## 17. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Deleting file only after `send` without `finally` | File left behind when `send` throws | Clean up in `finally` or resource owner |
| Deleting immediately after `addAttachment` | Provider may not have read the file yet | Retain file until synchronous send finishes |
| Using local files for jobs running on other nodes | Worker cannot find the path | Store artifacts in shared/durable storage |
| Deleting file in producer right after enqueue | Worker cannot read attachment | Let worker/artifact lifecycle manage cleanup |
| Deleting file after first attempt while retries remain | Retries lack attachment | Retain file until terminal state |
| Cleanup exception overwrites SMTP error | Root cause lost, wrong retry behavior | Record cleanup failure separately, preserve send result |
| Sharing one temp file across multiple workers | One worker deletes while another still reads | Give each job/attempt its own artifact or clear ref-counting |
| Janitor deletes all old files in system temp | Deletes files of other apps or valid jobs | Use dedicated directory, prefix, TTL, and job state checks |
| Logging sensitive paths/contents | Information leak | Use opaque IDs and minimal status logs |
| Treating delete as secure erase | Data may persist in snapshots/SSDs | Encryption at rest and retention policies |
| Using `ByteArrayResource` for huge files | Heap pressure, GC, and OOM | Use file/resource/stream with appropriate lifecycle |

## 18. Operational cleanup workflow for a mail service

An attachment-capable mail module can standardize on this workflow:

1. **Create artifact:** generate file with random name in a dedicated directory or durable storage.
2. **Record ownership:** attach job/attachment ID and identify the component responsible for deletion.
3. **Build MIME:** pass resource and display name; never delete when the helper merely registers the attachment.
4. **Execute send:** keep the resource readable throughout the entire synchronous send.
5. **Classify outcome:** submitted successfully, retryable error, permanent failure, or unknown state.
6. **Decide retention:** if retries remain possible, keep artifact; if job is terminal, schedule cleanup.
7. **Cleanup:** delete service-owned file/artifact; record deletion errors separately.
8. **Janitor:** remove orphaned files past TTL while checking ownership and job state.
9. **Monitor:** track file counts, disk usage, file ages, cleanup failures, and pending jobs.

### 18.1. Useful metrics

| Metric | Meaning |
| --- | --- |
| `mail_temp_files_created_total` | Total temporary files created |
| `mail_temp_files_deleted_total` | Total files deleted successfully |
| `mail_temp_cleanup_failures_total` | Number of cleanup failures |
| `mail_temp_storage_bytes` | Current bytes used in mail temp directory |
| `mail_temp_oldest_file_age_seconds` | Age of the oldest remaining file |
| `mail_attachment_size_bytes` | Distribution of attachment sizes |
| `mail_jobs_waiting_for_retry` | Number of jobs still needing artifacts for retry |

Metrics should use IDs or labels with bounded cardinality; never turn email addresses, arbitrary filenames, or unique job IDs into Prometheus labels as that creates excessive cardinality.

## 19. End-to-end scenario: synchronous vs. queued invoice sending

### 19.1. Synchronous sending inside one request/job

If the service creates a file, calls `JavaMailSender.send` immediately, and performs no retries after the method exits:

~~~text
Create temp PDF
    -> Build MimeMessage
    -> sender.send(...)
    -> finally delete temp PDF
~~~

This matches the `try/finally` pattern in Section 4. The file exists only for the lifetime of the service call.

### 19.2. Asynchronous sending with retries

If a user places an order and a worker sends the email later:

~~~text
Order transaction
    -> Create immutable mail job
    -> Store attachment artifact durably
    -> Enqueue job with artifact key/version

Worker attempt 1
    -> Read artifact
    -> Build MIME
    -> SMTP temporary failure
    -> Keep artifact; schedule retry

Worker attempt 2
    -> Read same artifact version
    -> SMTP submission succeeds
    -> Mark job SUBMITTED
    -> Cleanup artifact when retention policy permits
~~~

In this model, the first attempt's `finally` block can only close the **attempt's** stream/resource; it must not delete the artifact shared across retries. Artifact deletion belongs to the job lifecycle after reaching a terminal state and once consumers no longer reference it.

If multiple jobs share a single artifact, manage reference counts or copy artifacts per job. Never delete when one consumer finishes if another consumer still needs it.

## 20. Things to remember

- Temporary files must be deleted only by **the component that owns them**.
- For synchronous sending, retain the file until `send(...)` completes; place cleanup in `finally`.
- Clean up on both success and failure branches, including when an error occurs while writing the file.
- Never let a cleanup exception mask a send error; keep send status and cleanup status separate.
- Never delete an artifact while a queue/job can still retry.
- Never pass local paths to workers running on other machines; use durable storage with keys/versions.
- Janitors should only clean application-owned files in a dedicated directory according to TTL and job state.
- `Files.deleteIfExists` is not a secure erasure mechanism.
- Use in-memory bytes for small files; use appropriate files/resources/storage for large attachments.

With Spring Framework Mail, a reliable attachment lifecycle does not stop at `addAttachment(...)`. The application must control everything from file creation, providing the resource to MIME, completing the send operation, handling retries, and finally deleting data per policy. When **ownership, cleanup timing, and job states** are clearly defined, the system avoids orphaned files, reduces data-exposure risk, and prevents accidentally deleting attachments that workers still need.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`, and attachment resources.
- **Spring Framework API — `FileSystemResource` / `ByteArrayResource`:** supplying attachment data.
- **Java API — `Files.createTempFile`, `Files.deleteIfExists`, `Files.copy`:** creating, writing, copying, and deleting files.
- **Java Language/API — try/finally and try-with-resources:** resource management and close exceptions.
- **Jakarta Mail API:** `MimeMessage`, `MimeBodyPart`, `DataHandler`, and MIME serialization.
- **Spring Framework — Task Execution and Scheduling:** asynchronous job handling and scheduled cleanup tasks.

# Logging Full Messages and Recipient Data in Spring Framework Mail

In Spring Framework Mail, a very common operational mistake is **logging the entire email verbatim along with the recipient list** in order to “debug quickly”. A snippet like `log.info("sending mail: {}", message)` or `mimeMessage.writeTo(System.out)` can inadvertently dump names, addresses, subjects, HTML bodies, verification tokens, invoices, attachments, and MIME headers into the logging system. Even more dangerously, logs can be replicated to many places: container consoles, log collection agents, APMs, centralized storage, support tools, dashboards, alerting systems, and exports sent to third parties.

This is not merely an issue of overly verbose logs. **Email is business data and often contains personal data or secrets; logs are a separate storage and distribution environment with access permissions, retention periods, backups, and protection levels that can differ completely from the origin database.** Once data enters logs, retracting it is usually far harder than deleting a record inside the application.

This lesson analyzes the root causes, leak paths, and how to design **structured, minimal, privacy-aware logging** when using `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper`, Jakarta Mail, Spring Boot, Spring Integration, and workers/outboxes. It also provides Java code examples, SMTP error cases, logging during async/retry, trace/MDC, testing approaches, and an incident runbook.

## 1. The anti-pattern to recognize

Email sending example:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("security@example.test");
mail.setTo("customer@example.test");
mail.setSubject("Login code");
mail.setText("Your code is 482917");

log.info("Sending email: {}", mail);

mailSender.send(mail);
```

`SimpleMailMessage` can directly hold email fields. Never assume a message’s `toString()` is a log-safe serialization.

An even more obvious risky example with MIME:

```java
MimeMessage mime = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setTo("customer@example.test");
helper.setSubject("Invoice copy");
helper.setText(
    "Your invoice",
    "<p>Customer billing details</p>"
);

// Avoid: writing the full MIME, including headers and parts.
mime.writeTo(System.out);

mailSender.send(mime);
```

`MimeMessage.writeTo(...)` produces MIME data for mail transport, **not a redacted log entry**. It can emit payloads, encoded attachments, inline resources, and headers to the output stream.

Operations that should not appear in routine logging:

- `log.info("{}", mailMessage)` or stringifying a DTO containing the body.
- `log.debug("mime={}", mimeMessage)` without controlling the `toString` implementation.
- `mimeMessage.writeTo(System.out)` or writing to a log file.
- Logging `getContent()`, `getSubject()`, `getAllRecipients()`, or `getFrom()` verbatim.
- Logging `getFailedMessages()` without bounding keys/values.
- Logging raw request JSON containing HTML, recipient arrays, and attachment URLs.
- Enabling Jakarta Mail session debugging system-wide and forgetting to turn it off.

**Safe default:** log the outcome and internal identifiers needed for investigation; do not log email contents.

## 2. Data classes that can be exposed

| Component | Example | Risk |
| --- | --- | --- |
| To/Cc/Bcc | Recipient addresses | PII, exposing recipient groups, partners |
| From/Reply-To | Identity or internal mailbox | Org chart, contact information |
| Subject | “Test results”, “Order #...” | Can contain sensitive data |
| Plain text | Notification body | PII, secrets, monetary amounts, codes |
| HTML | Template + customer data | Sensitive content and tracking URLs |
| OTP/reset link | Codes, tokens, magic links | Account takeover risk |
| Attachments | PDF, CSV, images | Records, invoices, contracts |
| Inline resources | CID images | Unnecessary data and large size |
| MIME headers | Message-ID, custom headers | Correlation ID, routing, personal metadata |
| SMTP envelope | MAIL FROM/RCPT TO | May expose all recipients including Bcc |
| Exception messages | Rejected address, SMTP reply | PII, server/provider details |
| Trace baggage/MDC | Email, tenant, request ID | Automatically propagates across many logs |
| Provider response | Queue ID, rejection text | Can contain recipient or message metadata |

Never classify “subject is harmless”. An email subject alone can reveal a private business event: a failed transaction, a legal support request, a health status, or HR information.

An email “with no attachment” can still contain credentials, authentication tokens, and contact addresses.

## 3. Why logs carry a different risk profile than databases

Origin data typically has schemas, per-user access control, encryption, and retention tied to business workflows. Logs can travel through:

```text
Spring application
      |
      +--> stdout/container logs
      |
      +--> log shipper / agent
      |
      +--> central log platform
      |
      +--> APM / trace store
      |
      +--> alerts / chat integrations
      |
      +--> support export / incident attachment
      |
      +--> backup / archive
```

Even when log access is controlled, the number of systems and personnel permitted to read logs can be broader than access to the original emails. Payloads sitting in logs also get duplicated into dashboards, screenshots, tickets, or downloads.

**Do not use logs as an email archive.** If the business needs to retain copies of sent emails, build a dedicated storage/audit artifact with proper retention, encryption, and access control; do not dump MIME into logs.

## 4. What is the real goal of logging?

When an email fails, an operator usually wants to know:

1. Which business notification was affected?
2. Was a job created?
3. Is it at the prepare, queue, or SMTP stage?
4. How many send attempts have occurred?
5. Which provider/account handled it?
6. Is the error temporary or permanent?
7. Can it be retried, and when?
8. Did the SMTP relay accept the message?
9. Is there a provider delivery/bounce event?
10. Is it tied to a specific tenant/category?

Most of these questions **do not require the raw email body or full addresses**. They require notification ID, attempt ID, status transitions, failure class, latency, and provider correlation.

Instead of logging “what email was sent to whom”, log “which notification, which attempt, which stage, which outcome”.

## 5. Distinguishing three types of identifiers

| ID | Meaning | Should it be logged? |
| --- | --- | --- |
| `notificationId` | One logical email requested | Usually yes, as an internal opaque ID |
| `attemptId` | One specific SMTP send attempt | Usually yes |
| `businessEventId` | Event that triggered the email | Per policy, avoid sensitive content |
| MIME `Message-ID` | Email header | Per correlation and privacy requirements |
| Provider queue/message ID | Identifier supplied by provider | Controlled, only if provider returns one |
| Trace ID/span ID | Execution tracking | Yes, do not put PII in span names |
| Recipient correlation token | HMAC/pseudonymized address | Only when truly needed, with key governance |

`notificationId` and `attemptId` are two key identifiers for linking retry history without logging recipient addresses.

MIME `Message-ID` does not guarantee exactly-once; nor is a provider ID proof that an email was delivered if no delivery event confirmed it.

## 6. A minimal structured logging contract

Each log event can use a schema:

```json
{
  "event": "mail.smtp.submit.completed",
  "notificationId": "N-1001",
  "attemptId": "A3",
  "mailCategory": "TRANSACTIONAL",
  "provider": "smtp-primary",
  "stage": "SMTP_SUBMISSION",
  "outcome": "SUBMITTED",
  "durationMs": 742,
  "timestamp": "2026-11-12T11:20:00Z"
}
```

Excludes:

- Raw recipient address.
- Full subject.
- HTML/plain body.
- Attachment bytes or filesystem paths.
- OTP/magic links.
- SMTP password.
- Access/refresh tokens.

An error event:

```json
{
  "event": "mail.smtp.submit.failed",
  "notificationId": "N-1001",
  "attemptId": "A4",
  "mailCategory": "TRANSACTIONAL",
  "provider": "smtp-primary",
  "failureClass": "SMTP_TEMPORARY",
  "smtpReplyCode": "451",
  "outcome": "RETRY_WAIT",
  "nextAttemptAt": "2026-11-12T11:25:00Z"
}
```

`failureClass` and reply code are normalized; do not directly log the entire remote SMTP server message because it can contain recipients or arbitrary text.

## 7. Build a whitelist instead of a blacklist

Two approaches:

**Blacklist:**

```text
Serialize every field of MailJob
    |
    +--> exclude password, token, recipient?
    |
    v
Log the rest
```

This easily breaks when the DTO gains a new field such as `resetUrl`, `secretAttachmentKey`, or `bccAddresses` that the blacklist does not know about yet.

**Whitelist:**

```text
Choose event name
   |
   +--> notificationId
   +--> attemptId
   +--> category (low cardinality)
   +--> provider alias
   +--> status/outcome
   +--> duration/error class
   |
   v
Structured logger
```

Only approved fields enter the log, regardless of how the DTO evolves.

**Do not use reflection to log an entire object** and hope a masking layer catches everything sensitive.

## 8. Java code: safe logging around JavaMailSender

An illustrative service using Spring Mail:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import java.time.Duration;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

@Service
public class SafeMailSubmissionService {

    private static final Logger log =
        LoggerFactory.getLogger(SafeMailSubmissionService.class);

    private final JavaMailSender sender;
    private final Clock clock;
    private final MailFailureClassifier failures;

    public SafeMailSubmissionService(
            JavaMailSender sender,
            Clock clock,
            MailFailureClassifier failures) {
        this.sender = sender;
        this.clock = clock;
        this.failures = failures;
    }

    public void submit(PreparedMail prepared, UUID attemptId) {
        Instant started = clock.instant();

        try {
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

            sender.send(message);

            log.info(
                "event=mail.smtp.submitted notificationId={} attemptId={} "
                    + "category={} durationMs={}",
                prepared.notificationId(),
                attemptId,
                prepared.category(),
                Duration.between(
                    started, clock.instant()
                ).toMillis()
            );
        } catch (MessagingException | MailException exception) {
            MailFailureCategory failure =
                failures.classify(exception);

            log.warn(
                "event=mail.smtp.failed notificationId={} attemptId={} "
                    + "category={} failureClass={}",
                prepared.notificationId(),
                attemptId,
                prepared.category(),
                failure.name()
            );

            throw new MailSubmissionFailure(
                prepared.notificationId(),
                attemptId,
                failure,
                exception
            );
        }
    }
}
```

`PreparedMail`, `MailFailureClassifier`, `MailFailureCategory`, and `MailSubmissionFailure` are application-defined types. The example only illustrates choosing log fields. The repository/outbox must persist status and retry policy separately.

**Key point:** `exception` is used to classify, but **never pass `exception` as the final argument to `log.warn(...)`** or call `exception.getMessage()` to log raw SMTP text. Such data must follow a separate logging policy.

In production, if stack traces are needed for debugging, build a restricted-access diagnostics mechanism after assessing sensitive-data risk in the exception/cause chain; never assume every stack trace is safe.

## 9. Why can exception stack traces also expose PII?

Mail-related exceptions can contain:

- Recipient addresses rejected by SMTP.
- `InternetAddress` rendered in the message.
- Subjects or context inside application-created exceptions.
- SMTP server responses containing recipient addresses.
- Nested provider-specific exceptions.
- Maps of failed messages keyed by mail objects.

Example to avoid:

```java
try {
    sender.send(message);
} catch (MailException exception) {
    log.error(
        "SMTP failed for recipient={} message={}",
        recipient,
        message,
        exception
    );
}
```

It can log the recipient, the message, and the entire nested exception.

Better example:

```java
try {
    sender.send(message);
} catch (MailException exception) {
    MailFailureCategory category =
        classifier.classify(exception);

    log.warn(
        "event=mail.smtp.failed notificationId={} "
            + "attemptId={} category={}",
        notificationId,
        attemptId,
        category.name()
    );

    throw exception;
}
```

Error handling should live in the worker/outbox to update `RETRY_WAIT`, `FAILED`, or `AMBIGUOUS`. Do not swallow exceptions and let an API falsely report success.

## 10. JavaMailSender and MimeMessage are data, not log objects

`JavaMailSender` sends a `MimeMessage`; `MimeMessageHelper` helps set recipients, subject, HTML, and attachments. These objects can reference:

- Body content.
- MIME headers.
- Attachment resources.
- File paths.
- InputStreamSource/JavaMail DataSource.
- Template and sender details.

Even if `toString()` in one version only prints the class name, **do not rely on accidental `toString()` behavior** as a safeguard. A wrapper, record, custom serializer, logging encoder, or future developer can change how much data gets printed.

Avoid `log.debug("prepared={}", preparedMail)` when `PreparedMail` is a Java record containing raw body and recipient: `record.toString()` typically includes all field values.

Log only opaque IDs and allowlisted classifications.

## 11. Do not use writeTo for logging

`MimeMessage.writeTo(OutputStream)` serializes MIME for sending or archiving, including:

```text
From: ...
To: ...
Subject: ...
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=...

--boundary
Content-Type: text/html; charset=UTF-8

... raw HTML body ...

--boundary
Content-Type: application/pdf
Content-Transfer-Encoding: base64

... base64 attachment bytes ...
```

Base64 **is not security encryption**. Anyone with log access can decode the attachment.

A snippet such as:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
mimeMessage.writeTo(out);
log.debug("mail.raw={}", out.toString(StandardCharsets.UTF_8));
```

both pushes sensitive data into logs and can allocate a huge MIME copy on the heap. Never use it for logging; if MIME testing is needed, use an SMTP capture server in tests rather than writing full payloads into CI logs.

## 12. Spring Boot/Jakarta Mail debug: a different risk from application logs

Beyond the application’s `log.info`, there is protocol debugging from Jakarta Mail/Angus Mail or mail providers. Dangerous options in production:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
```

Or:

```java
Session session = ...;
session.setDebug(true);
```

These examples enable Jakarta Mail Session debugging when applied to the corresponding session/transport. The provider/version determines exact output details, which may include SMTP transcripts, server replies, envelope recipients, headers, and/or MIME payloads. Do not treat debug output as safely redacted.

In some clients/providers, debug AUTH output may be masked by default; that is **no guarantee** that all email addresses, bodies, or secrets are masked across every version.

Never enable global session debug in production just to investigate a single notification.

## 13. Distinguishing log level DEBUG from Session debug

Different mechanisms:

| Mechanism | Used for | Risk |
| --- | --- | --- |
| SLF4J `log.debug(...)` | Application log statements | Leaks data if fields are not allowlisted |
| Logback/Log4j2 logger levels | Toggle per package | Libraries may print protocol/headers |
| Jakarta Mail `Session.setDebug(true)` | Mail session protocol/debug output | Can expose transcripts/payloads |
| `mail.debug=true` | JavaMail debug property | Can emit data outside structured logs |
| HTTP request/response logging | Web filters/interceptors | Exposes bodies containing recipients/template fields |
| APM request capture | Observability agent | Copies payloads/headers into traces |
| Global exception logging | ControllerAdvice/filter/worker | Throwable message/cause may contain PII |
| Raw MIME archival | Persisting via `writeTo` | Requires separate storage/access/retention; not logs |

Turning off `logging.level.*=DEBUG` does not necessarily disable `Session.setDebug(true)` if session debug writes to a different output stream.

When an incident occurs, check **every log source**, not only the `MailService` logger.

## 14. Default configuration: keep mail protocol debug off

A typical production configuration:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
      "[mail.debug]": false

logging:
  level:
    root: INFO
    com.example.mail: INFO
```

This is an illustrative configuration example. `com.example.mail` must be replaced with your project’s package. Keep timeouts to prevent jobs from hanging indefinitely; do not use debug mode to mask timeout errors.

`mail.debug=false` does not by itself protect against data logging by application code, APM, or framework filters. Log statements must still follow an allowlist.

## 15. A data classification table before logging

| Field | Default logging | Handling guidance |
| --- | --- | --- |
| Event name | Allowed | Fixed enum/string |
| Notification ID | Usually allowed | Opaque identifier, scoped access |
| Attempt ID | Allowed | Opaque, low-sensitivity |
| Mail category | Allowed | Low-cardinality enum |
| Template key/version | Conditional | Only when it does not reveal sensitive record types |
| Provider alias | Allowed | Infrastructure name without secrets |
| Status/outcome | Allowed | Enum |
| Duration/size bucket | Allowed | Contains no content |
| SMTP reply code | Conditional | Only parsed/validated code |
| Recipient count | Conditional | Not the addresses |
| Recipient address | **Not by default** | Only in secure records if truly required |
| Recipient display name | No | PII |
| Subject | No | May be sensitive |
| Plain/HTML body | No | Content/secret |
| OTP/reset URL | **No** | Secret |
| Attachment filename/path | Not by default | May contain PII and internal paths |
| Attachment content | **No** | Sensitive file |
| Raw MIME headers | No | Contains recipient/correlation/PII |
| Raw SMTP response | Not by default | Parse class/code safely |
| SMTP password/OAuth token | **Never** | Secret |
| Throwable `getMessage()` | Not by default | May contain recipient |

Whether something is “loggable” is a scoped decision: a debug environment using synthetic data differs from production logs containing user data.

## 16. Pseudonymization: distinct from masking and anonymization

An investigation need might be: “Did all attempts to the same recipient fail?” There are three options:

1. Look up by `notificationId` and join inside an access-controlled database.
2. Record an **opaque recipient ID** already present in the application model.
3. If correlation without an ID is genuinely required, use a **secret-keyed HMAC** over the normalized address per policy.

Avoid:

```text
recipientHash = SHA256(emailAddress)
```

Email addresses typically have a guessable search space. An unsalted/unkeyed hash can be dictionary-attacked more easily than expected. HMAC with a protected key reduces this risk, yet **does not make the data truly anonymous**.

### Masking is also insufficient

For example:

```text
n***@example.test
```

can still reveal the domain, length, and pattern; for uncommon mailboxes, the user remains identifiable. Masking can be useful in privileged UIs, but should not be assumed safe for broad-access logs.

## 17. HMAC recipient token at the design level

An interface can be defined:

```java
public interface RecipientCorrelation {

    String tokenFor(String normalizedEmail);
}
```

A secure implementation requires:

- Canonicalization matching domain/provider/application rules.
- Secret key loaded from a secret manager; never hardcoded.
- HMAC-SHA-256 or another suitable algorithm.
- Key rotation/versioning.
- Scoping carefully by tenant/environment.
- Never logging raw input on error paths.
- Short retention and narrow access permissions.
- Never using the token as authentication or authorization proof.

Example event when genuinely needed:

```json
{
  "event": "mail.provider.bounced",
  "notificationId": "N-1001",
  "recipientCorrelation": "v2:78e...opaque",
  "failureClass": "HARD_BOUNCE"
}
```

The token string above is only a placeholder. For many systems, **there is no need to log recipient tokens**: the notification ID and an access-controlled store are sufficient for investigations.

## 18. MDC should only hold safe metadata

MDC helps attach correlation context to logs:

```java
import org.slf4j.MDC;

public void processJob(MailJob job) {
    try (
        MDC.MDCCloseable id = MDC.putCloseable(
            "notificationId",
            job.notificationId().toString()
        )
    ) {
        process(job);
    }
}
```

MDC can be automatically appended by the log encoder to **every log line** on the thread. Therefore never put in MDC:

- `recipientEmail`.
- `subject`.
- `otp`.
- Raw `tenantName` or user-supplied data.
- Authentication bearer tokens.
- Full request payloads.

If tenant correlation is needed, use an opaque ID classified compatibly with log access permissions and avoid turning tenant ID into a high-cardinality metric label.

### Thread pools and cleanup

Spring `@Async`/`ThreadPoolTaskExecutor` reuses threads. If you manually call `MDC.put` without `remove`/`clear`, context from email A can bleed into logs for email B. Use try/finally or `MDCCloseable` to clear keys after each job.

## 19. Tracing is not a store for recipients or bodies

Micrometer Observation/tracing can produce spans such as:

```text
mail.outbox.claim
      |
      v
mail.template.render
      |
      v
mail.mime.prepare
      |
      v
mail.smtp.submit
```

Allowed attributes might include:

```text
mail.category = TRANSACTIONAL
mail.provider = primary
mail.outcome = SUBMITTED
mail.failure_class = NONE
```

Avoid:

```text
span.name = "Send OTP to alice@example.test"
mail.recipient = alice@example.test
mail.subject = Password reset for ...
mail.body = ...
```

Span attributes, baggage, and links can be exported to an APM SaaS separate from the log system. Sampling does not make it safe if 1% of traces still contain OTPs or raw recipients.

Never use raw customer addresses as span names, metric tags, or trace baggage.

## 20. Structured logging: avoid CRLF/log injection

Data from emails or SMTP servers can contain control characters. If concatenated directly into log strings:

```java
log.warn(
    "SMTP failure: " + smtpServerResponse
);
```

untrusted content can forge fake log lines or break parsers, depending on the encoder.

Mitigations:

- Do not log raw remote text when only a status code/failure class is needed.
- Use a structured JSON encoder with proper escaping.
- Allowlist and bound field lengths.
- Normalize enums/status codes from a trusted classifier.
- Never allow arbitrary headers/subjects to become the `event` or `message` name.
- Do not trust client-supplied `X-Request-ID` without validating format/length.

**SLF4J parameterized logging is good practice for formatting**, but it does not automatically redact PII. Sensitive field removal must happen before calling the logger.

## 21. Exception classifier instead of raw SMTP text

A classifier can return an enum:

```java
public enum MailFailureCategory {
    SMTP_TEMPORARY,
    SMTP_PERMANENT,
    SMTP_AUTHENTICATION,
    SMTP_TLS,
    SMTP_CONNECT_TIMEOUT,
    SMTP_READ_TIMEOUT,
    SMTP_WRITE_TIMEOUT,
    MIME_PREPARATION,
    STORAGE,
    UNKNOWN,
    AMBIGUOUS
}
```

Interface:

```java
public interface MailFailureClassifier {
    MailFailureCategory classify(Throwable throwable);
}
```

The classifier inspects exception types, nested causes, and reliable protocol signals, while **logging the result enum**, not dumping the full cause chain into broad-access logs.

SMTP status codes such as `421`, `451`, `550` can be helpful when parsed accurately. Never assume all SMTP 5xx codes represent the same recipient reason or that every timeout proves the email was not submitted.

If a timeout may have occurred after DATA, the outcome may be `AMBIGUOUS`, requiring reconciliation before retrying because resending risks duplicates.

## 22. MailSendException can hold failed messages

In Spring Mail, certain send errors can hold a map of failed messages to their corresponding exceptions. Example handling `MailSendException#getFailedMessages()`.

Do not do:

```java
catch (MailSendException exception) {
    log.error(
        "All failed messages: {}",
        exception.getFailedMessages()
    );
}
```

The map may hold mail objects as keys and exception messages as values; stringifying the whole map is not a redacted log summary.

If you need error counts:

```java
catch (MailSendException exception) {
    int failedCount =
        exception.getFailedMessages().size();

    log.warn(
        "event=mail.smtp.batch_failed batchId={} "
            + "failedCount={}",
        batchId,
        failedCount
    );

    throw exception;
}
```

This example logs only the count and an opaque batch ID. Do not place map keys/values directly into events. If per-message retries are required, design notification/attempt IDs in the application from the start rather than stringifying mail objects.

## 23. Batch failures and partial success

Sending a batch of multiple messages can yield mixed outcomes:

```text
Batch:
  N-1 -> accepted
  N-2 -> temporary failure
  N-3 -> unknown / not attempted
```

Logging:

```text
batch failed: full message list = ...
```

both exposes recipients and fails to describe each individual outcome accurately. It is better to persist per-notification attempt state in the database and log:

```json
{
  "event": "mail.batch.completed",
  "batchId": "B-4002",
  "attemptedCount": 3,
  "submittedCount": 1,
  "temporaryFailureCount": 1,
  "unknownCount": 1
}
```

A batch-level exception does not by itself prove that all messages remain unsent. Information needed for retries should come from the outbox and provider evidence.

## 24. Do not log all recipients of a MIME message

An email with multiple recipients:

```text
To: customer@example.test
Cc: finance@example.test
Bcc: audit@example.test
```

Logging `message.getAllRecipients()`:

- Can expose Bcc recipients as well.
- Builds sensitive contact lists inside log systems.
- Adds little operational value when notification ID and routing metadata already exist.
- Easily leaks into dashboards or alert channels.

Instead of addresses:

```java
log.info(
    "event=mail.message.prepared notificationId={} "
        + "recipientCount={} attachmentCount={}",
    notificationId,
    totalRecipientCount,
    attachmentCount
);
```

Even `recipientCount` and `attachmentCount` need business justification; for very small or specialized recipient groups, counts can still reveal metadata. Log them only if operationally useful.

## 25. Attachment metadata can contain sensitive data

Example filenames:

```text
invoice-customer-name-2026.pdf
medical-report-user-id.pdf
disciplinary-case-employee-name.pdf
```

Do not log filenames or raw storage keys, because they can contain PII or business identifiers. With object storage, signed URLs can also act as time-limited file access capabilities.

Instead log:

```text
attachmentCount = 2
totalAttachmentBytesBucket = "1MiB-5MiB"
artifactLoadDurationMs = 184
failureClass = STORAGE_TIMEOUT
```

If investigating a specific artifact is necessary, use a controlled opaque `artifactId` and look up metadata in separately authorized storage.

**Do not log Base64 attachment bytes:** Base64 only encodes representation, not confidentiality.

## 26. HTML emails can contain more data than visible text

HTML emails often include:

- Customer names.
- Order IDs, line items, and monetary amounts.
- Links containing authentication tokens.
- Tracking pixels/URLs with recipient identifiers.
- CSS/inline image URLs.
- QR codes or barcodes.
- Hidden metadata, CID references.

Writing `html` to DEBUG logs can expose values that do not even appear when an operator looks at a visual preview.

Template variables must not be assumed safe merely because HTML is built server-side. To verify template rendering, use synthetic data in tests; production should only record a classified template key/version and rendering outcome.

## 27. HTTP request logging can expose emails before sending

An endpoint:

```http
POST /api/notifications/email
Content-Type: application/json

{
  "to": ["customer@example.test"],
  "subject": "Transaction result",
  "html": "<p>Sensitive information</p>"
}
```

Even if the mail service logs nothing, a request logging filter can record the entire body.

Check:

- `CommonsRequestLoggingFilter` or custom request logging.
- HTTP wiretap/client logging.
- Spring MVC interceptors/AOP request/response logging.
- API gateway access logs with body capture.
- Reverse proxy and service mesh debug settings.
- Error handlers printing raw request payloads.
- APM instrumentation capturing request bodies.

**Do not enable body logging for production email-sending endpoints**. If request correlation is needed, log request ID, authenticated actor ID, operation ID, and outcome—not raw JSON.

## 28. Spring Integration Message headers can also carry PII

In Spring Integration Mail:

```java
Message<String> outbound =
    MessageBuilder.withPayload(htmlBody)
        .setHeader(MailHeaders.TO, recipients)
        .setHeader(MailHeaders.SUBJECT, subject)
        .build();
```

A handler/debugger logging `Message<?>` intact can expose:

- HTML/text payload.
- `mail_to`, `mail_cc`, `mail_bcc`.
- `mail_from` and `mail_replyTo`.
- Subject.
- Application headers carrying customer metadata.

Do not log full Spring Integration `MessageHeaders`, and do not route raw messages to a DLQ with full-payload logging enabled at every step. You can log `messageId` or business `notificationId` and event classification.

If a DLQ is needed for reprocessing, store payloads durably in access-controlled storage; inspect the DLQ via IDs, not raw emails in logs.

## 29. Log accurately per pipeline stage

A pipeline:

```text
Business transaction
      |
      v
Outbox intent
      |
      v
Preparation/render
      |
      v
MimeMessage build
      |
      v
SMTP submission
      |
      v
Provider events
```

You can log:

| Stage | Sample event | Appropriate fields |
| --- | --- | --- |
| Outbox created | `mail.outbox.created` | notificationId, category |
| Worker claim | `mail.outbox.claimed` | notificationId, attemptId, workerId |
| Rendering | `mail.render.completed` | templateVersion, durationMs |
| MIME prepared | `mail.mime.prepared` | recipientCount, size bucket |
| SMTP submit | `mail.smtp.submitted` | provider, attemptId, durationMs |
| Temporary error | `mail.smtp.retry_scheduled` | failureClass, nextAttemptAt |
| Permanent error | `mail.smtp.failed` | failureClass |
| Ambiguous outcome | `mail.smtp.ambiguous` | attemptId, stage |
| Provider delivered | `mail.provider.delivered` | providerEventId/opaque notificationId |
| Provider bounced | `mail.provider.bounced` | normalized bounce class |
| Suppressed | `mail.notification.suppressed` | category, policy reason code |

Subject/body/recipient are unnecessary for nearly all events above.

## 30. Trace IDs can change across the outbox

An HTTP request and an outbox worker may run minutes apart or in separate processes. Keeping a single HTTP trace span open until mail delivery is not required.

Use:

```text
businessEventId
notificationId
attemptId
providerMessageId (if available)
```

for durable correlation. Trace/span IDs help inspect individual executions, but do not replace the notification/attempt ledger.

Never put `emailAddress` into trace baggage to cross async boundaries. Baggage can be forwarded over network headers and stored in observability systems.

## 31. Design a LogEvent DTO with only allowed fields

A sample record:

```java
public record MailSendLogEvent(
    String event,
    UUID notificationId,
    UUID attemptId,
    String category,
    String provider,
    String outcome,
    String failureClass,
    long durationMs
) {}
```

Excludes:

```java
// Not fields of MailSendLogEvent:
String recipientEmail;
String subject;
String plainText;
String htmlText;
byte[] attachment;
String smtpPassword;
```

Using a field-restricted event class gives teams a shared contract, reducing the chance that someone building a new feature arbitrarily logs `PreparedMail`.

Even though `MailSendLogEvent` has a leaner `toString()`, you still need mapping policies and access controls on allowed fields. For `category`, `provider`, and `outcome`, prefer enums or allowlisted values.

## 32. Structured logging APIs are not automatically safe

SLF4J parameterized logging:

```java
log.info(
    "event=mail.submitted notificationId={} attemptId={}",
    notificationId,
    attemptId
);
```

is a good pattern. Yet this pattern still leaks data:

```java
log.info(
    "mail to={} subject={}",
    recipientAddress,
    subject
);
```

Using a JSON encoder also only makes data machine-readable/escaped; it **does not automatically classify or redact PII**.

Protection must rely on:

- Field allowlists.
- Code reviews and logging tests.
- Static patterns/lint rules where appropriate.
- Centralized policy and access control.
- Retention and incident response.

## 33. When might logging recipients be permitted?

Some use cases such as abuse investigation or legal/compliance audits require recipient-identifying details. However, that should be **controlled retrieval**, not broad INFO logs:

1. Clear business purpose and access authorization.
2. Retrieved from an ACL-protected database/secure audit record.
3. Recorded actor, reason, and timestamp of access.
4. Scoped return data.
5. Never copied into unprotected channels.
6. Appropriate retention and encryption.
7. Procedures for deletion/redaction upon valid request.

If an incident requires inspecting full MIME, store the capture only in a secure diagnostic artifact store under an approved process, with TTL and audited access. Never enable raw logging across all producers.

## 34. Safe debugging with synthetic data

Instead of using real user emails:

```text
To: test-recipient@example.test
Subject: SMTP fixture
Body: Synthetic test content
Attachment: fake-document.pdf
```

Combine:

- GreenMail/Mailpit or an SMTP capture server.
- Template fixtures without PII.
- Synthetic recipient addresses in reserved test domains.
- Unit tests for HTML/MIME parts.
- Integration tests asserting attachment bytes and headers.
- Mocked provider failures when needed.

In test environments, raw MIME can serve as a test artifact if it contains no real data and has appropriate access control; **avoid letting test artifacts automatically upload to public log systems**.

This is the right way to verify exact MIME structure without turning on production debugging.

## 35. A common incident: email missing an attachment

An operator wants to inspect the full MIME because a customer reported a missing PDF. Before logging raw MIME, check:

1. Does the prepared artifact ID exist?
2. Are content size and checksum metadata correct?
3. What is the attachment count in the prepared manifest?
4. Was `MimeMessageHelper.addAttachment(...)` invoked?
5. Can the resource open a fresh stream each time?
6. Was there a read timeout or storage error during send?
7. Does an SMTP capture test with a fixture reproduce it?
8. Does the provider enforce a size limit or attachment policy?
9. Is the MIME tree in the right multipart mode?
10. Is a provider event or recipient client stripping the attachment?

Safe log entry:

```json
{
  "event": "mail.mime.prepared",
  "notificationId": "N-1001",
  "attachmentCount": 1,
  "attachmentBytesBucket": "1MiB-5MiB",
  "mimeBuildDurationMs": 83
}
```

No need to log raw PDF bytes or a filename containing the customer’s name.

## 36. Another incident: SMTP reports unknown recipient

An SMTP server may return text containing an email address. Conceptual example:

```text
550 5.1.1 <customer@example.test> unknown user
```

Do not print the raw reply text to general logs:

```java
log.warn("SMTP response={}", serverReply);
```

Instead parse/normalize:

```text
smtpReplyCode = 550
enhancedStatus = 5.1.1
failureClass = PERMANENT_RECIPIENT
notificationId = N-1001
```

The enhanced status code may be absent or provider-specific. If the parser cannot trust the data, record `UNKNOWN` instead of trying to log raw text. Recipient details can be looked up from the notification store under proper permissions during investigation.

## 37. Retry loops can multiply PII in logs

If every attempt logs the full message, a job retried 10 times can emit 10 copies containing the same subject/body/attachment references.

```text
Attempt A1 -> full MIME logged
Attempt A2 -> full MIME logged
Attempt A3 -> full MIME logged
...
Attempt A10 -> full MIME logged
```

A transient provider failure can cause log volume to surge when thousands of jobs retry together. This is simultaneously a personal-data risk, a storage cost problem, and an operational incident.

Replace it with logging one compact event per attempt:

```json
{
  "event": "mail.retry.scheduled",
  "notificationId": "N-1001",
  "attemptId": "A3",
  "failureClass": "SMTP_TEMPORARY",
  "nextAttemptAt": "2026-11-12T11:30:00Z",
  "retryCount": 3
}
```

Do not use long `Thread.sleep` calls inside sender workers just to wait for retries; store `nextAttemptAt` in the outbox.

## 38. Sampling is traffic control, not anonymization

Some systems log only 1% of mail messages to reduce size. Yet if that 1% still holds raw OTPs or contracts, serious risk remains.

Sampling does not replace:

- Data minimization.
- Encryption/access control.
- Field allowlists.
- Retention.
- Authorized diagnostic workflows.

Apply sampling after log events have already been designed safely, primarily to reduce noise and telemetry costs. For audits or critical state transitions, sampling can also drop evidence that must be kept; distinguish audit stores from operational logs.

## 39. Metrics must not contain recipients or subjects

Micrometer metrics can do:

```text
mail.smtp.submission.total{
  category="transactional",
  provider="primary",
  outcome="submitted"
}
```

Avoid:

```text
mail.smtp.submission.total{
  recipient="customer@example.test",
  subject="Payment for order ..."
}
```

Because:

- PII enters the monitoring backend.
- Cardinality becomes very high.
- TSDB cost and performance degrade.
- More sensitive than short-TTL logs.
- Metadata can persist across many dashboards/exports.

To inspect a specific notification, search logs by opaque ID or run an authorized database query; metrics are only for aggregation.

## 40. Log retention and access permissions

A pragmatic logging policy should specify:

- Who may read production mail service logs?
- Is there separation between developers, support, and security personnel?
- Are logs encrypted in transit and at rest?
- How long is retention, and which tiers/archives exist?
- Does the log agent ship data to any SaaS or region?
- Are broad export/download/search permissions restricted?
- Who manages retention and deletion?
- Are there backup/snapshot copies?
- How do logs get attached to incident tickets or chat messages?
- Are field schemas/sensitive leakage audited periodically?

The goal is **minimizing how long and how broadly metadata exists**, not keeping everything “just in case”. Legal rules and data classification must follow your organization’s actual policy and context rather than assuming a single universal retention period.

## 41. Avoid duplicating data across audit and logs

A well-structured system has two layers:

**Operational logs**

```text
event, notificationId, attemptId, stage, outcome,
duration, failure class, provider
```

**Secure business/audit store**

```text
notification ID, recipient reference,
template/content version, reason, actor,
consent/eligibility decision, status transition
```

Only the audit store should contain identifying data when necessary, protected by access controls. Operational logs use opaque IDs for authorized correlation queries.

Never push full JSON audit records containing recipients into INFO logs, as doing so bypasses the authorization layer.

## 42. Do not let logging errors break email sending

Another anti-pattern is serializing MIME for logging **before sending**:

```java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
mime.writeTo(bytes);
logger.info("{}", bytes.toString());
sender.send(mime);
```

For large files, logging can:

- Increase memory usage and GC pressure.
- Read an InputStreamSource prematurely.
- Lengthen send latency.
- Cause failures because attachment streams are non-repeatable.
- Create unnecessary I/O work.
- Expose content.

Logging should be cheap, minimal, and non-intrusive to the MIME lifecycle. If a logging/telemetry sink loses connectivity, the email worker needs an explicit policy on whether to continue; mandatory audits may require a durable local transaction rather than being silently skipped.

## 43. Use session debugging only under controlled procedures

When protocol-level diagnostics are genuinely required:

1. Identify the exact failure to investigate.
2. Prefer connection/read/write timeouts, exception classifiers, and provider logs first.
3. Reproduce against a test server with a synthetic message.
4. If production debugging is still necessary, obtain approval per policy.
5. Enable only in the narrowest possible scope, with TTL/owner/ticket.
6. Ensure no raw bodies, tokens, or credentials are exposed beyond required controls.
7. Isolate output from broad log platforms and restrict access.
8. Turn off after diagnosis and verify configuration rollback.
9. Check any copies/exports that may have been produced.
10. Audit who enabled it, when, and why.

**Never enable `Session.setDebug(true)` with a feature flag lacking a time limit and approval.** Especially avoid turning it on across all instances during an SMTP outage.

## 44. When full mail was accidentally logged: treat it as a data incident

Priority runbook:

1. **Stop the leak**: disable the offending code path/session debug/HTTP body logging.
2. **Determine scope**: timeframe, service/instances, log platforms, dashboards, alerts, and exports.
3. **Classify exposed data**: addresses, bodies, OTP/tokens, documents, secrets, attachment bytes.
4. **Restrict access**: temporarily tighten log readers and incident attachment sharing.
5. **Preserve required evidence** under security/incident procedures before altering storage.
6. **Clean up copies**: log shippers, archives, search indices, backups, tickets, chat integrations.
7. **Revoke/rotate secrets** if credentials or active authentication tokens were exposed.
8. **Assess notification/compliance duties** under applicable policies and regulations.
9. **Verify remediation**: log only allowlisted events and test that no sensitive data remains.
10. **Postmortem**: root cause, exposure window, blast radius, guardrails.

Do not merely delete one local log file and conclude the data is gone: logs may have already been collected and replicated to other systems. Deletion must also follow evidence-handling and retention procedures.

## 45. Testing: guarantee no sensitive data enters logs

A useful test constructs a **completely synthetic** notification containing distinctive markers:

```text
recipient = secret-recipient@example.test
subject   = UNIQUE-SUBJECT-XYZ
body      = SECRET-TOKEN-ABC123
attachment filename = PRIVATE-DOC-987.pdf
```

Run the send path or SMTP failure path and capture logs from the service under test. Assert that the logs **do not contain** those markers, while still containing the notification ID and outcome.

Example with Logback `ListAppender` (implementation-dependent):

```java
@Test
void doesNotLogRecipientOrMessageBody() {
    String recipient = "secret-recipient@example.test";
    String token = "SECRET-TOKEN-ABC123";

    // Configure ListAppender against the logger under test.
    // Invoke safe mail submission with a mocked sender.
    // Collect formatted messages in a test-only buffer.

    String capturedLog = collectFormattedLogs();

    assertFalse(capturedLog.contains(recipient));
    assertFalse(capturedLog.contains(token));
    assertTrue(capturedLog.contains("mail.smtp."));
}
```

`collectFormattedLogs()` is a test-suite helper; the snippet illustrates assertions, not a built-in JUnit utility.

Test both **success and failure paths**, especially nested exceptions, `MailSendException`, HTTP request logging, async MDC cleanup, and provider response parsing.

## 46. Test SMTP messages without polluting operational logs

Use GreenMail/Mailpit or a test SMTP server:

```text
JUnit test
    |
    v
Prepare synthetic MimeMessage
    |
    v
JavaMailSender
    |
    v
GreenMail SMTP capture
    |
    v
Assert subject/body/attachment in test
```

Tests can verify:

- `MimeMessage` has the right To/Subject.
- HTML/plain alternatives are valid.
- Attachment filename/bytes match the fixture.
- No Bcc leakage.
- Correct SMTP attempt state.
- No full message logged at runtime.
- Provider-like failures are classified safely.

The test server stores messages in the test environment, **which differs from logging raw MIME in production**. Never use real mailboxes/recipients or copies of user attachments in CI.

## 47. Special-case test scenarios

A test suite should cover:

1. Subject containing a customer name never appears in logs.
2. Body containing a reset token never appears in logs.
3. `MailSendException` with nested recipient errors only logs the failure class.
4. Bcc array does not leak into logs.
5. Filenames containing full names are not recorded.
6. SMTP server responses with newlines are normalized/truncated.
7. HTTP filters do not log raw notification JSON.
8. Spring Integration messages are not logged via `toString`.
9. MDC from email A does not bleed into email B on the same thread.
10. APM span attributes contain no recipient/subject/token.
11. Worker retrying 5 times does not duplicate MIME in logs.
12. Provider webhooks do not log entire sensitive raw payloads.
13. Unit and integration tests use fake test domains and fake secrets.
14. Logging pipeline failures do not make the worker silently succeed.
15. When session debug is unintentionally enabled, detection/guardrails alert.

Use synthetic fixtures in tests to avoid creating leaks inside the CI pipeline itself.

## 48. Static checks and code reviews

Code reviews can look for risky patterns:

```text
log.info("{}", mail)
log.debug("{}", preparedMail)
log.error("SMTP error", exception)
mimeMessage.writeTo(System.out)
session.setDebug(true)
mail.debug=true
log.info("to={} subject={}", ...)
requestLoggingFilter.includePayload=true
```

Not every occurrence is automatically wrong in every context, but each should be reviewed against the threat model and log access.

An effective development rule:

> Before adding a field to a log, explain which operational question requires that field and why an opaque identifier is not enough.

You can add lint/static pattern checks, logging schema reviews, or automated tests; however, reviews must understand context rather than merely searching and replacing source code.

## 49. Common anti-patterns

| Anti-pattern | Consequence | Replacement |
| --- | --- | --- |
| Logging full `SimpleMailMessage` object | Can expose recipient/body | Log notification ID/outcome |
| Dumping `MimeMessage.writeTo` to console | Exposes MIME/attachments | SMTP capture tests with fixtures |
| Enabling `mail.debug=true` in production | Transcripts may leak | Scoped diagnostics |
| Logging `MailSendException#getFailedMessages()` | May expose failed message keys | Count/classification |
| Logging raw exception messages/causes | Remote replies contain PII | Normalized error class/code |
| Logging To/Cc/Bcc recipients | Exposes contact lists/Bcc | Opaque notification ID |
| Logging subject as “just metadata” | Subject still carries PII | Controlled template category/version |
| Logging HTML/attachments on render failure | Exposes tokens/file contents | Render error class + artifact ID |
| Logging raw request JSON | Leaks before SMTP | Request ID/status |
| Logging Spring Integration Message headers | Exposes mail_to, mail_bcc, payload | Allowlisted event fields |
| Hashing emails with plain SHA-256 | Vulnerable to dictionary attacks | Opaque ID or keyed HMAC if needed |
| Treating address masking as anonymization | Still guessable | Data minimization |
| Putting emails into MDC/baggage | Propagates across all telemetry | Opaque correlation IDs |
| Putting recipient/subject into metric labels | PII, high cardinality | Enum tags |
| Sampling raw MIME at 1% | Still leaks real data | Redaction before sampling |
| Only disabling package DEBUG | Session debug may stay on | Check every mechanism |
| Deleting local logs after an incident | Copies still exist | Incident containment across full pipeline |
| Retaining logs forever “to investigate” | Increases blast radius | Retention and ACLs |
| Logging real data in unit tests | Leaks into CI artifacts | Synthetic fixtures |

## 50. Roadmap for implementing safe logging

1. **Inventory mail data**: body, subject, recipients, headers, files, tokens.
2. **Define operational events** genuinely needed across logs/metrics/traces.
3. **Design an allowlist field schema** per event/stage.
4. **Use notificationId and attemptId** as primary correlation keys.
5. **Separate errors by failure class**, without printing raw exception text.
6. **Disable protocol/session debug by default** in production.
7. **Audit HTTP logging and APM instrumentation** to prevent request body capture.
8. **Never log whole Spring Integration Messages or MailMessage objects**.
9. **Never log MIME or attachment bytes**, including Base64.
10. **Design a secure audit/diagnostic store** when recipient-identifying data is genuinely needed.
11. **Enforce access controls and retention** on logs/telemetry/exports.
12. **Test success, retries, failures, and nested exceptions** with synthetic markers.
13. **Monitor logging configuration changes** and alert on unexpected debug activation.
14. **Define an incident runbook** for accidental data exposure.
15. **Train support/operators** to look up notification IDs via authorized tools instead of asking for raw emails pasted into tickets.

## 51. Pre-deployment checklist

- [ ] No `mimeMessage.writeTo` to console/logs.
- [ ] No logging of full `SimpleMailMessage`/`MimeMessage`/`PreparedMail`.
- [ ] No logging of full To/Cc/Bcc/Subject/HTML/plain text.
- [ ] No logging of OTPs/reset URLs/credentials/attachments.
- [ ] `mail.debug` and session debug disabled by default.
- [ ] Exception logging does not print recipients in SMTP replies.
- [ ] Log statements use allowlisted fields.
- [ ] MDC is cleared after tasks, with no PII.
- [ ] Trace attributes and metric labels contain no email addresses.
- [ ] HTTP request logging does not capture mail bodies.
- [ ] Spring Integration logging does not serialize entire Messages.
- [ ] Retry logs contain only attempt ID/outcome/next retry.
- [ ] Bcc does not leak into logs or public MIME headers.
- [ ] Log access, retention, encryption, and exports are controlled.
- [ ] Tests verify synthetic secret markers never appear in logs.
- [ ] Runbooks exist for revocation/debugging/incidents when data is accidentally logged.

## 52. Key takeaways

- An email message is **business content**, not a safe log event.
- To/Cc/Bcc, Subject, HTML, plain text, headers, attachments, and provider replies can all contain PII/secrets.
- `MimeMessage.writeTo(...)` serializes MIME without redaction.
- `mail.debug`/`Session.setDebug(true)` can emit protocol traffic outside the SLF4J logger.
- `MailSendException` and nested exceptions must be handled via sanitized error classification.
- `record.toString()` on DTOs holding email bodies is a common leak vector.
- Log minimally: `notificationId`, `attemptId`, stage, category, provider, outcome, and duration.
- Whitelists beat blacklists because DTOs can gain new sensitive fields.
- Masking does not equal anonymization; unkeyed SHA-256 over email addresses can be guessed.
- MDC, tracing, APM, metrics, and HTTP body logging are all data egress paths.
- Sampling is unsafe if sampled entries still contain raw secrets.
- Logs require dedicated retention, access controls, and export procedures.
- Use GreenMail/Mailpit and synthetic fixtures to inspect MIME in tests.
- When recipient data is accidentally logged, execute the incident runbook across the entire log pipeline rather than merely deleting a local file.
- Correlating via opaque IDs still lets you investigate failures, retries, and deliveries without storing full emails.

**Core principle:** In Spring Framework Mail production, **log the mail-sending lifecycle, not the email itself**. Design structured events using an allowlist, link events with notification/attempt IDs, classify errors instead of printing raw exceptions, restrict protocol debugging, and keep recipient data in an appropriately authorized store. A system can observe SMTP successes, retries, bounces, and outages thoroughly without copying private recipient content into millions of log lines.

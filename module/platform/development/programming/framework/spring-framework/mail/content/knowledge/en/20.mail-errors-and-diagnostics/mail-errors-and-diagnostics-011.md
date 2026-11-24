# Never Log Passwords or Sensitive Content When Using Spring Framework Mail

When an email fails to send, a developer's natural reaction is to turn on `DEBUG` and print the entire exception, `MimeMessage` content, or SMTP configuration to find the cause. While those actions can speed up troubleshooting in test environments, they risk pushing **SMTP passwords, login tokens, email addresses, OTP codes, password reset links, message bodies, and attachments** into logging systems.

Logs are often aggregated across many places: container stdout, server files, log collectors, centralized observability platforms, long-term archives, support dashboards, and backups. A secret accidentally logged can be copied across all of these systems, outside the original application's control and surviving long past its intended lifetime.

**Core principle: log only enough data to diagnose sending status; never log credentials or private content.** Proactively strip sensitive data at the point logs are created; collector-side redaction is only a secondary defense layer.

In the context of Spring Framework Mail, this lesson covers how to design safe logging for `JavaMailSender`, `MimeMessageHelper`, Jakarta Mail, SMTP transport, queue workers, and retries. The goal is to remain able to analyze failures without turning logging systems into copies of emails.

## 1. Types of Data That Must Not Appear in Logs

An email contains multiple layers of data. Not every field shares the same sensitivity level, yet many fields are easily underestimated.

| Group | Examples | Risk if exposed in logs |
|---|---|---|
| **SMTP credentials** | Passwords, app passwords, OAuth access/refresh tokens, API keys | Mail account takeover, quota abuse, spoofed sending |
| **Verification codes or links** | OTPs, magic links, reset-password tokens, token-bearing verification URLs | Log readers can use codes or hijack verification flows |
| **Message content** | `text/plain`, `text/html`, template variables | Leaks personal data, orders, records, business info |
| **Headers** | `To`, `Cc`, `Bcc`, `Reply-To`, `Subject` | Exposes identities, relationships, conversation topics, Bcc lists |
| **Attachments** | PDF invoices, CSV, XLSX, inline images, filenames | Exposes financial, customer, or internal documents |
| **Paths/URLs** | `file://...`, signed-token URLs, storage paths | Exposes internal structure or resource access paths |
| **Provider errors** | SMTP reply text, exception causes, diagnostic dumps | May contain addresses, domains, header fragments, or externally controlled data |
| **Linking identifiers** | `Message-ID`, correlation ID, job ID | May allow correlating records or identifying subjects if carelessly designed |

Some information **can be logged under control**: normalized error codes, task types, send timestamps, retry counts, category-level provider names, `SUBMITTED`/`FAILED` statuses, and a random internal ID used for lookup.

Never treat email addresses as harmless metadata. For instance, looking merely at recipient lists and subjects can reveal relationships between users, businesses, and sensitive workflows. Even when an application serves customer support, email addresses do not belong in every mail worker log.

## 2. Designing Logs Around a Minimal Data Model

Ask: *During an incident, what does an operator actually need to act?*

Typically, a sufficient diagnostic record includes:

- A non-PII email job ID.
- A defined email category, e.g., `ORDER_CONFIRMATION`.
- Processing stage: `QUEUED`, `PREPARING`, `SMTP_SUBMITTING`, `SUBMITTED`, or `FAILED`.
- Normalized error code or error class, e.g., `SMTP_AUTH`, `SMTP_TIMEOUT`, `SMTP_REJECTED`.
- Attempt number and processing duration.
- Timestamp and appropriate instance/worker identifier.

Example of a structured log event:

```json
{
  "event": "mail_submission_failed",
  "mailJobId": "b6c821d5-7e8d-41ea-9a04-7e28e84def21",
  "mailType": "ORDER_CONFIRMATION",
  "attempt": 2,
  "stage": "SMTP_SUBMISSION",
  "failureClass": "SMTP_TIMEOUT",
  "retryable": true,
  "elapsedMs": 5032
}
```

This log snippet needs no password, recipient address, subject, or HTML body to recognize a timeout issue. For deeper lookups, authorized staff can use `mailJobId` to view metadata in the business system under separate permissions and audit controls.

### Examples of Logs Not to Write

```java
// Wrong: puts secrets into logs.
log.info("SMTP config: username={}, password={}", username, password);

// Wrong: can expose personal data and tokens.
log.debug("Sending mail to={}, subject={}, html={}",
        recipient, subject, htmlBody);

// Wrong: object metadata may expose every field via toString().
log.info("Outgoing mail request: {}", mailRequest);

// Dangerous if cause/provider text contains sensitive data.
log.error("Mail failed for {}: {}", recipient, exception.getMessage());
```

### Safer Examples

```java
log.info(
        "mail event={} jobId={} kind={} attempt={}",
        "submitted",
        job.id(),
        job.kind().name(),
        job.attempt());

log.warn(
        "mail event={} jobId={} failureClass={} retryable={}",
        "submission_failed",
        job.id(),
        failureClass.name(),
        retryable);
```

This example assumes `job.id()` is an internal ID that cannot be reversed into tokens/PII, while `kind` and `failureClass` are bounded enums. If the job ID itself embeds an email or account number, it is also unsafe to log.

## 3. Never Log SMTP Passwords, App Passwords, or Access Tokens

Spring Boot can configure SMTP via `spring.mail.*` properties:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
```

The placeholders above are illustrative environment variable names. Never put real secret values directly into committed configuration files. For production environments, use a secret manager or the platform's secret management mechanism.

**Being able to read a secret does not mean permission to write it to logs.** Never log the `Environment` object, full `Properties`, or `JavaMailSenderImpl` just to check whether environment variables were injected.

### Diagnosing Missing Configuration Without Exposing Values

When suspecting missing SMTP configuration:

```java
boolean credentialConfigured =
        password != null && !password.isBlank();

log.info(
        "mail smtpCredentialConfigured={} hostConfigured={} tlsRequired={}",
        credentialConfigured,
        smtpHost != null && !smtpHost.isBlank(),
        startTlsRequired);
```

Even the SMTP login account name does not necessarily need logging. If operations need to distinguish sending accounts, use a fixed alias like `primary-outbound` or `transactional` instead of printing the full username.

A `passwordPresent=true` check only proves the configuration string is non-empty, **not that credentials are valid**. If the server rejects AUTH, record category `SMTP_AUTHENTICATION_FAILED` and verify secrets through administrative processes rather than copying secrets into logs.

### SMTP AUTH Can Carry Multiple Credential Types

Depending on the provider, systems may use:

- Username and app password.
- Service-specific SMTP password.
- OAuth 2.0 access token via the corresponding SMTP AUTH mechanism.
- Network-policy and identity-based SMTP relay.
- API key if the application uses a mail provider adapter instead of SMTP.

All of these secrets must be shielded. A short-lived access token does not make logging it safe; logs can be read while the token is still valid.

## 4. Exercise Caution When Enabling Jakarta Mail Debug

Jakarta Mail provides debug capabilities for diagnosing SMTP sessions. In many implementations, `mail.debug=true` increases protocol output; `mail.debug.auth` controls whether AUTH-related details appear in debug output.

Specifically:

- **Never enable `mail.debug.auth=true` in production.**
- Do not enable `mail.debug=true` just because one email failed without assessing what data could be logged.
- Do not assume all debug output passes through SLF4J and application redaction filters; depending on Jakarta Mail/Angus Mail version, debug output may write to a separate stream.
- Never capture raw protocol transcripts and attach them to support tickets without inspecting contents.

Production configuration example:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": false
      "[mail.debug.auth]": false
```

In practice, these settings sit alongside host/port/TLS properties. When diagnosing, raised debug configs should be time-boxed, narrowly scoped, and approved per operational policy.

### Why Disabling Auth Debug Alone Is Insufficient

`mail.debug.auth=false` is an important safeguard for credentials during protocol debugging, **but it does not replace the policy against logging mail content**. Protocol lines and server replies can still contain sender/recipient addresses, server names, and other metadata. Proxies/gateways or network tracing layers may also create separate captures outside this flag's control.

Never feed real passwords or tokens into "testing whether debug logs mask them" in production.

### When Protocol Troubleshooting Is Truly Necessary

A cautious procedure:

1. Reproduce in a test environment using revocable test accounts, never customer mail.
2. Identify the specific question: DNS, TCP connect, TLS, SMTP AUTH, `MAIL FROM`, `RCPT TO`, or `DATA`.
3. Enable only the necessary logging for a short period.
4. Confirm outputs contain no secrets, recipients, or message bodies before sharing.
5. Disable debug and verify configuration returned to its safe baseline.
6. Delete test captures per retention and revoke test credentials if ever exposed.

In production, prefer measuring SMTP return code groups, latency, connection errors, and retry statuses without capturing full transcripts.

## 5. Never Log Raw `MimeMessage` or MIME Bodies

A `MimeMessage` can contain:

- `text/plain` and `text/html`.
- `Subject`, `From`, `To`, `Cc`, `Bcc`.
- `Content-ID` of inline images.
- PDF, CSV, XLSX, and other attachments.
- MIME boundaries, headers, transfer encodings.

Calling `MimeMessage.writeTo(OutputStream)` and logging the result creates a complete copy of the email in logs:

```java
// DO NOT use this approach for production debugging.
ByteArrayOutputStream buffer = new ByteArrayOutputStream();
message.writeTo(buffer);
log.debug("Raw outgoing message: {}",
        buffer.toString(StandardCharsets.UTF_8));
```

Even when attachments are Base64-encoded, content can still be decoded and is in no way anonymized. **Base64 is encoding, not security encryption.**

### Do Not Log HTML After Rendering Templates

For email templates:

```java
String html = templateRenderer.render("reset-password", variables);
```

`html` may contain user names, token links, OTPs, monetary amounts, or other sensitive data. If you need to verify template execution:

```java
log.debug(
        "mail templateRendered={} version={} jobId={}",
        "PASSWORD_RESET",
        templateVersion,
        jobId);
```

Do not log `variables` if they contain personal info or secrets. Also avoid serializing whole template DTOs to JSON hoping the log collector will "filter" them later; sensitive data already crossed unnecessary boundaries.

### Attachments Can Be Sensitive from Content Down to Filenames

Never log:

```java
log.debug("Attachment bytes: {}", Arrays.toString(invoicePdf));
log.debug("Attachment location: {}", fileSystemPath);
log.debug("Full attachment: {}", Base64.getEncoder()
        .encodeToString(invoicePdf));
```

If sizing is needed to diagnose `message too large`:

```java
log.info(
        "mail attachmentCount={} totalAttachmentBytes={} jobId={}",
        attachmentCount,
        totalAttachmentBytes,
        jobId);
```

Even filenames can contain full names, customer IDs, or contract numbers. Depending on needs, log controlled MIME types (`application/pdf`) and sizes instead of raw filenames.

## 6. Headers Are Also Sensitive Data

Many teams mask HTML bodies yet still log full headers:

```text
From: notifications@example.org
To: customer@example.net
Bcc: hidden-recipient@example.net
Subject: Private customer transaction confirmation
Message-ID: <...>
```

Headers reveal who communicates with whom, transaction types, and sometimes mail server hops. The `Bcc` header is especially sensitive because it exposes hidden recipients.

**Never use `message.getAllHeaders()` or `message.getRecipients(...)` as default log data.** Many SMTP exceptions involving invalid addresses can also embed recipients in message text or nested objects.

### Distinguishing Lookup Identifiers

Generate `mailJobId` at the application layer:

```java
UUID mailJobId = UUID.randomUUID();
```

In logs, use only this ID to correlate:

```text
mail jobId=... stage=QUEUED
mail jobId=... stage=SMTP_SUBMITTING
mail jobId=... stage=SUBMITTED
```

Never use raw recipient emails, reset tokens, or usernames as IDs. The email's `Message-ID` can be helpful for provider support, yet does not need to appear in every log and may require access controls.

## 7. Exceptions and Stack Traces Can Leak Data

A common logging pattern:

```java
log.error("Cannot send mail", ex);
```

This is not always safe. Throwables can contain:

- SMTP replies echoing recipient addresses.
- Sending account hostnames/usernames.
- Attachment filenames or filesystem paths.
- Template errors carrying variables and rendered content.
- Details from provider nested exceptions.
- Custom exceptions whose `toString()` embeds payloads.

Therefore, avoid dumping entire exception trees into broadly accessible logs. For incidents requiring stack traces, consider a dedicated diagnostic channel with filtered data, restricted access, and short retention.

### Do Not Log Raw `ex.getMessage()`

Example:

```java
catch (MailException ex) {
    log.error("Mail error: {}", ex.getMessage()); // May leak metadata.
}
```

There is no guarantee `getMessage()` lacks identifying data. Transport error messages can be constructed from SMTP server replies; never treat them as trusted strings for logging.

### Be Careful with `MailSendException.getFailedMessages()`

`MailSendException` can expose details about failed messages. This map may hold `MimeMessage` as keys and exceptions as values. Never log the whole map:

```java
// Do not log because keys/values may reveal content and addresses.
log.error("Failed messages: {}", ex.getFailedMessages());
```

If statistics are needed, extract only the **count** of failed messages without printing keys/values:

```java
int failedCount = ex.getFailedMessages().size();
log.warn("mail failureCount={} jobId={}", failedCount, jobId);
```

Not every SMTP error is represented by the same exception structure. Design an error classifier based on allowlisted fields without passing raw provider messages into the logging layer.

## 8. Classifying Errors into Safe Codes

For dashboards, logs, and retries, applications should translate exceptions into a **bounded set of error categories**.

Example:

```java
package com.example.mail;

public enum SafeMailFailure {
    AUTHENTICATION,
    CONNECTION,
    TIMEOUT,
    RECIPIENT_REJECTED,
    PROVIDER_THROTTLED,
    MESSAGE_TOO_LARGE,
    MIME_PREPARATION,
    UNKNOWN
}
```

This is an application-designed category, not a built-in Spring Mail enum. When an exception lacks reliable data for classification, use `UNKNOWN` and keep detailed diagnostics in a protected store.

### Classify by Type Rather Than Message Text

Example of a minimal classifier:

```java
package com.example.mail;

import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailParseException;

public final class MailFailureClassifier {

    public SafeMailFailure classify(MailException ex) {
        if (ex instanceof MailAuthenticationException) {
            return SafeMailFailure.AUTHENTICATION;
        }
        if (ex instanceof MailParseException) {
            return SafeMailFailure.MIME_PREPARATION;
        }
        return SafeMailFailure.UNKNOWN;
    }
}
```

The example intentionally **does not** read `ex.getMessage()` to infer errors. In production, extend it using known SMTP status codes and exception types of your active provider/Jakarta Mail version; avoid brittle regexes on server reply text.

An error classified as `UNKNOWN` can still be counted and alerted on. There is no need to sacrifice security by printing full protocol transcripts just to subdivide error buckets further.

## 9. Example of Safe Mail Logging in Spring Boot

The example below uses `JavaMailSender` and `MimeMessageHelper` to send email after business validation, logging only ID, email kind, outcome, and duration.

```java
package com.example.mail;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SafeMailService {

    private static final Logger log =
            LoggerFactory.getLogger(SafeMailService.class);

    private final JavaMailSender sender;
    private final MailFailureClassifier classifier;

    public SafeMailService(
            JavaMailSender sender,
            MailFailureClassifier classifier) {
        this.sender = sender;
        this.classifier = classifier;
    }

    public void send(
            UUID jobId,
            MailKind kind,
            String recipient,
            String subject,
            String plainText) {

        long startedNanos = System.nanoTime();
        log.info(
                "mail stage=SMTP_SUBMITTING jobId={} kind={}",
                jobId, kind.name());

        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, false, StandardCharsets.UTF_8.name());

            helper.setFrom("notifications@example.org");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(plainText, false);

            sender.send(message);

            log.info(
                    "mail stage=SUBMITTED jobId={} kind={} elapsedMs={}",
                    jobId,
                    kind.name(),
                    (System.nanoTime() - startedNanos) / 1_000_000);
        } catch (MessagingException ex) {
            log.warn(
                    "mail stage=FAILED jobId={} kind={} failureClass={}",
                    jobId, kind.name(), SafeMailFailure.MIME_PREPARATION);
            throw new IllegalStateException(
                    "Unable to prepare mail message", ex);
        } catch (MailException ex) {
            SafeMailFailure failure = classifier.classify(ex);
            log.warn(
                    "mail stage=FAILED jobId={} kind={} failureClass={}",
                    jobId, kind.name(), failure.name());
            throw ex;
        }
    }
}
```

In the example:

- `recipient`, `subject`, and `plainText` are used only to build the message and never enter logs.
- `jobId` must be generated by the application independently of recipient addresses.
- `MailKind` is an application-defined enum like `PASSWORD_RESET` or `ORDER_CONFIRMATION`, never arbitrary user input.
- Duration is measured via `System.nanoTime()`, suitable for elapsed time.
- `SUBMITTED` indicates Spring Mail succeeded per submission-layer response, not proof the email was delivered.
- Exceptions are **rethrown** so retry/job layers can handle them, yet upper layers must also follow safe logging policies. A global exception handler logging entire cause chains can expose data that the service above carefully avoided.

If only simple text mail is needed, `SimpleMailMessage` also works, with the same rule against logging bodies/passwords. For HTML/attachments, enable multipart mode and use `addInline`/`addAttachment` rather than serializing MIME into logs.

### Classifier as a Spring Bean

When using dependency injection as above, annotate the classifier as a component:

```java
import org.springframework.stereotype.Component;

@Component
public final class MailFailureClassifier {
    public SafeMailFailure classify(MailException ex) {
        if (ex instanceof MailAuthenticationException) {
            return SafeMailFailure.AUTHENTICATION;
        }
        if (ex instanceof MailParseException) {
            return SafeMailFailure.MIME_PREPARATION;
        }
        return SafeMailFailure.UNKNOWN;
    }
}
```

In real code, organize full imports and maintain a single class definition. Both snippets illustrate separating mail sending from failure classification; do not duplicate `MailFailureClassifier`.

## 10. Sensitive Data Can Enter Logs Through `toString()`

Even when developers avoid logging `password` directly, a DTO or record with an auto-generated `toString()` can accidentally print every field:

```java
public record MailRequest(
        String recipientEmail,
        String subject,
        String htmlBody,
        String resetToken) {
}
```

With Java records, the default `toString()` prints all components. The statement:

```java
log.debug("mailRequest={}", mailRequest);
```

can log both `resetToken` and `htmlBody`.

### Do Not Rely Solely on Custom Object Masking

A class can override `toString()`:

```java
public final class OutgoingMailCommand {

    private final UUID jobId;
    private final String recipient;
    private final String body;

    // Constructor/getters omitted for brevity.

    @Override
    public String toString() {
        return "OutgoingMailCommand{jobId=" + jobId + "}";
    }
}
```

This reduces risk when an object is formatted accidentally, **but does not replace the rule to log only allowlisted fields**. Another logger or framework serializer may use reflection/getters to access fields despite a safe `toString()`.

With Lombok `@Data` or `@ToString`, consider `@ToString.Exclude` for secrets, though a safer choice is never logging whole command objects carrying private data in the first place.

## 11. Do Not Log Request Bodies or Template Contexts Out of Habit

An application may expose an endpoint:

```text
POST /api/mail/send
```

The payload may contain recipient, subject, HTML body, attachment references, or tokens. An HTTP logging filter recording full bodies before the service executes can leak data even when the mail service has zero `log.debug` statements.

Control points:

1. HTTP filter/access logs: avoid logging query strings if URLs contain tokens; do not log request bodies by default.
2. Controller advice: never echo raw DTOs into error responses or exception messages.
3. AOP interceptors: avoid logging all method arguments/return values on mail-handling methods.
4. Template renderers: never log entire variable maps.
5. Serialization/debuggers: never auto-dump objects holding recipients/tokens/bodies.
6. Tracing instrumentation: set only safe attributes; never attach message bodies as span attributes.

### Example of a Risky Interceptor

```java
// Anti-pattern: can turn every argument into log content.
@Around("execution(* com.example.mail..*(..))")
public Object traceAll(ProceedingJoinPoint pjp) throws Throwable {
    log.debug("arguments={}", Arrays.toString(pjp.getArgs()));
    return pjp.proceed();
}
```

If AOP/tracing is needed, log only the operation name and IDs verified to contain no PII. Avoid applying generic argument logging to packages like `auth`, `mail`, and `payment`.

## 12. MDC and Correlation IDs: Tracing Without Content

MDC allows attaching short metadata to log lines within one execution flow:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
             MDC.putCloseable("mailJobId", job.id().toString())) {

    log.info("mail stage=STARTED kind={}", job.kind().name());
    mailProcessor.process(job);
    log.info("mail stage=FINISHED");
}
```

The benefit is every log line can share `mailJobId` without passing recipients or subjects. Still, follow these rules:

- Put only non-secret internal IDs into MDC.
- Clear MDC via `close()` or `finally` so thread pools do not carry an old job's context to a new job.
- With `@Async`, MDC does not automatically propagate cleanly across all executors/threads. If context copying is needed, use a selective `TaskDecorator` that copies only allowlisted fields.
- Never put raw JWTs, session cookies, OTPs, email addresses, or full URLs with query strings into MDC.

### Async Context Propagation Must Be Controlled

If a request thread holds inappropriate data in MDC and a `TaskDecorator` copies the entire map to a worker, secrets can spread into mail logs. Instead, construct worker context solely from `mailJobId` and safe fields, or strictly filter keys before propagating.

Never use raw correlation IDs taken verbatim from untrusted request headers without format validation and length limits; arbitrary input can corrupt logs or inject unauthorized data.

## 13. Metrics: Measuring Errors Without Sensitive Labels

Micrometer and Spring Boot Actuator can measure mail performance using counters and timers without logging payloads. Example:

```java
registry.counter(
        "mail.submission.attempts",
        "kind", kind.name(),
        "outcome", "failed",
        "failure", failure.name())
        .increment();
```

Safe labels typically have small value sets:

| Label | Should use? | Reason |
|---|---|---|
| `kind=PASSWORD_RESET` | Yes, if bounded enum | Finite business categories |
| `outcome=accepted/failed` | Yes | Normalized status |
| `failure=AUTHENTICATION` | Yes | Bounded error classification |
| `provider=primary/backup` | Yes | Application-controlled alias |
| `recipient_email=...` | No | PII and high cardinality |
| `subject=...` | No | May contain sensitive content |
| `job_id=...` | Not as a metric tag | Extremely high cardinality; use logs/tracing |
| `exception_message=...` | No | Can leak data and spawn unbounded series |
| `tenant_id=...` | Weigh carefully | May be a sensitive ID/high cardinality |

The `mail.submission.attempts` metric counts **attempt executions**, not unique emails: retries can generate multiple attempts for one job. Maintain separate metrics for enqueued, submitted, permanently failed, and expired jobs.

Never place raw email bodies or SMTP passwords into metric exemplars, span attributes, log annotations, or dashboard tooltips just because they are "not logs".

## 14. Safe Logging Configuration in Spring Boot

A production application configuration typically targets `INFO`/`WARN` and avoids protocol debugging:

```yaml
logging:
  level:
    root: INFO
    org.springframework.mail: WARN
    jakarta.mail: WARN
    org.eclipse.angus.mail: WARN

spring:
  mail:
    properties:
      "[mail.debug]": false
      "[mail.debug.auth]": false
```

Exact logger names may vary by Jakarta Mail/Angus Mail library version and logging bridge. Verify your actual implementation; do not assume setting log levels alone suppresses debug output written straight to a `PrintStream`.

### Configurations Never to Leave Enabled Indefinitely

Avoid leaving:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
      "[mail.debug.auth]": true
```

in production configs. Never set `TRACE` across all of `org.springframework` just to investigate an SMTP error, as traces from other components can expose requests, security contexts, or template variables.

### Actuator and Configuration Endpoints

Actuator can expose environment variables, `configprops`, and loggers. Protect these endpoints with network policies, authentication, and authorization; never broaden exposure just to debug mail. Modern Spring Boot masks sensitive values in some endpoints, yet that is no reason to expose configuration dumps widely.

Example restricting endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Exact keys depend on your Boot version; check version docs to ensure no custom endpoint or extension bypasses masking policies. What matters is preventing any HTTP path from exposing secrets via config dumps.

## 15. Redaction: A Secondary Layer, Not the Sole Solution

Redaction or masking can hide certain patterns before logs are persisted. For instance, a log collector might mask keys named `password` or `authorization`. However:

- SMTP passwords can appear as Base64 strings inside AUTH transcripts.
- Tokens can sit inside URLs under varying parameter names.
- HTML bodies contain free-form content matching no fixed pattern.
- Secrets can be URL-encoded, JSON-escaped, or split across lines.
- Provider exceptions can use formats outside configured regexes.

Therefore, no universal regex can sanitize every email-containing log.

### Prefer Allowlists Over Blocklists

**Allowlist logging:** construct log events exclusively from fields verified safe, e.g., `jobId`, `kind`, `stage`, `failureClass`.

**Blocklist redaction:** ingest everything and try to scrub `password`, `token`, or email addresses.

Allowlists stop unauthorized data from entering the pipeline at the source; blocklists only try to clean up after data has already been emitted. Combining both adds defense in depth, yet allowlisting must remain the primary principle.

### Avoid Directly Hashing Email Addresses to "Anonymize"

Unsalted or globally salted email hashes can be reversed via dictionary attacks because email spaces are structured and many addresses are common. If you genuinely need to correlate an address across events, consider an internal identifier or key-managed HMAC instead of putting plain hashes in every log.

Even pseudonymized identifiers can still count as personal data in certain contexts. Apply appropriate access controls and retention policies.

## 16. Separating Operational Logs from Business Audits

Logs and audits are not the same kind of data:

- **Operational logs:** detect SMTP timeouts, retry counts, failing workers, elapsed times.
- **Business audits:** record who triggered an email, business reason, processing status, and related authorization.

Audits may need to store recipients or transaction data for business needs, yet should reside in a system with its own schema, access controls, and retention; there is no need to copy those fields into centralized operational logs.

Example audit metadata:

```text
MailJob
  id: UUID
  type: ORDER_CONFIRMATION
  businessRef: internal order id
  state: SUBMITTED
  createdAt: timestamp
  submittedAt: timestamp
  attemptCount: 2
  lastFailureClass: SMTP_TIMEOUT
```

If support staff need to inspect recipients or subjects, provide an access-controlled lookup screen backed by `MailJob`, without granting access to raw operational logs.

### Distinguishing `SUBMITTED` and `DELIVERED`

`JavaMailSender.send(...)` returning cleanly usually means submission to the SMTP server was accepted. This **does not guarantee mailbox delivery**. If the provider supplies delivery/bounce webhooks, record them as separate events with proper permissions and retention; never guess from logs that a message was read.

## 17. Logging in Retries, Queues, and Transactional Outboxes

In async mail sending, a single request may run through multiple retries. Logging full commands each time multiplies sensitive content.

Instead, each attempt can log:

```text
mail jobId=... kind=ORDER_CONFIRMATION attempt=1
     stage=SMTP_SUBMITTING

mail jobId=... kind=ORDER_CONFIRMATION attempt=1
     stage=FAILED failureClass=SMTP_TIMEOUT retryable=true

mail jobId=... kind=ORDER_CONFIRMATION attempt=2
     stage=SMTP_SUBMITTING

mail jobId=... kind=ORDER_CONFIRMATION attempt=2
     stage=SUBMITTED
```

These lines show total attempts, error categories, and final status without containing recipients/subjects/bodies.

### Do Not Log Outbox Payloads

Transactional outboxes often store JSON events or job payloads. Some events may contain recipients, template variables, attachment references, or tokens:

```java
// Do not print the entire outbox record.
log.debug("Processing outbox record: {}", outboxEvent);
```

Log only the ID, allowlisted event type, status, and attempt count. For payloads carrying secrets, avoid even storing plaintext secrets in the outbox; consider storing references to protected data and enforcing retention.

### Do Not Log Repeatedly Across Retry Layers

An exception might be logged in the repository, worker, retry scheduler, async handler, and global exception handler. If every layer logs the full cause chain, a single failure produces multiple copies and noisy logs.

Useful convention:

1. Lower layers return typed/caused errors to callers.
2. The job-owning layer classifies errors, updates state, and decides retries.
3. Only one layer is responsible for emitting the **operational failure event**.
4. Metrics count by outcome/attempt.
5. Sensitive diagnostics go through a separate restricted channel when truly needed.

## 18. Logging for SMTP Auth Failures, Rate Limits, and Recipients

Different SMTP errors need different signals. There is no need to open protocol dumps for all of them.

| Scenario | Suggested safe log | Must not log |
|---|---|---|
| Wrong SMTP credentials | `failureClass=AUTHENTICATION`, provider alias | Passwords, AUTH transcripts, access tokens |
| SMTP timeout | `failureClass=TIMEOUT`, duration, retry attempt | Full session debug, body |
| Provider rate limit | `failureClass=THROTTLED`, retryable, delay | Raw server reply containing untrusted data |
| Recipient rejected | `failureClass=RECIPIENT_REJECTED`, count | Full email addresses in centralized logs |
| MIME parsing error | `failureClass=MIME_PREPARATION`, template ID/version | Raw MIME or HTML body |
| Attachment too large | `failureClass=MESSAGE_TOO_LARGE`, byte count | File contents, private filenames |
| DNS/TLS error | `failureClass=CONNECTION` or `TLS_FAILURE` | Full config dump, keystore passwords |

When SMTP reply codes are genuinely needed to drive retries, extract numeric codes or normalized enums at the adapter layer. Never log raw SMTP response strings, as they may echo recipient addresses or server-controlled data.

### Note on Third-Party Library Logs

A mail provider SDK may log HTTP requests/responses, including authorization headers, if HTTP wire logging is enabled. Spring Mail uses SMTP, yet architectures often combine SMTP, REST providers, and network proxies.

Ensure safe logging configurations across every layer: HTTP clients, SMTP transport, mail workers, proxies/sidecars, gateways, and collectors. Blocking one log statement in a service is not enough if lower libraries still dump requests.

## 19. Testing to Prevent Secrets from Leaking into Logs

Write tests injecting fake yet recognizable sentinel strings into sensitive inputs, trigger failure paths, and assert the system **does not log** those strings.

Sentinel test example:

```text
fake SMTP password: TEST_SECRET_SMTP_DO_NOT_LOG
fake reset token:   TEST_RESET_TOKEN_DO_NOT_LOG
fake recipient:     private-recipient@example.invalid
fake HTML marker:   TEST_PRIVATE_BODY_DO_NOT_LOG
```

Never use real secrets in tests. Test data should belong to `example.invalid` or be synthetically generated.

### Testing with Logback `ListAppender`

Sketch example for a service with its own logger:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class SafeMailLoggingTest {

    @Test
    void shouldNotExposeMailSecretsInApplicationLogs() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                SafeMailService.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            // Use a failing mock sender and dummy input with sentinels.
            // triggerMailFailureWithFakeSecrets();

            String logs = appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .reduce("", (a, b) -> a + "\n" + b);

            assertFalse(logs.contains("TEST_SECRET_SMTP_DO_NOT_LOG"));
            assertFalse(logs.contains("TEST_RESET_TOKEN_DO_NOT_LOG"));
            assertFalse(logs.contains("private-recipient@example.invalid"));
            assertFalse(logs.contains("TEST_PRIVATE_BODY_DO_NOT_LOG"));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
```

This is an **illustrative skeleton**, not a standalone runnable test: projects must mock the sender and invoke the failing call before asserting. The test above only captures logs emitted via `SafeMailService`'s logger. It does not prove Jakarta Mail debug output or third-party libraries did not write to stdout/stderr; end-to-end verification must also inspect collectors, container logs, and all active output streams.

### Important Test Cases

| Scenario | What to verify |
|---|---|
| SMTP AUTH failure | Passwords/tokens never logged, even in error handlers |
| SMTP timeout with nested exception | Raw exception message containing recipients is not logged |
| HTML template containing OTP | Body or template variable map is not logged |
| Failing PDF attachment | Bytes, Base64, or sensitive file paths are not logged |
| Multiple queue retries | Each attempt logs only allowlisted metadata |
| `mail.debug` accidentally enabled | Production config blocks or alerts on it |
| Global exception handler | Does not auto-dump full command/cause chains |
| `@Async` worker using MDC | Context does not leak between two jobs |
| Log collector/forwarder | Does not re-expose fields masked at the app layer |
| Request/HTTP client logging | Bodies, authorization, or signed URLs are not logged |

Tests can combine static scanning to catch anti-patterns like `log.info("password..."` or `log.debug("body=..."`, though static scans miss object `toString()` leaks and protocol debug. Defense is required in both design and runtime configuration.

## 20. Controlling Logs in Production Environments

Preventing secrets from entering logs is the first step. Logs already generated still require protection:

- Grant log access only to authorized personnel.
- Scope permissions by service/environment; do not let every developer read all logs containing user metadata.
- Encrypt log transit and storage.
- Set short retention periods suitable for operational logs.
- Control log exports/downloads and audit access.
- Never auto-forward raw logs into chat/tickets or external support channels.
- Apply collector-level DLP/redaction as a secondary safeguard.
- Audit debug settings at deploy time, especially overrides via environment variables.

### Log Sampling

At high email volumes, sampling success events can cut costs. However, sampling must never drop critical failures or security alerts completely. One approach:

- Metrics count 100% of attempts and outcomes.
- Log `SUBMITTED` at an appropriate rate or per sampling policy.
- Log failures with safe metadata and classification codes, rate-limited by group if needed.
- Use `mailJobId` to look up exact status in the job store when needed.

Sampling does not make sensitive data safe. A log containing a password is still an incident even if sampled at 1%.

## 21. Responding When Passwords or Sensitive Content Were Logged

If someone discovers credentials or sensitive mail content in logs, treat it as a data exposure incident, not merely "cleaning up a debug line".

### 21.1. Immediate Containment

1. Disable the configuration emitting sensitive logs and deploy the fix.
2. Identify the exposed secret/data types, start/end window, affected record count, and destinations.
3. Restrict access or pause sharing on affected log systems if needed.
4. Never copy exposed secrets into tickets, chats, or emails announcing the incident.

### 21.2. Revoke/Rotate Secrets

If SMTP passwords, app passwords, API keys, or OAuth tokens were exposed:

- Revoke or rotate credentials per provider mechanisms.
- Update secret managers and perform a safe rolling deployment.
- Inspect unusual sending activity, quotas, and active sessions.
- Never assume "we deleted the log so the password is safe", as logs may already have been read or replicated.

For exposed reset tokens/OTPs, evaluate invalidating active tokens/challenges per authorization and business policies, rather than merely deleting log entries.

### 21.3. Handling Log Copies

Logs can reside across:

```text
Application process
    -> stdout / file
    -> node/container logging
    -> collector/agent
    -> central index
    -> export / alert / ticket
    -> archive / backup
```

Check copies per organizational procedures. Deleting from a dashboard does not automatically purge archives or snapshots. Avoid injecting more sensitive data during searches by pasting raw tokens into queries if systems record search history.

### 21.4. Impact Assessment and Notification

Depending on data and scope, security/legal teams may need to assess notification obligations under applicable policies and regulations. Keep a minimal incident record without copies of passwords or full emails. After remediation, add tests and guardrails to prevent recurrence.

## 22. Common Mistakes During Mail Diagnostics

| Symptom | Root cause | Fix |
|---|---|---|
| SMTP password appears when debug enabled | Protocol debug/auth debug turned on | Disable, rotate secret, bound scope |
| Logs contain password reset tokens | Template variables or rendered HTML printed | Log template ID/version, never variables/body |
| Logs contain `Bcc` list | Dumping raw `MimeMessage` or headers | Log only `jobId` and recipient count if needed |
| PDF file logged as Base64 | Serializing attachment for debugging | Log byte size and MIME type |
| Logs contain recipient emails | Exception message/provider reply or `toString()` | Classify errors into safe enums |
| DTO `toString()` leaks data | Logging whole object at `INFO`/`DEBUG` | Allowlist fields; do not log commands |
| Service logs safely yet collector still leaks | HTTP/SMTP wire loggers or tracing | Audit the entire pipeline |
| MDC carries stale `jobId` | ThreadLocal not cleared after task | Use `putCloseable`/`finally` |
| Metrics spawn millions of series | Using recipient/`jobId` as labels | Use low-cardinality tags only |
| Cannot distinguish timeouts from auth errors | Storing message text instead of category | Safe failure classifier |
| Need to debug yet cannot identify which email | Missing correlation ID/job store | Use `mailJobId` and safe tracing metadata |
| Failing email logged multiple times | Every layer dumps full exceptions | Standardize one layer to log operational events |
| Secret remains after deleting dashboard logs | Logs were forwarded or backed up | Incident response, rotation, check all copies |

## 23. Project Adoption Checklist

Before deploying a new email flow, the team should verify:

1. **Secret provenance:** SMTP credentials come from a secret manager or protected config; never hard-coded and never logged.
2. **Logging surface:** services, controllers, filters, AOP, executors, provider SDKs, Jakarta Mail debug, proxies, and collectors are all reviewed.
3. **Permitted metadata:** `jobId`, `mailType` enum, attempt, status, `failureClass`, `elapsedMs`.
4. **Never-logged data:** recipients, subjects, passwords/tokens, MIME bodies, attachment bytes, and signed URLs.
5. **Exceptions:** do not print `getMessage()`/cause chains at every layer; use safe failure classification.
6. **Debug policy:** protocol debug off by default; elevated diagnostic logging must be short-lived and tightly scoped.
7. **MDC/tracing:** use non-PII IDs only, clean context after tasks.
8. **Metrics:** low-cardinality tags; never use recipients/`jobId` as labels.
9. **Audit:** sensitive business metadata lives in an access-controlled store, not operational logs.
10. **Testing:** sentinel tests with dummy secrets on typical failure paths and runtime output checks where applicable.
11. **Retention:** logs stored and permissioned strictly as needed; never turn logs into email archives.
12. **Incident response:** documented procedures to revoke credentials, invalidate tokens, and handle log copies if leaks occur.

## 24. Frequently Asked Questions

**Should I log `spring.mail.password` to verify Spring Boot read the configuration?** No. Check only whether credentials are configured, or verify via a controlled test connection. Secret values never need to appear in logs.

**Is `mail.debug=true` safe if `mail.debug.auth=false`?** It cannot be treated as completely safe. The auth debug flag helps suppress credentials in certain AUTH flows, yet protocol logs still carry sensitive metadata and come from multiple logging streams. Never leave it on long-term in production.

**Can I log the entire `MimeMessage` and strip a few fields?** No. MIME structures hold bodies, attachments, and many headers; scrubbing after dumping easily misses items. Log application-constructed metadata instead.

**Is logging email addresses always forbidden?** Email addresses are personal data and may be necessary in certain authorized support workflows. However, default operational logs do not need full addresses. When a valid business need exists, restrict purpose, access, and retention rather than logging them on every line.

**Should I hash recipients before logging?** Simple hashing does not make data anonymous. Use internal IDs or properly designed, privacy-reviewed pseudonymization instead of assuming SHA-256 on emails is safe.

**Can I log the subject?** Not by default. Subjects can contain order numbers, user names, transactions, or private details. Use template IDs/mail types instead.

**Why can exception stack traces also be dangerous?** Throwables, nested causes, and SMTP replies can embed addresses, paths, or externally controlled values. Print stack traces only through approved channels or after data controls.

**How do I look up the recipient of a mail job when needed?** Use `mailJobId` to query the record in an access-controlled, audited business system instead of expanding operational logs to hold recipients.

**Should `MailSendException.getFailedMessages()` be logged?** No. The map can hold `MimeMessage` objects and exceptions, easily leaking content. If stats are needed, extract counts or normalized outcomes.

**Can I log attachment sizes?** Usually yes, as long as the size itself does not reveal sensitive facts in a specific context. Do not log bytes, Base64, or full filenames unnecessarily.

**Without logging passwords, how do I diagnose AUTH errors?** Log `failureClass=AUTHENTICATION`, provider alias, instance, timestamp, and attempt. Check credentials in the secret manager and run a controlled connection test.

**Does `@Async` make MDC safer?** No. MDC is thread-bound context. Without clearing or selective copying, workers can inherit data from other requests/jobs. Propagate only safe keys and clean up in `finally`.

**Is a log containing passwords acceptable if retained for only one day?** No. Secrets can be read and replicated within that single day. Short retention never replaces preventing exposure upfront.

**Is Base64 in logs considered securely encrypted?** No. Base64 is trivially decoded. Base64-encoded MIME attachments remain fully recoverable original data.

**Should every success event for every email be logged?** Depends on needs; aggregate metrics and job stores suffice for many cases. If logging per-job, use only allowlisted metadata, sensible retention, and sampling.

**Does successful SMTP sending mean the email reached the inbox?** No. That usually means only submission succeeded. Delivery, bounces, or complaints require separate provider/gateway events.

**What should be done if a secret leaked into logs?** Stop the log emission source, contain copies, revoke/rotate credentials, evaluate exposed tokens, and execute incident response per policy—do not just delete one line in a dashboard.

## 25. Related Technical References

- **Spring Framework Mail:** `JavaMailSender`, `MimeMessageHelper`, `MailException`, `MailAuthenticationException`, and `MailSendException`.
- **Spring Boot Externalized Configuration:** `spring.mail.*`, secret injection, and environment profiles.
- **Jakarta Mail / Eclipse Angus Mail:** `Session`, SMTP transport, `mail.debug`, and `mail.debug.auth`; verify exact behavior against your active version.
- **SLF4J and Logback:** structured logging, MDC, appenders, filters, and configuration.
- **Micrometer / Spring Boot Actuator:** counters, timers, metrics endpoints, and tag cardinality limits.
- **OpenTelemetry:** span attributes, event attributes, and privacy in distributed tracing.
- **OWASP Logging Cheat Sheet:** principles for avoiding secret logging, preventing log injection, and controlling log access.
- **Operational security guidelines:** secret management, rotation, retention, auditing, and incident response suited to your deployment environment.

---

**Key takeaway:** diagnosing email does not require writing passwords, access tokens, OTPs, recipients, subjects, HTML bodies, raw `MimeMessage`, or attachments to logs. Use `mailJobId` and normalized status/error codes; disable protocol/auth debug in production; control exceptions, `toString()`, MDC, tracing, and log collectors; and measure counts with metrics. When sensitive data is found in logs, treat it as a security incident and revoke affected secrets promptly. **Logs should help locate sending failures, never become copies of emails and SMTP accounts.**

# Preserving Correlation IDs Across Mail Sending Layers

An email in a Spring Framework Mail application can travel through many layers before being sent: HTTP controller, business service, domain event, template renderer, queue, worker, `JavaMailSender`, SMTP server, and finally status webhooks from the provider. If each layer logs independently without a linking identifier, when an email is delayed or fails it becomes very hard to answer seemingly simple questions:

- Which request or business event created the email send request?
- Was the email created once or submitted multiple times?
- Did the task stall at the template layer, queue, worker, SMTP connection, or receiving system?
- Do logs from a worker running minutes after the initial request belong to the same process?
- Which email does a delivery/bounce event returned from the provider correspond to?
- Which request was affected by a `MailAuthenticationException` or `MailSendException`?

A **correlation ID** is an identifier used to link logs and records belonging to the same workflow. To preserve that ID through the mail sending pipeline, pass it **as explicit data** across layer, thread, process, and message broker boundaries; then inject it into logging contexts such as MDC for convenient observability. Relying solely on a thread-local variable is insufficient when sending asynchronously.

This lesson covers designing identifiers, generating and validating correlation IDs, propagating across Spring MVC and `@Async`, persisting in queues/outboxes, tying to SMTP and webhook outcomes, and avoiding data leaks or confusing correlation IDs with email `Message-ID`s.

## 1. What Is a Correlation ID and What Problem Does It Solve?

Suppose a user confirms an order and the application sends a notification email. In a multi-instance environment, logs may be scattered like this:

```text
HTTP service:       Order confirmed
Notification layer: Mail request created
Queue consumer:     Processing mail job
Template renderer:  Rendered order-confirmation/v3
SMTP adapter:       SMTP submission failed
```

Without a linking key, it is hard to tell whether these five logs refer to the same email.

With a correlation ID:

```text
correlationId=corr-63de orderId=ORD-401
    HTTP: Order confirmed

correlationId=corr-63de notificationId=notif-918
    Notification: Mail request created

correlationId=corr-63de notificationId=notif-918
    Worker: Processing mail job

correlationId=corr-63de notificationId=notif-918
    Renderer: Template rendered

correlationId=corr-63de notificationId=notif-918 attemptId=try-2
    SMTP: Authentication failed
```

A log query on `correlationId=corr-63de` reconstructs the processing flow. Querying `notificationId=notif-918` narrows down to one specific notification; `attemptId=try-2` narrows down to one send attempt.

**Correlation IDs aid diagnostics; they are not an authentication mechanism, duplicate-prevention guarantee, or delivery guarantee.** If those properties are needed, the application must implement idempotency, durable state persistence, and separate access rules.

## 2. Distinguishing Identifier Types in a Mail Sending System

Multiple identifier types coexist in an email sending chain with different meanings.

| Identifier | Scope | Purpose |
|---|---|---|
| `correlationId` | A related business flow/request | Links logs and processing steps across layers/threads/processes. |
| `requestId` | One specific HTTP request | Diagnoses a single API call. |
| `traceId` | One distributed trace | Tracks spans and latency across components when tracing is enabled. |
| `eventId` | One domain event | Identifies an emitted business event. |
| `notificationId` | One logical notification | Identifies an email requested for a recipient. |
| `attemptId` | One send attempt | Distinguishes first, second, and third retries. |
| `idempotencyKey` | An operation needing duplicate-submit protection | Helps prevent creating multiple logical notifications for the same request. |
| `Message-ID` | RFC 5322 email header | Internet message identifier; can be used for threading/diagnostics. |
| `providerMessageId` | Email provider's system | Looks up submission/delivery/bounce on the provider side. |

A single order may trigger emails to the customer, seller, and operations team. They can **share a correlation ID**, yet must have **distinct notification IDs**.

Example:

```text
correlationId = corr-order-401
eventId       = event-401-confirmed

    +-- notificationId = notif-customer-401
    |       recipient = customer
    |       attemptId = try-customer-1
    |
    +-- notificationId = notif-seller-401
    |       recipient = seller
    |       attemptId = try-seller-1
    |
    +-- notificationId = notif-ops-401
            recipient = operations
            attemptId = try-ops-1
```

With only a correlation ID and no notification ID, the three emails cannot be clearly told apart. Conversely, if each layer invents a new correlation ID without keeping the original, logs break apart.

### How Does Correlation ID Differ from `Message-ID`?

`Message-ID` is a MIME header, for example:

```text
Message-ID: <c4b7e13d.20261112@mailer.example.org>
```

It belongs to the email itself. The SMTP server or email provider may generate, preserve, or alter other identifiers during processing. `Message-ID` is not an HTTP request ID and is not guaranteed to be echoed in every webhook.

**Do not replace correlation ID with `Message-ID`.** Maintain the mapping among correlation ID, notification ID, attempt ID, `Message-ID` if present, and provider message ID in the mail-sending record.

## 3. Choosing Scope and When to Generate Correlation IDs

An easy-to-operate policy:

1. When an HTTP request enters the application, generate or accept a validated correlation ID.
2. If processing starts from a scheduler, broker, CLI, or domain event without an HTTP request, generate the correlation ID at that entry point.
3. Carry the same correlation ID throughout the related business flow.
4. Generate a distinct notification ID for each logical email.
5. Generate a new attempt ID for each SMTP call, while keeping the same notification ID and correlation ID across retries.

Example:

```text
HTTP request corr-A
  └── Order created
      └── Mail request notif-X
          ├── Attempt 1 try-X1: SMTP timeout
          └── Attempt 2 try-X2: SMTP accepted
```

Logs of both attempts must carry the same `corr-A` and `notif-X`; do not automatically change the correlation ID on the second retry.

### Use UUID or ULID?

You can use random UUIDs:

```java
String correlationId = UUID.randomUUID().toString();
```

ULIDs or equivalent IDs also work if your system standardized on them. More important than the ID format are:

- Sufficient collision resistance within system scope.
- Contains no passwords, emails, phone numbers, or personal data.
- Bounded length.
- Can be validated before use.
- Generated once at the entry point and propagated onward.

Never build correlation IDs by concatenating email addresses and timestamps directly. That leaks data and may not guarantee uniqueness.

## 4. Safely Accepting Correlation IDs from HTTP Requests

Some systems accept IDs from an `X-Correlation-ID` header or gateway. Client headers can be spoofed, overly long, or contain newlines, so establish a clear trust policy.

Two main approaches:

- **Always generate internally:** ignore client-sent IDs; safe and simple.
- **Accept from a trusted gateway:** the gateway validates/normalizes the header; the application still validates structure and length limits.

Never take arbitrary strings from the Internet and write them straight into logs or MIME headers.

Example Spring MVC filter:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String incoming = request.getHeader(HEADER);

        String id = incoming != null
                && SAFE_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        String previous = MDC.get("correlationId");

        try {
            request.setAttribute(ATTRIBUTE, id);
            response.setHeader(HEADER, id);
            MDC.put("correlationId", id);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    }
}
```

Key points:

- `OncePerRequestFilter` suits servlet request processing.
- Regex and length limits reject arbitrary headers.
- `request.setAttribute(...)` places the ID into request context.
- Response header helps clients report errors with the ID when contacting support.
- `MDC.put(...)` attaches the ID to logs on the same thread.
- The `finally` block restores MDC before returning the thread to the pool.

This example does not turn headers into a trusted source. In systems with strict security boundaries, **always generate an internal correlation ID** and store any external request ID in a separate field, linking them only in appropriately authorized systems.

### With Servlet Async Dispatch

Async dispatch mechanisms may use different threads or invoke filters across dispatches. Never assume MDC from the servlet thread is always present on async threads. Pass correlation IDs explicitly into commands/events, or use tracing library instrumentation.

## 5. What Is MDC and Why Is It Not Enough to Preserve IDs?

**MDC** (*Mapped Diagnostic Context*) is a mechanism in logging frameworks like SLF4J/Logback to attach key-value pairs to the current thread's context.

Example:

```java
MDC.put("correlationId", id);

logger.info("Preparing notification");
```

Logback can print the correlation ID in its pattern:

```xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>
        %d{ISO8601} %-5level [%thread]
        correlationId=%X{correlationId:-missing}
        %logger - %msg%n
      </pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

MDC is great for logging, yet relies on **thread-local state**. When crossing into `@Async`, thread pools, Kafka/RabbitMQ consumers, or another process, current MDC **does not automatically become job data**.

Two risks exist:

1. **Lost ID:** the worker thread has no MDC, logging `correlationId=missing`.
2. **Stale ID leakage:** thread pools reuse threads whose MDC was not cleared, making job B log job A's ID.

Therefore, the rule is: **the correlation ID lives in the send request's data; MDC is only a temporary representation for logging.**

## 6. Passing Correlation IDs Through Services and Message Builders

Instead of making every class depend on `MDC.get("correlationId")`, define a command carrying the ID explicitly.

Java record example:

```java
import java.util.Locale;

public record MailRequest(
        String correlationId,
        String notificationId,
        String eventId,
        String recipient,
        String templateKey,
        String templateVersion,
        Locale locale,
        String orderNumber
) {
}
```

Creating the request:

```java
MailRequest mailRequest = new MailRequest(
        correlationId,
        UUID.randomUUID().toString(),
        orderEvent.id(),
        customer.email(),
        "order-confirmation",
        "v3",
        customer.mailLocale(),
        order.number()
);
```

Service passing the object or required ID fields:

```java
public void submit(MailRequest request) {
    log.info(
            "Mail request accepted, notificationId={}, template={}",
            request.notificationId(),
            request.templateKey()
    );

    mailQueue.publish(request);
}
```

Logs can use MDC, while `MailRequest` itself carries the IDs wherever it travels.

### Separating Business Data from Logging Metadata

`correlationId` and `notificationId` are operational metadata, whereas `recipient`, `templateKey`, `locale`, and payload are data used to render the email. Never use correlation IDs as order numbers, verification codes, user IDs, or authorization keys.

In multi-layered systems, define a dedicated type:

```java
public record MailDiagnostics(
        String correlationId,
        String notificationId,
        String eventId
) {
}
```

Then embed `MailDiagnostics` inside the command envelope. This makes propagated metadata explicit without forcing every domain entity to carry mail-transport fields.

## 7. Preserving MDC Across `@Async` Using `TaskDecorator`

When using Spring `@Async("mailExecutor")`, calls run on threads from `ThreadPoolTaskExecutor`. A common way to copy logging context is `TaskDecorator`.

Example:

```java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submittingThreadContext =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousWorkerContext =
                    MDC.getCopyOfContextMap();

            try {
                if (submittingThreadContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittingThreadContext);
                }

                task.run();
            } finally {
                if (previousWorkerContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousWorkerContext);
                }
            }
        };
    }
}
```

Executor configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setTaskDecorator(new MdcTaskDecorator());

        return executor;
    }
}
```

If the request thread holds `MDC["correlationId"]` upon submission, the decorator snapshots that map. When the job executes, the worker thread receives that context and restores its prior context in `finally`.

### Two Points to Remember

**First:** the decorator only covers tasks running through the configured executor. If a component uses `new Thread(...)`, `CompletableFuture.supplyAsync(...)` without specifying the executor, or a different executor, MDC will not propagate.

**Second:** the decorator only preserves **logging context at submission time**. It does not durably persist work, does not propagate context across brokers/networks, and has no effect if the job originates from another process.

Therefore, still keep the correlation ID inside `MailRequest` or the outbox record.

### When `@Async` Fails

`@Async` works via Spring proxies; self-invoking an async method on the same instance usually does not switch threads as expected. Exceptions from `void` async methods also do not propagate back to callers. These issues affect diagnostics; provide explicit result/exception handling.

## 8. Setting Logging Context Right at the Worker Boundary

Even with `TaskDecorator`, a worker receiving jobs from a broker or database should set MDC from IDs **inside the payload/record**.

A helper that cleanly restores prior state:

```java
import java.util.Map;
import org.slf4j.MDC;

public final class MailLogContext implements AutoCloseable {

    private final Map<String, String> previous;

    private MailLogContext(MailRequest request) {
        previous = MDC.getCopyOfContextMap();

        MDC.put("correlationId", request.correlationId());
        MDC.put("notificationId", request.notificationId());
    }

    public static MailLogContext from(MailRequest request) {
        return new MailLogContext(request);
    }

    @Override
    public void close() {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}
```

Usage:

```java
public void handle(MailRequest request) {
    try (MailLogContext ignored = MailLogContext.from(request)) {
        log.info("Processing mail request");

        String html = templateRenderer.render(request);
        log.info("Mail template rendered");

        mailGateway.submit(request, html);
        log.info("SMTP submit step completed");
    }
}
```

The `try-with-resources` block cleans up MDC even if the template renderer or SMTP gateway throws an exception.

An improvement is passing a `MailDiagnostics` record instead of the entire `MailRequest` into the helper so it has no dependency on sensitive payloads.

### Why Restore MDC Instead of Just Removing One Key?

If the worker is invoked from a context already holding `traceId`, `spanId`, or other valid metadata, removing a key or calling `MDC.clear()` indiscriminately can break the parent's context. Snapshotting the prior map and restoring it in `finally` makes nesting safe.

Conversely, if a worker sets MDC across consecutive jobs without cleanup, later jobs can mistakenly inherit old IDs.

## 9. Outbox: Storing Correlation IDs as Durable Data

For critical emails, a common design persists send requests in a **transactional outbox** within the business transaction.

```text
HTTP request
  correlationId=corr-401
        |
        v
Business transaction
  ├── Save order
  └── Insert mail_outbox
        correlationId=corr-401
        notificationId=notif-401
        status=PENDING
        |
        v
Commit
        |
        v
Outbox worker (possibly another instance)
        |
        v
SMTP attempt
```

A minimal table might look like:

```sql
CREATE TABLE mail_outbox (
    id                VARCHAR(64) PRIMARY KEY,
    correlation_id    VARCHAR(64) NOT NULL,
    event_id          VARCHAR(64),
    notification_type VARCHAR(100) NOT NULL,
    recipient_ref     VARCHAR(128) NOT NULL,
    template_key      VARCHAR(128) NOT NULL,
    payload_json      TEXT NOT NULL,
    status            VARCHAR(40) NOT NULL,
    attempt_count     INT NOT NULL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL
);
```

This is an illustrative schema. For sensitive data, consider encrypting payloads, restricting access, defining retention, and separating recipient references from raw email addresses.

When the worker starts, it reads `correlation_id` back from the record. There is no guarantee the original request's MDC still exists, since the worker may run hours later or on another machine.

### Persist Correlation IDs in the Same Transaction

If an event commits while correlation ID metadata lives only in RAM, you lose log linkage if the process stops. With an outbox, persist the IDs and send request **in the same transaction** as the business state triggering the email.

For each logical notification, use `notificationId` as the primary tracking key. Correlation IDs may be shared across multiple notifications, making them unsuitable as unique keys on outbox records.

## 10. Propagating IDs Through a Message Broker

With RabbitMQ, Kafka, or another broker, correlation IDs can travel in **message headers** or in the body envelope. A resilient pattern stores them in the versioned body; headers let middleware/logging read metadata easily.

Example JSON envelope:

```json
{
  "eventType": "MAIL_REQUESTED",
  "schemaVersion": 1,
  "correlationId": "corr-63de",
  "notificationId": "notif-918",
  "eventId": "order-event-401",
  "templateKey": "order-confirmation",
  "templateVersion": "v3",
  "recipientRef": "customer-401"
}
```

Consumer:

```java
@RabbitListener(queues = "mail.notification")
public void onMessage(MailEnvelope envelope) {
    try (MailLogContext ignored =
            MailLogContext.from(envelope.toMailRequest())) {

        mailDeliveryService.process(envelope);
    }
}
```

`MailEnvelope` and `toMailRequest()` are illustrative application models and mappings, not built-in Spring AMQP APIs.

Real applications must validate schemas, IDs, size limits, and producer authorization. Never trust a correlation ID header from an unauthenticated producer and write it straight into logs.

### Header and Body Can Diverge

If the broker header has `correlationId=A` while the body has `correlationId=B`, define a canonical source of truth. A common policy treats the validated envelope as authoritative, with headers acting only as transport/logging copies. Log the mismatch and reject or quarantine the message if necessary; never silently pick a random value.

### Retries and Dead-Letter Queues

When retrying via queues or DLQs, preserve the same `correlationId` and `notificationId`. Generate a new `attemptId` for each SMTP attempt so they stay distinguishable:

```text
corr-63de / notif-918
    ├── attempt-1 -> temporary SMTP error
    ├── attempt-2 -> connection timeout
    └── attempt-3 -> SMTP accepted
```

If requeueing generated a new correlation ID, operators could not tell that all three tries belonged to the same notification.

## 11. Trace ID and Correlation ID in Distributed Tracing

If the application uses Micrometer Tracing, OpenTelemetry, or another tracing system, logs may include `traceId` and `spanId`. These complement correlation IDs.

```text
Correlation ID: corr-63de
    |
    +-- HTTP trace A
    |     ├── controller span
    |     └── outbox insert span
    |
    +-- Worker trace B
    |     ├── template render span
    |     └── SMTP submit span
    |
    +-- Webhook trace C
          └── provider event handling span
```

For long-running workflows, the correlation ID can stay constant across distinct traces, especially when trace context is not continued across queues/outboxes.

### Propagating W3C Trace Context

Some systems pass distributed tracing over HTTP or message headers using standards like `traceparent` and `tracestate`. If instrumentation libraries support it, span context can be extracted and continued in consumers.

Do not hand-roll `traceparent` parsers/serializers when proper propagation libraries exist. Propagation must obey trace/span semantics, sampling, and trust boundaries.

**Trace context does not replace notification IDs.** When looking up an email days later from a provider webhook, original traces may have expired past retention; durable `notificationId` and `correlationId` records remain essential.

### Baggage and Sensitive Data

OpenTelemetry/Micrometer baggage can propagate metadata across systems. Never put emails, access tokens, passwords, or PII into baggage just for logging convenience; metadata may appear in headers or telemetry backends.

Even if using baggage for correlation IDs, still persist IDs into the outbox when business needs require long-term traceability.

## 12. From Renderer to `JavaMailSender`: Carrying IDs Through Sending

A clean flow passes metadata into the SMTP gateway:

```java
public record MailSubmission(
        String correlationId,
        String notificationId,
        String attemptId,
        String recipient,
        String subject,
        String plainText,
        String html
) {
}
```

Gateway:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class SmtpMailGateway {

    private final JavaMailSender mailSender;

    public SmtpMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(MailSubmission request)
            throws MessagingException {

        try (var ignored = MailLogScope.open(
                request.correlationId(),
                request.notificationId(),
                request.attemptId())) {

            MimeMessage mime = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom("notifications@example.org");
            helper.setTo(request.recipient());
            helper.setSubject(request.subject());
            helper.setText(
                    request.plainText(),
                    request.html()
            );

            log.info("SMTP submit started");

            try {
                mailSender.send(mime);
                log.info("SMTP transport accepted message");
            } catch (MailException exception) {
                log.error(
                        "SMTP submit failed, errorType={}",
                        exception.getClass().getSimpleName()
                );
                throw exception;
            }
        }
    }
}
```

`MailLogScope.open(...)` is an application-defined logging context utility, similar to `MailLogContext` above. `log` is the class logger. The snippet illustrates metadata propagation; production code must separately handle `MessagingException` during MIME construction and persist attempt outcomes in storage.

The key point is that the gateway **receives IDs through `MailSubmission`**, rather than trying to guess correlation IDs from email addresses, subjects, or `Message-ID`s after sending.

### Logging by Stage

Useful events:

```text
MAIL_REQUEST_ACCEPTED
MAIL_TEMPLATE_RENDERED
MAIL_ATTEMPT_STARTED
MAIL_SMTP_ACCEPTED
MAIL_ATTEMPT_FAILED
MAIL_RETRY_SCHEDULED
MAIL_PROVIDER_DELIVERED
MAIL_PROVIDER_BOUNCED
```

Each log should carry correlation ID, notification ID, and attempt ID when available. When handling provider events, the provider message ID may also be needed.

## 13. Should Correlation ID Be Added to Email Headers?

Jakarta Mail lets you add custom headers:

```java
mimeMessage.setHeader(
        "X-Application-Correlation-ID",
        correlationId
);
```

This is occasionally useful when inspecting raw emails or if an SMTP provider preserves the header for search. However, understand its limits:

- **Headers can be read by recipients**; they are not secret metadata.
- Some providers or mail gateways strip, alter, or omit custom headers from webhooks.
- Headers do not guarantee deduplication by receivers/providers.
- Values must be validated to exclude CR/LF and personal data.
- Add only when there is an approved diagnostic purpose.

In many applications, keeping the correlation ID **in the database and logs** suffices; there is no need to embed it in the email itself.

### Correlation ID Is Not `Message-ID`

Do not use custom headers as substitutes for `Message-ID`, `In-Reply-To`, or `References`. Those headers have specific rules and roles in email standards.

If the application needs to track `Message-ID` for diagnostics, record the actual value from the prepared/sent message, recognizing providers may assign additional internal IDs. Do not assume every provider preserves IDs uniformly.

## 14. Recording SMTP Attempts and Uncertain Outcomes

Each call to `JavaMailSender.send(...)` needs an attempt ID to distinguish retries.

Record example:

```json
{
  "correlationId": "corr-63de",
  "notificationId": "notif-918",
  "attemptId": "attempt-918-02",
  "smtpRoute": "primary",
  "status": "SMTP_SUBMISSION_FAILED",
  "errorClass": "MailSendException",
  "smtpReplyCode": null
}
```

If `send` returns normally, you can record `SMTP_ACCEPTED` or `ACCEPTED_BY_SMTP` per system contract. **Never record `DELIVERED`** unless appropriate provider/recipient delivery evidence exists.

### Timeouts Can Be Indeterminate Outcomes

Scenario:

1. Worker sends full email content.
2. SMTP server accepts the message.
3. Connection drops before the client receives the final reply.
4. `JavaMailSender` throws an exception or timeout.
5. Worker does not know for sure whether the server received the message.

Here, separate `UNKNOWN` from definite failures. On retry, a duplicate email may be sent. Correlation IDs link attempts and aid investigation; **they do not provide exactly-once delivery**.

### Do Not Change Correlation ID on Retry

Keep:

```text
correlationId = corr-63de
notificationId = notif-918
```

And change:

```text
attemptId = attempt-918-01
attemptId = attempt-918-02
attemptId = attempt-918-03
```

If retried via a manual operator action, add `retryTriggeredBy` or `recoveryOperationId` to show the trigger source without losing the original workflow's correlation ID.

## 15. Correlating with Provider Message IDs and Webhooks

After SMTP accepts an email, a provider may assign its own ID. Subsequent events such as delivery, bounce, deferred, or complaint may arrive via webhooks, APIs, or event streams.

```text
Application mail request
  correlationId=corr-63de
  notificationId=notif-918
        |
        v
SMTP/API submission
        |
        v
providerMessageId=provider-7af1
        |
        v
Provider webhook (later)
  providerMessageId=provider-7af1
  event=DELIVERED
        |
        v
Lookup notificationId
        |
        v
Update delivery state
  correlationId=corr-63de
```

A minimal mapping table:

| Field | Purpose |
|---|---|
| `notification_id` | Internal key of the logical notification. |
| `correlation_id` | Links to original business flow and logs. |
| `attempt_id` | Which submit attempt generated the provider ID. |
| `provider_message_id` | Lookup key for events from the provider. |
| `mime_message_id` | `Message-ID` header if available and needed. |
| `provider_event_id` | Helps deduplicate webhooks when supplied by provider. |
| `delivery_status` | Post-submission status. |

### Not Every Webhook Returns Custom Headers

Some providers support passing custom metadata on API sends; others return only a provider message ID or event ID. Over SMTP, there may be no reliable metadata tagging equivalent to HTTP APIs.

Build webhook correlation around **actual provider capabilities**. You may need provider message IDs, email `Message-ID`s, supported custom metadata, or a mapping table populated at send time. Never assume setting `X-Correlation-ID` guarantees every webhook echoes it back.

### Webhooks Require Authentication and Replay Protection

Correlation IDs do not authenticate event sources. Webhooks must verify signatures, tokens, or authentication mechanisms published by the provider. Events can be delivered multiple times; use provider event IDs or appropriate deduplication keys.

Never let a webhook update arbitrary notifications solely by correlation ID, because one correlation ID can span multiple emails.

## 16. Querying Logs Starting from a `MailException`

A diagnostic flow may start with a log entry:

```text
timestamp=2026-11-12T09:20:11Z
event=MAIL_ATTEMPT_FAILED
correlationId=corr-63de
notificationId=notif-918
attemptId=attempt-918-02
errorType=MailAuthenticationException
smtpRoute=primary
```

Query in order:

1. **Attempt ID**: pinpoint the send try and specific failure details.
2. **Notification ID**: inspect prior attempts, outbox state, and retry decisions.
3. **Correlation ID**: locate the business event creating the email, related requests/events, and renderer/queue logs.
4. **Provider message ID**, if present: cross-check provider dashboards and delivery webhooks.

Questions to answer:

- When was the job created?
- Who/what emitted the event?
- Which template/version/locale was used?
- Which attempt ran first?
- Did the error happen before or after SMTP could have accepted the message?
- Are there other jobs sharing the same correlation ID?
- Did retries create duplicates?
- Did any delivery/bounce webhooks arrive later?

During a prolonged SMTP authentication outage, many correlation IDs may fail together on one mail route. Add **`route`/`provider` IDs** to spot systemic outages rather than investigating emails one by one.

## 17. Structured Logging and Field Naming Conventions

Standardize field names across services:

```text
correlationId
requestId
traceId
spanId
eventId
notificationId
attemptId
providerMessageId
smtpRoute
notificationType
templateKey
templateVersion
status
errorType
```

If each service uses different names like `corr_id`, `requestCorrelation`, and `mailFlowId`, dashboards and log queries get messy. You may normalize to snake_case at log ingestion, provided the schema is published and kept stable.

### Illustrative Structured Log

```json
{
  "event": "MAIL_SMTP_ACCEPTED",
  "correlationId": "corr-63de",
  "notificationId": "notif-918",
  "attemptId": "attempt-918-03",
  "smtpRoute": "primary",
  "durationMs": 842,
  "templateKey": "order-confirmation",
  "templateVersion": "v3"
}
```

No need to log full subjects or real recipients to correlate events. Store internal recipient references/aliases or controlled domains per privacy policy.

### Do Not Use Correlation IDs as Metric Labels

Correlation IDs have very high cardinality since nearly every request has a distinct value. Never put them into Prometheus/Micrometer timer or counter labels/tags:

```text
# Unsuitable due to very high cardinality:
mail_send_total{correlationId="corr-63de"}

# Better:
mail_send_total{smtpRoute="primary",result="accepted"}
```

Correlation IDs belong in **logs, traces, or queryable records**, not metric labels. Metrics use low-cardinality dimensions such as route, outcome, notification kind, or grouped error class.

## 18. Security and Privacy of Correlation IDs

A correlation ID looks like a mere technical string, yet can be used to query logs or trace user activity. Therefore:

- Never embed emails, phone numbers, access tokens, or personal data in IDs.
- Reject arbitrarily long values or control characters.
- Never use correlation IDs to authorize access to a mail record.
- Never place them in password reset links as secret tokens.
- Restrict access to log queries and dashboards.
- Enforce retention policies on logs and delivery records.
- Mask recipients, bodies, attachments, and tokens when logging errors.
- If placed in responses/email headers, treat them as potentially exposed metadata.

Pattern to avoid:

```text
correlationId = "user-email@example.org-2026-11-12"
```

Better example:

```text
correlationId = "e241cb19-8cfa-4bb0-b254-b94fefefc719"
```

If you need to link IDs to users, store mappings in an access-controlled database rather than encoding PII directly into IDs.

## 19. Common Mistakes That Lose Correlation IDs

| Symptom | Likely cause | Handling direction |
|---|---|---|
| Controller has ID, `@Async` lacks it | MDC relies on thread-locals | Pass ID in commands and use `TaskDecorator` if needed. |
| Worker logs previous email's ID | MDC not cleared/restored in thread pool | Use `try/finally` or `AutoCloseable` scope. |
| Queue consumer logs `correlationId=missing` | Publisher did not serialize metadata | Include correlation ID in a well-defined envelope/header schema. |
| Retries appear as brand-new emails | Generating new notification/correlation ID per attempt | Keep logical IDs; generate new attempt IDs. |
| Hard to tell multiple emails sharing a correlation ID apart | Using only correlation ID without notification ID | Generate a distinct notification ID per logical email. |
| Webhook cannot be linked back to email | Provider ID not saved or no mapping | Persist `providerMessageId` → `notificationId` mapping. |
| SMTP log has `Message-ID` yet request log lacks it | Confusing `Message-ID` with correlation ID | Store both and link via notification record. |
| Job logs have ID yet trace is broken | Trace context not propagated | Configure appropriate instrumentation/propagation. |
| Logs contain huge correlation ID values | Trusting unvalidated headers | Validate format and length at ingress. |
| Metric backend blows up with series | Using correlation ID as a metric tag | Move IDs to logs/traces. |
| Webhook has right ID yet updates wrong email | Using correlation ID to pick a single notification | Use specific notification/provider ID and verify webhooks. |
| ID lost after restart | ID lived only in RAM/MDC | Persist in durable outbox or queue envelopes. |

## 20. Testing End-to-End Propagation

Test **ID preservation**, not merely whether some single log line prints an ID.

### 20.1. Testing the HTTP Filter

Scenarios:

- Request with valid ID preserves it per policy.
- Request without ID generates a UUID.
- ID with newlines, whitespace, or excessive length is rejected and replaced with an internal ID.
- Response header and request attribute hold the same ID.
- After the request, MDC is restored to avoid polluting threads.

Conceptual example with MockMvc:

```java
mockMvc.perform(
        get("/orders/ORD-401")
            .header("X-Correlation-ID", "corr-test-401")
    )
    .andExpect(
        header().string("X-Correlation-ID", "corr-test-401")
    );
```

The example assumes matching endpoints and security/filter chains exist in the app. Also assert that commands created from the request carry the exact correlation ID.

### 20.2. Testing `@Async` and `TaskDecorator`

A test can:

1. Set `MDC["correlationId"] = "corr-A"` on the submitting thread.
2. Submit a task via `mailExecutor` and wait for `CompletableFuture` completion.
3. Inside the task, assert MDC equals `corr-A`.
4. Submit another task with `corr-B`.
5. Assert the second task does not see `corr-A`.
6. Assert MDC on both submitting and worker threads is clean afterwards.

Using `CountDownLatch` or `CompletableFuture` gives deterministic synchronization without arbitrary `Thread.sleep(...)`.

### 20.3. Testing Outbox and Queue Serialization

Create a `MailRequest` with:

```text
correlationId = corr-order-401
notificationId = notif-order-401
```

Serialize, persist/publish, then deserialize/read in the worker. Verify both IDs survive intact. This is a critical test because the request thread's MDC will not exist on the worker.

### 20.4. Testing SMTP Failures and Retries

Using a mocked `JavaMailSender` or fault-injecting SMTP test server:

- Attempt 1 fails: record carries correlation ID and first attempt ID.
- Attempt 2 succeeds: correlation ID and notification ID remain unchanged; attempt ID is new.
- Error logs contain no credentials or raw MIME.
- Job is not lost just because the worker threw `MailException`.

### 20.5. Testing Provider Webhooks

Using simulated webhook payloads authenticated per provider mechanism:

1. Create mapping between provider message ID and notification ID.
2. Receive delivery/bounce event.
3. Look up the right notification record.
4. Record state with the original correlation ID.
5. Replay the same webhook event to verify deduplication.

This tests the mapping and delivery layer, not a claim that all providers share the same webhook schema.

## 21. Rollout Strategy in an Existing Running System

If a legacy application lacks complete correlation IDs, you do not need to change every service at once.

Step-by-step rollout:

1. **Ingress:** standardize on the name `correlationId`; generate and validate IDs at HTTP/event entry points.
2. **Mail command:** add IDs to the send-request envelope alongside `notificationId`.
3. **Outbox schema:** persist IDs while maintaining backward compatibility for older jobs.
4. **Worker:** populate MDC from payload/record metadata.
5. **SMTP adapter:** log start/success/error with correlation ID and attempt ID.
6. **Provider integration:** store provider message IDs and map webhooks back to notifications.
7. **Dashboards/log queries:** update queries, alerts, and operational runbooks.
8. **Cleanup compatibility:** once old jobs drain, tighten invariants so correlation ID cannot be blank.

### Handling Legacy Jobs Missing Correlation IDs

If old outbox records lack IDs, you can generate a **legacy correlation ID** per job/event group when reading, while recording that it was backfilled rather than the original request's correlation ID.

Never claim linkage back to an original HTTP request if that data does not exist. You may use `eventId` or `orderId` to reconstruct relationships when sufficient evidence exists, without guessing arbitrarily.

## 22. Design and Operations Checklist

| Question | Expectation |
|---|---|
| Is there a policy to generate/accept correlation IDs at entry points? | Yes. |
| Are external headers validated or replaced with internal IDs? | Yes. |
| Does the same workflow keep its correlation ID across services/threads? | Yes. |
| Does each logical email have its own notification ID? | Yes. |
| Does each retry have a new attempt ID while keeping logical IDs? | Yes. |
| Does `@Async` propagate/clean up MDC? | Yes, if logs rely on MDC. |
| Do brokers/outboxes persist IDs as durable data? | Yes, for critical async mail. |
| Does the SMTP adapter log accurate `SMTP_ACCEPTED`/failure states? | Yes. |
| Is there a provider ID to notification ID mapping? | Yes, if delivery events must be correlated. |
| Are webhooks authenticated and deduplicated? | Yes. |
| Are correlation IDs kept out of secrets and authorization? | Yes. |
| Are correlation IDs kept out of high-cardinality metric labels? | Yes. |
| Is request → queue → worker → SMTP → webhook tested? | Yes. |
| Are logs queryable by `correlationId`/`notificationId`/`attemptId`? | Yes. |

## 23. Key Takeaways

- **Correlation ID** links steps belonging to the same business flow; **notification ID** identifies one logical email; **attempt ID** distinguishes send tries.
- Correlation ID is not HTTP request ID, distributed trace ID, SMTP `Message-ID`, or provider message ID.
- Generate or validate IDs at entry points and **pass them as explicit data** through services, events, queues, and outboxes.
- MDC is only per-thread logging context; never rely on MDC as the sole data source for asynchronous emails.
- With `@Async`, `TaskDecorator` can copy and restore MDC, yet IDs must still live inside mail commands.
- Consumers/workers should set MDC from received records and clean up in `finally` or `AutoCloseable`.
- Queues/outboxes must preserve correlation IDs across process restarts and job retries.
- Log the right stages: render, submit, SMTP accepted, failure, retry, and provider delivery/bounce; never equate SMTP accepted with delivered.
- Correlate webhooks via provider message IDs or provider-supported metadata; do not assume custom mail headers always return in webhooks.
- Never use correlation IDs as secrets, sole idempotency keys, or high-cardinality metric labels.
- Test propagation, cleanup, retries, and provider event mapping—not just a single log line.

Preserving correlation IDs across the entire email pipeline lets systems answer accurately **which email, where it originated, which attempts it went through, and where it stopped**. The foundation of this design is not a logging trick, but **stable metadata persisted and passed across every boundary**, paired with MDC/tracing for diagnostics and delivery records to reconcile actual outcomes.

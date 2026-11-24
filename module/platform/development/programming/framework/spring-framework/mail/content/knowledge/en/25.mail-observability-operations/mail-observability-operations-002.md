# Measuring Message Build Duration and SMTP Wait Time

In a Spring Framework Mail application, an email send request can be slow for many reasons: rendering an HTML template takes too long, a PDF file has not finished generating, an attachment is read from slow storage, a worker waits in a queue, TCP/TLS connections must be re-established, SMTP AUTH takes extra round-trips, or the mail server responds slowly. If you place only a single clock around the entire business operation, operators cannot tell which segment to optimize.

**Measuring message build duration and SMTP wait time** means dividing the send flow into clearly bounded measurement intervals, attaching success/failure outcomes, and observing them through logs, metrics, or traces.

Two foundational measurements:

1. **Message preparation/build duration:** from when the application begins constructing the email content until the defined preparation scope is complete—for example, rendering templates, resolving recipients, creating the MimeMessage, and configuring MIME parts.
2. **SMTP submit-call duration:** from immediately before calling **JavaMailSender.send(...)** until that synchronous call returns or throws an exception.

**Do not equate submit-call duration with SMTP server processing time.** A send call can include lazy attachment reads, MIME serialization, DNS, TCP connect, TLS, AUTH, DATA transfer, and waiting for the response. JavaMailSender does not automatically return a breakdown for each phase.

When the system uses **@Async**, **@TransactionalEventListener(AFTER_COMMIT)**, or a **transactional outbox**, you must also measure how long tasks wait in the queue and the duration from business commit until the SMTP relay accepts the message. These are completely different intervals from the duration inside a single send call.

## 1. Breaking down the entire email send flow

A typical application flow:

~~~text
Business transaction
        |
        v
COMMIT + create outbox event
        |
        |---- Queue waiting ----|
        v                       |
Worker claims event            |
        |
        +-- Load snapshot and template
        +-- Render subject/plain text/HTML
        +-- Validate data and resolve resources
        +-- Build MimeMessage
        |
        |---- Build duration ---|
        v                       |
JavaMailSender.send(...)
        |
        +-- Deferred resource reading / MIME serialization
        +-- DNS / TCP connect when required
        +-- STARTTLS or implicit TLS handshake
        +-- SMTP AUTH
        +-- MAIL FROM / RCPT TO
        +-- DATA transfer / final response
        |
        |---- Send-call duration ----|
        v                            |
Success returned or exception        |
        |
        +-- Later delivery / bounce / mailbox processing
~~~

Not every system has an outbox. When sending synchronously inside an HTTP request, the queue stage may not exist. Yet the distinction between **build**, **send call**, **SMTP acceptance**, and **delivery** remains critical.

### 1.1. Metric boundary table

| Suggested Metric | Start | End | Meaning |
| --- | --- | --- | --- |
| **mail.template.render.duration** | Start template rendering | Renderer finishes text/HTML | Rendering cost |
| **mail.message.build.duration** | Start preparing message | Message object built per contract | Application-layer preparation cost |
| **mail.smtp.submit.call.duration** | Before send(...) | send(...) returns/throws | Synchronous latency observed by caller |
| **mail.outbox.queue.delay** | Event enqueued/committed | Worker starts processing | Time spent waiting to be processed |
| **mail.attempt.processing.duration** | Worker begins an attempt | Attempt finishes | Total time of a single processing attempt |
| **mail.event.to.relay.acceptance** | Business event persisted | Relay accepts via SMTP | End-to-end latency to relay |
| **mail.outbox.pending.count** | Queue state snapshot | — | Backlog |
| **mail.delivery.attempts** | Each attempt | Increment by 1 | Attempt count |

Metric names are design examples; not all of them exist out of the box when adding Spring Boot Actuator.

### 1.2. Do not confuse with delivery latency

A `JavaMailSender.send` call returning normally usually means the transport completed according to the relay's SMTP response. It **does not prove the message entered the inbox, bypassed spam filters, or was read by the recipient**.

When measuring end-to-end latency, explicitly label the milestone **relay acceptance**, not generically “delivered” unless actual delivery data is available.

## 2. Use the right clock for each measurement type

There are two types of time measurements:

- **Elapsed duration within the same process:** use **System.nanoTime()** or a Micrometer Timer's monotonic clock.
- **Timestamps for reconciliation across queues or processes:** use wall-clock instants such as **Instant** or database-generated timestamps, and account for clock skew across hosts.

### 2.1. Why System.nanoTime is appropriate

Example:

~~~java
long started = System.nanoTime();

try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    long elapsedMillis =
            java.util.concurrent.TimeUnit.NANOSECONDS
                    .toMillis(elapsedNanos);

    log.info("operation.durationMs={}", elapsedMillis);
}
~~~

**System.nanoTime()** is designed for measuring elapsed intervals, not for representing a calendar date/time. Its absolute value must never be stored as an event timestamp to compare across two machines.

### 2.2. Why not use System.currentTimeMillis() for timers?

Wall-clock time can be adjusted by the OS or NTP synchronization. Subtracting wall-clock timestamps can then deviate from actual elapsed time, or even go negative in some cases. Millisecond resolution is also suboptimal for measuring short phases.

Use nanoTime for method durations; use Instant for `createdAt`, `claimedAt`, and `acceptedAt` in an outbox.

### 2.3. Never subtract nanoTime across different processes

A worker cannot take a `System.nanoTime` saved by another service and subtract its own `System.nanoTime`. The two values share no common reference origin. Queue delay must rely on timestamps with a consistent clock policy and account for clock skew.

## 3. Why measure both successes and failures?

Incomplete code pattern:

~~~java
mailSender.send(message);
recordDuration(System.nanoTime() - started);
~~~

If `send` throws a `MailException`, `recordDuration` never runs. The longest timeouts vanish from dashboards, making latency look better than reality.

Place duration recording inside **finally**:

~~~java
long started = System.nanoTime();
String outcome = "success";

try {
    mailSender.send(message);
} catch (RuntimeException ex) {
    outcome = "failure";
    throw ex;
} finally {
    long duration = System.nanoTime() - started;
    metrics.recordSubmit(duration, outcome);
}
~~~

In this example, **metrics.recordSubmit(...)** is an application-defined method, not a built-in `JavaMailSender` method.

### 3.1. Record outcomes with accurate semantics

- **success:** the `send` call returned normally.
- **failure:** the `send` call threw an exception.
- **unknown outcome:** a separate business state when it is uncertain whether the relay accepted the message, such as losing the response after `DATA`.

An exception alone does not automatically prove the email was definitely not sent.

### 3.2. Do not catch Exception and retry immediately

Instrumentation must preserve exception semantics. AUTH errors, recipient rejections, message preparation errors, and timeouts require distinct retry policies. A timer only observes; it must not turn every error into a retryable one.

## 4. What steps does message build include?

In a system sending HTML emails, building a message may include:

1. Reading the required DTO snapshot.
2. Selecting the locale and template.
3. Rendering Subject, `text/plain`, and `text/html`.
4. Formatting currency amounts and dates.
5. Creating the `MimeMessage` via `JavaMailSender`.
6. Creating a `MimeMessageHelper`.
7. Setting From, Reply-To, To, CC/BCC, and Subject.
8. Setting the body.
9. Building the multipart structure.
10. Adding inline image/attachment references.
11. Completing preparation according to the service contract.

These steps do not all have to live inside a single factory. What matters is keeping measurement boundaries consistent.

### 4.1. If template rendering sits outside the timer

Suppose:

~~~java
String html = templateRenderer.render(data);

long started = System.nanoTime();
MimeMessage message = buildMime(html);
long buildNanos = System.nanoTime() - started;
~~~

The timer only measures `buildMime`, **excluding rendering**. If a dashboard labels this “message preparation duration”, document that clearly or expand the timer to cover rendering as well.

### 4.2. Use sub-metrics when hunting bottlenecks

You can create:

~~~text
mail.template.render.duration
mail.attachment.generate.duration
mail.resource.load.duration
mail.message.build.duration
mail.smtp.submit.call.duration
~~~

Avoid creating an unbounded number of metrics. Start with build and send; add sub-step metrics only when you need to isolate major cost centers.

### 4.3. Do not hold a database transaction open while waiting on SMTP

If `send` is called inside a **@Transactional** method, SMTP duration can turn into database connection/lock hold time. Separate data transactions from sending so network latency does not degrade transaction performance.

## 5. Example measuring build and send with System.nanoTime

An illustrative service:

~~~java
public void sendOrderMail(OrderMailData data) {
    long buildStarted = System.nanoTime();

    MimeMessage message;
    try {
        message = buildMessage(data);
    } finally {
        recordBuildNanos(
                System.nanoTime() - buildStarted
        );
    }

    long submitStarted = System.nanoTime();

    try {
        mailSender.send(message);
    } finally {
        recordSubmitNanos(
                System.nanoTime() - submitStarted
        );
    }
}
~~~

**buildMessage**, **recordBuildNanos**, and **recordSubmitNanos** are example application methods. This code clarifies where timers start and stop.

If `build` throws an exception, the `submit` block does not run. That is right: message preparation failures must not be counted as an SMTP send attempt.

### 5.1. Example output

~~~text
mail.message.build.duration = 14 ms
mail.smtp.submit.call.duration = 780 ms
~~~

You can conclude that building the object took 14 ms and the send call took 780 ms.

**You cannot conclude that all 780 ms was server processing.** It can include connection setup, handshake, auth, MIME serialization, and network transfer.

## 6. Micrometer Timer is the right choice for metrics

**Micrometer Timer** records duration, count, and other statistics depending on the registry and configuration. It can be exported to backends such as Prometheus for latency distribution analysis.

In a Spring Boot application, Actuator/Micrometer is typically used:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

If using Prometheus, the application also needs the corresponding registry/exporter. The dependency snippet is illustrative and does not require a specific version.

**Do not assume JavaMailSender automatically emits separate metrics for build and send across the two scopes in this lesson.** You need to instrument the application or have appropriate instrumentation configured.

### 6.1. Timer.Sample

A pattern:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    performOperation();
} finally {
    sample.stop(
            registry.timer(
                    "mail.operation.duration",
                    "outcome",
                    "completed"
            )
    );
}
~~~

This is a simple measurement mechanism, though in a real application you should set the `outcome` tag to reflect success/failure as shown in the next example.

### 6.2. Why prefer a Timer over logging every millisecond?

A Timer aggregates executions, supports histograms/percentiles, and enables time-series alerting. Per-message logs remain useful for investigating specific events, but should not be the sole source for determining p95/p99.

## 7. Spring service measuring build and SMTP submit-call

Illustrative DTO:

~~~java
public record OrderMailData(
        String recipient,
        String orderNumber,
        String messageText
) {}
~~~

Service:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class TimedOrderMailService {

    private final JavaMailSender sender;
    private final MeterRegistry registry;

    public TimedOrderMailService(
            JavaMailSender sender,
            MeterRegistry registry
    ) {
        this.sender = sender;
        this.registry = registry;
    }

    public void sendConfirmation(OrderMailData data) {
        MimeMessage message = buildTimed(data);
        submitTimed(message);
    }

    private MimeMessage buildTimed(OrderMailData data) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            MimeMessage message = sender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            false,
                            "UTF-8"
                    );

            helper.setFrom("orders@example.org");
            helper.setTo(data.recipient());
            helper.setSubject(
                    "Order confirmation " + data.orderNumber()
            );
            helper.setText(data.messageText(), false);

            return message;
        } catch (MessagingException ex) {
            outcome = "failure";
            throw new MailPreparationException(
                    "Cannot prepare confirmation",
                    ex
            );
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.message.build.duration",
                            "kind", "order_confirmation",
                            "outcome", outcome
                    )
            );
        }
    }

    private void submitTimed(MimeMessage message) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (MailException ex) {
            outcome = "failure";
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "kind", "order_confirmation",
                            "outcome", outcome
                    )
            );
        }
    }
}
~~~

### 7.1. Boundaries of this code

- Build starts before `createMimeMessage` and finishes once fields are set.
- If build fails, `send` is not called.
- The send timer starts before `JavaMailSender.send` and stops when it returns or throws.
- Both timers use **kind** and **outcome** tags with finite value sets.
- Never put recipient, subject, body, or password into metric tags.

### 7.2. Do not treat this as the entire pipeline

This example receives an already-prepared DTO and does not render templates or attach files. If a real service queries a database, generates a PDF, or renders HTML, decide whether to include that work in the build metric or place a separate sub-metric.

### 7.3. Invalid data must be handled properly

The code reads the recipient from the DTO. In a real application, validate addresses and sending permissions per contract. Instrumentation does not replace validation or data security policies.

### 7.4. Timer success/failure alone is not enough for retry logic

`MailException` outcomes must be classified by root cause so the outbox can decide among `RETRY_WAIT`, `INVALID_RECIPIENT`, `PAUSED_CONFIG`, or `UNKNOWN_OUTCOME`. Metrics only provide aggregate signals.

## 8. Attachments and lazy MIME serialization

A critical point: **time to build the MimeMessage object does not necessarily include time to read the entire attachment**.

Example:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoiceFile),
        "application/pdf"
);
~~~

Depending on the overload and how Jakarta Mail uses `DataSource`, `addAttachment` may only attach a `Resource` reference. The actual bytes may only be read when the message is serialized inside `send`.

Result:

~~~text
Build object duration:  9 ms
Send call duration:   1800 ms
~~~

Send-call duration can be high because of file I/O or MIME encoding, rather than slow SMTP server performance.

### 8.1. Distinguish object build from message materialization

- **Object build:** creating the `MimeMessage`/`MimeMessageHelper` and configuring the MIME structure.
- **Materialization:** producing the MIME bytes to transmit; this may require opening streams, reading files, and encoding attachments.

If you want to measure materialization, place instrumentation around the serialization stage. Do not label an object-build timer as “full attachment read time” when it has not read the bytes yet.

### 8.2. Pre-reading into ByteArrayResource

If the application pre-reads the attachment:

~~~java
byte[] invoiceBytes =
        attachmentLoader.loadWithLimit(invoiceId);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoiceBytes),
        "application/pdf"
);
~~~

File read time falls under build/preparation if the timer covers `loadWithLimit`. Creating a `byte[]` from a file still consumes time and memory; it does not magically reduce total latency, it only shifts which stage reports the cost.

### 8.3. Do not serialize twice just for prettier metrics

In tests, you may call **message.writeTo(...)** to verify MIME output. In production, however, serializing to a `ByteArrayOutputStream` beforehand and letting `JavaMailSender` serialize again can double CPU/I/O and increase memory usage, especially with large attachments.

Optimize for real performance; never degrade application efficiency just to measure a metric.

### 8.4. Message size metrics

If comparison is needed, categorize by **size_class=small/medium/large** using sensible thresholds. Never turn every exact byte count or attachment filename into its own metric tag.

## 9. What does a JavaMailSender.send call do?

Conceptually:

~~~text
JavaMailSender.send
      |
      +-- Prepare/serialize deferred MIME data
      +-- Resolve SMTP host / TCP connection
      +-- TLS: implicit TLS or STARTTLS
      +-- SMTP AUTH if required
      +-- MAIL FROM / RCPT TO
      +-- DATA serialization and transfer
      +-- Wait for SMTP response
      |
      v
Return normally or throw
~~~

Exact steps vary by implementation, session configuration, batching, and transport. With connection reuse, connection/handshake cost for a subsequent message differs from the first send.

### 9.1. DNS and TCP connect

Send duration can spike due to DNS lookup or blocked connections. The server may not have received any SMTP commands yet.

### 9.2. TLS handshake

STARTTLS or implicit TLS requires protocol/cipher negotiation and certificate verification. If a certificate is invalid, `send` can fail with `MessagingException`/`SSLHandshakeException`.

### 9.3. SMTP AUTH

Providers may require authentication, adding round-trips. Failed AUTH must be distinguished from a slow server response.

### 9.4. MAIL FROM and RCPT TO

Multiple recipients can increase command exchange time or cause partial recipient failures. Do not treat a whole-message outcome as the outcome for every individual recipient when the API throws an exception.

### 9.5. DATA

Body and attachments are serialized and transmitted over the network, after which the client waits for the final server response. Large payloads and low bandwidth can make this step dominate total time.

### 9.6. Relay acceptance does not equal delivery

`JavaMailSender` returning normally indicates transport completion according to the SMTP response. It does not prove the provider delivered the message to the mailbox or that the recipient opened it.

## 10. Distinguishing client call time from server processing

We can approximate:

~~~text
T_submit_call
  = T_client_overhead
  + T_connect_when_needed
  + T_tls_and_auth
  + T_smtp_commands
  + T_mime_serialization
  + T_network_transfer
  + T_response_wait
~~~

This is a conceptual decomposition. `JavaMailSender` does not return individual component timings through its `send` API.

**You cannot use a single timer around `send` to deduce exactly how many milliseconds the SMTP server spent processing `DATA`.**

Measuring deeper may require:

- Telemetry published by the SMTP provider.
- Instrumentation inside a transport or SMTP proxy under your control.
- Dedicated connection/TLS/network tracing.
- An SMTP test server that injects delays per phase.
- Controlled protocol log analysis, only when necessary and after assessing PII/secret risks.

### 10.1. Do not enable SMTP debug by default just for timing

Jakarta Mail protocol debug can print addresses, commands, and metadata. It does not necessarily provide standardized timestamps or phase durations for metric aggregation. Prefer Timers/Observations in production.

### 10.2. Metric names should reflect what is actually measured

Good name:

~~~text
mail.smtp.submit.call.duration
~~~

Misleading name:

~~~text
smtp.server.processing.duration
~~~

if it only wraps `JavaMailSender.send` from the outside.

## 11. MimeMessagePreparator has a special boundary

Spring supports:

~~~java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(
                    mimeMessage,
                    false,
                    "UTF-8"
            );

    helper.setFrom("news@example.org");
    helper.setTo("an@example.net");
    helper.setSubject("Notification");
    helper.setText("Content", false);
});
~~~

In the **send(MimeMessagePreparator)** API, the message-building callback executes inside the `send` call. If you place a timer around the outside of this call, it includes **both the preparation callback and transport**.

### 11.1. Measure the callback with a separate Timer

~~~java
mailSender.send(mime -> {
    Timer.Sample buildSample = Timer.start(registry);
    String outcome = "success";

    try {
        MimeMessageHelper helper =
                new MimeMessageHelper(
                        mime,
                        false,
                        "UTF-8"
                );

        helper.setFrom("news@example.org");
        helper.setTo("an@example.net");
        helper.setSubject("Notification");
        helper.setText("Content", false);
    } catch (MessagingException ex) {
        outcome = "failure";
        throw ex;
    } catch (RuntimeException ex) {
        outcome = "failure";
        throw ex;
    } finally {
        buildSample.stop(
                registry.timer(
                        "mail.message.build.duration",
                        "kind", "notification",
                        "outcome", outcome
                )
        );
    }
});
~~~

If you also wrap the outside of `send(preparator)`, **the two scopes overlap**. Never sum those two durations as if they were independent.

### 11.2. Can you subtract callback duration from total?

`total - callback` can serve as a rough reference, but it still includes client-side and network overhead. **It does not mean server processing equals that difference.**

### 11.3. If you want two clean scopes

Build the `MimeMessage` first, time the build, and then call **send(MimeMessage)** and time the send. Still keep lazy resource serialization in mind.

## 12. SimpleMailMessage has different measurement characteristics

For plain text mail:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notifications@example.org");
message.setTo("an@example.net");
message.setSubject("Notification");
message.setText("Content");

mailSender.send(message);
~~~

Building a `SimpleMailMessage` is just creating an object and storing strings; `JavaMailSenderImpl` may convert it into a `MimeMessage` during send, so send-call duration can include that internal conversion work.

Do not directly compare the build latency of a **small SimpleMailMessage** against a **MimeMessage with a large PDF** without categorizing by message type or size.

## 13. Measuring queue delay in a transactional outbox

A reliable mail system can write an outbox event in the same business transaction and let a worker process it later.

Example timeline:

~~~text
10:00:00  Business transaction commits
10:00:45  Worker claims outbox event
10:00:46  Message preparation completed
10:00:48  SMTP relay accepted message
~~~

Intervals measured:

- Queue delay: roughly 45 seconds.
- Build/processing: from when the worker starts until the message is ready.
- Send-call: the `JavaMailSender.send` phase.
- Event-to-relay: roughly 48 seconds.

### 13.1. Queue delay and SMTP latency are two different things

A message sitting in the outbox for 5 minutes whose send finishes in 250 ms is not “5-minute slow SMTP”. The bottleneck could be worker scheduling, thread pools, leases, database queries, or retry backoff.

### 13.2. Illustrative timestamp schema

~~~text
eventId
createdAt
firstClaimedAt
availableAt
attemptStartedAt
attemptFinishedAt
relayAcceptedAt
status
attempts
~~~

Keep timestamps consistent across workers and the database, and monitor clock skew if multiple hosts use different time sources.

### 13.3. Separate retry backoff from scheduler lag

- **Initial queue delay:** from event creation to first claim.
- **Retry wait:** intentional delay until `nextAttemptAt`.
- **Scheduler lag:** task has reached its eligible time, but no worker has claimed it yet.
- **Attempt processing:** execution time of a single attempt.

If you lump all of these into queue latency, operators might scale up workers to fix an intentional backoff delay.

## 14. Measuring end-to-end from business commit to relay accept

From a user-experience perspective, the key metric may be:

~~~text
T_to_relay_accept
  = relayAcceptedAt - businessCommittedAt
~~~

It encompasses queuing, scheduling, rendering, building, sending, and retries, depending on the actual timeline.

### 14.1. Make the commit point clear

If outbox `createdAt` is recorded **before commit** inside the transaction, it can be slightly earlier than the true commit time. Pick a consistent definition and document that difference on dashboards.

### 14.2. Never sum overlapping durations

If a Timer wraps the entire worker attempt that already includes render/build/send, do not add it on top of individual render/build/send Timers and call the sum end-to-end. Only add non-overlapping segments.

### 14.3. Do not force a success duration on FAILED events

A task never accepted by the relay has no `relayAcceptedAt`. Track **time-to-terminal-failure** and **count failed** separately if failure-handling SLAs are needed.

## 15. @Async: measure inside the worker, not just at the caller

Example:

~~~text
HTTP request
     |
     +-- Submit async task
     |       |
     |       v
     |    Return immediately
     |
     v
HTTP response

Executor worker later:
     |
     +-- Build message
     +-- JavaMailSender.send
     +-- Record actual send-call duration
~~~

If you place a timer around an `@Async` call from the request handler, you may only measure submitting the task into the executor. To measure SMTP, place the timer **inside the method running on the worker**.

### 15.1. Executor queue wait

If tasks wait in an executor queue, measure that wait time separately when it impacts SLOs.

### 15.2. Async does not make tasks durable

`@Async` does not automatically persist sending intent to a database or durable queue. When a process stops, in-memory tasks can be lost. For important notifications, use a transactional outbox or a queue with appropriate retention.

### 15.3. Exceptions do not propagate back to the request

With a void async listener, send errors do not return to the already-completed request. The worker must record failure metrics, outbox state, and retries independently.

## 16. Measuring batch sends vs. individual messages

`JavaMailSender` supports sending multiple messages in one call:

~~~java
mailSender.send(messageA, messageB, messageC);
~~~

An outer timer measures **batch duration**, not three individual message durations.

Example:

~~~text
Batch size:        3
Batch send time:   3.6 s
~~~

**Do not divide 3.6/3 evenly** and treat it as each message's latency. Connections can be shared, each message differs in size and processing time, and one message can fail.

### 16.1. If per-message tracking is required

You can send and time each message independently if the trade-off is acceptable, or instrument inside an adapter/provider. When a batch has partial failures, track per-event state rather than just an aggregate outcome.

### 16.2. Which layer is being counted?

One `send` call containing three `MimeMessage` objects is **1 invocation**, but may represent **3 message attempts**. Use distinct metric names and instrumentation scopes to avoid confusion.

## 17. SMTP timeouts are not an overall deadline

Example Spring Boot configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: mail-service
    password: secret-from-secure-runtime
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Account name and password here are placeholders; in real deployments, retrieve secrets from a secret manager and never store real credentials in source code.

| Property | Wait Phase Typically Controlled |
| --- | --- |
| **mail.smtp.connectiontimeout** | Establishing connection |
| **mail.smtp.timeout** | Reading response |
| **mail.smtp.writetimeout** | Writing data to socket |

Values are typically in milliseconds in the corresponding Jakarta Mail SMTP provider.

### 17.1. A 10-second read timeout does not mean a 10-second max send

A single send call can involve multiple reads/writes, handshakes, authentication, and data transfers. One I/O operation's timeout does not equal an overall deadline for the entire procedure.

### 17.2. Metrics do not replace timeouts

Timers report duration; they do not abort an overly slow operation. Configure network timeouts and proper task-handling controls.

### 17.3. Timeouts set too low can cause false failures

When sending large attachments or using a provider that normally takes longer to respond, overly short timeouts increase errors and retries, and can even cause duplicates. Tune based on actual latency distributions and SLAs.

### 17.4. Timeout after DATA

If the client has transmitted `DATA` but does not receive the final response, the relay may have accepted the message. Failure metrics must be interpreted alongside **UNKNOWN_OUTCOME**; retrying risks creating duplicate emails.

## 18. Breaking down retry and backoff in total latency

An email event tried three times:

~~~text
Attempt 1: 2 s -> temporary failure
Backoff:  30 s
Attempt 2: 5 s -> temporary failure
Backoff: 120 s
Attempt 3: 1 s -> accepted
~~~

Total send-call time is 8 seconds, while backoff time is 150 seconds. End-to-end time can exceed 158 seconds due to queuing, building, and scheduling.

**Never label 158 seconds as “SMTP processing time”.**

### 18.1. Each attempt should have its own measurements

Track attempt count, build duration, submit-call duration, error category, and `nextAttemptAt` per task.

### 18.2. Separate event logs from metric tags

Event IDs, attempt ordinals, and recipient references belong in controlled logs/traces. Metric tags should only use bounded values like **attempt_group=first/retry** when genuinely needed.

### 18.3. Retries must have a business deadline

Password reset or OTP emails can expire. If an email is only accepted after its link has expired, optimizing submit-call latency will not fix user experience correctness. Measure end-to-end latency and bound retries appropriately.

## 19. Latency distribution: average, p50, p95, p99

An average can hide tail latency.

| Statistic | How to Read It |
| --- | --- |
| **Count** | Number of calls or samples |
| **Mean/average** | Average duration within the window |
| **p50** | Threshold below which roughly half of samples fall |
| **p95** | Roughly 95% of samples fall at or below this |
| **p99** | Roughly 99% of samples fall at or below this |
| **Max** | Largest sample in the statistical window |
| **Histogram** | Sample distribution across bucket thresholds |

Example:

~~~text
p50 send = 0.4 s
p95 send = 1.1 s
p99 send = 12 s
~~~

Most calls are fast, while a small fraction hit timeouts or large resources.

### 19.1. Percentiles at low volume

With 5 messages per hour, a one-minute percentile is statistically unstable. Dashboards should show sample counts alongside percentiles and use appropriate time windows.

### 19.2. Never average p95s across instances

Percentiles are not linearly additive. To obtain a system-wide p95, aggregate histogram buckets properly instead of averaging per-process p95 values.

### 19.3. Separate success and failure outcomes

Long timeout failures can pull the combined p95 upward. To understand system health, inspect latency split by **outcome** alongside **error ratio**, rather than a single combined percentile.

## 20. Configuring Micrometer histograms

Example Timer:

~~~java
Timer submitTimer = Timer.builder(
        "mail.smtp.submit.call.duration"
    )
    .description("Synchronous JavaMailSender send duration")
    .tag("kind", "order_confirmation")
    .tag("outcome", "success")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
            java.time.Duration.ofMillis(250),
            java.time.Duration.ofSeconds(1),
            java.time.Duration.ofSeconds(3),
            java.time.Duration.ofSeconds(10)
    )
    .register(registry);
~~~

You can then record:

~~~java
submitTimer.record(
        java.time.Duration.ofMillis(850)
);
~~~

Thresholds are illustrative. In a real application, keep Timer configuration consistent across instances and outcomes, avoiding meters with the same name/tags but differing distribution settings.

### 20.1. Histograms have a cost

Many buckets combined with many tag combinations can generate a huge number of time series. Enable histograms only for key Timers and control cardinality.

### 20.2. Never put raw sizes into tags

To analyze attachment sizes:

~~~text
size_class=small
size_class=medium
size_class=large
~~~

Buckets must be defined stably. Never turn every exact byte count into a separate tag value.

## 21. Reading Timers in Prometheus

A Micrometer metric named:

~~~text
mail.smtp.submit.call.duration
~~~

can be exported by Prometheus into series similar to:

~~~text
mail_smtp_submit_call_duration_seconds_count
mail_smtp_submit_call_duration_seconds_sum
mail_smtp_submit_call_duration_seconds_bucket
~~~

The **bucket** series depends on histogram/SLO configuration and exporter behavior. Never assume it always exists.

### 21.1. Throughput

~~~promql
sum(
  rate(mail_smtp_submit_call_duration_seconds_count[5m])
)
~~~

This is the rate of **send invocations recorded by the timer**, not the number of messages delivered to inboxes.

### 21.2. Average submit-call duration

~~~promql
sum(
  rate(mail_smtp_submit_call_duration_seconds_sum[5m])
)
/
sum(
  rate(mail_smtp_submit_call_duration_seconds_count[5m])
)
~~~

Results are typically in seconds. When there is no traffic, the denominator can be 0; dashboards must handle empty-sample states gracefully.

### 21.3. p95 from histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(
      mail_smtp_submit_call_duration_seconds_bucket{
        outcome="success"
      }[5m]
    )
  )
)
~~~

You can group by **kind** to compare email categories, for example aggregating `by (le, kind)`.

## 22. Metric tags should use low-cardinality values

| Tag to Consider | Example Values |
| --- | --- |
| **kind** | order_confirmation, password_reset |
| **outcome** | success, failure |
| **provider** | primary_smtp, backup_smtp |
| **error_category** | auth, timeout, tls, recipient, unknown |
| **size_class** | small, medium, large |
| **attempt_group** | first, retry |

Do not include directly:

- Recipient email address.
- Subject/body.
- Password or OAuth token.
- Order ID, event ID, or Message-ID.
- Arbitrary filename or URL.
- Raw exception message.
- Tenant ID if count is very high and the backend is not sized for it.

Individual values belong in access-controlled **structured logs/traces**, not general metric labels.

### 22.1. Map SMTP errors to categories

Never use `exception.getMessage()` as a tag. Diagnostic text can include addresses, hosts, or provider-returned content and explode time series counts.

### 22.2. Low cardinality is an operational requirement

Each tag combination can create a distinct series. At high email volumes, attaching `userId` or recipient causes the metrics backend to consume excessive memory/storage and degrades query performance.

## 23. Structured logs and tracing complement metrics

Metrics answer **how long and how many times**. Logs/traces help find **which event, which attempt, and what error**.

Safe log example:

~~~text
eventId=mail-event-3024
kind=order_confirmation
attempt=2
buildDurationMs=13
submitDurationMs=10024
outcome=failure
errorCategory=read_timeout
~~~

There is no need to log recipient addresses or email contents.

### 23.1. Correlation ID

With an outbox, a stable ID links business transaction → outbox event → worker attempt → SMTP outcome.

### 23.2. Do not leave Jakarta Mail protocol debug enabled permanently

Debug output can expose addresses, AUTH metadata, and sensitive provider details. For production performance monitoring, prefer metrics/traces and bounded logs.

### 23.3. Tracing does not replace a stopwatch

A trace span can capture operation duration and link multiple services. If you already use Observation/Tracing to emit the same metric, avoid double-instrumenting the same scope.

## 24. Using Micrometer Observation when tracing is already enabled

Conceptual example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation.createNotStarted(
        "mail.smtp.submit",
        observationRegistry
    )
    .lowCardinalityKeyValue(
            "mail.kind",
            "order_confirmation"
    )
    .observe(() -> mailSender.send(message));
~~~

**observationRegistry** and **message** are prepared by the application. Handlers/exporters decide how this observation produces metrics or traces.

### 24.1. Avoid duplicate instrumentation

If both a manual Timer and an Observation measure `send` with the same semantics, dashboards may end up with two different metric names for one scope or even double-count. Pick a consistent convention.

### 24.2. Trace fields still require privacy review

Even high-cardinality trace fields can be stored in a backend. Never put tokens or email content into attributes just because they do not create metric series.

## 25. Unit testing Timers without an SMTP server

To test instrumentation:

- Use **Mockito** to mock `JavaMailSender`.
- Use a real in-memory `MimeMessage`.
- Use **SimpleMeterRegistry**.
- Use **Micrometer MockClock** to control duration.
- Use JUnit 5 to assert count, outcome, and send invocation count.

Avoid calling **Thread.sleep(100)** and asserting an exact 100 ms timer; OS scheduling and CI load make such tests flaky.

### 25.1. MockClock example

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.time.Duration;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class TimedOrderMailServiceTest {

    @Test
    void measuresSubmitDurationWithoutNetwork() {
        MockClock clock = new MockClock();

        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(
                        SimpleConfig.DEFAULT,
                        clock
                );

        JavaMailSender sender = mock(JavaMailSender.class);

        MimeMessage mimeMessage = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage())
                .thenReturn(mimeMessage);

        doAnswer(invocation -> {
            clock.add(Duration.ofMillis(250));
            return null;
        }).when(sender).send(any(MimeMessage.class));

        TimedOrderMailService service =
                new TimedOrderMailService(sender, registry);

        service.sendConfirmation(
                new OrderMailData(
                        "an@example.net",
                        "ORDER-001",
                        "Order confirmed."
                )
        );

        Timer sendTimer = registry
                .find("mail.smtp.submit.call.duration")
                .tag("kind", "order_confirmation")
                .tag("outcome", "success")
                .timer();

        assertNotNull(sendTimer);
        assertEquals(1, sendTimer.count());
        assertEquals(
                250.0,
                sendTimer.totalTime(TimeUnit.MILLISECONDS),
                0.01
        );

        Timer buildTimer = registry
                .find("mail.message.build.duration")
                .tag("outcome", "success")
                .timer();

        assertNotNull(buildTimer);
        assertEquals(1, buildTimer.count());

        verify(sender, times(1))
                .send(any(MimeMessage.class));
    }
}
~~~

The test controls time with `MockClock` rather than waiting a real 250 ms. It verifies that the **Timer accurately recorded the mocked send call's duration**, not real-world SMTP performance.

### 25.2. Why doesn't the build Timer assert specific milliseconds?

`MockClock` only advances inside the mocked `send`. Building runs normal code and may record 0 duration on the fake clock. Here, the build test checks that the timer was created and counted accurately; if you need to test a non-zero build duration, advance the clock or mock a renderer within that scope.

## 26. Testing timers on send failure

Example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;

@Test
void recordsFailureDuration() {
    SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

    JavaMailSender sender = mock(JavaMailSender.class);

    when(sender.createMimeMessage()).thenReturn(
            new MimeMessage(
                    Session.getInstance(new Properties())
            )
    );

    doThrow(new MailSendException("simulated"))
            .when(sender).send(any(MimeMessage.class));

    TimedOrderMailService service =
            new TimedOrderMailService(sender, registry);

    assertThrows(
            MailSendException.class,
            () -> service.sendConfirmation(
                    new OrderMailData(
                            "an@example.net",
                            "ORDER-002",
                            "Order confirmed."
                    )
            )
    );

    Timer failure = registry
            .find("mail.smtp.submit.call.duration")
            .tag("outcome", "failure")
            .timer();

    assertNotNull(failure);
    assertEquals(1, failure.count());
}
~~~

### 26.1. Testing the build failure branch

When a recipient or template causes an error during build:

- The build timer must record `outcome=failure`.
- The send timer must have no sample added for that event.
- `JavaMailSender.send` must not be called.

This keeps input errors from polluting SMTP metrics.

### 26.2. An instrumentation test is not a benchmark

A unit test with mocks does not measure network, TLS, or provider latency. It verifies that metric recording behaves as coded.

## 27. Integration testing with a controlled SMTP server

To observe real sending performance, use an SMTP test server or fake transport capable of injecting delays at chosen phases:

| Phase | Test Scenario |
| --- | --- |
| Greeting | Server sends `220` slowly |
| STARTTLS | Slow TLS handshake or invalid certificate |
| AUTH | Slow response or returned error |
| RCPT TO | Delayed recipient acceptance |
| DATA | Throttled data transfer |
| Final response | Delayed response after DATA |
| Network | Connection drop, timeout |

These tests can verify that send-call duration grows with the delay and failure timers are still recorded.

### 27.1. Do not assert exact milliseconds over sockets

Scheduler, JVM, and network jitter cause total time to fluctuate. Use reasonable tolerance bounds or relative comparisons in a controlled test environment.

### 27.2. Never load-test production SMTP carelessly

Sending thousands of emails through a real provider can hit rate limits, harm sender reputation, or accidentally email real users. Only load-test in authorized environments/accounts with synthetic data.

### 27.3. Testing attachment sizes

Compare small and large messages to see the impact of file reading and byte transfer. Do not assume differences come solely from the SMTP server if resources are read lazily during `send`.

## 28. How to interpret slow scenarios

### 28.1. Slow build, fast send

~~~text
build p95 = 2.7 s
send p95  = 0.4 s
~~~

Investigate templates, queries, PDF generation, attachment loading, and CPU/GC. There is no basis yet to blame or replace the SMTP provider.

### 28.2. Fast build, slow send

~~~text
build p95 = 0.02 s
send p95  = 7.0 s
~~~

Investigate connect, TLS, AUTH, provider throttling, DATA, MIME size, and lazy resource reads. Do not conclude the server is slow before ruling out client-side work.

### 28.3. High queue delay, fast send

~~~text
queue p95 = 180 s
build p95 = 0.02 s
send p95  = 0.4 s
~~~

Investigate worker capacity, scheduling, leases, backlog, retry backoff, and outbox database queries.

### 28.4. Failure duration near timeout

~~~text
send failure ~= 10 s
errorCategory=read_timeout
~~~

Likely related to `mail.smtp.timeout` around 10 seconds. Inspect the root cause and phase; total send time does not necessarily equal a single read timeout.

### 28.5. Very high p99 with healthy p95

~~~text
p50 = 0.3 s
p95 = 1.0 s
p99 = 20 s
~~~

A small subset of messages may be hitting timeouts or large attachments. Break down by `kind`/`outcome`/`size_class` rather than adding a recipient tag.

### 28.6. Requests faster after switching to @Async

This may just be a boundary shift: the request no longer waits for SMTP. Measure inside the worker and check end-to-end to relay acceptance before claiming the system sends faster.

## 29. Minimum operational dashboard

A dashboard should display:

| Group | Metrics |
| --- | --- |
| Message build | p50, p95, p99, count, errors |
| Template render | p95 and cache/error metrics if needed |
| SMTP submit call | p50, p95, p99 by outcome |
| Throughput | Send attempts/second |
| Failure | Error ratio and error categories |
| Outbox | Pending, oldest pending, queue delay |
| Retry | Attempts, scheduled retries, terminal failure |
| End-to-end | Commit-to-relay acceptance |
| Capacity | Active worker count, executor saturation |
| Message class | Kind and size bucket |

### 29.1. Alerts must lead to action

For example:

- Build p95 spikes after template changes → inspect renderer.
- Send p95 spikes and TLS errors rise → inspect TLS/provider.
- Queue oldest age breaches SLA → inspect worker capacity/locks.
- Retry queue grows → inspect rate limits or provider outage.
- AUTH failures rise → check credentials/policy; do not retry blindly.
- `UNKNOWN_OUTCOME` rises → reconcile before retrying to reduce duplicates.

### 29.2. Display sample count

A percentile from a handful of messages has very different reliability from a percentile across tens of thousands of messages. Avoid firing overly sensitive alerts on tiny sample counts.

## 30. Example SLOs for email

Illustrative objectives can be defined:

~~~text
SLO-1:
  95% successful SMTP submit calls finish within 3 seconds.

SLO-2:
  99% order-confirmation events reach SMTP relay
  within 2 minutes of business commit.

SLO-3:
  No high-priority outbox event remains pending for
  more than 10 minutes without an observable state.
~~~

These are not universal standards for Spring Mail. Calibrate them to your provider, message type, SLA, traffic volume, and business criticality.

### 30.1. Operational SLOs are not recipient open-rate SLOs

SMTP relay acceptance is a technical milestone, not a read receipt. Never use send-call metrics to claim users read the email.

### 30.2. Security emails have different deadlines from newsletters

Password resets can become useless once the link expires. Newsletters can tolerate longer queue times. Do not apply identical deadlines across all types without a business reason.

## 31. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Measuring only total HTTP request | Cannot see queue/build/send bottlenecks | Separate scopes |
| Using `currentTimeMillis` for elapsed time | Vulnerable to clock adjustments | Use `nanoTime` or Timer |
| Recording metric after `send` without `finally` | Drops errors and timeouts | Record both success and failure |
| Calling send-call “server processing” | Technically inaccurate | Name accurately |
| Assuming `addAttachment` already read the file | Lazy reads may occur inside `send` | Document build contract clearly |
| Serializing MIME twice just to measure | Doubles CPU/I/O and memory | Instrument necessary operations only |
| Timing `@Async` from the caller | Measures only enqueueing | Time inside the worker |
| Mixing queue delay into SMTP latency | Misdiagnoses bottlenecks | Keep separate metrics |
| Putting recipient/Subject in tags | Leaks PII and causes high cardinality | Use low-cardinality tags |
| Looking only at average | Ignores tail latency | Track histograms/p95/p99 |
| Averaging p95 across instances | Statistically invalid | Aggregate histograms properly |
| Dividing batch duration evenly | Inaccurate per-message timing | Track batch and individual states separately |
| Treating send success as delivered | SMTP acceptance differs from inbox | Model state accurately |
| Using `Thread.sleep` in unit tests | Flaky CI | Use `MockClock` |
| Leaving protocol debug enabled permanently | Exposes data, adds overhead | Use structured metrics |
| Assuming timeout means definitely unsent | Could happen after `DATA` | Model `UNKNOWN_OUTCOME` |
| Treating timeout properties as overall deadline | Actually bounds only that I/O operation | Measure and control the full flow |

## 32. Frequently asked questions

**1. How do you measure message creation time?**

Start a timer before the MimeMessage render/build block and stop it when that block finishes. Clarify whether the timing includes templates, resource loading, and attachment generation.

**2. How do you measure SMTP wait time?**

Wrap `JavaMailSender.send(...)` with a timer and record it in `finally`. This is **synchronous submit-call duration**, not exact server processing duration.

**3. Why does send take long when build is fast?**

Because of network latency, DNS, TLS, AUTH, SMTP round-trips, MIME serialization, or lazily read attachments.

**4. Why use `System.nanoTime()`?**

It is suited for measuring elapsed time within a process and is unaffected by calendar clock adjustments.

**5. Can `Instant` be used for queue delay?**

Yes, when using persistent timestamps and accounting for clock skew. Never subtract `nanoTime` values from different machines.

**6. Do Timers record errors?**

Yes, if the application stops the sample in `finally` even when the operation throws an exception. Do not record timers only on the success branch.

**7. Does Spring Boot generate both build and send metrics automatically?**

Do not assume so. These are application-defined metric scopes that must be instrumented and exported according to configuration.

**8. Can a `JavaMailSender` Timer measure STARTTLS handshake separately?**

Not with a single timer wrapping `send`. You need transport-level instrumentation or suitable telemetry to measure individual phases.

**9. How does `MimeMessagePreparator` affect timers?**

The message-preparation callback executes inside `send(preparator)`, so an outer timer covers both build and transport. Measure the callback separately if you need to distinguish them.

**10. Does `SimpleMailMessage` need a build Timer?**

Possibly, though object construction is usually short; `JavaMailSenderImpl` may convert it to MIME during `send`. Document the scope clearly.

**11. Why do PDFs make `send` slower?**

The file may be read and encoded during MIME serialization inside `send`, and more bytes take longer to transfer over the network.

**12. Should `MimeMessage.writeTo` be called before `send` just to measure?**

No in production if it forces double serialization or high memory usage. It can be used in tests or specialized instrumentation.

**13. Is queue delay SMTP latency?**

No. Queue delay is how long the task waits before `send` begins, whereas send-call duration is how long the send invocation runs.

**14. Does `@Async` automatically make SMTP faster?**

No. It shifts work to another thread so the request returns quickly, while worker duration still needs to be measured.

**15. What is p95?**

The threshold that roughly 95% of samples in an observation set do not exceed. It is not the maximum and does not reveal the entire tail.

**16. Should `eventId` be attached as a metric tag?**

No. It creates high cardinality; keep it in controlled logs and traces.

**17. Can Timers be tested without `Thread.sleep`?**

Yes. Micrometer `MockClock` combined with `SimpleMeterRegistry` lets unit tests control elapsed time deterministically.

**18. In a batch send of three messages, which message owns the duration?**

The entire batch owns it if the timer wraps a single `send` call. Do not divide evenly; use separate instrumentation for per-message timing.

**19. Does a 10-second read timeout guarantee `send` finishes within 10 seconds?**

Not necessarily. Sending involves multiple I/O steps and can wait multiple times.

**20. If `send` throws a timeout, was the email definitely not accepted?**

No. A timeout after `DATA` can occur after the SMTP relay already received the message. Retrying risks creating duplicates.

**21. When is an end-to-end metric especially important?**

Especially when using an outbox, queue, retries, or async execution. It reflects the time from business commit to SMTP relay acceptance.

**22. Can `JavaMailSenderImpl.testConnection` be used to measure send latency?**

No. `testConnection` checks connectivity/login at a basic level without building and transmitting a real message. Calling it before every email also adds extra connections and overhead, so it cannot replace a Timer around `send`.

## 33. Key takeaways on measuring message build and SMTP wait time

**Good measurements require clear boundaries.** In Spring Framework Mail, separate message render/build time from the synchronous **JavaMailSender.send(...)** call time. Call the latter **SMTP submit-call duration** because it can include MIME serialization, lazy attachment reads, DNS/TCP, TLS, AUTH, DATA, and waiting for responses — not just SMTP server processing time.

Use **System.nanoTime()** or **Micrometer Timer** to measure elapsed time within a process. Record in **finally** so error and timeout samples are never lost. When using **@Async** or an outbox, place the Timer inside the worker and also measure **queue delay**, **retry backoff**, and **event-to-relay-acceptance**; never sum overlapping intervals.

Track count, error ratio, histograms, and p50/p95/p99; group by bounded tags such as `kind`, `outcome`, and `error_category`. Never put recipients, `Subject`, tokens, or event IDs into metric tags. Test instrumentation with **JUnit 5, Mockito, and Micrometer MockClock**, and use a controlled SMTP test server when investigating real transport behavior.

The goal is not merely answering “how long does sending an email take?”, but knowing **which stage causes slowness, how latency affects users, and whether to optimize templates, attachments, queues, or SMTP** without compromising system accuracy or security.

# Tracing Flows from Business Events to Mail Servers in Spring Framework Mail

When a user confirms an order but does not receive an email, the first question is usually: did the system send the email yet? That question goes deeper than a single `JavaMailSender.send(...)` call. An email may traverse a business transaction, event, outbox, scheduler, asynchronous worker, `MimeMessage` construction, SMTP submission, and finally delivery/bounce events sent back by the provider.

A successful send call only indicates that the SMTP transport completed the submission operation per the library contract. It does not prove the user saw the email in their Inbox. Conversely, a timeout after SMTP `DATA` can occur when the server already received the message yet the client missed the final reply. Merely adding “send started” and “send failed” logs is not enough to draw the right conclusion.

**Tracing** reveals execution stages, durations, and causal relationships. Observing a mail pipeline also requires **stable correlation IDs, structured logs, metrics, outbox states, and provider event IDs**, because traditional SMTP does not automatically carry distributed trace context like HTTP/gRPC.

This lesson walks through tracing an email from business event to mail server in a Spring application, covering Micrometer Observation/Tracing, MDC and async context, transactional outboxes, SMTP outcome ambiguity, provider webhooks, secure logging, runbooks, and testing.

## 1. Email flow from business logic to SMTP

Example when a user confirms an order:

~~~text
HTTP POST /orders/{id}/confirm
              |
              v
     OrderApplicationService
              |
              +--> validate + update order
              +--> insert mail_outbox
              |
              v
         DB COMMIT
              |
              v
      Outbox scheduler
              |
              v
        Claim mail job
              |
              v
        Mail worker
              |
              +--> load template/snapshot
              +--> render subject/plain/HTML
              +--> resolve attachments
              +--> build MimeMessage
              +--> acquire rate-limit slot
              |
              v
       JavaMailSender.send(...)
              |
              v
      SMTP connection + TLS + AUTH
              |
              +--> MAIL FROM
              +--> RCPT TO
              +--> DATA
              +--> final SMTP response
              |
              v
      Record SUBMITTED/RETRY_WAIT/FAILED
              |
              v
      Provider events if supported
              |
              +--> delivered
              +--> deferred
              +--> bounced
~~~

An HTTP trace may span validation, update, and outbox insertion. A worker may run seconds or hours later on a different instance. Provider webhooks may arrive even later. Therefore, never assume every step is a child span of one single HTTP trace.

## 2. Questions a good trace must answer

1. Which business event created the send intent?
2. Did the transaction commit or roll back?
3. Was the outbox record durably persisted?
4. Did the scheduler see the due job?
5. Which worker claimed the job, and is its lease still valid?
6. How long did the job wait before being processed?
7. Did anything fail while preparing templates, HTML, images, or attachments?
8. Was the SMTP client called?
9. Was send time spent in connect, TLS, AUTH, DATA, or waiting for the reply?
10. Did the SMTP relay accept the message?
11. How many retries ran, and for what errors?
12. Did the provider report delivered, bounced, or deferred?

Do not create spans for every getter. Instrument **meaningful boundaries**: transactions, enqueues, claims, rendering, transport, retry state, and event callbacks.

## 3. Traces, spans, logs, metrics, and durable state

| Component | Role | Example |
| --- | --- | --- |
| Trace | Links a related execution chain | HTTP confirm-order trace |
| Span | An operation with duration and attributes | `mail.smtp.submit` |
| Structured log | A point-in-time event | Job N-2105 claimed |
| Metric | Aggregate trends/counts | SMTP error rate or queue age P95 |
| Business event | A business occurrence | `OrderConfirmed` |
| Outbox row | Durable send intent | Notification N-2105 in `RETRY_WAIT` |
| Provider event | Downstream outcome from ESP/relay | Delivered or bounced |
| Correlation ID | Connects records across traces and systems | `notificationId` |

Traces undergo sampling and retention, so they are not the source of truth for notification status. Logs locate individual jobs; metrics reveal trends; outbox database rows and provider event records hold business-critical outcomes.

## 4. Identifiers to distinguish

| ID | Source | Stable Across Retries? | Purpose |
| --- | --- | --- | --- |
| `orderId` | Business domain | Yes | Look up order |
| `businessEventId` | Domain event | Yes | Look up email-triggering event |
| `notificationId` | Mail application | **Yes** | Identifies one logical send request |
| `outboxId` | Durable outbox | Yes | Look up record |
| `attemptId` | Worker per send | No | Distinguish individual attempts |
| `traceId` | Tracing system | Within one trace | Find related spans |
| `spanId` | Tracing system | No | One operation segment |
| `providerMessageId` | ESP if available | May change per attempt | Look up provider events |
| `smtpQueueId` | SMTP relay if exposed | May change | Search mail server queue |
| MIME `Message-ID` | Email header | Implementation-dependent | MIME-level correlation |

**Never use `traceId` as a business idempotency key.** One event may span multiple traces; one trace may spawn multiple notifications. `notificationId`/`outboxId` is usually the best key to follow a logical email across the whole pipeline.

MIME `Message-ID` is not a provider queue ID, and SMTP does not guarantee deduplication based solely on `Message-ID`.

## 5. An illustrative timeline

~~~text
T+000 ms   HTTP request starts
T+011 ms   order.confirm start
T+025 ms   order updated
T+030 ms   mail_outbox row N-2105 inserted
T+042 ms   transaction COMMIT
T+180 ms   outbox poller claims N-2105
T+192 ms   mail.render start
T+214 ms   mail.render completed
T+220 ms   smtp.submit starts, attempt A1
T+415 ms   SMTP connection/TLS/AUTH completed
T+770 ms   final DATA 250 accepted
T+782 ms   outbox status SUBMITTED
T+6 sec    provider event DELIVERED
~~~

Timings above are illustrative. Looking solely at the 550 ms `mail.smtp.submit` span misses the 180 ms queue wait or a transaction bottleneck. If a job sits 10 minutes in the outbox, SMTP may still be fast while notifications remain slow.

## 6. Micrometer Observation and Tracing in Spring

Modern Spring Boot supports Micrometer Observation to observe operations. With an appropriate Micrometer Tracing bridge and exporter, observations can be emitted as spans while also producing metrics.

~~~text
Application code
       |
       v
Micrometer ObservationRegistry
       |
       +--> Observation handlers / timers
       |
       +--> Micrometer Tracing bridge
                     |
                     v
               Trace exporter
                     |
                     v
               Trace backend
~~~

You need Spring Boot Actuator, a Micrometer Tracing bridge, and an exporter compatible with your Spring version. Injecting `ObservationRegistry` alone does not guarantee a trace backend receives spans unless a bridge and exporter are configured.

Partial configuration example:

~~~yaml
spring:
  application:
    name: order-mail-service

management:
  tracing:
    sampling:
      probability: 0.1
~~~

`0.1` illustrates 10% sampling, not a default or universal recommendation. Exporter endpoints, security, and logging integration must match your backend and version.

## 7. Span names should describe the operation

A system can define span names such as:

~~~text
order.confirm
mail.outbox.enqueue
mail.outbox.poll
mail.outbox.claim
mail.notification.process
mail.template.render
mail.attachment.load
mail.mime.prepare
mail.rate_limit.acquire
mail.smtp.submit
mail.outbox.mark_submitted
mail.provider.webhook.consume
~~~

Never construct span names containing recipients or IDs:

~~~text
mail.smtp.submit.customer@example.com
mail.smtp.submit.order.ORDER-123
~~~

Those values explode cardinality, hinder aggregation, and can leak personal data.

### Low-cardinality vs. high-cardinality

| Attribute | Cardinality | How to Use |
| --- | --- | --- |
| `mail.provider=primary` | Low | Metric tag and span |
| `mail.category=TRANSACTIONAL` | Low | Metric tag and span |
| `mail.outcome=SUBMITTED` | Low | Metric tag and span |
| `mail.failure_class=TRANSIENT` | Low | Metric tag and span |
| `notificationId=N-2105` | High | Structured log or controlled span attribute |
| Recipient address | High, PII | Avoid in metric tags; restrict in logs/traces |
| Mail subject/body | Potentially sensitive | Exclude from default telemetry |

In spans, use high-cardinality data only when investigative value outweighs retention/access risks. For metrics, never attach unique IDs to tags.

## 8. Tracing business logic and database transactions

Example use case:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orders.getRequired(orderId);

        order.confirm();
        orders.save(order);

        MailOutboxEntry mail =
            MailOutboxEntry.forConfirmedOrder(
                UUID.randomUUID(),
                orderId,
                order.customerId()
            );

        outbox.save(mail);
    }
}
~~~

The domain and repository classes are illustrative models, not Spring Mail classes. When updating the order and inserting into the outbox in one transaction, they commit or roll back together.

An `order.confirm` span returning normally does not automatically prove commit in every proxy/call setup. Observe transaction outcomes or read durable records. Never log “email enqueued durably” before commit if the transaction might still roll back.

## 9. An after-commit event listener is not yet durable dispatch

Example:

~~~java
@Component
public class ConfirmedOrderListener {

    private final MailDispatcher dispatcher;

    public ConfirmedOrderListener(
            MailDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onConfirmed(OrderConfirmedEvent event) {
        dispatcher.dispatch(event.notificationId());
    }
}
~~~

`AFTER_COMMIT` avoids running before commit when the event is published inside a transaction, yet a process crash after commit and before the listener finishes can still lose the send if it exists only as an in-memory event.

For critical emails, the outbox persists the request in the same transaction. Listeners can simply wake up a poller for lower latency, while the durable outbox still enables recovery after restarts.

Tracing should separate:

- Event published.
- Transaction committed.
- Durable outbox inserted.
- Worker claimed.
- SMTP submission attempted.

If you instrument only the listener, an event lost before the listener runs leaves no worker trace to inspect.

## 10. How async breaks trace context

Tracing context typically lives in execution scope or thread locals. Crossing into `@Async`, `TaskExecutor`, `@Scheduled`, or another process does not carry context automatically:

~~~text
HTTP thread:
  traceId = A
  spanId  = B
        |
        +--> submit async task
                     |
                     v
mail-worker thread:
  current trace?
  MDC?
~~~

Without proper propagation, the worker may start an unrelated trace, emit logs missing `traceId`, or retain MDC from a prior task.

Never copy the entire HTTP request, security principal, or transaction context just to carry a correlation ID. `notificationId` is smaller, stable, and far more meaningful for durable mail workflows.

## 11. TaskDecorator and context propagation

Spring Framework versions supporting `ContextPropagatingTaskDecorator` allow configuring an executor like this:

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailTaskExecutor")
    public ThreadPoolTaskExecutor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");

        executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator()
        );

        return executor;
    }
}
~~~

Class availability and Micrometer context propagation dependencies must match your Spring version; do not assume every project includes this class. When unsupported, you can write a custom `TaskDecorator`, though MDC-only propagation is not equivalent to full tracing context propagation.

When a task executes immediately after a request, a parent-child trace makes sense. For an outbox job running hours later, starting a new trace linked by a stable ID or span link is usually clearer.

## 12. What should the outbox store to link traces?

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE mail_outbox (
    id                    UUID PRIMARY KEY,
    business_event_id     UUID NOT NULL,
    aggregate_id          UUID NOT NULL,
    category              VARCHAR(40) NOT NULL,
    status                VARCHAR(30) NOT NULL,
    attempts              INTEGER NOT NULL DEFAULT 0,
    next_attempt_at       TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    origin_trace_id       VARCHAR(32),
    origin_span_id        VARCHAR(16),
    origin_service        VARCHAR(100)
);
~~~

Not every job must have `origin_trace_id`. When an active trace exists, the application can store valid IDs to aid investigation, while primary correlation remains the outbox/notification ID.

~~~text
Trace A: HTTP order confirmation
  |
  +--> order.confirm
  +--> mail.outbox.enqueue
          |
          +--> notificationId = N-2105

           time passes

Trace B: mail worker
  |
  +--> outbox.claim
  +--> mail.render
  +--> mail.smtp.submit
          |
          +--> notificationId = N-2105
          +--> originTraceId = A
~~~

If your backend supports span links, a worker span can link back to the originating context. Never hijack the worker's `traceId` just to make all logs look like one trace.

## 13. Parent-child spans, span links, and correlation IDs

| Relationship | When Appropriate | Key Detail |
| --- | --- | --- |
| Parent-child | Work runs within the parent's direct execution | Requires proper context propagation |
| Span link | Job/message runs independently yet was triggered by another trace | Requires tracing API/backend support |
| Correlation ID | Links across DB, workers, providers, and even when traces are sampled out | Must be persisted and logged consistently |

If using OpenTelemetry `SpanBuilder.addLink(...)`, supply a valid, trusted `SpanContext`. Never treat an arbitrary `traceparent` string from user input as trusted context to attach to internal traces.

Across different Micrometer Tracing bridges, span-link APIs can vary. Simply logging `originTraceId` works well if you want to avoid tying to a specific vendor API.

## 14. Creating an Observation around JavaMailSender.send

One of the cleanest instrumentation points is the SMTP send boundary:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

@Service
public class ObservedMailDeliveryAdapter {

    private final JavaMailSender mailSender;
    private final ObservationRegistry observations;

    public ObservedMailDeliveryAdapter(
            JavaMailSender mailSender,
            ObservationRegistry observations) {
        this.mailSender = mailSender;
        this.observations = observations;
    }

    public void send(
            MimeMessage message,
            String provider,
            String category) {

        Observation.createNotStarted(
                "mail.smtp.submit", observations
            )
            .lowCardinalityKeyValue("mail.provider", provider)
            .lowCardinalityKeyValue("mail.category", category)
            .observe(() -> mailSender.send(message));
    }
}
~~~

With an `ObservationRegistry` configured with appropriate handlers, this emits both a timer metric and a span. Without handlers/exporters, an observation alone does not guarantee traces appear on dashboards.

`provider` and `category` must be normalized to a small value set. Never pass recipient addresses or subjects into `lowCardinalityKeyValue`.

## 15. Recording errors inside an observation

To control span lifecycle explicitly:

~~~java
public void submit(
        MimeMessage message,
        String notificationId) {

    Observation observation =
        Observation.createNotStarted(
                "mail.smtp.submit", observations
            )
            .lowCardinalityKeyValue(
                "mail.transport", "smtp"
            );

    observation.start();

    try (Observation.Scope scope =
             observation.openScope()) {

        mailSender.send(message);

        log.info(
            "SMTP submission completed for notificationId={}",
            notificationId
        );

    } catch (MailException exception) {
        observation.error(exception);

        log.warn(
            "SMTP submission failed, notificationId={}, type={}",
            notificationId,
            exception.getClass().getSimpleName()
        );

        throw exception;
    } finally {
        observation.stop();
    }
}
~~~

A production adapter typically classifies errors into `TRANSIENT`, `PERMANENT`, `CONFIGURATION`, and `AMBIGUOUS`. Never automatically call every exception `NOT_SENT`. A timeout after SMTP `DATA` transmission can mean the relay accepted the message while the final reply was lost.

This code deliberately avoids logging subjects/bodies, attachments, passwords, or raw SMTP transcripts.

## 16. No automatic distributed trace across SMTP servers

Traditional SMTP does not automatically propagate W3C Trace Context like instrumented HTTP/gRPC systems. A client-side span around `JavaMailSender.send(...)` does not cause the SMTP relay to recognize `traceparent` and emit a child span.

~~~text
Application trace
   |
   +--> mail.smtp.submit span
              |
              v
           SMTP
              |
              v
        SMTP relay
              |
              +--> mail queue ID / server logs
              +--> provider events
~~~

If you operate the SMTP server, you can add custom instrumentation and correlate via IDs. When using an external provider, reconcile using provider message IDs, SMTP queue IDs, recipient/account details, and timestamps.

Never inject `traceparent` into outgoing email headers expecting servers to understand it. Any custom correlation header also requires privacy evaluation and checking whether providers preserve it. Using an opaque notification ID is usually safer than exposing internal trace metadata externally.

## 17. Different SMTP 250 replies

An abbreviated session:

~~~text
C: EHLO app.example.com
S: 250 capabilities
C: MAIL FROM:<sender@example.com>
S: 250 OK
C: RCPT TO:<recipient@example.net>
S: 250 OK
C: DATA
S: 354 Continue
C: headers and body
C: .
S: 250 2.0.0 Queued as ABC123
~~~

A `250` after `EHLO`, `MAIL FROM`, or `RCPT TO` does not prove the full message was accepted. Only the **final success reply after the DATA terminator** proves the current relay accepted the submission.

`JavaMailSender.send(...)` does not portably return an object containing the server queue ID. If you need `ABC123`, obtain it from provider logs/APIs or custom transport instrumentation.

Even when the server accepts `DATA`, you cannot infer Inbox delivery. Providers can still defer, filter, quarantine, or bounce downstream.

## 18. Structured logs link multiple traces

Example log in the business service:

~~~json
{
  "timestamp": "2026-11-12T10:00:00Z",
  "service": "order-service",
  "event": "mail.outbox.enqueued",
  "traceId": "9d7436e89df6482898fe347812ae6c51",
  "orderId": "ORDER-123",
  "notificationId": "N-2105"
}
~~~

The worker can create a separate trace:

~~~json
{
  "timestamp": "2026-11-12T10:00:02Z",
  "service": "mail-worker",
  "event": "mail.smtp.submitted",
  "traceId": "be92f8366cc44836a7f18c3be8ffbe01",
  "notificationId": "N-2105",
  "attemptId": "N-2105-A1",
  "provider": "primary-smtp",
  "elapsedMs": 742,
  "status": "SUBMITTED"
}
~~~

`notificationId` connects both phases even if trace sampling drops one of the two traces. That is why stable correlation IDs are necessary alongside tracing context.

## 19. MDC in logging and thread reuse

MDC (*Mapped Diagnostic Context*) attaches contextual fields to logs. Example:

~~~java
public void processMail(String notificationId) {
    try (MDC.MDCCloseable ignored =
             MDC.putCloseable(
                 "notificationId", notificationId
             )) {

        log.info("Mail processing started");
        mailDelivery.submit(notificationId);
        log.info("Mail processing completed");
    }
}
~~~

`mailDelivery` is an application abstraction. Import SLF4J's `org.slf4j.MDC`.

Thread pools reuse threads. If task A leaves `notificationId=A` in MDC, task B can accidentally log under A. Use scoped contexts and `finally`/restore to prevent cross-task data leakage.

If you need to preserve an existing MDC value under the same key, snapshot the map before setting and restore it afterward; never assume every logging implementation behaves identically.

## 20. TaskDecorator copying only MDC

A decorator can capture MDC at submission time:

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submitted =
            MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                MDC.getCopyOfContextMap();

            try {
                if (submitted == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submitted);
                }

                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Attach it to `ThreadPoolTaskExecutor`:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

This propagates **MDC**, not automatically full OpenTelemetry/Brave span context. When exact parent-child spans are needed, use the propagation API suited to your tracing stack.

Avoid stacking multiple decorators copying the same context unless precedence is clear. Test tasks A and B sequentially on the same thread to confirm MDC does not leak.

## 21. @Scheduled pollers should have their own traces

A scheduler runs even without an inbound HTTP request:

~~~java
@Component
public class MailOutboxPoller {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxPoller(MailOutboxDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString =
        "${app.mail.poll-delay-ms:1000}")
    public void poll() {
        dispatcher.dispatchDue();
    }
}
~~~

You can create a `mail.outbox.poll` observation per polling cycle, and a separate `mail.notification.process` observation per job.

If a poll claims 100 records, never stuff all high-cardinality IDs into one span. The poll span measures batch throughput, while job-level observations and structured logs tie to individual notifications.

With durable outboxes, starting a fresh job trace plus a span link (if available) is usually cleaner than forcing all jobs to be descendants of a single cron span.

## 22. Measure queue wait separately from SMTP duration

A job timeline:

~~~text
createdAt       10:00:00.000
nextAttemptAt   10:00:00.000
processingAt    10:00:04.000
submittedAt     10:00:04.800

Queue wait      4.000 s
Processing      0.800 s
End-to-end      4.800 s
~~~

If customers report slow email, SMTP took only 800 ms. The remaining four seconds may stem from polling intervals, lease contention, `TaskExecutor` saturation, or rate limiters.

Measure:

- `mail.outbox.wait`: from job due time until processing begins.
- `mail.template.render`: content rendering time.
- `mail.mime.prepare`: MIME building time.
- `mail.smtp.submit`: transport duration.
- `mail.outbox.status_update`: persisting the outcome.

If a job was intentionally scheduled for later delivery, do not count scheduled waiting time as queue saturation. Measure planned delay and unplanned due lag separately.

## 23. Outbox state is the source of truth

A state machine:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +--> SMTP accepted ------> SUBMITTED
   |
   +--> temporary failure --> RETRY_WAIT
   |                              |
   |                              +--> PROCESSING
   |
   +--> permanent failure --> FAILED
   |
   +--> uncertain result ----> AMBIGUOUS
~~~

Persisted state should include:

- `notificationId` and `attemptId`.
- Old and new status.
- Attempt count.
- Worker/lease ID when relevant.
- Failure class and SMTP code if available.
- `nextAttemptAt`.
- UTC timestamps.
- Provider ID when supplied.

Traces can be sampled out or lost on exporter failure; outbox database rows must never rely on the tracing backend to drive retries, dead-lettering, or status.

## 24. One logical email can have multiple attempt traces

~~~text
notificationId = N-2105
   |
   +--> attempt A1
   |       SMTP 421 temporary error
   |       retry after backoff
   |
   +--> attempt A2
   |       read timeout after DATA
   |       outcome AMBIGUOUS
   |
   +--> attempt A3
           SMTP accepted
           duplicate risk exists
~~~

`notificationId` stays constant; `attemptId` changes. A system can wrap the worker job in a parent span with child spans per attempt, or emit separate traces per attempt linked by `notificationId` when executions are decoupled.

Never reset attempt counts on worker retry or process restart. Observe actual SMTP invocations, not merely how many tasks entered the executor.

## 25. Timeouts after DATA can be AMBIGUOUS

~~~text
Application                       SMTP relay
   |                                   |
   |------ MIME + DATA end ----------->|
   |                                   | accepted?
   |<------- response lost -----------X|
   |
   +--> read timeout
~~~

The `mail.smtp.submit` trace may report an error, yet that does not prove the message was unaccepted. If the relay received and queued the message before the reply was lost, retrying can send two emails.

Therefore, model an `AMBIGUOUS` state, perform provider-side reconciliation when an API exists, and define clear idempotency/duplicate-risk policies. MIME `Message-ID` alone does not guarantee SMTP deduplication.

When logging the error, record “submission outcome unknown after DATA” if phase evidence supports it. Never log a definitive `NOT_SENT` based solely on a timeout.

## 26. Provider message IDs and queue IDs

If an SMTP server replies:

~~~text
S: 250 2.0.0 Queued as ABC123
~~~

the ID `ABC123` helps operators search mail server logs/queues. One email may have several IDs:

- Internal notification ID.
- Attempt ID.
- MIME `Message-ID` header.
- SMTP relay queue ID.
- ESP message ID.

Never collapse these IDs into one field. `JavaMailSender.send(...)` does not return a standardized queue ID; use provider logs/event APIs or custom transport instrumentation when you need it.

When a provider message ID is captured, save it on the attempt record to correlate delivered/bounced events. When unavailable, fall back to timestamps, account metadata, message headers, or provider-supported correlation fields.

## 27. Provider webhooks form an independent trace

Providers can emit events after SMTP submission:

~~~text
HTTP POST /mail-events
       |
       v
Verify provider signature
       |
       v
Deduplicate event
       |
       v
Resolve providerMessageId
       |
       v
Find notificationId
       |
       v
Update delivery status
       |
       +--> DELIVERED
       +--> BOUNCED
       +--> DEFERRED
~~~

A webhook creates a new HTTP request and therefore fits a new trace. Link it to the notification via the provider message ID or correlation ID, using a span link if supported by your stack.

**Never keep the `mail.smtp.submit` span open for hours** waiting for a delivery event. Submission and delivery are two separate lifecycles. An email can be `SUBMITTED` and later `BOUNCED`, and those two states do not contradict each other.

Provider webhooks require source signature verification, event ID deduplication, and out-of-order event handling. Never trust an unverified Internet payload claiming a bounce/complaint and update state blindly.

## 28. JSON structured log for an attempt

~~~json
{
  "event": "mail.attempt.finished",
  "notificationId": "N-2105",
  "attemptId": "A2",
  "businessEventId": "E-441",
  "provider": "primary-smtp",
  "category": "TRANSACTIONAL",
  "workerId": "worker-3",
  "outcome": "TEMPORARY_FAILURE",
  "failureClass": "TRANSIENT",
  "smtpCode": "421",
  "elapsedMs": 821,
  "retryAt": "2026-11-12T10:05:00Z",
  "traceId": "eb598f2f108c4d6b8fae95dd161b4692"
}
~~~

Values are illustrative. Never fabricate an `smtpCode` or `providerMessageId` without real evidence. Never log raw MIME, recipients, subjects, passwords, OTPs, or auth tokens just to make logs look thorough.

Use small-cardinality fields as metric tags, and keep `notificationId` or recipient email out of tags due to high cardinality.

## 29. SMTP debug logs and data-leak risks

Jakarta Mail can write a protocol transcript:

~~~properties
spring.mail.properties.mail.debug=true
~~~

In tests or controlled investigations, this reveals `EHLO`, TLS, `AUTH`, `MAIL FROM`, `RCPT TO`, `DATA`, and replies. Depending on library and version, however, the transcript can expose recipient addresses, authentication credentials, MIME headers, or bodies.

- Never leave protocol debug enabled permanently in production.
- Base64 `AUTH` is **not** encryption.
- Enable only within a narrow scope and short window.
- Redact credentials and PII.
- Restrict read permissions and retention.
- Never paste raw transcripts into public tickets.

Protocol debug does not automatically emit distributed spans for each SMTP command. On timeouts, if no final `DATA` response appears, accept that the outcome may be uncertain.

## 30. Metrics must complement traces

Example metric names:

| Metric | Meaning |
| --- | --- |
| `mail_outbox_pending` | Pending jobs count |
| `mail_outbox_oldest_due_age_seconds` | Age of oldest due job |
| `mail_outbox_claim_total` | Claims by outcome |
| `mail_send_attempts_total` | Actual SMTP invocation count |
| `mail_submission_total` | Submitted / failed / ambiguous |
| `mail_smtp_duration_seconds` | SMTP duration distribution |
| `mail_render_duration_seconds` | MIME preparation time |
| `mail_queue_wait_seconds` | Queue wait delay |
| `mail_retry_scheduled_total` | Scheduled retries count |
| `mail_retry_exhausted_total` | Emails exhausting retry policy |
| `mail_smtp_timeout_total` | Transport timeouts count |
| `mail_provider_events_total` | Delivery / bounce / defer events |
| `mail_executor_rejected_total` | Executor saturation rejections |

These are application-designed names; they do not exist by default merely by adding Spring Mail.

For example, when `mail_queue_wait_seconds` P95 rises, traces show slow worker claiming, while logs filtered by notification ID show whether a specific job hit rate limits or DB errors.

Sampling may export only a fraction of traces. Never count total emails from backend span counts; use metrics and database state.

## 31. Sampling, retention, and cost

A high-volume mail system emitting dozens of spans per recipient can incur heavy telemetry costs.

You should:

- Apply sensible sampling to healthy traffic.
- Keep error logs and durable state separate.
- Use tail-based sampling for errors or slow traces if your backend supports it.
- Cap span, attribute, and event counts.
- Avoid instrumenting every MIME byte or template variable.
- Set retention and access controls aligned with data sensitivity.
- Never treat the trace backend as an immutable audit system.

If the originating trace was sampled out of the backend, workers can still correlate by notification ID. Saving `originTraceId` in the outbox is merely supplemental context.

## 32. Data protection rules in mail tracing

Emails can contain sensitive data:

- `From`, `To`, `Cc`, `Bcc`.
- `Subject`, HTML body, and attachments.
- OTPs and reset tokens.
- SMTP usernames and passwords.
- OAuth access tokens and refresh tokens.
- Provider error payloads echoing recipient addresses.
- Template variables holding customer details.

Rules:

1. Never log raw bodies or attachments by default.
2. Never put recipients into span names or metric tags.
3. Never put credentials into trace baggage.
4. Never propagate full `Authorization` headers into mail workers.
5. Use internal notification IDs for correlation.
6. Redact provider errors whenever they contain PII.
7. Restrict telemetry read permissions and retention windows.
8. Be cautious before adding custom trace headers to outbound emails.
9. Never store raw SMTP transcripts in production without controlled procedures.
10. Collect only data needed for legitimate operational purposes.

A trace ID is not a password, yet it can reveal links between internal operations; never share it externally without review.

## 33. Multiple recipients and batch sends

A `MimeMessage` can target multiple recipients, or `JavaMailSender` can send multiple messages in a batch. On failure:

- One recipient may be rejected.
- Some recipients may be accepted if partial-send settings allow it.
- `MailSendException.getFailedMessages()` helps identify failing messages in a batch.
- Nested Jakarta Mail `SendFailedException` holds recipient-level details.
- An outer span marked `ERROR` is not enough to mark every message in the batch `NOT_SENT`.

If business logic requires per-recipient reconciliation, persist per-recipient submission outcomes or split messages per recipient. Never log `Bcc` recipients into logs or traces outside approved policy.

Never infer an entire batch's outcome from a single high-level exception.

## 34. Attachments and template rendering can be bottlenecks

For HTML emails with inline images and attachments:

~~~text
mail.notification.process
    |
    +--> mail.template.load
    +--> mail.template.render
    +--> mail.attachment.resolve
    +--> mail.mime.prepare
    +--> mail.smtp.submit
~~~

If file downloads are slow, `mail.smtp.submit` may stay short while total processing stretches. Instrument storage fetches, rendering, and MIME preparation when needed.

Attributes safer than raw content:

- Template key/version.
- Attachment count.
- MIME size bucket.
- Render duration.
- Provider category.
- Status/outcome.

Never write template variable values or filenames containing personal data into traces. If measuring attachment sizes by reading streams, avoid consuming non-repeatable input streams and leaving the MIME message empty on send.

## 35. In what order should you troubleshoot delayed mail?

A runbook:

1. Find the business aggregate/event ID.
2. Confirm the business transaction committed.
3. Locate the notification/outbox row.
4. Check `createdAt` and `nextAttemptAt`.
5. Check for suppression or consent decisions.
6. Compute queue wait.
7. Inspect worker claims, leases, and executor metrics.
8. Inspect template render and attachment spans.
9. Review all SMTP attempts and failure classes.
10. Check final responses or ambiguous outcomes.
11. If `SUBMITTED`, look up provider IDs and downstream events.
12. Cross-check metrics in the same time window for widespread outages or rate limits.

Do not start investigating SMTP when no outbox record exists yet. Also do not blame SMTP if a job was held for 10 minutes by a rate limiter before calling the sender.

## 36. Specific diagnostic scenarios

### A. Business event exists, but no outbox row

Check transaction rollbacks, repository inserts, deduplication keys, preference/suppression checks, event publication, and DB errors. An “event published” log does not prove the send intent was durably saved.

### B. Outbox stays PENDING for a long time

Check poller scheduling, `nextAttemptAt`, DB locks/leases, worker saturation, executor rejections, and provider cooldowns. Claim/poll traces are more helpful than SMTP traces because the sender was never called.

### C. PROCESSING with no SMTP span

Possible causes include renderer failures, crashed workers, trace sampling drops, disabled instrumentation, or unstarted tasks. **An absent span does not prove send never occurred.** Cross-check logs, outbox state, and server/provider evidence.

### D. SMTP read timeout

Identify the phase: before connect, `AUTH`, `RCPT TO`, or after `DATA`. When no final response arrives after `DATA`, mark `AMBIGUOUS` unless clear evidence says otherwise. Reconciliation beats blind retries.

### E. SUBMITTED, yet the user has not received the email

Inspect provider queue/message IDs, delivered/bounced/deferred events, spam/quarantine folders, and mailbox rules. Do not resend merely because the Inbox does not show it immediately.

### F. Trace ID lost after @Async

Check `TaskDecorator`/context propagation, MDC cleanup, sampling, worker trace policy, and notification IDs. Never propagate database transaction context across threads just to fix logs.

## 37. Testing tracing and correlation across the pipeline

An integration test can use GreenMail:

1. Create an order and invoke the real use case.
2. Let the transaction commit.
3. Assert the outbox record contains the notification ID.
4. Trigger the worker or poller under controlled conditions.
5. Wait for GreenMail to receive the message.
6. Assert subject, recipient, and correlation header if configured.
7. Verify outbox status is `SUBMITTED`.
8. Verify structured logs for enqueue, claim, and submit share the notification ID.
9. If using a test tracing handler, verify key span/observation names and tags.
10. Verify logs contain no passwords, bodies, or unnecessary personal data.

### Testing @Async propagation

Run tasks on a real executor to verify:

- Correlation ID appears in the worker with the expected value.
- Context propagation or new-trace linking works as designed.
- Task A does not leak MDC into Task B.
- Failures are still recorded when tasks run asynchronously.

### Testing retries

~~~text
Notification N-2105
  |
  +--> Attempt A1: temporary failure
  |       |
  |       v
  |    RETRY_WAIT
  |
  +--> Attempt A2: SUBMITTED
~~~

Expect the notification ID to stay constant, attempt IDs to differ, and outbox status plus attempt metrics to match.

### Testing provider events

- Only events with valid signatures are processed.
- Duplicate webhooks do not double-count metrics or state.
- Provider message ID links accurately to the notification.
- Webhooks can run in their own trace.
- Delivery status and submission status remain distinct.

You never need to send real Internet emails just to test tracing. An SMTP capture server validates transport tests, while provider integrations have separate contract tests.

## 38. Anti-patterns to avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `traceId` as `notificationId` | Unstable across retries/processes | Use a stable business ID |
| Logging only “mail sent” | Cannot tell enqueue/submit/deliver apart | Log explicit state transitions |
| Treating HTTP 200 as email delivered | Caller may only have enqueued | Separate milestones |
| Keeping spans open until provider webhooks | Huge spans, broken lifecycle | Trace webhooks separately |
| Forcing durable workers as children of old requests | Confusing trace relationships | Use span links and correlation IDs |
| Assuming MDC `TaskDecorator` is full trace propagation | Broken trace parenting | Use proper tracing APIs |
| Forgetting to clear MDC | Logs misattributed across jobs | Scoped/`finally` restore |
| Putting raw `Authorization` in baggage | Leaks secrets | Keep context minimal |
| Using recipient as span name | PII exposure and high cardinality | Use stable names |
| Using notification ID as metric label | High cardinality | Keep IDs in logs |
| Counting traces as exact email counts | Sampling undercounts | Use metrics and database state |
| Enabling SMTP debug across production | Exposes SMTP AUTH and MIME | Use controlled, scoped debug |
| Tracing only SMTP, ignoring queue wait | Misses pre-send delays | Measure poll/claim/render |
| Assuming exception means definitely unsent | Timeout after DATA may have been accepted | Use `AMBIGUOUS`/reconcile |
| Treating `Message-ID` as provider queue ID | Broken reconciliation | Store IDs separately |
| Marking `SUBMITTED` before `send` | Crashes drop emails silently | Update after actual outcome |
| Skipping webhook verification | Allows status spoofing | Verify signatures/auth + dedup |

## 39. Implementation roadmap

1. Assign a stable `notificationId` to each logical email.
2. Link business event IDs / aggregate IDs to the outbox.
3. Use a durable outbox if the workflow needs retries/recovery.
4. Add structured logs at enqueue, claim, render, submit, and status update.
5. Configure Micrometer Observation/Tracing and an exporter compatible with your Spring version.
6. Add stably named spans around key boundaries.
7. Choose context propagation when crossing into `@Async`/`TaskExecutor`.
8. For durable workers, prefer a new trace + span link and stable correlation ID.
9. Measure queue wait, render time, and SMTP duration separately.
10. Classify submission outcomes explicitly, including `AMBIGUOUS`.
11. Store provider queue/message IDs when a reliable source exists.
12. Integrate delivery/bounce webhooks with signature verification and deduplication.
13. Build dashboards/alerts for backlogs, timeouts, exhausted retries, and provider errors.
14. Govern sampling, cardinality, sensitive data, and retention.
15. Test the pipeline with an SMTP test server and a tracing test handler where appropriate.

~~~text
HTTP trace A
    |
    v
Business service + database transaction
    |
    v
Outbox row (notificationId=N-2105)
    |
    v
Worker trace B
    |
    +--> claim
    +--> render
    +--> smtp.submit
    +--> status update
    |
    v
Provider webhook trace C
    |
    +--> verify
    +--> dedup
    +--> correlate provider ID to N-2105
    +--> delivery state update
~~~

The three traces can be independent yet tied together through notification IDs, business event IDs, and provider IDs.

## 40. Key takeaways

- A mail pipeline spans business transactions, outboxes, workers, MIME preparation, SMTP, and provider events.
- Traces/spans reveal durations and relationships; database state remains the durable source of truth.
- `notificationId` stays constant across retries, `attemptId` changes, and `traceId` may differ across HTTP, worker, and webhook traces.
- Traditional SMTP does not automatically propagate W3C trace context to relays.
- Client-side observation of `JavaMailSender.send(...)` does not prove Inbox delivery.
- Only the final success reply after `DATA` proves the SMTP hop accepted submission; earlier replies are insufficient.
- Timeouts after `DATA` can be `AMBIGUOUS`, and retries carry duplicate risk.
- `@Async` requires deliberate context propagation; an MDC-only decorator is insufficient for every tracing stack.
- Outbox workers running hours later should generally start a new trace linked by IDs or span links.
- Structured logs keyed by `notificationId` matter when traces are sampled out or exporters fail.
- Never keep a span open for hours waiting on a delivery webhook.
- Measure queue wait, template render, and SMTP duration separately to pinpoint real bottlenecks.
- Use low-cardinality metric tags; keep recipients, subjects, and bodies out of telemetry.
- Never log SMTP passwords/tokens, MIME bodies, or raw AUTH transcripts.
- Tracing does not replace outboxes, idempotency, retry policies, or provider reconciliation.

**Core principle:** to trace from a business event to a mail server, do not merely wrap `JavaMailSender.send(...)` in one span. Maintain a correlation chain across **business event → outbox → worker attempts → SMTP submission → provider events**, using spans to see operations, logs to trace IDs, metrics to spot trends, and durable state to know accurately what the system did.

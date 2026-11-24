# Choosing Direct Sending vs. Using a Queue

## 1. The Architectural Decision Problem

In a **Spring Framework Mail** application, calling **JavaMailSender.send(...)** to send an email is relatively straightforward. The harder decision is **whether to invoke the send method directly on the business execution thread, or enqueue the send request for a worker to process later**.

For example, when a customer places an order:

~~~text
HTTP POST /orders
      |
      v
Create order
      |
      +-- Send confirmation email immediately?
      |
      +-- Or persist a notification job to send later?
~~~

Both approaches can be reasonable, but the difference is not merely **synchronous** vs. **asynchronous**:

- How long must the user wait for SMTP?
- Has the order already been committed when sending the mail?
- If the request succeeds but SMTP fails, how is it handled?
- If SMTP accepts and the application crashes, could a duplicate be sent?
- When the provider goes down, are business requests affected?
- How long can an email be delayed before losing its value?
- How does the system prove whether an email was created, attempted, accepted, or skipped?
- When a campaign generates hundreds of thousands of emails, will other transactional requests be throttled or blocked?
- Who is responsible for managing retries, quotas, state, alerts, and operational cost?

**Choosing between direct sending and a queue is a decision about business boundaries, reliability, and operations**, not just picking a Spring annotation.

In this article, "**direct sending**" primarily means calling the SMTP transport directly within the process serving a request or event. "**Via queue**" means persisting a send request into a queue or job store and letting an independent worker perform SMTP submission. A queue can be implemented using a database, a message broker, or a dedicated job service.

## 2. Two Fundamental Architectures

### A. Direct Sending Inside the Request

~~~text
Client
  |
  v
Spring REST Controller
  |
  v
Business Service
  |
  +-- Save business data
  |
  +-- Build MimeMessage
  |
  +-- JavaMailSender.send(...)
  |       |
  |       v
  |   SMTP provider
  |
  v
HTTP response
~~~

**Characteristics:** the result from the send method can be handled immediately to return a response, but the request must bear network latency, TLS, SMTP DATA, and provider timeout risks.

### B. Sending via Queue/Worker

~~~text
Client
  |
  v
Spring REST Controller
  |
  v
Business Service
  |
  +-- Save business data
  |
  +-- Enqueue notification intent
  |
  v
HTTP response

          Queue / Durable outbox
                   |
                   v
              Mail Worker
                   |
                   v
            JavaMailSender
                   |
                   v
              SMTP provider
~~~

**Characteristics:** the request does not need to wait for SMTP, but request success **does not mean the email has been sent**. The system must manage the state and outcome of the asynchronous job.

A common production variant is:

~~~text
Business transaction
    |
    +-- Update business entities
    +-- Insert email_outbox
    |
    v
Commit once
    |
    v
Outbox dispatcher -> Queue/broker -> Mail worker -> SMTP
~~~

The purpose of the outbox is to guarantee that **the send intent is persisted together with the business transaction**, not to guarantee exactly-once SMTP delivery.

## 3. Quick Comparison Table

| Criterion | Direct Sending | Sending via Queue |
|---|---|---|
| Implementation complexity | Low for simple needs | Higher, with workers and state |
| HTTP latency | Depends on SMTP provider | Primarily depends on the enqueue step |
| How results are surfaced | Can know SMTP submission outcome immediately | Initially only knows queued; updated later |
| During SMTP outage | Requests may slow down or fail | Can accept intents and retry later |
| Retries across process restarts | Must build custom persistence | Can be durable if queue/outbox is configured properly |
| Peak traffic | Easily creates many SMTP connections on request threads | Can buffer and throttle dispatch |
| Rate limiting | Needs throttling right on the request path | Easier to distribute quota/concurrency at workers |
| Sending order/priority | Depends on request arrival and threads | Can use priority/partitions/worker pools |
| History observability | Must add custom logging/DB | Usually has job/attempt state |
| Duplicate emails | Still possible on retry/timeout | Still possible on retry/redelivery |
| Operational cost | Usually low at small scale | Includes broker/DB queue, DLQ, monitoring, runbooks |
| Best fit | Low-volume, acceptable transport dependency | Critical workloads, high volume, recovery needed |

**A queue is not automatically better if you only switch to @Async or an in-memory QueueChannel**. A queue must be evaluated on durability, ownership, retry, and message acknowledgment semantics.

## 4. Do Not Equate HTTP Success with Email Delivery

There are at least four milestones:

~~~text
1. BUSINESS_COMMITTED
   -> Business data has been saved successfully

2. QUEUED / OUTBOX_PERSISTED
   -> Send intent has been stored for a worker to process

3. SMTP_SUBMITTED / ACCEPTED
   -> SMTP endpoint/provider has accepted the message

4. DELIVERY_CONFIRMED (provider-dependent)
   -> Provider records delivery on the hop it observes
~~~

A user may read the email seconds or minutes later, and even **SMTP acceptance does not guarantee the message lands in the primary inbox or is opened by the user**.

In the direct approach:

~~~java
mailSender.send(message);
~~~

returning normally usually only indicates that the submission operation succeeded according to the transport contract. That **is not proof that the recipient actually received and read the email**.

In the queued approach:

~~~text
HTTP 202 Accepted
{
  "notificationId": "N-100",
  "status": "QUEUED"
}
~~~

should only be understood as the system having **accepted the send request** under a specific guarantee level, and must not be phrased as "email sent successfully".

## 5. Questions to Answer Before Choosing

1. **Is the email a mandatory condition for the business operation to complete?** Or is it just a notification after the business operation succeeds?
2. **What is the maximum latency users can tolerate?** Especially for OTPs, login links, and security alerts.
3. **Is losing send intents after a process crash acceptable?**
4. **During an SMTP outage, should the business operation be allowed to proceed?**
5. **What are the average and peak volumes?** Are there burst campaigns or retry storms?
6. **Does the email have a deadline?** Is sending after expiration still useful?
7. **What level of audit is required?** Must you be able to answer why a recipient did not receive an email?
8. **Is a broker or database outbox infrastructure already in place?**
9. **How does the provider support API idempotency, delivery webhooks, and rate limits?**
10. **Does the operations team have the capacity to monitor backlogs, DLQs, reconciliation, and remediation?**

There is no single answer that fits every system. A small app sending a few test emails per day has different choices from a multi-tenant SaaS platform with millions of notifications.

## 6. When Is Direct Sending Appropriate?

Direct sending can be a reasonable choice if:

- Email volume is low, relatively steady, and bounded.
- Requests can tolerate SMTP latency with configured timeouts.
- Sending does not need to survive restarts, or the application already has a way to recover send intents.
- The email serves a standalone action such as an administrator's **test mail configuration**.
- The "check whether SMTP currently works" action genuinely needs immediate transport feedback.
- There are no strict SLA requirements for throughput, rate control, or backlog draining.
- Failures are surfaced honestly and the user can retry safely.

Example **Send Test Email**:

~~~text
Admin clicks "Test SMTP"
     |
     v
Spring API validates sender config
     |
     v
JavaMailSender.send(...)
     |
     +-- SMTP accepted -> show transport submission success
     |
     +-- Authentication/connection error -> show diagnostic
~~~

Here the primary need is **verifying whether the transport works at the moment of testing**. Direct sending gives more concrete feedback than just enqueueing and saying "request received".

Still, rate limiting, authorization, recipient allowlisting, and abuse controls are required; an SMTP test endpoint must not become a mass-mailing tool.

## 7. Direct Sending Does Not Mean Inside the Business Transaction

An anti-pattern:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(...);
    mailSender.send(buildConfirmation(order));
    return order;
}
~~~

Problems:

- The database transaction holds connections/locks while waiting for SMTP.
- If SMTP accepts and then the DB transaction rolls back, the user receives an email about an order that does not exist.
- If SMTP fails, the business operation might roll back even though the email is only a secondary notification.
- There is no atomic transaction between the DB and SMTP; rolling back the DB **cannot recall an email**.

Even if send is called inside a method annotated with @Transactional, the SMTP provider **does not participate in the JDBC transaction**.

If you still use direct sending for non-critical notifications, clearly define the business commit boundary and error handling. When losing a notification after commit is unacceptable, a **transactional outbox** is usually safer than merely sending after commit via an in-memory callback.

## 8. Sending After Commit: Better, but Still Has a Message-Loss Window

One technique is publishing an event and handling it:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreatedEvent event) {
    mailSender.send(...);
}
~~~

This avoids sending mail if the business transaction rolls back before commit. However, risks remain:

- The process crashes right **after DB commit** but **before the listener runs**.
- The listener runs, but an SMTP failure is not persisted for retry.
- If the listener is synchronous, latency can still sit on the transaction/request completion path.
- If `@Async` is added, the event may sit in an internal thread queue and be lost when the process stops.

**@TransactionalEventListener(AFTER_COMMIT) is not a durable transactional outbox.** It is a lifecycle event mechanism and does not replace a table recording send intents within the same transaction.

If missing a notification is acceptable, this technique may suffice. If notifications must be recoverable after a crash, durable intent is required.

## 9. When Is a Queue a Better Fit?

A queue or durable outbox is usually appropriate when:

- Email is a critical part of the user experience or business workflow.
- Business operations must still return HTTP responses quickly when the SMTP provider is slow.
- There is high sending volume, burst traffic, or scheduled campaigns.
- Retry/backoff, DLQ, suppression, unsubscribe, or per-tenant quotas are needed.
- Multiple services emit notifications and want to share the same mail pipeline.
- Status tracking is needed: queued → processing → submitted → delivery feedback.
- The impact of an SMTP outage needs to be isolated from the main API.
- Committed intents must be recovered after a process restart.
- Workers need to scale independently from HTTP instances.
- Multiple SMTP providers are used and failover control is required.

Example:

~~~text
Order Service      Billing Service       Support Service
      |                  |                      |
      +------------------+----------------------+
                         |
                         v
                    Durable queue
                         |
                         v
                 Central Mail Workers
                         |
             +-----------+-----------+
             |                       |
             v                       v
        SMTP Provider A         SMTP Provider B
~~~

This architecture enables centralizing policies, templates, security, and observability. However, you must decide whether **a single shared queue** could starve real-time emails when large marketing campaigns run.

## 10. Not All Queues Are Equal: Choose the Right Guarantee Level

| Mechanism | Durable Across Restarts? | Points to Understand |
|---|---|---|
| **@Async + TaskExecutor** | No by default | In-memory thread pool, no durable retry |
| **BlockingQueue/ExecutorService** | No | Data lost on JVM crash |
| **Default Spring Integration QueueChannel** | No by default | In-memory queue unless a persistent store is configured |
| **Database jobs/outbox** | Yes after commit | Needs atomic claim, indexes, retry, cleanup |
| **RabbitMQ durable queues + persistent messages** | Possible, depending on config and confirms | Must consider publisher confirms, consumer ACK, DLQ |
| **JMS durable/persistent messaging** | Possible, per broker/session configuration | Transaction/ack modes, reconnect, DLQ |
| **Kafka topic** | Possible per retention/acks/replication | Offset commits, duplicates, partition ordering |
| **Cloud task/queue service** | Per service contract | Visibility timeout, delivery count, DLQ, quotas |

All these tools can decouple the request from the sender, but **a durable queue does not equate to an exactly-once side effect on SMTP**.

A good architecture must specify: **where durability is stored, when the producer knows the job is accepted, who retries, and when the work is considered complete**.

## 11. Spring Boot Direct Sending Example

Suppose an API allows an administrator to send a configuration test email. Typical dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Example configuration via environment/secret manager:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

**Port 587 with STARTTLS is only a common example**; you must use your actual endpoint, TLS mode, authentication, and provider policy. The timeouts above are in milliseconds and do not guarantee that maximum total send time equals the sum of the three values. Do not log username/password or SMTP protocol traces containing tokens.

Service:

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TestEmailService {

    private final JavaMailSender sender;

    public TestEmailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendTest(String approvedRecipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("system@example.com");
        message.setTo(approvedRecipient);
        message.setSubject("SMTP configuration test");
        message.setText("This is a transport configuration test.");

        try {
            sender.send(message);
        } catch (MailException exception) {
            // Classify errors by cause/SMTP phase when needed;
            // do not assume every exception guarantees the mail was not sent.
            throw new TestEmailSubmissionException(exception);
        }
    }
}
~~~

**TestEmailSubmissionException** is an application-defined exception. The example focuses on direct submission and does not yet include authorization, `approvedRecipient` validation, rate limiting, or HTTP exception mapping.

Points to reflect in the API response:

- If send completes: **SMTP submission accepted** per contract.
- If authentication/configuration fails: surface an appropriate error without leaking credentials.
- If a timeout occurs after transmitting DATA: the outcome may be **ambiguous**; do not assert the email was not sent.
- Do not expose an endpoint to send mail to arbitrary addresses without permissions and rate limits.

## 12. Direct with MIME, HTML, and Attachments

Not every email is plain text only. With HTML and a file:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendInvoiceDirectly(
        JavaMailSender sender,
        String recipient,
        byte[] pdf
) throws MessagingException {

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");

    helper.setFrom("billing@example.com");
    helper.setTo(recipient);
    helper.setSubject("Your invoice");
    helper.setText(
            "Your invoice is attached.",
            "<p>Your invoice is attached.</p>"
    );

    helper.addAttachment(
            "invoice.pdf",
            new org.springframework.core.io.ByteArrayResource(pdf),
            "application/pdf"
    );

    sender.send(mime);
}
~~~

The snippet only illustrates MIME composition. Production requires **controlling recipients, invoice access permissions, file size, sensitive data, and retention**.

With large attachments, direct submission can significantly prolong the request:

~~~text
Database query -> render PDF -> load bytes -> SMTP DATA
~~~

If the API must respond quickly, decouple file generation and sending from the request, and store an **attachment reference** in the outbox instead of stuffing large files into a message broker.

## 13. @Async Is an Intermediate Option, Not a Durable Queue

Spring can execute mail-sending logic asynchronously:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendAsync(
            SimpleMailMessage message
    ) {
        mailSender.send(message);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

In Spring, you need to enable asynchronous method execution and configure a TaskExecutor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncMailConfiguration {

    @Bean("mailExecutor")
    public TaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.initialize();
        return executor;
    }
}
~~~

Limitations:

- Tasks reside in JVM memory; a process crash can lose pending send requests.
- An exceptionally completed **CompletableFuture** must be observed by the caller; returning HTTP and discarding the Future abdicates observability.
- **@Async** works via Spring proxies; calling an async method via **this.sendAsync(...)** within the same bean usually does not trigger interception as intended.
- Passing lazy JPA entities or request-scoped context to another thread can fail; pass immutable DTOs or durable references.
- If the queue is full, a rejection policy is needed. Do not increase capacity unboundedly just to avoid errors.
- If the email is important, `@Async` should be a **worker reading durable jobs**, rather than the sole place holding unsent messages.

**@Async reduces HTTP latency, but does not by itself guarantee against losing send intents.**

## 14. Why Just "Pushing to a Broker" Can Still Lose Notifications

Suppose:

~~~text
Order service:
    1. BEGIN transaction
    2. INSERT order
    3. COMMIT
    4. Publish SendEmail event to broker
~~~

If the process crashes between steps 3 and 4:

~~~text
Order already exists
Email event has not reached the broker
=> Lost notification
~~~

Reversing the order to publish before commit also has problems:

~~~text
Event published successfully
DB transaction rolls back
=> Email may be sent for a non-existent order
~~~

This is the **dual-write problem**: two different systems (database and broker) do not share a natural atomic commit.

A mechanism without distributed transactions should only offer guarantees that match reality. A **transactional outbox** usually solves creating the intent and business state in the same database.

## 15. What Part Does the Transactional Outbox Solve?

Within the **same database transaction**:

~~~sql
BEGIN;

INSERT INTO orders (...);

INSERT INTO email_outbox (
    id,
    business_event_id,
    notification_type,
    recipient_ref,
    status,
    created_at
) VALUES (
    :id,
    :eventId,
    'ORDER_CONFIRMED',
    :recipientRef,
    'PENDING',
    statement_timestamp()
);

COMMIT;
~~~

When the transaction commits:

- Both the order and the email intent exist together.
- On rollback, neither the order nor the intent exists.
- If the process crashes after commit, the outbox row can still be picked up by a worker.

Things the **outbox does not solve on its own**:

- Exactly-once SMTP sending.
- Whether the recipient still has consent or remains eligible when the worker processes it.
- Whether the template/attachment is still accessible.
- Provider quotas, outages, and retries.
- How to know whether a message was delivered or bounced.
- How to clean up/archive the outbox without losing required history.

The outbox shifts the problem from "not knowing if a send request existed" to "**having a durable record to process and reconcile**".

## 16. Two Ways to Implement an Outbox

### A. Database Outbox Is Also the Work Queue

~~~text
Order transaction -> email_outbox table
                            |
                            v
                       DB poller
                            |
                            v
                       Mail worker
                            |
                            v
                           SMTP
~~~

Pros: fewer components, easy to maintain atomicity at the producer, suited for moderate scale and minimal operations. Trade-offs: polling/claim/retry workload puts load on the database; must manage indexes, batching, and cleanup.

### B. Outbox Dispatcher Pushes to a Broker

~~~text
Order transaction -> email_outbox table
                            |
                            v
                     Outbox dispatcher
                            |
                            v
                      RabbitMQ/Kafka
                            |
                            v
                       Mail worker
                            |
                            v
                           SMTP
~~~

Pros: the broker helps distribute consumers, buffer, and decouple multiple mail workers. Trade-offs: **two layers of retry/dedup**, and you must get **publisher confirmations, event publishing idempotency, ack/offset, and broker retention** right.

In both models, **multiple deliveries of the same outbox event can happen**. Consumers must be idempotent on business state and recognize the true risk level with SMTP.

## 17. Illustrative Outbox Schema

PostgreSQL example:

~~~sql
CREATE TABLE email_outbox (
    id                UUID PRIMARY KEY,
    tenant_id         VARCHAR(120) NOT NULL,
    business_event_id VARCHAR(240) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    recipient_ref     VARCHAR(240) NOT NULL,
    template_version  VARCHAR(80) NOT NULL,
    payload_ref       TEXT NOT NULL,
    status            VARCHAR(40) NOT NULL,
    priority          SMALLINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL,
    next_attempt_at   TIMESTAMPTZ NOT NULL,
    expires_at        TIMESTAMPTZ,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    claim_token       UUID,
    lease_until       TIMESTAMPTZ,
    submitted_at      TIMESTAMPTZ,
    outcome_reason    VARCHAR(100),
    version           BIGINT NOT NULL DEFAULT 0,
    UNIQUE (
        tenant_id,
        business_event_id,
        notification_type,
        recipient_ref
    ),
    CHECK (attempt_count >= 0)
);

CREATE INDEX ix_email_outbox_due
ON email_outbox (
    priority DESC, next_attempt_at, id
)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

**This schema is an application example, not a table provided by Spring Mail.** It assumes `business_event_id` is specific enough to distinguish valid sends. For periodic digests/campaigns, a period/campaign version must be added; otherwise the unique key may accidentally block an email that needs to be sent in the next period.

**recipient_ref** can be an internal key instead of a raw email address to reduce PII exposure. The payload can be a reference to JSON and attachments in permission-controlled storage; the worker must verify tenant/context and retention when reading.

A production outbox typically needs **attempt history**, state transition audit, and other policy metadata depending on requirements.

## 18. Claiming Jobs Safely Across Multiple Worker Instances

Avoid doing:

~~~text
SELECT pending rows
for each row:
    send SMTP
    update status
~~~

Two pods could SELECT the same row and send two emails. With PostgreSQL, you can claim in batches using a short transaction:

~~~sql
WITH due_jobs AS (
    SELECT id
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= statement_timestamp()
      AND (
          expires_at IS NULL
          OR expires_at > statement_timestamp()
      )
    ORDER BY priority DESC, next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE email_outbox AS o
SET
    status = 'CLAIMED',
    claim_token = gen_random_uuid(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    version = o.version + 1
FROM due_jobs AS d
WHERE o.id = d.id
RETURNING o.id, o.claim_token, o.tenant_id,
          o.notification_type, o.recipient_ref;
~~~

**SKIP LOCKED** reduces lock contention across multiple workers, but it does not replace claim tokens and conditional state updates. The 2-minute lease is illustrative; choose it based on real latency/heartbeat/timeout. The UUID function must exist in the database or be replaced by an application-generated token.

After claiming:

1. Commit the claim transaction quickly.
2. Read the persisted payload.
3. Check tenant, consent/suppression, business relevance, and deadline.
4. Transition **CLAIMED → SENDING** conditionally with the claim token.
5. Perform SMTP submission **outside the transaction holding row locks**.
6. Record the result SUBMITTED/RETRY_WAIT/FAILED/UNKNOWN with the claim token.

If a row has already moved to another state, the worker must not drop the WHERE condition just to force an update.

## 19. Spring Scheduler Running a Database Queue

Spring Scheduling can wake the worker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class MailSchedulingConfiguration {
}
~~~

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxPollingJob {

    private final OutboxDispatchService dispatcher;

    public OutboxPollingJob(OutboxDispatchService dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelay = 1000)
    public void dispatchDueJobs() {
        dispatcher.dispatchBatch();
    }
}
~~~

**OutboxDispatchService** is an application-built service; it must implement atomic claim, worker concurrency, timeout, retry, and state handling. A 1-second fixed delay is not a default SLA; it only controls poll trigger frequency and can be delayed when work or the system is overloaded.

Running the same `@Scheduled` method across multiple instances may scan concurrently; use **DB claim/lease, distributed coordination, or sharding** depending on topology. Do not rely on a `synchronized` block that only works within a single JVM.

### @Scheduled Does Not Turn a Database into a Dedicated Queue

Database polling requires:

- Proper indexes matching the due-jobs query.
- Bounded batch size and limited transaction duration.
- Backoff when the DB is unavailable.
- Cleanup/archiving of terminal states.
- Metrics for oldest due age and claim lag.
- Protection against one tenant overloading all workers.

## 20. Worker Processing Emails via Interfaces with Clear Responsibilities

An abstraction:

~~~java
public record MailJob(
        String id,
        String tenantId,
        String notificationType,
        String recipientRef,
        String templateVersion,
        String payloadRef,
        String claimToken
) {
}

public enum SubmissionOutcome {
    ACCEPTED,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE,
    UNKNOWN
}

public interface MailJobStore {
    java.util.List<MailJob> claimDue(int maxJobs);
    boolean markSending(MailJob job);
    void markAccepted(MailJob job);
    void scheduleRetry(MailJob job, java.time.Instant nextAttempt);
    void markFailed(MailJob job, String reason);
    void markUnknown(MailJob job, String reason);
}
~~~

The code above as **application interfaces** shows the need to separate:

- **Claim and fencing token** belong to persistence.
- **Build MIME** belongs to template/message composition.
- **Send** belongs to the SMTP adapter.
- **Classify failures** belongs to retry policy.
- **State transitions** belong to the job store.
- **Metrics/audit** belong to observability.

If a worker mixes too much conditional code in a single method that accesses the DB, renders HTML, sends SMTP, retries, and logs, it becomes hard to control mid-step crashes.

## 21. Queue Delivery Is At-Least-Once in Many Designs

A message broker or database queue can redeliver a job when:

~~~text
Worker receives SendEmail N100
        |
        v
SMTP provider accepts email
        |
        v
Worker crashes before ACK / offset commit
        |
        v
Broker redelivers N100
        |
        v
Potential second SMTP submission
~~~

**Consumer ACK is not atomically coupled with SMTP provider acceptance.** Even if the broker supports transactions/idempotent producers, the SMTP server does not inherently participate in the broker's transaction.

Therefore you need:

- A **notification/recipient idempotency key**.
- Durable job state and attempt records.
- A rule to ACK/commit offset only after persisting the outcome.
- A policy for handling **UNKNOWN** outcomes.
- A provider API idempotency key if the service genuinely supports it.
- Reconciliation when the provider supports lookup.
- Acceptance of the reality that not all SMTP transports support exactly-once.

A queue prevents **losing pending work** when properly configured, but does not by itself prevent **duplicate send side effects** when a consumer gets redelivered.

## 22. Distinguishing Three Guarantee Levels Clearly for Product

| Guarantee Level | Interpretation | How Can It Be Achieved? |
|---|---|---|
| **Best effort** | Attempts to send; may be lost on process crash | Direct/in-memory async with minimal error handling |
| **Durable intent / at-least-once processing** | Send intent is persisted; worker retries on failure until a terminal outcome is reached | Outbox + claim + retry + audit |
| **Effectively-once business action** | Retries do not create duplicate business actions within a key scope | Unique constraint + idempotent handler + provider support/reconciliation |

"Exactly-once email delivery" is a very strong promise that usually **cannot be proven using Spring Mail and SMTP alone**.

Even two MIME emails with the same **Message-ID** do not guarantee that mail servers/recipients will deduplicate them. Message-ID helps threading/tracing, not a standard SMTP idempotency API.

### When Are Duplicates Still Acceptable?

An internal system alert might tolerate two rare duplicate emails. However:

- Duplicate invoices can cause confusion.
- Duplicate OTPs can cause confusion over which code is still valid.
- Financial emails with sensitive content sent to the wrong recipient are a serious risk.
- Duplicate marketing campaigns cause complaints/reputation loss.

Therefore, **duplicate tolerance** must be an input to the architectural decision, not merely a developer's technical preference.

## 23. SMTP Failures Can Be Transient, Permanent, or Ambiguous

Examples:

| Event | Likely Outcome | Action |
|---|---|---|
| DNS/connect fail before SMTP DATA | Not submitted, usually retryable if temporary | Backoff/retry within deadline |
| Authentication rejected | Not sent; usually config/token error | Fix credentials, avoid hot retries |
| SMTP 451 temporary failure | Temporarily rejected if reply is clear | Retry per provider policy |
| SMTP 550 5.1.1 invalid recipient | Usually permanent for recipient | Failed/suppression based on evidence |
| SMTP 5.7.1 policy reject | Possibly due to sender reputation/auth | Investigate, do not hard-suppress blindly |
| Timeout after DATA, no final reply seen | **UNKNOWN**: server may have accepted | Reconcile, do not auto-retry blindly |
| MailSendException with partial recipients | Some recipients were accepted | Track results per recipient |
| SMTP accepted but DB update fails | Email may have already gone out | Do not treat job as definitely unsent |

**Both direct and queued paths face these SMTP states.** A queue makes storing/transitioning state and retrying more convenient, but it does not make ambiguous outcomes disappear.

When building **MailRetryClassifier**, you must examine exception type, cause chain, SMTP status/enhanced code, timing of failure, and certainty of acceptance evidence. Do not retry every **MailException** the same way.

## 24. A Sensible State Machine for a Queue

~~~text
PENDING
    |
    v
CLAIMED
    |
    +-- policy changed --> SKIPPED
    +-- expired --------> EXPIRED
    |
    v
SENDING
    |
    +-- accepted --------> SUBMITTED
    +-- retryable -------> RETRY_WAIT
    +-- permanent -------> FAILED
    +-- ambiguous -------> UNKNOWN
                               |
                               v
                         RECONCILIATION
~~~

Some systems merge PENDING/RETRY_WAIT or use different names, but the semantics must be preserved:

- **PENDING**: intent recorded, not yet processed.
- **CLAIMED**: worker granted ownership.
- **SENDING**: SMTP attempt started or about to cross the side-effect boundary.
- **SUBMITTED**: evidence of SMTP acceptance exists.
- **SKIPPED**: a policy forbids sending or sending is no longer needed.
- **EXPIRED**: no new attempt may start after the deadline.
- **FAILED**: no further retries per evidence/policy.
- **UNKNOWN**: possibly sent, but outcome evidence is missing.

In the direct path, a similar state machine may still be needed if auditing/retrying is required; the main difference is **who runs the attempt and when information is persisted**.

## 25. Lease Expiration Does Not Mean the Email Was Not Sent

An example:

~~~text
Worker A claims N100
Worker A sends SMTP DATA
Worker A crashes before saving SUBMITTED
Lease expires
Worker B reclaims N100
~~~

If B immediately resends because the lease expired, the recipient may receive two copies.

Distinguish:

**CLAIMED, not yet entered SMTP:** can be reclaimed with evidence and deadline checks.

**SENDING, outcome not yet saved:** must treat as **UNKNOWN** and reconcile; do not simply reset to PENDING.

**Claim token/fencing** only protects database updates from a stale worker. It **cannot stop an old TCP connection** that has already started sending data to an external server.

Production models need attempt history and procedures for stuck SENDING states. "Which worker owns DB updates?" and "Could the email already have been accepted?" are two different questions.

## 26. When Should Broker ACK Occur?

A simple consumer architecture:

~~~text
Receive queue message
       |
       v
Claim/lookup durable notification state
       |
       v
Apply policy + SMTP attempt
       |
       v
Commit durable outcome
       |
       v
ACK message
~~~

If ACK happens **before** a durable outcome is persisted, a worker crash after ACK can lose the job (unless another outbox/DB scanner exists).

If ACK happens **after** the outcome commits, a crash between commit and ACK can cause broker redelivery. Therefore:

1. The consumer must be **idempotent** when seeing a job already in SUBMITTED/SKIPPED/FAILED.
2. If the outcome is still UNKNOWN, the consumer must not assume it was unsent.
3. SMTP retries and broker retries must follow **one unified policy**, avoiding two independent retry loops creating a storm.
4. Poison messages must go to DLQ/quarantine per proper rules without blocking the entire partition/queue.

ACK/offset commit semantics depend on the broker. Do not apply an imaginary single form of ACK identically to RabbitMQ, JMS, and Kafka.

## 27. RabbitMQ Consumer Example via Spring AMQP

If the system already has RabbitMQ, Spring AMQP lets you register a consumer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example consumer receiving only a **job ID**, not the entire MimeMessage:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
import java.util.UUID;

@Component
public class QueuedMailConsumer {

    private final MailDeliveryOrchestrator orchestrator;

    public QueuedMailConsumer(
            MailDeliveryOrchestrator orchestrator
    ) {
        this.orchestrator = orchestrator;
    }

    @RabbitListener(queues = "mail.send.jobs")
    public void onMessage(String notificationId) {
        orchestrator.process(UUID.fromString(notificationId));
    }
}
~~~

**MailDeliveryOrchestrator** is an application service with durable state, claim/dedup, retry, and policy; it is not a Spring class. The example uses a minimal listener style; **auto/manual ACK, prefetch, consumer concurrency, retry advice, DLQ, and publisher confirms** must be configured per project requirements.

If the orchestrator throws an exception, requeue/ACK behavior depends on the listener container and error handler. Do not infer from this example that the broker always retries properly or always prevents lost mail.

### Why Pass Only notificationId?

- Avoids oversized queue messages caused by HTML/attachments.
- Reduces PII exposure in broker logs/management UI.
- Worker reads template/payload version and tenant policy from a trusted source.
- Enables replay and reconciliation using the same ID.

If the message carries correlation metadata, you still must **verify** the tenant/notification mapping from the DB, rather than blindly trusting a tenantId injected into headers by an untrusted producer.

## 28. How Should Kafka Be Used Differently from RabbitMQ?

Kafka fits when the system already uses event streaming and multiple distinct consumers want to read business events. However, a **Kafka topic is not inherently a delayed-job queue**.

Example:

~~~text
OrderCreated event (Kafka topic)
      |
      v
Notification intent consumer
      |
      v
Dedup + insert email_outbox
      |
      v
Mail dispatcher with next_attempt_at
      |
      v
SMTP
~~~

Considerations:

- **Partition ordering** applies only within a partition; there is no global ordering.
- When one message fails, blocking the partition can stall many events behind it.
- **Kafka retry topics** or a retry scheduler must be designed explicitly for long backoffs and deadlines.
- Kafka consumer offset commit **does not atomically commit the SMTP side effect**.
- Kafka producer idempotence/transactions do not automatically make SMTP sends exactly-once.
- Events can be replayed within the retention window; consumers must be idempotent.
- Notification intent sometimes needs to live longer than a topic's retention, so an outbox database remains useful.

If the goal is just sending a few periodic emails, standing up an entire Kafka cluster merely because "we must use a queue" is usually cost- and operations-inefficient.

## 29. Database Queue vs. Broker: The Second Decision After Direct/Queued

| Criterion | Database Jobs | Broker-Backed Queue |
|---|---|---|
| Additional infrastructure | Uses existing DB | Separate broker/service |
| Transaction with business DB | Easy when in the same database | Needs outbox/CDC or another mechanism |
| Claim/due-job query | SQL + indexes/leases | Broker dispatch + retry scheduling |
| Backpressure | DB polling/batch limits | Prefetch, consumer concurrency, broker limits |
| Latency | Poll interval and DB load | Event push is usually fast, topology-dependent |
| Long retry delays | `next_attempt_at` is natural | Needs delay queue/plugin/retry topology per broker |
| Priority ordering | ORDER BY/partitioning | Priority queues or multiple queues |
| Scaling throughput | Up to DB/lock limits | Scale consumers/broker by architecture |
| Observability | SQL/job ledger | Broker metrics + job ledger |
| Cost | Added load on primary DB | Broker ops/cost + connections |

A **database queue** is usually sufficient for moderate email volume, non-extreme SLAs, and an already reliable relational DB.

A **broker** fits better when fan-out, high throughput, decoupling multiple services, or standardized message processing infrastructure is already present.

If using a broker still requires writing an outbox to avoid dual-write, factor in the total complexity of **both layers**.

## 30. Latency: Direct Is Faster to "Start Sending", Queue Is Faster on HTTP

Intuitions that "direct is always fast" or "queue is always fast" lack context. You must specify **where you measure**.

Example:

~~~text
Direct:
  HTTP + business logic  60 ms
  MIME preparation       20 ms
  SMTP submission       900 ms
  ----------------------------
  HTTP response          980 ms

Queue:
  HTTP + business logic  60 ms
  Persist outbox         20 ms
  ----------------------------
  HTTP response           80 ms

  Queue wait             200 ms
  MIME preparation        20 ms
  SMTP submission        900 ms
  ----------------------------
  SMTP accepted ~1.2 s from request
~~~

These are **illustrative hypothetical numbers**, not Spring Mail benchmarks.

In the example:

- Queue yields **lower HTTP latency**.
- Direct can get the email to SMTP sooner because there is no worker wait.
- Queue can simultaneously protect request threads when the provider is slow.

For OTPs, what matters may be **time-to-SMTP-accepted** or **time-to-delivery**, not just API response time. A queue backed up by 5 minutes is unacceptable for OTPs even if the API returns in 80 ms.

### Three Latencies to Measure

~~~text
API latency =
    response_at - request_received_at

Queue wait =
    attempt_started_at - intent_committed_at

SMTP submission latency =
    submission_result_at - attempt_started_at
~~~

Afterward, if the provider offers webhooks, also measure **provider delivery feedback latency** according to the accuracy of their data.

## 31. Queues Buffer Bursts, Not Create Infinite Throughput

Suppose:

~~~text
Campaign produces: 10,000 emails/minute
Provider allows:    2,000 recipients/minute
~~~

If traffic stays constant, backlog grows by roughly **8,000 recipients/minute**, even with workers running at maximum capacity.

An estimate:

\[
\text{Backlog growth rate} \approx \lambda - \mu
\]

Where:

- \(\lambda\): rate of valid notification creation.
- \(\mu\): actual processing rate, bounded by the SMTP provider, CPU, I/O, quotas, and workers.

When \(\lambda > \mu\) continuously, a queue only **defers pressure into the future**. The system needs admission control, campaign scheduling, rate limits, capacity planning, or workload reduction/shaping.

An example calculation:

~~~text
Backlog = 48,000 recipients
Effective sending rate = 1,600 recipients/minute

Minimum drain time ~= 30 minutes
~~~

That is an estimate under steady rate conditions, with no new jobs, retries, or provider outages. In practice, it can take longer.

**Do not solve overload by opening 500 SMTP connections if the provider only allows a small quota**; higher connection counts can increase throttling, timeouts, and complaint risk.

## 32. Backpressure and Per-Tenant Quotas

A multi-customer SaaS system:

~~~text
Tenant A: 100,000 marketing emails
Tenant B: 20 password-reset emails
Tenant C: 500 invoice emails
~~~

If all share a single FIFO queue and an unclassified pool, a marketing backlog can slow down critical emails.

Mechanisms:

- **Per-stream queues**: security, transactional, marketing.
- **Reserved worker capacity** for short-deadline emails.
- **Per-tenant rate limits** and fairness.
- **Per-provider concurrency cap**.
- **Bounded in-flight** jobs instead of spawning unbounded threads.
- **Deadlines** and skipping emails that have lost value.
- **Admission control** before a campaign generates millions of jobs that cannot be sent on time.
- A separate **retry budget** so a provider outage does not let retries consume all workers.

However, do not allow callers to self-assign **priority=SECURITY** without validation. Otherwise, every tenant could bypass quotas simply by changing a label.

## 33. Queue Ordering: Do Emails Need to Be Sent in Order?

Not all emails are independent.

For example, a user changes their password:

~~~text
Event 1: Password changed
Event 2: Security alert acknowledged
~~~

Or an order:

~~~text
Event 1: Order confirmed
Event 2: Order shipped
~~~

If workers process in parallel, the **Order shipped** email might be sent before **Order confirmed**.

Some options:

1. Accept out-of-order delivery if the content is self-contained with full context.
2. **Sequence numbers** per business aggregate/recipient and gate only when truly necessary.
3. Partition/serialize per recipient or business key, trading off throughput.
4. Coalesce notifications or suppress obsolete emails to reduce noise.
5. Include timestamps/current status fields in the content to avoid confusion.

**Queues do not guarantee global order by default.** RabbitMQ, Kafka, and database workers have different semantics; even when a broker guarantees order within a partition/queue, multiple consumers, retries, and DLQs can reorder side effects.

If strict ordering is not required, do not force serialization across all emails of every tenant just to avoid a rare edge case.

## 34. Deadlines: Is a Late Email Still Valid?

A queue can hold a job until the provider recovers. But sending late is not always right:

| Email | If Delayed | Potentially Appropriate Decision |
|---|---|---|
| OTP | Token may have expired | EXPIRED, do not send a useless code |
| Password reset | Link expires per TTL | Skip or create a new verified intent |
| Meeting reminder | Event already started/ended | Skip |
| Promotional campaign | Offer is no longer valid | Skip |
| Payment reminder | Order may already be paid | Revalidate business state |
| Invoice | Usually still obligated to send | Retry with SLA, do not drop arbitrarily |
| Security alert | May still need late delivery, but content must be accurate | Revalidate severity/status |

In the outbox:

~~~text
scheduled_at = desired send time
next_attempt_at = time when retry/worker is allowed to pick up
expires_at = deadline after which no new submission starts
~~~

Workers must check the deadline **before claiming and right before starting the SMTP attempt**. A periodic expiration scanner can mark pending jobs, but must not be the sole safeguard because the scheduler can lag.

**Do not turn an already SUBMITTED email into EXPIRED_NOT_SENT** just because the deadline passed after SMTP accepted it.

## 35. Policy Changes While an Email Is Waiting

Example:

~~~text
08:00  Create marketing notification N100
08:30  User unsubscribes
09:00  Worker would send N100
~~~

If the worker uses a consent snapshot stored in the message at enqueue time, it may send against the user's new choice.

Before SMTP, check:

- Does the recipient belong to a valid tenant?
- Is the address hard-bounce suppressed or complained?
- Has the recipient unsubscribed from the corresponding list/stream?
- Is the business event still valid?
- Was the campaign canceled/paused?
- Are the template and attachment versions still permitted?
- Is the notification still within its sending window and deadline?

A previously **PENDING** job can still transition to **SKIPPED** when its turn comes if a new policy forbids sending.

Do not rely solely on a TRANSACTIONAL label to bypass all suppression or security requirements; classification must be based on actual business substance.

## 36. Multiple Recipients: One Message or Multiple Jobs?

If a MimeMessage has three recipients:

~~~text
To: A@example.net
Cc: B@example.net
Bcc: C@example.net
~~~

SMTP can accept some recipients and reject the rest. In that case, a job tied to three recipients must track **per-recipient results** to retry properly.

Two architectures:

**One notification/job for multiple recipients**

- Fewer jobs, can share MIME rendering.
- Requires understanding partial SMTP acceptance and mapping each envelope recipient.
- Easy to introduce security bugs when Bcc, tenants, or personalized content are involved.

**One notification-recipient/job per recipient**

- Easy to apply separate unsubscribe/suppression, retry, deadline, and idempotency.
- Easy to store delivery/bounce outcomes per recipient.
- Increases job count and submissions, requiring batch/rate management.

For personalized, security, or multi-tenant emails, **one job per recipient** is usually simpler for permission boundaries and observability. For internal alerts to a small group, one message with multiple recipients can make sense if policy and privacy allow.

## 37. Where Should Attachments Live?

Avoid stuffing an entire 20 MB PDF into every queue message:

~~~text
Queue message:
  notificationId
  tenantId
  attachmentUrl with raw token
  entire PDF bytes
~~~

This easily inflates broker storage, network traffic, and token/data exposure risk.

A smaller message:

~~~json
{
  "notificationId": "N100",
  "schemaVersion": 2
}
~~~

The worker reads the outbox to fetch:

~~~text
tenant_id
recipient_ref
template_version
payload_ref
attachment_object_refs
authorization context
~~~

Object storage:

- Use system-generated keys.
- Protect with tenant scoping/least privilege.
- Keep retention longer than the maximum retry window.
- Do not issue signed download links that expire before the worker's turn.
- Validate checksum/size/content type when needed.
- Do not log contents or signed URLs containing tokens.

If an attachment is generated after outbox commit, you need a **PREPARING/READY** state and reconciliation; do not claim a send job before the data it requires is durably persisted.

## 38. Should Templates Be Rendered at Enqueue Time or Send Time?

Two options:

| Approach | Benefits | Risks |
|---|---|---|
| **Render at enqueue** | Content reflects a snapshot at the moment of the business event; stable audit | Large HTML/raw MIME, attachments not ready yet, does not reflect new policies |
| **Render at worker** | Fast request, uses worker resources, can reflect current content | Template changes between enqueue/send, references no longer exist |

A hybrid model:

~~~text
Outbox:
  template_id = order-confirmation
  template_version = v5
  safe_input_snapshot_ref = object://...
  business_event_id = ...
~~~

The worker uses the **pinned template version** and sufficient data snapshot to build the content, while **revalidating send permissions** and business conditions that may have changed.

Do not render from a live current entity without recognizing that its content may differ from the original event. For example, an order confirmation may need to reflect the price/address at order placement time, not data edited the next day.

### When to Store Raw MIME?

If you need to replay the exact originally sent content, you can store **raw MIME/reference** after composition with clear retention/security controls. Even then, understand that replaying the same MIME differs from replaying the same business action; duplicate sends can happen, and Message-ID does not guarantee mail server dedup.

## 39. API Contracts Differ Between Direct and Queued

With direct, an endpoint can respond based on the immediate SMTP result:

~~~text
POST /admin/test-email
    |
    +-- Submission accepted -> 200/appropriate success
    |
    +-- Known failure -> appropriate error
    |
    +-- Ambiguous timeout -> accepted status uncertain
~~~

With queued, the endpoint should return a **tracking ID**:

~~~http
POST /orders/ORD-100/notifications
Content-Type: application/json

{
  "kind": "ORDER_CONFIRMATION"
}
~~~

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "notificationId": "N100",
  "status": "QUEUED"
}
~~~

Then, a status endpoint:

~~~http
GET /notifications/N100
~~~

~~~json
{
  "notificationId": "N100",
  "status": "SUBMITTED",
  "lastAttemptAt": "2026-11-12T10:20:00Z",
  "deliveryStatus": "UNKNOWN"
}
~~~

Do not display **DELIVERED** if you only know SMTP accepted. An API must check tenant/user authorization before returning notification status, because metadata can reveal recipient addresses and business events.

### Asynchronous Also Needs Producer Idempotency

If a client resends the same request after an HTTP timeout:

~~~text
POST create notification -> DB commit
HTTP response lost
Client retries POST
~~~

The system needs an idempotency key or unique business intent key so it does not create two notification jobs. Queue consumer idempotency cannot fix a producer creating two separate intents without a domain key.

## 40. Example Service Writing Outbox Together with Business Logic

Illustrative interfaces:

~~~java
public record CreateOrderCommand(
        String customerId,
        String productId,
        int quantity
) {
}

public interface OrderRepository {
    Order saveNew(CreateOrderCommand command);
}

public interface MailOutboxRepository {
    void insertOrderConfirmation(
            String tenantId,
            String eventId,
            String orderId,
            String recipientRef,
            java.time.Instant createdAt
    );
}
~~~

Service:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox,
            Clock clock
    ) {
        this.orders = orders;
        this.outbox = outbox;
        this.clock = clock;
    }

    @Transactional
    public Order createOrder(
            String authenticatedTenantId,
            CreateOrderCommand command,
            String idempotentEventId
    ) {

        Order order = orders.saveNew(command);

        outbox.insertOrderConfirmation(
                authenticatedTenantId,
                idempotentEventId,
                order.id(),
                order.customerRecipientRef(),
                Instant.now(clock)
        );

        return order;
    }
}
~~~

**Order**, **OrderRepository**, and **MailOutboxRepository** are application abstractions. The example assumes both repositories share the **same Spring transaction manager and the same database**; if the outbox is in a different DB, `@Transactional` does not automatically create an atomic commit across both stores.

Production details still needed:

- Verify tenant/order/customer before saving.
- Validate quantity and business invariants.
- Prevent duplicate order creation on request replay.
- Unique constraint on `idempotentEventId`/notification intent.
- Select template version and persist an appropriate input snapshot.
- Do not put sensitive personal data into logs.

Main advantage: **no SMTP command runs inside the order creation transaction**.

## 41. One Code Path, Multiple Transports: Avoid Ad-Hoc Fallback

An anti-pattern:

~~~text
Try queue.publish(notification)
      |
      +-- broker down
              |
              v
        mailSender.send(...) directly
~~~

Problems:

1. Publish may have succeeded on the broker while the response to the producer was lost.
2. The producer sees a timeout and sends directly, while the broker still holds the message.
3. A worker later sends a second copy.
4. Retry, suppression, quota, and metrics of the direct fallback may differ from the worker pipeline.
5. The business API gets prolonged by an SMTP outage even though queued was originally chosen for isolation.

If failover is needed, **fallback must be based on a single durable intent ID and shared coordination state**, not calling SMTP ad-hoc just because of a queue publish exception.

A safer design:

~~~text
Durable outbox -> Queue available?
                      |
                 +----+----+
                 |         |
                Yes        No
                 |         |
                 v         v
              Broker   Outbox remains PENDING
                           |
                           v
                    Dispatcher retries later
~~~

Only when an explicit hot-standby architecture with fencing/idempotency and tested boundaries exists should you consider multiple active dispatch routes in parallel.

## 42. Circuit Breakers, Timeouts, and Provider Outages

Direct:

~~~text
SMTP provider unavailable
      |
      v
HTTP request thread waits / errors
      |
      v
Potential request backlog and thread exhaustion
~~~

Queued:

~~~text
SMTP provider unavailable
      |
      v
Worker attempts fail
      |
      v
Retry/backoff, circuit breaker, queue backlog
      |
      v
Business API can continue accepting valid intents
~~~

A queue helps **isolate failures** but requires bounds:

- Finite connection/read/write timeouts.
- Per-provider retry budget.
- Exponential backoff with jitter.
- Circuit breaker to avoid piling on requests while the provider consistently fails.
- Bounded worker concurrency.
- Backlog alerts and maximum retention/deadlines.
- Authorized manual pause/resume.
- Policy-driven provider failover, without blindly retrying for double sends when the outcome is UNKNOWN.

**A circuit breaker does not mean dropping every new email.** When the circuit is open, the system can hold durable intents for retry, but must reject/throttle producers if the backlog exceeds capacity or emails expire.

## 43. Retry Policy: Do Not Retry Every Spring Mail Error

A classifier:

~~~java
public enum RetryDecision {
    RETRY_LATER,
    FAIL_PERMANENTLY,
    RECONCILE_UNKNOWN,
    STOP_EXPIRED
}
~~~

Logical policy example:

~~~text
if SMTP acceptance is ambiguous:
    RECONCILE_UNKNOWN

else if business deadline passed:
    STOP_EXPIRED

else if error is transient and attempts < maxAttempts:
    RETRY_LATER

else:
    FAIL_PERMANENTLY
~~~

Do not use:

~~~java
@Retryable
public void sendMail(...) {
    mailSender.send(...);
}
~~~

without classification, attempt limits, deadlines, and outcome tracking. A timeout after DATA may have been accepted, so automatically retrying every exception can cause duplicate sends.

Configuration errors such as **MailAuthenticationException** are usually not resolved by retrying every second with the same credentials. Open the circuit/alert/run a credential refresh procedure.

### Retries Should Have Durable State

If retries live only in an interceptor or sleep loop, a process crash loses the retry schedule. For important notifications, persist:

~~~text
attempt_count
last_error_category
next_attempt_at
expires_at
provider_profile
outcome
~~~

On crash/restart, the new scheduler knows when to try next. An email affected by an unsubscribe policy before `next_attempt_at` must become SKIPPED, not retried against a stale snapshot.

## 44. SMTP Provider Failover and Duplicate Send Risk

Some businesses want:

~~~text
Primary SMTP provider fails
       |
       v
Try Secondary SMTP provider
~~~

This can improve availability **if you know for sure the primary did not receive the message**. However, when the primary times out on the final reply:

~~~text
Primary may have accepted
Secondary then accepts
=> Potential duplicate deliveries
~~~

Classify accordingly:

| Primary State | Can Use Secondary? |
|---|---|
| Connect refused before SMTP session | Possible per failover policy |
| Authentication/config error | Must verify sender policy/credentials |
| Known recipient rejection | Do not switch providers to bypass recipient policy |
| Known temporary provider outage | Can use secondary per quota and deadline |
| UNKNOWN after DATA | Needs reconciliation/duplicate-risk policy |
| Primary accepted | Do not resend merely because no delivery webhook arrived yet |

Switching providers also changes SPF/DKIM/DMARC setup, bounce routing, quotas, and domain reputation. **Failover must be a pre-deployed and tested plan**, not editing an SMTP property on a singleton sender during an outage.

## 45. Security and Authorization in Queues

A job may contain:

- Tenant ID.
- Recipient email/address reference.
- Order ID/ticket ID.
- Template data.
- Attachment object key.
- URLs containing tokens.
- Sender profile ID.

If you put the entire payload into the message broker:

- Broker management UI may expose PII to operators.
- Consumer/proxy logs may record full messages.
- Retry/DLQ may retain data longer than primary retention.
- A compromised consumer could read data belonging to unauthorized tenants.

Use:

1. **Minimal message schema**, preferring `notificationId`.
2. ACL/network/TLS for the broker.
3. Authentication/authorization between producers and consumers.
4. Tenant-scoped reads when the worker fetches payloads.
5. Appropriate encryption and secret management.
6. Redacted structured logs; do not log raw MIME/access tokens.
7. Controlled retention and DLQ cleanup.
8. Never pass credentials/sender passwords inside payloads.
9. Verify that the sender profile is authorized for the tenant.
10. Never use raw external input to construct arbitrary dynamic routing destinations/queue names.

**Async does not make data inherently safer than direct**; it adds storage and access surfaces, so it requires its own security design.

## 46. Updating Consent, Bounces, and Recipient State

A queued pipeline is also subject to signals arriving **after the job was created**:

~~~text
Notification created 08:00
Provider hard bounce received 08:30
Worker processes notification 09:00
~~~

The worker must evaluate suppression at 09:00, not use the information from 08:00.

A send gate may return:

~~~text
ALLOW
SKIPPED_UNSUBSCRIBED
SKIPPED_HARD_BOUNCE
SKIPPED_BUSINESS_OBSOLETE
EXPIRED
DEFERRED_PROVIDER_QUOTA
DENIED_TENANT_POLICY
~~~

If ineligible to send, transition the job via a **durable state transition** instead of calling SMTP or merely logging "skipped".

Do not lump SKIPPED due to unsubscribe into MailSendException or SMTP failure metrics. A valid business skip is not a transport failure.

With multiple recipients, evaluate per recipient when states differ.

## 47. Operational Cost and Total Complexity

A relative comparison:

| Cost | Direct | Queued with DB | Queued with Broker |
|---|---|---|---|
| Initial coding | Low | Moderate | Moderate/high |
| Intent storage | As needed | DB rows/indexes | Broker + usually also outbox |
| Monitoring | SMTP/API | Scheduler, rows, attempts | Plus broker queues/DLQ/offsets |
| Failure recovery | Usually manual if unpersisted | Has job ledger | Has broker retry + ledger |
| Worker scaling | Coupled to API threads | Separate batch/workers | Separate consumer pools |
| Infrastructure | Minimal | Existing DB | Additional cluster/managed service |
| Data retention | Minimal if unlogged | DB cleanup/archive | Also needs broker/DLQ retention |
| On-call complexity | Low at small volume | Moderate | Higher with complex topology |

A system sending 100 emails/day without durable intent requirements may not need a broker.

A system sending 500,000 emails/day with SLAs, bounce policies, marketing/transactional streams, and multiple tenants is hard to operate safely if every request calls SMTP directly.

**Evaluate total lifecycle cost**, including operational failures, downtime, manual replays, and user support—not just initial lines of code.

## 48. Architecture Selection Matrix by Scenario

| Scenario | Typically Appropriate Choice | Rationale |
|---|---|---|
| Admin clicks "Test SMTP connection" | **Direct** | Needs to wait for transport result to report immediately |
| Prototype sending a few non-critical emails/day | **Direct or best-effort async** | Simple, with clearly accepted risk |
| Order confirmation requiring audit and no lost intent | **Transactional outbox + worker** | Commits intent with order and is recoverable |
| Sending invoices with attachments requiring reconciliation | **Durable queue/outbox** | Needs retention, retry, per-recipient outcome |
| Marketing campaign to hundreds of thousands of users | **Queue + rate control/stream isolation** | Buffers bursts, quotas, unsubscribes, provider feedback |
| Short-TTL password reset/OTP | **Priority durable queue or controlled direct** | Needs end-to-end latency and deadline, not just fast HTTP |
| Critical security alert | **Durable intent + priority/secondary channel** | Should not lose alerts during temporary provider errors |
| Periodic digest reports | **Outbox/scheduler** | Misfire policy, per-period idempotency, conditional catch-up |
| A REST endpoint sending mail on behalf of tenants | **Queue when multi-tenant or high rate** | Isolates quotas, abuse, sender profiles, observability |
| Provider supports native scheduled send API | **Can combine local outbox + provider schedule** | Must track cancellations, status, and provider limits |

**These are considerations, not mandatory rules.** OTPs may need direct sending if the system lacks a sufficiently fast/reliable queue; conversely, many large apps send OTPs through a low-latency priority queue with a durable outbox.

### An Option Selection Example

A mid-sized e-commerce application has:

~~~text
Peak HTTP requests: 1,000 req/min
Order confirmation: 50 messages/min
Digest: 20,000 messages/night
SMTP provider: strict rate limit
Need audit for invoices
~~~

One option:

- Order confirmation and invoices: create durable intents in the business transaction.
- Digest: scheduler creates periodic intents using a separate marketing/digest queue.
- Workers enforce quotas/provider token buckets.
- OTP/security: priority pool with deadlines and queue-lag alerts.
- Admin SMTP test: direct endpoint with authorization/rate limiting.

You do not have to force every email type into the **same delivery mechanism** if SLAs and risk profiles differ; however, share the same **policy/transport abstraction** to avoid diverging security rules.

## 49. A Simple Decision Tree

~~~text
Is the email only an SMTP/transport test needing an immediate result?
      |
      +-- YES --> Direct with strict timeout, rate limit
      |
      +-- NO
            |
            v
After business commit, is losing the send intent acceptable?
      |
      +-- YES --> Direct after commit / @Async best effort
      |           (with clear awareness of process crash risk)
      |
      +-- NO
            |
            v
Is an atomic commit with business data required?
      |
      +-- YES --> Transactional outbox
      |
      +-- NO  --> Durable queue accepted as source of truth
            |
            v
Does the workload need independent scaling / is a broker already available?
      |
      +-- YES --> Outbox + broker/consumers as needed
      |
      +-- NO  --> Database outbox polling worker
            |
            v
Does the email have deadlines, priority, consent, quotas?
      |
      +-- YES --> Implement eligibility/admission + policies
      |
      +-- NO  --> Still define retry + outcome + monitoring
~~~

In practice, branches are not strictly linear. For instance, a project may have a durable broker while business data lives in another system and the producer has its own transactional event store. In that case, describe the exact consistency boundary rather than assuming every place must create the exact same table.

**The foundational question remains: "When the application claims it has accepted responsibility for sending, is there a durable record proving that responsibility?"**

## 50. Hybrid Strategy: Direct for Some Tasks, Queue for the Rest

A pragmatic architecture:

~~~text
Spring Application
       |
       +-- Admin SMTP diagnostic
       |      |
       |      v
       |   Direct sender
       |
       +-- Business notifications
       |      |
       |      v
       |   Durable outbox + mail worker
       |
       +-- Large marketing campaigns
              |
              v
         Campaign scheduler
              |
              v
         Rate-limited mail queues
~~~

These paths should still share:

- **Sender profile registry**: tenant, from domain, SMTP credentials.
- **Template/versioning policy**.
- **Recipient authorization/consent/suppression**.
- **MIME composition security**.
- **SMTP transport timeouts and error classification**.
- **Correlation/telemetry**.

If the same email could be sent via direct or queued depending on runtime state, there must be **idempotent job ownership**. Do not enable ad-hoc fallback for direct to "rescue" the queue on ambiguous broker timeouts.

### An Abstraction to Preserve Boundaries

~~~java
public interface NotificationDispatcher {
    DispatchReceipt requestSend(NotificationCommand command);
}

public record DispatchReceipt(
        String notificationId,
        String acceptedState
) {
}
~~~

One implementation can write to the outbox; another only sends directly for test emails. Their interfaces must not conflate semantics: **Direct submission accepted** differs from **Queued intent accepted**.

## 51. Migrating from Direct to Queue Step by Step

A system currently calling SMTP inside controllers can migrate in phases:

### Phase 1 — Measure the Current Baseline

- HTTP p50/p95/p99 latency when SMTP is normal and when slow.
- SMTP attempt duration/errors/timeouts.
- Email counts by business event, tenant, and provider.
- Number of duplicate requests caused by user retries.
- Cases where business transactions roll back after SMTP accepted.

### Phase 2 — Abstract the Send Intent

Separate:

~~~text
Business event -> NotificationCommand
      |
      v
Template/Recipient policy
      |
      v
Transport adapter
~~~

Do not let every controller build `MimeMessage` instances and choose senders independently.

### Phase 3 — Add Outbox Transactionally

Inside the same business transaction, create a notification row with a unique key. During migration, **do not enable both direct and the outbox worker for the same intent** without a clear ownership mechanism; otherwise duplicates will be sent.

### Phase 4 — Enable Workers for Pilot Traffic

Route a test stream/tenant through the durable worker. Monitor queue latency, retries, unknown outcomes, and provider responses. You can compare metadata in **shadow classification** mode, but do not run two parallel SMTP submissions for the same real email.

### Phase 5 — Roll Out Stream by Stream

Migrate transactional then marketing/digest—or vice versa—based on risk and operational readiness. Keep a rollback plan:

- Pause claiming new jobs on errors.
- Retain unfinished outbox rows.
- Do not reset SENDING/UNKNOWN back to PENDING just to roll back code.
- Allow controlled replay after fixing bugs.

### Phase 6 — Remove Obsolete Direct Paths

Ensure APIs have no legacy paths bypassing consent, quotas, and audits. Keep a separate direct test endpoint if SMTP diagnostics are still needed.

## 52. Which Metrics Should Be Monitored When Using a Queue?

| Metric | Purpose |
|---|---|
| **mail_outbox_created_total** | How many intents producers create |
| **mail_outbox_pending** | How many jobs are still unfinished |
| **mail_outbox_oldest_due_age_seconds** | Oldest due job currently waiting |
| **mail_queue_wait_seconds** | Time from commit to attempt |
| **mail_smtp_attempts_total** | Number of SMTP attempts by provider/result |
| **mail_smtp_submission_duration_seconds** | Latency of the SMTP transport |
| **mail_outbox_submitted_total** | Unique notifications reaching SUBMITTED |
| **mail_outbox_skipped_total** | Skipped due to consent, business rules, or deadline |
| **mail_outbox_retry_wait** | Jobs waiting for retry |
| **mail_outbox_unknown** | Submission outcomes still uncertain |
| **mail_worker_stale_claims_total** | Expired claims/leases needing investigation |
| **mail_dead_letter_total** | Jobs entering DLQ/quarantine |
| **mail_bounce_events_total** | Delivery feedback from providers |

Metrics must be clearly defined **per attempt, per notification, or per recipient**. For example, if one email has three recipients and one bounces, do not count all three as bounced.

**Avoid high-cardinality labels** containing email addresses, Subject, notificationId, raw exception messages, or signed URLs. Use bounded dimensions such as stream, tenant tier, provider, and result/error category; detailed information belongs in access-controlled databases/logs.

### Choosing the Right SLI/SLO

Example:

~~~text
99.9% valid OTP jobs must start SMTP submission
within 5 seconds of intent commit, before expiry.
~~~

This is a **submission timeliness objective**, not a guarantee that the recipient reads the OTP within 5 seconds. Measuring end-to-end delivery depends on ESP data and its reliability.

A queued system with a 20 ms API but p99 queue wait of 2 minutes may fail to meet OTP objectives.

## 53. Testing the Direct Architecture: What to Check?

For the direct path, verify:

| Case | Expectation |
|---|---|
| SMTP succeeds | API reports submission accepted, without promising delivery |
| Authentication fails | API returns a safe error, without leaking passwords |
| Connect timeout | Request terminates per timeout policy |
| SMTP explicitly rejects recipient | Do not treat as sent successfully |
| Final reply timeout after DATA | Outcome may be UNKNOWN; avoid blind auto-retry |
| DB rollback after event occurs | Do not send confirmation mail for a rolled-back transaction if required by design |
| Concurrent requests | Sender does not mutate state/credentials across threads |
| User sends duplicate requests | Appropriate idempotency key/endpoint policy |
| Unauthorized recipient | Transport is not invoked |
| MIME with HTML/attachments | Renders properly without leaking data across tenants |

You can use a test SMTP server to observe received message counts, but distinguish **client-side errors** from **server received DATA while client missed final reply**.

### Unit Testing the Direct Service

A simple check using a mock sender:

~~~java
import static org.mockito.Mockito.verify;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class DirectMailUnitTest {

    @Test
    void callsSenderWhenAuthorized() {
        JavaMailSender mockSender =
                Mockito.mock(JavaMailSender.class);

        TestEmailService service = new TestEmailService(mockSender);
        service.sendTest("allowed@example.net");

        verify(mockSender).send(
                Mockito.any(SimpleMailMessage.class)
        );
    }
}
~~~

This is only a **unit behavior test**; it does not test TCP, SMTP replies, TLS, or DKIM. Authorization/recipient validation needs separate tests. Only SMTP integration tests simulate real failure phases.

## 54. Testing the Queued Path: Prioritize Crashes and Transaction Boundaries

Key tests:

| Scenario | Expected Outcome |
|---|---|
| Business transaction rollback | No outbox intent exists |
| Business commit succeeds | Outbox intent exists for workers to pick up |
| Process crash after commit before dispatch | Intent is not lost; another worker can continue |
| Producer retries request with same idempotency key | Does not create duplicate business intent |
| Two workers claim the same row | Only one claim wins per DB ownership |
| Worker crashes while CLAIMED, before SMTP | Safe reclaim per state/lease policy |
| Worker crashes while SENDING | Do not assume unsent; route to UNKNOWN/reconciliation |
| SMTP accepted but DB update fails | Do not replay blindly and create duplicates |
| Broker redelivers after ACK timeout | Consumer recognizes durable state |
| Queue message has malformed job ID | Reject/quarantine per policy without blocking queue |
| Provider SMTP outage | Retry with backoff and rate budget |
| Retry past `expires_at` | Do not start a new attempt |
| User unsubscribes after enqueue | Worker sets SKIPPED, does not send |
| Hard bounce suppression arrives after enqueue | Worker does not ignore current policy |
| Marketing burst | OTP/transactional is not starved past SLA |
| DLQ replay | Has audit, idempotency, operator authorization |
| Outbox job deleted from broker but still in DB | Reconciliation/dispatcher re-emits when valid |

### Testing Real Database Claims

When using PostgreSQL **FOR UPDATE SKIP LOCKED**, integration tests must run against a database with the same semantics and transaction isolation as production. A unit test mocking a Queue with an in-memory list cannot prove claim/update atomicity.

Simulation:

~~~text
Thread A: claim next 1
Thread B: claim next 1

Given: 1 row PENDING

Assert:
  exactly one claim success
  unique claim token belongs to winning worker
~~~

Repeat tests with expired job states, concurrent cancellation, and changing leases. Do not reset worker status while bypassing claim tokens in production implementations.

### SMTP Capture Integration Tests

With a test mail environment that can return deliberate SMTP replies:

- Send a valid notification: captured mail count matches intent.
- Deterministic 4xx error: transitions to RETRY_WAIT if within deadline.
- 5xx invalid recipient error: records result per recipient.
- Timeout after DATA: status UNKNOWN, do not assert definitely unsent.
- Handler/worker restart: no duplicate created when durable state is already SUBMITTED.

Tools like a test SMTP server are solely for integration verification; never send emails to real recipients when testing retries/cancellations.

## 55. Runbook: HTTP API Is Slow Because of SMTP

If using direct sending and API latency increases:

1. Inspect trace breakdown: business DB, MIME rendering, DNS/TCP/TLS, SMTP DATA, read timeout.
2. Check SMTP connection/authentication failures, provider throttling, quotas.
3. Inspect how many request threads are blocked on network and connection pools.
4. Check whether emails have large attachments or slow template rendering.
5. Determine whether the endpoint actually needs to wait for the SMTP result.
6. If email is not a mandatory business condition, consider a durable queue/outbox to decouple latency.
7. Do not merely increase HTTP timeouts as a long-term solution.
8. Do not switch to in-memory `@Async` and claim you have achieved durable delivery.

### If Forced to Continue Direct Sending

- Enforce bounded concurrency.
- Configure SMTP timeouts.
- Enforce rate limits and input validation.
- Avoid SMTP I/O inside long-running DB transactions.
- Provide explicit error outcomes and support diagnostics.
- Enforce idempotency if callers retry requests.

These measures make direct sending safer within its limits, but do not create a durable retry queue without persistence.

## 56. Runbook: Queue Grows While SMTP Is Still Healthy

When **mail_outbox_pending** and **oldest_due_age** rise:

### Step 1 — Identify the Backlog Source

- Did producer traffic spike or did worker throughput drop?
- Which jobs are accumulating: marketing, OTP, invoices?
- Is a single tenant/campaign responsible for most of it?
- Is the provider rate limit lower than the job creation rate?
- Are retries repeating too quickly?

### Step 2 — Check Workers

- Active worker count and in-flight jobs?
- Are claim queries/indexes slow or experiencing heavy DB locks?
- Is the lease too short, causing jobs to be marked stale?
- Is queue consumer prefetch too high, causing one worker to hoard messages?
- Have SMTP connections/authentication/timeouts changed?

### Step 3 — Check Policies and Deadlines

- Are there overdue jobs that should be EXPIRED instead of sent late?
- Was a campaign paused while still enqueueing?
- Did consent/suppression changes cause many jobs to become SKIPPED?
- Are priorities/quotas starving the security stream?

### Step 4 — Take Action

- Throttle the producer/campaign.
- Scale up workers when **provider quota and DB capacity genuinely allow**.
- Fix index/claim contention.
- Tune retry backoff and circuit breakers.
- Apply expiry policies to emails that have lost value.
- Isolate stream/priority pools if head-of-line blocking is occurring.
- Keep UNKNOWN jobs for reconciliation; do not reset all SENDING jobs to PENDING.

### Step 5 — Verify Recovery

Monitor:

~~~text
queue_wait_p95 / p99
oldest_due_age
SMTP accepted rate
provider 4xx/5xx rate
retry_wait count
unknown count
expired_due_to_capacity count
~~~

Evaluate **by stream and recipient**, not just aggregate throughput.

## 57. Runbook: Duplicate Emails Were Sent

Common causes:

~~~text
Client retry -> creates 2 intent IDs
      |
Broker retry -> same intent delivered twice
      |
Worker A lease expired -> Worker B sends again
      |
SMTP accepted -> result DB update failed
      |
Provider timeout after DATA -> retry without reconciliation
      |
Direct fallback and queue both send same notification
~~~

Procedure:

1. Determine whether **two distinct business intents exist** or the same intent was retried.
2. Inspect unique business key/recipient, outboxId, and provider message IDs.
3. Check attempt history and SMTP phase for each attempt.
4. Check producer idempotency, broker ACK, queue redelivery, leases, and stale workers.
5. If using provider failover, check the primary outcome before secondary sends.
6. Fix state transitions/ownership, rather than just adding an `if` check on Subject/Message-ID.
7. Mark uncertain notifications as UNKNOWN and reconcile.
8. Retest crash windows that can cause duplicates.

Do not delete attempt history while investigating duplicates; it is the evidence distinguishing enqueue bugs from SMTP bugs.

## 58. Anti-Patterns and Alternatives

| Anti-Pattern | Consequence | Alternative |
|---|---|---|
| Sending SMTP inside a `@Transactional` business method | Long DB locks, rollback cannot recall email | Transactional outbox, send after commit |
| Assuming `@Async` is a durable queue | Jobs lost on JVM crash | Persist intents or explicitly accept best effort |
| Committing DB then publishing to broker without outbox | Dual-write gap loses events | Transactional outbox |
| Publishing to broker before business DB commit | Emails sent for rolled-back business actions | Atomic intent or explicit consistency model |
| ACKing before persisting outcome | Crash loses work | Commit durable state before ACK |
| ACKing after SMTP and assuming exactly-once | Redelivery can send duplicates | Idempotency/UNKNOWN/reconciliation |
| Resetting all stale SENDING rows to PENDING | Duplicates after SMTP acceptance | Distinguish CLAIMED from UNKNOWN |
| Retrying all `MailException` errors | Retries permanent/ambiguous errors | Classifier + deadline/backoff |
| Unbounded queue to absorb overload | Backlog just grows, emails go stale | Admission/backpressure/capacity planning |
| Single FIFO for OTP and marketing | OTP suffers starvation | Priority/stream isolation |
| Adding workers beyond provider quota | Throttling increases | Provider token bucket/concurrency cap |
| Setting status DELIVERED when `send()` returns | Misleading outcome reporting | SUBMITTED + provider feedback |
| Creating one job for multi-tenant recipients | Hard data isolation/partial results | Per-tenant/per-recipient jobs |
| Pushing full attachments into the broker | Broker bloat/PII risk | Durable object references |
| Using latest template without pinning version | Replayed email differs from original | Version/snapshot strategy |
| Trusting consent snapshot from enqueue time | Sends after unsubscribe | Final eligibility gate |
| Ad-hoc direct fallback on queue timeout | Duplicate sends | Durable intent + dispatcher retry |
| Using Message-ID as an exactly-once key | No SMTP dedup guarantee | Business idempotency/attempt state |
| No DLQ/replay procedure | Poison messages stall pipeline | Quarantine, controlled replay |
| Using email addresses as Prometheus labels | High cardinality and PII | Bounded dimensions, secured lookup |
| Measuring only queue producer HTTP latency | Misses delayed mail delivery | Queue wait + SMTP result + delivery feedback |
| Forgetting to clean up/archive terminal outbox rows | DB bloats and queries slow down | Retention/partitioning/audit store |
| Already having a broker so always using Kafka | Unnecessary complexity | Choose by workload, semantics, and team |

## 59. Checklist Before Finalizing Architecture

**Business Goals**

1. Which emails genuinely must be sent and which are only best-effort notifications?
2. Is it defined when HTTP is allowed to return success?
3. Are **QUEUED**, **SUBMITTED**, and **DELIVERED** clearly distinguished?
4. Are maximum latencies for OTP/security/campaigns measured with appropriate end-to-end SLIs?
5. Are late emails still useful or must they become EXPIRED?
6. Is duplicate SMTP risk in certain crash windows acceptable?

**Mechanism Selection**

7. Does direct sending truly need immediate transport feedback?
8. If using `@Async`, does the team understand it is in-memory best effort?
9. If a durable queue is needed, does the producer ensure intents are stored after business commit?
10. When business state and email intent share a DB, are they committed in one transaction?
11. Was database jobs vs. broker chosen based on throughput, recovery, and operations team?
12. If using a broker, are ACK/offsets, publisher confirms, and DLQs configured?
13. Is ad-hoc direct fallback causing duplicates on broker timeouts avoided?

**State and Idempotency**

14. Is there a unique key for business event/recipient/notification type?
15. Are there claim tokens, leases, and conditional state transitions?
16. Does the worker recognize terminal jobs on broker redelivery?
17. Is there an **UNKNOWN** state for ambiguous SMTP outcomes?
18. Are attempt history and provider correlation stored for reconciliation?
19. Are stale workers prevented from updating the DB after losing their lease?
20. Is idempotent business action distinguished from SMTP delivery?

**Capacity, Retry, and Policy**

21. Are there rate/concurrency limits per provider, stream, and tenant?
22. Are there alerts for oldest due age, queue wait p95/p99, and throughput drops?
23. Is there a retry classifier for transient/permanent/ambiguous errors?
24. Do retries have backoff, jitter, max attempts, and deadlines?
25. Is there priority/isolated capacity so marketing does not delay OTPs?
26. Is there a final consent/suppression/business eligibility gate before sending?
27. Is there a way to expire/skip valueless jobs without calling SMTP?
28. Is there backpressure when producer rate exceeds provider rate?

**Security and Operations**

29. Is sender profile ownership verified for the tenant?
30. Do queue messages carry only minimal metadata/refs instead of raw attachments/secrets?
31. Do the broker, DB, object storage, and DLQ have proper retention/ACLs?
32. Do logs/metrics avoid leaking recipients, Subjects, tokens, and bodies?
33. Are there runbooks for SMTP outages, backlogs, duplicates, and UNKNOWN states?
34. Is there an owner for replay/dead-letter handling and admin operation permissions?
35. Are delivery/bounce webhooks reconciled if supported by the provider?
36. Is there a cleanup/archive plan for outbox rows after retention?

**Testing**

37. Are business rollback and crash-right-after-commit tests designed?
38. Are concurrent two-worker claim and stale-lease tests in place?
39. Are broker redelivery after commit before ACK tests in place?
40. Are SMTP accepted with DB update failure tests in place?
41. Are timeout-after-DATA and UNKNOWN policy tests in place?
42. Are unsubscribe-after-enqueue and expiry-before-send tests in place?
43. Are marketing-burst impact tests on security/transactional streams in place?
44. Are provider failover and duplicate-risk boundary tests in place?

This checklist is a **design and implementation review tool**. Spring Framework Mail itself does not automatically satisfy all of the guarantees above merely by adding a dependency or annotation.

## 60. Summary: Choose Based on Responsibility and Guarantee Level

No single option is always best. **Direct, @Async, database queues, and broker queues sit at different levels of complexity and guarantees**.

| Core Question | Decision Direction |
|---|---|
| Must the SMTP response be received within the user's synchronous action? | Consider **direct** with timeouts/rate limits/authorization |
| Is losing notifications on JVM crash acceptable? | If yes, **best effort** may suffice |
| Must send intents be persisted with the business transaction? | Use a **transactional outbox** |
| Are retries, campaigns, quotas, and independent workers required? | Use a **durable queue/outbox** |
| Large scale, multiple services, needing buffering/fan-out? | Consider a **broker**, often combined with an outbox |
| Short-TTL or latency-sensitive emails? | Choose **priority lanes and measure queue wait**, not just HTTP latency |
| Strict non-duplication requirement? | Clarify SMTP limits, **idempotency, and UNKNOWN reconciliation** |
| Need to reduce outage risk? | **Durable intent + bounded retries + backpressure** |

A practical design recipe for a business-critical Spring application:

~~~text
Business event
     |
     v
BEGIN DB TRANSACTION
  Save business change
  Save notification intent (unique business key)
COMMIT
     |
     v
Durable outbox / broker
     |
     v
Claim + current-policy check + deadline
     |
     v
Compose MIME from versioned template and safe references
     |
     v
JavaMailSender.send(...)
     |
     +-- Accepted -> SUBMITTED + feedback correlation
     +-- Transient -> RETRY_WAIT + backoff
     +-- Permanent -> FAILED/SKIPPED by policy
     +-- Ambiguous -> UNKNOWN + reconciliation
     |
     v
Metrics, audit, provider delivery/bounce events
~~~

**Direct sending** remains a good choice for small, controlled needs that truly require immediate SMTP feedback. However, when email is a business responsibility that must not be lost after commit, **persisting send intents durably and processing them with workers** generally produces a more resilient, measurable, and operable architecture.

**The most important point is not "queue or no queue," but what responsibility the system claims to have accepted, where it records that responsibility, and how honestly it handles every case of success, failure, duplication, or unknown outcome.**










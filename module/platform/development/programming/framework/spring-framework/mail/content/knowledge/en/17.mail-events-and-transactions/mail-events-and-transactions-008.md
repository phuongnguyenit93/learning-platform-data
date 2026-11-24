# Reading the Outbox and Sending Mail Outside the Main Transaction

## 1. Why read an outbox to send email?

In a Spring application, a business operation often both updates the database and needs to send an email. For example:

- An order transitions to **SHIPPED**, and the buyer needs the tracking number.
- Payment is confirmed, and the customer needs a receipt.
- An account is activated, and the user needs a notification.
- A refund request is received, and the customer needs a status update.

If emails are sent directly inside the business transaction, transaction duration depends on the SMTP network. When SMTP is slow or unreachable, the database transaction may stay open longer, hold locks longer, and reduce concurrency.

A cleaner structure is a **transactional outbox**:

1. Inside the business transaction, update data and write an outbox record describing the email to send.
2. Commit the database transaction.
3. An independent worker reads due outbox records.
4. The worker claims ownership of a record and commits the claim.
5. The worker builds and sends the email via **JavaMailSender** outside the main database transaction.
6. After sending or hitting an error, the worker opens a separate transaction to update the processing outcome.

Overall flow:

~~~text
Request / Business event
          |
          v
   Business transaction
      |           |
      |           +--> INSERT notification_outbox
      |
      +--> UPDATE business data
          |
        COMMIT
          |
          v
    Outbox polling worker
          |
          v
     Claim due records
          |
        COMMIT
          |
          v
   Render + JavaMailSender
      (not holding DB transaction)
          |
          v
   SMTP/provider response
          |
          v
  Separate result transaction
          |
          v
  SUBMITTED / RETRY / FAILED / UNKNOWN
~~~

An outbox solves **persisting email send intent atomically with business changes**. The worker decouples mail delivery time from the primary state-updating transaction.

## 2. Problems with calling SMTP inside the main transaction

A common pattern:

~~~java
@Transactional
public void markOrderShipped(String orderId, ShipmentInfo shipment) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.markShipped(shipment);
    orderRepository.save(order);

    mailService.sendShippedEmail(order, shipment);
}
~~~

In this code, the database transaction remains open while sendShippedEmail connects to SMTP and transmits the message.

Potential issues:

- **Prolonged transactions:** SMTP latency is unpredictable, ranging from milliseconds to several seconds or longer.
- **Extended lock holding:** other transactions must wait if they need to update the same records.
- **Unsynchronized rollbacks:** SMTP may have accepted the email while the database rolls back afterward. The recipient gets a "shipped" email while the order status was never committed.
- **Lost notifications:** the database commits successfully while SMTP fails; state changed without sending the email.
- **Difficult retries:** if the entire method rolls back, the application has no durable record describing the email to send.
- **Hard to throttle load:** a large batch of business updates can simultaneously open many SMTP connections.

SMTP does not participate in database transactions. You cannot assume **@Transactional** will roll back an email already accepted by SMTP.

### Separating transactions does not mean abandoning consistency

If you merely update the database and then send email on another thread, a gap still exists: the process can stop after database commit but before the send task is durably stored. An outbox closes that gap by writing the send intent into the database in **the same transaction** as the business change.

## 3. What is a transactional outbox?

A transactional outbox is a database table or storage structure recording events or notifications that must be forwarded to external systems. For email, each record can represent one notification to send.

Example **notification_outbox** table:

| Column | Meaning |
|---|---|
| **id** | Primary key of the record |
| **event_id** | Unique identifier of the source event |
| **event_type** | Event type, e.g., ORDER_SHIPPED |
| **aggregate_id** | Related order/account ID |
| **payload** | Snapshot of data needed to build the email |
| **recipient** | Recipient or reference to the recipient |
| **template_key** | Template to render |
| **locale** | Content language |
| **status** | PENDING, PROCESSING, RETRY, SUBMITTED, FAILED... |
| **attempts** | Number of times a worker has claimed/attempted sending |
| **next_attempt_at** | Earliest timestamp eligible for retry |
| **locked_by** | Worker currently holding processing ownership |
| **claim_token** | Token verifying ownership of the current claim |
| **locked_until** | Lease expiration of the current claim |
| **last_error** | Sanitized error description |
| **created_at** | Outbox creation timestamp |
| **updated_at** | Most recent update timestamp |
| **submitted_at** | Timestamp when SMTP/provider accepted, if known |

Illustrative PostgreSQL DDL:

~~~sql
CREATE TABLE notification_outbox (
    id                UUID PRIMARY KEY,
    event_id          UUID NOT NULL,
    event_type        VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(150) NOT NULL,
    recipient         VARCHAR(320) NOT NULL,
    template_key      VARCHAR(150) NOT NULL,
    locale            VARCHAR(20) NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(30) NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by         VARCHAR(150),
    claim_token       UUID,
    locked_until      TIMESTAMPTZ,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at      TIMESTAMPTZ,
    CONSTRAINT uq_notification_outbox_event UNIQUE (event_id)
);

CREATE INDEX ix_notification_outbox_due
    ON notification_outbox (status, next_attempt_at, created_at);
~~~

This is an illustrative starting schema. Applications may use different column names, JSON types, indexes, or statuses depending on database engine and scale. If one event generates multiple notifications for different audiences, the unique key should use a suitable notification key, such as event ID + notification type + audience, rather than only event ID.

## 4. Writing to the outbox in the same business transaction

Core principle:

**Business data changes and the outbox record must commit or roll back together.**

For example, when an order is handed off to a shipping carrier:

~~~java
public record OrderShippedPayload(
        String orderId,
        String orderCode,
        String customerName,
        String recipientEmail,
        String trackingNumber,
        String trackingUrl,
        Instant shippedAt
) {
}
~~~

Application service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final NotificationOutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            NotificationOutboxRepository outboxRepository
    ) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public void shipOrder(String orderId, ShipmentInfo shipment) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.markShipped(shipment);
        orderRepository.save(order);

        OrderShippedPayload payload = new OrderShippedPayload(
                order.getId(),
                order.getCode(),
                order.getCustomerName(),
                order.getCustomerEmail(),
                shipment.trackingNumber(),
                shipment.trackingUrl(),
                Instant.now()
        );

        outboxRepository.insert(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "ORDER_SHIPPED",
                order.getId(),
                payload
        );
    }
}
~~~

The repositories and Order, ShipmentInfo types are application-defined components. The example shows both orderRepository.save(...) and outboxRepository.insert(...) participating in the same Spring transaction.

Outcome:

- If the transition or outbox insert fails, the transaction rolls back; no shipped order exists without a notification intent.
- If the commit succeeds, both the order change and the outbox record exist for workers to process.
- If SMTP goes down, the outbox record remains and workers can retry per policy.

In a real application, the event ID should be generated deterministically from a validated event or guarded by a unique constraint against duplicate processing. Never create a new outbox record every time the same webhook is resent.

### Why not call mailService.send() here?

The business method only persists data and send intent. It does not need to open SMTP connections, serialize MIME, or wait for external servers. Thus the main transaction stays short and can roll back atomically on the database.

## 5. What should the payload store?

Workers typically run after the event occurred. If the payload stores only orderId, the worker might read the latest state and construct an email that no longer matches the original event.

Example:

1. Order moves from PAID to SHIPPED; outbox is written.
2. Email is delayed because SMTP is failing.
3. Order moves onward to DELIVERED.
4. Worker reads orderId, queries current state, and sees only DELIVERED.
5. Worker sends delivery content while the original outbox record represented the shipped event.

To avoid this, payloads should store **the minimum snapshot needed at the moment the event occurs**, such as:

- Event type and event ID.
- Aggregate ID and version.
- Before/after states if needed.
- Display name, order code, and data permitted in the email.
- Verified recipient or recipient reference.
- Tracking number, business URL, or required transaction details.
- Template key and locale.

You do not need to store the entire entity. Keep only fields needed for the notification, or keep the ID plus a version/snapshot that can be retrieved consistently. The larger a payload is and the more personal data it holds, the stricter the encryption, read permissions, and retention policies required.

### Snapshot or re-query?

| Approach | When suitable | Risks to manage |
|---|---|---|
| Full snapshot of fields needed to render | Email must reflect exact event time | Payload may contain PII and require retention |
| Store ID only and re-query | Data rarely changes or policy demands latest info | Content may drift from original event |
| Store ID and version/snapshot reference | Large data needing versioned lookup | Storage must support versions and retain them long enough |

For event-confirmation emails, snapshots usually make consistency easier to guarantee. For current-status reminder emails, querying latest state may better match the intent. Decide by business meaning, not repository convenience.

## 6. Worker reading due outbox records

Workers periodically look for records eligible for processing, such as:

- PENDING and due for processing.
- RETRY whose next_attempt_at has arrived.
- PROCESSING whose lease has expired because a previous worker may have stopped abnormally.

Do not load the entire outbox table into memory and filter in Java. Use filtered, ordered, batch-limited queries.

A candidate selection query might look like:

~~~sql
SELECT id
FROM notification_outbox
WHERE
      (status = 'PENDING' AND next_attempt_at <= CURRENT_TIMESTAMP)
   OR (status = 'RETRY' AND next_attempt_at <= CURRENT_TIMESTAMP)
   OR (status = 'PROCESSING' AND locked_until < CURRENT_TIMESTAMP)
ORDER BY next_attempt_at, created_at
LIMIT 25;
~~~

This query only illustrates selection criteria. When multiple workers run concurrently, a plain SELECT like this **is insufficient for exclusive distribution**: two workers can read the same ID before either updates the status.

An atomic claim step or locking/lease mechanism is required so only one worker owns a processing attempt at a time.

## 7. Claiming records and committing before sending mail

A common strategy on databases supporting **FOR UPDATE SKIP LOCKED**:

1. Open a short transaction.
2. Select a batch of due records with SELECT ... FOR UPDATE SKIP LOCKED.
3. Update them to PROCESSING, increment attempts, set locked_by, claim_token, and locked_until.
4. Return the claimed records from the method.
5. The claim transaction commits when the method returns.
6. The worker starts rendering and sending emails after the claim transaction has committed.

SKIP LOCKED lets other workers skip rows currently locked by another worker and pick up different rows. This is a common pattern for building polling queues on PostgreSQL and several other databases; adapt syntax and support to your actual database.

Diagram:

~~~text
Worker A                         Worker B
   |                                |
   v                                v
BEGIN claim                     BEGIN claim
   |                                |
SELECT ... FOR UPDATE           SELECT ... SKIP LOCKED
   |                                |
claim row 101                    skip row 101
   |                             claim row 102
UPDATE row 101                      |
   |                             UPDATE row 102
COMMIT                              |
   |                             COMMIT
   v                                v
Send email 101                  Send email 102
~~~

### PostgreSQL SQL example

A transaction can select a batch:

~~~sql
SELECT id, event_type, aggregate_id, recipient, template_key,
       locale, payload, attempts
FROM notification_outbox
WHERE
      (status IN ('PENDING', 'RETRY')
       AND next_attempt_at <= CURRENT_TIMESTAMP)
   OR (status = 'PROCESSING'
       AND locked_until < CURRENT_TIMESTAMP)
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 25;
~~~

After selecting, update each row within the same transaction:

~~~sql
UPDATE notification_outbox
SET status = 'PROCESSING',
    attempts = attempts + 1,
    locked_by = :workerId,
    claim_token = :claimToken,
    locked_until = :lockedUntil,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

claimToken should be a fresh UUID for each claim. When the transaction commits, the database lock is released while the lease and token record temporary ownership. The worker may update the outcome only if the token still matches.

**Do not hold a transaction containing FOR UPDATE open while sending email.** The claim transaction must finish before the worker calls SMTP.

## 8. Claim service example with Spring transactions

You can use JdbcTemplate to run locking queries tailored to your database syntax. Below is an illustrative skeleton:

~~~java
public record ClaimedNotification(
        UUID id,
        UUID claimToken,
        String eventType,
        String aggregateId,
        String recipient,
        String templateKey,
        String locale,
        String payload,
        int attempts
) {
}
~~~

Claim service:

~~~java
@Service
public class OutboxClaimService {

    private final JdbcTemplate jdbcTemplate;
    private final String workerId;

    public OutboxClaimService(
            JdbcTemplate jdbcTemplate,
            WorkerIdentity workerIdentity
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.workerId = workerIdentity.id();
    }

    @Transactional
    public List<ClaimedNotification> claimBatch(int batchSize) {
        List<OutboxCandidate> candidates = jdbcTemplate.query(
                """
                SELECT id, event_type, aggregate_id, recipient,
                       template_key, locale, payload, attempts
                FROM notification_outbox
                WHERE
                      (status IN ('PENDING', 'RETRY')
                       AND next_attempt_at <= CURRENT_TIMESTAMP)
                   OR (status = 'PROCESSING'
                       AND locked_until < CURRENT_TIMESTAMP)
                ORDER BY next_attempt_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT ?
                """,
                outboxCandidateRowMapper(),
                batchSize
        );

        List<ClaimedNotification> claimed = new ArrayList<>();

        for (OutboxCandidate candidate : candidates) {
            UUID token = UUID.randomUUID();
            Instant leaseUntil = Instant.now().plus(Duration.ofMinutes(3));

            jdbcTemplate.update(
                    """
                    UPDATE notification_outbox
                    SET status = 'PROCESSING',
                        attempts = attempts + 1,
                        locked_by = ?,
                        claim_token = ?,
                        locked_until = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    workerId,
                    token,
                    Timestamp.from(leaseUntil),
                    candidate.id()
            );

            claimed.add(candidate.toClaimed(token));
        }

        return List.copyOf(claimed);
    }
}
~~~

OutboxCandidate, outboxCandidateRowMapper(), and WorkerIdentity are application components to implement. The example uses Instant to represent the lease while the database stores timestamps. Across multi-host systems where clocks may skew, compute lease times from the database clock or use reliable clock synchronization.

The SQL snippet follows PostgreSQL style; LIMIT/FOR UPDATE SKIP LOCKED, JSON types, and parameter binding may differ by database engine. Use matching syntax and verify query plans/indexes on deployment.

### Why is the claim method in a separate bean?

The worker calls claimService.claimBatch(...). When the call passes through the Spring proxy, the transaction opens before the method runs and commits when the method returns. The worker receives the list only after the claim transaction finishes, and then processes SMTP.

If calling another `@Transactional` method via `this.claimBatch()` on the same object, the Spring proxy may not be triggered under default proxy mode. Separating the claim service into its own bean makes transaction boundaries explicit.

## 9. Sending mail after the claim transaction has ended

The worker coordinates claiming and sending:

~~~java
@Component
public class OutboxMailWorker {

    private final OutboxClaimService claimService;
    private final OutboxMailProcessor processor;

    public OutboxMailWorker(
            OutboxClaimService claimService,
            OutboxMailProcessor processor
    ) {
        this.claimService = claimService;
        this.processor = processor;
    }

    @Scheduled(fixedDelay = 2000)
    public void poll() {
        List<ClaimedNotification> batch =
                claimService.claimBatch(25);

        for (ClaimedNotification notification : batch) {
            processor.process(notification);
        }
    }
}
~~~

The worker does not need @Transactional. claimBatch(...) has already finished its transaction before returning; each processor.process(...) invokes the mail sender outside the claim transaction and outside the original business transaction.

When processing a batch sequentially, one slow email delays the remaining emails in the batch. You can increase worker count or use a bounded executor, but control concurrency so you do not exceed SMTP provider connection limits and quotas.

## 10. Building MIME and sending with JavaMailSender

The processor takes a claimed record, decodes the payload, chooses a template, and sends:

~~~java
@Service
public class OutboxMailProcessor {

    private final EmailTemplateRenderer renderer;
    private final JavaMailSender mailSender;
    private final OutboxResultService resultService;
    private final OutboxFailureService failureService;

    public OutboxMailProcessor(
            EmailTemplateRenderer renderer,
            JavaMailSender mailSender,
            OutboxResultService resultService,
            OutboxFailureService failureService
    ) {
        this.renderer = renderer;
        this.mailSender = mailSender;
        this.resultService = resultService;
        this.failureService = failureService;
    }

    public void process(ClaimedNotification notification) {
        try {
            RenderedEmail content = renderer.render(notification);

            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    true,
                    StandardCharsets.UTF_8.name()
            );

            helper.setFrom("notifications@example.com");
            helper.setTo(notification.recipient());
            helper.setSubject(content.subject());
            helper.setText(content.plainText(), content.htmlText());

            mailSender.send(message);

            resultService.markSubmitted(
                    notification.id(),
                    notification.claimToken()
            );
        } catch (Exception exception) {
            failureService.recordFailure(
                    notification,
                    exception
            );
        }
    }
}
~~~

RenderedEmail, EmailTemplateRenderer, OutboxResultService, and OutboxFailureService are application abstractions. The example uses a hardcoded From address for illustration; production systems must configure a valid sender. In real implementations, classify specific exceptions instead of catching every Exception and applying the same retry policy.

Key point: the process(...) method has no @Transactional. Building MIME and calling mailSender.send(...) do not hold a database transaction open. The two result-updating services are invoked separately with their own short transactions.

## 11. Updating the outcome in a separate transaction

After SMTP/provider accepts the message, the worker updates the outbox:

~~~java
@Service
public class OutboxResultService {

    private final JdbcTemplate jdbcTemplate;

    public OutboxResultService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSubmitted(UUID id, UUID claimToken) {
        int updated = jdbcTemplate.update(
                """
                UPDATE notification_outbox
                SET status = 'SUBMITTED',
                    submitted_at = CURRENT_TIMESTAMP,
                    locked_by = NULL,
                    claim_token = NULL,
                    locked_until = NULL,
                    last_error = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status = 'PROCESSING'
                  AND claim_token = ?
                """,
                id,
                claimToken
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Outbox claim is no longer owned by this worker"
            );
        }
    }
}
~~~

REQUIRES_NEW creates an independent transaction for the outcome update if a transaction already exists. Since the processor opens no outer transaction, it starts a short transaction and commits.

The `claim_token = ?` condition is critical. If the lease expired and another worker reclaimed the record, the old token is no longer valid. The stale worker must never overwrite the newer worker's result.

If the update affects 0 rows, log the lost-claim situation and investigate. Never ignore it silently because that can hide race conditions or overly short leases.

### SUBMITTED does not mean landed in Inbox

The name SUBMITTED indicates the application received a successful result at the SMTP/provider submission stage. It does not prove the mailbox accepted the message, that it avoided Spam, or that the user read it. If the provider offers delivery webhooks/events, store separate delivery states as well.

## 12. Error handling and retries

If template rendering, MIME construction, or SMTP sending fails, the worker must record the result in the outbox inside a separate transaction. Never let an exception lose a pending record.

Common error categories:

| Error category | Example | Common policy |
|---|---|---|
| Data error | Payload missing field, template key missing | Move to FAILED or dead-letter for manual handling |
| Configuration error | Wrong SMTP credentials, disallowed sender | Alert, stop rapid retries or cap retries |
| Temporary error | SMTP 4xx, rate limit, transient connection drop | Retry with backoff |
| Recipient error | Invalid address, mailbox permanently rejected | Mark permanent failure per response |
| Indeterminate error | Timeout after sending DATA | Mark UNKNOWN or apply reconciliation policy |
| Local infrastructure error | Database temporarily unreachable during result update | Recover state via leases/reconciliation |

Not every MailException can be classified by exception class alone. Whenever possible, inspect SMTP response codes or provider metadata. Never store raw exception messages if they may contain addresses, URL tokens, or sensitive data.

### Exponential backoff

A simple policy:

~~~text
delay = min(maxDelay, baseDelay * 2^(attempt - 1)) + jitter
~~~

Example with a 30-second base delay and 30-minute max delay:

| Attempt | Base delay before jitter |
|---:|---:|
| 1 | 30 seconds |
| 2 | 60 seconds |
| 3 | 120 seconds |
| 4 | 240 seconds |
| 5 | 480 seconds |

Random jitter keeps multiple workers from retrying simultaneously right when the SMTP provider recovers. Cap maximum attempts, total age, and define what happens when limits are exceeded.

Retry update example:

~~~java
@Service
public class OutboxFailureService {

    private final JdbcTemplate jdbcTemplate;

    public OutboxFailureService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void scheduleRetry(
            UUID id,
            UUID claimToken,
            Instant nextAttemptAt,
            String safeError
    ) {
        int updated = jdbcTemplate.update(
                """
                UPDATE notification_outbox
                SET status = 'RETRY',
                    next_attempt_at = ?,
                    locked_by = NULL,
                    claim_token = NULL,
                    locked_until = NULL,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status = 'PROCESSING'
                  AND claim_token = ?
                """,
                Timestamp.from(nextAttemptAt),
                safeError,
                id,
                claimToken
        );

        if (updated != 1) {
            throw new IllegalStateException("Outbox claim was lost");
        }
    }
}
~~~

safeError must be truncated and sanitized. Place exception classification and nextAttemptAt calculation in the retry-policy layer; do not write arbitrary raw error text verbatim into the database.

## 13. Attempt limits and terminal states

A record should not retry infinitely. You can define:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- send succeeds --------> SUBMITTED
   |
   +---- temporary error ------> RETRY
   |                              |
   |                              v
   |                          PROCESSING
   |
   +---- permanent error ------> FAILED
   |
   +---- uncertain outcome ----> UNKNOWN
~~~

When attempts exceed the threshold:

- Mark FAILED or DEAD_LETTER.
- Save sanitized error codes and tracing info.
- Emit metrics/alerts for operations review.
- Provide a data-fix and controlled replay workflow if business rules permit.

Do not automatically mark every error as FAILED after a single attempt. Temporary SMTP failures deserve retries; broken templates cannot be fixed by retrying endlessly.

## 14. Uncertain outcomes and exactly-once limits

An outbox guarantees **durable persistence of email send intent**, yet cannot achieve exactly-once delivery over SMTP through database transactions alone.

A difficult scenario:

1. Worker transmits all DATA to the SMTP server.
2. SMTP server receives and accepts the message.
3. Connection drops before the worker receives the final response.
4. Worker observes a timeout and does not know whether the server accepted it.
5. If it retries, the email may be sent twice.

This is the **UNKNOWN** state, not definitely FAILED.

Risk-reduction measures:

- Store event ID, notification ID, and attempt ID.
- Use an idempotency key if the email provider offers API support with clear semantics.
- Store the provider message ID when returned.
- Reconcile status via provider APIs/webhooks if available.
- Cap retries and maintain a dedicated policy for uncertain errors.
- Email bodies may display a notification reference for investigation, without assuming mailboxes automatically deduplicate.

**SMTP Message-ID is not a deduplication guarantee.** Resending the same Message-ID does not guarantee every server or mailbox will drop the second email.

A transactional outbox typically provides an **at-least-once processing/attempt** model: durable records are retried until processed per policy. The application must accept possible duplicate sends in certain scenarios with indeterminate outcomes.

## 15. Leases, worker crashes, and reclaiming PROCESSING records

A worker can stop unexpectedly after claiming:

- Process is killed.
- Container restarts.
- Server loses power.
- Thread hangs.
- SMTP client hangs longer than expected.

If a record stays in PROCESSING without ever being released, it gets stuck permanently. Therefore, **leases** are needed:

- When claiming, set locked_until in the future.
- Worker processes within the lease window.
- Upon completion, update status and clear the lock.
- If the worker dies, the lease expires; another worker can reclaim it.

### Choosing lease duration

The lease must be longer than expected processing time, including rendering and SMTP sending. If emails carry large attachments or providers are often slow, a few minutes may be safer than a few seconds.

If an operation can outlast the lease, the worker must renew the lease via heartbeat:

~~~sql
UPDATE notification_outbox
SET locked_until = :newLockedUntil,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claimToken;
~~~

Renewal succeeds only while the token remains valid. Never renew by ID alone because a stale worker could accidentally extend a new worker's lease.

A lease does not cancel an in-flight SMTP request. If the old worker still sends after its lease expires and a new worker has already reclaimed, two sends can occur. Choose sensible leases, explicit SMTP timeouts, and heartbeats where needed.

## 16. Handling multiple concurrent workers

In production, multiple application instances or workers may run to raise throughput. Coordination is required so the same record is not sent concurrently.

### SELECT FOR UPDATE SKIP LOCKED

Suitable for databases supporting row-level locks and the matching syntax. Each worker locks distinct rows in a short claim transaction, updates leases, and commits.

### Atomic compare-and-set

For databases lacking SKIP LOCKED, use a conditional UPDATE so only one worker transitions a record from a claimable state to PROCESSING. The worker processes only when updated row count equals 1. Design batch/claim tokens carefully and verify isolation levels.

### Message brokers

An outbox publisher can forward events to a broker like Kafka or RabbitMQ while consumers send mail. You then need ack, retry, dead-letter, and idempotency across both stages. A broker does not remove the need for atomic outbox writes in the database if events originate from business transactions.

Never rely on a Java `synchronized` variable as the sole lock in a multi-instance system. Each JVM process has its own monitor and shares no locks across instances.

## 17. Preserving notification order for the same entity

Multiple workers can process events for the same order in parallel. Example:

~~~text
Event 1: ORDER_PAID
Event 2: ORDER_SHIPPED
Event 3: ORDER_DELIVERED
~~~

If event 2 sends more slowly than event 3, the recipient might receive "delivered" before "shipped."

If ordering matters, choose a strategy:

- Partition by aggregate_id so events for the same entity flow sequentially.
- Claim the next event only once the prior event for the same aggregate has completed per policy.
- Store sequence/version numbers and detect out-of-order arrivals.
- Coalesce older notifications if newer state renders old content obsolete, per business rules.

Not every email needs strict ordering. For critical transactional notifications, define ordering requirements explicitly and accept the throughput trade-off.

## 18. Polling schedules and load throttling

Workers can run via **@Scheduled**:

~~~java
@Scheduled(fixedDelay = 2000)
public void poll() {
    List<ClaimedNotification> batch = claimService.claimBatch(25);
    batch.forEach(processor::process);
}
~~~

fixedDelay measures the pause after the previous run finishes. If a batch takes longer, the next poll starts later. fixedRate or another scheduler can be used, provided you understand overlap and locking.

Example operational configuration:

~~~yaml
mail:
  outbox:
    poll-delay: 2000
    batch-size: 25
    max-attempts: 8
    lease-seconds: 180
    base-backoff-seconds: 30
    max-backoff-seconds: 1800
~~~

The values above are examples. Tune them according to SMTP quotas, response latency, email size, instance count, and business requirements.

### Limiting concurrency

- Use an executor with bounded threads and queue capacity.
- Never claim more records than can be processed within a lease.
- Set SMTP connect/read/write timeouts.
- Respect provider rate limits and quotas.
- Monitor pending record age and retry counts.
- Apply backpressure when SMTP slows down so heap or queues do not fill up.

Do not increase batch sizes and thread counts without monitoring SMTP/database resources. Higher throughput can trade off into more timeouts and retries.

## 19. Separating transactions with distinct Spring beans

A clear design typically has at least three boundaries:

| Bean | Method | Transaction |
|---|---|---|
| OrderApplicationService | Update order + insert outbox | Business transaction |
| OutboxClaimService | Claim batch and set leases | Short claim transaction |
| OutboxMailProcessor | Render and send SMTP | No DB transaction held |
| OutboxResultService | Mark submitted | Separate result transaction |
| OutboxFailureService | Set retry/failed/unknown | Separate result transaction |

Example:

~~~text
OrderApplicationService
  @Transactional
      UPDATE order
      INSERT outbox
      COMMIT

OutboxMailWorker
  calls claimService.claimBatch(...)
      OutboxClaimService @Transactional
          SELECT ... FOR UPDATE SKIP LOCKED
          UPDATE PROCESSING + lease
          COMMIT

  calls processor.process(...)
      render template
      JavaMailSender.send(...)     <-- outside DB transaction
      calls resultService.markSubmitted(...)
          @Transactional(REQUIRES_NEW)
          UPDATE SUBMITTED
          COMMIT
~~~

Spring transactions are typically managed via proxies. An internal self-invocation on the same object to a `@Transactional` method may bypass the proxy. Split services into separate beans or use explicit transaction templates so boundaries work properly.

### Is REQUIRES_NEW needed on every method?

Not necessarily. If the worker has no outer transaction, a `@Transactional` method with default REQUIRED will also open a new transaction. REQUIRES_NEW states independent intent explicitly and helps when a method could be invoked from another transaction. Do not overuse it to mask unclear transaction boundaries.

## 20. Why do @Async or AFTER_COMMIT not fully replace an outbox?

Spring offers mechanisms like **@Async** and **@TransactionalEventListener(phase = AFTER_COMMIT)**. They are useful in some cases, yet do not inherently provide durability like an outbox.

### @Async

~~~java
@Async
public void sendEmailAsync(...) {
    mailSender.send(...);
}
~~~

The method executes on an executor when configured properly. However, if the process stops before the task runs or the executor queue loses in-memory data, the send intent can vanish. `@Async` also does not record durable retry state.

### @TransactionalEventListener(AFTER_COMMIT)

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderShipped(OrderShippedEvent event) {
    mailService.send(event);
}
~~~

The listener runs only after the transaction commits, avoiding sending before business data commits. However, an in-memory event does not automatically become a durable message. The process can stop after commit before the listener completes.

### Outbox

An outbox writes the notification intent to the database in the same business transaction. Workers can read it again after restarts, track status, retry, and observe message age.

You can use `@TransactionalEventListener` to wake the worker after commit for low latency, while outbox polling remains the durable recovery mechanism. Never rely solely on in-memory wake-up signals.

## 21. Controlling recipients, templates, and payloads

An outbox stores durable data; an authorization bug or bad payload can be resent repeatedly. Before rendering/sending, verify:

- Recipient belongs to the right user/tenant for the event.
- Email address is verified per business rules.
- Template key is on an allowlist, never taken as an arbitrary path from requests.
- Locale is validated with a fallback.
- Payload version is supported.
- URLs use HTTPS and controlled domains.
- HTML is contextually escaped.
- Tokens or private data are not logged.

Never store arbitrary client-submitted HTML directly in the outbox and render/send it verbatim. Payloads should hold validated business data; templates remain controlled by the application.

### Versioning payloads

When event schemas evolve, new workers may encounter old records:

~~~json
{
  "schemaVersion": 2,
  "orderId": "ORD-123",
  "orderCode": "ORD-2026-015",
  "trackingNumber": "VN123456"
}
~~~

The JSON example illustrates structure only. Workers should inspect `schemaVersion` and transform older payloads via adapters or maintain compatibility throughout the outbox retention window. Never change payload structure while assuming all older records have already disappeared.

## 22. Outbox security and retention

The outbox can contain recipients, customer names, order numbers, tracking links, and other data. Treat this table like business data:

- Only workers/services with required permissions may read payloads.
- Encrypt sensitive data when system security requirements demand it.
- Restrict payloads to fields genuinely needed for rendering.
- Never store SMTP passwords, access tokens, or sensitive payment details.
- Sanitize error messages before persisting.
- Set retention periods for sent and dead-letter records.
- Enforce deletion/anonymization policies aligned with retention and auditing.
- Protect backups and debug environments since they may also contain payloads.

If the recipient changes after an event is created, the application needs a clear rule: send to the snapshot address from event time or the current verified address. This is a business and privacy decision, not something for a worker to pick arbitrarily.

## 23. Handling failed and dead-letter records

A record may become unprocessable because:

- Template key was deleted.
- Payload is missing required fields.
- Recipient is invalid.
- Attachment file was deleted.
- Security rules reject sending.
- Provider permanently rejected it.

After maximum attempts, move the record to FAILED or DEAD_LETTER, preserve sanitized diagnostic details, and raise an alert.

Handling workflow:

1. Operator inspects notification ID and error code.
2. Identifies whether the fault is data, template, permission, or provider.
3. Fixes the root cause or issues a new notification per business workflow.
4. If replaying the old record, verifies recipient and payload first.
5. Logs operator identity, timestamp, and replay reason.

Never manually edit payloads of already-sent records or bulk-replay without controls. Resending an email can trigger duplicate actions on the recipient's side.

## 24. Worker observability and alerting

Useful metrics:

| Metric | Meaning |
|---|---|
| outbox_pending_count | Number of waiting records |
| outbox_oldest_pending_age | Age of the oldest waiting record |
| outbox_processing_count | Number of currently claimed records |
| outbox_expired_lease_count | Number of expired leases |
| outbox_retry_count | Number of records in retry state |
| outbox_failed_count | Number of dead-letter/failed records |
| mail_send_duration | Time to build and send the message |
| mail_send_success_total | Count of SMTP/provider acceptances |
| mail_send_failure_total | Count of failed sends |
| mail_unknown_outcome_total | Count of uncertain outcomes |

Logs can include:

- Outbox ID and event ID.
- Worker ID and truncated/masked claim token if needed.
- Attempt number.
- Event type and template key.
- Claim, render, send, and result-update timings.
- Provider message ID if available.
- Sanitized error category/code.

Never log full MIME messages, bodies, attachments, or tokens. Those can contain personal information and secrets.

### Recommended alerts

- Pending record age exceeds SLA.
- Retry record count rises continuously.
- Abnormally high expired lease count.
- Worker stops polling or fails to process batches.
- SMTP latency or error rates exceed thresholds.
- Sudden spike in dead-letter records.

## 25. Testing a transactional outbox

Do not merely assert `mailSender.send(...)` was called. Test transaction boundaries and outbox lifecycles.

### Domain/application tests

- Valid transitions update state and create the right outbox record.
- Invalid transitions create no notification.
- Transaction rollbacks leave no outbox record behind.
- Event ID / notification key prevents duplicate record creation.

### Claim tests

- A record is claimed by only one worker at a time.
- Two concurrent workers claim disjoint batches.
- RETRY records are claimed only after next_attempt_at.
- PROCESSING records with expired leases can be reclaimed.
- Stale tokens cannot update results after a record has been reclaimed.

### Processor tests

- Worker renders the right template and invokes the mail sender.
- Successful send updates to SUBMITTED.
- Temporary failures schedule RETRY with a future timestamp.
- Permanent failures transition to FAILED.
- Uncertain errors follow the UNKNOWN policy.
- No DB transaction wraps the SMTP call.

### Integration tests

Use a test database and mock/sandbox SMTP server to verify:

- Business updates and outbox inserts commit/roll back together.
- Claim queries work under locking and concurrency.
- MIME messages have the right recipient, subject, plain text/HTML, and attachments.
- SMTP responses map to the right statuses.
- Restarted workers resume pending/expired records.

Mocking JavaMailSender checks processor logic, yet does not prove real SMTP behavior or delivery semantics. Never send test emails to production recipients.

## 26. Worker flow example with separated transactions

Putting the components together:

~~~java
@Component
public class OutboxPollingJob {

    private final OutboxClaimService claimService;
    private final OutboxMailProcessor processor;

    public OutboxPollingJob(
            OutboxClaimService claimService,
            OutboxMailProcessor processor
    ) {
        this.claimService = claimService;
        this.processor = processor;
    }

    @Scheduled(fixedDelay = 2000)
    public void poll() {
        List<ClaimedNotification> batch =
                claimService.claimBatch(25);

        for (ClaimedNotification item : batch) {
            processor.process(item);
        }
    }
}
~~~

Call sequence:

1. poll() calls claimBatch(...).
2. Spring opens a transaction for OutboxClaimService.
3. Claim service locks rows, updates to PROCESSING, creates tokens/leases, and returns the batch.
4. Claim transaction commits when the method returns.
5. poll() calls processor.process(...).
6. Processor renders, builds MimeMessage, and calls SMTP outside the claim transaction.
7. Processor calls result/failure service to open a separate transaction and update status.
8. Worker moves to the next record.

If the worker stops at step 6, the lease expires and the record can be reclaimed. If SMTP already accepted the message before the worker stopped prior to step 7, the status may be uncertain and the next run carries duplicate risk. That limitation must be managed with idempotency/reconciliation rather than expecting the outbox to eliminate it automatically.

## 27. Common implementation mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Sending SMTP inside business transaction | Prolonged transactions, unsynchronized rollbacks | Write only outbox inside main transaction |
| Committing business data then inserting outbox in another transaction | Notifications lost if process stops between steps | Write outbox in the same transaction |
| Workers only SELECT without claiming | Multiple workers send the same record | Row locks / skip locked or atomic claims |
| Holding row locks during SMTP | DB locks held across network latency | Commit claim transaction before sending |
| No leases | Records stuck in PROCESSING when worker dies | Leases and reclaim |
| No claim tokens | Old worker overwrites new worker's outcome | Token-conditioned updates |
| Infinite retries | Queue grows and provider gets overloaded | Backoff, max attempts, and dead-letter |
| Retrying immediately after ambiguous timeout | Emails may be sent twice | UNKNOWN and reconciliation |
| Calling @Transactional via self-invocation | Transaction boundary may not activate as expected | Separate beans or transaction templates |
| Marking DELIVERED immediately after send | Inaccurate status reporting | Use SUBMITTED and handle delivery events separately |
| Payload has only ID, worker reads current state | Email may misrepresent historical event | Snapshot or versioning |
| Unbounded worker concurrency | Exhausts SMTP/DB quotas, increases timeouts | Bound concurrency and batch sizes |
| Missing indexes on status/time | Polling slows down as outbox grows | Indexes matching queries and retention |
| Storing sensitive payloads indefinitely | Increases data exposure risk | Minimization, access control, and retention |

## 28. When should you use an outbox?

An outbox is especially valuable when:

- Emails must be sent after business changes commit.
- Critical notifications must not be lost on process restarts.
- SMTP can fail temporarily and needs retries.
- Multiple instances/workers exist.
- Visibility into pending, retry, failed, and attempt history is needed.
- Email content must reflect an event snapshot.

For low-priority emails that do not need durable retries and can tolerate loss on process stops, an AFTER_COMMIT listener or async task may suffice. Do not add an outbox just to make code more complex; use it when reliability and operability justify the cost of storage, polling, retries, and cleanup.

## 29. Key takeaways

Reading an outbox and sending mail outside the main transaction separates **business changes**, **notification send intent**, and **SMTP communication** into clearly bounded stages. The main transaction updates data and inserts the outbox atomically. Workers claim records in short transactions, commit leases, and then render and call JavaMailSender without holding a database transaction. Send outcomes or failures are recorded in separate transactions.

A transactional outbox prevents losing send intent across application restarts and supports controlled retries. It does not by itself guarantee exactly-once delivery: timeouts after SMTP may have accepted a message can still leave uncertain outcomes and duplicate sends. Therefore, you need event IDs, claim tokens, leases, backoff, attempt limits, dead-letter handling, reconciliation, and metrics.

**Keep database transactions short, never hold row locks while waiting on SMTP, and update records only with a valid claim token.** That is the foundation for sending email reliably without prolonging business transactions.

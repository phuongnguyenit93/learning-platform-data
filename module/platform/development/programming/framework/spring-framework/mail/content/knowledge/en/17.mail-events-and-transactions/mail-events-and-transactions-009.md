# Updating Outbox Status After Sending

## 1. Why must outbox status be updated?

In a Spring Framework Mail application, emails are often sent after a business operation completes: an order is confirmed, a payment succeeds, an account is created, or an invoice is issued. If the application sends the email directly in the middle of the business transaction, the database can roll back after the email has already been sent, or the database can commit while the application stops before sending the email.

A **transactional outbox** solves most of the coordination problem between the database and event emission by writing the pending event into an outbox table inside the business transaction. A worker reads those records and performs the external action, such as sending email via `JavaMailSender`.

However, writing to the outbox is only the first step. The worker must update each record's status according to the send outcome so the system knows:

- Is the email waiting to be sent, or has a worker picked it up?
- Did SMTP accept the message, or did sending encounter an error?
- When should the record be retried?
- Is there a permanent error requiring transition to a terminal state?
- Is another worker currently processing the same record?

Without controlled status updates, the same email can be sent repeatedly, dropped, or stuck forever in an in-progress state.

Overall flow:

~~~text
Business transaction
        |
        +--> Update business data
        |
        +--> Insert outbox record (PENDING)
        |
        v
      COMMIT
        |
        v
   Outbox worker claims row
        |
        v
   Build/render email
        |
        v
   JavaMailSender.send(...)
        |
        +--> SMTP accepted --> mark SENT
        |
        +--> Send failed ----> RETRY or FAILED
~~~

**Important note:** Outbox status reflects processing progress and outcomes observed by the worker. It does not by itself prove the email reached the Inbox or that the recipient read the message.

## 2. State model for an email outbox entry

A state machine typically includes these states:

| State | Meaning | Eligible for worker pickup? |
| --- | --- | --- |
| `PENDING` | New record waiting for its first processing attempt | Yes |
| `PROCESSING` | A worker has claimed and is processing it with a lease | Only after the lease expires and it is reclaimed |
| `RETRY` | Previous send failed under retry policy; waiting for next attempt time | Yes once `next_attempt_at` is due |
| `SENT` | `JavaMailSender.send` returned normally; SMTP transport accepted the message | No |
| `FAILED` | Exhausted retry attempts or hit an error classified as non-retryable | Not automatically |
| `CANCELLED` (optional) | Business logic cancelled sending before dispatch | No |

States can be simplified based on system needs. What matters is clearly defining **state transition conditions**, who may perform transitions, and when a worker may claim a record.

### 2.1. State transition diagram

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: worker claims
    RETRY --> PROCESSING: due time reached
    PROCESSING --> SENT: SMTP send returns successfully
    PROCESSING --> RETRY: retryable failure
    PROCESSING --> FAILED: permanent failure / max attempts
    PROCESSING --> PROCESSING: lease expires and another worker reclaims
    PENDING --> CANCELLED: business cancellation
    RETRY --> CANCELLED: business cancellation
~~~

Some systems use `NEW` instead of `PENDING`, `IN_PROGRESS` instead of `PROCESSING`, or `DEAD` instead of `FAILED`. Names matter less than consistent semantics and transition rules.

### 2.2. When to mark SENT?

Mark `SENT` **only after** the send call returns normally:

~~~java
mailSender.send(message);
outboxService.markSent(outboxId);
~~~

`JavaMailSender.send(...)` completing normally means transport delivered the message to the SMTP server and the server accepted the operation per protocol. It does not guarantee the message ultimately lands in the Inbox, avoids bouncing, avoids Spam, or is read by the recipient.

Delivery/bounce events, if needed, must be collected through the mail provider's own mechanisms, DSN, or appropriate webhooks. Outbox `SENT` status should only mean **successfully submitted to transport**.

### 2.3. Do not mark SENT before sending

The following sequence can lose emails:

~~~java
outboxService.markSent(outboxId);
mailSender.send(message);
~~~

If the application stops after updating the database but before calling SMTP, the record is already `SENT` and workers will not resend it. The recipient never receives the email even though the outbox reports success.

Therefore, the standard order is **send first, update SENT afterward**. This still leaves another failure window where sending succeeds but the database update fails; later sections explain that limitation.

## 3. Outbox table design

An email outbox table can contain:

| Column | Illustrative data type | Purpose |
| --- | --- | --- |
| `id` | UUID / BIGINT | Record identifier |
| `event_key` | VARCHAR | Business key or idempotency key |
| `recipient` | VARCHAR | Recipient address |
| `template_name` | VARCHAR | Template type to render |
| `template_version` | VARCHAR | Template version if consistent content reproduction is needed |
| `payload` | JSON / TEXT | Snapshot of data required for the email |
| `status` | VARCHAR | PENDING, PROCESSING, RETRY, SENT, FAILED |
| `attempt_count` | INTEGER | Number of dispatch attempts started |
| `next_attempt_at` | TIMESTAMP | Earliest timestamp eligible for retry |
| `lease_owner` | VARCHAR | Worker currently holding processing ownership |
| `lease_until` | TIMESTAMP | Lease expiration timestamp |
| `sent_at` | TIMESTAMP | Timestamp when SMTP accepted the send |
| `last_error_code` | VARCHAR | Normalized error code/category |
| `last_error_message` | TEXT | Error details stripped of sensitive data |
| `created_at`, `updated_at` | TIMESTAMP | Creation and update timestamps |
| `version` | BIGINT | Version for optimistic locking if used |

Not every system needs every column. With concurrent workers, `lease_owner` and `lease_until` or an equivalent claim mechanism prevent two workers from processing the same row simultaneously. `attempt_count` and `next_attempt_at` support bounded retries.

### 3.1. DDL example

PostgreSQL SQL example:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    event_key VARCHAR(160) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_name VARCHAR(160) NOT NULL,
    template_version VARCHAR(80),
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    last_error_code VARCHAR(120),
    last_error_message TEXT,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_mail_outbox_status CHECK (
        status IN (
            'PENDING', 'PROCESSING', 'RETRY',
            'SENT', 'FAILED', 'CANCELLED'
        )
    )
);

CREATE UNIQUE INDEX ux_mail_outbox_event_key
    ON mail_outbox(event_key);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox(status, next_attempt_at, created_at);

CREATE INDEX ix_mail_outbox_lease
    ON mail_outbox(status, lease_until);
~~~

This is a reference schema. A unique constraint on `event_key` is suitable only if business rules guarantee one event key corresponds to strictly one email. If an event sends to multiple recipients, use a unique key incorporating recipient/delivery identity, or create a separate outbox record per email delivery.

`payload` should contain a sufficient snapshot to render the email per business requirements. If payloads include personal info, email addresses, or tokens, enforce encryption, read permissions, retention windows, and data deletion policies. Never store passwords or unnecessary secrets in the outbox.

### 3.2. Creating outbox entries in the same business transaction

Example:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public void confirmOrder(String orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        MailOutboxEntry entry = MailOutboxEntry.pending(
                UUID.randomUUID(),
                "order-confirmed:" + order.getPublicId(),
                order.getCustomerEmail(),
                "order-confirmation",
                createMailPayload(order));

        outboxRepository.save(entry);
    }
}
~~~

`createMailPayload` is a helper creating a snapshot containing only the required email data. If the transaction commits, both the order update and the outbox record exist. If the transaction rolls back, both roll back.

Workers read the outbox after the transaction commits. This avoids sending an email for an uncommitted business change.

## 4. Claiming records with a lease before sending

When running multiple workers or application instances, you cannot simply do:

~~~java
List<MailOutboxEntry> rows = repository.findByStatus("PENDING");
~~~

Two workers can read the same row before either updates the status. Both think they own the send and create duplicates.

One solution is **claiming** records inside a database transaction:

1. Select rows that are due and not currently leased by another worker.
2. Lock/select them using a concurrency-safe mechanism.
3. Transition status to `PROCESSING`.
4. Write `lease_owner` and `lease_until`.
5. Commit the claim transaction.
6. Only after commit, perform the SMTP send.

A lease is a time-bounded ownership grant. If a worker dies, the lease expires and another worker can reclaim the row.

### 4.1. PostgreSQL: FOR UPDATE SKIP LOCKED

A batch claim query can be written as:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE
        (
            status IN ('PENDING', 'RETRY')
            AND next_attempt_at <= now()
        )
        OR
        (
            status = 'PROCESSING'
            AND lease_until < now()
        )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS o
SET status = 'PROCESSING',
    lease_owner = :worker_id,
    lease_until = :lease_until,
    attempt_count = o.attempt_count + 1,
    updated_at = now(),
    version = o.version + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.*;
~~~

The query above is for PostgreSQL. `FOR UPDATE SKIP LOCKED` lets workers skip rows currently locked by another transaction instead of waiting and claiming duplicates. `UPDATE ... RETURNING` returns the newly claimed rows.

The `PROCESSING` condition with an expired lease enables recovery of rows stuck when a worker dies or loses connectivity. Reclaims should be monitored because an old worker might still be running after a long pause; result updates must check `lease_owner` so an old worker cannot overwrite a newer worker's outcome.

For other databases, claim syntax may differ. You can use pessimistic locks, conditional atomic updates, or your database's queue mechanisms. Never copy PostgreSQL SQL blindly into every database without checking dialect support.

### 4.2. Commit the claim before calling SMTP

The claim transaction should end before sending. Keeping a database transaction open throughout SMTP calls can:

- Hold row locks longer when mail servers are slow.
- Increase contention and transaction wait times.
- Tie up connection pool slots during network waits.
- Trigger database rollbacks even after SMTP already accepted the email.

Split into two stages:

~~~text
Transaction A: claim row -> PROCESSING -> COMMIT
                           |
                           v
                   SMTP send outside DB transaction
                           |
               +-----------+-----------+
               |                       |
               v                       v
Transaction B: mark SENT       Transaction B: mark RETRY/FAILED
               |                       |
               +-----------+-----------+
                           v
                         COMMIT
~~~

SMTP is external to the database; a JDBC transaction cannot roll back an email already accepted by an SMTP server.

## 5. Updating to SENT after a successful send

After `JavaMailSender.send(message)` returns normally, the worker updates the outbox:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    sent_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = NULL,
    last_error_message = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

The `status` and `lease_owner` conditions ensure a worker updates only the record it owns. In systems using optimistic locking, you can add `AND version = :claimed_version`. If the updated row count is 0, ownership expired or another worker reclaimed the row.

### 5.1. Why must you check the updated row count?

Never ignore the update count:

~~~java
int updated = repository.markSent(id, workerId);
if (updated != 1) {
    // Record conflict state for operations handling.
}
~~~

If the update matches 0 rows, the worker cannot assert the database recorded `SENT`. However, since the SMTP send just succeeded, **never treat the email as unsent**. This situation warrants an alert/reconciliation because another execution may retry and produce a duplicate email.

### 5.2. What does sent_at mean?

`sent_at` should be the timestamp when the application confirmed the send call succeeded and updated status. If you need to separate when SMTP accepted from when the database recorded it, store a separate `smtp_accepted_at` or a worker-observed timestamp.

Do not name this field `delivered_at` if the system has not received delivery proof from the provider. Column names should reflect the exact event the application actually observed.

## 6. Updating to RETRY or FAILED when sending fails

If the worker catches an error while preparing or sending an email, it must decide whether the record can be retried.

One classification scheme:

| Error type | Example | Typically suitable action |
| --- | --- | --- |
| Temporary error | SMTP server temporarily unreachable, connection timeout before sending data, provider returns transient error | `RETRY` with backoff |
| Configuration/permanent error | Wrong credentials, sender rejected by policy, invalid address/message format | `FAILED` or hold in operations queue until config is fixed |
| Data/template error | Missing required variable, missing template, invalid payload | `FAILED` and investigate data/code |
| Indeterminate outcome | Connection lost after message was sent but before receiving response | Retry policy may create duplicates; explicitly record uncertainty |

Not every Spring Mail exception can be classified by class name alone. For instance, `MailSendException` can wrap a transient network error or a recipient rejection. Inspect the cause and SMTP response details provided by the provider. Authentication errors are usually configuration faults requiring alerts rather than rapid repeated retries.

### 6.1. Updating status after an error

An illustrative PostgreSQL query:

~~~sql
UPDATE mail_outbox
SET status = CASE
        WHEN attempt_count >= :max_attempts THEN 'FAILED'
        ELSE 'RETRY'
    END,
    next_attempt_at = CASE
        WHEN attempt_count >= :max_attempts THEN next_attempt_at
        ELSE :next_attempt_at
    END,
    last_error_code = :error_code,
    last_error_message = :safe_error_message,
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

While attempts remain, the row transitions to `RETRY` and `next_attempt_at` is set using backoff. Once the limit is reached, the row transitions to `FAILED` so automatic retries do not continue infinitely.

The `lease_owner` condition protects the row from stale workers. If the update returns 0 rows, the worker no longer owns that record; log the conflict and feed it into monitoring.

### 6.2. Exponential backoff and jitter

Retrying immediately can create a load spike when the SMTP provider is degraded. A common policy is exponential backoff:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where:

- `d_0` is the initial wait duration.
- `n` is the number of dispatch attempts started.
- `d_max` is the maximum wait cap.

Adding random jitter prevents multiple workers from retrying simultaneously at the same instant:

\[
d_{\text{scheduled}} = d_n + U(0,j)
\]

Configuration example:

| Attempt | Illustrative base delay |
| --- | --- |
| 1 | 30 seconds |
| 2 | 1 minute |
| 3 | 2 minutes |
| 4 | 4 minutes |
| 5 | 8 minutes |
| Subsequent attempts | Increases up to the configured cap |

This is a policy example, not a fixed rule. Systems should choose caps, jitter, and attempt counts based on SLAs, provider limits, and email type. Password reset emails may have tighter deadlines than invoice emails.

### 6.3. Do not retry permanent errors in a tight loop

Bad example:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException ex) {
        // Retry immediately.
    }
}
~~~

This loop burns CPU, overloads the SMTP provider, and pins the worker on a single message. Record the attempt in the database, set `next_attempt_at`, and let the scheduler/worker pick it up later.

### 6.4. Storing error details safely

Store:

- Exception type or normalized error code.
- SMTP response code if available and exposed by the provider.
- Failure timestamp and attempt count.
- Brief details sufficient for operations investigation.

Never store raw email bodies, credentials, access tokens, or full exceptions that may contain addresses/sensitive details in error columns. Sanitize and truncate `last_error_message`.

## 7. Failure window between SMTP and the database

A critical point of a transactional outbox is that the database and SMTP do not share a distributed transaction. Therefore, **exactly-once email delivery** cannot be guaranteed solely through outbox status updates.

### 7.1. Case A: send succeeds, application dies before updating SENT

Sequence:

~~~text
Worker claims row -> PROCESSING
        |
        v
SMTP accepts email
        |
        v
Application process crashes
        |
        v
Database row still PROCESSING
        |
        v
Lease expires; another worker claims row
        |
        v
Email may be sent again
~~~

The first email may already have been accepted by the SMTP server, yet the database has not recorded `SENT`. When the lease expires, another worker may resend it. This is the **duplicate window** of at-least-once delivery.

### 7.2. Case B: mark SENT first, then sending fails

~~~text
Database row -> SENT
        |
        v
Application crashes before SMTP send
        |
        v
Worker will not pick row again
        |
        v
Email is lost
~~~

This is why you must not update `SENT` before calling SMTP.

### 7.3. Indeterminate send outcome due to timeout

The application may transmit most or all of the message to the SMTP server and lose the connection before receiving the final response. The worker does not know whether the server accepted the message.

If it retries, there is duplicate risk. If it does not retry, the email may never have been accepted and gets lost. No single SQL statement can resolve uncertainty about whether an external system received data.

For critical emails, you can add an `UNKNOWN` or `NEEDS_RECONCILIATION` status to route ambiguous cases to a manual/provider reconciliation queue. If the system accepts at-least-once and minor duplicates are tolerable, the worker may retry with clear alerting.

### 7.4. Message-ID is not an idempotency guarantee

You can generate a stable Message-ID for the same outbox event to aid tracing:

~~~java
message.setHeader("Message-ID", stableMessageId);
~~~

However, **do not assume every SMTP server or mail client automatically drops duplicate emails merely because Message-ID matches**. Message-ID is useful for correlation and debugging, not a universal exactly-once mechanism.

If the provider offers an email-sending API supporting an idempotency key, use a stable key per delivery/event. The provider can guarantee not creating two sends for the same key within its documented scope and retention window. With plain SMTP, applications usually must accept an at-least-once model and design content/email workflows to minimize duplicate harm.

## 8. Separating claim, send, and state-update transactions in Spring

Do not hold a database transaction open during SMTP network calls. Split into three components:

- `OutboxClaimService`: claims batches in a short transaction.
- `MailDispatchWorker`: processes each record and calls `JavaMailSender` outside any transaction.
- `OutboxStateService`: updates `SENT`, `RETRY`, or `FAILED` in a new transaction.

### 8.1. Record representing a claimed entry

~~~java
public record ClaimedMail(
        UUID id,
        String recipient,
        String templateName,
        String payloadJson,
        int attemptCount,
        long version,
        String leaseOwner) {
}
~~~

The worker receives a claimed data snapshot. There is no need to keep a mutable JPA entity and persistence session open throughout email sending.

### 8.2. Claim service with its own transaction

~~~java
@Service
public class OutboxClaimService {

    private final MailOutboxRepository repository;
    private final String workerId;

    public OutboxClaimService(
            MailOutboxRepository repository,
            WorkerIdentity workerIdentity) {
        this.repository = repository;
        this.workerId = workerIdentity.id();
    }

    @Transactional
    public List<ClaimedMail> claimBatch(
            int batchSize,
            Instant leaseUntil) {

        return repository.claimDue(
                batchSize,
                workerId,
                leaseUntil);
    }
}
~~~

`repository.claimDue` must execute an atomic claim operation matching your database. The method returns after Spring commits the transaction, so the outer worker can send without holding the claim transaction's row locks.

### 8.3. Status update service

~~~java
@Service
public class OutboxStateService {

    private final MailOutboxRepository repository;

    public OutboxStateService(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public boolean markSent(ClaimedMail mail) {
        return repository.markSent(
                mail.id(),
                mail.leaseOwner(),
                mail.version()) == 1;
    }

    @Transactional
    public boolean markRetry(
            ClaimedMail mail,
            Instant nextAttemptAt,
            String errorCode,
            String safeErrorMessage) {

        return repository.markRetry(
                mail.id(),
                mail.leaseOwner(),
                mail.version(),
                nextAttemptAt,
                errorCode,
                safeErrorMessage) == 1;
    }

    @Transactional
    public boolean markFailed(
            ClaimedMail mail,
            String errorCode,
            String safeErrorMessage) {

        return repository.markFailed(
                mail.id(),
                mail.leaseOwner(),
                mail.version(),
                errorCode,
                safeErrorMessage) == 1;
    }
}
~~~

Repository methods must update conditionally by ID, status, owner, and version so a stale worker cannot overwrite a newer result. The returned `boolean` indicates whether exactly one row was updated.

### 8.4. Worker sending email outside transactions

~~~java
@Service
public class MailDispatchWorker {

    private final OutboxClaimService claimService;
    private final OutboxStateService stateService;
    private final MailMessageFactory messageFactory;
    private final JavaMailSender mailSender;
    private final RetryPolicy retryPolicy;
    private final FailureClassifier failureClassifier;

    public MailDispatchWorker(
            OutboxClaimService claimService,
            OutboxStateService stateService,
            MailMessageFactory messageFactory,
            JavaMailSender mailSender,
            RetryPolicy retryPolicy,
            FailureClassifier failureClassifier) {
        this.claimService = claimService;
        this.stateService = stateService;
        this.messageFactory = messageFactory;
        this.mailSender = mailSender;
        this.retryPolicy = retryPolicy;
        this.failureClassifier = failureClassifier;
    }

    public void dispatchBatch(
            int batchSize,
            Duration leaseDuration) {

        Instant leaseUntil = Instant.now().plus(leaseDuration);
        List<ClaimedMail> batch =
                claimService.claimBatch(batchSize, leaseUntil);

        for (ClaimedMail mail : batch) {
            dispatchOne(mail);
        }
    }

    private void dispatchOne(ClaimedMail mail) {
        try {
            MimeMessage message = messageFactory.create(mail);
            mailSender.send(message);

            boolean updated = stateService.markSent(mail);
            if (!updated) {
                // SMTP may have accepted the email, but the worker lost its lease.
                // Emit metric/alert and route to reconciliation workflow.
                reportStateConflict(mail.id(), "SENT");
            }
        } catch (MailException ex) {
            handleFailure(mail, ex);
        } catch (MailContentException ex) {
            stateService.markFailed(
                    mail,
                    "CONTENT_ERROR",
                    safeMessage(ex));
        }
    }

    private void handleFailure(ClaimedMail mail, MailException ex) {
        FailureDecision decision = failureClassifier.classify(ex);

        if (decision.retryable()
                && mail.attemptCount() < retryPolicy.maxAttempts()) {
            Instant nextAttempt = retryPolicy.nextAttemptAt(
                    mail.attemptCount());
            boolean updated = stateService.markRetry(
                    mail,
                    nextAttempt,
                    decision.code(),
                    safeMessage(ex));
            if (!updated) {
                reportStateConflict(mail.id(), "RETRY");
            }
        } else {
            boolean updated = stateService.markFailed(
                    mail,
                    decision.code(),
                    safeMessage(ex));
            if (!updated) {
                reportStateConflict(mail.id(), "FAILED");
            }
        }
    }

    private String safeMessage(Exception ex) {
        return ex.getClass().getSimpleName();
    }

    private void reportStateConflict(UUID id, String expectedState) {
        // Log/emit metric/alert; do not resend immediately inside this method.
    }
}
~~~

This is an illustrative skeleton; add imports, repository implementations, policies, and factories per your application. `MailContentException` is an application exception representing classified data/template errors. `FailureClassifier` decides error categories from causes/provider responses; do not treat every `MailException` as retryable.

An important detail: `dispatchBatch` has no `@Transactional`. `claimBatch` and the state-update methods are calls into separate beans with their own transactions. This prevents the claim transaction from spanning the SMTP call.

### 8.5. Note on Spring transaction proxies

In Spring, `@Transactional` is typically applied via proxies. If a method in the same class calls another `@Transactional` method on itself (self-invocation), the internal call may bypass the proxy and the annotation may not apply as expected.

Extracting `OutboxClaimService` and `OutboxStateService` into separate beans keeps transaction boundaries clear. You can also use `TransactionTemplate` when explicit transaction control is needed.

## 9. Claim leases, timeouts, and long-running workers

Leases should exceed the maximum expected duration of a send operation, without being so long that records stay stuck for ages when a worker dies.

Example:

| Parameter | Meaning |
| --- | --- |
| `mail.smtp.connectiontimeout` | Time limit to open SMTP connection |
| `mail.smtp.timeout` | Time limit waiting for SMTP read response |
| `mail.smtp.writetimeout` | Time limit writing data to SMTP |
| `lease_duration` | Duration a worker holds ownership of a row |
| `max_attempts` | Maximum number of dispatch attempts |

SMTP timeouts must be configured so workers do not hold leases indefinitely. If processing can outlast the lease, the worker must **renew the lease (heartbeat)** in a short transaction and check the renewal result before continuing.

### 9.1. Renewing a lease

Conditional update example:

~~~sql
UPDATE mail_outbox
SET lease_until = :new_lease_until,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

If no row is updated, the worker has lost its lease. Do not start new side effects. If an SMTP send is already underway, already-sent bytes cannot be recalled; that is another reason to bound timeouts and choose suitable leases.

### 9.2. An old worker must not overwrite a new worker's result

Suppose worker A claims a row, pauses too long, and its lease expires. Worker B reclaims and sends. Later worker A wakes up and tries to update `SENT` or `RETRY`.

The `lease_owner` and `version` conditions in the update prevent worker A from overwriting state owned by worker B. You can use a monotonically increasing **fencing token** (version/generation) so every state update must carry the token of the current claim.

A fencing token protects database state. It cannot stop an old worker from continuing an already-started SMTP call; to reduce that risk, combine timeouts, leases, and duplicate-tolerant design.

## 10. Classifying Spring Mail exceptions

`JavaMailSender` throws exceptions from the `org.springframework.mail` hierarchy when preparing or sending messages. Common types:

| Exception | What it can indicate | Handling approach |
| --- | --- | --- |
| `MailAuthenticationException` | SMTP authentication or credential/policy error | Usually needs config fix and alert; avoid rapid retries |
| `MailSendException` | Transport failed to send one or more messages; may contain per-message errors | Inspect cause and provider response to decide retry |
| `MailPreparationException` | Failed to prepare the message | Usually data/template/config error; investigate |
| `MailParseException` | Error parsing/preparing mail data | Usually not fixed by immediate retry |
| `MailException` | Base class for mail errors | Insufficient by class name alone to conclude retryable |

Conceptual classification example:

~~~java
public record FailureDecision(
        boolean retryable,
        String code) {
}

public class FailureClassifier {

    public FailureDecision classify(MailException exception) {
        if (exception instanceof MailAuthenticationException) {
            return new FailureDecision(false, "SMTP_AUTH");
        }

        if (exception instanceof MailPreparationException
                || exception instanceof MailParseException) {
            return new FailureDecision(false, "MAIL_PREPARATION");
        }

        if (exception instanceof MailSendException) {
            // Must inspect nested cause / SMTP response code.
            // Do not default every MailSendException to temporary.
            return classifyTransportFailure(exception);
        }

        return classifyTransportFailure(exception);
    }

    private FailureDecision classifyTransportFailure(Throwable cause) {
        // Example: connection refused/timeout may be retryable.
        // SMTP 4xx errors are typically temporary; 5xx typically require permanent handling.
        // Exact determination depends on provider and nested exceptions.
        return new FailureDecision(true, "SMTP_TRANSPORT");
    }
}
~~~

`classifyTransportFailure` is a placeholder showing where policy belongs; **do not put logic returning true for all errors directly into production**. Inspect nested causes, SMTP response codes, and provider details. Timeouts after transmitting the message can have ambiguous outcomes, so retryable does not guarantee the email was never accepted.

### 10.1. SMTP 4xx and 5xx responses

At the protocol level, SMTP 4xx responses usually indicate temporary errors; 5xx responses usually indicate errors that cannot be resolved by an identical retry. However, the application must interpret responses in context:

- Temporary connection errors or overloaded providers can be retried after backoff.
- Senders rejected by policy or invalid addresses usually require fixing data/configuration.
- Failures after the server received DATA where the response was lost may leave an indeterminate final state.

Not every Jakarta Mail implementation exposes the same exception types or response codes. For fine-grained classification, base logic on your specific provider/transport implementation and test it in the matching environment.

## 11. A scheduled dispatcher

The worker can be triggered periodically via Spring scheduling:

~~~java
@Component
public class MailOutboxScheduler {

    private final MailDispatchWorker worker;

    public MailOutboxScheduler(MailDispatchWorker worker) {
        this.worker = worker;
    }

    @Scheduled(fixedDelayString = "${mail.outbox.poll-delay:2000}")
    public void poll() {
        worker.dispatchBatch(
                20,
                Duration.ofMinutes(2));
    }
}
~~~

This example assumes scheduling is enabled with `@EnableScheduling`, workers are configured, and SMTP timeouts are set appropriately. `fixedDelay` measures wait time after the previous invocation completes; if higher throughput is needed, use a worker pool or separate queue while keeping claim safety intact.

Corresponding worker signature:

~~~java
public void dispatchBatch(int batchSize, Duration leaseDuration) {
    Instant leaseUntil = Instant.now().plus(leaseDuration);
    List<ClaimedMail> batch =
            claimService.claimBatch(batchSize, leaseUntil);

    for (ClaimedMail mail : batch) {
        dispatchOne(mail);
    }
}
~~~

### 11.1. Limiting batch size

Do not claim too many records if a worker processes sequentially and each send can take several seconds. Rows at the end of the batch may hit lease expiration before their turn to send.

Choose batch size based on:

- Average and p95/p99 SMTP send durations.
- Number of concurrent workers.
- Lease duration and timeouts.
- SMTP provider rate limits.
- Impact if a worker stops mid-batch.

For large volumes, claim in small groups, scale the worker pool, or renew leases for active items. Never claim hundreds of emails and leave them sitting in memory while leases tick down.

### 11.2. Do not exceed provider concurrency limits

Multiple workers boost throughput, yet SMTP connections and send rates must be bounded. You can apply:

- Bounded thread pools.
- Rate limiters per provider or sender account.
- Batch size and polling intervals.
- Global backoff when the provider returns frequent temporary errors.
- Circuit breakers to pause provider calls temporarily when error rates spike.

Circuit breakers do not replace outbox state. While a circuit is open, records must stay in `RETRY` or wait until due—never mark them `SENT`.

## 12. Idempotency and preventing duplicate outbox records

A transactional outbox ensures event records are saved in the business transaction, yet a business request can be resent due to client retries or duplicate event handlers. If each run inserts a new outbox row, workers will send duplicate emails.

A stable business key helps deduplicate:

~~~text
event_key = "order-confirmed:" + publicOrderId
~~~

Place a unique constraint on the key matching the definition of a single send. On insert conflict, the application service must handle per policy: ignore the already-created event or verify the existing record.

PostgreSQL SQL example:

~~~sql
INSERT INTO mail_outbox (
    id, event_key, recipient, template_name, payload, status
)
VALUES (
    :id, :event_key, :recipient, :template_name, :payload, 'PENDING'
)
ON CONFLICT (event_key) DO NOTHING;
~~~

If the same order can legitimately send multiple emails (e.g., confirmation, shipping update, invoice), the key must include **event type and version/occurrence**, not just the order ID.

### 12.1. Outbox deduplication does not equal SMTP deduplication

A unique key prevents creating two rows for the same event. It does not eliminate the duplicate window after SMTP accepts an email but before the database updates to `SENT`.

These are two separate layers:

1. **Idempotency at outbox creation:** prevents creating multiple delivery records for the same event.
2. **Idempotency at dispatch:** prevents the provider from executing the same delivery twice if the provider supports idempotency keys.

Plain SMTP lacks a standard idempotency-key mechanism universally enforced by all servers. Therefore, never claim a transactional outbox guarantees exactly-once email.

### 12.2. One record per recipient

When sending to multiple recipients, consider creating a separate delivery/outbox record per recipient. This helps:

- Track status per address independently.
- Retry a failed recipient without resending to already-succeeded recipients.
- Handle partial failures more cleanly.
- Limit personal data appearing in each recipient's message.

If multiple recipients are passed in a single `send`, the provider may accept some addresses and reject others. `MailSendException` may report failed messages, yet tracking per-recipient delivery becomes complex. One record per recipient is usually easier to operate for transactional emails.

## 13. Handling FAILED records and redrive workflows

`FAILED` should be the terminal state of automatic retries, not a signal that data is deleted or unrecoverable. Operations may need to:

- Inspect error codes, attempt counts, and failure timestamps.
- Fix SMTP configuration or template data.
- Determine whether the record is still eligible to send.
- Transition the record back to `RETRY` or create a new delivery per audit policy.
- Record who triggered the redrive, why, and when.

Never run a bulk reset turning all `FAILED` rows back to `PENDING` without checking root causes. If the recipient is invalid, retries will keep failing; if credentials are wrong, fix credentials first.

Controlled redrive statement example:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    next_attempt_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'FAILED';
~~~

This is only an illustrative status statement. Real operational actions must verify the root cause is fixed, enforce operator authorization, and write an audit record. Never arbitrarily mutate payloads or recipients on an old record to redirect it to someone else.

### 13.1. Dead-letter queue or terminal status

At high volume, terminally failed records can be moved to a dead-letter table or kept as `FAILED` in the same table with full metadata. Purpose:

- Prevent workers from retrying infinitely.
- Preserve diagnostic details for investigation.
- Monitor failure rates by template, provider, and event type.
- Enable controlled redrives.

Do not delete outbox rows immediately on successful send if the system needs auditing or duplicate-event protection. Archive/partition older data per retention policy.

## 14. Operational metrics to monitor

Looking only at sent email counts is not enough to know whether the outbox is healthy. Track:

| Metric | Meaning |
| --- | --- |
| `outbox_pending_count` | Number of records waiting for processing |
| `outbox_processing_count` | Number of records currently holding a lease |
| `outbox_retry_count` | Number of records waiting for retry |
| `outbox_failed_count` | Number of terminally failed records |
| `outbox_oldest_pending_age` | Age of the oldest waiting record |
| `outbox_send_success_total` | Total sends accepted by transport |
| `outbox_send_failure_total` | Total failed dispatch attempts |
| `outbox_send_duration` | Time spent calling SMTP |
| `outbox_lease_expired_total` | Count of expired/reclaimed leases |
| `outbox_state_conflict_total` | Count of updates failing owner/version match |
| `outbox_retry_exhausted_total` | Count of records exhausting max attempts |

Alerts can trigger when:

- `PENDING` records exceed SLA age.
- `PROCESSING` count spikes abnormally or leases expire repeatedly.
- SMTP failure rate exceeds threshold.
- `FAILED` spikes by template or recipient domain.
- State update conflicts appear after successful sends.

Metric labels must not contain recipient emails, tokens, or high-cardinality personal IDs. Use template type, provider, error category, and environment as dimensions instead.

### 14.1. Logs with correlation IDs

Logs should include `outboxId` or a sanitized event key to correlate:

~~~text
outboxId=...
eventType=ORDER_CONFIRMED
template=order-confirmation
attempt=2
worker=mail-worker-3
result=RETRY
errorCode=SMTP_TEMPORARY
~~~

Do not log full payloads, email content, verification tokens, passwords, or SMTP credentials. Correlation IDs trace a delivery without putting sensitive data into logs.

## 15. Testing outbox status updates

Tests should cover state transitions and critical failure windows, not just verify that a repository was called.

### 15.1. Worker unit test: successful send

Scenario:

1. Claim service returns one `PROCESSING` row.
2. Message factory builds a valid message.
3. Mock `JavaMailSender.send` returns normally.
4. State service is called to mark `SENT`.
5. No retry or failed calls occur.

Example:

~~~java
@Test
void marksOutboxSentAfterSuccessfulMailSend() {
    ClaimedMail claimed = sampleClaimedMail();
    when(claimService.claimBatch(anyInt(), any()))
            .thenReturn(List.of(claimed));

    worker.dispatchBatch(10, Duration.ofMinutes(2));

    verify(mailSender).send(any(MimeMessage.class));
    verify(stateService).markSent(claimed);
    verify(stateService, never())
            .markRetry(any(), any(), anyString(), anyString());
}
~~~

The example assumes JUnit/Mockito and matching worker dependencies. You may need to stub `messageFactory.create` and `markSent` depending on your actual implementation.

### 15.2. Worker unit test: temporary error

Scenario:

1. `mailSender.send` throws a `MailException` classified as retryable.
2. Worker computes `next_attempt_at`.
3. Worker calls `markRetry`.
4. `markSent` is never called.

Verify the retry timestamp is in the future and follows the backoff policy; do not assert an exact timestamp if the policy includes jitter.

### 15.3. Worker unit test: permanent error

For example, a data/template or credential error classified by policy as terminal:

- Worker calls `markFailed`.
- `markRetry` is not called.
- Error code is normalized.
- Error message contains no tokens or email contents.

### 15.4. Repository integration tests

With a real database or Testcontainers, verify:

- Eligible `PENDING` rows are claimed.
- `RETRY` rows are claimed only once `next_attempt_at` is due.
- `PROCESSING` rows with active leases are not claimed again.
- `PROCESSING` rows with expired leases can be reclaimed.
- Two concurrent transactions/workers never claim the same row.
- `SENT` updates require matching lease owner/version.
- Stale workers cannot overwrite rows reclaimed by a newer worker.
- Retries exceeding max attempts transition to `FAILED`.

Claim SQL is database-dependent, so test against the same production database engine or a compatible version. H2 may not accurately simulate PostgreSQL `SKIP LOCKED` or concurrency behavior.

### 15.5. Testing crash windows

You can simulate:

| Stop point | DB state | Expectation |
| --- | --- | --- |
| After outbox insert, before business commit | Transaction rolled back | No committed outbox row exists |
| After claim, before SMTP send | `PROCESSING` | Lease expires, another worker reclaims |
| Explicit SMTP send failure | `PROCESSING` before update | Transitions to `RETRY` or `FAILED` |
| SMTP accepted, before marking SENT | `PROCESSING` | May retry and duplicate; must be recognized as an at-least-once window |
| Marking SENT commits successfully | `SENT` | Not automatically resent |
| Marking SENT hits DB outage after SMTP success | `PROCESSING` until lease expiry | Alert and handle duplicate risk |

Mock unit tests cannot prove exactly-once. Clearly understand and accept the behavior when external side effects succeed while the database has not recorded them yet.

## 16. Common design mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Marking `SENT` before SMTP | Email may be lost if process stops | Send first, update afterward |
| Holding DB transaction while sending | Locks/connections held for long durations | Claim, commit, send, and update in separate transactions |
| Reading `PENDING` without atomic claim | Multiple workers send the same email | Atomic claim, locks, or leases |
| No lease expiration | Rows can stay stuck in `PROCESSING` forever | Leases and conditional reclaim |
| Not checking lease owner/version | Stale worker overwrites newer result | Conditional updates / fencing tokens |
| Retrying every exception infinitely | Spams provider, ties up workers | Error classification, backoff, and max attempts |
| Immediate retry | Creates retry storms | Exponential backoff + jitter |
| Treating successful `send` as Inbox delivery | Inaccurate delivery reporting | Define SENT as SMTP accepted; track bounces separately |
| Trusting Message-ID to block duplicates | Duplicates can still occur | Provider idempotency if available; accept at-least-once with SMTP |
| Logging raw exceptions/payloads | Leaks PII/tokens | Normalized error codes and sanitized messages |
| Multiple recipients in one row | Hard to handle partial failures | One delivery row per recipient when needed |
| Deleting rows right when SENT | Loses audit/dedupe evidence | Policy-based retention/archival |

## 17. Frequently asked questions

**"When should outbox be updated to SENT?"**  
After `JavaMailSender.send` returns normally and before finishing row processing. If the database update fails, the row is not confirmed as SENT even though SMTP may have received the message.

**"Does SENT mean the email landed in the Inbox?"**  
No. It only means the send call through transport completed successfully as observed by the application. Bounces, spam filtering, and delivery status require separate tracking mechanisms.

**"Can one transaction wrap both the database and SMTP?"**  
A standard JDBC transaction cannot roll back SMTP. Keeping a transaction open while sending also increases lock and connection hold times. Use short transactions to claim/update state, and send outside transactions.

**"Why not mark SENT before sending and roll back if sending fails?"**  
Database rollback cannot recall a sent email, and the process can stop before sending. That approach risks losing emails. Sending first and updating afterward produces at-least-once with a duplicate window.

**"Does a transactional outbox guarantee exactly-once?"**  
No. It synchronizes business changes and event persistence in the database, but does not create a distributed transaction with SMTP. Dispatch typically has at-least-once semantics.

**"Should MailSendException be retried?"**  
Do not classify solely by class name. Inspect nested causes and SMTP responses. Some transient errors can be retried; address, policy, or configuration errors usually need different handling.

**"What happens if a worker dies while PROCESSING?"**  
Lease expiration allows another worker to reclaim the row. Conditional updates are needed so a stale worker cannot overwrite newer state.

**"How long should a lease be?"**  
Base it on SMTP connect/read/write timeouts and expected processing duration. If tasks outlast the lease, use heartbeats. Never leave SMTP timeouts unbounded.

**"Should timeouts be retried?"**  
Timeouts before connecting/sending can usually be retried. Timeouts after transmitting the message can have indeterminate outcomes; retries may duplicate. Policy must weigh email criticality and provider idempotency capabilities.

**"Can Message-ID be used as an idempotency key?"**  
It can be used for tracing and correlation, yet SMTP servers are not required to deduplicate by Message-ID. Relying on it alone does not guarantee exactly-once.

**"Do I need per-recipient status?"**  
If sending to multiple people and needing per-recipient retries/reconciliation, use one delivery record per recipient. That way one bad address does not force resending to everyone.

**"Does FAILED mean the record must be deleted?"**  
No. FAILED is usually the terminal state for automatic retries, retained for auditing and redriving after fixing the root cause.

## 18. Key takeaways for updating outbox status after sending

Typical flow:

~~~text
Business transaction
  - update domain state
  - insert outbox row (PENDING)
  - COMMIT
          |
          v
Outbox worker
  - atomically claim row
  - set PROCESSING + lease
  - COMMIT
          |
          v
Build and send message outside DB transaction
          |
      +---+---+
      |       |
      v       v
    Success  Failure
      |       |
      v       v
   mark SENT  classify exception
      |       |
      |    +--+---+
      |    |      |
      |    v      v
      |  RETRY  FAILED
      |    |
      |    v
      |  next_attempt_at + backoff
      |
      v
    COMMIT
~~~

When implementing in Spring Framework Mail:

1. Write the outbox in the same business transaction.
2. Claim batches using atomic database operations and leases.
3. Commit claims before calling SMTP.
4. Send via `JavaMailSender` outside any database transaction.
5. If send returns normally, update to `SENT` in a short transaction.
6. On failure, classify and update to `RETRY` or `FAILED` with error codes, backoff, and attempt limits.
7. Use lease owner/version to prevent stale workers from overwriting newer worker state.
8. Monitor the duplicate window between SMTP accepted and database commit; do not claim exactly-once when using plain SMTP.

Outbox status is the basis for worker recovery after errors, operational backlog visibility, and controlled retries. Updating status at the right time, conditionally, and in separate transactions prevents lost emails, limits duplicates, and keeps processing history consistent with what the application actually observed.

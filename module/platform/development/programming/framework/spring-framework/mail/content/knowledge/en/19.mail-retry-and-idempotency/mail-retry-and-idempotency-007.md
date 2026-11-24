# Idempotency When Workers Re-Read the Outbox

In a Spring Framework Mail application, sending emails is commonly decoupled from the business transaction: a service updates an order status and inserts an **outbox** record, and later a worker reads the outbox and calls `JavaMailSender`. This avoids situations where the database transaction commits while the notification process is lost without a trace.

However, an outbox does not automatically guarantee an email is sent only once. A worker can re-read the same job during restarts, retries, timeouts, lease expirations, or concurrent polling across multiple instances. Worse yet, the SMTP relay may have already accepted the message before the worker crashed prior to updating status to `SENT`. On the next read, it is uncertain whether the message was sent, and retrying can create a second copy.

**Idempotency when workers re-read the outbox** means the system recognizes the same send intent, avoids creating duplicate jobs, prevents multiple workers from processing concurrently when possible, and manages retries without unintended side effects in controllable scenarios. It **does not mean** Spring Mail, SMTP, or a database outbox can execute a distributed transaction guaranteeing "exactly once" delivery to an inbox.

This lesson explains levels of duplication, stable identity keys, unique constraints, claim/lease mechanics, lock tokens, job states, crash windows, handling uncertain outcomes, backoff, outbox workers, and Java/Spring Boot examples with PostgreSQL.

## 1. What Problem Does an Outbox Solve?

A simple synchronous sending flow:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.confirm(orderId);
    mailSender.send(createMessage(orderId));
}
~~~

There are two separate systems here: the database and SMTP. A database transaction cannot roll back an email already handed off to a relay. If sending succeeds but the transaction rolls back, the recipient may receive a notice for an unconfirmed order. If the database commits and the process dies before calling SMTP, the notification may be lost.

With a **transactional outbox**, instead of sending inside the transaction, the service persists a **send intent**:

~~~mermaid
flowchart TD
    A["Confirm order"] --> B["DB Transaction"]
    B --> C["UPDATE orders"]
    B --> D["INSERT mail_outbox"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Worker polls outbox"]
    F --> G["Claim job"]
    G --> H["JavaMailSender.send"]
    H --> I["Record outcome"]
~~~

Updating the order and inserting the outbox record occur in the same transaction. Both commit or both roll back. After commit, a worker can pick up the job even if the original request process terminates.

Yet the sequence **claim → SMTP send → update status** is not a single atomic transaction. Workers can repeat it. That is why idempotency is needed.

## 2. Defining Idempotency in a Mail-Sending System

An idempotent operation executed multiple times for the same request produces no additional business effects beyond the first execution.

Suppose we have an event:

~~~text
Business event: ORDER_CONFIRMED
Event ID: evt-981
Order: ORD-2048
Recipient: contact-77
~~~

If the system receives the same event `evt-981` again, it should still have **one logical email-sending job** for `contact-77`, rather than creating a new job per redelivery.

Distinguish these boundaries:

| Boundary | Duplication scenario | Countermeasure |
| --- | --- | --- |
| Enqueueing into outbox | Event/request runs twice | Idempotency key + unique constraint |
| Worker picking up job | Two workers grab the same row | Atomic claim, row lock, lease |
| Worker recording outcome | Stale worker overwrites new status | Lock token or version check |
| Sending to SMTP relay | Sent then crashed before marking `SENT` | Cannot be solved purely by DB; needs retry policy and provider dedupe if available |
| Handling provider feedback | Same webhook delivered twice | Deduplicate provider events separately |

An outbox table with a unique key solves **duplicate enqueues**; it does not by itself prevent two SMTP calls for the same outbox record.

## 3. At-Least-Once Processing and Limits of Exactly-Once

When workers retry and recover jobs after crashes, a job can be **processed at least once** as intended by the system whenever infrastructure is up and retry policy permits. Still, each processing run can result in an SMTP send, even when the previous attempt succeeded before its outcome could be written to the database.

~~~text
Worker A: claim job
Worker A: sends to SMTP
SMTP relay: accepts email
Worker A: process crashes before UPDATE SENT

Worker B: sees expired lease
Worker B: reclaims job
Worker B: sends again
SMTP relay: accepts email again
~~~

There may be only **one** outbox row, yet **two** mail sends. No SQL constraint can recall a message already accepted by the relay.

Use accurate terminology:

- **At-most-once attempt:** Do not retry after uncertain situations; fewer duplicates, but risks losing emails.
- **At-least-once processing:** Retries and recovery exist; avoids losing send intents, while accepting some duplicate executions.
- **Exactly-once external effect:** Can only be claimed when the receiving system supports deduplication/transactions under an explicit contract; standard SMTP provides no universal idempotency key to guarantee this.

**Conclusion:** An outbox design improves durability of send requests, not a guarantee that every email appears exactly once in the inbox.

## 4. Why Workers Re-Read the Same Job

A worker may encounter the same outbox row again due to:

1. Process killed or JVM crash mid-send.
2. Server restart or deployment before the job is marked `SENT`.
3. SMTP timeout where the worker never receives the final reply.
4. Long GC pause stalling a worker until its lease expires.
5. Another worker reclaiming an expired-lease job.
6. Retry scheduled after a transient failure.
7. Queue/event consumer redelivering a message.
8. Overlapping scheduler polls.
9. Operator manually triggering a "retry."
10. Initial outbox insertion creating multiple equivalent jobs.

Both **duplicate logical jobs** and **repeated processing of the same row** must be handled. Simply adding `isSent = true` is insufficient because race conditions exist between reading, sending, and updating.

## 5. Building a Stable Idempotency Key

An idempotency key represents **one notification intent**, not one send attempt.

An identifier can combine:

~~~text
tenantId : eventId : mailPurpose : recipientId : contentVersion
~~~

Example:

~~~text
tenant-42:evt-981:ORDER_CONFIRMED:contact-77:v1
~~~

Components:

| Component | Meaning |
| --- | --- |
| `tenantId` | Avoids merging jobs across tenants |
| `eventId` | Business event identifier generated once |
| `mailPurpose` | Separates confirmations, invoices, alerts, etc. |
| `recipientId` | Distinguishes logical recipients |
| `contentVersion` | Used only if a new version truly represents a distinct send intent |

### 5.1. Do Not Generate a New UUID on Each Retry

Wrong:

~~~java
String key = UUID.randomUUID().toString();
outbox.insertIfAbsent(key, mailData);
~~~

If this method is called again, the new key creates a separate logical job. Random UUIDs can be used for `job_id` or `attempt_id`, but **the deduplication key must be deterministically reconstructed to the exact same value** from stable business data.

### 5.2. Do Not Pick a Key That Is Too Broad

If the key is only the email address, sending an invoice and sending an order confirmation could block each other. If the key contains only `orderId`, emails for payment and shipping events of the same order could collide as duplicates.

### 5.3. Do Not Pick a Key That Is Too Narrow

If you include `LocalDateTime.now()`, attempt number, or a per-request UUID in the key, two retries will usually get different keys. Idempotency is lost.

### 5.4. Is an "On-Demand Resend" the Same Job?

Decide based on business rules:

- If a user retries an HTTP request due to a timeout, that is usually **the same send intent** and should keep the same key.
- If a user explicitly requests a fresh copy of an invoice days later, that may be a **new send intent** with its own `resendRequestId`.
- If a campaign runs in multiple waves, each wave can have its own ID.

Never delete old jobs or randomize keys just to evade a unique constraint. Intentional resends must be distinguished and audited.

## 6. Designing the mail_outbox Table

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE mail_outbox (
    id                 uuid PRIMARY KEY,
    tenant_id          uuid NOT NULL,
    idempotency_key    text NOT NULL,
    business_event_id  text NOT NULL,
    mail_purpose       text NOT NULL,
    recipient_id       text NOT NULL,
    recipient_address  text NOT NULL,
    payload            jsonb NOT NULL,

    status             text NOT NULL DEFAULT 'PENDING',
    attempt_count      integer NOT NULL DEFAULT 0,
    next_attempt_at    timestamptz NOT NULL DEFAULT now(),

    lock_token         uuid,
    locked_until       timestamptz,

    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    sent_at            timestamptz,
    last_error_code    text,

    CONSTRAINT uq_mail_job UNIQUE (
        tenant_id, idempotency_key
    ),

    CONSTRAINT chk_mail_status CHECK (
        status IN ('PENDING', 'SENDING', 'RETRY', 'SENT', 'DEAD')
    )
);
~~~

Indexes for worker polling:

~~~sql
CREATE INDEX idx_mail_ready
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_mail_lease
    ON mail_outbox (locked_until)
    WHERE status = 'SENDING';
~~~

This is an illustrative schema, not a drop-in migration for every system. You can add `provider_message_id`, `last_attempt_at`, `max_attempts`, `error_details_ref`, schema version, correlation ID, and additional indexes as needed.

### One Row per Recipient?

For emails personalized per recipient, it is usually best to create **one outbox job per logical recipient**. Example:

~~~text
evt-981 + ORDER_CONFIRMED + contact-77 → job A
evt-981 + ORDER_CONFIRMED + contact-88 → job B
~~~

That gives each address independent retry tracking, suppression, and auditing. Sending a single message with multiple `To`/`Cc`/`Bcc` addresses introduces separate privacy and per-recipient outcome concerns.

## 7. Inserting Into Outbox in the Business Transaction

An overview SQL flow:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = :order_id
  AND status = 'PENDING';

-- Only create event/outbox when the business logic actually performs
-- a corresponding valid state transition.
INSERT INTO mail_outbox (
    id, tenant_id, idempotency_key,
    business_event_id, mail_purpose,
    recipient_id, recipient_address, payload
)
VALUES (
    :job_id, :tenant_id, :key,
    :event_id, 'ORDER_CONFIRMED',
    :recipient_id, :recipient, :payload
)
ON CONFLICT (tenant_id, idempotency_key)
DO NOTHING;

COMMIT;
~~~

Crucially, the business update and outbox insert commit or roll back **together**. In real code, only insert when the state transition is confirmed and the event ID is stable; the snippet above omits checking the `UPDATE` row count for brevity.

In Spring:

~~~java
@Service
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderConfirmationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirm(UUID orderId, UUID actorId) {
        Order order = orders.findForUpdate(orderId)
                .orElseThrow();

        boolean newlyConfirmed = order.confirm(actorId);

        if (!newlyConfirmed) {
            return; // Do not emit another event.
        }

        String eventId = order.confirmationEventId();
        String key = String.join(":",
                order.tenantId().toString(),
                eventId,
                "ORDER_CONFIRMED",
                order.recipientContactId().toString(),
                "v1"
        );

        outbox.insertIfAbsent(
                MailOutboxDraft.fromOrder(order, key)
        );
    }
}
~~~

`Order`, `MailOutboxDraft`, `findForUpdate`, and `insertIfAbsent` are hypothetical application components that must be implemented appropriately. `insertIfAbsent` must rely on a unique constraint / atomic SQL, not `findByKey` followed by `insert`, because two transactions can race.

**Note on JPA:** Catching `DataIntegrityViolationException` from a unique key violation inside a transaction and continuing work can be unsafe because the transaction may already be marked rollback-only. Using `ON CONFLICT DO NOTHING` (PostgreSQL) or an equivalent upsert mechanism is usually cleaner when conflicts are expected.

## 8. Job State Machine

An easy-to-follow state model:

| Status | Meaning |
| --- | --- |
| `PENDING` | Committed, awaiting worker |
| `SENDING` | Claimed by a worker with an active lease |
| `RETRY` | Waiting to retry after a temporary error or uncertain outcome |
| `SENT` | Application recorded a successful SMTP-layer send |
| `DEAD` | No further automatic retries; requires separate handling |

~~~mermaid
flowchart TD
    A["PENDING"] --> B["SENDING"]
    B -->|"send succeeded"| C["SENT"]
    B -->|"retryable error"| D["RETRY"]
    D -->|"next_attempt_at reached"| B
    B -->|"permanent error / exhausted"| E["DEAD"]
    B -->|"lease expired"| F["reclaim"]
    F --> B
~~~

Here `SENT` is explicitly defined as **the worker observed `JavaMailSender.send(...)` return successfully and persisted the outcome to the database**. Do not interpret `SENT` as "landed in inbox." If delivery tracking is needed, add provider callbacks/bounce feedback and separate states.

### Fields Supporting Claims

- `locked_until`: expires the claim so another worker can recover the job.
- `lock_token`: fresh token on each claim to stop stale workers from updating state.
- `attempt_count`: number of attempts/claims per system definition.
- `next_attempt_at`: earliest timestamp when retry is allowed.
- `last_error_code`: error classification for observability and operations.

`lock_token` changes on every claim; `idempotency_key` never changes.

## 9. Never SELECT PENDING and Immediately Send

Dangerous pattern:

~~~text
Worker A: SELECT row 123 WHERE status=PENDING
Worker B: SELECT row 123 WHERE status=PENDING
Worker A: SMTP send
Worker B: SMTP send
Worker A: UPDATE SENT
Worker B: UPDATE SENT
~~~

Both workers see `PENDING` before either changes the status. The **claim** operation must be atomic.

In PostgreSQL, use `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH candidates AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY')
        AND next_attempt_at <= now()
    ) OR (
        status = 'SENDING'
        AND locked_until < now()
    )
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS m
SET
    status = 'SENDING',
    attempt_count = m.attempt_count + 1,
    lock_token = gen_random_uuid(),
    locked_until = now() + interval '2 minutes',
    updated_at = now()
FROM candidates c
WHERE m.id = c.id
RETURNING
    m.id, m.lock_token, m.attempt_count,
    m.recipient_address, m.mail_purpose, m.payload;
~~~

In one short transaction, the worker:

1. Selects eligible jobs.
2. Uses row locks, skipping rows already locked by other workers.
3. Updates status to `SENDING` and generates a token.
4. Receives the job snapshots to process.
5. **Commits the claim transaction**.
6. Renders and sends via SMTP only after committing.

`gen_random_uuid()` is a PostgreSQL UUID-generation function; ensure your database/version supports it. On other databases, implement an equivalent claim mechanism rather than copying `SKIP LOCKED` where the dialect does not support it.

### Why Not Hold the Transaction Open While Sending?

An SMTP send can wait on connection setup, TLS, AUTH, timeouts, and attachment streaming. Holding a DB transaction/row lock across network I/O increases contention, ties up the connection pool, and stalls other workers. The standard pattern is **short claim → out-of-transaction send → short mark**.

The trade-off is a crash window between send and mark; that is an inherent limit of the system.

## 10. Leases and Lock Tokens

Suppose:

~~~text
10:00 Worker A claims job-123
      lock_token = token-A
      locked_until = 10:02

10:02 Worker A is still hung
      Worker B reclaims job-123
      lock_token = token-B
      locked_until = 10:04
~~~

If A comes back and tries to update `SENT` with `token-A`, the update must have no effect:

~~~sql
UPDATE mail_outbox
SET
    status = 'SENT',
    sent_at = now(),
    locked_until = NULL,
    lock_token = NULL,
    last_error_code = NULL,
    updated_at = now()
WHERE id = :job_id
  AND status = 'SENDING'
  AND lock_token = :claim_token
RETURNING id;
~~~

If `RETURNING` is empty, the token is stale or the job is no longer `SENDING`. The worker must not overwrite state simply because it believes it finished.

### Lock Tokens Do Not Undo SMTP Side Effects Already Executed

Duplicates can still occur in this case:

~~~text
Worker A sends very slowly
Lease A expires
Worker B claims token-B, starts sending
SMTP accepts A's message
A cannot mark SENT because token-A is stale
SMTP also accepts B's message
B marks SENT with token-B
~~~

Leases and tokens govern **database write authority**. They cannot roll back an SMTP call already started. Therefore, never claim fencing tokens give exactly-once email delivery.

### Heartbeats for Slow Sends

If processing may exceed the lease, a worker can extend it:

~~~sql
UPDATE mail_outbox
SET
    locked_until = now() + interval '2 minutes',
    updated_at = now()
WHERE id = :job_id
  AND status = 'SENDING'
  AND lock_token = :claim_token;
~~~

When the update affects 0 rows, the worker has lost its claim. It can abort any remaining safe local steps, though if the relay already accepted the SMTP call, a heartbeat cannot cancel that side effect.

## 11. Critical Crash Windows

| Failure point | Observed state | Recovery path | Duplicate risk |
| --- | --- | --- | --- |
| Before business transaction commit | No job committed | Not sent | None from that job |
| After commit, before worker claim | `PENDING` | Claimed on poll | Low |
| After claim, before SMTP | `SENDING` | Lease expires then reclaimed | Low if not yet sent |
| Mid-SMTP, unclear if relay accepted | `SENDING` | Classify uncertain outcome | **Yes** |
| Relay accepted, worker dies before mark | `SENDING` | Retry/reconcile | **Yes** |
| Mark `SENT` committed successfully | `SENT` | Not polled normally | No need to resend |
| Old worker finishes after lease | Stale token | Old worker update rejected | Side effect may still happen |

The hardest scenario:

~~~mermaid
sequenceDiagram
    participant W as Worker A
    participant S as SMTP
    participant DB as Database
    participant R as Worker B
    W->>DB: Claim token-A
    W->>S: Send email
    S-->>W: 250 accepted
    Note over W: Crash before marking SENT
    R->>DB: Lease expired, claim token-B
    R->>S: Send email again
    S-->>R: 250 accepted
    R->>DB: Mark SENT token-B
~~~

The unique constraint on `idempotency_key` does not help here because **no new row is inserted**. Both workers process the exact same job.

## 12. SMTP Timeouts Are Uncertain Outcomes

Example:

~~~text
Worker finishes sending SMTP payload
Relay accepts message
Network drops before worker receives reply
Worker reports timeout
~~~

The worker cannot conclude with certainty that the message was "not sent." If it retries, the email may be sent twice. If it does not retry, the email may be lost in cases where the relay actually never received it.

You can choose a policy:

- **Best effort:** Retry with backoff, accepting potential duplicates for low-sensitivity notifications.
- **Risk-sensitive:** Move to a reconciliation state instead of retrying immediately on ambiguous outcomes.
- **Provider idempotency:** If the sending API genuinely supports idempotency keys, pass the same key across retries within the provider's retention window.
- **Manual review:** For certain critical notifications, let an operator decide whether to resend.

No single choice fits every use case. Balance the risk of **missing a notification** against the risk of **sending a duplicate**.

### Does Message-ID Help SMTP Deduplicate?

Emails carry a `Message-ID` header, such as:

~~~text
Message-ID: <mail-evt981@example.org>
~~~

This header helps with identification, correlation, threading, or debugging. However, **there is no universal SMTP rule forcing relays to reject duplicate `Message-ID` values**. Sending twice with the same `Message-ID` can still deliver two messages to the recipient.

Libraries may generate or modify `Message-ID` during serialization. If you need a fixed header for tracing, understand your specific Jakarta Mail/provider behavior; this still does not substitute for idempotency in the receiving system.

## 13. Sending Successfully Is Not Inbox Delivery

When:

~~~java
mailSender.send(mimeMessage);
repository.markSent(job.id(), job.lockToken());
~~~

`send(...)` returning normally reflects success at the submission layer observed by the application. The relay may still have to route and deliver the email; bounces or final errors can appear later.

Define `SENT` clearly:

> `SENT` = the application recorded that handing off the message to the transport completed successfully; final delivery is not yet guaranteed.

If the product requires `DELIVERED` or `BOUNCED` states, integrate provider callbacks, delivery status notifications, or appropriate webhooks. Webhooks themselves can be redelivered and need their own deduplication.

## 14. Spring Worker: Separating Claim, Send, and Mark

One pattern:

~~~text
MailOutboxPoller
  → MailClaimService.claimBatch()  (short DB transaction)
  → MailDeliveryWorker.process(job)
     → MailRenderer.render(job)
     → MailGateway.send(mail)      (SMTP outside DB transaction)
     → MailStateService.markSent() (short DB transaction)
     → or recordFailure()          (short DB transaction)
~~~

### 14.1. Scheduler

~~~java
@Configuration
@EnableScheduling
public class MailOutboxSchedulingConfig {
}
~~~

~~~java
@Component
public class MailOutboxPoller {

    private final MailClaimService claims;
    private final MailDeliveryWorker delivery;

    public MailOutboxPoller(
            MailClaimService claims,
            MailDeliveryWorker delivery) {
        this.claims = claims;
        this.delivery = delivery;
    }

    @Scheduled(
        fixedDelayString = "${mail.outbox.poll-delay-ms:2000}"
    )
    public void poll() {
        List<ClaimedMailJob> jobs = claims.claimBatch(20);

        for (ClaimedMailJob job : jobs) {
            delivery.process(job);
        }
    }
}
~~~

Sequential processing illustrates the semantics clearly. Larger systems can use multiple processes or bounded executors while still enforcing safe claims and SMTP rate limits. `@EnableScheduling` enables the scheduler; `@Async` is not required merely to poll the outbox.

### 14.2. Claimed Job as a Snapshot

~~~java
public record ClaimedMailJob(
        UUID id,
        UUID lockToken,
        int attemptCount,
        String recipient,
        String purpose,
        String payloadJson) {
}
~~~

Do not pass a mutable JPA entity bound to a persistence context across transaction boundaries and worker threads. An immutable DTO carries the needed processing data more safely and cleanly.

### 14.3. Claim Service

~~~java
@Service
public class MailClaimService {

    private final MailOutboxJdbcRepository repository;

    public MailClaimService(MailOutboxJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMailJob> claimBatch(int limit) {
        return repository.claimReady(limit);
    }
}
~~~

`claimReady` is an application-implemented method using the atomic SQL claim above. `@Transactional` must go through a Spring proxy as usual; do not rely on self-invocation if you expect transaction advice to apply.

### 14.4. Worker Execution and Recording Outcomes

~~~java
@Component
public class MailDeliveryWorker {

    private final MailRenderer renderer;
    private final MailGateway gateway;
    private final MailStateService states;

    public MailDeliveryWorker(
            MailRenderer renderer,
            MailGateway gateway,
            MailStateService states) {
        this.renderer = renderer;
        this.gateway = gateway;
        this.states = states;
    }

    public void process(ClaimedMailJob job) {
        try {
            RenderedMail mail = renderer.render(job);
            gateway.send(mail);

        } catch (Exception preparationOrSendFailure) {
            states.recordFailure(
                    job.id(),
                    job.lockToken(),
                    job.attemptCount(),
                    preparationOrSendFailure
            );
            return;
        }

        // Must be a separate DB transaction.
        states.markSent(job.id(), job.lockToken());
    }
}
~~~

`MailRenderer`, `MailGateway`, `RenderedMail`, and `MailStateService` are application abstractions, not all built into Spring. This demonstrates separation of concerns; production code must handle failures of `recordFailure` and `markSent` themselves, with monitoring and recovery.

**Never catch a DB status-mark failure and treat it as an SMTP failure.** SMTP may have succeeded; if the DB mark fails, the job could be reclaimed and sent twice. Log and handle this situation explicitly.

### 14.5. Spring Mail Gateway

~~~java
@Component
public class SpringMailGateway implements MailGateway {

    private final JavaMailSender mailSender;

    public SpringMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void send(RenderedMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(mail.from());
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(
                    mail.plainText(),
                    mail.htmlText()
            );

            mailSender.send(message);

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Unable to create MIME message", ex
            );
        }
    }
}
~~~

`MailPreparationException` is an application-defined exception (or Spring's `MailPreparationException` when imported). `JavaMailSender.send` can also throw `MailException` and SMTP/network causes that need classification.

The gateway only sends prepared content. Choosing recipients, computing amounts, rendering templates, and managing idempotency belong to the application/domain layer.

## 15. Marking Retry With a Token

When sending fails with a retryable error, update state conditionally:

~~~sql
UPDATE mail_outbox
SET
    status = 'RETRY',
    next_attempt_at = :retry_at,
    last_error_code = :error_code,
    locked_until = NULL,
    lock_token = NULL,
    updated_at = now()
WHERE id = :job_id
  AND status = 'SENDING'
  AND lock_token = :claim_token;
~~~

If the update returns 0 rows, the worker has lost its claim and must not overwrite the newer state. For permanent failures or exhausted retry budgets, transition to `DEAD` using the same token guard.

### Retrying With Backoff and Jitter

A retry schedule can use:

\[
d_n = \min(d_{\max}, d_{\mathrm{base}} \cdot 2^{n-1}) + jitter
\]

Where `n` is the recorded attempt count, `d_base` is the initial wait, and `d_max` is the cap. Jitter prevents thousands of jobs from retrying at the exact same instant.

Example with a 30-second base and 30-minute cap:

| Attempt | Base delay |
| --- | --- |
| 1 | 30 seconds |
| 2 | 60 seconds |
| 3 | 120 seconds |
| 4 | 240 seconds |
| 5 | 480 seconds |

Bound the multiplication to avoid overflow and enforce a suitable max attempts limit. A job that cannot render due to invalid data will not heal itself after hundreds of retries.

### Error Classification

| Category | Example | Handling approach |
| --- | --- | --- |
| Temporary SMTP failure | Provider temporarily rejects, throttled | Retry after backoff |
| Permanent recipient rejection | Disallowed/invalid address | `DEAD` or policy handling |
| Rendering/data failure | Missing template, invalid payload | Do not retry indefinitely |
| Network timeout after sending data | Unknown if relay received it | Uncertain outcome, distinct risk policy |
| DB failure when marking sent | SMTP may have succeeded | Recovery and duplicate risk |
| Lease expiration | Slow or crashed worker | Controlled reclaim |

Never treat every `MailException` as a temporary error. When reading provider-specific codes, inspect error semantics and actual SMTP stage.

## 16. Transaction Boundaries and @Async

A design bug:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orderRepository.confirm(id);
    mailWorker.sendAsync(createMailCommand(id));
}
~~~

If `mailWorker` has `@Async` and is called through a proxy, the worker may execute **before the `confirmOrder` transaction commits**. If the transaction later rolls back, the email may already have been sent erroneously.

To prevent this:

- Use a transactional outbox: persist the job in the business transaction; workers read only after commit.
- For best-effort cases, an appropriate after-commit event mechanism can be used, though in-memory events lack outbox durability.
- Never wrap SMTP inside a database transaction expecting it to roll back the email.
- Never treat `@Async` as a durable queue: an in-memory executor loses tasks when the process dies.

`@Async` can still be used to run workers concurrently, **while the outbox database remains the durable store of send intents**. Control thread pools, queues, saturation, and SMTP rate limits.

## 17. Content and Recipient Snapshots

The outbox can store:

~~~json
{
  "orderId": "ORD-2048",
  "eventId": "evt-981",
  "recipientId": "contact-77",
  "recipientAddress": "buyer@example.org",
  "mailPurpose": "ORDER_CONFIRMED",
  "templateVersion": 1,
  "locale": "vi-VN"
}
~~~

Two common strategies:

| Strategy | Pros | Risks |
| --- | --- | --- |
| Store data snapshot at job creation | All attempts use identical information | Payload may hold PII and grow stale |
| Store IDs to resolve at send time | Compact data, can apply latest policies | Recipient/content may change between attempts |
| Snapshot + re-check policy | Preserves original intent, honors new suppression/consent | Must define which fields may vary |

For transactional emails, snapshots keep content consistent. For marketing, checking the latest unsubscribe/suppression state is usually critical.

**Do not let a retry of the same job silently switch to a new recipient** merely because a user profile email changed, without re-evaluating eligibility and the meaning of the idempotency key. A different recipient may constitute a new send intent.

## 18. SMTP Idempotency Limits

`JavaMailSender` is an API for sending MIME over mail transport; it does not have a standard parameter like:

~~~java
mailSender.send(message, idempotencyKey);
~~~

to ask every SMTP relay to deduplicate. Do not invent a custom SMTP header and assume the provider will honor it.

If using an **email API provider** that documents idempotency-key support, the application can pass the same key across retries to limit duplicate submissions within the provider's guaranteed window. Determine:

- Key scope by account/tenant.
- How long deduplication results are retained.
- How two concurrent requests are handled.
- What response is returned on timeout.
- Whether send status can be queried by request ID.
- Differences between "submitted," "accepted," and "delivered."

When using plain SMTP, you must accept a window of uncertainty between relay acceptance and DB status update.

## 19. Testing Idempotency and Failure Windows

You do not need to send real emails to test most of this design.

### 19.1. Duplicate Enqueue

Emit the same business event twice. Verify the unique constraint allows only one outbox row for the same `tenant_id` and `idempotency_key`. For concurrency tests, run two transactions inserting simultaneously against a real database rather than just mocking the repository.

### 19.2. Two Workers Claiming Concurrently

Create 20 `PENDING` jobs and run two claiming workers simultaneously. Verify no job is claimed by both while its lease is active. PostgreSQL `FOR UPDATE SKIP LOCKED` should be tested on a DB with equivalent semantics, rather than assuming H2 behaves identically.

### 19.3. Crash After Claim, Before Send

Claim a job without calling the gateway, let the lease expire, and reclaim it. The job should recover per policy, with `attempt_count` and `lock_token` updating accordingly.

### 19.4. Crash After SMTP, Before Marking SENT

Have a fake gateway record that it received the send command, and fail the DB mark step. After the lease expires, the job can be reclaimed. The test should **demonstrate the possibility of a duplicate**, rather than treating it as a SQL bug fixable with a unique key.

### 19.5. Stale Lock Token

Worker A claims `token-A`; after expiry, Worker B claims `token-B`. A attempts to mark `SENT` with `token-A` and must update 0 rows. B is allowed to mark with `token-B`.

### 19.6. Ambiguous Timeout

Have a fake SMTP client simulate the relay accepting the message while the caller times out. Verify the outcome is classified as unknown or retried per policy and metrics flag the duplicate risk.

### 19.7. Backoff and Dead States

- `RETRY` rows are claimed only once `next_attempt_at` is due.
- Attempts do not exceed the configured cap.
- Permanent errors transition to `DEAD`.
- `SENT` rows are never claimed in normal polling.
- Expired-lease jobs can be reclaimed.
- Manual replays follow policy and auditing.

### 19.8. Test Content Separately From Transport

Test the renderer with snapshot data, and test the gateway with a fake sender or SMTP test server. Test worker policy with a mock gateway and a DB test repository. Never mix routine tests with production SMTP sending.

## 20. Monitoring and Operations

Useful metrics:

| Metric | Meaning |
| --- | --- |
| Count of `PENDING` and `RETRY` jobs | Backlog level |
| Age of oldest incomplete job | Notification latency |
| `SENDING` jobs past lease expiry | Dead or hung workers |
| `attempt_count` distribution | Unusual retry rates |
| `DEAD` count by reason | Failures needing intervention |
| Stale-token update count | Contention/lease expirations |
| Duplicate enqueues blocked by unique key | Repeated requests/events |
| Unknown SMTP outcomes | Duplicate-send risk |
| SMTP duration and timeout errors | Transport bottlenecks |
| Event → SMTP accepted latency | Pipeline health |

Auditing should allow correlating `business_event_id`, `idempotency_key`, `outbox_id`, `attempt_id`, claim/send timestamps, reason codes, and state transitions.

Never log SMTP credentials, reset tokens, full email bodies, or unnecessary recipient data. Use contact IDs/correlation IDs, masking, and proper retention.

### Manual Retries

When an operator reviews a `DEAD` job:

1. Inspect the original error and current state.
2. Decide whether to retry **the same intent** or send a **new intent**.
3. If retrying the same intent, preserve the idempotency key and audit the state change.
4. If sending an intentional new copy, create a distinct resend event/request ID.
5. Check recipient policy, consent/suppression, and permissions before sending.

Never delete old keys to circumvent deduplication constraints.

## 21. Retention of Outbox and Deduplication Keys

If all `SENT` jobs are purged immediately after sending, an old event replayed later can recreate the job because the unique key is gone. Keep deduplication records long enough to cover the realistic replay window.

Options:

- Retain `SENT` jobs for a sufficiently long retention window.
- Archive the outbox while keeping a smaller deduplication-key table.
- Maintain notification history per event/recipient.
- Define key TTLs based on email type and audit needs.

Retention policies must also account for personal data inside payloads. No single duration fits every product; invoices, marketing emails, and security alerts have different needs.

## 22. Common Implementation Mistakes

### 22.1. Generating a Random Key on Each Retry

Leads to multiple equivalent outbox jobs. Keys must be stable per business event/purpose/recipient.

### 22.2. SELECT PENDING Without Atomic Claim

Two workers can send the same job. Use database-appropriate locking or conditional updates.

### 22.3. Marking SENT Before SMTP

If the process dies after marking but before sending, the job is considered done and the email is lost.

### 22.4. Assuming Mark SENT After SMTP Is Atomic

If the relay accepts the email and the process crashes before DB commit, retries can send duplicates.

### 22.5. Using Message-ID as a Deduplication Guarantee

`Message-ID` does not compel SMTP relays to reject duplicate messages.

### 22.6. Missing Lease Expiry

A crashed worker leaves jobs stuck in `SENDING` forever.

### 22.7. Updating Status Without a Lock Token

A stale worker can overwrite the newer worker's state.

### 22.8. Lease Too Short or Infinite SMTP Timeouts

Jobs get reclaimed while the previous worker is still sending. Set sensible timeouts, consider heartbeats, and bound waits.

### 22.9. Retrying All Errors Identically

Permanent recipient/policy errors do not fix themselves; do not retry indefinitely.

### 22.10. Treating SMTP Timeouts as Definitely Unsent

The relay may already have accepted the mail; retrying risks duplicates.

### 22.11. Calling SMTP Inside a Long DB Transaction

Increases DB contention without achieving atomicity between SMTP and the database.

### 22.12. Treating @Async as a Durable Job Queue

An in-memory executor loses tasks on process restart; only an outbox persists intents durably.

### 22.13. Omitting Tenant and Purpose From Keys

Valid notifications can accidentally suppress each other.

### 22.14. Purging Dedupe History Too Early

Late event replays can re-enqueue and resend already sent notifications.

### 22.15. Confusing Accepted With Delivered

`send` returning normally does not prove the email reached the inbox.

## 23. Self-Check Questions

**Q1.** An outbox record is `SENT`, yet a polling worker reads it again. What should it do?

Ignore it. `SENT` is not an eligible state to reclaim in the normal flow.

**Q2.** Two identical HTTP requests generate two different UUIDs as idempotency keys. Does that prevent duplicates?

No. A stable key is needed for the same send intent.

**Q3.** Two workers both `SELECT PENDING` and send before `UPDATE`. What can happen?

Both send the same job. Atomic claims using DB locks/conditions are required.

**Q4.** SMTP accepted the email, but the worker crashed before marking `SENT`. Does the unique constraint stop a retry from sending a duplicate?

No. The unique constraint stops creating another row with the same key; it does not stop sending the same row twice.

**Q5.** Why is a lock token needed?

So a worker holding an expired lease cannot overwrite state after another worker claims the job. It does not roll back an already-sent SMTP call.

**Q6.** Can reusing the same `Message-ID` make SMTP automatically drop duplicates?

There is no universal SMTP guarantee of that.

**Q7.** Does a timeout after transmitting SMTP data mean the message was definitely not sent?

No. That can be an uncertain outcome; the relay may have accepted it.

**Q8.** A `RETRY` job has `next_attempt_at` in the future. Should a worker claim it immediately?

No, unless an intentional operational procedure overrides it.

**Q9.** Can you hold a DB transaction open until `JavaMailSender.send` finishes?

Technically possible, but it should not be used to try to achieve atomicity. SMTP does not roll back with the DB, and long transactions hold resources.

**Q10.** Does `@Async` automatically recover 500 queued jobs after a JVM crash?

No. A persisted outbox or durable queue is required for recovery by design.

**Q11.** When retrying the same job, how many times does the idempotency key change?

Zero times; only the attempt ID/claim token changes.

**Q12.** When `JavaMailSender.send` returns normally, can the system mark the status `DELIVERED`?

Insufficient basis. Provider feedback or a separate delivery-tracking mechanism is required.

## 24. Mental Model to Remember

~~~mermaid
flowchart TD
    A["Business event"] --> B["Stable idempotency key"]
    B --> C["DB transaction: business + outbox"]
    C --> D["Unique constraint prevents duplicate enqueue"]
    D --> E["Atomic claim + lease + token"]
    E --> F["Render controlled content"]
    F --> G["JavaMailSender.send"]
    G --> H{"Outcome"}
    H -->|"Success"| I["Mark SENT with token"]
    H -->|"Temporary / unknown"| J["RETRY or reconcile"]
    H -->|"Permanent"| K["DEAD"]
    J --> E
~~~

Key points to remember:

1. **A transactional outbox durably stores the send intent within the business transaction.**
2. **Workers can process at-least-once** due to retries, restarts, and lease expirations.
3. **Keys must be stable** by event/purpose/recipient; never mint a new one per attempt.
4. **Unique constraints prevent duplicate enqueues**, not guaranteed single SMTP calls.
5. **Atomic claims and leases** minimize multiple workers processing the same job concurrently.
6. **Lock tokens block stale state updates**, without recalling already-executed SMTP side effects.
7. **Crashing after SMTP acceptance before marking `SENT` can still cause duplicates.**
8. **Timeouts can be uncertain outcomes**; retries must follow SLAs and risk policies.
9. **Separate the claim transaction, SMTP send, and mark transaction**; never hold database locks across network waits.
10. **Use retry/backoff, attempt caps, auditing, monitoring, and retention** to handle real-world replays.
11. **Distinguish SMTP accepted from delivered**, and never promise exactly-once delivery where infrastructure does not support it.
12. **Check consent/recipient policies at the right time**, because idempotency alone does not grant permission to send.

In Spring Framework Mail, `JavaMailSender` is responsible for establishing the connection to send MIME over SMTP; the database and worker orchestration are responsible for persisting jobs, preventing duplicate enqueues, distributing work, retrying, and tracking state. Proper design lets workers re-read the outbox while preserving consistent business semantics, while honestly acknowledging the limit that duplicates cannot be completely eliminated across the boundary between database and SMTP.

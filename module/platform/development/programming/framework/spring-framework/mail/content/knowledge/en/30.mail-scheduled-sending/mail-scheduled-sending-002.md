# Storing Send Time Together with Message Status

## 1. Why Store the Send Schedule and Status Together?

In a **Spring Framework Mail** application, an email request does not always have to be sent immediately. A user might schedule a report for Monday morning; the system might need to wait a period after order creation; a campaign might only be allowed to send during business hours; or the SMTP provider is throttling and the job must wait its turn.

A single `JavaMailSender.send(...)` call performs only **one message submission** to the SMTP server at the moment it is invoked. It does not handle scheduling, preserving state across restarts, coordinating multiple instances, cancellation, or retries. If the schedule is kept only in RAM:

~~~java
// Example that is not durable enough for business emails.
scheduler.schedule(() -> mailSender.send(message), sendTime);
~~~

then when the application restarts, registered schedules can vanish. When SMTP fails, there is no durable record to tell whether the email is still waiting or was already attempted. If the user clicks cancel right as a worker is sending, an in-memory flag is also insufficient to synchronize across replicas.

A common solution is to store an **email job** in the database with at least:

- **Allowed send time** (`scheduled_at`).
- **Job status** (`status`).
- **Next retry time** (`next_attempt_at`) if retrying.
- **Actual send attempt count** (`attempt_count`).
- **Provider acceptance timestamp** (`submitted_at`) if applicable.
- **Ownership/lease metadata** when multiple workers process jobs.

Then a worker periodically finds jobs that are **due and still eligible** to send.

~~~text
Application / User
        |
        v
Create mail job:
  scheduledAt + status=PENDING
        |
        v
Durable database / outbox
        |
        v
Due-job dispatcher
        |
        v
Claim -> Compose -> JavaMailSender
        |
        +-- Accepted  -> SUBMITTED
        +-- Temporary -> RETRY, nextAttemptAt
        +-- Permanent -> FAILED
        +-- Unclear   -> UNKNOWN
~~~

**Core principle:** time and status must describe the **same job entity**, updated through controlled transactions, rather than storing the schedule in one place and the status in an inconsistent separate variable.

## 2. Distinguishing Mail Jobs, MIME Messages, and Delivered Emails

In this guide, the word *message* appears at three layers:

| Layer | Concept | Typical identifier | Status |
|---|---|---|---|
| Business | Scheduled email send request | `mailJobId` | PENDING, RETRY, SUBMITTED... |
| SMTP/MIME | `MimeMessage` object sent to server | `Message-ID` header, attempt ID | Composing/submitting |
| Delivery | Message delivered by provider to mailbox | Provider message ID, delivery event | Delivered, bounced, deferred... |

One mail job can produce multiple **submission attempts** if temporary errors occur. A submission attempt may carry the same or a different `Message-ID` depending on how the message is constructed; `Message-ID` does not guarantee idempotency on its own. And a successful `send(...)` call does not prove the message landed in the inbox.

Therefore:

~~~text
PENDING       -> not yet due or not yet claimed
PROCESSING    -> worker claimed and is processing
SUBMITTED     -> SMTP/API reported submission accepted
DELIVERED     -> delivery signal from provider/receiver if integrated
BOUNCED       -> provider reported delivery failure
~~~

Do not call all of these `SENT` without defining it explicitly. If an application uses a `SENT` status, documentation and code must clarify whether that means **successfully submitted to the provider** or **delivered to the mailbox**.

## 3. Timestamps Worth Storing

A record may contain the following timestamps:

| Field | Meaning | When is it set? |
|---|---|---|
| `created_at` | Job creation time | In the transaction that creates the job |
| `scheduled_at` | Original/latest desired send time | When the user or business logic schedules it |
| `next_attempt_at` | Earliest time a worker may attempt sending | At job creation and upon defer/retry |
| `claimed_at` | Worker started owning the job | When claiming succeeds |
| `lease_until` | Time limit for holding processing ownership | When claiming/renewing lease |
| `attempt_started_at` | Actual submission attempt began | When the attempt is recorded |
| `submitted_at` | Provider accepted the submission | Upon explicit success confirmation from adapter |
| `last_failed_at` | Most recent recorded failure time | When an attempt fails |
| `delivered_at` | Provider reported email delivered | Upon receiving a trusted delivery event |
| `cancelled_at` | Job was cancelled while still cancellable | Upon valid cancellation |
| `updated_at` | Last state update time | On every state transition |
| `expires_at` | Final deadline while still meaningful to send | At job creation if content has an expiry |

**Not every table needs every field.** Start with `scheduled_at`, `next_attempt_at`, `status`, and a few audit fields; add other timestamps only when business rules require them. However, avoid collapsing every timestamp into a vague field named `sentTime`.

### scheduled_at and next_attempt_at are not the same

Suppose an email is scheduled:

~~~text
scheduled_at   = 2026-11-15T09:00:00Z
next_attempt_at= 2026-11-15T09:00:00Z
status         = PENDING
~~~

At 09:00, the SMTP provider suffers a temporary error. The worker schedules a retry:

~~~text
scheduled_at   = 2026-11-15T09:00:00Z  (preserve business schedule)
next_attempt_at= 2026-11-15T09:05:00Z  (retry time)
status         = RETRY
attempt_count  = 1
~~~

If `scheduled_at` is overwritten with 09:05 on every retry, the application loses the original schedule and struggles to measure **lag relative to the user's commitment**. Keep the two fields separate.

### submitted_at differs from delivered_at

`JavaMailSender.send(...)` does not provide synchronous confirmation that the recipient received the email. Therefore:

~~~text
submitted_at = after SMTP submission accepted
delivered_at = null if no delivery confirmation yet
~~~

If webhooks/DSN/tracking are not integrated yet, **`delivered_at` may remain absent**. Never set `delivered_at = submitted_at` just to make a dashboard look nice.

## 4. State Model for Scheduled Emails

A model detailed enough for many systems:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: Due time reached, claim succeeded
    PENDING --> CANCELLED: Cancelled before claim
    PENDING --> EXPIRED: Past deadline
    PENDING --> PENDING: Rescheduled
    CLAIMED --> PROCESSING: Begin attempt
    CLAIMED --> PENDING: Safely release claim
    CLAIMED --> CANCELLED: Controlled cancel before submit point
    PROCESSING --> SUBMITTED: Provider accepted
    PROCESSING --> RETRY: Classified temporary error
    PROCESSING --> FAILED: Permanent error
    PROCESSING --> UNKNOWN: Uncertain outcome
    RETRY --> CLAIMED: Reached nextAttemptAt
    RETRY --> CANCELLED: Cancelled before retry
    RETRY --> EXPIRED: Past deadline
    SUBMITTED --> DELIVERED: Provider delivery event
    SUBMITTED --> BOUNCED: Provider bounce event
    UNKNOWN --> RETRY: Reconciliation permits retry
    UNKNOWN --> SUBMITTED: Reconciliation found accepted
~~~

State names are **application-defined enums**, not built-in enums from Spring Mail. A small system might omit a separate `CLAIMED` state and only store `PROCESSING` with a lease. What matters is allowing only **valid transitions** and recording timestamps consistently.

| Status | Can a worker claim it to send? | Notes |
|---|---|---|
| PENDING | Yes, when due | Not yet attempted |
| RETRY | Yes, when `next_attempt_at <= now` | Previously hit a retryable failure |
| CLAIMED/PROCESSING | Not by another worker while lease is valid | Requires ownership/fencing |
| SUBMITTED | No | Provider accepted; delivery is a separate stage |
| DELIVERED | No | Post-delivery state when evidence exists |
| BOUNCED | Do not auto-resend | Requires bounce/complaint policy |
| FAILED | No | Permanent error or exceeded max attempts |
| CANCELLED | No | Cancelled before the point of no return |
| EXPIRED | No | Content exceeded business validity window |
| UNKNOWN | Do not unconditionally auto-retry | Must reconcile or apply dedicated policy |

A status such as `WAITING_QUOTA` can be used if you want to distinguish jobs deferred by a rate limiter; alternatively, you can keep `PENDING` with `next_attempt_at` and `defer_reason`. Do not invent too many statuses without clear operational semantics and actions.

## 5. Choosing Timezones and Time Data Types

**Store actual timestamps in UTC**, such as Java `Instant` and PostgreSQL `TIMESTAMPTZ`, for consistent comparison and claiming.

~~~java
import java.time.Instant;

Instant scheduledAt = Instant.parse(
        "2026-11-15T09:00:00Z");
~~~

If the user chooses **09:00 local time**, the application must know the timezone, such as `Asia/Ho_Chi_Minh` or `Europe/Berlin`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.Instant;

LocalDateTime localTime =
        LocalDateTime.of(2026, 11, 16, 9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = localTime.atZone(zone);
Instant scheduledAt = zoned.toInstant();
~~~

For a **one-off send**, storing `scheduled_at` as an instant is enough for dispatching. For a **recurring** schedule like "09:00 every Monday Paris time", you must also store `ZoneId`, the recurrence rule, and daylight saving time (DST) policies—you cannot simply keep adding 7 × 24 hours forever.

### DST: nonexistent and repeated hours

In some timezones, during DST transitions:

- Some local times **do not exist** (clocks spring forward one hour).
- Some local times **occur twice** (clocks fall back one hour).

`LocalDateTime.atZone(...)` has default rules for those situations, but default rules may not match product requirements. Choose an explicit policy:

1. Nonexistent time: shift to the next valid time or reject the request?
2. Repeated time: use the earlier offset, the later offset, or ask the user?
3. Which timezone should the chosen schedule be displayed in?
4. When a user changes their timezone, keep the old instant or preserve the local wall-clock time?

Never call `LocalDateTime.now()` and write it straight to the database as if it were UTC. Never treat the container's default timezone as the user's timezone.

## 6. What Does "Send on Time" Mean?

A scheduler cannot guarantee the SMTP server will receive the message at the exact millisecond `scheduled_at`. Actual timing also depends on:

~~~text
Scheduled instant
       |
       +-- Wait for scheduler tick
       +-- DB claim/lease
       +-- Quota/rate limiter
       +-- Worker queue
       +-- MIME rendering / attachments
       +-- DNS/TLS/SMTP connection
       |
       v
Provider accepts message
~~~

You can measure:

\[
\text{dispatchLag} =
  \text{attemptStartedAt} - \text{scheduledAt}
\]

\[
\text{submissionLag} =
  \text{submittedAt} - \text{scheduledAt}
\]

Both measurements may be negative or positive if a job was sent early due to a bug or clock skew; **jobs should not be submitted before `scheduled_at`** unless policy permits. Also, `submittedAt` may be null if the job failed or has not been attempted yet.

Commit to a **conditional maximum-lag SLA**, such as "begin processing within one minute after the scheduled time if provider quota is available", rather than promising an email will appear in an inbox at exactly 09:00.

## 7. Designing the Table for Send Schedules and Status

An illustrative PostgreSQL table:

~~~sql
CREATE TABLE scheduled_mail (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    sender_profile_id VARCHAR(80) NOT NULL,

    recipient_ref VARCHAR(160) NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    business_idempotency_key VARCHAR(180) NOT NULL,

    status VARCHAR(24) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,

    attempt_count INT NOT NULL DEFAULT 0,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    claim_token UUID,

    submitted_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    last_failed_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT chk_mail_attempts
        CHECK (attempt_count >= 0),
    CONSTRAINT chk_mail_expiry
        CHECK (expires_at IS NULL
               OR expires_at > created_at),
    CONSTRAINT chk_mail_status
        CHECK (status IN (
            'PENDING', 'RETRY', 'CLAIMED',
            'PROCESSING', 'SUBMITTED',
            'DELIVERED', 'BOUNCED',
            'FAILED', 'CANCELLED',
            'EXPIRED', 'UNKNOWN'
        )),
    CONSTRAINT uq_mail_business_intent
        UNIQUE (tenant_id, business_idempotency_key)
);
~~~

Fields like `recipient_ref` and `payload_ref` can point to protected data in the database or object storage. This is an **illustrative schema** and must be adapted to real requirements. Avoid putting SMTP passwords, tokens, raw MIME, or HTML containing personal data into uncontrolled log/status fields.

### Why is version needed?

`version` enables **optimistic concurrency control** for cancellation/rescheduling, or acts as fencing on state updates. A worker must not overwrite a job that a user just rescheduled unless policy allows it. The `claim_token` column identifies the **current claim round** when updating state, because two workers may process the same job at different times.

### Why is business_idempotency_key needed?

A use case can be invoked repeatedly:

~~~text
HTTP request A creates confirmation email for order-100
Client times out, unsure whether request succeeded
HTTP request B repeats the same intent
~~~

If a brand-new UUID is generated on each call, two identical jobs can be created. A business key like `ORDER_RECEIPT:order-100:version-1` paired with `tenant_id` prevents **duplicating send intent**, which differs from SMTP transport deduplication.

Do not use arbitrary client content like raw email text as an idempotency key that gets logged. Keys can be opaque identifiers or derived from controlled business events. Scope uniqueness meaningfully: one order might have multiple **authorized** resends and need a new key.

## 8. Indexes to Find Due Emails

A scheduler typically queries:

~~~sql
SELECT id
FROM scheduled_mail
WHERE status IN ('PENDING', 'RETRY')
  AND next_attempt_at <= CURRENT_TIMESTAMP
  AND scheduled_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, id
LIMIT 100;
~~~

Do not scan the entire table every few seconds when there are millions of jobs.

~~~sql
CREATE INDEX idx_scheduled_mail_ready
    ON scheduled_mail (next_attempt_at, id)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_scheduled_mail_claim_lease
    ON scheduled_mail (lease_until)
    WHERE status IN ('CLAIMED', 'PROCESSING');

CREATE INDEX idx_scheduled_mail_created
    ON scheduled_mail (created_at, id);
~~~

These indexes are suggestions. Real queries may also filter by `sender_profile_id`, tenant, priority, and provider route; choose indexes based on workload and `EXPLAIN ANALYZE` in an appropriate environment.

**Note on partial indexes:** the index predicate should depend only on fixed statuses—do not put `CURRENT_TIMESTAMP` in a partial index predicate (time-varying functions violate immutability requirements). Time conditions belong in the query, while indexing `next_attempt_at` supports ordered scans.

### Be careful with partitioning

If the table retains years of history and hundreds of millions of rows, consider partitioning/archival, but do not mechanically partition by `scheduled_at` if jobs can retry months later: active jobs would remain stuck in old partitions. Choose a model aligned with active queries and retention, potentially separating pending state from attempt history.

## 9. Creating the Job and Business Data in the Same Transaction

Suppose when creating an order, the system must schedule a confirmation email one hour later. An anti-pattern:

~~~java
orderRepository.save(order);
mailScheduler.scheduleEmail(order); // Written elsewhere afterward.
~~~

If the process crashes between the two operations, the order exists without the email intent. Conversely, if the email is created before the order commits, you might send an email for a rolled-back transaction.

When both share the same database, the **transactional outbox** is a common choice:

~~~text
BEGIN TRANSACTION
  INSERT / UPDATE business order
  INSERT scheduled_mail(
    scheduled_at,
    next_attempt_at,
    status='PENDING',
    business_idempotency_key,
    ...
  )
COMMIT

After commit:
  dispatcher reads due jobs
  SMTP submission runs outside the transaction
~~~

Spring example:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final ScheduledMailRepository scheduledMail;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ScheduledMailRepository scheduledMail,
            Clock clock) {
        this.orders = orders;
        this.scheduledMail = scheduledMail;
        this.clock = clock;
    }

    @Transactional
    public void confirmOrder(ConfirmOrderCommand command) {
        Order order = orders.confirm(command);

        Instant plannedAt = clock.instant()
                .plus(Duration.ofHours(1));

        scheduledMail.insertIfAbsent(
                new ScheduledMailIntent(
                        order.tenantId(),
                        "ORDER_RECEIPT",
                        "ORDERS",
                        order.customerRef(),
                        order.payloadRef(),
                        "ORDER_RECEIPT:" + order.id(),
                        plannedAt,
                        plannedAt,
                        "PENDING"));
    }
}
~~~

`OrderRepository`, `ConfirmOrderCommand`, `ScheduledMailRepository`, and the records in this example are application abstractions, not built into Spring Mail. `insertIfAbsent` must execute idempotently using a unique constraint and conflict handling; do not merely check `exists` and then insert separately due to race conditions.

**Never call `mailSender.send(...)` inside the order-creation transaction.** SMTP is a network side effect that does not roll back with the database; keeping a transaction open across SMTP holds resources too long and can send emails for transactions that ultimately roll back.

## 10. Creating Jobs via UPSERT to Prevent Duplicate Intents

With PostgreSQL, you can prevent creating two jobs for the same business event using a unique constraint and `ON CONFLICT`:

~~~sql
INSERT INTO scheduled_mail (
    id, tenant_id, notification_type,
    sender_profile_id, recipient_ref, payload_ref,
    business_idempotency_key,
    status, scheduled_at, next_attempt_at
) VALUES (
    :id, :tenant_id, :notification_type,
    :sender_profile_id, :recipient_ref, :payload_ref,
    :business_key,
    'PENDING', :scheduled_at, :scheduled_at
)
ON CONFLICT (tenant_id, business_idempotency_key)
DO NOTHING;
~~~

After a conflict, code must **identify the existing job** and return the ID/status matching the API contract. Do not assume a retried request is allowed to alter the old job's schedule; *create* and *reschedule* operations should have distinct contracts.

### When should you avoid a full DO UPDATE?

An HTTP retry may carry a stale payload while the user has already cancelled or rescheduled. If UPSERT unconditionally runs `DO UPDATE SET status='PENDING'`, an old request could "resurrect" a CANCELLED or SUBMITTED job. Update only via valid transitions, checking version/status and authorization.

## 11. Separating User Schedule from Deadlines and Retry Schedules

Three distinct conditions:

~~~text
scheduledAt:     do not send earlier than this timestamp
nextAttemptAt:   do not retry/defer earlier than this timestamp
expiresAt:       after this timestamp, no longer meaningful to send
~~~

When selecting due jobs:

\[
\text{eligible}(j,t) =
  j.status \in \{PENDING,RETRY\}
  \land j.scheduledAt \le t
  \land j.nextAttemptAt \le t
  \land (j.expiresAt = null \lor t < j.expiresAt)
\]

In practice, you must also check suppression/consent, user preferences, quotas, sender eligibility, and business rules **right before sending**.

Example of an expired OTP:

~~~text
scheduledAt   = 09:00:00
expiresAt     = 09:05:00
nextAttemptAt = 09:06:00 due to provider outage
~~~

At 09:06, do not send an expired OTP just because a worker finally got a permit. Move the job to `EXPIRED` and record a non-sensitive reason. Marketing emails may have an entirely different deadline; do not apply one expiry across every notification category.

## 12. How Does the Dispatcher Find Due Jobs?

A dispatcher is typically woken on a schedule, fetches a **small batch**, and submits only jobs it can process immediately:

~~~text
Scheduler tick
      |
      v
Query jobs WHERE status in PENDING/RETRY
    AND scheduledAt <= now
    AND nextAttemptAt <= now
      |
      v
Claim atomically
      |
      v
Load payload and check eligibility
      |
      v
Acquire provider rate/concurrency permit
      |
      v
Begin SMTP attempt
      |
      v
Save outcome
~~~

Do not fetch 100,000 due jobs and `submit` them all into an in-memory `ThreadPoolTaskExecutor` queue. When throughput is only a few emails/sec, jobs waiting long in the executor queue can lose their leases, lose state on restart, or get reclaimed by another worker.

### Poll interval and batch size

Suppose the scheduler runs every second, claiming up to 50 jobs per tick. That number **does not guarantee 50 emails/sec**; throughput still depends on quotas, concurrency, MIME composition time, SMTP latency, and worker count. Size batches to actual capacity rather than blindly increasing batch size to "send faster".

### Should the dispatcher wake immediately when a new job arrives?

Simple polling usually suffices for second/minute SLAs. For lower latency, you can emit a signal via a broker or database notification after commit to wake workers early. However, **the database remains the source of truth**: if signals are dropped, periodic polling must ensure due jobs are not missed.

## 13. Atomic Claiming with PostgreSQL SKIP LOCKED

With multiple Spring Boot replicas, this statement:

~~~sql
SELECT id FROM scheduled_mail
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP;
~~~

**is not enough**. Two workers can read the same job before either marks it as being processed.

PostgreSQL supports `FOR UPDATE SKIP LOCKED` so a worker grabs rows not locked by another transaction. A claim statement:

~~~sql
WITH eligible AS (
    SELECT id
    FROM scheduled_mail
    WHERE status IN ('PENDING', 'RETRY')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND next_attempt_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE scheduled_mail AS job
SET status = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    claim_token = :claim_token,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
FROM eligible
WHERE job.id = eligible.id
RETURNING
    job.id,
    job.claim_token,
    job.version,
    job.scheduled_at,
    job.next_attempt_at;
~~~

This runs inside a **short transaction**, then commits. `SKIP LOCKED` skips rows locked by other transactions; it fits queue consumers well, though it does not guarantee strict FIFO.

`:claim_token` is a random UUID generated by the worker for the claim round. You can use one shared token for the batch, though tracking explicit **attempt ownership** per job is better; database transactions and update predicates must still protect each row. A worker must track the IDs/claim tokens of the jobs it truly owns.

### Do not hold database row locks during SMTP

Wrong:

~~~text
BEGIN
  SELECT ... FOR UPDATE
  JavaMailSender.send(...)
  UPDATE status
COMMIT
~~~

SMTP can block for several seconds. Holding transactions and row locks throughout keeps database connection pools occupied, blocks cancel/reschedule operations, and increases contention.

Better:

~~~text
TX1: Claim + set lease + COMMIT

SMTP submission (without holding TX1)

TX2: Save outcome if claim token is still current
~~~

A crash can occur between TX1 and TX2. Leases, idempotency, and `UNKNOWN` handling are mandatory layers to resolve mid-flight states; `SKIP LOCKED` does not guarantee exactly-once mail sending on its own.

## 14. Leases and Fencing Tokens: Recovering From Worker Crashes

A worker can crash after claiming but before updating the outcome:

~~~text
Worker A claims job
   status=CLAIMED
   leaseUntil=09:02
   claimToken=A-123

Worker A crashes

After lease expires:
   Worker B can recover job
   claimToken=B-789
~~~

If A was actually just paused for a long time and resumed, A might write an outcome after B. Therefore every worker state update must enforce ownership:

~~~sql
UPDATE scheduled_mail
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    lease_until = NULL,
    claim_token = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
RETURNING id;
~~~

If 0 rows are updated, the worker **has lost the right to mutate state** and must treat it as a race requiring investigation/reconciliation—never overwrite with an unconditional update.

### Lease expiry does not mean "SMTP was not sent"

This is a crucial point:

~~~text
Worker A claims
Worker A calls SMTP
SMTP provider accepts
Worker A crashes before saving SUBMITTED
Lease expires
Worker B sees expired PROCESSING
~~~

If B automatically resets the job to PENDING and resends, the recipient may get **two emails**. Fencing tokens protect the database from stale writers; they **cannot recall an email already submitted to the SMTP server**.

Therefore, separate two cases:

- **CLAIMED before submission started**, with evidence no external side effect occurred: safe to return to PENDING for reprocessing.
- **PROCESSING/attempt already started** without a saved outcome: the provider may have accepted it; transition to `UNKNOWN` for reconciliation or a dedicated retry policy.

Even recording "submission started" in the database and actually making the network call cannot form a strictly atomic transaction across the DB and SMTP. The system must recognize that limit instead of making false guarantees.

## 15. Marking Submission Start Before Calling JavaMailSender

After claiming and checking business eligibility and quotas, a worker can create an **attempt record** before calling SMTP:

~~~sql
CREATE TABLE mail_submission_attempt (
    id UUID PRIMARY KEY,
    mail_job_id UUID NOT NULL REFERENCES scheduled_mail(id),
    attempt_number INT NOT NULL,
    provider_id VARCHAR(80) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(24),
    error_code VARCHAR(80),
    provider_message_id VARCHAR(255),
    UNIQUE (mail_job_id, attempt_number)
);
~~~

And inside a transaction:

~~~sql
UPDATE scheduled_mail
SET status = 'PROCESSING',
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'CLAIMED'
  AND claim_token = :claim_token
  AND (expires_at IS NULL
       OR expires_at > CURRENT_TIMESTAMP)
RETURNING attempt_count;
~~~

If successful, insert a `mail_submission_attempt` row for that attempt in the **same transaction**, commit, and only then call `JavaMailSender.send(...)`.

### Why doesn't attempt_count increment when denied by a rate limiter?

If SMTP cannot be called yet because quota lacks a permit, that is a **deferral**, not an SMTP attempt. Set a new `next_attempt_at`, release the claim, and leave `attempt_count` untouched. Rate-limiter deferrals can be metered separately rather than counting against max SMTP retries.

### What if an error occurs while composing MIME?

Template/attachment/resource errors happen **before actual submission** if composition runs before the network call. You can record `MIME_PREPARATION_FAILED` and track `attempt_count` vs. `preparation_attempt_count` per policy; never claim the provider was called. Whether to "compose first or reserve permit first" is a trade-off that must be clearly documented in the dispatcher.

## 16. Updating State Using Compare-and-Set

A safe state transition typically predicates on **ID, current status, and ownership/version**:

~~~sql
UPDATE scheduled_mail
SET status = 'RETRY',
    next_attempt_at = :next_attempt_at,
    last_failed_at = CURRENT_TIMESTAMP,
    last_error_code = :safe_error_code,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
RETURNING id;
~~~

`:safe_error_code` should be a normalized enum/code such as `SMTP_TEMPORARY_FAILURE`; do not dump raw `exception.getMessage()` because providers may echo recipient addresses or sensitive data.

When 0 rows are updated:

- Another worker may have claimed the job after lease expiry.
- The user may have cancelled before sending began.
- Another component may have already recorded the outcome.
- The worker may be holding a stale claim token.

**Do not work around this by removing status/token predicates and retrying the update.** Query the current state and apply the appropriate reconciliation policy.

## 17. Cancelling and Rescheduling Must Handle Concurrency

Suppose a user schedules 10:00 and then changes it to 11:00. An HTTP request may arrive right as the dispatcher is claiming the job.

### While still PENDING or RETRY

It can be rescheduled atomically:

~~~sql
UPDATE scheduled_mail
SET scheduled_at = :new_scheduled_at,
    next_attempt_at = :new_scheduled_at,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND tenant_id = :tenant_id
  AND status IN ('PENDING', 'RETRY')
  AND version = :expected_version
RETURNING id, version;
~~~

If the update succeeds, the new schedule is saved. If not, do not assume the job changed; return a conflict or the actual current state to the caller. If the job is already claimed, business rules may require the worker to release the claim before allowing a reschedule.

### When already CLAIMED or PROCESSING

Cancelling in CLAIMED state may be allowed if it has **not crossed the point of no return** and the transaction enforces ownership. Once the SMTP call has started, you cannot guarantee preventing delivery to the recipient.

An API should make this explicit:

~~~text
Cancellation accepted:
    job was PENDING/RETRY -> CANCELLED

Cancellation rejected/conflict:
    job is PROCESSING/SUBMITTED/UNKNOWN
    cannot guarantee email will not be sent
~~~

Do not return "Cancelled successfully" after merely setting a flag while a worker on another thread has already sent via SMTP. For emails already accepted by the provider, any "recall" capability (if available) is provider-dependent business logic, not a SQL rollback.

## 18. Creating the Scheduler in Spring Boot

A simple way to wake the dispatcher is `@Scheduled`:

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
public final class ScheduledMailPoller {
    private final MailDispatchService dispatcher;

    public ScheduledMailPoller(
            MailDispatchService dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
            fixedDelayString = "${app.mail.dispatch.poll-delay-ms:1000}")
    public void dispatchDue() {
        dispatcher.processReadyBatch();
    }
}
~~~

`MailDispatchService` is an application service, not a built-in Spring Mail class. The scheduler only triggers job discovery; it does not keep all schedules in RAM.

Example configuration:

~~~yaml
app:
  mail:
    dispatch:
      poll-delay-ms: 1000
      batch-size: 50
      max-concurrent: 5
      lease-seconds: 120
~~~

The `app.mail.dispatch.*` properties are **custom application configuration**. Putting them in YAML does not automatically create a durable scheduler or outbox; the application must bind and execute them.

### fixedDelay vs. fixedRate

- `fixedDelay`: interval between **when the previous invocation finishes** and **when the next invocation starts**, per scheduler semantics.
- `fixedRate`: attempts to run on a fixed cadence; can cause queued runs or overlaps depending on executor/task configuration.
- `cron`: fires on a calendar schedule; suitable for triggering the dispatcher or periodic tasks, not as a replacement for storing `scheduled_at` per mail job.

**Do not run thousands of synchronous SMTP submissions directly inside a scheduled invocation.** Use a bounded worker pool, claim batches matching capacity, and decouple network I/O from the scheduler tick.

### Multiple replicas all trigger @Scheduled

If 4 Spring Boot pods are deployed, every pod can run `@Scheduled`. There is no built-in automatic leader election ensuring only one pod runs. With PostgreSQL `SKIP LOCKED` and proper claim/lease handling, multiple dispatchers can compete safely. For a cron task that must execute only once cluster-wide, add appropriate distributed locking.

## 19. Flow of a Mail Job Through Service Layers

A design separating responsibilities:

~~~text
ScheduledMailPoller
   |
   v
MailDispatchService
   |
   +-- MailJobRepository.claimDueBatch()
   +-- EligibilityService.validate()
   +-- ProviderQuotaGate.tryReserve()
   +-- MimeMessageFactory.compose()
   +-- MailSubmissionAdapter.submit()
   +-- MailJobRepository.commitOutcome()
~~~

Abstractions should have clear contracts:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface MailJobRepository {
    List<ClaimedMailJob> claimDueBatch(
            Instant now, int batchSize);

    boolean beginSubmission(UUID id, UUID claimToken);

    boolean markSubmitted(
            UUID id, UUID claimToken, Instant submittedAt);

    boolean deferForRetry(
            UUID id, UUID claimToken,
            Instant nextAttemptAt,
            String errorCode);

    boolean markUnknown(
            UUID id, UUID claimToken, String errorCode);
}

public record ClaimedMailJob(
        UUID id,
        UUID claimToken,
        String notificationType,
        String payloadRef,
        Instant scheduledAt,
        Instant nextAttemptAt,
        Instant expiresAt) {
}
~~~

`MailJobRepository` and `ClaimedMailJob` are illustrative code. Every state-persisting method should use a short transaction and check token/status. Methods return `false` when state is no longer compatible; callers must handle lost claims rather than retrying unconditional writes.

## 20. Example Dispatcher Integrating JavaMailSender

The snippet below shows the main flow; it intentionally uses interfaces to avoid mixing SQL, SMTP, and retry logic in one class:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;

@Service
public final class MailDispatchService {
    private final MailJobRepository jobs;
    private final MailSubmissionAdapter sender;
    private final MailErrorPolicy errorPolicy;
    private final Clock clock;

    public MailDispatchService(
            MailJobRepository jobs,
            MailSubmissionAdapter sender,
            MailErrorPolicy errorPolicy,
            Clock clock) {
        this.jobs = jobs;
        this.sender = sender;
        this.errorPolicy = errorPolicy;
        this.clock = clock;
    }

    public void processReadyBatch() {
        Instant now = clock.instant();
        for (ClaimedMailJob job :
                jobs.claimDueBatch(now, 50)) {
            dispatchOne(job);
        }
    }

    private void dispatchOne(ClaimedMailJob job) {
        // Production: re-check consent, expiry, quota,
        // sender authorization, and claim ownership before submitting.
        if (!jobs.beginSubmission(job.id(), job.claimToken())) {
            return;
        }

        try {
            sender.submit(job);
            boolean saved = jobs.markSubmitted(
                    job.id(), job.claimToken(), clock.instant());
            if (!saved) {
                // Do not auto-resend; reconcile claim/state.
                reportStateConflict(job.id());
            }
        } catch (MailException ex) {
            MailSubmissionDecision decision =
                    errorPolicy.decide(ex, clock.instant());
            if (decision.kind() == SubmissionKind.RETRY) {
                jobs.deferForRetry(
                        job.id(), job.claimToken(),
                        decision.nextAttemptAt(),
                        decision.errorCode());
            } else {
                jobs.markUnknown(
                        job.id(), job.claimToken(),
                        decision.errorCode());
            }
        }
    }

    private void reportStateConflict(java.util.UUID jobId) {
        // Log jobId + internal error code; alert reconciliation.
    }
}
~~~

`MailSubmissionAdapter`, `MailErrorPolicy`, `MailSubmissionDecision`, and `SubmissionKind` are application abstractions. This example is **not a complete production implementation**:

- Does not yet implement `FAILED` for permanent errors, pre-submit quota deferral, MIME preparation failure handling, lease recovery, or outbox reservation.
- `catch (MailException)` does not cover all I/O/resource/database errors; errors must be classified by phase.
- When SMTP accepted the message but `markSubmitted` fails, do not retry immediately. Record and reconcile the outcome.
- Before `beginSubmission`, re-check eligibility/expiration; in a real application, claiming, eligibility, and transitions must align under DB conditions.
- If the method processes 50 jobs sequentially while each SMTP call is slow, throughput will suffer; you can dispatch onto a bounded executor while still preserving leases and not claiming beyond capacity.

### SMTP submission adapter

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public interface MailSubmissionAdapter {
    void submit(ClaimedMailJob job);
}

public final class SmtpMailSubmissionAdapter
        implements MailSubmissionAdapter {
    private final JavaMailSender mailSender;
    private final ScheduledMimeMessageFactory factory;

    public SmtpMailSubmissionAdapter(
            JavaMailSender mailSender,
            ScheduledMimeMessageFactory factory) {
        this.mailSender = mailSender;
        this.factory = factory;
    }

    @Override
    public void submit(ClaimedMailJob job) {
        MimeMessage message = mailSender.createMimeMessage();
        factory.populate(message, job);
        mailSender.send(message);
    }
}
~~~

`ScheduledMimeMessageFactory.populate(...)` must be designed to report content-preparation errors distinctly. If using `MimeMessageHelper`, `jakarta.mail.MessagingException` usually needs handling inside the factory. The adapter example assumes the factory translates such errors into a meaningful application exception instead of throwing an undeclared checked exception.

One advantage of an adapter is that business/scheduler code stays insulated from SMTP details and can swap in a fake sender during unit tests.

## 21. Controlling Time with Clock

Do not scatter `Instant.now()` calls across classes if you need to test time boundaries:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {
    @Bean
    Clock utcClock() {
        return Clock.systemUTC();
    }
}
~~~

In tests you can use:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-15T08:59:59Z"),
        ZoneOffset.UTC);
~~~

Tests do not need `Thread.sleep(...)` to wait until 09:00. You can instantiate a new fixed clock after the deadline or use a mutable test clock controlled by the test. Timestamps for **business decisions** must share a consistent clock source; if SQL uses `CURRENT_TIMESTAMP` while Java uses a fake clock, integration tests must account for that difference.

### Database clock vs. application clock

A SQL claim uses `CURRENT_TIMESTAMP` from the DB server; the application sometimes computes `nextAttemptAt` in Java. If clocks drift, jobs can run early/late or leases can expire incorrectly.

Operational rules:

- Synchronize host/DB clocks via reliable time synchronization.
- Use UTC/instants in state.
- Explicitly choose the **authoritative clock for due/lease decisions**; for DB claims, prefer the DB clock inside that transaction.
- Never trust client timestamps as the clock deciding whether a job is due.
- Monitor clock skew across regions or external dependencies.

## 22. Retries Differ From Changing the Original Schedule

When the SMTP provider returns a temporary error, update:

~~~text
status         = RETRY
scheduled_at   = unchanged
next_attempt_at= now + backoff
attempt_count  = actual attempt_count
last_error_code= SMTP_TEMPORARY_FAILURE
last_failed_at = now
~~~

Do not advance `scheduled_at` to the retry time if it represents the **user-selected schedule**. That preserves visibility into:

- How delayed was the email relative to the original schedule?
- How much delay was caused by quotas?
- How many times was SMTP actually called?
- How often did users reschedule vs. automatic retries?

### Which retries are safe?

Not every exception guarantees it is safe to call again:

| Response | Recommended policy |
|---|---|
| Template/MIME build error | Do not retry SMTP; fix data or resources |
| Authentication rejected | Pause route, fix credentials |
| Explicit temporary SMTP rejection | Retry with backoff and rate permit |
| Permanent SMTP rejection | Mark FAILED / suppress, do not retry blindly |
| TCP connect failure before SMTP session | May retry per policy |
| Connection lost after DATA | UNKNOWN; provider may have accepted |
| `mailSender.send` returns normally | Mark SUBMITTED, do not retry for missing delivery events |

A `MailSendException` can wrap multiple distinct causes, especially when sending batch messages. Classifiers must inspect phase, status code, and known outcomes rather than treating every `MailException` as temporary.

## 23. Exponential Backoff and Jitter for next_attempt_at

If 1,000 jobs all fail at 09:00 and all retry at 09:01, workers can simultaneously open bursts of SMTP connections, triggering another wave of throttling.

**Exponential backoff** with a ceiling:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where:

- `d0` is the base delay.
- `n` is the consecutive failure count.
- `dmax` is the maximum delay.

Add jitter to spread out retries:

\[
d_{\text{actual}} \sim U(0,d_n)
\]

With **full jitter**, the delay can be very small; if the provider prohibits immediate retries, enforce a minimum wait or pick a floored jitter variant.

Java example:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class MailRetrySchedule {
    private final long baseMillis;
    private final long maximumMillis;

    public MailRetrySchedule(Duration base, Duration max) {
        this.baseMillis = base.toMillis();
        this.maximumMillis = max.toMillis();
        if (baseMillis <= 0 || maximumMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid mail retry intervals");
        }
    }

    public Instant nextAttemptAt(
            Instant now, int failureNumber) {
        if (failureNumber < 1) {
            throw new IllegalArgumentException(
                    "failureNumber must start at 1");
        }

        long cap = baseMillis;
        for (int i = 1; i < failureNumber; i++) {
            if (cap >= maximumMillis) {
                break;
            }
            cap = cap > maximumMillis / 2
                    ? maximumMillis
                    : cap * 2;
        }

        long randomizedMillis =
                ThreadLocalRandom.current().nextLong(cap + 1);
        return now.plusMillis(randomizedMillis);
    }
}
~~~

For production use, also add:

- Max attempts, retry deadline, and total job age limits.
- Minimum retry delay if the provider rejects immediate retries.
- Classification of permanent/auth/UNKNOWN errors so they never enter blind retry.
- Respect for provider-specific cooldowns.
- Alignment of `next_attempt_at` with daily quota resets/rate-limiter permits.
- Persistence of `next_attempt_at` in the DB before the worker exits, not just a RAM timer.

### Does Retry-After apply to SMTP?

For **HTTP email APIs**, providers may return HTTP 429 and a `Retry-After` header; follow the API docs. For **SMTP**, there is no universal HTTP `Retry-After` equivalent. SMTP uses reply codes such as 421/450/451/452 and provider-specific enhanced codes; do not treat every 4xx as a "rate limit".

## 24. How Should State Update When a Rate Limiter Denies a Permit?

A due job is not always allowed to call SMTP immediately. A provider may have exhausted recipients/day, or an account may have hit its messages/second limit.

When quota has no permit available:

~~~text
Before:
status          = CLAIMED
scheduled_at    = 09:00
next_attempt_at = 09:00
attempt_count   = 0

Quota gate denies until 09:01

After:
status          = PENDING
scheduled_at    = 09:00  (unchanged)
next_attempt_at = 09:01
attempt_count   = 0     (no SMTP attempt made)
defer_reason    = PROVIDER_RATE_LIMIT
~~~

Save the **earliest retry time** aligned with permits/quotas instead of putting the worker to sleep for minutes.

When multiple limits overlap:

~~~text
message rate next available  = 09:01
daily quota next recheck     = 10:00
security lane policy        = 09:30
~~~

a reasonable time to re-evaluate is:

\[
\text{nextAttemptAt} =
 \max(\text{earliestAllowedAt}_1,
      \text{earliestAllowedAt}_2,
      \ldots)
\]

Note that you cannot always compute an exact timestamp if a provider exposes only estimated quotas. In that case, set a conservative recheck time and **always request a permit again** before submitting. For high-priority mail, approved quota reservations may be used; never bypass provider limits.

### Do not use RETRY for every kind of deferral

If SMTP was never called, `PENDING` with `defer_reason=QUOTA` is intuitive. `RETRY` should be reserved for jobs that actually failed under the application's contract. If you choose a different model, keep logic, dashboards, and attempt counters consistent.

## 25. Persisting State Transition History for Investigation

The main table shows the **latest** state, but operators also need to know which states a job passed through.

Example:

~~~text
09:00:00 PENDING
09:00:01 CLAIMED
09:00:02 PROCESSING
09:00:03 RETRY / TEMPORARY_SMTP_FAILURE
09:05:15 CLAIMED
09:05:16 PROCESSING
09:05:17 SUBMITTED
~~~

You can create an audit table:

~~~sql
CREATE TABLE scheduled_mail_status_event (
    id BIGSERIAL PRIMARY KEY,
    mail_job_id UUID NOT NULL
        REFERENCES scheduled_mail(id),
    transition_id UUID NOT NULL UNIQUE,
    from_status VARCHAR(24),
    to_status VARCHAR(24) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    actor_type VARCHAR(32) NOT NULL,
    actor_ref VARCHAR(100),
    attempt_number INT,
    safe_reason_code VARCHAR(80),
    detail_ref VARCHAR(160)
);

CREATE INDEX idx_mail_status_event_job
    ON scheduled_mail_status_event (
        mail_job_id, occurred_at, id);
~~~

Write the event **in the same transaction** as updating `scheduled_mail.status`. If inserting the audit event fails while the status commits, history no longer reflects reality.

An event record should include:

| Field | Purpose |
|---|---|
| `transition_id` | Prevents duplicate events on client retries |
| `from_status` / `to_status` | Tracks the state machine |
| `occurred_at` | Authoritative timestamp |
| `actor_type` | USER, SYSTEM, WORKER, PROVIDER_CALLBACK... |
| `actor_ref` | Opaque ID, not an email or password |
| `attempt_number` | Links to the SMTP submission round |
| `safe_reason_code` | QUOTA, SMTP_TEMPORARY, CANCELLED_BY_USER... |
| `detail_ref` | Access-controlled diagnostic reference, no raw MIME |

Do not log raw exceptions or SMTP transcripts as free-form text in the audit table. Provider responses can contain recipient addresses, subjects, or sensitive server details.

### Current state and event history must never contradict each other

With the database as source of truth:

~~~text
TX:
  UPDATE scheduled_mail ... WHERE expected_status/token
  INSERT scheduled_mail_status_event ...
COMMIT
~~~

If 0 rows are updated due to optimistic locking, **do not insert an event as if the transition happened**. Systems using dedicated event sourcing still need consistency and idempotent event appends.

## 26. Handling Delivery Events: Correlating to the Right Message Attempt

After SMTP accepts, some providers offer webhooks or DSNs reporting delivery outcomes:

~~~text
scheduled_mail:
  status       = SUBMITTED
  submitted_at = 09:05:17

provider webhook later:
  event        = DELIVERED
  event_time   = 09:05:45

scheduled_mail:
  status       = DELIVERED
  delivered_at = 09:05:45
~~~

To correlate events to the right mail job, store the **provider message ID** or attempt correlation when supported by the provider:

~~~text
mailJobId
  |
  +-- submissionAttemptId
         |
         +-- providerId
         +-- providerMessageId
         +-- submittedAt
~~~

If duplicate webhooks arrive, handle them idempotently by verified `eventId`/provider event key. If webhooks arrive **out of order**, enforce transition policies:

- `DELIVERED` must not be overwritten backward by a late `SUBMITTED` event.
- `BOUNCED` and `DELIVERED` may require a separate delivery status model when providers emit multiple event types for the same message.
- A provider callback carries its own source timestamp; also record **callback receipt time** to measure lag and detect clock skew.
- If the provider supplies no delivery confirmation, keep `delivered_at` null rather than inferring it from `submitted_at`.

### Separate submission state and delivery state in larger workflows

A single `status` column may not express everything:

~~~text
submissionStatus = ACCEPTED
deliveryStatus   = DEFERRED
processingStatus = DONE
~~~

For systems with multiple providers, multiple recipients, and bounce/complaint tracking, use **submission_attempt** and **delivery_event** tables while keeping job status focused on orchestration lifecycle. Avoid cramming every event into one giant enum lacking clear transitions.

## 27. Handling Messages With Multiple Recipients

One `MimeMessage` can target multiple To/Cc/Bcc recipients. Providers may accept some recipients, reject others, or report individual delivery outcomes.

If business logic needs status **per recipient**, one `submitted_at` on the job is insufficient. You can add:

~~~sql
CREATE TABLE scheduled_mail_recipient (
    mail_job_id UUID NOT NULL
        REFERENCES scheduled_mail(id),
    recipient_ref VARCHAR(160) NOT NULL,
    recipient_role VARCHAR(8) NOT NULL,
    submission_status VARCHAR(24) NOT NULL,
    delivery_status VARCHAR(24),
    submitted_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    PRIMARY KEY (mail_job_id, recipient_ref)
);
~~~

This schema assumes `recipient_ref` has unique semantics within one job; if the same mailbox appears in multiple roles or carries distinct recipient delivery IDs, adjust the primary key accordingly.

For personalized emails, one **mail job per recipient** is usually simpler to audit, retry, and protect Bcc privacy. When broadcast requirements exist, pick a structure matching the per-recipient semantics the provider actually returns.

## 28. APIs to Create, View, Reschedule, and Cancel Schedules

An API should explicitly return the **current status and timestamps** rather than just `200 OK` and the string "email sent".

### Creating a schedule request

~~~http
POST /api/notification-jobs
Idempotency-Key: order-receipt-1001-v1
Content-Type: application/json

{
  "notificationType": "ORDER_RECEIPT",
  "businessRef": "order-1001",
  "scheduledAt": "2026-11-16T09:00:00+07:00"
}
~~~

On the server:

1. Authorize access to `businessRef`.
2. Accept only permitted `notificationType` values.
3. Parse `scheduledAt` into `OffsetDateTime` or a type with full timezone info to convert to `Instant`.
4. Validate timing rules, advance-booking limits, and expiry policies.
5. Insert a `PENDING` job with `next_attempt_at = scheduled_at` inside a transaction.
6. Return an opaque ID and status fields.

Example response:

~~~json
{
  "jobId": "018d51e2-13d9-7479-a1a7-256b9f641100",
  "status": "PENDING",
  "scheduledAt": "2026-11-16T02:00:00Z",
  "nextAttemptAt": "2026-11-16T02:00:00Z",
  "submittedAt": null,
  "version": 1
}
~~~

This is an illustrative API, not a built-in Spring Mail endpoint. Never let clients pass raw SMTP credentials, arbitrary From addresses, unauthorized HTML emails, or arbitrary quota overrides.

### Rescheduling

~~~http
PATCH /api/notification-jobs/{jobId}/schedule
If-Match: "1"
Content-Type: application/json

{
  "scheduledAt": "2026-11-16T10:00:00+07:00"
}
~~~

The server allows rescheduling only in valid states, validates `version`/ETag, and records the transition. If the job is already claimed/submitting, it can return HTTP 409 Conflict per policy. Never reply "Rescheduled successfully" while silently letting a worker send on the old schedule.

### Cancelling

~~~http
POST /api/notification-jobs/{jobId}/cancel
~~~

Return distinct outcomes:

~~~text
CANCELLED: job was still in a cancellable state
CONFLICT: job is PROCESSING / already SUBMITTED
ALREADY_CANCELLED: repeated request, idempotent
NOT_FOUND / FORBIDDEN: unauthorized or job does not exist
~~~

Never let responses leak the existence of another tenant's job. When unauthorized, responses must obey the application's API security policy.

## 29. Recurring Schedules Differ From One-Shot Send Jobs

A `scheduled_mail` table stores **concrete send instances**. If a user asks:

> Send the report at 08:00 every Monday local time.

then create a separate **recurring schedule** and materialize individual job occurrences:

~~~text
RecurringSchedule
  id=weekly-report-42
  time=08:00
  dayOfWeek=MONDAY
  zoneId=Asia/Ho_Chi_Minh
  status=ACTIVE
  revision=3
            |
            v
ScheduledMail occurrence #1
  scheduledAt=...
  status=SUBMITTED
            |
            v
ScheduledMail occurrence #2
  scheduledAt=...
  status=PENDING
~~~

This allows:

- Pausing/cancelling the overarching schedule without deleting past send history.
- Giving each occurrence its own `scheduled_at`, `next_attempt_at`, and `status`.
- Ensuring last week's retries never shift next week's scheduled time.
- Giving each occurrence an idempotency key like `scheduleId:occurrenceLocalDate:revision`.
- Handling DST and timezones during **occurrence generation** instead of when the SMTP worker submits.

**Do not treat a single mail job as a recurring schedule by overwriting `scheduled_at` after every send.** That erases history and mixes the previous occurrence's `submittedAt` with the new schedule.

### Scheduler misfires after downtime

If the application shuts down at 08:00 and restarts at 09:30, the system must have a policy:

1. **Catch up:** send missed occurrences if still within expiry.
2. **Skip:** drop occurrences that are too late and generate the next one.
3. **Coalesce:** combine multiple missed occurrences into one summary if business rules allow.
4. **Manual review:** require operator intervention for sensitive notifications.

Misfire policies should be **persisted as configuration/business rules**, not left to accidental behavior when a cron tick is missed.

## 30. When Is Quartz Needed Instead of @Scheduled?

Some systems use Quartz with a JDBC JobStore to persist triggers/jobs, especially with complex cron schedules, calendars, and advanced scheduling needs.

However, even when Quartz **triggers tasks on schedule and persists triggers**, the email workflow still has to manage:

- Individual mail job states.
- Idempotency keys.
- SMTP submission attempts.
- `UNKNOWN_OUTCOME` and delivery event handling.
- Cancel/reschedule permissions.
- Provider quotas and retries.
- Content/recipient protection.

| Approach | Best fit | What you still must build |
|---|---|---|
| `@Scheduled` + database outbox | Many email jobs with individual timestamps, due-job queries | Claim/lease, state machine, retries, metrics |
| Quartz JDBC JobStore | Complex crons/triggers/calendars | Mail lifecycle, SMTP idempotency, delivery tracking |
| Message queue delayed delivery | Event-driven pipelines, low latency if broker supports it | Persistence/state, cancellation, retry/expiry semantics |
| External scheduler | Organizations with a shared scheduling service | Mail job state, routing, quotas, outage recovery |

No option guarantees **exactly-once delivery** over SMTP by itself. A Quartz trigger "firing" does not mean the email was "delivered".

## 31. Retrying After a Worker Crash: A Decision Table

Consider these failure windows:

| Crash point | State left in DB | Recovery strategy |
|---|---|---|
| Before job creation commit | No job | Client retries business call with idempotency key |
| After job commit, before poll | PENDING | Next scheduler tick picks it up |
| After claim, before attempt | CLAIMED | Lease expiry; reclaim after verifying no submit occurred |
| After writing PROCESSING, before network call | PROCESSING | May appear UNKNOWN even if SMTP wasn't called; needs reconciliation/policy |
| After SMTP accepted, before DB commit | PROCESSING | Outcome UNKNOWN; avoid unconditional resend |
| After DB marks SUBMITTED | SUBMITTED | Do not resend; wait for delivery events |
| After RETRY commit, before next tick | RETRY | Query due when nextAttemptAt arrives |
| While provider webhook arrives | SUBMITTED/DELIVERED... | Idempotent callbacks and conditional transitions |

### Why can't every crash be solved by a simple retry?

There is no atomic distributed transaction between PostgreSQL and an SMTP server in standard designs. A `send(...)` call may finish on the server before the application records `SUBMITTED`. Retrying risks creating a duplicate email.

Mitigations:

- Record attempt state before starting network I/O.
- Mark `UNKNOWN` whenever definitive proof is missing.
- Use provider APIs/message traces or idempotency keys **only when the provider truly supports those semantics**.
- For resendable notifications, explicitly decide the acceptable duplicate risk.
- For sensitive transactions, require reconciliation/manual approval before retrying.
- Never rely on `Message-ID` as an absolute deduplication guarantee on the receiver side.

## 32. Using System Clocks and Accurate Timestamps

Common timestamp traps:

### 32.1. Stripping timezones in API inputs

~~~text
"2026-11-16T09:00:00"
~~~

This string is a **local date-time without an offset/timezone**. For users in Vietnam, Paris, or New York, it points to different instants. Require a timezone or an explicit offset:

~~~text
"2026-11-16T09:00:00+07:00"
~~~

### 32.2. Using SQL TIMESTAMP WITHOUT TIME ZONE

`TIMESTAMP WITHOUT TIME ZONE` stores no timezone/offset and easily causes confusion when app/DB session configs differ. For absolute send times, `TIMESTAMPTZ` is the right choice in PostgreSQL; it preserves instant semantics and displays according to session timezone.

### 32.3. Using the client's local clock for leases

Lease expiry must not depend on an untrusted timestamp sent by a browser. The database can use `CURRENT_TIMESTAMP` in claim/renew transactions; API request time is only validated business input.

### 32.4. Adding days in milliseconds for local schedules

A recurrence of "09:00 daily" is not the same as "add 86,400 seconds" when a timezone observes DST. Compute occurrences using local date/time + `ZoneId`, then convert to `Instant`.

### 32.5. Comparing timestamps as strings

~~~java
if (scheduledString.compareTo(nowString) <= 0) { ... }
~~~

Strings with different offsets do not necessarily sort lexicographically in instant order. Parse into `Instant` or `OffsetDateTime` and compare as temporal types.

### 32.6. Assuming submittedAt is always milliseconds after scheduledAt

With large backlogs, rate-limiter denials, or slow servers, `submittedAt` may lag by minutes or hours. SLAs should measure actual lag and alert when thresholds are breached.

## 33. Unit Test: Send Only When scheduled_at Arrives

The most critical invariant of a scheduling system is **no early sends**. You can test the policy using `Clock.fixed` and a pure function:

~~~java
import java.time.Instant;

public enum ScheduledMailStatus {
    PENDING,
    RETRY,
    CLAIMED,
    PROCESSING,
    SUBMITTED,
    DELIVERED,
    BOUNCED,
    FAILED,
    CANCELLED,
    EXPIRED,
    UNKNOWN
}

public record MailDueSnapshot(
        ScheduledMailStatus status,
        Instant scheduledAt,
        Instant nextAttemptAt,
        Instant expiresAt) {
}

public final class MailDuePolicy {
    private MailDuePolicy() {
    }

    public static boolean isDue(
            MailDueSnapshot job, Instant now) {
        boolean eligibleStatus =
                job.status() == ScheduledMailStatus.PENDING
                || job.status() == ScheduledMailStatus.RETRY;

        return eligibleStatus
                && !job.scheduledAt().isAfter(now)
                && !job.nextAttemptAt().isAfter(now)
                && (job.expiresAt() == null
                    || now.isBefore(job.expiresAt()));
    }
}
~~~

JUnit 5 + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class MailDuePolicyTest {
    private static final Instant NINE =
            Instant.parse("2026-11-16T09:00:00Z");

    @Test
    void doesNotSendBeforeScheduledInstant() {
        MailDueSnapshot job = new MailDueSnapshot(
                ScheduledMailStatus.PENDING,
                NINE, NINE, null);

        assertThat(MailDuePolicy.isDue(
                job, NINE.minusMillis(1))).isFalse();
        assertThat(MailDuePolicy.isDue(
                job, NINE)).isTrue();
    }

    @Test
    void retryMustWaitForNextAttemptAt() {
        MailDueSnapshot retry = new MailDueSnapshot(
                ScheduledMailStatus.RETRY,
                NINE,
                NINE.plusSeconds(300),
                null);

        assertThat(MailDuePolicy.isDue(
                retry, NINE.plusSeconds(60))).isFalse();
        assertThat(MailDuePolicy.isDue(
                retry, NINE.plusSeconds(300))).isTrue();
    }

    @Test
    void cancelledAndExpiredJobsNeverBecomeDue() {
        MailDueSnapshot cancelled = new MailDueSnapshot(
                ScheduledMailStatus.CANCELLED,
                NINE, NINE, null);
        MailDueSnapshot expired = new MailDueSnapshot(
                ScheduledMailStatus.PENDING,
                NINE, NINE, NINE.plusSeconds(120));

        assertThat(MailDuePolicy.isDue(
                cancelled, NINE.plusSeconds(1))).isFalse();
        assertThat(MailDuePolicy.isDue(
                expired, NINE.plusSeconds(120))).isFalse();
    }
}
~~~

This pure unit test verifies **time rules in Java**, not replacing integration tests for SQL `WHERE scheduled_at <= CURRENT_TIMESTAMP`, claiming/leasing, or actual provider sending. For SQL using the database clock, write integration tests with deterministic timestamps and proper transaction isolation.

## 34. Unit Test: Invalid Transitions Must Be Rejected

States should not change arbitrarily:

~~~text
PENDING -> CANCELLED      valid
PENDING -> SUBMITTED      invalid if bypassing submission
SUBMITTED -> PENDING      invalid
CANCELLED -> PROCESSING   invalid
RETRY -> PROCESSING       valid with proper claim/ownership
UNKNOWN -> RETRY          only when reconciliation/policy allows
~~~

Example validator for intentional transitions:

~~~java
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

public final class MailStatusTransitions {
    private static final Map<
            ScheduledMailStatus, Set<ScheduledMailStatus>> ALLOWED =
            Map.of(
                ScheduledMailStatus.PENDING,
                EnumSet.of(
                        ScheduledMailStatus.CLAIMED,
                        ScheduledMailStatus.CANCELLED,
                        ScheduledMailStatus.EXPIRED),
                ScheduledMailStatus.RETRY,
                EnumSet.of(
                        ScheduledMailStatus.CLAIMED,
                        ScheduledMailStatus.CANCELLED,
                        ScheduledMailStatus.EXPIRED),
                ScheduledMailStatus.CLAIMED,
                EnumSet.of(
                        ScheduledMailStatus.PROCESSING,
                        ScheduledMailStatus.PENDING,
                        ScheduledMailStatus.CANCELLED),
                ScheduledMailStatus.PROCESSING,
                EnumSet.of(
                        ScheduledMailStatus.SUBMITTED,
                        ScheduledMailStatus.RETRY,
                        ScheduledMailStatus.FAILED,
                        ScheduledMailStatus.UNKNOWN),
                ScheduledMailStatus.SUBMITTED,
                EnumSet.of(
                        ScheduledMailStatus.DELIVERED,
                        ScheduledMailStatus.BOUNCED)
            );

    private MailStatusTransitions() {
    }

    public static boolean mayTransition(
            ScheduledMailStatus from,
            ScheduledMailStatus to) {
        return ALLOWED.getOrDefault(
                from, Set.of()).contains(to);
    }
}
~~~

This is a minimal policy and does not cover all workflows. When adding `UNKNOWN` reconciliation, approved requeues, or complex delivery-status updates, build the full transition table; **never add an `else return true` for unexpected states**.

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class MailStatusTransitionsTest {
    @Test
    void rejectsResendOfAlreadySubmittedJob() {
        assertThat(MailStatusTransitions.mayTransition(
                ScheduledMailStatus.SUBMITTED,
                ScheduledMailStatus.PENDING)).isFalse();
    }

    @Test
    void allowsCancellationWhileStillPending() {
        assertThat(MailStatusTransitions.mayTransition(
                ScheduledMailStatus.PENDING,
                ScheduledMailStatus.CANCELLED)).isTrue();
    }
}
~~~

**Important:** a Java validator does not prevent database races on its own. Every SQL update still requires expected status/version/claim-token checks. Transition tests should accompany concurrency-tested repository tests.

## 35. Integration Test: Two Workers Never Claim the Same Job

One of the most important DB queue tests runs **two concurrent transactions on two connections**:

~~~text
Database has 1 due job J

Worker A starts claim TX
Worker B starts claim TX

Expected:
  Exactly one worker owns J
  Both cannot mark J as PROCESSING
~~~

When using `FOR UPDATE SKIP LOCKED`:

- Ensure two connections/transactions truly run concurrently rather than sharing one outer test transaction.
- Use a barrier like `CountDownLatch` to synchronize their starting point.
- Verify the claim token/version belongs to one worker.
- Verify the non-owning worker cannot update using the wrong claim token.
- Commit/roll back cleanly so locks do not hang the test.

### Crash-window test matrix

| Scenario | Condition | Expectation |
|---|---|---|
| IT-01 | Job not yet due | Not claimed, not sent |
| IT-02 | Exactly at scheduledAt | Eligible to claim |
| IT-03 | Retry not yet at nextAttemptAt | Not claimed |
| IT-04 | Two workers race | One owner per job |
| IT-05 | Worker crashes after claim, before submit | Reclaimed per lease and policy |
| IT-06 | Worker crashes after attempt started | Do not auto-resend as if outcome were certain |
| IT-07 | SMTP accepted, DB update fails | UNKNOWN/reconciliation, no blind retry |
| IT-08 | User cancels before claim | SMTP not called |
| IT-09 | User cancels while PROCESSING | Return conflict / appropriate outcome |
| IT-10 | Reschedule with stale version | Update rejected |
| IT-11 | Provider quota denied | Deferred, SMTP attempt not incremented |
| IT-12 | Permanent failure | FAILED, no infinite retries |
| IT-13 | Delayed delivery webhook | Does not regress SUBMITTED state |
| IT-14 | Duplicate webhook | Does not create double state events |
| IT-15 | DST overlap/gap | Handled per timezone policy |
| IT-16 | Recurrence misfire | Catch-up/skip/coalesce follows rules |
| IT-17 | Job expires before retry | EXPIRED, do not send |
| IT-18 | App restarts with PENDING jobs | Jobs remain intact in DB |

Use an SMTP sink/test double (such as GreenMail or Mailpit depending on the test flow) instead of sending real mail to customers. To simulate *connection lost after DATA*, the test double must control SMTP phases accurately; a mock simply throwing `RuntimeException` before `send` cannot model an ambiguous outcome.

## 36. Observing Schedule Impact and Status

A dashboard should not just count "sent" emails. Useful metrics:

| Metric | Purpose |
|---|---|
| `mail_scheduled_pending` | Unfinished PENDING/RETRY jobs |
| `mail_due_backlog_count` | Due jobs not yet claimed |
| `mail_dispatch_lag_seconds` | `attempt_started_at - scheduled_at` |
| `mail_submission_lag_seconds` | `submitted_at - scheduled_at` |
| `mail_attempt_total` | Actual provider invocation count |
| `mail_retry_scheduled_total` | Jobs transitioned to retry |
| `mail_quota_defer_total` | Deferrals due to missing permit |
| `mail_claim_conflict_total` | Claim token/status conflict count |
| `mail_expired_total` | Expired jobs not sent |
| `mail_cancelled_total` | Jobs cancelled per policy |
| `mail_unknown_outcome_total` | Attempts needing reconciliation |
| `mail_oldest_due_age_seconds` | Age of the oldest due job |
| `mail_delivery_event_total` | Delivery/bounce events if provider supports them |

Labels should stay low-cardinality, such as `notification_type`, `provider_id`, `status`, and `failure_kind`. Never put `mailJobId`, recipient emails, subjects, or raw error text into metric labels; they create high cardinality and risk leaking data.

### Measuring backlog accurately

A job scheduled for next month is PENDING, **not part of today's due backlog**. Dashboards should distinguish:

~~~text
scheduled future:
    scheduled_at > now

due pending:
    scheduled_at <= now
    next_attempt_at <= now
    status in PENDING/RETRY

waiting retry/quota:
    scheduled_at <= now
    next_attempt_at > now
~~~

Counting all PENDING rows as backlog triggers false alarms when users schedule far ahead. Conversely, counting only due jobs can hide a massive queue of deferred retries; monitor both perspectives.

### Setting SLAs by notification type

OTPs may have tight deadlines, periodic reports may tolerate a few minutes of delay, and campaigns may run within wide windows. Measure by **notification type** and provider quota; do not enforce the same delay threshold on every job.

## 37. Logs, Tracing, and Mail Job Privacy

Mail jobs often contain recipients, subjects, payloads, and references to user data. Statuses and schedules may be more widely observable than business payloads, so **never dump the whole entity**:

~~~java
// Avoid if toString() includes recipient, body, or secrets.
log.info("Scheduled email {}", job);

// Avoid: provider may echo email addresses in the exception.
log.error("Mail submission failed", exception);
~~~

Log according to an approved schema:

~~~text
event=scheduled_mail_transition
mailJobId=opaque-job-123
notificationType=ORDER_RECEIPT
fromStatus=PROCESSING
toStatus=RETRY
attempt=2
provider=PRIMARY_SMTP
reasonCode=SMTP_TEMPORARY_FAILURE
scheduleLagBucket=1m_5m
~~~

`mailJobId` should be an opaque ID, never built by concatenating emails or subjects. If support needs to look up real recipients, use an authorized and audited support tool rather than printing emails on every log line.

### Protect the status event table as well

Some events can be sensitive even without containing an email address:

~~~text
notificationType=PASSWORD_RESET
occurredAt=...
tenant=...
~~~

Combining timestamps and notification types can still reveal user activity. Restrict read access, retention, and export capabilities on status/audit tables under least-privilege principles.

### Never use raw exception messages as last_error_code

A provider might return:

~~~text
550 5.1.1 <customer@example.test> rejected
~~~

Instead of storing verbatim text, classify it:

~~~text
last_error_code=SMTP_PERMANENT_RECIPIENT_FAILURE
~~~

If raw diagnostics are needed during a special incident, store them in a separate restricted, short-retention channel rather than shipping them to centralized logs. Log only safe error codes and job states.

## 38. Authorization When Scheduling, Editing, and Cancelling

A request to change `scheduled_at` is more than updating a timestamp:

- Does the caller have permission to manage notifications for this tenant?
- Are they allowed to alter schedules for this category of email?
- Are the recipient and payload still valid for the business event?
- Has the job already been claimed, started sending, accepted, or cancelled?
- Does the schedule change violate quiet hours, consent, or SLAs?
- Could an already-`SUBMITTED` job be recreated improperly by an API retry?

### Never skip authorization just because job IDs are hard to guess

Even when IDs are random UUIDs, enforce tenant/owner checks in queries:

~~~sql
UPDATE scheduled_mail
SET status = 'CANCELLED',
    cancelled_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND tenant_id = :authorized_tenant_id
  AND status IN ('PENDING', 'RETRY')
  AND version = :expected_version
RETURNING id;
~~~

When 0 rows match, respond per authorization policy without revealing whether a job exists in another tenant.

### Re-check authorization at dispatch time

A user may unsubscribe after the job was created but before `scheduled_at`. For opt-out-governed content, the worker must re-check suppression lists/consent before submitting. Never treat "already scheduled" as permanent permission to send.

For security/transactional messages, legal/business exemptions and consent categories must be defined by the product; never lump every email under one policy.

## 39. Retention, Archival, and Content Protection

Scheduled jobs, attempts, provider events, and audit tables can grow rapidly. For long-term operations, define:

1. How long active jobs are kept.
2. How long terminal states (`SUBMITTED/FAILED/CANCELLED/EXPIRED`) are retained for support and auditing.
3. Retention policies for HTML bodies, attachments, and recipient data.
4. Whether deleting a job leaves behind an anonymized audit record.
5. Whether backups/database replicas and object storage share consistent protection policies.
6. Whether deletion propagates across all copies as required by regulations.

Do not purge PENDING/RETRY jobs solely because `created_at` is old; they may be scheduled far in the future. Do not archive a PROCESSING job holding an active lease without understanding its send state.

### Terminal status and original content have different lifecycles

An already-`SUBMITTED` email may only need to retain metadata:

~~~text
mailJobId
notificationType
scheduledAt
submittedAt
status
providerRef
errorCode (if any)
~~~

while raw MIME/attachments can be purged earlier per policy. If retries span days, payloads must remain readable, authorized, and version-stable. Never let a RETRY job point to a deleted temporary file.

### Store a snapshot or re-render at send time?

Two approaches:

| Approach | Pros | Risks |
|---|---|---|
| Snapshot content at job creation | Exact version approved at scheduling | Stores more PII; needs encryption/retention |
| Store template ID + required data, render at send time | Less raw MIME stored, can pull fresh data | Data/template changes alter message vs. creation time |

Define **content versioning** and rules for when business data changes or expires. For example, an issued invoice may require an immutable snapshot; an appointment reminder may need to read the latest appointment time. No single strategy fits every email type.

## 40. Runbook: Email Reached Due Time Without Sending

Suppose a customer asks why an email scheduled for 09:00 has still not arrived at 09:20. Diagnose in order:

~~~mermaid
flowchart TD
    A[Mail job has not reached recipient] --> B{Job exists in database?}
    B -- No --> C[Check intent-creation transaction / idempotency]
    B -- Yes --> D{Have scheduledAt and nextAttemptAt arrived?}
    D -- No --> E[Check timezone / rescheduled time / backoff]
    D -- Yes --> F{What is status?}
    F -- PENDING/RETRY --> G[Check claims, indexes, poller, quotas]
    F -- CLAIMED/PROCESSING --> H[Check lease, attempts, provider outcome]
    F -- SUBMITTED --> I[Check delivery/bounce at provider]
    F -- UNKNOWN --> J[Reconcile, do not resend blindly]
    F -- CANCELLED/EXPIRED/FAILED --> K[Check transition history and policy]
~~~

### Step 1: verify schedule and timezone

Query:

~~~sql
SELECT
    id, status, scheduled_at, next_attempt_at,
    expires_at, attempt_count,
    claimed_at, lease_until,
    submitted_at, updated_at, last_error_code
FROM scheduled_mail
WHERE id = :job_id;
~~~

Check which timezone/offset the client chose, whether it was rescheduled, and whether `next_attempt_at` reflects a retry or quota deferral.

### Step 2: if due but still PENDING

- Is the scheduler running on at least one instance?
- Does the query filter status and due time accurately?
- Is quota/capacity available? Was `next_attempt_at` pushed back?
- Is the DB connection pool exhausted?
- Are indexes/queries slow due to a large backlog?
- Is another tenant/lane monopolizing the executor?
- Are too many claimed jobs sitting in RAM with leases about to expire?

### Step 3: if stuck in CLAIMED/PROCESSING

- Is the lease still valid or expired?
- Is the worker actively sending over SMTP or hung in I/O?
- Are connect/read/write timeouts configured for the SMTP transport?
- Are attempt-started and provider-accepted logs present?
- Could the worker have crashed after the provider accepted?
- On lease expiry, does recovery separate unsubmitted claims from started attempts?

Never mass-reset `PROCESSING -> PENDING` to "unstick" jobs if any could have already been accepted; that risks duplicates.

### Step 4: if SUBMITTED but recipient has not seen it

- Check provider message trace/accepted ID if available.
- Check delivery, bounce, spam classification, or mailbox filters.
- Remember `submitted_at` marks successful submission, not inbox delivery.
- Do not automatically resend via another provider just because `delivered_at` is absent.

### Step 5: when the incident persists

Throttle low-priority traffic, protect OTP/transactional deadlines, record backlog age, and trigger incident procedures. Perform manual replays only with clear state/outcome visibility and operator authorization.

## 41. Common Design Mistakes

### 41.1. Using only ScheduledExecutorService/Thread.sleep

If schedules live only in RAM, restarts lose jobs. For business emails needing reliability, persist `scheduled_at` and status in a database/outbox.

### 41.2. Storing status without scheduled_at

A `PENDING` job does not tell you when it was supposed to send or whether it breached SLA. Store timestamps with clear semantics.

### 41.3. Storing scheduled_at without status

Workers will not know whether a job was already sent, cancelled, or needs retry, and may send the same email on every poll.

### 41.4. Overwriting scheduled_at with next retry time

Erases the original schedule; dashboards can no longer separate provider lag from business schedule adherence. Keep `scheduled_at` distinct from `next_attempt_at`.

### 41.5. Setting sentAt right before calling send

~~~java
job.setSubmittedAt(clock.instant());
mailSender.send(message);
~~~

If SMTP fails, the database may show "sent" even though it was never accepted. Write `submitted_at` only after submission succeeds; for unclear errors, use `UNKNOWN`.

### 41.6. Setting deliveredAt simply because JavaMailSender threw no exception

`send(...)` returning normally does not mean the message reached the inbox. Delivery confirmation requires an external signal.

### 41.7. Using @Scheduled without claim/lease

Multiple Spring Boot pods can pick up the same job and double-send. Use atomic claiming, ownership/fencing, and idempotency.

### 41.8. Plain SELECT followed by UPDATE

Two workers can both SELECT PENDING before either updates. Use transactions/locks/conditional updates so only one worker claims.

### 41.9. Holding DB transactions open across SMTP calls

Slow networks hold DB row locks and connections too long, increasing contention and timeouts. Separate short transactions for claiming and committing outcomes.

### 41.10. Resending all PROCESSING jobs when leases expire

If the server already accepted before the worker crashed, retrying creates duplicates. Separate pre-submit claims from unknown outcomes.

### 41.11. Using Message-ID as an exactly-once key

Message-ID is a header/correlation value, not an SMTP or receiver deduplication guarantee. Do not rely on it alone to stop duplicate emails.

### 41.12. Incrementing attempt_count when a rate limiter rejects

Counting non-SMTP deferrals as retries can prematurely exhaust max attempts. Separate quota deferrals from SMTP attempts.

### 41.13. Rescheduling via SQL UPDATE without status checks

A `SUBMITTED` or `CANCELLED` job could be resurrected by a stale request. Enforce status/version and permission checks on every transition.

### 41.14. Reporting cancellation success when PROCESSING

Cancelling a DB row cannot recall an already-started network submission. Return a conflict or an honest non-guaranteed state depending on workflow.

### 41.15. Using timezone-less LocalDateTime for absolute times

Especially dangerous with multi-timezone users or cross-region deployments. Convert to `Instant`, and store `ZoneId` separately for recurring rules.

### 41.16. Treating cron ticks as durable mail jobs

A tick missed while the app is off leaves no record to recover. Persist individual occurrence jobs and define a misfire policy.

### 41.17. Retrying business creation without an idempotency key

Timeouts cause clients to retry and create duplicate jobs. Use a business idempotency key with a unique constraint; do not hack around it by querying "is there an email with the same subject?".

### 41.18. Claiming more jobs than SMTP capacity

Jobs expire their leases while sitting in executor queues and get reclaimed by other workers. Match batch sizes to real throughput with bounded queues and backpressure.

### 41.19. Not storing state transition history

A single `FAILED` status hides how many retries occurred and when. Controlled event/attempt logs aid diagnostics.

### 41.20. Treating submitted and delivered as one status

Prevents distinguishing submission errors from post-acceptance bounces. Separate milestones and evidence sources.

### 41.21. Treating every SMTP exception as temporary

Auth failures or invalid senders cannot be fixed by infinite retries. Classify by response/phase and apply distinct policies.

### 41.22. Not checking consent when send time arrives

An email scheduled last week may no longer be permitted today. Revalidate suppression/eligibility right before submission.

### 41.23. Deleting payloads before jobs reach a terminal state

A worker retrying hours later loses the required content/attachments. Align retention between mail jobs and payload storage.

### 41.24. Putting email addresses or subjects into metric labels

Explodes cardinality and leaks data. Use bounded labels like notification type, provider, and status; inspect recipients through authorized business tools.

## 42. Frequently Asked Questions

**Is a database required to schedule emails?** For emails that can be dropped on process restart, an in-memory timer may suffice; for reliable business emails, persist intents and state in a database, outbox, or suitable scheduler store.

**Does Spring Mail have a `sendAt` API?** `JavaMailSender` builds and submits SMTP messages; durable scheduling and job state must be managed by the application or another scheduling layer.

**What data types should store timestamps?** For a concrete send, use `Instant` in Java and `TIMESTAMPTZ` in PostgreSQL. For recurrences, also store `ZoneId` and DST rules.

**How does `scheduled_at` differ from `next_attempt_at`?** `scheduled_at` is the business target time. `next_attempt_at` is the earliest time a worker may try next, which can shift due to retries or quotas.

**If `scheduled_at` is in the future, what is the status?** Usually `PENDING`; workers claim it only once both `scheduled_at` and `next_attempt_at` are due.

**What if a user schedules an email and then changes the time?** Update `scheduled_at` and `next_attempt_at` with optimistic concurrency/status checks. Never let stale requests overwrite a job already sending.

**When does status become SUBMITTED?** After the SMTP/API returns an accepted result per the adapter. This is not proof of delivery to the recipient's mailbox.

**Should the column be named `sent_at` or `submitted_at`?** `sent_at` works if defined clearly, though `submitted_at` more accurately conveys provider acceptance. Avoid vague names that imply delivered.

**Can a single status column cover the entire delivery lifecycle?** For simple workflows, yes. With multiple recipients, bounces/deferrals, and provider events, consider separate attempt/delivery tables.

**Should status and timestamp update in the same transaction?** Yes. If updated in separate unrelated transactions, a crash can leave `SUBMITTED` with `submitted_at = null`, or vice versa.

**Does `@Scheduled` preserve schedules across restarts automatically?** Not for individually registered runtime tasks. When `@Scheduled` polls a DB, jobs stay in the DB and resume after restarts.

**Does Quartz replace the `scheduled_mail` table?** Quartz can persist triggers/calendars and fire events on schedule, but mail business state, attempt history, idempotency, and delivery tracking still need an appropriate model.

**Can there be multiple dispatchers?** Yes, with atomic claiming, leases, and proper state checkpoints; `@Scheduled` across multiple pods does not automatically exclude other pods.

**Does `SKIP LOCKED` guarantee exactly-once email delivery?** No. It prevents two workers from claiming concurrently inside the transaction, not making SMTP and DB updates atomic.

**Does an expired lease mean the job definitely wasn't sent?** No. The worker may have called SMTP and crashed before committing. Track attempt starts and unknown states.

**Why have an `UNKNOWN` status?** For cases where it is unclear whether the provider accepted, such as losing the connection after DATA. Immediate retries risk duplicates.

**How do you prevent users from cancelling after sending?** Enforce state/ownership atomically. Once `PROCESSING/SUBMITTED`, the API must clearly state cancellation cannot be guaranteed.

**When quota runs out, should `attempt_count` increment?** Not if SMTP was never called. Record the defer reason and `next_attempt_at`, keeping `scheduled_at` intact.

**If a job is due but workers are slow, are emails lost?** No, if persisted durably and not expired/deleted. However, dispatch lag increases, requiring monitoring and capacity planning.

**Should all `SUBMITTED` jobs be kept forever?** Not by default. Define retention/auditing and purge sensitive payloads per policy while never deleting non-terminal jobs.

**How should status work for multi-recipient emails?** Decide whether status is message-level or recipient-level. If per-recipient tracking is needed, store recipient-level status/attempt events.

**Can `Message-ID` deduplicate retries?** Use it only for correlation; it does not guarantee a provider or receiver will deliver only once.

**What if application and DB clocks drift?** Due/lease checks can skew. Synchronize clocks and pick one authoritative time source, preferring DB time for atomic DB claims.

**Should every mail job store a cron expression?** One-shot mail jobs only need an instant. Recurring schedules belong in a separate recurring-schedule table that spawns concrete occurrence jobs.

**If a cron tick is missed while the app is off, does it catch up automatically?** That depends on the misfire policy—catch up, skip, coalesce, or manual review—which must be explicitly modeled and stored.

**What if no delivery webhook ever arrives?** Keep `SUBMITTED` with `delivered_at = null`, or a delivery state like `UNKNOWN/NOT_TRACKED` per your model. Never set delivered merely on SMTP success.

**Should Redis replace a database for send schedules?** Redis/delayed queues can play a role, but evaluate durability, restart recovery, cancellation, dedup, and business transactions. If business data lives in SQL, a same-DB outbox offers strong consistency.

**Do we need to test against production SMTP to verify scheduling?** No. Unit-test with a fixed clock/mock sender, and integration-test with PostgreSQL and an SMTP sink/test server. Production should use controlled, observable rollouts.

## 43. Summary

**"Storing send time together with message status"** is the foundation for turning an email send call into a **schedulable, retryable, cancellable, and observable** workflow in Spring Framework Mail.

The system should distinguish:

~~~text
scheduledAt    -> when the user/business wants to send
nextAttemptAt  -> earliest time a worker may try next
status         -> which stage the job is in
attemptCount   -> actual submission attempt count
claimedAt      -> when a worker took ownership
leaseUntil     -> when processing ownership expires
submittedAt    -> when the provider accepted
deliveredAt    -> when delivery was confirmed, if available
expiresAt      -> after which sending is no longer allowed
~~~

A reliable operational flow:

~~~text
Business transaction
      |
      v
INSERT scheduled_mail:
  scheduled_at + next_attempt_at + PENDING
      |
      v
Database commit
      |
      v
@Scheduled polls due rows
      |
      v
Atomic claim + lease
      |
      v
Revalidate eligibility + quota
      |
      v
Record submission attempt
      |
      v
JavaMailSender.send(...)
      |
      +-- Accepted -> SUBMITTED + submitted_at
      +-- Temporary -> RETRY + next_attempt_at
      +-- Permanent -> FAILED + last_error_code
      +-- Uncertain -> UNKNOWN + reconciliation
      |
      v
Provider delivery events (if available)
      |
      v
DELIVERED / BOUNCED + timestamps
~~~

Key principles:

1. **Persist schedules and statuses in a durable data store**, updating them transactionally with explicit transition conditions.
2. **Never mix the original schedule with retry timing**; keep `scheduled_at` and `next_attempt_at` separate.
3. **Never use `submitted_at` to claim inbox delivery**; distinguish submission from delivery.
4. **Claim safely across multiple workers**, while recognizing that leases/fencing do not create exactly-once SMTP by themselves.
5. **Handle cancellation, rescheduling, and retries with concurrency control**, never letting terminal jobs resurrect.
6. **Use Instant/UTC for absolute timestamps and ZoneId for recurrences**, with explicit DST and misfire rules.
7. **Monitor backlogs, dispatch lag, attempts, unknown outcomes, and status history**, not just successful send counts.

When time and status models are clearly defined from the start, the application can recover after restarts, pace sends within quotas, explain why an email was delayed, and handle support inquiries without guessing whether "the email was sent". At the same time, SMTP's inherent boundaries are represented honestly: **submitted to the provider** does not mean **delivered to the recipient**, and retrying is not always safe when the submission outcome is uncertain.

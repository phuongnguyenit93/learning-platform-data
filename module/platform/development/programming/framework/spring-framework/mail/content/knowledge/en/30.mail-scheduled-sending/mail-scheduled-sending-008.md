# Handling Expired or Skipped Emails

## 1. Why Might an Already-Scheduled Email Still Not Be Sent?

In a **Spring Framework Mail** application, email scheduling records a send intent now while executing `JavaMailSender.send(...)` at another time. Some emails wait for a delay; some are grouped into campaigns; others depend on business hours, quotas, or live business state.

Having a job in the queue does not mean **the job is still valid when a worker reaches it**.

Examples:

- An OTP is valid for 5 minutes, but the queue backs up for 12 minutes. Sending an expired code only causes confusion.
- A payment reminder was scheduled for 09:00, but the user already paid at 08:55. The email is no longer relevant.
- An event reminder was meant to send before the start time. When workers recover after an outage, the event is already over.
- A customer unsubscribes from marketing emails before send time. The message must be dropped from the schedule per policy.
- An email is waiting to retry, but the next retry falls past its **deadline**.
- A tenant runs out of quota or capacity. The email may wait, but must not wait forever.
- An administrator pauses or cancels a campaign. Unsent jobs must not auto-resume when the scheduler starts.
- A notification is classified as **intentionally skipped** because it is a duplicate, lacks a valid recipient, or is blocked by a business rule.

Therefore, **handling expired or skipped emails** is an essential part of **scheduled sending**: the system must decide when an email may still send, when to stop trying, when to reschedule, and how to record the reason.

A core principle:

> **Do not send an email solely because it is sitting in a queue. Send if and only if status, timing, send permissions, and business conditions remain valid at execution time.**

Spring Mail provides message building and sending; **deadlines, skip policies, outbox states, and safe retry rules** are up to your application design.

## 2. Distinguishing Scheduled Time, Due Time, and Expiration Time

A notification may require several timestamps:

| Field | Meaning |
|---|---|
| **created_at** | When the send intent was created |
| **scheduled_at** | Business target time to send the email |
| **not_before_at** | Earliest time sending may be attempted |
| **next_attempt_at** | Earliest time a worker may make the next attempt |
| **expires_at** | Deadline after which **no new submission** may begin |
| **claimed_at** | When a worker took ownership |
| **attempt_started_at** | When an SMTP attempt began |
| **submitted_at** | When the SMTP provider confirmed accepting the message |
| **completed_at** | When the notification processing workflow ended |
| **cancelled_at / skipped_at / expired_at** | When the system recorded the respective terminal state |

Do not conflate three concepts:

1. **scheduled_at**: when sending is desired.
2. **next_attempt_at**: when the scheduler wakes to try, which can shift due to backoff or quotas.
3. **expires_at**: after which no new SMTP attempt should start.

Example:

~~~text
created_at       08:00
scheduled_at     09:00
not_before_at    09:00
next_attempt_at  09:00
expires_at       09:15

09:00  provider temporary error
09:01  retry 1 fails
09:05  next_attempt_at updated to 09:10
09:10  retry if still valid
09:15  do not start a new SMTP attempt
~~~

An email can be **due but not yet expired**, or **not yet due but already cancelled**. Statuses should reflect the true cause rather than lumping everything under FAILED.

## 3. How Do Expired Emails Differ From Skipped Emails?

Use clear status names and reasons:

| Outcome | Meaning | Example |
|---|---|---|
| **EXPIRED** | No longer permitted to send because the deadline passed | 5-minute OTP expired, meeting reminder after meeting ended |
| **SKIPPED** | System intentionally chose not to send per business rule/policy | Order already paid, invalid recipient |
| **CANCELLED** | Authorized actor cancelled the send intent | User cancelled campaign before send time |
| **SUPPRESSED** | Recipient/email blocked by sending policy | Recipient unsubscribed, on valid suppression list |
| **FAILED** | Attempted processing/sending and hit a policy-defined failure | Permanent MIME prep error, definitive SMTP 5xx |
| **RETRY_WAIT** | Not yet sent, still has a valid retry window | SMTP 451, temporary provider throttling |
| **UNKNOWN** | Unclear whether SMTP accepted the message | Lost final SMTP reply after DATA |
| **SUBMITTED** | Provider/SMTP hop accepted submission | `send(...)` completed per transport contract |

An application need not use all of these exact names, but it must keep their **semantics distinct**.

For example, an email skipped because the order was already paid is not an SMTP failure. Recording it as FAILED inflates transport-error dashboards and risks improper retries.

Likewise, an email already SUBMITTED before noticing the deadline passed cannot simply be flipped to **EXPIRED_NOT_SENT**, because the message may have already left the system. Distinguish **submission start**, **SMTP outcome**, and **business deadline**.

## 4. Choosing a Policy: Send Late or Drop?

Not every delayed email should be dropped. Before deploying a scheduler, define a **late-delivery policy** for each notification category.

| Email category | If 2 minutes late | If 2 hours late | Policy direction |
|---|---|---|---|
| OTP or magic link | May already be useless depending on TTL | Do not send | Hard deadline |
| Critical security alert | Likely still needs sending | Likely still useful, but must state accurate timing | Verify state and content |
| 15-min pre-meeting reminder | May send if before meeting start | Do not send after meeting passed | Bind deadline to event |
| Payment reminder | Must check whether already paid | Send only if balance is still due | Business revalidation |
| Order confirmation | Usually still valuable | Can send late, but avoid wording like "just placed" | Bounded late send |
| Valid invoice | Can send | Likely must send even late, per obligations | Prioritize delivery with SLA |
| Marketing promotion | Acceptable | Drop if promotion expired | Campaign window |
| Daily digest | Acceptable within grace window | Roll to next period or drop | Period-based policy |

**All figures in the table are business examples**, not Spring Framework Mail defaults.

A system can define:

~~~java
public enum LateSendPolicy {
    DROP_AFTER_DEADLINE,
    SEND_WITHIN_GRACE_PERIOD,
    REVALIDATE_BEFORE_SEND,
    ROLL_TO_NEXT_WINDOW,
    SEND_WHEN_AVAILABLE
}
~~~

With **SEND_WHEN_AVAILABLE**, you still need retention limits, retry budgets, and business preconditions. Never use this policy to keep an email with an expired link/token alive indefinitely.

## 5. Questions to Resolve When Designing Policies

Before writing code, answer:

1. Which emails become **meaningless** after a certain point?
2. Does expiration come from **token TTL**, an event, a campaign, user preferences, or a contract?
3. Is there a **grace period** after `scheduled_at`?
4. Should an email that is due but lacks quota **wait or be skipped**?
5. Before sending, must we re-read order status, subscription, or consent?
6. Who is authorized to cancel or reschedule?
7. Once claimed by a worker but before SMTP submit, how far can cancellation reach?
8. When **UNKNOWN** occurs after DATA, how are state and retries handled?
9. If a job expires while a worker is actively sending, how is the outcome interpreted?
10. Which **final reasons** should users and operators see?

Document the answers as a **policy per notification type** rather than letting workers guess from timestamps or Subjects.

## 6. State Machine for Scheduled Emails

An illustrative state machine:

~~~text
                 +----------------+
                 |   SCHEDULED    |
                 +----------------+
                       |
               next_attempt_at reached
                       |
                       v
                +--------------+
                |    READY     |
                +--------------+
                  |    |     |
     expired -----+    |     +----- policy invalid
                  |    |                 |
                  v    v                 v
              EXPIRED CLAIMED          SKIPPED
                        |
                        +---- cancel before SMTP -> CANCELLED
                        |
                        v
                   SENDING
                     |
        +------------+-------------+-------------+
        |            |             |             |
        v            v             v             v
    SUBMITTED     RETRY_WAIT      FAILED        UNKNOWN
                      |
                      +--> READY if not expired
                      |
                      +--> EXPIRED if retry window ended
~~~

These states are illustrative. In a production database, **SCHEDULED/READY** may be combined into **PENDING** with `next_attempt_at`, or **PROCESSING** may be used alongside a lease.

Crucially, **terminal states** (`SUBMITTED`, `EXPIRED`, `SKIPPED`, `CANCELLED`, `FAILED` per contract) must have strict update rules; never let a scheduler revert a terminal state back to `PENDING` merely because cron fired.

**UNKNOWN must never default to FAILED or EXPIRED.** It requires reconciliation because the server may have received the email.

## 7. Deadlines Govern Attempt Start, Not Email Recall

Suppose:

~~~text
expires_at = 10:00:00

09:59:59.700  Worker starts SMTP submission
10:00:02.400  SMTP server returns 250 Accepted
~~~

If policy states "do not **start** an attempt after `expires_at`", an attempt started at 09:59:59.700 may be valid. Do not turn a `SUBMITTED` outcome into `EXPIRED` merely because `accepted_at` is after 10:00.

Conversely:

~~~text
10:00:01.000  Worker starts a new SMTP attempt
~~~

This send violated the policy deadline if `expires_at` was 10:00:00.

Specify **at which points the deadline is checked**:

- Before claiming?
- Before building the `MimeMessage`?
- Immediately before calling `JavaMailSender.send(...)`?
- Immediately before transmitting SMTP DATA?

A typical application can check **before claiming and right before sending**, but cannot guarantee a message will not leave the system past the deadline if sending is already in flight—unless infrastructure/providers offer native schedule-and-cancel support.

## 8. Do Not Equate Business Deadlines With SMTP Timeouts

Two distinct parameters:

~~~text
Business deadline:
  expires_at = timestamp after which sending must no longer start

SMTP transport timeout:
  mail.smtp.connectiontimeout = TCP connect wait limit
  mail.smtp.timeout           = socket read limit
  mail.smtp.writetimeout      = socket write limit
~~~

SMTP timeouts prevent threads from hanging indefinitely, but **do not automatically cancel an expired notification**. Conversely, `expires_at` does not interrupt an open socket or bound DNS/TCP/TLS automatically.

If an email has only 2 seconds of validity left, whether to allow starting a send whose total socket timeouts exceed 2 seconds should follow policy. One strategy is enforcing a **minimum remaining validity**:

~~~text
remaining = expires_at - now

if remaining < minimumSendBudget:
    EXPIRE_OR_DEFER_BY_POLICY
else:
    ALLOW_ATTEMPT
~~~

**`minimumSendBudget`** is an application-chosen safety margin, not a guarantee that SMTP completes within that window. If an email or token has expired by the time the recipient opens it, message content should explain how to request a fresh code or action.

## 9. Root Causes of Delayed or Skipped Emails

Classify operational causes clearly:

| Category | Example | Handling |
|---|---|---|
| **SCHEDULER_DELAY** | Scheduler stopped, wrong cron | Restore scheduler and reconcile queue |
| **CAPACITY_BACKLOG** | Workers lack threads/slots | Scale/balance load, monitor queue age |
| **PROVIDER_THROTTLE** | ESP caps recipients/s | Backoff, defer per quota |
| **PROVIDER_OUTAGE** | DNS/TCP/TLS/SMTP failures | Bounded retries with deadline |
| **BUSINESS_OBSOLETE** | Order already paid, event ended | `SKIPPED` |
| **CONSENT_REVOKED** | Recipient unsubscribed | `SUPPRESSED`/`SKIPPED` per policy |
| **REQUEST_CANCELLED** | User or admin cancelled | `CANCELLED` |
| **INVALID_RECIPIENT** | Address failed validation | `SKIPPED` or `FAILED_VALIDATION` |
| **DUPLICATE_INTENT** | Event redelivered | Deduplicate, create no new job |
| **MISCONFIGURED_WINDOW** | `scheduled_at` past `expires_at` | Reject or mark invalid |
| **LEASE_STUCK** | Worker died after claim | Reclaim via lease and evaluate deadline |
| **UNKNOWN_SUBMISSION** | Lost reply after DATA | Reconcile, do not assume unsent |

Never dump everything into `skip_reason = OTHER`. A bounded set of reason codes helps dashboards, customer support, and runbooks separate configuration bugs from intentional business decisions.

## 10. A Skipped Email Can Be the Exact Right Result

A high `SKIPPED` rate does not automatically mean the email system is broken.

Example:

~~~text
08:00  Order ORD-100 created
08:05  Payment reminder scheduled for 09:00
08:30  Customer pays successfully
09:00  Worker sees order is already paid
09:00  Notification moves to SKIPPED/BUSINESS_OBSOLETE
~~~

Here **not sending the email** is the correct behavior. Record:

- Which notification was skipped.
- Which policy applied.
- Reason **`ORDER_ALREADY_PAID`** or equivalent code.
- Decision timestamp.
- Zero SMTP attempts created when skipped prior to sending.

Conversely, an email skipped because **workers lacked capacity until its deadline passed** is a service-quality signal to monitor. Both share status `EXPIRED`, yet reason **`CAPACITY_BACKLOG`** differs fundamentally from **`USER_CANCELLED`** or **`TOKEN_TTL_ENDED`**.

## 11. Scheduling Architecture With a Transactional Outbox

A practical architecture looks like:

~~~text
Business transaction
      |
      +-- Save business state
      +-- Insert email intent with schedule/deadline
      |
      v
Commit database transaction
      |
      v
Scheduled outbox storage
      |
      +-- Expiration scanner -> mark EXPIRED
      |
      +-- Cancellation/business changes -> mark SKIPPED/CANCELLED
      |
      +-- Due-job scheduler -> claim eligible jobs
                                     |
                                     v
                             Revalidate policy
                                     |
                                     v
                          SMTP attempt via JavaMailSender
                                     |
                +--------------------+-------------------+
                |                    |                   |
                v                    v                   v
            SUBMITTED            RETRY_WAIT            UNKNOWN
                |
                v
           Provider feedback
~~~

Separating the **business transaction** from **SMTP submission** avoids holding a database transaction open across DNS, TCP, TLS, authentication, and DATA.

When workers restart, outbox data survives to:

- Pick up unprocessed due jobs.
- Expire jobs past their deadline.
- Retry with backoff if still valid.
- Reconcile jobs stuck in `PROCESSING`.
- Explain why an email was not sent.

**`@Scheduled`** only triggers work on a timer; it does not provide an outbox, durability, transactions, idempotency, or skip history on its own.

## 12. Outbox Table Design With Deadlines and Reason Codes

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE email_outbox (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(120) NOT NULL,
    notification_type   VARCHAR(80) NOT NULL,
    business_key        VARCHAR(240) NOT NULL,
    recipient_ref       VARCHAR(240) NOT NULL,
    payload_ref         TEXT NOT NULL,

    status              VARCHAR(40) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    next_attempt_at     TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ,

    attempt_count       INTEGER NOT NULL DEFAULT 0,
    claim_token         UUID,
    claimed_at          TIMESTAMPTZ,
    lease_until         TIMESTAMPTZ,

    submitted_at        TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    outcome_reason      VARCHAR(100),
    last_error_category VARCHAR(100),
    version             BIGINT NOT NULL DEFAULT 0,

    CHECK (attempt_count >= 0),
    CHECK (
        expires_at IS NULL
        OR scheduled_at < expires_at
    )
);

CREATE UNIQUE INDEX uq_email_intent
ON email_outbox (
    tenant_id,
    notification_type,
    business_key,
    recipient_ref
);

CREATE INDEX ix_email_outbox_due
ON email_outbox (next_attempt_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX ix_email_outbox_expiration
ON email_outbox (expires_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

This schema is an **application-defined example**, not a default Spring Mail table.

Decisions to clarify:

- **Nullable `expires_at`** means the job has no business expiry, though retention/retry policies must still exist.
- **`scheduled_at < expires_at`** is a strict illustrative rule. If your product allows deadlines equal to `scheduled_at`, define those semantics explicitly rather than silently relaxing constraints.
- **`recipient_ref`** can point to a PII-protected recipient record instead of storing raw emails in the queue.
- The unique intent key must match the idempotency unit. Two emails for different periods or campaigns may need distinct keys.
- **`claim_token`** and **`lease_until`** govern processing ownership across multiple workers.
- **`outcome_reason`** must be normalized and never contain exception text or personal data.

With **PostgreSQL**, indexes on status and timestamps enable fast scans over unfinished jobs. Tune indexes to actual data volume, partitioning, and application queries.

## 13. Enforcing Time and State Invariants

Before writing to the outbox, check:

~~~text
scheduled_at >= created_at?       (if policy forbids past schedules)
expires_at > scheduled_at?        (if deadline is present)
next_attempt_at >= scheduled_at?  (except cases needing immediate retry)
tenant and recipient authorized?
notification still relevant?
~~~

Not every notification requires **`scheduled_at >= created_at`**. Late-synced legacy data may carry an original past schedule with policy allowing catch-up. What matters is **defining how to handle it** instead of skipping checks.

Key invariants:

1. A **`SUBMITTED`** job is never transitioned to `EXPIRED` by a scanner.
2. A **`CANCELLED`/`SKIPPED`** job is never re-executed by workers.
3. An expired job is never claimed for a **new SMTP attempt**.
4. A job with an **`UNKNOWN` outcome** is never assumed definitely unsent.
5. Only the worker owning the active claim token/lease may update a job's outcome.
6. A replayed intent never creates a second job with the same business key.
7. Modifying deadlines checks policy version and authorization.
8. If a notification targets multiple recipients, per-recipient states/deadlines may be needed rather than a single summary row.

**Invariants must be enforced at the database/state-transition boundary**, not merely by an `if` check before calling a service. Between reading and writing, other threads or workers can mutate state.

## 14. Selecting Due Jobs: Due Does Not Mean Send Immediately

A job is eligible to start processing when:

~~~text
status in (PENDING, RETRY_WAIT)
AND next_attempt_at <= now
AND (expires_at IS NULL OR expires_at > now)
AND tenant/campaign/recipient policy allows
AND capacity available
~~~

Example read-only query to inspect due jobs:

~~~sql
SELECT
    id,
    tenant_id,
    notification_type,
    scheduled_at,
    next_attempt_at,
    expires_at
FROM email_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= statement_timestamp()
  AND (
      expires_at IS NULL
      OR expires_at > statement_timestamp()
  )
ORDER BY next_attempt_at, id
LIMIT 100;
~~~

**Never use this standalone `SELECT` as a claim mechanism in multi-worker environments**, as two workers can read the same row and both send.

Beyond SQL time predicates, workers still verify dynamic policies: an order may have been paid, a user unsubscribed, or a tenant disabled right before the job's turn.

## 15. Expiring Waiting Jobs Atomically

A scanner can transition expired unsent jobs to `EXPIRED`:

~~~sql
UPDATE email_outbox
SET
    status = 'EXPIRED',
    outcome_reason = 'DEADLINE_REACHED',
    finished_at = statement_timestamp(),
    version = version + 1
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND expires_at IS NOT NULL
  AND expires_at <= statement_timestamp();
~~~

The **`status IN ('PENDING', 'RETRY_WAIT')`** predicate is crucial:

- Never modifies `SUBMITTED` jobs.
- Never overwrites `CANCELLED` or `SKIPPED` jobs.
- Never forcibly marks `SENDING` jobs `EXPIRED`, because SMTP may be in flight.
- Never marks `UNKNOWN` as `EXPIRED` before reconciliation.

At large row counts, never update millions of rows in one long transaction. Batch it instead:

~~~sql
WITH expired_batch AS (
    SELECT id
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND expires_at IS NOT NULL
      AND expires_at <= statement_timestamp()
    ORDER BY expires_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 500
)
UPDATE email_outbox AS o
SET
    status = 'EXPIRED',
    outcome_reason = 'DEADLINE_REACHED',
    finished_at = statement_timestamp(),
    version = o.version + 1
FROM expired_batch AS b
WHERE o.id = b.id
RETURNING o.id, o.tenant_id, o.notification_type;
~~~

**`FOR UPDATE SKIP LOCKED`** avoids blocking on rows locked by other transactions, ideal for competing workers/scanners. Note that skipped rows may remain and be picked up on the next pass.

This is a PostgreSQL example. Do not assume **`RETURNING / SKIP LOCKED`** syntax is identical across all databases.

## 16. Concurrent Job Claiming: Stopping Two Workers From Sending the Same Row

With multiple workers:

~~~text
Worker A: sees N100 is due
Worker B: sees N100 is due
Worker A: sends SMTP
Worker B: sends SMTP
~~~

To prevent two workers from claiming one row, run a short transaction:

~~~sql
WITH due_batch AS (
    SELECT id
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= statement_timestamp()
      AND (
          expires_at IS NULL
          OR expires_at > statement_timestamp()
      )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE email_outbox AS o
SET
    status = 'CLAIMED',
    claim_token = gen_random_uuid(),
    claimed_at = statement_timestamp(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    version = o.version + 1
FROM due_batch AS b
WHERE o.id = b.id
RETURNING
    o.id,
    o.tenant_id,
    o.claim_token,
    o.expires_at,
    o.next_attempt_at;
~~~

Once committed, the worker holds a **unique claim token** per row. Subsequent updates check the token to prevent an old worker from overwriting a new worker's results.

**Claimed does not mean sent.** After claiming, the worker checks business state, deadline, recipient permission, cancellation, and provider capacity before opening an SMTP session.

**Note:** **`gen_random_uuid()`** availability depends on your PostgreSQL version/extensions; an application-generated UUID works if absent. The 2-minute lease is illustrative only, not a universal default.

## 17. When Scanner and Worker Contend for the Same Job

Suppose N100 has:

~~~text
status = PENDING
expires_at = 10:00
~~~

At 10:00, two actions may race:

~~~text
ExpirationScanner       SendingWorker
      |                        |
      |  UPDATE EXPIRED        |  CLAIM due job
      |                        |
      +------------+-----------+
                   |
             Database row lock
~~~

With conditional updates:

- If the scanner locks/updates first, the worker can no longer claim N100 as `PENDING`.
- If the worker claims before the deadline, N100 becomes `CLAIMED`. The scanner must not blindly mark it `EXPIRED` as if unowned.
- After claiming, the worker still checks the deadline right before sending. If expired, transition conditionally to `EXPIRED` using the claim token.

Never rely on a single timestamp check when reading the object: an admin, user, or scanner may alter state while the worker is preparing.

### Never hold a database transaction during SMTP sends

Claims must use short transactions that commit before network I/O begins. Calling **`JavaMailSender.send(...)`** inside a transaction holding row locks for seconds or minutes spikes lock contention, and sent emails never roll back if the transaction rolls back.

## 18. Re-Checking Deadlines Right Before Sending

Between claiming and starting SMTP, several things can happen:

- Template rendering takes multiple seconds.
- Attachments must be fetched from object storage.
- The worker waits for a semaphore or provider rate token.
- The user cancels the request.
- The campaign is paused.
- The deadline arrives.

Therefore, enforce a **final admission gate**:

~~~text
CLAIMED
   |
   +-- expires_at <= now --> EXPIRED
   +-- cancellation --> CANCELLED
   +-- business condition false --> SKIPPED
   +-- no capacity --> DEFER (if not expired)
   |
   v
Transition to SENDING with claim_token
   |
   v
JavaMailSender.send(...)
~~~

Example conditional update:

~~~sql
UPDATE email_outbox
SET
    status = 'SENDING',
    version = version + 1
WHERE id = :id
  AND status = 'CLAIMED'
  AND claim_token = :claimToken
  AND (
      expires_at IS NULL
      OR expires_at > statement_timestamp()
  )
RETURNING id;
~~~

If no row returns, the worker must not send yet; re-read state to check for **expiration, cancellation, lost claim, or conflict**.

**Explicit boundary:** there is always a tiny gap between the DB transition and the network call. A cancellation arriving right after `SENDING` may not stop the email. If strict post-cancel blocking is required, use provider/transport controls where supported and accept SMTP's limits. Application guards shrink races without promising unconditional recall.

## 19. Java Clock Makes Deadline Logic Predictable

Avoid scattering **`Instant.now()`** across services; it makes boundary tests brittle.

In Spring, inject **`Clock`**:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationTimeConfiguration {

    @Bean
    public Clock notificationClock() {
        return Clock.systemUTC();
    }
}
~~~

A policy service:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class SendDeadlinePolicy {

    private final Clock clock;

    public SendDeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean mayStartAttempt(Instant expiresAt) {
        return expiresAt == null
                || clock.instant().isBefore(expiresAt);
    }

    public Optional<java.time.Duration> remaining(
            Instant expiresAt
    ) {
        if (expiresAt == null) {
            return Optional.empty();
        }
        return Optional.of(
                java.time.Duration.between(
                        clock.instant(), expiresAt
                )
        );
    }
}
~~~

**`Optional.empty()`** expresses no deadline cleanly instead of a fake huge duration. Negative durations mean the deadline passed. At exact boundary **`now == expiresAt`**, **`mayStartAttempt`** returns false.

**Important:** Java code uses an injected `Clock`, while the SQL above uses the database's **`statement_timestamp()`**. Those two clocks can drift. For critical state transitions, pick one authoritative clock source (usually DB time for atomic updates) and monitor skew—never assume JVM checks and DB checks happen at the exact same `Instant`.

## 20. @Scheduled Sweeps for Expiration and Due Work

Spring Scheduling can trigger the scanner:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class NotificationSchedulingConfiguration {
}
~~~

A scheduled component:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ExpirationSweepJob {

    private final ExpirationService expirationService;

    public ExpirationSweepJob(
            ExpirationService expirationService
    ) {
        this.expirationService = expirationService;
    }

    @Scheduled(fixedDelay = 30000)
    public void sweepExpired() {
        expirationService.expireEligibleBatches();
    }
}
~~~

**`ExpirationService`** is an application service running conditional updates, batching, and recording events/audits. The 30-second delay is illustrative only.

A scanner running every 30 seconds **does not guarantee jobs are marked expired down to the millisecond**; scheduler lag, host load, or outages delay sweeps. That is why **send workers must still block expired jobs at the admission gate**. The scanner handles state cleanup and visibility, not sole enforcement.

### Schedulers running across multiple instances

If the same `@Scheduled` method runs on 5 pods, it can sweep 5 times. Conditional updates prevent overwrites but still add database load.

Options:

- Leader election/distributed lock with an appropriate lease.
- Database batching with **`SKIP LOCKED`**.
- A single dedicated scheduler service with failover.
- Queue partitioning/sharding by tenant or time bucket.

Never rely on a **`static boolean`** or single-JVM memory lock to coordinate an entire cluster.

## 21. Timezones and Daylight Saving Time (DST)

Users may request sending at:

~~~text
"09:00 AM my time, November 20"
~~~

The application should separate:

- User-supplied **`LocalDateTime`**.
- User's IANA **`ZoneId`**, e.g., **`Asia/Ho_Chi_Minh`**.
- Normalized **`Instant`** stored and compared by the scheduler.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDateTime local =
        LocalDateTime.of(2026, 11, 20, 9, 0);

ZoneId zone =
        ZoneId.of("Asia/Ho_Chi_Minh");

Instant scheduledAt =
        local.atZone(zone).toInstant();
~~~

**`Instant`** fits deadline comparisons and `TIMESTAMPTZ`/UTC storage. **`ZoneId`** must still be kept if users want recurring local-time schedules.

In DST-observing timezones, a local time can **fail to exist or happen twice**. For local-time schedules, define gap/overlap rules—never assume **`local.atZone(zone)`** matches expectations without an explicit policy.

### Event-anchored deadlines

For a meeting starting at 10:00 in `ZoneId`, a 15-minute reminder might have:

~~~text
scheduled_at = meeting_start_instant - 15 minutes
expires_at   = meeting_start_instant
~~~

If the meeting is rescheduled, update both `scheduled_at` and `expires_at`, or cancel the old intent and create a new one per idempotency policy. Never update only the Subject while leaving a stale deadline.

## 22. Spring JDBC Example for Batched Expiration Sweeps

Using **`NamedParameterJdbcTemplate`**, implement a repository sweeping past-due `PENDING`/`RETRY_WAIT` jobs:

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class EmailExpirationRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public EmailExpirationRepository(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<UUID> expireBatch(int batchSize) {
        if (batchSize < 1 || batchSize > 1000) {
            throw new IllegalArgumentException(
                    "batchSize must be between 1 and 1000"
            );
        }

        String sql = """
            WITH due AS (
                SELECT id
                FROM email_outbox
                WHERE status IN ('PENDING', 'RETRY_WAIT')
                  AND expires_at IS NOT NULL
                  AND expires_at <= statement_timestamp()
                ORDER BY expires_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE email_outbox AS o
            SET status = 'EXPIRED',
                outcome_reason = 'DEADLINE_REACHED',
                finished_at = statement_timestamp(),
                version = o.version + 1
            FROM due
            WHERE o.id = due.id
            RETURNING o.id
            """;

        return jdbc.query(
                sql,
                Map.of("limit", batchSize),
                (rs, rowNum) -> (UUID) rs.getObject("id")
        );
    }
}
~~~

This snippet uses **Java text blocks** and **PostgreSQL**. It transitions only unclaimed/unsent rows and leaves `SENDING`/`UNKNOWN` untouched.

For auditing, an implementation can write transitioned IDs to an **outcome event table** in the same transaction. Do not send a second notification email to the user merely because a job became `EXPIRED` unless explicitly required by policy; failure-notice emails may need deadlines of their own.

### Never sweep the entire backlog in one long transaction

A service can invoke **`expireBatch(500)`** repeatedly, each via a separate transactional public repository method:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ExpirationService {

    private final EmailExpirationRepository repository;

    public ExpirationService(
            EmailExpirationRepository repository
    ) {
        this.repository = repository;
    }

    public void expireEligibleBatches() {
        for (int i = 0; i < 20; i++) {
            int expired = repository.expireBatch(500).size();
            if (expired == 0) {
                break;
            }
        }
    }
}
~~~

This way one scheduler pass can process up to 10,000 rows in small batches. The 500/20 bounds are illustrative; measure DB load and actual runtime limits.

**Spring transaction note:** placing **`@Transactional`** on a method and calling **`this.method()`** within the same object bypasses Spring's transaction proxy under default AOP settings. Above, the service invokes a public method on a separate repository bean.

## 23. SKIPPED Due to Business State: Must Check Close to Send Time

Payment reminder example:

~~~text
Order ORD-200 created at 08:00
Reminder scheduled for 09:00
Customer pays at 08:59:58
Worker picks up job at 09:00:00
~~~

If the payload stored a snapshot:

~~~json
{
  "orderId": "ORD-200",
  "paymentStatus": "UNPAID"
}
~~~

that snapshot is now stale. **Payload snapshots** remain helpful for stable content rendering, yet send eligibility must verify **current business state**.

A policy checker:

~~~java
public interface NotificationEligibilityPolicy {
    EligibilityDecision evaluate(
            String tenantId,
            String notificationType,
            String businessKey
    );
}

public record EligibilityDecision(
        boolean allowed,
        String reasonCode
) {
    public static EligibilityDecision allow() {
        return new EligibilityDecision(true, "ELIGIBLE");
    }

    public static EligibilityDecision skip(String reason) {
        return new EligibilityDecision(false, reason);
    }
}
~~~

Example **`PAYMENT_REMINDER`**:

~~~text
if order does not exist:
    SKIP: ORDER_NOT_FOUND
else if order paid:
    SKIP: ORDER_ALREADY_PAID
else if order cancelled:
    SKIP: ORDER_CANCELLED
else:
    ALLOW
~~~

Watch **time-of-check/time-of-use**: an order can be paid right after the worker checks and right before SMTP runs. When strict prevention is required, coordinate transactions/conditional outbox updates with order updates. For state owned by external services without shared transactions, define clear guarantees and race handling.

## 24. Conditional SKIPPED Updates Without Overwriting Other States

Suppose a worker claimed a notification and policy determines it no longer needs sending. It may update status only while still owning the job:

~~~sql
UPDATE email_outbox
SET
    status = 'SKIPPED',
    outcome_reason = :reason,
    finished_at = statement_timestamp(),
    claim_token = NULL,
    lease_until = NULL,
    version = version + 1
WHERE id = :id
  AND status = 'CLAIMED'
  AND claim_token = :claimToken
RETURNING id;
~~~

If zero rows return:

- The worker may have lost its lease/ownership.
- The user cancelled the notification.
- Another worker already finished.
- Another state transition occurred.

Never retry the update without status/token predicates. Re-read state and follow the state machine.

### Reason codes should be an allowlist

Example:

~~~java
public enum SkipReason {
    ORDER_ALREADY_PAID,
    ORDER_CANCELLED,
    EVENT_ALREADY_FINISHED,
    RECIPIENT_SUPPRESSED,
    USER_PREFERENCE_CHANGED,
    CAMPAIGN_CANCELLED,
    DUPLICATE_INTENT,
    INVALID_RECIPIENT,
    POLICY_NOT_ELIGIBLE
}
~~~

Never store raw error messages, Subjects, recipient emails, or sensitive data in **`outcome_reason`**. Detailed evidence, if needed, belongs in an access-controlled audit store with retention policies.

## 25. Grace Periods and Allowed Send Windows

An email may target a specific time while still permitting late delivery within a bounded window.

Example:

~~~text
scheduled_at = 09:00
grace_period = 15 minutes
expires_at   = 09:15
~~~

A policy can compute:

~~~java
import java.time.Duration;
import java.time.Instant;

public Instant deadlineFromSchedule(
        Instant scheduledAt,
        Duration grace
) {
    if (grace.isNegative() || grace.isZero()) {
        throw new IllegalArgumentException(
                "Grace period must be positive"
        );
    }
    return scheduledAt.plus(grace);
}
~~~

Do not apply one grace period to every category:

- OTP expiry depends on token TTL, often just a few minutes.
- Meeting reminders should expire by event start.
- Daily digests may drop once the next period generates a fresh digest.
- Invoices may have SLA targets yet must not be discarded if legal obligations remain.

**A grace period does not automatically extend a token's TTL.** An email containing a link that expired at 09:05 does not become useful just because the scheduler allows sending until 09:15.

## 26. Retries Must Respect Deadlines

Suppose SMTP fails temporarily at 09:03 and the worker wants to retry in 10 minutes:

~~~text
expires_at = 09:10
now = 09:03
backoff = 10 minutes
next_attempt_at = 09:13
~~~

Do not schedule a retry at 09:13 only for a worker to discover later it expired, when policy lets you decide right now:

~~~java
import java.time.Duration;
import java.time.Instant;

public boolean canRetryBeforeDeadline(
        Instant now,
        Duration backoff,
        Instant expiresAt
) {
    Instant next = now.plus(backoff);
    return expiresAt == null || next.isBefore(expiresAt);
}
~~~

In the example:

~~~text
09:03 + 10 minutes = 09:13
09:13 >= 09:10
=> Do not schedule a new SMTP attempt past deadline.
~~~

Transition to `EXPIRED` with reason **`RETRY_WINDOW_EXHAUSTED`**, or a terminal state like **`FAILED_DEADLINE`** per policy.

### Do not squeeze retries by shrinking backoff to 0

Trying to cram one last retry into remaining seconds by dropping backoff to milliseconds triggers **retry storms** during provider outages. Combine:

- Max attempts.
- Minimum backoff.
- Jitter.
- Provider `Retry-After` when available.
- Per-tenant and global retry budgets.
- Deadlines and minimum remaining validity.

If insufficient time remains to retry safely, **stopping attempts** can be the right decision.

## 27. Difference Between Retryable Errors and Expiration

Suppose:

~~~text
N100: SMTP 451 at 09:00, expires_at 10:00
N101: SMTP 451 at 09:59, expires_at 10:00
~~~

A 451 may be **temporary**, yet N101 may lack enough time remaining for backoff.

Thus the decision:

~~~text
shouldRetry =
    errorIsTransient
    AND attemptCount < maxAttempts
    AND deadlineAllowsAnotherAttempt
    AND tenantAndProviderPolicyAllows
~~~

Outcomes should distinguish:

| Condition | Status |
|---|---|
| Temporary failure, time remaining | `RETRY_WAIT` |
| Temporary failure, past deadline | `EXPIRED`/`RETRY_WINDOW_EXHAUSTED` |
| Non-recoverable failure per policy | `FAILED` |
| Unclear if provider accepted | `UNKNOWN` |
| Job cancelled while awaiting retry | `CANCELLED` |

Lumping everything into `FAILED` hides why emails failed to arrive: provider rejection, ambiguous timeouts, or expired business deadlines.

## 28. Emails Cancelled by Users or Administrators

**Cancellation** differs from **expiration**:

- Expiration happens because the validity window elapsed.
- Cancellation is an authorized action stopping send intent.

A cancellation API should:

1. Authenticate the actor and tenant.
2. Verify the actor is authorized to cancel the notification/campaign.
3. Determine the current state.
4. Execute a conditional transition.
5. Audit actor, reason, and timestamp.
6. Return semantically accurate outcomes if the email is already `SENDING` or `SUBMITTED`.

Example cancelling an unclaimed job:

~~~sql
UPDATE email_outbox
SET
    status = 'CANCELLED',
    outcome_reason = 'USER_CANCELLED',
    finished_at = statement_timestamp(),
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND status IN ('PENDING', 'RETRY_WAIT')
RETURNING id;
~~~

If status is `CLAIMED`, a **`cancellation_requested_at`** timestamp or flag lets the worker notice before the final gate. Once `SENDING` or `SUBMITTED`, however, successful cancellation cannot be promised.

**Never report "email recalled" merely because the database updated to `CANCELLED`** if SMTP DATA may have already been accepted.

## 29. Races Between Cancellation, Expiry, and SMTP Submission

A timeline:

~~~text
09:59:59.800  Worker checks deadline and claims token
09:59:59.900  Worker transitions to SENDING
10:00:00.000  Expires
10:00:00.050  User requests CANCEL
10:00:00.100  SMTP DATA transmitting
~~~

Three rules:

1. **Never blindly flip `SUBMITTED` or `SENDING` to `CANCELLED`.** The system must know whether cancellation arrived before or after sending could be stopped.
2. **Never return one generic "cancel success" across all states.** Return `CANCELLED_BEFORE_SUBMISSION`, `CANCEL_REQUESTED_TOO_LATE`, or `ALREADY_SUBMITTED` per API contract.
3. **Never use a deadline to deny a submission that actually happened.** If SMTP accepted, preserve acceptance evidence and annotate e.g. `SENT_AFTER_REQUESTED_CANCELLATION` if a race occurred.

If a provider exposes a **scheduled send + cancel API**, you can cancel on the provider side. Still understand its limits and return states; calling cancel cannot recall mail already relayed to a receiving mail server.

## 30. Skipping Emails When the Recipient Is No Longer Permitted

Some conditions live not in the schedule but in **permission to email the recipient**:

- User withdrew consent or unsubscribed.
- Address landed on a suppression list after a hard bounce or spam complaint.
- Account was locked or no longer exists.
- User disabled optional notification categories.
- Recipient was removed from the tenant or lost content access.
- A tenant/account was disabled by policy.

Example:

~~~text
08:00  User subscribes to newsletter
08:10  Marketing email scheduled for 15:00
14:45  User unsubscribes
15:00  Scheduler runs
       -> Skips newsletter
       -> SKIPPED/RECIPIENT_UNSUBSCRIBED
~~~

**Never treat a consent snapshot from job creation time** as final permission to send marketing mail hours or days later.

Re-check consent and suppressions right before sending, while applying distinct policies for mandatory/critical emails permitted by law and product rules. Never assume "transactional" exempts an email from every privacy or anti-spam rule.

### Multiple recipients in one message

If a `MimeMessage` contains 10 To/Cc/Bcc recipients and 2 are suppressed before send time:

- Do not send to the 2 blocked recipients.
- Refresh the permitted recipient list at send time.
- Evaluate whether modifying To/Cc/Bcc leaks recipient lists.
- Count quotas/metrics by eligible recipients per contract.
- Store separate state per **notification-recipient** when accurate delivery feedback and retries are required.

For personalized or sensitive flows, **one notification per recipient** usually makes isolating skips, expirations, and outcomes far simpler.

## 31. Changing Business State: Skip or Send a Newer Version?

Not every business change means skipping. You may need to change the **content or email type**.

Order example:

~~~text
08:00  Order status = PREPARING
08:05  Schedule "Order is being prepared" for 09:00
08:50  Order status = SHIPPED
09:00  Worker reaches job
~~~

Sending "Order is being prepared" now would be wrong. Options:

1. **SKIP the obsolete notification** and let the `SHIPPED` event create a new email.
2. **REPLACE the notification** via versioning rules, cancelling the old job and creating the new one.
3. **RENDER CURRENT STATE** if the email is designed to reflect live state and semantics permit it.

Avoid silently mutating an already-audited notification's content into something completely different under the same business event ID, making reconciliation difficult.

If choosing **replace**:

~~~text
Old intent N100 -> SKIPPED/SUPERSEDED
New intent N101 -> PENDING with new schedule/content
~~~

Include **`supersedes_id`** or equivalent metadata linking the two notifications. Never send both N100 and N101 if business rules make them mutually exclusive.

## 32. Recurring Schedules: Handling Missed Periods

A cron job may run hourly or daily:

~~~text
Every day at 08:00 -> send daily digest
~~~

If the service is down from 07:50 to 11:30, on restart decide:

- **SKIP_MISSED**: skip the missed 08:00 slot and wait for tomorrow.
- **CATCH_UP_ONCE**: catch up once if still valuable.
- **CATCH_UP_ALL**: run every missed slot, e.g., when archived reports are required.
- **COALESCE**: merge missed periods into one summary.
- **ROLL_FORWARD**: move unsent jobs into the next valid window.

These are **misfire policies defined by the application or scheduler framework**, not uniform default behavior of Spring **`@Scheduled`**.

### `@Scheduled` is not a durable record of every trigger

Suppose:

~~~java
@Scheduled(cron = "0 0 8 * * *", zone = "Asia/Ho_Chi_Minh")
public void createDailyDigest() {
    // create scheduled intent
}
~~~

In basic configurations, **`@Scheduled`** fires while the application is alive; it does not automatically record every scheduled cron tick during downtime.

If your product requires catching up missed periods, build a **schedule ledger** or use a durable scheduler with explicit misfire policies.

Example period key:

~~~text
(tenant_id, notification_kind, recipient_id, period_start)
~~~

That way a restart never creates two digests for the same day if cron triggers or retries overlap.

## 33. Skipping a Missed Occurrence Differs From Expiring an Existing Job

Two cases:

**A. Job already saved before the outage**

~~~text
07:50  PENDING notification in DB
08:00  Scheduled send
08:05  expires_at
11:30  Service recovers
~~~

The scanner can mark that record **`EXPIRED`** because evidence shows an intent was created and is no longer valid.

**B. No job created because the cron service was down**

~~~text
08:00  Cron expected to create a notification
11:30  Service recovers
~~~

There is no record for a scanner to "expire". The system needs **recurring schedule reconciliation**:

- Identify which period should have run.
- Check whether an intent exists (unique period key).
- Apply the misfire policy.
- Create a catch-up job or record **`SKIPPED_MISSED_OCCURRENCE`** in the schedule ledger if auditing is needed.

**Never mistake "no record exists" for "processed successfully".** For critical periodic notifications, track **expected occurrences vs. actually created intents**.

## 34. Daily Digest: Skip a Period or Coalesce Content?

A digest may cover a data window:

~~~text
Day D:
  activity 00:00 - 23:59

Schedule:
  send at 08:00 on Day D+1
~~~

If it fails to send by 12:00:

- You may **send late** if the content remains valuable.
- You may **skip the period** if the next notification rolls up the activity.
- You may **coalesce** unsent periods into one combined report.
- You may switch to a **download center** if the email grows too large across accumulated periods.

Crucially, manage **`coverage period`** separately from **`scheduled_at`**.

~~~text
digest_period_start = 2026-11-11T00:00:00Z
digest_period_end   = 2026-11-12T00:00:00Z
scheduled_at        = 2026-11-12T01:00:00Z
expires_at          = ...
~~~

If a scheduler runs late and builds the digest later, never query "last 24 hours from send time" and shift the period's contents. Use **fixed periods** and per-period idempotency.

## 35. Marketing Campaigns: Pause, Cancel, and Window End

A campaign may have states:

~~~text
DRAFT -> APPROVED -> SCHEDULED -> RUNNING
                           |
                           +-> PAUSED
                           +-> CANCELLED
                           +-> COMPLETED
~~~

Campaign emails must check:

- Is the campaign `RUNNING` or `PAUSED`?
- Is local time inside the sending window?
- Is recipient consent still valid?
- Are offers/content still active?
- Are tenant/provider quotas sufficient?
- Was this email already sent in this campaign?

**PAUSED** differs from **CANCELLED**:

- `PAUSED`: temporarily halts starting new attempts; jobs can continue upon resume if not expired.
- `CANCELLED`: permanently stops unsubmitted intents per policy.
- `COMPLETED`: campaign finished or ended; generates no further intents.

Do not mark all jobs `SKIPPED` when merely `PAUSED` if the product supports resuming. If `PAUSED` lasts past `expires_at`, however, those jobs may need to become `EXPIRED` upon resume.

### Stopping a campaign does not recall already-sent emails

The provider may already have accepted emails into its relay queue. Even after campaign status updates in the DB, already-`SUBMITTED` messages may still reach recipients. UI/admin views should clearly separate submitted, pending, cancelled, and unknown counts.

## 36. Quotas and Rate Limits: Until When Should Jobs Defer?

A due job may wait because:

~~~text
Tenant A rate: 20 recipients/second
Provider rate: 100 recipients/second
Global SMTP concurrency: 15
~~~

If no rate token or slot is available, the worker can update:

~~~text
status = RETRY_WAIT or DEFERRED_CAPACITY
next_attempt_at = proposed_retry_time
outcome_reason = CAPACITY_THROTTLED
~~~

However, compare against the deadline:

~~~text
if proposed_retry_time >= expires_at:
    EXPIRE (do not start a new SMTP attempt)
else:
    DEFER
~~~

A marketing campaign might wait until the next hour; an OTP likely cannot. **Deferral rules must follow notification policies**, not blindly "rate limiter said wait 1 hour, so wait".

### Never hold worker slots while merely waiting on rate limits

Thousands of jobs missing rate tokens should not block thousands of threads in **`Thread.sleep(...)`** or hold DB transactions open.

Instead:

1. Calculate the next retry timestamp.
2. Persist deferred status and `next_attempt_at`.
3. Release the slot/lease.
4. Let the scheduler pick it up again when due and still valid.

If a job defers repeatedly until its deadline, the `EXPIRED` reason should reflect **`CAPACITY_BACKLOG/PROVIDER_THROTTLE`** so SLA misses are visible rather than mislabeled as business errors.

## 37. Prioritizing Critical Emails Under Heavy Backlogs

Suppose:

~~~text
Tenant A:
   20,000 marketing emails pending
   10 OTP pending
~~~

If workers pull purely FIFO, those 10 OTPs may expire before sending.

Mitigations:

- **Priority classes**: security, transactional, marketing.
- **Reserved capacity** for short-TTL notifications.
- **Earliest-deadline-first** within an appropriate class.
- **Fair scheduling** across tenants so large tenants cannot monopolize queues.
- **Per-stream rates/concurrency**.
- **Admission control** for oversized campaigns.
- **Backpressure** toward producers to prevent unmanageable backlogs.

Still, unbounded priority for every security email can be abused. Enforce quotas and stream authorization so callers cannot self-assign `priority=security` to bypass limits.

### Priority does not override expiration policy

Even when the scheduler prioritizes OTPs, an expired OTP must still not be sent. Never let high priority bypass `expires_at`.

## 38. Worker Crash After Claim: Lease Expiry Does Not Prove Unsent

A worker might:

~~~text
09:00:00  Claim N100, lease_until = 09:02
09:00:01  Status = SENDING
09:00:02  SMTP DATA transmitted
09:00:03  Process crashes before saving SUBMITTED
09:02:00  Lease expires
~~~

If a scanner sees the expired lease and moves N100 back to `PENDING` for immediate resend, a duplicate email can be sent.

Distinguish two cases:

**CLAIMED but not yet SENDING:**

- Worker claimed the row, but has not started SMTP.
- When the lease expires with solid evidence send was not called, reclaim or expire based on deadline.
- Issue a new **`claim_token`** when another worker takes ownership.

**SENDING with no durable outcome:**

- SMTP may have accepted before the worker died.
- Lease expiration does not imply the message went unsent.
- Move to **`UNKNOWN/NEEDS_RECONCILIATION`** or await reconciliation per policy.
- Never blindly replay merely because `expires_at` has also passed.

### Fencing tokens and their limits

Claim tokens protect the database: an old worker cannot update the outbox after losing ownership.

However, tokens **cannot stop an already-open TCP connection** on the old worker from transmitting to the SMTP server. That is the boundary of leasing around non-transactional external side effects.

When sizing lease TTLs, measure SMTP connect/read/write timeouts, attachment rendering, and heartbeats. Even well-tuned leases do not create an exactly-once delivery guarantee.

## 39. SMTP Accepted but Saving Status Failed

A typical timeline:

~~~text
Worker:
    |
    +-- JavaMailSender.send(message)
    |         |
    |         v
    |      SMTP 250 Accepted
    |
    +-- UPDATE email_outbox SET status='SUBMITTED'
              |
              X database unavailable
~~~

The email may have left the application while the database row still says `SENDING`. If a worker restarts and retries it, the recipient can receive a second copy.

Mitigations:

1. Create an **attempt record** before starting SMTP.
2. When supported by the provider, attach a permitted **provider correlation ID** or custom idempotency metadata.
3. After accepted send, persist the outcome in a short transaction checked by claim token.
4. If the update fails, retain the attempt in a reconciliation-needed state rather than erasing traces.
5. Run a reconciliation worker with policies forbidding blind duplicate sends.
6. If replay is unavoidable, document duplicate risk and restrict to permitted notification types.

No standard ACID transaction spans both your application database and an SMTP server. **An outbox makes intent creation durable; it does not make SMTP exactly-once.**

## 40. UNKNOWN After Timeout: Never Mark EXPIRED_NOT_SENT

An attempt starts before the deadline, then hits a socket timeout awaiting the final reply:

~~~text
09:59  expires_at = 10:00
09:59  SMTP DATA begins
10:00  SMTP server may have accepted DATA
10:01  Client times out without receiving final reply
~~~

The application does not know whether the server accepted. The evidence-accurate status is **`UNKNOWN`**, neither definitely `FAILED` nor `EXPIRED_NOT_SENT`.

Resolution flow:

~~~text
UNKNOWN attempt
      |
      +-- Provider confirms accepted -> SUBMITTED
      |
      +-- Provider confirms rejected -> FAILED or EXPIRED
      |                               depending on deadline/policy
      |
      +-- No authoritative evidence -> UNKNOWN_REVIEW
      |
      +-- Retry explicitly allowed -> new attempt
                                      with duplicate risk noted
~~~

Some providers allow querying submission/delivery by message ID or API. Standard SMTP guarantees no universal idempotency query across all providers.

If expiration arrives while an attempt is `UNKNOWN`, **never start a brand-new attempt after `expires_at`**, yet still reconcile the old attempt. Expiration of **permission to keep trying** does not erase the possibility the email was already sent.

### Do not infer delivery from send()

Even when `JavaMailSender.send(...)` returns normally, you typically only know the message was **accepted by the SMTP server at submission**. You cannot claim the recipient opened it or that it definitely reached the Inbox.

**Bounces, deferrals, spam complaints, or delivery reports** arrive asynchronously via ESP webhooks or DSNs.

## 41. Idempotency Keys for Scheduled Notifications

An event or API request may be retried:

~~~text
POST /schedule-email
    -> DB insert succeeds
    -> response is lost

Client retry POST /schedule-email
    -> must not create a duplicate send intent
~~~

Define keys by business identity:

~~~text
(tenant_id, notification_kind, business_event_id, recipient_key)
~~~

For periodic notifications:

~~~text
(tenant_id, digest_kind, period_start, recipient_key)
~~~

For a campaign:

~~~text
(tenant_id, campaign_id, campaign_version, recipient_key)
~~~

Never use just Subject or `To` address as an idempotency key: two valid emails can share the same Subject and recipient across distinct events.

### Same key, changed schedule

If a client resends the same idempotency key intending to change `scheduled_at`/`expires_at`, the app must define whether to:

- Return the existing intent because it is a duplicate request.
- Require a separate **reschedule** operation with an expected version.
- Create a new version/intent per business rules and cancel the old one.

Never silently overwrite timestamps on an already-claimed or `SENDING` job simply because a replayed request carried different payload fields.

## 42. Rescheduling an Already-Skipped Email

A user may ask to resend a `SKIPPED`/`EXPIRED` email. However, **flipping status straight back to `PENDING`** usually erases history and can break idempotency.

Safer option:

~~~text
N100:
  status = EXPIRED
  reason = DEADLINE_REACHED
  finished_at = 10:00

N101:
  source_intent_id = N100
  reason = MANUAL_RESCHEDULE
  status = PENDING
  scheduled_at = 10:15
  expires_at = 10:45
~~~

Hence:

- N100 preserves its audit trail.
- N101 gets a fresh intent/version and fresh deadline.
- User/tenant resend permissions can be verified.
- Excessive reschedules can be throttled with separate idempotency.
- No guessing whether N100 was ever sent.

**Exception:** if a system updates the same row for an unstarted job, enforce versioning/locking and audit transitions. Never reschedule an `UNKNOWN`-outcome message as if it were guaranteed unsent.

## 43. Persisting Stop Reasons and Attempt History

A lone `EXPIRED` status does not explain why it happened. Keep **`outcome_reason`** plus a separate history table:

~~~sql
CREATE TABLE email_attempt (
    id                 UUID PRIMARY KEY,
    outbox_id          UUID NOT NULL,
    claim_token        UUID NOT NULL,
    attempt_number     INTEGER NOT NULL,
    started_at         TIMESTAMPTZ NOT NULL,
    completed_at       TIMESTAMPTZ,
    result             VARCHAR(40),
    error_category     VARCHAR(100),
    smtp_phase         VARCHAR(40),
    provider_message_ref VARCHAR(500),
    FOREIGN KEY (outbox_id) REFERENCES email_outbox(id)
);
~~~

Example history:

~~~text
N100 created      08:00
N100 scheduled    09:00
Attempt 1         09:00 -> SMTP 451
Retry scheduled   09:05
Attempt 2         09:05 -> connect_timeout
Retry proposed    09:20
Deadline          09:10
N100 EXPIRED      09:05 (RETRY_WINDOW_EXHAUSTED)
~~~

Here the **terminal status** is decided at 09:05 because the next retry would exceed the deadline, without waiting until 09:10 for a scanner. **`finished_at`** records when termination was decided, while **`expires_at`** remains the business deadline—those two timestamps can differ cleanly.

A notification that was never sent should also leave a clean record, e.g.:

~~~text
status=SKIPPED
reason=ORDER_ALREADY_PAID
attempt_count=0
~~~

Never fabricate a fake SMTP attempt just to log a skip. Attempt counts should reflect real transport attempts.

### Audits need access control and retention

History may contain message IDs, domains, provider replies, and correlation identifiers. Enforce tenant-scoped authorization and retention; never store passwords, raw SMTP traces, or raw email bodies in error tables.

## 44. Metrics: Separating Expired Emails From Failed Emails

A system might process 1,000 notifications in a day:

~~~text
SUBMITTED: 850
EXPIRED:    70
SKIPPED:    50
CANCELLED:  20
FAILED:     10
~~~

Lumping those 150 unsubmitted records into "SMTP failures" skews dashboards. Most never even started an SMTP attempt.

Use semantically clear metrics:

| Logical metric | Type | Unit |
|---|---|---|
| **`mail.outbox.created`** | Counter | New notification intents |
| **`mail.outbox.outcome`** | Counter | Unique notifications entering terminal state |
| **`mail.outbox.expired`** | Counter | Notifications past deadline |
| **`mail.outbox.skipped`** | Counter | Notifications skipped by policy |
| **`mail.outbox.cancelled`** | Counter | Notifications cancelled |
| **`mail.smtp.attempts`** | Counter | Actual SMTP submission attempts |
| **`mail.outbox.pending`** | Gauge | Waiting notifications |
| **`mail.outbox.oldest.due.age`** | Gauge | Wait time of the oldest due notification |
| **`mail.outbox.schedule.lag`** | Timer/Histogram | Lag from `scheduled_at` to attempt start |
| **`mail.outbox.expiration.lag`** | Timer/Histogram | Lag from `expires_at` to persisting `EXPIRED` |
| **`mail.worker.claims`** | Counter | Claimed jobs |
| **`mail.worker.stale.leases`** | Gauge/Counter | Expired leases or detected expired claims |
| **`mail.smtp.unknown`** | Counter/Gauge | Ambiguous attempts or jobs, per definition |
| **`mail.schedule.missed`** | Counter | Missed recurring schedule occurrences |

**Micrometer counters are not transactional ledgers.** A process can crash between DB commit and `Counter.increment()`. For exact billing or auditing counts, query the outbox/attempt tables and run reconciliation.

## 45. Choosing Labels Carefully to Avoid High Cardinality

Useful dimensions:

~~~text
notification_type=OTP|ORDER_REMINDER|DIGEST|MARKETING
outcome=EXPIRED|SKIPPED|CANCELLED|SUBMITTED|FAILED
reason=DEADLINE_REACHED|ORDER_ALREADY_PAID|...
provider=primary|backup
stream=security|transactional|marketing
environment=production|staging
~~~

Use only labels with **bounded, normalized values**. Never put recipient addresses, Subjects, notification/attempt IDs, business keys, raw exception messages, tokenized URLs, or per-email timestamps into metric labels.

A metric carrying a distinct `notification_id` across millions of emails creates millions of time series and PII exposure. Use **structured logs, traces, and authorized database queries** to look up individual emails.

### Micrometer example for terminal outcomes

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailOutcomeMetrics {

    private final MeterRegistry registry;

    public MailOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String notificationType,
            String outcome,
            String reason
    ) {
        registry.counter(
                "mail.outbox.outcome",
                "notification_type", notificationType,
                "outcome", outcome,
                "reason", reason
        ).increment();
    }
}
~~~

Assumes **`notificationType`/`outcome`/`reason`** are validated against allowlists/enums. If the same job is reprocessed, incrementing twice skews metrics. To keep "unique terminal outcome" semantics, emit only from a successful transition or aggregate from the ledger—never call `record(...)` on every poll for already-terminal jobs.

## 46. Alerts: Detecting Expirations Caused by System Congestion

An OTP expiring because the user never used the token is normal. An **OTP expiring before sending even starts** due to backlog indicates the system is missing its goal.

Example policy:

~~~text
If over 10 minutes:
  expired_due_to_capacity / all created OTP notifications > 1%
and at least 100 notifications
  -> Warning
~~~

Additional rules:

| Alert | Signal | First action |
|---|---|---|
| **`HighExpiryDueToBacklog`** | `EXPIRED` from capacity/worker lag rising | Inspect queues, workers, quotas |
| **`OldestDueAgeHigh`** | Due pending job waiting too long | Inspect scheduler, DB, provider |
| **`ExpiredScannerStopped`** | Missing expected sweep heartbeat | Check scheduler/liveness |
| **`UnknownSubmissionGrowing`** | `UNKNOWN` jobs increasing | Reconcile with provider, check outage |
| **`MissedScheduleOccurrences`** | Expected period missing intents | Inspect cron/schedule ledger |
| **`CancellationAfterSendSpike`** | Users cancelling already-sent jobs frequently | Review UX/schedule guards/races |
| **`SkipReasonDistributionChanged`** | Business skips spiking abnormally | Investigate policies or upstream data |

Never alert on raw ratios alone, since **1/1 = 100%** on tiny samples creates noise. Combine ratio thresholds, **minimum volume**, duration, and stream criticality.

### PromQL example

Suppose the exporter exposes counters:

~~~text
mail_outbox_outcome_total{
  outcome="EXPIRED",
  reason="CAPACITY_BACKLOG",
  stream="security"
}

mail_outbox_created_total{
  stream="security"
}
~~~

A windowed ratio:

~~~promql
sum by (stream) (
  increase(
    mail_outbox_outcome_total{
      outcome="EXPIRED",
      reason="CAPACITY_BACKLOG"
    }[10m]
  )
)
/
clamp_min(
  sum by (stream) (
    increase(mail_outbox_created_total[10m])
  ),
  1
)
~~~

**Denominator caveat:** emails created and expired within the same clock window do not strictly belong to the same cohort, because expiration happens after creation. This query is an **operational proxy** to spot spikes, not an exact cohort failure rate. For exact SLAs, analyze outbox rows by `scheduled_at` and observed outcome.

When deploying alerts, verify actual exporter metric/label names and enforce minimum volume. Also maintain separate scrape/liveness alerts so missing metrics from a dead worker are never misread as zero errors.

## 47. Wait Time and Skew Between Scheduled Time and SMTP Attempt

Three time metrics carry distinct meanings:

~~~text
schedule_lag =
    attempt_started_at - scheduled_at

outbox_wait_age =
    now - next_attempt_at
    (for due unprocessed jobs)

expiration_mark_lag =
    expired_at - expires_at
    (for scanner marking EXPIRED after deadline)
~~~

Never use **`expiration_mark_lag`** to claim "emails sent late". A scanner paused for 3 hours may mark `EXPIRED` late while worker guards still prevented sending the entire time.

Conversely, high **`schedule_lag`** before the deadline can breach SLAs even if the job has not `EXPIRED` yet.

### Cohort analysis

To measure missed-deadline rates:

~~~text
Cohort = all notifications with scheduled_at on Day D

Numerator = cohort notifications that failed to start
            a valid submission attempt before expires_at
            due to capacity/scheduler/provider

Denominator = cohort notifications obligated
              to be attempted/sent per policy
~~~

Exclude or separate notifications validly skipped because the user paid, cancelled, or withdrew consent. Those are not SLA failures of the email system.

### Pick verifiable SLIs/SLOs

Example:

> 99.9% of valid OTP notifications must start SMTP submission within 10 seconds after `scheduled_at`, before `expires_at`.

This is a **submission-timeliness SLI**, not the percentage of users actually receiving the OTP within 10 seconds. Delivery also depends on providers, receiving servers, and spam filters.

## 48. Per-Notification Diagnostics

When a user asks "Why didn't I get the reminder email?", the system should give an evidence-backed answer:

~~~text
Notification: N100
Type: PAYMENT_REMINDER
Scheduled: 2026-11-12T02:00:00Z
Deadline:  2026-11-12T02:15:00Z
Status: SKIPPED
Reason: ORDER_ALREADY_PAID
Attempts: 0
Decision time: 2026-11-12T02:00:03Z
~~~

Or:

~~~text
Notification: N101
Type: OTP
Status: EXPIRED
Reason: CAPACITY_BACKLOG
Scheduled: 2026-11-12T02:00:00Z
Deadline:  2026-11-12T02:05:00Z
Attempts: 0
~~~

Or:

~~~text
Notification: N102
Type: ORDER_CONFIRMATION
Status: UNKNOWN
Attempts: 1
Last phase: SMTP_FINAL_REPLY
Reconciliation: pending
~~~

For N102, the UI must never assert "email was definitely not sent". Show the uncertain status and reconcile with provider data.

**Never expose raw recipient emails, payloads, or SMTP traces to unauthorized callers.** Lookup endpoints must enforce tenant/user authorization.

## 49. Unit-Testing Time Boundaries With Clock.fixed

Deadline tests should not depend on the real system clock:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class SendDeadlinePolicyTest {

    private static Clock at(String timestamp) {
        return Clock.fixed(
                Instant.parse(timestamp),
                ZoneOffset.UTC
        );
    }

    @Test
    void beforeDeadlineMaySend() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T09:59:59Z")
        );

        assertTrue(
                policy.mayStartAttempt(
                        Instant.parse("2026-11-12T10:00:00Z")
                )
        );
    }

    @Test
    void exactlyAtDeadlineMustNotStartAttempt() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T10:00:00Z")
        );

        assertFalse(
                policy.mayStartAttempt(
                        Instant.parse("2026-11-12T10:00:00Z")
                )
        );
    }

    @Test
    void pastDeadlineMustNotSend() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T10:00:01Z")
        );

        assertFalse(
                policy.mayStartAttempt(
                        Instant.parse("2026-11-12T10:00:00Z")
                )
        );
    }

    @Test
    void noBusinessDeadlineAllowsAttempt() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T10:00:00Z")
        );

        assertTrue(policy.mayStartAttempt(null));
    }
}
~~~

These tests verify **pure Java policy**, not SQL transactions or live scheduler behavior. Because SQL uses `statement_timestamp()`, testing **database state-transition** boundaries requires a real database or test-controlled time injection.

### Matrix of time tests to include

| Scenario | Expectation |
|---|---|
| `now` 1 ns before `expires_at` | Allowed if policy has no minimum budget |
| `now` equals `expires_at` | Do not start a new attempt |
| `now` after `expires_at` | `EXPIRED` if still unsent |
| `scheduled_at` in the future | Not yet claimed |
| `next_attempt_at` after `expires_at` | Do not schedule a pointless retry |
| `expires_at` null | Follow non-expiring and retry/retention policies |
| `scheduled_at > expires_at` | Reject input or handle invalid per rule |
| User cancels before send | Do not send |
| Cancel after `SUBMITTED` | Do not claim email was recalled |
| Timezone with DST gap/overlap | Follow defined timezone rules |
| Event rescheduled | Deadline and notification version stay consistent |
| Cron misses a period during downtime | Misfire policy applied |

## 50. Concurrency Testing at the Expiration Boundary

To prove scanner and worker never overwrite each other, write **database integration tests** using the same PostgreSQL engine and transaction isolation as production.

### Scenario: worker and scanner race on the same row

~~~text
Given:
  N100: PENDING, expires_at imminent

Thread A:
  expire batch

Thread B:
  claim due batch

Assert:
  Only one transition wins for N100
  Never both validly EXPIRED and CLAIMED
  Never two workers owning the same claim token/state
~~~

### Scenario: cancellation vs. claim

~~~text
Thread A: CANCEL if PENDING
Thread B: CLAIM if PENDING and before deadline
~~~

Permitted outcomes:

- CANCEL wins; worker does not send.
- CLAIM wins; worker observes the cancellation request at the final admission gate if supported.

Never allow **cancel returning success while a worker still sends in `PENDING` state** due to an update lacking state/version checks.

### Scenario: lease expiration

1. Worker A claims N100.
2. A stops heartbeating.
3. Lease expires.
4. Worker B evaluates reclaim.
5. Worker A reappears and tries updating the outcome with its old token.

The system must reject A's **stale DB update**, while recognizing A may have called SMTP so B cannot blindly assume resending is safe.

### Scenario: batched expiration

- Seed 1,500 expired `PENDING` rows.
- Seed 300 expired `RETRY_WAIT` rows.
- Seed 30 expired `SENDING` rows.
- Seed 20 `SUBMITTED` rows past deadline.
- Sweep in batches.

Expect the scanner to expire only **eligible unsent states**, leave `SENDING`/`SUBMITTED` untouched per policy, and miss no eligible rows under lock contention.

**Never use a sequential in-memory `HashMap` test to infer SQL atomicity across concurrent workers.**

## 51. Integration Testing With a Test SMTP Server

Integration tests can use **GreenMail**, **Mailpit**, or a suitable SMTP capture server to verify **no actual submission occurs** for skipped/expired cases.

~~~text
JUnit / Spring test
      |
      +-- Start SMTP test server
      |
      +-- Insert scheduled notifications
      |
      +-- Trigger scheduler/worker
      |
      +-- Read captured SMTP messages
      |
      +-- Assert DB statuses and attempts
~~~

Cases to run:

| Case | DB outcome | What SMTP server receives |
|---|---|---|
| Job before `scheduled_at` | `PENDING` | Nothing |
| Job expired before claim | `EXPIRED` | Nothing |
| Order paid before send | `SKIPPED` | Nothing |
| Recipient unsubscribed | `SKIPPED`/`SUPPRESSED` | Nothing |
| User cancelled before claim | `CANCELLED` | Nothing |
| Job valid and eligible | `SUBMITTED` if accepted | One message per intent |
| Explicit SMTP reject, deadline left | `RETRY_WAIT` | Per server reply |
| Explicit SMTP reject, retry window spent | `EXPIRED`/`FAILED` per policy | No further attempt after deadline |
| SMTP timeout after DATA | `UNKNOWN` | May have received; do not guess |
| Job held due to quota | `DEFERRED`/`RETRY_WAIT` | Nothing until capacity opens |

For **`UNKNOWN`**, tests must simulate losing or failing to read the final reply. Never assert "0 messages captured" when transport may have received DATA before losing the reply.

For non-sent cases, assertions should prove:

1. Worker never called sender or SMTP server received zero messages.
2. Outbox holds the exact terminal status and reason.
3. No fabricated attempt records exist.
4. Retries or restarts never resend terminal intents.

Never send test emails to real mailboxes just to test expiration.

## 52. Runbook: Scheduled Email Was Not Sent

When a report arrives saying "send time passed and no email arrived", operators can investigate:

### Step 1 — Locate the notification intent

- Search with authorization by **tenant, business event ID, notification type, recipient reference**.
- Is there an outbox record?
- If none exists, this may be a **missed schedule occurrence** rather than an expired outbox record.
- Check the idempotency key to see whether the request was created earlier.

### Step 2 — Check timestamps

- Does `scheduled_at` match the right `Instant`/`ZoneId`?
- What is `next_attempt_at`?
- Was `expires_at` computed properly from TTL/event?
- Was there DST ambiguity or bad timezone conversion?
- Is clock skew between application and database abnormal?

### Step 3 — Inspect status

| Status | Investigation focus |
|---|---|
| **PENDING** | Not yet due, or scheduler has not picked it up |
| **RETRY_WAIT** | Temporary failure, rate limit/`next_attempt_at` |
| **CLAIMED** | Worker holds claim; check whether lease is still valid |
| **SENDING** | SMTP in flight or result update stuck |
| **EXPIRED** | Deadline and reason; separate business expiry from capacity |
| **SKIPPED** | Policy decision, consent, business state |
| **CANCELLED** | Actor, timestamp, cancellation audit |
| **FAILED** | Error category and retry policy |
| **UNKNOWN** | Provider reconciliation; never blindly replay |
| **SUBMITTED** | Check provider/delivery events; do not claim delivered |

### Step 4 — Identify root cause

- Are scheduler heartbeats/crons running?
- Are queue depth, oldest due age, and worker throughput abnormal?
- Is the SMTP provider hitting DNS/TCP/TLS/AUTH/throttle failures?
- Did a campaign starve OTPs?
- Did policy or consent change?
- Did a batch job or deployment stall leases?
- Is the database experiencing lock contention or slow indexes/queries?

### Step 5 — Recover safely

- **`PENDING` within deadline:** let the scheduler pick it up per rules.
- **`RETRY_WAIT` within deadline:** allow retry when provider recovers without dropping backoff.
- **`EXPIRED`:** do not catch up if content is meaningless; if needed, create a **new intent** per policy.
- **`SKIPPED`:** resend only if business rules changed and the actor is authorized.
- **`CANCELLED`:** never auto-reverse cancellations.
- **`UNKNOWN`/`SENDING` with lost outcome:** reconcile with provider before replaying.
- **`SUBMITTED`:** inspect delivery/bounce events instead of double-sending.

### Step 6 — Confirm recovery

Monitor backlog-induced expiry rate, pending age, retries, unknown outcomes, throughput, and new scheduled occurrences created on time.

## 53. Common Mistakes

| Mistake | Consequence | Better approach |
|---|---|---|
| Relying solely on `@Scheduled` to store schedules | Restarts lose planned periods | Durable schedule/outbox ledger |
| Omitting `expires_at` | Stale OTPs/campaigns still send | Per-category deadlines |
| One TTL for all emails | Invoices dropped or OTPs sent late | Per-notification-type policy |
| Expiring only in scanner, no worker check | Slow scanner lets expired emails send | Guard before claim and before send |
| Comparing `LocalDateTime` without `ZoneId` | Wrong timezones and DST bugs | Convert to `Instant` with explicit `ZoneId` |
| `SELECT` then send without claiming | Multiple workers double-send | Atomic claim + token/lease |
| Scanner expiring any row with old `expires_at` | Overwrites `SUBMITTED`/`UNKNOWN` | Filter eligible statuses |
| Treating expired lease as unsent | Duplicate retries after crash | Separate `CLAIMED` from `SENDING` |
| Timeout after DATA = definite failure | Duplicate sends | `UNKNOWN` and reconciliation |
| Counting `SKIPPED` as `SMTP FAILED` | Misleading dashboards | Clear outcome taxonomy |
| Using only job-creation data | Sends payment reminder after payment | Revalidate business state |
| Skipping suppression/consent re-check | Sends unauthorized emails | Policy check close to send time |
| No idempotency key for crons | Multiple digests for one period | Unique period/business key |
| Missing cron ticks with no ledger | Unaware which periods vanished | Misfire reconciliation |
| Every retry consumes business quota | Provider outage exhausts budget | Separate intent quota from attempt capacity |
| Retrying infinitely on errors | Retry storms and post-deadline sends | Backoff, max attempts, cutoffs |
| Flipping `EXPIRED` back to `PENDING` on resend | Loses audit, breaks idempotency | New intent/versioned reschedule |
| Cancelling jobs by deleting rows | Erases history and reconciliation | `CANCELLED` with audit |
| UI saying "cancelled" after SMTP accepted | Misleads users about recall | Distinguish cancel request vs. acceptance |
| Batching multiple recipients, skipping whole batch for one opt-out | Wrong per-recipient outcome | Per-recipient eligibility/outcome |
| Ignoring quota/provider lag when measuring lateness | Hides root cause | Oldest-age and reason metrics |
| Putting raw exceptions/recipients in metric labels | PII leaks, high cardinality | Enum reasons and access-controlled logs |

## 54. Implementation Checklist

**Policies and timing**

1. Does every notification type have an explicit late-send policy?
2. Are `scheduled_at`, `next_attempt_at`, and `expires_at` separated?
3. Are deadlines derived accurately from token/event/campaign TTLs?
4. Are timezone/DST rules defined for local-time schedules?
5. When due emails see changed business state, is SKIP/REPLACE/SEND_CURRENT defined?
6. Is a misfire policy defined for cron downtime?

**States and transactions**

7. Do terminal states `EXPIRED`, `SKIPPED`, `CANCELLED`, and `SUBMITTED` exist?
8. Are reason codes, actors, timestamps, and audits recorded?
9. Does the scanner expire only eligible unsent rows?
10. Do workers use atomic claims with tokens/leases?
11. Is there a final deadline check right before SMTP?
12. Are DB transactions kept out of SMTP sending?
13. Are stale workers and expired leases handled?
14. Do idempotency keys block duplicate intents?

**Retries and providers**

15. Do retries factor in deadlines, backoff, minimum delay, and max attempts?
16. Are explicit SMTP rejections separated from `UNKNOWN` after DATA?
17. When DB updates fail after acceptance, is reconciliation in place?
18. Does cancellation return honest statuses if already `SENDING`/`SUBMITTED`?
19. Are per-recipient eligibility and suppressions handled where needed?
20. Does provider failover control duplicate risk?

**Operations and security**

21. Are capacity-induced expirations, per-reason skips, and oldest due age measured?
22. Are alerts configured for missed occurrences, worker liveness, and unknown backlogs?
23. Are attempt-level and notification-level metrics separated?
24. Are emails, Subjects, and tokens kept out of metric labels and ordinary logs?
25. Do lookup UIs/APIs enforce tenant authorization?
26. Do runbooks exist for controlled replays and rescheduling?

**Testing**

27. Tested before/at/after deadlines with `Clock.fixed`?
28. Tested scanner and worker racing on the same row?
29. Tested user cancellation during claim/send?
30. Tested retries crossing `expires_at`?
31. Tested cron misfires and unique period keys?
32. Tested SMTP accepted with DB result update failure?
33. Tested never sending to suppressed recipients or expired jobs?

## 55. Key Takeaways

**Handling expired or skipped emails** is about defining how far in the scheduling lifecycle a notification remains eligible to send, and recording precisely why it was not sent when conditions changed.

Core principles:

1. **`scheduled_at`, `next_attempt_at`, and `expires_at` serve distinct roles.** Use `Instant`/`ZoneId` and business deadlines instead of a single timestamp.
2. **`EXPIRED`, `SKIPPED`, `CANCELLED`, `FAILED`, `UNKNOWN`, and `SUBMITTED` are not equivalent.** They require clear state transitions and reason codes.
3. **The scanner is not the sole safeguard.** Workers must conditionally check state and deadlines right before starting an SMTP attempt.
4. **An outbox and atomic claims** survive restarts, prevent two workers from grabbing the same job, and preserve audits; they do not make SMTP exactly-once.
5. **Retries must respect final deadlines.** Do not keep retrying solely because an error is temporary if the notification is no longer useful.
6. **Re-check business state, consent, and suppressions** before sending notifications that may have become obsolete.
7. **Cron misfires** differ from existing jobs that expired; use a schedule ledger and catch-up policies when backfill is required.
8. **`UNKNOWN` after SMTP DATA** requires reconciliation—never label it "definitely unsent" and replay arbitrarily.
9. **Measure skip causes by notification cohort**, never lumping business skips together with SMTP failures.
10. **Test time boundaries, concurrency, cancellations, and crash recovery** with fixed `Clock`s, real databases, and suitable SMTP test servers.

**A reliable email scheduling system is not one that forces every job out at all costs—it is one that sends only notifications that remain valid, stops for the right reason when sending should not happen, and preserves enough evidence to explain outcomes or recover safely.**








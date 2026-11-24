# Rescheduling Without Losing Pending Requests

In an application using **Spring Framework Mail**, an email is not always sent the moment a business event happens. The system may send a newsletter every Monday, a payment reminder after three days, an end-of-day digest, or let users schedule notifications.

Problems arise when **the schedule changes while requests are already waiting**. If developers simply cancel the old in-memory task and create a new one, scheduled emails can vanish. If an update shifts every send timestamp in the database without checking states, retrying emails can get pushed back indefinitely or jobs already claimed by workers can be double-sent.

Example:

~~~text
09:00  Customer created 800 requests scheduled for 10:00.
09:20  Administrator changes the schedule to 11:00.
09:21  A worker is currently processing 20 requests.
09:22  30 other requests are awaiting retry after SMTP 451.

Design requirements:
  - Do not silently delete the 800 existing requests.
  - Do not create 800 duplicate requests with the same content.
  - Define explicit rules for which requests get moved.
  - Never arbitrarily alter already-sent or in-flight requests.
  - Preserve recoverable state after application restarts.
~~~

**Core principle:** **the schedule generating work** and **the already-created send requests** are two distinct entities. Changing a cron expression, send hour, or frequency does not automatically mean deleting and recreating every mail job.

This lesson focuses on designing safely mutable schedules with Spring, databases/outboxes, `@Scheduled`, `TaskScheduler`, or Quartz—especially preserving pending requests, avoiding race conditions, and supporting auditing.

## 1. Distinguishing Schedule, Occurrence, and Send Request

A scheduled mail system typically has three layers:

| Layer | Question answered | Example |
| --- | --- | --- |
| **Schedule definition** | When and by what rule should work be generated? | Every Monday at 09:00, timezone `Asia/Ho_Chi_Minh` |
| **Schedule occurrence** | Which specific firing of that schedule is this? | Weekly newsletter 2026-W46 |
| **Mail request/job** | Which email goes to whom and in what current state? | Newsletter for subscriber 123 currently `PENDING` |

A model:

~~~mermaid
flowchart TD
    A["Schedule definition v3"] --> B["Schedule occurrence"]
    B --> C["Durable mail requests / outbox"]
    C --> D["Due job dispatcher"]
    D --> E["SMTP/API sender"]
    E --> F["Provider events"]
    A -. "Schedule change" .-> G["Schedule definition v4"]
    G --> H["Future occurrences"]
~~~

The transition from schedule v3 to v4 **does not implicitly delete** rows already saved in the outbox.

### 1.1. Recurring schedules differ from single-email schedules

**Recurring schedule:** generates a batch of emails on a cadence:

~~~text
Every Monday 09:00
  -> occurrence: weekly-digest:2026-W46
  -> creates 10,000 mail requests
~~~

If moved to Tuesday, the question is whether the new schedule applies only to **future unmaterialized occurrences** or also shifts already-created jobs.

**One-time schedule:** a user schedules an email for 09:00 tomorrow:

~~~text
request-abc:
  sendAt = 2026-11-13T02:00:00Z
  state = PENDING
~~~

If the user changes it to 11:00, you normally update `sendAt` on that exact request; there is no need to delete the old request and mint a new ID.

### 1.2. Triggering the schedule does not mean the email was sent

Milestones must stay distinct:

~~~text
Schedule triggered
    |
    v
Mail job persisted
    |
    v
Job eligible for sending
    |
    v
Worker claims job
    |
    v
SMTP/API submission attempted
    |
    v
SUBMITTED / RETRY_WAIT / FAILED_FINAL / UNKNOWN
~~~

A cron firing does not prove emails were sent. Conversely, a failed SMTP submission may leave a job waiting for retry regardless of whether the cron changed.

## 2. Why Can Cancel-and-Recreate Lose Mail?

A simple but risky pattern:

~~~java
scheduledFuture.cancel(false);
scheduledFuture = taskScheduler.schedule(
        () -> mailSender.send(message),
        newTrigger);
~~~

With this code, the schedule lives inside `ScheduledFuture` and JVM memory. Risks:

- **Restarts:** the app loses tasks living solely in memory.
- **Schedule changes:** cancelling the old task can discard the underlying work it represented.
- **Races:** the old task may have already started; `cancel(false)` cannot recall an already-sent email.
- **Multiple replicas:** every instance can schedule the same task, causing duplicates.
- **No audit trail:** hard to know how many requests were waiting, who edited the schedule, and which emails were affected.
- **No durable retries:** an SMTP exception can fail the work with no persisted state left to retry.

`TaskScheduler` and `ScheduledFuture` remain useful to **wake the coordinator**, never as the sole store for critical business send requests.

### 2.1. A cron expression is not a queue

~~~java
@Scheduled(cron = "0 0 9 * * MON")
void sendWeeklyDigest() {
    // ...
}
~~~

The `@Scheduled` annotation runs a method on a configured timer; it does not maintain a durable table of pending emails to recover after a crash. If the app changes cron, restarts, or deploys mid-run during a long batch, preserving/recovering remaining requests is the application's responsibility.

### 2.2. Never use an in-RAM recipient list as the source of truth

~~~java
List<String> pendingRecipients = loadRecipients();
// Reschedule -> cancel old task -> list vanishes when process stops.
~~~

For important emails, persist a **durable mail request** or outbox row before handing off to workers, including business identity, send time, status, and retry metadata.

## 3. Choose a Rescheduling Policy Before Writing Code

No single rule fits every product. Publish explicitly **how far a schedule change reaches**.

| Policy | Already-created requests | Not-yet-created requests | Best fit |
| --- | --- | --- | --- |
| **KEEP_EXISTING** | Keep committed send time | Use new schedule | Weekly newsletters, scheduled reminders |
| **MOVE_UNSTARTED** | Move only unattempted and unclaimed jobs | Use new schedule | User edits a one-time send hour |
| **CANCEL_UNSENT** | Move eligible jobs to `CANCELLED` with audit | Do not generate under old schedule | Explicit campaign cancellation |
| **REPLAN_FUTURE_OCCURRENCES** | Keep already-materialized occurrences; recalculate future | Use new cron/timezone | Recurring schedule frequency changes |
| **REVIEW_IN_FLIGHT** | Keep/investigate in-flight or unknown-outcome jobs | Follow new schedule | Major changes with duplicate risk |

Policy names in this table are **suggested application conventions**, not enums provided by Spring Mail.

### 3.1. KEEP_EXISTING — safe default for recurring schedules

~~~text
09:00  Weekly digest occurrence W46 created 2,000 requests.
09:10  Admin changes schedule from Monday to Tuesday.

Already-created W46:
  2,000 requests remain intact under their committed time/conditions.

Unmaterialized occurrences:
  Use Tuesday schedule.
~~~

Benefit: honors commitments for existing jobs without mass-mutating data—especially valuable when the schedule is purely a **work generator**.

### 3.2. MOVE_UNSTARTED — changing send time on a pending job

~~~text
Request #A:
  state=PENDING
  attempts=0
  sendAt=10:00

User reschedules:
  sendAt=11:00

Request #A:
  ID preserved
  state=PENDING
  attempts=0
  sendAt=11:00
  rescheduled audit recorded
~~~

Do not create Request #B for the same business request. Preserving ID/correlation avoids double-sending and helps support trace history.

### 3.3. CANCEL_UNSENT does not mean "losing the request"

When a user truly cancels, never delete the row without a trace:

~~~text
PENDING -> CANCELLED
reason=USER_CANCELLED_CAMPAIGN
actor=admin-17
changedAt=...
~~~

The row and audit event remain per retention policy. An already-`SUBMITTED` email cannot be "unsent" merely by flipping status in the database.

### 3.4. Product questions to decide upfront

Before changing a schedule:

1. Does the new schedule apply **only to future firings** or also to already-created jobs?
2. Can a job whose send time passed but was not yet claimed be moved?
3. Should a `RETRY_WAIT` job after an SMTP error keep retrying under its old backoff?
4. Can a `SUBMITTING` job accept a cancellation request?
5. May time-limited emails like OTPs send if the new time exceeds expiry?
6. When changing timezone or cron, should an already-created occurrence regenerate?
7. Can users preview affected job counts and undo?

These decisions are a **business contract**—they cannot be derived from `@Scheduled` or `CronTrigger` alone.

## 4. Durable Data Model

To illustrate, assume PostgreSQL, Spring Boot 3, and Java 17+. Real schemas must match business rules, indexes, partitioning, and migration strategies.

### 4.1. Schedule table

~~~sql
CREATE TABLE mail_schedule (
    id                UUID PRIMARY KEY,
    tenant_id         VARCHAR(80) NOT NULL,
    schedule_kind     VARCHAR(30) NOT NULL,
    cron_expression   VARCHAR(200),
    timezone_id       VARCHAR(100) NOT NULL,
    one_time_at       TIMESTAMPTZ,
    next_fire_at      TIMESTAMPTZ,
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    version           BIGINT NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Where:

- `schedule_kind` may be `ONE_TIME` or `RECURRING`;
- `cron_expression` defines occurrence generation;
- `timezone_id` stores an **IANA timezone** like `Asia/Ho_Chi_Minh`, not just `+07:00`;
- `next_fire_at` stores the computed next trigger time for scheduler scans;
- `version` supports optimistic concurrency control and change auditing.

**Never store SMTP passwords or OAuth tokens in the schedule table.** Schedules can reference a sender profile ID, while credentials stay in secure provider adapter configuration.

### 4.2. Mail request table

~~~sql
CREATE TABLE mail_request (
    id                UUID PRIMARY KEY,
    schedule_id       UUID REFERENCES mail_schedule(id),
    schedule_version  BIGINT,
    occurrence_key    VARCHAR(150),
    recipient_key     VARCHAR(150) NOT NULL,
    tenant_id         VARCHAR(80) NOT NULL,
    mail_type         VARCHAR(80) NOT NULL,
    payload_ref       VARCHAR(300) NOT NULL,
    state             VARCHAR(40) NOT NULL,
    scheduled_at      TIMESTAMPTZ NOT NULL,
    next_attempt_at   TIMESTAMPTZ,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(120),
    lease_until       TIMESTAMPTZ,
    cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mail_request_due
    ON mail_request (scheduled_at, next_attempt_at, state);

CREATE INDEX idx_mail_request_schedule_state
    ON mail_request (schedule_id, schedule_version, state);
~~~

`payload_ref` points to safely persisted render/template/attachment data rather than stuffing raw email bodies into job rows. `recipient_key` is a controlled internal identifier, not a raw email address used as a metric label.

A suitable unique key for recurring schedules:

~~~sql
CREATE UNIQUE INDEX uq_mail_request_occurrence_recipient
ON mail_request (
    schedule_id,
    occurrence_key,
    recipient_key
)
WHERE schedule_id IS NOT NULL
  AND occurrence_key IS NOT NULL;
~~~

This unique constraint blocks duplicating **the same logical occurrence for the same recipient**. `occurrence_key` must be derived deterministically from business semantics, such as `weekly-digest:2026-W46`. Never simply include `schedule_version` in the unique key, because editing the schedule could let the same occurrence regenerate under the new version and **bypass deduplication**.

For standalone requests lacking a `schedule_id`, enforce an `idempotency_key` or dedicated unique business key; the partial index above does not cover every case.

### 4.3. Schedule change audit

~~~sql
CREATE TABLE mail_schedule_audit (
    id               UUID PRIMARY KEY,
    schedule_id      UUID NOT NULL,
    old_version      BIGINT NOT NULL,
    new_version      BIGINT NOT NULL,
    actor_id         VARCHAR(120) NOT NULL,
    change_policy    VARCHAR(50) NOT NULL,
    old_definition   JSONB NOT NULL,
    new_definition   JSONB NOT NULL,
    affected_jobs    BIGINT NOT NULL,
    changed_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

In production, audits may also need request IDs, reasons, approvers, dry-run impact, and access control. Avoid logging full recipients, secrets, or payloads unnecessarily.

### 4.4. Distinguishing scheduled_at and next_attempt_at

These are two **different** timestamps:

- `scheduled_at`: business constraint forbidding sending earlier than this time.
- `next_attempt_at`: transport retry timestamp after an error.

Example:

~~~text
scheduled_at    = 10:00
attempt-1       = 10:01 -> SMTP 451
next_attempt_at = 10:06
state           = RETRY_WAIT
~~~

If an admin moves the campaign to 11:00, do not blindly overwrite `next_attempt_at=11:00` on every job. That alters retry policy and can delay unsent mail unpredictably.

A job becomes eligible when both business timing and backoff allow:

~~~text
scheduled_at <= now
AND (next_attempt_at IS NULL OR next_attempt_at <= now)
AND state in (PENDING, RETRY_WAIT)
~~~

## 5. Mail Request State Machine

An example flow:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: due + atomic claim
    PENDING --> CANCELLED: authorized cancel
    PENDING --> PENDING: reschedule
    CLAIMED --> SUBMITTING: begin send
    CLAIMED --> PENDING: safe lease recovery
    SUBMITTING --> SUBMITTED: transport accepted
    SUBMITTING --> RETRY_WAIT: retryable failure
    SUBMITTING --> FAILED_FINAL: permanent failure
    SUBMITTING --> UNKNOWN: uncertain outcome
    RETRY_WAIT --> CLAIMED: backoff complete
    RETRY_WAIT --> FAILED_FINAL: retry limit
    SUBMITTED --> [*]
    FAILED_FINAL --> [*]
    CANCELLED --> [*]
    UNKNOWN --> [*]
~~~

This state machine is illustrative; define "terminal" explicitly for your app. `SUBMITTED` means transport acceptance, not provider delivery; separate delivery events may follow.

### 5.1. Rescheduling rules by state

| State | Automatically move `scheduled_at`? | Reason |
| --- | --- | --- |
| `PENDING`, 0 attempts, unclaimed | Yes, under `MOVE_UNSTARTED` | No side effect has started |
| `RETRY_WAIT` | Not by default | Retry schedule is a post-attempt decision |
| `CLAIMED` | Do not edit arbitrarily | Worker already holds job/lease |
| `SUBMITTING` | Cannot guarantee cancel/move | SMTP side effect may be in flight |
| `SUBMITTED` | No | Email already handed to transport |
| `UNKNOWN` | Never blindly retry/move | Provider may have already accepted |
| `FAILED_FINAL` | No | Requires a dedicated recovery command |
| `CANCELLED` | Never auto-resurrect | Deliberate cancellation with audit |

Never just check `sent = false` and update every job; a boolean cannot distinguish retry, claimed, unknown, or cancelled.

### 5.2. Never overload "send time" into one multi-actor column

Wrong:

~~~text
nextSendAt = business schedule time
nextSendAt = retry backoff time
nextSendAt = worker lease expiry
~~~

One column serving three meanings breaks when admins reschedule. Better:

~~~text
scheduled_at
next_attempt_at
lease_until
~~~

Each column has its own owner and transition rules.

## 6. Modifying a One-Time Schedule Transactionally

Suppose a one-time schedule created unattempted `PENDING` requests. The user moves send time from 10:00 to 11:00 under `MOVE_UNSTARTED`.

One transaction should:

1. Lock/update the schedule at the expected version.
2. Update `scheduled_at` on **eligible jobs only**.
3. Preserve IDs, payloads, recipients, and audits.
4. Commit together so workers never see half-old, half-new state.

### 6.1. PostgreSQL SQL example

~~~sql
BEGIN;

SELECT version
FROM mail_schedule
WHERE id = :schedule_id
FOR UPDATE;

-- Application verifies the read version equals expected_version.

UPDATE mail_schedule
SET one_time_at = :new_send_at,
    next_fire_at = :new_send_at,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :schedule_id
  AND version = :expected_version;

-- Move only requests never attempted or claimed,
-- and still scheduled in the future.
UPDATE mail_request
SET scheduled_at = :new_send_at,
    schedule_version = :new_version,
    updated_at = CURRENT_TIMESTAMP
WHERE schedule_id = :schedule_id
  AND schedule_version = :expected_version
  AND state = 'PENDING'
  AND attempt_count = 0
  AND lease_owner IS NULL
  AND scheduled_at > CURRENT_TIMESTAMP;

-- INSERT mail_schedule_audit with moved row count.

COMMIT;
~~~

This is an **illustrative transaction pattern**, not a standalone runnable script: the application must check row counts/versions, bind `:new_version`, insert the audit row in the same transaction, and roll back on conflict. PostgreSQL evaluates row locks and `WHERE` predicates safely under concurrent updates.

**Critical limitation:** updating all jobs of a schedule to **the same `new_send_at` is valid only for a one-time schedule** or a targeted single occurrence. For recurring crons, never collapse jobs from multiple weeks onto one timestamp!

### 6.2. Never overwrite next_attempt_at on retry jobs

The SQL above intentionally filters `state = 'PENDING'` and `attempt_count = 0`. `RETRY_WAIT` jobs preserve their backoff. If product rules demand shifting retry jobs too, use an approved policy such as:

~~~text
eligible_at = max(new_business_send_at, existing_retry_backoff_at)
~~~

while still checking retry limits, deadlines, and prior attempts. Never run a blanket SQL update simply matching `status != 'SUBMITTED'`.

### 6.3. What if the new time is in the past?

If an admin changes 11:00 to 09:00 when it is already 10:00:

- **Send immediately:** jobs become eligible at once.
- **Reject:** API rejects timestamps in the past.
- **Next valid occurrence:** for recurring schedules, compute the next future firing.

Choose an explicit policy. Never silently "snap to now" when the user expects exact scheduling.

## 7. Spring Service Example With Optimistic Versioning

Architectural Java example; repository implementations use JPA/`JdbcTemplate` depending on your project:

~~~java
public enum ReschedulePolicy {
    KEEP_EXISTING,
    MOVE_UNSTARTED,
    CANCEL_UNSENT
}

public record RescheduleCommand(
        UUID scheduleId,
        long expectedVersion,
        Instant newSendAt,
        ReschedulePolicy policy,
        String actorId,
        String reason) {
}

public record RescheduleResult(
        UUID scheduleId,
        long newVersion,
        int affectedJobs) {
}
~~~

Service:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailScheduleService {
    private final MailScheduleRepository schedules;
    private final MailRequestRepository requests;
    private final ScheduleAuditRepository audits;
    private final Clock clock;

    public MailScheduleService(
            MailScheduleRepository schedules,
            MailRequestRepository requests,
            ScheduleAuditRepository audits,
            Clock clock) {
        this.schedules = schedules;
        this.requests = requests;
        this.audits = audits;
        this.clock = clock;
    }

    @Transactional
    public RescheduleResult changeOneTimeSchedule(
            RescheduleCommand command) {

        MailSchedule schedule = schedules.lockById(
                command.scheduleId()).orElseThrow();

        if (schedule.version() != command.expectedVersion()) {
            throw new ScheduleVersionConflictException();
        }
        schedule.requireKind("ONE_TIME");

        Instant now = clock.instant();
        long oldVersion = schedule.version();
        long newVersion = oldVersion + 1;
        int affected;

        switch (command.policy()) {
            case KEEP_EXISTING -> affected = 0;
            case MOVE_UNSTARTED -> affected =
                    requests.moveNeverAttemptedFutureJobs(
                            schedule.id(),
                            oldVersion,
                            newVersion,
                            now,
                            command.newSendAt());
            case CANCEL_UNSENT -> affected =
                    requests.cancelNeverAttemptedFutureJobs(
                            schedule.id(), oldVersion, now);
            default -> throw new IllegalArgumentException(
                    "Unsupported policy");
        }

        schedules.updateOneTimeDefinition(
                schedule.id(),
                oldVersion,
                command.newSendAt());

        audits.record(
                schedule.id(),
                oldVersion,
                newVersion,
                command.policy().name(),
                affected,
                command.actorId(),
                command.reason(),
                now);

        return new RescheduleResult(
                schedule.id(), newVersion, affected);
    }
}
~~~

Interfaces, repositories, and exceptions here are **illustrative application code**, not built-in Spring Mail APIs. Repositories must:

- ensure `lockById` uses `SELECT ... FOR UPDATE` or equivalent locking;
- update `version` predicated on the old version and verify affected row counts;
- update requests predicated on state/attempt/lease and return actual affected row counts;
- write audits inside the same DB transaction;
- check tenant/actor authorization before editing schedules;
- reject new send times violating deadlines or quiet hours.

For `KEEP_EXISTING` in this example, the one-time schedule updates while already-created jobs do not move; that makes sense only if the architecture separates unmaterialized occurrences from old jobs. If a one-time schedule was already fully materialized, the business API should clarify that "editing config only" does not move already-queued emails. Never expose a meaningless policy in the UI just to fill an enum.

### 7.1. Check versions to prevent lost updates

Two administrators open the schedule page at version 4:

~~~text
Admin A sees version 4 -> changes to 11:00.
Admin B sees version 4 -> changes to 13:00.

Admin A commits version 5.
Admin B sends expectedVersion=4 -> receives 409 Conflict.
~~~

Never silently let B overwrite A. The API can return the latest schedule and ask the user to confirm.

### 7.2. Reschedule requests must be idempotent

A client may time out after the server already committed:

~~~text
Client POST /reschedule
Server COMMITs successfully
Network timeout before response
Client retries POST /reschedule
~~~

Without retry recognition, the system could emit two audit events or bump versions twice. Accept an `idempotency_key` on reschedule operations, persist the outcome in the same transaction, and return the cached result when the client retries the same key.

Optimistic versioning prevents overwrites, while **idempotency keys** recover uncertain HTTP outcomes. Both mechanisms complement each other.

## 8. Race Conditions Between Admins and Mail Workers

A hazardous scenario:

~~~text
T1 Worker reads job #A (scheduled_at=10:00, PENDING).
T2 Admin changes #A's scheduled_at to 11:00.
T3 Worker still sends job #A at 10:00.
~~~

If a worker simply `SELECT`s and sends much later, admin reschedules may not take effect. Use **atomic claiming** or **leases** instead of read-then-work.

### 8.1. Atomic claiming with PostgreSQL

~~~sql
WITH due AS (
    SELECT id
    FROM mail_request
    WHERE state IN ('PENDING', 'RETRY_WAIT')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (
          next_attempt_at IS NULL
          OR next_attempt_at <= CURRENT_TIMESTAMP
      )
    ORDER BY scheduled_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_request AS m
SET state = 'CLAIMED',
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM due
WHERE m.id = due.id
RETURNING m.*;
~~~

Meaning:

- `FOR UPDATE SKIP LOCKED` lets multiple workers claim distinct rows.
- Status and lease update in the same transaction.
- Workers receive only jobs satisfying `scheduled_at` and `next_attempt_at`.
- Admin reschedules update only `PENDING`, unattempted, unclaimed jobs.

In PostgreSQL, competing updates lock rows and re-evaluate predicates under proper transaction semantics. If the admin locks/updates first, the worker sees the new timestamp and skips claiming early. If the worker claims first, the admin sees the job is no longer `PENDING` to move. That creates a consistent boundary around **which jobs have started execution**.

### 8.2. Never hold DB transactions open across SMTP sends

Avoid:

~~~text
BEGIN
SELECT ... FOR UPDATE
SMTP connect/send (can block tens of seconds)
UPDATE job
COMMIT
~~~

Holding row locks and DB connections across network calls causes lock contention, indirect deadlocks, and pool exhaustion. Better:

1. Claim a short batch inside a DB transaction.
2. Commit the lease.
3. Re-check status and send SMTP outside any transaction.
4. Persist attempt results in a new transaction using worker ownership/fencing tokens.

Between steps 1 and 3, a race with cancellation can still happen. Workers should re-check `cancel_requested` right before starting side effects, yet **cannot guarantee recalling an email being submitted to SMTP** if cancellation arrives right at send time.

### 8.3. Leases and fencing tokens

A worker may crash after claiming. When the lease expires, the job must recover. However, the old worker may simply have paused and resumed.

Example:

~~~text
Worker A claims job #A (lease=1).
Worker A pauses.
Lease expires.
Worker B recovers and claims (lease=2).
Worker A wakes up and tries writing SUBMITTED.
~~~

Use a `lease_version` or claim token incremented on every claim:

~~~sql
UPDATE mail_request
SET state = 'SUBMITTED',
    lease_owner = NULL,
    lease_until = NULL
WHERE id = :job_id
  AND lease_version = :expected_lease_version
  AND state = 'SUBMITTING';
~~~

If affected rows equals 0, the old worker lost permission to mutate status. **Database fencing stops state overwrites**, but cannot stop an SMTP request already sent onto the wire. Continue relying on idempotency, attempt history, and `UNKNOWN` handling.

### 8.4. Never blindly reset all SUBMITTING jobs to PENDING

If a worker dies **after the SMTP server accepted the message but before the DB committed**, the job stays in `SUBMITTING`. Blindly resetting all such rows for immediate retry can send duplicate emails.

Define a policy for uncertain outcomes:

- wait for provider events or query provider message IDs if supported;
- mark `UNKNOWN` and route to reconciliation;
- evaluate retries based on email criticality, deadlines, and duplicate risk;
- log attempt IDs and correlation IDs for investigation.

Plain SMTP provides no end-to-end exactly-once delivery; never promise that a DB transaction guarantees single delivery.

## 9. Recurring Schedules: Version Instead of Mass-Editing

Weekly newsletter example:

~~~text
Schedule v1:
  MON 09:00 Asia/Ho_Chi_Minh

W46 occurrence created:
  5.000 mail requests.

Admin changes schedule:
  TUE 10:00 Asia/Ho_Chi_Minh
  Schedule v2
~~~

Under `REPLAN_FUTURE_OCCURRENCES`:

- already-created occurrence W46 keeps its identity and requests;
- the schedule definition advances to v2;
- `next_fire_at` recalculates for future occurrences;
- pending/retrying W46 requests are not deleted;
- occurrence keys prevent creating a second firing for the same week if the business contract specifies one newsletter/week.

### 9.1. What is an occurrence key?

If the contract is "one newsletter per ISO week":

~~~text
scheduleId=weekly-newsletter-tenant-a
occurrenceKey=2026-W46
~~~

Moving from Monday to Tuesday within the same week still maps to occurrence W46; it will not fire a second time just because the fire time changed.

If the contract is "every cron trigger—even twice in one day—is a distinct event", key occurrences by a durably persisted scheduled fire ID. **Occurrence identity rules must match business semantics**, rather than forcing `week number` onto every cron.

### 9.2. Never rely on schedule_version alone for deduplication

Wrong:

~~~text
unique(schedule_id, schedule_version, recipient_id)
~~~

If the version increments, the same recipient could receive the same occurrence content again. Prefer:

~~~text
unique(schedule_id, occurrence_key, recipient_key)
~~~

and keep `schedule_version` as metadata/audit. When intentionally resending an occurrence, create a controlled and audited **resend operation ID** instead of bypassing uniqueness via version bumps.

### 9.3. Create occurrences and advance the cursor in one transaction

Multi-instance scheduler:

~~~text
Replica A sees schedule is due.
Replica B also sees schedule is due.
~~~

If both spawn jobs independently, email volume doubles. Design:

1. Lock the schedule row or claim a schedule lease.
2. Read current `version` and `next_fire_at`.
3. Compute `occurrence_key` and persist the occurrence.
4. Create/incrementally enqueue requests under the unique constraint.
5. Compute and persist the new `next_fire_at`.
6. Commit.

When creating tens of thousands of requests, you do not have to insert every row inside one huge transaction; persist the **occurrence** once and let a generator batch via cursor using per-recipient idempotency keys.

Crucially, **never advance `next_fire_at` as if done before durably persisting the occurrence**.

### 9.4. Schedule updates concurrent with scheduler ticks

If an admin updates a cron while the scheduler is about to fire, serialize them:

~~~text
Admin transaction:
  lock schedule row -> update version/next_fire_at

Scheduler transaction:
  lock same row -> check version/due -> create occurrence
~~~

Two transactions must never read a stale cron snapshot and commit incompatible decisions. DB locking/version checks establish a deterministic order:

- scheduler wins first: old occurrence was created; admin handles per published policy;
- admin wins first: scheduler sees new version and new `next_fire_at`;
- never silently delete an already-committed occurrence.

## 10. @Scheduled Should Wake the Dispatcher, Not Hold the Backlog

A simple approach in Spring Boot:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Dispatcher:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailDispatchTick {
    private final DueMailJobService jobs;

    public MailDispatchTick(DueMailJobService jobs) {
        this.jobs = jobs;
    }

    @Scheduled(
        fixedDelayString = "${app.mail.dispatch-delay:PT5S}")
    public void dispatchDueJobs() {
        jobs.claimAndDispatchDueBatch(50);
    }
}
~~~

`DueMailJobService` is an application service executing claim transactions/leases and sending via the appropriate sender. `@Scheduled` merely triggers scans of **durably persisted** DB rows.

Why does this make rescheduling safe?

- Send timestamps live in `mail_request.scheduled_at`, not buried solely inside annotations.
- When admins change schedules, transactions update schedules/jobs per policy.
- The next tick claims only jobs now due.
- Across process restarts, pending rows remain in the database.
- If a tick is skipped, the next tick still picks up due jobs.

### 10.1. @Scheduled does not coordinate multiple instances automatically

With three replicas, `@Scheduled` methods run on all three. That works fine when claiming via atomic SQL `SKIP LOCKED`, but breaks badly if each replica runs:

~~~java
repository.findAllDueJobs()
        .forEach(job -> sender.send(job));
~~~

without claiming, leases, or idempotency.

### 10.2. Changing dispatcher interval differs from changing business schedules

`app.mail.dispatch-delay=PT5S` controls **polling frequency**. Changing it to `PT10S` may require restarting or refreshing the scheduler depending on Spring config; it **does not** change send times stored in `scheduled_at`.

Do not confuse the two:

~~~text
Dispatch interval: check the DB every 5 seconds.
Business schedule: send email at 10:00 on November 15.
~~~

Changing the interval tunes worker cadence; changing a business schedule updates persisted domain data.

## 11. TaskScheduler and Safe Task Cancellation

`TaskScheduler` helps register dynamic triggers inside a JVM. However, if tasks live only in `ScheduledFuture`, restarts lose them.

A safer pattern:

~~~text
Database:
  mail_schedule + durable mail_request

TaskScheduler:
  only wakes dispatcher or triggers occurrence calculation

When the schedule changes:
  1. Commit new schedule version to DB.
  2. Refresh/re-register JVM trigger if needed.
  3. New trigger re-reads DB before materializing work.
  4. Already-created jobs remain in DB.
~~~

Even if `ScheduledFuture.cancel(false)` returns `true`, it does not prove the old task did not already create jobs or call SMTP. If the callback already started, rely on schedule-version checks and idempotent occurrence generation.

### 11.1. Cancelling a ScheduledFuture does not cancel an email

~~~java
boolean cancelled = scheduledFuture.cancel(false);
~~~

Its return value reflects only future state under Java concurrency semantics. It does not automatically:

- remove mail already submitted to SMTP;
- retract emails created in the database;
- cancel retry jobs;
- write audits;
- stop another worker.

Therefore, user-facing "cancel send request" APIs must update the **durable `mail_request`** with proper status and preconditions.

## 12. Quartz With JDBC JobStore

For systems with complex schedules, multiple nodes, and persisted triggers, **Quartz** is an option. `JDBC JobStore` stores jobs/triggers in a database and supports clustering when configured, reducing single-JVM dependency.

Still distinguish:

- **Quartz job/trigger:** describes logical firing timing.
- **Application mail request:** per-recipient send request with payload, status, and retries.

Updating a Quartz trigger does not automatically update or remove already-materialized mail requests. If business rules require moving pending jobs, enforce that policy at the application layer.

### 12.1. Rescheduling a cron trigger

Quartz API example:

~~~java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.TriggerBuilder;
import org.quartz.TriggerKey;

public class QuartzScheduleUpdater {
    private final Scheduler quartz;

    public QuartzScheduleUpdater(Scheduler quartz) {
        this.quartz = quartz;
    }

    public void update(
            TriggerKey triggerKey,
            JobKey jobKey,
            String cron,
            String timeZoneId) throws Exception {

        CronScheduleBuilder schedule =
                CronScheduleBuilder.cronSchedule(cron)
                        .inTimeZone(TimeZone.getTimeZone(timeZoneId))
                        .withMisfireHandlingInstructionDoNothing();

        CronTrigger replacement = TriggerBuilder.newTrigger()
                .withIdentity(triggerKey)
                .forJob(jobKey)
                .withSchedule(schedule)
                .build();

        quartz.rescheduleJob(triggerKey, replacement);
    }
}
~~~

Using `withMisfireHandlingInstructionDoNothing()` shows just **one** misfire choice: discard missed firings and compute the next future fire. **Do not default to this for all use cases.** Mandatory invoices, reports, or alerts may need explicit catch-up; marketing may skip stale runs.

When production maintains both `mail_schedule` tables and Quartz JobStore, decide which is the **source of truth**. Updating two stores outside a shared transaction can drift; use outbox/reconciliation or a controlled synchronization mechanism.

### 12.2. Misfires can look like lost requests

A "misfire" occurs when a trigger misses its scheduled time due to a paused scheduler, node restart, or overload. Policies can:

- catch up missed occurrences;
- skip overdue occurrences;
- fire once to catch up and resume.

Picking the wrong misfire policy can dump bursts of newsletters after an outage or drop critical notices. Define per category:

~~~text
Missed marketing newsletter:
  may skip if campaign window expired.

Missed monthly invoice:
  must generate all required invoices/emails, even if late.

Missed OTP:
  do not send if token already expired.
~~~

Never apply one blanket misfire policy to every email category.

## 13. Timezones, DST, and Changing Timezones

Schedules are often entered in **local time**, while databases and workers compare absolute instants.

Example:

~~~text
User selects:
  09:00 Asia/Ho_Chi_Minh on 2026-11-15

Persist:
  timezone_id=Asia/Ho_Chi_Minh
  local_send_time=09:00 (if needed for display/rules)
  scheduled_at=<computed UTC Instant>
~~~

Never store only the string `2026-11-15 09:00` without a timezone, as two tenants in different regions expect different UTC instants.

### 13.1. DST causes nonexistent or repeated local times

In some timezones, during seasonal transitions:

- 02:30 may **not exist** on spring-forward day;
- 01:30 may occur **twice** when clocks fall back.

A recurring "02:30 daily" schedule needs an explicit policy:

- skip nonexistent times;
- shift to the next valid time;
- pick the earlier or later offset on repeated times;
- or apply a custom domain rule.

Never store a fixed `+07:00` offset for a tenant in `America/New_York` expecting it to match local time year-round.

### 13.2. Changing timezone is a semantic schedule change

Changing "09:00 daily `Asia/Ho_Chi_Minh`" to "09:00 daily `Europe/Paris`" changes UTC fire times. That is a **schedule modification**, requiring versioning and a policy for pending occurrences.

If a user only changes their **UI display timezone**, never alter `scheduled_at` on already-scheduled jobs. Distinguish:

~~~text
DISPLAY_TIMEZONE_CHANGED
SCHEDULE_TIMEZONE_CHANGED
~~~

### 13.3. Use Clock in code

~~~java
import java.time.Clock;
import java.time.Instant;

Instant now = clock.instant();
~~~

Injecting `Clock` enables testing before/after schedule boundaries without `Thread.sleep(...)` or relying on CI machine wall clocks.

For crons, use `ZoneId` and a parser matching your Spring/Quartz version to compute next fire times; never add `Duration.ofDays(1)` for "09:00 daily" schedules in DST zones.

## 14. Quiet Hours, Consent, and Deadlines When Rescheduling

Moving a send time can push an email into restricted hours or past its validity window.

### 14.1. Quiet hours

Example marketing policy:

~~~text
Do not send promotions between 22:00 and 08:00 in the tenant's timezone.
~~~

If an admin moves a campaign from 20:00 to 23:00, the app should:

- reject the new time;
- or propose the next allowed hour;
- or clearly show the active policy.

Never silently violate quiet hours merely because the row was already `PENDING`.

### 14.2. Consent can change while waiting

A recipient was subscribed when the job was created, then unsubscribes before send time:

~~~text
10:00 Newsletter job scheduled for 16:00.
11:00 Recipient unsubscribes.
16:00 Worker prepares to send.
~~~

Workers must **re-check eligibility/opt-outs** at send time per policy; an existing job never grants permanent permission to send. When no longer eligible, record `SUPPRESSED` or `CANCELLED_BY_POLICY` with an audit instead of deleting without trace.

### 14.3. Expiry/deadlines

An OTP email has `expires_at`:

~~~text
created_at    10:00
scheduled_at  10:01
expires_at    10:05
~~~

If rescheduled to 11:00, sending an expired OTP is useless and confusing. Instead:

- reject reschedules violating expiry;
- or transition the job to expired/cancelled per policy;
- or issue a fresh OTP request if the business use case permits.

Never extend a security token's lifetime merely by editing `scheduled_at` without proper verification workflows.

## 15. Email Content: Snapshot or Render at Send Time?

When a request waits for hours, underlying data can change.

Suppose an invoice email scheduled for 09:00 is moved to 15:00. Meanwhile:

- recipient contact details may change;
- invoice amounts or status may be adjusted;
- templates may advance to a new version;
- links/tokens may expire;
- attachments may be purged by retention.

Two options:

| Approach | Pros | Risks |
| --- | --- | --- |
| **Snapshot content at job creation** | Sends exact committed content; easy to audit | Can go stale, tokens expire, uses storage |
| **Render at send time** | Uses latest data, easy template updates | Content differs from scheduling preview; breaks if source records deleted |

Neither is universally right. Classify by business domain:

- Invoices may require an immutable snapshot of the issued document.
- Newsletters may render from the approved campaign.
- OTPs/tokens must bind to validity windows and re-issuance rules.
- Status notices may need live state checks before sending to avoid wrong messages.

### 15.1. Do not let temporary attachments expire before the new time

If a job holds a `payload_ref` to a temporary file:

~~~text
File retention: 24h
Reschedule job: from 12h to 72h
~~~

The worker will miss the file when send time arrives. Before rescheduling, verify the **lifetime** and access permissions of payloads/attachments. Use durable object storage with matching retention, or safe regeneration policies when appropriate.

### 15.2. Template versions should be audited

If content renders at send time, store template ID/version or version-selection rules. When a sent email differs from the preview seen at scheduling, support needs to know why.

Never create a separate metric label per dynamic template version; store that detail in the job/audit event store.

## 16. Rescheduling Mid-Way Through a Large Campaign

A campaign targets 500,000 recipients with 300,000 mail requests still pending. Updating all rows in one transaction can:

- lock huge numbers of rows for a long time;
- stall workers;
- cause WAL/replication lag;
- trigger deadlocks or timeouts;
- freeze the admin UI.

Large-scale rescheduling requires a durable **rescheduling operation**:

~~~text
reschedule_operation:
  operationId=op-123
  scheduleId=campaign-88
  oldVersion=4
  newVersion=5
  policy=MOVE_UNSTARTED
  status=IN_PROGRESS
  rowsPlanned=300000
  rowsChanged=...
  cursor=...
~~~

### 16.1. Transitioning in batches

Example:

1. Persist the new version and create the reschedule operation.
2. Pause new claims **within the target scope** or add an effective-version predicate on the dispatcher.
3. Update eligible jobs in small cursor-based idempotent batches.
4. Track progress and affected counts; never delete jobs.
5. Once complete, reopen dispatching for that scope.
6. Report actual counts: moved, skipped as claimed/sent, retrying, invalid, cancelled.

**Use a real synchronization protocol** across pause, reschedule, and dispatch—never a boolean in RAM. Use DB-persisted schedule state, leases, or schedule-version claim predicates so all pods obey.

### 16.2. Never assume "100% updated"

While the operation runs, some jobs may:

- get claimed by a worker right before the cutover boundary;
- already be submitted;
- enter retry;
- expire;
- get unsubscribed or cancelled.

Dashboards should display:

~~~text
Requested reschedule: 300.000
Moved:                298.740
Skipped in-flight:        110
Skipped submitted:        900
Skipped retry:            250
~~~

Figures are illustrative. Report per-group reasons and audit details; never claim "300,000 succeeded" if only 298,740 actually moved.

### 16.3. Ensure resumability if the process crashes

If the reschedule operation is a durable job, a restarted process can resume from the cursor. Batches must be idempotent: re-running a batch must never add hours twice or corrupt schedule versions.

Avoid:

~~~text
scheduled_at = scheduled_at + INTERVAL '1 hour'
~~~

running unconditionally on retry after a crash, which can turn into **+2 hours**. Instead, use an explicit target timestamp defined by the operation, or predicate `schedule_version = oldVersion` so each row moves at most once.

## 17. Recovering After Downtime and Missed Schedules

Suppose the server is down for 45 minutes while many jobs become due.

When the app restarts:

~~~text
Pending rows in DB: still intact.
Dispatcher tick: queries scheduled_at <= now.
Worker: claims and processes per deadline/policy.
~~~

That is the value of a durable job store: **requests do not vanish merely because ticks were missed**.

### 17.1. Catch up or skip?

Not every overdue email should be sent:

| Email type | Potentially appropriate policy |
| --- | --- |
| Critical invoice | Catch up, record lateness |
| Order confirmation | Catch up if still meaningful |
| Expired OTP | Never send expired codes |
| Daily digest | Coalesce or skip per product rule |
| Time-limited promo | Skip if campaign expired |
| Appointment reminder | Do not send "starting soon" after the event ended |

Never treat **an existing pending row** as sufficient reason to send anything regardless of deadlines and consent.

### 17.2. Never recreate the same occurrence on restart

A scheduler scanning past `next_fire_at` values might attempt to create the same occurrence across restarts. Unique occurrence keys and transactions prevent generating the same job twice.

Log such incidents clearly:

~~~text
Missed occurrence identified.
Occurrence already exists -> no-op / reconcile missing recipients.
Occurrence not created -> materialize according to catch-up policy.
~~~

Never blindly bump `next_fire_at = now + interval` and ignore older occurrences without knowing whether they are business-critical or skippable.

## 18. Admin API for Safe Rescheduling

An API might require:

~~~http
PATCH /api/mail-schedules/98b.../timing
If-Match: "version-7"
Idempotency-Key: 5db2...
Content-Type: application/json

{
  "newSendAt": "2026-11-15T04:00:00Z",
  "policy": "MOVE_UNSTARTED",
  "reason": "Moving campaign to afternoon"
}
~~~

This is an illustrative contract, not a built-in Spring Mail API. The backend must:

- verify tenant-scoped admin authorization;
- validate timestamps, timezones, crons, deadlines, and quiet hours;
- verify current version (optimistic concurrency);
- validate the idempotency key;
- compute an **impact preview**;
- execute a transaction or create a batch operation;
- return actual moved/skipped counts;
- audit actor, before/after state, and reason.

### 18.1. Preview before committing

UI example:

~~~text
You are changing the send time from 10:00 to 11:00.

Requests:
  620 pending, eligible to move
   30 retrying, will keep existing retry schedule
   20 in flight, cannot guarantee recall
  130 already submitted, unchanged

Policy: move unstarted requests only.
~~~

A preview is a point-in-time snapshot. By commit time, numbers may shift as workers run; the backend must return **actual affected counts** and skip reasons rather than treating the preview as a guarantee.

### 18.2. API must separate updates from cancellations

Do not conflate:

~~~text
PUT /schedule/{id} { enabled: false }
~~~

with "cancel all pending emails" unless the contract says so. Disabling a schedule may mean only **stop generating new occurrences**, while cancelling pending jobs is a separate action.

Example:

~~~text
DISABLE_SCHEDULE: stop generating new occurrences.
CANCEL_UNSENT: cancel eligible unsent jobs.
RESCHEDULE_UNSTARTED: move unstarted jobs.
~~~

Each action should have its own permissions, policy, audit, and user-facing messaging.

## 19. Multiple Workers and Concurrent Schedule Edits

A timeline:

~~~text
09:59:58 Worker A claims job #101.
09:59:59 Admin reschedules from 10:00 to 11:00.
10:00:00 Worker B polls due jobs.

Job #101:
  already CLAIMED before cutover; not moved automatically.

Job #102:
  still PENDING when admin transaction locks/updates.
  scheduled_at updated to 11:00.

Worker B:
  sees #102 is not yet due; does not send.
~~~

If Worker A has not actually sent yet, you can add `cancel_requested` and a pre-send check to try stopping it. Never promise **100% cancellation of in-flight mail** because SMTP side effects can begin between checking and sending.

### 19.1. Do not let retry workers bypass the new schedule

A bug:

~~~text
Main queue checks scheduled_at.
Retry queue checks only next_attempt_at.
Admin moves scheduled_at to 11:00.
Retry worker sends at 10:06 even though policy wanted everything held until 11:00.
~~~

If product policy applies the new time to retries as well, the dispatcher must enforce:

~~~text
now >= scheduled_at AND now >= next_attempt_at
~~~

Clarify upfront whether new schedule times apply to retry jobs. Never alter retry semantics accidentally.

### 19.2. Do not let the scheduler spawn new jobs while rescheduling the same occurrence

If the materializer and an admin operation run concurrently, use row locks, versions, or operation status to enforce consistent ordering. Never rely solely on "a per-JVM thread lock": multiple replicas do not share Java `synchronized` or `ReentrantLock`.

## 20. Metrics, Audits, and Alerts

Useful metrics:

| Suggested metric | Purpose |
| --- | --- |
| `mail_schedule_changes_total` | Schedule edits by policy/result |
| `mail_reschedule_jobs_moved_total` | Jobs actually moved |
| `mail_reschedule_jobs_skipped_total` | Jobs unable to move, by reason |
| `mail_reschedule_operation_duration_seconds` | Operation completion time |
| `mail_pending_jobs` | Pending job count |
| `mail_oldest_eligible_pending_age_seconds` | Oldest eligible unclaimed job age |
| `mail_submission_attempts_total` | Transport attempt count |
| `mail_jobs_expired_total` | Jobs dropped past deadline per policy |
| `mail_schedule_occurrence_deduplicated_total` | Materializer hits on already-existing occurrences |
| `mail_claim_lease_expired_total` | Leases needing recovery |
| `mail_unknown_submission_total` | Attempts with unknown outcomes |

These are names **an application can instrument itself**, not built-in metrics supplied automatically by Spring Framework Mail.

### 20.1. Bounded labels

Suitable labels:

~~~text
mail_type=otp|invoice|newsletter|order_confirmation
policy=keep_existing|move_unstarted|cancel_unsent
result=success|conflict|validation_failed|partial
skip_reason=claimed|submitted|retry_wait|expired|cancelled
~~~

Never put job IDs, high-cardinality tenant IDs, recipient emails, raw reasons, or message content in metric labels. Per-job/tenant details belong in an access-controlled audit database.

### 20.2. Rescheduling dashboard

A view:

~~~text
Schedule: Campaign 88
Current version: 5
Old timing: 10:00
New timing: 11:00

Operation status: COMPLETED
Eligible before:  50.000
Moved:            49.200
Skipped in-flight:   250
Skipped retry:       300
Skipped other:       250

Pending at new time: 49.200
Old pending remaining: review 300 (retry policy)
~~~

Numbers are illustrative. Dashboards should show last-updated timestamps and **actual counts**, not just preview estimates.

### 20.3. Alerts

- Reschedule operation stuck `IN_PROGRESS` too long or making no progress.
- Schedule enabled yet due occurrences fail to materialize.
- Pending backlog keeps climbing after a reschedule.
- Moved jobs dispatched **before `scheduled_at`**.
- Unknown or duplicate attempts spiking after cutover.
- Missing audit event for a critical schedule change.
- Expired emails still getting submitted.

Investigations need job/occurrence/operation correlation IDs without dumping full email bodies or secrets into logs.

## 21. Testing With Fixed Clocks and Competing Workers

Rescheduling tests must verify **data survives and never sends at the wrong time**, not merely HTTP 200.

### 21.1. Policy unit tests

With `Clock.fixed(...)`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T03:00:00Z"),
        ZoneOffset.UTC);
~~~

Test cases:

1. `PENDING`, `attempt_count=0`, unclaimed → rescheduled cleanly.
2. `RETRY_WAIT` → keeps retry timing under `MOVE_UNSTARTED`.
3. `CLAIMED` → not moved, counted in skipped.
4. `SUBMITTED` → never moved or "resent".
5. `UNKNOWN` → never blindly retried.
6. Schedule version already changed → conflict, no overwrite.
7. Repeated reschedule request with same idempotency key → returns prior result.
8. New time violates deadline/quiet hours → policy validation rejects.
9. `KEEP_EXISTING` → pending jobs unchanged.
10. `CANCEL_UNSENT` → transitions status without deleting rows.

### 21.2. Integration tests with a real database

`SELECT ... FOR UPDATE SKIP LOCKED` and transaction isolation must be tested on PostgreSQL/Testcontainers matching production. Mock repositories cannot prove race safety.

A critical concurrency test:

~~~text
Transaction A: admin reschedule.
Transaction B: worker claims same job.

Run repeatedly with interleaved ordering:
  - A commits first -> B does not claim when new time is still future.
  - B claims first -> A skips CLAIMED job.

Never observe:
  a job missing from DB;
  a job both moved and claimed early;
  one occurrence spawning two mail requests for the same recipient.
~~~

### 21.3. Crash/restart tests

Scenario:

1. Seed 100 pending mail jobs.
2. Reschedule a subset per policy.
3. Kill process mid-batch or right after DB commit.
4. Restart workers and scheduler.
5. Verify pending jobs still exist.
6. Operation resumes idempotently without double-shifting hours.
7. Workers claim only due jobs.
8. Duplicate occurrence requests are blocked by unique constraints.

### 21.4. SMTP tests using GreenMail/Mailpit

Test against a simulated SMTP server:

- before the new time: mailbox contains no matching message;
- after the new time: job submits per policy;
- worker retries create no extra logical jobs;
- cancelled jobs are never sent;
- temporary SMTP errors do not delete jobs;
- attempt states record simulated timeouts accurately.

For async workflows, await conditions with a timeout instead of `Thread.sleep(...)`. Negative assertions ("not sent") must wait until worker ticks/claims would have run and the app reaches an observable state; checking an empty mailbox immediately is insufficient.

### 21.5. Cron and DST tests

Cases:

- Moving from Monday to Tuesday in the same week creates no second occurrence under a one-newsletter/week contract.
- Changing timezone updates UTC fire times accurately.
- DST gaps/overlaps obey published rules.
- Downtime missing two occurrences catches up or skips per mail type.
- Disabling a schedule stops new occurrences while keeping old pending jobs if policy demands.

### 21.6. Cleaning up test fixtures

Integration tests should clean up:

- SMTP test mailboxes/servers;
- test schedule/occurrence/request/attempt/audit rows;
- background workers and retry tasks;
- temporary attachment files;
- leases and job states;
- container/port resources.

Never purge shared queues/mailboxes when tests run in parallel; isolate by ID/namespace.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing schedules only in `ScheduledFuture` | Restarts lose waiting tasks | Durable schedule/job store |
| Deleting old cron means deleting all pending jobs | Unintended request loss | Separate definitions and requests |
| Deleting old jobs and creating new ones on reschedule | Duplicates, lost audit/IDs | Update eligible jobs in place |
| `UPDATE` all jobs where `sent=false` | Corrupts retry, claimed, unknown | State machine + explicit predicates |
| Editing `next_attempt_at` as business schedule | Broken backoff or infinite delay | Separate `scheduled_at` and retry time |
| Shifting all recurring occurrences to one hour | Collapses distinct periods | Version schedules + per-occurrence policy |
| Putting `schedule_version` in unique key instead of occurrence | Rescheduling causes duplicates | Stable occurrence key + recipient |
| No locking/version check between admin and worker | Early sends or lost updates | Transactions + atomic claims |
| Holding DB locks across SMTP calls | Lock contention, pool exhaustion | Claim/commit, send, ack |
| Resetting all `SUBMITTING` after crash | Potential duplicates | `UNKNOWN`/reconciliation |
| Multiple `@Scheduled` pods reading same row | Duplicate dispatch | `SKIP LOCKED`/leases/dedup |
| Ignoring timezones/DST | Hour drift or duplicate occurrences | `ZoneId` + DST policy |
| Rescheduling after OTP expiry | Useless notifications | Deadline validation |
| Skipping marketing opt-out checks at send time | Emails unsubscribed users | Revalidate consent at dispatch |
| Rescheduling 500,000 rows in one transaction | Long locks, poor recovery | Versioned batch operations |
| Batch rescheduling via repeated `scheduled_at + interval` | Crash/retry shifts time multiple times | Absolute targets + version guards |
| Counting only cron ticks | Misses lost or delayed pending mail | Job backlog, age, audit metrics |
| Not auditing who rescheduled | Hard to explain or recover | Before/after, actor, policy, counts |
| Using Quartz misfire `DoNothing` for mandatory mail | Drops required occurrences | Per-mail-type catch-up/skip |

## 23. End-to-End Scenario: Rescheduling a Weekly Newsletter

A tenant currently has:

~~~text
Schedule: weekly-newsletter-tenant-a
Rule v4: MON 09:00 Asia/Ho_Chi_Minh
Occurrence: 2026-W46

Mail requests already created for W46:
  8.000 PENDING
    100 CLAIMED
     80 RETRY_WAIT
    820 SUBMITTED
~~~

The administrator wants to move to **TUE 10:00**.

### 23.1. Step 1 — Choose semantics

If the new schedule should apply starting next week:

~~~text
Policy = REPLAN_FUTURE_OCCURRENCES

Already-created W46:
  keep requests and states unchanged

W47 onward:
  calculate using TUE 10:00
~~~

This is usually the least surprising choice for recurring schedules.

If the business wants to move part of already-created W46, require selecting the **specific occurrence** with `MOVE_UNSTARTED` rather than mutating every week at once.

### 23.2. Step 2 — Preview impact

~~~text
Target occurrence: 2026-W46
Eligible PENDING never attempted: 8.000
In-flight: 100
Retry: 80
Already submitted: 820

Proposed:
  Move 8.000 requests to new instant.
  Keep in-flight/ retry / submitted unchanged.
~~~

Previews can shift while workers run. The commit API must return actual counts.

### 23.3. Step 3 — Execute cutover

1. Verify permissions and schedule version.
2. Commit schedule version v5 and an operation ID.
3. If moving a batch, pause new claims scoped to W46 during transition.
4. Move `PENDING`/unattempted jobs while preserving request IDs.
5. Audit moved and skipped counts.
6. Lift the dispatcher pause and recalculate `next_fire_at`.

Workers send only when both `scheduled_at` and retry eligibility pass. Never resend `SUBMITTED` merely because a schedule changed.

### 23.4. Step 4 — Verify

After cutover:

- All mail request rows accounted for; none silently deleted.
- Actual moved count matches audit logs.
- Moved jobs are never sent before the new time.
- Retry jobs follow published policy.
- Occurrence W46 is never generated twice.
- Backlogs and metrics reflect true state.

**Scenario takeaway:** changing the timing of a **schedule definition** and changing the timing of **already-materialized mail requests** are two distinct operations. Perform both only when the product explicitly requires both, using clear transactions, state filters, and audits.

## 24. Pre-Production Checklist

### Architecture

- [ ] Schedule definitions and durable mail requests are separate entities.
- [ ] Recurring schedules have stable occurrence identities.
- [ ] Mail jobs have domain-appropriate unique/idempotency keys.
- [ ] Pending jobs survive restarts and deployments.
- [ ] Worker claiming uses DB locking/leases safe across replicas.

### Rescheduling

- [ ] Explicit policy defined: `KEEP_EXISTING`, `MOVE_UNSTARTED`, `CANCEL_UNSENT`, or replan future occurrences.
- [ ] UI/API previews potentially affected job counts.
- [ ] Modifies only jobs eligible by state, attempts, and claim status.
- [ ] Retry timing, deadlines, and scheduled times remain separate.
- [ ] Optimistic versioning, idempotency keys, and audits in place.
- [ ] Large batch operations support resumption.

### Correctness

- [ ] Pending jobs are never deleted merely because cron/trigger changed.
- [ ] Same occurrence never regenerates on version change.
- [ ] SMTP timeouts are never assumed definitely unsent.
- [ ] In-flight and submitted jobs are never mutated arbitrarily.
- [ ] Cancelled jobs never resurrect automatically.
- [ ] Consent, quiet hours, and token expiry are checked at dispatch.
- [ ] Payloads and attachments remain valid until send time.

### Time and operations

- [ ] IANA timezones and UTC/`Instant` timestamps stored properly.
- [ ] Explicit policies exist for DST gaps/overlaps and downtime misfires.
- [ ] Backlogs, oldest eligible age, moved/skipped counts, and unknown outcomes monitored.
- [ ] Runbooks exist for stuck reschedules and expired worker leases.
- [ ] Concurrency, restart, and time-shift tests run against a real DB.
- [ ] SMTP sandbox tests and fixture cleanups implemented.

## 25. Key Takeaways

- **Changing a schedule must never default to deleting already-waiting requests.**
- Separate **schedule definitions**, **occurrences**, and **durable mail requests**.
- For recurring schedules, usually **keep already-created occurrences** and recompute only future ones.
- For one-time schedules, when users truly move the time, shift **unstarted `PENDING` jobs** while preserving IDs.
- `RETRY_WAIT`, `CLAIMED`, `SUBMITTING`, `SUBMITTED`, and `UNKNOWN` carry distinct semantics; never bulk-update via `sent=false`.
- `@Scheduled` or `TaskScheduler` can wake dispatchers, **not serve as the pending-job store**.
- Quartz/JDBC JobStore persists triggers, not full business mail-request lifecycles.
- Atomic claiming, optimistic versioning, unique occurrence keys, and auditing protect against races and duplicates.
- `scheduled_at`, `next_attempt_at`, and `lease_until` must keep separate meanings.
- An already-sent SMTP submission cannot be recalled merely by cancelling a task or updating the DB.
- New schedules must respect timezones/DST, quiet hours, consent, deadlines, and payload lifetimes.
- For large job counts, use resumable rescheduling operations rather than locking entire tables.

Reliable practice in Spring Framework Mail keeps **send requests in the database**, lets the scheduler decide when to generate or wake work, and lets workers claim only genuinely due requests. When users reschedule, the system alters **only the permitted scope**, preserves waiting request states, reports unmovable jobs honestly, and resumes cleanly after failures or restarts. Thus rescheduling becomes a controlled business operation rather than an action that accidentally drops or duplicates emails.

### References

- **Spring Framework Reference — Task Execution and Scheduling:** `@Scheduled`, `TaskScheduler`, and `Trigger`.
- **Spring Framework API — CronTrigger, CronExpression:** scheduling and computing next execution times.
- **Spring Framework Reference — Transaction Management:** `@Transactional` and transaction boundaries.
- **Spring Data JPA Reference:** optimistic/pessimistic locking and `@Version` when using JPA.
- **Spring Framework Reference — Email:** `JavaMailSender` and transport submission.
- **Quartz Scheduler Documentation:** `CronTrigger`, `Scheduler.rescheduleJob`, JDBC JobStore, clustering, misfire instructions.
- **PostgreSQL Documentation:** `SELECT ... FOR UPDATE SKIP LOCKED`, conditional `UPDATE`, unique indexes, and transaction isolation.
- **Java Platform — java.time:** `Instant`, `Clock`, `ZoneId`, and `ZonedDateTime`.
- **RFC 5321 — Simple Mail Transfer Protocol:** submission outcomes and SMTP delivery guarantee limits.
- **Documentation of your active ESP:** rate limits, delivery events, provider idempotency, and submission lookups when outcomes are uncertain.

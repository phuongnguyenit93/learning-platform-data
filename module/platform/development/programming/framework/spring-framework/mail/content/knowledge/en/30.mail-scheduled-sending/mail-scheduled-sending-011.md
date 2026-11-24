# Tracking Send Jobs and Runs

In **Spring Framework Mail**, an email sending feature can start from a business event, an HTTP request, or a scheduled task. In a system with **@Scheduled**, multiple workers, transactional outbox, and retry, seeing a log stating "job ran" is not enough to conclude that every email was sent properly. A single scheduler run can process hundreds of mail events, an event can be tried via SMTP multiple times, and a successful SMTP return does not prove the message reached the recipient's inbox.

**Tracking send jobs and runs** aims to record verifiable execution history: which job was triggered, when it actually ran, on which instance, how many events it claimed, how many succeeded, where errors occurred, whether any job is stuck or missed its schedule, and what needs to be retried.

This lesson belongs to the **Scheduled Sending** chapter in the **Spring Framework Mail** topic. The content covers the job/run/outbox/attempt model, states, database schema, Spring Scheduling, distributed coordination, transaction boundaries, Micrometer, structured logs, tracing, Prometheus, dashboards, alerting, recovery, and testing.

Key principles:

- A **job definition** is not a **job run**; a run is not a single email.
- A **mail event** is not an **SMTP attempt**; retries can create multiple attempts for a single event.
- A successful run may only indicate that the **dispatcher finished its work**, not that every email was delivered.
- Distinguish scheduled time, actual start, queue delay, run duration, and SMTP send-call duration.
- With multiple workers, atomic outbox claims/leases are required; `@Scheduled` alone does not guarantee mutual exclusion across nodes.
- A crash after the SMTP relay has accepted the message but before updating the database can create a **duplicate window**.
- Metrics show trends; logs/traces support investigation; durable run and attempt records support post-crash reconciliation.

## 1. Four Distinct Tracking Units

| Unit | Description | Example |
| --- | --- | --- |
| **Job definition** | Schedule/dispatcher definition | mail-outbox-dispatcher |
| **Job run** | One specific execution | run-001 |
| **Mail event** | Durable sending intent from business logic | ORDER_CONFIRMED:1001 |
| **SMTP attempt** | One send attempt via JavaMailSender | attempt-003 |

Diagram:

~~~text
Job: mail-outbox-dispatcher
       |
       +--- Run R1
       |       |
       |       +--- Event A -> Attempt A1 -> success
       |       +--- Event B -> Attempt B1 -> retryable error
       |       +--- Event C -> Attempt C1 -> success
       |
       +--- Run R2
               |
               +--- Event B -> Attempt B2 -> success
               +--- Event D -> Attempt D1 -> success
~~~

A run processes multiple mail events; an event can be processed across multiple runs; each event can have multiple SMTP attempts.

### 1.1. Job Definition

This may include cron/fixedDelay, timezone, batch size, concurrency, an enabled flag, and a routing policy.

### 1.2. Run Identifier

Whenever the scheduler actually starts an execution, assign a new `runId`. If triggered manually, that is also a separate execution.

### 1.3. Event Identifier

`MailEventId` must remain stable across retries for the same sending intent. Business idempotency helps avoid creating multiple events from a duplicated business action.

### 1.4. Attempt Identifier

Each actual call to the SMTP transport has its own `attemptId`, provider, start/end timestamps, and outcome.

## 2. Why Simple Start/Finish Logs Are Misleading?

Example:

~~~java
@Scheduled(fixedDelayString = "5000")
public void sendPending() {
    log.info("Mail job started");

    for (MailJob job : repository.findPending()) {
        mailSender.send(buildMessage(job));
    }

    log.info("Mail job finished");
}
~~~

The code lacks a `runId`, does not measure duration, does not know the processed count, does not record attempt history, and does not distinguish having no work from a database error. If the sender throws an exception, the finished log does not run. If two instances execute `SELECT PENDING` at the same time, both can send the same mail event.

We need to design a tracking mechanism with clear boundaries and states.

## 3. End-to-End Tracking Architecture

~~~text
Cron / fixedDelay / manual trigger
                |
                v
       Record job run STARTED
                |
                v
      Optional scheduler lock
                |
                v
   Atomic claim eligible outbox rows
                |
                v
    Validate / Render / Build MIME
                |
                v
       Create SMTP attempt
                |
                v
      JavaMailSender.send(...)
                |
        +-------+-------+
        |       |       |
     Success  Failure  Unknown
        |       |       |
        v       v       v
   Outbox state transition
                |
                v
      Finalize run summary
                |
                v
       Metrics / logs / traces
~~~

Each step answers a different question. The scheduler may finish enqueuing into a durable queue before SMTP runs; in that case, make it explicit that the run finished **enqueuing**, not sending.

## 4. Required IDs

A naming convention:

~~~text
jobName     = mail-outbox-dispatcher
runId       = UUID for one execution
mailEventId = durable UUID for one business intent
attemptId   = UUID for one SMTP submission
workerId    = node/process instance alias
traceId     = distributed tracing context
~~~

Do not mix the IDs:

- `RunId` is used to inspect a single scheduled execution.
- `MailEventId` is used to reconcile retries of a single sending intent.
- `AttemptId` is used to diagnose a specific SMTP call.
- `WorkerId` is used to detect a failing instance.
- `TraceId` is used to link steps in telemetry, not to replace a business ID.

**Do not put `runId`, `mailEventId`, `attemptId`, or recipient into metric labels**: these values have very high cardinality and can link to private information.

## 5. Job Run Lifecycle

A suggested state machine:

~~~text
SCHEDULED (if the system stores planned triggers)
      |
      v
STARTING
      |
      +-- cannot acquire lock -> SKIPPED
      |
      v
RUNNING
      |
      +-- no due events -> SUCCEEDED_EMPTY
      |
      +-- all work done -> SUCCEEDED
      |
      +-- mixed outcomes -> PARTIAL
      |
      +-- infrastructure error -> FAILED
      |
      +-- cancelled -> CANCELLED
      |
      +-- crash / no heartbeat -> STALE
~~~

These states are an **application-defined convention**, not a default enum in `JavaMailSender`.

### 5.1. `SUCCEEDED_EMPTY` Is Not an Error

A run that properly checks the queue and finds no due mail events is a valid run. It helps distinguish a live scheduler from one that is not running.

### 5.2. `PARTIAL` Has Contract-Based Semantics

If a run sends 80 emails and puts 20 into `RETRY_WAIT`, you can record `PARTIAL`. If the run's contract is simply "process each event properly and update state," a run can also be `SUCCEEDED` from an orchestration standpoint. The key is to **publish clear status definitions and expose counters**.

### 5.3. `STALE` Does Not Prove SMTP Did Not Send

A process that crashed before recording its result may have already sent part of the batch successfully. Do not replay the entire run based on the `STALE` status.

### 5.4. Skipped Triggers May Not Create a Run

If ShedLock blocks the method before code inside runs, no run record is created inside the method. To measure skipped triggers, instrument the scheduler/lock provider layer.

## 6. Mail Event Lifecycle

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- submit success --> SENT
   |
   +-- known temporary error --> RETRY_WAIT
   |
   +-- permanent error --> FAILED
   |
   +-- ambiguous SMTP result --> UNKNOWN_OUTCOME
   |
   +-- lease expired --> RECOVERY_ELIGIBLE
~~~

`RECOVERY_ELIGIBLE` can be inferred from `PROCESSING` when `claim_until` has expired.

### 6.1. `SENT` Is a Submission Milestone

`JavaMailSender.send` returning normally typically indicates that the transport call completed from the client's perspective. It **does not prove inbox delivery or read**.

### 6.2. `RETRY_WAIT` Has Its Own Timestamp

`nextAttemptAt` is when the mail event can be retried, not the scheduler's cron schedule.

### 6.3. `UNKNOWN_OUTCOME` Must Be Separated From Certain Failure

The SMTP client may have transmitted `DATA` but lost the final response, so the relay may have accepted the message. Retrying carries a duplicate-send risk.

## 7. Timeline and Count Example

~~~text
10:00 Run R1 starts
10:01 R1 claims A, B, C
10:02 A attempt 1 -> success
10:03 B attempt 1 -> temporary failure
10:04 C attempt 1 -> success
10:05 R1 -> PARTIAL

10:06 Run R2 -> no due events -> SUCCEEDED_EMPTY

10:07 Run R3 claims B after retry deadline
10:08 B attempt 2 -> success
10:09 R3 -> SUCCEEDED
~~~

Total: **3 runs**, **3 unique mail events**, **4 SMTP attempts**, **3 mail events ultimately submitted successfully**, and **1 temporary-failure attempt**.

You cannot call 4 attempts "4 emails delivered."

## 8. Job Definition and Schedule Configuration

An optional table:

~~~sql
CREATE TABLE mail_job_definition (
    job_name VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_type VARCHAR(32) NOT NULL,
    cron_expression VARCHAR(120),
    timezone_id VARCHAR(64),
    batch_size INTEGER NOT NULL DEFAULT 50,
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    config_version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Example schema for PostgreSQL. If the schedule is written with `@Scheduled` annotations and source configuration, this table is not strictly required.

### 8.1. Store Versions or Snapshots

When changing cron, batch size, or concurrency, version metadata explains why older runs processed work differently.

### 8.2. Enabled and Maintenance

Missed-run alerts must distinguish an intentionally disabled job from a dead scheduler.

### 8.3. Timezone

A `09:00` schedule in `Asia/Ho_Chi_Minh` is not equivalent to `09:00 UTC`. Always choose the timezone based on business requirements.

## 9. Database Schema for Job Runs

~~~sql
CREATE TABLE mail_job_run (
    run_id UUID PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    status VARCHAR(32) NOT NULL,
    trigger_type VARCHAR(32) NOT NULL,
    scheduled_for TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    last_progress_at TIMESTAMPTZ,
    instance_id VARCHAR(128),
    config_version INTEGER,
    claimed_count INTEGER NOT NULL DEFAULT 0,
    submit_success_count INTEGER NOT NULL DEFAULT 0,
    submit_failure_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    error_category VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mail_run_by_start
    ON mail_job_run(job_name, started_at DESC);

CREATE INDEX idx_mail_run_stale
    ON mail_job_run(status, heartbeat_at);
~~~

### 9.1. Planned and Actual Are Two Distinct Timestamps

`scheduled_for` should only be stored when the scheduler genuinely provides the planned fire time. If only `started_at` is known, do not round it to fabricate `scheduled_for`.

### 9.2. Heartbeat Differs From Progress

A worker can send heartbeats while stuck on an SMTP socket. `last_progress_at` shows whether any event has actually progressed recently.

### 9.3. Counters Must Have Consistent Definitions

`submit_success_count` can count successful attempts or completed events; choose one meaning and name it clearly. In this article, the example uses **attempt successes within the scope of the run**.

## 10. Storing Outbox Events and SMTP Attempts

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    business_event_key VARCHAR(200) NOT NULL,
    mail_kind VARCHAR(64) NOT NULL,
    recipient_ref VARCHAR(200) NOT NULL,
    payload_ref VARCHAR(300) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_owner VARCHAR(128),
    claim_until TIMESTAMPTZ,
    claim_version BIGINT NOT NULL DEFAULT 0,
    last_run_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_mail_intent
    ON mail_outbox(business_event_key, mail_kind, recipient_ref);

CREATE INDEX idx_mail_ready
    ON mail_outbox(status, next_attempt_at);

CREATE TABLE mail_send_attempt (
    attempt_id UUID PRIMARY KEY,
    mail_event_id UUID NOT NULL REFERENCES mail_outbox(id),
    run_id UUID REFERENCES mail_job_run(run_id),
    attempt_number INTEGER NOT NULL,
    provider_alias VARCHAR(64),
    outcome VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_ms BIGINT,
    error_category VARCHAR(64),
    smtp_reply_code VARCHAR(16),
    UNIQUE(mail_event_id, attempt_number)
);

CREATE INDEX idx_mail_attempt_event
    ON mail_send_attempt(mail_event_id, attempt_number);
~~~

### 10.1. Outbox and Runs Have a Many-to-One-or-More Relationship

`last_run_id` only shows the most recent execution; the attempt table reveals earlier send attempts.

### 10.2. `attempt_number` Must Be Assigned Atomically

Do not compute `MAX(attempt_number) + 1` outside a transaction without race control. Use an atomic counter/locking or unique constraints with appropriate transaction retries.

### 10.3. Do Not Put MIME Bodies Into Observability Tables

`payload_ref` points to snapshots/content managed under privacy and retention policies. Run/attempt records only need operational metadata.

## 11. Timestamps and Durations

Distinguish:

- **scheduledFor:** planned trigger time.
- **triggerObservedAt:** when the scheduler noticed the schedule was due.
- **startedAt:** execution start.
- **finishedAt:** execution end.
- **lastProgressAt:** most recent progress timestamp.
- **nextScheduledFor:** next planned trigger if provided by the scheduler.
- **nextAttemptAt:** retry deadline of the mail event.
- **relayAcceptedAt:** timestamp observed or reconciled when the relay accepted, if available.

### 11.1. Scheduler Lag

If a real planned timestamp exists:

~~~text
scheduler_lag = startedAt - scheduledFor
~~~

If `scheduledFor` is unavailable, record actual execution without fabricating a lag metric.

### 11.2. Use `System.nanoTime` for Elapsed Time

Within a single JVM, `nanoTime` or a Micrometer `Timer` is suitable for measuring duration. Do not subtract `nanoTime` values from two different hosts.

### 11.3. Timestamps Across Multiple Nodes

Use `Instant` or database time to store history, while controlling clock skew between nodes.

## 12. `@Scheduled`: `fixedDelay`, `fixedRate`, and `cron`

~~~java
@Scheduled(fixedDelayString = "5000")
public void pollAfterPreviousCompletion() {
    // ...
}

@Scheduled(fixedRateString = "5000")
public void pollAtRegularRate() {
    // ...
}

@Scheduled(
        cron = "0 */5 * * * *",
        zone = "Asia/Ho_Chi_Minh"
)
public void pollEveryFiveMinutes() {
    // ...
}
~~~

- **fixedDelay:** a wait interval after the previous execution completes.
- **fixedRate:** a periodic target cadence; in practice it is subject to the scheduler executor and execution time.
- **cron:** scheduled calendar points; requires an explicit zone.
- **@Scheduled:** triggers per application instance; it does not provide a distributed mutex by itself.

### 12.1. Cron With DST

In timezones with daylight saving time, a local hour may be skipped or repeated. If each business date requires exactly one meaningful execution, use a dedicated period key/unique constraint.

### 12.2. Manually Triggered Jobs

A manual trigger should also create a run with `trigger_type=manual` and audit the actor according to access-control rules.

## 13. Missed Runs and Catch-Up

Suppose a job is scheduled for 10:00, 10:05, 10:10, but the application is down from 09:58 to 10:12.

### 13.1. `@Scheduled` Does Not Automatically Store Every Missed Tick

A regular `@Scheduled` method has no durable trigger history to replay every missed point during process downtime.

### 13.2. Outbox Polling Can Catch Up on Workload Automatically

A run after restart can pick up mail events that are still `PENDING` or `RETRY_WAIT` and due. You do not necessarily have to run three catch-up cron executions.

### 13.3. Daily Digests and Other Periodic Reports

If each business date needs its own digest, you must track period keys and a catch-up policy so no day is skipped or sent twice.

### 13.4. Quartz or Dedicated Job Schedulers

A scheduler with a job store and misfire handling such as Quartz can provide `scheduledFireTime` or a misfire policy. When used, map that information accurately into the run tracker; do not assume simple Spring `@Scheduled` has those semantics.

## 14. Recording the Run Record Before Processing

When the scheduler starts:

~~~text
runId       = new UUID
jobName     = mail-outbox-dispatcher
status      = RUNNING
triggerType = scheduled
startedAt   = current database time
instanceId  = mail-worker-node-3
~~~

Write the run record in a **short, committed transaction** before claiming/sending. If the worker dies, the `RUNNING` record remains for a sweeper to detect `STALE`.

### 14.1. Write Finish in a Separate Transaction

The run finish is updated after the summary. Do not hold a transaction open across an SMTP network call.

### 14.2. Separate the Tracker From the Business Transaction

If the dispatcher rolls back due to an error, you still want the run failure record. A dedicated `JobRunTracker` Spring bean with an independent transaction is a useful pattern.

### 14.3. Do Not Create One Run Per Email

A run is one scheduler/dispatcher execution; a mail event/attempt is the unit for an individual email.

## 15. Java Model for Run Summary

~~~java
public record DispatchSummary(
        int claimed,
        int submittedSuccessfully,
        int submitFailures,
        int unknownOutcomes,
        int skipped,
        int unfinished
) {
    public boolean isEmpty() {
        return claimed == 0;
    }

    public boolean hasProblems() {
        return submitFailures > 0
                || unknownOutcomes > 0
                || unfinished > 0;
    }
}
~~~

### 15.1. Define Non-Overlapping Groups

The example above assumes `submitFailures` and `unknownOutcomes` are two separate groups. If a metric counts unknown as a failure subtype, adjust the aggregation so it does not double count.

### 15.2. `claimed` Does Not Necessarily Equal Attempts

After claiming, an event may be suppressed, expired, fail rendering before send, or hit a worker crash. An event may also have multiple attempts if policy allows internal retries.

### 15.3. In-Memory Summary Is Not Enough After a Crash

Durable outbox and attempt records help reconstruct history when a run has not recorded finish.

## 16. A Scheduled Orchestrator With Tracker

~~~java
import java.util.UUID;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledMailDispatchJob {

    private final JobRunTracker runs;
    private final MailOutboxDispatcher dispatcher;

    public ScheduledMailDispatchJob(
            JobRunTracker runs,
            MailOutboxDispatcher dispatcher
    ) {
        this.runs = runs;
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "5000")
    public void execute() {
        UUID runId = runs.begin(
                "mail-outbox-dispatcher",
                "scheduled"
        );

        try {
            DispatchSummary summary =
                    dispatcher.dispatch(runId);

            runs.finish(runId, summary);
        } catch (RuntimeException ex) {
            runs.fail(runId, "unexpected_dispatch_error");
            throw ex;
        }
    }
}
~~~

**`JobRunTracker`** and **`MailOutboxDispatcher`** are custom application services, not default APIs of Spring Framework Mail.

### 16.1. `begin` and `finish` Must Persist Separately

A run start transaction commits before dispatch; finish is written after the dispatcher ends.

### 16.2. What If `runs.fail` Also Fails?

In production, preserve the root cause: if a database outage causes both the dispatcher and the tracker to fail, structured logs/tracing must keep both the original error and the secondary error. The snippet above illustrates the basic happy/error flow.

### 16.3. Do Not Replay the Entire Run When Finish Fails

Some emails may have already been sent. Recovery must rely on event-level state and attempt history.

## 17. `JobRunTracker` and `@Transactional`

~~~java
import java.util.UUID;

public interface JobRunTracker {
    UUID begin(String jobName, String triggerType);

    void finish(UUID runId, DispatchSummary summary);

    void fail(UUID runId, String errorCategory);

    void heartbeat(UUID runId);
}
~~~

The implementation can use repository/JDBC and **`@Transactional(propagation = REQUIRES_NEW)`** in a separate Spring bean.

### 17.1. Reason for an Independent Transaction

If the database transaction for a mail event rolls back, the run start/failure history must still remain.

### 17.2. Spring AOP Self-Invocation

A `@Transactional` method called internally from the same instance may bypass the proxy, so transaction semantics will not behave as expected. Use a separate bean or `TransactionTemplate`.

### 17.3. Avoid Holding a DB Transaction While Sending

SMTP can be slow, time out, or disconnect. Holding row locks or connections during send increases contention and provides no SMTP rollback.

## 18. SQL for Recording `begin` and `finish`

Create run:

~~~sql
INSERT INTO mail_job_run (
    run_id,
    job_name,
    status,
    trigger_type,
    started_at,
    heartbeat_at,
    last_progress_at,
    instance_id,
    updated_at
)
VALUES (
    :run_id,
    :job_name,
    'RUNNING',
    :trigger_type,
    now(),
    now(),
    now(),
    :instance_id,
    now()
);
~~~

Finish:

~~~sql
UPDATE mail_job_run
SET status = :final_status,
    finished_at = now(),
    heartbeat_at = now(),
    claimed_count = :claimed,
    submit_success_count = :success,
    submit_failure_count = :failure,
    unknown_count = :unknown,
    skipped_count = :skipped,
    updated_at = now()
WHERE run_id = :run_id
  AND status = 'RUNNING';
~~~

### 18.1. Check `affectedRows`

If `UPDATE` returns 0, the run may have been marked `STALE` by recovery or updated by another operation. Do not overwrite unconditionally.

### 18.2. Clear `finalStatus` Definitions

A run with no work -> `SUCCEEDED_EMPTY`. A run that finishes everything without error -> `SUCCEEDED`. A run with mixed results -> `PARTIAL`. A run with an infrastructure failure preventing dispatch -> `FAILED`. These are example policy rules that should match your actual architecture.

## 19. Heartbeat and Detecting `STALE` Runs

~~~sql
UPDATE mail_job_run
SET heartbeat_at = now(),
    updated_at = now()
WHERE run_id = :run_id
  AND status = 'RUNNING';
~~~

### 19.1. Heartbeat Does Not Prove Progress

A heartbeat thread may stay alive while the worker hangs on an SMTP socket. Observe `last_progress_at` and active attempts as well.

### 19.2. Do Not Renew Indefinitely

You need an overall run deadline, SMTP timeouts, and a watchdog. A run without progress should not stay `RUNNING` forever.

### 19.3. `STALE` Sweeper

A periodic process detects `RUNNING` runs with expired heartbeats. However, it must not automatically reset all mail events in the run to `PENDING` because some already succeeded over SMTP.

### 19.4. Run Heartbeat Differs From Outbox Lease

Run heartbeats serve execution tracking; per-event leases govern processing ownership of an outbox job. The two mechanisms do not replace each other.

## 20. Distributed Locks and Skipped Triggers

With multiple instances, `@Scheduled` can run on every node. Two strategies:

| Strategy | Scope | Meaning |
| --- | --- | --- |
| Scheduler distributed lock | One scheduled execution | One node executes the orchestration turn |
| Atomic per-row outbox claim | Each event | Multiple nodes claim different events |

### 20.1. ShedLock and Skip Telemetry

A `@SchedulerLock` may skip an invocation that fails to acquire the lock. If the run-recording code lives inside the method, skipped invocations may have no run record. Add metrics at the lock acquisition/trigger layer to count skips accurately.

### 20.2. Scheduler Lock Does Not Replace Row Ownership

If the dispatcher only enqueues tasks and releases the lock while outbox rows remain `PENDING`, another node can pick up the same rows. Durable claims are required.

### 20.3. Lock Acquired Is Not Email Sent

A lock only protects orchestration authority; it does not indicate whether an SMTP attempt has started or finished.

## 21. Claiming Outbox Rows and Attaching `runId`

PostgreSQL example:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY_WAIT')
        AND next_attempt_at <= now()
    )
    OR (
        status = 'PROCESSING'
        AND claim_until < now()
    )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox m
SET status = 'PROCESSING',
    claim_owner = :worker_id,
    claim_until = now() + INTERVAL '90 seconds',
    claim_version = m.claim_version + 1,
    last_run_id = :run_id,
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING
    m.id,
    m.claim_version,
    m.last_run_id;
~~~

### 21.1. Claim and Commit Before SMTP

A database transaction selects, updates, and commits the rows before calling `JavaMailSender.send`. Do not hold row locks during network calls.

### 21.2. `SKIP LOCKED` Does Not Guarantee Strict FIFO

Rows locked by another transaction may be skipped. If emails require strict ordering, separate ordering or partitioning logic is needed.

### 21.3. An Expired Lease Does Not Mean Unsent

The worker may have sent over SMTP but crashed before updating `SENT`. Recovery must account for the unknown/duplicate window.

### 21.4. Fencing on Update

When writing `SENT`/`RETRY_WAIT`, check the matching owner/`claim_version`/token so a stale worker cannot overwrite newer state.

## 22. Tracking SMTP Attempts

Create an attempt record right before sending:

~~~text
attemptId   = UUID
mailEventId = durable event ID
runId       = current execution ID
provider    = actual selected provider
outcome     = STARTED
startedAt   = current timestamp
~~~

When sending finishes, update the outcome, duration, error category, and provider reply code when known.

### 22.1. Recording `STARTED` Is Valuable After a Crash

If the process disappears before finishing, a non-terminal attempt record remains, enabling reconciliation instead of vanishing from history.

### 22.2. Do Not Treat an Overdue `STARTED` Attempt as Unsent

The relay may have accepted the message. An attempt missing `finishedAt` is incomplete information, not proof of non-sending.

### 22.3. Rendering Errors Are Not SMTP Failures

If building the `MimeMessage` fails before send, record a preparation failure separately; do not increment the counter of actual SMTP attempts.

## 23. Retries Can Span Multiple Job Runs

~~~text
Event E:
  Run R1 / Attempt 1 -> SMTP 421 -> RETRY_WAIT
  Run R2 -> event not due, not selected
  Run R3 / Attempt 2 -> read timeout -> UNKNOWN_OUTCOME
  Run R4 -> reconciliation / policy decision
~~~

### 23.1. Run Frequency Differs From Retry Frequency

A scheduler running every 5 seconds does not mean every event is resent every 5 seconds. `nextAttemptAt` and backoff govern retries.

### 23.2. Classify Errors

AUTH, certificate, or invalid-recipient errors should usually not be retried aggressively. Temporary SMTP 4xx responses may fit backoff. Timeouts after `DATA` require duplicate-risk evaluation.

### 23.3. Terminal Failure

When `maxAttempts` or the deadline is exceeded, the event transitions to `FAILED`; the run dashboard should have a separate counter for terminal failures.

## 24. Critical Crash Windows

| Crash point | Run | Event/attempt | Risk |
| --- | --- | --- | --- |
| Before `begin` commit | No record | Not claimed | No run recorded |
| After `begin`, before `claim` | `RUNNING` | `PENDING` | Run becomes `STALE` |
| After `claim`, before `send` | `RUNNING` | `PROCESSING` | Recovery after lease expires |
| During template render | `RUNNING` | `PROCESSING` | Preparation failure/crash |
| After `DATA`, before final reply | `RUNNING` | Attempt incomplete | Unknown SMTP acceptance |
| After send success, before `SENT` | `RUNNING` | `PROCESSING` | Retry may send duplicate |
| After `SENT`, before run `finish` | `RUNNING` | `SENT` | Do not resend just because of run status |
| After `finish` | Terminal | Individual event states | Run history complete |

### 24.1. Do Not Replay an Entire `FAILED` Run

The run may have already sent many emails successfully. Replaying the whole list without checking outbox state will send duplicates.

### 24.2. Durable States Are the Source of Decision

Retries rely on mail event/attempt history, claim leases, status, and `nextAttemptAt`, not on a single metric counter.

## 25. Minimum Metrics

| Suggested metric | Type | Meaning |
| --- | --- | --- |
| `mail.scheduler.runs` | Counter | Runs by job/outcome |
| `mail.scheduler.run.duration` | Timer | Execution duration |
| `mail.scheduler.trigger.lag` | Timer | Planned-to-actual start |
| `mail.scheduler.lock.skipped` | Counter | Skipped due to lock |
| `mail.outbox.claimed` | Counter | Events claimed |
| `mail.outbox.ready.count` | Gauge | Events due now |
| `mail.outbox.pending.count` | Gauge | Pending workload |
| `mail.outbox.oldest.pending.age` | Gauge | Oldest pending age |
| `mail.outbox.retry.wait.count` | Gauge | Scheduled retries |
| `mail.outbox.expired.leases` | Gauge | Work with stale ownership |
| `mail.smtp.submit.attempts` | Counter | Actual sends attempted |
| `mail.smtp.submit.call.duration` | Timer | Caller-observed submit time |
| `mail.smtp.submit.unknown` | Counter | Unknown outcomes |
| `mail.event.terminal.failures` | Counter | Failed events |
| `mail.event.to.relay.acceptance` | Timer | Business-to-submit latency |

These are application-designed metric names; Spring Boot Actuator does not generate all of them by default.

### 25.1. Do Not Double Count

If both a `JavaMailSender` wrapper and worker code increment the submit attempt counter, the dashboard will be inflated. Choose a single place to instrument each event.

### 25.2. Bounded Metric Tags

Use allowlisted `job` aliases, `mail_kind`, `provider_alias`, `outcome`, and `error_category`. Do not use `runId`, `mailEventId`, recipient, Subject, or raw exception text.

## 26. Micrometer Timer for Runs

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class ObservedRunExecutor {

    private final MeterRegistry registry;

    public ObservedRunExecutor(MeterRegistry registry) {
        this.registry = registry;
    }

    public DispatchSummary execute(
            String jobName,
            java.util.function.Supplier<DispatchSummary> task
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            DispatchSummary summary = task.get();

            if (summary.hasProblems()) {
                outcome = "partial";
            }

            return summary;
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.scheduler.run.duration",
                            "job", jobName,
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.scheduler.runs",
                    "job", jobName,
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

### 26.1. Timer Records Failures Too

`finally` ensures duration/count are not lost when the task throws an exception. A metrics implementation that records only after success will skew the dashboard.

### 26.2. A Crash Can Bypass `finally`

If the process is killed, the in-process timer may not be recorded or exported. Durable run records and `STALE` recovery are still required.

### 26.3. Do Not Call Run Duration SMTP Duration

A run may include claiming, rendering, building, sending, and state updates. To pinpoint bottlenecks, measure those stages separately.

## 27. Timer for `JavaMailSender.send`

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class TimedSmtpSubmitter {

    private final JavaMailSender sender;
    private final MeterRegistry registry;

    public TimedSmtpSubmitter(
            JavaMailSender sender,
            MeterRegistry registry
    ) {
        this.sender = sender;
        this.registry = registry;
    }

    public void submit(
            MimeMessage message,
            String mailKind
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "kind", mailKind,
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.smtp.submit.attempts",
                    "kind", mailKind,
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

### 27.1. Caller-Observed Latency

`JavaMailSender.send` can include DNS, TCP, TLS, AUTH, MIME serialization, attachment I/O, `DATA` transfer, and the server reply. Do not equate it with pure SMTP server processing time.

### 27.2. Failure Differs From Unknown Outcome

In the wrapper, failure is only a caller-side exception. The durable attempt layer must classify cases that the relay may have accepted.

### 27.3. Do Not Send Twice to Measure

Instrumentation must wrap exactly **one** send side effect; do not let both the handler and the wrapper call `sender.send` for a single message.

## 28. Structured Logs for Runs and Attempts

Run start:

~~~json
{
  "event": "mail.job_run.started",
  "jobName": "mail-outbox-dispatcher",
  "runId": "run-001",
  "instanceAlias": "worker-a",
  "triggerType": "scheduled",
  "startedAt": "2026-11-12T08:00:00Z"
}
~~~

Run finish:

~~~json
{
  "event": "mail.job_run.finished",
  "runId": "run-001",
  "status": "PARTIAL",
  "durationMs": 3700,
  "claimed": 20,
  "submittedSuccessfully": 18,
  "submitFailures": 1,
  "unknownOutcomes": 1
}
~~~

SMTP attempt:

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "runId": "run-001",
  "mailEventId": "event-42",
  "attemptId": "attempt-3",
  "providerAlias": "smtp-primary",
  "outcome": "failure",
  "errorCategory": "timeout",
  "durationMs": 10010
}
~~~

### 28.1. Do Not Log Full MIME

Email content can contain PII, tokens, invoices, reset links, or attachments. Logs only need IDs, aliases, and outcomes sufficient for investigation.

### 28.2. Do Not Use Raw Exception Messages as Labels

Provider reply text can contain recipients, hosts, and variable strings; map it to a bounded `error_category` and only keep diagnostic text after appropriate sanitization.

## 29. Tracing and Async Boundaries

~~~text
mail.scheduler.run
       |
       +-- mail.outbox.claim
       |
       +-- mail.event.process
       |       |
       |       +-- mail.template.render
       |       +-- mail.mime.prepare
       |       +-- mail.smtp.submit
       |
       +-- mail.event.process
               |
               +-- mail.smtp.submit
~~~

### 29.1. A Run May Be Too Large for One Trace

If each run processes tens of thousands of emails, consider a separate trace per event and use span links or correlation fields to link to the run.

### 29.2. Trace ID Does Not Replace Business ID

Trace context is subject to sampling/retention and can break across the outbox, so `runId`/`mailEventId` are still needed for durable history.

### 29.3. Do Not Put Body Content Into Traces

Trace attributes are also stored by the backend. Avoid recipients, SMTP credentials, message bodies, and tokens in attributes.

## 30. Basic Dashboard

| Panel | Question |
| --- | --- |
| Last run status | How did the latest job finish? |
| Last actual start | Is the scheduler still active? |
| Next expected trigger | Upcoming schedule point, if known |
| Run duration p50/p95/p99 | Is the job unusually slow? |
| Runs by status | Are there FAILED/PARTIAL/EMPTY runs? |
| Claimed jobs/run | Is the dispatcher picking up work? |
| SMTP attempts by outcome | Is the transport failing? |
| Ready backlog | How much work is due now? |
| Retry backlog | How much work is in backoff? |
| Oldest pending age | Is any job suffering starvation? |
| Expired leases | Are workers losing ownership/crashing? |
| Terminal failed events | Which emails need manual handling? |
| Event-to-relay time | End-to-end latency to submission |

### 30.1. Dashboards Must Show Both Counts and Ratios

A p95 from 3 runs means something different from a p95 from 3,000 runs. Display sample counts to avoid wrong conclusions.

### 30.2. `SUCCEEDED_EMPTY` With High Backlog Is Abnormal

There may be an issue with the claim query, eligibility filter, routing, or lease logic.

### 30.3. Pending Count Alone Is Not Enough

A single mail event can stay stuck for a very long time. Oldest pending age and deadline misses matter more than the total count in many situations.

## 31. Prometheus Queries

Suppose Micrometer `Counter` exports:

~~~text
mail_scheduler_runs_total{
  job="mail-outbox-dispatcher",
  outcome="success"
}
~~~

Run rate:

~~~promql
sum by (job, outcome) (
  rate(mail_scheduler_runs_total[15m])
)
~~~

Failure ratio:

~~~promql
sum by (job) (
  increase(
    mail_scheduler_runs_total{outcome="failure"}[1h]
  )
)
/
sum by (job) (
  increase(mail_scheduler_runs_total[1h])
)
~~~

If `Timer` enables histograms, p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (job, le) (
    rate(
      mail_scheduler_run_duration_seconds_bucket[1h]
    )
  )
)
~~~

### 31.1. Do Not Assume Buckets Always Appear

You must configure appropriate Micrometer histograms or SLO buckets. Prometheus series names depend on registry/naming conventions.

### 31.2. Do Not Average Per-Pod p95 Values

For system-wide p95, aggregate histogram buckets first and then compute the quantile; averaging per-pod p95 is not the p95 across all samples.

### 31.3. With No Runs, the Denominator Is 0

The dashboard should display no data/no samples instead of assuming a 100% success rate.

## 32. Alerting on Missed Runs and Scheduler Lag

A job can:

- Have no trigger because the process is down.
- Have a trigger that is skipped by a distributed lock.
- Start, then hit a database error.
- Start and have no work.
- Run, but take too long.
- Run and crash before finishing.

### 32.1. Missing Differs From Skipped and Empty

**Missing:** no execution observed. **Skipped:** trigger occurred, but policy/lock prevented running. **Empty:** execution ran, no work found. **Failed:** execution encountered an error.

### 32.2. Alert Based on Real Expected Schedules

If only `startedAt` is available inside a `@Scheduled` method, do not fabricate `scheduledFor` to compute scheduler lag. When the scheduler provides a planned fire timestamp, you can measure actual-start minus planned-start.

### 32.3. Maintenance Windows

If a job is intentionally disabled, no-run alerts should be suppressed according to configuration to avoid noise.

## 33. Alerting on Stuck Runs, Backlogs, and Unknown Outcomes

Important signals:

- `RUNNING` past the deadline.
- Stale heartbeat or no progress.
- Increasing `expired leases`.
- Growing `ready backlog` even while the scheduler continues running.
- `oldest pending age` exceeding the SLO.
- `RETRY_WAIT` growing due to rate limits.
- Rising AUTH/TLS failures.
- Rising SMTP unknown outcomes after `DATA` timeouts.
- Unhandled `FAILED` terminal events.

### 33.1. Do Not Add Workers to Fix Every Problem

If the provider is throttling, adding workers can make things worse. Analyze error categories and rate limits before scaling.

### 33.2. Unknown Outcomes Relate to Correctness

A message may already have been accepted by the relay. Retrying quickly can create duplicates, not just waste resources.

### 33.3. A Heartbeat Without Progress Still Requires Investigation

The job may be waiting on the network or deadlocked even though the health endpoint still reports it as running.

## 34. Testing Orchestration With JUnit and Mockito

~~~java
import static org.mockito.Mockito.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class ScheduledMailDispatchJobTest {

    @Test
    void recordsRunSummary() {
        JobRunTracker runs = mock(JobRunTracker.class);
        MailOutboxDispatcher dispatcher =
                mock(MailOutboxDispatcher.class);

        UUID runId = UUID.randomUUID();

        when(runs.begin(
                "mail-outbox-dispatcher",
                "scheduled"
        )).thenReturn(runId);

        DispatchSummary summary =
                new DispatchSummary(5, 5, 0, 0, 0, 0);

        when(dispatcher.dispatch(runId))
                .thenReturn(summary);

        ScheduledMailDispatchJob job =
                new ScheduledMailDispatchJob(
                        runs,
                        dispatcher
                );

        job.execute();

        verify(dispatcher).dispatch(runId);
        verify(runs).finish(runId, summary);
        verify(runs, never()).fail(
                eq(runId),
                anyString()
        );
    }
}
~~~

### 34.1. Test the Failure Branch

Have the dispatcher throw a `RuntimeException` and assert that `runs.fail` is called and the exception is not swallowed.

### 34.2. Test the Empty Run

Set `claimed=0` and verify that the tracker receives the summary to map to `SUCCEEDED_EMPTY`.

### 34.3. Do Not Prove Distributed Correctness With Single-Threaded Mocks

The unit test above does not check database locks or concurrent claims; separate integration tests are needed.

## 35. Testing Micrometer Without SMTP

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

class ObservedRunExecutorTest {

    @Test
    void recordsPartialOutcome() {
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry();

        ObservedRunExecutor executor =
                new ObservedRunExecutor(registry);

        DispatchSummary result =
                executor.execute(
                        "mail-outbox-dispatcher",
                        () -> new DispatchSummary(
                                3, 2, 1, 0, 0, 0
                        )
                );

        assertTrue(result.hasProblems());

        Counter runs = registry
                .find("mail.scheduler.runs")
                .tag("job", "mail-outbox-dispatcher")
                .tag("outcome", "partial")
                .counter();

        assertNotNull(runs);
        assertEquals(1.0, runs.count(), 0.0001);
    }
}
~~~

To test exact durations accurately, use Micrometer **`MockClock`** instead of `Thread.sleep` with tight thresholds that cause flaky CI.

## 36. Integration Testing With PostgreSQL and Crash Recovery

If production uses **`FOR UPDATE SKIP LOCKED`**, use real PostgreSQL in tests—for example via Testcontainers—because H2 or mocks may not share equivalent semantics.

~~~text
Insert 100 PENDING outbox records
Start worker A and B concurrently
Each calls claimBatch in own transaction
Commit
Assert claimed row sets do not overlap
Assert claim ownership and version correct
~~~

### 36.1. Use Latches/Barriers

`CountDownLatch`/`CyclicBarrier` creates real contention; do not run A then B sequentially and call it a concurrency test.

### 36.2. Test Stale Ownership

A claims version 1, the lease expires, and B claims version 2. A updating `SENT` with version 1 must affect 0 rows.

### 36.3. Test the SMTP Crash Window

A fake transport returns success, but the database update to `SENT` is not committed. Recovery must obey policy rather than blindly resending the whole run.

### 36.4. Test `STALE` Runs

Create a `RUNNING` record and simulate a process crash; after the heartbeat timeout, the sweeper marks it `STALE`. Events already `SENT` keep their state.

## 37. Scenario Test Matrix

| Scenario | Expected behavior |
| --- | --- |
| Cron with zone | Runs in the configured timezone |
| App restart drops missed ticks | Due outbox events are still processed |
| Manual trigger | Has a distinct `runId` and audit entry |
| Job disabled | Does not raise false missed-run alerts |
| Distributed lock busy | Skips without duplicate sending |
| Empty outbox | `SUCCEEDED_EMPTY` |
| Database error | `FAILED` or appropriate error state |
| Some events retry | Run summary matches the contract |
| Worker crashes mid-run | `STALE`, per-event recovery |
| Heartbeat alive but no progress | Stuck alert fires |
| Two workers claim concurrently | No shared active ownership |
| Lease expired | Stale update is blocked |
| `nextAttemptAt` in the future | Not retried early |
| SMTP send success | Caller-side attempt success |
| Invalid AUTH | Not retried aggressively |
| Temporary SMTP 421 | Appropriate backoff |
| Timeout after `DATA` | `UNKNOWN_OUTCOME` |
| Provider failover | Attribution per attempt |
| Timer failure | Sample recorded in `finally` |
| PII in payload | Not logged or tagged outside policy |

## 38. Runbook When a Job Does Not Run

1. Confirm job enabled state, `cron`/`fixedDelay`, and timezone.
2. Check last run status, last start, and expected trigger if available.
3. Check app instances, scheduler executor, and thread saturation.
4. Check ShedLock/lock provider and skipped triggers.
5. Check database connectivity and permissions to write run records.
6. Check outbox ready count, status filter, and `nextAttemptAt`.
7. If `claimed=0` while `ready>0`, inspect the claim query and lease.
8. If `claimed>0` while `attempts=0`, inspect validation, rendering, and MIME preparation.
9. If attempts fail, classify `AUTH`/`TLS`/`connect`/`rate_limit`/recipient.
10. If `RUNNING` too long, check `heartbeat` and `last_progress_at`.
11. If a worker crashed, reconcile `SENT`/`PROCESSING`/`UNKNOWN_OUTCOME`.
12. Retry only eligible events according to policy; do not replay the entire run.

### 38.1. Do Not Arbitrarily Reset `SENT` to `PENDING`

If SMTP already accepted the message, a resend can create duplicates. A manual resend is a separate business operation that requires auditing.

### 38.2. Access Control and Personal Data

Run history needs metadata, not passwords, tokens, full HTML, recipient addresses, or attachments. To look up a specific event, use IDs and an access-controlled system.

## 39. Common Anti-Patterns

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Start/Finish logs without `runId` | Hard to reconcile | Durable run ID |
| Treating a run as one email | Wrong unit | Separate definition/run/event/attempt |
| Marking `SENT` on async enqueue | Premature success report | Acknowledge by SMTP outcome |
| Recording only successful attempts | Loses errors/timeouts | `STARTED` + terminal outcome |
| Counting retries as new events | Skewed unique counts | Stable `mailEventId` |
| Using `@Scheduled` as a distributed mutex | Multi-node duplicates | Lock/atomic row claim |
| Holding a DB transaction during send | Contention | Claim/commit before SMTP |
| No heartbeat/recovery | Stuck `RUNNING` | `STALE` sweeper |
| Heartbeat without progress | False health | Last progress/deadline |
| Replaying an entire `FAILED` run | Duplicates | Retry per outbox event |
| Blindly retrying timeout after `DATA` | Duplicate risk | `UNKNOWN_OUTCOME` |
| Watching only `pending_count` | Misses starvation | Oldest pending age |
| Recipient/`eventId` as metric tag | PII/high cardinality | Low-cardinality labels |
| Comparing `nanoTime` across nodes | Wrong duration | Proper timestamps/clocks |
| Fabricating `scheduledFor` | Fake lag | Real planned trigger |
| Calling `SUCCEEDED` delivered | Wrong SLA | Submission vs downstream |
| Mocking DB to prove `SKIP LOCKED` | Misses race conditions | Database integration test |
| Testing duration with `Thread.sleep` | Flaky CI | Fake clock/`MockClock` |

## 40. Frequently Asked Questions

**1. Is a mail-sending job a single email?**

No. A job is the schedule/orchestration; a run is an execution; an event is a sending intent; an attempt is one SMTP submission.

**2. What should a run store?**

`runId`, `jobName`, trigger, `startedAt`, `finishedAt`, status, `instanceId`, counters, and categorized errors. If scheduler lag is needed, a trustworthy planned fire timestamp is required.

**3. Is a run with no emails an error?**

No. When querying the outbox succeeds and no events are due, `SUCCEEDED_EMPTY` is a valid outcome.

**4. Does a `FAILED` run mean no emails were sent?**

No. Some events may have been sent successfully before the error. Do not replay the whole run.

**5. Does `@Scheduled` automatically store durable run history?**

Not in this tracker model. You can use an application run table or an appropriate scheduler/job framework.

**6. Does `@Scheduled` automatically prevent duplicate runs across pods?**

No. Each instance has its own scheduler; distributed coordination or atomic row claims are required.

**7. Does ShedLock replace the outbox?**

No. Scheduler locks and per-event durable state solve two different layers.

**8. Why are separate `eventId` and `attemptId` needed?**

A mail event can be retried multiple times, each time as a distinct attempt with its own outcome.

**9. Is `nextAttemptAt` the same as the cron schedule?**

No. Cron decides when the dispatcher wakes up; `nextAttemptAt` decides when an event is eligible to retry.

**10. Does run success mean the email reached the inbox?**

No. `JavaMailSender.send` success only reflects transport submission; it does not guarantee downstream delivery/read.

**11. Does a timeout guarantee the relay did not accept the message?**

No. Losing the final response after `DATA` can produce an unknown outcome.

**12. Does a heartbeat prove the job is still making progress?**

Not necessarily. Also track `last_progress_at`, active attempts, and deadlines.

**13. Why not use recipient as a metric tag?**

It is PII and has high cardinality. Use correlation IDs in access-controlled logs/databases.

**14. Can the tracker be tested without real SMTP?**

Yes. Use Mockito for the sender/dispatcher, `SimpleMeterRegistry` for metrics, and an SMTP capture server for integration tests.

**15. Is testing `SKIP LOCKED` with H2 sufficient?**

Do not assume so. Use PostgreSQL if production relies on PostgreSQL semantics.

**16. Can Quartz or Spring Batch help with run tracking?**

Yes in suitable architectures, but you still need to link executions to outbox events and SMTP attempts; they do not provide inbox delivery tracking out of the box.

**17. What happens if the scheduler misses ticks during a restart?**

Outbox polling after restart can process due events. If each business period needs catch-up, durable period keys are required.

**18. When is a manual resend needed?**

When requested by business logic and after reconciling the previous state; do not simply flip `SENT` back to `PENDING`.

**19. Does a low pending count mean there is no dangerous backlog?**

No. A single event can stay stuck for a long time. You need `oldest pending age` and deadline misses.

**20. Is run success rate the same as SMTP success rate?**

No. One measures executions, the other measures transport attempts. Their units and scopes differ.

## 41. Key Takeaways on Tracking Send Jobs and Runs

**A well-scheduled Spring Framework Mail system must track job definitions, job runs, mail events, and SMTP attempts separately.** Assign a `runId` per execution, record timestamps/statuses/counters, use a stable `mailEventId` across retries, and assign a new `attemptId` for each transport call. Run success, SMTP send success, and inbox delivery are **three distinct concepts**.

Write run `begin`/`finish` in short transactions, and monitor heartbeats and `last_progress_at` to detect `STALE` runs. When running on multiple nodes, use atomic outbox claims/leases and appropriate distributed coordination; do not hold a database transaction during SMTP send. When the relay may have accepted `DATA` but the client did not receive the response, record **`UNKNOWN_OUTCOME`** and avoid blind retries.

Combine durable run/outbox/attempt history with **Micrometer `Timer`/`Counter`**, structured logging, tracing, dashboards, and alerts on missed runs, expired leases, retry backlogs, oldest pending age, and terminal failures. Test orchestration with JUnit/Mockito, metrics with `SimpleMeterRegistry`/`MockClock`, and concurrency against an appropriate database.

The goal is not merely to know that the scheduler ran, but to answer **which run did what, which event was attempted, why an error occurred, whether the outcome is certain, and what work needs handling next** — verifiably, without duplicate sends, and without exposing email data.

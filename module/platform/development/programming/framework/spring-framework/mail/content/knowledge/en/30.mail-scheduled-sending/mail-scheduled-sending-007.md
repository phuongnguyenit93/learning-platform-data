# Choosing Batch Size and Polling Interval in Spring Framework Mail

In a Spring application, a durable email-sending model typically writes send requests to a **database outbox**, then uses a scheduler/worker to pick up due requests and send them via `JavaMailSender`. Two critical parameters in this design are **batch size** (the maximum number of jobs claimed per round) and **polling interval** (the cadence at which the scheduler checks for newly due jobs).

These two small numbers directly affect wait times, database query load, the number of jobs holding leases, SMTP quota consumption rate, and duplicate risk when a process fails. Increasing batch size does not automatically speed up SMTP; shrinking the interval does not cure provider throttling. Conversely, too small a batch and too slow a poll can leave workers idle while urgent emails pile up.

**Goal:** choose batch size and polling interval based on SLOs, job arrival rate, SMTP latency, concurrency, provider quotas, database capacity, and recovery behavior rather than copying fixed magic numbers.

This lesson walks through the math, Spring Scheduling/PostgreSQL implementation patterns, bounded executors, claiming/leasing, retries, metrics, high-load scenarios, and a practical tuning workflow. All concrete numbers serve strictly to illustrate the model.

## 1. Where Do Batch Size and Polling Interval Apply?

```text
Business transaction
        |
        +--> Update business data
        +--> Insert mail_outbox job
        |
        v
COMMIT
        |
        v
Durable outbox
        |
        v
@Scheduled poller
        |
        +--> Find due jobs
        +--> Claim at most batchSize
        +--> Mark owner/lease
        |
        v
Bounded worker pool
        |
        +--> Check eligibility/expiry
        +--> Load prepared HTML/attachments
        +--> Build MimeMessage
        +--> Apply rate/concurrency limits
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP submission outcome
        |
        +--> SUBMITTED
        +--> RETRY_WAIT
        +--> FAILED
        +--> AMBIGUOUS
```

Here **batch size = number of outbox jobs per claim**, not the number of recipients on one email or MIME messages sent over a single SMTP connection. One job may equal one email to one person, though that is a business modeling decision.

**Polling interval = cadence of reading/claiming due jobs**. It is not the delay between `JavaMailSender.send(...)` calls, not retry backoff, and not a per-recipient frequency cap.

## 2. Separating Related Parameters

| Parameter | Unit | Effect |
| --- | --- | --- |
| `batchSize` | jobs/round | Maximum jobs claimed per poll |
| `pollDelay` | seconds/ms | Interval between scheduler checks |
| `sendConcurrency` | tasks | Concurrent SMTP attempts running |
| `maxInFlight` | jobs | Claimed jobs not yet completed |
| `queueCapacity` | tasks | Tasks waiting inside the executor |
| `providerRate` | messages/s or recipients/min | SMTP provider rate limit |
| `leaseDuration` | seconds/minutes | Ownership duration for a job |
| `retryBackoff` | seconds/minutes | Retry delay schedule on failures |
| `sendTimeout` | seconds | Transport connect/read/write limits |

Do not lump these parameters into one vague notion of "send speed". Raising batch size only speeds up **work supply** if the poller is the bottleneck. When SMTP or provider quotas are the real bottleneck, raising batch size merely inflates in-flight jobs.

## 3. Symptoms of Too Small a Batch Size

Suppose a poller claims 1 job per second while the database holds 10,000 waiting jobs and SMTP can handle 50 jobs/sec. Without another mechanism to pull more work, the poller supplies only about 1 job/sec.

Consequences:

- SMTP workers sit idle despite a full `READY` outbox.
- Queue age climbs.
- Campaigns finish very slowly.
- Database queries per email are needlessly high.
- Adding more send threads fails to improve throughput.

Small batches do have benefits: fewer active leases, lower memory usage, cleaner crash recovery, and less starvation risk. Never increase batch size merely to "go faster"; confirm first that the poller itself is starving workers.

## 4. Symptoms of Too Large a Batch Size

Suppose a poller claims 1,000 jobs, the executor has 10 threads, and each SMTP attempt takes 4 seconds on average:

```text
1,000 jobs / 10 workers = 100 waves
100 waves × 4 seconds ≈ 400 seconds
```

This is a rough estimate assuming equal wave durations. The tail jobs may wait several minutes before starting. If `leaseDuration=60s`, many jobs expire their leases while still waiting in the executor queue, causing:

- Other workers reclaiming the same notifications.
- Duplicate processing or duplicate emails.
- Memory and queue pressure.
- Hard-to-control crash recovery.
- Bulk campaigns starving transactional mail capacity.
- High `PROCESSING` counts without higher throughput.

**Rule of thumb:** never claim far ahead of when tasks actually have free worker slots and safe lease margin.

## 5. Why Polling Too Fast Is Also Costly

Suppose 20 application instances all poll every 20 ms:

```text
1 instance: 50 polls/s
20 instances: 1,000 polls/s
```

If the system sends only a few emails per minute, nearly every query returns 0 jobs while still burning DB round trips, connection pools, CPU, and scheduler wake-ups.

Fast polling may be needed for low-latency SLOs, but monitor your empty-poll ratio. If fast detection is needed alongside low send volume, an **event/broker wake-up + periodic reconciliation poll** may fit better.

Event wake-ups should serve only as hints; if a wake-up signal drops, periodic polling must still discover durable outbox jobs.

## 6. Why Polling Too Slowly Increases Latency

In an idealized setting where the poller runs with steady effective period `I`, jobs arrive roughly uniformly between polls, and there is no backlog:

\[
E[T_{\mathrm{detection}}]\approx I/2
\]

| Effective poll period | Approximate average detection delay | Approximate max wait |
| --- | ---: | ---: |
| 100 ms | 50 ms | 100 ms |
| 500 ms | 250 ms | 500 ms |
| 1 s | 500 ms | 1 s |
| 5 s | 2,5 s | 5 s |
| 30 s | 15 s | 30 s |
| 60 s | 30 s | 60 s |

This covers **detection wait only**. Total time from business event to SMTP acceptance also includes transaction commit, queue wait, rendering, rate limiting, and transport duration. Under heavy backlogs, total latency can far exceed `I`.

Short-TTL OTPs and newsletters with multi-hour deadlines do not need the same polling interval.

## 7. Define SLOs Before Tuning

A system should answer:

1. Measurement start point: business event commit, `nextAttemptAt`, or request accepted?
2. Measurement end point: job claimed, first SMTP attempt, or SMTP relay accepted?
3. Target P95/P99 latency per email category?
4. Average and peak job arrival rates?
5. Is the SMTP provider quota counted per message or per recipient?
6. P50/P95/P99 SMTP attempt duration?
7. How much do MIME/attachment sizes and I/O fluctuate?
8. How many app instances, SMTP worker threads, and DB connections exist?
9. How much backlog is acceptable?
10. Do emails have business deadlines or token expirations?

Never use "email landed in Inbox" as the poller's own SLO: `JavaMailSender.send(...)` succeeding confirms transport submission, not downstream delivery.

## 8. Theoretical Work Supply Rate

With batch size `B` and effective poll cycle `I_eff` seconds:

\[
R_{\mathrm{claim}}\leq \frac{B}{I_{\mathrm{eff}}}
\]

Example:

```text
batchSize = 20 jobs
effectivePollCycle = 2 seconds

Claim supply ≈ 10 jobs/s
```

This formula gives an upper bound on claim supply when enough jobs exist and queries are fast. It does not guarantee every poll claims all `B` jobs.

Actual SMTP throughput is further bounded by concurrency, latency, the provider, and template/attachment I/O.

## 9. Throughput Is Bounded by the Slowest Link

Simple model:

\[
R_{\mathrm{effective}}\lesssim
\min\left(R_{\mathrm{claim}},\frac{C}{S},R_{\mathrm{provider}},R_{\mathrm{storage}},R_{\mathrm{DB}}\right)
\]

Where `C` is SMTP attempt concurrency and `S` is mean seconds per attempt.

Example:

```text
batchSize                  40 jobs
effectivePollCycle         2 seconds
poller supply              ~20 jobs/s

SMTP concurrency            8
mean SMTP attempt           2 seconds
sender capacity            ~4 attempts/s

provider limit              6 messages/s
```

The slowest link here is sender capacity at ~4 attempts/s. Raising batch size from 40 to 100 will not raise throughput to 50 jobs/s.

Watch **units**: one SMTP message may carry multiple recipients while a provider quota counts recipients/minute. Never compare the two directly without converting units.

## 10. Sizing Backwards From Arrival Rate

Let `λ` be the job arrival rate per second during the window of interest. To keep backlogs from growing unboundedly in steady state, long-run processing capacity must exceed `λ`:

\[
R_{\mathrm{effective}} > \lambda
\]

Example:

```text
Peak arrival        8 jobs/s
Claim capacity     10 jobs/s
SMTP capacity      12 jobs/s
Provider capacity  15 messages/s
```

Throughput may be capped by the poller at 10 jobs/s, leaving slim headroom for bursts or retries. Appropriate headroom must be measured from real workloads—no single fixed safety ratio fits every system.

## 11. Little's Law and Backlog

In steady state, Little's Law states:

\[
L = \lambda W
\]

Where `L` is average jobs in the system/queue over the measured boundary, `λ` is average throughput, and `W` is average time spent inside that boundary.

If a queue sustains 10 jobs/s with a 3s average wait, roughly 30 jobs are in queue on average under appropriate steady-state assumptions.

Increasing batch size does not reduce `W` if SMTP is already the bottleneck. It simply shifts backlog from `READY` in the database into `PROCESSING`/executor queues.

## 12. fixedDelay, fixedRate, and cron Differ

Spring Scheduling supports:

- `fixedDelay`: next run starts after a delay measured from **when the previous run completed**.
- `fixedRate`: attempts to schedule at a fixed cadence between start times, depending on the runtime scheduler/executor.
- `cron`: triggers at specified calendar times.

Example where `poll()` takes 300ms with a 1s fixed delay:

```text
Poll #1 start  0.0s
Poll #1 end    0.3s
Poll #2 start  1.3s
Poll #2 end    1.6s
Poll #3 start  2.6s
```

For a sequential poller:

\[
I_{\mathrm{eff}}\approx I_{\mathrm{configured}}+T_{\mathrm{poll}}
\]

If `poll()` sends the whole batch synchronously, execution can last tens of seconds. Then a configured 1s fixed delay no longer means starting every second. `fixedRate` also cannot fix provider throttling or missing worker capacity.

## 13. Basic Spring @Scheduled Poller

```java
@Configuration
@EnableScheduling
public class MailSchedulingConfiguration {
}
```

```java
@Component
public class MailOutboxPoller {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxPoller(
            MailOutboxDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.dispatch.poll-delay:PT1S}"
    )
    public void poll() {
        dispatcher.dispatchDue();
    }
}
```

Application configuration:

```yaml
app:
  mail:
    dispatch:
      poll-delay: PT1S
      batch-size: 20
      max-in-flight: 40
      lease-duration: PT2M
```

`app.mail.dispatch.*` are **application-defined properties**, not a built-in outbox feature of `spring-boot-starter-mail`. Use explicit duration units such as ISO `PT1S`.

## 14. Send Inside the Poller or Hand Off to Workers?

**Approach A: poller sends the whole batch synchronously.**

```text
@Scheduled poll()
    claim B jobs
    for each job:
        render, send, update status
    return
    wait fixedDelay
```

Simple, but poll cadence gets coupled to SMTP latency. One hung attempt stalls newly due jobs.

**Approach B: poller claims quickly and hands off to bounded workers.**

```text
@Scheduled poll()
    calculate available slots
    atomic claim <= available slots
    submit jobs to bounded executor
    return quickly

Worker:
    load content, SMTP send, update status
```

Approach B decouples polling cadence from network duration much better, provided you enforce `maxInFlight`, bounded queues, leases, ownership, and recovery. Never claim thousands of jobs just to buffer them in memory.

## 15. Practical Batch Claims Should Depend on Capacity

A bound:

\[
B_{\mathrm{claim}} \leq
\min(B_{\mathrm{configured}},K_{\mathrm{available}},B_{\mathrm{safeLease}},B_{\mathrm{policy}})
\]

Example:

```text
Configured batch          50
Idle worker slots          6
Free bounded queue slots   4
Safe new in-flight        10
Actual claim              <= 10
```

If you do not want jobs waiting in memory after claiming, claim at most 6. If a small bounded queue is permitted, ensure leases are long enough or renewed properly.

**Batch size is an upper ceiling, not a quota every poll must hit.**

## 16. Rate Limits Are Independent of Batch Size

Providers may limit messages/sec, recipients/min, concurrent connections, and daily quotas. Adding send threads can increase 421/4xx throttling.

When multiple instances share one SMTP account, per-JVM limiters can overshoot the global provider quota. Use global/shared rate coordination or instance-partitioned budgets.

Recipient frequency caps (at most N marketing emails per recipient in a window) also differ from provider rate limits. Pollers must never bypass consent or suppression simply because SMTP has spare capacity.

## 17. A PostgreSQL Outbox Schema

```sql
CREATE TABLE mail_outbox (
    id               UUID PRIMARY KEY,
    notification_id  UUID NOT NULL UNIQUE,
    category         VARCHAR(40) NOT NULL,
    status           VARCHAR(30) NOT NULL,
    next_attempt_at  TIMESTAMPTZ NOT NULL,
    priority         INTEGER NOT NULL DEFAULT 0,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    locked_by        VARCHAR(100),
    lease_until      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Statuses may include `READY`, `PROCESSING`, `RETRY_WAIT`, `SUBMITTED`, `FAILED`, `AMBIGUOUS`, `CANCELLED`, and `EXPIRED`.

Read-only job query:

```sql
SELECT id
FROM mail_outbox
WHERE status IN ('READY', 'RETRY_WAIT')
  AND next_attempt_at <= NOW()
ORDER BY priority DESC, next_attempt_at, created_at, id
LIMIT :batch_size;
```

With multiple pollers, **SELECT then send is insufficient to prevent duplicates**. Two instances can observe the same row. Use atomic claiming with locking/leases or a broker with ownership/ack semantics.

## 18. Atomic Claiming With FOR UPDATE SKIP LOCKED

PostgreSQL example claiming and updating status in one query:

```sql
WITH eligible AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('READY', 'RETRY_WAIT')
        AND next_attempt_at <= NOW()
    )
    OR (
        status = 'PROCESSING'
        AND lease_until < NOW()
    )
    ORDER BY priority DESC, next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'PROCESSING',
    locked_by = :worker_id,
    lease_until =
        NOW() + (:lease_seconds * INTERVAL '1 second'),
    attempt_count = attempt_count + 1,
    updated_at = NOW()
FROM eligible
WHERE job.id = eligible.id
RETURNING job.id, job.attempt_count, job.lease_until;
```

Named parameters are bound by the repository. The claim transaction should:

1. Select at most B eligible records.
2. Skip rows locked by other transactions.
3. Transition them to `PROCESSING`, writing owner/lease/attempt.
4. Return the exact claimed rows.
5. **Commit fast** before rendering or calling SMTP.

`FOR UPDATE SKIP LOCKED` resolves lock contention **inside the claim transaction**; `lease_until` and `locked_by` preserve ownership **after the transaction commits**. They are two separate mechanisms.

## 19. Never Hold a DB Transaction Across SMTP

Anti-pattern:

```text
BEGIN TRANSACTION
    SELECT 100 jobs FOR UPDATE
    for each job:
        JavaMailSender.send(...)
        update status
COMMIT
```

Consequences:

- Holds DB rows and connections open too long.
- Network timeouts prolong transactions.
- DB rollbacks cannot roll back already-sent emails.
- A batch may contain accepted emails whose DB status has not committed.
- Contention spikes when multiple pollers run.

Recommended pattern:

```text
Transaction #1: claim jobs, assign lease, COMMIT

Outside DB transaction:
    Render MIME and submit SMTP

Transaction #2 per job:
    Record outcome with ownership/version check, COMMIT
```

To synchronize with business events, **insert the mail intent/outbox inside the business transaction**. SMTP side effects still run after commit.

## 20. Indexes for Polling Due Jobs

Example:

```sql
CREATE INDEX idx_mail_outbox_due
ON mail_outbox (
    next_attempt_at,
    priority DESC,
    created_at
)
WHERE status IN ('READY', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_lease
ON mail_outbox (lease_until)
WHERE status = 'PROCESSING';
```

Optimal indexes depend on actual query plans, status ratios, and table size. Queries with `OR`/`ORDER BY` may not use every column as expected. Monitor scan counts, buffer reads, update/WAL overhead, and lock contention.

Never shrink the poll interval when the DB query is already slow for lack of indexes; that only multiplies load.

## 21. Strongly Typed Properties Record

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.dispatch")
public record MailDispatchProperties(
    int batchSize,
    Duration pollDelay,
    int maxInFlight,
    Duration leaseDuration
) {}
```

Registration:

```java
@Configuration
@EnableConfigurationProperties(MailDispatchProperties.class)
public class MailDispatchConfiguration {
}
```

At startup, validate `batchSize > 0`, `maxInFlight > 0`, positive durations, and leases sized for real timeouts and executor capacity. Use Bean Validation per your project's dependencies/version.

Never silently accept a batch size of 0 or negative poll delay that breaks worker operation.

## 22. Repository Contract for Claiming

```java
public record ClaimedMailJob(
    UUID jobId,
    UUID notificationId,
    int attemptNo,
    String workerId,
    Instant leaseUntil
) {}
```

```java
public interface MailOutboxRepository {

    List<ClaimedMailJob> claimDue(
        int maxCount,
        String workerId,
        Duration leaseDuration
    );

    void releaseIfOwned(ClaimedMailJob job);
}
```

These types are application-defined contracts. `claimDue` must run in a short transaction using atomic SQL claiming. `releaseIfOwned` reverts status only when owner and attempt still match.

When using `@Transactional`, ensure calls pass through the Spring proxy or use `TransactionTemplate`; self-calling a `@Transactional` method on the same object bypasses proxy transactions under default settings.

## 23. Bounded Dispatcher Using a Semaphore

Example dispatcher that never claims beyond available in-flight slots:

```java
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Semaphore;

import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;

@Service
public class MailOutboxDispatcher {

    private final MailOutboxRepository repository;
    private final MailSubmissionWorker worker;
    private final TaskExecutor executor;
    private final MailDispatchProperties settings;
    private final Semaphore slots;
    private final String workerId = UUID.randomUUID().toString();

    public MailOutboxDispatcher(
            MailOutboxRepository repository,
            MailSubmissionWorker worker,
            TaskExecutor executor,
            MailDispatchProperties settings) {
        this.repository = repository;
        this.worker = worker;
        this.executor = executor;
        this.settings = settings;
        this.slots = new Semaphore(settings.maxInFlight());
    }

    public void dispatchDue() {
        int reserved = 0;

        while (reserved < settings.batchSize()
                && slots.tryAcquire()) {
            reserved++;
        }

        if (reserved == 0) {
            return;
        }

        List<ClaimedMailJob> jobs;

        try {
            jobs = repository.claimDue(
                reserved, workerId, settings.leaseDuration()
            );
        } catch (RuntimeException exception) {
            slots.release(reserved);
            throw exception;
        }

        slots.release(reserved - jobs.size());

        for (ClaimedMailJob job : jobs) {
            try {
                executor.execute(() -> {
                    try {
                        worker.process(job);
                    } finally {
                        slots.release();
                    }
                });
            } catch (TaskRejectedException exception) {
                slots.release();
                repository.releaseIfOwned(job);
            }
        }
    }
}
```

This is a **capacity-bounding pattern**, not a complete worker library:

- `claimDue` must enforce proper transactions and leases.
- If the executor rejects and `releaseIfOwned` also fails, lease recovery serves as fallback.
- `worker.process` must persist status/retries or rely on recovery.
- The semaphore is in-memory per instance, not a replacement for global SMTP quotas.
- On a crash, the semaphore vanishes while durable jobs recover via leases.
- If multiple threads can call `dispatchDue` concurrently, serialize or coordinate capacity properly.
- If the dispatcher crashes after claiming but before task submission, jobs recover after lease expiry.

Core takeaway: **acquire capacity before claiming** and always release permits when tasks finish.

## 24. ThreadPoolTaskExecutor Must Also Be Bounded

```java
@Bean(name = "mailSubmissionExecutor")
public ThreadPoolTaskExecutor mailSubmissionExecutor() {
    ThreadPoolTaskExecutor executor =
        new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(12);
    executor.setThreadNamePrefix("smtp-mail-");
    executor.initialize();

    return executor;
}
```

With 8 worker threads and a queue of 12, a `maxInFlight` around 20 may match **maximum buffered tasks**, yet still must account for leases, MIME sizes, and quotas.

Warnings:

- Unbounded executor queues invite memory pressure.
- `CallerRunsPolicy` can run SMTP on scheduler or request threads; use only intentionally.
- In-memory tasks never replace a durable outbox.
- Claims must match real worker slots, not an arbitrary guess at CPU core count.

## 25. Worker Sends Mail and Persists Outcome

Java-like pseudocode example:

```java
public void process(ClaimedMailJob claim) {
    UUID notificationId = claim.notificationId();

    if (!eligibility.permitsSendingNow(notificationId)) {
        states.markSuppressedIfOwned(claim);
        return;
    }

    try {
        PreparedMail mail = contents.loadPrepared(notificationId);
        smtpDelivery.submit(mail);
        states.markSubmittedIfOwned(claim);
    } catch (TemporaryMailFailure exception) {
        states.scheduleRetryIfOwned(claim, exception);
    } catch (PermanentMailFailure exception) {
        states.markFailedIfOwned(claim, exception);
    } catch (AmbiguousMailFailure exception) {
        states.markAmbiguousIfOwned(claim, exception);
    }
}
```

`eligibility`, `states`, `contents`, `smtpDelivery`, and exception types are application abstractions. `JavaMailSender` does not return an outcome enum by default.

Never catch every SMTP exception and assume the server definitely did not receive the message. The outcome may be **AMBIGUOUS** if the response dropped after the relay accepted DATA.

## 26. Lease Duration Must Balance With In-Flight Count

If you claim 100 jobs with 10 workers, 3s P95 SMTP latency, and a 30s lease, tail jobs may start right as their leases expire.

Solutions:

- Claim close to when tasks start.
- Reduce `batchSize` or `maxInFlight`.
- Cap executor queue depth.
- Size leases to worst expected processing time.
- Renew leases during long runs if heartbeats are implemented.
- Check ownership at start and on status updates.
- Design recovery for worker crashes.

Overly long leases are also bad: when a worker dies, jobs sit stuck until recovery. No single lease number fits every system.

## 27. Fencing Stale Owners

Worker A's lease may expire and Worker B reclaims the job. If A wakes up, it must never overwrite state now owned by B.

```sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    locked_by = NULL,
    lease_until = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND status = 'PROCESSING'
  AND locked_by = :worker_id
  AND attempt_count = :claimed_attempt;
```

If affected rows equals 0, owner or attempt changed. Never update blindly by job ID.

Fencing protects **database state**, not undo an SMTP submission already made by Worker A. That is why idempotency, lease management, and ambiguous-attempt handling are essential.

## 28. Polling Interval Is Not Retry Interval

When a provider returns a temporary failure, do not reset the job to READY and let the poller retry it every 100ms.

```text
SMTP temporary error
        |
        v
Classify + exponential backoff + jitter
        |
        v
status=RETRY_WAIT
nextAttemptAt=now + backoff
        |
        v
Poller only claims when due
```

Example formula:

\[
d_n=\min(d_{\max},d_0\cdot2^{n-1})+\mathrm{jitter}
\]

A poller running every second works seamlessly with a job retrying two minutes later, because `nextAttemptAt` governs eligibility.

Never call a long `Thread.sleep` inside an SMTP worker waiting to retry; persist the retry schedule in the DB and free capacity.

## 29. SMTP Submission Outcome Differs From Delivery

| Status | Meaning |
| --- | --- |
| `READY` | Due job, not yet claimed |
| `PROCESSING` | Worker holds lease and is working |
| `SUBMITTED` | SMTP transport/relay reported success |
| `RETRY_WAIT` | Waiting for retry time |
| `FAILED` | No further retries per policy |
| `AMBIGUOUS` | Unclear whether server accepted the message |
| `DELIVERED` | Downstream evidence from provider per source definition |

`JavaMailSender.send(...)` succeeding does not mean the recipient saw the email in their Inbox. Providers may still filter, defer, or bounce it.

An SMTP timeout after DATA can occur when the relay accepted the message but the client lost the final response. Retrying risks duplicates. Batching and polling do not provide exactly-once delivery on their own.

## 30. Multiple Instances and Total Poll Load

Suppose each instance uses batch 20, polls every second, across 5 instances:

```text
5 instances × 20 jobs/poll × 1 poll/s
≈ 100 jobs/s claim supply upper bound
```

This is not guaranteed throughput. Atomic DB claiming, SMTP rate, and total concurrency determine real throughput.

When autoscaling:

- Total DB poll queries increase.
- Total `maxInFlight` increases.
- Per-JVM rate limiters can exceed the global provider quota.
- Instances may poll in sync, creating spikes.
- Jobs need ownership/lease IDs for tracing.
- Priority/fairness must stay consistent across workers.

You can choose a single leader poller or multiple pollers with atomic claims. A leader reduces duplicate queries but needs failover; multiple pollers scale horizontally but need rate coordination. Choose based on scale and HA goals.

## 31. Fairness Between OTPs and Newsletters

If a campaign inserts tens of thousands of jobs, a simple `ORDER BY priority DESC` poller can still saturate slots or starve lower-priority categories.

Strategies:

- Separate queues for security, transactional, and marketing mail.
- Reserved worker capacity for high-priority mail.
- Per-category batch quotas.
- Weighted fair scheduling.
- Separate provider budgets per mail class where appropriate.
- Deadline-aware processing.
- Per-tenant/campaign limits.

Never just raise batch size to fix OTP latency while newsletters hog all sender threads. Separating queues and capacity is far more effective.

## 32. One Batch Does Not Equal One MIME Message

For 1,000 recipients:

- 1,000 jobs of 1 recipient each.
- 100 jobs of 10 recipients each.
- 1 job with 1,000 recipients.

All three target the same recipient count yet differ drastically in DB batch size, provider quotas, and bounce/consent tracking.

When personalization, unsubscribes, and per-recipient delivery tracking are required, one logical notification per recipient is usually easier to operate despite more job rows. Never compare job-based batch sizes with recipient-based quotas without normalizing units.

## 33. Adaptive Polling When Empty vs. Backlogged

One strategy:

```text
Empty polls repeatedly
       |
       v
Increase idle delay (bounded)
       |
       v
New job wake-up OR next periodic poll
       |
       v
Jobs available and worker capacity free
       |
       v
Use shorter busy delay / bounded drain
```

App-specific config example:

```yaml
app:
  mail:
    dispatch:
      idle-poll-delay: PT5S
      busy-poll-delay: PT0.5S
      batch-size: 25
```

This does not happen automatically with `@Scheduled(fixedDelayString=...)`. To vary intervals dynamically, use `TaskScheduler` or a custom worker loop.

Never shrink busy delay indefinitely when workers are saturated or the provider is down: polling faster then only wastes DB resources.

## 34. Jitter When Many Instances Start Polling Together

If multiple instances start simultaneously:

```text
Instance A: 0s, 1s, 2s, 3s
Instance B: 0s, 1s, 2s, 3s
Instance C: 0s, 1s, 2s, 3s
```

The DB may see simultaneous claims at identical ticks. Use startup staggering or mild polling jitter while SQL atomic claiming still guarantees safety.

Jitter only smooths load; it does not replace indexes/locking and must not breach job-detection SLOs.

## 35. Cron, Timezones, and scheduled_at

If a job has a future `nextAttemptAt`:

- Store exact instants as UTC/`Instant`.
- Compute quiet hours in the recipient's `ZoneId` if business rules require it.
- Handle DST (missing/repeated hours) when converting local schedules.
- Check expiry/deadlines before submitting.
- Keep application and database clocks synchronized for time comparisons.

For example, a job due at 09:00:01 may be picked up near 09:01 with 1-minute polling. Tuning intervals will not fix timezone bugs, miscalculated due times, or stale business state.

## 36. Backlogs During a Provider Outage

During an SMTP outage:

```text
SMTP 421 / connection failures increase
          |
          v
Worker attempts slow / fail
          |
          v
RETRY_WAIT and READY backlog increase
          |
          v
Poller still queries frequently
```

Increasing batch size here just claims more jobs only to fail and retry them, creating storms. Instead:

1. Classify temporary, permanent, and configuration errors.
2. Reduce rate and concurrency per provider cooldown.
3. Persist `nextAttemptAt` for retries.
4. Use jitter to spread retries.
5. Keep jobs in durable storage rather than pushing infinitely into memory.
6. Monitor backlog age and business deadlines.
7. Consider circuit breakers to pause claiming for failing providers.

A provider outage is never cured by polling the DB faster.

## 37. Metrics for Pollers and Senders

| Suggested metric | Question answered |
| --- | --- |
| `mail_poll_total` | How many polls ran? |
| `mail_poll_empty_total` | What is the empty poll ratio? |
| `mail_poll_duration_seconds` | How long do queries/dispatches take? |
| `mail_claim_batch_size` | How many jobs are claimed per poll? |
| `mail_ready_count` | How many jobs are waiting? |
| `mail_oldest_due_age_seconds` | How old is the oldest due job? |
| `mail_processing_count` | How many jobs currently hold leases? |
| `mail_expired_lease_total` | How many jobs were reclaimed? |
| `mail_send_inflight` | How many attempts are currently active? |
| `mail_smtp_duration_seconds` | What are P50/P95/P99 SMTP durations? |
| `mail_submission_total` | Outcomes by provider and category? |
| `mail_retry_scheduled_total` | How many retries were scheduled? |
| `mail_executor_rejected_total` | Is the executor overloaded? |
| `mail_provider_throttle_total` | Is the provider throttling? |

Metric names are application-defined examples, **not built-in Spring Mail metrics**.

Separate due `READY` backlogs, not-yet-due `RETRY_WAIT`, and active-lease `PROCESSING`. Lumping them together misleads operators.

Never use email addresses or notification IDs as metric labels due to PII and high cardinality.

## 38. Structured Logs and Correlation

Every logical email should have a stable `notificationId`; every attempt should have an `attemptId`.

```json
{
  "event": "mail.outbox.claimed",
  "notificationId": "N-2105",
  "attemptId": "A2",
  "workerId": "mail-worker-3",
  "claimBatchSize": 12,
  "status": "PROCESSING",
  "leaseUntil": "2026-11-12T10:05:00Z"
}
```

When SMTP succeeds:

```json
{
  "event": "mail.smtp.submitted",
  "notificationId": "N-2105",
  "attemptId": "A2",
  "provider": "primary-smtp",
  "smtpDurationMs": 742,
  "outcome": "SUBMITTED"
}
```

Tracing context can drop across the outbox/worker boundary after commit. Durable correlation IDs link business events, pollers, SMTP attempts, and provider events.

Never log passwords, OTPs, raw MIME bodies, or attachment contents in telemetry.

## 39. Two Worked Examples

### Example A: OTP requiring fast issuance

Suppose total submit P95 target is 3 seconds, SMTP P95 is ~1.1 seconds, and prepare/update takes ~0.3 seconds. Remaining budget for detection/queue/rate delay is roughly 1.6 seconds under a simplified estimate.

A 5-second poll interval alone yields a P95 detection delay near 4.75 seconds under uniform arrivals, missing the target. A shorter interval or wake-up signal is needed, assuming DB and SMTP have capacity.

Batch size does not need to be large: just enough to feed free worker slots. OTPs also need TTLs and anti-abuse controls; never send expired tokens just to "clear the backlog".

### Example B: 36,000-email campaign in 2 hours

Theoretical minimum average rate:

\[
36{,}000/(2\cdot3600)=5\ \text{jobs/s}
\]

If the provider allows only 3 messages/s, no batch/interval setting can finish in two hours while respecting quotas. Either adjust expectations or legitimately expand provider capacity.

If sender capacity is 8 jobs/s, claiming 40 every 5 effective seconds supplies ~8 jobs/s, leaving little headroom for retries or spikes. Tune against P95 and peak traffic, not flattering averages.

## 40. Load Tests and Integration Tests

**Unit tests:**

- Reject `batchSize=0` or negative delays.
- Do not query/claim DB when zero slots are free.
- With configured batch 20 and 5 permits available, claim `<= 5`.
- Claiming 2 of 5 requested rows releases the 3 unused permits.
- Executor task rejection releases the permit while durable jobs recover cleanly.
- Jobs before `nextAttemptAt` are not claimed.
- Worker completion and exceptions both release capacity.

**Database integration tests:**

- Two competing pollers never claim ownership of the same row.
- `SKIP LOCKED` skips locked records.
- Batch limits are respected.
- Expired leases are reclaimed.
- Stale owners cannot overwrite a new owner's results.
- Races between cancel/expire and claim never cause invalid sends.
- Query plans stay stable with many historical rows in the table.

**SMTP integration tests:**

- GreenMail or an SMTP capture server receives the exact expected messages in the happy path.
- Temporary errors transition to `RETRY_WAIT` with backoff.
- No jobs are lost when the SMTP server goes temporarily offline.
- DB state failures after SMTP accepted follow the duplicate policy.
- Rate limiters do not exceed simulated quotas.
- Never report delivered solely from `send()` success.

**Load tests:**

- Idle, steady, burst, and provider-outage workloads.
- Small/large message sizes and attachment I/O.
- Multi-instance autoscaling.
- Crashes/restarts mid-claim.
- P50/P95/P99 metrics for queue age, SMTP duration, and DB claim time.
- Lease expirations and executor rejections.

Never run load tests using production recipient addresses to avoid spam, quota burn, and data leaks.

## 41. Iterative Controlled Tuning Loop

1. Measure baseline traffic: arrival rate, batch, effective poll cycle, concurrency, and quotas.
2. Build a representative workload including retries and large attachments.
3. Identify the bottleneck: poller supply, SMTP threads, provider, storage, or DB.
4. If poller supply is low while workers sit idle, modestly raise batch size or shorten interval.
5. If empty polls dominate, lengthen idle interval or add wake-ups.
6. If workers are saturated or provider throttled, never claim more just because backlog grew.
7. Bound `maxInFlight`, queue depth, and lease validity.
8. Watch P95/P99 latency, expired leases, rejections, and DB load.
9. Check how multiple instances multiply total poll rate.
10. Test outages and recovery before deploying to production.
11. Change one parameter group at a time to isolate effects.
12. Preserve headroom, monitor post-deploy, and roll back if metrics degrade.

Never auto-tune solely on backlog length. A rising backlog may come from a provider outage, where raising batch size only creates more in-flight failed attempts.

## 42. Quick Incident Runbook

| Symptom | What to inspect | Action |
| --- | --- | --- |
| `READY` backlog grows, workers idle | Effective poll interval, batch, SQL time | Optimize claiming/batch/interval |
| `READY` backlog grows, workers always full | SMTP P95, quotas, render I/O | Expand valid capacity or pacing |
| Many empty polls | Empty ratio, app instance count | Lengthen idle delay, use wake-ups |
| High `PROCESSING`, leases expiring | In-flight count, executor queue, SMTP timeouts | Shrink claims, manage leases |
| Frequent SMTP 421/4xx | Provider quotas/cooldowns | Throttle rate, apply backoff |
| Transactional slow during large marketing | Category fairness, shared pool | Separate queues/budgets |
| Duplicate email sent | Claim race, stale owner, ambiguous send | Atomic claiming, fencing, reconcile |
| DB CPU/queries spike after scale-out | Poll volume, query plans, locks | Adjust intervals/indexes/coordination |
| Job never gets sent | `nextAttemptAt`, expiry, suppression, owner | Classify state and investigate |
| SMTP accepted but customer never received | Provider delivery/bounce events | Do not treat polling as delivery evidence |

## 43. Anti-Patterns to Avoid

| Mistake | Consequence |
| --- | --- |
| Picking batch 1,000 to "send fast" | Lease expirations, memory pressure, duplicates |
| Polling every 10ms when mostly empty | DB query storm |
| Using batch size as an SMTP rate limiter | Provider throttling |
| Treating configured interval as actual cycle | Miscalculated capacity |
| `SELECT` then send without atomic claim | Multiple instances double-send |
| Holding DB transactions across SMTP | Long locks; DB rollback cannot undo mail |
| Claiming more than executor capacity | Queued tasks expire leases |
| Using an in-memory queue as job source | Jobs lost on process restart |
| Retrying on every poll without backoff | Retry storm |
| Huge leases to hide bottlenecks | Slow crash recovery |
| No fencing for expired-lease owners | Stale updates corrupt status |
| Not prioritizing OTPs over newsletters | Security mail delayed |
| Treating `send()` success as delivered | False reporting |
| Assuming timeouts definitely weren't sent | Duplicates after retry |
| Using raw recipients as metric labels | PII leaks and extreme cardinality |
| Watching only averages, ignoring P95/P99 | Misses tail latency and expirations |

## 44. Sample Configuration **for Testing**, Not a Universal Standard

```yaml
app:
  mail:
    dispatch:
      batch-size: 20
      poll-delay: PT1S
      max-in-flight: 20
      lease-duration: PT2M
      max-attempts: 5
```

Meaningful only after verifying:

- Peak workload and message sizes.
- SMTP provider rate and concurrency quotas.
- Appropriate worker pool and bounded queue.
- Leases exceeding required duration or using renewal.
- DB claim queries stay within load limits.
- Backoff and circuit breakers for provider failures.
- Deadlines and suppressions checked before submission.
- Category fairness protecting OTP latency.
- P95/P99 meeting SLOs via real measurements.

An app sending one email/minute needs completely different numbers from one sending tens of thousands per hour.

## 45. Implementation Checklist

1. Define the batch unit clearly as **outbox jobs**, not confused with recipients.
2. Define SLOs from commit/due time to SMTP accepted.
3. Measure peak arrivals, SMTP duration, and provider quotas.
4. Size bounded worker pools, `maxInFlight`, and leases before raising batch size.
5. Treat `batchSize` as a **ceiling**, claiming only to available capacity.
6. Understand `fixedDelay` vs. `fixedRate` and measure effective poll cycles.
7. Use short transactions with atomic claims, leases, and owner fencing.
8. Never call SMTP under a DB lock.
9. Keep retry backoff independent of polling interval.
10. Coordinate global provider rates across multiple instances.
11. Enforce category fairness between transactional and bulk mail.
12. Measure empty polls, claim time, ready age, in-flight count, expired leases, and SMTP outcomes.
13. Test concurrency, outages, restarts, and ambiguous sends.
14. Tune one variable at a time from metrics—never copy blindly.
15. Preserve durable status and notification IDs across all attempts.

## 46. Takeaways

- Batch size governs **maximum jobs claimed per round**.
- Polling interval governs **cadence of discovering due jobs**.
- Both are distinct from sender concurrency, provider rate limits, and retry intervals.
- Claim supply is roughly `batchSize / effectivePollCycle` when enough jobs are waiting.
- Actual throughput is capped by SMTP latency/concurrency, providers, DB, and storage.
- With `fixedDelay`, effective cycle includes the poll method's runtime.
- Too small a batch starves workers; too large a batch causes queueing and lease expirations.
- Polling too fast burdens the database; polling too slow raises detection latency.
- Claim to available capacity rather than dumping unbounded jobs into executors.
- `FOR UPDATE SKIP LOCKED` lets multiple pollers claim safely in short transactions.
- Leases require owner/version guards and recovery—not permanent DB locks.
- Retries use `nextAttemptAt` + backoff/jitter rather than re-sending on every poll.
- Multi-instance scaling increases total poll load and global quota pressure.
- SMTP timeouts after DATA can be `AMBIGUOUS`, risking duplicates on retry.
- Monitoring must distinguish `READY`, not-yet-due `RETRY_WAIT`, and `PROCESSING` leases.
- Pick numbers from SLOs, peak volumes, and real load tests.

**Core principle:** pick a **batch size large enough to fill idle capacity without claiming jobs before they can be processed**, and a **polling interval short enough to meet detection-latency SLOs without generating wasteful polling load**. A Spring Framework Mail outbox runs reliably through atomic claiming, bounded in-flight work, SMTP quota control, retry scheduling, and observability—not from picking the largest batch size or fastest SELECT cadence.

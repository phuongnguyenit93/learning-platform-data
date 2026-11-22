# Handling Scheduled Tasks and Expired Data After a Pause

A CRaC checkpoint saves the process state at a point in time, but external time continues to pass while the process is paused. A scheduled task may have missed its run schedule, an access token may have expired, a cache may be stale, a session may have been revoked, and a lease may have been granted to another replica. After restore, objects in the heap may still hold old values even though the actual state of the system has changed.

Therefore, the application needs to clearly define what must happen to schedulers and time-limited data during checkpoint/restore. You cannot simply restore a thread waiting on an old delay and assume the schedule is still accurate. Nor can you treat a cache entry, token, or lock remaining in the heap as still valid.

This practice exercise builds an approach for handling two groups of state:

- **Scheduled tasks:** schedules, missed runs, in-progress work, retries, schedulers, and job ownership.
- **Expired data:** TTL, caches, tokens, sessions, certificates, leases, locks, and business deadlines.

The goal is to ensure the application continues correctly after time has elapsed, without unbounded catch-up runs, without missing mandatory work, without repeating side effects, and without using expired data.

## 1. Why Does Pause Time Change Application State?

Suppose a service is checkpointed at 09:00. The JVM is restored at 11:30. During those two and a half hours:

- A data synchronization job was scheduled to run at 09:15, 09:30, and 09:45.
- An access token expired at 10:00.
- A cache entry with a 20-minute TTL has expired.
- A leader lease with a 60-second duration has been granted by the coordinator to another replica.
- A certificate may have been rotated.
- A login session has been revoked.
- The retry deadline of an operation may have passed.

The heap snapshot still contains objects created at 09:00. If the application uses these values directly after restore, incorrect behavior may occur:

- The scheduler runs three times in a burst or does not run at all even though the business logic requires processing.
- The client sends an expired token to an external service.
- The cache returns stale data.
- The old replica continues writing using a lost lease.
- A retry re-executes a side effect that has already completed.
- A job whose deadline has expired is still processed as if it were new.

The key point is to distinguish **snapshotted state** from **state that is still valid at the current time**. CRaC restores process state; the application must re-evaluate conditions that depend on time and external systems.

### 1.1. Time Categories to Consider

| Category | Examples | What to Verify After Restore |
|---|---|---|
| Recurring schedule | Cron, fixed-rate, fixed-delay | Next schedule and missed-run handling policy |
| Business deadline | Payment deadline, reservation hold time | Whether the deadline is still valid or must transition state |
| Data TTL | Cache, session, temporary record | Whether data is still valid or needs to be evicted |
| Credential | Access token, refresh token, certificate | Whether credential is still valid and could have been revoked |
| Lease/lock | Leader lease, distributed lock | Whether ownership still exists or must be reacquired |
| Retry/backoff | Next attempt of an operation | Whether the retry window is still open and the attempt is still needed |
| Technical timeout | Connection idle timeout, DNS TTL | Whether connections or caches need to be recreated |
| Elapsed time measurement | Duration of callback, job | Use monotonic clock to measure intervals |

### 1.2. Not Every Missed Task Needs a Catch-Up Run

A missed run may need to be:

- Skipped if the data only needs the latest state.
- Coalesced into a single run to update the current state.
- Caught up period by period if each period has business significance.
- Placed into a durable queue for ordered processing.
- Canceled if the deadline or retry window has expired.

For example, a cache refresh job may only need to run once after restore to load the latest data. A daily invoicing job may have to generate invoices for every missed day. Do not use a single catch-up policy for all schedulers.

## 2. Distinguishing Absolute Time and Relative Time

Proper design starts with choosing the right type of time.

### 2.1. Absolute Time

Absolute time represents a point on the timeline, typically using Instant:

~~~java
Instant expiresAt = Instant.parse("2026-11-13T10:00:00Z");
~~~

This value can be persisted durably, passed across services, and compared after the process is paused. After restore, the application gets the current time from Clock and checks:

~~~java
boolean expired = !clock.instant().isBefore(expiresAt);
~~~

Absolute time is suitable for:

- Expiration time of a token or session.
- Business deadlines.
- Execution time of a specific schedule.
- Creation or expiration time of a cache entry.
- Lease expiration according to the coordinator's contract.

### 2.2. Relative Time

Relative time describes an interval such as "wait 30 seconds" or "run again after 5 minutes". Schedulers typically use relative delays to schedule an execution:

~~~java
executor.schedule(task, 30, TimeUnit.SECONDS);
~~~

Relative delays are useful within a running process, but should not be the sole source of truth for business deadlines across a checkpoint. On restore, recalculate the delay from the absolute timestamp or from durable state.

For example, if a token expires at 10:00 and the application restores at 10:20, continuing a "5 minutes remaining" timer created at 09:55 will be wrong. Read expiresAt, compare it with the current time, and fetch a new token.

### 2.3. System.nanoTime() and Instant

System.nanoTime() is suitable for measuring durations and timeouts within a single run. Its value has an arbitrary origin and is only meaningful when comparing differences between readings in the same execution environment. Do not store a nanoTime value in a database or checkpoint metadata and treat it as an absolute timestamp.

Practical rules:

- Use Instant or epoch timestamps for expiration times and deadlines that must survive restore.
- Use System.nanoTime() to measure processing time or short timeouts within the current process.
- After restore, recreate relative timers from the absolute deadline and the current Clock.
- Do not subtract wall-clock timestamps from two machines without handling clock skew.

### 2.4. Inject Clock for Testing

Do not scatter Instant.now() calls throughout business logic if you need to test time. Inject Clock:

~~~java
public final class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

In production, use Clock.systemUTC(). In tests, use Clock.fixed() or a controllable clock to advance time without actually waiting.

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-13T10:30:00Z"),
        ZoneOffset.UTC);

ExpirationPolicy policy = new ExpirationPolicy(fixedClock);
~~~

Clock injection helps accurately test expired tokens, TTLs, missed schedules, and deadlines after restore.

## 3. Building Policies for Scheduled Tasks

Before changing code, define the semantics of the schedule. Different schedule types require different recovery approaches.

### 3.1. Fixed-rate

Fixed-rate schedules executions at regular intervals from an initial point in time. For example: 10:00, 10:05, 10:10, 10:15.

~~~java
executor.scheduleAtFixedRate(
        task,
        0,
        5,
        TimeUnit.MINUTES);
~~~

With scheduleAtFixedRate, the schedule is based on a periodic cadence. If one execution takes longer than the period, subsequent executions may start late; the same periodic task will not be executed concurrently by that same executor. After a pause, do not assume the internal timer will automatically produce the exact business behavior the system expects.

### 3.2. Fixed-delay

Fixed-delay calculates the pause interval after the previous execution completes:

~~~java
executor.scheduleWithFixedDelay(
        task,
        0,
        5,
        TimeUnit.MINUTES);
~~~

This style is suitable when you need to wait an interval after each completion, such as checking a dependency 5 minutes after the previous check. It is not equivalent to a fixed wall-clock schedule.

After restore, determine whether you need to wait 5 minutes from when the job restarts, or return to the original fixed schedule. That is a business decision, not an executor implementation detail.

### 3.3. Calendar Schedule and Cron

A schedule like "02:00 every day in timezone Asia/Ho_Chi_Minh" is a calendar schedule. The interval between two runs may not always be 24 hours due to daylight saving time in some regions.

A calendar schedule needs to store:

- Zone ID, for example Asia/Ho_Chi_Minh or Europe/Berlin.
- Cron rule or local time.
- Policy when a local time does not exist due to DST springing forward.
- Policy when a local time occurs twice when DST ends.
- Missed-run policy after the application stops.

Do not store a fixed 24-hour delay and use it as a substitute for a "daily at 02:00" schedule across all timezones.

### 3.4. Choosing a Missed-Run Policy

| Policy | Behavior After Restore | Suitable Examples |
|---|---|---|
| Skip | Discard past runs, schedule the next future run | Refresh cache, poll current state |
| Coalesce | If one or more runs were missed, run once to catch up to the latest state | Snapshot synchronization, state aggregation |
| Catch-up | Execute each missed occurrence in order | Daily interest calculation, periodic reporting |
| Durable replay | Read incomplete occurrences from queue/store and process idempotently | Billing, reconciliation, workflow |
| Expire | Cancel occurrences past their deadline | Time-limited notifications or offers |

The policy must be clearly documented in operational documentation and acceptance criteria. If a job has side effects, define a business key for each occurrence to avoid duplicate processing.

### 3.5. Persisting Durable Progress

For critical work, do not rely on a lastRun variable living only in the heap. Persist progress in a database or durable scheduler:

| Field | Meaning |
|---|---|
| job_name | Logical name of the job |
| scheduled_for | Expected timestamp of the occurrence |
| status | PENDING, RUNNING, SUCCEEDED, FAILED, EXPIRED |
| attempt | Attempt count |
| lease_owner | Worker currently holding processing ownership |
| lease_until | Lease expiration timestamp |
| completed_at | Completion timestamp |
| idempotency_key | Key to prevent duplicate side effects |

An occurrence can be identified by (job_name, scheduled_for) or another stable job key. A unique constraint prevents multiple replicas from creating two records for the same occurrence.

## 4. Preparing the Scheduler Before Checkpoint

A scheduler is a resource that must be managed intentionally. Before checkpoint, the application needs to stop creating new tasks, handle running tasks, and put the scheduler into a state that can be reinitialized.

### 4.1. Stop Accepting New Schedules

When starting to quiesce:

1. Mark the scheduler as stopping.
2. Do not register new tasks.
3. Cancel future runs stored only in memory if they will be recalculated after restore.
4. Keep progress of critical jobs in the durable store.
5. Wait for running tasks to complete or cancel according to policy.

Do not let a scheduler thread continue creating side effects while other Resources are closing the database pool or broker client.

### 4.2. Drain Running Tasks

For each job, determine:

- Can it complete within the pre-checkpoint timeout?
- Can it stop safely at a transaction boundary?
- If interrupted, can the job be retried?
- Has the current progress been durably persisted?
- Are the side effects idempotent?

If a task cannot drain within the timeout, the checkpoint should be rejected or the job must save a durable business checkpoint. Do not checkpoint a task that is in an unclear commit/rollback state.

### 4.3. Avoid Keeping ScheduledFuture as the Source of Truth

ScheduledFuture is in-process coordination state. It should not be the authoritative source for whether a business occurrence has completed.

After restore, rebuild the schedule from:

- Schedule rule.
- Current Clock.
- Last successful run persisted durably.
- Pending occurrences.
- Missed-run policy.

The Future is merely the mechanism for the executor to run the next execution after the policy has been computed.

### 4.4. Handling Callback Failures

If the beforeCheckpoint callback cannot drain tasks or close the scheduler, fail the checkpoint explicitly. The application needs a way to roll back the quiescing state if the checkpoint is aborted: restart the scheduler or put the instance into a controlled shutdown.

Do not mark the callback as successful when jobs are still running or the scheduler could produce side effects during checkpoint. For jobs that cannot be safely interrupted, prefer waiting for completion within a deadline or rejecting the checkpoint.

## 5. Reinitializing the Scheduler After Restore

After restore, do not just resume an old delay. Create a new scheduler or reconfigure the scheduler according to the supported lifecycle, calculate the next run from the current time, and apply the missed-run policy.

### 5.1. Recovery Procedure

1. Create a new scheduler/executor.
2. Read the current schedule configuration.
3. Read durable job progress.
4. Identify occurrences missed during the pause.
5. Apply Skip, Coalesce, Catch-up, Durable replay, or Expire.
6. Verify dependencies and job ownership.
7. Schedule valid runs.
8. Open readiness once the application can serve according to policy.

If the scheduler runs jobs that require a database, broker, or secret manager, ensure those dependencies are ready before allowing jobs to start. Do not rely on arbitrary callback ordering between resources to guarantee dependencies initialize before the scheduler.

### 5.2. Example: Calculating the Next Run by Local Time

The following example calculates the next daily execution time given a ZoneId and LocalTime:

~~~java
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class DailySchedule {
    private final ZoneId zone;
    private final LocalTime runAt;

    public DailySchedule(ZoneId zone, LocalTime runAt) {
        this.zone = zone;
        this.runAt = runAt;
    }

    public Instant nextOccurrence(Instant now) {
        ZonedDateTime localNow = now.atZone(zone);
        ZonedDateTime candidate = localNow.toLocalDate()
                .atTime(runAt)
                .atZone(zone);

        if (!candidate.toInstant().isAfter(now)) {
            candidate = localNow.toLocalDate()
                    .plusDays(1)
                    .atTime(runAt)
                    .atZone(zone);
        }

        return candidate.toInstant();
    }
}
~~~

atZone() applies Java's DST handling rules for nonexistent or repeated local times. If the business logic requires different rules, handle them explicitly and test against the corresponding ZoneId. For services needing global schedules, store both the occurrence instant and the zone/rule used to generate it.

### 5.3. Example: CRaC Scheduler Using One-Shot Schedule

The example below illustrates a cleanup job running daily at a local time. The scheduler cancels the future run before checkpoint, waits for the current task to complete, and creates a new executor after restore. Each run receives scheduledFor so it can record the occurrence and execute idempotently.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class DailyCleanupResource implements Resource {
    @FunctionalInterface
    public interface CleanupJob {
        void run(Instant scheduledFor) throws Exception;
    }

    private final Object lock = new Object();
    private final Clock clock;
    private final DailySchedule schedule;
    private final CleanupJob job;

    private ScheduledThreadPoolExecutor executor;
    private ScheduledFuture<?> nextRun;
    private boolean stopping;

    public DailyCleanupResource(
            Clock clock,
            ZoneId zone,
            LocalTime runAt,
            CleanupJob job) {
        this.clock = clock;
        this.schedule = new DailySchedule(zone, runAt);
        this.job = job;
        Core.getGlobalContext().register(this);
        start();
    }

    private void start() {
        synchronized (lock) {
            if (executor != null && !executor.isShutdown()) {
                return;
            }

            stopping = false;
            executor = new ScheduledThreadPoolExecutor(1);
            executor.setRemoveOnCancelPolicy(true);
            executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
            executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
            scheduleNextLocked(executor);
        }
    }

    private void scheduleNextLocked(ScheduledThreadPoolExecutor current) {
        Instant now = clock.instant();
        Instant scheduledFor = schedule.nextOccurrence(now);
        long delayMillis = Math.max(
                0L,
                Duration.between(now, scheduledFor).toMillis());

        nextRun = current.schedule(
                () -> executeAndReschedule(current, scheduledFor),
                delayMillis,
                TimeUnit.MILLISECONDS);
    }

    private void executeAndReschedule(
            ScheduledThreadPoolExecutor current,
            Instant scheduledFor) {
        synchronized (lock) {
            if (stopping || executor != current) {
                return;
            }
            nextRun = null;
        }

        try {
            job.run(scheduledFor);
        } catch (Exception failure) {
            // Log/metric and save failure status according to the job's policy.
            // Do not mark the occurrence as succeeded when the job fails.
        } finally {
            synchronized (lock) {
                if (!stopping
                        && executor == current
                        && !current.isShutdown()) {
                    scheduleNextLocked(current);
                }
            }
        }
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        ScheduledThreadPoolExecutor current;

        synchronized (lock) {
            stopping = true;
            current = executor;
            executor = null;

            if (nextRun != null) {
                nextRun.cancel(false);
                nextRun = null;
            }
        }

        if (current == null) {
            return;
        }

        current.shutdown();
        if (!current.awaitTermination(30, TimeUnit.SECONDS)) {
            current.shutdownNow();
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Cleanup scheduler did not stop before checkpoint");
            }

            // Checkpoint will be aborted because the callback threw an exception.
            // Re-arm scheduler after the old executor has stopped.
            start();
            throw new IllegalStateException(
                    "Cleanup task exceeded checkpoint drain deadline");
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        start();
    }
}
~~~

This is an illustrative skeleton. CleanupJob needs to persist occurrence status to a durable source, have an idempotency key, and handle errors explicitly. In a real application, starting the scheduler should be coordinated after mandatory dependencies have recovered; do not let tasks run before the database, secrets, or coordinator.

The example chooses the Skip policy for the daily schedule: nextOccurrence() returns the next future run. If the application needs Catch-up or Durable replay, it must query missed occurrences from the database/queue instead of only calculating the next single run.

If the callback times out and shutdownNow() interrupts the job, the job must support interruption and idempotency. When a task cannot stop, do not start a second scheduler running the same job; keep the instance not ready and let the operations system handle it according to policy.

## 6. Handling Missed Runs

### 6.1. Skip

Skip discards all past occurrences and only schedules the next one in the future.

Suitable for:

- Refreshing cache from the current source.
- Polling the latest state.
- Cleaning up data that can be rescanned in full.
- Jobs that do not produce a separate result per period.

Example: a config sync job running every 5 minutes. After stopping for 2 hours, run once to fetch the latest config and then continue the cycle.

### 6.2. Coalesce

Coalesce merges multiple missed occurrences into one representative run. The job needs to know the missed time range to process the corresponding data.

Example: a metrics aggregation job running every 10 minutes can accept from and to, and aggregate all data in the missed interval in one run.

Do not coalesce if each occurrence requires a separate side effect, such as sending one invoice per day.

### 6.3. Catch-up

Catch-up executes each missed occurrence in order. You need to limit:

- Maximum number of occurrences in a batch.
- Maximum time allocated for catch-up.
- Concurrency and dependency ordering.
- Retries and backoff.
- Condition to skip occurrences that are too old.

If a job missed 1,000 runs, do not spawn 1,000 concurrent threads or requests immediately after restore. Run in batches, with backpressure and backlog monitoring.

### 6.4. Durable Replay

For critical business logic, store occurrences in a database or message queue. Each occurrence has a status, idempotency key, and lease. After restore, workers query incomplete occurrences and claim them using transactions/locking.

Example:

~~~sql
CREATE TABLE scheduled_occurrence (
    job_name       VARCHAR(100) NOT NULL,
    scheduled_for  TIMESTAMP WITH TIME ZONE NOT NULL,
    status         VARCHAR(20) NOT NULL,
    attempt        INTEGER NOT NULL DEFAULT 0,
    lease_until    TIMESTAMP WITH TIME ZONE,
    completed_at   TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (job_name, scheduled_for)
);
~~~

The primary key prevents creating two occurrences for the same job and timestamp. Workers need to claim using an atomic operation or a transaction with appropriate locking. When the job completes, update the status in the same transaction boundary as the business result if possible.

### 6.5. Expire

An occurrence may no longer have value after a deadline. For example, sending a notification before an appointment or applying an offer valid only within a short window. After restore, if the deadline has passed, mark it EXPIRED instead of catching up.

Criteria to define:

- Where the deadline comes from.
- Which clock is used for comparison.
- Whether a grace period is allowed.
- Whether skipping needs to be audited.
- Whether notification or business compensation is required.

## 7. Expired Data: TTL and Expiration

TTL typically represents the duration for which data is considered valid from a creation or update time. For checkpointable applications, store the absolute expiration timestamp or enough data to recalculate it.

### 7.1. Store expiresAt Instead of Only remainingSeconds

Do not store only:

~~~java
long remainingSeconds = 300;
~~~

because this value does not decrement automatically while the JVM is stopped. Instead, store:

~~~java
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(5));
~~~

After restore:

~~~java
Duration remaining = Duration.between(clock.instant(), expiresAt);
if (remaining.isNegative() || remaining.isZero()) {
    expireEntry();
} else {
    scheduleExpiration(remaining);
}
~~~

expiresAt is the source of truth for validity. Timers only help perform cleanup near that time; every data read must still check expiry.

### 7.2. Lazy Expiration and Background Cleanup

There are two complementary mechanisms:

- **Lazy expiration:** check the expiration timestamp when reading or using data. If expired, do not return the data and mark/remove the entry.
- **Background cleanup:** a scheduler scans and deletes expired data to free memory or storage.

Background cleanup should not be the sole mechanism ensuring expired data is not used. The scheduler may be stopped, errored, or delayed. Checking expiration at the point of use is the proper safeguard.

### 7.3. Cache Entry

A cache entry can store:

~~~java
public record CacheEntry<V>(
        V value,
        Instant expiresAt,
        long sourceVersion) {

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

When reading:

~~~java
public Optional<CacheEntry<String>> getValid(
        String key,
        Clock clock) {
    CacheEntry<String> entry = cache.get(key);
    if (entry == null || entry.isExpired(clock)) {
        cache.remove(key);
        return Optional.empty();
    }
    return Optional.of(entry);
}
~~~

After restore, expired cache entries must be evicted or refreshed. If the data source has a version, verify the version before using critical cached data.

### 7.4. Monotonic-Time-Based Cache TTL

Some caches use System.nanoTime() to compute TTL because a monotonic clock avoids the impact of wall-clock adjustments. This approach works within a single run, but a snapshotted nanoTime value should not be treated as a durable timestamp.

On restore:

- Rebuild cache deadlines from absolute expiresAt if expiry needs to be preserved across pause.
- Or invalidate the cache and reload if deadlines cannot be verified.
- Do not take an old deadlineNanos and subtract the current nanoTime as if the origin is guaranteed unchanged.

If the cache is just regenerable data, invalidating the entire cache after restore is often simpler and safer than trying to preserve complex TTL state.

## 8. Access Tokens, Refresh Tokens, and Sessions

Credentials are time-limited data and can be revoked independently of their expiry timestamp.

### 8.1. Access Token

Do not just check that the token object is non-null. After restore, check:

- exp and nbf if the token has those claims.
- Issuer, audience, and scope.
- Clock skew between client and issuer.
- Whether the token has been revoked or policy has changed.
- Whether the credential is tied to an old workload/replica identity.

You should refresh ahead of expiry by a safety margin, but the decision to use a token must still be based on the current time and the response from the service.

### 8.2. Refresh Token

Refresh tokens can also expire or be rotated. An old refresh token may be invalidated after a successful use. If multiple replicas restore from the same image and the same refresh token, they may refresh concurrently; some providers will only accept the first one or rotate the token causing subsequent attempts to fail.

Solutions:

- Issue credentials per instance or workload identity if the provider supports it.
- Use a distributed refresh coordinator or single-flight mechanism when tokens are shared.
- Store new tokens atomically and protect secrets.
- Do not let multiple replicas overwrite a new refresh token with an old token.
- Check token status before opening readiness if the credential is a mandatory dependency.

### 8.3. Sessions and Cookies

Sessions can expire or be revoked while stopped. A session ID remaining in the heap does not prove the server-side session still exists.

After restore:

- Verify the session with the authoritative store.
- Do not restore authenticated state solely from a boolean flag in the heap.
- If the session is no longer valid, require re-authentication or perform a protocol refresh.
- Do not log sensitive session IDs or cookies.

### 8.4. TLS Certificates and Connections

Open TLS connections should generally not be assumed to be unconditionally resumable after a pause. Closing and recreating connections performs a handshake with the current certificate, trust store, and endpoint.

If a certificate or CA was rotated during the pause, the client after restore must use the new trust material according to policy. Check hostname, chain, and validity period; simply checking if the socket is open is not enough.

## 9. Leases, Distributed Locks, and Leader State

A lease is time-limited ownership granted by a coordinator or storage. A lease can expire while the JVM is stopped. The heap snapshot may still contain isLeader = true, a lock handle, or an old lease token.

### 9.1. Do Not Trust Leader Flags in the Heap

Dangerous example:

~~~java
if (leader) {
    performLeaderWork();
}
~~~

If leader was set to true before checkpoint, the replica could continue running leader work after the lease has been granted to another instance.

After restore:

1. Mark ownership in the heap as unverified.
2. Connect to the coordinator.
3. Acquire a new lease or verify the lease according to the protocol.
4. Obtain a new fencing token/generation.
5. Only perform writes if storage confirms the current token.

### 9.2. Fencing Token

A fencing token is a monotonically increasing value or generation issued by the coordinator. Storage checks the token on every protected operation. When an old replica restores with token N while the new owner has N+1, writes from token N are rejected.

Do not just check the lease in the application and trust that it remains valid until the end of the transaction. Ownership can expire right after the check. The destination receiving the side effect needs to verify the fencing token or an equivalent compare-and-set mechanism.

### 9.3. Distributed Lock

If a lock has a TTL, the lock can expire during a pause. After restore:

- Do not call unlock with an old token if the lock already belongs to another owner.
- Do not continue a critical section based on a snapshotted lock handle.
- Reacquire the lock using the current owner identity.
- Use a fencing token if the operation can write to shared resources.
- Ensure cleanup when acquisition fails.

## 10. Retries, Backoff, and Business Deadlines

Retry state also depends on time. A task may be waiting on backoff at checkpoint; upon restore, the old delay is not necessarily still valid.

### 10.1. Store Absolute retryAt

Store nextAttemptAt or retryDeadline instead of storing only the remaining delay:

~~~java
Instant nextAttemptAt =
        clock.instant().plus(Duration.ofMinutes(2));
~~~

After restore:

~~~java
Instant now = clock.instant();
if (!now.isBefore(nextAttemptAt)) {
    enqueueRetryIfStillNeeded();
} else {
    scheduleRetry(Duration.between(now, nextAttemptAt));
}
~~~

Before retrying, query the operation state to determine whether the previous attempt already executed the side effect. If the outcome is unknown, use an idempotency key or reconciliation.

### 10.2. Expired Retry Window

If retryDeadline has passed, do not continue retrying indefinitely. Transition the operation to an expired state or one requiring intervention according to policy.

Examples:

- Sending an OTP that is only valid for 5 minutes.
- Calling a reservation API that only allows retries for 10 minutes.
- Payments must be reconciled before resending.
- Notifications for an old event may no longer be meaningful.

### 10.3. Backoff and Jitter

When multiple replicas restore at the same time, if all retry immediately, dependencies can suffer a retry storm. Recalculate backoff from durable state, add jitter, and limit concurrency.

Do not use the same snapshotted random seed for all replicas if that seed produces the same jitter sequence. Sources of randomness and retry schedules need to fit a multi-replica model.

## 11. Practice Exercise: Recovering a Scheduler and TTL Cache

This practice exercise builds a service with a job that refreshes a cache every 5 minutes and cache entries that expire after 15 minutes. After checkpoint, we simulate stopping the JVM for 25 minutes and then restoring.

### 11.1. Requirements

- Cache entries have an absolute expiresAt.
- Every cache read checks expiration.
- The scheduler does not use a snapshotted ScheduledFuture as the source of truth.
- The refresh job is idempotent and repeatable.
- After restore, expired cache entries are evicted or refreshed.
- The scheduler calculates the next run from the current Clock.
- Readiness only opens when mandatory dependencies are ready.

### 11.2. Cache Model

~~~java
import java.time.Clock;
import java.time.Instant;

public record TimedValue<V>(
        V value,
        Instant expiresAt,
        String version) {

    public boolean validAt(Clock clock) {
        return clock.instant().isBefore(expiresAt);
    }
}
~~~

### 11.3. Cache Repository

~~~java
import java.time.Clock;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class TimedCache<V> {
    private final ConcurrentHashMap<String, TimedValue<V>> values =
            new ConcurrentHashMap<>();
    private final Clock clock;

    public TimedCache(Clock clock) {
        this.clock = clock;
    }

    public Optional<TimedValue<V>> get(String key) {
        TimedValue<V> entry = values.get(key);
        if (entry == null) {
            return Optional.empty();
        }

        if (!entry.validAt(clock)) {
            values.remove(key, entry);
            return Optional.empty();
        }

        return Optional.of(entry);
    }

    public void put(
            String key,
            V value,
            java.time.Duration ttl,
            String version) {
        Instant expiresAt = clock.instant().plus(ttl);
        values.put(key, new TimedValue<>(value, expiresAt, version));
    }

    public void removeExpired() {
        values.entrySet().removeIf(
                entry -> !entry.getValue().validAt(clock));
    }

    public void invalidateAll() {
        values.clear();
    }
}
~~~

This is an in-memory cache for demonstration. In a real system, if the cache is regenerable and does not need to survive restore, you can call invalidateAll() after restore. If you need to keep the cache, store expiresAt and the data source version, then verify before returning results.

### 11.4. Testing Pause Duration

Suppose:

- A cache entry is created at 09:00 with a 15-minute TTL.
- Checkpoint is created at 09:05.
- Restore happens at 09:30.

Expected results:

- Entry expires at 09:15.
- After restore at 09:30, get() does not return the old entry.
- Background cleanup may remove the entry, but correctness does not depend on whether cleanup has run.
- The refresh job runs according to the chosen missed-run policy.

### 11.5. Testing the Refresh Job

If the refresh only needs the latest state, choose Coalesce: after restore, if one or more runs were missed, execute one refresh and record the skipped interval.

If the job generates a separate report for each 5-minute period, use Durable replay: create occurrences for each period and process idempotently.

Do not use the same scheduler policy for two types of work just because they both run every 5 minutes.

## 12. Testing Time and Edge Cases

### 12.1. Short and Long Pauses

Run tests with multiple pause durations:

- Shorter than the scheduler period.
- Longer than one period.
- Longer than multiple periods.
- Longer than cache TTL.
- Longer than access token expiry.
- Longer than lease duration.
- Longer than retry window.

Each test must define the expected missed-run policy and expiry state.

### 12.2. Clock Skew

In distributed systems, application machines and dependencies can have clock drift. If token expiry or leases are evaluated in multiple places, clock synchronization and a safety margin are needed.

Do not arbitrarily increase the grace period to the point of accepting expired credentials. For tokens, use skew allowance according to the protocol and issuer; for leases, prefer coordinator/fencing semantics rather than comparing local clocks.

### 12.3. DST and Timezones

Test calendar schedules at these points:

- Local hour skipped when transitioning into DST.
- Local hour occurring twice when DST ends.
- Month transitions, leap years, and end-of-month dates.
- Changes to ZoneId or schedule configuration.

If the schedule has global meaning, store the absolute timestamp. If the schedule has local meaning such as "daily at 02:00 branch local time", store both ZoneId and the DST policy.

### 12.4. Adjusted Wall Clock

NTP can slew or step the wall clock. Monotonic-clock-based timers and wall-clock-based deadlines have different purposes. For business deadlines, use an authoritative timestamp and check skew. For internal durations, use a monotonic clock.

In tests, use an injected Clock to simulate time jumping forward or backward. Do not change the production OS clock to test expiration.

### 12.5. Restoring Multiple Replicas Simultaneously

If the same checkpoint is restored into multiple replicas:

- All may compute the same next schedule.
- All may detect the same missed occurrence.
- All may refresh the token simultaneously.
- All may clean up the same dataset.
- All may retry the same operation.

Use distributed claims, unique occurrence keys, idempotency keys, lease/fencing, and jitter. An alreadyRan variable in the heap cannot coordinate multiple processes.

## 13. Observability for Schedulers and Expiration

### 13.1. Lifecycle Logs

Log these events:

- Scheduler quiescing started/finished.
- Number of running tasks and pending occurrences.
- Tasks canceled or completed before checkpoint.
- Checkpoint preparation failed due to undrained tasks.
- Restore started/finished.
- Missed occurrences skipped, coalesced, caught up, or expired.
- New scheduler created and next run calculated.
- Cache entries expired or refreshed.
- Credential refresh succeeded/failed.
- Lease acquire/reacquire and fencing token generation.
- Readiness opened after dependencies are ready.

Each log should include job name, occurrence key, service ID, replica ID, and process incarnation ID. Do not log tokens, session cookies, or secrets.

### 13.2. Suggested Metrics

| Metric | Meaning |
|---|---|
| crac_scheduler_quiesce_duration_seconds | Time to stop and drain the scheduler |
| scheduled_occurrence_missed_total | Number of missed occurrences |
| scheduled_occurrence_skipped_total | Number of occurrences skipped by policy |
| scheduled_occurrence_coalesced_total | Number of coalesced occurrences |
| scheduled_occurrence_replayed_total | Number of caught-up occurrences |
| scheduled_occurrence_expired_total | Number of expired occurrences |
| scheduled_job_duration_seconds | Job execution duration |
| scheduled_job_failure_total | Number of job failures |
| scheduled_job_backlog | Number of unprocessed occurrences |
| cache_entry_expired_total | Number of expired cache entries |
| credential_refresh_failure_total | Number of credential refresh failures |
| lease_reacquire_failure_total | Number of failed lease acquisitions after restore |
| restore_to_scheduler_ready_seconds | Time until the scheduler is allowed to run |

Metric names are suggestions. Avoid using occurrence ID, user ID, or token ID as high-cardinality labels; keep them in controlled logs/traces.

### 13.3. Dashboards

Post-restore dashboards should show:

- Restore-to-ready and scheduler-ready time.
- Missed occurrences by job.
- Backlog and catch-up processing time.
- Job duration and failure rate.
- Cache hit ratio and expired entry count.
- Credential refresh latency/errors.
- Lease reacquire success/failure.
- Readiness and incoming traffic.

If the backlog grows continuously or missed occurrences do not decrease, the scheduler may not be keeping up with load even though the process restored successfully.

## 14. Test Matrix

| Category | Condition | Action | Expected Result |
|---|---|---|---|
| Skip policy | Paused across multiple periods | Restore scheduler | Only future occurrences run |
| Coalesce policy | Multiple refresh runs missed | Restore | Run once to update the latest state |
| Catch-up | Multiple business periods missed | Restore | Catch up in order with batch limits |
| Durable replay | Occurrence still PENDING | Restore multiple workers | Atomic claim, no duplicate business effects |
| Expire policy | Deadline passed | Restore | Occurrence transitions to EXPIRED |
| Cache TTL | TTL expired during pause | Read after restore | Entry is not returned |
| Token expiry | Access token expired | Call API after restore | Refresh before use |
| Refresh token rotation | Multiple replicas restored | Concurrent refresh | One valid flow, no overwriting new token |
| Session revoke | Session revoked while paused | Restore | Old session not accepted |
| Lease expiry | Lease expired and new owner granted | Restore old owner | Reacquire or remain follower |
| Retry deadline | Retry window expired | Restore | Do not retry; transition state per policy |
| Scheduler drain | Long-running job | Checkpoint | Wait for completion or reject checkpoint |
| Dependency unavailable | DB not ready | Restore | Scheduler does not run DB-dependent jobs yet |
| DST | Restore across DST boundary | Compute next occurrence | Respects ZoneId and DST policy |
| Clock adjustment | Clock jumps forward/backward | Restore and check TTL | Do not use old nanoTime deadlines |
| Multi-replica | N replicas from same image | All see pending occurrence | Only one claim or idempotent effect |

## 15. Acceptance Criteria

**AC-01 — Scheduler does not use old delay**

- Condition: create a checkpoint when the scheduler already has a future task scheduled.
- Action: pause the process longer than the initial delay and then restore.
- Result: the next run is recalculated from the schedule rule and current time.
- Evidence: scheduledFor, nextRun, and scheduler lifecycle logs.

**AC-02 — Running tasks are handled safely**

- Condition: a job is running when checkpoint starts.
- Action: request checkpoint.
- Result: the job completes at a safe boundary or checkpoint is rejected; no incomplete side effect is treated as successful.
- Evidence: job status, transaction record, and callback result.

**AC-03 — Missed-run policy**

- Condition: the application is stopped across at least three occurrences.
- Action: restore.
- Result: Skip, Coalesce, Catch-up, Durable replay, or Expire executes according to the configured policy.
- Evidence: occurrence records and business effect count.

**AC-04 — Cache TTL**

- Condition: cache entry expires while the JVM is stopped.
- Action: restore and read the entry.
- Result: entry is not returned; data is refreshed or a cache miss is reported.
- Evidence: expiresAt, cache lookup, and source version.

**AC-05 — Expired credentials**

- Condition: access token expires before restore.
- Action: perform a protected request.
- Result: old token is not sent; new credential is issued before the request proceeds.
- Evidence: issuer/service audit metadata, without storing plaintext tokens.

**AC-06 — Stale lease**

- Condition: lease expires and another owner receives a new fencing token.
- Action: restore old replica and request a write using the old token.
- Result: write is rejected; old replica only operates after acquiring new ownership.
- Evidence: coordinator record and storage response.

**AC-07 — Multi-replica schedule**

- Condition: at least three replicas restore from the same checkpoint and all see a pending occurrence.
- Action: all attempt to claim it.
- Result: one valid owner processes the occurrence or all executions are deduplicated by business key.
- Evidence: unique occurrence record, lease owner, and effect ledger.

**AC-08 — Readiness**

- Condition: mandatory dependency is not ready after restore.
- Action: observe scheduler and readiness.
- Result: dependent jobs do not run and the instance does not receive traffic until the dependency meets conditions.
- Evidence: readiness probe, dependency health, and job execution logs.

## 16. Common Pitfalls and Resolutions

| Symptom | Cause | Resolution |
|---|---|---|
| Jobs run in a burst after restore | Timer/fixed-rate continues unintended catch-up | Compute missed-run policy from schedule and durable progress |
| Job does not run again | Executor was shut down before checkpoint and not recreated | Create a new scheduler after restore |
| Two replicas run the same job | Relying on heap flags or local locks | Durable claim, unique occurrence key, and fencing |
| Cache returns stale data | Relying solely on cleanup timer | Check expiresAt on every read |
| Token rejected after restore | Token expired/revoked during pause | Refresh or verify credential before use |
| Multiple replicas refresh same token | Shared refresh token gets rotated | Distributed coordinator/single-flight or per-instance credentials |
| Old replica still writes after lease expiry | Trusting snapshotted leader flag or lock handle | Acquire new lease and check fencing at storage |
| Retry storm | Multiple replicas retry immediately after restore | Backoff, jitter, concurrency limit, and idempotency |
| Job runs before DB is ready | Scheduler starts before dependency recovery | Gate scheduler on readiness/dependency state |
| Wrong expiration after clock adjustment | Mixing nanoTime and wall-clock deadlines | Store Instant, use Clock and monotonic clock for duration |
| Schedule off by one hour around DST | Using 24-hour delay for calendar schedule | Calculate occurrence using ZoneId and DST policy |
| Checkpoint hangs during scheduler drain | Job has no deadline or is not interruptible | Deadlines, cooperative cancellation, and durable progress |

## 17. Implementation Workflow

1. List all schedulers, jobs, caches, tokens, sessions, leases, and retry states.
2. For each state, identify the authoritative source and expiration.
3. Choose fixed-rate, fixed-delay, or calendar schedule.
4. Choose a missed-run policy for each job.
5. Persist critical occurrences/progress in a database or durable queue.
6. Use idempotency keys and unique constraints for side effects.
7. Before checkpoint, quiesce schedulers, drain tasks, and cancel future timers.
8. Create the checkpoint after resource callbacks complete.
9. After restore, read the current Clock and recalculate deadlines.
10. Refresh credentials, caches, sessions, and leases according to policy.
11. Initialize the new scheduler after mandatory dependencies are ready.
12. Claim occurrences atomically and process according to the missed-run policy.
13. Open readiness once the application can serve safely.
14. Monitor missed-run, backlog, expiry, retry, and restore-to-ready metrics.
15. Test various pause durations, multiple replicas, and clock/DST scenarios.

## 18. Practice Checklist

### Scheduler

- [ ] List the schedule and semantics of each job.
- [ ] Choose Skip, Coalesce, Catch-up, Durable replay, or Expire.
- [ ] Persist critical job progress outside the heap.
- [ ] Stop accepting new tasks before checkpoint.
- [ ] Drain running tasks within deadline.
- [ ] Cancel future timers that will be recalculated after restore.
- [ ] Create a new scheduler after restore.
- [ ] Gate jobs on dependency readiness.
- [ ] Use claim/lease/idempotency for multi-replica.

### Expired Data

- [ ] Store absolute expiresAt instead of only remaining delay.
- [ ] Check TTL at point of read/use.
- [ ] Use background cleanup as an optimization, not the sole safeguard.
- [ ] Invalidate or refresh cache after restore.
- [ ] Check access tokens and refresh tokens.
- [ ] Verify current sessions and certificates.
- [ ] Reacquire leases and locks.
- [ ] Recalculate retry deadlines and backoff.

### Time and Testing

- [ ] Inject Clock into time-dependent logic.
- [ ] Use nanoTime only to measure in-process durations.
- [ ] Test short and long pauses.
- [ ] Test across TTL, token expiry, and lease expiry.
- [ ] Test missed-runs and retry windows.
- [ ] Test DST and clock skew if using calendar schedules.
- [ ] Restore multiple replicas from the same image.
- [ ] Verify unique occurrences and business side effects.
- [ ] Collect logs/metrics by job, replica, and incarnation.

## 19. Key Takeaways

- External time continues to pass while the JVM is paused; a heap snapshot does not refresh time-limited data.
- Store absolute deadlines using Instant; recalculate delays after restore.
- Use System.nanoTime() for in-process durations, not as a durable timestamp.
- Choose a dedicated missed-run policy for each job: Skip, Coalesce, Catch-up, Durable replay, or Expire.
- Critical jobs require durable occurrences/progress, unique keys, and idempotency.
- Before checkpoint, stop the scheduler, cancel future timers, and drain running tasks.
- After restore, create a new scheduler and compute schedules from rules and current time.
- Check TTL at the point of use; background cleanup only helps free resources.
- Refresh or verify tokens, sessions, certificates, caches, and leases before use.
- Do not trust leader flags or lock handles remaining in the heap; use a coordinator and fencing tokens.
- Use Clock injection to test expiry, deadlines, missed-runs, and DST.
- When multiple replicas restore simultaneously, use distributed claims, idempotency, and backoff with jitter.
- Only open readiness when schedulers and dependencies can operate according to policy.

Properly handling scheduled tasks and expired data prevents the application from drifting off schedule, running duplicates, or using stale state after a CRaC restore. By storing authoritative timestamps, defining missed-run policies, managing schedulers through the Resource lifecycle, and verifying TTL/credentials/leases at the point of use, the process can resume safely whether paused for a few minutes or many hours.
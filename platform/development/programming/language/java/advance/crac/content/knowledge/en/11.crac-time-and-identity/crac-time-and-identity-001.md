# Pause duration and time data stored in the image

When a Java process is checkpointed with CRaC, the process's memory state is saved so that it can be restored later. Time values that the application placed in objects or fields are also part of that state. However, **time in the outside world is not frozen along with the heap**. While the process is paused, the real clock continues running, tokens can expire, deadlines can pass, and schedules can become overdue.

This creates an important distinction between two things:

- **Time data stored in the checkpoint image:** timestamps, deadlines, TTLs, `Instant`, `Date`, `LocalDateTime`, counters, or timer state that the application wrote into memory.
- **Time sources read while the process is running:** wall clock via `System.currentTimeMillis()` or `Instant.now()`, and the elapsed-time measurement source via `System.nanoTime()`.

Upon restore, the saved object values are recovered as memory state. New clock reads reflect the environment's time source at restore time. Therefore, a deadline computed before checkpoint may already have expired, while a timer or counter stored in the heap may not accurately reflect how long the process was inactive.

## 1. What is stored in the checkpoint image?

View the checkpoint image as a snapshot of the process state at a point in time. If the application holds the following values in the heap, they can be restored along with the process:

```java
Instant createdAt = Instant.now();
Date legacyCreatedAt = new Date();
LocalDateTime localStart = LocalDateTime.now();
long deadlineEpochMillis = System.currentTimeMillis() + 30_000;
long startedNanos = System.nanoTime();
Duration retryDelay = Duration.ofSeconds(10);
```

The values above are ordinary data in memory. After restore:

- `createdAt` still represents the point in time created before checkpoint.
- `legacyCreatedAt` still holds the old epoch milliseconds.
- `localStart` still holds the recorded local date and time, though by itself it contains no time zone.
- `deadlineEpochMillis` is still the deadline computed before checkpoint; it does not automatically add the pause duration.
- `startedNanos` is still the saved integer, but one should not assume it can be used to measure time including the pause interval.
- `retryDelay` still represents a 10-second duration; it does not automatically become the next execution time.

Checkpointing does not turn timestamps inside objects into new timestamps. If a field contains an `Instant` at 10:00 and the process is restored at 10:20, that field still represents 10:00. The application must compare it against the current time itself and decide what to do.

| Data in heap | Behavior to understand after restore |
|---|---|
| `Instant`, `Date`, epoch milliseconds | Retains the recorded point in time; does not automatically update to now |
| `LocalDateTime` | Retains the old date/time fields; contains no time zone information |
| `Duration` | Retains the length of the interval; does not indicate how much of that interval has elapsed |
| Deadline computed from wall clock | Still retains the old deadline; must be compared with current time |
| Value obtained from `System.nanoTime()` | A reading from a monotonic source; do not use as a calendar timestamp or durable deadline across checkpoint |
| Scheduler/timer state | Can be restored with the process; requires evaluating deadlines and catch-up policy |

## 2. Distinguishing wall clock and monotonic clock

Java provides multiple time APIs because different problems require different kinds of clocks.

### Wall clock: calendar point in time

`System.currentTimeMillis()` returns the number of milliseconds since the Unix epoch. `Instant.now()` also reads the current time from the system clock, represented in UTC. They are suitable for recording event timestamps, storing absolute deadlines, or comparing against expiration times issued by external systems.

```java
Instant checkpointRequestedAt = Instant.now();
long epochMillis = System.currentTimeMillis();
```

The wall clock can be adjusted by NTP, administrators, or system configuration. Therefore, it is not a perfect clock for measuring durations: the clock can jump forward or backward. When an authoritative timestamp is needed—such as token expiration, lease expiration, or transaction deadlines—rely on a time source managed by an authoritative system, such as a database or lease-issuing service.

### Monotonic clock: measuring elapsed time

`System.nanoTime()` is designed to measure elapsed time. The returned value has an arbitrary origin, is not an epoch timestamp, and cannot be converted into an actual date and time. The proper usage is taking the difference between two reads within the same execution span:

```java
long started = System.nanoTime();
performOperation();
long elapsedNanos = System.nanoTime() - started;

System.out.println("Elapsed nanos: " + elapsedNanos);
```

Do not store `started` in a database, use it as an expiration time shared across multiple processes, or compare it with `System.currentTimeMillis()`. In particular, do not assume a `nanoTime` value saved in a checkpoint can be used to accurately compute time including the period when the process was paused. How the OS monotonic source handles that interval depends on the platform and checkpoint/restore mechanism.

| Need | Time source to use |
|---|---|
| Record when an event occurred | `Instant.now()` or an authoritative clock |
| Store token/lease expiration time | Absolute timestamp managed by the issuer/database |
| Measure execution time of running code | Difference between two `System.nanoTime()` calls |
| Compute pause duration from checkpoint to restore | Wall clock timestamp recorded before checkpoint and read again after restore; consider clock skew |
| Schedule an event by local time | Clearly defined business time/time zone, then converted to an instant when needed |

## 3. Measuring how long the process was paused

If you need to know approximately how long the process was inactive, you can record an `Instant` right before checkpoint and compare it with the current time after restore.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class PauseTimeResource implements Resource {

    private final Clock clock;
    private Instant checkpointBoundary;

    public PauseTimeResource(Clock clock) {
        this.clock = clock;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        checkpointBoundary = clock.instant();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        Instant restoredAt = clock.instant();
        Duration approximatePause = Duration.between(
                checkpointBoundary,
                restoredAt);

        if (approximatePause.isNegative()) {
            // Wall clock moved backward; record it and apply the appropriate policy.
            handleClockMovedBackward(checkpointBoundary, restoredAt);
            return;
        }

        recordPauseDuration(approximatePause);
    }

    private void handleClockMovedBackward(Instant before, Instant after) {
        // Record clock anomaly; do not use negative duration as pause time.
    }

    private void recordPauseDuration(Duration duration) {
        // Record metric/log with the appropriate instance label.
    }
}
```

`Clock` is injected for testability. `checkpointBoundary` is a timestamp stored in the resource's state; after restore, `clock.instant()` reads the current time. The difference between the two values gives an estimate of the pause duration.

This calculation has limitations:

- The wall clock may be adjusted while the process is paused.
- If restored on a different host, the two hosts may have clock skew.
- `beforeCheckpoint()` is invoked during the callback sequence, so the timestamp recorded there is an approximate mark; it does not necessarily match the exact instant the snapshot completed.
- If authoritative time is needed for security or lease decisions, query the lease/token-issuing system instead of trusting local clock subtraction.

If accurate timing across a distributed system is needed, store timestamps from a unified time source or have a coordinator record checkpoint/restore times. Do not use a local `nanoTime` variable to measure intervals across two hosts.

## 4. Handling deadlines that elapsed during checkpoint

A deadline is typically computed as follows:

```java
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(5));
```

If a checkpoint is taken right after and restored 8 minutes later, the deadline is still the old timestamp and has already expired. The application needs to re-evaluate instead of restarting the 5-minute counter.

```java
Duration remaining = Duration.between(clock.instant(), expiresAt);

if (remaining.isNegative() || remaining.isZero()) {
    expireOperation();
} else {
    scheduleWithDelay(remaining);
}
```

The snippet above shows the calculation. In real code, `expireOperation()` and `scheduleWithDelay()` must handle concurrency, retries, and whether the business state has changed elsewhere.

### Request or workflow timeouts

If a task has an absolute deadline, store that deadline rather than only storing the remaining seconds at checkpoint time. After restore, recompute the remaining time. If already overdue, cancel or transition to a timeout state according to business rules.

```java
public final class OperationDeadline {

    private final Clock clock;
    private final Instant deadline;

    public OperationDeadline(Clock clock, Duration allowedTime) {
        this.clock = clock;
        this.deadline = clock.instant().plus(allowedTime);
    }

    public Duration remaining() {
        Duration value = Duration.between(clock.instant(), deadline);
        return value.isNegative() ? Duration.ZERO : value;
    }

    public boolean isExpired() {
        return !clock.instant().isBefore(deadline);
    }
}
```

If the deadline is stored in a database or workflow store, read the latest state from the source of truth after restore. A checkpoint image may contain a stale operation state while an external system has already completed or canceled that operation.

### Leases and distributed locks

Leases are usually granted with an absolute expiration time. When a process is paused longer than the lease duration, another instance may have already acquired ownership. Restore does not automatically renew the lease, nor does it prove the process is still the owner.

After restore:

1. Read the lease state from the coordination system.
2. Verify that the lease is still valid and still belongs to the current instance.
3. If expired, register or acquire a new lease according to the protocol.
4. Perform exclusive work only after ownership is confirmed.

Do not use a boolean `isLeader = true` in the heap as proof that leadership is still held. That value may have been saved in the image while the lease in the external system has expired.

## 5. TTLs for caches, tokens, and sessions

TTL is typically represented by an expiration timestamp or creation timestamp plus time-to-live duration. If only `remainingTtlSeconds` is stored in the heap, that duration can become logically frozen while the process is not running.

Unsafe example:

```java
// Only stores remaining seconds at checkpoint time.
long remainingSeconds = 120;
```

If the process restores 10 minutes later, the variable can still hold 120. If the application reuses that raw value, expired data could be treated as still alive for another 2 minutes.

Store the expiration time instead:

```java
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(2));

boolean isExpired(Instant expiration, Clock clock) {
    return !clock.instant().isBefore(expiration);
}
```

For caches:

- Keep the cache immutable if the data does not change during its intended lifetime.
- For caches with TTL, check expiration after restore before returning data.
- For caches depending on external data, check version or invalidation state.
- If a cache holds sensitive data or access permissions, refresh when there is any doubt about freshness.

For tokens and sessions:

- Use the `expires_at` field or expiration information issued by the issuer.
- Refresh or re-authenticate after restore when a token is near expiration or already expired.
- Do not assume a token in the heap is still valid merely because the token object was restored.
- Across multiple restores, avoid sharing a token representing an exclusive session if the issuer does not allow it.

## 6. Timers and schedulers after restore

A scheduler may store tasks, delays, and scheduling state in the heap. However, while the process is paused, no application thread executes callbacks. After restore, timer behavior depends on the specific implementation, clock source, and checkpoint/restore mechanism. Some tasks may become overdue and run immediately; others may continue with their remaining delay; native timers or dedicated management threads may need to be recreated.

Do not rely on implicit behavior of `ScheduledExecutorService` to determine business policy. Explicitly decide what should happen to delayed schedules:

- **Skip:** skip the overdue execution and wait for the next cycle.
- **Coalesce:** if multiple executions were delayed, run only once to bring state up to date.
- **Catch up:** run missed executions to catch up, while bounding the count and rate.
- **Expire:** cancel the work if the deadline has passed.

For example, a job that syncs a cache every minute does not necessarily need to catch up 20 times after a 20-minute process pause. It may only need a single full sync of the latest state. Conversely, a workflow processing individual events may need to resume from a durable offset so no events are missed.

### Pausing and resuming a scheduler using Resource

```java
public final class SchedulerResource implements Resource {

    private final Clock clock;
    private final JobScheduler scheduler;
    private Instant nextRunAt;

    public SchedulerResource(Clock clock, JobScheduler scheduler) {
        this.clock = clock;
        this.scheduler = scheduler;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        scheduler.stopAcceptingNewJobs();
        scheduler.drainInFlightJobs();
        nextRunAt = scheduler.nextRunAt();
        scheduler.pauseAndReleaseTimers();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        Instant now = clock.instant();
        if (nextRunAt != null && !nextRunAt.isAfter(now)) {
            scheduler.handleMissedRun(nextRunAt, now);
        } else if (nextRunAt != null) {
            scheduler.scheduleAt(nextRunAt);
        }
    }
}
```

`JobScheduler` is an illustrative abstraction. `handleMissedRun()` must implement one of the skip/coalesce/catch-up/expire policies. If the scheduler already has CRaC integration, use that integration and avoid registering duplicate callbacks. If the schedule must span multiple instances, store the schedule and execution state in a durable system rather than relying solely on an in-heap scheduler.

### Fixed rate and fixed delay

Fixed-rate schedules target periodic execution times; fixed-delay schedules measure the wait interval after an execution finishes. After a long pause, catching up or bunching multiple runs can cause load spikes. Check the semantics of the specific scheduler and apply an explicit skip/coalesce/catch-up policy. For distributed tasks, use a lease or coordination mechanism so multiple restores do not run the same exclusive job.

## 7. Calendar timestamps and time zones

Not every Java time type represents the same thing:

| Type | Meaning | Notes on restore |
|---|---|---|
| `Instant` | A point in time on the UTC timeline | Suitable for storing absolute timestamps and deadlines |
| `Date` | A legacy epoch-millisecond instant | Retains the old point in time; consider migrating to `Instant` |
| `LocalDateTime` | Date/time without a zone or offset | Insufficient to identify a unique instant |
| `OffsetDateTime` | Date/time with a UTC offset | Identifies an instant, though offset does not fully represent zone rules |
| `ZonedDateTime` | Date/time attached to a `ZoneId` | Useful for zone-based business schedules; zone rules may change with timezone database updates |
| `Duration` | Time span in seconds/nanos | Not a start or end point in time |
| `Period` | Span in calendar years/months/days | Has calendar meaning, not always equivalent to a fixed number of seconds |

For example, if storing a schedule "09:00 daily in Asia/Ho_Chi_Minh", explicitly store `LocalTime` along with `ZoneId` and the schedule rule. If storing "expires at a specific point in time", store `Instant`. Do not store `LocalDateTime` and assume the restore host has the same default time zone.

Daylight Saving Time (DST), timezone database changes, and `user.timezone` configuration can affect how local times are interpreted. For recurring schedules in a business time zone, define how to handle nonexistent or repeated hours during DST transitions. For audit timestamps or deadlines, use UTC instants to avoid ambiguity.

## 8. Multiple restores from the same image

When a checkpoint image is used to start multiple processes, every restored process can start with the same saved timestamps, deadlines, counters, and scheduler state. That can lead to:

- Multiple replicas all believing a lease still belongs to them.
- Multiple schedulers all running an overdue job.
- Multiple tokens/sessions being reused even though issued for a single instance.
- Multiple copies all executing a catch-up task.
- An identical `createdAt` timestamp being mistaken for the creation time of each new replica.

Distinguish the timestamp of the **checkpoint artifact**, the timestamp of the **restore**, and the timestamp of the **current instance**. After restore, each instance may need to record a new `restoredAt`, obtain a new instance ID, and register a new lease. If lineage tracking is needed, you can keep `checkpointCreatedAt` as immutable metadata while creating a new `instanceStartedAt` or `restoredAt`.

Do not use an in-heap time variable to coordinate uniqueness across multiple replicas. Use an authoritative database, coordinator, distributed lock, or lease service.

## 9. Clock skew and clock changes

Time calculations based on the wall clock can be affected by clock skew. For example, the host creating the checkpoint may be 30 seconds ahead of the restore host. When taking the difference of two timestamps, the pause duration can become negative or significantly skewed.

Handling principles:

- Synchronize host clocks using NTP or the platform's time mechanism.
- For leases/tokens, trust expiration times and validation from the issuer/database instead of inferring ownership from the local clock.
- Detect and log cases where time jumps backward or forward abnormally.
- Do not turn a negative duration into a large wait interval due to overflow or faulty unit conversion.
- Use `Clock` injection to test forward clock jumps, backward clock jumps, and late restores.
- For critical tasks, store timestamps and business state in the same source of truth when consistency is required.

`Instant` avoids time zone ambiguity but is still read from the wall clock. It does not eliminate clock skew by itself. Accuracy depends on the time source used.

## 10. Design patterns for timeouts within one run vs. across checkpoints

A timeout within a short processing span can use `System.nanoTime()`:

```java
long timeoutNanos = TimeUnit.SECONDS.toNanos(5);
long started = System.nanoTime();

while (!conditionMet()) {
    if (System.nanoTime() - started >= timeoutNanos) {
        throw new TimeoutException("Operation timed out");
    }
    waitForProgress();
}
```

This is how to measure elapsed time in the current execution span. If an operation can be interrupted by a checkpoint and needs to count pause time as well, store an absolute deadline or durable timeout state:

```java
Instant deadline = clock.instant().plusSeconds(5);

void resumeOperation() {
    if (!clock.instant().isBefore(deadline)) {
        throw new OperationExpiredException();
    }

    Duration remaining = Duration.between(clock.instant(), deadline);
    continueWithTimeout(remaining);
}
```

Some operations need both kinds of time: use `Instant` to determine the deadline across checkpoints, then use `nanoTime` to measure execution duration of individual retries or I/O segments within a single run. Do not use one kind of clock for every purpose.

## 11. Testing time behavior across checkpoint/restore

Do not test only restoring immediately after creating a checkpoint. Create varying pause intervals to confirm that deadlines, TTLs, and schedulers react properly.

Scenarios to test:

1. Restore immediately after checkpoint, when all tokens and caches are still valid.
2. Restore after a deadline has expired.
3. Restore after a token or lease has expired.
4. Restore when cache TTL has elapsed.
5. Restore when a scheduler has multiple missed runs.
6. Restore when the wall clock is adjusted forward or backward in a test environment.
7. Restore on a host with clock skew within assumed bounds.
8. Start multiple restores from the same image and verify jobs/leases are not unintentionally duplicated.
9. Checkpoint while a task is waiting on a timeout and verify the timeout after restore follows policy.

Log milestones `beforeCheckpoint`, `checkpointBoundary`, `afterRestore`, `restoredAt`, `deadline`, `remainingDuration`, and `readiness`. Attach a new instance ID for each restore. Do not log tokens or credentials. Useful metrics include pause duration, number of deadlines expired on restore, number of tasks skipped/caught up, number of leases re-acquired, and time from restore to readiness.

Use `Clock.fixed()` in unit tests to verify deadline logic without real waiting. For integration testing, perform checkpoint/restore in a compatible runtime and operating system to observe actual timers, schedulers, and clock sources.

## 12. Conclusion

A checkpoint image stores the time values the application wrote in memory, but does not stop real time. After restore, `Instant`, `Date`, deadlines, and TTLs in the heap still hold their old values; new wall clock reads reflect the current time. `System.nanoTime()` is suitable for measuring elapsed time within an execution span, but should not be used as a calendar timestamp or durable deadline across checkpoints.

For timeouts, tokens, caches, leases, and schedulers, explicitly decide whether pause duration counts toward the expiration period. Use absolute deadlines and authoritative time sources when pause time must be counted; recompute remaining time after restore; choose a skip, coalesce, catch-up, or expire policy for delayed schedules. When one image spawns multiple restores, generate new timestamps and identifiers for each instance, and re-establish leases and ownership via external systems. This way, the application will not inadvertently use stale time data as if the process had never paused.
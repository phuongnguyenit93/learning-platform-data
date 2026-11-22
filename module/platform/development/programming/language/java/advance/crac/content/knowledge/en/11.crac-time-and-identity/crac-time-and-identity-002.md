# Wall clock, nanoTime, and how to recompute durations

Java applications often need to know two different kinds of time: **the current point in calendar time** and **elapsed duration**. These two concepts look similar, yet the JVM provides clock sources for different purposes:

- The wall clock, typically accessed via Instant.now() or System.currentTimeMillis(), gives the point in time relative to the epoch. It is suitable for timestamps, business deadlines, and scheduled appointments.
- The monotonic clock, accessed via System.nanoTime(), is suitable for measuring durations and timeouts within a running process. Its value is not a timestamp and cannot be converted into a date and time.

This distinction matters with CRaC (Coordinated Restore at Checkpoint). When a process is checkpointed, the application pauses while outside time continues to pass. A deadline, token, cache TTL, or execution schedule may have expired by the time the process restores. Keeping a counter or timer created before checkpoint without recomputing it can cause the application to process work too late, run tasks early, or treat an expired credential as still valid.

This lesson explains how to choose a clock, measure elapsed time with nanoTime, and recompute durations after restore according to the application's time policy.

## 1. Two time concepts to distinguish

### 1.1. Wall-clock time

Wall-clock time represents a point on the civil timeline. In Java, the appropriate type to represent a point in time is Instant.

Example:

~~~java
import java.time.Instant;

Instant now = Instant.now();
System.out.println(now);
~~~

Instant represents a point in time in UTC on the timeline, commonly used for:

- Record creation time.
- Request arrival time.
- Token expiration time.
- Business deadlines.
- Checkpoint and restore timestamps.
- Timestamps to store in a database or event log.

You can obtain epoch milliseconds using:

~~~java
long epochMillis = System.currentTimeMillis();
~~~

This value counts milliseconds from the Unix epoch (1970-01-01T00:00:00Z). It has meaning as a timestamp, though actual resolution and accuracy depend on the operating system and clock source.

The wall clock can be adjusted. For example, NTP resynchronizes the clock, an administrator changes the system time, a VM's clock is adjusted, or the clock jumps due to misconfiguration. Thus, two calls to currentTimeMillis() may not produce a difference that accurately reflects actual elapsed time; the later value may even be smaller than the earlier value.

### 1.2. Monotonic time

System.nanoTime() provides a high-resolution time source for measuring elapsed time:

~~~java
long started = System.nanoTime();

// Perform the work to be measured.

long elapsedNanos = System.nanoTime() - started;
~~~

The nanoTime value has an arbitrary origin. Do not interpret it as nanoseconds since 1970 or convert it into a date and time. Only the difference between two reads within the same clock domain is meaningful.

The monotonic clock is designed to measure durations without being affected by wall clock adjustments such as NTP synchronization or system time changes. Actual precision is not the same as the returned unit resolution: the API returns nanosecond units, whereas hardware/OS resolution may be lower.

### 1.3. Quick comparison

| Criterion | Wall clock: Instant/currentTimeMillis | Monotonic: nanoTime |
|---|---|---|
| Meaning | Point on the timeline | Monotonic time counter |
| Origin | Unix epoch for Instant/currentTimeMillis | Arbitrary origin |
| Used for | Timestamps, expiration dates, business deadlines | Elapsed time, in-process timeouts |
| Can jump backward/forward from clock changes | Yes | Unaffected by wall clock adjustments |
| Convertible to date/time | Yes, with Instant | No |
| Save to compare across process restarts | Can save Instant | Should not save nanoTime |
| Fit for checkpoint/restore | Used to compute timestamps and remaining validity | Used for measuring duration within a controlled run span |

There is no single clock source suitable for every situation. Determine whether the application's question is "what time is it now?" or "how much time has elapsed?".

## 2. Using nanoTime properly

### 2.1. Measuring duration by subtraction

Common approach:

~~~java
long start = System.nanoTime();

doWork();

long elapsed = System.nanoTime() - start;

System.out.println(
        "Elapsed: " + elapsed + " ns");
~~~

Convert units using TimeUnit:

~~~java
import java.util.concurrent.TimeUnit;

long elapsedNanos = System.nanoTime() - start;
long elapsedMillis =
        TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Or use Duration to represent the result:

~~~java
import java.time.Duration;

long start = System.nanoTime();

doWork();

Duration elapsed =
        Duration.ofNanos(System.nanoTime() - start);

System.out.println(elapsed.toMillis() + " ms");
~~~

Duration here is only a wrapper for the measured time interval. It does not turn nanoTime into a timestamp.

### 2.2. Checking timeouts using difference

Suppose an operation has a 2-second timeout:

~~~java
long timeoutNanos =
        TimeUnit.SECONDS.toNanos(2);

long started = System.nanoTime();

while (!operationCompleted()) {
    long elapsed = System.nanoTime() - started;

    if (elapsed >= timeoutNanos) {
        throw new IllegalStateException("Operation timed out");
    }

    doSmallUnitOfWork();
}
~~~

Use subtraction between two nanoTime values instead of adding the timeout to the start mark and comparing:

~~~java
// Do not check by adding to the baseline timestamp:
if (System.nanoTime() >= started + timeoutNanos) {
    // timeout
}
~~~

Addition can overflow. Comparing the difference is recommended by Java for intervals shorter than roughly 2^63 nanoseconds, approximately 292 years.

### 2.3. Do not compare nanoTime against a fixed constant

Do not write logic like:

~~~java
if (System.nanoTime() > 1_000_000_000L) {
    // ...
}
~~~

The nanoTime value has no fixed origin and can be negative. Only compare the difference between two related reads.

Do not store nanoTime in a database as a "start timestamp", do not send it over an API, and do not use it as a timestamp in logs. If you need to log a timestamp, use Instant; if you need to log elapsed time, record the duration number with its unit.

## 3. What happens to time during a CRaC checkpoint?

Checkpointing saves the process state and stops the process from executing for a period of time. Meanwhile:

- The JVM does not handle requests or run normal Java code.
- The host and external services may continue running.
- Databases still process sessions and timeouts.
- Tokens, leases, certificates, or cache entries may expire.
- A business deadline may still fall due.
- In-process schedulers cannot execute tasks while the process is stopped.

Therefore, duration from the application's perspective can be defined in two ways:

1. **Real elapsed time**, including the interval during which the process was checkpointed.
2. **Application active/CPU time**, excluding the interval during which the process was stopped.

These two definitions serve different purposes.

### 3.1. Monotonic clocks on Linux and the checkpoint interval

On Linux, CLOCK_MONOTONIC is typically the source the JVM uses to implement System.nanoTime(). This clock advances steadily while the system is running and is not altered by wall clock changes. It does not count time when the system is suspended. CLOCK_BOOTTIME has different semantics: it includes system suspend time.

Checkpointing a process with CRIU is not the same as suspending the entire machine. When the host continues running, the host's monotonic clock typically continues advancing while the process is frozen. However, clock source details, how timers are restored, and exact behavior can vary by OS, JDK build, CRIU, and deployment platform.

Consequently, do not build business logic assuming that a nanoTime value saved before checkpoint is guaranteed to have identical semantics across all environments after restore. Test the behavior of your exact runtime combination if you need to measure intervals spanning checkpoint time.

### 3.2. Deciding whether pause time counts toward duration

| Need | Count checkpoint time? | Representation |
|---|---|---|
| Measure handling time of a single request | Usually no; requests should be drained before checkpoint | Measure nanoTime while the request actually runs |
| Measure total duration of a business workflow | Usually yes | Store startedAt/deadline using Instant |
| Timeout for an in-flight operation | Depends on policy; best not to checkpoint mid-operation | Drain/cancel before checkpoint or store an absolute deadline |
| Cache TTL | Yes | Store expiresAt using Instant or use TTL from the cache server |
| Token/credential validity | Yes | Use expiresAt from the issuer or authentication authority |
| CPU benchmark/latency measurement | Should not count process stopped time as runtime | Stop measurement before checkpoint, start a new measurement after restore |

Before writing code, clearly decide whether the checkpoint interval counts as elapsed time in business logic.

## 4. Store deadlines using Instant, not nanoTime

If a deadline needs to survive across a checkpoint, store an absolute point in time:

~~~java
import java.time.Instant;

Instant expiresAt = Instant.now().plusSeconds(300);
~~~

When you need to know the remaining time:

~~~java
import java.time.Duration;
import java.time.Instant;

Duration remaining =
        Duration.between(Instant.now(), expiresAt);

if (remaining.isNegative() || remaining.isZero()) {
    expire();
} else {
    continueWork(remaining);
}
~~~

This approach allows recomputing the remaining time after restore. If the checkpoint lasted 10 minutes while the deadline had only 5 minutes left, the remaining time after restore will be negative and the application can handle the expired state.

### 4.1. Creating a testable deadline type

Do not scatter Instant.now() calls throughout business logic. Inject Clock so time can be tested:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class Deadline {

    private final Instant expiresAt;

    public Deadline(Instant expiresAt) {
        this.expiresAt = expiresAt;
    }

    public static Deadline after(
            Clock clock,
            Duration duration) {
        return new Deadline(clock.instant().plus(duration));
    }

    public Instant expiresAt() {
        return expiresAt;
    }

    public Duration remaining(Clock clock) {
        Duration remaining =
                Duration.between(clock.instant(), expiresAt);

        return remaining.isNegative()
                ? Duration.ZERO
                : remaining;
    }

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Usage:

~~~java
Clock clock = Clock.systemUTC();

Deadline deadline =
        Deadline.after(clock, Duration.ofMinutes(5));

Duration remaining = deadline.remaining(clock);
~~~

You can store expiresAt in a database or in data structures preserved by the checkpointed application. Upon restore, use the current Clock to recompute remaining.

### 4.2. Absolute deadlines and wall clock changes

Instant solves storing a point in time across checkpoints/process restarts, but the wall clock can be adjusted. If the host clock jumps forward, a deadline may be treated as expired early; if it jumps backward, the validity period may extend longer than expected.

For deadlines requiring high reliability, use an authoritative time source appropriate to the domain, for example:

- Expiration provided by the token issuer.
- Expiration/lease managed by the database or coordination service.
- Server time of the system owning the data.
- A synchronized time service with a clock-skew handling policy.

Do not manually adjust timestamps received from other systems using the machine's time zone. Instant is already a UTC point in time; time zones apply only when displaying or calculating civil schedules.

## 5. Recomputing remaining time after restore

There are two common approaches, depending on the data to store.

### 5.1. Storing an absolute deadline

This is the simple approach when the business logic already has an expiration timestamp:

~~~java
Instant expiresAt = ...; // Saved with the application state.

@Override
public void afterRestore(Context<? extends Resource> context) {
    Duration remaining =
            Duration.between(Instant.now(), expiresAt);

    if (remaining.isNegative() || remaining.isZero()) {
        handleExpired();
    } else {
        scheduleWith(remaining);
    }
}
~~~

Advantages:

- No need to store a nanoTime counter.
- The checkpoint interval is automatically accounted for in remaining time.
- The deadline can be stored in a database or message.
- Easy to test with a fixed Clock.

Limitation: depends on the wall clock and current time source. If the machine clock is untrustworthy, the deadline must be verified against an authoritative time source.

### 5.2. Storing remaining before checkpoint and subtracting paused time

Sometimes an application wants to preserve a remaining duration, such as the allowed time for a workflow. Before checkpoint, store remaining and the checkpoint start timestamp:

~~~java
Instant checkpointAt = clock.instant();
Duration remainingAtCheckpoint = currentRemaining;
~~~

After restore:

~~~java
Duration paused =
        Duration.between(checkpointAt, clock.instant());

Duration remaining =
        remainingAtCheckpoint.minus(paused);

if (remaining.isNegative()) {
    remaining = Duration.ZERO;
}
~~~

Example:

| Moment | Value |
|---|---:|
| Before checkpoint | 8 minutes remaining |
| Process stopped duration | 3 minutes |
| After restore | 5 minutes remaining |

This approach is useful when business logic stores duration rather than deadline. However, it still uses the wall clock to compute the pause interval. If the wall clock jumps backward or forward during checkpoint, the result can be wrong. When a deadline already exists, storing expiresAt is usually easier to understand.

### 5.3. When you want to exclude checkpoint time

If the goal is to measure the time the application was actually active, excluding checkpoint time, stop the measurement before checkpoint and start a new measurement segment after restore:

~~~java
private long activeSegmentStartedAt;

public void startSegment() {
    activeSegmentStartedAt = System.nanoTime();
}

public Duration finishSegment() {
    long elapsed =
            System.nanoTime() - activeSegmentStartedAt;

    return Duration.ofNanos(elapsed);
}

@Override
public void beforeCheckpoint(Context<? extends Resource> context) {
    accumulatedActiveTime =
            accumulatedActiveTime.plus(finishSegment());
}

@Override
public void afterRestore(Context<? extends Resource> context) {
    startSegment();
}
~~~

The example above illustrates how to split measurement segments. In a real implementation, protect accumulatedActiveTime with a lock or appropriate synchronization mechanism, and do not call finishSegment() if no segment is currently running.

The result is the total active time summed from segments before and after checkpoint; the time the process was stopped is excluded from the measurement.

## 6. Recomputing timeouts and ScheduledExecutorService

ScheduledExecutorService normally takes a relative delay:

~~~java
scheduler.schedule(task, 30, TimeUnit.SECONDS);
~~~

This delay works well within a continuous execution span. During checkpoint, scheduler threads cannot run tasks. After restore, do not assume a task will run at the business-expected time if it depended on remaining time computed before checkpoint.

### 6.1. Using a deadline as the source of truth

Instead of holding only a 30-second delay, hold a deadline:

~~~java
Instant runAt = clock.instant().plusSeconds(30);
~~~

Before checkpoint, stop the scheduler and keep runAt. After restore, recompute:

~~~java
Duration delay =
        Duration.between(clock.instant(), runAt);

if (delay.isNegative()) {
    delay = Duration.ZERO;
}

scheduler.schedule(
        task,
        delay.toMillis(),
        TimeUnit.MILLISECONDS);
~~~

If the checkpoint lasted longer than 30 seconds, the task is scheduled with delay 0. The application still must decide whether an overdue task should run immediately, be skipped, or be coalesced with the next scheduled run.

### 6.2. Resource managing the scheduler

A CRaC Resource skeleton:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public final class DeadlineScheduler implements Resource {

    private final Clock clock;
    private final Runnable task;

    private Instant nextRunAt;
    private ScheduledExecutorService scheduler;
    private ScheduledFuture<?> scheduled;

    public DeadlineScheduler(Clock clock, Runnable task) {
        this.clock = clock;
        this.task = task;

        Core.getGlobalContext().register(this);

        startScheduler();
    }

    public synchronized void setNextRunAt(Instant nextRunAt) {
        this.nextRunAt = nextRunAt;
        reschedule();
    }

    private synchronized void startScheduler() {
        scheduler = Executors.newSingleThreadScheduledExecutor();
        reschedule();
    }

    private synchronized void reschedule() {
        if (scheduler == null || nextRunAt == null) {
            return;
        }

        if (scheduled != null) {
            scheduled.cancel(false);
            scheduled = null;
        }

        Duration delay =
                Duration.between(clock.instant(), nextRunAt);

        long delayMillis =
                Math.max(0L, delay.toMillis());

        scheduled = scheduler.schedule(
                task,
                delayMillis,
                TimeUnit.MILLISECONDS);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        if (scheduler != null) {
            if (scheduled != null) {
                scheduled.cancel(false);
                scheduled = null;
            }
            scheduler.shutdownNow();
            scheduler = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) {
        startScheduler();
    }
}
~~~

This is a skeleton illustrating how to save the run time and recreate the scheduler. A real application needs to add:

- Cancel the old ScheduledFuture when rescheduling so multiple task copies are not created.
- Ensure the task does not run concurrently with the callback closing the scheduler.
- Handle task exceptions and update nextRunAt after completion.
- Decide whether an overdue task runs immediately or is skipped.
- Choose a shutdown/awaitTermination policy rather than always canceling immediately.
- Handle the case where the restore callback runs before the task's dependencies are ready.

For periodic jobs like daily reports, compute the next run according to the calendar schedule and ZoneId rather than adding a fixed number of seconds to the previous run time.

## 7. TTL, tokens, leases, and caches after restore

Many pieces of data have a lifetime. If you only store "60 seconds remaining" using nanoTime or an in-RAM counter, the application may keep expired data after checkpoint.

### 7.1. Cache TTL

A cache entry should have expiresAt:

~~~java
record CacheEntry<T>(T value, Instant expiresAt) {
    boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

When reading the cache after restore, check expiresAt before returning data. Do not rely solely on a scheduled eviction task, since that task could not run while the process was checkpointed.

If the cache is backed by Redis or another cache server with server-side TTL, prefer letting that system manage expiration. When the application restores, the cache server has already tracked expiration against its own clock.

### 7.2. Tokens and credentials

Tokens usually have an expiration claim or expires_at field. After restore, check expiration before using:

~~~java
if (!clock.instant().isBefore(token.expiresAt())) {
    tokenProvider.refresh();
}
~~~

Do not use nanoTime to represent token validity. Expiration issued by an issuer is typically an absolute point in time and must be compared against a wall clock source with clock skew control.

If the refresh token also expired or was revoked during the checkpoint period, the application must handle re-authentication according to security policy. Do not assume a credential is still valid just because the token object still exists in the heap.

### 7.3. Distributed leases and locks

Distributed leases may be granted by a database, coordination service, or lock system. While the application is checkpointed, the lease may expire and be granted to another instance.

After restore:

- Do not continue using the old lease merely because the lease object still exists.
- Check the lease with the lease-owning system.
- Renew or re-acquire according to the protocol.
- Verify the fencing token/version before writing data.
- Do not assume the instance is still the owner after a long pause.

For distributed locks, a fencing token is usually safer than merely comparing timestamps on the client. The data storage system must reject operations from an old owner when a new owner's token is higher.

### 7.4. Rate limiters and token buckets

A token bucket usually needs to store the last refill time. If nanoTime is used and that value is kept across checkpoint, refill logic after restore may behave contrary to the intended meaning.

You can store lastRefillAt as an Instant and compute elapsed time after restore, but you must decide whether the bucket is allowed to accumulate tokens during the checkpoint period. If you do not want an instance to be granted a burst of tokens after pausing, cap the refill amount or sync state with a shared rate limiter.

## 8. Wall clock adjustments and preventing skew errors

The wall clock is a necessary source for timestamps and deadlines across checkpoints, yet it can change.

Example:

~~~text
12:00:00  Save expiresAt = 12:05:00
12:02:00  Checkpoint
12:04:00  Restore
12:04:00  About 1 minute remaining

If the clock is adjusted:
12:04:00 → 11:55:00
The application may compute 10 minutes remaining

Or:
12:04:00 → 12:10:00
The application may treat the deadline as expired
~~~

Appropriate measures:

- Use NTP or the platform's time synchronization mechanism.
- Use UTC Instant to store timestamps; do not store local time without a time zone.
- For security-sensitive expirations, rely on the expiration provided by the issuer or authoritative server.
- For distributed leases and locks, let the lease-owning system decide the state.
- For clock-skew-sensitive logic, set a skew threshold and handle cases where time cannot be trusted.
- Do not use nanoTime as a substitute for the wall clock for deadlines spanning processes or hosts.

Time zones and daylight saving time are presentation/civil calendar concerns, not ways to fix the wall clock. If you need a schedule like "9 AM Vietnam time", use ZonedDateTime and ZoneId:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime localSchedule =
        ZonedDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

When storing a specific point in time, store Instant. When storing a recurring schedule rule in local time, store LocalTime/ZoneId or the corresponding schedule structure so the next execution is computed accurately under DST rules.

## 9. Measuring performance across checkpoints

Latency measurement or benchmarking must clearly separate code execution time from process paused time.

### 9.1. Measuring a processing segment

~~~java
long started = System.nanoTime();

handleRequest();

long elapsed = System.nanoTime() - started;
recordLatency(elapsed);
~~~

This snippet is meaningful only for a single execution within the same run span. If a request is running at checkpoint time, it is best to drain or complete the request before checkpoint rather than letting an incomplete measurement continue after restore.

### 9.2. Measuring startup-to-READY time

If you want to measure from process start until the application is READY, you can use Instant or wall-clock timestamps. If you want to measure how long startup code actually executed while excluding checkpoint pause time, sum the separate nanoTime segments.

The two measurements answer two different questions:

| Metric | Meaning |
|---|---|
| Wall-clock startup duration | From start until READY in real-world time |
| Active startup duration | Total time the application actually ran startup code |
| Restore-to-ready duration | From restore start until readiness succeeds |
| Checkpoint-to-restore duration | External interval between checkpoint and restore |

When reporting CRaC performance, specify which metric is being measured. Simply reporting "startup 200 ms" without stating whether checkpoint time is included makes results hard to compare.

## 10. Testing time without real waiting

Java Clock allows decoupling time logic from the system clock. You can use Clock.fixed to test deadlines:

~~~java
import java.time.Duration;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T10:00:00Z"),
        ZoneOffset.UTC);

Deadline deadline =
        Deadline.after(fixedClock, Duration.ofMinutes(5));

System.out.println(deadline.remaining(fixedClock)); // PT5M
~~~

To simulate restoring 7 minutes later, create a new clock at the corresponding instant:

~~~java
Clock restoredClock = Clock.fixed(
        Instant.parse("2026-01-01T10:07:00Z"),
        ZoneOffset.UTC);

System.out.println(deadline.remaining(restoredClock)); // PT0S
System.out.println(deadline.isExpired(restoredClock));  // true
~~~

This approach helps verify:

- Whether a deadline is still valid or expired.
- Cache TTL after the checkpoint interval.
- Token expiration while the process was stopped.
- Whether the scheduler should run immediately or wait.
- Wall clock jumping forward or backward.
- Handling policy when remaining duration is negative.

For nanoTime logic, create a small abstraction for a monotonic ticker so tests can advance time under control. Do not try to use Clock.fixed to mock nanoTime because the two APIs represent two different kinds of clocks.

## 11. Common errors when handling time in CRaC

| Error | Consequence | Fix |
|---|---|---|
| Storing nanoTime in checkpoint as an absolute deadline | Value has no meaning as a timestamp | Store Instant/deadline or remaining duration with a clear policy |
| Using currentTimeMillis to benchmark short latency | Results affected by resolution and clock adjustments | Use nanoTime |
| Keeping old ScheduledFuture and trusting the task will run on time | Task may be late or scheduler state invalid after restore | Store the deadline and reschedule after restore |
| Not checking tokens after restore | Requests may use expired credentials | Check expiresAt and refresh |
| Treating an old lease as still valid | Two instances may both think they own the resource | Reacquire/renew and verify fencing token |
| Computing duration from wall clock without considering clock skew | Negative or overly large durations | Use monotonic clock for in-process elapsed; authoritative clock for deadlines |
| Adding timeout to nanoTime before comparing | Risk of overflow | Compare the difference |
| Using LocalDateTime to store a global point in time | Cannot determine an instant without a time zone | Store Instant or OffsetDateTime |
| Letting timers run while callbacks are shutting down | Race condition or tasks accessing closed resources | Stop accepting tasks, cancel, and synchronize lifecycle |

## 12. Time design workflow for CRaC applications

When a component uses timeouts, deadlines, or timers, clarify the following steps:

1. Determine whether this is an absolute point in time or an elapsed duration.
2. If it is a timestamp/deadline, represent it with Instant and save it with the state to be checkpointed.
3. If it is elapsed time within an execution span, measure it with System.nanoTime() and use subtraction.
4. Decide whether process checkpoint time counts in business logic.
5. Before checkpoint, stop or drain timers/tasks using resources about to close.
6. Record the deadline or remaining duration according to the chosen policy.
7. After restore, recompute remaining from the appropriate time source.
8. Check tokens, leases, caches, and credentials that may have expired during the pause.
9. Recreate necessary schedulers or timers.
10. Open traffic only after dependencies and time states have been verified.

For business deadlines, prefer storing an absolute expiration timestamp. For local timeouts within a single processing span, use nanoTime. For measuring performance across multiple execution phases, sum monotonic segments and exclude the checkpoint interval if the goal is measuring active time. For leases or expirations managed by external systems, re-verify state with that system after restore.

By clearly separating the wall clock and monotonic clock, the application avoids using a time value for the wrong purpose. CRaC can restore memory state, but does not make business deadlines, database sessions, tokens, or external leases automatically remain valid. Time-dependent values must be recomputed or re-verified before the application resumes work.

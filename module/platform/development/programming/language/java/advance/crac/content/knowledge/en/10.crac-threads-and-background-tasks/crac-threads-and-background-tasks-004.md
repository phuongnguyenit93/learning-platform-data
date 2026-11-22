# `ScheduledExecutorService`: fixedRate, fixedDelay, and Missed Schedules

`ScheduledExecutorService` allows Java to run a task after a delay or run repeatedly on a cycle. The two commonly used periodic modes are `scheduleAtFixedRate` and `scheduleWithFixedDelay`. They compute the next execution time differently, so choosing the right one depends on the semantics of the work.

When an application uses CRaC, schedules are also affected by the duration the process spends in the checkpointed state. A restore may happen seconds, minutes, or longer later. During that interval, scheduled execution times may have passed. The application must explicitly decide whether to skip missed runs, coalesce them into one run, or catch up one by one. Do not rely on assuming every `ScheduledExecutorService` implementation and every CRaC runtime handles the checkpoint interval identically.

## 1. `scheduleAtFixedRate`: fixing the interval between expected start times

`scheduleAtFixedRate(task, initialDelay, period, unit)` schedules the first run after `initialDelay`. Subsequent runs are scheduled at a fixed cadence measured from the initial expected start time:

```text
start 1       start 2       start 3       start 4
   |-------------|-------------|-------------|
        period        period        period
```

For example, with `initialDelay = 0` and `period = 10 seconds`, the expected start times are 0s, 10s, 20s, 30s, ... If one run takes 13 seconds, the next one is already overdue when the current one finishes. The executor may start the next run immediately afterward to get closer to the scheduled cadence.

Executions of **the same periodic task do not run concurrently**. If one run takes longer than the period, subsequent runs may start late, but they do not overlap with the previous run of that same task. This does not stop the task from spawning asynchronous work and returning early; if the task submits a `CompletableFuture` and finishes immediately, the next scheduled run can start while the previous future is still running.

Example:

```java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        this::refreshMetrics,
        0,
        10,
        TimeUnit.SECONDS
);
```

Choose fixed rate when business logic needs a periodic cadence, such as:

- Sampling metrics every 10 seconds.
- Checking heartbeats at a fixed period.
- Synchronizing state at periodic milestones.
- Running a housekeeping task where the spacing between expected timestamps matters.

Fixed rate is not a time-zone-aware cron schedule. It is a repeating schedule over the executor's relative intervals. If you need to run at 09:00 every day in local time, compute schedules from `Instant`, `ZoneId`, and date/time calendar policies; do not treat `scheduleAtFixedRate(..., 24, HOURS)` as equivalent to 09:00 every day across DST transitions.

## 2. `scheduleWithFixedDelay`: waiting an interval after the previous run finishes

`scheduleWithFixedDelay(task, initialDelay, delay, unit)` computes the next execution from **the moment the previous execution finishes**:

```text
start 1       finish 1       start 2       finish 2
   |--------------|-------------|--------------|
       duration       delay         duration
```

If a task takes 4 seconds and fixed delay is 10 seconds, the next run starts about 14 seconds after the previous run started. If the run takes 20 seconds, the next run starts about 30 seconds later. Processing time does not cause runs to overlap.

Example:

```java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> future = scheduler.scheduleWithFixedDelay(
        this::pollRemoteQueue,
        0,
        10,
        TimeUnit.SECONDS
);
```

Fixed delay fits work where you want a rest interval after completion:

- Polling an external service, avoiding back-to-back calls when the previous poll was slow.
- Cleaning up data with variable processing times.
- Checking a dependent system without needing an absolute cadence.
- Running a maintenance task where the next run should only start after the previous one finishes plus a rest duration.

## 3. Comparing fixed rate and fixed delay

| Criterion | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
|---|---|---|
| Reference point for next run | Expected timestamps along the initial cadence | Completion time of the previous run |
| Effect when a task runs long | Next run may start late and run to catch up on missed cadence | Next run always waits the full delay after previous completion |
| Actual spacing between two starts | May be shorter than normal while executor catches up | Equals previous execution duration plus delay |
| Overlap of the same periodic task | No | No |
| Use when | Periodic cadence matters | Rest interval after processing matters |
| Example | Periodic sampling | Polling with a rest interval after each poll |

Suppose period/delay is 10 seconds and each run takes 13 seconds:

### Fixed rate

The expected points are 0s, 10s, 20s, 30s. Since the first run finishes at 13s, the second starts late at 13s; the following run can start immediately when the second finishes at 26s to catch up on the delayed cadence.

```text
Run 1: 0s -------- 13s
Run 2:              13s -------- 26s
Run 3:                           26s -------- 39s
```

### Fixed delay

After each completion, the executor waits another 10 seconds. Thus, the second run starts at 23s and the third at 46s.

```text
Run 1: 0s -------- 13s
Wait:                13s --- 23s
Run 2:                         23s -------- 36s
Wait:                                      36s --- 46s
Run 3:                                               46s ...
```

These timelines illustrate the ordinary scheduling contract. When a process is checkpointed, time elapsed while the process is not running introduces a distinct situation; see the missed schedules section below.

## 4. What happens if a periodic task throws an exception?

Under the `ScheduledExecutorService` contract, if any execution of a periodic task throws an exception, subsequent executions of that periodic task are suppressed (do not continue running). The `ScheduledFuture` typically enters an abnormally completed state.

This is easy to miss if you only log where the schedule is created. For example:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        () -> updateRemoteState(),
        0,
        30,
        TimeUnit.SECONDS
);
```

If `updateRemoteState()` throws a `RuntimeException` on the first run, you must not assume the executor will automatically retry after 30 seconds. If you want periodic execution to continue after transient errors, catch errors inside the task body and explicitly define a retry policy:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        () -> {
            try {
                updateRemoteState();
            } catch (Exception failure) {
                logger.warn("Periodic state update failed", failure);
                recordFailure(failure);
            }
        },
        0,
        30,
        TimeUnit.SECONDS
);
```

Catching exceptions prevents the task from terminating abnormally, yet it does not mean every error should be swallowed. Log, record metrics, perform bounded retries, or transition system state to unhealthy if errors persist. For serious errors making subsequent runs unsafe, stop the schedule and require explicit recovery.

You can keep the `ScheduledFuture` to observe status. If `isDone()` returns `true` unexpectedly, call `get()` to retrieve the cause; a normal periodic future does not return a result after each run and keeps waiting until canceled or abnormally terminated. When `get()` throws `ExecutionException`, inspect `getCause()` to identify the error that stopped the schedule.

## 5. Missed schedules during checkpoint

Suppose a task is scheduled every minute. The application runs at 10:00, creates a checkpoint at 10:02, and restores at 10:07. During that 5-minute interval, the 10:03, 10:04, 10:05, 10:06, and 10:07 slots may have passed.

What must be decided is: after restore, should the application re-execute every missed slot? The answer depends on business semantics:

- If the task merely refreshes a cache, one fresh refresh is usually enough.
- If the task aggregates data per minute, each missing bucket may need processing.
- If the task sends reports strictly per period, skipping missed periods may be unacceptable.
- If the task polls an endpoint to check current status, running once right after restore usually makes more sense than bursting multiple runs.

**CRaC does not define a universal business policy for missed schedules.** `ScheduledExecutorService` specifies fixed-rate/fixed-delay while the executor is running, yet behavior of delay queues, clocks, and overdue tasks across checkpoint/restore also depends on the JDK implementation, CRaC runtime, and platform. Test on the exact deployment runtime and define the missed-run policy at the application layer.

Do not treat the fact that an `afterRestore` callback is called as proof that all missed runs were automatically replayed, or that they were definitely skipped.

## 6. Three policies for handling missed schedules

### Skip

Only run the next occurrence whose timestamp lies in the future. Slots during the checkpoint are skipped.

Example: every-minute schedule, restored at 10:07:20, next run is at 10:08. This policy suits metric sampling, cache refreshes, or tasks that only need the latest state.

### Coalesce

If one or more slots were missed, run once right after restore to update current state, then resume the normal schedule.

Example: even though five refreshes were missed, the application runs one refresh at 10:07:20 and then continues at 10:08. This policy suits snapshot synchronization or calculations where the latest run subsumes older data.

### Catch-up

Execute each missed period in order, with rate limiting and a count limit per batch. This policy suits cases where each period represents a distinct piece of business data requiring separate processing.

Example: the system must aggregate each one-minute bucket. After restoring at 10:07:20, it processes buckets 10:03 through 10:07 and then resumes the current schedule. Limit batch sizes, set deadlines, and monitor backlogs to avoid a massive catch-up burst overloading databases or dependent services.

| Policy | Action after restore | Suitable cases |
|---|---|---|
| Skip | Drop past slots, schedule future slot | Caches, sampling, health polls |
| Coalesce | Run once representing missed slots | Snapshot refreshes, current state synchronization |
| Catch-up | Process each missed slot, typically in batches | Billing periods, aggregation buckets, periodic event processing |

Do not choose catch-up merely out of desire "not to lose runs." If a task has side effects, replay requires idempotency and durable source data. Conversely, skip is safe only when business logic permits omitting skipped periods.

## 7. Recalculating execution times from durable data

If schedules matter across checkpoints, store the necessary schedule info outside the heap, for example in a database:

- Job name and schedule configuration version.
- Most recent expected timestamp or `nextDueAt`.
- Most recently succeeded slot (`lastCompletedSlot`).
- Time zone if the schedule relies on local time.
- Backlog state or cursor if catch-up applies.
- Idempotency key for each business period.

After restore, reload this data, compare against current time, and apply the missed-run policy. Do not rely solely on a `ScheduledFuture` or a `nextRun` variable on the heap, because a checkpoint may hold stale values.

### Fixed rate by expected timestamp

If fixed rate is 60 seconds, you can maintain an `anchor` timestamp and calculate slots at fixed intervals. The example below computes the first slot after `now`, using seconds for illustration:

```java
import java.time.Duration;
import java.time.Instant;

static Instant nextFixedRateSlot(
        Instant anchor,
        Instant now,
        long periodSeconds) {
    if (periodSeconds <= 0) {
        throw new IllegalArgumentException("periodSeconds must be positive");
    }

    if (now.isBefore(anchor)) {
        return anchor;
    }

    long elapsedSeconds = Duration.between(anchor, now).getSeconds();
    long completedIntervals = elapsedSeconds / periodSeconds;
    long nextInterval = Math.addExact(completedIntervals, 1);
    long offset = Math.multiplyExact(nextInterval, periodSeconds);

    return anchor.plusSeconds(offset);
}
```

This is a calculation for a seconds-based interval schedule, not a time-zone-aware cron schedule. For calendar schedules, calculate using `ZonedDateTime`/`ZoneId` and explicitly define how DST, repeated hours, or nonexistent hours are handled.

Once `nextDueAt` is determined, compute a non-negative delay and create a new schedule:

```java
Instant now = clock.instant();
Instant nextDueAt = scheduleStore.calculateNextDue(now);
long delayNanos = Math.max(
        0L,
        Duration.between(now, nextDueAt).toNanos()
);

future = scheduler.schedule(
        this::runOneSlot,
        delayNanos,
        TimeUnit.NANOSECONDS
);
```

After that execution, the application can compute the next slot itself from the anchor and persisted data, or create a new periodic schedule if semantics match. The specific calculation must avoid overflow when converting large `Duration` values to nanoseconds.

### Fixed delay by completion time

For fixed delay, the reference point is the completion time of the previous run. If the application wants to preserve exact semantics across checkpoints, persist `lastCompletedAt` durably. After restore, the next timestamp is:

```text
nextDueAt = lastCompletedAt + configuredDelay
```

If `nextDueAt` has already passed, the application still must choose skip, coalesce, or catch-up per business logic. If the policy is "wait a full delay starting from restore," set `nextDueAt = restoreTime + delay` and document clearly that this is a new resume policy, not restoring the original pre-checkpoint cadence.

## 8. Integrating with CRaC: stopping old schedules and creating new ones

One easily controllable approach is managing the scheduler as a resource with an explicit lifecycle:

### Before checkpoint

1. Close the gate creating new work if jobs can be triggered from multiple sources.
2. Cancel periodic schedules to prevent subsequent executions from being spawned.
3. Wait for the current run and any asynchronous work it created to finish.
4. Persist progress or `lastCompletedAt` to durable storage.
5. Stop the dedicated scheduler executor if it is no longer used.

### After restore

1. Create a new `ScheduledExecutorService`.
2. Read schedule configuration and state from durable sources.
3. Calculate missed periods and apply skip/coalesce/catch-up.
4. Schedule the first execution according to the chosen policy.
5. Allow jobs to accept new triggers only after dependencies and recovery state are ready.

CRaC wrapper example:

```java
import java.time.Duration;

import org.crac.Context;
import org.crac.Resource;

final class ScheduledJobsResource implements Resource {
    private final PeriodicJobLifecycle jobs;
    private final Duration drainTimeout;

    ScheduledJobsResource(
            PeriodicJobLifecycle jobs,
            Duration drainTimeout) {
        this.jobs = jobs;
        this.drainTimeout = drainTimeout;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        jobs.stopSchedulingAndDrain(drainTimeout);
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        jobs.recreateExecutorAndApplyMissedRunPolicy();
    }
}
```

`PeriodicJobLifecycle` is an application-implemented abstraction. It should hold the `ScheduledFuture`, executor, running task state, and durable schedule information. `stopSchedulingAndDrain` needs to cancel future triggers, wait for the current task to finish within a deadline, and then shut down the dedicated executor. `recreateExecutorAndApplyMissedRunPolicy` creates a new executor and recalculates schedules from the authoritative data source.

If `beforeCheckpoint` times out, the callback must report an error so the checkpoint is rejected. The orchestration layer needs a way to recover the scheduler if the process keeps running after a failed checkpoint. Do not assume a shut-down executor can be restarted; typically you need to create a new executor and reschedule tasks. If the checkpoint engine fails after the callback has completed, the controller managing the attempt must handle returning the instance to service or replacing it.

## 9. Canceling schedules and waiting for running tasks

`ScheduledFuture.cancel(false)` prevents future executions of the task without requesting interruption of the currently running one. This is usually the right choice when you want the current task to finish on its own before checkpointing.

`cancel(true)` may request interrupting the executing thread. Do not use it as the default way to drain: the task may be committing a transaction, writing a file, or updating state. Use interrupts only if the task is designed cooperatively and can stop safely.

With a dedicated scheduler executor, a simple sequence is:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

future.cancel(false);
scheduler.shutdown();

if (!scheduler.awaitTermination(30, TimeUnit.SECONDS)) {
    throw new TimeoutException("Scheduled work did not finish in time");
}
```

`awaitTermination` waits for the executor to finish after shutdown; it does not replace tracking asynchronous work submitted by the task to another executor. If a periodic task merely spawns a future and returns, wait for child futures as well or use a shared work tracker.

On timeout, do not silently continue checkpointing. Record which task is still running, and decide whether the scheduler can be recovered on the current process or the instance must be marked unhealthy. If a task cannot be safely interrupted, do not forcibly close resources the task is still using.

## 10. Periodic schedules in multi-replica environments

When multiple instances restore from the same checkpoint, all of them may initialize the same periodic job. If every replica runs work with side effects, the system may send duplicate emails, aggregate duplicate data, or update the same record concurrently.

`ScheduledExecutorService` only coordinates tasks within a single JVM. It does not provide distributed locks, leader election, or guarantees that only one replica runs a job.

For jobs permitted to run only once system-wide, an external coordination mechanism is needed:

- Distributed lock or time-bounded lease.
- Leader election with fencing tokens so an old instance cannot keep writing after losing authority.
- A job schedule table with a unique key on `jobName + scheduledSlot`.
- Queue/work partitioning so each period or partition has only one owning consumer.
- Idempotency keys so retries or catch-ups do not create duplicate side effects.

Do not keep an `isLeader` flag on the heap and trust it remains valid after restore. Leases can expire during checkpointing; verify or acquire a fresh lease after restore before running write-capable jobs.

## 11. Choosing a policy by task kind

| Task kind | Schedule suggestion | Post-restore policy |
|---|---|---|
| Refresh cache from authoritative source | Fixed delay or fixed rate depending on freshness needs | Coalesce: refresh once after restore |
| Collect metrics at a cadence | Fixed rate | Skip missed samples if continuous data is unnecessary; or explicitly record gap |
| Poll queue | Fixed delay | Run once after restore; broker holds unacked messages |
| Aggregate by time bucket | Fixed-slot schedule | Catch-up in batches, with cursor and idempotency |
| Send daily report | Calendar schedule by `ZoneId` | Decide catch-up vs skip; store idempotency key per day/period |
| Clean up old data | Fixed delay or calendar schedule | Usually coalesce, based on durable cutoff |
| Heartbeat/lease renewal | Per dependent system protocol | Issue/renew fresh lease after restore before marking instance healthy |

These are design suggestions. Final decisions must follow the business commitments, data requirements, and retryability of each task.

## 12. Observability and testing

Monitor the following signals:

| Metric/log | Meaning |
|---|---|
| Expected timestamp and actual start timestamp | Measure scheduler lag |
| Execution duration per run | Detect tasks taking longer than period/delay |
| Missed slot count | Quantify missed schedules after checkpoint |
| Catch-up run count and remaining backlog | Track catch-up |
| Task failure and `ScheduledFuture` status | Detect suppressed periodic execution |
| Checkpoint time and restore time | Compute how long the scheduler was interrupted |
| Instance ID/lease owner | Detect multiple replicas running the same job |

Test scenarios should include:

1. Task running faster than period to observe fixed-rate and fixed-delay.
2. Task running longer than period to confirm no overlap of the same periodic task and understand scheduler lag.
3. Task throwing an exception to confirm subsequent executions are suppressed if the exception escapes.
4. Checkpointing while a task is running to verify the callback awaits drain or rejects checkpoint on timeout.
5. Restoring after a duration longer than multiple cycles and verifying skip/coalesce/catch-up policies.
6. Restoring after a timezone change or across a DST transition if the job uses calendar schedules.
7. Restoring multiple replicas and verifying distributed coordination prevents duplicate side effects.
8. Making the database or dependencies temporarily unreachable to verify retries and readiness.

Run tests on the exact JDK/CRaC runtime and executor implementation that will be used in production. Record actual delay-queue behavior across checkpoints instead of inferring from a single run on a development machine.

## 13. Implementation checklist

- [ ] Chosen fixed rate or fixed delay based on task semantics.
- [ ] Understood that executions of the same periodic task do not overlap, yet submitted async work may still overlap.
- [ ] Tasks handle exceptions explicitly so the entire schedule is not accidentally suppressed.
- [ ] Determined whether the task is permitted to miss one or more cycles.
- [ ] Chosen skip, coalesce, or catch-up policy for checkpoint intervals.
- [ ] Critical schedules and business progress are durably persisted outside the heap.
- [ ] `beforeCheckpoint` cancels new triggers and waits for current work to finish within deadline.
- [ ] `afterRestore` creates a new executor and recalculates schedules from authoritative data sources.
- [ ] Catch-up has batch limits, rate limits, and idempotency.
- [ ] Jobs with side effects are coordinated across replicas via appropriate leases/locks/partitions.
- [ ] Tested missed-schedule behavior on the exact CRaC JDK and deployment platform.

## 14. Conclusion

`scheduleAtFixedRate` keeps cadence by expected start times; `scheduleWithFixedDelay` waits a full interval after the previous run finishes. Fixed rate fits when periodic cadence matters; fixed delay fits when a rest interval after each processing run is needed. Neither permits executions of the same periodic task to overlap, though asynchronous tasks they spawn must be managed separately.

With CRaC, treat checkpoint duration as an interruption during which schedules can be missed. Stop triggers and drain tasks before checkpoint; after restore, read durable schedule state and apply skip, coalesce, or catch-up policies. If a job has side effects or runs across multiple replicas, add idempotency and distributed coordination. That way, execution schedules reflect business requirements rather than relying on timer state remaining on the heap.
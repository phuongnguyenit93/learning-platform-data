# Cron schedules, periodic tasks, and missed-run handling policies

Java applications frequently run scheduled work: syncing data every few minutes, aggregating reports at midnight, purging data daily, or sending notifications at a fixed time. When an application uses CRaC, the process may pause at checkpoint and resume after some interval. During that time, cron marks still pass according to the calendar clock. Without redesigning the scheduler lifecycle, the application may catch up too many tasks at once, skip essential work, or execute a task twice.

A scheduler safe for checkpoint–restore needs to clearly define three things: how to pause and recreate schedules, how to compute the next run time according to the clock and time zone, and the policy for handling runs that fell due while the application was inactive. The policy can be skipping, running once immediately upon restore, catching up one by one, coalescing multiple runs into one, or bounded catch-up.

## 1. Distinguishing cron from interval-based periodic tasks

Not every schedule has the same semantics.

| Schedule type | Example | How the next run is determined |
|---|---|---|
| Fixed rate | Every 10 seconds at a periodic cadence | Computed from start baseline and fixed period |
| Fixed delay | Wait 10 seconds after the previous run finishes | Computed from completion time of the previous run |
| Cron | Daily at 02:30 in `Asia/Ho_Chi_Minh` time zone | Computed from schedule expression and calendar clock |
| One-shot | Run at a specific `Instant` | An absolute point in time |

`ScheduledExecutorService.scheduleAtFixedRate()` is suitable for work with relative periodicity. `scheduleWithFixedDelay()` fits when the pause interval is measured after the previous run finishes. Neither method replaces a cron calendar, because cron often depends on day of week, day of month, time zone, and Daylight Saving Time (DST) transitions.

Example:

```java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

// Target cadence is every 10 seconds measured from the initial baseline.
scheduler.scheduleAtFixedRate(
        this::refreshMetrics, 0, 10, TimeUnit.SECONDS);

// Wait 10 seconds after each refresh completes.
scheduler.scheduleWithFixedDelay(
        this::compactCache, 0, 10, TimeUnit.SECONDS);
```

Periodic schedules in `ScheduledExecutorService` use relative durations and do not persist schedules durably. If the application requires date/time calendar schedules or accurate handling of runs missed during checkpoint, persist the schedule definition and latest run state, then recompute schedules after restore.

## 2. Calendar clock vs. duration-measuring clock

Scheduler design must distinguish two kinds of time:

- **Wall-clock time:** calendar time such as `Instant`, date, time, and time zone. Cron uses this time to determine which day a run belongs to and when it occurs.
- **Monotonic time:** monotonically increasing time used to measure durations and deadlines within a process, typically obtained from `System.nanoTime()`.

Do not save a `System.nanoTime()` value in a checkpoint or database for reuse after restore. This value is meaningful only within a single system execution run and is not a timestamp comparable across processes or startups.

For cron, store the `Instant` of the scheduled run and use `ZoneId` to interpret the schedule expression. On restore, read the current clock and recompute the next run. Use an injectable `Clock` in the scheduler to test time jumps without waiting for the real clock.

```java
Clock clock = Clock.systemUTC();
Instant now = clock.instant();

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime localNow = now.atZone(zone);
```

The system clock may be adjusted by NTP or administrators. If time jumps forward, some cron marks may become overdue; if time jumps backward, a schedule mark may reappear depending on the cron implementation. For critical tasks, store `scheduledAt` or a run identifier key to avoid duplicate execution when the clock changes.

## 3. Time zones and Daylight Saving Time (DST)

A cron expression such as `0 30 2 * * *` can mean different things depending on the time zone. If the application runs across multiple machines, do not rely on the JVM default time zone. Configure `ZoneId` explicitly:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
```

Region-based time zones can have their own historical and future rules. In regions with DST, a local hour may be skipped when the clock jumps forward and may occur twice when the clock falls back.

For example, a schedule at 02:30 in a region transitioning into DST may encounter a day where 02:30 does not exist. A schedule at 01:30 on a fallback day may match two different `Instant`s. A cron library may choose to skip, shift, or run twice depending on its semantics.

Decide and test:

- When a local time does not exist, should the run be skipped, shifted to the next valid time, or follow another rule?
- When a local time occurs twice, should it run once or twice?
- Is the run identifier based on `Instant` or local date-time plus zone?
- When the timezone database (tzdb) version changes, are saved schedules recomputed under the new rules?

For financial tasks or business processes depending on business days, store `scheduledAt` as an `Instant`, `ZoneId`, and a business schedule key (e.g., report date) for auditing and deduplication.

## 4. Why can checkpointing produce missed runs?

Suppose a task runs daily at 01:00. The application checkpoints at 00:50 and restores at 03:15. While the process was inactive, the 01:00 mark passed. The in-heap scheduler may still hold a `ScheduledFuture` or delay computed before checkpoint, but it cannot automatically decide whether business logic requires catching up or skipping the 01:00 run.

To handle this properly, separate two questions:

1. **When is the next scheduled run?** Compute using the cron expression, zone, and wall clock after restore.
2. **How should past marks be handled?** Apply the misfire policy defined for each task type.

Do not simply add one period to the old timestamp. With cron, the next schedule must be recomputed by the cron library from the current time or from the saved cursor, depending on the misfire policy.

## 5. Missed-run handling policies

A *misfire* is a scheduled run that came due, yet the scheduler did not trigger at the scheduled time, for example because the application was checkpointed, restoring, starting up, or overloaded.

Common policies:

| Policy | Behavior after restore | Suitable for |
|---|---|---|
| Skip | Mark overdue points as skipped and wait for the future point | Refresh/cache or tasks needing only the latest state |
| Fire once now | Run once immediately after restore, even if multiple points were missed | State sync or reports that can be consolidated |
| Catch up all | Run each missed point in order | Tasks that must process each period individually |
| Coalesce | Merge multiple missed points into a single run processing a range | Data aggregation, snapshot recomputation |
| Bounded catch-up | Catch up at most N runs or within a time budget; skip/coalesce the rest | Schedules that can accumulate many runs during downtime |

There is no single right policy for every task. For example, a job sending reminder emails per milestone might need bounded catch-up; a cache refresh job usually only needs to run once; a daily revenue calculation job may have to process each unfinished day.

### 5.1. Skip

Skip ignores all runs whose `scheduledAt` fell during the period the application was inactive. After restore, the scheduler computes the next future cron point and continues normally.

This policy fits when old runs no longer have value. For example, a 01:00 cache refresh can be replaced by a refresh right after restore or waiting for the next schedule. When skipping, record the time window and count of skipped runs for observability.

### 5.2. Fire once now

If one or more points were missed, run the task once immediately after dependencies are ready. Multiple overdue points are represented by a single execution.

This policy fits tasks synchronizing the latest state. However, the task must read current state or cover the entire missed window. If each milestone represents a distinct business period, fire once now can drop period data.

### 5.3. Catch up all

Runs each missed point in chronological order. This preserves every period but can generate a large load spike after restore. If downtime lasts multiple days, the scheduler could produce thousands of consecutive runs.

Use catch-up all only when each point genuinely needs separate processing and the system can handle the catch-up volume. Enforce limits on duration, concurrent tasks, and resumability in case catch-up is interrupted again.

### 5.4. Coalesce

Merges a sequence of missed points into a single run representing a range. For example, if an aggregation job runs hourly and the application was down for 6 hours, a single run can accept `from=lastCompletedAt` and `to=now` and aggregate all changed data.

Coalescing is valid only when business logic can process a range of data. Do not coalesce work where each run has independent side effects, such as sending one invoice per period.

### 5.5. Bounded catch-up

Catches up at most the N most recent points or at most within a time window. Older points are skipped or merged according to a separate rule. This bounds recovery load, yet requires clearly recording what ran, what was skipped, and why.

## 6. Persisting schedule and run state

If the schedule lives only in memory, restore may keep old Java state, which is insufficient to know whether a run completed from a business perspective. For critical tasks, persist execution state to a database or durable store.

A state table may contain:

| Field | Purpose |
|---|---|
| `job_id` | Stable identifier of the job |
| `schedule_version` | Version of cron expression and configuration |
| `zone_id` | Time zone used to interpret the schedule |
| `scheduled_at` | Instant of the intended run mark |
| `started_at` | Execution start timestamp |
| `completed_at` | Completion timestamp |
| `status` | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `SKIPPED` |
| `attempt` | Attempt count for the same mark |
| `lease_owner` / `lease_until` | Owner and lease expiration when running multiple instances |

A run identifier can be a unique key `(job_id, schedule_version, scheduled_at)`. This helps prevent creating duplicate run records when multiple instances restore together or the scheduler restarts.

When a worker starts, it must claim a run via a transaction or conditional lease mechanism. Upon completion, update `SUCCEEDED` along with `completed_at`. If the process stops mid-run, the run may remain in `RUNNING`; the recovery procedure must detect expired leases and decide whether to retry or reconcile results before re-running.

Do not store only a `lastRun` variable in the heap if the job must avoid loss or duplicate runs across checkpoints, crashes, and multiple instances. Durable state distinguishes runs that were scheduled, started, completed, or skipped.

## 7. Idempotency and re-run tasks

Catch-up, retries, or restores can cause the same scheduled mark to execute again. Tasks should be designed idempotently: re-running the same `job_id` and `scheduled_at` must not produce duplicate business results.

For example, instead of always inserting a new report row, a job can write results keyed by `(report_date, report_type)` via upsert. For message sending, use a stable event ID or outbox to ensure messages are not unintentionally published twice.

Idempotency must cover external side effects as well. A database transaction cannot roll back an email already sent or an HTTP request already processed by another server. For tasks calling external services, use an idempotency key if the API supports it and store execution outcomes for reconciliation.

## 8. Pausing the scheduler before checkpoint

A scheduler is a work producer. Before checkpoint, prevent it from triggering new tasks and handle running tasks within a deadline.

A typical sequence:

1. Close job admission so no new runs are accepted.
2. Pause triggers or cancel the next future.
3. Wait for running tasks to complete within a bounded timeout.
4. Persist necessary run state and misfire cursors.
5. Stop scheduler threads or place the scheduler in a safe state per the library API.
6. Allow checkpoint once no callbacks can access closed shared resources.

Do not simply call `future.cancel(false)` and assume the job has stopped. The `false` argument does not interrupt an already-running task; that task can keep running. Track active tasks and await completion or apply a safe cancellation policy.

With Quartz, Spring Scheduler, or other libraries, use the pause/shutdown and misfire-handling APIs provided by the library. Do not manipulate the scheduler's internal threads directly. If the library offers CRaC integration, prefer using that integration to manage timers, workers, and trigger state.

## 9. Recomputing schedules after restore

After restore, the scheduler must read the current clock and durable state, then apply the misfire policy before opening schedules.

Workflow:

1. Recover the database, message broker, and dependencies required by the job.
2. Read the cron configuration, `ZoneId`, schedule version, and latest run state.
3. Determine the missed interval from the saved cursor up to the current time.
4. Generate catch-up runs according to policy: skip, fire once, catch-up, coalesce, or bounded catch-up.
5. Claim runs using a lock or lease to prevent multiple instances from executing simultaneously.
6. Register the next future cron point.
7. Open admission and readiness for the scheduler.

Register resources in dependency order: databases and backing services before the scheduler; the scheduler before ingress or other producers if they depend on schedules. The global context invokes `beforeCheckpoint` in reverse registration order and `afterRestore` in registration order. Thus, the scheduler can stop before dependencies close and resume only after dependencies have recovered.

## 10. Example CronResource design

The following example illustrates a scheduler adapter responsible for pausing schedules, saving state, and restoring schedules. Cron calculation is abstracted via `CronPlan`, as syntax and semantics vary across cron libraries.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CronResource implements Resource {
    private final CronPlan plan;
    private final JobStateStore stateStore;
    private final JobRunner runner;
    private final Clock clock;
    private final ZoneId zone;
    private final MissedRunPolicy policy;

    private volatile boolean paused;

    public CronResource(
            CronPlan plan,
            JobStateStore stateStore,
            JobRunner runner,
            Clock clock,
            ZoneId zone,
            MissedRunPolicy policy) {
        this.plan = plan;
        this.stateStore = stateStore;
        this.runner = runner;
        this.clock = clock;
        this.zone = zone;
        this.policy = policy;
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        paused = true;
        runner.stopAdmissionAndAwaitCompletion(Duration.ofSeconds(20));
        stateStore.flush();
        runner.stopScheduler();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        Instant now = clock.instant();
        JobCursor cursor = stateStore.loadCursor(plan.jobId());

        MissedRunDecision decision = policy.decide(
                plan, cursor, now, zone);

        runner.executeMissedRuns(decision);
        runner.scheduleNext(plan.nextAfter(now, zone));
        runner.startScheduler();
        paused = false;
    }
}
```

The interfaces in the example are application-defined abstractions. A real implementation must ensure `stopAdmissionAndAwaitCompletion()` has a timeout and reports an error if running jobs do not stop; `executeMissedRuns()` must claim each run via transaction or lease; and `scheduleNext()` must use the cron time calculated with `Clock` and `ZoneId`.

The example also assumes `CronResource`'s dependencies have recovered before `afterRestore` runs. If the scheduler has separate resources for the database or broker, register backing resources before `CronResource` in the same context or in the corresponding context tree.

## 11. Misfire decision model

A policy can be configured explicitly:

```java
public enum MisfireMode {
    SKIP,
    FIRE_ONCE_NOW,
    CATCH_UP_ALL,
    COALESCE,
    BOUNDED_CATCH_UP
}

public interface MissedRunPolicy {
    MissedRunDecision decide(
            CronPlan plan, JobCursor cursor, Instant now, ZoneId zone);
}
```

When computing overdue marks, the policy receives the cursor and the current time:

```java
public interface CronPlan {
    String jobId();

    Instant nextAfter(Instant instant, ZoneId zone);

    Instant nextAfterOrAt(Instant instant, ZoneId zone);
}

public interface JobStateStore {
    JobCursor loadCursor(String jobId);

    void flush() throws Exception;
}

public interface JobRunner {
    void stopAdmissionAndAwaitCompletion(Duration timeout) throws Exception;

    void executeMissedRuns(MissedRunDecision decision) throws Exception;

    void scheduleNext(Instant nextFireTime) throws Exception;

    void startScheduler() throws Exception;

    void stopScheduler() throws Exception;
}
```

`MissedRunDecision` and `JobCursor` must be defined according to business requirements. For example, the cursor can hold `lastCompletedScheduledAt`, while the decision holds the list of marks to execute, the range to coalesce, and marks flagged as skip. Configuration can be stored separately via a record containing `MisfireMode`, `maxCatchUpRuns`, and `maxCatchUpWindow`, and `MissedRunPolicy` implemented from that configuration. Do not simply overwrite the cursor with `now` if older runs have not been processed or explicitly marked.

## 12. Configuring misfire per job type

An application usually has multiple job types, each requiring a different policy:

| Job type | Typically suitable policy | Reason |
|---|---|---|
| Refresh cache | Fire once now or skip | Only latest state is needed |
| Sync current snapshot | Coalesce | Can synchronize a range of changes in one run |
| Compute daily reports | Catch-up or bounded catch-up | Each day is a distinct business period |
| Send reminder emails | Bounded catch-up or skip | Avoid sending a flood of stale emails after downtime |
| Purge expired data | Fire once now or coalesce | Can scan all currently expired data |
| Transaction reconciliation | Controlled catch-up | Must process each period and maintain an audit trail |
| Periodic health check | Skip | No need to catch up missed checks |

Do not use a single global misfire policy for all jobs. Configure the policy alongside the job definition, store the schedule version, and log policy changes so you can explain why a run was skipped or coalesced.

## 13. Limiting load during catch-up

Catch-up can cause the scheduler to produce a heavy load spike right after restore. Control:

- Number of concurrent jobs.
- Maximum catch-up runs per job.
- Total time budget allocated for catch-up.
- Rate at which tasks are submitted to the worker pool.
- Quotas and rate limits of external services.
- Priority between catch-up jobs and live requests.

You can split catch-up into small batches, save the cursor after each batch, and continue in a subsequent run. If another restore occurs mid-way, the durable cursor lets execution resume without re-running the entire history.

Do not let all jobs catch up simultaneously. Prioritize jobs needed to open readiness, then run less critical jobs in the background. However, separate per-feature readiness clearly so the system does not accept requests needing data that has not yet been updated.

## 14. Scheduler frameworks and misfire semantics

Frameworks have their own ways of expressing cron and handling misfires. Before integrating CRaC, determine:

- Are triggers persisted durably or held only in the heap?
- Does the scheduler provide safe pause/resume and shutdown APIs?
- By what threshold is a trigger misfire defined?
- When the scheduler restarts, does it automatically fire once, skip, or catch up?
- Can a timezone be configured directly on the cron trigger?
- Can the job run concurrently across multiple nodes?
- Is there a built-in cluster lock or misfire recovery mechanism?

With Quartz, inspect the `CronTrigger` misfire instruction and job store configuration; do not assume `SMART_POLICY` means the same thing for every trigger type. With Spring, check which executor `@Scheduled` and `TaskScheduler` use, how the cron timezone is configured, and how running tasks are handled when the context stops. If a framework or library provides CRaC integration, use that integration instead of manually shutting down internal threads.

A persistent scheduler still needs a business policy for missed runs. Storing triggers in a database does not automatically decide whether to catch up all points or coalesce them.

## 15. Testing schedules across checkpoint–restore

Use a mock `Clock` or controllable time provider to test without waiting for real cron wall-clock times.

Cases to test:

1. Restore before the next cron point: the scheduler calculates the future time accurately.
2. Restore right after a point: the policy handles one missed run accurately.
3. Restore after multiple points: skip, fire once, catch-up, coalesce, and bounded catch-up yield distinct results matching configuration.
4. Job running when checkpoint starts: admission closes and the task finishes or checkpoint fails per deadline.
5. Checkpoint fails mid-quiesce: paused schedulers are safely recovered.
6. Repeated restores before catch-up finishes: durable cursor prevents losing or duplicating periods.
7. Two instances restore simultaneously: only one instance claims the same scheduled run.
8. Clock jumps forward or backward: run keys and cursors prevent accidental duplicate processing or omissions.
9. DST gap and overlap: zoned schedules follow the chosen policy.
10. Job calls external APIs: idempotency keys keep side effects stable across retries.

When measuring performance, record time from restore until scheduler readiness, missed-run count, catch-up count, catch-up processing duration, and load on dependencies. Do not measure only JVM restore time while ignoring scheduled-work backlog.

## 16. Logging and observability

Each run should have traceable log fields:

- `job_id` and `schedule_version`.
- `scheduled_at` and `zone_id`.
- `started_at`, `completed_at`, and duration.
- `run_id` or a stable idempotency key.
- Status: success, failed, skipped, misfired, or coalesced.
- Misfire policy and affected time range.
- Remaining catch-up count and processed count.
- Instance or lease owner that claimed the run.

Useful metrics include missed-run count, catch-up run count, skipped-job count, catch-up duration, scheduler lag, and running-job count. Avoid using `run_id` or full timestamps as metric labels because cardinality can explode; use logs or traces for detailed identifiers.

## 17. Implementation checklist

- [ ] Distinguished cron calendar from fixed rate and fixed delay.
- [ ] Cron expressions have an explicit `ZoneId`, not relying on the JVM default timezone.
- [ ] DST gaps and overlaps have decided and tested rules.
- [ ] Do not store `System.nanoTime()` as a timestamp used across restore.
- [ ] Scheduler stops accepting new jobs before checkpoint.
- [ ] Running tasks are drained or handled within a deadline.
- [ ] Important schedules and run cursors are persisted durably.
- [ ] Each job has an appropriate misfire policy: skip, fire once, catch-up, coalesce, or bounded catch-up.
- [ ] Catch-up has load limits and can resume across multiple restores.
- [ ] Each scheduled run has a stable identifier and idempotent processing.
- [ ] Multiple instances cannot claim the same run if the job requires single execution.
- [ ] After restore, dependencies are ready before the scheduler, and the scheduler before dependent ingress.
- [ ] Tested clock jumps, DST, in-flight jobs, and repeated restores.
- [ ] Have logs and metrics for misfires, catch-up, and schedule lag.

## 18. References

- [Java `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): semantics of fixed-rate and fixed-delay scheduling.
- [Java `Clock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): clock abstraction for reading current time and testing.
- [Java `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): time zone identifiers and local time conversion rules.
- [CRaC API — `Resource`](https://javadoc.io/doc/org.crac/crac/latest/org/crac/Resource.html): callbacks managing resources before checkpoint and after restore.
- [Quartz Scheduler — CronTrigger Tutorial](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-06.html): cron trigger and timezone configuration.

Cron schedules must be recomputed against the wall clock after restore, while deadlines and durations within a single run should use the monotonic clock. Stop the scheduler and handle running tasks before checkpoint; after restore, recover dependencies, read durable cursors, and apply the misfire policy per job. Skip, fire once, catch-up, coalesce, and bounded catch-up carry different business impacts, so combine idempotency, load limiting, and observability so periodic schedules continue accurately after each checkpoint–restore cycle.
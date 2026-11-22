# Canceling Schedules Before Checkpoint and Re-registering Schedules After Restore

In Java, periodically executed tasks are commonly managed using ScheduledExecutorService, ScheduledThreadPoolExecutor, or framework schedulers. They may use background threads, task queues, timers, and Future states to determine the next execution.

When an application uses CRaC (Coordinated Restore at Checkpoint), do not assume a schedule registered before checkpoint will continue properly after restore. Scheduler threads may have stopped, relative wait times may no longer be appropriate, dependencies such as databases or HTTP clients need to be recreated, and runs may be duplicated if the application registers new schedules without managing old ones.

The common organization is to stop triggers and wait for running tasks to complete before checkpointing, persist business schedule state, then create a new scheduler and re-register tasks after restore. If the checkpoint is aborted, the application must restart schedules in the original process.

## 1. How do scheduler, task, and schedule differ?

Java provides ScheduledExecutorService to schedule tasks to run after a delay or repeat periodically.

Key components:

| Component | Role |
|---|---|
| ScheduledExecutorService | API for scheduling tasks over time |
| ScheduledThreadPoolExecutor | Common implementation using a thread group to run scheduled tasks |
| Runnable / Callable | The work being executed |
| ScheduledFuture | Represents a scheduled task; can cancel or inspect status |
| Trigger / schedule metadata | Business rules deciding when a task needs to run next |

Example:

~~~java
ScheduledExecutorService scheduler =
    Executors.newScheduledThreadPool(2);

ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
    this::refreshCache,
    0,
    5,
    TimeUnit.MINUTES
);
~~~

In the example, scheduler manages threads and queues; future represents the registered schedule; refreshCache() is the actual work.

Distinguish between a **business schedule** and a **ScheduledFuture object**. A business schedule might be "synchronize data at 02:00 every day in time zone Asia/Ho_Chi_Minh." ScheduledFuture is merely a specific registration inside a running scheduler. After restore, the application should recreate registrations from the business schedule rather than relying on the old future.

## 2. Why cancel schedules before checkpointing?

A scheduler can hold:

- Background threads waiting or executing.
- A queue of one-shot and periodic tasks.
- ScheduledFuture state.
- Delays calculated against a monotonic clock.
- Runnables that may reference DataSource, HTTP clients, file channels, or other beans.
- Execution state of an incomplete run.

If a checkpoint is created while a task is running, problems can appear after restore:

- The task continues running while external dependencies have closed or timed out.
- Both old and new schedules are registered, causing the task to run twice.
- A task partway through writing data gets re-executed.
- The next run is delayed or executes immediately contrary to expectations.
- The scheduler holds references to old resources after new resources were created.

Stopping schedules before checkpointing helps the application control the boundary between the two lifecycles. The goal is not merely stopping scheduler threads; it must also ensure running work has finished or been canceled per business policy.

### Canceling a schedule is not the same as immediately stopping a running task

With ScheduledFuture:

- cancel(false) prevents future executions without requesting interruption of the currently executing run.
- cancel(true) requests interrupting the executing thread if possible.
- Neither guarantees the task stops immediately. The Runnable must cooperate with interrupt signals and not be stuck indefinitely in I/O or locks.

Therefore, a safe workflow typically includes: stopping creation of new runs, canceling the future, waiting for the running task to finish, and shutting down the scheduler.

## 3. Choosing the right scheduling method

ScheduledExecutorService has three common scheduling methods.

### schedule(): run once after a delay

~~~java
scheduler.schedule(
    this::runReport,
    30,
    TimeUnit.SECONDS
);
~~~

Suitable for a task that only needs to run once after a duration. If recovery after checkpoint is required, the application must store the timestamp or business deadline to compute a new delay.

### scheduleAtFixedRate(): period by start time

~~~java
scheduler.scheduleAtFixedRate(
    this::poll,
    0,
    10,
    TimeUnit.SECONDS
);
~~~

The schedule tries to keep the spacing between execution start times according to the specified period. If one run takes longer than the period, later runs start later; the same periodic task does not overlap itself in this executor.

This approach fits when a steady time cadence is needed. However, after a long checkpoint interval, the application must decide whether to execute missed runs or run only once to catch up with current state.

### scheduleWithFixedDelay(): wait an interval after the previous run finishes

~~~java
scheduler.scheduleWithFixedDelay(
    this::syncData,
    0,
    10,
    TimeUnit.SECONDS
);
~~~

The delay is measured from when the previous execution finishes until the next begins. This approach fits polling or synchronization work that does not need to track an absolute clock cadence.

### Comparison

| Criterion | Fixed rate | Fixed delay |
|---|---|---|
| Period reference point | Start times on a fixed cadence | After the previous run completes |
| When a task runs long | Next run may start immediately when previous ends if cadence fell behind | Always waits the full delay after completion |
| Suitable for | Cadence-based polling, periodic metrics | Sync, cleanup, or work needing rest between runs |
| Upon restore | Must decide how to handle missed cadence ticks | Can restart with the defined delay |

Do not use fixed rate just because you want "run once every N seconds." If processing time varies and you do not want executions running back-to-back after falling behind, fixed delay is usually more predictable.

## 4. Persist business schedules instead of relying on old delays

Scheduler delays are usually relative durations. Meanwhile, business schedules are often described by absolute timestamps or time-zone rules.

Examples:

- Run report at 02:00 every day.
- Sync data every 15 minutes.
- Refresh token before expiration time.
- Run cleanup on the first Sunday of each month.

If a checkpoint exists for some duration, a delay calculated before checkpoint may no longer represent the right execution time after restore.

Persist information such as:

~~~text
jobId            = daily-report
scheduleVersion  = 4
zoneId           = Asia/Ho_Chi_Minh
nextRunAt        = 2026-11-14T02:00:00+07:00
lastSuccessfulAt= 2026-11-13T02:00:12+07:00
missedRunPolicy  = SKIP_AND_RUN_ONCE
~~~

After restore, use the current Clock to compute the delay:

~~~java
Duration remaining = Duration.between(
    clock.instant(),
    nextRunAt
);

long delayMillis = Math.max(0, remaining.toMillis());
~~~

If nextRunAt is already in the past, the application needs an explicit policy:

- **SKIP:** drop missed runs and calculate the next run.
- **RUN_ONCE:** run once immediately after restore without catching up each period.
- **CATCH_UP:** catch up missed runs if each run carries business meaning.
- **COALESCE:** merge multiple missed runs into a single run processing the latest state.

Do not default to catching up everything. After a long interval, hundreds of accumulated runs could overload databases or dependent services.

### Time-zone and daylight saving time schedules

For local-time schedules, store the ZoneId alongside schedule rules. Do not store a string "02:00" and assume it always corresponds to the same Instant. Time-zone rules can change; in some regions, local times can be skipped or repeated during daylight saving transitions.

In Vietnam, applications commonly use the Asia/Ho_Chi_Minh time zone. Even so, use ZoneId instead of manually adding or subtracting a fixed number of hours when calculating daily/weekly/monthly schedules.

## 5. Stopping the scheduler safely before checkpointing

A preparation workflow may include:

1. Block new schedule registrations and stop accepting task trigger requests.
2. Cancel ScheduledFuture to prevent subsequent runs.
3. Wait for the current run to finish or send an interrupt according to policy.
4. Shut down the scheduler so it accepts no additional tasks.
5. Wait for the executor to finish within a bounded time.
6. Persist nextRunAt, business state, and information needed to re-register.
7. Mark the component prepared for checkpoint.

Do not hold the component lock while waiting for the executor to terminate if the Runnable may need the same lock to finish. Transition state to STOPPING inside a short synchronized block, then release the lock before awaitTermination().

### Example of stopping ScheduledThreadPoolExecutor

~~~java
private void stopScheduler() throws InterruptedException {
    ScheduledThreadPoolExecutor old;

    synchronized (this) {
        old = scheduler;
        if (old == null) {
            return;
        }

        if (scheduledFuture != null) {
            scheduledFuture.cancel(false);
        }

        old.shutdown();
    }

    if (!old.awaitTermination(30, TimeUnit.SECONDS)) {
        old.shutdownNow();

        if (!old.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Scheduled tasks did not terminate"
            );
        }
    }

    synchronized (this) {
        if (scheduler == old) {
            scheduler = null;
            scheduledFuture = null;
        }
    }
}
~~~

Configure ScheduledThreadPoolExecutor to handle scheduled tasks on shutdown:

~~~java
ScheduledThreadPoolExecutor executor =
    new ScheduledThreadPoolExecutor(1);

executor.setRemoveOnCancelPolicy(true);
executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
~~~

These settings remove canceled tasks from the queue and stop continuing delayed/periodic tasks when the executor shuts down under the corresponding policies.

If a task does not stop after shutdownNow(), do not create a new scheduler running the same work. Two parallel runs can write duplicate data or contend for resources. Keep the application in an unready state, log the unfinished task, and handle it according to operational policy.

## 6. Canceling schedules with a CRaC Resource

CRaC provides Resource for components to register callbacks:

- beforeCheckpoint(): cancel schedules, stop the executor, and persist required state.
- afterRestore(): create a new scheduler and re-register schedules.

The example below illustrates a job running periodically with fixed delay. The job and dependencies are passed into the resource; in a real application, the job should retrieve current dependencies upon execution rather than holding a previously opened Connection or client.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ScheduledJobResource implements Resource {
    private final Clock clock;
    private final Runnable job;
    private final Duration interval;

    private Instant nextRunAt;
    private ScheduledThreadPoolExecutor scheduler;
    private ScheduledFuture<?> scheduledFuture;

    public ScheduledJobResource(
            Clock clock,
            Runnable job,
            Duration interval,
            Instant nextRunAt) {
        this.clock = clock;
        this.job = job;
        this.interval = interval;
        this.nextRunAt = nextRunAt;

        startScheduler();
        Core.getGlobalContext().register(this);
    }

    private synchronized void startScheduler() {
        if (scheduler != null) {
            if (!scheduler.isShutdown()) {
                return;
            }

            if (!scheduler.isTerminated()) {
                throw new IllegalStateException(
                    "Previous scheduler has not terminated"
                );
            }
        }

        ScheduledThreadPoolExecutor next =
            new ScheduledThreadPoolExecutor(1);

        next.setRemoveOnCancelPolicy(true);
        next.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        next.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);

        long delayMillis = Math.max(
            0,
            Duration.between(clock.instant(), nextRunAt).toMillis()
        );

        scheduler = next;
        scheduledFuture = next.scheduleWithFixedDelay(
            this::runOneSafely,
            delayMillis,
            interval.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }

    private void runOneSafely() {
        try {
            job.run();
        } catch (RuntimeException failure) {
            // Log and apply the job's error policy.
            reportFailure(failure);
        } finally {
            synchronized (this) {
                nextRunAt = clock.instant().plus(interval);
            }
        }
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopScheduler();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        startScheduler();
    }

    public void restartAfterAbortedCheckpoint() {
        startScheduler();
    }

    private void stopScheduler() throws InterruptedException {
        ScheduledThreadPoolExecutor old;

        synchronized (this) {
            old = scheduler;
            if (old == null) {
                return;
            }

            if (scheduledFuture != null) {
                scheduledFuture.cancel(false);
            }

            old.shutdown();
        }

        if (!old.awaitTermination(30, TimeUnit.SECONDS)) {
            old.shutdownNow();

            if (!old.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Scheduled job is still running"
                );
            }
        }

        synchronized (this) {
            if (scheduler == old) {
                scheduler = null;
                scheduledFuture = null;
            }
        }
    }

    private void reportFailure(RuntimeException failure) {
        // Log and update error metrics.
    }
}
~~~

This is an illustrative skeleton; add a logger, error handling per application policy, and ensure the job does not hold stale resources. The constructor calls startScheduler() before registering the Resource to demonstrate lifecycle; in a real application, ensure the job does not start before its dependencies are ready.

### Why create a new scheduler after restore?

After beforeCheckpoint(), the old scheduler was shut down and its threads terminated. Therefore, afterRestore() creates a new ScheduledThreadPoolExecutor and registers a new future.

Do not rely on an old ScheduledFuture to continue the schedule. The future is tied to the old executor and queue; it is not independent business schedule metadata.

Each restart must ensure only one scheduler and one future exist for the same job. The startScheduler() method should be idempotent so multiple calls within the same lifecycle do not create duplicate schedules.

## 7. Re-registering schedules at the right time after restore

After restore, not every job should run immediately. Before registering schedules, the application may need to:

1. Recreate DataSource, HTTP clients, file channels, or other resources.
2. Verify dependencies are ready.
3. Reload schedule configuration and secrets if needed.
4. Calculate the next execution time from nextRunAt and the missed-run policy.
5. Create a new scheduler.
6. Register a single future.
7. Reopen request acceptance or job triggering mechanisms.

If a scheduler resource depends on a database resource, ensure the database is ready before jobs are allowed to run. You can coordinate ordering via a lifecycle coordinator instead of letting independent callbacks start work too early.

### Do not hold Connections inside Runnables

A Runnable can persist on the heap across a checkpoint. If the Runnable holds a closed Connection, EntityManager, HTTP response, or file channel, re-registering the future does not make those dependencies valid.

Let each execution obtain the current dependency:

~~~java
Runnable refreshJob = () -> {
    DataSource current = dataSourceProvider.current();

    try (Connection connection = current.getConnection()) {
        refreshFromDatabase(connection);
    } catch (SQLException failure) {
        throw new IllegalStateException(failure);
    }
};
~~~

dataSourceProvider is an application abstraction returning the current DataSource. This lets the job use the new pool after restore rather than holding a reference to the old pool.

## 8. Handling running tasks and avoiding duplicate runs

Canceling a future does not automatically undo work a task has already performed. For example, a job may have sent an email, updated a database, or written a file before being interrupted.

Design tasks according to these principles:

- Process in batches or records with explicit commit boundaries.
- Use transactions for groups of changes requiring consistency.
- Use idempotency keys so a rerun does not create duplicate side effects.
- Record lastSuccessfulAt or a business checkpoint after completion.
- Check interrupts at safe points if the task supports stopping.
- Do not swallow InterruptedException; restore the interrupt flag or terminate per the stop protocol.

Example:

~~~java
public void runBatch() {
    for (Record record : loadPendingRecords()) {
        if (Thread.currentThread().isInterrupted()) {
            return;
        }

        processIdempotently(record);
        markCompleted(record.id());
    }
}
~~~

If a task cannot stop mid-way, let it finish before checkpointing. If a task is forcibly stopped, persist state so after restore it can resume from uncommitted records.

### Ensuring one job does not run on two instances

When restoring from the same checkpoint image into multiple instances, each instance can register the same schedule. If the work acts on shared resources, all instances may run the same job.

In that case, in-memory schedules are insufficient to guarantee a single executor. An out-of-process coordination mechanism is needed, such as:

- Database lease or distributed lock.
- Leader election.
- Job queue with consumer coordination.
- Centralized job scheduler.
- Idempotency keys and unique constraints at the result store.

Java locks only coordinate threads within a single process; they do not stop another instance from running the same job.

## 9. Handling missed schedules during checkpoint time

Suppose a job runs every 10 minutes. The application checkpoints at 10:02 and restores at 10:47. Four scheduled runs may have been missed.

Do not take the old future and try to resume without defining a policy. Instead, use nextRunAt or lastSuccessfulAt to decide:

| Policy | Behavior after restore | Suitable example |
|---|---|---|
| Skip | Drop missed runs, wait for next slot | Periodic cache refresh |
| Run once | Run once immediately, then continue schedule | Synchronize latest state |
| Catch up | Catch up each missed run | Process each mandatory data period |
| Coalesce | Merge multiple periods into one task | Aggregate metrics or cleanup |

If using catch-up, limit the number of catch-up runs in one batch and control load. If using run once, the task must fetch the latest state rather than assuming each tick represents a distinct data slice.

### Computing the next execution time

Example with a fixed-delay schedule based on current time:

~~~java
Instant nextRunAt = clock.instant().plus(interval);
~~~

With a local-time schedule:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime now = ZonedDateTime.now(clock.withZone(zone));

ZonedDateTime nextRun = now
    .toLocalDate()
    .plusDays(1)
    .atTime(LocalTime.of(2, 0))
    .atZone(zone);

Instant nextRunAt = nextRun.toInstant();
~~~

This is only an illustration for a daily schedule at 02:00; handle the case where the time has already passed today and ZoneId transition rules. Use java.time instead of storing a fixed delay for business schedules.

## 10. If a checkpoint is aborted, how do we re-register schedules?

A possible scenario:

1. Resource A cancels schedules and shuts down the scheduler in beforeCheckpoint().
2. Resource B runs its callback afterward and throws an exception.
3. CRaC aborts the checkpoint.
4. The original Java process continues, yet scheduler A is already stopped.

afterRestore() is not a rollback callback for an aborted checkpoint. It is used when the process is actually restored from a checkpoint image.

If the application calls Core.checkpointRestore(), it can catch CheckpointException on the coordinating thread and call restartAfterAbortedCheckpoint():

~~~java
try {
    Core.checkpointRestore();

    // When restore succeeds, afterRestore() has already registered the new schedule.
    resumeApplication();

} catch (CheckpointException checkpointFailure) {
    try {
        scheduledJobResource.restartAfterAbortedCheckpoint();
    } catch (RuntimeException restartFailure) {
        checkpointFailure.addSuppressed(restartFailure);
        markApplicationNotReady();
    }

    throw checkpointFailure;

} catch (RestoreException restoreFailure) {
    // This is a failure on the restored instance.
    // Do not treat it like an aborted checkpoint.
    markApplicationNotReady();
    throw restoreFailure;
}
~~~

If restarting the schedule fails, the application must not mark itself ready. Log the root error and the restart error, keep the job in a stopped/failed state, and let monitoring mechanisms handle it.

### When checkpoint is requested via jcmd

A request can be sent from outside:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

In this case, application code has no Core.checkpointRestore() call to wrap with try/catch. Therefore, the application's coordinator does not automatically receive a CheckpointException along its API call path.

If recovering schedules after an aborted checkpoint is mandatory, use an internal administrative endpoint or mechanism so the application itself calls Core.checkpointRestore() and performs rollback. If operating directly with jcmd, a separate administrative procedure is needed to detect failed checkpoints and bring schedulers back to an active state. Do not assume CRaC will automatically invoke afterRestore() for an aborted checkpoint case.

## 11. Framework-managed schedules

Not every application creates ScheduledExecutorService directly. Frameworks may manage schedulers and register tasks via annotations or beans.

For example, Spring can use @Scheduled:

~~~java
@Scheduled(fixedDelayString = "PT5M")
public void refreshCache() {
    // Refresh cache.
}
~~~

If using a framework, determine:

- Which scheduler bean executes the method.
- Where the thread pool is created and closed.
- Which lifecycle API can pause/resume or shut down the scheduler.
- Whether reinitializing beans after restore registers duplicate schedules.
- Whether dependencies injected into jobs are updated after restore.

Do not manually invoke a scheduler initialization method in afterRestore() if the framework also reinitializes the scheduler automatically. That can create two thread pools or two schedules for the same method.

With Quartz or schedulers persisting triggers in a database, distinguish durably persisted schedules from in-process scheduler threads. After restore, do not create duplicate triggers in the JobStore; let the scheduler reconnect to the JobStore per the framework's lifecycle and verify misfire policies. If multiple instances run Quartz together, clustering and database locking configurations must be maintained properly.

## 12. Managing shutdown and errors when stopping tasks

### Tasks do not finish within timeout

If a task does not finish after cancel(false), you can issue shutdownNow() to interrupt threads. However, an interrupt is only a cooperative request. A task stuck in a library that does not support interrupts may keep running.

Do not create a new executor while the old executor is still executing the same work. Choose one of the directions:

- Wait for the task to finish within operational limits and abort the checkpoint if overdue.
- Design the task to check interrupts at safe points.
- Move long work to a durable queue so it can resume.
- Keep the instance in a not-ready state if duplicate execution cannot be prevented.

### Tasks throwing exceptions

A periodic task registered via scheduleAtFixedRate() or scheduleWithFixedDelay() will not continue subsequent runs if one execution ends with an unhandled exception. Decide clearly:

- Log and continue the schedule.
- Stop the schedule and transition job state to failed.
- Perform bounded retries with backoff.
- Send the work to a dead-letter queue or operational handling mechanism.

If choosing to catch RuntimeException in a wrapper to continue, log and update metrics; do not swallow errors completely.

### Shutdown policies of ScheduledThreadPoolExecutor

Two notable policies:

- setExecuteExistingDelayedTasksAfterShutdownPolicy(false): do not execute already-queued delayed one-shot tasks when the executor shuts down.
- setContinueExistingPeriodicTasksAfterShutdownPolicy(false): do not continue periodic tasks after shutdown.

setRemoveOnCancelPolicy(true) removes canceled tasks from the queue, avoiding holding Runnables or unnecessary references longer than needed.

Configuration must be applied whenever creating each new scheduler, including after restore.

## 13. Observing schedules before and after restore

Log the following information:

- jobId and scheduleVersion.
- Timestamp when schedule cancellation starts.
- Timestamp when the future was canceled.
- Number of running tasks.
- awaitTermination result.
- nextRunAt before checkpoint.
- Timestamp when new schedule was registered.
- Missed-run handling policy.
- Result of the first run after restore.

Useful metrics:

| Metric | Meaning |
|---|---|
| scheduled_job_active | Whether the job is currently registered |
| scheduled_job_running | Current running execution count |
| scheduled_job_cancel_total | Number of times the schedule was canceled |
| scheduled_job_restart_total | Number of times the schedule was re-registered |
| scheduled_job_failure_total | Number of task failures |
| scheduled_job_last_success | Timestamp of the most recent successful execution |
| scheduled_job_next_run | Next expected execution timestamp |
| scheduler_termination_timeout_total | Number of times the scheduler did not stop on time |

Use a stable jobId to correlate logs before and after restore. If there are multiple instances, add an instance ID and leader/lease owner to distinguish local schedules from system-wide job execution authority.

## 14. Implementation workflow

### Before checkpoint

1. Transition the job to a state not accepting new triggers.
2. Persist nextRunAt and business state needed to resume.
3. Cancel ScheduledFuture to prevent the next execution.
4. Wait for running tasks to complete; use interrupts if policy permits.
5. Confirm job transactions and resources have been released.
6. Shut down the scheduler and wait for threads to finish.
7. Mark the resource ready for checkpoint.

### After restore

1. Wait for DataSource, HTTP clients, file resources, and other dependencies to be ready.
2. Reload schedule configuration and business state.
3. Compute new delay from nextRunAt or schedule policy.
4. Create a new ScheduledThreadPoolExecutor.
5. Apply shutdown policy and remove-on-cancel policy.
6. Register exactly one future per job.
7. Reopen job execution capability once the scheduler is ready.

### When checkpoint is aborted

If the application calls Core.checkpointRestore():

1. Catch CheckpointException.
2. Check whether the old scheduler has already terminated.
3. If the old scheduler stopped, create a new scheduler.
4. Recalculate the next run from persisted schedule state.
5. Ensure the job is not registered twice.
6. Mark ready only once schedules are active and dependencies are ready.

If checkpointing is requested externally via jcmd, a separate administrative procedure is needed because application threads cannot catch exceptions from that command.

## 15. Principles to remember

- Distinguish business schedules from ScheduledFuture and scheduler threads.
- Cancel futures before checkpointing to prevent the next run.
- cancel(false) does not stop the current run; drain or wait for the task to finish.
- Do not hold the component lock during awaitTermination() if tasks need that lock.
- Shut down the old scheduler and create a new scheduler after restore.
- Persist nextRunAt or business schedule state; do not rely on old delays.
- Explicitly choose skip, run once, catch-up, or coalesce policy for missed runs.
- Do not let Runnables hold closed Connections, clients, or resources across checkpoints.
- Ensure only one future exists per job within an instance.
- If restoring multiple instances, use distributed locks, leases, or a centralized job scheduler to avoid duplicate runs.
- Catch CheckpointException to re-register schedules when a checkpoint is aborted if the application proactively calls Core.checkpointRestore().
- Do not use afterRestore() as a rollback callback for aborted checkpoints.
- If tasks cannot stop or schedules cannot restart, keep the application in an unready state.

A task schedule is operational state of the application, whereas the scheduler is the mechanism executing that schedule. By persisting business schedules, stopping and draining tasks before checkpoint, creating a new scheduler after restore, and handling aborted checkpoints separately, an application can resume background tasks at the right time without creating duplicate schedules or running on stale dependencies.
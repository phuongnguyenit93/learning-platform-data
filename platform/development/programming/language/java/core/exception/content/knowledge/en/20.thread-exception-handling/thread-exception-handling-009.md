# Errors in Periodic Tasks and Their Impact on Subsequent Runs (Java)

## 1. Scenario: If one execution fails, does the schedule keep running?

A periodic task is configured to run repeatedly at a time interval, such as refreshing a cache, cleaning up temporary data, synchronizing state, or sending reports. If a task throws an exception during one execution, what happens to subsequent executions?

In Java, the answer **depends on the scheduling API and whether the exception escapes from the task body**. Specifically, for `ScheduledExecutorService.scheduleAtFixedRate(...)` and `scheduleWithFixedDelay(...)`, the Java contract states:

> If **any execution** of a periodic task encounters an **unhandled exception that escapes the task**, subsequent executions are **suppressed** (*subsequent executions are suppressed*).

This is why a regularly running job can **silently stop operating after a single error**, even though the `ScheduledExecutorService` is still alive and other tasks continue running. The caller cannot catch the error simply by wrapping the scheduling call in a `try/catch`; the error occurs later on an executor thread.

This article clarifies the mechanism, the differences between the two scheduling styles, how to observe and handle exceptions, when to continue or cancel a task, as well as limitations regarding state, retries, and concurrency.

## 2. Distinguishing three separate events

When analyzing a periodic task, separate the following three events:

1. **Successful scheduling:** calling `scheduleAtFixedRate` or `scheduleWithFixedDelay` returns a `ScheduledFuture<?>`. This only confirms that the request was accepted; it does **not** guarantee that all future runs will succeed.
2. **A single run succeeding or failing:** the executor executes `Runnable.run()` on a worker thread. If `run()` returns normally, the schedule can continue. If a `Throwable` escapes the run, the schedule's future transitions to an exceptionally completed state according to the contract of the periodic methods, and subsequent runs are suppressed.
3. **The caller observing the result:** `ScheduledFuture.isDone()`, `isCancelled()`, `get()`, logs/metrics, or a separate error-reporting channel is what allows monitoring to know whether the task is alive or has stopped.

Do not infer that a schedule is still active just because calling `scheduleAtFixedRate(...)` did not throw immediately when creating the schedule. Likewise, do not infer that the entire scheduler is dead just because **one schedule** stopped due to an exception.

## 3. Two important periodic scheduling styles

### `scheduleAtFixedRate`: period measured against scheduled timestamps

Signature:

```java
ScheduledFuture<?> scheduleAtFixedRate(
    Runnable command,
    long initialDelay,
    long period,
    TimeUnit unit);
```

This is an **API signature for reading and understanding**, not a standalone code snippet. For example, with `initialDelay = 0`, `period = 1 SECOND`: the schedule targets timestamps around `t0, t0+1s, t0+2s, ...`, rather than always waiting a full second after the previous run finishes.

If a run takes longer than the period, the next run may start late and may begin almost immediately after the previous one to catch up with the scheduled timestamps. **Executions of the same periodic task do not overlap**, even if the executor has multiple workers; **different** periodic tasks can still run concurrently. Under the `ScheduledThreadPoolExecutor` contract, the effects of a prior execution *happen-before* the next execution of the same periodic task.

**When an exception escapes a run:** subsequent executions of **that same schedule** are suppressed, regardless of whether other periodic timestamps arrive.

### `scheduleWithFixedDelay`: delay measured after the previous run finishes

Signature:

```java
ScheduledFuture<?> scheduleWithFixedDelay(
    Runnable command,
    long initialDelay,
    long delay,
    TimeUnit unit);
```

For example, if the work runs in `300 ms` and `delay = 1 SECOND`, the next run is allowed to start about one second after the previous one **finishes**, i.e., about `1.3 seconds` from when the previous run started (ignoring scheduling latency). If the work takes `3 seconds`, the interval between two start times may be around `4 seconds`.

**When an exception escapes a run:** subsequent executions are also suppressed. This is the core **similarity** between both fixed-rate and fixed-delay.

| Property | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
| --- | --- | --- |
| Next run timing | At scheduled timestamps spaced by `period` | After the previous run finishes, waits an additional `delay` |
| Run takes longer than the period | Next run may be delayed, then start almost immediately | Always has a `delay` wait between completion and the next start |
| Same task overlapping? | No | No |
| Exception escaping a run | Suppresses subsequent executions | Suppresses subsequent executions |
| Best suited for | Sampling/work cadence at a relatively fixed frequency | Polling, cleanup, or tasks that should rest after each completion |

Both mechanisms above use **relative time** and do not natively support cron rules, time zones, or daylight saving time handling. If the requirement is "8:00 AM every day in local time," you need to design the schedule around a clock/calendar using an appropriate API.

The `period` and `delay` parameters for periodic tasks must be **greater than 0**; invalid input can cause `IllegalArgumentException` immediately on the **scheduling caller thread**, unlike errors inside a later `run()` execution.

## 4. Why does an exception stop the schedule?

With `ScheduledThreadPoolExecutor` (the standard implementation of `ScheduledExecutorService`), each periodic schedule is managed by a future object tied to its execution state. When `Runnable` throws an exception that is not caught inside:

- The current run terminates abnormally.
- The schedule's future is marked as **completed exceptionally** (*exceptional completion*).
- The executor **does not re-enqueue that same schedule for the next run**.
- The caller can retrieve the cause via `ScheduledFuture.get()`; because the error completed the future, `get()` throws `ExecutionException` whose `getCause()` is the cause of the failed run.

For a periodic schedule that has not terminated and is operating normally, `future.get()` **does not return a success value after each run**. It can wait indefinitely until the schedule is cancelled or encounters an error (or the waiting thread is interrupted). Therefore, never call `get()` without a timeout on a critical thread just to "check whether the last run went well."

`Future.isDone() == true` can be due to an **error** or **cancellation**, so you should check `isCancelled()` and the cause where appropriate. `isDone() == false` is not enough to guarantee the task is healthy: the schedule might not have reached its next run yet, might be running long, might be experiencing worker starvation, or a dependency might be hung.

## 5. Runnable Java 17+ example: one schedule stops, another continues

The program below creates a scheduler with two workers and two periodic tasks:

- **Task A:** succeeds on the first run, throws `IllegalStateException` out of `Runnable` on the second run. Schedule A stops; `get()` reports `ExecutionException`.
- **Task B:** simulates an error on the first run but **catches and records the error internally**; it completes normally and continues for at least three runs, after which `main` cancels it to end the example.
- **Independent task:** scheduled after A's failure to demonstrate that the scheduler still executes other work.

Create the file `PeriodicTaskFailureDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicTaskFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newScheduledThreadPool(2);
        AtomicInteger failedRuns = new AtomicInteger();
        AtomicInteger resilientRuns = new AtomicInteger();
        AtomicInteger handledErrors = new AtomicInteger();
        CountDownLatch thirdRun = new CountDownLatch(1);
        ScheduledFuture<?> resilient = null;

        try {
            ScheduledFuture<?> failed = scheduler.scheduleAtFixedRate(() -> {
                int n = failedRuns.incrementAndGet();
                if (n == 2) {
                    throw new IllegalStateException("second execution failed");
                }
            }, 0, 20, TimeUnit.MILLISECONDS);

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("FAILED: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("FAILED RUNS: " + failedRuns.get());
            System.out.println("FAILED FUTURE DONE: " + failed.isDone());

            resilient = scheduler.scheduleWithFixedDelay(() -> {
                int n = resilientRuns.incrementAndGet();
                try {
                    if (n == 1) {
                        throw new IllegalArgumentException("recoverable example");
                    }
                } catch (IllegalArgumentException ex) {
                    handledErrors.incrementAndGet();
                } finally {
                    if (n >= 3) {
                        thirdRun.countDown();
                    }
                }
            }, 0, 20, TimeUnit.MILLISECONDS);

            if (!thirdRun.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("resilient task did not run");
            }
            resilient.cancel(false);

            System.out.println("HANDLED ERRORS: " + handledErrors.get());
            System.out.println("RECOVERED AND KEPT RUNNING: "
                    + (resilientRuns.get() >= 3));

            ScheduledFuture<String> independent = scheduler.schedule(
                    () -> "still active", 0, TimeUnit.MILLISECONDS);
            System.out.println("OTHER TASK: "
                    + independent.get(5, TimeUnit.SECONDS));
        } finally {
            if (resilient != null) {
                resilient.cancel(false);
            }
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Scheduler did not terminate in time");
            }
        }
    }
}
```

Commands to run in the directory containing the file, with JDK 17 or later:

```bash
javac -encoding UTF-8 PeriodicTaskFailureDemo.java
java PeriodicTaskFailureDemo
```

Standard output:

```text
FAILED: IllegalStateException
FAILED RUNS: 2
FAILED FUTURE DONE: true
HANDLED ERRORS: 1
RECOVERED AND KEPT RUNNING: true
OTHER TASK: still active
```

Interpreting the output:

1. `failedRuns` is **2** because an exception escaped on the second run; the executor did not schedule a third run.
2. `failed.get(...)` throws `ExecutionException`. The program inspects `getCause()` to see the actual `IllegalStateException`.
3. `failed.isDone()` returns `true` because the schedule **completed due to an error**; this does not mean the task "succeeded."
4. The `resilient` schedule catches `IllegalArgumentException` itself and finishes its first run normally. Subsequent runs continue to execute; `CountDownLatch` helps the example verify reaching three runs without relying on `Thread.sleep()`.
5. `resilient.cancel(false)` prevents future runs from being scheduled. An already-started run might continue since `false` does not request an interrupt, but the program only checks the condition "ran at least three times," so the output does not depend on the exact count at cancellation time.
6. The `independent` task still receives the result `still active`, showing that schedule A's failure **does not by itself shut down the scheduler**.

`AtomicInteger` keeps the counters thread-safe when read from `main` and updated on worker threads. `CountDownLatch` synchronizes the completion condition; `get(timeout)` and `await(timeout)` prevent infinite waiting in the demo. `shutdownNow()` requests stopping and interrupts active workers; it does not guarantee that an uncooperative task will stop immediately. The `finally` block cleans up the scheduler so the program can exit.

The example intentionally uses **20 ms** for quick demonstration, not to treat the scheduler as a millisecond-accurate timer. On a heavily loaded machine, timeouts may expire before tasks run; that is a timeout condition to handle in real applications and does not change the suppression contract when a task throws an error.

## 6. How do escaping errors differ from errors handled inside the task?

The deciding point for whether a schedule continues after a business error is **how `Runnable.run()` returns**:

### Escaping exception

```java
Runnable job = () -> {
    loadData();
    saveData(); // If an uncaught RuntimeException is thrown...
};
scheduler.scheduleAtFixedRate(job, 0, 1, TimeUnit.MINUTES);
```

This is an illustrative snippet assuming `ScheduledExecutorService scheduler` and methods `loadData()`, `saveData()`. If an exception escapes `job.run()`, the periodic task contract requires **suppressing subsequent executions of this schedule**.

### Catching expected errors and finishing the run normally

```java
Runnable job = () -> {
    try {
        refreshCache();
    } catch (RecoverableBackendException ex) {
        recordFailure(ex);
        // This run failed, but the policy allows retrying in the next period.
    }
};
scheduler.scheduleWithFixedDelay(job, 0, 30, TimeUnit.SECONDS);
```

This is also an **illustrative snippet**, with `RecoverableBackendException`, `refreshCache()`, and `recordFailure()` defined by the application. If the `catch` block completes and `run()` returns normally, the schedule **can continue** in the next period. That behavior is an application decision: transient errors may be recorded and skipped for this run, while unrecoverable errors should be reported and may intentionally stop the schedule.

Pay special attention: `recordFailure(ex)` itself can also throw an exception. If logging, metrics, or an error-reporting callback fails and the new exception escapes `run()`, the schedule will still be suppressed. Choose a resilient monitoring path and handle monitoring-path errors according to their criticality.

**Do not wrap the entire task in `catch (Throwable)` and ignore all errors.** `Throwable` includes `Error` such as `OutOfMemoryError`, a condition where there is usually no basis to continue using resources normally. Only catch error types for which the application has a handling policy and can preserve invariants. For `InterruptedException`, follow a dedicated cancellation and interrupt-status policy.

## 7. Does a failed schedule automatically restart?

No. With `scheduleAtFixedRate` and `scheduleWithFixedDelay`, when a run throws an escaping exception, **that schedule's `ScheduledFuture` transitions to an exceptionally terminated state**. The executor does not automatically retry the failed run, nor does it create a new schedule.

If restarting after an error is required, the application must have an explicit strategy:

- Allow certain transient errors to be **caught inside the task**, log/record metrics, and let the next periodic run try again.
- If the schedule needs to adapt based on failure count, use **conditional rescheduling** (one-shot `schedule(...)` that explicitly schedules the next run) with backoff/jitter instead of a rigid period.
- If a task has stopped due to a severe error, transition its state to `FAILED` and require operational action or configuration changes; do not infinitely re-schedule automatically.
- Have monitoring detect futures that are unexpectedly `isDone()`, preventing critical tasks from silently stopping without anyone noticing.

When rescheduling manually, prevent duplicates: only one scheduler/controller should own the schedule, cancel/track the old schedule reference, and avoid having multiple callbacks create new schedules concurrently after an incident. If multiple application instances are running, consider leader election, distributed locks, or appropriate idempotency; `ScheduledExecutorService` itself does not coordinate across different JVMs.

## 8. Checking status and reading the cause via `ScheduledFuture`

The `ScheduledFuture<?>` object is the handle for managing and observing a schedule's lifecycle. Key operations:

| Call | Meaning |
| --- | --- |
| `future.isDone()` | The schedule has completed due to cancellation, error, or another termination form; does not mean success |
| `future.isCancelled()` | The schedule was cancelled |
| `future.cancel(false)` | Requests cancelling unstarted runs; does not request interrupting a currently executing run |
| `future.cancel(true)` | Requests cancellation and **may interrupt** the currently running execution; the task must cooperate |
| `future.get()` | For a healthy periodic schedule, usually **never returns normally**; throws `ExecutionException` on error, `CancellationException` on cancellation |
| `future.get(timeout, unit)` | Bounded wait; `TimeoutException` may simply reflect that the schedule is still active |

Observation pattern *once you know the future has finished*:

```java
if (future.isDone()) {
    if (future.isCancelled()) {
        reportCancelled();
    } else {
        try {
            future.get();
        } catch (ExecutionException ex) {
            reportFailure(ex.getCause());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }
}
```

This is a code snippet inside a method that has `ScheduledFuture<?> future`, appropriate `java.util.concurrent.*` imports, and application-defined `reportCancelled()`, `reportFailure(Throwable)` methods. Protect against races between cancellation state and result retrieval if multiple threads manage the handle. If `get()` is cancelled after the check, it can throw `CancellationException`; the snippet omits that branch for brevity, whereas production code should handle it completely.

Do not call `future.get()` inside **a periodic task execution on that same schedule**, because the future has not completed and it can block waiting on itself indefinitely. If you need to handle per-run errors, record them directly in a wrapper and use a separate monitoring system.

### Does `UncaughtExceptionHandler` see this error?

For tasks run through `ScheduledThreadPoolExecutor`, the executor typically **captures the error into the future**. Therefore, `Thread.UncaughtExceptionHandler` is not a reliable channel to observe all failures of scheduled tasks; the error may not surface as an uncaught exception on the worker thread. The reliable path is managing `ScheduledFuture`, a wrapper that records per-run outcomes, or an application-defined monitoring channel.

If you subclass `ScheduledThreadPoolExecutor` and override `afterExecute(Runnable, Throwable)`, note that the second `Throwable` parameter can be `null` even when the task failed, because the error is stored inside the `Future`. Do not unconditionally call `get()` on periodic futures that are not yet `isDone()`; doing so can block an executor worker.

## 9. Why one task failing does not mean the whole scheduler is broken

`ScheduledExecutorService` manages **multiple independent tasks**. A periodic schedule failing and being suppressed is the state of **that schedule's handle**, not a global `shutdown()` command. For example, with two jobs:

- Job A refreshes exchange rates and hits an uncaught `IllegalStateException`;
- Job B cleans up the cache normally.

As long as the scheduler is still active and resources are available, Job B is still allowed to execute on its schedule. Conversely, do not conclude that the scheduler is completely healthy just because Job B is still running: workers may be saturated, queues may be growing, or Job A may already be dead.

Monitoring should track **each schedule** and **the pool** separately. Useful signals include:

- Most recent run start/end timestamp;
- Last successful run timestamp;
- Consecutive failure count, most recent error type, and correlation ID;
- `ScheduledFuture.isDone()`, `isCancelled()` for schedules expected to run long-term;
- Single-run duration, scheduling lag relative to target time, and worker saturation;
- Number of queued tasks, and the executor's `isShutdown()`/`isTerminated()` state.

Do not mark status as "HEALTHY" solely because the JVM process is alive; a scheduler can remain alive for a long time while every critical periodic job has stopped after an exception.

## 10. Comparison with `java.util.Timer` and `TimerTask`

Legacy Java includes `java.util.Timer`, which operates on a single-thread model running `TimerTask` instances sequentially within one `Timer`. When a `TimerTask.run()` throws an unhandled **unchecked exception**, the `Timer`'s execution thread can terminate; the timer can no longer continue its schedule as before, and other tasks on **the same Timer** are also affected.

This differs significantly from `ScheduledThreadPoolExecutor`:

| Aspect | `java.util.Timer` | `ScheduledExecutorService` with periodic schedules |
| --- | --- | --- |
| Execution threads | Single thread for the Timer's tasks | Pool of one or more workers |
| Unchecked error escaping a task | Can terminate the Timer thread, affecting all tasks on that Timer | Suppresses subsequent runs of **the failed schedule**, does not stop other schedules |
| Channel to retrieve task errors | Does not return a `Future`-style handle per schedule | `ScheduledFuture` can complete exceptionally |
| Long-running task | Blocks other tasks on the same Timer | Pool can run other tasks on other workers, depending on pool size |
| Recommendation for new code | Usually not the preferred choice | Usually more suitable due to pool management, cancellation, and futures |

`Timer` example (code snippet inside a method; imports `java.util.Timer` and `TimerTask`):

```java
Timer timer = new Timer("legacy-timer", true);
timer.scheduleAtFixedRate(new TimerTask() {
    @Override
    public void run() {
        throw new IllegalStateException("legacy timer task failed");
    }
}, 0L, 1000L);
```

This example is **for analyzing consequences**, not a production error-handling pattern. With `Timer`, an uncaught runtime exception in a task can kill the Timer thread and prevent later scheduled tasks from running. If `Timer` is used in legacy code, handle errors, manage its lifecycle, and consider migrating to `ScheduledExecutorService` when appropriate.

In both models, **selectively catching errors** in the task body can help keep subsequent runs scheduled, but it does not guarantee that the actual work completed correctly.

## 11. Checked exceptions, unchecked exceptions, and `Error`

`ScheduledExecutorService` accepts `Runnable` for periodic tasks. `Runnable.run()` **does not declare `throws` for checked exceptions**. Therefore, a method performing I/O that throws a checked `IOException` must handle it inside `run()`:

```java
Runnable job = () -> {
    try {
        refreshFromRemote(); // May throw IOException
    } catch (IOException ex) {
        logTransientFailure(ex);
    }
};
```

This is an illustrative snippet requiring `java.io.IOException` and application methods `refreshFromRemote()`, `logTransientFailure(...)`. If `IOException` is contained in the `catch` block and `run()` completes normally, the schedule can continue. If you intentionally wrap it in `UncheckedIOException` or `IllegalStateException` **and rethrow it**, the schedule will be suppressed just like with any other runtime exception.

`Error` is also a `Throwable`. The Java contract for periodic tasks uses the wording "execution encounters an exception"; `ScheduledThreadPoolExecutor` captures severe execution failures as well. Do not rely on catching every `Throwable` to "keep the job alive" when the JVM may be out of resources or its state is no longer trustworthy.

Separate policies clearly:

- **Recoverable errors:** e.g., a transient network request failure where this run's data can be skipped while keeping a valid old cache. Record it and finish normally if state is preserved.
- **Business/validation errors:** configuration errors, undecodable payloads, violated invariants. Usually you should stop or isolate the job and alert, rather than running repeatedly and corrupting data.
- **Cancellation/interruption errors:** may require stopping the task, releasing resources, and restoring interrupt status. Not every `InterruptedException` is a transient error to ignore.
- **Severe runtime-level errors:** report to monitoring or let the executor/runtime handle them according to operational policy, avoiding masking them with an infinite retry loop.

## 12. `InterruptedException` and schedule cancellation

A periodic task may block on I/O, locks, or `sleep`/`wait` calls. When the worker thread is interrupted, blocking calls can throw `InterruptedException`. Because `Runnable.run()` cannot declare checked exceptions, the task must decide how to handle it.

A handling snippet inside `Runnable`:

```java
try {
    waitForWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

This is a snippet inside a `void` method, with `waitForWork()` defined by the application. It preserves the interrupt signal so outer code can observe it if appropriate.

**Important pitfall:** if the task only catches `InterruptedException` and **returns normally** while the schedule's `ScheduledFuture` **has not been cancelled**, the periodic schedule may still be scheduled for the next run. `return` only ends **the current run**, not the periodic contract. To cancel the entire schedule, call `future.cancel(...)` or shut down / use an appropriate lifecycle control mechanism.

`cancel(true)` only requests an interrupt if currently running and is *best effort*. Tasks doing I/O that do not respond to interrupts may continue causing side effects. `cancel(false)` does not request interrupting in-progress work. Neither automatically undoes file writes, DB updates, or HTTP requests that have already occurred.

If a task is marked `isCancelled()`, `get()` throws `CancellationException` instead of returning a completion result; cancellation has different semantics from exceptional completion caused by an error in `run()`.

## 13. Periodic tasks with async work inside: another error boundary

Suppose a `Runnable` only **initiates** an asynchronous operation and returns:

```java
scheduler.scheduleAtFixedRate(() -> {
    CompletableFuture<Void> action = service.refreshAsync();
    action.whenComplete((value, error) -> {
        if (error != null) {
            reportFailure(error);
        }
    });
}, 0, 1, TimeUnit.MINUTES);
```

This snippet assumes `ScheduledExecutorService scheduler`, an application `service` returning `CompletableFuture<Void>`, and a `reportFailure(Throwable)` method.

If `refreshAsync()` returns a stage normally and an error occurs **later** while the stage is running, that error **does not escape directly from the `Runnable.run()` execution** that has already returned. Consequently, the outer schedule may **continue running subsequent iterations**, even though the earlier stage failed. If the `whenComplete` callback itself throws an exception, the stage it returns may complete exceptionally; it also does not throw back into the stack of the already-finished `Runnable`.

Another risk is **asynchronous overlap**: the executor guarantees no overlap between **`Runnable.run()` executions** of the same schedule, but when each run merely dispatches a future and returns, the **async work started by those runs** can still overlap elsewhere in the system.

To handle this, choose an explicit contract:

1. Enforce a concurrency/in-flight limit, such as a semaphore or state flag, and ensure it is released on all completion paths.
2. Schedule the next run **after the previous stage completes** if you truly want zero overlap.
3. Track each future, recording errors, status, and cancellation requests.
4. If you must wait via `join()`/`get()` inside `Runnable`, recognize that waiting can block a worker, produce wrapper exceptions, and requires proper timeouts/cancellation.

Similarly, an exception occurring in a callback on another thread does not propagate to a `catch` around the caller's `scheduleAtFixedRate` call. Results must be propagated through the future or a designed observability channel.

## 14. One-shot tasks vs. periodic tasks

`scheduler.schedule(Runnable, delay, unit)` or `schedule(Callable, delay, unit)` creates a **one-shot** task. If the task fails, its future completes exceptionally, but there is no "next execution of the same schedule" to suppress. The caller can call `get()` to retrieve the result or exception.

By contrast, `scheduleAtFixedRate` and `scheduleWithFixedDelay` define a recurring sequence; when an exception escapes, **that sequence ends**. Do not confuse manually calling `schedule(...)` repeatedly from a callback with the contract of the two periodic APIs: a self-rescheduling system must manage errors, cancellation, and duplicate schedules with its own logic.

Similarly, `executor.execute(Runnable)` does not return a future, whereas `executor.submit(...)` returns a `Future`. How the executor records exceptions can differ between the two APIs. When analyzing an existing system, first identify the exact **method used**, rather than applying one blanket answer to "all background thread errors."

## 15. After an exception, is updated data rolled back?

No. Suppression only stops **future scheduled runs**. It does not automatically undo changes made during the failed run.

Example snippet:

```java
Runnable job = () -> {
    updateDatabase();       // May have already committed
    sendNotification();     // May fail after the update
};
```

This illustrates application methods `updateDatabase()` and `sendNotification()`. If the DB operation has already committed and `sendNotification()` throws an exception, the periodic schedule may be suppressed, **but the committed DB data remains**. When operations retry, a record may already have been processed or a notification may already have been sent without an ACK.

For jobs with side effects:

- Use properly scoped transactions for changes within the same resource.
- Distinguish pre-commit failures, post-commit failures, and indeterminate outcomes on timeouts.
- Use idempotency keys / correlation IDs to avoid duplicate processing during retries or rescheduling.
- For DB and messaging, consider the outbox pattern if business logic requires recording the intent to emit an event in the same transaction.
- Use progress state, checkpoints, or business reconciliation if a job processes multiple records.

"Catching errors so the schedule continues" is a choice about **scheduling**, not a guarantee that business state is safe. If invariants have been broken, continuing in the next period can make the corruption worse.

## 16. Designing a policy-driven error-handling wrapper

A sound wrapper should separate errors that allow continuing from errors that require stopping:

```java
Runnable guarded = () -> {
    long started = System.nanoTime();
    try {
        performOneSafeIteration();
        recordSuccess(System.nanoTime() - started);
    } catch (TransientDependencyException ex) {
        recordRecoverableFailure(ex);
        // Normal return: the schedule is allowed to run the next execution.
    } catch (IllegalStateException ex) {
        recordFatalFailure(ex);
        throw ex; // Intentionally stop subsequent executions of this schedule.
    }
};
```

This is a **design snippet**; `TransientDependencyException`, `performOneSafeIteration()`, and the `record...` methods must be defined by the application. Exception classification and the stop/continue decision should be based on the specific job's contract.

The metric/log recording path must also be sufficiently reliable. If `recordFailure` throws an exception, it can alter the continuation decision. In applications requiring high observability, consider an independent error-reporting channel, attaching logging errors as suppressed, or persisting failure state durably. However, do not write an unbounded `catch` that blindly ignores unknown errors just to maintain an artificial run rate.

### Retry within the same run or wait for the next period?

There are two valid approaches, and they are not equivalent:

- **Wait for the next period:** when the error is likely transient and immediate recovery is not needed, record the failed run and return normally. The next run will retry on the existing `fixedRate` or `fixedDelay` schedule.
- **Retry within the current run:** perform bounded retries with timeout/backoff, then decide success or failure. If a run takes too long, a fixed-rate schedule may fall behind; a fixed-delay schedule also shifts according to when the run finishes.

Do not stack multiple retry loops across client, service, and scheduler without an overall bound. A temporarily unavailable dependency can cause a *retry storm* if all instances wake up at the same time; jitter and circuit breakers may be appropriate for larger-scale systems.

## 17. Observing and alerting when a job silently stops running

A common incident is a job stopping after an exception while the application still returns HTTP 200 and the JVM remains alive. You can build a dedicated watchdog using metrics updated on each run:

- `lastStartedAt`: most recent start time;
- `lastCompletedAt` and `lastSuccessAt`: most recent completion/success time;
- `consecutiveFailures`: number of consecutive failures;
- `lastErrorType`, `lastErrorSummary`: error type and context without secrets;
- `ScheduledFuture` state: **active**, **cancelled**, **completed exceptionally**;
- Expected deadline for the next run, plus an appropriate tolerance and scheduler health.

If `future.isDone()` is true for a schedule **expected to still be running**, raise an alert and determine the root cause rather than blindly creating a new schedule. If `future.get(timeout)` throws `TimeoutException`, remember that a healthy periodic future is also not done yet, so a `get()` timeout alone is not enough to conclude the job is hung.

Avoid monitoring solely via stack trace logs, because a task may fail with its exception captured in the future, and a task that catches errors itself may print nothing. The monitoring path should be an explicit part of the job's contract.

## 18. Scheduler lifecycle: shutdown, cancel, and impact on schedules

A scheduler can stop future runs for reasons **other than an error inside the task**:

- `future.cancel(...)` cancels a specific schedule.
- `scheduler.shutdown()` stops accepting new tasks, and by default with `ScheduledThreadPoolExecutor`, existing periodic tasks do not continue after shutdown (this policy can be changed via `setContinueExistingPeriodicTasksAfterShutdownPolicy` on the implementation class).
- `shutdownNow()` requests stopping as soon as possible, returns unstarted tasks, and may interrupt running workers; it does not guarantee that all side effects stop instantaneously.
- A task is delayed due to pool saturation or a hung dependency, even though the future is not yet `isDone()`.
- The JVM or process stops; in-memory schedules are not automatically persisted and restored after a restart.

To diagnose "why isn't the job running," distinguish **exception suppression**, **cancellation**, **executor shutdown**, **overload/scheduling delay**, **stuck work**, and **process restart**. Looking at a single Boolean is not enough.

In production code using `ScheduledThreadPoolExecutor`, consider `setRemoveOnCancelPolicy(true)` so cancelled tasks are removed from the queue sooner; this API is an option on the implementation class, not a method on the `ScheduledExecutorService` interface. Do not treat that setting as handling tasks that **completed exceptionally**, which is distinct from cancellation.

## 19. Testing stopping and continuing accurately

When writing tests, beyond checking the exception type, verify the execution count **before and after the error**. Key test cases:

| Scenario | Verification |
| --- | --- |
| `scheduleAtFixedRate` fails on second run | `ScheduledFuture.get(timeout)` throws `ExecutionException` with expected `cause`; counter stops incrementing afterward |
| `scheduleWithFixedDelay` fails on first run | Schedule stops; subsequent runs do not execute |
| Task catches transient error | After one failed run, subsequent runs continue; metrics record the failure |
| Exception escapes from logging/callback | Schedule can also stop; observer receives the appropriate error |
| One schedule fails, independent schedule is healthy | Independent schedule continues running while scheduler is active |
| `Future` is cancelled | `isCancelled()` is true; not confused with execution error |
| Executor is shut down | Do not confuse shutdown policy with exception suppression |
| A run takes longer than `period` | No two runs of **the same schedule** execute concurrently |
| Async stage fails after `Runnable` returns | Outer schedule can continue; stage error must be collected separately |
| Retrying a task with side effects | Does not produce duplicate DB writes, messages, or payment requests |

Use `CountDownLatch`, `AtomicInteger`, and generous timeouts to test the required events. Do not use `Thread.sleep()` as sole proof that "three runs definitely happened"; scheduler timing depends on system load. When verifying suppression, `future.get(timeout)` returning via exception confirms the schedule has ended; afterward you can check the counter. Avoid leaving test tasks running forever or leaking executors after failed assertions: always clean up in `finally`.

If using scheduling systems outside Java SE such as Quartz, Spring `@Scheduled`, or an application scheduler, read that framework's contract and configure its error handler accordingly. Do not generalize `ScheduledExecutorService`'s suppression rule to every framework: some frameworks catch errors, log them, and continue future runs according to their own policies.

## 20. Pre-deployment checklist for periodic tasks

1. **Choose the right schedule type:** fixed-rate if you need cadence anchored to target timestamps, fixed-delay if you want a wait after each completion; understand that the same periodic task does not overlap at the `Runnable` level.
2. **Classify errors:** which transient errors should be caught to continue, and which severe errors must escape to stop the schedule?
3. **Observe outcomes:** retain `ScheduledFuture` and record status/errors; do not rely solely on `UncaughtExceptionHandler` or default logs.
4. **Do not block indefinitely on `get()`:** an active periodic future normally has no terminal result; use timeouts and appropriate monitoring mechanisms.
5. **Manage lifecycle:** cancel, shutdown, interrupt, and cleanup per policy; note that cancel does not undo prior side effects.
6. **Preserve data integrity:** transactions, idempotency, checkpoints, and checking indeterminate outcomes before retrying.
7. **Check async jobs:** if `Runnable` only initiates a future, handle that future's errors and overlap separately.
8. **Monitor per job:** last success time, consecutive failures, future state, and scheduler health.
9. **Test both behaviors:** an escaping exception **stops** subsequent runs; a properly handled exception **allows continuing**.
10. **Verify the right library:** `Timer`, `ScheduledThreadPoolExecutor`, Spring/Quartz, or other schedulers have different contracts and error policies.

**Rule to remember:** with `scheduleAtFixedRate` and `scheduleWithFixedDelay`, **an exception escaping a run can terminate all future executions of that schedule**. Catching errors internally allows continuing when truly safe; observing `ScheduledFuture` and business state helps prevent silent failures. Scheduling, data state, and recoverability must be designed together.

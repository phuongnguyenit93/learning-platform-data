# Exceptions in Periodic Tasks and Their Impact on Subsequent Runs (Java ScheduledExecutorService)

> **Scope:** **Future & Scheduling** in Java SE 17+, specifically how `ScheduledExecutorService.scheduleAtFixedRate()` and `scheduleWithFixedDelay()` handle exceptions thrown from a single execution and their impact on the entire sequence of subsequent runs. This lesson applies to **general Java concurrency**; Spring-specific scheduler APIs, job annotations, or lifecycles are covered in another chapter.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **one-shot tasks** from **periodic tasks**, and distinguish `scheduleAtFixedRate()` from `scheduleWithFixedDelay()`.
- Accurately analyze the API rule: **an execution of a periodic task throwing an unhandled exception → subsequent executions of that same task are suppressed**.
- Know how to observe a periodic task stopped by an error via `ScheduledFuture.isDone()` and `get()`, without mistakenly assuming that `get()` on an active periodic task will return a normal result.
- Distinguish `ExecutionException`, `CancellationException`, `TimeoutException`, `InterruptedException`, and `RejectedExecutionException`.
- Explain why `ScheduledThreadPoolExecutor.afterExecute(Runnable, Throwable)` typically receives `Throwable == null` **even when the scheduled command fails**.
- Decide when to **catch and handle exceptions within each run** to allow subsequent runs, when to **let an error escape to stop the schedule**, and when manual alerting/restarting is needed.
- Build a runnable Java 17 program verified using `Future.get(timeout)` and `CountDownLatch` rather than guessing thread ordering with `Thread.sleep()`.
- Analyze retries, backoff, shutdown, idempotency, memory visibility, overlap, metrics, and pitfalls that cause a periodic task to stop silently.

**The most important rule:** `scheduleAtFixedRate` / `scheduleWithFixedDelay` do not default to "retrying on the next cycle" when `Runnable.run()` throws an exception. On a periodic scheduled task sequence, an exception **escaping a run** is an abnormal termination event; subsequent executions of the **same ScheduledFuture** are suppressed.

## 2. Why Is This an Easily Overlooked Operational Bug?

A task that updates in-memory data or syncs a cache every 10 seconds can run fine for hours. Once, it receives invalid input and throws a `RuntimeException`:

```java
scheduler.scheduleAtFixedRate(() -> {
    refreshCache(); // May throw RuntimeException.
}, 0, 10, TimeUnit.SECONDS);
```

This is an **illustrative code snippet** placed inside a method; it requires `scheduler` as a `ScheduledExecutorService`, `refreshCache()` to be defined, and `java.util.concurrent.TimeUnit` to be imported.

If `refreshCache()` throws an exception out of `Runnable`, many people expect that "after 10 seconds it will automatically run again." With standard `ScheduledExecutorService`, **the opposite is true**: that periodic task **will no longer run in subsequent cycles**. Other tasks in the same scheduler can still run normally, because the error state usually belongs to **this specific ScheduledFuture**, not meaning the entire thread pool has died.

The consequences can be severe:

- Cache data becomes stale, while the application still responds to HTTP requests.
- A daily reconciliation job stops running, while the process health check remains green.
- Monitoring only tracks whether the JVM is alive/dead without tracking the "last successful run," so it fails to detect that the task has stopped.
- A one-time error log is missed, or the exception is held inside the Future where no one checks it.

Therefore, you must design an **error policy + completion monitoring** for each periodic task, rather than relying on the scheduler to restart automatically.

## 3. Reviewing ScheduledExecutorService

`ScheduledExecutorService` extends `ExecutorService` and provides methods to run tasks once after a delay or periodically:

| API | Purpose | Execution Count | Return Value |
|---|---|---|---|
| `schedule(Runnable, delay, unit)` | Execute a Runnable after a delay | Once | `ScheduledFuture<?>` |
| `schedule(Callable<V>, delay, unit)` | Execute a Callable returning a result after a delay | Once | `ScheduledFuture<V>` |
| `scheduleAtFixedRate(Runnable, initialDelay, period, unit)` | Repeat based on periodic **start times** | Multiple times, until stopped | `ScheduledFuture<?>` |
| `scheduleWithFixedDelay(Runnable, initialDelay, delay, unit)` | Repeat based on **delay after the previous run finishes** | Multiple times, until stopped | `ScheduledFuture<?>` |

`ScheduledFuture` extends `Delayed` and `Future`; you can use `cancel()`, `isDone()`, `isCancelled()`, and `get()` according to the semantics of each task type.

### Example of creating a scheduler

```java
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);
```

This is a code snippet inside a method, importing `java.util.concurrent.Executors` and `ScheduledExecutorService`. The call creates a scheduled executor with **2 core threads**; it does not mean that a single periodic task will run **two concurrent instances**.

**Important API note:** for both periodic methods, `period` and `delay` must be greater than 0; `initialDelay` can be 0. This scheduler is not a cron/calendar scheduler: it computes relative delays and does not promise absolute wall-clock times or timezone-based schedules.

## 4. Fixed Rate vs. Fixed Delay: How Do They Differ?

### `scheduleAtFixedRate()`

Syntax:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        task, initialDelay, period, TimeUnit.MILLISECONDS);
```

This is illustrative code; `scheduler`, `task`, `initialDelay`, and `period` are already declared in the method.

Start times are **nominally scheduled** at the following points:

```text
t0 + initialDelay
t0 + initialDelay + period
t0 + initialDelay + 2*period
...
```

If one execution takes **longer than period**, subsequent executions may **start late**. The executor does not run two executions of the **same periodic task** concurrently just because it is behind schedule. After a slow execution finishes, the next one may become eligible to run almost immediately without waiting for a full period again.

Example with a 100 ms period, where the first run takes 260 ms:

```text
Nominal marks: 0 ms, 100 ms, 200 ms, 300 ms ...
Actual:        run #1 [0----------------260]
               run #2                      [260--...]
               #3, #4 may continue to lag depending on load and scheduling
```

This diagram is illustrative, not a guarantee of absolute start times. "Fixed rate" does not mean the scheduler abandons the running job and spawns a parallel execution at each tick.

### `scheduleWithFixedDelay()`

Syntax:

```java
ScheduledFuture<?> future = scheduler.scheduleWithFixedDelay(
        task, initialDelay, delay, TimeUnit.MILLISECONDS);
```

This is illustrative code with the corresponding variables already declared.

The next execution becomes eligible to run **after the previous one finishes + delay**. If the task takes 260 ms and the delay is 100 ms:

```text
run #1:      [0----------------260]
delay:                            [260----360]
run #2:                                        [360--...]
```

The difference is the **rest interval after completion**, rather than catching up to fixed-rate ticks.

### Quick comparison

| Property | Fixed rate | Fixed delay |
|---|---|---|
| Next start based on | Theoretical periodic marks | Completion time of the previous run |
| When task is slower than period/delay | Subsequent runs may start late and run back-to-back | Still waits the requested delay after completion |
| Do two runs of the **same periodic task** overlap? | No, per `ScheduledThreadPoolExecutor` contract | No, per contract |
| One run throws an exception escaping `run()` | **Suppresses subsequent runs** | **Suppresses subsequent runs** |
| `ScheduledFuture.get()` during normal periodic execution | Does not return normally | Does not return normally |

The choice depends on semantics: "at every interval from the schedule" vs. "wait N units after the previous run." **The exception rule is the same for both**.

## 5. Official Rule When a Run Throws an Exception

The `ScheduledExecutorService` specification states clearly for both `scheduleAtFixedRate` and `scheduleWithFixedDelay`:

- The sequence of periodic executions continues until the **Future is cancelled**, the executor terminates according to policy, or **an execution of the task throws an exception**.
- When an exception escapes, **subsequent executions are suppressed**.
- `ScheduledFuture.get()` throws `ExecutionException`, whose cause is the task's exception.
- `isDone()` becomes **true** after abnormal termination.
- Periodic `get()` **does not return normally** while the task is repeating. It only exits with an exception due to cancellation/failure or termination conditions defined by the API.

### Reading the state diagram

```text
             SCHEDULED PERIODIC TASK
                        |
                  run #1 / #2 / ...
                   /           \
           run() returns        run() throws
           normally             throwable
               |                    |
       schedule next run      Future completed
       by fixed rate/delay    exceptionally
               |                    |
           keep running       suppress subsequent runs
               |
       until cancel/shutdown
```

The deciding point is **whether the exception escapes `Runnable.run()`**. If the code catches the error itself and `run()` returns normally, the scheduler has grounds to continue scheduling; whether the actual business operation succeeded or not is something you must evaluate separately.

### Not every error stops the entire scheduler

A `ScheduledThreadPoolExecutor` can hold multiple independent periodic tasks. One failing task usually only stops **that task's** sequence; other tasks can keep running. Do not assume "the pool is still alive, so periodic job A must still be running."

**Do not rely on the application still responding to requests as proof that all jobs are running.** Track the heartbeat of each critical task.

## 6. What Exceptions Can Runnable Throw?

`Runnable.run()` does not declare `throws Exception`, but it can throw **unchecked exceptions**:

```java
Runnable task = () -> {
    throw new IllegalStateException("unexpected state");
};
```

This is a standalone code snippet inside a method. `IllegalStateException` is a `RuntimeException`, so it does not require `throws`.

If an operation has a checked exception like `IOException`, the `Runnable` lambda must **catch it or wrap it into an unchecked exception**:

```java
Runnable task = () -> {
    try {
        readFile();
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
};
```

This is illustrative code; it requires importing `java.io.IOException` and `UncheckedIOException`, and `readFile()` must be defined.

When you wrap it with `UncheckedIOException` and let it escape `run()`, the periodic sequence **is also suppressed**. `Future.get()` receives an `ExecutionException` whose cause is `UncheckedIOException`; to inspect the original I/O cause, traverse further via `getCause()` on that wrapper.

`Error` is also a `Throwable` and can cause a periodic task to terminate abnormally. **You should not catch all `Throwable`s to keep running under all circumstances**, especially severe runtime errors like `OutOfMemoryError`. A recovery policy must be based on expected errors that can be safely handled.

## 7. Standalone Java 17 Example: Stopping, Detecting, and Recovering

The following program tests three scenarios:

1. `scheduleAtFixedRate`: the first run throws `IllegalStateException`, the Future holds the error, and the task runs only **once**.
2. `scheduleWithFixedDelay`: the first run throws `IllegalArgumentException`, and subsequent runs are also suppressed.
3. Another fixed-rate task **catches the expected error inside the Runnable itself**, records the failure, and returns normally; subsequent runs continue to execute. `CountDownLatch` confirms at least three runs, after which `main` explicitly calls `cancel(false)`.

Create the file **`PeriodicFailureDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
        try {
            AtomicInteger fixedRateRuns = new AtomicInteger();
            ScheduledFuture<?> failedRate = scheduler.scheduleAtFixedRate(() -> {
                fixedRateRuns.incrementAndGet();
                throw new IllegalStateException("failed rate task");
            }, 0, 10, TimeUnit.MILLISECONDS);

            try {
                failedRate.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                System.out.println("rateCause=" + e.getCause().getClass().getSimpleName());
            }
            System.out.println("rateRuns=" + fixedRateRuns.get());
            System.out.println("rateFutureDone=" + failedRate.isDone());

            AtomicInteger fixedDelayRuns = new AtomicInteger();
            ScheduledFuture<?> failedDelay = scheduler.scheduleWithFixedDelay(() -> {
                fixedDelayRuns.incrementAndGet();
                throw new IllegalArgumentException("failed delay task");
            }, 0, 10, TimeUnit.MILLISECONDS);
            try {
                failedDelay.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                System.out.println("delayCause=" + e.getCause().getClass().getSimpleName());
            }
            System.out.println("delayRuns=" + fixedDelayRuns.get());

            AtomicInteger handledFailures = new AtomicInteger();
            AtomicInteger recoveredRuns = new AtomicInteger();
            CountDownLatch threeRuns = new CountDownLatch(3);
            ScheduledFuture<?> recovered = scheduler.scheduleAtFixedRate(() -> {
                int round = recoveredRuns.incrementAndGet();
                try {
                    if (round == 1) {
                        throw new IllegalStateException("transient");
                    }
                } catch (RuntimeException e) {
                    handledFailures.incrementAndGet();
                } finally {
                    threeRuns.countDown();
                }
            }, 0, 10, TimeUnit.MILLISECONDS);

            if (!threeRuns.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("recovery runs timed out");
            }
            recovered.cancel(false);
            System.out.println("recoveredAtLeastThree=" + (recoveredRuns.get() >= 3));
            System.out.println("handledFailures=" + handledFailures.get());
            System.out.println("recoveredCancelled=" + recovered.isCancelled());
        } finally {
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("scheduler did not terminate");
            }
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 PeriodicFailureDemo.java
java PeriodicFailureDemo
```

**Compiled and verified stdout:**

```text
rateCause=IllegalStateException
rateRuns=1
rateFutureDone=true
delayCause=IllegalArgumentException
delayRuns=1
recoveredAtLeastThree=true
handledFailures=1
recoveredCancelled=true
```

### Analysis of the failing fixed-rate part

- `fixedRateRuns.incrementAndGet()` executes before `throw`.
- The first run throws `IllegalStateException` out of `Runnable.run()`.
- The `ScheduledFuture` of this sequence transitions to **completed exceptionally**; subsequent executions are suppressed, so there is no run #2.
- `failedRate.get(3, SECONDS)` throws `ExecutionException` because the periodic task failed, and `getCause()` is `IllegalStateException`.
- Once `get` throws the exception, the failure has been recorded; `fixedRateRuns.get() == 1` is a deterministic conclusion without needing `sleep` to "wait and see if it runs again."
- `failedRate.isDone()` is true: it completed **abnormally**, not "succeeded."

### Analysis of the failing fixed-delay part

- The first run of `failedDelay` increments the counter and throws `IllegalArgumentException`.
- `scheduleWithFixedDelay` has the **same suppression rule** when an exception escapes the Runnable. `delayRuns=1`.
- `failedDelay.get()` throws `ExecutionException` with the corresponding cause.

### Analysis of continuing after a handled error

- The first run of `recovered` intentionally throws `IllegalStateException`, but `catch (RuntimeException e)` handles the error inside the Runnable.
- `run()` **returns normally**, so the scheduler continues scheduling subsequent runs at the fixed rate.
- `threeRuns` is counted down in `finally` on every run, including the run where an error occurred and was caught.
- `main` uses `threeRuns.await(3, SECONDS)` to know the task entered at least three rounds. There is no need to hope the scheduler happens to run exactly three rounds before `main` proceeds; hence the output uses `recoveredAtLeastThree=true` instead of printing an exact count that could vary due to scheduling.
- `recovered.cancel(false)` cancels future runs; if a run is currently executing, `false` does not request interrupting that active execution. `isCancelled()` is true after cancellation succeeds in this demo's execution path.
- `finally` calls `shutdownNow()` and `awaitTermination` so no scheduler worker remains alive after `main` finishes; in long-running applications, use an appropriate shutdown policy instead of always calling `shutdownNow`.

**Sample limitations:** this is a demo, not a simulation of real network/database retries, and it does not encourage catching every `RuntimeException` and continuing regardless of invariants. If an error leaves state unsafe, stop and alert. The three periodic sequences are independent tasks in the same pool; a failure in one sequence is not automatically a failure of the entire pool.

## 8. Why Shouldn't You Just Wait for a Period and Check a Counter?

A flawed test often uses:

```java
// Illustrates a flaky testing approach, NOT valid proof.
scheduler.scheduleAtFixedRate(task, 0, 100, TimeUnit.MILLISECONDS);
Thread.sleep(500);
System.out.println(runs.get());
```

This is an illustrative snippet with `scheduler`, `task`, and `runs` already declared. `Thread.sleep(500)` does not guarantee that the scheduler gets CPU time on schedule, that the task doesn't block, or that the system doesn't pause for GC. The counter after a duration can depend on the scheduler.

Instead:

- For **terminal failure**, use `ScheduledFuture.get(timeout, unit)` and inspect `ExecutionException.getCause()`.
- For **progress**, use `CountDownLatch`/`Phaser`/atomic counters paired with explicit completion events.
- For **termination after cancel**, use `Future.isCancelled()`/an appropriate termination protocol; cancelling a Future does not always guarantee the action has stopped if it is currently running and `cancel(false)` was used.
- For **non-occurrence of run #2**, reason from the API's **suppression contract** and the Future's exceptionally completed state; if additional runtime proof is needed, check the count after failure completion or use instrumentation.

Deadline-bound tests should **fail in a controlled manner** when the environment stalls; avoid hanging tests forever on an untimed `get()`.

## 9. What Happens to ScheduledFuture?

The `ScheduledFuture<?>` returned for a periodic schedule is a handle for the **entire repeating sequence**, not a separate Future for each run.

### While the task is still repeating normally

- `isDone()` is typically **false** while the sequence is active.
- `get()` **does not return a normal value just because one iteration has completed**.
- `get(timeout, unit)` can throw `TimeoutException` if the schedule is still active and has not been cancelled/failed within the wait time.
- Do not call `get()` right after `scheduleAtFixedRate(...)` to "wait for the first iteration": it can block **forever** if the task keeps running.

### When an iteration throws an escaping exception

- `isDone() == true` after abnormal completion.
- `get()` throws `ExecutionException` with the cause being the original throwable from the failing iteration.
- The sequence has no further runs; a new schedule action is required if you want to continue.

### When the caller cancels the schedule

- If `cancel(...)` succeeds, `isCancelled() == true` and `isDone() == true`.
- `get()` throws `CancellationException` (unchecked), **not `ExecutionException`** from the business task.
- `cancel(true)` requests interrupting the currently running task per Future semantics; it **does not guarantee the task stops immediately** if the code ignores interrupts or is in uninterruptible I/O.
- `cancel(false)` does not request interrupting the currently running task; a cancelled Future state does not by itself prove all side effects have stopped immediately.

### Distinguishing exceptions from get()

| Exception | When typically encountered | Meaning |
|---|---|---|
| `ExecutionException` | An iteration throws an escaping Throwable | Sequence terminated abnormally; `getCause()` is the original error |
| `CancellationException` | The Future was cancelled | Sequence was cancelled; not a business failure by default |
| `TimeoutException` | `get(timeout)` did not observe termination within the deadline | Schedule may still be running; **a get timeout does not cancel it** |
| `InterruptedException` | The thread calling `get` was interrupted while waiting | Caller was requested to stop; propagate/restore the flag per contract |

**Do not treat `isDone()` as a sign of success.** For a periodic task, done is usually a critical signal of **cancelled or failed**, not "the most recent iteration succeeded."

## 10. Why Might the Exception Not Appear in afterExecute(Throwable)?

A subtle detail of `ScheduledThreadPoolExecutor`: the implementation uses `ScheduledFuture` instances to manage work. The Javadoc for this class explicitly states: **`afterExecute` always receives a null second `Throwable` parameter**, even when the scheduled command terminates abnormally. To inspect the throwable, read the outcome via `Future.get()`.

Example of an insufficient monitor:

```java
@Override
protected void afterExecute(Runnable task, Throwable error) {
    super.afterExecute(task, error);
    if (error != null) {
        report(error);
    }
}
```

This is an illustrative method of a `ScheduledThreadPoolExecutor` subclass; `report(Throwable)` is application-defined. Checking `error != null` like this can **completely miss errors from scheduled tasks**, because the wrapper stores the error inside the Future.

**Another caveat:** `afterExecute` is called after **each iteration** of a periodic task, yet while the task continues repeating, `ScheduledFuture.isDone()` remains **false**. If the hook unconditionally calls `future.get()` for an active periodic task, the worker can **block indefinitely right inside `afterExecute`** and never run subsequent iterations!

A safer pattern:

```java
@Override
protected void afterExecute(Runnable task, Throwable error) {
    try {
        if (task instanceof Future<?> future && future.isDone()) {
            try {
                future.get();  // Only read the outcome when the Future is done.
            } catch (ExecutionException e) {
                reportFailure(e.getCause());
            } catch (CancellationException e) {
                recordCancellation();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    } finally {
        super.afterExecute(task, error);
    }
}
```

This is an **illustrative method** inside a subclass, with `reportFailure` and `recordCancellation` provided externally and `Future`, `ExecutionException`, `CancellationException` imported. In real code, these telemetry methods must be **fast, non-blocking, and exception-safe**, because the hook runs on the worker thread. `future.isDone()` prevents `get()` from blocking while the periodic Future is still active.

### Difference from a regular ThreadPoolExecutor

`ThreadPoolExecutor.afterExecute`, when given a direct `Runnable` via `execute`, can observe a `Throwable` escaping `run()`. With `ScheduledThreadPoolExecutor`, however, **even `execute()` is wrapped into a scheduled future**. Therefore, do not copy the "`t != null` means error" pattern from a regular thread pool to a scheduled pool without checking the wrapper semantics.

### Hook exceptions are not business task exceptions

If `beforeExecute` or `afterExecute` itself throws an exception, the worker hook/lifecycle behavior can differ from a scheduled task's `run()` throwing an exception. Do not use hooks to hold business logic or operations that might throw unmanaged errors. Such errors can affect the worker/monitoring and make root-cause analysis difficult.

## 11. Option A: Catch and Handle Expected Errors So the Schedule Continues

If the business requirement is "the task must continue on the next cycle even if this run encounters a **recoverable** error," handle the error **inside `Runnable`** before it escapes.

```java
Runnable refresh = () -> {
    try {
        refreshFromRemote();
        markSuccess();
    } catch (TransientNetworkException e) {
        recordFailure(e);
        // run() returns normally; the scheduler can run the next cycle.
    }
};
```

This is **illustrative code**, not a standalone program: `TransientNetworkException` and the remaining methods are application-defined. Catch only specific exceptions, allowing a **retry on the next cycle** when that failure mode is determined to be safe.

**Do not turn an exception into a "success."** Even though `run()` returns normally so the scheduler continues, you must log/record an **iteration failed** metric and not increment the success counter. `ScheduledFuture` cannot tell you that an individual iteration failed if it was caught and your own code does not report the outcome.

### Failure classification pattern

An example policy:

- **Transient/retryable:** temporary timeouts, upstream returning overloaded status, brief connectivity issues. Can be recorded, skipped this round, and retried on the next cycle if the operation is idempotent or does not leave partial state.
- **Permanent/data validation:** invalid data, violated preconditions. Can quarantine bad data and continue with valid data; or stop the schedule if the error indicates a broken invariant.
- **Programming/invariant failure:** unexpected `NullPointerException`, `IllegalStateException` signaling seriously corrupted state. Usually should fail fast and alert rather than catching and continuing indefinitely.
- **JVM/runtime fatal:** `OutOfMemoryError` and other severe errors. Do not blindly catch `Throwable` to "keep the schedule alive."

Place **cleanup operations** in an appropriate `finally` block to release per-iteration resources:

```java
Runnable task = () -> {
    Resource resource = openResource();
    try {
        performWork(resource);
    } finally {
        resource.close();
    }
};
```

This is an **illustrative snippet**, with `Resource`, `openResource`, and `performWork` application-defined. For `AutoCloseable`, use try-with-resources when appropriate. If cleanup also throws an unchecked exception that escapes the Runnable, **it can stop the entire periodic task**, even if the main logic just succeeded.

## 12. Option B: Let Errors Escape When Stopping Is Needed to Prevent Data Corruption

Not every periodic schedule should continue after a failure. For example, a job that processes a batch and updates shared dependent state:

- An exception occurs after 50% of the data has been updated.
- The next run does not know which batch it is on, and continuing could write duplicates or drop items.
- Silently continuing just to "keep the scheduler alive" can cause larger corruption.

In that situation, letting the exception escape `Runnable` to trigger **suppression** is the right choice, provided there is **alerting and a recovery workflow**:

```java
Runnable criticalJob = () -> {
    validateInvariant();   // If invalid, throw.
    commitOneBatch();      // If it fails, throw to stop the schedule.
};
```

This is an illustrative snippet with application-defined methods.

Key requirements:

1. The error is clearly reported via `ScheduledFuture.get()`/monitoring, not left unnoticed.
2. The pipeline determines whether the final data state was committed.
3. Operators or a controller have a reset/recovery protocol.
4. During recovery, do not unconditionally call a new `scheduleAtFixedRate` if an old instance might still be running or still have side effects.
5. Retries/restarts must be **idempotent** or have the necessary transactional semantics.

**Suppression is a scheduler behavior, not a business transaction/rollback.** Side effects that occurred before the exception are not automatically undone by the JVM.

## 13. Retry Within an Iteration or Retry on the Next Cycle?

There are two different levels:

### Internal retry within a single iteration

An execution can attempt an I/O operation a few times with backoff and timeout, then decide to return or throw. For example:

```java
void runWithLimitedRetries() {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            callIdempotentRemoteApi();
            return;
        } catch (RetryableFailure e) {
            if (attempt == 3) {
                recordPermanentFailure(e);
                return; // or throw to stop the schedule per policy
            }
            backoff(attempt);
        }
    }
}
```

This is an **illustrative method**; `RetryableFailure`, `callIdempotentRemoteApi`, `recordPermanentFailure`, and `backoff` must be defined. If `backoff` uses sleep, it must handle `InterruptedException` properly; the overall deadline must not be exceeded arbitrarily.

When retrying within an iteration:

- Iteration duration can become longer than the period/delay.
- `scheduleAtFixedRate` may start the next run late and run back-to-back immediately after completion to catch up.
- `scheduleWithFixedDelay` still waits the full delay after the iteration finishes.
- Excessive retries can tie up a worker, increase downstream load, and delay other tasks.
- A failure after max attempts must be recorded, with an explicit decision to **return to continue next time** or **throw to suppress**.

### Letting the next cycle act as the retry

If skipping the current cycle does not break invariants, catch the transient error, log, and return. The scheduler will schedule the next run; this is a **periodic** retry, not an immediate retry. Ensure the next run's input is sufficient to process the failed run's data, without silently losing work items that require acknowledgment.

### Retry does not mean exactly-once

If a job calls an external API outside the JVM and times out **after the receiver has committed**, retrying can duplicate side effects. Use idempotency keys, transaction/outbox patterns, checkpoints, and business reconciliation as required. `ScheduledExecutorService` does not guarantee exactly-once external side effects.

## 14. Exceptions, Interrupts, and Cancellation Must Be Clearly Categorized

### `InterruptedException`

A `Runnable` cannot declare checked `InterruptedException`, so when calling interruptible APIs it must handle it itself:

```java
Runnable worker = () -> {
    try {
        waitForWork();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Stop work or signal cancellation; do not continue looping indefinitely.
    }
};
```

This is illustrative code, with `waitForWork()` already defined. When an interrupt signals shutdown/cancel, **do not swallow it** and treat it as a normal retryable failure. In a scheduled task, if code swallows the interrupt and returns normally while the Future is not cancelled, the scheduler may still reschedule per policy; the shutdown path must be explicitly defined.

If an iteration is cancelled via `cancel(true)`:

- Cancellation marks the Future as cancelled per the API.
- An interrupt is usually a **request** to stop; the code must cooperate.
- A cancelled Future is not proof that external side effects were rolled back or that the iteration has completely stopped.

### `RejectedExecutionException`

This error can occur when you try to schedule a new task after shutdown, or when the executor cannot accept the task per its policy. It occurs at **submission/admission**, not as an exception thrown inside a scheduler-executed iteration. Track rejections separately.

### `TimeoutException` from Future.get

A call:

```java
future.get(2, TimeUnit.SECONDS);
```

This is an illustrative snippet, where `future` is a `Future`. The `get` timeout indicates that **the caller did not observe completion within that time**. For an active periodic task, this can be completely normal behavior. `get(timeout)` does not cancel the schedule.

### `Error`

An `Error` is not caught by `catch(Exception)`. An `Error` thrown out of an iteration also causes the periodic sequence to be suppressed per `ScheduledExecutorService` behavior. Do not unconditionally catch `Throwable` just to protect the schedule; errors can indicate that the JVM or resources are no longer in a trustworthy state.

## 15. A Periodic Task Does Not Overlap With Itself

With `ScheduledThreadPoolExecutor`, successive executions of the **same periodic task** do not run concurrently, even if one iteration takes longer than the period; subsequent runs may start late.

This is important when reading logs:

```text
rate 100ms, iteration 1 takes 350ms

Task A: [run1------------------------------]
                                                [run2---]
Task B:    [runB]          [runB]
```

The diagram shows two independent schedules A and B; **B can run while A is running** if the pool has available resources. No overlap **between iterations of A** does not mean A cannot run concurrently with other schedules.

The `ScheduledThreadPoolExecutor` Javadoc also provides a **happens-before relationship between the effects of successive executions of the same periodic task**, even when each run executes on a different worker thread. However:

- Do not infer that **different** periodic tasks are serialized.
- Do not infer that mutable state accessed concurrently by jobs A and B becomes thread-safe.
- Do not infer that every run will start at the exact wall-clock time.
- A failure stopping a sequence still requires monitoring.

If the same code is scheduled **twice separately**, those are **two distinct periodic tasks** and can run concurrently when the pool has multiple workers. Do not rely on the no-overlap guarantee of a single schedule to protect shared state between two schedules.

## 16. Clocks, Period, Drift, and the Impact of Errors

`scheduleAtFixedRate` and `scheduleWithFixedDelay` take **relative delays**, typically suited to scheduling mechanisms using monotonic time for intervals. They are not local-time wall-clock crons.

### Fixed rate if a task runs long

If execution consistently takes longer than the period, the scheduler cannot run **overlapping** executions of the same task to catch up. Subsequent runs may start **late**, with very little actual wait time. If an iteration fails in this sequence, subsequent runs are suppressed even if multiple deadlines were missed earlier.

### Fixed delay if a task runs long

The delay interval between **the end** of one iteration and the start of the next still applies; total spacing between two starts is roughly **iteration duration + delay**, plus overhead/scheduling jitter.

### How errors break the cadence

If a task unexpectedly throws an exception on round 5:

- There is no round 6 on the **same schedule**, and no policy to "wait another period and retry."
- `ScheduledFuture` transitions to the failed done state.
- To run again, you must **create a new schedule** after deciding how to handle round 5's state.
- There is no default mechanism to "catch up on all missed runs" once you create a new schedule.
- For business logic requiring catch-up, you need a separate **work items/checkpoints** model rather than assuming fixed rate will automatically replay missed data.

## 17. Monitoring: How to Detect That a Job Has Stopped

An alive scheduler does not prove every periodic job is executing. At a minimum, each critical job should have:

- **Stable identifiers:** job name, work type, appropriate partition/tenant, without logging sensitive payloads.
- **Last start timestamp** and **last completion timestamp**.
- **Last success timestamp** and **last failure timestamp** tracked separately.
- **Consecutive failures** and total failure count, categorized as retryable/fatal.
- **Current ScheduledFuture state:** cancelled, done, or still active.
- **Execution duration**, queue delay / schedule lag if required by SLAs.
- **Restart count** and reason, to avoid restart storms.
- **Age of output data:** a job that runs without making progress must also be detected.

In cases where logic catches exceptions and returns, the Future **can still be active** even though the business operation has failed for many rounds. Checking `future.isDone()` alone is not enough; you must track **business success metrics** from the executing code.

### Non-blocking Future probing

```java
void inspect(String jobName, ScheduledFuture<?> future) {
    if (!future.isDone()) {
        return; // Periodic task may be operating normally.
    }
    try {
        future.get(); // Already done, does not wait indefinitely.
    } catch (CancellationException e) {
        recordCancelled(jobName);
    } catch (ExecutionException e) {
        recordFailed(jobName, e.getCause());
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
```

This is an **illustrative method**, with `recordCancelled`/`recordFailed` and `java.util.concurrent` imports defined by the application. Calling `Future.get` after `isDone` fits standard `ScheduledFutureTask`; if using a custom Future, evaluate its contract separately.

**Do not call untimed `future.get()` on an active periodic Future** in a health-check thread or scheduler worker, as it can block indefinitely. For a periodic controller, store the Future handles and inspect status non-blockingly.

### When a job is active but stuck forever

If a task **hangs inside an iteration** without throwing an exception, the Future may still report `isDone()==false` and no subsequent run will occur (because the current iteration has not finished). You need **heartbeats, duration thresholds, I/O timeouts, and stack/thread diagnostics** to distinguish "still active" from "stuck." `Future.isDone()==false` is not sufficient to assert that the scheduler is making proper progress.

## 18. What Happens If You Auto-Restart?

A watchdog can detect a failed Future and create a new schedule, but this must be done carefully:

1. **Confirm the actual state:** inspect the done Future and extract the cause; distinguish failed/cancelled/shutdown.
2. **Check the restart policy:** is the error transient or permanent/invariant corruption? If permanent, stop and alert.
3. **Limit attempts:** apply backoff, controlled jitter, and a threshold/consecutive-failure breaker; avoid creating hundreds of new schedules in a minute.
4. **Avoid creating duplicates:** if the scheduler already has another schedule for the same invariant, a new restart could create two jobs running concurrently. You need ownership/a registry and a compare-and-swap operation on the handle or lifecycle coordinator.
5. **Do not assume failed Future = rolled-back side effects:** check transactions/checkpoints, idempotency, and in-flight state.
6. **Do not restart after intentional shutdown:** `isShutdown()`/operational policy must be respected.
7. **Control metrics and alerts:** continuous restarts can mask the root cause; track restart counts, causes, and last healthy interval.
8. **Evaluate races between watchers/restarts:** if multiple watchdogs detect a failure simultaneously, only one may create a valid replacement.

A conceptual skeleton:

```text
if periodicFuture completed exceptionally:
    cause = observe future failure
    if cause recoverable and restart budget available:
        reconcile state, then atomically register a new schedule
    else:
        alert and disable job until repaired
```

This is **pseudocode**, not runnable Java. Do not auto-retry on every exception.

### Data loss and idempotency

A job reads 100 records and writes 50 records sequentially before failing. Recreating the same schedule does not mean the first records were processed exactly once. You must have transactions, checkpoints, idempotency, or deduplication to protect side effects. The scheduler only controls **when code runs**, not the durability of the data pipeline.

## 19. ScheduledThreadPoolExecutor Shutdown Policies

`ScheduledThreadPoolExecutor` has specific policies for scheduled tasks when the executor shuts down:

- `setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)` determines whether **existing periodic tasks** continue after `shutdown()` (default **false**).
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)` determines whether already-queued **one-shot delayed tasks** run after `shutdown()` (default **true**).
- `setRemoveOnCancelPolicy(boolean)` determines whether cancelled tasks are immediately removed from the work queue (typically default **false** in Java 17; check the JDK version/implementation when using).

Understand that **shutdown** and **exceptions** are two distinct reasons a periodic task stops running. `shutdownNow()` also attempts to interrupt running tasks, returns waiting tasks, and does not guarantee all side effects have stopped.

### Why do shutdown policies matter for debugging?

If a job does not run its next iteration after some component calls `scheduler.shutdown()`, do not jump to the conclusion that it threw an exception. Check `isShutdown/isTerminated`, cancellation, and the Future's outcome.

Example:

```java
ScheduledThreadPoolExecutor scheduler = new ScheduledThreadPoolExecutor(2);
scheduler.setRemoveOnCancelPolicy(true);
// Use the scheduler, then explicitly shut it down according to ownership.
```

This is an illustrative snippet inside a method; it requires importing `ScheduledThreadPoolExecutor`. `setRemoveOnCancelPolicy(true)` helps avoid retaining cancelled delayed tasks in the queue longer than necessary, though it does not stop currently running work immediately.

**Lifecycle ownership:** whoever creates the scheduler should generally be responsible for shutting it down. Do not call shutdown on a shared pool from inside an iteration or a business method that does not own its lifecycle.

## 20. A Periodic Sequence Differs From a Series of One-Shot Tasks

Many people try to simulate periodic work by having a task call `scheduler.schedule(this, delay, unit)` at the end:

```java
// Illustrative model, omitting lifecycle details:
void runAndReschedule() {
    try {
        doWork();
    } finally {
        scheduler.schedule(this::runAndReschedule, 1, TimeUnit.SECONDS);
    }
}
```

This is an **illustrative method** with `scheduler` and `doWork` from an outer context, not production code. Rescheduling in `finally` even after an error can create a new sequence **regardless of failure policy**. If the scheduler shuts down, `schedule` can reject; if there are retries elsewhere, it can create duplicates; if the task has a critical error, self-rescheduling can corrupt invariants.

An API-managed periodic `ScheduledFuture` sequence has clear cancellation/error-suppression semantics; a **self-rescheduling one-shot chain** requires managing everything manually:

- Errors and the continue/stop decision.
- Retry limits and backoff.
- The Future/handle of the next scheduled run.
- Races with shutdown/cancel.
- Avoiding multiple parallel schedules.
- Per-iteration results/metrics.

Do not switch from the periodic API to self-rescheduling just to "dodge" exception suppression without designing the full lifecycle.

## 21. Verifying Exceptions Without Making the Scheduler "Silent"

### Log at the right layer

There are three useful places:

1. **Directly inside the iteration:** catch recoverable errors, record metrics/causes, decide whether to return or rethrow.
2. **In the ScheduledFuture observer:** when the Future is done, call `get()` to learn the terminal failure/cancellation.
3. **In worker/executor-level instrumentation:** measure duration, run counts, queue, `afterExecute`, while understanding the Future wrapper and the `isDone` condition.

Do not rely solely on `Thread.UncaughtExceptionHandler`: because scheduled tasks are wrapped in `ScheduledFutureTask`, throwables can be stored in the Future without escaping the worker as a normal uncaught exception.

### Logging must not swallow the original error

If logging throws a new exception while handling the original error, the task's outcome may reflect the logging failure rather than the initial business error. Make instrumentation **exception-safe**, bound I/O time, and avoid logging secret data.

### Distinguish a single failed iteration from a stopped sequence

If an iteration catches and returns, `iterationFailures++` increments while `ScheduledFuture.isDone()` remains false. If an iteration throws out, the Future completes exceptionally and `lastTerminalCause` appears. These are two different alert types: **sequence still running with bad results** vs. **sequence has terminated**.

## 22. Time-Related Confusions

### `get` timeout is not a task timeout

`future.get(100, TimeUnit.MILLISECONDS)` only limits **how long the caller waits for completion**. It does not impose a hard deadline on the body of `run()`. If an iteration is blocking on I/O for 30 seconds, a 100 ms `get` timeout does not stop that I/O.

To bound an iteration, design timeouts on I/O operations, interrupt-supporting cancellation, deadlines in logic, or separate coordination. Never run periodic tasks indefinitely without liveness metrics.

### Fixed rate does not "catch up" concurrently

If the pool is busy, a fixed-rate task can lag. Subsequent runs do not overlap with previous runs of the same task. Do not assume 1,000 iterations will occur in exactly one second with `period=1ms` under high load.

### A caught error does not automatically adjust the schedule

If code handles a transient exception and returns normally, fixed rate/delay continues according to the original timing rules. It **does not automatically increase backoff** based on error count; if you want exponential backoff, you must design an appropriate state machine/scheduling strategy yourself.

### Repeated bad input

If the same bad item appears on every iteration and you always catch and return, the scheduler stays "alive" while the work may fail every single time. You need quarantine/dead-letter handling, alerts on consecutive failures, bad-data validation, and protection against retry storms.

## 23. Java Memory Model and Happens-Before Relationships

An issue orthogonal to exceptions is **memory visibility** across threads.

`ScheduledThreadPoolExecutor` specifies that successive executions of the **same periodic task** do not overlap, and the effects of a prior execution *happen-before* the effects of the subsequent execution, even if they run on different worker threads. This gives carrying state across iterations of the **same schedule** proper memory-ordering guarantees.

However:

- **Different periodic tasks** do not automatically share a happens-before order if they read/write the same state.
- A shared mutable object can be modified by another thread while the job is running; proper locks/atomics/immutable state are still required.
- `Future.get()` is the boundary for the Future's outcome/completion; for a periodic task that is still active, you cannot wait on it with `get()` and assume a single iteration has completed.
- `CountDownLatch`/`AtomicInteger` in the demo allow `main` to observe progress via primitives with clear memory effects.
- Do not use `Thread.sleep` as a publication/happens-before mechanism.

**Do not confuse** the no-overlap rule of a single periodic task with transactions across external systems: databases, files, and networks still require their own consistency protocols.

## 24. Common Pitfalls — Frequent Mistakes and How to Fix Them

1. **"A RuntimeException will be ignored and the scheduler will still run the next cycle."** False for `scheduleAtFixedRate`/`scheduleWithFixedDelay`: an escaping exception suppresses subsequent runs.
2. **"Only fixed rate stops; fixed delay retries automatically."** False: both share the same suppression rule.
3. **"Future.get() after scheduleAtFixedRate returns the result of the first run."** False: an active periodic Future does not return normally.
4. **"isDone() == true means the last iteration succeeded."** False: periodic `isDone()` usually means cancelled or failed.
5. **"Seeing counter == 1 after 2 seconds proves it won't run again."** Timing tests can be flaky; rely on the Future's failed outcome + contract.
6. **"Catching Throwable and ignoring it to keep the job running is a safe solution."** It can mask JVM fatal errors and state corruption.
7. **"Catching an exception and returning means the business task succeeded."** False: you need per-iteration failure/success metrics.
8. **"Exceptions from periodic tasks always show up via UncaughtExceptionHandler."** No; the scheduled future wrapper typically captures the error.
9. **"afterExecute's Throwable will be non-null when a periodic task throws."** No for standard `ScheduledThreadPoolExecutor`: behind scheduled wrappers, the Throwable parameter is always null per Javadoc.
10. **"In afterExecute, just call future.get() to see the error."** False: if the periodic task is still active, `get()` can block indefinitely. You must check `isDone()`.
11. **"A schedule has two workers, so two iterations of the same job will overlap."** No, per `ScheduledThreadPoolExecutor`'s contract.
12. **"Two different schedules won't overlap because they share the same pool."** False: the pool can run them concurrently if enough workers are available.
13. **"Future.get(timeout) cancels the iteration when the timeout expires."** False: only the caller stops waiting.
14. **"cancel(true) guarantees external side effects are stopped/rolled back."** False: interruption requires task cooperation.
15. **"The scheduler is still running other tasks, so the job I care about must be healthy."** False: failure belongs to each individual periodic Future.
16. **"Automatically rescheduling a task after failure is always safe."** It can cause duplicates, restart storms, or re-run non-idempotent operations.
17. **"A failure means all data from that run was rolled back."** False: side effects before the exception may already be committed.
18. **"Fixed rate catches up all missed ticks simultaneously."** False: iterations of the same task do not overlap.
19. **"shutdown() does not affect already-scheduled periodic jobs."** False under `ScheduledThreadPoolExecutor`'s default policy.
20. **"Putting Thread.sleep inside Runnable is a good way to control the period."** Unnecessary and often increases drift/blocks workers; use the scheduling API per its contract.
21. **"Schedule a new task for each retry without keeping the handle."** False: without a handle, it is hard to cancel, monitor, and prevent duplicates.
22. **"If isDone=false, there cannot be any errors."** False: an iteration may catch errors and return normally, or hang.
23. **"Logging errors cannot change the schedule's state."** False: logging that throws an unchecked exception out of `Runnable` can also trigger suppression.
24. **"newScheduledThreadPool(4) means one periodic task runs four instances in parallel."** False: core pool size limits concurrent distinct tasks, not duplicating a single schedule.

## 25. Production Design Checklist

When deploying a periodic job in Java SE, answer the following:

- **Job semantics:** does the job need to run at every tick, or only periodically refresh state?
- **Timing:** fixed rate or fixed delay; what are the period, initialDelay, jitter, and deadline?
- **Failure policy:** which exceptions are caught to continue, and which must stop/alert?
- **Data:** if an iteration fails midway, is state/output still consistent?
- **Retry:** what are the attempt limits, backoff, idempotency, replay, and checkpoints?
- **Observability:** do we track last success, last error, consecutive failures, task duration, lag, and Future state?
- **Termination:** is there a clear scheduler owner, shutdown policy, deadline, and cancellation?
- **Overlap:** can the same logic be scheduled twice by two different components?
- **Concurrency:** do other schedules share mutable state?
- **Timeouts:** does every I/O operation have a timeout so the task cannot block indefinitely?
- **Monitoring:** do observers avoid blocking `get()` calls on active periodic Futures?
- **Testing:** using latches/Futures/timeouts, are first-run exceptions, Nth-run exceptions, cancel, shutdown, restart, and retry tested?
- **Compatibility:** are JDK 17+ APIs available in the build/runtime environment?

Turn all answers into tested/monitored contracts rather than throwing an exception and hoping the schedule continues.

## 26. Practice Exercises

**Exercise 1 — Fixed rate stops after round 2:** modify the demo so iteration #1 runs normally and #2 throws `IllegalStateException`. Use `Future.get(timeout)` to verify the cause and final counter equal to 2. Do not use `Thread.sleep` for testing.

**Exercise 2 — Fixed delay continues after a transient failure:** write a `Runnable` that runs 4 rounds, where round #2 catches a `RetryableException` and returns; use `CountDownLatch(4)` to verify 4 rounds complete. Count **business successes** separately from **iteration attempts**.

**Exercise 3 — Future observer:** build a non-blocking `inspect(ScheduledFuture<?>)` method; if the future is not done, return; if done, classify `CancellationException`/`ExecutionException`. Call `inspect` on an active Future and a failed Future.

**Exercise 4 — Restart budget:** create a controller that only permits restarts after a future fails and after a backoff delay. Write a test so two observers do not create two replacements at the same time. Do not restart when the cause is an invariant violation.

**Exercise 5 — Side effects:** simulate writing 3 records, failing after record #2, and retrying. Demonstrate why an idempotency key or commit boundary is needed to avoid processing records #1/#2 twice.

**Exercise 6 — Monitoring caught errors:** if a Runnable always catches exceptions and returns, the Future stays active. Design `consecutiveFailures` and `lastSuccessNanos` counters so a health check detects a job making no progress even though its schedule is alive.

## 27. Review Questions and Answers

**Question 1.** Does `scheduleAtFixedRate()` automatically run the next iteration when the previous iteration throws a `RuntimeException` out?  
**Answer:** No. Subsequent runs of the same periodic schedule are suppressed; the Future completes exceptionally.

**Question 2.** Does `scheduleWithFixedDelay()` differ from fixed rate regarding failure suppression?  
**Answer:** No. It differs in how the next run time is calculated, but it has the same exception rule stopping subsequent runs.

**Question 3.** How do you retrieve the root cause of a failed periodic task?  
**Answer:** Call `ScheduledFuture.get()` on the done Future; it throws `ExecutionException`, from which you read `getCause()`.

**Question 4.** Why shouldn't you call `future.get()` unconditionally in `afterExecute`?  
**Answer:** While the periodic task is still active, the Future is not done, so `get` can block indefinitely on the worker; you must check `future.isDone()`.

**Question 5.** Does `ScheduledThreadPoolExecutor.afterExecute(r, t)` always receive a Throwable when a scheduled Runnable throws an error?  
**Answer:** No. `ScheduledThreadPoolExecutor` wraps tasks in `ScheduledFuture`, and the Javadoc states `t` is always null; errors are read via the Future.

**Question 6.** When one scheduled task throws an error, are all other scheduled tasks on the same pool stopped?  
**Answer:** Not by default. The failing task's sequence is suppressed; other schedules can continue running if the executor is active.

**Question 7.** Why does `isDone() == true` not prove a task succeeded?  
**Answer:** For a periodic task, `done` can result from failure or cancellation; you must inspect the outcome.

**Question 8.** If a Runnable catches a transient exception and returns, does the scheduler continue?  
**Answer:** It can continue per the defined schedule because no exception escaped; you must record separate metrics for the failed iteration.

**Question 9.** Should you catch all `Throwable`s to prevent a schedule from stopping?  
**Answer:** No. Severe errors like `OutOfMemoryError` or invariant corruption should not be hidden and blindly continued past.

**Question 10.** Does `Future.get(1, SECONDS)` throwing `TimeoutException` on an active periodic task mean the job failed?  
**Answer:** No. It only means the caller did not see the Future complete within the deadline; a normally operating periodic Future does not complete.

**Question 11.** If a fixed-rate task takes 500ms with a 100ms period, does the scheduler run five instances of the same task concurrently?  
**Answer:** No. Runs of the same periodic task do not overlap; subsequent runs may start late.

**Question 12.** Does `cancel(false)` prevent unstarted future runs, and does it force an active iteration to stop immediately?  
**Answer:** Cancellation prevents subsequent runs per contract; `false` does not request interrupting the active iteration, so it does not promise immediate termination.

**Question 13.** After a job fails, does creating a new schedule guarantee all data is valid?  
**Answer:** Not yet. You need reconciliation/checkpoints/idempotency, duplicate prevention, a restart budget, and root-cause analysis.

**Question 14.** Can `shutdown()` on `ScheduledThreadPoolExecutor` stop periodic tasks under the default policy?  
**Answer:** Yes. The default `continueExistingPeriodicTasksAfterShutdownPolicy` is `false`.

**Question 15.** A job always catches errors and returns so its Future has `isDone()==false`; is the job guaranteed to be healthy?  
**Answer:** No. It could be failing every iteration while continuing; you must monitor last success/failure, progress, and output.

**Question 16.** An iteration does not throw an error but blocks indefinitely: what might the Future look like?  
**Answer:** It may remain not done, with no subsequent runs executing because the current iteration hasn't finished; duration/timeout/heartbeat monitoring is needed.

## 28. Official References

- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): contracts of `scheduleAtFixedRate` and `scheduleWithFixedDelay`, exception suppression, periodic `Future.get`.
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): scheduling, no-overlap, happens-before between successive executions, `afterExecute`, shutdown and cancellation policies.
- [Java SE 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): Future + Delayed semantics.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, `isDone`, memory consistency.
- [Java SE 17 — Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): `newScheduledThreadPool` and factory methods.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test coordination/synchronization with happens-before.
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): failure wrapper from Future.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, interrupts, and happens-before.

**Conclusion:** for Java periodic tasks using `scheduleAtFixedRate()` or `scheduleWithFixedDelay()`, **an exception escaping a run causes subsequent runs of that same task to be suppressed**. `ScheduledFuture` helps observe the terminal cause; to keep the scheduler running after expected errors, the code must **catch/record and return normally** under a data-safe policy. Never call `Future.get()` unconditionally on an active periodic Future; monitor business progress, duration, and lifecycle separately from "the pool is still alive."
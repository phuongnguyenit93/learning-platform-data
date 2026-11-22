# `scheduleAtFixedRate()` and `scheduleWithFixedDelay()` in Java

When a Java application needs health checks, cache refreshes, metric sampling, or periodic jobs, `ScheduledExecutorService` lets you schedule repeated execution without writing a manual `while` loop with `Thread.sleep()`. The two common APIs look similar on the surface, but they differ in **when the next run is scheduled**:

- **`scheduleAtFixedRate()`:** aims to run at evenly spaced points on a **fixed schedule**, calculated from the expected time of the first run. If one run is slow, the next may start late and runs may execute back-to-back to catch up with the schedule; **two executions of the same periodic task never overlap**.
- **`scheduleWithFixedDelay()`:** the next run is only scheduled after **the previous run finishes**, then waits for a full delay period. The actual frequency depends on both the delay and how long the work takes.

Both run on Java SE's scheduled thread pool. **There is no hard real-time guarantee**: exact timing can drift due to the scheduler, CPU, queue, garbage collection, or other tasks. Furthermore, a periodic task that throws an unhandled exception causes **subsequent runs to stop** according to the contract of both APIs.

This article belongs to **Future & Scheduling** in **general Java concurrency**, using JDK 17+, without Spring Framework annotations, schedulers, or runtime.

## 1. Where are the APIs, and which executor is used?

The `ScheduledExecutorService` interface lives in `java.util.concurrent` and extends `ExecutorService`. The most commonly used implementation is `ScheduledThreadPoolExecutor`.

Example of creating a scheduler:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);
```

This is an illustrative snippet, not a standalone program. The factory typically creates a `ScheduledThreadPoolExecutor` with the corresponding number of core threads. Two other options:

```java
ScheduledExecutorService one =
        Executors.newSingleThreadScheduledExecutor();

ScheduledExecutorService several =
        Executors.newScheduledThreadPool(4);
```

`newSingleThreadScheduledExecutor()` provides a scheduler using a single thread to process tasks sequentially (and can replace the worker when needed); `newScheduledThreadPool(4)` can execute **different tasks** concurrently on up to the appropriate number of core workers.

A scheduled executor **is not an absolute-precision clock timer**, and the core pool size does not guarantee when a task will start. You need to design logic that tolerates delays and overload.

## 2. Signatures and parameters of the two methods

```java
ScheduledFuture<?> scheduleAtFixedRate(
        Runnable command,
        long initialDelay,
        long period,
        TimeUnit unit);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable command,
        long initialDelay,
        long delay,
        TimeUnit unit);
```

These are illustrative API declarations, not code to add to a class.

| Parameter | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
| --- | --- | --- |
| `command` | `Runnable` to run repeatedly | `Runnable` to run repeatedly |
| `initialDelay` | How long to wait before the first scheduled run | How long to wait before the first run |
| `period` / `delay` | Interval between **expected start times** | Interval between **previous completion** and **next start** |
| `unit` | Time unit for `initialDelay` and `period` | Time unit for `initialDelay` and `delay` |
| Result | `ScheduledFuture<?>` to control/observe the schedule | `ScheduledFuture<?>` to control/observe the schedule |

For both methods:

- `period` or `delay` must be **positive**; zero or negative values throw `IllegalArgumentException`.
- `initialDelay` of 0 (or negative per the delayed execution contract) means the first run is considered immediately eligible to run, though still subject to scheduling.
- If `command` is `null`, the contract throws `NullPointerException`.
- If the executor does not accept the task (for example, after shutdown), `RejectedExecutionException` may be thrown.
- `Runnable` does not return a business value; `ScheduledFuture<?>` mainly represents lifecycle/cancellation and exceptions of the periodic task, not a stream of results per run.

## 3. Fixed rate: scheduled timestamps, not task completion time

Suppose `initialDelay = 0`, `period = 1 second`. The **ideal timestamps** are:

```text
time (s):  0       1       2       3       4       5
           |-------|-------|-------|-------|-------|
target:    R1      R2      R3      R4      R5      R6
```

If each run takes around 200 ms, the scheduler usually has idle time between runs. When one run takes 1.6 seconds, the next target timestamp arrives before the current run finishes:

```text
Schedule:  0       1       2       3       4       5
           |-------|-------|-------|-------|-------|
run R1:    [==============]   (takes ~1.6 s)
run R2:                   [==] (may start late)
run R3:                     [==]
```

The diagram **illustrates timing relationships**, not mandatory output. Java does not promise that actual timestamps are spaced by exactly 1 second.

Key points:

1. The target interval is based on the expected start schedule, not adding `period` after the task finishes.
2. If a task is delayed/overruns, the next run **is allowed to start late**.
3. Runs may happen close together or back-to-back when the scheduler is behind schedule.
4. **Executions of the same periodic task never overlap**, even in a pool with multiple workers.
5. Consecutive runs may execute on **different worker threads**, and `ScheduledThreadPoolExecutor` guarantees that the effects of a previous run happen-before the next run for the same periodic task.

Do not interpret "fixed rate" as "forced to spawn an independent copy every 1 second." `scheduleAtFixedRate` is not a mechanism that automatically clones a task when an older run is slow.

## 4. Fixed delay: rest interval after completion

Suppose `initialDelay = 0`, `delay = 1 second`; the first run takes 600 ms:

```text
time:      0        0.6        1.6        2.2        3.2
           |--------|----------|----------|----------|
run 1:     [======]
delay:              [----------]
run 2:                         [======]
delay:                                  [----------]
run 3:                                             ...
```

With `scheduleWithFixedDelay`, the next run is scheduled after **the current run finishes** plus `delay`. If the current run takes 2 seconds and the delay is 1 second, the time from the start of this run to the start of the next is typically around 3 seconds plus scheduling delay.

Therefore:

- Useful for polling that should rest after each completion.
- Does not try to catch up on missed schedule slots; the system has a defined rest interval between successful completions.
- A slow run pushes the next start time back accordingly.
- Like fixed rate, **two runs of the same periodic task never overlap**.

If the requirement is "at least 1 second between two network requests," fixed delay is usually a better fit than fixed rate; however, you must still consider retries, other requests, and deadlines of the work inside.

## 5. Brief timeline comparison

Suppose the task takes 800 ms and the configured interval is 500 ms, ignoring scheduler jitter:

| Aspect | Fixed rate (period 500 ms) | Fixed delay (delay 500 ms) |
| --- | --- | --- |
| Next calculation anchor | Scheduled start time from the first run | Completion time of the previous run |
| When task runs 800 ms | Schedule is behind; next run may start almost immediately after completion | Waits an additional ~500 ms after completion |
| Interval between starts | Can be close to 800 ms when the task always overruns | Approximately 800 + 500 = 1,300 ms |
| Catch-up behavior? | May start late runs back-to-back to catch up | No |
| Can one periodic task overlap? | No | No |
| Frequency tied to | Target schedule cadence | Work cycle + rest time |

These numbers are **estimates for learning**, not JVM-guaranteed timings. When the system has high scheduler delay, observed intervals can be significantly longer.

## 6. Java 17+ example: both schedules complete at least three runs

The following example checks **lifecycle** using `CountDownLatch` instead of guessing time intervals with `Thread.sleep`.

Save as `PeriodicThreeRunsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class PeriodicThreeRunsDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newScheduledThreadPool(2);
        CountDownLatch rates = new CountDownLatch(3);
        CountDownLatch delays = new CountDownLatch(3);

        try {
            ScheduledFuture<?> fixedRate =
                    scheduler.scheduleAtFixedRate(
                            rates::countDown,
                            0, 10, TimeUnit.MILLISECONDS);

            ScheduledFuture<?> fixedDelay =
                    scheduler.scheduleWithFixedDelay(
                            delays::countDown,
                            0, 10, TimeUnit.MILLISECONDS);

            boolean rateReached = rates.await(
                    5, TimeUnit.SECONDS);
            boolean delayReached = delays.await(
                    5, TimeUnit.SECONDS);

            fixedRate.cancel(false);
            fixedDelay.cancel(false);

            System.out.println("Rate reached three: " + rateReached);
            System.out.println("Delay reached three: " + delayReached);
            System.out.println("Both canceled: "
                    + (fixedRate.isCancelled()
                            && fixedDelay.isCancelled()));
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac PeriodicThreeRunsDemo.java
java PeriodicThreeRunsDemo
```

**Stdout on a normal run where the scheduler gets CPU within 5 seconds:**

```text
Rate reached three: true
Delay reached three: true
Both canceled: true
```

Both periodic tasks may execute more than three times before `main` cancels them because `main`'s scheduling is not instantaneous. **The example intentionally does not print the actual count** or promise exactly three runs. `CountDownLatch` only verifies that at least three invocations ran. `cancel(false)` requests stopping **future** runs; it does not automatically interrupt a currently running invocation.

Using `await(timeout)` in tests reduces the risk of hanging indefinitely if the executor makes no progress. In a real application, if `await` returns `false`, you must handle the deadline expiration instead of assuming success.

## 7. Runs of the same periodic task do not overlap

Someone might look at `ScheduledThreadPoolExecutor(4)` and think four threads will run multiple instances of **the same** periodic job in parallel if the period is small. That is a misconception.

Per the `ScheduledThreadPoolExecutor` contract, successive executions of **a single periodic task** do not run concurrently. While the task is still running, the next run is not allowed to overlap that invocation, even if other workers in the pool are idle.

Moreover, **the effects of the previous execution happen-before the next execution** for the same periodic task. Therefore, a task object with its own mutable state accessed only by periodic runs **of that exact task** can rely on this sequencing; however, if that state is also read/written by other threads, proper synchronization/safe publication is still required.

Java 17+ example verifying the concurrent invocation count of the same periodic task:

Save as `NoOverlapDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class NoOverlapDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(4);
        CountDownLatch completed = new CountDownLatch(3);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumConcurrent = new AtomicInteger();

        try {
            ScheduledFuture<?> task =
                    scheduler.scheduleAtFixedRate(() -> {
                        int now = active.incrementAndGet();
                        maximumConcurrent.accumulateAndGet(
                                now, Math::max);
                        try {
                            Thread.sleep(60);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        } finally {
                            active.decrementAndGet();
                            completed.countDown();
                        }
                    }, 0, 10, TimeUnit.MILLISECONDS);

            boolean reached = completed.await(
                    5, TimeUnit.SECONDS);
            task.cancel(false);

            System.out.println("Three runs observed: " + reached);
            System.out.println("Max concurrent runs: "
                    + maximumConcurrent.get());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac NoOverlapDemo.java
java NoOverlapDemo
```

Stdout on a normal run:

```text
Three runs observed: true
Max concurrent runs: 1
```

The task runs longer than the period, yet the same task does not overlap. `active` is only incremented/decremented inside the invocation, and `completed.countDown()` runs after decrementing. Using `Atomic` types allows safe metric observation if the logic changes later. If `main` is delayed by the scheduler, the task may execute a fourth time before cancellation; **max concurrent** remains 1.

Note that two **different** periodic tasks can still run in parallel when the pool has enough workers. The non-overlap rule here applies to runs of **the same `ScheduledFuture` periodic task**, not to all tasks in the executor.

## 8. Does fixed rate "make up" for missed schedule slots?

When a task runs longer than `period`, the ideal schedule timestamps keep advancing. After an invocation finishes, if the next timestamp is already in the past, the executor may let the next invocation start as soon as a worker and resources are available. When delays continue, invocations can happen close together.

However:

- There is no mechanism to run **multiple copies concurrently** of the same periodic task to clear a backlog.
- There is no exact promise that "each missed slot corresponds to one execution at a specific millisecond."
- If the system is continuously overloaded, the schedule may stay behind and the task may run almost continuously.
- If the task throws an exception, future runs stop (no further catch-up).
- If the executor shuts down or the task is canceled, lifecycle rules block future runs per the corresponding policy.

**A periodic task is not an event log.** If the business logic must process every event that occurred each second even after the app stops or restarts, an in-memory schedule provides neither durability nor exactly-once semantics. You need checkpoint/offset/queue data or a dedicated persistence mechanism.

## 9. Fixed delay provides a "cool-down" but does not guarantee a minimum frequency

With a fixed delay of 2 seconds, after an invocation completes normally, the next one will not be scheduled to start **before that rest interval** per the scheduling rules. This is useful when you want to avoid aggressive back-to-back polling.

However, there is no guarantee that the next invocation will definitely start right after 2 seconds; it can be delayed by the scheduler, a busy pool, or system resources. If the task itself takes 10 seconds, the cycle from one start to the next will be greater than 12 seconds.

Therefore, ask yourself:

- Want a **fixed cadence** for sampling? Consider fixed rate.
- Want **a rest interval after work completes**? Consider fixed delay.
- Want **a specific time on the clock** (e.g., 02:00 local time daily)? Both APIs take relative delay/period; for wall-clock and timezone schedules, you need a different scheduling layer.
- Want **global rate limiting across multiple tasks**? A per-task schedule is not automatically a global rate limiter.

## 10. Timeline table when one run is too slow

Suppose the first start is at t=0, each invocation takes 1.4 seconds, and the configured interval is 1 second, ignoring scheduler overhead:

```text
Fixed rate, period = 1 s
Target schedule: 0, 1, 2, 3, 4, ...
Approximate start: 0, 1.4, 2.8, 4.2, ...
Approximate end: 1.4, 2.8, 4.2, ...
=> almost no rest time when continuously overrunning.

Fixed delay, delay = 1 s
Approximate start: 0, 2.4, 4.8, 7.2, ...
Approximate end: 1.4, 3.8, 6.2, ...
=> always about 1 s of rest between completions
   and the next start.
```

These numbers are **idealized for explanation**, not guaranteed stdout or runtime deadlines.

With fixed rate, the second run starts around t=1.4 s not because the period changed to 1.4 s, but because the first invocation had not finished at t=1. With fixed delay, the second run's time is calculated **after** the first invocation finishes, so it is around t=2.4 s.

## 11. Why not print time intervals as fixed output?

Two `System.nanoTime()` calls placed before each invocation can help **observe** start intervals, but there is no fixed result. If you print `startDeltaMs` or `currentTimeMillis`, each machine and each run can differ.

A practical measurement program should:

1. Record `System.nanoTime()` right when the invocation starts and ends.
2. Avoid excessive logging on the critical path because logging can add overhead.
3. Wait for a sufficient number of invocations using a latch/atomic counter to collect samples.
4. Compute median/p95 and compare against task duration and queue contention.
5. State only **trends**, without treating millisecond output as invariant.
6. Keep correctness test logic separate from performance benchmarks; do not use a single jitter number to conclude the scheduler is broken.

`System.nanoTime()` measures **elapsed duration**, not real-world date/time or timezone. In these scheduling APIs, relative delays are also not guaranteed to stay aligned with absolute wall-clock ticks.

## 12. Exceptions in a periodic task: subsequent runs stop

The contract of both periodic methods states that if **any execution of the task encounters an exception**, subsequent executions are **suppressed**. This differs from many cron-like mental models of "fail this time, still run next time."

Example:

```java
scheduler.scheduleAtFixedRate(() -> {
    refreshCache(); // Throws RuntimeException if refresh fails.
}, 0, 1, TimeUnit.MINUTES);
```

This is an illustrative snippet. If `refreshCache()` throws an unchecked exception out of `Runnable.run()`, that schedule will not continue in the following minutes as usual.

Design considerations:

- Which tasks should **stop completely** on error to avoid corrupting state? Letting the exception propagate may be the right policy.
- Which tasks should **continue** after a transient error? Catch **selectively**, record the error, update health status, and decide whether the next invocation should be allowed to run.
- If an exception is caught and completely ignored, the system may keep running on schedule while data state remains broken. **Do not use a catch-all just to "keep the schedule alive"** without a policy.
- If a task blocks forever, there is neither an exception nor an invocation completion; the scheduler cannot start the next invocation of the same task until the current one finishes.

## 13. Java 17+ example: an exception terminates the periodic future

Save as `PeriodicExceptionDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicExceptionDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicInteger attempts = new AtomicInteger();

        try {
            ScheduledFuture<?> future =
                    scheduler.scheduleAtFixedRate(() -> {
                        int n = attempts.incrementAndGet();
                        if (n == 2) {
                            throw new IllegalStateException("boom");
                        }
                    }, 0, 10, TimeUnit.MILLISECONDS);

            boolean failed = false;
            String type = "";
            try {
                future.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                failed = true;
                type = e.getCause().getClass().getSimpleName();
            }

            System.out.println("Failed: " + failed);
            System.out.println("Invocations: " + attempts.get());
            System.out.println("Cause: " + type);
            System.out.println("Future done: " + future.isDone());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac PeriodicExceptionDemo.java
java PeriodicExceptionDemo
```

Stdout on a normal run:

```text
Failed: true
Invocations: 2
Cause: IllegalStateException
Future done: true
```

`future.get(5, SECONDS)` waits for the future to complete exceptionally when the second invocation throws. Because the exception stops the schedule, **there is no third run**. `ExecutionException.getCause()` retrieves the underlying cause. A single failed invocation does not automatically shut down the entire executor; other tasks in the pool can continue per the contract.

If you replace `scheduleAtFixedRate` with `scheduleWithFixedDelay` using a positive delay, the same rule of suppressed executions on exception applies.

## 14. What is special about `ScheduledFuture.get()` for a periodic task?

Both methods return `ScheduledFuture<?>`. Because a periodic schedule runs repeatedly until cancellation, an exception, or a shutdown policy ends it, **`future.get()` does not return a normal result for each run**.

Per the scheduling contract:

- If the periodic task keeps being scheduled and does not terminate, `get()` will **block and wait** rather than returning a `List` of results.
- If canceled, `get()` throws `CancellationException`.
- If an invocation throws an unhandled exception, `get()` can throw `ExecutionException` with the corresponding cause.
- `get(timeout, unit)` can throw `TimeoutException` if the future is still not done.
- `isDone()` is not a counter of completed runs; a periodic future may have run 100 times while `isDone() == false`.

If you need **results from each invocation**, report them yourself via a queue, metric, listener, or properly synchronized result/notification structure. Do not call `get()` on a periodic future after each run expecting a normal result.

## 15. Java 17+ example: `get(timeout)` does not count individual iterations

Save as `PeriodicFutureGetDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.CancellationException;

public class PeriodicFutureGetDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch oneRun = new CountDownLatch(1);

        try {
            ScheduledFuture<?> future =
                    scheduler.scheduleWithFixedDelay(
                            oneRun::countDown,
                            0, 1, TimeUnit.HOURS);

            oneRun.await();

            boolean timedOut = false;
            try {
                future.get(10, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            future.cancel(false);

            boolean canceledGet = false;
            try {
                future.get();
            } catch (CancellationException e) {
                canceledGet = true;
            }

            System.out.println("One run completed: "
                    + (oneRun.getCount() == 0));
            System.out.println("Get timed out: " + timedOut);
            System.out.println("Get after cancel: " + canceledGet);
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac PeriodicFutureGetDemo.java
java PeriodicFutureGetDemo
```

Stdout on a normal run:

```text
One run completed: true
Get timed out: true
Get after cancel: true
```

`oneRun.await()` waits for the first invocation to signal. The periodic future still has a next run scheduled **1 hour** later, so `get(10ms)` times out rather than returning a value from the first run. After `cancel(false)`, `get()` throws `CancellationException`.

If the scheduler is shut down or the task is canceled from another source beforehand, the execution path may differ; this example has only the `main` thread managing the pool lifecycle. `await()` in the demo intentionally has no timeout, as the first invocation is non-blocking and the pool is running; production test harnesses should still use timeouts to avoid hanging in broken environments.

## 16. Proactively catching errors: when should the next run still proceed?

For a polling task where individual outcomes are not critical, you can choose a **log/metric and continue** policy:

```java
scheduler.scheduleWithFixedDelay(() -> {
    try {
        pollRemoteService();
    } catch (TransientPollingException e) {
        recordFailure(e);
        // The next run is still scheduled after the delay.
    }
}, 0, 1, TimeUnit.MINUTES);
```

This is an illustrative snippet with hypothetical classes/methods.

However:

- Only catch errors that are **truly recoverable**. Errors that break invariants may need to stop the schedule.
- If the task performs I/O, set a timeout on **the I/O itself**, because the delay only starts after the task finishes.
- When catching `InterruptedException` in a `Runnable`, you should usually call `Thread.currentThread().interrupt()` and **exit per cancellation protocol**; do not swallow the interrupt and keep running normally.
- Track failure rate, consecutive failures, and last-success time; do not just print the exception to the console and forget it.
- If retry/backoff is needed, a fixed 1-minute delay may not be suitable. You can manage retries inside the task with a deadline or schedule **one-shot** tasks with dynamic delays.

## 17. Cancellation: stopping future runs vs. interrupting the running invocation

`ScheduledFuture.cancel(boolean mayInterruptIfRunning)` requests cancellation of a periodic task.

- `cancel(false)`: requests terminating future scheduled runs **without requesting an interrupt** of the currently running invocation via this parameter.
- `cancel(true)`: allows attempting to interrupt the currently running invocation, if the implementation handles it properly; does not guarantee immediate termination.
- When cancellation succeeds, `isCancelled()` and `isDone()` reflect the future's state, **not proof that all side effects of the invocation have finished cleaning up**.
- The task may finish right around the time of cancellation; handle races and idempotency if the task interacts with external systems.

Basic lifecycle pattern:

```java
ScheduledFuture<?> handle =
        scheduler.scheduleWithFixedDelay(
                work, 0, 5, TimeUnit.SECONDS);

// At the appropriate lifecycle management point:
handle.cancel(false);
```

This is an illustrative snippet, assuming `scheduler` and `work` are declared elsewhere.

Do not rely on `future.cancel(false)` to forcibly stop an HTTP request that has already been sent. Even `cancel(true)` is only a cooperative request; I/O may require its own timeout/close.

## 18. Java 17+ example: `cancel(false)` does not cancel work already in progress

This example uses latches to separate **schedule cancellation requested** from **invocation finished**.

Save as `CancelPeriodicDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelPeriodicDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicInteger started = new AtomicInteger();

        try {
            ScheduledFuture<?> future =
                    scheduler.scheduleAtFixedRate(() -> {
                        started.incrementAndGet();
                        entered.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        } finally {
                            finished.countDown();
                        }
                    }, 0, 10, TimeUnit.MILLISECONDS);

            entered.await();
            boolean accepted = future.cancel(false);
            boolean beforeRelease = finished.getCount() == 0;

            release.countDown();
            finished.await();

            System.out.println("Cancel accepted: " + accepted);
            System.out.println("Finished before release: "
                    + beforeRelease);
            System.out.println("Invocations started: "
                    + started.get());
            System.out.println("Future canceled: "
                    + future.isCancelled());
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac CancelPeriodicDemo.java
java CancelPeriodicDemo
```

Stdout on a normal run:

```text
Cancel accepted: true
Finished before release: false
Invocations started: 1
Future canceled: true
```

**Analysis:**

1. `entered.await()` ensures the first invocation has started and is waiting on `release`.
2. `cancel(false)` puts the future in the canceled state; it **does not request interrupting** the thread waiting on the latch.
3. Right before `main` opens `release`, `finished` has not reached 0, so the invocation is not done yet; `Finished before release: false` demonstrates that cancel does not mean cleanup is done.
4. `main` opens the latch, waits for `finished`, and prints the results. Only one invocation was ever started because subsequent runs were canceled while the first had not finished.
5. `finally` ensures the latch is released on error, avoiding leaving the worker waiting forever.

Do not directly reuse a `finished` latch like this across multiple invocations without clarifying **generations**; a latch with count=1 only tracks a single completion event.

## 19. Self-stopping after N runs: avoid unsafe handle storage

Some online examples write a periodic task that calls `future.cancel(false)` on itself through a `future` variable assigned after `scheduleAtFixedRate(..., 0, ...)`. Because the first run **can execute before the variable is assigned**, that code has a race condition or risks a `NullPointerException`.

A safer pattern in simple programs is:

1. Create the task and a `CountDownLatch` marking that N runs have occurred.
2. `main` or the schedule owner awaits the latch and then cancels via the returned `ScheduledFuture`.
3. Accept that an extra invocation may occur between reaching N and canceling, **unless** the task has a state machine that refuses work past N.

If you require **exactly N side effects**, place an atomic counter/claim inside the task and skip side effects on invocations beyond N, then let the owner cancel the schedule. Do not confuse "only N side effects" with "the scheduler invokes the task exactly N times."

Logic example:

```java
int ordinal = count.incrementAndGet();
if (ordinal > 3) {
    return;
}
performSideEffectFor(ordinal);
```

This is an illustrative snippet, where `count` is an `AtomicInteger` and `performSideEffectFor` is a hypothetical method. If external side effects can fail, you need separate completion/at-least-once/exactly-once policies; a counter alone does not create a transaction.

## 20. Different periodic tasks can contend for workers

The non-overlap rule **only applies to successive executions of the same periodic task**. In a pool with two workers:

```java
ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2);

pool.scheduleAtFixedRate(this::sampleMetrics,
        0, 1, TimeUnit.SECONDS);

pool.scheduleWithFixedDelay(this::pollResource,
        0, 1, TimeUnit.SECONDS);
```

This is an illustrative snippet in a class that has `sampleMetrics` and `pollResource`.

The two tasks above can run **concurrently** and contend for shared state. If both modify an `ArrayList` or send data over a non-thread-safe resource, you must protect it or design separate ownership. There is no "global lock" just because both belong to the same executor.

With **one worker**, different tasks execute sequentially, but a very slow periodic task can cause **starvation/latency** for the other task. With multiple workers, a long-blocking task occupies one worker while other tasks can still run if capacity remains.

Therefore, choose pool size based on **task duration, blocking behavior, and number of periodic work types**, not just "how many schedules per minute."

## 21. Java 17+ example: one worker makes another task wait

Save as `SharedSchedulerContentionDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SharedSchedulerContentionDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondFinished = new CountDownLatch(1);
        AtomicBoolean releasedBeforeSecond = new AtomicBoolean();

        try {
            pool.schedule(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, 0, TimeUnit.MILLISECONDS);

            firstStarted.await();

            pool.schedule(() -> {
                releasedBeforeSecond.set(
                        releaseFirst.getCount() == 0);
                secondFinished.countDown();
            }, 0, TimeUnit.MILLISECONDS);

            boolean secondBeforeRelease =
                    secondFinished.getCount() == 0;

            releaseFirst.countDown();
            secondFinished.await();

            System.out.println("Second ran before release: "
                    + secondBeforeRelease);
            System.out.println("Second saw release: "
                    + releasedBeforeSecond.get());
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac SharedSchedulerContentionDemo.java
java SharedSchedulerContentionDemo
```

Stdout on a normal run:

```text
Second ran before release: false
Second saw release: true
```

Because the pool has only **one worker**, the first task holds the worker while waiting on the latch; the second task cannot run before the first task leaves the wait. When `main` opens the latch, the worker finishes the first task and only then can execute the second task.

This example uses one-shot `schedule` to demonstrate **worker contention** clearly, independent of period or delay. The same principle applies when a periodic invocation occupies a worker for too long. If the pool had two workers, the two different tasks could run at the same time and the check outcome would change.

## 22. `shutdown()` and whether periodic tasks continue

With `ScheduledThreadPoolExecutor`, shutdown policies matter:

- **`setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)`:** determines whether already-scheduled periodic tasks continue running **after `shutdown()`**. Default is **`false`**.
- **`setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)`:** determines whether already-accepted one-shot delayed tasks run after `shutdown()`. Default is **`true`**.
- `shutdownNow()` requests stopping running tasks, attempts to prevent queued waiting tasks, and returns the list of tasks that never started per the contract; it does not guarantee running tasks stop immediately.

Do not conflate **delayed one-shot** tasks with **periodic** tasks when discussing shutdown. A shut-down scheduler rejects new tasks, while already-accepted tasks remain subject to their respective policies.

If you enable continue-existing-periodic-after-shutdown, periodic tasks may keep executing, preventing `awaitTermination()` from completing until they are canceled or terminate by some other condition. You must retain `ScheduledFuture` handles and design a clear lifecycle.

Illustrative configuration example:

```java
ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2);

pool.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
pool.setExecuteExistingDelayedTasksAfterShutdownPolicy(true);
```

These are the default values, but writing them explicitly tells the reader what the policy is. If managing a **shared** pool, do not arbitrarily change policies or call shutdown from a component that does not own the executor.

## 23. `removeOnCancelPolicy` and canceled tasks retained in the queue

`ScheduledThreadPoolExecutor` uses a delayed work queue. A task scheduled far in the future and then canceled may **remain in the queue** until its delay expires, under the default policy of keeping the entry.

With many tasks canceled before their deadline, this can cause the queue to hold extra references and increase memory retention even though the tasks will not run.

You can enable:

```java
ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2);
pool.setRemoveOnCancelPolicy(true);
```

This is an illustrative snippet. `setRemoveOnCancelPolicy(true)` requests immediate removal of canceled tasks from the work queue upon cancellation, reducing reference retention when many delayed/periodic tasks are canceled. `getRemoveOnCancelPolicy()` reports the current policy.

Do not assume that removing a task from the queue proves a running task has finished. **Queue retention** and **worker execution/cancellation** are two separate concerns.

Avoid calling `getQueue().remove(...)` directly or manipulating the queue instead of retaining the `ScheduledFuture` handle and calling `cancel`; manual manipulation can break the executor's lifecycle tracking.

## 24. If tasks run long: separate scheduling from blocking work

A periodic method might make HTTP calls, read files, or wait on a downstream service. If the blocking operation has no timeout:

- The current invocation can hang indefinitely.
- No subsequent invocation of **the same periodic schedule** can start before this one finishes.
- `scheduleWithFixedDelay` cannot start the delay after an unfinished invocation.
- `scheduleAtFixedRate` also cannot spawn another invocation to bypass a blocked one.
- Other tasks can be delayed if they share a small worker pool.

The solution depends on requirements:

1. **Set I/O timeouts** using the proper client/channel APIs.
2. **Define a deadline** for the whole operation, not just the scheduler's period/delay.
3. If you need non-overlapping runs and can wait, use sequential scheduling with a timeout policy.
4. If you need true concurrency, separate the timer from the worker pool and use **bounded concurrency / queue / semaphore**, while managing overlap, backpressure, memory, and cancellation.
5. **Do not submit unbounded** new tasks every second when downstream is stuck; the backlog can grow without limit.
6. Use metrics such as `lastSuccess`, duration, failure count, and queue depth to observe actual latency.

Fundamentally, `period` and `delay` govern **the invocation schedule**, not a hard timeout on the task body.

## 25. One-shot self-rescheduling example: when the delay needs to vary

`scheduleWithFixedDelay` has a **fixed delay**. If you need exponential backoff or a schedule based on the previous result, one approach is to **schedule a one-shot task that reschedules the next run itself**.

Outline:

```java
void pollOnce() {
    long nextDelayMillis;
    try {
        doPoll();
        nextDelayMillis = 1_000L;
    } catch (TransientException e) {
        nextDelayMillis = 5_000L;
    }

    if (!stopping.get()) {
        scheduler.schedule(this::pollOnce,
                nextDelayMillis, TimeUnit.MILLISECONDS);
    }
}
```

This is an illustrative snippet, not a standalone program. `scheduler` is a `ScheduledExecutorService`, `stopping` is safely published state, and `doPoll`/`TransientException` belong to the application.

Additional things you must design:

- Race between `stopping` and `schedule`: shutdown may happen right after the check, throwing `RejectedExecutionException`; handle it intentionally.
- If you want to guarantee no tasks remain after stopping, manage the scheduled handle and cancellation.
- If another exception escapes before the reschedule step, the chain can stop.
- Retries need limits and appropriate jitter to avoid many clients retrying in lockstep.
- One-shot scheduling does not automatically carry the "successive executions of the same periodic task happen-before" semantics of the periodic APIs; new tasks still require proper publication and synchronization for shared state.

## 26. Fixed rate is not cron or a real-time calendar schedule

When using:

```java
scheduler.scheduleAtFixedRate(
        this::refresh, 0, 24, TimeUnit.HOURS);
```

this is an illustrative snippet. It sets a **relative 24-hour** cycle, which is not equivalent to "every day at 08:00 in the local timezone." Wall-clock time has daylight saving time, systems can restart, and relative targets also experience scheduler delay.

A calendar schedule needs to handle:

- Timezones and daylight saving time.
- Missed runs when the process is down.
- Duplicate execution across multiple JVM instances.
- Idempotency/transaction semantics.
- Catch-up or skip policies for missed occurrences.
- Persistence of schedules and state across restarts.

`ScheduledExecutorService` is a tool for running periodic tasks **inside a live JVM**, not a distributed scheduler or durable job coordinator.

## 27. Naming threads and separating pools by task type

If a scheduler runs multiple types of tasks, naming workers helps with diagnostics:

```java
AtomicInteger sequence = new AtomicInteger();

ThreadFactory factory = runnable -> {
    Thread t = new Thread(runnable);
    t.setName("metrics-scheduler-" + sequence.incrementAndGet());
    return t;
};

ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2, factory);
```

This is an illustrative snippet; it requires importing `AtomicInteger`, `ThreadFactory`, and `ScheduledThreadPoolExecutor`.

Consider separate pools when one group of tasks has long blocking I/O or vastly different latency requirements from the rest. However, creating too many pools also consumes threads and resources; observe the actual workload.

If a pool is shared by multiple components, define **who owns shutdown and policies**. Do not let an arbitrary listener call `shutdownNow()` and accidentally stop schedules belonging to other components.

## 28. Proper lifecycle management practices

A public class that owns a scheduler should have a clear start/stop policy. Skeleton:

```java
final class PeriodicService implements AutoCloseable {
    private final ScheduledThreadPoolExecutor scheduler =
            new ScheduledThreadPoolExecutor(1);
    private ScheduledFuture<?> handle;

    synchronized void start() {
        if (handle != null) {
            throw new IllegalStateException("Already started");
        }
        handle = scheduler.scheduleWithFixedDelay(
                this::tick, 0, 1, TimeUnit.SECONDS);
    }

    private void tick() {
        // Perform one step with appropriate timeout/cancellation.
    }

    @Override
    public synchronized void close() {
        if (handle != null) {
            handle.cancel(false);
        }
        scheduler.shutdown();
    }
}
```

This is an illustrative class without `main`; it requires importing `ScheduledThreadPoolExecutor`, `ScheduledFuture`, and `TimeUnit`.

Points to add in production:

- Specify whether `close()` is idempotent and whether it waits for running tasks to finish.
- Avoid holding the `this` monitor while **waiting for workers** that might call synchronized methods on the same object.
- Check `scheduler.isShutdown()` or a state machine if `start` could be called after close.
- `cancel(false)` does not interrupt a running tick; if a shutdown deadline is needed, define `awaitTermination(timeout)` and escalation.
- If `tick` throws an exception, the future completes exceptionally; report health status instead of failing silently.
- If `tick` calls an external system, establish idempotency/timeout policies.

`AutoCloseable.close()` only tells callers there is a place to close; it does not automatically create a transaction or wait for cleanup unless the implementation does so.

## 29. How to choose the right API for your requirements

| Requirement | Recommendation |
| --- | --- |
| Sample metrics periodically at a nominal cadence | `scheduleAtFixedRate` |
| Poll a remote endpoint, resting N seconds after each poll | `scheduleWithFixedDelay` |
| Task needs dynamic retry/backoff | One-shot `schedule` rescheduling itself based on result |
| Run only once after a delay | `schedule` |
| Every day at 08:00 local time with DST support | Calculate schedule via calendar/timezone, not just 24h fixed rate |
| Same periodic task must not overlap | Both periodic APIs guarantee non-overlap |
| Multiple different tasks need to run concurrently | Pool with enough workers, and protect shared state yourself |
| Long-running task must be canceled | Separate task timeout/cancellation from period/delay |
| Transient errors must not kill the schedule | Catch/record per failure policy inside the task |
| Shutdown must stop periodic jobs | Retain handles, cancel, shut down, and choose appropriate policies |

**Product goals matter more than API names.** Fixed rate fits sampling cadence, but if downstream cannot tolerate back-to-back runs after an overrun, fixed delay or dynamic backoff may be more resilient.

## 30. Common mistakes

**1. "Fixed rate spawns multiple overlapping copies when a task is slow."** False. Runs of a single periodic task never overlap.

**2. "Fixed delay measures from the start time of the previous run."** False. Delay is measured from when the previous run **finishes**.

**3. "Fixed rate is accurate to the millisecond."** False. The scheduler/JVM provides no hard real-time guarantees.

**4. "Fixed rate never runs two executions back-to-back."** False. After an overrun, runs may occur close together while catching up to the schedule.

**5. "If a task throws a RuntimeException, the next run still executes."** False. Subsequent periodic invocations are suppressed when an exception escapes the task.

**6. "`ScheduledFuture.get()` returns the result of one periodic run."** False. It waits for the terminal state of the periodic future; it is not a stream of per-invocation results.

**7. "`cancel(false)` immediately stops the currently running invocation."** False. It does not request interrupting that invocation.

**8. "`cancel(true)` forces external side effects to roll back."** False. Interruption is only a cooperative request.

**9. "A pool of four workers runs the same task four times in parallel."** False. Multiple workers allow **different** tasks to run concurrently; they do not break non-overlap for the same periodic task.

**10. "Setting `period=0` means run as fast as possible."** False. Period/delay must be positive; invalid values are rejected.

**11. "`initialDelay=0` means the schedule method blocks until the command finishes."** False. Scheduling returns a handle; the command runs asynchronously when the executor has a worker.

**12. "By default, shutdown lets all periodic tasks keep running forever."** False. The default continue-existing-periodic policy of `ScheduledThreadPoolExecutor` is `false`.

**13. "Once canceled, a task is immediately removed from the queue in all configurations."** Not by default; see `setRemoveOnCancelPolicy(true)`.

**14. "Adding `Thread.sleep(period)` inside the command is equivalent to fixed delay."** False. Sleeping lengthens the invocation body without changing the scheduling anchor contract; it can hurt throughput and trigger fixed-rate catch-up.

**15. "A periodic task printing a huge iteration count proves there are no races."** No. Shared state and other tasks still require synchronization per the Java Memory Model.

**16. "`scheduleAtFixedRate` is a system that guarantees exactly-once across restarts."** No. It only schedules in-memory within the running executor.

## 31. Self-check questions

**Question 1:** `scheduleAtFixedRate(task, 0, 1, SECONDS)`, each invocation takes 2 seconds. Will the executor run two invocations of the same task concurrently?

**No.** The next run may start late and right after the previous one finishes; the same periodic task does not overlap.

**Question 2:** With `scheduleWithFixedDelay(task, 0, 1, SECONDS)`, the task takes 2 seconds. Roughly how long is the interval between consecutive starts without scheduling delay?

Approximately **3 seconds**: 2 seconds of work plus 1 second of rest after completion.

**Question 3:** Why can't `period=0` be used to run "continuously"?

Because the API requires `period > 0`, otherwise throwing `IllegalArgumentException`. If you want a worker continuously processing a queue, a consumer loop with clear cancellation/lifecycle is usually better.

**Question 4:** `ScheduledFuture.isDone()` is `false` even though the task has run 1,000 times. Is that a contradiction?

No. The periodic future is still active; `isDone` is not a count of completed runs.

**Question 5:** An invocation throws `IllegalStateException` out of `Runnable`. What happens?

Subsequent periodic invocations stop. You can observe the failure via `ScheduledFuture.get()` throwing `ExecutionException` with the corresponding cause.

**Question 6:** When a task does slow I/O, should you use fixed rate or fixed delay?

It depends on the contract. Fixed delay usually fits when you want a rest after a request finishes; fixed rate fits when you want a nominal cadence, at the risk of back-to-back runs after an overrun. Both still need I/O timeouts.

**Question 7:** If a periodic task is canceled with `false` while waiting on a latch, does it wake up on its own?

No. `cancel(false)` does not request interrupting the running invocation. A separate signal/lifecycle mechanism is needed to finish.

**Question 8:** On `shutdown()`, do periodic tasks continue by default with `ScheduledThreadPoolExecutor`?

By default **no**; `getContinueExistingPeriodicTasksAfterShutdownPolicy()` defaults to `false`. Delayed one-shot tasks have a different policy.

**Question 9:** Does `scheduleAtFixedRate` replace a daily timezone-aware cron?

No. It uses relative intervals and does not handle timezones, DST, restarts, or distributed ownership.

**Question 10:** Why enable `setRemoveOnCancelPolicy(true)` if an application has many canceled delayed tasks?

So canceled entries are removed early from the delayed queue, reducing reference retention time and avoiding unnecessary memory retention.

**Question 11:** Can two different periodic tasks in a two-worker pool mutate a shared ordinary `HashMap`?

Only with an appropriate synchronization protocol protecting it; the scheduler does not make `HashMap` thread-safe.

**Question 12:** What should you do if you want to adjust the delay after each failure?

Use one-shot scheduling with a delay computed from state/failure count, with retry limits and a clear lifecycle; the fixed-delay periodic API only takes a constant delay.

## 32. Implementation and operations checklist

Before taking a schedule to production:

1. **What is the timing goal?** Nominal start timestamps or rest intervals after completion?
2. **How long can the task run at most?** If it does I/O, configure timeouts/deadlines for the work itself.
3. **Is back-to-back catch-up acceptable?** If not, fixed delay or backoff may be better.
4. **Is there shared mutable state?** Only the same periodic task has non-overlap; different tasks still run concurrently.
5. **Who owns the `ScheduledFuture`?** Retain the handle to cancel the schedule properly.
6. **Should exceptions stop the schedule?** Define recoverable vs. fatal policies and report health/metrics.
7. **Do you need results from each invocation?** Do not rely on `ScheduledFuture.get()` for a result stream.
8. **On close, should running invocations be interrupted?** Choose `cancel(false/true)` per your contract.
9. **Is there a shutdown wait timeout?** Use `awaitTermination` and appropriate escalation; never block indefinitely inside a monitor.
10. **Do canceled tasks hold queue references for long?** Consider `setRemoveOnCancelPolicy(true)`.
11. **Do you need calendar/DST or durability?** Do not use fixed rate as a distributed persistent scheduler.
12. **Is task data idempotent on failure or retry?** Account for late results, retries, and partial side effects.
13. **Does the pool have enough workers for different tasks?** One long-blocking task can delay others.
14. **Are there backpressure and resource limits?** Do not submit unbounded new tasks on every tick.
15. **What is measured?** Scheduled-vs-actual start delay, invocation duration, success/failure count, longest gap, queue depth.
16. **Do tests rely on exact sleep times?** Use latches and invariant checks; timestamp logs are for observation only.

## 33. Summary

- **`scheduleAtFixedRate()`** targets **evenly spaced start times** in relative time; if a task is slow, the next run may start late and runs may execute back-to-back.
- **`scheduleWithFixedDelay()`** starts waiting `delay` **after the previous run finishes**; the start-to-start cycle includes task duration + delay + scheduling delay.
- **Neither allows runs of the same periodic task to overlap**, but other tasks in the pool can execute concurrently and require protecting shared state.
- **An exception escaping a periodic `Runnable` stops subsequent runs.** Design a failure policy and monitor `ScheduledFuture` status.
- **`ScheduledFuture.get()` does not return per-tick results**; cancellation, shutdown, and exceptional completion define the end of its lifecycle.
- **Scheduling intervals are not task timeouts.** Blocking work still needs its own deadlines, cancellation, and cleanup.
- **`ScheduledThreadPoolExecutor` has dedicated shutdown and remove-on-cancel policies.** They affect lifecycle and memory retention.
- **These two APIs are not a cron calendar, hard-real-time timer, or durable distributed job scheduler.** Requirements for exact timezone wall-clock times, catching up missed schedules, or exactly-once across restarts need a different solution.

The best choice comes from the **business meaning of the interval**: do you want work to try to appear on a clock-like beat, or do you want a guaranteed rest interval between completed runs? Once you understand that boundary, along with Java's exception/cancellation/shutdown contracts, scheduling becomes much more predictable than combining `while` and `Thread.sleep()`.

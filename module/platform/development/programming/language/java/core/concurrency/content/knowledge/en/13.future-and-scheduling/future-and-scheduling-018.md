# Long-Running Periodic Tasks: Fixed Rate, Fixed Delay, and Non-Overlapping Execution

> **Key Takeaway:** In Java, `ScheduledExecutorService.scheduleAtFixedRate` and `scheduleWithFixedDelay` both create **a sequential execution chain of the same periodic task**. When a task runs longer than the period/delay, the next run of **that same periodic task does not overlap the previous one**. The difference is that **fixed rate tracks nominal start times**, whereas **fixed delay starts counting the delay only after the previous run finishes**. Do not infer that *different* periodic tasks in the pool cannot run in parallel.

This article belongs to **Future & Scheduling** in **general Java concurrency**, using Java SE 17+ and primarily the `ScheduledExecutorService` and `ScheduledFuture` interfaces along with the `ScheduledThreadPoolExecutor` implementation. It does not cover Spring or framework scheduling annotations.

## 1. Periodic Tasks and the Question to Solve

For polling, cache refreshes, health checks, data cleanup, or recording statistics, we want to run a `Runnable` repeatedly on a schedule. The problem arises when **a single run takes longer than the scheduled interval**.

For example, a task needs to run "every 100 ms" but one processing pass takes 250 ms. What happens to the next pass?

- Is a new thread spawned to overlap the currently running pass?
- Are late "ticks" skipped?
- Is the next pass calculated from the **initial schedule mark** or **when the previous pass finishes**?
- If the pool has 4 workers, can 4 runs of the same task execute at the same time?
- If one pass throws an exception, does the periodic schedule still exist?

Answering correctly requires distinguishing between **a periodic schedule**, **a single execution**, and **multiple independent scheduled tasks**.

~~~text
ScheduledExecutorService
  ├── periodic task A: A1 -> A2 -> A3 -> ...   (does not self-overlap)
  ├── periodic task B: B1 -> B2 -> B3 -> ...   (does not self-overlap)
  └── one-shot task C: C1

A1 can run concurrently with B1 or C1 if enough workers are available,
but A1 does not run concurrently with A2 from the same schedule.
~~~

The **non-self-overlapping** property belongs to *successive executions of a periodic task scheduled through this API*. It is not a shared mutex protecting all calls of the same class or the same `Runnable`.

## 2. Two Common APIs

~~~java
// Illustrative API snippet, not a standalone program.
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);

// Ideal start times: initialDelay, initialDelay+period,
// initialDelay+2*period,... calculated from the initial schedule.
ScheduledFuture<?> rateHandle = scheduler.scheduleAtFixedRate(
        task, 0, 100, TimeUnit.MILLISECONDS);

// Wait delay from the END of the previous execution,
// before becoming eligible to start the next execution.
ScheduledFuture<?> delayHandle = scheduler.scheduleWithFixedDelay(
        task, 0, 100, TimeUnit.MILLISECONDS);
~~~

Both methods accept a `Runnable`, `initialDelay`, and a duration `period` or `delay`, returning a `ScheduledFuture<?>` used to observe or cancel the schedule.

Constraints worth remembering:

- `scheduleAtFixedRate` requires `period > 0`; `scheduleWithFixedDelay` requires `delay > 0`, otherwise they throw `IllegalArgumentException`.
- `initialDelay` can be 0 to run as soon as eligible; negative delays in some methods are treated as an immediate request under the scheduling contract, but do not design business schedules around negative delays.
- `TimeUnit` defines the unit; do not confuse milliseconds with seconds.
- Executions take place on worker threads managed by the executor; do not use `Thread.sleep` in the thread calling schedule to maintain the schedule.
- `ScheduledFuture.get()` **does not return a normal result after each pass** for an ongoing periodic schedule. It represents the entire periodic execution chain, not a separate Future for each tick.

## 3. Fixed Rate: Scheduled Start Marks Spaced by One Period

`scheduleAtFixedRate(task, initialDelay, period, unit)` targets the schedule:

~~~text
Scheduled time of run k (k starting from 0):
    scheduledStart(k) = t0 + initialDelay + k × period
~~~

For example, with a 100 ms period, the eligible start times are 0, 100, 200, 300 ms (relative to t0).

If each pass runs **shorter than the period**, there is a gap between passes to stay on the marks. However, if the first pass takes **250 ms**, the nominal time of the second pass (100 ms) has already passed. The second pass can **start late almost immediately after the first pass finishes**, depending on worker scheduling; it does not need to wait another full 100 ms from the finish time.

~~~text
period=100 ms, each run=250 ms (idealized illustration)

Fixed-rate marks: 0    100    200    300    400    500 ...
                  |-----|------|------|------|------|
Run A1:           [========= 250 ms =========]
Run A2:                                      [==== ...]
                  ^ A2 starts late, does not overlap A1
~~~

**Important:** This does not mean the scheduler creates a pile of separate `Runnable` instances for missed marks and runs them concurrently. The `ScheduledThreadPoolExecutor` contract guarantees that executions of **the same periodic task do not overlap**. When time is already behind, subsequent runs may start back-to-back with **little or no rest time** (beyond scheduler overhead).

There is no hard real-time guarantee for the exact 100 ms mark: the OS, CPU saturation, GC, contention, timer resolution, and available workers can all cause a run to start late.

## 4. Fixed Delay: Counting Delay After the Previous Pass Finishes

`scheduleWithFixedDelay(task, initialDelay, delay, unit)` follows this rule:

~~~text
First eligible time: t0 + initialDelay
Next run is allowed to start:
    finish(previous execution) + delay
~~~

If an execution takes 250 ms and delay is 100 ms, ideal runs start at 0, 350, 700, 1050 ms.

~~~text
delay=100 ms, each run=250 ms (idealized illustration)

Run D1:         [========= 250 ms =========]
Rest:                                    [100 ms]
Run D2:                                         [========= 250 ms =========]
Rest:                                                                     [100 ms]
Run D3:                                                                   ...
~~~

It is not that "fixed delay tries to maintain 100 ms between two starts." It commits to a **scheduled minimum wait between finish and the next start** (CPU scheduling may make the actual wait longer).

When a task is slow, the actual frequency of fixed delay drops with execution duration. This is suitable for:

- Polling that needs to wait after the previous request finishes.
- Cleanup that should not run back-to-back aggressively.
- I/O-bound tasks that need a rest interval to reduce downstream pressure.
- Cases where two consecutive invocations must not run closely together when an invocation is delayed.

Fixed delay also does not allow the same periodic task to overlap itself.

## 5. Comparison When a Pass Runs Longer Than Period/Delay

| Criterion | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
| --- | --- | --- |
| Where is the schedule calculated from? | Nominal start marks from `initialDelay` + multiples of `period` | Finish of previous pass + `delay` |
| When duration is shorter than interval | Usually has a rest gap to stay on schedule | Waits the full delay per scheduler mechanism |
| When duration is longer than interval | Next pass may start late, almost right after the previous one finishes | Still waits an extra delay after the previous pass finishes |
| Self-overlap on the same periodic task? | **No** | **No** |
| Preserves exact absolute wall-clock marks? | No, relative scheduling only; subject to jitter | No, subject to jitter |
| Frequency under overload | May bunch passes closely together, causing continuous pressure | Naturally decreases because each pass has a rest gap |
| Suitable when | You want to follow a periodic cadence, e.g., roughly even sampling | You want to avoid bunched runs, e.g., polling and cleanup |
| Drawbacks to watch | Accumulated lag, back-to-back runs without rest | Schedule drift based on each execution's duration |

In many cases, **fixed rate does not "skip" each late mark in the way you might assume**; it continues based on the nominal mark sequence. However, the API does not promise a fixed number of ticks completed by a fixed wall-clock time. Do not use `numberOfRuns == elapsed/period` to prove correctness under all scheduling/load conditions.

## 6. Example 1 — Deterministic Time Model to Understand the Difference

Before writing a program with real threads and clocks, you can compute the **idealized timestamps** to distinguish the two rules. The following example does not use a real scheduler; it simulates a periodic task that **always** takes 250 ms with a 100 ms period/delay.

Create `PeriodicTimelineModel.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;

public class PeriodicTimelineModel {
    public static void main(String[] args) {
        long durationMs = 250;
        long intervalMs = 100;
        int iterations = 4;

        List<Long> rateStarts = new ArrayList<>();
        long nextNominalRate = 0;
        long previousRateFinish = 0;

        for (int i = 0; i < iterations; i++) {
            long actualStart = Math.max(nextNominalRate, previousRateFinish);
            rateStarts.add(actualStart);
            previousRateFinish = actualStart + durationMs;
            nextNominalRate += intervalMs;
        }

        List<Long> delayStarts = new ArrayList<>();
        long nextDelayStart = 0;

        for (int i = 0; i < iterations; i++) {
            delayStarts.add(nextDelayStart);
            long finish = nextDelayStart + durationMs;
            nextDelayStart = finish + intervalMs;
        }

        System.out.println("fixed rate starts (ms) = " + rateStarts);
        System.out.println("fixed delay starts (ms) = " + delayStarts);
    }
}
~~~

Run:

~~~bash
javac PeriodicTimelineModel.java
java PeriodicTimelineModel
~~~

**Exact** stdout:

~~~text
fixed rate starts (ms) = [0, 250, 500, 750]
fixed delay starts (ms) = [0, 350, 700, 1050]
~~~

**Explanation:** Fixed rate has scheduled marks at 0, 100, 200, 300 ms, but each pass takes 250 ms, so the next pass is already eligible by the time the current pass completes. Fixed delay adds 100 ms **after each completion**. Both models execute only **one pass at a time**.

This is an idealized model **without scheduler jitter, executor queues, GC, preemption, or multi-worker systems**. The model's stdout is completely deterministic, whereas absolute timestamps in real applications do not have the same guarantee.

## 7. How Far Does the "No Self-Overlap" Rule Apply?

The Java API `ScheduledThreadPoolExecutor` states explicitly: successive executions of a task scheduled via `scheduleAtFixedRate` or `scheduleWithFixedDelay` **do not overlap**; the effects of one execution *happen-before* the effects of the next, even if the executions are performed by **different worker threads**.

This has several consequences:

1. If invocation `A1` of a periodic schedule has not finished yet, invocation `A2` **cannot start overlapping** `A1` from that schedule alone.
2. Whether the scheduler has `corePoolSize=4` or `corePoolSize=32` **does not change** rule 1.
3. The next invocation may be executed by a different thread, so do not rely on `Thread.currentThread().getName()` staying the same.
4. Runs are coordinated for memory visibility via the *happens-before* relationship between successive executions.
5. Two **different** periodic schedules can run concurrently; there is no global exclusion across all tasks in the scheduler.
6. If an application **schedules the same Runnable object twice**, it creates **two independent periodic futures**; invocations from the two schedules can overlap. Sharing the same `Runnable` reference does not mean sharing the same periodic task schedule.
7. A periodic task submits a child task to another pool and returns; **the asynchronous work of the child task** may still be running when the next invocation starts. The scheduler only prevents overlap of **the execution body of the scheduled Runnable itself**, and does not automatically track downstream tasks.

### Distinguishing "No Overlap" from "No Synchronization Needed"

If only one periodic schedule accesses state that no other thread uses, non-overlapping invocations prevent internal reentrancy. However, if:

- External readers read the same mutable state,
- Another scheduled task also modifies the state,
- Concurrent handlers arrive from another API,
- The task hands off work to an asynchronous child task,

then **race conditions can still occur**. You must design thread confinement, locks, atomic variables, or immutable snapshots according to the actual scope.

## 8. Example 2 — Confirming a Periodic Task Does Not Self-Overlap in a Multi-Worker Pool

To avoid using `Thread.sleep` and guessing scheduler behavior, use latches to hold an invocation in a controlled state. While the first invocation remains blocked, another task can still run on another worker in the same pool.

Create `PeriodicNoOverlapDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicNoOverlapDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(4);

        CountDownLatch firstEntered = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch otherTaskRan = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumActive = new AtomicInteger();
        AtomicInteger runs = new AtomicInteger();

        ScheduledFuture<?> periodic = pool.scheduleAtFixedRate(() -> {
            int nowActive = active.incrementAndGet();
            maximumActive.accumulateAndGet(nowActive, Math::max);
            int invocation = runs.incrementAndGet();

            try {
                if (invocation == 1) {
                    firstEntered.countDown();
                    releaseFirst.await();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        }, 0, 1, TimeUnit.MILLISECONDS);

        try {
            firstEntered.await();

            pool.schedule(otherTaskRan::countDown,
                    0, TimeUnit.MILLISECONDS);
            otherTaskRan.await();

            System.out.println("runs while first blocked = " + runs.get());
            System.out.println("maximum active = " + maximumActive.get());
            System.out.println("other task completed = true");

            System.out.println("cancelled = " + periodic.cancel(true));
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Run:

~~~bash
javac PeriodicNoOverlapDemo.java
java PeriodicNoOverlapDemo
~~~

Stdout when there is no external interruption:

~~~text
runs while first blocked = 1
maximum active = 1
other task completed = true
cancelled = true
~~~

**Why can we trust this result?**

- `firstEntered.await()` proves the first run has entered the Runnable and is waiting on `releaseFirst`.
- While the first run has not returned, that periodic schedule cannot run a second invocation, even though the pool has 4 workers and the period is only 1 ms.
- **Another** task enqueued with 0 delay still runs on a free worker, proving the pool is not globally exclusively locked.
- Main cancels the periodic Future while the first run is still held, then `finally` releases the latch and stops the pool; there is no chance for a second invocation to succeed.
- `maximumActive == 1` at the time of inspection is an experimental observation; the general guarantee of non-overlap comes from the API contract, not from a single stress test.

**Do not hold blocking latches in a production periodic job** just for testing. In real systems, use timeouts and alerts if a task stops making progress; avoid locking critical resources while waiting for another thread that also needs those resources.

## 9. Fixed Rate Under Overload: Handling Late Marks Without "Parallel Catch-Up"

Suppose the period is 100 ms, but an execution waits on the network for 2 seconds. During those 2 seconds, many nominal marks pass. With fixed rate:

- It does not spawn 20 copies of **the same periodic Future** across 20 workers to "catch up."
- The next run can start late once the previous run finishes.
- Subsequent runs remain tied to the original mark sequence; if still behind, they may restart very quickly.
- Bunched runs after a stall can keep **downstream under continuous load**, with no rest time to recover.
- There is no commitment that the total number of runs corresponding to elapsed marks will complete within a bounded time.

A data-reading fixed-rate task may need a **skip stale work** or **coalesce** policy: instead of trying to process every late update according to scheduler logic, the code checks the current snapshot itself and only performs work that is still useful. If you need a durable event stream with per-event processing, periodic scheduling is not a durable business queue.

Do not use fixed rate expecting it to limit concurrency by itself. It limits **overlap of that schedule itself**, not **total work** if the task calls `submit` to push more work to another executor.

## 10. Fixed Delay When Tasks Run Long

With fixed delay, if an execution takes 2 seconds and delay=100 ms, the next run becomes eligible only after the execution finishes plus 100 ms. This:

- Creates a **real rest interval between two invocations**, per the scheduling mechanism.
- Avoids firing invocations back-to-back with near-zero rest when a pass runs late.
- Is easier to reason about for polling ("wait a bit and try again after the previous one finishes").
- Causes start frequency to vary with processing duration rather than keeping a fixed start cadence.

Fixed delay **does not** set a deadline on duration. If an invocation hangs forever, the next invocation never runs; the scheduler does not automatically interrupt an invocation just because the delay has passed. You need I/O timeouts, cancellation, watchdogs, or other policies if you want to bound execution time.

If you want to "retry 100 ms after receiving a response," fixed delay fits well. If you want to "try to sample near every minute by wall-clock time," you must analyze fixed rate, clock alignment, latency, and missed sampling separately.

## 11. Example 3 — Checking the Delay Gap After an Invocation Finishes

The example below runs **for real** with a scheduler and only prints a **guaranteed ordering assertion**, not random timestamps. One simulated work pass takes about 70 ms; the delay between passes is 20 ms. After two passes, we check the interval from near the end of pass 1 to the start of pass 2.

Create `FixedDelayGapDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class FixedDelayGapDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        AtomicInteger runs = new AtomicInteger();
        AtomicLong firstEnd = new AtomicLong();
        AtomicLong secondStart = new AtomicLong();

        ScheduledFuture<?> future = pool.scheduleWithFixedDelay(() -> {
            int iteration = runs.incrementAndGet();
            long start = System.nanoTime();
            if (iteration == 1) {
                try {
                    // Only simulates slow work; not used to
                    // prove schedule positions using absolute timestamps.
                    Thread.sleep(70);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                firstEnd.set(System.nanoTime());
            } else if (iteration == 2) {
                secondStart.set(start);
                secondStarted.countDown();
            }
        }, 0, 20, TimeUnit.MILLISECONDS);

        try {
            secondStarted.await();
            long observedGapNs = secondStart.get() - firstEnd.get();
            System.out.println("at least two runs = " + (runs.get() >= 2));
            System.out.println("gap >= 20 ms = "
                    + (observedGapNs >= TimeUnit.MILLISECONDS.toNanos(20)));
        } finally {
            future.cancel(true);
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Run:

~~~bash
javac FixedDelayGapDemo.java
java FixedDelayGapDemo
~~~

Stdout when the task is not interrupted externally:

~~~text
at least two runs = true
gap >= 20 ms = true
~~~

The scheduler computes the next eligible time **after the previous callback returns**; `firstEnd.set` happens right before returning, so the measured gap to the start of pass 2 cannot be smaller than the 20 ms delay under normal JVM semantics and a monotonic clock. The actual elapsed number may be larger due to the scheduler or GC; the example intentionally prints only the threshold condition, without hard-coding "90 ms".

**Testing limitation:** A real-world timing benchmark requires multiple samples, warmup, and a proper environment. `Thread.sleep(70)` here only creates a duration longer than the delay for illustration, not a technique to guarantee an exact 70 ms or how to coordinate threads in production.

## 12. Multi-Worker Pool: Two Different Periodic Schedules Can Still Overlap

The no-self-overlap rule **does not create a global mutex** for the scheduler. A scheduler with two or more workers can run task A and task B concurrently.

### Example 4 — Two Different Periodic Schedules Running Together

Create `DifferentPeriodicTasks.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DifferentPeriodicTasks {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(2);

        CountDownLatch aEntered = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        CountDownLatch bFinished = new CountDownLatch(1);
        AtomicBoolean aRunning = new AtomicBoolean();
        AtomicBoolean bObservedA = new AtomicBoolean();

        ScheduledFuture<?> a = pool.scheduleAtFixedRate(() -> {
            aRunning.set(true);
            aEntered.countDown();
            try {
                releaseA.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                aRunning.set(false);
            }
        }, 0, 1, TimeUnit.DAYS);

        ScheduledFuture<?> b = null;
        try {
            aEntered.await();
            b = pool.scheduleWithFixedDelay(() -> {
                bObservedA.set(aRunning.get());
                bFinished.countDown();
            }, 0, 1, TimeUnit.DAYS);

            bFinished.await();
            System.out.println("B ran while A active = "
                    + bObservedA.get());
        } finally {
            a.cancel(true);
            if (b != null) {
                b.cancel(true);
            }
            releaseA.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Run:

~~~bash
javac DifferentPeriodicTasks.java
java DifferentPeriodicTasks
~~~

Normal stdout:

~~~text
B ran while A active = true
~~~

Task A is holding the first worker and waiting on the latch; task B runs on the second worker and reads that flag A is still active. Two **independent** periodic tasks can overlap. What cannot happen is a second run of A starting while the first run of A has not finished, because those two belong to the same schedule `a`.

**If the same `Runnable` instance is scheduled twice**, the same conclusion applies: each schedule call creates an independent periodic job. If both jobs modify the same state, you need separate synchronization or avoid scheduling it twice.

## 13. Successive Runs Have a Happens-Before Relationship

`ScheduledThreadPoolExecutor` provides a special guarantee: even though two consecutive executions of **the same periodic task** may run on different threads, the effects of the previous run *happen-before* the next run. This ensures operations of the periodic task itself are observed in its execution order.

~~~text
Periodic schedule A:
    A1 (worker-2) -- completes --> A2 (worker-1)
        |                             ^
        +----------- happens-before --+

Periodic schedule B:
    B1 (worker-3) can run concurrently with A1;
    there is no global happens-before just because two tasks share a scheduler.
~~~

Do not infer that:

- Mutable fields of the task are automatically safe for **external readers**.
- Two different periodic tasks are serialized with each other.
- Downstream async tasks are protected just because the parent task does not overlap.
- Network/database side effects "commit" in JVM execution order if they belong to external systems and the API has not synchronized that state.
- `Runnable.run()` is always called on the same worker thread or carries the same `ThreadLocal` state.

If snapshots need to be exposed to other consumers, you still need safe publication/`volatile`, locks, queues, atomics, or immutable state as appropriate. Do not use `ThreadLocal` to store persistent state across invocations if the schedule can run on different workers.

## 14. A Run Throws an Exception: The Periodic Schedule Stops

An important characteristic of `scheduleAtFixedRate` and `scheduleWithFixedDelay`: if an execution throws an exception that **escapes `Runnable.run()`**, subsequent executions of that periodic task **are suppressed**. This is not just a single failed tick; the periodic execution chain terminates.

The `ScheduledFuture` representing that chain then completes exceptionally:

- `isDone() == true`, because the chain has terminated.
- `isCancelled() == false` if it terminated due to an exception rather than cancellation.
- `future.get()` throws `ExecutionException`, with the cause in `getCause()`.
- The scheduler may still run other scheduled tasks; **it does not mean the entire executor has shut down**.

### Example 5 — Failure on the Second Pass Stops the Schedule

Create `PeriodicFailureDemo.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        AtomicInteger count = new AtomicInteger();

        try {
            ScheduledFuture<?> future = pool.scheduleAtFixedRate(() -> {
                int n = count.incrementAndGet();
                if (n == 2) {
                    throw new IllegalStateException("boom");
                }
            }, 0, 1, TimeUnit.MILLISECONDS);

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("cause = "
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("runs = " + count.get());
            System.out.println("isDone = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Run:

~~~bash
javac PeriodicFailureDemo.java
java PeriodicFailureDemo
~~~

Stdout:

~~~text
cause = IllegalStateException
runs = 2
isDone = true
isCancelled = false
~~~

At invocation 2, an unchecked exception escapes the body, and the periodic execution chain **does not continue**. A `get()` waiting on the periodic Future is released with an `ExecutionException` (instead of waiting forever). This is easy to miss if a program schedules a job and ignores the `ScheduledFuture`.

### Catch Exceptions or Let the Schedule Stop?

Decide based on business semantics:

- **Fail-fast:** if an error leaves state invalid, let the exception escape to stop the schedule, report the error, and wait for an operator/coordinator.
- **Continue after a recoverable error:** catch known exceptions, record the failure, handle valid retry/backoff, and return normally so the scheduler allows the next pass.
- **Do not swallow everything:** catching `Throwable` indiscriminately and continuing can hide serious `Error`s; unbounded logging/retrying can also overwhelm the system.
- **Interrupt handling:** if `InterruptedException` occurs during a blocking call, consider restoring the interrupt flag and exiting per policy; do not treat shutdown as an error to retry immediately.

An illustrative wrapper:

~~~java
// Snippet inside a scheduled Runnable; not a standalone program.
try {
    pollOnce();
} catch (RecoverableDomainException e) {
    recordFailure(e);
    // Return so the next run is allowed to execute.
}
~~~

An exception thrown by `recordFailure` can still stop periodic execution. Track both **last successful run** and **failure count** in a controlled place, rather than only checking whether the executor is alive.

## 15. ScheduledFuture: State, get, and Cancellation

The two periodic methods return a `ScheduledFuture<?>`. This handle represents **the entire periodic execution chain**, not a new Future created for each callback invocation.

| Moment | `isDone` | `isCancelled` | `get()` |
| --- | --- | --- | --- |
| Waiting for initial delay | Usually false | false | Waits |
| An invocation is running or schedule is repeating normally | false | false | **Keeps waiting** (does not return after one run) |
| An invocation throws an escaping exception | true | false | `ExecutionException` |
| `cancel` succeeds | true | true | `CancellationException` |
| Executor shuts down and periodic schedule is cancelled per policy | true | true (if Future was cancelled) | `CancellationException` |

`getDelay(unit)` reflects the remaining time until the task is eligible to run per the scheduler mechanism; it does **not** indicate callback duration or a start-time guarantee. For an overdue periodic task, the delay may be 0 or negative depending on timing/API, but you cannot infer that multiple copies are running concurrently.

### Cancellation Does Not Force a Running Callback to Stop Immediately

- `future.cancel(false)`: requests stopping future runs, without requesting an interrupt of the current invocation. The Future may be cancelled while the running callback continues working.
- `future.cancel(true)`: requests stopping future runs and **attempts to interrupt** the running callback if the implementation allows. The task must cooperate with interruption/timeouts to stop early safely.
- `isDone()==true` after cancel is not proof that all in-flight side effects have finished, nor is it a transaction rollback.
- `get(timeout)` only bounds **the caller's wait**, and does not cancel the schedule. For a normal running periodic Future, `get(timeout)` will easily time out because the Future has no normal result per cycle.

If you need to know when a specific run has finished processing, use a `CountDownLatch`, per-run `CompletableFuture`/acknowledgment, metrics, or a dedicated state machine. Do not misuse `ScheduledFuture.get()` as a "wait until next tick finishes" mechanism.

## 16. Example 6 — Cancelling a Periodic Task Before It Starts

Create `CancelPeriodicDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelPeriodicDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        pool.setRemoveOnCancelPolicy(true);

        AtomicInteger runs = new AtomicInteger();

        try {
            ScheduledFuture<?> future = pool.scheduleAtFixedRate(
                    runs::incrementAndGet,
                    1, 1, TimeUnit.DAYS);

            System.out.println("cancelled = " + future.cancel(false));
            System.out.println("done = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());
            System.out.println("queued entries = " + pool.getQueue().size());

            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }

        System.out.println("runs = " + runs.get());
    }
}
~~~

Run:

~~~bash
javac CancelPeriodicDemo.java
java CancelPeriodicDemo
~~~

Stdout:

~~~text
cancelled = true
done = true
isCancelled = true
queued entries = 0
get = CancellationException
runs = 0
~~~

The initial delay is one day, so cancelling right after scheduling happens before the first run. `setRemoveOnCancelPolicy(true)` ensures cancelled delayed tasks are not kept in the queue unnecessarily per the `ScheduledThreadPoolExecutor` implementation.

**Memory retention note:** By default, `ScheduledThreadPoolExecutor` can retain cancelled delayed tasks in the work queue until their scheduled time arrives, even though they will not run; the remove-on-cancel policy frees them sooner. Do not confuse it with methods on a regular `ThreadPoolExecutor`.

## 17. `ScheduledThreadPoolExecutor` and Worker Count

`Executors.newScheduledThreadPool(corePoolSize)` creates a scheduler with the requested number of core workers. Unlike `ThreadPoolExecutor` with an arbitrary bounded queue, `ScheduledThreadPoolExecutor` uses an **effectively unbounded** delayed work queue at the application level; the documentation notes it acts as a **fixed-sized pool of `corePoolSize` threads** and adjusting `maximumPoolSize` has no useful effect.

Consequences:

- Multiple delayed tasks or different periodic schedules may become eligible at the same time and have to **wait for a free worker**.
- If `corePoolSize=1` and task A blocks, task B can be delayed even if B has an earlier deadline.
- If `corePoolSize=4`, a single periodic task A running too long still **does not self-overlap**; however, tasks B, C, and D can use other workers.
- If there are many periodic schedules, having a queue does not make worker count infinite; total load is still bounded by CPU, I/O, and downstream capacity.
- Scheduled future/queue entries can retain object graphs and increase memory pressure if registered schedules grow unchecked.

**Do not increase `maximumPoolSize` expecting to fix a backlog** in `ScheduledThreadPoolExecutor`; instead measure core worker utilization, invocation duration, number of independent schedules, queue wait, and downstream saturation. Increasing `corePoolSize` is only appropriate when tasks are independent and external resources can handle increased concurrency.

### Do Not Arbitrarily Reduce Core Pool to 0

The `ScheduledThreadPoolExecutor` documentation recommends generally not setting `corePoolSize=0` or enabling core thread timeouts because it can leave the scheduler with no thread ready to process tasks when due. This is a different tradeoff from executors dedicated to request bursts.

## 18. Shutdown: Which Policies Affect Periodic Tasks?

`ScheduledExecutorService` manages tasks, while `ScheduledThreadPoolExecutor` has specific policies for pending schedules:

- `setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)`: determines whether registered periodic tasks **continue** after `shutdown()`. Default is **false**, meaning existing periodic tasks do not continue after shutdown.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)`: determines whether already-submitted one-shot delayed tasks **execute** after `shutdown()`. Default is **true**.
- `setRemoveOnCancelPolicy(boolean)`: requests immediate removal of cancelled tasks from the queue per the implementation's policy, avoiding retaining them until their scheduled time.
- `shutdownNow()`: best-effort interrupts running tasks and returns tasks that have not started; does not guarantee a running body cooperates to stop immediately.
- `awaitTermination(timeout, unit)`: waits for the executor to terminate after shutdown; the method itself does not cancel or run additional tasks.

Coordinated shutdown example:

~~~java
// Illustrative snippet inside a method that may throw InterruptedException.
periodicFuture.cancel(true);
scheduler.shutdown();

if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
    scheduler.shutdownNow();
    scheduler.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

If you enable `continueExistingPeriodicTasksAfterShutdownPolicy(true)` without actively cancelling schedules, the scheduler may keep running periodic tasks and fail to terminate as expected. Therefore, **do not configure the policy and forget to manage the handles**.

When an orderly stop is needed, typically:

1. Stop registering new periodic tasks.
2. Decide explicitly whether running tasks should be **waited on to finish** or **requested to interrupt**.
3. Cancel handles according to business policy.
4. Call `shutdown()` and wait via `awaitTermination` with a timeout.
5. Use `shutdownNow()` as an escalation path if needed, and record any remaining state.
6. Release I/O/database resources **after confirming** tasks are no longer using them or via a synchronized shutdown protocol.

A successful cancel signal alone does not prove the body has stopped; if a task is blocked in non-interruptible I/O, you may need deadlines/socket timeouts or another stopping mechanism.

## 19. When a Periodic Task Submits Child Tasks: Indirect Overlap

A design that easily causes confusion:

~~~java
// Snippet, not a standalone program.
scheduler.scheduleAtFixedRate(() -> {
    workerPool.submit(this::longOperation);
}, 0, 100, TimeUnit.MILLISECONDS);
~~~

The scheduled Runnable only performs **submit and returns** quickly. Thus the scheduler **does not overlap the submit Runnable**, but the submitted `longOperation` tasks can **run in parallel** or **pile up** in `workerPool`.

Consequences:

- `longOperation` can run concurrently even though the periodic scheduler strictly obeys no-overlap.
- If `workerPool` has an unbounded queue, backlog grows when production rate exceeds completion rate.
- Cancelling `ScheduledFuture` only stops **future submissions**, and does not automatically cancel child tasks already accepted by `workerPool`.
- Calling `shutdown()` on the scheduler does not shut down `workerPool` if the application created two independent executors.
- If child tasks mutate shared state, appropriate atomicity, idempotency, locks, or a serial executor are required.

To prevent business-level overlap, either **keep all processing inside the scheduled Runnable** and use fixed delay; or place a gate such as `Semaphore.tryAcquire()`/`AtomicBoolean.compareAndSet(false,true)` around the entire asynchronous operation, releasing it exactly once in every branch. If the gate is released too early (right after `submit`), overlap still occurs.

### Non-Overlap Pattern with AtomicBoolean (Illustrative)

~~~java
// Structural snippet inside a class with corresponding fields.
AtomicBoolean inFlight = new AtomicBoolean();

void tick() {
    if (!inFlight.compareAndSet(false, true)) {
        return; // Skip this turn when the previous work has not finished.
    }

    try {
        doWorkSynchronously();
    } finally {
        inFlight.set(false);
    }
}
~~~

This pattern only works if the work completes directly inside `doWorkSynchronously()`. If replaced with `workerPool.submit(...)` where `finally` always releases as soon as `submit` returns, the gate becomes meaningless. For async work, release only after the work **actually** completes, fails, or is cancelled, and ensure the gate does not leak if the task never starts. That is a separate lifecycle/ownership problem.

## 20. Tasks with Long I/O: Designing Cancellation and Timeouts

"No overlap" does not solve a job that **hangs forever**. If an invocation waits indefinitely for a network response:

- Fixed rate will not spawn a new invocation to replace the stuck one.
- Fixed delay will not run the next pass either.
- The scheduler pool can lose a worker for a long time.
- `cancel(true)` may not immediately interrupt a non-interruptible I/O API.
- Other independent tasks can still run if workers remain in the pool, though shared resources may be affected.

Checklist:

- Set socket/connect/read timeouts or API-specific deadlines.
- Support interruption wherever possible; do not swallow `InterruptedException`.
- Use try-with-resources/`finally` to clean up task-owned resources.
- Do not hold a shared lock across long I/O.
- Track **start time, duration, last successful run, error count, cancellation latency**.
- If an invocation is overdue, explicitly choose to cancel, skip, retry/backoff, or report an error.
- Ensure operations are idempotent if retries may happen after timeouts or process restarts.
- Do not assume cancel rolls back already-committed side effects.

For heavy periodic callbacks, consider separating "deciding whether work is needed" from actual I/O, while redesigning work coordination if splitting into asynchronous child tasks.

## 21. Is Fixed Rate Equivalent to Cron or an Absolute Clock?

No. `scheduleAtFixedRate` in Java SE schedules by **relative delays/periods**; it is not a cron schedule with calendar semantics such as "00:00 every day in timezone X". Other concerns include:

- Timezones, DST, and local clock jumps backward/forward.
- Leap seconds, NTP sync, and system clock changes.
- Schedules like "first day of the month", "Monday at 9:00", or "after each calendar day".
- Process restarts, losing schedules when the JVM stops, and replaying missed runs.
- Multiple JVMs/instances running the same job.

`ScheduledExecutorService` **does not provide a distributed single-leader lock or durable scheduling**. If multiple JVMs register the same periodic job, each JVM can run its own job and cause overlap on the same external data. If you need a business schedule that "runs only once across the entire cluster," you need a coordinator/lease/lock/durable scheduler protocol at the appropriate layer; do not infer it from no-overlap **within a single periodic Future**.

When you want to follow wall-clock time, compute the next target from `ZonedDateTime`/appropriate calendar rules, convert it to a relative delay, and handle clock changes/holidays/DST as required; do not just set `period=24 hours` and assume it means "every day at 09:00" forever.

## 22. Observing and Testing Long-Running Task Behavior

### A. Production Observability

Useful metrics:

| Metric | Meaning |
| --- | --- |
| Last start / last finish | Shows whether the current invocation is making progress |
| Per-run duration, p95/p99 | Reveals which tasks exceed their period/delay |
| Time since last successful finish | Detects jobs that silently stopped due to an exception |
| Number of failures | Distinguishes a live scheduler from a succeeding job |
| Late start/drift | Measures how far a fixed-rate schedule lags behind nominal marks |
| Missed business deadlines | More important than raw JVM tick counts |
| Pool active threads / queue size | Reveals contention across different scheduled tasks |
| Cancellation-to-stop latency | How long after Future cancellation the body actually stops |
| Downstream saturation | Whether periodic tasks are overloading the DB/API |

A periodic Future with `isDone=false` does not prove "the job is healthy": it may be stuck in an unfinished invocation. Measure duration/last finish. Conversely, `isDone=true` does not mean the job succeeded; it could be due to an exception or cancellation.

### B. Use Latches to Test Overlap Instead of Guessing Scheduling

A reliable test should:

1. Start an invocation and hold it at a controllable point.
2. Confirm the invocation has entered the body using a latch.
3. Use another worker/coordination to give an independent task a chance to run.
4. While the first invocation is still held, verify the same-schedule run count does not increase.
5. Release the latch or cancel in `finally` so the test does not hang.
6. Wait for executor termination (with a timeout) before leaving the test.
7. Separate verifying the **non-overlap contract** from measuring **timing jitter**.

Do not write a test with `Thread.sleep(110)` and assume the second invocation must have run or that the OS must schedule at exactly 110 ms. Scheduling provides no hard deadlines; stress tests only support evidence under observed conditions and do not replace API documentation.

### C. When Comparing Fixed Rate and Fixed Delay

Do not just count runs in 1 second and draw conclusions. If task duration varies, invocation counts depend on scheduler jitter, GC, and resource contention. Measure **start/finish timestamps** with a monotonic clock (e.g., `System.nanoTime()`) and compute:

- For fixed rate: spacing between starts relative to the nominal period.
- For fixed delay: spacing between **previous finish** and **next start** relative to the delay.
- For both: whether the same periodic Future ever has two active invocations; by contract it does not.
- Amount of new work generated by each invocation, especially when child tasks/worker queues are involved.

## 23. Common Mistakes

| Mistake | Why it is dangerous / how to fix |
| --- | --- |
| "Fixed rate will overlap the same task when delayed." | No, successive executions in the same periodic schedule do not overlap. |
| "The pool has 8 workers so 8 runs of the same task run concurrently." | The pool can run **eight different tasks**, without violating per-schedule no-overlap. |
| "Fixed delay means 100 ms between two start times." | Delay is measured from **previous finish** to next eligible start. |
| "Fixed rate always waits a full period after finishing." | When behind, the next pass can start very soon, almost right after the previous one. |
| "Each overdue period spawns a parallel task copy." | Not the contract of either periodic scheduling method. |
| "Two schedule calls with the same Runnable are one task." | They are two independent schedules and can overlap each other. |
| "The previous pass ran on worker-1 so the next pass will too." | Implementations may use another worker; do not rely on ThreadLocal across passes. |
| "Scheduler no-overlap also protects asynchronous child tasks." | No; child tasks have their own lifecycle and can overlap/queue in another pool. |
| "Periodic Future.get() returns after one run." | Normal periodic schedules have no normal per-run return value. |
| "A job throws an exception but the scheduler keeps running the next pass." | Uncaught exceptions suppress subsequent runs. |
| "Future cancelled means the body stopped cleanly." | Cancel does not guarantee the worker stopped immediately or side effects rolled back. |
| "Increasing maximumPoolSize of ScheduledThreadPoolExecutor." | With an unbounded delayed queue, max pool size does not help as many expect. |
| "shutdown() always stops all one-shot and periodic schedules the same way." | Delayed and periodic tasks have different continuation policies. |
| "A 24h fixed rate is cron at 9:00 every day." | Calendar/DST and relative periods are different problems. |
| "Per-JVM no-overlap means cluster-wide no-overlap." | ScheduledExecutorService has no distributed coordination. |
| "No exceptions means the job is healthy." | The task may be hung; monitor last successful finish and duration. |

## 24. Self-Check Questions

**Question 1.** A fixed-rate task has a 100 ms period, and each execution takes 250 ms. Can two invocations of the same `ScheduledFuture` run concurrently?  
**Answer:** No. The next pass may be late and start right after the previous one, but they do not overlap.

**Question 2.** With the idealized model above, what start marks do 100 ms fixed rate and fixed delay produce?  
**Answer:** Fixed rate can start at 0, 250, 500, 750 ms; fixed delay starts at 0, 350, 700, 1050 ms if each pass always takes 250 ms.

**Question 3.** A fixed-delay periodic task has a 250 ms duration and a 100 ms delay. Is the gap between two **starts** at least 100 ms?  
**Answer:** Yes, and typically the gap is previous duration + delay + scheduling overhead, roughly 350 ms in the idealized model.

**Question 4.** Does `Executors.newScheduledThreadPool(4)` allow tasks A and B to run concurrently?  
**Answer:** Yes, if they are **two different schedules** and workers are available. It does not make A overlap the next A.

**Question 5.** Do two calls to `scheduleAtFixedRate(sameRunnable, ...)` create a single periodic schedule?  
**Answer:** No. Two independent Futures can invoke the same Runnable concurrently.

**Question 6.** An execution throws a `RuntimeException` that escapes the Runnable. Does the next pass run automatically?  
**Answer:** No. Subsequent executions are suppressed; the Future completes exceptionally and `get()` throws `ExecutionException`.

**Question 7.** A periodic Future has run 10 times and has not been cancelled. Does `get()` return normally?  
**Answer:** No. A periodic Future represents the whole schedule and normally has not completed.

**Question 8.** `cancel(true)` is called while an invocation is waiting on network I/O. Is the network call guaranteed to stop immediately?  
**Answer:** No. It only attempts to interrupt; you need I/O timeouts and cooperative cancellation.

**Question 9.** Can fixed rate put heavy pressure on downstream when an execution is delayed?  
**Answer:** Yes, subsequent invocations can run very close together; fixed delay waits again after each finish.

**Question 10.** If a periodic Runnable only calls `submit(longTask)` and returns, is `longTask` still guaranteed not to overlap?  
**Answer:** No. The scheduler only prevents overlap of the Runnable's own invocations, while child tasks in another pool can run concurrently.

**Question 11.** What can `setContinueExistingPeriodicTasksAfterShutdownPolicy(true)` affect?  
**Answer:** Existing periodic tasks can continue after `shutdown`; you must actively cancel them so the scheduler can terminate.

**Question 12.** Is a 24-hour fixed-rate period the same as "every day at 09:00 in timezone X"?  
**Answer:** No. A relative period does not replace calendar rules/DST.

## Java SE References

- [`ScheduledExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): `scheduleAtFixedRate`/`scheduleWithFixedDelay`, initial delay, period/delay, exception suppression.
- [`ScheduledThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): non-overlapping successive executions, happens-before, core pool, remove-on-cancel, shutdown policies.
- [`ScheduledFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): handle for delayed/periodic jobs.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `isDone`, `get`.
- [`Executors` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): `newScheduledThreadPool` factory.
- [`TimeUnit` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): time conversion and representation.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): deterministic test coordination.

**Remember:** `scheduleAtFixedRate` tracks **scheduled start marks**, so when delayed, passes can run back-to-back; `scheduleWithFixedDelay` always waits an extra **delay after the previous pass finishes**. **Neither overlaps executions of the same periodic task**, though other schedules, asynchronous child tasks, or other JVMs can still compete for resources.
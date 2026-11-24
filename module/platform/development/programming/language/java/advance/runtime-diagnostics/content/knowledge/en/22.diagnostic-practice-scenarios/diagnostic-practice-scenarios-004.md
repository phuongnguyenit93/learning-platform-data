# 22.4 Reproducing Pool Saturation and Separating Queue Wait Time from Run Time

> **Module:** Java Advance – runtime-diagnostics, section **22. Integrated Practice**. This Java 17+ lab uses a `ThreadPoolExecutor` with one worker and a bounded queue to create a controlled saturation state. Using `submit → start → finish` timestamps, we separate **wait-for-execution latency** from **in-flight execution latency**, distinguishing overload, backlog, slow tasks, and appropriate remedies.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain how `corePoolSize`, `maximumPoolSize`, `BlockingQueue`, and `RejectedExecutionHandler` determine whether a task runs, queues, or is rejected.
2. Reproduce the state of **one task running + one task waiting in the queue + a third task rejected**, without relying on lucky `Thread.sleep()` timing at submission.
3. Measure **submit-to-start latency** and **run duration** separately with `System.nanoTime()`, verifying their relationship to total task latency.
4. Explain why a task taking 40 ms to run can make the caller wait 300 ms or more.
5. Use queue depth, active workers, rejections, wait/run histograms, thread dumps, JFR, and application metrics to diagnose causes of saturation.
6. Design load shedding and evidence-based tuning, without assuming "enlarge the pool" or "switch to an unbounded queue" fixes the bottleneck.

**Starting scenario:** Users report an API taking 900 ms, yet the profiler shows business processing takes only about 40 ms. If the task sat in the executor queue for nearly 850 ms waiting for a free worker, optimizing 40 ms down to 30 ms saves only 10 ms. You must measure **both phases** before choosing a fix.

## 2. Separating Three Time Intervals

For a task accepted by the pool:

```text
Caller                            ThreadPoolExecutor                    Worker
   |                                     |                                 |
   | -- submit task -------------------->|                                 |
   |    tSubmit                          | -- queue / dispatch wait ------>|
   |                                     |                         tStart ->| call()
   |                                     |                                 |  work...
   |                                     |                         tEnd   ->| finish
   | <------------------------- Future/result -----------------------------|
```

Measured using **the same monotonic clock**:

```text
submitToStartNanos = tStart - tSubmit
runNanos           = tEnd   - tStart
totalNanos         = tEnd   - tSubmit

totalNanos == submitToStartNanos + runNanos
```

- `tSubmit`: timestamp when the caller prepares to submit the task, right before `execute/submit`.
- `tStart`: first line executed inside the worker's task wrapper.
- `tEnd`: task finishes the measured portion of work.

**Exact naming:** `submitToStart` is the interval **from preparing submission to starting execution**. It usually approximates executor queue wait time, though it also includes admission, worker creation, dispatch, and scheduling overhead. If you need exact *time spent inside the queue*, instrument enqueue/dequeue directly or use a custom queue/executor. This lesson uses `submitToStart` as a practical indicator without claiming it is purely queue residence.

**`runNanos` is elapsed wall time, not CPU time consumed.** A worker that picked up a task and is calling `Thread.sleep`, waiting on DB/sockets, locks, semaphores, or the filesystem remains occupied until the task finishes. Separating **in-task waiting** differs from **waiting before a task gets a worker**.

### 2.1. `Future.get()` Is Not Queue Wait

A `future.get()` call waiting 500 ms can include:

- Time the task spent queued.
- Time after the task started working.
- Time the worker waited on network/DB inside the task.
- Scheduling and when the caller actually began waiting.

Therefore, never take `Future.get()` duration and label it `queueWaitMs`. Moreover, `Future.get(timeout)` expiring only stops the caller from waiting; the task **is not automatically cancelled**. If cancellation is needed, handle `cancel`, interruption, and resource cleanup per the application's contract.

### 2.2. End-to-End Requests Have Even More Phases

```text
request arrival
   -> ingress queue
   -> parse/auth
   -> pool admission / submit
   -> submit-to-start
   -> task run (CPU + I/O + locks + business logic)
   -> result-handling / serialization
   -> response sent
```

Client-perceived total latency can exceed `submitToStart + run`, and some stages may overlap when asynchronous. Never add measurements with **overlapping boundaries** and call the sum total request latency. Always document the exact start/end points each metric covers.

### 2.3. Tasks That Never Ran

| Status | Has `tStart`/`tEnd`? | How to Record |
| --- | --- | --- |
| Accepted and completed | Yes | `submitToStart`, `run`, `total`, outcome |
| Accepted then failed in `run` | Yes | Measure in `finally` and record `FAILED` |
| Rejected because full or shut down | **No** | Rejection count, reason, and submit-site response latency separately |
| Cancelled while still queued | No `tStart` | Separate cancellation/expiration metrics; do not force `run=0` into success latency histograms |
| `CallerRunsPolicy` runs on caller | Has start/end but **did not run on a pool worker** | Record execution location, caller latency, and backpressure separately |

## 3. How `ThreadPoolExecutor` Decides Queuing and Worker Count

`ThreadPoolExecutor` coordinates three bounds:

- **`corePoolSize`:** target number of core workers.
- **`maximumPoolSize`:** ceiling of workers usable when the queue rejects more tasks.
- **`workQueue`:** holds accepted tasks that have **not yet been dequeued by a worker**.

Key HotSpot/JDK `ThreadPoolExecutor` rules:

1. If fewer than `corePoolSize` workers are running, the executor generally prefers **creating a new worker**.
2. Once core workers are populated, the executor generally prefers **queuing the task** rather than immediately scaling up to max.
3. Only if the queue cannot accept the task does the executor try adding workers up to `maximumPoolSize`.
4. If max workers are reached and the queue refuses the task, `RejectedExecutionHandler` handles it.
5. A shut-down executor also rejects tasks; **rejection does not automatically mean saturation**.

**Lab configuration chosen:**

```text
corePoolSize = 1
maximumPoolSize = 1
queue capacity = 1
handler = AbortPolicy

Task A -> worker #1 (running/waiting on latch)
Task B -> workQueue[0] (waiting for worker #1)
Task C -> no slot or worker left -> REJECTED
```

During the steady hold window: `active workers≈1`, `queue.size()=1`, total **accepted and unfinished** tasks is 2. Queue depth is **not** 2 because running task A has already left the queue.

### 3.1. Bounded vs. Unbounded Queues

- `new ArrayBlockingQueue<>(1)` creates a queue with **an explicit single slot**; once full, additional workers may spawn if `max > core`, or tasks get rejected per policy.
- `Executors.newFixedThreadPool(n)` normally uses an **unbounded `LinkedBlockingQueue`**. While core threads are busy, new tasks keep queuing. As a result, tail latency and memory grow without immediate rejections. With an unbounded queue, `maximumPoolSize` above `corePoolSize` generally never takes effect because the queue never reports full.
- `Executors.newCachedThreadPool()` uses a different thread expansion strategy and is not bounded backpressure by default.
- `Executors.newVirtualThreadPerTaskExecutor()` on JDK 21+ does not limit business concurrency merely because virtual threads are cheaper than platform threads. Database connections, remote API limits, buffers, and memory remain finite; pair with semaphores/bulkheads/timeouts as appropriate.

A larger pool is not necessarily faster. If 200 workers wait on 10 DB connections, memory pressure, context switching, and downstream contention can get **worse**. Measure what occupies worker time.

## 4. Standalone Java 17+ Lab: One Running, One Queued, One Rejected

The following program runs purely on the JDK with no server, DB, network, or external libraries:

- `ThreadPoolExecutor(1, 1, ..., ArrayBlockingQueue<>(1), AbortPolicy)`.
- Task `first` occupies the worker and waits on a `CountDownLatch`.
- Main waits for `first` to start, then submits task `queued`.
- Main confirms the queue is full and submits a third task to trigger `RejectedExecutionException`.
- Main **holds the first task for another 250 ms**, then releases the worker; the second task works for roughly 40 ms.
- The first two tasks are measured with the same monotonic clock `System.nanoTime()`.

### 4.1. Create `PoolQueueTimingLab.java`

```java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PoolQueueTimingLab {
    record Sample(String name, long submittedAt, long startedAt, long endedAt) {
        long submitToStartNanos() { return startedAt - submittedAt; }
        long runNanos() { return endedAt - startedAt; }
        long totalNanos() { return endedAt - submittedAt; }
    }

    static Callable<Sample> measured(
            String name, long submittedAt, Callable<Void> work) {
        return () -> {
            long startedAt = System.nanoTime();
            work.call();
            return new Sample(name, submittedAt, startedAt, System.nanoTime());
        };
    }

    static void show(Sample sample) {
        System.out.printf(Locale.ROOT,
            "%s submitToStartMs=%.2f runMs=%.2f totalMs=%.2f%n",
            sample.name(),
            sample.submitToStartNanos() / 1_000_000.0,
            sample.runNanos() / 1_000_000.0,
            sample.totalNanos() / 1_000_000.0);
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException, TimeoutException {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());
        try {
            Future<Sample> first = pool.submit(measured(
                "first", System.nanoTime(), () -> {
                    firstStarted.countDown();
                    releaseFirst.await();
                    return null;
                }));

            if (!firstStarted.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            Future<Sample> queued = pool.submit(measured(
                "queued", System.nanoTime(), () -> {
                    Thread.sleep(40);
                    return null;
                }));

            boolean saturated = pool.getActiveCount() == 1
                && pool.getQueue().size() == 1
                && pool.getQueue().remainingCapacity() == 0;

            boolean thirdRejected = false;
            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException expected) {
                thirdRejected = true;
            }

            // Keep the one worker occupied while the second task waits.
            Thread.sleep(250);
            releaseFirst.countDown();

            Sample a = first.get(3, TimeUnit.SECONDS);
            Sample b = queued.get(3, TimeUnit.SECONDS);

            System.out.println("saturated=" + saturated);
            System.out.println("thirdRejected=" + thirdRejected);
            System.out.println("completed=2");
            System.out.println("queuedStartedAfterFirstEnded=" +
                (b.startedAt() >= a.endedAt()));
            System.out.println("queuedWaitPositive=" +
                (b.submitToStartNanos() > 0));
            System.out.println("latencyIdentity=" +
                (b.totalNanos() == b.submitToStartNanos() + b.runNanos()));
            show(a);
            show(b);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }
}
```

**Lab limitation:** `measured(...)` here constructs `Sample` only after a **successful** task. Because both demo tasks complete normally, it reports accurate figures. In production code, to preserve metrics when a task throws an exception you must record them inside `finally`, as shown in section 6. The line `completed=2` appears after **both `Future.get()` calls succeed**, describing the scenario's task count rather than reading `ThreadPoolExecutor.getCompletedTaskCount()` directly.

### 4.2. Compiling and Running

```bash
javac PoolQueueTimingLab.java
java PoolQueueTimingLab
```

Compiled with `javac --release 17` and verified across multiple runs on OpenJDK 24. The first six lines are logic checks verified in the test environment:

```text
saturated=true
thirdRejected=true
completed=2
queuedStartedAfterFirstEnded=true
queuedWaitPositive=true
latencyIdentity=true
```

The next two lines **vary in measured values** by machine, moment, and load. Example of an actual run:

```text
first submitToStartMs=6.82 runMs=253.72 totalMs=260.54
queued submitToStartMs=253.93 runMs=40.44 totalMs=294.37
```

This is **illustrative output from one run**, not fixed values. The key takeaway: `queued` **waited ~254 ms before starting** yet **ran for only ~40 ms**. Looking only at `runMs` misses most of the tail latency.

### 4.3. Why Do Latches Make the Test Deterministic?

`firstStarted.await(3, SECONDS)` guarantees the first task actually entered the worker before the second task is submitted. While the worker waits on `releaseFirst`, the second task must sit in the queue because the pool cannot spawn a second worker. With the capacity-1 queue full, the third task is rejected by `AbortPolicy`.

Do not use plain `Thread.sleep(100)` to *hope* the first worker starts before the second task; that race produces flaky results on slower machines/CI. `CountDownLatch` creates a repeatable synchronization boundary. The `Thread.sleep(250)` after checking saturation only **keeps the wait long enough to measure**, not to decide task ordering correctness.

`getActiveCount()` is an **estimate**, and `getQueue().size()` is a point-in-time snapshot. They remain steady in the lab only because the latch holds the worker. In live systems, a worker can finish between reading the gauge and submitting another task; never build admission logic via `if (queue.size() < capacity) submit(...)` due to the race condition.

### 4.4. Interpreting Numbers with Correct Units

For task `queued` in the sample:

```text
tSubmit -> tStart = 253.93 ms  (waiting to execute)
tStart  -> tEnd   =  40.44 ms  (task running)
tSubmit -> tEnd   = 294.37 ms  (total task latency)
```

In nanoseconds, `total = submitToStart + run` holds algebraically. When formatted to two decimal places, rounded components can sometimes differ by ~0.01 ms; **do not** conclude lost time or clock drift from rounding.

Notice `first` has `runMs≈254 ms`, yet most of it is **waiting on the latch**, not executing on CPU. From the pool's perspective, it still occupies a worker and prevents `queued` from progressing.

## 5. Reading `ThreadPoolExecutor` Runtime Metrics Properly

| API | Returned Value | Do Not Infer |
| --- | --- | --- |
| `getCorePoolSize()` | Core worker configuration | Actual busy thread count |
| `getMaximumPoolSize()` | Max worker configuration | That the pool always scales to max when core is busy |
| `getPoolSize()` | Existing worker threads right now | Active workers or task throughput |
| `getActiveCount()` | **Approximate** threads actively running tasks | CPU busy % or completed requests |
| `getQueue().size()` | Tasks waiting in the queue at observation time | Running tasks or how long the queue has waited |
| `getQueue().remainingCapacity()` | Instantaneous free slots | That the next submit is guaranteed to be accepted |
| `getLargestPoolSize()` | Highest concurrent worker count ever reached | Current latency |
| `getTaskCount()` | **Approximate** total scheduled tasks | Rejected count or task success rate |
| `getCompletedTaskCount()` | **Approximate** completed tasks | Business success or exact task count across snapshots |

**Queue depth can currently be 0 while p99 wait is still high.** For instance, a task waited 10 seconds, just got dequeued by a worker, and left the queue empty. A once-per-minute snapshot misses that past backlog; per-task `submitToStart` still reveals the long wait. Therefore use `queue.depth`, `oldestQueuedAge` (when available), and delay histograms together rather than queue depth gauges alone.

Pools serving different roles must use distinct stable names; do not mix metrics from request pools, DB connection pools, message consumer pools, and schedulers. Attach `poolName`, `taskType`, and `outcome` from **finite** sets, never request IDs as time-series labels.

## 6. Two-Phase Instrumentation in Real Applications

### 6.1. Minimum Measurement Points

```text
tSubmitted = System.nanoTime()       // right before execute/submit
tStarted   = System.nanoTime()       // start of wrapper inside worker
... instrumented work ...
tFinished  = System.nanoTime()       // finally

submitToStart = tStarted - tSubmitted
execution     = tFinished - tStarted
total         = tFinished - tSubmitted
```

Use `System.nanoTime()` for **durations** because it measures elapsed time inside the same process; `System.currentTimeMillis()` is wall-clock time subject to NTP/clock adjustments. If you need to correlate timelines with JFR/logs, record a **separate** wall-clock timestamp rather than mixing it into latency subtraction.

Place `tSubmitted` right near `execute/submit`. If the caller previously waited on an admission semaphore or an HTTP request queue, that time lies **outside** submit-to-start and needs its own metric. Place `tStarted` at the start of the task wrapper and `tFinished` in `finally` for both success and failure. With async continuations, define clearly which unit of work is measured; never blindly equate submit-to-start with end-to-end user request latency.

### 6.2. Illustrative Snippet with `finally`

This is a **code snippet requiring application-defined** `executor`, `metrics`, and `performBusinessOperation()`; it is not a standalone program:

```java
long submittedAt = System.nanoTime();

try {
    executor.execute(() -> {
        long startedAt = System.nanoTime();
        String outcome = "SUCCESS";
        try {
            performBusinessOperation();
        } catch (RuntimeException failure) {
            outcome = "FAILED";
            throw failure;
        } finally {
            long finishedAt = System.nanoTime();
            metrics.recordSubmitToStart(startedAt - submittedAt);
            metrics.recordRun(finishedAt - startedAt, outcome);
        }
    });
} catch (RejectedExecutionException rejection) {
    metrics.incrementRejected("submission_rejected");
    throw rejection;
}
```

Key point: an accepted task that **fails during execution** must still record its duration; a task **rejected before running** is only visible at the submit site. `RejectedExecutionException` can also occur when the executor has already shut down, so do not automatically tag reason `"saturated"` without checking runtime lifecycle. A metric callback inside `finally` could throw and mask the original exception if poorly implemented; use a safe, non-blocking metrics library with no business side effects.

If you need to cover `Error`, checked exceptions, interrupts, and cancellation, use a broader wrapper/outcome mapping while preserving original exceptions. With `ExecutorService.submit()`, tasks are typically wrapped in a `FutureTask`; `afterExecute(Runnable, Throwable)` may receive `Throwable=null` even when `Future.get()` later throws `ExecutionException`. Do not count failures solely from `afterExecute`'s `Throwable` parameter without understanding submission wrapping.

### 6.3. Still Distinguish Worker Time from CPU Time

A started task can have:

```text
submit-to-start =   3 ms
run             = 900 ms
  CPU           =  10 ms
  wait DB       = 880 ms
  serialization =  10 ms
```

Here `run` is high because the worker is occupied by **I/O wait**, not queuing. Adding workers might just increase tasks waiting on the DB; check pool acquire metrics, DB query latency, socket timeouts, locks/parks, and CPU profiling.

Conversely:

```text
submit-to-start = 850 ms
run             =  40 ms
```

signals that pre-worker waiting dominates. However, saturation can stem from an **arrival spike** or **other tasks** running long; measure all task types, not just the task reported as slow.

## 7. Observing Saturation with Metrics, Thread Dumps, and JFR

### 7.1. Minimum Metric Set

| Metric | Type | Used For |
| --- | --- | --- |
| `executor.active` | Gauge | Approximate count of workers running tasks |
| `executor.pool.size` | Gauge | Existing worker count |
| `executor.queue.depth` | Gauge | Current backlog |
| `executor.queue.capacity` | Gauge/config | Effective capacity limit |
| `executor.submitted` | Counter | Submission attempts by the application |
| `executor.accepted` | Counter | Tasks accepted under policy |
| `executor.rejected` | Counter | Rejections; split shutdown vs. overload when verifiable |
| `executor.submit_to_start` | Histogram/Timer | p50/p95/p99 wait before starting |
| `executor.run` | Histogram/Timer | p50/p95/p99 inside worker, both success/failure with explicit semantics |
| `executor.total` | Histogram/Timer | Task submit-to-end latency |
| `executor.oldest_queued_age` | Gauge when measurable | Oldest queued task age, useful when queues grow |
| `request.end_to_end` | Histogram/Timer | User-perceived latency, including phases outside the pool |

**Do not** infer business success rate from `getCompletedTaskCount`: completing a `FutureTask` can include failed tasks. Capture rejections at the submit path; with `CallerRunsPolicy`, the handler may run the task on the caller without throwing an exception, so model metrics by execution location/outcome.

Never put `taskId`, `correlationId`, email, or URLs with query strings into metric labels due to high cardinality. Keep opaque correlation IDs in logs/traces/JFR with appropriate retention and access control.

### 7.2. Thread Dumps Do Not Show Stacks for Queued Tasks

While the JVM is running and attach is permitted:

```bash
jcmd <PID> Thread.print -l > thread-t0.txt
sleep 5
jcmd <PID> Thread.print -l > thread-t1.txt
```

Replace `<PID>` with the real PID, record capture timestamps, and mind dump overhead. Thread dumps reflect **workers already occupied by tasks**, showing I/O, lock, park, or business code frames. A `Runnable`/`Callable` **sitting inside `ArrayBlockingQueue` does not yet have a worker**, so it **has no execution stack trace of its own** in the thread dump.

In the lab, the first worker is waiting on `CountDownLatch.await()`; the second task has not started and has no separate stack. The worker's `WAITING` state explains **why the worker is not free**, while queue metrics explain **that the second task is waiting**. Do not conflate them into "the second task is blocked inside its own code."

**`RUNNABLE` does not mean 100% CPU**; a worker could be waiting on OS I/O. When `active=max` yet CPU is low, check thread dumps, network/DB latencies, native calls, and lock events.

### 7.3. JFR Helps Investigate Run Time

JFR includes events such as `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, socket/file I/O, CPU sampling, GC pauses, and allocations — depending on version and settings. These help explain why **a worker that already started stays occupied for long**. By default JFR **does not know** an application field like `task X waited Y ms in executor queue`; you must instrument submit/start or emit a custom event in the application.

You can define a custom JFR event with `poolName`, `taskType`, `submitToStartNanos`, `runNanos`, and `outcome` using bounded String labels. Never record request bodies, tokens, or unauthorized correlation IDs; lower event rates or raise thresholds under heavy production load.

Example JFR commands while the JVM is alive and attachable:

```bash
jcmd <PID> JFR.start name=pool-diagnostics settings=profile duration=2m filename=pool.jfr
jcmd <PID> JFR.check name=pool-diagnostics
jfr summary pool.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter pool.jfr
```

`pool.jfr` exists only after the recording finishes/dumps. If you need a snapshot while the recording is still active:

```bash
jcmd <PID> JFR.dump name=pool-diagnostics filename=pool-now.jfr
```

JFR thresholds/sampling can omit events. **Absence of an event** does not prove a task never waited. Use JDK Mission Control (JMC) to align timelines when needed.

## 8. Rejection Policies and Backpressure

| Handler | When Pool Is Full | Side Effects |
| --- | --- | --- |
| `ThreadPoolExecutor.AbortPolicy` | Throws `RejectedExecutionException` | Caller must handle failure explicitly; easy to monitor overload |
| `CallerRunsPolicy` | Runs task in **caller thread** unless shut down | Throttles producer, but can stall ingress threads for long periods |
| `DiscardPolicy` | **Silently** drops task | Loses work; especially dangerous if caller holds a `Future` waiting forever |
| `DiscardOldestPolicy` | Drops an old queued task and retries submit | Loses tasks and alters fairness/ordering; unsuitable for critical work without compensating contracts |

Using `ExecutorService.submit()` with a discard handler can drop a task even though the caller already received a `Future`, leaving it waiting indefinitely without proper resolution. For work requiring durability/acknowledgment, use a durable queue or messaging system with explicit delivery, idempotency, retries, and deadlines — **never** treat an in-memory `ThreadPoolExecutor` as a transaction ledger.

Practical load-shedding options:

- **Bounded admission:** limit accepted tasks; return explicit overload responses (e.g., HTTP 429/503 where appropriate).
- **Intentional `CallerRunsPolicy`:** can slow submitters down, but never apply blindly to event loops, request acceptors, or latency-sensitive threads.
- **Bulkheads/semaphores:** cap concurrency to downstream dependencies independently of the thread pool.
- **Deadlines/timeouts:** avoid keeping stale tasks queued for minutes; ensure cancellation matches APIs rather than just `Future.get(timeout)`.
- **Circuit breakers and rate limiting:** shed load toward failing downstreams.
- **Bounded retries with backoff:** never spin-retry immediately on `RejectedExecutionException`, which amplifies overload.
- **Evidence-based scaling:** CPU-bound jobs depend on CPU budget/GC, while I/O-bound jobs depend on connection limits/buffers, not merely thread count.

**Do not choose a huge queue just to avoid rejections.** Huge queues hide backlogs and cause most requests to miss SLOs before ever reaching a worker; enlarging queues only **buffers bursts**, it does not raise steady-state service throughput.

## 9. Diagnostic Matrix for Wait Time vs. Run Time

| Symptom | Hypothesis to Test | Additional Evidence | Remedy Direction |
| --- | --- | --- | --- |
| High submit-to-start p99, low/stable run p99, growing queue | Arrivals exceed service capacity or sustained burst | Tasks/s, active, rejected, queue age, core/max | Bounded load, optimize admission, evidence-based concurrency scaling |
| High run p99, submit-to-start also rising | Workers held long by I/O, locks, downstream, or CPU | Thread dumps, JFR parks/sockets, DB wait, CPU profile | Reduce blocking, fix downstream, timeouts/bulkheads |
| High run p99 while queue stays low | Tasks intrinsically slow, no large backlog yet | TaskType breakdown, GC, I/O, CPU | Optimize run phase rather than focusing on queue |
| Current queue depth is 0 yet wait p99 is high | Gauge polling missed past bursts | Per-task histograms, event timeline | Measure submit→start and oldest queued age |
| Rising rejections, full queue, `active≈max` | Genuine admission saturation | Policy, traffic burst, max/queue config | Backpressure or capacity tuning |
| Rising rejections while `queue=0` and `active≈0` | Pool shut down, lifecycle/race issue | `isShutdown`, restart logs | Fix lifecycle instead of adding workers |
| Low CPU, `active=max`, high queue | Workers waiting on DB/network/locks | Thread dumps, JFR, dependency metrics | Fix waiting inside run phase |
| High CPU, `active=max`, high queue | CPU-bound load, GC pressure | CPU profiler, GC, allocation, throughput | Optimize compute or scale appropriately |
| `CallerRunsPolicy` and rising ingress latency | Caller executing overflowed tasks | Caller thread stacks, admission rate | Adjust overload response/policy |
| No rejections yet queue latency climbs steadily | Unbounded queue accumulating backlog | Queue length, oldest age, heap pressure | Add bounds/backpressure, reduce arrivals |

A saturated pool is a **capacity symptom**, not a root cause. It can stem from peak arrivals, threads waiting on DB, lock contention, GC pauses, hung tasks, or a deploy shrinking pool size. Combine wait/run histograms with worker states and dependency metrics.

## 10. Load Estimation Without Misusing Formulas

Notation:

- `λ`: arriving tasks per second (arrival rate).
- `E[S]`: average time a task occupies a worker (execution/occupied time).
- `c`: workers able to execute concurrently.

Ideal processing capacity can be roughly estimated around **`c / E[S]` tasks/s** if tasks are independent enough and no other bottlenecks exist. In practice, account for contention, I/O, service-time variance, GC, and CPU budget. If arrival rate **stays** above actual throughput, backlog accumulates and a bounded queue eventually rejects or applies backpressure.

**Example:** 4 workers, tasks occupying a worker for 100 ms on average give an ideal capacity around 40 tasks/s. If arrivals stay at 60 tasks/s without execution speeding up, queues tend to grow; enlarging the queue only **delays rejection**, without raising processing capacity.

Little's Law **`L = λ × W`** applies to steady-state systems with consistent measurement boundaries and long-term averages. Do not apply it directly to a 250 ms lab burst and treat it as a p99 guarantee. In production, evaluate distributions (p50/p95/p99), task mix, saturation periods, SLOs, and dependency headroom.

## 11. Extended Practice Exercises

### A. Try `CallerRunsPolicy`

Replace the last argument in the constructor with:

```java
new ThreadPoolExecutor.CallerRunsPolicy()
```

Keep `core=1, max=1, queue=1`. The third task may run **directly on the main/caller thread** instead of being rejected; the original lab's `thirdRejected=true` assertion **no longer holds**. Measure how long the caller is occupied and compare submission throughput. Explain the backpressure benefit and the risk of stalling HTTP/event-loop threads.

### B. Add a Worker

Try `core=2, max=2, queue capacity=1`. Hold **both** workers using latches, enqueue one task, then submit the next task to observe rejection. Do not simply change worker count while holding only one latch and assume the same state as the original lab; when two workers are free, admission order changes.

### C. Unbounded Queue with a Finite Task Count

Use:

```java
ExecutorService pool = Executors.newFixedThreadPool(1);
```

Submit a finite batch of 20 tasks, each taking ~40 ms, instrumenting `submitToStart`. Observe later-submitted tasks accumulating delay even without rejections. Do not use an infinite loop to exhaust heap just to demonstrate this.

### D. Failed and Cancelled Tasks

Create one task that throws `IllegalStateException` and another cancelled while queued. Update the wrapper to record run/outcome in `finally` without hiding the original exception, counting rejections/cancellations separately. Do not feed tasks that never started into successful runtime latency histograms.

### E. Caller Timeout

Try `future.get(50, TimeUnit.MILLISECONDS)` while a task is queued. After `TimeoutException`, check that the task may still be queued or running. If calling `cancel(true)`, verify whether the task supports interruption and cleanup. Explain how **caller wait budget** differs from queue wait measured via tSubmit/tStart.

### F. Thread Dumps and JFR

Hold the worker longer in a separate experiment and run `jcmd Thread.print -l` while the pool is full. Locate **task A's stack inside the worker**, and explain why you cannot find a separate Java stack for **queued task B**. If creating a custom JFR event, record submit-to-start/run by taskType with bounded fields and align timelines with JFR `ThreadPark`/I/O events.

## 12. Frequent Misconceptions

1. **"An accepted task is already running."** False: it may still sit in the queue.
2. **"40 ms inside `run()` equals 40 ms request latency."** False: queuing, ingress, and response handling add to it.
3. **"`Future.get()` duration equals queue wait."** False: it can include run time and scheduling.
4. **"Queue depth=0 means there was never a backlog."** False: a snapshot after a burst misses prior history.
5. **"`getActiveCount()=max` means 100% CPU."** False: workers may be waiting on I/O or locks.
6. **"A large `maxPoolSize` scales up immediately when core threads are busy."** False: it usually **queues first**, only expanding above core when the queue refuses tasks.
7. **"Unbounded queues prevent overload."** False: they hide rejections while inflating heap and tail latency.
8. **"`CallerRunsPolicy` always runs on a worker."** False: it can execute on the caller thread.
9. **"`DiscardPolicy` is equivalent to returning an explicit error."** False: tasks can vanish silently.
10. **"Zero rejections means all requests meet SLO."** False: they can time out before ever starting.
11. **"`Future.get(timeout)` cancels the task."** False: caller timeout does not cancel by default.
12. **"`shutdownNow()` guarantees all workers stop instantly."** False: it attempts interrupts and returns unstarted tasks; tasks ignoring interrupts can continue.
13. **"`afterExecute(Throwable)` sees every error from `submit()`."** False: `FutureTask` can swallow/store the exception.
14. **"`currentTimeMillis` is a stable duration clock."** False: use `nanoTime`.
15. **"Enlarging the pool fixes an exhausted DB pool."** False: it only adds workers waiting on the DB unless true capacity increases.
16. **"Virtual threads make unlimited concurrency safe."** False: downstream capacities remain finite.
17. **"`submitToStart + run` always equals HTTP latency."** False: phases outside the executor still apply.
18. **"One lab run is enough to size a production pool."** False: representative load, tail latency, memory, CPU, and SLOs are required.

## 13. Diagnostic Checklist and Practice Criteria

- [ ] The lab produces **1 running + 1 queued + 1 rejected** with `core=max=1`, queue capacity 1.
- [ ] `tSubmit`, `tStart`, `tEnd` come from **the same `System.nanoTime()`**, computing nanosecond durations accurately.
- [ ] Demonstrates that the `queued` task has substantial wait despite a short run; understands `submitToStart` includes dispatch.
- [ ] Excludes rejected and cancelled-before-start tasks from latency histograms of executed tasks.
- [ ] Knows `runNanos` is occupied wall time, not CPU time.
- [ ] Tracks queue depth, active count, rejection rate, submit-to-start, and run histograms with clear scopes.
- [ ] Distinguishes shutdown from overload when `RejectedExecutionException` occurs.
- [ ] Uses thread dumps/JFR to discover **why workers are occupied**, not expecting stacks for unstarted queued tasks.
- [ ] Separates caller timeouts, queue delay, task runtime, and end-to-end request latency.
- [ ] Chooses bounded concurrency and suitable backpressure/retries/deadlines; does not blindly enlarge pools/queues.
- [ ] Verifies changes under comparable load via throughput, rejections, p95/p99, and resource budgets.

**Conclusion:** A task can **run quickly yet start very late** when a pool saturates. Separating `submit→start` from `start→finish` turns a vague "slow API" complaint into actionable evidence: **waiting for a worker** versus **slow after the worker started**. Combine per-task measurements with queue state, rejection policies, and in-worker blocking causes to pick the right solution.

## References

- [Oracle JDK 21 — ThreadPoolExecutor: core/max, work queues, and RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle JDK 21 — ArrayBlockingQueue: capacity and remainingCapacity](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Oracle JDK 21 — ExecutorService: submit/shutdown](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle JDK 21 — Future: get(timeout), cancellation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Oracle JDK 21 — System.nanoTime for elapsed time measurement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())
- [Oracle JDK 21 — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle JDK 21 — jcmd: Thread.print and JFR](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
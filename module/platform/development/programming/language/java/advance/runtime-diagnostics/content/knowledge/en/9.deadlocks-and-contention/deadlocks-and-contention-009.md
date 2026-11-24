# 9.9 Verifying Post-Fix Progress via Completed Operations and Wait Time

## Learning Objectives

Fixing a deadlock, livelock, starvation, or long-wait bug **does not end when the application stops logging errors, thread dumps look “cleaner,” or the process restarts successfully**. The ultimate question is: **is work genuinely progressing again, on time, and under comparable load?**

A thread can be `RUNNABLE` yet merely retry without completing any transaction. CPU can drop after a change while the queue keeps growing. A thread dump may show no monitor deadlock cycle while the service still waits on the database. You must therefore measure **completed operations**, **wait times**, and **end-to-end processing impact**, comparing before and after in a controlled way.

After this lesson, you will be able to:

1. Define “useful progress” using terminal business outcomes: succeeded, failed, timed out, cancelled; never confuse attempts, accepted, or started with completed.
2. Build cumulative counters, compute **deltas/completion rates**, success throughput, error rates, and detect counter resets.
3. Measure **queue wait**, **lock acquisition wait**, **dependency wait**, **total operation latency**, and **oldest queued/in-flight age** using proper time bases and units.
4. Analyze p50/p95/p99 alongside sample counts, distinguish means from tails, and avoid mistaking `ThreadInfo.getBlockedTime()` for total business wait time.
5. Design a before–after comparison under **comparable load, same window, and same definitions**, with warm-up, baseline, repeat runs, guardrails, and conclusion boundaries.
6. Run a **standalone Java 17+** example featuring a fixture mode with deterministic stdout and a mode simulating an executor with a queue to observe real counters and queue waits.
7. Define PASS/FAIL criteria for deadlock, livelock, starvation, and long-wait fixes, including regression detection in production.
8. Write a technical report distinguishing what was observed, what remains hypothesized, and the next verification step.

---

## 1. “Progress” Does Not Equal “Activity”

Suppose a Java service shows two changes after a fix:

- Before fix: CPU at 95%, 10,000 retries/minute, completed business orders equal 0.
- After fix: CPU drops to 30%, 100 retries/minute, completed orders rise to 200/minute.

The second signal is better **in terms of useful progress**, yet you still need to verify whether latency, failure rate, queues, and offered load match. If post-fix traffic is only 1/10 of baseline, lower CPU or fewer completed orders **proves no improvement on its own**.

Another example: after a restart, `ThreadMXBean.findDeadlockedThreads()` returns `null` and the first request succeeds. That confirms the fresh snapshot detects no lock cycle, yet **does not prove** the root cause was eliminated: buggy lock ordering can resurface after hours of high concurrency.

**Pragmatic definition:** A system makes progress when accepted/eligible units of work transition to **verifiable terminal states**, at rates and latencies meeting SLOs, without unbounded queue growth at the agreed load.

### 1.1 Lifecycle Milestones to Keep Separate

```text
RECEIVED / OFFERED
      |
      v
ACCEPTED INTO SYSTEM ----- REJECTED
      |
      v
QUEUED / PENDING
      |
      v
STARTED / IN_FLIGHT
      |
      v
SUCCESS | FAILED | TIMED_OUT | CANCELLED
```

Not every service uses this exact diagram; there may be retries, dead-letter queues, ack/requeue, transaction rollbacks, deduplication, and unknown states. Choose a lifecycle model **fitting the business domain**, then define every metric by concrete events.

For example:

- `accepted_total`: requests **accepted** by an explicit admission decision.
- `started_total`: requests that began execution; not merely enqueued.
- `completed_total`: requests reaching a terminal outcome (within the defined scope).
- `succeeded_total`: requests completing **business-successfully**.
- `failed_total`: requests ending in failure; timeouts/cancellations may be separated per policy.
- `retried_total`: retry attempts; **does not** represent unique completed requests.
- `in_flight`: gauge of work units started and not yet finished.
- `queue_depth`: gauge of work units waiting and not yet started.
- `oldest_queued_age_ms`: age of the oldest queued item at observation time.

If a job retries three times and then succeeds, the business outcome may be **1 success** while attempts are 4; never mix these two measurement levels.

## 2. Minimal Metric Set to Confirm a Fix

| Metric | Type | Meaning | Caution When Using |
| --- | --- | --- | --- |
| `completed_total` | `long` counter | Work units reaching a terminal outcome since instance start | Includes failures if contract defines it so |
| `succeeded_total` | `long` counter | Useful progress committed/acked successfully | Do not double-count retries |
| `failed_total` | `long` counter | Work ending in error | Failure does not prove safe handling |
| `accepted_total` | `long` counter | Traffic admitted | Not completed |
| `retry_attempts_total` | `long` counter | Retry activity | Can climb while progress is 0 |
| `queue_depth` | `long/int` gauge | Current waiting items | A snapshot can miss transient spikes |
| `in_flight` | `long/int` gauge | Running unfinished items | Can be high due to slow dependencies |
| `oldest_queued_age_ms` | `long` gauge | Longest-waiting item | Very useful for spotting starvation |
| `queue_wait_ms` | Distribution | Accepted/enqueued to start | Excludes service time |
| `lock_wait_ms` | Distribution | Requesting lock to acquiring lock | Not lock **hold** duration |
| `dependency_wait_ms` | Distribution | Waiting on DB/RPC/HTTP or specific signal | Must tag dependency type and timeout |
| `end_to_end_latency_ms` | Distribution | Entry boundary to terminal outcome | State whether queue time is included |
| `deadline_exceeded_total` | `long` counter | Operations exceeding configured deadline | Caller timeout does not guarantee remote work stopped |

You do not have to emit every metric immediately. Pick **few enough yet sufficient to answer the question**. For instance, when fixing a stalled queue, completed/succeeded rates and oldest queue age are core; thread counts/CPU are supporting evidence.

### 2.1 Counters vs. Gauges

Counters normally grow over an instance’s lifetime; gauges rise and fall:

```text
Time       completed_total  queue_depth  in_flight
T1                1000           60         8
T2                1040           80         8
T3                1120           30         5
```

`completed_total` grew by 40 and then 80; `queue_depth` first **rose** then **fell**; `in_flight` does not necessarily correlate linearly with completions. You also need received/accepted counts and elapsed time to tell whether processing keeps pace with offered load.

Across a JVM restart, counters can reset to 0: never subtract `completed(T2) - completed(T1)` across two processes to get a negative number and claim “progress went backward.” Attach `process_start_time`, instance ID/pod, build, and timestamp.

### 2.2 Counting “Finished” Executor Tasks Does Not Reflect Business Outcomes

Per the Java 17 Javadoc, `ThreadPoolExecutor.getCompletedTaskCount()` is the **approximate total number of tasks that have completed execution**, not “orders delivered successfully,” and while workers change it is **approximate**. A `FutureTask` can hold an exception while still counting as completed from the executor’s perspective.

Thus, when verifying a fix:
- Use executor metrics for **pool capacity and state**.
- Use **business counters** at commit/ack/terminal events to prove genuine progress.
- Check `Future.get()`/exceptional completions, retries, transaction outcomes, and idempotency so failures are never counted as successes.

## 3. Completion Rate and Progress Rate Formulas

Given two samples on the **same instance**, with no counter reset, at times `T1` and `T2`:

```text
elapsedSeconds = (monotonicTimeT2 - monotonicTimeT1) / 1e9

completedDelta = completedTotal(T2) - completedTotal(T1)
successDelta   = succeededTotal(T2) - succeededTotal(T1)
failureDelta   = failedTotal(T2) - failedTotal(T1)

completionRate = completedDelta / elapsedSeconds
successRate    = successDelta / elapsedSeconds
failureRate    = failureDelta / elapsedSeconds
```

Rate units are **operations/second**. `completionRate` answers “how many operations reach a terminal state per second”; `successRate` answers “how many operations actually succeed per second.”

**Both are needed.** If a fix replaces buggy processing with returning failures ultra-fast, `completionRate` may jump while `successRate` stays flat. A useful-progress fix must preserve business semantics and success criteria.

### 3.1 Quantitative Before–After Example

Assume two **30-second** windows, both with **240** offered/accepted requests, identical hardware, and builds differing only by one fix:

| Metric Over 30s Window | Before | After |
| --- | ---: | ---: |
| Accepted | 240 | 240 |
| Completed terminal outcomes | 60 | 240 |
| Succeeded | 57 | 237 |
| Failed | 3 | 3 |
| Completion rate | 2.00/s | 8.00/s |
| Success rate | 1.90/s | 7.90/s |
| p95 queue wait | 1,200 ms | 90 ms |
| Accepted minus completed in window | 180 | 0 |

Formulas:

```text
completionRateGain = 8.00 / 2.00 = 4.00x

p95WaitReduction =
    (1200 ms - 90 ms) / 1200 ms * 100 = 92.50%
```

These numbers are a **hypothetical fixture**, not production data. They suggest the fixed service completes more operations and cuts tail queue wait. They are **not yet** absolute causal proof until you verify load conditions, request mix, data, caches, warm-up, repeat runs, and correctness guardrails.

**Important nuance:** `acceptedDelta - completedDelta = 180` reflects the inflow/outflow imbalance in that window, **not automatically the end-of-window queue depth**. Some operations may be in-flight, the initial queue may have been non-zero, cancellations/retries/requeues may exist, or snapshots may be non-atomic. Only with a full state-balance model can exact backlog be derived.

### 3.2 Window Failure Fraction Formula

```text
windowFailureFraction =
    failureDelta / completedDelta
```

Compute only when `completedDelta > 0`, with matching denominators/definitions and no resets. In the fixture:

- Before: 3 / 60 = **5%** of terminal outcomes failed.
- After: 3 / 240 = **1.25%** of terminal outcomes failed.

The absolute failure count **did not change**; the fraction dropped partly because the `completed` denominator grew. Never claim a business-error root cause was fixed solely because the fraction shrunk, especially if the request mix or difficulty changed.

## 4. Measuring Wait Times at the Right Boundaries

“Wait time” is not a single number. Inside a processing pipeline:

```text
accepted
  |--- queue wait ---|
                     started
                       |--- lock acquisition wait ---|
                                                         lock acquired
                       |----------- service time ----------------|
                                                                   terminal outcome

accepted |---------------- end-to-end latency -------------------> terminal outcome
```

**Separate boundaries before measuring:**

| Component | Start | End | Semantics |
| --- | --- | --- | --- |
| `queue_wait` | Request accepted/enqueued | Worker actually pulls task to run | Time **waiting to be served** |
| `lock_wait` | Requesting the lock | Lock acquired or timed out | Cost of **waiting for lock** |
| `lock_hold` | Lock acquired | Lock released | Time **holding lock**, distinct from `lock_wait` |
| `dependency_wait` | Calling DB/HTTP/RPC or await | Response/failure/timeout received | Time of that specific dependency |
| `service_time` | Worker starts processing | Terminal outcome | May include internal lock/dependency waits |
| `end_to_end` | Accepted or received per contract | Terminal outcome | May include queue wait and service time |

Never mechanically sum `lock_wait + dependency_wait + service_time`: `service_time` usually already **includes** internal wait components, so adding them double-counts.

### 4.1 Choosing the Clock: `System.nanoTime()` for Elapsed Time

For durations within the same JVM:

```java
long before = System.nanoTime();
try {
    // Call whose duration needs measurement.
} finally {
    long elapsedNanos = System.nanoTime() - before;
    // Record duration into an appropriate histogram/timer.
}
```

This is an **integration illustration snippet**, not a standalone program. `System.nanoTime()` uses an arbitrary reference suitable for computing **elapsed deltas within one JVM**, not epoch timestamps. To align events with logs/traces across machines, record UTC timestamps like `Instant.now()` **separately**.

Measuring elapsed time with `System.currentTimeMillis()` can be skewed by wall-clock adjustments; use it for event timestamps rather than precise elapsed measurement. Keep the same clock source and paired start/end points for every operation.

### 4.2 Measuring Queue Wait

Capture a timestamp **before enqueueing** and record when the worker begins running:

```java
long enqueuedAt = System.nanoTime();
executor.execute(() -> {
    long queueWaitNanos = System.nanoTime() - enqueuedAt;
    // metrics.recordQueueWait(queueWaitNanos);
    runBusinessWork();
});
```

This is an **integration snippet**; `executor` and `runBusinessWork()` must be defined. In production, handle rejections: a rejected request must not be counted as accepted; increment `rejected_total` and define explicitly when `accepted` is recorded.

With frameworks using schedulers, batch consumers, or message brokers, “enqueued” may occur in another system. `System.nanoTime()` values **cannot be subtracted directly across two JVMs**, since origins are per-process. For distributed queues, use clock-synced event timestamps, broker metrics/traces, and account for clock skew.

### 4.3 Measuring Lock Acquisition Wait

With `ReentrantLock`:

```java
long waitingSince = System.nanoTime();
lock.lock();
long acquiredAt = System.nanoTime();
try {
    // metrics.recordLockWait(acquiredAt - waitingSince);
    updateSharedState();
} finally {
    lock.unlock();
}
```

This is also an integration snippet. Measuring lock acquisition wait **differs from** measuring lock hold duration. Always unlock in `finally`; if using `tryLock`/`lockInterruptibly`, record timed-out/interrupted attempts separately and never `unlock` without holding the lock.

With `synchronized`, instrumenting right before/after the block requires care:

```java
long start = System.nanoTime();
synchronized (sharedMonitor) {
    long acquired = System.nanoTime();
    // Measure elapsed before entering the monitor and update the metric appropriately.
}
```

**Never** record metrics using slow blocking code inside the lock region, lest monitoring introduce new contention.

### 4.4 Measuring Dependency Waits and Timeouts

An HTTP client may traverse DNS, connect, TLS, pool acquisition, and response read. Define whether “HTTP latency” means total time or a slice. With JDBC connection pools, time spent **waiting for a connection** differs from query execution time.

Place timestamps, trace spans, and deadlines at the proper boundaries:

- How long did the caller wait?
- Did downstream receive the request?
- Are timeouts set at connect/read/query/overall layers?
- Does caller timeout **cancel** remote work?
- Did retries multiply the request?

When requests are slow while queue wait is low, the cause likely lies in service time / dependencies. When queue wait is high while service time is steady, look for insufficient workers, scheduling starvation, or offered load exceeding capacity.

## 5. Histograms, p50/p95/p99, and Sample Counts

A low average latency **does not** rule out terrible tail latency. If 99 requests take 10 ms and 1 takes 20 seconds, the mean still hides the worst-request experience.

Track **distributions** of queue wait, lock wait, and end-to-end latency, not just sums.

### 5.1 Percentile Meaning

- **p50:** median; half of samples have waits at or below this threshold per the percentile definition used.
- **p95:** roughly 95% of samples in the window do not exceed the p95 threshold.
- **p99:** roughly 99% similarly; sensitive to tails and requires a sufficiently large sample count.

Percentiles depend on estimation algorithms, interpolation vs. nearest-rank, histogram bucket layout, sample count, and window. If a lab has **8 samples**, nearest-rank p95 will usually equal the **maximum sample**, which is very noisy. Never use a small lab’s p95 to claim production SLO compliance.

### 5.2 Never Compute Cluster p95 by Averaging Replicas’ p95

If replica A has p95 = 50 ms and B has p95 = 500 ms, `(50+500)/2 = 275 ms` is **not** the cluster p95. You need properly mergeable distribution/histogram data or raw traces/samples aggregated properly.

Furthermore, before–after p95 comparisons must use the **same percentile algorithm**, window duration, sampling strategy, and operation population. If post-fix measures only successful requests while baseline included timeouts, a lower p95 may simply reflect changing the population.

### 5.3 Check Sample Counts and No-Data Cases

A “0 ms” wait differs from **no samples**. If zero requests arrived in one minute, that window’s p95 may be **undefined**—never default it to 0 and conclude all requests responded instantaneously.

Report `sampleCount` alongside distributions/quantiles, distinguishing:

- 0 samples: insufficient data;
- measured zero: actual samples near 0 within timer resolution;
- metric missing: exporter failed to measure/scrape;
- timeout/cancelled: recorded with proper semantics rather than silently stripped from charts.

An idle application receiving zero requests is not “stalled”; stall detection requires **offered/accepted work > 0** with no progress over a threshold window.

## 6. JVM Tools: For Explanation, Not Replacing Business Progress

`ThreadMXBean`, `ThreadInfo`, `jcmd Thread.print`, and JFR provide runtime evidence. They help explain *why* waits changed, yet do not themselves confirm business operations succeeded.

### 6.1 ThreadMXBean and Contention

Java 17 provides:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();

boolean supported =
        mx.isThreadContentionMonitoringSupported();
if (supported && mx.isThreadContentionMonitoringEnabled()) {
    ThreadInfo info = mx.getThreadInfo(threadId);
    if (info != null) {
        long blockedCount = info.getBlockedCount();
        long blockedMs = info.getBlockedTime();
        long waitedMs = info.getWaitedTime();
        // Analyze only within the same thread and same window.
    }
}
```

This snippet is **not standalone**: it needs `ThreadMXBean`, `ThreadInfo`, and `ManagementFactory` imports plus a valid positive `threadId`. On many JVMs, contention monitoring is **off by default**; when disabled, `getBlockedTime()` / `getWaitedTime()` can return **`-1`**, not 0.

**Core limitations:**

- `getBlockedTime()` is an approximate cumulative time waiting on **intrinsic monitors** (`BLOCKED`), not all waits on `ReentrantLock`, HTTP, databases, or queues.
- `getWaitedTime()` reflects time in waiting/timed-waiting states per API semantics, not transaction-level latency.
- Counts/times belong to a thread; a pool worker handles many business operations, so thread wait milliseconds cannot be directly assigned to one request.
- Timing stats may reset when monitoring is toggled; never compute deltas across monitoring config changes.
- `setThreadContentionMonitoringEnabled(true)` **mutates JVM observability state** and incurs overhead; enabling it in production requires authorization, timestamping, and weighing cost.

### 6.2 Thread Dumps and Deadlock Detection

A few post-fix thread dumps can verify whether lock graphs and call paths still exhibit issues. On HotSpot with proper permissions:

```bash
jcmd 12345 Thread.print -l
```

`12345` is an **illustrative PID**; replace it with the real target JVM PID. Run `jcmd 12345 help Thread.print` if unsure of options on that JDK.

`ThreadMXBean.findMonitorDeadlockedThreads()` and `findDeadlockedThreads()` check monitor/ownable-synchronizer cycles within supported scope. Returning `null` post-fix only means **no cycle of that type was detected at measurement time**, not that requests finished or pool starvation disappeared.

**Priority order:** measure business progress first, then use stacks/lock owners/CPU/JFR to explain causes. Never use a single `RUNNABLE` or `WAITING` thread state as the sole PASS criterion.

### 6.3 CPU Changes Do Not Automatically Mean Better Throughput

“Fixing” a livelock by adding `Thread.sleep(100)` can lower CPU and retries while **completed work remains 0**; that is not a successful fix. Conversely, removing lock contention can raise CPU because workers are now actually processing more requests.

Compare CPU alongside **completed/succeeded rates, p95/p99 wait, queue age, and errors** under the same workload. CPU is a **guardrail and supporting signal**, not the final goal for business-oriented SLOs.

## 7. Designing a Reliable Before–After Experiment

A comparison consists of **baseline → change → verification**. Changing workload, process identity, worker counts, caches, and counter definitions all at once makes it impossible to tell what caused the improvement.

### 7.1 Write a “Measurement Contract”

Before running, lock down:

| Element | What Must Be Fixed or Recorded |
| --- | --- |
| Scope | Service/component, endpoint/job class, JVM/instance, and build |
| Load | Arrival rate, concurrency, mix, payload size, input data |
| Duration | Warm-up, steady-state window, measurement interval |
| Metric definitions | Accepted/started/completed/succeeded/failed/retry semantics |
| Units | operations/s, milliseconds, percentages, queue depth |
| Sampling | Histogram buckets, quantile method, sample count, missing data |
| Runtime | JDK/GC/CPU quota/memory, worker count, pool/queue sizes |
| Environment | Downstream versions/availability, DB state, caches, network |
| Pass criteria | Completion and success rates, max age/p95 wait, timeout/error guardrails |
| Failure protocol | If progress stalls, when to stop the test and safely capture evidence |

If pre-fix ran at 1,000 concurrent requests while post-fix ran at 10, that is not a valid control to claim “starvation solved under 1,000-concurrency load.”

### 7.2 Warm-Up and Multiple Runs

JIT compilation, class loading, lazy initialization, cache warm-up, connection pooling, and GC can make initial runs behave differently from later runs. Practice:

1. Run baseline long enough to reach near-steady state where possible.
2. Exclude the **warm-up interval** from the measurement window.
3. Capture multiple consecutive windows (or repeat runs) with timestamps and sample counts.
4. Repeat under the exact conditions that previously triggered the failure, not merely average load.
5. Deploy one focused fix; keep other configs stable as far as possible.
6. Collect post-fix data with the same tools, contract, and sample count/cadence.
7. Compare both center and tails (p50/p95/p99), rates, and backlogs.
8. If results vary widely, report the range and hypotheses; never cherry-pick the single best run.

**Never massage numbers** by excluding timed-out or failed intervals post-fix while comparing against a baseline that included failures. If any samples are excluded, the exact same exclusion rule must apply before and after.

### 7.3 Compare Matching Windows and Matching Instances

For cumulative counters, each rate needs **two timestamps on the same instance** without resets. If a rollout replaces a pod, start a fresh series or use reset-aware tooling.

For rolling histograms, match window duration and population. For logs/traces, align timezones and account for clock skew across hosts. `System.nanoTime()` values from one JVM **cannot be compared directly in absolute terms** with `nanoTime` from another JVM.

### 7.4 A Passing Test Needs Both Efficiency and Correctness

Hypothetical criteria example for a job queue:

- Post-warm-up, offered load 8 jobs/s sustained for 10 minutes.
- Success throughput at least 7.8 jobs/s; completions fully tracked.
- p95 queue wait under 200 ms; p99 and oldest queue age within configured budget.
- Failure/timeout/cancellation rates show no abnormal rise vs. baseline.
- Queue depth shows no unbounded upward trend; no stuck oldest task.
- Stress tests reproduce no lock cycles or stalled execution paths.
- CPU/RSS/GC/connection pools/DB latency stay within guardrails.

The numbers above **are examples only** to illustrate writing acceptance criteria; replace them with real SLOs and workloads. If criteria are missed, report `NOT_VERIFIED`/`FAIL` per definition rather than extrapolating from a handful of successful requests.

## 8. Java 17: Program Measuring Completions and Queue Wait

**`ProgressVerificationLab.java`** has two modes:

- `fixture`: uses the hypothetical before–after data from section 3 to compute rates, improvement factor, and p95 queue wait reduction; **deterministic** stdout, runs no real tasks.
- `observe`: creates a **two-worker ThreadPoolExecutor**, submits eight simulated tasks where one intentionally fails, and collects accepted/started/completed/succeeded/failed and queue wait. Outcome totals are verifiable; **elapsed time, queue p95, and execution order are machine-dependent**. This is a small lab, not a production benchmark.

Requires Java 17 or newer, with no external libraries.

Create file **`ProgressVerificationLab.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class ProgressVerificationLab {
    record Window(String name, long accepted, long completed,
                  long succeeded, long failed,
                  double durationSeconds, long queueP95Millis) {
        double completionRate() {
            return completed / durationSeconds;
        }
    }

    static void fixture() {
        Window before = new Window(
                "before", 240, 60, 57, 3, 30.0, 1200);
        Window after = new Window(
                "after", 240, 240, 237, 3, 30.0, 90);

        for (Window w : new Window[] {before, after}) {
            System.out.printf(Locale.ROOT,
                    "%s accepted=%d completed=%d succeeded=%d "
                    + "failed=%d rate=%.2f/s queueP95=%dms%n",
                    w.name(), w.accepted(), w.completed(),
                    w.succeeded(), w.failed(),
                    w.completionRate(), w.queueP95Millis());
        }

        double rateGain =
                after.completionRate() / before.completionRate();
        double p95Reduction = 100.0 *
                (before.queueP95Millis() - after.queueP95Millis())
                / before.queueP95Millis();

        System.out.printf(Locale.ROOT,
                "completionRateGain=%.2fx queueP95Reduction=%.2f%%%n",
                rateGain, p95Reduction);
    }

    static final class Metrics {
        final AtomicLong accepted = new AtomicLong();
        final AtomicLong started = new AtomicLong();
        final AtomicLong completed = new AtomicLong();
        final AtomicLong succeeded = new AtomicLong();
        final AtomicLong failed = new AtomicLong();
        final AtomicInteger inFlight = new AtomicInteger();

        // For small labs only; production should use a memory-bounded
        // histogram instead of retaining every duration.
        final List<Long> queueWaitNanos =
                Collections.synchronizedList(new ArrayList<>());

        void onStart(long queuedAtNanos) {
            long now = System.nanoTime();
            queueWaitNanos.add(Math.max(0L, now - queuedAtNanos));
            started.incrementAndGet();
            inFlight.incrementAndGet();
        }

        void onFinish(boolean successful) {
            if (successful) {
                succeeded.incrementAndGet();
            } else {
                failed.incrementAndGet();
            }
            completed.incrementAndGet();
            inFlight.decrementAndGet();
        }

        long queueP95Millis() {
            List<Long> copy;
            synchronized (queueWaitNanos) {
                copy = new ArrayList<>(queueWaitNanos);
            }
            if (copy.isEmpty()) {
                return -1; // No samples yet, not 0 ms.
            }
            Collections.sort(copy);
            int index = (int) Math.ceil(0.95 * copy.size()) - 1;
            return TimeUnit.NANOSECONDS.toMillis(copy.get(index));
        }
    }

    static void observe() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(16),
                work -> new Thread(work, "progress-lab-worker"));

        Metrics metrics = new Metrics();
        List<Future<?>> futures = new ArrayList<>();
        long sampleStart = System.nanoTime();

        try {
            for (int i = 0; i < 8; i++) {
                final int jobId = i;
                final long enqueuedAt = System.nanoTime();

                Future<?> future = pool.submit(() -> {
                    metrics.onStart(enqueuedAt);
                    boolean success = false;
                    try {
                        Thread.sleep(jobId == 0 ? 80L : 15L);
                        if (jobId == 3) {
                            throw new IllegalStateException(
                                    "synthetic lab failure");
                        }
                        success = true;
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "lab interrupted", ex);
                    } finally {
                        metrics.onFinish(success);
                    }
                });

                // Accepted by pool; do not count as rejected.
                metrics.accepted.incrementAndGet();
                futures.add(future);
            }

            int futureFailures = 0;
            for (Future<?> future : futures) {
                try {
                    future.get(3, TimeUnit.SECONDS);
                } catch (ExecutionException ex) {
                    futureFailures++;
                }
            }

            pool.shutdown();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "pool did not terminate");
            }

            long elapsedNanos = System.nanoTime() - sampleStart;
            System.out.printf(Locale.ROOT,
                    "accepted=%d started=%d completed=%d "
                    + "succeeded=%d failed=%d "
                    + "futureFailures=%d inFlight=%d%n",
                    metrics.accepted.get(), metrics.started.get(),
                    metrics.completed.get(), metrics.succeeded.get(),
                    metrics.failed.get(), futureFailures,
                    metrics.inFlight.get());

            System.out.printf(Locale.ROOT,
                    "elapsedMs=%d queueP95Ms=%d%n",
                    TimeUnit.NANOSECONDS.toMillis(elapsedNanos),
                    metrics.queueP95Millis());
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java ProgressVerificationLab fixture|observe");
            return;
        }
        switch (args[0]) {
            case "fixture" -> fixture();
            case "observe" -> observe();
            default -> System.out.println("Unknown mode");
        }
    }
}
```

### 8.1 Compile and Run fixture

```bash
javac ProgressVerificationLab.java
java ProgressVerificationLab fixture
```

**Exact** stdout of `fixture` mode:

```text
before accepted=240 completed=60 succeeded=57 failed=3 rate=2.00/s queueP95=1200ms
after accepted=240 completed=240 succeeded=237 failed=3 rate=8.00/s queueP95=90ms
completionRateGain=4.00x queueP95Reduction=92.50%
```

**Explanation:** `60 / 30 = 2.00` and `240 / 30 = 8.00`; `8/2 = 4.00`; `(1200-90)/1200*100=92.50`. The code uses `Locale.ROOT` to format decimals with a dot regardless of machine locale.

The two p95 values in `fixture` **are pre-supplied** as hypothetical data, not percentiles calculated by the program from request timestamps. This is a **mathematical verification of reporting logic**, not proof a real fix worked.

### 8.2 Running a Real Workload in the Lab JVM

```bash
java ProgressVerificationLab observe
```

When tasks complete within the lab timeout without external interference, the expected **counters line** is:

```text
accepted=8 started=8 completed=8 succeeded=7 failed=1 futureFailures=1 inFlight=0
```

The timing line takes the form:

```text
elapsedMs=<actual measured value> queueP95Ms=<actual measured value>
```

**Both bracketed placeholders above describe the format, not fixed stdout.** Busy machines, OS scheduling, JIT, clock resolution, and task queueing vary durations. Meanwhile the task with `jobId==3` intentionally throws `IllegalStateException`; `submit()` captures the exception in the `Future`, so the loop catches `ExecutionException` and increments `futureFailures`. It still counts as a **completed terminal outcome that failed**, not a success.

This directly demonstrates an operational trap: **if you only count finished tasks, a fix can look successful even while all tasks return failures**. Keep success/failure and business correctness separate.

### 8.3 Limitations of the observe Lab

- Only eight tasks; nearest-rank p95 is essentially the **max sample**, unsuitable for proving production SLOs.
- `queueWaitNanos` is kept in a `List` for readability; **never use this** for millions of production requests due to unbounded memory growth. In real production, use bounded histograms/reservoirs or proven metrics libraries.
- Counters are independent atomics, lacking an **atomic multi-property snapshot** while work is running. After waiting for all futures and pool termination, lab counts stabilize.
- The lab’s queue is bounded at 16 with 8 tasks, so it does not intentionally test `RejectedExecutionException`. Production must track **rejections and admission** accurately rather than counting rejected tasks as accepted.
- Timing measures queue wait from before `submit` to when `Runnable` starts; this includes some submit/scheduling overhead, differing from internal queue wait definitions of a message broker. Document your real system’s contract.
- `Thread.sleep(80)` only simulates a waiting operation, not a real contention cause. Reducing sleep time and seeing higher throughput does not prove a deadlock was fixed.
- `pool.shutdownNow()` in `finally` is lab cleanup. Never apply it unconditionally to a production pool serving live user requests.

## 9. Why One Good Window Is Not Enough to Prove a Fix

High post-fix completion rate in one window may happen because:

- Workload was lighter than baseline with fewer requests competing for resources.
- Caches warmed up, DB just purged/compacted, or downstream recovered independently.
- The fix only masked symptoms with fast retries while failures persisted.
- Service restart broke an in-memory lock/dependency cycle while the bug remained in code.
- Metric definitions changed: “accepted” or “completed” stopped counting retries/timeouts the old way.
- Collectors dropped samples under CPU overload or agent restarts.
- You are observing **backlog drain**: completion rate temporarily exceeds offered rate, then settles back down.
- The test did not run long enough to trigger a rare race condition or multi-minute starvation.
- Another request group suffered worse; aggregate throughput hid a small group’s tail.
- The observer picked the fastest run to report and discarded poor runs.

### 9.1 Designing a Repeatable Experiment

A practical procedure:

1. Reproduce the failure with a controlled test and capture multiple baseline runs.
2. Confirm reproducibility: after how long progress stalls, and what conditions trigger it.
3. Apply only one fix or one tightly coupled set of changes.
4. Re-run with the exact same arrival pattern, payload/data, pool sizes, JVM flags, quotas, dependencies, and duration.
5. Compare completed work **per window**, success rate, p95/p99 wait, oldest pending age, and errors.
6. Test bounded overload, cancellation/timeouts, repeated runs, and rollback/canary as needed.
7. Capture thread dumps/JFR when symptoms reproduce, not only when everything looks healthy.
8. State conclusions with confidence level, denominators, observation windows, and untested gaps.

A change can genuinely reduce contention yet worsen fairness: verify both aggregate throughput and **per-class oldest wait** plus tail latency.

## 10. Criteria per Fixed Failure Type

### 10.1 After Fixing a Deadlock

**Before:** several threads held crossed locks, completing no business work; lock graph showed a cycle.

**After:** under reproduction load, accepted work keeps arriving; completed and succeeded rise steadily; locks are acquired/released properly with no cycles across meaningful samples; p95/p99 lock/queue waits stay within budget; no request lingers forever.

**What to verify:**

- Code paths acquire locks in a consistent global order, including error paths.
- Evidence collected via `ThreadMXBean` if using matching synchronizer types and supported by the JVM.
- Did not simply delete a lock and introduce races/data corruption to boost throughput.
- High-load / contended paths do not recreate the cycle.

**Limitations:** `findDeadlockedThreads()==null` at one instant does not prove no logical/distributed deadlocks exist anywhere. Business completions and wait times across multiple samples are necessary additional evidence.

### 10.2 After Fixing a Livelock

**Before:** retry/attempt counts climbed fast with activity/CPU yet committed operations stayed near 0.

**After:** **successfully committed operations** increase; `successDelta / attemptDelta` improves; retries are bounded with backoff/deadlines; oldest queue age stops growing forever; latency stays within budget.

**What to verify:**

- Did `retried_total` drop merely because code removed retries and failed immediately?
- Did `succeeded_total` rise under the same conflict rate?
- Do retry jitter/backoff keep p99 within bounds without starving tasks?
- When downstream is genuinely down, does it fail boundedly rather than spinning in an infinite retry loop?

Lower CPU while `successDelta` stays 0: **cannot PASS**.

### 10.3 After Fixing Starvation

**Before:** one task class was starved and oldest queue age climbed while other tasks kept progressing.

**After:** all work classes receive service per policy; per-class completion rates and oldest waits meet deadlines; no group is delayed indefinitely under expected load.

**What to verify:**

- Aggregate completed/s rose, yet did low-priority p99 / oldest age actually improve?
- Did fair locks / priority aging depress throughput too severely?
- Are bounded queues/rejections reported transparently?
- Do certain tasks need dedicated capacity reservation/bulkheads so long-running tasks cannot monopolize slots?

An important request group having a 10-minute queue wait while total service throughput is 1,000 RPS can still be severe starvation.

### 10.4 After Fixing a Long Wait

**Before:** requests waited unboundedly on `Future.get`, network, DB, locks, conditions, or latches, holding workers past deadlines.

**After:** sensible deadlines/timeouts exist and return explicit terminal outcomes; active waits / queue age do not grow unboundedly; success rates meet SLOs; cancellation/cleanup work per semantics; downstream/workers recover.

**What to verify:**

- Timeouts rose while successes fell? This may be useful fail-fast resource protection, **not synonymous with business recovery**.
- Caller timed out yet remote job kept running and caused side effects? Verify idempotency/cancellation.
- Is queue time subtracted from the overall budget, or does timeout only start once the worker begins?
- Is there data loss or duplicate processing due to retries?

## 11. Verifying Without Disrupting the System

Measurement has cost. Taking full thread dumps every 100 ms or enabling contention monitoring without assessing overhead can worsen the incident.

**Prefer least-intrusive order:**

1. Already-instrumented application counters, histograms, request traces, and queue metrics.
2. Existing JVM/process/container metrics: CPU, GC, memory, thread counts, cgroup throttling.
3. A few timestamped thread dumps when lock/stack evidence is needed.
4. Controlled JFR sampling or contention monitoring with start/stop timestamps logged.
5. Heavy snapshots only when lightweight metrics cannot answer the diagnostic question.

Remember to check `ThreadMXBean` availability flags before using CPU/blocked/waited times; `-1` or `null` may mean unmeasured, missing thread, or unsupported feature—**not** measured zero.

When recording logs/traces, limit request payloads, secrets, and sensitive data; enforce retention and access controls. Never create a new metric label per request/user/trace ID, as cardinality explodes and privacy risks rise.

## 12. Verifying “Unstuck” Requires Checking Both Backlog and Arrival Rate

Suppose post-fix shows:

```text
Offered load:    100 jobs/s
Completed rate:   80 jobs/s
Queue depth:      1,000 → 1,200 → 1,400 ...
```

The service **is making progress** (80 jobs/s), yet **is not keeping up with load** (100 jobs/s), so backlog keeps growing. Do not call this full recovery.

Another example:

```text
Offered load:     80 jobs/s
Completed rate:  100 jobs/s
Queue depth:    1,000 → 700 → 400 ...
```

The system may be **draining backlog**: completed temporarily exceeds offered while the queue shrinks. That is a positive sign if success/correctness hold, yet keep measuring **after backlog stabilizes**, because completion rate may drop once the queue empties.

With matching denominators, the intuitive relation is:

```text
changeInBacklog ≈ acceptedDuringWindow
                  - startedDuringWindow
                  + requeuedDuringWindow
                  - removedQueuedItems
```

This is an **illustrative model**, not a universal invariant for every queue; worker transfers, cancellations, failures, transaction retries, and snapshot consistency all matter. Never treat `accepted - completed` as queue depth without accounting for `inFlight` and intermediate states.

### 12.1 What Does Oldest Age Add?

A steady queue depth does not guarantee fairness. A priority scheduler can keep accepting and finishing high-priority tasks while one low-priority job sits stuck for hours. Total queue depth barely moves, yet **oldest age of the victim group climbs forever**.

Therefore when fixing starvation, beyond aggregate throughput, measure:
- accepted/completed per class;
- waiting age per class;
- oldest unserved job duration;
- p95/p99 queue wait for the affected group;
- rejected/cancelled/deadline-exceeded per class.

You do not need every job ID in a metric label; bounded aggregation by priority/class works for dashboards while detailed IDs live in logs/traces.

### 12.2 Little's Law: Interpretive Aid, Not Verdict

In a **steady-state system** meeting appropriate assumptions, Little's Law states:

```text
Average number of jobs in system
    ≈ throughput per second × average time in system

L ≈ λ × W
```

For example, if a system completes 10 jobs/s and average time in system is ~2 s, average WIP is roughly 20 jobs. Never use this formula to declare “deadlocked” from one snapshot: it relies on averages and steady state, not p99 or a system experiencing unbounded backlog growth.

## 13. Never Trade Correctness for Completion Rate

Ways throughput can rise while the product breaks:

- Skipping auth/validation so requests return success faster.
- Skipping transaction writes/commits or DB result waits before acking.
- Swallowing exceptions and incrementing `succeeded_total` despite unfinished business work.
- Timing out at caller while retrying repeatedly and causing duplicate payments.
- Relaxing locks/ordering without preserving invariants, introducing race conditions.
- Dropping slow request classes from post-fix reporting to make p95 look prettier.

**Business progress** must be verified by real outcomes: records committed, jobs acked only after valid processing, responses honoring contracts, and no lost/duplicated data. Acceptance criteria must therefore include **correctness**, success/failure semantics, idempotency, and reconciliation where needed.

If `completed` rose due to 1,000 fast failures, the system may **fail-fast better** (protecting resources) yet cannot be declared business-recovered. Report both facts separately: *wait time was bounded* and *success rate has not yet met target*.

## 14. Quick Evidence-Reading Matrix

| Post-Fix Observation | What Can Be Concluded | What Cannot Yet Be Concluded |
| --- | --- | --- |
| Completed rate > 0, previously 0 | Signs of resumed progress | SLO/correctness met under all loads |
| Steady succeeded rate, lower failures | Business progress improved in measured window | Change was caused solely by the code fix |
| Queue p95 dropped, oldest age dropped | Queue waiting improved | No individual request class is still starved |
| Retry rate dropped, success rate rose | Fewer wasted retries, better output | Livelock will not recur under edge loads |
| `ThreadMXBean` finds no deadlock cycle | No cycle of API-supported types found at measurement time | No logical/distributed deadlocks or deadlocks at other times |
| CPU dropped while completed=0 | Proves no progress yet | Issue is fixed |
| `Future.get(timeout)` throws timeout | Caller exhausted wait budget | Remote task stopped |
| Pool `getCompletedTaskCount` rose | Executor finished tasks | All business operations succeeded |
| p99 latency rose, mean dropped | Tail worsened for some work | Fix definitely met SLO |
| One run passed, others failed | Fix works under some conditions | Concurrency bug reliably eliminated |

## 15. Before–After Verification Report Template

```text
IDENTITY
- Service, build/revision, JVM vendor/version, PID/pod:
- Fix description and hypothesized failure mechanism:
- Baseline incident timestamp and reproduction conditions:

MEASUREMENT CONTRACT
- Work type and definition of accepted/completed/succeeded/failed:
- Units: operations/s, queue/lock/dependency wait in ms:
- Window duration, sample count, percentile algorithm:
- Workload: offered load, concurrency, request mix, payload size:
- Environment: CPU quota, GC, pool/queue sizes, dependency state:

BEFORE FIX
- Accepted/completed/succeeded/failed counts per window:
- Completion rate, success rate, retries and failure fraction:
- Queue depth, oldest age, in-flight age:
- p50/p95/p99 queue wait, lock wait, e2e latency:
- Thread dump/JFR/lock owner evidence:
- CPU/GC/DB/network guardrails:

AFTER FIX
- Same metrics under comparable conditions:
- Completion/success rate improvement:
- Wait/tail percentile changes and absolute differences:
- Backlog trend, fairness per class, deadline exceed count:
- Correctness/idempotency/duplicate/lost-work checks:

QA / UNCERTAINTY
- Number of runs, warm-up excluded, variance:
- Counter resets, missing samples, observer overhead:
- What is observed vs hypothesized:
- PASS/FAIL/INCONCLUSIVE criteria:
- Remaining risk, regression tests, rollout/canary owner:
```

The template above should be filled with **timestamped numbers and clear sources**. If a metric cannot be measured, write `not measured`, `unsupported`, or `insufficient samples` rather than filling in 0.

A credible report might state:

> “Across five 30-second windows under 8 accepted requests/s, post-fix completion rate rose from ~2 to 8/s, p95 queue wait dropped, success rate did not degrade, and oldest queue age stopped climbing. Within controlled test scope, criteria PASS; canary monitoring during peak traffic and rare-conflict loads remains necessary.”

This is an **example of phrasing findings**, not data collected from a real system. Always distinguish “test passed” from “proven impossible for a race condition to occur under any schedule.”

## 16. Common Mistakes

1. **Counting attempts instead of completed.** Livelocks can have endless retries with 0 progress.
2. **Counting completed executor tasks as business successes.** Tasks can finish by throwing exceptions.
3. **Comparing only CPU.** Lower CPU can simply mean workers are sleeping/waiting more.
4. **Comparing only live thread counts.** Fewer threads do not prove queues are being served.
5. **Treating one cumulative counter point as throughput.** You must compute deltas on the same instance/window.
6. **Ignoring counter resets after restarts.** Can produce negative rates or wrong conclusions.
7. **Lumping accepted, started, and completed together.** Fails to separate queue wait from service time.
8. **Confusing queue wait with end-to-end latency.** Reducing one piece may not reduce the whole.
9. **Adding service time and dependency wait when dependency is already inside service time.** Double-counts.
10. **Using `System.nanoTime` as a UTC timestamp.** It measures elapsed time, not wall-clock time.
11. **Comparing `nanoTime` timestamps across JVMs.** Different origins.
12. **Omitting sample counts for p95/p99.** Percentiles over 8 samples are very noisy.
13. **Averaging p95 across replicas.** Does not yield cluster p95.
14. **Turning missing samples into 0 ms.** Masks exporter faults and creates fake improvements.
15. **Dropping timeouts/failures post-fix without dropping them in baseline.** Populations no longer match.
16. **Comparing before–after under different loads.** Invalidates causal comparison.
17. **Forgetting warm-up/JIT/caches.** First runs can be abnormally slow.
18. **Cherry-picking the best run.** Hides variance and rare race bugs.
19. **Running only once.** Insufficient evidence for deadlocks/starvation requiring specific schedules.
20. **Not measuring oldest queue age.** Total throughput can look high while one group starves.
21. **Trusting a null deadlock detector means the fix is done.** The API only checks supported cycle types at one instant.
22. **Enabling contention monitoring without recording timestamps.** Times may reset and overhead shifts results.
23. **Converting `ThreadInfo`'s `-1` into 0.** `-1` usually means no valid measurement available.
24. **Reporting higher completion rate when only fast failures increased.** Fails to separate success/correctness.
25. **Testing only during backlog drain.** Keep measuring once the new steady state settles.
26. **Not measuring queue deadlines.** Tasks may exhaust budgets before workers ever start them.
27. **Forgetting cancellation/idempotency.** Caller timeout does not cancel remote side effects.
28. **Overly heavy instrumentation.** Getters/tracing/dumps can introduce new contention.
29. **Putting user IDs into metric labels.** High cardinality and major privacy risks.
30. **Restarting before collecting evidence.** Destroys thread graphs, queue ages, and original timelines.
31. **Declaring “no hangs” from one succeeding request.** Tails, full populations, and stress reproduction are needed.
32. **Having no pre-defined PASS criteria.** Makes it easy to pick favorable metrics after seeing results.

## 17. Knowledge Self-Check

1. Why is a rising retry counter insufficient to prove the system is making progress?
2. Distinguish `accepted_total`, `started_total`, `completed_total`, and `succeeded_total` using an example of a request retried three times.
3. Going from 60 to 240 completed operations in two 30-second windows, by what factor did completion rate increase?
4. If post-fix `completedRate` rises while `succeededRate` stays flat, which outcomes must you inspect?
5. Is `System.nanoTime()` for elapsed time or cross-host timestamps? Why?
6. Where does queue wait start and end? Should it include worker execution time?
7. Why is `ThreadInfo.getBlockedTime()` not total DB/RPC wait time?
8. If `ThreadMXBean.findDeadlockedThreads()` returns `null`, does that confirm starvation is gone?
9. Why can p99 queue wait rise even when the mean drops? What extra data do you need?
10. Why is p95 over 8 samples insufficient to verify a production SLO?
11. Can you average the p95 of two replicas to obtain cluster-wide p95?
12. If accepted rate stays 100/s while completed rate stays 80/s, what happens to backlog in a simple model?
13. Why can a steady queue depth still hide starvation of low-priority jobs?
14. How do you distinguish a completion-rate spike from backlog draining vs. a steady-state improvement?
15. If before and after loads differed by 10x, what limitation must the report state?
16. Post-fix shows faster timeouts yet fewer successes: should you conclude the fix succeeded or merely failed fast?
17. Does `Future.get(timeout)` guarantee the task was canceled? What must be checked?
18. Which guardrails should be measured alongside completion rate to ensure correctness was not traded away?
19. When should you use repeat tests, canaries, and controlled chaos/failure injection?
20. Write one measurable acceptance criterion for fixing queue starvation and one for deadlock.

## References

- Oracle Java SE 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- Oracle Java SE 17 — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 17 — `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 17 — `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- Oracle Java SE 17 — `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Takeaway:** verify hang/contention fixes using **meaningfully completed work**, **success throughput**, **wait times and tail latency**, **queue age**, and **correctness/guardrails** under comparable load. CPU, thread states, or absence of lock cycles are only supporting evidence. A fix is considered verified within test scope when pre-defined criteria pass across multiple suitable windows without introducing side effects or stalling other work groups.
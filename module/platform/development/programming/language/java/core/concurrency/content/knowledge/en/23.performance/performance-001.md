# Latency, Throughput, Utilization, and Stability in Java Concurrency

## 1. Four Different Perspectives on Performance

A concurrent Java program can process many tasks, but "more threads" does not automatically mean "faster." You need to distinguish four metrics to know how fast the system responds, how much work it completes, how resources are used, and whether quality holds up over time.

| Metric | Question to Answer | Common Measurements | Risk of Looking at Only One Metric |
| --- | --- | --- | --- |
| **Latency** | How long does a task take from acceptance to completion? | ms/request; p50, p95, p99 | Low average, yet some requests wait a very long time |
| **Throughput** | How many tasks are completed within a given time interval? | requests/s, tasks/s, MB/s | High number of started requests, but low completion count or many errors |
| **Utilization** | What fraction of a resource's capacity is busy? | CPU %, thread busy time, pool/queue fill level | 100% does not necessarily mean efficient; an underutilized resource may be blocked by a bottleneck elsewhere |
| **Stability** | Is quality maintained under sustained, fluctuating, or spiking load? | Latency/throughput variance, errors, backlog, recovery time | Good results for a few seconds, followed by degradation after a few minutes |

Metrics must be measured **over the same work boundary and the same time window**. For example, whole-application throughput should not be compared directly against the latency of only a single data-access step. With concurrency, you must also account for rejected, expired, canceled, and failed requests; counting only successful requests hides overload conditions.

## 2. Latency: Time to Complete a Task

For a task submitted to an `ExecutorService`, you can break down:

`total latency = queue wait time + scheduling wait time + execution time + I/O/lock wait time + finalization overhead`.

This is a conceptual breakdown; phases may overlap and must not be double-counted. The starting point must be explicit: from when the user sends the request, from when the application receives it, or from when `executor.execute()` is called? If you only start the timer when `Runnable.run()` begins, you **omit queue wait** and easily overestimate system performance.

- **Service time**: the time spent actively serving a task after it starts running; may include I/O wait time if defined at the task level.
- **Queueing time**: the time from receipt/submission until processing begins; typically grows very rapidly near saturation.
- **Response time**: end-to-end time at the chosen system boundary, usually what users care about.
- **Tail latency**: slow requests at the tail of the distribution, especially p95/p99, easily affected by lock contention, GC, the scheduler, load spikes, and slow external calls.

For example, if 100 requests have 95 finish in 20 ms and 5 take 1,000 ms: most users experience very fast responses, yet the mean is 69 ms and p99 is near 1,000 ms. A single average value does not describe tail experience. p50 is the median; p95/p99 is the threshold not exceeded by roughly 95%/99% of samples under the chosen estimation method. With small sample sizes, percentiles are noisy; always record sample size, time window, and statistical algorithm.

Latency also has two meanings to distinguish: **latency of completed requests** and **wait time of requests still in-flight or queued**. If you only measure completed requests, hung or timed-out requests can be hidden. When generating load with a benchmark tool, avoid *coordinated omission*: a tool that sends the next request only after the previous one finishes automatically slows down when the system slows down, hiding stall-induced delays. To study a fixed arrival load, you need a load generator with an independent schedule that also records schedule slips, rejections, and timeouts.

## 3. Throughput: Tasks Completed per Unit of Time

The basic formula:

`throughput = completed tasks / observation window`.

For example, completing 6,000 tasks in 60 seconds corresponds to 100 tasks/s. You must define clearly what **completed** includes: successes, errors, rejections, or all terminal outcomes. Typically, you should track separately:

- **Arrival rate (λ)**: number of tasks arriving per second.
- **Admission rate**: number of tasks accepted for processing; may be lower than arrival rate due to load shedding.
- **Completion rate**: number of tasks finishing per second, split into success/failure.
- **Backlog**: accepted tasks that have not yet completed; includes both queued and running tasks.

When the arrival rate consistently exceeds the completion rate, backlog grows. A non-full queue does not prove the system is healthy: it may be accumulating work and driving latency higher and higher. If tasks are dropped, the completion rate of admitted work may look good while the overall request service rate is poor. Always report successful throughput alongside rejection rate and error rate.

Increasing concurrency helps throughput when there is waiting time or idle CPU capacity. Once CPU is saturated, adding threads usually only increases context switching, memory/lock contention, and queueing time. For I/O-bound tasks, the number of concurrent tasks can exceed CPU core count, but practical limits usually lie in connections, memory, downstream services, or shared resource capacity.

## 4. Utilization: How Busy, and Busy Where?

You can think of a resource's utilization as:

`utilization ≈ resource busy time / total available resource service time`.

This definition is only meaningful when you specify the **resource**: CPU, workers in a thread pool, connections, disk, or an exclusive lock. These measurements must not be conflated:

| Observation | Plausible Interpretation | Further Checks Needed |
| --- | --- | --- |
| CPU near 100% | Compute tasks have hit the CPU limit | CPU quota/cgroup, GC, profiling, context switching |
| Low CPU but high latency | Threads are `BLOCKED`/`WAITING`, waiting on I/O, locks, or queues | Thread dump, JFR, queue/lock/I/O time |
| `activeCount == maximumPoolSize` | Pool workers were busy at the sampling instant | Is the pool waiting on I/O, is the queue growing, task duration |
| Queue stays long | Processing capacity cannot keep up during that period | Arrival/completion rate, age of oldest task |
| Low CPU and low throughput | Bottleneck may be on a non-CPU resource | Connection limits, synchronization, rate limits |

For example, one thread holding a lock and executing slowly can leave 100 other threads waiting: CPU is not necessarily high, yet latency is terrible. Conversely, an independent compute-bound program that utilizes cores well often has high CPU and good throughput; high CPU **is not inherently a bug**. Inside containers, measure against the allocated CPU quota rather than assuming the host's physical core count. Host CPU percentage and container CPU percentage can have different denominators.

`ThreadPoolExecutor.getActiveCount()`, `getQueue().size()`, and `getCompletedTaskCount()` are useful for observing trends, but they are approximate snapshots and do not form an atomic, consistent measurement. Use them as monitoring metrics rather than exact criteria for business logic.

## 5. Relationship Between Latency, Throughput, Concurrency, and Load

**Little's Law** describes a long-term stable system:

`L = λ × W`

Where `L` is the **average number of tasks in the system**, `λ` is the **long-term throughput of the stable system** (tasks/second), and `W` is the **average time a task spends in the system** (seconds). All three must use the same system boundary. For example, a steady throughput of 200 requests/s and an average response time of 0.1 s implies an average of about 20 *in-flight* requests, including both waiting and running. Do not infer that you need exactly 20 platform threads or that increasing threads to 20 will achieve 200 requests/s.

A rough approximation for `m` independent workers, each with average service time `S`, is:

`ρ ≈ λ × S / m`.

For instance, with 4 workers, each task occupying a worker for an average of 20 ms, and an arrival rate of 150 tasks/s, `ρ ≈ 150 × 0.02 / 4 = 0.75`. This is **only a load estimate** in a simplified model: lock/I/O wait times, variance, bursts, heterogeneous task sizes, and worker skew can make real-world behavior differ significantly.

As `ρ` approaches 1, queueing delay typically increases nonlinearly, especially when service time varies. A system may reach peak throughput at high load while failing its p99 target. Therefore, production "capacity" should mean **sustainable throughput that simultaneously satisfies latency and error limits**, not just the highest tasks/s number observed in a short test.

Distinguish between experiment types:

1. **Fixed concurrency / closed-loop**: N clients always submit a new task when the previous one finishes; when the server slows down, the load generation rate drops automatically.
2. **Fixed arrival rate / open-loop**: attempts to send on a schedule of 100, 200, 300 requests/s; exposes queueing, timeouts, and overload much more clearly.
3. **Burst test**: applies a short traffic spike then returns to normal; measures queue peak and recovery time.
4. **Soak test**: sustains load long enough to observe heap, GC, threads, connections, resource leaks, and degradation over time.

Never take results from different test types and treat them as the same performance characteristic.

## 6. Measuring Correctly in Java

Measure **elapsed intervals** with `System.nanoTime()`; do not use `System.currentTimeMillis()` for short measurements because wall-clock time can jump and its resolution is unstable. `nanoTime()` is a monotonic clock suitable for computing differences between two calls within the same JVM, not a timestamp to persist or compare across machines.

When collecting metrics, record at least these timestamps: **accepted**, **started**, **finished**. From them, compute queue wait = started − accepted and end-to-end latency = finished − accepted. Also record terminal status (success/error/rejected/timeout/canceled), active count, queue depth, and oldest wait time. For multi-phase tasks, measure I/O wait, lock hold time, or synchronization blocking separately when needed.

For test runs with millions of requests, do not store every duration in an unbounded `List`. Use a bounded-memory histogram or an appropriate metrics library; document your sampling/percentile estimation method. Combining percentiles from multiple groups via arithmetic mean is **wrong**: you must merge distributions/histograms using a compatible method or recompute from samples.

### Java 17 Example: Bounded Executor and Wait Time Measurement

The following program illustrates separating queue wait time from submitted-to-finished time. It uses a `ThreadPoolExecutor` with 2 platform workers and a bounded queue of 4 elements. When full, `CallerRunsPolicy` makes the submitting thread run the task, applying backpressure to the load generator. `sleep` merely simulates waiting; this is **not a proper benchmark or production capacity test**.

~~~java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public class PerformanceDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 20;
        LongAdder completed = new LongAdder();
        ConcurrentLinkedQueue<Long> queueWaitNanos =
                new ConcurrentLinkedQueue<>();
        ConcurrentLinkedQueue<Long> totalNanos =
                new ConcurrentLinkedQueue<>();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4),
                new ThreadPoolExecutor.CallerRunsPolicy());

        long testStarted = System.nanoTime();

        for (int i = 0; i < taskCount; i++) {
            long acceptedAt = System.nanoTime();
            pool.execute(() -> {
                long startedAt = System.nanoTime();
                queueWaitNanos.add(startedAt - acceptedAt);

                try {
                    Thread.sleep(30); // Simulate an I/O-waiting task.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    totalNanos.add(System.nanoTime() - acceptedAt);
                    completed.increment();
                }
            });
        }

        pool.shutdown();
        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            throw new IllegalStateException("Executor timeout");
        }

        long elapsedNanos = System.nanoTime() - testStarted;
        System.out.println("Completed: " + completed.sum());
        System.out.printf(Locale.ROOT,
                "Observed throughput: %.1f tasks/s%n",
                completed.sum() / (elapsedNanos / 1_000_000_000.0));
        System.out.printf(Locale.ROOT,
                "Average queue wait: %.1f ms%n",
                averageMillis(queueWaitNanos));
        System.out.printf(Locale.ROOT,
                "Average submitted-to-finished: %.1f ms%n",
                averageMillis(totalNanos));
    }

    private static double averageMillis(ConcurrentLinkedQueue<Long> samples) {
        return samples.stream()
                .mapToLong(Long::longValue)
                .average()
                .orElse(0.0) / 1_000_000.0;
    }
}
~~~

Save as `PerformanceDemo.java` and run:

~~~bash
javac PerformanceDemo.java
java PerformanceDemo
~~~

The first line of stdout is always `Completed: 20` when the program exits normally. The next three measurements are **non-deterministic**, as they depend on the scheduler, CPU state, and host machine. In this example, `CallerRunsPolicy` may execute tasks directly on the `main` thread; therefore, the observed throughput reflects the entire run (including `main`), not just the two workers. This also slows down submission under saturation, so do not use this test to conclude that an application can sustain a fixed arrival rate.

If tasks can fail, replace `completed` with outcome-classified counters; `finally` in the example only means "the execution path ended," not that the task succeeded. If tasks can be interrupted, define a cancellation policy and count cancellations separately. If `execute()` is called after the pool has been `shutdown()`, `CallerRunsPolicy` does not run the task; submission design must have a clear lifecycle.

### Reading Percentiles Instead of Only the Average

Suppose you have collected a non-empty set `latenciesNanos` from the same observation window, such as a load sample. A simple percentile estimator is *nearest rank*:

~~~java
import java.util.List;

public class PercentileExample {
    static long percentile(List<Long> latenciesNanos, double p) {
        if (latenciesNanos.isEmpty() || p <= 0 || p > 1) {
            throw new IllegalArgumentException("Invalid samples or p");
        }
        List<Long> sorted = latenciesNanos.stream().sorted().toList();
        int index = (int) Math.ceil(p * sorted.size()) - 1;
        return sorted.get(index);
    }

    public static void main(String[] args) {
        List<Long> ms = List.of(10L, 12L, 15L, 20L, 100L);
        System.out.println("p95 = " + percentile(ms, 0.95) + " ms");
    }
}
~~~

Save as `PercentileExample.java`; `javac PercentileExample.java` then `java PercentileExample` outputs `p95 = 100 ms`. The example passes milliseconds to a parameter named `latenciesNanos` to illustrate order statistics; the method **returns values in whatever unit the input uses**. In real systems, standardize on nanoseconds at the measurement layer and convert to milliseconds for display. Nearest-rank is just one convention; comparing two systems requires using a consistent percentile method.

## 7. How Concurrency Configuration Affects All Four Metrics

### 7.1. CPU-Bound

Tasks such as encryption, image processing, or pure computation are typically limited by available cores and cache efficiency. If `P` CPU cores are actually allocated, testing concurrency near `P` is a reasonable starting point, then measure throughput and p99. Adding hundreds of platform threads to CPU-bound computation rarely increases compute capacity; it can make things worse due to context switching, cache contention, allocations, and GC. Do not treat the near-`P` rule as an immutable constant: the environment also has other processes, GC, and cgroup quotas.

### 7.2. I/O-Bound

Tasks waiting on network, disk, or responses from other resources can benefit from concurrency higher than the core count. With a platform thread pool, a thread blocked in `blocking I/O` still occupies a worker. A pool that is too small creates queueing; a pool that is too large consumes excessive memory and connections and puts pressure on downstream systems. Limit the number of concurrent tasks accessing a slow service using appropriate **bounded queues, semaphores, connection limits, and timeouts**, then measure.

Since Java 21, **virtual threads** fit many blocking I/O workloads well: they allow many waiting tasks without needing a dedicated platform thread per task. They **do not increase CPU core count**, do not automatically fix a bottlenecked database, and do not replace concurrency-limiting mechanisms. A "one virtual thread per task" executor imposes no limit on active requests; if a downstream resource can only handle 50 concurrent operations, enforce a limit of 50 with a semaphore or equivalent mechanism at that boundary. For code using `synchronized`, native calls, or specialized blocking libraries, evaluate pinning/carrier behavior and library support on your target JDK version using JFR and real profiling.

### 7.3. Locks, Contention, and Shared State

Locks protect correctness, but reduce the parallelism of critical sections. Adding workers when multiple workers contend on the same lock can cause throughput to plateau and tail latency to climb. Best practices:

- Keep lock-held sections short; avoid performing I/O or slow operations while holding a lock.
- Partition independent state where appropriate; use concurrent data structures with the right contracts, such as `ConcurrentHashMap` and `LongAdder` for high-frequency counters.
- Never replace synchronization with racy data access just to make a benchmark look good; correctness is always a prerequisite.
- Observe actual contention before optimizing. `LongAdder.sum()` is not an atomic snapshot under concurrent updates; it is suitable for monitoring metrics, not as a replacement for a strictly consistent counter.

### 7.4. Backpressure and Queues

A queue **does not create new processing capacity**; it only holds waiting work. An unbounded queue may reduce short-term rejections, but causes high latency, growing memory usage, and `OutOfMemoryError` under sustained overload. A bounded queue forces you to define behavior when full:

| Policy | Mechanism | Trade-off |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` when work cannot be accepted | Failures are explicit; caller must handle them |
| `CallerRunsPolicy` | The thread calling `execute` runs the task itself while the pool is running | Useful backpressure; can slow down the caller |
| `DiscardPolicy` | Drops the new task without throwing an exception | Risk of silent work loss |
| `DiscardOldestPolicy` | Drops the head of the queue and retries accepting the new task | May discard older work; requires understanding ordering/business value |

Choose a policy based on required guarantees: whether work loss is acceptable, whether order must be preserved, whether explicit errors are needed, and where retries happen. Timeouts, cancellations, and overload rejections must also be recorded in metrics. When a caller has a deadline, continuing to process work after the deadline has expired can waste resources and make queues harder to drain.

## 8. Stability: Sustained Performance Over Time and Changing Load

A stable system is not one with identical latency at all times; it is one capable of meeting chosen service thresholds, avoiding unbounded backlog growth, and recovering from fluctuations under designed conditions. Example test criteria:

- Under **150 requests/second** for **15 minutes**, p95 ≤ 100 ms, p99 ≤ 300 ms, errors + rejections ≤ 0.5%; all thresholds here are **illustrative assumptions**, not default SLOs for every application.
- With a burst of **300 requests/second for 10 seconds**, observe peak queue depth and require backlog to return to baseline within an acceptable time.
- Under sustained load, check whether memory/heap, allocation rate, GC pauses, thread count, file descriptors/connections, or throughput drift over time.

Typical instability signals: p99 creeps upward while throughput stays flat; queue remains elevated; GC pauses lengthen; thread/connection counts keep rising; retries pile load onto an already failing system; timeout rate rises while logged successful throughput still looks relatively healthy. Stability requires **load limits, queue bounds, deadlines, controlled retry policies, and resource observability**. Immediate synchronized retries after failure can trigger a retry storm and push effective load higher than the original traffic.

Stability also ties to correctness: race conditions, deadlocks, livelocks, or starvation can cause unbounded latency or leave a subset of tasks unserved even while CPU remains active. Never consider a concurrency optimization successful if it produces wrong results, loses tasks, or breaks ordering guarantees.

## 9. Experimental Process to Find the Balance Point

**Step 1 — Lock down boundaries and goals.** Pick a specific unit of work (a request, a task, a batch), and define success/failure, timeouts, measurement start/end, and test SLOs. For example: p99 < 200 ms, successful throughput ≥ 120 tasks/s, errors ≤ 0.1% over 10 minutes. These numbers only illustrate how to set targets.

**Step 2 — Establish a repeatable baseline.** Record JDK version, CPU/quota, RAM, garbage collector, heap size, worker count, queue capacity, task size and distribution, I/O resources, warm-up/JIT state, and load generator setup. Separate warm-up from the measurement window; run long enough and repeat multiple times before drawing conclusions. Avoid saturating the load generator itself.

**Step 3 — Step up load in controlled increments.** Test multiple arrival rates, not just a single "push until it breaks" run. At each step, monitor completions/s, p50/p95/p99, errors/rejections/timeouts, in-flight count, queue depth/age, CPU, GC, thread states, and downstream service health. If a queue remains after a step, wait for the system to return to baseline or reset the experiment state.

**Step 4 — Identify practical limits.** Find the highest load at which all thresholds are met sustainably. Watch for the "knee" or breaking point: throughput flattens, p99 spikes, queue grows, or error rate climbs. Observing queues and resources helps distinguish CPU, lock, I/O, and pool-size bottlenecks.

**Step 5 — Change one variable at a time.** For example, pool size 4 → 8, queue 100 → 200, or moving part of I/O work to virtual threads. Keep workload, metric definitions, and test duration comparable; verify speed, latency, correctness, and resource usage. You can trade higher latency for throughput, but it must be a measured trade-off that fits the SLO.

**Step 6 — Soak, burst, and recovery.** Test over long durations, during overload, and after load drops. Improving p50 for 30 seconds while causing steady heap growth after 30 minutes is not a successful optimization.

### Useful Java Tools

- **JDK Flight Recorder (JFR)**: inspect CPU samples, allocations, GC, thread scheduling/parking, monitor contention, I/O, and related events; correlate them with the exact time window where p99 spikes.
- **Java Mission Control (JMC)**: read and analyze JFR recordings to locate hot spots and wait times.
- **`jcmd <PID> Thread.print` / thread dump**: inspect thread states at a point in time to spot lock contention or deadlocks. A single dump is insufficient for trends; take several snapshots spaced apart.
- **JMH**: microbenchmarking for pure Java code, with warm-up/forking and mechanisms to reduce JIT bias; do not use a simple `nanoTime()` loop to judge the performance of a small algorithm. JMH results also do not directly predict end-to-end response time or capacity under real load.
- **CPU/heap/GC profilers and OS metrics**: identify throttling, allocations, GC, context switching, and limits outside the JVM.

## 10. Practical Diagnostic Scenarios

| Symptom | Hypothesis to Verify | Inspection / Adjustment Direction |
| --- | --- | --- |
| Throughput does not increase with more threads; CPU near limit | CPU-bound, scheduling overhead | CPU profile; test concurrency close to CPU quota |
| p99 rises, CPU low, many `BLOCKED` threads | Lock contention | JFR monitor events, thread dumps; shorten critical sections |
| Queue grows continuously, workers busy | Arrival rate exceeds service rate | Separate service time/queue time; limit input and inspect bottlenecks |
| p50 stable, p99 spikes suddenly | GC pauses, I/O tail, locks, bursts | Correlate p99 timestamps with JFR/GC/upstream events |
| Errors drop as queue grows, but latency spikes | Converting overload into waiting | Bounded queue, timeouts, explicit rejection, monitor queue age |
| Low CPU, many threads waiting on I/O, heap growing | Blocking I/O and unbounded concurrency | Limit in-flight/connections; evaluate virtual threads if appropriate |
| Benchmark very fast, production slow | Different workload or measurement boundary | Reproduce payload, arrival pattern, dependencies, warm-up, GC |
| Throughput degrades over long runs | Resource leaks, accumulation, retries | Soak test and monitor heap, connections, queues, GC |

Never conclude from a single signal. For example, low CPU can be caused by locks, but also by low arrival load; combine **arrival rate + completion rate + queue wait + resource metrics** to identify the root cause.

## 11. Common Mistakes to Avoid

1. **Increasing thread counts by gut feeling:** throughput may already be saturated; measure p99, CPU, queue, and error rate before and after.
2. **Reporting only average latency:** slow tail requests are hidden; add p95/p99, timeouts, and wait time of incomplete requests.
3. **Using unbounded queues to "never reject":** backlog and memory can grow until the process crashes.
4. **Treating submission rate as throughput:** measure *completed* tasks over the same time window and classify outcomes.
5. **Measuring only inside `run()`:** ignores queueing and admission time, underestimating response time.
6. **Mistaking virtual threads for unlimited parallel CPU:** virtual threads help manage blocking tasks, not multiply CPU cores or downstream capacity.
7. **Comparing benchmarks across different environments:** CPU quota, JIT, warm-up, GC, payload, and dependencies can outweigh code changes.
8. **Ignoring coordinated omission and incomplete requests:** reported latency can look artificially good while the system is stalled.
9. **Optimizing at the expense of correctness:** data races, deadlocks, lost tasks, or broken cancellation are failures, even if a short test shows high throughput.
10. **Intrusive measurement:** logging every task or storing unbounded samples can slow down the test itself; use controlled sampling or histograms.

## 12. Self-Check Questions

- A pool has 8 workers, all busy, yet CPU is only 20%. Can you conclude CPU is insufficient? **No**: you need to know whether workers are waiting on I/O, locks, or the scheduler, and inspect the queue.
- Throughput stays at 100 tasks/s, but p99 jumps from 80 ms to 2 s as load increases. Is this better capacity? **No**: the system may already be saturated; backlog and tail latency are worsening.
- Can you use `L = λW` to require creating exactly `L` Java threads? **No**: `L` is the number of tasks in the system, which may be queued or waiting on I/O, and the law requires steady-state conditions.
- If increasing queue size reduces rejections, is the system definitely better? **No**: it may be trading rejection errors for latency/timeouts or higher memory usage; evaluate against the full SLO.
- Why is measuring p99 for 10 seconds insufficient? **Because** small sample sizes, JIT/GC state, and load variance can make results unrepresentative; repeat, run longer, and record measurement conditions.

**Guiding principle:** design concurrency for **sustainable throughput with acceptable latency and error rates**, within clear resource bounds; observe the real bottleneck, apply backpressure, and verify stability under sustained load.
# Correlating Garbage Collection with Java Application Latency

## 1. Why Correlate GC with Latency?

**Garbage Collection (GC)** reclaims memory from objects that are no longer in use. This process frees the application from having to deallocate objects manually, but it can affect response times.

**Latency** is the time an operation or request takes to complete. In Java services, operators typically track p50, p95, p99, and maximum values rather than looking only at the average time.

GC can increase latency when the JVM needs to pause application threads to perform a stop-the-world (STW) phase. If a request is being processed during that pause, its completion time can increase. Requests arriving during a pause may also have to wait in a queue and subsequently continue experiencing the impact of the backlog.

The goal of the analysis is not to automatically blame GC whenever a latency spike occurs. You need to correlate the timing of slow requests with GC pauses, safepoints, allocation rates, heap state, and other factors to determine how much GC contributes to the latency.

## 2. Types of Latency to Distinguish

| Metric | Meaning | Question Answered |
|---|---|---|
| p50 | 50% of requests complete within or below this time. | What is the typical experience? |
| p90 | 90% of requests complete within or below this time. | How slow are most requests that are slower than normal? |
| p95 | 95% of requests complete within or below this time. | How significant is the tail latency? |
| p99 | 99% of requests complete within or below this time. | How affected is the slowest 1% of requests? |
| max | The slowest request in the measurement window. | Are there extreme outliers? |
| mean | The average time. | What is the average total processing time per request? |

Example:

| Metric | Before GC anomaly | During window with latency spike |
|---|---:|---:|
| p50 | 12 ms | 12 ms |
| p95 | 28 ms | 34 ms |
| p99 | 45 ms | 190 ms |
| max | 90 ms | 240 ms |

The table above illustrates a scenario: p50 remains nearly unchanged while tail latency increases sharply. This is why you need to examine the distribution rather than just the average.

Percentiles must be computed from a histogram or an appropriate sample set. Do not average the p99 values of multiple instances to produce a system-wide p99; instead, aggregate histogram buckets or appropriate request data and recalculate the percentile.

## 3. How GC Pauses Affect Requests

During an STW phase, the relevant application threads are stopped at a safepoint so the JVM can perform the required work. For example, G1 Young GC typically has an evacuation pause phase.

Suppose a request starts at 10:00:00.100 and requires 8 ms of CPU time. If the JVM pauses for 15 ms while the request is running, the wall-clock time of the request can increase by approximately the portion of the pause it spans.

Requests arriving while the JVM is paused may not yet be picked up by an application thread. When the JVM resumes, those requests have to wait additional time for the backlog to drain. Therefore, end-to-end latency can exceed the duration of a single GC pause.

To measure accurately, the request timer should start at ingress or the point where the request is received and end when the response is complete. If you only start measuring after the request is dequeued, the time spent waiting during a JVM pause may be missed.

A 10 ms GC pause does not mean every request in that minute increases by exactly 10 ms. Only requests whose execution overlaps with the pause or that have to wait on the backlog are directly affected.

## 4. Distinguishing GC Cycle, GC Pause, and Concurrent Phase

Not all of a GC cycle's duration is time during which the application is stopped.

| Concept | Meaning | Latency Impact |
|---|---|---|
| GC cycle | A collection cycle, which may consist of multiple phases. | Can span several seconds without necessarily stopping the application for that entire duration. |
| STW pause | The period during which application threads are stopped. | Can directly prolong in-flight requests or cause queues to grow. |
| Concurrent phase | GC works concurrently with application threads. | Can compete for CPU or memory bandwidth, slowing requests even without long pauses. |
| Safepoint | A state where the JVM brings threads to a safe point to execute a VM operation. | Some safepoints are GC-related; others are not. |

With concurrent collectors, you need to examine pause phases and concurrent phases separately. Do not take the duration of an entire concurrent cycle and treat it as STW time.

Concurrent GC can still reduce the CPU available to the application. When CPU saturation occurs, request latency can rise even if pauses are very short.

## 5. How Safepoints and GC Pauses Relate

GC pauses are typically executed at a safepoint. When reading logs, you can see the time to bring threads to the safepoint, the time spent at the safepoint, and the time to leave the safepoint.

Actual example on JDK 24.0.2:

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 35M->4M(64M) 2.200ms
Safepoint "G1CollectForAllocation", Reaching safepoint: 4800 ns, At safepoint: 2245200 ns, Leaving safepoint: 8300 ns, Total: 2258300 ns
~~~

How to read this:

- Heap changed from 35 MiB down to 4 MiB within a 64 MiB heap capacity.
- The reported GC pause is 2.200 ms.
- Application threads spent approximately 2.2452 ms at the safepoint.
- The total safepoint duration, including reaching and leaving, is approximately 2.2583 ms.

The numbers above are from a single test run and are for illustration only. GC pause duration and safepoint total can differ due to measurement methods and auxiliary stages.

Not every safepoint is caused by GC. Other VM operations, deoptimization, class redefinition, or certain runtime activities can also require a safepoint. Read the operation name and correlate it with the GC log before attributing the cause to GC.

## 6. Enabling Unified GC Logging on JDK 17+

Unified logging has been available since JDK 9. You can enable GC and safepoint logging with:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Meaning:

- gc*: logs tags related to GC, including collection, heap, and phase details.
- safepoint: logs safepoint activity.
- file=gc.log: writes to a file instead of printing only to the console.
- time: wall-clock date and time.
- uptime: time since JVM startup.
- level: log level.
- tags: tag group for each log event.

You can add log rotation to prevent the file from growing unbounded:

~~~bash
java -Xlog:gc*,safepoint:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

In this example, the JVM keeps up to five rotated files, each targeting 20 MiB. The filename includes the PID to distinguish processes.

For production, choose log levels and rotation settings suited to disk capacity, retention policies, and investigation needs. Do not leave overly verbose debug/trace logging running indefinitely without evaluating I/O overhead.

## 7. Reading Key Fields in a GC Log

A GC line typically provides the following information:

~~~text
[2026-11-10T20:19:51.994+0700][0.308s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 35M->4M(64M) 2.200ms
~~~

| Component | Meaning |
|---|---|
| 2026-11-10T20:19:51.994+0700 | Timestamp in local time with offset. |
| 0.308s | JVM uptime at the time of the log entry. |
| GC(0) | ID of the GC event within the process. |
| Pause Young | Collection type. |
| G1 Evacuation Pause | Cause or pause type according to the collector. |
| 35M->4M | Heap occupancy before and after collection. |
| (64M) | Heap capacity at that time. |
| 2.200ms | Logged pause duration. |

Subsequent heap and phase lines can show Eden, Survivor, Old regions, object promotion, and evacuation work. Read the entire block sharing the same GC ID to understand what the collection did.

Do not infer a memory leak from a single occupancy line. Observe the trend across many comparable GC cycles, especially post-collection usage and the growth rate of the live set.

## 8. Using Java Flight Recorder to Inspect GC and Safepoint Events

Java Flight Recorder (JFR) records events with timestamps and durations. You can enable recording at JVM startup:

~~~bash
java -XX:StartFlightRecording=filename=gc-latency.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Or start a recording on a running JVM:

~~~bash
jcmd 12345 JFR.start name=LatencyCapture settings=profile duration=5m filename=gc-latency.jfr
~~~

After the recording completes, view a summary:

~~~bash
jfr summary gc-latency.jfr
~~~

Print GC and safepoint events:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCPhaseConcurrent,jdk.SafepointBegin,jdk.SafepointEnd gc-latency.jfr
~~~

Useful events:

| JFR event | Data to inspect |
|---|---|
| jdk.GarbageCollection | Collector name, cause, duration, sumOfPauses, and longestPause. |
| jdk.GCPhasePause | Duration of each pause phase. |
| jdk.GCPhaseConcurrent | Duration of concurrent GC phases. |
| jdk.SafepointBegin | Timestamp and duration of the safepoint. |
| jdk.GCHeapSummary | Heap usage before/after collection or at recorded points. |
| jdk.ObjectAllocationSample | Allocation samples to understand the object creation workload. |

Events can vary by JDK and collector. Use the JDK's own metadata or `jfr summary` to confirm which events are present in the recording.

The JFR `profile` settings collect more detail than `default` and can increase overhead. Choose a sufficiently short recording window and evaluate overhead if using it in production. JFR events record GC timing and causes, but do not by themselves prove that a specific request was slow because of that event.

## 9. Aligning Request Latency with the GC Timeline

To correlate GC with latency, you need a shared timeline.

One approach:

1. Record latency histograms over short time windows, such as 1 second or 10 seconds.
2. Record timestamps of GC pauses and safepoints.
3. Record request timestamps or trace spans when investigating an outlier.
4. Use the same timezone or common time reference for comparison.
5. Mark windows where latency rises concurrently with pauses.
6. Identify which requests were running or queued during the pause.
7. Compare against windows without GC pauses to establish a baseline.

GC logs contain both wall-clock timestamps and JVM uptime. JFR contains event start times and durations. Applications should use `System.nanoTime()` to measure request duration because it is a monotonic clock and is not affected by system clock adjustments.

If you need to align request durations with the GC log, also record a wall-clock timestamp at the start or export trace spans with start times. Do not compare `nanoTime` values directly against GC log date-time timestamps; the two clocks have different origins.

Correlation is a coincidence in timing or trend between a latency spike and a GC event. Causation requires additional evidence, such as requests actually overlapping the pause, backlog growing after the pause, or a controlled experiment reproducing the behavior. Correlation alone does not prove causation.

You do not need to log every request in production if volume is high. You can use histogram metrics to track the distribution and selective sampling/tracing to investigate outlier requests.

## 10. Reading a Latency Histogram in the Same Window as GC Pauses

Example over a 10-second window:

| Metric | Normal window | Window with GC pauses |
|---|---:|---:|
| Request count | 12.000 | 12.500 |
| p50 | 14 ms | 14 ms |
| p95 | 32 ms | 41 ms |
| p99 | 58 ms | 180 ms |
| GC pause count | 0 | 3 |
| Longest GC pause | 0 ms | 24 ms |

If p99 rises in a window with three GC pauses, that is a signal for further investigation. It does not prove that GC caused the entire 122 ms difference in p99.

Check the following:

- Do the pauses coincide with the timestamps of slow requests?
- Did any requests span multiple pauses or wait on a backlog after a pause?
- Do the slow requests share the same endpoint, route, or dependency?
- Were there changes in CPU, locks, network, or database during the same window?
- Does p99 remain elevated in windows without GC pauses?

If latency increases continuously while GC pauses are short and rare, the cause may lie in concurrent GC CPU pressure, application CPU, queueing, or another dependency.

## 11. Relating Pause Duration to the Latency Budget

Suppose an API has a p99 latency objective under 200 ms. A 25 ms GC pause can consume a significant portion of that budget if it occurs while requests are in flight.

However, comparing pause duration directly to p99 is only a first step. The impact depends on:

- The fraction of requests in flight when the pause begins.
- Arrival rate and queue depth.
- Thread pool size.
- Request timeout and retry behavior.
- The number of pauses in a window.
- Throughput recovery time after the pause.

A 20 ms pause during low traffic may not produce noticeable tail latency. That same pause during peak hours can build a backlog and cause many requests to finish much later than 20 ms.

Set a pause budget based on the latency objective, but do not use a single GC duration threshold as the sole criterion. You need to monitor pause frequency, longest pause, allocation rate, throughput, and request histograms together.

## 12. Calculating Pause Time Ratio and GC Pressure

Useful metrics include:

- Total pause time in the window.
- Number of pauses in the window.
- Longest pause.
- Pause time / wall-clock time.
- Allocation rate.
- Promotion rate or old-generation growth.
- Heap occupancy after collection.
- Concurrent GC CPU time.

For example, in a 60-second window with 600 ms of total STW pause time:

\[
\text{Pause ratio} = \frac{0.6}{60} \times 100\% = 1\%
\]

A 1% pause ratio does not mean latency only increases by 1%. A pause concentrated right at peak traffic can heavily impact p99 even when the overall pause ratio is low.

For concurrent collectors, do not add the entire concurrent phase duration into the STW pause ratio. Concurrent work can reduce the CPU available to application threads, but it does not stop all threads.

Exporter metric names vary. For example, a Prometheus/JMX exporter may expose counters or histograms for GC pauses, collection counts, and durations; verify the actual metric names and units in your system.

## 13. Differences Between Garbage Collectors

| Collector | Characteristics to examine when analyzing latency |
|---|---|
| Serial GC | Collection is primarily stop-the-world; pauses can be large as heap or live set grows. |
| Parallel GC | Prioritizes throughput; pauses can be longer when many objects need to be collected. |
| G1 GC | Has STW evacuation pauses and concurrent phases; monitor both individual pauses and concurrent cycles. |
| ZGC | Designed for short pauses with most work concurrent; still measure pauses and concurrent CPU impact. |
| Shenandoah | Performs most work concurrently but still has some pause phases; inspect specific events. |

Do not apply the same Eden/Old interpretation or the same pause threshold to every collector.

A concurrent collector does not guarantee low latency. Concurrent work competes with the application for CPU, memory bandwidth, and cache. If CPU is near saturation, latency can increase even with tiny STW pauses.

Check the active collector with:

~~~bash
jcmd 12345 VM.flags
~~~

Record the JDK vendor, version, collector, and flags when comparing results across environments.

## 14. Signs That GC May Be Part of the Cause

The following signs help guide the investigation:

### p99 rises at the exact time of STW pauses

If outlier request timestamps overlap with GC pauses and request durations increase by a roughly corresponding amount, there is stronger evidence of a direct pause impact.

### Multiple consecutive pauses and growing queues

A dense sequence of Young GCs can cause application threads to spend significant time waiting. If post-pause throughput is insufficient to clear the backlog, latency can remain elevated after GC finishes.

### Allocation rate rises before a latency spike

Allocation pressure can cause Young GC to occur more frequently. Inspect the allocation profile and workload changes before resizing the heap or switching collectors.

### Concurrent GC coincides with CPU saturation

If concurrent phases are prolonged, application CPU can drop. Monitor process CPU, GC CPU time, run queue, and application throughput.

### Full GC or rare long pauses

A long Full GC can create large outliers. Check the cause, heap occupancy, live set, promotion failures, humongous allocations, and memory pressure.

## 15. Other Factors That Can Cause Latency Spikes

Not every latency spike is caused by GC. Other causes include:

- CPU saturation or threads delayed by the scheduler.
- Lock contention, synchronized blocks, or partial deadlocks.
- Thread pool exhaustion or queue backlog.
- Network latency, packet loss, or DNS.
- Slow database queries, connection pool exhaustion, or database locks.
- Disk I/O, page faults, or container throttling.
- JIT compilation, deoptimization, or class loading.
- Non-GC-related safepoints.
- Retry storms, traffic bursts, or downstream timeouts.

If a GC pause is only 2 ms but requests jump from 20 ms to 500 ms, you need to find where the rest of the time was spent. Do not attribute the entire outlier to GC just because a GC event occurred in the same minute.

## 16. Running a Controlled Experiment to Verify the Hypothesis

To test whether GC impacts latency:

1. Choose a fixed workload and representative data.
2. Keep the JDK, collector, heap size, and thread count fixed.
3. Record request latency histograms.
4. Record unified GC logs.
5. Repeat the workload for the same duration.
6. Change one factor at a time, such as allocation rate or heap size.
7. Compare pause count, longest pause, allocation rate, and p95/p99.
8. Repeat enough times to assess variance.
9. Validate in a production-like workload before applying.

Do not call `System.gc()` in a benchmark to create artificial pauses and conclude that it represents production behavior. That call can trigger a Full GC or be handled differently depending on JVM configuration; it does not faithfully simulate real allocation pressure.

Do not change heap size, collector, thread count, and workload simultaneously, as it will be difficult to isolate which factor caused the difference.

## 17. Practical Example: Measuring Latency During Allocation

Create the file **GcLatencyProbe.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicLongArray;

public class GcLatencyProbe {
    private static final int BUCKETS = 64;
    private static final AtomicLongArray HISTOGRAM = new AtomicLongArray(BUCKETS);
    private static final AtomicLong MAX_NANOS = new AtomicLong();
    private static final long[] CHECKSUMS = new long[4];

    private static final class Worker implements Runnable {
        private final int id;
        private final CountDownLatch ready;
        private final CountDownLatch start;

        Worker(int id, CountDownLatch ready, CountDownLatch start) {
            this.id = id;
            this.ready = ready;
            this.start = start;
        }

        @Override
        public void run() {
            ready.countDown();
            try {
                start.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            long checksum = 0;
            long operations = 0;
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(6);

            while (System.nanoTime() < deadline) {
                long requestStart = System.nanoTime();

                byte[] payload = new byte[16 * 1024];
                long value = 0;
                for (int i = 0; i < payload.length; i += 64) {
                    payload[i] = (byte) (i + operations);
                    value += payload[i];
                }

                checksum += value;
                long elapsed = System.nanoTime() - requestStart;
                int bucket = 63 - Long.numberOfLeadingZeros(Math.max(1L, elapsed));
                HISTOGRAM.incrementAndGet(bucket);
                MAX_NANOS.accumulateAndGet(elapsed, Math::max);
                operations++;
            }

            CHECKSUMS[id] = checksum;
        }
    }

    private static long percentileUpperBound(long total, double percentile) {
        long target = (long) Math.ceil(total * percentile);
        long cumulative = 0;
        for (int bucket = 0; bucket < BUCKETS; bucket++) {
            cumulative += HISTOGRAM.get(bucket);
            if (cumulative >= target) {
                return bucket == 63 ? Long.MAX_VALUE : 1L << (bucket + 1);
            }
        }
        return MAX_NANOS.get();
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(4);
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(
                    new Worker(i, ready, start), "request-worker-" + i);
            workers[i].start();
        }

        ready.await();
        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        long total = 0;
        for (int i = 0; i < BUCKETS; i++) {
            total += HISTOGRAM.get(i);
        }

        long checksum = 0;
        for (long value : CHECKSUMS) {
            checksum += value;
        }

        System.out.printf("operations=%d%n", total);
        System.out.printf("p50_upper_us=%.3f%n",
                percentileUpperBound(total, 0.50) / 1000.0);
        System.out.printf("p95_upper_us=%.3f%n",
                percentileUpperBound(total, 0.95) / 1000.0);
        System.out.printf("p99_upper_us=%.3f%n",
                percentileUpperBound(total, 0.99) / 1000.0);
        System.out.printf("max_us=%.3f%n", MAX_NANOS.get() / 1000.0);
        System.out.printf("checksum=%d%n", checksum);
        System.out.println(
                "Note: percentiles are upper bounds from a base-2 histogram.");
    }
}
~~~

The probe uses four worker threads. Each operation allocates a 16 KiB array, writes and reads a few bytes, and records the elapsed time with `System.nanoTime()`. The histogram uses log₂ buckets, so the percentiles are bucket upper bounds rather than nanosecond-exact percentiles.

This example measures a synthetic allocation operation inside the JVM. It does not simulate an HTTP server, network, database, or queueing of a real service. Use it to observe how pauses can show up in operation processing times.

## 18. Compiling and Running with GC Logs and JFR

Compile with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 GcLatencyProbe.java
~~~

Run with G1, a 64 MiB heap, unified GC/safepoint logging, and JFR:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*,safepoint:file=gc-latency.log:time,uptime,level,tags -XX:StartFlightRecording=filename=gc-latency.jfr,settings=profile,dumponexit=true GcLatencyProbe
~~~

After the program finishes, inspect the GC log:

~~~bash
findstr /i "Pause Young Pause Full G1CollectForAllocation" gc-latency.log
~~~

Read the JFR summary:

~~~bash
jfr summary gc-latency.jfr
~~~

Print relevant events:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCPhaseConcurrent,jdk.SafepointBegin,jdk.SafepointEnd gc-latency.jfr
~~~

These commands were verified on JDK 24.0.2 with Java 17-compatible source code. The GC log captured Young pauses and safepoint breakdowns; both `jfr summary` and `jfr print` read the recording successfully.

If using PowerShell, let `jfr summary` finish running before filtering output. Piping directly to `Select-Object -First` can close stdout early and cause the native command to return a non-zero exit status even though the recording file is valid.

## 19. Results from a Verification Run

A probe run on JDK 24.0.2 with four workers, G1, and a 64 MiB heap produced:

~~~text
operations=4985025
p50_upper_us=4.096
p95_upper_us=8.192
p99_upper_us=8.192
max_us=497116.200
checksum=-638435584
Note: percentiles are upper bounds from a base-2 histogram.
~~~

In the same run, the GC log recorded a Young pause of approximately 2.200 ms and a safepoint total of approximately 2.2583 ms.

The max latency of about 497 ms is much larger than the observed GC pause. This is a useful illustration: a large outlier cannot be automatically attributed to GC. OS scheduling, thread delays, JFR overhead, or environmental factors may contribute. You need to correlate the timestamps of individual requests and events before drawing conclusions.

The numbers above are the output of one specific run, not fixed results. On subsequent runs, operation counts, histograms, and max latency will vary with CPU, OS, JDK, collector, and background load.

## 20. Using Metrics and Tracing in Real Services

In production, monitor latency and GC at the same time resolution.

Useful metric groups:

| Group | Metrics |
|---|---|
| Request | Request count, p50, p95, p99, timeout, and error rate. |
| GC | Pause count, pause duration, longest pause, and collection cause. |
| Heap | Heap used, heap after GC, old-generation occupancy. |
| Allocation | Allocation rate, promotion rate, and object allocation profile. |
| CPU | Process CPU, container CPU throttling, GC CPU, and run queue. |
| Thread/queue | Active threads, queue depth, rejected tasks, and lock contention. |

Specific metric names depend on Micrometer, JMX exporter, OpenTelemetry, or the monitoring agent. Verify metric units and semantics before correlating them.

Distributed tracing helps identify whether a request was slow in the application, database, network, or a downstream service. Use trace IDs and timestamps to correlate spans with the GC timeline. Avoid excessive logging for every request when volume is high; histograms and sampling can reduce observability overhead.

## 21. Ways to Reduce GC-Related Latency

Choose mitigations after identifying the root cause:

### Reduce Unnecessary Allocations

- Avoid creating temporary objects on hot paths when more suitable structures can be used.
- Reduce unnecessary array or buffer copies.
- Review boxing/unboxing, string concatenation, and collection churn.
- Reuse buffers only when ownership and concurrency are properly controlled.

### Reduce Live Set and Object Retention

- Bound caches and queues.
- Set TTLs for temporary data.
- Avoid holding references longer than needed.
- Check class loaders, listeners, and collections that retain unnecessary objects.

### Choose an Appropriate Heap and Collector

- Measure allocation rate and live set before changing `Xms`/`Xmx`.
- Check container memory limits and native memory.
- Compare collectors under realistic workloads.
- Set pause goals or collector flags according to the documentation for the JDK in use.

### Tune Concurrency and Workload

- Inspect thread pools and queue depths.
- Limit allocation bursts if the workload can be throttled.
- Avoid retry storms after a long pause.
- Monitor post-GC throughput to see whether the application can drain the backlog in time.

Increasing the heap can reduce collection frequency but may also make some pauses longer or increase memory footprint. Switching collectors does not automatically solve allocation pressure or CPU saturation. Every change should be benchmarked and validated under a production-like workload.

## 22. Common Analysis Mistakes

| Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| Concluding GC caused a latency spike because GC occurred in the same minute | The time window is too wide and other causes may be present. | Correlate request timestamps with specific pauses. |
| Treating GC cycle duration as STW pause time | A cycle may include multiple concurrent phases. | Inspect `GCPhasePause` and pause durations. |
| Looking only at average latency | Tail outliers are hidden. | Monitor p95/p99 and histograms. |
| Looking only at heap used | Does not show pauses, allocation rate, or post-GC live set. | Combine heap, allocation, GC, and request metrics. |
| Assuming every safepoint is GC | Many VM operations are unrelated to GC. | Read the safepoint operation name and GC ID. |
| Assuming concurrent GC cannot affect latency | Concurrent work can compete for CPU and memory bandwidth. | Monitor GC CPU, process CPU, and throughput. |
| Drawing conclusions from a single max latency | Max is sensitive to scheduler jitter and noise. | Repeat measurements, inspect the distribution, and trace outliers. |
| Calling `System.gc()` to simulate production | Not representative of real allocation and live-set behavior. | Use a workload that generates application-like allocations. |
| Comparing collectors with different heaps or traffic | Cannot isolate the cause. | Keep the environment and workload constant. |
| Ignoring time requests spend waiting in queues | Can miss pause impact on requests not yet being processed. | Measure end-to-end from ingress to response. |

## 23. GC and Latency Investigation Workflow

A repeatable workflow:

1. Define the latency objective and the spike window.
2. Check p50/p95/p99, request count, errors, and timeouts.
3. Identify the affected instance or JVM.
4. Read the GC log by timestamp and uptime.
5. Find pauses, durations, causes, and heap before/after.
6. Check the safepoint breakdown for reaching/at/leaving times.
7. Open JFR and inspect `GarbageCollection`, `GCPhasePause`, `GCPhaseConcurrent`, and allocation events.
8. Correlate request traces or histograms with the GC timeline.
9. Check CPU, thread pools, queues, locks, network, and database.
10. Identify which requests actually overlapped a pause or suffered post-pause backlog.
11. Form a hypothesis and change one factor in a controlled experiment.
12. Compare results across multiple runs on an equivalent workload.
13. Re-verify p99, throughput, allocation, and pauses after the change.

An investigation report should record the JDK version, collector, JVM flags, heap size, workload, timestamps, GC cause, pause duration, and request percentiles. This enables others to verify the conclusions.

## 24. Checklist Before Concluding That GC Increased Latency

- [ ] Measured request latency from ingress to response.
- [ ] Monitored p50, p95, p99, and request count.
- [ ] Enabled GC logging with timestamps and uptime.
- [ ] Enabled safepoint logging when STW analysis is needed.
- [ ] Identified the collector and JDK version.
- [ ] Distinguished GC cycle, STW pause, and concurrent phase.
- [ ] Correlated slow request timestamps with specific pauses.
- [ ] Checked GC cause and heap before/after.
- [ ] Inspected JFR GC events and allocation events.
- [ ] Checked queue depth and request backlog.
- [ ] Checked CPU, scheduler, locks, network, and database.
- [ ] Distinguished correlation from causation.
- [ ] Repeated a controlled experiment.
- [ ] Validated changes with a production-like workload.

## 25. References

- Oracle JDK 24 — Unified Logging: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — Diagnostic Tools and Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Java Flight Recorder event reference: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html
- Java SE 17 System.nanoTime(): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()

GC can affect requests directly through STW pauses and indirectly through concurrent CPU pressure or backlogs. To prove impact, correlate request latency histograms and traces with GC/safepoint timestamps, distinguish pauses from concurrent phases, and rule out competing causes before changing the heap or collector.
# How to Draw Conclusions from a JFR Recording

Java Flight Recorder (JFR) records runtime events with timestamps, durations, threads, stack traces, and related metadata. A recording can help explain why an application is slow, why CPU usage is high, why GC takes a long time, or why threads are waiting on locks or I/O. However, a recording only provides evidence for the captured time window and the set of enabled events. To reach reliable conclusions, you need to clearly define the symptom, verify data quality, correlate events along a timeline, and distinguish direct observations from root-cause hypotheses.

This guide uses JDK 17 or later and JDK Mission Control (JMC). It covers validating a recording, reading Automated Analysis Results, analyzing CPU, threads, locks, I/O, allocation, and GC, comparing against a baseline, understanding sampling limitations, and writing a verifiable conclusion.

## 1. What Evidence Does a Recording Provide?

JFR collects events emitted by the JVM and the application. Depending on configuration, events can describe:

- JVM and machine CPU load; method samples and stack traces of running threads.
- Threads that are parked, sleeping, waiting on a monitor, or blocked acquiring a lock.
- Socket read/write and file read/write operations.
- Allocation samples and TLAB-related allocations.
- Garbage collection, GC phases, and pauses.
- Thrown exceptions/errors; thread start/end; class loading; safepoints.
- Custom events defined and emitted by the application.

Each event may include a timestamp, duration, event thread, stack trace, and event-specific fields. Not every event has all fields; some are instantaneous events, some have a duration, and some are statistical samples.

A recording is useful for answering questions that map to collected events:

- During which interval did CPU spike, and which threads have the most method samples?
- How long did critical threads wait on locks or sockets?
- How much of the observation window was spent in GC pauses?
- Which classes or stack traces generated the most allocations?
- Which exceptions occurred frequently during the incident window?

JFR does not automatically know which requests were slow unless the application emits custom events or uses tracing to correlate requests. Nor does it prove causality simply because two phenomena appear at the same time.

## 2. Define Questions Before Opening the Recording

Start by writing down the symptom and the time window:

- Did users experience increased latency, reduced throughput, or request timeouts?
- Was high CPU isolated to the JVM or across the entire machine?
- Did heap usage grow, were GC pauses long, or was the allocation rate high?
- Were threads blocked, waiting on locks, waiting on sockets, or waiting on queues?
- When did the incident start and end?
- Did workload, traffic, batch size, or configuration change?

| Symptom | First Analysis Questions |
|---|---|
| High CPU | Is the JVM using high CPU? Which threads/methods are sampled most often? |
| Slow requests | Is time spent in code, locks, sockets, file I/O, or GC pauses? |
| Heavy GC | Is the allocation rate high, is the live set large, or are individual GC pauses too long? |
| Thread growth | Which threads were created, which are still alive, and what are they doing? |
| Timeouts | Are there I/O wait, lock, park, or custom request timeout events at the same time? |
| Rising errors | Which exceptions/errors appear, and on which threads and stacks? |

Do not start by picking an unusual-looking event and declaring it the cause. First define the time window and impact you need to explain.

## 3. Inspect the Recording Before Interpreting It

Open the file in JMC or inspect it from the command line:

~~~powershell
jfr summary recording.jfr
jfr metadata recording.jfr
~~~

The `summary` command shows the recording duration, event counts by type, and general overview information. The `metadata` command displays the event types and fields defined in the file.

Verify:

1. Does the file open cleanly and contain events?
2. Do the start and end times cover the incident window?
3. Does the recording include the workload that actually experienced the issue?
4. Are the relevant CPU, thread, lock, I/O, GC, or allocation events present?
5. Were stack traces recorded for the events under investigation?
6. Are the event thresholds and sampling intervals appropriate?
7. Are there gaps caused by stopped recordings, rotation, or missing data?
8. Do the JVM version, GC, VM arguments, and recording settings match the target environment?

If the recording started after the incident ended, it cannot explain that phase. If a required event was disabled, the absence of that event does not prove the phenomenon did not occur.

### 3.1. Align the Timeline

Record the recording's start/end times, timezone if known, JVM uptime, and incident timestamps from logs/monitoring. Align the timeline across JFR, application logs, reverse proxies, databases, and metrics.

Mark startup/warm-up, normal workload, high-traffic or batch periods, the incident window, and recovery. A long recording can contain multiple workload phases; analyze the symptomatic window separately.

### 3.2. Check Event Thresholds

Many events have a duration threshold. In common configurations, many Java Application events are only recorded when their duration exceeds a threshold; JDK 17 documentation cites a default of around 20 ms as an example for several event types. Thresholds can be changed in the recording settings.

Therefore:

- Having no monitor contention events does not prove there were no short lock waits.
- Seeing no socket read events does not mean there was no network I/O; short operations may be below the threshold or the event may be disabled.
- Lowering thresholds captures more events but increases data volume and overhead.
- When investigating short waits, take a short recording with a lower threshold and measure its impact.

Check settings and metadata before using event counts as negative evidence.

## 4. Start with Automated Analysis Results in JMC

The **Automated Analysis Results** page summarizes potential signals across groups such as Java Application, JVM Internals, and Environment. Yellow and red findings help prioritize investigation; they are alerts based on recorded data, not automated verdicts on root cause.

Workflow:

1. Open the `.jfr` file in JMC.
2. Read **Automated Analysis Results**.
3. Note warnings directly related to the symptom.
4. Open the corresponding detail pages from the Outline.
5. Select the time range where the anomaly appears.
6. Inspect the underlying events, threads, classes, stack traces, and durations.
7. Cross-check against independent logs and metrics.

Do not rely on colored scores alone. Verify with specific events, counts, total duration, timestamps, and stack traces.

## 5. Drawing Conclusions About CPU and Code Execution

When CPU is high, distinguish JVM CPU usage from overall machine CPU usage.

### 5.1. CPU Load

The `jdk.CPULoad` event provides JVM and machine CPU load at sample times:

- High JVM load and high machine load: the JVM may be a significant CPU consumer.
- Low JVM load but high machine load: another process may be consuming CPU.
- Both low: the high-CPU symptom may lie outside the recording window or have already ended.

Cross-check with Task Manager, `top`, `pidstat`, or host/container monitoring. JFR values are periodic samples, not continuous absolute measurements.

### 5.2. Method Samples and Stack Traces

JFR uses method sampling to capture the stacks of threads executing code. In JMC, check **Method Profiling**, **Hot Methods**, **Call Tree**, or the Java Application page depending on your version.

How to read them:

1. Select the high-CPU time window.
2. Identify methods with prominent sample counts.
3. Open the call tree to see which code paths call that method.
4. Find the first frame belonging to your application package.
5. Inspect multiple stack traces and threads; avoid optimizing a method just because it appears in a single sample.
6. Correlate with workload and completed request counts.

Method samples show where threads were sampled while running. They do not directly measure the exact duration of individual method calls. Low sample counts make conclusions less reliable.

### 5.3. Per-Thread CPU

If `jdk.ThreadCPULoad` events are present in the recording, use them to see which threads have notable CPU load. Combine this with method samples to identify the code running on those threads.

- A request worker thread with high CPU load and a call tree concentrated in a data-processing method: that method is a candidate for deeper profiling.
- Low JVM CPU load but high host load: check other processes.
- A thread with few method samples but high latency: the thread may be spending time waiting on locks/I/O rather than executing on CPU.

Do not conclude a thread has high CPU solely from total event count; check the time range, event types, and sample coverage.

## 6. Drawing Conclusions About Thread Waits and Synchronization

Threads may not be executing code because they are waiting on a lock, parked, sleeping, waiting in a queue, or waiting on another condition.

| Event | Meaning |
|---|---|
| `jdk.JavaMonitorEnter` | Thread waiting to enter an intrinsic monitor, typically `synchronized` |
| `jdk.JavaMonitorWait` | Thread called `Object.wait()` and is waiting for notification/timeout |
| `jdk.ThreadPark` | Thread parked via mechanisms such as `LockSupport`/AQS |
| `jdk.ThreadSleep` | Thread sleeping via `sleep` |
| `jdk.ThreadStart` / `jdk.ThreadEnd` | Thread lifecycle |

### 6.1. Monitor Enter and Monitor Wait

`JavaMonitorEnter` relates to time spent waiting to acquire a monitor. If many critical threads wait on the same lock and total wait time is large, that critical section may be a bottleneck.

`JavaMonitorWait` relates to `Object.wait()`. This is a condition-wait mechanism; the thread releases the monitor while waiting and must reacquire it before continuing after notification or timeout.

Do not lump both event types together into a conclusion of "lock held too long." Read the event type, monitor class/identity, thread, and stack trace.

### 6.2. Identifying Lock Contention

In JMC, open **Lock Instances** or the corresponding synchronization page:

1. Sort by total blocked time or contention count.
2. Select lock instances with high impact.
3. Inspect the waiting threads and their stack traces.
4. Locate the application code holding or requesting the lock.
5. Check whether the critical section contains I/O, logging, heavy data processing, or slow calls.
6. Compare against request latency during the same period.

If many request threads wait on the same lock while throughput drops, there is evidence that contention contributes to the bottleneck. Identify the lock owner and relevant code path before proposing changes.

### 6.3. ThreadPark and Thread Pools

`ThreadPark` can occur when a thread waits in an executor, queue, semaphore, future, or synchronizer. Parking is not automatically a bug; idle workers normally park while waiting for new tasks.

- Idle worker pool waiting for tasks: typically normal.
- All workers parked waiting on a future whose completion requires the same pool: possible thread starvation.
- Request threads parked waiting on a queue or semaphore while latency rises: check concurrency limits and producer/consumer rates.
- Threads parked waiting for an external response: correlate with I/O or timeouts.

A single park event does not reveal the full dependency chain. Correlate across multiple threads and timestamps.

## 7. Drawing Conclusions About I/O and Network

Commonly used events are `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, and `jdk.FileWrite`.

In JMC, open **Socket I/O** or **File I/O**. Inspect duration, byte counts, remote address/host or file path if provided by the event, thread, and stack trace.

- Long socket read duration: thread waiting for data from the peer or across the network path.
- Long socket write duration: slow writes, slow peer reads, or buffer/network backpressure.
- Long file read/write: storage, filesystem, or file operations may contribute to latency.
- Many events targeting the same host/endpoint: check that dependency and corresponding server-side metrics.

Do not conclude that a remote server is slow solely from a socket read. Duration can include network transit time, peer processing, congestion, or protocol behavior. Cross-check with tracing, peer logs, network metrics, and timeouts.

If no I/O events appear, check whether the events were enabled and whether thresholds filtered out short operations.

## 8. Drawing Conclusions About Garbage Collection

GC can affect performance in two main ways: a single GC with a long pause stalls requests; or high cumulative pause time causes the application to spend too much time not doing useful work.

Useful events include `jdk.GarbageCollection`, `jdk.GCPhasePause`, heap summary events, and allocation events.

### 8.1. Look at GC Pauses, Not Just GC Duration

Many collectors perform concurrent work while application threads continue running. The total duration of a GC does not necessarily equal the time the application was paused.

To evaluate pauses, check `jdk.GCPhasePause` and the sum of pause durations per GC ID. In JMC, open the **Garbage Collections** page and the pause / sum-of-pauses charts.

Track GC count, total pause time in the observation window, maximum pause, GC type/cause, heap before/after GC if recorded, allocation rate, and live set.

### 8.2. Interpreting GC

| Observation | Hypothesis to Verify |
|---|---|
| Frequent young GCs, high allocation rate | High short-lived object creation is increasing collection demand |
| A few unusually long pauses | Specific GC phases or heap pressure may be impacting latency |
| Full GCs occurring alongside heap pressure | The JVM may lack headroom or need to reclaim long-lived objects |
| High total pause time from many short pauses | Cumulative pauses may be hurting throughput/latency |
| Low GC time but requests are still slow | Look for locks, I/O, CPU, queues, or other dependencies |

Do not increase heap size or switch collectors based on a single recording alone. First verify whether pauses coincide with latency spikes, whether the live set is growing, how high the allocation rate is, and what the current heap configuration is.

### 8.3. Heap Statistics

In JDK 17, enabling Heap Statistics can trigger old GCs at the start and end of the recording, introducing extra pauses and altering the very system being measured. When your goal is normal latency/performance measurement, avoid enabling this option unless you are investigating live set size or a memory leak and accept the impact.

## 9. Drawing Conclusions About Allocation and Memory Retention

Allocation events help locate where objects are created; heap and old-object data help investigate objects that remain alive.

Common events include `jdk.ObjectAllocationSample`, `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB`, `jdk.ThreadAllocationStatistics`, and `jdk.OldObjectSample` when configured and supported by the recording.

Use JMC's **TLAB Allocations** view to inspect allocations by class, thread, and stack trace. For `ObjectAllocationSample`, the `weight` field is an estimated byte amount represented by the sample; do not count events as an exact object count.

- High allocation rate with stable post-GC heap: likely many temporary objects.
- High allocation rate alongside frequent young GCs: allocation pressure may be contributing to increased GC work.
- Heap/live set growing across multiple cycles: investigate retained objects.
- Old object samples with long-lived reference chains: trace back to GC roots to find the owner.

An allocation hotspot does not prove a memory leak. Conversely, a leak can come from objects allocated infrequently but retained indefinitely. When you need to confirm retention, use a heap dump and analyze reference chains.

## 10. Drawing Conclusions About Exceptions and Errors

If the recording includes `jdk.JavaExceptionThrow` and `jdk.JavaErrorThrow`, inspect the exception/error type, thread, stack trace, timestamp, and occurrence count.

An exception that is thrown and caught can be normal control flow; not every exception indicates an incident-causing failure. Focus on exceptions that spike during the incident window, repeated identical stack traces, errors related to resource exhaustion, and exceptions paired with request failures, retries, or timeouts in logs.

JFR events do not necessarily capture full messages or business payload data. Combine them with application logs, metrics, and traces to understand real impact.

## 11. Reading a Recording Along a Timeline

A strong conclusion connects signals in chronological order.

Hypothetical example:

1. Request rate increases.
2. Allocation rate increases in request worker threads.
3. Young GCs occur more frequently.
4. Total GC pause time rises during the high-latency window.
5. After request rate drops, allocation and GC activity also decrease.

This sequence supports the hypothesis that workload object creation increased GC pressure. To make the conclusion stronger, compare the same workload against a baseline and inspect allocation stack traces.

Another example:

1. Request latency increases.
2. Multiple request workers wait on the same monitor.
3. A lock instance shows high total blocked time.
4. Stack traces point to a logging method inside a `synchronized` section.
5. After changing the logging/critical section, a new recording shows reduced blocked time.

This is stronger evidence because it connects timing, lock identity, stack traces, and a before/after change. Even then, verify throughput and latency to confirm the improvement.

## 12. Comparing a Good Recording and a Bad Recording

When possible, capture one recording during normal operation and another when the symptom occurs. Keep conditions as similar as possible:

- Same application version and JDK.
- Same GC and VM arguments.
- Same recording template and event thresholds.
- Comparable duration.
- Comparable workload, traffic, and batch size.
- Same way of measuring latency and throughput.

| Category | Metrics to Compare |
|---|---|
| CPU | JVM/machine CPU load, method samples, and thread CPU |
| Threads | Thread count, thread stalls, parks, and monitor blocked duration |
| I/O | Event count, bytes, duration, and endpoint/file |
| GC | GC count, pause sum, max pause, and heap trend |
| Allocation | Weighted bytes, class, thread, and stack trace |
| Exceptions | Event type, count, and stack trace |
| Workload | Request rate, throughput, latency, and timing |

Do not compare raw total bytes or event counts if the recordings have different durations. Use per-second rates, per-request ratios, or deltas over equal intervals.

## 13. Using `jfr` to Inspect Events from the Terminal

View summary and metadata:

~~~powershell
jfr summary recording.jfr
jfr metadata recording.jfr
~~~

Print CPU, thread, lock, I/O, GC, and allocation events present in the recording:

~~~powershell
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite,jdk.GarbageCollection,jdk.GCPhasePause,jdk.ObjectAllocationSample recording.jfr
~~~

Print exceptions:

~~~powershell
jfr print --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow recording.jfr
~~~

Save filtered events to a file:

~~~powershell
jfr print --events jdk.JavaMonitorEnter,jdk.SocketRead,jdk.GCPhasePause recording.jfr > selected-events.txt
~~~

An event type not present in the recording produces no output when printed. Use `summary` and `metadata` to check actual event types before filtering. For large recordings, filter to the needed events or use JMC to filter by time range and criteria.

## 14. Hands-on Example: Creating a Recording with CPU, Lock, and Allocation Activity

Create `RecordingConclusionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class RecordingConclusionDemo {
    private static final Object LOCK = new Object();
    private static volatile byte[] lastBuffer;
    private static int criticalSections;

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        for (int worker = 0; worker < 4; worker++) {
            final int workerId = worker;
            tasks.add(pool.submit(() -> {
                try {
                    start.await();
                    for (int i = 0; i < 6; i++) {
                        synchronized (LOCK) {
                            Thread.sleep(30);
                            criticalSections++;
                        }
                        byte[] buffer = new byte[512 + (i * 16)];
                        buffer[0] = (byte) workerId;
                        lastBuffer = buffer;
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }));
        }

        start.countDown();
        for (Future<?> task : tasks) {
            task.get();
        }
        pool.shutdown();

        long checksum = 0;
        for (int i = 0; i < 5_000_000; i++) {
            checksum += (i * 31L) % 97;
        }
        lastBuffer = new byte[(int) (checksum % 4096) + 1];

        for (int i = 0; i < 100_000; i++) {
            byte[] temporary = new byte[256 + (i & 1023)];
            temporary[0] = (byte) i;
            lastBuffer = temporary;
        }

        System.out.println("Workers completed: 4");
        System.out.println("Critical sections: " + criticalSections);
        System.out.println("Allocation loop completed: 100000");

        // Keep the JVM alive long enough for the recording to collect events.
        Thread.sleep(22_000);
    }
}
~~~

The program intentionally generates three kinds of activity:

- Four workers contend on the same monitor; sleeping inside `synchronized` is only used to create observable lock waits, not as a production coding pattern.
- The checksum loop creates compute work so method sampling has a chance to observe it.
- The array loop generates allocations; a `volatile` field holds the latest reference so the objects are not optimized away completely as dead data.

Compile:

~~~powershell
javac RecordingConclusionDemo.java
~~~

Run and record JFR for 20 seconds:

~~~powershell
java -XX:StartFlightRecording=name=conclusion,settings=profile,duration=20s,filename=conclusion.jfr RecordingConclusionDemo
~~~

The stdout lines printed by the program after the workers finish:

~~~text
Workers completed: 4
Critical sections: 24
Allocation loop completed: 100000
~~~

The JVM may print additional recording startup messages depending on the JDK version. Actual events and sample counts depend on the runtime, machine, and JFR settings; do not expect identical event output across runs.

After the recording completes:

~~~powershell
jfr summary conclusion.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ExecutionSample,jdk.ObjectAllocationSample conclusion.jfr
~~~

Open `conclusion.jfr` in JMC:

1. Check **Lock Instances** to inspect monitor waits.
2. Check **Method Profiling** to inspect methods sampled during the checksum workload.
3. Check **TLAB Allocations** to inspect array allocations.
4. Compare event timestamps against the worker execution phase and the main thread sleep phase.
5. Write a separate conclusion for each signal and cite the supporting events/stacks.

If an event type does not appear, check recording settings, thresholds, and workload timing. Do not fabricate results based on the example's expected output.

## 15. Distinguishing Observation, Interpretation, and Root Cause

When writing conclusions, separate three levels:

| Level | Example |
|---|---|
| Observation | In the 14:02–14:04 window, request workers recorded many long `JavaMonitorEnter` durations on the same monitor. |
| Interpretation | Workers had to wait on the same critical section; contention may be increasing request processing time. |
| Confirmed Root Cause | Stack traces and source code show the critical section held the lock during synchronous logging; after changing it, re-measurement showed reduced blocked duration. |

An observation is what the recording directly shows. An interpretation is the meaning inferred from the events. A confirmed root cause requires additional evidence such as source code, logs, dependency metrics, heap/reference analysis, or a before/after experiment.

Use wording that matches your level of certainty:

- **Observed:** events and metrics present in the recording.
- **Likely:** evidence aligns, though alternative hypotheses remain.
- **Insufficient data:** missing events, mismatched time windows, or non-representative workload.
- **Confirmed:** backed by independent evidence or a reproducible verification test.

Do not write "JFR proves" when the recording only shows two events occurring at the same time.

## 16. Template for Writing a Conclusion from a Recording

A concise, verifiable report should include:

~~~text
1. Scope
   - Recording file:
   - JDK/VM:
   - Recording time window:
   - Workload and symptoms:

2. Data Quality
   - Required events present/missing:
   - Stack traces present/missing:
   - Thresholds/template:
   - Missing time intervals:

3. Observations
   - Metric/event:
   - Timestamp:
   - Duration/count/weight:
   - Related thread/class/stack:

4. Interpretation
   - What the recording supports:
   - Remaining hypotheses:
   - Missing evidence:

5. Conclusion and Confidence
   - Conclusion:
   - Confidence level: high / medium / low
   - Rationale:

6. Verification Steps
   - Logs/metrics/source to cross-check:
   - Next experiment or recording:
   - Success criteria:
~~~

Example of a well-grounded conclusion:

> During the 14:02–14:04 window, multiple request workers recorded monitor wait times on the same lock instance. Event stack traces concentrated in `OrderService.updateCache()`. This indicates that contention in this critical section likely contributed to increased latency. The recording does not capture the full duration the lock owner held the monitor; source inspection and a follow-up recording under an equivalent workload are needed to confirm the fix after making changes.

This example clearly states scope, events, stack traces, confidence level, and what needs to be verified next.

## 17. Limitations to Document in Conclusions

- JFR only records enabled events and cannot recover missed events.
- Event thresholds can omit short operations.
- Method profiling is sampling, not a trace of every method call.
- Allocation samples carry estimated weights, not a complete list of every object.
- Recordings without custom request events may not correlate directly with request/trace IDs.
- A recording may not cover the start or end of a symptom.
- Coinciding events do not prove causality.
- JMC Automated Analysis Results provide warnings/suggestions; the analyst must verify the underlying events.
- Differences in workload, JVM flags, JDK, GC, and environment make results hard to compare.
- Recordings can incur noticeable overhead and file size depending on event settings.

For standard performance recordings, Oracle notes that overhead is typically low in many applications; however, you must measure it on your actual workload. Heap Statistics can trigger old GCs at the start and end of a recording and cause significant pauses, so do not enable it when the goal is measuring normal latency.

## 18. Common Mistakes When Drawing Conclusions

| Mistake | Why It Is Wrong | How to Fix It |
|---|---|---|
| Seeing no events and concluding there is no problem | Events may be disabled or below threshold | Check event settings and thresholds |
| Treating the most-sampled method as the slowest in absolute terms | Sampling does not measure exact per-call duration | Use samples to rank hotspots, then profile/benchmark |
| Equating GC duration with application pause time | Many GC phases run concurrently | Check `GCPhasePause` and total pause time |
| Equating high allocation with a memory leak | Temporary objects may be reclaimed quickly | Cross-check post-GC heap and retained objects |
| Assuming `ThreadPark` always means a hung thread | Idle workers normally park | Read the stack, thread role, and timeline |
| Concluding a remote server is slow from long `SocketRead` alone | Duration includes network and peer factors | Cross-check logs/metrics on both ends and tracing |
| Treating one recording as proof of a regression | Workload, settings, or timing may differ | Capture baseline and bad runs under comparable conditions |
| Changing multiple things at once and claiming improvement | Cannot isolate which change produced the effect | Change one factor at a time and re-measure |

## 19. End-to-End Investigation Workflow

1. Write down a measurable question and symptom.
2. Identify PID, JDK, GC, VM arguments, and workload.
3. Capture a recording covering the incident window with appropriate event settings.
4. Run `jfr summary` and verify metadata/event coverage.
5. Open JMC and read **Automated Analysis Results**.
6. Open the relevant pages: CPU/Methods, Threads, Locks, Socket/File I/O, GC, or Allocations.
7. Record timestamps, event types, durations/counts/weights, threads, and stack traces.
8. Correlate events along a timeline and cross-check with request rate, latency, logs, and host/container metrics.
9. Separate observation, interpretation, root-cause hypothesis, and confidence level.
10. Identify missing evidence and design an experiment or follow-up recording to verify.
11. Make one controlled change at a time.
12. Capture a post-change recording under equivalent workload and settings.
13. Compare before/after metrics and confirm impact on latency, throughput, CPU, GC, or contention.
14. Store recordings and reports in a location with appropriate access controls.

## 20. Checklist for Drawing Conclusions from a JFR Recording

- [ ] Investigation questions and symptoms are clearly defined.
- [ ] The recording covers the incident window and a representative workload.
- [ ] JDK, VM, GC, template, and recording duration are documented.
- [ ] `jfr summary` and event metadata have been checked.
- [ ] Required events and stack traces are confirmed present in the file.
- [ ] Thresholds and sampling limitations have been accounted for.
- [ ] Automated Analysis Results have been reviewed and underlying events verified.
- [ ] CPU/method samples checked if code execution is suspected.
- [ ] Threads, monitors, parks, and lock instances checked.
- [ ] Socket/file I/O checked if external dependencies are suspected.
- [ ] GC pauses checked separately from total GC duration.
- [ ] Allocation pressure distinguished from retained heap.
- [ ] Events correlated along a timeline and against workload.
- [ ] Observation, interpretation, and root cause kept separate.
- [ ] Confidence level and missing data documented.
- [ ] Measurable verification steps proposed.
- [ ] Before/after recordings compared under comparable conditions.
- [ ] Recordings protected and sensitive information redacted before sharing.

A good JFR conclusion always states what the recording captured, when it occurred, on which threads and stacks, and what hypothesis it supports. Use CPU samples, thread stalls, locks, I/O, GC pauses, and allocations to pinpoint where to investigate; cross-check workload and baseline before calling something the root cause. Document event/sampling limitations, confidence level, and next measurements to turn a conclusion into a testable hypothesis.

## References

- Oracle, Java SE 17 Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle, Java SE 17 Diagnostic Tools — Analyze a Flight Recording: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle, Java SE 17 — The jfr Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle, Java SE 17 — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Java SE 17 — Flight Recorder Configurations: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html
- Oracle, Java SE 17 API — jdk.jfr package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html

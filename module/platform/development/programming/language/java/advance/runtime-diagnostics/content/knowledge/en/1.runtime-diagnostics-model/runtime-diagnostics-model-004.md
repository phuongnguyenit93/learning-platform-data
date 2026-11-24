# 1.4 — Map of Logs, Metrics, Stack Traces, Thread Dumps, Heap Dumps, and JFR Recordings

## 1. Objective: Choose the Right Evidence for the Right Question

When a Java application is slow, failing, using high CPU, or growing in memory, six common types of evidence are **logs**, **metrics**, **stack traces**, **thread dumps**, **heap dumps**, and **Java Flight Recorder (JFR)**. They observe the same JVM process at different resolutions and across different time dimensions. None of them completely replaces the others.

After this lesson, you should be able to answer: (1) what each type of evidence measures or records; (2) which one to collect first for each symptom; (3) how to read, combine, and verify hypotheses; (4) the operational costs, limitations, and risks of collecting them in real environments.

> Investigation rule: **symptom → testable question → appropriate evidence → hypothesis → cross-check with additional evidence**. A single snapshot or a single chart is usually insufficient to conclude the cause.

## 2. Map of the Six Evidence Types

| Evidence | Unit of Observation | Time Dimension | Question It Answers Best | Core Limitations |
| --- | --- | --- | --- | --- |
| **Log** | A business or technical event with context | Points in time when events are recorded | *Which request failed, and which input/processing branch was involved?* | Only shows what was logged; can be incomplete or noisy |
| **Metrics** | Aggregated values: counters, gauges, histograms… | Time series by window | *When did errors/slowness/load rise, and how widespread is it?* | Usually does not pinpoint the specific request or line of code |
| **Stack trace** | Call chain of a single thread at the moment of error/observation | A single instant | *Which call path led to the error or current execution point?* | One stack does not represent all threads or history |
| **Thread dump** | States and stacks of multiple Java threads in the JVM | Instantaneous snapshot; can be taken repeatedly | *Which threads are BLOCKED/WAITING/RUNNABLE, waiting on what lock or resource?* | A snapshot does not prove how long a thread has been there |
| **Heap dump** | Object graph on the Java heap and reference relationships | Memory snapshot | *Which objects are retained, who holds them, and why hasn't GC reclaimed them?* | Heavy, sensitive; does not directly describe CPU or all native memory |
| **JFR recording** | JVM/application events, durations, sampled stacks | Time range with timestamps | *Over a few minutes, what happened with CPU, allocation, GC, locks, and I/O?* | Uses sampling/thresholds and event configs; does not record every call |

**Two axes to remember:**

- **Snapshot vs. timeline:** stack traces, thread dumps, and heap dumps show state at sampling time; metrics, logs, and JFR reveal evolution over time. Multiple thread dumps spaced a few seconds apart form a sequence of snapshots, yet still not a complete history.
- **Breadth vs. depth:** metrics cover the system; logs locate specific requests; stack traces inspect call paths; thread dumps inspect thread coordination; heap dumps inspect the object graph; JFR connects multiple views with events and timestamps.

For example, "heap reached 90%" is a **symptom** from metrics. It does not prove a memory leak: the application might be holding a valid cache, GC might not have run yet, or the heap might rise and then stabilize. You need to inspect **post-GC** heap, multi-window trends, and, when justified, retained objects in a heap dump.

## 3. Preparing Context Before Collection

Record the **service**, environment, build/JDK version, start and end times of the anomaly, timezone, instance/pod, PID, load (RPS), error rate, and most recent changes (deploys, flags, traffic). Synchronize clocks across hosts, logs, and monitoring systems to correlate events accurately.

- Distinguish the **JVM PID on the host** from the PID inside a container; `jcmd` must run where it can attach to the JVM, typically the same host and same effective user/group.
- Define the **incident window** and a **normal baseline** for comparison. If charts use 5-minute averages while logs have millisecond precision, align them to the same window before concluding.
- Capture easy-to-collect, low-intrusion evidence first. Consider duration, file size, free disk space, and latency impact before taking dumps or enabling deep recording settings.
- Label every artifact with timestamp, instance, PID, and version. An unlabeled `threads.txt` is easily miscorrelated with `incident.jfr`.

## 4. Logs: What Did the Application Record?

Logs are intentional event records: request start/end, processing errors, retries, timeouts, state transitions, and external system interactions. Ideal logs include timestamp, level, service/instance, operation name, `traceId`/`requestId`, error code, duration, and permitted business fields.

```text
2026-01-15T10:15:01.240Z WARN service=checkout traceId=7f21 operation=reserveStock durationMs=1800 result=timeout
2026-01-15T10:15:01.245Z ERROR service=checkout traceId=7f21 operation=placeOrder error=InventoryTimeout
```

These two **illustrative** lines let you link two steps via `traceId=7f21` and spot an upstream timeout. They do **not** by themselves prove network congestion, locks, or CPU exhaustion; you must verify with metrics and evidence on the relevant service.

**How to read and emit useful logs:**

1. Find an error spike or slow request, then filter by the same service, timestamp, and trace ID.
2. Read the event sequence in order, distinguishing the initial error message from "consequential" errors thrown at higher layers.
3. Preserve full exceptions including `Caused by`; generic messages like "request failed" are rarely enough.
4. Use structured logging with stable field names; avoid free-form concatenation that makes searching/filtering hard.
5. Choose `INFO`/`WARN`/`ERROR` levels meaningfully; `DEBUG` can help short-term investigation but increases volume and latency.

**Do not log** passwords, tokens, card numbers, sensitive payloads, or unnecessary personal data. Log sampling or rate limiting can mean not every request has complete logs. The absence of a log line does **not** prove an event did not happen.

## 5. Metrics: Scale, Trends, and Anomaly Onset

Metrics represent measurements over time:

- **Counter** only increases (e.g., `requests_total`, `errors_total`); compute the **rate of increase over a window**, and avoid directly comparing cumulative values from two different process restarts.
- **Gauge** can rise and fall (e.g., active threads, queue depth, heap used, connection count).
- **Histogram** records distributions of observations (e.g., request latency); supports viewing p50/p95/p99. **p99** means roughly 99% of observations in the examined dataset do not exceed that threshold, not the duration of "the worst request."

The **RED** group for services: **Rate** (traffic), **Errors** (failures), **Duration** (latency). Pair with process/host CPU, GC pauses, heap used/committed/max, thread count, connection pools, and queue depth depending on symptoms.

Examples of grounded analysis:

1. RPS is nearly flat, p99 spikes sharply, and the thread pool is saturated: suspect **contention or downstream waits**, though metrics alone cannot decide which one.
2. Process CPU nears its limit while p99 increases: collect JFR CPU sampling, compare GC and thread dumps; do not automatically assume the application is in an infinite loop.
3. Heap used rises with load and drops after GC: could be normal allocation. If the **post-GC floor** rises steadily across many cycles, suspect long-lived object retention and consider a heap dump.
4. Error rate = errors / requests in the same window; watch for small denominators and label cardinality. Never attach raw user IDs or request IDs as metric labels because unbounded string cardinality explodes series count.

A chart with 1-minute resolution can hide a 2-second spike. Pay attention to aggregation (`sum`, `avg`, `max`), denominators, latency distributions, and scrape/sampling intervals. Metrics are **pointers to where to dig deeper**, not standalone proof of cause.

## 6. Stack Traces: Call Path at a Point in Time

A stack trace lists frames with class name, method, file, and line number, typically appearing when an exception is logged. Read from the exception message and `Caused by` clauses to trace the origin, while checking relevant application frames (many framework frames are just forwarding layers).

```text
java.lang.IllegalStateException: Could not create order
    at example.OrderService.create(OrderService.java:42)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at example.OrderService.readQuantity(OrderService.java:19)
```

This is a **structural illustration**, not stdout from a program in this lesson. Line `OrderService.java:19` points to where input is parsed; inspect the data and error handling there rather than blaming `Integer.parseInt` just because a library frame appears. For nested exceptions, `Caused by` often explains the deeper cause; `Suppressed` (e.g., when closing resources) can also hold clues.

**Distinction:** an exception stack trace is the call path leading to an error on **one thread**. A thread dump contains stacks and states for **many threads**, even when no exception occurred. With async/`CompletableFuture`, task/queue boundaries can break call-stack continuity; correlation IDs and tracing connect the steps.

Do not conclude "method X consumes 90% CPU" simply because it appears in one stack trace. You need CPU profiling/JFR across many samples.

## 7. Thread Dumps: What Are Many Threads Doing or Waiting On?

Use when requests hang, thread pools are exhausted, deadlocks are suspected, many requests wait on locks, or CPU is high without knowing which threads are involved. Thread dumps show thread names, states, stacks, monitors, and certain lock information.

Java states to interpret carefully:

| `Thread.State` | Cautious Interpretation |
| --- | --- |
| `RUNNABLE` | Eligible to run from the JVM's perspective; may be executing or in certain native/I/O operations. Does not automatically mean it is consuming CPU. |
| `BLOCKED` | Waiting to enter a `synchronized` monitor; find the thread holding the monitor and the associated call path. |
| `WAITING` | Waiting indefinitely via mechanisms like `Object.wait`, `Thread.join`, `LockSupport.park`; often normal for idle workers. |
| `TIMED_WAITING` | Waiting with a timeout such as `sleep` or timed wait/park/join; inspect frames to see if it is abnormal. |
| `NEW` / `TERMINATED` | Not yet started / completed; rarely the focus in a running process thread dump. |

Collect with JDK 17+ (replace `<pid>` with the actual PID):

```bash
jcmd -l
jcmd <pid> Thread.print -l > threads-t1.txt
```

To detect **persistent conditions**, take 2–3 dumps spaced roughly 5–10 seconds apart during the incident; record each dump's timestamp. Compare whether threads and stacks remain stuck at the same wait point or are merely passing through. `-l` adds `java.util.concurrent` lock information if supported by the JVM. If attach fails, check PID, permissions, container/namespace, and the JVM's command list with `jcmd <pid> help`.

**How to analyze:** group threads by name and stack, identify active vs. idle pools, trace "waiting to lock" ↔ "locked" chains and monitor owners; look for wait cycles if deadlock is suspected. A thread `WAITING` in `ThreadPoolExecutor.getTask` is likely an **idle worker**, not a deadlock. Multiple threads `BLOCKED` on the same monitor or repeatedly at the same wait point is a much stronger signal.

Thread dumps only capture specific instants. Do not use a single snapshot to prove lock-wait duration or CPU cause; combine with JFR events, throughput, and timings of slow requests.

## 8. Heap Dumps: Who Is Retaining Java Heap Memory?

A heap dump (usually HPROF) records the object graph, classes, sizes, and reference paths at a point in time. It is especially useful when **post-GC** heap continues rising, on `OutOfMemoryError: Java heap space`, or when suspecting caches/sessions/listeners retaining unneeded objects.

From a heap dump, tools like Eclipse Memory Analyzer (MAT) provide:

1. **Class histogram:** which classes have many instances or consume the most memory.
2. **Shallow size:** size of the object itself; **retained size:** memory that can be freed if that object and objects reachable only through it become unreachable.
3. **Dominator tree:** which objects/subtrees retain most of the heap; do not equate "largest" with "bug" if that data is an intentionally designed cache.
4. **Path to GC roots:** reference chain from a GC root (static field, thread, JNI handle…) to the suspected object; this explains **why the object is still alive**.

Example command for HotSpot JDK 17+:

```bash
jcmd <pid> GC.heap_dump /var/tmp/incident-heap.hprof
```

The path must be writable by the **target JVM process** and have sufficient disk space. This is a **high-impact** operation: it can cause pauses and consume significant CPU, RAM, I/O, and disk space; by default `GC.heap_dump` triggers a full GC unless `-all` is used. Weigh timing and operational authorization before running in production. Startup option to dump automatically on Java heap OOM:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/app-oom.hprof -jar app.jar
```

Must be configured at startup with guaranteed storage space. A heap dump does not directly explain **native/off-heap memory**, file descriptors, or high CPU; do not automatically assume every OOM is a heap leak. A single snapshot also does not prove **growth rate**: compare metrics or two dumps when cost permits.

**Security:** heap dumps can contain tokens, sessions, passwords, and user data inside objects. Transfer and store only in access-controlled locations with retention/deletion policies and restricted sharing.

## 9. JFR: JVM Event Timeline and Observation Samples

**Java Flight Recorder** produces a `.jfr` file containing time-stamped events, such as CPU execution samples, allocations, GC, monitor contention, thread parks, I/O, and some environment metadata; **actual events depend on configuration and thresholds**. JFR excels at answering "what happened before, during, and after the spike?" or correlating CPU, GC, locks, and code paths.

- `default.jfc` is generally suitable for continuous low-overhead recording; `profile.jfc` collects deeper detail for short investigation windows and can consume more resources.
- "Sampled" means not every method invocation is recorded; events below thresholds or disabled may not appear. **Absence of events does not prove absence of activity.**
- Use JDK Mission Control (JMC) to view timelines, flame graphs, allocations, and locks over time; or filter with the `jfr` command without a GUI.

Example recording 1 minute to a file on a running JVM:

```bash
jcmd <pid> JFR.start name=incident settings=profile.jfc duration=60s filename=incident.jfr
jcmd <pid> JFR.check
```

Once finished and the file exists, analyze it:

```bash
jfr summary incident.jfr
jfr print --events jdk.ExecutionSample,jdk.JavaMonitorEnter incident.jfr
```

`jfr summary` reports event types, counts, and sizes; `jfr print` outputs filtered events. Whether `jdk.JavaMonitorEnter` records appear depends on the profile/threshold and whether contention actually occurred during the recording window.

If you need a **continuous ring buffer and want to extract a slice when an incident occurs**, use a different workflow:

```bash
jcmd <pid> JFR.start name=rolling settings=default.jfc maxage=10m maxsize=200m
jcmd <pid> JFR.dump name=rolling filename=incident-window.jfr maxage=5m
jcmd <pid> JFR.stop name=rolling
```

`JFR.dump` writes a snapshot of the recording to a file **without automatically stopping the recording**; `JFR.stop` stops the named recording. `maxage`/`maxsize` limits retain only recent history, preventing unbounded file growth. Files are created relative to the target JVM's path view; use absolute paths when working with services.

JFR helps identify **hot call paths, allocation rates, GC pauses, and prolonged lock contention**. Heap dumps complement this by identifying **retained objects**; JFR allocation events and heap dumps answer two different questions: "where was it allocated?" vs. "why is it still alive?".

## 10. Java 17+ Hands-On Scenario: Request Waiting on a Monitor

This example creates two threads: `lock-holder` holds a monitor for 60 seconds; `lock-waiter` waits to enter the same monitor. The goal is to **see the difference between symptoms, thread states, and JFR events**, not to simulate a full HTTP server.

Create the file **`LockContentionDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class LockContentionDemo {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch acquired = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (MONITOR) {
                acquired.countDown();
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-holder");

        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                // Continues running after holder releases the monitor.
            }
        }, "lock-waiter");

        holder.start();
        acquired.await();
        waiter.start();

        System.out.println("Ready: inspect threads for 60 seconds.");
        holder.join();
        waiter.join();
        System.out.println("Finished.");
    }
}
```

Compile and run with JDK 17+ in the first terminal:

```bash
javac LockContentionDemo.java
java LockContentionDemo
```

**Program stdout** (two lines, roughly one minute apart; excluding external shell/JDK messages):

```text
Ready: inspect threads for 60 seconds.
Finished.
```

During the 60-second wait, open a second terminal and run:

```bash
jcmd -l
jcmd <pid> Thread.print -l > threads-during-wait.txt
```

Find the exact PID with main class `LockContentionDemo`. In a thread dump taken while both threads are alive, expect `lock-holder` in `TIMED_WAITING` due to `Thread.sleep`, and `lock-waiter` in `BLOCKED` waiting to enter the same monitor. Object addresses, native frame names, and ordering vary by JVM, so **do not treat the dump as fixed stdout**. If taken too early or after 60 seconds, `BLOCKED` may not appear yet or may already be gone.

To observe the same scenario with JFR **from JVM startup**, run another session:

```bash
java -XX:StartFlightRecording=filename=locks.jfr,settings=profile.jfc,dumponexit=true LockContentionDemo
jfr summary locks.jfr
jfr print --events jdk.JavaMonitorEnter locks.jfr
```

Wait for the program to exit before reading `locks.jfr`. Whether monitor events are captured depends on configuration, thresholds, and JVM version; if no events appear, check `jfr summary` and the profile instead of concluding there was no lock wait. This demo uses `sleep` **inside** a `synchronized` block to intentionally hold the monitor; in production code, keep critical sections short and avoid I/O/blocking inside locks.

**Explaining the demo's evidence:**

- **Logs/stdout:** confirms the demo started and finished; does not quantify lock wait time on its own.
- **Metrics (if instrumented):** shows task completion time increased; still does not pinpoint the monitor.
- **Thread dump:** reveals the `BLOCKED` and `TIMED_WAITING` relationship at capture time.
- **JFR:** can show monitor contention and event timestamps over time if the event was recorded.
- **Heap dump:** not a priority choice since the issue is not long-lived object retention.
- **Exception stack trace:** absent because no exception was thrown; this does not mean the program was not slowed down.

## 11. Choosing Evidence by Symptom: Three Investigation Scenarios

### A. p99 Latency Rises While CPU and Heap Do Not Increase Significantly

1. **Metrics:** isolate spike window, service/instance, RPS, p99, queue depth, connection count, and timeout rate. Compare with baseline.
2. **Logs and traceId:** locate slow requests, identify which step takes time; distinguish delays inside the JVM from downstream delays.
3. **2–3 thread dumps:** if multiple threads are `BLOCKED` on the same monitor, `WAITING` on a semaphore/connection pool, or on the same I/O stack, form a specific hypothesis.
4. **JFR in the matching window:** inspect monitor enter, thread park, socket/file I/O, and correlate with the spike.
5. **Conditional conclusion:** only state "lock contention causes latency" when timestamps, waiting threads, and lock holder align. If traces point to a slow downstream service, expand the investigation downstream.

### B. Post-GC Heap Used Rises Over Many Hours

1. **Metrics:** chart pre/post-GC heap used, old generation, GC frequency/pauses, load, and cache sizes. Check for configuration changes or batch jobs.
2. **Logs/JFR:** identify growth phases, allocation activity, and allocation sites; distinguish **high allocation rate** from **high retention**.
3. **Controlled heap dump:** examine dominator tree and paths to GC roots for large/abnormally growing objects; inspect maps/caches/static fields/listeners/sessions.
4. **Confirm:** compare against expected behavior and data lifetimes; after fixing, verify whether the post-GC heap floor stabilizes. Do not conclude a leak solely from a class having many instances.

### C. CPU Spikes Sharply Without Many Exceptions

1. **Metrics:** confirm whether CPU belongs to the JVM or the whole host, and whether GC CPU rose; correlate with request count/load.
2. **JFR CPU samples:** inspect methods and stacks with high sample share during the exact spike window; account for sample bias.
3. **Thread dump:** use as a supplement to spot threads repeatedly in the same code region, remembering `RUNNABLE` does not by itself prove CPU consumption.
4. **Logs:** look for retry loops, unusual batch processing, or behavior shifts; verify via load testing/profiling and post-change results.

## 12. Common Mistakes and How to Avoid Them

| Premature Conclusion | Why It Is Wrong | Appropriate Verification |
| --- | --- | --- |
| "There is an `ERROR` in the log, so that line slowed down the system." | The error may be a **consequence** of a timeout or bottleneck elsewhere. | Compare timestamps, traces, metrics, and JFR/thread dumps. |
| "Average latency is normal, so nothing is slow." | Tail latency can rise while the average stays flat. | Check p95/p99, timeouts, and per-route distributions. |
| "A `RUNNABLE` thread means it is burning CPU." | Java state does not fully reflect OS CPU scheduling or native I/O. | Process/thread CPU and JFR execution samples. |
| "Many `WAITING` threads mean a deadlock." | Idle worker pools normally sit in `WAITING`. | Read frames, lock ownership, repeated dumps, and work progress. |
| "A large heap proves a memory leak." | Caches/load and GC cycles can legitimately keep heap large. | Post-GC trends, retention, and GC roots. |
| "A heap dump shows where objects were created." | It focuses on **live objects and current references**. | JFR allocation stacks + heap retained graph. |
| "No JFR events means it did not happen." | Events may be disabled, filtered by threshold, or outside the recording window. | Check settings, `jfr summary`, and timestamps. |
| "Collect every dump immediately on incident." | Heap dumps can cause pauses and expose sensitive data. | Start with metrics/logs; choose the lowest-impact evidence sufficient to answer the question. |

## 13. Checklist for a Real Incident

- [ ] Clearly state measured symptom, impact scope, timestamps, baseline, and current hypothesis under test.
- [ ] Confirm exact service, instance, PID, JDK, timezone, and deployed version.
- [ ] Read metrics first to determine scale, trend, and anomaly window.
- [ ] Use logs/traces to link related requests or jobs; avoid logging sensitive data.
- [ ] Pick stack traces for call-path errors, thread dumps for waits/contention, heap dumps for object retention, and JFR for CPU/GC/lock/allocation timelines.
- [ ] Record file names, time ranges, PIDs, access permissions, impact, and artifact sizes.
- [ ] Cross-check **at least two independent signals** before declaring a cause.
- [ ] After a change, verify improvement using the same metrics and comparable load conditions; note remaining uncertainties.

**Official reference documentation for JDK 17:**

- [Oracle — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print`, `GC.heap_dump`, `JFR.start`, `JFR.dump`.
- [Oracle — `jfr` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print`, `metadata`.
- [Oracle — Java SE 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): diagnostic scenarios and evidence collection.

**Key takeaway:** metrics tell you *where and when there is a problem*; logs/traces tell you *which request or operation was involved*; stack traces show *the call path*; thread dumps show *what threads are doing/waiting on*; heap dumps show *which objects remain retained*; JFR shows *which JVM events occurred across the investigation window*. They are most effective when properly time-aligned and cross-verified.
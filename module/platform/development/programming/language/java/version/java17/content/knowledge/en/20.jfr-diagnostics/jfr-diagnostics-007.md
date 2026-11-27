# Analyzing CPU, Allocation, GC, I/O, and Locks in JFR — Java 17

Java Flight Recorder (JFR) is a JVM runtime event recording tool for investigating performance and application behavior. In Java 17, JFR is built into the JDK and can record CPU execution samples, object allocations, Garbage Collection cycles, file/socket operations, and lock-wait events. Data is saved to a recording file for analysis with Java Mission Control (JMC) or the `jfr` command-line tool.

JFR is valuable when an application runs slowly, CPU spikes, GC runs frequently, I/O stalls, or multiple threads wait on one another. Instead of looking at a single aggregate metric, recordings tie events to timestamps, threads, and stack traces to locate the relevant areas of code.

This lesson focuses on recording in Java 17 and reading five diagnostic areas:

- **CPU:** which threads are executing and which stacks appear frequently.
- **Allocation:** which code allocates many objects and puts pressure on the heap.
- **GC:** when collections run, how long pauses last, and how the heap changes.
- **I/O:** which file or socket operations take a long time.
- **Locks:** which threads block entering monitors or park waiting for synchronization.

JFR is a low-overhead observability tool in many configurations, though it is not a profiler where every event can be enabled at maximum detail with zero impact. Choose an appropriate configuration, record over a period with representative load, and interpret results in application context.

## 1. What Data Does JFR Provide?

JFR records **events** occurring inside the JVM. Each event can include a timestamp, duration, thread, stack trace, and event-specific fields. Not every event contains all of these fields.

Key event groups:

| Group | Representative Events in JDK 17 | Used to Investigate |
| --- | --- | --- |
| CPU and execution | `jdk.ExecutionSample`, `jdk.NativeMethodSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` | Execution stacks, process/machine CPU load, and per-thread CPU. |
| Object allocation | `jdk.ObjectAllocationSample`, `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB` | Allocation locations and object creation pressure. |
| Garbage Collection | `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.GCHeapSummary` | GC timing, pauses, and heap state before/after collection. |
| File I/O | `jdk.FileRead`, `jdk.FileWrite` | File read/write duration, byte counts, and paths. |
| Socket I/O | `jdk.SocketRead`, `jdk.SocketWrite` | Socket read/write duration, host/port, and data volume. |
| Monitors and lock waits | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` | Monitor contention, wait/notify, and thread parking. |

Event names and detail levels depend on the JDK, recording configuration, and whether the event is enabled. If an event does not appear in a file, you cannot conclude the problem never occurred; the event might not be enabled or a duration threshold may be filtering out short operations.

JFR does not just write plain-text logs. Recordings store structured data that can be filtered by event, time, thread, and stack trace. This helps analyze causal chains such as: a method allocates many objects, causing frequent young GCs, while request latency climbs.

## 2. Starting a Recording on Java 17

Before analyzing, create a recording file while the application is running the workload under investigation.

### 2.1. Recording at JVM Startup

You can instruct the JVM to start a recording automatically with an option:

```bash
java -XX:StartFlightRecording:filename=app.jfr,settings=profile,duration=120s -jar app.jar
```

In this example:

- `filename=app.jfr` is the output recording file.
- `settings=profile` selects a configuration containing more profiling data than `default`.
- `duration=120s` caps recording time at roughly two minutes.

You can select `settings=default` for continuous recording or when lower overhead is required. The `profile` configuration typically captures more useful diagnostic data, but can produce more events and overhead. Test in a representative environment before enabling it long-term in production.

### 2.2. Starting a Recording for a Running Process with jcmd

JDK 17 includes the `jcmd` tool. Find the Java process PID, then start a recording:

```bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=2m filename=diagnostic.jfr
```

Replace `<pid>` with the actual process ID. The command instructs the JVM to start a recording named `diagnostic`, using `profile` settings, and write the file once the duration completes.

Check running recordings:

```bash
jcmd <pid> JFR.check
```

If you need a snapshot before the recording auto-stops:

```bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic-snapshot.jfr
```

Stop a recording by name:

```bash
jcmd <pid> JFR.stop name=diagnostic
```

`JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop` must run with appropriate permissions and user identity to attach to the target JVM. In container environments, run `jcmd` inside the right container or an environment able to attach to that process.

### 2.3. Continuous Recordings

For long-running services, use a continuous recording with `default` settings and age/size limits:

```bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=1h maxsize=256m
```

When an investigation is needed, dump a snapshot:

```bash
jcmd <pid> JFR.dump name=continuous filename=incident.jfr
```

When the recording is no longer needed:

```bash
jcmd <pid> JFR.stop name=continuous
```

`maxage` and `maxsize` limits keep retained data bounded. Continuous recordings are valuable when bugs occur infrequently; still, account for disk capacity, retention policy, and file access permissions.

## 3. Reading Recordings with the JFR Tool

JDK 17 provides the `jfr` command-line tool to inspect summaries and print events from recording files.

View overall statistics:

```bash
jfr summary diagnostic.jfr
```

This shows recording duration, JDK version, configuration, and event counts by type. Run `summary` first to verify whether the file captured the event groups you need to investigate.

Print specific events:

```bash
jfr print --events jdk.ExecutionSample diagnostic.jfr
jfr print --events jdk.ObjectAllocationSample diagnostic.jfr
jfr print --events jdk.GarbageCollection diagnostic.jfr
jfr print --events jdk.FileRead diagnostic.jfr
jfr print --events jdk.JavaMonitorEnter diagnostic.jfr
```

Output can be lengthy. For large recordings, filter by event or time window, or open the file in JMC for visual tables and charts.

### Using Java Mission Control

Java Mission Control (JMC) can open `.jfr` files and provide analysis pages such as:

- **Overview:** recording summary, JVM, heap, and key metrics.
- **Threads:** thread states and activity over time.
- **Method Profiling:** stack samples and frequently appearing methods.
- **Memory:** allocations and heap/GC details.
- **Garbage Collections:** GC cycles, pauses, and heap summaries.
- **I/O:** file/socket events with durations.
- **Locks:** monitor contention and thread parking.

JMC is an analysis tool; JFR is the in-JVM event recording engine. You can record with JFR on a server and transfer the recording file to a workstation with JMC for analysis, following your organization's data security policies.

## 4. Analyzing CPU with ExecutionSample

High CPU can stem from compute-heavy loops, processing large datasets, serializing/parsing many objects, native code, or many threads contending for CPU. JFR helps locate execution stacks that appear frequently in the recording.

### 4.1. The ExecutionSample Event

`jdk.ExecutionSample` samples the stacks of executing threads. Rather than tracing every method call, JFR samples periodically to observe running code.

Example viewing events:

```bash
jfr print --events jdk.ExecutionSample diagnostic.jfr
```

Each sample typically shows the thread and stack trace at the sampling instant. When many samples share the same method or stack branch, that signals an area of code to inspect.

**Sampling is a statistical estimate.** A method appearing in many samples may consume significant execution time, but sample count is not an exact measure of invocation count or CPU time per call.

### 4.2. Reading Stack Traces and Flame Graphs

Suppose a recording has many samples with the stack:

```text
com.example.ReportService.generate
  com.example.ReportService.aggregate
    com.example.ReportService.normalize
      java.text...
```

This suggests the report generation branch and `normalize` method merit inspection. If the same stack appears across many samples, check for redundant processing, data conversions, or unnecessary CPU-intensive computations.

In a flame graph:

- The horizontal axis represents the proportion of samples across stacks.
- The vertical axis represents the call stack depth.
- A wide block indicates that branch appeared in many samples.
- Blocks deep in the stack may be specific methods consuming high CPU or called very frequently.

Do not look solely at methods with prominent names. Distinguish **self time** (time spent inside the method itself) from **inclusive time** (the method plus its callees). A top-level method may appear often simply because it invokes an expensive child method.

### 4.3. Distinguishing CPU-Bound Threads from Waiting Threads

Execution samples primarily observe executing threads. If a thread is blocked on a lock, waiting on I/O, or parked, the problem may not surface as a hot CPU stack.

For complete analysis:

- Use `jdk.ExecutionSample` to locate executing stacks.
- Check `jdk.CPULoad` to observe JVM and machine CPU load.
- Check `jdk.ThreadCPULoad` when per-thread CPU data is needed and the event is enabled.
- Inspect I/O and lock groups to spot threads waiting rather than executing.

An application with low CPU yet slow requests may be stalled on I/O or locks. Do not try to optimize CPU just because latency is high.

### 4.4. Systematic CPU Investigation

1. Record JFR while CPU is high and real workload is running.
2. Open the Method Profiling page or filter `jdk.ExecutionSample`.
3. Group samples by thread and stack.
4. Identify stack branches with high sample shares.
5. Inspect corresponding source code for algorithms, loops, string processing, collections, or serialization.
6. Fix one specific cause, then capture a new recording to compare.

If high CPU is spread across many threads executing in parallel, analyze each thread group. A method taking a small fraction per thread but running across dozens of threads can still account for a major share of total process CPU.

## 5. Analyzing Object Allocations

Continuously allocating many objects drives up the allocation rate, filling the young generation rapidly and triggering frequent GC. Some allocations also strain CPU and caches even when objects are very short-lived.

JFR shows **where objects are allocated** and which object types create pressure.

### 5.1. ObjectAllocationSample

`jdk.ObjectAllocationSample` is an allocation-sampling event. It can include the object's class, allocation size info, and stack trace.

View events:

```bash
jfr print --events jdk.ObjectAllocationSample diagnostic.jfr
```

This is a practical way to locate allocation hot spots without recording every single allocation. Sampling means the recording does not hold one event per object; read the weight/size fields and aggregate by stack in JMC rather than counting raw event rows as total objects created.

### 5.2. TLAB and Allocations Outside TLAB

HotSpot normally allocates small objects using a **Thread-Local Allocation Buffer (TLAB)**. Each thread has its own allocation buffer, keeping ordinary allocations fast with minimal synchronization.

JFR can emit related events:

- `jdk.ObjectAllocationInNewTLAB`: allocations tied to allocating a new TLAB.
- `jdk.ObjectAllocationOutsideTLAB`: allocations occurring outside a TLAB.

These events help investigate specific allocation scenarios, though you should not assume they represent every single object allocation. For general allocation analysis, `jdk.ObjectAllocationSample` is usually the right starting point.

### 5.3. Finding Allocation Hot Spots

Suppose sample stacks show heavy allocation coming from:

```text
com.example.ApiMapper.toResponse
  java.util.ArrayList...
  java.lang.String...
```

Questions to ask:

- Are intermediate collections created on every request?
- Is the same data converted repeatedly?
- Are temporary strings built inside loops?
- Are objects parsed/serialized repeatedly?
- Can a more suitable data structure be used or unnecessary object creation avoided?

Not every allocation is bad. Small, short-lived, cheaply allocated objects are normal in Java. The goal is not to eliminate all allocations, but to cut unnecessary ones when they generate significant pressure.

### 5.4. Allocation vs. Retained Heap

JFR allocation events show where objects are **created**. They do not themselves answer which objects are retained long-term or why those objects are not collected.

Distinguish:

- **Allocation pressure:** many objects created per unit time.
- **Retained heap:** memory of objects still kept alive by live references.
- **Memory leak:** objects no longer needed by business logic yet still referenced, causing the live set to grow.

If allocation is high while objects are short-lived, young GC may run frequently while post-GC heap remains stable. If heap after GC cycles keeps climbing, inspect a heap dump, dominator tree, and reference paths. Changing GC algorithms will not fix logic that unintentionally retains objects.

## 6. Analyzing Garbage Collection

GC events identify collection frequency, pause durations, trigger causes, and heap fluctuations.

### 6.1. Key Events

| Event | Key Information |
| --- | --- |
| `jdk.GarbageCollection` | A GC cycle, duration, collector name, and related cause. |
| `jdk.GCPhasePause` | Pause phases within GC execution. |
| `jdk.GCHeapSummary` | Heap summary before or after certain GC phases. |
| `jdk.GCPhaseConcurrent` | Concurrent GC phases if emitted by the collector. |
| `jdk.GCReferenceStatistics` | Statistics on processing reference types during GC. |

Exact event names and counts depend on the collector and JFR configuration. Different collectors have different phase sequences; do not compare phase names across collectors as if they had identical semantics.

View GC events:

```bash
jfr print --events jdk.GarbageCollection diagnostic.jfr
jfr print --events jdk.GCPhasePause diagnostic.jfr
jfr print --events jdk.GCHeapSummary diagnostic.jfr
```

### 6.2. Reading Duration and Pauses

For each GC event, inspect:

- Start time and duration.
- Collector name or collection type.
- Trigger cause if provided by the event.
- Pause duration and pause phases.
- Heap before and after GC.

A GC event with a long total duration does not mean the entire time was stop-the-world. Several collectors include concurrent phases. When investigating request latency, inspect specific pause events rather than taking the whole cycle duration.

### 6.3. Distinguishing High Allocation Rate from Memory Leaks

Example A: high allocation rate

- Young GC occurs frequently.
- Heap drops substantially after young collections.
- Post-GC live set remains relatively stable.
- Allocation samples cluster in methods creating temporary objects.

Remediation: inspect allocation hot spots, intermediate objects, data conversions, and batch sizes.

Example B: continuously growing live set

- Post-GC heap climbs steadily across cycles.
- Old generation or long-lived regions grow.
- GC reclaims less and less relative to occupied heap.
- The application may hold unreleased caches, collections, or listeners.

Remediation: inspect heap dumps, dominator trees, reference chains, and object lifecycles. JFR pinpoints timing and trends; heap dumps are usually needed to find which objects hold references.

### 6.4. Correlating GC with Latency

If request latency rises alongside GC pauses, check:

1. Do pauses align with latency spikes?
2. Do pauses occur frequently or as a single anomaly?
3. Does the heap have sufficient headroom before collection?
4. Did the allocation rate spike before GC ran?
5. Is GC CPU competing with application threads?
6. Did slow requests hit the same JVM or instance experiencing the pauses?

A pause occurring near a latency rise does not alone prove GC is the sole cause. Cross-reference timestamps, request metrics, and I/O/lock events.

## 7. Analyzing File I/O

File operations can stall due to large files, storage latency, filesystems, antivirus/scanners, network filesystems, or congested thread pools.

JFR can record:

- `jdk.FileRead`: reading data from files.
- `jdk.FileWrite`: writing data to files.

View events:

```bash
jfr print --events jdk.FileRead diagnostic.jfr
jfr print --events jdk.FileWrite diagnostic.jfr
```

Depending on the event and configuration, fields can include path, byte count, duration, thread, and stack trace.

### 7.1. Finding Slow File Operations

When inspecting events, focus on:

- Large durations.
- Repeated file paths.
- Bytes read/written.
- Threads performing I/O.
- Stack traces calling file APIs.

Example stack:

```text
com.example.ExportService.export
  java.nio.file.Files.write
  ...
```

If many slow file write events share the same path and stack, examine export logic, data sizes, batching, and storage location.

### 7.2. Separating I/O Time from Processing Time

A request can take a long time because of:

- Slow file reads.
- Parsing content after reading.
- Waiting on a lock before reading.
- Writing results to a file.
- Waiting on another service.

The JFR `FileRead` event reports the recorded file operation; the stack trace points to the calling code. To understand the full request, align event timestamps with application spans/logs/metrics if available.

### 7.3. Event Thresholds

I/O events are typically configured with a duration threshold to avoid recording vast numbers of brief operations. Thus, a recording may contain only operations exceeding the threshold.

If you do not see a file read you know occurred, check event configuration, thresholds, and stack trace settings. Never conclude file I/O has no issues simply because the recording lacks events.

## 8. Analyzing Socket I/O

A slow HTTP request can stem from a remote server, network, DNS, proxy, connection setup, or application socket reads/writes. JFR provides:

- `jdk.SocketRead`: reading from a socket.
- `jdk.SocketWrite`: writing to a socket.

View events:

```bash
jfr print --events jdk.SocketRead diagnostic.jfr
jfr print --events jdk.SocketWrite diagnostic.jfr
```

Details may include host, address, port, bytes, timeout, end-of-stream, duration, thread, and stack trace depending on the event.

### 8.1. Reading SocketRead

If `SocketRead` has a long duration, the thread may have waited for data from the peer or network stack. Inspect:

- Target host and port.
- Bytes received.
- Thread performing the read.
- Stack trace invoking socket/client APIs.
- Whether the request has a timeout.
- Whether events align with slowness on the remote server.

A long read does not itself prove the network is broken. The remote server may not have sent data yet, the app may be awaiting a response, or the protocol may require further reads.

### 8.2. Reading SocketWrite

If `SocketWrite` takes a long time, the thread may be waiting for write readiness, socket buffers, or a slow-reading peer. Inspect payload size, send rate, backpressure, and target service health.

### 8.3. Combining with HTTP Client Metrics

For applications using HTTP Client or networking libraries, correlate JFR socket events with:

- Total request duration.
- Connection pool wait time.
- DNS lookup and TLS handshake if relevant metrics/events exist.
- Server response time.
- Bytes sent and received.
- Retries, timeouts, and error rates.

JFR socket events do not replace distributed tracing. To follow one request across multiple services, use trace/span IDs and align with JFR timestamps on each JVM.

## 9. Analyzing Locks and Thread Contention

Multiple threads may simultaneously need access to a protected resource. If one thread holds a lock too long, other threads wait, reducing throughput even while CPU stays low.

JFR has several important events:

| Event | What It Observes |
| --- | --- |
| `jdk.JavaMonitorEnter` | Thread blocked trying to enter a `synchronized` monitor held by another thread. |
| `jdk.JavaMonitorWait` | Thread called `Object.wait()` and is awaiting notification or timeout. |
| `jdk.ThreadPark` | Thread parked via mechanisms like `LockSupport.park()`; common in synchronizers and concurrent utilities. |

View events:

```bash
jfr print --events jdk.JavaMonitorEnter diagnostic.jfr
jfr print --events jdk.JavaMonitorWait diagnostic.jfr
jfr print --events jdk.ThreadPark diagnostic.jfr
```

### 9.1. JavaMonitorEnter: synchronized Contention

When a thread tries to enter a `synchronized` block while another thread holds the monitor, it must wait. `jdk.JavaMonitorEnter` records the contention event along with duration and monitor/thread details.

Example code prone to contention:

```java
public class SharedCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
```

If many threads call `increment()` continuously on the same instance, they must serialize through the monitor. If critical sections are long or locks are too coarse, contention escalates.

When reading events, examine:

- Which threads are blocked.
- Monitor wait duration.
- Stack trace where the thread attempted to enter `synchronized`.
- Monitor class and details if provided by the event.
- Which thread may be holding the monitor long-term; correlate thread activity and stacks around the same time.

The event shows the waiting thread; to locate the code holding the lock long-term, inspect the activity of the monitor-owning thread around that timestamp.

### 9.2. JavaMonitorWait: Object.wait Is Not Always Lock Contention

`Object.wait()` puts a thread into waiting state on a monitor. The thread must own the monitor when calling `wait()`; while waiting, it releases the monitor and waits for `notify`/`notifyAll` or timeout.

`jdk.JavaMonitorWait` helps observe this wait duration. However, long waits are not automatically contention bugs: they may be normal producer-consumer behavior or an unfulfilled business condition.

Check:

- In which method the thread is waiting.
- Whether `wait` has a timeout.
- Whether another thread calls `notify`/`notifyAll`.
- Whether the loop condition around `wait` is correct.
- Whether wait duration aligns with SLAs.

### 9.3. ThreadPark: ReentrantLock and Synchronizers

`jdk.ThreadPark` records thread parking via `LockSupport`. Constructs such as `ReentrantLock`, `Semaphore`, `BlockingQueue`, and certain executors use this mechanism.

Example:

```java
import java.util.concurrent.locks.ReentrantLock;

public class LockExample {
    private final ReentrantLock lock = new ReentrantLock();

    public void update() {
        lock.lock();
        try {
            // Critical section
        } finally {
            lock.unlock();
        }
    }
}
```

If many threads contend on `lock`, waiting threads may park. Still, `ThreadPark` does not mean every event is lock contention. Threads also park intentionally while waiting on queues, conditions, schedulers, or other signals.

Inspect the stack trace, blocker/parked class if present, thread state, and activity of other threads to determine the cause.

## 10. Distinguishing High CPU, Slow I/O, and Lock Contention

These scenarios can all slow down requests yet exhibit distinct patterns:

| Symptom | JFR Data to Inspect | Common Signs |
| --- | --- | --- |
| CPU-bound | `ExecutionSample`, `CPULoad`, `ThreadCPULoad` | Many samples clustered in specific methods; high process CPU. |
| I/O-bound | `FileRead`, `FileWrite`, `SocketRead`, `SocketWrite` | Long I/O event durations; threads waiting on reads or writes. |
| Lock contention | `JavaMonitorEnter`, `JavaMonitorWait`, `ThreadPark` | Many threads waiting on the same monitor/synchronizer; CPU may be low. |
| Allocation pressure | `ObjectAllocationSample` and GC events | Allocation samples clustered on a specific stack; frequent young GC. |
| GC pauses | `GarbageCollection`, `GCPhasePause`, `GCHeapSummary` | Pauses align with latency spikes; heap shifts after collections. |

These are investigative signals, not automated diagnoses. A single request can suffer from multiple factors at once: allocating too many objects, triggering frequent GC, and then waiting on I/O or locks.

## 11. Analyzing Along a Timeline Instead of Isolated Events

JFR is most effective when events are placed on a shared timeline.

Example of an API experiencing rising latency:

```text
Time  ──────────────────────────────────────────────────────────>

Request starts
    |
    +-- Allocations spike in Mapper
    |
    +-- Young GC pause
    |
    +-- Thread waits on SocketRead
    |
    +-- Response completes
```

When investigating, ask:

1. Which event started before latency climbed?
2. Was the request-handling thread paused, blocked, or parked?
3. Did a GC pause coincide with that timestamp?
4. Does an allocation stack or CPU hot spot repeat consistently?
5. Did I/O take longer than normal?
6. Are multiple requests/threads waiting on the same monitor?

Use timestamps, thread names/IDs, and stack traces to correlate events. If the application has distributed tracing, align the JFR timeline with traces and correlation-ID logs.

Do not simply pick the event with the largest duration and declare it the root cause. Verify whether that event actually sits on the critical path of the slow requests.

## 12. Choosing Recording Settings and Thresholds

JFR provides built-in recording configurations such as `default` and `profile`:

- `default` targets continuous recording with lower overhead.
- `profile` gathers more detailed data for performance investigations over a bounded interval.

You can use `jfr configure` to create custom configurations or JMC to tune event settings. In a JFC file, each event can configure `enabled`, `stackTrace`, and `threshold` alongside appropriate settings.

Illustrative snippet enabling socket reads and recording only events with sufficient duration:

```xml
<event name="jdk.SocketRead">
    <setting name="enabled">true</setting>
    <setting name="stackTrace">true</setting>
    <setting name="threshold">10 ms</setting>
</event>
```

This snippet illustrates tuning one event; integrate it into a complete JFC file suitable for the recording. A 10 ms threshold is just an example, not a universal standard.

If the threshold is too high, moderately slow events are missed. If the threshold is too low and the event fires frequently, the recording grows large and incurs higher overhead.

### Choosing Settings by Investigation Question

| Question | Events/Settings to Focus On |
| --- | --- |
| Which methods consume CPU? | Execution sampling and stack traces. |
| Which code allocates many objects? | Allocation sampling and stack traces. |
| Which GC pauses slow the app? | Garbage collection, pause phases, and heap summaries. |
| Which files/sockets have slow operations? | FileRead/FileWrite/SocketRead/SocketWrite, thresholds, and stack traces. |
| Which threads wait on synchronized monitors? | JavaMonitorEnter and stack traces. |
| Which threads are parking? | ThreadPark and relevant thread/stack info. |

You do not need every event at maximum detail in every recording. Start with an appropriate baseline configuration, then capture focused recordings if deeper investigation is needed.

## 13. Workflow for Investigating a Performance Incident

A repeatable workflow:

### Step 1: Identify Symptoms

Gather application metrics before enabling recordings:

- Process or container CPU.
- Request latency p50/p95/p99.
- Throughput and error rate.
- Heap usage and GC count.
- I/O latency and queue depth.
- Thread count and thread states if available.

### Step 2: Record JFR at the Right Time

Start the recording while the workload exhibits the symptom. Choose `profile` for a short investigation window or `default` for continuous recording.

### Step 3: Verify the Recording Has Enough Events

Run `jfr summary` to inspect event counts and duration. If required event groups are missing, check settings, thresholds, and recording timing.

### Step 4: Select Event Groups by Symptom

- High CPU: inspect `ExecutionSample` and CPU load.
- Abnormal heap/GC: inspect allocation samples, `GarbageCollection`, and heap summary.
- Slow I/O: inspect `FileRead`/`Write` and `SocketRead`/`Write`.
- Waiting threads: inspect `JavaMonitorEnter`, `JavaMonitorWait`, and `ThreadPark`.

### Step 5: Identify Involved Stacks and Threads

Group events by stack, thread, class, host/path, and duration. Look for recurring hot spots rather than a single isolated event.

### Step 6: Cross-Reference Code and Metrics

Open the source code for the implicated stacks. Compare event timestamps with request metrics, application logs, and distributed traces.

### Step 7: Make Targeted Changes and Re-Record

Fix an evidence-backed cause, re-run an equivalent workload, and capture a fresh recording. Compare using the exact same metrics and conditions.

## 14. Limitations to Remember When Reading JFR

- **Sampling is not full tracing:** `ExecutionSample` and `ObjectAllocationSample` are sampled measurements, not logs of every method call or every allocation.
- **Events can be filtered by thresholds:** missing events do not prove an activity never occurred.
- **Recordings may be non-representative:** recording while idle or only during startup does not reflect production workload.
- **Stack traces have cost:** enabling stack traces on high-frequency events increases recording size and overhead.
- **CPU samples do not directly measure request latency:** correlate with metrics and tracing.
- **Allocations are not retained heap:** finding live objects and retention paths may require a heap dump.
- **Socket events do not explain the full network path:** DNS, TLS, connection pools, and server processing may need additional metrics or traces.
- **ThreadPark is not always a bug:** it can be normal waiting behavior.
- **GC events do not themselves prove a memory leak:** inspect live set trends, heap dumps, and object lifecycles.
- **JFR does not replace application observability:** metrics, logs, and distributed tracing remain essential.

## 15. Protecting Recordings and Sensitive Data

JFR files can contain internal details such as class names, methods, file paths, hosts/ports, thread names, stack traces, and certain event values. Do not assume a recording is harmless simply because it is not a business log.

When sharing recordings:

- Store files in locations with restricted access permissions.
- Do not upload recordings to public services without authorization.
- Inspect for sensitive details before sending to external parties.
- Cap recording duration and size.
- Comply with your organization's data retention policies.
- Use filtered or scrubbed recordings when sharing is necessary.

The `jfr scrub` tool can help strip certain information from recordings using appropriate filters; inspect the output before sharing and never treat scrubbing as an absolute anonymization guarantee.

## 16. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| JFR records every method call. | `ExecutionSample` samples stacks periodically; it is not a complete call trace. |
| No `ObjectAllocationSample` means zero allocations. | The event may be disabled or no sample fell in the recording window. |
| Allocation samples reveal leaked objects. | They show where objects are created; retained heap and reference paths require separate analysis. |
| GC event duration equals pause time. | A GC cycle may include concurrent phases; inspect specific pause events. |
| Long `SocketRead` proves a network failure. | The thread may be waiting for the peer to send data; check the server, timeouts, and traces. |
| `ThreadPark` is always lock contention. | Parking is normal waiting behavior in many synchronizers. |
| No `JavaMonitorEnter` means no lock contention. | The code may use park-based synchronizers, events may be threshold-filtered, or settings disabled. |
| Profile recordings have zero overhead. | JFR generally has low overhead, but not zero; impact depends on events and workload. |
| A short recording while idle finds production bottlenecks. | Record under representative load at the time symptoms occur. |
| JFR replaces metrics, logs, and tracing. | JFR adds detailed JVM data; combine it with application and system observability. |

## 17. Practice Exercises

### Exercise 1 — Recording and Reading Summary

Run a Java 17 application under load for roughly two minutes. Use `jcmd` to start a recording with `settings=profile`, then run `jfr summary`. Note which events appear most frequently.

### Exercise 2 — Finding CPU Hot Spots

Write a method with a compute loop running long enough to appear in a recording. Inspect `jdk.ExecutionSample` and stack traces. Identify which method has the most samples and explain why sample count is not an exact invocation count.

### Exercise 3 — Observing Allocations

Create a workload allocating many temporary objects in a loop. Enable allocation sampling, inspect `jdk.ObjectAllocationSample`, and group by stack/class. Try reducing intermediate objects and capture a new recording to compare.

### Exercise 4 — Linking GC to Allocations

Create a high-allocation-rate workload. Inspect allocation samples, `jdk.GarbageCollection`, and `jdk.GCPhasePause`. Compare allocation hot spots with young GC frequency and pauses.

### Exercise 5 — Observing File I/O

Write a program reading and writing a sufficiently large file. Capture JFR and inspect `jdk.FileRead` and `jdk.FileWrite`. Compare durations, byte counts, and stack traces.

### Exercise 6 — Observing Socket I/O

Call a test endpoint with controlled latency. Inspect `jdk.SocketRead` and `jdk.SocketWrite`. Identify thread, host/port, and duration of socket operations.

### Exercise 7 — Observing Monitor Contention

Have multiple threads call a `synchronized` method holding the monitor long enough to contend. Record JFR and inspect `jdk.JavaMonitorEnter`. Locate waiting threads and stack traces where they attempt monitor entry.

### Exercise 8 — Distinguishing wait and park

Create one example using `Object.wait()` and another using `ReentrantLock`. Observe `jdk.JavaMonitorWait` and `jdk.ThreadPark`. Explain why these two events represent different waiting mechanisms.

### Exercise 9 — Analyzing a Combined Incident

Create a workload that allocates objects, reads files, and synchronizes via a lock. Capture JFR under high load. Use the timeline to determine whether CPU, allocation, GC, I/O, or locks contribute most to latency.

## 18. Quick Reference

| Goal | Event / Tool |
| --- | --- |
| Start recording on running JVM | `jcmd <pid> JFR.start ...` |
| Check recordings | `jcmd <pid> JFR.check` |
| Dump recording | `jcmd <pid> JFR.dump ...` |
| Stop recording | `jcmd <pid> JFR.stop ...` |
| View file summary | `jfr summary recording.jfr` |
| View CPU stack samples | `jdk.ExecutionSample` |
| View allocation samples | `jdk.ObjectAllocationSample` |
| View GC cycles | `jdk.GarbageCollection` |
| View GC pause phases | `jdk.GCPhasePause` |
| View heap summary | `jdk.GCHeapSummary` |
| View file I/O | `jdk.FileRead`, `jdk.FileWrite` |
| View socket I/O | `jdk.SocketRead`, `jdk.SocketWrite` |
| View synchronized contention | `jdk.JavaMonitorEnter` |
| View Object.wait | `jdk.JavaMonitorWait` |
| View thread park | `jdk.ThreadPark` |
| Visual analysis | Java Mission Control (JMC) |

**Core Principle:** Use JFR to connect events, threads, timestamps, and stack traces. `ExecutionSample` locates hot CPU stacks; allocation samples show where objects are created; GC events reveal pauses and heap dynamics; File/Socket events assist I/O investigation; `JavaMonitorEnter`, `JavaMonitorWait`, and `ThreadPark` expose waiting mechanisms. Record under representative workload, verify settings/thresholds, and combine JFR with metrics, logs, and tracing before concluding a root cause.

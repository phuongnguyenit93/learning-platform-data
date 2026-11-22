# Allocation Analysis with Java Flight Recorder (JFR)

Allocation is the process by which the JVM allocates memory for new objects and arrays. When an application creates many temporary objects, the allocation rate increases, the garbage collector must reclaim them more frequently, and CPU usage can shift heavily toward GC. Allocation analysis with Java Flight Recorder (JFR) helps identify the classes, threads, and stack traces generating the most data, pinpointing where allocations should be reduced.

This guide uses JDK 17 or later and JDK Mission Control (JMC) to inspect recordings. The focus is on understanding allocation samples, TLABs, JFR events, how to capture recordings, how to locate allocation hotspots, and how to distinguish allocation pressure from a memory leak.

## 1. What is Allocation?

Whenever code creates an object or array with `new`, calls an API that constructs objects, concatenates strings, or uses libraries that produce intermediate data, the JVM may need to allocate memory on the Java heap.

Example:

~~~java
Customer customer = new Customer();
byte[] buffer = new byte[8192];
String message = "Order-" + orderId;
~~~

The lines above create objects or arrays. A real-world request can allocate hundreds or thousands of objects across application code, frameworks, and libraries.

Allocation analysis answers these questions:

- Which classes are created most often or account for the most allocated bytes?
- Which methods or stack traces are the primary sources of allocation?
- Which threads allocate the most objects?
- Does allocation occur primarily inside TLABs or outside TLABs?
- At what points in the recording does the allocation rate spike?
- Are those objects short-lived or retained long-term?

An allocation profile is especially useful when an application experiences frequent GC cycles, rising CPU during request handling, reduced throughput, or increased latency caused by allocation pressure.

## 2. Distinguishing Allocation from Retained Memory

This is the most important distinction when reading allocation data:

- **Allocated bytes:** the total amount of memory allocated over a period of time.
- **Live/retained objects:** objects that are still referenced and cannot yet be reclaimed at the time of inspection.
- **Heap used:** the amount of heap currently in use at a given point in time.
- **Allocation rate:** the number of bytes allocated per unit of time, typically measured in MB/s.

An object can be allocated and become unreachable immediately afterward. It still increases allocation pressure, but GC can reclaim it very quickly. Conversely, an object allocated once and held long-term by a cache or static collection can grow the heap without producing a high allocation rate.

Example:

~~~java
for (int i = 0; i < 1_000_000; i++) {
    byte[] temporary = new byte[4096];
    process(temporary);
}
~~~

This loop may allocate nearly a million temporary arrays. If those arrays are not retained, they create allocation pressure but do not necessarily cause a memory leak.

Conversely:

~~~java
static final List<byte[]> CACHE = new ArrayList<>();

void cache(byte[] data) {
    CACHE.add(data);
}
~~~

If the cache grows continuously without evicting elements, objects can survive across multiple GC cycles. This is a retention/leak issue that requires reference-path analysis and cannot be diagnosed from allocation samples alone.

Therefore, use allocation profiling to find where objects are created; use heap dumps, old-object sampling, and GC root analysis to find why objects are retained.

## 3. What is a TLAB?

TLAB stands for Thread-Local Allocation Buffer. The JVM reserves a small region in the heap for each thread so the thread can allocate objects quickly by bumping an allocation pointer within that region.

Simplified flow:

1. The JVM assigns a TLAB to a thread.
2. When the thread creates an eligible object, the JVM allocates it inside that thread's TLAB.
3. When the TLAB is nearly full or lacks enough space, the JVM allocates a new TLAB.
4. Objects that are not allocated in a TLAB may be allocated outside the TLAB.

TLABs reduce contention between threads when multiple threads allocate objects concurrently. In HotSpot, TLABs are enabled by default in standard configurations; `-XX:-UseTLAB` can disable them.

### 3.1. In-TLAB Allocation

Small objects that fit in the remaining space are typically allocated inside the TLAB. This is the common allocation path in many Java applications.

A TLAB has a finite size. When a new TLAB is needed, the JVM handles buffer allocation and may emit an event related to allocating the new TLAB.

### 3.2. Outside-TLAB Allocation

Large objects or objects that do not fit in a TLAB may be allocated outside the TLAB. These allocations can have a different cost profile than the TLAB fast path.

Do not assume an object must go outside a TLAB simply because its size exceeds a fixed threshold. That decision also depends on how much space remains in the TLAB, JVM configuration, and runtime behavior.

### 3.3. Why Distinguish Between the Two?

JMC can analyze both in-TLAB and outside-TLAB allocations. This helps determine whether pressure comes from a high volume of small, continuously created objects or from large objects.

However, event count does not equal the total number of objects in the application. In particular, events related to allocating a new TLAB do not represent every object allocated inside that TLAB.

## 4. Allocation-Related JFR Events

JFR collects data as timestamped events with payloads. On JDK 17, common events used in allocation analysis include:

| Event | Meaning and Key Data |
|---|---|
| jdk.ObjectAllocationSample | Weighted allocation sample, typically including class, thread, stack trace, and weight |
| jdk.ObjectAllocationInNewTLAB | Allocation information tied to allocating a new TLAB; includes class, allocation size, TLAB size, thread, and stack |
| jdk.ObjectAllocationOutsideTLAB | Object allocation information outside a TLAB; includes class, allocation size, thread, and stack |
| jdk.ThreadAllocationStatistics | Per-thread allocation statistics |

Event names and available fields should be verified against the recording's metadata and the running JDK version.

### 4.1. ObjectAllocationSample

`jdk.ObjectAllocationSample` is an allocation sampling event. It was introduced in JDK 16 to support allocation profiling with lower overhead than older detailed allocation events.

Useful fields:

- `objectClass`: the class of the sampled object.
- `eventThread`: the thread associated with the sample.
- `stackTrace`: the call stack at the allocation site.
- `weight`: the estimated number of bytes represented by the sample.

`weight` is a critical field. A single sample can represent many bytes of allocation; summing `weight` by class, thread, or stack trace provides an estimate of allocation pressure. Do not count each event as an exact single object, and do not treat `weight` as the exact size of the individual sampled object.

Sampling is a statistical method. The results are well suited for ranking hotspots and comparing trends; they are not an exhaustive inventory of every object created.

### 4.2. ObjectAllocationInNewTLAB

This event records allocation information associated with allocating a new TLAB. Common fields include:

- `objectClass`: the class of the associated object.
- `allocationSize`: the recorded allocation size.
- `tlabSize`: the size of the new TLAB.
- `eventThread` and `stackTrace`: the associated thread and call stack.

This event is not emitted for every small object allocated inside a TLAB. Do not treat the count of this event as the total number of objects created in TLABs.

### 4.3. ObjectAllocationOutsideTLAB

This event records allocations that occur outside a TLAB. It is typically useful when investigating large objects or allocations that cannot take the TLAB fast path.

The `allocationSize` field shows the recorded allocation size; `objectClass`, `eventThread`, and `stackTrace` help trace back to the allocation source.

### 4.4. ThreadAllocationStatistics

This event provides allocation statistics per thread. It is useful for identifying which threads allocate the most data—such as request workers, schedulers, background consumers, or batch workers.

Per-thread numbers should be interpreted alongside workload and active duration. A thread handling more requests may show higher allocation simply because it performs more work.

## 5. Choosing the Right Recording Template

JFR provides two built-in configurations in `<JAVA_HOME>/lib/jfr`:

| Template | Purpose |
|---|---|
| default.jfc | Baseline event set with low overhead, suitable for continuous recording |
| profile.jfc | Collects more data for time-bounded profiling; overhead and recording size are typically higher |

To find allocation hotspots, start with a short recording using `profile`. For continuous production recordings, consider `default` and verify whether the required allocation events are enabled.

Not every template, JMC configuration, or custom recording captures the same set of events. A recording may contain no allocation data even when the JVM supports JFR. Always check the actual events in the recording before concluding there are no allocations.

JDK 16 introduced `jdk.ObjectAllocationSample` and noted that it was enabled in both the standard `default` and `profile` configurations at that time. Detailed TLAB events carry higher overhead and may be disabled in standard templates. For any specific recording, inspect its event settings and metadata rather than relying on assumptions.

## 6. Starting a JFR Recording at Application Launch

You can start a recording as soon as the JVM launches using `-XX:StartFlightRecording`.

Practical syntax:

~~~powershell
java -XX:StartFlightRecording=name=allocation,settings=profile,duration=30s,filename=allocation.jfr AllocationDemo
~~~

Parameters:

- `name=allocation`: the recording name.
- `settings=profile`: uses the profiling template.
- `duration=30s`: records for 30 seconds.
- `filename=allocation.jfr`: output recording file written when the recording completes.

You can add `delay=10s` if you want to wait for application startup and warm-up before recording begins:

~~~powershell
java -XX:StartFlightRecording=name=allocation,settings=profile,delay=10s,duration=30s,filename=allocation.jfr AllocationDemo
~~~

A `.jfr` file is binary. Open it in JMC or use the JDK's `jfr` tool to inspect summaries and events.

## 7. Starting a Recording on a Running JVM

If the application is already running, find its PID:

~~~powershell
jcmd -l
~~~

Start a recording:

~~~powershell
jcmd <PID> JFR.start name=allocation settings=profile duration=30s filename=allocation.jfr
~~~

Check active recordings:

~~~powershell
jcmd <PID> JFR.check
~~~

If you want to record continuously and dump the file on demand once enough data is collected:

~~~powershell
jcmd <PID> JFR.start name=allocation settings=profile
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=allocation filename=allocation.jfr
jcmd <PID> JFR.stop name=allocation
~~~

`JFR.dump` writes the current data to a file while the recording keeps running. `JFR.stop` stops the recording. Use the correct PID, and run `jcmd` on the same machine under the same effective user/group as the target JVM process.

In production, choose a recording duration that matches the workload you need to observe. Do not enable high-overhead detailed events for long periods without evaluating their impact.

## 8. Opening a Recording in JDK Mission Control

JDK Mission Control (JMC) is a separate tool for viewing and analyzing `.jfr` files; it is not necessarily bundled with every JDK distribution.

Workflow:

1. Open JMC.
2. Select File → Open File... and choose `allocation.jfr`.
3. Open the recording in Flight Recorder.
4. Review Automated Analysis Results for warnings and areas to investigate.
5. Open the TLAB Allocations page or the corresponding Allocation page for your JMC version.
6. Select the time range containing the workload you want to analyze.
7. Compare allocations by class, thread, and stack trace.

The TLAB Allocations page in JMC can provide views such as:

- **Allocation by Class:** which classes account for the most allocation.
- **Allocation by Thread:** which threads account for the most allocation.
- **Allocation Profile:** a call-stack tree aggregating allocation sites.
- **By Top Methods:** some JMC versions also include a method-level view.

Tab names and layouts may vary across JMC versions. If you do not see the Allocation or TLAB Allocations page, check whether the recording contains allocation events and whether your JMC version supports those events.

## 9. Reading Allocation by Class

Start with the class list sorted by allocation amount. Look for classes with a large estimated total byte count or a high share of the recording.

Illustrative example:

| Class | Estimated Allocation | Initial Interpretation |
|---|---:|---|
| byte[] | 420 MB | Frequently created buffers or payloads |
| java.lang.String | 180 MB | String concatenation, parsing, formatting, or key generation |
| char[] | 95 MB | Text processing or data conversion |
| java.util.HashMap$Node | 72 MB | New entries as maps grow or are recreated repeatedly |
| com.example.OrderDto | 48 MB | DTOs created in the order-processing flow |

This is hypothetical data to illustrate how to read the table. A top-ranked class is not automatically a bug. `byte[]` may dominate bytes due to large buffers; `String` may dominate allocations because the application processes a lot of text.

After selecting a class:

1. Inspect the stack traces to find the methods creating the objects.
2. Identify the component or request path calling those methods.
3. Check whether the allocation occurs during startup, batch jobs, or normal requests.
4. Correlate the byte total with request volume and recording duration.
5. Check whether the objects are retained or short-lived.

If multiple classes share the same stack trace, the root cause may be a single method creating intermediate objects across multiple data types.

## 10. Reading Allocation by Thread

The per-thread view helps identify which work pools generate the most allocation.

Examples:

- `http-nio-8080-exec-*` may be HTTP request-handling threads.
- `pool-2-thread-*` may be executor worker threads.
- `scheduler-*` may be scheduled task threads.
- `kafka-consumer-*` may be message-receiving and processing threads.
- `batch-worker-*` may be batch job worker threads.

If a thread allocates heavily, check how much work that thread performs. Do not compare two threads by total bytes alone if one thread handles many times more requests than the other.

Analysis steps:

1. Select a thread with high allocation.
2. Open that thread's stack profile.
3. Find the application methods at the top of the allocation branches.
4. Correlate with request rate, batch size, or message count.
5. Compare allocation per unit of work, such as bytes/request or bytes/message.

If all workers show high allocation in the same method, the issue is likely in shared logic. If only one thread stands out, check for workload skew, oversized inputs, or a specific job.

## 11. Reading Allocation Profile and Stack Traces

Allocation Profile aggregates events into a call-stack tree. This is usually the most useful place to trace from an allocated class back to the application method requesting the allocation.

Illustrative example:

~~~text
com.example.OrderController.submit()
  com.example.OrderService.createOrder()
    com.example.OrderMapper.toDto()
      java.util.ArrayList.<init>()
      java.lang.StringBuilder.<init>()
      java.lang.String.substring()
~~~

This tree suggests `OrderMapper.toDto()` is creating intermediate lists and strings. Open the source code to check how often the method is called, collection sizes, and how text transformations are performed.

Read stack traces from the allocation method upward to its callers:

- Frames closest to the allocation show which API/class creates the object.
- The next frames show which application method calls that API.
- Higher frames show the request, batch, or message flow leading to the allocation.

A single class can be allocated from multiple stack traces. Address each allocation source according to its share and real-world impact rather than only fixing the class with the largest byte total.

## 12. Understanding Weight and Estimating Allocation Rate

With `jdk.ObjectAllocationSample`, `weight` is the estimated number of bytes represented by the sample. By aggregating samples across a recording, you can estimate allocation pressure by class, thread, or stack trace.

Simple formula:

\[
\text{Allocation rate} \approx
\frac{\text{Total sample weight (bytes)}}{\text{Recording duration (seconds)}}
\]

For example, if the total weight for a stack trace is 600 MiB over 60 seconds:

\[
600 \div 60 = 10\ \text{MiB/s}
\]

This is the estimated allocation rate for that stack trace over the observation window. When working with sample data, do not treat the result as an exact count of individual objects.

Review these together:

- Total allocated bytes.
- Number of samples/events.
- Class and stack trace.
- Thread performing the allocation.
- Recording duration.
- Workload during the same window.

Do not use event counts to calculate object counts when the event is a sampling event. Do not compare two recordings with different templates, durations, or workloads without explicitly noting those differences.

## 13. Using `jfr` to Read Allocation Events from the Terminal

First, inspect the recording summary:

~~~powershell
jfr summary allocation.jfr
~~~

Filter for allocation sample events:

~~~powershell
jfr print --events jdk.ObjectAllocationSample --stack-depth 12 allocation.jfr
~~~

Filter for TLAB events:

~~~powershell
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB --stack-depth 12 allocation.jfr
~~~

Inspect event metadata and fields:

~~~powershell
jfr metadata allocation.jfr
~~~

You can redirect output to a file to search for classes, threads, or stack traces:

~~~powershell
jfr print --events jdk.ObjectAllocationSample --stack-depth 12 allocation.jfr > allocation-events.txt
~~~

`jfr summary` shows which events are in the recording and how many were recorded. `jfr print` displays event details; `--events` filters by event type and `--stack-depth` controls stack trace depth.

If `jdk.ObjectAllocationSample` is missing from the summary, check the template, event settings, and JDK version. If a recording does not contain an event, `jfr print` cannot recover allocations that were never recorded.

## 14. Hands-On Example: Creating an Allocation Workload

Create `AllocationDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class AllocationDemo {
    private static volatile byte[] lastPayload;
    private static volatile String lastLabel;
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 1_000_000; i++) {
            byte[] payload = new byte[256 + (i & 2047)];
            payload[0] = (byte) i;
            lastPayload = payload;

            String label = "order-" + i + "-" + (i % 17);
            lastLabel = label;

            if (i % 5_000 == 0) {
                RETAINED.add(new byte[16 * 1024]);
            }
        }

        System.out.println("Allocation workload finished.");
        System.out.println("Retained arrays: " + RETAINED.size());

        // Keep the JVM alive so the recording can complete.
        Thread.sleep(35_000);
    }
}
~~~

This program intentionally allocates many temporary arrays and `String` instances. The `volatile` fields hold the latest references so the allocations remain observable; the `RETAINED` list keeps a subset of arrays alive to illustrate retained objects.

Compile:

~~~powershell
javac AllocationDemo.java
~~~

Run and record JFR for 30 seconds:

~~~powershell
java -XX:StartFlightRecording=name=allocation,settings=profile,duration=30s,filename=allocation.jfr AllocationDemo
~~~

Stdout printed by the program:

~~~text
Allocation workload finished.
Retained arrays: 200
~~~

Depending on the JDK, JFR may print additional messages when starting the recording. The two lines above are the application's output after the workload completes; the number of events and sample weights in the recording depend on runtime behavior.

Once the file is created:

~~~powershell
jfr summary allocation.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 12 allocation.jfr
~~~

Open `allocation.jfr` in JMC and compare the `byte[]` and `java.lang.String` classes, the `main` thread, and the stack trace of `AllocationDemo.main()`.

This example creates both short-lived and retained objects. When reading the recording, distinguish the allocation pressure from the loop from the roughly 200 arrays retained in the list.

## 15. From Allocation Hotspots to Code Improvements

Once you have identified a high-allocation method, determine why it creates objects and whether you can reduce allocations while preserving behavior.

### 15.1. Reduce Intermediate Objects

Inspect data conversion steps that create unnecessary collections, wrappers, DTOs, or temporary objects. If multiple steps copy the same data, consider passing data in a more suitable representation or reducing the number of conversions.

### 15.2. Control String Allocations

String concatenation, formatting, parsing, and key generation inside loops can create many `String` objects and backing arrays. Check the stack trace to see where the allocations originate.

Use `StringBuilder` when building strings across multiple steps. Avoid creating intermediate strings if an API can accept buffers or streams directly. Do not mechanically replace every concatenation with `StringBuilder`; the compiler can already optimize simple concatenations.

### 15.3. Size Collections Appropriately

When the approximate size is known in advance, initializing `ArrayList` or `HashMap` with an appropriate capacity can reduce resizing and backing-array allocations.

Do not over-allocate capacity for every collection. Balance fewer resizes against holding unused memory.

### 15.4. Reduce Buffer Copies

If stack traces show heavy `byte[]` or `char[]` allocations, look for repeated copying, encoding/decoding, serialization, or buffering steps. You can often reduce copies, process data in chunks, or reuse buffers with a clear lifecycle.

Reusing buffers requires attention to thread safety, stale data, and holding oversized buffers after load drops. Do not introduce object pools just because an allocation profile shows many small objects; pooling can increase retention, synchronization overhead, and complexity.

### 15.5. Evaluate Under Realistic Workloads

After making changes:

1. Run the same workload for the same duration.
2. Use the same JDK, GC, and recording template.
3. Compare allocation rate, class/stack hotspots, and GC activity.
4. Check throughput and latency.
5. Check post-GC heap usage to ensure retention has not increased.

A change that reduces allocations at the expense of higher CPU or latency may not be a net improvement.

## 16. Distinguishing Allocation Pressure, GC Pressure, and Memory Leaks

| Symptom | Likely Cause | Evidence to Check |
|---|---|---|
| High allocation rate, stable post-GC heap | Many temporary objects created and reclaimed | Allocation Profile, GC frequency and pauses |
| High allocation rate, frequent GC runs | Allocation pressure causing extra GC work | Allocation rate alongside GC events/pauses |
| Post-GC heap grows across cycles | Long-lived objects or increasing retention | Heap dump, old-object samples, GC roots |
| One class dominates allocation but is not live after GC | Temporary objects, not necessarily a leak | Allocation stacks and live set |
| A loader/cache/collection holds growing objects | Possible retention or memory leak | Heap dump and reference paths |

JFR allocation samples do not prove a memory leak. To find long-lived objects, use JFR `jdk.OldObjectSample` if the recording is configured appropriately, or capture a heap dump and analyze reference paths from GC roots.

In JDK 17, JFR can also record information about old objects and paths to GC roots. Collecting path-to-GC-roots data can pause the application for a period of time; enable it only when a leak is suspected and after weighing the impact.

## 17. Common Pitfalls in Allocation Analysis

| Symptom | Common Cause | How to Handle |
|---|---|---|
| TLAB Allocations missing in JMC | Recording did not enable allocation events or JMC does not support them | Check `jfr summary`, event settings, and JMC version |
| `jdk.ObjectAllocationSample` missing | Custom template or event disabled | Record with an appropriate template or enable the event in a template copy |
| Low sample weight or few samples | Short workload, low allocation, or insufficient sampling | Record longer under a representative workload and review event settings |
| Incomplete stack traces | Stack traces disabled or stack depth too small | Enable stack traces for the event and increase stack depth as needed |
| Allocation by Class differs from heap bytes | Allocation is cumulative over time; heap is current retained state | Compare with GC and live set; do not use the two numbers interchangeably |
| Many TLAB events without knowing object count | TLAB events do not record every object inside a TLAB | Use `ObjectAllocationSample` and interpret `weight` properly |
| Recording file too large | Too many events enabled or profiling template used for too long | Shorten duration, select only needed events, use `default` for continuous recording |
| Results differ between two recordings | Different workloads, durations, templates, or JDKs | Standardize measurement conditions and compare allocation rates |
| Application methods not visible | Stack truncated or allocation happens inside a library | Increase stack depth and trace callers upward in the profile |

## 18. Overhead and Securing Recordings

JFR is designed for low-overhead profiling and runtime diagnostics, though actual overhead depends on the application, event settings, duration, and volume of recorded data. The `profile` template collects more data and can incur higher overhead and larger file sizes than `default`.

Key practices:

- Start with short recordings and a representative workload.
- Enable detailed events only when samples are insufficient to locate hotspots.
- Do not record excessive events for long periods without evaluating overhead.
- Monitor file sizes and set age/size limits for continuous recordings.
- Do not enable Heap Statistics solely to find allocation hotspots; it can trigger an old GC and alter pause behavior.
- Record the JDK, GC, template, duration, and workload alongside the recording file.

A `.jfr` file can contain class names, package names, method names, stack traces, thread names, file paths, and custom event payloads. Restrict file access permissions, avoid publishing recordings publicly without review, and redact or sanitize shared copies when needed.

## 19. Allocation Analysis Workflow During an Incident

1. Identify the symptom: frequent GC, high CPU, high latency, or growing heap.
2. Select a representative workload and time window exhibiting the symptom.
3. Capture a time-bounded JFR recording using `profile`.
4. Check `jfr summary` to confirm allocation events were recorded.
5. Open the file in JMC and inspect TLAB Allocations / Allocation Profile.
6. Rank by class, thread, and stack trace.
7. Estimate the allocation rate by dividing sample `weight` by duration.
8. Open the source code for the top methods and identify intermediate objects.
9. Correlate with GC pauses and post-GC heap to separate temporary allocations from retention.
10. Make a small change, re-measure under the same workload, and compare results.

## 20. Allocation Reading Checklist

- [ ] Selected the right JVM, JDK, and time window with active workload.
- [ ] Confirmed the recording contains the allocation events needed for analysis.
- [ ] Understood that `jdk.ObjectAllocationSample` is a sampling event and `weight` is an estimated byte count.
- [ ] Avoided treating sample counts as exact object counts.
- [ ] Distinguished in-TLAB allocation from outside-TLAB allocation.
- [ ] Avoided treating new-TLAB allocation events as every object created in TLABs.
- [ ] Reviewed Allocation by Class, Allocation by Thread, and Allocation Profile.
- [ ] Found the first stack frames belonging to application code.
- [ ] Evaluated allocation rate over time and relative to workload.
- [ ] Distinguished allocated bytes from retained heap and post-GC live objects.
- [ ] Correlated with GC activity and heap/live set where needed.
- [ ] Re-measured with the same workload and template after optimization.
- [ ] Secured and redacted the `.jfr` file before sharing.

Allocation analysis with JFR helps locate the classes, threads, and stack traces creating the most objects. Use `jdk.ObjectAllocationSample` to estimate allocation pressure, TLAB events to understand allocation paths, and JMC to trace from classes back to methods. Then correlate with GC and live heap: reducing allocations can ease GC pressure, whereas a memory leak requires evidence that objects remain retained after collection.

## References

- Oracle, Java SE 17 Troubleshooting Guide — Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle, Java SE 17 — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Java SE 17 — The jfr Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle, Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle, Java SE 17 — Flight Recorder Configurations: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html
- Oracle, Java SE 17 API — jdk.jfr package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle, JDK Mission Control 9 User Guide — Flight Recorder: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html
- Oracle, JDK 16 Release Notes — New jdk.ObjectAllocationSample Event Enabled by Default: https://www.oracle.com/java/technologies/javase/16-relnote-issues.html

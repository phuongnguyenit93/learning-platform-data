# Measuring Allocation in Java

**Allocation** is the process by which the JVM allocates heap memory for new objects and arrays. Measuring allocation helps determine how many bytes of objects an application creates over a period of time, which classes are instantiated most frequently, which methods are the primary allocation sites, and which threads create the most objects.

A high allocation rate can fill Eden quickly, increase garbage collection (GC) frequency, increase CPU time spent on GC, and impact throughput. However, high allocation is not automatically a memory leak: many objects are short-lived and are reclaimed by GC. To understand the problem, you need to measure the volume of objects created, the volume of objects still alive after GC, and the code paths performing the allocations.

Commonly used tools:

- **Java Flight Recorder (JFR) and JDK Mission Control (JMC)**: find classes, threads, and stack traces that allocate many objects.
- **ThreadMXBean**: approximately measure the number of heap bytes allocated by a platform thread.
- **JMH with the GC profiler**: measure allocation per operation in microbenchmarks.
- **jstat and GC logs**: observe allocation pressure indirectly through Eden, heap, and GC behavior.

## 1. What Is Allocation and Why Measure It?

When code executes the `new` instruction, the JVM allocates a memory region for the object. For example:

~~~java
Customer customer = new Customer();
byte[] payload = new byte[4096];
List<String> names = new ArrayList<>();
~~~

Each allocated object or array increases the amount of heap in use. Applications often create many short-lived objects such as request DTOs, iterators, temporary `String` instances, wrappers, intermediate collections, and buffers.

If objects are no longer reachable, GC can reclaim them. Creating and then reclaiming objects still incurs costs:

- The JVM must allocate memory and update metadata.
- A TLAB can fill up and require a new one to be allocated.
- GC must locate and reclaim dead objects.
- Allocation and GC can increase CPU usage.
- GC pauses or concurrent GC activity can affect latency and throughput.

Measuring allocation answers the following questions:

- How many MB per second does the application allocate?
- How many bytes does each request or operation create?
- Which class is allocated the most?
- Which method is the primary allocation site?
- Which thread creates the most objects?
- Are objects allocated inside a TLAB or outside a TLAB?
- Does increased allocation cause more frequent GC?

## 2. Distinguishing Allocation, Live Set, Retained Heap, and RSS

These are four different metrics.

| Concept | Meaning | Question |
|---|---|---|
| Allocation | Total volume of new objects created during the measurement interval | How many bytes does the application create? |
| Live set | Volume of objects remaining alive after GC reclaims unreachable objects | How many bytes still need to be kept? |
| Retained heap | Amount of heap that could be reclaimed if the target object became unreachable | Which objects are holding onto memory? |
| RSS | Resident memory of the process in the operating system | How much RAM is the process occupying? |

For example, suppose a request creates 10 MB of temporary objects but retains only 100 KB after processing:

- Request allocation: about 10 MB.
- Live set increase after the request: possibly only about 100 KB.
- Retained heap depends on the references keeping objects alive.
- RSS also depends on native memory, metaspace, thread stacks, and other regions.

An application can have a high allocation rate while its live set remains stable. This is usually allocation pressure, not necessarily a memory leak.

Conversely, a moderate allocation rate accompanied by a continuously growing live set can be a sign that objects are being retained unexpectedly.

## 3. Allocation Measurement Units and Formulas

### Allocation rate

Allocation rate is the amount of memory allocated per unit of time:

\[
\text{Allocation rate} =
\frac{\text{allocated bytes}_{after}-\text{allocated bytes}_{before}}
{\text{elapsed seconds}}
\]

For example, if a thread allocates an additional 200 MB over 10 seconds:

\[
200/10 = 20\ \text{MB/s}
\]

Clearly specify whether MB means \(10^6\) bytes or MiB means \(2^{20}\) bytes, as tools may use different conventions.

### Bytes per operation

When measuring a workload with a known operation count:

\[
\text{Bytes/op} =
\frac{\Delta \text{allocated bytes}}{\text{operation count}}
\]

If 100,000 operations create a total of 50 MiB:

\[
50 \times 1024^2 / 100000 = 524.29\ \text{B/op}
\]

This metric is useful when comparing two implementations of the same functionality.

### Per-thread allocation

For an individual thread:

\[
\text{Thread allocation rate} =
\frac{\text{thread allocated bytes in the measurement interval}}
{\text{elapsed seconds}}
\]

Comparing across threads helps identify which worker or request handler creates the most objects.

### Use deltas instead of absolute counters

Many APIs report cumulative total allocations since the JVM or thread started. Take two snapshots:

~~~text
allocated_before = 120,000,000 bytes
allocated_after  = 220,000,000 bytes
delta            = 100,000,000 bytes
~~~

Do not use cumulative values directly to conclude the allocation rate of a single request or time window.

## 4. TLAB and Allocation Outside TLAB

HotSpot typically uses a **Thread Local Allocation Buffer (TLAB)** to allocate small objects faster.

A TLAB is a heap region dedicated to a single thread. When a thread creates an eligible object, the JVM can allocate it by bumping a pointer within its TLAB rather than synchronizing with other threads for every object.

~~~text
Java heap
+-----------------------------------------------------+
| Thread A's TLAB   | Thread B's TLAB   | other area  |
| [obj][obj][obj]   | [obj][obj]        |             |
+-----------------------------------------------------+
        |                    |
        v                    v
   Thread A              Thread B
~~~

When a TLAB becomes nearly full, the thread needs a new TLAB. Large objects or objects that do not fit in a TLAB may be allocated directly outside the TLAB.

| Allocation category | Characteristics |
|---|---|
| In TLAB | Typically small objects allocated in the thread's private buffer |
| Outside TLAB | Objects allocated directly outside a TLAB |
| TLAB refill | A thread needs a new TLAB when the current buffer no longer has enough space |

TLABs reduce contention on the object allocation path. Allocations inside a TLAB still consume heap and still must be processed by GC when objects become unreachable.

## 5. Measuring Allocation with Java Flight Recorder

JFR is well suited for finding allocation sites in a running application. A recording can include information about allocated classes, threads, allocation sizes, and stack traces depending on the events and settings.

Commonly used events:

| Event | Purpose |
|---|---|
| `jdk.ObjectAllocationInNewTLAB` | Allocations associated with acquiring a new TLAB |
| `jdk.ObjectAllocationOutsideTLAB` | Objects allocated outside a TLAB |
| `jdk.ThreadAllocationStatistics` | Per-thread allocation statistics |

Available events and fields can vary by JDK/JVM. Check the metadata and settings of the actual recording.

### Choosing recording settings

The `default.jfc` template is designed for low-overhead continuous recording. In JDK 26, continuous recording with the default template does not collect allocation profiling.

The `profile.jfc` template collects more data and is suitable for short-duration profiling. The recording can produce more data and higher overhead.

Do not enable detailed allocation profiling indefinitely in production without evaluating overhead and storage capacity.

### Starting a recording with jcmd

Find the JVM:

~~~bash
jcmd -l
~~~

Assuming the application PID is 2125, start a 60-second recording:

~~~bash
jcmd 2125 JFR.start name=allocation settings=profile duration=60s filename=allocation.jfr
~~~

Check the recording:

~~~bash
jcmd 2125 JFR.check
~~~

Stop early and dump the file if needed:

~~~bash
jcmd 2125 JFR.stop name=allocation filename=allocation-final.jfr
~~~

Use the real PID. `jcmd` must run on the same machine and under an effective user/group compatible with the target process.

### Reading allocation events

View the summary:

~~~bash
jfr summary allocation.jfr
~~~

Filter allocation events:

~~~bash
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB,jdk.ThreadAllocationStatistics allocation.jfr
~~~

View metadata:

~~~bash
jfr metadata allocation.jfr
~~~

If no events appear, check the template and active settings before concluding that the application is not allocating objects.

## 6. Analyzing Allocation with JDK Mission Control

JMC provides the **TLAB Allocations** page to inspect allocations inside and outside TLABs.

| View | Question |
|---|---|
| Allocation by Class | Which class is allocated the most? |
| Allocation by Thread | Which thread creates the most objects? |
| Allocation Profile | Which stack traces produce the most allocations? |
| By Top Methods | Which methods produce the most allocations? |
| Alloc Total | What is the total allocation volume over time? |

Workflow:

1. Open `allocation.jfr` in JMC.
2. Verify the recording duration and workload.
3. Open the Memory or TLAB Allocations page.
4. Check Allocation by Class to find classes with large allocations.
5. Check Allocation by Thread to find threads creating many objects.
6. Open Allocation Profile to inspect aggregated stack traces.
7. Select a top method and open its corresponding source code.
8. Check whether objects are created inside loops, mapping, serialization, or request handling.
9. Correlate allocations with GC events and heap usage.
10. Re-measure after optimization using the same workload.

Do not look only at instance counts. A class with many small instances can consume less memory than a class that creates fewer instances where each instance holds a large array.

### Reading an allocation profile

Illustrative example:

~~~text
com.acme.OrderService.process
  com.acme.OrderMapper.map
    java.lang.String
    java.util.ArrayList
    byte[]
  com.acme.JsonEncoder.encode
    byte[]
~~~

If `byte[]` appears heavily under `JsonEncoder`, check whether encoding creates intermediate buffers or copies data multiple times.

Stack traces help pinpoint allocation sites. From there, check:

- Are objects being created inside a loop?
- Can buffers be safely reused?
- Can the number of copies be reduced?
- Can collections be initialized with an appropriate capacity?
- Can boxing or repeated data conversions be avoided?

Every optimization must preserve semantics and thread safety. Do not reuse mutable objects across multiple threads without a clear ownership and synchronization mechanism.

## 7. Measuring Per-Thread Allocation with ThreadMXBean

HotSpot provides the `com.sun.management.ThreadMXBean` extension to approximately measure the total number of heap bytes allocated by a platform thread.

| Method | Meaning |
|---|---|
| `getCurrentThreadAllocatedBytes()` | Total heap bytes allocated by the current thread |
| `getThreadAllocatedBytes(id)` | Total heap bytes allocated by the thread with the specified ID |
| `getTotalThreadAllocatedBytes()` | Total heap bytes allocated by threads since JVM startup |
| `isThreadAllocatedMemorySupported()` | Whether the JVM supports per-thread allocation measurement |
| `isThreadAllocatedMemoryEnabled()` | Whether per-thread allocation measurement is enabled |
| `setThreadAllocatedMemoryEnabled(true)` | Enables allocation measurement if supported by the JVM |

The reported value is an approximation. It is not the amount of live objects or retained heap.

### Example: measuring delta for the current thread

~~~java
import java.lang.management.ManagementFactory;

public class ThreadAllocationCounter {
    public static void main(String[] args) {
        java.lang.management.ThreadMXBean platformBean =
                ManagementFactory.getThreadMXBean();

        if (!(platformBean instanceof com.sun.management.ThreadMXBean bean)
                || !bean.isThreadAllocatedMemorySupported()) {
            System.out.println("ALLOC_METRIC_SUPPORTED=false");
            return;
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        long before = bean.getCurrentThreadAllocatedBytes();

        byte[][] values = new byte[1000][];
        for (int i = 0; i < values.length; i++) {
            values[i] = new byte[1024];
        }

        long after = bean.getCurrentThreadAllocatedBytes();
        long allocated = after - before;

        System.out.println("ALLOC_METRIC_SUPPORTED=true");
        System.out.println("OBJECTS=" + values.length);
        System.out.println("ALLOCATED_BYTES=" + allocated);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 ThreadAllocationCounter.java
java ThreadAllocationCounter
~~~

The output looks like:

~~~text
ALLOC_METRIC_SUPPORTED=true
OBJECTS=1000
ALLOCATED_BYTES=<value measured by the JVM>
~~~

The byte count depends on object layout, JDK, JVM, and platform. This example measures the allocation of the `main` thread for the code between the two counter reads.

Limitations:

- The counter is the cumulative allocation of the thread; take a delta to measure an interval.
- The value is approximate and may be updated lazily depending on the JVM.
- If measurement is not enabled, the method may return `-1`.
- A JVM implementation may not support this feature.
- In JDK 26, `getThreadAllocatedBytes` returns `-1` for virtual threads.
- The counter does not tell you which class or method performed the allocation; use JFR to find allocation sites.

## 8. Measuring Allocation with the JMH GC Profiler

When comparing two implementations of a small operation, **Java Microbenchmark Harness (JMH)** is more appropriate than writing a manual loop with `System.nanoTime()`.

Run the benchmark with the GC profiler:

~~~bash
java -jar target/benchmarks.jar -prof gc
~~~

Common metrics:

| Metric | Meaning |
|---|---|
| `gc.alloc.rate` | Allocation rate, typically in MB/s |
| `gc.alloc.rate.norm` | Allocation per operation, typically in B/op |
| `gc.churn.*` | Volume of objects reclaimed in memory pools over time |
| `gc.churn.*.norm` | Churn normalized per operation |
| `gc.count` | Number of collections during the benchmark |
| `gc.time` | Collection time recorded during the benchmark |

Illustrative output example:

~~~text
Benchmark                         Mode  Cnt    Score
StringMapping.benchmark           avgt    5  1200.0 ns/op

StringMapping.benchmark:gc.alloc.rate       500.0 MB/sec
StringMapping.benchmark:gc.alloc.rate.norm  512.0 B/op
StringMapping.benchmark:gc.count            12 counts
StringMapping.benchmark:gc.time             18 ms
~~~

The numbers above only illustrate the format. If implementation A allocates 512 B/op and B allocates 128 B/op, B reduces allocation per operation by:

\[
\frac{512-128}{512}\times100 = 75\%
\]

This is the reduction in allocation, which does not automatically mean latency also drops by 75%. Compare throughput, latency, GC count, and GC time as well.

To keep benchmarks reliable:

- Use warmup and multiple measurement iterations.
- Use multiple forks to reduce the impact of prior JVM state.
- Choose inputs representative of production.
- Use `Blackhole` or observable results to avoid dead-code elimination.
- Keep the same JDK, collector, heap, and hardware when comparing.
- Read both `gc.alloc.rate` and `gc.alloc.rate.norm`.

The absolute allocation rate depends on benchmark execution speed. Therefore, bytes/op is usually more useful when evaluating the allocation cost of an operation.

## 9. Using jstat to Observe Allocation Pressure Indirectly

`jstat` does not provide allocation sites and is not a tool for measuring exact bytes allocated. Nevertheless, Eden and GC statistics help observe allocation pressure.

Find the JVM:

~~~bash
jps -l
~~~

Sample GC utilization:

~~~bash
jstat -gcutil 2125 1000 10
~~~

Columns of interest:

| Column | Meaning |
|---|---|
| E | Percentage of Eden currently used |
| O | Percentage of Old Space currently used |
| YGC | Cumulative number of Young GCs |
| YGCT | Cumulative Young GC time |
| FGC | Cumulative number of Full GCs |
| FGCT | Cumulative Full GC time |
| GCT | Cumulative total GC time |

`E` rising rapidly and dropping when `YGC` occurs shows that Eden is receiving allocations. A rapidly increasing `YGC` can reflect allocation pressure. `O` increasing over multiple cycles can be caused by promotion or a growing live set.

Do not infer exact allocated bytes/second from `E` or `YGC` alone. Eden size can change, and objects can be promoted or reclaimed.

## 10. GC Logs Help Explain Allocation Impact

GC logs show when collections happen, why they happened, heap before/after, and pause times.

Enable unified GC logging:

~~~bash
java -Xlog:gc*:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Example capturing additional GC phase details:

~~~bash
java -Xlog:gc*,gc+phases=debug:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

List available tags and levels:

~~~bash
java -Xlog:help
~~~

Illustrative log line example:

~~~text
[0.123s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 25M->4M(64M) 2.345ms
~~~

- `0.123s` is the uptime since JVM startup.
- `GC(0)` is the collection ID.
- `Pause Young` describes the collection and pause type.
- `25M->4M` is the heap used before and after the collection.
- `(64M)` is the committed heap capacity in this example.
- `2.345ms` is the pause duration.

GC logs do not directly tell you which method created the objects. Use a JFR allocation profile to find allocation sites.

## 11. Measuring Allocation and GC Together with JFR

JFR lets you correlate allocation, heap usage, and GC along the same timeline.

Useful events:

| Event | Purpose |
|---|---|
| `jdk.GarbageCollection` | Information about a GC cycle |
| `jdk.GCPhasePause` | Duration of pause phases |
| `jdk.GCHeapSummary` | Heap statistics around GC |
| `jdk.ObjectAllocationInNewTLAB` | Allocation associated with TLAB refills |
| `jdk.ObjectAllocationOutsideTLAB` | Allocation outside TLABs |
| `jdk.ThreadAllocationStatistics` | Per-thread allocation |

Start a 5-minute profile recording:

~~~bash
jcmd 2125 JFR.start name=memory-profile settings=profile duration=5m filename=memory-profile.jfr
~~~

Read allocation and GC events:

~~~bash
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB,jdk.ThreadAllocationStatistics,jdk.GarbageCollection,jdk.GCPhasePause memory-profile.jfr
~~~

In JMC, inspect TLAB Allocations and Garbage Collections to find allocation sites, threads, and pauses. Do not enable Heap Statistics if you are measuring latency and do not need live-set analysis, because this feature can trigger additional old GCs at the start and end of the recording.

## 12. Common Mistakes When Measuring Allocation

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing allocation with live set | Wrong conclusion about a memory leak | Compare allocation against post-GC heap |
| Looking only at object count | Missing large objects | Check allocated bytes and class |
| Using cumulative counter as rate | Result is not scoped to the interval | Take a delta and divide by elapsed time |
| Measuring before warmup | Results skewed by JIT and class loading | Warm up before taking a baseline |
| Benchmarking without multiple forks | Noisy results | Use JMH and multiple forks |
| Checking only jstat | Cannot find allocation sites | Use JFR/JMC |
| Checking only JFR default | No allocation profiling collected | Use `profile` or custom settings |
| Measuring all threads with one counter | Cannot tell which thread creates objects | Use per-thread `ThreadMXBean` or JMC |
| Using ThreadMXBean on virtual threads | Counter may return `-1` | Use JFR or an appropriate tool |
| Reusing objects unsafely | Introduces race conditions | Verify ownership and thread safety |
| Leaving detailed profiling on too long | Large recordings and higher overhead | Limit duration and event settings |

## 13. Practical Allocation Measurement Workflow

1. Identify the symptom: frequent GC, increased latency, or growing heap.
2. Record the JDK, collector, heap size, and workload.
3. Choose the metric: MB/s, B/op, per-thread allocation, or allocation sites.
4. Use a short JFR `profile` recording to find high-allocating classes and stack traces.
5. Use JMC Allocation by Class, Thread, and Allocation Profile.
6. Use `ThreadMXBean` when you need a per-platform-thread counter.
7. Use JMH `-prof gc` when comparing implementations.
8. Use `jstat` and GC logs to observe allocation pressure and its impact on GC.
9. Distinguish temporary objects from objects that survive GC.
10. Pick the largest allocation site that can be optimized while preserving semantics.
11. Change one factor at a time.
12. Re-measure under the same workload and configuration.
13. Compare B/op, MB/s, GC count, GC time, latency, and throughput.
14. Document the JDK, collector, settings, and results.

## 14. Key Takeaways

- Allocation is the total volume of new objects created; live set is the objects still alive after GC.
- Allocation rate measures bytes/second; bytes/op measures bytes per operation.
- TLABs make allocating small objects faster; large objects may be allocated outside TLABs.
- JFR and JMC help find classes, threads, and stack traces that create many objects.
- The JFR default continuous template does not collect allocation profiling in JDK 26; use `profile` for short-duration profiling.
- `ThreadMXBean` provides an approximate per-platform-thread allocation counter.
- JMH `-prof gc` measures allocation rate, bytes/op, GC count, and GC time.
- `jstat` only gives indirect allocation pressure signals via Eden and GC.
- GC logs show collections and heap before/after, not allocation sites.
- High allocation is not automatically a memory leak; correlate with live set and retained heap.
- Always re-measure with an equivalent workload after optimizing.

## Official References

- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Troubleshoot Performance Issues Using Flight Recorder — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [ThreadMXBean — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/ThreadMXBean.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The java Command — Unified Logging, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JMH GC Profiler Sample — OpenJDK](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java)

# 11.3 Allocation rate, object lifetime, and pressure on the collector

> Context: Java 17+ on the HotSpot JVM. The object flow section uses G1 GC as a concrete example; allocation policies, generations, and object movement vary by collector, JDK version, and configuration.

## Learning objectives

After this lesson, you can:
- Calculate and interpret **allocation rate** without confusing it with the amount of heap currently in use.
- Explain why **object lifetime / survival across GC** changes collection cost, promotion, and pressure on the old generation.
- Distinguish **allocation churn** (continuous creation of short-lived objects), legitimate **retention**, and a **memory leak** caused by unintended lingering references.
- Use GC logs, Java Flight Recorder (JFR), Java Mission Control (JMC), and controlled measurements to find root causes before optimizing.

## 1. Three quantities to keep separate

**Allocation rate** is the total number of bytes a program allocates over an interval, divided by the measurement duration:

~~~text
allocation rate (MiB/s) ≈ allocated bytes / elapsed seconds / 1_048_576
~~~

For example, if a processing flow creates 600 MiB of objects in 5 seconds, the average allocation rate is 120 MiB/s. This is **allocation throughput**, not a statement that the heap must grow by 600 MiB after 5 seconds. Most of those objects may already have become unreachable and had their space reused by GC.

**Live set / retained heap** is the amount of objects still *reachable* from GC roots at the time of observation. GC roots can include active local/stack references, static fields, threads, JNI handles, and JVM structures. Heap usage before GC includes dead objects not yet reclaimed; heap usage after an appropriate GC cycle is usually closer to the live set, though it still depends on the collector phase.

**Object lifetime** is the time from when an object is created until it is no longer reachable. The moment an object is *physically reclaimed* may be later than when it dies in terms of reachability. **Object age** in a generational GC is typically counted in the number of young collections an object has survived; it is not synonymous with how many milliseconds the object has existed.

For example, a web service receiving 10,000 requests/second and allocating an average of 12 KiB/request:

~~~text
10_000 × 12 KiB/s = 120_000 KiB/s ≈ 117.2 MiB/s
~~~

If 99% of allocations quickly become unreachable, the program can still generate GC pressure because it continually needs allocation space. If the remaining 1% **keeps being held indefinitely** in an unbounded cache, that portion alone grows at roughly 1.17 MiB/s, approximately 70 MiB/minute. A small retention ratio is still dangerous when sustained without an eviction/release policy.

## 2. An object's journey in the heap and its relationship with GC

With a typical HotSpot G1 configuration, the general flow can be pictured as follows:

1. A Java thread typically allocates small objects into a **Thread-Local Allocation Buffer (TLAB)** to avoid contention on the fast allocation path. When a TLAB runs out of space, the thread requests a new buffer; some allocations bypass TLABs.
2. Most new objects are placed in **Eden** regions of the young generation. G1 divides the heap into *regions* and adjusts the number of young regions according to the collector's goals.
3. Young GC finds reachable young objects and **evacuates/copies** live objects to Survivor or Old; dead objects do not need to be copied individually. An object may survive multiple young GCs before being promoted; age thresholds and movement rules are decided by the collector.
4. When many objects live longer, the volume of data to copy, Survivor usage, and the rate of moving objects to Old all rise. Higher Old occupancy or more Old collection work can lead to mixed collections, concurrent marking, or other costly collection events.
5. Very large objects can take a special allocation path; G1 has the concept of *humongous objects* occupying dedicated regions. Therefore, do not assume that **every** object moves sequentially through Eden → Survivor → Old.

Not every collector has the same concept of generations/age: mechanisms and log details differ among G1, Parallel GC, ZGC, and Shenandoah; some collectors/versions also have separate generational modes. Check the actual collector used by the JVM before interpreting promotion or memory regions.

### Why does lifetime matter?

| Object group | Examples | Common consequences |
| --- | --- | --- |
| Very short-lived | Intermediate strings, wrappers, temporary arrays for one operation | Allocation rate can be high while survival rate across young GC is low; young GC usually reclaims plenty of space |
| Survives a few young GCs | Queued requests, in-flight batches, briefly shared objects | Increases Survivor copying cost and may get promoted |
| Intentionally long-lived | Configuration, bounded caches, active indexes | Contributes to baseline live set; needs clear sizing and bounds |
| Unintentionally retained | Unbounded growing static Map, unregistered listeners, unconsumed queues, lingering reference chains | Old/live set may grow over time and eventually exhaust the heap |

Living long **is not automatically a leak**: a stable cache can be valid. Conversely, a low allocation rate does not guarantee healthy GC if the live set is too large.

## 3. Why do allocation rate and lifetime create pressure on the collector?

At least four mechanisms are involved:

**(1) Exhausting fast allocation space.** The faster objects are created, the sooner Eden/TLABs must be refilled and the more frequently young collections can occur. An intuitive approximation:

~~~text
interval between young GCs ≈ usable young allocation capacity / allocation rate into that region
~~~

Assuming usable young allocation capacity is 192 MiB and threads allocate into it at 96 MiB/s, the idealized interval is roughly 2 seconds. This is only a simplified model: TLAB waste, changing young generation size, large allocations, survivors, and collector policy make the real number differ.

**(2) Collection cost depends on *live objects*.** GC largely processes live data to mark/copy/relocate. An Eden full of dead objects can be relatively cheap to reclaim; an Eden holding many live objects that must be copied consumes CPU and memory bandwidth and can increase pauses.

**(3) Pressure on Old.** When objects live long enough or Survivor lacks space, they may be moved to Old. High promotion drives up old occupancy, adds work for concurrent marking/mixed GCs, and risks running out of evacuation space. **Promotion rate is not identical to allocation rate**, and rising old occupancy does not directly measure newly retained bytes either, because concurrent GC may reclaim older objects.

**(4) Resource contention with the application.** GC uses CPU, caches, memory bandwidth, and sometimes Stop-The-World (STW) phases; heavy collector activity can reduce throughput or degrade tail latency. Distinguish **GC CPU / total CPU**, **total pause time / uptime**, **p95/p99 pause**, and **p95/p99 request latency**: they are related, not the same quantity.

Thus, GC pressure cannot be concluded from a single MiB/s measurement. You must evaluate **allocation rate + lifetime/survival distribution + live set + heap/collector configuration + latency/throughput targets** together.

## 4. Allocation churn, retention, and leak: distinguishing by symptoms

- **High churn, stable live set:** Many bytes allocated per second; GC runs fairly often, yet post-GC heap remains nearly flat. Likely continuous temporary object creation. Optimize only if GC/CPU cost or latency genuinely exceeds targets.
- **High promotion, rising post-GC heap:** Many objects survive young GCs or more long-lived references are added. Inspect caches, queues, sessions, and slow processing pipelines. This is **suspected retention**, not yet enough to declare a leak.
- **Large live set, low allocation rate:** Memory needed for valid state may simply be large. The issue here is usually footprint/old GC/heap limit rather than creating objects too quickly.
- **Unbounded rising old occupancy under steady workload:** Inspect what retains the objects and whether input rate exceeds consumption capacity. Only after finding an unintended reference chain should you conclude a memory leak.

A heap *spike* before young GC is normal. Do not infer a leak from the sawtooth curve of a used-heap graph; observe the memory baseline across multiple comparable GC cycles at the same load level.

## 5. Practical measurement: using the right tool for the right question

### 5.1 GC unified logging: knowing when GC runs and what it costs

On HotSpot Java 17+, you can run the application with GC logging:

~~~sh
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*,gc+age=trace:file=gc.log:time,uptime,level,tags AllocationLifetimeDemo
~~~

This is an illustrative configuration for observation, **not** a default tuning flag set for production systems. In the log, compare timestamps, GC types, pause durations, heap before/after GC, changes across Eden/Survivor/Old regions, and age/survivor details when output by the collector. GC logs do not by themselves identify which exact line of Java code creates many objects.

When evaluating a service, compare over the same time window with request rate, throughput, tail latency, and CPU. If you change the collector or JDK version, event names and the meaning of some counters may differ.

### 5.2 JFR + Java Mission Control: finding allocation call stacks

JFR records diagnostic data from the JVM with configuration-dependent overhead. For a running Java process, use the real PID:

~~~sh
jcmd <pid> JFR.start name=allocation-study settings=profile duration=60s filename=allocation.jfr
jfr summary allocation.jfr
jfr print --events jdk.ObjectAllocationSample allocation.jfr
~~~

The `jfr summary` and `jfr print` commands run **after** the recording has been written to a file. You can open the file in **Java Mission Control** to inspect allocation hot spots, object types, threads, stack traces, and correlations with GC/CPU. In a recording that is too short, there may not be enough useful samples.

The **jdk.ObjectAllocationSample** event is sampled and carries an estimated weight (*sample weight*); **do not sum event counts as if they were the total number of objects allocated**. TLAB and out-of-TLAB allocation events have different collection mechanisms/costs; check which events are actually enabled in the JFR file before analyzing. Do not use a single sampled stack to conclude the cause of an entire workload.

JFR also includes events supporting analysis of long-lived objects (such as Old Object Sample when configured appropriately), though that is **not** a complete record of every object's lifetime. Taking a heap dump / tracing GC roots is a technique to inspect retention when you have a specific suspicion, carrying significant pause cost and file size.

### 5.3 JMH: comparing the allocation cost of a small code snippet

For benchmarks built with JMH, the `-prof gc` option can display metrics such as `gc.alloc.rate` (MB/s) and `gc.alloc.rate.norm` (B/op), along with supported GC metrics. **B/op** is convenient for comparing two ways to handle the same unit of work; **MiB/s** reflects bytes over time and also depends on operations/second.

You must include warmup, sufficient iterations/forks, and proper result consumption. The JIT can eliminate allocations via escape analysis/scalar replacement or dead-code elimination; an overly simple benchmark may measure **code optimized by the JVM far differently from what the author envisioned**. JMH is a microbenchmarking tool, not a replacement for whole-system measurement under representative load.

### 5.4 What to read and not read from other tools

- `jcmd <pid> GC.class_histogram` or a heap dump helps identify which object types are present in the heap, **not allocation rate by call site directly**; some operations can cause pauses. Use deliberately, especially in production.
- `GarbageCollectorMXBean` provides collection counts/times per collector; cumulative counters require taking the difference between two timestamps, and do not prove the cause of allocation.
- Used heap, committed heap, max heap, and process RSS are different metrics. Off-heap/direct buffers, metaspace, stacks, and native allocations must not all be attributed to Java heap allocation.

## 6. Runnable Java 17+ example: short-lived vs. retained

The program creates two lifecycle patterns. In the first pass, a 1 KiB array is assigned through a `volatile` field and typically loses references quickly as new arrays replace it; in the second pass, 4,000 arrays are stored in a static list so they remain reachable. `System.gc()` is not called to force GC: when collection happens is up to the JVM.

Save the file **AllocationLifetimeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class AllocationLifetimeDemo {
    private static final List<byte[]> HELD = new ArrayList<>();
    private static volatile byte[] visible;

    private static void allocate(int count, boolean hold) {
        for (int i = 0; i < count; i++) {
            byte[] data = new byte[1_024];
            data[0] = (byte) i;
            visible = data; // Let the object escape; limit optimization elimination.
            if (hold) {
                HELD.add(data);
            }
        }
    }

    public static void main(String[] args) {
        allocate(100_000, false);
        System.out.println("after ephemeral: " + HELD.size());

        allocate(4_000, true);
        System.out.println("after retained: " + HELD.size());

        HELD.clear();
        visible = null;
        System.out.println("after release: " + HELD.size());
    }
}
~~~

Compile and run:

~~~sh
javac --release 17 AllocationLifetimeDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC AllocationLifetimeDemo
~~~

Stdout from the program (without GC logging enabled):

~~~text
after ephemeral: 0
after retained: 4000
after release: 0
~~~

**Accurate interpretation:** the first 100,000 arrays have a total *requested payload* of 102,400,000 bytes (about 97.7 MiB) plus object header/alignment overhead. They **do not coexist in the list**; the JVM can reuse the space of dead arrays. The 4,000 arrays in the second pass have a payload of roughly 3.9 MiB and stay reachable via `HELD` until `clear()`. The result `HELD.size() == 0` only shows that the list dropped its references: **it does not prove that GC just ran, that heap used decreased, or that process RSS was returned to the OS**.

The `visible` field is one way to give the array an escape path so allocations can be observed; this is an educational example, not a pattern to put into production application code. Specific GC figures will vary by JDK, heap, collector, runtime duration, and system. To capture JFR for this short program, you can start the recording right at startup:

~~~sh
java -Xms64m -Xmx64m -XX:+UseG1GC -XX:StartFlightRecording=settings=profile,filename=allocation.jfr,dumponexit=true AllocationLifetimeDemo
jfr summary allocation.jfr
~~~

In a very short run, JFR may still lack allocation samples; on a long-running service, record over a window with sufficiently representative workload. When `-Xlog:gc*` is enabled, stdout includes JVM log lines in addition to the three lines printed by the program.

## 7. Repeatable diagnostic workflow

1. **Establish the problem and SLO:** For example, GC CPU rose from 3% to 20%, request p99 crossed the threshold, or old occupancy is approaching the limit. Record the exact time range, JDK version, collector, `-Xms/-Xmx`, and container CPU/memory limits.
2. **Hold the comparison workload constant:** RPS, request/response size, cache warmup, error rate, data shape, concurrency, and run duration. Do not compare two profiles with different traffic while looking only at MiB/s.
3. **Measure three layers:** (a) allocation rate and top call stacks from JFR/JMH where appropriate; (b) pause frequency/duration and young/survivor/old from GC logs; (c) live set and post-GC occupancy graphs over time. Synchronize timestamps with CPU and latency.
4. **Form a concrete hypothesis:** "Each request creates multiple copies of `byte[]` because of double format conversion" or "Queue enqueue rate > processing rate so requests live longer." Predict which metric should change if the hypothesis is right.
5. **Change one cause at a time:** Remove redundant copies, bound the queue, fix cache eviction, improve streaming/batching... Then re-measure under the same workload type. Monitor allocation B/op, throughput, GC CPU, p99, and post-GC retained memory.
6. **Check trade-offs:** A technique that reduces object count while holding buffers longer can increase the live set or contention. Prioritize measured results and correctness, rather than optimizing just because an allocation chart went down.

## 8. Three data-reading scenarios

| Observation under equivalent load | First hypothesis | Evidence to check |
| --- | --- | --- |
| Allocation 300 MiB/s, frequent young GCs, stable post-GC heap, high GC CPU | Short-lived object churn | JFR allocation top stacks and B/op; compare p99 before/after reducing copies |
| Allocation 70 MiB/s, post-GC old occupancy rising steadily, queues/caches also growing | Data retained long-term or consumers unable to keep up | Heap histogram, GC root reference paths, queue/cache sizes and eviction policy |
| Allocation 15 MiB/s, post-GC live set near `-Xmx`, poor pauses | Live dataset is large relative to heap, possibly with fragmentation or unsuitable GC policy | Object histogram, whether live set is stable or rising, heap/headroom, actual collector logs |

The numbers above are illustrative scenarios, **not fixed thresholds** for diagnosing every JVM. "High allocation rate" is only meaningful alongside CPU budget, pause SLO, workload, and heap size.

## 9. Optimization directions by pressure source

**When churn causes high GC CPU:** Identify hot stacks first. Consider eliminating intermediate conversions/copies, avoiding boxing and temporary strings in hot loops, switching to streaming when the entire dataset need not be retained, or batching small operations that carry high wrapper overhead. Compare **B/op** and processing time; a cleaner-looking API chain does not by default allocate fewer objects. Do not implement an object pool for small objects purely on intuition: pools keep them alive longer, add synchronization, and can underperform the JVM's fast allocation path.

**When retention/promotion is high:** Audit reference scope; bound caches by size/TTL, unregister listeners at end of lifecycle, ensure queues have backpressure or bounds, finish batches and close resources promptly. Trimming long-lived references can be more effective than shaving a few bytes off temporary objects.

**When the live set is large yet legitimate:** Evaluate heap headroom, data structures (especially map/list overhead/padding), actual data-retention needs, partitioning/batching, and a collector suited to latency/throughput goals. Tune heap or collector only after establishing a baseline; increasing `-Xmx` can lower GC frequency but also changes footprint and pause characteristics. Do not solve a leak by continually raising the heap.

**When many large objects exist:** Inspect array/buffer copy paths, special allocation paths, batch size limits, and region/fragmentation pressure per collector. Do not equate native/direct memory allocations with Java heap allocation.

## 10. Common wrong conclusions

1. **"Heap rising before GC means a leak."** No: pre-GC heap can contain many dead objects; look after GC and inspect GC roots.
2. **"1 GiB/s allocation requires a heap larger than 1 GiB."** No: that is bytes/second throughput; reclamation speed and live set determine feasibility.
3. **"Fewer GCs is always better."** No: long pauses or a large live set can be worse than brief young GCs; look at overall SLOs.
4. **"Objects entering Old are a leak."** No: many structures are legitimately long-lived; promotion is just a management mechanism.
5. **"After `clear()`, OS memory must drop."** No: GC does not necessarily run immediately, and committed heap may still be held by the JVM.
6. **"One JFR allocation event equals one real allocation."** No: sampling, event configuration, weight, and stack context determine interpretation.
7. **"Reducing `new` calls in source definitely reduces allocated bytes."** No: JIT optimizations can eliminate allocations; conversely, an object pool holding bytes longer can increase GC pressure.
8. **"GC pauses cause every slow request."** No: timestamps must be correlated with CPU, I/O, lock contention, network, and queuing time.

## 11. Self-check reasoning exercises

**Problem A.** If threads actually allocate 120 MiB/s and the assumed usable young capacity is 240 MiB, what is the simple fill interval? **Answer:** about 2 seconds. This is not a guaranteed GC schedule because young size and survival vary.

**Problem B.** Two builds both run at 100 MiB/s. Build 1 has a stable post-GC live set of 300 MiB; Build 2 climbs from 300 to 800 MiB over several minutes at the same load. Which build needs retention investigation first? **Answer:** Build 2. Check caches/queues/reference chains rather than immediately asserting a leak.

**Problem C.** You reduced allocation from 200 to 90 B/op, yet p99 rose and old occupancy increased. Was the optimization successful? **Answer:** cannot conclude so. You may have traded short-lived allocations for longer buffer retention, higher contention, or another cost; evaluate throughput, p99, GC CPU, and live set together.

## Key takeaways to apply

- **Allocation rate** answers "how many bytes per second does the program create?"; **live set** answers "how many bytes still need to be kept?"; **lifetime/survival** links those two quantities to GC cost.
- **High churn** and **high retention** call for different strategies. Read GC logs to learn *when/collection cost*; use JFR/JMC to learn *who allocates*; use reference analysis when suspecting *who retains*.
- A good change is verified by representative workload and application goals, not merely by reducing `new` calls or GC counts.

### References

- Oracle, *Java 21 GC Tuning Guide*: https://docs.oracle.com/en/java/javase/21/gctuning/
- Oracle, *Java 21 Diagnostic Tools* (JFR, `jcmd`, heap histogram): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle, *The jcmd Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Dev.java, *Configuring the JDK Flight Recorder*: https://dev.java/learn/jvm/jfr/configure/

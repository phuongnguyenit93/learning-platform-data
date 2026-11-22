# Parallel GC: Throughput-Oriented Parallel Collection in HotSpot JVM

**Parallel GC**, also known as the **throughput collector**, is a **generational** garbage collector in HotSpot, optimized so that the program spends more time executing application work and less time on GC. The difference from Serial GC is that **multiple GC worker threads perform collection work together**, utilizing multiple CPU cores; the difference from low-latency collectors like G1/ZGC is that Parallel GC prioritizes **overall throughput** over limiting individual pauses to be short.

In this article, "parallel" does **not** mean GC always runs concurrently with the application. The main collection phases of Parallel GC are **stop-the-world (STW)**: application threads (mutators) must pause, and **multiple GC worker threads** handle the same pause. This is the easiest place to get confused:

> **Parallelism of GC workers** helps reduce the wall-clock time of certain GC work using multiple CPUs. **Concurrency with application threads** is a different characteristic and is not the meaning of the name Parallel GC.

With **HotSpot Java 17**, select this collector using `-XX:+UseParallelGC`. The collector allows the JVM to balance three goals itself: **pause-time goal**, **throughput goal**, and **heap footprint**, in the priority order specified by the ergonomics mechanism. Learners will explore young/old collections, copying/compaction, adaptive sizing, configuration flags, GC logging, and a **runnable Java 17+ example** to generate allocation pressure while having stable stdout.

## 1. "Parallel", "concurrent", and "throughput" are three different terms

| Term | Meaning | Example in GC |
| --- | --- | --- |
| **Parallel work** | Multiple worker threads process GC work at the same time | Parallel GC divides tracing/copying/compacting work among multiple GC threads |
| **Concurrent work** | Part of GC work takes place while application threads are still running | G1 concurrent marking, ZGC concurrent phases |
| **Stop-the-world** | Mutator/application threads pause so GC can perform necessary work | Main young and old collections of Parallel GC |
| **Throughput** | The ratio of time the JVM spends on application work to total measured application + GC time | 99% application time is a ratio goal, not an SLA for each pause |
| **Pause time** | The duration the application pauses due to GC in an event | A 300 ms STW GC can affect request latency |
| **Footprint** | The heap capacity that the program/JVM uses or maintains | Reducing heap can save memory but increases GC frequency |

### 1.1. Diagram of a parallel but STW GC cycle

```text
Time ─────────────────────────────────────────────────────────►

Application threads:
  Thread A: █████████████ │ PAUSED     │ ███████████████████
  Thread B: █████████████ │ PAUSED     │ ███████████████████
  Thread C: █████████████ │ PAUSED     │ ███████████████████

Parallel GC worker threads during the pause:
  GC W1:                │ mark/copy A │
  GC W2:                │ mark/copy B │
  GC W3:                │ mark/copy C │
  GC W4:                │ compact/... │

                        ↑ STW starts  ↑     ↑ STW ends
```

During the pause, **collection work can run in parallel**, while application threads have no opportunity to advance business code in the normal way. Thanks to that, Parallel GC can process the heap quickly on multi-core machines; however, long pauses can still cause users to experience request timeouts or frame drops.

Do not state that "Parallel GC has no concurrency in any JVM thread" in an absolute sense: the JVM also has compiler/service threads and its own implementation activities. What matters is that **Parallel GC does not design main heap collection around low-pause concurrency with mutators like concurrent collectors do**.

### 1.2. Reducing GC wall time is different from reducing GC CPU work

If a scanning task has an amount of work W, increasing the number of workers can reduce the **wall-clock time** of the pause by dividing the work; total **CPU work** does not necessarily decrease, and there is even additional scheduling/synchronization overhead. Therefore:

- 8 GC workers do not guarantee a pause is exactly 8 times faster than 1 worker.
- A small heap or small live set may not have enough work to parallelize effectively.
- Container CPU quotas, NUMA, memory bandwidth, cache contention, and GC synchronization affect speedup.
- Too many workers can consume system CPU and worsen a workload that is contending for resources.

Parallelism is a tool to improve throughput on suitable hardware, **not a linear speedup factor guaranteed by the JVM**.

## 2. Parallel GC is a generational collector

Parallel GC manages the Java heap into a **young generation** and an **old generation**. In common HotSpot implementations:

- Young consists of **Eden**, Survivor From/To; most new allocations are placed in Eden via mechanisms such as TLAB.
- Young collection typically uses a **copying/evacuation** algorithm: unreachable objects are not copied, while live objects are moved to survivor or promoted to old.
- Old contains objects that remain live long enough or are allocated/promoted according to collector policy.
- Old collection needs to identify live objects and can **compact** to reduce fragmentation and recreate allocation space.

```text
                       YOUNG
                     ┌──────────┐
new objects ────────►│  EDEN    │
                     └────┬─────┘
                          │ Young GC (Parallel Scavenge)
                    ┌─────┴──────┐
                    │            │
                garbage       live objects
                    │            │
                 reclaim         ▼
                           SURVIVOR (age++)
                                │
                        next young GC
                                │
               threshold / survivor capacity / policy
                                ▼
                         OLD GENERATION
                                │
                         Old collection:
                         Parallel Old compacting
                                │
                         reclaim unreachable
```

**GC age is not the number of seconds of an object's lifetime**. It typically represents the number of times an object has survived young copying according to the collector. The threshold is not necessarily fixed throughout execution, as it is adjusted by the adaptive policy.

### 2.1. Minor/Young GC: Parallel Scavenge

In HotSpot documentation, the young collector part is often called **Parallel Scavenge**. When the young region needs collection:

1. The JVM reaches a safepoint to perform the STW collection.
2. Multiple GC workers take portions of the liveness discovery/object copying work.
3. GC identifies live objects from the root set and references relevant to young.
4. Objects that are no longer reachable do not need to be copied.
5. Live objects are copied to the appropriate survivor space or promoted to old according to policy.
6. GC can reuse most of the source Eden after evacuation and reference updates.

Because the work for young runs in parallel, multiple cores can help shorten the pause compared to a single worker, **but the entire pause still needs to be measured**. For a large young live set, copying/promotion cost can be high.

### 2.2. Old GC: Parallel Old, parallel compaction

In HotSpot Java 17, selecting `-XX:+UseParallelGC` normally also enables **parallel compaction** of the old generation (Parallel Old). This is important: Parallel GC does not only parallelize minor collections.

Old compaction can include:

- Identifying the set of live objects and references that need updating.
- Planning the destination locations of objects after compaction.
- Moving/copying live objects in appropriate phases.
- Updating object references to match the new addresses.
- Recreating useful free space for subsequent allocations.

The specific phase breakdown is a **HotSpot implementation detail**, not a public Java interface. What to remember: **parallel old collection is also mainly STW**, and can often pause for a long time when the old live set is large.

Oracle Java 17 documentation states that parallel compaction **is enabled by default when `UseParallelGC` is selected**, and can be disabled with `-XX:-UseParallelOldGC`. Disabling it does not mean "not collecting Old"; it changes the mechanism for performing major/old collections, which can cause a regression in scalability, so it is not an option recommended for arbitrary use.

### 2.3. Survivor space and promotion pressure

A young object that survives a Young GC usually goes from Eden to survivor or old. If survivor capacity is insufficient or the object reaches the tenuring threshold, it can be promoted.

```text
Eden:
   A live; B dead; C live; D dead

Young collection:
   B, D → garbage, no need to copy
   A, C → Survivor or Old

Survivor → stays when age/policy is suitable
Survivor → Old if promotion is necessary

Old:
   still collected by GC when objects are no longer reachable;
   not a "permanent" region.
```

An application that holds a lot of temporary data across many GC cycles can create **premature promotion** and increase old occupancy. This can be a retention burst, not necessarily a leak. When investigating, look at survival rate, bytes promoted, old occupancy, and heap dumps rather than concluding solely from the number of collections.

### 2.4. Do not assume every `new` creates an object in Eden

There are special allocation paths and JIT optimizations:

- Some allocations of different sizes or conditions may be handled by a slow path/old generation depending on collector policy.
- Escape analysis/JIT can avoid heap object allocation if the optimization is valid.
- TLAB is for fast allocations, not a "third generation" of the heap.

The Eden→Survivor→Old model is for understanding the main mechanism, not an address contract for every instance on every JVM.

## 3. Why does Parallel GC aim for throughput?

**Throughput** in GC ergonomics is typically measured as the ratio between application processing time and total application plus GC time over an appropriate measurement interval:

```text
throughput = application_time / (application_time + gc_time)

GC_time_fraction = gc_time / (application_time + gc_time)

If application_time = 9.9 s and gc_time = 0.1 s:
  throughput ≈ 99%
  GC fraction ≈ 1%
```

This is a **time-ratio model**, not a direct measurement of machine CPU utilization, requests/second, or bytes allocated. An application with high time throughput can still have low requests/second because business code is slow.

### 3.1. What goal does `GCTimeRatio` represent?

HotSpot supports:

```bash
-XX:GCTimeRatio=N
```

The goal is an approximate **GC time fraction**:

```text
gc_time_fraction = 1 / (1 + N)
application_time_fraction = N / (1 + N)

N = 99 → GC goal = 1/100 = 1%
         application goal ≈ 99%

N = 19 → GC goal = 1/20 = 5%
         application goal ≈ 95%

N = 9  → GC goal = 1/10 = 10%
         application goal ≈ 90%
```

According to **Java 17 HotSpot Parallel Collector Ergonomics** documentation, the default value is **`GCTimeRatio=99`**, meaning a goal of spending about 1% of total time on GC.

**You must distinguish a goal from a measurement**: setting `-XX:GCTimeRatio=99` does not guarantee every workload will spend exactly 1% of time on GC. If the heap is too small, allocation is too fast, or the live set is large, the collector may not meet the goal. The JVM adjusts based on statistics/heuristics and heap/throughput limits.

### 3.2. High throughput can come with long pauses

Consider a batch job that completes in 10 minutes with only 2 GC pauses of 800 ms. The application time ratio can be very high, fitting the **batch throughput** goal. However, if the same JVM serves an endpoint requiring p99 latency under 100 ms, those 800 ms pauses can severely violate the SLA.

Therefore, choosing Parallel GC is reasonable when:

- Total tasks completed per hour/minute is more important than peak latency.
- Relatively long pauses are **acceptable** according to service requirements.
- The machine has multiple processors/cores and the live set/heap is large enough for parallel GC work to be useful.
- The workload is batch, ETL, data processing, or CPU-intensive where throughput is the priority.

Do not rely solely on the name "Parallel" and choose it for every multithreaded application; realtime/interactive applications may need a collector specialized for low latency.

## 4. Adaptive tuning: pause, throughput, and footprint

HotSpot Parallel GC has **ergonomics/adaptive sizing policy**: instead of forcing users to fix every generation/space size, the VM measures collection behavior and adjusts young/old sizing and related parameters to move closer to the goals.

**Goal priority order** in the Parallel Collector Ergonomics documentation:

1. **Maximum pause time goal** if configured.
2. **Throughput goal**.
3. **Minimum heap footprint**, provided it does not break the two goals above.

This matters because the first two goals can conflict. Trying to reduce individual pauses may require more frequent collections and increase total GC time; a large young generation can increase throughput due to fewer collections, but each pause is longer.

### 4.1. `MaxGCPauseMillis` is a goal, not a deadline

```bash
-XX:MaxGCPauseMillis=200
```

The number 200 ms is a **hint/goal**, not a contract that the JVM must cut GC pauses to exactly 200 ms. The adaptive policy can reduce the size of relevant regions to reduce the amount of work per collection, but it may still fail to meet it if live data is very large or other conditions are unfavorable.

According to Java 17 docs, **by default there is no maximum pause-time goal** set for Parallel GC. If a goal is too strict, the JVM may reduce throughput because it needs to run GC more often.

### 4.2. `UseAdaptiveSizePolicy`

`-XX:+UseAdaptiveSizePolicy` allows the VM to automatically adapt generation sizes and related parameters; on HotSpot releases corresponding to Java 17, adaptive sizing is enabled by default with Parallel GC.

```bash
-XX:+UseParallelGC -XX:+UseAdaptiveSizePolicy
```

It can be disabled with `-XX:-UseAdaptiveSizePolicy` to experiment with manual configuration, but you need to understand `-Xmn`, `NewRatio`, `SurvivorRatio`, `MaxTenuringThreshold`, and their interactions. **Do not start tuning by disabling the adaptive policy** without measurements proving it hinders workload goals.

### 4.3. `Xms` and `Xmx`: heap budget

```bash
-Xms512m -Xmx2g
```

- `-Xms` sets the initial heap size at runtime.
- `-Xmx` is the maximum heap size; the collector cannot exceed this limit on its own.
- A large heap can reduce GC frequency when the workload allows, but footprint increases and it can change GC pauses.
- If the Java heap live set is close to `Xmx`, even adaptive sizing has difficulty creating free space. `OutOfMemoryError` or many collections reclaiming very little may occur.

**Increasing `-Xmx` does not fix every memory issue**: native thread stack, direct memory, metaspace, and native library memory are still separate categories.

### 4.4. `ParallelGCThreads`

`-XX:ParallelGCThreads=N` controls the number of GC worker threads used for the parts of GC executed in parallel as supported by HotSpot. For example:

```bash
-XX:ParallelGCThreads=4
```

Do not infer that the program only has 4 threads total, or that GC runs concurrently with 4 application threads. This configures **GC workers**, not `Executors.newFixedThreadPool(4)`.

The appropriate number of workers depends on actually usable CPU cores, container quotas, heap/live-set size, and contention. Forcing the value too high can increase overhead and fail to achieve expected pause/throughput.

### 4.5. Summary of commonly seen options

| HotSpot Java 17 Option | Purpose | Pitfalls to avoid |
| --- | --- | --- |
| `-XX:+UseParallelGC` | Select Parallel / throughput collector | Does not make GC concurrent low-latency |
| `-XX:ParallelGCThreads=N` | Set number of worker threads for parallel GC work | Not the total number of JVM threads |
| `-XX:GCTimeRatio=N` | GC time goal = 1/(N+1) | Does not guarantee exact measured ratio |
| `-XX:MaxGCPauseMillis=N` | Hint for maximum pause time | Not a hard deadline |
| `-XX:+UseAdaptiveSizePolicy` | Adaptive generation sizing | Can be constrained by heap bounds/other flags |
| `-Xms / -Xmx` | Initial/max Java heap size | Does not include all native memory |
| `-XX:MaxTenuringThreshold=N` | Survivor age limit before promotion per policy | Does not promise every object stays in survivor N times |
| `-XX:-UseParallelOldGC` | Disable parallel old compaction when using ParallelGC | Can make major collections scale poorly |
| `-XX:+UseGCOverheadLimit` | Check GC overhead leading to OOME when too little progress is made | Not a perfect memory-leak detector |
| `-Xlog:gc*` | Unified logging for GC | Does not promise identical logs across JDKs/runtimes |

The flags discussed here are within the scope of **HotSpot JDK 17**, not Java Language Specification keywords required to be supported by every JVM vendor.

## 5. Differences between Parallel GC and Serial/G1/ZGC

| Collector (HotSpot Java 17) | Orientation | General collection style | When to try |
| --- | --- | --- | --- |
| **Serial GC** | Simple, small overhead on small environments | Primarily one GC worker, STW | Small heap, few CPUs, simple programs |
| **Parallel GC** | **Throughput**, utilizes multiple cores | STW phases with **multiple GC workers**, generational | Batch/throughput-oriented, long pauses acceptable |
| **G1 GC** | Balances throughput and pause predictability | Region-based, evacuation pauses + concurrent marking | Large server heaps, aiming for lower and more consistent pauses |
| **ZGC** (JDK 17) | Very low latency | Concurrent phases, very short STW pauses | Low latency requirements, accepting CPU/throughput trade-offs |

**This is an orientation comparison, not an absolute ranking.** In a specific workload, G1 can have higher throughput than Parallel GC or vice versa. Heap size, live-set shape, hardware, thread count, and latency SLA determine the right choice.

### 5.1. Default collector in Java 17

On most common server configurations, **G1 is the default collector** in HotSpot Java 17. Therefore, if you want to experiment specifically with Parallel GC, **explicitly specify `-XX:+UseParallelGC`** and verify from the startup GC log.

Do not teach that "Parallel GC is always the default on servers" just because some Java 8 documentation says so; the default collector has changed across JDK releases and also depends on VM configuration.

### 5.2. Parallel is not Parallel Streams

`java.util.stream.Stream.parallel()`, `ForkJoinPool`, and `Executors` relate to **parallelizing application work**. `-XX:+UseParallelGC` relates to **parallelizing garbage collection work**.

The two features do not require each other. A Java program with only a main thread can still run Parallel GC, while an application with many platform threads is not required to use Parallel GC.

### 5.3. Is "G1 also has parallel GC worker threads" a contradiction?

No. "Parallel GC" is the name of a **specific collector** in HotSpot, while other collectors can also use multiple GC workers during their phases. The difference lies in the **architecture of the entire collection algorithm and the latency/throughput goals**, not just the question "does GC use 1 or many threads".

## 6. An illustrative Young GC cycle

Suppose we have:

- Eden contains 160 MB of allocations, mostly temporary objects.
- Survivor before collection contains 20 MB of live candidates.
- The young survival rate in this round is low.
- Old has enough headroom to accept promotions if needed.

The numbers below are **conceptual examples only**:

```text
Before Young GC:
  Eden:       160 MB
  Survivor:    20 MB
  Old:        400 MB

Stop-the-world Young GC, multiple workers:
  1. Identify live objects in young
  2. Do not copy unreachable objects
  3. Copy young survivors to survivor destination
  4. Promote needed objects to old
  5. Reuse/reclaim young source spaces

After GC (a hypothetical scenario):
  Eden:         0 MB used by old allocations
  Survivor:    25 MB live
  Old:        410 MB used

Reclaimed a significant amount of temporary data.
```

You cannot simply take `160 + 20 - 25 - 10` and conclude that total **process RSS** decreased by that exact value. GC may keep the heap committed, and there are headers/alignment, survivor sizing, promotions, and other VM native memory. In addition, before/after figures for heap pools may represent capacity/used according to tool definitions.

### 6.1. Do old collections usually pause longer than young collections?

Often they can because old contains more live objects and broader marking/compaction work, but **there is no law that "every Full GC is longer than every Young GC"**. Pause duration depends on live data volume, heap fragmentation, hardware, GC worker efficiency, and trigger. Evaluate using actual logs.

### 6.2. GC generations are not the entire heap and metaspace

The Java heap contains Eden/Survivor/Old according to generational collectors. **Metaspace** in HotSpot is the area managing class metadata located outside the Java heap by implementation. An `OutOfMemoryError: Metaspace` cannot be fixed simply by choosing more ParallelGCThreads.

## 7. A compilable/runnable Java 17 example to test Parallel GC

Create the file **`ParallelGcDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ParallelGcDemo {
    // Keep a portion of data to simulate long-lived objects.
    private static volatile List<byte[]> keepAlive;

    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();
        long checksum = 0L;

        for (int i = 0; i < 100_000; i++) {
            byte[] block = new byte[2048];
            block[0] = (byte) (i & 127);
            checksum += block[0] & 0xff;

            if (i % 5000 == 0) {
                retained.add(block);
            }
        }

        keepAlive = retained;

        System.out.println("processed=100000");
        System.out.println("retained=" + retained.size());
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("done");
    }
}
```

Compile with JDK 17:

```bash
javac --release 17 ParallelGcDemo.java
```

Run with HotSpot Parallel GC, with a relatively small heap to have a chance of seeing Young GC:

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m ParallelGcDemo
```

**Stdout of the Java program itself (without GC logging enabled):**

```text
processed=100000
retained=20
checksumPositive=true
done
```

**Output explanation:**

- `processed=100000` because the loop executes exactly 100,000 iterations.
- The condition `i % 5000 == 0` is true at `0, 5000, ..., 95000` → **20** arrays are added to `retained`.
- `checksumPositive=true` because there are many positive `block[0] & 0xff` values.
- `keepAlive` keeps the list and the retained arrays reachable until the program ends.
- Other arrays can become garbage early; **GC count, pause durations, age, and promotion of each array do not have a fixed stdout**. The Java API does not expose the generation of an individual object.

**Do not claim** there are exactly 3 Young GCs just because the source creates 100,000 arrays. Depending on JIT, TLAB, heap sizing, and GC ergonomics, the observed allocations/timing may differ.

### 7.1. An example without intentional `System.gc()`

The program does not call `System.gc()` because that is a **suggestion to the JVM to perform GC**, not a deterministic GC scheduling tool. The goal is to create a workload with **fixed business results**, then use **independent GC logging** to observe actual runtime behavior.

In real applications, calling `System.gc()` repeatedly can distort the throughput/pause picture and make benchmarks unrepresentative. If you need to evaluate a collector, let the workload run long enough or use a controlled load generator.

## 8. Observing the collector and GC phases with Unified Logging

### 8.1. Confirming Parallel GC is selected

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m -Xlog:gc=info ParallelGcDemo
```

On HotSpot Java 17, the startup log usually has an indicator like `Using Parallel` or related GC information. Exact wording, timestamps, GC ids, and event counts can vary between JVM builds; **do not present a fabricated log as exact stdout**.

When `-Xlog` is enabled, the command prints **additional GC logs** alongside the program's `processed=...` lines. If you need to separate logs from business output, you can configure logging to a file.

### 8.2. Viewing heap, young/old, and age table

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+heap=debug,gc+age=trace \
  ParallelGcDemo
```

In an appropriate log you can observe:

- GC events and GC causes.
- Young/old heap information before and after collection.
- Capacity/used statistics by Parallel collector spaces.
- Age table/survivor analysis and tenuring threshold when supported by log level/tags.
- Wall-clock pause durations.

This is POSIX-style shell syntax; on Windows PowerShell, write it on a single line or use PowerShell-compliant line continuation.

### 8.3. Writing logs to a file

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+heap=debug,gc+age=trace:file=parallel-gc.log:time,uptime,level,tags \
  ParallelGcDemo
```

The file `parallel-gc.log` contains runtime data; volume can be high if trace level is chosen. In production, consider disk capacity, log rotation, security, and overhead.

### 8.4. Sample log for reading practice — not real output

```text
[info][gc] Using Parallel
[info][gc] GC(0) Pause Young (Allocation Failure) ...ms
[info][gc] GC(1) Pause Full (Ergonomics) ...ms
```

This is an **illustrative diagram of log types**; actual causes/event types may differ. Do not infer that `Allocation Failure` means Java `new` threw an OutOfMemoryError: the collector can restore allocation capability after a Young GC, and the application continues running successfully.

GC logs are actual evidence; **an example line cannot serve as evidence for your run**.

## 9. Calculating throughput and pause from logs: a thought exercise

Suppose in a 100-second measurement window:

- The application performs work for 97 seconds.
- Total STW GC pauses are 3 seconds.

```text
application_time = 97 s
gc_time          =  3 s

throughput = 97 / (97 + 3) = 97%
GC fraction = 3 / 100 = 3%
```

If `GCTimeRatio=99` (1% GC fraction goal), a measured result of 3% means the collector did not meet the goal in that observation window. It **does not automatically identify the cause**: too small a heap, large live set, too many allocations, insufficient CPU, or how the measurement window was chosen all require further analysis.

### 9.1. Throughput does not yet reflect p99 latency

Suppose the same 3 seconds of GC is divided into:

- 300 pauses × 10 ms, or
- 3 pauses × 1000 ms.

Total pause time is 3 seconds in both cases, so throughput by the simple formula is the same. However, **tail latency** is vastly different; a service with a 100 ms SLA can fail with 1-second pauses.

That explains why Parallel GC can suit batch processing but be poorly suited for interactive services needing very low pauses. You need to compare **throughput and pause percentiles** together.

### 9.2. Pause time is not application CPU time

A 100 ms GC pause with 8 GC worker threads can consume more than 100 ms of total CPU time across all workers; the throughput ratio stated in the documentation is a **wall-time behavior concept**, not simply taking total CPU% per thread divided by some factor.

## 10. `GC overhead limit exceeded` and failure modes

HotSpot Java 17 has the `-XX:+UseGCOverheadLimit` policy (enabled by default in appropriate configurations). When most of the time is spent in GC but too little heap is reclaimed according to the policy threshold, the JVM can throw:

```text
java.lang.OutOfMemoryError: GC overhead limit exceeded
```

Java 17 option documentation describes the situation where parallel GC **spends more than about 98% of time on GC and reclaims less than about 2% of the heap**. This is a **guard against an application making virtually no progress**, not a new type of GC.

Causes to investigate:

- **Strong live set** close to `Xmx`.
- Caches/lists/queues holding references longer than expected.
- High allocation rate combined with many live objects.
- Heap configured too small for the workload.
- Object retention leaks, static maps, listeners, ThreadLocals, or native bridges holding Java objects.

**Do not treat it by merely setting `-XX:-UseGCOverheadLimit`** and assuming the problem disappears; that can cause the application to keep burning GC CPU with no progress, and then OOME via another mechanism.

### 10.1. Distinguishing OOME, Young GC, and promotion failure

- **Young GC** is normal operation; not an exception.
- **Promotion pressure** increases old occupancy, which can lead to heavier GC if headroom is lacking.
- **OutOfMemoryError: Java heap space** appears when the JVM cannot allocate a heap object under the corresponding conditions.
- **GC overhead limit exceeded** is a policy-based OOME when most time is "eaten" by GC while too little memory is reclaimed.
- **OutOfMemoryError: unable to create native thread** relates to thread/native memory resources, and cannot be inferred directly from Eden.
- **OutOfMemoryError: Metaspace** is not a message that the old Java heap is full.

Specific messages are implementation details and must be based on actual logs/stack traces. Do not blame every OOME on a Parallel GC "bug".

## 11. Why are more GC workers sometimes slower?

Parallel GC operates on a shared heap and must coordinate multiple threads during an STW pause. Factors that can reduce effectiveness:

- **Memory bandwidth:** multiple workers scanning/copying live objects simultaneously can saturate the memory subsystem.
- **Synchronization/task distribution:** creating/splitting work, load balancing, and rendezvous have overhead.
- **CPU contention:** the machine/container only provides a few physical cores, and many worker threads contend for CPU.
- **Small heap/live set:** the amount of GC work is small, and worker management cost outweighs the benefit.
- **NUMA effects:** accessing memory on a remote node has higher latency; placement matters.
- **Cgroup/resource limits:** the JVM seeing processor quotas can change worker decisions, sizing, and throughput.

There is no "ideal GC workers = cores × 2" for every machine. The right approach is to measure the workload under real CPU/memory quotas, use `ParallelGCThreads` as an isolated experiment, and compare GC wall time, CPU, throughput, and p99 latency.

## 12. Experimental configurations worth trying

### 12.1. Baseline: JVM chooses GC automatically

```bash
java -Xms512m -Xmx512m MyApp
```

Record the collector actually chosen, JVM vendor/version, and log/event metrics. On HotSpot Java 17 server it is usually G1; treat that only as an experimental baseline.

### 12.2. Comparing Parallel GC

```bash
java -XX:+UseParallelGC -Xms512m -Xmx512m \
  -Xlog:gc*:file=parallel.log:time,uptime,level,tags \
  MyApp
```

Keep the workload/heap sizing identical, and measure requests/s, total runtime, p99 pause, total GC time, process CPU, and memory. For a batch job, measuring **total completion time** is often more meaningful than a GC count figure.

### 12.3. Trying throughput goal, then pause goal

```bash
java -XX:+UseParallelGC -Xms512m -Xmx512m \
  -XX:GCTimeRatio=19 -Xlog:gc*=info MyApp

java -XX:+UseParallelGC -Xms512m -Xmx512m \
  -XX:MaxGCPauseMillis=200 -Xlog:gc*=info MyApp
```

These are **two different experimental configurations**; do not attribute the difference to a single flag if input/CPU load differs. `GCTimeRatio=19` allows a goal of up to about 5% GC time; `MaxGCPauseMillis=200` tries to steer pauses toward 200 ms. They are *goals*, not guarantees.

### 12.4. Testing worker count with real metrics

```bash
java -XX:+UseParallelGC -XX:ParallelGCThreads=4 \
  -Xms512m -Xmx512m -Xlog:gc*=info MyApp
```

Compare against the previous baseline on the same hardware, same heap, and same workload. If pauses decrease but application throughput worsens due to CPU contention, you need to decide based on the business SLA.

Commands using `MyApp` are **templates only**, not a Java class provided by this article. To run a complete lab yourself, replace it with `ParallelGcDemo` in section 7.

## 13. A fair comparison methodology against G1

When deciding whether to choose Parallel GC over G1:

1. **Define SLA:** batch jobs/s, time-to-completion, p95/p99 service latency, maximum acceptable pause.
2. **Fix the environment:** JDK build/vendor, CPU quota, container limits, `-Xms/-Xmx`, dataset, traffic pattern.
3. **Warm up:** let JIT/class loading stabilize relatively before taking long-term samples.
4. **Track peak and steady state:** GC behavior during bootstrap and after warmup can differ.
5. **Use consistent tooling:** GC logs at the same verbosity level, JFR/metrics, throughput counters, and heap usage.
6. **Look at both average and tail latency:** high throughput cannot compensate for p99 SLA violations if the application has strict requirements.
7. **Test one group of flags at a time:** avoid changing collector, heap size, CPU threads, and timeouts in the same experiment and drawing wrong causal conclusions.
8. **Run multiple times:** results depend on OS scheduling, CPU cache, thermal behavior, JVM warmup, and GC timing.
9. **Monitor OOME/GC overhead limit:** a collector that is faster in the first 5 minutes is not necessarily stable when caches grow over many hours.
10. **Decide on real data:** Oracle recommends letting the JVM choose the GC automatically if there are no strict constraints; switch collectors when there is evidence of a problem.

### 13.1. Metrics to read together

| Metric | Question answered | Conclusion to avoid |
| --- | --- | --- |
| GC pause duration | How long is the application stopped each time? | Not synonymous with total application throughput |
| Total GC wall time | How much did the JVM stop for GC in the measurement window? | Does not directly reflect worker CPU |
| Allocation rate | How many new bytes per second does the application generate? | Not synonymous with live heap |
| Young survival/promotion | How many bytes survive young collection and enter old? | Does not by itself prove a memory leak |
| Old occupancy trend | Does live/used old growth hit a plateau? | Temporary growth is not necessarily a leak |
| Heap footprint/RSS | How much memory does the JVM use? | RSS includes native memory |
| Requests/sec/jobs/sec | How much work does the application get done? | Does not tell you p99 |
| p95/p99 latency | Do the slowest requests exceed the SLA? | Not necessarily proportional to GC time |

**Read GC logs by event type/cause/time window**, do not stitch together unrelated events to produce fake "before/after" figures.

## 14. Common misconceptions about Parallel GC

1. **"Parallel GC is a concurrent GC."** False. It is mainly STW, but uses multiple GC workers in parallel.
2. **"With 8 GC workers, GC is 8 times faster."** False. Bandwidth, scheduling, GC live-set, and synchronization limit scaling.
3. **"Parallel GC has no Old collection."** False. Parallel Old supports parallel old compaction by default with `UseParallelGC`.
4. **"Young GC and Full GC are the same."** False. Young only processes young, whereas Full has a broader scope/cost.
5. **"The name Parallel means the application runs in parallel with GC."** False. Parallel here means **among GC workers**.
6. **"ParallelGCThreads is the number of application threads."** False. It is the number of GC workers.
7. **"Parallel GC guarantees no pause over 200 ms when setting `MaxGCPauseMillis=200`."** False, it is only a goal.
8. **"`GCTimeRatio=19` means GC must use 19% of the time."** False. It corresponds to a goal of **1/20 = 5%**.
9. **"`GCTimeRatio=99` guarantees GC takes exactly 1%."** False. This is a default goal, not a measurement.
10. **"Java 17 HotSpot always defaults to Parallel GC."** False on common server configurations; G1 is usually the default.
11. **"Old generation contains objects that never die."** False. Old is still collected.
12. **"Every new object always lands in Eden and goes through two Survivor spaces."** Not an invariant; JIT and policies have exceptions.
13. **"Increasing `-Xmx` fixes every OOME."** False. Native threads/metaspace/direct memory have their own constraints.
14. **"GC overhead limit exceeded is a type of leak conclusively diagnosed by the JVM."** False. It is a policy warning about lack of progress under GC/heap pressure conditions.
15. **"Simply reducing the number of GC events will increase throughput."** Not always true; pauses can become longer.
16. **"Calling `System.gc()` often helps benchmark the collector accurately."** False. It causes interference and does not guarantee GC scheduling.
17. **"Two JVMs with the same source must have line-for-line identical GC logs."** False. Scheduling, heap sizing, JIT, and hardware affect them.
18. **"Parallel GC is always faster than G1."** False. It depends on the workload and measurement criteria.
19. **"G1 has no parallel workers because its name is G1."** False. G1 also parallelizes some phases, while concurrency/architecture differ.
20. **"Heap and old generation include all of Metaspace."** False. Metaspace is managed outside the Java heap in HotSpot.
21. **"A Young GC is an `OutOfMemoryError`."** False. An allocation-related pause usually reclaims memory so the application can continue.
22. **"If survivor is full, the program must crash."** False. The collector can promote, perform additional operations, or report an error when actually out of memory.
23. **"Adaptive sizing keeps young/old sizes fixed."** False. It can adjust them according to pause/throughput/footprint goals.
24. **"In Java 17, `UseParallelOldGC` is disabled by default when Parallel is selected."** False according to Oracle docs: parallel compaction is enabled with `UseParallelGC`.
25. **"Enabling GC logs changes the Java API semantics of `String` or `List`."** No. Logging has overhead but must not alter application contracts.

## 15. Self-check questions (with answers)

**Question 1.** Why is Parallel GC still called stop-the-world when it uses multiple threads?

**Answer:** Because mutator/application threads are paused during collection; the multiple threads running simultaneously are **GC worker threads**, not the application running concurrently with GC.

**Question 2.** Does `-XX:+UseParallelGC` support parallel Old collection?

**Answer:** Yes. On HotSpot Java 17, parallel old compaction is typically enabled by default with `UseParallelGC`, and can be disabled with `-XX:-UseParallelOldGC`.

**Question 3.** With `GCTimeRatio=19`, what percentage is the GC time goal?

**Answer:** `1/(1+19)=1/20=5%`.

**Question 4.** With `GCTimeRatio=99`, what is the application throughput goal?

**Answer:** About `99/100=99%` application time, i.e., a 1% GC fraction goal, **not guaranteed in practice**.

**Question 5.** Does `MaxGCPauseMillis=100` forbid the JVM from pausing for 150 ms?

**Answer:** No. It is a goal/hint for adaptive sizing, not a hard deadline.

**Question 6.** What happens to an object in Eden that is still reachable during a Young GC?

**Answer:** The collector keeps the object by copying/evacuating it to survivor or old according to policy, not reclaiming it just because it is in Eden.

**Question 7.** Can an old object that is no longer reachable be reclaimed by Parallel GC?

**Answer:** Yes. Old collections identify live objects and reclaim/compact according to the Parallel Old mechanism.

**Question 8.** Why do more GC workers sometimes not increase throughput?

**Answer:** Because CPU/memory bandwidth has limits, synchronization and task scheduling overhead increases, or the workload is too small to parallelize usefully.

**Question 9.** Does running `ParallelGcDemo` with `-Xmx64m` guarantee seeing exactly 2 Young GCs?

**Answer:** No. GC count is runtime-dependent; only the business stdout `processed`/`retained`/`checksumPositive` is fixed.

**Question 10.** How many byte arrays does `retained` in the demo have?

**Answer:** **20**, because there are 100,000 iterations and every 5,000th element is kept, starting from 0.

**Question 11.** GC time is 0.5 s, app time is 9.5 s. What is the application time throughput?

**Answer:** `9.5 / 10 = 95%`.

**Question 12.** Why does a server with a 50 ms p99 latency SLA usually not choose Parallel GC just for good throughput?

**Answer:** Parallel GC has STW pauses that can be longer than the p99 budget; a collector/design suited to the latency SLA is needed and must be measured in practice.

**Question 13.** Does `GC overhead limit exceeded` necessarily prove the program has a reference retention leak?

**Answer:** No. Too small a heap or high live set/allocations can also cause too little progress; you need to inspect the heap, GC logs, and object graph.

**Question 14.** If a program is running G1 by default, how do you test Parallel properly?

**Answer:** Add `-XX:+UseParallelGC`, verify the startup log from `-Xlog:gc=info`, and keep other parameters consistent.

## 16. Summary

```text
                       Parallel GC
                     (Throughput GC)
                             │
             ┌───────────────┴────────────────┐
             │                                │
        Young GC                         Old/Full GC
    Parallel Scavenge                   Parallel Old
             │                                │
    Eden → Survivor/Old               mark/compact old
    live objects are copied           can take large pauses
             │                                │
             └───────────────┬────────────────┘
                             │
                        STW pauses
                   GC workers run in parallel
                  application threads pause
                             │
                     Ergonomics auto-adjusts
                    ┌────────┼──────────┐
                    │        │          │
                pause goal  throughput  footprint
                    │        │          │
                    └────────┴──────────┘

If the problem favors batch throughput and accepts pauses:
  Parallel GC is an option worth benchmarking.

If the problem has a strict latency SLA:
  Compare with G1/ZGC on real data, do not look only at throughput.
```

**Remember:** Parallel GC is HotSpot's **generational, stop-the-world, multithreaded garbage collector**, which handles Young GC and old compaction using multiple worker threads to boost **throughput**. It does **not** mean "the application keeps running during GC". Adaptive sizing prioritizes **pause goal → throughput goal → footprint**, with `GCTimeRatio` expressing the GC time ratio and `MaxGCPauseMillis` being only a soft goal. Choose Parallel GC when throughput matters more than tail latency, then use GC logs and workload benchmarks to verify actual effectiveness rather than inferring from the collector name or core count.

### Official references

- [Oracle Java SE 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): describes Serial, Parallel, G1, ZGC, Parallel Old, and use cases.
- [Oracle Java SE 17 — Parallel Collector Ergonomics](https://docs.oracle.com/en/java/javase/17/gctuning/parallel-collector1.html): pause/throughput/footprint goals and priority policy.
- [Oracle Java SE 17 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): generational architecture and tuning.
- [Oracle JDK 17 — `java` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `UseParallelGC`, `ParallelGCThreads`, `GCTimeRatio`, `MaxGCPauseMillis`, and `UseAdaptiveSizePolicy`.
- [Oracle JDK 17 — Unified JVM Logging `-Xlog`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): logging tags/levels/file syntax.
- [Oracle JDK 17 — `jstat` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): observing GC counters.
- [Oracle Java SE 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): reference for comparing concurrent marking and pause goals.

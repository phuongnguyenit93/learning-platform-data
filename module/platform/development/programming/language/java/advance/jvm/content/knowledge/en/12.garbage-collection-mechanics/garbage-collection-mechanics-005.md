# Serial, Parallel, and Concurrent-with-the-Application Garbage Collection

## 1. Core Point: “serial”, “parallel”, and “concurrent” are not on the same axis

When studying **garbage collection (GC)** in the JVM, three terms frequently appear:

- **Serial:** a single GC thread performs the main collection work of the phase under consideration.
- **Parallel:** multiple GC threads perform work together in a phase to speed up processing.
- **Concurrent with the application:** one or more GC threads perform **part of the work while application threads are still running**.

The two words **parallel** and **concurrent** are very easily mistranslated or confused. In the GC context, the deciding questions are:

1. **How many GC workers perform a phase together?** → the **serial ↔ parallel** axis.
2. **While the GC phase is running, are application threads (mutators) stopped or do they continue operating?** → the **stop-the-world (STW) ↔ concurrent** axis.

A collector can completely be **parallel during STW pauses** and **concurrent in other phases**. For example, HotSpot **G1** uses **parallel** GC workers when evacuating regions during an STW pause, yet also has **concurrent marking** that takes place concurrently with mutators.

### 1.1. Two-axis model

```text
                        APPLICATION
                       stopped?              still running?
                  +---------------------+---------------------+
1 GC worker       | Serial STW          | Serial concurrent   |
                  | Ex: Serial GC       | (1-worker GC phase  |
                  |                     | running w/ mutator) |
                  +---------------------+---------------------+
N GC workers      | Parallel STW        | Parallel concurrent |
                  | Ex: Parallel GC,    | Ex: concurrent      |
                  | G1 evacuation       | marking w/ multiple |
                  |                     | GC workers, dep. VM |
                  +---------------------+---------------------+
```

The cells above are **concepts about execution phases**, not a rigid list where “each collector sits in only one cell”. A collector can pass through **multiple cells in a single GC cycle**.

**Most important takeaway:** *Parallel GC is not necessarily concurrent with the application*. In HotSpot, the collector named **Parallel GC** mainly uses **multiple GC threads for STW phases**, meaning the application can still be stopped while the GC workers run in parallel.

## 2. Why does a running application complicate GC?

A Java application creates objects, updates reference fields, modifies data in collections, and can keep live objects via new reference paths. Threads executing application code are often called **mutator threads**, because they **mutate the graph of object references** in the heap.

GC wants to determine which objects are still reachable and reclaim memory regions that are no longer needed.

```text
GC observes graph:                  Mutator may change:
Root -> A -> B                      Root -> A -> B
         \                               \
          C                               D (new)
```

If GC marks reachable objects while mutators are still changing reference edges, the collector needs **an appropriate consistency/synchronization protocol** so it does not mistake a still-needed object for garbage.

Two major ways of organizing this:

- **Stop mutators during a phase:** the application graph does not continue to be updated by those threads in the usual way during this phase; GC can perform many operations against a more stable state.
- **Let mutators continue running:** the collector must track/correct significant changes, using **write/read/load barriers**, snapshots, remembered sets, forwarding/colored-pointer metadata, or other mechanisms depending on the collector.

**Concurrent collection does not mean there is no coordination left.** It increases requirements for correctness, synchronization, CPU time, and barriers. It can also still have **short STW pauses** to handle sensitive points of the algorithm.

## 3. What is Stop-the-world (STW)?

An **STW pause** is the period of time during which the JVM **pauses the application threads within that stop scope** so the runtime can perform some coordinated work, such as phases of garbage collection. GC worker threads can still run during the pause.

Timeline diagram:

```text
Time --------------------------------------------------->

Application:  RUNNING █████ | STOPPED .... | █████ RUNNING
GC worker 1:          idle | work work ... | idle
GC worker 2:          idle | work work ... | idle
                          ^ STW pause ^
```

During STW, **GC can be parallel** if there are multiple workers, but **the application does not run concurrently with the GC workers for that STW phase**.

### 3.1. Pause time differs from total GC time

- **Pause time:** the time the program is stopped from making progress due to a specific GC pause, as recorded by the JVM.
- **GC work time:** the total time GC workers spend working; if multiple workers work in parallel, **total CPU time** is not equal to wall-clock pause time.
- **Concurrent phase time:** elapsed time while GC performs work at the same time as the application.
- **Application latency:** the time for a request/task to complete from the user's perspective; it can be affected by GC pauses **as well as CPU contention** during concurrent phases.
- **Throughput:** the rate of useful work the system completes over a period of time.

**Do not use “a 500 ms GC cycle” as proof that requests were paused for 500 ms** if most of the cycle ran concurrently. Conversely, do not just look at “2 ms STW pause” and conclude GC does not affect latency: concurrent worker competition, allocation stalls, and barriers can also increase processing time.

### 3.2. STW is not synonymous with all causes of application stalls

Application latency is also affected by OS scheduling, I/O, locks, JIT compilation, safepoint operations, CPU throttling, and memory pressure. GC logs are **one part** of investigating latency, not the sole piece of evidence.

### 3.3. Safepoints and handshakes

HotSpot uses **safepoint/handshake machinery** for operations that require coordinating thread states at the VM level. GC pauses may need to bring mutators to a safe state to observe/update references.

It should not be taught that every STW is always simply “sending a signal to freeze all OS threads at the exact same instruction”: implementations can coordinate at safepoints, use thread-local handshakes, or other mechanisms.

## 4. Serial collection: fewer GC workers, less coordination overhead

The **Serial collector** in HotSpot uses **a single thread** to perform GC work by design. In Java 17, enable this collector with:

```bash
java -XX:+UseSerialGC -jar application.jar
```

`application.jar` is a **placeholder for a JAR with a valid Main-Class**. This is a configuration illustration; a separate practical section later has a runnable Java file.

### 4.1. Operation in a conceptual model

```text
Application   ██████████ |       STOP       | ███████████
GC Worker 1   ---------- | MARK/COPY/SWEEP   | -----------
GC Worker 2   (no second worker for the main collection work)
```

Depending on the generation/phase, the Serial collector may use **copying**, **mark-sweep-compact**, and specific steps. The essential point of the word “serial” is the **parallelism of GC work**, not “the JVM has only one application thread”.

### 4.2. Advantages

- Low coordination overhead between GC workers.
- Suitable for small heaps, limited CPU counts, or applications with simple workloads.
- Easy to reason about the relationship “mutators stop → one worker collects → mutators resume”.
- In some small workloads, the cost of organizing multiple workers can outweigh the benefit of parallelism.

### 4.3. Limitations

- On large heaps/live sets, a single GC worker cannot utilize multiple CPU cores.
- STW pauses can be long if the amount of collection work is large.
- If the SLA has strict latency requirements, Serial may not be suitable.

**Do not conclude that Serial is always the slowest for every workload.** With small data volumes, low CPU quota, or significant parallel setup overhead, a single worker may suffice and sometimes be more efficient.

## 5. Parallel collection: splitting work across multiple GC workers

The **Parallel collector**, also called the **throughput collector**, uses multiple GC workers to process its collection phases. In HotSpot JDK 17:

```bash
java -XX:+UseParallelGC -jar application.jar
```

For suitable tasks, total GC work is divided among multiple workers proceeding together.

```text
Application   ██████████ |         STOP          | ███████████
GC worker 1   ---------- | MARK/COPY PARTITION 1 | -----------
GC worker 2   ---------- | MARK/COPY PARTITION 2 | -----------
GC worker 3   ---------- | MARK/COPY PARTITION 3 | -----------
GC worker 4   ---------- | MARK/COPY PARTITION 4 | -----------
```

**Extremely important:** even though **GC workers run in parallel**, the application is still in an **STW pause**. The name “Parallel GC” does not mean GC runs in parallel with the application.

### 5.1. Why can parallel shorten pauses?

If there is an amount of GC work `W` and `P` workers, the ideal intuition might be “each worker processes about `W/P`”. However, actual time has overhead:

- Dividing work.
- Synchronization and barriers between GC workers.
- Work stealing or load imbalance.
- CPU scheduling and quota in containers.
- Memory bandwidth contention, cache, and NUMA effects.
- Phases that cannot be fully parallelized.

Therefore, **there is no guarantee that quadrupling workers reduces pause time by four times**.

### 5.2. Throughput vs pause time

Parallel GC is often the choice considered when a system needs **high throughput** and can tolerate longer STW pauses than low-latency applications.

For example, a batch job processing large amounts of data may prioritize total records/second over p99 request latency, so throughput GC is worth trying. But if it is an interactive service with a very low p99 SLA, collectors with concurrent phases should also be measured.

### 5.3. When there are too many parallel workers

If the JVM runs in a container granted only a small CPU quota, creating many GC workers can create overhead without real CPU capacity to use. HotSpot ergonomics usually calculate workers from available CPUs, but actual values should be checked, especially when changing container/cgroup configuration.

Do not assume that because the host has 64 cores, the JVM container will get to use all 64 cores.

## 6. Concurrent collection: mutators still operate during part of the cycle

A **concurrent phase** of a collector runs while **application threads can still continue working**. That means GC and the application share CPU/memory bandwidth, coordinating to trace/update references according to the collector's model.

```text
Time --------------------------------------------------------->

Application   ███████████ | pause | █████████████ | pause | ███
GC worker(s)  ----------- | init  | CONCURRENT   | final | ---
                                     ^
                          Mutators are also RUNNING
```

This is a model where **a cycle can combine short pauses and concurrent work**, not a mandatory timeline for every collector.

### 6.1. Concurrent does not mean parallel worker count > 1

A single GC worker can work **concurrently with an application thread** if the two are interleaved by the operating system or run on different cores. Conversely, multiple GC workers can run in parallel with each other during STW without **being concurrent with mutators**.

To answer the question “Is this GC parallel or concurrent?”, ask **which collector or phase is being discussed**, and identify who is stopped during that time interval.

### 6.2. Benefits

- Moves part of the GC work out of application pause intervals.
- Has the potential to reduce **STW time** and improve tail latency.
- Can reduce the dependence of pause duration on heap/live-set size for certain collectors.
- Suitable for applications requiring low latency.

### 6.3. Costs

- GC and the application compete for CPU/memory bandwidth.
- Write/load barriers and GC bookkeeping have overhead.
- Heap headroom is needed so mutators can continue allocating while the GC cycle has not finished.
- If the allocation rate exceeds the collector's reclamation rate, an **allocation stall**, fallback, or OOME can occur depending on the collector and situation.
- Implementation is more complex, requiring mechanisms to maintain correctness as the object graph changes.

**No collector provides “free GC” or guarantees absolute zero-pause merely by being concurrent.**

## 7. Synchronization mechanisms so concurrent collectors remain correct

A GC problem must answer: if mutators continuously update references while GC marks, how do we avoid mistakenly reclaiming live objects?

### 7.1. Marking, write barriers, and snapshots

Suppose GC has already scanned object `A`, and then a mutator changes `A.child` from `B` to `C`. A concurrent marking algorithm must handle this change in a way that preserves its invariants.

Technique families include:

- **Snapshot-at-the-beginning (SATB):** records a logical snapshot view at the start of marking, with barrier mechanisms to track references that might be removed from the graph.
- **Incremental-update marking:** tracks/adapts to new edges that change the graph being marked.
- **Load/read barriers:** check/adjust references when the application reads them, important in some collectors with concurrent relocation.
- **Remembered sets/card tables:** track relevant heap regions/generation groups, avoiding scanning the entire heap for every minor GC.

**There is no single barrier protocol that applies to every collector.** For example, G1 in configurations described by Oracle documentation uses **SATB concurrent marking** and remembered-set mechanisms; ZGC/Shenandoah use their own techniques for marking/relocation.

### 7.2. Why does remark still need to stop?

After a concurrent marking phase, the collector may need to finalize accumulated data and establish a consistent liveness state. With G1, **Remark** is an **STW pause**, processing the remainder of concurrent marking according to the algorithm.

Therefore:

```text
G1 concurrent mark ≠ “G1 has no STW left”
```

A collector described as **mostly concurrent** can still require other stop-the-world phases.

### 7.3. Mutation rate affects concurrent GC

If an application has a very high rate of reference updates and allocation, the amount of GC bookkeeping and marking needed can increase. A collector with concurrent marking cannot ignore all object mutations.

When benchmarking, in addition to heap size, one must measure **allocation rate, live-set size, mutation rate, and CPU capacity**. Two applications using the same `-Xmx` can have very different GC behavior.

## 8. Classifying by phase instead of sticking one label on the whole collector

| Collector/phase in HotSpot | Can GC workers be parallel? | Do mutators still run in that phase? | Meaning |
| --- | --- | --- | --- |
| **Serial GC — collection pause** | No, one main GC worker | **No — STW** | Simple, low coordination |
| **Parallel GC — collection pause** | **Yes, multiple workers** | **No — STW** | Prioritizes throughput |
| **G1 — young/mixed evacuation** | **Yes** | **No — STW** | Evacuates/copies live objects by regions |
| **G1 — concurrent marking** | **Can be multiple workers** | **Yes** | Traces live data while the application runs |
| **G1 — remark** | Can be parallel GC work | **No — STW** | Completes the marking part needing synchronization |
| **ZGC — most expensive GC work** | Has multiple workers depending on phase | **Yes** | Targets low latency, still has short pauses |
| **Shenandoah — many mark/evacuation phases** | Can be parallel | **Yes** | Concurrent mark and relocation, depending on build/mode |
| **Full GC fallback, if it occurs** | Depends on collector/version | Usually has significant **STW** | Should not be confused with normal cycles |

The table describes **typical phases**, not a contract that every HotSpot build uses the exact same threads/phases. Flags, collector version, and architecture can change the details.

## 9. Serial GC: mechanics and usage choices

Serial GC is a clear example of **serial and STW collection**. Points to remember:

1. **A single GC worker** performs the collection work.
2. **Young collection** in a generational model typically moves live objects and reclaims the young space.
3. **Old collection** may perform marking, sweep/compact depending on the specific operation of the Serial collector.
4. The main collection work creates a pause while mutators are stopped.
5. There is no overhead of coordinating multiple GC workers for each collection.

### 9.1. When to choose Serial?

- Small heap or small object graph.
- Environment with extremely limited CPU.
- Tool/CLI or batch workload with little concurrency.
- Measured pause time meets requirements.
- Wanting to measure a simple baseline before trying more complex collectors.

### 9.2. When to consider switching?

If request p99 is affected by long STW pauses, or the application has many cores and GC takes a significant portion of wall time, try Parallel/G1/ZGC according to measurement goals.

Do not change collectors just because “Serial sounds outdated”: a small configuration can still use it very reasonably.

## 10. Parallel GC: throughput and tuning

The Parallel collector uses multiple workers for GC, usually focusing on **throughput**. It still has pauses where the application stops.

### 10.1. Tuning workers with real data

Common HotSpot flag:

```text
-XX:ParallelGCThreads=<n>
```

This is a **placeholder**; in actual configuration `<n>` must be replaced with a valid integer, checking interaction with the collector and runtime. This flag relates to the number of GC workers for parallel work in collectors that support it.

“Setting workers = all CPU cores” is not always optimal. CPU quota, application threads, pause targets, and overhead must be accounted for.

### 10.2. Throughput-oriented configuration

Parallel GC can be tuned with throughput/pause goals and adaptive sizing of the collector in HotSpot, though flags have specific meanings/effects by version.

```text
-XX:+UseParallelGC
-XX:ParallelGCThreads=4
```

This is an option example, not a recommended default for every server. It is better to start from ergonomic defaults and measure GC logs, p95/p99, throughput, CPU, and pause distribution.

### 10.3. A common misconception: do more CPUs make STW disappear?

No. Parallelization can shorten the **wall-clock time** of the parallelized GC phase, but it is still an **STW pause**. If the live set is large, heap pressure is heavy, or much data must be moved, the pause can still be significant.

## 11. G1: a collector that is parallel, mostly concurrent, and STW

**G1 (Garbage-First)** is the default collector in many common HotSpot Java 17 configurations, though the actual default choice still depends on VM ergonomics and the environment. Explicit enablement flag:

```bash
java -XX:+UseG1GC -jar application.jar
```

G1 divides the heap into **regions**, manages logical young/old parts, and selects regions worth reclaiming. It uses concurrent marking to determine liveness/old candidates and uses STW evacuations to reclaim sets of regions.

### 11.1. Typical phases

```text
G1 cycle — conceptual diagram

[STW Young / Concurrent Start]
            |
            v
   Concurrent Root Region Scan
            |
            v
      Concurrent Marking
            |
            +-- STW Young collections may interleave
            |
            v
        [STW Remark]
            |
            v
   [STW + Concurrent Cleanup]
            |
            v
  Several [STW Mixed collections]
            |
            v
     Return to young-only phase
```

Specific names/ordering reflect JDK 17's description of G1 in typical operating scenarios; it is not a forced trace that happens on every GC.

### 11.2. G1 evacuation is still STW

During young/mixed GC:

- The JVM selects a set of regions.
- Multiple GC workers can **copy/evacuate** live objects to other regions.
- Object references are updated according to the algorithm.
- **Mutators are stopped during the evacuation pause**.

Because G1 has **concurrent marking**, calling “G1 a non-STW collector” is wrong.

### 11.3. G1 pause goal is not a guaranteed deadline

```text
-XX:MaxGCPauseMillis=200
```

This example represents a **pause-time goal** for a supporting collector, **not a guarantee that every pause is ≤200 ms**. G1 adjusts work based on predictions, and can miss the goal when memory pressure, live set, CPU, or workload is unfavorable.

Do not use a pause goal as a substitute for measuring tail latency.

### 11.4. Full GC fallback

In some situations where allocation/evacuation/marking cannot keep up and the heap is too tight, G1 may have to perform a costly **Full GC fallback**, usually causing a long STW pause.

Do not infer that “choosing G1 means there will never be a Full GC”. Headroom and root-cause investigation of pressure are needed.

## 12. ZGC and Shenandoah: moving more work into concurrent phases

### 12.1. ZGC

**Z Garbage Collector (ZGC)** focuses on **low latency**, performing most expensive work **concurrently with mutators**; there are still short coordinations/pauses depending on version and phase.

Enable on a supported HotSpot build with:

```bash
java -XX:+UseZGC -jar application.jar
```

ZGC is designed to bound pauses without having to put all marking/relocation of the live set inside an STW window. It can use specialized pointer/barrier mechanisms and needs CPU/headroom for concurrent work.

However:

- It does not promise **0 ms pauses**.
- It does not promise every endpoint's p99 will be better in every workload.
- It can incur throughput overhead and allocation stalls when there is insufficient CPU/headroom.
- Flags and generational/non-generational modes **change across JDKs**; do not apply every tuning recipe across Java 17, 21, 25, and newer releases.

### 12.2. Shenandoah

**Shenandoah** is a **low-pause**-oriented collector, performing many operations (including marking and, in its corresponding design, evacuation/compaction) concurrently with the application.

Some OpenJDK/HotSpot builds support:

```bash
java -XX:+UseShenandoahGC -jar application.jar
```

**Not every vendor/build/platform provides Shenandoah.** If the option is not recognized by the VM, it is a runtime feature-support issue; check `java -version` and vendor documentation before choosing it.

### 12.3. Why is concurrent relocation hard?

During marking, the collector identifies live objects. During **relocation**, the collector may move live objects to new locations. If mutators are still running, reference loads/stores must see the right object during the move; the VM must coordinate pointer forwarding, barriers, or other mechanisms.

**Concurrent compaction is not simply calling `System.arraycopy` in the background and hoping all Java references fix themselves.** It is a delicate coordination problem between mutator, GC, and runtime representation.

### 12.4. “Pause time completely independent of heap size” must be understood with conditions

Low-pause collectors are usually designed to avoid pauses scaling directly with large amounts of live data, but factors such as OS scheduling, root processing, CPU starvation, safepoint latency, and fallbacks still affect pauses. Do not treat a marketing phrase like “sub-millisecond” as an absolute SLA for every JDK/build/workload.

## 13. “Concurrent” is time overlap, not a guarantee of simultaneous execution on separate cores

In a container environment with **one CPU quota**, GC workers and application threads may interleave on the same CPU. They are still considered **concurrent** if the collector phase operates during the period when mutators are allowed to run, even if two instructions do not literally execute at **the exact same nanosecond** on two CPU cores.

Distinguish:

- **Concurrency:** tasks have logically overlapping lifetimes/execution.
- **Parallelism:** multiple tasks literally make progress at the same time on parallel processors, under appropriate conditions.
- **STW:** mutators do not make normal progress during the pause interval, even though GC workers may use multiple CPUs.

When reading GC documentation, **parallel** usually refers to the number of **GC worker threads** participating in a phase, not just the general definition of concurrency in multithreaded programming.

## 14. Costs of concurrent GC: CPU, barriers, allocation headroom

A concurrent collector can reduce pauses by paying a “price” elsewhere.

### 14.1. CPU contention

If GC workers operate concurrently for 300 ms, the application keeps running but may lack CPU capacity. A request that is not hit by an STW pause can still see increased latency due to scheduler contention.

### 14.2. Allocation headroom

Mutators continue allocating memory while the collector has not yet finished reclaiming. If the heap is too full, the collector may have no room to hold temporary objects or copy/relocate. At that point, **failure/stall paths** appear depending on the algorithm.

### 14.3. Barriers and metadata

Write/load barriers add some instructions/memory operations to mutators, depending on the collector. Remembered sets, mark bitmaps, and forwarding data also require memory.

### 14.4. Throughput trade-off

A benchmark might show:

- Parallel GC: higher throughput but longer p99 pauses.
- G1: slightly lower throughput, more controllable p99 pauses.
- ZGC/Shenandoah: lower pauses but may use additional CPU/heap for concurrent work.

**This is an illustrative scenario, not a fixed ranking table.** Actual results vary by workload, hardware, JDK/GC version, and measurement method.

## 15. A runnable Java 17+ example across multiple collectors

The program below creates a **controlled allocation workload**. It retains some arrays in a list, while other arrays are not kept long-term. Because GC scheduling is non-deterministic, the program **does not print GC event counts or pause timings**; those metrics are viewed in GC logs.

Create the file **`GCWorkloadDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GCWorkloadDemo {
    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 512; i++) {
            byte[] block = new byte[512 * 1024];
            block[0] = (byte) i;

            checksum += block[0] & 0xFF;
            if (i % 32 == 0) {
                retained.add(block);
            }
        }

        long sum = 0;
        for (byte[] block : retained) {
            sum += block[0] & 0xFF;
        }

        System.out.println("checksum=" + checksum);
        System.out.println("retained arrays=" + retained.size());
        System.out.println("retained first bytes sum=" + sum);
    }
}
```

### 15.1. Compile

```bash
javac --release 17 GCWorkloadDemo.java
```

### 15.2. Run with different collectors

On an OpenJDK/HotSpot build that supports the corresponding collectors:

```bash
java -Xms64m -Xmx64m -XX:+UseSerialGC GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseParallelGC GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseG1GC GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseZGC GCWorkloadDemo
```

**Application stdout when runs complete normally:**

```text
checksum=65280
retained arrays=16
retained first bytes sum=1792
```

The code was compiled with `javac --release 17` on OpenJDK 21 and tested with **Serial, Parallel, G1, and ZGC at a 64 MiB heap**; all four printed the same result as above.

Do not treat `-Xmx64m` as a recommended production configuration: this is a small heap creating GC pressure for easy practice. In an environment lacking native memory, where a GC mode is not built, where other flags interact, or where CPU quota is too low, a command may fail or produce a different GC timeline.

### 15.3. Calculation explanation

- There are 512 allocations of `byte[512*1024]`.
- `block[0]` is the byte of `i`; when read back as unsigned with `& 0xFF`, values `0..255` repeat twice.
- The sum is `2 × (0+1+...+255) = 65280`.
- Every 32 iterations retains one array: `i = 0,32,...,480`, totaling **16 arrays**.
- The first bytes of the 16 retained arrays are `0,32,...,224` repeated twice, totaling **1792**.

The application does not depend on the collector to compute correctly. Differences lie in **GC throughput, pause/concurrent timings, CPU usage, and memory footprint**.

### 15.4. Why not write a test asserting “GC must occur exactly 12 times”?

The collector chooses timing and amount of work based on heuristics, allocation patterns, JDK/VM options, heap pressure, and JIT. There is no guarantee that a program allocating 512 arrays must make Java run exactly N GCs.

To measure, use logging/profiling and compare distributions instead of hardcoding event counts.

## 16. Enabling GC logging to observe STW and concurrent phases

HotSpot JDK 17 has **Unified Logging**. For example:

```bash
java -Xms64m -Xmx64m -XX:+UseSerialGC -Xlog:gc*=info GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseParallelGC -Xlog:gc*=info GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseZGC -Xlog:gc*=info GCWorkloadDemo
```

**GC log output is NOT fixed** and will appear in addition to the three stdout lines of the application: timestamps, GC IDs, event counts, heap occupancy, workers, and timings vary by runtime and environment. You must not take one log sample and claim every machine must produce the exact same result.

### 16.1. Reading key terms in logs

On applicable HotSpot builds:

- `Pause Young`: an STW pause related to young collection.
- `Pause Full`: a full-heap collection pause or corresponding fallback.
- `Concurrent Mark` or `Concurrent ...`: a GC phase organized to work concurrently with mutators.
- `Using ...`: startup lines may state the chosen collector.
- `workers` or phase/worker tags: help observe the level of parallelism and worker time.

**Do not interpret every line containing `GC(n)` as one STW.** A single GC cycle can have multiple phase logs; concurrent phases can carry the same GC ID or different log organization.

### 16.2. Comparing Serial and Parallel

In many workloads:

- Serial has GC work based on one worker, STW times.
- Parallel has multiple GC workers during pauses, STW times still exist.
- Log lines differ due to collector-specific formats and algorithms.

Do not conclude “Parallel is faster than Serial” just by looking at **a single pause**: total throughput, pause distribution, and CPU cost must be compared.

### 16.3. Comparing G1 and ZGC

- G1 has both STW young/mixed evacuations and concurrent marking.
- ZGC moves much heavy work into concurrent phases; some pauses/coordinations still remain.
- Suitability depends on latency budget, CPU, and heap headroom.

### 16.4. Checking logging tags

```bash
java -Xlog:help
```

Tags and levels can differ when changing JDKs; do not copy a specific `-Xlog` combination from an old blog and use it for all HotSpot versions.

## 17. Parameters to measure when deciding on a collector

| Metric | Meaning | How to use |
| --- | --- | --- |
| **STW pause p50/p95/p99/max** | Distribution of pause intervals | Examine tail latency, outliers, and SLA |
| **Request p95/p99** | Actual user-facing latency | Combine GC logs and tracing |
| **Throughput** | Requests/records/tasks per second | Compare end application benefit |
| **CPU utilization** | Mutators + GC workers | Detect GC contention |
| **Allocation rate** | Bytes newly created per second | Analyze pressure on young/old heap |
| **Live set** | Size of still-reachable objects | Determines amount of mark/copy/compact |
| **Heap occupancy / headroom** | Space remaining for allocation/relocation | Avoid stalls, fallbacks, OOME |
| **GC CPU time vs wall time** | Compute cost and elapsed time | Do not mistakenly sum multiple workers as one pause |
| **Concurrent cycle duration** | Time GC keeps running alongside mutators | Detect cycles falling behind |
| **Full GC / allocation stalls** | Abnormal situations that can cause latency | Analyze memory pressure and tuning |

### 17.1. Distinguishing latency and throughput

- A batch processing application can optimize records/s, accepting STW pauses.
- A user-facing API can prioritize p99 end-to-end latency.
- A mixed-workload system must balance both, depending on the SLO.

The same collector is not always optimal for every goal.

### 17.2. Benchmark results need repetition and a baseline

A good process:

1. Keep the **same JDK build**, same application artifact, and workload.
2. Fix appropriate heap options, CPU quota, and container limits.
3. Warm up before measuring to reduce JIT/class-loading noise.
4. Repeat multiple runs, measuring throughput and pause/latency distribution.
5. Record class counts, live set, allocation rate, CPU, and memory.
6. Compare against business goals before choosing a collector.

If a single run gives Parallel GC better p99 than G1, that is an observation, not a permanent law.

## 18. Related flags and caveats against “blind tuning”

### 18.1. Choosing a collector

```text
-XX:+UseSerialGC
-XX:+UseParallelGC
-XX:+UseG1GC
-XX:+UseZGC
-XX:+UseShenandoahGC  (when supported by the HotSpot build)
```

Each JVM process usually selects **one appropriate collector**; do not arbitrarily combine different collector selection flags in one command. Availability and defaults depend on the VM/JDK build.

### 18.2. G1 goals and workers

```text
-XX:MaxGCPauseMillis=200
-XX:ParallelGCThreads=4
-XX:ConcGCThreads=2
```

The values above **only illustrate flag types**, not default production configurations. `ParallelGCThreads` controls parallel work in supporting collectors/phases; `ConcGCThreads` is a parameter related to concurrent worker count depending on the collector.

If concurrent workers are set too low, the collector may not keep up with the allocation/mutation rate. If too high, the application may be starved of CPU.

### 18.3. Avoid relying on old tuning recipes

Collectors, flags, and algorithms have changed across JDK releases. For example, **CMS** (Concurrent Mark Sweep) is a historical collector, removed from HotSpot since **JDK 14** (JEP 363), so do not use `-XX:+UseConcMarkSweepGC` as a current option in JDK 17.

With ZGC, newer versions have **generational** support that brings major changes in design and tuning. Do not take a set of flags from JDK 17 and apply them to JDK 25/27 without checking migration notes.

### 18.4. “50ms GC pause goal” is not a real-time guarantee

Some flags help a collector aim for a pause target using heuristics, but do not promise an absolute deadline in every situation. Hard real-time guarantees (*hard real-time*) require a different system model and specialized runtime, not just changing GC flags.

## 19. A G1 cycle can be both parallel and concurrent: full interpretation

Suppose (for ease of visualization) an application has 4 application threads and G1 is assigned 4 parallel workers during STW pauses, and 2 workers during concurrent phases. These are **illustrative numbers**, not guaranteed defaults.

```text
                t0              t1              t2             t3
                |               |               |              |
Mutators A-D    RUNNING  ...  [PAUSE]   RUNNING  ...          [PAUSE]
                                  |                              |
GC 4 workers                      | parallel evacuation          | parallel work
                                  |
GC 2 workers                                     concurrent mark
                                                 +------+--------+
                                                        |
                                               mutators RUNNING
```

Interpretation:

1. During **STW evacuation**: 4 GC workers can run simultaneously with each other, while the 4 mutator threads are stopped.
2. During **concurrent mark**: 2 GC workers work during a period when the 4 mutators are allowed to run.
3. At the end of marking there may be **STW remark/cleanup**.
4. Do not count the total time of the concurrent phase as a pause.
5. Application CPU may be shared during concurrent mark.

That is why a description such as **“G1 is parallel, mostly concurrent, evacuating, and stop-the-world”** is not self-contradictory; each attribute describes an aspect/phase of the collector.

## 20. Practical scenario analysis

### Scenario A — Small CLI tool, running for a few seconds

A CLI tool with a small heap, a modest number of objects, and a low CPU quota can try **Serial GC**. The overhead of creating multiple GC workers sometimes brings no benefit. However, verify runtime and total latency, rather than relying on the collector's name.

### Scenario B — Batch processing needing throughput

A batch worker running on a multi-core machine, which tolerates fairly long pauses but wants short total processing time, can try **Parallel GC**. Still measure pause times and memory, because overly long pauses can affect job coordination.

### Scenario C — HTTP API with a p99 target

An HTTP service needing to reduce tail latency can start with **G1** (often the default on server-class Java 17 configurations) and observe STW young/mixed pauses. If p99 still does not meet requirements, try **ZGC** on a supported runtime, while measuring CPU, request latency, and allocation stalls.

### Scenario D — Application creating objects extremely fast

A system with a high allocation rate, large live set, and little heap headroom can cause a **concurrent collector to fall behind**. It is not simply solved by “choosing concurrent GC”; you need to reduce allocation, fix retention, increase heap/headroom appropriately, or adjust the workload.

### Scenario E — 2-vCPU container experiencing CPU throttling

A JVM running concurrent GC in a container can suffer CPU contention/throttling, lengthening both GC cycles and request times. Measured GC pauses may be small, yet p99 requests still increase. Check CPU quota and throttling metrics instead of looking only at GC logs.

## 21. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Parallel GC runs alongside the application.” | Parallel mainly refers to GC workers; the Parallel collector has STW phases during which mutators stop. |
| “Serial GC only runs when the application has one thread.” | One GC worker does not limit the number of application threads. |
| “Concurrent GC never has STW.” | Many concurrent collectors still have short pauses/coordination. |
| “G1 is only concurrent, not parallel.” | G1 uses both parallel STW evacuation and concurrent marking. |
| “A 500 ms GC cycle means requests pause for 500 ms.” | Concurrent cycle elapsed time differs from STW pause time. |
| “4 GC workers are definitely 4x faster.” | Synchronization/overhead/CPU and non-parallel work limit speedup. |
| “A 2ms STW pause means GC uses no CPU.” | Concurrent phases, barriers, and runtime bookkeeping can consume CPU. |
| “Concurrent GC needs no heap headroom.” | Mutators still allocate while GC has not finished reclaiming. |
| “`MaxGCPauseMillis` is an absolute deadline.” | It is a heuristic goal, not a hard SLA. |
| “Enabling ZGC always makes throughput better.” | Low-latency has CPU/throughput trade-offs and depends on the workload. |
| “`System.gc()` guarantees a GC cycle starts/ends on an exact schedule.” | It is not a portable tool for testing GC event counts. |
| “With a large heap, there is no need to measure GC.” | Live set, allocation/mutation rates, and latency still matter. |
| “CMS is still a normal choice on JDK 17.” | CMS was removed from HotSpot in JDK 14. |
| “Shenandoah is always available on every JDK.” | Depends on vendor/build/platform. |
| “G1 is the default on all JVMs.” | The default depends on implementation/ergonomics, though G1 is common on HotSpot server configurations. |
| “Every GC log line represents a pause.” | There are also concurrent phase logs, startup info, and multiple events in one cycle. |
| “Host CPU has 64 cores means the container uses all 64.” | CPU quota/cgroup can impose limits. |
| “There is one best collector for every system.” | Must choose based on SLO, workload, heap, CPU, version, and measurement. |

## 22. Self-check exercises with answers

**Question 1.** Does Parallel GC need to stop application threads during collection pauses?

**Answer:** Yes. Multiple GC workers work **in parallel with each other** during **STW**, which does not mean they run concurrently with mutators.

**Question 2.** Does Serial GC forbid a Java program from creating multiple threads?

**Answer:** No. “Serial” refers to GC work, not the number of application threads.

**Question 3.** A concurrent GC phase has exactly one GC worker and mutators still run. Is it concurrent?

**Answer:** Yes. Being concurrent with the application is a different axis from the number of parallel GC workers.

**Question 4.** Can G1 have concurrent mark and STW evacuation together in one GC lifecycle?

**Answer:** Yes. G1 combines multiple phases; there is no contradiction between “mostly concurrent” and “stop-the-world phases”.

**Question 5.** Why does a concurrent collector need write/load barriers?

**Answer:** Mutators still modify or access the reference graph while GC is working; barriers help preserve the invariants of the respective marking/relocation algorithm.

**Question 6.** Does a 300 ms concurrent marking phase mean the application is paused for 300 ms?

**Answer:** No. That can be the time GC works while mutators continue; pauses, if any, must be checked in separate phases/logs.

**Question 7.** If ZGC has small pauses but CPU usage increases, is the application definitely faster?

**Answer:** No. CPU contention/barrier overhead can affect throughput and latency; you must benchmark end-to-end.

**Question 8.** Why can Parallel GC help a batch job?

**Answer:** Multiple GC workers can shorten the wall time of collection phases on multi-core systems, improving throughput when long pauses are acceptable.

**Question 9.** Can `-XX:MaxGCPauseMillis=50` be treated as a p99 SLA under 50ms?

**Answer:** No. It is a GC pause goal, not a guarantee that every pause or request response time is under 50ms.

**Question 10.** A concurrent collector is still working while mutators create many more objects. What is the risk?

**Answer:** Heap headroom may be exhausted before GC reclaims enough, causing allocation stalls/fallback/OOME depending on the collector.

**Question 11.** Are ZGC and Shenandoah present in every Java 17 distribution?

**Answer:** Cannot be assumed. Features and support depend on VM vendor/build/platform.

**Question 12.** Is G1 young collection usually STW or concurrent with the application?

**Answer:** Evacuation of selected young regions takes place during an **STW pause**; GC workers can operate in parallel.

**Question 13.** Why not measure GC speed by a single total elapsed time line and compare?

**Answer:** A collector can have concurrent work that does not stop mutators; pause times, CPU work, throughput, and effect on the application must be separated.

**Question 14.** Seeing a gc worker count of 8 in the log, does that prove 8 real CPU cores ran simultaneously?

**Answer:** No. The number of worker threads does not guarantee parallel hardware execution, especially with CPU quota/throttling.

**Question 15.** Does switching from Serial to Parallel always reduce p99 request latency?

**Answer:** No. It may reduce some STW durations, but there are overheads and workload differences; measurement is required.

**Question 16.** Why does `GCWorkloadDemo` produce the same stdout when run with different collectors?

**Answer:** GC chooses how to reclaim memory, but must preserve Java program semantics. The checksum and retained list elements have deterministic results.

**Question 17.** When to consider ZGC instead of G1?

**Answer:** When the latency SLO is hard to meet despite optimizing workload/heap and G1, while the runtime supports ZGC and has CPU/heap headroom for concurrent GC. Must be verified by benchmarking.

**Question 18.** If G1 is doing concurrent mark but STW young collections interleave, is it wrong to call G1 concurrent?

**Answer:** No. G1 is mostly concurrent in some work, yet still has pauses. It needs to be described at the phase level.

## 23. Selection and operations checklist

1. Define **latency SLO**, **throughput**, and CPU/memory budget.
2. Record JVM vendor, version, architecture, cgroup quota, and heap limits.
3. Start with the default collector if there are no special requirements; check logs to confirm the actual collector.
4. Measure allocation rate, live set, promotion, and heap headroom.
5. Observe **STW pause distribution**, not just total GC duration.
6. Observe **CPU contention during concurrent phases**.
7. Check for Full GC fallbacks, allocation stalls, and OOME if any.
8. With G1, understand that concurrent marking differs from STW evacuation.
9. With Parallel, remember that parallel GC workers do not mean mutators still run during STW.
10. With low-latency collectors, do not assume zero pauses or free CPU cost.
11. Compare workloads after warm-up, across repeated runs, with the same resource limits.
12. If the container is being throttled, check quota and available processor count.
13. Check current flags with `java -XX:+PrintFlagsFinal -version`; do not guess defaults.
14. Check collector support before setting flags, especially Shenandoah and flags across JDK versions.
15. Do not try to trigger GC in unit tests and assert fixed event counts.
16. Fix **unbounded allocation or object retention** before treating GC flags as a cure-all.
17. For production systems, combine GC logs, JFR, application tracing, and OS metrics.
18. Ensure any collector tuning does not change application semantics and correctness.

### Final summary

```text
                   How many GC workers?
                     1              N
                     |              |
               Serial GC work    Parallel GC work
                     \              /
                      \            /
               Are mutators still running?
                 /             \
                No             Yes
                |                |
                v                v
           STW phase         Concurrent phase
                |                |
          Application pause    GC & application
                               make progress together
                                 (sharing CPU)

A modern collector can use N GC workers during STW
AND multiple GC workers running concurrently in another phase.
```

**Conclusion:** **Serial/parallel** describes **the degree of parallelism of GC work**, whereas **STW/concurrent** describes **whether GC works while the application is stopped or still running**. Do not conflate the two axes into one.

### Official references

- [Oracle JDK 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC, and selection criteria.
- [Oracle JDK 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): GC workers, STW evacuation, concurrent marking, pause goals.
- [Oracle — G1 Garbage Collector Phases](https://www.oracle.com/java/technologies/g1gc.html): SATB, remark, young/mixed evacuation, phase-specific concurrency.
- [OpenJDK JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/333): concurrent GC and low-latency objectives.
- [OpenJDK JEP 189 — Shenandoah: A Low-Pause-Time Garbage Collector](https://openjdk.org/jeps/189): concurrent compaction/reclamation.
- [OpenJDK JEP 363 — Remove the Concurrent Mark Sweep (CMS) Garbage Collector](https://openjdk.org/jeps/363): historical CMS no longer in JDK 14+ HotSpot.
- [Oracle JDK 17 — java command options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): collector selection and Unified Logging `-Xlog`.
- [JVMS `2.5.3` — Heap (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): automatic storage management does not mandate a specific GC implementation.

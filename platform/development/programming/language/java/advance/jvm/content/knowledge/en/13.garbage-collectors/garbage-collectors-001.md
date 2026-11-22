# Serial GC: Simple Mechanism and Resource-Constrained Environments

**Serial Garbage Collector (Serial GC)** is a **HotSpot JVM** garbage collector that uses **a single GC worker thread** to perform collection work during each collection, rather than mobilizing multiple GC workers in parallel. When Serial GC performs its normal collection phases, **application threads (mutators) are paused via a stop-the-world (STW) mechanism**. This design reduces GC thread coordination overhead, is fairly easy to observe, and can be suitable for small programs, small heaps, or limited CPU resources; in return, it **does not utilize multiple CPU cores to shorten collection pauses**.

In HotSpot JDK 17, Serial GC can be explicitly selected with:

```bash
java -XX:+UseSerialGC MyApp
```

Here, `MyApp` is the name of a compiled class containing `public static void main(String[] args)`. `-XX:+UseSerialGC` is a **HotSpot-specific flag**; do not assume all other Java SE JVMs support the same syntax.

This lesson explains **how it works**, especially **young copying collection**, **old mark-compact**, **GC roots**, **pauses**, and **promotion**, while also guiding how to **measure, compare, and choose an appropriate environment**. Examples are compatible with **Java 17+**, and only the output of the Java program is considered deterministic; the number of lines, frequency, and GC timings in the logs **must not be guessed in advance**.

## 1. Distinguishing Serial GC from a “Single-Threaded Application”

Two concepts are often confused:

- **Single-threaded garbage collection:** Serial GC uses **one worker** to handle collection work across its collection phases.
- **Single-threaded application:** a Java program has only one application thread.

Choosing Serial GC does **not** force a Java program to be single-threaded. The program can still create multiple threads, use executors, networking, synchronization, or virtual threads if the JDK supports them. The difference is that **the garbage collection work of this collector is not parallelized across multiple GC workers** like Parallel GC.

```text
Multi-threaded application             Serial GC pause
──────────────────────────┐           ┌───────────────────────
Thread A running Java     ├── STW ────┤ Thread A resumes
Thread B running Java     │           │ Thread B resumes
Thread C running Java     │           │ Thread C resumes
──────────────────────────┘           └───────────────────────
                                │
                                ▼
                           One GC worker
                           scans/copies/compacts
```

This is a **logical diagram**: it does not depict the exact start/end points of each thread or all VM runtime activities. The JVM also has other management/JIT/VM threads; **“Serial GC uses one GC thread” does not mean the entire JVM has only a single OS thread**.

**Main consequence:** GC does not pay the coordination cost of multiple GC worker threads for a single collection; however, when the heap has many live objects, **a single worker has to do a lot of work sequentially**, so pause times can be longer than collectors that use parallel/concurrent work for the same workload.

## 2. Serial GC Is a Generational Collector

In the traditional generational model of HotSpot Serial GC, the Java heap is divided into the **young generation** and the **old (tenured) generation**. The generational hypothesis states that many objects die quite early, while objects that survive multiple collections are likely to continue living longer.

```text
Java Heap (Serial GC model)
┌────────────────────────────────────────────────┐
│ Young generation                               │
│   Eden ─── where many new objects are allocated│
│   Survivor S0                                  │
│   Survivor S1                                  │
├────────────────────────────────────────────────┤
│ Old / Tenured generation                       │
│   longer-lived objects, promoted objects       │
└────────────────────────────────────────────────┘

Outside Java heap:
  Metaspace, Code Cache, thread stacks,
  direct/native allocations ... (non-heap)
```

This is a **heap region concept**, not a guarantee of addresses, region ordering, or byte counts across all JVMs. The organization in Serial GC differs from G1, ZGC, or Shenandoah.

### Young generation

The young generation typically consists of:

- **Eden:** where most new objects are initially created.
- **Two survivor spaces:** source/destination for copying objects that survive across young GC cycles.
- **Tenuring/promotion:** objects that have reached a sufficient age, or objects that are not suitable to remain in a survivor space, may be moved to the old generation according to VM policy.

### Old generation

The old generation receives long-lived objects or objects promoted from the young generation; when space is insufficient or based on VM conditions, an **old-generation/full collection** may be performed. In the traditional HotSpot Serial collector, old collection work is associated with **mark-compact**, differing from the **copying** approach commonly seen in young collection.

**Note:** Eden, survivor, and old generation are the collector's runtime model. **A local variable residing on the stack does not mean the object it points to also resides on the stack.** Objects are allocated in the Java heap, except for optimizations that eliminate physical allocation while preserving Java semantics.

## 3. Allocation Flow and Lifecycle of an Object

Example:

```java
byte[] data = new byte[1024];
```

This is a line of Java placed inside a method. In the typical execution of HotSpot Serial GC:

1. When a new object is needed, the VM finds suitable allocation space, usually in **Eden**.
2. When the young generation no longer has enough space or a collection condition is met, the JVM may trigger a **young GC**.
3. The JVM pauses mutator threads at appropriate safepoints (**STW pause**).
4. The collector identifies live objects via roots and relevant references, and **copies the young objects that need to be kept alive** to the appropriate survivor/old space.
5. Eden memory containing dead objects can be reused after the collection.
6. Objects surviving across multiple cycles may age and **promote** into the old generation.
7. When the old generation comes under pressure or another condition arises, the VM may perform a **Full GC/old collection** according to collector policy.

Not every object must go through **exactly N** young GCs before moving to the old generation. **Tenuring threshold**, survivor occupancy, object sizes, and memory conditions all have an impact; an object may be promoted earlier. There is no Java SE rule stating “every object surviving more than 15 times is guaranteed to promote on the 16th time” regardless of configuration.

### TLAB and allocation

HotSpot may use **thread-local allocation buffers (TLABs)** to help application threads allocate objects quickly in the young generation. TLAB does not mean GC becomes multi-threaded or has no STW; it mainly helps the **allocation path** while the application is running.

In practice, an object proven by the JIT not to escape may be handled via escape analysis/scalar replacement, so a `new` statement in source code **does not prove an actual heap allocation occurred** on every execution path.

## 4. Young GC: How Does Copying Collection Work?

Serial collector's Young GC uses a **stop-the-world copying scavenger** mechanism. During a collection, the collector starts from roots and references entering the young generation, discovers live objects in the collected region, and then copies them to a survivor space or promotes them to old.

```text
BEFORE YOUNG GC

Eden:        [A live][X dead][B live][Y dead][Z dead]
Survivor S0: [C live][W dead]
Survivor S1: [empty]

            stop-the-world
                │
                ▼
GC scans roots + relevant old-to-young references.
Logically marks reachable young objects; copies to destination.
                │
                ▼

AFTER YOUNG GC (illustrative diagram)

Eden:        [empty / available for reallocation]
Survivor S0: [empty / ready for another cycle]
Survivor S1: [A][B][C]  (if it fits, not yet promoted)
Old:         [some objects promoted if needed]
```

In reality, the copy order and survivor ages depend on references, sizes, allocation, and policy. The diagram is only meant to explain that **copying retains live objects and discards garbage in the source region**; not every illustrated object is copied exactly once in A-B-C order.

### Why is young copying efficient when many objects die early?

Suppose there are 10,000 young objects, but only 150 objects need to be kept alive. A copying scavenger can focus its moving work on the **live objects** instead of having to copy all 10,000 objects. Of course, the collector still needs to scan appropriate roots/references/metadata; do not conclude that total GC cost is strictly equal to the number of bytes of live objects.

**The benefit** is that the source region can be reused quickly; the destination region receives live objects contiguously, helping reduce fragmentation in the young generation.

### GC roots and old-to-young references

Stack locals and static fields are not the only things keeping young objects alive. An old-generation object can have a field pointing to a young object:

```text
Old object ─────────► Young object
```

Young GC must account for these **cross-generation references**; HotSpot has a card table/remembered information mechanism and write barriers to assist tracking, avoiding having to scan the entire old generation on every young collection.

If an old-to-young edge is missed, GC could mistakenly reclaim a young object that is still reachable. Therefore, **root scanning + appropriate incoming reference sources** is a correctness requirement, not just “traversing only Eden”.

### Survivor spaces are not two permanently existing copies

The two survivor spaces typically alternate roles as **from** and **to** across young collections. A live object can be copied along the appropriate path or promoted, rather than always storing two copies of the object simultaneously from the program's perspective.

Application Java references must be properly updated/maintained by the VM after an object moves. Object identity (`==`, `System.identityHashCode` semantics) does not turn into a different Java object because of a physical move.

## 5. Old Generation: Mark-Compact Differs from Young Copying

When an old-generation/full collection occurs, HotSpot Serial Old performs **mark-compact** work, typically described through:

1. **Mark:** find the objects that need to be kept alive starting from roots and meaningful reference paths.
2. **Compute post-compaction locations:** determine where live objects will be relocated.
3. **Compact/move:** slide live objects together to consolidate free space into regions favorable for allocation.
4. **Update references:** ensure live references still point to the right objects after relocation.

```text
Old before GC:
[A live][gap][B live][gap][C live][gap][gap]

Old after mark-compact (illustrative):
[A live][B live][C live][     free space     ]
```

Unlike the young scavenger which mainly copies between source/destination regions, old mark-compact must handle live objects and fragmentation within the old generation. **This is work that can take more time when the live set is large**, especially because Serial uses a single GC worker during a stop-the-world pause.

**Do not assume that every normal GC always runs old compaction.** Young GC occurs more frequently; old/full collection requires appropriate conditions. A Full GC can involve multiple regions/generations and have multiple triggers, depending on the HotSpot version/policy.

### Mark-compact is not the same as simple mark-sweep

- **Mark-sweep:** marks live objects and then reclaims free space, which can leave scattered holes.
- **Mark-compact:** marks and then **compacts objects** to reduce fragmentation.
- **Copying:** moves live objects to a destination region and reuses the source region.

In the traditional HotSpot Serial GC model, **young copying and old mark-compact** have different meanings. Do not generalize by saying “Serial GC only deletes dead objects in place.”

## 6. Stop-the-World: Why Does Serial GC Have Pauses?

When Serial GC runs its collection phases, application threads must be **stopped** so the collector can safely observe/move objects. This process creates a **GC pause**, which counts toward application latency.

```text
Illustrative timeline

App:  ██████████░░░░██████████████░░░░████████
GC:             [YOUNG]                [FULL]
                STW                    STW
```

In the figure, `░` represents the interval where the application is paused due to GC, not an actual millisecond measurement. Because Serial uses one GC worker, the same heap may take longer than a parallel collector if the amount of GC work is large, but **the exact difference cannot be quantified without benchmarking the same workload**.

### Pause time and throughput are not synonymous

- **Pause time:** the duration of a single period during which the application must wait for GC.
- **Throughput:** the ratio of time/capacity spent doing application work compared to GC overhead and other costs.
- **Latency p95/p99:** tail latency of requests; particularly sensitive to large pauses.
- **Footprint:** memory and CPU resources the collector and JVM need to operate.
- **Warm-up:** the time the VM/JIT takes to optimize the application after startup.

Serial can reduce coordination overhead compared to multi-worker collectors, helping small workloads run efficiently; however, when the heap is large, the live set is dense, or a service requires tight latency, **single-worker STW** is usually a disadvantage.

### Serial GC does not provide “main concurrent marking” like a low-pause collector

Targeting low pause times, some other collectors perform GC phases **concurrently with application threads**, or parallelize STW work. Serial GC does not have this characteristic as its focus; you should not choose Serial and expect it to meet a requirement of “pauses of a few milliseconds for a multi-GB heap.”

## 7. Why Does Serial GC Suit Resource-Constrained Machines?

HotSpot JDK 17 documentation describes the Serial collector as using a single GC thread, with no communication overhead between workers. It is suitable for **single-processor machines** and can be useful on multiprocessors with **small data sets**; the documentation suggests a benchmark of around **100 MB** for small data sets as a guideline, **not a hard limit or correctness threshold**.

### Scenarios where it can be considered

| Environment | Why it may fit | What to check |
| --- | --- | --- |
| Small command-line utility | Short-lived, small heap, no pause guarantee needed | Startup, peak heap, and total time |
| Small batch job | Not directly exposed to user request latency | Total time and longest pause |
| Container/VM limited to ~1 CPU | Few CPUs to utilize multiple GC workers | CPU quota, throttling, heap live set |
| Relatively simple embedded device/app | Prioritizes footprint and low coordination overhead | Actual Java runtime/vendor support |
| Small object graph workload | Little live data to scan/copy/compact | Live bytes after GC, allocation rate |
| Learning/investigating GC | Easy-to-observe and compare mechanism | Distinguish learning goals from production tuning |

**“Low resources” does not mean every container should use Serial.** A small container running a latency-critical API may not tolerate STW pauses; a CPU-limited container may still have other collectors that fit better depending on needs. Measure **heap after GC**, **pauses**, **throughput**, and **native memory** under realistic load.

### When is Serial usually not a good choice?

- Interactive services needing **low p99 latency** and consistent responsiveness.
- Large heap/live set where old-generation collection takes a long time.
- Servers with many CPU cores where GC is expected to use parallelism to shorten pauses.
- High allocation rate causing young collections to happen too frequently.
- Long-running workloads continuously updating large object graphs.
- Modern JVMs/concurrent collectors whose target performance has already been proven by benchmarks.

These are **signals to verify**, not a hard rule that “at 101 MB heap, Serial is wrong.” A choice must be based on workload and SLO, not just core/heap numbers.

## 8. Comparing Serial, Parallel, G1, and Low-Pause Collectors

| Aspect | Serial GC | Parallel GC | G1 GC | ZGC/Shenandoah (when supported) |
| --- | --- | --- | --- | --- |
| GC workers in main STW collection | One | Multiple | Has multiple workers for some phases | Depends on design |
| Concurrent work with application | Not a primary characteristic | Not a primary characteristic | Has concurrent marking | Designed for extensive concurrent work |
| Target group | Small heap / low CPU / simplicity | Throughput, multiprocessor | Balance of throughput and pause targets | Low latency with specific trade-offs |
| GC coordination overhead | Relatively low | Coordinates multiple workers | Has more metadata/phases | Has barriers/concurrent metadata/threads |
| Pause | Can be long when live set is large | Can reduce work time via parallelism | Aims for pause goals via policy | Aims to reduce pauses via concurrent work |
| Typical HotSpot configuration | `-XX:+UseSerialGC` | `-XX:+UseParallelGC` | `-XX:+UseG1GC` | `-XX:+UseZGC`, or specific flags |

The table **describes trends**, not a guarantee that every collection will be faster/slower by a certain number of ms. In particular, ZGC and Shenandoah configurations vary by JDK vendor/release; consult the documentation for the exact runtime.

### Serial vs. Parallel GC

Both can use a generational model. The notable difference is that **Parallel GC uses multiple GC workers** to process collection work and generally suits workloads utilizing multiple cores to improve throughput. Serial reduces coordination overhead but does not benefit from multiple workers when the heap is large.

### Serial vs. G1

G1 is designed around regions and concurrent marking combined with STW phases, setting pause-time goals using heuristics. Serial is simpler but lacks G1-style pause-goal optimization mechanisms. **Having G1 does not mean zero pauses**; GC logs and benchmarks still need to be observed.

### Serial vs. ZGC/Shenandoah

Low-pause collectors perform significant concurrent work, use additional barriers/metadata, and have different trade-offs. **Do not conclude they are always better than Serial** on a few-second command-line job with a small heap; compare startup, throughput, native overhead, and resource limits before choosing.

## 9. Enabling Serial GC and Verifying with Flags

Java 17 HotSpot syntax:

```bash
javac -encoding UTF-8 SerialGcDemo.java
java -XX:+UseSerialGC SerialGcDemo
```

The complete `SerialGcDemo.java` file is provided in section 12. If the file has not been created yet, `javac` cannot run; create the exact file first.

### Verifying the selected collector

```bash
java -XX:+UseSerialGC -Xlog:gc=info -version
```

On HotSpot JDK 17, GC logging may produce a message similar to:

```text
[info][gc] Using Serial
```

This is a **sample**, not exact stdout: timestamps/log decorators and wording depend on the version. `java -version` typically writes version info to stderr; do not confuse GC logging with application output.

Another way to inspect flags:

```bash
java -XX:+UseSerialGC -XX:+PrintFlagsFinal -version
```

Filter flags such as `UseSerialGC`, `UseParallelGC`, `UseG1GC`, `MaxHeapSize`, `NewSize`, `MaxNewSize`. Defaults may depend on core count, heap limit, container awareness, and JDK vendor.

**Do not infer from hardware that the collector is definitely Serial.** HotSpot has ergonomics and may automatically choose another collector on multi-core machines; startup flags verify better than guessing.

## 10. Heap Sizing: `-Xms`, `-Xmx`, and Generation Configuration

Options commonly needing understanding:

| Option | Purpose | Notes |
| --- | --- | --- |
| `-Xms<size>` | Initial Java heap size | Affects heap initialized/committed by VM |
| `-Xmx<size>` | Maximum Java heap size | Does not limit total process RSS/native memory |
| `-Xmn<size>` | Sets young generation size per supported option | May alter sizing policy behavior |
| `-XX:NewRatio=n` | Old/young ratio per relevant HotSpot rules | Effect depends on sizing constraints |
| `-XX:SurvivorRatio=n` | Adjusts Eden-to-survivor sizing appropriately | Does not guarantee fixed survivor occupancy ratios every time |
| `-XX:MaxTenuringThreshold=n` | Limits tenuring age per policy | May promote early due to survivor pressure |
| `-XX:+UseSerialGC` | Selects the Serial collector | Does not imply a small heap |

**Principle:** start with reasonable sizing for the workload; **avoid tuning a slew of generation/survivor flags** before having metrics. The JVM can choose more reasonable sizes automatically than a set of values copied from another application.

### Young too small

If Eden is too small relative to the allocation rate, young collections can happen many times:

```text
Fast app allocation
  → Eden fills up frequently
  → Continuous Young GC STW
  → cumulative pause overhead increases
```

Increasing the young generation can reduce frequency, but young GCs may process more live data and require a trade-off with old generation capacity.

### Old too small or live set too large

If long-lived objects grow, the old generation may lack capacity and cause frequent old/full collections. One worker mark-compacting a large amount of live data can create **long pauses**. Increasing `-Xmx` does not fix a memory leak by itself: if root paths keep retaining unboundedly growing data, a larger heap only delays OOME.

### Heap vs. entire process

Serial GC may have a lower management footprint than some collectors, but the process still includes:

```text
Process memory
  = Java heap
  + Metaspace/class metadata
  + Code Cache/JIT
  + thread stacks
  + direct/native buffers
  + GC/VM structures and libraries
```

This is a **categorization**, not an exact RSS calculation formula. A 256 MB container should not be configured with `-Xmx256m` assuming the JVM still has enough room for all native allocations. Actual OS/container limits must be accounted for.

## 11. STW Mechanism and Metrics to Measure

To decide whether Serial GC is suitable, gather metrics instead of just looking at flags.

| Metric | Why it matters |
| --- | --- |
| **Young GC count/time** | Frequency and total pause time caused by young collection |
| **Full GC count/time** | Is there a continuous old generation/full collection issue? |
| **Max/p95/p99 pause duration** | Impact on user-facing latency or deadlines |
| **Heap used after GC** | Is the live set growing steadily across multiple cycles? |
| **Allocation rate** | Is Eden being filled too quickly? |
| **Promoted bytes/tenuring** | How many long-lived objects are being moved to old? |
| **Throughput/job completion time** | Is GC overhead significant relative to total work? |
| **CPU quota/throttling** | Is low CPU the cause of performance issues? |
| **Container memory/RSS** | Is there enough budget for heap and native allocations? |

A single `System.gc()` cannot replace a real workload benchmark: it may trigger a Full GC in some configurations but does not represent normal automatic young collection cycles.

### Percentiles are more reliable than an average number

Suppose most requests take 10 ms, but a few requests suffer a 250 ms pause. Average latency may still look quite fine while p99 is bad. Serial GC on an appropriate workload may be acceptable; however, a service with a 50 ms SLO needs careful pause tail analysis.

**Do not assert that Serial pauses are always >50 ms or <10 ms.** Pauses depend on heap, live data, references, CPU, workload, and JVM. Always measure on the deployment target.

## 12. Java 17+ Lab: An Allocation Program to Observe Serial GC

Create a single file **`SerialGcDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SerialGcDemo {
    private static volatile Object sink;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 600; i++) {
            byte[] block = new byte[128 * 1024];
            block[0] = (byte) (i % 100);

            checksum += block[0] & 0xffL;

            // A few arrays are kept alive across multiple iterations.
            if (i % 100 == 0) {
                survivors.add(block);
            }

            // Publication causes each block to actually escape;
            // independent of whether the compiler keeps or eliminates local allocation.
            sink = block;
        }

        System.out.println("checksum: " + checksum);
        System.out.println("survivors: " + survivors.size());
        System.out.println("one survivor bytes: "
                + survivors.get(0).length);
        System.out.println("done");
    }
}
```

### Compile and run

```bash
javac -encoding UTF-8 SerialGcDemo.java
java -XX:+UseSerialGC -Xms32m -Xmx32m SerialGcDemo
```

**Program standard output, when GC logging is not enabled:**

```text
checksum: 29700
survivors: 6
one survivor bytes: 131072
done
```

Explanation of values:

- The loop runs 600 times, with each `block` being **128 × 1024 = 131072 bytes** long.
- The first element receives values 0–99, repeating for 6 cycles. The sum `0 + 1 + ... + 99 = 4950`, so `checksum = 6 × 4950 = 29700`.
- The list retains the block at `i=0,100,200,300,400,500`, so there are exactly **6 survivors** at the application logic level.
- `sink` is a `volatile` field assigned sequentially to each block; it helps prevent the compiler from optimizing away the entire allocation path in the demo, while keeping the latest block live via a reference. However, GC/JIT still have other runtime decisions; the number of GC cycles is non-deterministic.
- Total temporary bytes requested for allocation exceed 32 MiB over the entire run, so the JVM will have to reuse memory via appropriate mechanisms. **Do not guess the young/full GC count** without reading the logs.
- In the Java source, `survivors` is a list holding references; it does not prove that exactly 6 blocks must be promoted to the old generation under a specific tenuring threshold.

**Do not add `System.gc()` to “guarantee” logging a number of young GCs**: manual Full GC changes what is being observed, whereas the goal here is **automatic GC under allocation pressure**.

### Enable GC logging

```bash
java -XX:+UseSerialGC -Xms32m -Xmx32m -Xlog:gc*:info SerialGcDemo
```

When logging is enabled, the four Java output lines above are still what the code produces, but the console will have **interleaved GC log lines**. The count, timing, duration, occupancy, and wording of those log lines depend on the VM and machine.

Example log format might look like:

```text
[info][gc] Using Serial
[info][gc,start] GC(...) Pause Young (Allocation Failure)
[info][gc,heap] ... DefNew: ... -> ...
[info][gc] GC(...) Pause Young (Allocation Failure) ...ms
```

This is an **illustrative description**, not exact stdout and not a mandatory template for every HotSpot release. The `...` represents non-fixed data. With a HotSpot 17 Serial build, you may see different region names/log labels such as `DefNew` and `Tenured`; rely on actual logs.

### Observing Full GC

If the workload or heap policy triggers a Full GC, you may see lines in the `Pause Full` or `Full GC` group depending on JVM/log configuration. A Full GC will not necessarily occur in a lab run that has enough heap for live objects; **do not call `System.gc()` and present it as the default result of automatic old collection**.

## 13. Observing Serial GC with GC Logs

Unified logging on HotSpot JDK 17 can accept additional tags:

```bash
java -XX:+UseSerialGC -Xms32m -Xmx32m -Xlog:gc*,safepoint=info SerialGcDemo
```

For production work, configure appropriate log files and log rotation. Simple console experiments are only meant for learning how to read events.

### How to read a GC event

When the log displays a pause:

- **GC ID:** helps group lines belonging to the same collection cycle.
- **Cause:** e.g., `Allocation Failure` when unable to allocate from the appropriate region.
- **Type:** Young or Full per the collector message.
- **Before → after:** change in heap/generation occupancy.
- **Duration:** event duration; read the actual unit in the log.
- **Generation details:** can help inspect Eden/Survivor/Old occupancy and promotions.
- **Safepoint timing:** part of the cost of stopping threads/safepoints, when relevant logging is enabled.

**Do not mix up metrics:** the time in a young GC line is not synonymous with full end-to-end response latency, though STW pauses can contribute directly to latency. Allocation failure is a common GC cause name, **not automatically synonymous with OutOfMemoryError**.

### Parsing example

```text
Pause Young ... 24M->5M(32M) 4.7ms
```

This is a **hypothetical number for reading practice**, not a measured log. It indicates that in a reported event, some measure of occupied heap changed from 24 MiB down to 5 MiB out of a 32 MiB capacity, with a duration of 4.7 ms in the reporting context. You cannot deduce that 19 MiB of a specific class alone was reclaimed; to know the object graph, you must use a profiler/heap dump.

## 14. Using the Java Management API to Inspect Collectors

Alongside GC logs, Java SE provides `java.lang.management.GarbageCollectorMXBean`. Create the file **`GcBeanDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class GcBeanDemo {
    public static void main(String[] args) {
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("collector: " + bean.getName());
            System.out.println("count: " + bean.getCollectionCount());
            System.out.println("time(ms): " + bean.getCollectionTime());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 GcBeanDemo.java
java -XX:+UseSerialGC GcBeanDemo
```

**Output depends on implementation:** with the HotSpot Serial collector, names may be **`Copy`** and **`MarkSweepCompact`**; collection counts and times depend on the workload. Do not fabricate a fixed set of stdout numbers. A bean may return `-1` for an unsupported metric.

**Meaning:**

- `getName()` reflects the collector name exposed by the JVM via the management API.
- `getCollectionCount()` and `getCollectionTime()` are metrics at the time of querying.
- These two metrics do not tell which specific objects were reclaimed or how many reference paths changed.
- Non-HotSpot JVMs may expose different bean names; bean names are not a portable Serial GC identifier standard.

### Comparing with Parallel/G1 using the same program

You can run:

```bash
java -XX:+UseSerialGC -Xms32m -Xmx32m -Xlog:gc=info SerialGcDemo
java -XX:+UseParallelGC -Xms32m -Xmx32m -Xlog:gc=info SerialGcDemo
java -XX:+UseG1GC -Xms32m -Xmx32m -Xlog:gc=info SerialGcDemo
```

**Use only if the JVM and heap sizes support it.** With small heaps, startup options and minimum region constraints of each collector may differ; if a run rejects the flags, record that as an invalid configuration result rather than forcing a comparison.

A small demo program may not reveal the advantages of strong multi-core collectors. A serious comparison must use a **production-like workload**, multiple measurements, after proper warm-up, with the same CPU/memory limits and JVM version.

## 15. Java Flight Recorder, jcmd, and External Monitoring

### Identifying the JVM process

```bash
jcmd -l
```

Once you have the PID of the running Java process:

```bash
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
```

Replace **`PID` with the actual process ID**. `jcmd PID help` verifies commands supported by the build/runtime. Tools like heap histogram may require a safepoint and cause overhead/pauses; do not use them arbitrarily in sensitive environments.

`GC.heap_info` usually helps view the current heap layout. `VM.flags` helps verify the actual collector flag, heap size, and related options.

### Java Flight Recorder

JFR can record GC events and allocation/pause statistics of the corresponding process. It can be useful when correlating GC pauses with application latency. However, recording features/configuration, sampling, and event names depend on the JDK version and profile.

Do not compare a measurement in JFR with `System.currentTimeMillis()` output and conclude a causal relationship without synchronizing time and checking event boundaries.

### Native memory and container limits

Serial GC reduces overhead associated with multiple GC workers, but **does not guarantee a very small process memory footprint**. JIT code cache, class metadata, thread stacks, direct buffers, and other native regions still exist. In containers, monitor **process RSS/container memory**, not just `MemoryMXBean.getHeapMemoryUsage().getUsed()`.

## 16. Common Errors/Diagnostics with Serial GC

| Symptom | Hypothesis to check | Investigation direction |
| --- | --- | --- |
| Young GC too frequent | Eden too small, high allocation rate, many short-lived objects | GC logs, allocation profiling, heap sizing |
| Repeated Full GC | Growing live set/old occupancy, promotion pressure, fragmentation, or heap limit | After-GC occupancy, root paths, sizing |
| Prolonged GC pauses | Single GC worker handling many live objects, large old compaction, slow CPU | Max pause, live bytes, CPU quota |
| Poor throughput on multi-core machine | Serial does not parallelize GC work | Try Parallel/G1 with equivalent load |
| `OutOfMemoryError: Java heap space` | Live set too large or allocation needs exceed heap | Heap dump, leak analysis, actual `-Xmx` |
| High RSS despite small heap | Native memory/code cache/metaspace/thread stacks | Process metrics, NMT when supported |
| GC logs do not show Serial | JVM not run with right flag, different JVM, or incorrect command line | `java --version`, `VM.flags`, startup logs |
| Container throttled | CPU quota/scheduling starves both app and GC of CPU | cgroup metrics, CPU profiles, observed pauses |
| `System.gc()` causes Full pause | Explicit request and collector policy | Check GC cause; do not confuse with automatic workload |
| No Full GC seen in demo | Old generation has not needed collection yet | Do not conclude Serial Old does not exist |

### Does GC fix memory leaks?

Not when there are **unintentional strong references**. For example, a static `List<Object>` holding 100,000 items that the application never removes; a correct tracing collector must retain those reachable objects. Increasing the heap only delays the problem; **the unneeded retention path must be removed** or the cache bounded.

### Are long pauses always caused by GC?

No. The JVM also has lock contention, class loading, JIT compilation, I/O, thread scheduling, safepoint operations, and OS throttling. Correlate event timestamps in GC logs/JFR with request traces before asserting the cause.

## 17. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Serial GC means the Java app runs only one thread.” | GC worker is one; mutators can still be multi-threaded |
| “Serial does not pause the application.” | Serial's traditional collection mechanism is STW |
| “Serial GC is always slow.” | Small workloads may benefit from low overhead; must measure |
| “On an 8-core machine, Serial automatically runs GC on all 8.” | No; Parallel GC uses multiple workers for GC work |
| “Serial only has one heap generation.” | Has young/old following the traditional generational model |
| “Young GC only deletes objects, without copying.” | Serial young is a copying scavenger |
| “Old GC only mark-sweeps leaving holes.” | Serial Old uses mark-compact |
| “Every object is promoted after exactly 15 young collections.” | Threshold/promotion policy can vary and promote earlier |
| “GC is the job of a normal Java application thread.” | VM GC worker and mutators have different roles |
| “A young GC only needs to scan young roots.” | Must consider incoming references from old and root metadata |
| “Serial is never suitable on multi-core machines.” | May fit when data set is small; does not utilize multiple cores for GC work |
| “Heap under 100 MB must use Serial.” | A guideline benchmark, not a mandatory limit/configuration |
| “Full GC always runs after every young GC.” | No; old/full collection depends on conditions |
| “Enabling Serial makes memory leaks disappear on their own.” | As long as root paths retain objects, the collector must keep them |
| “`System.gc()` guarantees all garbage is deleted immediately.” | A limited hint; do not use it to test GC behavior |
| “`-Xmx` is the limit for the entire process.” | It limits the Java heap, excluding all native memory |
| “One young pause log tells the exact p99 latency.” | Must correlate with request metrics and event timestamps |
| “Need to optimize `-Xmn`/tenuring before measuring.” | Prioritize baseline and metrics, avoid arbitrary tuning |

## 18. Self-Check Exercises (with Answers)

**Exercise 1.** How many GC workers does Serial GC have for a main collection?  
**Answer:** One. This does not prevent the application from having multiple Java threads.

**Exercise 2.** What regions does Serial GC's young generation typically consist of?  
**Answer:** Eden and two survivor spaces; survivors alternate source/destination roles according to collection rules.

**Exercise 3.** When can an object move to the old generation?  
**Answer:** When surviving across collections per policy or when survivor space is unsuitable/lacks room, depending on thresholds and VM state; there is no fixed count applying to every configuration.

**Exercise 4.** Why can a copying young collector be efficient?  
**Answer:** When most young objects are dead, only the appropriate live objects need to be moved, while reusing the source region quickly.

**Exercise 5.** Must two objects pointing to each other with no path from GC roots stay alive forever?  
**Answer:** No. Tracing GC can reclaim unreachable cycles.

**Exercise 6.** Which algorithm does Serial Old typically apply in traditional HotSpot?  
**Answer:** Mark-compact, which helps reduce fragmentation by compacting live objects.

**Exercise 7.** When Serial young GC runs, do Java threads still execute application code concurrently with the collection?  
**Answer:** During an STW pause, mutators are paused; the JVM GC worker performs collection according to the collector mechanism.

**Exercise 8.** Why can Serial be suitable for a 1-CPU environment?  
**Answer:** A single GC worker avoids the overhead of coordinating multiple workers that could not run effectively in parallel on limited CPU. Pauses/heap should still be measured.

**Exercise 9.** A service needs p99 latency < 20 ms with a large heap; should Serial be chosen just because it is “simple”?  
**Answer:** Not by default. Single-worker Serial STW may not meet it; other collectors must be benchmarked against the SLO.

**Exercise 10.** Is `-XX:+UseSerialGC` a Java SE standard across all JVMs?  
**Answer:** No. It is a HotSpot option and must be verified on the actual runtime.

**Exercise 11.** In `SerialGcDemo`, why is `checksum` 29700?  
**Answer:** 600 iterations consist of six 0..99 cycles; each cycle sums to 4950.

**Exercise 12.** If GC logs show `Allocation Failure`, is the JVM guaranteed to throw `OutOfMemoryError`?  
**Answer:** No. This can be a normal GC cause when a region cannot allocate further before a collection.

**Exercise 13.** Does `-Xmx32m` prove the process is under 32 MB RSS?  
**Answer:** No; there are still metaspace, code cache, stacks, and other native allocations.

**Exercise 14.** Can Serial's Young GC ignore old-to-young references?  
**Answer:** No; appropriate incoming references must be considered so live objects are not mistakenly reclaimed.

**Exercise 15.** Old generation used keeps increasing after multiple collections; what should be done?  
**Answer:** Inspect live set, retained size/Paths to GC Roots, queues/caches, allocation/promotions, and heap sizing; do not repeatedly call explicit GC to mask a leak.

**Exercise 16.** Does enabling `-XX:+UseSerialGC` guarantee the fastest startup for every app?  
**Answer:** No; JIT, class loading, memory, I/O, and other workloads still dominate. Only benchmarking can conclude.

**Exercise 17.** Why should `System.gc()` not be inserted into a workload to test young GC?  
**Answer:** An explicit request can trigger a Full GC unlike an automatic workload, skewing the observation away from its goal.

**Exercise 18.** At its core, how does Parallel GC differ from Serial?  
**Answer:** It uses multiple GC worker threads to collect, utilizing multiprocessor hardware; coordination/footprint trade-offs differ.

## 19. Checklist Before Putting Serial GC into Production

- [ ] Confirmed the **JVM vendor/release** and that the `UseSerialGC` flag actually takes effect.
- [ ] Identified the **CPU quota** and container memory limit the application is subject to.
- [ ] Measured **live heap after GC**, allocation rate, and peak heap.
- [ ] Observed young/full GC **count, cause, duration**.
- [ ] Checked **p95/p99 latency** or batch job completion time.
- [ ] Estimated **native memory budget** outside `-Xmx`.
- [ ] Compared Serial against at least one suitable baseline collector on the same workload.
- [ ] Avoided complex sizing flags without supporting evidence.
- [ ] Verified root paths if the heap live set grows abnormally.
- [ ] Have the ability to rollback/restart after changing JVM flags.
- [ ] Do not treat “single-threaded” as synonymous with “uses no CPU”.
- [ ] Do not predict GC cycle counts from demo source code.
- [ ] Monitored both throughput and pause time; not just average.
- [ ] Evaluated application data/threads during peak hours.

## 20. Summary

**Serial GC** is a **generational, stop-the-world, single-worker** collector in HotSpot: young-generation collection mainly uses **copying**, while old-generation collection traditionally uses **mark-compact**. It reduces GC worker coordination overhead and is easy to understand, making it suitable for **small heaps, simplicity, low CPU, and short batch/CLI jobs**; in return, when the amount of live data is large, GC has only one worker and application threads must wait for collection to finish.

Do not choose Serial just because the configuration is small, nor rule it out just because the machine has many cores. **Evaluate using real workloads, heap live set, GC pauses, CPU/memory budget, throughput, and latency SLOs.**

### Official References

- **Oracle JDK 17 — HotSpot Garbage Collection Tuning Guide, Available Collectors** (Serial/Parallel/G1/ZGC and collector selection context): https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- **Oracle JDK 17 — The java Command** (flags `-XX:+UseSerialGC`, `-Xms`, `-Xmx`, and GC options): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle JDK 17 — HotSpot GC Tuning Guide** (generation concepts, sizing, collector ergonomics): https://docs.oracle.com/en/java/javase/17/gctuning/
- **Oracle JDK 17 — jcmd** (reading VM flags, heap info, and practical commands): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Java SE 17 — GarbageCollectorMXBean** (management API collection count/time): https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html

Information about Serial GC here applies to the **HotSpot JVM verified on JDK 17 and related generational principles**. Other JVMs such as GraalVM Native Image may have a “Serial GC” but **do not necessarily share the same implementation/flags/heap layout**, so do not apply HotSpot conclusions without consulting their specific documentation.

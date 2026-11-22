# Young Collection in Java Garbage Collection

## 1. What Is a Young Collection?

A **young collection** is a garbage collection cycle focused on the memory area for newly created objects (the young generation). In generational garbage collectors, most objects are short-lived: requests, iterators, DTOs, temporary buffers, intermediate strings, and objects serving a single computation typically become unreferenced after a short period.

HotSpot exploits this characteristic through the weak generational hypothesis: most objects die young. Instead of scanning the entire heap on every collection, the collector can collect the young generation more frequently, process surviving objects, and reclaim the space occupied by objects whose lifetime has ended.

In traditional terminology, a young generation collection is often called a **minor GC**. G1 typically logs it as `Pause Young`, while Generational ZGC may log `Minor Collection`. The exact naming and mechanics depend on the collector and JDK version.

A young collection usually costs less than a full-heap collection because the number of surviving objects in the collected area is typically small. However, a young collection can still take significant time if many objects survive, many objects must be copied, many references need to be scanned, or the system is CPU-constrained.

## 2. Why Does the JVM Divide the Heap into Generations?

A Java object is considered eligible for collection when there is no longer any strong reference path from the GC roots to that object. If every GC had to inspect every live object in the entire heap, an application with a large live set would spend considerable time in GC.

Generational GC classifies objects by age:

- **Young generation:** where most new objects are allocated. Short-lived objects are typically reclaimed here.
- **Old generation:** where objects that survive multiple young collections or are promoted early according to the collector's policy are kept.

The goal is to concentrate collection work in the area with the highest garbage ratio. A young collection usually only processes a portion of the heap, so its duration correlates more closely with the amount of surviving objects to retain/copy than with the total bytes allocated beforehand.

Not all objects have the same lifetime. Caches, sessions, queues, static collections, or objects tied to long-running requests can live long and get promoted. If the application retains too many objects, young collections will continue to run regularly while the old generation steadily grows.

## 3. Eden, Survivor, and Old Generation

In classic generational collectors such as Serial and Parallel, the young generation typically consists of:

- **Eden:** where most new objects are allocated. The JVM usually performs fast allocation via Thread-Local Allocation Buffers (TLABs) to reduce contention between threads.
- **Survivor From:** the area holding objects that survived the most recent young collection.
- **Survivor To:** the destination area for copying surviving objects from Eden and Survivor From during the next collection.
- **Old/Tenured:** the area holding objects that have lived long enough or been promoted.

The two survivor spaces alternate roles between From and To. After a young collection, Eden and the source survivor space are emptied; surviving objects are copied to the destination survivor space or the old generation.

G1 uses heap regions instead of three fixed contiguous areas. A region can be assigned the role of Eden, Survivor, or Old; regions belonging to the same generation do not necessarily sit adjacent to one another in heap address space. Therefore, when reading G1 logs, look at region counts and region states rather than assuming the heap has three contiguous address ranges.

## 4. How Does a Young Collection Work?

For a copying/evacuating collector, the general process consists of the following steps:

1. The JVM pauses or synchronizes application threads according to the collector's mechanism.
2. The collector identifies live objects in the area to be collected by traversing GC roots and relevant references.
3. Unreachable objects are treated as garbage; their memory space can be reused.
4. Surviving objects are copied to Survivor or Old based on age, capacity, and tenuring policy.
5. References are updated to point to the new locations of the objects.
6. Eden and the previous source Survivor space are reused for subsequent allocations.

With Serial and Parallel young collections, the application is typically paused throughout the collection phase; Parallel uses multiple GC workers to process in parallel. G1 also performs stop-the-world evacuation young pauses. Generational ZGC performs most of the time-consuming work concurrently with the application and only pauses threads during brief necessary pauses.

A young collection does not mean every object in the heap is scanned. The collector must handle references from areas outside the collection set pointing to young objects; this is why generational collectors use a card table, remembered set, or an equivalent mechanism.

## 5. Object Aging and Promotion

Objects that survive a young collection have their age incremented. Depending on the collector, an object may be copied across Survivor spaces multiple times before being promoted to Old.

Factors affecting promotion:

- The object's age has reached the current tenuring threshold.
- The Survivor space no longer has enough room for the surviving objects.
- The collector chooses a lower age threshold to keep Survivor at its target utilization.
- Collector-specific policies for large objects or special allocations.

In HotSpot, `MaxTenuringThreshold` is the configured maximum age limit, but the actual threshold may be lower because the JVM adjusts it dynamically based on survival data and Survivor capacity. Therefore, you should not assume every object must survive exactly 15 GC cycles before being promoted.

A promoted object increases the data volume in the Old generation. If more objects are retained longer than expected, the promotion rate increases and the old generation can fill up faster.

### Lifetime Example

| Collection | Object A | Object B |
|---|---|---|
| Allocation | A and B are created in Eden | A and B are created in Eden |
| Young collection 1 | A is still referenced so it survives | B is no longer referenced so it is collected |
| Young collection 2 | A continues to live and ages | B no longer exists |
| Next young collection | A may remain in Survivor or be promoted | — |

This table illustrates the general idea. Exact ages, promotion timing, and how objects are stored depend on the collector, configuration, and actual workload.

## 6. Remembered Set and Old-to-Young References

An old object can hold a reference to a young object. If a young collection only inspected references from thread stacks and objects within the young generation, a young object referenced by an Old object could be mistakenly collected.

The collector needs to know which locations outside the collected area hold references pointing into it. Common mechanisms include:

- **Card table:** divides the heap into small cards and marks cards that may contain references needing inspection.
- **Remembered set:** stores information about locations outside the collection set that hold references pointing into the managed region.
- **Write barrier:** code inserted by the JVM into reference write operations to maintain metadata for GC.

In G1, the remembered set helps identify references from regions outside the collection set into the regions being collected. G1 uses cards to represent reference locations; by default, a card is 512 bytes in the JDK 24 documentation. This metadata helps the collector avoid scanning the entire old generation on every young collection.

Processing remembered sets and scanning heap roots also take time. When a young pause is long, inspect the phase breakdown instead of looking only at total duration.

## 7. Distinguishing Young Collection, Mixed Collection, and Full GC

These three concepts are often confused:

| Type | Primary Scope | Meaning |
|---|---|---|
| Young collection | Young generation | Collects Eden/Survivor or the corresponding young area |
| G1 Mixed collection | Young regions and selected Old regions | Collects young regions while reclaiming part of the Old generation |
| Full GC | Entire heap | Collects/compacts a broader heap scope; usually an event to investigate when pauses are long |

In G1, the **Young-Only phase** consists of normal young collections. When old occupancy reaches the threshold to start marking, G1 can run a **Concurrent Start young collection**: this pause both performs a young collection and initiates concurrent marking for the Old generation.

After marking, G1 can enter the **Space-Reclamation phase**. During this phase, **Mixed collections** collect young regions plus some Old regions selected for good reclamation efficiency. A Mixed collection still includes a young collection; the name Mixed does not mean Full GC.

The term **major GC** is used inconsistently across documentation and collectors. Do not automatically equate every major collection with a Full GC or infer scope from the name alone. Check the logs for the specific collector and JDK in use.

## 8. How Young Collection Differs Across Collectors

Young collection does not have the same log names or implementation across all collectors.

| Collector | Young collection representation | Key characteristics |
|---|---|---|
| Serial GC | Typically `Pause Young (Allocation Failure)` and `DefNew` | Collects with a single GC thread; application threads pause during collection |
| Parallel GC | Typically `Pause Young (Allocation Failure)` and `PSYoungGen` | Uses multiple GC workers for the young generation |
| G1 GC | `Pause Young (Normal)` or other young pause types | Region-based; has Young-Only and Mixed collections; evacuation pauses are stop-the-world |
| Generational ZGC | May show `Minor Collection` and `Young Generation` in logs | As of JDK 24, ZGC is generational; most GC work runs concurrently with very short pauses |

On JDK 24, G1 is HotSpot's default collector. ZGC is also a generational collector; the `-XX:+ZGenerational` option was removed as generational mode became ZGC's default.

Log labels such as `DefNew`, `PSYoungGen`, `Pause Young`, or `Minor Collection` are indicators of a specific collector. Do not write scripts or dashboards assuming every JVM uses the same event name.

## 9. Enabling Unified GC Logging to Observe Young Collections

Unified Logging is the standard way on modern JDKs to observe GC activity.

Basic GC logging:

~~~bash
java -Xlog:gc -jar application.jar
~~~

Detailed logging of GC tags and age traces to a rotating file:

~~~bash
java \
  -Xlog:gc*,gc+age=trace:file=gc.log:uptime,level,tags:filecount=5,filesize=20M \
  -jar application.jar
~~~

Meaning:

- `gc*` enables logs with tags starting with `gc`.
- `gc+age=trace` logs object age details and tenuring thresholds.
- `file=gc.log` writes logs to a file.
- `uptime,level,tags` adds time since JVM startup, log level, and tags.
- `filecount=5,filesize=20M` limits the number of rotation files and the target size of each file.

You can increase per-phase detail:

~~~bash
java \
  -Xlog:gc*=info,gc+age=trace,gc+phases=debug,gc+cpu=info:file=gc.log:uptime,level,tags \
  -jar application.jar
~~~

`gc+phases=debug` helps analyze per-phase durations. `gc+cpu=info` shows user/system CPU time and wall-clock (`Real`) time for pauses. Detailed logging can increase I/O and disk usage; in production, choose appropriate tags, levels, and rotation settings.

## 10. Reading a G1 Young Collection Log

Example from a test workload on Azul JDK 24.0.2:

~~~text
[0.043s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.043s][info][gc,heap] GC(0) Eden regions: 17->0(9)
[0.043s][info][gc,heap] GC(0) Survivor regions: 0->3(3)
[0.043s][info][gc,heap] GC(0) Old regions: 2->4
[0.043s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->5M(32M) 1.777ms
~~~

How to read it:

- `0.043s`: time elapsed since JVM startup.
- `GC(0)`: GC event ID; lines with the same ID belong to the same collection.
- `Pause Young`: indicates a young collection pause.
- `Normal`: G1 young pause type.
- `G1 Evacuation Pause`: G1 copies live objects out of the collection set.
- `Eden regions: 17->0`: number of Eden regions before and after the pause.
- `Survivor regions: 0->3`: number of Survivor regions before and after the pause.
- `Old regions: 2->4`: number of Old regions before and after the pause.
- `18M->5M(32M)`: heap used before GC, heap used after GC, and heap capacity at the time of the log.
- `1.777ms`: pause duration recorded in this example.

Region count is not object count. `18M->5M` is also not the amount of memory freed in Eden alone; it is the aggregate heap figure for the GC cycle.

Durations and region counts in logs vary by JDK, heap, CPU, and workload. Use examples to understand the structure, not the sample numbers as production thresholds.

## 11. Reading Object Age and Tenuring Thresholds

When `gc+age=trace` is enabled, G1 may log entries like:

~~~text
[0.042s][debug][gc,age] GC(0) Desired survivor size 1572864 bytes, new threshold 2 (max threshold 2)
[0.044s][debug][gc,age] GC(1) Desired survivor size 1048576 bytes, new threshold 1 (max threshold 2)
~~~

Key details:

- **Desired survivor size:** the Survivor capacity target the JVM aims for.
- **new threshold:** the actual age threshold chosen for surviving objects.
- **max threshold:** the configured maximum age limit.

In this example, the threshold changes between 2 and 1 even though the max threshold is 2. This illustrates that the JVM can adjust the tenuring threshold based on survival data and Survivor capacity.

If many objects reach higher ages or Survivor becomes nearly full, promotion can happen earlier. When the old generation grows rapidly, cross-check the age table, allocation profile, and references retaining objects.

## 12. Monitoring Young Collections with jstat

`jstat` can provide snapshots of memory pools and GC counts. Example:

~~~bash
jstat -gc <pid> 1000 5
~~~

Commonly useful columns for the young generation:

| Column | Meaning |
|---|---|
| `S0C`, `S1C` | Capacity of Survivor space 0 and 1 |
| `S0U`, `S1U` | Used space of Survivor space 0 and 1 |
| `EC` | Eden capacity |
| `EU` | Eden used space |
| `YGC` | Number of young GC events occurred |
| `YGCT` | Total time spent in young GC |

Columns may be represented differently depending on the collector and JDK. For G1, `jstat` reports aggregate pool metrics; GC logs usually provide additional region and phase context. For ZGC, do not assume Survivor/Eden columns follow the Serial/Parallel layout.

`jstat` is an experimental/unsupported tool and its text format may change. Use it for quick observation, combined with GC logs or JFR for deeper investigation; do not build parsers that depend on an unstable text format.

## 13. Evaluating Young Collection Frequency and Duration

There is no single young GC per second rate considered good for every application. A service that allocates many short-lived objects may run young collections frequently while still achieving good throughput and latency.

Track the following metrics over the same time window:

- Young collections per second or per minute.
- Total pause time and p95/p99 pause percentiles.
- Application allocation rate.
- Heap used after each young collection.
- Survivor occupancy and age distribution.
- Promotion rate and Old generation trend.
- CPU spent on GC versus application CPU.
- Request latency, throughput, and error rate.

### Common Signals

| Observation | Interpretation and Next Checks |
|---|---|
| Frequent young GCs with very short pauses | May be a normal high-allocation workload; compare against throughput/latency |
| Frequent young GCs and high total GC time | Check allocation rate, young generation size, and GC CPU |
| Long young pauses with high surviving object volume | Inspect age traces, object copying, survivor pressure, and heap roots |
| Old generation grows across multiple young GCs | Long-lived objects or objects retained by caches, queues, sessions, or static references |
| Survivor frequently full or low threshold | Check lifetime distribution and promotion rate |
| `Pause Young (Mixed)` appears in G1 | G1 is collecting young regions along with some old regions in the Space-Reclamation phase |
| `Pause Full` appears | Investigate the Full GC cause; check evacuation failure, old occupancy, humongous allocations, and `System.gc()` |

A single young GC is not enough to conclude there is a memory leak. Observe the post-GC heap and old occupancy trend over multiple cycles.

## 14. Factors That Slow Down Young Collections

### Many Surviving Objects

Evacuation time typically increases when the collector must copy many live objects. A workload shift that causes objects to live longer can cause pauses to spike suddenly.

### Increased Promotion

Promoted surviving objects increase the Old generation. If the promotion rate exceeds Old generation reclamation capacity, the heap can approach the Full GC threshold.

### Insufficient Survivor Space

A Survivor space that is too small can cause premature promotion. This increases pressure on the Old generation and can alter the frequency of subsequent collections.

### References and Remembered Sets

G1 must scan references from outside the collection set into the regions being collected. Many cross-region references or many dirty cards can make the merge/scan heap roots phase time-consuming.

### CPU or Environment Contention

Pause wall-clock time can increase when GC workers do not receive enough CPU, a container is CPU-throttled, or the host is running competing workloads. Compare `User`, `Sys`, and `Real` in `gc+cpu` logs.

### Allocation Bursts or Large Objects

An allocation burst can fill the young generation quickly. In G1, humongous objects can be allocated directly into old regions and put pressure on old generation reclamation.

## 15. Tuning the Young Generation Properly

Start by measuring the real workload and using collector defaults. Change the young generation size only after logs reveal a specific issue.

### For G1

G1 automatically sizes the young generation to try to meet its pause-time goal. Oracle recommends avoiding fixing the young generation size with `-Xmn`, `-XX:NewRatio`, or similar options because doing so can disable G1's ability to control pause times.

Key principles:

- Set `-Xmx` based on measured live set, allocation rate, and headroom.
- `-XX:MaxGCPauseMillis` is an optimization target, not a guaranteed pause limit.
- Only consider `G1NewSizePercent` or `G1MaxNewSizePercent` when logs point to a young generation sizing or object copy issue.
- If `Evacuate Collection Set` and `Object Copy` dominate pauses, review surviving object counts, allocation patterns, and young generation bounds.
- If Mixed collections are slow, separate young region and old region processing times using `gc+ergo+cset=debug` logs.

### For Serial and Parallel

Classic collectors can be tuned with `-XX:NewRatio`, `-XX:NewSize`, `-XX:MaxNewSize`, and `-XX:SurvivorRatio`. These options adjust the young/old or Eden/Survivor ratios. However, enlarging the young generation reduces minor GC frequency but can increase pause duration; shrinking it can make GC occur more frequently.

Do not copy tuning values from one collector to another. Re-measure after each change using the same workload and the same metric set.

## 16. Complete Java 17 Example Triggering Young Collections

The following example allocates many temporary objects and retains one object per batch to create both garbage and a small retained set.

Create the file `src/demo/YoungCollectionDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** Creates short-lived allocations and a small retained set for GC practice. */
public final class YoungCollectionDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static long checksum;

    public static void main(String[] args) {
        for (int batch = 0; batch < 24; batch++) {
            byte[][] allocations = new byte[512][];

            for (int i = 0; i < allocations.length; i++) {
                byte[] value = new byte[8 * 1024];
                value[0] = (byte) (batch + i);
                checksum += value[0] & 0xff;
                allocations[i] = value;
            }

            RETAINED.add(allocations[0]);
        }

        System.out.println(
            "READY batches=" + 24
            + " retained=" + RETAINED.size()
            + " checksum=" + checksum
        );
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d out src/demo/YoungCollectionDemo.java
~~~

Run with G1, a small heap for easy observation, and age tracing enabled:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC -XX:MaxTenuringThreshold=2 -Xlog:gc*,gc+age=trace:stdout:uptime,level,tags -cp out demo.YoungCollectionDemo
~~~

Program stdout:

~~~text
READY batches=24 retained=24 checksum=1566720
~~~

GC logs will appear before the `READY` line. In a test run on Azul JDK 24.0.2, G1 performed multiple young collections. The first logged `Pause Young (Normal) (G1 Evacuation Pause)`, Eden regions `17->0`, Survivor regions `0->3`, Old regions `2->4`, and heap `18M->5M(32M)`. The age log also showed the JVM adjusting the tenuring threshold. Pause durations and region counts vary by machine, heap, and JDK.

`-XX:MaxTenuringThreshold=2` is only used here to demonstrate aging/promotion in the lab. Do not use this value as a default production configuration. Once the run finishes, the program exits and the JVM terminates the process.

## 17. Comparing Logs Across Collectors

Running the same workload on JDK 24.0.2 shows that collectors use different log labels:

**G1:**

~~~text
Pause Young (Normal) (G1 Evacuation Pause)
Eden regions: 17->0(9)
Survivor regions: 0->3(3)
Old regions: 2->4
~~~

**Parallel GC:**

~~~text
Pause Young (Allocation Failure)
PSYoungGen: 8704K(9728K)->1008K(9728K)
Eden: 8704K(8704K)->0K(8704K)
From: 0K(1024K)->1008K(1024K)
~~~

**Serial GC:**

~~~text
Pause Young (Allocation Failure)
DefNew: 8704K(9792K)->1088K(9792K)
Tenured: 1136K(21888K)->4231K(21888K)
~~~

**Generational ZGC:**

~~~text
Minor Collection (High Usage)
Young Generation
Concurrent Mark
Pause Relocate Start
Concurrent Relocate
~~~

These are log snippets observed in the lab; they are not a fixed format for every build. With ZGC, concurrent phases are a major part of the cycle; do not sum all concurrent durations as stop-the-world pause time.

## 18. Common Mistakes When Reading Young Collections

### Thinking Every Young GC Is a Bad Sign

GC frequency depends on allocation rate and young generation size. Compare pauses, throughput, and latency before drawing conclusions.

### Confusing `18M->5M(32M)` with the Amount of Eden Freed

This represents heap used before/after GC and total heap capacity. Use the `Eden regions`, `Survivor regions`, and `Old regions` lines to inspect individual areas.

### Confusing Promotion with a Memory Leak

Long-lived objects can be expected behavior, such as caches or sessions. Check ownership and retention paths before concluding there is a leak.

### Treating Every `Pause Young (Mixed)` as a Full GC

In G1, a Mixed collection includes young regions and some selected old regions. Look for the exact log type and collection set.

### Forcing the Young Generation Too Small

Young collections may occur more frequently and increase total CPU spent on GC. In G1 especially, fixing the young generation size can undermine pause-time control.

### Looking Only at GC Counts and Ignoring Pauses

An application with many short young GCs can outperform one with fewer GCs that have very long pauses. Track total GC time and p95/p99 pauses.

### Using `System.gc()` to Test Young Collections

`System.gc()` may trigger a full-heap collection or other behavior depending on the collector and flags. Do not use it to simulate young collections.

### Comparing Logs from Two Collectors as the Same Format

Serial, Parallel, G1, and ZGC have different phase names, pools, and semantics. Record the collector, JDK version, and flags before comparing.

## 19. Investigation Workflow for Young Collections in Real Applications

1. Confirm the JDK version, collector, heap size, and GC flags.
2. Enable GC logging with `-Xlog:gc*`; add `gc+age=trace` if you need to understand promotion.
3. Collect logs over a representative workload window with timestamps and rotation.
4. Count young collections, pause durations, total GC time, and post-GC heap trends.
5. Check Eden/Survivor/Old regions or the corresponding pools for your collector.
6. If pauses are long, inspect the phase breakdown to see whether time is spent in root scanning, remembered sets, object copying, or another phase.
7. If the old generation grows, inspect age distribution, promotion rate, and structures retaining objects long-term.
8. If you see a Full GC or evacuation failure, investigate old occupancy, allocation bursts, humongous objects, and headroom.
9. Correlate with request latency, throughput, CPU, container limits, and allocation metrics.
10. Change one factor at a time, rerun the same workload, and compare the same metric set.

For production, use a log level sufficient to answer the investigation question and bound log file size. Do not change young generation size or tenuring threshold based on a single log line.

## 20. Checklist

- [ ] Understand the weak generational hypothesis and why objects typically die young.
- [ ] Distinguish Young generation, Old generation, and Full GC.
- [ ] Understand the roles of Eden, Survivor From/To, and promotion.
- [ ] Understand object age and that the tenuring threshold can be adjusted by the JVM.
- [ ] Know that remembered sets/card tables help find Old-to-Young references.
- [ ] Distinguish young-only and mixed collections in G1.
- [ ] Recognize `Pause Young`, `PSYoungGen`, `DefNew`, and `Minor Collection`.
- [ ] Enable `-Xlog:gc*` and `gc+age=trace` when needed.
- [ ] Read heap before/after, pause duration, region counts, and age traces.
- [ ] Monitor YGC/YGCT when using `jstat -gc`.
- [ ] Evaluate GC frequency alongside pauses, throughput, and request latency.
- [ ] Do not confuse promotion with a memory leak.
- [ ] Avoid fixing the young generation size in G1 without evidence.
- [ ] Check for Full GC, evacuation failure, and humongous allocations when the old generation grows.
- [ ] Compare the same workload and collector when measuring before/after.

## 21. References

- [Oracle JDK 24 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-collector-implementation.html): generational hypothesis, minor collection, Eden/Survivor, aging, throughput, and latency.
- [Oracle JDK 24 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html): G1 region layout, Young-Only phase, Concurrent Start, Mixed collection, evacuation, and remembered sets.
- [Oracle JDK 24 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html): GC logging, young collection pauses, object copying, pause-time target, and young generation tuning caveats.
- [Oracle JDK 24 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): Generational ZGC, young/old generations, and concurrent behavior.
- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): heap and young generation options such as `-Xmn`, `-XX:NewSize`, and `-XX:NewRatio`.

Young collection is a normal part of generational GC. To evaluate whether it affects your application, look at surviving objects, promotion, pause duration, allocation rate, and latency together. Using collector-appropriate GC logs helps pinpoint which part of the cycle is taking time before tuning configuration.

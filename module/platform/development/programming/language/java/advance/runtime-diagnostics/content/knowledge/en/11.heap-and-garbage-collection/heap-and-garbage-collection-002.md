# 11.2. Reading heap graphs over time and live data after collection cycles

In Java, a heap graph over time helps distinguish two very different phenomena: **temporary memory growth because the application continuously allocates objects** and **memory still retained after the garbage collector (GC) has had an opportunity to reclaim it**. The diagnostically meaningful signal is not only the `heap used` peak, but also the trend of usage levels **after comparable GC events**.

This lesson focuses on how to read the graph, calculate from before/after GC points, recognize abnormal signals, and verify through JVM observation. The numbers and log snippets below are illustrative examples, not fixed values across all JVMs.

## 1. Reading the lines and axes on the graph accurately

The horizontal axis is typically time (seconds, minutes, hours); the vertical axis is memory capacity (MiB/GiB or bytes). Before drawing conclusions, identify the exact metric and scope the tool is plotting.

| Concept | Meaning | How to use when reading the graph |
| --- | --- | --- |
| `heap used` | Amount of heap memory the JVM reports as currently in use at sampling time. | Observe peaks, troughs, and fluctuations between GC runs. |
| `heap committed` | Amount of heap memory the JVM has committed/allocated to the heap at that time. | Explains why the heap region size can expand or shrink. |
| `heap max` | Maximum heap usage the JVM reports for the heap, usually related to the `-Xmx` limit. | Assesses the theoretical limit; may be undefined in some APIs/memory pools. |
| `used after GC` | Amount of heap reported still in use immediately after a specific GC event. | Tracks the post-GC baseline, though you need to know which GC type ran. |
| `live set` | The set of objects actually reachable from GC roots at a point in time under the reachability model. | Conceptual model for reasoning about live data; not mechanically identical to every `used after GC` sample. |
| `old generation / tenured used` | Memory in use in the region holding long-lived objects, if the collector partitions regions accordingly. | Useful for distinguishing short-term churn from long-term accumulation. |

`used`, `committed`, and `max` are three distinct curves: `used ≤ committed`, and in typical configurations `committed ≤ max`. A rising `committed` curve alone does not prove a leak: the JVM may expand the heap to meet load. At the same time, **OS RSS/process memory does not equal heap used**: metaspace, code cache, thread stacks, direct buffers, native libraries, and other off-heap parts also consume memory.

Check units before comparing: 1 MiB = 1,048,576 bytes; 1 GiB = 1,024 MiB. Do not compare pool usage percentages with absolute MiB values without converting. Auto-scaled Y axes on graphs can make a small change look very large.

## 2. Why does the graph often have a sawtooth shape?

In an application that creates many short-lived objects, memory usage typically climbs between two GC events and then drops when GC reclaims memory. When repeated, the `heap used` curve looks like a sawtooth:

1. **Upward slope:** the application allocates more objects; some soon become garbage but have not yet been collected.
2. **Pre-GC peak:** the `used` level right before the collection event, influenced by allocation rate, heap size, collector policy, and load.
3. **Post-GC drop:** some space is reclaimed; the before/after difference is the change in the `used` metric across that event.
4. **Post-GC trough:** the `used` level still reported after collection. Connect troughs from **the same event type, under equivalent load** to observe the memory retention trend.

Not every collector produces a sharp sawtooth. Concurrent collectors such as ZGC or Shenandoah perform multiple phases while the application runs; sparsely sampled graphs may look smooth or drop in multiple steps. G1 has young GC, mixed GC, and concurrent phases with different effects. Therefore, **a sharp drop on the graph is only a suggestive clue; GC event labels and logs determine what actually happened**.

The spacing between two consecutive peaks can reflect allocation rate, GC trigger thresholds, or changes in heap size. Do not interpret GC frequency independently of request rate, batch jobs, committed heap, and GC algorithm.

## 3. "Alive after GC" must be understood within the scope of the collection event

A *live* object is an object still reachable via a reference chain starting from GC roots (for example, active local variables, static references, or JVM-managed roots). An unreachable object is a candidate for reclamation, but **when the collector actually reclaims it** still depends on the algorithm and the scope of the cycle.

- **After a young GC:** surviving objects in the young region are retained/moved according to the algorithm, while many unneeded objects in the old generation may not have been examined yet. `total heap used after young GC` therefore **does not accurately measure the entire live set**.
- **After a mixed/old/full collection:** may better reflect long-term retention, though collection scope varies across collectors and individual events. Even after a full GC, figures are still affected by measurement timing, application activity, and how the JVM accounts memory regions.
- **In a concurrent GC:** the application can still allocate/mutate references while the collector works. A `used` sample right after a "cycle complete" label is not a strictly atomic snapshot of the entire object graph.
- **`Retained size` in a heap dump:** the size of objects that could be freed if a corresponding object/group of roots no longer kept them alive (per dominator analysis). This is an analysis of reference relationships, **different from** total `used after GC`.

When saying "the post-GC trough is rising," the accurate phrasing is: *reported heap usage remaining after comparable GC events is increasing*. Only after ruling out workload changes, legitimate caches, collection policy, and sampling effects do you have grounds to suspect unintended data retention.

## 4. Step-by-step process for reading a heap graph over time

### Step 1 — Identify the exact metric and configuration

Record the collector (G1, Parallel, ZGC, Shenandoah...), JDK version, `-Xms`, `-Xmx`, units, sampling interval, and whether the graph shows the whole heap or a single memory pool. Check whether each data point is an instantaneous value, a windowed average, a `max`, or an aggregation across multiple JVMs. For instance, a 1-minute average curve can hide very short spikes.

### Step 2 — Mark real GC events

Align the graph timeline with GC logs/JFR: start time, end time, event type, before/after values (if reported by the collector), pause duration, and concurrent cycles. A graph with only `used` and no GC events is still useful for watching trends, but **insufficient** for accurately labeling every trough.

### Step 3 — Read both peaks and troughs

For each event with before/after figures, record:

- `before`: heap used right before GC.
- `after`: heap used right after GC.
- `reclaimed_observed = before - after`: the MiB reduction observed across the event, not synonymous with the total garbage created during the preceding interval.
- `after / committed` and `after / max`: two different reference ratios; keep the denominator consistent when comparing.

For example, if GC reports `760 MiB → 260 MiB (heap capacity 1,024 MiB)`: the observed reduction is `500 MiB`; remaining usage after GC accounts for `260 / 1,024 ≈ 25.4%` of the displayed capacity. If `-Xmx=1,536 MiB`, the post-GC level is about `16.9%` of the maximum limit. The remaining `1,536 - 260 = 1,276 MiB` is only **headroom based on used vs. max**, not a guarantee that every future allocation will succeed.

### Step 4 — Connect comparable troughs to identify trends

Select points after **the same GC category**, same version/configuration, and same workload phase. For three young GCs, levels of `250 → 265 → 280 MiB` might reflect a warming cache, objects promoted to old, or increased load; it cannot yet be called a leak. If, after workload stabilizes, a series of **collection events covering the old generation** still shows troughs of `300 → 450 → 610 MiB`, that is a signal to investigate long-retained objects.

Do not directly compare "trough after young GC" with "trough after full GC" to infer live-set growth or shrinkage; they do not measure the same scope. With concurrent GCs, choose metrics/phases after an appropriate cycle, or use observations over a sufficiently long window rather than a single point.

### Step 5 — Read slope and GC cadence in the context of load

Between two clear GC events, `Δused / Δt` is the **observed rate of heap used increase**, not total allocation rate: during the same interval there may be uncollected garbage, retained objects, or background GC activity. To measure true allocation rate, prefer JFR/profilers/appropriate allocation metrics.

When troughs stay stable but peaks rise quickly and GCs happen frequently, the application may be creating many short-lived objects. When both troughs and old usage rise over many cycles, investigate long-held references or legitimately growing data volume. A faster GC cadence usually increases CPU/pause cost, but is not sufficient proof of a leak.

### Step 6 — Correlate with performance and application events

Plot on the same timeline: requests/s, batch jobs, user count, queues, cache size, p95/p99 latency, GC pauses, CPU, and `OutOfMemoryError` errors (if any). A spike coinciding with a traffic surge or importing millions of records means something different from a heap trough climbing over many hours under flat load.

## 5. Sample data reading exercise

Suppose a G1 application has `-Xmx1536m`, and committed heap capacity at the timestamps below is around 1,024 MiB. GC logs provide before/after pairs; the table is simplified to practice reasoning:

| Time | Event | Heap before GC | Heap after GC | Observed reduction | Note |
| --- | --- | ---: | ---: | ---: | --- |
| 09:00 | Young GC #41 | 710 MiB | 250 MiB | 460 MiB | Plenty of short-lived data reclaimed. |
| 09:05 | Young GC #42 | 760 MiB | 265 MiB | 495 MiB | Trough rose 15 MiB, not enough to conclude. |
| 09:10 | Young GC #43 | 790 MiB | 280 MiB | 510 MiB | Need to cross-check old usage and load. |
| 09:20 | Mixed GC #55 | 820 MiB | 230 MiB | 590 MiB | GC scope changed; do not mix into the young GC series as the same sample type. |

At 09:05, `760 - 265 = 495 MiB` shows how much heap used dropped during the event, **not** that exactly 495 MiB of objects died in the preceding 5 minutes. The three young GC troughs `250, 265, 280 MiB` rose by 30 MiB in 10 minutes; the series is too short and lacks workload control to draw a conclusion. After the mixed GC, `230 MiB` is lower than every prior young GC trough: this suggests additional memory regions were reclaimed, though it also does not mean a leak had occurred earlier.

Compare three hypothetical situations over a longer period with stable load and configuration:

| Data after equivalent GC events | Reasonable interpretation | Verification step |
| --- | --- | --- |
| `280, 286, 279, 283 MiB` | Trough fluctuates around a relatively stable baseline. | Check GC pauses and throughput; may be normal operation. |
| `280, 360, 440, 530 MiB` | Used baseline is steadily increasing. | Match against workload/cache/old usage, then inspect classes and reference retention paths if the trend continues. |
| `280, 360, 440, 300 MiB` | Rises then drops; could be cache eviction, a finished workload, or another GC cycle reclaiming more. | Find the exact event/task at the inflection point; avoid concluding from a single segment. |

## 6. Typical shapes and how to form hypotheses

| Observed shape | Hypothesis to consider | Distinguishing signals |
| --- | --- | --- |
| Repeating sawtooth, trough around one level | Frequent allocation, steady GC reclamation. | Troughs stable over many cycles; acceptable latency/CPU. |
| Higher peaks without corresponding trough rise | Higher load or short-lived object creation rate; committed heap may expand. | Compare requests/s, allocation rate, `committed`, and GC pauses. |
| Troughs after equivalent GCs steadily climb | Growing live data: caches, queues, sessions, unfinished batches, or unintended reference retention. | Track old usage and retained objects in heap dumps/JFR. |
| Dense GC cadence, heap near limit, high after GC | Memory pressure; risk of high GC overhead, longer pauses, or OOM if no room remains to allocate. | Check `-Xmx`, GC cause, allocation pressure, pauses, and allocation failures. |
| Heap used nearly flat while RSS climbs | Off-heap or native memory; could also be high committed heap with low used. | Compare RSS with direct buffers, thread stacks, metaspace, code cache, and native memory tracking if enabled. |
| Sharp drop after batch/traffic ends | Temporary objects collected or caches released. | Align the drop timestamp with GC logs, batch completion, and old usage metrics. |
| No drop visible in a short observation window | No GC occurred yet, collector runs concurrently, or sampling missed the event. | Check event logs and lengthen the window / shorten the sampling interval. |

A bounded cache typically grows during warm-up and then plateaus; an unbounded cache can retain data indefinitely. Both can produce an initially rising baseline. **The graph is evidence of memory symptoms, not proof of the source of references.**

## 7. Collecting data from the JVM to confirm your reading

### 7.1. Unified GC logging (Java 17+)

When launching the application, enable GC logging at a level suitable for the environment:

```bash
java -Xms256m -Xmx1536m \
  -Xlog:gc*,gc+heap=debug:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

Example of an illustrative GC log line (exact wording varies by JDK/collector/tag configuration):

```text
[12.345s][info][gc] GC(41) Pause Young (Normal) (G1 Evacuation Pause) 760M->260M(1024M) 12.3ms
```

In this example: `760M` is heap before the event; `260M` is heap after the event; `1024M` is the heap capacity reported in the log line; `12.3ms` is the reported pause duration. **Do not read `1024M` in parentheses as the `-Xmx` value**; they can differ. When analyzing another collector, rely on the actual log structure rather than assuming every line shares the same template.

Do not turn log verbosity too wide for too long in production without evaluating storage/I/O cost; ensure log rotation is configured and timestamps/timezones are aligned with monitoring.

### 7.2. Observation commands without modifying code

```bash
# Heap information for the current collector, at a point in time
jcmd <pid> GC.heap_info

# Sample pool utilization and GC counters every 1,000 ms, 10 samples
jstat -gcutil <pid> 1000 10

# Record a short JFR to analyze GC events, pauses, and workload
jcmd <pid> JFR.start name=heaptrend settings=profile duration=120s filename=heaptrend.jfr
```

`jstat -gcutil` primarily displays **pool utilization percentages** and GC counters/times; you cannot treat the `O` column as the whole heap's live set in MiB. `jcmd GC.heap_info` is a snapshot rather than a full timeline. With JFR, open the file in Java Mission Control (JMC) to view GC timelines, allocations, pauses, and metrics actually recorded by the JDK/collector; available event types differ across configurations.

You can use VisualVM, JConsole, or Micrometer/Prometheus dashboards to view `heap used`/`committed`/`max` time series. For application metrics, check the `area=heap` tag, pool, instance, units, and how the tool aggregates series. A "live data size" metric depends on the collector and update timing; do not assume it refreshes after every young GC.

### 7.3. Sampling the heap yourself with Java 17+

The following standalone example prints heap state and total collection count every second. It is useful for understanding **sampled values**, though by itself it does not pinpoint every "immediately after GC" point.

Create the file `HeapTrend.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.time.Instant;

public class HeapTrend {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 10; i++) {
            MemoryUsage heap =
                    ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
            long collections = 0L;

            for (GarbageCollectorMXBean gc :
                    ManagementFactory.getGarbageCollectorMXBeans()) {
                long count = gc.getCollectionCount();
                if (count >= 0) {
                    collections += count;
                }
            }

            String max = heap.getMax() >= 0
                    ? (heap.getMax() / MIB) + "MiB"
                    : "unknown";

            System.out.printf(
                    "%s used=%dMiB committed=%dMiB max=%s gcCount=%d%n",
                    Instant.now(), heap.getUsed() / MIB,
                    heap.getCommitted() / MIB, max, collections);

            if (i < 9) {
                Thread.sleep(1000);
            }
        }
    }
}
```

Compile and run (requires JDK 17 or later):

```bash
javac HeapTrend.java
java -Xms128m -Xmx512m HeapTrend
```

The program prints **10 lines**, each formatted as `<timestamp> used=<n>MiB committed=<n>MiB max=512MiB gcCount=<n>` in the example configuration (`used`, `committed`, timestamps, and GC counts vary by machine and run). No fixed numeric stdout is given because allocation, JVM startup, and GC scheduling are non-deterministic. `gcCount` is the sum of collection counts reported by supported MXBeans, not a GC event ID, and is not guaranteed to increment by exactly one for each heap change. To pair before/after figures accurately with events, use GC logs/JFR rather than inferring from two samples 1 second apart.

## 8. When to suspect unintended memory retention

A grounded investigation workflow is:

1. **Build a sufficiently long baseline:** collect a series after comparable GCs across many cycles, not just 2–3 points; record load and configuration changes.
2. **Separate legitimate growth:** rule out cache warm-up, growing sessions, unprocessed queues, bulk imports, batch-scoped data retention, and intentional business changes.
3. **Inspect long-lived regions:** compare old usage, promotion rate, old/mixed/full GCs, `committed`, and pauses over the right phase. For collectors not partitioned this way, use their appropriate metrics.
4. **Find what holds the objects:** if the baseline keeps rising under steady load, use JFR, class histograms, or heap dumps and analyze them with Eclipse Memory Analyzer/VisualVM. Inspect top memory consumers, dominator tree, retained size, GC roots, and reference retention paths.
5. **Verify hypotheses:** an uncleaned static `Map`, unregistered listeners, unconsumed queues, overly long-lived `ThreadLocal`s, or unbounded caches are *common suspects*; only conclude once you find the reference retention path or compare before/after-fix samples.

Heap dumps can be large, create CPU/I/O load, and pause the application depending on the tool/JVM; dumps may also contain sensitive data. Collect them only when operational conditions allow. Avoid calling `System.gc()` to "force proof" of a leak: the call is a GC hint that can be disabled, causes pauses, and distorts measurement conditions. Do not treat raising `-Xmx` as the sole remedy for retention growth; it may only delay when the heap fills up.

## 9. Common misconceptions to avoid

- **"Rising heap used means a memory leak."** False: allocating and waiting for GC is normal behavior. Watch troughs after comparable GCs and workload progression.
- **"The trough after young GC is the entire live set."** False: uncollected regions may still hold garbage.
- **"300 MiB remaining after GC means 300 MiB is leaked."** False: live objects can be valid application and JVM state; only data that is no longer needed yet still retained warrants investigation.
- **"The `before-after` reduction equals all objects that died since the previous GC."** False: two sample points do not count total allocations/garbage over the interval; other GCs/accounting and concurrent work can intervene.
- **"A peak touching `committed` causes an immediate OOM."** False: the JVM can expand the heap when headroom remains; OOM depends on limits, fragmentation, allocation type, and reclaimability.
- **"More frequent full GCs are better because troughs look clearer."** False: full GCs are usually expensive; do not trigger them intentionally just to make graphs easier to read.
- **"High RSS with low heap used proves GC is broken."** False: check off-heap memory, native allocations, and committed heap.
- **"A graph with little sawtooth means no GC is running."** False: concurrent collectors and aggregation can smooth out drops.

## 10. Practical checklist when viewing a dashboard

Answer all of the following questions before proposing tuning or code changes:

1. Which **JVM**'s `heap used` am I looking at, in what unit, and with what sampling interval/aggregation?
2. Where are the `committed` and `max` curves? Is the heap expanding automatically?
3. Which **GC events** do the drops correspond to: young, mixed/old, full, or concurrent cycles?
4. After events of **the same kind and under equivalent load**, is the trough stable, rising, or returning to its prior level?
5. If the trough is rising, is that due to warm-up/batch/legitimate caching, or does it continue climbing once workload stabilizes?
6. How do peaks, GC frequency, CPU, pauses, latency, and allocation failures move together?
7. If verifying a leak, have **the object types and reference paths retaining them** been identified with appropriate evidence?

**Key takeaway:** the sawtooth curve describes the cadence of allocation and collection; **troughs after comparable GC cycles** help estimate the trend of retained memory; and concluding whether a leak exists requires accounting for GC scope, actual workload, and evidence of retained objects.

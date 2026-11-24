# 6.4 GarbageCollectorMXBean for GC counts, collection time, and the limits of aggregate totals

In Java runtime diagnostics, the question "Is GC running too much?" often leads to two easy-to-fetch numbers: **collection count** and **time spent collecting**. Java provides the standard `java.lang.management.GarbageCollectorMXBean` interface to read those two cumulative values from a running JVM. However, they are only **aggregate counters**. They cannot tell how long a single GC event lasted, which requests were affected, how much time was stop-the-world (STW), why GC occurred, or why heap grew.

For example, a bean reports `getCollectionCount() = 200` and `getCollectionTime() = 3_000`. You cannot conclude the application "paused for 3 seconds", "every pause was exactly 15 ms", "GC took 15% CPU", or "p99 latency is 15 ms". You must know which collector the bean belongs to, how the JVM defines this metric, since when it was measured, and whether two snapshots belong to **the same JVM instance**.

This lesson shows how to find `GarbageCollectorMXBean`, read its two methods accurately, compute **windowed deltas**, handle `-1` and resets, avoid misinterpreting aggregate statistics, reconcile multiple collectors, and supplement with GC logs/JFR/metrics when event-level data is needed. The Java 17+ example includes both a **deterministic** output section for verification and a **live** reading mode that varies by JVM.

## 1. Where GarbageCollectorMXBean fits in the MXBean ecosystem

### 1.1 MXBeans provide a JVM management interface

An MXBean (management bean) is a management/observation interface for runtime objects. In the `java.management` module, `GarbageCollectorMXBean` represents **one garbage collector** exposed by the JVM. It extends `MemoryManagerMXBean` and `PlatformManagedObject`; thus alongside GC count and time, it also carries a name, memory pool info, and a JMX `ObjectName`.

A JVM may have **one or multiple** collector beans; the count, names, and meaning of each bean depend on the implementation, GC algorithm, configuration, and version. Do not write code that always assumes there are exactly two beans, "Young" and "Old".

Common ways to obtain the beans:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

List<GarbageCollectorMXBean> collectors =
        ManagementFactory.getGarbageCollectorMXBeans();
```

This is an **illustrative snippet to place inside a method/class**; a complete standalone program appears in the practice section. The list comes from the JVM **executing this code**. It does not automatically query another JVM by PID; reading remotely via JMX requires appropriate connection setup and authorization.

### 1.2 Identity attributes and relationship to memory pools

| API | Returns | What is it for? | Limitations |
| --- | --- | --- | --- |
| `getName()` | `String` | Collector name published by the JVM | Name can differ across collectors/JDKs/vendors |
| `getObjectName()` | `ObjectName` | JMX identifier of the bean, shaped `java.lang:type=GarbageCollector,name=...` | Not a persistent identifier across JVMs/restarts |
| `getMemoryPoolNames()` | `String[]` | Names of memory pools managed by this memory manager | Does not tell how many bytes each GC reclaimed |
| `isValid()` | `boolean` | Whether the bean/manager is still valid according to the JVM | Does not reflect latency quality or service health |
| `getCollectionCount()` | `long` | Cumulative number of GCs, if defined | Can be `-1`; lacks per-event timestamps |
| `getCollectionTime()` | `long`, unit **ms** | Approximate cumulative GC elapsed time, if defined | Can be `-1`; not a pause histogram |

Collector names are **runtime-supplied labels**, not independent proof that a bean belongs to a fixed generation. On some HotSpot collectors you might see names like "G1 Young Generation" and "G1 Old Generation"; under other configurations, bean names and counts can differ. Code should iterate over the list and **record the actual names**, rather than assigning Young/Old labels by assumed names.

### 1.3 Available via Java API and JMX

`ManagementFactory.getGarbageCollectorMXBeans()` retrieves the list within the current process. Those same beans can be exposed through the **platform MBeanServer**, with ObjectNames of the form `java.lang:type=GarbageCollector,name=<collector-name>`.

Remote JMX allows monitoring systems to query attributes, but permissions, connections, and security must be configured separately; **never enable unauthenticated public JMX remote access or weak auth just to view GC**. On apps that already run an exporter (Micrometer/JMX exporter), data may be translated into time series; verify the exporter's naming and semantics instead of assuming every metric maps 1:1 to a Java method.

## 2. Understanding getCollectionCount() accurately

Java SE 21 documentation describes `getCollectionCount()` as **the total number of collections that have occurred** for this collector. The return type is `long`, and **`-1` means undefined** for that collector.

Example:

```java
long count = bean.getCollectionCount();
if (count == -1L) {
    // Count is not provided by this collector.
} else {
    // Count is the cumulative number published by the JVM.
}
```

The snippet above requires a `bean` variable of type `GarbageCollectorMXBean` in scope; it illustrates value checking, not a standalone runnable program.

### 2.1 It is a counter, not a rate

Suppose collector A has count:

| Timestamp | `getCollectionCount()` |
| --- | ---: |
| 10:00:00 | 120 |
| 10:00:30 | 128 |

Over the 30-second window, **8 collections were recorded**. The observed rate is approximately `8 / 30 = 0.267 collections/second`, or roughly `16 collections/minute`. This is a **windowed average rate**, not a steady cadence of "definitely one GC every 3.75 seconds". All eight events could have clustered at the start, end, or unevenly.

Do not call 128 "the number of GCs in the last 30 seconds": it is a cumulative counter. To get the count in a window, subtract two snapshots **from the same collector and same process instance**.

### 2.2 Does not mean "each freed object is one GC"

A single collection may reclaim many objects, few objects, or perform steps with different meanings depending on the algorithm. Count **does not count** objects freed, bytes reclaimed, allocations, finalizations, or blocked requests. To assess heap reclamation effectiveness, you need before/after-GC memory usage or per-pool metrics; a small count can still accompany a long GC, while a large count may be many fast GCs.

### 2.3 Do not assume counts mean the same thing across collectors

Young/old GC, G1, Parallel, Serial, ZGC, Shenandoah, or generational collectors have different phases, cycles, and ways of exposing beans. One "collection" counted on one bean need not represent the same kind of work as one collection on another bean. Therefore:

- Comparing counts across **two identical configurations** is more meaningful than comparing raw counts between two different GC algorithms.
- When switching collectors or upgrading the JDK, the baseline count can shift simply due to **different observation semantics**, not necessarily workload or a code bug.
- Do not add counts across beans and declare that absolute sum "the number of times the application stopped for GC". Cycles/phases may not map one-to-one to pause events.

## 3. Understanding getCollectionTime() accurately

Java SE 21 documentation defines `getCollectionTime()` as **approximate accumulated collection elapsed time in milliseconds** for that collector. `-1` means collection time **is undefined** for that collector.

```java
long timeMs = bean.getCollectionTime();
if (timeMs == -1L) {
    // Unable to obtain elapsed GC time from this bean.
}
```

The JVM may use a higher-resolution clock to measure and convert to milliseconds. Consequently, count **can increase while `timeMs` stays unchanged** if collections are too brief to advance the millisecond-granularity counter. This behavior is documented by the API and does not by itself indicate a broken tool.

### 3.1 Cumulative time is neither a timestamp nor the last event's duration

Hypothetical example:

| Timestamp | Count | Collection time (ms) |
| --- | ---: | ---: |
| 10:00:00 | 120 | 2,400 |
| 10:00:30 | 128 | 2,560 |

Delta results: **8 collections** and **160 ms accumulated collection elapsed time** in the 30-second window. This **does not** tell you each event lasted an even `20 ms`. Computing `160 / 8 = 20 ms` gives the **collector-reported mean** over the window, not p95/p99 pauses or request latency.

Do not confuse:

- `getCollectionTime()` = approximate cumulative elapsed time reported by the collector;
- `System.nanoTime()` = elapsed time source between two instants inside the same JVM;
- UTC timestamp in logs/JFR = timestamp attached to **each event**;
- CPU time of GC worker threads = total CPU consumed across cores, not this metric.

### 3.2 "Elapsed collection time" is not by default stop-the-world pause time

A crucial point: **Java SE does not define this method as total time the application was stopped**. A JVM/collector can execute GC work concurrently with application threads or across multiple phases. How elapsed collection time is accounted is **implementation-dependent**. Therefore, do not interpret:

```text
delta(getCollectionTime) = total pause time delaying requests
```

as an equality **guaranteed by the API**.

Even when a specific JVM reports times closely correlated with certain pauses, proving latency root cause requires **event-level timing + timestamps** alongside application metrics/traces in the same window. When migrating from G1 to ZGC or changing JDKs, re-evaluate what "GC time" means on dashboards instead of keeping an invariant "STW time" label.

### 3.3 Why can cumulative time be >= 0 even when counts look unexpected?

- Count rises while `timeMs` does not: events are shorter than reporting resolution, or the JVM updates count/time differently.
- Count equals 0 in the window: no collection recorded for that bean; does not mean zero GC-related CPU work or that threads weren't paused for other reasons.
- `timeMs` may rise while collection counting does not reflect every phase detail; check implementation semantics before concluding.
- Counter/time equals `-1`: **undefined**, not a negative quantity, not an error ratio, and must not be added to totals.
- Values read in two consecutive calls may belong to slightly different instants, especially if a GC is underway.

## 4. From cumulative totals to windowed metrics

In performance investigations, two measurement points must be **contextually aligned** to be meaningful. Record run ID, PID/process start time, collector ObjectName/name, JDK version, GC algorithm, and window alongside them.

### 4.1 Basic delta formulas

Let:

- `C0`, `C1` be `getCollectionCount()` at the start/end of the window.
- `T0`, `T1` be `getCollectionTime()` (ms) at start/end.
- `W` be actual elapsed time between the two samples in seconds.

If all four counter readings are defined and non-decreasing:

```text
collections_in_window = C1 - C0
gc_elapsed_ms_in_window = T1 - T0

collection_rate_per_second = (C1 - C0) / W

if C1 - C0 > 0:
    mean_reported_elapsed_ms_per_collection = (T1 - T0) / (C1 - C0)
else:
    mean_reported_elapsed_ms_per_collection = UNDEFINED
```

These are transformations of two cumulative counters. They **do not reconstruct a pause histogram** and cannot recover individual GC timestamps.

### 4.2 Measuring window duration with a monotonic clock

Within the same JVM, use `System.nanoTime()` for elapsed duration; avoid subtracting two `System.currentTimeMillis()` calls over very short windows where wall-clock adjustments can occur. When monitoring remotely, use reliable collector timestamps with explicit timezones; avoid subtracting clocks from unsynchronized machines.

Note that `getCollectionCount()` and `getCollectionTime()` **do not form an atomic snapshot**. If a GC finishes between the two calls, count may have updated while time was read beforehand. With longer windows and reasonable sampling, relative error shrinks; over millisecond-scale windows, jitter/error can be huge. If you need exact per-event numbers, use an event-level source.

### 4.3 A ratio metric that is easily misnamed

People often compute:

```text
reported_gc_time_ratio = delta_collection_time_ms / elapsed_window_ms
reported_gc_time_percent = 100 * reported_gc_time_ratio
```

Suppose in a **30,000 ms** window, a collector reports a **150 ms** increase: the reported ratio is **0.5%**. This number is strictly the **ratio of bean-reported collection elapsed time to window wall time**. It **must not automatically be called** "% CPU spent on GC", "% time application threads were paused", "standard GC overhead across all JVMs", or "user-impact level".

When multiple collector beans can account for overlapping intervals or concurrent work, **summing time deltas** may not correspond to an independent wall-clock total. The summed ratio can become hard to interpret and even exceed intuitive bounds. **Do not clamp results to 100%** just to make a tidy chart if semantics haven't been verified.

### 4.4 Distinguishing measurement types

| Value | Source | How to read |
| --- | --- | --- |
| `C1` | Counter at end time | Lifetime/JVM-defined total, **not** a rate |
| `C1 - C0` | Two counters on same bean | Reported collections in the window |
| `T1 - T0` | Two time counters | Total increase in approximate **elapsed** ms |
| `(C1 - C0) / W` | Counter delta / wall seconds | Average collection rate |
| `(T1 - T0) / (C1 - C0)` | Time delta / count delta | Mean *reported time* per collection; not a pause percentile |
| p95 GC pause | Distribution of pause events | **Cannot be derived** from count and total time |
| Total GC worker CPU | GC CPU counters, if available | **Not identical** to getCollectionTime |
| Heap used after GC | Memory pools/JFR/GC logs | Not contained in these two counters |

## 5. Numerical example: why "average GC" easily misleads

Consider two **hypothetical** series with identical counts and total elapsed time:

```text
Window A: 10 GCs; durations = 10,10,10,10,10,10,10,10,10,10 ms
Window B: 10 GCs; durations = 1,1,1,1,1,1,1,1,1,91 ms

Both: count_delta = 10; time_delta = 100 ms
Mean from total/count: 10 ms
```

Yet their distributions are completely different: A is steady at 10 ms, while B has a 91 ms event that can hit tail latency. `GarbageCollectorMXBean` provides only the two totals, so **it cannot distinguish A from B**. There is no mathematical way to recover p99, max, or tail shape from those two sums alone.

Moreover, in concurrent collectors, bean-accounted "duration" may not even be pause duration; the example above is an **arithmetic model**, not an assertion that every GC event in every implementation is an STW pause.

### 5.1 Summing across multiple beans introduces more issues

Suppose a JVM exposes two beans:

| Bean | Δcount | ΔcollectionTime (ms) |
| --- | ---: | ---: |
| Collector X | 8 | 80 |
| Collector Y | 1 | 120 |

You can **display them separately**: X had eight collections and 80 ms elapsed increase; Y had one collection and 120 ms elapsed increase. However, **do not hastily conclude** the application experienced 9 distinct pauses, 200 ms total paused time, or a 120 ms p95 pause. The beans may differ in work scope and accounting definitions; you must prove quantities are non-overlapping and additive in the specific implementation.

In monitoring, preserve the `collector_name`/`object_name` label rather than collapsing beans anonymously. When bean counts change after a JDK upgrade, dashboards must handle new labels and record versions so semantically different series are not compared as equivalent.

## 6. Standalone Java 17+ example: exact deltas and live snapshots

The example below has two modes:

- **Default:** uses a synthetic dataset to demonstrate subtraction and produce **deterministic**, verifiable stdout.
- **`--live`:** takes two snapshots of `GarbageCollectorMXBean` instances in the program's own running JVM roughly one second apart, printing real deltas that **cannot be predicted in advance**.

The program **does not call `System.gc()`**, does not allocate heap pressure to "force pretty numbers", does not read another JVM, and does not print sensitive data. It handles `-1` and decreasing counters by flagging insufficient basis for a delta.

Save the file `GcMxBeanWindowDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;
import java.util.Locale;

public class GcMxBeanWindowDemo {
    record Snapshot(long count, long elapsedMs) {}
    record Delta(long collections, long elapsedMs) {}

    static Snapshot read(GarbageCollectorMXBean bean) {
        return new Snapshot(bean.getCollectionCount(), bean.getCollectionTime());
    }

    static Delta difference(Snapshot before, Snapshot after) {
        if (before.count() < 0 || before.elapsedMs() < 0
                || after.count() < 0 || after.elapsedMs() < 0
                || after.count() < before.count()
                || after.elapsedMs() < before.elapsedMs()) {
            return null; // Undefined, reset, or not from the same counter series.
        }
        return new Delta(
                after.count() - before.count(),
                after.elapsedMs() - before.elapsedMs());
    }

    static void showSynthetic() {
        Snapshot before = new Snapshot(10, 250);
        Snapshot after = new Snapshot(13, 310);
        Delta d = difference(before, after);

        // d is non-null because the fixed dataset is valid.
        System.out.println("SYNTHETIC_GC_COUNT_DELTA=" + d.collections());
        System.out.println("SYNTHETIC_GC_ELAPSED_MS_DELTA=" + d.elapsedMs());
        System.out.printf(Locale.ROOT,
                "SYNTHETIC_MEAN_REPORTED_MS=%.1f%n",
                d.elapsedMs() * 1.0 / d.collections());
        System.out.printf(Locale.ROOT,
                "SYNTHETIC_REPORTED_TIME_RATIO_PCT=%.1f%n",
                100.0 * d.elapsedMs() / 1000.0);
    }

    static void showLive() throws InterruptedException {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();
        Snapshot[] before = new Snapshot[beans.size()];
        Snapshot[] after = new Snapshot[beans.size()];

        long startNanos = System.nanoTime();
        for (int i = 0; i < beans.size(); i++) {
            before[i] = read(beans.get(i));
        }

        Thread.sleep(1000);

        for (int i = 0; i < beans.size(); i++) {
            after[i] = read(beans.get(i));
        }
        double windowMs = (System.nanoTime() - startNanos) / 1_000_000.0;

        System.out.println("LIVE_COLLECTOR_BEANS=" + beans.size());
        System.out.printf(Locale.ROOT, "LIVE_WINDOW_MS=%.1f%n", windowMs);
        for (int i = 0; i < beans.size(); i++) {
            GarbageCollectorMXBean bean = beans.get(i);
            Delta d = difference(before[i], after[i]);
            String identity = bean.getObjectName().toString();
            if (d == null) {
                System.out.println("LIVE " + identity
                        + " COUNT_OR_TIME_UNDEFINED_OR_DECREASED");
            } else {
                System.out.println("LIVE " + identity
                        + " count_delta=" + d.collections()
                        + " elapsed_ms_delta=" + d.elapsedMs());
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        showSynthetic();
        if (args.length == 1 && "--live".equals(args[0])) {
            showLive();
        }
    }
}
```

Compile and run the arithmetic verification using Java 17+:

```bash
javac GcMxBeanWindowDemo.java
java GcMxBeanWindowDemo
```

**Exact stdout** of the default mode:

```text
SYNTHETIC_GC_COUNT_DELTA=3
SYNTHETIC_GC_ELAPSED_MS_DELTA=60
SYNTHETIC_MEAN_REPORTED_MS=20.0
SYNTHETIC_REPORTED_TIME_RATIO_PCT=6.0
```

Explanation: the two hypothetical snapshots have count delta `13 - 10 = 3` and time delta `310 - 250 = 60 ms`. The **reported** mean is `60 / 3 = 20.0 ms/collection`. Assuming an exact 1,000 ms window, the reported time ratio is `60 / 1,000 × 100 = 6.0%`. **This 6% is not CPU % and must not be claimed as STW pause %.**

Run the version that reads the **demo JVM's** beans:

```bash
java GcMxBeanWindowDemo --live
```

The four `SYNTHETIC_...` lines stay the same, followed by `LIVE_...` lines depending on the real JVM. Example output structure:

```text
LIVE_COLLECTOR_BEANS=<number-of-beans>
LIVE_WINDOW_MS=<observed-elapsed-milliseconds>
LIVE java.lang:type=GarbageCollector,name=<collector> count_delta=<delta> elapsed_ms_delta=<delta>
```

The block above is a **structural description, not fixed stdout**. Bean names and counts, measured window, and count/time deltas all vary. If the program is short-lived or triggers no GC during the window, deltas may be 0. A collector that leaves a metric undefined may print `COUNT_OR_TIME_UNDEFINED_OR_DECREASED`.

### 6.1 Why does the lab avoid summing all collectors?

The program intentionally prints each ObjectName separately. Summing might be convenient on a dashboard, yet you must first verify non-overlap and what work each number represents. Additionally, getters are read sequentially, **not as a single JVM-wide atomic snapshot**. One collector may record an event while the program is sampling another bean.

### 6.2 Why is `LIVE_WINDOW_MS` only approximate?

In the code, `System.nanoTime()` spans the initial reads, sleep, and final reads. This measures "how long the sampling pass took" rather than **guaranteeing the exact same window for every individual bean**; getters are invoked at distinct times. Around one-second sampling, keep scheduling jitter and millisecond resolution in mind. In a real monitoring pipeline, attach timestamps per sample and configure more accurate cadence/clocks.

### 6.3 Handling invalid windows

The `difference` function returns `null` if:

- Any before/after number is `-1` or negative.
- The later counter/time is **less than** the earlier one.

A decrease can stem from a reset/restart, collector/JVM change, or discontinuous data source. Do not immediately say "GC had a negative count" or feed a negative delta into a rate. In a monitoring pipeline, distinguish restarts via process start time/instance ID and apply appropriate counter-reset handling. The demo program reads **itself** in-process so it avoids most PID mix-ups, while still illustrating the validation required for external metrics.

## 7. Collecting in monitoring: aligning bean names, timelines, and counter resets

### 7.1 Identify counter pairs by collector and JVM instance

When monitoring multiple JVMs, a valid GC time series should include at least these labels or metadata:

- **Workload/JVM instance:** service, pod/container/host scope, process startup epoch or instance ID, version.
- **Collector identity:** `getName()` or ObjectName, kept consistent when tracking that bean's counter.
- **Metric and unit:** count (occurrences), time (milliseconds), rate (events/second), elapsed ratio (fraction/%) if actually computed.
- **Sampling window:** UTC timestamp and scrape interval, missing data, restart markers.
- **Collector/JDK:** GC algorithm, JVM implementation/version, important flags, and workload when comparing performance.

PID helps locate a process at a point in time, yet it can be reused and collide across containers. Do not treat `PID=1` as a single JVM across deployments.

### 7.2 Counters start over when the JVM restarts

Cumulative values represent the current JVM; another JVM has separate lifetime counters, even with the same service and pod name. If you observe:

```text
T0 count=800; elapsedMs=21000
T1 count=12;  elapsedMs=300
```

subtracting to get a negative number does not mean GC "ran backward". The service likely restarted or series were stitched together erroneously. Check process start time, deployment/restart events, and collector identity before opening a new measurement window. **Do not merge pre- and post-restart intervals into a single naive delta**.

A system like Prometheus has counter-reset functions, yet you must still ensure the metric is truly a counter, JVM instance labels are right, and scrape intervals suffice. Do not divide `getCollectionCount()` by uptime and call that the current rate: that is only the **average rate since startup**, which easily masks short spikes.

### 7.3 -1 data: undefined values must be represented explicitly

If a bean returns `getCollectionCount() = -1`, the exporter should mark it **not available/undefined** per the metric contract. Incorrect approaches:

- Replacing `-1` with 0 so dashboards read "zero GC".
- Computing delta `-1 - 20` and recording "-21 collections".
- Adding `-1` into another bean's total.
- Holding the last value forever without recording data loss.

One option is dropping invalid samples alongside an "availability" metric, or reporting `NaN` according to system semantics—never turning missing data into success. When the time counter is undefined while count is valid, **you can still track count** without fabricating time.

### 7.4 Choosing sampling cadence and handling short events

Polling too sparsely can hide spike shapes (showing only 1-minute totals); polling too aggressively increases overhead and amplifies **non-atomic getters, millisecond rounding, and missing per-event data**. Pick cadence for your goal: 10–30 seconds for overview dashboards may suit some systems; for investigating tens-of-milliseconds pauses, sampling counters even every second **still cannot reconstruct individual pause lengths**.

Windowed GC counters should sit alongside **latency counts/histograms, throughput, errors, heap used, allocation rate, and CPU/cgroup** metrics at the same timestamps. To prove GC caused a p99 spike, you need event-level data and request traces/timings, not just two nearby counter deltas.

## 8. What cannot be inferred from the two totals?

### 8.1 No p50, p95, p99, or max GC pause

Two aggregates give only count and total reported time. Every distribution with the same count/sum produces identical bean outputs. Hence:

- Do not infer p99 pause from `getCollectionTime / getCollectionCount`.
- Do not infer "worst pause" from total elapsed time.
- Do not conclude GC is smooth just because the mean is small.
- Do not substitute mean collection elapsed time for API latency SLOs.

For percentiles, observe **individual pauses/events** or histograms from a trustworthy source.

### 8.2 Cannot pinpoint when a collection occurred

`getCollectionCount()` carries no per-event timestamps. If 20 collections occurred between 10:00 and 10:01, you do not know how they clustered relative to traffic peaks. When p99 latency spikes at 10:00:45, that minute's counter delta only supports a **hypothesis**—it does not prove GC coincided with 10:00:45. GC logs/JFR/notifications answer the timing question.

### 8.3 Cannot distinguish cause, phase, type, or object reclamation

Count/time lack:

- GC cause: allocation failure, metadata threshold, explicit GC, periodic cycle, etc.
- Young pause/remark/cleanup/mixed/full according to actual semantics.
- Bytes used, reclaimed, and committed before/after GC.
- Individual memory pool growth/shrinkage, promotion, allocation rate, or humongous regions.
- Concurrent work, thread parallelism, GC worker CPU, and heap pressure.

The bean name may hint at collector type, yet **cannot replace event metadata**. Rising count does not prove GC happened from heap exhaustion; a healthy JVM GCs regularly.

### 8.4 Cannot tell how many CPU cores were busy doing GC

GC can run many worker threads in parallel, so **elapsed time** and **CPU time** are distinct quantities. For instance, hypothetically 20 ms wall time with four concurrent busy workers could correspond to more than 20 ms total CPU, plus scheduling/overhead in practice. `getCollectionTime()` is not defined as that total CPU time. To measure CPU spent on GC, use a dedicated supported source and understand JVM/collector semantics; do not equate "GC elapsed / wall" with CPU %.

### 8.5 Cannot alone explain RSS/OOM or memory leaks

An application OOM can arise from heap, direct buffers, metaspace, native allocations, threads, container memory limits, or other sources. `GarbageCollectorMXBean` returns neither RSS, max heap, committed heap, nor the retained object graph. You need `MemoryMXBean`, `MemoryPoolMXBean`, `BufferPoolMXBean`, OS/cgroup metrics, GC logs/JFR, and—when authorized—heap analysis.

High heap `used` or rising GC count may just reflect normal load growth; **a memory leak cannot be diagnosed from count/time alone**.

## 9. Different collectors and the risks of direct comparison

### 9.1 Do not hard-code "young collector" and "old collector" names

Many tutorials illustrate HotSpot with two young/old beans. Yet the API guarantees no exact bean count, names, or algorithms. A JVM can switch collectors via flags/JDK upgrades; bean names can change. Some concurrent algorithms have cycle/phase concepts that do not map cleanly to familiar "Young GC".

Therefore:

1. Enumerate `ManagementFactory.getGarbageCollectorMXBeans()` at actual runtime.
2. Record name, ObjectName, associated memory pools, and whether count/time are available.
3. Verify GC algorithm/JVM implementation/version via config/startup logs or appropriate tools.
4. Build dashboards with flexible labels; never hard-code "Old GC = second bean".
5. When upgrading the JDK or changing collectors, re-establish count/time baselines instead of treating old and new series as equivalent.

### 9.2 Counts and times across beans are not guaranteed additive

Summing is valid only when quantities share semantics and do not overlap. With GC collectors:

- One bean may represent one collection branch while another represents a concurrent cycle.
- One event may involve multiple phases; how the JVM updates count/time is not normalized into a unified pause ledger.
- Summing elapsed milliseconds of concurrent processes can exceed wall-clock length without being an "arithmetic bug".
- If a tool/exporter already aggregates, summing again in a dashboard risks **double counting**.

Without proof of additivity, keep each bean separate and label any sum strictly as "sum of reported collector counters", never "total STW pause time".

### 9.3 Algorithm differences can make two runs non-comparable

Suppose switching from G1 to ZGC under the same workload reduces request p95 while GC counts change dramatically. You cannot conclude "ZGC has fewer GCs = faster" from counts alone. Compare:

- Application latency distribution, throughput, and error rate.
- Heap usage/commit/allocation and memory limits.
- GC events and pause durations actually emitted by each collector.
- CPU usage, container throttling, and work performed concurrently.
- Identical workload/payload, JDK release, heap flags, and measurement windows.

Only under aligned conditions and clear semantics can count/time serve as **supporting evidence**.

## 10. Combining with MemoryMXBean, MemoryPoolMXBean, and OS metrics

`GarbageCollectorMXBean` is one piece of the puzzle. To answer "Is GC effective?" you need other layers:

| Source | Primary data | Use case |
| --- | --- | --- |
| `GarbageCollectorMXBean` | Cumulative count/time per collector | Trend in frequency and reported elapsed time |
| `MemoryMXBean.getHeapMemoryUsage()` | Heap used, committed, init, max | Is heap approaching its limit? |
| `MemoryPoolMXBean` | Usage/peak/collection usage when supported | Which pool is growing; how much heap remains after GC? |
| Unified GC logs | Events, tags, timestamps, cause, before/after heap per config | Correlate pauses by timestamp and collector behavior |
| JFR | GC pauses/cycles, allocations, threads, and configured events | Link GC with latency/CPU/load |
| OS/container | Process CPU, RSS, cgroup memory, throttling/OOM events | Is the JVM resource-constrained outside the heap? |
| Application metrics | p50/p95/p99 latency, errors, queues, throughput | Are users affected? |

For example, if count climbs fast and post-GC memory stops dropping, investigate allocation pressure, live set growth, heap limits, or workload changes—though **do not automatically call it a leak**. If count/time are low while RSS climbs, inspect native memory/direct buffers, code cache, or memory accounting instead of claiming GC metrics are broken.

### 10.1 GC logs reveal what aggregates hide

On HotSpot/JDK 17+, Unified JVM Logging can be configured at startup, for instance:

```bash
java "-Xlog:gc*=info:file=gc-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

This command assumes `app.jar` exists, the output directory is writable, and the collector emits events. Logs can include timestamps, GC IDs, pause types, and tag details. **Do not replace production defaults just to experiment**: debug/trace levels add overhead and disk usage; choose suitable levels, retention/security, and time correlation.

GC logs allow event-by-event analysis to spot long pauses or correlate with p99 latency. Still, event types and log fields depend on JVM/collector; do not parse log formats as an immutable protocol across every JDK.

### 10.2 JFR and GcInfo: when event-level data is required

On some HotSpot/JDK builds, the `com.sun.management.GarbageCollectorMXBean` extension provides `getLastGcInfo()` (returning info on the most recent GC or `null`). `GcInfo` can provide start time, end time, duration, memory usage before/after a collection, and implementation-specific attributes. This is an **extension API in `jdk.management`, not** part of the two standard methods on `java.lang.management.GarbageCollectorMXBean`, and not guaranteed across every collector.

Systems can also receive GC notifications via JMX `NotificationEmitter` and `GarbageCollectionNotificationInfo` on supporting collectors. Receiving notifications requires registering a listener; events can be missed if the listener is inactive, the collector doesn't emit them, or monitoring disconnects. Event-level delivery **does not automatically guarantee** a complete pause histogram unless semantics and pipeline reliability are verified.

JFR recording is the choice when detailed event history is needed, covering timing/cause/memory/stacks/CPU per configured event types. Not every JFR event is an STW pause. Check recording templates, sampling, overhead, and data permissions before building a performance narrative.

## 11. JMX operations and data quality

### 11.1 Local sampling vs. remote sampling

Reading beans inside the application via `ManagementFactory` needs no JMX network port. Remote monitoring systems, however, usually rely on a JMX connector/agent/exporter:

- Enforce TLS, authentication/authorization, and network boundaries; never expose an unprotected JMX port to the Internet.
- When using an exporter, verify metric names, units, and labels: Java reports `getCollectionTime()` in **ms**, whereas many backends represent durations in **seconds**.
- Check sample sizes and JMX timeouts. A failed scrape does not mean GC count=0.
- Separate bean identity and JVM instance before taking rates; avoid artificial spikes when PID/replica/collector changes.
- Control overhead from multiple concurrent scrapers, profiling tools, and metadata that could expose internal details.

### 11.2 Dropped samples, counter lag, resolution, and annotations

The API allows the time counter to remain unchanged even as count increments for brief events. In addition, sampling and exporters can experience buffering, scrape lag, or resets. GC charts are not infallible proof of individual event durations.

A trustworthy dashboard should display at least:

- Collector name, service/instance name, and JVM version/GC algorithm.
- Count/time counters or rate deltas, with explicit **units** and calculation windows.
- Metric availability (`-1`/missing/collector disappeared).
- Application p95 latency, error rate, and throughput over the same UTC interval.
- JVM heap used/committed/max and a GC pause histogram if sourced separately.
- Deployment/restart markers to avoid comparing across JVM restarts.

### 11.3 Do not impose a universal alert threshold across all JVMs

A GC count of 100/minute may be normal for workload/config A and abnormal for B. A 5% delta collection time ratio may be a helpful descriptor, yet its impact on STW/p99 or throughput depends on the collector. Alerts should rely on **workload baselines, variance, service quality, and corroborating evidence**, not a single aggregate number.

For example, a better alert than "count > 10" is: application p95 latency exceeds a defined threshold continuously over a sufficient sample window, accompanied by shifts in GC events/pause distribution, with links to runtime/heap/CPU metrics for verification. Such alerts also require noise filtering, low-traffic handling, and isolation from DB/network causes.

## 12. Diagnostic scenarios you may encounter

### 12.1 Count rises every 30 seconds, yet p95 stays flat

**Observation:** collector A rises by 5 collections/30 s, reported time rises by tens of ms, p95 and error rate are steady, and post-GC heap returns to baseline.

**Reasonable interpretation:** GC activity exists, yet **there is no evidence of user impact**. Do not tune GC just because count increased; evaluate allocation/workload, baseline, and event-level pauses if risk exists.

**Do not conclude:** "GC never has an impact", because aggregates can hide an isolated pause and p95 does not reflect p99.

### 12.2 Count barely increases, yet one request took 800 ms

**Observation:** only one collection in the window, total time rose 100 ms; one request took 800 ms.

**Interpretation:** the two events may or may not be related. Count/time provide no timestamps and cannot prove a 100 ms GC caused all 800 ms of latency. Check request traces, GC event timestamps, CPU, queues, and downstream calls. The request may have waited independently on a connection, lock, DB, or thread pool.

### 12.3 JVM switches GC algorithm after an upgrade

**Observation:** new bean names appear, count drops sharply, yet throughput/latency barely changes.

**Interpretation:** the measurement source changed bean semantics/names. Before claiming "GC dropped 90%", verify collector/JDK release, metric mapping, event support, and count definitions. Establish a new baseline and compare user-facing metrics.

### 12.4 Collector time returns -1 while count keeps rising

**Observation:** `getCollectionCount()` returns values, `getCollectionTime()` is `-1`.

**Interpretation:** time is undefined through that bean. You can keep using count for rates, but do not infer `time delta = 0` or a percentage. Use GC logs/JFR/other metrics if GC duration is needed.

### 12.5 Process restarts between two scrapes

**Observation:** count drops from 2,100 to 7, time from 40,000 to 120 ms.

**Interpretation:** do not produce a negative rate or plot "GC reversed". Check JVM restarts/deployments, process identity, and counter-reset handling. Compare points only within the same instance.

### 12.6 Heap grows, yet GC time barely changes

**Observation:** heap occupancy and RSS rise, count/time change very little.

**Interpretation:** the workload may be retaining many objects, GC policy has not triggered the corresponding collection yet, or growth is outside the heap. Check `MemoryMXBean`/`MemoryPoolMXBean`, OS/container metrics, and allocation evidence. Do not use low count/time to rule out memory pressure.

## 13. Common mistakes and fixes

| Mistake | Why it is wrong | Correct practice |
| --- | --- | --- |
| "`getCollectionCount() = 100` means 100 GCs in the last minute" | Cumulative counter | Subtract two samples from the same bean/instance over the exact window |
| "`getCollectionTime() = 3000` means the app paused for 3 seconds" | Elapsed collection time does not equal STW | Label accurately as reported elapsed; correlate GC event timing |
| "Dividing total time/count gives p95 pause" | Mean contains no distribution info | Use reliable event-level/histogram data |
| "Treating `-1` as a real count/time" | API defines it as undefined | Report not available; do not compute deltas |
| "Count rises without time rising ⇒ broken bean" | Millisecond resolution can leave time unchanged | Understand semantics; widen window if suitable |
| "Summing time across all beans gives total pause" | Scope differences/overlap/concurrent work | Keep separate series; aggregate only with justification |
| "Assuming every JVM has Young/Old beans" | API does not guarantee bean counts/names | Iterate the list and record actual collector identity |
| "Comparing raw counters across processes" | Different lifetimes; restarts reset counters | Use deltas and instance identity |
| "Comparing G1 vs. ZGC by raw count" | Different collector semantics | Compare performance metrics + event logs under equivalent conditions |
| "Equating delta time / wall = CPU %" | Bean time is not GC worker CPU time | Use proper CPU metrics; annotate reported ratios |
| "Blaming GC for p99 from one aggregate point" | Lacks per-event timestamps and traces | Correlate event-level GC with latency/CPU/queues |
| "Charts without units" | ms/seconds or rate/count get confused | Display explicit units, collector labels, and window |
| "Ignoring collector `isValid()`, resets, or missing data" | Can process stale or invalid samples | Check validity and pipeline health |
| "Exposing raw JVM metadata unchecked" | Can leak paths, hosts, credentials | Share minimally, enforce RBAC and redaction |

## 14. Checklist for using GarbageCollectorMXBean properly

- [ ] Use the `java.management` module and standard `GarbageCollectorMXBean` interface.
- [ ] Enumerate **all actual beans**; never hard-code counts or Young/Old names.
- [ ] For each bean, record `getName()` or `getObjectName()` plus JVM instance/JDK/GC algorithm.
- [ ] Read `getCollectionCount()` and `getCollectionTime()` separately, noting **count** and **ms**.
- [ ] Handle `-1` as **undefined**; never convert to 0.
- [ ] Computing rates/deltas requires **two samples from the same bean, same process instance**, and same definition.
- [ ] Record actual window duration, sampling interval, and appropriate UTC timestamps.
- [ ] Handle restarts/counter drops, disappearing beans, and missing samples.
- [ ] Do not assume count and time getters form an atomic snapshot.
- [ ] Do not call aggregate elapsed time "total STW pause" or "GC CPU time" without proving it for that specific JVM.
- [ ] Do not compute p95/p99/max from total/count; use GC events or histograms.
- [ ] Do not sum multiple collector beans into total pause while ignoring possible overlap.
- [ ] Correlate GC counters with application latency, throughput, errors, heap usage, and CPU/container resource metrics.
- [ ] When changing JDK/collector, re-verify semantics and baselines.
- [ ] When event-level detail/cause/before-after memory is needed, use supported GC logs/JFR/notifications.
- [ ] Secure JMX connections and monitoring data according to operational permissions.

## 15. Self-check exercises

**Q1.** A bean's count goes from 45 to 51 and time from 200 to 230 ms over a 10-second window. What can be concluded?

**Answer:** Six collections were reported by the bean, and reported collection elapsed time increased by 30 ms. The average rate is `6 / 10 = 0.6 collections/second`. The mean reported elapsed time is `30 / 6 = 5 ms/collection`. You cannot infer p95 pause or API impact.

**Q2.** Count rises from 6 to 7, while time remains 10 ms. Is there definitely a bug?

**Answer:** No. The API states time may remain unchanged if a collection is shorter than reporting resolution; collector semantics or update timing may also play a role. Take more samples or check event-level data if truly in doubt.

**Q3.** Bean A reports time increased by 200 ms and bean B by 300 ms in a one-second window. Did the application definitely pause for 500 ms?

**Answer:** No. Summing collector elapsed times is not normalized into total STW paused time; work types can differ or overlap. Check GC pause events and timestamps.

**Q4.** Time returns `-1` while count returns 100. Can you compute a GC time percentage?

**Answer:** No, time is undefined. Count can still be used for deltas within the same instance; time percentage has no basis from this bean.

**Q5.** After a deploy, count drops from 5,000 to 20. Why shouldn't you plot a delta of -4,980?

**Answer:** The counter is cumulative per JVM/collector. The process may have restarted or series from different instances were stitched together; segment and verify identity. A negative number is not the GC count in the window.

**Q6.** Can `GarbageCollectorMXBean` answer "Which GC caused the p99 spike at 14:05:03?"

**Answer:** The two counters carry neither timestamps nor per-event durations. They only raise hypotheses. You need JFR/GC logs/notifications and time-synchronized request/latency traces to correlate.

**Q7.** Code gets the bean cleanly from `ManagementFactory`, yet sees zero collections during a one-second demo run. Can you conclude the JVM does not support GC?

**Answer:** No. Simply no collection occurred in the window, the bean returns undefined, or events were too brief/not accounted as expected. Check whether count/time are valid, workload, and collector semantics; never use one flat second to judge runtime capability.

## References

- [Java SE 21 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): `getCollectionCount()`, `getCollectionTime()`, `-1`, ms unit, and approximation semantics.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): `getGarbageCollectorMXBeans()` and platform MBeans.
- [Java SE 21 — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html): memory areas, memory managers, and memory pools.
- [Java SE 21 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): usage/collection usage when supported by the collector.
- [JDK 21 — com.sun.management.GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/GarbageCollectorMXBean.html): extension providing `getLastGcInfo()` on supported collectors.
- [JDK 21 — GcInfo](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/GcInfo.html): timestamp/duration and memory usage of the most recent GC event, when data is available.
- [JDK 21 — java command Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): configuring `-Xlog` by tag/level/output.

**Remember:** `GarbageCollectorMXBean` reports **published total collection count** and **approximate cumulative collection elapsed time**, per collector bean. To see change over time, compute **deltas between two samples from the same JVM** while handling `-1`/restarts. These two totals are useful for observing **trends**, yet they are **not** a GC pause histogram, total STW time, GC CPU time, or the cause of p99 latency. When details are needed to draw conclusions, combine them with GC events, heap, CPU, and application metrics over the same window.
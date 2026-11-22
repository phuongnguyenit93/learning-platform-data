# Garbage Collection Analysis with JFR

**Java Flight Recorder (JFR)** collects JVM runtime events along a timeline. When analyzing **Garbage Collection (GC)**, JFR shows which collections ran, what triggered them, their duration, application pauses, concurrent phases, heap state before/after GC, and allocation pressure.

Analyzing GC with JFR helps answer practical questions: how long the application pauses, how frequently GC occurs, whether the post-GC heap grows over time, which phase the collector spends time in, and which classes/methods allocate many objects. JFR provides evidence for investigation; a recording does not automatically conclude a memory leak or automatically choose an optimal GC configuration.

## 1. How does JFR record GC activity?

JFR records events with timestamps, durations, threads, stack traces, and fields specific to each event type. GC events can be viewed on a timeline using Java Mission Control (JMC) or read from the command line using the `jfr` tool.

A GC cycle can consist of multiple activities:

- The JVM decides a collection is needed and records the cause.
- The collector executes preparation, marking, sweeping, copying/evacuating, or object compaction phases.
- Some phases require stopping Java threads (stop-the-world pauses).
- Some phases run concurrently while the application continues executing.
- The JVM updates the heap summary and completes the collection.

Therefore, a GC cycle does not necessarily consist of just a single pause. Especially with G1, ZGC, and Shenandoah, it is essential to distinguish the duration of the entire cycle from the time the application is actually stopped.

JFR helps correlate events sharing the same **GC ID** to see which phases belong to a collection, how the heap changes, and what the longest pause is.

## 2. Important GC events

Event names and level of detail depend on the JDK, JVM vendor, collector, and recording settings. On HotSpot JDK 24, commonly useful events include:

| JFR event | Key data | Used for analyzing |
| --- | --- | --- |
| `jdk.GarbageCollection` | GC ID, collector name, cause, duration, sumOfPauses, longestPause | Overview of each collection and its associated pauses |
| `jdk.GCHeapSummary` | GC ID, Before GC/After GC timestamp, heap used, and heap space | Comparing heap before/after collection |
| `jdk.GCPhasePause` | GC ID, phase name, and duration | Identifying stop-the-world phases |
| `jdk.GCPhaseConcurrent` | GC ID, phase name, and duration | Viewing collector work running concurrently |
| `jdk.ObjectAllocationSample` | Object class, sample weight, thread, and stack trace | Finding sources of allocation pressure |
| `jdk.GCReferenceStatistics` | Reference type and count processed | Investigating Soft/Weak/Phantom reference processing overhead |
| `jdk.TenuringDistribution` | Object age and size by age | Tracking objects surviving across multiple young GCs |
| `jdk.EvacuationInformation` | Regions in collection set, bytes copied, regions freed | Investigating G1 evacuation |
| `jdk.AllocationRequiringGC` | Allocation size and GC ID being waited on | Finding allocations forced to wait for GC |
| `jdk.GCConfiguration` | Collector, GC thread count, pause target, and GC settings | Understanding the recorded environment |
| `jdk.GCHeapConfiguration` | Heap min/initial/max and layout information | Comparing results against heap limits |

Some collectors have their own events, such as `jdk.G1GarbageCollection`, `jdk.G1HeapSummary`, `jdk.YoungGarbageCollection`, `jdk.OldGarbageCollection`, or detailed ZGC/Shenandoah events. Do not assume all of these events exist or are enabled on every JDK.

Use the metadata of the JDK/recording itself to check event names and fields:

```bash
jfr metadata --events GarbageCollection,GCHeapSummary,GCPhasePause,GCPhaseConcurrent,ObjectAllocationSample
```

If you already have a recording file, you can read metadata from that file:

```bash
jfr metadata --events GarbageCollection recording.jfr
```

## 3. Distinguishing GC duration from pause duration

This is the most important point when reading JFR.

`jdk.GarbageCollection.duration` represents the duration of the collection event. For collectors with concurrent work, the duration of a cycle can be much longer than the time the application is stopped.

The `jdk.GarbageCollection` event also has two dedicated fields:

- **`sumOfPauses`:** total time Java execution was paused during that collection.
- **`longestPause`:** the single longest pause during that collection.

`jdk.GCPhasePause` records the duration of each pause phase. `jdk.GCPhaseConcurrent` records phases the collector runs concurrently; these phases do not mean the application is completely stopped.

For example, with G1:

- An old/concurrent GC cycle may span several seconds.
- During that cycle, the application continues running during the concurrent phases.
- The cycle may contain only a few short pauses.
- Therefore, looking at `duration` and treating the entire time as an application pause leads to the wrong conclusion.

When investigating latency, prioritize `sumOfPauses`, `longestPause`, `GCPhasePause` events, and pause percentile statistics. Use `duration` and `GCPhaseConcurrent` to understand how long the collector works in the background.

## 4. Reading GC ID and heap summary before/after GC

`jdk.GarbageCollection` has a `gcId` field. Related phase and heap summary events may also carry the same GC ID.

`jdk.GCHeapSummary` provides:

- `when`: the summary point, typically `Before GC` or `After GC`.
- `heapUsed`: bytes currently used in the heap at the time of the event.
- `heapSpace`: information about the corresponding heap space.

Reading workflow:

1. Find a `jdk.GarbageCollection` event with the GC ID to investigate.
2. Note the collector name, cause, duration, sumOfPauses, and longestPause.
3. Filter `jdk.GCHeapSummary` events with the same GC ID.
4. Pair the Before GC summary with After GC.
5. Inspect `GCPhasePause` and `GCPhaseConcurrent` events with the same GC ID.
6. Compare against preceding and succeeding collections in the recording.

Heap Before/After helps observe trends, but you should not always subtract the two values and treat the result as the exact number of object bytes reclaimed. With concurrent collectors, allocations can occur while a collection is running; how snapshots are calculated and timed also depends on the collector.

To evaluate a memory leak, observe the post-GC heap level across multiple cycles under a comparable workload. If the post-GC baseline steadily climbs, inspect object retention using a heap dump, JFR old-object sampling, or MAT.

## 5. Analyzing GC causes

The `cause` field of `jdk.GarbageCollection` indicates why the JVM triggered the collection. Exact values depend on the collector and JDK version.

Some common cause groups:

| Cause group | Interpretation |
| --- | --- |
| Allocation/evacuation pressure | The application allocates objects rapidly or allocation regions need to be reclaimed |
| System/explicit GC | The application or a library calls `System.gc()`/`Runtime.gc()`; the collector may handle it according to configuration |
| Metadata/Metaspace threshold | The JVM needs to handle metadata/class loading pressure |
| G1 humongous allocation | Large object allocations affecting G1 regions |
| Diagnostic/last-ditch collection | The JVM performs a collection in a special situation or under resource pressure |

Do not draw conclusions from the cause string alone. Combine:

- Collector name and collection type (young/old/full).
- Heap before/after.
- Collection frequency.
- Pause duration and phases.
- Allocation samples.
- GC configuration and heap max.
- Application workload at the same timestamp.

If the cause is repeated explicit GC, locate the call site or library invoking GC before considering changing explicit GC behavior. Do not mechanically disable `System.gc()` without understanding the application.

## 6. Reading pause distribution instead of only averages

A low average metric can hide a few very long pauses. For latency-sensitive applications, pay attention to percentiles and maximum values.

Metrics to track:

- **Pause count:** number of pauses in the recorded interval.
- **Total pause time:** total time the application was stopped due to GC.
- **Minimum/median/average:** typical pause levels.
- **P90/P95/P99/P99.9:** the tail of the distribution, reflecting rare but high-impact pauses.
- **Maximum pause:** the longest pause observed.

Use the built-in view:

```bash
jfr view gc-pauses gc-analysis.jfr
```

A test run on HotSpot JDK 24.0.2 with a small allocation workload and bounded heap produced the following illustrative output:

```text
GC Pauses

Total Pause Time: 206 ms
Number of Pauses: 447
Minimum Pause Time: 0.00390 ms
Median Pause Time: 0.493 ms
Average Pause Time: 0.460 ms
P90 Pause Time: 0.970 ms
P95 Pause Time: 1.07 ms
P99 Pause Time: 1.27 ms
P99.9% Pause Time: 3.12 ms
Maximum Pause Time: 3.12 ms
```

These are numbers from one specific run, not targets or baseline values for other applications. When evaluating production, use a recording that is long enough and has a representative workload.

You can calculate an approximate pause time ratio:

`GC pause ratio (%) = total GC pause time / recording wall-clock duration × 100`

This ratio represents the fraction of time the application was stopped by GC during the measured interval. It is not the CPU time consumed by GC workers. Do not manually sum durations of nested phases because that may double-count; prefer the `gc-pauses` statistics or the aggregated pause fields on the GC event.

## 7. Using built-in JFR views

JDK 24 provides views to summarize events without having to parse the file manually.

| View | Content |
| --- | --- |
| `gc` | GC ID, collection type, heap before/after, and longest pause |
| `gc-pauses` | Total pause, count, median, average, percentiles, and maximum |
| `gc-parallel-phases` | Parallel GC phases |
| `gc-concurrent-phases` | Concurrent GC phases |
| `gc-cpu-time` | CPU time spent on GC |
| `gc-references` | Reference processing statistics |
| `gc-configuration` | Collector configuration |
| `heap-configuration` | Heap configuration |
| `safepoints` | Safepoint statistics, helping distinguish GC pauses from other safepoints |

Examples:

```bash
jfr view gc gc-analysis.jfr
jfr view gc-pauses gc-analysis.jfr
jfr view gc-concurrent-phases gc-analysis.jfr
jfr view gc-parallel-phases gc-analysis.jfr
jfr view gc-cpu-time gc-analysis.jfr
jfr view gc-references gc-analysis.jfr
jfr view safepoints gc-analysis.jfr
```

`jfr view gc` helps locate anomalous collections. Then switch to `gc-pauses` to assess latency impact, or `gc-concurrent-phases` to see how long the collector worked in the background.

## 8. Analyzing GC with jfr summary and jfr print

Start with summary to see which events are in the recording and the count of each type:

```bash
jfr summary gc-analysis.jfr
```

Some lines that may appear:

```text
Event Type                         Count
----------------------------------------
jdk.GCPhaseConcurrent               ...
jdk.GCHeapSummary                   ...
jdk.GCPhasePause                    ...
jdk.GarbageCollection               ...
jdk.ObjectAllocationSample          ...
jdk.YoungGarbageCollection          ...
jdk.OldGarbageCollection            ...
```

Phase event counts are usually higher than the number of collections. A single GC can produce multiple phase events, multiple heap summaries, and multiple collector-specific events. Do not use the total count of `GCPhasePause` or `GCPhaseConcurrent` to infer the number of GC cycles.

Print the needed events:

```bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.GCPhasePause,jdk.GCPhaseConcurrent gc-analysis.jfr
```

Print allocation samples and stack traces:

```bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 32 gc-analysis.jfr
```

Print events for a specific collector when supported by the JDK:

```bash
jfr print --events jdk.G1GarbageCollection,jdk.G1HeapSummary,jdk.EvacuationInformation gc-analysis.jfr
```

You can filter by category:

```bash
jfr print --categories "GC" gc-analysis.jfr
```

Use `jfr metadata --events <event-name>` to inspect event fields and descriptions on your exact JDK. Event names and fields can vary across versions or collectors.

## 9. Analyzing allocation pressure

Frequent GC can be caused by an application creating many objects, even when there is no memory leak.

`jdk.ObjectAllocationSample` is an allocation sampling event. Key fields:

- `objectClass`: class of the sampled object.
- `weight`: relative size represented by the sample.
- `eventThread`: thread performing the allocation.
- `stackTrace`: call stack where the sample was recorded.

The `weight` field helps aggregate allocation statistics by class, thread, or stack trace. These are weighted samples, not an exact list of every allocated object.

Useful views:

```bash
jfr view allocation-by-class gc-analysis.jfr
jfr view allocation-by-site gc-analysis.jfr
jfr view allocation-by-thread gc-analysis.jfr
jfr view thread-allocation gc-analysis.jfr
```

How to analyze:

1. Find classes with high allocation weight.
2. Check which threads generate the most allocations.
3. Open `allocation-by-site` to find methods and stack traces.
4. Correlate allocation timestamps with young GCs and pauses.
5. Inspect code creating objects in loops, serialization/deserialization, logging, mapping, or buffer creation.
6. Check whether objects are retained for a long time or allocated and reclaimed quickly.

Allocation pressure and memory leaks are two different problems. A method may allocate millions of short-lived objects while the post-GC heap remains stable. Conversely, a cache that creates few objects but retains them forever can cause the live set to grow steadily.

## 10. Reading tenuring, promotion, and reference processing

Several detailed events help understand objects surviving across multiple GC cycles.

**`jdk.TenuringDistribution`** records object ages and sizes at each age. If many objects survive young GC and are promoted to the old generation, old gen can grow faster.

**`jdk.GCReferenceStatistics`** records the number of references processed by type. Reference processing can increase GC time when an application heavily uses `SoftReference`, `WeakReference`, `PhantomReference`, or related constructs.

**`jdk.EvacuationInformation`** can provide collection set data, freed regions, and bytes copied, which is especially useful with G1.

When promotion increases:

- Check caches, sessions, queues, and collections holding objects.
- Compare old-gen occupancy across GC cycles.
- Look for objects with high age or large retained size.
- Check whether objects are held by static fields, listeners, `ThreadLocal`, or reference chains.

When reference processing increases:

- Identify which reference type accounts for the largest count.
- Check libraries/caches using references.
- Evaluate reference processing time alongside pause phases.
- Do not change reference types based solely on a single event count.

Detailed events may be disabled in recording settings or unavailable on the active collector.

## 11. Recognizing common GC patterns

### Frequent Young GC but stable post-GC heap

The application may have a high allocation rate with mostly short-lived objects. Check allocation-by-site, GC frequency, and throughput before changing heap size or the collector.

### Old Gen grows after multiple cycles

If post-GC heap grows steadily under a similar workload, the live set may be increasing. Find classes with unusual allocation/retention and use a heap dump or old-object sampling to trace reference paths.

### Long pauses or rising P99

Check the GC ID with the highest longest pause, its cause, `GCPhasePause`, and sub-phases. Correlate heap occupancy, promotion, evacuation, and safepoints at the same timestamp.

### Long concurrent phases but short pauses

The collector may be doing significant background work. The application is not necessarily paused during that entire interval. Check GC CPU time, CPU saturation/throttling, and concurrent phase durations.

### Frequent Full/old collections

Check old-gen occupancy, allocation rate, promotion, heap max, and GC cause. An old collection cycle does not automatically mean a memory leak.

### Low GC pauses but application latency remains high

The root cause may lie in lock contention, I/O, scheduler, other safepoints, CPU throttling, or external dependencies. Use additional JFR thread, monitor, socket, file, and safepoint events to find the cause.

## 12. Distinguishing allocation pressure from memory leaks

| Symptom | Allocation pressure | Memory leak/retention |
| --- | --- | --- |
| Allocation samples | High | May be high or low |
| Young GC frequency | May increase | May increase |
| Post-GC heap | Usually stable under steady workload | Tends to grow over time |
| Old Gen | May remain stable | May grow continuously |
| Object lifetime | Many short-lived objects | Unneeded objects remain reachable |
| How to investigate | Allocation-by-site/thread/class | Heap dump, old-object sample, GC roots |

A workflow to distinguish them:

1. Capture JFR over a representative workload interval.
2. Compare allocation rate and GC frequency.
3. Track post-GC heap across multiple cycles.
4. If the post-GC baseline is stable, prioritize investigating allocation pressure/throughput.
5. If the baseline grows, inspect retained classes, old-object samples, and a heap dump.
6. Use MAT to inspect the dominator tree, retained size, and path to GC roots.
7. Repeat the recording after fixing to verify.

JFR `ObjectAllocationSample` shows where allocations occur; it does not by itself prove objects remain alive. To find retained objects, you need retention data and a reference graph.

## 13. Recording JFR for GC analysis

List JVMs:

```bash
jcmd -l
```

Check command help:

```bash
jcmd 18420 help JFR.start
```

Start a 60-second recording:

```bash
jcmd 18420 JFR.start name=gc-analysis settings=profile duration=60s filename=/var/tmp/gc-analysis.jfr
```

Check recording status:

```bash
jcmd 18420 JFR.check name=gc-analysis
```

When the duration expires, JFR finishes automatically and writes the file. Then:

```bash
jfr summary /var/tmp/gc-analysis.jfr
jfr view gc /var/tmp/gc-analysis.jfr
jfr view gc-pauses /var/tmp/gc-analysis.jfr
```

If you want continuous recording and on-demand snapshots:

```bash
jcmd 18420 JFR.start name=gc-live settings=default disk=true maxage=30m maxsize=256m
jcmd 18420 JFR.dump name=gc-live filename=/var/tmp/gc-snapshot.jfr
jcmd 18420 JFR.stop name=gc-live filename=/var/tmp/gc-final.jfr
```

`JFR.dump` exports current data while the recording continues; `JFR.stop` ends the recording and writes remaining data.

**Choosing settings:**

- `default.jfc`: collects a built-in set of events with low overhead, suitable for continuous recording.
- `profile.jfc`: collects more data with higher overhead; use for short intervals when deep analysis is needed.
- You can inspect options and event settings using `jcmd <pid> help JFR.start` and `jfr configure`.

The impact of `JFR.start` depends on settings. Do not run profile recordings continuously in production by default. Set `maxage` and `maxsize` when you need to bound disk usage.

The file path should be in an existing directory where the JVM has write permission. With the `jcmd` command line, use a simple path without spaces to avoid the parser splitting the filename into multiple arguments.

## 14. Collecting GC roots when suspecting a memory leak

JFR has a `path-to-gc-roots` option to record reference paths to GC roots for objects tracked during the recording.

Example:

```bash
jcmd 18420 JFR.start name=gc-roots settings=profile path-to-gc-roots=true duration=60s filename=/var/tmp/gc-roots.jfr
```

GC roots information is useful when investigating why objects remain reachable. However, collecting paths can consume time and resources. Enable it only when a memory leak is already suspected and deeper retention data is needed.

Do not treat JFR `path-to-gc-roots` as a complete replacement for a heap dump. For large object graphs or when you need retained size/dominator tree views, a heap dump and MAT remain the right tools.

## 15. Combining JFR with GC unified logging

JFR is well suited for event analysis, allocations, stack traces, and timelines. GC logs are useful when you need detailed, continuous text logs or want to cross-check collector configuration.

Enable GC and safepoint logging at JVM startup:

```bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
```

You can analyze:

- GC timestamps and collector.
- Heap occupancy before/after collection.
- Phases and pauses.
- Safepoint synchronization.
- Collector region/evacuation details if logged.

JFR and GC logs complement each other. Use JFR to filter events and locate stack traces; use GC logs to cross-check details via unified logging configuration.

## 16. Practical Java 17 example: generating allocations for GC analysis

This example creates short-lived allocations and retains some byte arrays in a bounded list. The goal is to generate observable GC activity, not a benchmark.

File **`GcWorkload.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class GcWorkload {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();
    private static volatile byte[] transientArray;

    private GcWorkload() {
    }

    public static void main(String[] args) throws Exception {
        long deadline = System.nanoTime() + 11_000_000_000L;
        long allocations = 0;

        while (System.nanoTime() < deadline) {
            for (int i = 0; i < 24; i++) {
                transientArray = new byte[256 * 1024];
                transientArray[0] = (byte) i;
                allocations++;
            }

            RETAINED.addLast(new byte[1024 * 1024]);
            if (RETAINED.size() > 12) {
                RETAINED.removeFirst();
            }

            Thread.sleep(50);
        }

        System.out.println("allocations=" + allocations);
        System.out.println("retainedChunks=" + RETAINED.size());
    }
}
```

Compile:

```bash
javac --release 17 GcWorkload.java
```

Run with G1 and a bounded heap while recording JFR for 8 seconds:

```bash
java -Xms32m -Xmx64m -XX:+UseG1GC -XX:StartFlightRecording=filename=gc-analysis.jfr,settings=profile,duration=8s GcWorkload
```

The two stdout lines from the program in a test run:

```text
allocations=5088
retainedChunks=12
```

Actual allocation counts vary with machine speed and scheduling; the retained list is capped at 12 chunks.

After the program finishes, analyze the file:

```bash
jfr summary gc-analysis.jfr
jfr view gc gc-analysis.jfr
jfr view gc-pauses gc-analysis.jfr
jfr view allocation-by-site gc-analysis.jfr
jfr view allocation-by-class gc-analysis.jfr
```

Look for `byte[]` in the allocation views and verify whether the stack trace points to `GcWorkload.main`. In the `gc` view, compare heap before/after and longest pause. In the `gc-pauses` view, inspect percentiles rather than looking only at the average.

To view detailed events:

```bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.GCPhasePause,jdk.GCPhaseConcurrent,jdk.ObjectAllocationSample gc-analysis.jfr
```

Open `gc-analysis.jfr` in JMC to view the timeline, select a GC event, and trace phases sharing the same GC ID.

## 17. Analyzing with Java Mission Control

Java Mission Control (JMC) provides a GUI to open `.jfr` files and analyze events along a timeline.

Basic workflow:

1. Open JMC and select the recording.
2. View the Garbage Collections page to check GC count, pauses, and heap.
3. Select a collection with a high longest pause.
4. Open event details and inspect cause, collector, and GC ID.
5. Inspect pause/concurrent phases sharing the same GC ID.
6. Switch to Allocation to find classes, threads, and stack traces creating many objects.
7. Cross-check heap before/after and old generation trends.
8. Save your findings along with the recorded time range and workload.

JMC displays rich event details and linked charts. Page names and layouts may vary by JMC version. Events not enabled in the recording will not appear completely in the UI.

## 18. Common mistakes when analyzing GC with JFR

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Treating `GarbageCollection.duration` as pause time | Duration may include concurrent work | Read `sumOfPauses`, `longestPause`, and `GCPhasePause` |
| Looking only at average pause | Average hides tail latency | Inspect P95/P99/P99.9 and maximum |
| Treating each `GCPhasePause` as a GC cycle | One cycle can have multiple phases/pauses | Use GC ID and `GarbageCollection` |
| Using phase event count as GC count | Phase events can outnumber collections | Use `jdk.GarbageCollection` or `jfr view gc` |
| Treating allocation samples as exact object counts | `ObjectAllocationSample` is weighted statistics | Read sample weight and look at trends by class/site/thread |
| Concluding a leak from rising pre-GC heap | Uncollected objects may still sit in the heap | Compare post-GC baseline across multiple cycles |
| Treating post-GC heap as the absolute live set | Collector and concurrent allocations affect snapshots | Cross-check heap summary, old-gen, retention, and heap dump |
| Looking only at GC while ignoring CPU | Concurrent GC can be slowed by CPU contention/throttling | Check GC CPU time, CPU load, and safepoints |
| Using `profile` continuously | Profile has higher overhead than default | Use default for long recordings, profile for short intervals |
| Comparing two recordings with different workloads | Different loads produce different GC metrics | Compare under the same workload, heap, and environment |
| Tuning multiple flags at once | Cannot isolate which change caused the effect | Change one factor at a time and re-measure |

## 19. Production GC investigation workflow

1. Identify the symptom: latency spikes, high CPU, growing heap, overly frequent GC, or `OutOfMemoryError`.
2. Record JDK version, collector, heap min/max, container limits, and workload.
3. Start a recording with `default` or `profile` for an appropriate duration.
4. Check `jfr summary` to confirm the recording contains GC events.
5. Use `jfr view gc` to locate anomalous collections and heap before/after.
6. Use `jfr view gc-pauses` to inspect pause count, P95/P99, and maximum.
7. Use `gc-concurrent-phases` and `gc-cpu-time` to evaluate background work.
8. Use `allocation-by-site`/`class`/`thread` to find sources of allocation pressure.
9. Check cause, tenuring, reference processing, and collector-specific events.
10. If the post-GC live set grows, consider old-object sampling or a heap dump/MAT.
11. Correlate GC events with application latency, CPU, safepoints, logs, and deployments.
12. Propose one change with a clear hypothesis, re-measure under the same workload, and compare before/after.
13. Protect `.jfr` files, GC logs, and heap dumps; delete or archive according to retention policy.

Do not change collectors or heap flags just because of a single high pause. First determine whether the issue stems from allocation rate, live set, pause phases, CPU contention, or resource configuration.

## 20. Takeaways

- JFR records GC events along a timeline and links phases via GC ID.
- `jdk.GarbageCollection` provides collector, cause, duration, sumOfPauses, and longestPause.
- `jdk.GCHeapSummary` records heap before/after; `GCPhasePause` and `GCPhaseConcurrent` separate application-stopping work from background work.
- `jfr view gc` summarizes collections; `jfr view gc-pauses` provides pause distributions and percentiles.
- Use P95/P99/maximum when investigating latency; do not look only at the average.
- `ObjectAllocationSample` includes weights and stack traces, useful for finding allocation pressure, but it does not prove objects are retained.
- `TenuringDistribution`, `GCReferenceStatistics`, and `EvacuationInformation` help investigate promotion, reference processing, and G1 evacuation.
- Post-GC heap growing across multiple cycles can indicate retention; use a heap dump/GC roots to identify the cause.
- `default.jfc` suits long recordings with low overhead; `profile.jfc` collects more data with higher overhead.
- Combine JFR, JMC, GC unified logging, heap dumps, and metrics for reliable conclusions.
- Evaluate GC changes under a comparable workload and change one factor at a time.

Analyzing Garbage Collection with JFR helps you move from vague observations like "GC runs a lot" to concrete evidence on causes, pause percentiles, heap trends, allocation sites, and collector phases. From there, you can pinpoint the right investigation path and improve latency/throughput based on measured data.

## References

- [Java Flight Recorder — Java SE 24](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf)
- [JFR Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [jcmd Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Garbage-First Garbage Collector Tuning — Java SE 24](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html)

# Old Collection: Monitoring and Diagnosing Old Generation Reclamation

**Old collection** is garbage collection activity that affects the **Old Generation** region of the Java heap. Objects that survive long enough can be promoted from the Young Generation to the Old Generation; as occupancy in this region grows, the JVM needs to determine which objects are still reachable and reclaim memory occupied by objects that are no longer in use.

In HotSpot, the terminology and how the Old Generation is reclaimed depend on the garbage collector. With G1, old region reclamation typically happens incrementally across multiple **Mixed collections** following a concurrent marking cycle. With Serial or Parallel GC, an old-generation collection is usually associated with a full old-generation collection. Therefore, not every old collection should be equated with a **Full GC**.

JFR also defines the `jdk.OldGarbageCollection` event, which provides the timestamp, duration, and GC identifier for an old garbage collection when the collector emits that event. This lesson explains how to read events and GC logs, determine the impact on pause time, and distinguish memory pressure from a memory leak.

## 1. Where does the Old Generation sit in the Java heap?

Generational collectors divide the Java heap into regions with different roles:

- **Eden:** where most new objects are allocated.
- **Survivor:** where objects that survive a young collection can remain before being promoted.
- **Old Generation:** where objects that have survived enough collections are stored, or where objects are allocated directly into the old space according to the collector's policy.

When a young collection occurs, the JVM finds reachable objects in Eden and Survivor. Live objects may be copied to Survivor or promoted to the Old Generation. Unreachable objects can be reclaimed.

The Old Generation typically holds longer-lived objects such as caches, sessions, shared data structures, and application state. However, object age does not prove an object is still needed: an unintentionally retained reference can also keep an object alive and occupy old space.

The **live set** is the amount of heap still in use after unreachable objects have been reclaimed. Tracking the live set across multiple collections under a steady workload is a useful way to tell whether the old space is growing abnormally.

## 2. Old collection, young collection, and Full GC

Common terms:

| Term | Meaning |
|---|---|
| Young collection | Collects regions belonging to the Young Generation, typically Eden and Survivor. |
| Old collection | Collects or reclaims regions belonging to the Old Generation; implementation depends on the collector. |
| Mixed collection | In G1, a pause that collects both young regions and a selected set of old regions. |
| Full GC | Collects the entire Java heap; typically has a long pause and may compact the heap. |
| Concurrent marking | A phase that marks live objects, mostly running concurrently with application threads in G1. |

In older documentation, **minor GC** usually refers to a young collection and **major GC** usually refers to an old-generation collection. These two terms do not have a uniform meaning across all collectors and JVM versions. When reading logs, rely on the specific collection type, GC cause, phase, and collector.

A Full GC can reclaim the old generation, but an old collection is not necessarily a Full GC. G1 is the clearest example: it can reclaim old regions across multiple Mixed collections without needing a heap-wide Full GC.

## 3. Why does the Old Generation need to be collected?

An old collection can occur when:

- The Old Generation approaches an occupancy threshold that triggers the collector to start a marking or reclamation cycle.
- Many objects from the young generation survive and get promoted.
- The application creates many long-lived objects or retains references for a long time.
- Large/humongous objects occupy many old regions.
- The collector cannot reclaim space fast enough to keep up with allocation or promotion rates.
- The JVM receives an explicit GC request from `System.gc()` or an external tool.
- A diagnostic tool requests heap statistics or an operation that requires an old/full collection.

An old collection does not automatically indicate an error. Periodic collections can be normal behavior. You should evaluate frequency, pause duration, amount of memory reclaimed, and the live set after collection.

## 4. How garbage collectors handle the Old Generation

| Collector | How old space is handled | What to watch out for |
|---|---|---|
| Serial GC | Collects the old generation in stop-the-world phases; Full GC can compact the heap. | Pause depends on heap size and live object volume. |
| Parallel GC | Can reclaim and compact the old generation as a whole during a Full GC. | High throughput, but old/full pauses can be long. |
| G1 GC | Marks old regions concurrently with the application, then reclaims a set of old regions across multiple Mixed collections. | Distinguish Mixed collections from Full GC fallbacks. |
| ZGC and Shenandoah | Use concurrent phases and their own reclamation mechanisms; generation and event/log naming depend on mode and version. | Do not infer the pause model solely from the phrase "old collection". |

Events and log tags also depend on the collector. If a recording does not contain `jdk.OldGarbageCollection`, you can still analyze `jdk.GarbageCollection`, GC logs, and the phase events provided by the collector.

## 5. G1: Old Generation reclamation cycle

G1 divides the heap into **regions**. Eden, Survivor, and Old are logical groups of regions, not necessarily contiguous in memory addresses.

A G1 cycle has two major phases:

1. **Young-Only phase:** G1 performs young collections and promotes live objects into old regions.
2. **Space-Reclamation phase:** after concurrent marking completes, G1 performs multiple Mixed collections to reclaim additional old regions.

A typical marking cycle includes:

- **Concurrent Start:** a young pause that also initiates the marking process.
- **Concurrent marking:** identifies live objects in old regions, mostly running concurrently with the application.
- **Remark:** completes marking and processes references.
- **Cleanup:** summarizes results and identifies reclaimable regions.
- **Mixed collections:** collects young regions along with a selected set of old regions.

G1 prioritizes old regions with a high ratio of dead objects and good reclamation efficiency. It spreads the work across multiple pauses to stay within its pause-time target.

## 6. How is a G1 Mixed collection different from a Full GC?

A **Mixed collection** collects young regions and a set of old regions in the same collection set. After each Mixed collection, G1 can continue reclaiming other old regions in subsequent pauses. Once enough efficient regions have been reclaimed, G1 returns to the Young-Only phase.

A **Full GC** is a fallback that collects and compacts the entire heap. In G1, the log `Pause Full (G1 Compaction Pause)` is a sign that warrants investigation, especially when preceded by an evacuation failure with reason `Allocation`.

A Full GC can occur when the application allocates objects faster than G1 can reclaim them, concurrent marking does not finish in time to start Space-Reclamation, or there are many humongous objects. An explicit `System.gc()` can also be the cause.

Do not treat a Mixed collection as an error just because it touches the Old Generation. Observe the pause time, the number of old regions reclaimed, and the old occupancy trend over the entire cycle.

## 7. Humongous objects and Old Generation pressure

In G1, an object whose size is half a region or larger is called a **humongous object**. These objects are allocated directly into the old generation as a sequence of contiguous regions.

Large arrays, large buffers, or long-lived payloads can increase the number of humongous regions. Because they require contiguous regions, G1 can struggle to allocate even when overall free space appears sufficient.

The GC log may show:

~~~text
[0.201s][info][gc,heap] GC(0) Old regions: 2->19
[0.201s][info][gc,heap] GC(0) Humongous regions: 0->0
~~~

These are region counts before and after collection, not byte counts. Cross-reference them with the heap region size, total heap, and allocated object sizes.

If humongous regions spike, check large allocations, buffer retention, file read/write patterns, and payload handling. Only tune `-XX:G1HeapRegionSize` after you have evidence that region size is the limiting factor.

## 8. Enabling Unified GC Logging

From JDK 9 onward, use Unified Logging with `-Xlog`. A detailed configuration suitable for starting an investigation:

~~~bash
java -Xlog:gc*,gc+phases=debug:file=gc.log:uptime,level,tags -jar app.jar
~~~

Meaning:

- `gc*`: logs tags starting with `gc`, including collections, heap, and related information.
- `gc+phases=debug`: logs detailed GC phases.
- `file=gc.log`: writes to a file instead of the console.
- `uptime,level,tags`: prepends JVM uptime, log level, and tags to each line.

G1 also recommends starting diagnostics with:

~~~bash
java -Xlog:gc*=debug -jar app.jar
~~~

You can reduce output or focus on a specific area once you understand the overall log.

## 9. Log tags and Old collection messages

Unified Logging attaches tags to messages. Oracle illustrates a line with the `gc,old` tag as follows:

~~~text
[6.567s][info][gc,old] Old collection complete
~~~

This is an example of a JVM log message and tag set. Not every collector emits this exact line or uses the same phrasing. With G1, the more useful entries are usually `Pause Young`, `Pause Full`, `Mixed`, `Old regions`, `Humongous regions`, and the phase lines.

You can filter log tags when needed, for example:

~~~bash
java -Xlog:gc+heap=info,gc+phases=debug -jar app.jar
~~~

To understand the collection type and cause, keep general `gc` logging enabled in the early stages. Enabling a tag that is too narrow can omit the context needed to correlate lines sharing the same GC ID.

## 10. Reading a GC log line

Example:

~~~text
[0.201s][info][gc] GC(0) Pause Full (System.gc()) 31M->14M(64M) 7.278ms
~~~

| Component | How to interpret it |
|---|---|
| `0.201s` | JVM uptime when the log line was written. |
| `info` | Log level. |
| `gc` | Message tag. |
| `GC(0)` | GC ID, used to correlate lines belonging to the same collection. |
| `Pause Full` | Collection and pause type. |
| `System.gc()` | Recorded cause for the collection. |
| `31M->14M(64M)` | Heap used before and after GC, along with current heap capacity. |
| `7.278ms` | Pause duration recorded on that line. |

The values above are examples from a test run. Timings, heap sizes, causes, and log text vary by collector, workload, and JDK.

## 11. Reading heap and Old regions before/after collection

To evaluate reclamation effectiveness, correlate lines with the same GC ID:

~~~text
[0.201s][info][gc,heap] GC(0) Old regions: 2->19
[0.201s][info][gc] GC(0) Pause Full (System.gc()) 31M->14M(64M) 7.278ms
~~~

A few notes:

- `Old regions: X->Y` is the region count before and after, not old-generation bytes.
- `Heap: X->Y` or the overall heap line indicates used heap before/after.
- `Humongous regions: X->Y` helps spot pressure from large objects.
- With a Full GC, old regions after collection can still increase if many objects are retained and moved into the old generation.
- A collection can free significant heap space without returning all committed memory to the operating system.

To compare over time, inspect multiple consecutive collections under a similar workload. A single log line is not enough to conclude a memory leak or misconfigured heap.

## 12. Evaluating pause time and reclamation effectiveness

Metrics to examine together:

1. **Old occupancy before GC:** is the old space nearly full?
2. **Old occupancy after GC:** does the post-collection baseline drop?
3. **Reclaimed space:** how significant is the difference in used bytes or region count?
4. **Pause duration:** does a single collection slow down requests?
5. **Sum of pauses:** total time the application was actually paused during the observation window.
6. **Frequency:** are old/full collections happening too close together?
7. **Live-set trend:** across multiple collections, is the volume of live objects steadily growing?

With concurrent collectors, total collection duration can be long while the application is only paused during specific phases. Therefore, total pause time usually reflects latency impact better than total background GC time.

## 13. JFR event jdk.OldGarbageCollection

Java Flight Recorder provides the event:

~~~text
jdk.OldGarbageCollection
~~~

This event provides additional details for old garbage collections. On JDK 24 as tested, the event metadata includes:

| Field | Meaning |
|---|---|
| `startTime` | Event start timestamp. |
| `duration` | Event duration. |
| `gcId` | GC identifier to link with other events from the same collection. |

`jdk.OldGarbageCollection` does not contain full cause information on its own. Correlate it with `jdk.GarbageCollection` using `gcId`, as that event can provide the collector name, cause, sum of pauses, and longest pause.

`jdk.GCPhasePause` provides pause phases with their durations and GC ID. Recorded event types and fields depend on the collector, JDK, and event settings.

## 14. Recording JFR on a running JVM

Find the process:

~~~bash
jcmd -l
~~~

Start a recording:

~~~bash
jcmd <pid> JFR.start name=old-gc settings=profile maxage=30m maxsize=512M jdk.OldGarbageCollection#enabled=true jdk.GarbageCollection#enabled=true jdk.GCPhasePause#enabled=true
~~~

Check the recording:

~~~bash
jcmd <pid> JFR.check name=old-gc verbose=true
~~~

Take a snapshot without stopping the recording:

~~~bash
jcmd <pid> JFR.dump name=old-gc filename=old-gc-snapshot.jfr
~~~

When enough data has been collected, stop and save the final file:

~~~bash
jcmd <pid> JFR.stop name=old-gc filename=old-gc-final.jfr
~~~

`JFR.dump` only copies existing data to a file; the recording continues running. `JFR.stop` is what ends the recording.

`default.jfc` is suited for long, continuous recordings because it has lower overhead. `profile.jfc` collects more data but can incur higher overhead; use it only for windows where deep profiling is needed.

## 15. Analyzing JFR with the jfr CLI

View a recording overview:

~~~bash
jfr summary old-gc-snapshot.jfr
~~~

Print old collection events:

~~~bash
jfr print --events jdk.OldGarbageCollection old-gc-snapshot.jfr
~~~

Print related events to correlate GC IDs:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause old-gc-snapshot.jfr
~~~

Abbreviated example from a recording:

~~~text
jdk.OldGarbageCollection {
  duration = 7.18 ms
  gcId = 0
}

jdk.GarbageCollection {
  duration = 7.18 ms
  gcId = 0
  name = "G1Full"
  cause = "System.gc()"
  sumOfPauses = 7.18 ms
  longestPause = 7.18 ms
}
~~~

`gcId = 0` indicates that both events belong to the same GC. This is how you link old collection duration with cause and pause metrics. Actual event output may include additional fields and vary in format across JDKs.

If the event does not appear, check event settings with `jcmd <pid> JFR.check name=old-gc verbose=true`, metadata with `jfr metadata --events jdk.OldGarbageCollection`, and which collector is active. You can use GC logs and `jdk.GarbageCollection` as supplementary diagnostic sources.

## 16. Analyzing with Java Mission Control

Java Mission Control (JMC) provides a UI for analyzing recordings:

1. Open the JFR file.
2. Check **Automated Analysis Results** and the Garbage Collections section.
3. Open **JVM Internals → Garbage Collections** to view the pause graph.
4. Check the counts of Full GC, Mixed GC, and when they occurred.
5. Read the Sum of Pauses and longest pause.
6. Cross-reference heap usage and the live-set trend.
7. Open event details to inspect cause, GC ID, duration, and stack/event context when available.

JMC makes it easy to spot trends over time and drill down into individual events. The CLI is better suited for quick event filtering or automated analysis.

## 17. Is a growing live set after Full GC a memory leak?

A notable warning sign is when the Old Generation keeps growing after multiple Full GCs while very little memory is reclaimed.

Example log:

~~~text
GC(10) Pause Full 45M->44M(48M) 90.0ms
GC(11) Pause Full 46M->45M(48M) 92.0ms
GC(12) Pause Full 47M->46M(48M) 95.0ms
~~~

If the workload and traffic are steady yet the post-GC live set keeps rising over time, objects may be retained unintentionally. However, this alone is not definitive proof of a memory leak. A heap that is too small for a legitimate live set or an increasing workload can produce similar symptoms.

Investigation workflow:

- Compare the post-GC live set at multiple points in time.
- Check which classes/object types are growing rapidly.
- Inspect allocation sites and reference retention.
- Use JMC Memory Leak Detection or a heap dump when you need to identify which objects are being retained.
- Check caches, collections, listeners, ThreadLocals, sessions, and static references.

A heap dump helps analyze the object graph and reference chains. JFR helps observe allocations and trends over time. The two data sources complement each other.

## 18. JFR Heap Statistics and explicit GC can skew measurements

JFR has a **Heap Statistics** feature. Oracle notes that this feature triggers an old garbage collection at the start and end of the recording. Those extra old GCs introduce pauses and can skew latency measurements.

Do not enable Heap Statistics when your goal is strictly performance profiling or measuring the application's natural pauses. Enable it only when investigating live set or memory leaks and you accept the overhead.

Similarly, `System.gc()` and `jcmd <pid> GC.run` request the JVM to perform an explicit GC. This operation can trigger a Full GC or old collection depending on the collector and configuration.

Do not call `System.gc()` repeatedly to fix a memory leak. It does not free reachable objects. When running benchmarks or latency tests, record any explicit GCs to avoid confusing them with collections caused by natural allocation pressure.

## 19. Using jcmd to inspect heap and class histograms

Some useful diagnostic commands:

~~~bash
jcmd <pid> GC.heap_info
~~~

This command provides an overview of the Java heap. Its impact is described as Medium in JDK 24.

You can also capture a class histogram:

~~~bash
jcmd <pid> GC.class_histogram
~~~

A class histogram shows heap statistics by class, useful for finding which object types consume the most memory. However, the JDK rates the impact of this command as High, depending on heap size and contents. Weigh traffic and pause impact before running it in production.

If you need to analyze the object graph or retained size, use a heap dump and a dedicated analysis tool. Do not use a histogram as sole proof of a memory leak.

## 20. Common symptoms and diagnostic directions

| Symptom | Possibilities to check | Investigation direction |
|---|---|---|
| Frequent Full GCs | High old occupancy, marking not finishing in time, allocation pressure, or explicit GC. | Read GC cause, evacuation failures, and live set. |
| Full GC reclaims very little | Many objects still reachable, heap too small for live set, or memory leak. | Compare post-GC baselines, JFR, and heap dump. |
| Long Mixed collection pauses | G1 has to evacuate many old regions or regions with high live-object ratio. | Enable `gc+ergo+cset=debug`, inspect predicted old region time. |
| Old regions growing rapidly | High promotion rate, long-lived allocations, or humongous objects. | Check allocation rate, `Humongous regions`, and object lifetimes. |
| JFR missing OldGarbageCollection | Event not enabled or collector does not emit this event. | Check JFR settings, metadata, and GC logs. |
| Old GC appears at recording start | JFR Heap Statistics may be enabled or explicit GC was invoked. | Check recording configuration and commands from external tools. |
| GC log shows `Pause Full (G1 Compaction Pause)` | G1 had to fall back to Full GC. | Look for evacuation failures, allocation pressure, and marking timing. |

## 21. Tuning G1 when old collections cause long pauses

Before changing JVM flags, identify the root cause from logs and workload. Oracle recommends starting with G1 defaults and tuning only when backed by evidence.

Some options that can help in specific cases:

- `-XX:G1MixedGCCountTarget`: increases the target number of Mixed collections to spread old-region reclamation across more pauses.
- `-XX:G1MixedGCLiveThresholdPercent`: adjusts the live occupancy threshold for selecting old regions as collection candidates.
- `-XX:G1HeapWastePercent`: adjusts the amount of heap waste G1 tolerates when ending the Space-Reclamation phase.
- `-XX:G1ReservePercent`: changes the reserve buffer to give G1 more headroom for evacuation.
- `-XX:InitiatingHeapOccupancyPercent`: sets the threshold for starting concurrent marking when adaptive IHOP is disabled.

Increasing the number of Mixed collections can reduce old-generation work per pause, but it extends the time needed to finish reclamation. Adjusting candidate thresholds can shorten pauses but also reduces the amount of space reclaimed.

For Full GCs caused by allocation pressure, consider reducing the allocation rate, shortening unnecessary object lifetimes, checking humongous allocations, and ensuring concurrent marking starts early enough. Only increase heap size when the live set and application requirements show the current heap is insufficient.

## 22. Java 17+ example: generating and analyzing Old collections with JFR

The following example retains several byte arrays in the Old Generation, triggers two explicit Full GCs, and records the relevant JFR events. This is a lab for observation, not a pattern for calling `System.gc()` in production applications.

File `OldCollectionDemo.java`:

~~~java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.Recording;

public class OldCollectionDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        Path output = Path.of(
                args.length == 0 ? "old-collection.jfr" : args[0]);

        try (Recording recording = new Recording()) {
            recording.setName("old-collection-demo");
            recording.setToDisk(true);
            recording.enable("jdk.GarbageCollection");
            recording.enable("jdk.OldGarbageCollection");
            recording.enable("jdk.GCPhasePause");
            recording.start();

            for (int i = 0; i < 48; i++) {
                RETAINED.add(new byte[256 * 1024]);
            }
            System.out.println("RETAINED_OBJECTS=" + RETAINED.size());

            System.gc();
            System.out.println("AFTER_FIRST_FULL_GC");

            RETAINED.clear();
            System.gc();
            System.out.println("AFTER_SECOND_FULL_GC");

            recording.stop();
            recording.dump(output);
        }

        System.out.println("JFR_FILE_CREATED=" + output.getFileName());
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/OldCollectionDemo.java
~~~

Run with G1, a fixed 64 MB heap, and detailed GC logging:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC "-Xlog:gc*,gc+phases=debug:file=gc.log:uptime,level,tags" -cp out OldCollectionDemo old-collection.jfr
~~~

Exact stdout:

~~~text
RETAINED_OBJECTS=48
AFTER_FIRST_FULL_GC
AFTER_SECOND_FULL_GC
JFR_FILE_CREATED=old-collection.jfr
~~~

Read the GC log with a text editor or search tool, paying attention to `Pause Full`, `Old regions`, `Humongous regions`, and the GC cause.

Read the JFR recording:

~~~bash
jfr summary old-collection.jfr
jfr print --events jdk.OldGarbageCollection old-collection.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause old-collection.jfr
~~~

In a test run on Azul OpenJDK 24.0.2 with G1, the program compiled with `javac --release 17`, ran successfully, and produced two `jdk.OldGarbageCollection` events and two `jdk.GarbageCollection`/`jdk.GCPhasePause` records. The events correlate via `gcId`; the GC log recorded `Pause Full (System.gc())` and `Old regions` counts before and after collection.

Durations, GC IDs, and event counts can vary across runs, collectors, and configurations. If the JVM is started with `-XX:+DisableExplicitGC`, the `System.gc()` calls in this example may be ignored.

## 23. Old collection diagnostic workflow

When an application experiences frequent old GCs or long pauses:

1. Identify the collector, JDK version, heap size, and JVM flags.
2. Enable `-Xlog:gc*,gc+phases=debug` to capture collection type, cause, occupancy, and phase durations.
3. For G1 Mixed collections, add `-Xlog:gc+ergo+cset=debug`.
4. Record JFR using `default` for long-term observation or `profile` for short-term profiling.
5. Correlate `jdk.OldGarbageCollection`, `jdk.GarbageCollection`, and `jdk.GCPhasePause` by `gcId`.
6. Compare old occupancy before/after GC and the live set across multiple cycles.
7. Check promotion, allocation rate, humongous regions, and explicit GCs.
8. If the live set grows under steady load, investigate object retention with JMC or a heap dump.
9. Change one parameter at a time, then re-measure pause, throughput, and reclamation.
10. Save GC logs, JFR recordings, JVM flags, and workload context so investigations can be compared.

Old collection is a normal part of generational heap management. Accurate diagnosis requires combining collection type, GC cause, old occupancy, reclaimed space, pause time, and live-set trend. When reading this data under the same GC ID and workload window, you can distinguish normal collections, allocation pressure, heap sizing issues, and memory leak candidates.

## References

- Oracle JDK 24 — [Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html).
- Oracle JDK 24 — [Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html).
- Oracle JDK 24 — [Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-memory-leaks.html).
- Oracle JDK 24 — [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
- Oracle JDK 24 — [The java Command and Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html).
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html).
- Oracle JDK 24 — [JFR API Package](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html).

# Measuring Garbage Collection (GC) in the JVM

## 1. Why Measure GC?

Garbage Collection (GC) automatically reclaims memory occupied by objects that are no longer reachable. This mechanism spares Java applications from manual object deallocation, but GC activity still consumes CPU, memory bandwidth, and occasionally pauses application threads.

Measuring GC means collecting data over a period with a representative load to answer:

- How many times does the JVM run GC, and which collection types are occurring?
- How long does each pause last? What are the P95, P99, and longest pause times?
- What percentage of the observed time is the application stopped due to GC?
- How much heap capacity remains after a collection?
- At what rate (bytes/second) is the application allocating objects?
- Are objects being promoted to the old generation too quickly?
- Are there Full GCs, evacuation failures, allocation stalls, or prolonged concurrent GC cycles?
- Is GC correlated with reduced throughput or increased request latency?

Measuring GC requires combining JVM logs, runtime metrics, application data, and profiling. A single number such as heap usage or GC count is not enough to conclude whether GC is a bottleneck.

## 2. Key GC Metrics

### 2.1. Collection Frequency and Count

Count collections by type over a time interval:

- Young collection: collects the region dedicated to young objects.
- Mixed collection: in G1, collects young regions along with a selected set of old regions.
- Full GC: a whole-heap collection according to the collector's implementation.
- Concurrent cycle: phases where the collector works concurrently with application threads.

Collection names and classifications depend on the collector. Do not assume all JVMs share the same concepts or event names.

High frequency may reflect a high allocation rate, a small heap, or many long-lived objects. High frequency by itself is not necessarily a bug: many short young collections can be normal behavior.

### 2.2. Pause Time and Total Pause Time

Pause time is the duration for which application threads are stopped during a GC pause. Track:

- Average pause: mean pause duration.
- Maximum pause: longest pause.
- P95/P99 pause: percentiles to spot outlier pauses.
- Total pause time: total time the application is stopped due to GC within the measurement window.

For interactive applications or APIs, P99 latency and the longest pause are often more important than the average. A single 300 ms pause can noticeably impact requests even if hundreds of other pauses last only a few milliseconds.

With concurrent collectors like G1, ZGC, or Shenandoah, most GC work can happen while application threads are still running. Therefore, the duration of an entire GC cycle does not equal the application's pause time. Measure pauses separately.

### 2.3. Application Throughput and Latency

Two common GC goals are:

- Throughput: the percentage of time the JVM spends not doing GC over a long interval.
- Latency: the responsiveness of the application; GC pauses can delay requests.

Measure alongside GC:

- Requests/second or jobs/second.
- P50, P95, and P99 latency.
- Error/timeout rate.
- Process CPU and CPU quota.
- GC pauses and allocation rate.

GC throughput is not a substitute for business throughput. A low-pause collector can still consume significant concurrent CPU, reducing the CPU available to application threads.

### 2.4. Heap Before and After GC

GC logs typically record heap used before and after a collection, along with heap capacity.

Example:

```text
239M->57M(307M)
```

Meaning:

- `239M`: heap used before collection.
- `57M`: heap used after collection.
- `307M`: heap capacity at that point in time.

Post-GC used memory can help estimate the live set, but it must be compared across multiple collections and for the right pool. Heap usage read at an arbitrary moment may include uncollected objects, including objects that are no longer reachable but have not yet been processed by GC.

### 2.5. Allocation Rate and Promotion

Allocation rate is the amount of object memory created per unit of time:

```text
Allocation rate = bytes allocated / elapsed seconds
```

For example, if an application allocates 600 MB in 30 seconds, the average allocation rate is 20 MB/s.

Promotion rate is the rate at which objects survive young collections and move into the region managing long-lived objects. Increased promotion can cause the old generation to grow rapidly and lead to more frequent old collections.

A high allocation rate does not necessarily indicate a memory leak. An application may create many temporary objects and reclaim them quickly. A memory leak typically manifests as a post-GC live set that steadily grows across cycles or observation windows.

### 2.6. Footprint and Live Set

Track heap used, committed, and max; post-collection used memory per memory pool when supported by the collector; process RSS or container memory; and Metaspace and direct/native memory when needed.

Heap does not represent the entire memory of the process. The JVM also has Metaspace, code cache, thread stacks, direct buffers, native libraries, and internal memory regions. Thus, free heap space does not guarantee that the process will not hit RAM or container limits.

## 3. Preparing a Meaningful Measurement

Before enabling tools, define the questions to answer and standardize the measurement conditions.

1. Record the JDK vendor/version, OS, collector, `-Xms`, `-Xmx`, container CPU/memory limits, and JVM options.
2. Choose a representative workload, input data, and concurrency equivalent to production.
3. Capture a baseline without changing GC configuration.
4. Warm up the application to reduce the impact of class loading and JIT compilation.
5. Measure over a window long enough to include multiple GC cycles; for rare issues, observe longer.
6. Record throughput, P95/P99 latency, CPU, memory, and error rate at the same time.
7. Repeat measurements and keep the workload identical when comparing configurations.
8. Save GC logs and JFR recordings with timestamps, JDK version, and configuration.

Do not call `System.gc()` in benchmarks to force collections. This call can alter collector behavior and produce results that are not representative of real workloads. If you need to test how the application reacts to explicit GC, measure it separately and clearly note that it is an intentional test.

## 4. Enabling GC Logs with Unified Logging

Since JDK 9, HotSpot uses Unified Logging via the `-Xlog` option. Basic usage:

```bash
java -Xlog:gc -jar app.jar
```

Log additional details about heap, phases, and GC components:

```bash
java -Xlog:gc* -jar app.jar
```

You can specify the log file, timestamp, uptime, and log level:

```bash
java "-Xlog:gc*:file=logs/gc.log:time,uptime,level,tags" -jar app.jar
```

The `logs` directory must exist, and the account running the JVM must have write permissions.

Example using log rotation to prevent the file from growing indefinitely:

```bash
java -Xms2g -Xmx2g "-Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
```

In this example:

- `gc*`: logs tags containing `gc`, including combined GC tags such as `gc,heap` or `gc,phases`.
- `safepoint`: additionally logs safepoint information.
- `filecount=5`: keeps up to five rotated log files, excluding the currently active file.
- `filesize=20M`: target size threshold for rotating each file.
- `time,uptime,level,tags`: includes wall-clock time, time since JVM startup, log level, and tags.

If you only need basic GC logs, you can use:

```bash
java "-Xlog:gc:file=gc.log:time,uptime,level,tags" -jar app.jar
```

To view heap details or specific phases:

```bash
java "-Xlog:gc+heap=debug,gc+phases=debug" -jar app.jar
```

The `debug` and `trace` levels generate significantly more data. Enable them only when investigating specific issues, and check disk usage and overhead after changing the configuration.

`-verbose:gc` is an alias for `-Xlog:gc` on modern HotSpot. Legacy GC logging flags such as `-XX:+PrintGCDetails` belong to pre-Unified Logging configuration; when working with newer JDKs, prefer `-Xlog`.

## 5. Reading a GC Log Line

Abbreviated example from a G1 log:

```text
[15.651s][info][gc] GC(36) Pause Young (G1 Evacuation Pause) 239M->57M(307M) 5.048ms
```

The fields can be read as follows:

| Component | Meaning |
|---|---|
| `15.651s` | JVM uptime at the time of the log entry |
| `info` | Log level |
| `gc` | Log tag |
| `GC(36)` | Collection ID |
| `Pause Young` | Collection/pause type |
| `G1 Evacuation Pause` | G1 pause cause or type |
| `239M->57M(307M)` | Heap used before, after collection, and capacity |
| `5.048ms` | Logged pause duration |

Some logs also include start/end timestamps and CPU time:

```text
[10.191s][info][gc] GC(36) Pause Young (G1 Evacuation Pause) 391M->114M(508M) 13.075ms
[10.191s][info][gc,cpu] GC(36) User=0.20s Sys=0.00s Real=0.01s
```

`Real` is elapsed wall-clock time, while `User` and `Sys` are CPU times. CPU time can exceed real time when multiple GC workers run in parallel. Do not use `User + Sys` as a substitute for application pause time.

Detailed logs also show Eden/Survivor/Old region counts, Metaspace, evacuation phases, and collector information. Tag names, fields, and formats can change across JDK releases or collectors; consult the documentation for your exact version and avoid writing brittle parsers based on a single log line format.

## 6. Using jstat to Observe GC Over Time

`jstat` retrieves statistics from an instrumented HotSpot JVM. First, find the PID:

```bash
jps -l
```

Collect GC utilization metrics every second for ten samples:

```bash
jstat -gcutil -t <PID> 1000 10
```

Or retrieve capacity and usage statistics for each space:

```bash
jstat -gc <PID> 1000 10
```

View the cause of the most recent collection:

```bash
jstat -gccause <PID> 1000 10
```

Common columns in `-gcutil`:

| Column | Meaning |
|---|---|
| `S0`, `S1` | Survivor space 0 and 1 utilization percentages |
| `E` | Eden space utilization percentage |
| `O` | Old space utilization percentage |
| `M` | Metaspace utilization percentage |
| `CCS` | Compressed Class Space utilization percentage |
| `YGC` | Number of young GC events |
| `YGCT` | Cumulative young GC time |
| `FGC` | Number of full GC events |
| `FGCT` | Cumulative full GC time |
| `GCT` | Total cumulative GC time |
| `CGC`, `CGCT` | Concurrent GC count and time if exposed by the JVM |

Columns depend on the JDK, VM, and collector. For example, a sampling run on JDK 24 might display:

```text
Timestamp    S0     S1      E      O      M     CCS    YGC   YGCT   FGC   FGCT   CGC   CGCT    GCT
1.0           -  100.00  57.14  28.18  73.95  35.01      5  0.007     0  0.000     0  0.000  0.007
1.5           -   93.75   8.82  33.60  73.95  35.01      8  0.009     0  0.000     0  0.000  0.009
```

In this example, Eden rises and then drops after young collections; `YGC` increases from 5 to 8. This indicates that collections occurred between the two samples.

**Note:** Oracle marks `jstat` as experimental/unsupported; options and output formats may change or be removed in future releases. Use it for live observation and trend checks, not for building production parsers that depend on its output format.

`GCT` and `YGCT` are cumulative time counters provided by the JVM. For collectors with concurrent phases, do not treat these numbers as exact total stop-the-world pause times. Use GC logs or JFR for pause analysis.

## 7. Measuring GC with GarbageCollectorMXBean

Java provides platform MXBeans to read collection counts and cumulative collection times.

Retrieve the list of collectors:

```java
List<GarbageCollectorMXBean> collectors =
        ManagementFactory.getGarbageCollectorMXBeans();

for (GarbageCollectorMXBean gc : collectors) {
    System.out.println(gc.getName());
    System.out.println(gc.getCollectionCount());
    System.out.println(gc.getCollectionTime());
}
```

Two key methods:

- `getCollectionCount()`: total number of collections that have occurred.
- `getCollectionTime()`: approximate cumulative collection time, in milliseconds.

Some JVMs may return `-1` if the value is undefined. Therefore, when calculating deltas, check both the initial and final values.

Example of computing deltas over a measurement window:

```java
long countBefore = gc.getCollectionCount();
long timeBefore = gc.getCollectionTime();

// Run the workload to be measured here.

long countAfter = gc.getCollectionCount();
long timeAfter = gc.getCollectionTime();

long countDelta = countBefore < 0 || countAfter < 0
        ? -1 : countAfter - countBefore;

long timeDeltaMs = timeBefore < 0 || timeAfter < 0
        ? -1 : timeAfter - timeBefore;
```

These metrics are suitable for monitoring and trend tracking. `getCollectionTime()` is an approximate cumulative collection time, not an exact measurement of total time application threads were paused. For concurrent collectors, use JFR or GC logs to measure pauses.

You can track heap usage via `MemoryMXBean`:

```java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

long used = memory.getHeapMemoryUsage().getUsed();
long committed = memory.getHeapMemoryUsage().getCommitted();
long max = memory.getHeapMemoryUsage().getMax();
```

`used` is the amount of heap currently in use at the time of reading; `committed` is the amount of memory guaranteed to be available to the JVM; and `max` is the maximum limit if defined. This value does not automatically tell you the post-GC live set.

For individual memory pools, `MemoryPoolMXBean.getCollectionUsage()` can provide post-collection usage if the pool supports it. Check `isCollectionUsageThresholdSupported()` before using collection thresholds. Pool names and support depend on the collector.

## 8. Monitoring MXBeans in JConsole

You can observe GC without writing custom monitoring code:

1. Start the Java application.
2. Launch `jconsole`.
3. Connect to the local process or a JVM configured for remote JMX.
4. Open the **Memory** tab to view the heap and memory pools.
5. Open the **MBeans** tab.
6. Select `java.lang` → `GarbageCollector`.
7. Select each collector to view `CollectionCount`, `CollectionTime`, and associated memory pool names.
8. Open `java.lang` → `Memory` to view heap usage.

JConsole is useful for live observation and identifying when memory changes occur. For long-term investigations, export metrics to a monitoring system and retain logs/recordings for historical analysis.

You can use `MemoryMXBean` notifications to detect when a pool exceeds its usage threshold or collection usage threshold. Not all pools support both threshold types; check capabilities before configuring.

## 9. Using Java Flight Recorder for More Accurate Pause Measurement

Java Flight Recorder (JFR) records JVM events over time. It is a valuable tool for analyzing GC pauses, GC phases, and allocations.

Start a time-bounded profiling recording:

```bash
jcmd <PID> JFR.start name=gc-profile settings=profile duration=10m disk=true filename=gc-profile.jfr
```

Check active recordings:

```bash
jcmd <PID> JFR.check
```

Once the recording completes, view a summary:

```bash
jfr summary gc-profile.jfr
```

Print GC pause events:

```bash
jfr print --events jdk.GCPhasePause gc-profile.jfr
```

You can also view general collection events:

```bash
jfr print --events jdk.GarbageCollection gc-profile.jfr
```

`jdk.GCPhasePause` provides the duration of pauses. From these events, you can calculate average pause, maximum pause, and total pause time. When analyzing, use top-level pause events; do not add sub-phase durations on top of them, as that will double-count time.

JFR also provides allocation events such as `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB`, and `jdk.ThreadAllocationStatistics`. These help identify classes or threads performing heavy allocations.

**Do not enable Heap Statistics during normal latency measurements.** According to Oracle, Heap Statistics can trigger an old GC at the start and end of a recording, introducing extra pauses that skew measurements. Enable it only when investigating live set or memory leaks, and explicitly note this impact in your results.

## 10. Analyzing Recordings with JDK Mission Control

JDK Mission Control (JMC) reads JFR files and presents data on a timeline.

To investigate GC:

1. Open the `.jfr` file in JMC.
2. Review **Automated Analysis Results** and the Garbage Collections section.
3. Open **JVM Internals → Garbage Collections**.
4. Inspect the GC pauses chart and **Sum of Pauses**.
5. Compare pause count, average, maximum, and total pause time.
6. Open the TLAB Allocations section to find classes/threads allocating many objects.
7. Correlate GC events with CPU, threads, allocations, and latency spikes.

**Sum of Pauses** is the total time the application was actually stopped during GC pauses. This is particularly useful for collectors that perform significant concurrent work, because the total duration of a GC cycle can be much longer than the pause experienced by the application.

If you see Full GCs or sharp pause spikes, check the cause in the GC logs and post-collection heap usage. Do not draw conclusions from charts alone; correlate them with workload, allocation, and memory retention.

## 11. Calculating Metrics from Collected Data

### 11.1. GC Pause Ratio

Calculate the percentage of time the application is stopped due to GC:

```text
GC pause ratio (%) =
  Total GC pause time / Measurement window × 100
```

For example, in a 300-second measurement window with a total pause time of 1.5 seconds:

```text
1.5 / 300 × 100 = 0.5%
```

This is the percentage of time stopped due to GC pauses. It does not include all CPU consumed by concurrent GC.

### 11.2. GC Frequency

```text
GC frequency = Collection count / Observed seconds
```

Break this down by young, mixed, full, and concurrent cycles when the log or collector provides those categories.

### 11.3. Average Pause

```text
Average pause = Total pause time / Number of pause events
```

Do not look at the average alone. P95, P99, and maximum help uncover rare but high-impact pauses.

### 11.4. Allocation Rate

```text
Allocation rate (MB/s) =
  Allocated bytes / Elapsed seconds / 1,048,576
```

To compare two versions of an application, use the same workload and the same allocation collection method. A high allocation rate can cause more frequent young GCs even if the live set does not grow.

### 11.5. Application Throughput

```text
Application throughput = Completed requests / Measurement duration
```

Always record this alongside P95/P99 latency and error rate. A low pause ratio accompanied by dropping throughput can be caused by concurrent GC CPU consumption, CPU throttling, allocation stalls, or other bottlenecks.

## 12. Recognizing Abnormal GC Patterns

| Symptom | What to Check |
|---|---|
| Young GC increases rapidly, post-GC Old usage is stable | High allocation rate or workload creating many short-lived objects |
| Post-GC Old usage steadily rises across windows | Long-lived objects, increasing retention, or a memory leak |
| Frequent Full GCs | Heap pressure, large live set, explicit GC, or promotion/collector issues |
| Isolated very long pauses | Evacuation/compaction, large live objects, heap pressure, or collector configuration |
| High total pause time despite short individual pauses | Collections occurring too frequently |
| Prolonged concurrent cycles, high CPU | Collector needs more CPU to keep up with allocation or is CPU-throttled |
| Allocation rate increases after a release | Code changes creating more temporary objects, buffers, or collections |
| Low post-GC heap but high RSS | Native memory, direct buffers, thread stacks, metaspace, or memory not yet returned to the OS |
| `jdk.DataLoss` in JFR | Event rate or collection conditions exceed current buffer/write capacity |

For G1, watch for messages related to evacuation failure, humongous allocation, and Full GC. For ZGC or Shenandoah, also check concurrent cycles and allocation stalls in collector events/logs. Event names and interpretation depend on the JDK and collector.

A single Full GC is not enough to conclude there is a memory leak. Examine the collection cause, post-GC heap usage, and trends across multiple measurement windows.

## 13. Practical Example: Generating Allocations and Reading GC MXBeans

The following example allocates temporary objects in batches, then reads the delta in collection count and collection time from MXBeans. The program does not call `System.gc()`.

Create `GcMeasureDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.util.Arrays;
import java.util.List;

public class GcMeasureDemo {
    private static long allocatedBytes;

    public static void main(String[] args) throws Exception {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();
        long[] countsBefore = new long[collectors.size()];
        long[] timesBefore = new long[collectors.size()];

        for (int i = 0; i < collectors.size(); i++) {
            countsBefore[i] = collectors.get(i).getCollectionCount();
            timesBefore[i] = collectors.get(i).getCollectionTime();
        }

        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        byte[][] batch = new byte[128][];
        long started = System.nanoTime();

        for (int round = 0; round < 40; round++) {
            for (int i = 0; i < batch.length; i++) {
                byte[] block = new byte[64 * 1024];
                block[0] = (byte) i;
                block[block.length - 1] = (byte) round;
                batch[i] = block;
                allocatedBytes += block.length;
            }

            Arrays.fill(batch, null);
            Thread.sleep(50);
        }

        long elapsedMillis =
                (System.nanoTime() - started) / 1_000_000;

        System.out.println("ALLOCATED_BYTES=" + allocatedBytes);
        System.out.println("ALLOCATION_WINDOW_MS=" + elapsedMillis);
        System.out.println("READY_FOR_JSTAT");

        // Keep the JVM alive long enough for jstat to sample from another terminal.
        Thread.sleep(6000);

        for (int i = 0; i < collectors.size(); i++) {
            GarbageCollectorMXBean gc = collectors.get(i);
            long countAfter = gc.getCollectionCount();
            long timeAfter = gc.getCollectionTime();

            System.out.println("GC=" + gc.getName()
                    + ",COUNT_DELTA="
                    + delta(countsBefore[i], countAfter)
                    + ",TIME_DELTA_MS="
                    + delta(timesBefore[i], timeAfter));
        }

        System.out.println("HEAP_USED_AFTER_BYTES="
                + memory.getHeapMemoryUsage().getUsed());
        System.out.println("DEMO_DONE");
    }

    private static long delta(long before, long after) {
        return before < 0 || after < 0 ? -1 : after - before;
    }
}
```

Compile:

```bash
javac --release 17 -g GcMeasureDemo.java
```

Run with a bounded heap and GC logging:

```bash
java -Xms64m -Xmx64m "-Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=3,filesize=1M" GcMeasureDemo
```

The program creates 40 batches, each containing 128 objects of 64 KB. The total counted allocation is:

```text
40 × 128 × 64 KB = 327,680 KB = 320 MB
```

When the program prints `READY_FOR_JSTAT`, open a second terminal and find the PID with `jps -l`. Then take eight samples 500 ms apart:

```bash
jstat -gcutil -t <PID> 500 8
```

In the GC log, look for `Pause Young`, `Pause Full`, heap before/after, and collection causes. When the program finishes, stdout will look similar to:

```text
ALLOCATED_BYTES=335544320
ALLOCATION_WINDOW_MS=2063
READY_FOR_JSTAT
GC=G1 Young Generation,COUNT_DELTA=10,TIME_DELTA_MS=9
GC=G1 Concurrent GC,COUNT_DELTA=0,TIME_DELTA_MS=0
GC=G1 Old Generation,COUNT_DELTA=0,TIME_DELTA_MS=0
HEAP_USED_AFTER_BYTES=43107352
DEMO_DONE
```

This is the output of a run on OpenJDK Zulu 24.0.2 with G1 and a 64 MB heap. Timings, collection counts, collector names, and heap usage may vary across machines or runs. The MXBean numbers in this example are cumulative collection counts and collection times, not exact pause measurements.

## 14. Before-and-After GC Optimization Workflow

When evaluating a code change or GC configuration change:

1. Select a workload with a representative request mix, data, and concurrency.
2. Warm up the JVM before starting measurements.
3. Capture a baseline: throughput, P95/P99, CPU, RSS, heap, and allocation rate.
4. Collect GC logs and JFR within the same measurement window.
5. Make only the single change being evaluated.
6. Re-run the exact same workload with the same JDK, CPU/memory limits, and duration.
7. Compare pause distribution, total pause, Full GCs, allocation rate, live set, and throughput.
8. Repeat enough times to filter out noise.
9. Conclude that the change is better only if it improves the target goal without degrading other critical metrics.

Do not increase `-Xmx` or switch collectors just because of a single slow GC. A larger heap can reduce collection frequency, but it increases footprint and may make some collections longer. Choose the collector and heap size based on latency, throughput, footprint goals, and environment constraints.

## 15. Common Pitfalls When Measuring GC

| Symptom | Possible Cause | Resolution |
|---|---|---|
| High heap usage concluded to be a leak | Looking only at instantaneous usage instead of post-collection usage | Compare live set across multiple GCs and windows |
| MXBean collection time treated as pause time | Confusing elapsed collection time with STW pauses | Use `jdk.GCPhasePause` or GC logs |
| Long GC cycle assumed to stop the app for the entire cycle | Collector performs significant concurrent work | Measure pauses separately and correlate with application latency |
| JFR records unusually large pauses | Heap Statistics enabled in the recording | Disable heap statistics during normal latency measurements |
| Large JFR files or high overhead | Too many events enabled, thresholds too low, or recording too long | Enable only required events and limit duration |
| `jstat` cannot see the process | Wrong PID, user, or process namespace | Verify the correct host/container and user account |
| `jstat` output changes across JDKs | Experimental/unsupported tool | Check `jstat -options` and docs for the exact JDK |
| GC log file grows without bound | Log rotation not configured | Set `filecount` and `filesize` |
| GC count increases but latency stays unchanged | Collections are short or mostly concurrent | Compare pauses, throughput, and CPU |
| Full GC appears after running a benchmark | Code or profiler explicitly triggers GC | Check for `System.gc()` calls and profiler settings |

## 16. Key Takeaways

- Measure GC under a representative workload, after warm-up, and over a sufficiently long window.
- Track pause time, throughput, allocation rate, live set, CPU, and application latency together.
- Use `-Xlog:gc*` to inspect collections, heap, and phases; enable rotation in production.
- Use `jstat -gcutil` for quick observation of pools and counters; keep the tool's limitations in mind.
- Use `GarbageCollectorMXBean` for collection counts and cumulative collection time; do not treat it as exact STW pause time.
- Use JFR `jdk.GCPhasePause` and JMC Sum of Pauses to analyze actual application stop time.
- Do not enable Heap Statistics during normal latency measurements, as it can trigger extra old GCs.
- Distinguish concurrent GC cycles from actual pauses.
- Do not conclude a memory leak from high heap usage alone or a single Full GC.
- Compare baseline and post-optimization runs using the same workload, JDK, collector, and resource limits.

**Official References:**

- [Oracle Java SE 24 — Garbage Collector Implementation and Performance Measurement](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-collector-implementation.html)
- [Oracle Java SE 24 — The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [Oracle Java SE 24 — The java Command and Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle Java SE 24 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 24 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Oracle Java SE 24 — MemoryMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 24 — ManagementFactory](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Oracle Java SE 24 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/24/gctuning/)

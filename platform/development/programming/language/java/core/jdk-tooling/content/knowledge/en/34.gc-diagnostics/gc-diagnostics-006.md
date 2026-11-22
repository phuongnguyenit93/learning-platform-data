# Measuring and Diagnosing GC Pause Time

**GC pause time** is the duration during which the JVM pauses application threads to perform a stop-the-world (STW) garbage collection phase. During a pause, application requests and worker threads cannot make progress, increasing latency or causing requests to breach their SLOs.

To diagnose pause time, you need to answer four questions:

1. How many pauses occurred during the observation window?
2. How long did each pause last, especially at P95, P99, and the maximum?
3. What type of GC caused the pause, what triggered it, and which phase took the most time?
4. Do the pauses coincide with application latency spikes?

Key tools in the JDK:

- **JFR:** analyze pause distribution, GC phases, heap before/after, and timeline.
- **Unified GC logging:** record each GC event with its cause, heap size, duration, and safepoints.
- **jstat:** monitor collection counts and cumulative time periodically.
- **GarbageCollectorMXBean:** read collection count and collection time from Java code.
- **JDK Mission Control (JMC):** open recordings, filter events, and correlate with workload.

## 1. Distinguishing GC Pauses, GC Cycles, and Concurrent Work

Not all garbage collection time is pause time.

### Stop-the-world pause

During an STW pause, application threads are stopped at a safepoint while the JVM executes a GC phase. For example, with G1:

- Pause Young (Normal).
- Pause Young (Concurrent Start).
- Pause Young (Mixed).
- Pause Remark.
- Pause Cleanup.
- Pause Full.

A pause may last only a few milliseconds, but if it occurs frequently or has high tail latency, it still impacts requests.

### Concurrent GC phase

Some collectors perform GC work concurrently with application threads. For example, G1 has concurrent marking and other concurrent phases. ZGC and Shenandoah also perform most of their work while the application continues running.

A concurrent phase can last hundreds of milliseconds or longer without being equivalent to an STW pause of the same duration. Therefore, do not treat the total duration of all GC cycles as total pause time.

### GC cycle and pause events

A single GC cycle can include multiple concurrent phases and multiple pauses. For example, a G1 marking cycle may include an initial start pause, concurrent marking, a remark pause, and a cleanup pause.

In JFR:

- jdk.GarbageCollection describes a collection event.
- jdk.GCPhasePause describes a pause phase.
- jdk.GCPhasePauseLevel1, Level2, and other levels describe sub-phases.
- jdk.GCPhaseConcurrent describes a concurrent phase.
- jdk.GCHeapSummary records the heap summary before or after GC.

Consequently, the number of jdk.GarbageCollection events can differ from the number of jdk.GCPhasePause events. A single collection can contain multiple pause events.

## 2. Pause Time Metrics to Monitor

| Metric | Meaning |
|---|---|
| Pause count | Number of STW pauses in the observation window |
| Total pause time | Sum of pause durations |
| Minimum | Shortest pause |
| Median / P50 | Half of the pauses are shorter than or equal to this value |
| Average | Mean pause duration |
| P90 / P95 | Tail latency of pauses |
| P99 / P99.9 | Pauses at the far tail of the distribution |
| Maximum | Longest pause |
| GC cause | Reason the collection was triggered |
| Heap before / after | Heap used before and after the collection |

### Why look at percentiles?

The average can hide a few very long pauses.

For example:

- 990 pauses lasting 2 ms.
- 10 pauses lasting 200 ms.

The average may still look relatively low, but those 10 long pauses can cause requests to time out or spike p99 latency.

When investigating production issues, look at P95, P99, and maximum alongside pause count. Compare these values against your application's latency SLO.

### Pause fraction

You can estimate the percentage of time spent paused in a recording:

\[
Pause\ fraction = \frac{Total\ pause\ time}{Recording\ wall\ time} \times 100
\]

For example, in an 8-second recording with a total pause time of 45.4 ms:

\[
\frac{45.4}{8000} \times 100 \approx 0.57\%
\]

This metric helps compare overall pause levels across recordings measured the same way. It does not replace P99 or maximum: a single 200 ms pause can still break a request even when the overall window's pause fraction is low.

## 3. Measuring Pause Time with Java Flight Recorder

JFR is well suited for analyzing pause distribution and GC phases.

Start a recording at JVM startup:

~~~bash
java \
    -XX:StartFlightRecording=filename=gc.jfr,settings=profile,duration=60s,dumponexit=true \
    -jar app.jar
~~~

Or start a recording on a running JVM:

~~~bash
jcmd -l

jcmd 12345 JFR.start name=GC settings=profile duration=60s filename=gc.jfr
~~~

Replace 12345 with the PID of the JVM you want to monitor.

Check active recordings:

~~~bash
jcmd 12345 JFR.check
~~~

Dump a snapshot if the recording is still running:

~~~bash
jcmd 12345 JFR.dump name=GC filename=gc-snapshot.jfr
~~~

Stop the recording:

~~~bash
jcmd 12345 JFR.stop name=GC
~~~

These JFR commands require Attach to be enabled and the user to have permission to access the process. In production, choose an appropriate recording window and evaluate the overhead of the `profile` configuration.

### Viewing the summary

~~~bash
jfr summary gc.jfr
~~~

Look for these events:

- jdk.GarbageCollection.
- jdk.GCPhasePause.
- jdk.GCPhasePauseLevel1.
- jdk.GCHeapSummary.
- jdk.GCPhaseConcurrent.

The summary shows event counts and sizes. If there are no GC pause events, check the recording duration, settings, collector, and workload timing before concluding that the JVM had no pauses.

### Viewing pause distribution

~~~bash
jfr view gc-pauses gc.jfr
~~~

This view summarizes:

- Total Pause Time.
- Number of Pauses.
- Minimum Pause Time.
- Median Pause Time.
- Average Pause Time.
- P90, P95, P99, and P99.9.
- Maximum Pause Time.

Example output from an 8-second recording on JDK 24.0.2:

~~~text
GC Pauses
---------

Total Pause Time: 45.4 ms

Number of Pauses: 80

Minimum Pause Time: 0.409 ms

Median Pause Time: 0.517 ms

Average Pause Time: 0.568 ms

P90 Pause Time: 0.766 ms

P95 Pause Time: 0.843 ms

P99 Pause Time: 2.60 ms

P99.9% Pause Time: 2.60 ms

Maximum Pause Time: 2.60 ms
~~~

This is the result of a lab workload generating continuous allocations with a 32–64 MB heap and G1. Other recordings will have different pause counts and percentiles.

### Viewing individual collections

~~~bash
jfr view gc gc.jfr
~~~

The summary table can display:

- GC ID.
- Start time.
- GC type.
- Heap before GC.
- Heap after GC.
- Longest pause.

Use this table to find collections with long pauses and check whether heap usage drops after GC.

### Viewing which phases consume time

~~~bash
jfr view gc-pause-phases gc.jfr
~~~

Example output:

~~~text
GC Pause Phases

Type              Name                     Average    P95    Longest Count   Total
----------------- ------------------------ --------- ------  -------- ----- -------
GC Phase Pause    GC Pause                  0.568 ms 0.843 ms 2.60 ms    80  45.4 ms
GC Phase Pause L1 Notify Soft/WeakReferences ...
GC Phase Pause L1 Notify PhantomReferences ...
~~~

If a specific phase accounts for most of the pause duration, examine the collector, heap layout, and the cause of that phase. Do not tune GC flags based solely on a phase name; correlate it with events and workload.

### Viewing GC CPU time

~~~bash
jfr view gc-cpu-time gc.jfr
~~~

This view summarizes CPU user time, system time, wall-clock time, and GC count based on recording data. GC CPU time is not the same as STW pause time: the collector can use CPU during concurrent phases while the application is still running.

### Printing events for detailed inspection

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary gc.jfr
~~~

An event may look like this:

~~~text
jdk.GCPhasePause {
  startTime = 20:21:49.726
  duration = 2.74 ms
  gcId = 1
  name = "GC Pause"
  eventThread = "VM Thread"
}

jdk.GarbageCollection {
  startTime = 20:21:49.726
  duration = 2.74 ms
  gcId = 1
  name = "G1New"
  cause = "G1 Humongous Allocation"
  sumOfPauses = 2.74 ms
  longestPause = 2.74 ms
}
~~~

Key fields:

- startTime: start timestamp.
- duration: event duration.
- gcId: associated collection ID.
- name: collection or phase type.
- cause: collection cause.
- sumOfPauses: total pause recorded for the collection.
- longestPause: longest pause within the collection.

The `GCHeapSummary` event has `when = Before GC` or `After GC` and the corresponding `heapUsed`. Use these two events to compare heap before and after GC.

## 4. Recording GC Logs with Unified Logging

Unified Logging is the standard way to record GC logs on JDK 9 and later. On JDK 24, use the `-Xlog` option instead of relying on legacy logging flags.

Enable GC and safepoint logs:

~~~bash
java \
    -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
    -jar app.jar
~~~

Meaning:

- gc*: log tags related to garbage collection.
- safepoint: information about safepoints and thread stop times.
- file=gc.log: write output to a file.
- time: wall-clock timestamp.
- uptime: time since JVM startup.
- level: log level.
- tags: tag group that produced the log line.

You can rotate log files to prevent unbounded growth:

~~~bash
java \
    -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
    -jar app.jar
~~~

This rotation syntax has been verified on JDK 24.0.2. Adjust the file count and file size according to your log retention policy.

### Reading a GC log line

Example:

~~~text
[2026-11-10T20:25:06.973+0700][0.228s][info][gc]
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->4M(34M) 2.726ms
~~~

Interpretation:

- Timestamp: time of the log entry.
- 0.228s: JVM uptime at that moment.
- GC(0): collection ID.
- Pause Young: pause type.
- G1 Evacuation Pause: G1 cause/operation type.
- 18M->4M: heap used before and after the collection.
- (34M): heap capacity at that time.
- 2.726ms: pause duration recorded on the completion line.

Read the start/end line pair for the same GC ID to determine duration. Do not add sub-phase line durations into the total pause if they are already included in the total pause, as that would double-count them.

### Common G1 log patterns

| Log text | General meaning |
|---|---|
| Pause Young (Normal) | Normal young collection |
| Pause Young (Concurrent Start) | Young pause that initiates concurrent marking |
| Pause Young (Mixed) | Collection involving both young and old regions |
| Pause Remark | STW remark during a marking cycle |
| Pause Cleanup | Short STW cleanup |
| Pause Full | Full GC, usually requires thorough investigation |
| Concurrent Mark Cycle | Concurrent marking phase |
| Evacuation Failure | G1 failed to evacuate some objects as expected |
| To-space exhausted | Insufficient destination regions for evacuation |
| G1 Humongous Allocation | Large object allocation triggering GC activity |

Phase names and ordering depend on the collector and JVM version. Read the actual logs of the running collector rather than blindly applying G1 interpretations to ZGC or Shenandoah.

## 5. GC Pauses and Safepoints Are Not Exactly the Same

A GC pause is an application stop to execute a GC phase. A safepoint is the JVM mechanism for bringing Java threads to a safe state to perform certain internal operations.

There are safepoints not directly related to GC, such as certain VM operations, deoptimization, or runtime management operations.

Enable both log groups:

~~~bash
-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags
~~~

Safepoint lines can show:

- Reaching safepoint: time spent waiting for threads to reach the safepoint.
- At safepoint: time spent executing the operation once threads are stopped.
- Leaving safepoint: time spent releasing threads from the safepoint.
- Total: total duration of the safepoint operation.

If a latency spike occurs without a corresponding GC pause, check the safepoint log to see whether the JVM stopped threads for another VM operation.

Do not add all safepoint durations into GC pause time. Categorize by operation and correlate timestamps.

## 6. Monitoring GC with jstat

`jstat` reads JVM statistics from performance data. It is useful when you want to observe periodic trends without opening JFR or parsing GC logs.

### Viewing GC utilization

~~~bash
jstat -gcutil 12345 1000 10
~~~

This command takes 10 samples, 1 second apart. Replace 12345 with the PID.

Common columns:

| Column | Meaning |
|---|---|
| S0, S1 | Survivor space utilization |
| E | Eden utilization |
| O | Old generation utilization |
| M | Metaspace utilization |
| CCS | Compressed class space utilization |
| YGC | Number of young GCs |
| YGCT | Cumulative young GC time, in seconds |
| FGC | Number of full GCs |
| FGCT | Cumulative full GC time, in seconds |
| CGC | Number of concurrent GCs |
| CGCT | Cumulative concurrent GC time, in seconds |
| GCT | Total cumulative GC time, in seconds |

Example output:

~~~text
S0     S1     E      O      M     CCS    YGC     YGCT     FGC    FGCT     CGC    CGCT       GCT
-      83.33  0.00   11.82  60.95 15.69     15     0.007     0     0.000     0     0.000     0.007
-      83.33  6.25   11.82  60.95 15.69     22     0.009     0     0.000     0     0.000     0.009
-      83.33  0.00   11.82  60.95 15.69     29     0.012     0     0.000     0     0.000     0.012
~~~

The time columns are cumulative counters. Take the delta between samples to see how much GC time increased during the observation window.

`jstat` does not provide pause percentiles like JFR. Nor does it show individual pause durations or stacks/phases in full detail. Use it to spot frequency and trends, then open GC logs or JFR to find the root cause.

### Viewing GC cause

~~~bash
jstat -gccause 12345 1000 10
~~~

Additional columns:

- LGCC: cause of the last GC.
- GCC: cause of the current GC or current state.

Example causes include `G1 Evacuation Pause` or `No GC`. Values depend on the collector and the sampling moment.

## 7. Reading Collection Metrics via GarbageCollectorMXBean

The Java Management API provides a `GarbageCollectorMXBean` for each garbage collector.

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    System.out.println(gc.getName());
    System.out.println(gc.getCollectionCount());
    System.out.println(gc.getCollectionTime());
}
~~~

Methods:

- getName(): collector name.
- getCollectionCount(): number of completed collections.
- getCollectionTime(): cumulative collection time, in milliseconds.

A value of `-1` means the implementation does not provide that metric. Collection count and collection time are cumulative counters since JVM startup.

**Important limitation:** `getCollectionTime()` is cumulative collection time reported by the implementation, not a per-STW-pause record, and it does not provide P95/P99. For collectors with concurrent work, do not assume this value equals the exact total STW pause time. Use it to track trends, and get pause distributions from JFR.

### Computing cumulative time over a window

Capture count and time before and after a workload window:

~~~java
long countDelta = countAfter - countBefore;
long collectionTimeDelta = timeAfter - timeBefore;
double gcTimeRatio =
        100.0 * collectionTimeDelta / wallTimeMillis;
~~~

This ratio is an estimate of collection time relative to wall time. If GC workers run in parallel or the collector performs concurrent work, total collection time may not match the time the application was actually paused.

## 8. Java 17+ Example: Measuring Collection Count and Time

The following program generates continuous allocations, retaining only the eight most recent byte arrays to put pressure on the young generation. It reads metrics from `GarbageCollectorMXBean` before and after the workload.

### GcPauseDemo.java

~~~java
package com.example;

import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;

public final class GcPauseDemo {
    private GcPauseDemo() { }

    public static void main(String[] args) throws Exception {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        long countBefore = total(collectors, true);
        long timeBefore = total(collectors, false);
        long wallBefore = System.nanoTime();

        Deque<byte[]> retained = new ArrayDeque<>();
        long end = System.nanoTime() + 8_000_000_000L;
        long allocations = 0;

        while (System.nanoTime() < end) {
            retained.addLast(new byte[256 * 1024]);

            if (retained.size() > 8) {
                retained.removeFirst();
            }

            allocations++;
            Thread.sleep(1);
        }

        long wallAfter = System.nanoTime();
        long countAfter = total(collectors, true);
        long timeAfter = total(collectors, false);

        long gcCount = countAfter - countBefore;
        long gcMillis = timeAfter - timeBefore;
        double wallMillis = (wallAfter - wallBefore) / 1_000_000.0;

        System.out.println("GC demo completed; allocations=" + allocations);
        System.out.println("GC count delta=" + gcCount);
        System.out.println("GC collection time delta ms=" + gcMillis);

        System.out.printf(
                "Approximate cumulative GC time / wall time=%.2f%%%n",
                wallMillis > 0 ? 100.0 * gcMillis / wallMillis : 0.0);

        for (GarbageCollectorMXBean gc : collectors) {
            System.out.println(gc.getName()
                    + " count=" + gc.getCollectionCount()
                    + " timeMs=" + gc.getCollectionTime());
        }
    }

    private static long total(
            List<GarbageCollectorMXBean> beans, boolean count) {
        long total = 0;

        for (GarbageCollectorMXBean bean : beans) {
            long value = count
                    ? bean.getCollectionCount()
                    : bean.getCollectionTime();

            if (value >= 0) {
                total += value;
            }
        }

        return total;
    }
}
~~~

### Compiling

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/GcPauseDemo.java
~~~

### Running with a bounded heap

~~~bash
java -Xms32m -Xmx64m \
    -cp build/classes \
    com.example.GcPauseDemo
~~~

Sample output observed on JDK 24.0.2:

~~~text
GC demo completed; allocations=3788
GC count delta=80
GC collection time delta ms=45
Approximate cumulative GC time / wall time=0.56%
G1 Young Generation count=81 timeMs=47
G1 Concurrent GC count=0 timeMs=0
G1 Old Generation count=0 timeMs=0
~~~

Counters and timings vary by JDK, collector, CPU, and workload. This program demonstrates how to retrieve collection metrics; it does not provide P99 pause times on its own.

## 9. Full Lab: Combining Java, JFR, and GC Logs

Use the same `GcPauseDemo` to generate a recording and log:

~~~bash
java -Xms32m -Xmx64m \
    -XX:StartFlightRecording=filename=gc-pause.jfr,settings=profile,duration=8s,dumponexit=true \
    -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
    -cp build/classes \
    com.example.GcPauseDemo
~~~

After the program exits, inspect the recording:

~~~bash
jfr summary gc-pause.jfr
jfr view gc-pauses gc-pause.jfr
jfr view gc-pause-phases gc-pause.jfr
jfr view gc gc-pause.jfr
~~~

Read the log:

~~~bash
# Search for pause types and durations
grep -E "Pause Young|Pause Full|Pause Remark|Pause Cleanup" gc.log

# Search for safepoint details
grep -i "safepoint" gc.log
~~~

On Windows PowerShell, you can use:

~~~powershell
Select-String -Path .\gc.log -Pattern 'Pause Young|Pause Full|Pause Remark|Pause Cleanup'
Select-String -Path .\gc.log -Pattern 'Safepoint'
~~~

JDK 24.0.2 lab results:

- 8-second recording.
- 80 jdk.GarbageCollection events.
- 80 jdk.GCPhasePause events.
- Total pause time ~45.4 ms.
- Median pause 0.517 ms.
- P95 pause 0.843 ms.
- P99 pause 2.60 ms.
- Maximum pause 2.60 ms.

The unified GC log shows G1 Young pauses along with heap before/after and duration. These numbers are from a single illustrative run, not production benchmarks.

## 10. Analyzing Causes of Long Pauses

When you find a long pause, do not look at duration alone. Check GC cause, heap before/after, phase breakdown, and allocation rate.

### Young GC occurring too frequently

Symptoms:

- YGC increases rapidly.
- JFR shows many Young pauses.
- Eden fills up quickly.
- Heap after GC drops, but the allocation rate remains high.

Investigation steps:

- Find allocation hot spots using JFR allocation events.
- Check for temporary objects created inside loops.
- Check serialization, boxing, collection growth, and buffer creation.
- View allocation rate and request throughput on the same timeline.

Increasing the heap is not necessarily the solution. If the application allocates too many objects, a larger heap may only space out GCs without reducing total allocation.

### Full GC or very long pauses

Symptoms:

- Logs contain `Pause Full`.
- FGC or FGCT increases.
- JFR shows a large maximum pause.
- Heap after GC remains high or drops very little.

Check:

- Is the live set close to heap capacity?
- Is there a memory leak or an unbounded cache?
- Are there allocation spikes or humongous objects?
- Is there promotion pressure or evacuation failure?
- Are there explicit GC calls from the application or libraries?
- Do you have a heap dump or JFR recording from the exact timeframe?

Full GCs usually require thorough investigation, but do not conclude the root cause from the event name alone.

### G1 evacuation failure

The log may contain:

- Evacuation Failure.
- To-space exhausted.

This indicates G1 did not have enough destination regions to evacuate some objects. Check heap pressure, live set, allocation rate, region availability, and mixed collection timing.

Do not raise the pause target as your sole fix. You need to determine why the heap lacked space for evacuation.

### Remark or Cleanup pauses

G1 concurrent marking includes Remark and Cleanup pauses. If these phases account for most of the pause time, inspect the GC pause phase breakdown and concurrent marking timeline. Frequency and duration depend on heap, object graph, reference processing, and workload.

### Concurrent GC consuming CPU with short pauses

If pauses are short but CPU usage is high during GC, the collector may be doing heavy concurrent work. Check JFR `gc-cpu-time`, concurrent phases, and process CPU. Reducing pauses does not necessarily mean reducing total CPU or increasing throughput.

## 11. Comparing Garbage Collectors

Each collector has different goals and pause characteristics.

| Collector | Characteristics when analyzing pauses |
|---|---|
| Serial GC | Mostly STW collections, suitable for small workloads or few cores |
| Parallel GC | STW collections using multiple workers to maximize throughput |
| G1 GC | Young/mixed/full pauses combined with concurrent marking |
| ZGC | Most work is concurrent, though short pauses still exist |
| Shenandoah | Concurrent compaction, still has pauses to monitor |

Do not directly compare pause durations across collectors if workload, heap, JDK, CPU quota, and latency objectives differ.

With ZGC or Shenandoah, some phases may have different names and structures. Consult JFR metadata, the GC logs of the actual collector, and the documentation for your running JDK.

### Checking which collector is in use

~~~bash
jcmd 12345 VM.flags
~~~

Look for flags such as:

~~~text
-XX:+UseG1GC
-XX:+UseZGC
-XX:+UseShenandoahGC
-XX:+UseParallelGC
-XX:+UseSerialGC
~~~

Do not assume the JVM is running G1. The selected collector can depend on startup configuration, JDK version, and environment.

## 12. Tuning GC After Gathering Data

Only tune after identifying the root cause and establishing a baseline.

### Heap size

- Xms: initial heap size.
- Xmx: maximum heap size.

Increasing `Xmx` can reduce GC frequency in some workloads, but it increases memory footprint and does not guarantee shorter pauses. A larger heap can cause some collections to take longer.

### G1 pause target

~~~bash
-XX:MaxGCPauseMillis=200
~~~

This is a soft goal that G1 considers when planning collections, not a guarantee that every pause will stay under 200 ms. The collector may prioritize throughput, heap occupancy, and other constraints.

Lowering the pause target may cause G1 to choose smaller collections or run GC more frequently. Measure pause distribution, throughput, and CPU after making changes.

### Do not force GC for measurement

Avoid calling `System.gc()` or `jcmd GC.run` while measuring a normal workload. Forcing GC alters JVM behavior and can produce pauses not representative of production.

Only use explicit GC in a lab or a diagnostic procedure with a clear purpose.

## 13. Correlating GC Pauses with Application Latency

A GC pause can stop all application threads, but request latency spikes can also come from locks, network, disk, scheduler, or CPU throttling.

Workflow:

1. Record the timestamps when request latency spiked from APM/metrics.
2. Check whether the JFR recording covers that timeframe.
3. Use `gc-pauses` to find long pauses or increased pause frequency.
4. Correlate timestamps and `gcId` in the events.
5. Check GC cause and heap before/after.
6. Check the phase breakdown to see what took time.
7. Check the unified safepoint log if there are stops unrelated to GC.
8. Correlate allocation rate, CPU load, threads, and I/O.
9. Reproduce under an equivalent workload to confirm the hypothesis.

A pause may coincide with a slow request without being the sole cause. Check which requests were affected, how large the pause was at that moment, and whether other concurrent factors were involved.

## 14. Common Mistakes When Reading Pause Time

### Confusing GC cycle duration with pause duration

Concurrent phases can run while the application is still serving requests. Use JFR `gc-pauses` or GC log pause lines to measure STW pauses.

### Looking only at the average

Averages hide tail latency. Always inspect P95, P99, maximum, and pause count.

### Double-counting sub-phases

A GC pause can have multiple sub-phases. Do not add sub-phase durations to the total pause if the total pause already includes them.

### Treating MXBean collection time as exact pause time

`getCollectionTime()` is a cumulative metric reported by the collector. It does not provide individual pauses or percentiles. Use JFR for pause analysis.

### Looking only at heap used after GC

Low heap after GC does not prove there were no long pauses. You need to inspect durations, phases, and collection counts.

### Not distinguishing Full GC from concurrent phases

A concurrent cycle can be long while the application continues running through much of it. Separate concurrent phases from STW pauses.

### Not checking safepoints

If the application pauses without a corresponding GC pause, check the safepoint log and VM operations.

### Comparing recordings under different conditions

Different heap sizes, collectors, CPUs, container quotas, or workloads make pause metrics non-comparable directly.

## 15. GC Pause Diagnostic Checklist

- [ ] Identify the correct PID and collector.
- [ ] Record the JDK version, heap size, and CPU/container limits.
- [ ] Enable JFR or unified GC logs during the incident window.
- [ ] Verify the recording covers the right timeframe.
- [ ] Check pause count, total, median, P95, P99, and maximum.
- [ ] Distinguish GC events, pause events, and concurrent phases.
- [ ] Read GC cause and heap before/after.
- [ ] Inspect the GC pause phase breakdown.
- [ ] Check YGC, FGC, CGC, and cumulative times via jstat.
- [ ] Cross-check collection metrics from MXBean when needed.
- [ ] Check safepoints if latency spikes have no GC pause.
- [ ] Correlate pauses with request latency and allocation rate.
- [ ] Identify the root cause before changing heap or GC flags.
- [ ] Re-measure after changes under an equivalent workload.

## 16. Commands to Remember

~~~bash
# Start a JFR recording at JVM startup
java -XX:StartFlightRecording=filename=gc.jfr,settings=profile,duration=60s,dumponexit=true -jar app.jar

# Start a recording on an existing JVM
jcmd <pid> JFR.start name=GC settings=profile duration=60s filename=gc.jfr

# Check recording
jcmd <pid> JFR.check

# Dump and stop
jcmd <pid> JFR.dump name=GC filename=gc-snapshot.jfr
jcmd <pid> JFR.stop name=GC

# Pause distribution and phases
jfr view gc-pauses gc.jfr
jfr view gc-pause-phases gc.jfr
jfr view gc gc.jfr
jfr view gc-cpu-time gc.jfr

# Print detailed GC events
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary gc.jfr

# Unified GC and safepoint logging
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar

# Rotate GC logs
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar

# Sample GC utilization
jstat -gcutil <pid> 1000 10

# Sample GC causes
jstat -gccause <pid> 1000 10

# Inspect heap and collector flags
jcmd <pid> GC.heap_info
jcmd <pid> VM.flags
~~~

GC pause time should be read as a distribution over time, not as a single average number. Use JFR to inspect totals, P95/P99, phases, and heap before/after; use unified logging to pinpoint individual pauses and safepoints; and use `jstat` and MXBeans to track cumulative trends. Once you find the root cause, make targeted configuration changes and re-measure under an equivalent workload.

## References

- [Java Flight Recorder — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/module-summary.html)
- [The jfr Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [The jstat Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [GarbageCollectorMXBean — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Java HotSpot VM Options — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [JDK Troubleshooting Guide: Garbage Collection](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-memory-leaks.html)

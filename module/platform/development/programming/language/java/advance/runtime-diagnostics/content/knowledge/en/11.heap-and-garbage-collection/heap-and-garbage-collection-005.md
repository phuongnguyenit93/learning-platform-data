# 11.5. Distinguishing GC frequency, total GC time, pause time, and time to safepoint

## Objectives

When investigating Java performance, saying "the app is slow because GC runs a lot" is not enough to identify the cause. You must distinguish **how often GC occurs**, **how much time is accounted to GC**, **how long the application actually stops each time**, and **how long the JVM takes to bring threads to a safepoint**. The four quantities have different units, measurement scopes, and impacts; confusing them can lead to tuning the heap or GC in the wrong direction.

This lesson focuses on HotSpot/JDK 17+; log names, counters, and accounting details may differ by JDK and garbage collector.

## 1. What are the four quantities?

| Quantity | Question it answers | Common units | What must NOT be misunderstood |
| --- | --- | --- | --- |
| **GC frequency/rate** | How many GC events of the type under consideration occurred during an interval? | events/minute, events/second | A high count alone does not prove each stop is long or that GC consumes heavy CPU. |
| **Total GC time** | What is the total time the measurement source accounts to collection activity over a window or since JVM startup? | ms, s, sometimes % of window | Depending on the source/collector, it may not equal total application stop time. |
| **Pause time (GC pause duration)** | How long did the JVM pause Java threads for a single GC stop? | ms, p50/p95/p99/max per pause | Not the duration of an entire GC cycle when concurrent phases exist. |
| **Time to safepoint (TTSP)** | After the JVM requests a safepoint, how long does it take to reach the safepoint state? | µs, ms, sometimes ns in logs | Not the time spent executing GC after the safepoint has been reached. |

**Classify events before computing frequency:** young evacuation, mixed, full GC, and concurrent phases/cycles do not have the same impact. One concurrent cycle may contain multiple phases and multiple short pauses. Do not count every `gc` or `gc,phases` log line or every internal phase as an independent "GC". Prefer matching by GC ID, event name, and how the collector structures cycles.

**Name "total GC time" accurately:** for instance, `GarbageCollectorMXBean.getCollectionTime()`, `jstat GCT`, the sum of GC event durations in logs, and the sum of `jdk.GCPhasePause` in JFR are measurements with different semantics. When reporting, state clearly *what is being summed*, *over which window*, and *with which collector/JDK*.

## 2. Timeline: GC, safepoint, and the application

An operation requiring a global safepoint can be viewed along a conceptual timeline:

```text
JVM requests safepoint
       |
       v
[ Reaching safepoint ] -> [ At safepoint / executing VM operation ] -> [ Java threads resume ]
  TTSP (time to reach)       typically includes related STW work
```

- **Safepoint** is a coordination mechanism so the JVM can perform tasks requiring a consistent thread state. Not every safepoint is caused by GC; other VM operations can also request a safepoint.
- **Reaching safepoint** is the interval the JVM waits while coordinating to arrive at the safepoint. Some threads may already be stopped while others have not yet reached a safe point; therefore, TTSP can contribute to the latency observed by application requests.
- **At safepoint** is the portion after the safepoint is reached to perform the requested work, which may be GC work or another JVM operation. Do not assume all `At safepoint` time is GC.
- **GC pause** recorded in GC logs/JFR is the duration of a GC phase that pauses the application within the scope measured by that tool. Its measurement boundaries do not necessarily match `At safepoint` identically; do not subtract GC pause from total safepoint time to infer TTSP unless you have confirmed the exact same event and boundaries.
- **Concurrent GC** (for example, some marking/relocation phases of G1, ZGC, or Shenandoah) can run while application threads keep executing. Thus, wall-clock GC cycle duration can be much longer than individual STW pauses.

With HotSpot JDK 17, `safepoint` logs typically include `Reaching safepoint`, `At safepoint`, and `Total` in nanoseconds; `Total` covers time to safepoint and time at safepoint according to that version's log boundaries. Newer JDKs may add components such as `Leaving safepoint`. Read the actual field names emitted by the running version.

## 3. Windowed formulas and valid comparisons

Suppose you observe a time window of `T` seconds, during which a GC counter increases from `N0` to `N1`:

- **GC rate** = `(N1 − N0) / T` events/second; multiply by 60 for events/minute. Count each GC type separately when comparing behavior.
- **GC-time delta** = `GC_time_end − GC_time_start`. When the source is a cumulative counter (such as JMX/jstat), take the delta between two samples; cumulative values since JVM startup are not the GC time of the current window.
- **GC time ratio** = `GC-time delta / (T × 1000 ms)`, when the numerator is in ms. Label it only as "GC time ratio per measurement source X"; do not rename it to STW fraction when X includes or accounts for other time.
- **STW pause fraction** = `sum(pause_duration_ms) / (T × 1000)` when all pauses in the window have been collected. This is the actual stop-time fraction for the measured set of pauses; do not infer it from GC count.
- **Pause mean** = sum of pauses / pause count; **p95/p99/max** require the list of *individual pause durations*. A low mean can still hide a very long pause.
- **TTSP** needs its own distribution (max/p95/p99) and timestamp correlation with pauses, request latency, and VM operations. Do not arbitrarily fold TTSP into the mean GC pause.

**Notes on metrics:** Use consistent time windows, clocks, and workloads; exclude warm-up periods when comparing steady state. Counters reset when a JVM restarts. Results across different collectors, versions, and tools cannot necessarily be summed together. With few samples, do not treat p99 of a handful of pauses as statistically stable.

### Hand-calculation example

In a **60-second** window, suppose there are **4 STW GC pauses** of **8 ms, 12 ms, 20 ms, and 160 ms**:

- Frequency of *these four events*: `4 / 60 = 0.0667` events/second, or **4 events/minute**.
- Total **STW GC pause**: `8 + 12 + 20 + 160 = 200 ms`, average **50 ms/pause**.
- Measured pause fraction: `200 / 60,000 × 100% ≈ 0.333%` of the window.
- Largest pause: **160 ms**. A 160 ms tail spike still matters for a p99-sensitive system, even though the overall stop percentage is only around 0.33%.

If the exact event with the 160 ms pause also had **Reaching safepoint = 70 ms**, a thread stopped early could experience an impact near **230 ms** (70 + 160 ms, ignoring boundary differences and other tasks). This example illustrates the two phases; do not add arbitrary TTSP values to arbitrary GC pauses without matching the exact event. **The 200 ms above is total pause time; do not automatically assume it equals `jstat GCT` or JMX total collection time.**

## 4. Collecting GC and safepoint logs in JDK 17+

For a newly launched Java process, enable Unified Logging right on the command line:

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC \
  -Xlog:gc*=info,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags \
  GcCountersDemo
```

The `\` line continuation is for Unix-style shells; in PowerShell, place the command on one line or use appropriate line continuation syntax. Depending on load, `gc*` can generate many lines; for long runs, consider log rotation and storage capacity.

A **structural illustration** (not fixed program output):

```text
[2026-01-01T10:00:00.000+0000][12.000s][info][gc] GC(18) Pause Young (Normal) (G1 Evacuation Pause) 40M->9M(64M) 160.000ms
[2026-01-01T10:00:00.001+0000][12.001s][info][safepoint] Safepoint "G1CollectForAllocation", Time since last: 3000000000 ns, Reaching safepoint: 70000000 ns, At safepoint: 160000000 ns, Total: 230000000 ns
```

How to read it:

1. The `gc` line describes a **G1 young evacuation pause**. `160.000ms` is the pause duration reported by the GC log for that event; `40M->9M(64M)` indicates illustrative before/after heap levels and total heap capacity, not time.
2. The `safepoint` line reports that the JVM spent **70 ms reaching safepoint**, **160 ms at safepoint**, and **230 ms total** for the corresponding VM operation. `Time since last` is the elapsed time since the previous safepoint, **not TTSP**.
3. To pair the two lines in real logs, compare timestamps, VM operation type, GC ID, and related phases. Do not assume every safepoint line belongs to GC, or that every pause always has an exact one-to-one safepoint line.

**Unit conversion tip:** `1 ms = 1,000,000 ns`. Thus `Reaching safepoint: 70000000 ns` = **70 ms**, not 70,000 ms.

## 5. Using jstat, JMX, and Java code: counters, not pause distributions

### 5.1 jstat to compare two samples over time

On HotSpot, while the process is still running:

```bash
jstat -gcutil 12345 1000 10
```

`12345` is an example PID; the command takes 10 samples spaced roughly 1,000 ms apart. Common columns:

- `YGC` and `YGCT`: young GC event count and total time accounted for them.
- `FGC` and `FGCT`: full GC event count and related total time.
- `GCT`: total GC time per the JVM's jstat metric; the unit of time columns is **seconds**, whereas durations in GC logs are usually in **ms**.
- Depending on version/collector, there may also be concurrent GC columns (such as `CGC`, `CGCT`). Counters, event types, and support levels vary; read the actual header rather than guessing from another JVM's columns.

For example, if over 10 seconds `YGC` increases from 40 to 45 and `YGCT` increases from 1.20 to 1.32 seconds, that is **5 young GCs / 10 seconds** and **0.12 seconds of young GC time accounted by jstat**. This is insufficient to know the longest pause or p99; detailed GC logs/JFR are required.

### 5.2 Measuring via `GarbageCollectorMXBean` with Java 17

The following program captures counters before and after an allocation burst. It clearly demonstrates taking **count deltas** and **time deltas**, instead of confusing cumulative values since JVM startup with a short window.

Save as **`GcCountersDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.LinkedHashMap;
import java.util.Map;

public class GcCountersDemo {
    private static Map<String, long[]> snapshot() {
        Map<String, long[]> result = new LinkedHashMap<>();
        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            result.put(gc.getName(),
                    new long[] {gc.getCollectionCount(), gc.getCollectionTime()});
        }
        return result;
    }

    public static void main(String[] args) {
        Map<String, long[]> before = snapshot();
        long started = System.nanoTime();

        byte[][] ring = new byte[128][];
        for (int i = 0; i < 30_000; i++) {
            ring[i % ring.length] = new byte[8 * 1024];
        }

        long elapsedNs = System.nanoTime() - started;
        Map<String, long[]> after = snapshot();

        long retainedBytes = 0;
        for (byte[] block : ring) {
            retainedBytes += block.length;
        }
        System.out.printf("Window: %.3f s; retained: %d bytes%n",
                elapsedNs / 1_000_000_000.0, retainedBytes);

        for (Map.Entry<String, long[]> entry : before.entrySet()) {
            String name = entry.getKey();
            long[] start = entry.getValue();
            long[] end = after.get(name);
            if (end == null) {
                continue;
            }
            long events = (start[0] >= 0 && end[0] >= 0) ? end[0] - start[0] : -1;
            long millis = (start[1] >= 0 && end[1] >= 0) ? end[1] - start[1] : -1;
            System.out.printf("%s: eventsDelta=%d, collectionTimeDeltaMs=%d%n",
                    name, events, millis);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 GcCountersDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC \
  -Xlog:gc*=info,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags \
  GcCountersDemo
```

`retainedBytes` is always **1,048,576 bytes** because the final ring buffer holds 128 arrays of 8,192 bytes each. The GC count/time lines and execution duration have **no fixed stdout**: they depend on the JDK, collector, machine architecture, optimizations, and runtime conditions. `-1` indicates the corresponding counter is not supported by the JVM. A value of `eventsDelta=0` is also valid if no GC occurred during the window.

**Important limitation:** `getCollectionTime()` returns the collection time in milliseconds provided by the implementation, which may be approximate; it **does not return individual pauses, p99, or TTSP**, and for concurrent collectors it should not automatically be treated as total application stop time. Separate metrics by bean name and cross-check the collector's logs.

## 6. Obtaining pause distributions with JFR

To inspect individual stops, you can record Java Flight Recorder (JFR) on a running process, for example:

```bash
jcmd 12345 JFR.start name=gcdiag settings=profile duration=60s filename=gcdiag.jfr
jfr print --events jdk.GCPhasePause gcdiag.jfr
```

The `jfr print` command must run after the recording finishes and the file exists. The `jdk.GCPhasePause` event carries `duration` and `gcId`, allowing you to aggregate **total pause ms**, **max**, and **p95/p99** over the recorded pauses. One GC can have multiple pauses; to compute "total pause per GC", group by `gcId` before summing. Events may not be recorded if JFR settings do not enable the corresponding event type; verify the actual settings and recording.

Keep **safepoint timing** from `-Xlog:safepoint=info` separate. JFR may contain related safepoint/GC events, but event types, enablement levels, and fields can vary across versions; do not assume TTSP is always present in `jdk.GCPhasePause`.

## 7. Diagnose by combinations, not a single isolated metric

| Observation | What to check next | Safe assessment |
| --- | --- | --- |
| Frequent GC, short pauses, low total pause | Allocation rate, young generation size, CPU, throughput, post-GC heap | High frequency may be acceptable; insufficient to conclude latency impact. |
| Few GCs but one extremely long pause | Max/p99 pause, Full GC/mixed GC, promotion, heap occupancy, SLA | Tail-latency risk even when total pause time is small. |
| Accounted total GC time climbs rapidly, many short pauses | Compare total with STW pause list; concurrent collector and CPU load | May lose throughput/CPU even if each pause is small; verify counter definition. |
| GC log shows short pauses but `Reaching safepoint` is large | VM operation name, thread states, JNI/native, timestamps, and slow-coordinating threads | Investigate **TTSP** separately; do not rush to resize heap or switch GC. |
| Long `At safepoint` with no matching GC event | Which VM operation triggered it, thread dumps/JFR/related logs | The safepoint may be serving JVM work outside GC. |
| Request latency is high while GC and TTSP are normal | CPU throttling, lock contention, I/O, scheduler, network, application traces | Do not blame all application latency on GC. |

### Practical investigation workflow

1. **State the symptom clearly:** throughput drop, request p99 spike, response freeze, or CPU rise. Mark timestamps and PID/JDK/collector.
2. **Choose a homogeneous measurement window:** e.g., one high-load minute; check for restarts or deployments.
3. **Measure frequency by GC type** and **cumulative time deltas** via counters, then inspect **individual pause durations** via GC logs/JFR.
4. **Cross-check safepoint logs**, especially large `Reaching safepoint` values; identify the VM operation and overlap with request latency spikes.
5. **Inspect memory and CPU pressure:** heap before/after GC, allocation rate, live set, promotion, system CPU/throttling. Separate STW pauses from CPU used by concurrent phases.
6. **Only after gathering evidence** test changing heap/GC settings, allocation intensity, or code delaying safepoint arrival; re-measure under the same workload to compare p95/p99, throughput, and CPU usage.

## 8. Common interpretation mistakes

- **"100 GCs/minute is definitely worse than 2 GCs/minute."** False: examine GC type, total cost, and pause distribution.
- **"GCT = 2 seconds means the application froze for 2 seconds straight."** False: it can be a cumulative sum across multiple collections; the measurement source's semantics must be verified.
- **"An 800 ms concurrent cycle is an 800 ms pause."** False: phases running concurrently with Java threads are not STW.
- **"If GC pause is 20 ms, time to safepoint is also 20 ms."** False: TTSP is measured separately; it can be much higher or lower.
- **"Time since last is TTSP."** False: that field is the interval since the previous safepoint, not the wait to reach the current safepoint.
- **"If there is a safepoint, there is a GC."** False: safepoints also serve other VM tasks.
- **"GCT/T is the fraction of CPU used by GC."** False: wall/elapsed collection time and GC worker CPU time are different measurements.
- **"Total pause divided by GC count is p99."** False: that is the mean when samples align; p99 requires the distribution of individual pauses and enough samples.
- **"Every log line containing GC is one GC."** False: phase lines, stats, and auxiliary messages can share one GC ID.
- **"Tune GC by counting pauses without looking at workload."** False: changes in traffic, heap config, collector, or warm-up state break comparability.

## 9. Self-check questions

1. In 60 seconds there are 30 young GCs, each pausing 2 ms. What is the frequency? What is the total STW pause? **Answer:** 0.5 events/second, 60 ms (0.1% of 60 seconds); from this data alone you cannot deduce JMX total collection time.
2. There is a 400 ms Full GC pause, yet the GC rate is low. For an API requiring p99 under 100 ms, is looking only at rate enough? **Answer:** No; you need the pause distribution and correlation with request latency/timestamps.
3. The log records `Reaching safepoint: 80000000 ns` and `At safepoint: 15000000 ns`. Which value is TTSP? **Answer:** 80 ms is TTSP; 15 ms is time at safepoint; in this style of JDK 17 log the total is about 95 ms.
4. Why can't `GarbageCollectorMXBean.getCollectionTime()` provide p99 pause by itself? **Answer:** It is a cumulative time counter per bean, not a series of individual pause durations.
5. You observe a 200 ms safepoint with no corresponding GC event. What should you do? **Answer:** Check the VM operation name and other safepoint/JFR sources before concluding it is GC.

## Reference documentation

- [Oracle JDK 17 — `java` / Unified Logging and `-Xlog`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle — Troubleshoot Performance Issues Using JFR, GC section and `jdk.GCPhasePause`](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle — `jstat` command, meanings of GC counters](https://docs.oracle.com/en/java/javase/11/tools/jstat.html)
- [OpenJDK — how HotSpot logs `Reaching safepoint`, `At safepoint`, and `Total`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.cpp)

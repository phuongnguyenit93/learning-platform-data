# 15.5 Isolating the symptom time window and cross-referencing multiple event groups

> **Scope:** Analyzing **Java Flight Recorder (JFR)** recordings from a Java 21 JVM when an application shows symptoms such as rising p99 latency, dropping throughput, request timeouts, or CPU spikes. The focus is moving from *external symptom timestamps* to a **verifiable time window**, then examining **GC, CPU, locks/threads, I/O, allocations, and virtual threads** in that same window to build and test hypotheses. This lesson uses JDK Mission Control (JMC), `jcmd`/`jfr` commands, and the `jdk.jfr.consumer` API available in JDK 21.

## 1. Objectives and diagnostic principles

After this lesson, you will be able to:

1. Convert an alert/trace/request log into an **absolute** time interval `[from, to)` on a single UTC axis, recording timestamp sources, timezone, clock skew, and pre/post margins to observe causes and effects.
2. Identify which JFR recording covers that interval; extract the required range via `JFR.dump begin=... end=...` if the recording is still active, or filter events from an existing `.jfr` file.
3. Read event **start/end** timestamps and **durations** accurately; compare event groups within the **same time interval** rather than grabbing prominent events from another time to explain the incident.
4. Distinguish temporal correlation from causation, especially with sampling events, thresholds, collection gaps, and overlapping events.
5. Produce a reproducible evidence table: symptom, window, JFR source, related events/stacks, hypothesis, and next verification step.

**Core rule:** *Isolate the symptom window first, then inspect events.* A long GC pause, hot CPU stack, or long `SocketRead` outside the p99 spike window is not evidence for the incident under investigation. Conversely, multiple event groups spiking in the same window does not by itself prove which caused which.

## 2. Selecting the window from symptom data

### 2.1. Establish anchors outside the JVM

Start from **alerts, latency/error dashboards, tracing, or request logs**. Collect at least: service/instance/pod name, symptom type, start time, end or peak time, metric resolution (1 minute / 10 seconds), timezone, and confidence level.

Hypothetical example (not real data):

| Source | Observation | UTC |
| --- | --- | --- |
| Metrics gateway | p99 rose from ~180 ms to 2.8 s | 10:12:30–10:14:00 |
| Error dashboard | Timeouts increased in the same interval | 10:12:40–10:14:10 |
| Distributed trace | Several downstream service call spans lengthened | 10:12:45–10:13:50 |
| Target JVM | `payment-api`, pod `payment-7c9...`, PID and startup time confirmed | Recording covers 10:05–10:25 |

Define two intervals and always keep a baseline:

- **Symptom window:** e.g., `[2026-10-29T10:12:30Z, 2026-10-29T10:14:10Z)`. Used to measure "during the incident."
- **Expanded analysis window:** e.g., `[2026-10-29T10:11:30Z, 2026-10-29T10:15:10Z)`, adding 60 seconds before/after to spot preceding triggers and recovery. The buffer should match metric scrape cadence and request duration; there is no universal 60-second rule for every system.
- **Reference (baseline) window:** a normal interval of comparable length, load, warm-up state, and identical recording settings if available, e.g., 10:07:00–10:10:40 UTC.

For metrics aggregated in 1-minute buckets, a point labeled "10:13" may represent data accumulated over an entire minute depending on the system's convention. Do not claim millisecond-level onset precision when the dashboard only has 1-minute resolution.

### 2.2. Normalize timestamps and identifiers

In Java, a JFR event provides `Instant getStartTime()` and `Instant getEndTime()`. Use **UTC or `Instant`** as the common axis; convert to local time only for presentation.

```text
2026-10-29 17:12:30 +07:00 = 2026-10-29T10:12:30Z
2026-10-29 17:14:10 +07:00 = 2026-10-29T10:14:10Z
```

Always check:

- **Clock skew:** are the app host, collector, database, and gateway NTP-synchronized? A skew of a few seconds can flip "the event happened before the request."
- **Trace/span timestamps:** start timestamp + duration differs from "request completion timestamp"; reconstruct the request interval `[start, start + duration)` rather than aligning solely on completion logs.
- **JVM identity:** PIDs can be reused after restarts; record pod name, host, container ID, JDK build, and *startup time*. Only compare within the same instance/recording when concluding about the same process.
- **Time zone / JFR CLI:** `JFR.dump begin/end` accepts `Instant` values ending in `Z` in JDK 21; timestamps without a timezone may be interpreted as local time. Prefer ISO 8601 with `Z` and explicitly record log timezones.
- **Boundary points:** defining `[start, end)` prevents double-counting instant events right on the `end` boundary when slicing consecutive buckets.

If clock skew cannot be estimated, widen the observation interval and note the **time-alignment uncertainty** in your conclusion.

## 3. Reading events properly before cross-referencing

JFR has **instant events** (a single timestamp), **duration events** (an interval `[start, end]`), and **sampling events** (samples taken at a point in time). Not every event row means the same thing.

- **`startTime` and `endTime`:** a long event may **start before** the symptom window and **end inside** it. Filtering only by `startTime >= from` misses ongoing events. Test the intersection between `[eventStart, eventEnd)` and `[from, to)`; for instant events, check whether the timestamp lies in `[from, to)`.
- **`duration`:** length of the event itself, not automatically the time a request was impacted. A long `SocketRead` may reflect waiting on a peer; a `JavaMonitorEnter` reflects waiting to enter a monitor.
- **`eventThread`/thread ID, stack trace:** helps link events by thread or call site; threads do not necessarily map 1-to-1 to requests due to executors/virtual-thread scheduling, and one request can span multiple threads.
- **Count / total duration / p95 duration:** metrics are meaningful only for the same event type, same threshold, and comparable window lengths. Do not sum `duration` across overlapping events and call the sum "JVM downtime."
- **`jdk.ExecutionSample` and `jdk.ObjectAllocationSample`:** sample counts indicate hot-path/allocation trends under sampling conditions, **not** exact execution counts or exact allocation counts.
- **Absent events:** may result from recording configuration, thresholds, sampling, buffer loss, missing stack traces, or a non-covering window. Verify the event was enabled before concluding "no problem."

In JDK 21, many blocking I/O/monitor events are only recorded after exceeding a threshold (often around **20 ms** depending on configuration); the `.jfc` profile determines actual values. The same operation repeated thousands of times at 5 ms each may produce zero corresponding events.

## 4. Map of event groups to cross-reference

| Group / example Java 21 event names | What can be observed | Next verification questions |
| --- | --- | --- |
| **CPU/sampling** — `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample` | JVM/machine CPU, thread utilization, sampled stacks | Did JVM CPU rise before or after p99? Are there recurring hot stacks in the window? |
| **GC/safepoint** — `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.SafepointBegin` (if present) | GC timing, pause phases, safepoints | Which pauses intersect the window? Do they explain part of the latency? |
| **Allocation/heap** — `jdk.ObjectAllocationSample`, `jdk.GCHeapSummary` | Sampled allocated objects, heap before/after GC | Did allocation/GC pressure rise before p99 degraded? |
| **Monitor/parking** — `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, `jdk.ThreadSleep` | Monitor lock waits, `Object.wait`, park/sleep | Which stacks or contended resources repeat? Are waiting threads on the request critical path? |
| **Socket/file I/O** — `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` | Long recorded I/O operations, durations, and peer/path fields | Which connection/host/file is slow, matching which downstream spans? |
| **Virtual threads (Java 21)** — `jdk.VirtualThreadPinned` | Virtual thread blocking while pinned to a carrier, duration/stack (if enabled) | Is pinning long and frequent enough to reduce serving capacity? |
| **Exceptions/auxiliary** — `jdk.JavaExceptionThrow`, `jdk.JavaErrorThrow` (if enabled) | Some thrown exceptions/errors | Did they spike near timeouts, on which stacks? Is the overhead of enabling high-volume events acceptable? |

**Do not assume every event is enabled in `settings=default` or `settings=profile`.** Check actual metadata and recording configuration; an event existing in the JDK does not mean it was recorded in the file. Start with groups tied to the symptom, then expand based on evidence.

The names above are full Java 21 **`jdk.*`** names; in `jfr print --events` they can be comma-separated. Some events lack request IDs, endpoints, or downstream service names, offering only stack/thread/host as indirect clues. Combine with APM/logs to identify application context.

## 5. Capturing and slicing JFR files with JDK 21 tools

### 5.1. An existing recording in a running JVM

Verify the right JVM can be attached to; on Linux this requires the same host/appropriate user. Commands with `<PID>` are **templates** and must use the verified PID:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> JFR.check
jcmd <PID> help JFR.dump
```

If a suitable recording **is running and still retains data**, you can extract a specific window with `JFR.dump`:

```bash
jcmd <PID> JFR.dump name=incident \
  begin=2026-10-29T10:11:30Z end=2026-10-29T10:15:10Z \
  filename=/srv/diagnostics/incident-window.jfr
```

**Timestamps and paths are purely hypothetical examples.** The path must be writable on the **target JVM's filesystem**, not necessarily the caller's machine. `JFR.dump` does not stop a running recording; JDK 21 supports `begin`/`end` in absolute time (e.g., `Instant` `...Z`) or local formats, as well as `maxage`/`maxsize` options. It can only extract events **already present in retained recording data**; it cannot recover data from before the recording started or evicted by retention.

Note: long events straddling window edges, metadata, and chunk boundaries can cause results to differ from an event-by-event overlap filter at analysis time. When you need to prove accurately that an event began before the window, keep a **sufficiently wide original recording** and filter using `getStartTime/getEndTime` as in section 7.

### 5.2. JFR was not enabled when the incident occurred

If no recording exists yet, you can only capture **from the moment you enable it onward**, not replay past events. For an ongoing investigation or recurring symptom, after weighing overhead and storage:

```bash
jcmd <PID> JFR.start name=incident settings=profile \
  disk=true maxage=30m maxsize=256m
jcmd <PID> JFR.check
```

Once enough data is captured:

```bash
jcmd <PID> JFR.dump name=incident \
  filename=/srv/diagnostics/incident-all.jfr
```

`30m`/`256m` are **examples**; tune them based on event rate, retention, and disk capacity. `settings=profile` typically captures more data than `default` and can increase overhead; test on staging/canary before prolonged use. If you need lower thresholds to catch short I/O, create a custom `.jfc` or use a vetted JFR configuration and document the change.

### 5.3. When handed an existing `.jfr` file

**Keep the original immutable**, record checksum/source, and use reading tools:

```bash
jfr summary incident-all.jfr
jfr metadata --events jdk.GarbageCollection,jdk.SocketRead incident-all.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident-all.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark incident-all.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite incident-all.jfr
jfr print --events jdk.CPULoad,jdk.ExecutionSample incident-all.jfr
```

`jfr summary` shows event counts/sizes and recording span; it **does not** replace symptom dashboards. `jfr metadata` shows field layouts in the recording. `jfr print` filters by **event name** or **category**; JDK 21's `jfr print` syntax has no `--start/--end` arguments. To filter accurately by time when you only have a file, select an interval in JMC or use the Java API in section 7.

When inspecting detailed stacks:

```bash
jfr print --stack-depth 64 \
  --events jdk.JavaMonitorEnter,jdk.SocketRead incident-all.jfr
```

Do not expect every event to have a stack. Output can be long and contain internal paths/methods; transfer and share files following security policies.

## 6. Visual cross-referencing in JDK Mission Control

JMC is a GUI tool for exploring recordings (may require separate installation). Exact page/tab names vary across JMC releases; the workflow matters more than button labels:

1. **Open the original `.jfr` file** and confirm JVM metadata, duration, timezone, and recording settings; verify the alert interval falls within the recording span.
2. **Set the timeline selection** to cover the expanded window. Compare start/end timestamps shown in JMC with alert UTC timestamps rather than relying on the slider's relative position.
3. **Read the CPU/GC timeline first** to spot long spikes, GC bursts, and latency gaps. Keep the exact same interval selected as you switch pages.
4. **Inspect Method Profiling / Java Application / Threads** (depending on version). Check samples/call trees, monitor contention, and parking; inspect stacks together with thread/timestamps inside the selected window.
5. **Inspect Socket I/O / File I/O**, grouping by host/path and stack; compare against downstream/DB spans if available.
6. **Inspect allocation and virtual thread events** if enabled in the recording; do not infer "none occurred" when events were not recorded.
7. **Switch to the reference window** of equal duration using the exact same grouping and metric definitions to avoid cherry-picking.

For long events, check both **start and end**. For example, a socket read starting at 10:12:10 and ending at 10:13:20 intersects a window starting at 10:12:30 even though its `startTime` lies outside.

## 7. Filtering and summarizing a window with the Java 21 API

Below is a standalone Java program **`WindowJfrReport.java`** using the `jdk.jfr` module built into JDK 21. It **streams** each event with `RecordingFile` instead of loading the entire recording into RAM; accepts two ISO 8601 timestamps with offsets (`Z` or `+07:00`), selects the listed events, and prints **count** and **total overlapping milliseconds** per *event type*.

Create **`WindowJfrReport.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class WindowJfrReport {
    private static final Map<String, String> GROUPS = Map.ofEntries(
        Map.entry("jdk.CPULoad", "CPU"),
        Map.entry("jdk.ThreadCPULoad", "CPU"),
        Map.entry("jdk.ExecutionSample", "CPU"),
        Map.entry("jdk.GarbageCollection", "GC"),
        Map.entry("jdk.GCPhasePause", "GC"),
        Map.entry("jdk.ObjectAllocationSample", "ALLOC"),
        Map.entry("jdk.JavaMonitorEnter", "WAIT"),
        Map.entry("jdk.JavaMonitorWait", "WAIT"),
        Map.entry("jdk.ThreadPark", "WAIT"),
        Map.entry("jdk.ThreadSleep", "WAIT"),
        Map.entry("jdk.SocketRead", "IO"),
        Map.entry("jdk.SocketWrite", "IO"),
        Map.entry("jdk.FileRead", "IO"),
        Map.entry("jdk.FileWrite", "IO"),
        Map.entry("jdk.VirtualThreadPinned", "VTHREAD"),
        Map.entry("demo.PhaseMarker", "MARKER")
    );

    static final class Stat {
        final String group;
        long count;
        long overlapNanos;

        Stat(String group) {
            this.group = group;
        }

        void add(long nanos) {
            count++;
            overlapNanos += nanos;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                "Usage: java WindowJfrReport file.jfr fromISO toISO");
            return;
        }
        Path path = Path.of(args[0]);
        Instant from = OffsetDateTime.parse(args[1]).toInstant();
        Instant to = OffsetDateTime.parse(args[2]).toInstant();
        if (!to.isAfter(from)) {
            throw new IllegalArgumentException("to must be after from");
        }

        Map<String, Stat> stats = new TreeMap<>();
        try (RecordingFile recording = new RecordingFile(path)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();
                String group = GROUPS.get(type);
                if (group == null) {
                    continue;
                }

                Instant begin = event.getStartTime();
                Instant end = event.getEndTime();
                boolean point = !end.isAfter(begin);

                boolean intersects = point
                    ? !begin.isBefore(from) && begin.isBefore(to)
                    : begin.isBefore(to) && end.isAfter(from);
                if (!intersects) {
                    continue;
                }

                long nanos = 0;
                if (!point) {
                    Instant clippedStart =
                        begin.isAfter(from) ? begin : from;
                    Instant clippedEnd =
                        end.isBefore(to) ? end : to;
                    nanos = Duration.between(
                        clippedStart, clippedEnd).toNanos();
                }
                stats.computeIfAbsent(
                    type, key -> new Stat(group)).add(nanos);
            }
        }

        System.out.println("WINDOW UTC: " + from + " .. " + to);
        System.out.printf(
            "%-9s %-29s %8s %12s%n",
            "GROUP", "EVENT", "COUNT", "OVERLAP_MS");
        for (Map.Entry<String, Stat> row : stats.entrySet()) {
            Stat stat = row.getValue();
            System.out.printf(
                Locale.ROOT, "%-9s %-29s %8d %12.1f%n",
                stat.group, row.getKey(), stat.count,
                stat.overlapNanos / 1_000_000.0);
        }
        if (stats.isEmpty()) {
            System.out.println("No selected events in window");
        }
    }
}
```

Compile and run on JDK 21, with **no external libraries** and no preview features:

```bash
javac WindowJfrReport.java
java WindowJfrReport incident-all.jfr \
  2026-10-29T10:11:30Z 2026-10-29T10:15:10Z
```

The two timestamps are an **illustrative window**; replace them with actual times from your recording. Since events in real files vary, **there is no fixed stdout table**. The printed column headers are `GROUP`, `EVENT`, `COUNT`, `OVERLAP_MS`. If the file has none of the selected event types in the interval, it prints `No selected events in window`.

**How to interpret the program's output accurately:**

- `COUNT` is the number of **recorded events** whose interval intersects the window. It does not equal request count, allocation count, or operation count when thresholds or sampling apply.
- `OVERLAP_MS` is the sum of each event's **duration intersecting the window**, excluding portions extending outside. For instant/sampled events, this duration is 0 even when count is large.
- GC events can **nest** (`GarbageCollection` and `GCPhasePause`); I/O/park events can run concurrently across many threads. **Do not sum `OVERLAP_MS` across types/groups to compute "downtime"** or CPU utilization.
- The code filters by **event overlap**, not by thread, stack, or external actor. This is a **lead-generation table**; root-cause investigation still requires drilling down into events, `eventThread`, stacks, host/peer, and request traces.
- Events dropped due to recording limits or disabled settings cannot reappear through a filter.

For very large files, `RecordingFile.readAllEvents` can consume a lot of RAM; the `hasMoreEvents/readEvent` loop in this example avoids holding all events in a list.

## 8. Lab: reproduce a window using a self-created recording

To practice without a live service, use `WindowLab.java` to record a custom `demo.PhaseMarker` (marking phases) and `jdk.ThreadSleep` (a duration event). The recording will contain `warmup`, `slow`, and `recovery` markers alongside `sleep` calls of varying lengths. This lab **does not simulate a production incident**: it only trains reading timelines and windows.

Create **`WindowLab.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Configuration;

public class WindowLab {
    @Name("demo.PhaseMarker")
    @Label("Lab Phase")
    static class PhaseMarker extends Event {
        @Label("Phase")
        String phase;
    }

    private static void mark(String phase) {
        PhaseMarker event = new PhaseMarker();
        event.phase = phase;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording =
                 new Recording(Configuration.getConfiguration("default"))) {
            recording.setToDisk(true);
            recording.enable(PhaseMarker.class);
            recording.enable("jdk.ThreadSleep")
                     .withThreshold(Duration.ofMillis(1));
            recording.start();

            mark("warmup");
            Thread.sleep(40);
            mark("slow");
            Thread.sleep(180);
            mark("recovery");
            Thread.sleep(40);

            recording.stop();
            recording.dump(Path.of("window-lab.jfr"));
        }
        System.out.println("LAB DONE: window-lab.jfr");
    }
}
```

Run with JDK 21:

```bash
javac WindowLab.java
java WindowLab
jfr summary window-lab.jfr
jfr print --events demo.PhaseMarker,jdk.ThreadSleep window-lab.jfr
```

**The only business stdout from `WindowLab`** (excluding `jfr` command output):

```text
LAB DONE: window-lab.jfr
```

`Thread.sleep(180)` is an intentional blocking call, not proof of a CPU spike. The number of `jdk.ThreadSleep` events, timestamp ranges, and stack traces depend on the runtime; do not assume the file contains exactly three sleep events if the JVM records other threads. `demo.PhaseMarker` has point timestamps, whereas `ThreadSleep` is a duration event; practice selecting a window containing just the `slow` phase and comparing it against the entire recording.

After checking the `startTime` timestamps printed by `jfr print`, pick two matching ISO offset timestamps and run the compiled `WindowJfrReport`:

```bash
java WindowJfrReport window-lab.jfr \
  2026-10-29T10:00:00Z 2026-10-29T11:00:00Z
```

**Replace the two timestamps** with the actual range appearing in `window-lab.jfr`; the line above only illustrates syntax and may return no events if timestamps differ. Try narrowing the window to 20–30 ms around a marker to see boundary behavior and how a long sleep event can intersect the window even if it started earlier.

## 9. From event table to hypothesis: investigation example

Suppose p99 jumps from 180 ms to 2.8 s during 10:12:30–10:14:10 UTC, with JFR data from the same JVM (all numbers below are **simulated for analysis practice**, not output from the program above):

| UTC interval | JFR / telemetry | Simulated evidence | Initial assessment |
| --- | --- | --- | --- |
| 10:11:30–10:12:30 | GC + CPU | GC pauses total 50 ms; JVM CPU 42% | Pre-incident window relatively normal |
| 10:12:30–10:13:10 | Socket I/O | Many `jdk.SocketRead` 400–900 ms, same peer/backend | Waiting on downstream is a strong hypothesis; need concrete connection traces |
| 10:13:10–10:13:50 | Thread parking/monitor | `ThreadPark` rises; `JavaMonitorEnter` repeats on same stack | Possibly secondary pool/lock waits as requests pile up |
| 10:12:30–10:14:10 | GC pause | Several short pauses, not aligned with request timeout peak | GC alone does not explain the full p99 |
| 10:12:30–10:14:10 | CPU samples + load | JVM CPU remains below saturation, no standout hot path | Deprioritize CPU-bound hypothesis, noting sample limits |
| 10:14:10–10:15:10 | Socket + latency | SocketRead returns low and p99 drops | Correlated recovery; still need peer-side data |

This is an **evidence chain**, not a verdict that "downstream caused the error." You must verify:

1. `jdk.SocketRead` events lie on the **same request path**; inspect `eventThread`, stack/endpoint if present, and compare timestamps against outbound spans and server-side latency.
2. Check whether `ThreadPark` is waiting on a connection pool, semaphore, or task queue; waits rising **after** long `SocketRead` calls suggest a secondary effect, though pool/queue metrics are needed.
3. Observe CPU/GC before, during, and after; short GCs can still add jitter, but if overall evidence does not explain the p99 magnitude, do not declare GC the primary cause.
4. Compare with a **reference window** at comparable request volume; more `SocketRead` events could simply reflect higher traffic. Normalize per request/s or event/s where appropriate.
5. If a config change, deployment, or traffic shift happened around that time, add it to the timeline to avoid missing causes outside the JVM.

A good report explicitly lists **hypotheses still requiring verification** and the next data to collect, instead of dumping whichever events had the highest raw counts.

## 10. Three traps when comparing multiple event groups

### 10.1. Confusing concurrency with causation

A request stalled on a DB produces a long `SocketRead`; growing queues can increase `ThreadPark`; retries further amplify I/O. All three appear in the same minute, which does not mean "parking caused network timeouts." Order events by **earliest onset, duration span, thread/stack, and parent–child span relationships**.

Timestamps need error bars: when metric buckets are 60 seconds wide and JFR timestamps are finer, do not claim "GC happened 2 ms before the p99 spike" based on a minute bucket.

### 10.2. Confusing event counts with severity

- 1,000 `jdk.ExecutionSample` events is not 1,000 function executions. Use sample ratios by stack to locate hotspots under matching sampling settings.
- `jdk.CPULoad` is a periodic CPU reading containing percentage fields; counting events is not %CPU. When concluding, read the **values** inside the event and cross-check OS/container CPU.
- `jdk.GarbageCollection` and `jdk.GCPhasePause` within the same GC cycle must not be double-counted when reporting pause time.
- `jdk.ThreadPark` and `SocketRead` have durations across threads that **overlap**; total duration across 100 threads can far exceed wall-clock window length.
- `jdk.VirtualThreadPinned` in Java 21 reflects carrier pinning while a virtual thread blocks; a single brief event does not prove poor throughput; compare frequency, duration, and load.
- `ObjectAllocationSample` uses sampling and does not replace exact allocation rates from GC/allocator metrics.

### 10.3. Ignoring recording configuration and data loss

When `SocketRead` or `JavaMonitorEnter` is missing, ask in order:

1. Does the recording even have that **event type** (`jfr metadata`, `jfr summary`)?
2. Was the event enabled in `.jfc` or runtime settings? What was the **threshold**?
3. Does the recording/retention fully cover the symptom window? Did any GC pause or request span in from **before** the window?
4. Could sampling intervals, overhead, or retention/buffer/chunk limits have dropped or truncated data?
5. Do the JVM/instance/clock match the metrics and traces being compared?
6. Do external logs or OS metrics confirm the issue lies outside JFR's scope (downstream network, kernel, cgroup, load balancer)?

**No events** is an observation about the available dataset, never an automatic conclusion of **no problem**.

## 11. Workflow for the first 15 minutes of an investigation

This is a sample operating sequence, not a rigid SLA:

1. **Preserve the symptom:** capture query/graph links, record p95/p99, error/throughput rates, host/pod, UTC `from/to`, and metric resolution.
2. **Verify the right recording:** JDK build, PID/startup time, whether `.jfr` covers the interval and required event settings.
3. **Isolate the window:** anchor the symptom interval, add pre/post buffers; always pick an equivalent reference window.
4. **Filter events:** select the interval in JMC; if a recording is still running, use `jcmd ... JFR.dump begin/end`; for existing files, use `WindowJfrReport` or filter APIs. Preserve the original file.
5. **Compare groups in order:** GC/CPU first, lock/park and I/O next, allocations and virtual threads if indicated. Record timestamps, types, durations, stacks, and threads/peers.
6. **Form falsifiable hypotheses:** e.g., "p99 rose due to connection pool waits following downstream slowness," rather than a vague "JVM was slow."
7. **Demand independent corroboration:** downstream traces, timeout/connection-pool metrics, host CPU/I/O, or change logs; re-check against the reference window.
8. **Write the report and decision:** state the incident, timeline, confidence level, missing data, next measurement, or mitigation. Never tune production from a single chart.

**Short report template:**

```text
Service/JVM:       <service, instance/pod, JDK build, PID/startup>
Symptom UTC:       <from> .. <to>; metric bucket=<resolution>
Analysis UTC:      <from-buffer> .. <to+buffer>
Reference window:  <from> .. <to> (same load/settings)
Recording:         <file, start/end, JFR settings, checksum>
Observations:      <event type, timestamps, duration, stacks/peer>
Hypothesis:        <mechanism, evidence for/against>
Unknowns:          <clock skew, missing event, threshold, lost data>
Next verification: <trace/metric/reproduction and expected result>
Decision:          <owner, action and success metric>
```

When automating reports, store **raw timestamps and units** alongside every number; do not store screenshots alone since they are hard to re-analyze.

## 12. Self-verification exercises

1. Take an alert with timezone `+07:00`, convert it to UTC, and define pre/post buffers. Verify with `Instant` rather than mental math alone.
2. Generate `window-lab.jfr`, inspect the `warmup`, `slow`, and `recovery` markers and corresponding `ThreadSleep` events. Pick 3 windows, run `WindowJfrReport`, and explain why a long-running event can intersect a window even if it started earlier.
3. On a sample recording or test system, build a table from **at least three groups**—GC, CPU, and I/O/lock—alongside a reference window. State what the events **cannot prove**.
4. Change the I/O event threshold in a test JFR config; compare counts and overhead. Explain why comparing results from two different configs requires explicit caveats.
5. Suppose `jdk.GarbageCollection` and `jdk.GCPhasePause` both appear within 500 ms. Explain why total `duration` is not 1,000 ms of downtime.
6. Compare the two statements: "Long `SocketRead` and rising p99 happened at the same time" and "socket reads caused p99 to rise." List the extra data needed to move from correlation to a stronger causal hypothesis.

**End-of-lesson self-check:** normalized UTC/offsets; verified the right JVM/recording/settings; filtered events by window intersection; used the same interval across groups; accounted for thresholds/sampling/overlapping durations; included a reference window and independent evidence; stated confidence levels clearly.

## 13. Java 21 references

- [Oracle JDK 21 — `jcmd`: `JFR.start`, `JFR.check`, `JFR.dump begin/end`, retention](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr`: `summary`, `metadata`, `print`, `view`, filter limits](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `RecordedEvent` (`getStartTime`, `getEndTime`, `getDuration`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle JDK 21 — `RecordingFile` (`hasMoreEvents`, `readEvent`, `write`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 21 — `Recording`, `Configuration`, enabling events in the lab program](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle — Troubleshoot Performance Issues Using Flight Recorder: CPU, I/O, blocking, and thresholds](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)

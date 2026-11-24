# 18.7 Analyzing Latency Spikes Coinciding with GC, Safepoints, Locks, or I/O

> **Context:** Java 21 / HotSpot; a server application experiences rising p95/p99 latency, falling throughput, or timeouts. Within the same time window, **GC**, **safepoints**, **lock contention**, and **slow I/O** may all appear. This lesson shows how to combine **request latency**, **JFR**, **GC/safepoint unified logs**, **thread stacks**, and **traces/metrics** to distinguish which factor truly sits on the request's critical path, which merely coincides in time, and which is a secondary effect.

## 1. The problem to solve: "at the same time" does not mean "caused by it"

A dashboard reports p99 jumping from 150 ms to 1.2 seconds at 10:15 UTC; in that same minute, the JVM logs a 200 ms GC, a safepoint, many threads waiting on monitors, and a burst of `jdk.SocketRead` events. There are at least five possible explanations:

1. A **GC stop-the-world (STW) pause** halted Java threads handling requests; afterward, requests resumed with elevated latency.
2. The JVM entered a **non-GC safepoint**, interrupting Java threads even without a matching GC pause.
3. Many requests **contended on a monitor/lock**; those waiting long enough hit high tail latency. GC or I/O in the same minute might not lie on the critical path.
4. A **downstream service, database, or filesystem** responded slowly; socket/file I/O dragged out, causing requests to wait and queue up. Subsequent monitor contention may simply be a consequence of the backlog.
5. **Multiple factors overlapping:** a single request waited on a lock, experienced an STW pause, and then waited on downstream. Because intervals **overlap**, summing all JFR durations inflates total latency.

**The right conclusion is never the name of the event with the largest duration.** A conclusion must state: *which requests were affected*, *start/end times*, *involved resources/threads/peers*, *degree of overlap with GC/safepoint/waits*, *independent evidence*, and *what would falsify the hypothesis*.

## 2. Distinguishing units of time and signals

| Concept | What does it measure? | What you must NOT automatically infer |
| --- | --- | --- |
| **Request latency** | Time from when a layer begins handling a request until completion per that layer's definition | Not always just JVM execution time; may include proxy queuing, network, and downstream |
| **p95/p99** | Percentile of **a set of requests** in a time bucket, e.g., 1 minute | Not the duration of any single arbitrary "p99 request," nor proof that all requests slowed simultaneously |
| **GC duration** | Duration of a GC activity measured by an event, which may include work running **concurrently with the application** | Not equivalent to the entire time the application was stopped |
| **GC pause / STW** | Interval when the application actually stopped for a GC phase; JFR has `jdk.GCPhasePause` | Do not add total GC duration or safepoint duration for the same operation on top |
| **Safepoint** | JVM coordination point for operations requiring safe thread states; may relate to GC or another VM operation | Not every safepoint is caused by GC; not all GC work happens inside safepoints |
| **Monitor-enter wait** | Time a thread waited to acquire a monitor entering `synchronized`, JFR `jdk.JavaMonitorEnter` | Not equal to the owner's lock-hold time, and not a CPU busy-loop |
| **Monitor wait / park** | `Object.wait`, `LockSupport.park`, or equivalent wait primitives | Not always lock contention; may be an empty pool, task queue wait, or timer |
| **Socket/file I/O** | Duration of an I/O operation recorded by JFR, including wait time per API semantics | Does not by itself prove the network is "broken"; slow peers, pools, kernel, and backpressure can all contribute |
| **JFR execution sample** | Stack samples at active execution instants, e.g., `jdk.ExecutionSample` | Does not give exact CPU time of a Java method or invocation counts |

With **Java 21 virtual threads**, many virtual threads can unmount while waiting on I/O; they do not have fixed OS thread IDs. If blocked while pinned on a carrier, `jdk.VirtualThreadPinned` (when enabled and above threshold) provides an extra signal. Do not automatically assume every virtual-thread `SocketRead` kept a carrier thread blocked.

## 3. Isolating symptom timing and choosing the right windows

### 3.1. Anchor from the user-facing side first

Collect from APM, access logs, tracing, gateway, and service metrics: service/endpoint, instance/pod, error rate, traffic, request count, request start/end, p95/p99, latency buckets, queue depth, and upstream/downstream spans. Record **timezone and resolution**.

Purely **hypothetical** example:

```text
Service:        checkout-api / pod checkout-7cd... / Java 21
Symptom UTC:    2026-10-29T10:15:00Z .. 2026-10-29T10:16:30Z
Metric bucket:  10s; p99 rose from 150ms to 1200ms
Analysis UTC:   2026-10-29T10:14:30Z .. 2026-10-29T10:17:00Z
Control UTC:    2026-10-29T10:10:00Z .. 2026-10-29T10:12:30Z
JVM identity:   PID + process start time + JDK vendor/build + pod
```

The three windows serve distinct purposes:

- **Symptom window:** where user-facing metrics degraded. Do not equate a bucket's timestamp with the exact timestamp of an individual request.
- **Expanded analysis window:** includes time **before** to catch preceding triggers (GC, downstream saturation, pool queues) and time **after** to observe recovery.
- **Control window:** a normal interval sufficiently comparable in length, workload, app version, collector configuration, and JFR settings, used as a baseline.

If traffic jumped from 100 to 1,000 requests/s, a 10x rise in event count may simply be a product of volume. Where appropriate, compare **events/request**, **events/second**, duration percentiles, and request critical-path composition rather than raw event counts.

### 3.2. Normalize every source to one clock

JFR uses absolute timestamps; unified logs may record JVM uptime or `utctime` if configured. Distributed traces, APM, and ingress logs typically use epoch/UTC but may display local time. Never compare `"10:15"` against `"10:15"` without verifying timezone and clock sync.

```text
10:15:00.000Z     = 17:15:00.000 +07:00
Request [start,end) = [10:15:00.000Z, 10:15:00.900Z)
```

- Record **NTP/clock skew** across JVM, proxy, DB, and monitoring collectors. With ±3 seconds of skew, you cannot prove GC preceded a 200 ms socket timeout across two separate hosts.
- Record JVM **start time/PID**, since restarts produce a new PID or reuse an old one.
- For logs containing only `uptime` (e.g., 473.250 s), align against startup time **of the same process**; ideally configure `utctime,uptime` from the start.
- If APM starts the server span when the request enters a handler while the gateway also measures queuing, investigate the difference **outside the handler**.
- Define half-open windows **`[start,end)`** so instantaneous events on the boundary between two consecutive buckets are not counted twice.

**Never treat `System.nanoTime()` from two different machines as one absolute clock.** It measures elapsed duration locally, with no shared origin with UTC elsewhere.

## 4. Event map across four hypotheses

| Category | Java 21 JFR / log evidence | Details to inspect | What to verify outside JFR |
| --- | --- | --- | --- |
| GC | `jdk.GarbageCollection`, `jdk.GCPhasePause`, collector-specific GC events; `-Xlog:gc*` | GC ID, phase pauses, start/end, and GC cause if present | Allocation rate, heap occupancy, GC collector, actual pause overlap with requests |
| Safepoint | `-Xlog:safepoint` / safepoint debug; safepoint events if enabled in JFR | VM operation, time for threads to reach safepoint, time at safepoint | Coinciding GC vs. other JVM activity, actual request duration affected |
| Locks/waits | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, `jdk.ThreadSleep`, `Thread.print -e -l` | Thread/stack, monitor class/address, wait time, lock owner if available | Which threads are on the critical path, what the owner is busy/waiting on, pool and queue metrics |
| I/O | `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` | Duration, thread/stack, remote endpoint, file/path, bytes if captured | Downstream spans, network retries, TCP/DB/pool, disk queues/timeouts |
| Supporting | `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample`; tracing, metrics | CPU saturation, runnable code, relevant stack samples | CPU quota/throttling, thread scheduling, host/process pressure |

**Never assume every event is enabled** in `default.jfc` or `profile.jfc`. Events can be gated by thresholds, sampling, or retention limits. Verify with `jcmd ... JFR.check verbose=true`, `jfr metadata`, `jfr summary`, and the actual `.jfc` config. Absence of events **does not mean** absence of lock waits or I/O delays; frequent operations below threshold can accumulate heavily.

### 4.1. GC: distinguishing collector activity from application pauses

With G1 and collectors that have concurrent phases, `jdk.GarbageCollection` can cover activity longer than actual application pauses. To see how much tail latency was impacted, prioritize **STW pause intervals** (`jdk.GCPhasePause`, the GC Pauses view in JDK Mission Control, and unified GC logs).

- An 800 ms concurrent marking cycle does not mean requests were paused for 800 ms.
- A 120 ms pause overlapping a 900 ms request explains **at most the overlapping portion** by timeline and mechanism, never the full 900 ms by itself.
- When multiple GC pauses overlap one request, take the **union of overlapping intervals** rather than summing nested phase events.
- If p99 rises while GC pauses inside the symptom window remain small and similar to the control window, deprioritize "GC is the primary cause" without dismissing it completely.

**GC count, total GC duration, and sum of pauses are three distinct quantities.** Use GC ID and phase names to avoid double-counting events from the same GC cycle.

### 4.2. Safepoints: they can occur without GC

Safepoints allow the JVM to perform VM operations requiring coordinated Java thread states. In logs, separate: time requesting/waiting for threads to reach the safepoint, time executing the operation once threads are ready, and total stopped/impacted time as reported by the JVM.

Cases to consider:

- **GC-triggered safepoint:** safepoints and STW GC pauses are tightly linked. **Do not add** safepoint duration and GC pause as two separate pauses.
- **Non-GC safepoint:** safepoint events can stem from non-GC VM operations depending on workload/JVM. If GC logs show no matching pause, read the VM operation name instead of blaming the collector.
- **Long time to safepoint:** a thread may take time to reach a safe state; inspect safepoint logs at authorized detail levels, thread states, and native/JNI context.
- **Coinciding JVM activity:** check `start/end` ordering of the safepoint relative to requests and GC instead of attributing every slowdown to "safepoint."

`-Xlog:safepoint` is a direct evidence source, yet **log levels and output fields vary by JDK build/collector**. Do not hard-code a brittle parser from a single log example across all JVMs.

### 4.3. Locks: reading three distinct wait mechanisms accurately

| JFR event | Description | How to investigate |
| --- | --- | --- |
| `jdk.JavaMonitorEnter` | Contention time while a thread **attempts to enter** a `synchronized` Java monitor | Find waiter stacks, monitor class, and lock-holding thread where available; compare with `Thread.print -l` |
| `jdk.JavaMonitorWait` | Thread called `Object.wait(...)`, **released the monitor**, and waits for notify/timeout before resuming | Do not confuse with blocked monitor entry; inspect the condition and notifier |
| `jdk.ThreadPark` | Thread parked via `LockSupport`/concurrency primitives; can stem from queues, `ReentrantLock`, `Future`, pools, latches | Inspect stack/caller/queue length; `ThreadPark` **does not prove** a lock owner is busy |

A lock holder itself can hit a GC pause or wait on I/O, extending waiter durations. In that case, a long `JavaMonitorEnter` is **a symptom of a prolonged critical section**; optimizing the work inside the lock or downstream call may be more effective than swapping lock implementations.

Never treat many `BLOCKED` threads as proof of "CPU overload." Monitor waiting generally means threads are not executing CPU computations. With virtual threads on Java 21, `jdk.VirtualThreadPinned` can add context, though you still must inspect duration, blocking behavior, and actual stacks.

### 4.4. I/O: a long event is only the starting point

`jdk.SocketRead` can be long while a request waits for data from a downstream server. Potential causes include:

- Slow downstream processing or queuing in a DB, cache, or HTTP service.
- Network jitter, retransmissions, DNS/pool/connect phases, or backpressure.
- The request was already delayed before the socket read—e.g., waiting on a connection pool—so `SocketRead` is only the final leg.
- A thread holds a lock while waiting on I/O, forcing other threads to queue on the monitor.
- File I/O affected by disk saturation or storage/network filesystem delays.

Check **`eventThread`, stack, endpoint/port/path, bytes, request span, timestamps**, and the full request lifecycle. A long `SocketRead` is not automatically a network fault: the peer may be running slow valid logic, or the app may be calling APIs sequentially.

Never sum the durations of 100 concurrent `SocketRead` events and report "100 seconds of downtime" if they occurred inside a single 1-second real-time window. Cumulative thread wait time **differs** from one request's wall-clock elapsed time and from whole-JVM downtime.

## 5. Safe collection with JDK 21

### 5.1. Identify the JVM and record symptoms first

On the host/container running the JVM, with appropriate attach permissions (replace `<PID>` with the verified PID):

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> JFR.check verbose=true
jcmd <PID> help JFR.dump
```

`jcmd` requires the same machine and matching effective UID/GID as the JVM; container PID namespaces can make host PID and container PID differ. Never use `jcmd 0` or a main-class selector when targeting **one** specific JVM.

Save monitoring metrics for **the same UTC window**: process CPU, GC pauses/counts, heap usage, request latency and throughput, error rate, OS I/O, network, CPU quota/throttling, queue/pool sizes, and downstream service timestamps.

### 5.2. If an incident recording already exists

Keep the original `.jfr` file immutable and inspect the recording's time span:

```bash
jfr summary incident.jfr
jfr metadata --events jdk.GCPhasePause,jdk.SocketRead incident.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark incident.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite incident.jfr
```

`jfr print --events` **filters by event type**, not by your symptom window. A file holding 30 minutes of data cannot be attributed to a single p99-spike minute just by looking at whole-file counts. Select the window in JDK Mission Control or use the API program in section 9 to compute overlap statistics.

If a recording **is currently running and still retains events**, you can dump a historical slice with `begin`/`end`:

```bash
jcmd <PID> JFR.dump name=latency \
  begin=2026-10-29T10:14:30Z end=2026-10-29T10:17:00Z \
  filename=/srv/diagnostics/incident-window.jfr
```

`latency`, the path, and timestamps are **examples**. This is JDK 21 syntax for a recording named `latency`; confirm the recording name with `JFR.check`. The target JVM needs write permissions to the directory **inside the JVM's own filesystem**. `JFR.dump` does not stop the recording, nor can it recover events from before the recording started or already evicted by retention.

### 5.3. If no JFR exists yet and the issue is recurring

Based on collection risk and available resources, start a recording **now** to catch the next occurrence; you cannot inspect unrecorded past events:

```bash
jcmd <PID> JFR.start name=latency settings=profile \
  disk=true maxage=30m maxsize=256m
jcmd <PID> JFR.check verbose=true
```

Once symptoms recur and sufficient data is captured:

```bash
jcmd <PID> JFR.dump name=latency \
  filename=/srv/diagnostics/incident-full.jfr
```

`profile` captures more data than `default` and carries higher overhead; `30m`/`256m` are illustrative only and must be sized for event rate, disk quotas, and bandwidth. If you need events below default thresholds, prepare a custom `.jfc`, test on staging/canary, and record the exact settings used. Enabling excessive exception/stack events at ultra-low thresholds can itself alter latency.

**Never enable Heap Statistics just to analyze latency**, as it can trigger extra old-generation collections and skew measurements.

### 5.4. Collecting GC and safepoint unified logs for correlation

Configure at startup (Linux example; directory must exist and be writable):

```bash
java -Xlog:gc*,safepoint:file=/srv/logs/gc-safe-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -jar app.jar
```

This enables GC and safepoint tag sets at default levels for those selections, writes logs with **UTC timestamps + JVM uptime**, and rotates files. `app.jar` and paths are illustrative; do not turn on broad `trace` tags in production without measuring overhead. `filecount`/`filesize` are approximate rotation limits, not exact byte guarantees.

If the app is already running without those logs, **runtime log adjustments via `jcmd <PID> VM.log`** are supported to some degree in JDK 21; check `jcmd <PID> help VM.log` and obtain operational approval before running. Enabling logs now provides evidence only from that moment onward—it cannot recover earlier safepoints.

In reports, include **GC ID, phase, pause duration, and safepoint operation**. Do not count a GC-triggered safepoint as an "extra pause" on top of the GC pause recorded for the same interval.

### 5.5. When suspecting monitor contention or stuck threads

Capture **a few timestamped snapshots** during the incident window, keeping `Thread.print` overhead in mind:

```bash
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -e -l
```

JDK 21 documentation classifies `Thread.print` as **Medium** impact depending on thread count; do not take hundreds of back-to-back full dumps on services with thousands of threads. One `BLOCKED`/`WAITING` snapshot is just a single slice; compare multiple timestamps alongside JFR events to confirm persistent waiting.

For virtual threads, traditional `Thread.print` does not display all virtual threads; consider virtual-thread dump tooling and JFR as appropriate. Do not assume a virtual thread has a fixed OS TID to match against `top -H`.

## 6. Aligning on one timeline: example of computing overlaps correctly

A slow request took **900 ms**. Below are **hypothetical intervals on the same request/JVM** in milliseconds since request start:

```text
Request wall-clock: [0,900) ms

                         0   100  200  300  400  500  600  700  800  900
Request             :     |=============================================|
JavaMonitorEnter    :         [ 80.............250)
Safepoint interval  :                [195............335)
GCPhasePause        :                 [200........330)
SocketRead          :                             [350................770)
```

| Phenomenon | Interval | Duration | Interpretation |
| --- | --- | --- | --- |
| Waiting to enter monitor | `[80,250)` | 170 ms | Thread on critical path may have waited on lock |
| JVM safepoint | `[195,335)` | 140 ms | Overlaps with monitor wait; check operation |
| GC pause | `[200,330)` | 130 ms | Already **inside** the safepoint in this example |
| Socket read | `[350,770)` | 420 ms | Request waited for data from hypothetical peer/DB |
| Request | `[0,900)` | 900 ms | Total elapsed at a defined measurement layer |

Summing the four durations (`170+140+130+420 = 860 ms`) commits at least two errors: **GC already sits inside the safepoint**, and the safepoint **overlaps** the monitor wait. You cannot simply label 860 ms as "the delay caused by four factors."

Computing the union of the three wait/safepoint/IO groups (with GC a subset of safepoint):

```text
Monitor [80,250) ∪ Safepoint [195,335)  = [80,335)  (255 ms)
Socket  [350,770)                       = [350,770) (420 ms)

Union of observed intervals in example = 255 + 420 = 675 ms
Remaining request time outside union   = 900 - 675 = 225 ms
```

**Even 675 ms is NOT "guaranteed time lost to these four causes"**: some intervals may belong to another thread or safepoints that did not block this specific request; multi-thread timings can nest; and the unclassified 225 ms may include CPU, queuing, application work, or waits omitted by thresholds.

Intersection for an event interval `[a,b)` and symptom `[c,d)`:

```text
overlap = max(0, min(b,d) - max(a,c))
```

For **instantaneous** events (duration = 0), test `c ≤ timestamp < d`; do not sum durations to 0 and conclude "no events." For long events starting before the symptom window, filtering **by `startTime` alone** misses the overlapping portion.

### 6.1. Event collections lack request IDs

Most JFR events are JVM telemetry and **do not carry HTTP request IDs**. At 10:15, the same JVM may serve 50 requests, one GC, and 200 `SocketRead`s; timestamps alone cannot tell which event belongs to a p99 request.

Correlate using **request traces and stacks/threads/endpoints**, custom JFR events, or existing instrumentation. If the app uses executors, async callbacks, or virtual threads, a single request may switch threads. Thread ID and `eventThread` are clues, not enough by themselves to reconstruct parent-child request chains.

### 6.2. Separating root causes from secondary effects

Suppose the timeline shows: downstream response slowed first, then the connection pool filled up, many callers parked, and finally a logger monitor became contended. Everything looks "simultaneous" on dashboards, yet the likely chain is:

```text
Downstream queue / slow response
        ↓
SocketRead duration and in-flight requests rise
        ↓
Connection-pool queue / ThreadPark rise
        ↓
Request backlog, retries, thread contention rise
        ↓
p99 and timeouts rise
```

This is a **testable hypothesis** using downstream spans, pool metrics, retry counts, and onset timestamps. Never declare causality from a single JFR file alone.

## 7. JDK Mission Control workflow: inspecting layer by layer

In JMC (page names may vary slightly by version):

1. Open the `.jfr` file and verify **JDK build, JVM identity, recording start/end, config, and duration**.
2. Select the exact **analysis window** on the timeline; align timestamps with APM/gateway and account for clock drift. Keep the selection consistent across tabs.
3. Inspect **GC pauses**: do not stop at generic "GC duration"; locate actual pauses, GC IDs, and see whether they overlap request spikes. Compare with safepoint logs.
4. Inspect **threads/locks**: monitor contention, thread parking/waiting, and waiter/owner stacks if present. Use durations/timestamps, not raw counts alone.
5. Inspect **Socket I/O / File I/O**: which peers/files are unusually slow, focusing on relevant threads/stacks and downstream spans.
6. Check **CPU/ExecutionSample** to rule out CPU saturation slowing requests down; also cross-check GC, safepoints, and thread scheduling.
7. Open a **control window** of matching duration and settings; compare rates/percentiles rather than raw event counts.
8. Return to tracing/metrics to confirm the request critical path and validate hypotheses. Produce an evidence table listing both supporting and contradicting data.

JMC visualizes timelines; **it does not automatically infer causality**. If an event type is missing from the recording, mark it "insufficient data" rather than assuming zero.

## 8. Java 21 lab: generating lock wait and I/O wait in one recording

This lab runs **standalone**, using only a local loopback socket with no external servers. It creates two distinct phases:

- Thread `monitor-owner` holds a `synchronized` monitor while waiting on a `CountDownLatch`; thread `monitor-waiter` tries to enter the monitor and blocks.
- Thread `mock-peer` waits about 180 ms before sending one byte; the client `SocketRead` waits on the peer.
- Custom JFR instant events `demo.Phase` mark phase boundaries to compare against `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, and `jdk.SocketRead`. Exact durations depend on scheduler, OS, and JDK; **this is not a production latency benchmark**.
- The lab **does not force GC/safepoints**, so significant GC pauses may not occur. Use another Java 21 recording with real GC and safepoint logs for the GC correlation side; never call `System.gc()` in production just to generate evidence.

Create **`LatencySignalsLab.java`**:

```java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class LatencySignalsLab {
    private static final Object MONITOR = new Object();

    @Name("demo.Phase")
    @Label("Lab phase marker")
    public static class Phase extends Event {
        @Label("Phase name")
        String name;
    }

    private static void mark(String name) {
        Phase phase = new Phase();
        phase.name = name;
        phase.commit();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording(
                Configuration.getConfiguration("profile"))) {
            recording.setToDisk(true);
            recording.enable(Phase.class);
            recording.enable("jdk.JavaMonitorEnter")
                     .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.SocketRead")
                     .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.ThreadPark")
                     .withThreshold(Duration.ofMillis(1));
            recording.start();

            mark("lock-start");
            lockPhase();
            mark("lock-end");
            System.out.println("LOCK PHASE COMPLETE");

            mark("io-start");
            socketPhase();
            mark("io-end");
            System.out.println("IO PHASE COMPLETE");

            recording.stop();
            recording.dump(Path.of("latency-signals.jfr"));
        }
        System.out.println("LAB DONE: latency-signals.jfr");
    }

    private static void lockPhase() throws Exception {
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch attempting = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (MONITOR) {
                locked.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "monitor-owner");
        Thread waiter = new Thread(() -> {
            attempting.countDown();
            synchronized (MONITOR) {
            }
        }, "monitor-waiter");

        owner.start();
        locked.await();
        waiter.start();
        attempting.await();
        try {
            Thread.sleep(180);
        } finally {
            release.countDown();
        }
        owner.join();
        waiter.join();
    }

    private static void socketPhase() throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {
            Thread peer = new Thread(() -> {
                try (Socket conn = server.accept()) {
                    Thread.sleep(180);
                    conn.getOutputStream().write(42);
                    conn.getOutputStream().flush();
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            }, "mock-peer");
            peer.start();
            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(), server.getLocalPort())) {
                int value = client.getInputStream().read();
                if (value != 42) {
                    throw new IllegalStateException("Unexpected response: " + value);
                }
            }
            peer.join();
        }
    }
}
```

Compile and run with **JDK 21** in a writable test directory:

```bash
javac LatencySignalsLab.java
java LatencySignalsLab
jfr summary latency-signals.jfr
jfr print --stack-depth 64 \
  --events demo.Phase,jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead \
  latency-signals.jfr
```

**Stdout printed by the Java program**, excluding `jfr` commands and system messages:

```text
LOCK PHASE COMPLETE
IO PHASE COMPLETE
LAB DONE: latency-signals.jfr
```

Inspecting the recording shows `demo.Phase` markers `lock-start`, `lock-end`, `io-start`, `io-end`. A long `jdk.JavaMonitorEnter` on `monitor-waiter` shows waiting to enter `synchronized`; `jdk.ThreadPark` can appear on `monitor-owner` because it awaits `CountDownLatch` **while still holding the monitor**. This illustrates why **a park is not always the contended primitive itself, but can be why the lock holder kept the monitor so long**.

`jdk.SocketRead` normally appears between `io-start` → `io-end`, without guaranteeing identical counts or durations across every JDK/OS. If an event is missing, check thresholds, recording settings, JVM build, and runtime behavior. Do not run demos on production servers.

## 9. Window-overlap analysis with a Java 21 program

If you need to filter a `.jfr` file accurately by **time window**, use `RecordingFile` in module `jdk.jfr`. `LatencyWindowReport.java` below streams events sequentially, counts recorded events intersecting the window, and totals **millisecond-overlap per event type**.

Create **`LatencyWindowReport.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class LatencyWindowReport {
    private static final Set<String> SELECTED = Set.of(
        "jdk.GarbageCollection",
        "jdk.GCPhasePause",
        "jdk.JavaMonitorEnter",
        "jdk.JavaMonitorWait",
        "jdk.ThreadPark",
        "jdk.SocketRead",
        "jdk.SocketWrite",
        "jdk.FileRead",
        "jdk.FileWrite",
        "demo.Phase"
    );

    static class Totals {
        long count;
        long overlapNanos;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                "Usage: java LatencyWindowReport file.jfr fromISO toISO");
            return;
        }
        Instant from = OffsetDateTime.parse(args[1]).toInstant();
        Instant to = OffsetDateTime.parse(args[2]).toInstant();
        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("from must precede to");
        }
        Map<String, Totals> totals = new TreeMap<>();
        try (RecordingFile recording = new RecordingFile(Path.of(args[0]))) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();
                if (!SELECTED.contains(type)) {
                    continue;
                }
                Instant start = event.getStartTime();
                Instant end = event.getEndTime();
                boolean instant = !end.isAfter(start);
                boolean intersects = instant
                    ? !start.isBefore(from) && start.isBefore(to)
                    : start.isBefore(to) && end.isAfter(from);
                if (!intersects) {
                    continue;
                }
                long nanos = 0;
                if (!instant) {
                    Instant clippedStart =
                        start.isAfter(from) ? start : from;
                    Instant clippedEnd =
                        end.isBefore(to) ? end : to;
                    nanos = Duration.between(
                        clippedStart, clippedEnd).toNanos();
                }
                Totals t = totals.computeIfAbsent(
                    type, key -> new Totals());
                t.count++;
                t.overlapNanos += nanos;
            }
        }
        System.out.println("WINDOW: " + from + " .. " + to);
        for (Map.Entry<String, Totals> row : totals.entrySet()) {
            System.out.printf(java.util.Locale.ROOT,
                "%s count=%d overlap_ms=%.1f%n",
                row.getKey(), row.getValue().count,
                row.getValue().overlapNanos / 1_000_000.0);
        }
        if (totals.isEmpty()) {
            System.out.println("No selected events in window");
        }
    }
}
```

Compile and pass an **ISO-8601 window with offset**, for example:

```bash
javac LatencyWindowReport.java
java LatencyWindowReport incident.jfr \
  2026-10-29T10:14:30Z 2026-10-29T10:17:00Z
```

Or with the lab, substitute `latency-signals.jfr` and **use real timestamps** from `jfr print`. Because recordings differ, **there is no fixed stdout table**; the program always prints `WINDOW: ...` followed by `event type count=... overlap_ms=...` lines, or `No selected events in window` if none match.

**Critical report limitations:**

- `count` reflects only **captured events** exceeding thresholds, not true operation counts.
- Per-type `overlap_ms` sums **event durations** intersecting the window **without deduplicating nesting among same-type events** or overlaps across **multiple threads**.
- `jdk.GarbageCollection` and `jdk.GCPhasePause` cannot be summed into STW duration. Safepoint logs must be correlated separately since this program does not parse safepoint logs.
- Zero-duration events (`demo.Phase`) show a count with `overlap_ms=0`. They are **timeline markers**, not evidence that "nothing happened."
- The program has no notion of request ID or critical path; causal analysis requires traces/stacks/peers and **per-request interval union** logic.

The program uses `RecordingFile.hasMoreEvents()/readEvent()` to avoid loading every event into a large list in RAM; for huge files, still budget scan time and disk space for file copies.

## 10. Four scenarios distinguishing the primary cause

### 10.1. GC pause partially overlapping tail latency

**Observation:** p99 reaches 900 ms; JFR has a 130 ms `jdk.GCPhasePause` overlapping the request, plus a 500 ms `SocketRead`. **Interpretation:** GC can explain at most the overlap of 130 ms, not the entire 900 ms alone. Check the request trace for socket waits and how the request progressed after GC ended.

**Next checks:** Compare requests not overlapping GC, distribution of other GC pauses, instance pause metrics, and correlation between GC phases and backlogs. Do not immediately increase `-Xmx` or swap collectors when primary evidence points downstream.

### 10.2. Long safepoint while GC logs stay quiet

**Observation:** p99 spikes for 800 ms and safepoint logs show a long operation, while `GCPhasePause` is negligible in the same window. **Interpretation:** Safepoints may be involved, yet **you must not automatically call it GC**.

**Next checks:** VM operation name, time-to-safepoint, operation duration, thread/JNI context; verify matching JDK, GC logs, and time window. If the operation did not touch critical request threads or clocks were skewed, revise the hypothesis.

### 10.3. Monitor contention whose owner is waiting on I/O

**Observation:** `JavaMonitorEnter` across many workers lasts 400 ms; the owner stack shows I/O or a park inside the critical section; the owner's `SocketRead` is also long. **Interpretation:** Lock contention is the immediate symptom for waiters, yet **holding a lock while waiting on I/O** may be the deeper cause.

**Next checks:** Actual lock owner and call stack, critical-section length, outbound spans, queued waiters, and timeouts. The proper fix may be moving blocking I/O **outside the `synchronized` block**, after verifying thread safety and correctness.

### 10.4. Long SocketRead, normal GC, unsaturated CPU

**Observation:** GC pauses are tiny, safepoint activity is normal, threads mostly wait on sockets for 1 second, and the peer DB shows queuing/slow queries. **Interpretation:** Downstream I/O is a stronger hypothesis than JVM pauses.

**Next checks:** DB traces, pool borrow times, TCP retries, network metrics, timeout/retry policies, and request rate. If JFR records socket reads only **after** requests already waited long in an ingress queue, expand the timeline outside the JVM.

## 11. Common pitfalls

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| "1 second GC duration → 1 second JVM pause" | Concurrent phases exist; duration ≠ STW pause | Use GC pause events/JMC GC Pauses and safepoint logs |
| "Safepoint + GC pause = two separate stops" | Same operation can overlap/nest | Align timelines and GC IDs; take interval unions |
| "Many simultaneous `JavaMonitorEnter`s mean high CPU" | Waiters may be `BLOCKED`, not running on CPU | Check thread states, CPU/OS metrics, and owner stacks |
| "`ThreadPark` means deadlock" | Park is a normal primitive for queues/latches/pools | Inspect callers, owners, queues, progress, and durations |
| "`JavaMonitorWait` is the same as waiting to enter `synchronized`" | `Object.wait` releases the monitor before waiting | Distinguish condition waits from entry contention |
| "A long `SocketRead` = network failure" | Peer, pool, retries, app logic, or scheduling can stretch it | Combine remote spans, endpoints, and file/socket metrics |
| "No event seen = cause did not occur" | Thresholds/config/retention/sampling/dropped data | Inspect `.jfc` and event metadata first |
| "Sum all event durations = request latency" | Parallel, nested, different requests, different threads | Intersect/union intervals on a verified **critical path** |
| "One thread dump identifies the lock owner" | Snapshot may catch an unrepresentative phase | Take multiple snapshots and events within the symptom window |
| "p99 spiked in minute 10:15 so GC at 10:15:00 caused it" | Bucket metrics lack per-request precision | Trace request start/end and check clock skew |
| "JFR profile has zero latency impact" | Capturing events, stacks, and thresholds all have overhead | Load test, pick sufficient settings, and bound capture duration |
| "Saw correlation so tune JVM flags immediately" | Risks treating the wrong symptom | Form a falsifiable hypothesis and compare metrics post-change |

## 12. Production runbook: before, during, and after

### Before capturing

- [ ] Identify service/endpoint/pod/PID, startup/JDK build, and where request latency is measured (gateway vs. application).
- [ ] Record symptom window, control window, timezone, resolution, and clock skew.
- [ ] Verify permissions for JFR/`jcmd`, writable file path, disk quota/headroom, retention, and read access controls.
- [ ] Choose proportional JFR config/thresholds; benchmark overhead if increasing event volume or stack depth.
- [ ] Prepare GC/safepoint logging with UTC timestamps and log rotation; never induce STW operations in production purely to experiment.

### During investigation

- [ ] Preserve traces/metrics/request volume, CPU, GC pauses, safepoints, pools, and downstream latency.
- [ ] Capture/`JFR.dump` from the right JVM and symptom window, avoiding retention/window mismatches.
- [ ] Inspect `jdk.GCPhasePause` and GC IDs **before** blaming GC.
- [ ] Inspect safepoint operation and timings (time-to-safepoint + operation) **without double-counting** GC pauses.
- [ ] Inspect lock owner/waiter stacks, `ThreadPark`, and I/O endpoints/files/peers; attach to requests only with strong correlation.
- [ ] Compare timings, event durations, sampling/thresholds, and the control window; document contradicting evidence too.

### After investigation

- [ ] Report **one unified UTC timeline**, primary/secondary hypotheses, confidence level, missing data, and SLO impact.
- [ ] Propose a **falsifiable verification test**: e.g., after shortening lock hold time, monitor waits and p99 must drop under identical load.
- [ ] Re-measure p95/p99, error rate, throughput, CPU-seconds/request, GC pauses, pool queues, and downstream latency after changes.
- [ ] Preserve original recordings, checksums, and context; `.jfr` files can contain internal classes/methods/hosts/paths—do not share publicly.
- [ ] Delete or retain per policy; do not leave sensitive diagnostic data sitting indefinitely in temp directories.

## 13. Responsible conclusion template

**Hypothetical evidence-backed example:**

```text
Symptom:
  checkout-api p99 jumped 150ms -> 1200ms during 10:15:00..10:16:30 UTC.
Scope:
  pod X, Java 21 JVM PID/uptime verified; APM and JFR clocks within ±100ms.
Supporting data:
  70% of slow traces contain outbound DB spans of 500-900ms.
  JFR SocketRead on the same thread/stack/peer overlaps multiple spans.
  GCPhasePause in window max 35ms; safepoint logs show no
  corresponding long pauses; JavaMonitorEnter rose after pool queue grew.
Priority hypothesis:
  DB/downstream waits queued requests; monitor contention
  in a secondary component is a consequence of rising concurrency.
Insufficient evidence:
  Root cause of DB slowness (query, lock, storage, or network) not yet isolated.
Next verification:
  Correlate slow-query metrics, pool borrow times, and DB traces;
  apply controlled change and re-measure p99/error rate under same load.
```

This is an **interpretation template**, not results from a lab or real system. If 70% of traces fail to represent the cohort or clocks diverge, lower the confidence rating. A strong report shows **which time intervals, which requests, and which events actually connect**, instead of blaming the biggest event.

## 14. Self-assessment exercises

1. A 1,000 ms request overlaps an 80 ms GC pause; `jdk.GarbageCollection` duration is 1,400 ms. How many milliseconds of the request can you attribute to GC? List missing data.
2. Using the table in section 6, compute the union of monitor wait, safepoint, and I/O; explain why 860 ms is an invalid sum and why the 675 ms union is still not proven "causal cost."
3. Run `LatencySignalsLab` on JDK 21, open `latency-signals.jfr`, and locate `demo.Phase` markers alongside monitor/park/socket events on the same timeline. Try changing JFR thresholds and explain why counts change.
4. On a recording with GC activity, compare `jdk.GCPhasePause` against safepoint logs by UTC/uptime; identify which safepoint interval (if any) enclosed each GC pause.
5. Suppose 200 requests wait concurrently on sockets for 500 ms. Why can total `SocketRead` duration equal 100,000 ms while individual request latency does not add up that way?
6. Sketch a timeline with a **GC pause outside the symptom window** while downstream timeouts coincide with the symptom; explain how to rule out "GC is the primary cause."
7. Design an incident record containing `service`, `JDK`, `GC`, `JFR settings`, `timestamp uncertainty`, `trace`, `GC pause`, `safepoint op`, `lock owner`, `peer`, `hypothesis`, and verification test.

**Self-completion checklist:** defined latency at the right layer; normalized to UTC; checked JFR settings/thresholds; separated GC activity from pauses; separated GC vs. non-GC safepoints; interpreted monitor enter/wait/park properly; paired I/O with downstream traces; computed intersections/unions without double-counting; used a control window; stated conclusions with confidence and verification steps.

## 15. Primary references for Java 21

- [Oracle JDK 21 — Troubleshoot Performance Issues Using Flight Recorder: GC, synchronization, I/O, and thresholds](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 21 — `java`: Unified Logging, `-Xlog`, `gc` and `safepoint` tags, UTC decorators](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — `jcmd`: `JFR.start`, `JFR.check`, `JFR.dump`, `Thread.print`, and `VM.log`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr`: `summary`, `print`, `metadata`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `RecordedEvent` time interval API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle JDK 21 — `RecordingFile` streaming reader](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 21 — `Recording` and `Configuration` programmatic APIs](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)

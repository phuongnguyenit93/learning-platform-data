# 22.8 Investigating Virtual Thread Pinning in a Java 21 Environment

**Pinning** is an important diagnostic condition in Java 21 applications using virtual threads: a virtual thread performs a **blocking** operation yet **cannot unmount** from the platform thread carrying it (*carrier thread*). As a result, the carrier stays occupied while waiting instead of being reused by the JVM to run another virtual thread. If this happens **frequently and for long durations**, throughput/concurrency can drop sharply even though the application spawns many virtual threads.

Pinning **is not an exception**, does not automatically mean deadlock, and does not by itself prove the application is broken. A brief `synchronized` block updating a few variables in memory usually has negligible impact. The operational questions to answer are: **where is it blocking, for how long, how often, are carriers getting exhausted under heavy load, and is it actually causing current latency?**

This practice lab intentionally focuses on **JDK 21** (where virtual threads became a finalized feature in JEP 444); running the examples requires **JDK 21+**, while the `synchronized` pinning section reflects **JDK 21** behavior. **JDK 24 changes this behavior via JEP 491**; therefore the same example can behave very differently on JDK 24 and newer. Never take results from JDK 24/25/26 and conclude JDK 21 has no issue.

## 1. Virtual Threads, Platform Threads, and Carriers

A platform thread typically maps one-to-one with an OS thread. A virtual thread is a `java.lang.Thread` scheduled by the JVM across a smaller pool of platform threads called **carriers**. When a virtual thread performs a blocking operation that the JDK supports unmounting on, the runtime detaches the virtual thread from its carrier while waiting; the carrier returns to the scheduler to run other work.

```text
                JVM virtual-thread scheduler
                          │
           ┌──────────────┴──────────────┐
           ▼                             ▼
       Carrier #1                    Carrier #2
           │                             │
           ▼                             ▼
       Virtual A                     Virtual B
           │                             │
           │ blocking I/O able to unmount│
           ▼                             ▼
    A is parked/saved               B keeps running
           │
           └─ Carrier #1 is free to run Virtual C
```

What makes virtual threads effective for I/O-bound workloads is that **many tasks can wait concurrently** without tying up an OS thread each. Virtual threads **do not make the CPU run faster** and do not create extra CPU cores. A CPU-bound service or one bottlenecked on a DB connection pool can still stall even with thousands of virtual threads.

When pinning happens:

```text
Virtual A mounted on Carrier #1
          │
          ▼
Enters synchronized / native context (in JDK 21)
          │
          ▼
Performs a blocking operation
          │
          ▼
Cannot unmount from Carrier #1
          │
          ▼
Carrier #1 also waits, cannot run Virtual C
```

**Do not conflate two concepts**: a virtual thread is **mounted** during normal execution, and can become **pinned** due to runtime constraints preventing unmounting while waiting. Simply seeing a virtual thread on a carrier is not proof of pinning. What needs investigation is **blocking while pinned**.

## 2. Typical Pinning Cases in JDK 21

Oracle JDK 21 highlights two primary sources:

1. A virtual thread is executing **inside a `synchronized` block/method** and encounters an operation that can block it. For example: waiting on network/DB, `Thread.sleep()`, `BlockingQueue.take()`, or other VM-compatible waits.
2. A virtual thread is executing a **native method** or foreign function in contexts where the VM cannot detach the continuation from the carrier.

Points to remember:

- **Merely using `synchronized` is not automatically an incident**. If a critical section only manipulates in-memory state for a few microseconds without significant blocking, pinning cost may be negligible.
- **Pinning does not necessarily mean lock contention**. A virtual thread can **acquire the lock cleanly** and then sleep or wait on I/O inside the critical section. Waiting while holding the monitor is what holds the carrier. No second contending thread is required.
- **Waiting to enter a monitor** and **holding a monitor while waiting on I/O** are two different points. `jdk.JavaMonitorEnter` reports monitor contention; `jdk.VirtualThreadPinned` reports a virtual thread unable to leave its carrier while blocked. Do not substitute one event for the other.
- **Native/foreign frames** also restrict unmounting. Do not claim converting every `synchronized` to `ReentrantLock` solves pinning caused by native libraries or foreign calls.
- **Do not infer pinning from `WAITING` state**. A waiting virtual thread that successfully unmounted is normal behavior that saves OS threads.
- **Do not assume every block emits a JFR pinned event**. It depends on event settings, thresholds, recording scope, timing, JVM build, and the blocking mechanism.

### Quick Comparison Table

| Observation | More Accurate Interpretation | Evidence to Check |
| --- | --- | --- |
| `synchronized` updates a short counter, no wait | Usually not the first pinning optimization target. | Critical section latency, JFR pinned events, frequency. |
| `synchronized` holds monitor then calls `Thread.sleep(300)` | In JDK 21, classic example that holds the carrier while waiting. | `jdk.VirtualThreadPinned`, `-Djdk.tracePinnedThreads=...`. |
| `ReentrantLock.lock()` then `Thread.sleep(300)` | Lock API supports virtual-thread park/unmount on JDK 21; does not mean contended sections run in parallel. | JFR, concurrency throughput, lock wait. |
| A native method performs a long blocking call | May pin via native frame; changing outer monitor won't fix it. | JFR stack, native profiler/JNI/FFM call site, duration. |
| Many virtual threads `WAITING` while CPU/carriers work normally | Waiting threads may be unmounted properly. | Scheduler/concurrency, JFR, throughput, and pending work. |
| Small thread/DB pool forces requests to wait | External capacity limit may be the real bottleneck. | Connection acquire wait, queued requests, downstream latency. |
| Carrier busy on CPU for long periods | Likely CPU-bound code, not pinning. | CPU samples, profiling; does a JFR pinned event actually appear? |

## 3. Signs That Pinning Is Causing an Operational Problem

Never find one stack trace and declare a root cause. A stronger chain of evidence looks like:

- The service shows **lower-than-expected throughput**, growing request queues, and elevated p95/p99 latency at peak load.
- Numerous `jdk.VirtualThreadPinned` events appear with **long durations**, repeating at **the same method/call site** during the incident window.
- Stack traces show a blocking call **inside a monitor** or through a native frame.
- Available platform carriers are insufficient to serve runnable virtual threads during abnormal spikes, or stack samples show carriers stuck inside wait paths.
- After shrinking the critical section / removing blocking under the monitor, **pinning events drop** and throughput/p99 improve under **the same workload**.

A handful of 25–40 ms pinning events during startup may not be worth fixing. On the other hand, 200 ms events repeating **thousands of times per second** can cripple the scalability of a virtual-thread-per-task architecture, even when heap/GC show no obvious rise.

**There is no universal pinning-event-count threshold for every system.** Weigh event rate, duration, service level objectives (SLOs), concurrency, carrier count, and workload.

## 4. Version Rule: Do Not Apply Newer JDK Behavior to JDK 21

| Runtime | Behavior to Note | Tools and Interpretation |
| --- | --- | --- |
| **Java 17** | No finalized virtual threads in `java.lang.Thread` as in Java 21; examples like `Thread.ofVirtual()` will not compile on JDK 17. | This lab is **not for Java 17**. |
| **Java 21** | Virtual threads finalized. Blocking inside `synchronized` or native/foreign code can pin the carrier. | JFR `jdk.VirtualThreadPinned` enabled by default with **20 ms** threshold; `jdk.tracePinnedThreads` prints stacks. |
| **Java 22–23** | Mostly identical `synchronized` pinning rules as JDK 21; verify on your exact build. | Do not apply JDK 24+ results to these versions. |
| **Java 24 and newer** | JEP 491 lets virtual threads synchronize on monitors without legacy pinning; native/foreign frames and other limits can still apply. | `jdk.VirtualThreadPinned`, trace properties, and fields may differ; consult version-matched docs. |

**Key assertion:** in **JDK 21**, it is not true that "every `synchronized` is an anti-pattern"; the guidance is avoiding **long/frequent blocking while holding a monitor**. When planning an upgrade to JDK 24+, JEP 491 can shift remediation priorities, though code and native libraries still need verification.

Do not assume `VirtualThreadSchedulerMXBean` exists in Java 21 just because it appears in newer JDK docs: that interface was introduced in **JDK 24**. On JDK 21, rely on JFR, `jcmd Thread.dump_to_file`, existing JVM metrics, and trace properties; do not put JDK 24 MXBean code into Java 21 examples.

## 5. Primary Evidence: JFR `jdk.VirtualThreadPinned`

Java Flight Recorder (JFR) emits `jdk.VirtualThreadPinned` when a virtual thread blocks while pinned for longer than the configured threshold. Oracle JDK 21 documents **`jdk.VirtualThreadPinned` as enabled by default** with a **20 ms threshold**. This implies:

- Pinning/blocking **shorter than the threshold** may **not appear**.
- Missing the incident window, disabling the event, or raising the threshold loses visibility.
- Duration shows **blocking-while-pinned time** recorded by the event; it is **not** total CPU time and does not automatically equal request latency.
- Stack traces point to where the runtime detected pinned blocking; trace back to the **application frame** and surrounding `synchronized`/native construct.
- `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` are **disabled by default**; do not expect full lifecycles of every virtual thread in default recordings.

### Creating a JFR Recording on Java 21 for the Lab

When running the standalone program (created in section 7), enable recording from launch:

```bash
java -XX:StartFlightRecording=filename=sync-pinning.jfr,settings=default,dumponexit=true \
  -Djdk.tracePinnedThreads=short \
  -Djdk.virtualThreadScheduler.parallelism=2 \
  VirtualThreadPinningLab sync
```

The command uses `\` for line continuation in Bash/Linux/macOS. In PowerShell or CMD, run the equivalent on one line — **do not** copy trailing `\` as PowerShell syntax. The filename must be new or follow your environment's overwrite policy in a writable directory. `dumponexit=true` dumps on normal JVM exit; a complete file is not guaranteed on `SIGKILL`/`OOMKilled`.

`sync-pinning.jfr` is ready only after the recording finishes writing. Run:

```bash
jfr summary sync-pinning.jfr
jfr print --events jdk.VirtualThreadPinned sync-pinning.jfr
```

First, `jfr summary` verifies the file, time window, and event counts. Next, `jfr print` lists each `jdk.VirtualThreadPinned` in the file with its timestamp/duration/stack fields per JVM build. If the event type is absent or count is 0, never assume "zero pinning happened": check capture timing, JDK version, runtime mode, threshold, and workload.

### JFR on an Already Running JVM

If the service did not start with JFR, within a short approved window with attach permissions you can run:

```bash
jcmd -l
jcmd <pid> help JFR.start

jcmd <pid> JFR.start \
  name=vthread_diag \
  settings=default \
  duration=60s \
  filename=/var/diag/vthread-60s.jfr
```

Replace `<pid>` and path with real values. The directory must exist and be writable by the target JVM. Inside containers, the file is written on the target JVM's filesystem/mount, not automatically in the operator's terminal. If a suitable JFR recording is already active, **check `jcmd <pid> JFR.check` and dump that recording** instead of starting a redundant recording.

Read the file using the **JDK 21** `jfr` CLI or a compatible version. For large files, filter to relevant events instead of printing gigabytes with `jfr print`.

## 6. Second Tool: `-Djdk.tracePinnedThreads=full|short`

JDK 21 offers a dedicated system property to diagnose pinning:

```bash
# Print full frames when a virtual thread blocks while pinned
java -Djdk.tracePinnedThreads=full YourMainClass

# Print only notable frames
java -Djdk.tracePinnedThreads=short YourMainClass
```

This is syntax illustration where `YourMainClass` stands for your program's main class, **not a class provided in this article**. The complete runnable example follows in section 7.

- `full` prints detailed stack traces to `stderr`, highlighting native frames and monitor-holding frames.
- `short` trims down to problematic frames with less output.
- Trace output may depend on repeated stack occurrences, deduplication/filtering, JVM build, and runtime conditions; **do not treat log line counts as exact event counts**.
- On systems with heavy pinning, full traces can flood logs and burn CPU/I/O. Enable only in staging or on one controlled instance/window.
- This is a **JDK system property**, not a Java source API; place it before the main class name in the `java` command. Do not pass `-Djdk.tracePinnedThreads` as a program argument and expect the JDK to honor it.

Use **JFR as timestamped, duration-measured evidence**, and use the trace property to quickly spot call sites when reproducing under controlled conditions. Both sources complement each other without needing identical event counts.

## 7. Runnable Java 21 Practice: Simulating and Comparing

Goal: spawn **multiple virtual threads**, each calling `Thread.sleep(250)` inside its **own monitor** (`sync` mode) or its **own `ReentrantLock`** (`lock` mode). Separate monitors/locks are used to **avoid intentionally serializing all tasks on one mutex**; that way, the primary difference is whether carriers can be released while waiting.

**JVM optimizer note:** if a lock object exists only locally without escaping, the compiler can elide unobservable synchronization. This example stores monitors in a `static` array so the optimizer does not eliminate the lock; that is one reason to measure real events rather than just spotting `synchronized` in source.

Create `VirtualThreadPinningLab.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public final class VirtualThreadPinningLab {
    private static final int TASK_COUNT = 12;
    private static final Object[] MONITORS = new Object[TASK_COUNT];
    private static final ReentrantLock[] LOCKS =
            new ReentrantLock[TASK_COUNT];

    static {
        for (int i = 0; i < TASK_COUNT; i++) {
            MONITORS[i] = new Object();
            LOCKS[i] = new ReentrantLock();
        }
    }

    private static void perform(int id, String mode)
            throws InterruptedException {
        if ("sync".equals(mode)) {
            synchronized (MONITORS[id]) {
                Thread.sleep(250);
            }
        } else {
            ReentrantLock lock = LOCKS[id];
            lock.lock();
            try {
                Thread.sleep(250);
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                (!"sync".equals(args[0]) && !"lock".equals(args[0]))) {
            System.err.println("Usage: java VirtualThreadPinningLab sync|lock");
            System.exit(2);
        }

        String mode = args[0];
        AtomicInteger completed = new AtomicInteger();
        List<Future<Void>> futures = new ArrayList<>();

        long start = System.nanoTime();
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < TASK_COUNT; i++) {
                final int id = i;
                Callable<Void> job = () -> {
                    perform(id, mode);
                    completed.incrementAndGet();
                    return null;
                };
                futures.add(executor.submit(job));
            }

            for (Future<Void> f : futures) {
                f.get();
            }
        }
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        System.out.println("mode=" + mode +
                " completed=" + completed.get());
        System.out.println("elapsedMs=" + elapsedMs);
    }
}
```

Compile with **JDK 21**; `--enable-preview` is not needed:

```bash
java -version
javac -version
javac VirtualThreadPinningLab.java
```

Execute two **separate** runs on the same machine/JDK, fixing scheduler parallelism for clear observation:

```bash
# Case 1: waiting inside synchronized on JDK 21
java -Djdk.virtualThreadScheduler.parallelism=2 \
  -Djdk.tracePinnedThreads=short \
  -XX:StartFlightRecording=filename=sync-pinning.jfr,settings=default,dumponexit=true \
  VirtualThreadPinningLab sync

# Case 2: waiting inside ReentrantLock
java -Djdk.virtualThreadScheduler.parallelism=2 \
  -XX:StartFlightRecording=filename=lock-pinning.jfr,settings=default,dumponexit=true \
  VirtualThreadPinningLab lock
```

**Deterministic portion of stdout** when both runs succeed, excluding JFR/JVM agent lines and stderr stack traces:

```text
mode=sync completed=12
elapsedMs=<actual measured value>
```

```text
mode=lock completed=12
elapsedMs=<actual measured value>
```

`<actual measured value>` is a **placeholder describing dynamic output**, not literal stdout. Real runs print a non-negative integer (ms) depending on machine, JIT, GC, scheduler timing, and load. Never assert `sync` is always 1,500 ms or `lock` is always 250 ms. Both runs complete **12 successful tasks** per program logic; `sync` mode on JDK 21 can pin carriers while sleeping, whereas `ReentrantLock` normally allows unmounting during `Thread.sleep`.

Inspect both files:

```bash
jfr summary sync-pinning.jfr
jfr print --events jdk.VirtualThreadPinned sync-pinning.jfr

jfr summary lock-pinning.jfr
jfr print --events jdk.VirtualThreadPinned lock-pinning.jfr
```

**Expected qualitative result on HotSpot JDK 21:** the `sync` recording typically captures `jdk.VirtualThreadPinned` events with stacks in `perform(...)` and `Thread.sleep(...)`, while the `lock` recording typically shows few or none from that path. Exact event counts, durations, and elapsed times vary. If no events appear, check `jfr summary`, JFR settings, whether you are truly on JDK 21, actual source executed, and whether events exceeded 20 ms.

### Why Does Each Task Use Its Own Monitor?

If all 12 tasks shared a single monitor, they would be **serialized by mutual exclusion** even before considering pinning. Switching to **one shared `ReentrantLock`** would still serialize them, preventing tasks from sleeping concurrently while the lock is held. The demo gives each task its own lock/monitor to isolate **carrier pinning** from **lock contention**; in real applications, if shared data truly requires mutual exclusion under one mutex, you cannot drop exclusion just for throughput.

## 8. Java 21: Summarizing Pinned Events via API Instead of Counting Logs

To compare two recordings quantitatively, scan `jdk.VirtualThreadPinned` events via `jdk.jfr.consumer.RecordingFile`. The example streams events without loading the whole file into a `List` and without treating event duration as CPU time.

Create `PinnedEventSummary.java`:

```java
import java.nio.file.Path;
import java.util.Locale;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class PinnedEventSummary {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java PinnedEventSummary file.jfr");
            System.exit(2);
        }

        long count = 0;
        long totalNanos = 0;
        long maxNanos = 0;

        try (RecordingFile file =
                     new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!"jdk.VirtualThreadPinned".equals(
                        event.getEventType().getName())) {
                    continue;
                }

                long duration = event.getDuration().toNanos();
                count++;
                totalNanos += duration;
                maxNanos = Math.max(maxNanos, duration);
            }
        }

        System.out.printf(Locale.ROOT,
                "pinnedEvents=%d sumPinnedMs=%.2f maxPinnedMs=%.2f%n",
                count, totalNanos / 1_000_000.0,
                maxNanos / 1_000_000.0);
    }
}
```

Compile and run:

```bash
javac PinnedEventSummary.java
java PinnedEventSummary sync-pinning.jfr
java PinnedEventSummary lock-pinning.jfr
```

An output line looks like `pinnedEvents=8 sumPinnedMs=2012.34 maxPinnedMs=257.89`, though **this is purely illustrative**, not a guaranteed result for any specific machine. `sumPinnedMs` is **the sum of event durations**, and **can exceed wall-clock elapsed time** because multiple virtual threads can be pinned concurrently. It is **not CPU time or total milliseconds the JVM froze completely**. `maxPinnedMs` reports the longest event in the file, not request p99 latency.

Event counts can miss pinning shorter than the JFR threshold or operations outside the recording time window. When reporting, include filename, configuration, count, sum, max, workload type, and task/request counts — never compare two different workloads and claim an improvement.

## 9. Reading Stack Traces: Finding the Monitor Held Around Blocking Calls

Suppose JFR or stderr traces point to `VirtualThreadPinningLab.perform`, `Thread.sleep`, and a `synchronized` site. How to analyze:

1. Confirm **this is a virtual thread** and the event type is truly `jdk.VirtualThreadPinned`, not merely a CPU sample or `jdk.ThreadPark`.
2. Record **timestamp, duration, virtual thread name, and call site** shown by the tool; exact event fields may vary by JDK version.
3. Open the exact matching source/JAR version; locate the **critical section** wrapping the waiting call. Seeing a `synchronized` method alone is not enough: check what the method invokes while holding the lock.
4. Separate **blocking I/O** from **in-memory protected state**: can the monitor scope be narrowed without breaking data invariants?
5. If the stack enters JNI/native/FFM, verify the library and version; do not automatically blame application `synchronized` blocks for all pinning.
6. Examine **count/duration/load-window** distributions. A rare startup trace does not explain p99 latency.
7. After a change, compare both **pinning events** and **throughput/latency/error rate** under identical workload.

### Code Patterns to Look For

```java
// Risk in JDK 21: holding a monitor across I/O / long waits
synchronized (sessionLock) {
    response = remoteClient.fetch();  // may block on network
    cache.put(key, response);
}
```

This is an **illustrative snippet**, not a standalone runnable file. If `remoteClient.fetch()` blocks on the network for a long time, the virtual thread can stay pinned inside `synchronized`.

One refactoring option when semantics allow:

```java
// Do not hold the monitor during I/O.
Response response = remoteClient.fetch();

synchronized (sessionLock) {
    cache.put(key, response);
}
```

**Do not apply this mechanically.** Moving `fetch` outside the monitor can break check-then-act atomicity, cause duplicate requests, read stale state, or corrupt concurrent updates. For shared state, define business invariants, versioning/compare-and-set, in-lock re-checks, or proper synchronization and test thoroughly.

### Replacing `synchronized` with `ReentrantLock` When a Lock Must Span Blocking

If a workflow genuinely requires mutual exclusion across a blocking operation, Java 21 supports `java.util.concurrent.locks.ReentrantLock`:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

void updateSession() throws InterruptedException {
    lock.lock();
    try {
        Thread.sleep(200);  // illustrates a blocking section
        updateStateSafely();
    } finally {
        lock.unlock();
    }
}
```

This is a **fragment inside a class** with `updateStateSafely()` as a placeholder business method, **not a self-compiling program**. `ReentrantLock` works nicely with virtual-thread parking/unmounting during waits in JDK 21; however, **if many tasks contend for the same lock**, they still wait on each other. Holding a lock across slow I/O increases lock hold time; swapping lock APIs does not remove serialization imposed by concurrency design.

Before refactoring, check `wait()/notify()/notifyAll()`, reentrancy, exception paths, interrupt handling, and lock ordering. Never replace `synchronized` with `ReentrantLock` while leaving code that relies incompatibly on intrinsic monitor semantics.

## 10. How Do Thread Dumps on JDK 21 Support Investigation?

JDK 21 provides `jcmd Thread.dump_to_file` to export a thread dump containing **platform threads and virtual threads**, showing many stacks at a single instant. This is a **complement** to JFR: a thread dump does not reveal all pinning that occurred before the snapshot.

```bash
# Find the right JVM PID
jcmd -l

# Inspect command syntax and options on the running JVM
jcmd <pid> help Thread.dump_to_file

# Snapshot at a suspect moment, JSON for automated analysis
jcmd <pid> Thread.dump_to_file -format=json /var/diag/vthreads.json
```

The file path lives in the **target JVM's** filesystem, requiring write permission and disk space. Per Java 21 documentation, virtual thread dumps show thread/task structure yet **omit some object addresses, lock/JNI/heap statistics** found in traditional dumps. Therefore, never use a JSON dump as "exact proof of how many carriers were pinned over a full minute"; you still need JFR events and metrics.

In apps spawning huge numbers of virtual threads, thread dumps can become massive and costly. Never run them continuously in production just because JSON output is convenient. Note that `jcmd <pid> Thread.print -l` produces a traditional thread dump with different scope and does not replace `Thread.dump_to_file` for virtual threads on JDK 21.

### When Should You Use a Dump?

- JFR flags a suspect call site, yet you still want to see **live stacks during high load**.
- Requests are hanging and you need to see what **many virtual threads** are currently waiting on.
- Scheduler queues/concurrency look abnormal and you want a point-in-time view of the application.

If you only need the pinning duration/call-site distribution over 60 seconds, a **JFR recording** is usually better than a single dump because it captures **timestamped events over time**.

## 11. Distinguishing Pinning from Saturation and Other Bottlenecks

High p99 in an app using virtual threads does not automatically mean pinning. Place three metric groups side by side:

| Group | What to Check | Meaning |
| --- | --- | --- |
| **Direct pinning** | `jdk.VirtualThreadPinned` count/duration/top stacks, trace property | Is there evidence carriers are held because threads blocked while pinned? |
| **Throughput/latency** | Requests/s, p50/p95/p99, errors/timeouts, queue wait, completion rate | Is pinning actually impacting user outcomes? |
| **Other capacity limits** | CPU usage, DB pool pending/active, HTTP connection limits, socket waits, locks, GC pauses, downstream SLAs | Is another bottleneck stalling all virtual threads? |

Consider a DB-backed service: 50,000 virtual threads may run against a DB pool capped at 50 connections. If tasks waiting for a connection **unmount cleanly**, carriers are not necessarily pinned; throughput is still bounded by the DB. Driving pinning events to 0 will not magically make the DB serve 5,000 concurrent queries. Conversely, if a network call sits **inside `synchronized`** on JDK 21 and pins carriers, adding more virtual threads may fail to raise effective concurrency.

**Carrier count is not virtual thread count.** A scheduler with just a few platform threads can still juggle massive numbers of waiting virtual threads thanks to unmounting. Never treat `Thread.activeCount()` or OS thread count as active virtual requests. Tie performance indicators to business operations, scheduler load, and pinning events.

### Are Scheduler Parameters a "Fix"?

JDK 21 includes implementation-specific properties such as `jdk.virtualThreadScheduler.parallelism` affecting the scheduler's target parallelism; in the lab we set `2` to make contention easy to observe. This is **not a recommendation to set `2` in production**. Raising scheduler parallelism can shift symptoms, yet it does not fix blocking-in-monitor code and increases OS thread count plus memory/CPU scheduling overhead. **Do not tune the scheduler before confirming the root cause.**

If you are creating custom "cached virtual thread pools" or trying to reuse virtual threads like a platform thread pool, revisit the design. Virtual threads are normally **one virtual thread per task**; use a `Semaphore` or proper concurrency limit to protect a downstream resource instead of treating virtual threads as scarce OS threads.

## 12. Walkthrough of a Hypothetical Incident Analysis

**Scenario:** after migrating request handlers to `Executors.newVirtualThreadPerTaskExecutor()` on JDK 21, throughput fails to scale as expected and p99 rises during peak hours.

### Minimum Data Collection

1. Check `java -version` on **the running process**, not only your dev SDK; verify Java 21, runtime vendor, and image.
2. Gather request rate, p95/p99, errors, CPU, active DB connections, queue wait, and GC time during the incident window.
3. Check active recordings (`jcmd <pid> JFR.check`). If none exists, consider a brief `default` JFR recording after verifying file/disk/permissions.
4. Run `jfr summary file.jfr` then `jfr print --events jdk.VirtualThreadPinned file.jfr`.
5. Group events by **stack/call site**, count occurrences, and compute duration stats; record window and sample counts.
6. Once reproduced in staging, run `-Djdk.tracePinnedThreads=short` and inspect monitor-holding/native frames.
7. Capture a virtual-thread dump only when a live snapshot of stacks is needed beyond JFR data.
8. Cross-check against other limits (DB pool/CPU/I/O) and test a minimal fix under matched load.

### Sample Data Table to Interpret

The figures below are **hypothetical**, not actual JFR output:

| 1-Minute Window | Requests/s | p99 response | `VirtualThreadPinned` events | p95 pinned duration | DB pool pending |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before refactor | 500 | 820 ms | 2,800 | 240 ms | 0 |
| After shrinking critical section | 730 | 310 ms | 35 | 25 ms | 0 |

Given matching workload/hardware and no other major changes, this strongly suggests fixing blocking-under-monitor reduced carrier pinning and improved throughput/tail latency. Yet two table rows alone do not prove absolute causation; verify CPU, GC, deployments, request mix, errors/rejections, and repeat tests.

If instead `p99` barely changes even as pinned events drop, keep investigating **DB/network bottlenecks, serialization, queue wait, lock contention, or CPU**. The goal is improving the service, not merely polishing event counts.

### Preserving Required Evidence

A report might record:

```text
Runtime: OpenJDK 21.x, one JVM / one pod
Window: 14:00-14:01 UTC (example)
JFR settings: default; pinned threshold = 20 ms
Pinned events: count, durations, top application callsites
JVM flags: scheduler parallelism, relevant startup flags
Traffic: request rate, p95/p99 latency, errors, queue depth
Hypothesis: blocking I/O inside synchronized method retains carriers
Fix/test: shorten monitor scope or use ReentrantLock where safe
Validation: same workload, JFR recording and latency comparison
Limitations: JFR threshold; unrecorded short events; version-specific behavior
```

Never attach full HPROF/JFR/stack traces containing customer data to public tickets. Record checksums, storage owner, retention, and access controls as required.

## 13. Common Reasoning Fallacies

- **"A `WAITING` virtual thread is pinned."** False: it may have unmounted cleanly while its carrier serves other threads.
- **"Every `synchronized` must be replaced."** False: prioritize **long or frequent blocking while holding a monitor** on Java 21.
- **"Pinning causes deadlock."** Pinning is not automatically deadlock; it reduces concurrency, whereas deadlock is a cyclic lock dependency.
- **"No lock contention means no pinning."** False: a single thread can hold a monitor and block inside its critical section.
- **"`Thread.sleep()` always pins."** False: outside a pinning context, virtual threads can unmount; inspect frames and runtime version.
- **"`jdk.VirtualThreadPinned` counts every pinning event."** False: the default 20 ms threshold, settings, and capture window determine what gets recorded.
- **"JFR pinned event duration is CPU time."** False: it is the blocking-while-pinned duration recorded for that event.
- **"Sum of pinned duration = 8 seconds means the app froze for 8 seconds."** False: events can overlap in time across multiple carriers.
- **"Using `ReentrantLock` lets all tasks run simultaneously."** False: mutual exclusion still blocks tasks contending on the same lock.
- **"Replacing every `synchronized` with `ReentrantLock` preserves exact semantics."** False: `Object.wait/notify`, lock ordering, exceptions, reentrancy, and interruption policies must all be reviewed.
- **"Spawning more virtual threads fixes carrier pinning."** False: it cannot create free carriers if existing carriers are tied up by long-lived blocking sections.
- **"Raising scheduler parallelism means the root cause is fixed."** False: it may mask symptoms while adding OS thread overhead.
- **"`Thread.dump_to_file` contains everything HPROF or traditional lock dumps contain."** False: virtual-thread dumps have their own scope and are point-in-time snapshots.
- **"One stderr trace equals one JFR event."** False: trace printing may be rate-limited/deduplicated; use JFR over time to quantify.
- **"Ran the demo on JDK 24 and saw no pinning, so Java 21 has no problem."** False: JEP 491 changed `synchronized` behavior starting in JDK 24.
- **"JDK 21 has every virtual-thread scheduler MXBean seen on JDK 26."** False: check `@since` in the API docs, especially `VirtualThreadSchedulerMXBean` added in JDK 24.
- **"Seeing pinning events alone proves SLA degradation."** Insufficient: correlate with request latency, throughput, and other bottlenecks.

## 14. Java 21 Operational Checklist

**Verify context:**

- [ ] Exact **JDK 21** on the running JVM; `Thread.ofVirtual()` and `Executors.newVirtualThreadPerTaskExecutor()` are genuinely used.
- [ ] Workload type (I/O-bound vs. CPU-bound), request rate, downstream concurrency, and SLOs are known.
- [ ] JFR recording covers the exact incident window, with `jdk.VirtualThreadPinned` enabled and suitable threshold.
- [ ] Platform thread count charts are not mistaken for virtual thread counts.

**Collect evidence:**

- [ ] Start with existing metrics/logs/JFR recordings to minimize production impact.
- [ ] Run `jfr summary` then `jfr print --events jdk.VirtualThreadPinned`, recording timestamps/durations/stacks.
- [ ] When reproducing, enable `-Djdk.tracePinnedThreads=short` or `full` in controlled staging.
- [ ] Use `Thread.dump_to_file` when a thread snapshot is needed, respecting scope limits and overhead.
- [ ] Do not drop JFR thresholds to 0 across all instances before evaluating event rate, disk, and overhead.

**Analyze and remediate:**

- [ ] Pinpoint the call site actually **blocked while pinned**, separating monitors, native/foreign frames, and DB pool limits.
- [ ] Prefer moving slow blocking I/O outside `synchronized` when invariants stay intact; if holding a lock is mandatory, consider `ReentrantLock` and test semantics.
- [ ] Do not mechanically rewrite synchronization strategies or scheduler flags across the board.
- [ ] Evaluate before/after on the same JDK 21 build, same workload/hardware, and same JFR settings.
- [ ] Review **throughput, p99, errors, lock waits, DB pending, and pinning event metrics** together.
- [ ] If upgrading to JDK 24+, review JEP 491 and re-measure rather than carrying version-specific conclusions forward unchanged.

**Conclusion:** In **Java 21**, the pinning issue to investigate is **blocking when a virtual thread cannot unmount from its carrier**. Use `jdk.VirtualThreadPinned` (default **20 ms** threshold) to measure when, how long, and at which call site it happens, paired with `-Djdk.tracePinnedThreads` to inspect stacks and throughput/latency metrics to assess real impact. Fix **the code holding a monitor across waits** or adopt an appropriate synchronization model while preserving invariants — never bulk-replace `synchronized` just because it exists. Finally, always verify **the exact JDK version**, as JDK 24 significantly changes how `synchronized` interacts with virtual threads.

### Official References

- [Oracle JDK 21 — Virtual Threads: Scheduling, Pinning, JFR, and Thread Dumps](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads (final in JDK 21)](https://openjdk.org/jeps/444)
- [Oracle JDK 21 — `jcmd` diagnostic commands, `JFR.start`, and `Thread.dump_to_file`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr`: `summary` and `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning, JDK 24](https://openjdk.org/jeps/491)
- [Oracle JDK 21 — `Executors.newVirtualThreadPerTaskExecutor()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html#newVirtualThreadPerTaskExecutor())
- [Oracle JDK 21 — `RecordingFile` JFR consumer API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
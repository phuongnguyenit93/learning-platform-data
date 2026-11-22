# Diagnosing Virtual Threads with Thread Dumps and Java Flight Recorder (JFR)

Virtual Threads are lightweight threads managed by the Java runtime, standardized in **Java 21** (JEP 444). They allow the *thread-per-task* model to scale well when tasks frequently wait on I/O. However, “having a lot of virtual threads” does not by itself prove that an application is running efficiently: tasks can still bottleneck on finite resources, locks, wait cycles, CPU, external systems, or execution sections where a virtual thread cannot yield its carrier.

This guide explains how to **diagnose Virtual Threads behavior in Java in general** using two tools built into the JDK:

- **Thread dump:** a snapshot of existing stacks at a point in time, answering “where are the threads, what are they waiting on, and which stacks repeat?”
- **Java Flight Recorder (JFR):** a stream of events and metrics over time, answering “when do anomalies occur, how long do they last, how frequent are they, and is there pinning or resource contention?”

These two tools complement each other. A single dump is usually not enough to conclude a performance root cause; a JFR recording without the right events enabled or not captured at the right time can also miss key evidence.

## 1. The Model to Understand Before Reading Traces

A **virtual thread** is a real `Thread` object in the Java API: it has a name, a stack, a state, interruption support, and a stack trace. Unlike platform threads that are tied 1:1 to OS threads, a virtual thread is **mounted** by the JVM onto a platform thread called a **carrier** when it needs to run. When it encounters a waiting operation where the JVM supports unmounting, the virtual thread can leave the carrier and yield it to run another virtual thread.

For example, a virtual thread in `CountDownLatch.await()` or waiting on network I/O does not necessarily occupy an OS thread for the entire wait duration. This does not mean waiting is free: tens of thousands of tasks waiting on a small connection pool still cause latency and backlog.

Distinguish four concepts:

| Concept | Diagnostic Meaning |
|---|---|
| *Waiting/parked* | The thread is waiting for a condition or result; may be normal behavior—inspect the stack and duration |
| *Blocked on monitor/lock* | The thread has not acquired the lock; measure lock contention and identify long-held critical sections |
| *Carrier pinning* | The virtual thread encounters a situation where it cannot unmount, keeping the carrier occupied for a period of time |
| *Starvation / saturation* | Tasks cannot make timely progress due to CPU, scheduler, or a finite resource; requires evidence beyond thread state names |

**A thread in the `WAITING` state is not automatically deadlocked**, and a `RUNNABLE` virtual thread is not automatically consuming CPU. States are JVM-level snapshots and must be correlated with stacks, timing metrics, and actual processing throughput.

### Differences Across JDK Versions: Especially Important for Pinning

- **Java 21–23:** waiting or blocking inside a `synchronized` block/method can keep a virtual thread pinned to its carrier. Therefore, a long I/O operation inside a monitor is a valid pinning suspect.
- **From Java 24 (JEP 491):** the JVM improved `synchronized` so that virtual threads can unmount in scenarios that previously caused monitor pinning. Do not conclude “has synchronized ⇒ pinning” when running on JDK 24+.
- **Newer versions still have other pinning cases**, typically native/foreign calls or VM frames that cannot yield the carrier. Always rely on JFR and stacks from the **exact JDK version being run**.

Prolonged pinning can limit scalability, but it does not mean the program is functionally incorrect. A brief, rare event may not be a priority issue.

## 2. When to Use Thread Dumps vs. JFR?

| Question | Thread dump | JFR |
|---|---|---|
| Which stacks are waiting right now? | Very well suited | Can assist via events/stack sampling |
| Are many virtual threads waiting on the same semaphore, latch, or I/O? | Good for finding similar stacks | Good for checking progression and duration |
| Does the issue happen for only a few seconds and disappear? | Easy to miss | Well suited if recorded at the right time |
| Is prolonged or repeated pinning actually occurring? | Only suggestive | The `jdk.VirtualThreadPinned` event is more direct evidence |
| High CPU, allocation, GC, or prolonged lock contention? | Partial | JFR has corresponding events/sampling |
| Concluding “deadlock”? | Requires multiple samples and lock info; newer dumps may omit some details | Requires correlating additional lock and progress data |

**Typical workflow:** identify symptoms and time window → capture multiple dumps spaced apart → record JFR during load → correlate stacks/events/resources → verify the hypothesis with a fix or repeated measurement.

## 3. Preparing the Environment and Identifying the Right JVM

Minimum requirements:

- **JDK 21+** for official Virtual Threads support; the JDK used to run the app and the `jcmd`/`jfr` tools should be compatible with the target JVM.
- Appropriate permissions to attach to the Java process. In containers, run commands in an environment that can see the JVM process and has the corresponding attach permissions.
- Sufficient disk space for dump/JFR files; with hundreds of thousands of virtual threads, a thread dump can be large. Collect selectively rather than looping continuously without limits.

List processes visible to `jcmd`:

```bash
jcmd -l
```

Select the **PID of the target application JVM**, then check which diagnostics that JVM supports:

```bash
jcmd <PID> help
jcmd <PID> help Thread.dump_to_file
jcmd <PID> help JFR.start
```

In the commands in this guide, `<PID>` is a placeholder to be replaced with the **actual PID number**, without typing the angle brackets. Parameter syntax and recorded details may improve across JDK versions, so `jcmd <PID> help ...` is the direct source of truth for the running JVM.

## 4. Capturing Thread Dumps with Virtual Threads

Use the `Thread.dump_to_file` command, designed to observe virtual threads as well:

```bash
jcmd <PID> Thread.dump_to_file vt-dump.txt
jcmd <PID> Thread.dump_to_file -format=json vt-dump.json
```

- Omitting the format uses the default text format of the running JDK.
- `-format=json` is suitable when analyzing with tools. The JSON shape/schema may vary across JDK versions; do not build a parser against a single hardcoded format example.
- The file path is resolved **within the target JVM process's environment**. Use an absolute path when working across containers, services, or different working directories to avoid saving to an unexpected location.
- Save **2–3 dumps a few seconds apart** when investigating prolonged issues, then compare similar stacks. Repeated patterns are more valuable than a single snapshot.

You can also use:

```bash
jcmd <PID> Thread.print -l
```

as a supplementary source for platform threads and lock information, but **do not rely solely on `Thread.print` to draw conclusions about all virtual threads**. Unmounted virtual threads may not appear completely in traditional dumps; the level of lock/monitor information in `Thread.dump_to_file` also depends on the JDK version (especially older releases).

### What to Read in a Dump?

In priority order:

1. **Common thread names/stacks:** look for virtual threads waiting together at a `CountDownLatch.await`, `Semaphore.acquire`, socket operation, `Future.get`, or `LockSupport.park`. A stack duplicated in large numbers may be where backlog is accumulating.
2. **Actual wait points:** inspect both the top frames (where it is waiting) and the application frames below (why the task reached there). Distinguish runtime library frames from application call sites.
3. **Changes across snapshots:** many threads remaining at the exact same point across consecutive dumps is a signal worth investigating, though it still does not prove a deadlock.
4. **Carriers and platform threads:** if a carrier is CPU-busy or blocked for too long, correlate with JFR to find what is holding it. Do not confuse the carrier's name with the logical work identity of the virtual thread.
5. **Dependent resources:** if many virtual threads are waiting on a `Semaphore` or pool, check pool limits, number of active tasks, wait times, and resource release rates.

**There is no universal “optimal maximum number of virtual threads” for all applications.** You must look at throughput, p95/p99 latency, queued requests, CPU usage, finite connection counts, and timeout frequency.

## 5. Java 21+ Hands-on Lab: Creating Easily Observable Virtual Threads

Save as **`VirtualThreadDiagnosticsDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualThreadDiagnosticsDemo {
    public static void main(String[] args) throws InterruptedException {
        int count = 3;
        CountDownLatch allWaiting = new CountDownLatch(count);
        CountDownLatch release = new CountDownLatch(1);

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < count; i++) {
                final int id = i;
                executor.submit(() -> {
                    Thread.currentThread().setName("diag-vt-" + id);
                    allWaiting.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            allWaiting.await();
            System.out.println("Virtual threads waiting: " + count);
            System.out.println("PID: " + ProcessHandle.current().pid());

            try {
                // Keep the process alive to capture thread dumps and JFR from another terminal.
                Thread.sleep(60_000);
            } finally {
                release.countDown();
            }
        }

        System.out.println("Finished");
    }
}
```

Compile and run in one terminal:

```bash
javac VirtualThreadDiagnosticsDemo.java
java VirtualThreadDiagnosticsDemo
```

**Example stdout structure** (PID differs on each run):

```text
Virtual threads waiting: 3
PID: <actual-PID>
Finished
```

The `Finished` line is only printed **after about 60 seconds**, once the program releases the `CountDownLatch` and the tasks complete. From another terminal, **while the program is sleeping**, substitute the printed PID into:

```bash
jcmd <PID> Thread.dump_to_file -format=json vt-lab.json
jcmd <PID> Thread.dump_to_file vt-lab.txt
```

Open the file and search for `diag-vt-0`, `diag-vt-1`, `diag-vt-2` along with the stack waiting on `CountDownLatch.await` (other internal frames may depend on the JDK). These three virtual threads are intentionally waiting for a signal: **this is neither a deadlock nor pinning**.

The example uses `Executors.newVirtualThreadPerTaskExecutor()`, **not a fixed pool of virtual threads**: the executor allocates one virtual thread per task. Limiting concurrent running tasks should be done according to actual resource constraints (such as a semaphore for connections or external services), not by replacing virtual threads with a small fixed pool to hide task backlogs.

### If Threads Are Not Found in the Dump

Check these first:

- Was the dump captured **before the program exited**? Once a task finishes, its thread disappears.
- Did you use the right PID, right JVM, and right output file?
- Did you use `Thread.dump_to_file` or only `Thread.print`?
- Did you search by thread name and stack instead of only searching for `RUNNABLE`/`WAITING` states?
- Was the dump truncated by the viewer? Use a tool that opens the full file or an appropriate parser.

## 6. Capturing Java Flight Recorder on a Running JVM

JFR is an event/sampling recorder built into HotSpot/JDK that can collect data on scheduling, blocking, CPU, allocation, GC, monitor contention, and virtual-thread-specific events. JFR typically has low overhead with appropriate settings, but **not every event is enabled by default**, and recordings that are too long or overly detailed can consume resources.

During the 60 seconds the demo program is alive, you can run:

```bash
jcmd <PID> JFR.start name=vt-diagnostics settings=profile duration=20s filename=vt-diagnostics.jfr
jcmd <PID> JFR.check
```

After the recording completes its duration and the file appears, inspect the summary and events:

```bash
jfr summary vt-diagnostics.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
```

If you start a recording **without a fixed duration**, manage its lifecycle explicitly, for example:

```bash
jcmd <PID> JFR.start name=vt-manual settings=default
jcmd <PID> JFR.dump name=vt-manual filename=vt-manual.jfr
jcmd <PID> JFR.stop name=vt-manual
```

`JFR.dump` writes a snapshot of the data at that point in time; `JFR.stop` ends the recording. If `duration=20s` is used, the recording stops automatically after the specified duration. With `JFR.start`, the `filename` is created by the target JVM process; use an absolute path to avoid working directory confusion. `jfr summary`/`jfr print` are executed on a machine with the JFR file and compatible JDK tools.

**Do not expect the Section 5 demo to generate `VirtualThreadPinned` on its own.** It simply waits on `CountDownLatch` properly; the JFR file may contain zero pinning events, which is a valid result.

### Key Events for Virtual Threads

| JFR Event | When Is It Useful? | Notes |
|---|---|---|
| `jdk.VirtualThreadPinned` | Suspecting a virtual thread held its carrier while blocking | Usually enabled by default with a 20 ms threshold in standard JFR configs; trigger conditions vary by JDK |
| `jdk.VirtualThreadSubmitFailed` | Suspecting virtual thread start/unpark hit resource issues | Usually enabled by default; check cause and timestamp |
| `jdk.VirtualThreadStart` | Need to know virtual thread creation time and creation rate | **Disabled by default**; enable selectively when needed |
| `jdk.VirtualThreadEnd` | Need to know virtual thread lifecycle and completion rate | **Disabled by default**; enable selectively when needed |
| `jdk.JavaMonitorEnter` / `jdk.JavaMonitorWait` | Suspecting monitor contention or time spent waiting on a monitor | Check configuration and threshold; do not equate monitor contention with pinning |
| `jdk.ThreadPark` | Suspecting prolonged wait/park durations | Can help locate waiting operations; verify the event and threshold are enabled in the recording |

A command to print the four Virtual Threads-specific events (produces output only if those events were actually recorded):

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
```

The absence of `VirtualThreadStart` and `VirtualThreadEnd` **does not prove there were no virtual threads**: these two events are usually disabled by default. To measure thread creation/termination, explicitly enable them via JDK Mission Control, a custom JFR configuration file, or the `jdk.jfr.Recording` API, while considering overhead when thread counts are very high.

### How to Read a Pinning Event

When you see `jdk.VirtualThreadPinned`, check:

1. **Start time + duration:** does it fall within the latency spike window, and how long did each occurrence last?
2. **Stack trace:** which application frame led to the blocking operation? Do not stop at VM/`LockSupport` frames.
3. **Event thread and carrier** (if recorded by runtime/JFR): identify the virtual thread and carrier involved.
4. **Frequency and total impact:** thousands of pinning events on a hot path are very different from a single brief event during startup.
5. **JDK version:** on Java 21–23, check whether blocking occurred inside `synchronized`; on Java 24+, investigate the remaining pinning causes and the exact stack/event details recorded.

JFR records **events exceeding a threshold**, which does not mean every blocking operation must appear. If event frequency is 0, check the configuration, threshold, recording duration, event availability, and JVM version before ruling out a hypothesis.

## 7. Distinguishing Normal Waiting, Lock Contention, Deadlock, and Pinning

### Scenario A — Thousands of Virtual Threads Waiting on a Resource

**Symptom:** latency increases and thread dumps repeatedly show `Semaphore.acquire` or acquiring a connection from a pool.

**Reasonable hypothesis:** concurrent tasks exceed resource capacity; wait time at the semaphore/pool is longer than the actual work execution time.

**How to verify:** capture 2–3 dumps during the bottleneck; measure active connections, queue depth, timeouts, and query/remote I/O execution time; record JFR to observe wait intervals and CPU. Counting many virtual threads in `WAITING` is not enough to conclude a scheduler bug or JFR pinning.

**Remediation:** bound concurrency according to actual resources, use explicit timeouts/cancellation, reduce connection hold time, or optimize the downstream system. Reducing carrier count does not increase the actual number of connections.

### Scenario B — Pinning on Java 21–23

**Symptom:** throughput drops sharply when many tasks perform blocking I/O inside `synchronized`; JFR shows many `jdk.VirtualThreadPinned` events with corresponding stacks.

**Hypothesis:** virtual threads are held on carriers during blocking, reducing the number of carriers available to run other tasks.

**Conditional remediation:** if the lock is only used to protect brief state updates, move the long I/O out of the `synchronized` block if correctness is preserved; or consider `ReentrantLock` on blocking hot paths, always calling `unlock()` in `finally`. Avoid mechanically converting **all** `synchronized` blocks to `ReentrantLock`. Where possible, benchmark after upgrading to JDK 24+ (JEP 491) since monitor behavior has changed.

Illustrative pattern (not a standalone program):

```java
// Risk on JDK 21–23 if remoteCall() blocks for a long time.
synchronized (guard) {
    remoteCall();
}

// Solution is only valid when calling remoteCall() does not require holding the monitor:
// re-check data invariants before applying.
synchronized (guard) {
    snapshot = buildSnapshot();
}
remoteCallWith(snapshot);
```

Do not move an operation out of a monitor when data synchronization requirements genuinely demand protection across the entire transaction; correctness matters more than a speculative optimization.

### Scenario C — Deadlock or Logical Wait Cycle

**Symptom:** multiple stacks remain unchanged at `Future.get`, `CountDownLatch.await`, or monitors across snapshots; tasks never complete, and release signals never occur.

**Hypothesis:** there is a dependency cycle, a stage is waiting on a result it is supposed to produce itself, or a lock is held by a task that is also waiting.

**Verification:** reconstruct the **who-is-waiting-for-whom** graph from code and stacks; correlate submission, completion, and timeout timestamps; use additional monitor/lock details if available. Do not infer deadlock from a single `WAITING` stack alone; many tasks may legitimately be waiting on a latch that has not yet been released.

**Remediation:** break dependency cycles, ensure release signals are in `finally`, and add deadlines and interrupt/cancellation propagation where appropriate by contract. Virtual Threads make waiting cheaper in terms of OS threads, **they do not automatically resolve logical deadlocks**.

### Scenario D — High CPU, No Pinning Observed

**Symptom:** CPU is near saturation, latency increases; JFR sampling shows many computation frames; `VirtualThreadPinned` is not prominent.

**Hypothesis:** CPU-bound work is exhausting compute resources, or GC/allocation has increased. Virtual threads do not create extra CPU capacity and do not make CPU-heavy calculations run faster just by switching thread types.

**Remediation:** use JFR CPU/profiling, analyze hot methods, allocation, and GC; isolate or bound CPU-heavy tasks; measure impact after changes.

## 8. Deeper JFR Analysis Using the Java API

Beyond `jfr summary` and `jfr print`, you can read JFR files using the `jdk.jfr.consumer.RecordingFile` API on JDKs that include the `jdk.jfr` module. The following complete example counts pinning events **recorded in the file**, without guessing active thread counts.

Save as **`CountPinnedEvents.java`**:

```java
import java.io.IOException;
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class CountPinnedEvents {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java CountPinnedEvents <file.jfr>");
            return;
        }

        long total = 0;
        try (RecordingFile recording =
                     new RecordingFile(Path.of(args[0]))) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                if ("jdk.VirtualThreadPinned"
                        .equals(event.getEventType().getName())) {
                    total++;
                }
            }
        }

        System.out.println("Recorded pinned events: " + total);
    }
}
```

Run with JDK 21+:

```bash
javac CountPinnedEvents.java
java CountPinnedEvents vt-diagnostics.jfr
```

For example, if the file contains no pinning events, stdout is:

```text
Recorded pinned events: 0
```

The count may differ on real files; it only counts JFR events **that occurred and were enabled/recorded**, not every monitor hold or every I/O operation. When you need to analyze multiple event types, you can open the file with **JDK Mission Control (JMC)** to filter by event type, duration, stack trace, and correlate with CPU/lock/GC.

## 9. Step-by-Step Diagnostic Workflow in Production

**Step 1 — Record symptoms and the time window.** For example, “p99 rose from 100 ms to 3 s during 15:20–15:25,” with timestamps, throughput, CPU, heap/GC, timeouts, queued tasks, and connection limits. Without baseline metrics, it is easy to mistake normal wait times for errors.

**Step 2 — Identify PID, JVM version, and diagnostic configuration.** Use `java -version` against the actual runtime, `jcmd -l`, and `jcmd <PID> help`. Note clearly whether it is JDK 21–23 or 24+ when suspecting pinning.

**Step 3 — Capture a series of thread dumps.** Use `Thread.dump_to_file` (preferring both JSON and text if needed); look for similar stack groups and observe changes over time. Under very high load, consider dump size and capture overhead.

**Step 4 — Capture JFR covering the problem window.** Use `settings=profile` for a short, controlled duration. Inspect `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed`, CPU samples, and relevant monitor/park/GC events. Enable start/end events if you need virtual thread lifecycle analysis.

**Step 5 — Correlate three layers of evidence.** (a) stacks at wait points, (b) events/durations/frequencies over time, and (c) resource metrics such as CPU, connection pools, queues, and latency. A root-cause conclusion is only strong when it explains both the observed symptoms and the metric changes.

**Step 6 — Verify the fix.** Address the actual bottleneck: monitors on older JDKs, undersized pools, missing timeouts, blocking with wait cycles, or CPU-heavy sections. Use the same measurement approach under the same load to compare before and after; avoid “optimizing” the entire codebase just because you see many virtual threads.

## 10. Common Diagnostic Pitfalls

1. **Using `Thread.print` and assuming you see all virtual threads.** For virtual threads, you need `Thread.dump_to_file`; use traditional dumps as supplementary evidence.
2. **Treating `WAITING` as deadlock.** You must check which task will release the condition, wait durations, and a series of dumps.
3. **Seeing `synchronized` on JDK 24+ and concluding pinning.** JEP 491 changed monitor behavior; check the exact JDK version and actual JFR events.
4. **Seeing zero `jdk.VirtualThreadPinned` events and concluding “no problem.”** Events have thresholds, recording windows, and JDK-dependent conditions.
5. **Seeing no `VirtualThreadStart/End` events and concluding no virtual threads exist.** These two events are typically disabled by default.
6. **Counting virtual threads instead of measuring resources.** Tens of thousands of legitimately sleeping threads can be far less severe than a few hundred tasks waiting on an exhausted pool.
7. **Blaming the scheduler for every slowdown.** CPU, GC, file descriptors, network, and upstream/downstream timeouts remain real limits.
8. **Capturing too late or taking only a single dump.** Short incidents may have already passed; time the recording properly and compare multiple samples.
9. **Writing a file and not finding it on the local machine.** `jcmd` instructs the target JVM to write the file: the working directory and write permissions belong to that JVM's environment.
10. **Accidentally sharing dumps/JFR files publicly.** Stack traces, class names, JVM arguments, and strings inside recordings may contain sensitive operational information; maintain appropriate access controls.

## 11. Summary and Official References

- **Thread dumps** show where virtual threads are at a point in time; use `jcmd <PID> Thread.dump_to_file ...`, read stacks in context, and compare multiple snapshots.
- **JFR** shows events unfolding over time; analyze `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed`, and CPU/lock/GC events to test hypotheses.
- **Pinning is distinct from waiting** and must be evaluated against the **JDK version**: monitor pinning is significant on Java 21–23 and greatly improved from Java 24; other pinning cases still exist.
- **Virtual Threads do not automatically cure** deadlocks, pool exhaustion, CPU saturation, or slow I/O. Reliable diagnosis combines dumps, JFR, and actual resource metrics.

Further reading:

- [Oracle: Virtual Threads (Java 21)](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Oracle: `jcmd` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)

# 10.5 Diagnosing Pinning on Java 21 with JFR and `jdk.tracePinnedThreads`

**Scope:** Java 21 (virtual threads are a permanent feature under JEP 444). This lesson focuses on how to detect, read evidence for, and resolve **carrier-thread pinning** when a virtual thread performs a blocking operation. Observation commands and examples are chosen for **JDK 21** behavior rather than extrapolated from newer JDKs.

## 1. Target Outcomes

After this lesson, you will be able to:

1. Explain the relationship between **virtual threads**, **carrier/platform threads**, **mount/unmount** operations, and why prolonged/repeated pinning can hurt scalability.
2. Identify the two primary sources of pinning in Java 21: holding a `synchronized` monitor and executing inside a native/foreign frame while blocking.
3. Collect evidence using the `jdk.VirtualThreadPinned` JFR event and stack traces from `-Djdk.tracePinnedThreads=short|full`.
4. Trace from a stack trace to the code that needs fixing, verify before/after behavior, and avoid false conclusions when seeing `synchronized` or zero events.

## 2. What Is Pinning Really?

Java 21 schedules virtual threads onto a small pool of platform threads called **carrier threads**. When a virtual thread hits a JVM-supported blocking operation (such as `Thread.sleep` or certain I/O), the JVM normally **unmounts** the virtual thread: the waiting task is suspended, and the carrier is returned to run other virtual threads. Once ready to resume, the virtual thread is **mounted** again; the carrier at that point need not be the previous one.

On Java 21, if a virtual thread **is holding a `synchronized` monitor**, or is inside a **native method / foreign-function call**, it may be unable to unmount when it has to block. The virtual thread is then **pinned**: the carrier must wait alongside it. If many concurrent requests hold carriers for long durations, fewer carriers remain available for other work, degrading system **throughput** and wait times.

```text
Unpinned:
virtual thread → begins waiting → unmounts → carrier runs other work → resumes

Pinned on Java 21:
virtual thread → holds monitor / native frame → begins waiting
               → cannot unmount → carrier must also wait → fewer free carriers
```

**Distinguish three concepts:**

- **Having `synchronized`** does not automatically mean an incident: short locks doing only in-memory work or hit rarely are usually harmless.
- **Pinning** is the state of being unable to release the carrier while the virtual thread blocks; its impact depends on **duration, frequency, concurrency level, and actual load**.
- **Lock contention/deadlock** is a separate issue. Many threads contending for the same monitor can serialize requests whether or not pinning occurs. A single pinning event does not prove a deadlock.

The key question is **where the blocking operation sits relative to the monitor or native frame**, not simply counting occurrences of the `synchronized` keyword.

## 3. Two Complementary Observation Channels

| Tool | Primary Evidence | When to Use | Limitations to Remember |
| --- | --- | --- | --- |
| **JDK Flight Recorder (JFR)** | `jdk.VirtualThreadPinned` event, timestamp, duration, virtual thread, stack trace | Collect over realistic load windows; compare before/after | By default records only events meeting the threshold (typically **20 ms**); zero events does not strictly prove zero pinning |
| **`jdk.tracePinnedThreads`** | Stack traces printed when a virtual thread blocks while pinned; `full` highlights monitor/native frames | Quickly isolate the exact code location on Java 21 | Log volume can be huge; does not replace frequency, throughput, and JFR metrics |
| **Thread dumps / system metrics** | Thread state context, latency, queues, CPU | Investigating complex scenarios | Does not replace pinning events and can easily mistake normal I/O waits for pinning |

In **JDK 21**'s default JFR configuration, `jdk.VirtualThreadPinned` is enabled with a **20 ms** threshold. `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` are **disabled by default** to avoid recording huge event volumes; `jdk.VirtualThreadSubmitFailed` is enabled by default. You do not need to enable Start/End just to investigate pinning.

## 4. Runnable Hands-On Lab on Java 21

Create the file **`PinningDemo.java`** with the following complete content. Both sections wait 250 ms; the difference is how the critical section is managed. The first intentionally blocks inside `synchronized`, while the second uses `ReentrantLock`.

```java
import java.util.concurrent.locks.ReentrantLock;

public class PinningDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    public static void main(String[] args) throws InterruptedException {
        Thread pinned = Thread.ofVirtual().name("pinned-demo").start(() -> {
            synchronized (MONITOR) {
                pause();
            }
        });
        pinned.join();
        System.out.println("synchronized: done");

        Thread withLock = Thread.ofVirtual().name("lock-demo").start(() -> {
            LOCK.lock();
            try {
                pause();
            } finally {
                LOCK.unlock();
            }
        });
        withLock.join();
        System.out.println("ReentrantLock: done");
    }

    private static void pause() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }
}
```

Compile and run on **JDK 21**, without `--enable-preview`:

```bash
java -version
javac PinningDemo.java
java PinningDemo
```

**The two lines printed to stdout by the program itself** (ignoring JVM version output and any tool messages):

```text
synchronized: done
ReentrantLock: done
```

Because both virtual threads are joined sequentially via `join()`, the order of the two lines is fixed when the example completes normally. `Thread.sleep(250)` merely simulates an easily reproducible blocking call; in real systems this is typically I/O, a DB query, or another waiting call. The `ReentrantLock` section still holds its lock while sleeping, yet this lock mechanism allows the virtual thread to yield its carrier at the blocking point on Java 21.

**Do not use the elapsed time of this two-task program to claim throughput improvements.** It is an example for recognizing events and stacks; measuring scalability requires many concurrent requests under realistic workloads.

## 5. Diagnosing with JFR on Java 21

### 5.1. Recording from Application Startup

Run a JFR recording; once the program exits, the JVM writes `pinning.jfr`:

```bash
java -XX:StartFlightRecording:filename=pinning.jfr,settings=default,dumponexit=true PinningDemo
```

Read the contents using the tools bundled with **the same JDK**:

```bash
jfr summary pinning.jfr
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

Expectation: at least one `jdk.VirtualThreadPinned` event corresponding to `pinned-demo` on a matching Java 21 build, because the virtual thread sleeps for roughly 250 ms inside a monitor, exceeding the default 20 ms threshold. Event count, field names, internal stack frames, actual duration, and JFR messages can vary across builds and runs; **do not treat a simulated log as guaranteed literal output**. If the recording contains no events, use Section 7 to verify the version, configuration, and capture scope before drawing conclusions.

When reading an event, pay attention to:

- `duration`: how long the blocking operation lasted while pinned, **not** total request runtime.
- `eventThread`: the virtual thread for the event; the thread name can help match it to a request or task.
- `stackTrace`: trace upward from `Thread.sleep`/blocking call to `PinningDemo.pause`, the lambda running the virtual thread, and the `synchronized` site. In real code, follow frames into your application packages and relevant libraries.
- `startTime`: correlate with latency spikes, throughput drops, or high load.

In JDK 21, do not expect advanced cause-explanation fields introduced in newer JDKs. Finding the **monitor held during blocking** usually requires combining the JFR stack with `jdk.tracePinnedThreads=full` and source code inspection.

### 5.2. Recording on a Running JVM

Find the PID and record across a representative load window (the application must remain running throughout the recording):

```bash
jcmd -l
jcmd <PID> JFR.start name=pinning settings=default duration=60s filename=pinning.jfr
```

Replace `<PID>` with the actual process ID. Once the recording completes, inspect events:

```bash
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

For prolonged investigations, you can use `JFR.check` and `JFR.dump` per `jcmd` documentation to inspect and export an active recording. On servers, cap recording duration and size and protect JFR files because stack traces can contain sensitive operational details.

### 5.3. Analyzing the Symptom Properly

A single event lasting a few hundred milliseconds **once** during startup may be insignificant. Hundreds of events on the same request path, accompanied by elevated p95/p99 latency under load, are a high-priority signal. Group by application stack frame, compare **events over time**, **total/distribution of `duration`**, concurrency levels, and throughput impact. Never sum every `duration` to claim total time the service was stalled: many events can overlap concurrently.

## 6. Diagnosing with `jdk.tracePinnedThreads`

This option belongs to the **Java 21** JVM; pass it **before the class name or `-jar`**, right at startup:

```bash
java -Djdk.tracePinnedThreads=short PinningDemo
java -Djdk.tracePinnedThreads=full PinningDemo
```

- `short` prioritizes problematic frames, useful for quickly spotting pinning sites.
- `full` prints a more complete stack, highlighting frames holding **monitors** and **native frames**. In the example, look for `PinningDemo.pause` and the lambda containing `synchronized`.
- The JVM trace output is **supplementary diagnostic output**, separate from the two business stdout lines in Section 4. Do not rely on fixed ordering, trace count, or line count in automated tests.

To correlate with JFR in the **same run**, both options can be combined:

```bash
java -Djdk.tracePinnedThreads=full -XX:StartFlightRecording:filename=pinning.jfr,settings=default,dumponexit=true PinningDemo
```

Read the trace to learn **which code/monitor** causes pinning; use JFR to learn **when and for how long**. A stack trace printed once does not prove the bug happens frequently; conversely, missing trace lines do not rule out every form of carrier saturation.

## 7. Investigation Workflow for a Real Service

1. **Lock down the exact version:** obtain `java -version` from the **JVM running the service** (not merely the JDK on a build machine). Confirm Java 21, that virtual threads are actually being created, and that the workload triggers blocking operations.
2. **Form symptom-based hypotheses:** when many requests wait on I/O, throughput plateaus, or p95/p99 degrades, record load, CPU, connection counts, DB pool usage, and in-flight requests. Pinning is a hypothesis, not the default conclusion.
3. **Record JFR during reproduction:** ensure `jdk.VirtualThreadPinned` is enabled (default 20 ms), run a window long enough to cover the incident, and keep a baseline for comparison.
4. **Group events and locate code paths:** prioritize stacks with large `duration` and high frequency. Find blocking calls inside a `synchronized` method/block or beneath a native/foreign frame; identify the library owning that code.
5. **Reproduce under control:** if you control a Java 21 JVM in a test environment, launch it with `-Djdk.tracePinnedThreads=full` to reveal the monitor/native frame at the exact call site. Enable verbose tracing only where needed.
6. **Fix the verified cause:** move I/O outside the monitor guard whenever invariants allow; or switch frequent/long-blocking monitors to `ReentrantLock` with `finally`; for native libraries, avoid blocking inside callbacks/native frames or upgrade the library.
7. **Re-measure under the same workload:** verify correctness and compare JFR event counts, duration distributions, throughput, latency, and resources. Treat a fix as successful only when pinning risk drops **and** synchronization/stability remain intact.

An example pattern to audit is:

```java
synchronized (guard) {
    // May take hundreds of ms waiting on network or DB:
    callRemoteService();
}
```

If the call does not need to sit inside the critical section, narrowing the `synchronized` scope is the simplest fix. If an exclusive lock must span the blocking work, an alternative in Java 21 is:

```java
lock.lock();
try {
    callRemoteService();
} finally {
    lock.unlock();
}
```

Both snippets are **structural illustrations**, not standalone Java programs. `guard`, `lock`, and `callRemoteService` must be defined by the application. This replacement can still suffer from **lock contention** and serialize requests even though it reduces carrier pinning. When changing lock types, audit all read/write paths for the shared data, lock acquisition/release order, exceptions, `wait/notify` (which must be redesigned using `Condition`), and library thread-safety contracts.

## 8. When JFR or Traces Do Not Show What You Expected

| Scenario | What to Check and How to Interpret |
| --- | --- |
| No `jdk.VirtualThreadPinned` events | Confirm JDK **21**, recording attached to the right JVM/PID, recording covers the workload, event enabled, and 20 ms threshold. Pins shorter than the threshold may not appear. |
| `synchronized` exists but no events appear | There may be no blocking inside the monitor; very short locked sections are not alarming. Trace the actual execution path. |
| Only `Thread.sleep` appears in the JFR stack | Walk up to application frames; use `full` trace to locate monitor/native frames. `Thread.sleep` outside a monitor normally unmounts. |
| `tracePinnedThreads` prints many lines | Group by call site and load rather than treating log lines as task counts. Heavy trace logging can add noise and affect performance. |
| Recording has events yet latency is still good | Pinning is not automatically an incident. Prioritize by frequency, duration, and impact on carriers/throughput. |
| Still slow after switching to `ReentrantLock` | Check lock contention, downstream I/O, DB pool limits, CPU, native frames, and system resources. Fixing pinning does not fix every bottleneck. |
| Example does not reproduce on JDK 24+ | **JEP 491** in Java 24 changed `synchronized` behavior to avoid monitor pinning; `jdk.tracePinnedThreads` no longer applies the way it did on Java 21. Use **JDK 21** per this lesson's scope. |

A particularly common reasoning error is mixing **Java 24+** JFR data with **Java 21** guides and expecting identical event fields or pinning logs. Always record the JDK version alongside every piece of evidence.

## 9. Self-Verification Exercises

1. Run the program on **Java 21** with `-Djdk.tracePinnedThreads=full`. Identify the application frame holding the monitor and the blocking `Thread.sleep` call. Cross-check with JFR.
2. Swap the order of the two test sections or run only the `ReentrantLock` section and record relevant events; explain why **zero** events is the expected outcome here.
3. Try lowering `Thread.sleep(250)` to `Thread.sleep(5)`. Predict why JFR with default settings may skip short pins under 20 ms while the trace flag may still reveal the pinning site. Explain why a single run is insufficient as statistical proof.
4. In your own codebase, find an I/O call inside `synchronized`. Propose the minimal change that preserves correctness; measure p95/p99, throughput, and event counts before/after under the same load configuration.

**Completion checklist:** know the JVM version; inspected `jdk.VirtualThreadPinned.duration`/stack; confirmed blocking inside monitor/native frames; gathered evidence of frequency and impact; fix preserves thread-safety; re-measured under the same workload.

## 10. Reference Sources

- [Oracle Java 21 — Virtual Threads: scheduling, pinning, JFR, and tracePinnedThreads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads (Java 21)](https://openjdk.org/jeps/444)
- [Oracle Java 21 — `jcmd` diagnostics/JFR.start](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java 21 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html)
- [JEP 491 — monitor pinning differences from Java 24](https://openjdk.org/jeps/491)

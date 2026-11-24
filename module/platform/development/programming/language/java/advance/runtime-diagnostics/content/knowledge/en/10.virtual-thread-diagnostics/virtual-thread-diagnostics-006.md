# 10.6 Observing `VirtualThreadPinned`, `VirtualThreadSubmitFailed`, and JFR Configuration

> **Scope:** Java 21+ (virtual threads are a permanent feature since JDK 21). Hands-on pinning examples target JDK 21–23; JDK 24+ introduces major changes via JEP 491. Event names below are full Java Flight Recorder (JFR) event names.

## 1. Objectives and Observation Model

After this lesson, you will be able to:

- Explain why a virtual thread sometimes holds onto its **carrier thread** while waiting, and what makes that affect scalability.
- Distinguish `jdk.VirtualThreadPinned` (waiting while pinned) from `jdk.VirtualThreadSubmitFailed` (failure to submit a virtual thread's work to the scheduler).
- Enable, tune, and inspect JFR events via `.jfc`, `jfr`, and `jcmd`; capture and read `.jfr` recordings.
- Use duration, stack traces, and real load context to pinpoint what needs fixing; recognize differences between JDK 21–23 and JDK 24+.

**Mechanism recap:** a virtual thread (VT) runs Java code by **mounting** onto a platform thread called a *carrier*. When a wait operation supports unmounting, the VT yields the carrier so the carrier can run another VT. When the VT cannot unmount because it is *pinned*, the carrier remains occupied while the VT waits. Pinning does not equate to deadlock, business errors, or `OutOfMemoryError`; its main impact is reducing reuse of the finite carrier pool when wait durations are long **and** frequent.

In JDK 21–23, blocking while inside a `synchronized` block/method or executing across a native/foreign frame can cause pinning. A `synchronized` section performing only brief computation does not automatically become a problem: what matters is **long blocking in an unmountable state**. Starting in JDK 24, JEP 491 allows virtual threads waiting inside `synchronized` constructs to release their carriers; pinning due to native/VM frames and certain runtime cases still warrants observation.

## 2. Four Key JFR Events to Know

| Event | Meaning | JDK 21 `default.jfc` Default | When to Use |
| --- | --- | --- | --- |
| `jdk.VirtualThreadPinned` | VT performed a blocking operation while pinned long enough to exceed the threshold. | `enabled=true`, `threshold=20 ms`, `stackTrace=true` | Locate code holding the carrier while waiting and measure the duration of that blocking call. |
| `jdk.VirtualThreadSubmitFailed` | The runtime failed to submit the continuation/task for a VT to start or resume after unpark; may relate to resource exhaustion or scheduler rejection. | `enabled=true`, `stackTrace=true` | Investigate scheduling failures; correlate with exceptions, logs, and resource health. |
| `jdk.VirtualThreadStart` | VT began executing. | `enabled=false` | Short-term lifecycle tracking when reconciling VT counts. |
| `jdk.VirtualThreadEnd` | VT terminated. | `enabled=false` | Correlate VT completion times during lifecycle investigations. |

The values above are **JDK default configurations**, which does not mean JFR is always recording continuously. You must **start a recording**, and that recording must use a profile containing the relevant events. Custom `.jfc` files, JDK versions, or vendors may alter effective settings.

**Understanding `threshold` properly:** `20 ms` is the duration threshold for a single blocking call **while pinned**, not total VT runtime, total monitor hold time, or total request latency. Events below the threshold do not appear in the recording; `VirtualThreadSubmitFailed` is a submission-failure event and has no equivalent duration threshold. `Thread.sleep`, `SocketRead`, `ThreadPark`, or `JavaMonitorEnter` do **not by themselves prove** a VT is pinned; they are useful only for correlating causes.

## 3. Configuring Events and Starting a Recording

### 3.1. Checking Tools and Event Definitions

Use a JDK with `java`, `javac`, `jfr`, and `jcmd` on `PATH`. Prefer tools from the **same JDK version as the JVM under diagnosis**.

```bash
java -version
jfr help configure
jfr metadata --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed
```

`jfr metadata` reveals the exact field names present on your JDK. On JDK 21, for example, focus on `duration`, `eventThread`, and `stackTrace` for pinned events; for submit failures, check `javaThreadId` and `exceptionMessage`. JDK 24+ adds pinning diagnostics such as `blockingOperation`, `pinnedReason`, and `carrierThread`; **do not assume these newer fields exist on JDK 21**.

### 3.2. Creating a `.jfc` File for Short-Term Observation

You do not need to hand-edit XML. `jfr configure` uses `default.jfc` as its base when `--input` is omitted:

```bash
jfr configure --output vt-diagnostics.jfc "jdk.VirtualThreadPinned#enabled=true" "jdk.VirtualThreadPinned#threshold=5ms" "jdk.VirtualThreadPinned#stackTrace=true" "jdk.VirtualThreadSubmitFailed#enabled=true" "jdk.VirtualThreadSubmitFailed#stackTrace=true"
```

`vt-diagnostics.jfc` keeps the baseline events from `default.jfc` and lowers the pinned threshold from 20 ms to **5 ms** for investigation. The `#` character is **part of the JFR setting syntax**, not a shell comment; quoting each argument ensures compatibility across shells.

- `enabled=true`: record the event when an appropriate recording is active.
- `threshold=5ms`: catch shorter pinned blocking calls; lower thresholds increase potential event volume and overhead.
- `stackTrace=true`: capture the call chain to trace back to the blocking site; increases data size compared to recording events alone.
- Do not add a `threshold` to `VirtualThreadSubmitFailed`: it does not measure a wait duration.
- Do not leave `VirtualThreadStart`/`End` enabled indefinitely on systems creating millions of VTs; they can generate massive event volumes. If genuinely needed for a brief window, add `"jdk.VirtualThreadStart#enabled=true" "jdk.VirtualThreadEnd#enabled=true"` to the configuration command.

For long-term production measurement, start with `default.jfc` and the 20 ms threshold; lower the threshold only for time-bounded diagnostic sessions. `profile.jfc` collects more data and therefore typically incurs higher overhead than `default.jfc`.

### 3.3. Capturing at Program Startup

```bash
java -XX:StartFlightRecording=filename=vt-diagnostics.jfr,dumponexit=true,settings=vt-diagnostics.jfc -cp . MyApp
```

Replace `MyApp` with your application's main class or launch flags (e.g., `-jar app.jar`). The recording uses the settings file you just created; `dumponexit=true` writes the file when the JVM exits. `.jfr` files are **binary** and must be opened with JFR/JDK Mission Control rather than read as plain-text logs. Prefer absolute paths if the working directory is uncertain.

### 3.4. Capturing on an Already-Running JVM

Locate the target JVM's PID and attach:

```bash
jcmd -l
jcmd <PID> JFR.start name=vt-diag settings=vt-diagnostics.jfc duration=60s filename=vt-diagnostics.jfr
jcmd <PID> JFR.check name=vt-diag verbose=true
```

`JFR.check verbose=true` verifies that the recording is active and confirms its effective event settings, avoiding false inferences from an unused `.jfc` file. To take a snapshot while the recording is still running:

```bash
jcmd <PID> JFR.dump name=vt-diag filename=vt-snapshot.jfr
```

Or to **stop a non-timed recording** and write the final file:

```bash
jcmd <PID> JFR.stop name=vt-diag filename=vt-final.jfr
```

With `duration=60s`, the recording expires automatically after that window; you do not need to call `JFR.stop` again. Attach commands require appropriate permissions for the target process. Depending on startup flags and environment, `jcmd` may be unable to attach; in that case, use `-XX:StartFlightRecording` at startup.

**Distinguish two easily confused commands:** `jfr configure` creates/edits a `.jfc` **event settings file**. `jcmd <PID> JFR.configure` mainly configures global recorder parameters (buffers, repository, etc.); to select events for a recording, pass `settings=...` to `JFR.start` or use the corresponding JFR API.

### 3.5. Reading Results and Checking Metadata

```bash
jfr summary vt-diagnostics.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd vt-diagnostics.jfr
jfr metadata --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
```

- `jfr summary` checks event presence, total counts, and size; helps catch wrong recordings or missing events.
- `jfr print --events` filters to specific event types so you can inspect timestamps, durations, threads, stacks, and error details. If Start/End were not enabled, printing those two events yields empty output, which is expected.
- `jfr metadata ... <file>` inspects the **schema stored inside the recording itself**; useful when the analysis tool and the producing JVM differ in version.
- JDK Mission Control (JMC) is more convenient when grouping by stack trace, filtering by time, inspecting related events, and correlating with CPU/GC/latency.

## 4. Interpreting `jdk.VirtualThreadPinned`

A pinned event indicates a **blocking operation long enough while the VT could not yield its carrier**. On JDK 21–23, the key fields to examine are:

| Field | How to Read |
| --- | --- |
| `startTime`, `duration` | When the blocking occurred and how long it lasted; used to correlate with latency spikes or stalls. |
| `eventThread` | The virtual thread that emitted the event (when provided by metadata/recording). |
| `stackTrace` | Call chain where the runtime recorded pinning; follow frames back into your application packages. |
| `blockingOperation`, `pinnedReason`, `carrierThread` | Richer details on newer JDKs (JDK 24+), indicating the waiting operation, pinning reason, and involved carrier. Do not assume these fields exist on JDK 21. |

**Practical analysis sequence:**

1. Select time windows showing elevated request latency, reduced throughput, or heavy carrier occupancy.
2. Filter `VirtualThreadPinned` and group by stack trace/source location. Count frequencies and examine duration distributions rather than reacting to a single event.
3. Locate application frames near I/O calls, `sleep`, park, monitors, or native boundaries; check JDK version and source code to determine why unmounting was blocked.
4. Correlate related events (`jdk.SocketRead`, `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`) and real metrics; they supply context without proving pinning on their own.
5. Fix only sites with **long and frequent pinned blocking**. After the change, replay comparable load and measure event counts, durations, throughput, and request latency.

Avoid jumping to "replace every `synchronized`": short monitors doing mostly CPU work or rarely blocking are not necessarily bottlenecks. On JDK 21–23, when I/O or long waits occur inside a monitor, prefer moving blocking outside the synchronized block; when mutual exclusion must span the wait, consider `ReentrantLock` with `try/finally`. JDK 24+ generally resolves monitor pinning via runtime upgrade; other pinning causes still require verification.

**Seeing zero events** can mean no pinned blocking occurred, wait durations stayed below the threshold, the recording window missed the load, the wrong `.jfc` was used, stack traces were disabled, or behavior changed in a newer JDK. It **does not prove** the system is immune to pinning.

## 5. Interpreting `jdk.VirtualThreadSubmitFailed`

Unlike pinning, `VirtualThreadSubmitFailed` signals a failure in the path that **submits/schedules a virtual thread's continuation** to start or resume after unpark. Per the OpenJDK JDK 21 implementation, one path is the scheduler rejecting task submission with `RejectedExecutionException`; the event contains fields such as the VT's `javaThreadId` and `exceptionMessage`. The event is enabled by default, **which does not mean every exception inside a task, every rejected `ExecutorService.submit()`, or every out-of-memory condition automatically emits this event**.

When you observe this event:

1. Read `startTime`, `javaThreadId`, `exceptionMessage`, and `stackTrace` if present; `eventThread` is the thread that recorded the event and may **differ** from the VT identified by `javaThreadId`.
2. Correlate with application logs/exceptions at the same timestamp, executor/scheduler lifecycles, and recent deployment changes. Look for evidence of scheduler shutdown, task rejection, or failures on the resume/unpark path.
3. Check resource pressure: memory/GC, platform/carrier thread counts, CPU load, file descriptors, container limits, backlogs, and downstream limits; separate proven causes from hypotheses.
4. Resolve the proven source of rejection, resource exhaustion, or lifecycle race; re-run the equivalent scenario and confirm the event does not recur.

Never interpret `VirtualThreadSubmitFailed` as "the task ran and returned an error." It is a failure **submitting work to the scheduler**, occurring either before the task runs or when a VT needs to resume. Nor does a pinned event mean a submit failure will follow: the two signals describe **two distinct mechanisms**.

## 6. Pinning Verification Lab (JDK 21–23)

The following experiment intentionally sleeps a VT for 250 ms **inside a monitor** in `monitor` mode, then uses `ReentrantLock` in `lock` mode. The goal is to observe the event, not to benchmark performance. Run this on JDK 21–23 to compare pinning caused by `synchronized`.

Create the file `VirtualThreadJfrDemo.java`:

```java
import java.util.concurrent.locks.ReentrantLock;

public class VirtualThreadJfrDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    private static void pause() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boolean useMonitor = args.length == 0 || !"lock".equals(args[0]);
        Thread vt = Thread.ofVirtual().name("vt-demo").start(() -> {
            if (useMonitor) {
                synchronized (MONITOR) {
                    pause();
                }
            } else {
                LOCK.lock();
                try {
                    pause();
                } finally {
                    LOCK.unlock();
                }
            }
        });
        vt.join();
        System.out.println(useMonitor ? "monitor completed" : "lock completed");
    }
}
```

Compile with JDK 21+ and run both modes using the `.jfc` from Section 3:

```bash
javac VirtualThreadJfrDemo.java
java -XX:StartFlightRecording=filename=monitor.jfr,dumponexit=true,settings=vt-diagnostics.jfc VirtualThreadJfrDemo monitor
java -XX:StartFlightRecording=filename=lock.jfr,dumponexit=true,settings=vt-diagnostics.jfc VirtualThreadJfrDemo lock
jfr print --events jdk.VirtualThreadPinned monitor.jfr
jfr print --events jdk.VirtualThreadPinned lock.jfr
```

Stdout lines printed by the **Java program**, in order of the two runs:

```text
monitor completed
lock completed
```

The JVM may print additional JFR startup/recording notices; those two lines are not the entirety of JVM stdout when recording is active.

**Expected result:** on JDK 21–23, the `monitor` run normally produces a `jdk.VirtualThreadPinned` event with a duration close to the wait time (varying in practice), because `Thread.sleep` executes while the VT holds the monitor. The `lock` run normally produces no pinned event for this sleep because the VT can unmount. Observations depend on recording timing, threshold, exact JDK, and system conditions. On JDK 24+, JEP 491 changed monitor behavior, so **do not treat the absence of pinned events in `monitor` mode as a broken lab**.

In production business code, better options often exist: shrink the `synchronized` scope to protect only brief state mutations and move I/O/blocking outside the lock if invariants permit. `ReentrantLock` requires disciplined `lock()`/`unlock()` pairing; mechanically replacing every monitor can add complexity without improving performance.

## 7. Investigating a Real-World Incident

Suppose a server uses virtual threads to call downstream HTTP services and suffers latency spikes as load rises.

**If `VirtualThreadPinned` appears frequently:** group by stack and observe VTs blocking on client calls inside monitors on JDK 21; examine why the monitor wraps I/O, and consider narrowing the critical section or switching to an appropriate lock. Re-measure under identical load rather than looking solely at reduced event counts. On JDK 24+, inspect `pinnedReason` and `blockingOperation` when available, since typical monitor pinning is resolved.

**If `VirtualThreadSubmitFailed` appears:** read the exception message and stack; check for scheduler/executor task rejection, shutdown races, resource exhaustion, or infrastructure changes. Do not blindly raise scheduler parallelism or spawn more VTs: large VT counts do not make downstream pools, CPU, or memory infinite. Monitor both error rates and resources while remediating.

**If neither event appears yet latency remains high:** verify configuration and recording coverage first, then examine connection pool bottlenecks, downstream request limits, DB, GC, CPU, lock contention, timeouts, and application-layer queues. Virtual threads reduce the cost of waiting on platform threads; they do not make I/O or downstream services faster.

Any meaningful measurement should record **JDK version, `.jfc` used, recording duration, load window, pinned threshold, event count, prominent stack groups, and latency/throughput**. Compare before/after under comparable conditions.

## 8. Version Differences and Common Pitfalls

| Situation | Correct Interpretation |
| --- | --- |
| JDK 21–23 blocking inside `synchronized` | VT may hold the carrier while waiting; `VirtualThreadPinned` is a signal worth inspecting. |
| Re-running the same code on JDK 24+ yields zero events | Likely the effect of **JEP 491**, not broken JFR; other pinning causes can still occur. |
| `synchronized` exists yet zero events appear | The event does not count every monitor; a pinned blocking call must exceed the threshold during the recording. |
| Event enabled in `.jfc` yet `.jfr` file has none | Verify the recording actually used that `.jfc` via `JFR.check verbose=true`, load coverage, and threshold. |
| `VirtualThreadStart`/`End` do not appear | Both lifecycle events are disabled in `default.jfc`; enable only briefly when needed. |
| `VirtualThreadSubmitFailed` missing when a task throws an exception | The event reflects scheduler submission failures, not general exceptions thrown inside task bodies. |
| Wanting to remove the threshold to catch every pin | Can cause data explosion; pick a smaller threshold for a short window, then revert to stable settings. |
| Analyzing JFR files from a different JDK version | Run `jfr metadata ... file.jfr`; event names and fields evolve across releases. |

On JDK 21–23, the local debugging flag `-Djdk.tracePinnedThreads=full` or `short` also prints stacks when pinning happens. This is a diagnostic aid from older JDK releases; **do not rely on this property in JDK 24+** following JEP 491 changes. JFR remains the better mechanism for capturing timestamped data, durations, and correlations with other events.

## 9. Action Checklist and Key Takeaways

1. Identify the running JVM version and reproduce the load.
2. Enable `jdk.VirtualThreadPinned` and `jdk.VirtualThreadSubmitFailed` using an appropriate `.jfc`; review thresholds and `stackTrace`.
3. Start recording via `-XX:StartFlightRecording` or attach with `jcmd JFR.start`; verify with `JFR.check verbose=true`.
4. Use `jfr summary`, `jfr print`, and JMC to group events by stack, timestamp, duration, or exception.
5. For pinning: locate **blocking that holds the carrier**, check frequency and JDK version. For submit failures: locate the **rejected submit path** and evidence of resource/lifecycle pressure.
6. Fix the verified cause, re-record under the same scenario, and compare latency, throughput, and event counts/durations. If higher sensitivity is needed, lower the threshold for a brief window and restore it afterward.

**Remember:** `VirtualThreadPinned` is for investigating **inability to yield the carrier while waiting**; `VirtualThreadSubmitFailed` is for investigating **continuation scheduling failures**. The presence of an event alone is not enough to assign blame or choose an optimization; always correlate stacks, recording configuration, JDK version, and application metrics.

## References

- [Oracle JDK 21 — Virtual Threads, pinning, and JFR events](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK — JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/jfr/configure/)
- [Oracle JDK 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)

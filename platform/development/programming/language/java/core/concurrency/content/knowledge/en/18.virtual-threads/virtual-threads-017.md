# JFR: `VirtualThreadPinned`, `VirtualThreadSubmitFailed`, and Event Recording Thresholds

## 1. Why Use JFR with Virtual Threads?

**Java Flight Recorder (JFR)** is a diagnostic event recorder built into the JDK. With **virtual threads** (finalized in Java 21), JFR helps identify conditions that limit scalability, in particular:

- **`jdk.VirtualThreadPinned`**: A virtual thread is held on a **carrier** (the platform thread executing it) during a blocking operation; the carrier cannot be used for another virtual thread during that interval. The event is recorded when recording is enabled and the duration meets the threshold.
- **`jdk.VirtualThreadSubmitFailed`**: The Java runtime failed to submit the work needed to **start or resume** a virtual thread, typically suggesting a resource or scheduler issue. This is a runtime-level failure signal, **not** a normal business exception inside a `Runnable`.
- **The `threshold` setting**: Filters out short pinning occurrences before recording an event. The threshold reduces noise and recording overhead; it does **not** alter scheduling, prevent pinning, or automatically resolve issues.

This covers **pure Java/JVM concurrency**. The examples use `java.lang.Thread`, `jdk.jfr`, and tools bundled with the JDK; no application framework is required.

> **Background:** Virtual threads are scheduled by the JDK onto one or more platform threads called *carriers*. When a virtual thread waits on supported I/O, the runtime can typically **unmount** it to free the carrier. *Pinning* occurs when a virtual thread cannot unmount while blocked; if it is prolonged and happens frequently, carriers remain occupied and throughput can drop. Pinning by itself does not prove that an application is deadlocked or has faulty logic.

## 2. How Do the Two JFR Events Differ?

| Criterion | `jdk.VirtualThreadPinned` | `jdk.VirtualThreadSubmitFailed` |
| --- | --- | --- |
| Detects | A **blocking while pinned** occurrence long enough to be recorded | A runtime failure to submit/resume virtual thread execution |
| Meaning | The carrier was not released during the wait | The runtime could not schedule a virtual thread task as expected |
| Default state in JFR `default.jfc` configuration | **Enabled**, threshold typically **20 ms** | **Enabled** |
| Needs `threshold` tuning? | Optional: 20 ms, 5 ms, 0 ms... | Does not use a duration threshold the way the pinned event does |
| Can be absent in a normal run? | Yes: no blocking pinning occurred, or all occurrences were below the threshold | Yes: no submit failure occurred |
| Investigation direction | Call stack, blocking operation, JDK version, native libraries, number of held carriers | System/JVM resource health, scheduler, pending task count, related errors |

Other events such as `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` track when virtual threads start/end, but are **disabled by default** in typical configurations because a large volume of virtual threads can generate many events. `jdk.ThreadSleep`, `jdk.SocketRead`, and `jdk.JavaMonitorEnter` can also be useful for correlating context; they are **not synonymous** with pinning.

### 2.1. What Does `VirtualThreadPinned` Measure?

An event does not appear simply because a virtual thread is inside a `synchronized` block. To produce a `jdk.VirtualThreadPinned` event, there must be an operation that **blocks while pinned**, JFR must be recording, the event must be enabled, and the duration must meet the threshold. The event typically includes timestamp, duration, thread information, and stack trace (if enabled). **Additional field names** such as the pinning reason or blocking operation can vary across JDK versions; inspect the schema via `jfr metadata` instead of hard-coding every field name.

Some practical scenarios:

1. On **JDK 21–23**, frequent or long-running blocking I/O or `Thread.sleep` **inside** a `synchronized` block can hold onto a carrier.
2. Native/foreign calls or VM frames that cannot unmount a virtual thread can still cause pinning on newer JDKs.
3. Monitor contention, waiting on class initialization, and other runtime details must be evaluated according to the actual JDK version and recorded events.

**Important change starting in JDK 24:** JEP 491 improved monitor handling so that virtual threads can unmount in most cases when blocking inside `synchronized`. Therefore, an example where "`synchronized` + `sleep` produces a pinned event" may work on JDK 21 but **no longer emit an event** on JDK 24+. JFR `VirtualThreadPinned` remains useful for the remaining causes of pinning; do not assume "no events observed" means there is no bottleneck.

### 2.2. What Does `VirtualThreadSubmitFailed` Report?

This event concerns **submitting a virtual thread** to the execution mechanism, including when newly created or when a virtual thread needs to resume after a wait state. It reflects a failed submission attempt, which may result from resource pressure or scheduler state. When encountering this event, check resources and context at the same timestamp; a single root cause cannot be concluded from the event name alone.

Distinctions:

- A task throwing `IllegalArgumentException`/`IOException` and terminating: does **not automatically** emit `VirtualThreadSubmitFailed`.
- `Future.get()` throwing `ExecutionException`: this is task error propagation; it is **not synonymous** with a runtime submit failure.
- Connection pool exhaustion or request timeouts: can cause business failures, but do **not inherently** produce this event.
- Absence of `VirtualThreadSubmitFailed` in a recording: only tells you the event was **not recorded** within the captured scope and configuration; it does not confirm all resources are healthy.

## 3. The `threshold` Setting: Understanding the 20 ms Number

In standard JDK JFR configurations, `jdk.VirtualThreadPinned` is enabled with **`threshold=20 ms`**. This means the event is recorded when the blocking-while-pinned duration is **long enough to pass the threshold filter**; not every piece of code running on a virtual thread for longer than 20 ms produces an event.

Illustrative examples:

| Operation | Duration | 20 ms threshold config | Likely to become a `Pinned` event? |
| --- | ---: | ---: | --- |
| Virtual thread sleeps 200 ms and unmounts normally | 200 ms | 20 ms | **No**, because it is not pinned |
| Blocking while pinned for 8 ms | 8 ms | 20 ms | **No**, because it is below the threshold |
| Blocking while pinned for 75 ms | 75 ms | 20 ms | **Yes**, if recording is active and the event is enabled |
| Scheduler failure to submit virtual thread | Not a pinning duration | Not applicable | `VirtualThreadSubmitFailed` may be recorded |

**Typical threshold levels:**

- **20 ms:** A reasonable starting point for detecting relatively long pinning with low noise (common default value).
- **5 ms:** Increases sensitivity during a short diagnostic run; may increase event volume and stack trace overhead.
- **0 ms:** Disables duration filtering; easily produces a very large number of events. Use only with a specific measurement goal, a sufficiently short duration, and while monitoring disk/overhead.
- **Higher than 20 ms:** Suitable when looking only for the longest blocking cases, but misses many shorter occurrences that add up.

`threshold` is an **event setting**, not the `period` or `cutoff` of a JFR file. `period` applies to periodic events; `maxsize`/`maxage` manage recording size/data age and do not determine the duration required to emit `VirtualThreadPinned`.

Do not turn an event with `duration=30 ms` into a conclusion that **the user experienced exactly 30 ms of slowdown**: that is the duration associated with the event, whereas request latency can include many other components.

## 4. Checking the JDK and Event Schema Before Analysis

The following commands run from a JDK with `java`/`jfr` tools. Java 21+ is recommended for virtual threads.

~~~bash
java -version
jfr help
jfr metadata --events jdk.VirtualThreadPinned
jfr metadata --events jdk.VirtualThreadSubmitFailed
~~~

`jfr metadata` prints the definitions and event fields known to the **current JDK**. On JDK versions that add fields, the output may differ. If the tool cannot find an event, check whether the JDK running `jfr` is the same version as the JVM that created the recording. For a `recording.jfr` file, you can inspect the metadata **of the recording itself**:

~~~bash
jfr metadata recording.jfr
~~~

To see the actual configuration in use, inspect `$JAVA_HOME/lib/jfr/default.jfc` (Windows: `%JAVA_HOME%\lib\jfr\default.jfc`), or any custom `.jfc` configuration that was loaded. Default values may vary across JDK versions, vendors, and configurations; **do not treat 20 ms as a mandatory rule for every recording**.

## 5. Recording and Reading JFR with JDK Commands

### 5.1. Starting Recording Together with the Application

Example of a Java program with main class `PinnedWorkloadDemo`, using the default configuration and writing a file when the JVM exits:

~~~bash
java -XX:StartFlightRecording:settings=default,filename=vt-events.jfr,dumponexit=true PinnedWorkloadDemo
~~~

When the JVM shuts down normally, `vt-events.jfr` contains the recorded JFR events. If the workload is too short, has too few samples, or has no events meeting the threshold, the recording may **not** contain either of the events you are looking for. The path is relative to the current working directory. You can use an absolute path in real deployments.

Inspect the file and filter events:

~~~bash
jfr summary vt-events.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-events.jfr
~~~

If you need to view virtual thread lifecycle context:

~~~bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-events.jfr
~~~

Note: `Start` and `End` may not appear because they are disabled by default. `jfr print --events` is a **display filter**; it cannot recover events that were never recorded. To output in a machine-readable format:

~~~bash
jfr print --json --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-events.jfr
~~~

Use `jfr summary` to see how many events of each type exist in the file. Use `jfr print` or JDK Mission Control (JMC) to inspect call stacks, durations, and timestamps; correlate with CPU, socket, lock, GC, and load at the same time.

### 5.2. Recording a Running Process

Find the target Java process:

~~~bash
jcmd -l
~~~

Example with an actual PID of **12345**:

~~~bash
jcmd 12345 JFR.start name=vt-diagnosis settings=default filename=vt-live.jfr
jcmd 12345 JFR.dump name=vt-diagnosis filename=vt-live.jfr
jcmd 12345 JFR.stop name=vt-diagnosis
~~~

The PID is only an example. `JFR.start` begins a recording in the target JVM; `JFR.dump` writes a snapshot to disk; `JFR.stop` ends the recording. To check the parameters supported by the running JVM, use:

~~~bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.check
~~~

Before analyzing, verify that the recorded **time window** overlaps with when the application experienced the issue. A file recorded after the incident ended may not contain the relevant events.

## 6. Customizing the Threshold with `.jfc`

Since JDK 19, the `jfr configure` tool supports creating a new configuration based on `default.jfc`. For example, lowering the `VirtualThreadPinned` threshold from 20 ms to **5 ms**, keeping `VirtualThreadSubmitFailed` enabled, and retaining stack traces:

~~~bash
jfr configure --input default --output vt-5ms.jfc "jdk.VirtualThreadPinned#enabled=true" "jdk.VirtualThreadPinned#threshold=5ms" "jdk.VirtualThreadPinned#stackTrace=true" "jdk.VirtualThreadSubmitFailed#enabled=true"
~~~

Then run:

~~~bash
java -XX:StartFlightRecording:settings=vt-5ms.jfc,filename=vt-5ms.jfr,dumponexit=true PinnedWorkloadDemo
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-5ms.jfr
~~~

If you only need to verify the threshold value, use `jfr help configure` and open `vt-5ms.jfc`: the corresponding section will look like XML (excerpt, **not** the full file):

~~~xml
<event name="jdk.VirtualThreadPinned">
  <setting name="enabled">true</setting>
  <setting name="stackTrace">true</setting>
  <setting name="threshold">5 ms</setting>
</event>
~~~

**Why not configure `VirtualThreadSubmitFailed#threshold`?** A submit failure is a failure signal, not a "blocking duration" to filter like `VirtualThreadPinned`. Only use settings actually supported by the event. You can check available events and settings in `default.jfc` or metadata. Lowering the threshold for `VirtualThreadPinned` does not cause more submit failures to occur.

How to interpret results after tuning:

1. If no pinned events appear at a 20 ms threshold, but many 6–15 ms events appear at 5 ms, those may be short pinning occurrences that were previously filtered out.
2. An increase in event count after lowering the threshold **does not by itself prove** the program became slower. It is a change in measurement.
3. To compare two points in time, keep the same configuration, the same JDK, and an equivalent workload. Do not directly compare raw event counts from two recordings with different durations or thresholds.
4. Even a single long event is not enough to prove a major throughput impact; you need to know its frequency, how many carriers are occupied, scheduler state, and actual load.

## 7. Runnable Example: Demonstrating Pinning on JDK 21–23

This example has a virtual thread call `Thread.sleep(120)` while holding a `synchronized` monitor. **On JDK 21–23**, this is the classic scenario that produces a `jdk.VirtualThreadPinned` event exceeding the 20 ms threshold. **On JDK 24+**, monitor handling was improved so the example typically no longer causes pinning; that is expected behavior for that version, not a JFR recording bug.

Save as **`PinnedWorkloadDemo.java`**:

~~~java
public class PinnedWorkloadDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-pinning-demo")
                .start(() -> {
                    synchronized (LOCK) {
                        try {
                            Thread.sleep(120);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    }
                });

        worker.join();
        System.out.println("Workload completed");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PinnedWorkloadDemo.java
java -XX:StartFlightRecording:settings=default,filename=vt-demo.jfr,dumponexit=true PinnedWorkloadDemo
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-demo.jfr
~~~

**Stdout produced by the Java program**, excluding JVM JFR initialization messages:

~~~text
Workload completed
~~~

The JVM may print additional `[info][jfr]` lines; these vary by version. `jfr print` has no fixed stdout:

- On **JDK 21–23**, if JFR recorded the right interval and the event met the threshold, there will usually be a `jdk.VirtualThreadPinned` record with a stack trace pointing to `PinnedWorkloadDemo`.
- On **JDK 24+**, do not expect an event solely from `synchronized` in this example.
- `jdk.VirtualThreadSubmitFailed` will almost certainly **not appear** in a normal run; do not intentionally trigger resource exhaustion just to generate the event.

**Why isn't `Thread.sleep(120)` alone enough?** A virtual thread can unmount during a normal sleep. In this example, the decisive factor on JDK 21–23 is that the sleep happens **while holding a Java monitor**. Do not equate the duration of `Thread.sleep` with `VirtualThreadPinned`.

## 8. Creating a JFR Recording via the Java API (Adjusting Threshold in Code)

If you need to automate diagnostics inside the program's JVM, use the `jdk.jfr.Recording` API. The following example enables both events, sets the `VirtualThreadPinned` threshold to **5 ms**, writes `vt-api.jfr`, and stops after the worker finishes. It does not depend on the `jfr configure` CLI.

Save as **`VirtualThreadJfrApiDemo.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public class VirtualThreadJfrApiDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("vt-api.jfr");
        Object lock = new Object();

        try (Recording recording = new Recording()) {
            recording.enable("jdk.VirtualThreadPinned")
                    .withThreshold(Duration.ofMillis(5))
                    .withStackTrace();
            recording.enable("jdk.VirtualThreadSubmitFailed")
                    .withStackTrace();

            recording.start();

            Thread worker = Thread.ofVirtual().start(() -> {
                synchronized (lock) {
                    try {
                        Thread.sleep(80);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            });

            worker.join();
            recording.stop();
            recording.dump(output);
        }

        System.out.println("JFR file exists: " + Files.exists(output));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 VirtualThreadJfrApiDemo.java
java VirtualThreadJfrApiDemo
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-api.jfr
~~~

**Primary stdout from Java** when write permissions exist in the current directory:

~~~text
JFR file exists: true
~~~

`recording.enable(...).withThreshold(...)` configures the event for this recording and does not permanently change the JVM defaults. Calling `recording.stop()` before `dump()` ensures the recording window is closed; `try-with-resources` closes the resource. The file may still contain no `VirtualThreadPinned` events on JDK 24+ or if the JVM did not meet the conditions to emit the event; `Files.exists` only checks that the file was created, **not** that pinning occurred.

To see which events are actually in the file, use `jfr summary vt-api.jfr`. You can write a custom reader using `jdk.jfr.consumer.RecordingFile`, though `jfr print` is usually easier for initial investigation.

## 9. How to Investigate When Events Appear

### 9.1. When You See `jdk.VirtualThreadPinned`

1. **Verify the JDK and JFR configuration:** version/vendor, `enabled`, `threshold`, `stackTrace`, and measurement window.
2. **Find hotspots:** group events by stack trace and blocking operation; prioritize call sites that repeat frequently with large total duration, rather than fixing a single rare long event.
3. **Check carrier resource usage:** how many virtual threads are waiting at peak times, how many carriers are busy, request latency, and throughput. A stack trace is only a starting point for inspecting the code.
4. **Distinguish causes by JDK version:** on JDK 21–23, check blocking inside monitors; on JDK 24+, check native/foreign calls, VM frames, and special cases.
5. **Mitigate in the right place:** narrow synchronized sections, avoid blocking I/O while holding a monitor on older JDKs, or replace with `ReentrantLock` when the semantics fit. For native calls, inspect the library and call architecture rather than blindly changing `synchronized`.
6. **Re-measure** with the same workload and JFR configuration; check throughput, latency, CPU, GC, and event counts rather than looking only at a drop in stack traces.

Example **conditional before–after on JDK 21–23** (illustrative snippet inside a method, not a standalone file):

~~~java
// Before: pinning can occur when performing blocking I/O inside a monitor.
synchronized (lock) {
    readFromRemoteService(); // assuming this is blocking I/O
}

// After: if logic allows, perform I/O outside the critical section.
var data = readFromRemoteService();
synchronized (lock) {
    updateSharedState(data);
}
~~~

The two versions are **not automatically equivalent in synchronization semantics**: if you must guarantee that data does not change between the read and the update, you need a different synchronization protocol. Do not move I/O arbitrarily in a way that breaks data invariants. A `ReentrantLock` can still cause contention; the goal is to avoid holding a carrier and reduce lock hold time, not to eliminate all locks.

### 9.2. When You See `jdk.VirtualThreadSubmitFailed`

1. Read all events at the **same timestamp**, stack traces, and any extra fields if present; do not guess field names that differ across JDK versions.
2. Check CPU, RAM/heap, native memory, cgroup/container limits, platform thread count, process limits, and virtual thread creation/unpark rates.
3. Correlate with `OutOfMemoryError`, scheduler issues, JVM logs, and related warnings. Failure may be due to resources, but the event itself **does not prove** a heap OOM.
4. Review load design: incoming request rate, fan-out, long CPU-bound work, and retry frequency; apply backpressure and bound **target resources** such as database connections or remote API concurrency.
5. If submit failures occur in production, prioritize analysis and controlled reproduction; **do not** intentionally exhaust a live machine's resources just to trigger a JFR event.

Do not treat `VirtualThreadSubmitFailed` as equivalent to a `RejectedExecutionException` from a user-configured `ThreadPoolExecutor`. They involve different execution paths; base your conclusions on JVM and application-code evidence.

### 9.3. When Neither Event Appears

Check in order:

- Did the JVM have recording enabled and capture the exact time window when the issue occurred?
- Does the file contain other events in `jfr summary`?
- Are `VirtualThreadPinned` and `stackTrace` enabled, and is the threshold set too high?
- On JDK 24+, does an older `synchronized` test case still produce pinning?
- `VirtualThreadSubmitFailed` may genuinely not have occurred, even if application requests failed.
- Does the workload have a different bottleneck: saturated database, socket timeout, CPU, blocking I/O unrelated to pinning, normal monitor contention, queues, or GC?

**No events ≠ no problem.** JFR only reflects events that were configured and actually recorded during the observation window.

## 10. Additional Observability and Practicality

To inspect virtual threads in a running process, the JDK may support:

~~~bash
jcmd 12345 Thread.dump_to_file -format=json vt-threads.json
~~~

Replace the PID with the actual process ID. A thread dump is useful for viewing waiting virtual threads; it is a **point-in-time snapshot**, whereas JFR collects events over time. On JDKs that support them, you can also check:

~~~bash
jcmd 12345 Thread.vthread_scheduler
jcmd 12345 Thread.vthread_pollers
~~~

Diagnostic commands can vary by version; use `jcmd 12345 help` to see which commands the JVM actually supports.

Do not enable `VirtualThreadStart`/`VirtualThreadEnd` wholesale for a system creating massive numbers of virtual threads over long periods without measuring overhead and recording size. Likewise for `VirtualThreadPinned`, when lowering `threshold`, prefer **short, targeted recordings** and tune `maxsize`/`maxage` according to available resources.

### Pre-Conclusion Checklist

- [ ] Recorded the JDK version/vendor and recording mode.
- [ ] Verified whether `VirtualThreadPinned` is enabled and its actual threshold; did not assume defaults if a custom `.jfc` is used.
- [ ] Distinguished event duration from request latency, and pinning from normal blocking.
- [ ] Checked JEP 491 changes for JDK 24+.
- [ ] Distinguished virtual-thread scheduler submit failures from business exceptions.
- [ ] Read events in the context of timestamps, stack traces, CPU, scheduler, resources, and workload intensity.
- [ ] After code changes, re-ran comparative benchmarks/workloads with the same measurement configuration.

## 11. Official Documentation

- [Oracle Java 21: Virtual Threads and JFR Events](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — default state and 20 ms threshold.
- [Oracle Java 24: Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html) — new pinning behavior when using monitors.
- [Oracle Java 26: Virtual Threads and JFR Event Examples](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html) — how to read blocking operations, pinned reasons, and diagnostic actions.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — design and related JFR events.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — `synchronized` improvements starting in JDK 24.
- [`jdk.jfr` package documentation (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — `enabled`, `threshold`, and `stackTrace`.
- [JDK 21 `jfr` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `jfr configure`, `summary`, `metadata`, and `print`.

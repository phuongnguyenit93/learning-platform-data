# 10.8 Comparing Behavior and Tooling Across JDK Versions When Analyzing Virtual Threads

A virtual thread is a `java.lang.Thread` scheduled by the Java runtime onto a smaller set of underlying threads (*carrier/platform threads*). When a virtual thread waits on an unmount-capable operation, its carrier is returned to run other work. Consequently, virtual threads primarily increase **capacity to serve many I/O-waiting tasks**, rather than making individual CPU computations run faster. When diagnosing incidents, the **JDK version running the application** determines the meaning of pinning, available `jcmd` commands, scheduler visibility, and even JSON data types inside thread dumps.

## 1. Objectives and How to Identify the Actual Version

After this lesson, you will be able to: identify key virtual-thread milestones; distinguish blocking, pinning, and lock contention; choose thread dumps, JFR, `jcmd`, or JMX according to the JDK; compare JDK 21–23 results against JDK 24+; and update dump parsers when upgrading to JDK 27.

Before interpreting logs, record the **JDK of the target process**, not only the JDK installed on your analysis workstation:

```bash
java -version
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
```

`<PID>` is the application JVM's PID; replace it with the actual number. `jcmd` typically must run on the same host with sufficient attach permissions and compatibility with the target JVM. Also record the update release (e.g., 21.0.x), JDK vendor, OS, JVM flags, test load, and collection timestamp. Never infer runtime behavior solely from `javac -version`, as an application may be compiled and operated on two different JDKs.

## 2. Quick Comparison Table of JDK Milestones

| Version | Status and Key Behavior to Remember | Diagnostic Tools / Notes to Watch |
| --- | --- | --- |
| **JDK 19** | Virtual threads introduced as a **preview** feature (JEP 425). APIs, implementation, and observability were not yet stable contracts. | Requires `--enable-preview` to compile/run preview API examples; consult JDK 19-specific docs. |
| **JDK 20** | Second preview (JEP 436); still not a permanent API. Pinning from `synchronized` and native/foreign calls remained an issue. | Use tools from the matching JDK 20; do not assume output matches JDK 21 onward. |
| **JDK 21** | **Finalized** under JEP 444; an LTS release. Includes `Thread.ofVirtual()`, `Thread.startVirtualThread(...)`, `Executors.newVirtualThreadPerTaskExecutor()`. Blocking while holding a `synchronized` monitor can pin the carrier; native/foreign calls can also pin. | `jcmd Thread.dump_to_file` (text/JSON), virtual-thread JFR events, and `-Djdk.tracePinnedThreads=full/short` to trace pinning on older releases. |
| **JDK 22–23** | Virtual threads remain a permanent feature; `synchronized`-related pinning limits still essentially apply in HotSpot before JDK 24. | Correlate JFR, thread dumps, and source code per build; JDK 24 scheduler-specific commands are not yet available. |
| **JDK 24** | **JEP 491**: virtual threads blocking inside or waiting on a `synchronized` monitor can release the carrier; monitor-induced pinning is eliminated. Native methods/foreign functions can still pin. | Adds `jcmd Thread.vthread_scheduler`, `Thread.vthread_pollers`, and `jdk.management.VirtualThreadSchedulerMXBean`. Switch to JFR for pinning diagnostics; drop workflows relying on the old `jdk.tracePinnedThreads` flag. |
| **JDK 25–26** | Retains the new behavior from JDK 24; virtual threads do not require preview flags. JFR remains useful for finding remaining pinning causes, especially native/foreign frames. | Continue using full dumps, JFR, the two newer `jcmd` commands, and the scheduler MXBean; verify event names/fields against the exact runtime. |
| **JDK 27** | Continues stable virtual thread support; **tooling compatibility change** in JSON thread dumps: PID, thread ID, and thread counts switch from strings to numbers, and `threadDump.formatVersion = 2` is added. | Legacy parsers/ETL assuming those fields are strings may fail. JFR also changes defaults to redact sensitive info in command-line arguments, properties, and environment variables (JEP 536). |

**Important boundary:** virtual threads became stable in JDK 21; *Structured Concurrency* is a related API with its own separate preview lifecycle (still in preview in JDK 27). Never require `--enable-preview` just to run `Thread.ofVirtual()` on JDK 21+.

## 3. Understanding Carriers, Unmounting, and Pinning by Version

A virtual thread can experience three distinct situations:

1. **Waiting while unmounting:** when waiting on `Thread.sleep`, certain I/O, or virtual-thread-friendly blocking primitives, the runtime saves the virtual thread's state and yields the carrier. Many waiting virtual threads do not imply many blocked OS threads.
2. **Pinning:** the virtual thread cannot release its carrier while waiting. On HotSpot JDK 21–23, blocking inside `synchronized` is a prominent cause; from JDK 24 onward, that monitor case is resolved. Native/foreign frames still require observation.
3. **Lock contention:** tasks compete for the same monitor/lock and must enter the critical section one at a time. JDK 24 reduces *carrier pinning*, **not the mutual exclusion semantics of `synchronized`**. If 100 requests wait on one lock, response times can still degrade even when JFR stops reporting monitor pinning.

Consider this snippet:

```java
synchronized (lock) {
    blockingCall(); // Example: network wait or long sleep
}
```

- **JDK 21–23:** if the virtual thread actually blocks inside that block, the carrier can be held. Prolonged and repeated pinning reduces scalability; JFR `jdk.VirtualThreadPinned` may record it.
- **JDK 24+:** the monitor no longer causes pinning for this kind of blocking. However, if many tasks share the same `lock`, they still queue due to synchronization rules; if `blockingCall` enters native/foreign code, pinning can still occur from that source.
- **Evidence-based fix:** on JDK 21–23, if JFR confirms long, repeated pinning inside `synchronized` blocks doing I/O, consider narrowing the lock scope, moving I/O outside the lock, or using `ReentrantLock` properly. On JDK 24+, analyze lock contention and operation duration first before altering synchronization primitives. Never replace every `synchronized` reflexively.

`jdk.VirtualThreadPinned` does not mean the virtual thread is deadlocked; it reports a wait unable to release the carrier that exceeded the event threshold. Conversely, **zero events does not prove zero problems**: durations may be below threshold, the event may be disabled, the JDK may already have fixed monitor pinning, or test load may not have reproduced it.

## 4. Choosing the Right Tool for the Question

| What You Need to Know | Tool | Version / Interpretation Limits |
| --- | --- | --- |
| Which virtual threads are doing/waiting on what? | `jcmd <PID> Thread.dump_to_file -format=text` or `-format=json` | Available on JDK 21+. Useful for both platform and virtual threads; reflects observations across multiple instants, **not an atomic snapshot**, and does not perform automatic deadlock detection. May omit some virtual threads in certain cases. |
| What are carriers and platform threads running? | `jcmd <PID> Thread.print`, `jstack` | Traditional HotSpot dumps emphasize platform threads and **mounted** virtual threads; do not substitute for dedicated dumps when most virtual threads are unmounted. |
| Where and how long is pinning occurring? | JFR `jdk.VirtualThreadPinned`; JDK 21–23 also has `-Djdk.tracePinnedThreads` | Default JFR threshold is **20 ms** when enabled by default config; pins shorter than the threshold may not appear. On JDK 24+, prefer JFR. |
| Are too many virtual threads starting/terminating? | JFR `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd` | Both events are usually **disabled by default**. Enable selectively; very high traffic can generate massive event volume. |
| Is the scheduler rejecting or failing to schedule tasks? | JFR `jdk.VirtualThreadSubmitFailed` | Generally points to resource pressure or submit/unpark failures; does not mean business exceptions inside individual tasks. |
| Does the scheduler have a large queue, and how many carriers are in use? | `jcmd <PID> Thread.vthread_scheduler` or `VirtualThreadSchedulerMXBean` | **JDK 24+**. These are scheduler metrics, not total business requests or all virtual threads in the JVM. |
| Are many virtual threads waiting on socket/network I/O? | `jcmd <PID> Thread.vthread_pollers` | **JDK 24+**. Poller metrics aid network I/O analysis; they do not measure every wait type (locks, sleep, DB pools, file I/O). |
| How many threads does `ThreadMXBean` see? | `java.lang.management.ThreadMXBean` | Primarily tracks **platform threads**, not a complete tally or control surface for virtual threads. `ThreadGroup.activeCount()/enumerate()` also do not enumerate virtual threads like platform threads. |
| Parsing JSON dumps with internal tooling? | `Thread.dump_to_file` parser | **JDK 27 changes schema to v2**; check field data types and `formatVersion` rather than hardcoding JDK 21–26 string types. |

IDEs and debuggers support virtual threads through the debugging protocol (JDWP/JDI); grouping, filtering, and displaying thousands of virtual threads depends on the **IDE/debugger version** and JVM, not just the Java API. When counts look unusual, cross-check with JFR and dumps instead of treating a single debugger view as authoritative.

## 5. Repeatable Incident Investigation Workflow

### Step 1 — Lock Down Environment and Symptoms

Record the Java runtime version, OS, PID, JVM flags, CPUs visible inside the container, workload type (I/O vs. CPU), error rate, p95/p99 latency, connection pools, and downstream resource limits. Distinguish: dropping throughput, rising latency, high CPU, lock stalls, exhausted connections, or excessive waiting tasks. Virtual threads do not replace connection pools, semaphores, or outbound rate limits.

### Step 2 — Take the Appropriate Thread Dump

```bash
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
jcmd <PID> Thread.print
```

In practice you may need absolute output paths and must ensure the destination directory exists and the process has write permission. Use text dumps for quick stack reading and JSON for grouping/filtering by name, state, thread container, and frames. Take several samples spaced apart while reproducing to see whether stacks advance or remain frozen; never merge separate samples into a fake single snapshot.

**How to read the results:**
- Numerous `WAITING`/`TIMED_WAITING` stacks on sockets, queues, or `park` can represent normal waiting. Correlate with downstream timings and request traces before declaring a stall.
- Seeing only a handful of carriers in `Thread.print` does not mean the application has only that many virtual threads; most may be unmounted.
- The dedicated dump does not perform deadlock detection automatically. Lock investigations also require lock ownership edges, acquisition ordering, application logs, and proper detection tools.
- `threadCount` in JSON may exceed the length of the `threads` array if the dump omits some virtual threads; do not use `threads.length` as an absolute total.

### Step 3 — Enable and Read the Right JFR Events

```bash
jcmd <PID> JFR.start name=vt settings=profile
# Reproduce the condition, then:
jcmd <PID> JFR.dump name=vt filename=vt.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt.jfr
```

These commands are template syntax for a HotSpot JVM with JFR; check `jcmd <PID> help JFR.start` on other tools or distributions. When virtual thread lifecycles are needed, create a custom JFR configuration enabling `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd`; both are typically disabled by default. In JDK 26+, pinning events can include fields such as `blockingOperation` and `pinnedReason`: inspect the actual recording schema instead of writing parsers that assume identical fields across all JDK generations.

On JDK 21–23, you can run separately with `-Djdk.tracePinnedThreads=full` or `short` to print stacks on pinning; this fits tooling of that era. On JDK 24+, use JFR instead of the removed legacy flag.

### Step 4 — Inspect the Scheduler on JDK 24+

```bash
jcmd <PID> Thread.vthread_scheduler
jcmd <PID> Thread.vthread_pollers
```

`VirtualThreadSchedulerMXBean` (`jdk.management` module, since JDK 24) exposes metrics such as `getParallelism()`, `getPoolSize()`, `getMountedVirtualThreadCount()`, and `getQueuedVirtualThreadCount()`; target parallelism can be adjusted via JMX if permitted. `parallelism` is the target carrier count for the scheduler, not a limit on existing virtual threads. By default, the scheduler typically bases this on available processors; `jdk.virtualThreadScheduler.parallelism` is an important setting to record when comparing runs.

**Combined interpretation:** a growing scheduler queue alongside saturated CPU can indicate many CPU-heavy/non-yielding tasks; a growing queue in JDK 21–23 paired with long pinning can indicate a shortage of free carriers. From JDK 24+, if monitor pinning disappears yet latency remains high, inspect lock contention, database pools, socket limits, file descriptors, native frames, and downstreams. Never raise parallelism as your first move before identifying the bottleneck.

### Step 5 — Compare the Same Workload Across JDKs

Keep source code, data, resource configuration, worker/connection counts, warmup duration, and measurement methodology constant; vary only the runtime whenever possible. Compare: lock wait time, p95/p99, throughput, CPU, active carrier count, scheduler queue, JFR pinning, and connection counts. Archive `.jfr` files, dumps, PID/JDK build, and configs for reproducibility. Changing JDK, framework, and DB connectivity simultaneously makes it impossible to attribute metric shifts solely to virtual threads.

## 6. Runnable Example: Verifying Virtual Threads on JDK 21+

Save the file **`VirtualThreadProbe.java`**:

```java
import java.util.concurrent.Executors;

public class VirtualThreadProbe {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            boolean virtual = executor
                    .submit(() -> Thread.currentThread().isVirtual())
                    .get();
            System.out.println("virtual=" + virtual);
        }
    }
}
```

Compile and run with **JDK 21 or later**, without `--enable-preview`:

```bash
javac VirtualThreadProbe.java
java VirtualThreadProbe
```

Exact stdout:

```text
virtual=true
```

Explanation: the executor creates one virtual thread per task; inside the task, `Thread.currentThread()` returns the executing virtual thread, so `isVirtual()` is `true`. `Future.get()` waits for the result; `try-with-resources` closes the executor cleanly. `newVirtualThreadPerTaskExecutor()` **is not a pool that reuses virtual threads**. On JDK 19/20, examples using preview APIs need the compiler/runtime of that exact version plus `--enable-preview`; do not treat JDK 21 commands as verbatim instructions for preview releases.

## 7. Example Comparing Pinning on JDK 21–23 vs. JDK 24+

Save the file **`PinningDemo.java`**:

```java
public class PinningDemo {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().start(() -> {
            synchronized (MONITOR) {
                try {
                    Thread.sleep(300);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        });

        worker.join();
        System.out.println("done");
    }
}
```

Compile with JDK 21+, then run on each runtime you want to compare (compile with a compatible target, e.g., `javac --release 21 PinningDemo.java` when using a newer compiler). Program stdout does not depend on version:

```text
done
```

To capture JFR for a test run:

```bash
javac PinningDemo.java
java -XX:StartFlightRecording:filename=pinning.jfr,dumponexit=true PinningDemo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

- On **JDK 21–23**, `Thread.sleep(300)` inside a monitor can pin the virtual thread's carrier; if the recording enables the event, duration meets the threshold, and runtime behavior matches expectations, you can observe `jdk.VirtualThreadPinned`.
- On **JDK 24+**, the same `synchronized` block no longer creates monitor-induced pinning; do not expect that event simply because a monitor is present. Native/foreign code in other workloads can still pin.
- This is a **mechanism test**, not a throughput benchmark: a single virtual thread proves nothing about application-level performance gains. To benchmark, use many independent tasks, fixed measurement conditions, and inspect both JFR and metrics.

If real traffic continuously contends on the same monitor, upgrading to JDK 24+ can eliminate carrier pinning without eliminating the lock wait queue. You must measure lock wait and scheduler behavior together.

## 8. Major Change in JDK 27: JSON Thread Dump v2

From **JDK 21 through JDK 26**, JSON thread dumps commonly represented PID/thread identifiers and thread counts as **strings**. **JDK 27** switches these fields to **numbers**, while adding `threadDump.formatVersion` set to `2`. Minimal structural snippets for illustration (not full dump files):

**Before JDK 27 (legacy style, excerpt):**

```json
{
  "threadDump": {
    "processId": "1234",
    "threadContainers": [
      {
        "threadCount": "1",
        "threads": [{"tid": "8", "name": "main"}]
      }
    ]
  }
}
```

**From JDK 27 (v2 style, excerpt):**

```json
{
  "threadDump": {
    "formatVersion": 2,
    "processId": 1234,
    "threadContainers": [
      {
        "threadCount": 1,
        "threads": [{"tid": 8, "name": "main"}]
      }
    ]
  }
}
```

When building parsers and dashboards:

1. Read `formatVersion` if present; if absent, treat it as likely legacy format while still validating the actual structure.
2. Support both strings and numbers for PID, `tid`, `threadCount`, `owner`, `carrier`, and related identifier fields. Use sufficiently wide numeric types for arithmetic and a canonical representation when joining keys/indexes.
3. Do not assume the length of `threads` equals `threadCount`; thread container structures and unsampled subsets can cause them to differ.
4. Test parsers against fixtures from JDK 21/24/26 **and** JDK 27. Never patch real JSON files via text find-and-replace: that easily corrupts data types or other text values.
5. JDK 27 also enables **JFR in-process data redaction** by default for sensitive data such as command-line arguments and initial environment/system property values. When comparing old and new recordings, missing fields due to redaction must not be misinterpreted as a change in virtual-thread behavior.

This milestone affects **observability data formats**, not the definition of `Thread.isVirtual()` or virtual-thread scheduling semantics.

## 9. Four Common Diagnostic Scenarios

### Scenario A — Same Application Has Pinning Events on JDK 21, None on JDK 24

**Hypothesis:** blocking inside `synchronized` used to pin carriers; JEP 491 eliminated that cause. **Verification:** same load, same JFR config, compare pinning stacks/counts and scheduler/latency metrics. **Do not jump to conclusions:** if latency remains high, measure lock contention and downstream durations; disappearing events do not mean all waits disappeared.

### Scenario B — JDK 26 Shows High Scheduler Queue While `Thread.print` Shows Few Threads

**Hypothesis:** many virtual threads are unmounted or waiting to be scheduled; `Thread.print` captures only platform threads and mounted virtual threads at snapshot time. **Verification:** `Thread.dump_to_file`, `Thread.vthread_scheduler`, `Thread.vthread_pollers`, JFR, and request traces. **Action:** determine whether the bottleneck is CPU, I/O, downstream, synchronization, or native code before raising target parallelism.

### Scenario C — `ThreadMXBean.getThreadCount()` Is Small While Tens of Thousands of Requests Are Open

**Hypothesis:** the metric reflects only platform threads; virtual threads are not fully accounted for in this MXBean. **Verification:** virtual-thread dumps, business metrics, and open request counts. **Action:** never rely solely on `ThreadMXBean` to alert on virtual thread counts; pick telemetry suited to the goal.

### Scenario D — Dump Reader Works on JDK 26 but Breaks After Upgrading to JDK 27

**Hypothesis:** the parser expects `tid`/`processId` as strings while v2 dumps return numbers. **Verification:** inspect `formatVersion` and actual JSON types. **Action:** update the parser to support both v1 and v2 schemas with fixtures and regression tests; retain runtime version metadata in every diagnostic artifact.

## 10. Misconceptions to Avoid

- **"Blocking equals pinning."** False. Virtual threads are *designed to block* and release their carriers. Only when the carrier cannot be released while waiting is it pinning in this diagnostic sense.
- **"JDK 24 removes `synchronized` or automatically eliminates lock contention."** False. Monitor handling changed to avoid pinning the carrier, not mutual exclusion rules.
- **"No `jdk.VirtualThreadPinned` means no bottleneck."** False. Account for JFR thresholds/configs, real load, JDK version, and other bottleneck types.
- **"`jstack`, `Thread.print`, and `ThreadMXBean` see all virtual threads."** False. They do not replace dedicated dumps covering unmounted virtual threads.
- **"Every virtual thread maps to one OS thread."** False. Carriers are reused; when a virtual thread unmounts, it occupies no carrier.
- **"High thread counts must be capped with a virtual-thread pool."** False. Use one virtual thread per task; use `Semaphore`, connection pools, and downstream limits to bound real resources.
- **"Increasing scheduler parallelism guarantees higher throughput."** False. If the bottleneck is CPU, connections, locks, or external services, it may not help and must be measured.
- **"Use preview flags on every version."** False. Preview flags applied only to JDK 19/20 for virtual threads; from JDK 21 onward, the feature is permanent. Structured Concurrency's preview status is separate.
- **"JSON thread dumps have a fixed schema."** False. JDK 27 changes numeric fields and adds `formatVersion`; parsers must handle multiple versions.

## 11. Pre-Conclusion Checklist

- [ ] Recorded the application's **runtime JDK + build/vendor**, PID, OS, CPU quota, and JVM options.
- [ ] Confirmed whether the runtime is JDK **21–23** or **24+** before blaming `synchronized` pinning.
- [ ] Distinguished **blocked, unmounted, pinned, lock contention**, CPU saturation, and downstream waits.
- [ ] Used `Thread.dump_to_file` to inspect virtual threads rather than `Thread.print`/`ThreadMXBean` alone.
- [ ] Captured JFR with the right events and checked `jdk.VirtualThreadPinned` thresholds; did not treat absent events as absolute proof.
- [ ] On JDK **24+**, used scheduler/pollers commands or the MXBean when queue/carrier visibility was needed.
- [ ] On **JDK 27**, verified JSON parsers handle `formatVersion=2` and numeric fields; accounted for JFR redaction.
- [ ] Correlated stacks, JFR, metrics/traces, and measured load before recommending lock changes, scheduler tuning, or a JDK upgrade.

## 12. Version-Specific Reference Documentation

- JEP 425 — Virtual Threads (JDK 19 preview): https://openjdk.org/jeps/425
- JEP 436 — Virtual Threads (JDK 20 second preview): https://openjdk.org/jeps/436
- JEP 444 — Virtual Threads (JDK 21 final): https://openjdk.org/jeps/444
- JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24): https://openjdk.org/jeps/491
- Oracle JDK 21, Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Oracle JDK 26, Virtual Threads and diagnostic tools: https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html
- Oracle JDK 26, `jcmd` command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
- Oracle JDK 24 Release Notes (scheduler MXBean, `jcmd` pollers/scheduler): https://www.oracle.com/java/technologies/javase/24-relnote-issues.html
- Oracle JDK 27 Release Notes (JDK-8381002 and JFR redaction): https://www.oracle.com/java/technologies/javase/27-relnote-issues.html
- JDK 27 JSON Thread Dump Format: https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/com/sun/management/doc-files/threadDump.html

**Rule of practice:** always anchor every conclusion to **JDK + tool version + observed evidence**. A dump or JFR file that "looks different" after a JDK upgrade may reflect scheduler changes, capture changes, or schema changes—analyze those three possibilities separately before blaming application code.
# Java Flight Recorder for Thread Park, Lock, and Allocation

## 1. Why Use JFR When Diagnosing Java Concurrency?

A multithreaded program can be slow even when CPU usage does not reach 100%: threads may be waiting for a lock, waiting for a signal, waking up too frequently, allocating objects heavily and increasing GC, or bottlenecked on a `synchronized` block. **Java Flight Recorder (JFR)** records events inside the JVM over time, helping correlate *which thread*, *what event occurred*, *when*, *how long it took*, and *which stack trace was involved*.

JFR is built into modern JDKs, including Java 17+. It can record data while the application is running, producing a `.jfr` file for analysis with the `jfr` command-line tool or Java Mission Control (JMC). JFR is suitable for practical diagnostics because its overhead is typically low with appropriate settings, but **no configuration guarantees zero overhead**. Events with stack traces, very low thresholds, or detailed allocation tracking can still consume significant resources.

The scope of this lesson is general Java/JVM concurrency, independent of any application framework.

After this lesson, you should be able to:

1. Distinguish **park**, **Java monitor contention**, **`Object.wait()`**, and **allocation** using the appropriate JFR event types.
2. Create a recording on Java 17+, and read its timeline, durations, and stack traces without over-interpreting them.
3. Use JFR to narrow down the causes of contention and allocation pressure, then verify them with other measurements/evidence.
4. Tune the recording scope to avoid skewing the workload or collecting too many events.

## 2. What Does JFR Store? Events, Time, and Stack Traces

JFR operates on an **event** model. Depending on the event type, a record may include a start time, duration, thread name/ID, involved class/object, statistical information, and a stack trace. Not every event contains all fields.

There are two types to distinguish:

- **Duration event:** describes an activity that spans a period of time, such as `jdk.ThreadPark` or `jdk.JavaMonitorEnter` when contended. An event is only recorded if it is enabled and meets the corresponding threshold/configuration. A long duration means the thread spent that amount of time in that state; **it does not mean the thread was consuming CPU throughout that period**.
- **Sample/statistics event:** samples or collects statistics at specific points/intervals, such as `jdk.ObjectAllocationSample` or `jdk.ThreadAllocationStatistics`. This data is **not a complete list of every allocation** or an instantaneous count of every memory write.

A useful recording must cover the **time window when the issue actually occurs**. If it starts too late, expires too early, or has a threshold higher than the event duration, JFR may fail to capture the desired signal. Conversely, the absence of events does not automatically prove there is no contention.

### Commonly Used Tools

| Tool | Role |
| --- | --- |
| `jcmd <pid> JFR.start ...` | Start a recording for a running JVM, if attach permissions allow |
| `jcmd <pid> JFR.check` | Check the recordings of the target JVM |
| `jcmd <pid> JFR.dump ...` | Write a recording snapshot to a `.jfr` file |
| `jfr summary file.jfr` | View event types, counts, and recording information |
| `jfr print --events ... file.jfr` | Print specific events, including time/thread/stack when available |
| Java Mission Control | Visually analyze timelines, threads, locks/parks, and allocation distribution |

**Version note:** syntax and feature interfaces may evolve across JDK releases. For example, `jfr view` is available in newer JDKs and should not be assumed to exist in Java 17; `jfr summary` and `jfr print` are the appropriate choices for Java 17.

## 3. Choosing the Right Events for Park, Lock, and Allocation

| JFR Event | What Is Observed? | Conclusions You Can Draw | What Not to Conclude Immediately |
| --- | --- | --- | --- |
| `jdk.ThreadPark` | Thread parked via `LockSupport` and synchronizers that use park | Thread waited/parked; find the waiting call path | Park always means lock contention or deadlock |
| `jdk.JavaMonitorEnter` | **Contended** entry into a `synchronized` Java monitor | Thread waited to enter a monitor; find where the monitor is held and awaited | Every `synchronized` entry emits an event |
| `jdk.JavaMonitorWait` | Call to `Object.wait()` on a monitor | Thread waited for notification/timeout, having released that monitor while waiting | This is wait time to *enter* `synchronized` |
| `jdk.ObjectAllocationSample` | Allocation sample on the Java heap, with object type/stack when available | Call paths likely causing heavy allocation | Exact count of every allocated object or byte |
| `jdk.ThreadAllocationStatistics` | Statistics of bytes allocated by a thread at collection intervals | Which threads have sharply rising cumulative allocation | Individual allocations or the entire cause of GC |
| `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB` | Events related to TLAB/outside-TLAB allocation when enabled | Helps investigate allocation paths in deeper detail | Low-overhead counter of all objects by default |

**Event names are technical JFR names on the corresponding HotSpot/JDK; always verify the actual event list of the JVM in use.** Events also depend on JVM support and whether they are enabled in the configuration.

### 3.1. `jdk.ThreadPark`: Thread Park/Wait Time

`LockSupport.park()` or `parkNanos()` can pause a thread until it is unparked (`unpark`), interrupted, times out (for timed variants), or returns due to a *spurious wakeup*. `java.util.concurrent` constructs such as certain wait paths of `ReentrantLock`, `Semaphore`, `CountDownLatch`, and `BlockingQueue` may use park underneath.

The `jdk.ThreadPark` event reveals the wait duration, thread, and associated stack trace. The stack may start at `LockSupport.park`, pass through AQS (`AbstractQueuedSynchronizer`), and reach application code calling `await()`/`take()`/`lock()`.

**Contextual interpretation:**

- An idle thread pool worker waiting for tasks and parking for seconds can be **normal behavior**.
- A producer/consumer waiting on an empty or full queue can reflect backpressure or throughput imbalance.
- A request thread parking for a long time at `ReentrantLock.lock()` can indicate lock waiting; you need to correlate who holds the lock and when it happens.
- `Thread.sleep()` is typically observed via **`jdk.ThreadSleep`**, not `jdk.ThreadPark` by default.

A `WAITING`/`TIMED_WAITING` state in a thread dump is also not enough to call something a bug: you must determine **the reason for waiting** and whether it lies on the request-serving path.

### 3.2. `jdk.JavaMonitorEnter`: Waiting to Enter `synchronized`

A thread entering `synchronized (monitor)` must acquire ownership of the monitor. When the monitor is already held by another thread and entry is contended, JFR can record `jdk.JavaMonitorEnter` if the event is enabled and the wait duration exceeds the threshold.

The data can show the **event thread** (the blocked thread), **monitor class**, duration, the stack of the site requesting the monitor, and **previous owner** information when provided by the JVM. However, the waiting thread's stack **does not by itself tell you which exact code in the monitor-holding thread caused the slowdown**. Additional thread dumps or concurrent events may be needed to identify long critical sections, I/O, or callbacks executed under the monitor.

This measures **waiting to *enter* a monitor**. A long-running `synchronized` block with no other threads contending for it may not produce any noticeable `jdk.JavaMonitorEnter` events. To measure the **hold time** of a monitor, you need additional instrumentation/benchmarks or profiling of the relevant path; do not treat the enter event duration as the total time the monitor was held.

### 3.3. `jdk.JavaMonitorWait`: `Object.wait()` Is Not Enter Contention

When a thread calls `Object.wait()` while holding a monitor, it releases **that monitor** and waits for `notify`/`notifyAll`, a timeout, or an interrupt. Before `wait()` returns normally or due to an interrupt, the thread must reacquire that monitor. The `jdk.JavaMonitorWait` event relates to the wait duration in this operation; it **does not mean** the thread was blocked simply trying to enter a `synchronized` block.

For example, a consumer waiting for a condition via `wait()` may be waiting legitimately. You should check the condition loop (`while (!condition) wait()`), the thread performing `notify`/changing the condition, timeouts, interruption, and the risk of lost notifications due to flawed design.

**Important distinction:** `Condition.await()` on a `ReentrantLock` is not `Object.wait()`; many implementations use `LockSupport` and show up as park events. Do not attribute every `WAITING` state to `jdk.JavaMonitorWait`.

### 3.4. Allocation: Where Objects Are Created and Its Impact on Concurrency

Allocation is very fast on many HotSpot execution paths, but an excessively high object creation rate can increase memory traffic, GC overhead, allocator contention, or cache pressure. Request-handling threads can be significantly stalled by GC or collection workloads even if they never contend on a Java monitor.

- **`jdk.ObjectAllocationSample`:** used to find notable object types and call paths. This is sampling; event counts depend on the sampling algorithm, configuration, and workload. Do not read each sample as "one single object in the system."
- **`jdk.ThreadAllocationStatistics`:** cumulative bytes allocated per thread at collection points; take the difference between appropriate samples to estimate allocation rate, accounting for thread lifecycle and time intervals. Do not use a single snapshot to infer a rate.
- **TLAB events:** thread-local allocation buffers (TLABs) eliminate most contention on the fast allocation path. In-new-TLAB/outside-TLAB events can help examine allocation behavior in greater depth, but you must evaluate overhead and sampling/configuration and must not treat them as a complete object inventory without verifying semantics.
- **GC events:** `jdk.GarbageCollection`, `jdk.GCPhasePause`, and other GC events (depending on the collector/JDK) add pause durations and GC counts; timeline correlation is more meaningful than concluding "allocation = lock contention."

Not every object in Java source code is actually allocated on the heap: JIT escape analysis/scalar replacement can eliminate some allocations. Samples only reflect runtime activity that occurred during the recording, not a count of `new` expressions in the source.

## 4. Runnable Hands-On on Java 17+: Actively Generating Three Signals

The example below creates **a JFR recording directly inside the JVM** using the `jdk.jfr` API, then triggers the following scenarios:

1. One thread parks for about 150 ms using `LockSupport.parkNanos`.
2. One thread holds a Java monitor while another thread attempts to enter that monitor.
3. One thread performs `Object.wait(120)`.
4. The main thread allocates many `byte[]` arrays to produce an observable allocation workload.

We enable events with small thresholds for this hands-on exercise. In production, thresholds must be chosen carefully to control overhead and focus on significant latency tails.

**File: `JfrThreadDiagnosticsDemo.java`**

```java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

public final class JfrThreadDiagnosticsDemo {
    private static final Object MONITOR = new Object();
    private static final Object WAIT_MONITOR = new Object();

    // Keep the reference escaping the loop so the JIT cannot easily eliminate allocations.
    private static volatile byte[] retained;

    private static void sleepInsideMonitor() {
        synchronized (MONITOR) {
            try {
                Thread.sleep(300);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("thread-lock-allocation.jfr");

        try (Recording recording =
                new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("thread-lock-allocation");
            recording.enable("jdk.ThreadPark")
                    .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.JavaMonitorEnter")
                    .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.JavaMonitorWait")
                    .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.ObjectAllocationSample");
            recording.enable("jdk.ThreadAllocationStatistics")
                    .withPeriod(Duration.ofMillis(100));

            recording.start();

            Thread parker = new Thread(() ->
                    LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(150)),
                    "park-demo");

            CountDownLatch holderEntered = new CountDownLatch(1);
            Thread holder = new Thread(() -> {
                synchronized (MONITOR) {
                    holderEntered.countDown();
                    try {
                        Thread.sleep(300);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }, "monitor-holder");

            Thread contender = new Thread(() -> {
                try {
                    holderEntered.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (MONITOR) {
                    // Can only enter after holder releases the monitor.
                }
            }, "monitor-contender");

            Thread waiter = new Thread(() -> {
                synchronized (WAIT_MONITOR) {
                    try {
                        WAIT_MONITOR.wait(120);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }, "object-wait-demo");

            parker.start();
            holder.start();
            contender.start();
            waiter.start();

            parker.join();
            holder.join();
            contender.join();
            waiter.join();

            for (int i = 0; i < 20_000; i++) {
                retained = new byte[4096];
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Saved: thread-lock-allocation.jfr");
    }
}
```

Compile and run commands:

```bash
javac JfrThreadDiagnosticsDemo.java
java JfrThreadDiagnosticsDemo
```

Stdout from the program (when run successfully in a writable directory):

```text
Saved: thread-lock-allocation.jfr
```

The `thread-lock-allocation.jfr` file is created in the current working directory unless you change the `output` path. The duration figures and event counts in the recording are **non-deterministic** due to scheduling, JIT, sampling, and thresholds. For instance, if `contender` is not scheduled to run before `holder` releases the monitor, the recording may not contain the intended monitor contention event; rerun or add test synchronization when you need to demonstrate a rare scenario.

**Mechanism breakdown:**

- `parker` has a call stack leading to `LockSupport.parkNanos`, corresponding to `jdk.ThreadPark` if the event meets the threshold.
- `holder` holds `MONITOR` while `contender` waits; this is a **contended entry** corresponding to `jdk.JavaMonitorEnter`. Calling `Thread.sleep` in `holder` does not release the monitor, which can increase `contender`'s wait time.
- `waiter` uses `Object.wait(timeout)` and releases `WAIT_MONITOR` while waiting; this is an example of `jdk.JavaMonitorWait`, not `contender`-style entry contention.
- `retained` is a `volatile` reference written on every iteration; the goal is to make the array escape simple computation so the benchmark does not just measure code eliminated by the JIT. Allocation sampling **does not guarantee** an event for every array creation.
- `recording.enable(...).withThreshold(...)` sets a specific threshold for duration events; `ThreadAllocationStatistics` uses a period to collect statistics. With the 1 ms learning setting, the number of events may be higher than with default settings.
- `try (Recording ...)` ensures the recording is closed after dumping. Stdout is printed only after all threads finish and the file is dumped successfully.

This exercise does not attempt to fully simulate a production deadlock or GC pause. In a real program, you should not intentionally hold a monitor across `Thread.sleep`; this exists solely to produce a clear contention signal.

### Reading Results via CLI

First, check which event types the recording contains:

```bash
jfr summary thread-lock-allocation.jfr
```

Next, filter for events related to thread/monitor waiting:

```bash
jfr print --stack-depth 24 --events jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.JavaMonitorWait thread-lock-allocation.jfr
```

And analyze the allocation group:

```bash
jfr print --stack-depth 24 --events jdk.ObjectAllocationSample,jdk.ThreadAllocationStatistics thread-lock-allocation.jfr
```

These commands can be run with the `jfr` utility from JDK 17+. Actual output depends on the JDK/OS, sampling rate, thread scheduling, and recording timing, so **there is no single fixed JFR stdout to copy verbatim**. If machine-readable output is needed, `jfr print --json --events ...` outputs JSON depending on the capabilities of your `jfr` version; avoid drawing conclusions from a field that is not guaranteed to exist on all JDKs.

If expected events are missing, check in order:

1. Did the recording cover the exact time window of the operation?
2. Is the event supported by the JVM and enabled? Did the threshold/period filter out short events?
3. Was the scenario actually triggered—for example, real contention rather than entering `synchronized` when the lock was free?
4. Are you reading the right dump file, the right JVM/PID, and the right thread names?
5. For allocation samples, was the workload large enough to be sampled, or did the JIT eliminate the allocations?

## 5. Recording JFR on a Running JVM: Using `jcmd`

In real applications, you usually do not modify source code just to create a recording. If you have access to the JVM process and JDK tools, find the PID:

```bash
jcmd -l
```

Start a bounded-duration recording (e.g., 60 seconds) with `profile` settings:

```bash
jcmd <pid> JFR.start name=triage settings=profile duration=60s filename=triage.jfr
```

Check status:

```bash
jcmd <pid> JFR.check
```

You can also proactively dump data while recording:

```bash
jcmd <pid> JFR.dump name=triage filename=triage-now.jfr
```

Read the resulting file:

```bash
jfr summary triage-now.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.ObjectAllocationSample triage-now.jfr
```

In the commands above, **`<pid>` is a placeholder** to replace with the actual PID. File paths may be resolved relative to the target JVM's working directory/permissions; when diagnosing a remote/containerized service, verify where the file is actually saved and whether you have access to it. When using `duration`, the recording stops automatically as configured; only use `JFR.dump` after confirming the file exists and contains data for the target window.

`settings=profile` typically provides more detail than `settings=default`, at the cost of potentially higher overhead. Avoid leaving detailed recording running indefinitely just to catch a rare event. For special requirements, use a verified `.jfc` JFR configuration file for the target JVM (customizing events, thresholds, stack traces, sampling/periods) and evaluate overhead before long-term use.

### Using Java Mission Control

Open the `.jfr` file in Java Mission Control, then:

1. Select the exact timeline range coinciding with the latency spike or incident.
2. Inspect thread activity, Java monitor blocking, socket/file I/O, allocation, and GC sections according to your JMC version's UI.
3. Identify recurring threads/stacks during long waits; filter by thread name, duration, monitor class, and application methods.
4. Correlate with CPU/GC/throughput/latency charts rather than simply sorting events by duration and labeling every long wait a bug.
5. Compare before and after changes under the same workload and recording settings.

JMC page names and UI labels vary across versions, but the core principle of **timeline + thread + stack + event type** remains constant.

## 6. Investigation Workflow: From Symptom to Root Cause

Suppose a multithreaded Java application experiences increased request latency. A disciplined workflow:

### Step 1 — Identify the Symptom and Time Window

Record when latency spikes, along with throughput, request volume, CPU, heap/GC, live thread count, and other anomalies. The recording must cover that window; a recording taken while the system is idle proves nothing about behavior under high load.

### Step 2 — Find the Corresponding Wait Type

- Many long-duration `jdk.JavaMonitorEnter` events with the same monitor class and stack: likely **monitor contention**; inspect the critical section, owning thread, I/O, or callbacks inside `synchronized`.
- Many `jdk.ThreadPark` events at `ReentrantLock.lock` or `Condition.await`: inspect the synchronizer wait path, queue, wakeup conditions, fairness, and load data.
- Many parks on an idle worker queue during low load: usually **legitimate waiting for work**; do not try to optimize this away.
- Long `jdk.JavaMonitorWait`: check the wait condition, notifications, timeouts, and the producer–consumer contract.
- Sharp rise in allocations/samples followed by increased GC pauses/frequency: may be an **allocation pressure** issue affecting latency, which does not mean all threads are blocked on locks.

### Step 3 — Inspect Stacks and Involved Parties

Find the application frame **calling into** the waiting API, rather than stopping at `Unsafe.park`/`LockSupport.park` or AQS internals. If `JavaMonitorEnter` provides `previousOwner`, use it as a clue, then cross-reference the timeline, thread dumps, and critical section code. JFR data can lack details due to sampling, thresholds, JVM version, and context; **never construct a causal chain from a single event**.

Example:

```text
request-thread-17
  -> OrderCoordinator.process()
  -> ReentrantLock.lock()
  -> LockSupport.park()                 [jdk.ThreadPark]

worker-thread-4
  -> CacheRefresher.refresh()
  -> synchronized (sharedMonitor)      [holds monitor]

request-thread-22
  -> synchronized (sharedMonitor)      [jdk.JavaMonitorEnter]
```

The diagram above is an **illustrative scenario**, not actual JFR output. The first two wait paths do not by themselves prove the same lock or a deadlock. Only after identifying the exact object/lock, holder/waiter, and dependency cycle can you reach a definitive conclusion.

### Step 4 — Verify with Independent Measurements

- For monitors: measure critical section duration, reduce unnecessary work inside the lock, and verify whether contention drops.
- For parks: check the data source the thread is waiting on, actual contention on `ReentrantLock`, queue size, signal rate, or backpressure issues.
- For allocation: use allocation profiles by object type/stack, reduce allocations on the hot path, and measure GC/throughput; avoid relying solely on a drop in sample count caused by JIT or a different profile.
- When suspecting a deadlock, take a thread dump/`jcmd <pid> Thread.print` to cross-check; some wait cycles involving external resources or custom protocols may not appear as a simple monitor deadlock.

### Step 5 — Validate After Changes

Record with the same JFR settings, same load, and same observation window; compare wait-time distribution by thread/method, count of events exceeding the threshold, bytes allocated per interval, GC pauses, and **system latency/throughput**. A drop in event count does not mean optimization succeeded if thresholds, run duration, or workload changed.

## 7. Understanding Thresholds, Sampling, and Overhead

### Duration Event Thresholds

An event may only be recorded if its duration is large enough. For example, a 20 ms threshold (a commonly seen setting, not an immutable default) filters out 2 ms waits, even though millions of short waits can degrade overall throughput. When investigating those, you can lower the threshold for a short recording, while monitoring overhead and total event volume.

Conversely, a tiny threshold on a very busy production system can generate massive data volumes, skew benchmarks, and increase I/O/CPU/memory overhead. Choose thresholds based on the question you are investigating: tail latency, total wait time, or a specific hotspot.

### Allocation Sampling

`jdk.ObjectAllocationSample` is a **sample**, not every `new`. Do not treat `count(events)` as the total number of objects; if the event includes weight/estimate fields, read the exact semantics for your JFR version rather than summing blindly. Differences between two recordings can come from JIT warmup, sampling, and throughput. To estimate bytes/thread, look at `jdk.ThreadAllocationStatistics` over an appropriate interval and correlate with GC/runtime counters.

### Stack Traces and Time Frames

Some events may have stack traces disabled to reduce overhead; if application frames are missing, check the recording settings instead of assuming the JVM does not know the event source. Thread names can be changed or reused across lifecycles; use timestamps and accompanying thread identifiers when correlating. A 5-second park event does not mean the CPU was busy for 5 seconds; a method appearing in many stack samples does not prove it held a lock for the entire duration.

### Recording Profiles

JFR is a relatively low-overhead diagnostic tool when configured appropriately. **Exact overhead depends on recording settings, event frequency, stack trace types, JVM, workload, and hardware.** Balance detail against noise; avoid using very heavy profiles in experiments comparing a few percent of performance without measuring profiler overhead.

## 8. Common Misinterpretations

**Mistake 1: “There are many `ThreadPark` events, so the system must be deadlocked.”**

False. Idle thread pools, blocking queues, latches, condition waits, and rate limiters can all park legitimately. A deadlock requires evidence of an unrecoverable dependency cycle, not just long durations.

**Mistake 2: “No `JavaMonitorEnter` events means no lock contention.”**

False. The event might be disabled, the threshold too high, JFR might have missed the window, or contention might be on `ReentrantLock`/non-monitor synchronizers. You must select both park and monitor events appropriately.

**Mistake 3: “`JavaMonitorEnter` duration equals the time a thread held the monitor.”**

False. It describes how long **the entering thread was blocked**. The monitor hold time may overlap with that duration, but they are not equivalent—especially when multiple waiters compete, scheduling delays occur, or multiple acquire/release cycles happen.

**Mistake 4: “`JavaMonitorWait` is the same as `LockSupport.park`.”**

False. `Object.wait()` belongs to the monitor API; `LockSupport` is the park primitive. Synchronizers built on AQS may use park without necessarily calling `Object.wait()`.

**Mistake 5: “200 allocation samples means only 200 objects were created.”**

False. JFR uses sampling, and the sampling rate/configuration affects event counts. Many allocations do not emit individual events, and the JIT can also eliminate heap allocations altogether.

**Mistake 6: “High allocation means we must switch to object pooling immediately.”**

Unwarranted. Object pooling increases lifecycle complexity, risk of contention/memory retention, and can make GC harder to optimize. You must verify that the allocation is on a hot path and that the change actually improves latency/throughput.

**Mistake 7: “JFR should always produce the exact same event count every time the demo runs.”**

False. JIT, scheduling, GC, recording timing, thresholds, and sampling make counts non-deterministic. What stays constant in the demo is the scenario-generation logic and the file-dumping command upon a successful run.

**Mistake 8: “A `WAITING` thread cannot be a bottleneck.”**

Not necessarily. A waiting thread can be normal or it can be on the critical path; what matters is **what** it is waiting on, **who can unblock it**, and the impact on SLAs. Thread state is a starting point, while JFR provides the context and timeline for deeper investigation.

## 9. Practical Checklist

Before recording:

- Identify the right JVM/PID/JDK; ensure permissions and sufficient disk space for `.jfr` files.
- Choose a recording window that overlaps the issue or reproduces the workload.
- Select events: `ThreadPark` for park/AQS, `JavaMonitorEnter` for contended `synchronized`, `JavaMonitorWait` for `Object.wait`, and allocation samples/statistics for allocation.
- Check thresholds, periods, stack traces, and sampling so they are just enough to answer the question.

During analysis:

- Examine thread, stack, start time, duration, and event class; apply the **exact semantics** of each event type.
- Correlate with CPU, GC, queues, throughput, latency, and code holding/acquiring locks.
- Verify the root cause with thread dumps, profilers, instrumentation, or appropriate benchmarks.
- Distinguish **legitimate** waiting of idle workers from waiting **on the critical path** of a request.

After optimizing:

- Re-run with the same workload and recording settings; compare latency distribution, contention, allocation rate, GC, and throughput.
- Ensure synchronization correctness is preserved: never remove `synchronized`/`volatile`/`Lock` just to reduce event counts.
- Keep recording duration and diagnostic data within the necessary scope; JFR files can contain method names, thread names, stacks, classes, and operational metadata that should be managed appropriately.

## 10. Review Questions

**1. A worker thread has an 8-second `jdk.ThreadPark` event on the thread pool's task-waiting path. Is this a concurrency bug?**

Not enough to conclude that. If the pool is idle, this may be normal behavior. Check the workload and see whether the thread is on the serving path of a delayed request.

**2. Thread A holds `synchronized(lock)` to call a slow method; B is blocked trying to enter the same monitor. Which event directly shows that B had to wait for the monitor?**

B's `jdk.JavaMonitorEnter` when the contended entry exceeds the threshold. To find why A held it so long, inspect A's code and other timeline/thread dump data; B's event duration does not directly equal A's hold time.

**3. Thread C calls `lock.wait(500)` inside a `synchronized(lock)` block. Is this `JavaMonitorEnter` or `JavaMonitorWait`?**

It is `jdk.JavaMonitorWait` if the event is enabled and meets the threshold. `Object.wait` releases that monitor while waiting; this differs from waiting to **enter** a synchronized block.

**4. JFR records 100 `jdk.ObjectAllocationSample` events for `byte[]`. Can we say the program created only 100 arrays?**

No. This is sampling; you need to check semantics/weights, allocated-byte statistics, and GC, and measure under the same workload to assess allocation pressure.

**5. Why can a recording with no `jdk.JavaMonitorEnter` events still contain a bottleneck caused by `ReentrantLock`?**

`ReentrantLock` is not a `synchronized` monitor; its wait path can use AQS and `LockSupport.park`, so inspect `jdk.ThreadPark` and the corresponding call stacks.

**Takeaway:** JFR provides **time-ordered evidence** of activities the JVM actually recorded. Combine the right events, stacks, workload context, thresholds, and control measurements; seeing a park, monitor wait, or allocation is only the beginning of finding the root cause.

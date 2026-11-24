# 6.5 ThreadMXBean for platform thread counts, CPU time, contention, and deadlock detection

## Learning objectives

When a Java service suffers from dropping throughput, high CPU, steadily growing thread counts, or long request waits, process-level metrics are not enough to know **which threads are running**, **which threads are waiting on locks**, and **whether a deadlock cycle exists in the JVM**. `java.lang.management.ThreadMXBean` is a standard API for observing the JVM's thread subsystem, supporting quantitative metrics and diagnostic snapshots.

After this lesson, you will be able to:

- Obtain `ThreadMXBean` from `ManagementFactory` and distinguish **live, peak, total started, and daemon thread counts**.
- Read per-thread CPU time in nanoseconds, check `isThreadCpuTimeSupported()` / `isThreadCpuTimeEnabled()`, and compute **deltas between two timestamps** instead of mistaking cumulative totals for CPU%.
- Understand `ThreadInfo`, `getBlockedCount()`, `getBlockedTime()`, `getWaitedCount()`, `getWaitedTime()`, and the scope of contention monitoring.
- Distinguish `findMonitorDeadlockedThreads()` from `findDeadlockedThreads()`; know how to retrieve lock owners, stack traces, and the limits of deadlock detection.
- Use **runnable Java 17+ code** for both regular snapshots and a safe monitor-deadlock lab inside a test process.
- Write diagnostic conclusions with timestamps, workload, measurement support flags, platform thread scope, and confounding factors.

## 1. What is ThreadMXBean and what does "platform thread" mean?

`ThreadMXBean` belongs to the `java.management` module, package `java.lang.management`. The JVM provides a single instance for its thread management system, typically accessed via:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
```

This is an illustrative snippet to place inside a method/class with the corresponding imports; it is not a standalone program. Another path is querying via JMX with ObjectName **`java.lang:type=Threading`**.

**Version scope:**

- **Java 17:** Java SE 17 does not yet include virtual threads as an official platform feature. Threads created via `new Thread(...)` are **platform threads** (threads managed by the JVM and OS under the platform thread model). `ThreadMXBean` numbers reflect this thread subsystem.
- **Java 21 and later:** Java has **virtual threads**, yet `java.lang.management.ThreadMXBean` is a management/monitoring tool for **platform threads**, not a comprehensive counter and profiler for every virtual thread. Do not use `getThreadCount()` to infer the total number of virtual threads. Carrier/execution threads must be distinguished from virtual tasks multiplexed onto them.

Therefore, in this lesson, "thread count" means **the number of live platform threads in the JVM at measurement time**, not in-flight requests, queued tasks, CPU cores, Java virtual threads, or total kernel threads across the node.

For a service deployed in a container, also distinguish **process/JVM scope** from cgroup `pids.current` metrics, OS thread counts, and threads belonging to sidecars or other processes.

### 1.1 Why this API matters for runtime diagnostics

`ThreadMXBean` answers four distinct questions:

| Question | API group | Signal obtained |
| --- | --- | --- |
| How many platform threads does the JVM have? | `getThreadCount()`, `getPeakThreadCount()`, `getTotalStartedThreadCount()`, `getDaemonThreadCount()` | Thread scale, historical peak, churn, daemon ratio |
| Which thread consumes CPU? | `getThreadCpuTime(id)`, `getThreadUserTime(id)` | Cumulative CPU nanoseconds per thread |
| Where are threads blocked/waiting? | `getThreadInfo(...)`, `ThreadInfo`, contention counters/times | State, stack, monitor/lock owner, wait events/times |
| Is there a lock wait cycle in the JVM? | `findMonitorDeadlockedThreads()`, `findDeadlockedThreads()` | Thread IDs belonging to JVM-detected deadlocks |

This is an **evidence source**, not an automatic fix or thread synchronization mechanism. Under load, combine these metrics with logs, request traces, queue depth, process/container CPU, GC, and dependency wait times.

## 2. Platform thread count counters

### 2.1 Four easily confused measurements

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();

int live = mx.getThreadCount();
int peak = mx.getPeakThreadCount();
long started = mx.getTotalStartedThreadCount();
int daemon = mx.getDaemonThreadCount();
```

**Exact meanings:**

- **`getThreadCount()`:** number of *live* threads at read time, including daemon and non-daemon threads.
- **`getPeakThreadCount()`:** the *highest live thread count* since JVM startup or since the most recent `resetPeakThreadCount()` call. It is not the maximum thread limit configured for the application.
- **`getTotalStartedThreadCount()`:** total number of threads created **and started** since JVM startup. This is a **cumulative counter** and normally never decreases when threads terminate.
- **`getDaemonThreadCount()`:** number of live daemon threads at read time; not the count of background jobs or "unimportant" threads.

Hypothetical example:

```text
time=T1: live=80, peak=120, totalStarted=1200, daemon=43
time=T2: live=82, peak=135, totalStarted=1650, daemon=44
```

Between T1 and T2, live threads grew by only 2 while total started grew by **450**. This can indicate heavy thread churn (continuous creation/destruction). It does not automatically conclude a memory leak or misconfigured pool: the application might be running many short tasks on dedicated threads or using a special thread factory policy.

**Counter scope notes:**

- `peak` depends on when it was reset; `resetPeakThreadCount()` **mutates a JVM-wide diagnostic landmark**, not a read-only operation. Never reset it mid-investigation just to "make the chart look nicer".
- `started` accumulates since JVM start; do not compare it directly between two processes with different uptimes. Compute deltas and convert to threads started/second over the same window.
- A fixed 50-worker thread pool may have 50 live platform threads yet thousands of queued tasks; **thread count does not measure queue length or user count**.
- A single pass of reads is not an atomic snapshot of all counters. `live`, `peak`, and `started` can change between calls if the program is creating/destroying threads.

### 2.2 Windowed formulas

With two samples at T1/T2:

```text
deltaStarted = totalStarted(T2) - totalStarted(T1)
threadStartRatePerSecond = deltaStarted / elapsedSeconds
liveChange = live(T2) - live(T1)
```

From the numbers above over 30 seconds: `deltaStarted=450`, or **15 thread starts/second**. This is a churn signal, not proof that 15 new threads stay alive every second.

Always attach run ID, timestamps, and workload. If throughput jumped 10x, a higher thread start rate may be reasonable; if workload is flat while the rate climbs and latency/GC degrade, inspect thread factory/executor lifecycles.

## 3. Listing threads and current info

```java
long[] ids = mx.getAllThreadIds();
ThreadInfo[] infos = mx.getThreadInfo(ids, 20);
```

- `getAllThreadIds()` returns the IDs of threads live at the time of the call. By the time `getThreadInfo` runs next, some threads may have terminated.
- `getThreadInfo(ids, 20)` retrieves info and stack traces up to **20 frames** per thread; entries for already-terminated IDs can be `null`. Limiting depth keeps output manageable.
- `getThreadInfo(id)` **does not** capture stack traces: it is equivalent to `getThreadInfo(id, 0)`.
- `dumpAllThreads(lockedMonitors, lockedSynchronizers)` provides a broader snapshot; options capturing lock info and stack traces can carry substantial cost when thread counts are large.

Useful fields on `ThreadInfo`:

| API | Interpretation |
| --- | --- |
| `getThreadId()`, `getThreadName()` | Identify the thread in that observation |
| `getThreadState()` | A state such as `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` |
| `getStackTrace()` | Call path at capture time (may be empty/truncated) |
| `getLockInfo()`, `getLockName()` | Lock/object the thread is waiting on, if any |
| `getLockOwnerId()`, `getLockOwnerName()` | Owner of the awaited lock, if the JVM can determine it |
| `getLockedMonitors()`, `getLockedSynchronizers()` | Locks held when requested and supported by the JVM |

**Thread ID** is a positive `long`. In Java 17 you can retrieve a `Thread`'s ID with `Thread.getId()`. An ID is unique for the thread's lifetime, yet **can be reused after the thread terminates**; never use a thread ID without timestamps/process identity as a permanent business key.

### 3.1 Thread state does not immediately tell the root cause

- **`RUNNABLE`:** may be executing or ready and waiting for CPU under JVM semantics; does not by itself prove the thread consumes high CPU.
- **`BLOCKED`:** typically waiting to acquire an **object monitor** to enter `synchronized`; useful when suspecting monitor contention.
- **`WAITING`:** waiting indefinitely on mechanisms such as `Object.wait()`, `Thread.join()`, or `LockSupport.park()`.
- **`TIMED_WAITING`:** similar, with a timeout (`sleep`, timed `wait`, `park`, etc.).
- **`TERMINATED`:** a terminated thread will no longer appear in the live set; `getThreadInfo(id)` may return `null`.

A worker pool with many `WAITING` threads idle for tasks is a **normal** state, not a deadlock. One thread seen `BLOCKED` at a single instant might also be brief contention; multiple samples, counters, and latency are needed to quantify.

## 4. Reading per-thread CPU time

### 4.1 CPU time differs from wall-clock time

`getThreadCpuTime(long id)` returns total CPU time consumed by the thread (user + system mode if the JVM distinguishes them), in **nanoseconds**. This is **cumulative CPU time**, not how long the thread has existed, request elapsed time, or an instantaneous CPU percentage.

`getThreadUserTime(id)` measures only user-mode CPU time within implementation limits; do not treat `getThreadCpuTime - getThreadUserTime` as a precise kernel profiler without understanding JVM/OS support and accuracy.

**Example on the same thread:**

```text
Wall sample T1: 0.0 s, thread CPU time = 5.100 s
Wall sample T2: 0.2 s, thread CPU time = 5.150 s
deltaCpu = 0.050 s; deltaWall = 0.200 s
CPU share on a single-logical-CPU basis = 0.050/0.200*100 = 25.0%
```

The 25% here is **usage equivalent to 0.25 logical CPUs during the window** for one thread. It is not "25% CPU of a 16-core machine" and does not measure time spent blocked/waiting on I/O. The sum across multiple threads can exceed 100% when they actually run concurrently on multiple logical CPUs.

When container CPU limits differ from host CPU count, keep the **denominator** explicit: one core, container quota, or total node. Measured CPU time also does not directly show how long a thread was throttled.

### 4.2 Always check support and enabled state

Before measuring any thread:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();

if (mx.isThreadCpuTimeSupported() && mx.isThreadCpuTimeEnabled()) {
    long cpuNanos = mx.getThreadCpuTime(threadId);
    if (cpuNanos >= 0) {
        // Valid CPU-time sample for a live thread.
    }
}
```

This is an **integrated illustrative snippet**, where `threadId` is the positive ID of a real thread; imports for `ManagementFactory` and `ThreadMXBean` are required.

Cases to consider:

- `isThreadCpuTimeSupported() == false`: the JVM does not support measuring CPU time for arbitrary threads; do not call `getThreadCpuTime` assuming numbers will always be available.
- `isThreadCpuTimeEnabled() == false`: support may exist while measurement is disabled; `getThreadCpuTime(id)` typically returns `-1`.
- `getThreadCpuTime(id) == -1`: may be because the thread is dead/non-existent or measurement is disabled; **it is not 0 nanoseconds**.
- `isCurrentThreadCpuTimeSupported()`: capability to measure the current thread only; do not assume both support flags match on every VM.
- Enabling `setThreadCpuTimeEnabled(true)` changes JVM measurement configuration and can incur resource cost; do so only with authorization, clear purpose, and a rollback plan. Never silently turn it on in production just for prettier charts.

Java 17 Javadoc notes **nanosecond** resolution, yet **does not guarantee nanosecond precision**. A thread's CPU time is a **cumulative counter over the measured lifetime**; if enabled after a thread has already been running, when accounting starts can depend on the VM. When computing deltas, use **the same thread ID, same process, same measurement state, and a well-defined interval**.

### 4.3 Finding top CPU threads properly

A workflow far better than sorting total CPU time once:

1. At T1 fetch `getAllThreadIds()`, then CPU time for live IDs.
2. At T2 fetch IDs/counters again after a fixed window, e.g. 10 seconds; compute `deltaCpuNs` for threads present in both samples.
3. Keep only **non-negative** deltas, discarding `-1`/terminated threads; watch out for thread ID reuse if the window is long or thread churn is very high.
4. Rank by **CPU delta**, not by total CPU time since JVM startup.
5. For suspicious threads, capture `ThreadInfo`/stacks/JFR CPU samples to see **which code path** is spending CPU.

A thread running for 10 hours might have high cumulative CPU time while currently asleep. Conversely, a newly spawned thread stuck in an infinite loop has low cumulative CPU time yet an extremely high **delta** over the last 10 seconds.

## 5. Contention: blocked count/time and waited count/time

### 5.1 "Blocked" differs from "waited"

`ThreadInfo` provides:

- `getBlockedCount()`: number of times the thread blocked to enter or re-enter a **monitor**.
- `getBlockedTime()`: **approximate cumulative** time, in **milliseconds**, the thread blocked waiting to enter a monitor since contention monitoring was appropriately enabled.
- `getWaitedCount()`: number of times the thread waited for notification per API semantics.
- `getWaitedTime()`: approximate cumulative time, in milliseconds, the thread waited for notification/in the corresponding waiting state since contention monitoring was enabled.

These are not "total wait time for all I/O", nor do they replace traces for measuring request latency. `BLOCKED` waiting on `synchronized` differs from `WAITING` in `Object.wait`, `Thread.join`, `park`, or waiting for tasks. `getBlockedTime` does not measure every `ReentrantLock`/database/network wait under one catch-all label.

### 5.2 Must check whether contention monitoring is enabled

```java
if (mx.isThreadContentionMonitoringSupported()) {
    boolean enabled = mx.isThreadContentionMonitoringEnabled();
    ThreadInfo info = mx.getThreadInfo(threadId);
    if (info != null) {
        long blockedCount = info.getBlockedCount();
        long blockedMs = info.getBlockedTime();
        long waitedCount = info.getWaitedCount();
        long waitedMs = info.getWaitedTime();
        // If enabled == false, blockedMs/waitedMs may be -1.
    }
}
```

This is an integrated illustrative snippet. In Java 17, contention monitoring is **disabled by default** per documentation; check the actual state instead of guessing. When monitoring is disabled, `getBlockedTime()` and `getWaitedTime()` return `-1`, while counts follow different semantics; **do not replace -1 with 0** because you lose the distinction between "not measured" and "measured zero wait time".

Enable/disable via:

```java
mx.setThreadContentionMonitoringEnabled(true);
```

This call **mutates JVM observation state**, requires management permission, only works when `isThreadContentionMonitoringSupported()` is true, and can introduce overhead. Upon re-enabling, related time statistics may reset, so do not compare raw counters across enable/disable toggles as one continuous series. In production, follow an agreed configuration/monitoring policy and record the timestamp of when it was enabled.

### 5.3 Interpreting properly with deltas

Purely **hypothetical** example for a platform thread in the same JVM:

| Metric | T1 | T2 | Delta |
| --- | ---: | ---: | ---: |
| Blocked count | 20 | 24 | +4 times |
| Blocked time (ms) | 110 | 118 | +8 ms |
| Waited count | 7 | 8 | +1 time |
| Waited time (ms) | 80 | 100 | +20 ms |

Between T1 and T2, assuming valid measurement and no reset, you can say the thread experienced **4 additional blocked events** and accumulated roughly **8 ms more blocked time**. You cannot conclude "average lock wait is 2 ms across all transactions" because that is one thread over one short interval, not necessarily representative of the whole workload.

For a thread whose `blockedCount` climbs while `blockedTime` stays low, there may be frequent very brief contention. When `blockedTime` rises sharply, inspect lock owner, stack, and request/load shifts in the same window.

### 5.4 Why one snapshot does not resolve contention

`ThreadInfo` describes a single instant. If you see 30 workers simultaneously `BLOCKED` waiting on one monitor, investigate:

- Which lock is contended? `getLockInfo`/`getLockName`.
- Which thread holds it? `getLockOwnerId`/`getLockOwnerName`.
- Where is the owner executing? Capture the owner's `ThreadInfo`/stack.
- Does it happen on every traffic peak or randomly? Compare multiple samples, blocked deltas, and p95/p99/throughput.
- Is the lock held across I/O or long computation? Need traces/call paths—never rewrite code based solely on one state.

`WAITING` threads in an idle executor are usually completely normal. If a downstream dependency slows down, workers may enter `WAITING`/park without any **monitor deadlock**. Never equate every wait with a synchronization bug.

## 6. Deadlock detection: two APIs that are not the same

### 6.1 What is a deadlock?

Lock deadlock typically occurs when there is a **wait cycle**:

```text
Thread A holds monitor M1, waiting for M2
Thread B holds monitor M2, waiting for M1
              A ----waits-for----> B
              ^                    |
              |-----waits-for------|
```

Since each holds a lock and waits for the other's lock, neither can make progress without external intervention. `ThreadMXBean` can detect certain lock wait cycles at the moment of inspection.

### 6.2 Comparing `findMonitorDeadlockedThreads` and `findDeadlockedThreads`

| Method | Scope | Return | Notes |
| --- | --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Wait cycles acquiring **object monitors** (locks used by `synchronized`) | `long[]` of IDs or `null` when none found | Does not cover all ownable synchronizers |
| `findDeadlockedThreads()` | Cycles involving **object monitors and ownable synchronizers** such as certain `java.util.concurrent.locks` | `long[]` or `null` | May throw `UnsupportedOperationException` if the VM does not support observing ownable synchronizers |

Check `isSynchronizerUsageSupported()` before using the broader detection method. If unsupported, you can use the monitor-only option while **explicitly noting the scope limitation**. Never turn `null` into "no deadlock of any kind exists"; the result only means **no cycle of the supported type was detected at that exact moment**.

Deadlock detection APIs are meant for troubleshooting and **can be expensive** when thread/lock counts are high. Do not poll them frequently on an already overloaded JVM.

### 6.3 Gathering concrete evidence after detection

With the returned IDs:

```java
long[] deadlocked = mx.findMonitorDeadlockedThreads();
if (deadlocked != null) {
    ThreadInfo[] infos = mx.getThreadInfo(deadlocked, 32);
    for (ThreadInfo info : infos) {
        if (info != null) {
            System.out.println(info.getThreadName()
                    + " waitingFor=" + info.getLockName()
                    + " owner=" + info.getLockOwnerName());
        }
    }
}
```

This is an integrated illustrative snippet; stdout depends on the JVM. In a real incident, also capture stack traces, lock owner ID, held locks list, and timestamp, and verify whether object monitors/ownable synchronizers are supported when requesting lock details.

`findDeadlockedThreads()` **does not** detect every "application hung" scenario:

- Thread A waiting on a database, thread B waiting on network where external non-JVM dependencies do not respond.
- Tasks in a pool waiting on `Future.get()` of other tasks without a JVM-recognized object monitor/ownable synchronizer cycle.
- Starvation from an exhausted thread pool or locks in another process.
- Livelocks, I/O without deadlines, or distributed deadlocks across services.
- Transient deadlocks that resolved before capture.

In those cases, investigate queues, thread stacks, traces, task scheduling, deadlines, and downstream systems. "No monitor deadlock found" does not mean "the request path isn't stalled".

## 7. Java 17+: one program with fixed fixture data, snapshot, and deadlock lab

The demo below has **three explicit modes**:

- **`fixture`**: computes deltas from hypothetical numbers, giving **exact, environment-independent** stdout.
- **`snapshot`**: observes the running JVM's `ThreadMXBean` with feature checks, **without enabling/disabling** CPU/contention monitoring; output varies by OS/JDK/state.
- **`deadlock`**: inside **a fresh lab JVM**, creates two daemon platform threads intentionally deadlocking via `synchronized`, then detects them with `findMonitorDeadlockedThreads()`. Never run this mode in a real service; the daemon threads remain deadlocked until the lab JVM exits.

Create the file **`ThreadMxBeanLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadMxBeanLab {
    private static final ThreadMXBean MX =
            ManagementFactory.getThreadMXBean();

    static void fixture() {
        long cpuBeforeNs = 5_100_000_000L;
        long cpuAfterNs = 5_150_000_000L;
        long elapsedNs = 200_000_000L;

        double share = 100.0 *
                (cpuAfterNs - cpuBeforeNs) / elapsedNs;

        long blockedBefore = 20;
        long blockedAfter = 24;
        long blockedMsBefore = 110;
        long blockedMsAfter = 118;

        System.out.println("live=80 peak=120 started=1200 (fixture)");
        System.out.printf(java.util.Locale.ROOT,
                "cpuDeltaMs=50 wallMs=200 cpuShare=%.1f%%%n", share);
        System.out.printf(java.util.Locale.ROOT,
                "blockedCountDelta=%d blockedTimeDeltaMs=%d%n",
                blockedAfter - blockedBefore,
                blockedMsAfter - blockedMsBefore);
        System.out.println("deadlockResult=null means not detected");
    }

    static void snapshot() {
        System.out.println("live=" + MX.getThreadCount());
        System.out.println("peak=" + MX.getPeakThreadCount());
        System.out.println("started=" + MX.getTotalStartedThreadCount());
        System.out.println("daemon=" + MX.getDaemonThreadCount());

        boolean cpuSupport = MX.isThreadCpuTimeSupported();
        System.out.println("cpuSupported=" + cpuSupport);
        if (cpuSupport) {
            boolean enabled = MX.isThreadCpuTimeEnabled();
            System.out.println("cpuEnabled=" + enabled);
            if (enabled) {
                long id = Thread.currentThread().getId();
                System.out.println("currentThreadCpuNs="
                        + MX.getThreadCpuTime(id));
            }
        }

        boolean contention =
                MX.isThreadContentionMonitoringSupported();
        System.out.println("contentionSupported=" + contention);
        if (contention) {
            System.out.println("contentionEnabled="
                    + MX.isThreadContentionMonitoringEnabled());
        }

        long[] ids = MX.getAllThreadIds();
        Arrays.sort(ids);
        int shown = 0;
        for (long id : ids) {
            ThreadInfo info = MX.getThreadInfo(id, 3);
            if (info == null) {
                continue; // Thread ended between the two reads.
            }
            System.out.println("thread=" + info.getThreadName()
                    + " state=" + info.getThreadState());
            if (++shown == 5) {
                break;
            }
        }

        long[] monitorDeadlocks = MX.findMonitorDeadlockedThreads();
        System.out.println("monitorDeadlockDetected="
                + (monitorDeadlocks != null));
    }

    static void lockInOrder(Object first, Object second,
            CountDownLatch ready, CountDownLatch proceed) {
        synchronized (first) {
            ready.countDown();
            try {
                proceed.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (second) {
                // Two threads hold opposite first locks in this lab.
            }
        }
    }

    static void deadlockLab() throws InterruptedException {
        Object first = new Object();
        Object second = new Object();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread a = new Thread(
                () -> lockInOrder(first, second, ready, proceed),
                "lab-deadlock-A");
        Thread b = new Thread(
                () -> lockInOrder(second, first, ready, proceed),
                "lab-deadlock-B");

        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        if (!ready.await(5, TimeUnit.SECONDS)) {
            System.out.println("lab=not-ready");
            return;
        }
        proceed.countDown();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            long[] ids = MX.findMonitorDeadlockedThreads();
            if (ids != null) {
                boolean foundA = Arrays.stream(ids)
                        .anyMatch(id -> id == a.getId());
                boolean foundB = Arrays.stream(ids)
                        .anyMatch(id -> id == b.getId());
                if (foundA && foundB) {
                    System.out.println(
                            "monitorDeadlock=lab-deadlock-A,lab-deadlock-B");
                    ThreadInfo[] info = MX.getThreadInfo(
                            new long[] {a.getId(), b.getId()}, 5);
                    for (ThreadInfo t : info) {
                        if (t != null) {
                            System.out.println(t.getThreadName()
                                    + " state=" + t.getThreadState());
                        }
                    }
                    return;
                }
            }
            Thread.sleep(20);
        }
        System.out.println("monitorDeadlock=not-detected-in-time");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java ThreadMxBeanLab fixture|snapshot|deadlock");
            return;
        }
        switch (args[0]) {
            case "fixture" -> fixture();
            case "snapshot" -> snapshot();
            case "deadlock" -> deadlockLab();
            default -> System.out.println("Unknown mode");
        }
    }
}
```

Compile with **JDK 17 or later**:

```bash
javac ThreadMxBeanLab.java
java ThreadMxBeanLab fixture
```

**Exact** stdout of `fixture`:

```text
live=80 peak=120 started=1200 (fixture)
cpuDeltaMs=50 wallMs=200 cpuShare=25.0%
blockedCountDelta=4 blockedTimeDeltaMs=8
deadlockResult=null means not detected
```

Calculation: `(5_150_000_000 - 5_100_000_000) ns = 50 ms`, `200_000_000 ns = 200 ms`, so `cpuShare = 50/200 * 100 = 25.0%`. `blockedCount` increased by 4 and `blockedTime` by 8 ms. This is a **synthetic dataset**, not statistics captured from an executing Java workload.

Run the **live snapshot**:

```bash
java ThreadMxBeanLab snapshot
```

This prints current counters, whether CPU/contention monitoring is supported/enabled, a few threads, and monitor deadlock status. **No fixed stdout**: thread count, CPU time, thread names, IDs, and feature flags vary by VM/OS/time; `cpuSupported=false` is not automatically an error.

Run the **deadlock lab only in a lab JVM**:

```bash
java ThreadMxBeanLab deadlock
```

On a JVM supporting monitor deadlock detection and normal thread scheduling, expected output once the wait cycle forms:

```text
monitorDeadlock=lab-deadlock-A,lab-deadlock-B
lab-deadlock-A state=BLOCKED
lab-deadlock-B state=BLOCKED
```

This mode **intentionally creates a deadlock**; both threads are marked `daemon` so they do not keep the lab process alive after `main` returns. On an overloaded machine or an implementation that does not detect in time, it may print `lab=not-ready` or `monitorDeadlock=not-detected-in-time`. Never treat those cases as proof of "no deadlocks" in applications generally. Do not put deadlock-creating code into production or unit tests sharing a long-lived JVM.

**Code QA points:**

- `ThreadInfo.getThreadId()` and `Thread.getId()` are Java 17 APIs.
- The `CountDownLatch` handshake guarantees both threads hold their first monitor before seeking the second, creating a symmetric wait cycle.
- `Arrays.sort(ids)` partially stabilizes snapshot ordering but does not guarantee a fixed thread list.
- The `snapshot` demo only **reads** monitoring state and calls no setters that alter JVM measurement settings.
- In `deadlock`, daemon threads may remain blocked when the program exits; that is an intentional lab trait, **not** an application design pattern.

## 8. Reading data in real Java diagnostics

### 8.1 High CPU while throughput fails to grow

**Symptom:** high process CPU, rising p99, flat throughput.

Gather data:

1. Record offered/received/completed RPS, request mix, GC, CPU quota/throttling, and timestamps.
2. Read per-thread CPU time at two timestamps and compute **CPU delta** over the same window.
3. Find top threads; capture stacks/JFR CPU profiles to inspect call paths; distinguish primary worker threads from GC/JIT threads.
4. Look for busy-spinning, heavy serialization, tight polling, retry loops, or lock contention; never assign cause from thread name alone.

A thread named `worker-4` having a high CPU delta does not yet prove which task/endpoint caused the CPU, because a pool reuses threads across tasks. You need trace/task IDs, sampling, and workload correlation.

### 8.2 Thread count rising continuously

**Symptom:** `live` rises alongside RSS/native memory, or thread creation errors appear.

Collect:

- `getThreadCount`, `getPeakThreadCount`, `getTotalStartedThreadCount` over time.
- Pending task counts, pool size/active count, worker counts by name, thread creation rate, socket/file descriptor usage.
- Thread dumps/stacks of similar threads to see where they wait.
- Container PID/memory/OS limits and thread stack sizes if relevant.

**Possible conclusion:** rising `live` and rising `started` indicate thread accumulation, yet are not enough to call it a "leak". Threads may be legitimately alive for demand; verify which threads **should have exited** yet remain retained.

If `started` climbs rapidly while `live` stays steady, the pattern fits **churn**, creating thread creation/destruction overhead rather than necessarily a leak.

### 8.3 Thread contention slows down requests

**Symptom:** many requests stall at a `synchronized` section.

Collect:

- `ThreadInfo` samples at T1/T2; inspect `BLOCKED`, `getLockOwnerName`, and the owner's stack frames.
- Blocked count/time deltas when contention monitoring is actually enabled.
- CPU deltas to see whether the owner is computing or itself stalled elsewhere.
- Request latency, throughput, load, and lock hold time if instrumented.

**Cautious conclusion:** rising blocked time with a consistent lock owner fits a monitor contention hypothesis. Do not declare the root cause confirmed until proving the lock lies on the slow request path and ruling out dependency/GC/scheduling effects.

### 8.4 Service hangs and deadlock is suspected

**Safe procedure:**

1. Capture stack traces/thread dumps and metrics before mutating state.
2. Run monitor deadlock detection; if ownable synchronizers are supported, consider broader detection.
3. For returned IDs, capture thread names, lock owner, lock/monitor info, call paths, and timestamps.
4. Verify whether this is a **mutual wait cycle** or simply many threads waiting on one slow worker.
5. Preserve evidence, analyze lock ordering, and fix regressions; never "fix" by toggling monitoring setters or resetting counters.

**Reject overly strong conclusions:** both APIs returning `null` does not prove the system cannot deadlock on network, DB, or at another instant.

## 9. Access via JMX and diagnostic tools

Because `ThreadMXBean` is a platform MXBean, you can use local code or suitable JMX tools such as JConsole/VisualVM/JMX clients to inspect `java.lang:type=Threading`. In server environments:

- Every remote operation requires proper authentication, TLS, and access control; never open public remote JMX just to view a few metrics.
- State-mutating APIs and operations such as `setThreadCpuTimeEnabled`, `setThreadContentionMonitoringEnabled`, and `resetPeakThreadCount` must be gated separately—do not let dashboards invoke them automatically.
- Thread dumps/deadlock detection can consume CPU, memory, and pause time; do not poll too aggressively.
- Thread names, stack traces, class/method names, or request-related context can be sensitive system info; enforce RBAC and retention limits.
- In containers or clusters, verify the connection/agent targets the exact JVM instance, rather than accidentally measuring a sidecar JVM or a freshly restarted process.

If attaching a JMX agent is not possible, collect via code instrumentation or `jcmd Thread.print`/JFR per operational policy; each option has its own scope and cost. Never assume every tool returns the exact same thread set at the exact same instant.

## 10. Performance, side effects, and measurement limitations

### 10.1 Measurements that can alter observation conditions

| Operation | Impact category | Practice |
| --- | --- | --- |
| `getThreadCount()`, `getPeakThreadCount()` | Relatively lightweight read | Accept variation between two calls |
| `getThreadCpuTime(id)` | Reads CPU counter | Check enabled/supported; avoid very tight polling |
| `setThreadCpuTimeEnabled(true)` | **Mutates tracking state** | Requires authorization and plan; incurs overhead |
| `setThreadContentionMonitoringEnabled(true)` | **Mutates tracking state** | Record enable time; affects statistics baseline |
| `getThreadInfo(ids, depth)` | Stack/lock snapshot | Bound ID count and depth when possible |
| `dumpAllThreads(...)` | Captures all thread stacks/locks | Can be heavy on JVMs with many threads |
| `findDeadlockedThreads()` | Analyzes lock wait graph | Do not poll frequently; know capability and null result |
| `resetPeakThreadCount()` | **Mutates peak history** | Do not reset while historical comparison is needed |

Capturing `ThreadInfo` or running deadlock detection can perturb wall-clock/CPU on a heavily loaded system. Stamp the exact capture time, measure command execution duration, and watch symptoms before/after the action.

### 10.2 Interpreting `-1`, `null`, and `false`

- CPU time `-1`: dead/non-existent thread or measurement disabled; invalid state for delta calculation.
- Blocked/waited time `-1`: contention monitoring is disabled, **not** meaning the thread never waited.
- `ThreadInfo == null`: thread is no longer alive at read time or ID does not exist.
- `long[] deadlocks == null`: no lock cycle within the method's scope detected **at that check**.
- `is…Supported() == false`: feature unavailable on the current VM/implementation, not an application bug.

Never use `Math.max(0, value)` to "sanitize" negative numbers before reporting: turning `-1` into `0` makes dashboards **falsely** report zero CPU or wait/blocked time.

### 10.3 Other limits to note

- **Sampling bias:** a single snapshot can miss threads busy for only a few milliseconds.
- **Thread churn:** IDs from T1 may die before T2; per-thread deltas lose meaning.
- **Container CPU quota:** CPU-time and utilization must be read alongside throttling/cgroup metrics.
- **Framework task scheduling:** one worker serves many tasks; thread CPU time cannot be attributed directly to one request.
- **Different JVMs:** CPU/contention monitoring support, overhead, and measurement timing vary by implementation.
- **Java version:** `getThreadCount` does not measure virtual thread count on newer JDKs.
- **Cumulative nature:** JVM restarts, peak resets, or toggling monitoring alter counter semantics.
- **Deadlock scope:** detects only supported lock cycles; does not detect logical or distributed deadlocks.

## 11. ThreadMXBean diagnostic report template

```text
RUN CONTEXT
- Service/build, JVM vendor/version, container/pod/PID:
- Workload: offered/received/completed RPS, concurrency, request mix:
- Start/end time, timezone, sampling interval, run IDs:

THREAD COUNTS
- live, peak, totalStarted, daemon per sample:
- deltaStarted / thread-start rate:
- pool size/queue depth/active workers correlation:

CPU
- isThreadCpuTimeSupported / isThreadCpuTimeEnabled:
- IDs, names, deltaCpuNs, deltaWallNs, per-core-equivalent share:
- stack/JFR evidence for top CPU threads:
- container quota/throttling and process CPU:

CONTENTION
- isThreadContentionMonitoringSupported / Enabled:
- start/stop time of any monitoring configuration change:
- blocked/waited counts and times (per thread, per window):
- lock owner, stack/frame evidence, state distribution:

DEADLOCK
- findMonitorDeadlockedThreads: IDs/null/unsupported context:
- findDeadlockedThreads: IDs/null/unsupported context:
- lock cycle, ThreadInfo/stack, timestamp:
- external waits not covered by MXBean:

CONCLUSION
- Confirmed observation:
- Hypotheses supported and alternative explanations:
- Limitations (sampling, duration, thread churn, JDK, workload):
- Risk, remediation owner, verification steps:
```

This is a **structural template**, not a report with real measurements. When used in production, add links to metrics/logs/traces/JFR, store under proper access control, and never broadcast sensitive stack contents.

## 12. Common misconceptions

1. **Treating `getThreadCount()` as active request or task count.** Worker threads are typically reused; measure queues separately.
2. **Treating `getTotalStartedThreadCount()` as live threads.** It is the cumulative total started since JVM startup.
3. **Seeing high peak and claiming threads are currently exhausted.** Peak is historical and resettable; inspect live count and current demand.
4. **Using cumulative CPU time to rank current top CPU threads.** Use deltas over the same window.
5. **Forgetting `isThreadCpuTimeSupported`/Enabled.** `-1` does not mean 0 CPU time.
6. **Dividing one thread's CPU share by core count and calling it container CPU without stating the denominator.** CPU% definitions vary.
7. **Enabling contention monitoring without recording timestamp/impact.** It adds overhead and can reset time stats.
8. **Equating `BLOCKED` and `WAITING`.** Waiting on an intrinsic monitor differs from waiting on notifications/park/I/O.
9. **Treating `getBlockedTime=-1` as zero contention.** That typically means time measurement is off.
10. **Calling `findMonitorDeadlockedThreads` and declaring no `ReentrantLock` deadlock exists.** The monitor-only method has a narrower scope.
11. **Calling `findDeadlockedThreads` without checking ownable synchronizer support.** Can throw `UnsupportedOperationException`.
12. **Treating a `null` deadlock result as "the app cannot hang".** Pool starvation or external waits can still stall it.
13. **Taking only one thread dump.** States are snapshots; multiple samples/metrics are needed to diagnose over time.
14. **Forgetting IDs can be reused.** Attach process identity, timestamp, and name/stack.
15. **Capturing full stacks continuously on an overloaded JVM.** Diagnostic tooling itself can worsen latency.
16. **Failing to separate platform and virtual threads.** ThreadMXBean on newer JDKs does not reflect total virtual tasks.
17. **Confusing CPU time with latency.** I/O-bound threads can consume low CPU while making requests slow.
18. **Using ThreadMXBean as a synchronization mechanism.** It is for monitoring, offering neither atomic snapshots nor lock ordering to drive business logic.

## 13. Self-check questions

1. How do `getThreadCount()`, `getPeakThreadCount()`, and `getTotalStartedThreadCount()` differ? When does total started climb quickly while live stays flat?
2. If CPU time grows by 50 ms in a 200 ms window, what percentage of one logical CPU equivalent was used? Does that equal 25% CPU of a 32-core node?
3. Under what conditions does `getThreadCpuTime(id)` return `-1`? Why must `-1` never be replaced with 0?
4. You call `getThreadInfo(ids, 20)` after `getAllThreadIds()` and encounter a `null` element. Is that a JVM bug?
5. Why do `getBlockedCount()` and `getBlockedTime()` have different units? Do these values measure all database/network waits?
6. `isThreadContentionMonitoringSupported()` returns true, yet `getBlockedTime()=-1`. What are the next checks?
7. What lock-type difference separates `findMonitorDeadlockedThreads()` from `findDeadlockedThreads()`? When should you check ownable synchronizer support?
8. Two workers are both `WAITING` in a thread dump. Is that sufficient proof of a deadlock? How would you inspect lock owners/queues/stacks?
9. In Java 21+, can `ThreadMXBean.getThreadCount()` serve as the count of running virtual threads? What other tools/metrics are needed?
10. A service has rising p99 while per-thread CPU time is low. What hypotheses around I/O, GC, locks, thread pool starvation, or throttling should be examined?
11. Which operations in `ThreadMXBean` **mutate measurement state** instead of only reading? What must you record on the timeline?
12. If `findDeadlockedThreads()` returns `null` once, what is the strongest valid conclusion?

## References

- Oracle Java SE 17 — ThreadMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 17 — ThreadInfo: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 21 — ThreadMXBean (clarifying platform thread scope on JVMs with virtual threads): https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html

**Remember:** `ThreadMXBean` measures **platform thread counts, cumulative CPU time, contention, and deadlock cycles of supported lock types**. Accurate diagnostics require checking support flags, distinguishing cumulative metrics from deltas, comparing figures within the same workload/window, and never turning `null` or `-1` into "no errors".
# Measuring Lock Contention in Java

**Lock measurement** is the practice of collecting metrics on how long threads wait to acquire a lock, how often contention occurs, how long locks are held, and how locking affects throughput and latency. The goal is to identify critical sections or locks that force many threads to wait, and then reduce wait times while preserving data consistency.

A lock can behave correctly yet still become a performance bottleneck. For example, consider a shared cache protected by `synchronized`; as concurrent requests increase, many threads must queue up to enter the same block of code. If the critical section performs I/O, long computations, or calls another service, the wait time for the remaining threads can spike dramatically.

No single metric fully describes lock contention. You need to distinguish between **lock wait time**, **lock hold time**, **contended acquisition count**, **queue length**, and **request latency**. Use thread dumps to identify the involved threads and locks, JFR to measure durations and stack traces over time, `ThreadMXBean` to collect contention statistics for platform threads, and JMH to benchmark in a controlled environment.

## 1. What Are Locks and Lock Contention?

A lock is a mechanism for coordinating access to shared resources. Java provides several synchronization mechanisms:

- Intrinsic monitors via `synchronized` on methods or blocks.
- Explicit locks such as `ReentrantLock` and `ReentrantReadWriteLock`.
- Synchronizers based on `AbstractQueuedSynchronizer` (AQS), which typically use `LockSupport.park` when a thread must wait.
- `Semaphore`, `CountDownLatch`, `Phaser`, and `Condition`, which coordinate permits or signals between threads; not all of them are exclusive locks.

**Lock contention** occurs when multiple threads want to use the same lock and at least one thread must wait for another thread to release the lock or allow it to proceed.

Example:

```java
private final Object lock = new Object();

public void update() {
    synchronized (lock) {
        updateSharedState();
    }
}
```

If one thread is inside `synchronized (lock)`, other threads attempting to enter the same monitor must wait. When the critical section is short and thread count is low, wait time may be negligible. As the number of competing threads grows or the work inside the lock takes longer, contention can become a bottleneck.

## 2. Distinguishing Monitors, Explicit Locks, and Thread States

You need to know the lock type before choosing a tool:

| Mechanism | How threads typically wait | Appropriate evidence |
|---|---|---|
| `synchronized` | Thread may be in `BLOCKED` state waiting for monitor | Thread dump, `ThreadMXBean`, JFR `jdk.JavaMonitorEnter` |
| `Object.wait()` | Thread is in `WAITING` or `TIMED_WAITING`, waiting for notification/timeout | Thread dump, JFR `jdk.JavaMonitorWait` |
| `ReentrantLock` | Thread may park via `LockSupport` in AQS | JFR `jdk.ThreadPark`, thread dump, lock instrumentation |
| `Condition.await()` | Thread parks until signaled or timed out | JFR `jdk.ThreadPark`, thread dump |
| `Semaphore`/`CountDownLatch` | Thread typically parks waiting for a permit or signal | JFR `jdk.ThreadPark`, thread dump |

`BLOCKED` has a specific meaning: the thread is waiting to enter or re-enter an intrinsic monitor. `WAITING` and `TIMED_WAITING` are broader; they can result from `Object.wait`, `LockSupport.park`, `Thread.join`, `Condition.await`, or other waiting mechanisms. Do not assume every `WAITING` thread is contending for a lock.

With `ReentrantLock`, waiting threads are typically parked, so do not look only for the `BLOCKED` state in thread dumps. Inspect stack traces, blockers, ownable synchronizers, and JFR events.

## 3. Metrics to Measure

A useful lock measurement should include the following metrics:

| Metric | Meaning | How to interpret |
|---|---|---|
| Acquisition count | Number of times the lock is acquired | Shows how frequently the lock is used |
| Contended acquisition count | Number of times threads had to wait before acquiring the lock | A high ratio indicates many threads are competing |
| Wait time | Time from starting the lock request until acquiring the lock | Reflects the caller's waiting cost |
| Hold time | Time from acquiring the lock until releasing it | Long critical sections can grow the wait queue |
| Queue length | Number (or estimate) of threads waiting | Helps identify locks with many waiters |
| Throughput | Number of operations completed per unit of time | Can drop as contention increases |
| Latency percentiles | p50, p95, p99 of the operation | Reveals tail latency caused by lock waits |
| CPU and context switches | CPU time, context switches, runnable threads | Distinguishes lock waits from CPU-bound workloads |

The two most important quantities are wait time and hold time:

- **Wait time** starts before the acquire operation and ends immediately after the lock is acquired.
- **Hold time** starts after a successful acquire and ends upon unlock or exiting the synchronized block.

If hold time is high, shorten the critical section. If hold time is low but wait time remains high, too many threads may be competing or the lock may be acquired too frequently.

Do not measure the entire method's duration as wait time. The method may also perform validation, I/O, computation, or result processing outside the lock.

## 4. Lock Contention Measurement Workflow

A practical workflow:

1. Identify the endpoint, job, or operation experiencing increased latency.
2. Record the workload, concurrency, timestamp, and JVM version.
3. Capture multiple thread dumps during the period when the issue occurs.
4. Identify the lock object, owner thread, waiter threads, and relevant stack frames.
5. Enable a short JFR recording to measure monitor enter and thread park durations.
6. Analyze events by thread, stack trace, lock class, owner, and duration.
7. If in-application metrics are needed, enable `ThreadMXBean` contention monitoring or instrument acquisition/hold time.
8. Reproduce the workload with JMH if you need to compare lock implementations.
9. Change one factor at a time and re-measure under the same workload.
10. Compare throughput, p95/p99, wait time, hold time, and CPU before and after.

Keep input data, thread counts, warm-up duration, and machine configuration consistent when comparing. If the workload changes significantly, before-and-after lock metrics are no longer directly comparable.

## 5. Using Thread Dumps to Find Contended Locks

Start by finding the PID:

```sh
jcmd -l
```

Capture a thread dump with lock information:

```sh
jcmd 24680 Thread.print -l
```

You can request extended information:

```sh
jcmd 24680 Thread.print -e -l
```

Replace `24680` with the target JVM's PID. Check the help on the exact target JVM with `jcmd 24680 help Thread.print`; `Thread.print` has Medium impact, depending on the number of threads.

Example excerpt of a thread dump:

```text
"worker-2" #42 prio=5 os_prio=0 tid=0x... nid=0x... BLOCKED
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Cache.update(Cache.java:48)
    - waiting to lock <0x0000000712345678> (a java.lang.Object)
    at com.example.OrderService.process(OrderService.java:91)

"worker-1" #41 prio=5 os_prio=0 tid=0x... nid=0x... RUNNABLE
    at com.example.Cache.rebuild(Cache.java:27)
    - locked <0x0000000712345678> (a java.lang.Object)
    at com.example.OrderService.refresh(OrderService.java:55)
```

In this example:

- `worker-2` is `BLOCKED`, waiting to acquire the monitor.
- `worker-1` holds the monitor with the same object identity.
- The stack trace shows the waiter is calling `Cache.update`, while the owner is running `Cache.rebuild`.
- The owner's critical section is the first place to inspect.

Object addresses in a thread dump are only meaningful within that snapshot; do not use them as stable IDs across dumps or JVM restarts.

### Capturing Multiple Thread Dumps

A single snapshot only shows the state at one point in time. Capture two or three more snapshots a few seconds apart:

```sh
jcmd 24680 Thread.print -l > thread-01.txt
```

After a few seconds:

```sh
jcmd 24680 Thread.print -l > thread-02.txt
```

And again:

```sh
jcmd 24680 Thread.print -l > thread-03.txt
```

Compare the snapshots:

- Same waiter continuously waiting on the same owner/lock: contention may be prolonged.
- Owner changes while waiters keep growing: multiple threads are acquiring the lock in succession.
- Thread is no longer waiting in the next snapshot: contention may have been brief.
- Many threads waiting on the same lock: that lock may be the serialization point of the workload.

Do not conclude there is a deadlock solely from seeing many `BLOCKED` threads. A deadlock requires a cycle of lock dependencies; normal contention still has an active owner that will eventually release the lock.

## 6. Measuring Synchronized Monitors with JFR

Java Flight Recorder (JFR) records events with timestamps and durations. Useful events for measuring locks:

| JFR event | What to observe |
|---|---|
| `jdk.JavaMonitorEnter` | Time a thread waits to enter an intrinsic monitor, typically related to `synchronized` |
| `jdk.JavaMonitorWait` | Time a thread waits in `Object.wait()` |
| `jdk.ThreadPark` | Time a thread is parked via `LockSupport`, common with AQS, `ReentrantLock`, and `Condition` |
| `jdk.JavaMonitorInflate` | Monitor inflation event; useful in certain monitor analyses, not a measure of total contention |

Do not confuse `JavaMonitorWait` with `JavaMonitorEnter`: one tracks waiting for notification/timeout via `Object.wait`, while the other tracks time spent waiting to acquire a monitor.

JFR events can be filtered by threshold. If the threshold is `10 ms`, events shorter than that threshold may not be recorded. Lowering the threshold lets you observe shorter waits, but generates more events and data. Stack traces help pinpoint the code path causing contention.

## 7. Starting a JFR Recording for Locks

Find the PID:

```sh
jcmd -l
```

Check the command:

```sh
jcmd 24680 help JFR.start
```

Start a short recording using the `profile` configuration and set custom thresholds for lock events:

```sh
jcmd 24680 JFR.start name=lock-profile settings=profile duration=60s filename=lock-profile.jfr jdk.JavaMonitorEnter#threshold=1ms jdk.JavaMonitorEnter#stackTrace=true jdk.JavaMonitorWait#threshold=1ms jdk.ThreadPark#threshold=1ms jdk.ThreadPark#stackTrace=true
```

Explanation:

- `name=lock-profile`: recording name for checking and dumping.
- `settings=profile`: collects more data than the `default` configuration; suitable for short investigations.
- `duration=60s`: the recording automatically stops after 60 seconds.
- `filename=lock-profile.jfr`: file written when the recording stops.
- `jdk.JavaMonitorEnter#threshold=1ms`: records monitor enter events with a duration at or above this threshold.
- `stackTrace=true`: captures the stack trace for the corresponding event.
- `jdk.ThreadPark`: helps inspect parks when threads wait on locks or synchronizers.

To check a running recording:

```sh
jcmd 24680 JFR.check name=lock-profile verbose=true
```

You can dump a snapshot before the recording finishes:

```sh
jcmd 24680 JFR.dump name=lock-profile filename=lock-snapshot.jfr begin=-30s
```

`JFR.dump` creates a snapshot file while the recording continues running. If `duration=60s` is set, the recording will stop automatically when time expires and write `lock-profile.jfr`.

If you need a longer recording, consider `settings=default`, bound the duration/size, and enable only the necessary events. Do not run detailed profiling configurations for extended periods without evaluating overhead.

## 8. Analyzing JFR with JDK Mission Control and the jfr CLI

Open `lock-profile.jfr` in JDK Mission Control (JMC). Focus on:

- Lock instances and monitor contention if your JMC version provides the corresponding page.
- `Java Monitor Enter` and `Thread Park` events.
- Duration and wait-time distribution.
- Waiter thread name/ID.
- Stack trace where waiting began.
- Monitor class, previous owner, or blocker if provided by the event.
- Timeline to correlate contention periods with latency spikes.

You can inspect the file from the command line:

```sh
jfr summary lock-profile.jfr
```

Print monitor enter events:

```sh
jfr print --events jdk.JavaMonitorEnter lock-profile.jfr
```

Print thread park events:

```sh
jfr print --events jdk.ThreadPark lock-profile.jfr
```

Print monitor wait events:

```sh
jfr print --events jdk.JavaMonitorWait lock-profile.jfr
```

Avoid printing an entire large recording to the terminal. Filter to the events you need to analyze, then use JMC to group by thread, class, stack trace, and duration.

When expected events are missing, check `JFR.check ... verbose=true`, thresholds, enabled settings, and the recording window. The absence of events in the file does not prove the lock was never contended; wait times may have been shorter than the threshold, or the event may have been disabled.

## 9. Using ThreadMXBean to Measure Platform Thread Contention

`ThreadMXBean` belongs to `java.lang.management`. It provides counts and durations for threads blocked entering a monitor, along with information about which threads hold or wait on locks.

Obtain the bean:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Thread contention monitoring is disabled by default. Check support and enable it when needed:

```java
if (bean.isThreadContentionMonitoringSupported()) {
    bean.setThreadContentionMonitoringEnabled(true);
}
```

Key methods on `ThreadInfo`:

| Method | Meaning |
|---|---|
| `getBlockedCount()` | Total number of times the thread was `BLOCKED` entering or re-entering a monitor |
| `getBlockedTime()` | Approximate accumulated time, in milliseconds, spent in `BLOCKED` state since contention monitoring was enabled |
| `getWaitedCount()` | Number of times the thread was in `WAITING` or `TIMED_WAITING` |
| `getWaitedTime()` | Approximate accumulated time spent in `WAITING`/`TIMED_WAITING` since monitoring was enabled |
| `getLockOwnerName()` | Name of the thread holding the object the current thread is waiting on |
| `getStackTrace()` | Stack trace of the thread |
| `getLockedMonitors()` | Intrinsic monitors currently held by the thread |
| `getLockedSynchronizers()` | Ownable synchronizers currently held by the thread |

`getBlockedTime()` only measures time spent in the `BLOCKED` state to acquire an intrinsic monitor; it is not lock hold time. `getWaitedTime()` includes both `WAITING` and `TIMED_WAITING` states, so not all of that value can be treated as lock-acquisition wait time.

Time values are approximate. Re-enabling contention monitoring resets the time statistics. Enable it only when measuring and remember to disable it after the investigation if you do not want to keep the measurement overhead.

In JDK 21, `ThreadMXBean` monitors platform threads; it does not provide equivalent management metrics for virtual threads. For virtual-thread applications, combine JFR with application-level instrumentation.

## 10. Java 17+ Example: Measuring Monitor Contention and ReentrantLock

The following example creates two scenarios:

1. One thread holds `synchronized` for a period of time while another thread must wait for the monitor.
2. One thread holds a `ReentrantLock` while another thread must park waiting for the lock.

The program enables `ThreadMXBean` contention monitoring, waits until the waiter is in the `BLOCKED` state, then reads `blockedCount` and verifies `blockedTime` is available.

Create `LockMeasurementDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class LockMeasurementDemo {
    private static void pause() {
        try {
            Thread.sleep(1_200);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void measureMonitor(ThreadMXBean bean)
            throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (monitor) {
                System.out.println("MONITOR_HOLDER_ENTERED");
                entered.countDown();
                pause();
                System.out.println("MONITOR_HOLDER_EXITING");
            }
        }, "monitor-holder");

        Thread waiter = new Thread(() -> {
            try {
                entered.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (monitor) {
                System.out.println("MONITOR_WAITER_ACQUIRED");
            }
        }, "monitor-waiter");

        holder.start();
        waiter.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (waiter.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(1);
        }

        if (waiter.getState() != Thread.State.BLOCKED) {
            throw new IllegalStateException("Waiter did not block on monitor");
        }

        ThreadInfo info = bean.getThreadInfo(waiter.getId());
        if (info == null) {
            throw new IllegalStateException("Waiter ThreadInfo is unavailable");
        }

        System.out.println("MONITOR_BLOCKED_COUNT=" + info.getBlockedCount());
        System.out.println("MONITOR_BLOCKED_TIME_AVAILABLE="
                + (info.getBlockedTime() >= 0));

        holder.join();
        waiter.join();
    }

    private static void measureReentrantLock() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch entered = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                System.out.println("REENTRANT_HOLDER_ENTERED");
                entered.countDown();
                pause();
                System.out.println("REENTRANT_HOLDER_EXITING");
            } finally {
                lock.unlock();
            }
        }, "reentrant-holder");

        Thread waiter = new Thread(() -> {
            try {
                entered.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            lock.lock();
            try {
                System.out.println("REENTRANT_WAITER_ACQUIRED");
            } finally {
                lock.unlock();
            }
        }, "reentrant-waiter");

        holder.start();
        waiter.start();
        holder.join();
        waiter.join();
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (!bean.isThreadContentionMonitoringSupported()) {
            throw new UnsupportedOperationException(
                    "Thread contention monitoring is not supported");
        }

        bean.setThreadContentionMonitoringEnabled(true);
        measureMonitor(bean);
        measureReentrantLock();
        System.out.println("DONE");
    }
}
```

Compile:

```sh
javac LockMeasurementDemo.java
```

Run:

```sh
java LockMeasurementDemo
```

Stdout on a HotSpot JDK supporting contention monitoring:

```text
MONITOR_HOLDER_ENTERED
MONITOR_BLOCKED_COUNT=1
MONITOR_BLOCKED_TIME_AVAILABLE=true
MONITOR_HOLDER_EXITING
MONITOR_WAITER_ACQUIRED
REENTRANT_HOLDER_ENTERED
REENTRANT_HOLDER_EXITING
REENTRANT_WAITER_ACQUIRED
DONE
```

`MONITOR_BLOCKED_COUNT=1` shows that the waiter entered the `BLOCKED` state once in the example. `MONITOR_BLOCKED_TIME_AVAILABLE=true` confirms that blocked time is readable; the exact millisecond value varies with scheduling and snapshot timing.

In the `ReentrantLock` section, the waiter typically parks via `LockSupport`. Therefore, `ThreadMXBean`'s `blockedCount` is not a complete measure of `ReentrantLock` wait time; use JFR `jdk.ThreadPark` or measure acquisition time at the application level.

This example creates contention intentionally to demonstrate measurement. Do not use sleep inside a critical section as a way to simulate production performance; real workloads should represent the actual work your application performs.

## 11. Measuring Wait Time and Hold Time in Code

If you need per-lock metrics at the application level, you can measure using `System.nanoTime()`. Use a monotonic clock for elapsed intervals; do not use `System.currentTimeMillis()` for durations.

Example with `ReentrantLock`:

```java
long waitStarted = System.nanoTime();
lock.lock();
long acquiredAt = System.nanoTime();

long holdNanos;
try {
    updateSharedState();
} finally {
    holdNanos = System.nanoTime() - acquiredAt;
    lock.unlock();
}

long waitNanos = acquiredAt - waitStarted;
metrics.recordLockWait("account-cache", waitNanos);
metrics.recordLockHold("account-cache", holdNanos);
```

In this example, metrics are recorded after unlocking so that recording metrics does not extend the critical section. In production code, ensure the metric-recording call does not swallow the original exception, and prefer histograms to capture distributions rather than storing only averages.

With `synchronized`, you can capture a timestamp before entering the block and immediately after entering; record the metrics after exiting the block to avoid extending monitor hold time.

Do not log on every acquisition on a hot code path. Logging can introduce I/O, its own locks, and allocations, altering the very contention you are trying to measure. Prefer low-overhead histograms/counters, sampling, or JFR.

## 12. Measuring Lock Queues and ReentrantLock State

`ReentrantLock` provides several observation methods:

| Method | Meaning |
|---|---|
| `isLocked()` | Whether any thread currently holds the lock |
| `isHeldByCurrentThread()` | Whether the current thread holds the lock |
| `hasQueuedThreads()` | Whether any threads are waiting for the lock |
| `getQueueLength()` | Estimate of the number of threads waiting |
| `isFair()` | Whether the lock uses a fairness policy |

`getQueueLength()` is an estimate, not an exact figure at every instant. Queue observation methods are suitable for diagnostics and should not be used for synchronization conditions or business logic.

A fair `ReentrantLock` attempts to grant access in arrival order, which can reduce throughput. A non-fair lock often delivers higher throughput in some workloads but can cause threads to wait longer. Benchmark and check tail latency before changing fairness.

## 13. Benchmarking Locks with JMH

JFR and thread dumps are for investigating running applications. When you want to compare two lock implementations under a controlled workload, use the Java Microbenchmark Harness (JMH).

JMH supports warm-up, measurement iterations, forks, and thread groups. The example below compares an intrinsic monitor with `ReentrantLock` in a pre-configured JMH benchmark project:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Group;
import org.openjdk.jmh.annotations.GroupThreads;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;

@BenchmarkMode(Mode.SampleTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class LockBench {
    @State(Scope.Group)
    public static class MonitorState {
        long value;
    }

    @State(Scope.Group)
    public static class ReentrantState {
        final ReentrantLock lock = new ReentrantLock();
        long value;
    }

    @Benchmark
    @Group("monitor")
    @GroupThreads(4)
    public void monitor(MonitorState state) {
        synchronized (state) {
            state.value++;
        }
    }

    @Benchmark
    @Group("reentrant")
    @GroupThreads(4)
    public void reentrant(ReentrantState state) {
        state.lock.lock();
        try {
            state.value++;
        } finally {
            state.lock.unlock();
        }
    }
}
```

Run the benchmark from the configured JMH project:

```sh
mvn clean package
```

```sh
java -jar target/benchmarks.jar '.*LockBench.*'
```

`Mode.SampleTime` shows the latency distribution of individual operations; JMH output can report percentiles. `@State(Scope.Group)` shares state across threads in the same group, while `@GroupThreads(4)` creates four threads contending on that state.

The benchmark above is a small illustrative workload. In real benchmarks, place the same critical-section workload in both implementations, use representative data, keep thread counts and environments identical, run sufficient warm-ups/forks, and check both throughput and p95/p99. Do not put logging or I/O inside the critical section unless that is the exact workload you intend to simulate.

Do not choose `ReentrantLock` just because a tiny microbenchmark is faster than `synchronized`. Differences can vary by JVM, CPU, critical section, thread count, fairness, and how the application uses the lock.

## 14. Identifying Common Contention Patterns

| Symptom | Possible cause | Remediation |
|---|---|---|
| One lock has many waiters | Many threads accessing a single shared resource | Split the lock or partition the data |
| Long hold time | Critical section contains computation/I/O or work that does not need locking | Move unprotected work outside the lock |
| High p99 wait time with low average | Some requests hit long queues or an owner holds the lock unusually long | Inspect percentiles, owner threads, and event timelines |
| Many threads waiting on a cache lock | Cache has a serialized write/update point | Use a concurrent cache, immutable snapshots, or sharding |
| Lock held during network/database calls | Slow I/O extends lock hold time | Fetch data outside the lock, re-check state, then perform a short update |
| Multiple nested locks | Inconsistent acquisition ordering or complex critical sections | Standardize lock ordering and reduce nesting |
| High `ReentrantLock` parks | Many threads waiting on a synchronizer or `Condition` | Inspect `jdk.ThreadPark`, queues, and signaling logic |
| Low CPU with high latency | Threads mostly waiting on locks or I/O | Measure wait time, thread states, and owners |
| High CPU alongside contention | Lock convoy, retries, spinning, or heavy critical sections | Correlate JFR, CPU profiles, and lock timelines |

These symptoms only generate hypotheses. Inspect events and stack traces to find the actual code path before making architectural changes.

## 15. Distinguishing Contention from Deadlock

Contention means threads must wait for a lock, but the lock is eventually released. Deadlock is a cycle of waiting that cannot make progress on its own.

You can check for deadlocks via `ThreadMXBean`:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] deadlocked = bean.findDeadlockedThreads();
if (deadlocked == null) {
    System.out.println("NO_DEADLOCK");
} else {
    System.out.println("DEADLOCK_THREADS=" + deadlocked.length);
}
```

`findDeadlockedThreads()` detects wait cycles across object monitors and ownable synchronizers supported by the JVM. This API is designed for troubleshooting, not as a synchronization coordination mechanism; the operation can be expensive and only considers platform threads.

`findMonitorDeadlockedThreads()` only detects deadlocks involving object monitors. If you need to include `ReentrantLock`/ownable synchronizers, use `findDeadlockedThreads()`.

Do not run deadlock detection continuously at high frequency. Use it when there are signs of a hang or when collecting incident diagnostics.

## 16. Virtual Threads and Lock Contention

Virtual threads change how the JVM schedules threads, but they do not eliminate lock contention. Many virtual threads can still contend for the same monitor or synchronizer.

Key points to remember:

- `ThreadMXBean` in JDK 21 only monitors platform threads and does not manage virtual threads.
- Thread dumps and JFR may offer different views into thread/park events; check your specific tools and JDK version.
- `synchronized` can cause carrier-thread pinning in certain virtual thread and native/monitor code paths; JFR provides the `jdk.VirtualThreadPinned` event to investigate pinning on JDKs that support virtual threads.
- Lock contention and carrier-thread pinning are two distinct issues; do not lump them into a single metric.

When using virtual threads, measure operation-level latency and JFR events. Check both lock waits and pinning if throughput drops unexpectedly.

## 17. Reducing Contention After Measuring

Once you have identified the right lock and code path, consider the following approaches:

- Shorten the critical section: hold the lock only around the state reads/writes that genuinely need protection.
- Avoid I/O, logging, network calls, or external callbacks while holding a lock.
- Partition data into shards to reduce the number of threads sharing one lock.
- Use concurrent collections when their semantics fit.
- Use immutable snapshots or copy-on-write for read-heavy, write-light workloads.
- Reduce the frequency of shared-state updates via batching or aggregation.
- Use `ReadWriteLock` when the read/write ratio and fairness characteristics fit; benchmark before switching.
- Use `tryLock`/timeouts when you need to avoid unbounded waits and have a proper timeout-handling path.
- Standardize multi-lock acquisition order to prevent deadlocks.
- Evaluate fairness based on tail latency and starvation, not throughput alone.

Do not remove a lock if the data still needs protection. Synchronization changes must preserve atomicity, visibility, and application invariants.

## 18. Tool Overhead and Limitations

Each tool measures a different angle:

| Tool | Good at measuring | Limitations |
|---|---|---|
| Thread dump | Thread states, stacks, monitor owners, and awaited locks | Point-in-time snapshot; does not provide latency distributions |
| JFR | Duration events, threads, stack traces, and timelines | Depends on event settings/thresholds; detailed configs produce more data |
| `ThreadMXBean` | Blocked count/time and thread synchronization info | Contention monitoring is off by default; `blockedTime` focuses on intrinsic monitors |
| JConsole/JMX | Observing `Threading` MXBean and runtime metrics | Does not automatically provide wait/hold histograms per application lock |
| JMH | Comparing throughput/latency under controlled workloads | Does not fully represent production if the workload differs from reality |
| Application instrumentation | Wait/hold time for specific locks or operations | Measuring at the wrong place or recording metrics inside the critical section can skew results |

Measurement itself has a cost. Large thread dumps, JFR profile recordings, stack traces, and overly detailed instrumentation can all increase overhead. Start with short durations and essential events; expand once you know the question you need to answer.

## 19. Common Mistakes When Measuring Locks

| Symptom | Cause | Fix |
|---|---|---|
| No `BLOCKED` threads seen, yet latency is high | Application uses `ReentrantLock`, `Condition`, or parking mechanisms | Check `WAITING`/`TIMED_WAITING`, `ThreadPark`, and JFR |
| `blockedTime` returns `-1` | Thread contention monitoring is not enabled | Check support and call `setThreadContentionMonitoringEnabled(true)` |
| `blockedTime` is `0` | Snapshot taken too early, wait was too short, or thread never entered `BLOCKED` | Re-sample and use an appropriate JFR threshold |
| No JFR `JavaMonitorEnter` events | Event disabled, threshold too high, or no monitor contention | Check `JFR.check verbose=true` and event settings |
| No `ThreadPark` events | Wait was shorter than threshold or event was not enabled | Check event threshold and stack trace settings |
| `getWaitedTime()` is very large | Thread waited on notification, park, or timeout | Do not treat the whole value as lock-acquisition time; inspect blockers and stacks |
| Queue length fluctuates wildly | It is a point-in-time estimate when called | Use multiple samples and JFR timelines; never use it as a synchronization condition |
| Benchmark results differ from production | Different workload, thread count, CPU, JVM, or critical section | Reproduce a realistic workload and compare using JFR |
| Fair lock has lower throughput | Fairness can reduce barging and alter scheduling | Compare throughput alongside p95/p99 and starvation |
| JFR file has no stack traces | Event settings did not enable `stackTrace` or recording used a different config | Enable stack traces for the target events and record again |

## 20. Incident Lock Measurement Runbook

1. Record the timestamp and the request/operation experiencing elevated latency.
2. Find the PID using `jcmd -l`.
3. Capture `jcmd PID Thread.print -l` several times, a few seconds apart.
4. Locate waiter threads, lock owners, and repeated stack frames.
5. Start a short JFR recording with `jdk.JavaMonitorEnter` and `jdk.ThreadPark`.
6. Dump the `.jfr` file and open it in JMC.
7. Group events by duration, thread, stack trace, and monitor/blocker.
8. Add application-level wait/hold time measurement if you need to separate acquisition wait from critical-section duration.
9. Identify the code path holding the lock and why the lock must be held.
10. Test one small change in staging or a controlled workload.
11. Re-measure with the same thread count, workload, and JVM settings.
12. Compare throughput, p95/p99, wait time, hold time, and CPU.
13. Document the results, JDK version, event thresholds, and commands used.

## 21. Checklist

- [ ] Identified whether the lock is an intrinsic monitor or an explicit synchronizer.
- [ ] Distinguished `BLOCKED` from `WAITING`/`TIMED_WAITING`.
- [ ] Measured wait time and hold time separately.
- [ ] Captured multiple thread dumps to identify owners and waiters.
- [ ] Used `jcmd Thread.print -l` when lock information was needed.
- [ ] Checked `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, and `jdk.ThreadPark`.
- [ ] Verified JFR thresholds and stack trace settings.
- [ ] Noted that `ThreadMXBean` contention monitoring is disabled by default.
- [ ] Understood that `getBlockedTime()` is not hold time and does not cover all `ReentrantLock` waits.
- [ ] Used JMH when controlled lock benchmarking was needed.
- [ ] Compared throughput alongside p95/p99 under equivalent workloads.
- [ ] Evaluated the overhead of thread dumps, JFR, and instrumentation.
- [ ] Checked for deadlocks separately from normal contention.
- [ ] Preserved correctness and memory visibility after optimization.

## 22. References

- Oracle JDK 21 Tool Reference — The jcmd Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 API — ThreadMXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 21 API — ThreadInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html
- Java SE 21 API — jdk.jfr package and event settings: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- OpenJDK JFR default.jfc event configuration: https://github.com/openjdk/jdk/blob/master/src/jdk.jfr/share/conf/jfr/default.jfc
- OpenJDK JMH project: https://github.com/openjdk/jmh

Effective lock contention measurement combines snapshots with time-series metrics. Thread dumps help locate waiting threads and owners; JFR measures durations and stack traces for monitor/park events; `ThreadMXBean` provides blocked counts and times for platform threads; and JMH helps compare locks under controlled workloads. After pinpointing the right critical section, re-measure under the same workload to confirm that both throughput and tail latency have improved.

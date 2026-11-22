# Lock Contention, Starvation, and Fairness Trade-offs in Java

## 1. Context and Objectives

A multithreaded program does not automatically run faster. If multiple threads frequently contend for the same lock, most of the time can be spent waiting, context-switching, or waking up threads instead of doing useful work. That is **lock contention**. Under certain scheduling behaviors or lock-granting policies, a thread may wait for a very long time even while other threads keep making progress: that is **starvation**. Switching from a nonfair lock (*nonfair*) to a fair lock (*fair*) can improve ordered service, but it usually comes at a performance trade-off.

This lesson focuses on **general Java concurrency**: `synchronized`, `ReentrantLock`, `ReentrantReadWriteLock`, and techniques for measuring/reducing contention; it is framework-independent.

After this lesson, you will be able to:

- Identify lock contention in code and in runtime metrics.
- Distinguish contention, starvation, deadlock, livelock, and slowdowns caused by CPU or I/O.
- Explain the difference between fair and nonfair locks, along with the limitations of each policy.
- Use `ReentrantLock(true)` properly and recognize the exception with `tryLock()`.
- Choose optimization measures based on throughput, tail latency, progress guarantees, and correctness.

## 2. How Does Lock Contention Happen?

A **critical section** is a section of code accessed by only one thread (or a permitted number of threads) at a time to protect shared state. The more operations a lock encloses, the longer the lock hold time (*hold time*). When multiple threads need the same lock, they must coordinate access to the protected region.

```text
Thread A: [acquire lock] [read/modify state...] [release lock]
Thread B:     [want lock] [----- wait -----] [acquire] [modify] [release]
Thread C:          [want lock] [---------- wait ----------] ...
```

Waiting can manifest in the following forms:

- A thread waiting on a `synchronized` monitor usually has the `BLOCKED` state in a thread dump.
- A thread waiting on a `ReentrantLock` is usually parked via the synchronization mechanism of `java.util.concurrent.locks`; snapshots may show `WAITING` or `TIMED_WAITING`, not necessarily `BLOCKED`.
- Some lock acquisitions do not have to wait because the lock is free; some brief contention only incurs minor coordination overhead.
- Retry loops can exist in lock-free (*lock-free*) algorithms, but that is a different form of contention; not every retry should be called lock contention.

Factors that increase contention:

1. **High lock acquisition frequency:** many small operations all have to enter the same critical section.
2. **Long lock hold time:** heavy processing, I/O, synchronous logging, network waits, sleeping, or invoking callbacks while still holding the lock.
3. **Many threads touching the same state:** a single global counter, a single map, or a shared queue.
4. **Load skew:** a hot key or a group of tasks continuously holding the lock while another group waits.
5. **Combining multiple locks:** a thread holding lock A and waiting for B keeps A occupied longer, potentially creating a wait chain.

A contended lock creates a **serialization** point: adding threads does not make the critical section run in parallel. If the code that must run sequentially accounts for a large fraction, total speedup cannot scale linearly with core count. Creating more threads can even slow the system down.

## 3. Contention, Starvation, Deadlock, and Livelock

| Phenomenon | Main Symptoms | Is the system still making progress? | Approach |
| --- | --- | --- | --- |
| **Contention** | Multiple threads wait on the same lock; lock queue or blocked/park time increases. | Usually yes; threads still complete one after another. | Reduce lock hold time, lock frequency, shared state, and re-measure. |
| **Starvation** | A thread or group is denied the chance to run/acquire a lock for a very long time. | Possibly: other threads still complete. | Review fairness policy, priority levels, continuous load sources, and scheduler/queue design. |
| **Deadlock** | Resource dependency cycle: A holds L1 waiting for L2, B holds L2 waiting for L1. | Threads in the cycle make no progress without intervention. | Enforce lock ordering, reduce nested locks, use timeouts, and analyze thread dumps. |
| **Livelock** | Threads continuously react/retry yet still fail to complete useful work. | Activity occurs, but no completion. | Backoff, retry limits, break symmetry, and coordinate progress. |

**Starvation is not synonymous with "waiting a long time once."** A single long wait can be caused by an expensive critical section, a GC pause, CPU scarcity, I/O, or OS scheduling. To conclude starvation, you must look at **a repeating pattern and disparity in progress**: some threads are continuously served while another thread is delayed or gets no opportunity.

Typical example: T1 is waiting on a nonfair `ReentrantLock`. Every time the lock is released, a newly running thread can grab the lock ahead of T1. If this repeats long enough, T1 suffers resource starvation. This is a **risk**, not a guarantee that a nonfair lock always causes starvation.

Starvation can also stem from thread priority, an executor lacking workers, tasks monopolizing a pool, or the OS not scheduling CPU time; using a fair lock only addresses **part** of the problem.

## 4. What Does Java Lock Fairness Mean?

### `synchronized` and monitors

`synchronized` guarantees mutual exclusion and *happens-before* relationships when unlocking/locking the same monitor. The Java specification **does not guarantee** that threads enter a monitor in FIFO order. You should not assume the longest-waiting thread will always be chosen next.

```java
private final Object monitor = new Object();

void update() {
    synchronized (monitor) {
        // Only the section that actually protects shared state.
    }
}
```

The advantages of `synchronized` are conciseness, readability, and automatic monitor release when exiting the block even if an exception is thrown. It has no fair/nonfair parameter and no `tryLock` or timed lock acquisition API equivalent to `ReentrantLock`.

### Nonfair `ReentrantLock` (default)

`new ReentrantLock()` is equivalent to a lock with a nonfair policy; under contention, a newly arriving thread can **barge**: acquire the lock ahead of a thread that has been waiting longer. This can reduce the overhead of direct handoff between waiting threads and increase throughput in some workloads, but it makes no commitment regarding service order or a bound on a specific thread's wait time.

### Fair `ReentrantLock(true)`

`new ReentrantLock(true)` uses a policy that favors threads that have been waiting longer **when there is contention**, applicable to lock acquisition methods governed by the fairness policy. This is a roughly FIFO policy at the lock queue level, not a promise that every thread will be scheduled fairly by the CPU or have a fixed maximum wait time.

```java
import java.util.concurrent.locks.ReentrantLock;

ReentrantLock lock = new ReentrantLock(true);

lock.lock();
try {
    // Access shared state.
} finally {
    lock.unlock();
}
```

The snippet above only illustrates usage inside a class/method; it is **not a standalone Java program**.

**An easily overlooked exception:** `tryLock()` **with no arguments** can immediately acquire an available lock **regardless** of whether the lock is configured as fair or nonfair; it can barge ahead of waiting threads. When you need to honor the fair policy for a timed lock attempt, use `tryLock(timeout, TimeUnit)`, including `tryLock(0, TimeUnit.SECONDS)` if you want an immediate attempt that still respects fairness. Using `lockInterruptibly()` also allows responding to interrupts while waiting for the lock.

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

// The lock variable is already initialized in its owning scope:
boolean acquired = lock.tryLock(100, TimeUnit.MILLISECONDS);
if (acquired) {
    try {
        // Short processing, avoid blocking I/O when possible.
    } finally {
        lock.unlock();
    }
} else {
    // Could not acquire lock within the deadline; retry/backoff/fail as required.
}
```

Calling `tryLock(timeout, unit)` can throw `InterruptedException`, so the snippet must reside in a method that declares `throws InterruptedException` or handles the exception. Every successful lock acquisition must be paired with `unlock()` in a `finally` block.

## 5. What Does Fairness Trade Off?

A practical perspective is to separate the criteria, because **"more fair" does not necessarily mean "faster."**

| Criterion | Nonfair lock | Fair lock |
| --- | --- | --- |
| Lock-granting order | Allows barging; no strict priority by wait time. | Favors longer-waiting threads under contention, for fairness-respecting APIs. |
| Throughput | Can be higher when lock hold times are short and contention is high. | Often lower under contention due to scheduling/wakeup and handoff overhead. |
| Wait time variance | Some threads may be repeatedly overtaken, resulting in high tail latency. | Can reduce variance in lock acquisition wait times across threads. |
| Starvation | No guarantee against starvation. | Reduces starvation risk from barging; does not solve starvation caused by the CPU scheduler or external tasks. |
| Under low contention | Difference can be small. | Difference can be small; measure on real workloads. |
| Maximum wait time guarantee | None. | Still **no** absolute upper bound on wait time. |

A fair lock can force threads to hand off the lock in queue order instead of letting a currently running thread immediately claim it. That increases wakeup/context-switch overhead and reduces cache locality in some situations. However, both throughput and tail latency depend on thread count, critical section length, CPU, scheduling, GC frequency, and workload; there is no fixed speedup/slowdown ratio.

**Do not choose fairness as a "just to be safe" parameter without a requirement.** First identify the problem you need to fix: insufficient throughput, a group of requests starving, missed deadlines, or a rising count of blocked threads? Once correctness is ensured, compare both throughput and wait time distributions, especially p95/p99, instead of looking only at the average.

Also do not equate lock-level fairness with **business priority** fairness: for example, priority orders require a scheduling queue with its own priority policy, which cannot be expressed with `ReentrantLock(true)` alone.

## 6. Java 17+ Program: The Same Workload with Fair and Nonfair Locks

The following example creates four workers that all increment a single counter. They start nearly together using a `CountDownLatch`, and each increment must acquire the same lock. Run it with `ReentrantLock(false)` and `ReentrantLock(true)` in turn to observe that **both guarantee the counter value**, while actual ordering and speed may differ. We intentionally **do not print fixed timings** because scheduling is non-deterministic and a small example is not a benchmark.

Create the file **`LockContentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class LockContentionDemo {
    private static final int WORKERS = 4;
    private static final int UPDATES_PER_WORKER = 4_000;

    private static final class Counter {
        private final ReentrantLock lock;
        private long count;

        Counter(boolean fair) {
            this.lock = new ReentrantLock(fair);
        }

        void increment() {
            lock.lock();
            try {
                count++;
            } finally {
                lock.unlock();
            }
        }

        long valueAfterWorkersFinish() {
            return count;
        }
    }

    private static long runCase(boolean fair) throws Exception {
        Counter counter = new Counter(fair);
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < WORKERS; worker++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();

                    for (int i = 0; i < UPDATES_PER_WORKER; i++) {
                        counter.increment();
                    }
                    return null;
                }));
            }

            if (!ready.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers chưa sẵn sàng");
            }

            start.countDown();

            for (Future<?> future : futures) {
                future.get(); // Wait for the worker to finish and surface errors if the task fails.
            }

            return counter.valueAfterWorkersFinish();
        } finally {
            start.countDown(); // Prevent workers from hanging if an earlier branch throws an error.
            pool.shutdown();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("nonfair: " + runCase(false));
        System.out.println("fair: " + runCase(true));
    }
}
```

Compile and run:

```bash
javac LockContentionDemo.java
java LockContentionDemo
```

Output when both runs complete normally:

```text
nonfair: 16000
fair: 16000
```

**Why is the output deterministic?** Each worker performs exactly `4_000` increments, totaling `4 × 4_000 = 16_000`, and `Future.get()` only returns after the task finishes. Operations performed before a task completes are visible after `Future.get()`; there is no race when `main` reads `count`. `ReentrantLock` protects `count++` against lost updates.

**Why does the output not prove performance?** The program does not measure time, and the number of updates is too small to draw stable conclusions. In another workload, the two policies might be close; a fair lock typically incurs more overhead as contention rises. To benchmark for decision-making, use JMH with warmup, multiple measurement iterations, JVM forks, multiple thread counts, and proper handling of GC/JIT noise; measure alongside latency distributions and actual contention levels.

**A closer look at resource cleanup:** `pool.shutdown()` and `awaitTermination(...)` are called in `finally`; `shutdownNow()` only attempts to interrupt still-running tasks. In this example, tasks respond to interrupts while waiting on `CountDownLatch`. In general-purpose code, you also need a policy for waiting/restoring interrupts and managing cancelled tasks.

## 7. Reducing Contention Is Usually More Effective Than Just Switching to a Fair Lock

Before choosing fairness, look for parts of the lock hold time that can be eliminated or reduced.

### 7.1. Shorten the critical section

**Inappropriate:** holding the lock across I/O operations or computations that do not need protection.

```java
synchronized (monitor) {
    // Read needed state...
    // Make HTTP calls, read files, write slow logs, or run long computations.
    // Update state...
}
```

**Better when logic allows:** capture the needed values inside the critical section, process independently outside, and then update the result under a short lock. You must re-check conditions when writing the result if the state could have changed during the computation.

```java
long snapshot;
synchronized (monitor) {
    snapshot = sharedValue;
}

long result = expensivePureComputation(snapshot);

synchronized (monitor) {
    // Only apply result if the condition/version is still valid.
    // Otherwise, retry or handle the conflict per business rules.
}
```

This is illustrative code residing inside a class/method with the corresponding variables and functions. Not every atomic transaction can be split into two locked regions while preserving semantics; you must verify invariants and consistency.

### 7.2. Reduce shared state

- **Thread confinement:** each worker processes its own state and only aggregates after finishing.
- **Partitioning/sharding:** split data by key or independent groups, avoiding a single global lock.
- **Immutable snapshots:** read an immutable copy and update via an appropriate mechanism to reduce read locking.
- **`LongAdder`:** useful for heavily contended counters when you do not need a strictly linearizable snapshot together with other state. Calling `sum()` during concurrent updates is not an atomic snapshot.
- **`ConcurrentHashMap`:** replace a globally locked map when the primary need is concurrent per-key operations. It does not automatically make multi-step sequences atomic outside the APIs it provides.

Using `AtomicInteger`/`AtomicLong` can eliminate locks for a single update, but when multiple variables must maintain a joint invariant, switching to separate atomics can break correctness.

### 7.3. Change lock scope or synchronization primitive

- `ReentrantReadWriteLock`: allows multiple readers to hold the read lock concurrently while writers are exclusive. Can increase throughput when the read ratio is high and the critical section is large enough; if writes are frequent or reads are very short, overhead can make it slower.
- `StampedLock`: supports optimistic reads with `validate(stamp)`, but the API is complex, non-reentrant, and does not guarantee fairness; it should not be chosen solely to "prevent starvation."
- `Semaphore`: limits the number of concurrent operations. `Semaphore(true)` has a FIFO policy for fairness-respecting permit acquisitions, though `tryAcquire()` without a timeout can still barge.
- `BlockingQueue` or a state-owning worker model: funnel updates through a queue so a single place processes them sequentially, when appropriate for ordering and latency requirements.

Changing primitives must be grounded in data semantics. If you need a transaction protecting multiple fields, replacing `ReentrantLock` with `ConcurrentHashMap` does not automatically protect that transaction.

## 8. Detecting Contention and Starvation in the JVM

### 8.1. Signals to watch for

- Throughput plateaus or drops as worker count increases.
- p95/p99 latency increases, with many threads waiting on locks or on the executor.
- CPU may be underutilized while requests are still slow because threads wait on each other; conversely, high CPU does not prove contention either.
- One group of threads has a much lower completion count than another group under the same load conditions.
- A single monitor or stack frame repeatedly appears at the wait site across multiple thread dumps.

### 8.2. Thread dumps

You can use `jcmd <pid> Thread.print -l` to inspect thread states and stacks (replace `<pid>` with the actual PID). Example of a thread waiting on a monitor:

```text
"worker-7" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at example.Inventory.update(Inventory.java:42)
    - waiting to lock <...> (a java.lang.Object)
```

The thread dump snippet above is illustrative; thread names and monitor addresses in a real JVM will differ. Look for multiple threads waiting on the same lock and the thread currently holding it. With `ReentrantLock`, thread dumps may show `LockSupport.park` and `AbstractQueuedSynchronizer` instead of the `BLOCKED` state.

A thread dump is a **point-in-time snapshot**. A single snapshot showing a waiting thread is not enough to prove starvation; you need multiple samples over time or longer-running telemetry.

### 8.3. Java Flight Recorder (JFR)

JFR is useful for capturing lock and scheduling events at reasonable overhead. On supported JDKs, you can start a recording at runtime with a command like:

```bash
jcmd <pid> JFR.start name=locks settings=profile duration=60s filename=locks.jfr
```

Open `locks.jfr` with Java Mission Control or a compatible JFR reader. Notable events include:

- `jdk.JavaMonitorEnter`: waiting to enter a `synchronized` monitor.
- `jdk.JavaMonitorWait`: waiting via `Object.wait()` (different from contention to *enter* a monitor).
- `jdk.ThreadPark`: park duration may relate to `ReentrantLock`, `Condition`, queues, or various other wait mechanisms; inspect the stack trace to identify the source.

Visibility, event thresholds, and overhead depend on the JFR configuration; do not treat a single event as proof of starvation. Test in an appropriate environment before enabling profiling in production.

### 8.4. API metrics

`ReentrantLock.getQueueLength()` estimates the number of threads waiting to acquire the lock; this is an **instantaneous estimate**, not an exact count or a stable guarantee for coordination logic. `ReentrantLock.hasQueuedThreads()` likewise only reflects the state observed at the moment of the call. Do not write correctness logic based on these estimated values.

`ThreadMXBean` supports querying thread states and, when supported/enabled by the JVM, blocked/waited times. These metrics do not fully replace specialized events or profilers. For a service with multiple kinds of waits, combine traces, latency histograms, completed task counts, and thread counts in each state.

## 9. When Should You Enable Fair Locks?

Consider `ReentrantLock(true)` when:

1. There is repeated evidence that some threads are frequently barged in the lock queue and make unacceptable progress.
2. Requiring relative ordering guarantees for resource access is more important than maximizing total throughput.
3. You have measured and accepted the impact on throughput/latency under target load.
4. All code paths using the lock adhere to the policy; none inadvertently mix in untimed `tryLock()`.

**Do not enable fairness just because you see many threads waiting.** If a lock is held too long, switching to fair still forces every thread to serialize on that critical section. First measure lock hold time, reduce work under the lock, and reduce sharing.

For tasks with deadlines, timed acquisition enables controlled failure handling:

```java
if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
    throw new IllegalStateException("Không lấy được lock trong hạn");
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

The code above requires a `lock` variable, an `updateSharedState()` method, and handling/declaring `InterruptedException` in the enclosing method. A timeout does not by itself make a request succeed; it provides a **fallback path when the lock cannot be acquired**. If interrupted, prefer propagating the exception or restoring the interrupt status if catching without rethrowing.

## 10. Benchmarking and Properly Evaluating Fairness

A useful experiment needs to observe both the **benefits and the costs**:

| Metric | Why measure it? |
| --- | --- |
| Throughput (operations/s) | Does fairness reduce the total amount of completed work? |
| Average and p50/p95/p99 acquisition latency | Who waits the longest; does tail latency increase or decrease? |
| Completed operations per worker | Detect imbalance and threads progressing too slowly. |
| Hold time distribution | Explain bottlenecks caused by long critical sections. |
| Waiting thread count, JFR lock events | Confirm which lock is actually the bottleneck. |
| CPU, GC, scheduler/park activity | Distinguish lock contention from other causes. |

Keep the logic and critical section size identical between the two trials; change only the fair/nonfair policy when evaluating fairness in isolation. Test across multiple load levels: fewer threads than cores, roughly equal to cores, and exceeding cores. Use JMH to minimize bias from warmup, dead-code elimination, and JIT. For benchmarks with shared resources, JMH has appropriate state/thread configurations; do not rely on a single `System.nanoTime()` run as conclusive evidence.

In real applications, evaluate against SLAs: sometimes reducing starvation matters more than throughput; other times an option that boosts throughput but worsens p99 fails to meet service requirements.

## 11. Common Mistakes and Fixes

1. **Assuming a fair lock guarantees zero starvation across the entire system.** It only affects the lock-granting policy; thread scheduling, priorities, executors, and other locks can still starve tasks.
2. **Assuming fair = strict FIFO for every call.** The no-argument `tryLock()` on a fair `ReentrantLock` can still barge.
3. **Enabling fairness to cure a critical section held too long.** That does not address the root cause; measure and narrow the locked region.
4. **Omitting `unlock()` when an exception occurs.** Always use `try/finally`. Forgetting to unlock can leave all other threads waiting indefinitely.
5. **Placing I/O, uncontrolled callbacks, or `Thread.sleep` inside a lock.** Extends lock hold times, increases tail latency, and risks deadlock/reentrancy.
6. **Confusing `BLOCKED` threads with all forms of synchronization waiting.** `ReentrantLock` typically parks threads; inspect stack traces and JFR instead of filtering only for `BLOCKED`.
7. **Drawing conclusions from a single thread dump or benchmark.** Contention varies with load; collect multiple samples, use a profiler, and compare statistically.
8. **Replacing locks with atomics while forgetting multi-variable invariants.** It may be faster but produce corrupt data; correctness always comes before optimization.
9. **Using an unbounded busy-spin `while (!lock.tryLock()) { }`.** Wastes CPU, increases contention pressure, and makes it harder for other threads to run; use blocking locks, timeouts, or appropriate backoff.
10. **Confusing starvation with deadlock.** Starvation can affect only one thread while the system still makes progress; deadlock is a wait cycle that cannot break itself.
11. **Adding threads indefinitely when throughput drops.** If a lock is a serialization bottleneck, adding threads usually increases waiting and context switching.
12. **Disabling all protection mechanisms for performance.** Race conditions and corrupted data are harder to detect than the few microseconds saved.

## 12. Decision Checklist and Exercise

When encountering high latency suspected to be caused by locks, ask yourself in order:

1. Which lock is contended? Is there evidence from thread dumps/JFR or is it just an assumption?
2. What percentage of time is spent inside the critical section and waiting for the lock?
3. Can I/O, computation, or callbacks be moved outside the lock?
4. Can state be partitioned, updates batched, or a more suitable primitive used?
5. If a single shared lock is still needed, does the system require maximum throughput or relatively fair progress?
6. Is any code using untimed `tryLock()` and breaking fairness assumptions?
7. How do fair/nonfair tests under realistic load compare on throughput, p95/p99, and per-worker progress?
8. Does the program have timeout, interrupt, and cleanup paths to avoid holding locks unintentionally?

**Hands-on exercise:** extend `LockContentionDemo`: have each worker measure total wait time from before `lock.lock()` until immediately after acquiring the lock, count completed operations, and run with different thread counts. Do not print measurements from inside each loop iteration (I/O will skew the results); aggregate after all workers finish. Compare fair/nonfair across multiple runs and interpret both throughput and per-worker disparity. Do not treat the print order of a single run as an API guarantee.

## 13. Key Takeaways

- **Contention:** multiple threads competing for the same lock, causing waiting and limiting parallelism.
- **Starvation:** a thread making little or no progress even while other threads continue working.
- **Fairness:** a policy that reduces the chance of long-waiting threads being barged; `ReentrantLock(true)` prioritizes longer waiters under contention, but does not guarantee CPU scheduling or maximum wait time.
- **Trade-off:** fairness can improve the distribution of lock acquisition opportunities, but increases handoff overhead and reduces throughput.
- **Practical priority:** verify correctness → measure contention → reduce locked scope / shared state → consider a fair lock when progress requirements and metrics support it.

**Java API Documentation:**

- [`ReentrantLock` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [`ReentrantReadWriteLock` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [`StampedLock` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
- [`ThreadMXBean` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [`Semaphore` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
# Concurrency Overhead in Java: Context Switch, Contention, and Scheduling

> **Scope:** Mechanisms and costs of concurrent programming in Java in general (JVM, Java threads, Java concurrency API, and the operating system). This content does not cover Spring-specific concurrency integrations.

## 1. Objectives and Big Picture

After this lesson, you will be able to:
- Explain why increasing the number of threads does not equate to increasing processing speed.
- Distinguish the costs of **context switch**, **contention** (resource contention), and **scheduling**, and recognize how they often amplify one another.
- Distinguish between threads that are running, ready to run, waiting on a lock, and waiting on I/O; interpret Java thread states accurately.
- Measure and verify bottlenecks, then choose an appropriate way to reduce overhead instead of arbitrarily increasing pool sizes or swapping synchronization mechanisms.

**Concurrency** allows multiple tasks to make progress over time; **parallelism** means multiple tasks are genuinely executing simultaneously on different compute resources. For example, if a machine has 2 available CPU cores and a program creates 100 threads performing continuous computation, only a number of threads corresponding to the available CPU resources can run at any given moment; the rest must wait their turn. Adding more threads can increase overhead without increasing CPU capacity.

A task can spend time on: executing useful code, waiting to be scheduled, contending for locks/resources, synchronizing data, waiting on I/O, and other JVM overhead. Phases can overlap across threads, so you cannot mechanically add up measurements from every thread to deduce wall-clock latency. Two fundamental metrics:

- **Throughput:** number of completed units of work per unit of time (e.g., requests/second).
- **Latency:** time from when a unit of work arrives until it completes; pay attention to p95/p99, not just the average.

A change that improves throughput can worsen tail latency if queues grow longer or some threads suffer CPU starvation.

## 2. Context Switch: Switching the CPU Between Threads

**Context switch** in this context mainly refers to the operating system pausing execution of one thread and resuming another, typically saving/restoring execution state such as registers, stack pointer, and scheduling metadata. With **platform threads** in Java (the standard usage in Java 17), the JVM maps Java threads to OS threads. This is an OS-level event; it is not synonymous with calling `Thread.yield()`, a `synchronized` operation, or every Java thread state transition.

Situations that typically cause a thread to yield or lose the CPU:
1. **Voluntary:** entering an I/O wait, waiting on a condition/lock, sleeping, or another wait mechanism that allows the OS to run another thread.
2. **Involuntary (preemption):** exhausting its allocated CPU time slice under the scheduling policy, being preempted by a higher-priority thread, or the OS needing to redistribute CPU time.
3. **CPU migration:** a thread is scheduled on a different core; this can reduce the benefit of warmed caches. Migration and context switch are two distinct events.

The cost of a switch is not just the CPU cycles spent saving/restoring registers. The interruption can affect caches and locality; switching between different address spaces also carries memory-management consequences depending on the CPU/OS. The actual cost **has no universal nanosecond constant across all machines**; it depends on hardware, load, thread type, caches, and kernel code paths.

**Example:** 8 CPU-bound threads competing for 2 cores, each performing a single long computation. The scheduler must rotate execution turns; when increased to 80 threads, the total useful computation does not magically increase 10x. More time may be lost to scheduling, context switching, and loss of locality.

Not every context switch is harmful: if a thread is waiting on I/O, switching the CPU to other work is how resources are kept usefully busy. The problem is **excessive switching relative to useful work**, especially when tasks are too small or the number of runnable threads exceeds CPU capacity.

### Java Thread States Are Not OS CPU Clocks

| `Thread.State` | Primary Meaning in Java | How to Interpret During Diagnosis |
|---|---|---|
| `RUNNABLE` | Running **or** ready to run in the JVM; may be waiting for a CPU turn from the OS | Do not assume the thread is definitely using CPU |
| `BLOCKED` | Waiting to enter/re-enter an **intrinsic monitor** (`synchronized`) | Suggests monitor contention |
| `WAITING` | Waiting indefinitely (e.g., `Object.wait`, `Thread.join`, `LockSupport.park`) | Not synonymous with deadlock |
| `TIMED_WAITING` | Waiting for a bounded time (`sleep`, timed wait/park/join) | May be intentional behavior |
| `NEW` / `TERMINATED` | Not yet started / finished | Does not directly reflect current load |

In particular, a thread waiting on a `ReentrantLock` can be in `WAITING` due to `LockSupport.park`, **not** `BLOCKED`. To determine the root cause, you must inspect the stack trace, lock owner, metrics, and history over time. A thread dump is a snapshot at a single point in time.

## 3. Contention: Multiple Threads Competing for the Same Resource

**Contention** occurs when multiple parties simultaneously need a finite resource: a monitor/lock, a frequently updated atomic variable, a shared queue, a connection pool, a file, memory/cache lines, or an I/O device. Under contention, a thread may:

- **Block/park:** yield the CPU and wait to be woken up; reduces wasted CPU, but incurs wake-up and rescheduling overhead.
- **Spin/retry:** repeatedly check or retry (e.g., a failing CAS loop); avoids some park calls for short waits, but burns CPU, generates memory traffic, and can slow down the thread currently holding the resource.
- **Queue up:** latency grows with the arrival rate and the time each party holds the resource. Even if each critical section is short, high enough total traffic to a hotspot still causes a bottleneck.

Types of contention in Java:

1. **Monitor:** `synchronized` protects consistency; if multiple threads need the same monitor, the protected code must execute sequentially. `Object.wait()` temporarily releases the corresponding monitor while waiting; `Thread.sleep()` does **not** release any held monitors.
2. **Explicit lock:** `ReentrantLock`, `ReadWriteLock`, or AQS-based synchronizers have their own mechanisms for managing waiters; do not assume they are always faster than `synchronized`. Fairness mode can make wait policies more predictable under some workloads, but usually trades off throughput.
3. **Atomic/CAS:** `AtomicLong.incrementAndGet()` avoids monitor locking, but updating a hot memory location causes contention and retries/cache coherence traffic. "Lock-free" does **not** mean "contention-free" or always fast.
4. **False sharing:** two logically independent values reside on the same cache line and are frequently written by different cores; the cache line still has to transfer ownership. This is not contention over the same lock. Measure in practice before using padding/`@Contended`.
5. **Non-CPU resources:** threads competing for a connection pool or queue can also increase latency; adding more threads does not create more database connections.

**Bottleneck example:** 16 workers all enter `synchronized (sharedLock)` to update a shared structure. Only one worker runs the critical section at a time; the remaining workers may block or wake up only to contend for the lock again. The result includes both **contention** and **wake-up/scheduling overhead**.

Reduce contention by shrinking the **critical section**, doing work outside the lock, partitioning data by key/shard, using thread-confined/local state and merging results afterward, or choosing primitives suited to the read/write frequency. Do not split locks arbitrarily if data invariants require updating multiple fields atomically together.

## 4. Scheduling: Who Runs, When, and on Which CPU?

There are at least **two scheduling layers** to distinguish:

- **Operating system:** decides which platform thread gets CPU time, priorities, preemption, and distribution across cores. Details depend on the OS and configuration; Java does not guarantee a fixed execution order.
- **Application / executor:** decides which task is assigned to which thread, which tasks stay in the queue, and how many workers the pool has. `ExecutorService`/`ThreadPoolExecutor` manages this layer; a task being dequeued **does not guarantee** its thread immediately gets CPU time.

Notes:
- `Thread.yield()` is only a **hint** to the scheduler, with no guarantee of yielding to any specific thread or ensuring fairness. Do not use it to fix race conditions.
- `Thread.setPriority()` is not a contract for latency, ordering, or CPU share across operating systems.
- CPU-bound workloads generally need a number of actively running workers roughly matching measurable CPU capacity; adding dozens of CPU-running threads on a few cores usually does not help. I/O-bound workloads may require higher concurrency because many tasks wait, but you must account for queue limits, memory, connection pools, and backpressure.
- Many tiny tasks also incur task creation, enqueue/dequeue, queue synchronization, and wake-up overhead; moderate batching can sometimes be more efficient than task-per-item.
- Work stealing (e.g., `ForkJoinPool`) helps balance splittable tasks; it does not solve contention on a single lock or an oversubscribed CPU.

### Reality of a Thread Pool

Suppose there are 4 available CPUs, a pool of 32 workers, and 1,000 CPU-bound tasks. The 32 workers cannot all execute simultaneously on 4 CPUs. Besides waiting for a CPU turn, tasks also wait in the queue. If mixed in the same pool with long-blocking work, short tasks can be delayed because workers are occupied. Measure queue wait, queue length, active workers, CPU saturation, and p95/p99; only tune the pool after identifying the bottleneck.

**Java 21+ (note):** virtual threads can unmount from their carrier thread during many supported blocking operations, reducing the need to tie up an OS thread for each waiting task. However, they are still scheduled across a finite number of carrier threads, do **not** create extra CPU cores, do not eliminate contention on shared state, and do not automatically make CPU-bound code faster. The example below still runs on Java 17+ and uses platform threads.

## 5. How the Three Sources of Overhead Relate

A common execution chain:

`Many tasks arrive → many workers want the same lock → workers wait/park → lock holder releases lock → OS wakes/schedules next worker → workers contend for lock again → slow outcome`.

Here:
- **Contention** is why tasks cannot make independent progress.
- **Scheduling** decides when a thread gets to resume.
- **Context switching** can be part of the cost when switching the CPU between threads.

An opposite case: 64 workers running independent computations on 4 cores without any shared locks. Here, contention on application locks may be very low, yet oversubscription and scheduling overhead remain high. Identify the actual phenomenon rather than calling every concurrency problem a "slow lock".

### Symptoms Do Not Prove Causes by Themselves

| Observation | What It Could Be | What to Check Next |
|---|---|---|
| High CPU, throughput does not increase when adding threads | CPU saturation, CAS retries, spinning, cache contention | CPU profiling, actual cores used, atomic hotspots |
| Many threads `BLOCKED` on the same monitor | Lock contention / long critical section | Lock owner, stack traces, JFR monitor events |
| Many threads `WAITING` | Idle workers, waiting on queue/condition, or park-based lock waiting | Stack/queue metrics, wait type, duration |
| Low CPU but high latency | Waiting on I/O, queue, lock, or exhausted connection pool | Trace queue/I/O/lock time, JFR |
| Context-switch rate spikes | Oversubscription, frequent wake-ups, repeated blocking | Voluntary/involuntary switches, CPU, throughput |
| p99 increases as throughput rises | Queueing/tail contention, GC, or other bottlenecks | Queue wait, duration distribution, GC/JFR |

## 6. Java 17+ Experiment: A Shared Update Hotspot

This hands-on example compares an `AtomicLong` (a single shared atomic update point) and a `LongAdder` (distributes updates under contention). Both approaches must count accurately after workers finish; **timings are not fixed** and `LongAdder` is not guaranteed to win every single run.

Create **`OverheadLab.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class OverheadLab {
    private static final int THREADS = 4;
    private static final int INCREMENTS_PER_THREAD = 100_000;

    @FunctionalInterface
    interface Work { void run(); }

    private static long timeConcurrent(Work work) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(THREADS);
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[THREADS];

        for (int i = 0; i < THREADS; i++) {
            workers[i] = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    work.run();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "worker-" + i);
            workers[i].start();
        }

        ready.await();
        long begin = System.nanoTime();
        start.countDown();
        for (Thread worker : workers) worker.join();
        return System.nanoTime() - begin;
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicLong atomic = new AtomicLong();
        long atomicNs = timeConcurrent(() -> {
            for (int i = 0; i < INCREMENTS_PER_THREAD; i++) atomic.incrementAndGet();
        });

        LongAdder adder = new LongAdder();
        long adderNs = timeConcurrent(() -> {
            for (int i = 0; i < INCREMENTS_PER_THREAD; i++) adder.increment();
        });

        System.out.println("AtomicLong count=" + atomic.get());
        System.out.println("LongAdder count=" + adder.sum());
        System.out.printf("AtomicLong elapsed=%.2f ms%n", atomicNs / 1_000_000.0);
        System.out.printf("LongAdder elapsed=%.2f ms%n", adderNs / 1_000_000.0);
    }
}
```

Compile and run:

```bash
javac --release 17 OverheadLab.java
java OverheadLab
```

The two count lines are **deterministic** (assuming normal program completion):

```text
AtomicLong count=400000
LongAdder count=400000
```

The next two lines take the form `AtomicLong elapsed=... ms` and `LongAdder elapsed=... ms`, with numbers varying by machine and run. `CountDownLatch` lets threads start work at nearly the same time; `join()` ensures the final count is read after all workers finish. `System.nanoTime()` measures total elapsed time, not context-switch cost in isolation.

Understand the limitations of this experiment:

- `AtomicLong` provides direct atomic read semantics; `LongAdder.sum()` does **not** provide an atomic snapshot while concurrent updates are occurring. Using `sum()` after `join()` to read the final total is appropriate.
- `LongAdder` has extra overhead and memory footprint; under low contention, `AtomicLong` can be faster. Neither directly represents `synchronized` monitor cost.
- Microbenchmarks are easily skewed by warm-up/JIT, GC, scheduling priority, core count, thermal/CPU frequency scaling, measurement order, and system noise. Running `java OverheadLab` once is **not enough** to draw performance conclusions.
- For more reliable comparisons: use **JMH** with warm-up, multiple iterations/forks, and a controlled load environment; report the distribution of results. Measuring throughput/latency under realistic load is what guides production optimization.

**Follow-up experiment:** keep the same code, run with `THREADS = 1, 2, 4, 8, 16` and a fixed number of increments **per thread**; in that setup, total work scales with the thread count, so you must **not** use total program runtime to compare scalability for a fixed workload. To compare the same amount of work, divide a fixed total increment count by the number of workers, handle any remainder, warm up, and measure independently.

## 7. Observing Overhead in the JVM and Operating System

### Thread Dumps: Seeing What Threads Are Waiting On

When the application runs long enough, use the actual Java PID:

```bash
jcmd <PID> Thread.print
```

Look for groups of stacks with many threads waiting on the same monitor/lock, cross-reference which thread holds the lock, and take several dumps spaced apart to distinguish sustained waiting from a coincidental snapshot. `BLOCKED`/`WAITING` only show state at the instant of the dump; do not infer total wait time from a single snapshot.

### ThreadMXBean: Java-Level Counters

`java.lang.management.ManagementFactory.getThreadMXBean()` lets you read thread metrics. Before enabling contention monitoring, check `isThreadContentionMonitoringSupported()`; if supported, `setThreadContentionMonitoringEnabled(true)` records `ThreadInfo.getBlockedTime()` and `getWaitedTime()` (with measurement overhead). `getBlockedCount()` counts times a thread waited **to enter a monitor**; it is not total context switches or total failed CAS attempts. Wait times may be `-1` when monitoring is disabled or unsupported. Do not use thread management info to control the program's own synchronization.

```java
// Illustrative snippet placed inside a method; not a standalone program.
var mx = java.lang.management.ManagementFactory.getThreadMXBean();
if (mx.isThreadContentionMonitoringSupported()
        && !mx.isThreadContentionMonitoringEnabled()) {
    mx.setThreadContentionMonitoringEnabled(true);
}
var info = mx.getThreadInfo(Thread.currentThread().getId());
if (info != null) {
    System.out.println("monitor blocked count = " + info.getBlockedCount());
    System.out.println("monitor blocked time ms = " + info.getBlockedTime());
}
```

### Java Flight Recorder (JFR): Finding Wait Points with Context

Run a long enough workload and record JFR (JDK 17+):

```bash
java -XX:StartFlightRecording=filename=overhead.jfr,settings=profile,dumponexit=true OverheadLab
jfr summary overhead.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark overhead.jfr
```

`jdk.JavaMonitorEnter` indicates monitor contention, `jdk.JavaMonitorWait` indicates monitor waiting, and `jdk.ThreadPark` indicates thread parking; inspect duration, stack traces, and threads. **The absence of events does not prove the absence of waiting:** JFR profile configurations may have duration thresholds, disable certain events, and short workloads may not emit useful events. For production systems, plan sufficiently long recording sessions and inspect them with JDK Mission Control when timeline analysis is needed.

### OS-Level: Measuring Real Context Switches

On Linux, you can use a thread monitoring tool such as:

```bash
pidstat -w -t -p <PID> 1
```

If `sysstat` is installed, track per-thread voluntary/involuntary context switches; correlate with CPU utilization, runnable queue, and throughput. On other operating systems, use the corresponding profiling/counter tools. Looking only at system-wide total context switches is insufficient to blame the Java process. Thread CPU time, Java blocked time, OS switch count, and wall-clock latency **are different metrics** and do not substitute for one another.

## 8. Root-Cause Optimization Methodology

**Step 1 — Establish a comparable baseline.** Fix inputs, load, JVM configuration, and available cores; record throughput, p50/p95/p99 latency, CPU, GC, active thread count, queue length/wait, and correctness outcomes. Measure multiple times before concluding.

**Step 2 — Classify the bottleneck.**
- **CPU saturated, many runnable threads, little waiting:** inspect CPU profile, oversubscription, overly small tasks, CAS retries, or false sharing.
- **Many threads waiting on monitors/locks:** use JFR/thread dumps to find lock owners, critical sections, and access frequency.
- **Many threads waiting on queues/I/O:** check slow external calls, connection pools, downstream capacity, and backpressure.
- **Threads constantly created/destroyed:** inspect execution model, worker reuse, and task granularity.

**Step 3 — Apply small changes and re-measure.**
- Shorten critical sections; move computation/I/O outside locks when safe; reduce lock granularity if invariants allow.
- Partition/shard state by key; use thread-local aggregation or `LongAdder` for frequently updated statistics that do not need a consistent snapshot during updates.
- Bound runnable workers for CPU-bound workloads; separate pools by blocking/CPU nature when justified; use **bounded** queues and explicit backpressure mechanisms.
- Avoid waking up repeatedly to poll; use blocking queues/conditions with proper predicates instead of scattered `sleep` and `yield` calls.
- Batch small operations sensibly; avoid creating threads and futures for overly tiny operations.
- If wait-time guarantees are needed, evaluate fairness/starvation with measurements. Fairness often trades off throughput; test tail latency as well.

**Step 4 — Prove improvement while preserving correctness.** Re-measure under representative load while verifying against races, lost updates, deadlocks, starvation, observable ordering, and visibility requirements. A "faster" approach that drops required synchronization is a bug, not an optimization.

## 9. Common Misconceptions

1. **"More threads are always faster."** False if the CPU is saturated, queues/locks are congested, or overhead dominates.
2. **"RUNNABLE means the thread is using the CPU."** False: it may be ready to run but not yet scheduled by the OS.
3. **"BLOCKED covers all kinds of lock waiting."** False: Java's `BLOCKED` describes waiting for a monitor; parking from other synchronizers produces different states.
4. **"Lock-free means contention-free."** False: CAS retries and cache-coherence traffic can still consume substantial CPU.
5. **"sleep/yield fixes races or guarantees fairness."** False: proper synchronization, conditions, and lifecycle design are required.
6. **"Low CPU means there is no concurrency problem."** False: threads can be stuck on I/O, queues, or locks while using little CPU.
7. **"Seeing many WAITING threads means a deadlock."** False: idle executor workers are also commonly in `WAITING`; analyze the wait graph and actual progress.
8. **"Measuring wall-clock time with nanoTime tells you context-switch cost."** False: wall-clock time includes execution, waiting, preemption, and noise.
9. **"Switching synchronized to ReentrantLock/AtomicLong is automatically faster."** False: correctness, fairness, contention patterns, and workload determine the outcome.
10. **"Virtual threads eliminate scheduling overhead."** False: scheduling, carrier threads, and shared resources still exist.

## 10. Self-Check

**Scenario A:** 8 CPU cores, 8 threads processing independent calculations reach 100% CPU; increasing to 64 threads worsens p99 without increasing throughput. **Explanation:** CPU-bound oversubscription increases turn-waiting time and can increase context switching/cache disruption. Try bounding active workers around available CPU capacity and re-measure.

**Scenario B:** CPU is not high, 40 threads are `BLOCKED` on one monitor, and the thread holding the monitor is doing I/O. **Explanation:** lock contention caused by holding a critical section for too long. Move I/O outside the lock if invariants can be preserved, or redesign data sharing and verify with JFR/traces.

**Scenario C:** An `AtomicLong` counter is incremented by many workers; CPU is high even though no threads are `BLOCKED`. **Explanation:** a hotspot on a single atomic memory location can make CAS/cache coherence expensive. Consider `LongAdder` if semantics allow; verify correctness and measure under load.

**Scenario D:** 200 threads are all `WAITING` in `BlockingQueue.take()` when the queue is empty. **Explanation:** these are usually idle workers waiting for work; the `WAITING` state alone does not prove a bug. Look at throughput, incoming workload, and queue depth.

## References

- [Java SE 17: `Thread.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html) — definitions of Java thread states.
- [Java SE 17: `ThreadInfo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html) — blocked/waited time, owner, and monitors.
- [Java SE 17: `ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html) — checking/enabling contention monitoring.
- [Java SE 17: `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html) — statistics behavior under contention.
- [JDK 17: `jfr` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html) — inspecting/summarizing recordings.
- [OpenJDK: Java Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/) — configuring and analyzing recordings.

**Key takeaway:** identify which work actually uses CPU and which work is waiting on resources or queues, then measure context switching and contention under realistic load; adding threads only helps when there are sufficient resources and independence for them to make progress.
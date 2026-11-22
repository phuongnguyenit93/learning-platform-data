# Identifying Root Causes Before Tuning Pools and Locks

## 1. Why Diagnose Before Changing Configuration?

When a Java application has many slow threads, request timeouts, or long-waiting tasks, the commonly suggested changes are **increasing the number of threads in the pool**, **increasing the queue size**, **changing the lock type**, or **replacing `synchronized` with concurrent data structures**. Those changes only help if they target the actual bottleneck. If the real problem lies in the database, network I/O, saturated CPU, deadlock, or unbounded workload, tuning pools or locks can reduce throughput, increase latency, and make bugs harder to trace.

The principle of this guide is:

> **Symptom → evidence → hypothesis → verification → small change → re-measure.**

For example: a growing executor queue does not prove that the pool is "too small"; tasks may be blocked downstream. A thread in the `WAITING` state does not by itself prove a deadlock; it may be legitimately waiting for work from a queue. High CPU does not prove a shortage of threads either; it can be a sign that **too many threads are already contending for CPU**.

The scope is **Java SE concurrency** (platform threads, `ExecutorService`, `ThreadPoolExecutor`, `synchronized`, `ReentrantLock`, `java.util.concurrent`, JVM diagnostics). These principles apply when using frameworks as well, but the diagnostics and examples here do not depend on Spring.

### Commonly Misinterpreted Symptoms

| Symptom | Hypothesis to Check | Key Evidence |
| --- | --- | --- |
| Tasks stay in the queue for a long time | Pool lacks processing capacity, slow downstream, bursts exceeding capacity | Queue depth + queue wait time + task execution time + active workers |
| Throughput does not increase despite adding threads | CPU saturation, lock contention, memory pressure, I/O limit | CPU utilization, thread stacks, JFR, throughput by thread count |
| Many `BLOCKED` threads | Intrinsic monitor (`synchronized`) contention | Stack traces, monitor owner, JFR monitor blocked events |
| Many `WAITING` threads | Waiting on queue, latch, condition, park, future, or lock | Stack and waiting object, wait duration, task state |
| Requests hang indefinitely | Deadlock, starvation, unresponsive external dependency | Multiple thread dumps over time, deadlock detection, timeout metrics |
| Pool throws `RejectedExecutionException` | Pool + queue out of capacity or executor shut down | Rejection count, queue depth, active workers, lifecycle |
| p99 latency increases while average barely changes | Pauses, lock convoy, GC, scheduler, bursty queue | Latency distribution, JFR, GC, queue wait |
| Low CPU, high latency | Waiting on I/O, locks, pool starvation, slow data source | Thread dumps and per-stage timing; not just overall CPU |
| Increasing queue reduces errors but slows everything down | Queue masks overload, increasing wait time | Queue wait, p95/p99, age of oldest task, memory |

**First, define the goal:** improving throughput (tasks/second), end-to-end latency, reducing tail latency, bounding resources, or increasing burst tolerance. One optimization may improve one metric while degrading another.

## 2. Modeling the Path of a Task

A task submitted to an executor typically follows this journey:

```text
Producer / caller
       |
       | submit/execute
       v
[Executor queue] ---- queue wait ----> [Worker thread]
                                            |
                                            +--> CPU computation
                                            +--> lock/condition
                                            +--> file/network/database I/O
                                            +--> wait for another future/task
                                            |
                                            v
                                       task complete
                                            |
                                            v
                                        result/ack
```

End-to-end time can be broken down into:

```text
end-to-end latency ≈ queue wait + execution duration + response/coordination overhead
execution duration = useful work + waiting/blocking + scheduling overhead
```

This is an *observational* breakdown, not an exact formula for every pipeline: if there are multiple queues, retries, or parallel processing, you must measure each stage and account for potentially overlapping segments.

Do not lump **queue time** and **execution time** into a single number and conclude that `ThreadPoolExecutor` lacks workers. If `queue wait` is high while workers are blocked on sockets or locks, the root cause may lie outside the pool.

To investigate, record at minimum: submission timestamp, task start timestamp, completion timestamp, completion/error/cancellation status, and workload type. When using `Future`, distinguish the caller's wait time in `get()` from the task's execution time; a long wait in `get()` does not prove the task ran for a long time.

## 3. Collecting a Baseline Before Tuning

### 3.1 Metrics to Measure Simultaneously

| Category | Suggested Metrics | Purpose |
| --- | --- | --- |
| Demand | submissions/s, burst size, concurrent callers | Know whether the submission source exceeds capacity |
| Completion | completed tasks/s, fail/cancel/reject count | See how much work actually finishes |
| Queue | depth, wait time, age of oldest queued item | Identify backlog and queue-induced latency |
| Pool | current/core/max threads, active threads, pool utilization | Know how many workers the executor has |
| Task | execution time, blocking time, timeout, exception | Distinguish slow tasks from slow queues |
| CPU | process CPU, available cores, run queue, context switches | Identify CPU saturation/oversubscription |
| Memory | heap occupancy, allocation rate, GC pauses | Identify GC/memory pressure |
| Lock | blocked time, lock owner, contended monitor/synchronizer | Identify contention and lock ordering |
| External | dependency latency, timeout, concurrency, and error rate | Avoid blaming the pool when downstream is the bottleneck |

Metrics must share the same **time window** and the same workload. A single point-in-time queue snapshot can miss short bursts; increasing throughput accompanied by worsening p99 is an important warning signal.

### 3.2 ThreadPoolExecutor Metrics Are Only Snapshots/Approximations

`ThreadPoolExecutor` provides diagnostic APIs:

```java
int poolSize = pool.getPoolSize();
int active = pool.getActiveCount();
int queued = pool.getQueue().size();
long submittedApprox = pool.getTaskCount();
long completedApprox = pool.getCompletedTaskCount();
```

This is an **illustrative method snippet** using a `pool` variable of type `ThreadPoolExecutor`, not a standalone program. `getActiveCount()`, `getTaskCount()`, and `getCompletedTaskCount()` return **approximate** values because the pool and tasks may change while being read. `getQueue().size()` is only a snapshot of the queue at the moment of the call; consecutive reads must not be treated as a consistent transaction.

Do not treat `getTaskCount() - getCompletedTaskCount()` as an exact pending count at all times, and do not rely on `getQueue().size()` to directly drive race-sensitive logic. These numbers are useful for plotting trends, setting thresholds, and supporting diagnostics.

### 3.3 Instrumenting Task Tracing Properly

If you need to separate queue wait from execution time:

```java
long enqueuedAt = System.nanoTime();
executor.execute(() -> {
    long startedAt = System.nanoTime();
    try {
        runBusinessTask();
    } finally {
        long endedAt = System.nanoTime();
        recordQueueWait(startedAt - enqueuedAt);
        recordExecution(endedAt - startedAt);
    }
});
```

This is **illustrative code**, assuming `executor`, `runBusinessTask`, `recordQueueWait`, and `recordExecution` are already provided. `System.nanoTime()` is suitable for measuring elapsed intervals within the same JVM; its absolute value must not be used as wall-clock time. For cancellations or rejections, record those branches separately, because a rejected task will never enter the lambda.

Adding telemetry also has overhead; avoid `println` on every hot operation and use appropriate sampling/aggregation.

## 4. Standalone Java 17+ Experiment: Distinguishing a Full Queue from Busy Workers

The following snippet intentionally creates one worker waiting on a latch, two queued tasks, and one rejected task. It demonstrates the signals to observe **before increasing pool size**. This is a controlled experiment, not a performance benchmark.

Create `PoolDiagnosisDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolDiagnosisDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            pool.execute(() -> {
                running.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            running.await();

            pool.execute(() -> {});
            pool.execute(() -> {});

            System.out.println("queued=" + pool.getQueue().size());
            try {
                pool.execute(() -> {});
                System.out.println("rejected=false");
            } catch (RejectedExecutionException e) {
                System.out.println("rejected=true");
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }
        System.out.println("completed=" + pool.getCompletedTaskCount());
    }
}
```

Compile and run:

```shell
javac --release 17 PoolDiagnosisDemo.java
java PoolDiagnosisDemo
```

Normal output of the experiment verified with the JDK:

```text
queued=2
rejected=true
completed=3
```

**Explanation:**

1. The pool has at most **1 worker**, a queue capacity of **2**, and `AbortPolicy`.
2. The first task counts down `running` so `main` knows the worker has started; the worker then waits on `release`. `running.await()` eliminates the race between submission and queue inspection.
3. The next two empty tasks are placed into the queue, yielding `queued=2`. Because the sole worker has not exited the latch, the queue remains full at inspection time.
4. The fourth task cannot be executed immediately and the queue has no remaining space, so `execute()` throws `RejectedExecutionException`: printing `rejected=true`.
5. In `finally`, `main` releases the latch, requests shutdown, and awaits termination. The worker finishes the first task and the two queued tasks, so `completed=3`; the rejected task is **not** counted as completed.
6. The experiment does not claim that "increasing the pool is right": it **intentionally blocks the worker**. With real workloads, you must know whether workers are blocked on I/O, locks, business conditions, or CPU-heavy work.

The program uses Java SE primitives with no external frameworks or dependencies. `getCompletedTaskCount()` is approximate in concurrent environments, but in this example after `awaitTermination` succeeds, all three tasks have finished, so the result is 3. If the machine stalls or times out, the program throws an error rather than silently reporting completion.

### Deriving a Root-Cause Check

Suppose a real system reports "the queue is always full." Before increasing `maximumPoolSize`, ask:

- Are workers **`RUNNABLE` using CPU**, waiting on I/O, `BLOCKED` on a monitor, or waiting on `Future.get()` of another task?
- Are task duration and queue wait increasing together, or is only queue wait increasing?
- Does the submission rate exceed the completion rate over a sustained period?
- What does the rejection policy do: throw an exception, run on the caller, drop, or use a custom mechanism?
- Is the queue bounded or unbounded? With common unbounded queues, a larger `maximumPoolSize` may **never be used to create additional workers** once core threads are active and tasks are queued.

Answer these questions first, then choose pool sizing, backpressure, producer throttling, or fixing the blocking cause.

## 5. Understanding ThreadPoolExecutor Behavior Before "Increasing Max"

`ThreadPoolExecutor` takes key parameters: `corePoolSize`, `maximumPoolSize`, `keepAliveTime`, `BlockingQueue<Runnable>`, and `RejectedExecutionHandler`. The typical task acceptance flow:

1. If the number of workers is less than `corePoolSize`, the executor prefers creating a new worker to run the task.
2. Once core workers are in place, it attempts to put the task into the queue.
3. If the queue cannot accept it and the worker count is below `maximumPoolSize`, it attempts to create an additional worker.
4. If the task cannot be accepted or the executor is no longer accepting work, it applies the rejection policy.

The implementation has synchronization, race, and lifecycle details; the sequence above is a behavioral model for understanding configuration, not a guarantee that every snapshot matches step by step.

| Queue | Consequence | What to Watch Out For |
| --- | --- | --- |
| `LinkedBlockingQueue` (virtually unbounded) | Tasks accumulate easily; `maximumPoolSize` often has no effect while tasks keep entering the queue | Risk of growing memory usage and queue latency during prolonged overload |
| Bounded `ArrayBlockingQueue` | Prevents unbounded backlog growth; can trigger worker expansion up to max or rejection | Capacity must be chosen based on latency/memory and bursts |
| `SynchronousQueue` | Does not store tasks in the queue; hands off directly to a worker | Easily spawns workers on demand up to max; requires a reasonable upper bound |
| Custom queue | Depends on specific semantics | Verify blocking, capacity, fairness, and contract |

**`Executors.newFixedThreadPool(n)`** uses an unbounded queue by default; if producers outpace consumers for an extended period, the number of queued tasks can grow large. **`Executors.newCachedThreadPool()`** can scale workers on demand and risks creating too many platform threads if workload limits are missing. Choosing a convenience factory does not absolve you from defining resource bounds.

### Choosing Pool Size Based on Workload Nature

- **CPU-bound:** when workers spend most of their time computing, having more workers than logical CPUs usually does not increase throughput and can increase context switching and contention. This is a heuristic to start measuring, not an absolute formula.
- **Blocking I/O:** workers spend significant time waiting on I/O, so the number of workers can exceed the CPU count. However, downstream connection pools, OS resources, memory, and remote service limits may become the bottleneck first.
- **Mixed workload:** separate task types when necessary, or at least measure CPU/wait ratios and queues per group. One slow task group can cause head-of-line blocking for fast tasks.
- **Burst workload:** define the burst size, maximum acceptable queue wait, and admission/rejection mechanism. Making the queue very large may reduce rejections but cause cascading timeouts later.

Do not pick `poolSize = 2 * CPU` or `poolSize = 100` from a memorized formula alone. Measure throughput and p95/p99 latency across multiple concurrency levels under controlled conditions.

## 6. Distinguishing Thread States in Thread Dumps

A thread dump is a **point-in-time snapshot**. For Java platform threads, the common states are:

| State | Meaning per `Thread.State` | Do Not Infer |
| --- | --- | --- |
| `NEW` | Not yet started | Pool is broken |
| `RUNNABLE` | Executing in the JVM or ready to run; may be in native code | Definitely using 100% CPU |
| `BLOCKED` | Waiting to enter a `synchronized` monitor | Definitely a deadlock |
| `WAITING` | Waiting indefinitely due to `Object.wait`, `Thread.join`, `LockSupport.park`, etc. | Definitely broken |
| `TIMED_WAITING` | Waiting with a timeout such as `sleep`, timed `wait`, timed `join`, timed `park` | Task is definitely hung |
| `TERMINATED` | Thread has exited | Automatically indicates the outcome of all tasks |

`ReentrantLock` uses `AbstractQueuedSynchronizer` and `park`; a thread waiting for a lock can be in `WAITING`/`TIMED_WAITING`, unlike threads waiting on an intrinsic monitor which are typically in `BLOCKED`. Therefore, counting only `BLOCKED` threads will **miss other forms of lock contention**.

When reading a stack trace, locate the **first application frame** near the blocking call and check:

- Which lock is the thread waiting on, and which thread is the lock owner?
- If waiting on `Future.get()`, which pool is the awaited task running on? Is it waiting on the same pool that has run out of workers?
- If the stack is in `SocketInputStream`/network I/O, what are the downstream wait times and timeouts?
- If it is in `BlockingQueue.take()`, that may simply be a **normal idle worker**.
- Are multiple threads stuck at the same call site across several consecutive dumps?

### When Are Multiple Thread Dumps Needed?

A single dump shows "where a thread is" but does not prove how long it has been there. Take **several snapshots spaced according to the expected latency**, compare stacks per thread, and correlate them with metrics at that time. Do not take dumps continuously at excessive frequency because observation itself has overhead.

**Example interpretation:**

```text
worker-1 WAITING at LinkedBlockingQueue.take()
worker-2 WAITING at LinkedBlockingQueue.take()
```

This may simply be an idle pool with no tasks. Conversely:

```text
worker-1 WAITING at FutureTask.get()
worker-2 WAITING at FutureTask.get()
```

If both workers are waiting on new tasks submitted to **the very same two-worker pool**, this is a sign of **thread starvation deadlock**: no worker is free to run the child tasks. A stack trace alone is not enough; verify the parent–child task relationship and the queue.

## 7. Diagnosing Lock Contention and Deadlock

### 7.1 Lock Contention

**Contention** occurs when multiple threads compete for the same lock and at least one thread must wait. It is not necessarily a bug; locks protecting invariants are necessary. The issue arises when lock hold time, lock acquisition frequency, or the number of contending threads prevents throughput/latency from meeting requirements.

Signs:

- Multiple threads waiting on the same monitor/`ReentrantLock`.
- JFR shows slow monitor enter events or significant wait times.
- Overall CPU is low yet throughput is low because most threads are blocked.
- p99 rises during peak hours when contention crosses a threshold.

**Critical section analysis:** what actually needs to be inside the lock? Is there blocking I/O, `Thread.sleep`, uncontrolled callbacks, database calls, synchronous logging, or nested locks inside? Holding a lock while calling code outside your control increases lock hold time and deadlock risk.

Prefer reducing work inside the critical section if correctness allows, or reducing shared mutable state. Only switch to `ReadWriteLock`, `StampedLock`, atomics, or concurrent structures if the workload truly fits and semantics have been verified. Those abstractions are not automatically faster than `synchronized`.

### 7.2 True Deadlock

A deadlock is a group of threads/tasks **waiting on each other in a cycle** and unable to make progress under current conditions. Example with two monitors:

```text
Thread A: holds lockA -> waits for lockB
Thread B: holds lockB -> waits for lockA

A ----waiting----> B
^                   |
|------waiting------|
```

Fundamental remedies:

- Enforce a **consistent lock acquisition order** across all code paths.
- Reduce nested locks and lock hold durations.
- With `ReentrantLock`, consider `tryLock(timeout)` and design **bounded**, testable fail/retry paths; timeouts do not automatically fix every kind of deadlock.
- Avoid holding a lock while waiting on `Future.get()` or a callback that might need that lock.
- Fix cyclic dependencies between tasks/executors rather than just adding workers.

**Distinguishing from starvation:** a group of tasks may fail to run because workers are waiting on other tasks in the same pool without a *monitor ownership cycle*. `ThreadMXBean.findDeadlockedThreads()` is not guaranteed to detect every kind of starvation or wait-for-resource cycle.

### 7.3 ThreadMXBean in Java SE

`java.lang.management.ManagementFactory.getThreadMXBean()` provides an API to inspect platform threads. Two important methods:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
long[] deadlocked = mx.findDeadlockedThreads();
ThreadInfo[] infos = mx.dumpAllThreads(true, true);
```

This is an **illustrative snippet**; it requires importing `java.lang.management.ManagementFactory`, `ThreadMXBean`, and `ThreadInfo`, as well as checking feature support. `findDeadlockedThreads()` may return `null` if no deadlock cycle involving supported monitors/ownable synchronizers is detected. If the implementation does not support a specific feature, the API may throw `UnsupportedOperationException`; check `isSynchronizerUsageSupported()` and `isObjectMonitorUsageSupported()` before requesting the corresponding information.

You can use `isThreadContentionMonitoringSupported()` and `setThreadContentionMonitoringEnabled(true)` to observe contention time when the JVM supports it. Contention monitoring is typically **disabled by default** and has overhead; enable it as needed rather than leaving it on permanently just to collect one number.

**Important limitation:** traditional `ThreadMXBean` focuses on **platform threads**; it does not support tracking and managing virtual threads through these same enumeration/detection methods. On Java 21+, if the application uses virtual threads, use JFR/dump tools appropriate for the environment and do not infer that "no threads in MXBean" means no work is running.

## 8. JVM Diagnostic Toolkit

### 8.1 jcmd and Thread Dumps

On a supported JDK, run on the same machine with appropriate permissions for the Java process:

```shell
jcmd -l
jcmd <pid> help
jcmd <pid> Thread.print -l
```

Replace `<pid>` with the actual PID without typing the angle brackets. `jcmd -l` lists visible Java processes; `Thread.print -l` prints stacks and `java.util.concurrent` locks when supported. Exact command names or options may vary by JDK/vendor; use `jcmd <pid> help` to confirm.

**Key points when reading dumps:** distinguish `RUNNABLE` threads from actual CPU usage, `WAITING` on an idle queue from `WAITING` on `Future.get()`, and `BLOCKED` on a monitor from `WAITING` on an ownable synchronizer. Cross-reference multiple dumps and metrics from the same time window.

### 8.2 JFR: Recording Progression Instead of a Single Snapshot

Java Flight Recorder (JFR) supports observing runtime events with relatively low designed overhead. Example of capturing a 60-second recording from a running Java process:

```shell
jcmd <pid> JFR.start name=pool_diagnosis settings=profile duration=60s filename=pool-diagnosis.jfr
```

`settings=profile` provides a deeper event profile than `default`, which may increase overhead; configuration and permissions must suit the environment. You can open the recording with JDK Mission Control or inspect it using the matching JDK `jfr` tool. Analyze results over the **time range** coinciding with queue/latency spikes. A recording taken while the system is idle will not explain an incident under high load.

Useful signals: execution samples, CPU load, allocations, garbage collection, Java monitor blocked/park events, and thread active time. Not all events are enabled in every configuration; check the JFR template before drawing conclusions from the absence of an event.

### 8.3 GC and CPU Profiling

On HotSpot, you can enable GC logging when needed for diagnostics, for example:

```shell
java -Xlog:gc -jar app.jar
```

This is an illustrative command requiring a real `app.jar` file; it launches a new process with logging rather than attaching logging to an existing process. Match GC pauses against latency spikes by timestamp; do not conclude "GC is the culprit" merely from seeing GC activity.

CPU profilers help distinguish busy computation from wait time, though profilers have overhead. For lock contention, capture stacks, lock owners, and JFR rather than looking only at a CPU flame graph.

### 8.4 Observe Dependencies Outside the JVM as Well

If workers wait on network, file I/O, or a database, JVM metrics are only **half the story**. Cross-reference connection pool saturation, downstream throughput, retry storms, timeouts, rate limits, and queues on the dependency side. If a downstream service limits connections to 20, raising the Java pool to 200 workers can simply create 180 more waiting threads and worsen tail latency.

## 9. Reasoning Workflow from Symptom to Fix

A practical workflow for real investigations:

### Step 1 — Quantify the Incident

Record the exact time, workload, JDK version, worker count, queue capacity, rejection policy, CPU, p50/p95/p99 latency, and error rate. For example: "p99 rose from baseline to 2 seconds when submissions tripled and queue wait increased proportionally" is far more useful than "Java is slow."

### Step 2 — Separate Queue Wait from Execution Time

If queue wait rises while task execution stays flat, the issue may be **insufficient processing capacity relative to submission rate**. If execution time rises while active workers are all busy, inspect what workers are doing. If both rise, the backlog may be a *consequence* of longer task duration.

### Step 3 — Identify the Workload Type

Distinguish CPU-bound, blocking I/O, lock-bound, memory/GC-bound, mixed, or dependency-bound workloads. Use thread dumps and JFR to find hot paths and waiting points. Do not automatically attribute every `WAITING` thread to a deadlock.

### Step 4 — Verify a Falsifiable Hypothesis

For example:

- Hypothesis **A**: too few workers for I/O tasks. Verification: workers spend most of their time waiting on I/O, CPU has headroom, downstream has capacity; does increasing workers improve completion throughput and p99?
- Hypothesis **B**: lock held too long. Verification: many threads wait on the same monitor, owner holds the lock across I/O; does shortening the critical section reduce blocked time?
- Hypothesis **C**: CPU is saturated. Verification: CPU is near physical/logical core limits; does adding workers increase context switches without increasing throughput?
- Hypothesis **D**: tasks are waiting on child tasks in the same pool. Verification: `Future.get()` stacks, child tasks queued, no workers available; change dependency/scheduling rather than just adding threads?

### Step 5 — Make a Bounded Change and Re-measure

Prioritize fixing the verified root cause: limit fan-out, remove blocking I/O from locks, replace mutual waiting structures, add timeouts, throttle producers, cache/reduce work, and choose appropriate pool size and queue capacity. Change **one significant variable at a time** in a representative load environment.

Compare before/after using the same data types and measurement methodology; verify correctness, throughput, p95/p99, CPU, memory/GC, backlog, rejections, and recovery behavior when load subsides.

### Step 6 — Prepare Rollback and Overload Policies

A pool that is stable under normal load can still collapse during bursts. Design explicitly: bounded queue, overload signals, backpressure/rate limiting, rejection behavior, cancellation, timeouts, and resource cleanup. Do not switch to `CallerRunsPolicy` by default without checking its impact: this policy makes **the caller run the task when the pool is saturated** (while the executor is not shut down), slowing the caller and potentially altering latency, control flow, or causing unexpected blocking.

## 10. Typical Scenario: Pool Starvation from Tasks Waiting on Tasks

Suppose a fixed pool has 2 workers. Two parent tasks occupy both workers; each parent submits a child task to the same pool and synchronously waits on `Future.get()`. Both child tasks sit in the queue, but **no worker is free**.

```text
fixed pool: 2 workers

worker-1: parent-A --> submit child-A --> Future.get() -- waits
worker-2: parent-B --> submit child-B --> Future.get() -- waits

queue: [child-A, child-B]      no free worker
```

**Symptoms:** low CPU, tasks still in the queue, all workers `WAITING`, requests hanging. This is not necessarily a monitor-ordering deadlock; `findDeadlockedThreads()` may report nothing.

**Fundamental fix:** do not synchronously wait on child tasks on the same bounded executor; redesign dependencies, switch to non-blocking asynchronous composition, separate pools appropriately, or have the caller execute child work if semantics allow. Increasing `maximumPoolSize` may have no effect with an unbounded queue; increasing a fixed worker count only postpones recurrence if fan-out also grows.

To verify, measure the number of blocking parent tasks, queued child tasks, and stacks at `Future.get()`. After fixing, verify throughput, correctness, and termination under high load.

## 11. Typical Scenario: Lock Contention vs. Adding Threads

Suppose 16 workers all call a method that updates a shared map under `synchronized`. Each lock acquisition is held for 20 ms because the method also logs or performs I/O. Even if you increase to 64 workers, the critical section still essentially allows only one thread at a time.

**Signs:** many threads `BLOCKED` on the same monitor, owner holding the lock in a slow method; throughput is capped by the lock and blocked time grows as worker count increases.

**Evidence-based solution:**

1. Move I/O, logging, and independent computation outside the critical section while preserving correctness.
2. Replace coarse-grained locks with concurrent structures or partitioned state when access patterns fit.
3. Reduce fan-out to avoid creating work that pointlessly contends on the same lock.
4. Re-measure contention, throughput, and correctness at multiple thread counts.

Do not replace `synchronized` with `ReentrantLock` just because the class name sounds more optimized. Both can still guard long critical sections, and measuring contention tells you whether the switch actually helps.

## 12. Decision Matrix Before Tuning

| Verified Evidence | Usually Reasonable Intervention | Risks to Measure |
| --- | --- | --- |
| CPU near limit, workers `RUNNABLE` doing computation | Reduce work/improve algorithm, reduce oversubscription, bound parallelism | Context switches, GC, throughput when reducing threads |
| Low CPU, workers waiting on I/O, downstream has capacity | Timeouts, async processing, or bounded concurrency increase | Downstream saturation, connection pool, tail latency |
| High queue wait, low execution time, active workers genuinely busy | Adjust pool size for workload, admission control | Memory, rejections, p99, completion rate |
| Queue grows alongside downstream latency | Address dependency, limit input and retries | Retry storms, cascading timeouts |
| Many threads waiting long on the same monitor | Shrink critical section / reduce lock contention | Correctness, races, visibility |
| `Future.get()` from tasks on the same fixed pool | Remove blocking dependency or redesign scheduling | Task ordering, cancellation, error propagation |
| Deadlock confirmed by lock cycle | Fix lock ordering, nested locks, acquisition protocol | Correctness, livelock, timeout semantics |
| GC pauses coincide with spikes and high allocation | Reduce unnecessary allocations, tune heap/GC based on evidence | Throughput, heap pressure, latency |
| Rejections due to genuine overload | Bounded queue, backpressure, and explicit failure policy | Caller impact, dropped work, retries |
| Incomplete metrics or single snapshot only | Increase observability in a controlled manner | Instrumentation overhead |

## 13. Common Mistakes

- **Adding threads when CPU is already saturated:** adds scheduling overhead and cache misses without necessarily increasing completed work.
- **Making the queue unbounded to "eliminate errors":** merely turns overload into latency and memory pressure; many tasks may time out before ever running.
- **Checking only `pool.getActiveCount()` without inspecting stacks:** high active count does not tell you whether workers are burning CPU or blocked.
- **Treating every `WAITING` thread as a deadlock:** idle workers waiting on a queue is normal.
- **Assuming no `BLOCKED` means no lock contention:** `ReentrantLock` can use `park` and appear as `WAITING`.
- **Using `Thread.sleep` to "fix races" in diagnostic code:** sleep does not prove a worker has reached a specific step; use a latch/phaser/condition with explicit signaling.
- **Reading one thread dump and immediately making changes:** thread state is a snapshot; correlate multiple snapshots and metrics.
- **Measuring only average latency:** can miss the p99 tail, where queueing and contention show up clearly.
- **Ignoring rejections/cancellations:** throughput counting only completed work misses lost/rejected tasks.
- **Forgetting to shut down executors:** live thread pools prevent applications from exiting cleanly; call `shutdown()` and, where appropriate, `awaitTermination()`/cancellation paths.
- **Seeing more completed tasks while ignoring correctness:** races, lost updates, or skipped tasks are not optimizations.

## 14. Self-Check Questions

**Q1. Does a long queue prove the pool size is too small?** No. You must examine completion rate, task execution duration, and why workers are busy or waiting.

**Q2. Does the `RUNNABLE` thread state mean a thread is consuming CPU?** No. It is a JVM state that includes waiting for CPU or executing in native code; measure CPU time and appropriate OS state.

**Q3. Does the `WAITING` thread state mean a deadlock?** No. A thread may legitimately wait on a queue, condition, latch, join, or future. Check the stack, dependencies, and wait duration.

**Q4. Does `findDeadlockedThreads()` returning `null` prove there is no starvation?** No. The API only detects certain monitor/ownable synchronizer cycles among platform threads, not every wait-for-task situation.

**Q5. Why can increasing `maximumPoolSize` with an unbounded queue be useless?** Once core workers exist and the queue always accepts tasks, the executor generally has no reason to create additional workers up to the maximum.

**Q6. Why must queue wait be measured separately from task execution time?** Because the bottleneck may occur before the task runs or inside the task; the two problems have different remedies.

**Q7. Should you replace `synchronized` with `ReentrantLock` as soon as contention appears?** No. Inspect the critical section, lock hold time, and semantics, and re-measure before choosing an alternative structure.

**Q8. If a test increasing a pool from 8 to 16 workers boosts throughput by 10%, is that enough to finalize?** Not yet. You need to inspect variance, p95/p99, CPU, memory, errors/rejections, downstream impact, and representative workload under realistic load.

## 15. Pre-Decision Diagnostic Checklist

- [ ] Clearly identify the affected workload, time window, and problematic metric.
- [ ] Collect submission rate, completion rate, rejections, queue depth, queue wait, and execution time simultaneously.
- [ ] Collect CPU, memory/GC, and thread count relative to core count.
- [ ] Capture thread dumps/JFR during the symptom window, distinguishing normal waiting from abnormal states.
- [ ] Check whether tasks wait on `Future`s of other tasks in the same executor.
- [ ] Confirm contention owner, lock hold time, and call sites before changing locks.
- [ ] Confirm downstream capacity, timeouts, and retries before increasing parallelism.
- [ ] Identify whether the queue is bounded/unbounded and what the rejection policy is.
- [ ] Formulate a fix hypothesis with confirmation and falsification criteria.
- [ ] Make small changes with rollback ready, and re-measure throughput, tail latency, errors, and correctness.

### Java SE / OpenJDK References

- [`ThreadPoolExecutor` — Queueing, rejection, and monitoring methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [`Thread.State` — thread state definitions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html)
- [`ThreadMXBean` — CPU, contention monitoring, and deadlock detection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [`jcmd` — thread dump and JFR diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK Mission Control and JFR](https://openjdk.org/projects/jmc/)

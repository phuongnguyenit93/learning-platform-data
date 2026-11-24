# 9.1 Distinguishing Deadlock, Livelock, Starvation, and Long Waits

## Learning Objectives

A Java service may still be running and report no exceptions, yet **fail to complete work**. Operators often refer to this collectively as a “hang”; however, four distinct mechanisms can produce a similar symptom:

- **Deadlock:** multiple threads form a resource dependency cycle, and no thread in the cycle can proceed.
- **Livelock:** threads remain active, repeatedly reacting or retrying, but their interaction causes useful progress to be zero.
- **Starvation:** a thread or task is continuously deprived of opportunities to acquire a resource or be scheduled, even though other work continues to make progress.
- **Long wait:** a call waits for I/O, a lock, a signal, or a result for too long relative to its time budget; this may be caused by a slow or unresponsive dependency and **does not necessarily** involve deadlock or starvation.

Accurate classification helps determine whether to look for a **lock cycle**, a **retry loop**, **resource/queue fairness**, or **deadlines/external dependency paths**, instead of blindly increasing thread counts, forcing GC, or restarting without evidence.

After this lesson, you will be able to:

1. Define and distinguish the four phenomena by **progress**, thread state, lock ownership, CPU, queue, and timeout.
2. Read multi-point thread dumps, distinguishing `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING`; understand why these states **are not a complete diagnosis**.
3. Use `ThreadMXBean`, `ThreadInfo`, `findMonitorDeadlockedThreads()`, and `findDeadlockedThreads()` within their proper scope; recognize limitations regarding dependencies outside the JVM.
4. Collect metrics such as completed jobs, retries, per-thread CPU delta, lock owner, queue waiting age, and downstream latency to verify hypotheses.
5. Practice **time-bounded** Java 17+ scenarios in a lab program; keep intentional deadlock examples separate from real applications.
6. Design preventive measures: lock ordering, shrinking lock-holding regions, backoff with jitter, bounded queues, fairness when needed, timeouts/deadlines, cancellation, and progress monitoring.
7. Write diagnostic conclusions stating the scope of evidence and limitations, avoiding equating “no deadlock detected” with “no problem.”

## 1. First, Define “Progress”

You should not use “high CPU,” “low CPU,” “threads are WAITING,” or “the application hasn’t crashed” as the sole measure. A system can execute many loops without completing a single transaction; a worker can sit idle while other workers finish their work; a call waiting 30 seconds might be valid for a batch report, yet be a failure for an API with a 300 ms SLO.

**Useful progress** must be measured in business/operational terms, for example:

- Number of requests **completed** and returning a response, not just requests received.
- Number of jobs **acknowledged/committed**, not just the number of dequeue attempts.
- Number of records actually processed successfully, not just retry attempts.
- Whether queue oldest-item age decreases, not just whether queue length fluctuates.
- Whether a specific task has transitioned to a completed/failed/canceled state.
- End-to-end latency relative to the deadline, not just whether an internal method runs fast.

For example:

```text
14:00:00  requestsReceived=1000  requestsCompleted=980
14:00:10  requestsReceived=1100  requestsCompleted=980
14:00:20  requestsReceived=1200  requestsCompleted=980
```

Over 20 seconds, 200 new requests arrived, yet **no additional requests completed**. This is a “lost progress” signal, which does not yet identify deadlock, livelock, starvation, or downstream wait. Thread dumps, queue/lock metrics, and dependency traces are needed.

### 1.1 “Application Hang” Has Multiple Scopes

- A single **thread** is blocked, while other threads continue serving normally.
- A **thread pool** loses processing capacity because workers are occupied by waiting tasks.
- A **component** (payment/cache/message consumer) stops making progress while the health endpoint still returns OK.
- The **entire process** becomes unresponsive, possibly due to CPU saturation, safepoints, locks, GC, native I/O, or other faults.
- The **entire distributed system** stalls due to a dependency, rate limit, or RPC cycle across services.

Investigation must specify the scope before inferring the cause.

## 2. Quick Comparison of the Four Phenomena

| Criterion | Deadlock | Livelock | Starvation | Long wait |
| --- | --- | --- | --- | --- |
| Primary mechanism | Resource/lock wait cycle | Repeatedly reacting, yielding/changing state without finishing work | One party is denied resource opportunities | Waiting on a condition/event/dependency beyond budget |
| Active execution? | Parties in the cycle are typically blocked/parked | **Yes**; repeated retry/yield/backoff | Deprived party may sit waiting while others keep running | Usually little activity on the waiting side, though not strictly required |
| Useful progress | Zero for parties in the cycle | Zero or near zero despite rising attempts | Zero progress for the affected party; others can complete | No progress for the waiting operation; other operations can complete |
| Lock ownership cycle? | Usually yes for lock deadlocks; can also be a logical dependency cycle outside locks | Not required | Not required | Not required |
| CPU | Typically low on blocked threads; no fixed rule for the whole process | Can be high with tight retries; can be low with backoff | No fixed CPU pattern | Typically low during blocked I/O/park, though JVM state depends on the API |
| Thread dump | `BLOCKED`, `WAITING`, or `TIMED_WAITING` depending on lock/synchronizer | Stack changes or stays in the same retry section; can be `RUNNABLE`/`TIMED_WAITING` | Victim waits on a lock or **has not yet been run by an executor**, so it does not appear as an executing thread | I/O, `Future.get`, `CountDownLatch.await`, `wait`, `park`, lock… |
| Remediation direction | Break circular wait, lock ordering, reduce lock nesting | Randomized/exponential backoff, clear priority, avoid symmetric collisions | Appropriate fairness, scheduling/queue isolation, reduce monopolization | Deadlines/timeouts, propagate cancellation, address dependency and resource leaks |

**Warning:** this table presents common indicators, not a classification rule based on a single metric. A logical deadlock between two `Future`s can put a worker in `WAITING` without being detected by `ThreadMXBean.findDeadlockedThreads()`. A livelock can include `Thread.sleep()` and have low CPU. Task starvation in a queue may not even **have its own stack trace**, because no worker has run it yet.

## 3. Deadlock: A Cycle of Waiting for Locks or Resources

### 3.1 Mechanism

Suppose two threads traverse the same two monitors in opposite orders:

```text
Thread A holds Lock X, wants to acquire Lock Y
Thread B holds Lock Y, wants to acquire Lock X

A --waits for Y held by B--> B
^                          |
|----waits for X held by A-|
```

If neither releases its lock until it acquires the other lock, neither can advance. This is a **monitor-style deadlock**.

A common model for understanding the necessary conditions of a resource deadlock is the four Coffman conditions:

1. **Mutual exclusion:** a resource can be used by only one party at a time.
2. **Hold and wait:** holding one resource while waiting for another.
3. **No preemption:** resources cannot be safely reclaimed by force.
4. **Circular wait:** a cycle of ownership waiting exists.

Breaking a suitable condition can prevent a design from entering deadlock—for example, enforcing a consistent lock acquisition order. This is an explanatory model, not a checklist proving every “hang” is caused by locks.

### 3.2 Java Deadlocks Are Not Only `synchronized`

There are at least three classes to distinguish:

**Intrinsic monitor deadlock:** occurs with `synchronized` and object monitors; `ThreadMXBean.findMonitorDeadlockedThreads()` is designed to detect these monitor cycles.

**Ownable synchronizer deadlock:** for example, `ReentrantLock` instances owned and waited on mutually by threads. `ThreadMXBean.findDeadlockedThreads()` can find cycles involving object monitors **and ownable synchronizers** when the VM supports monitoring this type. Check `isSynchronizerUsageSupported()` and handle `UnsupportedOperationException`.

**Logical/distributed deadlock:** a worker in a single-thread executor waits on `Future.get()` of another job queued **behind** it in the same queue; or service A calls B synchronously and B waits on A. This can form a dependency cycle that is not represented as a monitor/ownable synchronizer cycle in the JVM. The two deadlock APIs above **do not guarantee detection**.

Example of an executor dependency deadlock:

```java
// Anti-pattern illustration snippet, DO NOT run as-is.
// The executor only has one worker; the outer task is waiting for the inner task,
// but the inner task can only run when the current worker is released.
Future<?> outer = singleThreadExecutor.submit(() -> {
    Future<?> inner =
            singleThreadExecutor.submit(() -> doWork());
    inner.get(); // needs checked exception handling; may wait forever
});
```

This is **not a standalone Java program**, because `doWork()` and the executor variable are placeholders illustrating the concept. By design, do not block a worker on work that requires that very worker to execute. In production, use an acyclic dependency graph, appropriate async composition, or separate pools/preprocessing and deadlines.

### 3.3 Symptoms and Evidence Collection

A monitor deadlock typically exhibits:

- Two or more threads `BLOCKED` while waiting for monitors.
- Each thread holds a monitor that another thread is waiting for.
- Thread dumps taken at intervals continue to show the same cycle.
- Completed requests/jobs may stall for the affected business paths.
- `findMonitorDeadlockedThreads()` may return an array of thread IDs in the cycle.

However, **having no deadlock result** does not prove the entire system is not hung: it could be another JVM, a dependency outside the JVM, a resource type not monitored, or an issue not present at the exact sampling moment.

### 3.4 Prevention

- **Global lock ordering:** every code path acquires X then Y, with nowhere acquiring Y then X.
- Reduce the number of locks held simultaneously and lock-holding duration.
- Do not hold monitors during network/DB calls or unbounded `Future.get()` waits.
- With `Lock`, consider `tryLock(timeout, TimeUnit)` when semantics allow; on failure, **release all already-acquired locks** in `finally`, and do not hot-retry.
- Use immutable data, concurrent collections, single-writer design, or message passing when appropriate.
- Test concurrency under load and use lock graphs / thread dumps / JFR / metrics as evidence.

For `synchronized`, a thread that is `BLOCKED` waiting to acquire a monitor **does not automatically exit on `interrupt()`** like a `lockInterruptibly()` call; do not treat interrupt as a “cure” for monitor deadlocks. `Thread.stop()` is unsafe and is not an acceptable solution.

## 4. Livelock: Threads Remain Active but Do Not Finish Work

### 4.1 Mechanism

Two “polite people” yielding the hallway to each other:

```text
Round 1: A sees B wants to pass → A yields
         B sees A wants to pass → B yields
Round 2: both retry at the same time → both yield again
Round 3: repeats the same way → neither gets through
```

Similarly in Java: two workers detect a conflict, both roll back, both immediately retry, and collide again due to a **symmetric strategy**. Threads may consume CPU, emit logs, increment retry counters, and flip states back and forth, yet **completed work = 0**.

Livelock differs from deadlock in that the system **is not merely sitting still waiting on an immovable lock**; parties are actively working or reacting, and the interaction mechanism itself prevents useful progress.

### 4.2 Indicators

- Retry/attempt counters grow very fast while completion/commit rates do not rise correspondingly.
- CPU may be high due to busy retries, or low if each retry sleeps/backs off.
- Stacks captured across multiple samples may oscillate across retry, conflict check, and release/reacquire.
- Logs contain many “conflict, retry”, “CAS failed”, “optimistic lock failure”, or “temporary unavailable” messages.
- There is not necessarily a monitor cycle for `ThreadMXBean` to report a deadlock.

**Note:** a retry loop with many failures **is not automatically a livelock**. An upstream dependency might genuinely be returning continuous errors; in that case the root cause is a failing dependency, while uncontrolled retries act as an aggravating factor. You must analyze the relationship between actors and why attempts produce no progress.

### 4.3 Preventing Livelock

- **Exponential backoff with jitter**: two actors do not keep retrying on a synchronized cadence forever.
- Cap retry attempts / retry budget / deadline and surface failures to a handleable error path.
- Use a deterministic priority rule or conflict resolution so both do not yield infinitely.
- For locked resources, consider lock ordering or a handoff protocol.
- With optimistic concurrency, only retry if the chance of success changes; do not busy-spin infinitely on the same data version.
- Measure **successful commits per second** alongside attempts per second; do not mistake “lots of activity” for health.

Jitter only **reduces the probability** of in-phase collisions in many models; it is not a mathematical proof that all livelocks are eliminated.

## 5. Starvation: A Task Is Denied Its Chance

### 5.1 Mechanism

A worker/task can wait for a very long time because others are repeatedly chosen to run or use a resource:

- An **unfair** lock can be repeatedly claimed by other contenders, leaving one waiter unchosen.
- A small thread pool is monopolized by long-running tasks; tasks behind them sit waiting in the queue.
- High-priority work keeps arriving, so low-priority tasks never get a “slot.”
- A semaphore/connection pool is monopolized or returned slowly, leaving one group of requests constantly resource-starved.
- Scheduling policy / cgroup CPU throttling and OS contention leave some threads without enough runtime, though starvation cannot be concluded from low CPU alone.

**Distinguishing trait:** **other** tasks can still complete, while a victim waits indefinitely or fails to receive the resources it needs.

### 5.2 Starvation vs. Normal Queue Wait

A queue with 100 jobs where each worker takes 1 second/job will legitimately have wait time if workload arrives quickly while still achieving fairness. Not every queued job is “starved.”

To prove meaningful starvation, observe:

- **Oldest queued item age** climbs continuously even while the system completes other jobs.
- Per-task wait time / tail latency exceeds the deadline/SLO by many multiples.
- Certain task groups are systematically delayed while another priority group repeatedly claims slots.
- Lock/semaphore acquisition distribution is skewed or one party repeatedly fails.
- The queue uses priority/barging policies without aging/fairness.
- Thread dumps can identify busy workers; however, a task that **has not started running yet** does not necessarily have its own `Thread` to show a stack.

### 5.3 Avoiding Starvation

- Choose **fair scheduling** where needed; a `ReentrantLock(true)` prioritizes long-waiting threads under contention, though it **does not guarantee absolute OS scheduling fairness** and may reduce throughput.
- Isolate pools for long/blocking work from pools handling short requests.
- Set bounded queue capacities, backpressure, and admission control instead of unbounded queues.
- Use aging in priority queues if the domain permits; avoid letting low-priority work be permanently excluded.
- Set deadlines on time spent in the queue, not only timeouts once a task starts.
- Track queue age by class/priority, number of tasks that have not had a turn, and completion rates.
- Do not treat the victim running **once** after several minutes as proof that scheduling is fair.

A single-thread pool with task A waiting indefinitely and task B queued behind it illustrates **task starvation / queue starvation risk**; it can be the outcome of an initial long wait. A real incident can involve **multiple mechanisms** simultaneously, and they must be analyzed causally.

## 6. Long Waits: Not Automatically Deadlock

### 6.1 Types of Waits

- `Future.get()` without a timeout waiting on a task/dependency.
- `CountDownLatch.await()` waiting for a signal whose producer path failed.
- `BlockingQueue.take()` waiting for a message while the producer has stopped.
- `Object.wait()` or `Condition.await()` waiting for notification.
- Socket/JDBC/RPC read waiting on a server/downstream, potentially lacking a read/query timeout or deadline.
- `Thread.join()` waiting for another thread to finish.
- `LockSupport.park()` waiting for unpark/interrupt/event; **`WAITING` does not state the business reason**.
- `ReentrantLock.lock()` waiting on a lock held too long by another thread.
- DNS/connect/SSL handshake and filesystem/network I/O have their own timeout mechanisms.

An operation waiting 20 seconds may be **completely valid** for a job awaiting a batch window, yet wrong for a request with a 2-second deadline. There is no universal absolute threshold to classify a “long wait” across all workloads.

### 6.2 Bounded vs. Unbounded Waits

```java
// Integration illustration snippet:
String value = future.get(250, TimeUnit.MILLISECONDS);
```

`Future.get(timeout, unit)` throws `TimeoutException` when the wait budget expires before a result is ready. **It does not guarantee that the background task has stopped.** You must design cancellation, signaling/interruption, lower-layer I/O timeouts, and cleanup paths, while handling `InterruptedException` purposefully.

Different timeout APIs do not necessarily govern the same conditions: `socket.setSoTimeout(...)` applies appropriately to socket reads, JDBC driver/query timeouts have their own semantics, and gRPC/HTTP clients have deadline/connect/read/overall timeouts depending on the library. When an end-to-end request has 500 ms, you should not sequentially give 5 dependencies 500 ms each without propagating the **remaining deadline**.

### 6.3 Long Waits Without Deadlock

For example, service A waits for an HTTP response from a server under maintenance. Thread A may be blocked in a socket read; it does not hold a monitor that service B is waiting on to form a cycle. `findDeadlockedThreads()` legitimately returns `null`. This is an **unbounded or overdue wait**, not evidence of deadlock.

Conversely, a worker in a single-thread executor waiting on the future of a task queued behind it creates a **dependency cycle**, which can be called a logical deadlock even though the monitor deadlock detector does not see it. Thus a “long wait” is an **operation-level symptom**, which can be an independent mechanism or a consequence of deadlock/starvation.

### 6.4 Prevention

- Define end-to-end deadlines and per-stage timeouts.
- Propagate the remaining time budget across layers and dependencies.
- Limit blocking calls on small pools; prefer async composition where appropriate.
- Use interruptible waits/locks when APIs and semantics permit, with cleanup in `finally`.
- Do not retry infinitely after timeouts; combine backoff, circuit breakers, retry budgets, and idempotency.
- Distinguish **caller** timeout from actually stopping **remote work**; implement a cancellation protocol if available.
- Track latency per dependency and oldest in-flight age.

## 7. Reading Thread States Properly

Java 17 defines `Thread.State` with states `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED`. These are JVM states, **not a one-to-one mapping to OS process/thread states**.

| State | Standard Meaning | What Not to Conclude Hastily |
| --- | --- | --- |
| `RUNNABLE` | Thread is executing in the JVM or runnable; may be waiting for OS resources such as CPU | “Definitely using 100% CPU” |
| `BLOCKED` | Waiting to acquire an intrinsic monitor to enter/reenter `synchronized` | “Definitely a deadlock” |
| `WAITING` | Waiting indefinitely for another action/signal; e.g., `Object.wait`, `join`, `park` | “Definitely broken” |
| `TIMED_WAITING` | Waiting with a bound per API: sleep/timed wait/park | “Definitely will make progress before business deadline” |
| `TERMINATED` | Thread has finished execution | “Can still get this thread’s stack from getAllThreadIds” |

**Specifically:** having many threads in a pool in `WAITING` when the queue is **empty** is normal. A `RUNNABLE` thread in a native socket read / OS wait does not prove CPU is busy. A thread in `BLOCKED` for a few milliseconds can be normal contention.

With `ReentrantLock` or `Condition`, waiting typically goes through park/AQS and may show up as `WAITING`/`TIMED_WAITING`, not necessarily `BLOCKED`. You must inspect **the stack, lock owner, and awaited resource**, not just the state.

## 8. Thread Dumps: What to Capture and How to Read Them

### 8.1 Capturing Data from the Right JVM

Example with HotSpot JDK 17+ and a JVM you have permission to manage:

```bash
jcmd -l
jcmd <PID> Thread.print -l
```

`<PID>` is a **placeholder to replace with the actual numeric PID**, not literal text to type. `jcmd -l` may not see JVMs in a different container/PID namespace. In container environments, verify the exact pod/container, PID namespace, effective user, whether the image has JDK tools, and the JVM start time.

`Thread.print -l` provides stack traces and lock info depending on JVM/version; it has overhead and can increase latency on systems with many threads. If unsure of options, run `jcmd <PID> help Thread.print`.

**Do not rely on a single sample:** take 3–5 timestamped samples (e.g., 2–5 seconds apart) when system state allows. Duration and count must fit the workload, avoiding continuous high-frequency dump scripts that worsen the incident.

An example sampling schedule:

```text
T0: record p99, completed rate, queue depth/age, CPU/GC
T1: thread dump #1
T2: thread dump #2
T3: thread dump #3
T4: compare stacks/owners/retries/queue age and record the collection impact
```

This is an **illustrative structure**, not measured output from a JVM.

### 8.2 What to Inspect in a Dump

1. Thread name and ID (tied to the right JVM/instance).
2. Thread state.
3. Top stack frames and call path, especially `synchronized`, `LockSupport.park`, `FutureTask.get`, `ThreadPoolExecutor.getTask`, socket reads, and database clients.
4. Locks **awaited** (`waiting to lock`, `parking to wait for`) and locks **held**.
5. Lock owner; trace `A → B → A` cycles if any.
6. Is a thread currently holding a lock while performing I/O under that lock?
7. Changes across multiple samples: does the stack repeat a retry loop? Does the owner change? Do request completions increase?
8. Correlate with request/trace IDs if available; thread pool names do not always match business IDs.

**A thread dump reflects a single instant**, not how long the thread has been waiting in that state. To know “how long the wait lasted,” you need timestamps, logging instrumentation, duration metrics, multiple samples, or suitable contention monitoring.

## 9. ThreadMXBean: A Scoped Deadlock Detector

In Java 17:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
long[] monitors = mx.findMonitorDeadlockedThreads();
```

**`findMonitorDeadlockedThreads()`** finds cycles of threads waiting to acquire **object monitors** (typically involving `synchronized`). The result is `long[]` thread IDs or `null` if none is found.

```java
if (mx.isSynchronizerUsageSupported()) {
    long[] broader = mx.findDeadlockedThreads();
}
```

**`findDeadlockedThreads()`** includes cycles waiting on **object monitors and ownable synchronizers** when supported by the JVM; it can throw `UnsupportedOperationException` if the VM does not support ownable synchronizer monitoring.

These are **two integration snippets**, requiring `import java.lang.management.*` and appropriate error handling.

| API | Usable Data | Limitations |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Threads in a monitor deadlock cycle | Does not detect all other lock/dependency types |
| `findDeadlockedThreads()` | Object monitors + ownable synchronizers | Support-dependent; does not cover every wait type |
| `getThreadInfo(ids, maxDepth)` | Stack, state, lock owner at sample time | May return `null` for terminated threads; snapshot |
| `getThreadCpuTime(id)` | Cumulative CPU time if supported/enabled | `-1` when unavailable; use deltas, not lifetime values |
| Contention monitoring | Blocked/waited counts/time | Times only available when feature is supported and enabled; has overhead |

### 9.1 `null` Does Not Mean “The System Has No Deadlock”

`findDeadlockedThreads()==null` means **no cycle within the API’s scope was detected at the moment of invocation**. It does not rule out:

- Logical deadlocks across `Future`s, queues, latches, or callbacks.
- Network/DB/resource deadlocks in another process.
- Livelock and starvation.
- Long waits without a cycle.
- Transient deadlocks whose state changed before sampling.
- Scope outside the synchronizer types monitored by the API.

In newer JDKs with virtual threads, verify monitoring/tool capabilities for that specific JDK: `ThreadMXBean` is not a comprehensive profiler for all virtual threads. This lab targets **Java 17 platform threads**.

### 9.2 ThreadInfo Lock Owner and Stack

With detected IDs:

```java
ThreadInfo[] infos = mx.getThreadInfo(ids, 32);
for (ThreadInfo info : infos) {
    if (info != null) {
        System.out.println(info.getThreadName()
                + " state=" + info.getThreadState()
                + " waitingFor=" + info.getLockName()
                + " owner=" + info.getLockOwnerName());
    }
}
```

This is an **integration illustration snippet**; it needs `ids` from a detector API and importing `ThreadInfo`. When held locks are needed, see the overload `getThreadInfo(ids, lockedMonitors, lockedSynchronizers)`, but check `isObjectMonitorUsageSupported()`/`isSynchronizerUsageSupported()` accordingly and weigh the cost.

Do not use these diagnostic methods to **control lock ordering** in an application. They are meant for troubleshooting/management, and results can change immediately after the snapshot.

## 10. CPU, Retries, and Metrics: Signals to Identify the Phenomenon

An incident with only `requestCompleted=0` and low CPU is not enough. Place the signals side by side:

| Signal in Window | Deadlock | Livelock | Starvation | Long wait |
| --- | --- | --- | --- | --- |
| Completed work of affected group | Stopped | Stopped/near 0 | Victim stopped, other groups may continue | Waiting operation stopped |
| Retry/attempt counters | Not necessarily increasing | **Typically increasing** | May increase if denied resources | May stay flat or retry depending on caller layer |
| Thread CPU delta | Blocked threads may be low | May be high (busy retry) or low (backoff) | Victim low; contender may be high | Usually low on the waiting operation |
| Lock cycle evidence | Yes for lock deadlock | Not required | Not required | Not required |
| Queue oldest-item age | May increase as workers stall | May increase | **Very useful** to spot a starved victim | May increase if workers are waiting |
| Dependency latency | Situation-dependent | May relate to conflicts | May relate to pool contention | **Primary focus** when waiting on I/O |
| Thread stacks across samples | Stable owner cycle | Retry path/active transitions | Victim waiting/queued, others progressing | A wait call, latency/timer/dependency |

### 10.1 Computing CPU Across Two Timestamps

`ThreadMXBean.getThreadCpuTime(id)` returns cumulative CPU time in **nanoseconds** when supported and enabled. An example:

```text
T1: threadCpuNs=8_000_000_000
T2: threadCpuNs=8_150_000_000
elapsedWallNs=500_000_000
deltaCpuNs=150_000_000
Equivalent CPU share of one logical CPU = 150/500 * 100 = 30%
```

This percentage is **not** 30% of the entire multi-core node; you must state the denominator if comparing against container/CPU quota. Check `isThreadCpuTimeSupported()` and `isThreadCpuTimeEnabled()`; `-1` means no valid value, not 0. When a thread dies or IDs change, do not mix counters from two different threads.

### 10.2 Contention Time Does Not Measure Every Kind of Wait

`ThreadInfo.getBlockedTime()` reflects time blocked due to monitor contention when monitoring is enabled; `getWaitedTime()` reflects wait time according to API semantics, not “all socket read time.” If the feature is disabled, times may be `-1`. Enabling monitoring in production is a **diagnostic state change** with overhead and its timestamp should be recorded.

A worker waiting on `Future.get()` or the network may not have high blocked time. Do not use `getBlockedTime()==0` to rule out latency or starvation.

## 11. Java 17 Practice: A Safe Mode-by-Mode Program

The program **`HangPatternsLab.java`** has the following modes:

- `fixture`: only prints a fixed summary table, **exact** stdout.
- `deadlock`: intentionally creates a **monitor deadlock** between **two daemon threads in a separate lab JVM**, then uses `ThreadMXBean` to find them; does not join the deadlocked threads.
- `livelock`: simulates **two actors repeatedly seeing a conflict and both yielding** for a finite number of rounds. They remain active/retrying without business progress; this is a simulation of a livelock strategy, not a production lock algorithm.
- `starvation`: a single-thread executor has its first task occupy the worker while the next task waits in the queue before release; this simulates **queue starvation risk**, and does not prove the system always starves infinitely.
- `longwait`: a `CompletableFuture` is never completed, and `get` uses a timeout; simulates an operation waiting for an event that does not arrive within the deadline.

**Only run these modes on a lab process that you own.** The `deadlock` mode intentionally creates a cycle and is not meant for an application server. The other modes do not send network requests or interact with other JVMs.

Create the file `HangPatternsLab.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.atomic.AtomicInteger;

public class HangPatternsLab {
    static void fixture() {
        System.out.println("deadlock: circular lock wait, no progress");
        System.out.println("livelock: active retries, no progress");
        System.out.println("starvation: victim denied execution opportunities");
        System.out.println("longwait: external event absent before deadline");
    }

    static void acquireInOppositeOrder(Object own, Object other,
            CountDownLatch ready, CountDownLatch proceed) {
        synchronized (own) {
            ready.countDown();
            try {
                proceed.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (other) {
                // Intentionally unreachable once both threads have first locks.
            }
        }
    }

    static void deadlockLab() throws InterruptedException {
        Object left = new Object();
        Object right = new Object();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread a = new Thread(
                () -> acquireInOppositeOrder(
                        left, right, ready, proceed), "lab-deadlock-A");
        Thread b = new Thread(
                () -> acquireInOppositeOrder(
                        right, left, ready, proceed), "lab-deadlock-B");
        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        if (!ready.await(3, TimeUnit.SECONDS)) {
            proceed.countDown();
            System.out.println("deadlock=lab-not-ready");
            return;
        }
        proceed.countDown();

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        boolean detected = false;
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(3);

        while (System.nanoTime() < deadline) {
            long[] ids = mx.findMonitorDeadlockedThreads();
            if (ids != null) {
                boolean hasA = Arrays.stream(ids)
                        .anyMatch(id -> id == a.getId());
                boolean hasB = Arrays.stream(ids)
                        .anyMatch(id -> id == b.getId());
                if (hasA && hasB) {
                    detected = true;
                    break;
                }
            }
            Thread.sleep(20);
        }
        System.out.println("monitorDeadlockDetected=" + detected);
    }

    static void livelockLikeLab() throws InterruptedException {
        CyclicBarrier bothAttempt = new CyclicBarrier(2);
        AtomicInteger retries = new AtomicInteger();

        Runnable polite = () -> {
            try {
                for (int i = 0; i < 5; i++) {
                    bothAttempt.await(3, TimeUnit.SECONDS);
                    // Both notice a conflict and both give way.
                    retries.incrementAndGet();
                    bothAttempt.await(3, TimeUnit.SECONDS);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException | TimeoutException ex) {
                System.err.println("lab barrier failed: " + ex);
            }
        };

        Thread a = new Thread(polite, "polite-A");
        Thread b = new Thread(polite, "polite-B");
        a.start();
        b.start();
        a.join(7_000);
        b.join(7_000);
        if (a.isAlive()) a.interrupt();
        if (b.isAlive()) b.interrupt();
        System.out.println("retries=" + retries.get()
                + " usefulCompletions=0");
    }

    static void starvationLikeLab() throws Exception {
        ExecutorService single = Executors.newSingleThreadExecutor();
        CountDownLatch releaseFirst = new CountDownLatch(1);
        try {
            Future<?> first = single.submit(() -> {
                releaseFirst.await();
                return null;
            });
            Future<String> victim = single.submit(() -> "DONE");
            boolean missedWindow = false;
            try {
                victim.get(80, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                missedWindow = true;
            } finally {
                releaseFirst.countDown();
            }

            first.get(3, TimeUnit.SECONDS);
            String result = victim.get(3, TimeUnit.SECONDS);
            System.out.println("victimMissedWindow=" + missedWindow
                    + " recovered=" + "DONE".equals(result));
        } finally {
            releaseFirst.countDown();
            single.shutdownNow();
        }
    }

    static void longWaitLab() throws Exception {
        CompletableFuture<String> response = new CompletableFuture<>();
        boolean timedOut = false;
        try {
            response.get(80, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            timedOut = true;
        } finally {
            response.cancel(true);
        }
        System.out.println("waitTimedOut=" + timedOut
                + " futureCancelled=" + response.isCancelled());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java HangPatternsLab "
                    + "fixture|deadlock|livelock|starvation|longwait");
            return;
        }
        switch (args[0]) {
            case "fixture" -> fixture();
            case "deadlock" -> deadlockLab();
            case "livelock" -> livelockLikeLab();
            case "starvation" -> starvationLikeLab();
            case "longwait" -> longWaitLab();
            default -> System.out.println("Unknown mode");
        }
    }
}
```

### 11.1 Compile and Run the Deterministic Mode

Requires JDK 17 or newer:

```bash
javac HangPatternsLab.java
java HangPatternsLab fixture
```

**Exact** stdout of `fixture`:

```text
deadlock: circular lock wait, no progress
livelock: active retries, no progress
starvation: victim denied execution opportunities
longwait: external event absent before deadline
```

The `fixture` mode **only prints four definitions**, creating no locks, threads, waits, executors, or network activity. Therefore stdout is stable and independent of machine speed.

### 11.2 Deadlock Mode — Timing/VM-Dependent Output

Run **in a fresh lab JVM**, never put into production:

```bash
java HangPatternsLab deadlock
```

`CountDownLatch ready` ensures both A and B already hold their first monitor before `proceed` allows them to request the second monitor. This is an intentional monitor cycle. On HotSpot supporting the detector and under normal scheduling, the line typically observed is:

```text
monitorDeadlockDetected=true
```

If setup times out or detection does not finish in time, the program may print `deadlock=lab-not-ready` or `monitorDeadlockDetected=false`. Therefore **no fixed stdout is guaranteed** for this mode. The deadlocked threads are **daemon** threads, so they do not keep the lab JVM alive indefinitely when main exits. Do not move this deadlock snippet directly into a test sharing a long-lived JVM.

Why not `join()` A/B? An unbounded `join` on deadlocked threads would hang `main`, breaking the finiteness of the lab.

### 11.3 Livelock Mode — Active Progress Still Yields 0 Completions

```bash
java HangPatternsLab livelock
```

Two threads use `CyclicBarrier` to go through 5 rounds of *both try, both yield*. Under normal conditions, the illustrative output is:

```text
retries=10 usefulCompletions=0
```

Each thread records one retry across 5 rounds; neither completes any business task. This is an **intentional simulation of symmetric retry/yielding**, not a production CAS or lock implementation. If the barrier times out or is interrupted, the retry count may be smaller and stderr logs may appear; the core lesson is that **increasing attempts does not mean increasing completed work**.

A real livelock can persist indefinitely without a tie-breaker/backoff or deadline. The lab **bounds the number of rounds** so it does not cause an infinite loop on the learner’s machine.

### 11.4 Starvation Mode — Task Stuck Behind a Worker-Occupying Task

```bash
java HangPatternsLab starvation
```

In a single-thread executor, the first task occupies the worker waiting on `releaseFirst`, and the second task sits behind it in the queue. The mode tries waiting for the second task for **80 ms**, then releases the first task and verifies that the second task eventually executes.

Normal output:

```text
victimMissedWindow=true recovered=true
```

This is a **controlled simulation of queue starvation risk / scheduling delay**, and **does not** by itself prove a program suffers permanent starvation. Because the first worker is waiting on a latch rather than a monitor cycle, the deadlock detector may not see it. Once the first worker is released, the later task can run.

It is important to track **time spent waiting in the queue** and oldest-item age; having 1 worker alone does not prove a bug, as sequential designs can be completely valid when tasks are short and backlog is bounded.

### 11.5 Longwait Mode — Deadline Instead of Waiting Forever

```bash
java HangPatternsLab longwait
```

A `CompletableFuture` has no producer completing it; `get(80, MILLISECONDS)` times out. Under normal conditions:

```text
waitTimedOut=true futureCancelled=true
```

`cancel(true)` marks the **Future** as canceled; here no real background work is running. In production, `Future.cancel(true)` **does not guarantee** that a remote network call, thread, or transaction stops immediately. Deadlines/cancellation must be propagated to the appropriate execution layer.

### 11.6 Do Not Mix Modes to “Compare CPU Numbers”

Each `java HangPatternsLab ...` command starts a new JVM with different PID/thread lifecycles. Do not compare CPU/heap/thread counts across modes as a precise quantitative benchmark; they are **teaching scenarios**. When investigating a real incident, measure on the same service/build/config/workload and over the same window.

## 12. Triage Process for a “No Progress” Incident

### Step 1 — Confirm Target and Symptoms

- Which JVM/process, which pod/container, which build, what was recently deployed?
- Is one request, one queue, one worker pool, or the entire service making no progress?
- What is the operation’s SLO/deadline?
- What **has stopped completing**? Collect completed/failed/accepted per second and oldest in-flight/queue age.
- Are there GC pauses, CPU quota throttling, OOM, DNS/network errors, downstream outages, or resource saturation?

Do not immediately call it a deadlock just because a user says “it hung.” Record **timestamps and workload** before intervening.

### Step 2 — Collect Low-Intrusiveness Evidence

- Existing request/trace IDs, logs, and metrics.
- JVM CPU, GC, heap, native memory, pool size/active/queue, request concurrency.
- Dependency latency and timeout counts.
- Thread dumps at several points. Record the timestamp and collection cost of dumps, since snapshots can add latency.

### Step 3 — Check for a Lock Ownership Cycle

- From stacks/ThreadInfo, find `thread A waiting to lock X`, owner B; follow from owner B onward.
- For object monitors, use `findMonitorDeadlockedThreads()`.
- If the JVM supports ownable synchronizer usage, use `findDeadlockedThreads()`.
- If there is no lock cycle, inspect the dependency graph / logical cycles (executor A waiting on B in the same pool, RPC A → B → A).

**Conclusion:** “No cycle within the detector’s scope was observed at T1/T2” is valid; “there is no deadlock whatsoever” is too strong.

### Step 4 — If There Is Activity Without Progress, Look for Livelock

- Compare retry attempts, CAS conflicts, rollback counts, task completions, and CPU/thread stack changes over the same window.
- Are two actors repeatedly colliding on retries and yielding in lockstep?
- Is there backoff/jitter or just an immediate retry loop?
- Do retries respect deadlines and budgets, or turn a downstream error into a retry storm?

If retries are high yet requests still complete at an acceptable rate, it cannot yet be called livelock. You must define “useful progress” per the business domain.

### Step 5 — If One Group Still Processes While a Victim Is Delayed, Look for Starvation

- Inspect queue oldest age, priority classes, worker busy time, and lock/semaphore acquisition distribution.
- Has the victim not been scheduled yet, or is it inside a worker blocked on downstream?
- Is there unfair lock barging, a priority queue lacking aging, a small pool monopolized by long tasks, or a resource leak?
- Do tasks have a separate deadline for time **spent in the queue**?

Do not confuse intentional queue wait with chronic starvation. Conclude starvation only with evidence that one group is significantly underserved while another group continues progressing.

### Step 6 — If an Operation Waits Long, Follow the Dependency Path

- Is the stack in `Future.get`, socket read, latch, join, DB driver, `Condition.await`, or `BlockingQueue.take`?
- Who is responsible for sending the event / completing the future / releasing the resource?
- Is the dependency alive, does it have timeouts/circuit breakers, and is there a request ID/trace connecting across services?
- Has the caller’s deadline already expired; is cancellation propagated, and could side effects still happen?
- Is a lock being held while waiting on I/O, affecting many other threads?

A **long wait** can be the root cause of **queue starvation**, which in turn leads to a service outage. Distinguish **root cause and consequence** in the timeline.

### Step 7 — Verify and State Conclusion Boundaries

Before declaring it fixed:

- Re-measure under comparable load: completed rate, tail latency, retry rate, wait age, thread states, and dependency latency.
- Verify the lock graph or absence of cycles across multiple samples.
- Run controlled reproduction tests, including concurrency stress and failure injection with deadlines.
- Record before/after data, code/config changes, environment, and sample limitations.
- Do not conclude it is solved merely because the service stopped hanging **after a restart**; a restart clears state and much evidence without proving the root cause.

## 13. Four Real-World Scenarios

### Scenario A — Crossed Locks in Order Processing

**Observation:** two threads repeatedly appear `BLOCKED`; thread A holds the order-cache monitor and waits for inventory-lock, while B holds inventory-lock and waits for order-cache. ThreadMXBean returns both IDs.

**Classification:** consistent with **monitor deadlock**, because there is an ownership and wait cycle.

**Remediation:** enforce a global lock order, do not hold locks while calling downstream, and test both success and error paths. Do not simply increase thread count, as additional threads will just pile up behind the cycle.

### Scenario B — Infinite Optimistic Update Retries

**Observation:** `retries_total` rises by thousands per second while `commits_total` does not increase; stacks frequently sit in CAS/rollback/retry; two workers both reverse their decisions upon seeing a conflict.

**Classification:** **livelock** is a strong hypothesis if parties continually affect one another so no progress is made; you must still check whether downstream is genuinely returning continuous errors.

**Remediation:** jitter/backoff, retry budgets/deadlines, tie-break/priority rules, and the `commits/attempts` metric.

### Scenario C — Batch Work Starved

**Observation:** high-priority tasks are continuously processed; low-priority jobs have sat in the queue for 40 minutes and oldest age keeps climbing; workers are active with no monitor cycle.

**Classification:** consistent with **starvation due to priority policy / lack of fairness**, not deadlock.

**Remediation:** aging, dedicated capacity or weighted fairness, queue deadlines, and per-class metrics instead of looking only at aggregate throughput.

### Scenario D — Client Call Missing a Read Timeout

**Observation:** a worker waits in socket read for 120 seconds while downstream is unresponsive; thread dumps show the same call path, the lock detector finds no cycle, and other requests still complete.

**Classification:** **overdue wait** due to dependency/timeout; insufficient evidence for deadlock or starvation.

**Remediation:** consistent connect/read/overall deadlines, cancellation propagation, circuit breakers with appropriate semantics, and monitoring downstream latency and retries. If blocking workers exhaust slots, this can lead to queue starvation; the cause–effect relationship must be stated clearly.

The scenarios above are **analytical templates**, not logs from a specific system.

## 14. Risk-Reducing Changes and Their Trade-offs

| Measure | Goal | Trade-offs / Limitations |
| --- | --- | --- |
| Lock ordering | Eliminate circular wait from conflicting lock acquisition orders | Requires standardization across all code paths |
| Shrinking critical sections | Reduce contention and hold-and-wait | Must preserve data invariants |
| `tryLock(timeout)` | Bound lock wait time when semantics allow | Can fail and require handling/rollback; does not solve every deadlock |
| Backoff + jitter | Prevent in-phase actor retries leading to livelock/retry storms | Adds latency per retry; requires a budget |
| Fairness/aging | Mitigate starvation | May reduce throughput and increase context switching |
| Pool isolation/bulkheads | Prevent long blockers from occupying all workers | Increases complexity/resource cost |
| Bounded queues & backpressure | Prevent backlog/OOM and expose pressure | Requires an appropriate rejection policy and caller experience |
| Deadlines/timeouts | Prevent an operation from waiting forever | Caller timeout does not guarantee remote task stopped |
| Cancellation/interruption | Provide an exit path for supported waits | Not all operations are interruptible; requires cleanup/idempotency |
| Progress metrics + multiple dumps | Distinguish mechanisms with evidence | Polling/dumps have overhead and sampling bias |

No single setting such as “increase pool from 20 to 200 threads” automatically solves all four categories. If new threads keep waiting on the same dependency, enlarging the pool may only increase memory, context switches, and pressure on downstream.

## 15. Safety Notes for Production Diagnostics

- **Never run an intentional deadlock lab on a real server.** Use a separate JVM in isolated local/staging environments.
- Never call `Thread.stop()` to break a wait cycle; it is a dangerous API that can break invariants and leave data in an inconsistent state.
- Never treat `Thread.interrupt()` as a universal “kill thread” command; it is only a **signal** that APIs/code must cooperate to handle. A thread `BLOCKED` waiting for a monitor in `synchronized` does not simply exit on interrupt.
- Do not automatically invoke `GC.run()`, heap dumps, or restarts before gathering evidence; they can erase traces and worsen the incident.
- Do not collect full thread dumps/JFR at high frequency without accounting for CPU, pauses, output size, and sensitive data.
- Do not share raw stack traces/arguments/hostnames/tokens if logs/traces contain private information; obtain authorization and redact appropriately.
- For containers, verify PID/cgroup/quota/thread caps; a JVM can have too little CPU quota causing slow progress without any lock cycle.
- If thread CPU, blocked time, or lock owner cannot be measured, record “**unknown/unsupported**”; do not turn `-1`/`null` into 0 and draw conclusions.
- When proposing fixes, prioritize impact reduction, preserve diagnostic data before intervening, measure guardrails, and have a rollback plan.

## 16. Common Misinterpretation Mistakes

1. **Seeing `BLOCKED` and declaring deadlock.** It may be brief legitimate contention; you need a cycle, owners, and multiple samples.
2. **Seeing `WAITING` as a bug.** Idle workers normally wait on queues.
3. **Seeing high CPU and concluding livelock.** It could be useful CPU-bound work or GC/JIT.
4. **Seeing low CPU and ruling out livelock.** Backoff/sleep can keep retries from using much CPU.
5. **Seeing rising retries and concluding livelock.** A dependency may be failing or retries may still be completing.
6. **Using thread count in place of progress.** 100 live threads do not prove 100 jobs are doing useful work.
7. **Relying on a single dump.** A snapshot does not show wait duration or history.
8. **Trusting `findDeadlockedThreads()==null` as no deadlock at any layer.** The API is scoped to object monitors/ownable synchronizers.
9. **Failing to check ownable synchronizer support.** You may fail to run the broader detector.
10. **Equating queue delay with starvation.** You need to compare fairness, oldest age, and the victim’s progress.
11. **Not seeing a queued task’s stack and concluding the task vanished.** An unstarted task has no worker call stack of its own.
12. **Ignoring downstream long waits.** One overly long call can occupy a pool and cause secondary queue starvation.
13. **Missing timeouts on `Future.get()`/I/O.** Operations can wait forever even while the process appears healthy.
14. **Assuming `Future.get(timeout)` automatically cancels the task.** Caller timeout does not stop the task.
15. **Using `Thread.stop()` to rescue production.** It can corrupt state/locks and cause severe data errors.
16. **Increasing the thread pool without verifying root cause.** It may amplify resource contention.
17. **Ignoring the lock owner.** Counting `BLOCKED` threads does not reveal the cause; you need the lock graph/owner’s stack.
18. **Looking only at average latency.** Tail latency and oldest queue age can be bad even when the mean looks fine.
19. **Failing to distinguish “slow” from “no progress.”** Multiple timestamps, progress deltas, and deadlines are needed.
20. **Lumping every incident under one label.** A long wait can cause starvation; a deadlock can make queues grow.
21. **Testing only without concurrent load.** A lock-order bug may not reproduce in single-threaded tests.
22. **Not recording timestamps/config/workload when comparing before and after.** There is no basis to conclude a change fixed the issue.
23. **Interpreting `RUNNABLE` as “occupying CPU.”** The thread may be waiting on an OS resource.
24. **Ignoring process/JVM identity in containers.** You may be diagnosing the wrong instance.
25. **Forgetting timeouts/cancellation can have side effects.** A remote action may still complete after the caller gives up.

## 17. Self-Check Questions

1. In one sentence, state the essential difference among deadlock, livelock, starvation, and long wait.
2. A holds lock X and wants Y; B holds Y and wants X. Why is this deadlock rather than starvation?
3. Why can two workers “continually yielding to each other” be a livelock even when CPU is high and threads are not `BLOCKED`?
4. A low-priority job waits 30 minutes while high-priority jobs keep completing. What evidence do you need to call it starvation?
5. `Future.get()` waits 1 minute with no timeout. Can you conclude deadlock yet? Why?
6. A thread pool has 30 `WAITING` workers and no tasks in the queue. Is this an incident?
7. Which lock types distinguish `findMonitorDeadlockedThreads()` from `findDeadlockedThreads()`?
8. Why might a logical dependency cycle of two `Future`s in a single-thread executor not be detected by `ThreadMXBean`?
9. A retry counter increases by 1,000/sec while completed jobs equal 0: what other explanations must be ruled out before concluding livelock?
10. `Future.get(timeout)` throws `TimeoutException`. Does that prove the remote task was canceled?
11. What signals distinguish a legitimate queue delay from prolonged starvation?
12. Why might a `RUNNABLE` thread not be using 100% CPU?
13. In the deadlock lab, why use daemon threads and avoid an unbounded `join()`?
14. Describe 5 metrics to collect when a service fails to complete requests even though the health endpoint returns OK.
15. If an external long wait leads to queue starvation, how should the report separate root cause and consequence?
16. Why are `tryLock(timeout)` and lock ordering different measures that should not be equated?
17. In diagnostics, why can increasing pool size temporarily mask symptoms while making the root cause worse?
18. If `findDeadlockedThreads()` returns `null`, what is the most accurate way to phrase the limitation of that conclusion?

## 18. Diagnostic Report Template

```text
IDENTITY
- Service/build/JDK vendor/version:
- PID/container/pod/node, start time:
- Timestamp/timezone and request workload:

SYMPTOM / PROGRESS
- Which operations stopped completing?
- receivedRate/completedRate/failedRate:
- Retry/attempt rate and useful commit rate:
- Queue depth and oldest queued age:
- InFlight oldest age, latency p95/p99/deadline violations:

THREAD / LOCK EVIDENCE
- Thread dump timestamps and collection overhead:
- Thread names, IDs, state and stack at each sample:
- Waiting lock, current owner and ownership cycles:
- ThreadMXBean monitor/ownable-synchronizer results:
- CPU deltas, contention times and support/enabled flags:

DEPENDENCIES
- DB/HTTP/RPC/file/socket calls and their configured timeout:
- Downstream latency/errors/availability:
- Caller deadline and cancellation propagation:

DIFFERENTIAL DIAGNOSIS
- Deadlock evidence / gaps:
- Livelock evidence / gaps:
- Starvation evidence / gaps:
- Long wait evidence / gaps:
- Primary cause vs secondary symptoms:

CHANGE / VERIFICATION
- Action owner, timestamp, exact code/config change:
- Before/after at comparable load:
- Confirmation test and remaining uncertainty:
- Regression test, rollback criterion and follow-up:
```

A quality report separates “**observed**” from “**hypothesis**.” For example, “workers completed no requests for 20 seconds; three dumps show A/B mutually waiting on monitors; ThreadMXBean returned the matching IDs” is strong evidence for monitor deadlock. “High p99, low CPU, definitely deadlock” is an unsupported conclusion.

## 19. Official References

- Oracle Java SE 17 — `Thread.State`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- Oracle Java SE 17 — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 17 — `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 17 — `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- Oracle Java SE 17 — `Lock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html
- Oracle Java SE 17 — `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Takeaway:** before diagnosing a “hung” Java system, ask **“which work stopped making progress?”**. Then verify whether there is a **wait cycle**, **active retries without completions**, **a victim starved of resources while other work progresses**, or **a call waiting past its deadline**. Multiple timestamped samples, ownership/stack/queue/dependency evidence, and scoped conclusions are required; never use a single thread state or CPU sample to label an entire incident.
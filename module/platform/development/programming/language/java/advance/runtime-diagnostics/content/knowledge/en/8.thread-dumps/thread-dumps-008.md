# 8.8. Distinguishing threads normally waiting for work from threads blocking processing

A Java thread dump can contain dozens or hundreds of threads in `WAITING` or `TIMED_WAITING` while the application still runs smoothly. Executor workers normally **wait for new work**; schedulers wait until the next scheduled run time; consumers wait for a queue to receive data. Yet an already-accepted request may be **waiting for a result that never arrives**, occupying workers or resources so other requests cannot progress. Both situations sometimes display the exact same `WAITING (parking)`.

This lesson in **8. Thread dumps** helps answer: **is the thread waiting for work by design, or is it holding/blocking work that ought to complete?** The answer must combine **thread role, the complete call stack, the wake-up condition, owners/producers, queues, and progress metrics across multiple points in time**, rather than inferring from a single state line.

After this lesson, you will recognize idle stacks like `ThreadPoolExecutor.getTask`, understand in-handler waits like `Future.get()`, distinguish monitor contention from starvation, use `jcmd` and `ThreadMXBean` in a controlled manner, and run a Java 17 example featuring a normally WAITING worker alongside a BLOCKED worker genuinely impeding progress.

## 1. Thread state and business impact are two different axes

In Java 17, `Thread.State` has six values: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`. Four states typically need analysis when investigating a non-progressing service:

| Java state | JVM meaning | Examples | Cannot conclude from state alone |
| --- | --- | --- | --- |
| **RUNNABLE** | Thread is executable in the JVM; may be waiting on OS resources | Java code, native socket read, loop | Not certain it is consuming CPU or doing useful work |
| **BLOCKED** | Waiting to acquire/reenter an **intrinsic monitor** | Another thread holds `synchronized(lock)` | Not automatically a deadlock |
| **WAITING** | Waiting for another thread/event's action, with no timeout on the current call | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Does not mean waiting “forever” or definitely a bug |
| **TIMED_WAITING** | Waiting with a bounded duration | `Thread.sleep`, timed wait/join/park | Does not guarantee the request finishes within SLO |

`NEW` is unstarted, `TERMINATED` is finished; thread dumps of live threads may omit these threads. Java states are not copies of OS thread states.

**Important:** `Thread.State.BLOCKED` specifically means waiting on an intrinsic monitor. A thread waiting on a `ReentrantLock`, `Semaphore`, `Future`, connection pool, or native I/O **does not necessarily** carry state BLOCKED. When we say “a thread is blocking processing”, that is a **system-level conclusion**, not an enum label.

Three mandatory questions:

1. **What role is the thread playing?** Idle worker, request handler, scheduled job, consumer, event-loop, or background helper?
2. **What condition is it waiting on?** Task queue, future completion, monitor, latch, permit, timeout, or network event?
3. **Is that wait slowing down real work?** Are requests exceeding deadlines, backlogs growing, completed tasks stalling, or dependencies unable to run?

A worker idling in `WAITING` for 10 minutes can be healthy if there are no tasks. A request `WAITING` for 30 seconds can be a severe incident when the SLO is 2 seconds.

## 2. Two WAITING sites with different meanings

Lifecycle model of an executor worker:

~~~text
Worker created
      |
      v
Fetch task from work queue
      |
      +-- No task yet: wait in take()/poll()
      |    This is usually normal idle
      |
      +-- Task received: run handler
           |
           +-- Finished processing, increment completed count
           |
           +-- Wait on Future/lock/DB/IO inside task
                If past deadline or no producer exists,
                worker may impede progress
~~~

| Question | Idle worker | Worker potentially blocking processing |
| --- | --- | --- |
| Has it accepted a task? | No, waiting to fetch a new task | Yes, currently inside a handler or transaction |
| Top call path | `ThreadPoolExecutor.getTask` → `BlockingQueue.take` | `OrderService.process` → `Future.get/join` |
| Queue of that exact executor | No backlog, or already being drained | Queue growing / oldest task age increasing |
| Completion counter | Increases when work arrives | Stalled even though work is available |
| Wake-up condition | New task arrives or timer expires | Producer, lock owner, RPC, signal, or permit |
| Impact | SLO/throughput remain healthy | Timeouts, in-flight requests, and p99 rise |

Reading the state while **ignoring the frames underneath** is a common mistake: `LockSupport.park()` only describes how the thread waits, not whether it is waiting for **new work** or **a result to finish current work**.

## 3. Normal work-waiting patterns

### 3.1. `ThreadPoolExecutor.getTask` on an empty queue

With a fixed Java 17 executor, workers commonly wait on the queue for new tasks. **Illustrative** HotSpot stack, which may vary by version:

~~~text
"order-pool-3" #48 ...
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
        at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(...)
        at java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(ThreadPoolExecutor.java:...)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:...)
~~~

Interpretation: the worker is in `getTask`, with **no next task yet**. When this pool's queue is empty, completed tasks keep pace with demand, and request latency is normal, this is healthy idle behavior.

Do not rigidly demand the state be WAITING: with a `ThreadPoolExecutor` using `SynchronousQueue`, `ArrayBlockingQueue`, core-thread timeouts, or `poll(timeout)`, workers may appear in `TIMED_WAITING`/different frames while still being idle.

**In particular:** an empty queue only proves that queue is empty. Work could be stuck at the producer, in an upstream queue, rejected, or routed to the wrong executor. Therefore, always inspect the end-to-end flow.

### 3.2. Scheduler waiting until run time

`ScheduledThreadPoolExecutor` uses a delayed work queue to wait until deadlines. A worker can be in `TIMED_WAITING` in `LockSupport.parkNanos` or `DelayedWorkQueue.take`, or WAITING when no tasks exist.

~~~text
"scheduler-1" ...
   java.lang.Thread.State: TIMED_WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.parkNanos(...)
        at java.util.concurrent.ScheduledThreadPoolExecutor$DelayedWorkQueue.take(...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(...)
~~~

This is an orientation pattern, not fixed stdout. If it is 09:59 and the next job is at 10:00, the scheduler waiting is valid. If at 10:05 the job still has not run, investigate backlog, a worker running a previous job too long, exceptions, shutdown, rejections, or clock skew.

### 3.3. ForkJoin workers and background consumers

- `ForkJoinPool` workers can park when there are no tasks, though internal method names change across JDKs. Check active/running counts, queued submissions/tasks, and work-stealing statistics.
- A consumer in `BlockingQueue.take` when the queue has no events is normal. If the producer stops emitting events, **the bug may be upstream**.
- Network selectors/acceptors can wait for I/O readiness. With native I/O, Java state is sometimes `RUNNABLE`, not WAITING.
- Metrics writers, cleaners, background pollers, and health timers can sleep or wait on schedule; correlate with job deadlines.

Example consumer logic (**illustrative** snippet, omitting imports and `InterruptedException` handling):

~~~java
while (!Thread.currentThread().isInterrupted()) {
    Event event = queue.take();
    handle(event);
}
~~~

When the queue is empty, replacing `take()` with a busy-loop only burns CPU with no new data. If the service lacks events, trace the producer, transport, retries, routing, and message broker.

## 4. Wait patterns that can genuinely block progress

### 4.1. Request handler waiting on a `Future`

**Non-standalone illustrative** logic snippet:

~~~java
CompletableFuture<Result> result =
        CompletableFuture.supplyAsync(this::fetchResult, executor);
return result.join();
~~~

If the task producer has capacity and finishes quickly, waiting may match the architecture. If the producer cannot run, or the request waits past its deadline, the handler holds a slot waiting without making progress.

Illustrative thread dump:

~~~text
"http-worker-7" ...
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(...)
        at java.util.concurrent.CompletableFuture$Signaller.block(...)
        at java.util.concurrent.CompletableFuture.join(...)
        at com.example.CheckoutController.checkout(CheckoutController.java:...)
~~~

Locate the future's producer: which pool was the task submitted to, does that pool have free workers, are callback exceptions or cancellations propagated, and does the downstream call have a deadline? A single `WAITING` dump is insufficient to conclude a bug; you need an event timeline, request age, and completion metrics.

### 4.2. Monitor contention: owner waiting while still holding the lock

Two threads may display:

~~~text
"request-8" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Repository.update(Repository.java:91)
        - waiting to lock <0x00000000AAAABBBB> (a java.lang.Object)

"request-3" ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.Repository.update(Repository.java:80)
        - locked <0x00000000AAAABBBB> (a java.lang.Object)
~~~

Addresses, classes, line numbers, and headers are **illustrative values**. The owner thread is in TIMED_WAITING yet holds the monitor; request-8 is BLOCKED and cannot proceed.

Check for matching monitor IDs in `waiting to lock` and `locked`, the owner's stack, lock hold time, waiter count, and progress across multiple dumps. This is **contention**; if the owner can release, it is not yet a deadlock. Deadlock requires a cyclic wait relationship or an unsatisfiable dependency.

### 4.3. Waiting on a `ReentrantLock` or connection pool can appear as WAITING

A thread waiting on `ReentrantLock.lock()` typically parks inside `AbstractQueuedSynchronizer`, so it can be in `WAITING`. `Semaphore.acquire`, `Condition.await`, `CountDownLatch.await`, acquiring a DB connection, or waiting on an HTTP connection pool can also use park/wait.

Never filter only by `BLOCKED` to find bottlenecks. Inspect the **application** frames beneath `LockSupport.park`, resource owners, and pool metrics: active, idle, pending acquires, timeouts, and queue age. A worker WAITING due to `LinkedBlockingQueue.take` is completely different from WAITING due to `DataSource.getConnection` on an exhausted pool.

### 4.4. RUNNABLE can still block on native I/O

A thread in a native socket/file/DNS/TLS wait can appear `RUNNABLE`, depending on JDK/OS. If that thread is an event-loop thread, a single blocking call can prevent many requests from being processed.

Correlate per-thread CPU:
- RUNNABLE + continuously rising CPU + non-progressing Java loop → suspect CPU-bound work.
- RUNNABLE + low CPU + socket native read + high remote latency → suspect I/O wait.
- WAITING at Future.get + producer queue backlog → suspect dependency/capacity bottleneck.

`Thread.State` does not directly measure CPU usage or SLO impact.

### 4.5. Latches and conditions with nobody waking them

When seeing `Object.wait`, `Condition.await`, `LockSupport.park`, `Thread.join`, or `CountDownLatch.await`, ask:
1. What is the exit condition for the wait?
2. Which thread/producer must call `notify/signal/unpark/countDown/complete`?
3. Is that producer still running/scheduled?
4. Could an exception/cancellation have dropped the signal?
5. Are timeouts, fallbacks, and rollbacks implemented per contract?

`Object.wait()` **releases the monitor of the object on which wait is called** while waiting and must reacquire it to proceed. `Thread.sleep()` and `CountDownLatch.await()` **do not automatically release any held outer monitors**. A WAITING thread can still be the lock owner causing other threads to be BLOCKED.

## 5. Thread-pool starvation: everyone is WAITING, yet not idle

A classic case worth recognizing:

~~~text
Single-thread executor has Worker-1
    |
    Worker-1 picks up OuterTask
    |
    OuterTask submits InnerTask to same executor
    |
    OuterTask calls Future.get() waiting for InnerTask
    |
    InnerTask sits in queue
    |
    Worker-1 is not free to run InnerTask
    |
    Work cannot complete without cancelling/redesigning
~~~

**Read-only** example (non-standalone, risks infinite wait, do not run on a real service):

~~~java
// executor is Executors.newSingleThreadExecutor().
Future<String> outer = executor.submit(() -> {
    Future<String> inner = executor.submit(() -> "done");
    return inner.get();
});
~~~

In a dump, the worker may be `WAITING` at `FutureTask.get`, with pool active=1, queue=1, and completed not increasing. There is no Java monitor `BLOCKED`, and a deadlock detector may return `null` because it does not detect every future/executor dependency.

**This is starvation**: tasks exist, yet the sole worker occupies its slot waiting for a task sitting in the queue. Fix via async continuation/composition, avoiding nested blocking, proper resource isolation, or timeout/cancellation design; arbitrarily increasing pool size merely masks one configuration and does not solve general dependency cycles.

`ThreadMXBean.findDeadlockedThreads()` finds wait cycles on object monitors/ownable synchronizers (when supported), and is not guaranteed to find all Future starvation, remote waits, or business deadlocks.

## 6. Step-by-step thread dump collection and analysis

### 6.1. Pick the right JVM/PID

On HotSpot JDK 17, for example:

~~~bash
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
~~~

`12345` is an **illustrative** PID; substitute the service's verified PID in the right PID namespace. `-l` on `Thread.print` collects additional `java.util.concurrent` lock details when supported; it differs from `jcmd -l` which lists JVMs. `jstack 12345` can also be used on supporting JDKs/OSes.

Thread dumps carry cost proportional to thread count, so capture a few timestamped snapshots **during the symptom**, not endlessly. If attach fails, check user/group permissions, whether the JVM exited, container namespaces, and attach configuration.

### 6.2. Read header, state, and call chain together

~~~text
"pool-4-thread-1" #59 ... tid=0x00007f... nid=0x1a2b waiting on condition
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(...)
        at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(...)
        at java.util.concurrent.LinkedBlockingQueue.take(...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(...)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(...)
~~~

- Thread name hints at the executor, but is not a request ID.
- `#59` in some HotSpot headers is the Java thread ID.
- `tid=0x...` is typically an internal VM thread pointer/ID, not automatically equivalent to Linux TID.
- `nid=0x...` is the native ID in HotSpot, usually hex, requiring the right OS/PID namespace for CPU correlation.
- The `java.lang.Thread.State` line is the snapshot enum; the word “waiting” in the header does not always match the enum.
- Top frames describe the park/monitor primitive, while **frames below** reveal whether it is fetching a new task or waiting inside a handler.

Read stacks bottom-up to find business callers and top-down to find primitives. Never conclude solely because `Unsafe.park` appears.

### 6.3. Inspect owners and wait relationships

Dumps may contain annotations:

~~~text
- waiting to lock <0x0000000011112222> (a java.lang.Object)
- locked <0x0000000011112222> (a java.lang.Object)
- parking to wait for <0x0000000033334444> (...)
~~~

For `synchronized`, find the owner showing `locked` on the same monitor. For `ReentrantLock`/ownable synchronizers, inspect lock info when provided by the tool/runtime. `parking to wait for` may simply be waiting on an empty queue; check the frames underneath. Not all dumps share identical formats or annotations.

### 6.4. Compare multiple snapshots and progress

At T0 (hypothetical):

~~~text
worker-A WAITING at Future.get
worker-B WAITING at queue.take
queue_depth=4; completed_tasks=1000
~~~

Five seconds later:

~~~text
worker-A WAITING at same Future.get
worker-B WAITING at queue.take
queue_depth=27; completed_tasks=1000
~~~

This suggests a thread **is not progressing**, though you cannot blame worker-B if `queue_depth` belongs to another executor. Check task producers, oldest age, request deadlines, and owner stacks. One snapshot is not a video; identical stacks across multiple timestamps + backlog/timeouts establish whether a wait has impact.

## 7. Key metrics to correlate

| Source | Metrics | Purpose |
| --- | --- | --- |
| Executor | `getPoolSize()`, `getActiveCount()` | Know pool size and busy workers (approximate figures) |
| Executor | `getQueue().size()`, oldest task age | Is there a waiting backlog? |
| Executor | `getCompletedTaskCount()`, task rejected count | Are tasks completing; are any rejected? |
| Service | in-flight requests, throughput, timeouts, p95/p99 | Real impact on users |
| Dependency | DB pool active/idle/pending, HTTP latency, remote errors | Waiting on resources/downstream? |
| JVM/OS | thread CPU, GC pauses, RSS, FD count | CPU loop, I/O wait, or runtime pressure |
| Logs/traces | requestId, traceId, event start/end, duration | Which point in the workflow is stalled |

Pool APIs typically return **point-in-time estimates**. `Executors.newSingleThreadExecutor()` returns an `ExecutorService` wrapper and does not guarantee exposing all `ThreadPoolExecutor` getters directly; instrument the executor/framework appropriately.

### `ThreadMXBean` supplements, but does not replace, business progress

`ManagementFactory.getThreadMXBean()` provides `ThreadInfo`, stacks, and synchronization info when supported by the JVM. The following is **illustrative** and requires surrounding imports:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo[] infos = bean.dumpAllThreads(true, true);
for (ThreadInfo info : infos) {
    System.out.printf(
            "name=%s id=%d state=%s lock=%s owner=%s%n",
            info.getThreadName(),
            info.getThreadId(),
            info.getThreadState(),
            info.getLockName(),
            info.getLockOwnerName());
}
~~~

Check `isObjectMonitorUsageSupported()` and `isSynchronizerUsageSupported()` before requesting the corresponding info; dumping incurs overhead. `getBlockedTime()`/`getWaitedTime()` require thread contention monitoring to be enabled/supported, which is usually disabled by default and returns `-1`. Do not enable `setThreadContentionMonitoringEnabled(true)` arbitrarily in production due to overhead. Per-thread CPU time also has its own support/enablement flags.

## 8. Java 17+ Hands-on: normal WAITING vs progress-blocking BLOCKED

This program uses JDK 17+ with no external libraries. It creates two scenarios:
1. `idle-queue-worker` in `newSingleThreadExecutor`: finishes an empty task and enters **WAITING** to fetch a new task from the queue. With no backlog, this is healthy idle behavior.
2. `lock-owner` holds a monitor; `blocked-worker` has work assigned but waits on the monitor, so it is **BLOCKED**. Only when the owner releases the monitor does the work complete.

The main thread waits until each state is genuinely observed before printing, reducing race errors from snapshotting too early. Only main writes to stdout so lines never interleave.

Create file **IdleVsBlockedDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class IdleVsBlockedDemo {
    private static Thread.State awaitState(
            Thread thread, Thread.State expected)
            throws InterruptedException {

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(10);

        while (System.nanoTime() < deadline) {
            if (thread.getState() == expected) {
                return expected;
            }
            Thread.sleep(5L);
        }
        throw new IllegalStateException(
                "State not reached: " + thread.getName()
                + " actual=" + thread.getState());
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Thread> idleWorker = new AtomicReference<>();
        ExecutorService idlePool =
                Executors.newSingleThreadExecutor(task -> {
                    Thread t = new Thread(task, "idle-queue-worker");
                    idleWorker.set(t);
                    return t;
                });

        Object monitor = new Object();
        CountDownLatch ownerHolding = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        CountDownLatch workCompleted = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerHolding.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-owner");

        Thread blockedWorker = new Thread(() -> {
            synchronized (monitor) {
                workCompleted.countDown();
            }
        }, "blocked-worker");

        try {
            idlePool.submit(() -> { }).get(5, TimeUnit.SECONDS);

            owner.start();
            if (!ownerHolding.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Owner did not lock");
            }
            blockedWorker.start();

            Thread.State idle = awaitState(
                    idleWorker.get(), Thread.State.WAITING);
            Thread.State blocked = awaitState(
                    blockedWorker, Thread.State.BLOCKED);

            System.out.println("idle_worker=" + idle);
            System.out.println("blocked_worker=" + blocked);
            System.out.println(
                    "completed_before_release="
                    + (workCompleted.getCount() == 0));

            releaseOwner.countDown();
            if (!workCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Work did not complete");
            }
            System.out.println(
                    "completed_after_release="
                    + (workCompleted.getCount() == 0));
        } finally {
            releaseOwner.countDown();
            owner.interrupt();
            blockedWorker.interrupt();
            idlePool.shutdownNow();
            owner.join(2_000L);
            blockedWorker.join(2_000L);
            idlePool.awaitTermination(2, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac IdleVsBlockedDemo.java
java IdleVsBlockedDemo
~~~

**Exact stdout under normal scheduling conditions:**

~~~text
idle_worker=WAITING
blocked_worker=BLOCKED
completed_before_release=false
completed_after_release=true
~~~

**Line-by-line explanation:**
- The empty task finished; the fixed single-thread executor's worker awaits the next task. `WAITING` at queue `take()` is normal.
- `ownerHolding` ensures the owner entered `synchronized` before the blocked worker starts. The worker awaits the monitor, hence `BLOCKED`.
- Before `releaseOwner.countDown()`, `workCompleted` remains 1; the result is `false`.
- After release, the owner exits the monitor; the blocked worker enters the critical section and counts down; the result becomes `true`.
- `finally` releases, interrupts, and shuts down to avoid leaving stuck workers behind.

**Key point:** `lock-owner` is `WAITING` inside `CountDownLatch.await()`, yet **still holds the outer monitor**, because latch await does not release monitors. Reading the owner's state alone does not reveal its impact on the waiter; you must read owner/waiter lock annotations.

**Limitation:** `Thread.getState()` is a snapshot and can change immediately after reading. A 10-second polling deadline reduces races, though in heavily overloaded environments or where threads cannot be created, `awaitState` may throw `IllegalStateException`; the four lines above are expected output in a normal Java 17 environment.

To try `jcmd` while the demo is waiting, you can add `Thread.sleep(10_000L);` **right after printing `completed_before_release` and before `releaseOwner.countDown()`**, then run from another terminal:

~~~bash
jcmd -l
jcmd 12345 Thread.print -l
~~~

Replace `12345` with the real PID; never hold monitors/sleep like a demo in production.

## 9. Real-world scenario matrix

| Scenario | Signs | Assessment |
| --- | --- | --- |
| Pool of 20 workers `WAITING` in `getTask`, queue 0, normal throughput | No work waiting in that queue | Valid idle, no need to wake them |
| Handler `WAITING` at `CompletableFuture.join`, request past SLO, producer task not yet run | Producer queue grows, completions stalled | Suspect Future dependency/executor starvation |
| Thread `RUNNABLE` in native socket read, low CPU delta, high remote p99 | Slow network call | Suspect I/O wait, do not infer CPU loop |
| Owner `TIMED_WAITING` sleeping yet `locked <0xABCD>`, many waiters `BLOCKED` on same monitor | Lock held too long | Monitor contention; look to shrink critical section |
| Consumer `WAITING` at `queue.take`, queue 0 while upstream errors rise | Producer not emitting events | Valid consumer wait; bug is upstream |
| Pool A idle, Pool B has 300 queued tasks and workers awaiting Future | Two different executors | Analyze the right pool; do not mix metrics |
| Single-thread executor active=1, queue=1, worker `WAITING` at Future.get | Outer waiting on Inner in same pool | Starvation/dependency cycle |
| Scheduler `TIMED_WAITING` before deadline | Task not yet due | Normal; if well past deadline, investigate |

Numbers in the table are illustrative assumptions; verify against real workloads, JDK versions, timestamps, and metrics.

## 10. Common reasoning errors

- **“WAITING means the application is hung.”** Workers waiting for new tasks are usually healthy.
- **“RUNNABLE means high CPU.”** Native I/O and OS waits can appear as RUNNABLE; measure CPU time.
- **“BLOCKED covers every kind of wait.”** Java `BLOCKED` applies only to intrinsic monitors.
- **“An owner in WAITING holds no locks.”** It may be awaiting a latch inside `synchronized`.
- **“Deadlock detector returning null means no starvation.”** Future/queue/external RPC dependencies fall outside many checks.
- **“Many WAITING threads means increase the worker pool.”** During low traffic, that is just spare capacity; adding threads wastes memory and context switches.
- **“Empty queue means all work is done.”** Producers may not have dispatched yet or tasks may sit in another queue.
- **“Large queue proves every WAITING thread is abnormal.”** Verify the queue belongs to that exact executor.
- **“One snapshot suffices to prove no progress.”** Timeline and completion/latency metrics are needed.
- **“Seeing `park` means fix `LockSupport`.”** Park is only a primitive; the bug may be in a handler, future, or producer.
- **“Increasing timeout fixes it.”** Longer timeouts can hold slots longer; fix cancellation and dependency design.
- **“Thread name is request ID.”** Pools reuse threads; use correlation/trace IDs.
- **“All `TIMED_WAITING` are harmless.”** Sleeping while holding a lock or retry storms can impact many threads.
- **“Just call notifyAll to wake them.”** If protocol/condition logic is broken, notify will not fix the root cause.
- **“No completion log means the task never ran.”** Logs may be sampled/dropped; check business state and metrics.

## 11. Production diagnostic playbook

1. **Lock the symptom:** service, pod, PID/start time, Java version, time window, SLO, request timeout, throughput, and error rate.
2. **Collect a few timestamped thread dumps** during the incident; do not spam `jcmd` on an overloaded JVM.
3. **Classify threads by role:** handlers, executor workers, schedulers, selectors, consumers, DB pools, JVM helpers.
4. **Read the full call chain:** `getTask/take` waiting for tasks or `Future.get/join/await` inside a handler? Are there `waiting to lock`, `locked`, or native reads?
5. **Map dependencies:** whose result is the task awaiting, what resource does the owner hold, and can the producer run?
6. **Measure progress:** queue depth/age, active/completed/rejected tasks, in-flight count, p99, connection pools, GC, thread CPU, dependencies.
7. **Compare multiple timestamps:** did states change, did tasks complete, did oldest pending age grow, did trace events continue?
8. **Distinguish problem category:** healthy idle, contention, starvation, true deadlock, I/O wait, hot CPU loop, or producer outage.
9. **Fix the real cause:** avoid blocking event loops, avoid nested Futures on bounded executors, shrink monitor critical sections, handle downstream timeouts/cancellations, control pools/retries.
10. **Re-measure SLO/progress**, never using a drop in WAITING thread count as the sole criterion.
11. **Store evidence safely:** dumps contain classes, paths, and internal details; redact sensitive data and restrict access.

**Quick checklist before concluding a thread is blocking processing:** Has the thread accepted a task or is it waiting for a new task? Which resource is it waiting on and who wakes it? Is there a task backlog on that exact executor? Is the producer/completer still running? Has the request exceeded its deadline? Is there progress across multiple snapshots? Which monitor/connection/permit does the owner hold? Do CPU/JFR/metrics support the hypothesis?

**Key takeaway:** `WAITING` in `ThreadPoolExecutor.getTask` is usually an **idle worker ready for work**, whereas `WAITING` in `Future.get` inside a handler is **accepted work waiting for another result**. Only by inspecting **the full stack, the right queue/resource, the signaler, and business progress** can you distinguish normal waiting from blocked processing.

### References

- Oracle Java 17, `Thread.State`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- Oracle Java 17, `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java 17, `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java 17, `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle JDK 17, `jcmd` (`Thread.print`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

Stack snippets and figures are marked as illustrative; internal methods, states, and thread dump formats may vary by JVM/vendor/OS. During investigations, prioritize actual outputs and timelines.
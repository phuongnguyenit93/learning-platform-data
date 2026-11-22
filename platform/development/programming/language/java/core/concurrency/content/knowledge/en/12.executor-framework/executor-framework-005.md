# corePoolSize, maximumPoolSize, and keepAliveTime in Java ThreadPoolExecutor

## 1. Lesson Objectives

A Java application handling many concurrent tasks usually does not want to create an unbounded `new Thread(...)` for every request. `ThreadPoolExecutor` manages **worker threads**, a **work queue**, and a **task rejection policy** to regulate execution.

The three parameters `corePoolSize`, `maximumPoolSize`, and `keepAliveTime` are fundamental, yet they **cannot be understood in isolation from the queue**. Beginners often think: "core=2, max=10, so when there are 10 requests the pool will run 10 threads." This assumption is **incorrect in many configurations**: with a queue that can accept more tasks, the pool prioritizes **queuing after reaching core**, rather than immediately scaling up to max.

After this lesson, you will be able to:

- Accurately interpret `corePoolSize` (core worker threshold), `maximumPoolSize` (worker ceiling), and `keepAliveTime` (idle time after which an eligible worker may be reclaimed).
- Describe the decision order on `execute(task)`: **create core worker → prioritize queue → add non-core worker when queuing fails → reject when capacity is exhausted**.
- Distinguish **unbounded** queues, **bounded** queues, and `SynchronousQueue` (direct handoff), and understand why they fundamentally change the practical meaning of `maximumPoolSize`.
- Understand **lazy** worker creation, `prestartCoreThread()`, `prestartAllCoreThreads()`, `allowCoreThreadTimeOut(true)`, and configuration constraints.
- Write Java 17+ code to create, observe, and shut down a bounded `ThreadPoolExecutor`; deterministically reproduce queuing, scaling to max, and rejection **without relying on sleep to guess scheduling**.
- Understand the impact on latency, throughput, memory, backpressure, blocking I/O, CPU-bound work, and cancellation.
- Avoid common mistakes such as setting a very large `maximumPoolSize` with an unbounded queue, keeping unnecessary workers alive, ignoring `RejectedExecutionException`, or letting tasks/blocking exhaust the entire pool.

**Scope:** Java SE, `java.util.concurrent`, and the Executor Framework; no external libraries or frameworks required. Examples run on Java 17+.

## 2. Overview of ThreadPoolExecutor Structure

A common constructor:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                          // corePoolSize
        4,                          // maximumPoolSize
        30,                         // keepAliveTime
        TimeUnit.SECONDS,           // unit
        new ArrayBlockingQueue<>(8) // workQueue, up to 8 waiting tasks
);
~~~

This is a **snippet used inside a method**. After finishing with it, call `shutdown()`/`awaitTermination()` appropriately. The constructor itself does not automatically start all 2 core threads if there is no work yet or no prestart has been called.

Visualization:

~~~text
                      ThreadPoolExecutor
                   ┌──────────────────────────┐
execute(task) ────►│ admission / decision     │
                   │                          │
                   │  Running workers         │
                   │  ┌────────────────────┐  │
                   │  │ core (<= 2)        │  │
                   │  │ extra (<= total 4) │  │
                   │  └────────────────────┘  │
                   │                          │
                   │  Work queue (capacity 8) │
                   │  ┌────────────────────┐  │
                   │  │ waiting tasks      │  │
                   │  └────────────────────┘  │
                   │                          │
                   │  Reject if not accepted  │
                   └──────────────────────────┘
~~~

**The total number of threads does not exceed `maximumPoolSize`** per the configuration contract (aside from internal operational details of replacing a dead worker during management; you should not rely on snapshot metrics to assert an absolute instantaneous bound). The task queue and the worker pool are **two separate components**: the queue holds tasks that have not started running yet; a worker holding a task may be running, blocked, or waiting on an external resource.

To properly calculate capacity and latency, you cannot look only at the worker count; you must also consider **task execution time**, queue capacity, task arrival rate, throughput, and the rejection policy.

## 3. corePoolSize: The Core Worker Threshold

`corePoolSize` is the number of workers the executor tries to maintain when there is work, unless the core timeout policy allows them to terminate due to being idle.

Rules:

1. On `execute(task)` when the worker count is **less than `corePoolSize`**, the executor prioritizes creating a new worker to run the task **even if existing workers are currently idle** and the core threshold has not been reached. This is the JDK policy description; on a concrete thread pool, worker states may change concurrently.
2. Core workers are normally created **lazily when tasks are submitted**, meaning calling the constructor does not mean core threads already exist.
3. Once the worker count reaches `corePoolSize`, the executor normally **attempts to queue the task** before creating an additional non-core worker.
4. By default, core workers do not terminate merely from being idle; however, they can be created/replaced on failure, terminated on pool shutdown, or reclaimed when `allowCoreThreadTimeOut(true)` is enabled.
5. `corePoolSize` is not a thread ceiling; the pool can grow up to `maximumPoolSize` if the queue cannot accept the task and conditions allow.

Do not confuse `corePoolSize=2` with "there are always exactly 2 threads from initialization" or "only 2 tasks can ever run." A pool can have 0 workers when newly created, 2 workers under low load, and up to max when the queue is full.

### Prestart: Starting Core Workers Before Requests Arrive

~~~java
executor.prestartCoreThread();     // attempts to start one core thread
executor.prestartAllCoreThreads(); // starts any missing core threads
~~~

`prestartCoreThread()` returns a boolean indicating whether a new worker was created; `prestartAllCoreThreads()` returns the number of additional workers started. This can be useful if you want to reduce worker initialization cost when the first request arrives, or when the queue already has tasks. However, prestarting incurs thread/stack overhead and does not algorithmically make tasks faster.

### Is corePoolSize = 0 Valid?

Yes, `corePoolSize` is allowed to be 0 if the other constructor constraints are met (`maximumPoolSize > 0` and not less than core). In that case, the work admission mechanism and the guarantee of having a worker to process the queue have specific details; you should not infer "the queue has tasks so the pool will never run." For typical use cases, choosing a positive core size makes behavior easier to predict and monitor.

## 4. maximumPoolSize: Worker Ceiling, Not Target Worker Count

`maximumPoolSize` is the **upper limit** on the number of workers the pool can create to serve tasks under appropriate admission conditions. Configuration invariants:

~~~text
0 <= corePoolSize <= maximumPoolSize
maximumPoolSize > 0
~~~

Once the pool has core workers and the queue still accepts tasks, it normally **does not create additional workers** even if max is large. Only when the queue **cannot accept another task** (for example, a bounded queue is full or a direct handoff cannot complete) does the executor try to create additional workers up to the max ceiling.

Therefore:

~~~java
new ThreadPoolExecutor(
        2, 100, 60, TimeUnit.SECONDS,
        new java.util.concurrent.LinkedBlockingQueue<>()
);
~~~

With `LinkedBlockingQueue` constructed without a capacity, the nominal limit is huge (`Integer.MAX_VALUE`). Under normal operation, the queue keeps accepting tasks; the pool usually stays around `core` workers, and `maximumPoolSize=100` **is practically never used to clear the backlog**. The queue can grow large, consuming heap memory and making requests wait a long time.

This is one of the most common configuration mistakes: increasing `maximumPoolSize` while **forgetting queue capacity**.

### When Does maximumPoolSize Actually Take Effect?

For example, `core=2, max=4`, and queue capacity 3:
- The first two tasks are assigned to core workers.
- Subsequent tasks are queued until 3 tasks are waiting.
- If both workers are still busy and the queue is full, the next arriving task can trigger creation of a 3rd and then a 4th worker.
- Once total workers reach 4 and the queue is still full, the next arriving task cannot be accepted under normal policy and must be **rejected** or handled via a `RejectedExecutionHandler`.

Do not turn this order into a guarantee that "task #6 always runs strictly before task #3": scheduling, task completion times, and the moment a worker takes a task from the queue can vary. This is an **admission rule**, not an absolute system-wide completion/FIFO order.

## 5. keepAliveTime: How Long Are Idle Workers Kept?

`keepAliveTime` is the duration an idle worker **not receiving new tasks** may be kept alive before being reclaimed, subject to the pool's conditions.

By default:
- When the pool has **more than `corePoolSize` workers**, workers **above core** may be terminated after being idle longer than `keepAliveTime`.
- Core workers **are not reclaimed merely for being idle**, unless `allowCoreThreadTimeOut(true)` is enabled.
- Keep-alive applies to **the time a worker waits for new work**; it does **not** limit the execution time of a running task.
- If a worker is doing 1 minute of I/O, `keepAliveTime=30s` will not interrupt the task after 30 seconds.
- When a worker finishes a task and picks up another within the timeout, it continues to be reused; the idle timer is not an absolute TTL on the `Thread` object.

Example:

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 5,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(10)
);
~~~

If the pool temporarily has 5 workers, when load drops to 0, the extra workers above core may terminate after being idle for 30 seconds. Under the default policy, the core workers remain alive waiting for new work until shutdown or a configuration change. **Do not assume an exact worker count at the 30,000ms mark** because the OS scheduler and threads executing work or polling the queue do not have millisecond-exact deadlines.

### Enabling Core-Thread Timeout

~~~java
pool.allowCoreThreadTimeOut(true);
~~~

When `true`, **core workers as well** may be reclaimed after the idle time. Requirement: `keepAliveTime` must be **greater than 0**; otherwise, `allowCoreThreadTimeOut(true)` throws `IllegalArgumentException`. Setting this policy **before the pool takes load** is usually clearer and less variable.

Note that `keepAliveTime=0` can be a valid configuration when core timeout is **not** enabled: extra workers are allowed to terminate when there is no waiting work. However, you cannot set `keepAliveTime=0` while core-thread timeout is enabled.

## 6. The Most Important Decision Order: execute and workQueue

The `ThreadPoolExecutor` documentation describes **three interaction rules between worker size and queue**:

1. **If fewer than `corePoolSize` workers are running:** prioritize creating a new worker to run the submitted task, rather than queuing it immediately.
2. **If at least `corePoolSize` workers are running:** prioritize attempting to add the task to `workQueue`, rather than creating another worker.
3. **If the queue cannot accept the task:** try creating a new worker, provided total workers have not reached `maximumPoolSize`; if that also fails, apply the **rejection handler**.

Simplified admission diagram:

~~~text
                   execute(task)
                        |
             workerCount < corePoolSize ?
                 /               \
               yes                no
               |                   |
        create core worker     queue.offer(task)
        to run task              /      \
                             accepted  rejected
                                |          |
                              queued    workerCount < max ?
                                           /       \
                                         yes        no
                                         |           |
                                create extra worker  reject / handler
                                to run task

* In practice, implementation must handle shutdown, races between workers and queue,
  worker creation failures, and workers that have exited.
~~~

This is a **learning model** for the admission flow. The actual implementation re-checks the `RUNNING`/`SHUTDOWN` state after `queue.offer` and manages worker count via CAS; do not rewrite the diagram above as a complete thread-safe implementation.

### State Table with core=2, max=4, queue capacity=3

Assume every worker runs a long task so no task completes during submission:

| New task | Typical behavior | Worker count | Waiting tasks |
|---|---|---:|---:|
| #1 | Create 1st core worker | 1 | 0 |
| #2 | Create 2nd core worker | 2 | 0 |
| #3 | Queue | 2 | 1 |
| #4 | Queue | 2 | 2 |
| #5 | Queue | 2 | 3 |
| #6 | Queue full → create 3rd (extra) worker | 3 | 3 |
| #7 | Queue full → create 4th (extra) worker | 4 | 3 |
| #8 | Workers at max + queue full → reject | 4 | 3 |

These numbers **depend on the assumption that all workers remain busy**. If a worker finishes early, it can pull a task from the queue, freeing capacity and changing the decision for subsequent submissions.

## 7. How the Queue Changes the Meaning of the Three Parameters

### 7.1. Unbounded Queue: Core Dominates, Max Is Rarely Used

~~~java
new java.util.concurrent.LinkedBlockingQueue<Runnable>()
~~~

This queue has a huge nominal limit, so `offer(task)` almost always succeeds. Consequences:
- Once core workers exist, subsequent tasks keep queuing.
- `maximumPoolSize` usually has no effect on worker count under normal conditions.
- Backlog can grow and consume heap when the arrival rate exceeds the processing rate.
- Tail latency can become very high even though the system never throws `RejectedExecutionException`.

`Executors.newFixedThreadPool(n)` uses a practically unbounded queue and a fixed number `n` of workers: suitable when you **already control the submission rate**, but it does not automatically apply backpressure when producers are too fast.

### 7.2. Bounded Queue: Capped Backlog, Max Takes Effect When Full

~~~java
new java.util.concurrent.ArrayBlockingQueue<Runnable>(100)
~~~

The queue limits waiting tasks to 100. Once core workers are running, tasks are queued first. Only when the queue has no room left does the executor try to add workers up to `maximumPoolSize`. Once both sources of capacity are exhausted, the rejection policy takes effect.

A bounded queue helps **cap memory backlog growth**, but you must define how the system reacts to overload. If rejections are swallowed or turned into unbounded retries, load is still not safely regulated.

### 7.3. SynchronousQueue: Direct Handoff, No Backlog Stored in Queue

~~~java
new java.util.concurrent.SynchronousQueue<Runnable>()
~~~

`SynchronousQueue` has no capacity to hold tasks; it only performs a **direct handoff** of a task to a waiting worker. If no worker is ready to receive, `offer` does not store the task to wait, so the executor can create additional workers up to `maximumPoolSize`. When max is reached and no worker can receive, the new task may be rejected.

This configuration makes `max` much more impactful; at the same time, it can rapidly increase thread count under bursty load. You need to choose `max` and the rejection policy carefully. `Executors.newCachedThreadPool()` is implemented using this direct-handoff model with a very large max, so if producers are unbounded, it can create too many platform threads.

### Quick Comparison

| Queue | Characteristics | Effect on core/max/keepAlive | Risk |
|---|---|---|---|
| `LinkedBlockingQueue<>` without capacity | Practically unbounded | Queue takes priority; max rarely takes effect | Backlog/heap growth, tail latency |
| `ArrayBlockingQueue<>(capacity)` | Bounded | Extra workers created up to max only when full | Rejections under overload; needs policy |
| `SynchronousQueue<>` | Stores no backlog | Creates extra workers earlier when handoff fails | Worker explosion if max is too high |
| `LinkedBlockingQueue<>(capacity)` | Bounded linked queue | Similar to bounded queue; different allocation profile | Memory/queue contention cost |

There is no single "best" queue for all workloads. The queue is an **essential part of the sizing decision**; you cannot choose core/max/keepAlive first and ignore the queue.

## 8. Deterministic Java 17+ Example: core → queue → extra → reject

This program uses `CountDownLatch` to keep worker 1 and worker 2 busy. Meanwhile, a queue of capacity 1 holds exactly one task. Submitting a 4th task triggers rejection via `AbortPolicy`.

Save as **ThreadPoolSizingDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ThreadPoolSizingDemo {
    private static void awaitGate(CountDownLatch gate) {
        try {
            gate.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2,
                10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch coreStarted = new CountDownLatch(1);
        CountDownLatch extraStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        boolean rejected = false;
        try {
            // Task 1: creates the core worker and keeps it busy.
            pool.execute(() -> {
                coreStarted.countDown();
                awaitGate(release);
            });
            coreStarted.await();

            // Task 2: core is busy -> goes into the capacity-1 queue.
            pool.execute(() -> { });

            // Task 3: queue is full -> creates the 2nd (extra) worker.
            pool.execute(() -> {
                extraStarted.countDown();
                awaitGate(release);
            });
            extraStarted.await();

            // Task 4: both core and extra are busy, queue is still full -> reject.
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("rejected=" + rejected);
        } finally {
            // Release both workers on all paths.
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        System.out.println("completed=" + pool.getCompletedTaskCount());
    }
}
~~~

Compile and run:

~~~bash
javac ThreadPoolSizingDemo.java
java ThreadPoolSizingDemo
~~~

Output when tasks are not externally interrupted and the executor terminates normally:

~~~text
poolSize=2
queued=1
rejected=true
completed=3
~~~

**Why this is deterministic:**

1. `main` waits on `coreStarted.await()`: task 1 is running on the core worker and cannot finish because `release` is still closed.
2. Task 2 is submitted while the core worker is busy, so it is placed in the capacity-1 queue; no worker has been released to pick it up yet.
3. Task 3 arrives when the queue is full. The pool is below `maximumPoolSize=2`, so it creates a second worker. `main` waits on `extraStarted` to ensure the second worker has started and is waiting on `release`.
4. Task 4 cannot be queued and cannot trigger a third worker, so `AbortPolicy` throws `RejectedExecutionException`; `main` catches it and sets `rejected=true`.
5. Before releasing the latch, the pool has exactly 2 busy workers and 1 waiting task; the `poolSize` and `queued` metrics reflect the controlled state in the example.
6. In `finally`, `main` opens the gate, initiates graceful shutdown, and waits for termination. The three accepted tasks (1, 2, 3) complete; task 4 was rejected and never ran. Thus `completed=3`.

**Practical note:** The latches in this example are **used to stage execution and demonstrate the admission policy**, not as a pattern to put into production pools. In real systems, a task may finish before the next task is submitted, so you should not deduce worker/queue counts from **request sequence numbers**.

### Why Not Use sleep to Force the Queue Full?

`Thread.sleep(100)` only pauses the current thread for a duration; it does not guarantee which tasks have started or remain busy on another machine. `CountDownLatch` establishes explicit ordering, allowing the program to demonstrate sizing policies rather than relying on scheduler luck.

## 9. Control Example: Unbounded Queue Does Not Scale to Maximum

With the default `LinkedBlockingQueue<>`, while the core worker is busy, additional tasks enter the queue instead of triggering extra workers. We can verify this with a short example.

Save as **UnboundedQueueDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 5,
                30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            // Core worker is busy. These two tasks are queued.
            pool.execute(() -> { });
            pool.execute(() -> { });

            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("maximum=" + pool.getMaximumPoolSize());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac UnboundedQueueDemo.java
java UnboundedQueueDemo
~~~

Output under normal conditions:

~~~text
poolSize=1
queued=2
maximum=5
~~~

Even though `maximum=5`, the pool **does not need to create additional** workers as long as the queue can accept tasks. This is why you must inspect `workQueue` before increasing `maximumPoolSize` in an application with a large backlog.

## 10. Example: Configuring keepAliveTime and Core Timeout

The example below illustrates the configuration API without using `sleep` to measure an exact worker count at a scheduler-sensitive moment.

Save as **CoreTimeoutConfigDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CoreTimeoutConfigDemo {
    public static void main(String[] args) {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 15, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(8)
        );

        try {
            pool.allowCoreThreadTimeOut(true);

            System.out.println("core=" + pool.getCorePoolSize());
            System.out.println("max=" + pool.getMaximumPoolSize());
            System.out.println("keepAliveSeconds=" +
                    pool.getKeepAliveTime(TimeUnit.SECONDS));
            System.out.println("coreCanTimeOut=" +
                    pool.allowsCoreThreadTimeOut());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run:

~~~bash
javac CoreTimeoutConfigDemo.java
java CoreTimeoutConfigDemo
~~~

Output:

~~~text
core=2
max=4
keepAliveSeconds=15
coreCanTimeOut=true
~~~

The configuration above does **not** require the pool to have already created two core workers. Because no tasks were submitted and prestart was not called, the worker count may still be 0. `allowCoreThreadTimeOut(true)` only changes **the survival policy of core workers after becoming idle**; it does not command running workers to be canceled.

### When Should You Enable Core Timeout?

It can be useful when:
- Load arrives in widely spaced bursts, each using many platform threads.
- You want to reduce resources during long idle periods and accept the cost of recreating workers when traffic returns.
- You do not need to keep threads warm to minimize startup latency for the next task.

Do not enable it merely to "save threads" while ignoring cold-start or burst latency. Measure your actual workload and consider `ThreadFactory`, initial task work, OS resources, and memory.

## 11. Rejection Policy Is Part of Capacity Design, Not a Minor Detail

If the pool is still running but **the queue can no longer accept tasks** and **the worker count has reached max**, a new task is handled by the `RejectedExecutionHandler`. The executor can also reject tasks after it has been shut down.

Built-in handlers:

| Handler | Typical behavior on rejection | Caveats |
|---|---|---|
| `AbortPolicy` (default) | Throws `RejectedExecutionException` | Caller must explicitly handle overload / failure. |
| `CallerRunsPolicy` | Caller executes the task **on the submitting thread**, if the executor is not shut down | Creates indirect backpressure, but can increase latency and run code on an unexpected thread. If shut down, the task is dropped. |
| `DiscardPolicy` | Drops the task without throwing | Dangerous if the task is required work; causes silent data loss. |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submitting the new task | Can lose older tasks; with priority queues and certain configurations, behavior can be especially hazardous. Watch shutdown and retry behavior. |

No handler by itself guarantees "exactly once" processing for business requests. If a task represents an order, transaction, or work that must be durably persisted, you need a reliable ingestion and queuing path at the appropriate system layer. Within a single JVM, a rejected task that was never accepted/committed must not be logged as succeeded.

### How Does CallerRunsPolicy Provide Backpressure?

When the pool is overloaded, the submitting thread must **execute the task directly**, preventing it from submitting further tasks rapidly. This can help balance producer/consumer rates. However, if the submitting thread is an event loop or a latency-sensitive thread, running the task there will **block the main processing path**. Do not use `CallerRunsPolicy` out of habit without verifying whether the caller thread is allowed to run that work.

### AbortPolicy Is a Transparent Choice

An application can catch `RejectedExecutionException` and return "overloaded / try again later" or route the work elsewhere. Do not retry in an unbounded loop on the submitting thread: immediate retries add contention and do not relieve system pressure.

## 12. keepAliveTime Is Not a Task Timeout

These are distinct time limits serving completely different purposes:

| Configuration / API | What is limited? | Does it cancel a running task? |
|---|---|---|
| `keepAliveTime` | Time an **idle** worker can wait for a new task before being reclaimed per policy | **No** |
| `Future.get(timeout, unit)` | Time the **caller waits for a result** | **No** (does not cancel the task) |
| `Future.cancel(true)` | Requests Future cancellation and attempts to interrupt the worker if applicable | **Best-effort** only; requires cooperative task |
| I/O API timeout | Wait time for the **corresponding I/O operation** | Depends on the API/resource |
| `awaitTermination(timeout, unit)` | Time to wait for the **executor to terminate** | Does not forcibly kill workers |

For example, a task holding a worker while waiting 90 seconds on the network will not be forcibly stopped midway by `keepAliveTime=10s`. Because the task is **not idle**, the keep-alive timer does not address long-running tasks.

If you need a business deadline, design timeouts where the task blocks, along with proper cancellation and cleanup. Do not adjust `keepAliveTime` as a substitute for request timeout management.

## 13. corePoolSize and CPU-Bound vs. Blocking Workloads

### CPU-Bound Work

Tasks that continuously use CPU:
- Do not open far more platform worker threads than CPU capacity just to increase "thread count."
- When runnable threads greatly outnumber CPU cores, context-switching overhead can rise and throughput does not necessarily improve.
- A pool close to the number of available CPU cores is a **starting point for benchmarking**, not a rigid formula.
- A bounded queue can help keep memory stable when task arrival outpaces computation speed.

Example:

~~~java
int cores = Runtime.getRuntime().availableProcessors();
int workers = Math.max(1, cores);
~~~

This is an illustrative snippet; `availableProcessors()` depends on the environment/container and does not know your actual workload. Sizing should account for CPU quota, parallelism of other modules, GC, contention, and latency requirements.

### Blocking I/O Workload

If workers spend more time **waiting on I/O** than computing, having more workers than CPU cores can sometimes improve concurrency:
- However, each platform thread still carries stack, scheduler, and resource overhead.
- Too many workers can overload connection pools, disks, remote services, or memory.
- For blocking I/O, limiting **downstream resource concurrency** and queue capacity is often just as important as thread count.
- Measure active threads, queue depth, I/O duration, rejections, external service saturation, and tail latency.

In Java 21+, **virtual threads** offer a different model for many blocking tasks: `Executors.newVirtualThreadPerTaskExecutor()` creates a virtual thread per task instead of maintaining a fixed pool of platform workers. However, that is **not** a mechanism for throttling connection pool sizes or external resource quotas. When you need to limit concurrent requests, use a semaphore, bounded work admission, or an appropriate quota. `corePoolSize`/`maximumPoolSize`/`keepAliveTime` remain the direct parameters of `ThreadPoolExecutor` for pooled workers.

## 14. Observing the Pool: Configuration Values vs. Point-in-Time Metrics

Commonly used APIs:

~~~java
pool.getCorePoolSize();
pool.getMaximumPoolSize();
pool.getKeepAliveTime(TimeUnit.SECONDS);
pool.getPoolSize();
pool.getActiveCount();
pool.getQueue().size();
pool.getCompletedTaskCount();
pool.getLargestPoolSize();
pool.getTaskCount();
~~~

These values fall into two groups:

**Configuration settings:** `corePoolSize`, `maximumPoolSize`, `keepAliveTime`, queue type, core timeout policy, `RejectedExecutionHandler`.

**Dynamic metrics:** `poolSize` (current workers), `activeCount` (approximate workers executing tasks), `completedTaskCount` (approximate completed tasks), `taskCount` (approximate total tasks), `queue.size()` (waiting tasks at the time of observation).

**Do not treat these statistical APIs as a transactional atomic snapshot.** The pool operates continuously; between reading `activeCount` and `queue.size()`, tasks may complete or be submitted. `ThreadPoolExecutor` metrics provide data for monitoring and tuning, not synchronization primitives for admission logic.

Some diagnostic patterns:

| Symptom | What to check | Likely cause |
|---|---|---|
| Long queue, workers not scaling to max | Unbounded queue or queue still has space | Executor prioritizes queue after core |
| `activeCount` stays near `poolSize`, queue grows | Slow tasks, downstream blocking, high arrival rate | Measure service time, workload, and bounded capacity |
| Pool scales to max then rejects heavily | Load exceeds capacity | Admission/backpressure, timeouts, rate limiting |
| Pool drops back to core after idle period | Non-core workers reclaimed via keepAlive | Normal policy behavior |
| Pool drops to 0 after idle despite `core > 0` | Is core-thread timeout enabled? | Check `allowsCoreThreadTimeOut()` |
| Very high latency with few rejections | Unbounded queue backlog | Increasing max will not help if queue keeps accepting |
| "Disappearing tasks" when full | `DiscardPolicy`/`DiscardOldest`/dropped on shutdown in `CallerRuns` | Check handler and track accepted/rejected counts |

## 15. Modifying Configuration While the Pool Is Running

`ThreadPoolExecutor` provides setters:

~~~java
pool.setCorePoolSize(newCore);
pool.setMaximumPoolSize(newMax);
pool.setKeepAliveTime(20, TimeUnit.SECONDS);
pool.allowCoreThreadTimeOut(true);
~~~

This snippet illustrates calls inside a method that has `pool` and configuration variables. These setters can be called while the pool is active, but **they do not update all workers atomically in a transactional manner**. Workers may be added or reclaimed when idle or when work is waiting according to policy.

### Configuration Constraints

- `corePoolSize` must be >= 0.
- `maximumPoolSize` must be > 0 and >= `corePoolSize`.
- `keepAliveTime` must be >= 0; if core timeout is enabled, `keepAliveTime` cannot be set to 0.
- `allowCoreThreadTimeOut(true)` requires `keepAliveTime` > 0.
- Changing values across multiple setters must respect the invariants **at every step**.

For example, if currently `core=4, max=8` and you want to change to `core=10, max=12`, you cannot call `setCorePoolSize(10)` **before** raising maximum to at least 10. Conversely, when lowering max below the current core, lower core first. If multiple threads configure the executor concurrently, use a clear coordination protocol to avoid invalid intermediate states.

### Do Not Rely on Tuning to Fix Correctness Bugs

Adjusting core/max/queue only affects scheduling and work limits. It **does not make a shared `counter++` atomic**, does not fix races inside tasks, does not make mutable state thread-safe, and does not reduce external transaction complexity. Task logic still needs proper synchronization and ownership.

## 16. Proper Shutdown and Worker Lifecycle

A pool must have its lifecycle managed to avoid thread leaks or preventing the JVM from exiting.

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(50)
);

try {
    pool.execute(() -> System.out.println("work"));
} finally {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Some tasks did not terminate");
            }
        }
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

This is a valid Java method snippet. `shutdown()` stops accepting new tasks while continuing to process already-accepted tasks according to policy. `shutdownNow()` makes a **best-effort attempt** to stop running workers (typically via interrupt) and returns the unstarted tasks drained from the queue; it does not guarantee that arbitrary tasks terminate immediately.

When a task is blocked on a non-interruptible API, `shutdownNow` may not unblock it. You need timeouts, resource closing, or cancellation hooks per the task's contract. Do not confuse `keepAliveTime` with shutdown wait time, nor `awaitTermination` timeout with a forcible kill command.

### Task Responsibilities

- Respond appropriately to `InterruptedException`; do not swallow interrupts and keep running indefinitely.
- Clean up in `finally` / `try-with-resources`.
- Keep shared state consistent if canceled.
- Avoid holding locks across long blocking operations unnecessarily.
- Avoid spawning subtasks in the same small pool where parent tasks wait on child tasks and no free workers remain (thread-starvation deadlock).

## 17. Common Pitfall: Task Waiting on Another Future in the Same Pool

Example:
- A pool has `core=max=1`, a single worker.
- Task A runs on that worker and submits task B to **the same pool**.
- Task A calls `futureB.get()`, waiting for B to finish.
- B sits in the queue, but the only worker is held by A waiting for B.

Without another worker to execute B, the application can **hang**. Increasing `maximumPoolSize` will not save it if an unbounded queue accepts B and the executor never creates another worker. This is a classic example of queue semantics affecting liveness, not just throughput.

Solutions to consider:
- Avoid synchronously waiting on child tasks within the same fixed-size pool.
- Design asynchronous composition or separate pools with clear responsibilities.
- Size capacity/queues to match the dependency model, without relying on "a large max is enough."
- If blocking to wait for results is necessary, ensure the pool can make progress without circular wait dependencies.

## 18. Is There a Fixed Formula for Optimal Configuration?

There is no single optimal `(core, max, keepAlive)` triple for every workload. Consider:

1. **Task duration:** CPU time vs. wait time.
2. **Arrival rate:** tasks per second, burstiness.
3. **SLO:** p95/p99 latency and acceptable error/rejection rate.
4. **Queue budget:** memory for backlog, maximum delay before a task starts.
5. **Downstream limits:** DB connections, remote API quotas, file handles.
6. **CPU/GC:** actual cores, heap, thread stacks, allocation rate.
7. **Timeout/cancellation:** are expired requests canceled from the queue or do they still occupy memory?
8. **Rejection handling:** can the system tolerate dropping or retrying tasks?
9. **Load variation:** steady traffic or bursts—keep workers warm or reclaim quickly?
10. **Observability:** queue length, `activeCount`, task service time, completed count, timeouts/rejections, and tail latency.

A responsible approach:
- Define the maximum number of tasks allowed to **run concurrently** and the maximum allowed to **wait**.
- Choose a bounded queue and rejection/backpressure aligned with business semantics.
- Start with core/max suited to the workload; measure real traffic or representative load tests.
- Tune `keepAliveTime` based on burst spacing and worker startup cost; do not use keep-alive to control task runtime.
- Test shutdown and overload behavior, not just moderate-load scenarios.

## 19. Common Mistakes and How to Fix Them

**Mistake 1 — "max=50 so the pool will create 50 workers when 50 tasks arrive."** Not if the queue keeps accepting tasks. After core, the queue takes priority.

**Mistake 2 — Using an unbounded queue and being surprised that `poolSize` stays near core.** That is a direct consequence of the admission policy. Use a bounded queue or another queue type if you need max to take effect under your workload's contract.

**Mistake 3 — Using `keepAliveTime` to limit how long a task runs.** Wrong. Keep-alive is an idle-worker policy; task timeouts must be handled separately.

**Mistake 4 — Assuming `corePoolSize` workers are created immediately in the constructor.** Core workers are lazily created by default; use prestart if needed.

**Mistake 5 — Setting `keepAlive=0` and then enabling `allowCoreThreadTimeOut(true)`.** Invalid; `keepAlive > 0` is required for core timeout.

**Mistake 6 — Choosing a huge `max` with `SynchronousQueue` and assuming the pool protects resources.** The pool can create too many threads and overload the system. Apply real bounds.

**Mistake 7 — Using `AbortPolicy` without catching `RejectedExecutionException`.** Tasks may be rejected; the caller must handle and report the outcome.

**Mistake 8 — Using `DiscardPolicy` for required work.** Risks silent task loss. Use a protocol that prevents data loss where required.

**Mistake 9 — Using `CallerRunsPolicy` without checking the caller context.** The caller may run a blocking task and degrade request or event-loop latency.

**Mistake 10 — Using an unbounded queue to "avoid rejections."** Often just turns overload into memory pressure and long latency.

**Mistake 11 — Forgetting to shut down the pool.** Workers can hold resources and keep the JVM alive; establish clear ownership.

**Mistake 12 — Assuming `shutdownNow` kills every task.** It attempts interruption, but tasks must cooperate. Plan for cleanup, `awaitTermination`, and deadlines.

**Mistake 13 — Increasing `max` to fix thread-starvation deadlock while the queue is still unbounded.** The queue still absorbs child tasks while the parent worker waits; fix the dependency model.

**Mistake 14 — Treating `activeCount`/`queueSize` as an immutable snapshot.** Metrics change continuously; use them for monitoring, not check-then-act correctness.

**Mistake 15 — Changing core/max in an order that temporarily makes `core > max`.** Setters validate invariants; plan the update order accordingly.

**Mistake 16 — Using the same parameters for CPU-bound and I/O-bound workloads.** Blocking behavior and downstream resources dictate different choices.

**Mistake 17 — Using a thread pool to hide race conditions in tasks.** An executor schedules execution; it does not synchronize mutable state shared by tasks.

**Mistake 18 — Confusing queue size with total active tasks.** The queue only holds tasks **not yet running**; active workers are executing tasks outside the queue.

## 20. Checklist for Reviewing a ThreadPoolExecutor

- Are `corePoolSize`, `maximumPoolSize`, `keepAliveTime`, and `TimeUnit` clearly defined?
- Do you know the `BlockingQueue` type and its **actual capacity**?
- Do you understand **core → queue → extra → reject** under expected load?
- With an unbounded queue, do you recognize that `maximumPoolSize` usually does not help with backlog?
- With a bounded queue, is behavior defined when the queue is full and workers reach max?
- Is a rejection policy defined to avoid silent task loss?
- Is `allowCoreThreadTimeOut` enabled, and if so, is `keepAlive > 0`?
- Do you need to prestart core workers, or is lazy startup acceptable?
- Are workers CPU-bound, blocking I/O, or mixed? Are downstream concurrency limits in place?
- Do parent tasks wait on child tasks in the same pool? Is there a starvation-deadlock risk?
- Are there separate timeout/cancellation policies for tasks rather than misusing keep-alive?
- Are metrics collected for active workers, queue depth, rejections, task duration, and tail latency?
- Are `shutdown`, `awaitTermination`, `shutdownNow`, and cleanup safely designed?
- Have both burst and overload scenarios been load-tested, not just the happy path?

## 21. Practice Questions and Answers

**Q1.** A pool has `core=2, max=16`, and a default `LinkedBlockingQueue<>`. After two workers exist, 100 long tasks are submitted. Will the pool automatically scale to 16 workers?

**Answer:** Normally no. The queue keeps accepting tasks, so the executor prioritizes the queue after core. `maximumPoolSize` has very little effect if the queue almost never fills.

**Q2.** A pool has `core=2, max=4`, and a bounded queue with `capacity=3`. Two workers are busy, the queue has 3 tasks, and 1 more task arrives. What happens?

**Answer:** The executor can create a 3rd worker to run the incoming task, because the queue cannot accept another task and total workers are still below max.

**Q3.** If the pool already has 4 busy workers and the capacity-3 queue is full, what happens when a new task arrives?

**Answer:** The executor applies `RejectedExecutionHandler`, or throws `RejectedExecutionException` if using `AbortPolicy`.

**Q4.** `keepAlive=5` seconds, and a task runs for 30 seconds. Will the task be automatically interrupted at the 5-second mark?

**Answer:** No. Keep-alive applies to how long a worker is **idle**, not how long a running task can execute.

**Q5.** `core=3`, the constructor finishes, and no tasks have been submitted yet. Is `poolSize` guaranteed to be 3?

**Answer:** No. Workers are created lazily; `poolSize` can be 0 if prestart has not been called.

**Q6.** Can you enable `allowCoreThreadTimeOut(true)` when `keepAliveTime=0`?

**Answer:** No. The API requires `keepAliveTime > 0` for core-thread timeout.

**Q7.** Why can `CallerRunsPolicy` provide backpressure while being dangerous for an event-loop thread?

**Answer:** When the pool is overloaded, the caller runs the task directly, slowing down its submission rate; however, an event-loop thread becomes occupied by the task, hurting latency and its ability to serve other events.

**Q8.** Does a `Future.get(100, MILLISECONDS)` timeout cause the worker pool to reclaim the thread or cancel the task immediately?

**Answer:** No. It is only the caller's wait timeout on the `Future`, independent of keep-alive/worker lifecycle and cancellation.

**Q9.** If using `SynchronousQueue`, can the queue hold 100 waiting tasks?

**Answer:** No. It is a direct-handoff queue that stores no backlog; when handoff fails, the pool may scale workers up to max or reject depending on configuration.

**Q10.** A pool has one worker running task A; A submits B to the same pool and calls `Future.get()`, while B waits in the queue. What is the risk?

**Answer:** Thread-starvation deadlock: the sole worker waits for B, while B has no worker to run on. You must change the dependency design or adjust capacity/admission appropriately.

## 22. Official References

- **ThreadPoolExecutor — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **ExecutorService — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **BlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- **ArrayBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **LinkedBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- **SynchronousQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- **ThreadPoolExecutor.RejectedExecutionHandler — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html
- **TimeUnit — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html

**Conclusion:** The three parameters **`corePoolSize`**, **`maximumPoolSize`**, and **`keepAliveTime`** only make sense alongside **`workQueue`** and the **rejection policy**. The pool normally creates workers up to core, then queues tasks, scales up to max only when the queue cannot accept more, and finally rejects when both workers and queue are at capacity. Keep-alive reclaims **idle workers**, not long-running tasks. Proper configuration must simultaneously protect **throughput, latency, memory, external resources, and overload behavior**.

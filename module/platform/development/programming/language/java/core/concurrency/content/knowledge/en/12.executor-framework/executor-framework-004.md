# Assessing the Risks of Unbounded Queues in the Java Executor Framework

> **Thesis:** An executor with finite workers that accepts nearly all tasks into an unbounded queue **does not automatically scale processing capacity**. When the arrival rate exceeds the completion rate, the backlog grows, tasks retain more memory, wait times increase, requests may miss their deadlines, and ultimately the JVM can encounter `OutOfMemoryError`. A large queue also masks overload because `submit()` can still return quickly. **Capacity, throughput, memory, latency, rejection, cancellation, and shutdown** must be evaluated as a single system.

This article belongs to the **Executor Framework** section of **general Java concurrency**. The examples use Java SE 17+ (`ThreadPoolExecutor`, `Executors`, `BlockingQueue`, `Future`); Spring is not used.

## 1. What is an unbounded queue?

A queue is called *unbounded* when the application does not set a sufficiently small finite capacity to control the workload. For example, `new LinkedBlockingQueue<>()` has a default capacity of `Integer.MAX_VALUE`: technically it has an element count limit, but the heap usually runs out before reaching this limit. Therefore, **unbounded does not mean the JVM has infinite resources**.

Basic model:

~~~text
Producer threads
       |
       | execute(task) / submit(task)
       v
[ Waiting task queue ] ---> worker-1 ---> complete
                         -> worker-2 ---> complete
                         -> worker-N ---> complete

If task arrivals > task completions over a sustained period:
     queue grows -> longer wait -> heap retention -> increased GC/timeouts
~~~

A successful `execute` or `submit` means the task **has been accepted by the executor under its contract**, not that it has started, completed successfully, or returned a result within the deadline. Some tasks may even sit in the queue until the pool shuts down, is cancelled, or preceding tasks finish.

### An unbounded queue is not an unbounded thread pool

| Design | Primary behavior | Risk under overload |
| --- | --- | --- |
| `Executors.newFixedThreadPool(n)` | Fixed number of workers, unbounded work queue | Growing backlog and heap, prolonged latency |
| `Executors.newSingleThreadExecutor()` | Single worker, unbounded queue, sequential processing | Head-of-line blocking, very long wait times |
| `Executors.newCachedThreadPool()` | Uses `SynchronousQueue` for handoff; can create many workers | Explosion of thread count and native/CPU resources |
| `ThreadPoolExecutor` with `ArrayBlockingQueue(cap)` | Bounded queue, min/max workers | Requires explicit rejection/backpressure handling |
| `ScheduledThreadPoolExecutor` | Scheduled/delayed task queue with its own contract | Retention of scheduled/cancelled tasks, time-based backlog |
| `ForkJoinPool` | Work-stealing and its own mechanism | Do not assume `ThreadPoolExecutor` worker-scaling rules apply to it |

Do not see the word “Executor” and assume every implementation uses the same type of queue.

## 2. Which factory methods easily lead to a backlog?

~~~java
// API snippet, not a standalone program.
ExecutorService fixed = Executors.newFixedThreadPool(8);
ExecutorService single = Executors.newSingleThreadExecutor();
~~~

`newFixedThreadPool(8)` provides up to 8 reusable workers and a **shared unbounded queue** for waiting tasks. `newSingleThreadExecutor` has one worker and an unbounded queue. They are convenient for small examples or certain input-bounded workloads, but they **do not provide automatic backpressure** before the heap hits its limit.

A misleading configuration:

~~~java
// Snippet illustrating ThreadPoolExecutor configuration.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        4, 16, 60L, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>()
);
~~~

Developers set `maximumPoolSize=16` expecting that when load increases, the pool will create up to 16 workers. In practice, `ThreadPoolExecutor`'s strategy is typically:

1. When the worker count has not reached `corePoolSize`, attempt to create a core worker for the task.
2. Once core is reached, prefer `workQueue.offer(task)` if the queue can accept it.
3. Only when the task cannot be queued does it consider creating a non-core worker up to `maximumPoolSize`.
4. If it still cannot accept the task, apply `RejectedExecutionHandler`.

With `LinkedBlockingQueue<>()` having a huge capacity, step 2 usually succeeds, so workers typically stay near **core=4** while new tasks lengthen the queue. One should not call `maximumPoolSize` completely useless in every context; it is simply **rarely triggered because of the queue choice**.

### Capacity is part of the pool algorithm

~~~text
new task
    |
    v
workerCount < corePoolSize ?
    | yes -> create core worker if possible
    | no
    v
Is Executor still RUNNING and queue.offer(task) succeeds?
    | yes -> queue to wait for a worker
    | no
    v
Try creating an additional worker up to maximumPoolSize
    | success -> run task
    | failure -> rejection policy
~~~

This is the general decision model; the implementation also re-checks the executor state after enqueuing to handle races with shutdown. Even so, it is enough to explain **why an unbounded queue makes `maximumPoolSize` hard to take effect**.

## 3. Risk 1 — arrival rate exceeds processing rate

Let:

- `λ`: average number of tasks submitted/accepted per second.
- `μ`: average number of tasks the pool completes per second at the load under consideration.
- `Q`: number of waiting tasks.

If `λ > μ` over a sustained period, the backlog will grow by the difference, unless there is cancellation, deduplication, rate limiting, or a workload change. If `λ < μ` after a burst, the pool can drain the queue, though tasks still had to wait beforehand.

Example: 1,000 tasks arrive per second, and the pool can process 800 tasks per second. The backlog grows by about **200 tasks/second** while this condition holds. After ten minutes, roughly **120,000 tasks** may accumulate, before accounting for retries and load changes.

This is only an illustrative calculation, not a rigid predictive formula for workloads with bursts, varying task durations, GC pauses, and downstream saturation. However, it reflects a fundamental limit: a queue **stores work rather than processing additional work itself**.

### Why might overload not show up in admission metrics?

When a queue accepts tasks quickly, `execute()` does not block. An API handler can return “accepted” in a few microseconds while the actual task has to wait a long time before a worker starts it.

Measure separately:

| Metric | Question |
| --- | --- |
| Accepted/sec | How many tasks were accepted? |
| Completed/sec | How many tasks actually completed? |
| Rejected/sec | How many tasks were rejected? |
| Queue length / slope | Is the backlog draining after a burst or growing steadily? |
| Queue waiting time | How long does a task wait from submit to start? |
| Task execution time | Once started, how long does a task take? |
| Failure/cancel/timeout | Is the task still valuable or has it already failed? |

Looking only at **accepted** or “submit did not throw” is not enough to assess executor health.

## 4. Risk 2 — tasks retain memory and cause GC pressure

The queue holds `Runnable` or `FutureTask` instances; a task can retain references to:

- Request payloads, `byte[]`, JSON trees, buffers, and parsed objects.
- Lambdas capturing `this`, context, collections, or business data.
- `Callable` and `Future` result/exception structures.
- Large object graphs that should only be short-lived if tasks were processed immediately.
- Data from requests that already timed out at the caller while the task still sits in the queue.

As long as the executor is alive, it holds the queue; the queue holds the tasks; the tasks hold objects reachable along that reference chain. The garbage collector **cannot reclaim** objects that remain reachable just because the client is no longer waiting for the result.

Consequences:

1. Used heap grows with the backlog, especially the retained heap of captured objects.
2. GC frequency or pause times can increase, reducing effective processing capacity.
3. Reduced capacity further increases the backlog — a vicious feedback loop.
4. The JVM can hit `OutOfMemoryError: Java heap space` before the queue reaches its theoretical capacity.
5. An outage can arrive delayed: the queue has been accumulating data for a long time and only manifests during the next load spike.

**Do not multiply the entry count by an assumed lambda size** to conclude memory is safe. A tiny lambda can retain a huge object graph. Use a heap profiler/dump and real task data to estimate retained bytes per queued task.

`LinkedBlockingQueue`'s default capacity of `Integer.MAX_VALUE` is an **element count** limit, not a memory limit for the application.

## 5. Risk 3 — end-to-end latency increases

A task with a 10 ms execution time that waits 5 s in the queue will have multi-second latency. Approximately:

~~~text
Total time = queue waiting time + running time + scheduling/other overhead
~~~

If a task must finish within 300 ms, a queue holding thousands of tasks may already make the SLA **unachievable before the task even starts**.

By Little's Law in steady state under appropriate assumptions: `L = λ × W`, where `L` is the average number of items in the system, `λ` is the compatible throughput/arrival rate, and `W` is the average time spent in the system. When examining the queue alone, you must use the corresponding **queue length** and **queue waiting time**, without mixing them with active tasks. When the backlog is growing indefinitely, the system is not in steady state, so simple long-term results cannot be derived from that formula.

### Head-of-line blocking

In a FIFO queue, a slow or blocking task occupying a worker can make subsequent tasks wait a very long time:

~~~text
worker-1: blocking remote call ...
worker-2: blocking remote call ...
queue:    [fast1, fast2, fast3, ...]
~~~

Adding queue capacity does not make the two workers block any less. You need to find the root cause reducing the service rate: I/O without timeouts, locks, overloaded downstream DB/API, a shared pool for overly different tasks, or a dependency cycle.

### Thread-pool starvation deadlock

A task in a single-thread executor that submits another task **to the same pool** and waits on `Future.get()` can deadlock itself: the sole worker is occupied by the outer task, and the queued task has no worker to run it.

~~~java
// Illustrative anti-pattern; do not run directly as it can hang.
ExecutorService pool = Executors.newSingleThreadExecutor();

pool.submit(() -> {
    Future<Integer> nested = pool.submit(() -> 42);
    return nested.get(); // Worker waits for a task the pool cannot run yet.
});
~~~

This is a dependency deadlock, not unique to unbounded queues. However, the queue allows accepting more tasks that cannot make progress, masking the stall.

## 6. Example 1 — queue grows despite a large maximumPoolSize

This example is **coordinated with latches**, without allocating millions of objects to deliberately trigger an OOM. One worker is forced to wait; 5 subsequent tasks are enqueued; even though `maximumPoolSize` is 4, the executor still has only one worker because the queue accepts the tasks.

Create `UnboundedQueueDemo.java`, Java 17+:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 4, 60L, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>());

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

            for (int i = 0; i < 5; i++) {
                pool.execute(() -> {});
            }

            System.out.println("max = " + pool.getMaximumPoolSize());
            System.out.println("workers = " + pool.getPoolSize());
            System.out.println("queued = " + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
        System.out.println("completed = " + pool.getCompletedTaskCount());
    }
}
~~~

Run:

~~~bash
javac UnboundedQueueDemo.java
java UnboundedQueueDemo
~~~

Normal stdout:

~~~text
max = 4
workers = 1
queued = 5
completed = 6
~~~

`started.await()` confirms the worker is running and blocked at `release.await()`. The next five tasks are accepted by the queue; the pool does not scale workers above core because the queue still has room. `release.countDown()` lets the worker finish and then run all accepted tasks; `awaitTermination()` waits before printing the completed count.

Simply increasing `maximumPoolSize` does not solve a backlog when using an unbounded queue.

## 7. Bounded queues and admission conditions

A common approach is to use `ArrayBlockingQueue` or `LinkedBlockingQueue` with an explicitly set capacity:

~~~java
// Configuration snippet; not a standalone program.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4,
        30L, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

When the queue is full and the pool has not reached max, the executor can create additional workers. When the queue cannot accept the task and no more workers can be spawned, **the task is rejected** according to `RejectedExecutionHandler`.

**Capacity=100 is only an example**, not a universal standard. The capacity must depend on retained task size, heap budget, throughput, waiting-time SLO, burst size, and worker count/downstream concurrency limits. Too small a queue may reject too early under valid bursts; too large a queue may absorb requests that have already lost their value.

Note that capacity refers to **waiting tasks**, not all in-flight tasks. Total concurrency/in-flight includes active tasks, queued tasks, and possibly tasks at other pipeline stages.

## 8. Example 2 — bounded queue surfaces overload via rejection

Create `BoundedQueueDemo.java`, Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

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
            pool.execute(() -> {});
            pool.execute(() -> {});

            boolean rejected = false;
            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            System.out.println("queued = " + pool.getQueue().size());
            System.out.println("rejected = " + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
        System.out.println("completed = " + pool.getCompletedTaskCount());
    }
}
~~~

Run:

~~~bash
javac BoundedQueueDemo.java
java BoundedQueueDemo
~~~

Normal stdout:

~~~text
queued = 2
rejected = true
completed = 3
~~~

One worker is blocked, two tasks sit in the capacity-2 queue; the fourth task has no room left and no additional worker can be created since max=1. `AbortPolicy` throws an exception instead of accepting an unbounded backlog. After releasing the latch, the three accepted tasks complete.

**A bounded queue does not create extra processing capacity**, but it allows the application to **detect overload in a controlled way**. Callers must be designed to handle `RejectedExecutionException`: reject, retry with backoff, notify the client, write to a dead-letter store if needed, or do the work at the appropriate layer.

## 9. Rejection policies and tradeoffs

`ThreadPoolExecutor` provides built-in `RejectedExecutionHandler` implementations:

| Policy | Behavior when the pool cannot accept a task | Watch out for |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Caller must handle it; good for avoiding silent work loss |
| `CallerRunsPolicy` | If the pool **is not shut down**, runs the task on the thread calling `execute` | Provides backpressure, but increases caller latency and changes execution context |
| `DiscardPolicy` | Silently drops the task | Can lose work unnoticed; only suitable when business logic allows it |
| `DiscardOldestPolicy` | Attempts to drop the task at the head of the queue and resubmit | Loses older work; unsuitable if ordering/priority matters |

**Important detail:** `CallerRunsPolicy` **discards the task** when the executor has already been shut down. Therefore, it does not guarantee that “every task will be executed.” It is only a feedback strategy while the pool is still accepting tasks.

`DiscardOldestPolicy` does not mean dropping the “lowest-priority” task in every queue. For a priority queue, the head element depends on the comparator; for a FIFO queue, it is typically the task that has been waiting the longest.

### CallerRunsPolicy may be unsuitable on a request thread

If a task takes several seconds, the request/event-loop thread itself may have to execute it and block as well. Context such as thread-locals, transactions, security principals, or held locks may differ from a worker thread. Only use this policy when **inline execution** is valid behavior and acceptable in terms of latency.

## 10. Example 3 — CallerRunsPolicy actually runs on the submitter

Create `CallerRunsDemo.java`, Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread submitter = Thread.currentThread();
        AtomicBoolean ranInCaller = new AtomicBoolean();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

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

            pool.execute(() -> {}); // Queue slot is now occupied.
            pool.execute(() -> ranInCaller.set(
                    Thread.currentThread() == submitter));

            System.out.println("caller ran = " + ranInCaller.get());
            System.out.println("queued = " + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Normal stdout:

~~~text
caller ran = true
queued = 1
~~~

Because the worker is busy and the capacity-1 queue is full, the third task runs **synchronously on the main thread**. `execute` only returns after this task finishes, so the submitter absorbs the feedback. The result is verified by **Thread identity**, rather than guessing thread names or OS scheduling.

When choosing a policy, clearly define whether the client is allowed to wait longer, whether callbacks can run on the caller, and whether task exceptions may propagate to the caller.

## 11. Deadline, timeout, and cancellation risks

A request waiting on `future.get(timeout, unit)` and hitting `TimeoutException` does not mean the task was cancelled. The task may:

- Still sit in the queue after the client has given up.
- Be started by a worker after the deadline, consuming resources for a result nobody will read.
- Have already run and produced side effects, while the caller retries and creates a second task.
- Not handle cancellation and continue after `Future.cancel(true)` if it does not cooperate with interruption.

Proper deadline management requires clear rules: who owns the Future, who calls cancel, whether the task checks the deadline when starting, whether a task performing side effects is idempotent, and where success/failure state is recorded.

**Waiting timeout is not execution timeout.** `Future.get(100, MILLISECONDS)` stops waiting after that duration; it does not automatically interrupt the worker or remove the queue entry.

### A cancelled Future may still remain in the work queue

Tasks submitted via `submit` are usually wrapped in `FutureTask`. `Future.cancel()` changes the Future's state; it does not necessarily remove the wrapper from the queue immediately. `ThreadPoolExecutor.purge()` is provided to remove cancelled Future tasks still in the work queue, though it has a cost and does not replace bounded admission.

`ScheduledThreadPoolExecutor` has a separate `setRemoveOnCancelPolicy(true)` method; do not confuse that method with the API of a regular `ThreadPoolExecutor`.

## 12. Example 4 — cancellation differs from queue removal

Create `CancelledQueueDemo.java`, Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CancelledQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2));

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

            Future<?> pending = pool.submit(() -> {});
            boolean cancelled = pending.cancel(false);

            System.out.println("cancelled = " + cancelled);
            System.out.println("queue before purge = "
                    + pool.getQueue().size());

            pool.purge();
            System.out.println("queue after purge = "
                    + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac CancelledQueueDemo.java
java CancelledQueueDemo
~~~

Normal stdout:

~~~text
cancelled = true
queue before purge = 1
queue after purge = 0
~~~

The worker is held, so the Future cannot start yet; cancel marks the Future as cancelled, but the wrapper remains in the queue. `purge` removes it. Do not generalize this implementation behavior to every custom executor; check the contract and instrumentation of the executor you are using.

## 13. Admission control and backpressure beyond queue bounds

A bounded queue can still accept more tasks than the SLA allows. Complementary approaches:

- **Rate limiting** at the producer/API layer: avoid submitting faster than sustainable processing speed.
- **Semaphore for an in-flight budget**: limit the total number of accepted tasks including both running and queued, not just queue length.
- **Explicit rejection**: return an overload signal and retry-after/backoff when business rules permit.
- **Caller-runs** if inline execution is valid.
- **Pool isolation by workload**: CPU-bound, blocking I/O, and high/low priority tasks can use separate resources.
- **Coalescing/deduplication**: drop stale status notifications that are no longer valuable, per business rules.
- **Deadline-aware tasks**: a task already expired when it starts can return a cancelled result instead of performing useless side effects.
- **Durable queue outside the JVM** when load exceeds memory and persistence is required, paired with quotas/retention/broker backpressure; not a way to “create infinite capacity.”

### Be careful when rolling your own Semaphore

A naive pattern that acquires a permit before `submit` and releases it in the worker's `finally` block can **leak permits** if the task is cancelled **before execution**: the worker's `finally` block never runs. When `submit` is rejected, the permit must also be returned; when a handler runs the task inline on the caller, you must avoid **double-releasing** when an exception unwinds the call stack. A correct solution requires an ownership/release-once protocol across all states, not just slapping on a `Semaphore`.

If the need is simply to bound the queue, `ArrayBlockingQueue` with explicit rejection can be less error-prone.

## 14. Choosing capacity from memory budget and latency budget

There is no single default capacity that fits every system. Consider two main bounds:

**Memory bound:** suppose each queued task retains an average of R bytes of retained heap as measured, and the heap budget allocated to the queue is M bytes; the theoretical capacity must not exceed M/R, and headroom is needed for GC, unusually large task payloads, workers, and other subsystems.

**Latency bound:** with a steady completion rate of about C tasks/s and an allowable queue wait time of about W seconds, a queue with far more elements than C×W will make it hard for tasks at the tail to meet their deadline. This is only a rough estimate for FIFO and relatively uniform workloads, not a hard guarantee when task durations vary.

If the two bounds yield different numbers, the **tighter bound** is the starting point for experimentation. Do not set queue capacity simply to “the largest number the JVM allows.”

| Question | Why it matters |
| --- | --- |
| Peak arrival rate and how long do bursts last? | Determines how much backlog truly needs to be absorbed |
| Completion rate when downstream is slow? | Measures capacity in worst-case scenarios |
| Retained heap per queued task? | Prevents OOM before capacity hits its threshold |
| P95/p99 queue wait target? | Protects SLA rather than just heap |
| Timeout/cancel rate? | Avoids keeping tasks that no longer have value |
| Is rejection acceptable? | Decides between fail-fast or durable buffering |
| Are tasks idempotent? | Avoids retry storms/double side effects |
| What is the shutdown deadline? | A very long queue makes draining slow |

## 15. Shutdown with large queues

`ExecutorService.shutdown()` stops accepting new tasks and allows already-accepted tasks to proceed per contract, including those still waiting. With a huge queue, graceful shutdown can take a very long time.

`shutdownNow()` is a best-effort cancellation request: it attempts to interrupt running tasks and returns the list of tasks that had not started. It **does not** guarantee that running threads stop immediately, nor does it automatically persist waiting tasks. The owner must have an appropriate policy to record/requeue/cancel them.

`awaitTermination(timeout, unit)` only waits for the terminated state; it does not fix a backlog or cancel tasks on its own. If a task is stuck in I/O that ignores interrupts, the executor may fail to terminate within the timeout.

~~~java
// Coordinated shutdown snippet; caller must handle InterruptedException.
pool.shutdown();
if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
    java.util.List<Runnable> neverStarted = pool.shutdownNow();
    // Per business logic: record, cancel, or hand off tasks that never started.
    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        // Tasks still unresponsive to interruption: alert/escalate.
    }
}
~~~

Do not turn an overload problem into “fast shutdown by dropping the entire backlog” if work must be processed reliably. Acceptable loss and retry/durability must be designed explicitly.

## 16. Observability: which metrics should be tracked?

`ThreadPoolExecutor` exposes getters such as:

- `getQueue().size()`: number of tasks waiting in the queue **at the moment of measurement**.
- `getActiveCount()`: number of threads actively executing tasks, an **approximate** value for monitoring.
- `getPoolSize()`, `getLargestPoolSize()`: current and historical maximum worker counts.
- `getTaskCount()`, `getCompletedTaskCount()`: total and completed task counts, values intended for monitoring.
- `getRejectedExecutionHandler()`: configured policy, though counting rejections usually requires your own instrumentation.
- **Queue waiting time**: time from enqueue/accept to task start; critical for SLAs.
- **Execution time**: how long the task runs; avoid confusing it with queue wait.
- **Heap/GC**, downstream response time, timeouts, cancellations, and retries.

Snapshot/approximate getters **are not synchronization primitives**: checking `getQueue().size() < capacity` and then calling `execute()` does not guarantee room remains, because another thread may submit in the meantime. Rely on the bounded queue/rejection itself or a proper admission protocol.

### Clear signs of overload

- Queue size grows continuously across multiple measurement intervals, failing to drain after bursts.
- Completed/sec stays below accepted/sec over a sustained period.
- Active workers reach the useful worker count while the queue keeps growing.
- P99 queue wait rises, and many tasks start after the client deadline.
- Post-GC heap grows alongside the queue.
- Retry rate, timeout rate, and cancelled task count rise together.
- Executor shutdown takes a long time due to backlog.

If the queue is always 0 yet requests are still slow, look for another bottleneck: running tasks, downstream services, `SynchronousQueue`, thread count, lock contention, or CPU, instead of blaming every issue on an unbounded queue.

## 17. Load testing and real-world risks

There is no need to deliberately push the JVM to `OutOfMemoryError` to prove the risk. Use latches as in the examples above, small queue capacities, deadlines, and clear metrics. For dedicated load tests, verify:

1. **Steady state:** are accepted/completed balanced and is the queue stable?
2. **Burst:** does the queue drain within the allowed time after a burst passes?
3. **Sustained overload:** do rejection/backpressure trigger properly?
4. **Slow tasks:** when workers are blocked, how does queue wait change?
5. **Timeout/cancel:** do expired tasks still run or retain memory?
6. **Failure:** are exceptions thrown by tasks recorded, retried properly, and idempotent?
7. **Shutdown:** with a remaining backlog, do `shutdown`/`shutdownNow` behave according to policy?
8. **Caller-runs:** is the submitter blocked for too long or running tasks under an inappropriate context?
9. **Memory:** do post-GC heap and retained task graphs fit within the budget?
10. **Tail latency:** do p95/p99 of queue wait and end-to-end latency stay within requirements?

Use JMH for appropriate microbenchmarks, but evaluating queue overload requires **load tests with multiple producers, representative task durations, downstream limits, and cancellation/shutdown scenarios**. A `System.nanoTime()` loop running in `main` does not reflect real pressure.

### A specific note on `submit`

With `submit(Callable/Runnable)`, a task's exception is typically stored in the `Future`; if you ignore the Future without an error-observation channel, tasks can **fail silently from the business logic's perspective**. `execute(Runnable)` handles exceptions differently. Thus, monitoring “submit succeeded” does not prove tasks ran properly, especially when the queue is huge.

## 18. Decision workflow when spotting an unbounded queue

**Step 1 — Identify the actual executor type.** `newFixedThreadPool`, `newSingleThreadExecutor`, or a custom `ThreadPoolExecutor`? What kind of work queue, what capacity, what core/max, and what rejection handler?

**Step 2 — Measure arrival vs. completion.** Tasks submitted and completed over the same time window; is the backlog growing sustainably?

**Step 3 — Assess memory retention.** Which large object graphs do tasks hold, are cancelled Futures sitting in the queue, and how much memory budget remains for the queue?

**Step 4 — Assess deadlines.** Is a task still valuable by the time it runs, or is it just doing wasted work? Should it be rejected/cancelled/expired early?

**Step 5 — Choose capacity.** Base it on both memory and latency; do not default to `Integer.MAX_VALUE`.

**Step 6 — Choose an overload policy.** Abort, caller-runs if semantics allow, rate limiting, semaphore admission with release-once, or a durable queue with quotas. Record rejections and their client impact.

**Step 7 — Check worker count/downstream.** CPU-bound differs from blocking I/O; adding workers does not automatically increase DB capacity or external API rate limits.

**Step 8 — Check failure and shutdown.** Collect errors from `Future`, have a cancellation policy and drain time limit; do not lose tasks unintentionally.

**Step 9 — Benchmark/load test.** Compare p95/p99 wait, completed/sec, heap, GC, rejections, timeouts, and correctness under representative load.

## 19. Common misconceptions

| Misconception | Reality |
| --- | --- |
| “An unbounded queue means infinite resources.” | Heap is finite; `LinkedBlockingQueue` also has an `Integer.MAX_VALUE` element-count bound |
| “Just increase `maximumPoolSize`.” | Unbounded queues usually accept tasks before creating workers beyond core |
| “`submit` returns fast, so tasks run fast.” | They may still be waiting a very long time |
| “No rejections means the system is healthy.” | The queue may be accumulating a dangerous backlog |
| “Small tasks have a small memory footprint.” | Closures and `FutureTask` can retain large object graphs |
| “A `Future.get` timeout cancels the task.” | Caller timeout is not cancellation |
| “`cancel` immediately removes the task from the queue.” | Some executors require dequeueing or `purge` |
| “A bounded queue handles overload by itself.” | It makes overload visible; callers still need a policy |
| “`CallerRunsPolicy` always executes the task.” | After shutdown it can drop tasks; before shutdown it can block the caller |
| “Queue size 0 means all tasks are done.” | Running tasks are not in the queue |
| “`shutdown()` clears the backlog.” | It normally drains already-accepted tasks |
| “`shutdownNow()` guarantees immediate termination.” | It is best-effort interruption; some tasks do not cooperate |
| “A short benchmark is enough to prove optimality.” | Results depend on contention, GC, payload, scheduling, and downstream |

## 20. Self-check questions

**Question 1.** A `ThreadPoolExecutor` has core=2, max=20, and `new LinkedBlockingQueue<>()`. If core workers are busy, will new tasks necessarily scale the pool up to 20 workers?  
**Answer:** No. The huge queue usually accepts the tasks, so the executor does not need to create workers beyond core.

**Question 2.** Why can an OOM occur before the queue reaches `Integer.MAX_VALUE`?  
**Answer:** The number of tasks and their captured object graphs can exhaust the heap much earlier.

**Question 3.** When `Future.get(100, MILLISECONDS)` times out, has the task stopped?  
**Answer:** Not necessarily. The caller's wait deadline is separate from execution/cancellation.

**Question 4.** One worker is blocked, a bounded queue of capacity 2 has 2 waiting tasks, and maxPoolSize=1. What happens to the next task under `AbortPolicy`?  
**Answer:** It is rejected with `RejectedExecutionException`.

**Question 5.** Does `CallerRunsPolicy` guarantee a task will run even when the executor has shut down?  
**Answer:** No. The policy drops tasks on shutdown; when not shut down and under overload, the task may run inline on the caller.

**Question 6.** If `getQueue().size() == 0`, can you conclude the executor has no work?  
**Answer:** No. Workers may still be executing tasks.

**Question 7.** Why does `shutdown()` take a long time with a large unbounded queue?  
**Answer:** It does not automatically drop accepted tasks; the executor must finish the backlog before terminating, unless policy/cancellation changes.

**Question 8.** Does `cancel(false)` on a queued Future necessarily remove the wrapper immediately?  
**Answer:** No. `ThreadPoolExecutor.purge()` can be used to remove cancelled Futures still in the queue.

**Question 9.** Is measuring only accepted/sec enough to detect overload?  
**Answer:** No. You also need completed/sec, queue slope, wait latency, heap/GC, timeouts, and failures/rejections.

**Question 10.** Is the criterion for choosing queue capacity “the largest the JVM can withstand”?  
**Answer:** No. It must be based on heap budget, queue waiting-time deadline, workload bursts, and overload policy.

## Official Java SE Documentation

- [`ThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core/max/queue strategy, rejection, `purge`, monitoring.
- [`Executors` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): `newFixedThreadPool`, `newSingleThreadExecutor`, `newCachedThreadPool`.
- [`LinkedBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): default capacity and queue behavior.
- [`ArrayBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO queue.
- [`RejectedExecutionHandler` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html): handling unaccepted tasks.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): timeout, cancellation, and completion.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, termination, task lifecycle.
- [`Semaphore` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): admission/resource permits.

**Key takeaway:** An unbounded queue **delays when you have to face overload**; it does not give an executor infinite throughput. A safe design requires **bounded admission, memory and latency budgets, rejection/backpressure policies, deadlines/cancellation, backlog measurement, and shutdown semantics**.
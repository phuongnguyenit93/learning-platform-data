# ThreadPoolExecutor Admission Order: Core Threads, Queue, Maximum, and Rejection

## 1. The Problem to Understand

In Java, when `ThreadPoolExecutor.execute(Runnable)` is called, the executor must decide how a new task will be executed: hand it to a **newly created worker**, place it into the **work queue**, create an additional worker when the queue cannot accept it, or invoke the **RejectedExecutionHandler**.

Many people think `corePoolSize=2, maximumPoolSize=8` means the executor will run 8 tasks concurrently as soon as 8 requests arrive. That is usually **wrong**: with a work queue capable of accepting work, once the core pool size is reached, the executor **prioritizes the queue**, not expanding immediately to maximum.

**Rule of thumb:**

~~~text
              execute(task)
                   │
       workerCount < corePoolSize?
            ┌──────┴──────┐
           YES            NO
            │              │
    create core worker  try queue.offer(task)
    run new task         ┌───┴─────┐
                      success    failure
                         │          │
                   recheck pool   try creating worker
                   state/count    up to maximumPoolSize
                         │          ┌───┴────┐
                      queued     success   failure
                                    │         │
                                run task    REJECT
~~~

The diagram illustrates the **common decision path** and omits several important concurrent state checks. In practice, after the queue accepts a task, the executor **rechecks** whether the pool has been shut down or whether the worker count has dropped to 0; it may remove the just-queued task to reject it or start a worker to ensure progress.

After this lesson, you will:

- Accurately describe the **core → queue → maximum → rejection** rules of `ThreadPoolExecutor`.
- Distinguish **worker count**, **active count**, **queue size**, **accepted**, **started**, and **completed**; avoid confusing execution progress with admission decisions.
- Understand the impact of `ArrayBlockingQueue`, `LinkedBlockingQueue`, `SynchronousQueue`, bounded/unbounded queues, and executor factories.
- Analyze why `maximumPoolSize` rarely takes effect with an unbounded queue, yet is crucial when the queue is bounded or uses direct handoff.
- Know why shutdown, racing updates, and worker creation failures can cause a task to be rejected even when looking at the thread count and queue alone makes it seem there is room.
- Choose among `AbortPolicy`, `CallerRunsPolicy`, `DiscardPolicy`, and `DiscardOldestPolicy` based on zero-task-loss and backpressure requirements.
- Run Java 17+ examples using `CountDownLatch` to control ordering and produce deterministic stdout instead of guessing with `Thread.sleep`.
- Review backlog, tail latency, shutdown, cancellation, and starvation/deadlock risks.

**Scope:** Java SE and the Executor Framework; framework integrations are not covered. All programs in this lesson compile with JDK 17+.

## 2. Minimal Structure of ThreadPoolExecutor

Commonly used constructor:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2,                             // corePoolSize
        4,                             // maximumPoolSize
        30,                            // keepAliveTime
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(3),   // max 3 waiting tasks
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

This is an **illustrative snippet inside a method**, not a standalone program. The caller must manage the lifecycle of `pool` via `shutdown()` and an appropriate waiting/cancellation strategy.

Key components:

| Component | Function |
|---|---|
| `corePoolSize` | Worker threshold that the executor **prioritizes creating** before queuing new tasks. |
| `maximumPoolSize` | Limit on the total number of workers when the queue cannot accept more tasks. |
| `workQueue` | Holding area for tasks that have been accepted but have not yet started running on a worker. |
| `keepAliveTime` | Duration an eligible worker is kept alive while idle before it may be reclaimed. |
| `ThreadFactory` | Creates Threads; can set names, daemon status, uncaught exception handlers, etc. |
| `RejectedExecutionHandler` | Handles tasks that are not admitted due to saturation, shutdown, or inability to create a worker. |
| `execute(Runnable)` | Submits a task for later execution; may create a new worker, enqueue, or reject. |

`corePoolSize` and `maximumPoolSize` are neither two separate queues nor independent request counts. `maximumPoolSize` is the limit on **total** workers, not additional workers on top of core. For example, core=2, max=4 means at most 4 workers in total according to the configuration, not 2+4=6.

### Configuration constraints

~~~text
0 <= corePoolSize <= maximumPoolSize
maximumPoolSize > 0
keepAliveTime >= 0
workQueue != null
~~~

Invalid parameters can throw `IllegalArgumentException` or `NullPointerException` when creating or configuring the executor. Enabling `allowCoreThreadTimeOut(true)` specifically requires `keepAliveTime > 0`.

## 3. First Rule: Worker Count Below corePoolSize

When the executor is in a state accepting work and the worker count is lower than `corePoolSize`, it **prioritizes trying to create an additional worker** to run the newly submitted task, rather than placing the task into the queue.

Suppose the configuration is:

~~~text
corePoolSize = 2
maximumPoolSize = 4
queue capacity = 3
initial workerCount = 0
~~~

When calling `execute(task1)` and `execute(task2)` sequentially, assuming no worker has terminated or changed configuration:

- Task 1: creates the first worker; this worker takes task 1 as its first piece of work.
- Task 2: creates the second worker; this worker takes task 2.
- The queue remains empty on both submissions because the pool is still below core.

**Common misconception:** the rule is based on the **current worker count**, not simply `getActiveCount()`. The Javadoc states that if fewer than `corePoolSize` threads are running, the executor always prefers adding a new thread rather than queuing, even if an existing worker is idle. Therefore, you cannot deduce "there is an idle worker, so the new task will definitely be queued" when total workers are still below core.

### Core workers are created lazily

The constructor usually **does not create all** core workers immediately. If you need workers ready before requests arrive:

~~~java
int started = pool.prestartAllCoreThreads();
~~~

`prestartAllCoreThreads()` returns the number of newly started core workers. `prestartCoreThread()` tries to create one missing core worker. This is a warm-start option and does not change the fundamental queue and maximum rules under load.

### CorePoolSize = 0

`corePoolSize=0` is valid when `maximumPoolSize>0`. The executor still has a mechanism to create a worker to process work, including when a task has been queued and no worker exists yet. Do not read the simplified diagram as "core=0 so tasks just sit in the queue forever with no one running them." The implementation performs a post-queue recheck and creates a worker when needed.

## 4. Second Rule: At Core, Prioritize the Queue

Once the worker count has reached at least `corePoolSize`, the executor **tries to place the task into the work queue first**, rather than creating a new worker just because `workerCount < maximumPoolSize`.

With core=2, max=4, bounded queue capacity=3, and **both core workers busy processing long tasks**, subsequent tasks arrive as follows:

~~~text
running workers: [task1, task2]
workQueue:       []

execute(task3) → workQueue.offer(task3) = true
workQueue:       [task3]

execute(task4) → workQueue.offer(task4) = true
workQueue:       [task3, task4]

execute(task5) → workQueue.offer(task5) = true
workQueue:       [task3, task4, task5]

workerCount can still be 2 even though max = 4.
~~~

This is why **the queue determines how the pool scales**. As long as the queue can still accept tasks, the pool normally does not increase the worker count toward max.

**The queue holds waiting work, not running tasks.** When a worker takes `task3` from the queue, the queue size decreases and `task3` becomes active. Never treat `queue size=0` as meaning the system has no work currently executing.

### A queue does not guarantee completion order

`task3` may be submitted and queued before `task6`, yet `task6` can be handed directly to an extra worker when the queue is full. If `task6` runs quickly, it **may finish before `task3`**, which is still waiting. Even if the queue is FIFO, **the pool as a whole does not provide FIFO completion order**. Tasks running on different workers can finish in any order.

This clearly affects applications requiring per-key ordering, such as processing state updates for a single account. If ordering is a business invariant, you need dedicated serialization or an ordering protocol, not just reliance on a FIFO queue.

## 5. Third Rule: Only When the Queue Rejects Does the Pool Try Scaling to maximumPoolSize

When `queue.offer(task)` fails, the executor tries to create a new worker to run that task, up to `maximumPoolSize`.

Using the example core=2, max=4, queue capacity=3 with busy workers:

~~~text
After 5 tasks:
- worker 1: task1 (running)
- worker 2: task2 (running)
- queue: [task3, task4, task5] (full)

execute(task6):
- queue.offer(task6) → false
- workerCount=2 < max=4
- create extra worker 3, assign task6 as its first task

execute(task7):
- queue is still full
- workerCount=3 < max=4
- create extra worker 4, assign task7 as its first task
~~~

**`task6` and `task7` may start before `task3–5`**, depending on the scheduler and execution time. Extra workers are created because the queue could not accept the task; direct handoff does not preserve order relative to older queued tasks.

### MaximumPoolSize does not trigger worker creation if the queue keeps accepting

If `maximumPoolSize=100` but `queue.offer` keeps succeeding, the queue-first policy means the pool will not necessarily create a 3rd worker when core=2. Conversely, with `SynchronousQueue`, which has no storage for tasks, `offer` can fail immediately when no worker is waiting for handoff, causing the pool to create additional workers much sooner.

**There is no single "optimal" maximum without knowing the queue strategy and workload.**

## 6. Fourth Rule: Cannot Queue and Cannot Add Worker → Reject

When both of the following conditions hold simultaneously:

1. The work queue cannot accept more tasks.
2. No additional worker can be created, such as `workerCount >= maximumPoolSize`.

The executor passes the task to the `RejectedExecutionHandler`.

A task can also be rejected **when the executor has already been shut down**, even if the queue has space or the worker count is below max. In addition, a `ThreadFactory` failing to create a `Thread`, or resource exhaustion, can prevent worker creation; do not assume every rejection is caused by a full queue.

Example with core=2, max=4, queue capacity=3:

| Submitted task | Both core workers and queue still hold work | Typical decision | Total workers | Queue size |
|---|---|---|---:|---:|
| 1 | No workers yet | Create core worker 1 | 1 | 0 |
| 2 | Task 1 still running | Create core worker 2 | 2 | 0 |
| 3 | Both workers busy | Queue | 2 | 1 |
| 4 | Both workers busy | Queue | 2 | 2 |
| 5 | Both workers busy | Queue full after accepting task5 | 2 | 3 |
| 6 | Queue already full | Create extra worker 3 | 3 | 3 |
| 7 | Queue already full | Create extra worker 4 | 4 | 3 |
| 8 | Workers at max, queue full | Reject/handler | 4 | 3 |

This table is **only accurate under the assumption** that no task finishes or is taken from the queue by a worker during submission. In a real application, a worker may finish a task and dequeue a waiting task before the next submission, changing all the numbers. Therefore, do not infer actual runtime decisions **solely from request sequence numbers**.

## 7. A More Complete Decision Diagram

~~~text
                          execute(command)
                                 |
                         command == null?
                         /              \
                       yes              no
                        |                |
                NullPointerException   check state/workerCount
                                         |
                           workerCount < core?
                           /                 \
                         yes                 no
                          |                   |
                 addWorker(task, core=true)  pool RUNNING?
                          |                  /           \
                       success             yes           no
                          |                 |             |
                        return          offer(queue)   do not accept
                                         /    \
                                     success  fail
                                        |       |
                                RECHECK pool    addWorker(task,
                                 state/count    core=false, <=max)
                                     |              /     \
                           shutdown? 0 workers   success  fail
                             |          |           |      |
                        remove/reject  start      return  reject
                                     worker if
                                      needed
                                        |
                                     return
~~~

This diagram is an **explanatory model** of the contract, not copy-paste implementation code for building your own executor. OpenJDK uses atomic operations and recheck steps to handle state changes happening mid-decision.

### Why recheck after queue offer succeeds?

Suppose thread A checks that the pool is still RUNNING, and then `queue.offer(task)` succeeds. At the same time, thread B calls `shutdown()`. If A simply returned "accepted" without checking for state changes, a task could remain in the queue of a pool that is no longer allowed to accept new work. That is why the implementation rechecks `runState`: in certain interleavings, it removes the task from the queue and rejects it.

Another example: the queue accepts a task, but the worker count drops to 0 due to timeout or error. The executor must ensure a worker can continue picking up work, rather than leaving a task in the queue with no worker to process it. Hence, it checks and creates a worker when needed.

### "Queued" does not mean "guaranteed to run exactly once" in all situations

A task may:
- be accepted and started;
- be queued but later drained by `shutdownNow` before running;
- be removed from the queue by a caller with task-management access;
- be cancelled via `Future.cancel(...)` before execution;
- run and throw an exception (which is still an execution that started).

Do not equate `execute` returning normally, `submit` returning a `Future`, `Future.isDone()`, `Future.isCancelled()`, and completed side effects. You need a proper completion/acknowledgment protocol if the work is business-critical.

## 8. Standalone Example 1: Verifying core → queue → max → reject

The following program **does not rely on `Thread.sleep()`**. It uses `CountDownLatch` to keep workers busy until `main` finishes observing. This allows the admission order to be verified via worker count and queue size.

Save as **AdmissionOrderDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class AdmissionOrderDemo {
    private static Runnable blockingTask(
            CountDownLatch started,
            CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch coreStarted = new CountDownLatch(2);
        CountDownLatch extraStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;

        try {
            pool.execute(blockingTask(coreStarted, release)); // #1
            pool.execute(blockingTask(coreStarted, release)); // #2
            coreStarted.await();

            pool.execute(() -> { }); // #3: queue slot 1
            pool.execute(() -> { }); // #4: queue slot 2

            pool.execute(blockingTask(extraStarted, release)); // #5
            pool.execute(blockingTask(extraStarted, release)); // #6
            extraStarted.await();

            try {
                pool.execute(() -> { }); // #7: queue + workers full
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            System.out.println("workers=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("rejected=" + rejected);
        } finally {
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

Compile and run with JDK 17+:

~~~bash
javac AdmissionOrderDemo.java
java AdmissionOrderDemo
~~~

**Stdout when there are no external interrupts and all workers complete:**

~~~text
workers=4
queued=2
rejected=true
completed=6
~~~

Step-by-step explanation:

1. Tasks #1 and #2 initialize the two core workers, and both workers wait on `release.await()`.
2. `main` proceeds only after `coreStarted.await()` completes, ensuring both workers have started and **cannot finish** before `release` is opened.
3. Tasks #3 and #4 enter the queue of capacity 2. Since both core workers are waiting on `release`, neither worker takes these two tasks.
4. Tasks #5 and #6 arrive when the queue is full. The pool creates the third and fourth workers; each takes its new task immediately and waits on `release`.
5. `main` waits for both extra workers to report that they have started, then submits task #7. Because the queue still holds #3/#4 and all four workers are held busy, `AbortPolicy` throws `RejectedExecutionException`; `main` catches it and records `true`.
6. Before `release`, the count snapshots are deterministically **4 workers, 2 queued** under the example's conditions. No assumptions are made about worker name order or task completion order.
7. Finally, all four workers are released; #3 and #4 are processed and the executor shuts down. Six tasks were accepted and completed; #7 was rejected, so `getCompletedTaskCount()` is 6.

**Note:** `getCompletedTaskCount()` is described by the Javadoc as an **approximate** value while the pool is active, but after all accepted tasks finish and the pool has terminated, the count in this example is stable. If `awaitTermination` fails within 5 seconds or a task is unexpectedly interrupted, identical stdout cannot be guaranteed.

### Failure-path handling in the demo

The program places `release.countDown()` in `finally` to avoid holding workers indefinitely if an unexpected submission/rejection causes `main` to exit the block. In production code, you must also log/propagate errors and handle shutdown so required data is not lost.

## 9. Standalone Example 2: Unbounded Queues Prevent Maximum from Taking Effect

With a default `LinkedBlockingQueue<>`, the queue has a very large nominal capacity. Once a core worker exists and is busy, new tasks are queued rather than creating additional workers up to max.

Save as **QueueFirstDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueFirstDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 10, 30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );

        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

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

            pool.execute(() -> { });
            pool.execute(() -> { });
            pool.execute(() -> { });

            System.out.println("core=" + pool.getCorePoolSize());
            System.out.println("max=" + pool.getMaximumPoolSize());
            System.out.println("workers=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
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

Compile and run:

~~~bash
javac QueueFirstDemo.java
java QueueFirstDemo
~~~

Stdout:

~~~text
core=1
max=10
workers=1
queued=3
~~~

One core worker is held busy while three tasks wait. `max=10` **does not force the executor to create nine more workers**, because the queue keeps accepting tasks. This is why a pool with a large maximum can still suffer from growing queue depth, rising tail latency, and idle CPU.

**Do not treat an unbounded queue as having unlimited resources.** A default `LinkedBlockingQueue<>` has a capacity of `Integer.MAX_VALUE`, but task objects and queue nodes consume heap. Long before reaching the nominal limit, the application can experience memory pressure or `OutOfMemoryError` if producers outpace consumers over a sustained period.

## 10. Standalone Example 3: SynchronousQueue Causes Early Pool Expansion

`SynchronousQueue` **does not hold elements** like a normal queue. A successful handoff requires a matching waiting receiver. When the pool's core worker is busy and no worker is waiting to take a task, `SynchronousQueue.offer(task)` has no storage capacity, causing the executor to try creating additional workers up to max.

Save as **DirectHandoffDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class DirectHandoffDemo {
    private static Runnable blocked(
            CountDownLatch started,
            CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 20, TimeUnit.SECONDS,
                new SynchronousQueue<>(),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean thirdRejected = false;

        try {
            pool.execute(blocked(firstStarted, release));
            firstStarted.await();

            pool.execute(blocked(secondStarted, release));
            secondStarted.await();

            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                thirdRejected = true;
            }

            System.out.println("workers=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("thirdRejected=" + thirdRejected);
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

Commands:

~~~bash
javac DirectHandoffDemo.java
java DirectHandoffDemo
~~~

Stdout:

~~~text
workers=2
queued=0
thirdRejected=true
~~~

Because `SynchronousQueue` holds no backlog:
- The first task uses the core worker.
- While core is busy, the second task cannot be handed off immediately, so the executor creates an extra worker up to max=2.
- Both workers are busy; the third task cannot be queued and no more workers can be added: rejected.
- `queue.size()` remains **0**, which does not mean the pool is idle. It is a specific property of a handoff queue.

**Do not arbitrarily set an enormous `maximumPoolSize`** to avoid rejections with `SynchronousQueue`: when many blocking tasks arrive in succession, the pool can create too many platform threads and exhaust system resources.

## 11. How Do Queue Rules Change Across Queue Types?

| Work queue | Holds backlog? | When core workers exist and all are busy | Role of `maximumPoolSize` | Risks |
|---|---|---|---|---|
| `LinkedBlockingQueue<>` without capacity | Yes, very large nominal capacity | Tasks enter the queue | Rarely reaches max | Uncontrolled heap/backlog growth |
| `ArrayBlockingQueue<>(n)` | Yes, up to `n` waiting tasks | Tasks enter the queue until full | Scales only when the queue is full | Rejection on overload |
| `LinkedBlockingQueue<>(n)` | Yes, up to `n` waiting tasks | Similar to bounded queue | Scales only when the queue is full | Requires sizing/backpressure |
| `SynchronousQueue<>` | Holds no waiting tasks | Attempts direct handoff to waiting worker; otherwise creates new worker | Takes effect early | Worker growth, rejection if max is small |
| `PriorityBlockingQueue<>` | Yes, practically unbounded by default | Queues by priority policy | Usually does not trigger scaling to max | Priority inversion/starvation, backlog |

To understand an executor, **always ask what the queue is and what its capacity is before looking at `maximumPoolSize`**.

### A FIFO queue does not mean a FIFO executor

Even with `ArrayBlockingQueue` or `LinkedBlockingQueue` following their own queue order, a task handed directly to an extra worker when the queue is full can start before tasks already waiting. The combination of worker scheduling and processing time makes **completion order** independent of **submission order**. Do not use a shared pool as a FIFO transaction engine if the business logic requires strict ordering.

### Executors.newFixedThreadPool and newCachedThreadPool

- `Executors.newFixedThreadPool(n)` configures a fixed worker count and a practically unbounded queue: worker count is bounded, while backlog can grow.
- `Executors.newCachedThreadPool()` uses direct handoff and can aggressively expand platform workers, reclaiming idle workers per policy: it does not provide a bounded concurrency limit suitable for every workload.
- `Executors.newSingleThreadExecutor()` runs one task at a time by design, but still requires queue and shutdown management, and is not a durable transaction log.
- `Executors.newWorkStealingPool(...)` belongs to a different model and should not be assumed to follow the admission diagram of a custom-configured `ThreadPoolExecutor` here.
- On Java 21+, `Executors.newVirtualThreadPerTaskExecutor()` uses one virtual thread per task; it does **not** throttle downstream concurrency via core/max/queue like a `ThreadPoolExecutor` platform worker pool.

## 12. Rejection Is a Policy Action, Not Necessarily an Exception

When a task cannot be admitted, `ThreadPoolExecutor` calls `RejectedExecutionHandler.rejectedExecution(task, executor)`. Standard policies:

| Policy | When pool is saturated and still RUNNING | What to understand |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | Default; caller must handle the exception, do bounded retries, or signal overload. |
| `CallerRunsPolicy` | Caller of `execute` runs the task directly | Natural backpressure, but can block the caller; if the executor is already shut down, the policy drops the task. |
| `DiscardPolicy` | Drops the task without throwing | Dangerous if the task must run; no completion evidence. |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submitting the new task | Can lose an older task; interaction with priority queues easily violates expectations. |

**Special rule:** `RejectedExecutionHandler` is an extension point, so a custom handler can block, route to another channel, record metrics, throw, or do something else. Therefore, you cannot say "every rejection throws an exception." With the default `AbortPolicy`, it throws; with `DiscardPolicy`, `execute` can return normally **even though the task was never run**.

### Rejection also occurs after shutdown

~~~java
pool.shutdown();
pool.execute(() -> System.out.println("will not be accepted"));
~~~

With `AbortPolicy`, `execute` throws `RejectedExecutionException` because the pool no longer accepts new work, **without the queue needing to be full**. With `CallerRunsPolicy`, if the executor has already shut down, the policy does not run the task on the caller. Always check lifecycle state and policy rather than assuming all rejections are saturation.

## 13. Standalone Example 4: CallerRunsPolicy Creates Backpressure

Suppose the pool has only **one worker**, one queue slot, and the first task is holding the worker. The second task occupies the queue; the third task is rejected in the normal admission sense, so `CallerRunsPolicy` **runs it directly on `main`**.

Save as **CallerRunsDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<String> thirdThread = new AtomicReference<>();

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workerStarted.await();

            pool.execute(() -> { }); // task 2 queued
            pool.execute(() ->
                    thirdThread.set(Thread.currentThread().getName()));

            System.out.println("thirdThread=" + thirdThread.get());
            System.out.println("queued=" + pool.getQueue().size());
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

Compile/run:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Stdout when run directly via `java CallerRunsDemo` from the default main thread:

~~~text
thirdThread=main
queued=1
~~~

Explanation:
- The worker is still waiting on `release`, and task #2 is queued.
- Task #3 arrives when no capacity remains; `CallerRunsPolicy` invokes the task's `run()` directly on the thread calling `execute`, which is `main`.
- `thirdThread` is set to `"main"` before `execute` returns, without waiting for a worker.
- The queue still holds task #2 because the first worker has not been released yet. Thus, the queued count is 1.
- If `main` is run through a harness that renames threads, the name may differ; the invariant semantics are **the submitting thread**.

**Benefit:** the producer is slowed down because it must execute tasks itself, creating a form of backpressure. **Cost:** if the caller is an event loop or a latency-sensitive request thread, it can be blocked for a long time, degrading tail latency.

## 14. Where Do execute and submit Differ in This Scenario?

`ThreadPoolExecutor.execute(Runnable)` directly applies the admission/rejection policy.

When using `ExecutorService.submit(Callable)` or `submit(Runnable)`:
- `submit` typically wraps the work in a `FutureTask` and dispatches it through `execute`.
- If the task is accepted, `submit` returns a `Future` to retrieve the result or cancel.
- If `AbortPolicy` rejects it, an exception may be thrown during `submit` and the caller **does not** receive a `Future` for an accepted task.
- If the handler **silently discards**, the caller may receive a `Future` that never executes or completes normally; `Future.get()` can wait forever without cancellation or timeout.
- With `CallerRunsPolicy`, the task may run on the **submitting thread** before `submit` returns.
- `Future.cancel(true)` only requests cancellation per the API; it does not force a task performing side effects to stop.

**Do not use `submit` returning as proof that a task is guaranteed to run.** Consider the handler, shutdown, queue removal, and lifecycle. If your workload requires durability, you need an explicit admission/acknowledgment layer beyond an in-memory queue.

### Task exceptions

With `execute`, an unhandled exception from `Runnable.run()` goes through the uncaught-exception/worker lifecycle mechanism. With `submit`, an exception from `Callable`/`Runnable` is captured in the `Future` and surfaced when `Future.get()` throws `ExecutionException`. This is **different** from rejection at submission time. Do not confuse "the task ran and failed" with "the task was not admitted to the executor."

## 15. Real-World Races Not Fully Shown in Simple Diagrams

### 15.1. Shutdown occurs after queue.offer succeeds

Thread A gets `true` from `queue.offer`. Thread B may call `shutdown()` almost simultaneously. The executor rechecks state and, when needed, **removes the just-enqueued task and rejects it**, rather than letting a new task slip past an invalid shutdown boundary.

That is why state checks and admission must use an atomic/synchronized protocol at the implementation level. Application authors should not replace `execute` with:

~~~java
if (!pool.isShutdown()) {
    pool.getQueue().add(task); // NOT the standard way to submit tasks
}
~~~

The snippet above is an **anti-pattern**. Between the check and `add`, the pool can shut down; manipulating the queue directly bypasses worker creation and retry/rejection logic. The Javadoc also discourages using `getQueue()` for normal task control, except for monitoring/debugging or specific intentional administrative actions.

### 15.2. Queue accepts a task but no workers remain

If workers have terminated due to errors, timeouts, or race conditions, a successful `queue.offer` alone does not guarantee anyone is consuming the queue. The executor checks the worker count and can create a new worker (even when `corePoolSize=0`) to avoid stranding queued tasks.

### 15.3. ThreadFactory fails to create a worker

If `ThreadFactory.newThread(...)` returns `null` or cannot create a thread due to resource limits, `addWorker` can fail. The end result can be rejection; **worker count being below `maximumPoolSize`** does not guarantee a new thread can actually be created.

### 15.4. Metrics change between reads

`getPoolSize()`, `getActiveCount()`, `getQueue().size()`, and `getCompletedTaskCount()` do not form a transactional snapshot of the executor. While you read them one by one, a worker may finish a task, dequeue a new task, or be reclaimed. They are useful for monitoring, but should not be used to build a DIY check-then-act algorithm in place of `execute`.

## 16. How Do KeepAlive and Core Timeout Affect Admission?

`keepAliveTime` does not alter the core → queue → max rule. It affects the **number of existing workers** when the pool is idle, which can cause subsequent `execute` calls to see a worker count below core.

- When the worker count exceeds `corePoolSize`, excess workers can be reclaimed after idling according to the keepAlive policy.
- By default, core workers are kept when idle, except for shutdown, errors, and lifecycle replacement.
- `allowCoreThreadTimeOut(true)` allows even core workers to be reclaimed when idle, provided `keepAliveTime > 0`.
- `prestartAllCoreThreads()` pre-creates core workers, changing the initial state before requests arrive.
- `keepAlive` does **not** limit how long a task runs, and does **not** force a blocked task to terminate when a deadline passes.

Hence, "will the next submission queue or create a core worker?" depends on the current worker count, which is influenced by prestarting, timeouts, worker failures, and dynamically updated core size.

## 17. Why Does Queue-First Before Extra Workers Have Tradeoffs?

This is a fundamental design policy of `ThreadPoolExecutor`, not a minor detail.

**Advantages of a moderate queue:**
- Limits creating platform threads too quickly.
- Reuses existing workers, reducing scheduling overhead and stack memory.
- Absorbs short bursts when arrival rate temporarily exceeds processing rate.

**Disadvantages of an oversized queue:**
- Tasks wait a long time before starting even when `maximumPoolSize` is high.
- Memory holds many `Runnable`/`FutureTask` instances and captured data, increasing heap usage.
- Deadlines may expire while tasks sit in the queue, turning them into wasted work.
- Tail latency (p95/p99) degrades while the system does not reject, making overload hard to detect if you only watch error rates.

**Advantages of a small queue / direct handoff:**
- When workers are busy, the pool can add workers earlier up to maximum.
- Capacity limits and rejections are more visible.

**Disadvantages:**
- Can create many threads, causing context switching and increased downstream load (DB, remote API, disk).
- If max is small and traffic bursts, many tasks may be rejected even for brief spikes.
- Callers must have proper backpressure, retry, or fallback protocols.

No single strategy fits all cases. Choose the queue based on consumer throughput, deadlines, memory budget, concurrency of arrivals, and what rejection means for your system.

## 18. Thread-Starvation Deadlock When Subtasks Are Queued

A dangerous case:

~~~text
core = maximum = 1
workQueue is unbounded

The single worker runs task A
  A submits task B to the same pool → B enters the queue
  A calls futureB.get() → waits for B to complete
  B is queued and needs the worker currently held by A
=> no free worker to run B
=> A and B can wait indefinitely
~~~

Increasing `maximumPoolSize` **will not save you** if an unbounded queue keeps accepting task B, preventing the pool from creating an extra worker. The root cause is the **task dependency structure** and admission policy.

Possible solutions:
- Avoid parent tasks blocking on child tasks within the same fixed pool.
- Separate tasks with different dependency levels onto appropriate executors.
- Design completion/composition without blocking a worker that holds pool capacity.
- Ensure there are no resource wait cycles, and do not rely on queue growth for liveness.
- Use timeouts where waiting is truly necessary, noting that a timeout only detects/ends the wait—it does not make the child task finish.

## 19. Observing and Monitoring Admission in Production

Metrics to track:

| Metric | API / observation method | Notes |
|---|---|---|
| Configured core size | `getCorePoolSize()` | Threshold before queuing. |
| Configured max size | `getMaximumPoolSize()` | Worker ceiling when unable to queue. |
| Current worker count | `getPoolSize()` | Can differ from both core and max. |
| Workers running tasks | `getActiveCount()` | Approximate at read time. |
| Queued tasks | `getQueue().size()` | Excludes tasks already taken by workers. |
| Completed tasks | `getCompletedTaskCount()` | Approximate while active. |
| Total tasks | `getTaskCount()` | Approximate submitted/processed tasks per metrics. |
| Peak worker count | `getLargestPoolSize()` | Shows whether the extra-worker range was ever reached. |
| Rejection count | Custom rejection handler / dedicated metric | Separate saturation from shutdown. |
| Queue wait time | Admission/start timestamps with proper protocol | Do not infer task latency from queue size alone. |

`ThreadPoolExecutor` counters/metrics aid **observation**; they do not make concurrency throttling correct on their own. A custom handler can record rejections, but must not silently swallow required tasks while letting the caller think they were accepted.

### Example of a custom handler that counts and rejects

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicLong;

final class CountingAbortHandler implements RejectedExecutionHandler {
    private final AtomicLong rejected = new AtomicLong();

    @Override
    public void rejectedExecution(Runnable task, ThreadPoolExecutor pool) {
        rejected.incrementAndGet();
        throw new RejectedExecutionException(
                "executor rejected task; shutdown=" + pool.isShutdown());
    }

    long rejectedCount() {
        return rejected.get();
    }
}
~~~

This is a **valid Java class without a `main` method**. When passed to the executor constructor, the handler records each rejection and throws an exception so the caller knows the task was **not admitted**. If you need to classify the cause, do not rely solely on the `isShutdown()` snapshot because state can change between the reject decision and the callback; combine lifecycle logs and metrics with clearer contracts.

## 20. Reading OpenJDK Source: The Three Steps of execute

The JDK expresses this idea at the implementation level in three stages:

1. If worker count is below core, try `addWorker(command, true)` and return on success.
2. If the pool is RUNNING, try `workQueue.offer(command)`. On success, **recheck state**: if the pool is no longer RUNNING and the task can be removed, reject; if workers are still missing, create a worker to ensure a consumer exists.
3. If unable to enqueue, try `addWorker(command, false)` within max. If creation fails, invoke rejection.

**This is a logical description**, not a source-code copy or a blueprint for building your own executor. OpenJDK's CAS and `runState` checks are critical to prevent races between shutdown, queuing, worker creation, and thread failure.

The subtlest point is that **returning from step 2 does not rest on a single `queue.offer()` call**. The double-check prevents tasks from being stranded or slipping into an invalid shutdown state. When debugging an "unexpected" executor rejection, remember that pool state may have changed between checks.

## 21. Configuration and Admission Logic Review Checklist

1. **What are the current `corePoolSize` and `maximumPoolSize`?** Have you verified that maximum is the total worker cap, not an extra count?
2. **What is the queue type and capacity?** Default `LinkedBlockingQueue<>` is practically unbounded, `ArrayBlockingQueue` is bounded, `SynchronousQueue` holds no backlog.
3. **Below core, is it understood that workers are created preferentially?** The default constructor does not necessarily prestart them.
4. **Once core is reached, is it understood that the queue is prioritized before expansion?** Do not promise max will be used as soon as task count rises.
5. **When the queue is full, is total max accounted for?** Rejection must be accounted for afterward.
6. **What is the rejection policy?** Abort, CallerRuns, Discard, DiscardOldest, or custom? Is the caller clearly notified when work is dropped?
7. **Can shutdown occur concurrently with submit?** Remember the executor double-checks after enqueue and rejects when no longer RUNNING.
8. **Can tasks finish before the whole batch is submitted?** Do not predict states by task sequence number without controlling conditions.
9. **Do parent tasks wait on child tasks in the same pool?** Avoid thread-starvation deadlock.
10. **How long is queue retention?** Task deadlines may expire before execution even starts.
11. **Is there backpressure or producer throttling?** Do not pick an unbounded queue just to avoid immediate rejections.
12. **Are queue depth, active count, completed count, rejections, and tail latency monitored?** Have approximate metrics been distinguished from synchronization primitives?
13. **Which layer owns timeouts and cancellation?** `keepAlive` is not a task timeout, and `Future.get(timeout)` does not cancel the task itself.
14. **Are shutdown/awaitTermination/cleanup handled properly?** After shutdown, new work is not admitted.
15. **Has overload been tested with a fixed queue?** Use latches/handoffs to control ordering rather than relying on `sleep` and guessing scheduler behavior.

## 22. Self-Check Exercises

**Q1.** A pool has core=2, max=8, and an unbounded `LinkedBlockingQueue`. Both core workers are busy, and 20 more tasks arrive. Will the pool definitely create all 8 workers?

**Answer:** No. After core, the queue accepts the tasks; `maximumPoolSize` generally has no effect while the queue still has capacity. Backlog grows in the queue.

**Q2.** A pool has core=2, max=4, queue capacity=2. Both core workers are busy, and the queue already holds two tasks. How is the next task handled?

**Answer:** `queue.offer` fails; if the pool is still RUNNING and a worker can be created, the executor creates a third (extra) worker to run the new task.

**Q3.** If the pool already has 4 busy workers and the queue is still full, what happens to a new task?

**Answer:** It is passed to the `RejectedExecutionHandler`. With `AbortPolicy`, `RejectedExecutionException` is thrown; with `CallerRunsPolicy` when the pool is not shut down, the caller runs the task.

**Q4.** Why can a task submitted later run before a task that was queued earlier?

**Answer:** When the queue is full, the executor can create an extra worker to run the **new task directly**. The older task continues waiting in the queue, so there is no FIFO guarantee for overall start/completion order.

**Q5.** Does `SynchronousQueue` hold many waiting tasks when the pool is overloaded?

**Answer:** No. It is a handoff queue with no storage capacity. When handoff cannot happen, the executor tries creating a worker up to max or rejects.

**Q6.** `ThreadPoolExecutor.execute` already queued a task—why can it still be rejected?

**Answer:** The executor rechecks after `offer`. If the pool shuts down during submission and the task can be removed, it rejects rather than letting a new task remain against policy.

**Q7.** Does `getQueue().size() == 0` prove the executor is completely idle?

**Answer:** No. Workers may still be executing tasks, especially with `SynchronousQueue`, which never holds a backlog.

**Q8.** Does `submit` returning a `Future` under `DiscardPolicy` guarantee the `Future` will complete?

**Answer:** No. The handler may silently drop the task; the `Future` may never receive a completion state from execution, and the caller can wait forever without a timeout or cancellation.

**Q9.** A fixed pool with one worker has task A submit B to the same pool and call `Future.get()`; why can this deadlock?

**Answer:** A holds the only worker while waiting for B; B is in the queue and cannot run because no worker is free. This is a thread-starvation deadlock.

**Q10.** A task is rejected due to shutdown even though the queue has room; does this violate the contract?

**Answer:** No. An executor does not accept new work after shutdown; rejection is not caused solely by saturation.

## 23. Official Documentation and Further Reading

- **ThreadPoolExecutor — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **ThreadPoolExecutor (OpenJDK 21 source):** https://github.com/openjdk/jdk21/blob/master/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java
- **ExecutorService — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Executors — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- **ArrayBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **LinkedBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- **SynchronousQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- **RejectedExecutionHandler — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html

**Core takeaway:** `ThreadPoolExecutor` does not jump straight from core to maximum when new tasks arrive. The normal path is **prioritize creating workers below core, prioritize the queue at core, try creating extra workers when the queue cannot accept, and finally delegate to the rejection handler**. To understand it accurately, you must account for **queue type/capacity, shutdown races, worker lifecycle, and overload-handling policy**. A task being admitted, a task having started, and a task having completed are three distinct milestones.

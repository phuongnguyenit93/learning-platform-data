# Work Queue, Worker Pool, and Task Dispatch in Java Concurrency

## 1. The Problem to Solve

Suppose an application receives requests to process reports, send emails, or compute data. Requests can arrive faster than the processing rate. If each request creates a new platform `Thread`, the application easily consumes excessive memory, increases context-switching overhead, and loses control during traffic spikes. If requests are processed directly on the receiving thread, response time and the ability to accept more work suffer.

A common design separates three responsibilities:

1. **Work queue:** stores pending tasks, optionally with a bounded capacity.
2. **Worker pool:** a set of threads that take and execute tasks; the number of workers limits how much work is being processed concurrently.
3. **Task dispatch:** decides which tasks are accepted, whether they are placed into the queue or handed directly to a worker, how overload is handled, and how errors and lifecycle are tracked.

~~~text
Producer(s) -- submit task --> [ Work queue ] -- take --> Worker 1
                                         |-------> Worker 2
                                         |-------> Worker N
                         | full |
                         v
              wait / reject / caller runs / shed load
~~~

A **Task** is the unit of work to be done, usually represented by `Runnable` (no return value) or `Callable<T>` (returns `T` and can throw checked exceptions). A **Worker** is the thread that executes tasks. The **Queue** is the holding area for tasks *that have not started running yet*. In Java, the core APIs live in `java.util.concurrent`: `BlockingQueue`, `Executor`, `ExecutorService`, and `ThreadPoolExecutor`.

This model does not guarantee that all tasks run in the exact order they were enqueued. A FIFO queue guarantees **dequeue order** at the head of the queue (under proper usage), but multiple workers can finish tasks at different times.

## 2. How the Work Queue Coordinates with Workers

### 2.1. Producer–Consumer and the Blocking Principle

In the producer–consumer model:

- **Producers** create tasks and put them into the queue.
- **Consumers/workers** call `take()` to wait for and retrieve a task; when the queue is empty, the thread waits instead of polling continuously.
- When a queue is bounded and full, a producer can wait for space (`put`), wait with a timeout (`offer` with timeout), or fail immediately (`offer` without timeout).
- Workers execute tasks outside the queue retrieval operation. Multiple producers and consumers can use a `BlockingQueue` concurrently without manually adding `synchronized` around every `put`/`take`.

Basic options of `BlockingQueue<E>`:

| Action | Throws exception if unable immediately | Returns status immediately | Blocks indefinitely | Blocks with timeout |
| --- | --- | --- | --- | --- |
| Insert item | `add(e)` | `offer(e)` → `boolean` | `put(e)` | `offer(e, timeout, unit)` |
| Retrieve and remove | `remove()` | `poll()` → item or `null` | `take()` | `poll(timeout, unit)` |
| Examine head only | `element()` | `peek()` | Not available | Not available |

For example, `queue.put(task)` can block the **producer** when the queue is full; this is a simple form of **backpressure**. Do not call `put` on a thread that must not wait long (for example, a thread holding a critical lock) if there is a risk of cascading stalls. `BlockingQueue` does not accept `null` elements; `poll()` returns `null` to indicate no item is available.

Operations on a blocking queue also support memory visibility: actions that occur **before** a thread places an item into the queue *happen-before* actions that occur **after** another thread retrieves/accesses that item through the queue. This is part of the concurrency contract, not an accident of CPU caching.

### 2.2. Choosing a Queue Type

| Queue | Characteristics | When to use | Risks / caveats |
| --- | --- | --- | --- |
| `ArrayBlockingQueue<>(capacity)` | FIFO, fixed capacity | When you want to bound pending tasks and predict memory usage | Producers may block or be rejected when full |
| `LinkedBlockingQueue<>(capacity)` | FIFO, configurable capacity | When you want a bounded queue without requiring a fixed array | If **no capacity is passed**, the bound is `Integer.MAX_VALUE`, which in practice can grow memory unboundedly |
| `SynchronousQueue<>` | Stores no items; transfers directly to a waiting worker | Direct handoff, avoiding queue buildup | If no consumer is ready, `offer` fails immediately; with a pool, this can increase threads or trigger rejection |
| `PriorityBlockingQueue<>` | Ordered by comparator/natural ordering, essentially unbounded | When priority-based processing is needed | Does not preserve FIFO for equal-priority tasks unless you add a sequence number; prone to starvation; no built-in backpressure |
| `DelayQueue<>` | Item can only be taken when its delay has expired, unbounded | Time-delayed tasks | Not a general-purpose pool scheduler; elements must implement `Delayed` |

Using a bounded queue is usually safer for systems with fluctuating traffic. However, **queue capacity is not throughput**: increasing queue length only allows more tasks to wait, it does not make workers process faster.

## 3. Runnable Example: Building a Custom Work Queue with Two Workers

This example illustrates a producer pushing work into an `ArrayBlockingQueue`; two workers loop on `take()` until they receive a termination signal. After all tasks are enqueued, the producer sends **one poison pill per worker** so they exit the loop.

Save as **`WorkQueueDemo.java`** (JDK 17+):

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;

public class WorkQueueDemo {
    private static final int STOP = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        List<Integer> processed = new CopyOnWriteArrayList<>();

        Runnable consumer = () -> {
            try {
                while (true) {
                    int jobId = queue.take();
                    if (jobId == STOP) {
                        return;
                    }
                    processed.add(jobId);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(consumer, "worker-1");
        Thread second = new Thread(consumer, "worker-2");
        first.start();
        second.start();

        for (int id = 1; id <= 4; id++) {
            queue.put(id);
        }

        // Send STOP only after all real jobs have been submitted.
        queue.put(STOP);
        queue.put(STOP);

        first.join();
        second.join();

        processed.sort(Comparator.naturalOrder());
        System.out.println("Processed: " + processed);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 WorkQueueDemo.java
java WorkQueueDemo
~~~

Output:

~~~text
Processed: [1, 2, 3, 4]
~~~

**Explanation:**

1. The queue holds at most two *pending* elements. When full, `put` waits for a worker to take an item.
2. Two workers concurrently take jobs. Therefore, execution/completion order can vary; the program **sorts after `join()`** so stdout is deterministic.
3. `STOP` is added **after** all real jobs; since the queue is FIFO, each worker receives one signal and terminates.
4. `join()` forces `main` to wait for both workers to stop before printing the result.
5. `CopyOnWriteArrayList` is only used for simplicity in a small example; in a system recording results at high frequency, copying the array on every add is very expensive. Typically you would use an appropriate aggregator or `ConcurrentLinkedQueue`.

**Poison pills have limitations:** you need a sentinel that **cannot collide with real data** (here valid jobs only have positive IDs); the number of sentinels and consumers must match. If other producers are still submitting tasks, if a worker dies unexpectedly, or if multiple sources send `STOP`, a more robust queue-closing protocol is required. `BlockingQueue` **has no general `close()` method**; dedicated task pools should generally use `ExecutorService`.

## 4. `Executor` and `ExecutorService`: Submitting Tasks Instead of Managing Threads Manually

At a low level, you can call `new Thread(task).start()`. For continuously arriving tasks, this forces your code to handle creating, managing, cancelling, and tracking each thread. The `Executor` API decouples **task submission** from **task execution**:

~~~java
Executor executor = ...;
executor.execute(() -> doWork());
~~~

This is an **illustrative snippet**, assuming `executor` and `doWork()` are already defined. `ExecutorService` extends `Executor` with `submit(Callable/Runnable)`, `Future`, `shutdown`, `awaitTermination`, and mechanisms for waiting on or cancelling tasks.

| API | Usage | Receiving result or error |
| --- | --- | --- |
| `execute(Runnable)` | Submit a fire-and-forget task, though errors still need to be recorded | Does not return a `Future`; uncaught errors depend on the worker/executor |
| `submit(Runnable)` | Submit a task and track its status | `Future<?>`; `get()` returns `null` on success |
| `submit(Callable<T>)` | Submit a task that returns a result | `Future<T>.get()` retrieves the result; task exceptions are wrapped in `ExecutionException` |
| `Future.cancel(true)` | Request cancellation and optionally interrupt the worker | Cancellation is cooperative; does not guarantee immediate stop |
| `shutdown()` | Stop accepting new tasks, process already-accepted tasks | **Does not wait** for all tasks to finish |
| `awaitTermination(...)` | Wait for the pool to terminate after shutdown | Returns `true` when stopped, `false` on timeout |
| `shutdownNow()` | Attempt to interrupt running tasks and return unstarted tasks | Best-effort; does not guarantee workers stop immediately |

`submit` does not mean "already finished" when the method returns. `execute` and `submit` can also be **rejected immediately upon submission** if the executor is already shut down or resource-constrained. With `Future`, if you **never call `get()`**, an exception inside the task may go unobserved by the caller.

Common factories:

~~~java
ExecutorService fixed = Executors.newFixedThreadPool(4);
ExecutorService single = Executors.newSingleThreadExecutor();
ExecutorService cached = Executors.newCachedThreadPool();

// Use shutdown() / awaitTermination() when finished.
// The lines above illustrate creating executors, not a complete program.
~~~

- `newFixedThreadPool(4)` has four workers at most by design and uses a waiting queue that is effectively **unbounded**; do not treat this as a complete backpressure mechanism.
- `newSingleThreadExecutor()` keeps one worker processing sequentially; it still has a waiting queue that can grow large.
- `newCachedThreadPool()` uses direct handoff and can create many platform threads under continuous load; resource limits must be evaluated.
- In Java 21+, `Executors.newVirtualThreadPerTaskExecutor()` **creates a new virtual thread for each task**, not a pool with a fixed number of virtual threads. To cap concurrency when accessing a database, HTTP service, or other resource, you need a separate limit (such as a semaphore) rather than assuming the executor limits the number of tasks.

Factories are convenient, but they do not always provide the control over queue capacity, thread count, and rejection policy that a system needs. When those parameters matter, use `ThreadPoolExecutor` directly.

## 5. `ThreadPoolExecutor`: Dispatch Rules You Must Know Cold

Common constructor (Java 17+):

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        corePoolSize,
        maximumPoolSize,
        keepAliveTime,
        TimeUnit.MILLISECONDS,
        workQueue,
        threadFactory,
        rejectedExecutionHandler);
~~~

This is a **configuration snippet**; the variable names represent parameters not declared in this excerpt.

Parameters:

- `corePoolSize`: core worker level. If the number of workers is **less than core**, the pool prefers creating a new worker when a task arrives, even if the queue has room (by default, core workers are not pre-started).
- `maximumPoolSize`: maximum number of workers existing in the pool. Most relevant when the queue **cannot accept more tasks**.
- `keepAliveTime`: how long workers *above core* may remain idle before terminating; by default core workers do not time out unless `allowCoreThreadTimeOut(true)` is enabled.
- `workQueue`: where tasks wait once at least `corePoolSize` workers exist; queue capacity directly affects whether the pool scales up toward max.
- `threadFactory`: sets thread name, daemon flag, and uncaught exception handler for platform threads as needed.
- `rejectedExecutionHandler`: handles tasks that cannot be accepted into the pool (including during shutdown).

Decision order when submitting a task to `ThreadPoolExecutor`:

~~~text
Call execute(task)
   |
   +-- running workers < corePoolSize ? --> create a new worker to process task
   |
   +-- otherwise: try offer(task) into workQueue
   |       |
   |       +-- accepted --> task waits for a worker to take it
   |
   +-- queue cannot accept more: workers < maximumPoolSize ?
   |       |
   |       +-- yes --> create an additional worker to run task
   |
   +-- no --> rejectedExecutionHandler
~~~

This is the **conceptual decision flow**. The implementation also checks run/shutdown state and handles thread races to avoid accepting tasks after the executor has stopped.

**Commonly misunderstood consequence:** configuring `core=2, max=8` with an unbounded `LinkedBlockingQueue` usually runs only **2 workers** because the queue keeps accepting tasks; `max=8` does not automatically cause the pool to expand. With `ArrayBlockingQueue<>(100)`, tasks begin entering the queue once two core workers exist; the pool only adds more workers when the queue cannot accept any more. With `SynchronousQueue`, there is no storage for waiting tasks, so the executor attempts to add workers sooner if handoff fails.

### 5.1. Verifiable Example: Full Queue and Task Rejection

The following program creates **1 worker** and a queue with **1 slot**. The first task waits on a `CountDownLatch` so it is guaranteed to occupy the worker; the second task sits in the queue; the third task has no room left and is rejected under `AbortPolicy`. Using latches makes the outcome independent of scheduler speed.

Save as **`PoolRejectionDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolRejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();              // task 1 is holding the worker
            pool.execute(() -> { });      // task 2 is waiting in the queue

            try {
                pool.execute(() -> { });  // task 3 has no slot left
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }

        boolean stopped = pool.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Third rejected: " + rejected);
        System.out.println("Pool stopped: " + stopped);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PoolRejectionDemo.java
java PoolRejectionDemo
~~~

Output when the machine runs normally and the pool stops before the timeout:

~~~text
Third rejected: true
Pool stopped: true
~~~

The worker count, queue slot, and latch ordering are all controlled. `awaitTermination(5, SECONDS)` can return `false` if the JVM is paused or overloaded longer than the timeout; that is why the final line's output is stated conditionally. This section shows that **task dispatch is governed by worker and queue state**, not just by `maximumPoolSize`.

## 6. Rejection Policy Is the Overload Decision

When the pool cannot accept a task, `ThreadPoolExecutor` invokes `RejectedExecutionHandler`. Four built-in policies exist:

| Policy | Behavior | When to consider |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` (default) | When you need to signal overload/rate-limit and must not silently drop tasks |
| `CallerRunsPolicy` | If not shut down, the caller **runs the task itself** | When you want to throttle the producer by making the caller do the work; watch out for latency and blocking the caller |
| `DiscardPolicy` | Drops the task without error | Only for droppable data, with metrics and acceptance of lost work |
| `DiscardOldestPolicy` | Drops the task at the head of the queue and retries submitting the current task | Only when trading priority/losing older tasks is acceptable; easily breaks ordering and business assumptions |

With `CallerRunsPolicy`, when the pool **is already shut down**, the task may be **dropped** according to the policy's contract. Therefore, do not assume this policy always guarantees every task will be processed.

**Real-world backpressure** combines multiple layers: bounded queues, producer/request limits, concurrency limits on downstream calls, timeouts, controlled retries, and explicit overload signals. Simply switching `AbortPolicy` to `CallerRunsPolicy` is not enough if the caller is an event loop or is holding a critical lock.

An example of designing a task admission boundary:

~~~java
// Illustrative snippet: executor, task, and rejectedCounter already exist.
try {
    executor.execute(task);
} catch (RejectedExecutionException rejected) {
    rejectedCounter.incrementAndGet();
    // Report "overloaded" to the sender or persist to a durable mechanism.
}
~~~

This snippet is **not a complete program**; a rejected task cannot be considered "accepted." If the queue only lives in memory, a shutdown or crash can lose pending tasks. When work must not be lost, a separate durable queue/transaction/ack mechanism is required; `BlockingQueue` is not a durable message broker.

## 7. Getting Results: `Callable`, `Future`, and Completion-Order Dispatch

`Runnable` is suitable when no result is needed. `Callable<T>` returns `T` and can throw checked exceptions, so it is typically used with `ExecutorService.submit`. `Future.get()` waits for the result; `ExecutionException` wraps the root cause. If you need to process **whichever task finishes first**, `ExecutorCompletionService` provides a completion queue; call `take()` to retrieve completed `Future`s.

Standalone example **`CompletionDispatchDemo.java`** (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CompletionDispatchDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            ExecutorCompletionService<Integer> completed =
                    new ExecutorCompletionService<>(pool);

            for (int i = 1; i <= 3; i++) {
                int id = i;
                completed.submit(() -> id * id);
            }

            List<Integer> results = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                Future<Integer> future = completed.take();
                results.add(future.get());
            }

            Collections.sort(results);
            System.out.println("Results: " + results);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompletionDispatchDemo.java
java CompletionDispatchDemo
~~~

Stdout:

~~~text
Results: [1, 4, 9]
~~~

`completed.take()` returns `Future`s in **completion order**, which can vary between runs. Only after `sort` is the printed output deterministic. `submit` can throw `RejectedExecutionException` immediately if the pool rejects the task; an accepted task that throws an exception during execution causes `future.get()` to throw `ExecutionException`.

If each task has its own deadline, consider `future.get(timeout, unit)` and `future.cancel(true)`; remember that cancellation is usually interrupt-based and tasks must cooperate. `shutdown()` in `finally` does not wait for termination like `awaitTermination()`, but the example already retrieved all three results, so all submitted work finished before leaving the `try` block.

## 8. Dispatch and Processing Order: FIFO Does Not Mean Sequential Completion

A FIFO queue with two workers can produce a timeline like this:

~~~text
Time          Worker A                  Worker B
t0            takes task 1              takes task 2
t1            task 1 waits for I/O      task 2 finishes computing
t2            still waiting             takes task 3
t3            task 1 finishes           task 3 finishes
Completed:    2, 1, 3  (or another order depending on scheduling)
~~~

Distinctions to keep clear:

- **Enqueue order:** the order in which producers place tasks into the queue. Multiple concurrent producers create a contended order, not automatically matching external wall-clock order.
- **Dequeue/start order:** the order in which workers take/start tasks. A FIFO queue normally preserves item retrieval order, but a worker can be preempted by the scheduler before running the actual task body.
- **Completion order:** the order in which tasks finish; with multiple workers, this cannot be inferred from FIFO.

If operations for the same account/order must run in exact sequence, you can use a **single-thread executor** for a group of work, or **partition by key** into sequential queues/workers. If you need to preserve output order while still processing in parallel, assign sequence numbers and sort/reassemble before emitting results. Both approaches incur waiting overhead; do not apply global serialization if only per-key ordering is needed.

**Task priority** also needs consideration: a priority queue can cause low-priority tasks to wait indefinitely (**starvation**). Aging mechanisms or separate queues are needed if fairness is required. **Task timeouts** must include **time spent in the queue** if the SLA is measured from request receipt, not only execution time after a worker starts.

## 9. Is a Worker Pool Better Suited for CPU-Bound or I/O-Bound Work?

- **CPU-bound:** work primarily consumes CPU; a reasonable starting point is a platform-thread worker count around the number of available CPU cores, then measure against your workload and container limits. Too many workers can increase context switching without increasing throughput.
- **Blocking I/O-bound:** workers spend significant time waiting on network/disk/database. With platform threads, you may need more workers than cores, but other resources like connection pools and memory still cap concurrency.
- **Java 21+ virtual threads:** allow many blocking tasks written in synchronous style without dedicating one platform thread per task; `newVirtualThreadPerTaskExecutor()` does **not** create a fixed-size pool. You still need backpressure or semaphores for downstream resources.
- **Mixed workload:** if CPU-heavy tasks share the same pool as long-waiting I/O tasks, short tasks can be starved of workers. Separate executors/queues can be used by workload type and SLA.

There is no universal `poolSize=16` or `queueCapacity=1000` that fits every system. Size based on **arrival rate**, **service rate**, **queue wait time**, memory per task, downstream limits, and latency targets. If 60 tasks/s arrive on average while all workers combined sustain 40 tasks/s, the backlog grows by roughly **20 tasks/s** while the condition persists. A 100-slot queue will fill very quickly without input throttling (this is an idealized estimate, ignoring variance and initial state).

### Distinguishing the Limits

| Limit | What does it protect? | Where is it configured? |
| --- | --- | --- |
| Worker count | Number of tasks actively running in the worker pool | `corePoolSize`/`maximumPoolSize` |
| Work queue capacity | Number of tasks waiting in the pool | Bounded `BlockingQueue` |
| Downstream concurrency | Number of concurrent connections/calls to DB or external services | `Semaphore`, connection pool, rate limiter |
| Timeout | Maximum wait time to retrieve/complete a task | `Future.get(timeout)` or a dedicated timeout mechanism |
| Admission/rate limit | Number of incoming requests accepted | Throttling logic at the producer/entry point |

Limits must align with one another. For example, if a pool has 100 workers but the database only has 10 connections, adding more workers will not make the database respond faster; extra workers may simply pile up waiting for a connection.

## 10. Lifecycle and Safe Shutdown

**With a custom queue + self-managed workers:** clearly define when producers stop sending, which consumers need termination signals, how pending tasks are drained, and how interrupts and failed tasks are handled. Poison pills fit examples with a single producer that controls termination; multi-producer systems need a careful closing protocol to avoid losing tasks.

**With `ExecutorService`/`ThreadPoolExecutor`:**

1. Stop accepting new tasks at the producer layer.
2. Call `shutdown()`: rejects subsequent tasks while letting already-accepted tasks continue running.
3. Call `awaitTermination(timeout, unit)` to wait for a bounded time.
4. If the timeout expires and stopping is required, call `shutdownNow()`, capture the returned pending tasks, and handle them according to application policy.
5. On `InterruptedException`, trigger appropriate shutdown and restore the interrupt flag (`Thread.currentThread().interrupt()`).

The following Java 17+ pattern is a **standalone method** to place inside a Java class with the corresponding imports:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public static void stopPool(ExecutorService pool) {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                System.err.println("Pool still running");
            }
        }
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

`shutdownNow()` does **not** forcibly kill threads: it attempts to interrupt running tasks and returns the list of unstarted tasks; tasks that ignore interrupts may not stop. `isShutdown()` only indicates that shutdown was requested; `isTerminated()` confirms that all work has completed after shutdown.

A common cause of hangs is a **task inside a pool calling `Future.get()` on another task queued in the same pool**, while all workers are busy waiting. For example, in a single-worker pool: task A submits task B to the same pool and calls `get()` to wait for B; B cannot run because A is occupying the worker. This is **thread starvation deadlock**. Prevent it by designing dependency flows carefully, avoiding cross-blocking on the same pool, using asynchronous composition, or separating executors in a controlled way.

## 11. Performance Monitoring and Operations

For `ThreadPoolExecutor`, several metrics can be observed:

| API/metric | Meaning | Notes |
| --- | --- | --- |
| `getPoolSize()` | Current number of workers in the pool | Not the total task count |
| `getActiveCount()` | Approximate number of workers executing tasks | An **instantaneous estimate** |
| `getQueue().size()` | Current number of waiting tasks | Changes continuously; do not use for synchronization |
| `getCompletedTaskCount()` | Approximate number of completed tasks | Cumulative count, not instantaneous throughput |
| Rejected task count | Number of tasks not accepted | Must be measured via handler/exceptions; note some policies do not throw |
| Queue wait time | From task submission to worker start | Must be measured explicitly; critical for SLAs |
| Task execution time | From execution start to completion | Analyze separately from queue wait time |
| End-to-end latency | From request receipt to result availability | Includes queuing, execution, and result delivery |

Do not infer load solely from queue size at a single point in time. A queue can be empty because there are too many workers, because producers have no work, or because a rejection policy is dropping tasks. Observe **arrival rate, completion rate, latency percentiles, errors, timeouts, CPU usage, heap, and downstream saturation** together.

Scenarios to test:

- **Burst load:** a short traffic spike; verify the queue grows and then drains as expected.
- **Sustained overload:** input exceeds output over a long period; verify controlled rejection/throttling without unbounded memory growth.
- **Slow task:** some tasks hang on I/O; verify timeouts, cancellation, and that not all workers become blocked.
- **Task failure:** a task throws a runtime exception; track errors and ensure unrelated tasks do not disappear.
- **Graceful stop:** stop producers, drain/wait for workers, and verify no accepted tasks remain unprocessed.
- **Ordering/duplicates:** on retries or worker failures, verify idempotency and ordering by business key.

For critical data, design **idempotency keys**, bounded retries, and explicit tracking of accepted/completed state. In-memory `BlockingQueue`/`ThreadPoolExecutor` do not provide transactions, persistence, or exactly-once delivery.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `while (true) { if (!queue.isEmpty()) queue.remove(); }` | Busy-spin; check-then-act is not atomic | Use `take()`/`poll(timeout)` |
| Using an unbounded queue without monitoring | Memory grows when input exceeds serving capacity | Choose a calculated capacity and rejection/backpressure |
| Configuring a large `maxPoolSize` with an unbounded queue | Pool typically never grows past core | Understand dispatch rules before sizing |
| Calling `Future.get()` immediately after each `submit` in a loop | Accidentally serializes work | Submit all first then collect results, or use `CompletionService` |
| Never calling `Future.get()` / not catching task errors | Failures go undetected | Collect `Future`s, log exceptions, decide on retry/compensation |
| Ignoring `InterruptedException` | Tasks fail to cancel properly, shutdown hangs | Stop appropriately and restore the interrupt flag if not fully handled |
| Ignoring `RejectedExecutionException` | Tasks are silently lost | Handle overload at the submission site, record metrics |
| Treating `shutdown()` as immediate stop | Tasks keep running; resources not yet released | Use `awaitTermination()` and handle timeout |
| Workers doing long I/O in a CPU pool | CPU tasks queue unnecessarily | Separate workloads and resources |
| Treating FIFO as completion order | Wrong state when tasks run in parallel | Use sequence numbers/partitioning/result coordination |
| Wrong poison pill count | Consumers hang or tasks remain | Clear closing protocol, one sentinel per worker |
| Treating an in-memory queue as durable | Tasks lost after a crash | Use a durable mechanism when reliability is required |

## 13. Design Decision Summary

- For simple producer–consumer with direct control over queued items: start with a **bounded `BlockingQueue` + worker loops**, and make the shutdown protocol explicit.
- For general-purpose task dispatch and lifecycle management: use **`ExecutorService`**.
- When you need explicit **core/max/queue capacity/rejection** settings: use **`ThreadPoolExecutor`** and test overload behavior before deployment.
- To return results and manage errors: use **`Callable`/`Future`**, or **`ExecutorCompletionService`** for completion order.
- For blocking I/O tasks on Java 21+: consider **virtual threads**, while still bounding concurrent operations against scarce resources.
- For high reliability: explicitly define admission, timeouts, retries, idempotency, persistence, and observability; a pool/queue alone cannot guarantee completion across a JVM crash.

### Official Documentation

- [Java SE 21 — `BlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html) — `put/offer/take/poll` modes, memory consistency, and poison pills.
- [Java SE 21 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — core/queue/max rules, configuration, and rejection.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) — `submit`, `Future`, and shutdown.
- [Java SE 21 — `ExecutorCompletionService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html) — results in completion order.
- [Java SE 21 — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html) — factory methods and virtual-thread-per-task executor.

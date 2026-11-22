# Observability of active count, queue size, and completed tasks in the Java Executor Framework

## 1. Why observe a thread pool?

When using `ExecutorService`, a program delegates tasks to an executor instead of manually creating each `Thread`. However, a running system needs to know: how many workers are currently executing tasks, how many tasks are waiting, how many tasks have finished, whether the pool has reached its limits, and whether processing is slowing down?

With `java.util.concurrent.ThreadPoolExecutor`, three common observations are:

- **`getActiveCount()`:** estimates the number of threads in the pool that are currently **executing tasks**.
- **`getQueue().size()`:** the number of elements currently in the pool's **work queue**, typically tasks waiting to be taken by a worker, **not including currently running tasks**.
- **`getCompletedTaskCount()`:** estimates the total number of tasks that have **completed execution in the pool's workers**, since the executor was created.

These metrics help detect backlogs, monitor load, and support capacity tuning. However, they are not an **atomic snapshot of the entire executor**, not a "successful" business outcome, and **cannot be used on their own to reliably decide** whether a subsequent `execute()`/`submit()` call will be accepted.

This lesson belongs to the general Java concurrency **Executor Framework** topic, illustrated with Java 17+ and JDK APIs, without being tied to any specific framework or application configuration.

## 2. Understand the task lifecycle to read metrics accurately

A task in `ThreadPoolExecutor` can go through the following stages:

```text
Application submits task
       |
       v
Executor decides
       |
       +--> Worker picks up and executes immediately
       |
       +--> Work queue waits for an available worker
       |
       +--> Rejection handler (when it cannot be accepted per policy)
                    |
                    +--> Throw exception / discard task / run on caller / other
                            
Task runs in worker --> Finishes run/call --> Completed-task accounting
```

**Do not conflate the three measurements:**

| Metric | What it measures | What it does not measure |
| --- | --- | --- |
| `getActiveCount()` | Estimate of workers currently executing tasks | Not necessarily the number of threads using CPU; tasks waiting on I/O may still count as active |
| `getQueue().size()` | Number of tasks still in the work queue at the time of sampling | Does not include tasks already taken from the queue by a worker; not queue wait latency |
| `getCompletedTaskCount()` | Estimate of tasks that have finished processing in the pool | Does not indicate how many tasks succeeded, failed, or how many results callers have received |
| `getPoolSize()` | Current number of worker threads in the pool | Not the number of truly active workers |
| `getLargestPoolSize()` | Largest number of workers that have ever simultaneously been in the pool | Not the configured maximum threshold or current load level |
| `getTaskCount()` | Estimate of tasks that have ever been scheduled for execution by the pool | Not the number of completed user requests or truly successful tasks |

In particular, `getCompletedTaskCount()` should not be labeled on a dashboard as "successful jobs". A task can terminate with an exception, be cancelled, or finish execution while failing at the business level. `submit()` typically wraps a task in a `FutureTask`: the exception is stored in the `Future` so that a caller calling `get()` receives an `ExecutionException`; the task can still be counted as completed by the executor.

### Does "Active" include workers waiting inside a task?

Yes, it can. If a worker **is running `Runnable.run()`** but is blocked on another `queue.take()`, an I/O query, or waiting for a lock, it is still executing the executor's task in the worker-management sense. `getActiveCount()` is not CPU utilization. A pool thread that is **idle waiting to take the next task** is not counted as active according to this metric's definition.

Therefore, active count should be correlated with queue length, task execution duration, queue latency, and CPU utilization, rather than looking at a single number.

## 3. Where to read the metrics from?

`ExecutorService` is a general interface and **does not have** the `getActiveCount()`, `getCompletedTaskCount()`, or `getQueue()` methods. These observation methods are part of the **`ThreadPoolExecutor`** API.

Instantiate an explicitly configured pool directly:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                         // corePoolSize
        4,                         // maximumPoolSize
        30, TimeUnit.SECONDS,      // keepAliveTime
        new ArrayBlockingQueue<>(20)
);

int active = executor.getActiveCount();
int queued = executor.getQueue().size();
long completed = executor.getCompletedTaskCount();
```

This is a **snippet**; you need to import `ThreadPoolExecutor`, `ArrayBlockingQueue`, and `TimeUnit`, and shut down the executor when done. Do not cast an arbitrary `ExecutorService` to `ThreadPoolExecutor` if you do not know the implementation: it could be a wrapper, another executor, or an implementation that does not support these metrics.

`Executors.newFixedThreadPool(n)` in the JDK typically creates a `ThreadPoolExecutor` underneath, but the API declares it as returning `ExecutorService`; if your code needs implementation-specific metrics, it is best to **hold a direct reference to `ThreadPoolExecutor` at creation time** or expose a dedicated monitoring interface, rather than downcasting arbitrarily.

`Executors.newWorkStealingPool()` is based on a different model; `ForkJoinPool` has its own set of metrics such as `getActiveThreadCount()` and `getQueuedTaskCount()`. Do not apply `ThreadPoolExecutor`'s interpretation of queue and active counts verbatim to every executor.

## 4. Java 17+: example of observing a pool with a controlled schedule

To understand the measurements, let's create a pool with **2 workers** and a work queue holding at most **3 tasks**. All five tasks share a waiting gate. Two workers enter the gate, while the remaining three tasks sit in the queue; `main` reads the metrics and only then opens the gate so they can finish.

Create the file `ThreadPoolMetricsDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ThreadPoolMetricsDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(3)
        );

        CountDownLatch twoStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable task = () -> {
            twoStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            for (int i = 0; i < 5; i++) {
                pool.execute(task);
            }

            twoStarted.await();

            System.out.println("Submitted: 5");
            System.out.println("Queue size before release: "
                    + pool.getQueue().size());
            System.out.println("Active estimate before release: "
                    + pool.getActiveCount());
            System.out.println("Completed estimate before release: "
                    + pool.getCompletedTaskCount());
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Final queue size: "
                + pool.getQueue().size());
        System.out.println("Final active estimate: "
                + pool.getActiveCount());
        System.out.println("Final completed estimate: "
                + pool.getCompletedTaskCount());
    }
}
```

Compile and run:

```bash
javac ThreadPoolMetricsDemo.java
java ThreadPoolMetricsDemo
```

Illustrative output under normal execution conditions:

```text
Submitted: 5
Queue size before release: 3
Active estimate before release: 2
Completed estimate before release: 0
Final queue size: 0
Final active estimate: 0
Final completed estimate: 5
```

**Analysis and guarantee limits:**

1. The pool has `corePoolSize = maximumPoolSize = 2`. The first two tasks are executed by workers and wait on `release`; the remaining three tasks fit into the queue of capacity 3. There is no sixth task, so no rejection is needed.
2. `twoStarted.await()` confirms that **two tasks have entered `run()`**; because the gate has not opened yet, these two workers cannot finish normally. The remaining three tasks are in the queue. This is why the snapshot before opening the gate typically shows active ≈ 2, queued = 3, completed ≈ 0.
3. `getActiveCount()` and `getCompletedTaskCount()` are documented as **approximate values**. Do not use this sample output to write assertions that every implementation and every concurrent sampling must yield exact absolute numbers.
4. When `release.countDown()` runs, the two workers finish their current tasks and pick up the waiting tasks. `shutdown()` rejects new tasks but **continues running already-accepted tasks** according to the normal shutdown mechanism.
5. After `awaitTermination()` returns true, all workers have stopped and the queue has been drained in this example. Because all five tasks completed normally, the final snapshot is typically active 0, queue 0, completed 5.
6. `finally` ensures the gate is opened and shutdown begins even if `main` is interrupted while waiting on the gate, avoiding leaving workers stuck because of metric-measurement code.

The key point of the example is **separating the sampling points before and after tasks complete**. In a real application, calling the three getters does not capture a unified transaction; the values may come from slightly different points in time while the pool is changing.

## 5. Reliability: ThreadPoolExecutor metrics are snapshots/estimates

The Javadoc describes `getActiveCount()`, `getCompletedTaskCount()`, and `getTaskCount()` with **approximate** semantics. `getQueue().size()` reflects the number of elements visible in the queue at the moment of reading, but tasks may be taken or added immediately afterward; how `size()` behaves also depends on the queue implementation.

This leads to three rules:

- **Do not use snapshots as concurrency invariants:** for example, `if (pool.getQueue().size() < 100) pool.execute(task)` still has a race condition between reading the size and submitting. Other threads can fill the queue in between.
- **Do not derive exact results by adding/subtracting metrics read at different times:** `getTaskCount() - getCompletedTaskCount() - getActiveCount()` is not guaranteed to equal `queue.size()` due to non-atomic sampling and specific counting mechanics.
- **Do not wait for state via tight polling when a proper waiting API exists:** instead of looping `while (getActiveCount() > 0)`, use `shutdown()` + `awaitTermination(timeout, unit)` to wait for the pool to finish; instead of manually waiting for completed count to increase, use `Future.get()`, `CountDownLatch`, or `invokeAll()` where appropriate.

These metrics are still very useful for dashboards, trends, SLOs, and anomaly detection. "Approximate" does not mean "useless"; it means they are suitable for **observability**, not for thread synchronization or making atomic task-acceptance decisions.

### Which metrics reflect "bottlenecks"?

For example:

- **Active near the current worker count, queue continuously growing:** task arrival rate may exceed processing capacity, or many tasks are stuck in I/O/locks.
- **Low active count, nearly empty queue:** the pool may be idle, or upstream may not be sending work; correlate with incoming request rate.
- **Completed count rising slowly, queue growing:** processing throughput may have degraded. If active remains high, inspect task execution time, lock contention, and downstream I/O.
- **Queue always empty but high latency:** tasks may be blocked at a step outside the executor, inside the task itself, or at request intake; queue metrics do not cover the entire pipeline.

Do not conclude "deadlock" or "thread starvation" from a single snapshot. Also inspect thread dumps, JFR, task execution times, queue type, and dependency health.

## 6. Properly understanding queue size: bounded, unbounded, and handoff

`ThreadPoolExecutor` can use different types of work queues; the semantics of `size()` change depending on the type:

| Queue type | Characteristics | How to interpret |
| --- | --- | --- |
| `ArrayBlockingQueue<>(capacity)` | Fixed capacity, elements are stored in the queue | `size()` is the stored backlog, which can be compared against capacity |
| `LinkedBlockingQueue<>(capacity)` | Bounded if capacity is explicitly passed | Monitor backlog, keep cost/memory in mind |
| Default `LinkedBlockingQueue<>()` | Very large capacity (effectively unbounded for practical purposes) | The queue can grow significantly and consume memory before rejection occurs due to being full |
| `SynchronousQueue` | Direct handoff, **no capacity to store elements** | `size()` is typically always 0, **which does not mean there is no load pressure** |
| `PriorityBlockingQueue` | Ordered by priority, no fixed bound by default | `size()` does not indicate priority levels, task age, or deadlines |
| `ScheduledThreadPoolExecutor` queue | Can hold delayed/not-yet-due tasks and periodic tasks | `size()` is not simply the number of normal requests waiting for a worker |

### Note when a pool has a very large queue

In `ThreadPoolExecutor`, after reaching `corePoolSize`, if the queue can still accept tasks, the executor may **prefer putting tasks into the queue** rather than creating additional workers up to `maximumPoolSize`. With an effectively unbounded `LinkedBlockingQueue`, `maximumPoolSize` often **does not take effect** the way beginners expect. A growing queue is a warning about backlog and memory risk, not necessarily a reflection that the pool has scaled up to its maximum workers.

With `SynchronousQueue`, because tasks are not stored in the queue, `getQueue().size()` does not describe backlog. When no worker is available to accept the handoff and no more workers can be added, submissions may be rejected according to the rejection policy. You need to observe rejections, latency, and request sources as well.

### Do not arbitrarily modify `getQueue()`

`getQueue()` returns the queue that the executor is using. The Javadoc notes that this access is primarily intended for **monitoring and debugging**; using it to arbitrarily add/remove elements interferes with the executor's task-management mechanism. Do not call `pool.getQueue().clear()` as a way to "shed load" or `queue.add(runnable)` instead of `execute()`.

If you need to proactively remove a queued task, look at supported APIs such as `remove(Runnable)`/`purge()` according to their contracts, or manage cancellation and ownership in a wrapping layer. Cancelling a task does not necessarily mean the queue shrinks immediately for every executor.

## 7. How is a completed task different from a "successful task"?

`getCompletedTaskCount()` tracks tasks that **have finished executing in the pool**, not business success. A `Runnable` can throw an exception; a `Callable` submitted via `submit()` can end in an error; a task can be cancelled or terminate early.

### Java 17+: a failed task is still counted as completed

Create the file `CompletedIsNotSuccess.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;

public class CompletedIsNotSuccess {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>()
        );

        boolean businessSuccess = true;
        try {
            Future<?> result = pool.submit(() -> {
                throw new IllegalStateException("business failed");
            });

            try {
                result.get();
            } catch (ExecutionException e) {
                businessSuccess = false;
                System.out.println("Failure observed via Future: "
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Business success: " + businessSuccess);
        System.out.println("Completed tasks: "
                + pool.getCompletedTaskCount());
    }
}
```

Compile and run:

```bash
javac CompletedIsNotSuccess.java
java CompletedIsNotSuccess
```

Output:

```text
Failure observed via Future: IllegalStateException
Business success: false
Completed tasks: 1
```

The `submit` call wraps the work in a `Future`. `result.get()` throws an `ExecutionException` whose cause is the business error; the executor still executed and finished one task, so the completed count incremented. If you only have the completed count without checking the `Future` result or a separate metric, a dashboard might show "1 completed" and **give no indication of 1 failure**.

### Relationship between `execute()`, `submit()`, and exceptions

- `execute(Runnable)` typically passes the `Runnable` directly to a worker. An uncaught exception can pass through `afterExecute(Runnable, Throwable)` as a `Throwable` and cause the worker to terminate abnormally.
- `submit(Runnable/Callable)` typically uses `FutureTask`, keeping the exception **inside the Future** so that `get()` reports an `ExecutionException`. In the `afterExecute` hook, the `Throwable` argument may be null **even when the task failed**.
- `Future.cancel(...)` affects the cancellation state of the Future, but not every cancellation means the worker has finished immediately. Do not use the completed count to infer that cancellation has completed or that side effects have been rolled back.

If you want to count successes/failures, define what **business success** means and measure it directly—for example, a `Callable` wrapper that records the outcome after the task returns a result or throws an exception. Do not label `ThreadPoolExecutor`'s worker-management metric as business success.

## 8. Rejection policies cause "submitted" and "completed" metrics to diverge

When neither the pool nor the queue can accept more tasks, `RejectedExecutionHandler` decides how to handle it. Some standard policies:

- `AbortPolicy`: throws `RejectedExecutionException` to the caller.
- `CallerRunsPolicy`: if the executor is not shut down, runs the task **directly on the thread calling `execute`**, creating backpressure; if shut down, it may discard the task.
- `DiscardPolicy`: silently discards the task without reporting an error.
- `DiscardOldestPolicy`: drops the oldest waiting task and retries submission; requires special care with deadlines/priorities/retries.

**Consequence:** a task can be executed on the **caller thread** rather than a pool worker. That task is not completed "by a pool worker", so you should not expect `getCompletedTaskCount()` to reflect all work processed by both callers and workers.

### Java 17+: CallerRunsPolicy causes counter divergence

Create the file `CallerRunsMetrics.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CallerRunsMetrics {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger callerExecuted = new AtomicInteger();
        Thread submitter = Thread.currentThread();

        try {
            pool.execute(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            entered.await();           // Worker 1 is holding the execution slot.
            pool.execute(() -> { });   // Task 2 is in the full queue.
            pool.execute(() -> {       // Task 3 runs in the caller.
                if (Thread.currentThread() == submitter) {
                    callerExecuted.incrementAndGet();
                }
            });

            System.out.println("Executed in caller: "
                    + callerExecuted.get());
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Completed by pool workers: "
                + pool.getCompletedTaskCount());
    }
}
```

Run:

```bash
javac CallerRunsMetrics.java
java CallerRunsMetrics
```

Output:

```text
Executed in caller: 1
Completed by pool workers: 2
```

Because the pool has only one worker and the queue holds one element, when the third task is submitted, both the worker and the queue are busy. `CallerRunsPolicy` executes this task directly on the caller. The other two tasks run in the worker and complete after `release` opens. From a business perspective, **three tasks were executed**; from the pool's metrics, only **two tasks were completed by workers**.

**Key dashboard takeaway:** the counts of requests **submitted**, **accepted**, **run in caller**, **rejected/discarded**, **business-failed**, and **business-succeeded** can all differ. Have separate counters if you need to measure the entire pipeline, rather than inferring everything from the completed count.

## 9. Designing a practical pool observability dashboard

A useful monitoring dashboard typically has two groups:

### A. Executor state metrics (gauge/snapshot)

| Metric | Type | Question answered |
| --- | --- | --- |
| `getActiveCount()` | Approximate gauge | How many workers are currently busy executing tasks? |
| `getPoolSize()` | Gauge | How many workers does the pool currently have? |
| `getCorePoolSize()`/`getMaximumPoolSize()` | Configuration | What are the design thresholds? |
| `getQueue().size()` | Gauge | How many elements are still waiting in the queue? |
| Queue remaining capacity, if supported by the queue | Gauge | How many slots remain in a bounded queue? |
| `isShutdown()`, `isTerminating()`, `isTerminated()` | Lifecycle state | Is the pool accepting work or shutting down? |

Gauges change over time. Sampling too infrequently can miss short spikes; sampling too frequently adds overhead and still does not make the data atomic.

### B. Cumulative or business metrics (counter/histogram)

| Metric | Source | Why it is needed |
| --- | --- | --- |
| `getCompletedTaskCount()` | Executor, **cumulative estimate** | Worker execution throughput trend |
| `getTaskCount()` | Executor, **cumulative estimate** | Total tasks managed by the pool according to the implementation's counting |
| Submitted/accepted/rejected | Instrumentation at submission/rejection points | Detect overload and policy behavior |
| Caller-runs count | Instrumentation in `CallerRunsPolicy` or wrapper | See backpressure costing the caller time |
| Business success/failure/cancel | Task wrapper or Future result | Distinguish business outcome from "executed" |
| Queue wait duration | Enqueue timestamp and execution start timestamp | Detect backlog via latency, not just size |
| Execution duration | Task start and end timestamps | Identify slow tasks, I/O, and contention |
| End-to-end latency | At the request/workflow boundary | See queue wait, task run, retries, and response together |

**Throughput estimation formula** over a measurement window:

```text
completed_rate_per_second
    = (completed_at_t2 - completed_at_t1) / elapsed_seconds
```

Use elapsed time from a monotonic clock (`System.nanoTime()`) to measure the sampling interval; do not use wall-clock time to compute elapsed duration unless necessary. Because the completed count is an estimate and snapshots are not atomic, the rate computed from the difference should be treated as an **estimate**, especially over short sampling intervals or when the pool is resizing/shutting down.

Do not directly compare counters from **two different executor instances** or after a pool has been recreated: counters reset to 0, so deltas can be wrong if lifecycle changes are not accounted for.

## 10. Periodic sampling without blocking workers

One implementation approach is to use a scheduler/monitor **separate from the worker pool**, reading metrics periodically and exporting them to logs or a metrics system. Do not let the saturated pool itself be the sole entity responsible for measuring its own state, because when its queue is full, the monitoring task can also be delayed.

Structural example:

```java
// Illustrative snippet: pool is a ThreadPoolExecutor, sampler
// is an initialized ScheduledExecutorService.
ScheduledFuture<?> monitor = sampler.scheduleAtFixedRate(
        () -> {
            int active = pool.getActiveCount();
            int queued = pool.getQueue().size();
            long completed = pool.getCompletedTaskCount();

            recordMetrics(active, queued, completed);
        },
        0, 1, TimeUnit.SECONDS
);

// When stopping monitoring:
monitor.cancel(false);
sampler.shutdown();
```

This is a **snippet**, not a standalone Java file: `recordMetrics` and the variables are assumed to be defined. Do not perform slow or indefinitely blocking logging/network calls inside the sampling callback. If one sampler run takes too long or throws an unhandled exception, the sampling schedule can be affected. `scheduleAtFixedRate` does not guarantee exact per-second sampling under all scheduling conditions.

A production monitoring setup should:

1. Label pools by function (e.g., IO, CPU, background groups), without embedding personal information in metric tags.
2. Record active state, pool size, queue length, completed, rejected, and latency along with timestamps.
3. Avoid tagging by task ID/request ID with extremely high cardinality.
4. Handle exporter/metrics backend errors independently of task execution.
5. When the pool is shutting down, continue sampling long enough to observe draining, then stop the sampler cleanly according to its lifecycle.
6. Alert on **sustained trends over time**, not on a single noisy snapshot.

### `beforeExecute`/`afterExecute` hooks

You can subclass `ThreadPoolExecutor` and override `beforeExecute(Thread,Runnable)`/`afterExecute(Runnable,Throwable)` to measure worker lifecycle. However, these hooks run on the task execution path, so measurement code must be lightweight, thread-safe, and must not break executor logic.

- `beforeExecute` can record the start timestamp, but if using a shared map, IDs and cleanup must be managed.
- `afterExecute` is called when the task's `run()` finishes in the worker. `Throwable` may be null for `FutureTask` even when user code fails: you must inspect the `Future` result or instrument the wrapper directly if you want accurate success/failure tracking.
- If a hook itself throws an exception, the worker may terminate abnormally and processing can be affected.
- `CallerRunsPolicy` can execute a task on the caller **without going through worker hooks**, so hook-only metrics also do not cover all task executions.

For typical needs, wrapping `Runnable`/`Callable` right at the submission boundary to measure duration, status, and errors is clearer than trying to interpret completed count as business success.

## 11. Pattern for instrumenting outcomes at the task boundary

Below is a **standalone runnable** example for tracking business success/failure with separate counters while comparing against the completed count. Create the file `ExecutorOutcomeDemo.java`:

```java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.LongAdder;

public class ExecutorOutcomeDemo {
    private static final LongAdder succeeded = new LongAdder();
    private static final LongAdder failed = new LongAdder();

    static Runnable tracked(Runnable work) {
        return () -> {
            try {
                work.run();
                succeeded.increment();
            } catch (RuntimeException | Error e) {
                failed.increment();
                throw e;
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>()
        );

        try {
            Future<?> ok = pool.submit(tracked(() -> { }));
            Future<?> bad = pool.submit(tracked(() -> {
                throw new IllegalArgumentException("invalid input");
            }));

            for (Future<?> future : new Future<?>[] {ok, bad}) {
                try {
                    future.get();
                } catch (ExecutionException ignored) {
                    // The error was already counted in the wrapper; the caller knows the task failed.
                }
            }
        } catch (ExecutionException e) {
            throw new AssertionError(e);
        } finally {
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Succeeded: " + succeeded.sum());
        System.out.println("Failed: " + failed.sum());
        System.out.println("Completed by pool: "
                + pool.getCompletedTaskCount());
    }
}
```

Run:

```bash
javac ExecutorOutcomeDemo.java
java ExecutorOutcomeDemo
```

Expected output:

```text
Succeeded: 1
Failed: 1
Completed by pool: 2
```

**Note on the example:** `LongAdder.sum()` is well suited for observing counters updated by multiple threads, though during concurrent updates the returned sum is not an atomic snapshot. Here we call `sum()` **after the pool has terminated**, so the final result is stable. In applications that need to track multiple error types, categorize exceptions at the business layer rather than distinguishing success/failure solely by a single `RuntimeException`.

*Detail on checked exceptions:* `Runnable.run()` does not declare checked exceptions. For a `Callable` with checked exceptions, the wrapper needs to declare/propagate them appropriately and count errors accordingly. In the example above, tasks only throw unchecked exceptions.

## 12. When are metrics skewed or missing?

### Task cancelled before a worker runs it

If a `Future` is cancelled while still in the queue, the user code wrapper may never have run at all. The `FutureTask` or queue entry may still be present until cleaned up or taken by a worker according to policy. `getQueue().size()` and the completed count **do not** automatically provide the number of tasks cancelled before execution.

### Long-running or hung tasks

`getActiveCount()` can stay continuously high while the completed count barely increases. This could be a legitimate long-running task or a task blocked on I/O/locks. Measure execution duration and inspect thread dumps/JFR; do not immediately assume deadlock.

### Rejected tasks

A task rejected by `AbortPolicy` may never have entered the queue or a worker. It does not mean the completed count should increase. Separate counters are needed right at the submission boundary and in the rejection handler, alongside retry policy tracking.

### Tasks running in the caller

`CallerRunsPolicy` can cause throughput to be dominated by the time the caller is blocked; the pool's active metric does not reflect the caller running the task. Track both caller-run count and submit latency.

### Periodic tasks

`ScheduledThreadPoolExecutor` has periodic tasks that can run multiple times from a single registration, and its queue can hold delayed tasks. Do not interpret `getCompletedTaskCount()` of a periodic executor as the number of business records processed, nor compare its queue size directly with a normal pool without considering scheduler semantics.

### Pool shutdown

`shutdown()` allows already-accepted tasks to finish normally while accepting no new tasks. `shutdownNow()` attempts to interrupt running tasks and returns the list of waiting tasks that had not started, **without guaranteeing** that running threads/tasks stop immediately. After shutdown, active/queue/completed metrics can still change during the drain phase. Use `awaitTermination()` to wait for the pool to terminate within a timeout rather than only watching the active count.

## 13. Using metrics to tune a pool: dos and don'ts

**Dos:**

- Monitor active count, queue size, task latency, rejections, and throughput on the same timeline.
- Use a bounded queue when you need to limit backlog and memory; account for worker capacity and rejection strategy.
- Distinguish CPU-bound, I/O-bound, and resource-waiting tasks; configure pools according to workload.
- Alert when the queue grows persistently, wait times increase, or rejections occur continuously.
- Compare results before/after changing `corePoolSize`, `maximumPoolSize`, queue, and rejection policy via benchmarks/real load.

**Don'ts:**

- Do not use `if (getActiveCount() < max) execute(...)` for atomic coordination; state changes immediately after reading.
- Do not use `getQueue().size() == 0` to conclude that all tasks are done; workers may still be running.
- Do not rely on `completed == submitted` if there are rejections, caller-run tasks, cancellations, or tasks submitted over multiple intervals.
- Do not use `getLargestPoolSize()` as the current active worker count.
- Do not confuse `getPoolSize()` with `getActiveCount()`; idle workers are still in the pool.
- Do not call `getQueue().clear()` or manually enqueue tasks to "optimize" the executor based on a snapshot.
- Do not let blocking I/O in a metrics exporter degrade the throughput of the pool itself.
- Do not use a single measurement point to conclude the optimal thread count; consider CPU, I/O, task duration, memory, latency, and contention.

## 14. Checklist for implementing Executor Framework observability

1. **Verify the executor implementation:** is it actually `ThreadPoolExecutor`, or an `ExecutorService` wrapper/`ForkJoinPool`/scheduled executor?
2. **Define metric meanings:** active = workers executing tasks, queued = elements waiting, completed = tasks that finished executing in the pool, not business success.
3. **Distinguish gauges and counters:** active/queue are snapshots; completed/task counts are approximate cumulative values.
4. **Document queue type/capacity:** bounded, unbounded, handoff, or delayed queues give `size()` different meanings.
5. **Do not use getters for atomic decisions:** `execute`/`submit` and the rejection policy themselves determine task acceptance.
6. **Instrument submitted/accepted/rejected/caller-runs** when the system needs accurate statistics on task paths.
7. **Count business outcomes independently:** success, failure, retry, and cancel must be determined at the task-management layer or Future.
8. **Measure latency:** queue wait time, execution duration, end-to-end response, and tail latency help explain queue length.
9. **Sample with a lightweight, separate pool when possible:** avoid having the exporter put backpressure on the system.
10. **Account for shutdown/restart:** counters reset when instances change; snapshots still change during draining.
11. **Test edge cases:** idle pool, saturation, failed tasks, caller-runs, rejection, cancellation, shutdown.
12. **Do not trust a single snapshot:** verify trends with JFR/thread dumps and realistic workloads.

**Conclusion:** `ThreadPoolExecutor` provides useful measurements such as `getActiveCount()`, `getQueue().size()`, and `getCompletedTaskCount()` to understand load levels and worker progress. However, they are **observations of changing state**, not synchronization operations or business success counts. Combine them with rejection metrics, task wait/execution times, and separate outcome statistics to get an accurate picture of the Executor Framework.
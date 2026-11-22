# Choosing a Custom Executor to Manage Load and Avoid Deadlocks in CompletableFuture

## 1. Why Does CompletableFuture Need a Controlled Executor?

`CompletableFuture<T>` describes an asynchronous computation and its dependent processing steps. APIs such as `supplyAsync`, `thenApplyAsync`, `thenComposeAsync`, `thenAcceptAsync`, and `thenRunAsync` can dispatch callbacks to an **Executor**. However, asynchrony does not make CPU, threads, database connections, or network bandwidth infinite. If requests arrive faster than they can be processed, work will **queue up, be rejected, or consume additional resources**.

A **custom executor** is an executor created and configured by the application for a specific workload instead of using the default for every callback. The goals are:

- **Load isolation:** blocking I/O tasks do not exhaust workers dedicated to CPU computation.
- **Resource bounding:** the number of workers and the amount of queued work stay within a reasonable budget.
- **Overload detection:** when workers and the queue are full, there is an explicit admission/rejection policy.
- **Avoiding deadlock-prone dependencies:** tasks do not hold a worker and then `join()` work that can only run on that same worker.
- **Lifecycle management:** knowing who owns the executor, when it stops accepting tasks, and when all dependent stages have actually completed.

This article discusses standard Java Concurrency only, independent of any framework.

## 2. Which Executor Executes CompletableFuture?

| API | Execution policy |
|---|---|
| `CompletableFuture.supplyAsync(supplier)` | Dispatches using the default async execution facility |
| `CompletableFuture.runAsync(runnable)` | Same, for a `Runnable` that returns no value |
| `future.thenApply(fn)` | **Non-Async**; the callback may run on the thread that completes the source stage or another thread calling completion |
| `future.thenApplyAsync(fn)` | Uses the default async executor |
| `future.thenApplyAsync(fn, executor)` | Dispatches the callback to the specified executor |
| `future.thenComposeAsync(fn, executor)` | Dispatches the function returning a new `CompletionStage` via the specified executor |
| `future.thenAcceptAsync(action, executor)` | Executes the `Consumer` via the specified executor |
| `future.thenRunAsync(action, executor)` | Executes the `Runnable` via the specified executor |

With standard `CompletableFuture`, async methods without an explicit executor typically use **`ForkJoinPool.commonPool()`**, provided the common pool supports a parallelism of at least two; otherwise, the implementation may use a dedicated thread per async task. Subclasses can customize `defaultExecutor()`, so do not assume a single pool name is guaranteed across all environments.

**The common pool is a shared resource across the JVM.** If one component submits many blocking callbacks to it, work from other parts of the application can also be affected. Fork/Join work stealing is useful for divide-and-conquer computation, but it does not make a waiting HTTP/database call finish any sooner.

**Non-Async does not mean it always runs on the thread that registers the callback.** If the source is already complete, the callback may execute immediately upon registration; if the source completes later, the thread completing the source may execute the callback. A `thenApply` containing blocking I/O can therefore inadvertently tie up the worker that just finished the previous task.

## 3. When Should You Use a Custom Executor?

Use a dedicated executor when you want to:

1. **Isolate CPU and blocking I/O**, or separate batch/background tasks from flows with strict SLOs.
2. **Set a bounded queue** and define behavior when saturated instead of holding an unbounded backlog in memory.
3. **Enforce a rejection policy** and report overload accurately.
4. **Name workers and observe** `activeCount`, queue depth, latency, and rejections.
5. **Manage lifecycle** per component with orderly shutdown capability.

Do not create a separate executor for each Future or request. Each executor consumes resources and requires shutdown. Typically, you should **reuse a small number of executors by workload type and ownership**, rather than multiplying pools endlessly to mask load issues.

Also avoid mechanically applying `thenApplyAsync` to every transformation taking a few microseconds: switching queues has overhead. For very short, non-blocking callbacks, non-Async can be reasonable if its thread execution policy is acceptable.

## 4. ThreadPoolExecutor: Parameters That Govern Load

Core configuration:

~~~java
// ILLUSTRATIVE CODE; variables must be defined beforehand.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        corePoolSize,
        maximumPoolSize,
        keepAliveTime,
        TimeUnit.SECONDS,
        workQueue,
        threadFactory,
        rejectedExecutionHandler
);
~~~

| Parameter | Role |
|---|---|
| `corePoolSize` | Target number of core workers |
| `maximumPoolSize` | Maximum worker limit |
| `keepAliveTime` | Idle time before workers above core can terminate |
| `BlockingQueue<Runnable> workQueue` | Holds tasks not yet picked up by a worker |
| `ThreadFactory` | Names/configures threads for diagnostics |
| `RejectedExecutionHandler` | Reaction when the pool is saturated or already shut down |

Common task-acceptance rules of `ThreadPoolExecutor`:

1. If the current worker count is below core, the pool can create a new worker.
2. Once core workers exist, the pool generally prefers **queuing the task**.
3. If the queue cannot accept the task, the pool can scale workers up to maximum.
4. If neither a worker can be created nor the task queued, the task is **rejected** according to the handler.

This explains an important trap: **`maximumPoolSize` may have virtually no effect if the queue is unbounded**. The queue always accepts waiting tasks, so the pool never needs to expand beyond core via the saturated-queue path.

~~~text
core=2, max=6, queue capacity=10

Fewer than 2 workers -> can add worker
At 2 workers, queue has space -> enqueue task
Queue full, fewer than 6 workers -> can expand
Queue full, at 6 workers -> rejection policy
~~~

`Executors.newFixedThreadPool(n)` in the standard JDK implementation uses a `LinkedBlockingQueue` with a very large capacity (`Integer.MAX_VALUE`). While it fixes the worker count at `n`, **it does not bound the number of waiting tasks to a useful operational budget**. If the arrival rate exceeds the processing rate over time, the backlog and heap/GC/queue wait will continue to grow.

## 5. Choosing a Bounded Queue and Handling Overload

A clearly bounded model:

`running ≤ maximumPoolSize`

`queued ≤ queueCapacity`

However, **total unfinished load** also includes tasks in other pools, retries, timers, requests waiting for permits, or dependent futures not yet scheduled. You need to account for the entire pipeline, not just a single queue.

| Rejection policy | Behavior when saturated | Risk |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | The caller/boundary must handle overload errors |
| `CallerRunsPolicy` | Executes the rejected task on the **thread calling execute** if the pool is not shut down | May block the caller, event loop, or request thread |
| `DiscardPolicy` | Drops the rejected task | May cause a Future to never complete |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submission | Lost work or broken ordering semantics |

**Never silently ignore rejections.** If work is accepted into the pipeline but never runs, a caller calling `join()` may wait forever. For pipelines that require an explicit outcome, `AbortPolicy` paired with an overload-handling boundary is usually easier to verify than discard policies.

**CallerRunsPolicy** can provide backpressure feedback: the submitter has to execute the callback itself and therefore cannot keep submitting as fast as before. However, when saturated, a `thenApplyAsync` callback may **not run on an executor worker**, but instead on the thread executing the submit; you must consider whether that thread needs to stay responsive.

When the executor **is already shut down**, `CallerRunsPolicy` discards the task instead of running it on the caller. Therefore, it is not a mechanism that guarantees every dependent Future will be resolved.

## 6. Classifying CPU-Bound and Blocking I/O

**CPU-bound:** callbacks spend most of their time computing. The useful worker count is typically close to the effective CPU count after accounting for quotas/containers, SMT, and other pools. Increasing workers beyond CPU count does not automatically increase throughput; it can increase context switching and cache contention.

**Blocking I/O:** callbacks spend significant time waiting on synchronous HTTP/database/file APIs. You may need more workers than CPUs so that not all workers are blocked at once. However, downstream concurrency ceilings, connection counts, and memory limits still apply.

Reference heuristic:

`N_threads ≈ N_CPU × targetCPUUtilization × (1 + waitTime / computeTime)`.

**Use this only as an initial measurement starting point**, not a formula that fits every system. When a downstream service allows 20 connections, 200 I/O workers cannot safely keep 200 connections active beyond that quota.

A pipeline can be split as:

~~~text
Incoming requests
       |
admission / bounded queue
       |
I/O executor: blocking dependency, timeout
       |
CPU executor: parse/transform/computation
       |
result / completion callback
~~~

Splitting pools **does not automatically create backpressure**: producers can still submit unboundedly, or stages on a downstream pool can still be rejected. Overload must be designed explicitly at every boundary.

## 7. Java 17 Example: Routing I/O and CPU to Two Executors

This example uses two pools, each with one worker, a queue capacity of 2, and distinct thread names. There is no real I/O; simulated data is used to verify the API and thread routing.

Save the file **CustomExecutorRoutingDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CustomExecutorRoutingDemo {
    private static ThreadPoolExecutor pool(String threadName) {
        return new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                task -> new Thread(task, threadName),
                new ThreadPoolExecutor.AbortPolicy());
    }

    public static void main(String[] args) {
        ThreadPoolExecutor io = pool("io-worker");
        ThreadPoolExecutor cpu = pool("cpu-worker");
        AtomicReference<String> ioThread = new AtomicReference<>();
        AtomicReference<String> cpuThread = new AtomicReference<>();

        try {
            CompletableFuture<String> pipeline =
                    CompletableFuture.supplyAsync(() -> {
                        ioThread.set(Thread.currentThread().getName());
                        return "  java  ";
                    }, io).thenApplyAsync(value -> {
                        cpuThread.set(Thread.currentThread().getName());
                        return value.trim().toUpperCase(Locale.ROOT);
                    }, cpu);

            System.out.println("result=" + pipeline.join());
            System.out.println("io thread=" + ioThread.get());
            System.out.println("cpu thread=" + cpuThread.get());
        } finally {
            io.shutdown();
            cpu.shutdown();
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac CustomExecutorRoutingDemo.java
java CustomExecutorRoutingDemo
~~~

Stdout:

~~~text
result=JAVA
io thread=io-worker
cpu thread=cpu-worker
~~~

`supplyAsync(..., io)` runs on `io-worker`; `thenApplyAsync(..., cpu)` runs on `cpu-worker`. `main` only prints after `pipeline.join()`, so it does not depend on the scheduling order of the two workers.

**Do not copy pool size 1 and queue 2 into production**: these are demo values. Real applications require benchmarking and policies for deadlines, rejection, shutdown, I/O timeouts, and metrics.

## 8. Choosing thenApply or thenApplyAsync?

If `ioFuture.thenApply(parse)` registers a non-Async callback, `parse` may run directly on the thread that completes `ioFuture`. If parsing is heavy, the callback occupies the I/O worker, forcing the next I/O task to wait.

~~~java
// ILLUSTRATIVE CODE: ioFuture is a CompletableFuture<String>
// and cpuExecutor is a configured Executor.
CompletableFuture<Result> converted =
        ioFuture.thenApplyAsync(value -> parse(value), cpuExecutor);
~~~

The snippet above **is not a standalone program**; `Result`, `parse`, `ioFuture`, and `cpuExecutor` are placeholder symbols.

However, **`thenApplyAsync` does not mean "faster"**: it incurs the cost of submitting the callback to the executor and can be rejected when saturated. For extremely short transformations, `thenApply` can be more efficient and simpler.

If the callback returns another `CompletionStage<U>`, use `thenCompose`/`thenComposeAsync` to flatten it, avoiding a nested `CompletableFuture<CompletableFuture<U>>` from `thenApply`.

## 9. Java 17 Example: Executor Rejecting a Callback on Overload

We create a pool with **1 worker and queue capacity 1**. The worker waits on a latch; another task already occupies the queue slot; the third async callback must be rejected.

**Important CompletableFuture detail:** in JDK 17, with `thenApplyAsync` on an already-completed source and an executor using `AbortPolicy`, the registration call **returns a dependent stage that completed exceptionally**. Therefore, you must inspect the **returned Future**, not only catch `RejectedExecutionException` around the `thenApplyAsync` call.

Save **BoundedRejectionDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedRejectionDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            pool.execute(() -> { }); // Fill the queue.
            System.out.println("queue full="
                    + (pool.getQueue().remainingCapacity() == 0));

            CompletableFuture<Integer> stage =
                    CompletableFuture.completedFuture(2)
                    .thenApplyAsync(value -> value * 10, pool);
            System.out.println("stage done=" + stage.isDone());
            try {
                stage.join();
            } catch (CompletionException failure) {
                System.out.println("rejection cause="
                        + failure.getCause().getClass().getSimpleName());
            }
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

Run command:

~~~bash
javac BoundedRejectionDemo.java
java BoundedRejectionDemo
~~~

Stdout on JDK 17:

~~~text
queue full=true
stage done=true
rejection cause=RejectedExecutionException
~~~

**Explanation:** `ThreadPoolExecutor.execute` is rejected by `AbortPolicy`; in CompletableFuture's dependent-completion path, the error is recorded on the callback's Future. `stage.isDone()` being true **does not mean success**, because `stage.join()` throws `CompletionException` with cause `RejectedExecutionException`.

In other situations, a rejected task may surface at the caller of the submission API or on the thread completing the source. The system should handle both **synchronous rejection** and **exceptional completion of the Future**, rather than assuming every call always throws in a single place.

## 10. Java 17 Example: CallerRunsPolicy Can Run the Callback on the Caller

Switch the policy to `CallerRunsPolicy`. When the pool is saturated, the third callback runs immediately on the thread calling `execute`, which here is `main`. Calling `thenApplyAsync` does not guarantee execution on a pool worker if the rejection policy intervenes.

Save **CallerRunsStageDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsStageDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ranOnCaller = new AtomicBoolean();
        Thread caller = Thread.currentThread();

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            pool.execute(() -> { }); // Queue is full.
            CompletableFuture<Integer> stage =
                    CompletableFuture.completedFuture(2)
                    .thenApplyAsync(value -> {
                        ranOnCaller.set(Thread.currentThread() == caller);
                        return value * 10;
                    }, pool);

            System.out.println("ran on caller=" + ranOnCaller.get());
            System.out.println("result=" + stage.join());
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
javac CallerRunsStageDemo.java
java CallerRunsStageDemo
~~~

Stdout:

~~~text
ran on caller=true
result=20
~~~

**Caution:** if the caller thread is a request-handling, UI, or event-loop thread, a slow CPU/I/O callback can degrade that thread's responsiveness. `CallerRunsPolicy` can serve as simple backpressure for producers that are allowed to slow down, not as a default choice everywhere.

## 11. Deadlock From Joining Within the Same Single-Thread Executor

A dangerous bug: the sole worker runs task A, and then **waits for task B, which can only run on that same executor**.

~~~java
// INCORRECT EXAMPLE; DO NOT RUN: oneWorker is a single-thread ExecutorService.
CompletableFuture<Integer> outer = CompletableFuture.supplyAsync(() -> {
    CompletableFuture<Integer> inner =
            CompletableFuture.supplyAsync(() -> 42, oneWorker);
    return inner.join(); // Holds the sole worker and waits for inner.
}, oneWorker);
~~~

While A holds the worker and calls `join`, B sits in the queue unable to run; A cannot exit until B finishes. This is a **thread starvation deadlock**. Increasing the queue capacity does not fix it because there is no free worker to pick up B.

Instead of blocking inside the callback, use **composition**:

~~~java
// CORRECT EXAMPLE: oneWorker is already declared and active.
CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> 21, oneWorker)
        .thenCompose(value ->
                CompletableFuture.supplyAsync(
                        () -> value * 2, oneWorker));
~~~

`thenCompose` establishes an asynchronous dependency without calling `join()` inside the preceding worker. `main` or a boundary layer can wait for the final result when needed.

### Java 17 Example: Compose Instead of Holding the Worker

Save **SingleWorkerCompositionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SingleWorkerCompositionDemo {
    public static void main(String[] args) {
        ExecutorService oneWorker = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(() -> 21, oneWorker)
                    .thenCompose(value ->
                            CompletableFuture.supplyAsync(
                                    () -> value * 2, oneWorker));

            System.out.println("result=" + result.join());
            System.out.println("done=" + result.isDone());
        } finally {
            oneWorker.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac SingleWorkerCompositionDemo.java
java SingleWorkerCompositionDemo
~~~

Stdout:

~~~text
result=42
done=true
~~~

**There is no `join()` inside the stage callback**; after computing 21, the worker thread is free to run the newly created subtask. `main` waits at the boundary without occupying a pool worker. This avoids the specific dependency deadlock analyzed above, though it does not prevent other lock or I/O deadlocks.

## 12. Deadlocks Can Still Happen With Multiple Pools

Splitting into `ioPool` and `cpuPool` is not enough if:

- `ioPool` workers collectively `join()` tasks on `cpuPool`, while `cpuPool` workers `join()` tasks that need `ioPool`;
- a task holds a lock/permit and waits for a callback that needs the same resource;
- tasks A and B acquire locks in opposite orders, A→B and B→A;
- a running task blocks a worker while the task that emits its completion signal sits behind it in the queue;
- `CallerRunsPolicy` causes a callback to run on a thread holding a lock or handling critical events.

The solution is not "just add more threads," but to **map out the dependency graph**, avoid synchronous wait cycles, use `thenCompose`/`thenCombine`/`allOf` with their intended semantics, and set deadlines if blocking is unavoidable.

**Do not call `get()` or `join()` in every stage just to "be sure it's done."** These methods can block workers and defeat the purpose of composition. If you need to synchronize with a traditional caller, wait only at an appropriate boundary.

## 13. Managing Upstream Backpressure

A custom executor with a bounded queue creates a **saturation detection point**, but backpressure requires upstream **to change its behavior**. Options include:

- **Fail-fast:** decline the task and return a clear overload status.
- **Bounded wait:** wait for capacity up to an overall deadline if the admission API supports it; do not block critical threads indefinitely.
- **CallerRuns:** slow down the producer by executing immediately, only when the submitting thread is allowed to bear the load.
- **Intentional drop/coalesce:** suitable for metrics or non-critical updates; **never** arbitrarily drop transactional work.
- **Durable persistence:** if work must survive restarts, a separate durable storage mechanism is needed; a `ThreadPoolExecutor` queue lives only in memory.

Do not retry indefinitely as soon as the executor rejects: a retry storm increases load at the exact moment the system is full. Use a retry budget, backoff with jitter where appropriate, and ensure idempotency for side effects.

If the queue is large and there are no rejections, wait latency increases before errors appear. Therefore, measure **queue wait**, **end-to-end latency**, and throughput—not just success rate.

## 14. Downstream Concurrency and Timeouts

Limiting the executor does not necessarily limit all outbound requests: a callback can initiate other async I/O calls and return immediately, allowing more in-flight downstream requests than there are workers.

A `Semaphore` at the boundary of a finite resource or a connection pool with an appropriate concurrency limit manages **in-flight requests** independently of worker/queue counts. Be sure to release the permit exactly once after the work actually finishes, even when the Future completes exceptionally.

**`CompletableFuture.orTimeout` does not guarantee stopping a background task.** It can complete the Future with a `TimeoutException` while the blocking work continues running. Similarly, `CompletableFuture.cancel(true)` does not use that boolean to forcibly interrupt the worker. Apply timeouts at the HTTP/database layer, enforce overall deadlines, and use cooperative cancellation when the dependency supports it.

In Java 21+, virtual threads reduce the cost of managing many blocking tasks in certain workloads, but **they do not increase CPU, database connections, or quotas**. Even with a virtual-thread-per-task executor, in-flight/downstream limits are still necessary. The examples here are kept compatible with JDK 17.

## 15. How to Size Pools and Queues

There is no single formula that fits every problem. A practical process:

1. **Measure the workload:** CPU time, I/O wait time, downstream latency, throughput, and concurrent requests.
2. **Bound by downstream:** connection counts, API rate/in-flight quotas, and memory may be lower than the desired thread count.
3. **Size the CPU pool** around effective CPUs and benchmark across multiple sizes.
4. **Size the blocking I/O pool** based on wait-to-compute ratio and downstream ceilings; do not multiply workers endlessly.
5. **Size the queue capacity** based on burst-absorption needs and latency budgets, not just available heap.
6. **Choose an observable rejection policy** suited to the business logic with a single place responsible for handling errors.
7. **Load test under saturation**, recording p50/p95/p99 queue wait, end-to-end latency, CPU, GC, rejections, and recovery speed.
8. **Test shutdown** while source stages are still pending and async callbacks have not yet been submitted.

Heuristic for blocking I/O in some models:

`threads ≈ CPUs × targetCPUUtilization × (1 + waitTime/computeTime)`.

This is a starting point to measure from, not a production default.

In steady state, Little's Law for a well-defined queue:

`L = λ × W`

`L` is the **average number of waiting tasks**, `λ` is the queue throughput, and `W` is the average queue wait time. It does not guarantee P99 or automatically compute appropriate capacity during unstable overload periods.

### Metrics to Monitor

| Group | Examples |
|---|---|
| Worker | `getActiveCount()`, `getPoolSize()`, completed task count |
| Queue | queue size, remaining capacity, waiting task age |
| Admission | rejection rate, timeouts, retries, drops |
| Latency | queue wait, callback duration, end-to-end p95/p99 |
| Downstream | in-flight count, connection saturation, I/O timeouts |
| Liveness | workers blocked in `join/get`, lock contention, pending stages |
| Shutdown | incomplete pipelines, executor terminated, escalation count |

`size()`, `remainingCapacity()`, or active count are typically snapshots/approximations for monitoring, **not atomic reservation operations**. Do not read that the queue has space and assume the next submission is guaranteed to succeed.

## 16. Proper Lifecycle and Shutdown

An executor must have a clear owner. If multiple components share an executor, a non-owning component **must not shut it down**, as that can cause another component's tasks to be rejected.

Shutdown procedure:

1. **Stop admission** of new root requests/tasks.
2. Track live pipelines, including `thenApplyAsync` callbacks **not yet scheduled** because their source stage is still pending.
3. Intentionally complete or cancel in-flight pipelines, avoiding shutting down the executor before dependent callbacks are submitted.
4. Call `shutdown()`: rejects new tasks and lets already-accepted tasks continue per contract; `shutdown()` **does not wait**.
5. Call `awaitTermination(timeout, unit)` on a coordinating thread outside the workers that must exit.
6. Upon timeout, consider `shutdownNow()`, wait boundedly again, and log cases that did not stop. Interruption **is not a guaranteed kill**.
7. Close connections/clients/dependent resources only when no tasks are still using them, or with a safe cleanup policy.

**Important trap with CompletableFuture:** an async callback may have been **registered** without yet being submitted to the executor. If the executor shuts down in the meantime, the dependent callback can fail when the source completes later. Track the **entire chain**, not just the source Future.

If `awaitTermination` throws `InterruptedException`, typically propagate it or restore the interrupt flag if caught for local handling; do not swallow it and keep waiting indefinitely.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Letting all blocking callbacks use the common pool | Contention for shared workers, reduced throughput | Dedicated pool for I/O and downstream limits |
| Performing long blocking I/O in `thenApply` | May tie up the thread completing the source | Use an async stage and appropriate executor |
| Using `newFixedThreadPool` thinking the queue is bounded | Uncontrolled backlog growth | Use a bounded `ThreadPoolExecutor` |
| Increasing max pool size while keeping an unbounded queue | Pool may not scale up as expected | Redesign queue and sizing |
| Ignoring the Future from a rejected async callback | Pipeline loses its result or error goes unhandled | Handle overload at the boundary and exceptional stages |
| Catching errors only at `thenApplyAsync` registration | Returned Future may already be completed exceptionally | Keep the Future and handle `join/get/whenComplete` |
| Using `DiscardPolicy` for tasks needing completion | Future may wait forever | Never silently drop work someone is awaiting |
| Using `CallerRunsPolicy` on latency-sensitive threads | Long callbacks block the caller itself | Define overload policies per thread type |
| Single worker calling `join()` on a task in the same pool | Thread starvation deadlock | Use `thenCompose` or decouple dependencies |
| Assuming `TimeoutException` means the background task stopped | May still consume resources and cause side effects | I/O timeouts, cooperative cancellation |
| Creating a new pool per request | Thread overhead, hard to shut down | Reuse pools by workload |
| Shutting down the executor before the chain finishes | Dependent async stages may be rejected | Manage ownership and the entire pipeline |
| Using queue depth as an atomic admission check | Race between check and submit | Let the executor handle admission/rejection |

## 18. Checklist and Conclusion

Before deploying, answer:

1. Is this callback CPU-bound, blocking I/O, or a short non-blocking operation?
2. Is `Async` needed, or can non-Async be used safely?
3. Which pool owns the work queue; what are the specific core/max/queue capacity values?
4. When the pool is full, will work be rejected, wait, run on caller, drop, or be persisted durably?
5. Does the caller handle both **exceptions inside the Future** and **exceptions on submission**?
6. Does any stage hold a worker and then `join/get` a task that needs that same worker?
7. Are downstream in-flight limits, timeouts, deadlines, and retry budgets in place?
8. Are both source and dependent stages tracked before shutting down the executor?
9. Have saturation, rejection, callback failure, timeout, and shutdown been load-tested?
10. Are queue wait, active workers, rejections, and p95/p99 latency metrics available for tuning?

**Conclusion:** choosing a custom executor for `CompletableFuture` is about defining **resource boundaries, admission mechanisms, queuing, and liveness**, not just naming threads. Separate CPU and I/O when needed, use bounded queues and observable rejection policies, avoid blocking `join` inside workers that depend on the same pool, and manage the full lifecycle of dependent stages.

## 19. Java SE Documentation

- [CompletableFuture – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [ThreadPoolExecutor – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [ExecutorService – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)

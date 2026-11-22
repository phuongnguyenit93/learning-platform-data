# Building an Executor with a Bounded Queue and Rejection Policy in Java

## 1. Practical Problem: Avoiding Unbounded Queue Growth

Suppose a Java process receives many file-processing requests. Each request takes about 200 ms of CPU time. If you keep accepting requests and placing them into an unbounded queue, whenever the arrival rate exceeds the processing rate over a sustained period, the number of waiting tasks will grow: wait times become long, many objects are retained on the heap, GC pressure increases, and eventually resources may be exhausted.

A `ThreadPoolExecutor` with a **bounded queue** (a queue with a fixed capacity limit) makes the work-admission capacity explicit:

- At most how many workers actually process tasks concurrently?
- At most how many tasks have been accepted but have not yet started?
- When all workers are busy and the queue is full, should the executor **reject**, **push the work onto the calling thread itself**, or execute a custom policy?
- When shutting down the executor, what happens to running tasks, queued tasks, and newly submitted tasks?

The practical goal is to build an executor in **Java SE 17+**, create a reproducible overload scenario, verify the rejection policy, understand how to choose limits, and clean up resources. This is general Java concurrency knowledge; no container or framework is required.

## 2. Architecture and the Path of a Task

You can create a `ThreadPoolExecutor` via its constructor:

```java
// Configuration illustration, not a standalone program.
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                         // corePoolSize
        4,                         // maximumPoolSize
        30L, TimeUnit.SECONDS,     // keepAliveTime
        new ArrayBlockingQueue<>(8), // workQueue: at most 8 waiting tasks
        new ThreadPoolExecutor.AbortPolicy());
```

Meaning of each component:

| Component | Meaning and Constraints |
|---|---|
| `corePoolSize` | Target baseline number of workers; when tasks arrive, the pool typically creates new workers up to the core threshold (unless specially configured). |
| `maximumPoolSize` | Maximum number of concurrent workers the executor may create; must be `>= corePoolSize`. |
| `keepAliveTime` | Duration that workers **beyond core** are allowed to remain idle before exiting (by default, core workers do not time out unless `allowCoreThreadTimeOut(true)` is enabled). |
| `workQueue` | Holds tasks that have been **accepted but not yet started**; `ArrayBlockingQueue<>(capacity)` has a fixed capacity. |
| `ThreadFactory` | Optional factory for creating workers, naming them, configuring threads, and aiding diagnostics. |
| `RejectedExecutionHandler` | Policy applied when a task cannot be accepted (due to resource saturation or because the executor has been shut down). |

For a running `ThreadPoolExecutor`, the task-admission sequence is essentially:

1. If the current number of workers is **less than `corePoolSize`**, try to create a new worker to run the task.
2. If enough core workers already exist, **try to insert the task into the queue**.
3. If the queue cannot accept it (for example, it is full), try to create additional workers **up to `maximumPoolSize`**.
4. If no more workers can be added and the queue cannot accept the task either, invoke `RejectedExecutionHandler`.

```text
execute(task)
    |
    +-- workers < corePoolSize ? -- yes --> create worker + run
    |                                   |
    no                                  v
    |
    +-- queue.offer(task) succeeds ? -- yes --> accepted into queue
    |                               
    no
    |
    +-- workers < maximumPoolSize ? -- yes --> create additional worker
    |
    no
    |
    +-- rejectedExecution(task, executor)
```

The diagram is a behavioral model; the implementation also handles shutdown states and races among enqueueing, worker creation, and pool shutdown. In particular, **the queue is tried before growing the worker count beyond core**: do not assume a configuration of `core=2, max=8` will immediately have 8 threads when 8 tasks arrive.

Example with `core=2`, `max=4`, queue capacity 3, where all tasks block their worker:

| Number of Submitted Tasks | Ideal Distribution While All Earlier Tasks Remain Busy |
|---:|---|
| 1–2 | Up to 2 core workers are created to run tasks. |
| 3–5 | Both workers remain busy; 3 tasks sit in the queue. |
| 6–7 | Queue is full; up to 2 additional workers are created, totaling 4 workers. |
| 8 onward | Pool has 4 workers and queue holds 3: rejection begins. |

This table assumes no task completes before the next task is submitted and there is no shutdown or thread-factory failure.

## 3. What Does a Bounded Queue Solve, and What Does It Not Solve?

`new ArrayBlockingQueue<Runnable>(k)` limits **k waiting tasks in the queue**. It does not by itself limit the number of incoming external requests, the number of objects held inside each task, the number of threads in other systems, or the amount of memory retained by in-flight results.

If a pool has `maximumPoolSize=4`, queue capacity 8, and every worker is busy, the number of accepted, uncompleted tasks at one point can be approximately **4 running + 8 waiting = 12** (excluding completed tasks whose results have not yet been reclaimed elsewhere). This is the executor's *admission* bound under simple assumptions, not a fixed memory-usage guarantee.

Common queue choices:

| Queue | Key Characteristics |
|---|---|
| `ArrayBlockingQueue<>(capacity)` | Hard bound; array with a fixed number of slots; FIFO order; supports optional fairness for queue operations, though that does not create a complete FIFO guarantee across all threads/tasks in the system. |
| `LinkedBlockingQueue<>(capacity)` | Can also be bounded if an explicit capacity is passed; allocates a node on enqueue. The no-arg capacity constructor uses `Integer.MAX_VALUE`, which in practice can grow excessively large. |
| `SynchronousQueue<>()` | Stores no waiting tasks; direct handoff between producer and worker; when no worker is available, the executor may need to create workers up to max or reject. |
| `PriorityBlockingQueue<>()` | Inherently has no useful element-count bound via its constructor capacity; do not use it as a bounded queue merely because it accepts an initial capacity parameter. |

When using `Executors.newFixedThreadPool(n)`, the default internal queue is a `LinkedBlockingQueue` that is effectively unbounded for normal workloads. If the requirement is a **bounded queue with explicit rejection**, construct `ThreadPoolExecutor` directly.

## 4. Rejection Policy: Deciding Under Saturation

The built-in handlers of `ThreadPoolExecutor`:

| Policy | When the Executor Is Running and Saturated | Risks / Usage |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` on the task-submitting thread. | Suitable when the caller can return an overload response, perform bounded retries, or route to another mechanism. |
| `CallerRunsPolicy` | The thread calling `execute` runs the task **synchronously** if the executor is not shut down. | Applies backpressure to the caller, but can slow down the caller, hold locks, or alter where thread-local/context is used. If the executor is shut down, this policy drops the task without running it. |
| `DiscardPolicy` | Silently drops the task without throwing an error. | Can lose work silently; with `submit`, the returned `Future` may never complete. |
| `DiscardOldestPolicy` | Attempts to drop the task at the **head of the queue**, then retries `execute` if the executor is not shut down. | Can discard older unexecuted work; with `submit`, an older `Future` may remain stuck. Do not use when ordering/no-data-loss is required or when queue/policy configuration can cause endless retries. |

The policy is only part of the application contract: you must explicitly decide what the caller does when a task is not accepted, whether to retry, and avoid tight retry loops that worsen an already overloaded system. No policy by itself guarantees "zero lost work" if the process crashes or if tasks have non-idempotent side effects.

### When to Choose Which?

- **Need explicit overload signaling:** typically start with `AbortPolicy`, record rejections, and handle them at the call boundary.
- **Caller can tolerate executing inline to throttle submission:** consider `CallerRunsPolicy`, but only when the calling thread is allowed to execute that kind of task, has appropriate timeouts, and will not deadlock.
- **Data may be dropped under a documented policy:** consider dropping with clear metrics; silent-drop policies are inappropriate for critical work.
- **Need custom business behavior:** implement a `RejectedExecutionHandler` that inspects the executor state and throws an informative exception, or routes to another designed and tested handling path.

## 5. Complete Java 17 Example: Filling the Queue and Verifying Rejection

The following program contains two practical tests. We intentionally hold workers using a `CountDownLatch` to deterministically observe when the pool is full, without relying on `Thread.sleep()` or machine speed.

**File:** `BoundedExecutorExercise.java`

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class BoundedExecutorExercise {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void abortPolicyExample() throws Exception {
        // 2 workers, 2 queue slots, no scaling beyond 2 workers.
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> a = pool.submit(() -> {
                started.countDown();
                release.await();
                return "A";
            });
            Future<String> b = pool.submit(() -> {
                started.countDown();
                release.await();
                return "B";
            });

            // Only submit further tasks once both workers have entered their tasks.
            check(started.await(5, TimeUnit.SECONDS),
                    "Workers did not start");

            Future<String> c = pool.submit(() -> "C");
            Future<String> d = pool.submit(() -> "D");

            // A/B are holding both workers; C/D must be in the queue.
            check(pool.getQueue().size() == 2,
                    "Expected two queued tasks");

            boolean rejected = false;
            try {
                pool.submit(() -> "E"); // 5th task: out of capacity.
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            check(rejected, "Expected rejection");

            System.out.println("abort: queued=2");
            System.out.println("abort: rejected=true");

            release.countDown();
            String result = a.get(5, TimeUnit.SECONDS)
                    + b.get(5, TimeUnit.SECONDS)
                    + c.get(5, TimeUnit.SECONDS)
                    + d.get(5, TimeUnit.SECONDS);
            check("ABCD".equals(result), "Missing accepted task");
            System.out.println("abort: results=" + result);

            pool.shutdown();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "Executor did not terminate");
            System.out.println("abort: terminated=true");
        } finally {
            release.countDown(); // Release workers if an assertion fails.
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void callerRunsExample() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread caller = Thread.currentThread();
        AtomicBoolean executedByCaller = new AtomicBoolean(false);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            check(started.await(5, TimeUnit.SECONDS),
                    "Worker did not start");

            // Worker is busy; the second task takes the queue slot.
            pool.execute(() -> { });
            check(pool.getQueue().size() == 1,
                    "Expected one queued task");

            // Third task: both pool and queue are full, runs on caller.
            pool.execute(() -> executedByCaller.set(
                    Thread.currentThread() == caller));
            check(executedByCaller.get(), "Caller did not run task");
            System.out.println("caller-runs: on-caller=true");

            release.countDown();
            pool.shutdown();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "Executor did not terminate");
            System.out.println("caller-runs: terminated=true");
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        abortPolicyExample();
        callerRunsExample();
    }
}
```

Compile and run:

```bash
javac BoundedExecutorExercise.java
java BoundedExecutorExercise
```

**Exact stdout if all assertions succeed:**

```text
abort: queued=2
abort: rejected=true
abort: results=ABCD
abort: terminated=true
caller-runs: on-caller=true
caller-runs: terminated=true
```

The two workers may finish A or B in either order. The output remains deterministic because string concatenation calls `get()` in the order A, B, C, D, and there are no competing `println()` calls inside the tasks. That `CallerRunsPolicy` runs the third task on the main thread is verified by directly comparing `Thread.currentThread()` with `caller`, rather than merely inspecting the thread name.

**Test conditions:** `started.await` confirms the workers have entered their tasks; `release` remains closed so workers cannot pick up queued tasks. Therefore, the rejection and caller-runs results are stable across machines of different speeds. The 5-second timeout is a guard so the test fails in finite time if the environment cannot create workers; it is not a timing guarantee in the executor contract.

## 6. Deep Dive into the Program Output

### 6.1. Why Was the Fifth Task Rejected?

In `abortPolicyExample()`:
1. A and B start running and both wait on a latch.
2. C and D are accepted and sit in the `ArrayBlockingQueue` of capacity 2.
3. `maximumPoolSize = 2`: the pool cannot add a third worker.
4. E cannot fit into the queue; `AbortPolicy` throws `RejectedExecutionException` **immediately on the submitting thread**.
5. After `release.countDown()`, the workers complete A/B and continue taking C/D from the queue. All four `Future` instances complete normally.

**Rejection does not mean the executor has been shut down.** At step 4, the pool is still active: it rejects due to overload. If space frees up in the queue later, subsequent submissions can be accepted again. Distinguish `pool.isShutdown()` from point-in-time overload.

### 6.2. Why Is `CallerRunsPolicy` a Coarse Backpressure Mechanism?

In `callerRunsExample()`:
1. The single worker is blocked.
2. The one-slot queue is full.
3. The caller submits the third task and **must execute it itself** before `execute` returns.

In a production program, if the third task takes 300 ms, the submitting thread also spends roughly that much time instead of continuing to push tasks into the pool. This can slow down the producer, acting as a form of **feedback/backpressure**. However, because the task executes on the caller, it can also cause deadlock if the caller holds a lock the task needs, introduce unexpected latency on a sensitive thread, or cause thread-local/context discrepancies.

**Important constraint:** Java does not guarantee that `CallerRunsPolicy` enforces a precise rate limit. It is only a fallback mechanism under saturation; if the pool is already shut down, this policy neither runs the task nor throws an exception by default.

### 6.3. `execute()` and `submit()` Have Different Consequences When Dropping Tasks

`execute(Runnable)` does not return a `Future`. `submit(...)` wraps the task in a future so the caller can query its status and result. With `AbortPolicy`, both submission paths receive `RejectedExecutionException` immediately upon rejection.

With `DiscardPolicy`, `submit` can return a `Future` that is never executed and never completes; an untimed `future.get()` can block forever. With `DiscardOldestPolicy`, an older task evicted from the queue may also have a pending `Future`. Therefore, task-dropping policies require an error/cancellation strategy for callers that were issued a `Future`.

When writing a custom `RejectedExecutionHandler`, do not accidentally "swallow" a rejection and return as if it succeeded when callers rely on a `Future` or need to know whether the task was accepted.

## 7. Custom Rejection Handler for Observing Overload

A `RejectedExecutionHandler` receives both the rejected task and the current executor. The following pattern is an **illustrative configuration snippet**, placed in code with the appropriate imports declared:

```java
AtomicLong rejectedCount = new AtomicLong();

RejectedExecutionHandler handler = (task, executor) -> {
    rejectedCount.incrementAndGet();

    // Distinguish pool shutdown from a running but saturated pool.
    String reason = executor.isShutdown()
            ? "executor is shutdown"
            : "executor queue and workers are saturated";

    throw new RejectedExecutionException(reason);
};
```

Required imports: `java.util.concurrent.RejectedExecutionHandler`, `java.util.concurrent.RejectedExecutionException`, `java.util.concurrent.atomic.AtomicLong`. Replace `new ThreadPoolExecutor.AbortPolicy()` with `handler` in the constructor.

Because the handler runs on the thread calling `execute` and on the rejection path, keep it fast: do not perform heavy work, do not perform unbounded retries, and do not recursively call `execute` back onto the same saturated pool. The `rejectedCount` metric counts rejection occurrences, which is not necessarily equal to the number of failed business requests if a single request attempts multiple submissions.

Additional metrics you can expose:
- `getActiveCount()`: approximate number of threads actively executing tasks.
- `getPoolSize()` and `getLargestPoolSize()`: current and peak worker counts.
- `getQueue().size()` and `getQueue().remainingCapacity()`: queue snapshot.
- `getCompletedTaskCount()` and `getTaskCount()`: approximate statistics; do not use them as strict assertions under concurrent updates.

These are operational snapshots, **not synchronization mechanisms**. For example, a test writing `while (pool.getActiveCount() != 2) { }` both burns CPU and has races. Use `CountDownLatch` to control state; use metrics for observation.

## 8. Designing Queue and Thread Limits Based on Reality

There is no single `core/max/capacity` tuple that is optimal for every application. You must measure arrival rate, service time, per-task size, CPU/I/O utilization, and latency targets. How to reason about it:

1. **Identify the workload:** Is the task CPU-bound, I/O-bound, or mixed? Is input bursty? How long are tasks at higher percentiles?
2. **Set worker limits:** CPU-bound tasks are typically limited by core count and contention; I/O-waiting tasks may benefit from more threads but remain constrained by external resources. `availableProcessors()` is only a reference point, not a mandatory formula.
3. **Set a bounded queue:** A capacity of 50 does not mean a maximum wait time of 50 ms. If one worker processes 5 tasks/s, 50 queued tasks can create significant wait times; measure actual queue depth and latency.
4. **Choose a rejection policy:** Overload must be surfaced to the caller or follow a consistent drop/retry policy. If the caller must not block, avoid using `CallerRunsPolicy` indiscriminately.
5. **Apply deadlines:** An accepted task can still wait a long time; handle `Future.get(timeout)`, I/O timeouts, and appropriate cancellation. A `Future.get` timeout does not automatically cancel the task.
6. **Load test:** Verify worker counts, queue depth, rejection rate, wait time, latency, and resource usage when input exceeds processing capacity.

### A Simple Capacity Estimate

Suppose each task takes an average of 100 ms of pure CPU time and 4 cores are genuinely available to the application. In an ideal model, 4 workers can process about `4 / 0.1 = 40 tasks/s`. If producers continuously submit 100 tasks/s, the backlog grows by roughly 60 tasks/s until the queue fills and the system rejects or slows down.

The figure of 40 tasks/s is only an **ideal-condition estimate**, not a benchmark. Real runtimes have overhead, GC, variance in task duration, and multiple sources of contention. Increasing the queue from 100 to 10,000 does not create new processing capacity; it mainly increases the number of accepted tasks and wait time.

**Little's law**, `L = λ × W` (for a stable system with consistent measurement), relates the average number of tasks in the system `L`, the average completion rate `λ`, and the average time spent in the system `W`. It does not by itself tell you the "right capacity" during unstable overload scenarios; you need measured data, service-time distributions, and required latency bounds.

## 9. Lifecycle: Task Submission, Overload, and Shutdown

A bounded executor still needs to be shut down properly. `shutdown()` stops accepting new tasks while allowing already-accepted tasks (both running and queued) a chance to complete. `shutdownNow()` attempts to interrupt running tasks and returns tasks that have not yet started; it does not guarantee that all tasks stop immediately.

Deadline-based shutdown pattern (illustrative snippet inside an appropriate method, with `pool` already declared):

```java
pool.shutdown();
try {
    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        java.util.List<Runnable> neverStarted = pool.shutdownNow();
        // The application needs to decide how to handle/cancel unstarted tasks.
        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            System.err.println("Some tasks did not stop");
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

**Note:** `shutdownNow()` may return `FutureTask` instances created by `submit`; draining them from the queue **does not automatically guarantee** their `Future` is cancelled. If callers are still waiting on `Future.get()`, the cancellation/notification policy must be handled explicitly.

The `try/finally` block in the runnable example proactively releases the latch and calls `shutdownNow()` to avoid keeping workers alive after an assertion failure. In heavier tests, check the return value of `awaitTermination` during cleanup and report a failure if it does not stop; do not let the test suite hang indefinitely due to non-daemon threads.

## 10. Recommended Test Suite for the Practical Exercise

| Test Case | Deterministic Setup | Expectation |
|---|---|---|
| Pool has capacity | Run fewer tasks than capacity. | Accepted, executed once, `Future` yields result. |
| Exactly at limit | Hold all workers with a latch, fill the queue. | All tasks up to the threshold are accepted. |
| Overload with `AbortPolicy` | Submit more while workers and queue are full. | `RejectedExecutionException`; rejected task does not run. |
| Overload with `CallerRunsPolicy` | Keep pool saturated, submit from test thread. | Fallback task runs on the **caller** before `execute` returns. |
| Rejection after shutdown | Call `shutdown()`, then submit a new task under `AbortPolicy`. | New task is not accepted; exception is observed. |
| Task accepted before shutdown | Submit task, call `shutdown()`, wait for completion. | Pre-shutdown task can still run and produce a result. |
| Running task during `shutdownNow()` | Block task on an interruptible primitive. | Task responds to interrupt per code; pool terminates only after worker exits. |
| Queued task during `shutdownNow()` | Block one worker, submit a waiting task. | Unstarted task is returned; verify caller's `Future` policy. |
| Caller with its own context | Use `ThreadLocal` in the fallback task. | Verify the effect of running on the caller; do not rely on assuming tasks always run on a worker. |
| Sustained load | Keep producer faster than consumer by a controlled margin. | Queue does not exceed capacity, rejections/latency are observable, no unbounded backlog growth in the executor. |

Tests for ordering and saturation should use latches/barriers and `Future.get(timeout, unit)`, not `Thread.sleep()` to "hope a task is running." Load tests with performance variance should be separated from deterministic unit tests.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `Executors.newFixedThreadPool(8)` and assuming the queue is bounded. | The default queue can grow uncontrollably in practice. | Use `ThreadPoolExecutor` with `ArrayBlockingQueue<>(n)` or another queue with an explicit capacity. |
| Setting `maximumPoolSize=16` while using a nearly unbounded queue. | The queue keeps accepting tasks, and the pool rarely scales beyond core. | Understand the order: workers → queue → additional workers → rejection. |
| Increasing queue capacity to fix sustained overload. | Latency rises while processing capacity remains insufficient. | Measure throughput, reduce per-task cost, throttle producers, or reject explicitly. |
| Using `CallerRunsPolicy` on a thread that must not block. | Calling thread is occupied; can cause latency spikes or deadlock. | Use an overload-reporting handler or another throttling architecture. |
| Using `DiscardPolicy` with `submit` and unbounded `Future.get()`. | The `Future` may never complete. | Prefer explicit rejection; if dropping, ensure a cancellation/notification state. |
| Retrying immediately inside the handler by re-submitting to the same pool. | Can cause infinite loops or amplify overload. | Use bounded retries with backoff/conditions, typically managed outside the handler. |
| Treating `getActiveCount()` as a test synchronization signal. | Snapshot values are racy. | Use latches for test checkpoints; use metrics for observation only. |
| Calling `shutdown()` and assuming tasks have finished. | `shutdown()` does not wait. | Use `Future.get(timeout)` and `awaitTermination`. |
| Using a bounded queue while each task holds a very large array. | Can still consume excessive RAM. | Control payload size, per-task memory, and in-flight data. |

## 12. Extension Exercises

**Exercise 1 — Varying core and max.** Modify the first example to `corePoolSize=1`, `maximumPoolSize=3`, queue capacity 2. Hold running tasks with a latch; submit enough work so the queue fills and workers scale up to 3. Predict exactly which task number is rejected. Remember: the second and third tasks may enter the queue before the pool scales up.

**Exercise 2 — Handler with metrics.** Use an `AtomicLong` to count rejections and then throw `RejectedExecutionException`. Write an assertion that each submission beyond capacity increments the counter by one; still verify that accepted tasks complete.

**Exercise 3 — Replacing `AbortPolicy` with `CallerRunsPolicy`.** Keep the worker blocked and submit the third task from the test thread. The `execute` call will return only after the fallback task runs; if the fallback task blocks on a latch that the test thread is supposed to open, you can deadlock yourself. Explain why you must design so the caller can complete that task.

**Exercise 4 — Rejection during shutdown.** After `pool.shutdown()`, submit a new task under `AbortPolicy` and confirm `RejectedExecutionException`. Retry with `CallerRunsPolicy` to observe that the fallback does not run once the pool is shut down; discuss why an error-reporting policy is needed for the caller.

**Exercise 5 — Deadline control.** Make a task take longer than the caller's timeout. Use `Future.get(timeout, unit)`; on `TimeoutException`, decide whether to call `cancel(true)`. Verify that the task actually responds to the interrupt; **a `get` timeout does not stop the task by itself**.

## 13. Practical Exercise Completion Checklist

- Have a `ThreadPoolExecutor` with intentionally chosen `corePoolSize`, `maximumPoolSize`, bounded `BlockingQueue`, and `RejectedExecutionHandler`.
- Understand the processing order when core is full, queue is not full, queue is full, and max workers are reached.
- Have deterministic tests for **running tasks** and **queued tasks**, proving the exact rejection threshold.
- Do not silently drop tasks; `Future` instances for dropped tasks have an explicit policy.
- Have evidence that `CallerRunsPolicy` runs on the calling thread and understand its latency/reentrancy impact.
- Have timeouts on waiting operations, `shutdown()`/`shutdownNow()`, and cleanup in `finally`.
- Have appropriate operational metrics: pool size, queue depth, rejection rate, latency, throughput.
- Have benchmarked with a realistic workload; queue/thread configuration is not based solely on CPU count or guesswork.

**Conclusion:** A bounded queue turns work-admission limits into an explicit part of `ThreadPoolExecutor` design. When the pool and queue are full, the rejection policy determines how overload is surfaced externally. A safe-to-operate executor requires **worker limits + queue limits + an explicit overload policy + proper cleanup + deterministic tests**. Increasing thread count or queue length does not by itself create additional processing capacity.

### Java SE 17 Documentation

- [`ThreadPoolExecutor` and queueing/rejection rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [`RejectedExecutionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- [`ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [`ExecutorService`, `shutdown()`, `shutdownNow()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

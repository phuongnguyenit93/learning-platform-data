# RejectedExecutionHandler and the Four Rejection Policies in Java

## 1. Why Does ThreadPoolExecutor Have to Reject Work?

`ThreadPoolExecutor` manages the number of worker threads and a `BlockingQueue<Runnable>`. When work arrives faster than it can be processed, the executor must decide what happens to a new task instead of accepting tasks indefinitely and causing memory, latency, or resource usage to grow out of control.

`RejectedExecutionHandler` is the interface that defines the action **when a task is not accepted by `ThreadPoolExecutor`**. This is a mechanism of **Java Concurrency in `java.util.concurrent`**, applicable independently of any framework.

There are two main cases that trigger rejection:

1. **Saturation:** the number of workers has reached `maximumPoolSize` and the queue cannot accept any more tasks. A configuration using a bounded-capacity queue makes this event occur clearly.
2. **Executor is shutting down / has shut down:** after `shutdown()` or `shutdownNow()`, new tasks are no longer accepted, even if the queue still has space. State changes occurring concurrently with task submission can also cause a task that was just placed in the queue to be removed and passed to the handler.

For example: `corePoolSize = 1`, `maximumPoolSize = 1`, and the queue holds at most 1 task. When A is running, B is waiting, and C is submitted, C will be rejected; the **rejection policy** decides C's fate. Conversely, if the executor has already shut down, the policy is also invoked when submitting C, regardless of how full the queue is.

> "Rejected" does not mean "the task ran and failed." It means the executor **did not accept the task for execution** through the normal mechanism. A handler may throw an error, execute it on the calling thread, discard the task, or reroute it.

## 2. Task Acceptance Order and Handler Trigger Point

Simplified `execute(command)` flow of `ThreadPoolExecutor`:

1. If the number of existing workers is less than `corePoolSize`, attempt to create a new worker to handle `command`.
2. If no worker is created in step 1 and the executor is still in the running state accepting work, try to insert `command` into `workQueue`.
3. After enqueuing succeeds, **re-check the executor state** to handle races with `shutdown`; if it has shut down and removing the task from the queue succeeds, the task is rejected. The executor also ensures a worker exists when needed.
4. If the queue does not accept `command`, try to create additional workers up to `maximumPoolSize`.
5. If that still fails (already shut down, or both worker and queue limits have been reached), call `RejectedExecutionHandler.rejectedExecution(command, executor)`.

This is a conceptual sequence for understanding the thresholds, not a guarantee that every check in the internal implementation is a single atomic operation.

`RejectedExecutionHandler` is a functional interface:

```java
@FunctionalInterface
public interface RejectedExecutionHandler {
    void rejectedExecution(Runnable r, ThreadPoolExecutor executor);
}
```

- `r` is the task being rejected; if the initial call was `submit(...)`, it is typically a `RunnableFuture` created by `submit`.
- `executor` is the associated pool, allowing inspection of its state, queue, and metrics.
- The handler may throw `RejectedExecutionException`. If the handler returns normally, `execute` may return normally **even though the task was discarded**. "No exception thrown" must not be treated as proof that the task completed.
- By default, `ThreadPoolExecutor` uses `AbortPolicy`. A handler can be passed to the constructor or replaced with `setRejectedExecutionHandler(...)` when needed; configuring it before receiving load is easiest to control.

### Role of the Queue Type

| Queue | Practical Consequence for Rejection Thresholds |
| --- | --- |
| `ArrayBlockingQueue<>(N)` | Queue with capacity N; when full and no more workers can be added, the handler has a chance to be invoked. |
| `LinkedBlockingQueue<>(N)` | Bounded queue of capacity N; saturation behavior is similar, though data-structure overhead differs. |
| `LinkedBlockingQueue<>()` | Practically not constrained by a small application-defined threshold; after reaching core workers, tasks usually enter the queue and `maximumPoolSize` has little effect on scaling while the queue keeps accepting tasks. Latency/memory can grow before any rejection occurs. |
| `SynchronousQueue<>` | Holds no waiting elements: a task must be handed off directly to a worker. When handoff fails and no new worker can be created, it can be rejected; `DiscardOldestPolicy` is especially unsuitable because there is no element to `poll()`. |

`corePoolSize` is the threshold that prioritizes creating initial workers; it does not mean the executor always keeps that many threads alive from the start—the pool can initialize workers as tasks arrive. `maximumPoolSize` is the worker limit, not the total number of running tasks plus queued tasks.

## 3. Comparison of the Four Built-In Policies

All of them are nested classes inside `ThreadPoolExecutor` implementing `RejectedExecutionHandler`.

| Policy | When pool is active but saturated | When pool is shut down | Key Trade-off |
| --- | --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` to the submitting thread | Throws `RejectedExecutionException` | Explicit failure; the caller must handle it. |
| `CallerRunsPolicy` | Runs the task immediately on the **thread calling `execute`**, synchronously before the call returns | Discards the task | Creates natural backpressure, but blocks the caller and changes the execution context. |
| `DiscardPolicy` | Silently discards the new task | Silently discards the task | Tasks can be lost without the caller knowing. |
| `DiscardOldestPolicy` | Discards the element at the **head of the waiting queue**, then retries `execute` with the new task | Discards the new task | Loses an already-queued task; the retry may still be rejected. |

### 3.1. AbortPolicy: Explicit Failure

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.AbortPolicy();
```

The handler always throws `RejectedExecutionException`, even when the executor has already shut down. This is the default choice and is usually a safe starting point when every task matters: the submitter can log, increment a metric, signal backpressure/busy status, perform a **bounded** retry, or route the task to a durable mechanism.

Example of handling at the submission boundary (illustrative snippet; `pool` and `task` are created elsewhere):

```java
try {
    pool.execute(task);
} catch (RejectedExecutionException rejected) {
    // Log and delegate the decision to the appropriate caller layer.
    // Do not retry infinitely on the same overloaded pool.
    System.err.println("Task was not accepted: " + rejected.getMessage());
}
```

**Common mistakes:** catching and ignoring the exception, which turns `AbortPolicy` into silent data loss in practice; or retrying immediately without bounds, worsening the overload.

### 3.2. CallerRunsPolicy: Throttling the Submitting Thread

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.CallerRunsPolicy();
```

If the executor has not shut down, the handler calls `r.run()` on the **very thread that is submitting the task**. For example, if `main` submits work and the pool is saturated, `main` directly runs the rejected task and only returns from `execute` after it finishes. This is a form of backpressure: the producer spends time processing work itself, so it cannot keep pushing new tasks at the same rate.

Points that require careful evaluation:

- The task runs **synchronously**; the caller might be a UI thread, an event loop, a thread holding a lock, or another worker, leading to latency, deadlock, or resource starvation if chosen inappropriately.
- There is no longer a guarantee that the task runs on a configured worker (thread name, `ThreadLocal`, security context, request context, MDC management, etc.). Tasks should not rely on thread pool identity.
- Unchecked exceptions from a directly executed `Runnable.run()` can propagate to the caller, unlike failures of tasks running on a worker. For tasks wrapped by `submit`, `FutureTask` captures the error inside the `Future`.
- When the executor has already shut down, this policy **discards the task** and does not fall back to running on the caller.

Use it when the producer can be blocked, the task does not depend on worker-thread state, and the design accepts shifting execution cost onto the caller.

### 3.3. DiscardPolicy: Silently Dropping New Tasks

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.DiscardPolicy();
```

The handler neither throws an error nor runs the task. It is only appropriate when dropping some events is an **intentional business decision**, such as latest-state updates that can be regenerated, best-effort sampling, or periodic work where the next cycle supersedes the previous one. Even then, you should usually still count rejections to detect load loss.

It is unsuitable for transactions, data writes, payments, jobs that must complete, operations requiring a response, or tasks returning a `Future` awaited by another component. After `submit`, a discarded `FutureTask` can remain incomplete forever, causing `get()` to block indefinitely unless there is a timeout or separate cancellation.

### 3.4. DiscardOldestPolicy: Dropping the Task at the Head of the Queue

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.DiscardOldestPolicy();
```

When the pool is not shut down, the handler calls `executor.getQueue().poll()` to remove the waiting element at the head of the queue and resubmits the new task via `execute`. It does **not** cancel a currently running task. With a FIFO queue, that is usually the longest-waiting task; with a priority queue, `poll()` removes the head according to priority order, **not necessarily the earliest-submitted task**.

Consequences that are easy to overlook:

- The evicted old task does not throw an exception directly on the thread that submitted it; if it is a `FutureTask`, anyone waiting on `Future.get()` can hang because the `Future` was never cancelled.
- Retrying is **not guaranteed to succeed**: the new task may be rejected again due to contention with other producers or a shutdown transition. With a zero-capacity queue such as `SynchronousQueue`, `poll()` frees no space; retrying can recurse deeply. Do not use this policy with that configuration.
- Replacing "old work" with "new work" only makes sense if old data can truly be lost. Dropping the head of a `PriorityBlockingQueue` can violate expected priority guarantees.
- When the executor has shut down, the policy immediately discards the new task without retrying.

The JDK documentation also warns that this policy is rarely appropriate when callers wait for task completion; when "superseding old work" is needed, it is usually better to design a coalescing/state-updating queue along with explicit cancellation and failure notification.

## 4. Standalone Java 17+ Example: Same Load, Four Different Outcomes

This program deterministically establishes the state **A is running, B is waiting, and C arrives at full capacity** using `CountDownLatch`, avoiding reliance on `sleep()` or machine speed. Each policy uses a fresh pool, holds A unfinished until C is handled, and then releases it.

Save as `RejectionPoliciesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionPoliciesDemo {
    public static void main(String[] args) throws InterruptedException {
        runCase("AbortPolicy", new ThreadPoolExecutor.AbortPolicy());
        runCase("CallerRunsPolicy", new ThreadPoolExecutor.CallerRunsPolicy());
        runCase("DiscardPolicy", new ThreadPoolExecutor.DiscardPolicy());
        runCase("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy());
    }

    private static void runCase(
            String name, RejectedExecutionHandler policy)
            throws InterruptedException {

        List<String> events =
                Collections.synchronizedList(new ArrayList<>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                policy);

        try {
            pool.execute(() -> {
                events.add("A-start");
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                events.add("A-end");
            });

            started.await(); // A has occupied the worker
            pool.execute(() -> events.add("B")); // B has entered the queue

            try {
                pool.execute(() -> events.add("C")); // C is rejected
            } catch (RejectedExecutionException ex) {
                events.add("REJECTED-C");
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Pool did not terminate: " + name);
        }
        System.out.println(name + " -> " + String.join(", ", events));
    }
}
```

Compile and run:

```bash
javac RejectionPoliciesDemo.java
java RejectionPoliciesDemo
```

Deterministic output in this example:

```text
AbortPolicy -> A-start, REJECTED-C, A-end, B
CallerRunsPolicy -> A-start, C, A-end, B
DiscardPolicy -> A-start, A-end, B
DiscardOldestPolicy -> A-start, A-end, C
```

Explanation:

- `AbortPolicy`: C is rejected with an exception; A and then B still execute.
- `CallerRunsPolicy`: C runs immediately on the `main` thread before A is unblocked; B continues waiting for the worker.
- `DiscardPolicy`: C disappears; B remains in the queue.
- `DiscardOldestPolicy`: queued element B is evicted and C takes the waiting slot; after A finishes, C runs.

This example intentionally uses `execute` to show the handler mechanism directly. **Log order in concurrent programs is generally not fixed by itself**; here, latches enforce the order needed for verification. In practice, do not use latches to force saturation; measure throughput, latency, and rejection rate under real load.

## 5. `execute` and `submit`: Two Call Forms, One Major Risk

Both `execute(Runnable)` and `submit(...)` go through `ThreadPoolExecutor`'s rejection mechanism, but `submit` wraps the task in a `RunnableFuture` and returns a `Future` when the call returns normally.

| Scenario | With `execute` | With `submit` |
| --- | --- | --- |
| `AbortPolicy` rejects | Exception is thrown at submission time | Exception is also thrown during submission; no `Future` is returned |
| `CallerRunsPolicy` when not shut down | `Runnable` runs on the caller | `FutureTask` runs on the caller, so the `Future` is already done afterward; still potentially time-consuming |
| `DiscardPolicy` | Returns normally even though the task did not run | May return a `Future` that **never completes** |
| `DiscardOldestPolicy` | New task may be accepted; waiting task is replaced | The `Future` corresponding to the evicted task may never complete |

Calling `get(timeout, unit)` prevents indefinite blocking on the consumer side, **but does not fix the lost task**. `isDone()` does not become `true` just because the executor dropped the `FutureTask` from the queue. If the application truly allows dropping tasks, you must design a way to `cancel(false)` the discarded `Future` and emit a signal/metric for observers, or choose a policy that surfaces failures explicitly.

Common pitfall: using `Executors.newFixedThreadPool(n)` and assuming rejection will occur under overload. That factory uses an unbounded queue by default, so the queue can grow very large instead of triggering the handler early. If you need to bound waiting work and control rejection, construct `ThreadPoolExecutor` with an appropriately bounded queue.

## 6. Customizing RejectedExecutionHandler Responsibly

A custom handler is useful when the application needs to **measure** rejected tasks and make a consistent decision. A "count then throw" pattern preserves an explicit failure contract:

```java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicLong;

// Illustrative fragment; can be placed inside the pool configuration method.
AtomicLong rejectedCount = new AtomicLong();
RejectedExecutionHandler handler = (task, executor) -> {
    rejectedCount.incrementAndGet();
    throw new RejectedExecutionException(
            "Executor rejected task; shutdown=" + executor.isShutdown());
};
```

Pass `handler` to the `ThreadPoolExecutor` constructor as in the earlier example. `AtomicLong` tracks concurrent rejections safely, but the counter records **handler invocations**, which may not equal the number of ultimately lost tasks if the handler retries or hands off successfully. Time-series data should be exported to monitoring alongside active load, queue depth, and wait time.

When writing a more complex policy, ask:

1. Which tasks are allowed to be dropped? Are ordering, at-most-once semantics, retryability, or durable delivery required?
2. How long can the producer be blocked? Are there timeouts, interruption support, and an exit path on shutdown?
3. If a `FutureTask` in the queue has to be evicted, who cancels the `Future` and notifies waiters of failure?
4. The handler can be invoked concurrently from multiple threads. All state updates must be thread-safe; avoid holding locks or invoking callbacks that risk deadlock.
5. Communicate the "not accepted" status clearly to the submitting layer; do not pretend acceptance succeeded if processing cannot be guaranteed.
6. Do not blindly call `execute` recursively on the same full pool, and do not block indefinitely inside the handler itself. If there is a fallback queue, give it its own capacity and shutdown policy.

Some systems are better served by admission control in front of the pool (for example, limiting in-flight tasks with a `Semaphore`), pushing events to a durable queue, or returning a "busy" signal to the producer. A rejected handler is only the **last line of defense** after `ThreadPoolExecutor` has already rejected a task; it does not replace system-wide load-shedding design.

## 7. Choosing a Policy by Task Characteristics

| Requirement | Starting Choice | What to Verify Before Production |
| --- | --- | --- |
| Tasks must not be lost silently | `AbortPolicy` | Catch and handle rejection; use bounded retries or durable persistence when needed |
| Producer can slow down to shed load; work can run on caller | `CallerRunsPolicy` | Do not call from an event loop, latency-sensitive thread, or lock-holding thread; shutdown still drops tasks |
| Best-effort events can be dropped and nobody awaits a `Future` | `DiscardPolicy` | Task loss matches product requirements; monitor drop rate |
| Old data can be superseded by newer data | Consider a coalescing queue design; only consider `DiscardOldestPolicy` if risks are understood | FIFO queue, handle evicted `Future`s, avoid `SynchronousQueue` and unbounded retries |

**There is no single "best policy" for every application.** What matters are the nature of the tasks, error-reporting conventions, and the load tolerance of producers and consumers. For tasks that must complete, `AbortPolicy` paired with re-intake or durable persistence is usually clearer than a handler that drops work silently.

### Configuration and Operations Checklist

- Choose `corePoolSize` and `maximumPoolSize` based on whether tasks are CPU-bound or I/O-bound, actual resources, and benchmarks; do not set a huge thread count just to avoid rejection.
- Use a **bounded-capacity** queue if the goal is to limit queued work, accepting the trade-off between burst absorption and latency.
- Monitor at least rejection count/rate, `getActiveCount()`, `getPoolSize()`, `getQueue().size()`, `getCompletedTaskCount()`, processing time, and queue wait time. Pool and queue getters are **approximate snapshots**, not atomic capacity checks for exact decisions.
- Distinguish saturation rejections from shutdown rejections using executor state and telemetry; do not lump both together as "not enough threads."
- For a controlled shutdown, stop submitting work, call `shutdown()`, call `awaitTermination(...)`, and define how unfinished tasks are handled; `shutdownNow()` attempts to interrupt workers and returns tasks remaining in the queue, but does not guarantee all tasks stop immediately.
- Test the effects of `submit`/`Future`, exceptions, timeouts, and cancellation; write latch-controlled tests like the example above rather than relying on random timing.
- Test traffic spikes, slow callers, full queues, multiple competing producers, and shutdown races. Verify that the handler is invoked as expected and that dropped or handed-off work matches the contract.

## 8. Self-Check Questions

1. A pool has `corePoolSize=2`, `maximumPoolSize=4`, and a bounded queue of 10 slots: when 2 workers are busy and queue space remains, will the executor enqueue the task or scale up to 3 workers? **Enqueue first** in the standard sequence; only when the queue cannot accept the task does it try to scale workers toward the maximum.
2. Why can `CallerRunsPolicy` throttle the producer? **Because the producer directly pays the cost of running the rejected task**, holding the `execute` call until completion; however, this mechanism does not apply once the pool has shut down.
3. Does `DiscardOldestPolicy` cancel a currently running task? **No**; it calls `poll()` on the waiting queue and retries; a running task is not at the head of the queue.
4. If a `submit` call is dropped by `DiscardPolicy`, does `Future.get()` automatically throw `RejectedExecutionException`? **No**; the handler returned silently, and the `Future` may wait forever unless cancelled.
5. Can a task submitted to a pool that has already called `shutdown()` be executed on the submitting thread by `CallerRunsPolicy`? **No**; the policy discards the task when the executor has already shut down.

## References

- Java SE 17 API: [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- Java SE 17 API: [RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- Java SE 17 API: [AbortPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html), [CallerRunsPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html), [DiscardPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html), [DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)

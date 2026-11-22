# Submitting Independent Tasks and Avoiding Thread Starvation in the Java Executor Framework

## Objectives

After this lesson, you will be able to:

- Distinguish between **submitting multiple independent tasks** and having a running task wait for the result of another task.
- Understand how `ExecutorService`, `submit`, `Future`, queues, and the number of workers affect progress.
- Recognize **thread starvation** situations, especially *thread-starvation deadlock* when a worker waits for work stuck in its own executor.
- Choose ways to coordinate tasks without unnecessarily blocking workers; use timeouts, cancellation, pool separation, and backpressure appropriately.
- Observe, reproduce, and test these issues using Java SE tools.

Scope: Java concurrency and the Executor Framework in general; examples do not depend on any application framework.

## 1. Execution Model: Tasks, Workers, and Queues

An `ExecutorService` accepts work (`Runnable` or `Callable<T>`) and manages execution through threads. With a fixed thread pool:

~~~text
Thread calling submit()
       |
       v
  ExecutorService
       |
       +--> Worker 1: runs task A
       +--> Worker 2: runs task B
       +--> ... (up to the pool's maximum worker count)
       |
       +--> Queue: task C, task D, ... waiting for an idle worker
~~~

**Submit** means handing work over to the executor and receiving a tracking object; it **does not guarantee** that the task will run immediately or that tasks will run in parallel. Actual progress depends on the number of workers, thread creation policy, queue, external resources, and whether workers are blocked.

Key APIs:

| API | Key Meaning to Remember |
| --- | --- |
| `execute(Runnable)` | Submits work without returning a `Future`; errors cannot be retrieved via `Future.get()`. |
| `submit(Runnable/Callable)` | Returns a `Future`; task exceptions are captured and surface via `get()` as `ExecutionException`. |
| `Future.get()` | Blocks the **calling thread** until a result, error, or interruption occurs; the no-timeout version can wait indefinitely. |
| `Future.get(timeout, unit)` | Limits the **caller's** wait time; throws `TimeoutException` on expiration, **does not automatically cancel the task**. |
| `Future.cancel(true)` | Requests cancellation and, if the task is running, attempts to interrupt the thread; the task must cooperate to stop in time. |
| `shutdown()` | Stops accepting new tasks and attempts to finish already submitted tasks. |
| `shutdownNow()` | Attempts to interrupt running tasks and returns unstarted tasks; does not guarantee all tasks stop immediately. |

### What Makes Tasks Independent?

Two tasks are independent when one task **does not need the result or completion signal of the other to finish**. For example, processing three independent inputs and then aggregating the results in the coordinating thread. If all three modify a shared global variable or contend for the same resource, you still must handle data safety and resource limits; "independent in inputs" does not mean "synchronization-free".

A sensible pattern is: **submit all tasks first, then wait for results at the coordination point**. Calling `Future.get()` sequentially on the calling thread does not cause the three tasks to run sequentially, because they were already submitted beforehand. However, the order of retrieving results can delay displaying them if the first future has not finished yet.

## 2. Runnable Example: Submitting Three Independent Tasks

Create the file `IndependentTasksDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class IndependentTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 10 * 10,
                    () -> 20 * 20,
                    () -> 30 * 30
            );

            List<Future<Integer>> futures = new ArrayList<>();
            for (Callable<Integer> task : tasks) {
                futures.add(pool.submit(task)); // Submit all first
            }

            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get(2, TimeUnit.SECONDS); // Wait in main
            }

            System.out.println("Tổng = " + total);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run on JDK 17 or later:

~~~bash
javac IndependentTasksDemo.java
java IndependentTasksDemo
~~~

Deterministic output:

~~~text
Tổng = 1400
~~~

None of the three `Callable`s wait on each other, so the pool can assign them to different workers. The `get` loop in `main` only aggregates the results. In a real program, you must decide on a policy when a future times out or fails: log/collect errors, cancel redundant work, or return partial results. Calling `shutdown` in `finally` ensures no new tasks continue to be accepted once the coordination block finishes.

**Common pitfall:** submitting a task and calling `get` immediately inside each iteration causes the caller to wait for that task to complete before submitting the next one. That forfeits concurrency, even though it may not cause starvation. The recommended pattern is:

~~~java
// Good when tasks are truly independent:
for (Callable<Integer> task : tasks) {
    futures.add(pool.submit(task));
}
for (Future<Integer> future : futures) {
    consume(future.get());
}
~~~

The snippet above is illustrative: `tasks`, `futures`, `pool`, and `consume` need to be declared in a real program.

### When You Need to Process Results in Completion Order

`ExecutorCompletionService<T>` wraps an executor and places completed futures into a result queue. `take()` waits for **whichever result completes next**, rather than waiting for the first future in a list. This is still a caller-blocking operation; let the coordinating thread wait, and avoid using a worker inside the same pool to wait on tasks from that same pool.

~~~java
// Illustrative snippet when pool and tasks have already been created:
java.util.concurrent.ExecutorCompletionService<Integer> completed =
        new java.util.concurrent.ExecutorCompletionService<>(pool);

for (Callable<Integer> task : tasks) {
    completed.submit(task);
}
for (int i = 0; i < tasks.size(); i++) {
    Integer result = completed.take().get();
    // Process in completion order, without assuming submission order.
}
~~~

## 3. How Does Thread Starvation Occur?

**Thread starvation** is a condition where a task gets no opportunity to make progress for a significant period because execution resources are occupied: for example, all workers are busy, blocked, or other higher-priority tasks continuously take turns. An executor with a queue can still accept more tasks while none of the queued tasks are assigned a worker.

A special case is **thread-starvation deadlock**: workers are running parent tasks, while those parent tasks are waiting on child tasks submitted to **the very same pool that has no idle workers left**. The wait relationship locks progress on itself:

~~~text
Pool with 1 worker
Worker-1: runs Parent
  Parent: submits Child to the same pool
  Parent: calls child.get() -> WAITING
Queue: [Child]
Child needs Worker-1 -> Worker-1 is waiting on Child
=> Neither task can release the worker.
~~~

This does not necessarily involve two mutexes locking each other in a cycle. It is a dependency cycle between **worker scheduling** and **Future completion**. Simply increasing the pool size from 1 to 2 is not a sustainable fix: two concurrently running parents can simultaneously wait on two children sitting in the queue.

Beyond the dependency above, starvation can also be caused by long-running I/O or blocking tasks occupying the entire pool; a queue that is too long relative to processing speed; or tasks needing a shared lock/semaphore. "Low CPU with a full queue" is often a sign worth investigating, though low CPU alone is not enough to conclude starvation.

## 4. Safe Reproduction: Parent Waiting on Child in a Single-Thread Executor

Create `StarvationDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class StarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        Future<Integer> parent = pool.submit(() -> {
            Future<Integer> child = pool.submit(() -> 42);
            return child.get(); // The sole worker waits on a queued task
        });

        try {
            System.out.println(parent.get(200, TimeUnit.MILLISECONDS));
        } catch (TimeoutException expected) {
            System.out.println("Timeout: task con không có worker để chạy");
        } finally {
            parent.cancel(true);  // Interrupt the worker waiting on Future.get()
            pool.shutdownNow();   // Prevent the demo program from hanging
        }
    }
}
~~~

Run:

~~~bash
javac StarvationDemo.java
java StarvationDemo
~~~

Expected output:

~~~text
Timeout: task con không có worker để chạy
~~~

`parent.get(200, ...)` is called in `main` and bounds how long **main waits**. It does not allow `child` to run, nor does it fix the dependency inside the worker. In `finally`, `cancel(true)` requests an interrupt on the parent blocked at `child.get()`; `shutdownNow()` attempts to clean up remaining queued tasks. The goal is for the demo to terminate, not to use timeouts as an architectural solution.

In a two-worker scenario, the same failure still occurs when both workers run parents waiting on children from the same pool. The core takeaway: **never hold a worker of an executor just to wait for a task that needs a worker from that same executor**.

## 5. Primary Fix: Model Dependencies Instead of Blocking Workers

If the next step merely transforms the result of the previous step, use a pipeline: the next task is only triggered **after** the previous result is available. In Java SE, `CompletableFuture` supports `thenApply`, `thenCompose`, and `thenCombine` to express that relationship.

Create `CompositionDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompositionDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(() -> 21, pool)
                            .thenApply(value -> value * 2);

            System.out.println("Kết quả = " + result.get(2, TimeUnit.SECONDS));
        } finally {
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
javac CompositionDemo.java
java CompositionDemo
~~~

Deterministic output:

~~~text
Kết quả = 42
~~~

`thenApply` does not create a child task and block the worker waiting for it; the transformation function runs once the previous stage completes. For variants without the `Async` suffix, the action may run on the thread that completed the previous stage or the thread registering the continuation if the stage is already complete. Therefore, **do not assume** every continuation has its own thread.

Choose the composition operation according to semantics:

| Need | How to Express |
| --- | --- |
| Transform result A into B | `future.thenApply(transform)` |
| B is an asynchronous step returning `CompletionStage<B>` | `future.thenCompose(startB)`, flattening nested futures |
| A and B are independent, only need to combine when both finish | `a.thenCombine(b, combine)` |
| Only need a completion signal for multiple futures | `CompletableFuture.allOf(...)` |
| Want to process results of `Callable`s as they complete | `ExecutorCompletionService` |

Illustrative example for a dependent step that must execute next on the same executor:

~~~java
// Uses existing pool variable, does not call get()/join() inside a worker.
CompletableFuture<String> chain =
        CompletableFuture.supplyAsync(() -> "java", pool)
                .thenCompose(text ->
                        CompletableFuture.supplyAsync(
                                () -> text.toUpperCase(java.util.Locale.ROOT), pool));
~~~

Here, the second step **is only submitted once the first step has completed**; even a single worker can finish this chain because no worker is held waiting on a child. If the continuation performs blocking I/O, consider a separate executor for blocking operations; automatically using `thenApplyAsync` does not guarantee eliminating starvation if it still targets the same congested pool.

### When Creating a Child Task Is Unnecessary

If the sub-computation is short and a natural part of the parent's work, executing it directly inside the parent task may be the simplest approach. Submitting another task and calling `get` on its result provides no benefit if the parent has no independent work to do while waiting.

## 6. Separating CPU-Bound and Blocking Workloads

A CPU-bound task typically occupies the CPU until computation finishes. A blocking task (file/network reads, waiting on a lock, waiting on another service) can hold a platform thread while the CPU is mostly idle. When both types are placed in a small pool, blocking tasks can occupy all workers and delay short computational work.

Design principles:

1. **CPU-bound pool:** set concurrency to match CPU core count and empirical measurements; do not assume "more threads means faster".
2. **Blocking pool:** consider a dedicated executor and limit downstream resources (connections, rate limits, file descriptors); adding too many threads can shift the bottleneck to another resource.
3. **Do not use a shared pool for orchestration flows that must wait on tasks in the same pool:** when waiting is unavoidable, wait on a coordinating thread outside the dependent pool, or design an asynchronous pipeline.
4. **Measure against real workloads:** latency, throughput, active task count, queue length, and wait time; pool size is only part of the problem.

`Executors.newFixedThreadPool(n)` by default uses an **unbounded-capacity queue** (`LinkedBlockingQueue`), so tasks can accumulate heavily when submission rate exceeds processing rate; this easily leads to increased memory usage and latency. `newCachedThreadPool()` can aggressively grow the thread count when many tasks block, and is also no substitute for load control.

### Bounded Queues and Handling Overload

Example `ThreadPoolExecutor` configuration (illustrative configuration snippet, not a standalone program):

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

The queue holds at most 100 **waiting** tasks, separate from the maximum of 4 running tasks. When the pool has all workers busy and the queue is full, `AbortPolicy` throws `RejectedExecutionException`; the caller must have an explicit policy (slow down submission, report overload, bounded retry, or reject the request). `import java.util.concurrent.*;` is required for this example.

`CallerRunsPolicy` can create backpressure by having the caller run the task when the pool is overloaded, but it blocks the caller and behaves differently once the executor has shut down. Do not pick a rejection policy just to hide overload symptoms; understand the caller context and shutdown conditions.

For external services with rate/concurrency quotas, a `Semaphore` or request-limiting mechanism may be necessary even when the executor still has plenty of workers. **Queue limits and concurrent request limits solve two different problems.**

## 7. Timeouts, Cancellation, Interruption, and Shutdown

A timeout is a **wait-time boundary**, not proof that the task has been cancelled. The following snippet is only a control pattern, assuming `future` has already been initialized:

~~~java
try {
    Result value = future.get(1, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException timeout) {
    future.cancel(true);
    // Log the timeout and decide the response for the caller.
}
~~~

`Result` and `use` are illustrative placeholders. In real code, you must handle `InterruptedException` (usually restoring the interrupt flag at the appropriate coordination layer), `ExecutionException`, and `CancellationException`; never swallow errors and treat them as success.

If a task is blocked on an interruptible API, `cancel(true)` can cause it to stop; if the task ignores interrupts, uses non-interruptible I/O, or runs tight CPU code without checking the interrupt flag, cancellation is not guaranteed to complete immediately. Tasks should have status check points, their own I/O timeouts, and `finally` blocks to release resources.

When shutting down an executor, the typical sequence is: stop accepting new work via `shutdown()`, wait with a bound via `awaitTermination`, and only then call `shutdownNow()` if needed. Do not leave pools alive indefinitely after demos/tests; also do not arbitrarily shut down a shared pool from individual tasks.

**An important note:** putting `get(timeout)` directly inside a parent running in the same small pool still holds the worker until the timeout expires. It only bounds the damage in time; it does not eliminate the waiting structure that causes starvation.

## 8. Detection and Diagnosis in Java Applications

Warning signs may include:

- The queue keeps growing or tasks wait for a very long time; throughput drops even while tasks are still being accepted.
- Pool workers are all busy, yet few tasks complete; CPU may be low if most threads are waiting.
- Thread dumps show many workers in `WAITING`/`TIMED_WAITING` at `FutureTask.get`, `CompletableFuture.join`, a lock, or I/O; meanwhile, the queue contains the work those workers are waiting on.
- Timeouts increase as workload increases; adding workers only delays when the symptom appears.

Verification workflow instead of guessing:

1. Identify **which executor** receives parent/child tasks and the actual worker count; draw the "task A waits on task B" graph along with where B is queued.
2. Capture a thread dump during congestion (e.g., `jcmd <pid> Thread.print` on an appropriate JDK) and inspect the stacks of waiting workers.
3. If using `ThreadPoolExecutor`, observe `getPoolSize()`, `getActiveCount()`, `getQueue().size()`, and `getCompletedTaskCount()` over time; these metrics are only approximate snapshots and should not be used in isolation as proof.
4. Compare CPU/I/O processing time, lock wait time, and queue length; test under controlled load to see where the bottleneck lies.
5. Fix the dependency / split workloads / bound the queue, then re-measure throughput, timeouts, and resources. Do not use increasing pool size as proof that the bug has been thoroughly resolved.

**Terminology distinction:** a traditional lock deadlock is typically a wait cycle among locks; thread-starvation deadlock here is a dependency cycle involving workers and the task queue. "Starvation" is broader and can simply be prolonged delay due to scheduling or resource contention, without necessarily having a strict wait cycle.

## 9. Self-Testing Easily Overlooked Scenarios

Valuable tests should force progress using bounded synchronization primitives (such as `CountDownLatch`), avoiding `Thread.sleep` to "guess" ordering. Cases worth reproducing:

| Scenario | What to Verify |
| --- | --- |
| Three independent tasks; pool has enough workers | All are submitted before the caller waits; result does not depend on execution order. |
| 1-worker pool, parent submits child then calls `get` | Detects timeout, prevents the test from hanging, and cleans up the pool afterward. |
| Two workers, two parents concurrently waiting on two children in the same pool | Demonstrates that increasing from 1 to 2 workers does not eliminate the architectural issue. |
| One task fails or runs long | Caller receives the expected `ExecutionException`/`TimeoutException`, with a clear cancellation policy. |
| Queue full | Rejection is handled predictably; no tasks are silently lost. |
| Task is cancelled/interrupted | Resources are closed; task responds to interrupt or I/O timeout as designed. |

When writing tests, **do not rely on thread execution order** or fast/slow machine timing to assert correctness. Check results, timeout states, and observable wait relationships. A test with a test-runner-level timeout still needs to clean up the executor in `finally` so it does not stall the entire test suite.

## 10. Quick Decision Rules

- **Truly independent tasks:** submit all, then collect results in the caller; use `CompletionService` if you need to process in completion order.
- **Task B depends on A:** use transformations/chaining like `thenApply` or `thenCompose`; do not occupy A's worker to wait on B queued in the same pool.
- **Tasks blocked on I/O:** separate workload types and measure resource limits; consider an appropriate executor and real I/O timeouts.
- **Unbounded queue growth:** bound the queue, introduce backpressure/rejection policies, and control producer rate.
- **Small pool frequently "stalls":** inspect thread dumps, `Future.get()/join()` chains, and check whether the queued work needs the very workers being held.
- **Java 21+ with virtual threads:** `Executors.newVirtualThreadPerTaskExecutor()` is useful for many thread-per-task blocking workloads, but it does not automatically rate-limit external services, cure logical dependency cycles, or replace timeouts/cancellation. This lesson's main examples use APIs that run on Java 17+.

Core point: **submit independent work so the executor has a chance to run it; express dependent work as coordination chains; never let all workers get locked up waiting on the very queue they are supposed to serve.**

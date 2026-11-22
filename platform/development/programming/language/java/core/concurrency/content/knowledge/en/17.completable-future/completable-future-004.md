# thenApplyAsync() and the Meaning of Executor in CompletableFuture

> **Key takeaway:** `CompletableFuture.thenApplyAsync(fn)` creates **a dependent stage** that applies a transformation function when the previous stage **completes normally**; the function is scheduled via the **default asynchronous execution facility**, usually `ForkJoinPool.commonPool()` in Java 17. `thenApplyAsync(fn, executor)` uses the **specified Executor** to run the transformation function. In contrast, `thenApply(fn)` does not require an async scheduling boundary: the callback may execute on the thread that completed the previous stage or on the thread calling the registration if the stage is already completed. The word `Async` describes **how the callback is dispatched**, and does not guarantee that the callback is non-blocking, runs in parallel, is faster, or cannot be rejected.

This article belongs to the **CompletableFuture** group of **general Java concurrency**, using Java SE 17+, without discussing Spring. The content focuses on the meaning of the executor at each stage, timing, thread context, errors/rejection, data dependencies, pool selection, cancellation, and operations.

## 1. Context: CompletableFuture Is a Chain of Stages

`CompletableFuture<T>` is an abstraction for a result that may arrive later, and is also a `CompletionStage<T>`. A pipeline can consist of multiple stages:

~~~text
Source stage
 CompletableFuture<Integer>
           |
           | when completed normally
           v
 thenApplyAsync(Integer -> String, Executor)
           |
           v
 CompletableFuture<String>
           |
           | when completed normally
           v
 thenApply(String -> Integer)
           |
           v
 CompletableFuture<Integer>
~~~

Each call creates a **new stage**. It does not modify the result type of the original stage, does not turn a failed callback into a success, and does not create extra CPU on its own. The condition for the `thenApplyAsync` callback to be invoked is that the input stage has **completed normally**; if the input stage is exceptional/cancelled, the normal transformation callback **does not run**, and the dependent stage completes exceptionally down the chain.

A minimal example:

~~~java
// API snippet: use inside a method with CompletableFuture imported.
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(21);

CompletableFuture<String> result =
        source.thenApplyAsync(n -> "value=" + (n * 2));
~~~

`result` has type `CompletableFuture<String>`; `source` remains `CompletableFuture<Integer>`. Even if `source` is already completed, `thenApplyAsync` is not a synonym for `thenApply`: the callback may be submitted to an executor instead of executing immediately on the caller.

### Three Questions That Must Be Separated

1. **When is the callback eligible to run?** When the source stage completes normally.
2. **Where does the callback run?** Depends on the non-async/async variant and the executor.
3. **When does the callback actually finish running?** Depends on queueing, worker count, workload, errors, and cancellation; there is no automatic hard deadline.

Saying "after `thenApplyAsync`, the program continues immediately" is also imprecise: the method *usually* returns quickly after registering/submitting the dependent stage, but a custom executor/rejection/direct callback and chained operations can cause exceptions or overhead. To know that **the value has been computed**, you must observe/wait on the corresponding Future.

## 2. Comparing thenApply, thenApplyAsync, and thenApplyAsync with an Executor

| Method | When is the callback invoked? | Where can the callback execute? | Things to note |
| --- | --- | --- | --- |
| `thenApply(fn)` | After the previous stage completed normally | The thread completing the previous stage, or the thread participating in completion/registration depending on timing | No guarantee of a separate thread, no async scheduling boundary |
| `thenApplyAsync(fn)` | After the previous stage completed normally | Default asynchronous execution facility, usually `commonPool()` | Call sites may contend for the common pool; low-parallelism exception applies |
| `thenApplyAsync(fn, executor)` | After the previous stage completed normally | According to the specified `executor.execute(...)` | May queue, reject, or be slow when busy; requires lifecycle ownership |

**All three** perform a **`T -> U` mapping** and return `CompletableFuture<U>`; none returns `U` directly. The difference lies mainly in **callback execution rules**, not the mathematics of the transformation function.

### What Does "Without an Executor" Mean in the API?

It does not mean the callback runs in a vacuum. When calling `thenApplyAsync(fn)`, the implementation selects a **default asynchronous execution facility**. In JDK 17, the default is usually `ForkJoinPool.commonPool()`; the `CompletableFuture` Javadoc notes an exception: if the common pool does not support **parallelism of at least 2**, a new Thread may be created for each async task.

Therefore, the statement "`thenApplyAsync` always uses a specific shared worker" is **false**. Do not write tests that require thread names to have the prefix `ForkJoinPool.commonPool-worker` or demand a fixed worker index.

### Async Does Not Mean the Callback Executes Immediately

Registering an async action before the source completes:

~~~text
Thread A: source.thenApplyAsync(fn, executor) --> returned dependent stage
                    |
                    | source not yet completed
                    v
         callback not yet allowed to run
                    |
Thread B: source.complete(value)
                    |
                    v
       executor is requested to run fn
                    |
                queue/wait
                    |
              worker runs fn
                    |
             dependent completed
~~~

A registered stage may wait for the **source** and then wait for the **executor**, meaning there are **two types of wait time** that must be measured separately when a pipeline is slow.

## 3. Example 1 — Clearly Observing the Source-Completing Thread and the Callback's Executor

Use two single-thread executors with clear thread names. The source is initially **not completed**, and callbacks are registered beforehand. A worker `source-worker` calls `complete(21)`; `thenApply` runs synchronously on the completion path, while `thenApplyAsync(..., stageExecutor)` is submitted to `stage-worker`.

Create `ThenApplyVsAsync.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenApplyVsAsync {
    public static void main(String[] args) throws Exception {
        ExecutorService sourceExecutor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "source-worker"));
        ExecutorService stageExecutor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "stage-worker"));

        try {
            CompletableFuture<Integer> source =
                    new CompletableFuture<>();

            CompletableFuture<String> inline =
                    source.thenApply(v ->
                            Thread.currentThread().getName() + ":" + v);

            CompletableFuture<String> async =
                    source.thenApplyAsync(v ->
                            Thread.currentThread().getName() + ":" + v,
                            stageExecutor);

            sourceExecutor.execute(() -> source.complete(21));

            System.out.println("thenApply = " + inline.join());
            System.out.println("thenApplyAsync = " + async.join());
        } finally {
            sourceExecutor.shutdown();
            stageExecutor.shutdown();

            if (!sourceExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                sourceExecutor.shutdownNow();
            }
            if (!stageExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                stageExecutor.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ThenApplyVsAsync.java
java ThenApplyVsAsync
~~~

Normal stdout on JDK 17:

~~~text
thenApply = source-worker:21
thenApplyAsync = stage-worker:21
~~~

This is a **controlled experiment**: only `source-worker` completes the source; `thenApply` is registered while the source is not yet completed, so the non-async continuation runs on the completion path. The async continuation's executor has one worker named `stage-worker`, so the result is deterministic regardless of which thread gets CPU time first.

**Do not overgeneralize:** `thenApply` does **not always** run on the source worker in every program. If the source is already completed **before** `thenApply` is called, the callback may run **immediately on the registering thread**; other completion interactions also affect where it runs. `thenApplyAsync(fn, executor)` is the explicit way to choose the execution facility for the callback.

## 4. Source Already Completed Before Registration: The Difference Still Exists

A stage may already be completed before a dependent method is called. For example, `CompletableFuture.completedFuture(5)` is a stage that already has a value.

- `thenApply(fn)` may compute the mapping immediately upon registration; in typical JDK 17 implementations, the callback runs on the thread calling the method.
- `thenApplyAsync(fn, executor)` still schedules the callback through the executor instead of forcing the caller to execute the mapping directly.
- Do not use `isDone()` immediately after creating an async stage to assert whether the callback has or has not finished: the worker might have already run before main checks. To verify completion, use `join()`/`get()` or a separate signal.
- Do not measure the duration between the call and `join()` once and conclude that async is always faster.

### Example 2 — Completed Source: Does the Callback Run on the Caller or a Separate Worker?

Create `CompletedStageExecutor.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletedStageExecutor {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> done =
                    CompletableFuture.completedFuture(5);

            CompletableFuture<Boolean> plain = done.thenApply(
                    value -> Thread.currentThread() == caller);

            CompletableFuture<Boolean> async = done.thenApplyAsync(
                    value -> Thread.currentThread() != caller, executor);

            System.out.println("plain on caller = " + plain.join());
            System.out.println("async on executor worker = " + async.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac CompletedStageExecutor.java
java CompletedStageExecutor
~~~

Typical stdout on JDK 17:

~~~text
plain on caller = true
async on executor worker = true
~~~

This demonstrates the behavior **without depending on OS thread names**. A non-async call on a `completedFuture` that completed before registration may execute immediately on the caller; the async call uses a thread from the separate `ExecutorService`. Do not turn this example's output into a contract that all `thenApply` calls run on the caller — when the source is still pending, the completing thread may run the mapping.

## 5. Executor Is Not Data: It Is an Execution Policy

The `Executor` interface has only a foundational contract:

~~~java
public interface Executor {
    void execute(Runnable command);
}
~~~

An `Executor` accepts a command to execute according to its own mechanism. There are very different choices:

- An executor that runs each command immediately on the caller (direct executor).
- An executor using a single worker thread, executing sequentially.
- An executor using multiple workers and a queue.
- An executor with a bounded queue that may throw `RejectedExecutionException` when overloaded.
- An executor that prioritizes/schedules according to its own policy; it may delay or reorder tasks.
- An executor that has been shut down no longer accepts new tasks.

**Executor does not by itself guarantee that a task runs on a different thread.** For example:

~~~java
// Snippet: valid direct Executor, runs the command synchronously on the caller.
Executor direct = Runnable::run;
CompletableFuture<Integer> f =
        CompletableFuture.completedFuture(1)
                .thenApplyAsync(x -> x + 1, direct);
~~~

Even though the method has the `Async` suffix, the direct executor calls `Runnable.run()` immediately, so the mapping can run synchronously on the calling thread. Therefore, "Async = guaranteed non-blocking/thread switch" is a serious misconception.

### Choosing `Executor` or `ExecutorService`?

`Executor` is sufficient to pass an execution policy to `thenApplyAsync`. `ExecutorService` adds `submit`, `shutdown`, `awaitTermination`, etc. In practice, many executors we pass are `ExecutorService`, but the signature of `thenApplyAsync` accepts **`Executor`**. If code owns an `ExecutorService`, that code is responsible for closing and cleaning up resources. Do not call `shutdown` on a shared executor managed by another framework/library/module.

## 6. Example 3 — A Direct Executor Does Not Create a New Async Thread

Create `DirectExecutorDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public class DirectExecutorDemo {
    public static void main(String[] args) {
        Thread caller = Thread.currentThread();
        Executor direct = Runnable::run;

        CompletableFuture<Boolean> stage =
                CompletableFuture.completedFuture(7)
                        .thenApplyAsync(value ->
                                Thread.currentThread() == caller,
                                direct);

        System.out.println("mapped value = " + stage.join());
        System.out.println("stage done = " + stage.isDone());
    }
}
~~~

Run:

~~~bash
javac DirectExecutorDemo.java
java DirectExecutorDemo
~~~

Stdout:

~~~text
mapped value = true
stage done = true
~~~

A direct executor satisfies the API, but **creates no thread boundary**. It can be suitable for tests or cases where inline execution is desired; in production, read the contract of the actual executor before concluding that "Async" isolates latency from the caller.

Note for callbacks with recursion or nested completions: a direct executor can push more work onto the same call stack or completion path, altering latency/reentrancy; it should not be used as a default way to avoid all thread pool overhead.

## 7. Meaning of thenApplyAsync in a Stage Chain

Each call to `thenApplyAsync(fn, executor)` creates a dependent stage and requests **the corresponding executor for that specific callback**. It **does not set a permanent "current executor" attribute** for all subsequent stages.

Example:

~~~java
// API snippet, variables/source are created elsewhere.
CompletableFuture<String> result =
        source
            .thenApplyAsync(this::parse, cpuExecutor)
            .thenApplyAsync(this::render, renderExecutor)
            .thenApply(this::format);
~~~

- `parse` is dispatched via `cpuExecutor`.
- `render` is dispatched via `renderExecutor`.
- `format` has no async executor specified; it may run on the completion path of the `render` stage.
- If a later stage calls `thenApplyAsync(this::more)` without an executor, it falls back to the implementation's **default asynchronous facility**, rather than automatically "inheriting" `renderExecutor`.

**Key point to remember:** An executor is a **parameter of each individual async dependent method**, not a context that automatically propagates through the pipeline.

### Example 4 — Pipeline Handing Off Across Two Separate Executors

Create `ExecutorHandoffChain.java` (Java 17+):

~~~java
import java.util.Queue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorHandoffChain {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService poolA = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "pool-A"));
        ExecutorService poolB = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "pool-B"));
        Queue<String> contexts = new ConcurrentLinkedQueue<>();

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(() -> {
                        contexts.offer(Thread.currentThread().getName());
                        return 20;
                    }, poolA)
                    .thenApplyAsync(value -> {
                        contexts.offer(Thread.currentThread().getName());
                        return value + 1;
                    }, poolB)
                    .thenApplyAsync(value -> {
                        contexts.offer(Thread.currentThread().getName());
                        return value * 2;
                    }, poolA);

            System.out.println("result = " + result.join());
            System.out.println("contexts = " + contexts);
        } finally {
            poolA.shutdown();
            poolB.shutdown();
            if (!poolA.awaitTermination(10, TimeUnit.SECONDS)) {
                poolA.shutdownNow();
            }
            if (!poolB.awaitTermination(10, TimeUnit.SECONDS)) {
                poolB.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac ExecutorHandoffChain.java
java ExecutorHandoffChain
~~~

Stdout:

~~~text
result = 42
contexts = [pool-A, pool-B, pool-A]
~~~

Stage 2 depends on stage 1, and stage 3 depends on stage 2, so the three context recordings happen in logical order even though the thread may change. `ConcurrentLinkedQueue` ensures safe additions from the managed threads; `join` on the final stage waits for the entire pipeline to complete before main prints.

A separate pool isolates **executor queues and worker threads**, but CPU, heap, GC, and downstream services in the JVM are still shared. Do not treat each executor handoff as "a new server" or a hard-deadline guarantee.

## 8. Default Executor and ForkJoinPool.commonPool()

In Java 17, `CompletableFuture` has a default asynchronous execution facility. For async methods without a specified executor, the JDK typically uses `ForkJoinPool.commonPool()` — a global pool within the same JVM.

Other components may also share the common pool:

- `CompletableFuture.runAsync` / `supplyAsync` without an executor argument.
- Many `thenApplyAsync`, `thenAcceptAsync`, `thenComposeAsync` calls without an executor argument.
- `ForkJoinTask` algorithms submitted to `ForkJoinPool.commonPool()`.
- Parallel streams in standard JDK implementations.

Do not assume everything always uses the common pool in every configuration/implementation. In particular, when the common pool does not support a minimum parallelism of 2, `CompletableFuture` may use a thread-per-task fallback.

### Noisy Neighbor

~~~text
Module A: 100 heavy CPU tasks ────────┐
                                      +── commonPool workers
Module B: 1 short thenApplyAsync ─────┘
                                      |
                                  contention
                                      |
                         callback B may wait a long time
~~~

A callback that takes only 2 ms of CPU time can have an **end-to-end latency** of hundreds of ms if it has to wait to be scheduled while the shared pool is busy. Queueing/scheduling, CPU saturation, GC, and downstream blocking must be measured separately; do not draw conclusions from a single log or a single benchmark run.

**When to leave the default?** For lightweight, CPU-oriented computation with no isolation requirements and measured under realistic load, the common pool can be a concise choice. When the workload is latency-sensitive, blocking, or resource-intensive, consider a dedicated executor.

## 9. Avoid Blindly Putting Long Blocking I/O into commonPool

A common mistake:

~~~java
// Snippet — blockingRemoteCall() is an undeclared business method.
CompletableFuture<String> pipeline =
        source.thenApplyAsync(value -> blockingRemoteCall(value));
~~~

The `Async` suffix here **does not turn blocking I/O into non-blocking**. Fork/Join workers can still wait on network/database/file for seconds; many concurrent callbacks can starve the shared pool of workers for other computations.

A safer choice when blocking is involved:

~~~java
// Snippet — ioPool is an ExecutorService created/managed in the component.
CompletableFuture<String> pipeline =
        source.thenApplyAsync(value -> blockingRemoteCall(value), ioPool);
~~~

However, simply passing `ioPool` is not enough. The pool needs sizing based on **downstream limits and memory**, I/O timeouts, bounded admission or a rejection policy if producers can outpace consumers, queue-wait observability, and shutdown when the component is no longer in use. `Executors.newFixedThreadPool(n)` uses an unbounded queue by contract, so it is not a production template for backpressure.

### CPU-Bound vs. I/O-Bound

- **CPU-bound:** Choose concurrency considering cores/quotas and the size of leaf work; too many threads can increase context switching.
- **I/O-bound:** May need more concurrent tasks than CPU cores, but is still bounded by connections, remote rate limits, and memory. Apply timeouts.
- **Mixed workload:** Consider separating executors for CPU transformations and blocking I/O callbacks if you need to protect p99 latency.
- **Many small pipelines:** Creating a new executor per request usually increases overhead; use pools tied to component lifecycle and reuse them.

Naming executors after their **workload characteristics** or isolation requirements makes configuration and monitoring easier to explain than "pool1", "pool2" in real applications.

## 10. Executor Rejection: thenApplyAsync Is Not a Guarantee That It Will Run

An `Executor` can reject a command when the pool has been shut down or when queue/worker capacity is exhausted. `ThreadPoolExecutor` typically signals this with `RejectedExecutionException` depending on the `RejectedExecutionHandler`.

When designing a pipeline:

- Do not assume every callback registered with `thenApplyAsync` will be accepted.
- With a custom executor, `execute(Runnable)` may throw an exception; rejection may **surface immediately at registration time** or **on the path that triggers the dependent stage**, depending on timing/implementation.
- Handle the error path properly; do not wait indefinitely on a Future whose completion you do not control.
- `AbortPolicy` makes overload explicit; `DiscardPolicy`/`CallerRunsPolicy` have different semantics and can cause tasks to be dropped or run on the caller.
- Do not use `CallerRunsPolicy` without evaluating whether the callback is safe to run on the request/event-loop thread or during executor shutdown.

### Example 5 — An Executor Intentionally Rejecting Callbacks

Create `RejectedExecutorDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;

public class RejectedExecutorDemo {
    public static void main(String[] args) {
        Executor rejecting = command -> {
            throw new RejectedExecutionException("not accepting");
        };

        boolean rejectionObserved = false;
        try {
            CompletableFuture<Integer> next =
                    CompletableFuture.completedFuture(10)
                            .thenApplyAsync(x -> x * 2, rejecting);
            next.join();
        } catch (RejectedExecutionException ex) {
            rejectionObserved = true;
        } catch (CompletionException ex) {
            rejectionObserved =
                    ex.getCause() instanceof RejectedExecutionException;
        }

        System.out.println("rejection observed = " + rejectionObserved);
    }
}
~~~

Run:

~~~bash
javac RejectedExecutorDemo.java
java RejectedExecutorDemo
~~~

Stdout in Java SE 17:

~~~text
rejection observed = true
~~~

The custom executor **always throws** `RejectedExecutionException` upon receiving a command. The code handles both common manifestations on the asynchronous dispatch path: the rejection propagates directly through the registration call, or is recorded into the dependent completion and wrapped in `CompletionException` on `join()`. It never prints a mapped value because the executor does not execute the command.

**Important:** Do not treat catching these two error paths as a complete overload solution: the caller must decide whether to return an error, retry with backoff, intentionally drop, or offload to a durable system according to business requirements.

## 11. Callback Failures and Exception Propagation

For example, the source completes with `10`, and the `thenApplyAsync` callback throws `IllegalStateException`. The dependent stage terminates **exceptionally**; the source may still have completed normally.

- `dependent.isCompletedExceptionally()` is true.
- `dependent.isDone()` is true, but that does **not** mean success.
- `dependent.join()` throws an unchecked `CompletionException` with the corresponding cause (except in special cases like cancellation).
- `dependent.get()` throws a checked `ExecutionException`; the cause is retrieved via `getCause()`.
- `exceptionally(fn)` can convert an error into a fallback value for the next stage.
- If `thenApplyAsync` is attached to a source that has **already failed/cancelled**, the mapping callback **is not run**; the dependent stage propagates the corresponding failure state.

### Example 6 — Error in Callback and Fallback

Create `AsyncMappingFailure.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncMappingFailure {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<Integer> mapped =
                    CompletableFuture.completedFuture(10)
                    .thenApplyAsync(value -> {
                        throw new IllegalStateException("mapping failed");
                    }, pool);

            CompletableFuture<Integer> recovered =
                    mapped.exceptionally(error -> -1);

            System.out.println("fallback = " + recovered.join());
            System.out.println("mapped exceptional = "
                    + mapped.isCompletedExceptionally());

            try {
                mapped.join();
            } catch (CompletionException ex) {
                System.out.println("cause = "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
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
javac AsyncMappingFailure.java
java AsyncMappingFailure
~~~

Stdout:

~~~text
fallback = -1
mapped exceptional = true
cause = IllegalStateException
~~~

`exceptionally` does not "fix" the old `mapped` stage; it creates **a new recovery stage**. `mapped` remains exceptional. Understanding this helps avoid confusion in error handling: which variable represents the original result, and which represents the fallback?

### What If the Source Is Already Exceptional?

~~~java
// Snippet, not a standalone program.
CompletableFuture<Integer> source =
        CompletableFuture.failedFuture(new IllegalArgumentException("bad"));

CompletableFuture<Integer> mapped =
        source.thenApplyAsync(x -> x * 2, executor);
// Mapper is not called because source did not complete normally.
// mapped completes exceptionally by propagation, with no mapped value.
~~~

To handle errors, consider `exceptionally`, `handle`/`handleAsync`, or `whenComplete`/`whenCompleteAsync` depending on whether you are **recovering a value**, **observing a side effect**, or **transforming both the result and the error**. Do not mistake `thenApplyAsync` for an error handler.

## 12. thenApplyAsync vs. thenComposeAsync: Mapping or Flattening?

`thenApplyAsync(fn, executor)` applies a function returning a **value U**. If the function returns `CompletableFuture<U>`, the result will be a Future **nested inside a Future**:

~~~text
CompletableFuture<T>
  .thenApplyAsync(T -> CompletableFuture<U>, executor)
        |
        v
CompletableFuture<CompletableFuture<U>>
~~~

`thenComposeAsync(fn, executor)` takes a function returning `CompletionStage<U>` and **flattens/composes** it so the result is `CompletableFuture<U>`:

~~~text
CompletableFuture<T>
  .thenComposeAsync(T -> CompletionStage<U>, executor)
        |
        v
CompletableFuture<U>
~~~

This difference has **nothing** to do with "which async stage has more threads"; it is the difference between **mapping** and **monadic flattening/dependency composition**.

### Which One Should You Use?

| Function | Appropriate method |
| --- | --- |
| `T -> U`, computes a plain value | `thenApply` / `thenApplyAsync` |
| `T -> CompletionStage<U>`, calls another async service | `thenCompose` / `thenComposeAsync` |
| Two independent Futures, need to combine both | `thenCombine` / `thenCombineAsync` |
| Only perform a side effect with the value, return `Void` | `thenAccept` / `thenAcceptAsync` |
| Only perform a task after completion, no input needed | `thenRun` / `thenRunAsync` |

### Example 7 — thenComposeAsync Does Not Block the Worker to Wait for the Child Future

Create `ComposeVsApply.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ComposeVsApply {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.completedFuture(3);

            CompletableFuture<CompletableFuture<Integer>> nested =
                    source.thenApplyAsync(x ->
                            CompletableFuture.completedFuture(x * 2), pool);

            CompletableFuture<Integer> flattened =
                    source.thenComposeAsync(x ->
                            CompletableFuture.supplyAsync(() -> x * 2, pool),
                            pool);

            System.out.println("nested result = "
                    + nested.join().join());
            System.out.println("flattened result = "
                    + flattened.join());
        } finally {
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
javac ComposeVsApply.java
java ComposeVsApply
~~~

Stdout:

~~~text
nested result = 6
flattened result = 6
~~~

`thenApplyAsync` in the first example returns **a Future inside a Future**, so main needs `join().join()`. `thenComposeAsync` takes an asynchronous computation and returns a flat Future. Even when using a **single-thread pool**, no starvation occurs in this example because the compose callback **returns the child Future and exits**, without blocking the worker via `join()` inside that callback.

**Do not write this instead**:

~~~java
// Anti-pattern snippet: blocking wait inside a worker of a single-thread pool.
source.thenApplyAsync(x ->
        CompletableFuture.supplyAsync(() -> x * 2, pool).join(),
        pool);
~~~

In a single-thread configuration, the outer callback occupies the worker and then blocks waiting for a child task submitted **to the same pool**; the child task has no free worker to run on. This can cause a **thread-pool starvation deadlock**. `thenComposeAsync` expresses the dependency without blocking a worker to wait for the child Future in that way.

## 13. thenApplyAsync and the Java Memory Model

Transitioning from the previous stage to the next is not an arbitrary plain variable read/write. `CompletableFuture` and `Future` provide completion and synchronization mechanisms so that the dependent callback receives the completed value properly, even when it runs on a different thread.

For a simple pipeline:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> "ready", executorA)
                .thenApplyAsync(value -> value + "!", executorB);
~~~

The subsequent callback runs when the previous stage completes normally; it receives the immutable String returned by the previous stage. You do not need `volatile` on the **`value` parameter** just to pass that Future value itself. The completion/execution synchronization guarantees ensure the result is handed over safely.

However:

- If a callback holds a reference to a **mutable object** that other threads continue to modify, `CompletableFuture` does not make those other mutations atomic.
- `sharedCounter++` in two concurrent callbacks can still suffer lost updates; use `AtomicInteger`, a lock, or an immutable reduce pattern when needed.
- Source completion does not automatically guarantee that an external transaction (DB/network) has committed if the out-of-JVM operation has not been synchronized/acked.
- Running a callback on another executor does not automatically transfer thread-local values from the source thread.
- If a callback launches another **fire-and-forget** task and returns, completion of the callback does **not** mean the child task has finished.

### Transferring Ownership of Mutable Objects

A safer design is:

1. Create an immutable DTO/snapshot before completing the stage.
2. Make that DTO/snapshot the result of the Future.
3. Have each callback only read the snapshot or create a new value.
4. If a callback must modify shared mutable state, use proper synchronization.
5. Do not continue mutating an object after "publishing" it while assuming the Future has locked the entire object graph.

This is general Java concurrency; it does not depend on any framework's transaction management or request-scope mechanism.

## 14. ThreadLocal and Mutable Execution Contexts

`ThreadLocal` stores state per **thread**, and does not automatically propagate context from the thread calling `thenApplyAsync` to another worker. Therefore:

~~~java
// Warning snippet, not a standalone program.
ThreadLocal<String> correlationId = new ThreadLocal<>();
correlationId.set("request-7");

future.thenApplyAsync(value -> {
    // Do not assume correlationId.get() == "request-7".
    return transform(value);
}, executor);
~~~

If this thread is a shared worker, you should also not rely on a leftover `ThreadLocal` from a previous request. If you actively set context on a worker, you must restore/clear it in a `finally` block or a verified safe adapter.

You can pass **immutable context** as part of the input object instead of relying on hidden thread-bound variables:

~~~java
// API snippet, declare record/context/method per application.
record Input(String correlationId, int value) {}

CompletableFuture<Input> inputStage =
        CompletableFuture.completedFuture(new Input("request-7", 21));

CompletableFuture<String> result =
        inputStage.thenApplyAsync(input ->
                input.correlationId() + ":" + (input.value() * 2),
                executor);
~~~

This is not a standalone program because the `executor` variable is configured elsewhere. The main point: context is **explicit data**, independent of which worker the scheduler picks.

## 15. Timeouts: Caller Wait Time Differs from Callback Execution Time

If the caller does:

~~~java
// API snippet inside a method that may throw TimeoutException/Exception.
String value = future.get(100, TimeUnit.MILLISECONDS);
~~~

Then `get(timeout)` limits **the caller's wait time**; it **does not automatically cancel** the `thenApplyAsync` callback waiting in the executor or currently running. The callback can still finish after the caller times out.

Java 17 also provides `CompletableFuture.orTimeout(timeout, unit)` to complete the Future **exceptionally with `TimeoutException`** if not yet completed, and `completeOnTimeout(value, timeout, unit)` to supply a fallback value. They affect the **completion state** of the `CompletableFuture` per contract; they do **not** mean the worker executing the application function will be interrupted or that side effects will be rolled back.

### Example 8 — Timeout While Callback Waits on a Latch, Then Still Completes

Create `AsyncWaitTimeout.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncWaitTimeout {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<Integer> mapped =
                    CompletableFuture.completedFuture(7)
                    .thenApplyAsync(value -> {
                        started.countDown();
                        try {
                            release.await();
                            return value + 1;
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(e);
                        }
                    }, pool);

            started.await();
            try {
                mapped.get(50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                System.out.println("wait timed out = true");
            }

            System.out.println("cancelled = " + mapped.isCancelled());
            System.out.println("done before release = " + mapped.isDone());

            release.countDown();
            System.out.println("result = " + mapped.join());
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
javac AsyncWaitTimeout.java
java AsyncWaitTimeout
~~~

Stdout on a normal run:

~~~text
wait timed out = true
cancelled = false
done before release = false
result = 8
~~~

`started.await()` confirms the callback has entered its body; it cannot return before `release` opens. Thus `get(50ms)` is guaranteed to time out on the caller. After the timeout, the stage is still pending; releasing the latch lets the callback return `8` normally. This avoids relying on an indeterminate `Thread.sleep` to create a delay.

**Production tip:** For I/O, set deadlines at the **I/O API** level (connect/read/request timeout) and design cooperative cancellation; do not assume a caller timeout means the connection has been safely closed.

## 16. CompletableFuture Cancellation Does Not Force-Interrupt the Callback

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` affects the **CompletableFuture state**. According to the `CompletableFuture` implementation documentation, `mayInterruptIfRunning` **has no effect in controlling the computation** as readers might expect from some `FutureTask` implementations.

This matters for `thenApplyAsync`:

- A cancelled stage can make `isDone()`/`isCancelled()` true and cause `join()` to throw `CancellationException`.
- A callback currently executing on a separate worker is **not guaranteed to be interrupted/stopped immediately** just because the dependent stage was cancelled.
- If the callback has already sent side effects to a DB/API, cancellation does not roll them back.
- Cancelling a dependent stage **does not automatically cancel** an independent source stage; conversely, failure/cancellation propagation through a dependent pipeline according to `CompletionStage` rules must be clearly understood.
- `exceptionally`/`handle`/`whenComplete` are not themselves mechanisms to stop a worker.

If running work must be stopped, use a **stop token**, deadlines, library timeouts, cooperative cancellation checks, and a separate **body actually stopped** signal when resource cleanup is needed.

### Do Not Rely on `isDone()` After Cancel as a Condition to Close Resources

A stage that completed exceptionally/was cancelled may no longer provide a normal result while the actual computation is still cleaning up or still running. Do not close a socket/object still in use by the callback solely based on the Future's state without a proper ownership protocol.

When multiple dependent stages share the same source, cancelling one branch also requires checking whether another branch still needs the source result; do not abort shared computation just because one caller stopped waiting.

## 17. Pipeline Errors and Where to Place Recovery Stages

A typical pipeline:

~~~text
supplyAsync(fetch, ioPool)
      |
      v
thenApplyAsync(parse, cpuPool)
      |
      v
thenApplyAsync(validate, cpuPool)
      |
      +---------- completed normally ---> thenAcceptAsync(persist, ioPool)
      |
      +---------- exceptional ----------> exceptionally(recover/log)
~~~

If `parse` fails, `validate` is not run and `persist` will not run along the normal `thenAccept` branch. This is critical so unvalidated data is not accidentally written.

Error handling options:

| API | When is it called? | What type does it return? |
| --- | --- | --- |
| `exceptionally(fn)` | When the previous stage is exceptional | A fallback value of the same result type |
| `handle(fn)` | On either success or failure | Transforms `(value, throwable) -> U` |
| `handleAsync(fn, executor)` | On either success or failure | Same, but mapping runs via executor |
| `whenComplete(action)` | On either success or failure | Observes side effects, preserves result type |
| `whenCompleteAsync(action, executor)` | On either success or failure | Same, action runs via executor |
| `exceptionallyAsync(fn, executor)` | When exceptional | Async recovery mapping, available in Java 17 |

Do not blindly return `null` from recovery and let a later stage invoke a method on `null`. Clearly define whether a **fallback** is valid for business semantics; sometimes it is best to propagate the failure and return an error to the caller.

When using a separate executor for error handling, remember that **even logging/recovery callbacks** can be queued or rejected if the executor is unavailable; do not build an error-reporting path that relies solely on a pool that is already failing/full.

## 18. A Heavy Callback Can Stall the Completion Path If You Use thenApply

This is a practical reason to choose `thenApplyAsync`: if `thenApply` runs on the thread completing the source, a CPU-heavy or blocking callback can hold that thread longer than expected. If the source completes on a latency-sensitive thread (an I/O event loop, request dispatcher, or a thread publishing results to many dependents), inline computation can slow down other operations.

~~~text
thenApply:
  source completed by thread X
           |
       heavy callback runs inline on completion path
           |
        X busy, cannot serve other work

thenApplyAsync(..., executor):
  source completed by thread X
           |
       submit dependent callback to executor
           |
        X can leave completion path sooner
           |
        callback waiting/running on executor
~~~

This is a **possibility**, not a guarantee that thread X will never do other work after submission. Handing off a task also has overhead and can be rejected; a direct/caller-runs executor may still run the callback inline. For very tiny mappings, the extra scheduling cost can exceed the mapping work itself.

### Starting Rules of Thumb

- `thenApply`: **very short, pure, non-blocking** function acceptable to run on the completion/caller path.
- `thenApplyAsync(fn)`: want an async boundary, CPU-oriented task, no special resource isolation needed; common pool has been evaluated.
- `thenApplyAsync(fn, executor)`: need explicit workload isolation/lifecycle/threads/queue policy, or blocking callback should have a dedicated I/O pool.
- `thenComposeAsync`: mapper returns an async operation; need to compose instead of blocking on a child Future.

Choose after measuring; do not automatically add `Async` to every stage. Executing a chain of hundreds of tiny callbacks through an executor can create unnecessary scheduler overhead.

## 19. Thread Pool Starvation If a Callback Blocks Waiting for a Task in the Same Pool

Suppose you use `Executors.newSingleThreadExecutor()`, and a `thenApplyAsync` callback runs on the sole worker, then inside it submits another task to **the same pool** and calls `join()` to wait. The child task sits in the queue while the sole worker is held by the parent callback. That can be a **thread-pool starvation deadlock**.

~~~java
// Dangerous snippet: DO NOT run directly as a program.
source.thenApplyAsync(value ->
        CompletableFuture.supplyAsync(
                () -> slowTransform(value), sameSingleThreadPool).join(),
        sameSingleThreadPool);
~~~

To avoid this:

1. Use `thenCompose`/`thenComposeAsync` to **compose** the child Future instead of blocking the parent callback.
2. Avoid dependency cycles where task A waits for B, and B must be run by the resource A is occupying.
3. Put timeouts on waits where meaningful (not a substitute for correctness).
4. Separate workloads with special dependencies or provision sufficient resources with an appropriate protocol.
5. Do not hold a lock inside a callback and wait for another task that needs that same lock.

Do not assume that because the default executor is a work-stealing `ForkJoinPool`, all blocking Future waits are safe. Work stealing does not resolve dependency cycles or finite downstream resources.

## 20. Changing Executors Can Change Priority and Completion Order

In a pipeline `A -> B -> C`, stages have a **dependency relationship**: B cannot run its mapper before A has completed normally; C cannot run its mapper before B has completed normally. However, if **two independent branches** both depend on the source:

~~~text
             source
              /  \
             /    \
    thenApplyAsync A   thenApplyAsync B
       executorA          executorB
             \            /
              \          /
               thenCombine
~~~

There is no guarantee that A finishes before B or vice versa. Choosing different executors affects wait time, CPU, queue policy, and thread-local context; it does **not** impose an ordering between two independent branches.

If you need to merge results, use `thenCombine`/`thenCombineAsync` or `allOf` and then read the results, rather than combining via side effects on an unsynchronized shared `ArrayList`.

### Fan-Out and Resource Budgeting

One source can trigger many async dependents at once. If 1,000 source stages all complete, each fanning out 10 callbacks, the number of pending tasks can grow very quickly. Do not treat the mere existence of an `Executor` as proof that the backlog is bounded.

Some mitigations:

- Reduce fan-out / batch inputs where appropriate.
- Rate-limit / admission-limit at the producer.
- Use an executor with a bounded queue and a clear overload policy.
- Keep the memory footprint of captured closures small.
- Cancel/expire work that is no longer valuable per protocol.
- Monitor queue length, queue wait, rejections, active workers, and completion counts.
- Use representative execution times when sizing, not just empty-callback microbenchmarks.

## 21. Impact of Shutdown and Dependencies Waiting on an Executor

When a component owns an `ExecutorService` and uses it in a pipeline, shutdown order is critical:

- **Stop accepting new pipelines** before stopping the executor; otherwise, late-completing source stages may try to submit new callbacks into an already shut-down executor.
- If a callback is only registered while the source has not completed, the callback **has not been submitted to the executor yet**; shutting down early can prevent the dependent stage from executing normally.
- `executor.shutdown()` does not wait for all pipelines to finish before returning; it only initiates a graceful shutdown per the executor contract.
- Keep handles to **final pipeline stages** and wait with `get/join` or `allOf` with an appropriate deadline before shutting down the executor if you want to drain.
- `shutdownNow()` is best-effort interruption and returns not-yet-started tasks; it does not automatically roll back task/`CompletableFuture` side effects.
- For the shared common pool, do not call shutdown on it as if the pool belonged to a single module.
- When an executor rejection occurs, do not let monitoring record "pipeline completed" if a dependent stage actually failed.

### Shutdown Pattern Principle

~~~java
// Architectural snippet, not standalone.
stopSubmittingNewPipelines();
awaitOwnedPipelineFuturesWithDeadline();
ownedExecutor.shutdown();
if (!ownedExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
    ownedExecutor.shutdownNow();
}
~~~

`awaitOwnedPipelineFuturesWithDeadline` should collect successful/exceptional/cancelled outcomes as needed, rather than just calling `join` and ignoring exceptions. If there are errors, decide whether to retry/compensate/log before leaving the component. With cancellation, still-running bodies may need to finish separate cleanup.

## 22. Observing Executors and Callbacks in Production

When a `thenApplyAsync` stage is slow, break the time down into:

~~~text
T0: previous stage completes
    |
    | callback eligible; submitted to executor
    v
T1: executor receives/queues callback
    |
    | QUEUE WAIT TIME
    v
T2: worker starts mapper
    |
    | EXECUTION TIME
    v
T3: mapper returns or throws
    |
    | dependent completion / downstream notification
    v
T4: next stage starts/receives result
~~~

A callback body that runs in 2 ms but has a 200 ms queue wait will significantly increase the latency depending on that stage. Logging only the time inside the body misses the waiting part.

Useful metrics:

| Metric | Why it is needed |
| --- | --- |
| Parent stage completion time | Distinguish slowness in the source from slowness in the dependent |
| Submit-to-start (queue wait) | Detect executor saturation |
| Callback execution time p50/p95/p99 | Detect blocking/CPU/GC contention |
| Pool active/queued/completed counts | View processing capacity and backlog |
| Rejected tasks | Detect overload or shutdown races |
| Timeout/cancel/exceptional completions | Assess the rate of invalid/unsuccessful outcomes |
| Heap/GC/allocations | Captured closures/queued tasks may retain object graphs |
| Thread dumps | Detect workers blocked on locks, `Future.join`, or I/O |
| Downstream connections/rate limits | Adding workers does not always increase throughput |

`ThreadPoolExecutor` getters are snapshots/estimates and cannot replace an admission protocol. Checking `queue.size() < limit` and then submitting is not atomic because another thread can submit between the two operations.

For the common pool, metrics such as `getQueuedTaskCount`, `getQueuedSubmissionCount`, `getActiveThreadCount`, and `getStealCount` are diagnostic estimates; do not use a single snapshot as proof that a module's stages are finished.

## 23. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "`thenApplyAsync` always creates a new thread." | Usually uses an executor/pool; may reuse workers, and a direct `Executor` can run inline |
| "`thenApplyAsync` definitely runs in parallel with the previous stage." | The mapper depends on the source and is only eligible once the source has completed normally |
| "`thenApply` always runs on the thread calling registration." | May run on the thread completing the previous stage, or on the caller if the stage is already completed |
| "`thenApplyAsync(fn)` uses a private pool for the pipeline by default." | Usually defaults to `commonPool()`, barring fallback or another implementation |
| "Passing an executor to the first stage makes the whole chain inherit it." | Each async dependent method requires considering its own executor |
| "Having an executor means it cannot reject." | The executor may be shut down or have a full bounded queue |
| "`Async` means non-blocking I/O callback." | The callback can still block; `Async` primarily describes scheduling |
| "`join` always returns a value immediately." | It can block until the stage completes; errors usually throw `CompletionException` |
| "`thenApplyAsync` handles exceptions from the source." | The mapper is not called if the source is exceptional; use recovery APIs |
| "A failed source still lets the mapper compute a normal value." | The dependent stage normally propagates exceptional completion |
| "`CompletableFuture.cancel(true)` always interrupts the worker." | The interrupt parameter has no effect in the `CompletableFuture` implementation |
| "Caller `get(timeout)` timing out cancels the pipeline." | A caller timeout does not automatically cancel the computation |
| "All dependent stages complete in registration order." | Independent branches may execute in different orders |
| "`thenApplyAsync` is right when the function returns a Future." | `thenComposeAsync` flattens async dependencies |
| "A separate pool means more CPU." | CPU, heap, GC, and downstream services are still shared resources |
| "Having the common pool prevents deadlocks." | Blocking waits, dependency cycles, and lock contention can still get stuck |
| "`ThreadLocal` automatically propagates to the worker." | There is no automatic propagation of ordinary `ThreadLocal` |
| "Shutting down the executor right after registering callbacks is enough." | The source may not be completed yet; the callback is not submitted yet and may be rejected after shutdown |
| "A small `thenApplyAsync` is always faster than `thenApply`." | Scheduling overhead/queue wait can exceed the mapping work |
| "`isDone` true means all side effects have been rolled back/cleaned up." | Exceptional/cancelled completion and actual cleanup are different states |

## 24. Self-Check

**Question 1.** Does `CompletableFuture.completedFuture(10).thenApply(x -> x+1)` create a different stage?  
**Answer:** Yes, it returns a new `CompletableFuture<Integer>` with value `11`; the old source still holds `10`.

**Question 2.** Where does `thenApplyAsync(fn)` run by default in Java 17?  
**Answer:** Usually via `ForkJoinPool.commonPool()`; there is a fallback when the common pool does not support parallelism of at least 2.

**Question 3.** Does `thenApplyAsync(fn, executor)` guarantee switching threads from the caller?  
**Answer:** Not a mandatory contract for every `Executor`; a direct `Executor` can call `run` inline.

**Question 4.** When the source `CompletableFuture` is not yet completed, does calling `thenApplyAsync` make the mapper run immediately?  
**Answer:** No. The mapper waits for the source to complete normally before being triggered.

**Question 5.** The source completed exceptionally. Does the `thenApplyAsync` callback run to "fix the error"?  
**Answer:** No; you need `exceptionally`, `handle`, or the corresponding recovery API.

**Question 6.** Which thread can `thenApply` run on when the source is already completed?  
**Answer:** It can run immediately on the caller/registration thread; in the case where the source completes after registration, it usually runs on the completion path.

**Question 7.** If you want to separate CPU transforms from blocking database calls, what should you do?  
**Answer:** Consider separate executors—a CPU pool and an I/O pool with timeouts, capacity limits, and an overload policy; pass the executor explicitly to each async stage that needs isolation.

**Question 8.** An earlier stage uses `poolA`, and a later stage calls `thenApplyAsync(fn)` without an executor. Will it still definitely run on `poolA`?  
**Answer:** No. The later stage uses `CompletableFuture`'s default async facility, usually the common pool.

**Question 9.** What type does `thenApplyAsync(x -> CompletableFuture.supplyAsync(...), pool)` return?  
**Answer:** Usually `CompletableFuture<CompletableFuture<U>>`; use `thenComposeAsync` if you want to flatten it to `CompletableFuture<U>`.

**Question 10.** A worker of a single-thread pool calls `supplyAsync(..., samePool).join()` inside a running mapper. What is the risk?  
**Answer:** Thread-pool starvation deadlock because the child task waits for the worker currently occupied by the parent mapper.

**Question 11.** The mapper throws `IllegalStateException`. What does `join` on the dependent stage do?  
**Answer:** Usually throws `CompletionException` with `IllegalStateException` as its cause.

**Question 12.** The executor has been shut down; will `thenApplyAsync(fn, executor)` still definitely run the callback?  
**Answer:** No. Submission may be rejected; you must handle failure/shutdown races.

**Question 13.** The caller's `get(50, MILLISECONDS)` times out; is the callback automatically cancelled?  
**Answer:** No. A timeout on the waiting thread does not automatically cancel the `CompletableFuture`.

**Question 14.** Does `future.cancel(true)` guarantee interrupting a running `Supplier`/mapper?  
**Answer:** No. `CompletableFuture` cancellation changes the completion state and does not force-interrupt executing code.

**Question 15.** Why shouldn't you use an ordinary `ThreadLocal` to pass a request ID across `thenApplyAsync`?  
**Answer:** The callback may run on a different worker; ordinary `ThreadLocal` does not automatically propagate values from the caller.

**Question 16.** When is `thenApply` usually a better fit than `thenApplyAsync`?  
**Answer:** When the mapper is short, pure, non-blocking, and safe to run on the completion path without extra scheduling overhead.

## Java SE 17 References

- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenApply/thenApplyAsync`, default async facility, explicit executors, cancellation, error handling.
- [`CompletionStage` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): dependent stages, `thenComposeAsync`, `thenCombine`, and execution rules.
- [`Executor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): the `execute(Runnable)` contract.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): worker pool management and shutdown.
- [`ThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queueing, rejection, lifecycle, and monitoring.
- [`ForkJoinPool` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, work-stealing, shared-resource considerations.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, completion, and cancellation.
- [`RejectedExecutionException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionException.html): when an executor rejects a task.
- [`ThreadLocal` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread context.
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronization, memory visibility, and happens-before.

**Remember:** `thenApplyAsync` separates **the dependency condition** from **where the mapping executes**. Use `thenApply` for short transforms that can run inline; use `thenApplyAsync(fn)` when the default async facility is acceptable; use `thenApplyAsync(fn, executor)` when you need to explicitly choose **worker resources, queue/rejection policy, and lifecycle**. Every choice still requires considering deadlines, error propagation, backpressure, thread context, and whether downstream calls are blocking.
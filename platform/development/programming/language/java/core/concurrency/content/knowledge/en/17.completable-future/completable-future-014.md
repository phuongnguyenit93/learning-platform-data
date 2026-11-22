# Limiting Concurrency When Creating Bulk Futures with CompletableFuture

## 1. The problem: thousands of futures do not mean thousands of tasks should run concurrently

`CompletableFuture<T>` helps represent a result that may complete in the future, compose processing steps, and collect errors. When processing many inputs, a common way to write it is:

```java
// Snippet: executor is already declared; items is List<Item>.
List<CompletableFuture<Result>> futures = items.stream()
        .map(item -> CompletableFuture.supplyAsync(
                () -> process(item), executor))
        .toList();

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])
).join();
```

This is **only a snippet**: `Item`, `Result`, `items`, `executor`, and `process` are not declared. It highlights a problem: **a loop can submit all tasks before waiting for them to finish**.

If the list has 100,000 elements:

- 100,000 `CompletableFuture` instances may be created and held in memory.
- The executor may have only 8 workers, yet its **queue** can still accept a huge number of tasks.
- If each task performs I/O, opens connections, or calls downstream services, the worker limit is not necessarily the limit on **initiated** external operations (especially with asynchronous I/O).
- Memory used for tasks, lambdas, captured objects, futures, and metadata grows with the number of submitted items; overload can occur **before** workers finish processing.

**The goal of concurrency limiting** is to keep the number of tasks actively using a resource **within a clear threshold** and, when needed, keep the number of tasks waiting to be admitted under control as well.

This article focuses on **general Java concurrency** with **Java 17+** JDK, without depending on Spring or other frameworks.

## 2. Distinguishing four quantities that are often conflated

| Quantity | Meaning | Control mechanism |
| --- | --- | --- |
| **Number of input items** | Total amount of work to resolve | Batching, data streaming, pagination |
| **Number of created futures** | Number of objects representing task state | Create only within a bounded window, avoid holding unbounded results |
| **Number of tasks currently executed by workers** | Work that has started running in the executor | Pool size, executor admission |
| **Number of truly active external operations** | For example, sent HTTP requests or unanswered database queries | Semaphore/bulkhead tied to the **actual I/O lifecycle** |

**A `CompletableFuture` is not necessarily a thread.** A future may already be completed, waiting as a task in a queue, representing a `thenApply` step, or tracking an I/O operation that does not block a worker.

Similarly, **`CompletableFuture.allOf(...)` only combines completion signals; it does not limit concurrency**. `allOf` does not regulate queue size, create backpressure, or guarantee that all results succeeded.

### Concurrency, parallelism, throughput, and rate limit

- **Concurrency**: the number of work items existing/in-flight simultaneously at a chosen boundary.
- **Parallelism**: the number of work items actually executing in parallel, such as across multiple CPU cores.
- **Throughput**: the number of work items completed per second, depending on duration and processing capacity.
- **Rate limit**: a limit on the number of work items started per unit of time (e.g., requests/second).

`Semaphore(10)` limits **the number of permits that can be held simultaneously**, and does not directly promise “at most 10 requests per second”. If requests return very quickly, it still allows many requests to start within one second. Conversely, if requests are very slow, only 10 requests may remain active while throughput is low.

A system often needs **both a concurrency limit and limits on request creation rate, connection count, and queue size**, depending on the resource type.

## 3. Why doesn't a fixed thread pool completely solve fan-out?

`Executors.newFixedThreadPool(8)` creates an executor with a fixed number of workers. That is useful for **blocking tasks running on workers**: by design, no more than the worker count will execute tasks in the pool at the same time.

However, `newFixedThreadPool` typically has a **practically unbounded work queue**. A loop creating tens of thousands of `supplyAsync` calls can still push tens of thousands of tasks into the queue:

```text
Fast producer:
  submit 1, 2, 3, ... 100000
               |
               v
  Executor: 8 running workers
            |
            +-- queue: many unstarted tasks
               |
               v
          Memory / latency / backlog
```

Do not assume:

- “The pool has 8 workers, so submitting 100,000 tasks does not consume significant memory.”
- “There are only 8 workers, so at most 8 futures are incomplete.”
- “Whenever `allOf.join()` returns, every future succeeded.” If one input future fails, `allOf` also completes exceptionally; errors must be handled.
- “Increasing the pool size will always make the program faster.” Increasing parallelism can overload downstream services, increase context switching, or cause lock contention.

**There are two distinct layers of limits:** limiting **executing** tasks (actively using workers/resources) and limiting **admission/backlog** (work allowed to enter the pipeline). A large problem often requires controlling both.

## 4. Approach 1: fixed window/batch processing

This is the easiest approach to explain: create at most `windowSize` futures per batch, wait for the entire batch to finish, and only then create the next batch.

Pros:

- The number of “active futures in a batch” is clearly bounded.
- Easy to apply when data is already batched or one batch needs all results before moving to the next.
- No semaphore needed, and easy to manage the executor in the calling scope.

Limitations:

- **Barrier at the end of a batch**: if one task in a batch is very slow, the remaining slots may sit idle waiting for that slow task. Thus throughput may be lower than a **rolling window** model that always replenishes a task when one completes.
- If all inputs are already loaded into a `List` in memory, batching only limits the number of futures and **does not automatically bound input memory**.
- `allOf.join()` has no built-in timeout; if tasks can hang, design explicit timeouts and cleanup.

### Standalone Java 17+ example: at most 4 futures per batch

Create `WindowedBatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WindowedBatchDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newFixedThreadPool(8);
        final int windowSize = 4;
        int total = 0;
        int batches = 0;

        try {
            for (int start = 1; start <= 10; start += windowSize) {
                List<CompletableFuture<Integer>> window =
                        new ArrayList<>();

                for (int value = start;
                     value < start + windowSize && value <= 10;
                     value++) {
                    final int input = value;
                    window.add(CompletableFuture.supplyAsync(
                            () -> input, executor));
                }

                CompletableFuture.allOf(
                        window.toArray(new CompletableFuture<?>[0])
                ).join();

                for (CompletableFuture<Integer> future : window) {
                    total += future.join();
                }
                batches++;
            }
        } finally {
            executor.shutdown();
        }

        System.out.println("Processed inputs: 10");
        System.out.println("Sum: " + total);
        System.out.println("Batches: " + batches);
    }
}
```

Compile/run with JDK 17+:

```bash
javac WindowedBatchDemo.java
java WindowedBatchDemo
```

Output:

```text
Processed inputs: 10
Sum: 55
Batches: 3
```

The three batches contain inputs 1–4, 5–8, and 9–10 respectively. Each batch creates at most four futures and waits, so it never actively submits all ten tasks at once. `total` is the sum of numbers 1 to 10, equal to 55, regardless of worker completion order. The pool has eight workers, but the **window** only allows at most four tasks from the current batch.

**Note on errors:** the example only uses tasks that always succeed. If a future fails, `allOf(...).join()` can throw `CompletionException`; you must have a policy for marking errors, handling partial results, and stopping/continuing batches. `finally` still calls `shutdown`, but `shutdown` does not wait with a deadline. For tasks that may hang, add timeouts, cancellation, and termination monitoring.

## 5. Approach 2: Semaphore acquiring a permit **before submitting**

To continuously replenish work without creating unbounded futures, you can use a `Semaphore` representing “the right to have one task admitted/running in the system”.

Pattern:

```text
Producer has item
      |
      v
permits.acquire()  <--- if out of permits, producer must wait
      |
      v
create CompletableFuture / submit to executor
      |
      v
supplier runs and finishes (even if throwing an exception)
      |
      v
finally { permits.release(); }
      |
      v
producer can submit the next item
```

**The key point is where `acquire()` is placed:** perform it **before** `supplyAsync()`, so the producer **cannot create more than the limit of incomplete work**. If you put `semaphore.acquire()` **inside** each supplier after calling `supplyAsync` hundreds of thousands of times, all futures/tasks are still created and queued; the semaphore then only limits the code section inside the supplier, **not the amount of submitted work**.

Another rule: **release the permit exactly once for each successful acquire**. If the executor rejects the submission, the producer must return the permit. If the task starts and finishes normally or throws an exception, the supplier should release the permit in `finally`.

### Java 17+ example: limit to at most 3 admitted/unfinished tasks

Create `SemaphoreFanOutDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreFanOutDemo {
    static CompletableFuture<Integer> submitBounded(
            int input,
            ExecutorService executor,
            Semaphore permits,
            AtomicInteger active,
            AtomicInteger peak) throws InterruptedException {

        permits.acquire(); // Block producer before creating future.

        try {
            return CompletableFuture.supplyAsync(() -> {
                int now = active.incrementAndGet();
                try {
                    peak.accumulateAndGet(now, Math::max);
                    return input * input;
                } finally {
                    active.decrementAndGet();
                    permits.release(); // End of supplier execution.
                }
            }, executor);
        } catch (RejectedExecutionException e) {
            permits.release(); // Executor did not accept the task.
            throw e;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        final int maxInFlight = 3;
        Semaphore permits = new Semaphore(maxInFlight);
        ExecutorService executor = Executors.newFixedThreadPool(6);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<CompletableFuture<Integer>> futures = new ArrayList<>();

        try {
            for (int input = 0; input < 12; input++) {
                futures.add(submitBounded(
                        input, executor, permits, active, peak));
            }

            CompletableFuture.allOf(
                    futures.toArray(new CompletableFuture<?>[0])
            ).join();

            int sum = futures.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("Results: " + futures.size());
            System.out.println("Sum of squares: " + sum);
            System.out.println("Peak <= 3: " + (peak.get() <= 3));
            System.out.println("Active after completion: "
                    + active.get());
            System.out.println("Available permits: "
                    + permits.availablePermits());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                throw new IllegalStateException("Executor did not stop");
            }
        }
    }
}
```

Run:

```bash
javac SemaphoreFanOutDemo.java
java SemaphoreFanOutDemo
```

Output when tasks are not unexpectedly cancelled:

```text
Results: 12
Sum of squares: 506
Peak <= 3: true
Active after completion: 0
Available permits: 3
```

Explanation:

1. Although the pool has up to six workers, **the producer only grants at most three permits**. It does not create a fourth future while three permits are still held.
2. The supplier computes the square of inputs from 0 to 11; the sum of squares is 506.
3. `active` observes how many suppliers are currently running; `peak` records the maximum value seen. The actual peak number can be 1, 2, or 3 depending on scheduling, so the example only asserts **`peak <= 3`**, rather than printing “peak is definitely 3”.
4. The supplier's `finally` releases the permit **before the future is completed**. When `allOf.join()` returns normally, all suppliers have completed, and the permit count returns to 3.
5. If `supplyAsync` is **rejected by the executor before accepting the task**, the catch branch releases the acquired permit. This is the pattern for executors with the standard `RejectedExecutionException` contract.
6. `permits.acquire()` can throw `InterruptedException` before granting a permit; in that case you must not release because the producer never owned a permit.
7. `Semaphore` limits the number of admitted/unfinished invocations in this logic, not the start rate per second. An optional fair semaphore has its own overhead/semantics and does not automatically guarantee system-wide fairness.

**Intentional limitation of the example:** the futures are internal, are not cancelled while waiting in the queue, and the producer processes finite inputs. With complex cancellation or deadlines, **permit ownership** must be redesigned (section 8). Do not copy this pattern into a library with arbitrary `cancel()` without handling the path where a task has not started yet.

## 6. Approach 3: Executor with a bounded queue and rejection policy

Another strategy is to **bound admission** through executor configuration:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.AbortPolicy()
);
```

This is a snippet requiring the corresponding imports; the resource owner must shut down the executor. This configuration has at most two workers and a queue holding at most 16 tasks. When both workers and queue are at capacity, `execute()` may be rejected according to the rejection policy.

Common policies:

| Policy | When pool is saturated | Consequence to remember |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Caller knows it was rejected and must retry/report overload properly |
| `CallerRunsPolicy` | If executor is not shut down, runs task **on the caller thread** | Indirect backpressure, but caller can be blocked for a long time; worker count no longer describes all execution places |
| `DiscardPolicy` | Drops the task | If caller is not notified, work can be lost |
| `DiscardOldestPolicy` | Drops the oldest waiting task and retries | Needs a clear policy for important tasks and deadlines |

**Specific warning with `CompletableFuture.supplyAsync`:** if the rejection handler **drops the task without throwing an exception**, a created `CompletableFuture` may **never complete**. Therefore, do not use `DiscardPolicy` or silent policies for work requiring results without a separate cancellation/timeout and diagnostic protocol.

`CallerRunsPolicy` executes the task directly on the submitting thread, so a supplier may run **synchronously inside the `supplyAsync` call itself** when the pool is saturated. That provides backpressure, but can slow down the producer or cause deadlock if the caller holds a lock that the task needs.

### Java 17+ example: demonstrating bounded queue and rejection

Create `BoundedQueueRejectionDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedQueueRejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try {
            pool.execute(() -> {
                firstStarted.countDown();
                try {
                    release.await();
                    completed.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            firstStarted.await(); // Worker is holding the execution slot.
            pool.execute(() -> completed.incrementAndGet()); // Queue has 1.
            boolean rejected = false;
            try {
                pool.execute(() -> completed.incrementAndGet());
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            System.out.println("Third rejected: " + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            throw new IllegalStateException("Pool did not stop");
        }
        System.out.println("Completed: " + completed.get());
    }
}
```

Run:

```bash
javac BoundedQueueRejectionDemo.java
java BoundedQueueRejectionDemo
```

Output without external interrupts:

```text
Third rejected: true
Completed: 2
```

Because the first task is waiting on `release`, the sole worker cannot run the second task yet; the queue only has one slot, so the third task is not accepted and `AbortPolicy` throws an exception. Main opens the gate in `finally` so the worker completes the two accepted tasks, then waits for the pool to terminate.

The example does not need `sleep()` to “guess that the worker is busy”. `CountDownLatch` sets the exact milestone: the first worker has started before the test submits the second task.

**How this differs from Semaphore:** a bounded queue can accept **2 workers + 16 queued**, i.e., up to 18 tasks in the snippet's configuration, but it does not automatically block the producer before calling submit if `AbortPolicy` is used. A semaphore sets the **total in-flight count** right at the producer; a bounded executor sets **admission limits and overload policy** at the executor. Both mechanisms can be combined, but you should not add multiple limiting layers without defining who owns the permit and how rejections are handled.

## 7. Why is a semaphore inside the supplier not enough to limit futures?

An anti-pattern:

```java
// Snippet illustrating the PROBLEM with the number of submitted tasks.
List<CompletableFuture<Result>> futures = items.stream()
        .map(item -> CompletableFuture.supplyAsync(() -> {
            permits.acquireUninterruptibly();
            try {
                return process(item);
            } finally {
                permits.release();
            }
        }, executor))
        .toList();
```

This is not a standalone file, because `Result`, `items`, `process`, `permits`, and `executor` are not declared.

Even with only 5 permits, the stream loop can still **create all futures** and queue all suppliers into the executor. Some workers are occupied **just waiting for a permit**, reducing worker efficiency. With a small pool, workers holding permits and tasks waiting for permits can cause pressure/starvation if there are interdependencies.

**Solutions depending on requirements:** acquire the permit **before** creating/submitting the task (as in section 5), submit in windows (section 4), or use bounded executor admission (section 6). If it is an **asynchronous I/O operation that does not occupy a worker**, acquire the permit when **the real I/O starts**, and release when **the real I/O finishes**, not merely when a future wrapper is considered completed due to a timeout.

## 8. Cancellation: a subtle bug when using permits with CompletableFuture

The `submitBounded` pattern in section 5 is intentionally simple, but **it is not a full cancellation-aware pattern**. This is especially important when thousands of futures are created and external callers have the right to call `cancel(...)`.

### Case A: cancelling a future before the supplier runs

`CompletableFuture.cancel(...)` completes the future in a cancelled state, but **does not guarantee cancelling a queued task or interrupting a worker** the way some `FutureTask` usages do.

For a future from `CompletableFuture.supplyAsync`, if it is cancelled **before the supplier starts**, the executor may still pick up the internal runnable, see that the future is already completed, and **not invoke the supplier**. Then `finally { permits.release(); }` **inside the supplier never runs** → the permit can **be leaked forever**.

### Case B: releasing the permit immediately in `whenComplete` of a cancelled future

If you attach `future.whenComplete((value, error) -> permits.release())`, cancellation can cause the callback to run **as soon as the future transitions to cancelled**, even though the supplier is **actually still running and using the resource**. The producer then receives a permit too early and initiates new work, causing **actual concurrency to exceed the limit**.

Therefore:

- **The completed state of a CompletableFuture** can differ from **the task actually having stopped using the resource**.
- `cancel(true)` on `CompletableFuture` does not mean the worker is guaranteed to be interrupted; the `mayInterruptIfRunning` parameter does not control the `CompletableFuture` implementation's handling the way `FutureTask` does.
- `orTimeout(...)` / `completeOnTimeout(...)` change how the future completes; they **do not automatically stop running I/O or CPU work**. They can cause `whenComplete` to report completion earlier than the physical operation.
- For accurate cancellation-aware admission, you must manage **actual task state** (queued/running/finished/cancelled), permit ownership, and an **exactly-once** permit release mechanism, or use a specialized executor/queue/cancellation policy with a clear contract.

**Do not mechanically fix this by releasing both in the supplier's finally and when the future completes**: double release increases the permit count, breaking the concurrency limit.

### Java 17+: future timeout is not worker completion

Create `FutureTimeoutVsWorkDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutVsWorkDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch workerFinished = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "done";
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            workerFinished.countDown();
                        }
                    }, executor);

            started.await();
            boolean timeoutSeen = false;
            try {
                future.orTimeout(20, TimeUnit.MILLISECONDS).join();
            } catch (CompletionException e) {
                if (!(e.getCause() instanceof TimeoutException)) {
                    throw e;
                }
                timeoutSeen = true;
            }

            System.out.println("Future timed out: " + timeoutSeen);
            System.out.println("Worker done before release: "
                    + (workerFinished.getCount() == 0L));

            release.countDown();
            if (!workerFinished.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not finish");
            }
            System.out.println("Worker done after release: true");
        } finally {
            release.countDown();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor did not terminate");
            }
        }
    }
}
```

Compile/run:

```bash
javac FutureTimeoutVsWorkDemo.java
java FutureTimeoutVsWorkDemo
```

Normal output:

```text
Future timed out: true
Worker done before release: false
Worker done after release: true
```

**Explanation:** the worker signaled `started` and waited on the `release` latch. The future is allowed to complete exceptionally with `TimeoutException` after 20 ms, but the worker **is still waiting on the latch** because the main thread has not opened the gate yet. Hence `workerFinished` has not reached 0, even though the future timed out. Only after main opens the gate does the worker finish and `workerFinished` confirm it.

This scenario proves: **looking only at a timed-out/cancelled future is not enough to release the slot of a physical operation**, especially for HTTP/database/CPU tasks with side effects.

## 9. Limiting concurrency for truly asynchronous I/O calls

For example, `HttpClient.sendAsync` (Java 11+) can send a request and return a `CompletableFuture<HttpResponse<T>>` without occupying an application worker for the entire wait time.

With this style, the goal is usually **at most N requests actually in flight over the network**, not at most N suppliers running on a thread pool.

Conceptual model:

```text
Request not yet sent
      |
      v
Acquire permission to start external operation
      |
      +-- no slot available: hold item in bounded queue
      |
      v
Start asynchronous I/O
      |
      v
I/O actually completes (success/failure/cleanup)
      |
      v
Record outcome, release slot, feed next item
```

**Important note:** a `CompletableFuture` callback may run on the thread that completes the stage or the thread that registers the callback if the stage is already complete. Do not use callbacks to run heavy blocking work on I/O/event loop threads without controlling the executor.

A common pattern is a **rolling window**: keep at most K real operations active; whenever one operation finishes, initiate the next unsent item. You need a bounded input queue or streaming iterator, and handle errors, timeouts, cancellation, and network resource limits according to the API.

**Do not use `supplyAsync(() -> httpClient.sendAsync(...))` and release the permit when the supplier returns**: the supplier only returns **a future of the request**, which can finish almost immediately while the HTTP request is still active. To represent the external result, you must use `thenCompose`/manage a stage reflecting **actual request completion**. However, timing out/cancelling a wrapper stage still requires a permit-ownership policy as in section 8.

### Completion callbacks and accounting

For an operation that is not prematurely completed artificially, a `whenComplete` callback can be convenient for recording errors and releasing the slot after the work **actually** finishes. But you must clearly define **which future is the source of truth for the physical operation**, who has the right to cancel it, and whether cancellation has completed cleanup. Do not blindly attach release to a wrapper whose state is altered by `orTimeout` and assume the background operation has stopped.

## 10. Error handling with `allOf` and collecting results

`CompletableFuture.allOf(f1, f2, ...)` returns a `CompletableFuture<Void>` that completes when all input futures have completed, however:

- It does not return a typed list of results.
- If at least one future fails, the combined future **completes exceptionally**; `join()` can throw `CompletionException`.
- An input future completing normally does not mean the business output is valid if code turned an error into a default value.
- `allOf` **does not automatically cancel** other work when one future fails.
- It does not limit concurrency or the number of futures held in memory.
- `CompletableFuture.join()` throws unchecked `CompletionException`/`CancellationException` depending on state; `get()` uses checked `ExecutionException`/`InterruptedException`.

### Collecting outcomes without letting one error mask everything

```java
// Snippet: futures is an already-created List<CompletableFuture<String>>.
List<CompletableFuture<String>> safe = futures.stream()
        .map(f -> f.handle((value, error) ->
                error == null ? "OK: " + value
                              : "FAIL: " + error.getClass().getSimpleName()))
        .toList();

CompletableFuture.allOf(
        safe.toArray(new CompletableFuture<?>[0])
).join();

for (CompletableFuture<String> future : safe) {
    System.out.println(future.join());
}
```

This is a **snippet**: `futures` and imports are omitted. The purpose is to **convert each outcome into a value** so that every item's success/failure can be read. `handle` here only distinguishes errors by class for illustration; production code needs to log the cause, preserve the index/input ID, and decide whether to retry.

If a task times out or is cancelled, you must still separate **future state** from **actual processing state** before re-issuing the slot.

## 11. Backpressure: who must wait and where?

Concurrency limiting is only practically meaningful when you define **who bears the overload pressure**.

**Common options:**

1. **Block the producer:** acquire a permit before submitting. Simple for synchronous pipelines, but can block the calling thread (unsuitable for event loops).
2. **Reject early:** bounded executor and `AbortPolicy`. The caller must have a “no longer accepting” contract, retry, or report an error.
3. **Batching:** create only K futures, wait for the whole batch. Simple, but can waste slots due to a single slow task.
4. **Rolling replenishment:** maintain K operations; when one completes, submit the next. Utilizes slots better, requires more complex state and error management.
5. **Bounded upstream queue:** hold at most M items waiting for admission; when full, block, drop by policy, or reject. Avoids creating unbounded waiting objects.
6. **Traffic shaping:** in addition to a concurrency limit, apply a rate limit when downstream has per-second/per-minute quotas.

There is no single optimal K for every application. It depends on resource hold time, target latency, RAM, CPU, connection limits, downstream quotas, and retry capability. A K that is too low can cause low throughput; a K that is too high can increase timeouts, tail latency, and error rates under overload.

### Estimating via completion time

For a system in steady state, there is a directional relationship between **the number of in-flight requests**, **throughput**, and **time spent in the system** (Little's Law):

```text
Average number of tasks in the system
  ≈ average throughput × average latency
```

This is an **analytical estimate** under suitable conditions, not an exact formula for choosing semaphore permits for every workload. Queueing, latency variance, and resource limits need to be measured under real load.

## 12. Interruption and deadlines when the producer waits for a permit

`Semaphore.acquire()` is an **interruptible** operation. If the producer is interrupted before obtaining a permit, it has no right to release. If an API needs to bound the **admission** wait time, you can use:

```java
// Snippet: permits is an already-declared Semaphore.
boolean admitted = permits.tryAcquire(
        200, TimeUnit.MILLISECONDS);
if (!admitted) {
    // Return overload response or retry according to business policy.
    return;
}
try {
    // Initiate the operation that has been granted a slot.
} finally {
    // Release only when the operation has actually finished,
    // not when a wrapper times out while I/O is still running.
}
```

This snippet **is not a standalone program**: the enclosing method and operation are not declared; you must define exactly who owns the permit and when it is released.

If a workflow has an overall deadline, do not use `tryAcquire(200ms)` and then `future.get(200ms)` assuming the total is only 200 ms: you have granted two separate budgets. Use `System.nanoTime()` to compute the **remaining time** for each step, and distinguish the caller's deadline from task termination.

**Do not swallow `InterruptedException`** and continue creating thousands of futures; propagate it or restore the `Thread.currentThread().interrupt()` flag when it cannot be propagated. For already-submitted work, a cleanup/cancellation policy is needed; interrupting the producer does not automatically undo previously submitted tasks.

## 13. Common mistakes

1. **“`CompletableFuture.allOf` limits the number of running futures.”** False: it only aggregates completion state.
2. **“An 8-worker fixed thread pool means only 8 tasks/futures exist.”** False: the queue can hold a huge number of tasks.
3. **“A semaphore inside each supplier prevents creating many futures.”** False: all futures and queued tasks can still be created.
4. **“`supplyAsync` always runs on a separate thread.”** False: the executor decides; it may reuse a worker or a caller-runs policy.
5. **“A concurrency limit of 5 is enough to cap at 5 requests/second.”** False: concurrency and rate are different.
6. **“`orTimeout` will interrupt all background tasks.”** False: completing the future's state does not guarantee stopping the real task.
7. **“`CompletableFuture.cancel(true)` always interrupts the worker.”** False: `mayInterruptIfRunning` has no such effect in this implementation.
8. **“A supplier cancelled before running still enters finally.”** False: the supplier may never be called, causing a leak if it is the only place releasing the permit.
9. **“Attaching `whenComplete` to release a permit is always correct.”** Not if the future can be completed/cancelled before the physical operation finishes.
10. **“Release in both the callback and finally to avoid leaks.”** False: this can double release, breaking the limit.
11. **“Once `allOf.join` returns, all business outcomes succeeded.”** False: errors must be handled; timeout wrappers can also finish early.
12. **“An unbounded queue is nothing to worry about because there are few workers.”** False: backlog and memory still grow.
13. **“`DiscardPolicy` with `supplyAsync` is safe because the future will know it was rejected.”** False: the future may never complete.
14. **“`CallerRunsPolicy` never has side effects on the caller.”** False: it can run the entire supplier on the calling thread.
15. **“Batching always optimizes throughput.”** False: one slow task can block advancing the entire batch.
16. **“`Semaphore.availablePermits()` is an atomic reservation.”** False: it is a snapshot; use `acquire/tryAcquire` to obtain a permit.
17. **“Admission timeout proves the external request has stopped.”** False: it only indicates a slot could not be acquired within the timeout.
18. **“Increasing K will always speed things up.”** False: when downstream is saturated, increasing K can worsen latency/errors.
19. **“A completed future means the resource it represents is definitely closed.”** Not when the future only reflects a wrapper signal or a cancelled task.
20. **“No need to shut down a custom executor once enough futures have completed.”** False: the owner must still manage the executor lifecycle.

## 14. Checklist for designing bulk fan-out with CompletableFuture

1. **Identify the resource to protect:** CPU workers, DB connections, unanswered HTTP requests, admitted tasks, or futures holding RAM?
2. **Choose the right limits:** worker count, actual in-flight count, queue capacity, initiation rate, and memory budget can be separate thresholds.
3. **Do not create all futures at once** if input volume is large; choose a window, rolling admission, or streaming.
4. **Acquire permits before submitting** if the goal is to limit the number of admitted tasks. Do not acquire after creating unbounded futures.
5. **Define who owns the permit** across queued/running/finished/cancelled phases; release exactly once.
6. **Check submission failures:** `RejectedExecutionException` must return the permit when the task was not accepted.
7. **Do not release on a timeout wrapper** if the physical operation is still running.
8. **If cancellation is supported**, design a dedicated protocol for not-yet-started tasks and running tasks; do not just attach `whenComplete` indiscriminately.
9. **Handle every outcome:** result, exception, cancellation, timeout, retry; `allOf` does not replace an error policy.
10. **Have clear timeouts and deadlines:** bound both admission and operation when supported by the API; do not reset the budget for each step.
11. **Measure under real load:** in-flight count, queue length, rejections, downstream errors, p95/p99 latency, memory, and throughput.
12. **Manage the executor lifecycle:** shut down pools you own and track unfinished tasks; do not close the common pool.
13. **Avoid blocking event loops:** `Semaphore.acquire()` blocks the caller thread; if the caller is an event loop, an asynchronous admission mechanism is needed.
14. **Clarify retry/idempotency properties:** timeouts do not roll back side effects; retrying can cause duplicate work.
15. **Write controlled tests:** use latches to make workers hold permits/queue, verifying limits without guessing with `sleep`.
16. **Choose the simplest approach that meets the contract:** batching if small and independent; producer gating if waiting is acceptable; bounded executor if rejection is desired; rolling async window when efficient slot utilization without blocking the caller is needed.

## 15. JDK Reference Documentation

- [CompletableFuture — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Semaphore — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [ThreadPoolExecutor — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Executors — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html)
- [CountDownLatch — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Conclusion:** creating `CompletableFuture` instances in bulk easily leads to **uncontrolled fan-out** even when the executor has few workers. `allOf` helps wait for results, **not limit concurrency**. To bound the number of admitted tasks, use batching/windowing, acquire a permit **before submitting**, or use a bounded executor/rejection with the right contract. With asynchronous I/O and cancellation, you must manage slots according to **when the real operation starts/finishes**, not just the `Future` state; otherwise, you risk leaking permits or releasing permits early and exceeding the limit.
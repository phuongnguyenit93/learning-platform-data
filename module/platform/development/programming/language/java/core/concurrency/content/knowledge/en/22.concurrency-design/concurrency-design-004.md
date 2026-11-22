# Fan-out / Fan-in and Result Aggregation in Java Concurrency

**Fan-out / fan-in** is a two-phase concurrency design pattern: **fan-out** splits a piece of work into multiple tasks that can run independently; **fan-in** waits for or coordinates the results and produces a combined output. In Java, this pattern can be built using `ExecutorService`, `Future`, `CompletionService`, and `CompletableFuture`. The goal is to leverage I/O wait time or parallel processing capacity **when tasks can genuinely run concurrently**, while maintaining correctness under failures, timeouts, cancellation, and resource pressure.

For example, a program needs to compute prices from three independent sources. Fan-out submits three tasks to fetch the prices; fan-in combines the results in source order and then calculates the total or makes a decision. The three tasks may finish in a different order than they were submitted, but **the aggregation rule is decided by the program**, and should not depend arbitrarily on thread scheduling.

This article focuses solely on **concurrency in Java**, without tying to any specific framework.

## 1. Fan-out and fan-in are two distinct responsibilities

```text
                       ┌── Task A ── Result A ──┐
Input / Request ───────┼── Task B ── Result B ──┼── Aggregate ── Output
                       └── Task C ── Result C ──┘
               fan-out                         fan-in
```

In the **fan-out** phase, you need to determine:
- Which parts of the work are **independent in data and ordering**? If B needs A's output, then B depends on A and cannot be treated as a completely parallel branch.
- What separate inputs does each task need? Is any shared mutable data used?
- How many tasks are allowed to run simultaneously? Executors, connection pools, CPU, rate-limited APIs, and memory can all be bottlenecks.
- When the caller cancels or times out, do the tasks still need to continue?

In the **fan-in** phase, you need to determine:
- **All-or-nothing:** if one result is missing, the entire aggregation fails.
- **Partial success:** collect all successful results while also returning the error for each failed branch.
- **First result / quorum:** only need the first result or enough valid results; this is a different policy from "wait for all".
- **Ordering:** preserve input order, sort by a business key, or process in completion order?
- **Timeouts:** is there a timeout per branch, per wait operation, or a **shared deadline** for the entire request?

A good design must state the **aggregation contract** clearly before choosing an API. You should not run tasks concurrently and then simply call `join()` on whatever future is available without deciding how failures are handled.

### Expected latency and practical limits

If three independent branches take 100 ms, 180 ms, and 250 ms respectively, running them sequentially takes approximately 530 ms (excluding overhead). If there are enough resources for concurrent execution and fan-in requires all of them, the ideal latency is roughly **250 ms plus scheduling/aggregation overhead**, because it has to wait for the slowest branch. This is only an illustrative model: resource contention, I/O, CPU, executor queues, and network variability can cause actual results to differ significantly.

**Concurrency does not automatically make a program faster.** If the tasks are CPU-bound, the number of CPU cores limits useful parallelism. If the tasks all call a service with a small connection pool, a large fan-out only makes the queue at the pool longer.

## 2. Choosing a Java fan-out / fan-in mechanism

| Mechanism | Suitable when | How results are collected | Notes |
|---|---|---|---|
| `ExecutorService.submit` + `Future.get` | You want control over tasks, the executor, and cancellation | Call `get()` sequentially on the list of futures | Submitted tasks still run concurrently; waiting in list order can delay processing of early-completing results |
| `ExecutorService.invokeAll` | You have a collection of `Callable`s and need to wait for the whole group | Returns a `List<Future>` in **input order** | `invokeAll` waits for the group to complete, which does not mean every result succeeded; individual `get()` calls can still throw |
| `ExecutorCompletionService` | You want to process results in **completion order** | `take()`/`poll()` retrieves completed futures | `take()` may block; `get()` on the retrieved future can still throw an exception |
| `CompletableFuture.allOf` | Waiting for **all** futures | Retrieve individual results after `allOf` completes | The combined future returns `Void`; errors from all branches are not automatically listed in full |
| `CompletableFuture.thenCombine` | Combining **two** independent tasks | Receives both values to aggregate | Multiple pairs can be chained; for N branches, `allOf` is typically used |
| `CompletableFuture.anyOf` | Observing the **first branch to complete** | Returns `Object` or the error of the completed branch | **Not** "first successful result"; the first branch to complete may also fail |
| `handle`, `exceptionally` | Turning branch errors into results/fallbacks | Creates a stage with an explicit recovery policy | Must distinguish between handled errors and errors that still need to be propagated to the caller |

`CompletableFuture.supplyAsync(supplier)` defaults to using `ForkJoinPool.commonPool()` if no `Executor` is passed (except in special runtime situations). In practical examples, pass an explicit executor to separate where tasks run from where results are collected, and to control the level of parallelism.

## 3. Complete example: fan-out three computations, fan-in preserving input order

Save as **`FanOutFanInDemo.java`** (Java 17+):

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FanOutFanInDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            List<Integer> inputs = List.of(3, 5, 7);

            // FAN-OUT: create all three tasks before waiting.
            List<CompletableFuture<Integer>> tasks = inputs.stream()
                    .map(n -> CompletableFuture.supplyAsync(
                            () -> n * n, executor))
                    .toList();

            CompletableFuture<?>[] allTasks =
                    tasks.toArray(new CompletableFuture<?>[0]);

            // FAN-IN: wait for the entire group, then read results in input order.
            CompletableFuture<List<Integer>> results =
                    CompletableFuture.allOf(allTasks)
                            .thenApply(ignored -> tasks.stream()
                                    .map(CompletableFuture::join)
                                    .toList());

            List<Integer> values = results.join();
            int sum = values.stream().mapToInt(Integer::intValue).sum();

            System.out.println("Results: " + values);
            System.out.println("Sum: " + sum);
        } finally {
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac FanOutFanInDemo.java
java FanOutFanInDemo
```

Exact output:

```text
Results: [9, 25, 49]
Sum: 83
```

**Explanation:**
1. `supplyAsync(..., executor)` schedules three independent computations on the executor. Creating all three futures **before** waiting gives them the opportunity to run concurrently.
2. `allOf(allTasks)` returns a `CompletableFuture<Void>`: it completes after all component futures have completed. `allOf` itself **does not collect a `List<Integer>`**.
3. `thenApply` only runs when `allOf` completes **normally**; at that point, `join()` on each item in `tasks` no longer blocks. The result list follows the order of `inputs`, even though task execution/completion order may differ.
4. `executor.shutdown()` only stops accepting new work and allows already-submitted tasks to continue; on the normal path, waiting on `results.join()` already ensures the necessary tasks have finished.

The example uses `newFixedThreadPool(3)` to show three tasks executed by up to three worker threads. In real systems, the number of workers should be based on the workload type and available resources, rather than defaulting to "open N platform threads for N branches".

### Common pitfall: accidentally turning fan-out into sequential execution

Incorrect for parallel intent:

```java
for (int n : inputs) {
    int result = CompletableFuture
            .supplyAsync(() -> expensiveWork(n), executor)
            .join(); // Wait immediately after each submit.
    consume(result);
}
```

This is a **snippet** using existing variables/methods, not a standalone program. Because each iteration waits for completion before submitting the next, the tasks do not make progress together. Instead, create the list of futures first, and then build the fan-in stage or `allOf`.

## 4. Combining two branches directly with thenCombine

When there are exactly two independent sources, `thenCombine` expresses the merge relationship more concisely than `allOf`:

```java
CompletableFuture<Integer> price =
        CompletableFuture.supplyAsync(() -> 100, executor);
CompletableFuture<Integer> tax =
        CompletableFuture.supplyAsync(() -> 10, executor);

CompletableFuture<Integer> total =
        price.thenCombine(tax, Integer::sum);

System.out.println(total.join()); // 110
```

This is a snippet inside a method with a suitable `executor` and `CompletableFuture` imported. The combiner function only runs when **both** branches complete normally. If one branch fails, the combined future completes exceptionally; if you want a fallback, you must decide on an error-handling policy.

**Distinguishing `thenCombine` and `thenCompose`:** `thenCombine` combines **two independent futures**. `thenCompose` chains task B that depends on the future value of A, forming a data-dependent pipeline; this dependent part should not be called an independent fan-out.

## 5. Collecting results in completion order with CompletionService

A task that finishes early can be processed immediately without waiting for futures listed before it. `ExecutorCompletionService` accepts `Callable<T>` tasks and places **completed futures** onto a queue; `take()` retrieves the next completed element. The order may vary on each run.

A complete example where the total sum does not depend on completion order. Save as **`CompletionOrderDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CompletionOrderDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            List<Callable<Integer>> jobs = List.of(
                    () -> 40,
                    () -> 2,
                    () -> 7
            );

            ExecutorCompletionService<Integer> completions =
                    new ExecutorCompletionService<>(executor);

            for (Callable<Integer> job : jobs) {
                completions.submit(job);
            }

            int sum = 0;
            for (int i = 0; i < jobs.size(); i++) {
                // take() waits for a completed Future.
                sum += completions.take().get();
            }

            System.out.println("Sum: " + sum);
        } finally {
            executor.shutdown();
        }
    }
}
```

Run:

```bash
javac CompletionOrderDemo.java
java CompletionOrderDemo
```

Output:

```text
Sum: 49
```

Key characteristics to remember:
- `take()` retrieves futures in **completion order**, not submission order.
- `take()` can throw `InterruptedException` when the waiting thread is interrupted.
- `take().get()` can still throw `ExecutionException` due to a task failure, or `CancellationException` if the future was cancelled. "Completed" itself **does not mean succeeded**.
- If you need to map results back to their source positions, return a data type containing a `requestId`/index or maintain a future-to-input mapping instead of relying on the order from the completion queue.
- `CompletionService` is well-suited for accumulation, streaming partial results, or processing available results early; you must decide what happens to the remaining running tasks if you choose to stop early.

## 6. allOf does not automatically aggregate values or all errors

Key contract of `CompletableFuture.allOf(f1, f2, ...)`:

1. It completes when **all passed-in `CompletableFuture`s complete**; it does not mean returning success as soon as one future returns.
2. If any branch completes exceptionally, the combined future also completes exceptionally (typically observed as `CompletionException` at `join()`).
3. It **does not create a list of results**, and **does not automatically return a list of all failure causes**. The exception provided at `join()` on the combined future is not enough to infer every failed branch.
4. Calling `allOf()` with an **empty array** returns a future already completed normally with `null`; for an empty list, you can explicitly return `List.of()` if that is your program's contract.

Error-handling cases must be designed explicitly, for example:

| Fan-in policy | Implementation approach | Meaning |
|---|---|---|
| All must succeed | `allOf`, then `join()` each branch | If one branch fails, the entire aggregate fails; `allOf` itself does not stop the remaining branches early |
| Some branches may fail | Wrap each branch with `handle` into an `Outcome` type, then `allOf` | Captures both the value and the error of every branch |
| A branch has a fallback value | `exceptionally(...)` on the appropriate branch before `allOf` | Continue aggregating with the fallback; indicate that fallback data was used if the business logic requires it |
| Only one branch needs to complete | `anyOf` | The first branch to complete **may be an error**, and the other branches are not automatically cancelled |
| Need all errors, not just the first | Store an `Outcome` per branch | Do not rely on `allOf`'s exception as a complete report |

**Note:** "all-or-nothing" is a policy on **result values**; it does not automatically provide rollback for I/O or side effects in tasks that have already run. If three branches update three systems and one branch fails, the other successful operations are **not automatically reversed**. You must have separate compensation mechanisms or idempotency rules if side effects are involved.

## 7. Complete example: collecting both successful results and per-branch errors

A reliable way to implement **partial success** is to turn each completion into a result carrying its status. `handle` executes for both normal and exceptional paths, so a future of type `Outcome` can complete normally with the failure information stored as data.

Save as **`PartialFanInDemo.java`** (Java 17+):

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.stream.IntStream;

public class PartialFanInDemo {
    record Outcome(int index, Integer value, String error) {}

    public static void main(String[] args) {
        List<CompletableFuture<Integer>> branches = List.of(
                CompletableFuture.completedFuture(10),
                CompletableFuture.failedFuture(
                        new IllegalStateException("source unavailable")),
                CompletableFuture.completedFuture(30)
        );

        List<CompletableFuture<Outcome>> safeBranches =
                IntStream.range(0, branches.size())
                        .mapToObj(i -> branches.get(i).handle((value, failure) -> {
                            Throwable root = failure;
                            while (root instanceof CompletionException
                                    && root.getCause() != null) {
                                root = root.getCause();
                            }
                            return new Outcome(
                                    i,
                                    value,
                                    root == null
                                            ? null
                                            : root.getClass().getSimpleName());
                        }))
                        .toList();

        CompletableFuture<?>[] all =
                safeBranches.toArray(new CompletableFuture<?>[0]);
        CompletableFuture.allOf(all).join();

        List<Outcome> outcomes =
                safeBranches.stream()
                        .map(CompletableFuture::join)
                        .toList();

        int successSum = 0;
        for (Outcome outcome : outcomes) {
            if (outcome.error() == null) {
                System.out.println("task " + outcome.index()
                        + ": value=" + outcome.value());
                successSum += outcome.value();
            } else {
                System.out.println("task " + outcome.index()
                        + ": error=" + outcome.error());
            }
        }
        System.out.println("Sum of successes: " + successSum);
    }
}
```

Run:

```bash
javac PartialFanInDemo.java
java PartialFanInDemo
```

Exact stdout:

```text
task 0: value=10
task 1: error=IllegalStateException
task 2: value=30
Sum of successes: 40
```

**Notable points:**
- `Outcome` is a Java 17 `record` containing the source index, value, or error type name. In real systems, you can retain the `Throwable` and detailed metadata, while avoiding exposing sensitive information when returning responses to users.
- The three branches in the example are pre-created so the output is deterministically reproducible; this code illustrates the **fan-in policy on failure**. Creating concurrent tasks with an executor was already demonstrated in section 3.
- One failed branch does not discard the two successful branches. Here, `allOf` receives **futures already wrapped with `handle`**, so each branch reports its status through `Outcome`.
- If the `handle` callback itself throws an exception, the corresponding stage can still fail. "Wrapping errors into data" is a strategy that must be tested like any other piece of code.
- Do not assume all errors are safe to ignore. If a required branch (such as critical data validation) fails, the aggregation policy may require failing the request even if other optional branches succeed.

### How do exceptionally, handle, and whenComplete differ?

- `exceptionally(error -> fallback)` runs on the failure path and returns a **replacement value**; no error information remains if only the fallback value is kept.
- `handle((value, error) -> outcome)` receives both cases and is suited for producing a status-bearing result type.
- `whenComplete((value, error) -> log(...))` is primarily for observation; it **does not turn a failure into a success** just because the callback finishes. If the callback throws, the stage result still depends on the upstream branch; do not use `whenComplete` as a recovery mechanism.

A common mistake is logging inside `whenComplete`, then calling `allOf(...).join()`, and being surprised when `CompletionException` is still thrown.

## 8. Limiting concurrent branches: backpressure and resources

Even if an executor has many threads, I/O resources still have limits: connection pools, file descriptors, API quotas, memory, CPU, and DB sessions. Fanning out 50,000 tasks and fanning in all of them can cause massive backlogs, timeouts, and memory growth even when most tasks are just waiting.

There are three scopes to distinguish:

1. **Number of tasks created/submitted:** affects memory, queues, and overall system pressure.
2. **Number of tasks actually running:** bounded by the scheduler/executor and resource capacity.
3. **Number of operations hitting a finite resource:** often requires a per-resource bulkhead / rate limit / `Semaphore` policy, which may be smaller than the number of tasks.

Example limiting at most two tasks entering a resource-using section concurrently:

```java
import java.util.concurrent.Semaphore;

// Snippet inside a class that has a limiter and an operation to throttle.
private final Semaphore limiter = new Semaphore(2);

String callLimited() throws InterruptedException {
    limiter.acquire();
    try {
        return callExternalService();
    } finally {
        limiter.release();
    }
}
```

This is illustrative code, **not a standalone Java file**: `callExternalService()` is an application method. Always `release()` in `finally` after a successful `acquire()`. A `Semaphore` limits the number of tasks **currently holding a permit**, but if you create unbounded futures waiting for permits, work still piles up; therefore, in practice you also need **input/queue bounds**, batching, or overload rejection.

For CPU-bound tasks, use a worker pool sized appropriately for the CPU. For I/O-bound tasks, you can increase concurrency in a controlled way and validate with measurements. Avoid using a small pool for tasks that wait on subtasks submitted **to the same pool**; if all workers are waiting on child tasks, the child tasks may never get scheduled (thread starvation deadlock).

### Do Virtual Threads (Java 21+) replace concurrency limits?

No. You can use `Executors.newVirtualThreadPerTaskExecutor()` to create a virtual thread per I/O-waiting task, but virtual threads **do not create more connections, CPU, or database capacity**. You still need semaphores/bulkheads or concurrency limits at the downstream data source.

Java 21+ snippet (inside a method, not a standalone program):

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> first = executor.submit(() -> fetchFirst());
    Future<String> second = executor.submit(() -> fetchSecond());
    // Handle results and errors according to the problem's fan-in contract.
}
```

`ExecutorService` has supported `AutoCloseable` since Java 19; this `try-with-resources` block requires Java 21+ to use Virtual Threads as a standard feature. On Java 17, use `ExecutorService` with `shutdown()`/`awaitTermination()` in the appropriate lifecycle.

## 9. Timeouts and shared deadlines: do not multiply the wait budget

Setting a separate timeout for each `Future.get(timeout)` call can result in a total wait time exceeding the desired budget if called sequentially. For example, three calls to `get(1, SECONDS)` on three incomplete branches can make the caller wait nearly three seconds instead of one second **for the entire request**.

Commonly used tools:

| API | Timeout effect |
|---|---|
| `Future.get(timeout, unit)` | Only bounds **the caller's wait**; by itself it does not mark the `Future` as failed or cancel the work |
| `CompletableFuture.orTimeout(timeout, unit)` | Arranges for **the future itself** to complete exceptionally with `TimeoutException` if not done by the deadline |
| `CompletableFuture.completeOnTimeout(value, timeout, unit)` | If not done, completes normally with the fallback value when the timeout expires |
| `ExecutorService.invokeAll(tasks, timeout, unit)` | Waits for the entire group up to the time limit; incomplete tasks are cancelled when returning due to timeout |
| `CompletionService.poll(timeout, unit)` | Waits up to a given duration to **retrieve one completed future**; returns `null` if timed out |

For `CompletableFuture`, both `orTimeout` and `completeOnTimeout` operate on **the target future itself** (they do not create a separate copy just for the timeout). If multiple components reference that future, they all observe the new state.

**Shared deadline:** compute an expiration timestamp using a monotonic clock at the start of the request (e.g., `System.nanoTime()`), and then at each waiting step use only the **remaining time**. Avoid using `currentTimeMillis()` to measure wait intervals because the system clock can be adjusted. When the deadline expires, decide whether to fail, return partial success, or return a fallback, and handle/cancel incomplete branches.

Once the deadline is reached, cancel no-longer-needed `Future`s with `cancel(true)` if the task model allows it. However:
- `Future.cancel(true)` on an executor-submitted task may send an interrupt to the running thread, but the task must **cooperate** with interruption to actually stop.
- `CompletableFuture.cancel(true)` only completes the future with cancellation; the `mayInterruptIfRunning` parameter **is not used to interrupt the underlying work** per the class contract.
- Cancelling a combined future via `allOf(...).cancel(...)` **does not automatically guarantee that all child branches are cancelled**. If you want to stop everything, you must retain and actively manage the individual futures or task resources.

Therefore, distinguish between "the caller no longer wants to wait" and "actually stopping the task and its side effects".

## 10. Handling interruption, errors, and lifecycle

At the waiting boundary, `Future.get()` can throw `InterruptedException` (the waiting thread was interrupted), `ExecutionException` (the task failed), and can throw `CancellationException` directly. With `CompletableFuture.join()`, errors are typically wrapped in `CompletionException` (unchecked), while cancellation can throw `CancellationException` directly. Do not handle all cases generically with `catch (Exception)` and return an empty list.

Example pattern inside a method that already has `List<Future<T>> futures`:

```java
try {
    for (Future<String> future : futures) {
        consume(future.get());
    }
} catch (InterruptedException interrupted) {
    for (Future<String> future : futures) {
        future.cancel(true);
    }
    Thread.currentThread().interrupt();
    // Or propagate InterruptedException when the method signature allows.
    throw new IllegalStateException("Fan-in interrupted", interrupted);
} catch (ExecutionException failed) {
    Throwable cause = failed.getCause();
    // Record the cause and decide whether to cancel, retry, or return a partial result.
    report(cause);
}
```

This is a **snippet**; you need to supply the variables/methods, imports, and `CancellationException` handling according to context. Restore the interrupt flag when you catch `InterruptedException` without propagating it, because preserving this signal is useful for callers and lifecycle management.

**Executor lifecycle:** when creating a dedicated executor, you must `shutdown()` or close it properly; in long-running applications, a shared executor with a managed lifecycle is typically used rather than creating a new pool per request. Distinguish `shutdown()` (stops accepting new tasks) from `shutdownNow()` (attempts to interrupt running tasks and returns unstarted tasks); neither method guarantees that all tasks stop immediately.

## 11. Aggregating by input order, completion order, or business key

There are at least three independent ordering rules:

- **Input order:** results corresponding to `[A, B, C]` are needed for rendering or reconciliation; track each task's position and assemble in input order. For example, `allOf` + `tasks.stream().map(join)`.
- **Completion order:** process whichever is ready first to reduce display/accumulation latency; use `ExecutorCompletionService.take()`, though results may arrive as `[C, A, B]`.
- **Business key order:** each branch's result has an `id`/`timestamp`/priority; sort/group by the key before publishing the aggregate. Thread completion order must not be used as a business key.

Non-commutative or non-associative aggregations (ordered string concatenation, selecting the latest record, applying patches, order-sensitive floating-point calculations) must state explicit rules. With floating-point addition, changing the order can produce small differences due to floating-point rounding; do not assume a completion-order reduction yields bit-for-bit identical results.

Instead of having concurrent tasks update a shared `ArrayList` or an unsynchronized `int sum` variable, the simple, safe approach is to **return each task's result individually** and aggregate after they complete. If concurrent state updates are unavoidable, use appropriate synchronized/atomic structures and evaluate contention.

## 12. Strategic error handling: fail, fallback, retry, or partial

A consistent strategy needs to address:

| Scenario | Typically sensible policy | Risk if ignored |
|---|---|---|
| Required branch fails | Fail the request, log the cause, and decide whether to cancel remaining branches | Aggregating invalid or missing required data |
| Optional branch fails | Return an `Outcome` or a marked fallback | Users are unaware that information is missing or substituted |
| Transient error | Bounded retry with delay/backoff/jitter and a deadline | Retry storm, multiplying load |
| Rate limit / overload | Reduce concurrency, use bounded queues, signal overload | Unbounded queues and cascading timeouts |
| Request exceeds deadline | Stop waiting, return error or partial per contract; cleanup/cancel if valid | Consuming resources for results no one needs anymore |
| Partial side-effect success | Idempotency / compensation / appropriate transactions | Cannot "rollback" using `CompletableFuture` alone |

**Retries must account for side effects:** resending a non-idempotent write request can create duplicate transactions. With large fan-outs, simultaneous retries can overload downstream services further. Cap retry counts, use identifiers/idempotency keys where appropriate, and budget timeouts for the entire workflow.

If a problem requires "getting 2 out of 3 results" (*quorum*) or "picking the first successful result", that is a custom fan-in algorithm tracking counts of successes, failures, and in-flight tasks. `CompletableFuture.anyOf` does not automatically solve this policy, because it completes on the **first future to complete**, even if it failed.

## 13. Observability and testing for correctness

Useful metrics for fan-out/fan-in:
- **Total latency** and per-branch latency (p50/p95/p99), especially the slowest branch when waiting for all.
- **Counts of branches created**, running, queued, succeeded, failed, timed out, cancelled, and retried.
- **Actual resources:** executor/queue size, CPU, connection pool, open I/O operations, downstream limits.
- **Correlation IDs** for each request and each branch; log root errors per branch to identify which branch caused the fan-in to fail.

Tests should cover at least these scenarios: all succeed; one branch fails early while others are still running; multiple branches fail concurrently; results arrive out of order; timeout; interrupt; cancellation; executor rejection (`RejectedExecutionException`); empty input list; and duplicate branches with identical inputs. For concurrency, do not rely on `Thread.sleep` and hope the scheduler runs in a fixed order: use `CountDownLatch`, `Phaser`, or deliberate coordination primitives to control synchronization points in tests.

When debugging, check **whether tasks are submitted together**, whether any stage performs blocking work on the same executor running the fan-in, and whether any task holds a lock/resource needed by another branch.

## 14. Fan-out / fan-in design checklist

1. Separate branches that are **truly independent**; do not accidentally wait on each branch right after submitting it.
2. Define the **aggregation policy** upfront: all-or-nothing, partial, first, quorum, or fallback.
3. Choose the API based on how results are collected: `allOf`/`thenCombine`, `CompletionService`, or `Future`/`invokeAll`.
4. Specify **result ordering** (input, completion, or business key), rather than depending arbitrarily on the scheduler.
5. Manage executors, queues, resource limits, and a shared deadline; balance throughput against latency.
6. Distinguish `ExecutionException`, `CompletionException`, cancellation, and interruption; preserve error causes and stop signals.
7. Clearly define retry, fallback, cleanup, and side effects; cancelling a future does not mean rolling back work.
8. Measure and test when branches complete, fail, or are interrupted **in any order**.

**Conclusion:** Fan-out lets you launch multiple independent tasks at once; fan-in turns asynchronous results into a response with a **clear contract**. Understanding resource limits, result data types, aggregation order, and failure policies matters more than simply increasing the number of threads.

### Official Java APIs

- [Java 21: `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 21: `ExecutorCompletionService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
- [Java 21: `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)

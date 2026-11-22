# Calling Multiple Simulated I/O Operations with CompletableFuture and Timeout

## 1. Exercise Objectives

You need to build a **pure Java concurrency** program that executes multiple simulated I/O calls concurrently, limits the waiting time, and aggregates the results. This exercise does not depend on Spring or any web framework.

After this lesson, you should be able to do the following:

1. Distinguish between **sequential execution** time and **parallel execution time for tasks with I/O wait**.
2. Use `CompletableFuture.supplyAsync(..., executor)` to submit independent tasks to an executor you manage.
3. Combine results using `CompletableFuture.allOf(...)` or `thenCombine(...)` without calling `join()` inside each supplier and accidentally serializing execution.
4. Set timeouts for individual tasks and for the entire waiting phase, choosing between a **fallback** and an **explicit error**.
5. Distinguish between a **future completing due to timeout** and **the background I/O having stopped**.
6. Classify errors, ensure executor cleanup, and measure total latency properly.
7. Understand the limits of thread pools, concurrent requests, queues, and how to test asynchronous logic with minimal reliance on `Thread.sleep()`.

**Scenario:** a data aggregation screen needs three independent results: user info, product price, and recommendations. Each data source is simulated by a function that waits and then returns a string. The slow recommendation source should return a fallback value after a timeout, while the two critical sources must succeed. This is a general Java concurrency example; when making real I/O calls, there will also be connection/socket-level timeouts and separate resource limits.

## 2. Understanding the Problem Before Writing Code

Assume normal I/O times are:

| Task | Simulated Time | Role | Policy |
| --- | ---: | --- | --- |
| User | 100 ms | Required | If it fails/times out, the whole task fails |
| Price | 150 ms | Required | If it fails/times out, the whole task fails |
| Recommendation | 1,500 ms | Optional | Returns fallback after 300 ms |
| Total | Not directly additive | Three independent tasks | Wait until the required results are ready |

If executed **sequentially** and waiting for all three real results, the time is approximately `100 + 150 + 1500 = 1750 ms`, excluding scheduling and processing overhead. If all three tasks are launched at the same time on workers capable of executing them, and a fallback is accepted after 300 ms, the time to obtain the results of the three futures is approximately `max(100, 150, 300) = 300 ms`. This is an **ideal estimate**, not a hard guarantee: an overloaded machine, queueing, GC, or delayed timeout scheduling will all change the measured numbers.

It is important to distinguish three moments in time:

- **Task submitted:** calling `supplyAsync` creates a future and requests the executor to run the supplier.
- **Task completed at the CompletableFuture level:** has a value, an error, or is completed specially by a timeout.
- **Background I/O actually stopped:** the supplier thread has returned, has been effectively interrupted, or the I/O call has been canceled in the underlying API.

These three moments **do not necessarily coincide**. For example, `completeOnTimeout("fallback", ...)` can complete the future with a fallback while the supplier continues waiting on the network.

### Flow Diagram

~~~mermaid
flowchart TD
    A[Initialize executor] --> B[Submit User I/O]
    A --> C[Submit Price I/O]
    A --> D[Submit Recommendation I/O]
    B --> E[Future User]
    C --> F[Future Price]
    D --> G{Recommendation within 300 ms?}
    G -->|Yes| H[Real value]
    G -->|No| I[Fallback]
    E --> J[allOf]
    F --> J
    H --> J
    I --> J
    J --> K{Required sources succeeded?}
    K -->|Yes| L[Aggregate results]
    K -->|No| M[Report error and handle]
    L --> N[Shut down executor]
    M --> N
~~~

`allOf` is only a future representing the completion of the input futures; it **does not aggregate results automatically**. After `allOf` completes normally, you retrieve the value from each individual future. If an input future completes exceptionally, `allOf` also completes exceptionally. You must attach a fallback/handler to a degradable task **before passing it into `allOf`** if you want the whole group to still succeed.

## 3. Complete Solution: Three Concurrent I/O Calls, One Fallback with Timeout

The following program uses Java 17+, `CompletableFuture`, and an `ExecutorService` with three workers. `Thread.sleep(...)` appears **only inside the function simulating I/O latency**, and must not be used as a synchronization signal between threads or as a test condition. With real APIs, replace the sleep with an HTTP/file/database call that has its own timeout and cancellation policy.

Create the file **`ParallelIoTimeoutDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ParallelIoTimeoutDemo {
    private static String fakeIo(String source, long millis) {
        try {
            Thread.sleep(millis); // Only simulates slow I/O.
            return source + "-ok";
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(source + " interrupted", e);
        }
    }

    private static CompletableFuture<String> callAsync(
            String source, long millis, ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> fakeIo(source, millis), executor);
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService ioPool = Executors.newFixedThreadPool(3);
        long started = System.nanoTime();

        try {
            // All three calls are submitted before waiting for results.
            CompletableFuture<String> user =
                    callAsync("user", 100, ioPool)
                            .orTimeout(5, TimeUnit.SECONDS);

            CompletableFuture<String> price =
                    callAsync("price", 150, ioPool)
                            .orTimeout(5, TimeUnit.SECONDS);

            CompletableFuture<String> recommendation =
                    callAsync("recommendation", 1_500, ioPool)
                            .completeOnTimeout(
                                    "recommendation-fallback",
                                    300, TimeUnit.MILLISECONDS);

            CompletableFuture<Void> all =
                    CompletableFuture.allOf(user, price, recommendation);

            // Block the main thread only at the result-retrieval boundary.
            all.join();

            System.out.println("User: " + user.join());
            System.out.println("Price: " + price.join());
            System.out.println(
                    "Recommendation: " + recommendation.join());

            double elapsedMs =
                    (System.nanoTime() - started) / 1_000_000.0;
            System.out.printf(java.util.Locale.ROOT,
                    "Elapsed: %.1f ms%n", elapsedMs);
        } catch (CompletionException e) {
            System.err.println("Required I/O failed: " + e.getCause());
            throw e;
        } finally {
            ioPool.shutdownNow();
            if (!ioPool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "I/O worker pool did not terminate");
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ParallelIoTimeoutDemo.java
java ParallelIoTimeoutDemo
~~~

**Example stdout under normal execution conditions:**

~~~text
User: user-ok
Price: price-ok
Recommendation: recommendation-fallback
Elapsed: 309.2 ms
~~~

The three value lines are expected as shown above when the two required tasks finish before the 5-second timeout and recommendation is slower than the 300 ms threshold. **The `Elapsed` line is a machine-dependent measurement, not a fixed output**; on an extremely slow CI runner, completion timing may also differ. If a 5-second timeout occurs on a required source, the program reports an error instead of printing successful results.

### Section-by-Section Analysis

**`supplyAsync`** takes a supplier and an executor. Calling it **does not wait** for `fakeIo` to return; it creates a future that can be completed later. All three `callAsync` calls happen before `all.join()`, so there is no "finish user before starting price" chain.

**`orTimeout(5, SECONDS)`** on user/price: if the future has not completed before the deadline, it is completed **exceptionally** with a `TimeoutException`. This is a result-level fail-fast policy for required sources; there is no automatic fallback. The 5-second mark in this exercise is used to avoid hanging forever, not as an optimal value for a real service.

**`completeOnTimeout("recommendation-fallback", 300, MILLISECONDS)`**: if the future is still incomplete when 300 ms elapses, it is completed normally with the fallback string. If recommendation returns in time, the real value is received. Thus, the optional source does not fail the entire result just because it is slow.

**`allOf(user, price, recommendation)`** waits for all three futures to reach a completed state. It knows nothing about "required" or "optional" semantics; that meaning comes from the handling policy on each individual future. After `all.join()` returns normally, calling `join()` to read the values from the three completed futures **no longer waits on I/O**.

**`System.nanoTime()`** is used to measure elapsed time. Do not use `System.currentTimeMillis()` for measuring short intervals because wall-clock time can be adjusted. If benchmarking, you must run warm-ups, repeat many iterations, and separate queue wait/worker time; this single run is for illustration only.

**`finally`** shuts down the pool so the program does not keep workers alive after `main` exits. `shutdownNow()` attempts to interrupt running workers; `fakeIo` handles `InterruptedException`. With real I/O, an interrupt might not immediately cancel a blocking call, so closing connections/requests and configuring I/O-layer timeouts must still be designed.

### A Very Common Misconception About Timeouts

Both `orTimeout` and `completeOnTimeout` in Java 9+ **mutate the completion state of the CompletableFuture being called**, and return that same future. They do not create a task that "can be automatically interrupted," nor do they guarantee that the `fakeIo` supplier has stopped. When recommendation exceeds 300 ms, the future has already received the fallback, while the supplier may still be sleeping/waiting; in the example, `shutdownNow()` at the end is what attempts to interrupt it.

Some consequences:

- If the real result arrives after the future has already been completed by a fallback, the real result **cannot replace** the previously completed value.
- `CompletableFuture.cancel(true)` completes the future in a cancelled state; CompletableFuture's `mayInterruptIfRunning` parameter **does not control interruption of the background task** the way a regular `FutureTask` can. Do not rely on `cancel(true)` as a socket/thread cancellation mechanism.
- If the pool is very small and the queue is long, a timeout can occur **before the supplier even starts running**; therefore, you need to monitor the backlog and limit accepted work.
- The timer used for timeouts only determines the future's state; the deadline for the entire external operation must be passed into the real I/O client if you want to avoid holding resources for too long.

## 4. `allOf` vs. `thenCombine`: Choosing the Right Aggregation Method

**`allOf`** is suitable when you have N futures, need to know that **all** of them have completed, and then retrieve each value separately:

~~~java
// Code snippet: userFuture and priceFuture are CompletableFuture<String>.
CompletableFuture<Void> done =
        CompletableFuture.allOf(userFuture, priceFuture);
done.join();
String summary = userFuture.join() + " | " + priceFuture.join();
~~~

**`thenCombine`** is suitable for combining values from two futures without blocking the calling thread:

~~~java
// Code snippet: both futures have been submitted to an appropriate executor.
CompletableFuture<String> combined =
        userFuture.thenCombine(priceFuture,
                (user, price) -> user + " | " + price);
String summary = combined.join(); // Block at the final boundary.
~~~

You can chain further: `user.thenCombine(price, ...).thenCombine(recommendation, ...)`. For independent futures, this pattern preserves parallelism because the combine operation runs only when both inputs are ready.

**Avoid the following anti-pattern:**

~~~java
// Wrong for parallel execution: waiting immediately after submitting each request.
String user = callAsync("user", 100, pool).join();
String price = callAsync("price", 150, pool).join();
String rec = callAsync("recommendation", 1_500, pool).join();
~~~

Even though each task uses `supplyAsync`, calling `join()` immediately after each submission causes requests to be **submitted sequentially**: price is only submitted after user finishes, and recommendation is only submitted after price finishes. Create all futures first, then wait for them at the end.

Also avoid calling `join` inside a supplier/callback running on **the same small executor** if the task being waited on is sitting in that executor's queue. Two workers blocking to wait on a third task that has not yet run can cause starvation or deadlock. Use composition via `thenCompose`/`thenCombine`, or adjust the scheduler design so a worker is not held just to wait on another future.

## 5. Two Timeout Policies: Fallback or Fail?

| API | On Expiration | When to Use |
| --- | --- | --- |
| `orTimeout(t, unit)` | Completes the future with `TimeoutException` | Required source that must report an error if too slow |
| `completeOnTimeout(value, t, unit)` | Completes the future with a fallback value | Optional source with a valid substitute result |
| `get(t, unit)` | **The thread calling `get`** throws `TimeoutException` | Limit how long a thread is willing to wait; does not change the future's state |
| `join()` | Waits indefinitely, or returns result/throws `CompletionException` | Should only be used when there is a clear external timeout/lifecycle/deadline |
| `get()` | Waits indefinitely, throws `ExecutionException` on task failure | When checked error classification is needed and a wait-limiting mechanism is already in place |

In particular, when `future.get(200, MILLISECONDS)` expires, it **does not cause the future itself to complete with a failure**, so a subsequent `get` call can still receive the result if the I/O arrives late. Conversely, `future.orTimeout(200, MILLISECONDS)` actually attaches an exceptional completion mechanism to the future upon expiration.

### Standalone Example: Explicitly Verifying a Timeout Exception

No sleep or real I/O is needed: we create a future that deliberately **nobody completes**, then apply a timeout. This isolates and verifies the timeout mechanism instead of guessing worker scheduling.

Save as `TimeoutPolicyDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutPolicyDemo {
    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> timed =
                pending.orTimeout(100, TimeUnit.MILLISECONDS);

        try {
            timed.join();
            throw new AssertionError("Expected timeout");
        } catch (CompletionException e) {
            if (!(e.getCause() instanceof TimeoutException)) {
                throw e;
            }
            System.out.println("Timeout detected");
        }

        CompletableFuture<String> optional = new CompletableFuture<>();
        String fallback = optional
                .completeOnTimeout("cached", 100, TimeUnit.MILLISECONDS)
                .join();
        System.out.println("Fallback: " + fallback);
    }
}
~~~

Compile/run:

~~~bash
javac TimeoutPolicyDemo.java
java TimeoutPolicyDemo
~~~

Stdout:

~~~text
Timeout detected
Fallback: cached
~~~

Neither future in the demo has a supplier, so there is no background I/O work to cancel. `orTimeout` surfaces through `CompletionException` when using `join`; `get` wraps the cause in `ExecutionException`. Distinguishing between **a detected timeout** and **the real source having stopped** is a crucial part of the design.

## 6. Per-Task Timeout and Overall Deadline Are Not the Same

Suppose each source has a 500 ms timeout, but the screen must complete everything within 700 ms. There are two different limits:

1. **Per-task timeout**: an individual source must not be waited on longer than its designated threshold. For example, recommendation can fall back after 300 ms.
2. **Overall deadline**: the total time from receiving the request to returning the result must not exceed a shared budget.

If three tasks are submitted **sequentially** and `get(500 ms)` is called on each, the total time can reach 1,500 ms. If submitted concurrently, the time is usually close to the max of the tasks, though initialization, queueing, callbacks, and final processing must still be accounted for. When an accurate deadline is required by design, compute the **remaining time from a shared deadline** instead of granting the full budget again on every wait.

Illustrative snippet for a synchronous caller with a **remaining deadline**:

~~~java
// Code snippet: all is CompletableFuture<Void>, budgetNanos depends on the SLO.
long deadline = System.nanoTime() + budgetNanos;
long remaining = deadline - System.nanoTime();
if (remaining <= 0L) {
    throw new java.util.concurrent.TimeoutException("Budget exceeded");
}
all.get(remaining, java.util.concurrent.TimeUnit.NANOSECONDS);
~~~

Use `System.nanoTime()` to measure time differences; for extremely long deadlines, overflow must be considered, though budgets in seconds/minutes in tests usually do not encounter this. If there are multiple wait stages, recompute `remaining` before each wait. This `deadline` mark limits **how long the caller waits**; it does not automatically cancel submitted requests. Propagate the deadline down to the real I/O client's timeout mechanism and proactively clean up when expired.

A subtle bug is attaching `allOf(...).orTimeout(totalBudget)` and assuming all I/O is cancelled. Only the aggregate future completes exceptionally; the child futures may still be running. Another mistake is setting a timeout only on `get` on the main thread while leaving the executor without a completion policy or cleanup, causing workers to remain stuck after the test finishes.

## 7. Error Handling When One of Multiple I/O Calls Fails

When tasks have different levels of criticality, the policy must be stated upfront:

- **Required source:** if it errors, the overall request fails; do not display fake results as if they were real data.
- **Optional source:** can be replaced with a fallback, a cached value, or a "no data" state, but the degraded result must be identifiable.
- **One source's error should not hide another source's error info:** log which source failed and why; do not swallow all exceptions and report success.

Common error-handling operations:

| Method | Purpose | Notes |
| --- | --- | --- |
| `exceptionally(ex -> fallback)` | When upstream fails, provides a fallback of the same type | Includes timeout/cancellation errors unless classified |
| `handle((value, ex) -> ...)` | Handles both result and error, transforming to a new type | Invoked in both cases |
| `whenComplete((value, ex) -> ...)` | Observes/logs/records metrics upon completion | Usually preserves the original result or error if the callback itself does not throw |
| `exceptionallyCompose(...)` | Recovers using another future (Java 12+) | Suitable when the fallback is also asynchronous |
| `thenCompose(value -> nextFuture)` | Chains work dependent on previous data | Avoids `thenApply` creating nested futures |

Example of a source **with a fallback on any error**:

~~~java
// Code snippet: sourceFuture is CompletableFuture<String>.
CompletableFuture<String> safe =
        sourceFuture.exceptionally(ex -> "unavailable");
~~~

Note that a blanket fallback can accidentally hide programming bugs (`NullPointerException`), permission errors, or invalid data. In production code, classify exceptions and only fall back on defined error types. If auditability or correctness is critical, it is better to fail explicitly than to substitute results silently.

**Exceptions in CompletableFuture:** `join()` throws `CompletionException` (unchecked) when the pipeline fails; `get()` throws `ExecutionException` (checked). You must inspect `getCause()` / unwrap the wrapper properly, and preserve the interrupt flag properly when using `get`. When one or more futures fail, `allOf` only represents an aggregate failure; it does not by default provide a list of all failing sources. If you want a complete report, normalize each result into a record containing status/duration/error and then aggregate.

## 8. Resource Limits: Parallelism Has a Cost

In the example above, `Executors.newFixedThreadPool(3)` creates a pool of three **platform threads**. Simulating I/O with `Thread.sleep` keeps a worker occupied while waiting. With 3 tasks and 3 workers, the tasks can run in parallel. With 1,000 tasks and 3 workers, most must enter the queue, causing total latency to spike sharply.

**Specifically:** `Executors.newFixedThreadPool` uses an unbounded queue by default; this is a concise API for exercises but **not a safe default choice** for unbounded production load. In larger applications, consider a `ThreadPoolExecutor` with a bounded queue, a rejection/backpressure policy, timeouts on external APIs, and concurrency limits on in-flight requests.

Example of configuring a pool with a bounded queue:

~~~java
// Alternative configuration snippet: must be shut down according to lifecycle.
java.util.concurrent.ThreadPoolExecutor bounded =
        new java.util.concurrent.ThreadPoolExecutor(
                3, 3,
                0L, java.util.concurrent.TimeUnit.MILLISECONDS,
                new java.util.concurrent.ArrayBlockingQueue<>(12),
                new java.util.concurrent.ThreadPoolExecutor.AbortPolicy());
~~~

`AbortPolicy` rejects when full by throwing `RejectedExecutionException`. If this happens in `CompletableFuture.supplyAsync` during task submission, the exception may be thrown immediately at the submit call, before a future is even returned. The caller must handle overload instead of assuming a future will always be produced to complete. A queue that is too long can also cause a future to time out **before it even starts performing I/O**.

Do not default to `CompletableFuture.supplyAsync(supplier)` without passing an executor in this exercise: the default overload typically uses `ForkJoinPool.commonPool()`, which other tasks in the JVM may also share. Long-running blocking I/O tasks on the common pool can slow down unrelated work. Passing an explicit executor helps manage worker count, resource limits, and cleanup.

Java 21 introduces **virtual threads**, which can be helpful for many blocking I/O calls. However, virtual threads do not increase backend capacity and do not replace connection limits, deadlines, or backpressure. This exercise uses Java 17 so it runs easily across many environments; when upgrading the JDK, you can try a virtual thread executor for blocking workloads, while still limiting requests to external sources and measuring performance.

## 9. How to Test Without Relying on Simulated Timing

`Thread.sleep` in `fakeIo` is an **I/O wait-time model** for practice, not a way to guarantee correct synchronization in tests. When testing future orchestration logic, you can use incomplete `CompletableFuture` instances and explicitly call `complete`/`completeExceptionally` to control ordering.

Example of simulating a delayed result **without sleeping**:

~~~java
// Orchestration test snippet.
CompletableFuture<String> user = new CompletableFuture<>();
CompletableFuture<String> price = new CompletableFuture<>();

CompletableFuture<String> combined =
        user.thenCombine(price, (u, p) -> u + "/" + p);

user.complete("alice");
if (combined.isDone()) {
    throw new AssertionError("Must still wait for price");
}

price.complete("120");
if (!"alice/120".equals(combined.join())) {
    throw new AssertionError("Incorrect aggregation");
}
~~~

This result is determined by an **explicit `complete` signal**, independent of scheduler speed. Similarly, `completeExceptionally` lets you test error branches, and a never-completing future lets you test timeouts as in `TimeoutPolicyDemo`.

For integration tests using real I/O, you can add controlled delays in a fake server, tune transport timeouts, and use `CountDownLatch` to confirm work has started before releasing it. Use finite timeouts on `get/await` calls and close executors/network clients in `finally`. Avoid assertions like "sleep 200 ms and hope the request finished"—that is a source of flaky tests.

### Observations Worth Measuring

- Time from **before submitting the task group** until aggregation completes.
- Per-source timing: request submitted, started, completed; queue wait if significant.
- Counts of succeeded, failed, timed-out, and fallback tasks; do not mix fallbacks with real results in statistics.
- Number of busy workers, queued tasks, and tasks still running **after a future times out**.
- p95/p99 latency and completion rate across many iterations; a single `Elapsed` measurement is not a sufficient benchmark.

## 10. Extension Exercises with Acceptance Criteria

**Exercise A — Aggregate results into a record.** Replace separate strings with `record Dashboard(String user, String price, String recommendation, boolean degraded)`. When recommendation times out, set `degraded = true`; when the real value is received, set it to `false`. Do not infer degraded status from the fallback string's name in production code; use a result type that explicitly describes the state.

**Exercise B — Test a failing source.** Modify `fakeIo` so the price source throws an exception and verify that the program does not print a successful result table. Attach a handler only for recommendation and try adding a recommendation error as well to observe the fallback; never swallow errors from a required source.

**Exercise C — Separate per-task and overall timeouts.** Give recommendation a 300 ms timeout; give the two required sources appropriate per-task timeouts; add an overall 1-second deadline. Test the case where one future takes too long or the queue backs up. Ensure that when the overall deadline expires, the program reports an error and cleans up all managed resources.

**Exercise D — Try a small pool.** Reduce the executor to 1 worker and observe that all three tasks, even though submitted concurrently, will be **serialized at the executor**; recommendation may time out while still sitting in the queue. Compare the timings and execution states, and explain why concurrent submission alone is not enough when worker capacity is small.

**Exercise E — Load limiting.** Replace the fixed pool with a bounded `ThreadPoolExecutor` and submit multiple batches of I/O groups; test queue limits and handle `RejectedExecutionException` in a controlled manner. Do not retry infinitely; clearly report accepted/rejected request counts and queue time.

**Exercise F — Write deterministic tests.** Do not sleep to guess that a future has finished. Use test-owned `CompletableFuture` instances to explicitly complete user/price/recommendation and verify `allOf`, `thenCombine`, fallback, and error handling. For real-time tests, use sufficiently wide thresholds and warn if CI is overloaded.

### Completion Criteria

- Submit all three requests before waiting for results; do not `join` immediately after each `supplyAsync`.
- Separate required sources from optional sources; apply fallbacks only where appropriate.
- Have finite timeouts, error handling, and executor lifecycle management.
- Correctly describe the meaning of a timeout: **the future can complete while the supplier/I/O is still running**.
- Results do not depend on callback log-printing order; display order is determined at the aggregation step.
- Have actual timing measurements and be able to explain why they differ from the sum of sequential I/O times.
- When scaling to many requests, enforce resource limits and concurrency bounds.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `supplyAsync(...).join()` immediately after each call | Accidentally executes sequentially | Create all futures first, then aggregate/wait at the end |
| Not passing an executor for blocking I/O | Can starve the common pool | Use a dedicated, bounded I/O executor |
| Believing `orTimeout` interrupts the I/O thread | Resource leaks while background requests keep running | Configure timeouts/cancellation on the underlying I/O client, clean up explicitly |
| `allOf` fails because of an optional source | Loses the whole result table despite having a fallback | Attach the fallback to the right source before combining |
| `exceptionally` returns a fallback for all errors | Hides bugs or invalid data | Classify errors; preserve required-source errors |
| `get(500ms)` per future and treating it as a 500ms total deadline | Total wait exceeds budget | Compute `remaining` from a shared deadline |
| Using a single-worker pool for three blocking I/O calls | Tasks get queued | Choose worker count/concurrency model for the workload, measure queueing |
| Unbounded executor queue | Growing backlog, memory usage, timeouts | Bounded queue, rejection/backpressure |
| Looking at a single `Elapsed` run | Confusing a demo output with a benchmark | Warm up, measure many iterations, track latency/throughput/fallback rate |
| `Thread.sleep` in tests to "wait for completion" | Flaky tests or false passes | `Future.get`, latch, barrier, explicit completion |
| Ignoring `shutdown`/interrupt | Threads stay alive, program hangs on exit | `try/finally`, shutdown, await termination |
| Treating fallbacks as real source results | Wrong metrics and business decisions | Distinguish degraded/cache/timeout states |

## 12. Self-Check Questions

**1. Why doesn't `allOf` directly return a `List<String>`?** It returns `CompletableFuture<Void>` representing the point in time when all futures have completed; the values reside on each individual future. To get a combined result object, combine the values after all relevant futures are ready or use a `thenCombine` chain.

**2. Can `completeOnTimeout` return a fallback when the supplier has never even started?** Yes. The timeout starts counting from when it is attached to the future, while the supplier may still be waiting in the executor queue.

**3. How does `get(timeout)` differ from `orTimeout`?** `get(timeout)` limits how long **the calling thread waits** and does not complete the future itself; `orTimeout` causes the future to complete exceptionally when the deadline arrives, whether any thread is waiting or not.

**4. Why is `cancel(true)` on a `CompletableFuture` not considered a guarantee to interrupt the supplier?** Because the future's cancellation state and controlling the execution of the background task are two separate mechanisms; `CompletableFuture` does not directly own a `FutureTask` to guarantee interruption like some executor APIs do.

**5. When three independent I/O calls run concurrently, is the total time always equal to the max of each I/O's time?** No. That is only an approximation under conditions where tasks are actually scheduled concurrently, the pool has sufficient capacity, there is no large queue, and overhead is low. Timeouts/fallbacks can also make the time to get an *acceptable result* shorter than the real I/O time.

**6. If a required source fails, should a partially populated table be returned?** Only if the business logic defines that degraded mode as valid. In this exercise, user/price are required, so we must report an error and clean up instead of treating an incomplete result as success.

**7. Should all `Thread.sleep` calls be replaced with `CompletableFuture`?** No. `sleep` can be used to simulate latency in exercises; the problem is using sleep as a **synchronization verification condition** or designing unbounded concurrency. With real I/O, use the appropriate client and timeouts.

**Key takeaway:** `CompletableFuture` lets you launch, coordinate, transform, and handle asynchronous results. To call multiple I/O operations effectively, you must **submit all tasks first**, **distinguish timeouts from background task cancellation**, **bound resources**, and **define failure/fallback policies upfront** for each source.
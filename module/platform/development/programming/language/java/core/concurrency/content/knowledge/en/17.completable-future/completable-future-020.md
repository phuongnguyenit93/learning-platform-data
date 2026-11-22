# exceptionallyCompose(): Recovering with an Asynchronous CompletionStage

## 1. When Error Recovery Is Also an Asynchronous Task

In a Java `CompletableFuture<T>` pipeline, a step can either **complete normally** with a value of type `T` or **complete exceptionally** due to an exception, cancellation, an explicitly configured timeout, etc. If a primary task fails, many systems need to perform **another asynchronous step** to recover:

- The primary data source is down; try a backup service.
- A call to a dependency fails transiently; initiate a bounded retry.
- Reading a record fails; perform an asynchronous query to another store.
- A distributed computation fails; switch to a fallback execution path and wait for the actual result of that path.

`exceptionallyCompose` solves this exact problem: **when the current stage fails, invoke a function that receives the error, returns a new `CompletionStage<T>`, and composes (flattens) the result of that recovery stage into the pipeline**.

```text
                  ┌─ success: T ───────────────────────┐
primaryStage ─────┤                                     ├─> result: T
                  └─ failure: Throwable ───────────────┤
                                            │           │
                                            ▼           │
                                  exceptionallyCompose  │
                                            │           │
                                            ▼           │
                                fallbackStage: T ───────┘
                                   /         \
                               success       failure
                               → result T    → error result
```

**Core point:** `exceptionallyCompose` does not turn every error into a valid result. It only provides an opportunity to recover using another stage; if the fallback stage also fails, the final result still fails. This lesson falls under **pure JDK Java Concurrency**, with no framework dependencies.

## 2. API and Java Version Requirements

`exceptionallyCompose` was added to `CompletionStage` in **Java 12** and is available in Java 17. Three important overloads when called on `CompletableFuture<T>`:

```java
CompletableFuture<T> exceptionallyCompose(
        Function<Throwable, ? extends CompletionStage<T>> fn);

CompletableFuture<T> exceptionallyComposeAsync(
        Function<Throwable, ? extends CompletionStage<T>> fn);

CompletableFuture<T> exceptionallyComposeAsync(
        Function<Throwable, ? extends CompletionStage<T>> fn,
        Executor executor);
```

These are **illustrative API signatures**, not a standalone compilable program. On a variable statically typed as `CompletionStage<T>`, the corresponding methods return `CompletionStage<T>`; on a variable typed as `CompletableFuture<T>`, the implemented methods return `CompletableFuture<T>`.

The components:

- `T`: **the same result type** before and after recovery. For example, if the source has type `CompletableFuture<Order>`, the recovery function must return a stage for `Order`, not `CompletionStage<String>` without type conversion.
- `Throwable`: the exception representing the cause of the source's exceptional completion. It may be the original exception or a `CompletionException` wrapping the cause; do not assume it is always the exact exception class thrown by the application.
- `Function<Throwable, ? extends CompletionStage<T>>`: a function that builds/initiates the **recovery stage**, rather than returning a `T` value directly.
- `Async`: refers to **how the callback that creates the recovery stage is executed**, not necessarily the executor that runs all the business logic inside the returned stage.

`exceptionallyCompose` is called when **building the graph**; the function `fn` is only triggered when the source completes **exceptionally**. If the source has already succeeded, the new stage continues carrying that result and the recovery callback does not run.

### Return Type: Avoiding Nested CompletableFuture

The concept is equivalent to a "flatMap on the error branch":

```java
CompletableFuture<String> recovered =
        primary.exceptionallyCompose(error ->
                CompletableFuture.supplyAsync(() -> "from backup", executor));
```

`primary` is a `CompletableFuture<String>` and `executor` is declared by the application; this is an illustrative fragment. The result has type **`CompletableFuture<String>`**, not `CompletableFuture<CompletableFuture<String>>`. The new stage waits for the stage returned by the callback to complete, and then takes **that stage's value or error** as its own completion.

Therefore, if the callback returns a `CompletionStage<T>` that is still pending, the recovery stage is also **not yet complete** until that stage finishes. There is no guarantee that the callback must create a task on a new thread; the callback can return `completedFuture` or `failedFuture` immediately.

## 3. Comparing exceptionally(), exceptionallyCompose(), and thenCompose()

| API | When does it run? | What does the callback return? | Result |
| --- | --- | --- | --- |
| `exceptionally(error -> fallbackValue)` | Source fails | A **value T** | The new stage completes with the fallback value |
| `exceptionallyCompose(error -> fallbackStage)` | Source fails | A **CompletionStage<T>** | The new stage completes according to the result/error of the fallback stage |
| `thenCompose(value -> nextStage)` | Source succeeds | A **CompletionStage<U>** | The new stage completes according to the next stage |
| `handle((value, error) -> result)` | Source succeeds **or** fails | A **value U** | The new stage carries the value returned by the callback, or the error thrown by the callback |
| `whenComplete((value, error) -> ...)` | Source succeeds or fails | Returns no value; callback observes | Usually preserves the original outcome; not meant for converting an error into a value |
| `exceptionallyAsync(error -> value, executor)` | Source fails | A **value T**, async callback | Does not compose a stage; available since Java 12 |

If the error can be recovered **immediately** from available data, `exceptionally` is simpler:

```java
CompletableFuture<String> value =
        primary.exceptionally(error -> "cached");
```

If you need to **invoke another asynchronous task** and can only return a result after that task finishes, use `exceptionallyCompose`:

```java
CompletableFuture<String> value =
        primary.exceptionallyCompose(error ->
                CompletableFuture.supplyAsync(
                        () -> loadBackup(), backupExecutor));
```

Both fragments assume `primary` has type `CompletableFuture<String>`; `loadBackup` and `backupExecutor` are components declared by the application.

**Do not** use `thenCompose` to recover a failed source: `thenCompose` only runs its callback when the source **succeeds**, so a fallback callback in a `thenCompose` branch will be skipped when the source fails.

## 4. Standalone Java 17 Example: Primary Source Fails, Using Backup Source

The following program intentionally creates a failed primary source, then recovers using `CompletableFuture.supplyAsync` on a separate executor. The program also demonstrates that the recovery callback does not run when the primary source succeeds, and that the original future's error is **not modified** by the recovery branch.

Save the file **`ExceptionallyComposeDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExceptionallyComposeDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService backupPool = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<String> primary =
                    CompletableFuture.failedFuture(
                            new IllegalStateException("primary offline"));

            CompletableFuture<String> recovered =
                    primary.exceptionallyCompose(error ->
                            CompletableFuture.supplyAsync(
                                    () -> "backup:OK", backupPool));

            System.out.println("Recovered: " + recovered.join());
            System.out.println("Original failed: "
                    + primary.isCompletedExceptionally());

            AtomicBoolean fallbackCalled = new AtomicBoolean(false);
            CompletableFuture<String> healthy =
                    CompletableFuture.completedFuture("primary:OK");

            CompletableFuture<String> unchanged =
                    healthy.exceptionallyCompose(error -> {
                        fallbackCalled.set(true);
                        return CompletableFuture.completedFuture("backup:OK");
                    });

            System.out.println("Healthy: " + unchanged.join());
            System.out.println("Fallback called: " + fallbackCalled.get());
        } finally {
            backupPool.shutdown();
            if (!backupPool.awaitTermination(5, TimeUnit.SECONDS)) {
                backupPool.shutdownNow();
            }
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ExceptionallyComposeDemo.java
java ExceptionallyComposeDemo
```

Deterministic stdout on a successful run:

```text
Recovered: backup:OK
Original failed: true
Healthy: primary:OK
Fallback called: false
```

Explanation:

1. `failedFuture` creates `primary` in an exceptional state from the start.
2. `exceptionallyCompose` creates a **new future** `recovered` and invokes the recovery function with the error from `primary`.
3. The callback creates `CompletableFuture.supplyAsync(...)`, scheduling the backup work on `backupPool`.
4. `recovered.join()` only returns once the fallback stage has completed with `"backup:OK"`.
5. `primary.isCompletedExceptionally()` remains `true`: the recovery pipeline **does not erase the error of the original future**.
6. The `healthy` future already succeeded, so the `exceptionallyCompose` callback is not called; `fallbackCalled` remains `false`.

There are no print statements inside the callback or worker, so the stdout order does not depend on executor scheduling. `backupPool.shutdown()` is called in `finally`, avoiding leaked threads. A value produced by `supplyAsync` may arrive quickly or slowly, but `join()` waits until it is ready.

## 5. Outcome Table: What Happens in Each Branch?

| Source Outcome | Recovery Callback | Returned Future Outcome |
| --- | --- | --- |
| Source succeeds with `T` | **Not called** | Succeeds with the exact value `T` |
| Source succeeds with `null` | **Not called** | Succeeds with `null` |
| Source fails; callback returns a stage succeeding with `T` | Called | Succeeds with `T` from the fallback stage |
| Source fails; callback returns a stage that also fails | Called | Fails with the outcome of the fallback stage |
| Source fails; callback throws an exception | Called | The composed stage fails due to the callback |
| Source fails; callback returns `null` instead of a stage | Called | Fails to obtain a valid stage; dependent completes exceptionally |
| Source is `cancel(...)`ed | This is an exceptional completion | May invoke callback and create fallback; requires a clear policy |
| Source is not yet complete | Not yet called | Dependent stage keeps waiting |

**"Asynchronous recovery" does not mean "always succeeds".** The fallback can fail, hang, or miss its deadline. Code must decide how to handle the secondary error and enforce timeouts/cancellation on real dependencies.

You can observe the outcome using `join()` or `get()` at the boundary where the value is needed:

- `join()` typically throws `CompletionException` if the stage is exceptional; if the future itself was cancelled, it may throw `CancellationException` directly.
- `get()` declares `ExecutionException` and `InterruptedException`; it may throw `CancellationException`.
- `get(timeout, unit)` adds `TimeoutException` when waiting past the timeout, **without changing the future's state or cancelling the task**.

If a future depends on a cancelled source, the exception may arrive as a `CompletionException` wrapping a `CancellationException`. Therefore, when classifying errors, inspect the cause rather than only comparing the surface exception class.

## 6. exceptionallyComposeAsync: How Is the Callback Executed?

The three overloads provide the same semantics of **recovering with another stage**, but differ in where the exception-handling callback runs.

### 6.1. exceptionallyCompose(fn)

The callback is not submitted to a separate executor by default. Under `CompletableFuture`'s policy for non-Async dependents, the callback may run on the thread that completes the source stage or a thread participating in completion; if the source is already completed, the callback may run immediately on the thread attaching the stage. **Do not rely on thread names.**

Suitable when the callback is very lightweight: inspecting the error type, selecting a fallback branch, and **returning a stage** without blocking.

### 6.2. exceptionallyComposeAsync(fn)

The callback is executed using the stage's default asynchronous execution facility. For standard `CompletableFuture`, this typically uses `ForkJoinPool.commonPool()`; some environments/implementations may use a fallback strategy. Do not assume the common pool is appropriate for long blocking I/O.

### 6.3. exceptionallyComposeAsync(fn, executor)

The callback is scheduled on the provided `Executor`. This option gives you control over where the fallback decision runs, queue/capacity policies, and executor lifecycle:

```java
CompletableFuture<String> recovered =
        primary.exceptionallyComposeAsync(
                error -> loadFromBackupAsync(),
                callbackExecutor);
```

This snippet is a fragment; `loadFromBackupAsync()` must return a `CompletionStage<String>`, and `callbackExecutor` is configured by the application. **Key note:** the executor in this overload is used to run the **callback function**, not necessarily the internal executor used by `loadFromBackupAsync`. If the callback creates `supplyAsync(..., otherExecutor)`, the backup task runs on `otherExecutor`.

### Do Not Use Async Assuming Extra Parallelism

Calling `exceptionallyComposeAsync` only matters after an error occurs. It does not make the primary source asynchronous, does not automatically create retries, and does not improve throughput if the recovery merely returns `completedFuture("fallback")`. For lightweight callbacks, the extra scheduling can even add overhead.

If the callback must perform blocking I/O, it is better for it to **initiate** the asynchronous work and return a stage immediately, rather than occupying a callback worker waiting on `get()`/`join()`.

## 7. Crucial Distinction: Return a Stage, Do Not Wait for a Stage

Incorrect pattern:

```java
// Fragment to avoid: waiting for fallback directly inside the callback.
CompletableFuture<String> result =
        primary.exceptionally(error ->
                loadFromBackupAsync().toCompletableFuture().join());
```

`exceptionally` requires the callback to **return a `String`**, so this code blocks with `join()` until the fallback finishes. If the callback runs on a thread-constrained pool and the fallback needs that same pool, blocking can increase latency, cause thread starvation, or trigger a deadlock.

Correct expression:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> loadFromBackupAsync());
```

The callback **returns a stage**, and the pipeline continues according to that stage's completion. No thread is held just to wait inside the callback. Both snippets assume `primary` is a `CompletableFuture<String>` and `loadFromBackupAsync()` returns a `CompletionStage<String>`.

### Why Not Use exceptionally(error -> supplyAsync(...))?

With `primary` of type `CompletableFuture<String>`, `exceptionally` expects a `String`. A callback returning `CompletableFuture<String>` will not type-check. You could widen the type to something like `Object`, but that produces a nested value or loses type safety — defeating the purpose. `exceptionallyCompose` was created to *flatten* the asynchronous recovery branch.

## 8. Java 17 Example: Fallback Errors Must Also Propagate Properly

No API guarantees that a backup source will always succeed. Below is a standalone program demonstrating three outcomes: source succeeds, source fails but fallback succeeds, and source fails with fallback also failing.

Save the file `RecoveryOutcomeDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class RecoveryOutcomeDemo {
    public static void main(String[] args) {
        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("main");
        CompletableFuture<String> fail =
                CompletableFuture.failedFuture(
                        new IllegalStateException("main failed"));

        CompletableFuture<String> kept =
                ok.exceptionallyCompose(error ->
                        CompletableFuture.completedFuture("never-used"));

        CompletableFuture<String> recovered =
                fail.exceptionallyCompose(error ->
                        CompletableFuture.completedFuture("backup"));

        CompletableFuture<String> failedAgain =
                fail.exceptionallyCompose(error ->
                        CompletableFuture.failedFuture(
                                new IllegalArgumentException("backup failed")));

        System.out.println("Normal: " + kept.join());
        System.out.println("Recovered: " + recovered.join());

        try {
            failedAgain.join();
        } catch (CompletionException error) {
            System.out.println("Fallback error: "
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac RecoveryOutcomeDemo.java
java RecoveryOutcomeDemo
```

Stdout:

```text
Normal: main
Recovered: backup
Fallback error: IllegalArgumentException
```

In the last case, `failedAgain` fails to recover because the stage returned by the callback failed. The resulting stage reflects the fallback's error, rather than retaining any value from `main`. If you need to preserve **both errors** for observability, record the first cause before starting the fallback and record the second cause when the fallback fails; do not assume the pipeline automatically carries a full collection of causes.

Example of observing both source and fallback:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> {
            logPrimaryFailure(error);
            return backupAsync().whenComplete((value, backupError) -> {
                if (backupError != null) {
                    logBackupFailure(backupError);
                }
            });
        });
```

This is a fragment; `logPrimaryFailure`, `logBackupFailure`, and `backupAsync` are defined by the application. `whenComplete` is used for observing the outcome and avoids throwing new exceptions from logging; it is not meant to replace the result value. When both the source and backup fail, operators need to classify and record the causes clearly.

## 9. Error Classification: When Should You Attempt a Fallback?

Not every error can or should be recovered. Some examples:

| Error Type | Should fallback/retry? | Reason |
| --- | --- | --- |
| Transient timeout in a dependency | Possibly, if deadline remains and backup system is independent | Can overcome transient failures |
| Primary source unavailable | Can switch to another backup source | Requires a consistency policy and sufficiently fresh data |
| Authentication/authorization error | Usually no | Retrying another path may mask security errors |
| Invalid input data | Usually no | The error will not go away by switching sources |
| Resource exhausted / rate limit | Consider delaying or stopping | Immediate retry can worsen the incident |
| Cancellation requested by caller | Usually **do not** restart | The user no longer wants the work to continue |
| Programming error (`NullPointerException`, bug) | Should not blindly mask with fallback | Needs bug fixes and monitoring |

The `Throwable` in the callback may be a `CompletionException` wrapping an application exception. If you need to inspect the root cause, unwrap it **in a controlled way**:

```java
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    while (current instanceof java.util.concurrent.CompletionException
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

This is a **syntactically standalone method fragment** that must be placed inside a class to compile. Do not automatically unwrap every `RuntimeException`: an application-created exception may carry its own intended meaning. Rely on the dependency's error contract and avoid filtering by exception message strings.

Example of falling back only on a transient error:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> {
            Throwable root = unwrapCompletion(error);
            if (root instanceof java.io.IOException) {
                return loadBackupAsync();
            }
            return CompletableFuture.failedFuture(error);
        });
```

This is a fragment; `primary`, `loadBackupAsync`, and `unwrapCompletion` are provided by the application. `CompletableFuture.failedFuture(error)` preserves the error path instead of fabricating a fake success. In real programs, `CancellationException` or errors with special rules should be handled before the general fallback policy.

## 10. Bounded Recovery: Retry Creates a New Stage Each Time

`exceptionallyCompose` is well-suited for writing **bounded** retries: after the current attempt fails, create a new attempt using a `Supplier<CompletableFuture<T>>`. The key thing to remember is that **attaching a handler again to the same failed future does not re-run the work**. A retry must *actually re-invoke* the logic that initiates an attempt.

Standalone Java 17 example. The first two attempts intentionally fail; the third attempt succeeds. The program caps retries at two after the initial attempt, so the result is deterministic.

Save the file `ExceptionallyComposeRetryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class ExceptionallyComposeRetryDemo {
    static <T> CompletableFuture<T> retry(
            Supplier<CompletableFuture<T>> operation,
            int retriesLeft) {

        if (retriesLeft < 0) {
            throw new IllegalArgumentException("Negative retriesLeft");
        }

        CompletableFuture<T> current;
        try {
            current = operation.get();
        } catch (Throwable failure) {
            current = CompletableFuture.failedFuture(failure);
        }

        return current.exceptionallyCompose(error -> {
            if (retriesLeft == 0) {
                return CompletableFuture.failedFuture(error);
            }
            return retry(operation, retriesLeft - 1);
        });
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger attempts = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Supplier<CompletableFuture<String>> operation = () ->
                    CompletableFuture.supplyAsync(() -> {
                        int n = attempts.incrementAndGet();
                        if (n < 3) {
                            throw new IllegalStateException("temporary");
                        }
                        return "OK";
                    }, pool);

            CompletableFuture<String> finalResult =
                    retry(operation, 2);

            System.out.println("Result: " + finalResult.join());
            System.out.println("Attempts: " + attempts.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
javac ExceptionallyComposeRetryDemo.java
java ExceptionallyComposeRetryDemo
```

Stdout:

```text
Result: OK
Attempts: 3
```

Each call to `operation.get()` produces **a new `CompletableFuture`** and schedules a new `supplyAsync` call. When an attempt fails, the `exceptionallyCompose` branch calls `retry` with the remaining retry count decremented by 1. The final result is `OK` on the third attempt.

### Limitations of the Retry Example

This is a conceptual example, **not a production retry mechanism**:

- Retries in the demo happen immediately after failure, without **backoff + jitter** to prevent many clients from retrying at once.
- There is no overall deadline or concurrency limit.
- It does not distinguish between transient and permanent errors.
- It does not check for caller cancellation; a cancelled request should not be inadvertently retried.
- If many attempts fail quickly, repeated composition can create many completion nodes; a low bound avoids building overly long chains.
- An operation with side effects such as sending a payment or writing to a database may **not be safe to retry**, unless there is an idempotency key or duplicate-handling protocol.
- If an attempt was already accepted by an external system but timed out on the response, retrying can cause the work to execute multiple times. Do not infer that a timeout means the work was not processed.

In production systems, you should have a retry budget, deadlines, exponential backoff/jitter, error classification, metrics, and clear stop conditions.

## 11. Timeouts: Recovery Does Not Automatically Set Deadlines on Sources

`exceptionallyCompose` has no timeout parameter. If the source remains **pending forever**, the recovery callback **never runs**, because no exceptional completion has occurred.

You can set a deadline on the source using `orTimeout`:

```java
CompletableFuture<String> primary = loadPrimaryAsync();

CompletableFuture<String> result =
        primary.orTimeout(1, TimeUnit.SECONDS)
               .exceptionallyCompose(error -> loadBackupAsync());
```

This is a fragment; `loadPrimaryAsync` and `loadBackupAsync` are declared by the application. `orTimeout` (Java 9+) completes **the future it is called on** with a `TimeoutException` when the deadline expires, and returns **the same future instance** without creating a copy. When `primary` times out and completes exceptionally, the handler can start the backup.

**Four mandatory caveats:**

1. Timing out `primary` **does not automatically cancel** the underlying I/O work, and a late result may still arrive even though the future has already completed exceptionally.
2. A one-second deadline on `primary` **does not automatically limit the backup's duration**. If the backup never completes, `result` can still remain pending indefinitely.
3. If multiple components hold the same `primary` reference, `orTimeout` mutates the state observed by all of them; deciding ownership is critical.
4. `result.get(1, TimeUnit.SECONDS)` only times out **the waiting thread** and throws `TimeoutException`; it does **not** make `result` exceptional and therefore does not trigger `exceptionallyCompose`.

If you need a deadline for the entire process including the backup, you can place a timeout on the **final** stage or design a request-level shared deadline:

```java
CompletableFuture<String> result =
        loadPrimaryAsync()
            .orTimeout(400, TimeUnit.MILLISECONDS)
            .exceptionallyCompose(error -> loadBackupAsync());

result.orTimeout(1200, TimeUnit.MILLISECONDS);
```

This fragment illustrates two deadlines **measured from the moment each `orTimeout` is called**, not 400 ms + 1200 ms sequentially per stage. The scheduler determines the exact timing of timeout completion, so the numbers are only target budgets. When you need accurate remaining request time, compute a shared deadline and pass it to the client/task; timing out a `CompletableFuture` alone does not release sockets or workers.

**Do not fall back on every `TimeoutException` by default**. Check the overall budget and attempt count; if the primary timeout has already consumed most of the budget, starting a slow backup may make the request even slower.

## 12. Cancellation: Being Cancelled Is Also an Exceptional Completion

When `CompletableFuture.cancel(...)` succeeds, the future becomes completed exceptionally with `CancellationException`. This means the `exceptionallyCompose` handler **can run even when the source is cancelled**. If the handler recovers from every `Throwable` without checking, the program may **start a backup even after the caller asked to stop**.

Example fragment:

```java
CompletableFuture<String> pending = new CompletableFuture<>();
CompletableFuture<String> recovered =
        pending.exceptionallyCompose(error ->
                CompletableFuture.completedFuture("fallback"));

pending.cancel(true);
System.out.println(recovered.join()); // fallback
```

This is a valid fragment when `CompletableFuture` is imported. It illustrates a "recover even on cancellation" policy; this is **not necessarily appropriate** for requests cancelled by a user.

To preserve cancellation across a recovery branch, inspect the cause and return a corresponding exceptional stage:

```java
CompletableFuture<String> recovered =
        primary.exceptionallyCompose(error -> {
            Throwable root = unwrapCompletion(error);
            if (root instanceof java.util.concurrent.CancellationException) {
                return CompletableFuture.failedFuture(error);
            }
            return loadBackupAsync();
        });
```

`primary`, `unwrapCompletion`, and `loadBackupAsync` are provided by the application. In this example, on cancellation, the handler does not start the backup; returning `failedFuture(error)` keeps the resulting stage completed **exceptionally**. `recovered.isCancelled()` will not necessarily be `true`; the dependent may complete with an exception wrapping `CancellationException`, so inspect the outcome/causes rather than relying on a specific flag on the dependent stage.

### Cancelling the Recovery Result Does Not Guarantee Cancelling the Fallback

`CompletableFuture.cancel(true)` **does not use interrupts** to control running threads in the `CompletableFuture` implementation; `mayInterruptIfRunning` has no effect as documented in the API. Cancelling the output stage does not automatically guarantee that a task running inside `supplyAsync` or an I/O client actually stops.

If you need to cancel background work, keep a separate cancellation handle (such as a `Future<?>` from `executor.submit` or a client-supported cancellation API), propagate deadlines, handle interruption, and clean up. Distinguish between **the future was cancelled**, **the thread was interrupted**, and **side effects actually stopped**.

## 13. Where Should Recovery Be Placed in the Stage Chain?

Where you attach the handler determines **which errors** it can catch.

### Recovering the Source Before a Transformation

```java
CompletableFuture<Integer> result =
        fetchNumberAsync()
            .exceptionallyCompose(error -> loadNumberBackupAsync())
            .thenApply(value -> 100 / value);
```

Here, recovery handles errors from `fetchNumberAsync`. If `thenApply` subsequently divides by zero, that new error occurs **after the handler**, so it is not handled by the earlier handler.

### Recovering the Entire Pipeline After a Transformation

```java
CompletableFuture<Integer> result =
        fetchNumberAsync()
            .thenApply(value -> 100 / value)
            .exceptionallyCompose(error -> loadResultBackupAsync());
```

Now the final handler can handle errors from both the source and the `thenApply` transformation. Consider carefully: if dividing by zero indicates a bug or invalid data, should you switch to a backup? Recovering "all errors" at the end of a pipeline can mask programming errors.

Both snippets are illustrative fragments; `fetchNumberAsync`, `loadNumberBackupAsync`, and `loadResultBackupAsync` are undeclared. In real code, place the handler close to the dependency boundary where fallback is permitted, and only recover from classified errors.

### Recovery Does Not Alter All Branches of a Future

```java
CompletableFuture<String> primary = loadPrimaryAsync();

CompletableFuture<String> recovered =
        primary.exceptionallyCompose(error -> loadBackupAsync());

CompletableFuture<String> observed =
        primary.whenComplete((value, error) -> audit(value, error));
```

This is a fragment. If `primary` fails, `recovered` may succeed via fallback, but `observed` still sees the original error. Each dependent of `primary` has its own outcome in the graph; attaching one handler does not "fix `primary`".

## 14. Threading, Blocking, and Worker Exhaustion

Although `exceptionallyCompose` supports asynchrony through the returned stage, an application can still create a bottleneck if the callback:

- Calls `get()`/`join()` to wait for the fallback on the thread completing the source.
- Runs long blocking I/O inside `exceptionallyComposeAsync` on `ForkJoinPool.commonPool()`.
- Shares a very small executor pool among the primary source, callback, and fallback while the callback waits for a task that has no free worker to run.
- Retries without a bound, causing queues to grow when a dependency is failing.
- Performs expensive synchronous logging from thousands of callbacks.
- Holds an important lock while waiting for a fallback.

The standard approach is to keep the callback **very short**, only classifying the error and initiating/obtaining a `CompletionStage<T>` from a non-blocking API. Time-consuming I/O or computation should run on an appropriate executor with timeouts and backpressure.

Good example:

```java
CompletableFuture<String> result =
        primary.exceptionallyCompose(error -> {
            if (!shouldFallback(error)) {
                return CompletableFuture.failedFuture(error);
            }
            return fetchBackupAsync(); // Return stage, do not block here.
        });
```

This is a fragment; `shouldFallback` and `fetchBackupAsync` are defined by the application. If `fetchBackupAsync` actually blocks before returning a stage, naming the method `Async` **does not make the work asynchronous**.

When creating your own `ExecutorService`, you must manage shutdown, queue/capacity limits, and rejection. If the executor rejects work (`RejectedExecutionException`), the callback or recovery stage can fail; this is also an error to diagnose, not a fallback success.

## 15. Memory Visibility and Data in the Recovery Stage

`CompletableFuture` has completion/result-retrieval mechanics that satisfy Java Concurrency synchronization; a thread observing the successful completion of a dependent stage can safely use values properly published by the preceding step. However, **that does not automatically make shared mutable objects thread-safe**.

Unsafe example: multiple retries mutating a plain `HashMap` or a shared `int` counter without locks/atomics, assuming `join()` at the end will fix earlier races. That is incorrect; the race already occurred while the workers were running.

Prefer having each attempt produce an independent/immutable result, such as a Java 17 record:

```java
record UserInfo(long id, String name) {}

CompletableFuture<UserInfo> result =
        fetchPrimaryUserAsync()
                .exceptionallyCompose(error -> fetchBackupUserAsync());
```

This is a fragment; both async functions return the same `CompletionStage<UserInfo>` type. When each stage returns an immutable result, subsequent steps are easier to reason about and you avoid multiple workers mutating shared state.

When you need an attempt counter or metrics, use `AtomicInteger` or a thread-safe telemetry system. Do not rely on "the order callbacks usually run" as a synchronization mechanism.

## 16. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using `exceptionally` to return `CompletableFuture<T>` | Wrong callback return type (expected `T`) | Use `exceptionallyCompose` |
| Using `thenCompose` to handle a failed source | Callback does not run when source fails | Attach `exceptionallyCompose` on the error branch |
| Calling `fallbackFuture.join()` inside `exceptionally` | Blocks the thread; can starve workers | Return the stage directly from `exceptionallyCompose` |
| Assuming `exceptionallyCompose` always runs the callback | Successful sources pass straight through | Callback only runs on exceptional completion |
| Assuming this API automatically retries the source | It only invokes a function that creates a stage | The supplier must actually create a new attempt |
| Retrying infinitely or without backoff | Overloads dependencies and queues | Bound attempts, set deadlines, use backoff/jitter |
| Recovering from permanent business errors | Masks bugs, returns wrong data | Classify causes; only fall back on allowed errors |
| Unintentionally recovering from cancellation | Cancelled requests still launch backups | Check for `CancellationException` and preserve cancellation policy |
| Assuming `exceptionallyComposeAsync` runs the backup on the passed executor | The executor only applies to the callback; backup chooses its own | Explicitly specify the backup stage's executor |
| Timing out only the primary without bounding the backup | Requests may wait on the backup indefinitely | Use an overall deadline and I/O timeouts |
| Calling `orTimeout` thinking it creates a copy | It mutates state on the future it is called on | Manage future ownership and deadlines |
| Calling `get(timeout)` and expecting the recovery handler to run | `get` timeout only affects the caller | Design a stage deadline if you want exceptional completion |
| Cancelling the output and assuming the source task stopped | `CompletableFuture.cancel` does not interrupt tasks | Keep a separate cancellation handle and use cooperative stopping |
| Losing the primary error when the fallback also fails | Diagnostics miss the initial root cause | Log/trace both outcomes |
| Attaching the handler too far downstream after transformations | May mask programming bugs unrelated to the dependency | Place recovery at the boundary of recoverable errors |
| Using non-idempotent side effects in retries | Can create duplicate operations | Use idempotency keys and reconcile state |

## 17. Pre-Implementation Checklist

1. **Define which errors are eligible for recovery**: transient timeouts, dependency unavailable, or specific error types?
2. **Place the handler at the right stage** so you do not accidentally catch unrelated errors.
3. **Keep the same type `T`** between source and fallback; if a type change is needed, convert intentionally in both branches.
4. **Keep the callback non-blocking**; return the `CompletionStage<T>` created by the backup service.
5. **Choose an Async overload** when you need to control where the callback runs, without assuming that executor controls all tasks inside the fallback.
6. **Bound retries** if the callback creates new attempts; include a retry budget, backoff/jitter, deadlines, and error classification.
7. **Respect cancellation** if the user cancelled or the request no longer needs a result.
8. **Set both overall and I/O timeouts**, avoiding timing out only the primary while forgetting the backup.
9. **Preserve error observability** for both primary and backup when incident investigation is needed.
10. **Use immutable results and thread-safe telemetry**, avoiding shared mutable state.
11. **Check side effects/idempotency** before automatically retrying external requests.
12. **Test all branches**: source succeeds, source fails/fallback succeeds, fallback fails, callback throws, callback returns `null`, cancellation, timeout, and executor rejection.

## 18. Self-Check Questions

**1. Why is `exceptionallyCompose` different from `exceptionally`?**  
`exceptionally` returns a value `T` directly from the callback; `exceptionallyCompose` returns a `CompletionStage<T>` and waits for that stage's outcome.

**2. If the primary succeeds, does the `exceptionallyCompose` callback run?**  
No. The returned stage continues completing normally with the primary's value.

**3. If the primary fails and the fallback also fails, what is the final result?**  
Exceptional completion; there is no successful value. Separate observation is needed if you want to retain full details of both errors.

**4. Can `thenCompose` be used to handle a primary failure?**  
No. `thenCompose` runs its callback when the upstream succeeds, not on the exceptional branch.

**5. Does `exceptionallyComposeAsync(fn, executor)` guarantee that the backup task runs on that executor?**  
No. That executor runs the callback; the backup stage may use a different executor.

**6. Does attaching a recovery handler to a future turn the original future into a success?**  
No. It creates a new dependent stage; the original future keeps its own outcome.

**7. Does calling `primary.orTimeout(...)` followed by `exceptionallyCompose` automatically stop running I/O?**  
No. Timing out a `CompletableFuture` does not automatically close sockets or interrupt the source task.

**8. Does `get(timeout)` on an incomplete future automatically trigger recovery?**  
No. The `get` timeout only limits how long the caller thread waits; it does not complete the future exceptionally.

**9. If the primary is cancelled, can the recovery callback run?**  
Yes, because cancellation is an exceptional completion. The application must decide whether to fall back or preserve the cancellation.

**10. What must a proper retry do besides re-attaching `exceptionallyCompose`?**  
It must actually create a new attempt, bound the number of retries, classify errors, and respect deadlines, cancellation, and idempotency.

**11. Which Java version introduced `exceptionallyCompose`?**  
Java 12; it can be used in Java 17 and later without additional libraries.

## References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)

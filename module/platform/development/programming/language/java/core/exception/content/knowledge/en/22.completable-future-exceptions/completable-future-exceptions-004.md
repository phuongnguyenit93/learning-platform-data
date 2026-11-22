# Tracing the Root Cause Through Async Wrappers in `CompletableFuture`

An asynchronous task can fail while reading data, transforming data, or calling an external service, yet the thread waiting for the result receives a `CompletionException` or an `ExecutionException`. Looking only at the outermost exception class name can easily mislead a developer into concluding that `CompletableFuture` itself caused the error. The right way to diagnose it is to **distinguish the async failure wrapper from the original business or execution exception thrown by the task**, and then trace the `getCause()` chain deliberately.

This article focuses on **tracing the root cause of a failure** when using `CompletableFuture` in Java: where the error starts, how it propagates across stages, how it surfaces when calling `join()` or `get()`, and how to log, handle, and test it while preserving sufficient context.

## 1. Mental model: where an error originates differs from where it is observed

Suppose the main thread calls `CompletableFuture.supplyAsync(...)` to load data. The code inside the supplier throws `IllegalStateException("storage unavailable")`. At this point, there are three conceptual layers:

1. **Error origin** (*origin*): the actual unit of work that failed, such as a supplier, a `thenApply` lambda, or a transformation step inside `thenCompose`.
2. **Stage state** (*exceptional completion*): `CompletableFuture` records that the work completed with an error. Dependent stages can continue propagating the failure state without executing functions that only handle successful values.
3. **Observation boundary** (*observation boundary*): the call site of `join()`, `get()`, or a result-handling callback that receives the error information, possibly through a wrapper exception.

The causal flow can be visualized as follows:

```text
Supplier/Stage throws IllegalStateException
                |
                v
CompletableFuture completes exceptionally
                |
        +-------+--------+
        |                |
        v                v
      join()            get()
        |                |
        v                v
 CompletionException   ExecutionException
        \                /
         \-- getCause() /
                 |
                 v
   Original IllegalStateException
```

The diagram illustrates the **common case**. The actual cause chain may have multiple layers because the application intentionally wraps additional exceptions, or it may be a special completion exception such as cancellation (`CancellationException`). You should not assume that *every* failure has exactly one wrapper layer.

Key point: the stack trace at the `join()`/`get()` call site shows where the error was **detected**; the stack trace of the deeper cause is usually closer to where the error was **originally thrown**. Read both when investigating.

## 2. Common exception types and their meanings

| Exception Type | Typical Role | Where Does It Usually Appear? |
| --- | --- | --- |
| `CompletionException` | Runtime exception used to represent exceptional completion of a `CompletionStage` | `join()`, `getNow()`, or propagated across stages |
| `ExecutionException` | Checked exception used by `Future.get()` to report that the awaited task failed | `get()` and `get(timeout, unit)` |
| Original business/technical exception | Actual error: `IllegalArgumentException`, `IOException`, `IllegalStateException`, SDK errors… | `getCause()` of the wrapper, or deeper in the cause chain |
| `CancellationException` | Indicates that the task was cancelled | Can be thrown directly by `join()`/`get()` when that future itself was cancelled |
| `InterruptedException` | The thread **waiting** in `get()` was interrupted | `get()`, distinct from the async task throwing an error |
| `TimeoutException` | `get(timeout, unit)` timed out; or a stage completed exceptionally via `orTimeout(...)` | The former is thrown directly while waiting; the latter may appear as the cause of a wrapper exception |

For `CompletableFuture`, `join()` is a convenience API that throws unchecked exceptions; `get()` follows the `Future` contract and throws the checked `ExecutionException` when the result fails. For a task throwing a normal exception, you typically see:

```text
join() --> CompletionException --> IllegalStateException
get()  --> ExecutionException  --> IllegalStateException
```

If the completion state already carries a `CompletionException`, `get()` typically constructs an `ExecutionException` whose `cause` is **the cause held inside the `CompletionException`**, rather than necessarily inserting `CompletionException` as an intermediate layer. Conversely, an application may intentionally throw an already multi-layered wrapped exception; in that case, the actual cause chain is deeper. Inspect the cause tree rather than guessing the number of layers based on the API.

**Do not equate `isDone()` with success:** `isDone()` returns `true` whether the future completed normally, failed, or was cancelled. `isCompletedExceptionally()` helps detect an abnormal state, but it does not tell you the exact error type or origin; you need to inspect the `Throwable` to investigate.

## 3. Java 17+ example: the root error surfaces differently via `join()` and `get()`

Create the file **`AsyncFailureTrace.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class AsyncFailureTrace {
    static Throwable unwrapAsync(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<Integer> source =
                CompletableFuture.supplyAsync(() -> {
                    throw new IllegalStateException("storage unavailable");
                });

        CompletableFuture<Integer> mapped =
                source.thenApply(value -> value * 2);

        try {
            mapped.join();
        } catch (CompletionException error) {
            Throwable root = unwrapAsync(error);
            System.out.println("join wrapper=" + error.getClass().getSimpleName());
            System.out.println("join root=" + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }

        try {
            mapped.get();
        } catch (ExecutionException error) {
            Throwable root = unwrapAsync(error);
            System.out.println("get wrapper=" + error.getClass().getSimpleName());
            System.out.println("get root=" + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }

        CompletableFuture<Integer> recovered = mapped.exceptionally(error -> {
            Throwable root = unwrapAsync(error);
            System.out.println("callback root=" + root.getClass().getSimpleName());
            return -1;
        });

        System.out.println("fallback=" + recovered.join());
        System.out.println("source exceptional=" + source.isCompletedExceptionally());
        System.out.println("recovered exceptional="
                + recovered.isCompletedExceptionally());
    }
}
```

Run with Java 17+:

```bash
javac AsyncFailureTrace.java
java AsyncFailureTrace
```

Output:

```text
join wrapper=CompletionException
join root=IllegalStateException: storage unavailable
get wrapper=ExecutionException
get root=IllegalStateException: storage unavailable
callback root=IllegalStateException
fallback=-1
source exceptional=true
recovered exceptional=false
```

**Why is the output deterministic?** The first `join()` waits for `mapped` to complete before reading the error; the subsequent `get()` reads that same completed result. The `exceptionally(...)` callback is attached to an already-failed stage and must finish before `recovered.join()` returns. No print order depends on worker thread speed.

Explanation:

- The error originates inside the supplier with type `IllegalStateException` and message `storage unavailable`.
- Because `mapped` has no successful value, the multiplication in `thenApply` does not run. The failure propagates to `mapped`.
- `mapped.join()` reports `CompletionException`, whereas `mapped.get()` reports `ExecutionException`. The `unwrapAsync` helper extracts `IllegalStateException` in both cases.
- `exceptionally(...)` receives a `Throwable` representing the prior stage's failure and **turns the error into a fallback value** `-1`. Thus `source` remains failed, while `recovered` completes normally.

The `unwrapAsync` helper is designed to strip **two specific technical wrapper types**, preserving a domain or technical exception once reached. This is appropriate for typical error paths. You should not automatically walk to the deepest cause of *every* `Throwable`, because a business exception may intentionally wrap a lower-level cause while still being the abstraction level the caller needs to handle.

## 4. Reading the `getCause()` chain properly

Every `Throwable` can hold a cause exception via `getCause()`. For a complete diagnosis, you should identify:

- **Exception at the observation boundary:** the outermost class provided by `join()`, `get()`, or a callback.
- **Exception after stripping async wrappers:** the result of unwrapping `CompletionException` and `ExecutionException`, if present.
- **Deeper cause exceptions:** for example, a `ServiceException` created with `new ServiceException("cannot fetch", sqlException)`; keeping `ServiceException` helps the business layer understand the context, while `sqlException` helps diagnose the data layer.
- **Stage context information:** operation name, request key, log-safe parameters, pipeline step; Java does not automatically include a lambda's business name in error messages.
- **Suppressed exceptions** via `Throwable.getSuppressed()` if code used `addSuppressed` or additional errors occurred when closing resources in `try-with-resources`. These errors do not appear in the primary `getCause()` chain.

Conceptual example:

```text
CompletionException
  cause -> OrderLookupException("lookup failed")
             cause -> IOException("connection reset")
```

If you only print `error.getMessage()`, origin details may be missing or contain only the wrapper class name. Conversely, if you only take the deepest cause, you lose the context that the failure occurred during an order lookup operation. You should **log the full stack trace of the `Throwable`** at an appropriate logging boundary, and then select which exception to handle according to application policy.

Here is a callback handling pattern, **placed in a scope where `CompletableFuture<Order> future` and the application logger already exist**:

```java
CompletableFuture<Order> observed = future.whenComplete((order, error) -> {
    if (error != null) {
        Throwable meaningful = unwrapAsync(error);
        logger.error("Order lookup failed", meaningful);
    }
});
```

The snippet above is illustrative, not a standalone class: `Order`, `future`, `logger`, and `unwrapAsync` must be declared by the application. Note that `whenComplete(...)` returns **a new stage** (`observed`), so use that downstream stage if observation is part of the pipeline.

When logging in production, pass the `Throwable` to the logger so you get the stack trace and cause chain rather than logging only `cause.toString()`. Also avoid placing secrets or personal data into contextual messages.

## 5. How are exceptions propagated and handled at each stage?

A stage chain operates according to completion state:

- `thenApply`, `thenAccept`, `thenRun`, and similar dependent operations run their value-handling branch only when the previous stage completes normally. If the previous stage fails, the dependent stage typically completes exceptionally without running the value handler.
- `thenCompose` can return a child stage. An error in the child stage becomes the failure of the composed stage; when tracing, remember it may come from the returned stage, not just the outer function.
- `exceptionally(error -> fallback)` runs when the previous stage fails; if the lambda returns a normal value, the new stage **recovers**. If the lambda itself throws, the new stage can fail with the error from the recovery step.
- `handle((value, error) -> ...)` runs for both completion types and can transform either a value or an error into a new result. On error, `value` is typically `null`; on normal completion, `error` is `null`. A valid successful value can also be `null`, so do not rely solely on `value == null` to conclude failure.
- `whenComplete((value, error) -> ...)` is suitable for observation and logging; normally it preserves the existing result or error for the returned stage. If the callback itself throws when the input succeeded, the returned stage fails. If the input already failed and the callback also throws, the original error still takes precedence according to the API contract.

The second example demonstrates the difference between **observing an error**, **turning an error into a value**, and **a new error created by the callback itself**.

Create the file **`StageObservation.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class StageObservation {
    static Throwable meaningful(Throwable error) {
        Throwable current = error;
        while (current instanceof CompletionException
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> failed = CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid item"));

        CompletableFuture<Integer> observed = failed.whenComplete((value, error) -> {
            if (error != null) {
                System.out.println("observed=" + meaningful(error).getMessage());
            }
        });

        try {
            observed.join();
        } catch (CompletionException error) {
            System.out.println("observed failure="
                    + meaningful(error).getClass().getSimpleName());
        }

        CompletableFuture<Integer> handled =
                observed.handle((value, error) -> error == null ? value : 10);
        System.out.println("handle result=" + handled.join());
        System.out.println("original exceptional=" + failed.isCompletedExceptionally());

        CompletableFuture<Integer> good = CompletableFuture.completedFuture(5);
        CompletableFuture<Integer> badObserver = good.whenComplete((value, error) -> {
            throw new IllegalStateException("audit failed");
        });
        try {
            badObserver.join();
        } catch (CompletionException error) {
            System.out.println("observer failure="
                    + meaningful(error).getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac StageObservation.java
java StageObservation
```

Output:

```text
observed=invalid item
observed failure=IllegalArgumentException
handle result=10
original exceptional=true
observer failure=IllegalStateException
```

The first `whenComplete` branch only observes and preserves the error; therefore `observed.join()` still fails. The `handle` branch turns that error into the result `10`, while `failed` retains its error state. In the final case, the original stage `good` completes normally, but the observation callback itself throws `IllegalStateException`, causing **the returned stage** `badObserver` to fail. When investigating, check exactly which stage is being awaited.

## 6. Tracing the cause in a multi-step pipeline

In a long pipeline, retrieving only the root exception is sometimes not enough to know **which step** broke, especially when multiple steps can throw `IllegalArgumentException` or `IOException`.

Illustrative example (does not compile standalone; `load`, `parse`, `save`, and dependent types must be defined in the application):

```java
CompletableFuture<Result> pipeline =
        CompletableFuture.supplyAsync(() -> load(key))
                .thenApply(raw -> parse(raw))
                .thenApply(parsed -> save(parsed));
```

You can add context **at a step boundary** using an appropriate exception, while preserving the cause:

```java
.thenApply(raw -> {
    try {
        return parse(raw);
    } catch (IllegalArgumentException error) {
        throw new ParseStageException("Invalid document format", error);
    }
})
```

The snippet above is also illustrative and requires a `ParseStageException` class and `parse` method. The new exception indicates the **step's role**; `error` is passed to the constructor as the cause so lower-level trace details are not lost. If there is no requirement to change the abstraction layer, simply adding an observation callback and letting the error propagate can be simpler.

A clean boundary-marking pattern is to use `whenComplete` at key points:

```java
CompletableFuture<Data> loaded = CompletableFuture
        .supplyAsync(() -> loadData())
        .whenComplete((value, error) -> {
            if (error != null) {
                reportFailure("loadData", error);
            }
        });
```

This illustrative snippet depends on `Data`, `loadData()`, and `reportFailure(...)`. `reportFailure` should avoid throwing; if it throws, the new stage returned by `whenComplete` can carry the new error when the upstream source succeeded. In systems with tracing, attach a request correlation ID (*correlation ID*) to the stage context to link worker logs with caller-thread logs.

**Do not re-wrap errors at every stage** just to get a longer stack trace. Too many wrapper layers are hard to read and often obscure the exception type that upper layers need to handle.

## 7. When multiple tasks fail together: `allOf` and `anyOf`

`CompletableFuture.allOf(a, b, c)` creates a future that completes when **all** input futures finish. If any input future fails, the aggregate future also completes exceptionally, but the exception received from `allOf(...).join()` **is not a complete list of all errors**. When multiple tasks fail, the API does not guarantee that this single cause represents every root cause.

To investigate individual tasks, **keep references to the component futures** and inspect each one after `allOf` completes. Inspection snippet placed in a method where `CompletableFuture<?>[] tasks` is already available:

```java
CompletableFuture<Void> all = CompletableFuture.allOf(tasks);
try {
    all.join();
} catch (CompletionException | java.util.concurrent.CancellationException ignored) {
    // Do not infer the failures of all tasks solely from the aggregate exception.
}

for (int index = 0; index < tasks.length; index++) {
    try {
        tasks[index].join();
    } catch (CompletionException error) {
        System.err.println("task " + index + ": " + unwrapAsync(error));
    } catch (java.util.concurrent.CancellationException cancelled) {
        System.err.println("task " + index + ": cancelled");
    }
}
```

This illustrative snippet uses `unwrapAsync` from the earlier example. `tasks` must be a valid array of futures. `allOf` ensures all input futures have completed before the loop, so `join()` on each element does not block on still-running work. When logging, preserve the `Throwable` and its stack trace; the code above prints only a summary to illustrate the flow.

`CompletableFuture.anyOf(...)` behaves differently: the aggregate future completes when **one** component completes (normally or exceptionally). Therefore, the state of `anyOf` describes only the first result and **does not assert** whether the other futures have finished or succeeded. Do not use an `anyOf` error to draw conclusions about all remaining tasks.

If the application needs an aggregated report of *all* errors, design a structure that collects each result/exception with clear task labels; do not assume `getSuppressed()` on the aggregate exception will automatically contain all errors from `allOf`.

## 8. Distinguishing task errors from waiting, cancellation, or scheduling errors

These are cases that are very easy to confuse if you only look at the outermost exception:

### 8.1. Timeout of `get(timeout, unit)`

If you call `future.get(100, TimeUnit.MILLISECONDS)` before the work finishes, the waiter may receive `TimeoutException` **directly**. That only means this wait timed out: the future may still be running and complete normally afterward. Do not log “task failed due to TimeoutException” solely from this case.

By contrast, `future.orTimeout(100, TimeUnit.MILLISECONDS)` configures **the future itself to complete exceptionally with `TimeoutException`** if the deadline expires. When observing the failed future via `join()` or `get()`, the error may appear under the corresponding wrapper. The two cases must be distinguished during diagnosis.

### 8.2. Interrupted waiting thread

`future.get()` can throw `InterruptedException` when the **waiting thread** is interrupted. This is not automatically an exception thrown by the supplier. If it cannot be propagated, code catching `InterruptedException` should usually call `Thread.currentThread().interrupt()` to preserve the interrupt flag and exit the flow appropriately. `join()` does not declare `InterruptedException`, but that does not mean it turns an interruption request into a business error of the task.

### 8.3. Cancellation with `cancel(...)`

`CompletableFuture.cancel(boolean)` completes the future in the cancelled state if it has not yet completed. In `CompletableFuture`'s own implementation, the `mayInterruptIfRunning` argument **is not used to interrupt execution**; cancelling the future does not guarantee stopping the physical work running in the supplier. When calling `join()`/`get()` on a **future that was directly cancelled**, `CancellationException` can be thrown directly. A dependent stage may carry a `CompletionException` wrapping `CancellationException`. Therefore, if you need to report “cancelled” separately, check both `isCancelled()` where appropriate and the cause chain.

### 8.4. Executor rejects the task

When calling `CompletableFuture.supplyAsync(supplier, executor)`, the executor may refuse to schedule the task, for example because it has been shut down; `RejectedExecutionException` can occur **immediately upon calling the submission method**, before a `CompletableFuture` is returned. This is a **task submission** error, distinct from an error thrown inside the supplier and stored as an exceptional completion.

The caller should distinguish these two boundaries:

```java
CompletableFuture<String> future;
try {
    future = CompletableFuture.supplyAsync(() -> fetch(), executor);
} catch (java.util.concurrent.RejectedExecutionException error) {
    // No valid future was returned from the rejected call.
    throw error;
}

// Track the result and errors of the future only after it has been created.
```

This illustrative snippet requires `fetch` and `executor` to be provided by the application. Do not use `try/catch` around every `supplyAsync` call as the sole way to “catch errors inside the supplier”: errors in the supplier are normally observed via the future upon completion.

## 9. Pattern for context-rich error handling without losing causes

A consistent strategy at application boundaries includes:

1. **Name each step** in the pipeline so you know where processing failed.
2. **Preserve the cause** when translating a technical exception into a business-meaningful exception.
3. **Unwrap only well-recognized wrappers** (`CompletionException`, `ExecutionException`) when selecting an error type to handle. When logging details, preserve the full exception/stack trace.
4. **Distinguish recovery from observation:** `exceptionally` and `handle` can turn the state into success; `whenComplete` is normally used to observe while preserving the error.
5. **Do not abandon the final stage.** If nothing awaits or observes the stage and no other monitoring is in place, errors can remain inside the future without reaching a handler.
6. **Define primary logging points** to avoid logging the same error redundantly across multiple callbacks. Log at the step level when adding context; outer layers can decide on error responses, alerts, or retries.
7. **Keep cancellation and timeout paths separate** from business errors. If retrying, avoid automatically retrying programming bugs or side-effecting operations without safety conditions.

You can define a shared “unwrap async wrapper” helper with a clear comment stating that the returned value is the *nearest meaningful exception*, not necessarily the deepest cause in the entire chain. For error data coming from untrusted or uncontrolled sources, consider abnormal cause chains (reference cycles, excessive depth) to avoid infinite loops; avoid writing a generic unwrapping utility without stating its contract.

## 10. Common mistakes and self-check questions

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| “`CompletionException` is the original business error.” | Sees only the wrapper, misses the real error | Inspect `getCause()` and the inner exception type |
| “`get()` and `join()` always produce the exact same cause chain.” | Catches the wrong class and misdiagnoses layers | `get()` uses `ExecutionException`; `join()` typically uses `CompletionException` |
| “A trailing `thenApply` stage didn't run, so that stage threw the error.” | Misattributes error location | An error may have propagated from an earlier stage, skipping the final lambda |
| “`whenComplete` logged the error, so the new future must succeed.” | Error keeps propagating and goes unhandled | `whenComplete` normally preserves the error; only `handle`/`exceptionally` can recover |
| “`allOf` returns every error.” | Misses concurrently failing tasks | Inspect each component future if you need all causes |
| “`isDone()` returning `true` means the task succeeded.” | Mistakes exceptional completion for success | Check the result or `isCompletedExceptionally()` and handle the throwable |
| “`get(timeout)` throwing `TimeoutException` means the supplier threw a timeout error.” | Confuses waiter timeout with task failure | Distinguish wait-call timeout from `orTimeout(...)` exceptional completion |
| “`cancel(true)` definitely interrupts the `CompletableFuture` supplier.” | False assumption that the work actually stopped | Cancelling the future does not force-stop the running task |
| “Walking to the deepest `getCause()` always gives the exception to catch.” | Loses business context of a meaningful wrapper | Unwrap only technical wrappers; keep the full chain when logging |

Self-check:

**Q1.** A supplier throws `IllegalArgumentException` and the pipeline does not recover. What does `join()` usually catch, and where is the root error? **`CompletionException`**, then inspect `getCause()` (and any technical wrappers) to find `IllegalArgumentException`.

**Q2.** On the same future, what does `get()` report? **`ExecutionException`**; `getCause()` holds the reason the task completed exceptionally.

**Q3.** `future.exceptionally(error -> 0)` returns a new stage. If the source fails, can the new stage succeed? **Yes**, when the callback returns `0` normally. The source future remains failed.

**Q4.** `allOf(a, b)` completes exceptionally, and both `a` and `b` failed. Does the `allOf` error contain enough data to pinpoint both causes? **No**. You must inspect each future individually.

**Q5.** `future.get(100, MILLISECONDS)` times out, but a few seconds later `future.join()` returns a value. Is this a contradiction? **No**: the first wait expired, while the future was still able to continue and complete normally.

**Q6.** A `whenComplete` stage throws when the source stage succeeded. Where did the new stage's error come from? **From the observation callback itself**; check which stage is being awaited and where the exception was actually thrown.

To trace asynchronous errors, start from the **failing stage**, check the **wrapper type at the observation point**, strip the **technical wrappers** to find the **meaningful exception**, and then use the **stack trace and per-step context** to pinpoint the failure location. This approach preserves both the root error details and the path the error took through the `CompletableFuture` chain.

## API References

- [Java 21 API — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): contracts of `get`, `join`, `handle`, `whenComplete`, `allOf`, `orTimeout`, and `cancel`.
- [Java 21 API — `CompletionException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionException.html) and [Java 21 API — `ExecutionException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutionException.html): the two common wrapper exception types.

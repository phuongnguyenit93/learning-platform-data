# Error Propagation Across Dependent Stages in CompletableFuture (Java)

## 1. What Happens to Downstream Stages When a Stage Fails?

`CompletableFuture<T>` represents a computation that will either **complete with a value** or **complete exceptionally** (*exceptional completion*). Multiple stages can be chained into a processing pipeline using methods such as `thenApply`, `thenCompose`, `thenAccept`, `handle`, or `exceptionally`.

The fundamental rule of a dependency chain is:

> When a source stage completes exceptionally, dependent stages that **require a successful value** from the source will not execute their normal processing callback. The dependent stage still completes, but **completes exceptionally** to propagate the failure information down the chain, unless an appropriate error-handling stage is present.

Example:

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(5)
            .thenApply(n -> n * 2)
            .thenApply(n -> {
                throw new IllegalStateException("cannot convert");
            });
```

This is a **code snippet placed inside a method** with `java.util.concurrent.CompletableFuture` imported. The first stage returns `5`, the next stage returns `10`, and the final callback throws `IllegalStateException`. The `result` future completes exceptionally instead of returning an `Integer`. If another `thenApply` depends on `result`, its callback **is not invoked**, and the new stage also receives an exceptional status.

**"Error propagation" does not mean a `Throwable` automatically jumps from one worker thread to the call stack of another thread.** It is a mechanism for **propagating exceptional completion state between stage objects**; the caller only receives the exception when actively waiting for or retrieving the result via `join()`, `get()`, or when a stage has an error-handling handler.

## 2. Stage, Dependency, and Completion Model

A stage can be in the following conceptual states:

- **Incomplete:** does not yet have a final result; dependent stages are waiting for the completion condition.
- **Completed normally:** has a result value, which may be `null` for `Void` types or where the contract permits.
- **Completed exceptionally:** terminated abnormally due to an exception, a wrapped error, or cancellation; there is no successful result to pass to normal callbacks.

A chain:

```text
source (value)
   |
   v
thenApply A  --> success: output A
   |
   v
thenApply B  --> throws exception E
   |
   +-------------------------------+
   |                               |
   v                               v
thenApply C                     exceptionally D
(callback C is skipped)         (receives E, can provide fallback)
   |                               |
   v                               v
exceptional completion          normal completion if D returns a value
```

Two branches depending on the same source do not necessarily have the same final outcome. One branch can recover to return a success; the other branch can continue to fail. **Handling an error in a dependent stage does not retroactively modify the state of the source stage.** This mindset is important when composing multiple processing flows, APIs, or requests.

## 3. When Is the Next Callback Executed?

You must distinguish between callbacks that **only receive a successful value**, callbacks that **only run on error**, and callbacks that **handle both**.

| Stage API | Condition for invoking the stage's callback | Outcome when upstream fails |
| --- | --- | --- |
| `thenApply(fn)` | Upstream succeeds; requires value | Skips `fn`; new stage completes exceptionally |
| `thenAccept(action)` | Upstream succeeds | Skips `action`; new stage completes exceptionally |
| `thenRun(action)` | Upstream succeeds (does not use value) | Skips `action`; new stage completes exceptionally |
| `thenCompose(fn)` | Upstream succeeds; `fn` returns another stage | If upstream fails, `fn` is not called; new stage fails |
| `thenCombine(other, fn)` | Both sources succeed | `fn` is not called if success condition is not met; combined stage fails |
| `exceptionally(fn)` | Upstream fails | `fn` can return a fallback value and recover |
| `handle((v,e) -> ...)` | Upstream succeeds or fails | Can transform the result/error into a value or throw a new error |
| `whenComplete((v,e) -> ...)` | Upstream succeeds or fails | Primarily for observation; normally preserves the previous state/result |

In all three methods `thenApply`, `thenAccept`, and `thenRun`, if the callback **is invoked and throws an exception itself**, the resulting stage also completes exceptionally. The error propagation mechanism therefore occurs both when **upstream has already failed** and when **a downstream callback creates a new error**.

A notable detail: `thenRun` does not accept a value, yet it **still depends on the successful completion** of the source. Not using the value does not mean the callback will run when the source fails.

## 4. Propagation Across Successive Stages

Consider the chain:

```java
CompletableFuture<String> pipeline = fetchUser()
        .thenApply(user -> parseUser(user))
        .thenApply(parsed -> formatDisplay(parsed))
        .thenApply(text -> decorate(text));
```

This is a **design snippet**; the methods `fetchUser()`, `parseUser()`, `formatDisplay()`, and `decorate()` are defined by the application. Suppose `parseUser` throws `IllegalArgumentException`:

1. The `fetchUser()` stage succeeded, so `parseUser` is invoked.
2. The `parseUser` callback throws an exception, causing the first `thenApply` stage to **complete exceptionally**.
3. `formatDisplay` needs the `parsed` value from the failed stage; since there is no successful value, the callback **does not run**.
4. `decorate` is also not invoked because the preceding stage completed exceptionally.
5. The final `pipeline` future has an exceptional completion state, even though the code created all the stages when constructing the pipeline.

There is no requirement that every stage **must run** for the final stage to complete. When a dependency fails, the runtime can propagate the exceptional completion signal through the entire chain without invoking any downstream data-processing callbacks.

This prevents processing a missing or invalid value; at the same time, it easily causes bugs if an application places mandatory actions (*audit*, *cleanup*, *metrics*) in a final `thenApply`: when an earlier stage fails, those actions **never run**. Use `whenComplete`, `handle`, or a dedicated cleanup mechanism when you need to observe both states.

## 5. Java 17+ Example: Verifying Multiple Propagation and Recovery Branches

The standalone program below tests:

- The second stage throws `IllegalStateException`.
- A subsequent `thenApply` is **skipped**.
- `exceptionally` produces a fallback, allowing a downstream stage to run normally.
- `handle` converts an error into a result.
- `whenComplete` observes the error but **does not automatically recover**.
- `thenCompose` receives a failed child future.
- `get()` and `join()` report errors using different wrappers.
- `allOf` yields an exceptional state when one member fails, while an independent future still succeeds.

Create the file **`CompletableFutureFailureChainDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureFailureChainDemo {
    static Throwable root(Throwable error) {
        while ((error instanceof CompletionException
                || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger downstreamRuns = new AtomicInteger();

        CompletableFuture<Integer> chain =
                CompletableFuture.completedFuture(4)
                    .thenApply(n -> n * 2)
                    .thenApply(n -> {
                        if (n == 8) {
                            throw new IllegalStateException("conversion failed");
                        }
                        return n;
                    })
                    .thenApply(n -> {
                        downstreamRuns.incrementAndGet();
                        return n + 1;
                    });

        try {
            chain.join();
        } catch (CompletionException ex) {
            System.out.println("CHAIN: " + root(ex).getClass().getSimpleName());
        }
        System.out.println("DOWNSTREAM RUNS: " + downstreamRuns.get());

        CompletableFuture<Integer> recovered =
                chain.exceptionally(ex -> 99).thenApply(n -> n + 1);
        System.out.println("RECOVERY: " + recovered.join());

        CompletableFuture<String> handled = chain.handle((value, error) ->
                error == null ? "ok" : "failed");
        System.out.println("HANDLE: " + handled.join());

        CompletableFuture<Integer> observed = chain.whenComplete(
                (value, error) -> {
                    if (error != null) {
                        System.out.println("OBSERVED: "
                                + root(error).getClass().getSimpleName());
                    }
                });
        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("WHENCOMPLETE: "
                    + root(ex).getClass().getSimpleName());
        }

        CompletableFuture<Integer> composed =
                CompletableFuture.completedFuture(5)
                    .thenCompose(n -> CompletableFuture.<Integer>failedFuture(
                            new IllegalArgumentException("remote failed")))
                    .thenApply(n -> n + 1);
        try {
            composed.join();
        } catch (CompletionException ex) {
            System.out.println("COMPOSE: "
                    + root(ex).getClass().getSimpleName());
        }

        try {
            chain.get();
        } catch (ExecutionException ex) {
            System.out.println("GET: " + root(ex).getClass().getSimpleName());
        }

        CompletableFuture<Integer> independent =
                CompletableFuture.completedFuture(10);
        CompletableFuture<Void> combined =
                CompletableFuture.allOf(chain, independent);
        try {
            combined.join();
        } catch (CompletionException ex) {
            System.out.println("ALLOF: "
                    + root(ex).getClass().getSimpleName());
        }
        System.out.println("INDEPENDENT: " + independent.join());
        System.out.println("SOURCE STILL FAILED: " + chain.isCompletedExceptionally());
    }
}
```

Compile and run with JDK 17 or later, from the directory containing the file:

```bash
javac -encoding UTF-8 CompletableFutureFailureChainDemo.java
java CompletableFutureFailureChainDemo
```

Expected output:

```text
CHAIN: IllegalStateException
DOWNSTREAM RUNS: 0
RECOVERY: 100
HANDLE: failed
OBSERVED: IllegalStateException
WHENCOMPLETE: IllegalStateException
COMPOSE: IllegalArgumentException
GET: IllegalStateException
ALLOF: IllegalStateException
INDEPENDENT: 10
SOURCE STILL FAILED: true
```

**Explanation of each key point:**

1. `chain` is built from `4 → 8`, after which a callback throws an error. The final `thenApply` of `chain` is skipped, so `downstreamRuns` is `0`.
2. `chain.exceptionally(ex -> 99)` creates **another stage** that returns `99`, and then `thenApply` adds `1`, so `recovered.join()` returns `100`. The original `chain` remains exceptional.
3. `handle` receives both value and error; on the error path it produces the string `"failed"`, so the `handled` stage completes normally.
4. `whenComplete` prints the error type and the `observed` stage still fails. `whenComplete` is an observation mechanism, not a fallback.
5. `thenCompose` receives a child future that is already exceptionally completed via `failedFuture`; the error enters the `composed` stage, and the subsequent `thenApply` callback is skipped.
6. `join()` on an exceptional future typically throws `CompletionException`, whereas `get()` throws `ExecutionException`; the `root` helper unwraps these wrappers to print the cause's class name.
7. `allOf` completes exceptionally because one of its two members failed. The `independent` future still holds `10`; the failure of `chain` **does not automatically fail an independent future**.
8. `chain.isCompletedExceptionally()` remains `true` even though successful branches `recovered` and `handled` were created from it.

The example uses `completedFuture` and `failedFuture` so that the output has a deterministic order without depending on a scheduler. `root` only illustrates reading a wrapped cause chain; in a real application, not every `CompletionException`/`ExecutionException` should be stripped mechanically if the wrapper itself carries domain semantics.

## 6. `join()`, `get()`, and the Actual Cause

When a `CompletableFuture` completes exceptionally, the caller does not "receive the exception immediately" when constructing the stage. The error information is stored in the completion state, and the APIs that wait for or retrieve the result **throw the exception on the thread calling that API**.

| API | When the future has failed | Key points to remember |
| --- | --- | --- |
| `future.join()` | Typically throws `CompletionException`, with the cause in `getCause()` | Unchecked wrapper; does not declare checked exceptions |
| `future.get()` | Throws `ExecutionException`, with the cause in `getCause()` | Can also throw `InterruptedException` if the waiting thread is interrupted |
| `future.get(timeout, unit)` | Similar to `get()` if the future failed, plus `TimeoutException` if no result arrives in time | Caller timeout does not automatically cancel upstream |
| `future.isCompletedExceptionally()` | Returns `true` when the future completed exceptionally, including cancellation | Status only; does not provide cause details |
| `future.isDone()` | Returns `true` when completed with a value, error, or cancellation | Does not equate to success |
| `future.isCancelled()` | Indicates that this specific future was cancelled | Distinguishes cancellation from business errors |

A dependent stage may hold a `CompletionException` whose cause is the original exception. Therefore, `getCause()` may return an intermediate wrapper depending on the source and how it completed. When diagnosing issues, walk the cause chain with a bound, log the stage context as well, and do not merely print `ex.getMessage()` or guess the error type from text.

`InterruptedException` in `future.get()` is a signal that **the waiting caller thread** was interrupted, which is distinct from a failure in the source task. When the caller cannot propagate `InterruptedException`, it should generally call `Thread.currentThread().interrupt()` and then terminate or execute an appropriate cancellation policy. Interrupting the caller **does not automatically complete or cancel the source future**.

A future that has been `cancel(...)`ed may cause `join()`/`get()` to throw `CancellationException` directly; do not use a single `catch (CompletionException)` and claim it covers all cancellation cases.

## 7. Recovering with `exceptionally`: Turning an Error into a Valid Value

`exceptionally(fn)` only invokes `fn` when the source stage completes exceptionally. If the source stage succeeds, it preserves the successful result (matching the result type) without calling the fallback.

```java
CompletableFuture<Integer> finalCount = readCountAsync()
        .exceptionally(ex -> {
            recordFailure(ex);
            return 0;
        })
        .thenApply(n -> n + 1);
```

This is a code snippet with `readCountAsync()` and `recordFailure(Throwable)` defined by the application. When upstream fails, the callback returns `0`, after which `thenApply` is invoked and produces `1`. When upstream succeeds with `n`, the fallback callback does not run and the final result is `n + 1`.

**Be careful with fallback values:** `0` might be a genuinely valid count; if `0` masks an important error, the caller will assume it read valid data. Only use a fallback when business logic permits it and when there is a mechanism to record warnings, data reliability, or a "degraded" status as needed.

If the `exceptionally` callback throws an error itself, the returned stage will **complete exceptionally with the new error**. You can preserve the original cause using a constructor that accepts `cause` when appropriate, for example:

```java
.exceptionally(ex -> {
    throw new IllegalStateException("Fallback also failed", ex);
})
```

This is a chain snippet, not a full program. Once again, the **new stage** carries the result, while the upstream stage is not modified.

## 8. `handle`: Operating on Both Result and Error

`handle((value, error) -> result)` always receives the completion of the previous stage, whether it succeeded or completed exceptionally:

- On success: `error == null` and `value` holds the result (the value itself may be `null` if the contract allows).
- On failure: `error != null` and there is no successful value to use.
- If the callback returns a value normally, the new stage **succeeds**.
- If the callback throws an error, the new stage **fails**.

Example:

```java
CompletableFuture<String> display = loadProfileAsync()
        .handle((profile, error) -> {
            if (error != null) {
                return "Profile temporarily unavailable";
            }
            return profile.displayName();
        });
```

The snippet above assumes `loadProfileAsync()` returns a future of type `Profile` with `displayName()`, and is not a standalone program. You must not call `profile.displayName()` when `error != null`. Conversely, if the loader can **succeed while returning `null`**, you still need to check `profile` according to the contract to avoid creating a `NullPointerException` in the error-handling stage itself.

`handle` is suitable when you want to unify both paths into a single result type, such as `Result<T>` containing `value/error`. However, it can also accidentally swallow errors if the `error != null` branch always returns a dummy value without surfacing the failure to the business layer.

## 9. `whenComplete`: Observing Without Automatic Recovery

`whenComplete((value,error) -> action)` allows executing a callback when the source completes, whether with a value or an error; it is typically used for logging, metrics, tracing, or cleanup without altering the result:

```java
CompletableFuture<Order> observed = loadOrderAsync()
        .whenComplete((order, error) -> {
            if (error != null) {
                metrics.recordFailure(error);
            } else {
                metrics.recordSuccess();
            }
        });
```

The snippet above requires `Order`, `loadOrderAsync()`, and `metrics` defined by the application. If the source fails and the `whenComplete` callback runs normally, the `observed` stage still completes exceptionally. If the source succeeds and the callback runs normally, the `observed` stage carries the same result.

**Note when the observation callback also throws an exception:**

- Source **succeeds**, `whenComplete` throws → the resulting stage can **fail due to the callback**.
- Source **already failed**, `whenComplete` also throws → according to the `CompletionStage.whenComplete` contract, **the original error takes precedence** when determining the exception of the resulting stage.
- A `whenComplete` callback should not contain business logic that heavily depends on uncertain state, or cause the entire pipeline to fail merely because metrics/logging are unavailable.

If you want to **convert an error into another value**, use `exceptionally` or `handle`. If you want to **run a side effect and preserve the result**, use `whenComplete` with a carefully designed observation path.

## 10. `thenCompose` and Propagation from a Child Future

`thenCompose(fn)` is used when a callback returns **another stage**, for example querying account information and then loading transactions from an external system. It avoids nested types like `CompletableFuture<CompletableFuture<T>>`.

```java
CompletableFuture<Account> result = findUserAsync(userId)
        .thenCompose(user -> findAccountAsync(user.accountId()));
```

This is a snippet with `findUserAsync` and `findAccountAsync` already defined. There are **three main failure paths**:

1. `findUserAsync` fails → the `thenCompose` callback **is not invoked**; the resulting stage fails.
2. `findUserAsync` succeeds, but the `user -> ...` callback throws an exception itself → the resulting stage fails.
3. The callback returns a child future normally, but **the child future subsequently fails** → the final resulting stage also completes exceptionally with the child future's error.

`thenCompose` does not automatically catch, retry, or roll back errors from the child future. Nor is it forced to run on a specific thread; the callback may run on the thread that completed the source or another thread according to the API policy and sync/async variant.

With Java 17, `CompletableFuture.failedFuture(Throwable)` is available to create a future that is already exceptionally completed, as shown below:

```java
CompletableFuture<Integer> unavailable =
        CompletableFuture.failedFuture(
                new IllegalStateException("backend unavailable"));
```

This is a valid code snippet inside a method. It is useful for unit testing error paths without needing to spawn threads or create real failing connections.

## 11. `exceptionallyCompose`: When the Fallback Is Also an Async Operation

When recovery needs to invoke **a fallback future** instead of returning a value immediately, modern JDKs (including JDK 17) provide `exceptionallyCompose`:

```java
CompletableFuture<String> data = fetchPrimaryAsync()
        .exceptionallyCompose(ex -> fetchReplicaAsync());
```

This is an illustrative snippet with `fetchPrimaryAsync()` and `fetchReplicaAsync()` returning `CompletableFuture<String>`. If the primary succeeds, the fallback callback does not run. If the primary fails, the callback is used to obtain a new stage; if the new stage succeeds then `data` succeeds, whereas if the fallback stage fails then `data` also fails.

Similar to `exceptionally`, the fallback callback can throw an exception itself; whether the callback or replica succeeds does not alter the error state stored in the primary stage. If you need to preserve the primary error when the replica also fails, you must collect the appropriate context/cause; you **must not** expect the API to automatically merge both causes into a complete list.

An automatic fallback can generate unexpected traffic or route data across different trust boundaries; define timeouts, data consistency expectations, retry policies, and security requirements for the replica.

## 12. Error Relationships in Branching (Fan-Out)

A single source can have multiple dependent stages:

```java
CompletableFuture<Data> source = loadAsync();
CompletableFuture<Summary> summary =
        source.thenApply(this::makeSummary);
CompletableFuture<Report> report =
        source.thenApply(this::makeReport);
```

This is a snippet inside a class with types `Data`, `Summary`, `Report` and methods `loadAsync()`, `makeSummary`, `makeReport`. If `source` fails, **both dependent stages that require a successful value** can complete exceptionally without invoking their callbacks. If `source` succeeds but `makeSummary` fails, `report` **does not automatically fail** just because its sibling branch encountered an error; each branch handles its own result/cause.

Design considerations:

- One branch calling `exceptionally` and recovering does not mean the other branches are also recovered.
- One branch throwing an exception in its callback does not automatically cancel sibling branches.
- If all branches share a mutable object as the result of `source`, a failure in one branch does not automatically roll back modifications already made to that object.
- If callbacks run concurrently, ensure thread safety and do not assume log ordering.
- For errors observable across multiple stages, avoid logging the same incident multiple times without a correlation ID.

## 13. Combining with `thenCombine`, `allOf`, and `anyOf`

### `thenCombine` / `thenAcceptBoth` / `runAfterBoth`

*Both*-style combinators require both sources to succeed before running the success callback:

```java
CompletableFuture<Result> combined =
        first.thenCombine(second, (a, b) -> merge(a, b));
```

This is a snippet inside a method where `first`, `second`, and `merge` are defined. If either source fails, the `merge` callback **is not invoked**; the resulting stage completes exceptionally when the combinator's completion condition is met. If **both sources fail**, the API does not provide a complete list of both exceptions as a default result; which error is observed may depend on the dependency relationship and implementation. If you need to audit both, you must track both sources separately.

### `CompletableFuture.allOf(...)`

`allOf(a,b,...)` creates a `CompletableFuture<Void>` that completes when **all** input futures complete. If **any** input completes exceptionally, `allOf` also completes exceptionally. It does not produce a list of results; callers that want individual values must retain references to the child futures and read them according to contract afterward as appropriate.

`allOf` **does not automatically cancel other futures just because one future failed**. Whether an independent future has already succeeded or is still running is a separate matter. If multiple futures fail, the exception exposed by the aggregate future **does not replace collecting all errors** when the application needs full diagnostics. Do not assume `allOf` is "fail-fast and auto-cancels siblings" like a specialized structured concurrency mechanism.

### `CompletableFuture.anyOf(...)`

`anyOf(a,b,...)` completes when **any** future completes first according to its completion condition. If the first future completes **exceptionally**, `anyOf` may also complete exceptionally, even if another future succeeds later. This is not "return the first successful result"; waiting for the **first success** requires a custom design with error and cancellation conditions.

If multiple futures complete nearly simultaneously, do not rely on a particular processing order or a "guaranteed chosen" error type without explicit synchronization and constraints.

## 14. Cancellation Can Also Propagate as Exceptional Completion

When `cancel(...)` is called on an incomplete `CompletableFuture`, that future is **exceptionally completed with `CancellationException`**. Stages that depend on its success will not run their success callbacks; those stages typically complete exceptionally, and a `CompletionException` wrapping `CancellationException` may appear when observed.

Distinguish clearly:

- **Cancelling upstream:** dependent stages do not receive a successful value from the cancelled source; they can become exceptional.
- **Cancelling a dependent stage:** does not implicitly stop work in upstream or siblings; do not infer a general backward-propagating cancellation mechanism.
- **`CompletableFuture.cancel(boolean)`:** the `mayInterruptIfRunning` parameter does not play the same role as in `FutureTask` for interrupting the executing thread; cancelling a `CompletableFuture` **does not automatically guarantee stopping running code**.
- **Future wrapper:** `isCompletedExceptionally()` returns `true` even when cancelled; to distinguish, use `isCancelled()` or inspect the exception.
- **External side effects:** cancelling a future does not automatically roll back DB writes, files, or HTTP requests that have already been sent.

Example of observing a direct cancellation:

```java
CompletableFuture<Integer> source = new CompletableFuture<>();
CompletableFuture<Integer> dependent = source.thenApply(n -> n * 2);
source.cancel(false);
// dependent cannot run thenApply with source's successful value.
```

This is an illustrative snippet. You should not infer that every dependent has `isCancelled() == true`; a dependent may complete exceptionally via a wrapper containing `CancellationException` **without carrying the same cancelled flag as the source**.

If you use executors, background tasks, and `CompletableFuture` together, you need a dedicated cancellation protocol suited to the APIs and actual state.

## 15. Timeout Is Another Source of Exceptional Completion

Two useful APIs on `CompletableFuture`:

- `orTimeout(timeout, unit)`: if not completed when the deadline expires, completes that `CompletableFuture` itself exceptionally with `TimeoutException`; dependent stages handling success may be skipped.
- `completeOnTimeout(value, timeout, unit)`: if not completed when the deadline expires, completes the future itself with a **fallback value**, so downstream stages can run normally.

These methods return the future they were called on and **mutate its own completion state**; they do not always create a new independent dependent stage. For example, if you call `source.orTimeout(...)`, the timeout can affect every branch using the same `source` object. Be careful when a future is widely shared.

A future timeout **does not automatically stop** background tasks or undo side effects. The computation thread may continue after the future has completed due to timeout; a later `complete(...)` call may not change the already-determined result. For network communication, you need client/dependency-level timeouts and a separate cancellation/reconciliation mechanism if business logic requires it.

`get(timeout, unit)` has different semantics: it limits **how long the calling thread waits**, and does not implicitly complete the awaited `CompletableFuture` with a timeout error. Confusing the two forms of timeout can cause dependent branches to be affected unexpectedly.

## 16. Exceptions in Async Callbacks and Executor Selection

Methods with the `Async` suffix such as `thenApplyAsync` or `thenComposeAsync` can execute callbacks on a different executor; if no explicit executor is passed, they use the API's default executor policy. However, **the exceptional completion rules remain the same**: a callback requiring a successful value does not run if upstream has failed; a callback that runs and throws an error causes the new stage to fail.

Example:

```java
CompletableFuture<String> result = fetchAsync()
        .thenApplyAsync(this::parse, executor)
        .thenApply(this::format)
        .exceptionally(ex -> fallbackText(ex));
```

This is a snippet inside a class with `executor` and application methods. If `parse` throws an error on the worker, `format` is not called, and then `exceptionally` can produce a fallback. The error does not unwind to a `catch` block surrounding the pipeline construction statement that already finished earlier.

**Scheduling errors are also worth noting:** if the executor rejects the task (for example, after `shutdown()`), the async callback execution mechanism can lead to exceptional completion involving `RejectedExecutionException`. Depending on the call path and implementation, errors occurring right when building/scheduling a stage may surface differently. You must observe both synchronous errors during pipeline construction and the error state of the resulting future, rather than assuming all failures occur only inside callbacks.

Callbacks without the `Async` suffix are also **not guaranteed to run on the main thread**. If the source has already completed before registration, the callback may run immediately on the registering thread; if the source completes later, a thread performing the completion may run the callback. Do not use `ThreadLocal` or assume MDC/tracing context will automatically transfer across every stage; use an explicit context propagation mechanism when required.

## 17. Choosing the Right Placement for Error Handlers

The position of `exceptionally` or `handle` in the chain changes which errors it catches.

### Handler in the middle

```java
CompletableFuture<Integer> result =
        source.thenApply(this::parseNumber)
              .exceptionally(ex -> 0)
              .thenApply(this::invert);
```

This is a snippet inside a class with `source` and methods `parseNumber`, `invert`. The handler in the middle handles errors occurring **before it** and returns `0`. However, `invert(0)` may throw an error (for example, division by zero); this error occurs **after the handler**, so the earlier handler **cannot catch** it. The final stage can still fail.

### Handler at the end

```java
CompletableFuture<Integer> result =
        source.thenApply(this::parseNumber)
              .thenApply(this::invert)
              .exceptionally(ex -> 0);
```

The handler at the end receives failures from any preceding stage on **this dependency path**, including `parseNumber` and `invert`. However, it also risks lumping very different errors into a single fallback. If a parse error is due to invalid user data while an invert error is due to a programming bug, recovery policies may need to differ.

### A handler for one branch does not mean a handler for all branches

```java
CompletableFuture<Integer> a = source.thenApply(this::a);
CompletableFuture<Integer> b = source.thenApply(this::b);
CompletableFuture<Integer> safeA = a.exceptionally(ex -> -1);
```

This snippet has the appropriate methods defined. `safeA` only recovers branch `a`; it does not automatically fix `b`. If you need to observe the entire fan-out failure, keep handles to each branch or use a state-aggregation mechanism.

## 18. A New Error Can Replace an Old Error Through a Handler Stage

Handler methods have callbacks, and callbacks themselves can fail:

- `exceptionally(fn)`: source fails with E, but `fn` throws F → the new stage fails with F; preserve information about E via `cause` when appropriate.
- `handle((v,e) -> ...)`: callback throws F → the new stage fails with F, whether the source succeeded or failed with E.
- `whenComplete((v,e) -> ...)`: the goal is to preserve the source result; if the source already failed and the callback also fails, the source exception takes precedence according to the method's contract.
- `thenApply(fn)`: source succeeds, `fn` throws F → the new stage fails with F.
- `thenCompose(fn)`: source succeeds, callback throws F or child future fails with F → the new stage fails with that failure.

Example of preserving the cause:

```java
CompletableFuture<Integer> converted = source.exceptionally(ex -> {
    throw new IllegalStateException("Conversion fallback failed", ex);
});
```

This is a code snippet, with `source` as `CompletableFuture<Integer>`. Passing `ex` as the cause helps preserve context. However, `ex` may be a `CompletionException` wrapper; callers should inspect the cause chain as needed.

Do not write code that treats every `RuntimeException` as a transient error. A bug such as `NullPointerException` in a handler usually needs to be detected, alerted, and fixed rather than blindly retried.

## 19. When You Need to Collect All Errors, `allOf` Is Not Enough

Suppose three data-loading tasks run in parallel. If you only write:

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(loadA(), loadB(), loadC());
```

then the `all` future can report that at least one task failed, but it does not automatically provide **a complete list of errors** nor all successful values. If auditing each task is required, retain the child futures and transform each completion into a structured result.

Structured example (conceptually standalone; requires defining `Result<T>` for the application):

```java
CompletableFuture<Result<String>> observedA = loadA()
        .handle((value, error) ->
                error == null ? Result.success(value) : Result.failure(error));

CompletableFuture<Result<String>> observedB = loadB()
        .handle((value, error) ->
                error == null ? Result.success(value) : Result.failure(error));
```

This is a **design snippet**, not a standalone program; `Result.success` and `Result.failure` are application-chosen APIs. Because each `handle` converts completion into a normal `Result` value, you can use `allOf(observedA, observedB)` and then retrieve each `Result`. If a handler throws an exception itself, the corresponding future can still fail, so design a reliable observation path.

Do not assume `allOf` automatically stops sibling tasks when one task fails; if tasks have side effects, you must have separate cancellation, transaction, and idempotency mechanisms.

## 20. Error Propagation Does Not Mean Automatic Rollback

A pipeline might look like:

```java
CompletableFuture<Void> job = updateDatabaseAsync()
        .thenCompose(ignored -> sendNotificationAsync())
        .thenRun(() -> markFinished());
```

This is a snippet with three application-defined methods. If `updateDatabaseAsync` has already committed and then the `sendNotificationAsync` stage fails, `thenRun(markFinished)` is skipped and `job` fails. However, the database **has already committed**, and the notification may even have been sent with a lost ACK.

Therefore:

- Exceptional completion only describes the **pipeline** outcome; it does not undo side effects that have already occurred.
- Callers should not retry the entire pipeline without knowing which parts have already committed.
- Where possible, record the business outcome and the intent to emit an event in the same DB transaction using an outbox; use idempotency keys to prevent duplicate sends/writes.
- When a pipeline has multiple sources, store the request ID, stage ID, last success timestamp, and uncertain states.
- Do not use `exceptionally(ex -> null)` to turn every failure into an "empty success" if the caller needs to know the business operation did not complete.

For a stage that recovers via a fallback, define clearly: **under which contract** did the system succeed? "Reading stale cache" may be an acceptable degraded result, whereas "transferring money and ignoring a notification error" requires ensuring data and remaining steps are tracked.

## 21. Proper Logging, Tracing, and Error Observation

A long pipeline can produce multiple exception wrappers; if every stage logs a stack trace and rethrows, a single root error easily creates excessive duplicate logs. Choose clear observation boundaries:

1. Attach a correlation ID/request ID along the business flow, rather than relying solely on thread names.
2. Log the cause and stage context: data source, operation, timeout, retry count, upstream status.
3. Have a single place responsible for logging the final pipeline failure; if metrics are needed at multiple stages, avoid spamming duplicate logs.
4. Preserve `Throwable#getCause()` when translating error types, and do not arbitrarily strip stack traces.
5. Never log tokens, passwords, private payloads, or sensitive connection strings.
6. If a fallback is used, distinguish *normal completion with degraded result* from full success so monitoring is not blind.

Example:

```java
return callRemoteAsync()
        .whenComplete((value, error) -> {
            if (error != null) {
                metrics.failedOperation("remote-call");
            }
        });
```

This is a snippet inside a method with `callRemoteAsync` and `metrics` defined by the application. The metric-recording path must be reliable enough; if it throws an exception when upstream succeeded, the returned stage can become a new failure.

## 22. Testing Propagation Across Stages

A good test suite does not only `assertThrows` at the end, but also verifies **which callbacks ran, whether the original stage's result was altered, and which cause chain is preserved**.

| Scenario | Expectation |
| --- | --- |
| Source stage succeeds | `thenApply` callback is invoked, dependent holds the value |
| `thenApply` callback throws exception E | Dependent completes exceptionally |
| Earlier stage fails with E, later stage is `thenApply` | Later stage's callback **does not run**, dependent is exceptional |
| `exceptionally` placed after failed stage | Error callback is invoked, returns normal fallback |
| `exceptionally` placed before a new failing stage | Earlier handler cannot catch the new downstream error |
| `handle` on succeeding/failing source | Receives `value` or `error` appropriately and can produce a normal stage |
| `whenComplete` on failing source | Runs observation callback, but returned stage still fails |
| `thenCompose` with failing child future | Resulting stage fails even though outer source succeeded |
| `thenCombine` with one failing source | Success-combining callback is not invoked |
| `allOf` with one failing source | Aggregate future fails; independent future is not auto-cancelled |
| `anyOf` when first future completes exceptionally | Aggregate result can be exceptional |
| `CompletableFuture.cancel` | Dependents react to exceptional completion; do not infer upstream was interrupted |
| `get` interrupted on caller | `InterruptedException` belongs to caller; source future does not auto-fail from waiting interruption |
| `orTimeout` before source completes | Future times out and success-handling dependents may be skipped |

Use `completedFuture`, `failedFuture`, and `AtomicInteger` or `CountDownLatch` to construct exact scenarios. Avoid `Thread.sleep` and guessing when callbacks run if you can wait on a clear condition. For timeout/cancellation tests, choose reasonable bounds and clean up executors after tests so the test suite does not hang.

If testing real async contexts, you can use a controllable executor and verify thread safety, but **do not depend on callback ordering** when the contract does not guarantee it.

## 23. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "When a stage fails, all callbacks after it still run and automatically receive `null`." | Success-handling callbacks like `thenApply` **are not invoked** when upstream is exceptional. |
| "`thenRun` does not use the value, so it still runs when upstream fails." | `thenRun` still requires the source to complete **normally**. |
| "`exceptionally` modifies the state of the source future." | It creates a **new stage**; the source keeps its existing state. |
| "`whenComplete` automatically recovers from errors." | It is primarily for observation; without another mechanism, the error still propagates. |
| "`get()` and `join()` return the same wrapper type." | `get()` uses `ExecutionException`; `join()` typically uses `CompletionException` on failure. |
| "`thenCompose` only fails when the outer callback throws an exception." | The child future returned by the callback can also fail later. |
| "A failure in one branch automatically cancels all sibling branches." | There is no general backward or cross-branch cancellation propagation. |
| "`allOf` returns a list of all results and all exceptions." | It returns `CompletableFuture<Void>`, and does not build a full list of results/errors. |
| "`anyOf` waits for the first success." | It follows the **first future to complete**, including exceptional completion. |
| "If a future reports a timeout, the background task definitely stops." | Timeout completion and stopping computation/side effects are two separate concerns. |
| "An exception on a worker propagates straight to a `catch` around pipeline creation." | Errors are recorded in completion; the caller must observe the future or a handler. |
| "The pipeline failed, so the database rolled back." | Exceptional completion does not automatically undo side effects outside the future. |

## 24. CompletableFuture Chain Design Checklist

1. Map out dependencies between stages and identify which stages require a successful result to run.
2. Distinguish **errors originating from a callback** from **errors propagated from upstream**.
3. Place `exceptionally`/`handle` at the exact point where recovery is needed; avoid fallbacks that mask serious errors.
4. Use `whenComplete` to observe both success and failure, while guarding against errors from logging/metrics.
5. With `thenCompose`, track child future errors and the cancellation policy of the entire task.
6. When using `allOf` or fan-out, keep references to child futures if you need all results or all causes.
7. Understand `CompletionException`/`ExecutionException` wrappers, `CancellationException`, `TimeoutException`, and caller `InterruptedException`.
8. Do not assume callbacks run on a specific thread; choose appropriate executors, context propagation, and thread safety.
9. Define post-failure states for side effects: not started, committed, recovering, outcome unknown.
10. Test each stage's error path, skipped callbacks, recovery callbacks, and independent branches using clear synchronization signals.

**Remember:** in `CompletableFuture`, when a stage fails, dependent stages that require a successful value are typically **marked as failed without running their callbacks**. To continue, an error-handling stage such as `exceptionally` or `handle` must be placed appropriately; to know the cause, you must observe the completion and cause chain. This mechanism propagates failure state across dependencies, rather than transferring exception stacks across threads or rolling back already-executed work.

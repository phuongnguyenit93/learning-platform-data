# CompletableFuture.exceptionally: Recovering with a Result

In Java, a `CompletableFuture<T>` can **complete normally** with a value of type `T`, or **complete exceptionally** (*exceptional completion*) with a failure cause. The `exceptionally` method lets you register a handler for the failure branch and **turn that failure branch into a replacement value**. If recovery succeeds, the stage returned by `exceptionally` completes normally with the fallback value.

This is an important tool for building readable asynchronous flows: instead of letting every failure propagate to `join()` or `get()`, the application can decide that a specific error can be turned into a **meaningful result**. However, you must distinguish between **recovering to continue** and **merely logging an error**, **retrying a task**, or **hiding a serious bug**.

This article belongs to the *Java core - exception* topic, in the `CompletableFuture` group. The examples use Java 17 or later and require no external libraries.

## 1. Fundamental Mechanism: Normal Completion and Exceptional Completion

A `CompletableFuture` is an object representing a result that may appear later. It can be incomplete, completed normally, or completed exceptionally. For example:

```java
CompletableFuture<Integer> success =
        CompletableFuture.completedFuture(100);

CompletableFuture<Integer> failure =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));
```

This is an **illustrative snippet**; you need to import `java.util.concurrent.CompletableFuture` when placing it in a Java program. The two factory methods above create a future already completed with `100` and a future already completed exceptionally with `IllegalStateException`, respectively.

With a processing chain:

```text
Read data → Transform → Validate → Return
    |           |          |
    +-----------+----------+---- may fail
                                   |
                                   v
                             exceptionally
                                   |
                                   v
                        fallback value of type T
                                   |
                                   v
                        stage continues normally
```

`exceptionally` only runs when **the stage immediately preceding it completes exceptionally**. If the preceding stage succeeds, `exceptionally` forwards the success value and **does not invoke the error handler**.

This also shows why **where you place `exceptionally` in the chain** matters. It can only recover from errors in stages **before** it, and it does not automatically catch errors thrown by stages placed **after** it.

## 2. API Signature and Data Types

In `CompletionStage<T>`, the core signature of the method is:

```java
CompletionStage<T> exceptionally(
        Function<Throwable, ? extends T> fn);
```

This is a simplified signature to explain the types, not a standalone class declaration; the `Function` type belongs to `java.util.function`. On `CompletableFuture<T>`, the method returns `CompletableFuture<T>`.

The `fn` argument is a function that takes a `Throwable` representing the failure of the source stage and returns a **value compatible with type `T`**. For example, if the stage has type `CompletableFuture<Integer>`, the recovery function must return an `Integer` or a compatible value; it cannot return an arbitrary string.

```java
CompletableFuture<Integer> safe = source.exceptionally(error -> 0);
```

This is a snippet assuming `source` has type `CompletableFuture<Integer>`. When `source` fails, `safe` can complete normally with `0`. When `source` succeeds with `42`, `safe` receives `42` and the lambda does not run.

You need to distinguish between two objects:

- **`source`:** the original stage, which keeps its own success or failure state.
- **`safe`:** the **new** dependent stage returned by `exceptionally`; this stage can complete normally thanks to the fallback value.

`exceptionally` **does not mutate the completed state of the original stage**. It creates a new result branch. If you keep both references, other code can still observe the error on `source` while code using `safe` receives the fallback.

## 3. Standalone Java 17 Example: Recovering to a Default Value

Create the file `ExceptionallyDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ExceptionallyDemo {

    private static CompletableFuture<Integer> loadPrice(boolean fail) {
        if (fail) {
            return CompletableFuture.failedFuture(
                    new IllegalStateException("service unavailable"));
        }
        return CompletableFuture.completedFuture(120);
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> failed = loadPrice(true);

        CompletableFuture<Integer> recovered = failed.exceptionally(error -> {
            System.out.println("recover: " + error.getClass().getSimpleName());
            return 0;
        });

        System.out.println("result: " + recovered.join());
        System.out.println("source failed: " + failed.isCompletedExceptionally());
        System.out.println("recovered failed: "
                + recovered.isCompletedExceptionally());

        CompletableFuture<Integer> success = loadPrice(false);
        CompletableFuture<Integer> untouched = success.exceptionally(error -> {
            System.out.println("should not run");
            return -1;
        });

        System.out.println("success: " + untouched.join());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ExceptionallyDemo.java
java ExceptionallyDemo
```

Exact stdout:

```text
recover: IllegalStateException
result: 0
source failed: true
recovered failed: false
success: 120
```

Line-by-line analysis:

1. `loadPrice(true)` creates a future that has failed with `IllegalStateException`.
2. `failed.exceptionally(...)` sees that the source stage completed exceptionally, so it invokes the lambda and receives `0`.
3. `recovered.join()` returns `0` normally because **the recovery stage succeeded**.
4. `failed.isCompletedExceptionally()` is still `true`; `exceptionally` does not clear the error from the source.
5. `recovered.isCompletedExceptionally()` is `false` because the lambda returned a value.
6. `loadPrice(false)` already succeeded with `120`; the lambda in `exceptionally` for this branch does not run, so there is no `should not run` line.

The example uses already-completed futures, so there is no non-determinism from thread scheduling, and the output order is deterministic.

## 4. What Errors Can exceptionally Recover From?

`exceptionally` triggers whenever the source stage completes exceptionally; it does not catch only a single specific exception type. Situations that can lead to exceptional completion include:

- An upstream supplier or function throws a `RuntimeException` or another `Throwable`.
- The upstream stage is completed via `completeExceptionally(cause)` or `failedFuture(cause)`.
- A dependent stage inherits the failure state from a preceding stage.
- A `CompletableFuture` is cancelled, because cancellation is reflected as an exceptional completion.
- The upstream stage is completed exceptionally by a timeout mechanism such as `orTimeout`.

The parameter received by the recovery function is a `Throwable`. Depending on how the upstream stage was completed and how the stage was created, it may be the original exception or a wrapper such as `CompletionException`. **Do not assume `error.getClass()` always equals the exact exception type thrown inside the source lambda**.

Example:

```java
CompletableFuture<String> pipeline =
        CompletableFuture.completedFuture("abc")
                .thenApply(value -> {
                    throw new IllegalArgumentException("bad transform");
                })
                .exceptionally(error -> "fallback");
```

This is a snippet that can be placed inside a method with appropriate imports. `exceptionally` receives the error from the `thenApply` stage and can return `"fallback"`. If your logic needs to classify business exceptions, clarify the wrapper shape of the chain before inspecting the cause.

**Note:** errors caused by `NullPointerException` or upstream bugs can trigger `exceptionally`; that **does not mean every error is appropriate to turn into a normal value**. Normally, you should only recover from errors that the business domain has predefined as acceptable for a fallback.

## 5. Selective Recovery, Avoiding Hiding Programming Bugs

Do not return a fallback value regardless of the cause when the consequences of different errors are not the same.

For example, calculating a recommended selling price might use a cached price when the pricing service is temporarily unavailable. But if the code failed because of severely malformed data, blindly returning `0` could lead to an invalid transaction.

One approach is to classify the exception:

```java
CompletableFuture<Integer> safe = upstream.exceptionally(error -> {
    Throwable cause = unwrapCompletion(error);

    if (cause instanceof PriceServiceUnavailableException) {
        return cachedPrice;
    }

    throw new CompletionException(cause);
});
```

This is a **non-standalone illustrative snippet**: `upstream`, `cachedPrice`, `unwrapCompletion`, and `PriceServiceUnavailableException` are hypothetical components, and `CompletionException` must be imported. For errors allowed by policy, the function returns the fallback. For other errors, it **throws** an exception so the recovery stage remains exceptional; having no fallback is a valid decision.

When you want to preserve error classification, do not wrap it in a `RuntimeException("failed")` with no cause. If you must translate to another error abstraction, preserve the `cause` and document the public contract.

### Controlled Unwrapping

In code that needs to read the underlying cause behind `CompletionException` and `ExecutionException`, you can use a helper:

```java
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

This is an illustrative method; it requires importing `CompletionException` and `ExecutionException` and must be placed inside a class. Only unwrap the wrappers that the handling layer actually understands; **do not strip every cause layer**, because a cause may represent an important application boundary. When rethrowing or propagating the error, preserve cause information for diagnostics.

In many cases, a better design is for the upstream layer to already translate vendor errors into a **stable application error type** before reaching `exceptionally`.

## 6. Distinguishing exceptionally, handle, and whenComplete

These three methods are often confused because all of them can see errors.

| Method | When upstream succeeds | When upstream fails | Primary purpose |
| --- | --- | --- | --- |
| `exceptionally(error -> fallback)` | Forwards the value; does not call the function | Calls the function and can turn the error into a value of type `T` | **Recover the failure branch only** with a value of the same type |
| `handle((value, error) -> result)` | Function is called with the value and `error` is normally `null` | Function is called with the error and `value` is normally `null` | **Transform both branches**, can change the result type |
| `whenComplete((value, error) -> ...)` | Callback observes the result | Callback observes the error | **Observe/record side effects**, usually preserving the outcome |

`handle` can return a new type `U`, which is useful when you want to turn an error into a report object or a stateful result:

```java
CompletableFuture<String> labeled = source.handle((value, error) -> {
    if (error != null) {
        return "FAILED";
    }
    return "VALUE=" + value;
});
```

This is an illustrative snippet assuming `source` is a `CompletableFuture<Integer>`. The result `labeled` has type `CompletableFuture<String>`, whereas `exceptionally` keeps the same value type as the source.

`whenComplete` is commonly used for logging:

```java
CompletableFuture<Integer> observed =
        source.whenComplete((value, error) -> {
            if (error != null) {
                logFailure(error);
            }
        });
```

This is an illustrative snippet, with `logFailure` defined by the application. If the source failed and the `whenComplete` callback completes normally, `observed` **remains failed**; it does not turn the error into a fallback value. If the callback also throws an exception, error precedence follows the contract of `whenComplete`; do not use a logging callback that can throw carelessly.

If you want to both record the error and return a fallback, you can chain them in order:

```java
CompletableFuture<Integer> safe = source
        .whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        })
        .exceptionally(error -> 0);
```

The symbols `source` and `recordFailure` must be declared elsewhere. This approach is reasonable when logging does not alter the error definition or when logging failures are already handled appropriately.

## 7. Java 17 Example: Comparing the Three Operations with Deterministic Results

Create `RecoveryMethodsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class RecoveryMethodsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("unavailable"));

        CompletableFuture<Integer> observed =
                failed.whenComplete((value, error) -> {
                    System.out.println("whenComplete observed: " + (error != null));
                });

        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> 10);

        CompletableFuture<String> mapped =
                failed.handle((value, error) ->
                        error == null ? "OK=" + value : "FAILED");

        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("observed still failed");
        }

        System.out.println("exceptionally: " + recovered.join());
        System.out.println("handle: " + mapped.join());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 RecoveryMethodsDemo.java
java RecoveryMethodsDemo
```

Stdout:

```text
whenComplete observed: true
observed still failed
exceptionally: 10
handle: FAILED
```

Why is this right?

- `failed` has completed exceptionally, so `whenComplete` is invoked and prints `true`.
- `observed.join()` still throws `CompletionException` because `whenComplete` does not replace the failure outcome when the callback completes normally.
- `exceptionally` turns the error into `Integer 10`.
- `handle` produces `String "FAILED"`, demonstrating the ability to change types.
- `failedFuture` is used to eliminate executor scheduling effects and make the output easy to verify.

You do not need to use all three together in every pipeline. Choose according to your goal: **error recovery**, **two-branch transformation**, or **observation while preserving the outcome**.

## 8. The Position of exceptionally Determines the Recoverable Error Scope

Consider two chains:

**Recover first, then transform:**

```java
CompletableFuture<Integer> value = upstream
        .exceptionally(error -> 0)
        .thenApply(x -> 100 / x);
```

If `upstream` fails, `exceptionally` returns `0`. The subsequent `thenApply` stage throws `ArithmeticException` due to division by zero. The earlier `exceptionally` **does not go back to catch this new error**. The resulting chain remains exceptional.

**Transform first, then recover:**

```java
CompletableFuture<Integer> value = upstream
        .thenApply(x -> 100 / x)
        .exceptionally(error -> 0);
```

Here `exceptionally` is placed **after** the division; it can return `0` when `upstream` fails or when `thenApply` throws. However, catching this broadly can hide programming bugs, so you should classify the cause to avoid turning division by zero into a business-invalid valid result.

These two snippets only illustrate structure, assuming `upstream` has type `CompletableFuture<Integer>`. The key takeaway: place recovery at **the boundary where you want to turn an error into a result**, and avoid covering more stages than your policy allows.

### When a Stage Succeeds, exceptionally Does Not Run

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(5)
                .thenApply(x -> x * 2)
                .exceptionally(error -> -1);

// result.join() == 10, the recovery function is not called.
```

`exceptionally` is not meant for normalizing success values. For success values, use `thenApply`; for both branches, use `handle`.

## 9. What If the Recovery Function Itself Throws an Exception?

`exceptionally` is an **application function**, so it can fail as well. If the recovery callback throws an exception, the new stage completes exceptionally; there is no fallback value. This is normal and can be used to **decline recovery** for errors outside your policy.

Create `RecoveryFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class RecoveryFailureDemo {

    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("upstream failed"));

        CompletableFuture<Integer> recovered = source.exceptionally(error -> {
            throw new IllegalArgumentException("fallback failed", error);
        });

        try {
            recovered.join();
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            System.out.println(cause.getClass().getSimpleName());
            System.out.println(cause.getMessage());
            System.out.println(cause.getCause().getClass().getSimpleName());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 RecoveryFailureDemo.java
java RecoveryFailureDemo
```

Stdout:

```text
IllegalArgumentException
fallback failed
IllegalStateException
```

`recovered` fails with `IllegalArgumentException("fallback failed")`, while the original error is preserved as the `cause`. When `join()` is called, the stage's exception surfaces through `CompletionException`. The printing code here calls `getCause()` to obtain the application error, and then calls `getCause()` again to inspect the upstream error.

A realistic example is when a fallback cache also fails. If returning fallback data fails, you should propagate a new contextual error while preserving the relevant cause so the system can distinguish the error source; do not default to printing the error and returning `null` to continue as if it succeeded.

## 10. Fallback Values Must Be Business-Meaningful

Not every `T` has a safe fallback value.

Examples:

| Task type | Potentially reasonable fallback | Fallback likely to cause business bugs |
| --- | --- | --- |
| Fetching optional UI configuration | A vetted default configuration | An object missing required fields |
| Non-essential product recommendations | An empty list, while recording that the recommendation service is unavailable | A fake list presented as accurate personalized results |
| Fetching dashboard metric values | A fallback value labeled `stale` | Turning every failed metric into `0`, making readers think there is no activity |
| Reading a report from cache | Cached data still within an acceptable threshold | Overly stale data treated as fresh data |
| Processing payments or financial transactions | Usually requires a structured failed/pending result | Returning `true` or `SUCCESS` when the transaction has not actually been verified |
| Login/authorization | Usually fails safe and reports an appropriate error | Granting access when the authentication system is unavailable |

`exceptionally(error -> null)` is allowed when `T` is a reference type. In that case, the recovery future **completes normally with `null`**, but downstream stages may throw `NullPointerException`. `null` is only a valid fallback if the contract explicitly states it and all consumers know how to handle it.

For collections, `List.of()` can be a good fallback when "no recommendations" is an acceptable meaning. If "no data" is different from "the recommendation service is down", use a result type that represents both states or includes metadata; returning an empty list loses the failure signal and can lead to wrong decisions.

### Recovery Is Not Retry

`exceptionally` **does not automatically re-invoke the failed supplier or I/O operation**. The callback only runs when the source stage completes exceptionally and receives the `Throwable` to compute a fallback. If the business logic requires retries, you must explicitly design the retry schedule, attempt count, backoff, timeout, and idempotency.

Do not write:

```java
return serviceCall()
        .exceptionally(error -> serviceCall().join());
```

This snippet illustrates a **problematic** pattern: `serviceCall` is assumed to return `CompletableFuture<T>`. Calling `join()` inside the handler can block the thread running the callback, starving the executor or causing a deadlock in configurations with too few workers. It can also repeat side effects if the first call partially processed.

A proper async retry strategy typically uses composition (`thenCompose`/`exceptionallyCompose` when appropriate for the JDK and contract), bounded attempts, deadlines, and per-attempt monitoring. If you only want an **already-available fallback value**, `exceptionally` is the cleaner choice.

## 11. Does exceptionally Run on a Separate Thread?

Do not assume the lambda in `exceptionally` always runs asynchronously or always runs on a separate pool.

When the source stage has already completed before registration, the dependent stage may be processed immediately on the calling thread. When the source completes later, the callback may run on the thread performing the completion or according to the implementation's execution mechanism.

Therefore:

- Do not use non-async `exceptionally` to perform a long blocking network read or a large database query.
- Do not assume the callback is always allowed to access the caller's UI thread, request context, or thread-local state.
- If recovery is genuinely an asynchronous task, choose an appropriate async recovery/composition API (such as `exceptionallyCompose` and async variants in supporting JDKs) with a clearly managed executor.
- For an already-completed source stage, the callback may run before the line of code immediately after `exceptionally` executes; do not rely on callback timing for business logic.

`CompletableFuture` on Java 17 provides appropriate async recovery methods in the `exceptionallyAsync`/`exceptionallyCompose` family. Even so, choosing an executor must be based on workload characteristics (CPU/I/O), timeout policy, and executor lifecycle. Creating an unbounded executor for every recovery is poor design.

### Example on Logging and Context

`ThreadLocal` may not hold the expected value when the callback runs on another thread. If you need to log a correlation ID, tenant, or request ID, pass the needed values as immutable data into the closure or use a managed context propagation mechanism; avoid implicitly reading the entire context from another thread and assuming it belongs to the original request.

## 12. exceptionally and Cancellation

A cancelled `CompletableFuture` is considered completed exceptionally; therefore `exceptionally` can observe a `CancellationException` and **return a fallback**:

```java
CompletableFuture<String> original = new CompletableFuture<>();
original.cancel(false);

CompletableFuture<String> fallback =
        original.exceptionally(error -> "cancelled-fallback");
```

This is a snippet with the appropriate `CompletableFuture` import. `original` remains cancelled, but `fallback` can complete normally with `"cancelled-fallback"`. This is valid per the API, though it may **conflict** with the caller's intent to stop.

If cancellation is a signal that must be preserved, classify it explicitly:

```java
CompletableFuture<String> safe = original.exceptionally(error -> {
    if (error instanceof CancellationException) {
        throw (CancellationException) error;
    }
    return "fallback";
});
```

This is an illustrative snippet; it requires importing `CancellationException` and declaring `original`. In a stage chain where a `CompletionException` may wrap the cause, actual cancellation classification must match the error shape at the boundary.

Do not automatically turn every cancellation into success data when an orchestration layer relies on the cancelled state to halt a workflow. Conversely, if the UI only wants a "cancelled" message for an optional operation, representing it as an explicit domain result may be better than a fallback string easily confused with real data.

Keep in mind that `CompletableFuture.cancel(true)` does not mean an underlying worker is guaranteed to be interrupted in the way `FutureTask.cancel(true)` can request. Future cancellation and actual task termination are two separate responsibilities to consider.

## 13. Timeouts and Error Sources

There are two "timeout" scenarios that are easily confused:

1. `future.get(timeout, unit)` can throw `TimeoutException` **directly on the waiting thread** because the caller does not want to wait any longer. This **does not cause an exceptional completion** on `future`, so `future.exceptionally(...)` does not run just because a `get(timeout)` call expired.
2. `future.orTimeout(timeout, unit)` arranges for the `CompletableFuture` itself to complete exceptionally with `TimeoutException` if it has not completed by the deadline. In that case, an `exceptionally` attached after `orTimeout` can run and return a fallback.

Note that `orTimeout` **mutates the CompletableFuture itself** on which it is called, rather than creating an independent source; if the future is shared by multiple consumers, a deadline set by one consumer can affect others.

An example illustrating the chain:

```java
CompletableFuture<String> safe = fetchRemote()
        .orTimeout(2, TimeUnit.SECONDS)
        .exceptionally(error -> "temporarily-unavailable");
```

This is a non-standalone snippet, assuming `fetchRemote()` returns `CompletableFuture<String>` and requiring `TimeUnit` to be imported. It applies the fallback to **every** exceptional completion, not just timeouts. If you need a fallback specific to timeouts, classify the error before returning the fallback value.

`orTimeout` completes the future exceptionally, but **does not guarantee stopping the background work** that is running. If the task has side effects, the fallback value is only the outcome observed at the CompletableFuture layer, not a guarantee that the external operation has not been performed.

## 14. When Should You Use exceptionallyCompose?

`exceptionally` expects the callback to return **a value `T`**. If your fallback is another **asynchronous task** (for example, reading from a remote cache), a function of type `Throwable -> CompletableFuture<T>` does not directly match the `Throwable -> T` requirement.

`exceptionallyCompose` (available in Java 17) is designed for recovery with another stage, with the conceptual signature:

```java
CompletableFuture<T> recovered =
        primary.exceptionallyCompose(error -> fallbackAsync());
```

This is an illustrative snippet assuming `primary` has type `CompletableFuture<T>` and `fallbackAsync()` returns a compatible `CompletionStage<T>`. The method creates a stage whose outcome follows the stage returned by the callback without needing a blocking `join()` call.

Comparison:

- `exceptionally(error -> cachedValue)`: an **already-available fallback value**, fast to compute.
- `exceptionallyCompose(error -> fetchFromBackup())`: needs an **asynchronous fallback task** and awaits it via composition.
- `exceptionally(error -> fetchFromBackup().join())`: can **block** a thread and undermine the benefits of an async pipeline.

If the upstream stage succeeds, the recovery methods do not need to invoke the fallback. If the async fallback itself fails, the resulting stage remains exceptional; it does not become successful merely because a recovery handler was attached.

The choice also depends on whether the API wants to genuinely retry the same operation or switch to another service. Even when using composition, bounding retry loops and controlling side effects remain critical.

## 15. Combining with thenApply, thenCompose, and Result Branches

A typical pipeline:

```java
CompletableFuture<String> display = fetchUserId()
        .thenCompose(id -> fetchUserName(id))
        .thenApply(name -> name.trim())
        .exceptionally(error -> "Khách");
```

This is an illustrative snippet, with `fetchUserId()`/`fetchUserName(...)` assumed to have compatible types and declared in the application. `exceptionally` can turn an error in any stage **before it** into the string `"Khách"`.

However, if this chain is used for activity auditing or identity verification, a `"Khách"` fallback may violate business rules. Place recovery at a boundary whose contract permits a fallback result, such as displaying an optional UI nickname.

After recovery, subsequent stages treat `"Khách"` as a normal success result. If you want to distinguish between a "real value" and a "fallback value", preserve metadata:

```java
record DisplayName(String text, boolean fallback) {}

CompletableFuture<DisplayName> value =
        fetchName().thenApply(name -> new DisplayName(name, false))
                .exceptionally(error -> new DisplayName("Khách", true));
```

This is an illustrative snippet, assuming `fetchName()` returns `CompletableFuture<String>`. `record` has been supported since Java 16, so it fits Java 17. Calling code can read `fallback()` to know the content was substituted due to an error, instead of guessing from the string `"Khách"`.

## 16. Two Different Errors: Upstream Failure and Recovery Failure

When recovery also fails, good diagnostics require preserving two pieces of information:

- **Upstream failure:** the original reason recovery was needed.
- **Recovery failure:** the reason the fallback value could not be produced.

In the `RecoveryFailureDemo` example, `IllegalArgumentException("fallback failed", error)` preserves the upstream exception as the cause. However, if an async fallback fails in another stage, depending on your API you may need to construct a domain exception with the appropriate cause and correlation information.

Avoid accidentally **double-logging** the same exception at every stage; log at a single observation boundary with clear ownership and add context only if genuinely needed. If recovery turns an error into a normal result, consumers of the new stage will not automatically see the old exception. If you want to track the fallback usage rate, the recovery callback can record a metric/counter, but a metric system failure should not break recovery unless policy requires it.

Security also matters: `Throwable.getMessage()` from HTTP/SQL/SDK layers may contain internal URLs, tokens, or sensitive data. Do not concatenate vendor messages directly into fallback results returned to clients; use messages and error types controlled by your API.

## 17. Testing Recovery Behavior Properly

Testing `exceptionally` should cover the success path, recoverable failure paths, non-recoverable failures, and failures of the fallback itself.

| Case | Expectation |
| --- | --- |
| Upstream succeeds with `10` | The lambda in `exceptionally` **does not run**; the new stage receives `10`. |
| Upstream fails with an error eligible for fallback | The callback runs once for the corresponding dependent stage; the new stage returns a valid fallback. |
| Upstream fails with an error that must propagate | The callback classifies and rethrows/wraps the error; the new stage remains exceptional. |
| Recovery callback throws an exception itself | The recovery stage is exceptional, and the cause should be preserved for diagnostics. |
| Recovery returns `null` for a reference type | The stage completes normally with `null`; downstream must handle it per contract. |
| Upstream is cancelled | The callback can receive an exceptional completion; do not accidentally clear the workflow's cancellation state when policy requires it. |
| Error occurs in `thenApply` **after** recovery | The earlier `exceptionally` **does not catch** errors from subsequent stages. |
| Error occurs in `thenApply` **before** recovery | The later `exceptionally` can handle that error. |
| `get(timeout)` merely expires while waiting | The source future does not become exceptional just because the caller timed out; it does not trigger recovery. |
| `orTimeout` completes exceptionally | A subsequent `exceptionally` can run and return a fallback. |

For small tests, use `completedFuture`/`failedFuture` to reduce dependency on scheduling. For tests that need to prove a pipeline is genuinely async, use `CountDownLatch` to control ordering instead of relying on `Thread.sleep` to guess timing.

A testing anti-pattern is asserting only `recovered.join() == fallback` and ignoring the source's state. You should also check `source.isCompletedExceptionally()` when you want to verify that recovery **did not mutate the original error**, and verify that stages placed after recovery receive the expected result.

## 18. Common Mistakes and How to Fix Them

**1. Assuming `exceptionally` runs on the success path too.** It only invokes the callback when the upstream stage completes exceptionally. Use `handle` if you must transform both success and failure.

**2. Assuming `exceptionally` only logs while preserving the error.** If the callback returns a value, the new stage completes normally. Use `whenComplete` when the goal is only observation; if you want to log and remain failed, make that choice explicit.

**3. Returning a fallback for every `Throwable`.** This can hide bugs, security errors, data corruption, and severe incidents. Classify the cause and recover only in permitted cases.

**4. Ignoring the `CompletionException` wrapper.** The exception type received by the handler may differ from the type thrown directly by the previous stage. Unwrap in a controlled manner and rely on a stable error contract.

**5. Placing `exceptionally` too early.** It does not recover from errors occurring in stages chained after it. Place recovery at the right boundary.

**6. Placing `exceptionally` too late and catching bugs as well.** A broad fallback at the end of a pipeline can hide errors from unrelated steps. Choose the placement and classification rules carefully.

**7. Using `join()` to call an async fallback task inside the lambda.** This easily blocks an important thread; use async composition when the fallback takes time.

**8. Using `null` or `0` as if it were always real data.** Callers may misinterpret it. Return a result with metadata or a fallback flag if that distinction matters.

**9. Thinking recovery mutates the source future.** It does not: the new stage can succeed while the source remains exceptional.

**10. Treating a `get(timeout)` timeout as an upstream failure.** A waiter timeout does not complete the future exceptionally. Distinguish it from `orTimeout`.

**11. Recovering from cancellation against the workflow's intent.** If the system needs to cancel, turning it into a "success" result can cause tasks to continue unexpectedly.

**12. Assuming the callback always runs on an executor.** Non-async continuations may run on the thread completing the future or the thread attaching the callback; avoid blocking and thread-local dependencies.

**13. Not testing when the fallback itself fails.** The recovery callback can throw an exception, leaving the new stage exceptional. Test and monitor this branch.

## 19. Self-Check Exercises

**Question 1:** What does `CompletableFuture.completedFuture(5).exceptionally(error -> 0).join()` return? Does the recovery lambda run?

**Answer:** It returns `5`; the lambda does not run because the upstream stage succeeded.

**Question 2:** A future has failed with `IllegalStateException`. After `exceptionally(error -> 10)`, how do the states of the original future and the returned future differ?

**Answer:** The original future remains completed exceptionally, whereas the new stage succeeds with the value `10` if the callback does not throw an exception.

**Question 3:** Does `upstream.exceptionally(error -> 0).thenApply(x -> 10 / x)` guarantee success when `upstream` fails?

**Answer:** No. Recovery returns `0`, and the subsequent `thenApply` stage can throw `ArithmeticException`. The earlier `exceptionally` does not recover from the new error.

**Question 4:** If you want to both inspect the error and preserve the exceptional completion, should you choose `whenComplete` or `exceptionally`?

**Answer:** Usually choose `whenComplete` with a non-throwing observation callback. `exceptionally` returning a fallback turns the failure branch into a normal value.

**Question 5:** When the fallback is another `CompletableFuture<T>`, should you write `exceptionally(error -> backup().join())`?

**Answer:** Prefer `exceptionallyCompose(error -> backup())` to compose the asynchronous stage without blocking the current thread, while also designing timeouts and task ownership.

**Question 6:** A caller calls `future.get(100, MILLISECONDS)` and gets a `TimeoutException`. Does an `exceptionally` attached to that future run automatically?

**Answer:** Not merely because the `get` call expired. `get(timeout)` limits a single wait and does not mutate the future's state.

**Question 7:** If a `CompletableFuture` is cancelled, should `CancellationException` automatically be turned into the string `"OK"`?

**Answer:** Only if the product contract intentionally treats cancellation as such a normal result. If the workflow uses cancellation to request stopping, `"OK"` can hide an important signal.

## 20. Checklist When Choosing exceptionally

Before adding `exceptionally` to a pipeline, ask yourself:

1. **Which stages can fail?** Is the handler placed right after the exact stages that need recovery?
2. **Which errors are allowed to become results?** Can you distinguish expected errors from bugs or cancellation?
3. **Is the fallback business-meaningful?** Could `0`, `null`, an empty list, or a default message mislead callers?
4. **Is the fallback an already-available value or an async task?** If it is async, use composition to avoid blocking.
5. **Can the callback throw an error?** When it fails, is the cause preserved and the state monitored?
6. **Are other consumers observing the original future?** Recovery creates a new stage; it does not erase the source's error.
7. **Do you have policies for cancellation, timeout, retry, and idempotency?** Recovery does not automatically stop background work and does not automatically retry failed work.
8. **Do you need to observe the fallback rate?** Record fallback usage at an appropriate boundary and avoid duplicate logging.
9. **Have you tested success, failure, and failure inside recovery?** Do not test only a single happy path.

`exceptionally` is a clear way to express: **"if the previous step fails under a recoverable condition, use a replacement value of the same type and continue"**. Using it at the right boundary, with a meaningful fallback and clear error classification, helps asynchronous programs maintain a consistent contract while preserving visibility into genuine failures.

# Comparing Error Recovery with `exceptionally`, `handle`, and `whenComplete` in Java

A `CompletableFuture` can complete **normally** with a value or **exceptionally** (*exceptional completion*) due to an error. When building asynchronous pipelines, the three methods `exceptionally`, `handle`, and `whenComplete` often appear side by side. All three allow reacting to errors, but **they do not serve the same purpose**:

- **`exceptionally`**: runs only when the previous stage fails; can **recover with a value** of the same result type.
- **`handle`**: runs when the previous stage succeeds **or** fails; can **transform both cases into a new result**, even of a different type.
- **`whenComplete`**: runs when the previous stage succeeds **or** fails to **observe/record**; normally preserves the result or error of the previous stage, and is not an API for producing a fallback value.

The most common mistake is writing `whenComplete((value, error) -> logger.error(...))` and assuming the error has been handled. **Logging does not mean recovering.** If the previous stage failed, the stage after `whenComplete` will normally still be failed, and `join()`/`get()` will still report a failure.

This practice guide uses Java 17+, with standalone compilable and runnable programs, to distinguish state propagation, fallback values, callbacks that throw exceptions themselves, and the impact on multi-step pipelines.

## 1. Model: a stage completes along one of two branches

A `CompletableFuture<T>` represents a completed result:

```text
CompletableFuture<T>
       |
       +-- Success -------------------> value: T
       |                                  |
       |                         thenApply / thenAccept
       |
       +-- Failure -------------------> error: Throwable
                                          |
                          exceptionally / handle / whenComplete
```

Do not use `isDone() == true` to conclude that work succeeded: a future that completed due to an error or cancellation is also considered done. When diagnosing failures, `join()` may throw `CompletionException` wrapping the cause; `get()` may throw `ExecutionException`. A directly cancelled future may throw `CancellationException`.

Suppose:

```java
CompletableFuture<Integer> success =
        CompletableFuture.completedFuture(7);
CompletableFuture<Integer> failure =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad input"));
```

These are two illustrative statements within a scope that has `import java.util.concurrent.CompletableFuture;`. `completedFuture` and `failedFuture` have been available since Java 9; on Java 17 they work out of the box. When invoking the callbacks below, there is no need to simulate threads or wait for network tasks: both futures already have a final state, giving the practice examples deterministic results.

**The source stage and the new stage are two distinct objects** for the methods in this guide. For example, `CompletableFuture<Integer> recovered = failure.exceptionally(e -> -1)` does not mutate the error state of `failure`; it creates a new dependent stage that can complete normally. Do not mistake recovery in a downstream stage for the original task having succeeded.

## 2. Exact comparison table of the three methods

| Criterion | `exceptionally` | `handle` | `whenComplete` |
| --- | --- | --- | --- |
| Runs when previous stage succeeds? | **No** | **Yes** | **Yes** |
| Runs when previous stage fails? | **Yes** | **Yes** | **Yes** |
| Data received by callback | `Throwable error` | `T value`, `Throwable error` | `T value`, `Throwable error` |
| What does callback return? | Replacement `T` value | New value of type `U` | `void` |
| Can turn failure into success? | **Yes**, when callback returns normally | **Yes**, when callback returns normally | **Not by returning a value** |
| When callback succeeds and source failed | New stage receives fallback | New stage receives handled value | New stage still propagates original error |
| When callback itself throws | New stage fails with callback's error | New stage fails with callback's error | If source succeeded: callback's error fails the new stage; if source already failed: source error takes precedence |
| Changes result type from `T` to `U`? | No (same `T`) | Yes | No (keeps `T`) |
| Typical purpose | Error recovery via fallback | Unifying success/failure into one result type | Logging, metrics, cleanup/observation |
| Returned object | New stage | New stage | New stage |

**Note on errors in `whenComplete`:** per the `CompletionStage` contract, if the callback itself throws an error, the returned stage completes exceptionally with the callback's exception **unless the source stage already completed exceptionally**. In the case where both fail, the source error still determines the state of the returned stage. Do not rely on the callback's error automatically being added to `getSuppressed()` of the source error; that is not an API guarantee.

## 3. Signatures and meaning of return values

The signatures below omit some generic details:

```java
CompletableFuture<T> exceptionally(
        Function<Throwable, ? extends T> fn);

<U> CompletableFuture<U> handle(
        BiFunction<? super T, Throwable, ? extends U> fn);

CompletableFuture<T> whenComplete(
        BiConsumer<? super T, ? super Throwable> action);
```

These are **API descriptions**, not a standalone Java program; the actual signatures use types in `java.util.function`.

- `exceptionally` takes a `Function` from an error to a `T` value. When the source succeeds, this callback does not run, and the success value passes through to the new stage.
- `handle` takes a `BiFunction`: for normal completion, `error == null`; for failure, `value` is usually `null`. It returns a value of type `U`, allowing you to convert `CompletableFuture<Integer>` into `CompletableFuture<String>` or a labeled result type.
- `whenComplete` takes a `BiConsumer`: it performs an action and **has no return value** to replace the stage's result. Even if the callback successfully logs or records metrics, the source error must still be handled at another boundary if the application needs recovery.

Be careful with `null`: a `CompletableFuture<String>` **can complete successfully with `null`**. Therefore, do not use `value == null` as the sole criterion for determining failure in `handle` or `whenComplete`. Use `error != null` to distinguish the error branch according to the callback contract.

## 4. Runnable example 1: same source, three handling approaches

Create **`RecoveryMethodsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class RecoveryMethodsDemo {
    static Throwable unwrap(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> failure =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad input"));

        int successExceptionally =
                success.exceptionally(error -> -1).join();
        System.out.println("success.exceptionally=" + successExceptionally);

        int successHandle = success.handle(
                (value, error) -> error == null ? value * 2 : -2).join();
        System.out.println("success.handle=" + successHandle);

        int successObserved = success.whenComplete(
                (value, error) -> {}).join();
        System.out.println("success.whenComplete=" + successObserved);

        CompletableFuture<Integer> recovered = failure.exceptionally(
                error -> {
                    System.out.println("exceptionally.error="
                            + unwrap(error).getClass().getSimpleName());
                    return -1;
                });
        System.out.println("failure.exceptionally=" + recovered.join());

        int failureHandled = failure.handle((value, error) -> {
            System.out.println("handle.hasError=" + (error != null));
            return error == null ? value * 2 : -2;
        }).join();
        System.out.println("failure.handle=" + failureHandled);

        CompletableFuture<Integer> observed = failure.whenComplete(
                (value, error) -> System.out.println(
                        "whenComplete.error="
                                + unwrap(error).getClass().getSimpleName()));

        try {
            observed.join();
        } catch (CompletionException error) {
            System.out.println("failure.whenComplete.root="
                    + unwrap(error).getClass().getSimpleName());
        }

        System.out.println("source.exceptional="
                + failure.isCompletedExceptionally());
        System.out.println("recovered.exceptional="
                + recovered.isCompletedExceptionally());
    }
}
```

Compile/run with Java 17:

```bash
javac --release 17 RecoveryMethodsDemo.java
java RecoveryMethodsDemo
```

Output:

```text
success.exceptionally=7
success.handle=14
success.whenComplete=7
exceptionally.error=IllegalArgumentException
failure.exceptionally=-1
handle.hasError=true
failure.handle=-2
whenComplete.error=IllegalArgumentException
failure.whenComplete.root=IllegalArgumentException
source.exceptional=true
recovered.exceptional=false
```

**Explanation of each branch:**

1. `success` completed normally with `7`. The `exceptionally` callback **did not run**, so the value remains `7`.
2. `handle` ran in the success case, multiplied `7` to `14`, and produced a new result.
3. `whenComplete` on the success branch did not alter `7` when the action did not throw.
4. `failure` completed exceptionally with `IllegalArgumentException`. `exceptionally` received the error, printed the error type, and returned `-1`; the `recovered` stage completed **normally** with `-1`.
5. `handle` also saw the error and returned `-2`; this is **a different recovery stage**, which does not interfere with the `recovered` stage.
6. `whenComplete` observed the error and printed its type without producing a fallback. When `observed.join()` was called, the stage remained failed and the meaningful cause was `IllegalArgumentException`.
7. The source `failure.isCompletedExceptionally()` remains `true`, whereas `recovered.isCompletedExceptionally()` is `false`. Recovering in a dependent stage **does not erase the failure history** of the source stage.

The example uses already-completed futures so stdout ordering is easy to verify; do not rely on callback ordering when attaching them to truly concurrent tasks without coordination.

## 5. `exceptionally`: recovering only the error path

An application displaying a username might allow a cached replacement when the profile service is temporarily unavailable:

```java
CompletableFuture<String> displayName =
        loadProfileNameAsync().exceptionally(error -> "Tên tạm thời");
```

This is **illustrative code**, requiring `loadProfileNameAsync()` to return `CompletableFuture<String>`. If the source succeeds, the callback does not run and the real name is preserved. If the source fails, the callback is invoked and returns the fallback `"Tên tạm thời"`.

**Note:** the pattern above recovers from **every** error. In a real application, you should classify errors if you do not want a `NullPointerException` from a bug, an authorization error, or a configuration error to be silently turned into a normal fallback.

Example filtering specifically for timeout on an existing `CompletableFuture<String> source`:

```java
CompletableFuture<String> maybeCached = source.exceptionally(error -> {
    Throwable current = error;
    while (current instanceof CompletionException
            && current.getCause() != null) {
        current = current.getCause();
    }

    if (current instanceof java.util.concurrent.TimeoutException) {
        return "CACHED";
    }
    throw new CompletionException(current);
});
```

This is an **illustrative snippet in a program with `source` and appropriate imports**. If the error is a timeout, the new stage receives the fallback. Otherwise, the callback rethrows a `CompletionException` to continue signaling failure. Re-wrapping creates an extra error path; a production implementation may choose to forward the error while preserving the cause in line with its logging contract, rather than necessarily adding a wrapper for every error.

### When `exceptionally` is not appropriate

- If you need to transform both the success value and the error into a different result type, use `handle`.
- If you only want to log **without** turning the error into a success, use `whenComplete`.
- If a fallback is not genuinely valid for the operation (for example, "payment succeeded"), do not recover with a fake value.
- If the caller needs to know that a fallback occurred, return an informative result type such as `Result<T>` or a record, instead of silently converting the error into an indistinguishable value.

`exceptionally` does not **retry** the failed operation. It is a **mapping from an error result to a value**. If you want to retry asynchronously, you need a bounded retry mechanism or an appropriate stage-composing API (`exceptionallyCompose` on supported JDKs), along with a safe retry policy.

## 6. `handle`: unifying success/failure and changing types

`handle` is suitable when the calling layer does not want to receive an unchecked exception, but rather a **structured** result that distinguishes success from failure:

```java
record Outcome<T>(T value, String errorCode) {
    boolean succeeded() {
        return errorCode == null;
    }
}

CompletableFuture<Outcome<Integer>> outcome =
        source.handle((value, error) -> {
            if (error != null) {
                return new Outcome<Integer>(null, "SERVICE_UNAVAILABLE");
            }
            return new Outcome<Integer>(value, null);
        });
```

This is an **illustrative code snippet**, requiring the record to be placed in a valid Java type declaration position and a `CompletableFuture<Integer> source` to exist. `Outcome` is an example result type; in a real API, avoid allowing contradictory states (neither value nor error, or both present) and consider sealed types if a stricter contract is needed.

The key feature is that `handle` returns `U`: the source stage is of type `Integer`, while the new stage is of type `Outcome<Integer>`. It still runs if the source stage succeeds, making it well suited for normalizing results into a common structure.

### Do not accidentally mask bugs

If a callback simply writes:

```java
source.handle((value, error) -> error == null ? value : 0);
```

then every error is converted into `0`, including internal logic bugs. Only use this when `0` is a contractually permitted fallback value and cannot be mistaken for a real result. For unrecoverable errors, `handle` can throw an appropriate exception so the new stage continues to complete exceptionally.

### `null` does not necessarily mean failure

If the source is `CompletableFuture.completedFuture(null)`, a `handle((value, error) -> ...)` can receive both `value == null` **and** `error == null`. That is still a successful completion. Do not handle it with `if (value == null) { fallback; }` if `null` is a contractually allowed value.

## 7. `whenComplete`: observing without changing the result

A common pattern for boundary logging:

```java
CompletableFuture<Order> observed =
        source.whenComplete((order, error) -> {
            if (error != null) {
                logger.error("Order computation failed", error);
            }
        });
```

This is an **illustrative code snippet** requiring type `Order`, `source` of type `CompletableFuture<Order>`, and `logger` (such as SLF4J). Passing the `Throwable` object to the logger allows the formatter to record the stack trace and cause, rather than logging only `error.getMessage()`.

When the source succeeds and the action does not throw, `observed` receives the same value. When the source fails and the action does not throw, `observed` still completes exceptionally. **Seeing the exception in the callback does not automatically mean it has been consumed.**

Another use case is recording metrics:

```java
CompletableFuture<String> monitored =
        source.whenComplete((value, error) -> {
            if (error == null) {
                metrics.recordSuccess();
            } else {
                metrics.recordFailure();
            }
        });
```

This is also an illustrative snippet requiring `source` and `metrics`. If the metric operation itself throws an exception when the source succeeded, the new stage can transition from success to failure. Therefore, observation callbacks should be **lightweight, reliable, and free of business-logic side effects**.

### `whenComplete` is not an absolute `finally`

It acts like an end-of-stage observation hook, but it is not a full equivalent of a synchronous `finally` block's semantics:

- It runs when the source stage **completes**; if the stage never completes, the callback may never run either.
- It does not automatically close resources belonging to a running supplier; a `CompletableFuture` completed by timeout or cancellation does not guarantee that the physical work has stopped.
- It does not replace `try-with-resources` where resources are opened.
- The callback may run on different threads depending on how completion happens and whether `Async` variants are used; do not use it assuming a thread-local context is preserved.

Use `whenComplete` to observe and emit metrics/logs at appropriate boundaries, not as a place to perform unsafe cleanup of worker resources.

## 8. Callback throws an error itself: how does behavior differ?

Callbacks themselves can fail due to programming bugs or internal side operations. Do not treat `exceptionally`, `handle`, or `whenComplete` as "unbreakable barriers."

- With `exceptionally`: if the recovery function throws, the new stage completes exceptionally. A failed recovery does not automatically become a fallback.
- With `handle`: if the function throws in either the success or failure branch, the new stage completes exceptionally with the function's error.
- With `whenComplete`: if the source **succeeded** and the action throws, the new stage fails due to the action. If the source **already failed** and the action also throws, the source error takes precedence per contract; do not assume there is an automatic suppressed list for the action's error.

To verify this, create **`CallbackFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CallbackFailureDemo {
    static String rootType(Throwable error) {
        Throwable current = error;
        while (current instanceof CompletionException
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> good =
                CompletableFuture.completedFuture(5);
        CompletableFuture<Integer> bad =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("origin failed"));

        try {
            good.whenComplete((value, error) -> {
                throw new IllegalStateException("observer failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("observerOnSuccess=" + rootType(error));
        }

        try {
            bad.whenComplete((value, error) -> {
                throw new IllegalStateException("observer failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("observerOnFailure=" + rootType(error));
        }

        try {
            bad.exceptionally(error -> {
                throw new IllegalStateException("recovery failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("failedRecovery=" + rootType(error));
        }

        try {
            good.handle((value, error) -> {
                throw new IllegalStateException("handler failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("failedHandle=" + rootType(error));
        }

        CompletableFuture<Integer> recovered =
                bad.exceptionally(error -> 100);
        System.out.println("recoveredThenApply="
                + recovered.thenApply(value -> value + 1).join());
        System.out.println("originalStillExceptional="
                + bad.isCompletedExceptionally());
    }
}
```

Run:

```bash
javac --release 17 CallbackFailureDemo.java
java CallbackFailureDemo
```

Output:

```text
observerOnSuccess=IllegalStateException
observerOnFailure=IllegalArgumentException
failedRecovery=IllegalStateException
failedHandle=IllegalStateException
recoveredThenApply=101
originalStillExceptional=true
```

In the first two lines, both `whenComplete` callbacks throw `IllegalStateException`; however, when the source had already failed, the new stage retains the `IllegalArgumentException` from the source. The third and fourth lines show that the recovery/handling callback itself can become a new source of failure. The last two lines remind us that a stage recovered with `exceptionally` allows `thenApply` to continue running, while **the original stage remains failed**.

This example uses already-completed futures to demonstrate deterministic semantics and output; in a real asynchronous pipeline, callback execution order cannot be inferred solely from attachment order.

## 9. Key difference between recovering and merely observing

Suppose `CompletableFuture<Integer> failed` has completed exceptionally.

```java
CompletableFuture<Integer> withFallback =
        failed.exceptionally(error -> 0);

CompletableFuture<Integer> handled =
        failed.handle((value, error) -> error == null ? value : 0);

CompletableFuture<Integer> observed =
        failed.whenComplete((value, error) -> logError(error));
```

This is an **illustrative snippet** requiring `failed` and `logError(Throwable)` to be declared. If all callbacks run normally, the first two stages **recover with `0`**, whereas the `observed` stage **continues to fail**. Do not write downstream code assuming `observed.join()` will return `0`.

A dependency diagram:

```text
                       failed (exceptional)
                        /       |         \
                       /        |          \
             exceptionally    handle     whenComplete
                   |             |             |
               result = 0    result = 0   still exceptional
                   |             |             |
                thenApply     thenApply      join() throws error
                  runs          runs
```

Understand "recovery" as **the new stage completing normally** when the callback returns a value. It does not repair data modified before the error occurred, does not roll back a DB transaction, does not stop an in-flight I/O task, and does not make the source stage succeed.

If callers need to know that the result is a fallback, include metadata in the result type—for example, `Outcome<T>` with a `REAL`/`FALLBACK` status—instead of returning only a number that could collide with a real success value.

## 10. Stage composition order changes error policy

The three methods are pipeline building blocks. **Placing them before or after a computation stage** can produce different results.

### Recover first, then transform

```java
CompletableFuture<Integer> result =
        failed.exceptionally(error -> 10)
              .thenApply(value -> value * 2);
```

This is an illustrative snippet with `CompletableFuture<Integer> failed`. If `failed` fails, the callback returns `10` and `thenApply` receives `10`, producing `20`. The subsequent computation step **does not know** `10` is a fallback unless the data type carries a distinguishing flag.

### Transform first, then recover

```java
CompletableFuture<Integer> result =
        source.thenApply(value -> transform(value))
              .exceptionally(error -> 10);
```

This snippet requires `source` and `transform(...)`. `exceptionally` placed after `thenApply` can recover from both errors in the **source** and errors thrown by `transform`. If the application only wants a fallback for source-read errors and **not** to mask programming bugs in the transformation step, you must adjust the placement or classify the error.

### Observe after recovering

```java
CompletableFuture<Integer> observed =
        failed.exceptionally(error -> 10)
              .whenComplete((value, error) -> {
                  System.out.println("error=" + error);
              });
```

This is an illustrative snippet. `whenComplete` sees the result of **the stage immediately preceding it**; if `exceptionally` already recovered, then `error == null`. To log the root cause, observe **before recovering**:

```java
CompletableFuture<Integer> observedAndRecovered =
        failed.whenComplete((value, error) -> {
                  if (error != null) {
                      report(error);
                  }
              })
              .exceptionally(error -> 10);
```

This snippet requires the application's `report(Throwable)` method. `whenComplete` preserves the error, so the downstream `exceptionally` still sees the error path to handle it. If `report` throws, you must understand `whenComplete`'s error rules and design reliable logging/metrics.

## 11. `CompletionException`, `ExecutionException`, and root cause

When a stage fails, the `Throwable` type seen by a callback may be the original exception or a technical wrapper created by the pipeline. Do not hard-code an assumption that `error.getClass()` is always the original business exception.

- `join()` may throw `CompletionException` (unchecked) with `getCause()` pointing to the underlying error.
- `get()` may throw `ExecutionException` (checked) with the failure cause.
- `whenComplete`, `handle`, and `exceptionally` receive a `Throwable` representing the failure state of **the input stage**. Depending on the path, one of those wrappers may appear.

Example unwrapping familiar technical wrappers:

```java
Throwable meaningful(Throwable error) {
    Throwable current = error;
    while ((current instanceof java.util.concurrent.CompletionException
            || current instanceof java.util.concurrent.ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

This is an **illustrative method inside a Java class**, not a standalone program. It skips two specific wrapper types to obtain the nearest meaningful exception, and does **not** automatically strip all business wrappers. If working with error data from untrusted or uncontrolled sources, a general-purpose utility should also account for unusual cause chains and depth limits to avoid unintended loops.

**Log the entire `Throwable`**, not just `getMessage()`, when you need the stack trace, cause, and suppressed exceptions. Taking only the deepest exception and discarding higher-level context can make it harder to locate where the error was translated.

## 12. Cancellation and timeout: do not silently turn errors into success

A cancelled or timed-out future can also reach error-handling callbacks:

- `CompletableFuture.cancel(...)` can complete a future in a cancelled state. When handling errors in a dependent stage, the callback may receive `CancellationException` or a wrapper of it depending on the path.
- `orTimeout(...)` completes a pending future **exceptionally** with `TimeoutException` if the deadline arrives first.
- `completeOnTimeout(fallback, ...)` completes a pending future **normally** with the fallback if the deadline arrives first; in that case, a downstream `exceptionally` will not be called because the stage succeeded.

Error-handling methods do not **stop the underlying work**. If a supplier is writing a file or calling a service, `exceptionally(error -> defaultValue)` does not cancel I/O, does not compensate side effects, and does not guarantee the supplier has finished. Do not use a "recovered future" as evidence that the original transaction completed successfully.

Return a fallback only when it is safe: a timeout on a display widget may safely use cached data, whereas a timeout on a payment transaction requires an explicit status and possibly reconciliation.

## 13. Synchronous vs. `Async` variants: where does the callback run?

The three APIs have asynchronous variants available across many JDK versions, including `handleAsync`, `whenCompleteAsync`, and `exceptionallyAsync` on Java 17. For the non-`Async` versions, dependent actions **may run on the thread that completes the stage or on another thread performing the completion operation**, with no guarantee that they always run on the same worker that ran the supplier.

Illustrative example:

```java
CompletableFuture<String> result =
        source.handleAsync((value, error) -> {
            return error == null ? value : "fallback";
        }, applicationExecutor);
```

This snippet requires `source` of type `CompletableFuture<String>` and `applicationExecutor` as an `Executor`. Providing an explicit executor lets you choose where the callback runs; you must still handle cases where the executor rejects scheduling or the application shuts down.

Do not perform long-blocking I/O or heavy CPU work inside a synchronous `whenComplete` just because it looks like a "logging callback." A slow callback can tie up the completing thread; if using asynchronous logging, define error correlation clearly and ensure diagnostic data is not lost.

Whether executed synchronously or asynchronously, the **recovery semantics** of the three API families follow the same contract: `exceptionally` can return a fallback on error, `handle` transforms both branches, and `whenComplete` primarily observes.

## 14. Test the recovery strategy, not just that the callback ran

For real systems, good tests must verify both the **source stage** and the **result-receiving stage**, while injecting failures at multiple points:

| Scenario | `exceptionally` | `handle` | `whenComplete` |
| --- | --- | --- | --- |
| Source succeeds with `7` | Recovery does not run; receives `7` | Callback runs, can yield `14` | Callback runs, still receives `7` |
| Source fails | Callback runs; can return fallback | Callback runs; can return fallback/`Outcome` | Observes error; downstream future normally still fails |
| Callback throws when source succeeds | Callback does not run | New stage fails | New stage fails |
| Callback throws when source already failed | New stage fails with callback's error | New stage fails with callback's error | Source error takes precedence |
| Source succeeds with `null` | No recovery | `error == null`, `value == null` is still success | Same, only observes |
| Fallback followed by `thenApply` | `thenApply` runs with fallback | `thenApply` runs if `handle` succeeds | `thenApply` runs only when observed stage still succeeds |
| Timeout/cancellation error | Must classify before fallback | Must classify before fallback | Observes and continues propagating error if it does not throw |

Tests should not assert only `isDone()` because failed/cancelled futures are also done. Check `join()`, `isCompletedExceptionally()`, cause type, fallback value, callback side effects, and recovery conditions. If an error is masked as a success, the test should catch it.

### JUnit 5 example for a failed source

This is an **illustrative test snippet**, requiring the JUnit Jupiter dependency and imports for `@Test` and `Assertions.*`:

```java
@Test
void exceptionallyRecoversButSourceStaysFailed() {
    CompletableFuture<Integer> source =
            CompletableFuture.failedFuture(
                    new IllegalArgumentException("bad input"));

    CompletableFuture<Integer> recovered =
            source.exceptionally(error -> -1);

    assertEquals(-1, recovered.join());
    assertFalse(recovered.isCompletedExceptionally());
    assertTrue(source.isCompletedExceptionally());
}

@Test
void whenCompleteDoesNotConsumeFailure() {
    CompletableFuture<Integer> source =
            CompletableFuture.failedFuture(
                    new IllegalArgumentException("bad input"));

    CompletableFuture<Integer> observed =
            source.whenComplete((value, error) -> {});

    CompletionException exception =
            assertThrows(CompletionException.class, observed::join);
    assertInstanceOf(IllegalArgumentException.class,
            exception.getCause());
}
```

The test snippet requires importing the concurrency classes; it does not run standalone with only the JDK. The first test verifies proper recovery without making the source succeed. The second test verifies that `whenComplete` **does not consume** the error.

### Testing callbacks that throw

Include test cases corresponding to `CallbackFailureDemo`:

- `whenComplete` throws while source succeeds → new observed stage fails.
- `whenComplete` throws while source already failed → source error is still the one reported by the downstream stage.
- `exceptionally` throws during recovery → new stage still fails.
- `handle` throws while handling → new stage still fails.
- Attaching `exceptionally` after `thenApply` → verify whether it accidentally masks transformation errors.

When a callback contains state-adjusting logic, also assert valid DB state/side effects/fallback values, not just the `Throwable` type.

## 15. Common mistakes and how to avoid them

| Misconception | Consequence | How to fix |
| --- | --- | --- |
| "`whenComplete` logged it, so the error is handled." | Downstream stage still fails, `join()` still throws | Use `exceptionally`/`handle` if recovery is actually needed |
| "`exceptionally` always runs after every stage." | Callback does not run on the success branch | Attach shared logic to `handle` or `whenComplete` |
| "`handle` only receives success values." | `error` is not handled properly | Always check `error != null`; `value` may be `null` |
| "`value == null` means error." | Misclassifies a source that succeeded with `null` | Use the `error` parameter to distinguish |
| "`whenComplete` never changes state." | A throwing callback can turn success into failure | Ensure observation callbacks are reliable |
| "A failing callback action always replaces the source error." | Misunderstands `whenComplete` precedence | If the source already failed, the source error takes precedence |
| "Recovering with a fallback clears the error on the original future." | Incorrect state monitoring | Distinguish the source stage from the dependent stage |
| "Using `exceptionally(e -> 0)` is safe for all errors." | Masks bugs, authorization errors, or invalid data | Classify errors; only fall back when contractually allowed |
| "`whenComplete` is where you can close all resources." | May close resources while the supplier is still running | Place cleanup within the resource-owning scope |
| "`isDone()` means the business operation succeeded." | Records false successes | Check completion status and postconditions |
| "Callbacks always run in attachment order." | Race conditions or unexpected log output | Use stage relationships and synchronization when needed |
| "`join()` returns the original error directly in all cases." | Catches the wrong exception and misses the cause | Account for `CompletionException`, `CancellationException`, and cause |
| "`get()` and `join()` are identical." | Misses checked exceptions on `get()` | Distinguish `ExecutionException` and `InterruptedException` |
| "A `handle` returning `null` is definitely an error." | Misinterprets a valid `null` value | It can complete normally with `null` |
| "A failing callback can be ignored." | New stage fails unobserved | Attach the result into the pipeline and have a handling boundary |

## 16. Choosing the right API for your goal

1. **Only want to log, record metrics, or observe a stage?** Choose `whenComplete`. Do not assume the error is recovered.
2. **Only want to replace classified errors with a fallback value of the same type?** Choose `exceptionally`. Verify that the fallback is valid and carries enough metadata.
3. **Want to handle both success and error branches into a new result type?** Choose `handle`. It is useful for producing `Outcome<T>`, a status code, or a unified result record.
4. **Want to retry with another asynchronous task?** Use a bounded retry flow and a stage-composing API; do not treat `exceptionally` returning a `CompletableFuture` as equivalent to flat-map in all cases.
5. **Want to preserve the error for another layer to decide?** Do not force a fallback. Use `whenComplete` to observe (if needed) and let the exception propagate.
6. **Want to ensure actual work stops?** Design cancellation/deadlines at the executor/I/O level; these three callbacks provide no guarantee of physically stopping work.

Place callbacks **at the right boundary**: log before recovering if you need to see the original error; place fallbacks after steps allowed to fail; avoid wrapping multiple phases in a single `handle` when a bug in the final phase should not be masked.

## 17. Practice exercises

**Exercise 1 — verify fallback.** Create `CompletableFuture.failedFuture(new IllegalArgumentException("x"))` and attach `exceptionally(error -> -1)`. Compare `isCompletedExceptionally()` on the source and the new stage. **Expected:** source is `true`, new stage is `false`, and `join()` on the new stage returns `-1`.

**Exercise 2 — success still goes through `handle`.** Create a future completed with `5`, attach `handle((value, error) -> error == null ? "OK:" + value : "FAIL")`. **Expected:** the new stage has type `CompletableFuture<String>`, and `join()` returns `"OK:5"`.

**Exercise 3 — observing does not recover.** Create a failed future, attach a `whenComplete` that only logs. Call `join()` on the returned stage. **Expected:** it still fails (typically with `CompletionException`).

**Exercise 4 — callback fails itself.** Based on `CallbackFailureDemo`, replace the `whenComplete` callback with an action that throws `IllegalStateException` on both a succeeded future and a failed future. **Expected:** if the source succeeded, the new stage reports `IllegalStateException`; if the source already failed, the source error takes precedence.

**Exercise 5 — `null` success value.** Create `CompletableFuture.completedFuture(null)` and attach `handle((value, error) -> error == null ? "SUCCESS" : "FAIL")`. **Expected:** `"SUCCESS"` even though `value == null`.

**Exercise 6 — stage order.** A `thenApply` intentionally throws `ArithmeticException`. Attach `exceptionally` before or after `thenApply` and compare the results. **Expected:** a fallback placed before does not recover from errors originating in `thenApply`; a fallback placed after can see and recover from that error.

**Exercise 7 — avoid masking bugs.** Inside `exceptionally`, recover only from `TimeoutException`; for `NullPointerException`, continue throwing the error. **Expected:** timeout errors receive the fallback, while internal bugs still fail.

**Exercise 8 — outcome with metadata.** Use `handle` to return a record containing whether it truly succeeded or failed along with an error code. **Expected:** the caller does not have to guess a fallback from a `0` value or an empty string.

## 18. References

- [Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `exceptionally`, `handle`, `whenComplete`, `Async` variants, and completion states.
- [Java SE 17 — `CompletionStage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): stage composition contract, exception propagation, and callback error precedence.
- [Java SE 17 — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): exception wrapper when observing asynchronously.
- [Java SE 17 — `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): checked exception received from `Future.get()`.
- [Java SE 17 — `TimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): timeout classification and timeout-based recovery.

**Remember:** `exceptionally` is for **recovering the error path only**; `handle` is for **transforming both success and failure**; `whenComplete` is for **observing without normally changing the result**. Returning a fallback from a callback makes the new stage succeed, **does not clear the error on the original stage**, does not undo side effects, and does not guarantee background work has stopped. Write tests for the success branch, the error branch, throwing callbacks, and stage composition order before deploying a recovery policy to production.
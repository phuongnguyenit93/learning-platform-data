# Error Propagation in Java CompletableFuture Chains

`CompletableFuture<T>` represents a result that will be completed in the future, either **normally with a value** or **exceptionally with an exception/cancellation**. When chaining multiple stages with `thenApply`, `thenCompose`, `thenAccept`, or `thenCombine`, an error in one stage typically **propagates to dependent stages**. Stages that only run on a successful result are **skipped**, whereas error-handling stages such as `exceptionally`, `handle`, and `whenComplete` have the opportunity to intervene with different semantics.

Misunderstanding error propagation paths can lead to very real issues: ignoring errors and returning fake data, accidentally swallowing exceptions, invoking a fallback twice, misreporting errors due to a `CompletionException` wrapper, losing an error from one branch in `allOf`, or assuming `cancel(true)` has stopped background work.

This lesson focuses on **general Java concurrency** with `java.util.concurrent.CompletableFuture` and JDK 17+ APIs; Spring-specific integration mechanisms are out of scope.

## 1. Two Completion States and One Key Principle

A `CompletableFuture<T>` can be:

- **Complete normally**: has a value of type `T`, including `null` if the contract allows it.
- **Complete exceptionally**: has a `Throwable` as the failure cause; cancellation is a type of exceptional completion.
- **Incomplete**: not yet completed; dependent stages may not have a result yet.

A future completes only once through normal mechanisms such as `complete` or `completeExceptionally`; subsequent completion calls do not automatically overwrite the first result. Forceful intervention APIs such as `obtrudeValue/obtrudeException` behave differently and should not be used to alter normal business flows.

**Key takeaway:** a `thenApply` stage does not receive a `Throwable` object to decide for itself. When the upstream fails, the `thenApply` callback is typically **skipped**, and the future created by `thenApply` also completes exceptionally. Only error/completion callbacks can observe a failed outcome.

### Basic Propagation Diagram

```text
supplyAsync(...) --success--> thenApply(...) --success--> thenCompose(...)
       |
       +--failure--> dependent exceptional completion
                          |
                          +--> thenApply callback SKIPPED
                          |
                          +--> exceptionally(...)  -> fallback value
                          |
                          +--> handle(...)         -> transform or recover
                          |
                          +--> whenComplete(...)   -> observe, not recover
```

These paths represent **different ways of attaching stages**, not that every callback is invoked in a single chain. Attachment position and callback type determine the behavior.

## 2. How Propagation Works from a Failed Stage

Consider the chain:

```java
CompletableFuture<Integer> output =
        CompletableFuture.supplyAsync(() -> loadValue())
                .thenApply(value -> normalize(value))
                .thenApply(value -> validate(value))
                .thenApply(value -> persist(value));
```

This is a **snippet**; you need `loadValue/normalize/validate/persist` methods with matching types and an import for `CompletableFuture`.

If `normalize` throws an exception:

1. The future of the `normalize` step completes exceptionally.
2. The `validate` callback **is not invoked** because it is a `thenApply` that runs on a successful result.
3. The `persist` callback **is not invoked** either.
4. The final future completes exceptionally, carrying the failure cause according to the chain's semantics.
5. The caller observes the error via `join`, `get`, or a handler such as `exceptionally/handle`.

If `loadValue` fails right at the start, all three downstream callbacks are skipped. If `persist` fails, the previous two steps have still executed and their side effects **do not automatically roll back**.

**Do not confuse "callback skipped" with "task cancelled":** steps that **already executed before the error** have still run. `CompletableFuture` does not provide transactions, undo, or automatic cancellation for all operations that have already started.

## 3. Java 17: Deterministic Error Propagation and Recovery

Create the file **`PipelinePropagationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class PipelinePropagationDemo {
    public static void main(String[] args) {
        AtomicBoolean downstreamRan = new AtomicBoolean(false);

        CompletableFuture<Integer> failed =
                CompletableFuture.completedFuture(5)
                        .<Integer>thenApply(value -> {
                            throw new IllegalStateException("bad value");
                        })
                        .thenApply(value -> {
                            downstreamRan.set(true);
                            return value * 2;
                        });

        String propagatedCause;
        try {
            failed.join();
            throw new AssertionError("Expected failure");
        } catch (CompletionException e) {
            propagatedCause =
                    e.getCause().getClass().getSimpleName();
        }

        int recovered = failed
                .exceptionally(error -> 40)
                .thenApply(value -> value + 2)
                .join();

        System.out.println(
                "originalExceptional=" + failed.isCompletedExceptionally());
        System.out.println("downstreamRan=" + downstreamRan.get());
        System.out.println("propagatedCause=" + propagatedCause);
        System.out.println("recovered=" + recovered);
    }
}
```

Run on JDK 17+:

```bash
javac PipelinePropagationDemo.java
java PipelinePropagationDemo
```

Stdout:

```text
originalExceptional=true
downstreamRan=false
propagatedCause=IllegalStateException
recovered=42
```

**Explanation:** `completedFuture(5)` is a successful upstream. The next stage throws `IllegalStateException`, so the stage that sets `downstreamRan` does not run. `join` throws `CompletionException`, containing the root cause inside. The `exceptionally` branch creates **another future** with the replacement value `40`, and then `thenApply` adds 2 to produce `42`.

**Notably:** the original `failed` future remains exceptional after creating the recovery branch. `exceptionally` does not mutate the source future's state; it returns a new **dependent future** that may succeed or fail. Therefore, two callers holding two different branches can observe different outcomes without conflict.

This is a deterministic demo: it creates no async workers and does not depend on `Thread.sleep` or scheduler ordering; the goal is to understand **composition semantics** before scaling to real concurrency.

## 4. Four API Groups to Distinguish

| API | When upstream succeeds | When upstream is exceptional | Recovers to normal completion? |
| --- | --- | --- | --- |
| `thenApply(fn)` | Calls `fn(value)` | Skips `fn`, propagates error | No, unless the error was already handled earlier |
| `thenAccept(consumer)` | Calls consumer | Skips consumer, propagates error | No |
| `thenRun(action)` | Calls action | Skips action, propagates error | No |
| `thenCompose(fn)` | Calls `fn` returning a `CompletionStage` and flattens | Skips `fn`, propagates error | No, if no recovery is attached |
| `exceptionally(fn)` | Does not call `fn`, passes value through | Calls `fn` with error; returns value of the same type `T` | **Yes**, if `fn` returns normally |
| `exceptionallyCompose(fn)` | Does not call `fn`, passes value through | Calls `fn` returning a fallback stage of the same type `T` | **Yes**, if the fallback stage succeeds |
| `handle(fn)` | Calls with (`value`, `null`) | Calls with (`null`, `error`) | **Possibly**, if `fn` returns normally |
| `whenComplete(action)` | Calls with (`value`, `null`) | Calls with (`null`, `error`) | **No**, only observes/completion side effect |
| `thenCombine(other,fn)` | Runs `fn` when both upstreams succeed | Does not run `fn` if a dependency fails | No |
| `allOf(...)` | Succeeds when all succeed | Exceptional if at least one fails | Does not auto-recover |
| `anyOf(...)` | Completes with the first future to complete | Exceptional if the winner fails | Does not automatically wait for a "successful winner" |

**Note:** the corresponding `Async` overloads change **where the callback is executed** (for example, on an executor), rather than turning an error-observing method into a recovery method.

## 5. `exceptionally`: Fallback for a Failure

`exceptionally(Function<Throwable, ? extends T>)` only runs when the upstream completes exceptionally. If the callback returns a value of type `T`, the dependent future **transitions to normal completion**.

```java
CompletableFuture<String> safe = remoteCall()
        .exceptionally(error -> "cached-value");
```

This is a snippet; `remoteCall()` returns `CompletableFuture<String>`. If the remote call fails, callers of `safe` can receive `"cached-value"` normally.

### When does a fallback make sense?

- Non-critical data can use a valid configured default.
- A recommendation service can fall back to a backup list.
- An optional read step can return an empty result with clear semantics.
- A secondary provider may be unavailable and we have a designed fallback.

### When should you not return a default fallback?

If a transaction-recording step fails yet the callback returns `null` or `0` and downstream continues reporting success, a serious business error has been **hidden**.

Example that is **wrong if payment must succeed**:

```java
chargePayment()
        .exceptionally(error -> null)
        .thenApply(ignored -> markOrderPaid());
```

This is a snippet; the methods are application-defined. If charging fails, `exceptionally` produces a normal completion with `null`; `markOrderPaid` can be called even though no payment was collected. **Choose fallbacks according to the contract**, and do not use `exceptionally` as a way to globally suppress errors.

### Only recover errors you truly understand

```java
.exceptionally(error -> {
    Throwable cause = unwrapCompletion(error);
    if (cause instanceof KnownTemporaryFailure) {
        return fallbackValue();
    }
    throw new CompletionException(cause);
})
```

This is a **snippet**; `KnownTemporaryFailure` and the helpers are undefined; `CompletionException` is in `java.util.concurrent`. Unexpected errors are **propagated** rather than silently turned into success. Do not rethrow every error in a way that loses the cause or stack trace.

If you need an **asynchronous** fallback future, `exceptionallyCompose` is a better fit than returning a future as type `T` or blocking with `join` inside the error handler.

## 6. `handle`: Sees Both Success and Failure, Can Change Result Type

The `handle(BiFunction<? super T, Throwable, ? extends U>)` method runs when the upstream completes **in either direction**.

```java
CompletableFuture<String> status = request()
        .handle((value, error) -> {
            if (error == null) {
                return "OK:" + value;
            }
            return "FAILED:" + error.getClass().getSimpleName();
        });
```

This is a snippet; `request()` returns a `CompletableFuture<?>` of a matching type. The callback returns a `String`, and the resulting future completes normally if the callback returns normally.

**Do not use `handle` just to log and forget to rethrow.** If a handler is written as:

```java
.handle((value, error) -> {
    if (error != null) log(error);
    return value;
})
```

then on failure, `value` is normally `null`, so the handler **returns `null` and turns the failure into a success**. Downstream steps may receive `null` instead of being skipped. When the goal is only logging, `whenComplete` is usually the right choice.

### `handle` can transform the result type

For example, the previous stage returns `Integer`, while `handle` returns a `Result`/status object covering both success and error. This is useful if a public API wants an **explicit result object** instead of exception propagation. However, it should make the status explicit, not hide errors.

`handleAsync(handler, executor)` preserves the observation/recovery semantics while running the callback on the specified executor. If the executor is shut down and rejects the callback, the dependent stage can also fail due to scheduling/rejection; you must manage the executor lifecycle.

## 7. `whenComplete`: Logging/Metrics Without Swallowing Errors

`whenComplete(BiConsumer<T, Throwable>)` is called when the upstream completes and returns a dependent future carrying **the same outcome** if the callback does not throw an exception.

```java
CompletableFuture<Result> traced = call()
        .whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            } else {
                recordSuccess();
            }
        });
```

This is a snippet; `Result`, `call`, and the metrics functions are application-defined.

- Upstream succeeds, observer succeeds -> downstream receives the exact value.
- Upstream fails, observer succeeds -> downstream remains **exceptional** with the upstream error.
- Upstream succeeds, observer throws -> downstream is **exceptional due to the observer's error**.
- Upstream fails, observer also throws -> by contract, the upstream error remains the primary cause for the dependent future; the secondary error may need to be logged explicitly if you want to preserve information about the observer failure.

**Conclusion:** `whenComplete` is suitable for recording metrics, logging, and simple cleanup, **not as a fallback stage**. If recovery is needed, attach `exceptionally` or `handle` afterward.

### Questions to ask when logging

- Are you logging the same exception multiple times at every stage, causing log spam?
- Are you logging sensitive information in exception messages?
- Could the logging function throw an exception due to a formatter/serializer/network issue?
- Instead of making blocking I/O calls in a callback, should data be written to a bounded queue for diagnostics?
- Are you preserving a correlation ID/workflow ID to trace the root cause without mistaking wrapper errors?

## 8. `exceptionallyCompose`: Fallback Returning a CompletionStage

When recovery needs to call another async source:

```java
CompletableFuture<String> value = primaryAsync()
        .exceptionallyCompose(error -> backupAsync());
```

This is a snippet; `primaryAsync/backupAsync` return `CompletableFuture<String>`. If the primary fails, the callback creates a **fallback stage**; the dependent future completes according to the fallback stage's result (success or failure).

If instead you write:

```java
.exceptionally(error -> backupAsync().join())
```

the error callback can **block the thread** waiting for the fallback; if running on a small executor and the fallback also needs that same executor, there is a risk of **thread starvation**. `exceptionallyCompose` expresses an asynchronous dependency without calling `join` inside the handler.

**Note:** the fallback itself can also throw or return an exceptional stage. The fallback's error then propagates downstream; the API does not guarantee that the fallback will always succeed.

`exceptionallyCompose` is available in JDK 12+, so it is valid on Java 17. The `exceptionallyComposeAsync` overloads use the default async execution facility or a specified executor.

## 9. Java 17: Comparing whenComplete/handle/exceptionally/exceptionallyCompose

Create the file **`RecoveryOperatorsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class RecoveryOperatorsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("invalid id"));

        AtomicInteger observerCalls = new AtomicInteger();

        CompletableFuture<String> observed =
                failed.whenComplete((value, error) ->
                        observerCalls.incrementAndGet());

        String recovered = observed
                .exceptionally(error -> "cached")
                .thenApply(String::toUpperCase)
                .join();

        String handled = failed
                .handle((value, error) ->
                        error == null ? value : "unavailable")
                .join();

        String composed = failed
                .exceptionallyCompose(error ->
                        CompletableFuture.completedFuture("backup"))
                .join();

        CompletableFuture<String> observerFailure =
                CompletableFuture.completedFuture("ok")
                        .whenComplete((value, error) -> {
                            throw new IllegalStateException(
                                    "observer failed");
                        });

        String observerCause;
        try {
            observerFailure.join();
            throw new AssertionError("Expected observer failure");
        } catch (CompletionException e) {
            observerCause =
                    e.getCause().getClass().getSimpleName();
        }

        System.out.println("observerCalls=" + observerCalls.get());
        System.out.println(
                "observedExceptional=" + observed.isCompletedExceptionally());
        System.out.println("recovered=" + recovered);
        System.out.println("handled=" + handled);
        System.out.println("composed=" + composed);
        System.out.println("observerFailure=" + observerCause);
    }
}
```

Run:

```bash
javac RecoveryOperatorsDemo.java
java RecoveryOperatorsDemo
```

Stdout:

```text
observerCalls=1
observedExceptional=true
recovered=CACHED
handled=unavailable
composed=backup
observerFailure=IllegalStateException
```

Explanation of each result:

1. `failed` is already exceptional before dependents are created.
2. `whenComplete` runs once, increments the counter, and returns normally; the `observed` future **remains exceptional**.
3. `exceptionally` attached after `observed` turns the error into `"cached"`, and the next stage converts it to uppercase.
4. `handle` runs with a non-null error and returns `"unavailable"` as a normal completion.
5. `exceptionallyCompose` returns an already-succeeded fallback future `"backup"`, and the result is flattened.
6. A `whenComplete` observer throwing an error when the upstream succeeds makes the dependent future **exceptional due to the observer itself**, even though the original upstream held `"ok"`.

There is no non-deterministic scheduling in the demo: all upstreams use `completedFuture/failedFuture`; the output illustrates **operator semantics**, not a benchmark.

## 10. Where You Place Recovery Changes Business Meaning

Consider two pipelines:

**Early recovery:**

```java
CompletableFuture<Integer> result = load()
        .exceptionally(error -> defaultValue())
        .thenApply(value -> validate(value))
        .thenApply(value -> persist(value));
```

**Late recovery:**

```java
CompletableFuture<Integer> result = load()
        .thenApply(value -> validate(value))
        .thenApply(value -> persist(value))
        .exceptionally(error -> defaultValue());
```

Both are snippets with methods of matching return types. Their meanings are very different:

- **Early recovery**: if `load` fails, subsequent stages still run with the **default value**. That may be desirable for optional data, or dangerous if persistence relies on real data.
- **Late recovery**: any error in `load`, `validate`, or `persist` can be replaced by the default. If `persist` is a critical side effect, late recovery easily hides the cause of a failed transaction.
- If `defaultValue()` itself throws an exception, the dependent future remains exceptional.
- `exceptionally` only catches errors from **the portion of the chain before it**. It does not automatically catch exceptions from stages attached **after it**, unless another handler is added later.
- Each `thenApply` call creates a new future; two branches attached at different points can have different error policies.

**Good design:** place an error boundary at the exact boundary of **a step that can be safely substituted**. Unrecoverable errors should propagate to an owner layer capable of making a business decision.

## 11. Synchronous/Async Callbacks and Where Errors Are Thrown

Methods like `thenApply`, `handle`, and `whenComplete` have both regular and `Async` variants. With the regular variant, the callback may run on the thread that completes the predecessor or another thread performing a completion-related action. **There is no guarantee it always runs on the original submitting thread**.

With `thenApplyAsync(fn, executor)`, the callback is scheduled onto the specified executor. If the executor is no longer accepting tasks or the handler throws an exception, the dependent future can become exceptional. For overloads without an executor parameter, the default async facility typically uses `ForkJoinPool.commonPool` under the conditions stated by the JDK, but do not rely on a fixed thread name for correctness.

### Exceptions inside a callback do not escape directly to the caller building the pipeline

```java
CompletableFuture<Integer> stage =
        CompletableFuture.completedFuture(1)
                .thenApply(value -> {
                    throw new IllegalStateException("boom");
                });
```

This is a snippet. Typically the exception is **captured into the dependent future `stage`**, rather than forcing the caller to catch around the `thenApply` call. The caller observes it via `join/get/handler`. This is very important: a callback finishing without any logs does not mean the task succeeded — the error may be sitting inside an exceptional future.

**Another case:** `executor.submit`/scheduling operations can throw synchronous errors such as rejection right at the API call site. Distinguish between errors **when registering a stage** and errors **inside an asynchronous stage**; the specific contract determines where the exception appears.

## 12. `join()` vs `get()`: Unwrapping Exceptions Properly

| API | On success | On normal failure | Interruptibility |
| --- | --- | --- | --- |
| `future.join()` | Returns value | Typically throws unchecked `CompletionException` wrapping cause | Does not declare `InterruptedException` |
| `future.get()` | Returns value | Throws checked `ExecutionException` wrapping cause | Can throw `InterruptedException` |
| `future.get(timeout, unit)` | Returns value before deadline | `ExecutionException` if future fails, `TimeoutException` if wait exceeds deadline | Can be interrupted |
| `future.join()` when **the future is cancelled directly** | No value | Can throw `CancellationException` directly | Not cancellation recovery |
| `get()` when the future is cancelled | No value | Throws `CancellationException` | Per `Future` contract |

An error **propagated through a dependent stage** can be inside a `CompletionException` whose cause is `CancellationException`. Therefore, you should not catch only `CancellationException` on **all dependent futures** and expect it to always match. Inspect the wrapper layer and root cause.

### Bounded unwrap pattern

```java
static Throwable rootCause(Throwable error) {
    Throwable cursor = error;
    while ((cursor instanceof CompletionException
            || cursor instanceof ExecutionException)
            && cursor.getCause() != null) {
        cursor = cursor.getCause();
    }
    return cursor;
}
```

This is a snippet; import `java.util.concurrent.CompletionException` and `ExecutionException`. It strips **common standard wrappers**, which does not mean you must always unwrap all nested causes of a business exception. If layers use custom exceptions with contextual information, preserve them in logs and error responses; unwrap only to **classify** the error appropriately.

Do not use `future.getNow(default)` as a mechanism to recover from all failures: if the future has completed exceptionally, that method can still throw an unchecked exception per its contract. If you need a real fallback, use `exceptionally/handle`.

### Do not confuse `isDone` with success

`isDone()` can be `true` for **normal**, **exceptional**, or **cancelled** completion. `isCompletedExceptionally()` indicates an exceptional outcome, but does not replace reading the cause. `isCancelled()` returns `true` for cancellation of that specific future, and does not assert that all worker computations have finished cancelling.

## 13. `thenCompose`: Errors Propagate Across Asynchronous Layers

`thenCompose(fn)` is typically used when the current stage needs to invoke a second asynchronous operation. It **flattens** `CompletionStage<CompletionStage<U>>` into a single stage `U`:

```java
CompletableFuture<Order> result = fetchOrder(orderId)
        .thenCompose(order -> fetchDetails(order)
                .thenApply(details -> enrich(order, details)));
```

This is a snippet; the types/methods are application-defined.

Failure paths:

- `fetchOrder` fails -> the `thenCompose` callback does not run; `fetchDetails` is not called.
- `fetchOrder` succeeds but the callback throws an exception -> the composed stage is exceptional.
- The callback returns the `fetchDetails` future, and that future fails -> the inner future's error propagates to the outer stage.
- The callback returns `null` instead of a valid `CompletionStage` -> the dependent stage is exceptional (typically due to a null-related failure), not a normal `null` result.
- `enrich` throws an exception -> the final future is exceptional.

**Do not lose an asynchronous result** by writing:

```java
.thenApply(order -> fetchDetails(order))
```

if `fetchDetails` returns `CompletableFuture<Details>`. That produces a **nested** `CompletableFuture<CompletableFuture<Details>>` stage, and the inner future's error is not automatically treated as an error of the outer `thenApply` as you might intend. `thenCompose` is the right form when you want the inner stage's result and error to **propagate**.

### Fail-fast by business stage

If a mandatory validation/payment step fails, downstream stages should usually be skipped. Use `thenCompose`/`thenApply` **without recovering** at that step unless a business fallback is genuinely valid. An error handler can be placed at the request boundary to produce an appropriate error response.

## 14. Fan-in: `allOf` When One of Several Tasks Fails

`CompletableFuture.allOf(f1,f2,f3)` creates a future that completes when **all provided futures have completed**. If one future is exceptional, `allOf` is also exceptional. However:

- `allOf` returns `CompletableFuture<Void>`; it **does not collect the values** of the futures.
- It **does not automatically cancel sibling futures** when one branch fails.
- If multiple branches fail, the aggregate's exception typically **does not fully represent every cause**; do not depend on "which exception is picked first".
- When `allOf` is exceptional, a success-dependent `thenRun/thenApply` callback is skipped.
- To collect all errors for reporting, read **the outcomes of each individual future** after `allOf` completes or attach a separate handler to each branch.

### Use a handler to turn each outcome into an explicit value

```java
CompletableFuture<Result<Integer>> safeA =
        taskA.handle((value, error) ->
                error == null
                        ? Result.success(value)
                        : Result.failure(error));

CompletableFuture<Result<Integer>> safeB =
        taskB.handle((value, error) ->
                error == null
                        ? Result.success(value)
                        : Result.failure(error));
```

This is a snippet assuming an appropriate `Result<T>` type; `taskA/taskB` are `CompletableFuture<Integer>`. Here `allOf(safeA,safeB)` can complete normally if **all handlers return normally**, and then the caller collects both success and failure records. That **does not automatically turn the business workflow into a success**: the decision layer must still check whether any error requires aborting.

Do not swallow all errors with `exceptionally(error -> null)` and treat `null` as valid data without an explicit outcome type. Especially avoid losing error context during fan-in.

## 15. Java 17: allOf and anyOf Do Not Auto-Recover

Create the file **`FanInFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FanInFailureDemo {
    static String causeName(CompletableFuture<?> stage) {
        try {
            stage.join();
            return "none";
        } catch (CompletionException e) {
            return e.getCause().getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> first = new CompletableFuture<>();
        CompletableFuture<Integer> second = new CompletableFuture<>();
        CompletableFuture<Integer> third = new CompletableFuture<>();

        CompletableFuture<Void> all =
                CompletableFuture.allOf(first, second, third);

        AtomicBoolean nextStageRan = new AtomicBoolean(false);
        CompletableFuture<Integer> next = all.thenApply(ignore -> {
            nextStageRan.set(true);
            return first.join() + second.join() + third.join();
        });

        first.complete(1);
        second.completeExceptionally(
                new IllegalStateException("subtask failed"));
        boolean allStillWaiting = !all.isDone();
        third.complete(3);

        System.out.println("allStillWaiting=" + allStillWaiting);
        System.out.println("allCause=" + causeName(all));
        System.out.println("nextStageRan=" + nextStageRan.get());
        System.out.println("nextCause=" + causeName(next));

        CompletableFuture<Integer> fastFailure = new CompletableFuture<>();
        CompletableFuture<Integer> slowSuccess = new CompletableFuture<>();
        CompletableFuture<Object> any =
                CompletableFuture.anyOf(fastFailure, slowSuccess);

        fastFailure.completeExceptionally(
                new IllegalArgumentException("first finished with error"));
        slowSuccess.complete(99);

        System.out.println("anyCause=" + causeName(any));
    }
}
```

Run:

```bash
javac FanInFailureDemo.java
java FanInFailureDemo
```

Stdout:

```text
allStillWaiting=true
allCause=IllegalStateException
nextStageRan=false
nextCause=IllegalStateException
anyCause=IllegalArgumentException
```

**Reasoning:**

1. `allOf` is attached while all three futures are still incomplete.
2. `first` succeeds, `second` is exceptional, but `third` is not yet complete -> `allOf.isDone()==false` per the "all" contract.
3. After `third.complete(3)`, the aggregate is exceptional because `second` failed; the `thenApply` callback after the aggregate is skipped.
4. `anyOf` is created while both inputs are incomplete; we **deliberately complete the failure first** and then complete the success, so the winner is an error and the aggregate is exceptional. It **does not** ignore the error to wait for a later success.
5. There is no asynchronous scheduler running in the demo; the `complete` calls are invoked sequentially, keeping the output deterministic.

**Important caveat:** when multiple futures actually run concurrently and fail close together, `allOf` can pick whichever cause represents the aggregate according to internal completion semantics. Do not assert a specific error name when **multiple branches fail** and you do not control ordering/selection. To capture all errors, record each branch's outcome.

## 16. `anyOf` Is Not "First Successful Result"

`anyOf` finishes according to **the first future to complete**; if that future is exceptional, the aggregate is immediately exceptional as well. A later success does not make it recover.

If the requirement is **first successful**, you need a dedicated algorithm:

- Iterate/attach callbacks to each candidate, completing a result promise normally with `complete(value)` on the first success.
- Count failures and only call `completeExceptionally` when **all candidates have failed**.
- Consider cancelling the losers and managing cleanup/resources of tasks still running.
- Decide precedence between cancellation, timeout, and a success race.
- Do not use a success `AtomicBoolean` while forgetting happens-before/publication of the payload.

In many cases, a composition library or domain-specific abstraction can make this clearer. Never **refer to `anyOf` as first-success** because the name is misleading.

### No inputs

`allOf()` with an empty array returns an already normally completed future; `anyOf()` with an empty array returns an incomplete future. When an empty list is possible, you must define clear semantics; otherwise `join()` on `anyOf()` with no inputs can wait forever.

## 17. Cancellation Is Also an Exceptional Completion Path

`CompletableFuture.cancel(mayInterruptIfRunning)` completes the future exceptionally with `CancellationException` if cancellation is accepted. Incomplete dependent stages typically also complete exceptionally (usually with `CompletionException` whose cause is `CancellationException`).

**Specific to the `CompletableFuture` implementation:** the `mayInterruptIfRunning` parameter **is not used to control interruption** in this implementation per the API documentation. Calling `cf.cancel(true)` **is not a guarantee that the thread running the supplier was interrupted**.

### Java 17: cancellation propagates to a dependent stage

Create **`CancellationAndTimeoutDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancellationAndTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        AtomicBoolean downstreamRan = new AtomicBoolean(false);

        CompletableFuture<Integer> dependent =
                source.thenApply(value -> {
                    downstreamRan.set(true);
                    return value + 1;
                });

        boolean cancelled = source.cancel(true);

        String dependentCause;
        try {
            dependent.join();
            throw new AssertionError("Expected dependent failure");
        } catch (CompletionException e) {
            dependentCause =
                    e.getCause().getClass().getSimpleName();
        }

        CompletableFuture<Integer> timedOut = new CompletableFuture<>();
        timedOut.orTimeout(50, TimeUnit.MILLISECONDS);

        String timeoutCause;
        try {
            timedOut.join();
            throw new AssertionError("Expected timeout");
        } catch (CompletionException e) {
            timeoutCause =
                    e.getCause().getClass().getSimpleName();
        }

        CompletableFuture<Integer> defaulted = new CompletableFuture<>();
        defaulted.completeOnTimeout(7, 50, TimeUnit.MILLISECONDS);

        System.out.println("cancelAccepted=" + cancelled);
        System.out.println("sourceCancelled=" + source.isCancelled());
        System.out.println("dependentCancelled=" + dependent.isCancelled());
        System.out.println("downstreamRan=" + downstreamRan.get());
        System.out.println("dependentCause=" + dependentCause);
        System.out.println("timeoutCause=" + timeoutCause);
        System.out.println("timeoutDefault=" + defaulted.join());
    }
}
```

Run:

```bash
javac CancellationAndTimeoutDemo.java
java CancellationAndTimeoutDemo
```

Normal stdout:

```text
cancelAccepted=true
sourceCancelled=true
dependentCancelled=false
downstreamRan=false
dependentCause=CancellationException
timeoutCause=TimeoutException
timeoutDefault=7
```

Explanation:

- `source.cancel(true)` transitions `source` to cancelled. The dependent `thenApply` has no successful value to process, so its callback does not run.
- The dependent is exceptional with a `CompletionException` wrapper whose cause is `CancellationException`, but **was not cancelled directly**, so `dependent.isCancelled()` is `false`.
- `orTimeout` completes **the future it is called on** with `TimeoutException` if it is still incomplete when the deadline expires. In the demo nobody completes `timedOut`, so it times out.
- `completeOnTimeout(7, ...)` completes **the future it is called on** with the value `7` when the deadline expires and the future is still incomplete. This is a **normal completion**, not an exception.
- The demo does not create a running supplier, so it **does not prove thread interruption**. In real applications, `CompletableFuture` timeout/cancel does not guarantee stopping I/O or background tasks; you must design resource timeouts/cooperative cancellation separately.

The 50 ms intervals intentionally trigger the timeout paths. The program uses `join()` to wait for state, does not rely on `Thread.sleep`, and does not assert that the scheduler wakes up at exactly 50 ms.

## 18. Timeout Is Not the Same as `get(timeout)`

These three semantics are frequently confused:

| API | Is the original future's state mutated? | On timeout | Does the background task stop? |
| --- | --- | --- | --- |
| `future.get(100, MILLISECONDS)` | **No**, not just because the caller timed out | Caller receives `TimeoutException` | Does not auto-cancel the task |
| `future.orTimeout(100, MILLISECONDS)` | **Yes**, if the future is still incomplete | Future completes exceptionally with `TimeoutException` | Not guaranteed to stop computation |
| `future.completeOnTimeout(default, 100, MILLISECONDS)` | **Yes**, if the future is still incomplete | Future completes normally with default | Not guaranteed to stop computation |

**Important:** `orTimeout` and `completeOnTimeout` return **that same `CompletableFuture`** to support chaining, rather than always creating a new dependent future. If multiple callers hold references to the original future, they will also see the mutated state when the timeout applies.

A real unit of work can still finish **after** the future has timed out. A late `complete(value)` call will not change the already-completed normal/exceptional state. However, the work/supplier **can still consume CPU, hold connections, or cause side effects** if not cooperatively cancelled.

If you want **a timeout only at one caller's wait point** without mutating the source future, `get(timeout, unit)` has a different meaning. If you want to time out a **dependent view**, design a dedicated wrapper/view intentionally.

## 19. Retrying After Exceptional Completion: Don't Assume `exceptionally` Retries

An `exceptionally` callback **does not re-run the source supplier**. It only receives the exception and can return a fallback value. To retry an operation, you must **re-invoke the logic that creates a new attempt** according to a policy:

- Only retry genuinely safe transient errors.
- Enforce a max attempt limit, deadline, and backoff/jitter as needed.
- Account for requests that already caused a side effect whose response was lost; a retry might execute the side effect a second time.
- Keep an idempotency key or deduplication/transaction mechanism if the business domain requires it.
- Do not block an executor thread with a `Thread.sleep`/`join` loop just to wait for a retry when a better async model exists.
- Do not let retries "fail and retry forever" and cause unbounded concurrency growth.

### Conceptual example

```java
CompletableFuture<Result> primary = attemptAsync();

CompletableFuture<Result> withOneRetry =
        primary.exceptionallyCompose(error -> {
            if (!isTransient(error)) {
                return CompletableFuture.failedFuture(error);
            }
            return attemptAsync();
        });
```

This is a **snippet**; `Result/attemptAsync/isTransient` are application-defined. It creates **a new attempt exactly once** when the error is classified as transient; if the second attempt fails, the new attempt's error propagates. In practice, unwrap exception wrappers before classifying, and manage timeouts/cancellation across attempts.

**Do not write `exceptionally(error -> primary.join())`**: `primary` has already failed, so `join()` only throws the old error and does not create a retry.

## 20. What If a Handler Throws an Exception or Returns a Failed Future?

Error-handling callbacks are **not immune to failure**. They can:

- Throw `IllegalStateException` due to a bug.
- Call a DB/network and fail.
- Return a `CompletableFuture.failedFuture(...)` via `exceptionallyCompose`.
- Read state that has already been shut down/closed.
- Be rejected by the executor when scheduling if using an `Async` variant.
- Encounter cancellation or timeout in the fallback stage.

Example:

```java
CompletableFuture<Integer> recovered =
        source.exceptionally(error -> {
            throw new IllegalStateException("fallback failed");
        });
```

This is a snippet; `source` is `CompletableFuture<Integer>`. If `source` fails, the callback throws -> the `recovered` future is also exceptional, this time due to **fallback failed**. The original exception may no longer be the dependent's primary exception. If both need to be preserved, the application must explicitly design chained causes/suppressed exceptions or an outcome object; do not assume `CompletableFuture` retains every error from all branch paths.

**When should `whenComplete` be attached at the end of a pipeline?** When you only want to log the final outcome, preserving the pipeline's primary exception as long as the callback does not throw. Still, an observer throwing is also a failure; avoid letting logging/metrics break a successful business result.

## 21. Exception Handling and Thread Interruption

A `Future.get()` call can throw `InterruptedException` if **the waiting thread** is interrupted. This differs from a `CompletableFuture` that **completed exceptionally because of a worker's `InterruptedException`**. You must distinguish:

- **Interrupting the waiting caller:** `get()` throws `InterruptedException` directly; the caller thread should propagate or restore the interrupt flag and exit per policy.
- **Supplier turning an interrupt into an exceptional completion:** `get()` can throw `ExecutionException` with an `InterruptedException` or wrapper as its cause; that is a *task failure* reported through the future.
- **`join()` does not declare `InterruptedException`**: that does not make it a cancellation/cleanup mechanism.
- **`CompletableFuture.cancel(true)`**: does not guarantee interrupting the supplier's worker.
- **`FutureTask.cancel(true)`** from another executor has different may-interrupt semantics; do not infer that they behave identically to `CompletableFuture`.

Proper waiting pattern when the API allows propagating interruption:

```java
try {
    Result result = stage.get();
    consume(result);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    stopWaiting();
} catch (ExecutionException e) {
    handleTaskFailure(e.getCause());
}
```

This is a snippet; `Result/consume/stopWaiting/handleTaskFailure` are application-defined. If the method is allowed to declare `throws InterruptedException`, you can **propagate** instead of catching and restoring. When the caller is interrupted, do not assume all upstream stages have been cancelled; separate lifecycle control is required.

## 22. Errors Inside a Worker vs Errors of the Whole Workflow

A pipeline can have multiple levels of errors:

1. **Business validation**: invalid input; usually not retried.
2. **Transient I/O**: timeout, rate limit; can be retried if idempotent.
3. **Permanent dependency failure**: service not available; fallback may or may not apply depending on the contract.
4. **Cancellation**: user aborts request or deadline expires; usually unnecessary work should stop.
5. **Programming bug**: `NullPointerException`, invariant violation; should not be swallowed with an arbitrary default.
6. **Resource exhaustion**: executor rejection, OOM risk, connection pool exhaustion; requires backpressure and telemetry.
7. **Observer/cleanup failure**: should not silently replace the original error.

When designing handlers, define **policies by error category** rather than "catch every `Throwable` and return `null`".

### Making outcomes explicit with types

A `sealed interface Result<T>` or `Success/Failure` record can be appropriate when multiple branches need to collect and report structured errors. However, when deciding to turn an exception into `Result.Failure`, remember that the future completes **normally** with the `Failure` object; subsequent `thenApply` stages will still run unless they check the status. This is an explicit API design choice, not a default `CompletableFuture` mechanism.

## 23. Propagation in Side Branches and Unobserved Errors

A future can be exceptional without **anyone calling `get/join` or attaching a handler**, because `CompletableFuture` does not automatically print stack traces for every failed stage. Thus:

```java
fireAndForgetAsync()
        .thenApply(value -> riskyTransform(value));
```

is a snippet that can leave errors trapped in a dependent future unhandled if the application drops the reference. For background work, you need an owner observing completion, metric/error reporting, and a shutdown policy.

### But don't log the same error at every stage

If every stage calls `whenComplete` and logs the stack trace of the same failure, one root error can produce 10 identical log entries. Choose appropriate boundaries:

- Log **the first time** at the source if technical details are needed.
- Log the **business outcome** at the request boundary.
- Use a trace/correlation ID to link stages.
- Avoid leaking sensitive data through exception logs.
- Record aggregated status for fan-in instead of just a random branch error.

## 24. Errors in `thenCombine`, `allOf`, and Multi-Source Dependencies

With two futures:

```java
CompletableFuture<Result> result =
        left.thenCombine(right, (a, b) -> combine(a, b));
```

This is a snippet assuming matching types/methods. If `left` or `right` is exceptional, the `combine` callback is not called on the normal path. However, **the result's error is a dependency error**, which does not mean the other dependency is automatically cancelled. If both fail, the selected error should be treated as **one representative outcome**, not a replacement for full logs of both branches.

Similarly with `allOf`, waiting for components and aggregating results after all complete are two separate steps. One approach to collect all causes:

```java
CompletableFuture<Outcome<A>> a = aTask
        .handle((value, error) -> toOutcome(value, error));

CompletableFuture<Outcome<B>> b = bTask
        .handle((value, error) -> toOutcome(value, error));

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
```

This is a snippet; `Outcome` and `toOutcome` must be defined. If neither handler **throws**, `all` can succeed and the controller can read the outcomes and decide whether to retry/abort. **Never turn every handler into a success and ignore the error field**.

If **fail-fast** behavior is required to stop siblings immediately when one branch fails, `allOf` does not provide that mechanism itself. You need separate cancellation propagation, task management, and resource cleanup. For data requiring a consistent snapshot, a transactional workflow is sometimes better than composing raw futures.

## 25. `minimalCompletionStage()`, `copy()`, and Protecting Upstream

In library design, sometimes you do not want callers to have the ability to call `complete` or `completeExceptionally` on an internal future. `CompletableFuture.minimalCompletionStage()` provides a view restricting completion methods, while `copy()` creates a dependent future reflecting the source's completion per the API contract.

These operations help **restrict mutation rights**, not make errors disappear on their own. Normal/exceptional outcomes still need handling. `CompletionStage` can be an appropriate API return type to avoid exposing all mutator methods of `CompletableFuture`.

**Warning:** `toCompletableFuture()` on a `CompletionStage` is not always the original mutable reference you own; read the implementation contract. Do not use `obtrudeException` to force an outcome onto an already-completed future in normal workflows: dependents already triggered earlier may hold stale results and make system state hard to reason about.

## 26. Common Misconceptions

| Misconception | What's wrong? | Right approach |
| --- | --- | --- |
| "`thenApply` still runs on upstream error with a null value" | Success callbacks are skipped | Use `exceptionally/handle` if recovery is needed |
| "`exceptionally` is only for logging, doesn't change outcome" | Returning a value turns failure into success | Use `whenComplete` to observe |
| "`whenComplete` catches and recovers exceptions" | Observers do not recover | Attach `exceptionally/handle` afterward |
| "`handle` logging then returning `value` is safe" | On error `value` may be null, swallowing the error | Propagate or convert to an explicit outcome |
| "`join` and `get` throw the same checked exception" | Wrapper/interrupt semantics differ | Catch `CompletionException` vs `ExecutionException` |
| "`isDone()` means success" | Exceptional/cancelled are also done | Read the outcome and cause |
| "`thenApply` with a future-returning callback flattens it" | Produces a nested future | Use `thenCompose` |
| "`allOf` cancels siblings immediately when one fails" | It does not auto-cancel | Design cancellation separately |
| "`allOf` collects all values" | Returns `Void` | Read each future after completion |
| "`anyOf` returns the first success" | It takes the first **completion**, which may be an error | Dedicated first-success algorithm |
| "`cancel(true)` on `CompletableFuture` always interrupts the worker" | `CompletableFuture` does not control interruption via this flag | Cooperative cancellation/resource timeout |
| "`orTimeout` only times out the caller" | It completes the future itself if still incomplete | Use `get(timeout)` to only bound the wait |
| "`completeOnTimeout` produces an exception" | It completes with a default value | Separate fallback and error per contract |
| "Recovering at the end of a chain is always good" | Can hide write/payment errors | Place at steps where fallback is valid |
| "If nobody calls `get` on a callback, the JVM auto-logs errors" | Future can hold the exception silently | Observe at the owner boundary |
| "`exceptionally` auto-retries the supplier" | Does not create a new attempt | Retry with a new supplier and policy |
| "`whenComplete` cannot fail a succeeding stage" | Observer throwing can make dependent exceptional | Keep observers lightweight and safe |
| "When multiple branches fail, the aggregate keeps all errors" | May only keep one representative cause | Collect each outcome separately |
| "Async is always non-blocking" | Suppliers and `join` can still block | Choose the right executor and composition |
| "Cancelled future means resources are closed" | Worker may still be running | Separate completion/cleanup handshake |

## 27. Debugging Checklist for "Lost" Exceptions in a Chain

1. **Draw the stage graph**, marking each `thenApply/thenCompose/handle/exceptionally/whenComplete`.
2. **Identify the first failing stage**: stack trace/source exception, not just the top-level `CompletionException`.
3. **Mark skipped stages**: success callbacks do not run if a predecessor is exceptional.
4. **Find recovery points**: is there an `exceptionally` returning a default, a `handle` returning `null`, or an `exceptionallyCompose` calling a fallback?
5. **Trace branches**: are there two downstream futures from the same source, one recovering and one still failing?
6. **Distinguish wrappers**: `join` -> `CompletionException`; `get` -> `ExecutionException`; direct cancel -> `CancellationException`.
7. **Count fan-in failures**: how many `allOf` inputs are exceptional, and which inputs are still incomplete?
8. **Check observer errors**: does `whenComplete` logging/metrics throw an exception?
9. **Check cancellation/timeout**: did `orTimeout` mutate the future itself? Is the worker still running?
10. **Check thread starvation**: is there a blocking `join/get` inside an executor that the fallback also needs?
11. **Check executor rejection/shutdown**: were `Async` callbacks scheduled successfully?
12. **Check ownership**: who is responsible for observing errors and cleaning up after the response or workflow finishes?
13. **Check retries**: does the fallback repeat side effects, or are there too many outstanding tasks?
14. **Test with already-completed/failed futures**: isolate propagation from scheduling noise.
15. **Report both root cause and boundary**: log sufficient context without duplication or exposing sensitive data.

### Test failure paths instead of only the happy path

A minimal test suite should cover:

- Source succeeds, all stages succeed.
- Source is exceptional, `thenApply` callbacks are skipped.
- Intermediate stage throws an unchecked exception; downstream is skipped.
- `thenCompose` returns an exceptional inner future.
- `exceptionally` recovers expected errors; unexpected errors still propagate.
- `handle` covers both success/error cases and does not accidentally swallow errors.
- `whenComplete` observer succeeds and observer throws.
- `exceptionallyCompose` fallback succeeds and fallback fails.
- `allOf` with one failing input, another incomplete input, and multiple failing inputs.
- `anyOf` with a failing winner followed by a succeeding follower.
- `cancel` on source and error propagation to dependent.
- `get(timeout)` compared with `orTimeout/completeOnTimeout`.
- Worker cleanup after cancellation, not just future state.
- Shutdown/executor rejection on `Async` callbacks.
- Non-duplicated error metrics/logging with correlation ID.

## 28. Self-Check Questions

**1. Is `thenApply` called if its predecessor is exceptional?** No; the dependent future carries the error, unless the stage was already recovered before reaching `thenApply`.

**2. Does `exceptionally` mutate the original future's state?** No; it returns a new dependent future, which can be normal if the callback returns a fallback.

**3. Does `whenComplete` recover?** No. If the observer returns normally, the original outcome is preserved.

**4. Can `handle` turn an error into a success?** Yes. If the handler returns a normal value when `error` is non-null, the dependent future succeeds.

**5. How does `exceptionallyCompose` differ from `exceptionally`?** It returns a `CompletionStage` as the fallback path, avoiding calling `join` inside the handler to obtain a value.

**6. Does `thenCompose` preserve an inner future's error?** Yes; an exceptional inner future makes the composed stage exceptional.

**7. Does `thenApply` returning a future automatically flatten it?** No. It creates a nested stage with the future as the value.

**8. Why does `join()` usually surface `CompletionException`?** It is the unchecked wrapper defined by the API to propagate causes from asynchronous stages.

**9. What can `get()` throw when a worker fails?** `ExecutionException` wrapping the cause, aside from interruption/cancellation cases.

**10. Does `allOf` collect values?** No; it returns `CompletableFuture<Void>`, only signaling that all have completed.

**11. Does `allOf` automatically cancel siblings when one input fails?** No.

**12. Does `anyOf` guarantee success if an input succeeds later?** No. If the first winner failed, `anyOf` is already exceptional.

**13. Does `future.isDone()==true` mean a valid value is present?** No; exceptional/cancelled futures are also done.

**14. Does `CompletableFuture.cancel(true)` guarantee interrupting the supplier's worker?** No; `mayInterruptIfRunning` is not used to control interruption in `CompletableFuture` per the docs.

**15. Does `orTimeout` create an independent future?** No; it completes the `CompletableFuture` it is called on if still incomplete, and returns that same object.

**16. Does `get(timeout)` make the future exceptional when the caller waits past the timeout?** No; the caller gets a timeout, but the original future can still continue.

**17. If a `whenComplete` throws an error on a succeeding future, what happens?** The dependent future can become exceptional due to the observer failure.

**18. What if both the upstream and the `whenComplete` observer fail?** The upstream exception takes precedence in the dependent outcome per contract; log the observer failure separately if important.

**19. Why can an `exceptionally` at the end of a chain be dangerous?** It can mask data-writing/side-effect failures that must not fall back.

**20. What is a real retry?** Creating and executing **a new attempt**, with a policy, deadline, and idempotency; not just returning a default in `exceptionally`.

## 29. Production Design Checklist

- Is the **stage graph** fully mapped from source to final result?
- Is it defined which errors are **recoverable** and which must fail the whole workflow?
- Are success-only stages skipped as expected when the upstream fails?
- Is `exceptionally` placed at the right boundary and returning a **genuinely valid** fallback?
- Does `handle` accidentally return `null` on error and swallow failures?
- Does `whenComplete` only observe/log, without blocking I/O or unintended throws?
- Is `exceptionallyCompose` used when the fallback requires an async stage?
- Is `thenCompose` used properly for future-returning callbacks, avoiding nested stages?
- Are `join/get` called in places that do not cause thread starvation?
- Are `CompletionException/ExecutionException` unwrapped when **classifying** errors?
- Is full exception context preserved for logging/tracing instead of only the message?
- Are cancellation/timeout handled separately without equating future state with worker termination?
- Is `get(timeout)` distinguished from `orTimeout/completeOnTimeout`?
- Does `allOf` manage results and errors for **each input**, not just the aggregate cause?
- Is `anyOf` used only when wanting the first **completion**, not the first success?
- Do fallback/retry have clear idempotency, budget, deadline, and backpressure?
- Do async callbacks have a lifecycle-managed executor rather than using the common pool arbitrarily?
- Does each future's owner take responsibility for observing errors, cleanup, and shutdown?
- Do tests cover exceptional cases at each stage, fan-in, cancellation, and observer failure?
- Can public APIs return `CompletionStage`/a `Result` type to prevent callers from mutating internal futures?

**Conclusion:** In a `CompletableFuture` chain, errors **propagate through dependent stages** and typically **skip callbacks that only run on success**. `exceptionally` can provide a fallback, `exceptionallyCompose` chains an asynchronous fallback, `handle` observes both outcomes and can transform them, and `whenComplete` is primarily for observing **without recovering**. `join/get` expose different wrappers; `allOf/anyOf` have clear semantics but do not automatically collect all errors, retry, or cancel siblings. Proper design requires **placing error boundaries to match business semantics**, classifying errors, preserving the root cause, and managing cancellation, timeouts, and worker cleanup independently of `Future` state.

### References

- Oracle Java SE 17 API: [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- Oracle Java SE 17 API: [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- Oracle Java SE 17 API: [CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- Oracle Java SE 17 API: [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

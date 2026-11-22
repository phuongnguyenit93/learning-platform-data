# completeExceptionally and failedFuture in Java CompletableFuture

> **Topic:** Java Core → Exception → CompletableFuture. This article analyzes two ways to represent failure in `CompletableFuture`: `completeExceptionally(Throwable)` to complete an **existing** future exceptionally, and `CompletableFuture.failedFuture(Throwable)` to **immediately create** a future that is already completed exceptionally. It focuses on the completion mechanism, exceptions observed in `get()`/`join()`, impact on dependent stages, common mistakes, and how to choose the appropriate API in Java 17+.

## 1. What state is exceptional completion?

A `CompletableFuture<T>` represents the result of a computation that may arrive immediately or in the future. It has the following main observable states:

- **Incomplete:** no final result yet; `isDone()` returns `false`.
- **Completed normally (successfully):** contains a value of type `T`, including `null`; callers can retrieve the value with `get()` or `join()`.
- **Completed exceptionally (exceptional completion):** contains information about the cause of failure; both `isDone()` and `isCompletedExceptionally()` return `true`.
- **Cancelled (cancellation):** also a form of exceptional completion with its own semantics; `isCancelled()` returns `true` for a future cancelled via the corresponding cancellation mechanism.

Examples: reading a file fails, invalid data, service unavailable, a callback returns an error, or a stage throws an exception. These cases can be modeled using exceptional completion.

**Key point:** when calling `completeExceptionally(ex)`, the method **does not throw `ex` immediately onto the caller's call stack**. It records `ex` as the failure state of the future. The error is surfaced where the result is retrieved or the stage is handled, such as `join()`, `get()`, `exceptionally(...)`, or `handle(...)`.

~~~text
                      CompletableFuture<T>
                             |
              +--------------+--------------+
              |                             |
          incomplete                    completed
              |                             |
      complete(value)              +--------+---------+
      completeExceptionally(ex)    |                  |
              |                normally          exceptionally
              |              contains value     contains error cause
              |                  |                  |
              +------------------+------------------+
                                 |
                get(), join(), dependent stages
~~~

A future already completed through the normal mechanism cannot transition from success to failure via a subsequent `completeExceptionally` call, or vice versa. Java picks the winning result when completions race. Advanced APIs like `obtrudeValue`/`obtrudeException` have different semantics and should not be used as the standard way of completing a future.

## 2. completeExceptionally(Throwable): marking an existing future as failed

Instance method signature:

~~~java
public boolean completeExceptionally(Throwable ex)
~~~

Given an already created `CompletableFuture<T>`, the call:

~~~java
// Valid illustrative snippet inside a Java method.
CompletableFuture<String> promise = new CompletableFuture<>();
boolean won = promise.completeExceptionally(
        new IllegalStateException("service unavailable"));
~~~

means:

1. If `promise` is not yet completed, it is completed exceptionally with `ex`; the method returns `true`.
2. If `promise` is already completed (normally, exceptionally, or cancelled), the method returns `false` and preserves the already established state.
3. The method is an operation to **complete the future**, not a command telling a running worker to stop or undo side effects.
4. Stages dependent on `promise` are triggered/completed according to each operator's semantics. A stage receiving the error can recover, record it, or propagate it further.
5. The `ex` argument must be non-null; passing `null` results in a `NullPointerException`. The `Throwable` type can be a checked exception such as `IOException`, but when waiting for the result, it is reported through the appropriate wrapper.

The boolean value reflects **whether this call won the completion**, not business success. For a future already marked as failed, `isCompletedExceptionally()` is `true` even if a subsequent `completeExceptionally` returned `false` earlier or later.

### If multiple places complete at the same time

~~~java
// Illustration inside a method.
CompletableFuture<Integer> result = new CompletableFuture<>();

boolean first = result.complete(42); // true
boolean second = result.completeExceptionally(
        new IllegalStateException("too late")); // false
~~~

The future still succeeds with `42`. If two threads actually race to call `complete(42)` and `completeExceptionally(ex)`, which one wins depends on execution order; in each race, only **one** normal completion result takes effect. Do not design business logic around a specific assumption about which thread always wins. Clearly define who has the authority to complete and who is responsible for handling a `false` return value.

## 3. failedFuture(Throwable): immediately creating an already failed future

Static factory signature:

~~~java
public static <U> CompletableFuture<U> failedFuture(Throwable ex)
~~~

Since Java 9, you can create one directly:

~~~java
// Illustrative snippet in a method returning CompletableFuture<String>.
return CompletableFuture.failedFuture(
        new IllegalArgumentException("invalid customer id"));
~~~

Things to understand:

- Creates a **new `CompletableFuture<U>` instance** that is already completed exceptionally from the moment it is returned.
- No need to create `new CompletableFuture<>()` and then call `completeExceptionally(...)`.
- Does not submit work to an executor and does not create a thread; this factory is **not** an asynchronous operation.
- Can serve as the return value of an API declaring `CompletableFuture<T>` when a synchronous error is detected (invalid input, missing configuration, insufficient permissions) while keeping the API consistent in returning a future.
- `ex` must be non-null, just like `completeExceptionally`.

Example:

~~~java
static CompletableFuture<String> lookup(String id) {
    if (id == null || id.isBlank()) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("id must not be blank"));
    }

    // In a real system, the valid branch would typically call an asynchronous service.
    return CompletableFuture.completedFuture("user:" + id);
}
~~~

This is a snippet that can be placed in an appropriate Java class; `lookup(" ")` does not need to wait for a background task to become failed. The caller still decides how to handle the future's error state via `join()`, `get()`, or a pipeline.

### Choosing the generic type

When the method's return type is `CompletableFuture<Order>`, the compiler usually infers `U = Order` from the return context. If context is lacking, you can specify it explicitly:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.<String>failedFuture(
                new IllegalArgumentException("invalid input"));
~~~

This is Java's type witness syntax for a static generic method, not a different way of handling exceptions.

## 4. Brief comparison of the two APIs

| Criterion | `completeExceptionally(Throwable)` | `CompletableFuture.failedFuture(Throwable)` |
|---|---|---|
| Method kind | Instance method | Static factory |
| Target object | An **existing** future | Creates a **new future** |
| Return value | `boolean`: whether this completion took effect | A `CompletableFuture<U>` already completed exceptionally |
| When to use | Callback reports error, data source arrives late, bridging external API | Error branch is already known at the moment an API returning a future is called |
| Future before the call | May be pending or already completed | No existing future is transitioned |
| Effect on existing completion | Does not change if future is already done | Does not touch any other future |
| Launches async work itself | No | No |
| When awaiting error result | `get()`/`join()` reports error per contract | Same |
| Effect on background task, side effects | Does not automatically cancel or roll back | No background task is launched by the factory |

Both APIs use the same `Throwable` type to represent errors, so the difference mainly lies in **future lifecycle and ownership**: marking an existing promise versus creating an already failed result.

## 5. Runnable Java 17 example: completing with failure and reading the error

Save the entire code as **`ExceptionalCompletionDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class ExceptionalCompletionDemo {
    private static void show(String name, CompletableFuture<?> future) {
        try {
            future.join();
            System.out.println(name + ": success");
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            System.out.println(name + ": "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<Integer> length = pending.thenApply(String::length);

        boolean first = pending.completeExceptionally(
                new IllegalStateException("service unavailable"));
        boolean lateSuccess = pending.complete("too late");

        System.out.println("first failure won: " + first);
        System.out.println("late success won: " + lateSuccess);
        show("pending", pending);
        show("dependent", length);

        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad request"));
        show("failed", failed);

        CompletableFuture<String> recovered =
                failed.exceptionally(ex -> "fallback");
        System.out.println("recovery: " + recovered.join());

        CompletableFuture<String> success =
                CompletableFuture.completedFuture("ready");
        System.out.println("overwrite success: "
                + success.completeExceptionally(
                        new IllegalStateException("ignored")));

        try {
            failed.get();
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            System.out.println("get cause: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac ExceptionalCompletionDemo.java
java ExceptionalCompletionDemo
~~~

**Exact standard output:**

~~~text
first failure won: true
late success won: false
pending: IllegalStateException: service unavailable
dependent: IllegalStateException: service unavailable
failed: IllegalArgumentException: bad request
recovery: fallback
overwrite success: false
get cause: IllegalArgumentException: bad request
~~~

Point-by-point explanation:

1. `pending` is initially incomplete, so `completeExceptionally` wins and returns `true`. The subsequent `complete("too late")` cannot change the result and returns `false`.
2. The stage `length = pending.thenApply(String::length)` was created before the failure. When the source completes exceptionally, `thenApply` does not invoke `String::length`, and the dependent stage also completes exceptionally. Calling `join()` on the dependent stage reports a `CompletionException` containing the original error cause.
3. `failedFuture` immediately creates a failed future with `IllegalArgumentException`, without scheduling any task.
4. `exceptionally` returns a **new stage** with the value `"fallback"`, while the `failed` future itself remains completed exceptionally.
5. `completedFuture("ready")` is already completed normally, so calling `completeExceptionally` afterward returns `false`.
6. `failed.get()` throws `ExecutionException` on the thread calling `get()`, and `getCause()` holds the original `IllegalArgumentException`.

No background thread is created in this example; that is intentional in order to verify completion semantics independently before introducing concurrency.

## 6. How do join(), get(), and getNow() report errors?

An exceptionally completed future **does not** cause the statement calling `failedFuture(...)` or `completeExceptionally(...)` to throw the underlying cause exception. The error is observed at the result-retrieval method.

| Retrieval method | Primary error type when computation fails | Checked exception in contract? |
|---|---|---|
| `join()` | `CompletionException` typically wrapping the cause via `getCause()` | No |
| `get()` | `ExecutionException` wrapping the cause via `getCause()` | Yes: also `InterruptedException` |
| `get(timeout, unit)` | `ExecutionException` if failed, `TimeoutException` if timed out | Yes |
| `getNow(valueIfAbsent)` | If not done, returns fallback; if done exceptionally, reports completion-style error | No |
| `isCompletedExceptionally()` | Only returns boolean, does not provide cause | No |

The `CancellationException` case has its own handling path. In particular, `join()` can throw `CancellationException` directly for a cancelled future. Do not claim that *every* exceptional completion only throws `CompletionException`.

**Reading the cause properly:**

~~~java
// Snippet inside a method, given CompletableFuture<String> future.
try {
    String result = future.join();
    consume(result);
} catch (java.util.concurrent.CancellationException ex) {
    handleCancellation(ex);
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    handleFailure(cause);
}
~~~

`consume`, `handleCancellation`, and `handleFailure` are illustrative functions that must be provided by the application. Similarly, with `get()`, you must catch `InterruptedException` and `ExecutionException` according to its contract.

**Do not classify errors based on the wrapper's `getMessage()` text** if the system needs to decide on retries or HTTP status mapping. Use the exception/cause type or an error code with a stable contract.

### Can a checked exception be used as the cause?

Yes. For example:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(new java.io.IOException("disk full"));
~~~

`IOException` is a checked exception, yet the factory does not declare `throws IOException` because it **only stores** the exception inside the future. A caller of `get()` receives `ExecutionException` and reads `getCause()`; a caller of `join()` sees the corresponding `CompletionException`. This passes error information through a result object rather than violating Java's checked exception checking rules.

## 7. Recovery and observation of dependent stages

Operators on `CompletableFuture` determine what happens after a stage fails.

### 7.1. exceptionally: turning a failure into a new success value

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("not found"));

CompletableFuture<String> fallback =
        source.exceptionally(ex -> "default");

System.out.println(fallback.join()); // default
~~~

`exceptionally` only runs on the failure branch. If the recovery callback returns a value, the **dependent stage** completes normally. If the recovery callback throws an exception, the dependent stage fails again. The original `source` future remains failed and will continue to report the error if `source.join()` is called.

### 7.2. handle: handling both value and error

~~~java
// Example inside a Java method.
CompletableFuture<Integer> normalized =
        CompletableFuture.<String>failedFuture(
                new IllegalStateException("unavailable"))
        .handle((value, error) -> error == null ? value.length() : -1);
~~~

`handle` receives one of two forms: the success value or the error; it can produce a different result type. Here `normalized.join()` returns `-1`. When the source completes normally with `null`, `error == null` still indicates normal completion; the application must account for whether `value` can be null before invoking methods on it.

### 7.3. whenComplete: observing without modifying failure state by default

~~~java
CompletableFuture<String> observed =
        CompletableFuture.<String>failedFuture(
                new IllegalArgumentException("bad"))
        .whenComplete((value, error) -> {
            if (error != null) {
                System.out.println("logged failure");
            }
        });
~~~

`whenComplete` is useful for logging, metrics, and tracing. If the source fails, the `observed` stage normally still completes with that error; it should not be treated as a recovery operation. If you want to turn a failure into a valid result, use `exceptionally` or `handle` and provide the fallback value.

### 7.4. thenApply, thenCompose, and propagation

- `thenApply` only transforms the value when the source stage succeeds; if the source fails, the function is not invoked and the error is surfaced on the dependent stage.
- `thenCompose` is used when the callback returns another `CompletionStage`, avoiding nested futures. Inside the callback, you can return `CompletableFuture.failedFuture(ex)` to represent a failed validation branch.
- `thenAccept` and `thenRun` also require the source to complete normally to execute their action normally.
- If a callback runs and throws an exception itself, the callback's stage can complete exceptionally even when the source stage succeeded.

Do not assume a dependent stage preserves the exact same **wrapper object** or stack trace in all cases. Rely on the exception/cause contract for classification rather than arbitrary reference identity comparisons.

## 8. Practical example: validate first, then return failedFuture

Suppose a public service always returns `CompletableFuture<User>`. If the input is invalid at call time, there is no need to wastefully schedule an executor task just to throw an exception on a background thread.

~~~java
// Java 17 snippet; User and repository types are application-defined.
CompletableFuture<User> findUser(String id) {
    if (id == null || id.isBlank()) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("user id required"));
    }
    return repository.findAsync(id);
}
~~~

The invalid branch returns **an already failed future**, so:

- The signature remains `CompletableFuture<User>` across all paths.
- Callers can attach `exceptionally`, `handle`, or use `get()`/`join()`.
- No new thread is created just to report a validation error.
- Callers cannot assume the error will be "thrown at the service call site" if the contract is designed to always return a future.

Distinguish between two different public contracts:

~~~java
// Contract 1: fail fast with a synchronous exception
CompletableFuture<User> a(String id) {
    if (id == null) {
        throw new IllegalArgumentException("id null");
    }
    return repository.findAsync(id);
}

// Contract 2: place the error into the future
CompletableFuture<User> b(String id) {
    if (id == null) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("id null"));
    }
    return repository.findAsync(id);
}
~~~

These are two **non-standalone illustrative snippets** assuming `User` and `repository` exist. Under Contract 1, a `try/catch` around `a(null)` catches the error immediately; under Contract 2, calling `b(null)` returns a future and the error only surfaces through the result-handling path. Both can be valid if documented consistently; switching between them in a released API can break caller behavior.

## 9. Practical example: callback completing an already created promise

`completeExceptionally` fits when an event arrives after the future has been created, such as wrapping a callback API, an event listener, or an I/O client callback.

~~~java
// Snippet inside a method; LegacyClient and Callback
// are application-defined abstractions.
CompletableFuture<String> fetchAsFuture(String key) {
    CompletableFuture<String> result = new CompletableFuture<>();

    legacyClient.fetch(key, new Callback() {
        @Override
        public void onSuccess(String value) {
            result.complete(value);
        }

        @Override
        public void onFailure(Throwable error) {
            result.completeExceptionally(error);
        }
    });

    return result;
}
~~~

When the callback reports failure, there is **an existing future waiting for a result**, so calling `completeExceptionally` is the right fit rather than creating a new `failedFuture` and abandoning the old promise. If the callback can be invoked multiple times or success/failure race, only the first completion wins; you can inspect the boolean to diagnose duplicate events:

~~~java
boolean accepted = result.completeExceptionally(error);
if (!accepted) {
    // Result was already finalized; log/measure the late callback error if needed.
}
~~~

**A common design mistake:**

~~~java
// Semantically wrong: creates a failed future and discards it.
legacyClient.fetch(key, new Callback() {
    @Override
    public void onFailure(Throwable error) {
        CompletableFuture.failedFuture(error); // Result is discarded.
    }
});
~~~

This snippet only illustrates a logic bug, not a standalone Java program. Anyone waiting on `result` may hang forever, because the new future has no relationship to `result` at all.

### What if registering the callback throws synchronously?

A real bridge must consider the case where `legacyClient.fetch(...)` throws before the callback is registered. If you want to uphold an "always return a future" contract, you can catch expected exceptions and call `result.completeExceptionally(ex)` to ensure the future does not hang. Do not catch `Throwable` too broadly and do not turn serious runtime errors into business errors by default; specify which types are allowed to be converted in the client contract.

## 10. completeExceptionally and completion races

In multithreaded code, `completeExceptionally` can race with `complete`, `cancel`, a timeout callback, or another result source.

~~~java
// Snippet inside a method.
CompletableFuture<String> promise = new CompletableFuture<>();
// Thread A:
boolean aWon = promise.complete("value");
// Thread B:
boolean bWon = promise.completeExceptionally(new RuntimeException("error"));
~~~

These are **two operations placed conceptually in two threads for illustration**, not two threads actually spawned by the code snippet. You cannot predict `aWon` and `bWon` from the code alone without synchronization ordering. One of the two normal completions is accepted; the other returns `false`.

This guarantee only covers **the future's result state**, not rolling back side effects already produced by both producers. For example, two sources writing to a database before calling `complete` can both cause side effects even though the future only accepts one result.

Helpful practices:

1. Establish a single clear owner with authority to complete the future whenever possible.
2. Check the boolean when callbacks arrive late, duplicate, or during timeout/cancellation.
3. Define a policy for tasks that already ran and produced side effects before the future was cancelled.
4. Do not use `isDone()` followed by `complete(...)` as an atomic check-then-write; another thread can complete between the two calls. Rely directly on the completion's boolean return value.
5. Keep meaningful `Throwable` error causes, including `cause` and task identifiers in logging.

## 11. Completion can run dependent actions on the calling thread

Neither `completeExceptionally` nor `failedFuture` schedules tasks on its own. However, when completing a future that has dependent stages, actions **without the `Async` suffix** are permitted to run on the thread completing the future or another thread participating in completion processing according to `CompletableFuture` rules.

Therefore, do not assume `completeExceptionally` always means "set a field and return immediately" in terms of runtime cost. In a real program, completion can trigger dependent actions and run observation or error-recovery work inline.

Distinguish:

- `exceptionally(fn)` is a non-Async stage in Java 17; the function may execute under non-async policy.
- `thenApplyAsync(fn, executor)` uses the provided executor for that action.
- `whenCompleteAsync(action, executor)` also schedules the callback via the executor.
- If the error is already present in a `failedFuture`, a non-async stage attached afterward may execute upon stage registration, not necessarily on a background worker.

**Note:** recovery or logging callbacks can throw errors. The original exceptionally completed future does not revert to pending; the callback's error is reflected on the dependent stage. Avoid placing hard-to-roll-back side effects inside callbacks unless ordering and ownership are clearly defined.

## 12. How does failedFuture differ from failedStage and completedFuture?

Related convenience factories:

| Factory | Return type | Initial state | Purpose |
|---|---|---|---|
| `CompletableFuture.completedFuture(value)` | `CompletableFuture<U>` | Normal with `value` | Value already available |
| `CompletableFuture.failedFuture(ex)` | `CompletableFuture<U>` | Exceptional with `ex` | Need to return an already failed CompletableFuture |
| `CompletableFuture.completedStage(value)` | `CompletionStage<U>` | Normal | Return a CompletionStage view |
| `CompletableFuture.failedStage(ex)` | `CompletionStage<U>` | Exceptional | API only wants to expose CompletionStage |

`failedFuture` and `failedStage` have existed since Java 9. The key API design point is the **return type**: `CompletionStage<T>` exposes stage composition operations, whereas `CompletableFuture<T>` additionally exposes completion/cancellation control operations.

If an API only wants callers to chain stages without actively completing an internal promise, consider a `CompletionStage<T>` public contract. However, changing the interface signature alone is not a security boundary or immutability guarantee; you still need to maintain data ownership and control the implementation.

**Do not confuse `failedFuture` with `supplyAsync(() -> { throw ex; })`.** The factory produces an immediately failed result without consuming a task on an executor. `supplyAsync` represents running a computation on the chosen executor, and the failure depends on when that computation executes.

## 13. How do cancellation and timeout differ from exceptional failure?

Cancellation in `CompletableFuture` is treated as a form of exceptional completion, but with distinct semantics:

~~~java
// Illustrative snippet inside a method.
CompletableFuture<String> task = new CompletableFuture<>();
boolean cancelled = task.cancel(true);
System.out.println(task.isCancelled()); // true
System.out.println(task.isCompletedExceptionally()); // true
~~~

For `CompletableFuture`, the `mayInterruptIfRunning` parameter of `cancel(boolean)` **is not used to control execution**, because `CompletableFuture` methods do not directly control a running computation. Therefore, **do not** infer that `cancel(true)` automatically stops a working thread or rolls back an already started transaction.

Timeout operations such as `orTimeout(...)` transition an incomplete future to exceptional completion with `TimeoutException` upon expiration; `completeOnTimeout(...)` attempts to complete normally with a fallback value. They can race with normal completion, so do not conclude the outcome solely from "having called timeout." A timeout also does not prove that external I/O has stopped or has not produced side effects.

Do not use `failedFuture(new TimeoutException(...))` as a replacement for timeout scheduling functionality: it only creates **an error result already known right now**. If you need expiration after a duration, choose the appropriate timeout API.

## 14. Catching the right error type, preserving cause, and not abandoning futures

### Controlling errors

Choose a semantically stable error type:

- `IllegalArgumentException` when API input is invalid.
- Domain/business exceptions if clients need to decide on retries, choose fallbacks, or display specific messages.
- `IOException` or another specific type preserved as the cause when the error originates from an external system.
- Avoid using a generic `RuntimeException` for every situation, as it loses the ability to classify errors.

`failedFuture` accepts `Throwable` directly; you do not need to wrap every checked exception in a `RuntimeException` just to pass it through a Future. When you want to change the public exception type, you can use an appropriate wrapper with `cause`:

~~~java
Throwable root = new java.io.IOException("connection lost");
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("fetch failed", root));
~~~

This snippet is an example inside a method; upon `get()`/`join()`, callers can trace back the cause chain.

### Tracking errors

If you create a failed future and discard it with no caller, stage, or logging mechanism observing it, the error may be silently ignored at the system level. Do not assume `failedFuture` or `completeExceptionally` will print a stack trace to stderr.

When developing a library, documentation should answer:

1. Can the method **throw synchronously** at call time, or does it always return a future?
2. Are input errors placed into `failedFuture` or thrown directly?
3. Which stage do computation errors come from, and how are they wrapped?
4. Should callers use `get()`, `join()`, `handle`, or `exceptionally`?
5. Does a running task stop when the future is cancelled or times out?
6. When an error occurs, to what extent has data state already been modified?

## 15. Common programming mistakes

1. **Using `completeExceptionally` like `throw`:** calling completion does not throw the cause directly into subsequent code; if you want to stop execution, you must `return`/`throw` or use separate control flow.
2. **Ignoring the boolean result:** a late error callback is rejected, yet the application still assumes it changed the caller's result.
3. **Calling `completeExceptionally` on a new future and returning a different one:** waiters on the original future may hang.
4. **Creating `failedFuture` without returning it or attaching stages:** the newly created failed future has no connection to the actual pipeline.
5. **Assuming `failedFuture` runs asynchronously:** it is just an already completed future; it creates no worker.
6. **Assuming `completeExceptionally` stops a running task:** completing the result is distinct from cancelling actual task execution.
7. **Using `exceptionally` for logging and accidentally turning an error into success:** the callback's return value becomes the success value of the recovery stage.
8. **Using `whenComplete` for recovery:** it primarily observes completion and does not replace a source error with success by default.
9. **Forgetting to unwrap `ExecutionException.getCause()`:** loses the underlying error type and conflates task failures with waiting-thread interruption.
10. **Treating every `join()` error as `CompletionException`:** a cancelled future can throw `CancellationException`.
11. **Using `isDone()` as a race guard:** checking then calling complete is not atomic; only the actual completion call determines the result.
12. **Changing an API from synchronous throw to `failedFuture` without notice:** callers with existing `try/catch` blocks may no longer handle errors as expected.
13. **Assuming a failed future automatically rolls back data:** exceptional completion is only a result state, not a transaction.
14. **Passing `null` as the `Throwable`:** both `completeExceptionally(null)` and `failedFuture(null)` are invalid.

## 16. Testing exceptional completion properly

Tests should observe both the **state** and the **error-reporting channel**:

| Scenario | What to verify |
|---|---|
| Pending future + `completeExceptionally(ex)` | Returns `true`; `isDone` and `isCompletedExceptionally` are true |
| Calling `complete(value)` after error | Returns `false`, initial error is not overwritten |
| Already succeeded future + `completeExceptionally(ex)` | Returns `false`; success result is preserved |
| `failedFuture(ex)` | Future immediately gets exceptional completion state, no executor needed |
| `get()` on failed future | `ExecutionException.getCause()` has the right type and cause |
| `join()` on failed future | `CompletionException` has the appropriate `cause` |
| `thenApply` on failed source | Transformation does not run; dependent stage fails |
| `exceptionally` / `handle` | Recovery stage has the right value; source stays in original state |
| `whenComplete` | Observes error without turning source into success |
| Two competing completion producers | Only one normal completion is accepted; do not assume order |
| Cancelled future | Distinguish cancellation from failed computation |
| Timeout vs. completion race | Only one result wins; external task/side effects checked independently |

Illustrative JUnit 5 example (standalone snippet requiring external JUnit dependency outside the JDK):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.*;

class ExceptionalFutureTest {
    @org.junit.jupiter.api.Test
    void firstCompletionWins() {
        CompletableFuture<String> future = new CompletableFuture<>();
        IllegalStateException cause = new IllegalStateException("failed");

        assertTrue(future.completeExceptionally(cause));
        assertFalse(future.complete("late"));
        assertTrue(future.isCompletedExceptionally());

        CompletionException thrown =
                assertThrows(CompletionException.class, future::join);
        assertSame(cause, thrown.getCause());
    }

    @org.junit.jupiter.api.Test
    void failedFutureCanBeRecovered() {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad"));
        assertTrue(failed.isCompletedExceptionally());
        assertEquals("fallback", failed.exceptionally(ex -> "fallback").join());
        assertTrue(failed.isCompletedExceptionally());
    }
}
~~~

This is **a test class** placed in a project structure supporting JUnit 5; it cannot be run with plain JDK `javac` alone without JUnit. Checking `assertSame(cause, thrown.getCause())` in the direct completion case helps catch incorrect wrappers/causes, while the recovery test ensures the failed source is not converted into success.

For concurrency tests, use `CountDownLatch` or an appropriate coordination mechanism to create contention; do not guess ordering with `Thread.sleep` and do not treat a single passing run as proof that a race is eliminated.

## 17. API selection checklist in real code

- **Is there already a future waiting for a callback/result?** Yes → use `completeExceptionally(ex)` to complete **that future** on failure.
- **No future yet and the error is already known?** Yes → use `CompletableFuture.failedFuture(ex)` as the return value.
- **Must the caller receive the cause?** Ensure the future/stage is consumed, preserving a clear `cause` and error type.
- **Need a fallback?** Use `exceptionally` or `handle`, distinguishing the new stage from the source.
- **Only need to log?** Use `whenComplete`, while keeping the source error propagating if the system needs to handle it.
- **Multiple competing producers?** Inspect the completion boolean, define an owner, and avoid uncoordinated side effects.
- **Timeouts or cancellation involved?** Use the appropriate timeout/cancel contract; do not equate future state with the actual task having stopped.
- **Changing how a public API reports errors?** Check compatibility with callers using synchronous `try/catch` and callers reading the future.
- **Verified data invariants after failure?** Do not use completion as a rollback mechanism.

## 18. Key takeaways

**`completeExceptionally(ex)`** exceptionally completes **an existing CompletableFuture** if it has not yet completed; it returns a boolean indicating whether the call won. **`CompletableFuture.failedFuture(ex)`** creates **a new CompletableFuture that is already failed**, suited for error return paths known upfront.

Both model failure in **an asynchronous result**, do not throw the cause on the thread creating the future, do not launch tasks, and do not roll back side effects. Consumers receive the cause via `get()`/`join()` or dependent stages, and can recover intentionally with `exceptionally`/`handle`. Proper design keeps the error channel, completion state, cancellation policy, and data state consistent with the API contract.

### References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java SE 17 — CancellationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html)

# `handle()`, `exceptionally()` and `whenComplete()` in CompletableFuture

A `CompletableFuture<T>` can complete normally (normal completion), complete exceptionally (exceptional completion), or remain incomplete. When building an asynchronous pipeline, it is important to distinguish between **handling errors for recovery** and **merely observing errors**. Three common methods of `CompletionStage`/`CompletableFuture` serve different goals:

- **`handle((value, error) -> newValue)`** runs **on both success and failure** and produces a **new result value**, which can change the type `T` to `U`. If the callback returns a normal value after an error, the dependent future has recovered.
- **`exceptionally(error -> fallback)`** runs only on **failure**, returning a **fallback of the same type `T`**. On success, the callback does not run and the dependent future receives the original success value.
- **`whenComplete((value, error) -> observe())`** runs on **both branches**, used for logging, recording metrics, monitoring, or cleanup. It is **not a recovery API**: if the callback returns normally, the dependent future preserves the upstream value or error.

Key point: **each method returns a new dependent stage**, without turning a failed upstream into a successful upstream. The outcome of a chain depends on where the handler is placed.

This article belongs to the **CompletableFuture** group of **general Java concurrency**, using Java SE 17+ and no Spring-specific APIs.

## 1. The CompletableFuture Outcome Model

`CompletableFuture<T>` has three observable states:

```text
           INCOMPLETE
                |
       +--------+---------+
       |                  |
  NORMAL(value)    EXCEPTIONAL(error)
       |                  |
  value can be null  error, cancellation,
                     error from continuation
```

Normal completion **can carry `null`**. Exceptional completion carries `Throwable` information or cancellation per the contract. `isDone()` being true does not mean the task succeeded; `isCompletedExceptionally()` also includes cancellation and failure cases from continuations.

Callbacks are triggered when **the source stage completes**. If the source has already completed before the callback is registered, the handler may be triggered immediately according to the corresponding execution policy; if not yet completed, the handler depends on when the source completes. There is no guarantee that a non-async callback always runs on the main thread.

## 2. Exact Comparison Table

| Property | `handle` | `exceptionally` | `whenComplete` |
| --- | --- | --- | --- |
| Runs on success | Yes | No | Yes |
| Runs on failure | Yes | Yes | Yes |
| Callback | `BiFunction<T,Throwable,U>` | `Function<Throwable,T>` | `BiConsumer<T,Throwable>` |
| Returns a value from callback | Yes | Yes | No |
| Dependent type | `CompletableFuture<U>` | `CompletableFuture<T>` | `CompletableFuture<T>` |
| Can recover from error | Yes | Yes | **Not intended** |
| When callback succeeds and source failed | Succeeds with U | Succeeds with fallback T | **Still fails** |
| Ideal use case | Transform both success/failure | Fallback on error | Logging, metrics, audit |

**Quick selection rule:** to replace the result on both branches, use `handle`; when you only need a fallback on error, use `exceptionally`; when you do not want to change the result and only want to observe, use `whenComplete`.

## 3. Method Signatures (Java SE 17)

```java
<U> CompletableFuture<U> handle(
        BiFunction<? super T, Throwable, ? extends U> fn);

CompletableFuture<T> exceptionally(
        Function<Throwable, ? extends T> fn);

CompletableFuture<T> whenComplete(
        BiConsumer<? super T, ? super Throwable> action);
```

These are **API signature excerpts**, not a standalone class. `handle` has a new type parameter `U`, whereas `exceptionally`/`whenComplete` keep `T`. `whenComplete` accepts a `BiConsumer`, so the callback **does not return a fallback**.

Import the necessary classes from `java.util.concurrent`. You can call the methods directly on `CompletableFuture` or via the `CompletionStage` interface; on the interface, the operations return `CompletionStage`.

## 4. `handle` on Success and Failure

Conceptual example:

```java
CompletableFuture<String> normalized =
        source.handle((value, error) -> {
            if (error != null) {
                return "FAILED";
            }
            return "VALUE:" + value;
        });
```

This illustrative snippet assumes `source` is a `CompletableFuture<Integer>`.

- Success 15 → dependent succeeds with `"VALUE:15"`.
- Failure E → dependent succeeds with `"FAILED"` if the callback does not throw.
- If the callback itself throws F → dependent fails with F.
- Source keeps its original outcome in all cases.

`handle` can convert `CompletableFuture<Integer>` into `CompletableFuture<String>` or into an object describing `Result<T>`. However, if you only want a fallback on error, `exceptionally` is simpler because you do not need to write logic for the success case.

## 5. `exceptionally` Only Handles Errors

Example:

```java
CompletableFuture<Integer> safe =
        source.exceptionally(error -> -1);
```

This illustrative snippet assumes `source` has type `CompletableFuture<Integer>`.

- Success 15 → `safe` succeeds with 15; the lambda **does not run**.
- Failure E → the lambda runs and returns -1; `safe` succeeds with -1.
- Lambda throws → `safe` remains exceptional.

**Recovery is a business decision**: for a failed cache read, an empty value may be acceptable; for a payment, returning `true` on a network error would produce false information. You should not use `exceptionally(e -> null)` for all errors if `null` will later be interpreted as valid data.

## 6. `whenComplete` Observes While Preserving Outcome

`whenComplete` is suitable for statistics and monitoring:

```java
CompletableFuture<Integer> observed =
        source.whenComplete((value, error) -> {
            if (error == null) {
                recordSuccess(value);
            } else {
                recordFailure(error);
            }
        });
```

This is an illustrative snippet; `recordSuccess`/`recordFailure` belong to the application.

- Success 15 + callback returns normally → dependent succeeds with 15.
- Failure E + callback returns normally → dependent **fails with E**.
- Callback itself throws an error → exception precedence rules apply, as covered later.

**Logging an exception is not catching/recovering from it.** If downstream stages need a fallback, you must add `exceptionally` or `handle` at the appropriate position.

## 7. Java 17+ Example: Comparing All Three Methods

Save as `ThreeHandlersDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThreeHandlersDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> ok =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> bad =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad"));

        String handledOk = ok.handle(
                (v, e) -> e == null ? "OK:" + v : "FAIL").join();
        String handledBad = bad.handle(
                (v, e) -> e == null ? "OK:" + v : "FAIL").join();

        int normal = ok.exceptionally(e -> -1).join();
        int fallback = bad.exceptionally(e -> -1).join();

        AtomicBoolean observedError = new AtomicBoolean();
        CompletableFuture<Integer> watched =
                bad.whenComplete((v, e) ->
                        observedError.set(e != null));

        System.out.println("Handle success: " + handledOk);
        System.out.println("Handle failure: " + handledBad);
        System.out.println("Exceptionally success: " + normal);
        System.out.println("Exceptionally failure: " + fallback);
        System.out.println("Observed error: " + observedError.get());
        System.out.println("Observer recovered: "
                + !watched.isCompletedExceptionally());
    }
}
```

Compile and run:

```bash
javac ThreeHandlersDemo.java
java ThreeHandlersDemo
```

Exact stdout:

```text
Handle success: OK:7
Handle failure: FAIL
Exceptionally success: 7
Exceptionally failure: -1
Observed error: true
Observer recovered: false
```

Both sources are already completed before registering the handlers, so the result does not depend on thread scheduling. `watched` remains exceptional even though the observer saw the error.

## 8. Outcome Matrix: Understanding the Dependent Stage

| Upstream | Handler | Dependent (if callback does not throw) |
| --- | --- | --- |
| Success 5 | `handle((v,e)->v+1)` | Success 6 |
| Failure E | `handle((v,e)->0)` | Success 0 |
| Success 5 | `exceptionally(e->0)` | Success 5 |
| Failure E | `exceptionally(e->0)` | Success 0 |
| Success 5 | `whenComplete(log)` | Success 5 |
| Failure E | `whenComplete(log)` | **Failure E** |

None of the three methods automatically retries the original operation. A handler typically **transforms the outcome** of the source into the outcome of the dependent; if you want retries, you need to design a new async operation with deadlines, idempotency, cancellation, and a retry limit.

## 9. Success With a Null Value: A Common Check Mistake

If the source completes normally with `null`:

```java
CompletableFuture<String> empty =
        CompletableFuture.completedFuture(null);

String answer = empty.handle((value, error) ->
        error == null ? "NORMAL" : "FAILED").join();
```

`answer` is `"NORMAL"`, not `"FAILED"`.

Therefore, do not branch on `value == null` to guess whether an error occurred. `handle`/`whenComplete` must check **`error != null`**. `CompletableFuture<Void>` (typically from `runAsync`/`thenRun`) makes this even clearer: the normal value is `null`.

If the business contract does not allow `null`, perform validation separately using `thenApply` or logic inside `handle`, rather than equating the framework's normal completion with business validation.

## 10. Java 17+ Example: Null Is Still a Normal Outcome

Save as `NullCompletionDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class NullCompletionDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture(null);

        String handled = source.handle((v, e) ->
                e == null ? "NORMAL_NULL" : "ERROR").join();

        String fallback = source.exceptionally(
                e -> "fallback").join();

        String observed = source.whenComplete(
                (v, e) -> {
                    if (e != null) {
                        throw new AssertionError("unexpected");
                    }
                }).join();

        System.out.println("Handle: " + handled);
        System.out.println("Exceptionally kept null: "
                + (fallback == null));
        System.out.println("WhenComplete kept null: "
                + (observed == null));
    }
}
```

```bash
javac NullCompletionDemo.java
java NullCompletionDemo
```

Exact stdout:

```text
Handle: NORMAL_NULL
Exceptionally kept null: true
WhenComplete kept null: true
```

`exceptionally` is skipped because there is no exception, even though the value is `null`.

## 11. Exception Propagation Along a Chain

The `thenApply`/`thenAccept`/`thenRun` family of methods only runs its callback when the upstream **completes normally**. If the upstream is exceptional, its dependent receives the failure without **running the normal-only callback**.

```text
source success -> thenApply(validate) ---- throws E
                                      |
                                      v
                       thenApply(enrich) [skipped]
                                      |
                                      v
                          exceptionally(fallback)
                                      |
                                      v
                         thenApply(render) [runs]
```

When `exceptionally` completes normally with a fallback, the subsequent `thenApply` treats the fallback as normal input. Therefore, where you place error handling matters: a handler **placed before** a failing stage does not handle errors **produced after** it.

## 12. Java 17+ Example: Placing Recovery in the Right Position

Save as `HandlerPositionDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class HandlerPositionDemo {
    public static void main(String[] args) {
        AtomicBoolean skipped = new AtomicBoolean();

        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(10);

        CompletableFuture<Integer> invalid =
                source.thenApply(n -> {
                    throw new IllegalArgumentException("invalid");
                });

        int result = invalid
                .thenApply(n -> {
                    skipped.set(true);
                    return n + 1;
                })
                .exceptionally(error -> 40)
                .thenApply(n -> n + 2)
                .join();

        CompletableFuture<Integer> lateFailure =
                source.exceptionally(error -> 99)
                      .thenApply(n -> {
                          throw new IllegalStateException("late");
                      });

        System.out.println("Recovered: " + result);
        System.out.println("Skipped normal callback: "
                + !skipped.get());
        System.out.println("Late failure remains: "
                + lateFailure.isCompletedExceptionally());
    }
}
```

```bash
javac HandlerPositionDemo.java
java HandlerPositionDemo
```

Exact stdout:

```text
Recovered: 42
Skipped normal callback: true
Late failure remains: true
```

The error from `invalid` causes the next `thenApply` not to run. `exceptionally` recovers with 40, and the subsequent stage adds 2. In the other branch, `exceptionally` sits **before** the failing stage, so it cannot fix an error that has not happened yet.

## 13. `handle` Changing the Result Type T → U

`handle` is a natural choice when you want to unify both success data and errors into a single **domain result**:

```java
record Outcome<T>(T value, Throwable error) {
    boolean success() {
        return error == null;
    }
}

CompletableFuture<Integer> source = ...;
CompletableFuture<Outcome<Integer>> result =
        source.handle(Outcome::new);
```

This is an illustrative Java 17 snippet without a `main` class. When the source is exceptional, the dependent can complete normally with an `Outcome` containing the error; this **does not mean the upstream has been fixed**.

Advantage: downstream APIs can receive an explicit status object. Drawback: if the caller forgets to check `error`, it may accidentally treat a failure as a success. If you want a stronger error type, you can use a `sealed interface Result<T>` depending on your application design.

`exceptionally` does not change type `T` to `U`: it returns a fallback compatible with the original type. `whenComplete` does not produce a value from its callback.

## 14. Exceptions Thrown by the Callback Itself

All three continuations can produce a new exception:

- `handle` callback throws F → dependent stage **fails with F**, even if the source succeeded.
- `exceptionally` callback throws F while handling an error → dependent **fails with F**, without automatically falling back again.
- `whenComplete` callback throws F → you must also consider the **source** outcome to determine which exception takes precedence.

If you want to preserve an original cause when rethrowing, wrap it with the cause rather than creating a bare `new RuntimeException("failed")` without a cause. Also do not catch every `Throwable` and turn it into `null`, as that can hide programming errors or cancellation.

## 15. Exception Precedence Rules for `whenComplete`

Java's `CompletionStage` specifies this explicitly:

1. Source **succeeds** + observer returns → dependent **succeeds**, keeping the original value.
2. Source **succeeds** + observer throws F → dependent **fails with F**.
3. Source **fails with E** + observer returns → dependent **fails with E**.
4. Source **fails with E** + observer throws F → dependent **gives precedence to failure E** over F.

Diagram:

```text
source SUCCESS ---- whenComplete OK ----> SUCCESS original value
        |                |
        +---- observer throws F --------> FAILURE F

source FAILURE E -- whenComplete OK ----> FAILURE E
        |
        +---- observer throws F --------> FAILURE E (preferred)
```

Do not assume the observer's exception is necessarily added to suppressed exceptions. The general contract only guarantees **preferring the source exception** when both fail.

A logging callback can turn a pipeline into a **new** failure when the source actually succeeded. Therefore, observers should be short, controlled, and not throw unexpectedly.

## 16. Java 17+ Example: Source Error Takes Precedence

Save as `WhenCompletePrecedenceDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class WhenCompletePrecedenceDemo {
    static String cause(CompletableFuture<?> stage) {
        try {
            stage.join();
            return "NONE";
        } catch (CompletionException e) {
            return e.getCause().getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("ok");

        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("original"));

        CompletableFuture<String> observerFailure =
                ok.whenComplete((v, e) -> {
                    throw new IllegalStateException("observer");
                });

        CompletableFuture<String> bothFailed =
                failed.whenComplete((v, e) -> {
                    throw new IllegalStateException("observer");
                });

        System.out.println("Success + observer throws: "
                + cause(observerFailure));
        System.out.println("Failure + observer throws: "
                + cause(bothFailed));
    }
}
```

```bash
javac WhenCompletePrecedenceDemo.java
java WhenCompletePrecedenceDemo
```

Exact stdout:

```text
Success + observer throws: IllegalStateException
Failure + observer throws: IllegalArgumentException
```

The code inspects the cause of `CompletionException` from the dependent stage rather than inferring the result from logging order. This is an important case to understand when placing `whenComplete` at the end of a pipeline and the callback itself fails.

## 17. `join()` and `get()` When a Future Is Exceptional

`CompletableFuture.join()` is convenient in pipelines because it uses unchecked exceptions: for a normal exceptional completion it throws `CompletionException` with the original cause; cancellation can be reported via `CancellationException`.

`get()`, following the `Future` contract, throws checked `InterruptedException` and `ExecutionException` on failure; `get(timeout, unit)` also throws `TimeoutException`.

A dependent callback may receive a `Throwable` that is already a `CompletionException`, rather than the business exception directly. Illustrative helper:

```java
static Throwable unwrap(Throwable error) {
    if (error instanceof java.util.concurrent.CompletionException ce
            && ce.getCause() != null) {
        return ce.getCause();
    }
    return error;
}
```

This is an illustrative Java 17 method; it unwraps **one layer** and preserves the cause. Do not blindly unwrap all layers and lose context needed for diagnostics.

## 18. Cancellation Is Also an Exceptional Outcome

Per Java SE 17, `CompletableFuture.cancel(boolean)` completes a not-yet-done future with `CancellationException`. The `mayInterruptIfRunning` parameter **is not used to control the underlying computation** of `CompletableFuture`.

Consequences:

- `handle` can see the `Throwable` representing cancellation.
- `exceptionally` can turn cancellation into a normal fallback on the **dependent stage**.
- `whenComplete` only records cancellation and normally preserves the exceptional outcome.
- Dependent recovery **does not change `isCancelled()` of the source**.
- You should not apply a fallback for every cancellation if callers need to respect cancellation requests.

Canceling a `CompletableFuture` does not prove that an I/O task was interrupted, side effects were rolled back, or a worker finished cleanup. That is a separate lifecycle contract.

## 19. Java 17+ Example: Observer Does Not Clear Cancellation

Save as `CancellationHandlersDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancellationHandlersDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                new CompletableFuture<>();

        AtomicBoolean seen = new AtomicBoolean();
        CompletableFuture<Integer> observed =
                source.whenComplete((v, e) -> seen.set(e != null));
        CompletableFuture<Integer> fallback =
                observed.exceptionally(e -> -99);

        boolean canceled = source.cancel(true);

        System.out.println("Source canceled: " + canceled);
        System.out.println("Observed error: " + seen.get());
        System.out.println("Observed still exceptional: "
                + observed.isCompletedExceptionally());
        System.out.println("Fallback result: " + fallback.join());
        System.out.println("Source isCancelled: "
                + source.isCancelled());
    }
}
```

```bash
javac CancellationHandlersDemo.java
java CancellationHandlersDemo
```

Exact stdout:

```text
Source canceled: true
Observed error: true
Observed still exceptional: true
Fallback result: -99
Source isCancelled: true
```

There is no real worker in this example, so it makes no promises about interrupting a running task. It only demonstrates the **state of the source** and the **state of the dependent stages**.

## 20. Async Variants: Who Runs the Callback?

Non-`Async` methods do not guarantee running on a specific thread. The callback may be executed by the thread completing the source or another thread participating in completion according to JDK policy.

The variants:

```java
source.handleAsync(fn, executor);
source.whenCompleteAsync(action, executor);
source.exceptionallyAsync(recoveryFn, executor);
```

This is an illustrative Java 17 snippet with variables declared elsewhere.

- `...Async` chooses the **execution facility for the callback**, without moving the upstream computation to that executor.
- If no executor is passed, `CompletableFuture`'s default async facility typically uses `ForkJoinPool.commonPool()` per the contract (with exceptions noted in the Javadoc).
- An async callback can still block; `Async` does not mean non-blocking.
- An executor can reject work when shut down or overloaded, making the dependent exceptional.
- A slow logging callback can hold an executor worker, increasing tail latency.

Use a dedicated executor when you need to isolate heavy callbacks; manage bounded queues, shutdown, and rejection policies appropriately.

## 21. Java 17+ Example: Explicitly Specified Executor

Save as `AsyncHandlerDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncHandlerDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "named-worker"));
        AtomicReference<String> threadName =
                new AtomicReference<>();

        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.completedFuture(10);

            int handled = source.handleAsync(
                    (value, error) -> value * 2,
                    executor).join();

            int observed = source.whenCompleteAsync(
                    (value, error) ->
                            threadName.set(
                                    Thread.currentThread().getName()),
                    executor).join();

            System.out.println("Handled: " + handled);
            System.out.println("Observer thread: " + threadName.get());
            System.out.println("Original: " + observed);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac AsyncHandlerDemo.java
java AsyncHandlerDemo
```

Exact stdout on the normal path:

```text
Handled: 20
Observer thread: named-worker
Original: 10
```

`main`'s `join()` waits for the callbacks before printing. The thread name is deterministic because the executor is configured to create threads with that name. Do not infer in reverse that non-async callbacks always run on `main`.

## 22. `exceptionallyCompose` When the Fallback Is Also Asynchronous

`exceptionally` requires the callback to return **`T`**, not another future. If recovery needs to call another asynchronous service, Java 17 provides `exceptionallyCompose`:

```java
CompletableFuture<String> recovered =
        source.exceptionallyCompose(error ->
                fetchBackupAsync());
```

This is an illustrative snippet; `fetchBackupAsync` returns an appropriate `CompletionStage<String>`.

Java 17 also provides `exceptionallyAsync` and `exceptionallyComposeAsync` to choose the execution facility. Distinctions:

- `exceptionally`: fallback **`T`**.
- `exceptionallyAsync`: fallback **`T`**, but the callback is scheduled asynchronously.
- `exceptionallyCompose`: fallback **`CompletionStage<T>`**, and the dependent follows the async result of that stage.

Do not write `source.exceptionally(e -> fetchBackupAsync())` when `source` is `CompletableFuture<String>`: the types do not match. Also do not use `handle` with a callback returning `CompletableFuture<T>` and forget to flatten it, as you will end up with a nested future if you do not compose.

## 23. Placing the Observer Before or After Recovery?

The two pipelines have different metric meanings:

```text
source
  |
whenComplete(logOriginalOutcome)
  |
exceptionally(fallback)
  |
whenComplete(logFinalOutcome)
  |
join/get
```

- The first observer sees the **original failure**.
- `exceptionally` can recover into a normal fallback.
- The last observer sees the **recovered success**, no longer knowing the old error unless separate context is kept.
- The source still retains its exceptional completion.

If you only place `whenComplete` **after recovery**, failure metrics may be lost. Conversely, if you log at every stage, the same error can produce duplicate stack traces and overhead.

Note: to guarantee the dependency relationship, the stages must be **chained together** as shown in the diagram. An independent observation branch does not automatically guarantee the callback runs before recovery on another branch.

## 24. Java 17+ Example: Recording Original Error and Recovered Success

Save as `RecoveryTelemetryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class RecoveryTelemetryDemo {
    public static void main(String[] args) {
        AtomicBoolean originalError = new AtomicBoolean();
        AtomicBoolean recoveredSuccess = new AtomicBoolean();

        CompletableFuture<Integer> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("temporary"));

        int result = source
                .whenComplete((v, e) ->
                        originalError.set(e != null))
                .exceptionally(e -> 12)
                .whenComplete((v, e) ->
                        recoveredSuccess.set(
                                e == null && v == 12))
                .join();

        System.out.println("Original failed: "
                + originalError.get());
        System.out.println("Recovered value: " + result);
        System.out.println("Final succeeded: "
                + recoveredSuccess.get());
        System.out.println("Source still failed: "
                + source.isCompletedExceptionally());
    }
}
```

```bash
javac RecoveryTelemetryDemo.java
java RecoveryTelemetryDemo
```

Exact stdout:

```text
Original failed: true
Recovered value: 12
Final succeeded: true
Source still failed: true
```

A stage that recovers successfully **does not overwrite the source**. This is also why logs and metrics need to be placed at the right points in the pipeline.

## 25. Anti-Patterns to Avoid

**1. "We logged the exception in `whenComplete`, so the error is caught."** False; the dependent remains exceptional unless the callback produces a new error that takes precedence by the rules.

**2. "`exceptionally` always runs."** False; it skips normal completions.

**3. "`handle` is only for logging."** No. It produces a new outcome, can change the type, and can recover.

**4. "`whenComplete` returns a fallback value."** No. The callback returns `void`.

**5. "`value == null` indicates failure."** False. A normal result can be `null`.

**6. "`exceptionally` recovers from errors in later stages."** No. It only sees errors that have reached its input stage.

**7. "A `whenComplete` callback throwing does not affect the pipeline."** False when the upstream succeeded; the dependent will fail.

**8. "If the source fails with E and the observer throws F, the dependent always fails with F."** False; E takes precedence.

**9. "Recovery makes `source.isCompletedExceptionally()` false."** False. The dependent is a different future.

**10. "`handleAsync` always moves the source task to a new executor."** False; it schedules the callback.

**11. "Cancellation should always recover to 0."** No. That is a policy that can hide cancellation requests.

**12. "Callbacks always receive the unwrapped business exception."** No. They may receive a `CompletionException`.

**13. "`join` and `get` have the same checked exceptions."** False. `get` has `ExecutionException` and `InterruptedException`.

**14. "Using long-blocking callbacks does not affect concurrency."** False; it can hold the completion or executor thread.

**15. "`exceptionally` returns `CompletableFuture<T>` like `exceptionallyCompose`."** False; it returns a value `T`.

**16. "Every error must be turned into a default success."** No. You need to classify recoverable, fatal, and cancellation cases per the business contract.

## 26. Production Review Checklist

1. **Which stages can fail?** Source, validation, transformation, executor rejection, timeout, or cancellation?
2. **Which stage is the handler placed after?** It cannot handle errors that occur later.
3. **Do you need observation or recovery?** `whenComplete` differs from `exceptionally`/`handle`.
4. **Do you need to convert `T` to `U`?** Use `handle` if you must process both outcomes.
5. **Can success be `null`?** Do not infer failure from `value == null`.
6. **Does the fallback have clear business meaning?** Do not create "false successes".
7. **Can the observer throw or block?** Control logging and cleanup.
8. **Is the error source being masked by recovery?** Place telemetry before the fallback if needed.
9. **Is cancellation possible?** Do not silently swallow cancellation requests.
10. **Are exception wrappers handled properly?** Preserve the cause and stack trace.
11. **Which executor do async callbacks use?** Define ownership and shutdown.
12. **Do multiple branches share the same source?** Recovery on one branch does not fix other branches.
13. **Are callbacks that throw tested?** Verify `whenComplete` precedence rules.
14. **Are `null` and `Void` tested?**
15. **Are success and failure tested at different callback registration times?**
16. **Are tests independent of `Thread.sleep` or flaky timestamps?** Use completed/failed futures and `join`/`get(timeout)`.
17. **Are there external side effects requiring idempotency?** Handlers do not automatically provide transactions or safe retries.
18. **Does the caller use `join()` or `get()`?** Document the appropriate exception contract.

## 27. Self-Check Questions

**Question 1.** What does `completedFuture(5).exceptionally(e -> 10).join()` return?

**5**, because success does not trigger the exception handler.

**Question 2.** The source fails, and `handle((v,e)->0)` returns 0 normally. Is the dependent still exceptional?

**No**, the dependent completes normally with 0; the source remains exceptional.

**Question 3.** The source fails, and `whenComplete` logs and returns. Does the dependent clear the error?

**No**, the source error is still propagated.

**Question 4.** What happens if `whenComplete` throws when the source succeeded?

The dependent fails due to the observer's error.

**Question 5.** The source fails with E and the observer also throws F; which does the dependent prioritize?

**E**, per the `CompletionStage` contract.

**Question 6.** Can `handle` convert `CompletableFuture<Integer>` to `CompletableFuture<String>`?

**Yes**; the callback returns `String`.

**Question 7.** Is it true that `exceptionally` returns another asynchronous stage?

No; use `exceptionallyCompose` when the callback needs to return a `CompletionStage<T>`.

**Question 8.** Is `handle((v,e) -> v==null ? "failed" : "ok")` safe when `null` is a valid value?

No. You must check `e != null` to detect exceptional completion.

**Question 9.** Does `exceptionally` before `thenApply` handle errors created by `thenApply`?

No. The error occurs downstream of the handler.

**Question 10.** Does `CompletableFuture`'s `cancel(true)` guarantee interrupting the worker?

No. It is an exceptional state of the future per the contract, not a guarantee of controlling the underlying computation.

**Question 11.** After a successful fallback, what does the final observer see?

The recovered normal result; to log the original error, you must observe the upstream **before** recovery or keep separate context.

**Question 12.** Do `get()` and `join()` have the same exception contract?

No. `get` per `Future` has checked exceptions; `join` typically uses unchecked `CompletionException`.

## 28. Summary

- **`handle`:** both success/failure → produces a new value, can change type and recover.
- **`exceptionally`:** failure only → returns a fallback of the same type; leaves normal results untouched.
- **`whenComplete`:** both success/failure → observes the outcome, **does not recover**, preserves the original result/error if the observer returns normally.
- **Exception precedence:** an observer throwing when the upstream succeeds makes the dependent fail; if the upstream also failed, the upstream error takes precedence.
- **Null normal result** is valid; branch on `Throwable`, not on a `null` value.
- **Continuation order** determines who sees an error; early recovery turns subsequent stages into normal flow.
- **Async variants** select the execution facility for the callback; they do not change the source's worker.
- **Cancellation** also has `CompletableFuture` exceptional semantics; a fallback does not automatically stop the computation.
- **Source and dependent are different stages**; recovery does not overwrite the source or other branches.

Mnemonic: **`handle` = "I decide the outcome anew"; `exceptionally` = "only on error do I return a fallback"; `whenComplete` = "I observe, without modifying the outcome"**.

**Official references:** [CompletableFuture — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) and [CompletionStage — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html).

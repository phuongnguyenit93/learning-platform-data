# exceptionally(), handle(), and whenComplete() in CompletableFuture and Spring @Async

When writing concurrent programs with Spring Framework, an `@Async` method can return `CompletableFuture<T>` so the caller can receive the result later or chain processing steps. However, tasks can fail: a database query fails, an external service times out, parameters are invalid, or a callback in the pipeline throws an exception itself. Three APIs—**`exceptionally()`**, **`handle()`**, and **`whenComplete()`**—address three distinct needs: **error recovery**, **transforming outcomes regardless of success or failure**, and **observing results while preserving completion state**.

The most important point: all three APIs create **a new dependent completion stage**. They do not mutate the result of the original stage itself. The order in which callbacks are attached determines whether a callback sees the result **before** or **after** error recovery. This lesson belongs to the **Exception Handling** group, focusing on Java 17+ contracts and usage in Spring `@Async` applications.

## 1. What should you master?

After this lesson, you will be able to:

- Explain how `CompletableFuture` completes normally, completes exceptionally, or is cancelled, and how exceptions are stored/propagated across stages.
- Precisely distinguish execution timing, callback types, return types, and recovery capability across `exceptionally`, `handle`, and `whenComplete`.
- Choose the right API for retries/fallbacks, result type conversion, logging/metrics, or preserving errors for upper layers to decide.
- Understand what happens when a callback throws an exception itself, especially **`whenComplete`'s rule prioritizing the original error** when the source already failed.
- Know that callbacks without the `Async` suffix may run on the thread completing the stage or the thread attaching the callback, with no guarantee of a new worker.
- Compare `get()`, `join()`, `ExecutionException`, `CompletionException`, and `CancellationException`.
- Use them in Spring `@Async` with `ThreadPoolTaskExecutor`, distinguishing **in-task errors** from **task submission rejections**.
- Avoid swallowing errors, business-invalid fallbacks, duplicate logging, blocking callbacks, lost thread context, and incorrect assumptions about cancellation/timeout.
- Run a Java 17+ example with deterministic output and write tests without relying on `Thread.sleep()`.

## 2. Foundation: CompletionStage and three terminal states

`CompletableFuture<T>` implements both `Future<T>` and `CompletionStage<T>`. Initially a Future may be incomplete; when it terminates, it can:

1. **Complete normally:** hold a value `T`; this value **may be `null`**.
2. **Complete exceptionally:** hold a failure cause, such as `IllegalArgumentException` or `IOException` wrapped at the appropriate level.
3. **Be cancelled:** calling `cancel(...)` on a `CompletableFuture` essentially leads to a form of exceptional completion with `CancellationException`.

A stage can finish normally or exceptionally while another stage is waiting on it:

~~~text
CompletableFuture<T> source
       |
       +--- completed normally (value T)
       |
       +--- completed exceptionally (Throwable)
       |
       +--- cancelled (CancellationException)
       |
       +--- dependent stage: callback depending on type
                |
                +--- completed normally (T/U)
                |
                +--- completed exceptionally (old/new cause)
~~~

A dependent stage created with `thenApply` typically executes only when the source **succeeds**. If the source fails, the value-processing callback does not run; the error can propagate through the pipeline. The three methods in this topic help explicitly define how the application handles or observes errors.

### Two principles before writing callbacks

- **A `null` result does not mean failure.** With `handle((value, error) -> ...)` or `whenComplete((value, error) -> ...)`, check `error == null` to tell whether the source succeeded, rather than checking `value == null` alone.
- **The original stage and the new stage are distinct.** `CompletableFuture<Integer> recovered = source.exceptionally(...)` does not “fix” `source`; `source` can still complete exceptionally while `recovered` succeeds with the fallback.

## 3. The most important comparison table

| Criterion | `exceptionally(fn)` | `handle(fn)` | `whenComplete(action)` |
| --- | --- | --- | --- |
| When is the callback invoked? | Only when the source completes **exceptionally** | Both success and failure | Both success and failure |
| Callback functional interface | `Function<Throwable, ? extends T>` | `BiFunction<? super T, Throwable, ? extends U>` | `BiConsumer<? super T, ? super Throwable>` |
| Data received by callback | Exception | Value or `null`, plus exception or `null` | Value or `null`, plus exception or `null` |
| Does the callback return a value? | Yes, must match type `T` | Yes, allows converting to type `U` | No, only performs side effects |
| New stage when source fails and callback returns normally | **Succeeds with fallback** | **Succeeds with new value** | **Still fails like the source** |
| New stage when source succeeds | Preserves source value; callback does not run | Result computed by callback | Preserves source value if action does not throw |
| Can it change type `T -> U`? | No, same type `T` | Yes | No, same type `T` |
| Can it merely observe errors without “swallowing” them? | Not naturally; must rethrow | Possible, though semantics easily shift if returning fallback | **Yes, the best fit** |
| If the callback throws an error itself | New stage fails with callback's error | New stage fails with callback's error | If source succeeded, new stage fails with callback's error; if source already failed, source error takes precedence |
| Primary purpose | Error recovery/fallback | Combining success/failure, mapping results | Logging, metrics, tracing, lightweight cleanup |

**Rule of thumb:** `exceptionally` is like a `catch` branch returning a replacement value; `handle` is like a `try/catch` computing a final value on **every path**; `whenComplete` is like a `finally` observation callback, yet **not identical to Java's `finally` in every aspect**: if the observer itself fails on the success path, the new stage fails too.

## 4. exceptionally(): runs only on the failure path

Signature in `CompletableFuture<T>`:

~~~java
public CompletableFuture<T> exceptionally(
        java.util.function.Function<Throwable, ? extends T> fn)
~~~

If the source stage succeeds, `fn` **does not run** and the new stage receives the same value. If the source fails (including cancellation), `fn` runs with the completion `Throwable` and returns a replacement value of the same type `T`. When the callback finishes normally, **the new stage becomes successful**, no longer holding the previous failure state.

Java 17 example:

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));

CompletableFuture<String> fallback =
        source.exceptionally(error -> "cached-value");

System.out.println(fallback.join());             // cached-value
System.out.println(source.isCompletedExceptionally()); // true
~~~

This is a **Java snippet that can be placed in a method with `import java.util.concurrent.CompletableFuture;`**. It shows recovery happens only on `fallback`, while `source` remains failed. If the exception handler throws an exception itself, the `fallback` stage also terminates exceptionally.

### Only fall back when the cause is recoverable

A common anti-pattern:

~~~java
CompletableFuture<Order> safe =
        loadOrder(id).exceptionally(error -> new Order());
~~~

This is an **illustrative non-standalone snippet**, where `Order`/`loadOrder` are application components. If the error is a lost DB connection, missing order information, programming bug, or security failure, returning an empty order can mislead the rest of the system. Identify which error types are recoverable:

~~~java
CompletableFuture<Price> safe =
        priceClient.fetch(sku).exceptionally(error -> {
            Throwable cause = unwrapCompletion(error);
            if (cause instanceof PriceServiceUnavailableException) {
                return priceCache.getIfPresent(sku);
            }
            throw new java.util.concurrent.CompletionException(cause);
        });
~~~

This is an **application design illustration**, requiring definitions for `Price`, `PriceServiceUnavailableException`, `priceClient`, `priceCache`, and the `unwrapCompletion` helper. A cache fallback can also return `null`; define a clear business policy for cache misses. Never automatically turn every exception into a default value.

### Error recovery ordering

~~~java
CompletableFuture<Integer> recovered =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("bad"))
                .exceptionally(error -> 5)
                .thenApply(value -> value * 2);
~~~

`recovered.join()` equals **10** because `exceptionally` turns the error into `5`, after which `thenApply` can run. However, if `thenApply` is placed **before** `exceptionally`, when the source fails `thenApply` is skipped and the fallback is the value returned directly by `exceptionally`, without doubling.

## 5. handle(): handles both success and failure and allows type conversion

Typical signature:

~~~java
public <U> CompletableFuture<U> handle(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn)
~~~

`handle` always receives either the source's result or its error and can return a value of **type `U`**, making it well-suited to producing a **Result object**, converting values into status messages, or applying fallback rules across both paths.

Example:

~~~java
CompletableFuture<Integer> number =
        CompletableFuture.completedFuture(42);

CompletableFuture<String> result =
        number.handle((value, error) -> {
            if (error != null) {
                return "failed";
            }
            return "value=" + value;
        });

System.out.println(result.join()); // value=42
~~~

With a failed source, the callback still runs and can return `"failed"`; the new stage completes **normally**. When the error needs to remain visible to the caller, rethrow an appropriate exception instead of unconditionally returning a fallback.

### Distinguishing null from errors

~~~java
CompletableFuture<String> nullable =
        CompletableFuture.completedFuture(null);

CompletableFuture<String> state =
        nullable.handle((value, error) ->
                error == null ? "success-even-if-null" : "failed");
~~~

`state.join()` is `success-even-if-null`. If you use `value == null` to infer failure, the application will misbehave with any API permitting null results and with `CompletableFuture<Void>`, because a `Void` task completing normally typically has a null value.

### Using handle to standardize application results

Suppose an API needs to represent status rather than throwing exceptions through every layer; you can create an `Outcome<T>` class holding `value` or `failure` and write:

~~~java
CompletableFuture<Outcome<Customer>> outcome =
        customerService.load(id)
                .handle((value, error) ->
                        error == null
                                ? Outcome.success(value)
                                : Outcome.failure(unwrapCompletion(error)));
~~~

This is an **integration snippet**, requiring real `Outcome`, `Customer`, and service classes; by itself it does not compile standalone. Crucially, when `handle` returns `Outcome.failure(...)`, **the stage succeeds at the Future level**, even though **the business operation failed**. Consumers must inspect `Outcome`, not merely `isCompletedExceptionally()`.

### When handle throws an exception itself

If the `handle` callback throws `IllegalStateException` in either branch, the new stage completes exceptionally with that error. The previous source error is not automatically preserved if the callback chooses to throw a new error. Design exception translation carefully to avoid masking the original cause.

## 6. whenComplete(): observes and preserves the source result or error

Typical signature:

~~~java
public CompletableFuture<T> whenComplete(
        java.util.function.BiConsumer<? super T, ? super Throwable> action)
~~~

`whenComplete` is invoked on both success and failure, yet the callback **returns no value**. The new stage typically **carries the same result or same failure** as the source. This suits logging, metrics, tracing, instrumentation, and brief cleanup upon task completion.

~~~java
CompletableFuture<String> original =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> observed =
        original.whenComplete((value, error) -> {
            if (error == null) {
                System.out.println("completed");
            } else {
                System.err.println("failed: " + error);
            }
        });
~~~

`observed.join()` remains `"ready"`, provided the callback does not throw. If the source already completed exceptionally, `observed.join()` also throws that exception, even when the callback only logs and does not throw.

### Do not use whenComplete to “return a fallback”

Wrong expectation:

~~~java
CompletableFuture<Integer> result =
        failedIntegerFuture.whenComplete((value, error) -> {
            if (error != null) {
                System.out.println("Using default 0");
            }
        });
~~~

This is an **illustrative snippet** assuming `failedIntegerFuture` already exists. It **does not** give `result` a value of `0`. `whenComplete` has no return value for substitution. If you need a fallback, use `exceptionally`; if you need to map both branches, use `handle`.

### If the observer throws an exception itself: there is a precedence rule

According to the `CompletionStage` contract:

1. Source **succeeded**, observer throws -> the dependent stage **fails with the observer's error**.
2. Source **already failed**, observer also throws -> the dependent stage **preserves the source error** rather than replacing it with the observer's error.
3. Source completes in any state, observer finishes normally -> the dependent stage preserves the source's exact state.

Example:

~~~java
CompletableFuture<Integer> normal =
        CompletableFuture.completedFuture(3);

CompletableFuture<Integer> brokenObserver =
        normal.whenComplete((value, error) -> {
            throw new IllegalStateException("logging unavailable");
        });
// brokenObserver fails with IllegalStateException.

CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

CompletableFuture<Integer> stillOriginalError =
        failed.whenComplete((value, error) -> {
            throw new IllegalStateException("observer also failed");
        });
// stillOriginalError still prioritizes the source's IllegalArgumentException.
~~~

This is **Java code inside a method**. This rule helps when analyzing failure causes, but do not rely on it to allow logging callbacks to throw arbitrarily. A good observer should avoid raising secondary exceptions and stay lightweight.

### whenComplete is not identical to finally

Java's `finally` syntax runs when exiting the corresponding `try` block; `whenComplete` runs when **the stage it is attached to** completes. If a `whenComplete` callback is registered *after* an `exceptionally` that already recovered, it sees the **success path**. If registered *before* `exceptionally`, it sees the **original error**.

## 7. Standalone Java 17+ example: comparing all three methods

The following example uses already-completed futures to produce **deterministic** stdout without depending on a scheduler or sleep duration. It also tests error precedence when `whenComplete` throws and cancellation.

File **CompletionHandlersDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class CompletionHandlersDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(10);
        AtomicInteger recoveryCalls = new AtomicInteger();

        CompletableFuture<Integer> unchanged =
                success.exceptionally(error -> {
                    recoveryCalls.incrementAndGet();
                    return -1;
                });

        System.out.println("success=" + unchanged.join());
        System.out.println("exceptionallyCalled=" + recoveryCalls.get());

        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad input"));

        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> 7);

        System.out.println("recovered=" + recovered.join());
        System.out.println("originalFailed="
                + failed.isCompletedExceptionally());

        CompletableFuture<String> mapped =
                success.handle((value, error) ->
                        error == null ? "value=" + value : "error");
        CompletableFuture<String> mappedFailure =
                failed.handle((value, error) ->
                        error == null ? "value=" + value : "failure");

        System.out.println("handleSuccess=" + mapped.join());
        System.out.println("handleFailure=" + mappedFailure.join());

        AtomicBoolean noticed = new AtomicBoolean();
        CompletableFuture<Integer> observed =
                failed.whenComplete((value, error) ->
                        noticed.set(error != null));

        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("observedCause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("observerCalled=" + noticed.get());

        CompletableFuture<Integer> newError =
                success.whenComplete((value, error) -> {
                    throw new IllegalStateException("observer failed");
                });
        try {
            newError.join();
        } catch (CompletionException ex) {
            System.out.println("observerOnSuccess="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<Integer> originalWins =
                failed.whenComplete((value, error) -> {
                    throw new IllegalStateException("second failure");
                });
        try {
            originalWins.join();
        } catch (CompletionException ex) {
            System.out.println("observerOnFailure="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> nullSuccess =
                CompletableFuture.completedFuture(null);
        System.out.println("nullIsSuccess="
                + nullSuccess.handle((value, error) -> error == null).join());

        CompletableFuture<Integer> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);
        System.out.println("cancelled=" + cancelled.isCancelled());
        System.out.println("cancelFallback="
                + cancelled.exceptionally(error -> 99).join());
    }
}
~~~

Compile and run:

~~~bash
javac CompletionHandlersDemo.java
java CompletionHandlersDemo
~~~

Stdout on a successful run:

~~~text
success=10
exceptionallyCalled=0
recovered=7
originalFailed=true
handleSuccess=value=10
handleFailure=failure
observedCause=IllegalArgumentException
observerCalled=true
observerOnSuccess=IllegalStateException
observerOnFailure=IllegalArgumentException
nullIsSuccess=true
cancelled=true
cancelFallback=99
~~~

**Explanation of each group of results:**

- With `success`, the `exceptionally` callback does not run, so the counter stays at 0.
- With `failed`, `exceptionally` yields `7` on the new stage; `failed` remains exceptional because recovery **does not mutate the source stage**.
- `handle` turns success into `"value=10"` and failure into `"failure"`; both new stages complete normally.
- `whenComplete` observes the exception without recovering; `observed.join()` throws `CompletionException` with cause `IllegalArgumentException`.
- If the observer fails on a successful source, the new stage carries the observer's error; if the source was already failed, the source exception takes precedence.
- `CompletableFuture.completedFuture(null)` is still a success: `handle` sees `error==null`.
- `cancelled.exceptionally(...)` can return fallback `99` because cancellation is a kind of exceptional completion. This does **not** mean cancellation was undone on `cancelled`: `cancelled.isCancelled()` stays true.

The example uses Java 17+, matching class/file names, has no Spring dependencies, and uses no `Thread.sleep()`. Spring integration snippets in later sections require project dependencies.

## 8. Callback order determines which error is seen

Suppose a source future fails. The following two pipelines **differ in meaning**:

~~~java
CompletableFuture<String> a =
        source.whenComplete((value, error) -> {
            if (error != null) {
                recordOriginalError(error);
            }
        }).exceptionally(error -> "fallback");

CompletableFuture<String> b =
        source.exceptionally(error -> "fallback")
              .whenComplete((value, error) -> {
                  recordFinalState(value, error);
              });
~~~

These are **illustrative snippets with application variables/functions** `source`, `recordOriginalError`, and `recordFinalState`. In `a`, the observer runs **before recovery** and thus sees the original error, while the final consumer receives the fallback. In `b`, the observer runs **after recovery** and thus can see the value `"fallback"` and `error==null`.

If you need to record both the original error and report the final outcome, intentionally attach two distinct observer stages with separate metric names. Do not invoke both only to record the same failure, as that easily double-counts.

### Placing recovery callbacks early or late?

~~~java
CompletableFuture<Integer> a =
        source.thenApply(value -> value * 2)
              .exceptionally(error -> 5);

CompletableFuture<Integer> b =
        source.exceptionally(error -> 5)
              .thenApply(value -> value * 2);
~~~

When `source` fails, `a` produces `5` because `thenApply` is skipped; `b` produces `10` because `exceptionally` recovers to `5` first, and then `thenApply` executes. Both expressions are valid when `source` has type `CompletableFuture<Integer>`.

**Lesson:** each callback operates on the **stage immediately to its left**, not automatically on “the entire pipeline”. To establish an error boundary for an entire chain, attach `exceptionally` at an appropriate point after all operations it should cover.

## 9. Unwrapping exception layers: CompletionException and ExecutionException

When a stage fails, Java may propagate the cause wrapped in `CompletionException`. When a consumer calls `join()`, the error typically surfaces as an unchecked `CompletionException` whose `getCause()` is the original exception. When a consumer calls `get()`, task errors are typically reported as a checked `ExecutionException`.

~~~java
CompletableFuture<String> bad =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

try {
    bad.join();
} catch (CompletionException ex) {
    Throwable root = ex.getCause();
    System.err.println(root.getClass().getSimpleName());
}

try {
    bad.get();
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable root = ex.getCause();
    System.err.println(root.getClass().getSimpleName());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
~~~

This Java snippet works inside a method with imports for `CompletableFuture` and `CompletionException`; it demonstrates both error paths. `get(timeout, unit)` can also throw `TimeoutException`. `CancellationException` can be thrown directly when a future is cancelled.

**Do not assume** the callback's `error` parameter always has one layer of `CompletionException`. If the source is `failedFuture(new IllegalArgumentException(...))`, the callback may receive `IllegalArgumentException` directly. If the error propagated through dependent stages, there may be a `CompletionException`. Therefore, unwrap with clear bounds when classifying errors.

Helper pattern:

~~~java
static Throwable unwrapCompletion(Throwable throwable) {
    Throwable current = throwable;
    while (current instanceof CompletionException
            || current instanceof java.util.concurrent.ExecutionException) {
        if (current.getCause() == null) {
            break;
        }
        current = current.getCause();
    }
    return current;
}
~~~

This is an **illustrative Java method**, requiring `CompletionException` to be imported and suitable for a utility class. It unwraps only the two wrappers representing future completion, rather than stripping every exception with a cause arbitrarily. When logging, preserve the stack trace with both wrappers and the root cause if needed for investigation.

## 10. Spring @Async exceptions vs. submission rejection

In Spring Framework, a method annotated with `@Async` can return `CompletableFuture<T>` when invoked through a Spring proxy with `@EnableAsync` enabled. There are two distinct failure points:

1. **Submission error:** the executor cannot accept the task due to saturation/shutdown, typically throwing `TaskRejectedException` (for `ThreadPoolTaskExecutor` and `AbortPolicy`) right at the proxy call. At this moment the caller may **not have received a future yet** to attach callbacks to.
2. **Error inside an accepted task:** the method body throws an exception after the executor accepted the work, or a subsequent stage fails. The returned Future completes exceptionally, and `exceptionally`/`handle`/`whenComplete` can process it.

Spring method example:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PricingAsyncService {

    @Async("pricingExecutor")
    public CompletableFuture<Integer> calculatePrice(int units) {
        if (units < 0) {
            throw new IllegalArgumentException("units must be non-negative");
        }
        return CompletableFuture.completedFuture(units * 100);
    }
}
~~~

This is a **Spring service** requiring `spring-context`, an executor named `pricingExecutor`, and calls from another bean through the proxy. Inside the target method, `completedFuture(...)` is a temporary handle satisfying the signature; the Spring proxy gives the caller a handle representing the actual async task. Do not infer this method runs synchronously just because it creates a `completedFuture` inside the worker.

Another consumer:

~~~java
CompletableFuture<Integer> result;
try {
    result = pricingAsyncService.calculatePrice(3);
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Executor did not accept task: respond with overload / send to durable store.
    throw ex;
}

CompletableFuture<Integer> visible =
        result.whenComplete((value, error) -> {
            if (error != null) {
                logJobFailure(error);
            }
        }).exceptionally(error -> 0);
~~~

This is an **integration snippet** with `pricingAsyncService` injected and `logJobFailure` defined by the application. If `calculatePrice(-1)` fails on the worker, the observer can log the exception and `exceptionally` can return fallback `0`. However, **returning a price of 0 when calculation fails is an example of risky business semantics**; in a commerce system, define a clear policy or preserve the error instead of substituting price 0.

### Illustrative executor configuration

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class PricingAsyncConfig {

    @Bean(name = "pricingExecutor")
    public ThreadPoolTaskExecutor pricingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("pricing-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

This is a **Spring configuration class** without a standalone `main`. Queue/rejection settings are illustrative only; in production, size according to workload and monitor queue depth, active threads, response time, timeouts, and rejections.

One detail: `@Async void` **does not** return a `CompletableFuture`, so there is nowhere for the caller to invoke these three methods. Uncaught errors in the body of `@Async void` typically go through `AsyncUncaughtExceptionHandler`. Choose `CompletableFuture<T>` when the caller needs to observe or compose the result.

## 11. Which callback to choose for logging, metrics, and fallbacks?

### Need A: log every completion without altering the value

~~~java
CompletableFuture<Order> tracked =
        orderService.load(orderId)
                .whenComplete((order, error) -> {
                    if (error == null) {
                        metrics.incrementSuccess();
                    } else {
                        metrics.incrementFailure();
                    }
                });
~~~

This is an **illustrative snippet** with `Order`, `orderService`, and `metrics` defined by the application. `whenComplete` preserves the result/error from `load` provided the metrics callback finishes normally. Metric handlers must be fast, thread-safe, perform no slow I/O, and throw no uncontrolled exceptions.

### Need B: network failure with a defined fallback

~~~java
CompletableFuture<Stock> current =
        stockService.fetch(sku)
                .exceptionally(error -> {
                    Throwable cause = unwrapCompletion(error);
                    if (cause instanceof RemoteStockTimeoutException) {
                        return lastKnownStock(sku);
                    }
                    throw new CompletionException(cause);
                });
~~~

This is a **design pattern snippet**; non-Java types/services/helpers must be declared in the project. If a stale fallback violates business rules, do not use it. Attach metrics to distinguish real fetched data responses from cached fallbacks.

### Need C: API must return a standardized result even on error

~~~java
CompletableFuture<ApiResult<Report>> api =
        reportService.generate(reportId)
                .handle((report, error) -> {
                    if (error == null) {
                        return ApiResult.ok(report);
                    }
                    return ApiResult.failure(
                            classify(unwrapCompletion(error)));
                });
~~~

`ApiResult`, `Report`, and `classify` are application components. Stage `api` completes **normally** with `ApiResult.failure` when `handle` returns normally. The HTTP layer must inspect `ApiResult`'s state and pick the right status code; `future.isCompletedExceptionally()==false` does not mean business success.

### Need D: log the error and let the error continue propagating

~~~java
CompletableFuture<Report> visible =
        reportService.generate(reportId)
                .whenComplete((report, error) -> {
                    if (error != null) {
                        logFailure(unwrapCompletion(error));
                    }
                });
~~~

Here `whenComplete` is usually a better fit than `exceptionally`: the callback observes the error without **replacing the error with a dummy value**. If you only want to log failures and do not care about the success path, `whenComplete` with a conditional check still works well.

## 12. async variants and which thread executes the callback?

These methods have multiple variants:

- `exceptionally(fn)`, `handle(fn)`, `whenComplete(action)`.
- `exceptionallyAsync(fn)`, `handleAsync(fn)`, `whenCompleteAsync(action)`.
- `...Async(fn, Executor executor)` overloads allowing an explicit executor.

With methods **without the Async suffix**, the callback may run on the thread completing the stage or the thread registering the callback if the stage is already complete. Do not bake the assumption “all callbacks run on the `@Async` worker” into business logic. With `...Async` variants, the callback work is scheduled via the stage's default executor (typically `ForkJoinPool.commonPool()` for standard `CompletableFuture`) or the supplied executor.

~~~java
CompletableFuture<String> result =
        source.handleAsync(
                (value, error) -> error == null
                        ? value.toUpperCase()
                        : "FALLBACK",
                callbackExecutor);
~~~

This is an **illustrative snippet** with `source` of type `CompletableFuture<String>` and `callbackExecutor` of type `Executor`. Picking a dedicated executor helps when the callback performs substantial CPU/I/O work and needs isolation from the thread completing the source; however, it also introduces queue, rejection, shutdown, and context management requirements.

Avoid two misconceptions:

1. **The Async suffix does not guarantee spawning a new thread.** It uses the specified scheduling mechanism; an executor might run directly on the caller or become saturated.
2. **Not having the Async suffix does not mean the callback always runs synchronously when registered.** If the source is not yet complete, the callback runs when the source completes; it simply does not request separate scheduling through another executor.

### Blocking callback warning

If you use `whenComplete` to make HTTP calls, write files, or block on another `Future.join()`, the callback can block the very thread completing the source task. That increases latency for downstream stages, holds workers longer, and can cause starvation when callbacks wait on tasks sharing a small pool. Prefer fast callbacks; for heavy work, provision a separate executor/queue and monitor overload independently.

## 13. New errors thrown inside callbacks: do not lose the root cause

The three APIs share one trait: if the callback throws an unhandled exception, **the returned stage can complete exceptionally**. However, `whenComplete` has a rule prioritizing the original error when both source and observer fail, whereas `handle` and `exceptionally` actively compute a new result so their new errors can replace the prior error path.

Intentional callback placement:

~~~java
CompletableFuture<Result> pipeline =
        doRemoteWork()
                .whenComplete((value, error) -> auditResult(value, error))
                .handle((value, error) -> {
                    if (error == null) {
                        return Result.success(value);
                    }
                    return Result.failure(unwrapCompletion(error));
                });
~~~

This is a **design pattern** requiring `Result`, `doRemoteWork`, and `auditResult` from the application. If `auditResult` throws an exception on the source's success path, the `whenComplete` stage fails with the observer's error and `handle` sees the observer's error, not a remote work error. Therefore logging, tracing, and metrics should avoid uncontrolled exceptions.

If an error is recovered in `exceptionally` before passing through another `whenComplete`, the later observer sees **success**, even though the source operation failed. To record both original errors and recoveries, distinguish metrics by stage.

## 14. Cancellation and timeout are also sources of exceptional completion

`CompletableFuture.cancel(true)` is not the same as reliably interrupting a worker: with standard `CompletableFuture`, the `mayInterruptIfRunning` parameter is not used to interrupt running tasks. Cancellation represents exceptional completion, so `exceptionally`, `handle`, or `whenComplete` can be triggered.

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
source.cancel(false);

CompletableFuture<String> converted =
        source.exceptionally(error -> "cancelled-or-failed");
~~~

`converted.join()` yields `"cancelled-or-failed"`, yet `source.isCancelled()` remains `true`. Automatically recovering every cancellation into a success value can **mask the caller's intent to cancel**. When cancellation means aborting a workflow, distinguish `CancellationException` from other business errors.

`orTimeout(2, TimeUnit.SECONDS)` can complete **that future itself** exceptionally with `TimeoutException` if not finished in time. `completeOnTimeout(fallback, ...)` can complete that future itself with a fallback value. Both methods are completion/deadline decisions; they do not automatically stop running I/O or roll back side effects that already happened.

In particular, placing `exceptionally` after a timeout makes the callback treat the timeout error as a failure branch. If retrying, verify whether the old task has stopped, whether the operation is idempotent, and whether duplicate side effects could occur.

## 15. Complex chains: allOf, thenCompose, and error propagation

Other stages such as `thenApply`, `thenCompose`, `thenCombine`, and `allOf` can complete exceptionally when a dependent branch fails. Placing error handlers at the right points determines fallback scope.

Example task chain:

~~~java
CompletableFuture<Receipt> receipt =
        customerService.load(customerId)
                .thenCompose(customer -> paymentService.charge(customer))
                .thenApply(payment -> receiptMapper.toReceipt(payment))
                .whenComplete((value, error) ->
                        metrics.recordPaymentAttempt(error == null))
                .exceptionally(error -> {
                    throw new CompletionException(
                            unwrapCompletion(error));
                });
~~~

This is **illustrative architectural code**, not standalone compilable because it needs system services/types. `whenComplete` observes completion before recovery. The trailing `exceptionally` here only rethrows the unwrapped error **without producing a fallback**, so it may be redundant; a cleaner approach is letting the error propagate and catching it at the appropriate boundary.

For **charge/payment tasks with side effects**, never use `exceptionally(error -> successReceipt)` to fabricate a fake successful receipt. Persist transaction state, enforce idempotency, reconcile, and handle indeterminate errors according to real requirements.

### allOf and a single failing branch

`CompletableFuture.allOf(a,b)` returns `CompletableFuture<Void>`, completing once both finish; if one branch fails, the combined future also completes exceptionally. You can attach `whenComplete` to the combined future to measure the overall outcome. If you need **per-branch** statistics, attach `handle`/`whenComplete` to each source instead of inferring from just one exception on the aggregate.

If you want to report **all** failures without letting one branch's error block reading another branch, use `handle` to turn each branch into an `Outcome` containing success/failure, then combine those `Outcome` instances. That is a deliberate choice, not “swallowing” errors out of convenience.

## 16. Transactions, ThreadLocal, and logging context in Spring

In Spring `@Async`, the method body typically runs on an executor thread. Transactions bound to the caller thread are not automatically inherited, just like many `ThreadLocal` values holding `SecurityContext`, MDC/log correlation, and trace context. Callbacks `thenApply/handle/whenComplete` without the Async suffix can run on **whichever thread completes the stage**, so assuming they always see the request context is also unsafe.

Error-prone situations:

- A `whenComplete` callback reads an MDC request ID, but the completing thread is a worker without MDC.
- An `exceptionally` fallback reads security principal info from a `ThreadLocal` instead of safe parameters.
- `handle` writes to the database, yet the controller's transaction has already committed/rolled back.
- Using `@Async` to dispatch work before the source transaction commits; the worker sees uncommitted or rolled-back data.

Solutions: pass required metadata as immutable values; use a `TaskDecorator` or appropriate context propagation mechanism on the executor; define separate transaction boundaries in the worker; when post-commit execution is required, use after-commit events or a transactional outbox. **Never choose a callback assuming thread context survives automatically.**

## 17. Designing logging and metrics to avoid missing or double-counting errors

A pipeline can have multiple stages:

~~~text
source (exception)
   |
   +--> whenComplete(log original) ---> exceptionally(fallback)
   |                                    |
   |                                    +--> whenComplete(log recovered)
   |
   +--> handle(create Outcome.failure)
~~~

If all three places increment the same `failed_jobs++` metric, the system double-counts one job. Differentiate instead:

- **True error source:** metric at the execution boundary or an observer attached directly to the source.
- **Fallback used:** separate metric counting result substitutions.
- **Final business outcome:** metric at the response/job-status boundary.
- **Callback processing error:** separate metric or log so it is not confused with source errors.

Do not log the exception object merely by calling `error.toString()` and dropping the stack trace in systems needing incident investigation. Yet also do not log sensitive request/exception data. When a logging callback can throw, isolate it or ensure a reliable sink with lightweight exception handling, since `whenComplete` can turn a successful pipeline into a failed one.

## 18. Testing with CompletableFuture: deterministic, no sleep guessing

### Unit-testing the three APIs directly

Use `CompletableFuture.completedFuture(value)` and `CompletableFuture.failedFuture(error)` to test every branch **without needing an executor**. You can assert:

1. `exceptionally` **is not called** when the source succeeds.
2. `exceptionally` returns the fallback when the source fails, while the source stays exceptional.
3. `handle` runs on both branches and can convert `Integer` to `String`.
4. `whenComplete` sees the error while the dependent stage stays exceptional.
5. When a `whenComplete` observer throws on a successful source, the dependent stage fails with the observer's error.
6. When the observer also throws on an already-failed source, the dependent stage prioritizes the source error.
7. A source completing normally with `null` is handled properly via `error == null`.
8. Cancellation can trigger exceptional completion without undoing cancellation on the source.

### Integration testing with Spring @Async

To test the real task path:

- Create a Spring-managed `@Async` bean, enable `@EnableAsync`, and **call through the Spring proxy**, avoiding `this.method()` within the same bean in proxy mode.
- Use `CountDownLatch entered` to confirm the worker started and `CountDownLatch release` to control when the worker finishes. Do not use `Thread.sleep(...)` to manufacture races.
- Return `CompletableFuture.completedFuture(value)` or let an exception throw from the body; inspect the proxy's Future with `get(timeout, unit)`, `whenComplete`, and `exceptionally`.
- Separately test submission rejection when the executor/queue is full; submission failures can happen **before a Future exists** and cannot be tested solely via downstream callbacks.
- Test executor cleanup and ensure latches are released in `finally` so CI does not hang.
- Test thread identity if the application has specific executor/context requirements; do not infer async execution from a future happening to be pending at a random moment.

Illustrative JUnit 5 assertions example:

~~~java
CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

assertEquals(10, failed.exceptionally(error -> 10).join());

CompletableFuture<String> mapped =
        failed.handle((value, error) ->
                error == null ? "ok" : "failure");
assertEquals("failure", mapped.join());

CompletableFuture<Integer> observed =
        failed.whenComplete((value, error) ->
                assertNotNull(error));
assertThrows(CompletionException.class, observed::join);
~~~

This is a **JUnit 5 fragment**, requiring static imports for `Assertions.assertEquals`, `assertNotNull`, `assertThrows`, imports for `CompletableFuture` and `CompletionException`, and an enclosing test method/class. Do not treat it as a standalone program.

## 19. Common mistakes to avoid

1. **Using `whenComplete` thinking it recovered the error.** An observer returns no fallback; the error keeps propagating.
2. **Using `exceptionally` just to log and accidentally returning a default.** The caller receives a false success and may miss the source failure.
3. **Using `handle` without checking `error`.** You may access a null `value` when the source failed, or treat null as failure when the source succeeded.
4. **Assuming all three APIs mutate the source future in place.** Each API returns a new dependent stage; the source is unchanged.
5. **Placing fallback too early in the pipeline.** A critical error turns into success and subsequent stages still execute side effects.
6. **Placing fallback too late when recovering a specific branch.** Intermediate transformations were already skipped because the error propagated.
7. **Catching every `Throwable` and returning default data.** Can hide programming bugs, data errors, interruption/cancellation, and system outages.
8. **Failing to unwrap `CompletionException` when classifying causes.** Inspecting the wrapper instead of the root cause.
9. **Unwrapping every exception layer with an unbounded loop.** Loses business semantics of exceptions that carry their own meaningful causes.
10. **Calling `join()` thinking it is non-blocking.** `join()` still blocks if the stage has not completed; it only removes checked exceptions.
11. **Assuming `whenComplete` is always safe and can never fail the stage.** An observer throwing on a successful source fails the dependent stage.
12. **Blocking for long durations in callbacks without the Async suffix.** Can tie up the worker that just finished the source and cause bottlenecks.
13. **Using `handleAsync` without passing an executor assuming it stays on the Spring pool.** It may switch to `commonPool`/the default execution facility.
14. **Forgetting submission rejection.** If the executor does not accept the task, the caller has no Future to attach `exceptionally` to.
15. **Writing `@Async void` and trying to call `whenComplete` on the void call.** There is no handle; you need a Future or other job-state tracking.
16. **Confusing cancel with actually interrupting work.** `CompletableFuture.cancel` does not reliably stop running CPU/I/O work.
17. **Confusing a Future timeout with rolling back side effects.** The task may keep running after the waiter gives up.
18. **Attaching the same metric at multiple stages without distinguishing scope.** Double-counts errors or reports fallback success as genuine success.
19. **Failing to test null success values and cancellation.** State-checking logic breaks easily on these two cases.
20. **Ignoring thread context in callbacks.** MDC, security, and transactions are not guaranteed to move from the request thread to the worker.
21. **Adding callbacks just to turn exceptions into an overly generic message.** Loses diagnostic root causes and semantic error codes.
22. **Using fallbacks for financial operations or critical side effects.** Returning a fake “success” can corrupt data; use job status, retries, and reconciliation instead.

## 20. Choosing an API via quick questions

| Application question | Choice |
| --- | --- |
| The source failed; I want to return a fallback value of the same type `T`? | `exceptionally` |
| The source succeeded or failed; I want to convert both into a different type `U`? | `handle` |
| I only need to log/record metrics for all outcomes without changing the value or error? | `whenComplete` |
| I want to keep the exception for the caller while adding observability? | `whenComplete` before propagating the error |
| I want an `Outcome<T>` instead of an exceptional future? | `handle` creating an `Outcome` with explicit status |
| I want a heavy callback to run on a dedicated executor? | `handleAsync`/`whenCompleteAsync`/`exceptionallyAsync` with an explicit executor |
| I want to fall back with another asynchronous task? | `exceptionallyCompose` in Java 17+ or `handle` + `thenCompose`; control executor and retries |
| I want to handle `@Async void` errors? | `AsyncUncaughtExceptionHandler` or change signature to return a Future |
| I want to detect executor rejection before a Future is returned? | Catch `TaskRejectedException` at the proxy call site, not in downstream callbacks |
| I want jobs to survive an application restart? | Durable queue/job table with idempotency/retry, not just `CompletableFuture` |

### More on exceptionallyCompose

`exceptionally` requires the callback to return a `T` value directly. If the fallback itself must call an **asynchronous** service returning `CompletionStage<T>`, Java 17 provides `exceptionallyCompose(fn)` to compose a fallback stage without creating nested Futures. Model example:

~~~java
CompletableFuture<String> result =
        primary.fetch(key)
                .exceptionallyCompose(error -> secondary.fetch(key));
~~~

This is an **integration fragment**: `primary`/`secondary` are hypothetical services returning `CompletableFuture<String>`. Falling back to a secondary source must enforce timeouts, circuit breakers, and avoid infinite retry loops. If you only need an in-memory default value, `exceptionally` is simpler.

## 21. Self-check questions

1. Among the three APIs, which method **runs only when the source fails**?
2. Which method can convert a `CompletableFuture<Integer>` into a `CompletableFuture<String>` with a single callback?
3. Why does `whenComplete((v,e)->log(e))` not mean the error has been recovered?
4. When the source succeeds but a `whenComplete` observer throws an exception, what state does the dependent stage have?
5. When the source already failed and the observer also fails, which error takes precedence in the `whenComplete` stage?
6. Is `CompletableFuture.completedFuture(null)` a success or a failure? Which field should you check in `handle`?
7. Why does `source.exceptionally(...)` not turn `source.isCompletedExceptionally()` from true to false?
8. How does placing `whenComplete` before vs. after `exceptionally` affect logging output?
9. Is `join()` more non-blocking than `get()`? How do the two methods differ in how they report exceptions?
10. Which thread pool can `handleAsync` without an executor run its callback on in a Spring application?
11. With `@Async`, how do errors from the method body differ from `TaskRejectedException` at submission time?
12. If a `CompletableFuture` was cancelled yet `exceptionally` turned it into a fallback in a later stage, does that mean the earlier task kept running or stopped?
13. If a metric observer fails, should it be able to alter the business result? How should you design the callback?
14. Why must a failed payment operation never be recovered into “success” simply with a default value?
15. If a fallback needs to call a service returning `CompletionStage<T>`, how does `exceptionallyCompose` differ from `exceptionally`?

## 22. Official references

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage (whenComplete and handle rules)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)

**Remember:** **`exceptionally()`** recovers the error path with a value of the same type; **`handle()`** always transforms results/errors and can change types; **`whenComplete()`** observes both paths while preserving the source result/error when the callback succeeds. They create new stages rather than mutating the original stage; in Spring `@Async`, you must also handle submission errors, executors, and thread context to keep pipelines reliable.
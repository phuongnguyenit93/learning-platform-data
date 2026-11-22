# CompletableFuture: `orTimeout()`, `completeOnTimeout()`, and Fallback

## 1. Why Is a Timeout Needed in Asynchronous Processing?

A `CompletableFuture<T>` represents a result that may become available in the future. It can complete normally, complete exceptionally, or **never complete** if the work hangs, takes too long to respond, or the provider fails to report a result. If subsequent steps simply wait on that future, the entire processing flow can slow down along with it.

A **timeout** is a time limit for waiting on *an asynchronous result*. A **fallback** is the alternative behavior when the result is not available in time or fails—for example, using cached data, returning a controlled default result, or switching to a backup source. These two decisions are related but not identical: a timeout determines *when to stop waiting*; a fallback determines *what to return or do afterward*.

In Java 9+, `CompletableFuture` provides two direct methods:

~~~java
CompletableFuture<T> orTimeout(long timeout, TimeUnit unit)
CompletableFuture<T> completeOnTimeout(T value, long timeout, TimeUnit unit)
~~~

Both **return the same `CompletableFuture` instance on which they are called**, schedule timeout handling if the future is still pending, and **do not block the calling thread**. They do not create a new request, do not automatically stop background computation, and do not turn the entire chain of operations into a transaction capable of rollback.

## 2. Two Ways to Complete on Expiration

| Aspect | `orTimeout(t, unit)` | `completeOnTimeout(value, t, unit)` |
|---|---|---|
| If completed before deadline | Keeps the existing value or error | Keeps the existing value or error |
| If still pending at deadline | Completes **exceptionally** with `TimeoutException` | Completes **normally** with the fallback `value` |
| `join()` after timeout | Throws `CompletionException` whose cause is `TimeoutException` | Returns `value` |
| `thenApply(...)` | Does not run on a timed-out result; propagates the error to downstream stages | Continues running on the fallback value |
| `exceptionally(...)` | Can catch the timeout error to recover | Is not invoked simply because the default was returned successfully |
| Automatically cancels original task? | No | No |
| Creates a new future? | No, returns `this` | No, returns `this` |

Imagine a future that is pending at `t = 0`, with a timeout set to 200 ms:

~~~text
t = 0 ms                 t = 200 ms                   t = 500 ms
  |--------------------------|-----------------------------|
  task starts               deadline                      background task returns late

orTimeout:                  TimeoutException              late result cannot change the future
completeOnTimeout("cache"): value "cache"                 late result cannot change the future
~~~

If the future has already completed before 200 ms (normally, exceptionally, or by cancellation), the scheduled timeout does not overwrite that state. This is a completion race: **the first valid completion wins**. For example, calling `complete("kết quả quá muộn")` after the timeout has already completed the future will return `false`.

**Note on units:** `unit` is a `TimeUnit` such as `MILLISECONDS` or `SECONDS`. Set timeouts based on a realistic latency budget; the system timer is not guaranteed to be accurate to the exact millisecond due to thread scheduling and machine load.

## 3. Standalone Java 17 Example: Comparing Three Scenarios

Create a file `TimeoutDemo.java` with the exact contents:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutDemo {

    public static void main(String[] args) {
        // 1) Nobody completes: orTimeout finishes with an error.
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> same = first.orTimeout(30, TimeUnit.MILLISECONDS);
        System.out.println(first == same);

        try {
            first.join();
        } catch (CompletionException ex) {
            System.out.println(ex.getCause() instanceof TimeoutException);
        }
        System.out.println(first.isCompletedExceptionally());
        System.out.println(first.complete("kết quả quá muộn"));

        // 2) Still pending at expiration: completeOnTimeout provides the default value.
        CompletableFuture<String> second = new CompletableFuture<>();
        String defaultResult = second
                .completeOnTimeout("cache", 30, TimeUnit.MILLISECONDS)
                .join();
        System.out.println(defaultResult);
        System.out.println(second.isCompletedExceptionally());

        // 3) orTimeout produces an error; exceptionally selects a fallback specifically for timeout.
        CompletableFuture<String> third = new CompletableFuture<>();
        String recovered = third
                .orTimeout(30, TimeUnit.MILLISECONDS)
                .exceptionally(error -> {
                    Throwable cause = unwrap(error);
                    if (cause instanceof TimeoutException) {
                        return "fallback timeout";
                    }
                    throw new CompletionException(cause);
                })
                .join();
        System.out.println(recovered);
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac TimeoutDemo.java
java TimeoutDemo
~~~

Expected output:

~~~text
true
true
true
false
cache
false
fallback timeout
~~~

Explanation in order:

1. `first == same` prints `true`: `orTimeout()` returns the same object, not an independent future.
2. `join()` waits for the future and throws `CompletionException`; `getCause()` is `TimeoutException`. `first` is in an exceptionally completed state (`isCompletedExceptionally() == true`).
3. `complete("kết quả quá muộn")` returns `false` because the final state has already been decided.
4. `second` completes normally with `"cache"`; `isCompletedExceptionally()` is `false`.
5. `third` times out, but the **new** stage returned by `exceptionally()` recovers to `"fallback timeout"`; other errors are rethrown.

The example intentionally leaves the futures pending without creating I/O tasks, which clearly demonstrates the API semantics and produces deterministic stdout; it does not imply that a timeout stops a network call or running work.

## 4. How Do Fallbacks Differ?

### 4.1. Fixed Default with `completeOnTimeout`

~~~java
CompletableFuture<String> result = remoteFuture
        .completeOnTimeout("Chưa có dữ liệu, dùng bản cache", 800, TimeUnit.MILLISECONDS);
~~~

`remoteFuture` is an existing `CompletableFuture<String>` in the application (the snippet above illustrates a single step, not a standalone program). If it completes before 800 ms, its value/error is preserved; if it is still pending, the future completes **normally** with the default string. Downstream consumers cannot distinguish real data from the fallback solely from the completion state. When distinguishing them is necessary, design a result type with a `source`/`isFallback` field or use a dedicated data type.

If the source fails early with `IOException` or `IllegalStateException`, `completeOnTimeout` **does not** turn that error into the default: the method only handles the incomplete state when time expires.

### 4.2. Timeout as an Error, Then Conditional Recovery

~~~java
CompletableFuture<String> result = remoteFuture
        .orTimeout(800, TimeUnit.MILLISECONDS)
        .exceptionally(error -> {
            Throwable cause = unwrap(error);
            if (cause instanceof TimeoutException) {
                return "cache";
            }
            throw new CompletionException(cause);
        });
~~~

`unwrap` is the helper from the standalone example in Section 3. This approach allows **falling back only when the error is a timeout**; programming errors, invalid data, and other system errors still propagate downstream. This is a significant difference from:

~~~java
.exceptionally(error -> "cache")
~~~

This short expression swallows **all** errors, easily hiding programming bugs or infrastructure failures. Use it only when the business contract truly accepts a fallback value for any error whatsoever.

**About `CompletionException`:** `join()` typically wraps errors in `CompletionException`; in a stage callback, the cause may be `TimeoutException` directly or wrapped through another stage. Therefore, the example handles both. `get()` differs from `join()`: `get()` is a checked-exception API that can throw `ExecutionException` and `InterruptedException`. Do not use `exception.getClass() == TimeoutException.class` across all layers because wrapped errors are easily missed.

### 4.3. Fallback Executing Another Asynchronous Task

If the fallback needs to read a cache asynchronously or try a second provider, `exceptionally()` takes a callback returning a **value `T`**, not a `CompletableFuture<T>` that is automatically flattened. Starting in Java 12, use `exceptionallyCompose()` to return a fallback future:

~~~java
// Illustrative example in a service that already has remoteFuture, cacheExecutor,
// readCache(), and unwrap() from Section 3.
CompletableFuture<String> result = remoteFuture
        .orTimeout(800, TimeUnit.MILLISECONDS)
        .exceptionallyCompose(error -> {
            Throwable cause = unwrap(error);
            if (cause instanceof TimeoutException) {
                return CompletableFuture.supplyAsync(this::readCache, cacheExecutor);
            }
            return CompletableFuture.failedFuture(cause);
        });
~~~

Here `readCache()` returns `String`. On timeout, the fallback branch runs on `cacheExecutor`; when another error occurs, the resulting future remains failed. `failedFuture` has been available since Java 9, and `exceptionallyCompose` since Java 12. The snippet only illustrates service components, so it will not run on its own without defining `remoteFuture`, `cacheExecutor`, and `readCache()`. If `exceptionallyCompose` is unavailable, you can combine `handle()` to create a future and then `thenCompose(f -> f)` to flatten it.

**Do not equate fallback with retry:** a fallback may return stale data, use a secondary source, or report a temporary status. A retry launches a new task and needs its own attempt limit and time budget. In operations with side effects, retrying can cause duplicate calls if idempotency is not guaranteed.

## 5. Impact of Timeouts on Stage Chains

A `CompletableFuture` consists of dependent stages. A timeout is a way of **completing the target future**, so it affects downstream stages:

~~~java
CompletableFuture<Integer> length = pendingText
        .orTimeout(500, TimeUnit.MILLISECONDS)
        .thenApply(String::length);
~~~

If `pendingText` expires, `length` completes exceptionally and `String::length` does not run. With a default value:

~~~java
CompletableFuture<Integer> length = pendingText
        .completeOnTimeout("N/A", 500, TimeUnit.MILLISECONDS)
        .thenApply(String::length);
~~~

If still incomplete at expiration, `thenApply` receives `"N/A"` and returns `3`. If the original task fails before the deadline, `thenApply` still does not run. The snippets above assume `pendingText` is a future completed elsewhere; they are chaining examples inside an application, not standalone programs.

### Three Frequently Confused Result-Handling Operators

| Operator | Runs on success? | Runs on error? | Can recover to a new value? |
|---|---|---|---|
| `exceptionally(fn)` | No | Yes | Yes, with `T` |
| `handle((value, error) -> ...)` | Yes | Yes | Yes, with the callback's return value |
| `whenComplete((value, error) -> ...)` | Yes | Yes | **No**; mainly for observation/logging, preserving the input result/error if the callback does not throw |

Example using `handle` when you want to explicitly handle both states:

~~~java
CompletableFuture<String> display = timedFuture.handle((value, error) -> {
    if (error == null) {
        return value;
    }
    if (unwrap(error) instanceof TimeoutException) {
        return "đang dùng cache";
    }
    throw new CompletionException(unwrap(error));
});
~~~

With `whenComplete`, code such as `whenComplete((v, e) -> log(e))` only **observes**; logging does not turn a failed future into a successful one. To recover, you must use `exceptionally`, `handle`, or `exceptionallyCompose`.

### Do Not Accidentally Put a Timeout on a Shared Future

Because `orTimeout` and `completeOnTimeout` mutate the state of the **original future being called**, the same `CompletableFuture` used in multiple places could be timed out according to a single consumer's budget:

~~~java
CompletableFuture<String> shared = loadSharedValue();

// View is a separate dependent stage; the timeout is only placed on view.
CompletableFuture<String> view = shared
        .thenApply(value -> value)
        .orTimeout(200, TimeUnit.MILLISECONDS)
        .exceptionally(error -> {
            if (unwrap(error) instanceof TimeoutException) {
                return "fallback riêng";
            }
            throw new CompletionException(unwrap(error));
        });
~~~

The example above is an illustration where `loadSharedValue()` returns a `CompletableFuture<String>`. `shared` is not forcibly completed by `orTimeout`; `view` has its own timeout. Java 9+ also provides `shared.copy()` to create a dependent `CompletableFuture` whose value/error is propagated from the source; you can attach the timeout to the copy instead of `shared`. Creating a view **does not duplicate or cancel background work**. If the application invokes two timeout mechanisms directly on the same instance, they race to complete that instance; which one wins depends on actual timing order.

## 6. Asynchronous Timeout Does Not Mean Task Cancellation

Suppose a `CompletableFuture` originates from `supplyAsync(() -> slowOperation(), executor)`. When `orTimeout` expires, the future may report an error while `slowOperation()` is **still running** on the executor. When `completeOnTimeout` expires, the consumer may receive the fallback while the old task keeps working and producing side effects. A late return value cannot overwrite the state of an already completed future.

This leads to three distinct responsibilities:

1. **Caller-side time limit:** `orTimeout` / `completeOnTimeout` decides the future's state after the deadline.
2. **Actual task limit:** I/O, HTTP, JDBC, socket libraries, or background tasks have their own timeout/cancellation mechanisms. Configure appropriate timeouts at the layer performing the work (such as connect/read timeouts) if you want to bound resource usage.
3. **Resource cleanup and correctness:** background work must close resources, bound concurrency, and account for side effects occurring after the caller has already used a fallback.

Even `CompletableFuture.cancel(true)` does not guarantee interrupting the thread of a `supplyAsync` task: the `mayInterruptIfRunning` argument does not make this mechanism automatically control processing interruption. If physical cancellation is required, you need to design a cancellation protocol and/or use a cancellation mechanism supported by the work source.

`orTimeout` can help the caller respond early, but it **does not replace** I/O-level timeouts and executor resource control.

## 7. Comparison with `get(timeout, unit)` and `join()`

The following approaches differ in semantics:

| Call | Does the calling thread wait? | Completes the future itself on expiration? | Outcome on expiration |
|---|---|---|---|
| `future.get(200, MILLISECONDS)` | Yes, up to the wait duration | No | `TimeoutException` is thrown to the calling thread; the future may remain pending |
| `future.join()` | Yes, until completion | No | No built-in timeout |
| `future.orTimeout(200, MILLISECONDS)` | No, when calling this method | Yes, if the future is still pending | Future completes exceptionally with `TimeoutException`; subsequent `join()` may throw `CompletionException` |
| `future.completeOnTimeout(fallback, 200, MILLISECONDS)` | No, when calling this method | Yes, if the future is still pending | Future completes normally with `fallback` |

For example, if `get(200, MILLISECONDS)` throws `TimeoutException`, other code can still call `future.complete("xong")` successfully afterward. Conversely, if `future.orTimeout(...)` itself has fired, the future is completed exceptionally and will not accept a late `complete`.

Calling `join()` at the end of the Section 3 example is for demonstration and output verification. In asynchronous applications, unless you need to bridge into synchronous processing, prefer composing stages rather than blocking threads with `join()` or `get()`.

## 8. Designing Fallbacks by Error Type and Business Requirements

There is no single right fallback for every situation. An appropriate decision typically depends on:

- **Reliability of the fallback result:** a cache can be stale; decide how long data remains acceptable. For calculations requiring high accuracy, a default value can be misleading.
- **Clarity of the data source:** if callers need to know cached data is being used, return a type such as `Result(value, source)` instead of hiding the fallback inside a normal result string.
- **Which errors are recovered:** timeouts, transient failures, or all errors? Do not swallow `NullPointerException` or validation errors just to return a success message.
- **Total latency budget:** if the primary timeout is 800 ms and the fallback itself can take 2 seconds, the overall operation can still exceed expectations. Set a separate deadline for the fallback branch when needed.
- **Background work and side effects:** if the original request still writes data after the caller returns a fallback, you need a mechanism to prevent duplicate processing or inconsistent state.
- **Observability:** record timeout counts, fallback rates, and latency; distinguish real results from fallbacks while avoiding logging sensitive data.

A practical recovery helper when the same future is used in multiple places:

~~~java
// Illustrative method that can be placed in a Java 17+ utility class.
// unwrap(Throwable) is the same as in the standalone example in Section 3.
static <T> CompletableFuture<T> withTimeoutFallback(
        CompletableFuture<T> source,
        T fallback,
        long timeout,
        TimeUnit unit) {

    return source.copy()
            .orTimeout(timeout, unit)
            .exceptionally(error -> {
                Throwable cause = unwrap(error);
                if (cause instanceof TimeoutException) {
                    return fallback;
                }
                throw new CompletionException(cause);
            });
}
~~~

This method only falls back upon receiving `TimeoutException`; other errors are propagated. `source.copy()` creates a stage copy to avoid mutating `source`'s state on timeout and allows the caller to apply its own timeout policy. However, because it only checks for `TimeoutException`, it will also fall back if the source failed with that exception type for another reason; if you need to **precisely** distinguish a timeout from this policy versus an internal source timeout, you must mark the cause or coordinate a specific error policy.

The fallback value passed into the method above is **precomputed**. If computing the fallback is expensive, start it conditionally when an error occurs using `exceptionallyCompose` (as in Section 4.3) to avoid unnecessary work in the normal success case.

## 9. Common Mistakes and Self-Check

1. **Assuming `orTimeout` returns a default value on its own.** In reality, it produces an exceptional result; use `exceptionally`/`handle` to recover, or use `completeOnTimeout` if a fixed default is appropriate.
2. **Assuming `completeOnTimeout` also handles errors occurring before the deadline.** It only applies when the future is still pending at the timeout point; early errors remain errors.
3. **Using `exceptionally(error -> fallback)` without classifying the error.** That branch hides programming bugs as well; inspect the cause and rethrow errors you do not intend to recover from.
4. **Attaching a timeout directly to a shared future.** Other consumers will also see that future completed; create a dependent stage or `copy()` if independent budgets are needed.
5. **Assuming a timeout has freed the thread or cancelled I/O.** The future may have completed while the task keeps running; you need source-level timeouts, cooperative cancellation, and separate executor management.
6. **Repeatedly calling `join()`/`get()` in asynchronous processing.** This can block threads and reduce scalability; prefer composing stages with `thenApply`, `thenCompose`, and `handle`.
7. **Failing to control the fallback path.** A fallback that is too slow, fails, has overly stale data, or causes side effects also violates system contracts; design and measure it separately.
8. **Setting multiple deadlines directly on the same future.** The actions race for state; only the first valid completion wins, and the actual outcome can depend on scheduling.

Self-check:

- If a future completes normally at 100 ms, what does `completeOnTimeout("cache", 200, MILLISECONDS)` return? **The real value**, because the future completed before the deadline.
- If a future completes exceptionally at 50 ms, does `completeOnTimeout("cache", 200, MILLISECONDS)` hide the error? **No**, the early error is preserved.
- If `get(200, MILLISECONDS)` throws a timeout, has the future transitioned to exceptional? **Not necessarily, and not because of the `get` call**; that timeout limits only the caller's wait operation.
- If a `supplyAsync` task runs longer than `orTimeout`, is it guaranteed to stop? **No**; the future's deadline and the task's execution lifecycle are two separate things.

## 10. Choosing the Right API for Each Goal

- Want to **report timeout as an error** for the caller to decide: use `orTimeout()` and let the exception propagate.
- Want to **return a fixed fallback value only on expiration**: use `completeOnTimeout(value, ...)`, and consider how to indicate the fallback source.
- Want to **fall back by error type**: use `orTimeout(...).exceptionally(...)` or `handle(...)` and preserve non-recoverable errors.
- Want the **fallback to be another async task**: use `exceptionallyCompose(...)` (Java 12+) and manage the fallback's own timeout if needed.
- Want **each caller to have a different deadline** on the same source: create a dependent stage/`copy()` before setting the timeout.

Key takeaway: **`orTimeout()` completes exceptionally; `completeOnTimeout()` completes normally with a default; both affect the target future itself and do not automatically cancel running work.** Proper fallback design requires defining which error types are acceptable, the quality of the fallback value, and how to control work that continues running after the deadline.

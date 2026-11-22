# `CompletableFuture.handle`: Transforming Both Success and Failure Results

In Java, a `CompletableFuture` chain does not only transform a value when a task succeeds; it also needs a way to represent the result when a task **fails**. The **`handle`** method receives *both completion paths* of a stage: the normal path carrying a value and the exceptional path carrying a `Throwable`. The handler can return a new value of the same or a different type, thereby producing the next stage.

This topic belongs to **Java Core – Exception / CompletableFuture**. The examples use **Java 17+**. After this lesson, you will know when to use `handle`, how to avoid masking errors, how to handle `CompletionException`/cancellation, and how to combine `handle` with other stages.

## 1. Core Model: One Callback, Two Entry Paths

A `CompletableFuture<T>` can:

- **Complete normally** with a value of type `T` (that value may be `null`).
- **Complete exceptionally** with a failure cause.
- **Be cancelled**; in `CompletableFuture`, cancellation is represented as an exceptional completion with `CancellationException`.

`handle` registers a callback with two parameters:

```java
CompletableFuture<U> next = source.handle((value, error) -> {
    // Return U, producing a new result for next.
});
```

For a `source` of type `CompletableFuture<T>`, the conceptual callback type is `BiFunction<? super T, Throwable, ? extends U>`. The signature on `CompletionStage<T>` is:

```java
<U> CompletionStage<U> handle(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn);
```

In the `CompletableFuture<T>` API, the result of the corresponding overload is `CompletableFuture<U>`.

| State of source | `value` in handler | `error` in handler |
|---|---|---|
| Completed normally with a non-`null` value | Value `T` | `null` |
| Completed normally with `null` | `null` | `null` |
| Completed exceptionally | `null` | Non-`null` `Throwable` |
| Cancelled | `null` | Failure representing cancellation, usually `CancellationException` |

**To distinguish success from failure, check `error == null`, not just `value == null`.** A task that completes successfully can very well return `null`.

A small diagram:

```text
Source CompletableFuture<T>
          |
          +-- success(value: T) ------+
          |                           |
          +-- failure(Throwable) -----+--> handle((value, error) -> U)
                                                |
                              +-----------------+------------------+
                              |                                    |
                         return U                            throw exception
                              |                                    |
                   next stage succeeds                  next stage fails
```

Calling `handle(...)` **does not block the thread** waiting for the result. It immediately returns the dependent stage. When the source finishes, the callback is executed according to the method's scheduling rules; a `join()` or `get()` placed **afterward** is the point where the caller may have to wait.

## 2. Basic Example: The Same `handle` Processing Both Cases

Create the file `HandleBasicsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class HandleBasicsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(42);

        CompletableFuture<Integer> failure =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("id không hợp lệ"));

        System.out.println(summarize(success).join());
        System.out.println(summarize(failure).join());
    }

    static CompletableFuture<String> summarize(
            CompletableFuture<Integer> source) {
        return source.handle((value, error) -> {
            if (error == null) {
                return "Thành công: " + value;
            }

            Throwable root = unwrap(error);
            return "Thất bại: "
                    + root.getClass().getSimpleName()
                    + " - " + root.getMessage();
        });
    }

    static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
```

Run:

```bash
javac HandleBasicsDemo.java
java HandleBasicsDemo
```

Exact output:

```text
Thành công: 42
Thất bại: IllegalArgumentException - id không hợp lệ
```

Explanation:

1. `completedFuture(42)` creates a stage that has already completed normally. The handler receives `value=42`, `error=null`.
2. `failedFuture(new IllegalArgumentException(...))` creates a stage that has completed exceptionally. The handler receives a `Throwable`; the `unwrap` method strips any `CompletionException` layers when present, then obtains the root cause.
3. In both branches, the handler **returns a `String`**. The resulting stage is therefore `CompletableFuture<String>` and is completed **normally**.
4. No task is submitted to a thread pool in this example; both sources are already completed. `handle` still transforms the outcome just as it does when registered before the source finishes.

`handle` does not change the fact that the original source failed. It creates **a new stage** with an independent state. If `handle` returns a successful fallback, a caller reading the new stage with `join()` gets a result; a caller reading the failed source again still encounters the error.

## 3. `handle` Also Transforms the Data Type, Not Just Error Recovery

The type `T` of the source and the type `U` returned by the handler **do not need to be the same**. This is what makes `handle` suitable for converting any outcome into a result DTO, UI message, audit event, `Result<T>`, or response under a stable contract.

Example converting `CompletableFuture<String>` into `CompletableFuture<Outcome>` (runs standalone on Java 17).

File `HandleResultTypeDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

public class HandleResultTypeDemo {
    record Outcome(boolean success, String text) {}

    static CompletableFuture<Outcome> convert(
            CompletableFuture<String> source) {
        return source.handle((value, error) -> {
            if (error != null) {
                return new Outcome(false, "không lấy được dữ liệu");
            }
            if (value == null) {
                return new Outcome(true, "<rỗng>");
            }
            return new Outcome(true,
                    value.trim().toUpperCase(Locale.ROOT));
        });
    }

    public static void main(String[] args) {
        Outcome a = convert(
                CompletableFuture.completedFuture(" java ")).join();
        Outcome b = convert(
                CompletableFuture.completedFuture(null)).join();
        Outcome c = convert(
                CompletableFuture.failedFuture(
                        new IllegalStateException("offline"))).join();

        System.out.println(a.success() + " | " + a.text());
        System.out.println(b.success() + " | " + b.text());
        System.out.println(c.success() + " | " + c.text());
    }
}
```

Commands:

```bash
javac HandleResultTypeDemo.java
java HandleResultTypeDemo
```

Output:

```text
true | JAVA
true | <rỗng>
false | không lấy được dữ liệu
```

In the success branch with a `null` value, `error` is still `null`. This is a valid result and is converted to `Outcome(true, "<rỗng>")`. In the failure branch, `value` is meaningless and the handler chooses the contract result `Outcome(false, ...)`.

In a real application, consider whether `Outcome(false, "không lấy được dữ liệu")` contains enough information for the caller. If traceability is needed, you can store a categorized error code, correlation ID, and log while preserving the cause; you should not silently turn every serious infrastructure error into a fallback string.

## 4. New Value or New Exception: How Does the Dependent Stage End?

When the `handle` callback runs:

- **`return U`**: the dependent stage completes normally with `U` (including `null` if the type allows it).
- **`throw exception`**: the dependent stage completes exceptionally; `join()` typically throws `CompletionException`, and `get()` typically throws `ExecutionException` when observing the failure.
- **Previous source failed, but handler returns a fallback**: the new stage succeeds; the old source remains failed.
- **Previous source succeeded, but handler throws an error**: the new stage fails even though the old source succeeded.

A simple example showing that the handler can produce an error:

```java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(5);

CompletableFuture<Integer> next =
        source.handle((value, error) -> {
            throw new IllegalStateException("lỗi bên trong handle");
        });

// next.join() will complete exceptionally, not return 5.
```

This is an **illustrative snippet**, placed inside a method with appropriate `CompletableFuture` imports; it is not a standalone Java file. If `next.join()` is called here without catching the exception, the caller thread can terminate with a `CompletionException` whose cause is `IllegalStateException`.

**Do not assume that having `handle` means all errors have been recovered.** The callback only recovers from an error when the error branch returns a normal value. If the callback keeps throwing, the downstream chain remains an error path.

## 5. Chain Example: An Error From an Intermediate Stage Transformed by `handle`

Create the file `HandleChainDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class HandleChainDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> parsed =
                CompletableFuture.completedFuture("abc")
                        .thenApply(Integer::parseInt);

        CompletableFuture<String> report = parsed.handle(
                (number, error) -> {
                    if (error != null) {
                        return "parse failed";
                    }
                    return "value = " + number;
                });

        System.out.println(report.join());

        try {
            parsed.join();
        } catch (CompletionException e) {
            System.out.println("source cause = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac HandleChainDemo.java
java HandleChainDemo
```

Output:

```text
parse failed
source cause = NumberFormatException
```

`thenApply(Integer::parseInt)` runs on the string `"abc"` and throws `NumberFormatException`. The `parsed` stage completes exceptionally; `report` uses `handle` to turn that failure into a normal message. When `parsed.join()` is called separately, the original error is still observable via `CompletionException`.

This example shows why you should keep a reference to the **exact stage level** you want to read. `parsed` and `report` are not a single overwritten result; they are two related stages in a dependency graph.

## 6. `handle`, `exceptionally`, `whenComplete`, `thenApply`: Using Each for Its Purpose

These four methods often sit next to each other, but their contracts differ.

| Method | Runs when source succeeds? | Runs when source fails? | Can change `T` to type `U`? | Common purpose |
|---|---|---|---|---|
| `thenApply(fn)` | Yes | No, callback branch is skipped | Yes | Transform a success value |
| `exceptionally(fn)` | No | Yes | No: returns a result of the same type `T` | Provide a fallback for the error case |
| `whenComplete(action)` | Yes | Yes | No: preserves the source's result type | Observe outcome, logging, metrics, cleanup |
| `handle(fn)` | Yes | Yes | **Yes** | Normalize outcome, transform value, or recover from error |

The intent can be expressed as:

```text
Transform value only on success         → thenApply
Recover only from failure               → exceptionally
Observe/log both outcomes only          → whenComplete
Convert both outcomes into a new type   → handle
```

`exceptionally` returns a fallback of type `T` on failure and does not run the error-handling function if the source succeeds. `whenComplete` receives `(value, error)`, but its `BiConsumer` callback has no return value to replace the result. It is useful for recording metrics or logging; if the action inside `whenComplete` throws an exception, the new stage can fail (if the source already failed, the original failure cause takes precedence per the contract). Therefore, `whenComplete` is not completely "side-effect-free" with respect to downstream state either.

Short comparison example (illustrative snippet):

```java
CompletableFuture<Integer> source =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad"));

CompletableFuture<Integer> fallback =
        source.exceptionally(error -> -1);

CompletableFuture<String> summary =
        source.handle((value, error) ->
                error == null ? "value=" + value : "failed");

CompletableFuture<Integer> observed =
        source.whenComplete((value, error) -> {
            System.out.println("observed failure: " + (error != null));
        });
```

`fallback.join()` returns `-1`, `summary.join()` returns `"failed"`; `observed` still holds the failure from `source`, so `observed.join()` will throw. If you only need to log while keeping the error state intact, `whenComplete` usually expresses that intent more accurately.

### Why Not Put `handle` Everywhere?

If every step uses `handle` to return a default value, errors can be masked and downstream stages may assume the data is valid. Let error states propagate naturally down the stages until a boundary responsible for deciding how to recover. Use `handle` when you genuinely need to **inspect both the value and the error**, typically at boundaries that return a response, display a message, persist an outcome, or select a fallback strategy.

## 7. `CompletionException` and the Root Cause

`CompletableFuture` commonly uses `CompletionException` (unchecked) to wrap errors from asynchronous stages. If a stage fails due to `IllegalStateException`, the `error` parameter in `handle` **may be the original exception or a wrapping `CompletionException`**, depending on the error source and how the stage was completed.

For example:

- `CompletableFuture.failedFuture(new IOException(...))` may pass the cause directly to the handler.
- A callback such as `thenApply` throwing an exception can cause the next stage to be marked failed through `CompletionException` wrapping.
- `future.join()` reports errors with `CompletionException` in normal failure cases, whereas `future.get()` uses `ExecutionException`. This is a mechanism for *observing errors at the caller*, not a guarantee that the `error` parameter in every handler always carries the exact same wrapper layer.

If you need accurate classification, unwrap `CompletionException` **only when a cause exists**:

```java
static Throwable unwrapCompletion(Throwable failure) {
    while (failure instanceof java.util.concurrent.CompletionException
            && failure.getCause() != null) {
        failure = failure.getCause();
    }
    return failure;
}
```

This is a **method that can be inserted into a Java class**; the input parameter `failure` must be non-`null`. Do not automatically unwrap every `RuntimeException` or every deepest cause, because other wrappers may carry business-domain meaning. Extra care is needed when handling `CancellationException` and `Error`.

Classification usage:

```java
return source.handle((value, error) -> {
    if (error == null) {
        return new Outcome(true, value);
    }

    Throwable cause = unwrapCompletion(error);
    if (cause instanceof java.io.IOException) {
        return new Outcome(false, "I/O tạm thời không khả dụng");
    }

    throw new java.util.concurrent.CompletionException(cause);
});
```

The snippet above is a **non-standalone pattern**: it assumes `source`, `Outcome`, and `unwrapCompletion` are already declared and that the value types are compatible. Only recover cases that have an explicit policy; let the remaining cases continue reporting failure. When creating a new exception, **preserve the cause** so the original stack trace is not lost. Do not turn every error, especially serious `Error`s, into a "fake success" result.

## 8. Cancellation: Does `handle` Receive Cancellation?

Yes. With `CompletableFuture<T>`, a successful `cancel(...)` call completes it exceptionally with `CancellationException`. Thus, a `handle` registered on the source can receive the error path and decide to return a fallback. However, cancellation is a **lifecycle control signal**, not necessarily an ordinary business error.

Standalone example `HandleCancellationDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class HandleCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();

        CompletableFuture<String> recovered =
                source.handle((value, error) ->
                        error == null ? value : "fallback");

        boolean canceled = source.cancel(false);

        System.out.println("source cancel accepted = " + canceled);
        System.out.println("source canceled = " + source.isCancelled());
        System.out.println("recovered = " + recovered.join());
        System.out.println("recovered canceled = "
                + recovered.isCancelled());
    }
}
```

Run:

```bash
javac HandleCancellationDemo.java
java HandleCancellationDemo
```

Output:

```text
source cancel accepted = true
source canceled = true
recovered = fallback
recovered canceled = false
```

The handler handled the cancellation exception with a fallback value, so the dependent stage `recovered` completed normally. Meanwhile, `source` retains its cancelled state.

Important point: **cancelling the source stage does not by itself prove that the background computation thread has stopped**. `CompletableFuture.cancel(boolean)` behaves the same regardless of whether `mayInterruptIfRunning` is `true` or `false`; by contract, that parameter is not used to control interrupting a task inside `CompletableFuture` itself. If you actually need to stop underlying resources, you must coordinate separately with the task or executor.

If the application treats cancellation as a signal that must not be masked, **classify** `CancellationException` and propagate the appropriate status to the caller instead of returning a fallback regardless of cause. A recovery policy for network errors usually differs from a user-requested cancellation policy.

## 9. `handle` Does Not Swallow the Waiting Thread's Interrupt

Two contexts must be distinguished:

1. A worker inside `supplyAsync(...)` is interrupted while calling `sleep`, `take`, or another waiting operation. If the worker throws the exception out, the source can complete exceptionally; a downstream `handle` receives the `Throwable` representing that failure.
2. The caller is calling `future.get()` or `future.get(timeout, unit)` and **the caller itself is interrupted**. The caller directly receives `InterruptedException`; this **does not automatically turn** the source into an exceptional completion, and does not implicitly trigger `handle` as a source error.

Example combining both directions (illustrative snippet):

```java
CompletableFuture<String> normalized =
        source.handle((value, error) ->
                error == null ? value : "nguồn thất bại");

try {
    String result = normalized.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // The current thread was interrupted while waiting; handle the caller's lifecycle.
} catch (java.util.concurrent.ExecutionException failure) {
    // normalized itself failed, e.g. the handler threw an exception.
}
```

This snippet uses an existing `source` variable of type `CompletableFuture<String>` inside a method. Calling `get()` to wait is different from the `handle` callback: **`handle` describes the outcome transformation of a stage**, whereas `get()` is a waiting operation of the calling thread.

## 10. `handle()` and `handleAsync()`: Choosing the Callback Execution Thread

Three overloads in `CompletableFuture`:

```java
<U> CompletableFuture<U> handle(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn);

<U> CompletableFuture<U> handleAsync(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn);

<U> CompletableFuture<U> handleAsync(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn,
        java.util.concurrent.Executor executor);
```

`handle` can typically run the callback directly on the thread completing the source or on the thread registering the callback if the source is already complete; **you must not rely on a fixed thread**. `handleAsync` uses `CompletableFuture`'s default asynchronous execution facility (typically `ForkJoinPool.commonPool()` under appropriate conditions). The overload taking an `Executor` submits the callback to the executor you specify.

File `HandleAsyncExecutorDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HandleAsyncExecutorDemo {
    public static void main(String[] args) {
        ExecutorService handlers = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "handler-worker"));

        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.completedFuture(10);

            CompletableFuture<String> result =
                    source.handleAsync((value, error) ->
                            Thread.currentThread().getName()
                                    + ": " + value,
                            handlers);

            System.out.println(result.join());
        } finally {
            handlers.shutdown();
        }
    }
}
```

Run:

```bash
javac HandleAsyncExecutorDemo.java
java HandleAsyncExecutorDemo
```

Result:

```text
handler-worker: 10
```

The handler runs on an executor with a clearly named thread, so the output is deterministic. This is an example of **specifying where the callback executes**, not forcing the source to re-run. The source had already finished before the handler was registered.

### When to Use the `Async` Variant?

- The handler performs heavy enough work that it should not run on the thread completing the source.
- You want to isolate CPU resources, limit the number of concurrent callbacks, or separate workload types.
- You want to control the executor lifecycle and monitor callbacks in a service environment.

Do not use `handleAsync` as a cure-all for blocking calls. If inside the callback you call `.join()` waiting for a stage that needs the very same single-threaded executor to run, starvation or deadlock can occur. You must also account for thread-switching overhead, full queues, shut-down executors, or rejected tasks: failure to schedule can cause the dependent stage to complete exceptionally.

**Keep handlers fast and non-blocking whenever possible.** If you need a new chain of asynchronous tasks, use appropriate stage composition methods like `thenCompose`, and avoid synchronous waiting inside callbacks.

## 11. `handle` Returning Another Future Can Create Nested Types

Suppose after an error, the program wants to call an **asynchronous** fallback source. If the handler returns a `CompletableFuture<U>`, then the result of `handle` can be `CompletableFuture<CompletableFuture<U>>`: a Future containing another Future.

Example **illustrative snippet** (with an application-provided `fallbackAsync()` method):

```java
CompletableFuture<CompletableFuture<String>> nested =
        source.handle((value, error) -> {
            if (error == null) {
                return CompletableFuture.completedFuture(value);
            }
            return fallbackAsync();
        });

CompletableFuture<String> flat =
        nested.thenCompose(java.util.function.Function.identity());
```

Here `source` is `CompletableFuture<String>` and `fallbackAsync()` returns `CompletableFuture<String>`. `thenCompose(Function.identity())` "flattens" the outer Future layer. Without it, a caller might mistakenly think `nested.join()` has finished waiting for the fallback task; in fact, it only returns the inner Future.

When recovering with an asynchronous task, consider APIs like `exceptionallyCompose(...)` (Java 12+) to handle only the error branch with a new stage, or use `handle(...).thenCompose(...)` if both paths must be handled. Avoid calling `.join()` directly inside the handler just to obtain the fallback result.

## 12. Combining `handle` With Multiple Steps and Handler Placement

Consider the following chain (illustrative snippet; `loadUser()`, `validateUser(...)`, and `toView(...)` are application-defined):

```java
CompletableFuture<UserView> response =
        loadUser()
                .thenApply(this::validateUser)
                .thenApply(this::toView)
                .handle((view, error) -> {
                    if (error == null) {
                        return view;
                    }
                    return UserView.unavailable();
                });
```

`handle` at the end handles errors originating from **any upstream stage** in that direct dependency chain, while also allowing normalization of the success value. However, it can also mask programming bugs (such as a `NullPointerException` due to a bug) if it always returns `unavailable()`. In production APIs, you need to distinguish recoverable errors from errors that must be recorded/propagated.

Placing the handler before or after a transformation changes the scope of errors it observes:

```text
load → handle → validate
         ↑         ↑
  handles load    validate errors can still
     errors       cause downstream to fail

load → validate → handle
                    ↑
        handles both load and validate errors
```

Do not overuse a catch-all `handle` at the end just to turn every exception into HTTP 200 or a "success" status. If inputs are missing or there is a logic bug, returning an overly broad fallback makes investigation harder.

## 13. Logging and Observing Failures Without Masking Errors

If you only need to log or measure timing, `whenComplete` is usually more appropriate:

```java
CompletableFuture<Data> observed =
        fetchData().whenComplete((data, error) -> {
            if (error == null) {
                metrics.success();
            } else {
                metrics.failure(error);
            }
        });
```

This is an **illustrative snippet** with `Data`, `fetchData()`, and `metrics` defined by the application. `observed` preserves the source's value or error state, except when the callback itself throws an error according to `whenComplete` rules.

Use `handle` for business results:

```java
CompletableFuture<ApiResult> result =
        fetchData().handle((data, error) -> {
            if (error != null) {
                return ApiResult.failed(error);
            }
            return ApiResult.ok(data);
        });
```

This is also an illustrative snippet, assuming valid `ApiResult` and `fetchData()`. If `ApiResult.failed(error)` is a normal completion value, downstream stages no longer see an exceptional completion unless they inspect the status field inside `ApiResult`. That is an **intentional contract transformation** that must be agreed upon at the calling layer.

A good strategy is to log once at a boundary that has sufficient context; preserve the cause when translating to an application error; and avoid having every `handle` layer log the same error and return a fallback. Sensitive data must not leak internal exception messages directly into public responses.

## 14. Notes on Concurrency, Timeouts, and Lifecycle

`handle` does not create timeouts on its own, does not interrupt source work, and does not guarantee that callbacks are invoked in a single global order across multiple independent stages. For **a single dependent stage created by one `handle` call**, the callback is applied when the source completes and its result completes the dependent stage; do not design your application around callback ordering between sibling stages.

Situations requiring caution:

- **Source never completes:** the handler never runs, and the resulting stage may never complete either. Place timeouts at appropriate boundaries, such as `orTimeout(...)` or a timeout on the underlying operation.
- **Source is cancelled:** `handle` can see the error path and return a fallback, but that does not prove the worker or resources have stopped.
- **Handler runs too long:** downstream stages are delayed; with synchronous `handle`, it can also tie up the thread completing the source.
- **Cross-waiting handler in a small executor:** risks starvation or deadlock, especially when a worker waits for a task that must run on the same saturated executor.
- **Callback throws an unchecked exception/`Error`:** the new stage can fail; preserve cause traces instead of swallowing all errors.
- **Mutating shared state:** the callback can run on a different thread at a different time; use immutable variables, thread-safe designs, and proper synchronization.

`CompletableFuture.orTimeout(duration, unit)` creates an exceptional completion with `TimeoutException` upon expiration and applies to the future on which it is called, not just an independent "copy". `completeOnTimeout(value, duration, unit)` supplies a normal value after the timeout if not yet completed. A handler placed after these two methods sees the outcome **after the chosen timeout policy**. Distinguish between the source's timeout, the caller's timeout when waiting in `get`, and actually cancelling the background task.

## 15. Common Pitfalls With `handle`

### 15.1. Checking Only `value == null`

Wrong:

```java
source.handle((value, error) -> {
    if (value == null) {
        return "FAILED";
    }
    return value.toString();
});
```

Because a source that **succeeds with `null`** also enters the `"FAILED"` branch. Fix this by checking `if (error != null)` to detect errors; handle `value == null` afterward according to the data contract.

### 15.2. Forgetting That the Original Source Is Not Modified

```java
CompletableFuture<Integer> original =
        CompletableFuture.failedFuture(new IllegalArgumentException());

CompletableFuture<Integer> recovered =
        original.handle((value, error) -> error == null ? value : 0);
```

`recovered.join()` returns `0`, while `original.join()` still throws. Do not expect a downstream handler to mutate the state of the source object.

### 15.3. Using `handle` Instead of `whenComplete` Just for Logging

`handle` is appropriate when you want to **return a new outcome**. If you use `handle` and accidentally return `null` in the error branch, you can mask the error and cause downstream stages to fail later with `NullPointerException`. Use `whenComplete` for observation, or intentionally propagate the error.

### 15.4. Swallowing All Errors Into a Fallback

If the received `Throwable` is a bug in transformation code or a serious `Error`, a fallback can prevent operators from noticing the failure. Only recover causes with a clear policy; remaining causes should be propagated with their cause preserved, or converted into an explicit error outcome.

### 15.5. Assuming `error` Is Always the Direct Business Exception Class

In an asynchronous chain, `CompletionException` can wrap the real cause. Classify after checking the appropriate wrapper rather than blindly casting `(MyBusinessException) error`.

### 15.6. Calling `join()` Inside a Handler to Run "Asynchronously"

`join()` can block the callback thread; in a small thread pool, it may wait on work that has no available worker to run. If a handler needs to start another stage, consider returning the stage and flattening with `thenCompose`.

### 15.7. Treating Cancellation Like Any Infrastructure Error

User-initiated cancellation or shutdown does not necessarily call for retries like a network error. You must have a separate policy for `CancellationException`, cancellation state, and resource cleanup, especially when the callback turns the error path into success.

### 15.8. Treating `handleAsync` as a Promise of a Fixed Thread

The overload without an executor runs on the default asynchronous execution facility; it does not promise a specific thread name. If you need clear resource boundaries and scheduling, pass a dedicated executor and shut it down according to its lifecycle.

## 16. Checklist When Using `handle`

Before writing a handler, verify:

1. **Purpose:** Do you need to transform *both success and failure*, or do you only want to log (`whenComplete`), handle errors (`exceptionally`), or transform values (`thenApply`)?
2. **Success state:** Is `value=null` allowed? Should it return the exact type `U` per the contract?
3. **Failure state:** Does `Throwable` have a wrapper? Do you need to classify the error, preserve the cause, or keep propagating?
4. **Cancellation/timeout:** Are these two events errors to recover with a fallback, or should the cancelled/timed-out state be preserved?
5. **Source preservation:** Is downstream code waiting on `source` or on the new stage returned by `handle`?
6. **Threading:** Is the handler blocking, CPU-heavy, or calling another service? Do you need `handleAsync(..., executor)` or composition via `thenCompose`?
7. **Observability:** Is the error logged at a single boundary with context? Does it leak internal details into responses?
8. **Testing:** Do you cover success, success with `null`, direct error, `CompletionException`-wrapped error, handler throwing its own error, cancellation, and timeout?

**Key takeaway:** `handle((value, error) -> result)` is an **outcome transformation** on a stage that runs for both normal and exceptional completions. Check `error == null` to detect success, return `U` to produce a new successful stage, or throw an error to keep the failure path. The source stage retains its own state; recovery, cancellation, or exception handling in later stages is always an intentional decision.

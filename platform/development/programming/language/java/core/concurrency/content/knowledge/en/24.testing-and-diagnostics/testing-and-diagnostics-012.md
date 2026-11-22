# Reading Stack Traces When Future and Async Stages Fail in Java

Asynchronous errors are difficult to diagnose because **where the error originates**, **where the error is recorded as the future's state**, and **where the caller observes the error** can occur on different threads and at different times. With `CompletableFuture`, an exception in `thenApply` may be stored inside the future; only when `join()` or `get()` is called on another thread does the caller receive the outer wrapper exception. If you only read the first few lines of the stack trace, it is very easy to fix the wrong place.

This lesson focuses on **general Java concurrency**: how to read the root cause, understand the boundaries of each asynchronous stage, distinguish Java-created wrappers from application errors, add diagnostic context, and handle cancellation/timeout/multiple failures. The examples use JDK 17+ APIs and require no external frameworks.

## 1. Three Locations to Distinguish When Reading Errors

Consider the following chain of work:

```text
request thread                   worker thread / executor
      |                                   |
      | supplyAsync(fetch) --------------> fetch()
      |                                   |
      |                             thenApply(parse)
      |                                   | 
      |                                   X throws IllegalArgumentException
      |                                   |
      |                         stage completes exceptionally
      |                                   |
      | join() / get() <------------------+
      |    |
      |    X throws wrapper to caller
```

There are three different places:

1. **Throw site (where the error occurs):** the first business code frame that throws `IllegalArgumentException`, `IOException`, or a specific error type. This is usually the direct place to fix.
2. **Completion site (where the future transitions state):** JDK, executor, or callback code that records the failed result into the stage. The stack may contain `CompletableFuture$UniApply.tryFire`, `AsyncSupply.run`, `ForkJoinTask.doExec`, `ThreadPoolExecutor.runWorker`. These frames show how the task was executed and transitioned, but do not by themselves indicate that the business error lives there.
3. **Observation site (where the error is received):** the thread calling `join()`/`get()`, or a downstream callback receiving `Throwable`. It may create or see a `CompletionException` or `ExecutionException` wrapper long after the original operation has completed.

**A single exception can contain multiple stacks:** the wrapper is created at one point; the inner cause is created at another. The wrapper's trace may therefore start at `CompletableFuture.reportJoin` or a similar JDK frame, while the **cause**'s trace starts at the application method that broke the task. Depending on the execution path and JDK version, line numbers and internal frames change; read the **exception type, cause chain, and application method names**, rather than relying rigidly on JDK line numbers.

## 2. How Different Future APIs Expose Errors

| Operation | On success | On future failure | On cancellation | While waiting |
| --- | --- | --- | --- | --- |
| `Future.get()` | Returns the result | Throws checked `ExecutionException`, cause in `getCause()` | Throws `CancellationException` | Waits until done; may throw `InterruptedException` |
| `Future.get(timeout, unit)` | Returns the result | Throws `ExecutionException` | Throws `CancellationException` | May throw `TimeoutException` if not done in time |
| `CompletableFuture.join()` | Returns the result | Usually throws unchecked `CompletionException`, cause in `getCause()` | May throw `CancellationException` directly when the future is canceled | Waits without a timeout parameter |
| `CompletableFuture.getNow(default)` | Returns the available result, or the default value if not done | When already failed, may throw `CompletionException` | Throws `CancellationException` if canceled | Does not wait |
| `CompletableFuture.whenComplete(...)` | Forwards the original result when the observer succeeds | Observer receives `Throwable`; returned stage remains exceptional if the source is exceptional | Observer receives failure/cancellation state depending on the source | Does not block waiting |
| `CompletableFuture.handle(...)` | Callback receives `(value, null)` | Callback receives `(null, throwable)` and can produce a replacement result | Callback can also see cancellation | Does not block waiting |
| `CompletableFuture.exceptionally(...)` | Skips callback on success | Callback receives the error, can recover or throw another error | May be invoked with cancellation as an exceptional completion | Does not block waiting |

**`get()` and `join()` do not return exceptions as values:** they throw when the future completes exceptionally. `get()` uses checked exceptions and supports interruptible waiting; `join()` is more convenient when composing code where you do not want to declare checked exceptions. All `handle`/`whenComplete`/`exceptionally` callbacks may run synchronously on the thread completing the stage or the thread registering the callback if the stage is already done; add the `Async` suffix to request asynchronous execution.

`CompletionException` and `ExecutionException` are **wrappers carrying the failure cause**, not necessarily bugs in the JDK. `CancellationException` indicates the future was canceled; `TimeoutException` from `get(timeout, ...)` usually indicates that the calling thread **timed out waiting**, and does not confirm that background work stopped or that the future failed.

Other errors to recognize: `RejectedExecutionException` may come from an executor refusing a task; `InterruptedException` signals that the waiting thread was interrupted; errors thrown by the task (`IllegalStateException`, `NullPointerException`, `IOException` wrapped in an appropriate exception) retain their own semantics in the cause chain.

## 3. How to Read a Stack Trace with Multiple "Caused by" Entries

**Illustrative** example, with frames and line numbers omitted as they vary by JVM:

```text
java.util.concurrent.CompletionException: java.lang.IllegalArgumentException: invalid payload
    at java.base/java.util.concurrent.CompletableFuture.encodeThrowable(...)
    at java.base/java.util.concurrent.CompletableFuture$UniApply.tryFire(...)
    ...
Caused by: java.lang.IllegalArgumentException: invalid payload
    at example.Parser.decode(...)
    at example.Pipeline.lambda$parse$0(...)
    at java.base/java.util.concurrent.CompletableFuture$UniApply.tryFire(...)
    ...
```

Read from the **outermost error type**, walk down each `Caused by:`, and find the **first application frame** in the relevant cause section:

- `CompletionException`: signals to the caller that the stage completed exceptionally.
- `IllegalArgumentException: invalid payload`: the specific error, containing a useful message.
- `example.Parser.decode`: the business logic location where the error occurred.
- `UniApply.tryFire`: the JDK executing an apply-style dependent stage. This frame helps identify the execution path, but is not where the invalid data was produced.

**Do not assume the "last cause" is always enough to understand the error.** If the application wraps `InvalidOrderException("orderId=...")` around an `SQLException`, the business wrapper contains critical context. You need to read the **entire causal chain** and the message of each layer; look at the root cause to identify the failure source, then return to the outer layers to understand the request, stage, retry, and resources.

Besides `Caused by`, Java has **suppressed exceptions** (displayed as `Suppressed:`), which often come from closing resources in `try-with-resources` or when code calls `addSuppressed`. They differ from causes: the resource-closing error is kept alongside the primary error rather than replacing it. When a trace is abbreviated, many logging tools collapse duplicate frames with `... N more`; this is a display convention and does not mean any frames have been lost.

A stack trace from a single thread **does not automatically reconstruct the entire async history** across other threads. When a callback runs on a new executor, the original calling frames may not appear in the exception thrown on the worker. You need to combine stage names, request IDs, sanitized input data, and completion events to reconstruct the path.

## 4. Standalone Java 17 Example: Seeing `join()`, `get()`, and Origin Clearly

The example below uses a single-worker executor and intentionally throws an exception in the parse stage. The code **does not print the full stack trace** so that stdout remains deterministic across machines; instead, it prints the wrapper type, cause, message, and first application frame. You can enable `printStackTrace` when you need to inspect the full trace.

Save as `FutureFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FutureFailureDemo {
    static Integer parse(String payload) {
        throw new IllegalArgumentException("invalid payload");
    }

    static Throwable unwrapAsyncWrapper(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "parse-worker"));
        try {
            CompletableFuture<Integer> stage =
                    CompletableFuture.supplyAsync(() -> "bad", executor)
                            .thenApplyAsync(FutureFailureDemo::parse, executor);

            try {
                stage.join();
            } catch (CompletionException failure) {
                Throwable cause = unwrapAsyncWrapper(failure);
                StackTraceElement origin = cause.getStackTrace()[0];
                System.out.println("join=" + failure.getClass().getSimpleName());
                System.out.println("cause=" + cause.getClass().getSimpleName());
                System.out.println("message=" + cause.getMessage());
                System.out.println("origin=" + origin.getClassName()
                        + "." + origin.getMethodName());
            }

            try {
                stage.get();
            } catch (ExecutionException failure) {
                Throwable cause = unwrapAsyncWrapper(failure);
                System.out.println("get=" + failure.getClass().getSimpleName());
                System.out.println("getCause=" + cause.getClass().getSimpleName());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted while waiting", interrupted);
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac FutureFailureDemo.java
java FutureFailureDemo
```

Deterministic stdout:

```text
join=CompletionException
cause=IllegalArgumentException
message=invalid payload
origin=FutureFailureDemo.parse
get=ExecutionException
getCause=IllegalArgumentException
```

The `origin` line points to the method that **actually threw the error**, which differs from where `join()` was called. In practice, to view all frames, replace the short print statements with:

```java
failure.printStackTrace(System.err);
```

The snippet above is **only a line inserted into a catch block**, not a standalone Java program. The full stack will show the wrapper, `Caused by`, worker/executor frames, and source/JDK-dependent line numbers. Do not write tests that compare an entire stack trace verbatim; assert on the exception type, cause chain, message, and key stage context instead.

**Why use `thenApplyAsync(..., executor)`?** This call requests that parsing run via the chosen executor, clearly simulating an asynchronous boundary. If you use `thenApply`, the dependent action may be executed by the thread completing the parent stage or by the thread registering the action when the parent is already complete. You cannot infer from the name `thenApply` that the callback always runs on the thread that created the pipeline.

## 5. Error Location in a Stage Chain

`CompletableFuture` represents a **dependency graph**. Each stage can succeed or complete exceptionally. A failed stage typically prevents normal dependent stages from running their bodies:

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> readPayload(), executor)
                .thenApply(payload -> decode(payload))
                .thenApply(value -> enrich(value))
                .thenApply(value -> render(value));
```

This is an **illustrative pattern** requiring `executor` and the corresponding functions. If `decode` throws an error, the success-path actions `enrich` and `render` do not run; the final future completes exceptionally. When you only have the stack trace at the end, do not conclude that `render` failed: trace the cause and determine which stage actually ran.

Distinguish between operators:

| Operator | When upstream succeeds | When upstream completes exceptionally |
| --- | --- | --- |
| `thenApply(fn)` | Runs `fn` and forwards the result | `fn` is not run; error propagates to dependent stage |
| `thenCompose(fn)` | Runs `fn` returning a future and "flattens" that future | `fn` is not run; error propagates; if the inner future fails, the new stage also fails |
| `thenAccept(action)` | Runs action with the result | Skips action, error propagates |
| `thenRun(action)` | Runs action without receiving the result | Skips action, error propagates |
| `whenComplete(observer)` | Observes result, normally preserves outcome | Observes error, normally preserves outcome; an observer throwing an error has specific semantics |
| `handle(handler)` | Allows mapping the value to a new result | Allows recovery/transformation; if the handler returns a fallback, downstream no longer sees the old error |
| `exceptionally(handler)` | Does not run handler | Runs on exceptional completion, can return a fallback or rethrow an error |

**`thenCompose` differs from `thenApply` for functions returning a future:** `thenApply` can produce a `CompletableFuture<CompletableFuture<T>>`, making it easy to forget to observe the inner future; `thenCompose` flattens it, making the inner future's exception visible on the final stage. When a callback returns a future but the pipeline only waits on the outer future, inner errors can be missed.

Errors originating in `whenComplete` also require careful reading. If upstream succeeds and the observer throws an exception, the stage returned by `whenComplete` fails with the observer's exception. If upstream already failed and the observer also throws an exception, the new stage normally preserves the upstream error per the API contract; you cannot use `whenComplete` to recover with a replacement result. Use `handle` or `exceptionally` when you want to **actively change the outcome**.

## 6. Adding Breadcrumbs to Identify Which Stage and Request Failed

Because the worker's call stack does not contain the full call path from the request thread, logs should include:

- **Correlation/request ID** to connect events before and after an asynchronous boundary.
- **Clear stage name**: `fetch`, `decode`, `validate`, `persist`, etc.
- **Non-sensitive operation context**: task type, coarsened business key, attempt number, deadline, executor or pool name.
- **Thread name** as supplementary info; threads can be reused across many requests.
- **The actual `Throwable` object** so the logger prints the causal chain, rather than only `failure.getMessage()`.

**Illustrative** example placed inside a class with `logger` and `requestId` variables, not a standalone runnable file:

```java
CompletableFuture<Result> observed = source.whenComplete((value, failure) -> {
    if (failure != null) {
        logger.log(
                java.util.logging.Level.SEVERE,
                "requestId=" + requestId + ", stage=decode",
                failure);
    }
});
```

`source` must be a `CompletableFuture<Result>`. Keep observer callbacks short, non-blocking, and non-throwing when logging. If a callback throws an error, the pipeline returned by `whenComplete` may change state and become harder to diagnose. Place logging **at appropriate boundaries** to avoid logging the same exception at every stage and producing dozens of duplicate entries.

If you need to wrap an error with business context, **preserve the cause**:

```java
static Item decodePayload(String payload, String requestId) {
    try {
        return decode(payload);
    } catch (IllegalArgumentException failure) {
        throw new DecodeStageException(
                "stage=decode, requestId=" + requestId,
                failure);
    }
}
```

This is an illustrative snippet; `Item`, `decode`, and `DecodeStageException` are application types/functions. `DecodeStageException` must have a constructor accepting `String` and `Throwable` and pass the cause to `super(message, cause)`. That way, the trace retains both the stage context and the technical cause. Replacing it with `throw new RuntimeException(failure.getMessage());` loses the original trace and exception type/cause.

Do not turn every error into `"unknown error"` or catch `Throwable` and return a fallback without an explicit recovery policy. In particular, an `Error` such as `OutOfMemoryError` usually needs to propagate through an appropriate fatal-error mechanism; do not treat it like a normal data error.

## 7. Unwrapping Exceptions: Doing It Right Without Losing Context

A diagnostic utility can strip standard async wrappers:

```java
static Throwable unwrapCompletion(Throwable failure) {
    Throwable current = failure;
    while ((current instanceof java.util.concurrent.CompletionException
            || current instanceof java.util.concurrent.ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

This is a **snippet you can place in a Java class**, not a standalone runnable file. Only unwrap **known wrappers**—do not automatically walk down to the deepest cause of every business exception, or you will lose `DecodeStageException`, `RetryExhaustedException`, or `RequestContextException` along the path.

Note that `CompletionException` can be intentionally thrown by application code to represent an async error. It is not always created by the JDK at the same site. An `ExecutionException` may wrap a `CompletionException` or the original exception depending on the forwarding path, so looping to unwrap both types is useful for cause reporting. **After unwrapping for classification**, still log the original received exception if you need to preserve the full causal chain.

**Do not turn error classification into business logic based solely on messages:** exception text can change across JDKs, libraries, or locales. Use types, error codes/application contracts, and dedicated metadata when retry or error-reporting behavior is needed.

## 8. Multiple Futures Failing: `allOf` Does Not Build a Complete List Automatically

`CompletableFuture.allOf(a, b, ...)` creates a future that completes when all components complete; if at least one component completes exceptionally, the combined future also completes exceptionally. **It does not provide a list of all failure causes out of the box.** Calling only `allOf(...).join()` and reading a single cause can miss failures from the remaining tasks.

Standalone Java 17 example, save as `FanInFailureDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FanInFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first =
                CompletableFuture.failedFuture(
                        new IllegalStateException("task A failed"));
        CompletableFuture<String> second =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("task B failed"));

        CompletableFuture<Void> all = CompletableFuture.allOf(first, second);
        System.out.println("allFailed=" + all.isCompletedExceptionally());

        List<CompletableFuture<String>> tasks = List.of(first, second);
        for (int index = 0; index < tasks.size(); index++) {
            try {
                tasks.get(index).join();
            } catch (CompletionException failure) {
                Throwable cause = failure.getCause();
                System.out.println("task" + (index + 1) + "=" + cause.getMessage());
            }
        }
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
allFailed=true
task1=task A failed
task2=task B failed
```

The example intentionally uses two already-completed failed futures so the output is deterministic. In real systems, each task may fail, be canceled, succeed, or still be pending; to tally each task, keep references to the individual futures and inspect them **once the required state is ready**. Do not treat the cause from `allOf` as the "only error" and ignore the remaining tasks. `anyOf` completes when **one** future completes first, so it even less implies that the entire group has finished.

For real fan-out/fan-in pipelines, consider assigning a distinct ID to each branch, logging or storing a `Result<T>` representing success/failure, and aggregating errors in a clear order. If you want to throw a single aggregate exception with multiple errors, you can pick a primary error and call `addSuppressed` for the secondary ones, but make sure the policy is explicit and avoid storing sensitive data in exception messages.

## 9. Timeout, Cancellation, and Interrupted Waiting Are Easy to Misinterpret

### 9.1. `get(timeout, unit)` Only Limits Wait Time

`future.get(100, TimeUnit.MILLISECONDS)` can throw `TimeoutException` because the caller did not receive a result within 100 ms. **The underlying future has not necessarily completed**, and the executor task may still be running. If the task finishes later with another error, you need a separate completion-observation mechanism; otherwise, the real exception will be lost.

`CompletableFuture.orTimeout(duration, unit)` (JDK 9+) behaves differently: it completes **that `CompletableFuture` itself** exceptionally with `TimeoutException` when the deadline expires if it has not already completed. `completeOnTimeout(value, ...)` substitutes a default value instead. Neither guarantees terminating I/O or interrupting the underlying source task just because the future reached a timeout result. When real work needs to be canceled, you must design cancellation/deadlines down to the underlying tasks and resources.

### 9.2. Cancellation Does Not Mean the Worker Has Stopped

`future.cancel(true)` transitions the future to the canceled state if successful. Specifically for `CompletableFuture`, the `mayInterruptIfRunning` parameter **does not control interrupting** the executing work the way a `FutureTask` can. Do not infer from `CancellationException` that the thread or network call has stopped. Dependent stages may complete exceptionally with a wrapper carrying the cancellation cause.

If a callback on a canceled future performs cleanup, make it idempotent; cancellation, timeout, and normal completion can race. Do not release a permit, close a connection, or report success twice due to competing handlers.

### 9.3. Handling Interruption Properly

`Future.get()` can throw `InterruptedException` when the waiting thread is interrupted. When it cannot be handled at the current layer, you usually need to **restore the interrupt flag** and propagate the signal to the caller:

```java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("wait interrupted", interrupted);
} catch (ExecutionException failed) {
    throw new IllegalStateException("operation failed", failed.getCause());
}
```

This snippet is an **illustrative pattern inside a method with a suitable `future`**, not a standalone runnable file. In environments that use checked exceptions or have a dedicated cancellation policy, you can declare and throw `InterruptedException` for the caller to handle. Never swallow the interrupt and keep waiting indefinitely.

**`join()` has no timed wait variant:** if you need an explicit, accurate deadline for the waiting thread, use `get(timeout, ...)` or design appropriate completion timeouts and cancellation. Timeouts/waiting are only one dimension of the system; latency, queue wait, retries, and end-to-end deadlines should be tracked consistently.

## 10. ThreadLocal, Logging Context, and Async Boundaries

Some systems store `requestId` in a `ThreadLocal` and expect callbacks on other threads to read that value automatically. However, `ThreadLocal` is state bound to the **current thread**, and executors typically reuse threads across many requests. `thenApplyAsync` or `supplyAsync` moves work to another thread, so context is not transferred automatically; `InheritableThreadLocal` is also unreliable for propagating context through an existing thread pool.

The simplest approach is to **pass context as immutable data**:

```java
record RequestContext(String requestId) {}

static CompletableFuture<String> runPipeline(
        RequestContext context,
        java.util.concurrent.Executor executor) {

    return CompletableFuture.supplyAsync(() -> "payload", executor)
            .thenApply(payload -> decode(payload, context.requestId()));
}
```

This is an **illustrative snippet** in a Java 17+ class requiring a `decode` definition. `context` is explicitly captured in the callback and does not depend on which worker was used by a previous request in the thread pool. If the application uses a tracing/MDC system, you need an explicit **capture/restore/clear** mechanism at the executor boundary and ensure cleanup in `finally` to prevent context leakage to subsequent tasks.

Thread names can help identify the worker pool (`ForkJoinPool.commonPool-worker-*` or custom threads), but names are not unique request IDs. For `CompletableFuture.*Async` without an explicit executor, the default execution policy typically uses `ForkJoinPool.commonPool()` (with the specification's exception regarding common pool parallelism). When investigating reproducibility and bottlenecks, **passing an explicit executor** makes it clear where the system is running and makes capacity easier to control.

## 11. Common Pitfalls When Attaching Observation Callbacks

### 11.1. Using `exceptionally` to Log and Accidentally Swallowing the Error

```java
CompletableFuture<String> recovered = source.exceptionally(failure -> {
    log(failure);
    return "OK";
});
```

**Illustrative** snippet requiring `source` and `log`. If upstream fails, the `recovered` future will succeed with `"OK"`. Downstream no longer receives an exceptional completion. That is actual recovery, which should only be done when a fallback is the contractually intended behavior—for example, optional data with a safe default value. If the goal is only observation, use `whenComplete` and let the outcome propagate.

### 11.2. Logging Only the Message

```java
System.err.println(failure.getMessage());
```

This loses the exception type, stack, cause, and suppressed exceptions. With logging APIs that accept a `Throwable`, pass the full error object:

```java
logger.log(java.util.logging.Level.SEVERE, "stage=parse failed", failure);
```

These two snippets are **non-standalone illustrations**, requiring `failure` or `logger` respectively. Production systems must control sensitive data in logs and avoid spamming at every stage.

### 11.3. Forgetting to Wait on or Observe a Future

`CompletableFuture.runAsync(() -> doWork());` returns a future immediately. If the caller discards the reference and there is no terminal observer or owner managing its lifecycle, errors in the task may remain in the future's state without being clearly reported in the original calling flow. Do not assume "no stack trace on the console" means the task succeeded. Explicitly design where `join`/`handle`/`whenComplete` lives and who owns error reporting.

### 11.4. Attaching an Observer Without Tracking the New Future

`thenApply`, `whenComplete`, `handle`, and `exceptionally` all return **a new future**. A callback itself can introduce a new failure; if you only observe the original future and ignore the new one, callback errors go unmonitored. Identify the **terminal future** that the caller awaits and ensure key stages are observed.

### 11.5. Blocking or Retrying Directly Inside a Callback

Calling `join()` inside a stage on the same small executor to wait for other work running on that very executor risks starvation or deadlock. Tightly retrying inside `exceptionally` can trigger a retry storm. Prefer non-blocking composition (`thenCompose`), bounded retries/backoff, deadlines, and clear ownership for background tasks.

## 12. Practical Workflow for Investigating an Async Error

Suppose you receive an alert: `CompletionException` from `CompletableFuture.join()`, but it is unclear which stage failed. Follow these steps in order:

1. **Ensure you have the full throwable:** collect the trace including `Caused by` and `Suppressed`, eliminating message-only logging. Keep logs/correlation IDs for the same unit of work.
2. **Separate observation site from throw site:** identify `join()`/`get()` in the caller, expand each `Caused by`, and find the first application frame at each layer.
3. **Identify the stage:** trace back through the `supplyAsync → thenApply → thenCompose → whenComplete...` chain; check which stages ran and which were skipped due to an exceptional upstream.
4. **Check thread/executor:** normal stage, `Async` stage, custom executor, shutdown/rejection state, queue saturation, and worker starvation. Note that a callback may run on the registering thread if the parent has already completed.
5. **Check failure type:** data error, downstream error, cancellation, timeout, or interruption. Separate a real task error from a timeout that occurred only on the caller.
6. **Inspect parallel branches:** for `allOf`, inspect each child future; do not treat the aggregate's single cause as the whole picture.
7. **Verify handling policy:** did `handle`/`exceptionally` turn the error into a fallback? Did a `whenComplete` observer throw a new error? Was a terminal future dropped without logging?
8. **Reproduce deterministically:** use a deterministic executor, `CompletableFuture.completedFuture` or `failedFuture`, control completion manually, and assert exception types/cause chains rather than relying on arbitrary timing.

When reporting the root cause, use a concrete statement such as: "Stage `decode` for request ID X ran on executor Y and threw `IllegalArgumentException` due to an invalid payload; the final future reported `CompletionException` at `join()` in the caller." This phrasing distinguishes the cause, propagation path, and detection point.

## 13. Testing Failure Paths Without Timing Dependencies

A good unit test for an asynchronous pipeline should control outcomes deterministically without needing `Thread.sleep()`. JDK 17 example using a `CompletableFuture` explicitly completed exceptionally:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FailurePropagationTestDemo {
    public static void main(String[] args) {
        CompletableFuture<String> upstream = new CompletableFuture<>();
        CompletableFuture<Integer> downstream = upstream.thenApply(String::length);

        upstream.completeExceptionally(
                new IllegalStateException("upstream failed"));

        try {
            downstream.join();
            throw new AssertionError("Expected exceptional completion");
        } catch (CompletionException expected) {
            Throwable cause = expected.getCause();
            if (!(cause instanceof IllegalStateException)
                    || !"upstream failed".equals(cause.getMessage())) {
                throw new AssertionError("Unexpected cause", expected);
            }
            System.out.println("failure propagated");
        }
    }
}
```

Run:

```bash
javac FailurePropagationTestDemo.java
java FailurePropagationTestDemo
```

Stdout:

```text
failure propagated
```

Here `String::length` does not run because upstream already completed exceptionally. Tests can go further by using an `AtomicInteger` counter in the callback to assert `0` invocations. Use `CompletableFuture.failedFuture(cause)` (Java 9+) when you do not need to control completion timing; use `new CompletableFuture<>()` when you need to simulate races between branches.

Cases that should have dedicated tests:

- **Failure at source:** `supplyAsync`/`runAsync` throws an error; dependent success-only stages do not run and the terminal future completes exceptionally.
- **Failure at intermediate stage:** a `thenApply` callback throws an exception; `join` yields `CompletionException` and the root cause is preserved.
- **Recovery:** `exceptionally`/`handle` returns a fallback only when contractually decided; no exception remains on the terminal future.
- **Observer:** `whenComplete` logs without swallowing the exception; the logging callback does not throw.
- **Failure in inner future:** using `thenCompose`, verify exceptional completion propagates properly.
- **Multiple failures:** `allOf` reports overall failure; each child retains its own reason.
- **Cancellation/timeout:** cancel is not misinterpreted as the task having stopped; deadlines are tested with a controllable clock/scheduler when needed.
- **Interrupted wait:** the thread calling `get()` receives `InterruptedException`, and the interrupt preserve/propagate policy is followed.

Do not assert on verbatim stack traces or assume `CompletableFuture.java:XXXX` line numbers stay fixed. When verifying the throw site, assert on cause type, message/context, and a few stable application frames; leave integration/stress tests to validate real scheduling conditions.

## 14. Quick Reference Table

| Symptom | How to read / check |
| --- | --- |
| Trace starts at `CompletableFuture.join` or `reportJoin` | This is usually the **observer**; inspect `Caused by` to find where the error was created |
| `ExecutionException` appears at `get()` | Call `getCause()` and read the causal chain |
| Exception only appears inside a `whenComplete` callback | Determine whether it is an upstream error observed by the callback or a new error thrown by the observer itself |
| Nested `CompletionException` | Unwrap only standard wrappers; still keep and log the full trace |
| No `supplyAsync` calling frame in the cause | Thread hop broke the direct call stack chain; add correlation/stage breadcrumbs |
| `allOf` returns one cause while multiple tasks failed | Inspect each child future after completion |
| Caller receives `TimeoutException` | Check whether the timeout came from `get(timeout)` or `orTimeout`; verify if the background task is still running |
| `CancellationException` | Distinguish the future's canceled state from whether the actual worker/I/O stopped |
| No logs when an async task fails | Is the future's terminal outcome being observed/recorded? |
| Used `exceptionally` but downstream reports success | The handler may be returning a fallback and actively recovering |
| Errors occur randomly under high pool load | Check scheduler, queue, rejection, starvation, shared state, and races; do not guess from the trace alone |

**Key takeaway:** A stack trace in async Java is evidence organized by **exception/cause chains and stage boundaries**, not a single linear call stack of the whole request. To diagnose accurately, identify the root exception, preserve the causal chain, attach stage/correlation IDs, understand `join()`/`get()`/callbacks, and distinguish real failures from timeouts or cancellations.
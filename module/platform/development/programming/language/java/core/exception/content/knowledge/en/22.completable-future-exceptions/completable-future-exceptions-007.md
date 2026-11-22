# whenComplete: Observing Results and Errors Thrown During Observation

## 1. Purpose and Meaning in Java CompletableFuture

`CompletableFuture<T>` represents a result that may not be ready yet, or that completes normally or exceptionally. When designing an asynchronous chain, we often want to **observe** the result at a certain point to log, record metrics, emit diagnostic signals, or clean up context, while preserving the primary computation result.

`whenComplete((value, error) -> { ... })` provides exactly one observation point for both branches:

- When the source stage completes normally, the callback receives `value` and `error == null`.
- When the source stage completes exceptionally, the callback receives a non-`null` `error`; `value` does not contain a success result.
- The callback returns `void`: it is not a function that transforms `T` into another type, and it does not turn a failure into a success by default.
- Calling `whenComplete` itself returns a **new CompletionStage/CompletableFuture** representing the completion of the observation. If the observation action **also throws an exception**, the state of the new stage follows the error precedence rules explained below.

It is essential to distinguish between two kinds of failure: **errors from the source work** and **errors originating in the observation callback itself**. Ignoring this distinction can cause an application to misclassify a metric-recording error as a business error, or lose secondary error information when both the source and the observer fail.

After this lesson, you will be able to read the `whenComplete` contract in Java 17+ accurately, understand the differences between `whenComplete`, `handle`, and `exceptionally`, determine which error is preserved when an observer throws an exception, write runnable examples, and structure error recording safely.

## 2. Signature and the Two Callback Parameters

The core API declaration is:

~~~java
CompletionStage<T> whenComplete(
        BiConsumer<? super T, ? super Throwable> action);
~~~

This is an **illustrative signature conveying the meaning of the `CompletionStage<T>` interface**, not a standalone program declaration. When using `CompletableFuture<T>`, the corresponding method returns `CompletableFuture<T>`. `BiConsumer` is a callback that accepts **two parameters and returns no value**.

A common usage expression:

~~~java
CompletableFuture<String> observed = source.whenComplete((value, error) -> {
    if (error == null) {
        System.out.println("result = " + value);
    } else {
        System.err.println("failed: " + error);
    }
});
~~~

This is a fragment assuming `source` is a `CompletableFuture<String>` and the corresponding imports are present. `observed` is a **new** stage. It is not `source` itself, even though it carries the same `String` value type. In practice, multiple stages can observe the same source, and callback ordering should not be assumed unless an explicit dependency relationship is established.

### 2.1. Exact Meaning of `value` and `error`

| Source completion | `value` in callback | `error` in callback | What to understand |
| --- | --- | --- | --- |
| `complete("OK")` | `"OK"` | `null` | Source succeeded with a value |
| `complete(null)` | `null` | `null` | Source **still succeeded** with value `null` |
| `completeExceptionally(exception)` | Typically `null` | `Throwable` associated with the error | Source completed exceptionally |
| Successful `cancel(...)` | No normal result | Cancellation error / representation of exceptional completion | Cancellation is also a form of exceptional completion for the observer to recognize |

**Only use `error == null` as the indicator of success**. Do not use `value != null`, because a `CompletableFuture<Void>` or a stage that validly returns `null` will complete normally with `value == null`.

`Throwable error` may be the original exception or a `CompletionException` wrapping the original exception, depending on how the source or preceding stage was completed. When categorizing error types, handle wrappers according to the contract and inspect the `cause` chain rather than comparing text strings from `getMessage()`. Do not call `error.getCause().getMessage()` without checking whether `error` and `getCause()` are non-`null`.

## 3. Fundamental Rule: Observation Callback and Dependent Stage

Consider:

~~~text
CompletionStage<T> source
          |
          +--- whenComplete(action) ---> CompletionStage<T> observed
                                         |
                                         +--- join()/get()/next stage
~~~

The `observed` stage completes only after `source` has completed and the `whenComplete` action has executed or failed according to the completion mechanism. Therefore, if you need to guarantee that the observer has finished running **before executing the next step**, wait on or chain **`observed`**, not just `source`.

A `source.join()` call may return before an asynchronous `whenCompleteAsync` callback has had a chance to run. Even with the synchronous `whenComplete` callback, when multiple threads compete to execute completions and dependents, you should not rely on incidental scheduling. Interacting operations need explicit dependency relationships.

`whenComplete` does not automatically create a "reliable audit log" of system state. It only provides a point to run Java code in the stage lifecycle. If the process terminates or a logging error occurs, there is no guarantee that all events were durably persisted.

## 4. When the Observer Runs Normally: Source Result and Error Are Preserved

If the `whenComplete` callback completes normally (without throwing an exception):

- Source **succeeds**: the returned stage also completes normally with the **same `T` value**.
- Source **fails**: the returned stage still completes exceptionally, reflecting the error from the source.
- Source **is cancelled**: the action may receive cancellation error information; the dependent stage still carries the corresponding exceptional state. Do not assume the dependent stage has the same `isCancelled()` flag as the source; cancellation observation and exception types can differ across wrapping layers.

Fragment example:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("saved");

CompletableFuture<String> observed =
        source.whenComplete((value, error) ->
                System.out.println("observer saw: " + value));

System.out.println(observed.join());
~~~

This is an illustrative snippet that can be placed in `main` after importing `java.util.concurrent.CompletableFuture`. With `source` already completed normally and the callback throwing no error, the output is:

~~~text
observer saw: saved
saved
~~~

The value `saved` is not produced by `whenComplete`; it comes from `source`. The callback only observes. If you want to **replace** the result, choose `thenApply` or `handle` as appropriate, instead of trying to return a `String` from a `whenComplete` lambda (which requires `void` behavior).

## 5. When the Observer Throws an Exception: The Most Important Precedence Rule

The `CompletionStage.whenComplete` contract specifies: **if the supplied action throws an exception, the resulting stage completes exceptionally with the action's exception, unless the source stage already completed exceptionally; in the case where the source already failed, the source error takes precedence**.

This is the core of the topic. There are four cases:

| Source before callback | Observation action | Outcome of the stage returned by `whenComplete` |
| --- | --- | --- |
| Succeeds | Succeeds | Succeeds with the source value |
| Succeeds | **Throws exception B** | **Fails with B** |
| **Fails with A** | Succeeds | **Fails with A** |
| **Fails with A** | **Throws exception B** | **Fails with A (source error takes precedence)** |

This precedence rule prevents the observer from masking the primary error A when the source work itself has already failed. However, you **should not expect** Java to automatically log B, preserve B as a `suppressed exception`, or emit an event about B across all implementations. If knowing that "the observer also failed" is valuable, record B through a separate, explicit, and safe observation path.

### 5.1. Source Succeeds, Observer Fails

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> observed = source.whenComplete((value, error) -> {
    throw new IllegalArgumentException("metric sink failed");
});
~~~

This is a fragment with `CompletableFuture` imported and no exception-catching code. When calling `observed.join()`, the caller receives a `CompletionException` with the corresponding cause `IllegalArgumentException`. However, `source.join()` still returns `"OK"`: the source computation **succeeded**, and it is the secondary observation branch that caused the new stage to fail.

This is why you should not attach a metrics callback that can throw an exception and then call `observed.join()` to confirm that business work completed: the system could report the operation as failed **solely because logging/metrics failed**, even though the primary task succeeded. Sometimes this is the intended policy (mandatory audit), but it must be decided by contract.

### 5.2. Source Already Failed, Observer Also Fails

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(new IllegalStateException("load failed"));

CompletableFuture<String> observed = source.whenComplete((value, error) -> {
    throw new IllegalArgumentException("metric sink failed");
});
~~~

This fragment creates a failed source first. When the caller invokes `observed.join()`, the source error `IllegalStateException("load failed")` retains precedence, and the error from the observer does not replace the primary outcome.

This **does not mean the observer did not run**: the action is still invoked and can still throw an error; it is simply that exception B does not become the primary cause of `observed`. Do not treat the log line for A as proof that the metrics system had no issues. If you must guarantee that observation failures are reported, you need a separate monitoring channel or explicit logic to catch B.

### 5.3. Why `source` and `observed` Must Be Distinguished

`whenComplete` does not mutate the terminal state of `source`. It creates a dependent stage whose state can **differ** from the source when the observer fails. Code that only observes `source` will see success; code that observes `observed` may see failure. Therefore, when designing an API, decide whether callers actually need to treat observation as a requirement for the work to be considered successful.

## 6. Complete, Compilable, Runnable Java 17 Example

The following program verifies five scenarios:
1. Source succeeds and observer only prints the result.
2. Source fails and observer inspects the exception type.
3. Source succeeds but observer throws an exception.
4. Source fails **and** observer throws a different exception: the source error retains precedence.
5. Chaining `whenComplete` with `exceptionally` to record the error and then intentionally turn it into a fallback value.

Save as **`WhenCompleteObservationDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class WhenCompleteObservationDemo {
    static String messageOf(CompletableFuture<?> future) {
        try {
            future.join();
            return "SUCCESS";
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            return cause.getClass().getSimpleName() + ": " + cause.getMessage();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> success = CompletableFuture.completedFuture("OK");
        CompletableFuture<String> watchedSuccess = success.whenComplete((value, error) -> {
            System.out.println("observe success: " + value + ", error=" + error);
        });
        System.out.println("result: " + watchedSuccess.join());

        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(new IllegalStateException("load failed"));
        CompletableFuture<String> watchedFailure = failed.whenComplete((value, error) -> {
            System.out.println("observe failure: " + error.getClass().getSimpleName());
        });
        System.out.println("source failure: " + messageOf(watchedFailure));

        CompletableFuture<String> badObserver = success.whenComplete((value, error) -> {
            throw new IllegalArgumentException("metrics failed");
        });
        System.out.println("observer failure: " + messageOf(badObserver));
        System.out.println("original success: " + success.join());

        CompletableFuture<String> bothFail = failed.whenComplete((value, error) -> {
            throw new IllegalArgumentException("observer also failed");
        });
        System.out.println("primary failure: " + messageOf(bothFail));

        CompletableFuture<String> recovered = failed
                .whenComplete((value, error) -> System.out.println("logged failure"))
                .exceptionally(error -> "fallback");
        System.out.println("recovered: " + recovered.join());
    }
}
~~~

From the directory containing the file with JDK 17 or newer:

~~~bash
javac --release 17 WhenCompleteObservationDemo.java
java WhenCompleteObservationDemo
~~~

Exact stdout:

~~~text
observe success: OK, error=null
result: OK
observe failure: IllegalStateException
source failure: IllegalStateException: load failed
observer failure: IllegalArgumentException: metrics failed
original success: OK
primary failure: IllegalStateException: load failed
logged failure
recovered: fallback
~~~

### 6.1. Step-by-Step Result Analysis

- First two lines: `watchedSuccess` returns the string `OK` from the source. `error=null` indicates the source succeeded.
- Next two lines: `failed` is a source completed via `completeExceptionally` with `IllegalStateException`. `whenComplete` reads the error type, and the new stage still fails with the source error.
- Line `observer failure`: the `success` source still succeeded, but `badObserver` failed because the action threw `IllegalArgumentException`.
- Line `original success`: the `success` source itself still returns `OK`, proving that the observer does not roll back the source's state.
- Line `primary failure`: the action on `bothFail` also throws, but the original failure `load failed` keeps precedence according to the contract.
- Last two lines: `whenComplete` records the failure, and then the `exceptionally` stage receives the error and returns `fallback`; this is an **intentional recovery transition**, not an automatic feature of `whenComplete`.

All sources in this program are completed **before** registering the observers, so there is no contention between multiple workers and stdout is well-defined. In a real system running asynchronously, the log print order of multiple independent stages can be non-deterministic without proper dependency/awaiting relationships.

The `messageOf` method illustrates the case where a future definitely completes with `CompletionException` on `join()`. In a production library, you should also account for `CancellationException` and other error types; `getCause()` should also be checked safely if the error source does not follow the helper's assumptions. Do not copy this helper as a general-purpose handler for every throwable in an application without adding a proper policy.

## 7. How Does `whenComplete` Differ from `handle` and `exceptionally`?

The difference lies in **the purpose of the callback and the return type**:

| API | What does the callback receive? | Intentionally produces a new value? | Behavior when the source fails |
| --- | --- | --- | --- |
| `thenApply(fn)` | Only the `T` value on success | Yes, `T -> U` | Typically skips `fn` and propagates the failure |
| `exceptionally(fn)` | `Throwable` when the source fails | Yes, replaces with a `T` value | Can recover with the value returned by `fn` |
| `handle(fn)` | `T` and `Throwable` | Yes, produces `U` in both branches | Can classify or recover the error into a value |
| `whenComplete(action)` | `T` and `Throwable` | **No**, action returns `void` | Preserves source failure if action does not throw; if both fail, source takes precedence |
| `whenCompleteAsync(action, executor)` | Same as `whenComplete` | No | Same failure semantics, but action is scheduled asynchronously |

### 7.1. When to Use `handle`?

If you want to convert success/failure into a typed `Result`:

~~~java
CompletableFuture<Outcome> mapped = source.handle((value, error) -> {
    if (error == null) {
        return new Succeeded(value);
    }
    return new Failed(error);
});
~~~

This is an illustrative fragment assuming `source` has an appropriate type and `Outcome`, `Succeeded`, and `Failed` are already defined. `handle` is allowed to return an object of a new type for both success and failure. `whenComplete` has no such data-returning path.

If a `handle` callback itself throws an exception, the `handle` stage can fail with that exception even when the source had already failed; **do not mechanically apply `whenComplete`'s source-error precedence rule to `handle`**. This is an important distinction when analyzing errors thrown inside observers.

### 7.2. When to Use `exceptionally`?

If the caller wants to provide a fallback when the source encounters an error:

~~~java
CompletableFuture<String> fallback = source.exceptionally(error -> {
    return "cache value";
});
~~~

This fragment assumes `source` is a `CompletableFuture<String>`. The new result can complete normally even though the source failed. The fallback policy must match business semantics: a payment-creation operation cannot arbitrarily turn a money-transfer error into "succeeded".

### 7.3. When to Use `whenComplete`?

When you want to **observe** without redefining the result:
- Log success/failure and task IDs.
- Record metrics, classify latency, or record error codes.
- Trigger monitoring mechanisms tied to completion.
- Clean up resources owned by the stage, if the callback must always run after completion and cleanup is designed safely.

However, because an observer can fail, decide whether observation errors should affect the returned stage. If logging is best-effort, catch predictable errors inside the observer and manage them via a separate channel. If auditing is mandatory to acknowledge success, letting an audit error fail the new stage **may** be right, but avoid conflating audit errors with source work errors when returning an API response.

## 8. Two Errors Occurring Together: Avoiding Loss of Secondary Information

Consider:
- **A** = error from the source work, such as `IOException("database unavailable")`.
- **B** = error from the observer, such as `RuntimeException("metrics backend down")`.

When both A and B occur, the stage from `whenComplete` prioritizes A. This aligns with the goal of **preserving the primary task's error**, but it does not produce an automatic report of all secondary errors.

### 8.1. Pitfall of Only Observing the New Stage's Result

~~~java
CompletableFuture<String> watched = source.whenComplete((value, error) -> {
    writeAuditRecord(value, error); // May throw.
});
return watched;
~~~

This fragment assumes `source`, `writeAuditRecord`, and a method returning `CompletableFuture<String>`. If `source` has already failed and `writeAuditRecord` also fails, the caller of `watched` will typically only see cause A. Incident B may go unreported through that result channel.

If you need to investigate audit errors separately, you can use a callback like:

~~~java
CompletableFuture<String> watched = source.whenComplete((value, error) -> {
    try {
        audit(value, error);
    } catch (RuntimeException auditFailure) {
        recordAuditFailure(auditFailure);
    }
});
~~~

This is an illustrative fragment with undefined helper methods. This approach intentionally catches `audit` errors and routes them to a separate channel. However, `recordAuditFailure` itself can also fail. Production-grade observability needs a bounded, safe, and reconcilable mechanism; do not push secondary errors into an infinite logging loop or repeatedly call a failing service inside a callback.

If the requirement is that **the audit record must be saved successfully before acknowledging the task**, model the audit as an explicit step with its own result and an appropriate durability protocol. Do not treat a `whenComplete` callback that logs as an atomic data + audit transaction guarantee.

### 8.2. Are Suppressed Exceptions Added Automatically?

Do not assume Java automatically attaches the observer's exception B to A via `getSuppressed()`. The `whenComplete` rule specifies which error takes precedence as the stage outcome; it does not promise callers a structure containing both exceptions. **Try-with-resources** has its own rules for suppressed exceptions when both the body and `close()` throw; do not apply those rules to every `CompletionStage` callback.

If the application needs to retain both A and B, design a `CombinedFailure` or report errors separately using typed data at the orchestration layer, and verify the behavior with tests. When two independent errors occur, you can log B under an observer-error label and continue propagating A with its original cause.

## 9. Observer Failure When the Source Succeeds: Impact on API Results

Suppose an API completes an update operation successfully and then attaches:

~~~java
CompletableFuture<Order> response = saveOrderAsync()
        .whenComplete((order, error) -> metricsClient.record(order, error));
~~~

This is a fragment: `Order`, `saveOrderAsync()`, and `metricsClient` are hypothetical components. If `saveOrderAsync()` succeeds but `metricsClient.record` throws an exception, `response` can fail because of the **observer**, even though the order has already been persisted.

Common consequences:
- The frontend receives an error and retries the order creation operation.
- Retries can create a duplicate order if idempotency is missing.
- Monitoring reports that the business operation failed even though the data write succeeded.
- Operators struggle to distinguish "order write failed" from "metric write failed".

To keep observer errors confined to the observation domain, you need a dedicated handling policy or an audit/metrics flow that is not allowed to alter the business outcome. If mandatory auditing is required, distinguish between **business processing success** and **publication/audit failure**, with stable error codes and reconciliation state.

**Do not catch every `Throwable` in a logger just to always keep the business outcome successful**: `Error` or severe JVM issues generally require a separate strategy; handle exceptions appropriate to your scope.

## 10. Which Thread Does `whenComplete` Run On?

The name `whenComplete` has no `Async` suffix. For non-Async dependent actions, the function may be executed by **the thread that completes the stage**, or another thread participating in the completion call according to `CompletableFuture` rules. If the source is already completed before registration, the callback may execute immediately during the stage-creation call. Therefore:

- Do not assume the callback always runs on the "main thread".
- Do not assume the callback always runs on the "worker executing the source task".
- Do not use code that requires a UI thread or HTTP request context merely because the caller invoked `whenComplete` there.
- Do not perform very long blocking work in the default callback if it could stall the completing thread or the dependent chain.

### 10.1. `whenCompleteAsync` and Executors

Variant:

~~~java
CompletableFuture<String> observed =
        source.whenCompleteAsync((value, error) -> {
            recordMetrics(value, error);
        }, observerExecutor);
~~~

This fragment assumes `source`, `recordMetrics`, and `observerExecutor` are already declared. The action is submitted to run asynchronously via the caller-provided executor. This is useful for offloading time-consuming observation from the thread completing the source task.

However, several issues remain:
- `whenCompleteAsync` **does not make the action "infallible"**. A callback that throws an exception still affects the resulting stage according to the rules already covered.
- The executor may reject the task (for example, if already shut down), causing the dependent stage to fail according to executor semantics.
- If the process exits early, the asynchronous action may not have run yet. Lifecycle management is required if you truly need to wait for the observer to finish.
- If the source completes with an error and the callback also throws, the source-error precedence rule still applies to the action invocation when it runs; however, executor scheduling failures must be handled separately.
- Offloading to another executor does not automatically make logs/metrics durable or ordered relative to business side effects.

If you discard `observed` after calling `whenCompleteAsync`, there is no guarantee the caller will know the callback failed. When the goal is best-effort metrics, a non-propagating error policy may be appropriate; when the goal is mandatory auditing, ensure completion is tracked.

### 10.2. Do Not Rely on the Ordering of Multiple Sibling Observers

~~~java
source.whenComplete((value, error) -> logA(value, error));
source.whenComplete((value, error) -> logB(value, error));
~~~

This is an illustrative fragment. The two callbacks are attached **independently** to the same source; do not assume A will definitely finish before B just because statement A appears earlier in the source code. If ordering is required, create a **dependent chain**:

~~~java
CompletableFuture<T> chain = source
        .whenComplete((value, error) -> logA(value, error))
        .whenComplete((value, error) -> logB(value, error));
~~~

This is an illustrative syntax fragment requiring declarations for type `T`, `source`, and the methods. In the chained model, the second callback runs after the first stage completes. However, if A throws an exception when the source succeeded, B will receive the error from the preceding stage; when the source already failed, the precedence rules continue to apply. This dependency relationship also makes observer errors part of the chain's data flow, so consider your goal carefully.

## 11. Cancellation and Timeout Are Still Exceptional Completions to Observe

With `CompletableFuture`:
- `cancel(...)` causes the future to complete exceptionally with `CancellationException` when cancellation succeeds; it is not guaranteed to interrupt the underlying source work.
- `orTimeout(...)` can cause the future to complete exceptionally with `TimeoutException` after the deadline if not yet completed.
- `completeOnTimeout(value, ...)` can complete the future normally with a fallback value, so `whenComplete` sees **a normal completion**, even though the supplier may still be running.

An observer:

~~~java
CompletableFuture<String> watched = source.whenComplete((value, error) -> {
    if (error == null) {
        recordSuccess();
    } else {
        recordFailure(error);
    }
});
~~~

This fragment assumes the recording methods are already declared. When source cancellation or timeout results in exceptional completion, the observer receives the appropriate `error`. However, **completion of the Future does not prove the underlying worker has stopped**. In particular, a supplier making an HTTP call can continue causing side effects after `orTimeout` causes the future to report a timeout.

If `recordSuccess` runs because `completeOnTimeout("PENDING", ...)` completed the future normally, a metric for "business processing succeeded" can also be misleading: distinguish a fallback value like `PENDING` from an actual result. Do not treat `error == null` as synonymous with "the remote side committed".

### 11.1. `get()`, `join()`, and the Error Types Observed

On an exceptionally completed stage:
- `join()` normally throws `CompletionException` wrapping the original cause; cancellation can throw `CancellationException` directly.
- `get()` throws `ExecutionException` wrapping the original cause when the task fails, can throw `InterruptedException` if the waiting thread is interrupted, and `CancellationException` if cancelled.
- `get(timeout, unit)` also has `TimeoutException` if the caller does not receive a result within the deadline; this is a timeout of **the wait**, and does not itself turn the source into completed exceptionally the way `orTimeout` does.

Do not confuse a `TimeoutException` thrown by `get(timeout)` on the caller with a `TimeoutException` recorded as the source's failure state by `orTimeout`. They share the same exception name, but their lifecycles and impact on the future are different.

## 12. Proper Observability: Intentional Logs, Metrics, and Traces

When using `whenComplete` in real-world systems, useful fields include:

| Field | Example | Purpose |
| --- | --- | --- |
| `taskId` | `job-42` | Correlate a specific task |
| `correlationId` | Request or trace ID | Link components together |
| `outcome` | `SUCCESS`, `FAILED`, `CANCELLED`, `TIMED_OUT` | Accurate classification |
| `errorCode` | `STORAGE_UNAVAILABLE` | Stable error grouping |
| `causeType` | `IOException` | Error diagnosis |
| `elapsedNanos` or latency metric | Elapsed duration | Performance investigation |
| `observerOutcome` | `METRIC_OK` / `METRIC_FAILED` | Distinguish observation incidents from work incidents |

Do not put passwords, tokens, private request payloads, customer data, or raw stack traces into metric labels; many observability systems restrict cardinality, so avoid using a unique `taskId` as a metric label when it can grow unboundedly. Logs can contain appropriate IDs, whereas metrics usually use stable, aggregated labels.

You can measure duration using `System.nanoTime()` at task start and inside the completion callback. However, if the callback is delayed due to a congested executor, the recorded duration may include observer scheduling delay; to accurately measure "when the task completed", instrument the actual completion point or pass a result timestamp. Do not conflate secondary stage latency with the supplier's CPU latency.

### 12.1. When Logging/Metric Code Can Fail

Clearly answer three questions:
1. **Criticality:** Is an observation error allowed to fail the main API?
2. **Boundary:** Who records errors from the observer itself?
3. **Resilience:** If the metric sink is slow or failing, is there an appropriate queue, buffer, circuit breaker, or drop policy?

If best-effort is sufficient, the observer should handle sink errors and not let them break the business path. If auditing is a mandatory requirement, treat it as a managed business/transactional protocol step with its own state rather than an ad-hoc side effect inside `whenComplete`.

Do not create a callback chain that recursively invokes the same future or an infinite retry loop inside the observer when downstream metrics fail. A long-blocking observer can hurt throughput if it runs on the completing thread; if offloaded asynchronously, bound the queue, thread count, and lifecycle so the observability system does not become a source of overload.

## 13. Interaction with `exceptionally`: Stage Order Changes Meaning

The following two chains are not equivalent:

**Chain A: Observe the original error first, then recover**

~~~java
CompletableFuture<String> recovered = source
        .whenComplete((value, error) -> audit(value, error))
        .exceptionally(error -> "fallback");
~~~

**Chain B: Recover first, then observe**

~~~java
CompletableFuture<String> observed = source
        .exceptionally(error -> "fallback")
        .whenComplete((value, error) -> audit(value, error));
~~~

These are two fragments assuming `source` is a `CompletableFuture<String>` and `audit` has compatible parameters; they are not two standalone files.

In A, `whenComplete` sees the **source error** before any fallback happens. However, if the source succeeds and `audit` throws an error, the downstream `exceptionally` may produce the fallback because of the **audit error**, changing the API state in a way the caller did not intend.

In B, `exceptionally` may convert a source error into the `fallback` value first; the downstream `whenComplete` will see a **successful** stage and will no longer directly see the source error. If `audit` throws, the final stage can still fail due to the observer.

Therefore, place observation at the exact point you want to measure:
- **Observe raw errors:** before recovery.
- **Observe final outcomes:** after recovery.
- **Need both:** design two observation points with distinct classification codes, and do not rely on independent callback ordering.

A `whenComplete` used for logging that throws an exception can cause a fallback policy to receive the **logging error** instead of the original service error. Tests must cover this.

## 14. Side-Effect Operations in Callbacks: Not Equivalent to Transactional

The fact that a callback receives a completion notification does not mean all external side effects have been committed or rolled back. For example:

~~~java
CompletableFuture<Order> stage = saveOrderAsync()
        .whenComplete((order, error) -> {
            if (error == null) {
                sendEmail(order);
            }
        });
~~~

This is a fragment: the relevant types and methods are undefined. It carries a clear risk:
- `saveOrderAsync()` has already saved the order successfully.
- `sendEmail(order)` throws an exception or the client times out.
- The returned `stage` may complete exceptionally because of the observer, while the order still exists.
- The caller retries order creation if idempotency and clear rules are lacking.

If email/auditing is critical, a mechanism like a **transactional outbox** can write a "to-be-sent" record in the same DB transaction; a worker sends it after commit and handles duplicates/idempotency. `whenComplete` does not automatically create a transaction spanning the DB and the email system.

For cleanup, a callback can close resources it owns, but keep in mind:
- Do not close shared resources while other stages still need them.
- Cleanup can throw an exception and fail the final stage.
- If both the source and cleanup fail, the source error takes precedence in the `whenComplete` stage; the cleanup error should be recorded separately if needed.
- If cleanup truly must run even when the process is shutting down or across restarts, an in-memory callback alone is not enough.

## 15. Thoroughly Testing Both Source Errors and Observer Errors

Do not write just one test for "observer is called on success". An appropriate QA matrix:

| Scenario | Prediction for `whenComplete` | What to assert |
| --- | --- | --- |
| Source succeeds, observer succeeds | Resulting stage succeeds | Value equals source value |
| Source succeeds with `null` | Observer receives `(null, null)` | Not mistaken for failure |
| Source fails, observer succeeds | Resulting stage fails with source error | Correct cause/type |
| Source succeeds, observer throws B | Resulting stage fails with B | Source remains successful |
| Source fails with A, observer throws B | Resulting stage fails with A | Source A takes precedence |
| Best-effort observer catches sink error | Stage follows source outcome | Secondary channel records sink error |
| `whenCompleteAsync` runs on specific executor | Callback is scheduled and runs | Correct thread/lifecycle observed, no wrong assumptions |
| Observer executor rejects task | Dependent stage fails | Observation infrastructure error is not silently dropped |
| Source is cancelled | Observer sees exceptional completion | Cancellation is not conflated with business failure |
| Source `orTimeout` | Observer sees future timeout error | Do not infer supplier has stopped |
| `exceptionally` before/after observer | Callback sees result at corresponding position | Errors are not unexpectedly masked by recovery |
| Two independent observers | Both may be called | Do not assert order without synchronization |
| Log/audit fails after data commit | Stage may fail due to observer | Committed data is not treated as rolled back |

For stable tests, use `CompletableFuture.completedFuture` and `completeExceptionally` to set up source states deterministically, or use `CountDownLatch` and controlled executors when verifying races. Do not use `Thread.sleep(100)` and assume the observer has definitely run. Use `observed.join()` or a bounded await mechanism when you need to know the observation stage has finished.

JUnit 5 test example (fragment, assuming imports and test class are present):

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ok");
CompletableFuture<String> observed =
        source.whenComplete((value, error) -> {
            throw new IllegalStateException("observer failed");
        });

CompletionException ex = assertThrows(
        CompletionException.class, observed::join);

assertInstanceOf(IllegalStateException.class, ex.getCause());
assertEquals("ok", source.join());
~~~

This is a **non-standalone illustrative test snippet**, requiring JUnit 5 and static imports `assertThrows`, `assertInstanceOf`, and `assertEquals`. It verifies that `observed` fails due to the observer while `source` remains successful. No separate thread is needed to test the exception precedence rule.

### 15.1. Testing When Both A and B Throw

Create a source via `completeExceptionally(A)`, then attach a `whenComplete` action that throws B. Use `observed.join()` and assert that source error A remains the cause of completion. If both errors must be preserved, test the application logic that **explicitly** records B; do not assert that Java automatically adds B to `getSuppressed()` when the contract does not specify it.

## 16. Common Mistakes in Real-World Code

### Mistake 1 — Using `value != null` to Conclude Success

~~~java
future.whenComplete((value, error) -> {
    if (value != null) {
        recordSuccess();
    } else {
        recordFailure(error);
    }
});
~~~

This fragment is wrong if the future can succeed with `null`. It is more accurate to check `error == null`, then classify the business value separately.

### Mistake 2 — Assuming `whenComplete` Consumes/Handles the Source Exception

~~~java
future.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println(error);
    }
});
~~~

The fragment above **observes** but does not recover. If the source fails, the returned stage still fails. To provide a replacement value, use `exceptionally` or `handle` with a clear contract.

### Mistake 3 — Discarding the Returned Stage

~~~java
future.whenComplete((value, error) -> publishAudit(value, error));
return future;
~~~

This fragment assumes `publishAudit` and a matching method signature. The caller receives the source `future`, so **it cannot rely on it** to know whether the audit finished or failed. If auditing is mandatory, return/await the observation stage or design a separate result channel, while addressing error precedence.

### Mistake 4 — Retrying Already-Succeeded Business Work Because the Observer Failed

If order persistence succeeded but the metrics callback failed, retrying order persistence can duplicate side effects. Distinguish source errors from observer errors, and use idempotency for operations with external effects.

### Mistake 5 — Believing Error B Is Always in `getSuppressed()` of A

There is no such general rule for `whenComplete`. To know both A and B, explicitly store, count, or log B in a safe place.

### Mistake 6 — Long-Blocking Callback Slowing Down the Pipeline

Because `whenComplete` can run on the thread completing the stage, an HTTP call from an observer can tie up an important thread. You can use `whenCompleteAsync` with a dedicated executor, but you must manage queues, deadlines, shutdown, and scheduling failures.

### Mistake 7 — Using `whenCompleteAsync` Without Lifecycle Management

An action not yet executed by the scheduler may be dropped when the application exits, or yield a stage failure if the executor no longer accepts work. Do not treat `whenCompleteAsync` as a durable audit solution just because its name contains `Async`.

### Mistake 8 — Logging Only `error.getMessage()` and Dropping the Cause

If `error` is a `CompletionException`, its message may only describe the wrapper type; preserve the typed cause and appropriate task context. Do not use message text as a stable error code, and do not leak sensitive data.

### Mistake 9 — Using `whenComplete` Instead of `handle` for Type Conversion

A `whenComplete` callback returns `void`, so you cannot `return new Failure(...)` to turn an error into a `Result`. Choose `handle` and return a typed result for each branch.

### Mistake 10 — Treating Independent Callback Order as Deterministic

When multiple observers are registered on the same source, do not rely on ordering if they are not chained sequentially. With chained stages, remember that an earlier callback throwing an error will affect subsequent callbacks.

## 17. Decision Tree for Using `whenComplete`

~~~text
Want to process a CompletableFuture result?
|
+-- Want to transform a success value? -> thenApply / thenCompose
|
+-- Want to turn a failure into a fallback? -> exceptionally
|
+-- Want to turn both success/failure
|   into a new typed result? -> handle
|
+-- Only want to observe / update logs or metrics?
    |
    +-- Lightweight, non-blocking callback -> whenComplete
    |
    +-- Need a dedicated executor -> whenCompleteAsync(action, executor)
    |
    +-- Mandatory durable observation?
        -> design separate audit/outbox/job state,
           with error tracking and recovery mechanisms
~~~

Design guidance diagram. A complete API may use **multiple coordinated stages**: process work with `thenCompose`, observe raw failures with `whenComplete`, convert to `Result` with `handle`, and then record final metrics. What matters is understanding **the chaining order and errors from the callbacks themselves**.

## 18. Production Readiness Checklist

1. **Check the state correctly:** `error == null` indicates normal completion; `value` can be `null` even on success.
2. **Do not confuse observation with recovery:** `whenComplete` does not turn a source failure into a success.
3. **Understand callback error rules:** source succeeds + observer fails → returned stage fails due to observer; source fails + observer fails → source error takes precedence.
4. **Distinguish the two stages:** `source` and `observed` can hold different outcome states.
5. **Define whether observer errors affect business outcomes:** best-effort logging differs from mandatory auditing.
6. **Do not lose error B:** if observation errors need monitoring, record them explicitly; do not assume the runtime adds suppressed exceptions.
7. **Know which thread runs the action:** `whenComplete` does not guarantee a specific thread; `whenCompleteAsync` requires an executor with a clear lifecycle.
8. **Do not block the completing thread for too long:** bound I/O, metrics, and callbacks; consider a dedicated executor when needed.
9. **Do not equate Future timeout/cancel with a stopped worker:** the observer only knows the completion state of the tracked future.
10. **Place observers in the right position:** before recovery to see raw errors, after recovery to see final outcomes; remember that a throwing observer also alters downstream stage outcomes.
11. **Observe the returned stage when required:** do not ignore observer errors if they are part of the contract.
12. **Test all four source/observer combinations**, plus null success, cancellation, timeout, async executor, and post-commit side effects.

### Practice Exercise

An API `createInvoiceAsync()` returns `CompletableFuture<Invoice>`. The system wants to record metrics and audit logs upon completion, while ensuring duplicate invoices are not created if logging fails.

1. Write two pipeline versions: `whenComplete` for best-effort metrics and a mandatory audit step with its own state.
2. Test all four combinations: invoice creation succeeds/fails; metrics succeed/fail. Specify which error reaches the caller of each stage.
3. Add `exceptionally` as a fallback for *recoverable* errors. Demonstrate how placing `exceptionally` before vs. after `whenComplete` determines whether the observer sees the source error or the fallback result.
4. If the audit callback throws an exception **after the invoice has been saved**, explain why the invoice cannot be assumed rolled back, and propose an operation ID / idempotency key along with reconciliation state.
5. Try `whenCompleteAsync` with a dedicated executor and verify that callbacks are always observed before shutdown as required. If logging can be rejected after the executor is closed, design an appropriate error-reporting channel.

**Key takeaway:** `whenComplete` is a tool for **observing both success and failure branches** and producing a dependent stage. It does not recover exceptions on its own. An exception thrown by the observer itself can fail the new stage; if the source has already failed, **the source error takes precedence**. Good design keeps a clear boundary between primary work, observation, and the error-handling policies for both.

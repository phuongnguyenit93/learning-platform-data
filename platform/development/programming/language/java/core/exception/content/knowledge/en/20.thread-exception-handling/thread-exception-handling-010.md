# Propagating Failure Information Across Thread Boundaries with Managed Results

## 1. Why Does a Multithreaded Application Need a Managed Result?

When a method directly calls another method on the **same thread**, an exception can propagate up the call stack to the caller's `catch` block. However, when work is delegated to another thread, each thread has its own call stack: an exception thrown in a worker **is not automatically thrown into the `try-catch` surrounding the submission operation** on the coordinator thread.

Therefore, if the caller needs to know whether the work ultimately succeeded or failed, the system must have a **channel to transfer information between threads**. In Java Core, two commonly used tools are:

- **`Future<T>`**: a handle representing the result of work that may not have completed yet. `Future.get()` waits for and retrieves the value or reports a failure.
- **`CompletableFuture<T>`**: a future that can be completed programmatically and chained into multiple asynchronous stages; it provides ways to handle, transform, and aggregate both results and failures.

A managed result typically needs to represent three distinct layers of information:

1. **Lifecycle state**: pending, running, completed, completed exceptionally, or cancelled.
2. **Business outcome**: found/not found; accepted/rejected; states that the application *expects*.
3. **Execution failure**: `IOException`, unexpected programming exceptions, timeouts, connection loss, or resource errors that prevent the computation from completing as planned.

Do not equate “`Future.isDone() == true`” with “succeeded”; do not treat every exception as a “not found” business value; and do not assume “the caller caught an error from Future” means all side effects of the worker were automatically rolled back.

The goal of this lesson is to design a clear path: **submit work → receive handle → complete with success or failure → observe result at the thread boundary → make a decision**.

## 2. Thread Boundaries Change the Path of Exceptions

Diagram:

~~~text
Coordinator thread A                     Worker thread B
--------------------------               --------------------------
try {                                    run task
    future = executor.submit(task);  ->       process data
    // submit returns handle                    throw IOException
} catch (...) {                               |
    // error from submit operation            v
}                                          Future records failure
           |
           v
future.get()  <-----------------------   task completes
    |
    +-- returns T
    +-- ExecutionException(cause)
    +-- InterruptedException
    +-- CancellationException
~~~

`submit` accepts the work and may return before the worker starts. A `catch` around `submit` can catch errors occurring **immediately at the submission call**, such as `RejectedExecutionException` if the executor rejects it; it does not automatically receive exceptions occurring **later inside the task**.

When using `ExecutorService.submit(Callable<T>)`, an exception escaping `call()` is normally recorded in the `Future` object. The caller retrieves it when calling `get()`: Java wraps the task's cause in an `ExecutionException`. This is how errors are transferred **across a thread boundary via a managed object**, rather than trying to throw backward across an unrelated call stack.

### 2.1. `Thread.join()` Does Not Replace `Future.get()`

`Thread.join()` only waits for a thread to finish. It has no return value from `Runnable.run()` and does not rethrow uncaught exceptions from the worker. When you need to retrieve a typed result or error, `Future` is usually more suitable than a manually created `Thread`.

A child thread can have an `UncaughtExceptionHandler` configured to record uncaught errors, but the handler serves that thread's own error-handling mechanism. The handler does not send a success value back to the caller, does not provide cancellation/timeout states like `Future`, and must not be treated as a guarantee that “the task succeeded” or “the task rolled back”.

## 3. Distinguishing Business Outcomes, Exceptions, and Coordination States

These three categories lead to different actions:

| Scenario | Nature | Typically appropriate representation | Caller action |
| --- | --- | --- | --- |
| Data exists | Business success | `Found(value)` | Use the value |
| Valid ID but no data | Expected normal outcome | `Absent(id)` or `Optional<T>` inside `Future` | Display not found |
| Rejected by business rule | Expected outcome with typed reason | `Rejected(code, details)` | Request fixing data/workflow |
| I/O error that API expects to report structurally | Categorized execution failure | `Failed(code, cause)` in a result type | Retry/record/report error by code |
| Worker throws unhandled exception | Abnormal task failure | `ExecutionException` or exceptional completion | Inspect `cause`, do not treat as absent |
| Caller times out waiting | Coordination state: no result within deadline | `TimeoutException` from `get(timeout, ...)` | Decide whether to keep waiting/cancel/check status |
| Task is cancelled | Lifecycle state | `CancellationException`, `isCancelled()` | Accept cancellation per policy |
| Waiting thread is interrupted | Coordination signal targeting the waiting thread | `InterruptedException` | Propagate or restore interrupt flag |

Therefore, a signature like `Future<Optional<Product>>` can make sense when a search may return empty while still letting real exceptions propagate through `get()`. If there are multiple business states, `Future<SearchResult>` with a sealed result type is often clearer to express. If you want to **convert I/O errors into a typed value**, a `Failed` branch can store a stable error code and cause; however, the code must convert **intentionally**, rather than using `catch (Throwable)` to swallow all JVM errors.

Key rule: **`Future<T>` manages completion; `T` expresses the success data or the business outcomes of the operation.** Classifying at the right layer helps the caller know what to do.

## 4. `Callable<T>` and `Future<T>`: The Foundation of Managed Results

`Runnable.run()` has no return value and declares no checked exceptions. `Callable<T>.call()` returns `T` and can declare `throws Exception`. Thus, when work needs to return a result or report an error, `Callable` combined with `submit` is a natural choice.

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<Integer> future = executor.submit(() -> 20 + 22);
    System.out.println(future.get());
} finally {
    executor.shutdown();
}
~~~

This is an **illustrative fragment**, assuming `ExecutorService`, `Executors`, `Future` are imported and the enclosing method declares or handles `InterruptedException`, `ExecutionException`. When run in an appropriate environment, the value from `get()` is `42`. `submit` only returns the handle; `get` is what waits and retrieves the result. Here, `finally` is responsible for calling `shutdown()` so no new tasks are accepted; if the program requires waiting for all tasks to finish, a separate waiting and cleanup strategy is needed.

### 4.1. Important States of a Future

| API | Primary meaning | What not to infer |
| --- | --- | --- |
| `get()` | Waits until a result is available, the task fails, or it is cancelled; may be interrupted | Not a guarantee that the task will never hang |
| `get(timeout, unit)` | Waits for a bounded time and may throw `TimeoutException` | Timing out does not mean the task has stopped |
| `isDone()` | Task completed according to Future state, including failure/cancellation | `true` does not mean success |
| `isCancelled()` | Future was cancelled | Does not guarantee all side effects were rolled back |
| `cancel(false)` | Attempts to cancel; does not request interrupting if already running | Does not guarantee stopping a running task |
| `cancel(true)` | Attempts to cancel, may request interrupting a running worker | Does not force an uncooperative task to stop immediately |

`ExecutionException` is a **wrapper**, not the root cause: `getCause()` usually returns the exception thrown by the worker. `InterruptedException`, on the other hand, belongs to the **waiting thread**. When receiving it, choose a clear policy: propagate it or call `Thread.currentThread().interrupt()` again if you cannot propagate a checked exception up the stack. Do not handle it the same way as a worker's `ExecutionException`.

`get(timeout, unit)` allows the caller to return quickly, but the job may still continue writing data. If a timeout leads to retrying an operation with side effects, the system must consider idempotency or status querying. Never equate a timeout with “the task definitely failed and did nothing”.

### 4.2. Error Information Needs to Accompany the Cause

Catching an exception to convert it into a typed state:

~~~java
Callable<SearchResult> task = () -> {
    try {
        return readFromRepository();
    } catch (IOException e) {
        return new Failed("P01", FailureCode.STORAGE, e);
    }
};
~~~

This is **non-standalone illustrative code**, because `SearchResult`, `Failed`, `FailureCode`, and `readFromRepository` are not defined in the fragment. The intent is to classify `IOException` into the stable code `STORAGE` and retain `cause` for diagnostics. Avoid catching every `Throwable` and returning `Failed("UNKNOWN")`, because doing so can hide serious errors, corrupt state, or mislead the caller into treating a programming bug as an anticipated business failure.

If the API itself decides that data-reading errors should propagate via `ExecutionException`, there is no need to catch `IOException` inside the `Callable`: simply let `call() throws Exception` surface the error. Both approaches are viable; what matters is that the contract is **consistent and clear to the caller**.

## 5. Complete Java 17 Example: Managing Results from Multiple Workers

The following program uses a two-thread `ExecutorService`. Four tasks are submitted concurrently:

- `A` returns data successfully.
- `N` is a valid lookup that does not exist.
- `IO` triggers an `IOException` and is converted by the task adapter into `Failed(STORAGE)`.
- `BUG` simulates a broken invariant and is kept on the exceptional completion channel of `Future`, rather than being disguised as a “not found” code.

Then a `CompletableFuture` demonstrates how to **convert an exceptional completion into a typed `Failed` value** at the `handle` boundary.

Save the complete code below as **`ManagedThreadResultDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ManagedThreadResultDemo {
    sealed interface SearchResult permits Found, Absent, Failed {}

    record Found(String id, String value) implements SearchResult {}
    record Absent(String id) implements SearchResult {}
    record Failed(String id, FailureCode code, Throwable cause)
            implements SearchResult {}

    enum FailureCode { STORAGE, UNEXPECTED }

    static SearchResult lookup(String id) throws IOException {
        return switch (id) {
            case "A" -> new Found(id, "alpha");
            case "N" -> new Absent(id);
            case "IO" -> throw new IOException("storage unavailable");
            case "BUG" -> throw new IllegalStateException("broken invariant");
            default -> new Absent(id);
        };
    }

    static Callable<SearchResult> managed(String id) {
        return () -> {
            try {
                return lookup(id);
            } catch (IOException e) {
                return new Failed(id, FailureCode.STORAGE, e);
            }
        };
    }

    static Throwable unwrapCompletion(Throwable error) {
        while (error instanceof CompletionException && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    static String display(SearchResult result) {
        if (result instanceof Found found) {
            return "FOUND " + found.id() + "=" + found.value();
        }
        if (result instanceof Absent absent) {
            return "ABSENT " + absent.id();
        }
        if (result instanceof Failed failed) {
            return "FAILED " + failed.id() + "=" + failed.code();
        }
        throw new IllegalStateException("Unknown result");
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<SearchResult>> futures = new ArrayList<>();
            for (String id : List.of("A", "N", "IO", "BUG")) {
                futures.add(pool.submit(managed(id)));
            }
            for (int i = 0; i < futures.size(); i++) {
                try {
                    System.out.println(display(futures.get(i).get()));
                } catch (ExecutionException e) {
                    System.out.println("UNEXPECTED " + e.getCause()
                            .getClass().getSimpleName());
                }
            }

            CompletableFuture<SearchResult> async =
                    CompletableFuture.<SearchResult>supplyAsync(() -> {
                        throw new IllegalArgumentException("async defect");
                    }, pool).handle((value, error) -> {
                        if (error == null) {
                            return value;
                        }
                        return new Failed("ASYNC", FailureCode.UNEXPECTED,
                                unwrapCompletion(error));
                    });
            System.out.println(display(async.join()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Using JDK 17 or higher, from the directory containing the file:

~~~bash
javac --release 17 ManagedThreadResultDemo.java
java ManagedThreadResultDemo
~~~

**Exact stdout:**

~~~text
FOUND A=alpha
ABSENT N
FAILED IO=STORAGE
UNEXPECTED IllegalStateException
FAILED ASYNC=UNEXPECTED
~~~

### 5.1. Explaining Why the Output Has a Fixed Order

The tasks in the first group may **execute and complete in any order** on the two workers. However, the loop iterates over `List<Future<SearchResult>>` in submission order and calls `get()` on each future, so the **order of printed lines** is A, N, IO, BUG even though actual execution times differ. If replaced with a callback printing directly on each worker, the print order could vary. After the loop, the program creates the `CompletableFuture` stage and waits on `join()` before printing the final line.

- `Found A=alpha`: the task returns `Found` normally; `Future.get()` returns the `SearchResult`.
- `Absent N`: the lookup returns `Absent`, which is an **execution-level success** with no record found.
- `Failed IO=STORAGE`: the task catches `IOException` specifically, preserves the original exception in `cause`, and returns a categorized result. `get()` does not throw `ExecutionException` because the `Callable` completed by **returning a value**.
- `UNEXPECTED IllegalStateException`: `managed` does not catch `IllegalStateException` from `lookup("BUG")`. The `Future` completes exceptionally; `get()` throws `ExecutionException` and the caller reads `getCause()`.
- `Failed ASYNC=UNEXPECTED`: `CompletableFuture.supplyAsync` completes exceptionally; `handle` creates a `Failed` containing the error code and the cause unwrapped from `CompletionException`. The **new** stage therefore completes normally with the `Failed` object.

The example retains `Throwable cause` **in the internal result type** for diagnostics; when translating to a REST response, event log, or user notification, you must provide a **safe error code**, avoiding serializing stack traces, file paths, or sensitive information externally. The codes `STORAGE` and `UNEXPECTED` illustrate policy; real applications can use a more detailed enum, such as `TEMPORARY_UNAVAILABLE`, `PERMISSION_DENIED`, or `NOT_RECOVERABLE` if callers genuinely need to distinguish them.

### 5.2. Why Not Catch Every Exception to Always Return `Failed`?

You can design a `Result<T,E>` that folds all application exceptions into an error branch, but you must consider the cause and boundary. In the example, expected I/O errors are converted to `Failed(STORAGE)`, while `IllegalStateException` simulating a broken invariant is kept as an exceptional completion so it is not masked.

At a **work-coordination** or **external-system** boundary, it may be necessary to convert certain unhandled exceptions into a typed result to respond to the caller. In that case, classify, log, and retain the appropriate cause—never silently turn it into “not found” or “success”. Java does not force every error type through the same channel.

### 5.3. Why Do Results Use `sealed interface` and `record`?

`sealed interface SearchResult` lists the permitted implementations: `Found`, `Absent`, `Failed`. Each `record` carries its own fields: the value when found, the missing key, or the error code and cause when failed. These are stable features in Java 17.

`display` uses `instanceof` pattern matching to read each type's data. Pattern matching in `switch` over sealed types is a preview feature in Java 17, so the example does not require enabling preview features to compile. The signature `Future<SearchResult>` lets callers handle structured results, but it **does not exempt** the `Future` layer from `ExecutionException` or cancellation.

## 6. Choosing Where to Convert Exceptions into Data

There are two common contracts:

**Contract A — execution errors remain exceptional completions:**

~~~java
Future<String> future = executor.submit(() -> remoteRead());
String value = future.get(); // May throw ExecutionException.
~~~

The illustrative snippet assumes `executor`, `remoteRead()`, and checked exceptions are already declared/caught. This approach fits when execution exceptions are part of the standard error channel and the calling layer has a unified handling policy.

**Contract B — certain outcomes are converted into a typed `Result`:**

~~~java
Future<LoadResult> future = executor.submit(() -> {
    try {
        return new Loaded(remoteRead());
    } catch (IOException e) {
        return new LoadFailed("STORAGE", e);
    }
});
~~~

The fragment assumes `LoadResult`, `Loaded`, `LoadFailed`, `remoteRead`, and `executor` exist. Here `get()` can return `LoadFailed` normally; uncaught exceptions can still lead to `ExecutionException`.

You must distinguish **normal completion of a Future** from **business success**: a `Future<Result>` returning `Failure` is not an exception on the `Future` channel, yet the business operation still failed and must be handled by the caller. If monitoring only counts exceptionally completed tasks, it can miss many results carrying `Failure`; metrics must be designed across both state layers.

Do not inadvertently use both representations for **the same error** in peer APIs without a rule, as callers will not know when to inspect the `Failed` branch and when to catch `ExecutionException`.

## 7. `CompletableFuture`: Managing an Entire Asynchronous Chain

`CompletableFuture<T>` extends the handle concept: instead of only waiting for the final result, the caller can define subsequent stages.

| API | Meaning when upstream succeeds | When upstream fails |
| --- | --- | --- |
| `thenApply(fn)` | Applies synchronous transformation per completion stage semantics | Does not invoke `fn`; resulting stage fails |
| `thenCompose(fn)` | Chains another dependent stage, avoiding nested `CompletableFuture<CompletableFuture<T>>` | Does not invoke `fn`; error is propagated |
| `thenCombine(other, fn)` | Combines values from two normally completed stages | If either stage fails, the result can complete exceptionally |
| `exceptionally(fn)` | Preserves original value | Allows producing a replacement value from the error |
| `handle((value,error) -> result)` | Sees value and can transform it | Sees error and can transform it into a value |
| `whenComplete((value,error) -> action)` | Performs an observation action | Sees error; by itself is not a recovery guarantee |
| `get()` | Returns value on completion | Checked `ExecutionException` (or cancellation), may be interrupted |
| `join()` | Returns value on completion | Unchecked `CompletionException` (or cancellation) |

A stage may be completed by a worker, by the thread completing the previous stage, or by an explicitly passed executor, depending on the API. **Never assume callbacks always run on the thread that created the `CompletableFuture`.** For `...Async` variants without an explicit executor, Java uses the default executor mechanism specified by the API; in systems requiring resource management, pass an appropriate executor and clearly define who owns its shutdown.

### 7.1. `handle` Is an Intentional Conversion, Not Automatic Healing

Example:

~~~java
CompletableFuture<String> raw = CompletableFuture.supplyAsync(
        () -> {
            throw new IllegalStateException("remote request failed");
        });

CompletableFuture<String> recovered =
        raw.exceptionally(error -> "fallback");
~~~

The fragment can be placed inside a method with `CompletableFuture` imported. `raw` completes exceptionally; `recovered` is a new stage that can complete normally with the string `fallback`. Only use a fallback if business rules genuinely allow it. For critical data, turning an error into a fake “success” value can hide the fact that the task was never performed.

Another approach is converting into a typed result:

~~~java
CompletableFuture<Outcome> observed =
        raw.handle((value, error) ->
                error == null
                        ? new Success(value)
                        : new FailedOutcome(error));
~~~

This is an illustrative fragment assuming `Outcome`, `Success`, and `FailedOutcome` are defined; these branches need a compatible common type. `handle` observes both states and produces an explicit result, rather than having to parse message strings to tell whether an error occurred.

### 7.2. `whenComplete` Is for Observation and Preserves the Error

`whenComplete` is typically suitable for recording metrics, logging, or controlled cleanup:

~~~java
CompletableFuture<String> withObservation =
        raw.whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });
~~~

The fragment assumes `recordFailure`. The stage `withObservation` still carries the result/error according to `whenComplete` rules; this callback **does not turn an error into a success by default**. Do not use `whenComplete` and then discard the resulting future if the caller still needs assurance that the failure was handled.

In particular, an observation callback can throw its own exception. If the upstream has already failed, which exception gets propagated follows the `CompletionStage` contract; therefore, logging/metric callbacks should be concise, avoid dangerous side effects, and not replace the main result-handling flow.

### 7.3. Combining Multiple Stages and Aggregating Results

`CompletableFuture.allOf(f1, f2, ...)` returns a `CompletableFuture<Void>` that completes after all component futures complete. If any stage fails, `allOf` completes exceptionally; it **does not return a list of values**, nor does it automatically produce a full summary report of every future. If you need to distinguish failures per task, observe each future individually or convert each stage into an `Outcome` value before aggregating.

`CompletableFuture.anyOf(...)` completes when any component stage completes, including exceptional completion; it does not mean picking “the first successful stage”. Use it only when that exact contract is what you need.

Example of classifying each stage before `allOf`:

~~~java
CompletableFuture<Outcome> a = serviceA()
        .handle((value, error) -> classify("A", value, error));
CompletableFuture<Outcome> b = serviceB()
        .handle((value, error) -> classify("B", value, error));

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
all.join();
Outcome first = a.join();
Outcome second = b.join();
~~~

This is **Java-like pseudocode** where `serviceA`, `serviceB`, `classify`, and `Outcome` are undeclared, and generic types would need to be aligned in real code. The idea is that each stage has a typed status channel, followed by aggregation after the synchronization point. Do not simply call `all.join()` and infer that everything succeeded at the business level.

## 8. Exceptional Completion and Unwrapping Causes

In `CompletableFuture`, ways to trigger/observe errors include:

- A worker or callback throws an exception: the stage can complete exceptionally.
- Code explicitly calls `completeExceptionally(error)`: attempts to complete an uncompleted `CompletableFuture` with the given error.
- `join()`: normally reports exceptional completion via unchecked `CompletionException`; cancellation may be via `CancellationException`.
- `get()`: reports failure via checked `ExecutionException`; the caller also needs to handle `InterruptedException`.
- `isCompletedExceptionally()`: checks whether the future completed exceptionally, without returning the specific cause.

A future cannot complete both normally and exceptionally at the same time; only one terminal state wins the completion race. `complete(value)` and `completeExceptionally(error)` return a boolean indicating whether the call transitioned the future to completion. Do not use these two calls as a way to “overwrite” an already completed result.

### 8.1. Do Not Rely on Exactly One Layer of `CompletionException`

In callbacks, the error argument may already be wrapped in `CompletionException` or another type depending on how the stage ended. Never call `error.getCause().getMessage()` unconditionally, because `getCause()` can be `null`. When normalizing exceptions at an internal layer, you can unwrap known wrappers while keeping a reference to the original error.

~~~java
static Throwable unwrapCompletion(Throwable error) {
    while (error instanceof CompletionException && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

This illustrative method is the exact function used in `ManagedThreadResultDemo`. It only unwraps `CompletionException` and avoids losing the cause when it is `null`. Do not blindly unwrap every wrapper by a blanket rule: a wrapping exception can carry important contextual information. When logging, you often need both the wrapper's context and the original cause chain.

### 8.2. Root Exceptions and Structured Business Errors Are Two Different Layers

A typed result should contain a **stable error code** for caller decisions. `cause` should serve internal analysis and logging, not act as an API for clients to parse `getMessage()` strings. For example, a code `STORAGE_UNAVAILABLE` allows choosing a retry policy; a detailed message like “connection refused” is not a long-term contract.

When multiple tasks fail, attach a **taskId/correlationId** before aggregating so you know which task an error belongs to; keeping only a single final `Throwable` may lose earlier errors. For external APIs, avoid exposing stack traces, file paths, user data, or tokens in the result.

## 9. Timeouts, Interruption, and Cancellation Must Be Reported Accurately

These states are often confused with “the worker threw an exception”. In reality:

| Signal | Raised at | Correct conclusion |
| --- | --- | --- |
| `ExecutionException` | Caller's `Future.get()` | Task completed with an exception; inspect `getCause()` |
| `CompletionException` | `CompletableFuture.join()` or stage | Stage completed exceptionally; inspect cause |
| `TimeoutException` | `Future.get(timeout, unit)` or other bounded wait | Caller did not receive a result within the deadline |
| `InterruptedException` | Thread waiting on `get`, `Thread.join`, or compatible blocking API | Waiting thread was interrupted; do not conclude the worker failed |
| `CancellationException` | Retrieving result of a cancelled future | Work is in cancelled state per `Future` contract |
| `RejectedExecutionException` | Submitting work to an executor that refuses it | Work was not accepted at that submission call |

Pattern for handling a `Future` with a timeout:

~~~java
try {
    Outcome result = future.get(2, TimeUnit.SECONDS);
    handleResult(result);
} catch (TimeoutException e) {
    reportStillPending();
    future.cancel(true); // Only if policy permits requesting cancellation.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException e) {
    reportFailure(e.getCause());
} catch (CancellationException e) {
    reportCancelled();
}
~~~

This is an **illustrative fragment**, assuming `future`, `Outcome`, handler methods, corresponding imports, and an enclosing method returning `void`. `cancel(true)` only requests cancellation/may interrupt the worker depending on task state; an uncooperative task may continue external side effects. If the caller does not own the task, **do not unilaterally cancel** shared work just because one caller timed out.

A `CompletableFuture.orTimeout(...)` can complete the `CompletableFuture` itself exceptionally with `TimeoutException` after the deadline, but **does not prove the underlying work has stopped**. `completeOnTimeout(value, ...)` supplies a fallback value if not completed in time, and likewise does not cancel ongoing external operations. Because these methods can complete the target future, think carefully before applying them to a future shared across multiple callers.

### 9.1. Handling `InterruptedException` Properly

Many blocking APIs clear the interrupt flag when throwing `InterruptedException`. If you catch it and cannot rethrow it, typically call `Thread.currentThread().interrupt()` and then exit or yield control upward. **Do not** do this:

~~~java
try {
    future.get();
} catch (InterruptedException ignored) {
    // Swallows interrupt request, continues indefinitely.
}
~~~

This fragment is intentionally an anti-pattern and does not handle other checked exceptions from `get()`. Swallowing interrupts can prevent shutdown/cancellation flows from working as expected.

If a task must stop when interrupted, the task code must also **cooperate**: check `Thread.currentThread().isInterrupted()` in long loops, handle `InterruptedException` from wait/sleep appropriately, and do not silently keep working after a cancellation request.

## 10. Executor and Result Ownership: Who Ensures Tasks Are Observed?

Asynchronous delegation creates management responsibilities. If a system uses `ExecutorService`, clearly define **who creates the executor, who shuts it down, who waits, and who is responsible for handling failures**.

A workflow might look like this:

~~~text
Request/Coordinator
    |
    +-- assign taskId and correlationId
    |
    +-- submit -> receive Future<T>
    |
    +-- store/hold handle until handled
    |
    +-- get()/callback/aggregate results
    |        |
    |        +-- Success
    |        +-- Business outcome
    |        +-- Execution failure
    |        +-- Cancel/timeout
    |
    +-- record status and respond appropriately
    |
    +-- release handle and resources per policy
~~~

Do not **fire-and-forget** an important task and treat it as successful without a recording mechanism. For example:

~~~java
executor.submit(() -> sendNotification(orderId));
return "sent";
~~~

The fragment assumes `executor`, `sendNotification`, and `orderId` exist. It only proves `submit` was called without throwing immediately; it does not prove the notification was sent. A discarded `Future` may hold an unread exception. If you want an immediate response, the status should be “accepted” or “processing”, accompanied by a job ID and a way to query the result later.

### 10.1. `shutdown()` Is Not the Same as “Everything Finished”

`ExecutorService.shutdown()` initiates an orderly shutdown: no new tasks are accepted, while submitted tasks may still be running. `shutdownNow()` attempts to stop active tasks and returns a list of waiting tasks, but does not guarantee they have all stopped. `awaitTermination(timeout, unit)` waits for the executor to terminate within a bound; it does not assert that every task succeeded.

Java 17 `ExecutorService` does not yet have `close()` as in newer Java versions; using `shutdown` and waiting/cancellation methods tied to the application lifecycle is the appropriate pattern. In the standalone example, all futures are retrieved via `get/join` before `shutdown`, so no tasks remain running at the end of the success path. In server applications, executors are usually owned at a long-lived layer and shut down when the application stops, rather than created/closed per request.

### 10.2. `Future` Is Not Durable Storage

`Future` and `CompletableFuture` are objects in JVM process memory. If the process dies, the `Future` object disappears; it is **not a durable queue** and provides no crash recovery. Work with business consequences that must survive restarts may require job state persisted in a DB, durable queues, an outbox, idempotency keys, and retry/reconciliation workflows depending on requirements.

“Having a `Future` handle” only solves observation **while the process and object are alive**. It does not turn multiple side effects into a single transaction. A task may have written a file or sent an HTTP request before failing; even if the caller receives `ExecutionException` or `Failed`, those prior effects may still exist.

## 11. When to Convert to a Result, When to Keep an Exception?

An easy-to-use API contract typically categorizes outcomes as follows:

- **Expected business states:** return a typed result such as `Found`, `Absent`, `Rejected` with enough information for the caller to act. These branches can be part of `T` in `Future<T>`.
- **Technical errors intentionally classified by the API:** convert to `Failed(ErrorCode, cause)` if the calling layer needs to decide on retry, error reporting, metrics, or recovery based on the code.
- **Abnormal errors/broken invariants:** can let the task complete exceptionally and notify the coordinator; do not automatically turn every error type into a normal data value.
- **Timeout/cancellation/interruption:** belong to the **coordination contract** and must be handled separately from business branches.
- **System stop/crash:** the `Future` result may never be received; durable state management is required if the feature demands it.

Depending on the API, a generic `Result<T, E>` type can also be useful. `E` should be a structured enum/record/sealed hierarchy, avoiding free-form message strings that force callers to check `contains("timeout")` or `contains("database")` to decide. There is no need to force `Future<Result<Optional<T>>>` everywhere if the business domain only has two simple states and callers already have the exceptional completion channel.

### 11.1. Decisions at Layer Boundaries

| Layer | Responsibility | Example |
| --- | --- | --- |
| Task/worker | Do the work, handle locally recoverable errors | Catch a specific I/O error with a bounded retry policy |
| Submission adapter | Create task, attach IDs, choose executor, manage handle | `submit(Callable<Result>)` |
| Coordinator | Wait/aggregate/read results, distinguish states, decide cancellation | `get()` / `handle` callback |
| API boundary | Map states to UI/HTTP/messages, protect error details | Return typed error code without exposing stack traces |
| Durable infrastructure when needed | Persist job state, retry, and deduplicate across process restarts | Database/outbox/job store |

Not every application needs every layer. What is essential is a **clear owner** of the final outcome, so failures do not turn into an ignored stack trace.

## 12. Observing Multiple Results: Complete Errors, Correct Order, and No Task Leaks

When submitting multiple tasks, a failure in one task **does not automatically cancel the remaining tasks**. If tasks are independent, you can wait for all and aggregate every `Outcome`. If one failed task makes the overall result meaningless, the coordinator can cancel the rest per policy; be aware of how cooperative cancellation is and what side effects have already occurred.

Key points:
1. **Completion order differs from submission order.** Iterating over a `Future` list and calling `get()` in submission order gives predictable reading order, but may block on an earlier task even if later tasks finish sooner.
2. **One task failing does not prove another task has not run.** If another task already sent an email, collecting the error does not unsend the email.
3. **`Future.isDone()` is not enough to classify.** To know the outcome, call `get`/read the result. If a future was cancelled, handle it separately.
4. **A failed `allOf` stage does not provide all errors as a list.** To report per-task results, turn each stage into an `Outcome` or query each future.
5. **Deadlines must make sense at the overall job level.** If each `get` uses a 5-second timeout sequentially across 20 tasks, total time can exceed the desired deadline; design an overall deadline instead of per-call timeouts when the requirement is “finish within 5 seconds”.
6. **Observability:** record separate metrics for succeeded, absent, business-failed, exception, timed-out, and cancelled tasks.

If the application must collect **all** failures, do not skip the remaining `Future`s just because `get` on the first `Future` throws `ExecutionException`; build an aggregated report per policy while bounding time and resources appropriately.

## 13. Common Design Mistakes

### 13.1. `try-catch` Only Around `submit`

~~~java
try {
    executor.submit(() -> failingOperation());
} catch (Exception e) {
    logError(e);
}
~~~

This fragment assumes variables/functions already exist. This `catch` can receive errors occurring directly when submitting the task, **not exceptions raised later inside the worker**. To observe the task, keep the `Future` and read `get()` or register an appropriate stage callback.

### 13.2. Discarding the Future and Returning a Success Message

~~~java
executor.submit(() -> writeImportantFile());
return true;
~~~

The fragment assumes a method returning boolean and related functions. This `true` is an unsupported conclusion: the work may not even have run yet. Return a job handle/accepted status; or wait/receive the result before confirming actual success.

### 13.3. Returning `Optional.empty()` for Every Exception

~~~java
try {
    return repository.findById(id);
} catch (RuntimeException ignored) {
    return Optional.empty();
}
~~~

The fragment assumes the repository returns `Optional`. Having no record is completely different from **not knowing the result because the query failed**. Propagate exceptional completion or return a typed error branch preserving the cause.

### 13.4. Turning Every `Failed` into Success After `handle`

If `handle` always returns `"ok"` after an exception, the resulting stage can complete normally and `Future`-level metrics will only see success. The recovery policy must be explicitly defined; a `Failed(code)` value still needs to be counted as a business/technical failure.

### 13.5. Catching `InterruptedException` and Staying Silent

Swallowing interrupts makes cancellation/shutdown unreliable. Propagate or restore the interrupt flag and end processing according to contract. A caller's `InterruptedException` does not replace checking whether the task has actually stopped.

### 13.6. Using `getCause()` Without Guarding Assumptions

With errors from different systems, wrappers/causes may not have the expected structure. Do not call `cause.getMessage()` when `cause` can be `null`; record the wrapper type and fall back appropriately. Do not fabricate an error type or treat message text as a stable error code.

### 13.7. Having No Executor Shutdown Policy

A pool created and forgotten can keep threads alive and consume resources. A shared executor shut down by one request's code can break other requests. Executor ownership boundaries must be defined at design time, not just in tests.

## 14. Testing the Result Path Across Thread Boundaries

A reliable test suite needs to test **both returned results and coordination states**, rather than only catching a single exception:

| Scenario | What to verify |
| --- | --- |
| `Callable` returns `Found` | `get()` returns the exact value |
| `Callable` returns `Absent` | Future completes normally; caller classifies as absent |
| `Callable` catches `IOException` and returns `Failed` | `get()` returns `Failed(STORAGE)`, cause is stored internally |
| `Callable` lets `IllegalStateException` escape | `get()` throws `ExecutionException`, cause has expected type |
| `CompletableFuture` stage fails | `join()` throws `CompletionException` when unrecovered |
| `handle` stage converts error to `Failed` | `join()` returns typed result, error code, and appropriate cause |
| Future not done by deadline | `get(timeout, ...)` throws `TimeoutException`; task is not assumed stopped |
| Waiting caller is interrupted | Flag restoration/interrupt propagation policy works properly |
| Future is cancelled | `isCancelled()` is true, `get()` may throw `CancellationException` |
| Multiple Futures with one failing task | Status/errors of other tasks are not lost |
| Executor shuts down while work exists | No new tasks accepted; accepted tasks handled per contract |
| Worker has side effects then fails | Result reports failure properly, without assuming side effects rolled back |

For deterministic concurrency tests, use `CountDownLatch` or futures with timeouts to coordinate milestones. Do not rely on `Thread.sleep(100)` and assume the task has definitely finished. For error testing, use a fake dependency that throws exceptions before/after state writes; this lets you assert exactly what the system did.

If a test uses its own executor, release the executor after the test; if a task is cancelled and does not cooperate with interrupts, design the test so it can finish without leaking threads. Tests for retries or side effects should cover the case where **the server processed the request but the response was lost**, not only immediate server rejections.

## 15. Checklist When Developing Managed Asynchronous APIs

- [ ] Work is submitted through a clear API; callers know when it is only **accepted** vs **completed**.
- [ ] There is a handle/channel to report results; do not assume `try-catch` around `submit` catches worker errors.
- [ ] Expected business outcomes are clearly typed and not mixed with exceptional completion.
- [ ] I/O/technical errors are classified per contract; do not turn errors into `Optional.empty()`.
- [ ] `ExecutionException` and `CompletionException` are handled via `cause`; do not guess solely from `message`.
- [ ] `TimeoutException`, `InterruptedException`, and `CancellationException` have separate policies.
- [ ] `handle`/`exceptionally` callbacks only convert errors to values when there is an explicit recovery decision.
- [ ] Every important `Future` is observed or has an owner handling it; errors stored in a `Future` are not ignored.
- [ ] Executors have a lifecycle and a designated shutdown owner.
- [ ] Failure metrics include both `Result.Failed` and exceptional completions.
- [ ] Side effects occurring before a failure are managed with transactions/idempotency or recovery workflows when needed.
- [ ] Test success, business failures, unexpected errors, timeouts, cancellation, and interruption in a coordinated environment.

### Practice Exercise

Design an API `loadProfiles(List<String> ids)` using `ExecutorService` to process multiple user IDs. For each ID, the operation can return: profile data, not found, or a retryable I/O error. Another ID intentionally triggers `IllegalStateException`.

1. Define a result type for loaded data, absence, and failure with an error code; decide which exceptions should continue propagating via `Future.get()`.
2. Submit four tasks in parallel and aggregate all results in input order. Do not skip unobserved `Future`s just because one task fails.
3. Apply a shared overall deadline for the entire batch; only cancel when policy and ownership permit.
4. Rewrite using `CompletableFuture`; convert each stage to a typed result before aggregating with `allOf`.
5. Write a test simulating a task that writes partial data and then throws an exception. Explain why receiving `Failed` or `ExecutionException` still **does not automatically roll back** effects that occurred before the error.

**Technical takeaway:** thread boundaries separate call stacks; to transfer failures, callers need a managed result protocol. `Future`/`CompletableFuture` carry completion status and errors across threads, while the application's result type clarifies business outcomes. Both layers must be handled explicitly and consistently.

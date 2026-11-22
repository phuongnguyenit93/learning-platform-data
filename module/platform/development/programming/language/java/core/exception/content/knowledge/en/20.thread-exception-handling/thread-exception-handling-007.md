# Separating Task Failures from Waiting Thread Failures

In Java multithreaded programming, the **thread executing a task** (*worker*) and the **thread waiting for the result** (*waiting thread/caller*) can encounter two completely different kinds of failures. A computation may fail inside the worker while the caller is still waiting normally. Conversely, the caller may be interrupted or time out even though the task is still running properly.

If these scenarios are mixed together, an application can easily misreport a "task failure" when only a single waiting request has expired; accidentally cancel necessary work; or retry the same transaction twice. To design exception handling properly, you must answer these separately:

1. **How did the task complete?** Did it succeed, fail, or get cancelled?
2. **How did this wait end?** Did it receive a result, get interrupted, time out, or observe a failed/cancelled task?
3. **Does the caller still have the authority or need to wait?** A failure of the waiting operation does not automatically dictate the lifecycle of the task.

This lesson focuses on the mechanisms of `Future`, `ExecutorService`, and `CompletableFuture` in Java 17+, along with how to classify, propagate information, and handle failure paths in real-world systems.

## 1. Two Activities, Two Exception Boundaries

Consider the model:

```text
Caller thread                        Worker thread
    |                                      |
    |--- submit(callable) --------------->| receives task
    |<-- Future --------------------------|
    |                                      | computes / calls I/O
    |--- future.get()                      |
    |        |                             |
    |        |                             +-- success: result
    |        |                             |
    |        |                             +-- failure: Throwable
    |        |
    +-- wait ends: value / ExecutionException
                    / InterruptedException
                    / TimeoutException / CancellationException
```

An exception thrown inside `Callable.call()` **is not automatically thrown directly on the caller's stack**. With `ExecutorService.submit`, the executor records the task's outcome in a `Future`; the caller invokes `get()` to access the result or find out why there is no result.

Similarly, an exception occurring in `future.get()` does not necessarily originate from the logic inside the task. The caller may be interrupted while waiting, or the wait deadline chosen by the caller may expire before the task finishes.

For example:

- The worker reads data and throws `IllegalArgumentException("bad input")`. The caller waits normally, but `Future.get()` throws `ExecutionException` whose `getCause()` is `IllegalArgumentException`.
- The worker is waiting on I/O, and while the caller is waiting via `get()`, another thread calls `interrupt()`. The caller itself encounters `InterruptedException`; the worker may still be running.
- The worker needs 5 seconds, while the caller only allows waiting 100 ms via `get(100, MILLISECONDS)`. The caller encounters `TimeoutException`; the task is not cancelled merely because the wait expired.
- Someone called `future.cancel(...)` successfully. When observing the cancelled `Future`, `get()` throws `CancellationException`.

You must understand **where an exception originates and its lifecycle meaning** before deciding to retry, cancel, roll back, or return an error.

## 2. The Four Key Exit Paths of Future.get

`Future<V>.get()` can return a value or throw an exception. The timed overload adds `TimeoutException`.

| Outcome observed while caller waits | Exception type at caller | Primary meaning | Does it prove the task itself failed? |
| --- | --- | --- | --- |
| Task succeeds | None; `get()` returns `V` | Result available | No |
| Task ends due to an exception | `ExecutionException` | An error occurred during task execution; inspect `getCause()` | **Yes**, for a task that completed exceptionally |
| Thread calling `get()` is interrupted while waiting | `InterruptedException` | The **caller's** wait operation was interrupted | **No** |
| Wait deadline of `get(timeout, unit)` expires | `TimeoutException` | The caller has not received the result within the allotted wait time | **No** |
| `Future` has been cancelled | `CancellationException` (unchecked) | The result is no longer provided due to cancellation | Does not equate to a business-logic task failure |

As you can see, `Future.get()` does not simply "throw the worker's exception." It is a **wait-and-observe-state** API, so it has exceptions tied to both **the outcome** and **the waiting behavior itself**.

### ExecutionException: an error belonging to task execution

`ExecutionException` is a wrapper (checked exception) indicating that the computation represented by the `Future` terminated abnormally. Check `getCause()` to find the underlying error:

```java
try {
    String value = future.get();
} catch (ExecutionException wrapper) {
    Throwable taskFailure = wrapper.getCause();
    // Classify according to meaningful task/API errors.
}
```

This is an illustrative snippet, assuming `future` is a `Future<String>` and the rest of the program handles `InterruptedException`. You should not treat `ExecutionException` itself as a business error: many different kinds of failures can be wrapped inside this class.

If `taskFailure` is an application exception with a stable error code, it can be handled purposefully. If it is a bug or a serious `Error`, do not arbitrarily turn it into an "invalid input" error.

### InterruptedException: an error belonging to the caller's wait

An `InterruptedException` from `Future.get()` usually indicates that **the thread calling `get`** was interrupted while waiting. Java allows another thread to request interruption, for instance during system shutdown or workflow cancellation. That **does not mean the worker was interrupted**, nor does it mean the worker failed.

Handling pattern when `InterruptedException` cannot be propagated directly to the caller:

```java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new WaitAbortedException("Stopped waiting for result", interrupted);
}
```

This snippet is only illustrative, with `future`, the return type, and `WaitAbortedException` determined by the actual API. Calling `Thread.currentThread().interrupt()` restores the interrupt flag that the blocking operation typically cleared when throwing `InterruptedException`. If the method can declare `throws InterruptedException` and let the caller decide, you can propagate that checked exception directly.

**Do not unconditionally call `future.cancel(true)` in the catch block** if only the caller was interrupted while the task is shared work, or if the application policy wants the task to continue. Only cancel when the caller truly owns the cancellation authority and the operational contract requires it.

### TimeoutException: wait timed out, not yet a task timeout

`future.get(200, TimeUnit.MILLISECONDS)` limits **how long the caller waits to retrieve the result**. If a timeout occurs:

- The `Future` may still be running, waiting in a queue, or have just completed around the expiration time.
- `get(timeout, unit)` **does not automatically call `cancel`**.
- The caller may wait again later, check `isDone()`, or choose to cancel if policy dictates.
- If you decide to retry with a new job, you must check whether the old job still has side effects or is processing the same data.

`TimeoutException` also does not equate to a timeout at the socket, query, or external service layer. A task may itself throw `SocketTimeoutException`; in that case `Future.get` reports `ExecutionException` with a cause that is the **worker's** exception, not a `TimeoutException` from the wait operation.

### CancellationException: cancelled state

After `Future.cancel(...)` succeeds, `isCancelled()` returns `true` and `get()` throws `CancellationException`. `CancellationException` is an unchecked exception.

`cancel(true)` may request interrupting the running thread, but it does not guarantee that the worker code will stop immediately: it must cooperate with interruption and may already have performed side effects. `cancel(false)` does not interrupt a running task; for an unstarted task it may prevent execution, while for a running task the `Future` may transition to the cancelled state per the implementation contract even though the background work continues.

Therefore, **the cancelled state of a Future** does not prove that the task has stopped all activity or finished rolling back.

## 3. Complete Java 17 Example: Separating Three Failure Sources

The following example has three controlled outcome groups:

1. A task throws `IllegalArgumentException` itself; the caller sees `ExecutionException` and its cause.
2. The task itself throws **`InterruptedException`**; the caller still sees **`ExecutionException`**, because that exception occurred inside `Callable`.
3. A third task is blocked by a `CountDownLatch`. The first wait times out; another wait is interrupted; finally the task is released and returns a successful result.

The example intentionally uses latches instead of `Thread.sleep(...)` so the outcome does not depend on accidental scheduling order between threads.

Create the file `TaskAndWaiterFailuresDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class TaskAndWaiterFailuresDemo {

    private static void printTaskFailure(
            String label, Future<String> future)
            throws InterruptedException {
        try {
            future.get();
            System.out.println(label + ": unexpected success");
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            System.out.println(
                label + ": ExecutionException -> "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage()
            );
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch releaseTask = new CountDownLatch(1);

        try {
            Future<String> failed = executor.submit(
                (Callable<String>) () -> {
                    throw new IllegalArgumentException("bad input");
                }
            );
            printTaskFailure("TASK_ERROR", failed);

            Future<String> taskInterrupted = executor.submit(
                (Callable<String>) () -> {
                    throw new InterruptedException("from task");
                }
            );
            printTaskFailure("TASK_INTERRUPTED", taskInterrupted);

            CountDownLatch taskStarted = new CountDownLatch(1);
            Future<String> pending = executor.submit(
                (Callable<String>) () -> {
                    taskStarted.countDown();
                    releaseTask.await();
                    return "done";
                }
            );

            // Ensure the worker is before the point of returning the result;
            // releaseTask has not been released yet.
            taskStarted.await();

            try {
                pending.get(1, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println(
                    "WAIT_TIMEOUT: cancelled=" + pending.isCancelled()
                );
            } catch (ExecutionException ex) {
                System.out.println("unexpected task failure");
            }

            AtomicReference<String> waitOutcome =
                    new AtomicReference<>("not observed");

            Thread waiter = new Thread(() -> {
                try {
                    pending.get();
                    waitOutcome.set("unexpected success");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    waitOutcome.set(
                        "InterruptedException; restored="
                            + Thread.currentThread().isInterrupted()
                    );
                } catch (ExecutionException ex) {
                    waitOutcome.set("unexpected task failure");
                }
            }, "waiting-thread");

            waiter.start();
            // The worker has not been released yet so waiter
            // cannot receive a successful result before the interrupt.
            waiter.interrupt();
            waiter.join();
            System.out.println("WAIT_INTERRUPTED: " + waitOutcome.get());

            // The caller can receive the result after two failed waits.
            releaseTask.countDown();
            try {
                System.out.println("TASK_RESULT: " + pending.get());
            } catch (ExecutionException ex) {
                System.out.println("unexpected task failure");
            }
        } finally {
            releaseTask.countDown();
            executor.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 TaskAndWaiterFailuresDemo.java
java TaskAndWaiterFailuresDemo
```

Stdout:

```text
TASK_ERROR: ExecutionException -> IllegalArgumentException: bad input
TASK_INTERRUPTED: ExecutionException -> InterruptedException: from task
WAIT_TIMEOUT: cancelled=false
WAIT_INTERRUPTED: InterruptedException; restored=true
TASK_RESULT: done
```

Comparing each scenario:

- `TASK_ERROR`: the exception is thrown inside `Callable` and stored by `Future`. The caller receives `ExecutionException` and classifies `IllegalArgumentException` via `getCause()`.
- `TASK_INTERRUPTED`: **the worker itself throws `InterruptedException`** inside the task. This does not cause main's `future.get()` to throw `InterruptedException`; main is waiting normally so it still receives `ExecutionException`. Two exceptions share the same name but originate on two different threads.
- `WAIT_TIMEOUT`: the third task cannot return a result yet because `releaseTask` has not been released. The wait times out and `pending.isCancelled()` remains `false`.
- `WAIT_INTERRUPTED`: `waiting-thread` has `interrupt()` called on it while preparing/performing `get()`. It catches `InterruptedException`, restores the interrupt flag via `Thread.currentThread().interrupt()`; `isInterrupted()` returns `true`. The task is not cancelled.
- `TASK_RESULT`: after `releaseTask.countDown()`, the task completes and returns `"done"`. Neither the earlier timeout nor the interruption of a waiter caused the task to fail.
- `finally` releases the latch if main exits the block due to an unexpected error, then requests executor shutdown. `shutdownNow()` is only a request to stop/interrupt work; in the successful run, all `Future.get()` calls have already completed before cleanup.

**Limitation of the example:** the `waiter` thread catches the exceptions related to `get()` properly; main's `join()` can still be interrupted by an external mechanism, and main declares `throws InterruptedException`. In a real application, executor management is usually the responsibility of an owner component with a controlled lifecycle; do not default to `shutdownNow()` to terminate all running tasks.

## 4. Why Can InterruptedException Appear in Two Places?

This is the biggest source of confusion. It is the same `InterruptedException`, yet its meaning changes depending on **where it is thrown and where it is caught**:

### 4.1. InterruptedException thrown inside the worker

Suppose `Callable<String>.call()` calls `BlockingQueue.take()`, gets interrupted, and lets `InterruptedException` propagate out. The task fails; with `submit`'s `FutureTask`, it is recorded as the cause of an exceptional completion.

The caller waits via `Future.get()`:

```java
try {
    future.get();
} catch (ExecutionException ex) {
    if (ex.getCause() instanceof InterruptedException) {
        // The task itself was interrupted and then completed exceptionally.
    }
}
```

The illustrative snippet assumes `future` exists. `ExecutionException` belongs to the result-observation layer; `InterruptedException` is the cause that occurred inside the worker. The caller may never have been interrupted at all.

### 4.2. InterruptedException thrown by get() at the caller

If the waiting thread is interrupted, `get()` can throw `InterruptedException` directly at the caller:

```java
try {
    future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Waiting itself was interrupted; do not infer that the task failed.
}
```

This is also just a snippet, assuming `ExecutionException` handling is written in the appropriate place. The caller can leave the wait while the worker continues.

An important technical distinction: `Thread.interrupted()` **reads and clears** the interrupt status of the current thread; `Thread.currentThread().isInterrupted()` reads without clearing. Do not use `Thread.interrupted()` as a "harmless check" in control flows that still need to know about the interrupt.

Inside a task, if you catch `InterruptedException` but cannot propagate it, you can restore the interrupt flag and exit cleanly. Do not turn interruption into a normal business error to be retried infinitely.

## 5. A Wait Timeout Differs from a Timeout Inside the Task

Both forms contain the word "timeout", but they belong to two different contracts:

**Timeout of the wait call:**

```java
future.get(500, TimeUnit.MILLISECONDS);
```

If no result arrives in time, **the caller itself** receives `TimeoutException`. The task does not automatically know that the caller stopped waiting. The caller can choose to keep waiting, check `isDone()`, or request cancellation.

**Timeout inside the task:**

```java
Callable<String> task = () -> {
    // An operation that may throw SocketTimeoutException.
    return fetchRemoteData();
};
```

This snippet assumes `fetchRemoteData()` and appropriate imports. If an operation inside the worker throws `java.net.SocketTimeoutException` and that exception propagates out of `call()`, `Future.get()` throws `ExecutionException` with `getCause()` being `SocketTimeoutException`. The caller has received **a task failure outcome**, not merely the expiration of a wait's time limit.

The conditions the caller must handle differ:

| Timeout source | Is the task known to have failed? | Common decision |
| --- | --- | --- |
| `Future.get(timeout)` exceeded | Not yet; it may still be running or about to finish | Wait again, return pending status, or cancel if authorized and policy allows. |
| Network timeout inside `Callable` and exception propagates | Yes, the task completed exceptionally | Classify the I/O error, evaluate retry/idempotency. |
| Service-layer deadline proactively cancels the task | `Future` may transition to cancelled state; worker may not have stopped yet | Report cancellation, coordinate cleanup, and handle side effects per contract. |

An external HTTP request returning "request timeout" does not prove that the server-side operation rolled back. Retrying immediately may create duplicate data. Use an idempotency key or reconciliation mechanism where appropriate.

## 6. CancellationException and the Limits of cancel()

A `Future` can be cancelled via `cancel(boolean mayInterruptIfRunning)`. The call returns a `boolean` indicating whether transitioning to the cancelled state succeeded according to the `Future`. After a successful cancellation, `isCancelled()` returns `true` and `get()` throws `CancellationException`.

Standalone Java 17 example, no executor required:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

public class CancelledResultDemo {
    public static void main(String[] args) {
        CompletableFuture<String> result = new CompletableFuture<>();
        System.out.println("cancelled: " + result.cancel(false));

        try {
            result.join();
        } catch (CancellationException ex) {
            System.out.println("observed: CancellationException");
        }

        System.out.println("isCancelled: " + result.isCancelled());
    }
}
```

Compile and run:

```bash
javac CancelledResultDemo.java
java CancelledResultDemo
```

Stdout:

```text
cancelled: true
observed: CancellationException
isCancelled: true
```

Here `CompletableFuture` is created incomplete, and `cancel(false)` marks it completed exceptionally due to cancellation; there is no worker to interrupt. `join()` throws `CancellationException` directly for the cancelled state of the future itself.

**Special note for `CompletableFuture`:** the `mayInterruptIfRunning` parameter of `CompletableFuture.cancel` is not used to control interrupting a running task the way `FutureTask` does; cancellation is represented in the completion state of `CompletableFuture`. Do not infer from calling `cancel(true)` that an associated computation thread has definitely been interrupted.

With `FutureTask` or a specific executor implementation, `cancel(true)` can request interrupting the thread running the task. This request may not be responded to if the task does not cooperate, is inside a non-interruptible operation, or has already performed side effects before stopping.

## 7. Why Thread.join() Cannot Propagate Task Errors

`Thread.join()` only waits for a thread to terminate; it carries no result object. A `Thread` can terminate normally or due to an uncaught exception, but the caller does not receive an `ExecutionException` from `join()`.

Illustrative snippet:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("failed");
});
worker.start();
worker.join();

// join() returns when the worker finishes; it does not rethrow "failed".
```

This code needs to be placed in a method that declares or handles `InterruptedException`. The worker can report an uncaught exception via `Thread.UncaughtExceptionHandler`, but that is a last-resort observation channel for the **thread**, not a `Future` returning a result to the caller.

For a task whose errors and values need to be handled by the caller, prefer result abstractions such as `Future`, `CompletionStage`, or a structured result-passing channel. Do not rely on the default uncaught handler to drive transaction logic.

## 8. ExecutorService.execute Differs from submit in Exception Propagation

`execute(Runnable)` and `submit(Callable/Runnable)` can differ in how exceptions are delivered to the client.

| API | Exception thrown by task | Observation channel |
| --- | --- | --- |
| `new Thread(runnable).start()` | If it escapes `run()`, the thread terminates abnormally | Thread/`ThreadGroup` uncaught handler. |
| `ThreadPoolExecutor.execute(runnable)` | With a plain `Runnable` and standard implementation, an unchecked exception escapes the worker; the worker may be replaced | Handler, worker log, or executor management hook. |
| `ExecutorService.submit(callable)` | Exception is caught and recorded by a task wrapper such as `FutureTask` | `Future.get()` receives `ExecutionException` with cause. |
| `CompletableFuture.supplyAsync(supplier)` | Exception is reflected in the completed-exceptionally state | `join/get`, `whenComplete`, `handle`, `exceptionally`. |

These are the typical behaviors in standard implementations; if an executor/framework uses wrappers, the handling mechanism may differ. Some frameworks catch task errors and invoke an internal callback instead of letting the exception escape to the uncaught handler.

If you override `ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` for monitoring, do not inspect only `t`: for a task created by `submit` as a `FutureTask`, `t` can be `null` even though the task failed, because the error is stored inside the `Future`. Understand completion timing, cancellation state, and how to access `Future.get()` appropriately before building a general monitoring mechanism.

## 9. CompletableFuture: get, join, and Error Callbacks

`CompletableFuture` also illustrates the difference between **result state** and **how the caller observes it**.

When a stage completes exceptionally due to a business error, there are two common ways to read it:

- `future.get()`: uses checked `ExecutionException` for stage failure; the caller must account for `InterruptedException`.
- `future.join()`: typically throws unchecked `CompletionException` for stage failure; does not declare checked `InterruptedException`. `join()` does not become an interruptible wait API in the same way `get()` does.
- When a stage is cancelled, `join()` may throw `CancellationException` directly; dependent stages may represent cancellation as exceptional completion and wrapping appropriate to the stage relationship.

A standalone Java 17 example using `CompletableFuture.failedFuture`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class StageFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                    new IllegalStateException("bad state")
                );

        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println(
                "JOIN: " + ex.getCause().getClass().getSimpleName()
            );
        }

        try {
            failed.get();
        } catch (ExecutionException ex) {
            System.out.println(
                "GET: " + ex.getCause().getClass().getSimpleName()
            );
        }

        String recovered = failed.exceptionally(ex -> "fallback").join();
        System.out.println("RECOVERY: " + recovered);
    }
}
```

Compile and run:

```bash
javac StageFailureDemo.java
java StageFailureDemo
```

Stdout:

```text
JOIN: IllegalStateException
GET: IllegalStateException
RECOVERY: fallback
```

`failedFuture` creates a future that is **already completed exceptionally**, so no execution thread is needed and there is no race in the example. `join` and `get` are simply two ways to observe the same failed state.

`exceptionally` creates a new stage that can return a fallback value. It does not directly mutate the original stage's exception; `failed` remains a failed stage. If the recovery function itself throws an exception, the new stage can also complete exceptionally.

### whenComplete and handle

- `whenComplete((value, error) -> ...)` is primarily for observing the value or error and returning a dependent stage. If the callback runs successfully, the dependent stage preserves the success/failure state of the original stage. If the callback itself throws, read the exceptional completion rules to understand which error takes precedence.
- `handle((value, error) -> result)` can **transform both a successful result and an error into a new result**, which is suitable when you want to classify and translate errors at a pipeline boundary.
- `exceptionally(error -> fallback)` handles the error path to produce a fallback value.
- `join()` is convenient but does not classify errors on its own and has no checked `InterruptedException`; for systems that require cooperative caller cancellation, choose an appropriate waiting and monitoring mechanism.

Do not use a logging-only callback as proof of "handled" if the business flow still needs to make a decision. You must manage the returned stage and any failure of the callback itself.

## 10. CompletableFuture Timeouts and Common Pitfalls

`CompletableFuture` has timeout APIs that mutate the future's state, unlike `get(timeout)`:

| API | Effect |
| --- | --- |
| `future.get(timeout, unit)` | Sets a wait limit for **a single call**; if it expires, throws `TimeoutException`, without completing or cancelling the future itself. |
| `future.orTimeout(timeout, unit)` | Arranges for **this `CompletableFuture` itself** to complete exceptionally with `TimeoutException` if it is still incomplete when the deadline arrives. |
| `future.completeOnTimeout(value, timeout, unit)` | Arranges for **this `CompletableFuture` itself** to complete normally with a fallback value if the deadline expires before it completes. |

`orTimeout` and `completeOnTimeout` return the same `CompletableFuture` being configured; they are not a separate copy of the original computation.

When `orTimeout` causes the future to complete exceptionally, calling `get()` afterward typically throws `ExecutionException` with `TimeoutException` as its cause. This is **an error recorded in the future's state**. It differs from a `get(timeout)` call throwing `TimeoutException` directly at the waiter.

`completeOnTimeout` likewise only sets the result of the `CompletableFuture` if it is still incomplete at the deadline; it **does not automatically interrupt or stop the background work** trying to complete the future. If the old work has side effects, they must still be controlled separately.

For a pipeline where you do not want to alter the state of a shared future just to cap one caller's wait time, use a timed wait mechanism or design a separate stage with an explicit timeout policy instead of arbitrarily calling `orTimeout` on a shared future.

## 11. Stable Error Representation Across Async Boundaries

In an async API, callers should distinguish **business errors of the task** from **operational errors while waiting**. Only expose error types that callers need to handle in the public contract; avoid leaking internal exceptions from executors or dependencies.

Example:

```java
public CompletableFuture<Report> generateReport(ReportRequest request);
```

This is an illustrative signature; `Report`, `ReportRequest`, and the enclosing class are undefined. The contract should specify:

- Under what conditions will the future complete normally with a `Report`?
- With which stable, meaningful errors does it complete exceptionally: validation, missing data, lost connection, quota limit?
- How is the original task exception preserved in `cause`?
- Who has the authority to cancel, and does cancellation actually stop the work?
- Are there task-level or workflow-level time limits, and after which side effects can a timeout occur?
- If the caller stops waiting, will the result still be saved or events still be emitted?

Do not write an async API that forces consumers to catch exception types from an internal HTTP/DB library unless that is an intentional design commitment. Nor should you turn every exception into `RuntimeException("Failed")` and lose error codes or diagnostic causes.

If you need to return a "pending" or "retry later" status to the HTTP layer, that outcome must be based on workflow policy; a `TimeoutException` at the waiter is not enough to declare the entire task failed.

## 12. Who Owns Cancellation Authority and Task Lifecycle?

A caller with permission to wait does not automatically have permission to **cancel the task for everyone**. A `Future` may represent a task exclusive to one request, or work observed by multiple callers.

Consider:

1. Is the task **exclusive** or **shared**? Will cancelling on one caller's timeout make another caller lose work?
2. Has the task already performed side effects? Is there an idempotency key or compensating action?
3. Does the task support `cancel(true)` via interruption? Does the task clean up in `finally`/`try-with-resources`?
4. If the caller is interrupted, does policy require propagating `InterruptedException`, restoring the flag and exiting, or keeping the task alive?
5. When the executor shuts down, who waits for tasks to finish and releases resources? Never let one waiter giving up cause resources to be orphaned.

Avoid combining them blindly:

```java
catch (TimeoutException ex) {
    future.cancel(true);
    return retrySameOperation();
}
```

This snippet **illustrates a potentially dangerous practice**, not a standalone program. If the old task has already written partial data or does not respond to interruption, retrying immediately can cause duplicate operations. Before cancelling/retrying, determine ownership, guarantee termination, and verify idempotency of the operation.

In a payment-processing system, a web-layer request timeout may need to return "processing" and provide a status-lookup ID, rather than asserting "payment failed."

## 13. Proper Layered Exception Handling

Consider a hypothetical system where a web request waits for a report-import task:

- **Task layer** catches exceptions it can explain or recover from; remaining exceptions are recorded by the `Future`/`CompletionStage`.
- **Task boundary** translates vendor errors into stable application error codes, preserving the cause for diagnostics.
- **Waiting/request layer** distinguishes `ExecutionException` (task failed), `InterruptedException` (caller interrupted), `TimeoutException` (wait expired), and `CancellationException` (result cancelled).
- **Workflow owner** decides whether to cancel or keep waiting, based on task criticality and ownership.
- **Monitoring** tracks task failures as well as waiter timeouts/interruptions, without lumping them all into a single "task failure" metric.

**Illustrative** classification pattern, not a standalone program:

```java
try {
    return future.get(waitDuration, TimeUnit.MILLISECONDS);
} catch (ExecutionException ex) {
    Throwable taskCause = ex.getCause();
    throw translateTaskFailure(taskCause);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new WaitingInterruptedException(ex);
} catch (TimeoutException ex) {
    throw new ResultNotReadyException(ex);
} catch (CancellationException ex) {
    throw new TaskCancelledException(ex);
}
```

`WaitingInterruptedException`, `ResultNotReadyException`, `TaskCancelledException`, `translateTaskFailure`, `future`, and `waitDuration` are assumed parts of the application API. What matters is that **each branch has a different meaning**, and `future.cancel(true)` is not called unless policy requires it.

If an `ExecutionException` carries an `InterruptedException` cause because the **task** failed, do not mistakenly mark the **waiter** as interrupted. Do not call `Thread.currentThread().interrupt()` on the waiter just because the worker's cause is `InterruptedException`: that interrupt belongs to the worker's context, not the current thread.

## 14. Do Not Neglect Handling Waiter Interruption

Interruption is a cooperative mechanism, unlike throwing a regular business exception. When a blocking method throws `InterruptedException`, the current thread's interrupt status has usually been cleared. Two appropriate ways to handle it:

**Approach A — propagate the interruption:**

```java
public String waitResult(Future<String> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
```

This snippet is a valid Java method when placed inside a class with appropriate imports. Higher-level callers decide whether to stop or recover; the method does not alter the meaning of the error.

**Approach B — translate the error type while restoring the flag:**

```java
try {
    return future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new WaitingInterruptedException(ex);
}
```

This snippet requires the class/type context noted earlier; the goal is to preserve the interruption signal for outer layers.

Do not swallow `InterruptedException` and call `get()` again in an infinite loop. Doing so can prevent shutdown from completing or keep the caller stuck longer than policy allows.

If you must clean up caller-owned resources in `finally`, clean up strictly within that scope; do not close the worker's resources merely because the waiter was interrupted.

## 15. Testing Failure Channels Independently

A good test suite distinguishes failure sources even when outputs look similar.

| Scenario | Expectation at caller | Assertion about task |
| --- | --- | --- |
| `Callable` returns a value | `get()` returns the result | Succeeded |
| `Callable` throws `IllegalArgumentException` | `ExecutionException`; cause is `IllegalArgumentException` | Completed with failure |
| `Callable` throws `InterruptedException` | `ExecutionException`; cause is `InterruptedException` | Completed with failure due to exception in task |
| Thread calling `get()` is interrupted while waiting | `InterruptedException` at waiter | Do not conclude the task failed |
| `get(timeout)` expires while task is still blocked | `TimeoutException` | Not cancelled by `get(timeout)` |
| `cancel(...)` succeeds | `CancellationException` on `get()` | Future cancelled; do not infer all side effects stopped |
| `CompletableFuture` exceptional | `get()` typically uses `ExecutionException`; `join()` typically uses `CompletionException` | Stage holds the failure |
| `CompletableFuture.orTimeout` completes exceptionally | `get()` receives `ExecutionException` with cause `TimeoutException` | This is an exceptional state of the future |

Use `CountDownLatch`, `Phaser`, or appropriate synchronization to control test ordering. Do not rely purely on `Thread.sleep(50)` and hope the task is still running; time-based tests like that are flaky when CI is overloaded.

Note that a task may have already completed right before the caller invokes `interrupt` or `get(timeout)`. In tests meant to reliably distinguish waiter errors, hold the task at a point where it cannot return a result yet—such as an unreleased latch—as in the program in Section 3.

### Avoid testing "right exception on the wrong thread"

If a test needs to verify the **caller's** `InterruptedException`, control the thread calling `get()` and verify the catch block on **that thread**. You cannot verify it by having the worker throw `InterruptedException` and thinking you tested the waiter's error path.

Conversely, if a test needs to verify task failure, use `Future.get()` and check `ExecutionException.getCause()`. Calling `Thread.join()` directly or only checking `UncaughtExceptionHandler` logs does not replace testing the `Future` contract.

## 16. Common Mistakes

**"`Future.get()` threw `InterruptedException`, so the task was interrupted."** Wrong: that usually means the thread calling `get` was interrupted. The task may continue running and return a result later.

**"The task threw `InterruptedException`, so the caller must catch `InterruptedException` from `get`."** With normal `submit(Callable)`, task failures are wrapped in `ExecutionException`, even when the cause is `InterruptedException`.

**"`TimeoutException` means the task failed."** A wait timeout only says the caller did not receive the result in time. Do not automatically cancel or attribute a failure to the task.

**"If the wait times out, retry immediately."** The old task may still be writing data. Retrying can cause duplicate side effects; evaluate idempotency and cancellation authority.

**"`cancel(true)` stopped all activity."** Interruption is cooperative; a cancelled state does not prove the worker finished releasing resources or rolling back.

**"Ignoring the `Future` means errors are already logged."** With `submit`, exceptions can be stored inside the `Future` and never reach the uncaught handler; if nobody reads the `Future`, failures can go unnoticed.

**"Just `catch (Exception)` and return one generic error."** This erases the distinction between task failure, waiting interruption, deadline, and cancellation. Wrong retries or status responses become likely.

**"`CompletionException` and `ExecutionException` have different business causes."** They are typically two wrappers depending on the observation API (`join` or `get`) for the same failure of a `CompletableFuture`.

**"A worker's error is the caller's interrupt error."** Do not restore the caller's interrupt flag based on `ExecutionException.getCause() instanceof InterruptedException` if the caller was not interrupted.

**"Catching `ExecutionException` is enough for `get`."** There is also `InterruptedException`; `get(timeout)` has `TimeoutException`; cancellation leads to `CancellationException`. Documentation and code must reflect all failure paths the caller must handle.

## 17. Exercises and Self-Check Questions

**Exercise 1.** A file-processing task can take 10 seconds. An HTTP API waits `future.get(2, SECONDS)` and gets `TimeoutException`. Should it return "processing failed" and resubmit the task immediately?

**Answer hint:** You must not conclude the task failed. Return a job ID/pending status, define a policy for cancelling or continuing to wait, and enforce idempotency before retrying.

**Exercise 2.** A worker calls `queue.take()`, is interrupted, and lets `InterruptedException` propagate out of `Callable`. The caller calls `get()` without being interrupted. Which exception does the caller catch?

**Answer:** `ExecutionException`, with `getCause() instanceof InterruptedException`. `InterruptedException` is an error that occurred in the worker, not a direct exception of the caller's wait operation.

**Exercise 3.** During another wait, while the caller is in `get()`, another thread calls `caller.interrupt()`. Is the worker's `Future` automatically cancelled?

**Answer:** No. The caller's `get` can throw `InterruptedException`, but the `Future` can still run and complete; only cancel when the owner executes an appropriate cancellation policy.

**Exercise 4.** `CompletableFuture.failedFuture(new IllegalStateException("bad"))` is observed via `join()` and `get()`. What is the difference?

**Answer:** `join` typically throws `CompletionException` containing the cause `IllegalStateException`, whereas `get` throws checked `ExecutionException` containing the corresponding cause. The underlying failed state of the stage is the same.

**Exercise 5.** Callers `A` and `B` both observe a shared `CompletableFuture`. `A` calls `orTimeout(...)` with a short deadline. What can affect `B`?

**Answer:** `orTimeout` affects the `CompletableFuture` itself; if the deadline wins, the future completes exceptionally for every observer, including `B`. If you only want to limit `A`'s own wait time, do not arbitrarily mutate the shared future this way.

## 18. Key Takeaways

Classify exceptions by **the subject affected** before deciding on behavior:

- **`ExecutionException` + cause:** the task completed with a failure; inspect the cause to handle errors from the worker.
- **`InterruptedException` thrown directly by `get()`:** the caller thread was interrupted while waiting; propagate it or restore the interrupt flag, and do not assume the task failed.
- **`TimeoutException` directly from `get(timeout)`:** the caller's wait time expired; the task may still be continuing.
- **`CancellationException`:** the result was cancelled per the Future's state; whether background execution stops depends on the API and cooperation.
- **`CompletionException` in `CompletableFuture.join()`:** a wrapper when observing a stage's exceptional state; inspect the cause rather than mistaking it for an error of the waiting thread itself.

Clear boundaries help callers react accurately to actual task failures, their own interruption, expired deadlines, or cancellation. As a result, applications can keep state consistent, avoid duplicate retries, and preserve cause information for handling, monitoring, and diagnostics.
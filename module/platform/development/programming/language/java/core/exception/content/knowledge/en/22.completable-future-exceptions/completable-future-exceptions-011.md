# CancellationException and the mayInterruptIfRunning Limitation of CompletableFuture in Java

> **Topic:** Java Core → Exception → CompletableFuture. This content explains the meaning of `CancellationException`, the behavior of `CompletableFuture.cancel(boolean)`, why the `mayInterruptIfRunning` argument has no effect in interrupting tasks for `CompletableFuture`, how to distinguish **cancelling the result state** from **stopping running work**, and how to handle coordination properly among `Future`, `ExecutorService`, timeouts, dependent stages, and interruption.

## 1. Three Events That Must Be Distinguished

In asynchronous programming, the three events below are easily conflated even though they differ in nature.

1. **Cancelling the result (cancel completion):** a future transitions to a cancelled state, so callers waiting for the result receive `CancellationException` instead of a successful value.
2. **Interrupting a thread (interrupt):** sending a cooperative request via `Thread.interrupt()`; the thread may react at blocking points or when actively checking the interrupt flag.
3. **Stopping/undoing work:** the computation actually stops executing, cleans up resources, and if necessary rolls back side effects. This requires dedicated design; it cannot be inferred solely from the future's state.

A `CompletableFuture` can be marked as cancelled **while the code running in the executor continues**. After a successful `cancel` call, the caller may not receive the final result of the computation even though the computation is still performing I/O, writing data, or consuming CPU.

**Key takeaway:** `CompletableFuture.cancel(true)` is not equivalent to "forcing the worker to stop"; `CancellationException` is a representation of a cancelled state, not a guarantee that all side effects have stopped or been rolled back.

## 2. What Is CancellationException?

`java.util.concurrent.CancellationException` is an unchecked exception (extending `IllegalStateException`, and then `RuntimeException`). In future/asynchronous APIs, it indicates that waiting for or retrieving a result encountered a task that has been cancelled.

Example:

~~~java
// Snippet that can be placed inside a Java method.
java.util.concurrent.CompletableFuture<String> future =
        new java.util.concurrent.CompletableFuture<>();

future.cancel(false);

try {
    future.join();
} catch (java.util.concurrent.CancellationException ex) {
    System.out.println("result was cancelled");
}
~~~

For a cancelled `CompletableFuture`, the following checks are typically all true:

~~~java
// future in the example above has been cancelled.
future.isDone();                    // true
future.isCancelled();               // true
future.isCompletedExceptionally();  // true
~~~

Because **cancellation is a form of exceptional completion**, `isCompletedExceptionally()` is not enough to determine whether a task failed due to a business error or was cancelled. Check `isCancelled()` and choose the appropriate handling path.

**Important detail:** `isCancelled()` for `CompletableFuture` is based on whether the future completed with a `CancellationException`. Therefore, calling `completeExceptionally(new CancellationException(...))` can also lead to a state considered cancelled. When classification is needed, examine the semantics of the result state rather than assuming only the `cancel()` method can produce that state.

## 3. The CompletableFuture.cancel(boolean) Contract

Signature:

~~~java
public boolean cancel(boolean mayInterruptIfRunning)
~~~

According to the Java SE 17 documentation for `CompletableFuture`, the `cancel` method attempts to complete the future exceptionally with a `CancellationException` if it is not already completed. The call has semantics equivalent to performing exceptional completion with a new `CancellationException` on a pending future.

Return value:

- `true` if the future was cancelled successfully by this call **or was already in the cancelled state**.
- `false` if the future had already completed in a non-cancellation state, such as succeeding with a value or failing with another exception.
- `true` must not be interpreted as a guarantee that the underlying computation has stopped.

In particular, **the `mayInterruptIfRunning` argument has no effect in the `CompletableFuture` implementation**, because this class's methods do not use interrupts to directly control the computation process. In Java SE 17, calling `cancel(true)` on a `CompletableFuture` does not automatically send an interrupt to the worker executing the supplier.

This holds true even when the future is associated with `CompletableFuture.supplyAsync(...)` or `runAsync(...)`. If the supplier is already running, it may continue until it completes on its own or encounters another cancellation mechanism. If cancellation wins before the task starts, the specific execution mechanism may skip the body already marked as completed; that does not constitute a guarantee that `cancel(true)` can interrupt a **running** task.

~~~java
// Illustration: future receives cancelled status, does not guarantee stopWorker().
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> runSlowOperation());

boolean accepted = result.cancel(true);
// accepted reflects the completion result.
// Do not infer that runSlowOperation() was interrupted or rolled back.
~~~

`runSlowOperation()` is an illustrative method that would exist in the application. To request stopping the actual task, you must design another coordination mechanism, such as a cancellation token checked by the task, retaining a `Future` returned by an executor, or a cancellation API for the I/O operation.

## 4. Comparison with Future.cancel(boolean)

Although sharing the same method name, `mayInterruptIfRunning` carries a different meaning when operating on a `FutureTask`/`Future` returned by `ExecutorService.submit()`.

| Criterion | `CompletableFuture.cancel(true)` | `Future.cancel(true)` from `ExecutorService.submit` |
|---|---|---|
| Directly affected target | Completion state of `CompletableFuture` | Cancellation state of the `Future` task |
| `mayInterruptIfRunning` | **Has no effect in interrupting the computation** per class contract | If the task is running, the implementation may **request interrupting the executing thread** |
| Guarantees task actually stops? | **No** | **No**: interruption is cooperative; the task may not respond |
| `get()` after cancellation | `CancellationException` | `CancellationException` |
| Side-effect rollback capability | Not performed automatically | Not performed automatically |
| Proper handling | Needs a separate cancellation channel if stopping the worker is required | Design the task to respond to interrupts, clean up, and manage lifecycle |

In the `Future.cancel(boolean)` contract, `mayInterruptIfRunning = true` allows requesting an interrupt when the task is running; `false` does not request interrupting already-running work. Even when `Future.cancel(true)` returns `true`, it still **does not prove** that the code has stopped completely or that resources have been released. The task might ignore interrupts, block on an API that does not respond to interrupts, or already have committed side effects.

`CompletableFuture` implements `Future` but specifically defines that this flag is not used to control computation; therefore, assumptions from `FutureTask` should not be applied directly to `CompletableFuture`.

## 5. Diagram of Two Independent Flows

~~~text
API-calling thread                           Executor worker
------------------                           -----------------------
CompletableFuture.supplyAsync(supplier)  --> starts supplier
         |                                      |
         |                                   waiting on latch/I/O
         |
result.cancel(true)
         |
 CompletableFuture transitions to cancelled
         |
result.join() -> CancellationException       worker may still be running
         |                                      |
         |                                   completes side effects
         |                                      |
         |                                   returns a value
         |                                      |
         |                                   result arrives too late
         v
caller does not receive that value from the cancelled future
~~~

The diagram illustrates the case where the supplier **has already started running** and has no independent cancellation mechanism. It does not claim that every supplier always runs to completion in all situations: the task might respond to a cancellation token, be interrupted by another source, fail due to I/O, or never start if the future was already cancelled beforehand.

## 6. Complete Java 17 Program: Cancelling CompletableFuture Does Not Interrupt the Worker

The following program uses a `CountDownLatch` to ensure the task has started before the caller cancels. It also uses a single-threaded `ExecutorService` and a subsequent marker task to ensure observation occurs **after the previous supplier finishes**, avoiding results that depend on `sleep` or OS scheduling timing.

Save the entire code to **`CompletableFutureCancellationDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        demonstrateCompletableFuture();
        demonstrateSubmittedFuture();
    }

    static void demonstrateCompletableFuture() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        AtomicBoolean completedWork = new AtomicBoolean(false);

        try {
            CompletableFuture<String> result =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            sawInterrupt.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        }

                        completedWork.set(true);
                        return "finished";
                    }, pool);

            CompletableFuture<Integer> dependent =
                    result.thenApply(String::length);

            started.await(); // Supplier has started.
            System.out.println("CF cancel: " + result.cancel(true));
            System.out.println("CF isCancelled: " + result.isCancelled());
            System.out.println("CF isExceptional: "
                    + result.isCompletedExceptionally());

            try {
                result.join();
            } catch (CancellationException ex) {
                System.out.println("CF join: CancellationException");
            }

            try {
                dependent.join();
            } catch (CompletionException ex) {
                System.out.println("Dependent cause: "
                        + ex.getCause().getClass().getSimpleName());
            }

            release.countDown();
            // A single-threaded executor: marker runs after supplier.
            pool.submit(() -> {}).get();

            System.out.println("CF worker interrupted: " + sawInterrupt.get());
            System.out.println("CF worker finished work: " + completedWork.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    static void demonstrateSubmittedFuture() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            Future<?> submitted = pool.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await(); // Wait until interrupted.
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            System.out.println("Future cancel: " + submitted.cancel(true));
            finished.await();
            System.out.println("Future worker interrupted: "
                    + sawInterrupt.get());

            try {
                submitted.get();
            } catch (CancellationException ex) {
                System.out.println("Future get: CancellationException");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac CompletableFutureCancellationDemo.java
java CompletableFutureCancellationDemo
~~~

**Exact stdout:**

~~~text
CF cancel: true
CF isCancelled: true
CF isExceptional: true
CF join: CancellationException
Dependent cause: CancellationException
CF worker interrupted: false
CF worker finished work: true
Future cancel: true
Future worker interrupted: true
Future get: CancellationException
~~~

**Step-by-step explanation:**

1. The `started` latch confirms that the `supplyAsync` supplier has started running. `result.cancel(true)` succeeds, putting `result` into the cancelled state, making `isCancelled` and `isCompletedExceptionally` return `true`.
2. `result.join()` throws `CancellationException` directly. The dependent stage `thenApply(String::length)` does not perform the length transformation and completes exceptionally; `dependent.join()` reports a `CompletionException` whose `cause` is `CancellationException`.
3. Because `CompletableFuture.cancel(true)` does not interrupt the supplier, the supplier continues waiting on `release`. After `main` releases the latch, the supplier performs the remaining work and updates `completedWork`, even though the future result has been cancelled. The marker task `pool.submit(() -> {}).get()` guarantees the previous supplier has finished running in the single-threaded executor; the `false` and `true` output on those two check lines does not rely on scheduler luck.
4. The second part uses a `Future<?>` created by `ExecutorService.submit`. After the `Runnable` has started, `submitted.cancel(true)` can request an interrupt to the thread waiting in `await()`. The `Runnable` catches `InterruptedException`, records `sawInterrupt=true`, and finishes. `submitted.get()` still reports `CancellationException` because the future was cancelled.
5. Both mechanisms share the **cancelled future** outcome, yet they differ clearly in whether they attempt to send an interrupt to the actual work. Even `Future.cancel(true)` only relies on task cooperation and cannot be treated as a transaction rollback.

The sample code manages the executor with `shutdownNow()` in `finally` to prevent thread leaks if a step fails. In production applications, you should have timeouts and a plan for handling work that intentionally does not respond to interrupts; this example deliberately chooses interruptible operations so the output is deterministic under normal execution conditions.

## 7. Why Can join/get Report CancellationException Differently?

If **the future itself** was cancelled, `CompletableFuture.join()` and `get()` can throw `CancellationException` **directly**. This is an unchecked exception, not an `ExecutionException` or `CompletionException` wrapping a business error.

Conversely, a dependent stage propagating an error from a cancelled source typically completes exceptionally through a `CompletionException` wrapper whose `cause` is `CancellationException`. Therefore, you must distinguish between the result of the *source* and a *dependent stage*.

~~~java
// Java illustration snippet, can be placed inside a method.
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> derived = source.thenApply(String::length);
source.cancel(false);

try {
    source.join();
} catch (CancellationException ex) {
    // Direct cancellation on source.
}

try {
    derived.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause(); // May be CancellationException.
}
~~~

In this situation, `derived.isCompletedExceptionally()` is `true`. However, `derived.isCancelled()` is typically `false` because it completed exceptionally with a wrapper propagated from the source, **not** because that stage itself was marked cancelled. Do not write logic assuming "if `isCancelled()` is false, it is definitely unrelated to cancellation"; inspect the stage's `cause` when you need to classify the root cause.

With `get()` on a dependent stage, the error-reporting wrapper is typically `ExecutionException`, which may contain `CancellationException` as its cause. Do not assume a single simple exception pattern applies to every combination of stages.

## 8. How Does Cancellation Affect Dependent Stages?

Stages chained from a cancelled future follow the completion semantics of `CompletionStage`:

| Stage | When source is cancelled | Meaning |
|---|---|---|
| `thenApply(fn)` | Does not invoke `fn` on the success branch; dependent stage completes exceptionally | No successful computation is performed |
| `thenCompose(fn)` | Does not invoke `fn` of the success branch; dependent stage fails | Cancellation at the source propagates along the error channel |
| `thenAccept`, `thenRun` | Action belongs only to the success branch, so it does not run | Action's side effects do not occur from a failed completion |
| `exceptionally(fn)` | Callback receives the error and can return a fallback value for the **new stage** | Useful if cancellation is treated as a valid fallback |
| `handle((value, error) -> ...)` | Invoked with failure information to produce a new result | Can classify cancellation separately |
| `whenComplete((value, error) -> ...)` | Observes the error, typically preserving the exceptional completion | Suitable for logging/metrics; does not recover by default |

An `exceptionally` stage can recover from both business errors and cancellation. This **may not match user intent**: cancelling a request sometimes must stop the entire pipeline, whereas a fallback causes downstream stages to continue as if it succeeded. Therefore, you should decide whether `CancellationException` should be propagated or converted into a "cancelled" value according to the API.

Example:

~~~java
// Snippet: fallback for normal errors, while still preserving cancellation.
CompletableFuture<String> recovered =
        source.exceptionally(error -> {
            Throwable root = error;
            if (root instanceof CompletionException && root.getCause() != null) {
                root = root.getCause();
            }
            if (root instanceof CancellationException) {
                throw new CompletionException(root);
            }
            return "fallback";
        });
~~~

This is an example of an application-layer policy. Because the recovery callback throws `CompletionException` on the cancellation branch, the `recovered` stage continues to complete exceptionally instead of returning `"fallback"`. When unwrapping the cause, do not unwrap every exception layer indefinitely or discard error information; handle the structure properly according to the specific API.

### Does cancelling a dependent stage cancel the source?

Not by default. `derived.cancel(true)` primarily cancels the result of **derived**, without guaranteeing that the original task is interrupted or that `source` is cancelled. Similarly, cancelling `source` may cause dependent stages to complete exceptionally, but it does not mean that all side-effecting tasks that have run or are running in other stages are stopped.

Systems that require true **cancellation propagation** must define the relationship between parent/child jobs, cancellation tokens, or resource-level cancellation operations.

## 9. Differences Between cancel, completeExceptionally, and obtrudeException

Several ways of completing exceptionally commonly appear in code:

~~~java
CompletableFuture<String> a = new CompletableFuture<>();
a.cancel(false);

CompletableFuture<String> b = new CompletableFuture<>();
b.completeExceptionally(new CancellationException("cancelled by user"));

CompletableFuture<String> c = new CompletableFuture<>();
c.completeExceptionally(new IllegalStateException("failed"));
~~~

- `a` represents a cancellation request; for `CompletableFuture`, the final state is exceptional completion with `CancellationException`.
- `b` can also be considered cancelled because the actual exception cause is `CancellationException`.
- `c` completes exceptionally due to a business error, but is not cancelled.
- `obtrudeException(ex)` can forcibly overwrite the result held by the future according to its special semantics, even if already completed. Do not use it in place of `cancel`/`completeExceptionally` in normal flows because already-triggered dependent stages may retain the previous state, causing inconsistent observations.

Note when logging and classifying: do not just look at `isCompletedExceptionally()` and mark every task as failed. Classify cancellation, timeout, technical failure, and business error according to their respective contracts.

## 10. Timeout Does Not Mean Cancellation or Interrupt

`CompletableFuture` supports:

- `orTimeout(timeout, unit)`: if the future has not completed by the deadline, it is completed exceptionally with `TimeoutException`.
- `completeOnTimeout(value, timeout, unit)`: if it has not completed by the deadline, it is completed normally with `value`.
- `cancel(...)`: transitions the future into the cancellation state with `CancellationException` when applicable.

These timeout methods **act on the future they are called on**, not necessarily creating a new independent future. Normal completion, timeout, and cancellation can race against each other; whichever wins depends on timing.

~~~java
// Illustrative snippet.
CompletableFuture<String> result = new CompletableFuture<>();
result.orTimeout(2, java.util.concurrent.TimeUnit.SECONDS);

// When timed out and not yet complete, join() throws CompletionException
// with cause TimeoutException, not CancellationException.
~~~

**A `TimeoutException` result does not prove the computation has stopped.** If the task is running on an executor or making a network request, it may still be executing. If you want to cancel the actual work after a timeout, you must invoke that work's own cancellation mechanism or pass a cancellation token and make the task cooperative.

`completeOnTimeout("fallback", ...)` can also cause consumers to see success even though the underlying external computation is still running. If the source has side effects, this must be stated clearly in the contract so callers do not assume the operation has actually ended.

## 11. Ensuring Real Task Cancellation When Needed

There are several strategies, depending on the abstraction and scope of work.

### 11.1. Retain the Actual Execution Future

When you control the `ExecutorService` and need to interrupt a running task, a `Future<?>` from `submit` is a more appropriate cancellation channel than a bare `CompletableFuture`.

~~~java
// Snippet in an application with an ExecutorService pool.
Future<?> task = pool.submit(() -> performBlockingWork());
boolean requested = task.cancel(true);
~~~

`performBlockingWork()` must react to interrupts or check cooperative state. The `mayInterruptIfRunning` flag now has semantics for the `Future` implementation returned by the executor, yet `requested` is still not a guarantee that "all work has stopped and rolled back".

### 11.2. Cancellation Token for Non-Blocking Tasks

For computation loops that do not call interruptible APIs, you can use a token such as `AtomicBoolean`:

~~~java
// Snippet: task reads the token in a loop.
AtomicBoolean cancelled = new AtomicBoolean(false);

// Caller requests cancellation:
cancelled.set(true);

// Inside the task:
while (!cancelled.get()) {
    doSmallUnitOfWork();
}
~~~

Any task that can run long code between token checks will not stop immediately; you need to choose reasonable check boundaries, preserve invariants, and clean up. The token must be shared properly between the requester and the task, unlike simply calling `CompletableFuture.cancel(true)`.

### 11.3. Stopping Specific I/O or Resources

Some operations do not respond to thread interrupts in the way you might expect. In those cases, use client timeouts, request cancellation APIs, proper resource closing, or shutdown mechanisms provided by the library, per that service's Javadoc. Do not arbitrarily close a shared connection from a cancellation callback if it is still serving other tasks.

### 11.4. Cancellation Protocol for APIs Returning CompletableFuture

A library can return both a result future and a cancellation control object, or provide a `cancelRequest(id)` method. The caller can simultaneously request cancelling the actual task and complete the future in a cancelled state according to a consistent policy. Races must be addressed: the task may have already completed/committed before the cancellation signal arrives.

## 12. Interrupt, InterruptedException, and Restoring the Flag

A cooperative task may wait on `BlockingQueue.take()`, `Thread.sleep()`, `Object.wait()`, `CountDownLatch.await()`, or other interruptible APIs. When interrupted, many methods throw `InterruptedException` and clear the interrupt status.

If a method can declare `throws InterruptedException`, it is usually best to propagate the exception per contract. If it cannot propagate it, as in `Runnable.run()`, it is typically necessary to:

~~~java
@Override
public void run() {
    try {
        doInterruptibleWork();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return; // Exit instead of continuing as if not cancelled.
    }
}
~~~

`doInterruptibleWork()` is an illustrative method declaring `throws InterruptedException`. `Thread.currentThread().interrupt()` restores the signal, while `return` exits the current execution path. Restoring the flag does not automatically roll back changes made by the task prior to the error.

**Do not think `CompletableFuture.cancel(true)` will automatically send the task into the catch block above.** With `CompletableFuture`, this argument is not used to interrupt the computation. The `InterruptedException` catch block only runs if the thread is actually interrupted through an appropriate channel or a blocking operation throws it for an API-defined reason.

## 13. Race Between Completion and Cancellation

Suppose a producer is about to call `complete("done")`, while a request handler calls `cancel(true)` at nearly the same time:

~~~java
// Illustration of racing logic; these lines do not create threads themselves.
CompletableFuture<String> result = new CompletableFuture<>();

// Producer:
boolean completed = result.complete("done");

// Request cancel:
boolean cancelled = result.cancel(true);
~~~

The outcome depends on who wins the race:

- If `complete("done")` wins while the future is pending, the result succeeds; the subsequent `cancel` call returns `false`.
- If `cancel(true)` wins first, the result is cancelled; the subsequent `complete("done")` call returns `false`.
- If the result was already cancelled earlier, a subsequent `cancel` call may still return `true` per the class contract, even though it does not perform another cancellation of actual work.

Do not write:

~~~java
// Wrong if treating the two operations as atomic.
if (!result.isDone()) {
    result.cancel(true);
    // Cannot assert that cancel won if ignoring the boolean result.
}
~~~

Checking `isDone()` and then mutating is a *check-then-act* pattern: another thread can complete the future in between. Use the completion result and define a policy for when cancellation arrives too late.

**In real production systems, cancellation can arrive after commit:** the API must define that "cancelling a request" does not necessarily mean "undoing completed side effects". For example, a payment has already been processed at an external system and then the client times out; calling `cancel` on the future does not issue a refund.

## 14. Designing Cancellation Around Business Requirements

Before designing a cancellation API, ask what "cancel" means in the business domain:

| Type of Work | Reasonable Expectation | Additional Mechanism Needed |
|---|---|---|
| Pure computation, no side effects | Can stop between steps | Token/interrupt flag checked periodically |
| Network read | Stop waiting and release resources if the client supports it | Timeout, cancel request, or closing the resource in the proper scope |
| File write | Do not leave incomplete files per contract | Temporary file, flush/close, atomic move when appropriate |
| DB update | Keep transactions consistent | Transaction, rollback before commit; handle race with completion |
| Sending email/events | May not be recallable once sent | Idempotency, outbox, delivery status check |
| Payment | Must not be assumed reversible | Idempotency key, inquiry, and explicit refund/compensation workflow |

A future reflects only one part of the system. A user clicking "Cancel" may be requesting to stop an uncommitted operation; if the operation has already committed, the system must report the actual state and offer an allowed reversal workflow, rather than simply marking the UI as cancelled.

## 15. Common Mistakes

1. **"`cancel(true)` on CompletableFuture interrupts the supplier."** No. `mayInterruptIfRunning` is not used to control this class's computation.
2. **"`cancel(false)` on CompletableFuture is fundamentally different from `cancel(true)`."** Not regarding `CompletableFuture`'s interrupt mechanism; both share the same limitation of not controlling the worker.
3. **"A cancelled future means I/O has stopped."** No. External resources may still be active.
4. **"`Future.cancel(true)` always stops the task immediately."** No. For an executor Future, it can send an interrupt; the task still must cooperate.
5. **"`CancellationException` is a business error like any `RuntimeException`."** It usually represents a cancellation request and should have its own policy.
6. **"`isCompletedExceptionally()` distinguishes cancellation from failure."** No. Cancellation is also an exceptional completion.
7. **"A dependent stage's `isCancelled()` must be true when the source is cancelled."** No. The dependent stage may hold a `CompletionException` wrapping `CancellationException`.
8. **"`join()` always wraps `CancellationException` in `CompletionException`."** Not for a cancelled source future: it can throw `CancellationException` directly.
9. **"Catching `CancellationException` and returning success is always right."** No. Doing so can accidentally continue a pipeline that the user requested to stop.
10. **"`orTimeout` automatically interrupts work."** No. It handles the completion state when the deadline expires.
11. **"Just call cancel, no need to clean up resources."** Wrong: cleanup, executor shutdown, and task state coordination are still required.
12. **"Checking `isDone` before `cancel` avoids races."** Wrong: the state can change between the two calls.
13. **"A cancelled task automatically rolls back transactions."** Wrong: completion state does not provide transactionality.
14. **"Just catch `Throwable` when a task is cancelled."** Avoid overly broad catches that mask serious errors; classify cancellation/interrupt/business errors per contract.

## 16. Reliable Testing

Concurrency tests should separately verify **the future's state** and **the worker's behavior**, not just `assertThrows(CancellationException.class, future::join)`.

| Scenario | Check |
|---|---|
| Cancel a pending CompletableFuture | `isCancelled()`, `isDone()`, and `isCompletedExceptionally()` are all true |
| Retrieve result of a cancelled future | `join()`/`get()` throws `CancellationException` directly in the source case |
| Dependent stage on a cancelled future | Appropriate `CompletionException`/cause; success-branch callbacks do not run |
| `supplyAsync` already running, then `cancel(true)` called | Future is cancelled, but do not assume the supplier was interrupted; measure with a latch |
| `ExecutorService.submit` running an interruptible task, then `cancel(true)` | Task observes the interrupt and enters the cleanup path |
| Cancel after `complete(value)` wins | `cancel` returns `false`; original value is preserved |
| Repeated cancel on an already cancelled future | Understand the boolean return value and do not infer that new work is cancelled each time |
| Timeout before computation finishes | Future completes with timeout; underlying I/O may still be active |
| Cancel a task with side effects | Data after cancellation/commit still conforms to the business contract |
| Shutdown executor | No thread leaks; incomplete tasks are handled per policy |

Use `CountDownLatch`, `CyclicBarrier`, or appropriate coordination primitives to construct verifiable execution schedules. Avoid using `Thread.sleep(100)` and guessing that the worker has started. A passing test does not replace reasoning about races, but tests with proper boundaries help catch false assumptions about interrupts.

## 17. Safe Implementation Checklist

1. **What kind of Future is it?** `CompletableFuture`, `FutureTask`, or a custom abstraction? Read the `cancel` semantics of the actual type.
2. **Do you need to cancel the result or interrupt the work?** If execution must stop, there must be a dedicated control path supporting it.
3. **Is the task interruptible?** If not, use a cooperative cancellation token or the library's close/cancel API.
4. **Are there dependent stages?** Distinguish direct cancellation from wrapped exceptions in dependent stages.
5. **Are there timeouts?** A timeout does not prove external resources have stopped running.
6. **Can completion race?** Handle races among `complete`, `cancel`, timeout, and exception.
7. **Are there resources and side effects?** Handle cleanup, transactions, idempotency, and commit status determination.
8. **Are error observation channels clear?** Classify `CancellationException`, `CompletionException`/cause, `ExecutionException`, and `InterruptedException`.
9. **Do tests measure actual worker state?** Use synchronization primitives instead of time-guessing sleeps.
10. **Does the API contract clearly state what "cancel" means?** Callers must understand cancellation rights, the extent of stopping, and irreversible actions already performed.

## 18. Summary

`CancellationException` typically signals that a future's result has been cancelled. For `CompletableFuture`, `cancel(boolean)` marks exceptional completion with `CancellationException`; the **`mayInterruptIfRunning` parameter is not used to interrupt the computation**, even when `true` is passed. This differs from `Future` instances executed via `ExecutorService.submit`, which may attempt to interrupt the task on `cancel(true)`.

A cancelled future cannot guarantee that the actual work has stopped, resources have been closed, or side effects have been rolled back. You must clearly separate **completion state**, **interrupt signals**, **task-stopping protocols**, and **state preservation**. Only when all of these are designed consistently can an application report and handle cancellation accurately.

### References

- [Java SE 17 — CompletableFuture.cancel(boolean)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html#cancel(boolean))
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CancellationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html)
- [Java SE 17 — Future.cancel(boolean)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean))
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Thread.interrupt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupt())
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)

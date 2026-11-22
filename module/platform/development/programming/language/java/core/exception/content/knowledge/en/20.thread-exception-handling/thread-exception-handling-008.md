# TimeoutException and CancellationException in Java Concurrency

## 1. Two Very Different Signals When Working with Asynchronous Tasks

When a calling thread waits for a result from a task running on another thread, there are at least two questions that must be kept separate:

- **Has the allowed waiting time expired?** This is a *timeout* issue: the wait call did not receive a result within the specified time window.
- **Has the task's result been canceled?** This is a *cancellation* issue: a task-managing object records that the result is no longer awaited via the normal completion path.

In Java, **java.util.concurrent.TimeoutException** and **java.util.concurrent.CancellationException** represent these two situations. They commonly appear when working with **Future**, **ExecutorService**, and **CompletableFuture**, but their meanings and handling are not the same.

A call to **Future.get(timeout, unit)** may throw `TimeoutException` because it waited too long. **That does not automatically stop the task.** The task may continue running, complete later, and return a result on another `get` call. Conversely, once a `Future` has transitioned to the canceled state, **Future.get()** will throw `CancellationException`; even if the worker code is still running for a while because it has not cooperated with the cancellation request, the `Future` object no longer provides a result via the normal path.

The most important principle: **timeout is a condition of the wait call; cancellation is the canceled state of the managed task/result**. A timeout may cause the application to *decide* to request cancellation, but making that request is a separate action that needs to be explicitly designed.

## 2. Exception Concepts and Classification

| Aspect | TimeoutException | CancellationException |
| --- | --- | --- |
| Package | **java.util.concurrent** | **java.util.concurrent** |
| Type | Checked exception, extends **Exception** | Unchecked exception, extends **IllegalStateException** via **RuntimeException**? No: it directly extends **IllegalStateException**, which is a **RuntimeException** |
| Meaning in Future | Result was not received within the specified wait duration | The Future has been canceled |
| Common example | **future.get(100, MILLISECONDS)** times out | **future.get()** after the Future has been canceled |
| Is the background task guaranteed to have stopped? | **No** | **Not necessarily** |
| Automatically calls **cancel**? | **No** | The canceled state usually comes from a **cancel** call or an API cancellation mechanism |
| Handling approach | Define deadlines, retry, fallback, or decide to cancel | Respect the cancellation intent; stop waiting, clean up, and report an appropriate status |

**Note on classification:** `CancellationException` **directly extends `IllegalStateException`**, and `IllegalStateException` extends `RuntimeException`. `TimeoutException` directly extends `Exception`. Because it is a checked exception, `TimeoutException` must be caught or declared if a method can throw it in its signature. `CancellationException` is unchecked, so Java does not require declaring it in **throws**.

Not every API with “timeout” in its name throws `TimeoutException`. **Thread.sleep** throws `InterruptedException` when interrupted; **Object.wait(timeout)** simply returns normally when the time expires; **CountDownLatch.await(timeout, unit)** returns **false** on timeout; **Lock.tryLock(timeout, unit)** returns **false** if the lock cannot be acquired. Always read the contract of the exact method you are calling.

## 3. State Model: Deadline, Completion, and Cancellation

A `Future` is typically viewed under these states:

- **Incomplete:** the task is waiting or running; **isDone()** is usually `false`.
- **Completed normally:** a result is available; **get()** returns the result.
- **Completed exceptionally:** **get()** throws **ExecutionException** whose cause is the task's error.
- **Canceled:** **isCancelled()** is `true`, **isDone()** is also `true`, and **get()** throws **CancellationException**.

**`isDone() == true` does not mean success.** It covers normal completion, abnormal completion, and cancellation. Nor should you infer “the worker has exited” from **isDone()** on a canceled `Future`, because the cancellation mechanism may mark the `Future` as canceled before the running thread actually terminates.

Conceptual diagram:

~~~text
Incomplete Future
    |                  |
    | get(timeout)     | cancel(...)
    | time expired     v
    |              Future canceled
    |                  |
    |                  +-- get() -> CancellationException
    |
    +-- TimeoutException for this wait attempt
    |
    +-- Task may still keep running
            |
            +-- Succeeds -> get() returns result
            |
            +-- Fails -> get() throws ExecutionException
~~~

The diagram focuses on observable outcomes from **Future**, not on every internal state of **Thread** or **FutureTask**. An expired `get` call does not transition a `Future` to canceled.

## 4. Complete, Runnable Java 17+ Example

The following program creates an **ExecutorService** with a single worker. The first scenario holds the task in a waiting state using **CountDownLatch**, triggers a timeout, and then opens the latch to retrieve the result afterward. The second scenario actively cancels the task with **cancel(true)** and checks whether the worker observes the interrupt.

Using latches to control execution order avoids relying on machine speed to determine the outcome. The 30 ms wait is only for demonstrating a timeout while the latch is still closed, not a recommended timeout for production applications.

Save to **TimeoutCancellationDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            CountDownLatch releaseFirst = new CountDownLatch(1);
            Future<String> first = executor.submit(() -> {
                releaseFirst.await();
                return "completed";
            });
            try {
                first.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("1. First get: TimeoutException");
            }
            System.out.println("2. Cancelled by timeout: " + first.isCancelled());
            releaseFirst.countDown();
            System.out.println("3. Later result: " + first.get());

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch releaseSecond = new CountDownLatch(1);
            CountDownLatch exited = new CountDownLatch(1);
            AtomicBoolean sawInterrupt = new AtomicBoolean(false);
            Future<String> second = executor.submit(() -> {
                started.countDown();
                try {
                    releaseSecond.await();
                    return "completed";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "stopped";
                } finally {
                    exited.countDown();
                }
            });

            started.await();
            try {
                second.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("4. Second get: TimeoutException");
            }
            System.out.println("5. Cancel request accepted: " + second.cancel(true));
            exited.await();
            System.out.println("6. Worker saw interrupt: " + sawInterrupt.get());
            System.out.println("7. Cancelled: " + second.isCancelled());
            System.out.println("8. Done: " + second.isDone());
            try {
                second.get();
            } catch (CancellationException e) {
                System.out.println("9. Get after cancel: CancellationException");
            }
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 TimeoutCancellationDemo.java
java TimeoutCancellationDemo
~~~

Verified stdout output from compiling and running the program:

~~~text
1. First get: TimeoutException
2. Cancelled by timeout: false
3. Later result: completed
4. Second get: TimeoutException
5. Cancel request accepted: true
6. Worker saw interrupt: true
7. Cancelled: true
8. Done: true
9. Get after cancel: CancellationException
~~~

### Explaining the first part: timeout does not cancel the task

**releaseFirst** has not been released yet. The first task calls **releaseFirst.await()**, so it cannot return yet. Therefore **first.get(30, MILLISECONDS)** throws `TimeoutException`. After catching the exception, **first.isCancelled()** is `false`: timing out *does not request cancellation*.

Calling **releaseFirst.countDown()** lets the task proceed, and **first.get()** then returns **completed**. This proves that a `Future` that previously caused a `TimeoutException` on one wait call can still deliver a normal result on a later wait call.

### Explaining the second part: cancellation request and interrupt

The second task signals **started** and then waits inside **releaseSecond.await()**. The main thread waits to ensure the task has started before calling `get` with a timeout.

After `TimeoutException`, **second.cancel(true)** requests cancellation and sends an interrupt request to the executing worker. **CountDownLatch.await()** is an interruptible wait operation; it throws **InterruptedException**. The worker records this event in **AtomicBoolean**, restores the interrupt flag, and exits the wait path. **exited.await()** ensures `main` does not print the **sawInterrupt** state before the worker has had a chance to handle the interrupt.

In this controlled demonstration, **cancel(true)** returns `true`, and both **isCancelled()** and **isDone()** are `true`. **second.get()** throws `CancellationException` instead of returning the string **stopped**: once the `Future` result is canceled, the value returned by the `Callable` after the interrupt is not returned through the normal `get` path.

**Key distinction:** The fact that the worker actually observed the interrupt is verified in the example using a dedicated flag and the **exited** latch. Looking solely at **isCancelled()** or a `true` return value from **cancel(true)** is not enough to confirm that every real-world task has stopped all side effects.

## 5. What Does Future.get(timeout) Mean Exactly?

The method:

~~~java
// Method of Future<T>, illustrating the API signature:
T get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

Asks the calling thread to wait at most the specified duration to receive the `Future` result. According to the API contract, the outcome can be:

| Outcome | Result from get(timeout, unit) |
| --- | --- |
| Task completes normally within the wait time | Returns the result |
| Task completes with an exception | Throws **ExecutionException**, with the task's exception as its cause |
| Future is already canceled | Throws **CancellationException** (unchecked) |
| Time expires before the result is ready | Throws **TimeoutException** |
| Waiting thread is interrupted | Throws **InterruptedException** |

Thus, **catch TimeoutException** is a control branch of the wait call. This branch does not tell you what percentage of work the task has processed, whether it has written external data, or whether you should retry.

### Wait-call timeout vs. business deadline

Each call to **future.get(1, SECONDS)** has its own wait duration. If the application repeats the call 10 times, it may spend well over 1 second waiting on the same task. To bound the time of an entire sequence of business steps, use a **shared deadline** and compute the remaining time before each step; do not accidentally reset the timeout on every retry.

For example, a request has a 500 ms time budget covering calling service A, retrieving the result from a `Future`, and writing the response. Using a separate 500 ms for each step can cause the total duration to far exceed the actual deadline.

### Timeout and slow execution

A timeout can be a signal to inspect performance, thread pool congestion, deadlocks, resource limits, or a slow dependency. A single `TimeoutException` does not by itself prove a business error or a permanent hang. You need to examine executor state, task progress, elapsed time, and the consequences if the task keeps running.

### Other APIs with a timeout that do not throw TimeoutException

- **CountDownLatch.await(timeout, unit)** returns a `boolean`.
- **Thread.join(millis)** may return when the time expires while the thread is still alive.
- **BlockingQueue.poll(timeout, unit)** may return `null` if no element is available within the wait limit.
- **Semaphore.tryAcquire(timeout, unit)** returns `false` when a permit cannot be acquired.
- **Future.get(timeout, unit)** uses `TimeoutException` for wait expiration per the `Future` contract.

Therefore, do not write a `catch TimeoutException` for every API that accepts a timeout parameter without checking the method signature.

## 6. Future.cancel(boolean) and Cooperative Cancellation

The `Future` interface provides:

~~~java
// Method on a Future<?>:
boolean cancel(boolean mayInterruptIfRunning);
~~~

The return value indicates whether the cancellation request successfully transitioned the `Future` to the canceled state per the implementation's contract. Typically, if the task has already completed normally or was already canceled, a subsequent `cancel` call returns `false`. There is a race between completion and cancellation; both outcomes must be handled.

The two invocation modes have different meanings:

- **cancel(false):** requests canceling the `Future` result without requesting an interrupt on the executing thread. If the task is already running, its code may continue until it finishes on its own.
- **cancel(true):** allows the execution mechanism to send an interrupt to the running thread, when supported by the implementation. This is a **cooperative signal**, not an OS command to kill the thread.

Even when **cancel(true)** returns `true`, you cannot infer that an I/O operation, database query, or internal code has definitely stopped immediately. If a worker only computes in a loop without checking for interrupts, it can keep running. Some blocking libraries have their own interruption mechanisms; other calls do not respond to interrupts or require a dedicated cancel/close API.

Illustrative code for a cancelable worker:

~~~java
// Illustrated inside a Callable<Result> or Runnable with a loop.
while (!Thread.currentThread().isInterrupted()) {
    doOneSmallUnitOfWork();
}
// Clean up per contract and exit.
~~~

When a worker uses an API that throws **InterruptedException**:

~~~java
// Illustrated inside a worker body; not a standalone program.
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Complete appropriate cleanup and exit.
    return;
}
~~~

Restoring the interrupt flag matters because methods such as **CountDownLatch.await()** typically clear the thread's interrupt status when they throw `InterruptedException`. However, in some cases an API wants to **rethrow `InterruptedException`** rather than restore the flag and return. Follow the calling layer's contract and avoid swallowing the cancellation signal and continuing as normal.

## 7. TimeoutException, CancellationException, InterruptedException, and ExecutionException

These four exception types often appear in the same business flow, yet they cannot be used interchangeably:

| Exception | What happened? | What to consider |
| --- | --- | --- |
| **TimeoutException** | Caller waited too long | Deadline, fallback, task still running, whether to cancel |
| **CancellationException** | Future was canceled | Respect cancellation; clean up, do not expect a normal result |
| **InterruptedException** | Waiting thread was requested to interrupt | Restore flag or rethrow, stop/hand off control |
| **ExecutionException** | Task itself completed with an error | Inspect **getCause()**, classify business/infrastructure error |

**InterruptedException** from **future.get(...)** concerns the *waiting thread* being interrupted. It does not mean the task worker itself was canceled. A `main` thread can be interrupted while waiting on a `Future`, while the worker keeps running. If business logic requires canceling the work when the caller is interrupted, that decision must be added to the handling policy.

**ExecutionException** is also distinct from `CancellationException`. If a `Callable` throws `IllegalArgumentException`, the `Future` is not necessarily canceled; **future.get()** typically throws `ExecutionException` with `IllegalArgumentException` as its cause. Never use `isCancelled()` to detect all failed tasks.

Do not rely on message strings to infer the error type. Catch the right exception, inspect **getCause()** when needed, and preserve stack traces and context.

## 8. Policy-Based Future Handling Pattern with Timeout

An application method can often choose to cancel a task when a deadline is exceeded. That is an **application policy**, separate from the default behavior of **get(timeout)**:

~~~java
// Illustrative code inside an existing method:
// Future<Result> future; long waitMillis;
// logger and result-handling business logic are defined elsewhere.
try {
    Result value = future.get(waitMillis, TimeUnit.MILLISECONDS);
    useResult(value);
} catch (TimeoutException e) {
    boolean accepted = future.cancel(true);
    recordTimeout(accepted, e);
} catch (CancellationException e) {
    recordCancellation(e);
} catch (ExecutionException e) {
    Throwable taskCause = e.getCause();
    recordTaskFailure(taskCause);
} catch (InterruptedException e) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    recordCallerInterrupted(e);
}
~~~

This is a **contextual** snippet, not a standalone Java class. The methods **useResult**, **recordTimeout**, **recordCancellation**, **recordTaskFailure**, and **recordCallerInterrupted** represent application-specific behavior. Do not copy this snippet assuming that calling **recordTimeout** has already handled in-flight side effects.

In real code, determine:

1. On timeout, should we always cancel, or keep the task so its result can be used later?
2. Is retrying allowed? If retrying, has the old task definitely stopped its side effects?
3. If **cancel** fails because the task just completed, should we read the final result?
4. If the caller is interrupted, should we cancel related work, hand it off to another thread, or let a long-running job continue?
5. Do we need to record a “timed out but completion unknown” state for external systems?

Also consider logging once at the error-observation boundary so duplicate logs are not multiplied across layers.

## 9. Cancellation Is a Future State, Not Proof That the Worker Has Stopped

This is a common pitfall in practice.

When a `Future` is marked canceled, **isDone()** is usually `true` and **get()** throws `CancellationException`. Yet the worker may:

- Have not started running yet and be prevented from running.
- Be blocked in an interrupt-aware API and stop once the API responds.
- Be doing a long computation without checking for interrupts.
- Be calling an external system with no effective cancellation path.
- Have already performed partial side effects before receiving the cancel request.

Therefore, **`isCancelled() == true` is not a rollback certificate**. If a task has already sent a payment request and the local `Future` is canceled, the payment provider may still have processed the request. If a task has written part of a file, `cancel` does not automatically delete the data. If a task has mutated a shared object, `cancel` does not reverse the change.

When strong state preservation is needed, structure the task to compute on temporary data, check for cancellation at appropriate boundaries, and publish the result only when it is certain that committing is still allowed. For tasks with external side effects, use transactions, idempotency, job status tracking, or a dedicated recovery mechanism.

A task can finish normally on its own when interrupted, yet the `Future` is still canceled if the `cancel` call wins the race against completion. This was demonstrated by the **"stopped"** value in the main program's `Callable`: that value is not returned via `get` after the `Future` is canceled.

## 10. Race Conditions Between Timeout, Completion, and Cancel

The following points in time do not occur within a single transaction:

~~~text
Caller                      Worker
  |                            |
  |--- get(timeout) ---------->|
  |                            | computing
  |<-- TimeoutException -------|
  |--- cancel(true) ---------->| may have just completed
  |<-- true or false ----------|
~~~

In the interval between when the caller receives `TimeoutException` and when it calls `cancel`, the worker may complete. In that case, `cancel` can no longer transition the `Future` state and returns `false`. An application branch that logs “canceled successfully” immediately upon catching `TimeoutException` has no basis for that claim.

The same task may have multiple consumers waiting on the `Future` with different timeouts. A timeout on the first consumer does not automatically cancel the task for the second consumer. If the first consumer actively cancels a shared `Future`, the remaining consumers may unexpectedly receive `CancellationException`. Therefore, cancellation authority should belong to the component that owns the task's lifecycle, not arbitrarily to any `get` call site.

If the task has side effects, retrying immediately after `TimeoutException` can cause duplicate side effects. For instance, timing out while waiting for a response from an invoice-creation job does not prove the invoice was not created. You need a request ID, idempotency key, or a job-status query mechanism before retrying.

## 11. CompletableFuture: Are Timeout and Cancellation Different from Future?

**CompletableFuture<T>** is both a **Future<T>** and a pipeline supporting the **CompletionStage** model. Several related APIs have different semantics:

| API | Primary behavior |
| --- | --- |
| **cf.get(timeout, unit)** | Waits up to the duration; may throw checked `TimeoutException`; does not auto-cancel |
| **cf.get()** | Waits and returns the result, or throws `ExecutionException`/`CancellationException` |
| **cf.join()** | Waits, does not declare checked `InterruptedException`/`ExecutionException`; abnormal completion errors are typically wrapped in `CompletionException`; direct cancellation may throw `CancellationException` |
| **cf.orTimeout(timeout, unit)** | If not completed when time expires, completes **that CompletableFuture itself** abnormally with `TimeoutException` |
| **cf.completeOnTimeout(value, timeout, unit)** | If not completed when time expires, completes **that CompletableFuture itself** normally with the fallback value |
| **cf.cancel(true/false)** | Completes the `CompletableFuture` in a canceled state; the **mayInterruptIfRunning** parameter does not control interrupting computation owned by `CompletableFuture` |

**Important difference:** **cf.get(200, MILLISECONDS)** throws `TimeoutException` directly at the wait call site when it expires. In contrast, **cf.orTimeout(200, MILLISECONDS)** arranges to *abnormally complete `cf` itself* when time expires. If **cf.get()** is called afterward, the caller typically receives **ExecutionException** whose **getCause()** is `TimeoutException`; with **join()**, the caller receives `CompletionException` with `TimeoutException` as its cause. These two paths should not be conflated into the same `catch` branch.

Contextual example:

~~~java
// Illustrating a Java 9+ method; not a complete program.
CompletableFuture<String> result = new CompletableFuture<>();
result.orTimeout(200, TimeUnit.MILLISECONDS);

// If nobody completes result before the deadline, result itself will
// be completed abnormally with TimeoutException.
~~~

With **completeOnTimeout("fallback", 200, MILLISECONDS)**, if not completed before the deadline, the `Future` can complete normally with **fallback**, so consumers will not necessarily see an exception. Design clearly whether the fallback represents real data or a degraded state.

### CompletableFuture timeout does not implicitly kill computation

The methods **orTimeout**, **completeOnTimeout**, and **cancel** determine the completion state of the `CompletableFuture`. They **do not guarantee** that a supplier running in **supplyAsync** has been interrupted, stopped processing, or ceased producing side effects. In particular, the **CompletableFuture.cancel(boolean)** documentation notes that the **mayInterruptIfRunning** parameter has no effect because interruption is not used to control processing that way.

If you need to cancel the actual computation, manage the underlying task separately (for example, a `Future` returned from `ExecutorService`), a cancellation token, or the dependency's own API. Do not assume that calling **CompletableFuture.cancel(true)** is equivalent to calling **FutureTask.cancel(true)** on a running worker.

### Abnormal handling branches in a pipeline

**exceptionally**, **handle**, and **whenComplete** can be used to observe or transform abnormal results. However:

- **exceptionally** can supply a fallback and turn the downstream pipeline into normal completion.
- **handle** receives both the result and the `Throwable`, and can transform them into another value or error.
- **whenComplete** is suitable for observation/side effects, though errors thrown by the callback itself must also be considered.
- A dependent stage may represent an earlier stage's error using **CompletionException**, so inspect the cause chain rather than assuming every stage throws the exact original exception type.

If downstream handles both timeout and cancellation, distinguish `TimeoutException` used for abnormal completion, `CancellationException` from a canceled `Future`, and other business exceptions.

## 12. Relationship with ExecutorService and Shutdown

**ExecutorService.submit(...)** typically returns a `Future` to observe results and request cancellation. **ExecutorService.shutdown()** stops accepting new tasks but **does not automatically cancel all running tasks**. **shutdownNow()** attempts to stop running tasks via interrupt and returns the list of tasks that had not started, but it does not guarantee that every running task will stop immediately.

**Future.cancel(true)** targets a specific `Future`; **shutdownNow()** is an executor-wide stop request. The two operations have different scopes, and both require workers to cooperate with interruption.

In an application with a long-lived executor, do not shut down the shared executor just because a single client request timed out. If you create a dedicated executor for a business unit of work, define a policy for closing it, awaiting termination, and managing threads to avoid resource leaks. If tasks do not cooperate with interrupts, **awaitTermination** can also expire while some workers remain alive.

Some higher-level APIs have their own timeout/cancellation mechanics, such as **ExecutorService.invokeAll(tasks, timeout, unit)**, which may cancel incomplete tasks when time expires according to its contract. Do not transfer that API's rules to **Future.get(timeout)**; read the JavaDoc for each method.

## 13. Designing Deadlines and Cancellation for Business APIs

A clean design should separate three decisions:

**Caller wait time:** How long can the caller tolerate waiting? This is the timeout or deadline. An HTTP caller might stop waiting while a background job still needs to run to finish processing.

**Authority to cancel the result/task:** Who is allowed to cancel and when? If multiple clients wait on a shared cached `Future`, one client timing out should not implicitly cancel work that other clients still need.

**Ability to stop side effects:** Where can the worker respond to interruption, and what rollback or compensation is needed? A network call that times out does not confirm that the server has not committed.

Business outcomes can be defined as clearly distinguishable states:

- **SUCCEEDED:** data is present and the result is confirmed.
- **FAILED:** the task completed with a genuine error; preserve the cause.
- **TIMED_OUT_WAITING:** the caller's wait expired; the final outcome may be unknown.
- **CANCEL_REQUESTED:** a cancel request was issued, though actual stopping may still be in progress.
- **CANCELED:** the `Future` is in the canceled state; business logic must still account for side effects.
- **UNKNOWN_REMOTE_OUTCOME:** the remote side may have processed the request, but the response did not arrive before the deadline.

These state names are only application design suggestions, **not** standard built-in JDK enums.

### When should you retry?

Retrying is only safe when you understand the nature of the operation:

- Pure in-memory computation with no side effects can spawn a new task if timed out per policy.
- Data reads can be retried with reasonable timeouts/backoff, while avoiding overloading a slow dependency.
- Creating orders, charging money, or emitting events requires idempotency/deduplication if a retry could produce duplicate outcomes.
- A task canceled locally whose external service has not confirmed stopping needs a status query before relaunching, if the API supports it.

Do not use a single catch block that treats `TimeoutException`, `CancellationException`, `InterruptedException`, and `ExecutionException` as “transient network errors” and retries them all indiscriminately.

## 14. How to Test Timeout and Cancellation Reliably

Testing with **Thread.sleep(100)** and hoping results arrive in the right order is often flaky on slow CI machines or when the scheduler changes. For deterministic tests, use **CountDownLatch**, **CyclicBarrier**, or suitable synchronization primitives to actively control when a task can complete.

Scenarios to verify:

| Scenario | Key check |
| --- | --- |
| Incomplete Future, `get` with short deadline | `TimeoutException`; Future is not automatically canceled |
| After timeout, allow task to complete | Subsequent `get` returns the expected result |
| Cancel before task starts | Future becomes canceled if cancel wins the race |
| `cancel(true)` while worker is awaiting | Interrupt is observed if API supports it; `Future.get` throws `CancellationException` |
| `cancel(false)` while worker is running | Do not assume the worker is interrupted |
| Task throws an exception | `get` throws `ExecutionException` and cause preserves the original error |
| Caller thread interrupted during `get` | Catch `InterruptedException`; apply interrupt policy |
| Canceled Future | Both `isDone` and `isCancelled` are `true`; `get` throws `CancellationException` |
| `CompletableFuture.orTimeout` expires | The CF itself completes abnormally; `get`/`join` have the appropriate wrapper type |
| Two callers waiting on the same task | One caller's timeout does not implicitly destroy the shared result |

In the main example, the first latch proves a task can complete after a `TimeoutException`. The **started** latch ensures the second worker is running before `main` calls `cancel`. The **exited** latch ensures `main` waits until the worker has actually finished `finally`, rather than confusing the canceled `Future` state with the worker having stopped.

There is no need to force races using random timing; if you want to test the race between completion and cancellation, control the schedule with barriers and verify the contractually allowed outcomes rather than hard-coding an unguaranteed scheduler order.

## 15. Common Pitfalls

**Misunderstanding “timeout means the task stopped.”** `Future.get(timeout)` only bounds the wait time. If you do not cancel or the task has not finished on its own, the worker may still be running.

**Calling `cancel(true)` and assuming side effects rolled back.** Interrupt is a cooperative signal; results in external systems may already be committed. You need a dedicated data/transaction policy.

**Using `isDone()` as a success flag.** `isDone` is also `true` for cancellation and errors. Call `get` or manage full result states.

**Confusing `CancellationException` with `InterruptedException`.** `CancellationException` reports the canceled state of a `Future`; `InterruptedException` reports that a waiting thread or worker was interrupted in an interrupt-supporting API.

**Swallowing `InterruptedException`.** When not rethrowing, you usually need to restore the interrupt flag and either exit or hand off the cancellation policy to an upper layer.

**Catching `TimeoutException` and immediately retrying a write.** The old task may still be running or the external request may have completed. Non-idempotent retries can duplicate side effects.

**Assuming `CompletableFuture.cancel(true)` forces the supplier to stop.** `CompletableFuture` does not use this parameter to interrupt processing the way `FutureTask` typically does. Manage the underlying computation separately.

**Setting `orTimeout` and expecting `get()` to throw `TimeoutException` directly.** When a CF completes abnormally with `TimeoutException`, `get` usually wraps it in `ExecutionException`; `join` usually wraps it in `CompletionException`. This is a different path from `get(timeout)` timing out.

**Creating multiple independent deadlines for the same request.** Resetting the timeout after each wait/retry can push total time over budget.

**Shutting down a shared executor when one task is slow.** Manage executor lifecycle according to ownership; cancel the specific task if needed and close the executor at the appropriate boundary.

## 16. Checklist Before Handling Timeout/Cancellation

1. Which API is being called: `Future.get(timeout)`, `CompletableFuture.orTimeout`, or an API that returns a `boolean` on expiration?
2. Does a timeout only stop waiting, or does it also actively transition the result state?
3. If a timeout occurs, does the task continuing to run cause business or resource issues?
4. Who owns the `Future` and has authority to cancel when multiple callers share it?
5. If `cancel(true)` is used, does the worker check for interrupts or call an interruptible API?
6. If `cancel` returns `false` because the task just completed, do we need to retrieve and handle the final result?
7. Are **CancellationException**, **InterruptedException**, and **ExecutionException.getCause()** handled distinctly?
8. Is the deadline calculated for the entire business chain, including retries and cleanup?
9. If I/O or side effects have occurred, how do we determine the outcome and avoid duplicate retries?
10. Do tests verify that timeout does not auto-cancel, cancel does not mean the worker stopped, and error paths are observed accurately?

**Remember:** **TimeoutException** in **Future.get(timeout)** states that *the wait attempt timed out*; it does not cancel the task. **CancellationException** indicates that *the Future was canceled*, but the `Future` state alone does not prove all computation and side effects have stopped. Proper handling combines clear deadlines, appropriate cancellation authority, worker responsiveness to interrupts, distinct handling of exception types, and state-safety mechanisms when operations have side effects.

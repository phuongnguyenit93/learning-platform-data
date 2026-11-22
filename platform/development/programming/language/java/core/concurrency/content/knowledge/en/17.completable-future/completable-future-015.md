# Cancellation, Interruption, and Limitations of CompletableFuture

`CompletableFuture<T>` helps build asynchronous processing pipelines using `supplyAsync()`, `thenApply()`, `thenCompose()`, `thenCombine()`, `exceptionally()`, and many other combinators. However, **completing a Future**, **cancelling a Future**, **interrupting a thread**, and **actually stopping the work** are four different things.

The most important takeaway of this lesson:

> **`CompletableFuture.cancel(true)` is not a command that forcefully interrupts the computing thread.** In the JDK's `CompletableFuture` implementation, the `mayInterruptIfRunning` parameter is not used to control processing. Cancelling transitions the `CompletableFuture` to an exceptional completion state due to cancellation, but the background computation may continue running, holding resources, and producing side effects.

This is **general Java concurrency** knowledge (JDK 17+), not based on Spring or any other framework. We will distinguish each API's contract using standalone Java programs with `javac`/`java` commands and verifiable stdout.

## 1. Four Concepts That Must Be Separated

| Concept | Who/what is affected? | Does it guarantee the task stops? |
|---|---|---|
| `CompletableFuture.cancel(...)` | The **completion state** of the `CompletableFuture` and related dependent stages. | **No.** Does not guarantee interrupting the underlying computation. |
| `Thread.interrupt()` | The interrupt flag of a **thread**; some blocking operations respond with `InterruptedException`. | **Not guaranteed.** Code must cooperate or use interrupt-aware APIs. |
| `Future.get(timeout)` | Limits **how long the caller waits for a result** in a single call. | **No.** Expiration does not automatically cancel the task. |
| `CompletableFuture.orTimeout(...)` | Can **complete the `CompletableFuture` itself with a timeout error** if it is still incomplete. | **No.** The underlying computation may continue. |
| `completeOnTimeout(value,...)` | Can complete the `CompletableFuture` itself with a **fallback value**. | **No.** Does not interrupt the background task. |
| Cooperative stop flag / I/O timeout | The **work-executing logic** itself checks the stop condition. | Can make the task exit according to protocol, but still requires checkpoints, cleanup, and termination observation. |

A pipeline might look like this:

```text
Caller thread                 CompletableFuture              Worker
--------------                -----------------              -------------
supplyAsync(task) ----------> [incomplete] ----------------> task starts
      |
      +--- cancel(true) -----> [CANCELLED]                     may still run
      |                                                            |
      +--- join() -----------> CancellationException                |
                                                                   v
                                                            side effect / cleanup
                                                            (not necessarily done)
```

**Do not equate `isDone() == true` with `worker has stopped` or `all resources have been released`.** `isDone` reflects the terminal state of the Future, not waiting for all threads/side effects.

## 2. CompletableFuture Is a Future, but Cancellation Has Its Own Semantics

`CompletableFuture<T>` implements `Future<T>` and `CompletionStage<T>`. It has `Future`'s `get()`, `get(timeout)`, `cancel()`, and `isDone()`, along with composition methods and manual completion methods.

Common states:

```text
                           [incomplete]
                            /    |     \
                           /     |      \
                   complete(T)  completeExceptionally(e)  cancel(...)
                         |          |            |
                         v          v            v
                      success   exceptional   canceled
                         \          |            /
                          \         |           /
                                isDone = true
```

For a standard `CompletableFuture`:

- `complete(value)` attempts to complete normally and returns `true` if **that attempt wins**.
- `completeExceptionally(error)` attempts to complete exceptionally; also returns a boolean indicating whether that completion won.
- `cancel(mayInterruptIfRunning)` attempts to complete exceptionally with `CancellationException`; the `mayInterruptIfRunning` parameter **has no effect on controlling interruption** for `CompletableFuture`.
- `isCancelled()` is `true` if the Future completed via cancellation.
- `isCompletedExceptionally()` is `true` for any exceptional completion, including cancellation.
- `isDone()` is `true` if completed normally, failed, or cancelled.

**A terminal state is not a "kill worker" button.** It is possible for the Future to be cancelled while the lambda running in `supplyAsync` has not yet exited the method. If the lambda later computes a value and tries to complete the same `CompletableFuture`, the new result generally cannot overwrite the already cancelled state.

### cancel(true) and cancel(false) on CompletableFuture

In the `Future` interface, `mayInterruptIfRunning` expresses the intent to interrupt when cancelling a running task. However, each implementation has its own contract. For `CompletableFuture`, the Java API explicitly states that this parameter **has no effect** because interrupts are not used to control its processing.

Therefore:

```java
CompletableFuture<String> cf = new CompletableFuture<>();
cf.cancel(true);   // Does not guarantee interrupting the worker.
```

This is a snippet; there is no actual worker here, because `new CompletableFuture<>()` simply creates an **incomplete promise**. Calling `cancel` transitions the promise's state if it is not yet completed. You must distinguish this promise from a computation created with `supplyAsync`.

## 3. Example 1 — cancel(true) Does Not Automatically Interrupt a CompletableFuture's Supplier

We hold a supplier waiting on a `CountDownLatch` and use additional flags to record whether it actually passes through the processing/cleanup section. The main thread cancels the `CompletableFuture` while the supplier is still waiting on the latch; if cancellation automatically interrupted the worker, `await()` would receive an interrupt. However, `CompletableFuture` does not use the `true` argument to interrupt the underlying worker.

Create **`CompletableCancellationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean workFinished = new AtomicBoolean();

        CompletableFuture<String> future =
                CompletableFuture.supplyAsync(() -> {
                    started.countDown();
                    try {
                        release.await();
                        workFinished.set(true);
                        return "actual-result";
                    } catch (InterruptedException e) {
                        interrupted.set(true);
                        Thread.currentThread().interrupt();
                        return "interrupted-result";
                    }
                }, executor);

        try {
            started.await();

            boolean cancellationAccepted = future.cancel(true);
            System.out.println("Cancel accepted: "
                    + cancellationAccepted);
            System.out.println("Future cancelled: "
                    + future.isCancelled());
            System.out.println("Work finished before release: "
                    + workFinished.get());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated =
                executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Worker interrupted: " + interrupted.get());
        System.out.println("Underlying work finished: "
                + workFinished.get());
    }
}
```

```bash
javac CompletableCancellationDemo.java
java CompletableCancellationDemo
```

Output when there is no external interruption and the worker is scheduled normally:

```text
Cancel accepted: true
Future cancelled: true
Work finished before release: false
Executor terminated: true
Worker interrupted: false
Underlying work finished: true
```

**Explanation:**

1. `started.await()` confirms the supplier has started, but the supplier **cannot exit `release.await()`** while the latch remains closed.
2. `future.cancel(true)` wins completion, causing the Future to report cancelled. It does not send an interrupt to the worker just because the argument is `true`.
3. The `workFinished` flag remains `false` before the latch is released. This is proof that the background task **has not finished**, even though the Future is cancelled.
4. When `main` opens the latch, the worker executes the rest and sets `workFinished=true`. Because it was not interrupted by `cancel`, the `interrupted` flag is `false`.
5. `awaitTermination()` is used to verify that the dedicated executor has stopped; **do not** infer cleanup solely from `future.isCancelled()`.

This example uses `CountDownLatch` to control timing milestones, **not `sleep()` to guess scheduling**. It demonstrates the contract of `CompletableFuture` on JDK 17 and does not imply that all other `Future` implementations share the same cancellation behavior.

## 4. Comparison with FutureTask / ExecutorService.submit(): cancel(true) Can Interrupt

A `Future` returned by `ExecutorService.submit(Callable)` on a standard `ThreadPoolExecutor` may be backed by `FutureTask`. With `FutureTask`, `cancel(true)` can attempt to **interrupt the executing thread** if the task has already started. This is still a **cooperative request**: a task that ignores the interrupt flag or performs unresponsive blocking can continue running.

### Example 2 — FutureTask Returned from submit() Receives Interrupt

Create **`FutureTaskInterruptDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureTaskInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean cleaned = new AtomicBoolean();

        Future<String> future = executor.submit(() -> {
            started.countDown();
            try {
                neverReleased.await();
                return "not-reached";
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                return "interrupted";
            } finally {
                cleaned.set(true);
            }
        });

        try {
            started.await();
            System.out.println("Cancel accepted: "
                    + future.cancel(true));
            System.out.println("Future cancelled: "
                    + future.isCancelled());
        } finally {
            executor.shutdown();
        }

        boolean terminated =
                executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Worker saw interrupt: "
                + interrupted.get());
        System.out.println("Cleanup finished: " + cleaned.get());
    }
}
```

```bash
javac FutureTaskInterruptDemo.java
java FutureTaskInterruptDemo
```

Output with a standard executor and no external interference:

```text
Cancel accepted: true
Future cancelled: true
Executor terminated: true
Worker saw interrupt: true
Cleanup finished: true
```

`started.await()` ensures the callable is running and waiting on a latch that is never released. `cancel(true)` on the `FutureTask` created by `submit` attempts to interrupt the worker; `CountDownLatch.await()` responds with `InterruptedException`, and the worker then runs through `finally`. Only when `awaitTermination()` returns `true` can it be used as a milestone confirming the worker has stopped.

Comparing the two examples:

| Same `cancel(true)` call | `CompletableFuture.supplyAsync(...)` | `Future` from `ExecutorService.submit(...)` |
|---|---|---|
| Transitions Future state to cancelled | Possible. | Possible. |
| `true` argument causes implementation to try interrupting worker | **No**, in JDK `CompletableFuture`. | **Possible**, if implementation uses `FutureTask` and the task is running. |
| Guarantees running code has stopped before `cancel` returns | **No.** | **No.** |
| Guarantees `finally` has completed when `isCancelled=true` | No. | No. |
| Requires separate timeout/cleanup/resource ownership | Yes. | Yes. |

Do not compare by simply calling `isDone()` right after `cancel`; both Futures can report a terminal state before the worker finishes `finally`.

## 5. What Do get()/join() Return When a Future Is Cancelled?

For **the `CompletableFuture` itself that was cancelled**:

- `future.get()` and `future.join()` can throw **`CancellationException`**.
- `isCancelled()` is `true`.
- `isCompletedExceptionally()` is also `true`.
- Normal `complete(value)` cannot overwrite the cancelled terminal state.

For a **dependent stage**, the outcome differs slightly: if the source is cancelled, a dependent stage that relies on the source's success can complete exceptionally with a **`CompletionException` wrapping `CancellationException`**. In that case, the dependent typically has `isCompletedExceptionally() == true`, but **not necessarily `isCancelled() == true`** because it was completed with a wrapped exception rather than cancelled directly.

### Example 3 — Cancellation Propagates to Dependents, Does Not Stop Upstream/Downstream

Create **`CancellationPropagationDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CancellationPropagationDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        CompletableFuture<Integer> dependent =
                source.thenApply(value -> value + 1);
        CompletableFuture<Integer> fallback =
                dependent.exceptionally(error -> -1);

        source.cancel(true);

        System.out.println("Source cancelled: "
                + source.isCancelled());
        System.out.println("Dependent exceptional: "
                + dependent.isCompletedExceptionally());

        try {
            dependent.join();
        } catch (CompletionException e) {
            System.out.println("Dependent cause is cancellation: "
                    + (e.getCause() instanceof CancellationException));
        }
        System.out.println("Recovered result: " + fallback.join());

        CompletableFuture<Integer> upstream = new CompletableFuture<>();
        CompletableFuture<Integer> child =
                upstream.thenApply(value -> value * 2);

        child.cancel(true);
        upstream.complete(7);

        System.out.println("Upstream result: " + upstream.join());
        System.out.println("Child cancelled: " + child.isCancelled());
    }
}
```

```bash
javac CancellationPropagationDemo.java
java CancellationPropagationDemo
```

Output:

```text
Source cancelled: true
Dependent exceptional: true
Dependent cause is cancellation: true
Recovered result: -1
Upstream result: 7
Child cancelled: true
```

**Analysis:**

- In the first branch, `source.cancel(true)` completes `source` as a cancellation. `thenApply` has no success value to run on, so `dependent` completes exceptionally. `dependent`'s `exceptionally` stage can recover to `-1`.
- When calling `dependent.join()`, `dependent`'s exception is observed via a `CompletionException` whose cause is `CancellationException`. This is **outcome propagation**, not a request to stop the CPU of an already-running callback.
- In the second branch, `child.cancel(true)` **does not cancel upstream** (`upstream`). We can still call `upstream.complete(7)` and retrieve `7`. The cancelled `child` does not need to complete the multiplication for its own result.

**There is no automatic rule that "cancelling one stage cancels the entire pipeline"**. The designer must determine which stages belong to the same operation, which stages are shared among multiple consumers, and who has the authority to request stopping actual work.

## 6. get(timeout) Does Not Cancel the Future; orTimeout/completeOnTimeout Are Future Completions

Three APIs are often grouped together as "timeout" but have different contracts:

| API | Does the caller block? | Does the `CompletableFuture` state change? | Does the underlying task stop automatically? |
|---|---|---|---|
| `future.get(50, MILLISECONDS)` | May block, up to roughly 50 ms. | **No**, merely because the wait expired. | No. |
| `future.orTimeout(50, MILLISECONDS)` | Does not block at timeout registration. | If still incomplete at deadline, **completes exceptionally with `TimeoutException`**. | Not guaranteed. |
| `future.completeOnTimeout("fallback", 50, MILLISECONDS)` | Does not block at timeout registration. | If still incomplete at deadline, **completes normally with fallback**. | Not guaranteed. |

`orTimeout` and `completeOnTimeout` on a standard `CompletableFuture` **return the same Future instance**, not an independent copy. If the Future is shared by multiple callers, adding a timeout from one caller can affect the outcome seen by the other callers.

**`TimeoutException` from `get(timeout)`** is a failure of **that wait**. **`TimeoutException` used by `orTimeout` to complete the Future** is an error state of **the Future itself**; with `join()`, callers typically see a `CompletionException` with the corresponding cause.

### Example 4 — Three Timeout Types and Different States

Create **`CompletableTimeoutDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableTimeoutDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> waiting = new CompletableFuture<>();

        try {
            waiting.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            System.out.println("get timed out");
        }

        System.out.println("Still incomplete: " + !waiting.isDone());
        waiting.complete("late-success");
        System.out.println("Later result: " + waiting.join());

        CompletableFuture<String> timedOut = new CompletableFuture<>();
        timedOut.orTimeout(20, TimeUnit.MILLISECONDS);

        try {
            timedOut.join();
        } catch (CompletionException e) {
            System.out.println("orTimeout cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> fallback = new CompletableFuture<>();
        fallback.completeOnTimeout(
                "fallback", 20, TimeUnit.MILLISECONDS);
        System.out.println("Fallback result: " + fallback.join());
    }
}
```

```bash
javac CompletableTimeoutDemo.java
java CompletableTimeoutDemo
```

Output:

```text
get timed out
Still incomplete: true
Later result: late-success
orTimeout cause: TimeoutException
Fallback result: fallback
```

There is no computing worker in this example; the Futures are manually created in an incomplete state. Therefore, the first `get(20, ...)` and the subsequent timeout completion mechanisms do not race with results from another task.

In a program with a real `supplyAsync`, **a timeout on `CompletableFuture` does not stop the running task**. That task may finish after the Future has already been marked timed out; the later completion cannot overwrite the terminal state via normal completion.

## 7. Example 5 — orTimeout Returns, Yet the Supplier Still Has Not Stopped

To prove the statement above, we run a supplier waiting on a latch. `main` registers `orTimeout`, waits for the stage to finish exceptionally, checks that the task has not finished, and only then releases the latch so the worker can proceed.

Create **`TimeoutDoesNotStopWorker.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutDoesNotStopWorker {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean workerFinished = new AtomicBoolean();

        CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> {
                    started.countDown();
                    try {
                        release.await();
                        workerFinished.set(true);
                        return "real-result";
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return "interrupted";
                    }
                }, executor);

        try {
            started.await();
            result.orTimeout(20, TimeUnit.MILLISECONDS);
            try {
                result.join();
            } catch (CompletionException e) {
                System.out.println("Timed out: "
                        + (e.getCause() instanceof TimeoutException));
            }
            System.out.println("Worker finished before release: "
                    + workerFinished.get());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Worker finished after release: "
                + workerFinished.get());
    }
}
```

```bash
javac TimeoutDoesNotStopWorker.java
java TimeoutDoesNotStopWorker
```

Output when the worker is not externally interrupted:

```text
Timed out: true
Worker finished before release: false
Executor terminated: true
Worker finished after release: true
```

`started.await()` guarantees the supplier has entered `release.await()`. While the latch is closed, the supplier cannot return `real-result`. Thus `orTimeout(20,...)` makes the Future exceptional, `join()` reports `CompletionException` wrapping `TimeoutException`, yet **the worker has not passed through its work**. `main` releases the latch and waits for termination; only then does the worker actually exit the lambda.

In a real system, a task may be handling database/network I/O and cannot simply "open a latch" to stop. You need I/O-level timeouts, a cancellation protocol, and cleanup inside the task.

## 8. InterruptedException: Interrupting a Waiting Caller Does Not Mean the Future Is Cancelled

`CompletableFuture.get()` and `get(timeout)` are interruptible waits. If **the waiting thread** is interrupted, the method can throw `InterruptedException`. It **does not automatically complete the Future as cancelled** and does not send an interrupt to the thread executing the supplier.

For `join()`, its contract does not declare `InterruptedException`; it is a wait that **does not respond to interrupts with a checked exception like `get`**. If the caller needs to preserve the ability to cancel/stop waiting, you must choose the right API and manage interrupts deliberately.

### Example 6 — Interrupting the Waiting Thread Leaves the Future Usable

Create **`InterruptedWaiterDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedWaiterDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> future = new CompletableFuture<>();
        CountDownLatch waiterReady = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        Thread waiter = new Thread(() -> {
            waiterReady.countDown();
            try {
                future.get();
            } catch (InterruptedException e) {
                sawInterrupt.set(true);
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        }, "waiter");

        waiter.start();
        waiterReady.await();

        waiter.interrupt();
        waiter.join();

        System.out.println("Waiter interrupted: "
                + sawInterrupt.get());
        System.out.println("Future cancelled: "
                + future.isCancelled());

        future.complete("still-usable");
        System.out.println("Future value: " + future.join());
    }
}
```

```bash
javac InterruptedWaiterDemo.java
java InterruptedWaiterDemo
```

Output:

```text
Waiter interrupted: true
Future cancelled: false
Future value: still-usable
```

`main` calls `future.complete("still-usable")` **only after `waiter.join()`**, so the waiter's `future.get()` cannot succeed from that completion. The waiter is interrupted and exits via the `InterruptedException` branch; the Future remains incomplete and uncancelled. Afterwards, `main` can complete it normally.

An `InterruptedException` typically clears the interrupt flag when thrown; if the calling layer **catches it without rethrowing**, consider calling `Thread.currentThread().interrupt()` to preserve the status. If the method is allowed to propagate `InterruptedException`, it is usually better to rethrow it rather than swallow the signal.

**Do not handle it with a `while(true) { try { get(); } catch(InterruptedException ignored) {} }` loop**: that ignores the stop request and can lead to infinite waiting.

## 9. Cancellation Can Propagate Outcomes, but There Is No Automatic Structured Cancellation

Given a pipeline:

```java
CompletableFuture<User> source = loadUserAsync();

CompletableFuture<String> label = source
        .thenApply(user -> user.name())
        .thenApply(String::toUpperCase);
```

This is a snippet assuming `User` and `loadUserAsync` are defined.

If `source` is completed exceptionally, stages that require a successful result generally **do not invoke their success callbacks** and instead complete exceptionally according to the dependency. However:

- Cancelling **the source stage** does not automatically cancel an in-flight HTTP/database request if the task itself has no cancel hook.
- Cancelling **the final stage** does not automatically cancel all upstream stages, especially if upstream is still used by other consumers.
- A dependent callback that has already started running can continue producing side effects even if its dependent stage is later cancelled via another path.
- Cancelling one branch does not mean `allOf`/`anyOf` will stop all siblings.
- A `CancellationException` state in a Future does not mean a transaction outside the JVM has rolled back.

If you need "cancel a request and all child work stops and cleans up", you must build a protocol of **ownership + cancellation token + I/O timeout + resource cleanup + completion acknowledgement**. A plain `CompletableFuture` does not automatically establish a *structured concurrency scope* for all stages it touches.

### Shared Tasks: Who Should Cancel Whom?

For example, two callers share a `sharedLoad` stage and create two separate dependents. If caller A cancels `sharedLoad`, caller B may also suffer an exceptional outcome. If A only cancels its own dependent stage, B's shared use of the source generally does not need to be stopped.

Therefore, distinguish:

1. **Source owned by one request:** may have authority to stop all work for that request.
2. **Shared cached/deduplicated source:** a single consumer should not unilaterally cancel a source that other consumers still need.
3. **Dependent view:** each consumer can create its own result stage to handle errors/timeouts without mutating the shared source under the chosen contract.

Do not just change the static type from `CompletableFuture` to `CompletionStage` and assume callers can never access the concrete object. If you need to separate completion/cancellation authority, consider `minimalCompletionStage()`, `copy()`, or an appropriate wrapper/API protecting the source, with a clear understanding of `toCompletableFuture()` and ownership.

## 10. Cooperative Cancellation: Truly Stopping via a Signal the Worker Reads

To **stop work**, code must have checkpoints. A simple pattern:

- An `AtomicBoolean stopRequested` owned by the operation owner.
- The worker checks `stopRequested.get()` before expensive steps and periodically inside loops.
- If the task has a blocking wait, the owner must have a way to **wake up** the task or use a timeout/specific cancel mechanism.
- The worker exits along a defined branch and cleans up in `finally`.
- The owner waits for a milestone confirming **the worker has finished** if resources need to be closed safely.

**Do not just set a flag and assume the worker will see it immediately if it is blocked on unbounded I/O.** You need API timeouts, interruption via a properly owned `FutureTask`, closing a socket per contract, or a wake-up signal.

### Example 7 — Cooperative Stop, Future Still Returns a Meaningful Result

Create **`CooperativeStopDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean stopRequested = new AtomicBoolean();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);
        AtomicBoolean cleaned = new AtomicBoolean();

        CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        started.countDown();
                        proceed.await();
                        if (stopRequested.get()) {
                            return "stopped-cooperatively";
                        }
                        return "finished-work";
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return "interrupted";
                    } finally {
                        cleaned.set(true);
                    }
                }, executor);

        try {
            started.await();
            stopRequested.set(true);
            proceed.countDown();

            System.out.println("Worker result: "
                    + result.get(5, TimeUnit.SECONDS));
        } finally {
            proceed.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Cleanup finished: " + cleaned.get());
    }
}
```

```bash
javac CooperativeStopDemo.java
java CooperativeStopDemo
```

Output under normal execution conditions:

```text
Worker result: stopped-cooperatively
Executor terminated: true
Cleanup finished: true
```

`main` sets the stop flag **before** opening the latch. The worker only proceeds to check the flag after the latch opens, so it sees the stop request and returns the `stopped-cooperatively` status. `CompletableFuture` completes **normally** with a meaningful outcome; there is no need to cancel the promise itself to exit the lambda.

This is a valid design when business logic needs to distinguish **controlled stop** from **cancelled Future**. In practice, you can use an `enum ResultStatus` or a sealed result type instead of strings. The key part is having a **real signal for the worker to cooperate with**, rather than relying on `CompletableFuture.cancel(true)`.

## 11. How to Both Cancel the Future and Stop the Worker?

If you must expose cancellation to the caller while still needing to stop the worker, you can separate two handles:

- **Result handle**: `CompletableFuture<Result>` for composition and observation.
- **Control handle**: `Future<?> submittedTask` from an executor or a `CancellationToken` capable of sending a stop signal.
- **Resource owner**: closes/terminates sockets, streams, requests, or child tasks according to the actual protocol.

Architectural example (snippet):

```java
AtomicBoolean stop = new AtomicBoolean();
CompletableFuture<String> result = new CompletableFuture<>();

Future<?> running = executor.submit(() -> {
    try {
        while (!stop.get()) {
            doOneSmallStep();
        }
        result.complete("stopped");
    } catch (Throwable failure) {
        result.completeExceptionally(failure);
    } finally {
        cleanupResources();
    }
});

// When the owner requests a stop:
stop.set(true);
running.cancel(true); // May interrupt per the FutureTask contract.
result.cancel(false); // Only if you want to publish the cancelled state.
```

This is an **outline** requiring definitions for `doOneSmallStep`, `cleanupResources`, and imports; it is not a standalone program. One point to note: if you cancel `result` immediately, the caller **can no longer use `result` to wait for cleanup**. You need an additional `done/terminated` signal or to wait for the executor/resource owner to shut down to verify completion.

With `FutureTask.cancel(true)`, even when an interrupt is sent, the task may ignore it. Combine a cooperative stop signal with internal API timeouts, and never call `Thread.stop()`.

**Another design pitfall:** if the owner cancels `running` **before the task starts**, the runnable may never run; the `finally` block **inside the runnable** will not run either. If resources were allocated outside the runnable, the owner must clean them up via a separate path. Do not rely solely on the `finally` block of a task that may never have started.

## 12. Resource Cleanup, try-with-resources, and Side Effects

Cancellation is especially tricky when a task owns data outside the JVM:

```text
Caller timeout/cancel
         |
         v
CompletableFuture completed exceptionally
         |
         +-- worker may still be using HTTP/DB connection
         +-- callback may still be writing to a file
         +-- external transaction may already be committed
         +-- other dependent tasks may still be running
```

Principles:

1. Place **`try/finally` or `try-with-resources` inside the worker** around the resources it opens and owns.
2. Use **timeouts at the I/O layer** (connect/read/request), not just timeouts on `get()`.
3. If you want to abort I/O, use the specific library's resource cancellation/closing API according to its contract.
4. Do not close resources from the caller as soon as `future.isDone()` is true if the worker may still be using them; require ownership and completion acknowledgement.
5. If retrying after a timeout, use an **idempotency key** or protocol to prevent duplicate side effects; a Future does not roll back transactions.
6. If cleanup can fail, provide a separate path to observe exceptions/metrics; Future cancellation can prevent cleanup errors from appearing in its `get()` call.
7. Manage the executor and dependent callbacks so you do not shut down too early while required async steps have not yet run.

No single flag or single `cancel()` call can guarantee that "all resources, across all threads and external systems, have returned to their initial state."

## 13. Executor Lifecycle and the Difference Between shutdown() / shutdownNow()

For a dedicated executor created by the application:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);

try {
    // Submit work; keep handles, timeouts, and cancellation contract.
} finally {
    executor.shutdown();
}
```

This is a snippet. `shutdown()` stops accepting new tasks, but **allows already-submitted tasks to finish**. It does not automatically cancel a `CompletableFuture` waiting on dependencies.

`shutdownNow()` attempts to send interrupts to workers and returns a list of tasks that have not started per the executor's contract, but **does not guarantee running tasks stop immediately**. For callbacks or `thenApplyAsync(..., executor)` stages not yet submitted, shutting down the executor too early can cause them to be **rejected** and dependent stages to complete exceptionally instead of running normally.

`awaitTermination(timeout, unit)` gives the owner a bounded wait. Returning `false` means the pool has not terminated within that time; do not log "cleanup complete" just because you called the method. In shutdown code, if the caller is interrupted, it is usually right to preserve the interrupt signal and follow an appropriate stop policy.

**Common pool:** `CompletableFuture.supplyAsync(...)` without specifying an executor typically uses `ForkJoinPool.commonPool()` per JDK policy, so do not try to shut down the common pool as if it were a per-request resource. If you need clear cancellation/resource isolation/metrics, pass an executor owned by your component.

## 14. Concurrent Completion Races: Success, Error, Timeout, Cancel

A `CompletableFuture` can have multiple competing paths to completion:

```text
                        Incomplete CompletableFuture
                                   |
                 +-----------------+------------------+
                 |                 |                  |
          worker complete(T)  orTimeout(...)      caller cancel(...)
                 |                 |                  |
                 +-----------------+------------------+
                                   |
                       One terminal completion wins
```

In normal cases, only one of `complete`, `completeExceptionally`, or `cancel` wins while the Future is incomplete. Subsequent completion calls return `false` or do not change the outcome. The scheduler may decide **which path wins** if a result arrives right around the deadline.

Therefore, do not write tests like:

```java
Thread.sleep(50);
assert future.isCancelled();
```

and assume it is deterministic; OS and JVM scheduling can make it fail. Use `CountDownLatch` or manually incomplete Futures to coordinate conditions deterministically in tests.

If a timeout and actual completion occur nearly simultaneously, the application must **accept the race boundary**: sometimes the Future completes with a value, and sometimes the timeout wins, depending on conditions and actual linearization order. Do not treat `orTimeout(100ms)` as a clock accurate to the nanosecond.

### CancellationException and CompletionException in Dependent Stages

Exception paths should be clearly categorized:

- Direct `CompletableFuture.cancel()` then `get()/join()` on **the Future itself**: `CancellationException`.
- Error in callback/supplier or `completeExceptionally`: `join()` typically throws `CompletionException` containing the cause; `get()` throws `ExecutionException` containing the cause.
- Source cancelled and dependent stage depends only on success: dependent may complete exceptionally with `CompletionException` wrapping `CancellationException`.
- `get(timeout)` on an **incomplete** Future when the deadline expires: `TimeoutException` directly from the wait.
- `orTimeout` completed the Future with a timeout error: `join()` typically throws `CompletionException` containing `TimeoutException`, while `get()` throws `ExecutionException` containing `TimeoutException`.
- Caller interrupted during `get()`: `InterruptedException`, which does **not** mean the source was cancelled.

Lumping all of these into a single "task failed" message breaks retry logic, alerting, and operational observability.

## 15. Limitations of CompletableFuture Beyond Cancellation

`CompletableFuture` is very useful for composition, but it does not handle all orchestration on its own:

| Limitation | Consequence | Design direction |
|---|---|---|
| `cancel(true)` does not control interrupting background tasks. | Worker may keep running/holding resources. | Cancellation token, `FutureTask` handle, I/O cancel APIs. |
| `orTimeout` only completes the Future. | The real task may still produce side effects after the deadline. | Pass deadlines into tasks and use I/O timeouts. |
| Does not automatically cancel all running upstream/sibling/dependent tasks. | Wasted work continues after the caller gives up. | Separate ownership and cancellation graph. |
| `allOf/anyOf` does not cancel remaining Futures by default. | Sibling tasks keep running even after the aggregator completes. | Clean up individual tasks as needed by policy. |
| Non-Async callbacks can run on the completing thread. | Heavy callbacks stall unintended threads. | Deliberately use `*Async(..., executor)`. |
| Async callbacks depend on a live executor. | Shutdown/rejection can make stages exceptional. | Manage lifecycle so dependents can run. |
| `join()` can block indefinitely. | Caller thread is held if a stage never completes. | Timed `get`, overall timeout/deadline, composition. |
| Completion does not guarantee I/O or transactions rolled back. | Retries can duplicate side effects. | Idempotency, transactions, deduplication. |
| Future result is not a multi-event stream. | Calling `complete` multiple times does not emit a sequence of results. | Use a queue/publisher suited for event streams. |
| API allows callers to `complete` internal Futures. | Callers can alter results violating ownership. | Return an appropriate `CompletionStage` view; protect completion rights. |

**There is no automatic "structured cancellation" just from chaining `thenCompose` or `thenCombine`.** You are creating dependent stages for results, not necessarily a tree of resource ownership and lifecycle.

## 16. Java Memory Model: Completion and Publication Differ from Worker Termination

For a `Future`, actions of the asynchronous computation have a **happens-before** relationship with actions in another thread **after retrieving the result via the corresponding `Future.get()`**. `CompletableFuture`'s synchronization allows dependent stages to observe results published via the completion mechanism.

However:

- A successful `future.get()` guarantees you have observed the Future's completion/result; it does **not** allow assuming all workers/siblings outside the Future have finished.
- When a Future is **cancelled early**, the worker may continue mutating state **after** the Future is already terminal; mutations that had not occurred at that point cannot automatically be considered finished or visible.
- An `AtomicBoolean` cancellation token has volatile read/write semantics: a worker reading the flag can observe the stop request properly per the JMM, provided it actually **reads the flag**.
- `CountDownLatch.countDown()/await()`, `Thread.join()`, and other synchronization primitives have corresponding happens-before contracts, making them suitable for testing milestones like "the worker reached here" or "the worker finished".
- `CompletableFuture` does not make an `ArrayList` mutated concurrently by multiple callbacks thread-safe.

The safe choice is usually immutable results, clear ownership, a separate cancellation flag for the operation, and an independent **task termination** signal if resources must be closed after cancelling the result future.

## 17. Designing an API with Cancellation Authority: A Reasonable Model

If you expose `CompletionStage<Result>` to callers, decide what authority callers have:

- May the caller **stop waiting**, while the computation must continue because others need it?
- May the caller **cancel the operation** and request the worker to exit?
- May the caller **receive a fallback** on timeout, while the background operation keeps running?
- Does the caller need to wait until **cleanup is actually done**?

You can separate three signals:

```text
Operation handle
   |
   +-- CompletionStage<Result> outcome   -> result/exception per contract
   +-- requestCancel()                     -> request stopping the actual work
   +-- CompletionStage<Void> terminated    -> worker/resource cleanup finished
```

This is a **design model**, not a built-in JDK API interface. It clarifies that **cancelling result observation** and **shutting down actual work** are two different needs. If the caller does not own the source computation, `requestCancel` may only cancel its own portion of work rather than stopping the shared source.

Simple cases do not need three separate handles: if a task always finishes quickly, has no side effects, and the owner only needs the value, a single `CompletableFuture` is usually enough. Only add cancellation machinery when the problem genuinely requires it.

## 18. Common Mistakes and Fixes

| Mistake | Consequence | Right approach |
|---|---|---|
| Believing `CompletableFuture.cancel(true)` will interrupt the worker. | Worker keeps running after the Future is cancelled. | Use a separate stop signal / `FutureTask` handle if interruption is needed. |
| Treating `isCancelled()` as worker cleanup being done. | Closing resources too early; state mutated afterwards. | Wait for a separate termination/acknowledgement signal. |
| Calling `get(timeout)` and treating it as task cancellation. | Timeout only ends the wait. | Decide whether to continue/cancel/timeout at the task level. |
| Using `orTimeout` as a timeout for database/sockets. | I/O may still run after the Future times out. | Set timeouts on the I/O client and use a cancellation protocol. |
| Thinking `completeOnTimeout` does not affect the source Future. | Shared callers may all see the fallback terminal state. | Clearly identify the owner and which stage gets the timeout. |
| Cancelling a dependent and expecting a shared source to stop. | Source keeps running; other consumers still use it. | Design upstream cancellation around ownership. |
| Cancelling a source and thinking all running dependents also stop. | Already-started callbacks may continue side effects. | Cooperative stop for real work. |
| Lumping `CancellationException`, `InterruptedException`, and `TimeoutException` into one case. | Broken retry/metrics and lifecycle handling. | Distinguish future-state, caller-wait, and operation-timeout. |
| Catching `InterruptedException` and ignoring it. | Caller may wait forever and lose the cancel signal. | Rethrow or restore the flag and exit. |
| Calling `join()` unboundedly on a stage with no completion path. | Thread blocked indefinitely. | Design deadlines/guaranteed completion and bounded waits. |
| Immediately retrying a task with side effects after a timeout. | May duplicate execution because the old task is still running. | Idempotency/dedup, track old state. |
| Shutting down the executor before dependent `thenApplyAsync` stages are submitted. | `RejectedExecutionException`, exceptional pipeline. | Manage the lifecycle of the entire pipeline. |
| Letting non-Async callbacks do long blocking I/O. | Completing thread gets stuck. | Specify an appropriate executor. |
| Creating a `CompletableFuture` and never completing it. | Dependents and callers may wait forever. | Timeouts/owners ensure every branch reaches a terminal state. |
| Using a plain unsynchronized boolean as a `CancellationToken`. | Worker may not see updates per the JMM. | Use `AtomicBoolean`/volatile and clear checkpoints. |
| Closing resources used by the worker right after `future.cancel`. | Worker still owns the resource. | Define ownership and a separate terminated signal. |

## 19. Practical Checklist

1. **Distinguish the requirement:** just stop waiting for the result, or stop the actual computation?
2. **Know the implementation:** `CompletableFuture.cancel(true)` does not behave like `FutureTask.cancel(true)`.
3. **Design a cancellation token:** use atomic/volatile or a dedicated API, checked at appropriate points.
4. **Wake up blocked tasks:** I/O timeouts, interruption via the right handle, closing resources per contract, or a wake-up mechanism.
5. **Never call `Thread.stop()`:** it provides no safe cleanup or invariant guarantees.
6. **Separate result and termination:** a cancelled Future does not mean the worker's `finally` block is done.
7. **Have clear exceptional outcome paths:** distinguish `CancellationException`, `CompletionException`, `ExecutionException`, `TimeoutException`, and `InterruptedException`.
8. **Do not assume cancel propagates backward:** cancelling a dependent does not automatically stop the source.
9. **Do not assume siblings are cancelled:** `allOf`/`anyOf` do not manage the full lifecycle of component tasks.
10. **Define deadlines:** `get` timeout differs from `orTimeout` and differs from I/O API timeouts; consider the overall SLA.
11. **Manage executors:** dedicated pools have an owner, controlled shutdown, and bounded `awaitTermination`.
12. **Protect mutable state:** completion does not replace locks/atomics/immutable payloads.
13. **Idempotency on retry:** an old task may still produce side effects after a timeout.
14. **Do not let cancel hide cleanup errors:** add logs/metrics and termination signals if needed.
15. **Test races deterministically:** use latches to separate task started, future cancelled, worker released, and executor terminated.
16. **Test uncooperative tasks:** if a task ignores tokens/interrupts, ensure the system has resource limits and monitoring.
17. **Consider shared computations:** a caller should not unilaterally cancel a source that others still need.
18. **Observe in production:** cancellation rate, timeout rate, lingering tasks after cancel, queue depth, thread pool saturation, I/O latency, and cleanup failures.

## 20. Self-Check Questions

1. **Does `CompletableFuture.cancel(true)` always interrupt the worker?** No; in the JDK implementation, `mayInterruptIfRunning` has no effect.
2. **Is `FutureTask.cancel(true)` different?** It can attempt to interrupt the worker if the task is running; it still cannot forcefully stop arbitrary code.
3. **Does `isDone() == true` mean the worker has stopped?** No; Future termination can occur before worker termination.
4. **Does `isCancelled() == true` guarantee cleanup is finished?** No.
5. **After `cancel()`, what does `join()` on the `CompletableFuture` itself usually throw?** `CancellationException`.
6. **How can a cancelled source make a dependent exceptional?** The dependent can throw `CompletionException` wrapping `CancellationException`.
7. **Does cancelling a dependent automatically cancel upstream?** Not by default.
8. **Does `get(timeout)` mutate the Future when it expires?** No.
9. **Does `orTimeout()` mutate the Future?** It can complete that Future itself with `TimeoutException`.
10. **Does `completeOnTimeout()` automatically stop the supplier?** No.
11. **If `get()` throws `InterruptedException`, who was interrupted?** The thread waiting in `get`; not necessarily the worker.
12. **Does `join()` declare `InterruptedException` like `get`?** No.
13. **How can a worker stop cooperatively?** Use an atomic/volatile token, checkpoints, an appropriate mechanism to wake blocking calls, and cleanup.
14. **Why is a separate termination acknowledgement needed?** Because the result future can reach a terminal state before worker cleanup finishes.
15. **Why can retrying immediately after a timeout be dangerous?** The old task may still be running/producing side effects, causing duplicate work.
16. **Does `allOf` automatically cancel all siblings when one Future is cancelled?** No.
17. **Should you shut down the common pool inside a request?** No; it is a shared pool.
18. **How does the JMM help with a cancellation token?** Atomic/volatile guarantees proper visibility, but the worker must read the flag.
19. **What happens if a completion path and a cancel path race?** One terminal completion wins; the outcome depends on the actual order.
20. **What is the most reliable design direction for long I/O tasks?** Set I/O timeouts, clear ownership, real cancellation at the source API, cleanup, and separate result/termination signals.

**Remember:** **`CompletableFuture.cancel()` cancels the result state, not a command to stop a thread.** `get(timeout)` limits a single wait, `orTimeout()` or `completeOnTimeout()` changes the Future's state, while stopping a computation requires **cooperative cancellation, I/O control, resource management, and termination confirmation**. Do not infer worker state solely from `isDone()` or `isCancelled()`.

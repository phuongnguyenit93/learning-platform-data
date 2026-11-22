# `orTimeout`, `completeOnTimeout`, and Whether the Task Actually Stops

When working with `CompletableFuture`, we often want to specify: "If the work is not finished after a certain duration, fail with an error or return a fallback value." Java provides `orTimeout(...)` and `completeOnTimeout(...)` to address that need. However, **an expired future does not mean the computing thread has stopped**.

This is a critical distinction when handling exceptions, task cancellation, and resources in asynchronous systems. A request may have already returned a `TimeoutException` to the caller while the underlying task continues reading data, holding connections, computing, or writing to another system. This lesson explains exactly what is guaranteed, what is not guaranteed, and how to design safe timeouts.

## 1. Two Different Things: The Observed Result and the Running Work

Let us distinguish:

- **The actual work**: the code inside a `Supplier`, `Runnable`, `Callable`, or an asynchronous stage. It may run on `ForkJoinPool.commonPool()` or a specified `Executor`.
- **The `CompletableFuture`**: the object representing a normal completion, exceptional completion, or cancellation result. Callers can read the result via `join()`, `get()`, or callbacks.
- **The time limit** (*deadline/timeout*): the point in time at which an observed result is chosen. This limit does not by itself provide a mechanism to stop the logic inside the work.

Model:

```text
Caller                           Executing Worker
    |                                  |
    |-- supplyAsync(...) ------------->| starts task
    |                                  | waiting / processing
    |-- orTimeout(100 ms)              |
    |                                  | still processing
    |<-- future completes with error --| 100 ms deadline reached
    |    TimeoutException              |
    |                                  | may continue
    |                                  | may cause side effects
    |                                  | then returns real result
    |                                  v
    |                          real result arrives too late,
    |                          does not replace timeout result
```

If the work has already started, `orTimeout`/`completeOnTimeout` **does not promise to interrupt the thread or cancel ongoing I/O**. Conversely, if the work has not started yet, the specific execution mechanism might skip the computation after the future has already completed. Do not infer an absolute rule of "always runs to completion" or "always gets stopped"; what the API guarantees is how the `CompletableFuture` **completes**.

## 2. Comparing the Contracts of the Two APIs

Both methods have existed since Java 9, so they can be used normally on Java 17+:

```java
CompletableFuture<T> orTimeout(long timeout, TimeUnit unit);
CompletableFuture<T> completeOnTimeout(T value, long timeout, TimeUnit unit);
```

These are **illustrative signatures** of the generic methods, not a standalone Java program.

| Property | `orTimeout(timeout, unit)` | `completeOnTimeout(value, timeout, unit)` |
| --- | --- | --- |
| If the future is incomplete at expiration | Completes **exceptionally** with `TimeoutException` | Completes **normally** with the fallback `value` |
| `join()` after timeout wins | Typically throws `CompletionException`, with `getCause()` as `TimeoutException` | Returns `value` |
| `get()` after timeout wins | Throws `ExecutionException`, with `getCause()` as `TimeoutException` | Returns `value` |
| `isCompletedExceptionally()` if timeout wins | `true` | `false` |
| `isDone()` if timeout wins | `true` | `true` |
| `isCancelled()` due to the timeout operation alone | `false` | `false` |
| Does it automatically interrupt the running thread? | **Not guaranteed; does not issue an interrupt request to the work** | **Not guaranteed; does not issue an interrupt request to the work** |
| Returned object | **The same future it was called on**, not a copy | **The same future it was called on**, not a copy |

The most common misconception is that **both mutate the state of the same `CompletableFuture`** if the timeout arrives before the real result. Writing `CompletableFuture<T> timed = source.orTimeout(...)` does not create an "independent observation layer" over `source`; `timed == source` is `true`.

Similarly, `completeOnTimeout(fallback, ...)` does not store "both the original value and the fallback" to pick again later. Once the future has completed with the fallback, a normal completion attempt from a late-arriving task cannot replace that result via regular `complete(...)`.

## 3. Completion Order: Who Wins the Race?

Both APIs schedule a possible completion **if the future is still not done when the deadline arrives**. The system has a race between the real result and the timeout action:

```text
                    Incomplete Future
                             |
                 +-----------+-----------+
                 |                       |
      Task completes first         Timeout arrives first
                 |                       |
      real result/error wins     +-------+-------+
                                 |               |
                             orTimeout    completeOnTimeout
                                 |               |
                           TimeoutException   fallback
```

If the task completes before the deadline, the timeout does not alter the real result. If the timeout completes the future first, a result produced afterward generally cannot overwrite the locked-in state. If the two events arrive close together, **do not rely on perceived ordering or millisecond timestamps printed in logs**; whichever completion action wins the race determines the result.

Points to remember:

1. The deadline counts from **when the timeout method is called**, not by default from when the worker actually begins running. A task still queued in an executor can still expire before it runs.
2. Apparent timing can drift due to JVM scheduling, machine load, and callback dispatch. A timeout is a wait/result-bounding policy, not a zero-error real-time clock.
3. If the future has already completed beforehand, calling these two APIs does not change the locked-in state; a timeout attached afterward does not make the old result disappear.
4. A new stage may depend on a timed-out future. When `orTimeout` wins, success-only branches such as `thenApply` typically skip value processing and propagate the error state. When `completeOnTimeout` wins, they can run with **the fallback as if it were a successful value**.
5. `isDone()` does not indicate whether it succeeded, failed, was cancelled, or finished the physical work. It is only a signal that **the future has completed**.

## 4. Runnable Java 17+ Example: The Future Expires While the Worker Keeps Running

This example uses `CountDownLatch` to ensure the worker has started and intentionally waits for a release signal from `main`. Thus, when the deadline occurs, we know the real work **has not finished**. We verify the two APIs separately on two independent futures rather than placing both timeouts on the same future.

Create the file **`TimeoutRealityDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TimeoutRealityDemo {
    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Demo synchronization timed out");
        }
    }

    private static CompletableFuture<String> blockedWork(
            ExecutorService pool,
            CountDownLatch started,
            CountDownLatch release,
            CountDownLatch finished) {
        return CompletableFuture.supplyAsync(() -> {
            started.countDown();
            try {
                release.await();
                return "real result";
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new CompletionException(exception);
            } finally {
                finished.countDown();
            }
        }, pool);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch releaseError = new CountDownLatch(1);
        CountDownLatch releaseFallback = new CountDownLatch(1);

        try {
            CountDownLatch startedError = new CountDownLatch(1);
            CountDownLatch finishedError = new CountDownLatch(1);
            CompletableFuture<String> originalError =
                    blockedWork(pool, startedError, releaseError, finishedError);
            await(startedError);

            CompletableFuture<String> timed =
                    originalError.orTimeout(150, TimeUnit.MILLISECONDS);
            System.out.println("orTimeout same future: "
                    + (timed == originalError));

            try {
                timed.join();
            } catch (CompletionException exception) {
                System.out.println("orTimeout cause: "
                        + exception.getCause().getClass().getSimpleName());
            }

            System.out.println("orTimeout work finished at deadline: "
                    + (finishedError.getCount() == 0));
            releaseError.countDown();
            await(finishedError);
            System.out.println("orTimeout still exceptional: "
                    + originalError.isCompletedExceptionally());

            CountDownLatch startedFallback = new CountDownLatch(1);
            CountDownLatch finishedFallback = new CountDownLatch(1);
            CompletableFuture<String> originalFallback =
                    blockedWork(pool, startedFallback, releaseFallback,
                            finishedFallback);
            await(startedFallback);

            CompletableFuture<String> fallback =
                    originalFallback.completeOnTimeout(
                            "fallback", 150, TimeUnit.MILLISECONDS);
            System.out.println("completeOnTimeout same future: "
                    + (fallback == originalFallback));
            System.out.println("completeOnTimeout result: " + fallback.join());
            System.out.println("completeOnTimeout work finished at deadline: "
                    + (finishedFallback.getCount() == 0));

            releaseFallback.countDown();
            await(finishedFallback);
            System.out.println("completeOnTimeout result after work: "
                    + originalFallback.join());
        } finally {
            releaseError.countDown();
            releaseFallback.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Compile and run:

```bash
javac --release 17 TimeoutRealityDemo.java
java TimeoutRealityDemo
```

Output:

```text
orTimeout same future: true
orTimeout cause: TimeoutException
orTimeout work finished at deadline: false
orTimeout still exceptional: true
completeOnTimeout same future: true
completeOnTimeout result: fallback
completeOnTimeout work finished at deadline: false
completeOnTimeout result after work: fallback
```

**Explanation of the results:**

- The two `same future: true` lines prove that the method returns the same object it was called on. No independent future is created by these two timeout methods alone.
- The `orTimeout` branch: `join()` ends with `CompletionException`, wrapping `TimeoutException`. `finishedError` has still not counted down to 0 because the worker is still waiting on `releaseError`. Thus **the future failed due to timeout before the real work finished**.
- After `main` unblocks the worker, the actual work runs to completion and returns `"real result"`; however, `originalError` still has `isCompletedExceptionally() == true`, because the timeout error state won earlier.
- The `completeOnTimeout` branch: `join()` returns `"fallback"` even though the worker is not done. After the worker is released and returns the real result, the future still returns `"fallback"` because the fallback value already completed the future earlier.

The example waits for `started` before setting the deadline and only releases the worker **after** observing the timeout; the outcome does not depend on whether the OS schedules the worker quickly or slowly. The five-second wait limits protect the demo program from hanging indefinitely if the environment encounters an issue. In real applications, tasks should not wait on artificial latches like this; this is purely a tool to demonstrate the difference between **completing a `CompletableFuture`** and **completing the actual processing**.

## 5. How Does `get(timeout, unit)` Differ from `orTimeout` and `completeOnTimeout`?

A method often confused with the two APIs above is:

```java
T result = future.get(100, TimeUnit.MILLISECONDS);
```

This is an illustrative snippet assuming `future` is already in scope, has result type `T`, and checked exceptions are handled. `get(timeout, unit)` bounds **the duration of a single waiting call**, without transitioning an incomplete future into a timeout error state. If the wait times out, that call directly throws `TimeoutException`, while the future may remain incomplete and later yield a successful result.

| API | What is bounded | Effect on future state upon expiration | Observed exception/value |
| --- | --- | --- | --- |
| `future.get(100, MILLISECONDS)` | The current thread's **call waiting for the result** | Does not complete the future itself | Throws `TimeoutException` directly at the waiting call |
| `future.orTimeout(100, MILLISECONDS)` | The time limit for **the future to still be allowed to wait for completion** | Transitions an incomplete future to exceptional completion | `join()` typically throws `CompletionException` wrapping `TimeoutException`; `get()` throws `ExecutionException` wrapping the cause |
| `future.completeOnTimeout(fallback, 100, MILLISECONDS)` | The time limit for the future to receive the real result before fallback | Transitions an incomplete future to normal completion | `join()`/`get()` returns `fallback` |

`get(timeout, unit)` can also throw `InterruptedException` when the **waiting thread** is interrupted, `ExecutionException` if the work completed exceptionally, and `CancellationException` if the future was cancelled. These are distinct paths from the waiting call's own `TimeoutException`.

The second example also shows how to attach a deadline to **a dependent stage** to bound the result for a caller while leaving the source future untouched.

Create the file **`TimeoutViewDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutViewDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> original = new CompletableFuture<>();

        try {
            original.get(50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException exception) {
            System.out.println("get wait timed out: true");
        }

        System.out.println("original done after get: " + original.isDone());
        original.complete("ready");
        System.out.println("original after completion: " + original.join());

        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> view = source.thenApply(value -> value);
        view.orTimeout(50, TimeUnit.MILLISECONDS);

        try {
            view.join();
        } catch (CompletionException exception) {
            System.out.println("view cause: "
                    + exception.getCause().getClass().getSimpleName());
        }

        System.out.println("source done at view deadline: " + source.isDone());
        source.complete("late success");
        System.out.println("source after completion: " + source.join());
        System.out.println("view still exceptional: "
                + view.isCompletedExceptionally());
    }
}
```

Compile and run:

```bash
javac --release 17 TimeoutViewDemo.java
java TimeoutViewDemo
```

Output:

```text
get wait timed out: true
original done after get: false
original after completion: ready
view cause: TimeoutException
source done at view deadline: false
source after completion: late success
view still exceptional: true
```

Explanation: `original.get(...)` timed out, yet `original.isDone()` remains `false`, so calling `complete("ready")` still produces a successful result. In the `source`/`view` example, `thenApply(value -> value)` creates **a new dependent `CompletableFuture`**; calling `orTimeout` on `view` only makes **`view`** complete exceptionally. `source` can still complete normally with `"late success"` and keep that result. This approach separates the "caller-visible deadline" from the source future; it **still does not automatically stop the work** producing `source`.

Do not apply this dependent-stage trick mechanically if the design requires preventing all side effects after a timeout. In that case, a dedicated stop protocol at the execution layer is needed.

## 6. Does `cancel(true)` Stop a `CompletableFuture` Task?

For **`CompletableFuture` itself**, `cancel(mayInterruptIfRunning)` transitions an incomplete future to a cancelled state with `CancellationException`. The API documentation explicitly states that the `mayInterruptIfRunning` argument **has no effect in this implementation because interrupts are not used to control processing**.

Therefore:

- `completableFuture.cancel(true)` does not guarantee interrupting the thread running the supplier.
- `isCancelled() == true` means **the future object** is in the cancelled state; it does not confirm that the supplier's code has terminated.
- If a future is **directly** cancelled, `join()`/`get()` may throw `CancellationException` directly. For dependent stages, the exception may be wrapped in `CompletionException`.
- `orTimeout` is not equivalent to `cancel(true)`: it completes exceptionally with `TimeoutException`. `completeOnTimeout` even completes **normally** with the fallback.

Distinguish this from a **`Future` returned by `ExecutorService.submit(...)`**: the standard implementation uses `FutureTask`, where `cancel(true)` can attempt to interrupt the running task thread. That is still a **cooperative interrupt request**; code that does not respond to interrupts or is blocked in uninterruptible I/O may not stop immediately. Do not automatically carry conclusions about `FutureTask` over to `CompletableFuture`.

If the application must stop a specific operation upon expiration, design **execution-side control over the work**, such as a controllable `Future<?>`, an application-owned cancellation signal, client-supported I/O deadlines, or the library's official cancellation API. After requesting cancellation, you still need to wait for or verify that the work has stopped if subsequent steps require it.

## 7. Cooperative Cancellation and I/O Timeout Strategies

Timeouts at the `CompletableFuture` layer should be combined with concrete execution policies:

### 7.1. CPU-Bound Work

If a computation loop is long-running and must support cancellation, check the stop request state at reasonable points. When the work runs in a context where the thread **is actually interrupted**, you can check `Thread.currentThread().isInterrupted()` and exit safely. With `CompletableFuture.orTimeout` alone, do not wait for the interrupt flag to appear on its own: this API does not send it.

If the code can accept a dedicated cancellation flag, such as `AtomicBoolean stopRequested`, the loop can check that flag to decide whether to stop. Make sure the application's deadline/cancellation mechanism actually sets the flag. Creating a flag that nothing ever updates has no effect.

### 7.2. Waiting Work

Operations such as `BlockingQueue.take()`, `Thread.sleep()`, or `Future.get()` can respond to `InterruptedException` when the thread executing them is interrupted. The task should catch the interrupt at the appropriate layer, restore the interrupt status with `Thread.currentThread().interrupt()` if not propagating the exception upward, and then exit and clean up. However, **`CompletableFuture` timeouts do not trigger this interrupt step on their own**.

### 7.3. Remote I/O, Databases, and External Services

A network request can still continue using a socket or causing side effects after the future has timed out. Therefore:

1. Configure timeouts on the **I/O client** (connect, read, overall call) or use deadline APIs provided by the library.
2. If the client has a real cancellation mechanism, tie it to the request lifecycle. Verify the contract to see whether cancellation releases resources and prevents late responses.
3. For operations with side effects such as transferring funds, writing orders, or emitting events, use idempotency keys or design to prevent duplicate processing. A "caller-side timeout" does not prove the server-side operation did not execute.
4. Track start time, timeout-reported time, actual work completion time, and resource hold duration; these timestamps can differ significantly.

Timeouts protect **the caller's wait time**. To protect **resources and correctness when stopping work**, you must combine them with appropriate stop mechanisms or limits.

## 8. Designing Safe Pipelines: Avoid Hiding Errors or Corrupting the Source

### 8.1. Use `orTimeout` When Expiration Must Be an Error

If returning late is invalid according to the API contract, you can use:

```java
CompletableFuture<Response> result =
        loadAsync().orTimeout(2, TimeUnit.SECONDS);
```

This is an illustrative snippet requiring the application's `Response` type and `loadAsync()` method. If `loadAsync()` returns a future shared across multiple places, calling `orTimeout` **applies the deadline to that exact future**, affecting everyone observing it. If you need a per-caller timeout, create a dependent stage and apply the deadline to the dependent stage:

```java
CompletableFuture<Response> shared = loadAsync();
CompletableFuture<Response> callerView =
        shared.thenApply(value -> value)
                .orTimeout(2, TimeUnit.SECONDS);
```

This is also an illustrative snippet requiring `loadAsync()` and `Response`. `shared` is not directly timed out by `callerView`. `callerView` only bounds how this caller receives the result; the background work of `shared` still needs its own stop mechanism if you genuinely want to cancel it.

### 8.2. Use `completeOnTimeout` When a Fallback Value Is a Valid Result

```java
CompletableFuture<String> displayName =
        fetchDisplayNameAsync()
                .completeOnTimeout("Ẩn danh", 300, TimeUnit.MILLISECONDS);
```

This is an illustrative snippet requiring the application's `fetchDisplayNameAsync()`. This approach is useful for display data where falling back is acceptable. However, `displayName.isCompletedExceptionally()` will return `false` if the fallback wins; downstream stages may see `"Ẩn danh"` as a successful value. If you need to distinguish a fallback from a real success, replace the return type with a structure representing the **result source** (*REAL* or *FALLBACK*) or record separate timeout metrics.

Do not use a silent success fallback for work where "real success" is mandatory, such as payment confirmation. Callers might assume the original task succeeded when it merely timed out and is still running.

### 8.3. Do Not Chain Both Methods on the Same Future Expecting "Error Then Fallback"

For example:

```java
future.orTimeout(100, TimeUnit.MILLISECONDS)
      .completeOnTimeout(fallback, 200, TimeUnit.MILLISECONDS);
```

This is an example **of a design to avoid**, not a standalone program (`future` and `fallback` are provided by the application). Both calls operate on the same future; if the 100 ms deadline completes exceptionally first, the 200 ms deadline has no opportunity to switch to the fallback. If the deadlines are equal, the outcome depends on a race. To convert a timeout error into a fallback, create an **exception-handling stage** using `exceptionally` or `handle`, recovering only the specific error type the application intends to recover from:

```java
CompletableFuture<String> withFallback =
        future.orTimeout(100, TimeUnit.MILLISECONDS)
              .exceptionally(error -> {
                  Throwable cause = error;
                  while (cause instanceof java.util.concurrent.CompletionException
                          && cause.getCause() != null) {
                      cause = cause.getCause();
                  }
                  if (cause instanceof java.util.concurrent.TimeoutException) {
                      return "fallback";
                  }
                  throw new java.util.concurrent.CompletionException(cause);
              });
```

This is an illustrative snippet assuming `CompletableFuture<String> future` is in scope. `exceptionally` creates a **new stage**, whereas `orTimeout` mutated `future` itself. If the source is shared, create an independent view first before attaching timeout/recovery. Do not catch all exceptions and return the same fallback, as that hides both programming bugs and data errors.

### 8.4. Post-Timeout Callbacks May Run Before the Worker Stops

When `completeOnTimeout` wins, a `thenApply`, `thenAccept`, or `whenComplete` stage can start on the future's completion path even while the supplier is still running. If the callback writes data, emits events, or releases a resource that the worker is still using, explicit coordination is required.

Some callbacks **without the `Async` suffix** may run on the thread performing the `complete` action, including the thread that triggers the timeout. Therefore, do not put heavy computation or long blocking I/O in synchronous callbacks assuming they always run on the original worker. For heavy logic, consider `whenCompleteAsync`, `handleAsync`, or `thenApplyAsync` variants with an intentional executor and manage that executor's queue/resources.

## 9. Monitoring State: What to Log to Avoid Confusion?

A system with deadlines should observe **both future-level outcomes and the execution lifecycle**:

| Signal | Accurate interpretation |
| --- | --- |
| `future.isDone() == true` | The future has reached a terminal state; the actual work has not necessarily stopped |
| `future.isCompletedExceptionally() == true` | The future completed abnormally (including timeout, cancellation, or another error), without identifying the specific cause |
| `future.isCancelled() == true` | The future was cancelled; does not guarantee the computing thread has stopped |
| `join()` reports `CompletionException` with cause `TimeoutException` | An `orTimeout`-style deadline caused the future to fail, if this is the configured timeout path |
| `completeOnTimeout` returns fallback | The future completed normally with the fallback value; separate metadata is needed if you need to know it was a fallback |
| Worker reported completion and resources were released | A separate signal from the work/execution manager; must be tracked outside the future's `isDone()` when deadlines exist |

Logs should include the request ID, operation name, deadline, timeout vs. success status, and actual stop status when verifiable. Do not log sensitive secrets. If the caller returns a timeout response while the backend request continues running, counting only "returned" requests does not reflect how many tasks are still consuming resources.

Do not use a careless `getCause()` check to conclude that the worker threw `TimeoutException`: it may be an error generated by **the deadline mechanism**, not an exception thrown inside the supplier. Conversely, if the supplier itself throws `TimeoutException` in the application's context, inspect the source and stack trace to tell them apart.

## 10. Common Pitfalls

| Misconception | Real-world consequence | How to handle it |
| --- | --- | --- |
| "Expiration definitely stops the background task." | Worker still holds resources or causes side effects | Design a dedicated cancellation mechanism and track real completion |
| "`orTimeout` creates a new future; the source stays untouched." | Accidentally applying a deadline to a shared result | Remember `orTimeout` returns `this`; create a dependent stage if a separate view is needed |
| "`completeOnTimeout` produces a fallback, but the real result will replace it later." | Mishandling state and fallback data | The first completion wins; late results do not overwrite normally |
| "`completeOnTimeout` reports `isCompletedExceptionally() == true` on fallback." | Monitoring misses timeouts | Fallback is a normal completion; track the result source separately |
| "`get(timeout)` fails the future." | Confusing a wait bound with the result state | Timeout from `get(timeout)` directly ends only that wait |
| "`cancel(true)` on `CompletableFuture` always interrupts the supplier." | False cancellation, task keeps running | Need an execution-controlling `Future` or dedicated cancellation protocol |
| "Timeouts automatically close HTTP/DB connections." | Pool exhaustion, work outlives caller departure | Configure timeouts/cancellation on the I/O client and clean up resources |
| "Multiple timeouts can be chained to replace an error with a fallback." | Unexpected results because the same future is already locked | Create an error-handling stage or a consistent deadline policy |
| "`isDone()` implies the worker has finished." | Premature resource release or duplicate work launch | Track the worker lifecycle and use a separate confirmation mechanism |

## 11. Self-Check Questions

**Scenario 1.** `CompletableFuture<String> f` is still running. `f.orTimeout(100, MILLISECONDS)` is called and the timeout occurs first. What does `f.join()` return?  
**Answer:** It typically throws `CompletionException` with `TimeoutException` as its cause; `f.isCompletedExceptionally()` is `true`. You cannot conclude from this that the supplier has stopped.

**Scenario 2.** Same situation, calling `f.completeOnTimeout("cached", 100, MILLISECONDS)`. The deadline arrives first. Later the supplier returns `"fresh"`. What does `f.join()` receive?  
**Answer:** `"cached"`; the future already completed normally with the fallback, and the late result cannot replace it through normal completion.

**Scenario 3.** `f.get(100, MILLISECONDS)` throws `TimeoutException`, yet `f.isDone()` is still `false`. Does this violate the contract?  
**Answer:** No. `get(timeout)` only bounds a single wait; it does not complete the future itself.

**Scenario 4.** Calling `CompletableFuture<String> timed = f.orTimeout(...)`. What is `timed == f`?  
**Answer:** `true`. `orTimeout` returns the exact future it was called on; the same applies to `completeOnTimeout`.

**Scenario 5.** A future just returned a fallback and `isCompletedExceptionally()` is `false`; does this prove the network API succeeded?  
**Answer:** No. It only proves the future completed normally, possibly with the fallback value; the network task may still be running.

**Scenario 6.** To apply a separate deadline for caller A while keeping the shared future for B, where should the timeout be placed?  
**Answer:** On a new dependent stage for A (e.g., `shared.thenApply(v -> v).orTimeout(...)`), not directly on `shared`; if stopping the underlying processing is also required, a cancellation mechanism must still be built.

**Scenario 7.** If `CompletableFuture.cancel(true)` succeeded, can we be sure the supplier thread received an interrupt?  
**Answer:** No. In the `CompletableFuture` implementation, the `mayInterruptIfRunning` parameter does not control interrupting the computation.

## 12. API Documentation

- [Java 17 — `CompletableFuture.orTimeout`, `completeOnTimeout`, `cancel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): specification of completion states, return objects, and the meaning of the cancel parameter.
- [Java 17 — `Future.get(timeout, unit)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): wait time limits and possible exceptions.
- [Java 17 — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html) and [Java 17 — `TimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): distinguishing the asynchronous error wrapper from the timeout signal.

Key design takeaway: **`orTimeout` completes the future with an error; `completeOnTimeout` completes the future with a value; `get(timeout)` only bounds a single wait. None of these three APIs guarantees terminating the running asynchronous work.** To actually stop the work, deliver the stop request to the execution or I/O mechanism and verify that it is handled.
# Callable<T> vs. Runnable When Returning a Result

## 1. The Problem: How Does a Task Running on Another Thread Return a Result?

In Java Concurrency, a task submitted to an executor typically runs on a different thread from the submitting thread. When you only need to **perform an action** (logging, updating state, sending notifications), `Runnable` is a natural choice. When the task needs to **compute and return a value**, `Callable<T>` represents the result directly via type `T`.

Both are **functional interfaces** and can be implemented using lambdas:

```java
Runnable printMessage = () -> System.out.println("Done");

Callable<Integer> calculate = () -> 21 * 2;
```

The key difference is not about "whether it runs asynchronously or not". `Runnable.run()` and `Callable.call()` themselves are just regular methods: calling them directly runs them on the **current thread**. They only execute asynchronously when handed off to a `Thread`, `Executor`, `ExecutorService`, or another scheduling mechanism.

When handed off to an `ExecutorService`, the application receives the result through a `Future<T>` rather than receiving it directly from the `submit(...)` call. `Future` is a **representation of a result that may become available in the future**, providing ways to wait for completion, retrieve the value, retrieve exceptions, check status, and request cancellation.

## 2. Comparing Runnable and Callable<T>

| Feature | `Runnable` | `Callable<T>` |
| --- | --- | --- |
| Interface | `java.lang.Runnable` | `java.util.concurrent.Callable<T>` |
| Abstract method | `void run()` | `T call() throws Exception` |
| Direct return value from method | None (`void`) | Yes, type `T` |
| Checked exceptions in signature | `run()` declares no checked exceptions | `call()` declares `throws Exception` |
| Direct use with `Thread` | `new Thread(runnable)` | Cannot pass `Callable` directly to the `Thread` constructor |
| Use with `Executor.execute(...)` | Yes, accepts `Runnable` | Does not accept `Callable` directly |
| Use with `ExecutorService.submit(...)` | Yes, returns `Future<?>` or `Future<T>` if a fixed result is provided | Yes, returns `Future<T>` |
| Typical scenario | Tasks that perform actions without producing a logical result | Tasks that compute, query, process data, and return a result |

Point to remember: `Runnable` does not mean "fire-and-forget". When submitting a `Runnable` via `ExecutorService.submit(runnable)`, the caller still receives a `Future<?>` to **wait for completion and observe errors**; it simply has no business value returned from `run()`.

Conversely, `Callable<T>` does not spawn threads on its own or guarantee parallel execution. A `Callable` invoked directly via `call()` is still a synchronous call.

## 3. API and Result Types of execute/submit

Two common abstractions:

```java
// Fragment illustrating the relevant signatures (not a standalone program).
interface Executor {
    void execute(Runnable command);
}

// Part of the ExecutorService API:
Future<?> submit(Runnable task);
<T> Future<T> submit(Runnable task, T result);
<T> Future<T> submit(Callable<T> task);
```

### 3.1. execute(Runnable): Delegate Work, No Future Returned

`executor.execute(runnable)` returns `void`. When the call succeeds, the executor has accepted the task according to its policy, but **no result handle** is returned to the caller by this API. Nor does it guarantee that the task has completed when `execute` returns.

If `Runnable.run()` throws an unchecked exception on a worker thread, the thread/`ThreadPoolExecutor` error-handling mechanism can record it via `UncaughtExceptionHandler` or `afterExecute` (depending on customization). The error is not turned into a `Future.get()` exception because no Future is returned. If the executor rejects the task, `RejectedExecutionHandler` may throw `RejectedExecutionException` immediately upon submission.

### 3.2. submit(Runnable): Returns Future, Completion Value Is null

```java
Future<?> future = executor.submit(
        () -> System.out.println("Side effect finished"));

Object result = future.get(); // null if Runnable completes normally
```

`future.get()` waits until the Runnable finishes (unless interrupted or the task is cancelled). On success, the return value is `null`; if the Runnable throws an error while running, `get()` throws `ExecutionException` with the underlying cause in `getCause()`.

Do not confuse `Future<?>` with "unable to track the task". It tracks the **lifecycle** even though it holds no computed result.

### 3.3. submit(Runnable, result): Fixed Value on Success

```java
Future<String> future = executor.submit(
        () -> performSideEffect(),
        "ACK");
```

This is an example fragment: `performSideEffect()` is defined by the application. After the `Runnable` runs successfully, `future.get()` returns the string `"ACK"` supplied by the caller **before** execution. This is not a value computed and returned by `run()` itself. If the Runnable throws an error, `get()` throws `ExecutionException` instead of returning `"ACK"`.

Use this approach when the task itself has no value to compute, yet the caller wants a typed Future and a value indicating completion.

### 3.4. submit(Callable<T>): Value Computed by the Task Itself

```java
Callable<Integer> task = () -> 20 + 22;
Future<Integer> future = executor.submit(task);
Integer answer = future.get(); // 42 when computation succeeds
```

`Callable.call()` may return `null` if that is a valid business result; type `T` does not require non-null. Choose a clear return type (`Integer`, `String`, `List<Record>`, a result record, etc.) so the caller understands the exact computation result.

## 4. Standalone Java 17 Example: Same Executor, Three Ways to Receive Results

The program uses a **single-thread executor** and always calls `get()` before moving on to the next task, so the order of printed lines is controlled. An exception from `Callable` is also demonstrated as the cause of `ExecutionException`.

Save as `CallableVsRunnableDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CallableVsRunnableDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Runnable action = () ->
                    System.out.println("Runnable: side effect");
            Future<?> actionFuture = executor.submit(action);
            System.out.println("Runnable result: " + actionFuture.get());

            Callable<Integer> computation = () -> 20 + 22;
            Future<Integer> computationFuture =
                    executor.submit(computation);
            System.out.println("Callable result: " + computationFuture.get());

            Future<String> fixedResult = executor.submit(
                    () -> System.out.println("Runnable: acknowledged"),
                    "ACK");
            System.out.println("Fixed result: " + fixedResult.get());

            Callable<String> failing = () -> {
                throw new IOException("source unavailable");
            };
            Future<String> failedFuture = executor.submit(failing);
            try {
                System.out.println(failedFuture.get());
            } catch (ExecutionException exception) {
                System.out.println(
                        "Failure cause: "
                        + exception.getCause().getClass().getSimpleName());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
javac CallableVsRunnableDemo.java
java CallableVsRunnableDemo
```

Output:

```text
Runnable: side effect
Runnable result: null
Callable result: 42
Runnable: acknowledged
Fixed result: ACK
Failure cause: IOException
```

Explanation: in the first submission, `submit(Runnable)` only indicates completion, so `get()` is `null`. In the second, `Callable<Integer>` actually produces `42`. In the third, `"ACK"` is passed from the caller side, not from `Runnable.run()`. In the last one, `IOException` is preserved as the cause of `ExecutionException`; it does not appear directly as an exception thrown by the `submit` call.

The example uses `main throws Exception` to keep the code concise; in real applications, code calling `get()` must plan for handling `InterruptedException`, `ExecutionException`, timeouts, and cancellation. The `finally` block requests shutdown and tries waiting up to 5 seconds; this does not guarantee that every uncooperative task will stop immediately after `shutdownNow()`.

## 5. Future<T> as the Bridge Between the Submitting Thread and the Result

When calling `submit(Callable<T>)`, the executor typically wraps the task into an object of type `RunnableFuture<T>` (one implementation example is `FutureTask<T>`). A worker can run the `Runnable` wrapper, while `Future<T>` gives the caller these operations:

| API | Semantics |
| --- | --- |
| `T get()` | Waits for the result; returns `T` on success; may be interrupted or throw an exception if the task fails/is cancelled |
| `T get(long timeout, TimeUnit unit)` | Waits at most the specified duration; may throw `TimeoutException` |
| `boolean isDone()` | `true` if the task completed normally, failed, or was cancelled |
| `boolean isCancelled()` | `true` if the task was cancelled |
| `boolean cancel(boolean mayInterruptIfRunning)` | Attempts to cancel; the return value indicates whether the cancellation request succeeded according to the Future's state |

A `Future` can represent the following logical states:

```text
SUBMITTED / QUEUED → RUNNING → COMPLETED_SUCCESS
                            └──→ COMPLETED_FAILURE
              └───────────────→ CANCELLED
```

This is a conceptual diagram of the task lifecycle; detailed state transitions also depend on the `Future` implementation. **`isDone() == true` does not mean the task succeeded**, because failed or cancelled tasks are also "done". You need `get()` or an explicit result-recording mechanism to distinguish the cases.

### Result, Failure, Cancellation: Three Completion Paths to Distinguish

```java
// Fragment: future returned by ExecutorService.submit(callable).
try {
    String value = future.get(1, TimeUnit.SECONDS);
    System.out.println("Success: " + value);
} catch (java.util.concurrent.TimeoutException timedOut) {
    System.out.println("Still waiting");
} catch (java.util.concurrent.CancellationException cancelled) {
    System.out.println("Cancelled");
} catch (java.util.concurrent.ExecutionException failed) {
    Throwable cause = failed.getCause();
    System.out.println("Task failed: " + cause);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
}
```

This is a fragment using a `Future<String> future` declared elsewhere.

- **`ExecutionException`**: the task ran and terminated with an exception or error; inspect `getCause()` for the root cause. `Callable.call()` allows checked exceptions; `Future.get()` does not throw that checked exception directly.
- **`CancellationException`** (unchecked): the Future was cancelled. `get()` does not return a valid result.
- **`TimeoutException`**: `get(timeout, unit)` waited past the limit; **the task is usually still running**. To cancel it, the caller must request cancellation separately, such as `cancel(true)`, and accept that cancellation is cooperative.
- **`InterruptedException`**: the thread waiting on `get()` was interrupted; this **does not automatically cancel the worker-side task**. Application code typically restores the interrupt flag or propagates the exception upward according to its contract.

### Future and Cross-Thread Data Visibility

`Future` also provides a memory consistency guarantee: actions taken by the asynchronous task **happen-before** actions following the corresponding `Future.get()` in another thread. Therefore, `get()` is useful as a synchronization point to read data properly published by the task.

However, `Future.get()` does **not** make arbitrary shared mutable state thread-safe. If multiple tasks concurrently modify an `ArrayList` or ordinary variables while running, synchronization, concurrent collections, or a design without shared mutable state is still required. For simple results, prefer **returning the result directly from `Callable`** instead of writing to a global variable and waiting on it manually.

## 6. Checked Exceptions and Errors "Hidden" When Using submit

`Callable<T>.call() throws Exception` allows asynchronous code to call APIs that throw checked exceptions:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

// Fragment: code reading a file and reporting IOException via Future.get().
Callable<String> readText = () ->
        Files.readString(Path.of("data.txt"));
```

`Files.readString` can throw `IOException`; because `call()` declares `throws Exception`, the lambda above is valid. With `Runnable.run()`, the caller must catch checked exceptions inside and handle them or wrap them into unchecked exceptions; it cannot declare `throws IOException` when overriding `run()`.

Another practical difference is how task errors are observed:

- `execute(runnable)`: unhandled unchecked exceptions from `run()` can go through the worker's uncaught exception mechanism; the caller has no `Future` returned by this call.
- `submit(runnable/callable)`: the executor typically runs a `FutureTask` wrapper, which **captures the exception**. Thus, the task's exception does not necessarily appear in the worker's uncaught exception log. The caller must call `get()` or have another error-recording path.
- `submit` can still throw `RejectedExecutionException` **at submission time** if the executor rejects the task under a throwing policy. This is an **admission** failure, distinct from `ExecutionException` caused by the task itself failing during execution.

Common mistake: calling `submit` and discarding the Future. If the task fails, the application may never read the cause and assume the work succeeded. For important tasks, keep the Future, collect results, or have a well-designed exception and metric collection path.

## 7. Risk of Indefinite Waiting and Using Timeouts

`Future.get()` without a timeout can block the caller indefinitely if the task never completes or the Future is orphaned due to a silent rejection policy. In systems with deadlines, `get(timeout, unit)` bounds **how long the caller waits**, but does not bound execution time on the worker.

Example fragment:

```java
try {
    Result result = resultFuture.get(500, TimeUnit.MILLISECONDS);
    use(result);
} catch (TimeoutException timedOut) {
    boolean cancellationRequested = resultFuture.cancel(true);
    reportTimeout(cancellationRequested);
}
```

`Result`, `resultFuture`, `use`, and `reportTimeout` are hypothetical application components; this snippet illustrates the idea and is **not a standalone program**. `cancel(true)` attempts to interrupt the running thread, but Java cannot forcibly stop a task that ignores interrupts or is stuck in an uninterruptible operation. If the task causes side effects, cancellation also does not undo work already performed.

### Thread Starvation Deadlock Trap

A task running in a single-thread executor submits a second task to the **same** executor and waits on `get()` of the second task:

```java
// ANTI-EXAMPLE (do not run): single-thread executor can deadlock.
// Callable<String> outer = () -> {
//     Future<String> inner = sameSingleThreadPool.submit(() -> "ready");
//     return inner.get(); // worker is running outer, inner has not started yet
// };
```

The single worker is busy waiting on `inner`, while `inner` sits in the queue waiting for the worker to become free. Avoid this kind of synchronous dependency: structure tasks as a processing pipeline, use an independent executor with appropriate capacity when truly needed, or apply non-blocking composition. **A Callable returning a result does not eliminate deadlock risks when the caller waits in the wrong place.**

## 8. What Do Task Cancellation and Interrupt Mean?

Example using `Future<String> future = executor.submit(callable)`:

- `future.cancel(false)`: requests cancellation without attempting to interrupt if the task is already running. The Future may transition to the cancelled state, but side effects of an already-executing task **may still continue**.
- `future.cancel(true)`: if the task is running, the Future may send an interrupt to the executing thread. The task only stops promptly if its code or blocking operations cooperate with interrupts.
- `future.get()` after successful cancellation throws `CancellationException`.
- `future.isCancelled()` reflects the Future's state; it does not guarantee that all resources have been closed or side effects rolled back.

A Callable can check for interrupts in a loop task:

```java
// Fragment: both Runnable and Callable can check for interrupts.
while (!Thread.currentThread().isInterrupted()) {
    performOneSmallStep();
}
```

Tasks calling blocking APIs may receive `InterruptedException`. Do not swallow that exception and keep running indefinitely; either propagate it from `Callable.call()`, or restore the interrupt flag in `Runnable.run()` before exiting.

Shutting down an executor and cancelling a Future are two different mechanisms. `shutdown()` stops accepting new tasks and lets already-accepted tasks finish; `shutdownNow()` attempts to interrupt workers and returns the list of queued tasks that have not started, **without guaranteeing** that running tasks stop immediately.

## 9. Callable from Runnable: Adapters and FutureTask

If you already have a `Runnable` that performs an action, but an API expects a `Callable<T>`, Java provides an adapter:

```java
// Fragment: Runnable already exists.
Runnable update = () -> System.out.println("Updated");
Callable<String> asCallable =
        java.util.concurrent.Executors.callable(update, "OK");
```

`asCallable.call()` runs `update.run()` and returns `"OK"` if it completes normally; if the Runnable throws an unchecked exception, that exception is still propagated through `call()`. The adapter **does not turn a side effect into a computed result**.

`FutureTask<V>` implements `RunnableFuture<V>`, meaning it can both be executed by an executor as a `Runnable` and read as a `Future<V>`:

```java
// Fragment illustrating the two roles of FutureTask.
java.util.concurrent.FutureTask<Integer> task =
        new java.util.concurrent.FutureTask<>(() -> 6 * 7);

executor.execute(task); // execute accepts Runnable.
Integer result = task.get(); // FutureTask is also a Future<Integer>.
```

There is no need to construct `FutureTask` manually in ordinary cases: `ExecutorService.submit(callable)` already handles Future creation and scheduling. `FutureTask` is useful when you need control over the wrapper or must integrate with an API that only accepts `Runnable`. Do not call `run()` manually and then also submit the same task, unless you truly understand `FutureTask`'s run-once completion semantics.

Another constructor is `new FutureTask<>(Runnable, V result)`: essentially equivalent in concept to `submit(Runnable, result)`, with the `result` value fixed in advance.

## 10. Multiple Callables: invokeAll and invokeAny

`ExecutorService` has two APIs for working with a collection of `Callable`s:

| API | Meaning | Result |
| --- | --- | --- |
| `invokeAll(Collection<? extends Callable<T>>)` | Waits for all to complete | List of `Future<T>` in the same order as the input collection; each `get()` may return a value or report an error |
| `invokeAll(tasks, timeout, unit)` | Waits up to a shared deadline | Upon return, any incomplete tasks are requested to cancel |
| `invokeAny(Collection<? extends Callable<T>>)` | Waits for **one** task to complete successfully | Returns the `T` value from one successful task; makes no promise about which task wins when multiple compete |
| `invokeAny(tasks, timeout, unit)` | Similar, with a time limit | May throw `TimeoutException` if no successful result arrives in time |

`invokeAny` does not mean "return the result of the first task to finish, even if it failed": it seeks a **successful result**; if one task fails, other tasks can still win. Once a result is chosen or there is no longer a reason to continue, the API handles cancelling incomplete tasks according to its contract. Do not use `invokeAny` to assume execution order or rely on side effects of all tasks.

Standalone program example `BatchCallableDemo.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BatchCallableDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 2 * 3,
                    () -> 4 * 5,
                    () -> 6 * 7);
            List<Future<Integer>> futures = executor.invokeAll(tasks);
            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get();
            }
            System.out.println("Total = " + total);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Compile and run:

```bash
javac BatchCallableDemo.java
java BatchCallableDemo
```

Stdout:

```text
Total = 68
```

Even with two workers and three tasks that may finish in any order, `invokeAll` returns Futures matching the order in the collection. The sum `6 + 20 + 42 = 68` does not depend on execution order.

## 11. Callable in ScheduledExecutorService

The **Future & Scheduling** group also includes scheduled tasks. `ScheduledExecutorService` supports:

- `schedule(Runnable command, long delay, TimeUnit unit)` returns `ScheduledFuture<?>`: runs **once** after a minimum delay, returning no business result.
- `schedule(Callable<V> callable, long delay, TimeUnit unit)` returns `ScheduledFuture<V>`: runs **once** after a minimum delay, allowing the value `V` to be retrieved from `get()`.
- `scheduleAtFixedRate(...)` and `scheduleWithFixedDelay(...)` accept a `Runnable` for repeated execution; a successful repeating task does not normally complete its Future in a one-shot manner. **Do not call `get()` expecting each cycle to return a value**: a periodic task's Future usually completes only upon cancellation or abnormal termination.

Example of a scheduled computation `ScheduledCallableDemo.java`:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledCallableDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        try {
            ScheduledFuture<Integer> future =
                    scheduler.schedule(() -> 7 * 6, 50, TimeUnit.MILLISECONDS);
            System.out.println("Scheduled result = " + future.get());
        } finally {
            scheduler.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac ScheduledCallableDemo.java
java ScheduledCallableDemo
```

Stdout:

```text
Scheduled result = 42
```

Note: `50 ms` is the **requested delay before eligibility for execution**, not a guarantee of running at exactly 50 ms or finishing on time. Scheduling depends on system load and worker availability. No framework is needed to schedule a Callable like this.

## 12. When to Choose Callable<T>, When to Keep Runnable?

**Choose `Callable<T>` when:**

1. The return value is part of the task's contract (total amount, analysis result, queried data, output object).
2. You want the compiler to check the return type of the `Future<T>` result, avoiding global variables or mutable holders.
3. The task needs to call APIs that throw checked exceptions and you want to surface errors through `Future.get()`.
4. You need `invokeAll`, `invokeAny`, or `schedule(Callable, delay, unit)` to receive results.

**Choose `Runnable` when:**

1. The task is action-oriented with no computed value to return (updating a cache, sending a notification, logging, cleanup).
2. The API requires `Runnable`, such as `new Thread(runnable)`, `Executor.execute(runnable)`, or periodic scheduling.
3. You only need to know whether the task finished or failed via `Future<?>` from `submit(runnable)`.
4. You want a fixed success value, in which case `submit(runnable, result)` can be used instead of creating a Callable just to return the same constant.

Avoid forcing every `Runnable` into `Callable<Void>`. This is valid when there is a design reason (returning `null`), but it makes code more verbose without adding business value on its own. If a task has a real value, `Callable<Result>` usually expresses the intent best.

### Quick Decision Table

| Goal | Preferred call | What the caller receives |
| --- | --- | --- |
| Just delegate a task without needing a handle | `execute(Runnable)` | No Future |
| Delegate a task and track completion/failure | `submit(Runnable)` | `Future<?>`, `get() == null` on success |
| Delegate an action task and want a constant on success | `submit(Runnable, T result)` | `Future<T>` returning the fixed value |
| Task computes and returns a result of type T | `submit(Callable<T>)` | `Future<T>` returning the result from `call()` |
| Multiple tasks producing results | `invokeAll`/`invokeAny` with `Callable<T>` | List of Futures or one successful value |
| One-time computation after a delay | `schedule(Callable<T>, delay, unit)` | `ScheduledFuture<T>` |

## 13. Common Pitfalls and How to Avoid Them

| Pitfall | Why it is wrong | How to handle it |
| --- | --- | --- |
| Thinking `Callable.call()` automatically runs on another thread | It is just a normal method if called directly | Use `ExecutorService.submit(callable)` or a scheduler |
| Trying to get a result from `Runnable.run()` | `run()` returns `void` | Switch to `Callable<Result>` or use `submit(runnable, fixedValue)` if only a fixed value is needed |
| Calling `submit(callable)` and expecting type T directly | `submit` returns `Future<T>`, not T | Call `future.get()` where blocking is permitted |
| Discarding the Future after `submit` | Task exceptions may only be stored in the Future and go unobserved | Keep the handle, read the result, monitor and log errors |
| Treating `isDone()` as success | Cancellation and failure also count as done | Call `get()`, handle `ExecutionException`/`CancellationException` |
| Catching `ExecutionException` and ignoring `getCause()` | Loses the root cause of failure | Use the cause for diagnostics or wrap/rethrow with context |
| Calling `get()` without timeout on latency-sensitive paths | Caller may wait a long time or indefinitely | Choose a timeout/deadline, design callbacks/composition when needed |
| Thinking `get(timeout)` stops the task | Timeout only bounds **waiting** | If appropriate, call `cancel(true)` and support interrupts |
| Having a worker wait on a Future of a task queued in the same single-thread pool | Can cause thread starvation deadlock | Restructure dependencies and avoid blocking inside workers |
| Using `DiscardPolicy` with `submit` and `get()` | Task is silently dropped; the Future may never complete | Prefer handlers that report errors clearly and proper admission control |
| Calling `Future.get()` on periodic schedules | A periodic Future does not produce a result per cycle | Report per-tick results via a dedicated mechanism; cancel according to lifecycle |
| Confusing `Future.get()` with a lock protecting shared state | It establishes memory visibility by contract, not mutual exclusion against data races from multiple writers | Use immutable designs or synchronization when sharing data |

## 14. Self-Check

1. **Can a `Runnable` be submitted via `submit`?** Yes. The caller receives `Future<?>`; if it completes successfully, `get()` returns `null`.
2. **How does `submit(Runnable, "OK")` differ from `submit(Callable<String>)`?** The former returns a fixed value supplied by the caller after the Runnable succeeds; the latter returns the actual value computed by `call()`.
3. **A `Callable<Integer>` throws `IOException`; what happens on `Future.get()`?** `get()` throws `ExecutionException`, whose `getCause()` is that `IOException`.
4. **Does `get(timeout)` throwing `TimeoutException` stop the task?** No. That is only a timeout on the wait operation; a separate cancellation policy is required.
5. **Does `isDone() == true` prove the task succeeded?** No; the task may have failed or been cancelled.
6. **Does `schedule(Callable<T>, delay, unit)` return a result?** Yes, via `ScheduledFuture<T>`; the requested delay does not guarantee an exact execution timestamp.
7. **When should `execute(Runnable)` be used instead of `submit(Runnable)`?** When no Future handle is needed and you want to delegate work under the `Executor` contract; if you need to wait for completion or inspect errors, `submit` is more appropriate.
8. **Why should you not call `Future.get()` on a queued task from inside the sole worker of the same executor?** The worker will block while the other task cannot be executed yet.

## References

- [Java SE 17: Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html)
- [Java SE 17: Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html)
- [Java SE 17: ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17: Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17: FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17: ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)

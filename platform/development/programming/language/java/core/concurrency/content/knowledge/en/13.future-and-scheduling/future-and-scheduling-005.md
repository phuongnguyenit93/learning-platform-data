# ExecutionException and Task Error Tracing in Java Concurrency

## 1. Why does a task fail without the calling thread receiving the exception immediately?

When calling a synchronous Java method, an exception can propagate up the call stack of **the calling thread itself**:

```java
String value = parseData(input); // May throw an exception right here.
```

However, with `ExecutorService`, the task runs on **another worker thread**. The submitting thread and the worker do not share a call stack. If the task throws an exception, that exception **does not automatically jump over** to the thread that called `submit()`.

Java provides `Future` to hold the **completion status** and result of a task. When another thread calls `Future.get()`, the API can **wrap the error thrown by the task** inside an `ExecutionException`, delivering the error information back to the caller.

```text
Submitting thread                  Worker thread
------------------                 ------------------
executor.submit(callable)  ───────> callable.call()
          │                             │
          │                         throw IOException
          │                             │
          ▼                             ▼
Future<T>                       Future stores failure
          │                             │
future.get()  <────────────────────────┘
          │
          ▼
throw ExecutionException
       └── getCause() -> original IOException
```

**`ExecutionException` is a wrapper indicating that task execution failed**, not the name of every concurrency error. It differs from `InterruptedException` when the waiting thread is interrupted, `TimeoutException` when waiting exceeds the deadline, and `CancellationException` when the future has been cancelled.

This lesson belongs to **Future & Scheduling**, covering **Java concurrency in general**, without framework dependencies.

## 2. Three roles: caller, executor, and Future

Responsibilities can be divided as follows:

1. **Caller:** creates/submits the task; holds the `Future`; decides when to wait and how to handle success or failure.
2. **Executor:** accepts the task and schedules a worker to execute it; does not necessarily return task errors directly at `submit()`.
3. **Future:** allows tracking completion status, retrieving the result on success, or tracing the error on failure/cancellation.

`submit(Callable<T>)` returns `Future<T>`. `submit(Runnable)` returns `Future<?>` whose `get()` normally returns `null` if the task completes successfully. Specifically, `submit(Runnable, T result)` can return a caller-supplied value after the `Runnable` completes normally.

### Important exceptions of Future.get()

| State when calling `Future.get()` | Common behavior |
| --- | --- |
| Task succeeds | Returns the value (may be `null` for `Runnable`) |
| Task throws an unhandled exception or error | Throws `ExecutionException`, `getCause()` is the stored error |
| Task/Future has been cancelled | Throws `CancellationException` (unchecked) |
| **Waiting** thread is interrupted | Throws `InterruptedException` |
| `get(timeout, unit)` expires | Throws `TimeoutException` |
| Task is still running and no timeout is set | `get()` may wait indefinitely |

**Do not confuse:** `Future.get()` does not send an interrupt simply because the caller waits a long time. `TimeoutException` does not cancel the task either: the task may continue running after the caller stops waiting.

A `get()` call can throw `InterruptedException` even when **the task is completely normal**, because the thread being interrupted is the one **waiting for the result**. That is not evidence that the worker failed.

## 3. Java 17+ Example: tracing an IOException inside ExecutionException

Create the file `ExecutionExceptionBasicsDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutionExceptionBasicsDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<String> result = executor.submit(() -> {
                throw new IOException("cannot read report.csv");
            });

            try {
                System.out.println(result.get());
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println("wrapper="
                        + e.getClass().getSimpleName());
                System.out.println("cause="
                        + cause.getClass().getSimpleName());
                System.out.println("message=" + cause.getMessage());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac ExecutionExceptionBasicsDemo.java
java ExecutionExceptionBasicsDemo
```

Output when there is no external interrupt request:

```text
wrapper=ExecutionException
cause=IOException
message=cannot read report.csv
```

Explanation:

- `submit()` returns `Future<String>`; the lambda is a `Callable` because the task has a return type and throws `IOException`.
- The worker executes `call()` and throws `IOException`.
- The `Future` records the failure state. When the caller invokes `result.get()`, it receives `ExecutionException`.
- `getCause()` returns the original `IOException` so the caller can identify the file-reading issue.
- `finally` requests shutting down the executor whether `get()` throws or handles the error; `awaitTermination` checks whether it terminates within the deadline.

**Do not only inspect `e.getMessage()` of the wrapper.** Useful domain details usually reside in `e.getCause()` and the entire cause chain. In real systems, you should still preserve the original stack trace and task information to locate the line of code that caused the error.

## 4. `getCause()`, cause chain, and root cause

An error can be wrapped across multiple layers:

```text
ExecutionException
  └── IllegalStateException("processing failed")
        └── IllegalArgumentException("invalid orderId")
```

Typically:

- **Wrapper:** the exception signaling that an error crossed an asynchronous boundary, such as `ExecutionException`.
- **Direct cause:** the throwable thrown by the task or wrapped by a business layer.
- **Root cause:** the deepest error in the cause chain, if there is a continuous chain of `getCause()`.
- **Suppressed exceptions:** other errors attached via `addSuppressed()`, commonly seen when resource `close()` also fails; they **do not belong to the linear cause chain**.

### Example 2: inspecting each layer of the error chain

Create the file `ExecutionCauseChainDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutionCauseChainDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Void> task = executor.submit(() -> {
                try {
                    throw new IllegalArgumentException("invalid orderId");
                } catch (IllegalArgumentException e) {
                    throw new IllegalStateException("processing failed", e);
                }
            });

            try {
                task.get();
            } catch (ExecutionException e) {
                Throwable direct = e.getCause();
                Throwable root = direct.getCause();

                System.out.println("direct="
                        + direct.getClass().getSimpleName());
                System.out.println("direct message=" + direct.getMessage());
                System.out.println("root="
                        + root.getClass().getSimpleName());
                System.out.println("root message=" + root.getMessage());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac ExecutionCauseChainDemo.java
java ExecutionCauseChainDemo
```

Output when there is no unexpected interrupt:

```text
direct=IllegalStateException
direct message=processing failed
root=IllegalArgumentException
root message=invalid orderId
```

In this example, `IllegalStateException` is the **nearest** business context thrown by the task, while `IllegalArgumentException` is the lower-level error chained via the constructor `new IllegalStateException(message, cause)`.

**The "root cause" is not always sufficient to decide how to handle the error.** Sometimes higher layers add critical information (task ID, processing step, retry conditions). Do not discard `IllegalStateException("processing failed")` just because you found `IllegalArgumentException`.

### Safely traversing the cause chain

An illustrative helper:

```java
static Throwable deepestCause(Throwable throwable) {
    Throwable current = throwable;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
```

This is an **illustrative method snippet**, without `main`. In general diagnostic code, you may need to guard against abnormal circular cause chains (for example, via custom throwables) to avoid an infinite loop. `printStackTrace()` already has built-in formatting for causes and suppressed exceptions; it is usually more effective than manually concatenating only the root message.

## 5. Preserving the stack trace instead of printing only a single message line

When a worker fails, tracing requires knowing **the error type, location, context, and call path**. A useful pattern:

```java
try {
    future.get();
} catch (ExecutionException e) {
    Throwable failure = e.getCause();
    logger.error("Task {} failed", taskId, failure);
}
```

This is **logging integration pseudocode**, where `future`, `taskId`, and `logger` are defined by the application. A proper logger can record the full stack trace of `failure`; passing `e` intact also preserves the cause chain.

With plain Java, you can use:

```java
failure.printStackTrace(System.err);
```

However, stack trace output depends on file names, line numbers, lambdas, JDK version, and compilation, so **do not fabricate fixed output**. When you want an exact demo, print `getClass().getSimpleName()` and `getMessage()`; when debugging in practice, keep **the entire throwable**, not just a string.

Logging recommendations:

- Record the task type, task ID or correlation ID, submission/execution time, and worker name when helpful.
- Record the wrapper and cause chain, especially the underlying error along with its stack trace.
- Use a log level proportional to whether the error is expected or abnormal.
- Do not log sensitive data (tokens, passwords, private content) just to add context.
- Do not automatically retry upon seeing an exception without considering side effects the task has already performed.

## 6. How `submit()` differs from `execute()` in observing exceptions

`ExecutorService` inherits `execute(Runnable)` and adds `submit(...)`.

**`submit()`:** returns a `Future`. In standard executors such as `ThreadPoolExecutor`, the task is typically wrapped in a `RunnableFuture` (for example, `FutureTask`) that holds either the result or the throwable. If the `Runnable`/`Callable` fails, the exception is stored for the caller to retrieve via `Future.get()`; that error does not necessarily appear directly at the worker's `UncaughtExceptionHandler`.

**`execute()`:** does not return a `Future`. If a `Runnable` throws an uncaught exception, the worker thread may terminate abnormally and the exception goes through the thread/runtime uncaught exception mechanism, depending on the executor. With `ThreadPoolExecutor`, the error from the task propagates out of `run()` and the worker may be replaced if the pool is still running. There is no `Future.get()` for the caller to retrieve the error directly.

Comparison table:

| Criterion | `execute(Runnable)` | `submit(Runnable/Callable)` |
| --- | --- | --- |
| Return value | `void` | `Future<?>` or `Future<T>` |
| Caller retrieves result | No `Future` from the call | `get()` |
| Caller traces task exception | Requires logging, handler, or another error-reporting protocol | `get()` throws `ExecutionException` |
| Cancelling an individual task | Requires another mechanism/handle | `Future.cancel(...)` |
| Risk if ignored | Task failure is not reported to the caller | `Future` stores the error, but **if `get()` is not called, the caller may never know** |

**Do not say "`submit` swallows exceptions" in the sense of erasing the error.** It **stores the throwable in the `Future`** and delivers it to the caller via `get()`. If code submits a task and forgets the `Future`, the error easily goes unobserved — that is a result-monitoring design issue.

### Anti-pattern: submitting and discarding the Future

```java
executor.submit(() -> {
    throw new IllegalStateException("failed");
});
// Ignoring the Future: the caller does not read the task status.
```

This is an illustrative snippet. Do not treat "no exception on the caller thread" as proof that the task succeeded.

A good design keeps the `Future` in the layer responsible for checking the outcome, or establishes an explicit error-reporting path via callbacks, channels, or application monitoring.

## 7. Example 3: multiple Futures, not missing a single task's failure

A common mistake is submitting dozens of tasks and only calling `get()` on one of them. The remaining `Future`s may fail without being recorded.

Create the file `MultipleTaskFailuresDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultipleTaskFailuresDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> good = executor.submit(() -> 7);
            Future<Integer> bad = executor.submit(() -> {
                throw new IllegalStateException("bad order");
            });

            List<Future<Integer>> futures = List.of(good, bad);
            for (int i = 0; i < futures.size(); i++) {
                try {
                    System.out.println("task " + i
                            + " result=" + futures.get(i).get());
                } catch (ExecutionException e) {
                    Throwable cause = e.getCause();
                    System.out.println("task " + i + " failed="
                            + cause.getClass().getSimpleName()
                            + ": " + cause.getMessage());
                }
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac MultipleTaskFailuresDemo.java
java MultipleTaskFailuresDemo
```

Output when there is no unexpected interrupt:

```text
task 0 result=7
task 1 failed=IllegalStateException: bad order
```

Completion order on the workers **does not necessarily match submission order**, but the caller iterates through `futures` by index `0` then `1`; therefore, the log line order is deterministic. `get()` waits for each `Future` to complete and then reads its result or failure.

**Limitation of sequential iteration:** if the first `Future` is slow, the caller may block waiting for it even though a later `Future` has already failed. When you need to process results **in completion order** rather than submission order, you can use `ExecutorCompletionService`.

## 8. `ExecutorCompletionService` for observing results in completion order

`ExecutorCompletionService<V>` accepts `Callable<V>` tasks and places completed `Future`s onto a completion queue. The caller invokes `take()` to retrieve the `Future` of a task that **has finished** (succeeded, failed, or was cancelled) and then calls `get()` to distinguish the outcome.

Illustrative pattern:

```java
ExecutorCompletionService<String> completed =
        new ExecutorCompletionService<>(executor);

completed.submit(() -> fetchA());
completed.submit(() -> fetchB());

for (int i = 0; i < 2; i++) {
    Future<String> future = completed.take();
    try {
        String value = future.get();
        consume(value);
    } catch (ExecutionException e) {
        reportFailure(e.getCause());
    }
}
```

This is an illustrative snippet assuming `import java.util.concurrent.*` and definitions for `executor`, `fetchA`, `fetchB`, `consume`, and `reportFailure`. Retrieval order may vary between runs, so fixed stdout is not shown.

The advantage is that a fast task is not blocked from being observed while the caller waits on a slow task **earlier in the list**. However, the code still must:

- Know the number of submitted tasks or have a termination protocol.
- Handle both `CancellationException` and `InterruptedException` appropriately.
- Have a policy to cancel remaining tasks if a critical error occurs.
- Manage the executor's lifecycle.
- Prevent the completion queue or `Future` collection from growing unboundedly if the producer is faster than the consumer.

`ExecutorCompletionService` helps **collect outcomes**; it does not turn a task exception into a successful result.

## 9. TimeoutException, InterruptedException, and CancellationException differ from ExecutionException

One of the most diagnostically confusing mistakes is lumping every `get()` failure together as "the task threw an exception."

### `TimeoutException`

`future.get(100, TimeUnit.MILLISECONDS)` throws `TimeoutException` if the wait deadline expires before the `Future` completes. That does not mean the task errored or was cancelled. The task may continue running after the timeout.

### `InterruptedException`

The thread **waiting on `get()`** was interrupted. The task itself may still be running normally. If you cannot propagate it, restore the interrupt flag and exit the workflow at a safe point. Do not confuse interrupting the caller thread with an original exception thrown by the worker.

### `CancellationException`

The `Future` was cancelled, so `get()` throws `CancellationException`. A task that already started may still be cleaning up or still running if it does not cooperate with interruption; `isCancelled()` alone does not prove that all cleanup has finished.

### `ExecutionException`

The task completed abnormally because it threw a `Throwable` during execution. `getCause()` contains the error thrown by the task (or an error wrapped by the task layer). Do not handle it as a timeout or cancellation without evidence.

### Suggested response table

| Exception from `get()` | Meaning | Reasonable handling |
| --- | --- | --- |
| `ExecutionException` | Task failed | Trace `getCause()`, log stack trace, classify retry/fail |
| `TimeoutException` | Waiting for result took too long | Decide whether to wait longer, cancel, or return timeout to caller |
| `InterruptedException` | Waiting caller was interrupted | Propagate or restore interrupt flag, clean up workflow |
| `CancellationException` | `Future` was cancelled | Confirm cancellation state, handle cleanup/outcome if needed |

## 10. Example 4: timing out does not mean the task failed

Create the file `FutureTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> task = executor.submit(() -> {
                started.countDown();
                release.await();
                return "OK";
            });

            started.await();
            try {
                task.get(50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("caller timed out");
            }

            release.countDown();
            System.out.println("later result=" + task.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Output when there is no external interrupt:

```text
caller timed out
later result=OK
```

Why the output is deterministic:

- The task signals `started` and then waits on `release`, so it **cannot complete yet** when the caller tries `get(50ms)`.
- The timeout causes `get` to throw an exception **in the caller**, but it **does not cancel** the task.
- `main` opens `release`; the task continues and returns `"OK"`.
- The subsequent `get()` call receives the successful result.

`finally` opens `release` even if an exception occurs, preventing the worker from getting stuck if the caller exits early. `shutdownNow()` in this example is only to clean up the executor; in systems requiring graceful shutdown, you can use `shutdown()` and fall back according to your own policy.

## 11. What memory guarantees does `Future.get()` provide?

`Future` does more than store a result. The Java concurrency API defines an important memory consistency rule: **actions taken by the asynchronous computation happen-before actions following the retrieval of that result via `Future.get()` in another thread**, as specified by the `Future` contract.

For example, if a task writes to a result object before completing, the caller—after `get()` returns successfully—has a memory relationship to observe the writes published through this path.

However, avoid overgeneralizing:

- `get()` does not make a mutable object that continues to be modified by multiple threads thread-safe.
- `get()` does not turn two state reads from two different versions into an atomic snapshot.
- If a task fails midway through multiple non-transactional updates, `ExecutionException` does not roll back the updates that already occurred.
- If the caller does not wait/call `get()` and instead reads shared state through an unsynchronized path, a different memory visibility protocol is required.

For new designs, prefer constructing a complete immutable result/DTO inside the task and returning it via `Future`. Readers do not mutate the result, and the worker does not continue mutating it after returning.

## 12. `CompletableFuture`: `get()` and `join()` wrap errors differently

`CompletableFuture<T>` is both a `Future<T>` and supports asynchronous composition. Two common waiting methods:

- `future.get()`: declares checked exceptions `InterruptedException` and `ExecutionException` (when computation fails).
- `future.join()`: declares no checked exceptions; when completion fails, it typically throws **`CompletionException`** (unchecked).
- If the `Future` was cancelled, both `get()` and `join()` can throw `CancellationException` directly.
- Callbacks such as `exceptionally`, `handle`, and `whenComplete` can handle or observe failures without calling `get` at every stage.

The error inside `CompletionException` is also usually found at `getCause()`. In complex chains, `CompletionException`/`ExecutionException` may be wrapped across multiple layers; do not assume the cause is always exactly one level deep.

### Example 5: the same error through `get` and `join`

Create the file `CompletableFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class CompletableFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> future = new CompletableFuture<>();
        future.completeExceptionally(
                new IllegalArgumentException("bad input"));

        try {
            future.get();
        } catch (ExecutionException e) {
            System.out.println("get wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("get cause="
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            future.join();
        } catch (CompletionException e) {
            System.out.println("join wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("join cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac CompletableFailureDemo.java
java CompletableFailureDemo
```

Output:

```text
get wrapper=ExecutionException
get cause=IllegalArgumentException
join wrapper=CompletionException
join cause=IllegalArgumentException
```

There is no thread race in this example because the `Future` is already completed exceptionally before calling either method. The example simply demonstrates **two wrapper types** of different waiting APIs.

With complex asynchronous stages, an error may propagate through `CompletionException` in the middle of the chain, while `get()` still wraps according to the `Future` contract. The way to trace it is to inspect **the full cause chain**, rather than rigidly expecting a single wrapper layer.

## 13. Using `exceptionally`, `handle`, and `whenComplete` for the right purpose

When using `CompletableFuture`, you can handle errors via a pipeline instead of waiting and catching everywhere.

```java
CompletableFuture<Integer> recovered = operation
        .exceptionally(error -> {
            report(error);
            return 0;
        });
```

This is an illustrative snippet, where `operation` is a `CompletableFuture<Integer>` and `report` is application-defined. `exceptionally` can **turn a failed completion into a default result**. This approach is only appropriate when a fallback of `0` is a valid business contract — otherwise, it masks the error and produces incorrect data.

`handle((value, error) -> ...)` receives both success and failure states to produce a new result. `whenComplete((value, error) -> ...)` is primarily used to **observe** the outcome and normally preserves the original result/exception if the callback itself does not throw; it should not be treated as a default recovery mechanism.

### Example 6: classifying an error before an intentional fallback

Create the file `CompletableRecoveryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class CompletableRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        source.completeExceptionally(
                new IllegalArgumentException("invalid quantity"));

        int result = source.exceptionally(error -> {
            Throwable cause = error.getCause() != null
                    ? error.getCause() : error;
            System.out.println("handled="
                    + cause.getClass().getSimpleName());
            return -1;
        }).join();

        System.out.println("result=" + result);
    }
}
```

```bash
javac CompletableRecoveryDemo.java
java CompletableRecoveryDemo
```

Output:

```text
handled=IllegalArgumentException
result=-1
```

`-1` is only an **illustrative fallback**, not a recommendation to use `-1` for every error. A real system might return a `Result<T>` type holding success/error, propagate the throwable, or retry according to policy. The key is not to invoke recovery blindly and ignore the original failure.

### Be careful when using `exceptionally` with side effects

A recovery callback may run on another thread or on the thread that triggers completion, depending on how the stage is constructed. If the callback writes logs, updates shared data, or calls another API, you still need to understand the thread safety of that operation. `CompletableFuture` does not eliminate synchronization requirements on external mutable objects.

## 14. `ScheduledExecutorService`: errors in periodic tasks

`ScheduledExecutorService` also uses `ScheduledFuture<?>`. For a one-shot scheduled task, `future.get()` can return the result or throw `ExecutionException` if the task throws an error.

For periodic tasks scheduled with `scheduleAtFixedRate` or `scheduleWithFixedDelay`, there is a very important difference:

> If one execution of a periodic task throws an unhandled exception, subsequent executions of **the same scheduled task** are suppressed according to the `ScheduledThreadPoolExecutor`/`ScheduledExecutorService` contract. The periodic task's `Future` may complete abnormally.

Because a normal periodic task can run repeatedly until cancelled, `get()` on its future normally **does not return successfully** while the repetition loop is active. It can complete abnormally due to an exception or cancellation.

### Example 7: tracing a periodic task failure

Create the file `ScheduledTaskFailureDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ScheduledTaskFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicInteger runs = new AtomicInteger();

        try {
            ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
                    () -> {
                        int n = runs.incrementAndGet();
                        throw new IllegalStateException("failed at run " + n);
                    },
                    0, 1, TimeUnit.SECONDS);

            try {
                future.get();
            } catch (ExecutionException e) {
                System.out.println("cause="
                        + e.getCause().getClass().getSimpleName());
                System.out.println("message=" + e.getCause().getMessage());
            }

            System.out.println("runs=" + runs.get());
        } finally {
            scheduler.shutdownNow();
            scheduler.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ScheduledTaskFailureDemo.java
java ScheduledTaskFailureDemo
```

Output when there is no unexpected interrupt:

```text
cause=IllegalStateException
message=failed at run 1
runs=1
```

The first run increments `runs` to `1` and throws `IllegalStateException`; the periodic future completes with a failure, and subsequent runs do not proceed. The caller calling `get()` receives `ExecutionException` and traces it via `getCause()`.

**Common risk:** a failing scheduled task can **stop running periodically** while the rest of the application remains alive. If you do not retain the `ScheduledFuture` or have an error-reporting path, the system can silently stop its scheduled work.

If you want a task to continue after a recoverable business error, the task can **catch and handle that specific error** at each iteration's boundary. However, never swallow every `Throwable` unconditionally: severe errors, invalid state, or shutdown requests may require stopping, reporting the failure, or restarting the component according to policy.

## 15. `invokeAll` and `invokeAny`: where do errors live?

`ExecutorService.invokeAll(tasks)` typically returns a list of `Future`s corresponding to the callables after they complete according to the contract. **Returning the list does not mean every callable succeeded.** You must iterate and call `get()` on each `Future` to check for errors.

```java
List<Future<Integer>> futures = executor.invokeAll(tasks);
for (Future<Integer> future : futures) {
    try {
        consume(future.get());
    } catch (ExecutionException e) {
        reportFailure(e.getCause());
    }
}
```

This is an illustrative snippet assuming `import java.util.concurrent.*` and `java.util.List`; `tasks`, `consume`, and `reportFailure` are application-defined.

With `invokeAll(timeout, unit)`, tasks that have not completed when the timeout expires may be cancelled according to the contract; their `get()` may throw `CancellationException`, **not necessarily `ExecutionException`**.

`invokeAny(tasks)` has a different goal: it returns the result of **one task that completed successfully**. If no task completes successfully (and no other interrupt/timeout condition governs), it may throw `ExecutionException`. One task in the group failing **does not necessarily cause `invokeAny` to fail** if another task succeeds.

Do not mistakenly assume `invokeAll` = "all results succeeded" or `invokeAny` = "the result of the first task to finish regardless of failure." Always read each API's contract.

## 16. Task exceptions can be RuntimeException, checked Exception, or Error

A `Callable<T>` declares `T call() throws Exception`, so it can throw checked exceptions like `IOException`. A `Runnable` cannot declare checked exceptions on `run()`, yet it can still throw an uncaught `RuntimeException` or `Error`.

When submitted via `submit()` and the task fails, `ExecutionException.getCause()` can be:

- `IOException` thrown by `Callable`.
- `IllegalArgumentException`, `IllegalStateException`, `NullPointerException`, or another runtime exception.
- An `Error` such as `AssertionError`, `OutOfMemoryError`, or other severe errors.

Do not write `catch (Exception e)` and assume every error is safe to retry. An `Error` usually signals a serious problem requiring operational handling rather than "retrying a few times." `ExecutionException` is a checked exception, but **its cause is a `Throwable`**; classification code must account for the fact that it might not be a subclass of `Exception`.

Do not invent a rule that every `Error` forces the JVM to die immediately: `FutureTask` can record an `Error` as the task's outcome. Even so, whether continuing the application after a severe error is safe depends on the specific cause and the JVM's state.

## 17. Tracing errors without losing context

A good strategy is to classify based on the **cause** and preserve the **wrapper/context** in logs or higher-level exceptions:

```java
try {
    return future.get();
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    throw new TaskFailedException(taskId, cause);
}
```

This is an illustrative snippet, where `TaskFailedException` and `taskId` are application-defined. A new exception carrying the original cause gives upper layers the task ID without losing the trace path.

When writing your own wrapper:

```java
throw new IllegalStateException("load config failed", original);
```

is better than:

```java
throw new IllegalStateException("load config failed");
```

if you want to preserve the underlying error. The second form loses the cause chain unless another mechanism records it.

Do not take only `cause.getMessage()` and build an exception without a cause. A message alone is insufficient to distinguish error types and does not preserve the stack trace. For multi-layered errors, keep suppressed exceptions as well when logging in full.

### Should you unwrap and rethrow the cause?

Sometimes an upper-layer API wants to rethrow the exact `IOException` or a specific exception. However, `ExecutionException.getCause()` has type `Throwable`; you cannot arbitrarily throw it from a method that only declares restricted checked exceptions. **Classify** intentionally or use a domain wrapper with a cause:

```java
Throwable cause = e.getCause();
if (cause instanceof java.io.IOException io) {
    throw io;
}
throw new IllegalStateException("task failed", cause);
```

This is an illustrative snippet inside a method that can declare `throws IOException`; `e` is the caught `ExecutionException`. Pattern matching for `instanceof` is supported on Java 17.

Do not catch every `Throwable` and turn it into an "OK" result or retry indefinitely. Errors like `OutOfMemoryError` can make recovery unreliable.

## 18. Classifying errors for safe retries

A task failure does not mean retrying is always right. Consider **repeatability** and partial success:

| Scenario type | Is immediate retry reasonable? | What to check |
| --- | --- | --- |
| Transient network error while reading a resource | Possibly, with limits/backoff | Timeout, idempotency, whether the resource is still valid |
| Malformed input data | Usually no | Validation, return a clear error |
| Database write failed midway through multiple steps | Only with transactions/reconciliation | Did a partial commit already happen? |
| Task was cancelled | Usually do not retry blindly | Who cancelled it, cancellation reason |
| Caller `get(timeout)` expired | Do not infer worker failure | Is the task still running? Should it be cancelled? |
| Severe JVM `Error` | Usually needs dedicated operational handling | Are process/resource states still safe? |

For example, a task calls a payment API; the API commits, but the response is lost; the worker throws a timeout exception and the `Future` returns `ExecutionException`. Retrying without idempotency could charge twice. Thus, **the cause chain is diagnostic data**, not a substitute for checking transaction state.

Apply retry limits, backoff, deadlines, circuit breakers where appropriate, and rules against executing side effects twice.

## 19. Handling InterruptedException while waiting on a Future

If the caller thread is interrupted during `Future.get()`, the method can throw `InterruptedException` and stop waiting. In many interruptible APIs, the interrupt flag is cleared when the exception is thrown; valid handling is typically:

**Propagate if the API allows:**

```java
String read(Future<String> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
```

**Or restore the flag and exit the wait path:**

```java
try {
    String value = future.get();
    consume(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException e) {
    report(e.getCause());
}
```

These are two illustrative snippets; `consume` and `report` are application-defined. `InterruptedException` is about **the caller thread**, and does not by default mean the task failed. Depending on policy, the caller may call `future.cancel(true)` to request that the worker stop, understanding that interrupting a worker is best-effort.

**Do not swallow the signal:**

```java
try {
    future.get();
} catch (InterruptedException ignored) {
    // Ignoring and looping indefinitely: loses cancellation capability.
}
```

This is an anti-pattern. If you must keep waiting despite interruption, that must be an intentional decision with a deadline and restoring the flag on exit. Especially during application shutdown, ignoring interrupts easily causes workers/callers to hang.

## 20. Cancelling a Future and task cleanup

`Future.cancel(true)` can request interrupting a running task. Once a `Future` is marked cancelled, `future.get()` throws `CancellationException` instead of `ExecutionException` for that branch. Even so:

- The task may not have started yet: cancellation prevents it from running.
- The task is running: an interrupt request is sent if the implementation supports it; the task may cooperate and stop.
- The task ignores interrupts: the code may continue running after the `Future` is already cancelled.
- The task has a `finally` block releasing files/locks/sockets: a cancelled `Future` **does not prove `finally` has finished running**.

If you need to know that cleanup has actually completed, use a separate signal such as a `CountDownLatch` in `finally` or wait for the executor lifecycle per contract. `Future.get()` after cancellation can throw `CancellationException` immediately, so it is not a reliable "cleanup join" for that task.

The same applies to `ExecutorService.shutdownNow()`: it is a best-effort stop request, not an instant conversion of arbitrary tasks into a safely terminated state.

## 21. Observing exceptions at the right time

There are three distinct moments:

1. **Task submission (`submit`):** the task may not have run yet; `submit()` usually just returns a `Future`. Errors from *failing to accept the task*, such as `RejectedExecutionException`, can occur right at submission time, **not as an `ExecutionException` wrapped inside a `Future`**.
2. **Task execution (worker):** the task may succeed, fail, or be cancelled; the status is recorded by the `Future`/handler.
3. **Result observation (`get`/callback):** the caller receives the outcome or exception when it decides to observe it.

This explains why:

```java
Future<Integer> f = executor.submit(() -> 1 / 0);
// submit() can return a Future normally.
f.get(); // ExecutionException containing ArithmeticException.
```

This is an illustrative snippet, assuming `executor` is already created and the caller handles checked exceptions. It does not mean the exception "occurred at `get`" inside the worker: the arithmetic error happened when the task executed, whereas `get()` is **the moment the error is reported back to the caller**.

### When should you log at the worker?

For fire-and-forget tasks, if no one holds the `Future`, there must be an active mechanism to report failures: logging at the task boundary, a callback, a supervisor, or a centralized result path. Do not log the same `Throwable` multiple times at every layer and create noise. You can designate one layer to own error reporting, preserving the cause chain and correlation ID.

## 22. Errors inside callbacks are also task errors

With `CompletableFuture`, one stage can succeed while a callback processing its result throws an error:

```java
CompletableFuture<Integer> mapped =
        CompletableFuture.completedFuture(3)
                .thenApply(value -> {
                    throw new IllegalStateException("mapping failed");
                });
```

This is an illustrative snippet. The source `Future` succeeds with the value `3`, but the `mapped` stage fails. If you only check the source `Future`, you will **not see the failure of the subsequent stage**. Each stage produces a new completion/outcome.

A chain of stages can have multiple wrapper layers, so record:

- Which stage failed, the step name, and the data key (without secrets).
- The cause and stack trace at that step.
- Where fallbacks (`exceptionally`) are created and where errors still propagate.
- Which final completion stage the caller actually waits on.

`whenComplete` is used to observe the outcome, but its callback can also throw an exception, altering the downstream state according to the contract. Do not assume a "logging-only" callback can never affect the result if it is capable of throwing.

## 23. Common mistakes when handling ExecutionException

### Mistake 1 — Catching ExecutionException and ignoring the cause

```java
catch (ExecutionException e) {
    System.out.println("failed");
}
```

This loses diagnostic context. Inspect `e.getCause()` and preserve the stack trace appropriately.

### Mistake 2 — Catching and unconditionally returning a default result

A serious data error can be turned into `0` or an empty list that the caller assumes is valid. Fallbacks must follow **a business contract**, not be a way to evade exceptions.

### Mistake 3 — Calling `submit` and forgetting the `Future`

The `Future` holds the failure; if unread, the caller may miss the error. Someone must own collecting results, or there must be a supervisor/logging mechanism.

### Mistake 4 — Confusing `TimeoutException` with `ExecutionException`

A timeout says the caller waited past the deadline; it does **not** prove the worker failed. If needed, check `isDone()`, decide whether to cancel, and inspect the outcome when the task actually completes.

### Mistake 5 — Confusing `CancellationException` with the task's original error

A cancelled `Future` has its own semantics; `get()` throws `CancellationException`. Do not report that the worker threw a business exception.

### Mistake 6 — Swallowing `InterruptedException`

A caller interrupted while waiting that keeps looping `get()` indefinitely can stall shutdown. Propagate or restore the flag and exit at a safe point.

### Mistake 7 — Calling `Future.get()` inside a single-worker pool to wait for a child task in the same pool

If the sole worker of a single-thread executor submits a child task to the same pool and waits on `get()`, the child task has no worker to run on: **thread-starvation deadlock**. `ExecutionException` cannot rescue a circular wait. Avoid circular dependencies, use a different task architecture, or use an executor with appropriate execution capacity.

### Mistake 8 — Assuming `execute` and `submit` report exceptions the same way

`submit` records errors in a `Future`; `execute` does not return a `Future`. Relying on `UncaughtExceptionHandler` to see errors from all `submit`ted tasks can miss them.

### Mistake 9 — Logging the message without keeping the cause

A single `e.getMessage()` is not enough to see where it happened or what error was wrapped. Log the throwable with its stack trace and cause, and consider suppressed exceptions.

### Mistake 10 — Retrying tasks with side effects without checking commits

The task may have already written to a database or sent a message before throwing an exception. Blind retries easily create duplicate side effects.

### Mistake 11 — Not observing errors from repeating scheduled tasks

One periodic task run throwing an exception can prevent all subsequent runs. Without holding the `ScheduledFuture` or having monitoring, the schedule can stop without anyone noticing.

## 24. Tracing checklist when an asynchronous task fails

When receiving `ExecutionException` or a `CompletableFuture` stage failure, check:

1. **Task name and ID:** which task, which input/correlation, which worker executed it?
2. **Submission API:** `submit`, `execute`, `schedule`, `invokeAll`, or which `CompletableFuture` stage?
3. **Waiting API:** `get()`, `get(timeout)`, `join()`, or callback? Wrappers may differ.
4. **Outcome type:** task failure (`ExecutionException`/`CompletionException`), caller interrupted, timeout, or cancelled?
5. **Direct cause:** what type is `getCause()`? What is its message?
6. **Cause chain:** which layer created the wrapper, which added context, and what root cause is actually useful?
7. **Suppressed errors:** are there secondary cleanup errors?
8. **Stack trace:** which method did the error start in? What are the worker call path and related stages?
9. **Side effects:** what state or resources did the task modify before failing? Is it safe to retry?
10. **Monitoring:** who holds the `Future`, who logs the failure, and are there metrics by error type?
11. **Lifecycle:** is the executor/scheduler still alive, shut down, or has a periodic task stopped running?
12. **Policy:** propagate, fall back, retry, cancel remaining tasks, or translate into a domain error?

The essence of `ExecutionException` is transporting an error across an asynchronous boundary. **Proper diagnosis** also requires knowing when and where the task was submitted, and what state the error affected.

## 25. Knowledge self-check

**Question 1.** A `Callable` throws `IOException`; the caller thread calls `future.get()`. What exception type does the caller typically receive?

**Answer:** `ExecutionException`; `getCause()` is the `IOException` thrown by the task.

**Question 2.** If you only call `executor.submit(task)` without keeping the `Future` or observing the outcome, can errors be missed?

**Answer:** Yes. The error is stored in the task's `Future`, but the caller does not automatically receive an exception at `submit()`.

**Question 3.** Does `future.get(100, MILLISECONDS)` throwing `TimeoutException` mean the task has definitely failed?

**Answer:** No. The task may still be running and complete later.

**Question 4.** Is `future.get()` throwing `InterruptedException` an error thrown by the task or caused by the waiting thread?

**Answer:** It is a signal that **the thread calling `get()` was interrupted**. Do not automatically infer that the task failed.

**Question 5.** When a `Future` has been cancelled, which exception does `get()` typically throw?

**Answer:** `CancellationException`, an unchecked exception, not `ExecutionException`.

**Question 6.** How do `CompletableFuture.get()` and `CompletableFuture.join()` wrap errors differently?

**Answer:** `get()` typically throws checked `ExecutionException`, while `join()` typically throws unchecked `CompletionException`. In both cases, inspect the cause.

**Question 7.** Why is `IllegalStateException("processing failed", cause)` better than omitting the cause?

**Answer:** It preserves the cause chain to trace back to the original error and stack trace, while adding business context.

**Question 8.** If a periodic task's `ScheduledFuture` receives `ExecutionException` because one run threw an error, will subsequent runs continue normally?

**Answer:** With standard `scheduleAtFixedRate`/`scheduleWithFixedDelay`, an abnormal failure in one periodic run suppresses subsequent runs of that same task.

**Question 9.** Does `ExecutorService.invokeAll` returning a list of `Future`s prove that all tasks succeeded?

**Answer:** No. You must call `get()` on each `Future` to distinguish success, exception, or cancellation.

**Question 10.** What JMM meaning does `Future.get()` have after a task succeeds?

**Answer:** Actions of the computation before completion happen-before actions of the caller after retrieving the result under the `Future` contract; it does not replace synchronization for subsequent modifications to shared mutable state.

**Question 11.** A task wrote to the database but threw an exception when sending the response. Should you retry immediately from the beginning?

**Answer:** Not without checking commit/idempotency; retrying could duplicate side effects.

**Question 12.** Why shouldn't you log only the root cause and discard business-layer wrappers?

**Answer:** Wrappers may contain important context: step name, task ID, processing state, and retry rules. You need to look at the entire cause chain.

## 26. Summary

`ExecutionException` is **the mechanism for reporting asynchronous task failures through `Future.get()`**. When encountering it, the first step is **`getCause()`**, followed by preserving and reading **the full cause chain, stack trace, task context, and any side effects that may have occurred**.

Distinguish clearly between: **task failure** (`ExecutionException`), **caller timeout** (`TimeoutException`), **caller interrupted while waiting** (`InterruptedException`), and **cancelled Future** (`CancellationException`). With `CompletableFuture`, `join()` typically uses `CompletionException`; with scheduled periodic tasks, an unhandled error can suppress subsequent runs.

For a reliable system, do not just submit tasks—establish **Future/outcome ownership**, logging/propagation/retry rules, clear timeouts/cancellations, and executor lifecycle handling. Wrapped exceptions do not lose the original error if we **preserve `getCause()` and observe at the right layer**, nor do they automatically resolve partially failed transactions or uncleaned resources.

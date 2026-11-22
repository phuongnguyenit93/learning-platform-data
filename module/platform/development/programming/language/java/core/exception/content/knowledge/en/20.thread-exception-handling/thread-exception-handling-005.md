# Differences Between `Executor.execute()` and `ExecutorService.submit()` When a Task Fails

In Java multithreaded programming, a task may be submitted to an executor yet throw an exception while running. Both `execute()` and `submit()` can be used to hand off a `Runnable` to an executor; the key difference is **the error propagation path and how the program detects the failure**. If you choose a submission method without designing how to receive errors, the application may continue running while an important piece of work has already failed.

This article examines errors that **occur inside the task**. Errors when the executor **rejects a task** are distinguished separately below.

## 1. Which Interfaces Do the Two Methods Belong To?

- `Executor.execute(Runnable command)` is declared in `java.util.concurrent.Executor`. The method returns `void`: the caller does not receive a result object to wait on or inspect for task failure.
- `ExecutorService.submit(...)` is declared in `java.util.concurrent.ExecutorService` (an interface extending `Executor`). Commonly used overloads are `submit(Runnable)`, `submit(Callable<T>)`, and `submit(Runnable, T result)`. The method returns a `Future`, which serves as the handle to track completion, retrieve the result, or retrieve the error.

| Aspect | `execute(Runnable)` | `submit(Runnable/Callable)` |
| --- | --- | --- |
| Owning interface | `Executor` | `ExecutorService` |
| Return value | `void` | `Future<?>` or `Future<T>` |
| When work completes normally | No direct return value | `Future.get()` returns `null` for a plain `Runnable`, or the value of `Callable<T>` |
| When the task body throws an uncaught exception | With `ThreadPoolExecutor` executing a `Runnable` directly, the error usually escapes the worker's `run()` and may reach `UncaughtExceptionHandler` | With the commonly used `FutureTask` mechanism, the error is stored in the `Future`; `get()` throws `ExecutionException` wrapping the original error |
| How does the caller detect failure? | Design an error-reporting channel inside the task, an appropriate handler/monitoring hook, or a custom mechanism | Retain the `Future` and call `get()` (or use a mechanism to collect/monitor the `Future`s) |
| Can completion be checked via the returned object? | No | Yes, via `isDone()`; however, `isDone() == true` **does not prove success** |
| Can it be canceled via the returned object? | No `Future` is returned by the method | Yes, `Future.cancel(...)`, subject to the limitations of the cancellation mechanism |

**Key takeaway:** `submit()` does not make tasks less error-prone. It changes how a task's outcome is represented and observed. Nor does `execute()` guarantee that a stack trace will always be printed: this depends on the executor, wrappers, and error-handling mechanism.

## 2. Exception Propagation Path

Consider a `Runnable` that throws `IllegalStateException` and does not catch the exception itself.

**Common case: `ThreadPoolExecutor.execute(runnable)`**

1. The executor accepts the `Runnable` and runs `run()` using a worker.
2. `run()` throws a `RuntimeException` or `Error` outward.
3. For a direct `Runnable` on `ThreadPoolExecutor`, the worker terminates abnormally; the error may be forwarded to the worker's `Thread.UncaughtExceptionHandler`.
4. The executor may create a replacement worker to maintain the pool size. This **does not mean the entire thread pool is broken**, nor does it automatically report the error back to the thread that called `execute()`.

If the worker has no custom handler, you will typically see the stack trace written by the default handler to standard error. Do not rely on the assumption that "calling `execute()` will always show the error on the console," because `Executor` implementations and task wrappers can differ.

**Common case: `ExecutorService.submit(runnable)`**

1. `ExecutorService` creates a task with `Future`-based state/result (for example, `FutureTask`) and schedules it to run.
2. When the task body throws an exception, the result wrapper catches and stores the exception.
3. The `Future` transitions to a completed state; a failure that occurred still causes `isDone()` to return `true`.
4. When the caller invokes `future.get()`, the method throws `ExecutionException`; `getCause()` reveals the original exception that caused the task to fail.

Because the error is held inside the `Future`, the worker's `UncaughtExceptionHandler` is **usually not invoked** for errors from tasks submitted via `submit()`. If you ignore the `Future` without another monitoring channel, the error may never appear in the logs.

Scope note: `Executor` is merely a command-execution contract. Some executors run the task directly on the calling thread, while others use separate workers. The worker and stack trace behavior above describes `ThreadPoolExecutor` with a direct `Runnable` task, not a guarantee for every executor.

## 3. Runnable Java 17+ Example: Same Error, Two Ways of Observing It

Create the file **`ExecuteVsSubmitFailure.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class ExecuteVsSubmitFailure {
    public static void main(String[] args) throws Exception {
        CountDownLatch handlerFinished = new CountDownLatch(1);

        ThreadFactory factory = task -> {
            Thread worker = new Thread(task, "demo-worker");
            worker.setUncaughtExceptionHandler((thread, failure) -> {
                System.out.printf("execute/handler: %s: %s%n",
                        failure.getClass().getSimpleName(),
                        failure.getMessage());
                handlerFinished.countDown();
            });
            return worker;
        };

        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });

            if (!handlerFinished.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("UncaughtExceptionHandler did not run");
            }

            Future<?> submitted = pool.submit((Runnable) () -> {
                throw new IllegalArgumentException("submit failed");
            });

            try {
                submitted.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException exception) {
                Throwable cause = exception.getCause();
                System.out.printf("submit/get: %s: %s%n",
                        cause.getClass().getSimpleName(),
                        cause.getMessage());
            }

            System.out.println("submit/isDone: " + submitted.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run:

```bash
javac ExecuteVsSubmitFailure.java
java ExecuteVsSubmitFailure
```

Expected output on the `ThreadPoolExecutor` mechanism created by `Executors.newSingleThreadExecutor(...)`:

```text
execute/handler: IllegalStateException: execute failed
submit/get: IllegalArgumentException: submit failed
submit/isDone: true
```

The example uses `CountDownLatch` to wait for the handler to finish printing before moving on to the `submit()` part, so the order of the three lines can be verified. A single-thread executor can create a new worker after the failure in `execute()`; the `submit()` part still runs. The custom handler already handled logging the error from `execute()`, so you should not expect the JVM's default stack trace.

Explanation of each output line:

- The `execute/handler` line is the message from the executing thread's `UncaughtExceptionHandler`. The caller of `execute()` does not receive any `ExecutionException` or `Future` from that call.
- The `submit/get` line only appears when the calling thread reads `submitted.get(...)` and catches `ExecutionException`. The original error is `IllegalArgumentException`, retrieved via `getCause()`.
- The `submit/isDone: true` line indicates that the task has **finished**, even though it finished due to an exception. Do not use `isDone()` as a success check.

Calling `get(5, TimeUnit.SECONDS)` only limits how long the calling thread waits; timing out throws `TimeoutException` and does not by itself prove that the task has stopped. The example includes `shutdown()` and `awaitTermination()` to clean up the executor when finished.

## 4. `Runnable`, `Callable`, and Checked Exceptions

`Runnable.run()` does not declare `throws` for checked exceptions. Therefore, a `Runnable` cannot throw a checked exception directly out of `run()` without handling it or wrapping it in an unchecked exception. Conversely, `Callable<V>.call()` declares `throws Exception`, so it can report checked exceptions when computation fails.

Example placed inside a method that has an `ExecutorService pool` variable:

```java
Future<String> result = pool.submit(() -> {
    throw new java.io.IOException("cannot read data");
});

try {
    String value = result.get();
    System.out.println(value);
} catch (ExecutionException exception) {
    Throwable cause = exception.getCause();
    // cause is the task's IOException("cannot read data").
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    // The waiting thread was interrupted; decide how to terminate/propagate the error.
}
```

This is an **illustrative snippet inside a method**, not a standalone Java class; it requires an active `pool`. The `IOException` occurring in the worker is stored as the cause of `ExecutionException`. The `Future<String>` return type comes from `Callable<String>`, not from `execute()`.

With `submit(Runnable)`, if the task succeeds, `get()` returns `null`; with `submit(Runnable, fixedResult)`, `get()` returns `fixedResult` on success. When the task fails, all variants can report the error via `ExecutionException`.

## 5. Three Types of Failures to Distinguish

### 5.1. Task Throws an Exception While Running

Examples include `NullPointerException`, `IllegalArgumentException`, `IllegalStateException`, or a checked exception from `Callable`. With `submit()` and the standard `Future` mechanism, `get()` is where the waiter receives `ExecutionException`. With `execute()` on a `ThreadPoolExecutor` worker and a direct `Runnable`, an uncaught error may go to the worker's handler.

`Future.get()` also has paths **other than** `ExecutionException`: `InterruptedException` when the waiting thread itself is interrupted; `CancellationException` if the task was canceled; and `TimeoutException` with the timed overload if no result is available in time. Do not lump all four situations together as "the task threw an exception."

### 5.2. Executor Rejects the Task

When the executor has been `shutdown()` or the queue/pool is overloaded according to the rejection policy, `execute()` may throw `RejectedExecutionException` **immediately at submission time**. `submit()` can also throw this error immediately: many `ExecutorService` implementations wrap the work in a `FutureTask` and then call the `execute()` mechanism to submit it. When rejected, **no `Future` may be returned at all**.

Example of catching it at the right place:

```java
try {
    pool.submit(() -> System.out.println("running"));
} catch (java.util.concurrent.RejectedExecutionException rejected) {
    System.err.println("Executor refused the task: " + rejected);
}
```

This is a snippet placed in a scope where `ExecutorService pool` already exists. Catching rejection at the **submission call** does not replace checking the result later with `Future.get()`. Some `RejectedExecutionHandler` implementations may run the task directly on the calling thread or discard the task according to their own policy; do not infer a single rule for every policy.

### 5.3. Task Catches and Swallows the Error

If a `try/catch` inside `Runnable` catches an exception but only logs it and returns normally, the executor sees a task that **completed normally**. In that case:

- `execute()` has no uncaught exception left to forward to the handler;
- `submit()` has `Future.get()` complete normally (`null` for `Runnable`), even though the actual business work may not have succeeded.

If you want the task to be recorded as failed, design it explicitly: rethrow the exception after adding context, return a result type representing success/failure, or emit the error event to a monitoring channel. Do not use an empty `catch` block to "lose" errors.

## 6. Proper Usage in Applications

**Choose `execute()`** when you only want to submit a command without needing to retrieve a result via `Future`, and you already have a clear logging/failure-reporting strategy. For example, a system where a `Runnable` handles its own errors and sends failure signals to a monitoring destination. `execute()` does not provide a built-in mechanism for the submitter to query the result.

**Choose `submit()`** when the submitter needs to know whether the work has completed, retrieve a result, wait with a timeout, or request cancellation. However, you must **keep and consume the `Future`** or feed it into a centralized observation mechanism. Calling `submit()` and discarding the return value often makes task failures hard to detect.

For the thread waiting on the result, use clear handling rules:

1. `ExecutionException`: retrieve `getCause()` and handle/report the underlying business or technical error.
2. `InterruptedException`: preserve the interrupt status with `Thread.currentThread().interrupt()` if not propagating the exception; then stop or conclude the waiting flow appropriately.
3. `CancellationException`: the task was canceled; do not treat it as successful completion.
4. `TimeoutException` (when calling `get(timeout, unit)`): decide whether to wait longer, retry, or call `cancel(true)`; requesting cancellation via interrupt does not guarantee that an uncooperative task will stop immediately.

For multiple tasks, a simple approach is to store the `Future`s in a list and check each result. In real-world systems, you can build a result or completion collector to avoid missing errors; do not rely solely on whether the executor is still running.

**Executor-level monitoring:** `ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` is useful when you want to track tasks, but `t` is usually `null` for `submit()` tasks wrapped in `FutureTask` because the wrapper has already captured the exception. If you install this hook, you must handle the case where `r` is a `Future` and read the result carefully (including cancellation and interruption) to avoid breaking the worker or waiting at the wrong time. `UncaughtExceptionHandler` also does not replace checking `Future.get()`.

## 7. Common Misconceptions and Mistakes

| Claim | More accurate explanation |
| --- | --- |
| "`submit()` swallows exceptions." | `Future` usually **holds** the exception. The error becomes hard to see when nobody checks the result. |
| "`execute()` always throws the error back to the `execute()` call." | If the task runs on another worker, the error happens on the worker; the submission call may have already returned. An executor running directly on the calling thread is a different case. |
| "`isDone() == true` means success." | `isDone()` is also true when the task failed or was canceled. You need to check `get()` or the appropriate state. |
| "Wrapping every job with `submit()` will automatically log errors." | Normally `submit()` does not print task errors to the console on its own. You need to obtain the `Future` and have an observation policy. |
| "If one task in the pool throws an exception, the whole pool stops." | With `ThreadPoolExecutor`, the worker may terminate abnormally and the pool may replace the worker; other tasks are not canceled by default. |
| "Having an `UncaughtExceptionHandler` is enough for both." | The `submit()` wrapper usually catches the error already, so the worker's handler does not receive it. |
| "Catching `Exception` around the `submit()` call catches task errors." | A `try/catch` at submission catches immediate submission-time errors (such as rejection). Errors raised **later** during execution require checking the `Future`. |

There is one technical exception worth understanding properly: a user can manually create a `FutureTask` and pass it to `execute()`. In that case, `FutureTask` itself will hold the error, even though the outer call is `execute()`. Therefore, error behavior depends on both **the type of task submitted** and **how the executor executes it**, not just the method name.

## 8. Self-Check

**Scenario A.** You submit `pool.submit(() -> { throw new IllegalStateException("bad"); });`, discard the `Future`, and continue processing. Is the caller guaranteed to see the error? **No.** The executor may have stored the error inside the `Future` without writing to the console; you must actively retrieve/observe the result.

**Scenario B.** A `Future<?> f` has `f.isDone() == true` and `f.isCancelled() == false`. Did the task definitely succeed? **No.** It may still have failed; `f.get()` will throw `ExecutionException` if it failed.

**Scenario C.** After calling `shutdown()`, both `execute()` and `submit()` can be rejected. Is this an `ExecutionException` thrown by `Future.get()`? **No.** This is a **task-submission** error (`RejectedExecutionException`), which can occur before any `Future` exists.

When designing error handling, answer two questions before choosing an API: *Who is responsible for knowing whether the task succeeded or failed?* and *Which channel delivers failure information to that party?* `execute()` fits commands that already have their own monitoring mechanism; `submit()` provides a `Future` for the submitter to actively retrieve results and errors.

# execute() vs. submit() and Error Handling in the Java Executor Framework

## 1. Two Ways to Submit Work to an Executor, Two Ways to Observe Errors

When using the **Executor Framework** in Java, we typically submit a task to an executor using one of two methods:

- `execute(Runnable)`, defined by the `Executor` interface, **does not return a result object** (return type `void`).
- `submit(...)`, defined by `ExecutorService`, **returns a `Future`** to observe completion, retrieve the result, receive errors, and send cancellation requests.

Both submit tasks to the executor according to the implementation's execution policy. With a typical `ThreadPoolExecutor`, the task runs on a worker thread; however, you should not generalize that **every executor always runs asynchronously**: some executors run in the caller thread, and certain `RejectedExecutionHandler` implementations can also execute the work in the calling thread.

The most important difference regarding errors:

- `execute(() -> { throw ...; })` with a direct `Runnable` in `ThreadPoolExecutor`: the error is not returned to the `execute` caller as an asynchronous exception. It typically escapes the worker's `run()`, is received by `ThreadPoolExecutor.afterExecute(Runnable, Throwable)` as the `Throwable` parameter, and reaches the thread's uncaught exception mechanism; the worker terminates abnormally and the pool may create a replacement worker depending on its state.
- `submit(() -> { throw ...; })`: typical implementations wrap the task in a `FutureTask` or `RunnableFuture` object. The error is **recorded as the failed state of the Future**; `Future.get()` throws an `ExecutionException` wrapping the cause. That error usually **does not escape `FutureTask.run()`** to reach `UncaughtExceptionHandler`. When `afterExecute` is called for a `FutureTask`, the `Throwable` parameter is usually `null` even though the inner task failed.

**Do not confuse:** a call to `execute(...)` or `submit(...)` **can throw `RejectedExecutionException` immediately in the calling thread** when the executor refuses to accept the task. This is a **submission** error, distinct from an exception thrown **while the task is running**.

This article uses Java 17+ and standard JDK APIs; the concepts apply to Java concurrency in general.

## 2. Quick Comparison Table

| Criterion | `execute(Runnable)` | `submit(...)` |
| --- | --- | --- |
| Interface | `Executor` | `ExecutorService` |
| Task type | `Runnable` | `Runnable` or `Callable<T>` |
| Return value from call | `void` | `Future<?>` / `Future<T>` |
| Retrieving computation result | No `Future` returned | `Future.get()` retrieves the result |
| Observing task completion | Requires another mechanism: latch, callback, queue, custom state | `Future.isDone()`, `get()` |
| Error in task with typical `ThreadPoolExecutor` | Can escape the worker and reach the uncaught handler | Usually kept inside the Future; `get()` throws `ExecutionException` |
| Error when executor rejects | Can throw `RejectedExecutionException` immediately | Can also throw `RejectedExecutionException` immediately |
| Canceling work via return value | No Future to call `cancel` on | `Future.cancel(...)` |
| Task ordering guarantee | Not guaranteed automatically | Not guaranteed automatically |
| Must the task run on another thread? | No, depends on implementation/policy | No, depends on implementation/policy |

The fact that an interface returns a `Future` **does not mean** you have finished designing error handling. If you simply call `submit(task)` and **discard the Future object**, errors in the task may not be observed or recorded by the application as expected.

## 3. Understanding `Runnable`, `Callable`, and the Three `submit` Overloads

`Runnable.run()` has no return value and declares no checked exceptions in its signature:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}
```

This is an API signature excerpt for explanation, not a redefinition of the interface in a project.

`Callable<V>.call()` returns a value of type `V` and is declared `throws Exception`:

```java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

`ExecutorService` has three commonly used overloads:

1. `Future<?> submit(Runnable task)`: if it completes normally, `future.get()` returns `null`.
2. `<T> Future<T> submit(Runnable task, T result)`: if it completes normally, `get()` returns the exact **provided `result` object**, not a return value from `Runnable.run()`.
3. `<T> Future<T> submit(Callable<T> task)`: if it completes normally, `get()` returns the result produced by `call()`.

`Future.get()` **waits until the task completes** or encounters a cancellation/interrupt/error event reflected through the API. `isDone()` can be true when the task has completed **successfully, failed, or been canceled**—it does not mean success.

### Java 17+ Example: Three `submit` Overloads and `get` Values

Create `SubmitResultsDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SubmitResultsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> runnable = executor.submit(() -> {
                int local = 1 + 1;
                if (local != 2) {
                    throw new AssertionError("Math error");
                }
            });

            Future<String> runnableWithResult =
                    executor.submit(() -> {}, "finished");

            Future<Integer> callable = executor.submit(() -> 40 + 2);

            System.out.println("Runnable result: " + runnable.get());
            System.out.println("Provided result: "
                    + runnableWithResult.get());
            System.out.println("Callable result: " + callable.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac SubmitResultsDemo.java
java SubmitResultsDemo
```

Output:

```text
Runnable result: null
Provided result: finished
Callable result: 42
```

`Future.get()` makes `main` wait for the task and establishes the appropriate memory consistency relationship: actions in the task happen-before actions following a successful `get()` on the corresponding Future under the `java.util.concurrent` contract. The example does not rely on nondeterministic worker ordering because `main` prints results after calling `get()` sequentially.

## 4. Exceptions from `execute` Do Not Propagate Back Through a Returned Call

Consider the following snippet:

```java
try {
    executor.execute(() -> {
        throw new IllegalStateException("worker failed");
    });
} catch (IllegalStateException e) {
    System.out.println("Caught in caller?");
}
```

This is a **snippet**, where `executor` is an existing variable. With a typical `ThreadPoolExecutor` accepting tasks to run on a worker, `execute` may return before the task runs, so the `catch` in the **caller** cannot catch exceptions thrown on the worker. The error is handled on the worker's own execution path.

**Important exception:** if you use an executor that **runs tasks immediately on the calling thread**, or a rejection policy like `CallerRunsPolicy` that causes the task to run in the caller, the task's exception **can** surface synchronously in the caller. Therefore, you cannot make an absolute rule that "no exception from `execute` can ever be caught in the caller"; you must distinguish the **executor policy**.

### Java 17+: Observing Errors via `UncaughtExceptionHandler` and `Future.get`

Create `ExecuteVsSubmitFailure.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExecuteVsSubmitFailure {
    public static void main(String[] args) throws Exception {
        AtomicReference<Throwable> uncaught = new AtomicReference<>();
        CountDownLatch handlerCalled = new CountDownLatch(1);

        ExecutorService pool = Executors.newSingleThreadExecutor(task -> {
            Thread t = new Thread(task, "example-worker");
            t.setUncaughtExceptionHandler((thread, error) -> {
                uncaught.set(error);
                handlerCalled.countDown();
            });
            return t;
        });

        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failure");
            });

            if (!handlerCalled.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Uncaught handler not called");
            }
            System.out.println("execute handler: "
                    + uncaught.get().getClass().getSimpleName());

            Future<?> submitted = pool.submit(() -> {
                throw new IllegalArgumentException("submit failure");
            });

            try {
                submitted.get();
            } catch (ExecutionException e) {
                System.out.println("submit get cause: "
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
javac ExecuteVsSubmitFailure.java
java ExecuteVsSubmitFailure
```

When the pool operates normally, without external interrupts and without exceeding the 5-second safeguard timeout:

```text
execute handler: IllegalStateException
submit get cause: IllegalArgumentException
```

**Analysis:**

1. The thread factory sets a custom `UncaughtExceptionHandler` on the worker, avoiding reliance on the default stack trace printed to stderr.
2. `execute` receives a `Runnable` that throws `IllegalStateException`. With this pool, the error is not caught by a FutureTask; the worker encounters an uncaught exception and the handler records it.
3. `handlerCalled.await(...)` forces `main` to wait until the handler has received the error before printing. The latch keeps the output independent of scheduling; do not insert `sleep` to "time" threads.
4. A single-thread executor pool maintains its ability to run subsequent work, creating a replacement worker when needed after the previous worker dies abnormally.
5. `submit` wraps the `Runnable` in a Future. The `IllegalArgumentException` is stored in the Future; `submitted.get()` throws `ExecutionException`, and `getCause()` returns the original exception.
6. The uncaught handler is **not the normal channel** for collecting errors from tasks created by `submit`, because the wrapper catches the error.

The demo uses a direct `Runnable` with `execute`. If the object passed to `execute` is itself a `FutureTask` or a wrapper that catches `Throwable`, the error reporting behavior can differ: you must understand **what Runnable object is actually being executed**, not just the name of the submission method.

## 5. Why Can Exceptions in `submit` Appear "Hidden"?

With an executor based on `AbstractExecutorService`, `submit` typically converts the task into a `RunnableFuture` via `newTaskFor`, then calls `execute` with that wrapper. `FutureTask.run()` catches errors from the `Runnable`/`Callable` and stores the failed outcome. The worker thread can **continue running subsequent tasks** instead of dying from the task's exception.

Conceptual processing flow:

```text
execute(runnable):
    caller -> executor queue -> worker.run()
                             -> exception escapes from Runnable
                             -> afterExecute(..., throwable)
                             -> uncaught exception handling

submit(callable/runnable):
    caller -> create RunnableFuture/FutureTask
           -> executor queue -> worker.run(FutureTask)
                             -> FutureTask stores result/exception
                             -> afterExecute(..., null) is common
    caller -> future.get() -> value or ExecutionException
```

This is a **diagram** of typical execution in `ThreadPoolExecutor`, not a specification requiring every `ExecutorService` implementation to have the same internals.

**Common mistake:**

```java
// Design flaw: not keeping the Future and not observing the task's exception.
executor.submit(() -> processOrder());
```

If `processOrder()` throws an exception, the caller may never know. In applications that require auditing, retries, alerts, or error logging, **keep the Future to observe it** or use a task management layer with centralized error reporting.

## 6. Handling `Future.get` Properly

`Future.get()` can have several important outcomes:

| Outcome | Reflected via API | Interpretation |
| --- | --- | --- |
| Normal completion | Returns result; `null` for Runnable without result | Task completed successfully per contract |
| Task throws an error | `ExecutionException` | `getCause()` is the original error inside the task |
| Future is canceled | `CancellationException` (unchecked) | The Future is in the canceled state |
| **Waiting** thread is interrupted | `InterruptedException` | Waiting was interrupted; the task is not necessarily canceled |
| `get(timeout, unit)` times out | `TimeoutException` | **Waiting** expired; the task may still be running |

When handling `ExecutionException`, do not ignore the cause:

```java
try {
    Result value = future.get();
    use(value);
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    recordFailure(original);
}
```

This is a snippet where `Result`, `future`, `use`, and `recordFailure` belong to a hypothetical application; you also need to handle `InterruptedException` and `CancellationException` at the appropriate layer.

**Do not swallow interrupts:** if the thread calling `get` is interrupted and the current layer cannot declare `throws InterruptedException`, typically call `Thread.currentThread().interrupt()` and exit or return a valid cancellation outcome. Do not catch `InterruptedException` and keep waiting indefinitely without a policy.

**Do not confuse timeout with cancellation:** `future.get(100, MILLISECONDS)` throwing `TimeoutException` does not stop the task automatically. If you want to request cancellation, the caller can call `future.cancel(true)`, but that is a **cooperative request** and does not guarantee that the worker stops immediately or rolls back side effects.

### Should You Call `get` Inside the Same Worker Running That Task?

If a task in a **single-worker** pool submits another task to the same pool and calls `future.get()` to wait for the new task, the worker can deadlock itself: the new task sits in the queue and there is no other worker to run it. This is **thread-starvation deadlock**, not a bug specific to `submit`. Do not design nested waiting workflows on an under-provisioned pool.

## 7. `ThreadPoolExecutor.afterExecute` and Why `Throwable` Can Be Null

`ThreadPoolExecutor` provides a hook:

```java
protected void afterExecute(Runnable r, Throwable t)
```

The hook runs when a task finishes on a pool worker. With `execute` given a `Runnable` that throws an exception directly, `t` typically contains that exception. However, with a `submit` task wrapped in a `FutureTask`, the error has already been captured by the wrapper, so `t` is usually `null`.

If you want to record errors for **both submission methods** in a custom `ThreadPoolExecutor`, you need to check for `r instanceof Future<?>` and extract the error from the Future **if the task is already done**. Calling `get()` when the task is not yet done could block the hook's worker; guard it properly.

### Java 17+ Example: Centralized Error Collection in `afterExecute`

Create `AfterExecuteFailures.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class AfterExecuteFailures {
    static final class ObservedPool extends ThreadPoolExecutor {
        final ConcurrentLinkedQueue<String> failures =
                new ConcurrentLinkedQueue<>();

        ObservedPool() {
            super(1, 1, 0L, TimeUnit.MILLISECONDS,
                    new LinkedBlockingQueue<>(), task -> {
                        Thread t = new Thread(task, "observed-worker");
                        t.setUncaughtExceptionHandler((thread, error) -> {
                            // This hook only avoids printing the default stack trace
                            // in the example; it does not replace real logging.
                        });
                        return t;
                    });
        }

        @Override
        protected void afterExecute(Runnable task, Throwable error) {
            super.afterExecute(task, error);
            Throwable failure = error;

            if (failure == null
                    && task instanceof Future<?> future
                    && future.isDone()) {
                try {
                    future.get();
                } catch (ExecutionException e) {
                    failure = e.getCause();
                } catch (CancellationException e) {
                    failure = e;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }

            if (failure != null) {
                failures.add(failure.getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ObservedPool pool = new ObservedPool();

        try {
            pool.submit(() -> {
                throw new IllegalArgumentException("submitted");
            });
            pool.execute(() -> {
                throw new IllegalStateException("executed");
            });

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Pool did not terminate");
            }
            System.out.println("Observed: " + pool.failures);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run:

```bash
javac AfterExecuteFailures.java
java AfterExecuteFailures
```

When the pool completes normally within the 5-second timeout:

```text
Observed: [IllegalArgumentException, IllegalStateException]
```

**Explanation:**

- The pool has exactly **one worker** and a FIFO `LinkedBlockingQueue`, so the `submit` task is processed before the `execute` task.
- `submit` creates a `FutureTask` that stores `IllegalArgumentException`; in the hook, `error` is `null` but `future.get()` throws `ExecutionException`, from which the cause is extracted.
- `execute` passes a `Runnable` that throws `IllegalStateException`; the hook receives a non-null `error` and records it in the failure queue.
- With the `execute` error, the worker may die; `ThreadPoolExecutor` handles the worker state appropriately. Waiting on `awaitTermination` ensures `main` only prints the failure list after both tasks have been processed.
- `future.isDone()` is a guard before `get()` to avoid unnecessary blocking. However, if a subclass or custom `RunnableFuture` has an unusual contract, or the hook is designed to run in a complex environment, care is still needed.

**Hook limitations:** `afterExecute` is called for tasks **that actually ran on a worker**. Tasks rejected before running will not pass through the hook automatically; tasks sitting in the queue that are drained by `shutdownNow()` also do not necessarily run. In addition, `afterExecute` is not the right place for heavy logging or long blocking operations, because it runs on the worker thread and can reduce throughput.

Do not treat this example as a complete observability library: in production, logging inside the hook must avoid throwing exceptions, record context/correlation IDs, and separate cancellation from business errors if needed.

## 8. Submission Rejection Errors: `RejectedExecutionException`

Both `execute` and `submit` can be rejected **immediately when called**, for example if the executor has already been shut down or both the thread pool and its bounded queue are full. With `ThreadPoolExecutor.AbortPolicy`, the method throws `RejectedExecutionException` in the calling thread.

Conversely, `CallerRunsPolicy` can run the task in the caller when the pool is still running but cannot accept more tasks; this can create backpressure, but it also changes the execution flow and how exceptions surface. `DiscardPolicy` or `DiscardOldestPolicy` risks dropping tasks according to policy; with `submit`, if a task's future is discarded without executing or completing, a caller waiting for the result may hang. Only use a rejection policy when you fully understand its impact on business logic and the Future contract.

### Java 17+: Reproducing Rejection with a Bounded Queue

Create `RejectionDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();     // Worker is waiting inside the first task.
            pool.execute(() -> {});   // Occupies the only slot in the queue.

            boolean rejected = false;
            try {
                pool.submit(() -> 42);
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("Submission rejected: " + rejected);
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile/run:

```bash
javac RejectionDemo.java
java RejectionDemo
```

Output when the pool completes normally:

```text
Submission rejected: true
```

The single worker is held inside the first task by `releaseWorker`; the capacity-1 queue already holds the second task. The third `submit` call has neither an available worker nor a queue slot, so `AbortPolicy` throws `RejectedExecutionException` **in the caller**. No `Future` is successfully returned from that rejected call.

**Submission failure differs from task failure:** `RejectedExecutionException` must be handled around the `submit`/`execute` call itself, whereas errors from a `submit` task must be observed via `Future.get` or a dedicated mechanism.

`Executors.newFixedThreadPool(n)` uses an unbounded queue by default configuration, so it is unsuitable if you need explicit bounded backpressure. A large number of queued tasks can still consume significant memory; consider `ThreadPoolExecutor` with carefully chosen queue capacity and rejection policy.

## 9. Shutdown, Interruption, and Cancellation

`ExecutorService` has two key lifecycle methods:

- `shutdown()`: stops accepting new tasks; previously accepted tasks continue to be processed according to the executor's contract. **It does not stop all workers immediately.**
- `shutdownNow()`: attempts to stop running tasks—typically via interrupt—and returns a list of tasks that were waiting and had not yet started. **It does not guarantee all running tasks will stop**, especially if code does not cooperate with interrupts or is at a non-interruptible blocking point.

`Future.cancel(false)` can mark a Future as canceled when appropriate without requesting an interrupt on the running thread. `Future.cancel(true)` attempts to send an interrupt to the running task if a thread is associated with it, but it is not a mechanism that forces rollback. `Future.get()` on a canceled Future throws `CancellationException`.

If a task has side effects, you need to determine:

1. If canceled before the task runs, do you need to release or return ownership of the work?
2. If canceled mid-write, how is cleanup/compensation handled?
3. If an interrupt arrives while waiting on a queue, lock, or I/O, how should it react?
4. Does timing out while waiting for a result mean the task must be requested to cancel?
5. Do you need to log **accepted**, **running**, **succeeded**, **failed**, and **canceled** states separately?

A responsible shutdown pattern for an application using its own executor is:

```java
// Snippet: executor is an ExecutorService owned by the application.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            // Report that workers have not stopped; do not declare shutdown successful.
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This is a shutdown policy snippet, not a standalone file. You should not arbitrarily shut down an executor **owned by another component**, because doing so can cut off their tasks.

### Task Code Must Cooperate with Interrupts

`submit` and `cancel(true)` will not automatically fix an infinite CPU-bound task:

```java
// Snippet of a computation loop with cooperative stop condition.
while (!Thread.currentThread().isInterrupted()) {
    processNextChunk();
}
```

Here `processNextChunk()` is defined by the application. For blocking operations such as `BlockingQueue.take()` or `CountDownLatch.await()`, the thread may throw `InterruptedException`; the code typically needs to clean up and restore/propagate the interrupt appropriately. Do not catch and swallow the exception, causing work to continue even though the caller requested cancellation.

## 10. When to Choose `execute`, When to Choose `submit`?

### Consider `execute` when

- The task truly **has no result** for the caller and is managed by a separate monitoring/lifecycle system.
- You want to use the simple `Executor` interface without needing the `Future` contract.
- The system has a clear channel for recording `Runnable` errors (e.g., catching/logging errors **inside** the task, a custom executor hook, or an uncaught handler suitable for the implementation).
- "Fire-and-forget" work is **valid for the business logic**, already has an error-handling path, and is not simply forgotten after submission.

Example wrapper for recording errors:

```java
// Snippet: executor is an Executor, task is a Runnable,
// recordFailure is defined by the application.
executor.execute(() -> {
    try {
        task.run();
    } catch (RuntimeException e) {
        recordFailure(e);
        throw e; // Policy-dependent: let the worker know about the failure.
    }
});
```

This is a snippet, not a standalone program. **Rethrowing** may trigger the uncaught handler or cause the worker to terminate in `ThreadPoolExecutor`; with a different `Executor`, the reaction may differ. Do not log the error twice if an observability system already captures it elsewhere.

### Consider `submit` when

- You need to receive the result of a `Callable` or observe when a `Runnable` completes.
- The caller needs to wait for the task via `get`, handle `ExecutionException`, use a timeout, or cancel via `Future.cancel`.
- You need to manage a set of tasks and collect explicit **succeeded / failed / canceled** statuses.
- There is a service responsible for **tracking Futures** rather than discarding them and assuming errors will be logged.

Example managing multiple tasks:

```java
// Snippet: executor is an ExecutorService, tasks is a list of Callable<Result>.
List<Future<Result>> futures = new ArrayList<>();
for (Callable<Result> task : tasks) {
    futures.add(executor.submit(task));
}
for (Future<Result> future : futures) {
    try {
        Result result = future.get();
        saveResult(result);
    } catch (ExecutionException e) {
        recordFailure(e.getCause());
    }
}
```

This is a snippet without imports or declarations for `Result`/`tasks`/`saveResult`/`recordFailure`; you also need to handle `InterruptedException`, `CancellationException`, deadlines, and the policy on whether to keep waiting after a task fails. If you need to collect results in **completion** order, `ExecutorCompletionService` can help avoid waiting on a slow first Future when later tasks have already finished.

### A Simple Design Rule

**If a task fails, who is responsible for knowing and reacting?**

- If the answer is **the caller**, `submit` + `Future.get`/Future management is usually the clearest design.
- If the answer is **the infrastructure or the task itself records it**, `execute` may suffice.
- If **no one** is responsible, both approaches lack an error-handling policy.

Neither option is universally better. The core difference is **the contract for submitting work, observing results, errors, and lifecycle**, not just "which method runs faster."

## 11. Pitfalls to Avoid

1. **"`execute` runs synchronously, `submit` runs asynchronously."** False; the implementation and rejection policy determine which thread actually runs the task.
2. **"`submit` never throws an exception in the caller."** False: `RejectedExecutionException` can be thrown **at submission time**; exceptions **inside the task** are recorded by the Future in typical implementations.
3. **"`try/catch` around `execute` always catches task errors."** False if the task runs on another worker; exceptions exist with direct/caller-runs execution.
4. **"`submit` automatically logs exceptions to stderr."** False; the Future wrapper usually catches the error; if you do not observe the Future, the error can be missed.
5. **"`Future.isDone()` being true means success."** False: canceled and failed tasks can also be done.
6. **"`Future.get()` returns the original exception directly."** Usually false: task exceptions are wrapped in `ExecutionException`; use `getCause()`.
7. **"`afterExecute` receives a non-null Throwable for every failed task."** False for `FutureTask` from `submit`; you may need to inspect the Future.
8. **"`afterExecute` catches rejected tasks too."** False: tasks rejected before running do not pass through the worker hook.
9. **"`Future.get(timeout)` expiring means the task was canceled."** False: timeout is the caller's state of **stopping waiting**.
10. **"`cancel(true)` guarantees the task stops immediately."** False: interruption is cooperative; tasks/I/O may not respond immediately.
11. **"`shutdownNow` stops all tasks immediately."** False: it only attempts to stop them and returns unstarted tasks; you must verify actual termination.
12. **"With one worker, a task doing a nested submit and get can always run."** False: it can deadlock due to worker starvation.
13. **"Using `DiscardPolicy` with submit is harmless."** False: a dropped task's Future may never complete, leaving the caller waiting forever.
14. **"Just catching `Exception` in a task handles all errors."** Not quite: `Error` is a `Throwable` but not an `Exception`; logging/lifecycle policies need proper error classification rather than trying to swallow serious system errors.
15. **"UncaughtExceptionHandler is a general mechanism for all submit styles."** False: the task wrapper can store the error without letting the exception escape to the worker.
16. **"Using Future means you already have observability."** False if the Future is never retained, read, or handled anywhere.
17. **"ExecutorService must be shut down everywhere submit is called."** Incorrect if the executor is managed by another service; you must respect ownership.

## 12. Checklist for Implementing `ExecutorService` with Error Handling

1. **Does the task need a result?** Choose `Runnable` or `Callable<T>` accordingly.
2. **Who owns the executor?** Who is responsible for `shutdown` and lifecycle monitoring?
3. **Choose `execute` or `submit` based on observation responsibility:** will the Future be stored and awaited/checked?
4. **Distinguish submission exceptions from execution exceptions:** catch `RejectedExecutionException` properly in the caller; handle task failures via Future/hook/logging.
5. **For `submit`, observe `ExecutionException` and its cause;** distinguish cancellation, interruption, and timeout.
6. **For `execute`, define the error reporting mechanism:** task-internal handling, uncaught handler, or `afterExecute` depending on the implementation.
7. **If overriding `afterExecute`, handle `Future` safely:** only call `get` when done; avoid making the hook blocking and do not let the hook itself throw exceptions.
8. **Review rejection policy and queue capacity:** a bounded pool with no available slots must have a clear backpressure/retry/rejection path.
9. **Do not wait on nested Futures on an under-provisioned pool:** check task dependencies, worker count, and held locks.
10. **Design timeout, cancel, and shutdown:** have a policy for when the caller stops waiting while the task is still running.
11. **Ensure error handling does not cause duplicate side effects:** retries require idempotency or an appropriate protocol.
12. **Test success, failure, cancellation, and rejection paths:** use `CountDownLatch`/bounded queues for controlled scheduling rather than guessing timing with `sleep`.
13. **Measure and monitor:** accepted/running/completed task counts, task failures, cancellations, rejections, queue backlog, and wait times; record context to trace related tasks.

**Key takeaway:** `execute(Runnable)` submits work **without returning a Future**; for direct tasks on `ThreadPoolExecutor`, exceptions can go through the worker's hook/uncaught handler. `submit(...)` returns a **Future**, which holds the result and error for the caller to observe via `get()`; task errors typically do not appear in the uncaught handler. Both can be rejected **at submission time**. A proper design must assign clear responsibility for receiving errors, handling timeouts/interrupts/cancellations, and managing the executor with a clear lifecycle.

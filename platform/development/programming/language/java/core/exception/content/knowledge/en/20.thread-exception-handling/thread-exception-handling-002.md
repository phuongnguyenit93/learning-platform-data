# A try-catch in the Creating Thread Does Not Automatically Catch Errors in a Child Thread

## 1. The problem: which execution flow does an exception follow?

When a Java method calls another method **on the same thread**, an uncaught exception can propagate back up the call chain to an appropriate `catch`. However, when code creates another thread via `Thread.start()`, the execution of `run()` takes place on a **new thread with its own call stack**. An exception thrown inside `run()` does not "jump" back onto the call stack of the thread that called `start()`.

This is a fundamental principle in Java Core:

> **A `try-catch` catches exceptions thrown within the execution flow of the `try` block, or rethrown through a result mechanism read by that same thread. It does not automatically catch errors occurring asynchronously in an independent thread.**

Consider the following idea:

~~~java
try {
    Thread worker = new Thread(() -> {
        throw new IllegalStateException("worker failed");
    });
    worker.start();
} catch (IllegalStateException e) {
    System.out.println("caught by creator");
}
~~~

This is a non-standalone illustrative snippet, though syntactically valid when placed inside a method. `start()` asks the JVM to launch the work on another thread; the `IllegalStateException` is thrown from the lambda running in the worker. The `catch` on the creating thread **does not catch this error**. Without a custom `UncaughtExceptionHandler`, the default handler may print the stack trace to standard error; the exact output depends on the runtime environment and handler configuration.

However, `start()` **can throw an error directly on the calling thread**, such as `IllegalThreadStateException` when attempting to `start()` the same `Thread` a second time. That error belongs to the `start()` call itself and can therefore be caught on the creating thread. You must clearly distinguish **errors when requesting to create/start a thread** from **errors in the work that the thread executes afterward**.

After this lesson, you will know how to:
- Explain why a `catch` in a parent thread does not catch exceptions from a child thread.
- Distinguish between `Thread.start()`, `Thread.run()`, and `Thread.join()`.
- Observe thread errors using `UncaughtExceptionHandler`, or return errors via `Future`/`CompletableFuture`.
- Properly handle `InterruptedException`, `ExecutionException`, `CompletionException`, cancellation, and timeouts.
- Design tasks with explicit error-collection points so asynchronous failures are not silently missed.

## 2. Each Java thread has its own call stack

Visualize two threads:

~~~text
Thread "main"                         Thread "worker"
--------------------------------     --------------------------------
main()                                Thread.run()
  |
  +-- try {                            +-- process task
  |     worker.start()                 |     +-- service.process()
  |     ...                            |           |
  |   } catch (...)                    |           +-- throw
  |                                    |
  +-- continue running                 +-- no matching catch
                                        -> UncaughtExceptionHandler
                                        -> thread terminates
~~~

Calling `start()` creates a launch relationship, not a synchronous call onto `main`'s stack. When the new thread encounters an unhandled exception, the JVM searches for a handler on **that thread's own stack**. The creating thread's stack is not part of this call chain.

Another thread can observe **data written by the child thread** or **a result object** when properly synchronized. Observing an error requires one of those communication mechanisms; the relationship "I created this thread" does not by itself define an exception propagation path.

### 2.1. Comparing `run()` and `start()`

~~~java
Runnable task = () -> {
    throw new IllegalStateException("failed");
};

try {
    task.run(); // Synchronous call on the current thread.
} catch (IllegalStateException e) {
    System.out.println("caught directly");
}
~~~

The snippet above illustrates a `Runnable`, not a complete Java file with `main`. `run()` is just a normal method call: the exception propagates on the same stack, so `catch` receives it. However, if you call `new Thread(task).start()`, the lambda runs on a new thread and a `catch` around `start()` will not observe the lambda's exception.

**Do not use `run()` instead of `start()` just to catch errors**, because doing so defeats the purpose of concurrent execution. Choose an appropriate error-collection mechanism instead.

## 3. `join()` waits for completion; it does not forward the child thread's exception

`Thread.join()` allows the calling thread to wait for the target thread to terminate. It **does not return a result object** from `run()` and **does not rethrow uncaught exceptions** from the target thread.

There are two categories of errors to distinguish:

| What happens | Which thread observes it directly? | Does `join()` rethrow the task error? |
| --- | --- | --- |
| Worker throws `IllegalStateException` and does not catch it | Worker, then the uncaught handler mechanism | No |
| Waiting thread is interrupted during `join()` | Waiting thread | `join()` may throw `InterruptedException` |
| Worker finishes normally | Creating thread can see this after `join()` | No error to throw |
| Worker never terminates | Calling `join()` indefinitely may wait forever | No; requires a separate wait/cancellation policy |

After a `join()` call returns normally because the target thread has terminated, the actions of the target thread **happen-before** the actions of the calling thread after `join()` according to the Java Memory Model. This ensures visibility of state written by the worker under memory rules; it **does not mean receiving exceptions**. If you want to transfer errors via shared state, you must also design a proper state channel and handling approach.

A common mistake is writing:

~~~java
try {
    worker.start();
    worker.join();
} catch (Exception e) {
    // Cannot rely on this catch to detect errors inside the worker.
}
~~~

This is a fragment assuming `worker` is already declared. `Exception` here can catch `InterruptedException` on the waiting thread itself, or another exception thrown directly on the calling thread. It does not receive exceptions thrown on the worker's stack.

## 4. Complete Java 17 example: three error observation mechanisms

Save the following program as **`ThreadExceptionBoundaryDemo.java`**. Within a single program, it sequentially demonstrates:

1. A separate `Thread` throws an exception; the thread's handler receives the error, while the `catch` around `start()/join()` does not.
2. A task runs via `ExecutorService.submit()`; the error is stored in the `Future` and reported when `get()` is called.
3. A `CompletableFuture` stage fails; the caller observes the error at `join()` via `CompletionException`.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadExceptionBoundaryDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread child = new Thread(() -> {
            throw new IllegalStateException("child crashed");
        }, "child");

        child.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("handler: " + thread.getName()
                        + " -> " + error.getMessage()));

        try {
            child.start();
            child.join();
        } catch (IllegalStateException error) {
            System.out.println("creator catch");
        }
        System.out.println("creator continued; terminated=" + !child.isAlive());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> task = pool.submit(() -> {
                throw new IllegalArgumentException("task failed");
            });
            try {
                System.out.println(task.get());
            } catch (ExecutionException error) {
                System.out.println("future: " + error.getCause().getMessage());
            }

            CompletableFuture<String> stage =
                    CompletableFuture.supplyAsync(() -> {
                        throw new UnsupportedOperationException("stage failed");
                    }, pool);
            try {
                stage.join();
            } catch (CompletionException error) {
                System.out.println("stage: " + error.getCause().getMessage());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run with JDK 17+ from the directory containing the file:

~~~bash
javac --release 17 ThreadExceptionBoundaryDemo.java
java ThreadExceptionBoundaryDemo
~~~

Stdout of the example:

~~~text
handler: child -> child crashed
creator continued; terminated=true
future: task failed
stage: stage failed
~~~

### 4.1. Output and ordering analysis

**Line 1:** the exception in `child` has no `catch` inside the thread itself; the JVM invokes the `UncaughtExceptionHandler` we configured specifically for it. The handler prints `child crashed`. The handler runs as part of the terminating thread's uncaught exception handling mechanism; do not treat this as a direct return value from `Thread.start()`.

**Line 2:** the `main` thread called `child.join()`, so it waited for the child to finish and then confirmed `!child.isAlive() == true`. The line `creator catch` **does not appear**, because the worker does not throw exceptions across `main`'s stack.

**Line 3:** `submit` returns a `Future<Integer>`. The task throws `IllegalArgumentException`, and `Future.get()` throws `ExecutionException` whose `getCause()` is the original exception. There is no need to try "catching worker errors" around the `submit` call.

**Line 4:** `CompletableFuture.supplyAsync` completes exceptionally. `join()` throws `CompletionException`, whose `getCause()` is `UnsupportedOperationException("stage failed")`.

The synchronization mechanisms in the program make the order of the printed lines above deterministic: `main` waits for `child` to finish before printing the second line; it waits for the task via `Future.get()` before creating the next stage on the single-threaded executor, and then `join()` waits for that stage. In other examples, if multiple threads write to `System.out` concurrently without such ordering relationships, **you should not rely on stdout ordering**.

In real-world applications, if an exception comes from an uncontrolled source, you still need to inspect the type of `getCause()` and handle or rethrow it according to your contract; printing only `getMessage()` is a minimal illustration for this lesson. If the caller is interrupted in `main`, the example's `throws InterruptedException` signature allows the error to propagate rather than silently ignoring it.

## 5. Catching in the executing thread itself

If you know how to handle the error inside the task, place `try-catch` **inside the lambda or `Runnable.run()`**:

~~~java
Runnable task = () -> {
    try {
        performWork();
    } catch (IllegalArgumentException e) {
        recordFailure(e);
    }
};
new Thread(task).start();
~~~

This is **illustrative code**, depending on undefined functions `performWork()` and `recordFailure(Exception)`. Because `catch` belongs to code running inside the worker, it can receive that error. However, after catching it, you must clearly define whether the task is considered failed or has recovered successfully. If you merely log the exception and treat the task as successful, the failure information will never reach the coordinator.

For a request-processing task, it may make sense to catch a business exception, convert it into a business result, and continue; however, for an unexpected unrecoverable error, you may need to forward it through a result channel or notify the coordinator. Avoid `catch (Throwable ignored)` and do not swallow JVM `Error`s just to keep a thread running.

### 5.1. Checked exceptions inside `Runnable`

The `Runnable.run()` method does not declare `throws` for checked exceptions. Therefore, a `Runnable` lambda cannot directly throw `IOException` without handling or converting it.

~~~java
Runnable fileTask = () -> {
    try {
        readFile();
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException("Reading failed", e);
    }
};
~~~

This is an illustrative fragment with an undefined method `readFile() throws IOException`. Wrapping with `UncheckedIOException` preserves the `cause`; if the task does not catch it further, this unchecked exception will reach the task/thread error-handling mechanism. Converting checked exceptions to unchecked ones is a contract choice, not the only option: a `Callable<T>` with `call() throws Exception` may be more appropriate when using `ExecutorService.submit()`.

## 6. `UncaughtExceptionHandler`: receiving errors when a thread fails to catch them

`Thread.UncaughtExceptionHandler` is invoked when a thread is about to terminate due to an uncaught exception. It can be registered per thread:

~~~java
Thread t = new Thread(() -> {
    throw new IllegalArgumentException("bad worker input");
}, "validation-worker");

t.setUncaughtExceptionHandler((thread, failure) -> {
    System.err.println(thread.getName() + ": " + failure);
});

t.start();
~~~

This snippet has no standalone `main`. The handler receives `Thread` and `Throwable` parameters. This mechanism is useful for logging errors from raw threads or preventing failures from disappearing from observability systems.

In addition to per-thread handlers, Java supports `Thread.setDefaultUncaughtExceptionHandler(...)` for a JVM-wide default handler. If no per-thread handler is set, the delegation chain involving `ThreadGroup` and the default handler is applied according to API rules. You should understand the exact runtime environment before changing the process-wide default handler: libraries, frameworks, application servers, or test runners may already rely on their own recording mechanisms.

Design limitations to keep in mind:
- The handler **does not turn the exception into an exception on the creating thread**.
- The handler typically runs as the thread is about to terminate due to an uncaught error; it is not a mechanism to "recover and resume from where it threw".
- The handler should not perform complex operations that might throw another exception; if the handler itself fails, the JVM does not guarantee a second handler will rescue it.
- The handler does not replace a typed result-collection system. If the caller needs to know whether a task succeeded or failed and branch accordingly, `Future` or `CompletableFuture` is usually more suitable.
- For tasks wrapped in a `Future` by `ExecutorService.submit()`, exceptions are normally **stored in the Future**; you cannot expect the uncaught handler to receive the error simply because a callable threw an exception.

In production, it is usually better to attach the thread name, task ID, correlation ID, and **non-sensitive** context data to logs, rather than calling `printStackTrace()` ad hoc in many places.

## 7. `ExecutorService`: differences between `execute` and `submit`

An `ExecutorService` accepts work to be executed by managed workers. Exception handling depends on the submission method:

| API | Return value | Observing failures from calling code |
| --- | --- | --- |
| `execute(Runnable)` | `void` | No `Future`; requires handling inside the task, the executor's uncaught logging/monitoring mechanism, or another application mechanism |
| `submit(Runnable)` | `Future<?>` | `get()` may throw `ExecutionException` if the task throws an exception |
| `submit(Callable<T>)` | `Future<T>` | `get()` returns a value or throws `ExecutionException` |
| `invokeAll(...)` | `List<Future<T>>` | Must inspect each `Future` to determine which tasks failed |
| `invokeAny(...)` | Value from one successfully completed task | May throw `ExecutionException` if no task succeeded, along with relevant orchestration errors |

**`submit` does not throw task exceptions to the caller at submission time.** It returns an object that can later represent running/incomplete, succeeded, failed, or cancelled states. If you call `submit` and discard the `Future`, a task can fail without any application branch handling the error.

With `execute`, if `Runnable.run()` lets an unchecked exception escape, worker behavior and logging depend on the executor/`ThreadFactory` and implementation. In a standard `ThreadPoolExecutor`, abnormal task termination may trigger uncaught handling; however, do not treat `execute` as "it will throw errors back to the calling thread," nor build business logic around default stack traces.

### 7.1. Handling `Future.get()` according to its contract

~~~java
try {
    String value = future.get();
    use(value);
} catch (java.util.concurrent.ExecutionException e) {
    Throwable taskFailure = e.getCause();
    reportTaskFailure(taskFailure);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This fragment assumes `future`, `use`, and `reportTaskFailure` exist, and is placed inside a method that can `return`. `ExecutionException` indicates **the task completed with an exception**; the root cause is retrieved via `getCause()`. `InterruptedException` indicates **the waiting thread was requested to be interrupted**, not proof that the task itself failed.

If you need to bound the wait time, use `future.get(timeout, unit)`; on timeout, the method throws `TimeoutException`. **A timeout does not automatically cancel the task.** The caller decides whether to keep waiting, report an indeterminate state, or call `future.cancel(true)` as appropriate. Cancelling with `mayInterruptIfRunning=true` only attempts to request interruption of the running worker; whether stopping succeeds depends on whether the task cooperates with interruption and its current state. Once a `Future` is cancelled, `get()` may throw an unchecked `CancellationException`.

### 7.2. Collections of multiple Futures

If you call `invokeAll` or submit 10 tasks via `submit`, all Futures being in the done state **does not mean all of them succeeded**. `Future.isDone()` returns true for normal completion, failure, and cancellation alike. For accurate reporting, retrieve each result and distinguish:
- value from `get()`: success;
- `ExecutionException`: task failure;
- `CancellationException`: task was cancelled;
- `InterruptedException`: coordinating thread was interrupted while waiting.

When one task fails, decide whether to continue the remaining tasks, cancel them, or return an aggregated report. Do not infer from a failed future that earlier futures caused no side effects.

## 8. `CompletableFuture`: exceptions flow through the stage chain

`CompletableFuture<T>` both represents an asynchronous result and provides transformation stages. A stage can **complete exceptionally**. Chained stages propagate failures to subsequent stages unless an appropriate recovery mechanism is provided.

### 8.1. Ways to observe errors

| API | When the stage fails | Usage |
| --- | --- | --- |
| `join()` | Throws unchecked `CompletionException`; if cancelled, may throw `CancellationException` | Convenient when the caller does not want checked exceptions |
| `get()` | Throws checked `ExecutionException`; may also throw `InterruptedException` | Used when the `Future` contract is needed |
| `get(timeout, unit)` | Same as `get()` plus `TimeoutException` | Bounds waiting time |
| `exceptionally(fn)` | Turns a failure into a fallback value if handling succeeds | Policy-based recovery |
| `handle((value, error) -> ...)` | Receives both success and error branches, producing a new result | Combines both branches |
| `whenComplete((value, error) -> ...)` | Observes the outcome and performs side effects; normally does not turn failure into success | Controlled metrics/logging/cleanup |

Example expression:

~~~java
CompletableFuture<String> recovered =
        CompletableFuture.<String>supplyAsync(() -> {
            throw new IllegalStateException("remote data failed");
        }).exceptionally(error -> "fallback");
~~~

This is a fragment requiring `import java.util.concurrent.CompletableFuture` and an enclosing method. If the supplier fails, the `exceptionally` stage returns `fallback`, so `recovered.join()` can return a string successfully. However, **returning a fallback is a business decision**, not always the right one. For a payment transaction, you cannot arbitrarily replace a submission error with "success".

A stage chained with `thenApply` may be skipped when the preceding stage completes exceptionally; the error propagates down the chain, so it must be handled at an appropriate observation point. If you build a chain:

~~~java
CompletableFuture<String> result = loadAsync()
        .thenApply(value -> transform(value))
        .whenComplete((value, failure) -> recordOutcome(value, failure));
~~~

this is only an illustrative fragment with undeclared functions. If `loadAsync` or `transform` fails, `whenComplete` can receive the error to record it; it does not clear the failure state by default. If the `whenComplete` action itself throws an exception, how the resulting stage completes depends on whether the original stage succeeded or failed, following `CompletionStage` rules.

### 8.2. Do not abandon asynchronous chains

~~~java
CompletableFuture.runAsync(() -> saveSomething());
System.out.println("request accepted");
~~~

This fragment assumes `saveSomething`. The print statement only indicates that processing has been scheduled, **not that saving succeeded**. If you neither store the future to observe it nor attach a reliable error-handling branch, a failure can become an unhandled state in the application.

Do not just catch exceptions around `runAsync(...)` and assume errors inside the lambda are handled: the exception may occur after the `runAsync` call returns. When returning a future to a caller, make it clear in the API whether the caller must call `join/get`, register a callback, or whether the system manages the task to completion.

## 9. `InterruptedException` and task cancellation are not the same as task exceptions

`InterruptedException` has a specific meaning in concurrency handling. When a thread is sleeping, waiting in `join`, or waiting in `Future.get()` and gets interrupted, the waiting API may throw `InterruptedException`. This reflects that **the waiting thread was requested to be interrupted**, rather than saying anything certain about the outcome of the thread/task being waited on.

In `Runnable` code, a common pattern is:

~~~java
Runnable pollingTask = () -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Thread.sleep(1_000);
            pollOnce();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
    }
};
~~~

This is a fragment using a hypothetical `pollOnce()`. When interrupted during `sleep`, Java throws `InterruptedException` and typically clears the interrupt status in the process. Calling `Thread.currentThread().interrupt()` restores the signal so upper layers know about the interruption request; then the task terminates instead of swallowing the error and running indefinitely. If your method allows `throws InterruptedException`, another option is to propagate the error.

Never treat `interrupt()` as a mechanism that forcefully kills a thread immediately. CPU-bound tasks that do not check for interruption, blocking libraries that do not support interruption, or specific I/O operations may continue running. Calling `Future.cancel(true)` likewise only requests cancellation according to the Future contract and the task's cooperation; it does not automatically roll back any effects that have already occurred.

## 10. Passing errors via controlled data

If you are not using an executor but the caller needs to retrieve an error from a manually created `Thread`, you can use a shared channel with explicit synchronization, such as `AtomicReference<Throwable>`, or a `BlockingQueue` holding a typed result. A simple pattern:

~~~java
import java.util.concurrent.atomic.AtomicReference;

class CaptureThreadFailure {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                throw new IllegalStateException("validation failed");
            } catch (RuntimeException e) {
                failure.set(e);
            }
        });
        worker.start();
        worker.join();

        if (failure.get() != null) {
            System.out.println(failure.get().getMessage());
        }
    }
}
~~~

If saved as `CaptureThreadFailure.java`, compile/run:

~~~bash
javac --release 17 CaptureThreadFailure.java
java CaptureThreadFailure
~~~

Stdout:

~~~text
validation failed
~~~

Here, **the worker actively catches and stores the exception** in `AtomicReference`; `main` calls `join()` to wait, then reads the error. `join()` does not catch the error itself — it simply provides a coordination point so `main` knows when the task has finished. With this pattern, the exception will not automatically reach `UncaughtExceptionHandler` because it was caught inside the worker. If the caller wants to rethrow it, it decides how to convert it, such as inspecting the exception type and wrapping it into an exception matching the caller's contract.

In complex programs, prefer `Future`/`CompletableFuture` or a lifecycle-managing abstraction; they handle completion/cancellation states more conveniently than manually coordinating multiple flags, references, and handlers. For tasks with return values or multiple expected business error types, you can also return a structured result type instead of throwing exceptions for normal states.

## 11. Where to place `catch` when designing multithreaded applications

A real-world design has distinct boundaries:

~~~text
Thread A: receives request
    |
    +-- submit/launch task on Thread B
    |        |
    |        +-- catch recoverable errors directly in B
    |        +-- other errors -> Future/CompletionStage/handler
    |
    +-- A continues working
    |
    +-- A retrieves result/callback when appropriate
             |
             +-- success -> process value
             +-- failure -> inspect cause and decide
             +-- cancel/timeout -> handle orchestration state
~~~

Choose the mechanism based on your needs:
- **Task is responsible for its own recovery:** handle with `try-catch` directly inside the task; if unrecoverable, reflect the failure state.
- **Caller needs to know if the task succeeded or failed:** use `Callable` + `Future`, or `CompletableFuture`/`CompletionStage`, and observe the outcome at the orchestration boundary.
- **Raw thread fails unexpectedly:** register an `UncaughtExceptionHandler` for logging/monitoring, while avoiding relying on it to pass business results.
- **Multiple tasks collaborate on one job:** define rules for waiting/cancelling/aggregating results; other already-completed threads may have caused side effects before one task failed.
- **Task does not need to respond to the current request:** the system still needs an owner for its lifecycle, exception recording, and retry/reconciliation mechanisms if persistent side effects exist.

Pay attention to **lifecycle**: if you return a response from the request-receiving thread before the asynchronous task finishes, distinguish "accepted" from "processed successfully." An exception arriving later cannot retroactively alter an already-sent response; status must typically be communicated via a job ID, callback, polling, or an appropriate communication channel.

### 11.1. Do not conclude all tasks succeeded just because waiting finished

`Thread.join()` succeeding, `CountDownLatch.await()` returning, `Future.isDone() == true`, or all tasks finishing all only indicate a **synchronization point / completion state**. To know whether they succeeded, you must inspect the results or the designed error channel. Similarly, `ExecutorService.awaitTermination(...)` tells you the executor terminated after shutdown within the timeout, not that every task ran without throwing exceptions.

This is also where exceptions and **state preservation** intersect: a worker may write partial data and then throw an exception. Even though `main` learns of the error via `Future`, any writes, HTTP requests, or mutations before the error may have already occurred. Capturing the exception lets you observe the failure; recovering requires transactions, compensation, idempotency, or appropriate state rules.

## 12. Common mistakes and how to fix them

| Anti-pattern | What is wrong | How to fix |
| --- | --- | --- |
| Putting `try-catch` outside `thread.start()` to catch worker errors | Different call stacks | Catch inside the worker, handler, or `Future` result |
| Believing `join()` will throw errors from `run()` | `join()` only waits and may be interrupted | Combine `join` with a state channel, or use `Future` |
| Calling `run()` to "be able to catch exceptions" | Runs synchronously without creating a thread | Use `start()` and an appropriate error-collection mechanism |
| Calling `submit()` without saving/reading the `Future` | Failure may go unobserved by the caller | Keep the `Future` and call `get` / attach management flow |
| Catching `ExecutionException` and only printing `getMessage()` | Loses original error context | Inspect `getCause()`, convert/record appropriately |
| Catching `InterruptedException` and ignoring it | Loses cancellation signal when upper layers need to know | Propagate or restore interrupt status and terminate |
| Catching `Throwable` so "no thread dies" | Masks `Error` and corrupted state | Catch only types you can handle, with a failure policy |
| Assuming `cancel(true)` terminates every task | Interruption is cooperative | Design timeouts/cancellation suited to the task type |
| Assuming `whenComplete` recovers from errors | Callback normally only observes | Use `exceptionally` or `handle` when recovery is intended |
| Handling an exception without handling partial side effects | Capturing an error ≠ rollback | Design transactions, idempotency, and compensation |

### 12.1. What does "Main didn't catch it, yet the program kept running" mean?

An uncaught exception in a worker normally terminates that worker; **it does not automatically exit the JVM immediately** while other threads are still running. This also depends on the count and state of daemon/non-daemon threads, application policies, and shutdown behavior. Conversely, an executor may replace a worker thread after a failure depending on the implementation, making the application appear healthy even though a specific task failed.

Therefore, the fact that the process is still alive, a REST server still serves other requests, or logs only show a stack trace **does not prove critical tasks succeeded**. You need error-tracking and completion-tracking mechanisms at the job level.

## 13. Testing exceptions across multiple threads

Do not just assert that calling `start()` does not throw. Write targeted tests:
1. **Raw Thread:** set a custom handler, have the worker throw an exception, call `join()`, assert the handler received the expected type and message; assert the `catch` around `start()/join()` is not where the error is received.
2. **Worker catches itself:** have the worker write the error to a result channel; after `join()`, verify the data without relying on `Thread.sleep` to guess when it finishes.
3. **ExecutorService.submit:** task throws an exception; `get()` throws `ExecutionException` and `getCause()` is the expected error.
4. **CompletableFuture:** stage fails; `join()` throws `CompletionException`, `get()` throws `ExecutionException`; `exceptionally/handle` can transform it into another result per policy.
5. **Interruption:** interrupt a waiting thread; ensure code handles `InterruptedException` properly and preserves/propagates the cancellation signal per contract.
6. **Timeout/cancellation:** verify a task is not treated as successful simply because the caller timed out, and verify appropriate cancellation rules.
7. **Side effects:** task writes data then fails; assert the post-error state matches the design, without assuming catching the exception means rollback.

In multithreaded tests, avoid asserting exact log order without synchronization. Prefer `CountDownLatch`, `Future.get(timeout, unit)`, timed `join`, or suitable concurrency testing tools for bounded coordination; avoid using `Thread.sleep` to "wait blindly" in tests. When tests finish, shut down executors and release test-owned resources.

## 14. Adoption checklist

- [ ] Identified **which thread** throws the exception and which thread runs the `catch` block.
- [ ] Not expecting a `catch` around `start()` to catch exceptions inside `run()`.
- [ ] Using `join()` strictly to wait for termination; using a separate result channel when success/failure is needed.
- [ ] Independent threads have an uncaught error observation mechanism, such as an appropriate `UncaughtExceptionHandler`.
- [ ] `submit` tasks are tracked via `Future`; `ExecutionException.getCause()` is handled.
- [ ] `CompletableFuture` stages are intentionally observed or recovered; `get` vs. `join` are distinguished.
- [ ] `InterruptedException`, timeouts, and cancellation have dedicated policies, not confused with task exceptions.
- [ ] Errors are neither swallowed nor conflated with task success.
- [ ] If a task has side effects, rollback, compensation, or reconciliation on failure is defined.
- [ ] Dedicated tests exist for worker exceptions, coordinator thread exceptions, callback exceptions, and task cancellation.

### Practice exercise

Write a `loadAll(List<String> ids)` API using `ExecutorService` to look up multiple IDs in parallel. Each task may return a record, report "not found," or throw an I/O exception. Determine how the caller distinguishes all three outcomes; how to collect all failures from the Futures without neglecting remaining tasks; how to cancel on request timeout; and why a `try-catch` around the `submit()` loop cannot replace observing `Future.get()`.

Then replace it with `CompletableFuture`, try `handle` to turn each stage into a structured result, and test the case where one stage fails before other stages complete. Do not rely on completion order unless the design itself applies synchronization or result sorting.

**Key takeaway:** An exception propagates along the call stack where it is thrown. Creating and child threads have separate stacks; to pass failures across this boundary, you must **design an explicit observation channel** such as a handler, `Future`, or `CompletionStage`.

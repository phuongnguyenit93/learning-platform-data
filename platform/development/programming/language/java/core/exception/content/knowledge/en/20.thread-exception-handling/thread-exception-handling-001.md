# Exceptions Only Propagate Within the Call Stack of the Executing Thread (Java)

## 1. Meaning of the Principle

In Java, when a method throws an exception, the JVM searches for a handler by sequentially exiting method calls **on the call stack of the currently running thread**. That process is called *stack unwinding*. If a compatible `catch` is found, the thread continues according to the handler's logic. If the exception traverses all frames without being handled, it becomes an **uncaught exception of that thread**.

Each `Thread` has its own call stack. Therefore, an exception thrown in thread B **does not automatically jump to** a `try/catch` running in thread A, even if A is the thread that created, started, or waited on B. This is a foundational boundary when writing APIs with concurrency.

Key terms:

- **Call stack:** the currently executing method frames of **a single thread**; each frame holds the return address and information needed for the call.
- **Stack unwinding:** the JVM exits frames within the same thread, runs the appropriate `finally` blocks, releases monitors of `synchronized` methods/blocks upon exiting their scope, and searches for a matching handler.
- **Uncaught exception:** an exception that reaches the top of the thread with no application handler handling it; the `Thread.UncaughtExceptionHandler` mechanism may be invoked.
- **Error delivery:** passing **information** about a failure from a task to another thread via a result object, `Future`, `CompletableFuture`, queue, callback, or notification protocol. This is an intentional action; it is not cross-thread stack unwinding.

This principle applies to both **platform threads** and **virtual threads** in Java versions that support virtual threads: each executing thread has its own exception context. Task orchestration and waiting mechanisms can help transfer an **error result** back to the caller, but they do not merge two call stacks into one.

## 2. Why Does the Parent Thread's `try/catch` Fail to Catch the Child Thread's Error?

Consider the following snippet (a code fragment inside a method, assuming the necessary imports are present):

```java
try {
    Thread child = new Thread(() -> {
        throw new IllegalStateException("failed inside child");
    });
    child.start();
    child.join();
} catch (IllegalStateException ex) {
    System.out.println("This catch does not handle the child's exception");
}
```

`Thread.start()` asks the JVM to run `Thread.run()` in a **new thread**. The `throw` statement belongs to `child`'s call stack; the outer `catch` block is on the call stack of the thread that called `start()`, so it **does not catch** the exception from `child`.

Important conditions:

- `start()` itself can throw an exception in the **calling thread**, such as `IllegalThreadStateException` when attempting to start a `Thread` object that has already been started. Such an exception can be handled by a compatible `catch` in the caller.
- `join()` can throw `InterruptedException` **in the waiting thread** when that thread is interrupted; that is not a business exception from `child`. If `join()` is interrupted, a `catch (InterruptedException)` block in the caller can catch it because this exception originates in the caller itself.
- In the example code, `join()` returns after `child` finishes; it does not rethrow the `IllegalStateException` that occurred in `child`. Without a custom handler, the runtime typically reports the uncaught exception on `System.err`.
- Calling `Thread.run()` **directly** via `child.run()` is just a normal method call on the **current thread**. In that case, the exception can propagate to the caller's `catch`; nor does it create a new thread.

It is important to clearly distinguish a method that initiates asynchronous work from a method that **waits for and retrieves a result**. Creating or waiting on a thread does not implicitly carry an error-transfer mechanism.

## 3. Call Stack Diagram When an Exception Is Thrown

Suppose A calls `start()` to run B. Conceptually, there are two threads with two independent stacks:

```text
Thread A (caller)                Thread B (worker)
----------------                 ----------------
main()                           Thread.run()
  start() [returns]                task()
  join() [waiting]                   step1()
                                     step2() -> throw X
  continues after join()           unwind step2 -> step1 -> task
                                 -> run -> uncaught handler
```

Exception X is searched for a handler in `step2()`, then `step1()`, then `task()`, then the frames above them in **thread B**. The JVM does not search for a handler in A's `main()`. After B terminates, A can continue after `join()` without knowing B encountered an error, unless the two sides have a **result-reporting channel**.

Common misleading signs:

1. Thread A called a method that created B: that does not make B's call stack a child branch in terms of Java exception handling.
2. Inside B, a method of an object created by A is called: the object may be shared, but the stacks are still separate.
3. The exception name or stack trace mentions a class called by A: that does not trigger A's `catch`.
4. Two tasks share an `ExecutorService`: each execution has the context of the executing thread; error transfer also depends on the task type and the result-retrieval API.

## 4. Compilable and Runnable Java 17+ Example

This example places four scenarios side by side: a synchronous call, a raw `Thread`, a `Future`, and a `CompletableFuture`. It intentionally throws the same `IllegalStateException` to distinguish **where the exception is thrown** from **where the error information is observed**.

Create the file `ThreadExceptionBoundaryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadExceptionBoundaryDemo {
    static void startOperation() {
        deeper();
    }

    static void deeper() {
        throw new IllegalStateException("boom");
    }

    public static void main(String[] args) throws InterruptedException {
        try {
            startOperation();
        } catch (IllegalStateException ex) {
            System.out.println("SYNCHRONOUS: " + ex.getClass().getSimpleName());
        }

        Thread worker = new Thread(ThreadExceptionBoundaryDemo::startOperation,
                                   "raw-worker");
        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("UNCAUGHT " + thread.getName() + ": "
                        + error.getClass().getSimpleName()));
        worker.start();
        worker.join();
        System.out.println("AFTER JOIN: main continues");

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> future = executor.submit(
                    ThreadExceptionBoundaryDemo::startOperation);
            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("FUTURE: "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            executor.shutdown();
        }

        CompletableFuture<Void> stage = CompletableFuture.runAsync(
                ThreadExceptionBoundaryDemo::startOperation);
        try {
            stage.join();
        } catch (CompletionException ex) {
            System.out.println("COMPLETABLE: "
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("MAIN: done");
    }
}
```

Compile and run with JDK 17 or newer, from the directory containing the file:

```bash
javac -encoding UTF-8 ThreadExceptionBoundaryDemo.java
java ThreadExceptionBoundaryDemo
```

Standard output of the example:

```text
SYNCHRONOUS: IllegalStateException
UNCAUGHT raw-worker: IllegalStateException
AFTER JOIN: main continues
FUTURE: IllegalStateException
COMPLETABLE: IllegalStateException
MAIN: done
```

**What happens in each part:**

1. `startOperation()` is called directly by `main`, so `IllegalStateException` travels along the `deeper() → startOperation() → main()` chain of the main thread itself. The `catch` in `main` catches it.
2. A `Thread` object is started with `start()`. The error occurs in `worker`; because `worker` does not handle it itself, **`worker`'s `UncaughtExceptionHandler`** prints the message. `join()` ensures `worker` has finished before `main` prints the next line, but does not rethrow the error.
3. `ExecutorService.submit()` submits the task to the executor and returns a `Future`. The execution failure is stored in the `Future` result; `main`'s `future.get()` call throws `ExecutionException` whose `getCause()` is the original `IllegalStateException`.
4. `CompletableFuture.runAsync()` creates an asynchronous stage. When the task fails, the stage completes in an exceptional state; `main`'s `stage.join()` call throws `CompletionException` wrapping the cause.
5. The program still reaches `MAIN: done`. A failure in a worker does not by default terminate all other threads or abort the process.

The example uses `setUncaughtExceptionHandler` for stable output instead of relying on default stack trace printing to stderr. `ExecutorService` is shut down with `shutdown()` after retrieving the result; on Java 17, do not assume `ExecutorService` is an `AutoCloseable` resource for `try-with-resources`.

Note: `Future.get()` may additionally throw `InterruptedException` or `CancellationException` depending on state; `CompletableFuture.join()` may throw `CancellationException` if the future is cancelled. Both retrieval calls are shown for the case where the task **fails due to an exception**, not in every possible state.

## 5. Where Is the Handler on the Same Call Stack?

A `catch` clause handles an exception when:

- The exception arises during synchronous execution on the **current thread itself**.
- The thrown exception type is compatible with the type in `catch`, according to Java's rules.
- No handler in a lower frame has already definitively handled the exception.

Example of a synchronous call chain:

```java
static void level1() {
    level2();
}

static void level2() {
    throw new IllegalArgumentException("bad value");
}

// In another method on the same thread:
try {
    level1();
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
```

These are **illustrative method fragments**, not a standalone program, because the method definitions and calling code must be placed in an appropriate class. `level2()` does not need a `catch` for the handler at the `level1()` call site on the same thread to catch it. If `level1()` spawns another thread and `level2()` runs in that thread, the interpretation changes completely.

Along the unwinding path, applicable `finally` blocks still execute on the **throwing thread**; `try-with-resources` resources are closed on the thread executing that path. Cleanup mechanisms may also throw additional errors, such as suppressed exceptions, but still do not automatically transfer the exception to a caller on another thread.

## 6. Raw Threads: What Role Does `UncaughtExceptionHandler` Play?

`Thread.UncaughtExceptionHandler` receives notification when a thread is about to terminate due to an unhandled exception. Example:

```java
Thread worker = new Thread(() -> {
    throw new IllegalArgumentException("invalid task state");
}, "worker-A");

worker.setUncaughtExceptionHandler((thread, failure) -> {
    System.err.println("Worker " + thread.getName()
            + " failed: " + failure.getClass().getSimpleName());
});

worker.start();
```

This snippet is an **implementation fragment** placed inside a method that manages the worker's lifecycle. The handler runs in the worker's failure-handling context; it can log, update state, or emit a notification through an appropriate shared channel. It is **not a `catch` of the parent thread**, and it does not automatically resume the failed task from where the exception was thrown.

The handler lookup order in Java includes the handler set directly on the thread or the `ThreadGroup`'s handler, and then the corresponding default behavior. A default handler can be configured via `Thread.setDefaultUncaughtExceptionHandler(...)`, but that global setting must be considered carefully because it affects threads that do not set their own handler. If the uncaught exception callback itself throws an exception, the JVM usually ignores the new exception from the callback; complex or error-prone recovery logic should not be placed here.

When no custom handler is set, the JVM typically prints uncaught exception details to stderr. The exact output may depend on the runtime, logging configuration, and thread name, so do not rely on log text as a result-delivery protocol. A thread dying from an uncaught exception does not mean all other threads must die.

**Notably:** for tasks executed via an executor or future, the framework may **catch the exception to store it in the result object**. Therefore, you must not rely solely on an uncaught handler to detect failures of all asynchronous tasks.

## 7. Distinguishing `Thread.start()`, `Thread.run()`, and `Thread.join()`

| API | Which thread does it run on? | Error mechanism |
| --- | --- | --- |
| `thread.run()` | The thread **calling** `run()` | Exception can propagate to the caller's `catch` like a synchronous call |
| `thread.start()` | Starts executing `run()` on a **new thread** | Errors in `run()` are handled on the new thread's stack; `start()` does not rethrow them |
| `thread.join()` | The thread calling `join()` waits for the target thread to terminate | Does not propagate the target thread's exception; may throw `InterruptedException` in the waiting thread |
| `thread.setUncaughtExceptionHandler(...)` | Registers a handler for the target thread | Handles/observes errors **not caught in the target**, does not automatically propagate them to the caller |

The `thread.run()` case can be confusing because it uses the same `Thread` object while in reality **no new thread** is created. Calling `run()` directly is usually a mistake when the goal is concurrency.

With `join()`, its key value is **synchronization**: once a thread has terminated, another thread can observe its memory effects under the *happens-before* rule when `join()` succeeds. However, memory *happens-before* does not mean automatically transferring a `Throwable` across threads. If you want to receive errors, the worker must place the result/exception into a shared channel or use an abstraction that supports results, such as `Future`.

## 8. `ExecutorService`: `execute()` and `submit()` Are Not the Same

`ExecutorService` manages a pool of threads that execute tasks. Its two API paths have an important difference:

### `execute(Runnable)`

`execute` takes a `Runnable` and **does not return a `Future`**. If the task throws an uncaught `RuntimeException`, the exception may reach the worker thread's uncaught handling mechanism, depending on the executor and how the task is wrapped. With a standard `ThreadPoolExecutor`, runtime exceptions from tasks submitted with `execute` can cause the worker to terminate abruptly and trigger uncaught exception handling.

This does not allow the caller to write `try { executor.execute(task); } catch (...)` and expect to catch an exception that occurs *later* in the worker. `execute` can only throw errors **synchronously at submission time**, such as `RejectedExecutionException` if the executor rejects the work.

### `submit(Runnable/Callable)`

`submit` returns a `Future`. Exceptions in the task are typically **recorded in the `Future` result** rather than escaping to the worker's uncaught handler. The caller must observe the result:

```java
Future<Integer> future = executor.submit(() -> {
    throw new IllegalStateException("calculation failed");
});

try {
    Integer value = future.get();
    System.out.println(value);
} catch (ExecutionException ex) {
    Throwable root = ex.getCause();
    System.err.println("Task failed: " + root);
}
```

This is a **code fragment inside a method** with an active `ExecutorService executor` and `Future`, `ExecutionException` imported. `get()` also declares `InterruptedException`, so the enclosing method must declare/catch it properly or restore the interrupt status according to its contract.

A practical consequence: if you call `submit` but **discard the `Future` result**, the task's exception may go unobserved or unlogged by the caller as intended. The design should have a component responsible for tracking each task/future, especially tasks that mutate data or resources.

### Incomplete Futures, Cancellation, and Timeouts

`future.get()` can block until the task completes. `future.get(timeout, unit)` adds the possibility of throwing `TimeoutException` in the calling thread **for waiting too long**; a waiter timeout does not by itself guarantee the task has stopped. `future.cancel(true)` sends a cancellation request that may use an interrupt, but the task must cooperate and may not stop immediately; already-performed work state must be handled independently.

When encountering `ExecutionException`, `getCause()` points to the `Throwable` that caused the task to fail. Do not assume the cause is a specific checked or unchecked type; inspect the type and the task's contract.

## 9. `CompletableFuture`: Errors Are Recorded in the Stage and Exposed at the Observation Point

`CompletableFuture` represents the result or failure of a processing chain. When an asynchronous function throws an exception, the associated stage is marked as completed **exceptionally**. Common observation points:

| Mechanism | How the error is received | Meaning |
| --- | --- | --- |
| `future.join()` | `CompletionException` with `getCause()` being the source error in normal cases | Retrieves the result synchronously, unchecked exception |
| `future.get()` | `ExecutionException` with `getCause()` being the cause | `Future` interface; also throws `InterruptedException` |
| `future.exceptionally(fn)` | Callback receives the `Throwable` and can produce a fallback value | Turns failure into a result if a valid fallback exists |
| `future.handle((value, error) -> ...)` | Callback sees either success or error | Produces a new result stage according to chosen logic |
| `future.whenComplete((value, error) -> ...)` | Callback observes the result or error | Typically used for logging/metrics, does not recover by default |

Example code fragment inside a method that already has `CompletableFuture<Integer> future`:

```java
CompletableFuture<Integer> recovered = future.exceptionally(ex -> {
    System.err.println("Async failure: " + ex);
    return -1;
});
```

This is only an example of turning an error result into `-1`; **only do this if `-1` is a fallback meaning permitted by the contract**. If `-1` is also valid data, the fallback can mask the error. For state-updating or financial tasks, swallowing an error and returning a default is usually very dangerous.

### Do Callbacks Run on the `main` Thread?

You must not infer from the names `handle`/`whenComplete` that the callback runs on the original calling thread. Continuations without the `Async` suffix may be executed by the thread that completes the preceding stage or the thread that triggers completion, depending on timing; `...Async` methods have their own executor policy and can accept an explicit executor. Therefore:

- Callback logic must be thread-safe.
- Do not rely on the calling thread's `ThreadLocal` unless the appropriate context is propagated.
- Do not make assumptions about log ordering across concurrent tasks without synchronization conditions.
- A new exception in a callback can cause the **next stage** to complete exceptionally; it does not automatically return to a `catch` that already exited earlier in `main`.

## 10. How to Transfer Errors from a Raw `Thread` to the Calling Thread

If using a raw `Thread` and you want the caller to confirm failure, you can use a synchronized result channel. The example below is a **code fragment inside a method declaring `throws InterruptedException`**, assuming `doWork()` is a method that can throw `RuntimeException`:

```java
AtomicReference<RuntimeException> failure = new AtomicReference<>();

Thread child = new Thread(() -> {
    try {
        doWork();
    } catch (RuntimeException ex) {
        failure.set(ex);
    }
});

child.start();
child.join();

RuntimeException observed = failure.get();
if (observed != null) {
    throw new IllegalStateException("Child task failed", observed);
}
```

You need to import `java.util.concurrent.atomic.AtomicReference`. `AtomicReference` supports safe result sharing; in addition, a successful `join()` establishes a *happens-before* relationship with the child's task. What is transferred to the caller is **a `Throwable` object as data**, after which the caller explicitly throws a new exception with `cause` set to the worker's error.

This is **not** a case of the JVM walking back from stack B to stack A. At the moment the caller throws the new `IllegalStateException`, the JVM unwinds **the caller's stack**; the `cause`'s stack trace still helps indicate where the error in the worker originated.

The code only catches `RuntimeException` for illustration purposes. For tasks with checked exceptions, you must decide on the contract and an appropriate channel for storing the exception type. Normally you should not `catch (Throwable)` and assume you can recover from every `Error`; a severe error may not allow safe continued operation.

If the software already uses an executor, prefer `Future` or `CompletableFuture` instead of rolling your own error-storage channel, which easily misses cancellation, timeouts, and thread lifecycle management.

## 11. Checked Exceptions, Unchecked Exceptions, and Errors in Lambdas

In Java, `Runnable.run()` does not declare any checked exceptions. Therefore, a lambda passed to `new Thread(() -> ...)` cannot simply throw a checked `IOException` outward without handling or wrapping/converting it inside the lambda. You can:

- Catch `IOException` inside the task and report it via a channel or a wrapper with `cause`;
- Use `Callable<V>` in an executor, because `Callable.call()` declares `throws Exception`, and the caller observes it via `Future.get()`;
- Structure the asynchronous API so that the result or error is the value of a future/stage.

Example code fragment inside a method that already has `ExecutorService executor`:

```java
Future<String> fileJob = executor.submit(() -> {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
});
```

Here `Callable<String>` can throw a checked `IOException`; that exception is preserved as the `cause` of `ExecutionException` when the caller invokes `fileJob.get()`. A missing file or I/O error only occurs when the task runs; at the moment `submit` returns, the caller may not yet know about the error.

Unchecked exceptions (`RuntimeException`) do not automatically "fly across threads" either; the checked/unchecked distinction belongs to **compile-time type checking and declaration contracts**, not erasing stack boundaries.

## 12. `InterruptedException` Belongs to the Waiting Thread

This is a case easily confused with "an exception propagated from child to main":

```java
try {
    child.join();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

The code above is a fragment inside an appropriate method that already has `Thread child`; `return` must be placed where Java syntax permits. `InterruptedException` occurs because the **thread calling `join()`** was interrupted while waiting, not because `child` threw this exception to the caller. Calling `Thread.currentThread().interrupt()` restores the interrupt flag so outer layers can see the signal if the method does not propagate the exception.

Do not treat an interrupt as an "exception sent from another thread." `interrupt()` sets a cooperative request signal; certain blocking APIs will throw `InterruptedException` in the interrupted thread, but stopping the task depends on the code and wait points. Do not use the interrupt mechanism as the primary business error-delivery path, or force a worker to stop using unsafe mechanisms.

## 13. Uncaught Exceptions, the JVM Process, and Shared Resources

A worker dying from an uncaught exception **does not guarantee the JVM shuts down immediately**. The JVM can continue running as long as non-daemon threads remain active; process termination depends on the remaining threads and the runtime environment. In particular:

- In a multi-request server, one request handler or worker dying does not mean all other requests must stop.
- A thread's failure does not automatically cancel tasks running on other threads.
- An exception in a worker does not automatically roll back databases, files, or shared mutable state.
- `synchronized` monitors are automatically released when exiting the stack, but partially modified data may still be left in an inconsistent state.
- An uncaught callback is a place to **observe/record** failures, not an automatic guarantee of business state recovery.

This imposes a failure-design requirement: if a worker holds locks, resources, transactions, or multi-step updates, establish a clear contract for cleanup, atomicity, rollback within the resource's scope, and how to report status to the rest of the system.

Also, do not use a thread name or exception message as the sole identifier for a request: an executor can reuse a worker for multiple tasks. Use an explicit correlation ID/task ID to tie errors to the business operation being handled.

## 14. Distinguishing Submission-Time Errors and Execution-Time Errors

An asynchronous API typically has **two distinct error zones**:

**Zone 1: right when the caller submits the work**

For example, `executor.submit(task)` or `executor.execute(task)` can fail synchronously because the executor has already been shut down or cannot accept more tasks. `RejectedExecutionException` arises in the caller's submission call, so a `try/catch` directly around that call can handle it.

**Zone 2: when the worker executes the work**

For example, code inside `task` throws `IllegalArgumentException`, `IOException`, or `IllegalStateException`. The caller cannot catch it directly just with a `try/catch` around `submit`. It must observe the `Future` or an equivalent error-notification mechanism.

Similarly, a `CompletableFuture.supplyAsync(...)` call can fail synchronously at creation/scheduling time due to executor rejection, whereas an exception inside the supplier after it starts running causes the stage to complete exceptionally. Distinguishing the two helps place `catch` blocks and monitoring mechanisms in the right spots.

## 15. Designing a Responsible Multithreaded Error-Handling Path

When writing a library or service with tasks running on other threads, decide upfront in the API contract:

1. **Who owns the task?** Which caller must wait for or receive the result of that work?
2. **How should errors be observed?** `Future`/`CompletableFuture`, callback, message, log + state machine, or handler? Is logging alone enough for the caller to make decisions?
3. **Which errors fail the task?** How are checked I/O errors, business errors, timeouts, cancellations, and bugs categorized?
4. **Does the task keep running after a timeout/cancellation?** If so, will a retry cause duplicate transactions or side effects?
5. **When one task in a group fails, what happens to the others?** Continue, cooperatively cancel, collect all errors, or fail fast according to the contract?
6. **Is shared state safe?** Are transactions, locks, snapshots, immutability, or idempotency needed?
7. **Where are errors recorded?** Is there an ID to correlate worker logs with the caller's result?

A clear implementation path is usually: the caller submits the task, retains a reference to the result, waits/composes at the appropriate point, checks success or failure, and then performs cleanup and retries according to the error type. Even for fire-and-forget tasks, you still need a defined place for **who receives error reports, tracks completion, and handles side effects**; "nobody calls `get()`" does not mean failures have been handled.

## 16. Common Misconceptions

| Misconception | What is true |
| --- | --- |
| "I wrapped `thread.start()` in `try/catch`, so I catch all errors in the worker." | The caller's `catch` only catches errors occurring **in the caller** when calling `start()`; errors in the worker follow the worker's stack. |
| "Calling `join()` rethrows the worker's exception." | `join()` only waits for the worker to finish; the caller must have a separate result channel. |
| "`ExecutorService.submit()` didn't print an uncaught log, so the task had no errors." | `submit` can store the error in the `Future`. You must monitor `get()` or an appropriate result-observation mechanism. |
| "Every `CompletableFuture` callback runs on the `main` thread." | Which thread executes the callback depends on the continuation type, completion timing, and executor. |
| "`CompletionException` is the root cause of the error." | Usually it is a **wrapper**; inspect `getCause()` and the full cause chain. |
| "`InterruptedException` from `join()` is an error propagated from the target thread." | It is a waiting error of the **thread calling `join()`** when it is interrupted. |
| "If a worker throws a `RuntimeException`, the JVM will definitely terminate." | The worker may terminate, while other threads and the process can continue. |
| "When a worker dies, transactions and shared variables revert to their prior state." | Java exceptions do not automatically roll back side effects or mutable state. |
| "Calling `thread.run()` is equivalent to `thread.start()`." | `run()` executes directly in the caller; `start()` creates execution on a separate thread. |
| "Catching `Throwable` in every worker is a safe way not to lose errors." | Catching `Error` as well can mask critical conditions; a clear error and bounded recovery policy is needed. |

## 17. How to Test Propagation Behavior

Concurrency tests should verify **where the error is caught** and **the error-delivery path**, not just check that the log contains the word `Exception`:

- **Synchronous:** call the throwing function directly, use the corresponding `assertThrows`, and verify the handler on the caller.
- **Raw thread:** set a handler on the thread; use `join()`; verify the handler receives the error and `join()` does not throw the business exception.
- **`Thread.start` vs `run`:** compare calling `run()` directly (same stack) with `start()` (separate stack).
- **`Executor.submit`:** submit a throwing task; `future.get()` must yield `ExecutionException` with the expected `getCause()`.
- **`CompletableFuture`:** fail a stage; `join()` yields `CompletionException` with the appropriate cause; `handle`/`exceptionally` produce the right result if the contract allows it.
- **Submission rejection:** test an already-shut-down executor and verify a synchronous error in the caller.
- **Cancellation and interruption:** ensure the waiter handles `InterruptedException`; verify the task can stop cooperatively and side effects are managed.
- **True multithreading:** use `CountDownLatch` or explicit test synchronization to coordinate ordering; avoid relying on `Thread.sleep()` or accidental timing.

If a test needs to wait for a task, it should have an explicit timeout to avoid hanging indefinitely. In particular, tests capturing errors from an uncaught handler should avoid relying on stdout/stderr, which can interleave across threads, or on runtime-dependent default thread names.

## 18. Summary of Working Rules

- Exceptions **unwind within a single call stack**: a handler that wants to catch directly must be on the thread executing that call path.
- `Thread.start()` creates an asynchronous boundary; `Thread.join()` waits for completion **but does not bring the exception back**.
- `Thread.UncaughtExceptionHandler` observes unhandled errors of a thread; it is not by itself a result channel for the caller.
- `Future.get()` and `CompletableFuture.get()/join()` allow the caller to **actively observe failures**, typically via `ExecutionException` or `CompletionException` with a `cause`.
- Exceptions in a worker and side effects of that worker are two separate concerns: you must define post-error state, ensure synchronization, cleanup, cancellation, and controlled retries.

**Remember:** *Exceptions do not automatically cross thread boundaries; information about an exception can be transferred through an explicit result API or communication channel.* Understanding this distinction helps design multithreaded APIs with reliable error-reporting paths and avoid silently dropping failed tasks.

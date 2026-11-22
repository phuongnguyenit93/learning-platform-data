# Thread.UncaughtExceptionHandler: Handling Uncaught Exceptions in Java Threads

When a `Thread` executes code and an exception or error escapes the thread's entry point without being handled, the thread terminates abnormally due to the failure. Java provides the `Thread.UncaughtExceptionHandler` interface to receive notifications about an **uncaught `Throwable`**, along with information about the failing thread. This serves as the final failure observation point for a thread, useful for logging, alerting, incident recording, and coordinating with monitoring mechanisms.

However, **a handler is not a `catch` block that can resume execution at the point of failure**. By the time it is invoked, the thread is already heading toward abnormal termination; to recover the task, return a result, or retry, the application must have its own mechanism. In particular, failures in tasks submitted via `ExecutorService.submit` or in `CompletableFuture` may be **stored in the result object** and never pass through the worker thread's uncaught-exception handler.

## 1. Understanding "Uncaught" at the Thread Boundary

A simple example:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Dữ liệu trạng thái không hợp lệ");
});
worker.start();
```

This is an illustrative snippet without a standalone `main` method. An `IllegalStateException` escapes `Runnable.run()` without being caught inside the worker. The JVM prepares to terminate the worker due to the error and invokes the effective handler for that thread. If no custom handler is set, the standard runtime prints the exception details and stack trace to `System.err` via the `ThreadGroup` mechanism.

Compare this with the following snippet:

```java
Thread worker = new Thread(() -> {
    try {
        riskyOperation();
    } catch (IllegalStateException ex) {
        reportAndRecover(ex);
    }
});
```

This is also an illustrative snippet, with `riskyOperation` and `reportAndRecover` defined by the application. If `catch` actually handles the exception and does not throw a new one, the handler is not invoked, because the exception is no longer "uncaught".

Key distinctions to make:

- **Exception caught inside the thread:** `catch` code can handle it, alter the outcome, perform a controlled retry, or decide to terminate.
- **Exception not caught and escaping the thread:** `UncaughtExceptionHandler` is invoked as a final reporting mechanism; the thread does not jump back to continue from the failing statement.
- **Exception caught and stored by a framework/task wrapper:** no exception may escape the worker thread; the caller retrieves the failure via `Future`, `CompletionStage`, or a framework callback.

One failing thread does not automatically stop all other threads. The application may continue running in an inconsistent state if the terminated thread was a critical component; therefore, a handler may be only one part of a broader monitoring system.

## 2. The Thread.UncaughtExceptionHandler Interface

The nested interface in `java.lang.Thread` has the method:

```java
@FunctionalInterface
public interface UncaughtExceptionHandler {
    void uncaughtException(Thread thread, Throwable error);
}
```

The snippet above describes the API signature for study purposes; do not redefine the JDK interface in an application program.

Meaning of the two parameters:

| Parameter | Meaning | What is it used for? |
| --- | --- | --- |
| `Thread thread` | The thread where the exception was uncaught | Record the thread name, ID, or metadata to locate the failing component. |
| `Throwable error` | The exception or error that escaped the thread | Record the error type, message, stack trace, cause, and suppressed exceptions if needed. |

Because the second parameter is `Throwable`, the handler can receive both `RuntimeException` and `Error` such as `AssertionError` or `OutOfMemoryError`. **Do not attempt to handle every `Error` as a recoverable business error.** When JVM resources are exhausted, even logging or allocating additional memory may fail.

A handler can be installed using a lambda:

```java
Thread.UncaughtExceptionHandler handler = (thread, error) -> {
    System.err.println("Luồng lỗi: " + thread.getName());
    error.printStackTrace(System.err);
};
```

This is a valid snippet when placed in an appropriate method or initializer. In production environments, structured loggers and observability systems are typically used; do not rely on console output as an application contract.

## 3. Registering Per-Thread and Application-Wide Handlers

Java provides two primary configuration points:

**Per-thread handler:**

```java
Thread thread = new Thread(task, "import-worker");
thread.setUncaughtExceptionHandler((t, e) -> {
    System.err.println(t.getName() + " gặp lỗi: " + e);
});
thread.start();
```

This snippet assumes `task` is already defined. The handler is set **before `start()`** to avoid a race condition between when the thread begins failing and when the handler is registered. The handler is attached to a specific `Thread` instance.

**Shared default handler:**

```java
Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
    System.err.println("Uncaught trong " + t.getName() + ": " + e);
});
```

The default handler is a static, JVM-wide configuration that broadly affects many threads using the default handling path. In applications with multiple libraries/frameworks, changing it may affect existing error-reporting mechanisms. It should only be set at the application startup boundary when you own that configuration.

API points to remember:

- `thread.setUncaughtExceptionHandler(handler)` attaches a dedicated handler to the thread; `null` can be passed to fall back to the default mechanism.
- `thread.getUncaughtExceptionHandler()` returns the handler attached directly, or the corresponding `ThreadGroup` if none is attached directly. **Do not assume** the returned value is always the currently set default handler.
- `Thread.setDefaultUncaughtExceptionHandler(handler)` sets the default handler; `Thread.getDefaultUncaughtExceptionHandler()` reads that value.
- When a custom `ThreadGroup` or a dedicated thread-management environment is present, the error-reporting flow also depends on how the group/framework handles it.

## 4. JVM Handler Selection Order

For a thread terminating due to an uncaught exception, the basic resolution order is:

1. If the thread has a handler set directly via `setUncaughtExceptionHandler`, the JVM invokes that handler.
2. Otherwise, the thread uses its `ThreadGroup` as its uncaught-exception handler.
3. The default implementation of `ThreadGroup.uncaughtException` may delegate to the parent group; at the root group, it may forward to the default handler if one is set.
4. If no suitable default handler is present, the standard `ThreadGroup` implementation typically prints error details to `System.err`. Special rules apply to `ThreadDeath`.

Key takeaway: **a per-thread handler has higher effective priority than the default handler** under the mechanism above. However, do not assume every thread will definitely reach the default handler: a `ThreadGroup` overriding `uncaughtException` may handle it differently, and frameworks may proactively catch errors before an exception escapes the thread.

Conceptual diagram:

```text
Throwable escapes Thread execution
              |
              v
Does Thread have its own handler?
       /               \
     Yes               No
     |                  |
     v                  v
Per-thread handler  ThreadGroup handles it
                        |
                 May delegate to parent group
                        |
                 May use default handler
                        |
               Fallback via ThreadGroup
```

The handler is notified only when the failure **actually reaches the thread termination boundary**. A `throw` statement inside a task does not guarantee the handler will be called if an outer layer has already caught the exception.

## 5. Complete Java 17 Example: Default and Per-Thread Handlers

The following example creates two threads sequentially. The first thread has no dedicated handler, so it uses the default handler in a standard Java environment; the second thread has a per-thread handler. Both throw uncaught exceptions. `join()` makes `main` wait for each thread to finish, making the output line order predictable.

Create `UncaughtHandlerDemo.java`:

```java
public class UncaughtHandlerDemo {

    public static void main(String[] args) throws InterruptedException {
        Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();

        try {
            Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
                System.out.println(
                    "DEFAULT " + thread.getName()
                        + " " + error.getClass().getSimpleName()
                        + ": " + error.getMessage()
                );
            });

            Thread first = new Thread(() -> {
                throw new IllegalStateException("boom A");
            }, "default-worker");

            first.start();
            first.join();

            Thread second = new Thread(() -> {
                throw new IllegalArgumentException("boom B");
            }, "custom-worker");

            second.setUncaughtExceptionHandler((thread, error) -> {
                System.out.println(
                    "CUSTOM " + thread.getName()
                        + " " + error.getClass().getSimpleName()
                        + ": " + error.getMessage()
                );
            });

            second.start();
            second.join();

            System.out.println("MAIN finished");
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(previous);
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 UncaughtHandlerDemo.java
java UncaughtHandlerDemo
```

Standard output in a typical Java runtime:

```text
DEFAULT default-worker IllegalStateException: boom A
CUSTOM custom-worker IllegalArgumentException: boom B
MAIN finished
```

Analysis:

- `first` has an exception escaping `Runnable` and no per-thread handler; the default handler prints the line starting with `DEFAULT`.
- `second` has a per-thread handler attached **before** starting, so the line starts with `CUSTOM`. The default handler does not process this same exception in the standard flow.
- Calling `join()` on each thread blocks `main` until that thread terminates. In this example, there is no race when `main` prints `MAIN finished` because each thread has already completed.
- `finally` restores the previous default handler to limit global side effects if the example is run in an integrated environment. A real application should not repeatedly swap the default handler per task.
- The handlers here intentionally print minimal details without a full stack trace so the output is easy to inspect. In real operations, stack traces along with cause/suppressed exceptions are usually helpful for diagnosis.

`main` declares `throws InterruptedException` because `join()` is a blocking operation with that checked exception. An `InterruptedException` on `main` is a separate concern and is **not** the `IllegalStateException`/`IllegalArgumentException` that escaped the workers. If `main` is interrupted while waiting, handling should follow the program's interruption policy.

## 6. Where Does the Handler Run and What Can It Do?

Typically, the JVM invokes `uncaughtException(thread, error)` on the thread that is terminating due to the error; it does not spawn a dedicated "rescue thread" to run application logic. Consequently, heavy or blocking work inside the handler can delay thread termination, hold onto resources, or cause deadlocks under adverse conditions.

A reasonable handler usually only:

- Records the failure along with thread identity, exception type, and safe context.
- Notifies a monitor or coordinator (if the application design includes one).
- Triggers a policy to mark a component unhealthy or request system shutdown, with safety and consistency in mind.
- Keeps the handler minimal, avoids triggering secondary errors, and does not assume all external systems are still operational when the JVM is low on resources.

A handler **cannot** rewind the instruction pointer back to the throwing line, cannot restore unwound stack frames, and cannot turn a dying thread back into a normally running one. To re-run a task, a scheduler or supervisor must create a new job/thread instance under a clear policy.

The Javadoc for `Thread.UncaughtExceptionHandler` specifies that any exception thrown by `uncaughtException` itself will be **ignored** by the JVM. Therefore, do not design systems assuming that a logger/handler failure will be forwarded to a backup handler.

If the handler itself throws an error:

```java
thread.setUncaughtExceptionHandler((t, e) -> {
    throw new IllegalStateException("handler also failed");
});
```

This is only an illustrative snippet, assuming `thread` exists in an appropriate context. Handler errors should not be relied upon as a dependable error-reporting mechanism; keep the handler simple and ensure an operational strategy exists when logging fails.

## 7. Core Difference: Direct Thread vs. ExecutorService.submit

A common misconception is thinking **every exception thrown in an async task will reach `UncaughtExceptionHandler`**.

Consider:

```java
Thread direct = new Thread(() -> {
    throw new IllegalStateException("direct failed");
});
direct.start();
```

An uncaught exception can reach `direct`'s handler.

However, when using:

```java
Future<?> future = executor.submit(() -> {
    throw new IllegalStateException("task failed");
});
```

This snippet assumes `executor` has already been created. With standard `ExecutorService.submit`, the task is typically wrapped in a `FutureTask`. The task's exception is **caught and recorded inside the `Future`**. The executor's worker can continue processing other work; the per-thread handler usually **does not receive** this task-level error.

The caller needs to call `future.get()` to observe the failure; for a task exception, `get()` throws `ExecutionException` with the root cause in `getCause()`. If the caller ignores the `Future`, the failure may go unobserved even though the task actually failed.

### Complete Java 17 Example with submit and Future

Create `FutureFailureDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> result = executor.submit(() -> {
                throw new IllegalStateException("task failed");
            });

            try {
                result.get();
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println(
                    "FUTURE " + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage()
                );
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
```

Stdout:

```text
FUTURE IllegalStateException: task failed
```

Explanation:

- `submit` returns a `Future`, which stores the completion status and failure of the task.
- `result.get()` waits for the task to complete and throws `ExecutionException` when the task fails.
- `ExecutionException.getCause()` holds the original `IllegalStateException`; the caller can decide to retry, roll back, report the error, or halt the workflow.
- `executor.shutdown()` stops accepting new tasks and allows already-submitted tasks to finish; `shutdown()` does not mean waiting for all tasks to complete. In this example, `get()` already waited for that specific task, so the output is deterministic.
- `UncaughtExceptionHandler` is not needed to receive errors caught by `submit`. If automatic logging for all tasks is desired, it must be designed at the task-wrapper level, `Future` result level, or via executor observation hooks.

`result.get()` can also throw `InterruptedException` if the waiting thread is interrupted; `main` declares this checked exception. If the task is cancelled, `get()` can throw `CancellationException` (unchecked), which is distinct from `ExecutionException` caused by task failure.

## 8. ExecutorService.execute and Differences from submit

Two ways of submitting a `Runnable` to an executor can change how exceptions are observed:

| Execution Approach | Common Failure Observation Mechanism | Notes |
| --- | --- | --- |
| `new Thread(task).start()` | Exceptions escaping `run()` can reach the uncaught handler | The thread terminates when an exception escapes. |
| `executor.execute(task)` | In standard `ThreadPoolExecutor`, uncaught unchecked exceptions in the task can escape the worker and be reported via the worker's handler/logging | Details depend on executor implementation, `ThreadFactory`, and wrappers; do not rely solely on the handler. |
| `executor.submit(task)` | Exceptions are stored in the `Future`; caller observes via `get()` | Failure signals can be lost if no one inspects the `Future`. |
| `CompletableFuture.supplyAsync(...)` | Failures are recorded in the `CompletableFuture` | Observed via `whenComplete`, `handle`, `exceptionally`, or `join/get`. |

A `ThreadPoolExecutor` can use the `afterExecute(Runnable r, Throwable t)` hook to observe tasks; however, for a `FutureTask` created by `submit`, the `t` parameter can be `null` even when the task failed because the error was already stored in the `Future`. Implementations must inspect the `Future` and handle `ExecutionException` intentionally if taking this approach. Do not call `get()` on an incomplete `Future` from a hook in situations that could cause unnecessary waiting; even for completed tasks in `afterExecute`, interruption/cancellation must still be handled carefully.

More importantly, `ExecutorService` is a task-execution abstraction, not a `Thread` always owned by the client. Worker threads may be reused, replaced, or managed by a framework; attaching a handler directly to a worker does not mean all task failures will be observed.

## 9. CompletableFuture and Asynchronous Exceptions

`CompletableFuture` is a clear example of a failure recorded as an **asynchronous result** rather than escaping a thread's entry point.

```java
CompletableFuture<Integer> stage =
    CompletableFuture.supplyAsync(() -> {
        throw new IllegalArgumentException("bad input");
    });

stage.whenComplete((value, failure) -> {
    if (failure != null) {
        // Observe the stage failure; do not rely on the worker's handler.
    }
});
```

This is an illustrative snippet, assuming `import java.util.concurrent.CompletableFuture`. Failures may be represented as a `CompletionException` wrapping the cause depending on the observation point and stage chain shape. `join()` typically throws `CompletionException` when a stage completes exceptionally; `get()` uses `ExecutionException` for normal failures. Handling code should follow the stage's API contract.

Avoid creating `whenComplete` callbacks just to log and discard the result without controlling side effects or downstream flow. When an error should affect business decisions, propagate it through the result-handling pipeline using a consistent strategy.

## 10. Thread.join Does Not Propagate Worker Exceptions to the Caller

`Thread.join()` only waits for the thread to finish. It **does not rethrow the worker's uncaught exception** on the thread calling `join()`.

Example with a manually created worker:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("worker failed");
});
worker.start();
worker.join();

// The thread has finished, but join has no return type to report worker failure.
```

The snippet above assumes it is inside a method that handles `InterruptedException`. After `join()`, `worker.isAlive() == false` does not indicate whether the worker succeeded or failed. A handler can log the error, but a caller needing to distinguish outcomes must use a state-exchange mechanism such as `Future`, `BlockingQueue`, `CountDownLatch` paired with a result holder, or a wrapper returning a structured result.

If the caller needs to receive or handle failure as a computation result, using `Future` or composition APIs is generally more appropriate than using a global uncaught handler as an error-propagation channel.

## 11. Special Case: Handler Runs on a "Dying" Thread

The right mental model is that the handler receives notification when the thread can no longer continue its original execution path. This leads to several design decisions:

**Do not arbitrarily retry directly inside the handler.** If the thread just died from an unexpected error, re-running a task with side effects can duplicate operations, write data twice, or fall into an infinite error loop. Retries require conditions, backoff, idempotency, and attempt limits.

**Do not rely on the handler to release all resources.** Resources opened in a thread should be closed via `try-with-resources`/`finally` close to where they are created and owned. The handler does not know full ownership and may not run in all types of process termination. It may also be called when program state is already severely corrupted.

**Do not treat the handler as a place to repair shared state.** At the moment of failure, invariants may already be broken. A supervisor can mark the component unhealthy and stop the pipeline rather than arbitrarily continuing.

**Avoid cross-locking that can easily lead to deadlocks.** If the error occurred while the thread held a monitor/lock or was participating in shutdown, calling back into that same subsystem from the handler can hang. Prefer minimal recording and forwarding the failure event to an appropriate monitoring system.

## 12. Exceptions, Errors, Interruption, and Shutdown

Different kinds of task termination behave differently:

| Scenario | Is the uncaught handler necessarily called? | Handling Guidance |
| --- | --- | --- |
| `RuntimeException` escapes `Thread.run()` | Yes, via the normal thread uncaught-exception mechanism | Record the cause and component state. |
| `Error` escapes the thread | Handler receives `Throwable`, though reporting may be unreliable during severe errors | Avoid reckless recovery; consider fail-fast. |
| `InterruptedException` caught and handled properly | No, if no new exception escapes the thread | Follow cancellation policy; restore the interrupt flag when appropriate. |
| `InterruptedException` wrapped as unchecked and escapes `run()` | Handler may be called since the new unchecked exception is uncaught | Preserve cause and interrupt policy. |
| `FutureTask` catches a `submit` task error | Typically no | Inspect `Future.get()` and its cause. |
| `Thread.stop()` (deprecated, unsafe API) | Should not be used for error/cleanup management | Use cooperative cancellation. |
| JVM/OS forcibly terminates the process | No guarantee the handler or `finally` will run | Rely on recovery, supervision, and out-of-process resource management when needed. |

`InterruptedException` is a checked exception and `Runnable.run()` does not declare checked exceptions, so tasks usually need to catch it. To terminate cleanly, you can restore the interrupt and `return`:

```java
@Override
public void run() {
    try {
        blockingOperation();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

This is an illustrative snippet; `blockingOperation` is provided by the application. This case does not produce an uncaught exception and the handler is not invoked. Whether to propagate or stop depends on the thread's semantics.

`ThreadDeath` is a special `Error` historically associated with `Thread.stop()`; `ThreadGroup` has special fallback behavior for it. Do not rely on this legacy mechanism to cancel threads.

## 13. Attaching Handlers via ThreadFactory in Multi-Worker Applications

If a component genuinely **manages thread creation**, you can configure a per-thread handler in a `ThreadFactory`:

```java
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "service-worker");
    thread.setUncaughtExceptionHandler((t, error) -> {
        System.err.println(t.getName() + " failed: " + error);
    });
    return thread;
};
```

This is an illustrative snippet (requires `import java.util.concurrent.ThreadFactory`). `ThreadFactory` is often passed to executors like `Executors.newFixedThreadPool(int, ThreadFactory)` to apply configuration to created workers.

However, **the factory only assigns a handler to the thread**; it does not cause exceptions stored in a `Future` by `submit` to naturally escape. Do not confuse "every worker has a handler" with "every task exception is observed".

Production designs typically combine:
- A handler for *uncaught* thread failures.
- `Future` result handling or `CompletableFuture` pipelines for task failures.
- Logging/metrics/tracing with task identifiers and sensitive-data sanitization.
- Appropriate stop/restart policies at the service/supervisor layer, not inside individual handlers.

`ThreadFactory` is also used to assign recognizable names and thread attributes as needed. Do not arbitrarily set `Thread.setDaemon(true)` if it alters application shutdown semantics without understanding the consequences.

## 14. Java 21+ Virtual Threads and Knowledge Scope

The examples here use **platform threads**, running on Java 17+. Starting in Java 21, virtual threads are also `Thread` instances and have uncaught-exception handling mechanisms, but lifecycle and task management rely more heavily on structured concurrency or executors. If a virtual-thread task is wrapped by an abstraction that stores results, distinguish task failures from uncaught exceptions according to that abstraction.

Do not assume that a failing virtual thread will halt the entire task group or automatically propagate exceptions to the parent thread. Read the specific contract of the API creating and awaiting the tasks; task groups and cancel/join mechanisms have their own semantics.

## 15. What Should a Well-Behaved Operational Handler Record?

A useful incident record may include:

- Timestamp and process/service identity.
- Thread name/ID, worker role, task or correlation ID if available.
- `Throwable` type, message, stack trace, cause chain, and suppressed exceptions.
- Severity level or component status (healthy/degraded/unavailable).
- Information that has been **sanitized** so tokens, credentials, personal data, or sensitive content are not exposed.

Exception messages are not a stable data API. Do not match against uncaught exception messages to decide on retries. If a task can fail due to business rules, convert it into a structured error **before** it reaches the uncaught handler.

A handler that only prints `error.getMessage()` may lose the deeper root cause; conversely, printing the entire exception into a public log system may leak data. Choose an appropriate logger and access permissions for the environment.

## 16. Common Pitfalls

**Treating the handler as a `catch` to keep the thread running.** Wrong because the handler runs while the thread is terminating due to an uncaught exception. Recovery logic belongs in the workflow or supervisor.

**Registering only a default handler and assuming `submit` is monitored.** `submit` may capture exceptions into a `Future`. You must inspect results or wrap tasks.

**Using `join` as an error-detection mechanism.** `join` only waits for completion; it does not report success/failure.

**Attaching the handler after `start`.** The thread may throw an exception before attachment. Set the handler before starting or via a factory.

**Resetting the default handler from inside individual libraries.** This is a JVM-wide setting and can conflict with frameworks or application code. If a library needs to observe its own errors, it should generally manage its own threads/tasks and handlers.

**Handler logging and then throwing an exception itself.** Exceptions thrown by the handler are ignored by the JVM; even the initial report can be lost if logging did not finish.

**Doing blocking or risky work inside the handler.** The handler may run in the context of a failed thread that still involves locks; thread termination may be delayed or deadlocked.

**Calling `System.exit` unconditionally in the handler.** This can terminate the entire process due to a non-critical worker failure. Service-wide shutdown policies must be decided by the operational layer and criticality rules.

**Catching `Throwable` in every `Runnable` just to prevent the handler.** This can mask serious `Error`s and break error observability. Only catch what the task can genuinely handle.

**Neglecting resource management on uncaught errors.** The handler is not a substitute for `finally` or `try-with-resources`; cleanup must stay with the resource owner.

## 17. Testing Handlers and Error-Observation Flows

Tests should rely on public behavior and avoid matching default stack-trace formatting across JVMs:

1. For a `Thread` directly throwing `IllegalStateException`, attach a per-thread handler that captures the `Throwable` into a thread-safe structure; call `start` then `join` and verify the handler was invoked with the expected thread/name/cause.
2. For the default handler, save the previous handler and restore it in `finally`; avoid letting parallel tests be affected by global configuration. If the runtime or a custom `ThreadGroup` has different semantics, the test should state clear environment assumptions.
3. Verify that a per-thread handler is selected over the default handler in the standard thread model.
4. For `ExecutorService.submit`, create a failing task and verify `Future.get` throws `ExecutionException` with the right cause; do not use whether a handler logged or not as the sole assertion.
5. For `CompletableFuture`, verify the stage completes exceptionally and the handling callback receives the expected state.
6. For thread resource cleanup, verify `try-with-resources` or `finally` executes even when the task throws an exception.
7. Ensure the handler does not hang the entire process if the logger or error-observation component fails.

Real unit tests can use `AtomicReference<Throwable>` or `BlockingQueue<Throwable>` to capture exceptions from the handler without relying on console output. Set appropriate timeouts on `join` or `Future.get` in CI environments so tests do not hang indefinitely if a worker deadlocks.

## 18. Self-Check

**Question 1:** `Runnable.run` throws an uncaught `IllegalArgumentException`, and the thread has a per-thread handler. Can the handler make `run` continue from the line after `throw`?

**Answer:** No. The handler is the final error notification point while the thread is terminating. To continue or retry, the application must have its own logic and an appropriate execution context.

**Question 2:** For the same `IllegalStateException`, why can `new Thread(task).start()` invoke the handler while `executor.submit(task)` usually does not?

**Answer:** With a direct thread, the exception can escape the thread's entry point. With `submit`, the task is wrapped in a `FutureTask` and the error is stored in the `Future` for the caller to retrieve via `get`; the worker does not necessarily experience an uncaught exception.

**Question 3:** Does `join()` returning normally mean the worker succeeded?

**Answer:** No. `join()` waits for the thread to finish and does not propagate worker exceptions. A separate status/result channel is needed.

**Question 4:** Why should a library not arbitrarily replace the default handler?

**Answer:** The default handler is a JVM-wide configuration that can affect framework threads or other parts of the application. A library should manage its own errors using its own handlers/thread factories or task results, leaving the default policy to the application owner.

**Question 5:** A thread writing to a file throws an uncaught exception. Should the handler directly close all files opened by that thread?

**Answer:** You should not rely on the handler as a resource owner. The code owning the file must use `try-with-resources`/`finally` for properly scoped cleanup. The handler's job is to observe the failure and support operational handling.

## 19. Design Takeaways

`Thread.UncaughtExceptionHandler` answers the question **"what happens when a Throwable escapes a thread uncaught?"**: the runtime selects a handler and reports the failure before the thread terminates. It **does not** replace `catch`, does not automatically propagate errors to `join`, does not replace `Future`/`CompletableFuture` handling mechanisms, and does not make a thread self-healing.

For manually created threads, set a per-thread handler before `start`, and optionally use an application-level default handler for broad observation. For executors and asynchronous pipelines, prefer observing errors through the **task's result contract**. Always perform cleanup near the resource owner and use a supervisor or service policy to decide the impact of a failing thread.
# Naming Threads and Setting UncaughtExceptionHandler in Java

## 1. Lesson Objectives

When multiple threads run concurrently, thread names help developers identify **which thread is performing which task** in logs, debuggers, thread dumps, and monitoring tools. `Thread.UncaughtExceptionHandler` provides a **final error-recording point** when a `Throwable` escapes a thread's run method uncaught.

After this lesson, you should be able to:

- Create and rename a `Thread`; choose meaningful names for concurrent processing.
- Read the current thread's name using `Thread.currentThread().getName()` and distinguish a thread name from a task identifier.
- Set a handler for an individual thread or the JVM default handler, and understand the handler selection order.
- Understand when the handler is invoked, and when an error is held in a `Future` or `CompletableFuture` and does not go through the handler.
- Write runnable Java 17+ examples, then verify thread names and exception paths.

This lesson focuses on the **Thread API and general Java concurrency**, without covering asynchronous mechanisms or executor configuration in Spring.

## 2. Why Do Thread Names Matter?

The JVM can run many threads with different responsibilities: receiving data, processing files, computing, reading queues, cleaning up, or performing background work. If logs only show `Thread-0`, `Thread-1`, readers have a hard time knowing a thread's origin and role when an error occurs.

For example, a message like:

~~~text
[import-parser-2] Invalid input at row 18
~~~

is usually much easier to trace than:

~~~text
[Thread-7] Invalid input at row 18
~~~

Thread names are especially useful when:

1. **Reading thread dumps:** distinguishing threads waiting on I/O, holding locks, waiting on a queue, or stuck.
2. **Filtering logs by component:** grouping worker logs by name prefix.
3. **Debugging in an IDE/JFR:** associating a thread with a task group, pool, or feature.
4. **Investigating unexpected errors:** the handler can log both the thread name and the exception stack trace.

A thread name is **descriptive and observability metadata**, not a globally guaranteed unique identifier, nor a synchronization, security, or access-control mechanism. Two threads can still have the same name; renaming a thread does not change execution order or code thread-safety.

## 3. APIs for Naming and Reading Thread Names

### 3.1. Naming a Thread at Creation Time

Two basic approaches:

~~~java
// Illustration: Runnable task is already declared.
Thread first = new Thread(task, "file-reader-1");
Thread second = new Thread(task);
second.setName("file-reader-2");
~~~

`new Thread(Runnable, String)` sets the name at creation time; `setName(String)` changes the name after creation. You should set the name **before `start()`** so that every event from the moment the thread starts carries the intended name. Neither approach runs the task by itself; calling `start()` is what launches a new thread of execution.

`Thread.getName()` reads the name of a `Thread` object. Inside a running task, `Thread.currentThread().getName()` returns the name of the **currently executing thread**. Avoid using an external `thread` variable instead of `currentThread()` when a task may run on multiple threads.

### 3.2. Renaming While a Thread Is Running

Java allows calling `setName` on an already started thread. However, the name can change between log statements, making trace correlation confusing. For reused workers in a pool, renaming per request and forgetting to restore it also causes subsequent task logs to carry the previous task's name.

If you truly need to rename a thread temporarily, restore it in a `finally` block:

~~~java
// Illustration inside a running task, not a standalone program.
Thread current = Thread.currentThread();
String previousName = current.getName();
try {
    current.setName("image-transform-temporary");
    processImage(); // Application-defined method.
} finally {
    current.setName(previousName);
}
~~~

In most systems, a more stable approach is to keep a fixed **worker name** and put the request ID, job ID, or correlation ID into a separate log/context structure. Never put sensitive data, tokens, or personal information in thread names because names can appear in thread dumps and observability systems.

### 3.3. Naming Conventions

A readable convention is `<component>-<role>-<sequence-number>`. For example:

| Name | Suggested Role |
| --- | --- |
| `import-parser-1` | First worker parsing imported data |
| `report-writer-2` | Second worker generating reports |
| `socket-reader-1` | Worker reading network data |
| `batch-cpu-3` | Worker performing computation |

Keep names short, stable, with a distinctive prefix, and do not mix **thread** names with **task** IDs. The sequence numbers in names do not indicate execution or completion order.

## 4. Example 1 — Naming and Catching Unhandled Errors (Java 17+)

Create the file `NamedThreadDemo.java`:

~~~java
public class NamedThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println(
                "Running: " + Thread.currentThread().getName()
            );
            throw new IllegalStateException("invalid payload");
        }, "import-validator-1");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            System.out.println(
                "Uncaught in " + thread.getName() + ": "
                + error.getClass().getSimpleName()
                + " (" + error.getMessage() + ")"
            );
        });

        worker.start();
        worker.join();
        System.out.println(
            "Main finished; worker isAlive=" + worker.isAlive()
        );
    }
}
~~~

Compile and run:

~~~bash
javac NamedThreadDemo.java
java NamedThreadDemo
~~~

Exact standard output (stdout):

~~~text
Running: import-validator-1
Uncaught in import-validator-1: IllegalStateException (invalid payload)
Main finished; worker isAlive=false
~~~

Explanation:

1. The name `import-validator-1` is assigned before `start()`, so `currentThread().getName()` inside the `Runnable` returns that name.
2. `IllegalStateException` escapes the run method without a `catch`. The JVM invokes the handler registered on `worker`.
3. The handler receives the `Thread` and `Throwable` objects, then prints the name, error type, and message.
4. `join()` makes the `main` thread wait for `worker` to finish, so the last line is printed after the worker finishes handling its abnormal exit path. `isAlive()` is `false` at that point.
5. The custom handler handled error reporting, so no default stack trace is printed by the default handler. In real systems, you should log the **full exception/stack trace** to a fault-tolerant logger; printing only `getMessage()` is not enough for diagnosis.

**Note:** The handler does not make the task succeed and does not restart the thread. After an uncaught exception escapes, the worker terminates. `join()` confirms that the thread has ended, not that the task succeeded; an explicit result/status channel is needed if business logic must know about failures.

## 5. How Does UncaughtExceptionHandler Work?

### 5.1. Interface and Trigger Timing

`Thread.UncaughtExceptionHandler` is a functional interface with the method:

~~~java
// API signature; not a standalone program.
void uncaughtException(Thread thread, Throwable error);
~~~

The JVM notifies the handler when a thread is about to terminate due to an **uncaught exception** — a `Throwable` that escaped the thread's execution path. `Throwable` includes both `RuntimeException` and `Error`; the handler may see severe errors like `OutOfMemoryError`, in which case it must not assume sufficient resources remain for logging or recovery.

The handler is **not invoked** merely because:

- A method throws an exception that is handled by `try/catch` in the same thread.
- A task finishes normally, returns from `run()`, or is asked to stop via a valid mechanism.
- A task reports an error through a channel that catches/holds exceptions, such as a `Future` from `submit()`.
- A plain `Thread.interrupt()` call occurs. Interruption is a cooperative signal; it does not automatically become an uncaught exception.

If you call `worker.run()` directly instead of `worker.start()`, the code runs on the calling thread without creating a new thread. An exception escaping `run()` propagates to the caller under normal Java rules; do not expect the `worker` object's handler to be used as when a thread actually dies from an exception.

### 5.2. Per-Thread Handler and Default Handler

| API | Scope | Usage |
| --- | --- | --- |
| `thread.setUncaughtExceptionHandler(handler)` | One specific thread | Record errors for a worker with a specific role |
| `thread.getUncaughtExceptionHandler()` | Inspect the handler applied directly to the thread | Returns the assigned handler; otherwise, returns the thread's `ThreadGroup` |
| `Thread.setDefaultUncaughtExceptionHandler(handler)` | Process-wide JVM default handler | Final fallback for threads without a dedicated handler |
| `Thread.getDefaultUncaughtExceptionHandler()` | Inspect the global default handler | May return `null` if not configured |

**Order matters:**

1. If the thread has an individual handler set via `setUncaughtExceptionHandler`, that handler is selected.
2. Otherwise, `Thread.getUncaughtExceptionHandler()` delegates handling to the thread's `ThreadGroup`. The default `ThreadGroup.uncaughtException` mechanism may delegate to the parent group, then to the JVM default handler (if any); if none is set, it may print the error to `System.err`.
3. A custom `ThreadGroup` can override `uncaughtException` and handle it differently. Therefore, do not assume the default handler will always run for every thread.

`ThreadGroup` is a legacy mechanism of the Thread API; for new code, prefer configuring handlers explicitly on threads or via a `ThreadFactory`, and managing lifecycles with an executor or appropriate construct.

### 5.3. Should You Set a Default Handler?

If an application wants a final error-reporting fallback for threads without their own handler, it can configure:

~~~java
// Illustration of startup configuration, not a standalone program.
Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    System.err.println(
        "Unhandled failure in thread: " + thread.getName()
    );
    error.printStackTrace(System.err);
});
~~~

This is a **global JVM state change**. Only the component that owns the application lifecycle should decide to install a default handler, typically at startup, after reviewing existing configuration and logging. Reusable libraries should not overwrite the application-wide default handler; multiple components overwriting it causes errors to route to unintended handlers.

Do not rely on a thread's `getUncaughtExceptionHandler()` returning the default handler directly: when no individual handler is set, it returns the `ThreadGroup` as described above.

## 6. Naming and Setting Handlers for Workers Created by ExecutorService

In programs with many tasks, you typically do not create a `Thread` manually for each task. `ExecutorService` manages workers; to name and attach a handler to **worker threads**, use a `ThreadFactory` when creating the executor.

A factory can do three things: create a new `Thread`, generate a name by role + sequence, and register an `UncaughtExceptionHandler` before the thread runs.

### 6.1. Distinguishing `execute()` and `submit()` When a Task Throws

This is a common source of confusion:

- With `execute(Runnable)` on a standard `ThreadPoolExecutor`, if `Runnable.run()` throws a `RuntimeException` out of the method, the worker can terminate abnormally and the worker's handler is invoked. The executor may replace the worker to maintain the pool.
- With `submit(Runnable)` or `submit(Callable)`, the executor typically wraps the task in a `FutureTask`. The exception is **captured as the failure state of the `Future`**. `future.get()` throws `ExecutionException` whose `getCause()` is the original error; the worker's handler **is not invoked merely because that task failed**.
- With `CompletableFuture`, an error can be stored in the failed completion state and observed via `join()`, `get()`, `handle()`, `exceptionally()`, or an appropriate error-handling branch; do not expect the uncaught handler by default.

The differences above describe the behavior of standard JDK executors, especially `ThreadPoolExecutor`. A custom `Executor` implementation may choose its own dispatch/error-handling behavior. Always understand the contract of the specific executor.

### 6.2. Example 2 — ThreadFactory, execute, and submit (Java 17+)

Create the file `ExecutorFailureDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger sequence = new AtomicInteger(1);
        AtomicInteger handlerCalls = new AtomicInteger();
        CountDownLatch handlerCalled = new CountDownLatch(1);

        ThreadFactory factory = task -> {
            Thread worker = new Thread(
                task,
                "report-worker-" + sequence.getAndIncrement()
            );
            worker.setUncaughtExceptionHandler((thread, error) -> {
                handlerCalls.incrementAndGet();
                System.out.println(
                    "Handler: " + thread.getName() + " -> "
                    + error.getClass().getSimpleName()
                );
                handlerCalled.countDown();
            });
            return worker;
        };

        ExecutorService executor =
            Executors.newSingleThreadExecutor(factory);

        try {
            Future<?> failed = executor.submit(() -> {
                throw new IllegalArgumentException("submit failure");
            });

            try {
                failed.get();
            } catch (ExecutionException error) {
                System.out.println(
                    "Future cause: "
                    + error.getCause().getClass().getSimpleName()
                );
            }
            System.out.println(
                "Handler calls after submit: " + handlerCalls.get()
            );

            executor.execute(() -> {
                throw new IllegalStateException("execute failure");
            });

            if (!handlerCalled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timed out waiting for uncaught handler"
                );
            }
            System.out.println(
                "Handler calls after execute: " + handlerCalls.get()
            );
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ExecutorFailureDemo.java
java ExecutorFailureDemo
~~~

When the two tasks run in order as written and the handler is invoked within the 5-second limit, stdout is:

~~~text
Future cause: IllegalArgumentException
Handler calls after submit: 0
Handler: report-worker-1 -> IllegalStateException
Handler calls after execute: 1
~~~

Why does it produce this output?

- `submit` creates a `Future` holding `IllegalArgumentException`; `get()` detects the error, but the executing thread does not terminate abnormally, so the handler counter remains 0.
- `execute` runs the `Runnable` directly according to `ThreadPoolExecutor` mechanics. `IllegalStateException` escapes the worker, causing it to terminate abnormally; the handler set in `ThreadFactory` is invoked.
- `CountDownLatch` lets `main` wait for the handler to actually run. Do not use `Thread.sleep(...)` to guess that the handler has run.
- `AtomicInteger` safely increments the name sequence number or handler counter if the factory/handler is called concurrently. A replacement thread created after an error may get the next sequence number.
- `shutdown()` and `awaitTermination(...)` release the executor in a controlled manner. `shutdownNow()` only **requests** interruption of running work; it does not guarantee immediate termination.

**Output scope:** This example runs with a standard JDK executor and assumes the machine is not hung or the scheduler is not delayed beyond 5 seconds. If the environment misses the deadline, the program throws a timeout error; it does not falsely print that the handler ran.

More importantly, even with a handler configured, **the application must still observe errors from `Future`**. If you call `submit` and ignore the `Future`, task failures are very easy to miss.

## 7. Writing Safe and Operationally Useful Handlers

### 7.1. What Should a Handler Do?

A useful handler typically collects the **thread name, exception class, message, stack trace**, and available safe context, and sends them to an appropriate error-logging sink. If process health alerts or metrics are needed, use only a short, fail-safe path.

Conceptual handling pattern:

~~~java
// Illustration; logger is provided by the application.
thread.setUncaughtExceptionHandler((failedThread, failure) -> {
    logger.error(
        "Uncaught error in thread " + failedThread.getName(),
        failure
    );
});
~~~

This snippet is **not standalone** because `thread` and `logger` must be initialized by the application. Passing the full `Throwable` object allows the logger to preserve the stack trace rather than logging only a single `getMessage()` line.

A handler should prioritize **not throwing new exceptions, not blocking for long, and not waiting on locks that might be held by the failing thread**. If `uncaughtException` itself throws an exception, the JVM **ignores the exception thrown by the handler**, potentially losing the original error information. When the heap is exhausted or the process is in a critical state, building large strings, making synchronous network calls, or allocating many objects for logging may fail.

### 7.2. Handlers Do Not Replace Business Error Control

| Handling Location | Purpose |
| --- | --- |
| `try/catch` where the error is understood | Recover or translate the error into a business result |
| `Future.get()` / `CompletableFuture` | Know whether an asynchronous task succeeded or failed |
| `UncaughtExceptionHandler` | Record errors that escape a thread's execution path |
| Executor/task lifecycle management | Decide retries, cancellation, resource limits, and shutdown |

Do not automatically retry a task from an uncaught handler: state may have been partially modified, data may be inconsistent, or the task may not be idempotent. Retrying must belong to a controlled business policy.

A severe error in one thread does not necessarily terminate the JVM; other threads may continue running. That **does not mean the application is still healthy**. The system needs observability and a mechanism to decide serving status based on the error's severity.

### 7.3. Coordinating with Interruption and Cancellation

`Thread.interrupt()` sends an interrupt signal; it does not invoke `UncaughtExceptionHandler` by itself. For example, a task that catches `InterruptedException` and exits normally will not trigger the handler. When `InterruptedException` cannot be rethrown, you should usually restore the flag with `Thread.currentThread().interrupt()` and exit the task cleanly.

Only if a task throws a `RuntimeException` from its interrupt-handling logic and that exception actually escapes the worker will the handler be called. Therefore, do not use the handler to track every task cancellation or stop.

## 8. Common Pitfalls

### Pitfall 1 — Calling `run()` Instead of `start()`

~~~java
// Illustrates the difference; not a standalone program.
Thread t = new Thread(task, "background-1");
t.run();    // Runs immediately on the calling thread.
t.start();  // Actually starts a separate thread (if not started before).
~~~

The snippet above compares the two methods; in a real program, **choose the appropriate call**. `start()` cannot be called a second time on the same thread object, or it will throw `IllegalThreadStateException`.

### Pitfall 2 — Setting a Handler and Assuming Every Exception Passes Through It

`try/catch`, `FutureTask`, and completion mechanisms may already capture errors. When running tasks through an executor, use `Future.get()` or a result-handling pipeline, and have a mechanism to detect failed tasks at the business layer.

### Pitfall 3 — Setting the Default Handler from a Library

`Thread.setDefaultUncaughtExceptionHandler` changes the policy for **every thread in the JVM** that follows the default path. Library code does not own the entire application lifecycle and should not overwrite the global handler.

### Pitfall 4 — Logging an Error Without Its Stack Trace

Printing only `exception.getMessage()` loses the throw site, call stack, and `getCause()` chain. In production code, pass the full `Throwable` to the logging system or use `printStackTrace` when appropriate.

### Pitfall 5 — Naming Threads per Request and Reusing Them in a Pool

Pool workers serve many tasks over time. Names should describe the **worker's role**; request/correlation IDs should go into a log context with a clear lifecycle. If you rename temporarily, restore it in `finally`.

### Pitfall 6 — Using the Handler as a Recovery or Error-Isolation Mechanism

The handler is the final reporting layer; it does not guarantee a task can be re-run, does not roll back side effects, does not protect shared mutable state, and does not guarantee safe continued operation after a severe `Error`.

## 9. Relation to Java 21+ and Virtual Threads

Java 21 made virtual threads a standard feature. A virtual thread is still a `Thread` object and can have a name and an `UncaughtExceptionHandler`, but they are typically organized as **one virtual thread per task** rather than a pool of reused platform workers.

An API illustration **for Java 21+ only** (does not run on Java 17):

~~~java
ThreadFactory factory = Thread.ofVirtual()
    .name("io-task-", 0)
    .uncaughtExceptionHandler((thread, error) -> {
        error.printStackTrace(System.err);
    })
    .factory();
~~~

This snippet only declares a `ThreadFactory`; it does not create or start a task yet. In systems using virtual threads, distinguish the task/virtual thread name from the carrier thread name, and still observe errors in `Future` if an executor wraps results. Naming helps with diagnostics, but it does not replace task management and resource limits.

## 10. Implementation and Self-Check Checklist

Before deploying:

1. Does each group of threads have a **role-based name** that is easy to recognize in logs/thread dumps?
2. Are worker names stable when threads are reused? Are personal data and secrets kept out of names?
3. Are individual handlers set **before `start()`** or via `ThreadFactory` before the executor uses the worker?
4. Does the application understand how the default handler differs from per-thread handlers and the `ThreadGroup` path?
5. For `submit` and `CompletableFuture`, are errors retrieved and handled through the result channel?
6. Does the handler log stack traces without causing additional errors, deadlocks, or prolonged blocking?
7. When a thread dies abnormally, is there a monitoring mechanism to decide on retries, job failure, or process health impact?
8. Does the executor have a shutdown plan and a bounded termination timeout?

**Knowledge-check scenarios:**

- A task created by `new Thread(task, "reader-1")` throws an uncaught `IllegalStateException` and has an individual handler assigned. **Outcome:** the individual handler is invoked, receiving thread `reader-1` and the exception; the thread terminates.
- A task created by `executor.submit(...)` throws `IllegalArgumentException`. **Outcome:** with a standard JDK executor, `Future.get()` throws `ExecutionException` with cause `IllegalArgumentException`; the worker's handler is not invoked merely because that task failed.
- A thread pool serves many requests, and each request needs its own ID. **Appropriate choice:** name workers by role, and put the request ID into the log context with clear scoping/cleanup.

Thread names help observe *who is executing*; `UncaughtExceptionHandler` helps record *which error escaped a thread*. Both tools aid concurrency diagnostics, but system correctness and reliability still depend on managing task results, shared state, resource limits, and thread/executor lifecycles.

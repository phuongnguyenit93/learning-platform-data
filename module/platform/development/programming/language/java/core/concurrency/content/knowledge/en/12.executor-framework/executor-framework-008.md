# ThreadFactory and UncaughtExceptionHandler in the Java Executor Framework

## 1. Why care about how threads are created and how errors are reported?

An `ExecutorService` accepts tasks and decides when and on which worker they are executed. Application developers often only call `execute(...)` or `submit(...)`, but in production operations you also need to answer:

- How are worker threads **named** so that thread dumps and logs are readable?
- Under which **ThreadGroup**, daemon flag, priority, context class loader, and handler are workers created?
- If a task throws an unhandled `RuntimeException`/`Error`, **who is notified**?
- If a task run via `submit(...)` fails, why might `UncaughtExceptionHandler` not be invoked?
- When a worker terminates abnormally, does the executor create another worker? Is the failed task automatically retried?
- How do we record errors **without breaking shutdown policies and resource management**?

Two APIs sit at the center:

1. **`java.util.concurrent.ThreadFactory`**: the strategy for creating `Thread` objects for an executor. A factory does not manage queues, does not run tasks itself, and does not decide how task failures are represented.
2. **`Thread.UncaughtExceptionHandler`**: a thread-level callback invoked when a thread **is terminating due to an uncaught exception**. It is not a general-purpose callback for every failed task in an executor.

**Core distinction:** Calling `ThreadPoolExecutor.execute(Runnable)` with a `Runnable` that throws an exception can allow that exception to escape the worker and reach the uncaught handler. By contrast, `submit(...)` typically wraps the task in a `FutureTask`, so the exception is **stored in the Future** rather than escaping as an uncaught exception from `Thread.run()`.

This lesson is scoped to the **Executor Framework and general Java concurrency**. The examples use standard JDK 17+ APIs and do not rely on external frameworks.

### Learning Objectives

After this lesson, you will be able to:

1. Write a `ThreadFactory` that gives workers readable names and attaches a handler when needed.
2. Understand why a factory must return an **unstarted thread**, and why a factory may be called multiple times over a pool's lifetime.
3. Distinguish how exceptions flow through `execute()`, `submit()`, `Future.get()`, and `Thread.UncaughtExceptionHandler`.
4. Know how to extend `ThreadPoolExecutor.afterExecute(...)` to monitor tasks properly, including errors captured by a Future.
5. Manage worker failure, replacement, shutdown, and retries, and avoid mistaking the handler for a task recovery mechanism.
6. Test error reporting with explicit observation channels rather than relying on log ordering across multiple threads.

## 2. ThreadFactory: Responsibilities and Contract

### 2.1. A simple interface with significant impact

`ThreadFactory` is a functional interface:

~~~java
// API signature, not a standalone program.
public interface ThreadFactory {
    Thread newThread(Runnable r);
}
~~~

The executor passes an internal `Runnable` that needs to be executed to `newThread(r)`. The factory creates and **returns an unstarted Thread**. The executor is responsible for calling `start()` when appropriate.

A factory can configure:

- **Name** with a functional prefix and an incrementing number: `orders-worker-1`, `orders-worker-2`.
- **Daemon** when there is a clear lifecycle reason; generally avoid daemon threads for critical work that must undergo controlled shutdown.
- **Priority** only if you truly understand scheduler limitations; do not use thread priority to guarantee business-level ordering.
- **UncaughtExceptionHandler** to record certain uncaught errors at the thread level.
- ThreadGroup or context class loader when required by the environment and ownership, not arbitrarily as a workaround for application bugs.

A factory **must not** call `start()` on the thread itself, call `r.run()` directly inside the factory, or return an already-started thread. Those actions violate the executor's assumptions about when workers start and can cause `IllegalThreadStateException` or incorrect behavior.

### 2.2. Do not assume one thread is created per task

`newFixedThreadPool(2, factory)` can reuse the same two workers to run a great many tasks. `ThreadFactory.newThread(...)` is called **when the executor needs to create a worker**, not on every `submit()` call.

Situations where the factory may be called again include:

- The pool does not yet have enough workers and needs a new one.
- A worker **terminates abnormally** and the pool needs to maintain its configured/target worker count.
- The pool scales or replaces workers according to `ThreadPoolExecutor` policies.

Conversely, the factory may **not be called** when a new task is queued and an existing worker executes it. Therefore, you should not place **per-task** initialization inside the factory. Request/task context data should be passed through the task or a wrapper and cleaned up according to the task's lifecycle.

### 2.3. Minimal factory example

~~~java
// Illustrative code; requires imports and usage inside a method.
AtomicInteger nextId = new AtomicInteger();

ThreadFactory factory = task -> {
    Thread thread = new Thread(
        task, "compute-worker-" + nextId.incrementAndGet()
    );
    thread.setDaemon(false);
    thread.setUncaughtExceptionHandler((t, error) -> {
        System.err.println(
            "Uncaught in " + t.getName() + ": " + error
        );
    });
    return thread; // Not started yet.
};

ExecutorService pool = Executors.newFixedThreadPool(2, factory);
~~~

Using an `AtomicInteger` for the naming counter keeps the factory thread-safe when multiple callers request worker creation concurrently. Do not assume the factory is always invoked from a single thread.

**Limitation:** The `UncaughtExceptionHandler` above only runs when an uncaught throwable reaches the thread boundary per its contract. It does not observe all errors from `FutureTask`, and it is not the place to run business retry logic.

## 3. Example 1 — Naming workers with ThreadFactory (Java 17+)

To demonstrate that the two threads of a fixed pool have distinct names without relying on scheduling order, we have both tasks wait at a latch and then print the **sorted set of names**.

Create the file `NamedWorkersDemo.java`:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.ThreadFactory;

public class NamedWorkersDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger ids = new AtomicInteger();

        ThreadFactory factory = command -> {
            Thread worker = new Thread(
                command, "lesson-worker-" + ids.incrementAndGet()
            );
            worker.setDaemon(false);
            return worker;
        };

        ExecutorService pool =
            Executors.newFixedThreadPool(2, factory);
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                entered.countDown();
                release.await();
                return Thread.currentThread().getName();
            });

            Future<String> second = pool.submit(() -> {
                entered.countDown();
                release.await();
                return Thread.currentThread().getName();
            });

            entered.await();
            release.countDown();

            TreeSet<String> names =
                new TreeSet<>(List.of(first.get(), second.get()));
            System.out.println("workers = " + names);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac NamedWorkersDemo.java
java NamedWorkersDemo
~~~

Stdout when both tasks complete normally:

~~~text
workers = [lesson-worker-1, lesson-worker-2]
~~~

Explanation:

1. `newFixedThreadPool(2, factory)` has capacity to run two tasks concurrently.
2. `entered` ensures both tasks have been picked up by workers and reached the waiting point; if only one worker existed, both could not count down the latch before one left it, so the executor must create the second worker to make progress.
3. `release` lets both tasks proceed once both have reached the waiting point.
4. `Future.get()` waits for each task's result and propagates any task error via `ExecutionException`.
5. `TreeSet` sorts the names before printing, avoiding dependence on which task finishes first.
6. `shutdown()` combined with `awaitTermination()` demonstrates controlled pool management. `shutdownNow()` on the timeout path is a *best effort* cancellation request, not a guarantee that all tasks will terminate.

**Do not infer from this example that the factory is called on every submit.** This run only proves two workers were created because two tasks needed to run concurrently. When subsequent tasks are submitted to the pool, they can be executed by these same two workers.

## 4. What does UncaughtExceptionHandler do?

### 4.1. Thread-level callback

`Thread.UncaughtExceptionHandler` has the method:

~~~java
// Interface signature, not a standalone program.
void uncaughtException(Thread thread, Throwable error);
~~~

When a thread is about to terminate due to an unhandled throwable, Java passes the details to the appropriate handler. The handler can record the thread name, throwable type, stack trace, and error count.

Ways to attach a handler:

- `thread.setUncaughtExceptionHandler(handler)`: a dedicated handler for that specific thread.
- `Thread.setDefaultUncaughtExceptionHandler(handler)`: a JVM-wide default handler for threads without an explicit handler, subject to the fallback/`ThreadGroup` mechanism.
- Attaching it to **every thread created by the factory** for consistent monitoring coverage across workers created by that factory.

With executors, it is usually best to attach the handler **when the factory initializes the thread**, rather than trying to find running workers to change their handlers later.

### 4.2. The handler does not replace exception handling inside tasks

Distinguish these three boundaries:

~~~text
Task business code
      |
      +--> handles error with try/catch: task handled it, handler never sees it
      |
      +--> execute(Runnable) -> Runnable.run() throws
      |                       -> worker may die abnormally
      |                       -> UncaughtExceptionHandler receives Throwable
      |
      +--> submit(Runnable/Callable)
                              -> FutureTask.run() catches Throwable
                              -> Future records the error
                              -> Future.get() throws ExecutionException
                              -> No uncaught throwable from the task
~~~

`UncaughtExceptionHandler` does not catch checked exceptions in the sense of resolving all errors on behalf of the caller; `Runnable.run()` does not declare checked exceptions. Only if you wrap a checked exception into a `RuntimeException` and that throwable actually escapes the worker will the handler have a chance to receive it.

**Guarantee to rely on:** Task errors from `submit` are placed into the Future and must be observed via the Future or a dedicated hook/mechanism. Merely attaching a handler to the thread pool **does not** guarantee you will see errors from every submitted task.

### 4.3. Limitations of the handler itself

A handler should:

- **Be brief and safe**: record the error, update a metric, or emit an alert through a low-dependency path.
- Avoid throwing another exception; an uncaught exception thrown by the handler itself is typically ignored by the runtime at that boundary.
- Avoid indefinite waiting and avoid acquiring locks that could cause deadlocks during logging.
- Avoid submitting a critical notification task back to the same failing executor without a fallback.
- Never call `Thread.stop()`, attempt to "revive" the terminating thread, or pretend a failed task was successfully retried.

If the application needs to retry failed tasks, it needs a retry system built around idempotency, attempt limits, deadlines, and result reporting. **A handler is only an observation point for thread failure**, not a retry policy.

## 5. execute() vs. submit(): The most important distinction in this lesson

### 5.1. `execute(Runnable)`

`Executor.execute(Runnable)` simply asks the executor to run the task. It **does not return a `Future`** to the caller to retrieve results or exceptions.

With a standard `ThreadPoolExecutor`, when a `Runnable` is passed directly to `execute` and throws an unhandled `RuntimeException`/`Error`, the throwable can escape the worker's `run()`. `ThreadPoolExecutor` calls `afterExecute` with that throwable and the worker may terminate abnormally; the thread's uncaught exception mechanism can then receive the throwable.

**Do not overgeneralize:** this holds for the standard `ThreadPoolExecutor` worker model, not as a promise that any custom `Executor` shares the same policy. A custom executor might catch all throwables or run tasks synchronously on the caller thread.

### 5.2. `submit(Runnable/Callable)`

`ExecutorService.submit(...)` returns a `Future<?>` or `Future<V>`. With standard `ThreadPoolExecutor` implementations, the task is wrapped into a `RunnableFuture` such as `FutureTask`. `FutureTask.run()` catches exceptions and stores the outcome.

If the task fails:

~~~java
// Illustrative code; executor is already created.
Future<?> result = executor.submit(
    () -> { throw new IllegalStateException("task failed"); }
);

try {
    result.get();
} catch (ExecutionException failure) {
    Throwable root = failure.getCause();
    // Report the error, translate to a caller-layer error, or handle in a controlled way.
}
~~~

`get()` is the standard way for a caller to learn about a task failure. If the caller **does not keep the Future or never calls `get()` / observe it otherwise**, the error can be silently lost in the orchestration flow without ever appearing at the uncaught handler.

### 5.3. Note: `execute(FutureTask)` can still hide exceptions

The key factor is not just "the method name `execute` vs `submit`", but **whether the task wrapper catches throwables**. If you pass a `FutureTask` directly to `execute()`, `FutureTask.run()` itself catches the error and holds it inside the `FutureTask`, so the uncaught handler still will not see it.

Thus, the operational rule is: **check how the task is wrapped and where results/exceptions are stored**, rather than only counting how many times the handler fires.

## 6. Example 2 — Error from execute() reaching UncaughtExceptionHandler (Java 17+)

This example attaches the handler in the factory and uses a latch to ensure `main` observes that the handler processed the error before printing. For deterministic stdout, the handler records the **exception class name** rather than printing unsynchronized stack traces across threads.

Create the file `ExecuteUncaughtDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.ThreadFactory;

public class ExecuteUncaughtDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch handled = new CountDownLatch(1);
        AtomicReference<String> observed =
            new AtomicReference<>("none");

        ThreadFactory factory = command -> {
            Thread worker = new Thread(command, "execute-worker");
            worker.setUncaughtExceptionHandler((thread, error) -> {
                observed.set(error.getClass().getSimpleName());
                handled.countDown();
            });
            return worker;
        };

        ExecutorService pool =
            Executors.newSingleThreadExecutor(factory);

        try {
            pool.execute(() -> {
                throw new IllegalStateException("from execute");
            });

            handled.await();
            System.out.println("handler = " + observed.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ExecuteUncaughtDemo.java
java ExecuteUncaughtDemo
~~~

Stdout in this example's standard `ThreadPoolExecutor` model:

~~~text
handler = IllegalStateException
~~~

The `execute` call submits a `Runnable` **not wrapped in a FutureTask**. `IllegalStateException` escapes `run()`, passes through the executor worker, and finally reaches the worker's handler. The handler records the throwable's class name and counts down the latch. `main` prints only after `handled.await()`, so it does not depend on log ordering between the two threads.

**A failed worker does not mean the whole pool is dead:** `ThreadPoolExecutor` can typically create a replacement worker per pool policy when the old worker terminates abnormally. However, **the task that threw the error is not automatically re-run**. Even with a replacement worker, task errors and business outcomes must still be monitored separately.

Do not expect the worker name `execute-worker` to remain unique across all creations; if a factory uses a fixed name as in this minimal example, a replacement worker will share the same name. In production, use an incrementing counter per worker, as in `NamedWorkersDemo`.

## 7. Example 3 — submit() captures the exception in Future (Java 17+)

This contrasting example uses the same handler technique but submits the task with `submit`. The handler **does not receive the task error**, whereas `Future.get()` surfaces it clearly.

Create the file `SubmitCapturedDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.ThreadFactory;

public class SubmitCapturedDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger handlerCalls = new AtomicInteger();

        ThreadFactory factory = command -> {
            Thread thread = new Thread(command, "submit-worker");
            thread.setUncaughtExceptionHandler((t, error) -> {
                handlerCalls.incrementAndGet();
            });
            return thread;
        };

        ExecutorService pool =
            Executors.newSingleThreadExecutor(factory);

        try {
            Future<?> future = pool.submit(() -> {
                throw new IllegalArgumentException("from submit");
            });

            try {
                future.get();
            } catch (ExecutionException failure) {
                System.out.println("future cause = "
                    + failure.getCause().getClass().getSimpleName());
            }

            System.out.println("handler calls = "
                + handlerCalls.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac SubmitCapturedDemo.java
java SubmitCapturedDemo
~~~

Stdout:

~~~text
future cause = IllegalArgumentException
handler calls = 0
~~~

Explanation:

- `submit` returns a `Future`, and the standard pool implementation stores `IllegalArgumentException` as the failure cause.
- `future.get()` waits for the task to complete and then throws `ExecutionException`; `getCause()` is the task's original exception.
- Because the exception did not escape `FutureTask.run()` to cause abnormal worker termination, the handler does not receive this error.
- If you do not call `get()` or use an appropriate observation mechanism, the error can go unnoticed even as the program keeps running.

**Do not conclude that an uncaught handler is useless.** It remains valuable for monitoring certain thread-level/`execute` failures; it simply does not replace checking Future results.

## 8. Error Diagnosis Decision Table

| How is the task run? | Where does the exception go? | Does it necessarily reach UncaughtExceptionHandler? | Primary observation mechanism |
| --- | --- | --- | --- |
| `new Thread(r).start()`, `r.run()` throws unhandled | Thread boundary | Yes, via Thread's uncaught mechanism | Handler + logs |
| `ThreadPoolExecutor.execute(plainRunnable)`, `run()` throws | Through worker, may terminate worker abruptly | Typically yes with standard pools | Handler or `afterExecute` |
| `ExecutorService.submit(Runnable)` throws | `FutureTask`/`Future` | **No**, error is captured | `Future.get()` |
| `ExecutorService.submit(Callable)` throws | `Future` | **No**, error is captured | `Future.get()` |
| `execute(FutureTask)` throws in delegate | `FutureTask` | Not by default | `FutureTask.get()` |
| Task `try/catch`es and handles error | Task code | No, unless rethrown | Task's result/log channel |
| `CompletableFuture.supplyAsync(...)` throws | Failed completion stage | Does not reach handler | `join()`, `get()`, `whenComplete` |
| Task cancelled via `Future.cancel(true)` | Future state and interrupt request | Not by default | `CancellationException`/state + separate cleanup confirmation |

Do not treat this table as a guarantee for every custom `Executor`: the executor/wrapper implementation itself determines the error-catching boundary. For JDK `ExecutorService` implementations, focus on the Future contract and dedicated hooks.

## 9. ThreadPoolExecutor.afterExecute(): Monitoring both execute and submit

### 9.1. What problem does this hook solve?

`ThreadPoolExecutor` provides the hook:

~~~java
// Method signature to override, not a standalone program.
protected void afterExecute(Runnable task, Throwable error)
~~~

It is called right after a task in the executor finishes running. If a `plain Runnable` throws an exception directly during `execute`, the `error` argument can be that throwable. With `submit`, however, the task is typically a `FutureTask` that catches the exception internally; therefore **`error` is usually null even when the task failed**.

If you want to observe errors from `submit` in this hook, you need to check `task instanceof Future<?>` and retrieve the outcome from the Future appropriately.

### 9.2. Safe hook pattern and limitations

~~~java
// Pattern inside a ThreadPoolExecutor subclass, not a standalone program.
@Override
protected void afterExecute(Runnable task, Throwable failure) {
    super.afterExecute(task, failure);

    Throwable observed = failure;
    if (observed == null && task instanceof Future<?> future) {
        try {
            future.get();
        } catch (CancellationException canceled) {
            // Cancellation is a distinct state, not a task failure by default.
        } catch (ExecutionException executedWithFailure) {
            observed = executedWithFailure.getCause();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    if (observed != null) {
        reportTaskFailure(observed);
    }
}
~~~

The snippet above requires importing `Future`, `CancellationException`, `ExecutionException`, and `InterruptedException`. This is a common JDK pattern; **you should not blindly call `get()` on any unfinished Future** elsewhere. Inside `ThreadPoolExecutor.afterExecute`, the task has already finished running under normal execution, so the `FutureTask` created by `submit` is already complete and `get()` does not wait for the task to keep running.

You must also consider other wrappers: if a `Runnable` holds a Future of another unfinished task, or a custom implementation returns a Future not tied to the just-finished task, `get()` could block. Production hooks should not block indefinitely. You can check `Future.isDone()` before retrieving the result, or only unwrap wrappers that you control.

**Do not throw unintended exceptions from `afterExecute`.** Under the `ThreadPoolExecutor` model, an exception escaping this hook can cause the worker to terminate abruptly, triggering extra worker replacement and obscuring the underlying business cause. Record errors via a resilient, low-dependency path and avoid slow I/O inside the hook when high throughput is needed.

### 9.3. Example 4 — Observing submit exceptions in afterExecute (Java 17+)

Create the file `AfterExecuteDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AfterExecuteDemo {
    static final class ObservingPool extends ThreadPoolExecutor {
        final CountDownLatch observed = new CountDownLatch(1);
        final AtomicReference<String> cause = new AtomicReference<>("none");

        ObservingPool() {
            super(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>()
            );
        }

        @Override
        protected void afterExecute(Runnable task, Throwable failure) {
            super.afterExecute(task, failure);

            Throwable found = failure;
            if (found == null && task instanceof Future<?> future) {
                try {
                    future.get();
                } catch (ExecutionException ex) {
                    found = ex.getCause();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }

            if (found != null) {
                cause.set(found.getClass().getSimpleName());
            }
            observed.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ObservingPool pool = new ObservingPool();
        try {
            Future<?> future = pool.submit(() -> {
                throw new IllegalArgumentException("sample");
            });

            try {
                future.get();
            } catch (ExecutionException expected) {
                // Caller received the exception; the hook will also observe it.
            }

            pool.observed.await();
            System.out.println("afterExecute = " + pool.cause.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac AfterExecuteDemo.java
java AfterExecuteDemo
~~~

Stdout:

~~~text
afterExecute = IllegalArgumentException
~~~

The outer `future.get()` observes the error on the caller side. `afterExecute` runs after the task, sees `failure == null` because the `FutureTask` wrapper held the exception, and then extracts `getCause()` from the Future. `observed` lets `main` wait until the hook has finished recording before printing, avoiding dependence on scheduling order.

This example submits only a failing task and never cancels it, so it omits a separate branch for `CancellationException`. **In real applications**, the hook must handle cancelled Futures and all wrapper types, and stay short and non-blocking. This pattern shows how to gain visibility into task failures; it does not replace business-layer retry management.

### 9.4. Use the hook or observe the Future at the caller?

- When the caller **needs the result to make a decision**, use `Future.get()` or appropriate stage composition; the exception belongs to the result-handling contract.
- When you need **centralized monitoring** across all tasks of a self-managed `ThreadPoolExecutor`, `afterExecute` or a task wrapper can record metrics and errors.
- When you only want to log **uncaught thread failures**, the handler is an extra safety net, not a system for handling every Future.

You can combine all three, but avoid logging the same error multiple times and remember that **logging an error is not the same as handling it in business logic**.

## 10. Abnormal Worker Termination and Replacement

### 10.1. What does a throwing task mean for the pool?

In `ThreadPoolExecutor`, when a `Runnable` exits with an uncaught throwable, the worker running that task may terminate abnormally. The pool manages its worker count and **may create a replacement worker** depending on pool configuration and executor state.

However, the following do **not happen automatically**:

- The failed task is retried like a transaction.
- Partial side effects are rolled back.
- A caller using `execute` gets a Future to receive the exception.
- The Future of a failed submitted task forwards its exception to the handler.
- All `ThreadLocal`-bound resources are cleaned up before the worker dies.
- Executor shutdown becomes safe even if tasks still hold other resources or locks.

If retries are needed, you must design a mechanism that accounts for task idempotency, attempt counts, backoff/deadlines, and result reporting. For operations like sending emails or transferring money, unconditional retries can duplicate side effects.

### 10.2. ThreadFactory does not control task scheduling

A factory is called when the pool needs a worker. It is **not** called each time a task starts, so:

- Do not set per-task request IDs or user context via fixed thread configuration.
- Do not embed current-task info into the thread name in the factory and assume it updates per task.
- Do not use `UncaughtExceptionHandler` to perform per-request business-level rollback.
- For `ThreadLocal`/MDC, set and clear them inside a task wrapper or dedicated hook using `try/finally`.

A single worker can run thousands of tasks; leftover context from a previous task can bleed into the next task even when no exception occurs. If you rename a thread per task, restore the original name in `finally` to prevent metadata leakage across tasks.

## 11. Daemon, Priority, Context Class Loader, and Security

### 11.1. Daemon workers

`Thread.setDaemon(true)` marks a thread as a daemon. The JVM can exit when only daemon threads remain, so work that must persist data, flush queues, or clean up during shutdown **should not rely solely on daemon status**.

A pool with daemon workers **does not** guarantee tasks will finish before the JVM exits. Conversely, non-daemon workers can keep the JVM alive if you forget to shut down the pool. Thus, choosing daemon vs. non-daemon must align with lifecycle management, not serve as a hack for a pool that "won't exit".

In `ThreadFactory`, call `setDaemon(...)` before the thread starts; do not attempt to change the daemon status of an already-running thread. Name and priority should also be configured before returning the thread.

### 11.2. Thread priority

`setPriority(...)` depends on the JVM and OS scheduler and does not guarantee task priority, FIFO ordering, or throughput by any simple formula. Do not use thread priority as a substitute for a priority queue or SLA mechanism.

### 11.3. Context class loader

A worker may inherit the context class loader of the thread that creates it, depending on the constructor/implementation used. In plugin, module, or complex class-loading environments, holding onto a context class loader for too long can retain unintended references. Establish a clear class loader policy, but do not arbitrarily set it to `null` or the system class loader without knowing what libraries called by tasks expect.

### 11.4. ThreadGroup and default handler

When a thread has no dedicated handler, the fallback mechanism may go through `ThreadGroup` and the default handler. This is useful for diagnostics, but a factory-level handler is a clearer choice if you want to capture errors for **a specific group of workers** without altering the behavior of other threads in the JVM.

Do not configure `Thread.setDefaultUncaughtExceptionHandler(...)` as if it were a harmless local change: it has JVM-wide impact and can override global policies of other libraries or parts of the application.

## 12. Task Failures, Cancellation, and Interrupts Are Not the Same

### 12.1. `Future.cancel(true)` is a cancellation request, not a task exception

A task waiting on `BlockingQueue.take()` or `Thread.sleep()` can respond to an interrupt with `InterruptedException`. If the task was run via `submit`, termination due to cancellation or exception is generally reflected through the **Future state** and the executor's contract.

Do not expect `UncaughtExceptionHandler` to receive every `InterruptedException`: it is a checked exception that many task APIs handle or capture into a Future; it does not by default escape `Thread.run()`. With `Callable`, the exception is thrown into the `FutureTask` boundary and observed via `get()`.

### 12.2. Future.cancel does not confirm worker cleanup

`Future.cancel(true)` can mark the future as cancelled while the task code is still running for a while—for example, because it does not check for interrupts or is in the middle of releasing resources. If you need to know that **cleanup has completed**, use a dedicated confirmation channel such as a latch, task state, or appropriate synchronization construct.

`CompletableFuture.cancel(true)` does not use the `mayInterruptIfRunning` parameter to interrupt execution per its API contract. Therefore, do not assume a running `CompletableFuture` will be interrupted the way a `FutureTask` task is.

### 12.3. Some errors can compromise the JVM or process

`UncaughtExceptionHandler` is an error-observation callback, not a reliable recovery boundary for every `Error`. Conditions like out-of-memory, stack overflow, or severe system errors can cause logging or metrics inside the handler itself to fail. Do not assume every failure will be recorded by the handler or that normal execution can continue after an `Error`.

## 13. How to Test Exception Reporting

### 13.1. Test with latches and Futures, not sleep-based timing guesses

For a handler, tests can use a `CountDownLatch` placed right inside the callback to verify it was invoked. For `submit`, use `Future.get()` to inspect the `ExecutionException` cause. For `afterExecute`, use a latch or result channel to confirm the hook finished before asserting.

Do not write:

~~~java
// Wrong verification approach, not a standalone program.
executor.execute(() -> { throw new RuntimeException("boom"); });
Thread.sleep(100);
assert handlerCalled;
~~~

The scheduler might delay the task/handler beyond 100ms even when the code is correct. Using a latch with a timeout in tests catches failures reliably without hanging the test suite forever.

### 13.2. Cases to test

| Test | Outcome to verify |
| --- | --- |
| Factory names workers | Name has prefix, distinct ID, thread is unstarted in factory |
| Pool reuses workers | Multiple tasks can share a worker; no per-task factory invocation |
| `execute(plainRunnable)` throws unchecked | Handler/hook receives error per standard pool implementation |
| `submit(Callable)` throws unchecked | `Future.get()` throws `ExecutionException` with expected cause |
| `submit(Runnable)` throws unchecked | Handler is not the default error channel |
| `execute(FutureTask)` throws in delegate | Error is held in `FutureTask`; do not assume handler runs |
| Task catches its own exception | No uncaught throwable unless rethrown |
| `afterExecute` with failed Future | Hook unwraps cause after Future completes |
| Cancelled Future | Distinguish cancellation from normal failure |
| Worker terminates abnormally | Pool can create another worker; old task is not retried |
| Shutdown | No worker leaks, no infinite wait; timeout handled |
| Handler/hook itself throws | Reporting path does not break pool stability |

### 13.3. Result channels and error observation

A good design should answer: **who owns the responsibility of inspecting task errors?**

- Callers of `submit` keep the Future and call `get()`, or hand it off to a management layer responsible for tracking it.
- A fire-and-forget system can use a task wrapper: catch `Throwable` at the right boundary, record it, and either **rethrow** if you want to preserve worker failure behavior or produce a structured error result.
- A custom `ThreadPoolExecutor` can use `afterExecute` for centralized error accounting, provided the hook is non-blocking and handles cancellation.
- The uncaught handler is the last line of defense for errors that **actually escape the thread**, not a replacement for Future observability.

If you catch `Throwable` in a task wrapper, be very careful with `Error`; generally do not silently swallow severe errors. Logging must be safe, and side effects should only run once unless retries are explicitly designed.

## 14. ThreadPoolExecutor or Executors Factory Methods?

### 14.1. Executors.newFixedThreadPool

`Executors.newFixedThreadPool(n, factory)` is convenient when you need a fixed number of workers and shared naming/handler configuration. However, this factory method uses an unbounded queue by standard design; if producers submit tasks faster than workers can process them over time, the queue can grow large and create memory pressure.

When you need a **bounded queue**, rejection/backpressure, and explicit monitoring, instantiate `ThreadPoolExecutor` directly with an appropriate capacity, rejection handler, and lifecycle management.

### 14.2. Bounded configuration example

~~~java
// Configuration pattern, not a standalone program.
// factory is already created with the naming/handler policy.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 4,
    30, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(100),
    factory,
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

This snippet requires importing `ThreadPoolExecutor`, `ArrayBlockingQueue`, and `TimeUnit`. `AbortPolicy` throws `RejectedExecutionException` when the executor cannot accept a task under its policy; this exception can occur **on the thread calling `execute`/`submit`**, not as an uncaught worker failure.

Do not rely on `UncaughtExceptionHandler` to catch rejected tasks, because the task may **never have been executed by a worker**. The caller must handle `RejectedExecutionException`, apply retry/backpressure, or propagate the error upstream.

### 14.3. Keep responsibilities separate

| Component | Primary responsibility |
| --- | --- |
| `ThreadFactory` | Create worker threads with appropriate properties |
| `RejectedExecutionHandler` | Decide how to handle tasks when the executor cannot accept them |
| `UncaughtExceptionHandler` | Receive throwables that truly go uncaught at the thread boundary |
| `Future.get()` | Retrieve the result/exception of a task represented by a Future |
| `ThreadPoolExecutor.beforeExecute/afterExecute` | Pre/post-execution hooks for measurement/observation per contract |
| `ExecutorService.shutdown/awaitTermination` | Manage pool lifecycle |
| Business retry policy | Decide which tasks are retried, backoff, idempotency, deadlines |

The more clearly responsibilities are separated, the easier it is to avoid the bug of "we set up a handler, so why did nobody notice the Future failed?".

## 15. Common Pitfalls to Avoid

**Pitfall 1 — Assuming `ThreadFactory` is called for every `submit`.** Workers can be reused. For per-task context, wrap the task or pass data inside the task.

**Pitfall 2 — Calling `thread.start()` inside the factory before returning.** The executor owns when the thread starts; return an unstarted thread.

**Pitfall 3 — Attaching only `UncaughtExceptionHandler` and assuming all task exceptions are caught.** `submit` usually stores errors in a `Future`; the Future's owner must observe it.

**Pitfall 4 — Passing `FutureTask` to `execute` and expecting the handler to fire.** `FutureTask.run()` catches throwables itself, so the error may never escape to the worker.

**Pitfall 5 — Never calling `Future.get()` on important tasks.** Errors are stored, but nobody looks at them; use a result protocol or centralized monitoring.

**Pitfall 6 — Checking only `Throwable error != null` in `afterExecute`.** With `submit`, that parameter can be `null` even when the task failed. Unwrap the Future when appropriate.

**Pitfall 7 — Calling `get()` indiscriminately in a hook on an unfinished Future.** This can block the worker or introduce an indefinite dependency; only unwrap completed tasks belonging to the executor with proper guards.

**Pitfall 8 — Throwing exceptions from a handler or hook and treating the error as handled.** Reporting code should be safe and must not cause secondary failures.

**Pitfall 9 — Assuming the executor retries a task whenever the handler is called.** The worker may be replaced, but the failed task is not automatically re-executed.

**Pitfall 10 — Using daemon workers as a workaround for forgetting to shut down.** The JVM may exit before important tasks finish. Manage lifecycle properly instead of relying on daemon status.

**Pitfall 11 — Failing to reset ThreadLocal/MDC between tasks.** A worker outlives a single task; previous request data can leak into subsequent tasks.

**Pitfall 12 — Treating `cancel(true)` as completed cleanup.** A cancellation signal is different from finished execution and side-effect cleanup; verify separately.

**Pitfall 13 — Sharing one `ThreadFactory` across multiple executors without distinct names.** Thread dumps become hard to read; use a pool-specific prefix and ID counter.

**Pitfall 14 — Ignoring rejections on the caller side.** A rejected task may never run on a worker; the worker's uncaught handler does not handle rejections.

**Pitfall 15 — Performing slow I/O inside the handler.** The thread handling the failure may be held too long, delaying worker replacement or masking incidents; keep reporting minimal and have a fallback.

## 16. Review Checklist and Exercises

### Implementation Checklist

- Does `ThreadFactory.newThread` always return a **new, unstarted Thread** per contract?
- Do worker names have a recognizable pool prefix and a monotonically increasing ID?
- Are daemon/priority/context class loader settings chosen intentionally rather than copied arbitrarily?
- Does the handler record sufficient throwable details while avoiding secondary exceptions, deadlocks, or long I/O?
- Are the different **exception delivery channels** for `execute` and `submit` documented?
- Is the caller responsible for observing every important Future?
- If using `afterExecute`, are `Future.get()`, `ExecutionException`, `CancellationException`, and interrupts handled properly?
- Does the hook avoid blocking on other unfinished Futures?
- Are failed, cancelled, rejected, and pool-shutdown states clearly separated?
- Is it understood that worker replacement does **not** automatically retry failed tasks?
- Is `ThreadLocal` leakage from old tasks to new tasks prevented?
- Are queue length, processing time, error counts, and latency measured alongside proper pool shutdown?
- Do you avoid setting a JVM-wide default handler outside your ownership scope?
- Is exception reporting tested with latches/Futures rather than timing sleeps?

### Question 1

**Why can `ExecutorService.submit(...)` fail without `UncaughtExceptionHandler` being called?**

Because with a standard `ThreadPoolExecutor`, `submit` typically wraps the task in a `FutureTask`. That wrapper catches the throwable and stores it in the Future; the throwable does not escape the worker as an uncaught exception. The caller must call `get()` or use another observation channel.

### Question 2

**If you pass a `FutureTask` to `execute(...)` instead of calling `submit(...)`, will the handler definitely see the error?**

No. `FutureTask.run()` still holds the exception internally; using the `execute` method name does not change the wrapper's behavior.

### Question 3

**Should a factory start the thread immediately to reduce latency?**

No. `ThreadFactory.newThread` creates and returns an unstarted thread; the executor manages `start()`. Starting early can break lifecycle management and correctness.

### Question 4

**When `execute(plainRunnable)` throws an exception, does the pool automatically re-run that exact task?**

No. The worker may terminate and be replaced, but task retry is a separate responsibility requiring explicit conditions, limits, and idempotency.

### Question 5

**Does receiving a `null` `Throwable` parameter in `afterExecute(Runnable, Throwable)` prove that a submitted task succeeded?**

No. `FutureTask` can catch the exception, leaving the throwable parameter `null` even though the Future is in a failed state. You can unwrap the outcome from the completed Future.

### Question 6

**Why is putting a request ID into the thread name inside the factory insufficient for tracking the current request?**

Because a worker can execute many tasks sequentially. The factory runs only when creating the worker, not per request. Per-request metadata must be set and cleared at the task scope.

### Question 7

**Does `Future.cancel(true)` or `future.isCancelled()` prove that the worker has released its resources?**

No. The Future's cancellation state can change before the worker actually finishes cleanup; use a separate confirmation channel when needed.

### Question 8

**When a pool uses a bounded queue and a task is rejected, where should that be handled?**

On the thread calling `execute`/`submit` and via the `RejectedExecutionHandler` policy. The task may never have run on a worker, so the worker's uncaught handler is not the channel for this error.

**Summary:** `ThreadFactory` defines **how workers are created**, `UncaughtExceptionHandler` observes **throwables that actually escape a thread**, and `Future` and `afterExecute` help observe **task results or failures** in an executor. Proper operation requires separating worker lifecycle from task lifecycle, avoiding swallowed `submit` errors, managing shutdown and cleanup, and never treating a handler as a retry or universal recovery mechanism.

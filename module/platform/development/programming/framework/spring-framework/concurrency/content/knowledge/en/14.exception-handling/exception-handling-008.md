# Error-Catching Limits of TaskDecorator When Tasks Are Wrapped in a Future

## 1. The problem: why can't try/catch inside TaskDecorator catch the error?

In Spring Framework, `ThreadPoolTaskExecutor#setTaskDecorator(...)` lets you wrap the execution of a `Runnable` with extra logic: setting up logging context, measuring execution duration, recording metrics, cleaning up `ThreadLocal`, or observing errors **escaping from the `run()` call**.

A common pattern:

```java
executor.setTaskDecorator(task -> () -> {
    try {
        task.run();
    } catch (RuntimeException ex) {
        logger.error("Task failed", ex);
        throw ex;
    }
});
```

This is only an **illustrative snippet** assuming `executor` and `logger` already exist. Looking at the `catch`, it is tempting to assume “every task that throws an exception will be logged here”. In reality, **that is false** when the task has been wrapped in a `FutureTask` or similar callback:

- With a raw `Runnable` executed directly via `execute(Runnable)`, an exception not captured by another wrapper can **escape from `task.run()`**, so the decorator catches it.
- With `submit(Runnable)` or `submit(Callable)`, the framework/executor typically creates a **`FutureTask`**: `FutureTask.run()` catches the business error and **stores it in the Future's state**. It returns normally at the `Runnable.run()` surface, so the outer `catch` **is not triggered**.
- With `@Async` returning `Future`/`CompletableFuture` or multi-layered wrapped tasks, the actual callback being decorated **may no longer be the user-supplied Runnable/Callable**. Do not infer types or error-catching rules solely from the signature `TaskDecorator.decorate(Runnable)`.

This exact limitation is noted in **Spring's Javadoc for `ThreadPoolTaskExecutor.setTaskDecorator`**: a decorator suits adding context/monitoring around callback execution, yet catching errors may only see exceptions from a direct `Runnable`. Along the `submit` path, `FutureTask` does not propagate exceptions out of `run()`; to observe errors, you may need to inspect `Future.get()`.

**Lesson goal:** understand the boundary where errors occur, reproduce it with Java 17, recognize Spring's behavior, and choose reliable exception-handling locations instead of expecting all errors to reach `TaskDecorator.catch`.

## 2. What can TaskDecorator do, and what can it not do?

Interface in Spring:

```java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
```

This is an abbreviated signature for conceptual study, not Spring's full source code. It accepts a `Runnable` that the executor will run and returns another `Runnable`, typically calling `runnable.run()`.

```text
Caller / @Async proxy / ExecutorService
       |
       v
  Task submitted
       |
       v
  (may be wrapped in FutureTask / internal callback)
       |
       v
  TaskDecorator.decorate(actualRunnable)
       |
       v
  decoratedRunnable runs on worker
       |
       +--> setup context / start timer
       |
       +--> actualRunnable.run()
       |       |
       |       +--> error may ESCAPE
       |       +--> or be captured by FutureTask
       |
       +--> finally: cleanup context / record duration
```

`TaskDecorator` is very useful when you need to:

1. Copy/restore logging context from the submitting thread to the worker (for example correlation ID/MDC).
2. Set `ThreadLocal` within an explicit scope, then restore or clear it in `finally` to prevent a previous request's data from leaking into the next task.
3. Measure callback execution time and record metrics with bounded-cardinality tags.
4. Propagate tracing/observation context, when the application has the right context-propagation libraries and mechanisms.
5. Instrument task lifecycle at the executor level without injecting measurement logic into every business method.

**TaskDecorator is NOT:**

- A global error handler that understands every `Future`, `CompletableFuture`, or `@Async` exception.
- A `try/catch` that can see through exceptions already recorded inside `FutureTask` state.
- A mechanism that automatically cancels tasks, retries, rolls back transactions, or guarantees errors are logged exactly once.
- A mechanism automatically covering work not submitted through the executor bean configured with that decorator.
- A mechanism catching all errors from asynchronous work *initiated by* the original task that continues running after `Runnable.run()` has returned.

What Spring decorates is the **actual callback**, not necessarily the exact `Runnable` or `Callable` object originally supplied by the caller. Therefore casting every callback to an application-defined type is generally unsafe.

## 3. Distinguishing execute, submit, and FutureTask

### 3.1. execute(Runnable): errors can escape from run()

With JDK `Executor.execute(Runnable)` or Spring `TaskExecutor.execute(Runnable)`, when the underlying executor actually runs a `Runnable` directly with no error-capturing wrapper:

```java
executor.execute(() -> {
    throw new IllegalStateException("direct failure");
});
```

The exception can escape `Runnable.run()`, pass through the decorator's wrapper, and then be handled by the thread's or executor's exception/uncaught-exception mechanism. If the decorator catches and rethrows it, the worker may terminate and the pool replaces the thread according to its implementation policy.

**Limitation of that statement:** “calling `execute`” is **not enough** to guarantee the decorated callback is the original lambda. Spring `@Async`, `CompletableFuture`, other adapters, or middleware may already have wrapped the task earlier. Verify the actual execution path before trusting that the decorator will see every exception.

### 3.2. submit(...): errors are stored inside FutureTask

JDK `ExecutorService.submit(Callable)` returns `Future<T>`:

```java
Future<String> future = executor.submit(() -> {
    throw new IllegalArgumentException("task failed");
});

// In code that owns the result (not by default inside TaskDecorator):
try {
    String value = future.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause(); // IllegalArgumentException
    // Record and decide handling according to business rules.
}
```

This snippet requires the `executor` variable and JDK imports. When using `FutureTask`, the outer `run()` call does not need to throw `IllegalArgumentException` to the decorator; it stores the error so `Future.get()` reports `ExecutionException` with `cause` being the original error.

`FutureTask` implements **both `Runnable` and `Future`** (via `RunnableFuture`). This explains why it can be executed by a worker as a `Runnable` while still holding result/exception state for the caller.

### 3.3. Comparison table

| Scenario | Can callback `run()` throw out business errors? | Reliable place to observe errors |
| --- | --- | --- |
| `execute(plainRunnable)`, no error-capturing wrapper | Yes | `catch` around `run()`; executor's uncaught handler/logger |
| `submit(Runnable)` via `FutureTask` | Usually no: error stays in Future | `Future.get()` → `ExecutionException.getCause()` |
| `submit(Callable)` via `FutureTask` | Usually no | `Future.get()` → `ExecutionException.getCause()` |
| `CompletableFuture.supplyAsync(...)` | Should not be assumed | `whenComplete`, `handle`, `exceptionally`, or `join/get` |
| Spring `@Async` returning `Future/CompletableFuture` | Should not assume `TaskDecorator` sees it | Future returned to caller; check completion/error |
| Spring `@Async void` | Returns no Future to caller | `AsyncUncaughtExceptionHandler` |
| Submission rejected by pool/queue | Task never ran | `TaskRejectedException` or `RejectedExecutionException` **at submitter** |

**Note:** `CompletableFuture.join()` throws `CompletionException` for normal failures; `Future.get()` throws `ExecutionException`. For cancellation cases, handle `CancellationException` separately.

## 4. Mechanism of FutureTask.run(): why is catch not triggered?

Sequence when a `Callable` is wrapped by `FutureTask`:

```text
Caller: submit(callable)
            |
            v
        FutureTask(callable)   <-- implements RunnableFuture
            |
            v
TaskDecorator sees a Runnable that may be this FutureTask
            |
            v
decoratedRunnable.run()
            |
            +--> try {
            |        futureTask.run()
            |            |
            |            +--> callable.call() throws IllegalArgumentException
            |            |
            |            +--> FutureTask records exceptional state
            |            +--> returns normally from run()
            |    } catch (RuntimeException ex) {
            |        // DOES NOT run for errors already captured by FutureTask
            |    }
            |
            v
Caller calls Future.get()
            |
            +--> ExecutionException(cause=IllegalArgumentException)
```

**Most important mechanism:** a `FutureTask` can complete in an **exceptional** state while its `run()` method still **returns normally**. There is no contradiction: the Future is where the error is stored, whereas `Runnable.run()` is the callback execution interface.

That does not mean “the error has been handled by business logic”. A caller that never calls `get()` and has no mechanism to observe exceptional state can **miss the error** while the pool keeps serving other tasks.

Nor does it mean all exceptions are swallowed by `FutureTask`: exceptions from the **decorator itself**, context setup, cleanup, or other wrapping layers can still escape. Which boundary catches errors must be determined from the actual object/callback being executed.

## 5. Standalone Java 17 example: same decorator, two different outcomes

The example below simulates the wrapper logic produced by a `TaskDecorator`, using **100% JDK 17** with no Spring required. It runs synchronously on the main thread so results are deterministic and clearly contrast `Runnable.run()` with `FutureTask.run()`. **This illustrates semantics**, not a full simulation of Spring's bean/executor lifecycle.

Create the file **`FutureTaskDecoratorDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;

public final class FutureTaskDecoratorDemo {
    static Runnable decorate(Runnable task) {
        return () -> {
            try {
                task.run();
            } catch (RuntimeException ex) {
                System.out.println(
                        "caughtAtRun=" + ex.getClass().getSimpleName());
                throw ex; // Preserve Runnable's error-reporting semantics.
            } finally {
                // Inspect Future only after run(), and only when Future reports done.
                if (task instanceof Future<?> future && future.isDone()) {
                    try {
                        future.get();
                    } catch (ExecutionException ex) {
                        System.out.println(
                                "causeFromGet="
                                        + ex.getCause().getClass().getSimpleName());
                    } catch (CancellationException ex) {
                        System.out.println("cancelled=true");
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                }
            }
        };
    }

    public static void main(String[] args) {
        Runnable direct = () -> {
            throw new IllegalStateException("direct");
        };
        try {
            decorate(direct).run();
        } catch (IllegalStateException ex) {
            System.out.println("directPropagated=true");
        }

        FutureTask<String> future = new FutureTask<>(
                () -> {
                    throw new IllegalArgumentException("stored");
                });

        decorate(future).run();

        System.out.println("futureDone=" + future.isDone());
        System.out.println("futureCancelled=" + future.isCancelled());
    }
}
```

Compile/run with JDK 17 or newer:

```bash
javac --release 17 FutureTaskDecoratorDemo.java
java FutureTaskDecoratorDemo
```

**Verified standard output when running the program:**

```text
caughtAtRun=IllegalStateException
directPropagated=true
causeFromGet=IllegalArgumentException
futureDone=true
futureCancelled=false
```

### Output explanation

1. For `direct`, `run()` throws `IllegalStateException`. The wrapper catches it, prints `caughtAtRun=IllegalStateException`, and rethrows. `main` catches it next and prints `directPropagated=true`.
2. For `future`, `FutureTask.run()` calls `Callable.call()`, receives `IllegalArgumentException`, **stores the exception in the Future's state**, and completes. It **does not throw** that exception out to the wrapper, so there is no `caughtAtRun=IllegalArgumentException` line.
3. In `finally`, the wrapper recognizes `task instanceof Future<?>` and `future.isDone()`. Calling `get()` throws `ExecutionException`; `getCause()` is `IllegalArgumentException`, so it prints `causeFromGet=IllegalArgumentException`.
4. The Future completed, yet **was not cancelled**: `futureDone=true`, `futureCancelled=false`. Business errors and cancellation are two distinct states.

The example calls `get()` **after** `FutureTask.run()` has completed; there is no unbounded wait. In a real executor, never call `Future.get()` recklessly from a wrapper while the future is still running or depends on the very worker being blocked: that can exhaust the pool and deadlock.

**Verified correctness:** the program above was compiled with `javac --release 17` and executed on a JDK supporting Java 17; stdout matched all five lines shown. This confirms JDK pattern semantics, **and does not replace integration tests on the Spring version your application uses**.

## 6. Configuring Spring TaskDecorator: context and metrics are the right fit

In Spring Framework 6.2, a `ThreadPoolTaskExecutor` bean can be configured:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ObservedExecutorConfig {
    private static final Logger LOG =
            Logger.getLogger(ObservedExecutorConfig.class.getName());

    @Bean("observedExecutor")
    public ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("observed-");

        executor.setTaskDecorator(task -> () -> {
            long start = System.nanoTime();
            try {
                task.run();
            } catch (RuntimeException | Error ex) {
                // Only errors ESCAPING callback.run() reach here.
                LOG.log(Level.SEVERE, "Runnable callback failed", ex);
                throw ex;
            } finally {
                long elapsedNanos = System.nanoTime() - start;
                LOG.fine("Callback duration (ns): " + elapsedNanos);
            }
        });
        return executor;
    }
}
```

This is a **Spring integration configuration class**, requiring relevant `spring-context`/`spring-aop` dependencies and an appropriate application context; it does not compile directly with plain JDK. There is no fixed output because it configures workers and runtime execution. Spring manages executor bean initialization/shutdown per its lifecycle.

**Correct analysis:**

- `setTaskDecorator` wraps the actual callback that Spring hands to the pool. It is useful for scoping callback runtime, logging context, and cleanup.
- `catch` receives only exceptions that actually escape `task.run()`. It **may not receive** errors already held in result state by a `FutureTask`/callback.
- Keep `throw ex` so you do not silently alter exception semantics for direct `execute(Runnable)`.
- `finally` still runs whether the callback finishes normally or throws an error. This is the right place to restore context/metrics.
- `System.nanoTime()` is suitable for relative duration measurement, not as a UTC timestamp. If the callback merely **schedules further work and returns**, the duration measured here is only **callback execution time**, not automatically spanning child futures.
- `LOG.fine` may not appear if the logger does not enable FINE level; that does not mean the decorator did not run.

**Do not use `TaskDecorator` as a place to swallow all exceptions** with a `catch (Exception ex) { log; }` that does not rethrow. For `execute(Runnable)`, that can make a failing task look like it completed normally; for `FutureTask`, even that still misses errors stored in the Future.

## 7. You can inspect Future.get() inside TaskDecorator, with caveats

Spring's Javadoc suggests: when the callback is exposed as a `FutureTask`, you can cast to `Future` and call `get()` to evaluate errors. This approach **is not a promise** that every callback implements `Future`.

A diagnostic variant:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import org.springframework.core.task.TaskDecorator;

// Used in executor configuration or where the decorator is created.
TaskDecorator diagnosticDecorator = runnable -> () -> {
    try {
        runnable.run();
    } finally {
        if (runnable instanceof Future<?> future && future.isDone()) {
            try {
                future.get();
            } catch (ExecutionException ex) {
                // Record error stored by FutureTask (ex.getCause()).
                recordFailure(ex.getCause());
            } catch (CancellationException ex) {
                // Cancellation differs from computation errors.
                recordCancellation();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
};
```

This is an **illustrative snippet** with `recordFailure(...)` and `recordCancellation()` supplied by the application; it needs appropriate imports/config and is **not a standalone program**.

### Critical conditions

- **Must check `instanceof Future<?>`.** The decorator may see a `Runnable` that is an internal wrapper **not** implementing `Future`, even when higher-level logic produces a `CompletableFuture` result.
- **Consider `get()` only after `run()` and when `isDone()`**. Attempting to call `get()` before `run()` or on an unfinished Future right inside a worker can block indefinitely or cause deadlock.
- **`get()` can throw three distinct error groups**: `ExecutionException` (computation error), `CancellationException` (task cancelled), and `InterruptedException` (waiting worker interrupted). Classify them separately; when catching `InterruptedException`, usually restore the interrupt flag.
- If the Future is another implementation, `get()` does not necessarily reflect all dependent tasks or downstream callbacks. Do not turn the decorator into a generic future orchestrator.
- With `@Async` returning `CompletableFuture`, the wrapper the executor actually runs may be an **internal callback**, not a `FutureTask` directly; `instanceof Future` may always evaluate to `false`. Verify against your real Spring version and executor implementation.
- `recordFailure` in the decorator may duplicate caller-side handlers. Pick one owner for error logs/metrics and identify tasks so you do not double-count.
- Hooks like `ThreadPoolExecutor.afterExecute(Runnable, Throwable)` have the same issue: `Throwable` may be `null` when `FutureTask` already stored the exception. The JDK shows checking `r instanceof Future<?>` and calling `get()`, yet if a decorator wraps `FutureTask` in another `Runnable`, `afterExecute` may see only that wrapper. Test the actual callback structure.

**Recommendation:** use Future inspection in a decorator for verified diagnostic needs, not as the **sole foundation** of business error handling. The next section presents stronger places to catch errors.

## 8. Handling errors at the Future: a more reliable place of ownership

### 8.1. Future.get(): clear root cause, though it can block the caller

When actively calling `submit` and holding the result:

```java
Future<String> result = executor.submit(() -> {
    throw new IllegalArgumentException("bad input");
});

try {
    String value = result.get();
    useValue(value);
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
    handleFailure(original);
} catch (CancellationException ex) {
    handleCancellation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    handleInterruptedWait(ex);
}
```

This snippet has `executor` and business methods provided by an integrated program. `Future.get()` can **block the caller**; if the caller is an HTTP event-loop or holds scarce locks/connections, consider async APIs or timeouts.

For deadlines, use `get(timeout, unit)` and also handle `TimeoutException`. Timing out while waiting **does not confirm** the task stopped; decide cancellation/cleanup appropriately for the executor and dependencies.

### 8.2. CompletableFuture.whenComplete(): observe without calling blocking get

With `CompletableFuture`, callbacks are the right choice for handling asynchronous completion:

```java
CompletableFuture<String> job =
        CompletableFuture.supplyAsync(() -> calculateReport(), executor);

job.whenComplete((value, error) -> {
    if (error != null) {
        // error may be a CompletionException wrapping the cause.
        logFailure(error);
    } else {
        logSuccess(value);
    }
});
```

This is an **integration snippet**. `whenComplete` receives the future's exceptional completion even when `Runnable.run()` on the executor returned normally. Note that the callback does not necessarily run on a new worker: depending on completion state and overload type, `whenComplete` can run on the stage-completing thread or the callback-registering thread; do not put long blocking work inside it.

If you always want to dispatch the callback onto a controlled executor, check `whenCompleteAsync(action, executor)`, accounting for saturation/rejection on that executor.

### 8.3. exceptionally(), handle(), whenComplete(): not the same

| API | Function | Watch out for |
| --- | --- | --- |
| `whenComplete((v,e) -> ...)` | Observes both success and failure | Usually preserves source stage result/error; callback can also throw |
| `exceptionally(e -> fallback)` | Recovers with another value after error | Can turn failure into success; do not use just to log and accidentally swallow errors |
| `handle((v,e) -> newValue)` | Transforms outcomes on both branches | Handler determines the new state |
| `join()` | Gets result, throws `CompletionException` on failure | Can block; use where appropriate |
| `get()` | Gets result, throws `ExecutionException` on failure | Checked exceptions, can block |

If the system must report errors to the caller, never use `exceptionally(ex -> null)` just to “log and be done” when `null` is interpreted as a valid result. Define an explicit recovery/fail-fast contract.

### 8.4. Placing catch directly inside the business task when context is needed

A task that knows `orderId`, transaction boundaries, and remote endpoints often has enough context to classify errors:

```java
public Invoice calculateInvoice(String orderId) {
    try {
        return invoiceClient.calculate(orderId);
    } catch (RemoteTimeoutException ex) {
        failureMetric.increment();
        throw ex;
    }
}
```

This is an **illustrative snippet**, depending on application business types and clients. Advantage: logs/counters have accurate context. Disadvantage: code repetition if every task adds the same block; in that case create a business wrapper component or aspect with a clear contract instead of forcing a generic `TaskDecorator` to understand every error.

## 9. Spring @Async: Future, CompletableFuture, and void follow different error paths

For Spring `@Async`, the return type affects how exceptions reach the caller:

| Method signature | When the method body throws | Recommended handling point |
| --- | --- | --- |
| `@Async CompletableFuture<T>` | Error can be represented as exceptional completion of the future returned to caller | `whenComplete`/`handle` or `join/get` |
| `@Async Future<T>` | Caller can receive exception via `Future.get()` | `get()` and `ExecutionException.getCause()` |
| `@Async void` | Caller receives no Future to retrieve exception | `AsyncUncaughtExceptionHandler`, logging/metrics at boundary |
| Task rejected at submission | Execution was never accepted | Handle `TaskRejectedException` at submission site |

**Spring service example:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("observedExecutor")
    public CompletableFuture<String> build(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("id is blank");
        }
        return CompletableFuture.completedFuture("report:" + id);
    }

    @Async("observedExecutor")
    public void publish(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("id is blank");
        }
    }
}
```

This is a **Spring integration class**, using the executor bean from section 6 and `@EnableAsync`; it is not a standalone JDK program. Spring manages dispatch via proxy when methods are called from another Spring bean; self-invoking `this.build(...)` inside the same target usually bypasses `@Async` in proxy mode.

**Caller handling future:**

```java
CompletableFuture<String> result = reportService.build("");
result.whenComplete((value, error) -> {
    if (error != null) {
        // This is an async computation error, not necessarily
        // a RuntimeException escaping TaskDecorator.run().
        recordBuildError(error);
    }
});
```

Snippet requires `reportService` and `recordBuildError` to be defined. When using `@Async void`, Spring provides `AsyncUncaughtExceptionHandler` to handle exceptions that have no returned Future.

### Configuring AsyncUncaughtExceptionHandler for void

```java
import java.util.concurrent.Executor;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;

@Configuration
public class AsyncErrorsConfig implements AsyncConfigurer {
    private static final Logger LOG =
            Logger.getLogger(AsyncErrorsConfig.class.getName());

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) ->
                LOG.log(Level.SEVERE,
                        "Async void failed: " + method.getName(), error);
    }
}
```

This is a Spring configuration class, usable in an application with `@EnableAsync` enabled and the proper executor bean; it is ***not*** a facility for receiving errors from `Future<T>`. If multiple `AsyncConfigurer` beans or async configurations coexist, verify which executor/error handler is actually selected.

**Do not expect `TaskDecorator` to replace `AsyncUncaughtExceptionHandler`.** With `@Async void`, exceptions may be caught by the async interceptor and routed to the handler before the callback exits back to the decorator. Which mechanism is invoked must be integration-tested on your actual Spring version.

## 10. Distinguishing four states: execution error, cancellation, timeout, rejection

### Execution error

The task was accepted into the executor, started running, and threw an error. The error may be placed into `Future`/`CompletableFuture` or escape the worker. Handle it at the result or at an execution boundary with full context.

### Cancellation

A cancelled `Future`: `isCancelled()` may be true; `get()` throws `CancellationException`. This is **not** an `ExecutionException` for a business error. Cancelling a `CompletableFuture` can change the future's state without stopping the backing supplier, depending on implementation.

### Timeout

`Future.get(timeout, unit)` can throw `TimeoutException` because the caller waited too long while the task keeps running. JDBC/HTTP client timeouts are separate mechanisms; measure waiting duration, execution duration, and resource release separately.

### Rejection

When an executor has shut down or exhausted capacity (e.g., full pool + full queue per policy), `submit`/`execute` calls can be rejected **before the task runs**. In Spring, this error is typically `org.springframework.core.task.TaskRejectedException`. The decorator of an unexecuted task **never gets a chance** to catch this exception. Handle it at the caller/admission layer, without confusing it with completion failures.

```text
                  submission
                      |
              +-------+-------+
              |               |
           rejected         accepted
              |               |
    TaskRejectedException    v
       (caller thread)     execution
                              |
                      +-------+-------+
                      |               |
                    plain          FutureTask/
                  Runnable         async wrapper
                      |               |
                may throw out     stores task error
                  of run()         in Future state
                      |               |
              decorator catch      Future.get() /
               may see error      whenComplete()
```

## 11. Why shouldn't you try to fix this with afterExecute or Thread.UncaughtExceptionHandler?

JDK `ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` runs after a worker executes a task. `t` can be `null` even when a `FutureTask` failed, because `FutureTask.run()` does not throw exceptions out to the worker.

The JDK Javadoc gives an example: if `t == null` and `r instanceof Future<?>`, call `get()` to retrieve `ExecutionException`/`CancellationException`; also handle `InterruptedException`.

**However, in Spring with TaskDecorator:**

1. `FutureTask` is wrapped by the decorator into a new `Runnable`.
2. `afterExecute` of the underlying pool may receive that **wrapper** rather than the original `FutureTask`.
3. If the wrapper does not implement `Future`, `r instanceof Future<?>` is `false` even though the error sits inside the inner `FutureTask`.
4. Thus copying JDK `afterExecute` logic does not automatically guarantee observing every error when decorators, async interceptors, adapters, or internal callbacks are present.

Similarly, `Thread.UncaughtExceptionHandler` handles only exceptions that genuinely go uncaught on a thread. An error already recorded by `FutureTask` into its state never becomes an uncaught exception.

**Choose error-handling locations based on result ownership:** `CompletableFuture` subscribers, callers holding `Future`, `@Async void` handlers, or business boundaries. Use `TaskDecorator`/`afterExecute` to add metrics/context rather than expecting them to see through every wrapper.

## 12. Context propagation and cleanup remain TaskDecorator's strong use cases

For Spring applications using log correlation IDs, MDC, or observation context, a decorator fits well because **it runs at the callback execution boundary**, independent of business success or failure.

Proper practice with `ThreadLocal`/MDC:

1. **Capture context at submission** on the source thread, if the implementation actually invokes `decorate` at submission time. Do not read the worker's `ThreadLocal` thinking it is the request context.
2. **Set context on the worker** before `task.run()`.
3. **In `finally`, restore old context or clear it** so reused workers never leak trace/request IDs from one task to the next.
4. **Do not forget cancellation and exception paths**; cleanup must still run.
5. Avoid attaching full security principals or sensitive data to uncontrolled log/metric tags.
6. Measure overhead when tasks are very short: snapshotting/restoring context also has a cost.

Spring Framework 6.1+ includes `ContextPropagatingTaskDecorator` supporting propagation of certain contexts such as logging/observation when integrated with Micrometer Context Propagation. This feature **does not turn `TaskDecorator` into an all-powerful exception handler**. When using `CompositeTaskDecorator` to combine multiple decorators, verify wrapping/cleanup order and the effect on the `Runnable` object seen by each layer.

Never assume worker thread-locals are a safe place to stash exceptions “for someone to pick up later”: threads can be reused by the pool; errors should be associated with the appropriate **task ID/future/trace context** and cleaned up along the proper lifecycle.

## 13. Practical testing for ThreadPoolTaskExecutor

A solid integration test should cover distinct cases rather than just one throwing call:

| Test case | Setup | Expectation to verify |
| --- | --- | --- |
| A: direct `execute(Runnable)` | `Runnable` throws `IllegalStateException`, no error-capturing wrapper | Decorator catch can see exception escaping `run()` |
| B: `submit(Callable)` | `Callable` throws `IllegalArgumentException` | `Future.get()` throws `ExecutionException`; decorator catch must not be considered sufficient |
| C: `submit(Runnable)` | `Runnable` throws error | Future holds error similarly to case B |
| D: `@Async CompletableFuture<T>` | Method body throws error | Caller's Future completes exceptionally, callback receives error |
| E: `@Async void` | Method body throws error | `AsyncUncaughtExceptionHandler` is triggered |
| F: cancellation | Cancel Future before/during execution | Handle `CancellationException` separately; do not treat as business failure |
| G: rejection | Saturate pool/queue or shut down | Caller receives `TaskRejectedException`; task does not run |
| H: cleanup | Task succeeds/fails/cancels | Context/`ThreadLocal` is restored to pre-run state |

**How to write deterministic tests:**

- Use `CountDownLatch`/barriers to confirm the task started, hold the worker at a blocking point, and explicitly release it; do not rely solely on `Thread.sleep(100)` to assert race ordering.
- Run against the exact `ThreadPoolTaskExecutor` bean configured with the decorator, not accidentally against the common pool or another executor.
- For `@Async`, calls must go **through the Spring proxy** (invoked by another bean); `this.asyncMethod()` inside the same target usually bypasses interception.
- For futures, put timeouts on `get(timeout, unit)` or `await` so tests cannot hang indefinitely.
- Track both errors appearing at the **submitter** and errors inside the **worker/future**. These are two separate points.
- When measuring metrics, avoid double-counting if you have `Future.whenComplete`, `Future.get` logic in a decorator, and logging in the business method.
- Verify worker, queue, and context cleanup even when assertions fail; close the executor or let Spring lifecycle shut it down by design.

### Core assertion

For case B on a real executor, prove **both things simultaneously**:

```text
(1) Future.get() -> ExecutionException(cause=IllegalArgumentException)
(2) catch(RuntimeException) around callback.run()
    DOES NOT catch the IllegalArgumentException already captured by FutureTask.

Conclusion:
  TaskDecorator may have RUN normally,
  yet it still DID NOT see the error as an exception escaping from run().
```

This distinction matters far more than merely checking “whether an error log exists”; logs can come from many different sources.

## 14. Production error-handling checklist

When designing a Spring service with executors and Futures:

1. **Classify submission style**: `execute`, `submit`, `CompletableFuture`, `@Async void`, or another scheduler/adapter?
2. **Identify the actual `Runnable` entering the decorator**: is it the user task or a wrapper/`FutureTask`? Never cast based on assumptions.
3. **Choose business error ownership**: caller's Future, `CompletableFuture` callbacks, method boundary, or `AsyncUncaughtExceptionHandler`.
4. **Classify exceptions**: task failure, cancellation, wait timeout, submitter rejection.
5. **Do not block workers with `get()` arbitrarily**: inspect Futures only after the task completes, `isDone()` is true, and implementation details are understood; prefer async callbacks for result flows.
6. **Preserve semantics**: a decorator catching `RuntimeException`/`Error` must rethrow unless intentionally translating into a defined recovery policy.
7. **Separate logging from recovery**: logging does not mean retry, nor does it mean the task succeeded.
8. **Handle rejections** at the admission gate with backpressure/responses/retries or a job store; do not push all responsibility onto the decorator.
9. **Keep context clean**: snapshot at the right time, restore in `finally`, avoid leaking `ThreadLocal` across the worker pool.
10. **Avoid duplicate error reporting**: define the owner of error metrics/logs with task IDs and causal exceptions.
11. **Test real code** on the exact JDK/Spring/Boot versions in use: behavior of `submitCompletable`, `@Async`, callbacks, and wrappers can vary.
12. **Protect resources**: bounded executors, queues, JDBC/HTTP timeouts, metrics for active/queued/rejected/failed counts, and context propagation.

### Error observation location lookup table

| Need | Preferred tool |
| --- | --- |
| Measure callback duration, MDC, trace context | `TaskDecorator` with `finally` |
| Catch errors from a plain `Runnable` executed directly | `catch` around `run()` or executor error hook |
| Know why a `FutureTask` failed | `Future.get()` → `ExecutionException.getCause()` |
| Observe `CompletableFuture` errors without blocking | `whenComplete`/`handle` |
| Handle `@Async void` errors | `AsyncUncaughtExceptionHandler` |
| Handle task submission errors when capacity is full | Catch `TaskRejectedException` at submitter |
| Analyze errors by business code and retry | Handler/boundary at service/client layer |
| Test error causes and cleanup | Integration tests with latches, timeouts, assertions |

## 15. Summary and official references

**Three sentences to remember:**

1. **`TaskDecorator` wraps the actual `Runnable`**; it does not necessarily see the original task.
2. **`FutureTask.run()` stores exceptions rather than throwing them out**, so `catch` around `run()` is insufficient to observe errors of `submit`/future-backed tasks.
3. **Handle errors by result type and at the right boundary**: `Future.get()`, `CompletableFuture.whenComplete(...)`, `AsyncUncaughtExceptionHandler`, or catching `TaskRejectedException` at submission; keep `TaskDecorator` for context/metrics and add future inspection only when the real wrapper is well understood.

**Reference documentation:**

- [Spring Framework 6.2 – ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — `setTaskDecorator` and the warning when callbacks are `FutureTask`.
- [Spring Framework 6.2 – TaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/TaskDecorator.html) — callback decoration contract and error-catching limits.
- [Java SE 17 – FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html) — `run`, `get`, and `setException`.
- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — `afterExecute` and how to inspect Future errors.
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `whenComplete`, `handle`, `join`.
- [Spring Framework 6.2 – Async exception management](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html#scheduling-annotation-support-exception) — handling `@Async Future` and `@Async void` errors.
- [Spring Framework 6.2 – ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html) — propagating logging/observation context.

**Conclusion:** When `TaskDecorator.catch` fails to log an error from a `submit` task, the reason can be completely valid: the error is already inside `FutureTask` and never escapes `Runnable.run()`. Do not try to “fix” it by stacking more `try/catch` blocks inside the decorator; instead, read or register handlers on the **Future result**, keep the decorator focused on context/metrics, and verify with tests on a real executor.

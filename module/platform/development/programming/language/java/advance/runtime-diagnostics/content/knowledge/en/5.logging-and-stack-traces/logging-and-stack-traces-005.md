# 5.5 Collecting Unhandled Errors via UncaughtExceptionHandler

## Learning Objectives

In a multi-threaded Java application, an exception can cause **a thread to terminate abruptly** without the calling thread or monitoring system directly receiving a return value. `Thread.UncaughtExceptionHandler` provides a final observation point when a `Thread` is about to terminate due to an uncaught `Throwable`. However, this mechanism does not replace exception handling in business logic and **does not see every asynchronous task failure**.

After this lesson, you will be able to:

- Describe accurately when the JVM invokes `Thread.UncaughtExceptionHandler`, the `Thread`/`Throwable` arguments, and the scope of an exception's impact on the thread/process.
- Register a **per-thread** handler, a **JVM-wide default** handler, or attach a handler when creating worker threads via `ThreadFactory`.
- Understand the handler resolution order: thread → `ThreadGroup` → default; and know why `getUncaughtExceptionHandler()` can return a `ThreadGroup`.
- Capture error type, message, stack trace/cause, and diagnostic context without creating excessive logging risks.
- Distinguish errors escaping `Thread.run()` from errors caught and stored by `ExecutorService.submit()`, `Future`, `CompletableFuture`, or frameworks.
- Build a **runnable Java 17+ example** and match the exact stdout across both error collection paths.
- Recognize the handler's limitations regarding OOM, native errors, `System.exit`, SIGKILL, and task streams with their own error-reporting mechanisms.

## 1. What Does "Uncaught" Mean?

In Java, `Throwable` is the root of the hierarchy comprising `Exception` and `Error`. An error is called **uncaught** with respect to a thread when it propagates up through call frames without being caught/handled by Java code and ultimately causes the thread to **terminate abnormally**.

Example:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("invalid invoice");
}, "invoice-worker");
worker.start();
```

This is an **illustrative snippet**, not a standalone program. `IllegalStateException` is not caught inside the `Runnable`; the `invoice-worker` thread will terminate because of the error. Without a custom/default handler, the standard `ThreadGroup` mechanism usually prints the message and stack trace to **standard error (`System.err`)**. It does not automatically forward the exception back to the thread that called `start()`.

Distinguish three cases:

1. **Caught inside the worker:** `try/catch` handles it and does not rethrow; the thread can continue. `UncaughtExceptionHandler` is not invoked for caught exceptions.
2. **Uncaught and escapes the thread:** the JVM enters the uncaught exception reporting path, calling the corresponding handler before the thread finishes terminating.
3. **Caught by a framework/executor:** the task failure may reside in a `Future`, response, callback, or dedicated job system, even though the task's logic failed. The thread's handler is **not necessarily invoked**.

**Important:** the handler is a **last-resort observation and failure-reporting point for a thread**, not a `catch` block around every Java statement and not a task auto-recovery mechanism.

## 2. The `Thread.UncaughtExceptionHandler` API

Java defines a functional interface:

```java
@FunctionalInterface
public interface Thread.UncaughtExceptionHandler {
    void uncaughtException(Thread t, Throwable e);
}
```

The snippet above shows the **API signature**, not a file you need to redefine yourself. In the JDK, the actual interface is declared inside `java.lang.Thread`. Two parameters:

- `Thread t`: the thread terminating due to an uncaught exception, providing name, ID, and thread metadata.
- `Throwable e`: the actual error object, which may be a `RuntimeException`, `Error`, or another `Throwable`; it contains the message, stack trace, cause, and suppressed exceptions if present.

When a thread is about to terminate due to an uncaught exception, the JVM queries `getUncaughtExceptionHandler()` and calls `uncaughtException(t,e)`. If **the handler itself throws another exception**, the JVM **ignores the exception thrown by the handler**. Therefore, keep handlers small, resilient, and never rely on exceptions from a handler propagating elsewhere.

Essential APIs:

| API | Scope | Meaning |
| --- | --- | --- |
| `thread.setUncaughtExceptionHandler(handler)` | A specific `Thread` | Sets a dedicated handler for that thread |
| `thread.getUncaughtExceptionHandler()` | A specific `Thread` | Returns the explicitly assigned handler, or the thread's `ThreadGroup` if no dedicated handler is set (while the thread has not terminated) |
| `Thread.setDefaultUncaughtExceptionHandler(handler)` | JVM-wide default | Sets the fallback handler used when there is no dedicated handling from the thread/group |
| `Thread.getDefaultUncaughtExceptionHandler()` | JVM-wide default | Inspects the current default handler, which may be `null` |
| `ThreadGroup.uncaughtException(t,e)` | A thread group | Can forward to parent/default or handle directly |

Do not confuse `getUncaughtExceptionHandler()` with `getDefaultUncaughtExceptionHandler()`: the first method **does not always return the default handler**. If a thread has no dedicated handler set, its `ThreadGroup` may be returned.

Methods that set handlers can throw `SecurityException` in environments with corresponding permission policies. In applications/frameworks that already install handlers, do not overwrite them blindly, as you may disable existing logging/tracing.

## 3. Handler Selection Order: Thread, ThreadGroup, Default

A mental model for Java 17:

```text
A Throwable escapes the execution code of a Thread
                   |
                   v
      Does the Thread have its own handler?
          /                   \
        Yes                   No
        |                      |
        v                      v
  Thread's handler        ThreadGroup.uncaughtException
                             |
                             v
                        Parent group (if any)
                             |
                             v
                  Default handler (if any)
                             |
                             v
               If none, fallback behavior:
                  print stack trace to stderr
                 (ThreadDeath is an exception)
```

The `ThreadGroup` arrows depict the **default mechanism**. A `ThreadGroup` subclass can override `uncaughtException` and handle it differently without necessarily forwarding. Thus, there is no guarantee the default handler will observe every error if the application/framework customized the group.

**Typical precedence:**

- A thread with a dedicated handler sends errors directly to that handler; **the default handler does not automatically receive a duplicate copy**.
- Without a dedicated handler, the thread's `ThreadGroup` acts as the handler; standard behavior forwards to parent and then to default.
- Without a default handler and without custom `ThreadGroup` handling, ordinary errors are printed to stderr; for `ThreadDeath`, the default fallback does not print as it does for other Throwables.
- `setDefaultUncaughtExceptionHandler(null)` clears the custom default; it does not remove dedicated handlers set on individual threads.

A handler **should not indiscriminately call back into `ThreadGroup.uncaughtException`** to "preserve old behavior", because that can loop back to the default handler itself and cause recursion. If combining handling systems is required, design delegation explicitly and guard against loops.

## 4. Registering a Per-Thread Handler

Useful when you know a specific thread owns critical responsibility or want to tag by business group. Example of a dedicated data-import worker:

```java
Thread importThread = new Thread(
        () -> { throw new IllegalStateException("import failed"); },
        "import-worker");

importThread.setUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Uncaught in " + thread.getName());
    error.printStackTrace(System.err);
});

importThread.start();
```

This is an **illustrative snippet**, without `main` or deterministic stdout. The handler prints to **stderr**, not stdout. In real applications, route to a structured logger and appropriate telemetry mechanism; direct `printStackTrace` is mainly useful in demos or when intentionally writing to a collected error stream.

Setting the handler **before `start()`** is the easiest way to keep behavior deterministic. Changing the handler while a thread is already running introduces a race with when the thread might fail. Furthermore, having permission to mutate another thread does not mean doing so won't disrupt a framework.

When should you use a per-thread handler?

- Specialized workers whose failure must never go unnoticed.
- Manually created threads with a specific component/job ID.
- Worker groups needing error reporting different from the app-wide default policy.

There is no need to attach a dedicated handler to **every** thread if a default handler and executor/framework error handling already cover the goal. Avoid producing multiple records for the same exception.

## 5. Setting a JVM-Wide Default Handler

Example:

```java
Thread.UncaughtExceptionHandler existing =
        Thread.getDefaultUncaughtExceptionHandler();

Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    // Forward info to the appropriate logger/monitoring.
    System.err.println("Uncaught failure on " + thread.getName());
    error.printStackTrace(System.err);
});
```

This snippet illustrates two APIs. `existing` captures the prior handler for the deployment team to **evaluate coordination**; do not blindly invoke the old handler if there is a risk of recursion or duplicate logging. Manage/change the default policy only when your component truly owns JVM-wide configuration.

Install the default handler **early during startup** before the application spawns many threads so behavior is predictable. However, installing early still does not guarantee every error flows through it, because threads with dedicated handlers, custom `ThreadGroup`s, executors, and frameworks may take other paths.

In servers running application containers, logging libraries, job schedulers, observability agents, or frameworks, check what mechanisms are already installed. Replacing the default handler must not disable intentional alerting/error-event pipelines.

### 5.1 Does the Default Handler Stop the Entire Application?

**No.** If a background thread terminates abnormally, the handler may record the error, yet other threads continue running and the Java process can stay alive. If an uncaught exception escapes `main`, the main thread terminates, but the JVM exits only when the corresponding thread/process lifecycle conditions are met; active non-daemon threads can keep the process alive.

The handler **does not** automatically restart the thread, retry the task, roll back transactions, or guarantee an error response to clients. Recovery requires an independent policy: supervisor, designed worker restarts, bounded retries, circuit breakers, health checks, or reporting failure to an orchestrator.

## 6. Java 17+ Demo: Per-Thread, Default, and Errors Held in Future

This standalone example demonstrates three paths: a thread with a dedicated handler, a thread using the default handler, and a task submitted via `ExecutorService.submit` whose error is held inside a `Future`.

Create **`UncaughtHandlerDemo.java`**:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class UncaughtHandlerDemo {
    private static void report(String route, Thread thread, Throwable error) {
        System.out.println(route + " | " + thread.getName()
                + " | " + error.getClass().getSimpleName()
                + " | " + error.getMessage());
    }

    public static void main(String[] args) throws Exception {
        Thread.setDefaultUncaughtExceptionHandler(
                (thread, error) -> report("DEFAULT", thread, error));

        Thread invoice = new Thread(
                () -> { throw new IllegalStateException("invoice missing"); },
                "invoice-thread");
        invoice.setUncaughtExceptionHandler(
                (thread, error) -> report("PER_THREAD", thread, error));
        invoice.start();
        invoice.join();

        Thread parser = new Thread(
                () -> { throw new IllegalArgumentException("bad CSV"); },
                "parse-thread");
        parser.start();
        parser.join();

        ExecutorService pool = Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(r, "pool-thread");
            thread.setUncaughtExceptionHandler(
                    (t, error) -> report("POOL_UNCAUGHT", t, error));
            return thread;
        });

        Future<?> result = pool.submit(
                () -> { throw new IllegalStateException("task failed"); });

        try {
            result.get();
        } catch (ExecutionException exception) {
            Throwable cause = exception.getCause();
            System.out.println("FUTURE_CAUSE | "
                    + cause.getClass().getSimpleName()
                    + " | " + cause.getMessage());
        } finally {
            pool.shutdown();
        }

        System.out.println("END");
    }
}
```

Compile and run with **JDK 17 or higher**:

```bash
javac UncaughtHandlerDemo.java
java UncaughtHandlerDemo
```

**Exact stdout in a standard JDK 17 environment:**

```text
PER_THREAD | invoice-thread | IllegalStateException | invoice missing
DEFAULT | parse-thread | IllegalArgumentException | bad CSV
FUTURE_CAUSE | IllegalStateException | task failed
END
```

Line-by-line explanation:

1. `invoice-thread` has a dedicated handler. It receives `IllegalStateException`; the default handler does not emit an extra `DEFAULT` line for this thread.
2. `parse-thread` has no dedicated handler, so it routes through the default `ThreadGroup` to the installed default handler.
3. `pool.submit(...)` creates a task whose error is **caught and stored by `FutureTask`**. `result.get()` throws `ExecutionException`, whose `getCause()` is `IllegalStateException`. The `POOL_UNCAUGHT` line **does not appear**.
4. `invoice.join()` and `parser.join()` wait for each thread to finish so the two handler lines appear in the order shown; `result.get()` waits for the task result before the `FUTURE_CAUSE` line.
5. `pool.shutdown()` tells the pool to stop accepting new tasks and finish queued work; here the single task is already done. The code avoids `Thread.stop()` or `System.exit()` to simulate failures.

To stay focused on **exception routing**, the demo handler prints only the error type and message. In production, you need **stack trace/cause/suppressed exceptions** via a proper logger; two text fields are insufficient for diagnostics. Also, the demo overrides the default handler for the **test program's JVM**—do not blindly copy default-overriding logic into a running server without verifying existing framework handlers.

### 6.1 Why Doesn't the Demo Automatically Produce a Long Stack Trace on stderr?

`ThreadGroup`'s fallback behavior prints a stack trace **when no matching default/custom handler is installed**. Here both a per-thread handler and a default handler are present, and both simply call `System.out.println`. The JVM does not print another default stack trace after your handler has handled it. To see a stack trace, the handler itself must call a logger with the `Throwable` object or explicitly print the trace.

### 6.2 Small Modifications to Check Understanding

- Remove `invoice.setUncaughtExceptionHandler(...)`: `invoice-thread` will use the normal default path; the first line changes its label to `DEFAULT`.
- Remove installing the default handler: for threads without a dedicated handler, the standard fallback may print a stack trace to **stderr**, preventing a pure stdout comparison like the original.
- Replace `pool.submit` with `execute`: task propagation differs; do not infer from this demo's output that every error in an executor is captured by a `Future`.

## 7. Why Might Errors in ExecutorService Never Reach the Handler?

This is the biggest trap when using `UncaughtExceptionHandler` to monitor background processing.

### 7.1 `execute(Runnable)` and `submit(...)` Are Not Equivalent

| Submission path | How errors are typically surfaced | Should you rely on UncaughtExceptionHandler? |
| --- | --- | --- |
| `new Thread(r).start()`, `Runnable` throws uncaught error | Exception escapes `Thread`'s run path; thread terminates | **Yes**, per the thread's handler rules |
| `Executor.execute(r)` with `ThreadPoolExecutor` | Throwing `Runnable` can terminate the worker abruptly; executor handles worker lifecycle | **Possibly**, if the Throwable genuinely escapes to the thread; depends on executor and task wrapping |
| `ExecutorService.submit(r/c)` | Usually wrapped in `FutureTask`; error is stored for `Future.get()` to report via `ExecutionException` | **No** for errors caught by `FutureTask` |
| `CompletableFuture.supplyAsync/runAsync` | Exception is stored as **exceptional completion**, observed via `get()/join()` or callbacks | **Do not rely** on the worker's handler |
| Thread/framework has its own `try/catch` and logs | Error never escapes to the thread boundary | No, because the error was handled in an inner layer |
| Task rejected by executor | `execute/submit` can throw `RejectedExecutionException` **on the submitting thread** | Not uncaught on the worker by default; handle at caller/rejection policy |

Note: if the **caller's** own thread throws `RejectedExecutionException` uncaught, the *caller thread's* handler may run when that thread terminates. That is a different phenomenon from "the worker caught a job failure".

### 7.2 Why Can't `Future.get()` Be Ignored?

A `FutureTask` catches `Throwable` from task execution and records failure state. If an application calls `submit()` and **abandons the `Future`**, the error risks never appearing in logs/alerts as expected.

```java
// Illustrative snippet inside a method that already has ExecutorService pool.
Future<?> future = pool.submit(() -> {
    throw new IllegalStateException("background task failed");
});

try {
    future.get();
} catch (ExecutionException ex) {
    Throwable rootCause = ex.getCause();
    // Log rootCause with stack trace, job ID, timestamp, status.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Apply appropriate stop/state-transition policy.
}
```

This snippet is **not a standalone program** and is not advice to always call `get()` immediately after `submit()`, as doing so turns async work into synchronous waiting. In real systems, maintain a **dedicated result-tracking component**, completion queue, callback, or framework failure hook instead of discarding `Future`s.

In `ThreadPoolExecutor.afterExecute(Runnable, Throwable)`, the `Throwable` parameter can be `null` for a `FutureTask` even when the task failed, because `FutureTask` caught and stored the error. Official documentation recommends checking `Future.isDone()` when observing both kinds of failures, then extracting the cause via `get()` while handling `CancellationException`/`InterruptedException`. Do not assume `afterExecute` receives a non-null Throwable for every failing task.

### 7.3 `CompletableFuture`: Observing Exceptional Completion

Example **integration snippet**, using an existing `Executor`:

```java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalStateException("remote lookup failed");
        }, executor);

stage.whenComplete((value, failure) -> {
    if (failure != null) {
        // Log failure with context; may be a CompletionException wrapper.
    }
});
```

`CompletableFuture` manages exceptional completion state; the `whenComplete` callback or `get()/join()` path is the proper place to observe it. `join()` surfaces failures as unchecked `CompletionException` in the corresponding cases, while `get()` uses checked `ExecutionException`. Check `getCause()` when wrapped, without assuming every `Throwable` has a non-null cause.

`whenComplete` may run on the thread completing the stage or on an executor depending on how it is registered; error-reporting logic should stay lightweight and must never derive request IDs from thread names.

## 8. Attaching Handlers in ThreadFactory for Thread Pools

If the application **controls worker thread creation**, a `ThreadFactory` consistently assigns names and handlers as threads are created.

```java
// Integration snippet inside a service with a logger named LOGGER.
AtomicInteger sequence = new AtomicInteger();

ThreadFactory factory = task -> {
    Thread worker = new Thread(
            task, "payment-worker-" + sequence.incrementAndGet());

    worker.setUncaughtExceptionHandler((thread, error) ->
            LOGGER.log(Level.SEVERE,
                    "Uncaught error in " + thread.getName(), error));

    return worker;
};

ExecutorService executor = Executors.newFixedThreadPool(4, factory);
```

In an integrated program, import `java.util.concurrent.*`, `java.util.concurrent.atomic.AtomicInteger`, and `java.util.logging.Level`. `LOGGER` is the service's logger, not a built-in JDK variable. This snippet is **not standalone** and does not guarantee every task error reaches the handler, since `submit` wraps errors as shown above.

Practices to keep:

- Set the handler **before returning the worker** from the factory, so the executor can start the thread immediately afterward.
- Name threads to identify the worker pool; never embed tokens, payloads, or personal data in thread names.
- Never treat thread name as job ID: a pooled worker runs **many tasks sequentially**, so attach and clear job/request IDs in logging context per task lifecycle.
- Keep `ThreadFactory` small; avoid heavy allocations or potentially blocking API calls during thread creation.
- If a framework already provides a factory/handler, integrate with that mechanism rather than replacing it abruptly from outside.
- If an error actually kills a worker, `ThreadPoolExecutor` may spawn a replacement worker depending on pool state/configuration; the handler does not confirm the task was retried or recovered.

## 9. What Evidence Should Be Collected Inside the Handler?

The goal is a **traceable diagnostic event**, sufficient for others to understand the error type, thread, component, and timestamp. At minimum include:

| Info group | Useful fields | Reason |
| --- | --- | --- |
| Time | UTC ISO-8601 with offset, accurate timestamp | Correlate with system logs/traces/GC/events |
| Process | Service, environment, build/version, instance/pod, PID if available | Identify exact running build and blast radius |
| Thread | Thread name, thread ID, worker type, group when helpful | Identify the terminated thread |
| Exception | Throwable type, sanitized message, **full stack trace, cause, and suppressed** | Trace code path and failure mechanism |
| Work | Job/task ID, request/trace/correlation ID, operation type | Link thread error to business request |
| Impact | Whether worker is critical, lost/pending work, recovery mechanism | Distinguish single task error from loss of service capacity |
| Observability | Event counter, log location, alert/deduplication key | Spot recurring incidents and impact scope |

Example logging with `java.util.logging` in a class holding a logger:

```java
private static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger("runtime-diagnostics");

static void reportUncaught(Thread thread, Throwable error) {
    LOGGER.log(java.util.logging.Level.SEVERE,
            "Uncaught failure on " + thread.getName(), error);
}
```

This is an **integration snippet**, not a standalone app. The `log(Level, String, Throwable)` overload passes the exception object to the logging framework; the logger's handler/formatter config governs destination and stack rendering. Never log only `error.getMessage()`, as it can be blank and drops the cause chain.

### 9.1 Async Context Does Not Propagate Automatically

On Java servers, request IDs may sit in `ThreadLocal`/MDC or tracing context. When work moves onto a pool:

- Request context **does not automatically** appear intact on another thread unless propagated by design.
- Workers run multiple tasks; failing to clear MDC/ThreadLocal after each task can stamp logs with the **wrong request ID** from a prior task.
- By the time the handler runs after a failure, the framework may have already cleared context or never set it.
- An uncaught failure on an admin/GC helper thread need not correspond to any HTTP request.

A more reliable approach is creating an **explicitly identified task context**, propagating it intentionally, and cleaning up in `finally`. The handler is the last line of defense, not a substitute for logging at task boundaries where full business context is still available.

### 9.2 Protecting Sensitive Data

Stack traces, exception messages, system properties, or request contents can expose internal paths, hosts, usernames, URLs with credentials, or business data. **Mask/redact** before shipping centrally, enforce retention, and restrict access. Never print raw payloads, tokens, or unguarded object `toString()` output just for diagnostics.

For high-frequency repeating errors, apply rate limiting/deduplication while keeping total counts; if logs flood while the service is failing, logging itself can worsen CPU, I/O, and disk exhaustion.

## 10. Handlers Must Be Safe Under Abnormal Conditions

A handler runs at the exact moment a thread is dying due to an error. Do not turn it into complex business logic.

**Good design:**

- Keep it short and non-blocking. Prefer preconfigured loggers/queues; avoid synchronous network calls with long timeouts or acquiring locks prone to deadlock.
- Preserve the `Throwable` and stack trace; attach only metadata genuinely available.
- Ensure logger errors cannot loop exceptions; keep a minimal fallback path, while accepting that fallbacks can still fail when resources are exhausted.
- Never call `System.exit()` just because one task failed, unless the application has an explicit operational policy for fatal errors.
- Do not attempt to "continue" the dying thread, and do not blindly retry tasks inside the callback without knowing idempotency, transaction state, and backoff policy.
- Avoid `synchronized` on resources potentially held by the failing thread during unwind.
- Separate error reporting from process supervision: restart policies belong in the proper supervisor/health/queue layer.

**Unavoidable limitations:**

- `OutOfMemoryError` may reach the handler if it unwinds call frames and kills a thread, yet formatting stacks, allocating log objects, and shipping data can **fail for lack of memory**. Never guarantee successful log emission during OOM.
- With `StackOverflowError`, stack/resource exhaustion can restrict logging.
- `SIGKILL`, kernel OOM kills, `Runtime.halt()`, power loss, severe native crashes, or abrupt termination do not guarantee Java handlers run.
- `System.exit()` initiates JVM shutdown; it does not throw an uncaught exception to handlers.
- If `uncaughtException` itself throws, the JVM **ignores that error**; do not expect another handler to "catch it instead".
- Async logging buffers may not flush before process exit. For severe incidents, combine with process logs, container termination reasons, crash files, JFR/metrics, and independent log collectors.

This mechanism **reduces the risk of silent failures** in common scenarios; it does not guarantee 100% of errors produce a record.

## 11. Distinguishing Thread Failure from Process-Wide Failure

| Observation | Permitted conclusion | What else to check |
| --- | --- | --- |
| Handler logs `IllegalStateException` on worker A | Thread A terminated due to an uncaught error and the handler ran | Which task was affected, was the worker replaced, was data lost |
| `Future.get()` throws `ExecutionException` | That specific task failed and the error was stored in the Future | Was the task reported/recovered, who tracks Futures |
| Logs show `OutOfMemoryError` | The JVM reported a resource error on a Java path | Heap/native/metaspace/threads, cgroup, GC, process state |
| Container shows `OOMKilled` with no handler log | Sign of kernel/container termination due to memory limit | Cgroup events, memory peak, exact PID/container, timestamp |
| App still serves HTTP 200 after a worker dies | Some threads are still serving traffic | Loss of background capacity or growing queue depth |
| No uncaught logs over a period | No uncaught events observed on the current collection path | Future/callback/framework errors, log drops, crashes/kills, instrumentation |

Distinguish **`UncaughtExceptionHandler`** from a **shutdown hook**: a shutdown hook runs when the JVM enters an orderly shutdown under suitable conditions, whereas an uncaught handler runs when a thread dies from an uncaught Throwable. The two mechanisms have different purposes and neither guarantees data capture when a machine/process is killed abruptly.

## 12. Production Diagnostics Rollout Workflow

### Step 1 — Map Thread Creation and Execution Paths

Inventory what needs protection: manually created threads, executors, schedulers, message consumers, event listeners, or job frameworks. Check whether frameworks already include error handler callbacks or `Future` completion hooks. **Never install a default handler and assume everything is covered.**

### Step 2 — Choose Matching Error Collection Points

- **Raw threads:** per-thread or default handler.
- **Self-managed pools:** `ThreadFactory` attaching names/handlers, paired with task-result observation.
- **`submit`/`Future`:** supervisor reading results or completion pipeline; catch `ExecutionException` and preserve cause.
- **`CompletableFuture`:** controlled `whenComplete`, `handle`, `exceptionally`, or `get/join`.
- **Framework-managed:** dedicated callbacks/filters/error hooks (HTTP, scheduling, messaging) to preserve business context.

### Step 3 — Define Event Schema and Alerts

Standardize timestamp, service/build/env, thread name/ID, exception type, cause/stack, task ID, correlation ID, and impact. Design severity and alerting around frequency/impact while avoiding duplicate logs between task layers and global handlers.

### Step 4 — Controlled Reproduction

Use the lab program in Section 6 and a failing task in a test environment. Verify three things:

1. A per-thread handler receives its thread's error without the default handler duplicating it.
2. The default handler receives errors from threads without per-thread handlers under the default `ThreadGroup`.
3. Errors from `submit` surface via `Future.get` and are not silently missed because the worker handler did not run.

Never induce OOM, native crashes, or production kills just to test handler logging; those paths have no guarantees.

### Step 5 — Test Under Realistic Workload

Observe event counts, logging latency, event drops, I/O cost, log quotas, and the impact of repeating errors. For pools, monitor worker count, queue depth, task failures, and throughput; a handler event alone does not confirm system recovery.

### Step 6 — Conclude and Monitor

Report clearly which **error paths are covered**, which are not, observed signals/data, limitations, and how remaining failures are detected. After fixing a root cause, run regression tests under the exact triggering conditions and monitor metrics/logs/alerts to confirm the change.

## 13. Diagnostic Event Schema Template

Illustrative example of an event stripped of sensitive data:

```json
{
  "timestamp": "2026-10-29T08:00:00Z",
  "service": "invoice-service",
  "environment": "staging",
  "build": "demo-build-17",
  "event": "uncaught_thread_exception",
  "thread_name": "invoice-worker-2",
  "thread_id": 18,
  "exception_type": "java.lang.IllegalStateException",
  "message": "invoice missing",
  "trace_id": "synthetic-trace-001",
  "task_id": "synthetic-task-123",
  "severity": "ERROR",
  "recovery_state": "worker_terminated"
}
```

This is an **illustrative schema**, not automatic output from `UncaughtExceptionHandler`; trace/task IDs must come from real task context rather than being guessed or fabricated when missing. In real implementations, include the exception stack trace/cause in appropriate fields or logging attachments. `thread_id` is an example and is not constant across runs.

Other metrics worth tracking:

```text
uncaught_thread_exceptions_total{service, component, exception_type}
background_task_failures_total{service, executor, task_type}
worker_restarts_total{service, component}
```

These are **suggested metric names**, not default metrics emitted by the JVM. When designing labels, avoid putting error messages, request IDs, or task IDs into metric labels with unbounded values that cause cardinality explosion. Specific IDs belong in logs/traces, not high-cardinality Prometheus labels.

## 14. Common Implementation Mistakes

1. **Installing a default handler and assuming it catches every pool error.** `FutureTask` and `CompletableFuture` usually capture exceptions without killing workers.
2. **Logging only `getMessage()`.** Loses exception type, stack trace, cause, and important suppressed exceptions.
3. **Overwriting a framework's handler.** Can break existing monitoring, logging, or crash reporting policies.
4. **Confusing `ThreadGroup` with the default handler.** `getUncaughtExceptionHandler()` may return the group rather than the object from `Thread.getDefaultUncaughtExceptionHandler()`.
5. **Calling the default handler manually from another handler without cycle protection.** Delegation can loop back onto itself or duplicate logs.
6. **Believing the handler revives the thread.** The handler runs as the thread is terminating; it does not resume the `Runnable`.
7. **Abandoning the `Future` after `submit`.** The task fails silently without anyone checking the result or alerting.
8. **Attaching uncared-for request context to pooled threads.** MDC/ThreadLocal may be missing or carry stale data from a prior task.
9. **Logging full requests/tokens in error logs.** Leaks private data; mask secrets and bound payload size.
10. **Doing heavy synchronous logging inside the handler.** A thread already in severe failure may block further on network calls, locks, or large file flushes.
11. **Emitting unbounded logs on repeated errors.** Causes I/O and disk pressure, worsening the incident.
12. **Treating `OutOfMemoryError` as guaranteed to log.** Memory may be too scarce to allocate the log event.
13. **Treating exit codes/process kills as uncaught Java exceptions.** Kernel kills, `halt`, and native crashes do not guarantee handler execution.
14. **Assuming losing one worker means the entire process died.** Other threads continue running; dedicated health/restart policies are needed.
15. **Not distinguishing stderr and stdout in tests.** Default fallback usually prints stack traces to stderr, while demos print to stdout.
16. **Failing to test on the real execution path.** Raw threads, executor `execute`, `submit`, schedulers, and `CompletableFuture` surface errors differently.
17. **Using thread names as business IDs.** Pools reuse threads across many tasks; track correlation IDs per task.
18. **Not reporting recovery state.** Catching the exception is step one; verify whether the task failed permanently, retried, or stayed queued.

## 15. Self-Check Questions

1. A `Thread` throws an uncaught `IllegalStateException`. Which API does the JVM invoke, and what two arguments does the handler receive?
2. When a thread has a dedicated handler installed, does the default handler also receive the same exception automatically? What role does `ThreadGroup` play when no dedicated handler exists?
3. Why can `thread.getUncaughtExceptionHandler()` return a `ThreadGroup` while `Thread.getDefaultUncaughtExceptionHandler()` returns the application-installed handler?
4. Why do exceptions in `ExecutorService.submit` usually not reach the worker's handler? Through which method must `Future` callers inspect exceptions?
5. `Executor.execute` throws `RejectedExecutionException` on the calling thread. Does that error belong to the worker's handler by default?
6. A handler logs only `error.getMessage()`, which is null. Which fields must be added to enable investigation?
7. If an `OutOfMemoryError` occurs, can you guarantee a logger inside the handler succeeds? Why?
8. A handler logs an error on `scheduler-1`, yet the process still serves HTTP. Which metrics/task states must you inspect to assess impact?
9. What exception type surfaces failures from `CompletableFuture.join()` in typical failure scenarios? Why might the global handler never see it?
10. How do you verify that a task ID/trace ID logged in a handler truly belongs to the task that just failed rather than leftover context from a prior task?
11. Why are `System.exit`, `SIGKILL`, and native crashes not cases where the handler reliably collects complete diagnostics?
12. An error occurs after installing a new default handler, yet no event appears. State at least four possible causes without prematurely concluding "no error occurred".

## References

- Oracle Java SE 17 — `Thread`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Oracle Java SE 17 — `Thread.UncaughtExceptionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html
- Oracle Java SE 17 — `ThreadGroup`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadGroup.html
- Oracle Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Key takeaway:** `UncaughtExceptionHandler` captures **Throwables that genuinely escape a thread**, in the order per-thread handler → thread group → default. It is valuable for never missing abnormal thread deaths, yet it does not replace observing `Future`, `CompletableFuture`, framework callbacks, or process-terminating errors. Preserve stack traces, context, and timestamps, and design separate recovery policies for failed work.

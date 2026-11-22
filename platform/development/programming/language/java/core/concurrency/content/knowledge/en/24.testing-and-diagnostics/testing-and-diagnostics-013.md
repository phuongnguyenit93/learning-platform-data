# Logging with Thread Name, Task ID, and Correlation ID in Java Concurrency

When multiple tasks run concurrently, their log lines interleave: the same thread can process multiple tasks sequentially, a single task can move across multiple threads, and a single request can spawn multiple child tasks. If logs only contain messages like `started` or `timeout`, it is difficult to tell which line belongs to which task, which request triggered it, and which worker encountered the issue.

Three additional fields help with diagnostics:

- **Thread name:** indicates which thread **actually emitted the log event**; useful for observing worker pools, deadlocks, starvation, and scheduling behavior.
- **Task ID:** identifies the unit of work being executed. Depending on the contract, this can be a logical work ID that remains stable across retries or an execution-attempt ID; the two should be clearly distinguished.
- **Correlation ID:** links logs belonging to the same request or business flow across multiple methods, tasks, and services. Multiple task IDs can share the same correlation ID.

This article focuses on **general Java concurrency**: threads, `ExecutorService`, `CompletableFuture`, `ThreadLocal`, Java Util Logging, and passing context across tasks. It does not depend on Spring-specific logging configuration, interceptors, or context propagation mechanisms.

## 1. Why Is a Single Log Field Not Enough?

Suppose a data import request creates two tasks to process two groups of records. An example of logs lacking context:

```text
Started
Started
Timeout
Completed
```

It is impossible to know for sure which task timed out, which task `Completed` belongs to, or whether the same worker re-ran the work.

When all three fields are present:

```text
level=INFO thread=import-worker-1 taskId=batch-84-part-1 correlationId=req-84 event=started
level=INFO thread=import-worker-2 taskId=batch-84-part-2 correlationId=req-84 event=started
level=WARN thread=import-worker-2 taskId=batch-84-part-2 correlationId=req-84 event=timeout
level=INFO thread=import-worker-1 taskId=batch-84-part-1 correlationId=req-84 event=completed
```

We can see that task `batch-84-part-2` encountered an error, while both tasks belong to `req-84`. The thread name clarifies which worker was handling the work at that moment. **Do not infer that a task is always tied to a single thread**: async pipelines can switch threads between stages, and pools reuse threads across different tasks.

### Recommended Consistent Field Conventions

| Field | Origin | Lifecycle | Role |
|---|---|---|---|
| `thread.name` | `Thread.currentThread().getName()` | Per thread; can be renamed | Diagnose which worker emitted the log |
| `task.id` | When creating the unit of work | Per logical task | Filter all processing steps of a task |
| `task.attempt` or `execution.id` | When starting an attempt | Per execution/retry | Distinguish reruns, takeovers, retries |
| `correlation.id` | Request/job boundary, or received from upstream after validation | Per related processing chain | Group logs across multiple tasks/threads/services |
| `parent.task.id` (optional) | Parent task | Per parent–child relationship | Reconstruct fan-out/fan-in relationships |
| `event`, `level`, `time`, `duration` | Log emission point | Per event | Understand outcomes and progression |

Typically, a `correlation.id` remains the same when a request creates multiple tasks. Each child task has its own `task.id`; if you need to track multiple attempts, store an additional `attempt` rather than generating a new task ID without preserving the link to the logical task. If a background task does not belong to any HTTP request, generate a correlation ID at the start of the workflow/job.

## 2. Naming Threads to Know Which Resource Is Working

Java allows naming a thread at creation time, via a `ThreadFactory`, or changing it using `Thread.setName()`. For executors, prefer naming threads **when creating workers**:

```java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

final class NamedThreads {
    private static final AtomicInteger NEXT = new AtomicInteger();

    static ThreadFactory factory(String prefix) {
        return job -> new Thread(job, prefix + "-" + NEXT.incrementAndGet());
    }
}
```

This is an illustrative class without `main`. You can pass the factory to `Executors.newFixedThreadPool(4, NamedThreads.factory("import-worker"))`. Names like `import-worker-1` then help when inspecting thread dumps and logs. Do not use thread names as business keys: Java does not guarantee uniqueness across the JVM or across restarts; two instances can have the same worker names. If you need to distinguish multiple instances, include `service.instance`, `host`, `process.id`, or deployment labels in your logs.

In applications using virtual threads (Java 21+), the number of threads can be very large and they may not have application-assigned names. Thread names remain useful supplementary information, but they do not replace `task.id`. Analyzing deadlocks, task stalls, or downstream bottlenecks requires combining logs with thread dumps, JFR, and metrics, not relying on thread names alone.

## 3. Complete Java 17 Example: Consistent Logging and Context Propagation Through an Executor

This is a standalone program using **JDK's `java.util.logging`** and a `ThreadLocal` that holds context for the currently running thread. An immutable `record` represents the correlation ID and task ID. When submitting a task, the code captures a context snapshot, sets it on the worker before execution, and **restores the previous context in `finally`** to prevent leaking into the next task.

Create the file `ContextLoggingDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ContextLoggingDemo {
    record Context(String correlationId, String taskId) {}

    private static final ThreadLocal<Context> CURRENT = new ThreadLocal<>();
    private static final Logger LOG = Logger.getLogger("demo.concurrent");

    static {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                Context context = CURRENT.get();
                String taskId = context == null ? "-" : context.taskId();
                String correlationId =
                        context == null ? "-" : context.correlationId();

                return "level=" + record.getLevel().getName()
                        + " thread=" + Thread.currentThread().getName()
                        + " taskId=" + taskId
                        + " correlationId=" + correlationId
                        + " event=" + record.getMessage()
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    static Runnable withContext(Context captured, Runnable action) {
        return () -> {
            Context previous = CURRENT.get();
            try {
                if (captured == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(captured);
                }
                action.run();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(job -> {
            Thread worker = new Thread(job);
            worker.setName("worker-1");
            return worker;
        });

        try {
            CURRENT.set(new Context("req-42", "task-A"));
            Future<?> first = pool.submit(
                    withContext(CURRENT.get(), () -> LOG.info("started")));
            first.get();

            CURRENT.set(new Context("req-42", "task-B"));
            Future<?> second = pool.submit(
                    withContext(CURRENT.get(), () -> LOG.info("completed")));
            second.get();

            CURRENT.remove();
            Future<?> background = pool.submit(
                    withContext(CURRENT.get(), () -> LOG.info("background")));
            background.get();
        } finally {
            CURRENT.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac ContextLoggingDemo.java
java ContextLoggingDemo
```

Three-line output (`ConsoleHandler` writes to **stderr** by default, without timestamps due to the custom formatter):

```text
level=INFO thread=worker-1 taskId=task-A correlationId=req-42 event=started
level=INFO thread=worker-1 taskId=task-B correlationId=req-42 event=completed
level=INFO thread=worker-1 taskId=- correlationId=- event=background
```

Calling `get()` forces the three tasks to complete in the order shown, so the output does not depend on scheduling timing across workers. The single thread `worker-1` is reused for all three tasks, yet the context is `task-A`, then `task-B`, then empty. This result demonstrates that **a thread name is not a task ID** and shows that cleanup works.

In this example, `ConsoleHandler`'s `Formatter.format()` is called synchronously when the log is emitted, so it reads the `ThreadLocal` on the right worker. **Production logging may format/write on a different thread if an asynchronous appender is used**. In that case, the context must be attached to the **log event at event-creation time**, such as through the logging library's structured fields/MDC, rather than reading `ThreadLocal` inside a delayed formatter. Do not copy this formatter example verbatim into an asynchronous logging pipeline without checking when context is captured.

### Why Use `try/finally` and Save `previous`?

Worker threads can be long-lived and process thousands of jobs. If you only call `CURRENT.set(context)` and forget `remove()`, task B may see task A's IDs. Beyond corrupting diagnostics, this is a risk of cross-user/cross-tenant data leakage. If a task invokes a nested inner wrapper, calling `remove()` alone would lose the parent context: the pattern of **saving the previous context and restoring it exactly** is safer in nested cases as well.

Cleanup is guaranteed even when `action.run()` throws an exception. Do not use `ThreadLocal` to store business data that must survive restarts; it only attaches metadata to the current execution flow. `ThreadLocal` does not automatically propagate to executor threads. `InheritableThreadLocal` also does not solve context propagation for pre-existing thread pools, because workers are typically created once and serve many different requests.

## 4. Propagating Context Across Asynchronous Boundaries

**Rule:** create context at the work boundary, capture a snapshot on submission, restore it on the executing thread, and clean up when done. Do not rely on the executing thread happening to be the same thread.

| Boundary | Required Action |
|---|---|
| Synchronous method call on the same thread | Current `ThreadLocal` is accessible, but scope must still be managed |
| `Executor.execute/submit` | Capture context at submission time, wrap `Runnable`/`Callable` |
| `CompletableFuture.supplyAsync/thenApplyAsync` | Capture context and wrap **each async stage** accordingly |
| `CompletableFuture.thenApply` without `Async` | The stage may run on the thread completing the previous stage or the calling thread; do not assume any thread context |
| `ScheduledExecutorService` | Explicitly choose the job's context at schedule/trigger time; do not accidentally retain a request context for too long |
| Message queue / process boundary | Serialize IDs into message metadata/headers, then validate/check input and reconstruct context |
| Virtual threads | Propagate context by task scope; do not rely on carrier thread affinity |

For `CompletableFuture`, the `Runnable`-based `withContext` helper above is not sufficient for lambdas that return a value. For `Supplier<T>`, create a wrapper using the **same idea** that returns the result and uses `try/finally`:

```java
import java.util.function.Supplier;

static <T> Supplier<T> contextualSupplier(Context captured, Supplier<T> action) {
    return () -> {
        Context previous = CURRENT.get();
        try {
            if (captured == null) CURRENT.remove();
            else CURRENT.set(captured);
            return action.get();
        } finally {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        }
    };
}
```

This is an **illustrative method snippet** meant to live inside a class that has `Context` and `CURRENT` like the previous example, not a standalone runnable file. When using `CompletableFuture.supplyAsync(contextualSupplier(captured, supplier), executor)`, the `captured` value must be obtained at the appropriate submission boundary. For a subsequent `thenApplyAsync`, pass the context again for the new stage; do not assume `ThreadLocal` follows `CompletableFuture` automatically.

If you are already using a library with MDC (Mapped Diagnostic Context), you can use `MDC.put`, `MDC.getCopyOfContextMap`, `MDC.setContextMap`, and `MDC.clear` **according to the actual API of your logging library and adapter**. MDC is usually thread-bound and is not a built-in feature of `java.util.logging`; it still requires capture/restore across thread switches. Proper context propagation also requires ensuring clean classloader/thread-local lifecycles in long-lived executors. Do not confuse MDC with full distributed tracing.

## 5. Assigning IDs at the Right Boundaries with the Right Semantics

A practical set of rules:

1. **At the entry point:** accept a valid correlation ID from a trusted upstream or generate a new ID. Avoid blindly trusting client-supplied strings; enforce length limits, allowed character sets, and access-boundary validation. If a trace context standard is in use, use a compatible format/convention.
2. **When creating a task:** assign `task.id` and maintain its relationship with `correlation.id`. For fan-out, each child task gets its own task ID; also set a parent task ID if needed.
3. **On retry:** keep the logical `task.id` if it represents the same unit of business work; attach a new `attempt` or `execution.id` to distinguish attempts. Do not use correlation ID as an idempotency key unless the contract explicitly defines them as identical.
4. **When logging:** always include the IDs in log events, including exception messages, timeouts, cancellations, retries, queue waits, and results.
5. **On completion:** restore/clear the context according to its scope. If a task spawns a child task that runs after the parent finishes, the child must receive its own snapshot before the parent cleans up.

Example pipeline:

```text
request (correlation=req-42)
   |
   +-- task-A (taskId=task-A, attempt=1) --> worker-1
   |
   +-- task-B (taskId=task-B, attempt=1) --> worker-2
   |       |
   |       +-- retry task-B (attempt=2) --> worker-3
   |
   +-- completion event (correlation=req-42)
```

All logs carry `req-42`; filtering by `task-B` reveals both attempts. If only thread names were used, the attempts would be disconnected and a worker could easily be mistaken for a single business operation.

### Correlation ID, Trace ID, and Span ID

A correlation ID is an application-defined identifier for a request or business flow. In **distributed tracing**, `trace_id` links a trace and `span_id` identifies a span; traces and spans have different rules for length, propagation, and parentage than task IDs. You can include `trace_id` alongside `correlation.id` in logs if the application has a tracer, but do not claim they are always synonymous. A long-running workflow can carry a correlation ID across multiple traces; a single trace can span multiple threads and tasks.

**Do not correlate logs using thread IDs or timestamps alone**: threads are reused, clocks between machines can drift, and multiple events can share the same millisecond. IDs and causal relationships must be propagated explicitly.

## 6. Logging at Moments with Diagnostic Value

Place logs deliberately at state transitions rather than spamming every internal step:

| Log Emission Point | Useful Additional Fields |
|---|---|
| `submitted` | `task.id`, `correlation.id`, queue name, accepted/rejected |
| `started` | thread name, attempt, queue wait duration |
| `waiting_for_lock` / `waiting_for_permit` | resource name, wait budget |
| `retry_scheduled` | retry reason, attempt, delay, remaining deadline |
| `cancel_requested` | caller/timeout reason; do not log `cancelled` until the task is confirmed stopped |
| `failed` | exception type, code, latency, **stack trace** when needed |
| `completed` | duration, outcome, safe-to-log summary of result |
| `shutdown` | pool name, task count, wait for completion, and rejection count |

Measure **queue wait** and **execution time** separately. If you only log `started` without logging `submitted`, queue latency is often missed. Use a monotonic clock such as `System.nanoTime()` for durations, and standard UTC timestamps or explicit offsets for logs compared across machines. Do not assume cross-machine timestamps establish absolute causal order.

For Java errors, log exceptions using the appropriate logger API, such as `LOG.log(Level.WARNING, "task failed", ex)` in `java.util.logging`, which preserves the stack trace when supported by the formatter. Avoid calling only `LOG.warning(ex.getMessage())`, which drops the exception type and stack trace. The minimal formatter example above only prints `record.getMessage()`; a production formatter must include the stack trace or use a standard encoder so `LogRecord.getThrown()` is not lost.

## 7. Structured Logging: Searchable and Safe Against Data Corruption

`key=value` logs like the demo are easy to read, but if an ID or event contains spaces, equals signs, newlines, or control characters, simple parsers will misread them or become vulnerable to **log injection**. In production, prefer structured encoders (such as properly escaped JSON) rather than manually concatenating untrusted data into strings. A log record should keep fields separate, for example:

```json
{
  "timestamp": "2026-01-15T10:20:30.123Z",
  "level": "WARN",
  "service": "importer",
  "thread.name": "import-worker-2",
  "task.id": "batch-84-part-2",
  "task.attempt": 1,
  "correlation.id": "req-84",
  "event": "downstream_timeout",
  "duration_ms": 2200
}
```

This is a **structural illustration**, not actual output from the program above. Every log should have a consistent event name (`task_submitted`, `task_started`, `task_failed`, `task_completed`) and a level reflecting severity: `INFO` for key milestones, `DEBUG` for diagnostic details, `WARN` for recoverable situations worth monitoring, and `ERROR` or `SEVERE` per framework convention for genuine failures.

**Cardinality** matters: correlation IDs and task IDs have very large numbers of distinct values. They work well as searchable log fields, but are usually **not** suitable as Prometheus metric labels or in-memory aggregation dimensions. Use low-cardinality labels for metrics (`pool`, `operation`, `status`), and keep IDs in logs and traces.

Do not put passwords, access tokens, cookies, sensitive personal data, or raw payloads in logs. For user-supplied IDs, validate/truncate and escape them. Ensure log access scopes prevent users in one tenant from viewing another tenant's data. If sampling is used, prefer retaining error/slow paths along with enough metadata to link the chain; log sampling can omit parts of an execution path and should be made clear to investigators.

## 8. Distinguishing Context Propagation from Data Races

`ThreadLocal` gives each worker **its own context value**, but it does not make concurrent operations thread-safe. If multiple tasks mutate the same `HashMap` or increment a non-atomic counter, complete log IDs will not fix the race condition. Thread dumps show which thread is waiting on a lock; log correlation links it to a task; meanwhile, you still need proper synchronization, atomic types, or concurrent data structures.

Similarly, context can leak if you:

- Forget to clean up in `finally` when an action throws an exception.
- Set context on the worker but reset it on the **calling thread** instead of the worker.
- Copy a **mutable** context object across threads and mutate it from multiple places.
- Use `InheritableThreadLocal` with a pool and assume it follows each submission.
- Create an async callback and forget to wrap one stage, causing logs with `task.id=-`.
- Use `CompletableFuture` defaults running in `ForkJoinPool.commonPool()` while assuming request context carries over.
- Use an async formatter/appender that reads thread-locals **after** the worker has already cleaned up.
- Use thread names as unique business keys; names collide across instances and restarts.

Use immutable context objects (such as a Java 17 `record`) and pass only the metadata needed. If nesting occurs, restore the previous context; if there is no parent context, call `remove()` rather than leaving a placeholder in `ThreadLocal` indefinitely.

## 9. Testing Correctness of Concurrent Logging

Logs are valuable when they are **complete, have the right context, and do not mix** under real-world conditions:

| Test Case | Expected Observation |
|---|---|
| Two tasks run sequentially on the same worker | Two different `task.id` values, same thread name |
| One request fans out into multiple tasks | Same correlation ID, different task IDs |
| Task switches threads via `thenApplyAsync` | Context remains correct when wrapped, thread name reflects actual execution thread |
| Task throws an exception | `finally` cleans up, subsequent task does not inherit old IDs |
| Task is cancelled/times out | Log accurately describes state, does not confuse cancel request with completion |
| Task retries multiple times | Same logical task ID, `attempt` distinguishes each attempt |
| Background task with no request | Context is initialized validly or missing fields are represented intentionally |
| Client sends long ID or newline characters | Encoder escapes/truncates, does not forge log lines |
| Async appender writes on a separate thread | Log event already captured the right IDs when created |
| Multiple JVMs have workers with the same name | Instance ID distinguishes where execution occurred |

An important test is to use a **single-thread executor** to submit task A with context, task B with a different context, and task C with no context, then inspect the logs: task C must not contain task A's or task B's IDs. Also test an exception thrown mid-task to verify `finally` always runs.

With complete logs, you can run a diagnostic query in order: filter by `correlation.id` to see the full workflow; select the failing `task.id`; break down by `attempt`; inspect `submitted/started/failed/completed`; then cross-reference `thread.name`, pool name, queue wait, lock wait, JFR/thread dumps, or metrics to locate the bottleneck. Across multiple machines, prioritize causal ID relationships over absolute timestamp ordering.

## 10. Practical Checklist

Before deploying logging for a concurrent Java system, verify:

1. **Correlation ID**, **logical task ID**, **execution/attempt ID**, and their uniqueness scopes are clearly defined.
2. Thread factories give workers recognizable names; logs also include service/instance identifiers to avoid confusion across JVMs.
3. When submitting async tasks, context is captured at the right time and restored/cleared on the **executing thread** using `try/finally`.
4. Every async continuation is wrapped with the appropriate context; do not rely on `InheritableThreadLocal` for executors.
5. The logger/encoder attaches context **when creating the log event**, especially if using an async appender.
6. Submit/start/retry/cancel/error/complete milestones are logged with accurate durations and outcomes.
7. Logs are escaped and controlled for sensitive data, size, retention, sampling, and access permissions.
8. Metrics use low-cardinality labels; IDs are kept for logs and tracing.
9. Tests cover failing tasks, retries, worker reuse, empty context, and thread switches.
10. When diagnosing concurrency issues, combine logs with thread dumps/JFR, metrics, and queue data rather than drawing conclusions from thread names alone.

**Key takeaway:** thread name answers *what is running where*, task ID answers *which unit of work*, and correlation ID answers *which events belong to the same journey*. In concurrency, **propagating and cleaning up context across asynchronous boundaries** is just as important as adding the three fields to your log format.

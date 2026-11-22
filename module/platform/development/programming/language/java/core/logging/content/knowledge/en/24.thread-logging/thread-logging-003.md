# Logging in Thread Pools (Java 17+)

## 1. Why Is Logging in a Thread Pool Easy to Misread?

A `thread pool` is a set of threads reused to run multiple tasks. With `ExecutorService`, the thread calling `submit()` or `execute()` only **submits the work**; the actual task may run on a different worker at a different time. When the number of tasks exceeds the number of workers, tasks also wait in a queue.

Three important consequences for logging:

- **Interleaved logs:** logs from two tasks can appear interleaved; the execution order across tasks does not necessarily match the submission order.
- **Reused workers:** the same thread name (for example, `log-worker-1`) can process multiple different requests or jobs in sequence. You cannot use the thread name alone to infer which request produced a log entry.
- **Thread-bound context can leak:** `ThreadLocal`, MDC, or other tracing metadata do not automatically follow a task from the submitting thread to the worker. If you forget to clean it up, context from an old task can appear in a new task's logs.

For example, suppose a pool with two workers processes three jobs A, B, and C: A and B can run concurrently; C waits for a free worker and then runs on the same thread that just processed A or B. Logs showing `start(A)`, `start(B)`, `end(A)`, `start(C)` are one possibility, not a guaranteed order.

**Principle:** every important log line should state *what event happened*, *which task/request it belongs to*, *which worker ran it*, and *whether it succeeded or failed*. Do not infer context solely from log line order or thread names.

## 2. What Fields to Log and Where to Log Them

A task log record is typically useful when it includes the following fields:

| Field | Meaning | Notes |
| --- | --- | --- |
| `event` | Event name: `task_submitted`, `task_started`, `task_succeeded`, `task_failed` | Use stable names for searching and alerting |
| `taskId` / `jobId` | Unique identifier for a single task execution | Do not use the thread name as a substitute |
| `requestId` / `traceId` | Correlates logs with a request or trace across multiple components | Must be propagated across async boundaries or re-established on the worker |
| `worker` | `Thread.currentThread().getName()` | Useful when investigating scheduling, not a business identifier |
| `elapsedMs` / `queueWaitMs` | Processing time and queue wait time | Measure durations with `System.nanoTime()` |
| `outcome` and exception | Result and stack trace on failure | Log the exception at a single chosen handling boundary to avoid duplicate logs |

You should log at **task submission**, **execution start**, **completion**, and **failure** when those events have operational value. `task_submitted` is logged on the submitting thread; `task_started` is logged inside the worker. If you want to measure queue latency, record `submittedAtNanos` at submission time and compute the difference at the start of the task. Wall-clock timestamps are suitable for correlating logs; `nanoTime()` is suitable for measuring duration.

For systems that support structured logging, prefer JSON fields or stable key/value pairs. Example message payload:

~~~text
event=task_started taskId=job-42 requestId=req-7 worker=log-worker-2
event=task_succeeded taskId=job-42 elapsedMs=18 worker=log-worker-2
~~~

The two lines above only illustrate the field format; they do not imply that the lines must appear adjacent to each other or on the same thread across every processing step.

## 3. Complete Java 17 Example: Naming Workers, Correlating Jobs, and Catching Errors

This example uses only the Java standard library. It creates a two-thread pool, names the workers, runs three jobs, and intentionally makes `job-B` fail to show the difference between worker logs and logs on the thread retrieving the result.

Save to **`ThreadPoolLoggingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class ThreadPoolLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ThreadPoolLoggingDemo.class.getName());

    record Job(String id, boolean shouldFail) {}

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger nextWorker = new AtomicInteger();
        ThreadFactory factory = task -> new Thread(
                task, "log-worker-" + nextWorker.incrementAndGet()
        );
        ExecutorService pool = Executors.newFixedThreadPool(2, factory);

        List<Job> jobs = List.of(
                new Job("job-A", false),
                new Job("job-B", true),
                new Job("job-C", false)
        );
        List<Future<String>> results = new ArrayList<>();

        try {
            for (Job job : jobs) {
                results.add(pool.submit(() -> process(job)));
            }

            for (int i = 0; i < results.size(); i++) {
                Job job = jobs.get(i);
                try {
                    results.get(i).get();
                } catch (ExecutionException error) {
                    LOG.log(Level.SEVERE,
                            "event=job_failed jobId=" + job.id(),
                            error.getCause());
                }
            }
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException error) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw error;
            }
        }
    }

    private static String process(Job job) {
        long started = System.nanoTime();
        String worker = Thread.currentThread().getName();

        LOG.info(() -> "event=job_started jobId=" + job.id()
                + " worker=" + worker);

        if (job.shouldFail()) {
            throw new IllegalStateException("simulated failure");
        }

        long elapsedMs =
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
        LOG.info(() -> "event=job_succeeded jobId=" + job.id()
                + " worker=" + worker + " elapsedMs=" + elapsedMs);
        return "ok";
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ThreadPoolLoggingDemo.java
java ThreadPoolLoggingDemo
~~~

Messages you might observe (this is a **summary of the log meaning**, not exact stdout):

~~~text
event=job_started jobId=job-A worker=log-worker-1
event=job_started jobId=job-B worker=log-worker-2
event=job_succeeded jobId=job-A worker=log-worker-1 elapsedMs=...
event=job_started jobId=job-C worker=log-worker-1
event=job_failed jobId=job-B
java.lang.IllegalStateException: simulated failure
~~~

With its default console configuration, `java.util.logging` typically writes to **stderr**, including timestamps, logger/method names, and stack trace details; the example does not require a fixed stdout format. Execution order, chosen worker, and `elapsedMs` vary with scheduling. Do not write tests that assert the exact sample order above.

How it works:

1. `ThreadFactory` gives workers readable names. The pool reuses threads; having more jobs than workers does not spawn a new worker for each job.
2. `job.id()` is passed explicitly into each `submit()` lambda. As a result, every log can be tied to the right job even when threads change or are reused.
3. `process()` logs `job_started` and `job_succeeded` directly on the worker. When `job-B` throws `IllegalStateException`, no `job_succeeded` log is emitted for that job.
4. `submit(Callable)` stores exceptions inside the `Future`. `Future.get()` throws `ExecutionException`, and `getCause()` holds the original error. In this example, only the thread calling `get()` logs `job_failed` with the stack trace, avoiding logging the same error twice.
5. `shutdown()` stops accepting new tasks while letting submitted tasks continue; `awaitTermination()` waits up to a limit; `shutdownNow()` attempts to interrupt running/queued tasks without guaranteeing immediate termination. When interrupted, the code requests pool shutdown, restores the interrupt flag, and rethrows the exception to the caller.

In a real application, agree on **who is responsible for logging errors**: at the worker boundary if the task handles its own failures, or where the `Future` result is collected if the caller is responsible. If both log the stack trace, the same error will be double-counted.

## 4. `execute()`, `submit()`, and Async Tasks: Where Do Exceptions Surface?

| Submission Method | When a Task Throws an Uncaught Error | Reliable Way to Observe |
| --- | --- | --- |
| `Executor.execute(Runnable)` | Unchecked exceptions can escape `run()`; the worker may terminate and the uncaught exception mechanism handles it | Wrap the task in `try/catch` at an appropriate boundary or configure uncaught exception handling |
| `ExecutorService.submit(Runnable/Callable)` | The error is captured in the `Future` and usually does not reach `UncaughtExceptionHandler` | Call `Future.get()` and handle `ExecutionException.getCause()`; or attach handling at the task level |
| `CompletableFuture.supplyAsync(...)` | Completion becomes exceptional | Use `whenComplete`/`handle`/`exceptionally`; `join()` may throw `CompletionException` |

Do not rely solely on `Thread.setUncaughtExceptionHandler(...)` to catch every pool error. In particular, `submit()` typically wraps the task in a `FutureTask`, so errors do not escape through the uncaught handler path. With `ThreadPoolExecutor.afterExecute(Runnable, Throwable)`, the `Throwable` parameter can also be `null` for tasks submitted via `submit()` even when the `Future` failed; inspecting it requires knowing how to extract the result from the completed `Future`.

Do not discard a `Future` if its result or failure matters. If the application intentionally submits fire-and-forget tasks, establish an explicit error-handling boundary inside the task itself or a centralized observation mechanism. Standardize naming, error codes, log levels, and retry policies so errors do not disappear silently in the queue.

## 5. MDC and ThreadLocal: The Biggest Pitfall When Workers Are Reused

`MDC` (Mapped Diagnostic Context) is where a logging framework stores contextual fields such as `traceId` or `tenantId`, usually backed by data attached to the **current thread**. When a request-handling thread submits a task to a pool, the worker is a different thread: the caller's MDC is **not automatically carried over to the worker**. After finishing, if the worker does not clear the context, the next task on that same worker risks inheriting the previous task's `traceId`.

Example logic bug:

~~~text
request A -> worker-1: MDC traceId=A; completed but forgot to clear
request B -> worker-1: traceId not set; B's logs still show A
~~~

With plain Java `ThreadLocal<String>`, set the value inside the task and always clean up in `finally`:

~~~java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static Runnable taskWithTrace(String traceId, Runnable task) {
    return () -> {
        try {
            TRACE_ID.set(traceId);
            task.run();
        } finally {
            TRACE_ID.remove();
        }
    };
}
~~~

This is a **helper snippet inside a Java class**, not a standalone program. It passes `traceId` as an explicit parameter and prevents the finished task's context from lingering after completion. If your code genuinely has nested contexts on the same thread, you need a save/restore strategy for the previous value instead of always clearing; for independent task boundaries on a thread pool, clearing after each task is usually the easiest option to verify.

With **SLF4J MDC** and a logging backend that supports MDC, you can capture a copy of the context **on the submitting thread** and set/clear it inside the worker:

~~~java
import java.util.Map;
import org.slf4j.MDC;

// Helper in a class that already has an executor and logger; requires SLF4J + a compatible backend.
static Runnable propagateMdc(Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();
    return () -> {
        try {
            MDC.clear();
            if (captured != null) {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            MDC.clear();
        }
    };
}

// Call on the thread that submits the work, while MDC still holds requestId/traceId:
// executor.submit(propagateMdc(() -> logger.info("processing")));
~~~

`propagateMdc(...)` must be called at **submission time**, not after the request has already ended; each task needs its own snapshot. The helper above is designed for *independent task boundaries* in a pool. If called directly in a nested manner on the same thread when an outer MDC must be preserved, save and restore the previous context in `finally`. Capturing the context alone is not enough: your logging backend's pattern or encoder configuration must also output MDC fields (for example, `%X{traceId}` in Logback) for them to appear in the logs.

`InheritableThreadLocal` does not solve per-task context propagation in a pool: workers are usually pre-created and reused, so values inherited at thread creation time do not reflect new requests. Do not store request-scoped data in shared `static` variables. For framework-managed executors, you can use an appropriate task decorator or context propagation mechanism, but still verify capture timing, cleanup, and task execution paths.

## 6. Preserving Context Across Multiple Async Steps

When a task submits another task to an executor or uses `CompletableFuture`, each hop to a new worker is a **context propagation boundary**. If you omit the executor argument in `CompletableFuture.supplyAsync(...)`, Java uses `ForkJoinPool.commonPool()` by default; the task may run on threads outside the pool you named and configured.

~~~java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(() -> loadData(requestId), executor);
~~~

This is an illustrative snippet: `Result`, `loadData`, `requestId`, and `executor` must be defined in your application. Passing `requestId` as a parameter is explicit; if your logging library requires MDC, create an appropriate wrapper for the `Supplier` before passing it to `supplyAsync`. Do not assume a `whenComplete` callback always runs on the same thread or retains the previous stage's MDC. Log `taskId`/`requestId` at each significant boundary to trace the flow of work.

When you need tracing across HTTP, messaging, and task queues, `traceId` and `spanId` from a tracing system link multiple execution segments together; logging context should integrate with a real tracing mechanism rather than guessing relationships from thread names.

## 7. Log the Right Events, at the Right Level, and at the Right Cost

- **`INFO`:** important operational events such as job completion, batch acceptance, or a retry decision; avoid logging `INFO` on every iteration of a high-frequency task.
- **`DEBUG`/`TRACE`:** step-by-step details, configuration, and internal timings for investigation, enabled on demand. Use parameterized or lazy log messages to reduce string-building overhead when the level is disabled.
- **`WARN`:** recoverable anomalies, such as retries or queue wait time exceeding a threshold.
- **`ERROR`/`SEVERE`:** final task failure or an incomplete action; attach the exception to preserve the stack trace and cause.

Do not log every retry attempt as a final error if the system can still recover; choose a sensible counting policy and warning level. Conversely, do not turn unexpected failures into a bare `"failed"` line without a stack trace.

Logging also has a cost: formatters, synchronous I/O, file writes, and log shipping can slow down workers and lengthen queues. An async appender can offload I/O from processing threads, but it introduces its own queue, overflow policy, and risk of dropped logs on sudden process termination; it is **not** equivalent to an `ExecutorService` running business work. When measuring performance, observe `activeThreads`, queue size, wait time, error rate, dropped logs, and processing latency; do not assume adding more threads is the solution.

## 8. Situations Requiring Special Attention

1. **Rejected tasks:** when an executor is shutting down or the pool/queue is saturated according to its policy, submission can throw `RejectedExecutionException` **directly on the submitting thread**. Log the `taskId`, pool state, and handling policy; do not wait for a `task_started` log that will never arrive.
2. **Canceled or interrupted tasks:** `Future.cancel(true)` only *requests* interruption if the task is running. Code must handle interruption properly; avoid logging intentional cancellation as a critical system error. `Future.get()` can throw `CancellationException`.
3. **Multi-tenant/multi-request pools:** always clear MDC/ThreadLocal; avoid logging personal data, tokens, passwords, or sensitive request payloads. When accepting untrusted external IDs, sanitize and cap their length to prevent log injection or oversized log entries.
4. **Out-of-order logs:** timestamps from multiple threads can be very close together; log shippers or async appenders may buffer entries, making the observed order differ from execution order. Analyze by `traceId`, `taskId`, and event milestones rather than line position.
5. **Swallowed exceptions:** `submit()` does not guarantee that errors automatically appear as stack traces; retrieve the `Future` or handle errors at the boundary.
6. **Duplicate stack traces:** logging on the worker and then logging the exact same error again on the caller creates noise and skews incident counts. Only log at both places when they represent *two distinct events* with clear additional information.
7. **Pool lifecycle:** requests should not create a new pool and abandon it; manage executors according to the application lifecycle, perform controlled shutdowns, and monitor remaining running tasks.

## 9. How to Verify with Tests

To catch real bugs, test behavior rather than matching non-deterministic log order:

- Create a **single-thread** pool and run two tasks sequentially with `traceId=A` then `traceId=B`. Capture logs via a test handler/appender and verify that B's logs do not contain A; run another task with no context to verify cleanup.
- Run a throwing task via `submit()`. Verify that `Future.get()` throws `ExecutionException`, preserves the cause, and that the system logs exactly one failure event according to policy.
- Run multiple tasks on a small pool and verify that each log record has the right `taskId` even as threads are reused and logs interleave. Do not assert a scheduler-dependent order.
- Test the `RejectedExecutionException`, interrupt/cancel, and shutdown paths wherever the application actually exercises those scenarios.
- If using MDC, test both **the data in MDC** and **the encoder/pattern configuration**; a properly populated MDC still results in missing `traceId` values if the formatter does not output the field.

A practical way to read logs during an incident is to filter by `taskId`/`traceId`, reconstruct the `submitted → started → succeeded/failed` milestones, inspect the worker and wait duration, and then correlate the stack trace with executor state. This approach remains effective even when a single worker processes many tasks and logs from multiple tasks interleave.

## 10. Practical Takeaway

With thread pools, **pass task identifiers explicitly**, name workers for diagnostics, handle errors according to the submission API, and treat MDC/ThreadLocal as data that must be set **and cleared on every task execution**. Log enough fields for tracing and timing, while controlling cost, sensitive data, and duplicate logging. Done right, your logs will still clearly show how a job moved through the system even when it waits in a queue, switches threads, or fails.
# Async Context in Java Logging: MDC, ThreadContext, and Safe Context Propagation

## 1. The Problem: Logs Lose `requestId` Across Thread Handoffs

A request in a Java application may pass through an HTTP controller, a service, an `ExecutorService`, a `CompletableFuture` callback, a scheduler, or a message consumer. When investigating failures, operators usually want log lines across all of those steps to share the same `requestId` or `traceId`.

Expected example:

```text
INFO requestId=R-17 thread=http-worker  Request accepted
INFO requestId=R-17 thread=payment-1   Payment started
WARN requestId=R-17 thread=payment-1   Fallback selected
```

Without context propagation, however, the output can look like this:

```text
INFO requestId=R-17   thread=http-worker Request accepted
INFO requestId=<none> thread=payment-1  Payment started
WARN requestId=<none> thread=payment-1  Fallback selected
```

Worse still, if a worker previously ran an earlier request and did not clean up its context, new logs may carry the **stale `requestId` of another request**. This is not just a formatting issue—it also undermines incident investigation and privacy.

The common root cause is that **MDC/ThreadContext is bound to the executing thread** through a mechanism similar to `ThreadLocal`. When the application runs code on a different thread, data from the source thread does not automatically appear on the target thread. Moreover, thread pools reuse workers across unrelated tasks.

This lesson focuses on two things:

1. **Propagating logging context when business logic switches to another thread or callback.**
2. **Understanding how an async logging backend preserves context inside the log event.**

Do not conflate these two mechanisms. Replacing `ConsoleAppender` with `AsyncAppender` cannot fix a business worker that never received `requestId` in the first place.

## 2. Two Completely Different Async Boundaries

### 2.1. Business Async: Request Thread Submits a Task

```text
Thread A: handling request
  MDC {requestId=R-17}
        |
        | executor.submit(task)
        v
Thread B: executor worker
  separate MDC, possibly empty or stale
        |
        | logger.info("Payment started")
        v
LogEvent created on B
  with B's context
```

In this scenario, you need to **capture context on A**, **install it on B before calling the logger**, and **restore B's previous context after the task finishes**. Otherwise, the event already lacks `requestId` at the moment it is created.

### 2.2. Logging Async: Event Is Created and Handed Off to the Backend

```text
Thread A or B: calls logger
  MDC {requestId=R-17}
        |
        | logger.info("Payment started")
        v
LogEvent / ILoggingEvent
  includes metadata and context snapshot
        |
        | async queue / LMAX Disruptor
        v
Thread C: logging backend consumer
        |
        | Layout -> Appender -> stdout/file
        v
Collector / storage
```

In Log4j 2 Async Logger or standard Logback `AsyncAppender`, the backend typically **captures the required context data inside the event** before handing it off to a background thread. There is no need to propagate the request's `ThreadLocal` to the logging consumer thread itself. Custom layouts/formatters must read **the event's context**, not the consumer thread's `ThreadLocal` under the mistaken assumption that it holds request data.

| Handoff | Where does context need to be right? | How to achieve it |
| --- | --- | --- |
| HTTP/controller → executor worker | On the worker before the logger call. | Snapshot → install → run → restore. |
| Thread calling logger → async backend consumer | Inside the created `LogEvent`. | MDC/ThreadContext + snapshot-capable backend/layout. |
| Service A → Service B over HTTP/Kafka | Headers/metadata and B's local context. | Inject/extract according to the propagation protocol. |
| Reactor/coroutines switching schedulers | Framework context in each callback. | Use runtime-native propagation integration; do not rely on `ThreadLocal`. |

**Rule of thumb:** check **which thread** invokes the logger. The context on that thread determines what values the event carries when the log is emitted.

## 3. Types of Context in the Java Logging Ecosystem

### SLF4J MDC

**Mapped Diagnostic Context (MDC)** is a set of key-value pairs such as `requestId`, `traceId`, and `tenantId`. For example:

```java
// Illustration in an application that already has SLF4J and an MDC-capable provider.
MDC.put("requestId", "R-17");
try {
    logger.info("Payment started");
} finally {
    MDC.remove("requestId");
}
```

`MDC.put` operates on the **current thread's context** via the MDC adapter. With a backend like Logback, the pattern `%X{requestId}` can output that value. Do not assume that `MDC.put` on an HTTP thread will be visible inside an `ExecutorService` worker.

### Log4j 2 ThreadContext

Log4j 2 uses `org.apache.logging.log4j.ThreadContext`. It provides:

- **Context Map (MDC):** key-value pairs, such as `requestId=R-17`.
- **Context Stack (NDC):** a nested context stack, such as scope `checkout` → `payment`.

```java
// Illustration inside a method using Log4j 2.
ThreadContext.put("requestId", "R-17");
ThreadContext.push("payment");
try {
    logger.info("Calling gateway");
} finally {
    ThreadContext.pop();
    ThreadContext.remove("requestId");
}
```

If an application uses the NDC stack, copying only the MDC map will not propagate the full context. Explicitly decide whether both structures must be propagated.

### Distributed Tracing Context

Tracers such as OpenTelemetry maintain their own context for the current span, trace state, sampling, and baggage. MDC can hold **a projection of `traceId`/`spanId` for logging**, but the two mechanisms are not automatically the same thing.

- Calling `MDC.put("traceId", ...)` does not mean a distributed span has been created.
- Having an HTTP `traceparent` header does not mean a JSON logger will automatically emit `traceId`.
- Copying MDC does not guarantee that tracing context follows a `CompletableFuture`.
- Network propagation requires controlled inject/extract, not dumping the entire MDC.

If your framework or tracing agent already provides an official propagation mechanism, prefer using it and verify compatibility before writing custom wrappers.

## 4. Why `ThreadLocal` or `InheritableThreadLocal` Is Not Enough

`ThreadLocal<T>` gives each thread its own state. When a task from thread A runs on thread B, calling `ThreadLocal.get()` on B reads B's state. An executor does not automatically copy all of the caller's `ThreadLocal` values.

`InheritableThreadLocal` can pass values when **creating a child thread**, but thread pools reuse previously created workers. A single thread may handle R-1, R-2, and R-3 over several minutes. A value inherited at thread creation time is **not per-task propagation**.

Broken example:

```java
// Illustration: MDC on the submitting thread does not propagate automatically.
MDC.put("requestId", "R-1");
executor.submit(() -> logger.info("Task started"));
MDC.clear();
```

By the time the callback runs later, the worker may not have R-1. Or the worker might still hold R-0 because an earlier task forgot to clear it. Therefore, **never guess based on thread names or worker creation timing**.

## 5. The Standard Pattern: capture → install → run → restore

A safe wrapper follows four phases:

```text
Caller A                                Worker B
───────────────────────────────────────────────────────
capture snapshot S
  at submit time
         |
submit wrapped task ---------> snapshot existing state P
                               install a copy of S
                               try {
                                 task.run();
                               } finally {
                                 restore P;
                               }
Caller can modify/clear
context after submit
without altering S
```

**Capture where the task is submitted**, not inside a lambda already running on the worker. **Copy the map**, rather than sharing a mutable object across threads. **Restore in `finally`**, not only on the success path.

Why restore instead of always clearing?

- The worker may already have a valid context from a parent scope or nested task.
- Always calling `clear` can destroy context that existed before the new task.
- Restoring gives the wrapper clean scoping semantics even if the callback modifies MDC.
- If the task throws, `finally` still restores the state during normal stack unwinding.
- On a worker shared across multiple requests, restoring prevents ID leaks and context contamination.

If you enforce a policy that workers are always empty at job boundaries, clearing after each job can also be a valid contract. However, **save/restore** is the safer general pattern for wrappers that may be nested.

Never pass request objects, database sessions, auth tokens, cookies, or passwords through the logging context for debugging convenience. Propagate only allowlisted fields.

## 6. Runnable Java 17 Example: Lost Context, Propagated Context, and Leak Verification

The example below uses only **JDK 17 and `java.util.logging` (JUL)** with no external libraries. JUL does not provide a built-in MDC like SLF4J or Log4j 2, so the program uses a `ThreadLocal<Map<String,String>>` as a demo context. A real JUL `Logger` and `StreamHandler` are used to emit log lines.

**Important:** the demo formatter is **synchronous** and runs on the thread calling the logger, so it can read the `ThreadLocal` for demonstration purposes. In Log4j/Logback async logging, a custom layout must read the context **captured in the event**; it should not read a request `ThreadLocal` from the logging consumer.

What the program demonstrates:

1. Sets R-1 on `main` and submits an unwrapped task → no `requestId`.
2. Submits a wrapped task → worker receives R-1.
3. The task intentionally changes `requestId` to `INNER`; the wrapper must restore the worker's prior state.
4. Submits another unwrapped task → neither `INNER` nor R-1 remains.
5. Sets R-2 and submits a wrapped task → receives R-2.
6. Final unwrapped worker task → R-2 is not present.
7. `main` still has R-2 before scope cleanup.

### 6.1. `AsyncContextDemo.java`

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class AsyncContextDemo {

    private static final ThreadLocal<Map<String, String>> CONTEXT =
            new ThreadLocal<>();
    private static final Logger LOG =
            Logger.getLogger("demo.async.context");

    private AsyncContextDemo() {
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        for (Handler previous : LOG.getHandlers()) {
            LOG.removeHandler(previous);
        }

        Handler console = new StreamHandler(System.out,
                new ContextFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        console.setLevel(Level.INFO);
        LOG.addHandler(console);

        ExecutorService pool = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "context-worker"));

        try {
            install(Map.of("requestId", "R-1"));

            // Not propagated: worker does not automatically have R-1.
            pool.submit(() -> log("UNWRAPPED")).get();

            // Wrapper captures R-1 on the main thread.
            pool.submit(withContext(() -> {
                log("R1_WRAPPED");
                install(Map.of("requestId", "INNER"));
                log("R1_CHANGED_INSIDE");
            })).get();

            pool.submit(() -> log("AFTER_R1")).get();

            install(Map.of("requestId", "R-2"));
            pool.submit(withContext(() -> log("R2_WRAPPED"))).get();

            pool.submit(() -> log("AFTER_R2")).get();
            log("MAIN");
        } finally {
            CONTEXT.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
            LOG.removeHandler(console);
            // Do not close StreamHandler: it may close System.out.
            console.flush();
        }
    }

    private static void log(String phase) {
        LOG.info(phase);
    }

    private static Runnable withContext(Runnable task) {
        Map<String, String> captured = snapshot();

        return () -> {
            Map<String, String> previous = snapshot();
            install(captured);
            try {
                task.run();
            } finally {
                install(previous);
            }
        };
    }

    private static Map<String, String> snapshot() {
        Map<String, String> current = CONTEXT.get();
        return current == null ? null : new HashMap<>(current);
    }

    private static void install(Map<String, String> values) {
        if (values == null || values.isEmpty()) {
            CONTEXT.remove();
        } else {
            CONTEXT.set(new HashMap<>(values));
        }
    }

    private static final class ContextFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Map<String, String> current = CONTEXT.get();
            String requestId = current == null
                    ? "<none>"
                    : current.getOrDefault("requestId", "<none>");

            return record.getMessage()
                    + "|thread=" + Thread.currentThread().getName()
                    + "|requestId=" + requestId + "\n";
        }
    }
}
```

### 6.2. Compiling, Running, and Stdout

Create a file named `AsyncContextDemo.java` and run it with JDK 17+:

```bash
javac -encoding UTF-8 AsyncContextDemo.java
java AsyncContextDemo
```

**Exact stdout** under the example conditions:

```text
UNWRAPPED|thread=context-worker|requestId=<none>
R1_WRAPPED|thread=context-worker|requestId=R-1
R1_CHANGED_INSIDE|thread=context-worker|requestId=INNER
AFTER_R1|thread=context-worker|requestId=<none>
R2_WRAPPED|thread=context-worker|requestId=R-2
AFTER_R2|thread=context-worker|requestId=<none>
MAIN|thread=main|requestId=R-2
```

Why is the output deterministic?

- `Executors.newSingleThreadExecutor` uses a single worker named `context-worker` by the `ThreadFactory`.
- `Future.get()` waits for each task to finish before continuing; no `Thread.sleep` is used to force ordering.
- `withContext` is invoked on `main` at submission time, so it snapshots the right `requestId`.
- The worker saves its own context, installs the snapshot, runs the task, and restores in `finally`.
- Even though the task changes the ID to `INNER`, `AFTER_R1` is still `<none>`.
- `MAIN` still has R-2 because the worker uses a copy of the `Map` and does not mutate the caller's `Map`.
- The formatter reads the `ThreadLocal` on the log-emitting thread only because the handler is synchronous; this is not a pattern to copy directly into an async logging consumer.
- The handler flushes explicitly so output is observable; this **does not prove that logs were received by a remote collector**.

Limitations: the demo does not propagate context across a network, nor does it handle OpenTelemetry, reactive schedulers, JSON encoders, transactions, or audit durability. It is a learning model for a single executor boundary.

## 7. SLF4J + Logback: MDC Wrapper for `Runnable`

In a project with `slf4j-api` and an MDC-capable backend/provider, the key APIs are:

- `MDC.put(k,v)` and `MDC.get(k)` for the current thread.
- `MDC.getCopyOfContextMap()` returns a **copy of the Map**, which may be `null`.
- `MDC.setContextMap(map)` replaces the current map (clears then copies).
- `MDC.clear()` removes context on the current thread.

An illustrative wrapper placed in a Java class with the corresponding imports:

```java
import java.util.Map;
import org.slf4j.MDC;

static Runnable withMdc(Runnable task) {
    // Called on the SUBMITTING thread before the executor runs.
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            installMdc(captured);
            task.run();
        } finally {
            installMdc(previous);
        }
    };
}

static void installMdc(Map<String, String> context) {
    MDC.clear();
    if (context != null && !context.isEmpty()) {
        MDC.setContextMap(context);
    }
}
```

Usage inside request-handling code that already has `executor` and `logger`:

```java
MDC.put("requestId", "R-17");
try {
    executor.submit(withMdc(
            () -> logger.info("Background payment processing")));
} finally {
    MDC.remove("requestId");
}
```

**Note:** the snippet above depends on SLF4J and is not a standalone project like Section 6. Verify that your runtime backend actually supports MDC. Some MDC adapters may not store context, or may not include it in logs if the layout is not configured.

### Why Not Just Call `MDC.clear` in the Worker?

In a general-purpose wrapper, the worker may already have a map `P` before running the task. Calling `clear()` at the end simply empties it, destroying `P`. Saving `previous` and reinstalling it restores the state cleanly.

### SLF4J 1.7 and 2.x

Some SLF4J 2.0 versions accept `null` in `MDC.setContextMap(null)`, but to maintain compatibility and avoid depending on adapter details, the example **calls `MDC.clear()` when the snapshot is `null`**. Do not put `null` keys, and avoid `null` values if the provider does not support them.

### `Callable` with a Return Value

If the task has a return value or checked exception:

```java
import java.util.Map;
import java.util.concurrent.Callable;
import org.slf4j.MDC;

static <T> Callable<T> withMdc(Callable<T> task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            installMdc(captured);
            return task.call();
        } finally {
            installMdc(previous);
        }
    };
}
```

This snippet reuses `installMdc(...)` from above. Even if `task.call()` throws, `finally` still restores the context.

**Wrong capture timing:**

```java
// WRONG: withMdc runs on the worker, snapshotting the wrong thread.
executor.submit(() -> withMdc(task).run());

// RIGHT: wrapper is created on the caller.
executor.submit(withMdc(task));
```

### `MDC.putCloseable` and Nested Scopes

`MDC.putCloseable(k,v)` is useful when you only want to attach and later remove a single key. However, closing an `MDCCloseable` does not mean you snapshotted and restored the entire prior MDC; with nested scopes, you need to understand the adapter's semantics. A full-map snapshot/restore wrapper is better suited when per-task context isolation is required.

## 8. Log4j 2: `ThreadContext` Across an Executor

Log4j 2 provides both a map and a stack:

```java
// Illustrative code on the submitting thread, with executor and LOGGER available.
Map<String, String> map = ThreadContext.getImmutableContext();
List<String> stack = ThreadContext.getImmutableStack().asList();

executor.submit(() -> {
    try (CloseableThreadContext.Instance ignored =
                 CloseableThreadContext.putAll(map)
                         .pushAll(stack)) {
        LOGGER.info("Background job started");
    }
});
```

Imports for the snippet above:

```java
import java.util.List;
import java.util.Map;
import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.ThreadContext;
```

Steps:

1. Capture the map and stack on the submitting thread.
2. On the worker, install the values via `putAll`/`pushAll`.
3. `try-with-resources` ends the scope even if the callback throws.
4. If an NDC stack is used, do not ignore it while claiming to propagate "the full context".

**When the worker may hold stale context or the task can modify arbitrary keys:** for strong isolation, you need a wrapper that **snapshots the entire prior state, replaces the state with the task's snapshot, and restores the prior state**. Merely adding a few keys in a scope does not guarantee that stale keys outside the scope are removed.

Example of full map-only restore in Log4j 2:

```java
static Runnable withLog4jMdc(Runnable task) {
    Map<String, String> captured =
            new java.util.HashMap<>(ThreadContext.getImmutableContext());

    return () -> {
        Map<String, String> previous =
                new java.util.HashMap<>(ThreadContext.getImmutableContext());
        try {
            ThreadContext.clearMap();
            ThreadContext.putAll(captured);
            task.run();
        } finally {
            ThreadContext.clearMap();
            ThreadContext.putAll(previous);
        }
    };
}
```

This snippet **handles only the map**, not the NDC stack or separate tracing contexts. When a system uses NDC, add corresponding stack handling or use Log4j/framework scoping mechanisms. Do not arbitrarily copy a `ThreadContext` map across different classloaders or backends.

### Displaying MDC in a Layout

Log4j 2 `PatternLayout` snippet:

```xml
<PatternLayout
    pattern="%d{ISO8601} %-5p requestId=%X{requestId} [%t] %c - %m%n"/>
```

With `JsonTemplateLayout`, an event template JSON snippet can look like:

```json
{
  "requestId": {
    "$resolver": "mdc",
    "key": "requestId"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  }
}
```

This snippet is not a complete Logger/Appender configuration. Using `JsonTemplateLayout` requires a compatible `log4j-layout-template-json` module and an appender wired to the template. If you want to query by `requestId`, configure the encoder to emit it as a **separate field**, rather than just concatenating the ID into the message.

## 9. Context in Async Logger and `AsyncAppender`

**Async Logger is not the same as `AsyncAppender`**, though both can offload log output processing to a background thread.

In Log4j 2 Async Logger, the event is created with its associated context on the logger-calling thread and passed through the LMAX Disruptor pipeline. Standard Logback `AsyncAppender` prepares deferred-processing data, including MDC, before the appender worker consumes the event.

```text
Business worker with MDC {requestId=R-17}
             |
             | logger.info(...)
             v
LogEvent/ILoggingEvent created
  message, level, timestamp, context data
             |
          enqueue
             |
             v
Logger async consumer
   reads captured event context
             |
             v
Layout / Appender / stdout / file
```

**Two key takeaways:**

- If the business worker lacks `requestId` at log emission time, the event will lack that field from the start; switching to `AsyncAppender` will not fix it.
- If the event is created with the right MDC, a standard async backend can normally format context values from the event even though the consumer thread does not carry the request's MDC.

### Custom Formatter Bug

A custom formatter that directly reads `MDC.get("requestId")` or `ThreadContext.get("requestId")` **on the logging consumer thread** can read the wrong context. You must use the backend's event-reading API such as `ILoggingEvent`/`LogEvent`, not the request `ThreadLocal` at formatting time.

### Mutable Messages

A message containing a `Map` or mutable object can change between log emission and backend formatting, depending on the `Message` type and policy. To avoid output that does not reflect event time, log captured immutable values. With Log4j 2 `MapMessage` or custom `Message` types, do not mutate the object after the logger call when using async logging.

### Full Queues and Shutdown

Correct propagation does not guarantee that logs will never be lost. If the queue fills up, an appender is slow, or the JVM is killed before draining, events can still be blocked, dropped according to policy, or fail to reach the sink. Monitor queue/backpressure and implement proper shutdown handling; never rely on a droppable async log as the sole transaction audit record.

## 10. `CompletableFuture` and Callback Chains

`CompletableFuture.runAsync`, `supplyAsync`, or `thenApplyAsync` stages may execute on an executor or the common pool, depending on the API and configuration. Never assume they inherit the MDC of the code that registered the callback.

Insufficient example:

```java
MDC.put("requestId", "R-17");
try {
    CompletableFuture.runAsync(
        () -> logger.info("Payment processed"), executor);
} finally {
    MDC.clear();
}
```

Pattern for passing a `Runnable`:

```java
MDC.put("requestId", "R-17");
try {
    CompletableFuture.runAsync(
        withMdc(() -> logger.info("Payment processed")),
        executor);
} finally {
    MDC.clear();
}
```

This snippet requires the imports, variables, and helpers from the earlier section; it is a **snippet inside an SLF4J-enabled application**, not a standalone JDK program. For `Supplier<T>`/`Function<T,R>`, provide appropriately typed wrappers that also capture context at registration or submission time.

### Trap: When the Callback Actually Runs

```java
future.thenApply(value -> transform(value))
      .thenApplyAsync(value -> save(value), executor);
```

A stage may execute on the completing thread, the caller thread, or the executor. If an `Executor.execute()` wrapper only captures context **when the stage is actually scheduled**, the caller at that moment might be the thread completing the future rather than the thread that registered the stage. For complex chains, wrap the **callback/function at registration time**, or use your framework's official propagation integration.

`exceptionally`, `handle`, and `whenComplete` can also run on another thread. Protect both success and failure paths, not just a single result-handling callback.

### Cancellation and Exceptions

`try/finally` ensures restoration when a callback exits normally or via an exception. When a `Future` is cancelled or interrupted, the task may still run briefly or be interrupted; restoration happens during stack unwinding. If the JVM is forcibly killed or a task hangs indefinitely, cleanup cannot be assumed complete.

## 11. Schedulers and Long-Running Background Jobs

A scheduled task usually no longer belongs to the original request. If you capture `requestId=R-17` when registering a job that runs every minute, the job may carry R-17 indefinitely:

```java
// Illustration of a design with a risk of semantic error.
scheduler.scheduleAtFixedRate(
    withMdc(() -> performPeriodicJob()),
    0, 60, TimeUnit.SECONDS);
```

A better approach for background jobs:

- Generate a fresh `jobId` or `runId` for each job execution.
- If the job was triggered by a request, optionally store `parentRequestId` for causal linkage according to policy.
- Do not implicitly treat an already-finished HTTP request as the active context of the job.
- Create a new logging scope per execution and clear/restore it upon completion.
- If the job is retried or passed through a queue, propagate IDs using defined metadata.

Example:

```text
HTTP request R-17
    |
    | enqueue export job J-42
    v
Background execution
  jobId=J-42
  parentRequestId=R-17 (if permitted)
  event=EXPORT_STARTED
```

Do not use the thread name as a job's unique ID, because a worker can process many jobs.

## 12. Spring, Reactor, and Thread-Switching Runtimes

### Spring `TaskDecorator`

In Spring, `ThreadPoolTaskExecutor` provides a `TaskDecorator` mechanism in supported versions. A decorator can centrally capture/install/restore MDC on task submission.

However, verify **which executor actually runs the work**: a decorator on pool A does not apply to pool B, `ForkJoinPool.commonPool()`, or an executor created internally by a library. If your framework or tracing agent already provides built-in propagation, avoid double wrapping that could overwrite context.

### Reactor/WebFlux

Reactive pipelines can switch schedulers at many points. In Reactor, the framework's `Context` is designed to carry data through the pipeline; `ThreadLocal` does not automatically follow each operator. If you need MDC output, use a bridge/context-propagation mechanism compatible with your Reactor/Spring version and manage scopes inside callbacks.

Do not call `MDC.put` once in a controller and assume every `Mono`/`Flux`, callback, and worker thread will see the value. Test across `publishOn`, `subscribeOn`, timeout, and error stages.

### Coroutines and Virtual Threads

Coroutines can suspend and resume on different threads; context must follow the coroutine abstraction. Virtual threads or structured concurrency change how threads are created and used, but **they do not change the contracts of logging libraries and frameworks**. Do not turn `InheritableThreadLocal` into a default answer for every runtime.

## 13. Across HTTP, Kafka, and RabbitMQ Boundaries

If async work runs in **another JVM or service**, simply copying a Java `ThreadLocal` is impossible.

```text
Service A:
 local tracing context + MDC
       |
       | inject trace metadata into
       | HTTP headers or message properties
       v
Network / message broker
       |
       v
Service B:
 extract + validate metadata
       |
 create local tracing/MDC scope
       |
 logger.info(...)
       |
 clear/restore local scope
```

Distributed tracing commonly uses the **W3C Trace Context** standard via `traceparent`/`tracestate`. Baggage can carry extra metadata under an explicit contract, but never place tokens, cookies, passwords, or arbitrary personal data into propagated headers.

Key considerations:

- Validate externally received trace identifiers at trust boundaries.
- Do not fabricate a fake `traceId` that conflicts with the active tracing system.
- Distinguish application `requestId` from the tracer's `traceId`/`spanId`.
- For message retries or DLQs, define rules for copying or reinitializing tracing context and causal links.
- Do not forward the entire MDC map over HTTP headers without an allowlist.
- Propagating context over the wire **does not automatically make the logger emit the field**; it must still be bound to the local event and encoder.

## 14. Emitting Context in JSON Logging

JSON Lines example:

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","requestId":"R-17","traceId":"4bf92f...","event":"PAYMENT_STARTED","message":"Payment started"}
```

This is an illustrative schema. Achieving similar output requires **all three conditions**:

1. Application code or tracing placed `requestId`/`traceId` into the logging context on the **right thread** when creating the event.
2. The backend preserved those values in the event, including during async writes.
3. The JSON encoder is configured to emit the fields with the expected names, and the collector preserves the mapping.

If step 1 is missing, formatting cannot invent an ID out of thin air. If step 3 is missing, MDC holds the value, but the JSON output omits the field. If you only use a text `PatternLayout`, do not call it structured JSON.

Keep `requestId` as a string field, `event` as a stable code, and `message` as a human-readable description. Do not just embed IDs in free-form messages and parse them back out with regex.

## 15. Security Rules and Avoiding Context Leaks

Because logging context can be repeated across **every log event of a request**, a sensitive field in MDC can spread to many appenders and sinks.

Use a small allowlist:

| Field | Purpose | Notes |
| --- | --- | --- |
| `requestId` | Correlate logs belonging to a request. | Not an access token. |
| `traceId` | Distributed correlation. | Must match the tracing system. |
| `spanId` | Identify the current span. | May change per operation. |
| `jobId` | Correlate background tasks. | Generated per job/run. |
| `tenantId` | Identify tenant when permitted. | Subject to multi-tenant/PII policy. |
| `operation` | Current business operation. | Bounded name; do not use raw input as key. |

Never put passwords, OTPs, access tokens, refresh tokens, session cookies, private keys, raw request bodies, or entire domain objects into MDC. Do not rely on an entity's `toString()` to mask secrets.

**Stale context is a privacy bug:** a worker handling request B while carrying request A's ID misattributes logs. This can confuse operational reporting or mix customer data during incident investigation. Snapshot, restore in `finally`, and test worker reuse.

Limit the number of keys, value lengths, and lifetime. Do not use `requestId`/`traceId` as high-cardinality metric labels; they belong in log and trace fields.

## 16. When Messages or Context Data Are Mutable

Even when MDC is propagated properly, other logged data can be mutated between the logger call and async backend formatting.

```java
// Unsafe illustration when the backend formats a mutable
// object lazily while the code continues modifying it.
Map<String, Object> state = new HashMap<>();
state.put("status", "PENDING");
logger.info("State: {}", state);
state.put("status", "DONE");
```

Depending on the `Message` type and backend, formatting may snapshot early or read the object later. To ensure the event reflects the state at emission time:

```java
String statusAtEvent = String.valueOf(state.get("status"));
logger.info("State: {}", statusAtEvent);
```

Similarly, the MDC snapshot must be a per-task copy; changing `requestId` on the caller after submission must not alter the context of an already-submitted task. Do not assume every object in a log event is deep-copied just because the context map was captured.

## 17. Testing Async Context Properly

| Scenario | What to verify |
| --- | --- |
| Caller has R-1, unwrapped task | Worker must not be assumed to inherit MDC. |
| Caller has R-1, wrapped task | Worker event carries R-1. |
| Caller changes context after submit | Task retains the snapshot from submission time. |
| Worker already has context P | Wrapper temporarily installs S and then restores P. |
| Task changes MDC to `INNER` | Subsequent tasks do not leak `INNER`. |
| Task throws an exception | `finally` restores context; `Future` reports the failure properly. |
| Task is interrupted/cancelled | When the task exits, context is cleaned up. |
| R-1 then R-2 on the same worker | No cross-request contamination. |
| `CompletableFuture` stage runs late | Does not accidentally capture the completing thread's context. |
| Periodic scheduled job | Has a per-run `jobId`, not an old `requestId` forever. |
| Logback `AsyncAppender` | Event context is preserved when the consumer outputs it. |
| Log4j 2 Async Logger | Backend reads event context, not consumer MDC. |
| JSON layout | `requestId`/`traceId` are separate fields matching the schema. |
| Distributed service | Trace metadata is injected/extracted properly. |
| Data privacy | No unapproved tokens/cookies/PII are propagated. |

Do not use `Thread.sleep(100)` as proof that propagation succeeded. For tasks, use `Future.get()` or a latch to wait for results. For async logging backends, wait/drain using the framework's API or verify events at a test sink with explicit synchronization.

### Smoke Test in a Production-Like Environment

1. Send a request with `requestId=TEST-R-1`.
2. Emit one event on the HTTP thread and one event on a worker.
3. Parse the JSON output and verify `requestId`.
4. Send a subsequent request `TEST-R-2` on the same worker pool.
5. Verify that no ID from R-1 appears in R-2's events.
6. Test events on exception and retry paths.
7. Verify `traceId` matches the actual trace if tracing is enabled.
8. Confirm the collector/index does not drop or mis-map fields.
9. Verify no tokens or PII appear in the logs.

## 18. Diagnosing Missing `requestId` in Logs

```text
Log missing requestId?
        |
        v
Did caller set context properly?
        |
        v
Which thread called logger.info?
        |
        +--- HTTP/caller:
        |      was scope cleared too early?
        |
        +--- Executor worker:
               snapshotted before submit?
               installed before logger?
               restored in finally?
        |
        v
Did LogEvent have context at creation time?
        |
        v
Did AsyncAppender/AsyncLogger receive the event?
        |
        v
Does Layout/JSON encoder read event context?
        |
        v
Did Collector parse/index it properly?
```

Common mistakes:

1. Setting MDC only on the request thread while calling the logger inside an executor worker.
2. Using `InheritableThreadLocal` as an automatic solution for thread pools.
3. Capturing MDC inside the worker instead of on the submitting thread.
4. Forgetting `finally`, causing an old `requestId` to leak into later tasks.
5. Only calling `clear` after a task, wiping out a parent scope's context.
6. Sharing a mutable `Map` and modifying it after submission.
7. Assuming `AsyncAppender` copies context between **two business threads**.
8. Writing a custom formatter that reads the logging consumer's `ThreadLocal` instead of `LogEvent`.
9. Setting MDC properly but forgetting to configure `%X{requestId}` or the JSON resolver.
10. Seeing dropped events due to level/filter/queue/collector issues and blaming MDC.
11. Copying all HTTP headers into MDC, leaking tokens.
12. Treating a `traceId` string in MDC as full distributed tracing.
13. Letting a periodic job reuse the `requestId` from registration time.
14. Using a context-aware `Executor` wrapper when a stage is scheduled late, accidentally capturing the completing thread.
15. Not testing combinations of exceptions, cancellation, nested tasks, and thread reuse.

## 19. Performance and Production Rollout

Copying maps, setting `ThreadLocal`, and creating snapshots carry CPU and allocation costs. Do not optimize by skipping restoration or sharing mutable maps; correlation failures are far more expensive than a few map copies.

- Centralize propagation at **executor/task framework boundaries** where standard hooks exist.
- Keep only a few useful keys; avoid copying the entire request.
- When tracing is already integrated, use its official propagation tools to avoid two sources of truth.
- For reactive code, prefer the runtime's context abstraction.
- For jobs not tied to a request, create a fresh job context.
- Measure p50/p95/p99 latency, GC, task counts, events missing context, and sink throughput.
- If the async logging backend queue fills up, address queue/backpressure separately; fixing MDC will not make disk or network I/O faster.
- When upgrading runtimes or libraries, re-run tests because context propagation behavior and adapters can change.

## 20. Implementation Checklist

- [ ] Know which thread actually invokes the logger.
- [ ] Distinguish business async handoffs from async logging consumers.
- [ ] Use the proper API: SLF4J/Logback MDC or Log4j 2 `ThreadContext`.
- [ ] Capture a snapshot on the caller at the appropriate submit/callback-registration time.
- [ ] Install it on the worker before calling the logger.
- [ ] Restore worker state in `finally`, including on exceptions.
- [ ] Do not use `InheritableThreadLocal` as a substitute for per-task propagation.
- [ ] If using NDC, define rules for propagating and restoring the stack.
- [ ] Use runtime-appropriate integration for `CompletableFuture`, schedulers, and Reactor.
- [ ] Ensure background jobs do not inherit old request IDs indefinitely.
- [ ] Inject and extract distributed trace metadata in a controlled manner.
- [ ] Have layouts/encoders read MDC from the event, not from the consumer's `ThreadLocal`.
- [ ] Emit `requestId`/`traceId` as dedicated fields with a consistent schema.
- [ ] Keep tokens, passwords, cookies, and unnecessary private data out of context.
- [ ] Do not mutate logged objects after emitting an async log event.
- [ ] Test multiple requests on a shared worker pool and failure branches.
- [ ] Test end-to-end to the sink/collector, not just `ThreadLocal` state.
- [ ] Have observability for events missing correlation IDs, queue drops, and ingest lag.

## Official References

- [SLF4J MDC API — getCopyOfContextMap, setContextMap, and clear](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Logback — MDC and worker thread pools](https://logback.qos.ch/manual/mdc.html)
- [Log4j 2 — Thread Context, CloseableThreadContext, putAll/pushAll](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html)
- [Log4j 2 — JSON Template Layout and MDC resolver](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [Java 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [W3C Trace Context — traceparent/tracestate](https://www.w3.org/TR/trace-context/)

**Key takeaway:** Async context propagation requires **snapshotting on the submitting thread → installing on the executing thread → running the task → restoring in `finally`**. Asynchronous logging backends typically preserve captured context inside the event, but **cannot recover** a `requestId` that was never propagated to the business worker. Verify correctness using actual log events, ensuring no stale data leaks to subsequent tasks and that encoders/collectors emit the correlation fields properly.

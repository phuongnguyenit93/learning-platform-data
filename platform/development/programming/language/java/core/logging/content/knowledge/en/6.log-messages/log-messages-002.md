# Contextual Log Messages in Java Logging

## 1. Why Do Log Messages Need Context?

In a Java application handling many concurrent requests and tasks, messages like `ERROR Failed` or `INFO Done` are not enough to identify **which operation**, **which request**, and **which cause** are being referred to. A **contextual log message** is a log record that combines an event with the attributes needed so a reader or observability system can trace the source, processing scope, and outcome.

Compare:

```text
ERROR Timeout
```

and:

```text
WARN event=payment.authorize.timeout service=checkout requestId=req-42 orderId=ord-81 dependency=payment-gateway errorCode=UPSTREAM_TIMEOUT
```

The second line makes it possible to filter by event code, correlate logs for the same `requestId`, and find the impact of a dependency. These IDs and details are only examples. The goal is not to log as much data as possible: a message must have **enough context to diagnose, consistency to query, and safety for sensitive data**.

A good log record usually answers four questions: what happened, in which component, as part of which unit of work, and with what outcome.

## 2. Layering Context Fields

Context is attached to logs from multiple different scopes. Not every event needs every field.

| Scope | Example Fields | Purpose |
| --- | --- | --- |
| Application/instance | `service`, `version`, `environment`, `instanceId` | Identify the application/version emitting the log |
| Request or distributed flow | `requestId`, `traceId`, `spanId` | Connect events belonging to the same execution |
| Background task | `jobId`, `batchId`, `taskType` | Trace work outside an HTTP request |
| Operation | `operation`, `dependency`, `retryAttempt` | Identify the specific step or dependency |
| Outcome | `event`, `outcome`, `durationMs`, `errorCode` | Find the event, result, and cost |
| Error | `errorType`, exception/stack trace when appropriate | Diagnose failures |

IDs need to be stable within the **right scope**: `requestId` typically stays the same while processing a single request, `jobId` stays the same within a job, while `spanId` changes across spans within the same trace. Do not use a thread name or class name as the unique key for a request; thread pools can reuse threads, and a single request may pass through multiple threads.

Choose safe and controllable fields. Operation names, error codes, outcomes, and appropriate technical IDs are usually more useful than putting an entire HTTP body, cookie, token, or an object's `toString()` into logs.

### 2.1. Three Layers of a Message

A clean design approach:

- **Stable event**: `event=order.created`, `event=payment.authorize.failed`, `event=cache.refresh.completed`. Use consistent categorical names and do not concatenate dynamic IDs into the event name.
- **Human-readable message**: `"Payment provider timed out"` describes the situation, rather than serving as the sole source for systems to group errors.
- **Machine-queryable fields**: `requestId`, `errorCode`, `durationMs`, `outcome`, and other attributes encoded separately.

JSON example:

```json
{
  "timestamp": "2026-01-12T09:15:30.125Z",
  "level": "WARN",
  "service": "checkout",
  "event": "payment.authorize.timeout",
  "message": "Payment provider timed out",
  "requestId": "req-42",
  "traceId": "4e9c3ab82fbb4dce8e5be54b2a778d21",
  "dependency": "payment-gateway",
  "errorCode": "UPSTREAM_TIMEOUT",
  "durationMs": 1200
}
```

This is a **structural pattern**, not an automatic output from the JDK. Producing actual JSON requires a properly configured encoder/formatter. Pick one field-naming convention (`requestId` or `request_id`) and data types (`durationMs` as a number) and apply them consistently; JSON enables querying by field without relying on regexes over the message.

## 3. Context Following the Request/Job Lifecycle

A request may pass through an HTTP controller, service, repository, and then call another API. If each layer logs `Started` or `Done`, concurrent requests will interleave and mix together. Store correlation IDs in key events:

```text
INFO event=request.received  requestId=req-42 operation=checkout
INFO event=inventory.locked  requestId=req-42 orderId=ord-81
INFO event=payment.accepted  requestId=req-42 orderId=ord-81
INFO event=request.completed requestId=req-42 outcome=success durationMs=38
```

When `req-42` fails, filtering by this ID helps find all recorded milestones; when the system has distributed tracing, `traceId`/`spanId` help link across services.

### 3.1. Distinguishing Three Types of Identifiers

**Request ID** identifies a single request execution according to gateway/application conventions; one client request may trigger multiple internal calls. **Trace ID** identifies a distributed chain of work, usually propagated via a unified tracing mechanism. **Span ID** identifies each unit of work within a trace; multiple spans can share a trace ID.

A logical illustration:

```text
Gateway:  requestId=R, traceId=T, spanId=S1
Checkout: requestId=R, traceId=T, spanId=S2
Payment:  requestId=R, traceId=T, spanId=S3
```

`R/T/S1` are illustrative symbols only, not a valid trace ID format. When using OpenTelemetry or another tracing library, use the context and propagator provided by the library, such as W3C Trace Context; do not generate a new trace ID per service and lose correlation.

IDs from client headers need a trust policy and validation for length, character set, and format. Never use a value containing control characters or excessive length directly to construct field names, logger names, or log output.

### 3.2. Defining Clear Scopes

A good workflow includes: creating or receiving the correlation ID at ingress; propagating the context to subsequent steps; logging the outcome at the responsible boundary; and cleaning up or restoring the context when the request ends. For asynchronous jobs continuing after a request, you can create a new `jobId` and keep a link key to the originating request if genuinely useful.

Context held in a global `Map` mutable by multiple threads will be overwritten across requests. Pass an immutable context or use an appropriately scoped context mechanism. On the logging path, take a snapshot if the backend may process the event after the call returns.

## 4. Propagating Context in Java

### 4.1. Passing via Arguments and Immutable Objects

The easiest approach to control is passing the context explicitly to methods that need to log:

```java
record RequestContext(String requestId, String traceId) {}

void execute(RequestContext context) {
    // Business code uses context.requestId() when creating log events.
}
```

This is an **illustrative declaration snippet**, not a standalone Java program. The benefit is that context follows the data flow, does not depend on threads, and has low risk of leaking in asynchronous processing. The drawback is having to pass it through layers or design an appropriate wrapper.

### 4.2. SLF4J MDC and Backend Support

**Mapped Diagnostic Context (MDC)** is commonly used with `org.slf4j.MDC` so events emitted by loggers on the current thread can be tagged by the backend with the same `requestId`. The backend's pattern or encoder must be configured to include MDC fields; calling `MDC.put` alone does not guarantee any output will include that field.

The snippet below uses SLF4J and existing `processRequest()`/`logger`; it **does not run standalone with the JDK** because it requires the corresponding dependencies and backend:

```java
import org.slf4j.MDC;

String previous = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    logger.info("event=request.received");
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Restoring the previous value is important for nested scopes; blindly removing `requestId` can wipe out the outer caller's context.

**JUL (`java.util.logging`) has no built-in MDC API like SLF4J.** With plain JUL, you can pass context in the message, attach metadata to `LogRecord`, and use a custom Formatter/Handler. An application bridged to another backend must understand the actual backend and configuration, rather than assuming setting SLF4J's MDC will automatically make every JUL logger output that context.

### 4.3. Thread Pools, CompletableFuture, and Async

MDC/ThreadLocal does not automatically follow a task when it runs on an executor thread. Without propagating context, worker-thread logs lack `requestId`; without cleaning up context at the end, the thread pool can retain the previous request's `requestId` and mistakenly attach it to the next request.

This is an **illustrative snippet** using SLF4J MDC with existing `executor` and `runJob()`:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.execute(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        runJob();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
```

You need to import `java.util.Map` and `org.slf4j.MDC` in your project. `captured` is the snapshot taken when submitting the task, while `previous` is the existing context on the worker thread. The `finally` block restores the old values. With reactive pipelines, tracing, virtual threads, or frameworks that have their own context propagation, use the mechanism supported by that system; do not treat ThreadLocal as something that automatically follows every async step.

## 5. Choosing Message Encoding

For text logs, a concise approach is `key=value`; for large collection systems, JSON or a strongly typed event structure is usually easier to query. Whichever you choose:

1. **Field names must be consistent:** choose `requestId` or `request_id`, not a different style per module.
2. **Preserve data types:** in JSON, `durationMs` should be a number, and `outcome`/error codes should use a stable set of values.
3. **Escape untrusted data:** a newline in input must not create a forged log record.
4. **Do not depend on field position:** query logic should rely on field names, not the third or fourth position in a string.
5. **Do not turn messages into secrets:** do not put tokens, cookies, passwords, authorization headers, or raw payloads into context.

Example of log injection risk if an application concatenates input directly:

```text
INFO event=search.query value=normal
ERROR event=admin.override outcome=success
```

The `ERROR` line could simply be part of a user-supplied `value` containing a newline character. A standard JSON encoder or a quote/escape function in a text logging system prevents creating forged records.

## 6. Standalone Java 17 Example: Contextual Messages with JUL

This program uses only JDK 17 classes. `Logger` accepts a `LogRecord`; fields are held as a snapshot `Map` inside `LogRecord.parameters`; the custom `Formatter` in the example sorts keys and quotes values. This is an **example convention**, not built-in structured logging in JUL. There are no external libraries and no new logger created per request.

Create the file **`ContextMessageDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ContextMessageDemo {
    private static final Logger LOG =
            Logger.getLogger(ContextMessageDemo.class.getName());

    public static void main(String[] args) {
        Handler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder line = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" event=")
                        .append(record.getMessage());

                Object[] params = record.getParameters();
                if (params != null && params.length == 1
                        && params[0] instanceof Map<?, ?> context) {
                    TreeMap<String, String> ordered = new TreeMap<>();
                    for (Map.Entry<?, ?> entry : context.entrySet()) {
                        ordered.put((String) entry.getKey(),
                                (String) entry.getValue());
                    }
                    for (Map.Entry<String, String> field : ordered.entrySet()) {
                        line.append(' ')
                                .append(field.getKey())
                                .append('=')
                                .append(quote(field.getValue()));
                    }
                }
                if (record.getThrown() != null) {
                    line.append(" errorType=")
                            .append(record.getThrown().getClass().getSimpleName());
                }
                return line.append(System.lineSeparator()).toString();
            }

            private String quote(String value) {
                String safe = value.replace("\\", "\\\\")
                        .replace("\"", "\\\"")
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                        .replace("\t", "\\t");
                return "\"" + safe + "\"";
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        handler.setLevel(Level.ALL);
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(handler);
        try {
            process("req-17", true);
            process("req-18", false);
        } finally {
            handler.flush();
            LOG.removeHandler(handler);
        }
    }

    private static void process(String requestId, boolean success) {
        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("requestId", requestId);
        fields.put("operation", "checkout");
        emit(Level.INFO, "request.started", fields, null);

        if (success) {
            fields.put("outcome", "success");
            emit(Level.INFO, "request.completed", fields, null);
        } else {
            fields.put("outcome", "failure");
            fields.put("errorCode", "UPSTREAM_TIMEOUT");
            emit(Level.WARNING, "request.failed", fields,
                    new IllegalStateException("Dependency timed out"));
        }
    }

    private static void emit(
            Level level,
            String event,
            Map<String, String> fields,
            Throwable cause) {
        LogRecord record = new LogRecord(level, event);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] { Map.copyOf(fields) });
        record.setThrown(cause);
        LOG.log(record);
    }
}
```

Compile and run:

```bash
javac ContextMessageDemo.java
java ContextMessageDemo
```

**Exact stdout:**

```text
INFO event=request.started operation="checkout" requestId="req-17"
INFO event=request.completed operation="checkout" outcome="success" requestId="req-17"
INFO event=request.started operation="checkout" requestId="req-18"
WARNING event=request.failed errorCode="UPSTREAM_TIMEOUT" operation="checkout" outcome="failure" requestId="req-18" errorType=IllegalStateException
```

**Why does it produce this output?**

- `requestId` appears at both the start and end points, making it easy to pair the two events of the same request.
- `Map.copyOf(fields)` creates an unmodifiable snapshot of the context when each event is emitted; adding `outcome` later does not mutate the previously created `LogRecord`.
- `TreeMap` sorts fields by key, so column order in the output is deterministic even though the iteration order of `Map.copyOf` is unspecified.
- `quote()` escapes double quotes, backslashes, newlines, carriage returns, and tabs. The `event` name and key names are controlled by program code; if users are allowed to determine key/event names as well, additional validation is required.
- `record.setThrown(cause)` keeps the exception on the record. The formatter intentionally prints only `errorType` so stdout is reproducible; a production formatter should output stack traces when needed and follow an information-control policy.
- `StreamHandler` writes to stdout and flushes after each event for easier observation. `LOG.setUseParentHandlers(false)` prevents records from being printed again by the root `ConsoleHandler`. The demo does not call `handler.close()` because a handler attached to `System.out` could close the shared stream.

The program simulates two sequential requests; in a real service, concurrent and async requests need an appropriate context-isolation mechanism. Attaching a `Map` to `LogRecord.setParameters` **only becomes structured fields thanks to the custom Formatter in the example**; the default `SimpleFormatter` does not automatically know how to interpret these fields.

## 7. Logging Outcomes and Errors with Context

A successful operation needs a final event with `outcome`, result code, and duration when meaningful. A failed operation should have a stable `errorCode` and an appropriate `Throwable`, rather than only `ex.getMessage()`. Detailed error information should be handled at the right boundary so the same stack trace is not logged across repository, service, controller, and HTTP boundaries.

Example:

```text
INFO  event=payment.authorized requestId=R1 outcome=success durationMs=35
WARN  event=payment.retry.scheduled requestId=R2 errorCode=UPSTREAM_TIMEOUT attempt=2
ERROR event=request.failed requestId=R2 outcome=failure errorCode=RETRY_EXHAUSTED
```

These lines only illustrate message style. `R1` and `R2` are two different units of work; an expected retry event does not necessarily need to print a full stack trace on every attempt.

**Measuring duration with a monotonic clock:** capture `long start = System.nanoTime()` before the work and compute `System.nanoTime() - start` at the end; convert to milliseconds with `TimeUnit.NANOSECONDS.toMillis(...)`. Timestamps serve to order events chronologically, but the difference between two wall-clock values should not be used to measure latency because it is sensitive to clock adjustments.

Do not log `outcome=success` before the important operation or transaction has actually completed. `logger.info(...)` does not handle errors, retry, roll back, or change exit codes by itself.

## 8. Avoiding Excessive Context and Leaks

### 8.1. Choose Few but Valuable Fields

Do not log entire DTOs, headers, payloads, stack traces on every `INFO` log, or sensitive user data just to have "enough context". Prefer safe technical identifiers, operation names, result codes, durations, dependencies, and error codes. Only log personal identifiers when there is a justified need and appropriate protection policies.

A high-cardinality `requestId` is a valid field in logs/traces, but **should not be used as a label in metrics with a finite number of time series**. Logs and metrics have different designs.

### 8.2. What Happens When Context Is Lost?

| Symptom | Check |
| --- | --- |
| Controller logs have `requestId`, executor logs do not | Capture and propagate context when submitting tasks |
| New request carries the ID of an old request | Clean up/restore MDC or ThreadLocal in `finally` |
| Logs in another service have a different trace ID | Tracing propagator, headers, and span creation rules |
| Log has message, but JSON is missing fields | Encoder/layout configuration and structured-field attachment mechanism |
| `getLogger` is right, but logs do not appear | Level/filter/logger/handler/appender and collection destination |
| Same error prints stack trace multiple times | Which layer is responsible for logging errors and exception throw/wrap policy |
| Logs are erratic only under high load | Buffers, queues, backpressure, races on context map, flush timing |

### 8.3. Safety When Accepting External Data

- Validate request ID header values and externally supplied fields; limit length and allowed characters.
- Use a standard JSON encoder or escape input before turning it into text logs; do not build JSON via unchecked string concatenation.
- Do not print passwords, API keys, JWTs, cookies, bearer tokens, card details, or sensitive payloads; exception messages can also contain such data.
- Control log read permissions, retention, and data deletion according to policy.
- Have a sampling/rate-limiting strategy for high-volume logs, without dropping incident or mandatory audit events.

## 9. Adoption Checklist

1. Each event has a stable name, appropriate level, and clear message.
2. Key business milestones include `requestId`/`jobId` and `outcome` to link start-to-end.
3. Multi-service systems propagate `traceId`/`spanId` via an appropriate tracing context.
4. Fields have a consistent schema for names, data types, units, and quoting/escaping.
5. Context is kept in the proper scope, snapshotted when emitting events, and cleaned up/restored after processing.
6. The project distinguishes JUL, SLF4J, backend MDC, and formatters; do not expect one API to automatically configure another.
7. Test success, failure, two interleaved requests, executor/async, inputs with special characters, and output configuration.
8. Store only necessary information, with security policies, retention, and cost monitoring.

**Conclusion:** Contextual log messages turn scattered lines of text into traceable events. Designing `event`, correlation IDs, outcome attributes, and consistent context propagation helps investigate the right unit of work in multi-request environments while avoiding data leaks or noise.

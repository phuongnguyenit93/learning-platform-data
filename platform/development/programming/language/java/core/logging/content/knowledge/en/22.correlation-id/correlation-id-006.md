# Logging Correlation IDs in Java

## 1. Lesson Goal and Scope

After an application **creates or receives** a Correlation ID and **propagates** it over HTTP or messaging, the next step is to make this ID appear in log events. Carrying the ID only in headers without writing it to logs still makes it difficult for operators to correlate events across controllers, services, and downstream systems.

For example, a request with `correlationId=corr-42` passes through three steps:

```text
INFO  cid=corr-42 event=order.received orderId=o-17
INFO  cid=corr-42 event=inventory.reserved orderId=o-17
ERROR cid=corr-42 event=payment.failed orderId=o-17 errorCode=TIMEOUT
```

Here, **the same Correlation ID** helps readers stitch log entries into a single processing flow, while `event` and `orderId` indicate what happened to which entity.

**Scope of this lesson:** placing an ID that has already been validated at the input boundary into the logging context, configuring the output so the ID is actually written, ensuring the ID does not leak between tasks, and verifying the generated log records. How to **create, receive, and propagate** the ID was covered in earlier lessons; how to **search** for the ID in logs is covered in the next lesson.

## 2. Distinguish Three Steps: Having the ID, Attaching Context, and Emitting Logs

Storing a string in a Java variable **does not mean** the ID has been written to the logs.

| Step | Example | If skipped |
| --- | --- | --- |
| Have a trusted ID | `String correlationId = ...` | No correlation key exists, or an unvalidated value is used |
| Attach the ID to the logging context | `MDC.put("correlationId", correlationId)` | The logger does not know the current unit of work's ID |
| Configure log output | `%X{correlationId}` in Logback | The context has the ID, but the log text does not display it |

For structured logging, the third step is configuring the encoder/collector to emit a **dedicated field**, such as `correlationId`, rather than merely embedding the string inside `message`.

**MDC does not automatically send the ID over the network**, nor does it replace propagating headers or message properties. It is a mechanism for storing key–value pairs for the logging backend to use within the **current execution context**.

## 3. Java Example with SLF4J MDC and Logback

The following example assumes the project already includes `slf4j-api` and a logging provider that supports MDC, such as `logback-classic`. The key name `correlationId` is an **application convention**, not a name mandated by SLF4J.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class CorrelationLoggingExample {
    private static final Logger LOG =
            LoggerFactory.getLogger(CorrelationLoggingExample.class);
    private static final String CORRELATION_KEY = "correlationId";

    private CorrelationLoggingExample() {}

    public static void processOrder(String correlationId, String orderId) {
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException("Missing correlationId");
        }

        // Save the previous context because this method may run nested inside another context.
        String previous = MDC.get(CORRELATION_KEY);
        try {
            MDC.put(CORRELATION_KEY, correlationId);
            LOG.info("event=order.received orderId={}", orderId);

            try {
                reserveInventory(orderId);
                LOG.info("event=inventory.reserved orderId={}", orderId);
            } catch (RuntimeException error) {
                LOG.error("event=inventory.failed orderId={}", orderId, error);
                throw error;
            }
        } finally {
            // Prevent a reused thread from carrying the previous request's ID.
            if (previous == null) {
                MDC.remove(CORRELATION_KEY);
            } else {
                MDC.put(CORRELATION_KEY, previous);
            }
        }
    }

    private static void reserveInventory(String orderId) {
        // Illustrative operation only; does not call a real data store.
    }

    public static void main(String[] args) {
        processOrder("corr-42", "o-17");
    }
}
```

Key takeaways from this example:

- Call `MDC.put` **before emitting events** that need the Correlation ID attached.
- Use `{}` placeholders for business data instead of manually concatenating strings just to log the ID.
- Pass the `Throwable` object to `LOG.error` so the backend can record the stack trace; a Correlation ID **does not replace** error details.
- Restore or remove the ID in `finally`, even when an exception occurs.
- Do not generate a new ID on every `LOG.info` call; logs within the same unit of work must share the same ID according to your contract.

If you are certain this is a new scope and do not need to preserve a nested context, SLF4J also provides `MDC.putCloseable(key, value)` to automatically remove the key when exiting `try-with-resources`. However, that method **removes the key** on close rather than restoring the previous value; therefore, the example above saves `previous` to protect nested contexts.

## 4. Configuring Logback to Print Values from MDC

Example `src/main/resources/logback.xml` for Logback:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [%thread] cid=%X{correlationId} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

With this configuration, log lines can appear as:

```text
2026-11-16T10:00:00.120 INFO  [main] cid=corr-42 CorrelationLoggingExample - event=order.received orderId=o-17
2026-11-16T10:00:00.125 INFO  [main] cid=corr-42 CorrelationLoggingExample - event=inventory.reserved orderId=o-17
```

If `%X{correlationId}` is omitted, both `LOG.info` calls still execute, but the text log records **will not output the ID**, even though `MDC.get("correlationId")` holds the right value. This syntax is specific to **Logback**'s PatternLayout; other logging backends may require different configuration.

For backends that already output JSON, keep a dedicated field:

```json
{
  "timestamp": "2026-11-16T10:00:00.120Z",
  "level": "INFO",
  "service": "order-service",
  "correlationId": "corr-42",
  "event": "order.received",
  "orderId": "o-17",
  "message": "Order received"
}
```

This is an **example of the desired structure**, not the default output of the XML configuration above. Including MDC fields in JSON depends on the actual encoder/provider and log collection pipeline. Verify the schema once logs reach your centralized logging system.

## 5. What Should Be Logged Alongside the Correlation ID?

A Correlation ID helps **link** events together, but it is not enough to explain an event. A practical logging contract should define:

| Field | Purpose | Notes |
| --- | --- | --- |
| `correlationId` | Link events across a processing flow | Keep naming and format consistent across services |
| `timestamp` | Order events chronologically | Synchronize clocks and specify the timezone |
| `level` | Severity level | Not every failure is `ERROR` |
| `service` | Identify the log source | Useful when multiple JVMs write to the same destination |
| `event` or `eventCode` | Classify the event type | Prefer values with a stable contract |
| `requestId`, `messageId` | Identify a specific request or message | May differ from the Correlation ID |
| `traceId`, `spanId` | Link with distributed tracing | Not identical to the Correlation ID by default |
| `errorCode` | Searchable error code | Does not replace stack traces or root cause details |

For example, a single Correlation ID may appear across many events, while `event` must specify the concrete action. Never treat a Correlation ID as an **idempotency key**, an authentication token, or a unique user identifier.

## 6. Thread, Async, and Reactive Boundaries

MDC is typically bound to the logging provider's thread context. As a result, the following code **does not guarantee** that logs inside the asynchronous task will see the same ID:

```java
MDC.put("correlationId", "corr-42");
executor.execute(() -> LOG.info("event=async.started"));
MDC.remove("correlationId");
```

The worker may run on a different thread at a different time; reading MDC inside the lambda does not automatically propagate the context. With thread pools, the opposite bug can also occur: **the ID stays behind** on the worker thread and leaks into the next task.

One illustrative pattern for a standard executor is to **capture the value at submission time** and attach it inside the worker:

```java
String idAtSubmission = MDC.get("correlationId");
executor.execute(() -> {
    String previous = MDC.get("correlationId");
    try {
        if (idAtSubmission == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", idAtSubmission);
        }
        LOG.info("event=async.started");
        // Perform the task's work here.
    } finally {
        if (previous == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", previous);
        }
    }
});
```

This snippet illustrates **a single key**; if your application uses multiple MDC attributes, copy and restore the full context according to your contract and verify that no sensitive data leaks.

With Reactor/WebFlux, coroutines, virtual threads, task executors, or automatic instrumentation, context propagation mechanisms vary by framework and provider. Do not assume `ThreadLocal`/MDC propagates correctly across every handoff. Use the appropriate context propagation mechanism, then verify the actual logs across each boundary.

## 7. Attaching the Correlation ID at the HTTP Boundary

In web applications, the right place to attach the ID for logging is a **filter or middleware** that runs after validating/normalizing the incoming ID and before business processing:

```text
HTTP request
  → receive and validate correlationId
  → attach to logging context
  → controller / service / repository emit logs
  → build HTTP response
  → clear or restore logging context
```

Avoid having each service call `MDC.put` with a newly generated ID. Also, do not blindly trust header values supplied by clients: enforce a contract covering length, allowed characters, trusted sources, and default values. Returning the Correlation ID in a response header is an API contract decision, not an automatic side effect of MDC.

If a request is processed asynchronously after the filter finishes, you must transfer the ID to the new task using a supported mechanism; do not expect the request thread's MDC to remain intact.

## 8. Common Pitfalls and How to Verify

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| `cid=` is empty despite `MDC.put` | Pattern uses the wrong key name or provider lacks MDC support | Align the key name across Java code, config, and backend |
| ID appears in initial log but disappears in worker | Context is not propagated to the executor | Capture and attach context in the worker, clean up in scope |
| Request B carries Request A's ID | MDC is not removed/restored on the thread pool | Clean up in `finally` and test consecutive executions |
| Text logs have the ID, JSON logs do not | Encoder/collector does not export MDC fields | Check encoder mapping and storage schema |
| ID differs between service A and service B | Header/message property was not propagated | Verify the transport contract at each hop |
| `correlationId` is present but no stack trace | Error log only writes a message | Log the exception using the proper logging API overload |
| ID is found in `message` but cannot be filtered accurately | ID is not a separate field | Standardize on structured logging |

### Testing Checklist

1. With ID `corr-42`, emit two events and verify both have `correlationId=corr-42`.
2. After the scope ends, verify that MDC **no longer** holds the previous request's ID.
3. Run two consecutive tasks on **the same worker thread** and verify there is no ID cross-contamination.
4. Trigger an exception and verify the log contains the ID, event code, and exception details.
5. Inspect the **emitted log records**, not just `MDC.get` in a unit test.
6. If using JSON logging, verify `correlationId` is a dedicated field searchable by exact value.
7. Test cases where the incoming ID is missing, malformed, or exceeds the maximum length.
8. If using tracing, verify that `traceId` and `spanId` retain their own semantics.

## 9. Security and Operational Cost

- **Do not use sensitive data as a Correlation ID**: login tokens, API keys, passwords, session cookies, or unnecessary email addresses/personal identifiers.
- If the ID originates from a user, restrict its length and allowed characters to reduce the risk of **log injection**, log bloat, or breaking record syntax.
- Do not log entire request headers or bodies just to capture a single ID. Select only the fields needed for diagnostics.
- Do not use a Correlation ID as proof of authentication or authorization; users may know or supply the ID themselves.
- Evaluate cardinality and retention when adding the ID as a metric label. High-cardinality fields generally belong in logs and traces rather than metric labels.

## 10. Summary and Practice Exercise

To **log Correlation IDs properly**, three elements must align: a validated ID, a clearly scoped logging context, and a logging backend that actually outputs that field. When async execution, messaging, or multiple services are involved, propagating the context is a separate responsibility; `MDC.put` does not guarantee end-to-end continuity on its own.

**Exercise:** Build a request handler that emits `request.received`, `work.completed`, and `request.failed` on error. Verify that all logs share the same ID; run two consecutive requests on a worker pool; spawn an async task; test a case where no input ID is provided; and confirm there is no context leak after each task completes.

### Official Documentation

- [SLF4J — MDC API and `putCloseable`](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Logback — Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
- [Logback — PatternLayout](https://logback.qos.ch/manual/layouts.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)

# Correlating Logs with Traces in Java

## Objectives

After this lesson, you will be able to explain why a `trace_id` helps connect log lines across multiple services into a single execution flow, distinguish `trace_id` from `span_id`, include both identifiers in Java logs, propagate trace context over HTTP/asynchronous tasks, and verify correlation using real data.

## 1. How Do Logs and Distributed Traces Complement Each Other?

- **Logs** record a specific event: an incoming request, a failed query, an approved payment, or an exception. Logs answer "what happened?".
- **Traces** describe the path of a task across components. A trace consists of multiple **spans**; each span represents a unit of work with a start time, end time, parent–child relationships, and attributes. Traces answer "where did the work go, and where was time spent?".
- **Log correlation** means recording the identifier of the active trace/span in the log at the time the event occurs. From a log line, you can find the corresponding trace, and from a span, you can query related log lines if the storage system supports this linkage.

A `POST /orders` request might flow sequentially through `api-gateway` → `orders` → `payments`. If each service only logs "processing request", it is very hard to tell whether the three log lines belong to the same transaction when many requests run concurrently. When trace context is propagated properly, all logs carry the **same `trace_id`**; `span_id` identifies the specific unit of work that is logging.

| Field | Meaning | Rules |
| --- | --- | --- |
| `trace_id` | Identifier of the entire trace | Remains constant across spans in the same trace; per W3C Trace Context, 16 bytes represented as 32 hex characters |
| `span_id` | Identifier of the current span | 8 bytes represented as 16 hex characters; changes when transitioning to another span |
| `service.name` or `service` | Service that emitted the event | Indicates which component the log came from; does not replace the trace ID |
| `timestamp`, `level`, `message` | Time, severity level, event content | Helps read and filter logs; structured format is recommended |
| `request_id` / business ID | Application-assigned request ID or business ID | Can be useful alongside; not automatically synonymous with `trace_id` |

Do not equate a **trace** with a **single HTTP request**: a trace can encompass multiple RPCs, messages, or subtasks. Conversely, without a context propagation mechanism, a cross-service request can be split into multiple separate traces.

## 2. How Trace Context Travels Across Services

For HTTP, the W3C Trace Context specification defines the `traceparent` header with the format:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             vv-<trace-id 32 hex>---------------<parent-id 16 hex>-ff
```

In the example: `00` is the version; the 32-hex-character part is the trace ID; `00f067aa0ba902b7` is the sender's span ID (the propagated parent ID); `01` is the sampling flag enabled. A value of `01` does not guarantee that the trace will be successfully stored in the backend. An all-zero trace ID or span ID is invalid under this specification.

Typical flow:

1. **Receive request.** The context extractor (propagator) reads accepted `traceparent`/`tracestate` headers from upstream; if no valid context is present, the tracing system can create a new trace.
2. **Create/activate server span.** The `orders` service has a current span; logs within that span's scope obtain `trace_id` and `span_id` from the active context.
3. **Call the next service.** HTTP client instrumentation injects the current context into outbound headers. `payments` receives the context and creates a child span with a new span ID while continuing to use the existing trace ID.
4. **Record and collect data.** Services emit logs with trace/span fields; the tracing SDK/agent exports spans to the collector/backend. The observability system can filter logs by trace ID and correlate timestamps/spans.

Example of three events belonging to one trace:

```json
{"service":"orders","level":"INFO","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","message":"Order accepted"}
{"service":"payments","level":"INFO","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"b7ad6b7169203331","message":"Payment approved"}
{"service":"orders","level":"INFO","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","message":"Response sent"}
```

Two different span IDs are **not an error**: this very change shows that the logs were recorded in different units of work within the same trace. To achieve correlation, merely adding fields to logs is not enough; context must be propagated and activated properly at the point of execution.

## 3. Standalone Java 17 Example: Mechanism for Attaching Identifiers to Logs

The following example uses `ThreadLocal` to simulate the "current context" and prints logs in a consistent format. It intentionally uses hardcoded IDs so the output is deterministic and verifiable; **it is not a distributed tracing library**, does not perform HTTP propagation, does not create/export spans, and you should not copy this ID generation approach into production.

Save as `TraceLogDemo.java`:

```java
public class TraceLogDemo {
    record TraceIds(String traceId, String spanId) {}

    private static final ThreadLocal<TraceIds> CURRENT = new ThreadLocal<>();

    static void inSpan(TraceIds ids, Runnable work) {
        TraceIds previous = CURRENT.get();
        CURRENT.set(ids);
        try {
            work.run();
        } finally {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    static void log(String service, String event) {
        TraceIds ids = CURRENT.get();
        String traceId = ids == null ? "-" : ids.traceId();
        String spanId = ids == null ? "-" : ids.spanId();
        System.out.printf(
                "service=%s trace_id=%s span_id=%s event=%s%n",
                service, traceId, spanId, event);
    }

    public static void main(String[] args) {
        String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";

        inSpan(new TraceIds(traceId, "00f067aa0ba902b7"),
                () -> log("orders", "order-created"));
        inSpan(new TraceIds(traceId, "b7ad6b7169203331"),
                () -> log("payments", "payment-approved"));

        log("orders", "background-idle");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac TraceLogDemo.java
java TraceLogDemo
```

Exact stdout:

```text
service=orders trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 event=order-created
service=payments trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331 event=payment-approved
service=orders trace_id=- span_id=- event=background-idle
```

`inSpan` sets the context before running the work and **restores the previous context in `finally`**, even when an exception occurs. Therefore, the `background-idle` log does not accidentally carry the trace ID of a finished task. In a real application, managing spans, active context, and propagation should be delegated to a tracing SDK/instrumentation.

## 4. Integrating with OpenTelemetry, SLF4J, and Logback

A practical approach in the Java ecosystem is:

- Use **OpenTelemetry** (SDK or a compatible Java agent/instrumentation) to create spans, manage active context, extract/inject trace headers, and export tracing data.
- Use **SLF4J** as the logging API, with a logging backend such as **Logback** to format and output logs.
- Put the `trace_id` and `span_id` of the **current span** into the **MDC** (Mapped Diagnostic Context) or structured log attributes. MDC attaches metadata to logs on the currently executing thread; MDC itself is not a distributed trace context.
- Ensure the log collector/backend actually ingests and indexes these fields, preferably as separate fields, so they can be searched and linked to traces.

**Choose one population mechanism**: if the OpenTelemetry Java agent or your current logging instrumentation already populates trace/span IDs into MDC/log records automatically, use that feature and verify the emitted field names. Avoid injecting them manually as well, which can produce duplicate data or inconsistent overrides. Key names may differ across agents, logging adapters, and backends (for example `trace_id` vs. `traceId`); configure them consistently from source to query.

### Illustrating How to Populate MDC from the Active Span

This is an **integration layer** for an application that already has compatible `io.opentelemetry:opentelemetry-api`, `org.slf4j:slf4j-api`, and SLF4J provider dependencies, and has already initialized tracing elsewhere. This snippet does not create spans, does not initialize an SDK/collector, and does not contain a standalone `main` method:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import org.slf4j.MDC;

import java.util.Map;

public final class TraceMdc {
    private TraceMdc() {}

    public static void runWithCurrentSpan(Runnable action) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            SpanContext span = Span.current().getSpanContext();

            if (span.isValid()) {
                MDC.put("trace_id", span.getTraceId());
                MDC.put("span_id", span.getSpanId());
            } else {
                MDC.remove("trace_id");
                MDC.remove("span_id");
            }

            action.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
```

Where an active span exists, you can call `TraceMdc.runWithCurrentSpan(() -> logger.info("Payment approved"));`. If `Span.current()` is invalid, do not assign fake IDs to give the false impression that logs are correlated. Saving and restoring the MDC snapshot in `finally` prevents metadata from leaking into another task on a reused thread.

Example partial `logback.xml` configuration when you **explicitly** use the `trace_id` and `span_id` MDC keys:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level trace_id=%X{trace_id} span_id=%X{span_id} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

A pattern makes IDs visible during debugging, but in a multi-service environment you should consider **structured JSON logging** so that `trace_id`/`span_id` fields are stored as separate attributes, avoiding reliance on regex string parsing. For log lines outside a span, these fields may be empty or omitted depending on configuration. Do not treat every log line missing a trace ID as an error; startup events, standalone cron jobs, or health checks without an active span can fall into this category.

## 5. Asynchronous Execution: Where Correlation Is Most Easily Lost

Active OpenTelemetry context and MDC are typically tied to the current execution scope, often using thread-local mechanisms. When crossing an `ExecutorService`, thread pool, `CompletableFuture`, callback, scheduler, or message consumer, do not assume context automatically transfers to another thread.

With the OpenTelemetry API, one way to pass the active context into a `Runnable` is to capture it on the calling thread and wrap the work when submitting to an executor:

```java
// Illustration where an Executor and tracing SDK/instrumentation are already available.
io.opentelemetry.context.Context captured =
        io.opentelemetry.context.Context.current();

executor.execute(captured.wrap(() ->
        TraceMdc.runWithCurrentSpan(() ->
                logger.info("Async payment event"))));
```

Here `captured.wrap(...)` ensures the active tracing context is present when the callback runs; `TraceMdc` repopulates MDC right on the executing thread. This is an **integration snippet**, requiring appropriate `executor`, `logger`, dependencies, and an active span from the application. Framework auto-instrumentation may also handle propagation, so check before wrapping multiple layers yourself.

With message queues, you must propagate context in message headers on publish and extract it on consume; merely putting `trace_id` into logs only helps with querying and does not restore the trace's parent–child relationship. The same applies to HTTP: use the tracing propagator/instrumentation rather than manually copying the trace ID string and setting `span_id` yourself.

## 6. Verification with a Realistic Scenario

Suppose a user calls `orders`, which calls `payments` and then returns a timeout error. How to verify log/trace correlation:

1. Send a request identifiable by timestamp and endpoint. Confirm that a server span in `orders` is created and log lines within the request scope have a valid `trace_id`.
2. In the `payments` logs, search for the same `trace_id`. `span_id` may differ because it belongs to the `payments` span. Check the trace tree for the relationship between the outbound HTTP call span and the corresponding HTTP server span.
3. Query logs by `trace_id` and sort by time; cross-check the timeout event against span durations, errors, and attributes. Do not infer sequential timing solely from log ordering if clocks across machines are skewed or tasks run in parallel.
4. Test async branches, exceptions, and consecutive requests on the same thread pool: logs must not retain the trace ID of a previous request; context must be reset/restored.
5. Verify that logs and traces are sent to the right backends, fields are parsed into queryable attributes, and navigation links (if any) use the same ID naming convention.

Example of filtering by attribute in a logging system that supports this field (syntax depends on the provider):

```text
trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
```

If you find logs but no trace, **you cannot yet conclude that correlation is broken**. The trace might not have been sampled, failed to export, expired past retention, or been collected in a different backend. Conversely, having a trace without logs may be due to log level, appender configuration, filtering pipelines, or MDC not being populated at the time of logging.

## 7. Common Issues and How to Handle Them

| Symptom | Common Cause | Check or Fix |
| --- | --- | --- |
| Each service has a different `trace_id` | `traceparent` is not injected/extracted; missing instrumentation on HTTP client/server or queue | Check outbound/inbound headers and propagator configuration |
| `trace_id` is right but `span_id` is wrong/stale | MDC was populated once at request start, and the active span changed afterward | Read IDs from the currently active span at log time; use span-aware logging instrumentation |
| Thread pool logs carry the previous request's trace | MDC or context scope was not cleaned up/restored | Use `try/finally`, close span scopes, restore context, and test thread reuse |
| Logs inside callbacks have no trace ID | Tracing context/MDC was not propagated to the callback | Propagate context explicitly or enable async-aware instrumentation |
| Logs have an ID, but the UI cannot find the trace | Sampling, exporter, collector, retention, or different backend | Check sampling status, pipeline, and retention period; do not fabricate fake traces |
| Logs are plain text, making `trace_id` hard to search | Pattern omits the field or collector fails to parse it properly | Emit structured logs; standardize field names and data types |
| `request_id` is present, but no trace can be found | Business request ID was confused with the tracing identifier | Log `request_id` separately, and add `trace_id` obtained from the tracing context |

### Security and Operational Notes

- `traceparent` and baggage from external callers are **untrusted input data**, not proof of identity authentication. Establish appropriate trust/propagation policies; do not blindly accept any arbitrary header and trust it as valid trace context.
- Do not log access tokens, passwords, card data, PII, or unfiltered baggage just for the sake of easier correlation; tracing can also carry sensitive data in attributes.
- `trace_id` is a high-cardinality identifier. Consider your log backend's indexing strategy, cost, and retention; do not turn every trace ID into a metric/log label that causes cardinality explosion in unsuitable systems.
- A trace may not be sampled/exported while logs still carry a valid trace ID. Do not use "trace not visible in UI" as the sole criterion to determine that application logic failed.

## 8. Completion Criteria

A log-to-trace correlation implementation can be considered working properly when: requests spanning multiple services keep the same `trace_id`; each log takes the `span_id` of the actually active span; propagation across HTTP/queue/async is verified; context is restored after each unit of work; logs have queryable fields in the backend; and log–trace lookup results match the collected tracing data. These checks should cover success paths, error paths, and concurrent execution.
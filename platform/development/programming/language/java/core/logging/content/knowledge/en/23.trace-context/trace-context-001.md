# Trace ID in Java Core Logging

## Objectives

This lesson belongs to the **Trace context** group. After completing this lesson, you will be able to explain what a Trace ID is, distinguish it from Span ID, Request ID, and Correlation ID, understand how a Trace ID flows across multiple services and Java execution threads, include the Trace ID in logs for tracing, and avoid context loss or context leakage bugs. The focus is on **Trace ID in Java Core Logging**; distributed tracing is introduced to the extent needed for proper application.

## 1. What is a Trace ID?

A **trace** describes a processing journey—for example, an HTTP request passing through API Gateway → Order Service → Payment Service → database. Each sub-operation can be represented by a **span**. A **Trace ID** is the shared identifier for the entire trace: every span belonging to the same trace uses the **same Trace ID**, while each span has its **own Span ID**.

```text
Client
  |
  v
API Gateway        trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  |
  v
Order Service      trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  |
  +--> Payment Service     trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  |
  +--> Database operation  trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
```

Logs may be scattered across multiple services and interleaved with other requests, but you can search by `trace_id` to group related events together. A Trace ID **does not itself represent ordering, duration, or parent-child relationships**; determining those requires spans, timestamps, and parent-child links. Having a Trace ID printed in a log also does not prove that the trace was exported to a tracing backend.

### Easily Confused IDs

| Identifier | Scope and Meaning |
| --- | --- |
| **Trace ID** | Shared across all spans of a trace; can propagate across multiple services. |
| **Span ID** | Identifies a specific span; changes from one span to another. |
| **Request ID** | Defined by the application or gateway; may apply only to a single HTTP request or hop and does not have to match the Trace ID. |
| **Correlation ID** | General term for an ID used to link events/logs; may be a Trace ID or a separate ID. |
| **User ID / Order ID** | Business identifiers with different lifecycles and data protection requirements; never a replacement for Trace ID. |

An order can go through multiple payment attempts. `order_id` remains the same, while each attempt may create a new trace. Do not reuse a single Trace ID for all operations of a customer, and do not treat a Trace ID as a business key.

## 2. Trace ID and the W3C Trace Context Standard

In W3C `traceparent` version `00`, a Trace ID is represented as **16 bytes = 128 bits = 32 lowercase hexadecimal characters** (`0-9` and `a-f`). An all-zero value (`00000000000000000000000000000000`) is invalid. The ID must be random with a very low collision probability; when continuing a valid trace, the Trace ID must be preserved rather than generating a new ID in each service.

Example HTTP header:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Parts in order:

- `00`: header version.
- `4bf92f3577b34da6a3ce929d0e0e4736`: **Trace ID** for the entire journey.
- `00f067aa0ba902b7`: **parent-id** of the incoming request, i.e., the sender's Span ID (8 bytes = 16 hex characters); an all-zero ID is also invalid.
- `01`: **trace-flags**, where the least significant bit is `sampled`. `00` indicates this bit is not set; it does not mean all logs are disabled.

When Payment Service receives a valid `traceparent`, it can create a new span with a different Span ID while keeping the existing Trace ID. When calling the next service, tracing instrumentation propagates the current context and updates the parent-id accordingly. Do not blindly copy the entire header across every hop, because parent-id must reflect the sender's span on each transmission.

`tracestate` is a supplementary header carrying vendor-specific tracing state. `baggage` is a separate mechanism for propagating contextual key-value pairs; do not put business data or secrets into a Trace ID.

**Important validation:** Incoming headers from external sources may be malformed or spoofed. Validate the version, delimiters, length, hex characters, all-zero IDs, and flags according to the specification. When the context is invalid, the propagator must not continue that context; the application typically starts a new trace according to policy. Use the OpenTelemetry/tracing library propagator instead of a custom `split("-")` parser in production.

## 3. How Does a Trace ID Flow Through the System?

1. **Entry point:** An HTTP request or message arrives. Instrumentation *extracts* the context from headers/metadata. If valid and permitted by policy, that Trace ID is used; otherwise, a new trace is started with a new ID.
2. **Inside the application:** Controllers, services, repositories, HTTP clients, and child spans belonging to the same trace share the Trace ID. The logger reads the current context to add the `trace_id` field.
3. **Leaving the process:** The HTTP client or message producer *injects* the context into the appropriate headers/metadata. The receiving service/consumer *extracts* the context before processing.
4. **Across asynchronous threads:** `ExecutorService`, `CompletableFuture`, callbacks, or schedulers require wrappers/instrumentation to propagate context. Standard `ThreadLocal` and MDC do not automatically copy to worker threads.
5. **Completion:** Close the scope and restore the previous context; clear temporary values in MDC/ThreadLocal to prevent thread pools from reusing an old request's Trace ID.

```text
HTTP inbound
  -> extract traceparent / create new trace
  -> set trace context in current scope
  -> log with trace_id during processing
  -> HTTP outbound / messaging: inject context
  -> close scope and restore previous context
```

Do not force every event related to an Order ID into a single trace. Asynchronous messages, batches, or fan-out/fan-in flows may require *span links* or new traces depending on semantics; how propagation works over queues also depends on producer/consumer instrumentation.

## 4. Adding Trace ID to Logs for Tracing

Example of two events in one trace:

```text
level=INFO service=order-service trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 event=order-created
level=INFO service=payment-service trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331 event=payment-authorized
```

The shared Trace ID helps locate all logs for the journey; the Span ID pinpoints the specific operation. Use consistent field conventions (`trace_id`, `span_id`, service name), keep IDs as **strings**, and configure the log collector not to drop those fields. JSON logs are generally more convenient for querying and correlation than concatenating IDs directly into the message text.

Example query for an exact ID (exact syntax depends on the backend):

```text
trace_id:"4bf92f3577b34da6a3ce929d0e0e4736"
```

Debugging workflow: take the Trace ID from an error log or response, search logs across all services by that ID, sort chronologically, and compare Span IDs / the span tree to understand the execution flow. Missing logs do not necessarily mean an operation did not run: log level, sampling, log collector, retention, or context propagation can all affect visibility.

## 5. Java 17: Standalone Example with ThreadLocal and ExecutorService

The following example uses **only the JDK** to illustrate *capture → attach context on worker → clean up context*. It is a logging correlation simulation, **not** a full distributed tracer/OpenTelemetry setup. The Trace ID is hardcoded so the output is deterministic; in a real system it must come from the trace context or be generated at a trace boundary.

Create `TraceIdLogDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TraceIdLogDemo {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    private static void log(String event) {
        System.out.println("trace_id=" + TRACE_ID.get() + " event=" + event);
    }

    public static void main(String[] args) throws Exception {
        String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";
        ExecutorService pool = Executors.newSingleThreadExecutor();

        TRACE_ID.set(traceId);
        try {
            log("request-start");

            String capturedTraceId = TRACE_ID.get();
            Future<?> task = pool.submit(() -> {
                TRACE_ID.set(capturedTraceId);
                try {
                    log("async-work");
                } finally {
                    TRACE_ID.remove();
                }
            });

            task.get();
            log("request-end");
        } finally {
            TRACE_ID.remove();
            pool.shutdown();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac TraceIdLogDemo.java
java TraceIdLogDemo
```

Expected output on **stdout**:

```text
trace_id=4bf92f3577b34da6a3ce929d0e0e4736 event=request-start
trace_id=4bf92f3577b34da6a3ce929d0e0e4736 event=async-work
trace_id=4bf92f3577b34da6a3ce929d0e0e4736 event=request-end
```

Explanation:

- `TRACE_ID` is a `ThreadLocal`: its value on the main thread **does not automatically transfer** to the `pool` thread.
- `capturedTraceId` is captured before `submit` and then set on the worker; therefore `async-work` has the same ID. `task.get()` ensures `request-end` appears after the worker log.
- `finally` cleans up the context on both threads even if an exception is thrown. Forgetting cleanup in a thread pool can cause subsequent request logs to carry the previous request's ID.
- This example runs a single independent worker task. A shared production wrapper needs to **restore the previous context value**, especially with nested scopes. Preferably, use the tracing library's context-aware executor/instrumentation.

**Self-check exercise:** remove the `TRACE_ID.set(capturedTraceId);` line inside the lambda. The `async-work` log will print `trace_id=null`. This reproduces the context-loss bug when switching threads.

## 6. Generating a Trace ID When Self-Instrumenting

Normally the **tracer**—not the logger—should be responsible for generating Trace IDs. Do not generate a new Trace ID per method, per span, or per log line. If you need to understand how to generate a properly formatted string in Java 17, you can use `SecureRandom` and `HexFormat`.

Create `GenerateTraceId.java`:

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class GenerateTraceId {
    private static final SecureRandom RANDOM = new SecureRandom();

    private static String newTraceId() {
        byte[] bytes = new byte[16];
        boolean allZero;

        do {
            RANDOM.nextBytes(bytes);
            allZero = true;
            for (byte b : bytes) {
                if (b != 0) {
                    allZero = false;
                    break;
                }
            }
        } while (allZero);

        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) {
        String id = newTraceId();
        System.out.println(id.length());
        System.out.println(id.matches("[0-9a-f]{32}"));
        System.out.println(!id.equals("0".repeat(32)));
    }
}
```

```bash
javac GenerateTraceId.java
java GenerateTraceId
```

Output:

```text
32
true
true
```

The actual ID changes randomly on each run, but the three checks above always hold true: 16 bytes produce 32 lowercase hex characters, and the loop rejects an all-zero ID. This sample code does **not** create spans, propagate context, perform sampling, or export traces; it does not replace a production tracer/propagator.

Avoid using plain timestamps, per-process counters, user IDs, emails, IP addresses, or order IDs as Trace IDs. Those approaches can collide, leak information, or create incorrect trace relationships.

## 7. Implementation with OpenTelemetry, SLF4J, and MDC

In real Java applications, you can use the OpenTelemetry Java agent or appropriate instrumentation to create spans, manage context, and automatically inject/extract across supported protocols. Once a scope is instrumented, the API allows reading the current context:

```java
// Snippet inside a method with the OpenTelemetry API on the classpath:
io.opentelemetry.api.trace.SpanContext sc =
        io.opentelemetry.api.trace.Span.current().getSpanContext();

if (sc.isValid()) {
    String traceId = sc.getTraceId();
    String spanId = sc.getSpanId();
    // Add to structured logs if the logging stack does not do so automatically.
}
```

The snippet above is **not a standalone Java program**. If the context is invalid, do not substitute a fake all-zero ID or generate a new ID for each log entry.

**MDC (Mapped Diagnostic Context)** in SLF4J/Logback, or the equivalent mechanism in Log4j, attaches context values to log events. Example of a **partial** Logback encoder pattern:

```xml
<pattern>%d{ISO8601} %-5level trace_id=%X{trace_id} span_id=%X{span_id} %logger - %msg%n</pattern>
```

This is not a complete `logback.xml` file. The pattern only reads MDC keys: an agent/bridge or the application must populate `trace_id`/`span_id` into the MDC or log record for them to appear. The OpenTelemetry Java agent provides MDC correlation for supported logging libraries, though how it is enabled and configured depends on the agent, version, and logging stack. For structured logging, use the corresponding JSON fields.

If you populate values manually with `MDC.put(...)`, always use `try/finally` to remove or restore the previous value and prevent context leakage. If automatic injection is already active, avoid inserting duplicates or overwriting values. Never store a request's Trace ID in a shared `static` variable. MDC/ThreadLocal is typically thread-bound: when using `CompletableFuture`, schedulers, or thread pools, use a context-aware executor, scope/wrapper, or appropriate instrumentation.

For a system to work end-to-end, verify **three layers**: (1) context is created/extracted/injected properly, (2) the logger adds the fields from the current context, and (3) the pipeline preserves the fields during log shipping and indexing. Having an ID in service A but losing it in service B is usually a bug in one of these three layers.

## 8. Sampling, Security, and Operations

- **Sampling is separate from logging.** A trace whose `sampled` flag is unset can still have a Trace ID in its context and logs. Conversely, a log containing an ID does not guarantee the span was exported; there may be no trace to open in the backend.
- **Trace ID is not a credential.** Do not use it for authentication, authorization, or as a secret. Do not embed personal data, tokens, session secrets, or user information into the ID. For `baggage`, control what data is propagated across service boundaries.
- **Never implicitly trust external headers.** Validate `traceparent`, enforce header size limits, and apply trust boundary policies. Do not rely on a client-supplied Trace ID to make resource access decisions.
- **Consistent formatting.** Keep the ID as a full 32-character lowercase hex string per W3C; do not parse it as a number because leading `0`s can be lost. Standardize field names and types across logs and collectors.
- **Metrics cardinality.** Each request typically has a unique ID; adding `trace_id` as a standard metrics label causes extremely high cardinality. It is better stored in logs and linked to traces.
- **Different retention and sampling.** Logs may still exist after a trace has expired or was not stored. The ID remains useful for locating related logs.

## 9. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| A has Trace ID but B does not | HTTP client does not inject or B does not extract | Check instrumentation on both sides and inspect `traceparent` in a test environment. |
| Trace ID changes at every service | Each service starts a new root trace | Use a consistent propagator and continue valid contexts. |
| `trace_id=null` in `CompletableFuture` | Thread-bound context is not propagated | Use a context-aware executor/wrapper or async instrumentation. |
| Next request logs carry previous request's ID | Forgot to clear MDC/ThreadLocal in pool | Close scope and restore/clear in `finally`. |
| Every log has a different ID | Generating IDs inside the logger | Read Trace ID from active context; generate new IDs only at trace boundaries. |
| Logs have ID but no trace appears | Sampling, exporter, collector, or retention | Check sampler, exporter, backend, and retention settings. |
| Searching logs by ID returns nothing | Collector drops field or parser/index misconfigured | Inspect raw logs, `trace_id` schema, and query syntax. |
| Header is rejected | Invalid version, length, hex, or all-zero ID | Let the propagator handle validation per W3C spec. |

### Verification Exercises

1. Send an HTTP request across two services. Search for `trace_id` in both services' logs: the **Trace ID is identical**, while the Span ID may differ.
2. Run `ExecutorService` and compare logs before/after context propagation; verify the worker log has the right ID.
3. Send two independent requests sequentially through the same thread pool; verify the old request's ID does not leak into the new request.
4. Test a `traceparent` with an all-zero Trace ID in a test environment; verify the propagator handles the invalid context.
5. Filter by Trace ID and open the tracing backend. If the trace is missing, check sampling/export/retention before concluding the ID is wrong.

**Completion criteria:** You understand why Trace ID stays stable within a trace while Span ID changes per span; you know how to read the ID from context, propagate it across boundaries, log it as a structured field, clean up scopes, and verify across multiple services.

## References

- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent`, trace-id, parent-id, trace-flags, and validation.
- [OpenTelemetry — Java instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/) — context, spans, and propagation.
- [OpenTelemetry Java instrumentation — Logger MDC](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md) — correlating traces/spans with logs via MDC.

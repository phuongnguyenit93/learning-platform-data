# Span ID in Trace Context (Java Core Logging)

## 1. What is a Span ID used for?

In a Java application, an HTTP request can pass through a controller, a service, database queries, and calls to other services. If you only look at individual log lines in isolation, it is difficult to tell which operations belong to the same request. **Distributed tracing** models this processing using **traces** and **spans**:

- **Trace** represents the entire chain of related work; spans within the same trace share a single **Trace ID**.
- **Span** represents a single unit of work with a start and end, such as handling an HTTP request or executing an SQL query.
- **Span ID** identifies a specific span within a trace. When entering a child span, the Span ID changes, while the Trace ID is typically preserved.
- **Parent Span ID** (if present) is the Span ID of the parent span. Through this parent–child relationship, the tracing system builds a call tree.

For example, a request that creates three spans:

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
└─ Gateway:       spanId=00f067aa0ba902b7   (root in this example)
   └─ OrderService: spanId=a3ce929d0e0e4736, parent=00f067aa0ba902b7
      └─ DB query:   spanId=b9c7c989f97918e1, parent=a3ce929d0e0e4736
~~~

The three operations belong to the same trace but have three different Span IDs. A log line associated with the `DB query` span can carry `traceId=4bf...` and `spanId=b9c...`, helping you pinpoint the exact processing step rather than only knowing the overall request.

## 2. Distinguishing Trace ID, Span ID, and Parent Span ID

| Attribute | Meaning | Scope of use |
| --- | --- | --- |
| Trace ID | Identifies the entire trace | Preserved as the trace traverses related spans/services |
| Span ID | Identifies the **current span** | A new value for each new span |
| Parent Span ID | Points to the direct parent span | Absent on the root span; helps build the parent–child relationship |
| Request ID / Correlation ID | Correlation identifier defined by the application or infrastructure | Can be useful for logging, but does not automatically replace Trace ID or Span ID |

In the context of W3C Trace Context, a **Trace ID** is 16 bytes (32 hex characters), while a **Span ID** is 8 bytes (16 hex characters). Hex values are typically represented in lowercase; an all-zero identifier is invalid. A Span ID must avoid collisions within a trace; when using real tracing, let the SDK generate appropriate IDs instead of hardcoding them, incrementing them sequentially, or deriving them from user data.

A single span can emit multiple log lines with the **same Span ID**: the ID only changes when switching to another span's context, not on every log call. A Span ID is also not a Java thread ID: multiple spans can run sequentially on one thread, and a single span may need its context carried across threads.

## 3. How is a Span ID propagated between services?

W3C Trace Context defines the `traceparent` HTTP header in the format:

~~~text
traceparent: 00-<trace-id>-<parent-id>-<trace-flags>
~~~

Example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- `00`: header format version.
- `4bf92f3577b34da6a3ce929d0e0e4736`: Trace ID.
- `00f067aa0ba902b7`: **the sender's Span ID**; this field is called `parent-id` because the receiver will use it as the ID of the parent span.
- `01`: trace flags, with the sampling bit enabled.

When OrderService receives the header above, a tracing SDK can create a **new server span** with Span ID `a3ce929d0e0e4736`, preserving the Trace ID and linking its parent to `00f067aa0ba902b7`. If OrderService calls a downstream service within the context of that server span, the outgoing `traceparent` header contains **OrderService's current Span ID**, not the Gateway's ID:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-a3ce929d0e0e4736-01
~~~

Do not interpret the `parent-id` field in the header as "the Span ID of the current span on the receiving side": the receiver must create or select its own span according to how its instrumentation operates. The `tracestate` header can supplement vendor-specific tracing context, but does not replace `traceparent`. The sampling flag communicates the sampling decision; whether logs appear or spans are exported still depends on logging/tracing configuration.

## 4. Standalone Java 17 example: logging by current span

The following example simulates a request from Gateway to OrderService, and then OrderService opens a child span for a DB query. It uses `ThreadLocal` to demonstrate context within **the same thread**. The hardcoded IDs are only for easily verifiable output; this is **not** a production tracer or Span ID generator.

Create the file `SpanIdDemo.java`:

~~~java
public class SpanIdDemo {
    private record SpanContext(
            String traceId, String spanId, String parentSpanId) {
    }

    private static final ThreadLocal<SpanContext> CURRENT = new ThreadLocal<>();

    private static void log(String message) {
        SpanContext current = CURRENT.get();
        System.out.printf(
                "traceId=%s spanId=%s parentSpanId=%s | %s%n",
                current.traceId(),
                current.spanId(),
                current.parentSpanId() == null ? "-" : current.parentSpanId(),
                message);
    }

    public static void main(String[] args) {
        // OrderService's span: same trace, parent is Gateway.
        SpanContext server = new SpanContext(
                "4bf92f3577b34da6a3ce929d0e0e4736",
                "a3ce929d0e0e4736",
                "00f067aa0ba902b7");

        CURRENT.set(server);
        try {
            log("HTTP GET /orders");

            // Child span uses the same traceId but has a new spanId and parent.
            SpanContext dbQuery = new SpanContext(
                    server.traceId(),
                    "b9c7c989f97918e1",
                    server.spanId());

            CURRENT.set(dbQuery);
            try {
                log("SELECT orders");
            } finally {
                CURRENT.set(server); // Restore the parent span's context.
            }

            log("HTTP 200");
        } finally {
            CURRENT.remove(); // Avoid leaking context to subsequent tasks.
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac SpanIdDemo.java
java SpanIdDemo
~~~

Exact stdout:

~~~text
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=a3ce929d0e0e4736 parentSpanId=00f067aa0ba902b7 | HTTP GET /orders
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=b9c7c989f97918e1 parentSpanId=a3ce929d0e0e4736 | SELECT orders
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=a3ce929d0e0e4736 parentSpanId=00f067aa0ba902b7 | HTTP 200
~~~

**What to observe:** the DB query log line has its own Span ID and points back to OrderService's span. The HTTP 200 line returns to OrderService's Span ID after restoring the context. This example only manages context for logging; to get trace graphs, span durations, events, and backend export, you need real instrumentation or a tracing SDK.

## 5. Retrieving Span ID in a real Java application

In an application integrated with the **OpenTelemetry API/SDK** or Java agent that has a valid active span, you can read the context as follows. This is an **integration snippet**, not a standalone Java program like the example in section 4; the project must have the appropriate OpenTelemetry dependencies and configuration.

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

SpanContext context = Span.current().getSpanContext();
if (context.isValid()) {
    String traceId = context.getTraceId();
    String spanId = context.getSpanId();
    // Put both IDs into structured logs or the active logging context.
}
~~~

`Span.current()` retrieves the span from the **currently active context**, so calling it outside a valid span can return an invalid context. Check `isValid()` before using the IDs. The tracing SDK/instrumentation is typically responsible for creating spans, linking parent–child relationships, and ending spans; logs simply read the information attached to the execution.

With **SLF4J + Logback**, you can put `trace_id` and `span_id` into the MDC (Mapped Diagnostic Context) so that a log pattern or JSON encoder outputs them alongside the message. For example, pattern tokens like `%X{trace_id}` and `%X{span_id}` **only work when an integration has actually written those two keys into the MDC**; the key names depend on the library and configuration. Do not assume that merely adding the pattern will make OpenTelemetry work automatically.

When using thread pools, `CompletableFuture`, reactive pipelines, or coroutines/fibers, context may not automatically follow execution across threads. You need the framework's or instrumentation's propagation mechanism; do not implicitly pass `ThreadLocal` across threads, and always restore/clear the logging context at task boundaries to avoid attaching a previous request's Span ID by mistake.

## 6. Common pitfalls when reading logs by Span ID

1. **Confusing Trace ID with Span ID.** A trace has many spans; filter by Trace ID for the entire journey, then use Span ID to narrow down to a single operation.
2. **Generating a Span ID per log line.** Logs within the same span must keep the current Span ID; generate a new ID when creating a new span, not when printing a log.
3. **Assigning the same Span ID to multiple different spans.** This breaks the tracing hierarchy. Use the SDK's ID generator and ensure each new span receives its own ID.
4. **Failing to propagate context when calling other services.** The Trace ID changes or the parent link breaks, leaving the trace tree disconnected. Check `traceparent` injection/extraction over HTTP/messaging.
5. **Losing or leaking context when switching threads.** Logs miss IDs or record IDs from another request. Verify context propagation and ensure `finally` blocks/scopes close properly.
6. **Treating a Span ID in logs as proof that the trace exists in the backend.** Logs may only contain correlation IDs while the span was never created/exported, was dropped by sampling, or failed in the exporter. Check the telemetry pipeline separately.
7. **Trusting an invalid `traceparent`.** When handling the protocol manually, enforce length, hex format, and non-zero ID rules; it is best to let standard instrumentation handle it. Never place sensitive data, user IDs, or tokens into IDs.

## 7. How to self-check when investigating a request

Suppose three log lines share the same Trace ID; the first two have `spanId=A`, and the third has `spanId=B` and `parentSpanId=A`. The logical conclusion is that the third log belongs to **a child span of A**, not an independent trace. If the Trace IDs differ, they do not belong to the same trace according to the observed identifiers, even if the request URL or timestamp is similar.

When logs have a Span ID but no span appears in the tracing UI, check in order: whether the span was created and ended, whether the exporter sent it successfully, whether sampling kept that trace, and whether the log being read captured the right active context. This helps distinguish a **logging correlation** issue from a **trace collection** issue.

**Remember:** Trace ID answers "which overall journey?", Span ID answers "which operation are we in?", and Parent Span ID answers "which span called this operation?". Together, these three concepts let you read logs according to the true structure of a distributed trace.
# Distinguishing Between Logs and Traces in Java

## 1. Lesson Objectives

When operating a Java application, **logs** tell you what events occurred, whereas **traces (tracing)** reconstruct the execution path and processing time of an operation—especially when it spans multiple methods, threads, or services. These two data sources complement each other in system observability and diagnostics.

After this lesson, you should be able to distinguish between:

- **Log record**: a record of an event at a specific point in time or execution.
- **Distributed trace**: a sequence of operations associated with the same request or business workflow; each operation is typically represented by a **span**.
- **The TRACE log level** in some logging frameworks: merely a verbosity level for log records; it **does not automatically create a distributed trace**.
- **Exception stack trace**: the list of method calls leading to an error location, which is **different from a distributed trace**.

This lesson uses Java 17 and `java.util.logging` (JUL) to demonstrate logging, then simulates spans to clarify trace data. The custom span implementation in the example is a **simulation for learning purposes**, not an actual distributed tracing system.

## 2. Log: A Recorded Event

Logging records what the application wants to report: processing started, login succeeded, query failed, missing configuration, or an exception. A log entry typically includes:

- **Timestamp**: when the record was generated.
- **Severity/level**: for example, `INFO`, `WARNING`, `SEVERE` in JUL.
- **Logger/source**: the class or component emitting the log.
- **Message**: what happened, optionally accompanied by contextual key-value pairs.
- **Exception**: the error type, message, and stack trace when needed for diagnostics.
- **Correlation fields**: `trace_id`, `span_id`, `request_id` if attached by the application.

Example of a structured log (illustrative data):

```text
2026-11-09T10:15:31.240Z INFO  OrderService trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 message="Order accepted" order_id=815
2026-11-09T10:15:31.275Z ERROR PaymentClient trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331 message="Payment request failed" error="timeout"
```

These two lines are **two separate events**. They show that the order was accepted and a payment call failed, but by themselves the lines do not prove the entire sequence of operations in between, which part called which, or how long each part took. The `trace_id` and `span_id` fields allow them to be correlated with a trace when tracing is enabled in the system.

Logs can be emitted at any point you want to observe, with frequency and detail depending on configuration. The console and files are **log destinations**; changing the destination does not turn a log into a trace.

## 3. Trace: The Processing Journey of a Request

In the context of observability, a **trace** represents the path of an operation from start to finish. A trace consists of multiple **spans** with parent-child or linked relationships, for example:

```text
Trace: checkout processing (shared trace_id)
└── HTTP POST /checkout                 185 ms  [root span]
    ├── validateCart                     12 ms
    ├── reserveInventory                 90 ms
    │   └── SQL UPDATE inventory         54 ms
    └── persistOrder                     65 ms
```

The durations and operation names above are illustrative only. In real systems, spans can run **in parallel**, so you cannot simply sum all child span durations to derive the parent span duration.

A span typically carries:

| Attribute | Meaning |
| --- | --- |
| `trace_id` | Shared identifier linking spans belonging to the same trace |
| `span_id` | Unique identifier of a single span |
| `parent_span_id` | ID of the parent span if any; the root span has no parent |
| Operation name | For example, `HTTP POST /checkout` or `reserveInventory` |
| Start time and duration | Indicates when the operation started and how long it lasted |
| Status, attributes, events | Outcome, technical/business attributes, and events within the span |

With distributed tracing, the trace context must travel with the request across services. For instance, Gateway, Order Service, and Inventory Service may each create different spans while keeping the same `trace_id`. The tracing system collects these spans to display a timeline or dependency graph.

A trace shows the **relationships and latency** of operations. It is not meant to store every detailed event like logs do. Spans can contain events, but span events do not replace all the log messages, stack traces, or business details that operations teams need.

## 4. Direct Comparison of Logs and Traces

| Perspective | Log | Trace |
| --- | --- | --- |
| Primary question | **What happened?** | **Where did the request go, in what relationship, and how long did it take?** |
| Data unit | A log record / event | A span; multiple spans form a trace |
| Timeline | Event timestamp; may include other data | Start time, duration, and relationships between spans |
| Causality | Not built-in; requires context/IDs to correlate | Described via parent/child relationships or span links |
| Error information | Message, exception, stack trace, context | Error span, position in the processing flow, duration; may include an exception event |
| Searching | Typically by level, keyword, class, time, request ID | Typically by trace ID, operation name, service, latency, status |
| Volume | Depends on log level and event emission frequency | Depends on number of spans/attributes/events and sampling policy |
| Common Java tools | JUL, SLF4J + Logback/Log4j2 | OpenTelemetry API/SDK, compatible agents and collectors/backends |

**There is no strict one-to-one relationship**: a span can have many logs, no logs, or a log can appear outside any trace (for example, during application startup). Likewise, a trace may be stored while its corresponding logs are filtered out or past their retention period.

### Practical Example: Payment Failure

Suppose a user reports that an order processed slowly and then failed:

- **Logs** from `PaymentClient` can reveal the timeout, endpoint, retry attempts, and specific exception.
- **Traces** can show the request flowing from Gateway → Order Service → Payment Service, with the span calling Payment Service taking most of the time.
- **Combining both**: open the trace to identify the slow span, grab the `trace_id`/`span_id` to find related logs, and then read the exception and retry details to determine the root cause.

If you look only at logs, many concurrent requests can interleave lines and make them hard to follow; if you look only at traces, you may see which span is slow but lack the business reason or stack trace needed to fix the bug.

## 5. Three Confusing Uses of the Word "Trace"

### 5.1. TRACE as a Log Level

In SLF4J/Logback and several other frameworks, `TRACE` is typically a log level more detailed than `DEBUG`. Example with SLF4J (this is an **illustrative snippet requiring the SLF4J dependency**, not a standalone Java program):

```java
logger.trace("Entering calculateTotal, itemCount={}", itemCount);
logger.debug("Discount rule selected: {}", ruleName);
logger.info("Order calculation completed");
```

Calling `logger.trace(...)` still produces a **log record**. Simply enabling the TRACE level **does not automatically** create a `trace_id`, spans, a timeline, or distributed tracing.

JUL's `java.util.logging.Level` **does not have a `TRACE` constant**. JUL uses `FINE`, `FINER`, and `FINEST` for detailed logging; do not mechanically rename them or treat these levels as exact equivalents across every framework's configuration.

### 5.2. Stack Trace as the Call Chain in an Exception

An `Exception` has a stack trace showing the methods on the call stack at the point where the throwable was created or recorded. For example:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    ex.printStackTrace();
}
```

By default, `printStackTrace()` prints the exception and call stack to `System.err`. A stack trace is useful for pinpointing the error location in Java code, but it **does not represent all operations across multiple services** and usually carries no per-step duration. In applications using a logging framework, you should log exceptions through the logger and use a formatter that supports stack traces so you get the log level and correlation info.

### 5.3. Distributed Trace as a Chain of Spans

A distributed trace uses `trace_id` to link spans of the same request and `span_id`/`parent_span_id` to reconstruct execution relationships. This is what "tracing" means in modern observability systems. A log level named TRACE, a stack trace, and a distributed trace share the word "trace" but serve different purposes.

## 6. Runnable Java 17 Example: Logging Events and Simulating Two Spans

The example below uses only the JDK's built-in libraries. The program does three things: emits business logs via JUL; creates two simulated span records for `checkout` and `reserveStock`; and prints the span data to show the parent-child relationship.

Create the file `LogTraceDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogTraceDemo {
    private static final Logger LOG =
            Logger.getLogger(LogTraceDemo.class.getName());
    private static final List<Span> SPANS = new ArrayList<>();

    record Span(String traceId, String spanId, String parentSpanId,
                String name, long startNanos, long durationNanos) {}

    private static String newId(int length) {
        return UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, length);
    }

    private static void log(String traceId, String spanId, String message) {
        LOG.info("trace_id=" + traceId
                + " span_id=" + spanId
                + " message=" + message);
    }

    private static void reserveStock(String traceId, String parentSpanId) {
        String spanId = newId(16);
        long started = System.nanoTime();
        try {
            log(traceId, spanId, "Checking stock");
            int available = 2;
            if (available == 0) {
                throw new IllegalStateException("Out of stock");
            }
            log(traceId, spanId, "Stock reserved");
        } finally {
            SPANS.add(new Span(
                    traceId, spanId, parentSpanId, "reserveStock",
                    started, System.nanoTime() - started));
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            String traceId = newId(32);
            String checkoutSpanId = newId(16);
            long started = System.nanoTime();

            try {
                log(traceId, checkoutSpanId, "Checkout started");
                reserveStock(traceId, checkoutSpanId);
                log(traceId, checkoutSpanId, "Checkout completed");
            } finally {
                SPANS.add(new Span(
                        traceId, checkoutSpanId, null, "checkout",
                        started, System.nanoTime() - started));
            }

            System.out.println("TRACE (local demo):");
            SPANS.stream()
                    .sorted(Comparator.comparingLong(Span::startNanos))
                    .forEach(span -> System.out.printf(
                            Locale.ROOT,
                            "name=%s trace_id=%s span_id=%s parent=%s "
                                    + "duration_ms=%.3f%n",
                            span.name(),
                            span.traceId(),
                            span.spanId(),
                            span.parentSpanId() == null
                                    ? "none" : span.parentSpanId(),
                            span.durationNanos() / 1_000_000.0));
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Run with Java 17 or higher from the directory containing the file:

```bash
javac LogTraceDemo.java
java LogTraceDemo
```

**What you will observe:**

1. JUL emits **four INFO lines** with messages `Checkout started`, `Checking stock`, `Stock reserved`, and `Checkout completed`, respectively. The two lines in `checkout` use `checkoutSpanId`; the two lines in `reserveStock` use its own span ID.
2. The program prints **two span records**: `checkout` has `parent=none`, while `reserveStock` has `parent` equal to `checkout`'s ID. Both spans carry the **same `trace_id`**.
3. `duration_ms` is measured by `System.nanoTime()`, so it varies across runs; the IDs generated by `UUID` also differ. Therefore, **there is no fixed numeric/ID output** to match verbatim.
4. JUL's `ConsoleHandler` writes logs to `System.err`, whereas the span output uses `System.out`. A terminal usually displays both, but if you redirect or merge the two streams, their display order may vary.

**Important limitations of this example:** the `SPANS` list is merely in-memory data within a **single process**. Creating `Span` records and printing them to the console **does not automatically send traces to Jaeger, Zipkin, or a collector**. Real-world tracing requires instrumentation, context propagation, an exporter/collector, and a backend. In this example, `System.nanoTime()` is suitable for measuring **elapsed time within a single JVM**, not an absolute timestamp for merging data across different machines. Loggers/tracers in multithreaded systems also need mechanisms to propagate context properly across threads and tasks.

## 7. Correlating Logs with Traces via Context

To combine logging and tracing, correlation information generally needs to be present in both types of data:

```text
Request A
  trace_id = T
  span checkout = S1
      log: "Checkout started"  trace_id=T span_id=S1
      span reserveStock = S2, parent=S1
          log: "Stock reserved" trace_id=T span_id=S2
      log: "Checkout completed" trace_id=T span_id=S1
```

The symbols `T`, `S1`, and `S2` above are illustrative notation, not the ID format sent over the network. Each span has its own ID and shares the trace ID. Logs carrying these IDs can be searched in the log storage system to navigate from a failing span to the detailed messages.

For HTTP between services, the **W3C Trace Context** standard typically uses the `traceparent` header to carry trace information. Example of valid syntax:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

According to version `00` syntax, the string consists of the version, a 32-hex-character trace ID, a 16-hex-character parent ID, and two-hex-character trace flags. The ID in the header is the **caller's current span ID**, not a requirement for every service to share one span ID; the receiving service continues the trace ID and creates a new span ID for its own operation. The sampling flag relates to the decision to collect the trace; it does not mean every log for the request is saved.

In real applications, you should let the instrumentation/tracing SDK propagate context according to the framework and protocol rather than manually concatenating header strings. With thread pools, `CompletableFuture`, or asynchronous calls, context must be propagated across task boundaries; using a single global variable for `trace_id` like in a single-request example would be **unsafe** when multiple requests run concurrently. Request-scoped context and propagation utilities help prevent mixing data between users.

An application-specific `request_id` can be useful for searching logs; it does **not necessarily** equal the tracing `trace_id`. If you use both, clearly define their scope and mapping.

## 8. When to Use Logs, Traces, or Both?

| Need | Prefer | Why |
| --- | --- | --- |
| Knowing why input data was rejected | Logs with validation reasons | Business details usually live in event messages |
| Finding the bottleneck across multiple services | Traces with span durations | Shows the call chain and per-step latency |
| Diagnosing an exception in a Java class | Exception logs and stack traces | Provides error type, method, and code location |
| A request occasionally times out and is hard to reproduce | Logs with trace IDs combined with traces | Lets you follow the path and read messages in the relevant span |
| Checking startup, shutdown, or config reload sequences | Logs | Typically lifecycle events not tied to an HTTP trace |
| Understanding parent-child call relationships between services | Distributed traces | Provides context and span hierarchy |
| Aggregating error rates or system-wide latency | Metrics, optionally combined with logs and traces | Avoids scanning all logs/traces for every aggregation |

**Example investigation flow:**

Suppose an API returns HTTP 500. First, search for error logs by timestamp, service, request ID, or trace ID. If a corresponding trace exists, open it to see which step failed or took the most time. From the failing span, use `trace_id` and `span_id` to query logs for the exception details. Check the source code, configuration, and actual backend before concluding the root cause. A span marked with an error indicates **where the error was detected in the observed flow**—it does not by itself prove that the root cause originated in that span.

For small systems or batch programs that do not call external services, logging alone may suffice for many problems. Tracing delivers the clearest value when you need to observe **relationships between operations**, distribution across services, or complex latency diagnostics.

## 9. Cost, Sampling, and Privacy

**Logging:**
- Levels (`INFO`, `WARNING`, `FINE`, etc.) help control verbosity and volume.
- You need log rotation, retention, file permissions, or storage policies on the logging platform.
- Logging too much on hot paths can increase I/O, raise costs, and dilute important signals.

**Tracing:**
- Each request can generate many spans; the number of spans and attributes determines the volume of collected data.
- **Sampling** records or exports only a fraction of traces to control costs; depending on the setup, a trace for a specific request might not exist in the backend even though the application ran and emitted logs.
- Sampling must be balanced with the need to catch rare errors: if the sample rate is too low, important traces may not be collected. Concluding "no trace" **does not mean** "no request."

**Both:** never log tokens, passwords, API keys, card numbers, or sensitive content. Be careful with URL query strings, request/response bodies, user IDs, and high-cardinality span attributes. Set volume limits, retention periods, access controls, and data-masking mechanisms before sending logs/traces to a centralized system.

## 10. Common Mistakes

1. **Confusing `logger.trace()` with distributed tracing:** it is just a logging level. To get spans, you need actual instrumentation/tracing APIs.
2. **Confusing a stack trace with a distributed trace:** a stack trace describes the call stack at an error point; a distributed trace connects operations across method, process, or service boundaries.
3. **Assuming all logs with the same trace ID belong to the same span:** there can be many span IDs within a single trace; use both fields to pinpoint the exact context.
4. **Generating a new trace ID in every service:** this breaks cross-service correlation. Receive and propagate the context; a new span ID is for the new span.
5. **Using a static/global variable to hold context for all requests:** concurrent requests can overwrite the trace ID. Use request-scoped context properly propagated across tasks.
6. **Summing child span durations to get the request duration:** spans can be nested or run in parallel, causing double counting. Inspect the waterfall/timeline and dependency relationships.
7. **Assuming no request happened when no trace is found:** sampling, exporter errors, or backend retention can prevent a trace from being stored.
8. **Logging only messages without correlation IDs:** in a high-concurrency environment, finding the logs corresponding to a span becomes significantly harder.
9. **Logging exceptions with a formatter that drops the `Throwable`:** you will lose useful stack traces; check your logging backend/formatter.
10. **Collecting every detail forever:** log/trace data grows too large, drives up costs, and increases the risk of data exposure.

## 11. Self-Check

**Scenario A:** In Logback, a developer enables the `TRACE` level, but no traces appear in Jaeger. Why?  
Because the TRACE level only controls log records. You need instrumentation, an exporter, and a tracing pipeline to produce distributed traces.

**Scenario B:** A trace has an `HTTP POST /checkout` span lasting 400 ms and a `callPayment` span lasting 350 ms. What does this suggest?  
`callPayment` accounts for most of the observed time in the trace; you need to inspect the timeline, related spans, and error logs to find the cause—you cannot conclude from those two numbers alone that the payment dependency is failing.

**Scenario C:** Two concurrent requests produce interleaved logs in a single file. How do you follow just one request?  
Attach correlation identifier fields (preferring `trace_id` and `span_id` when tracing is in place), then filter the logs by the ID of the request/span under investigation.

**Scenario D:** A log shows a `NumberFormatException` with many `at ...` frames. Is that a distributed trace?  
No. That is a Java exception stack trace; it only helps identify the call stack at the point of failure.

**Key takeaway:** **Logs describe events; traces describe the relationships and durations of operations within a processing flow**. The TRACE log level and exception stack traces are distinct concepts. In Java, combining logs with correlation IDs and proper tracing lets you move from "what happened" to "which step it happened in and why."

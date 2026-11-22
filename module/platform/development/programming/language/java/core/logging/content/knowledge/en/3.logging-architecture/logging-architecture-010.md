# Logging Architecture Extension Points in Java

## 1. Objectives and Scope

As a Java application grows, logging is no longer just calling a method to print a message. The system needs to change **how events are created**, **filtered**, **enriched with context**, **formatted**, **routed to destinations**, or **exported to observability systems** without rewriting business logic. Those controlled places where behavior can be customized are the **extension points** of a logging architecture.

After this lesson, you will be able to:

- Explain the boundaries between the logging API/facade, provider/backend, logger, filter, handler/appender, formatter/encoder, and collection pipeline.
- Choose the smallest suitable extension point for a new requirement, such as JSON formatting, redacting sensitive data, changing the log destination, or adding a correlation ID.
- Build and run an extension for **java.util.logging (JUL)** using Java 17+.
- Understand how similar concepts appear in **SLF4J**, **Logback**, **Log4j 2**, and the JDK's **System.Logger** mechanism.
- Avoid issues such as bridge loops, losing context across threads, sink failures, slowing down requests, duplicate records, and data leaks.

**Context:** This lesson is part of the *Logging Architecture* section of *Java Core Logging*. The focus is on the boundaries and extensibility of logging within a Java application, not a guide to building a complete centralized monitoring system.

## 2. Architecture Map: Where to Extend?

A common architecture can be viewed along the path of a log event:

~~~text
Business code
  |
  v
Logging API / facade             [1] Swap the API at the application boundary
  |
  v
Provider / logging backend       [2] Choose the implementation that processes logs
  |
  v
Logger + effective level         [3] Rules for accepting logs
  |
  +--> Context / attributes      [4] requestId, traceId, service...
  |
  v
Filter(s)                        [5] Select, drop, or route events
  |
  v
Handler / Appender / Sink        [6] Send to console, file, queue...
  |
  v
Formatter / Layout / Encoder     [7] Text, JSON, or other structures
  |
  v
Collector / Transport / Backend  [8] Collect, process, store, and query
~~~

This diagram represents **roles**, not a mandatory execution order for every framework. For example, a formatter may be invoked inside a handler; some frameworks run filters at multiple stages, perform asynchronous processing, or use routing appenders. Any integration decision should be checked against the actual API and lifecycle of the backend in use.

**Design principle:** business code should only provide *meaningful events* and *permitted context*. Choosing the output destination, formatting, and retention policy belongs in the logging layer or infrastructure. Changing the log format should not require changing the order-creation algorithm.

## 3. Key Extension Points and When to Use Them

| Extension Point | Responsibility | Example Requirement | Should Not Be Used For |
| --- | --- | --- | --- |
| API / facade | Stable logging call surface for application code | Modules share one API, swap backends later | Directly containing HTTP-sending or log-store connection logic |
| Provider / backend | Implement the API, manage loggers, configuration, and pipeline | Choose JUL, Logback, or Log4j 2 | Changing business semantics |
| Logger / level | Decide which events meet the threshold for processing | Enable controlled DEBUG for a specific package | Filtering sensitive data field by field |
| Filter | Rules for accepting or dropping records | Drop heartbeats, send only audit events to a separate sink | Complex record content transformation or calling external services |
| Formatter / layout / encoder | Represent data as bytes/text/structure | JSON Lines matching the organization's schema | Deciding whether a business transaction succeeded or failed |
| Handler / appender / sink | Write or forward data to a destination | File rotation, console, network, queue | Running database queries to make business decisions |
| Context propagation | Attach and propagate correlation information | requestId, traceId across executors/HTTP | Storing global data shared across all requests |
| Collector / exporter | Batch, retry, route, process, and forward telemetry | Send logs to centralized storage | Fixing or inferring business events already lost at the source |

A single requirement may touch multiple layers. For example, **"write JSON logs with a traceId and send them over the network"** requires three distinct parts: generating/propagating trace context, a JSON encoder, and an export/collection mechanism. Do not put all of that inside a single Formatter and make HTTP calls from it: a Formatter should be easy to test, whereas networking has its own timeouts, retries, backpressure, and shutdown lifecycle.

### 3.1. API/Facade and Provider

The **API/facade** is the contract that most Java code calls. It should remain stable so the logging implementation can be replaced, configured, or updated according to operational needs. The **provider/backend** is where actual operations such as filtering, routing, formatting, file writing, and batching are handled.

- **JUL (java.util.logging):** built into the JDK, consisting of Logger, LogRecord, Handler, Filter, Formatter, LogManager, and ErrorManager. Well suited for understanding the foundational mechanics without external libraries.
- **SLF4J:** a popular facade providing a logging API and MDC. **SLF4J 2.x** discovers a compatible provider at runtime; you must avoid having no provider or multiple unintended providers. Actual log writing is handled by the provider/backend.
- **Logback:** a backend commonly used with SLF4J, featuring appenders, encoders/layouts, filters, TurboFilters, and its own configuration.
- **Log4j 2:** provides an API, implementation, and plugin system for components such as appenders, filters, layouts, lookups, or other components; when used alongside SLF4J, you must choose the binding/bridge in the right direction.
- **System.Logger:** a logging API included in the JDK since Java 9. Its advanced extension mechanism is **System.LoggerFinder**; implementing a provider requires considering provider selection, service loading, and JVM startup. It is not the first extension path when you only need a sink or formatter.

The exact names and behavior of each extension depend on the framework and version. A custom JUL Handler **does not automatically become** a Logback Appender: the two follow different contracts and lifecycles.

### 3.2. Adapters and Bridges for Multiple APIs

Dependent libraries may emit logs through different APIs. An **adapter/bridge** routes one API into the chosen backend to centralize configuration and collection. Use a bridge only when there is actually a library that needs to be connected.

Example of a clear, well-designed direction:

~~~text
Application using SLF4J ----> one SLF4J provider/backend
Library using JUL ----------> carefully chosen JUL-to-backend bridge
                                      |
                                      v
                              one backend pipeline
~~~

**Avoid circular bridges** such as JUL → SLF4J → JUL; logs can loop back to the emission point, causing infinite recursion, stack overflows, or hard-to-diagnose errors. Do not add multiple reverse-direction routing mechanisms at once just because each library provides a "bridge." Inspect the actual dependency graph, the provider loaded at runtime, and the output of a sample event.

## 4. Extensibility of java.util.logging

JUL separates responsibilities fairly clearly. Understanding the following classes helps you read the architecture of other logging backends as well.

### 4.1. Logger and the Hierarchy

A **Logger** receives events from application code. Loggers typically form a name hierarchy, for example:

~~~text
(anonymous/root logger)
    |
    +--- com.example
             |
             +--- com.example.order
             |
             +--- com.example.payment
~~~

A LogRecord emitted by a child logger can be forwarded to its parent logger's handlers if **useParentHandlers** is enabled. As a result, a single record may appear twice if a dedicated handler writes it and the record also propagates up to the root logger.

- **setLevel(Level.FINE)** on a logger controls that logger's own processing threshold; the effective level can be inherited if not explicitly declared.
- **setUseParentHandlers(false)** prevents forwarding to parent handlers, which is useful when intentionally building an isolated pipeline.
- **addHandler/removeHandler** attaches or detaches output destinations. When attaching resources such as files or sockets, you must manage when they are flushed and closed.

Do not create a new logger per request or per user. Typically, loggers have stable names based on class/package; variable data such as requestId belongs in per-event attributes/context.

### 4.2. LogRecord: The Event Data Contract

**LogRecord** carries the level, message, source information, timestamp, parameters, Throwable, and metadata provided by JUL. It is the data object received by formatters, filters, and handlers.

Fields should have consistent meaning. An event like **order.failed** might include requestId, a non-sensitive orderId, the error type, and enough data for investigation. If true JSON output is required, you need a valid formatting and escaping strategy; manually concatenating fields into a string does not automatically constitute structured logging.

**Note:** do not rely on a Formatter always being able to obtain accurate caller information via reflection or stack crawling; computing caller location has overhead and can vary depending on how the log method is invoked.

### 4.3. Handler: Output Destination and Lifecycle

**Handler** is JUL's extension point for deciding how a LogRecord is processed. Its core methods are:

~~~java
public abstract void publish(LogRecord record);
public abstract void flush();
public abstract void close();
~~~

A Handler can write to the console, a file, an in-memory buffer, or forward records to a queue. If you write a custom Handler, you must account for **thread safety**, multiple threads calling publish concurrently, level/filter configuration, I/O error handling, flush, close, and behavior when the destination is slow.

- **ConsoleHandler, FileHandler, and StreamHandler** are built-in JUL implementations.
- A Handler has its own **Level**, which can be higher than the logger's level. A record accepted by a logger is not guaranteed to pass the handler.
- A Handler also has a **Filter**. In custom implementations, call **isLoggable(record)** to respect both level and filter rather than checking the message manually.
- Errors in a sink must not cause the business flow to retry indefinitely or generate additional logs through the failing sink itself. JUL provides **ErrorManager/reportError** to support reporting errors inside a Handler.

### 4.4. Filter: Event Selection Policy

**java.util.logging.Filter** is a functional interface:

~~~java
boolean isLoggable(LogRecord record);
~~~

A filter should be **fast, stable, and free of side effects**. A filter can:

- Accept only events whose names start with **order.** for an audit sink.
- Drop overly frequent heartbeat records from a secondary destination.
- Apply intentional sampling rules (if the retention policy allows).
- Route based on level or existing metadata.

Do not use a filter as a substitute for controlling sensitive data at the source. A record may reach other sinks with different filters; if PII is present, protect the data where the event is created and within a controlled pipeline.

### 4.5. Formatter: Representation, Not Delivery

**java.util.logging.Formatter** converts a LogRecord into a string. It can produce single-line text or a properly escaped JSON structure. Formatting should be tested as a pure function; never make network requests inside format().

In a multi-sink architecture, two Handlers can have different Formatters—for example, human-readable console output and a JSON Lines file. However, keep **event names** and **metadata** consistent so different destinations do not misinterpret the meaning of an event.

If you write JSON yourself, you must properly handle control characters, quotes, Unicode, newlines, and exceptions; in production, a battle-tested encoder or library is usually safer.

### 4.6. LogManager and Configuration

**LogManager** manages logging configuration in JUL. Common settings include handler names, levels, formatters, and configuration file selection. Example **logging.properties** file:

~~~properties
.level = INFO
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.order.level = FINE
~~~

The Java command can specify this file at **JVM startup**:

~~~bash
java -Djava.util.logging.config.file=logging.properties Main
~~~

This is an illustrative configuration example; Main must be a compiled class in an actual application. The thresholds at the logger and handler must align: **com.example.order.level=FINE** alone is not enough to see FINE output on the console if ConsoleHandler is still set to INFO. Changing configuration at runtime requires understanding the reload/reconfiguration behavior of the chosen solution and its impact on existing Handlers.

## 5. Complete Example: Extending Filter, Formatter, and Handler on Java 17+

The following example uses **only the JDK**, with no Maven, Gradle, or SLF4J required. The goal is to build an isolated pipeline:

1. **Logger** allows level FINE and above.
2. **Handler** accepts only INFO and above.
3. **Filter** accepts only events whose name starts with order.
4. **Formatter** outputs level, event, requestId, orderId, and exception type.
5. **Handler** writes the result to stdout. In a real application, the sink could be a file, queue, or collector, while the mechanism remains similar.

Create **LoggingExtensionPointsDemo.java**:

~~~java
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingExtensionPointsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.order");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Handler sink = new StdoutHandler();
        sink.setLevel(Level.INFO);
        sink.setFilter(record -> record.getMessage().startsWith("order."));
        sink.setFormatter(new EventFormatter());
        logger.addHandler(sink);

        try {
            logger.fine("order.debug");  // Rejected by handler level.
            logger.info("health.ping");  // Rejected by handler filter.

            LogRecord ok = new LogRecord(Level.INFO, "order.created");
            ok.setParameters(new Object[] {"req-42", "A-100"});
            logger.log(ok);

            LogRecord failed = new LogRecord(Level.WARNING, "order.failed");
            failed.setParameters(new Object[] {"req-43", "A-101"});
            failed.setThrown(new IllegalStateException("payment unavailable"));
            logger.log(failed);
            sink.flush();
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }

    private static final class EventFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] args = record.getParameters();
            String requestId = args != null && args.length > 0 ? String.valueOf(args[0]) : "-";
            String orderId = args != null && args.length > 1 ? String.valueOf(args[1]) : "-";
            String event = record.getMessage();
            String line = record.getLevel().getName() + " event=" + event
                    + " requestId=" + requestId + " orderId=" + orderId;
            if (record.getThrown() != null) {
                line += " error=" + record.getThrown().getClass().getSimpleName();
            }
            return line + System.lineSeparator();
        }
    }

    private static final class StdoutHandler extends Handler {
        private boolean closed;

        @Override
        public synchronized void publish(LogRecord record) {
            if (!closed && isLoggable(record)) {
                System.out.print(getFormatter().format(record));
            }
        }

        @Override
        public synchronized void flush() {
            System.out.flush();
        }

        @Override
        public synchronized void close() {
            flush();
            closed = true;
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 LoggingExtensionPointsDemo.java
java LoggingExtensionPointsDemo
~~~

**Exact stdout output** (verified by running):

~~~text
INFO event=order.created requestId=req-42 orderId=A-100
WARNING event=order.failed requestId=req-43 orderId=A-101 error=IllegalStateException
~~~

**Why are there only two lines?**

- **order.debug** at FINE passes the Logger level, but **does not pass the Handler's INFO level**.
- **health.ping** at INFO passes the Handler level, but **is rejected by the Filter** because the message does not start with order.
- **order.created** and **order.failed** satisfy both the level and the Filter; EventFormatter reads parameters and Throwable to produce searchable structured text.
- **setUseParentHandlers(false)** prevents duplicate output through parent logger handlers.
- **removeHandler + close** demonstrates cleaning up resources when the lifecycle ends.

**Intentional limitations of the demo:** this program does not integrate a framework, output JSON, propagate distributed traces, or handle I/O errors. Fields are concatenated into simple text from known data; if untrusted input is passed into a real formatter, it must be properly escaped/validated to prevent log injection. **StdoutHandler** only illustrates the Handler contract; production should use a built-in sink or a handler thoroughly designed for concurrency, error handling, backpressure, flushing, and shutdown. Do not treat this minimal example as a new logging framework.

### 5.1. Experimenting with Each Extension Point

You can test one change at a time:

- Change to **sink.setLevel(Level.FINE)**: the order.debug event appears, because the filter still accepts the order. prefix.
- Keep the Handler at INFO but change the filter to accept only events starting with **order.failed**: the output contains only the WARNING record.
- Modify **EventFormatter** to include the logger name and timestamp: the emitted output changes, while the event-emitting code stays untouched.
- Enable **setUseParentHandlers(true)**: you must account for parent logger handlers; output may be duplicated or also written to stderr depending on environment configuration.

This is a good way to verify boundaries: change a narrowly scoped policy and observe the records at the corresponding layer.

## 6. The Same Concepts in SLF4J, Logback, and Log4j 2

In projects using a facade, application code typically knows only the API:

~~~java
// Illustration; requires an SLF4J dependency and a suitable provider.
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG = LoggerFactory.getLogger(OrderService.class);

    public void complete(String orderId) {
        LOG.info("event=order.completed orderId={}", orderId);
    }
}
~~~

This snippet is an *integration fragment*, not a standalone application runnable with only the JDK. The **{}** syntax is SLF4J's parameter placeholder; it defers formatting until the backend needs to process the event in the way supported by the API/provider.

Common implementation boundaries:

~~~text
Application -> SLF4J API
                 |
                 v
          selected provider
                 |
       +---------+----------+
       |                    |
  policy/filter         context / MDC
       |                    |
       +---------+----------+
                 |
           Appender / sink
                 |
           Encoder / layout
~~~

- **Logback:** build a custom Appender when you need a new destination; an encoder/layout when you need a new representation; a filter/TurboFilter when you need to drop or accept events at the right point. Do not write a custom appender just to change console formatting if configuring a built-in encoder already meets the need.
- **Log4j 2:** its plugin system lets you build Appenders, Layouts, Filters, and components discovered by the framework via its plugin mechanism. Follow the plugin, configuration, and lifecycle contracts of the specific version you are using.
- **SLF4J:** a facade serving as the logging call contract; it is not where you write backend I/O logic. Swapping providers requires consistent dependency/runtime configuration.

**Architectural question to answer before adding an extension:** Does the current backend already support JSON encoders, rolling files, async appenders, filtering, or routing out of the box? If so, prefer configuring the supported component. Custom code is justified when you have a genuinely distinct requirement, because every self-written extension is a component you must test, monitor, and maintain across upgrades.

## 7. Context Extension Points: MDC and Correlation IDs

An isolated event is hard to investigate if you do not know which request or task it belongs to. Common context includes **requestId, traceId, spanId, service.name, environment, and application version**. This is a cross-cutting responsibility across layers, not just the formatter.

With SLF4J, **MDC** is the API for attaching key–value pairs to the current logging context. The following snippet requires SLF4J and a context-aware backend:

~~~java
import org.slf4j.MDC;

// requestId must be generated/validated at the request entry boundary.
try (MDC.MDCCloseable ignored = MDC.putCloseable("requestId", requestId)) {
    processOrder();
}
~~~

The provider/encoder must be configured to actually output requestId; setting MDC does not guarantee that every output includes the field. When processing finishes, the context must be cleared so reused threads do not retain IDs from another request.

**Concurrency is the easiest place to get this wrong.** MDC may be bound to thread-local context; handing off work to an ExecutorService, CompletableFuture, scheduler, or other execution model can lose or mix up context if the system does not propagate it properly. You need a propagation mechanism suited to your application, libraries, and threading model. Do not treat **ThreadLocal** as a safe context store for an entire distributed task.

**Distributed tracing** propagates trace context across processes. For example, HTTP can use the **W3C Trace Context (traceparent)** standard. OpenTelemetry Java provides instrumentation and context propagation mechanisms; if you choose this stack, you must wire the exporter and log integration properly to include traceId/spanId in logs. Having a traceId in a log **does not guarantee** the trace itself was stored: sampling, the exporter, or network issues may prevent it from reaching the backend.

**Distinction:**
- **requestId**: typically an application/gateway-level request ID used for log correlation.
- **traceId**: the ID of a trace spanning multiple spans/services.
- **spanId**: the ID of the current unit of work within a trace.

These IDs can be used to link records together, but they should not be treated as interchangeable by default. Only log IDs and attributes that comply with your organization's data policies.

## 8. Output Extensions and Pipelines Outside the JVM

Not every requirement should be solved inside the JVM logging backend. You can separate the telemetry transport/transformation layer:

~~~text
Service A      Service B
    |              |
    +-- stdout ----+------> Agent / Collector
    |              |                |
    +-- metrics ---+                +--> Route / Batch / Retry
    |              |                |
    +-- spans -----+                +--> Observability backend
~~~

**When should the application handle it?**
- Defining event names, severity, semantic fields, and business context.
- Ensuring sensitive data is not emitted as unintended telemetry.
- Adding instrumentation at transaction, request, and dependency boundaries.

**When should the collector/pipeline handle it?**
- Routing by environment/service, choosing backends, buffering/batching, and network delivery.
- Adding shared technical resource attributes (when reliable), reducing volume, or performing approved transformations.
- Managing exporter failures and monitoring the health of the telemetry transport pipeline.

A collector cannot recover context that was completely missing at the source. Conversely, each business request should not open a direct HTTP connection to the log storage system and retry indefinitely. This separation reduces coupling between the application and observability infrastructure.

## 9. Contracts to Uphold When Writing Custom Extensions

### 9.1. Performance and Policy When Destinations Are Slow

A synchronous Handler/Appender running on the log-emitting thread can increase request latency. If a file sink is slow or the network is unavailable, logging operations can stall, block threads, or fail. An async queue reduces impact in some cases, but introduces risks of **full queues**, **dropped records**, **lost records on process crash**, and **write order differing from processing order**.

Before using async, decide clearly:
- What is the queue size, and what happens when it is full: block, drop, spill, or fail?
- On shutdown, does it flush/drain with a reasonable timeout?
- Are there metrics for dropped records, queue depth, and exporter errors?
- Does mandatory audit data have separate durability requirements?

Do not claim "async is always faster" if the workload is small, throughput is high, or the blocking policy on a full queue has not been measured.

### 9.2. Error Handling Inside Extensions

Strictly avoid having a failing handler use **the same malfunctioning logger** to log its own error; this easily causes infinite recursion. A proper extension should:

- Follow the backend's error-reporting mechanism (in JUL, **ErrorManager** and the **reportError** helper in Handler).
- Not silently swallow errors unconditionally when the business has event-preservation requirements.
- Close files/sockets/queues on stop; clean up background threads; flush at the right time.
- Test scenarios such as lost connections, full disk, encoding errors, startup/reconfiguration, and shutdown.
- Not break the business processing path solely due to a logging change, unless explicit durability/audit contract requirements are designed.

### 9.3. Schema and Compatibility

When changing a formatter/encoder, you must preserve the data contract for downstream consumers: event names, required fields, data types, units of measurement, and timestamps.

For example, changing **duration_ms** to **duration_ns** without updating the field name and parser can throw off dashboards by a factor of one million. Changing severity from **WARNING** to **WARN** can also break rules if tools filter on fixed values. If the schema changes significantly, manage versioning and coordinate with data consumers.

### 9.4. Security and Cardinality Control

- Never log passwords, bearer tokens, cookies, secret keys, payment credentials, or full sensitive payloads.
- If using JSON, perform proper escaping; if using text, sanitize newlines, control characters, and user-supplied fields to mitigate **log injection**.
- Be careful with MDC and exception messages: they can also contain private data.
- Avoid putting requestId/userId/raw URLs containing IDs into high-cardinality metric labels. Those IDs belong in access-controlled logs/traces instead.
- Restrict log access, set appropriate retention, and protect data in transit and at rest.

## 10. Choosing an Extension Point for Specific Requirements

| Requirement | Suitable Extension Point | Key Verification |
| --- | --- | --- |
| Switch console text logs to JSON | Encoder/Formatter/Layout | Valid JSON, field types, escaping, one event per line |
| Write a separate file for audit events | Handler/Appender + filter/routing | No non-audit events leaked, file lifecycle and retention |
| Enable debug only for an investigated package | Logger level + handler/backend config | Events appear in the right sink without flooding logs |
| Keep source code independent of backend | Facade/API | Runtime has only the right provider, no bridge loops |
| Add requestId to all processing steps | Context + propagation + encoder | Correct ID across threads, no leakage to other requests |
| Send logs over network without slowing requests | Appender/collector + buffering policy | Backpressure, retries, drop metrics, graceful shutdown |
| Exclude heartbeat events from a secondary sink | Filter on that specific sink | Other events remain intact, primary sink still appropriate |
| Connect a JUL library to a shared backend | Supported one-way bridge | No loops, no duplicate records |
| Reduce sensitive content | Avoid emitting at source + safe redaction | Real data never appears in any sink, including errors |
| Add a new log event type | Business code defines event and attributes | Consistent event semantics, schema, and severity |

**Practical rule:** If you only need to change *how data looks*, start with the formatter/encoder. If you are changing *where data goes*, start with the handler/appender/pipeline. If you are changing *which data is accepted*, look at level/filter. If you are changing *the context of the data*, look at instrumentation and propagation. If you are changing *the contract business code calls*, look at the facade/provider.

## 11. Process for Designing, Testing, and Deploying Extensions

A good extension needs a clear contract before writing code.

**Step 1 — Define the boundary.** Clearly specify inputs (LogRecord/log event), outputs (bytes/file/network), level policy, filters, metadata, exceptions, ownership, and failure conditions.

**Step 2 — Check built-in configuration capabilities.** If the backend already supports rolling files, JSON encoders, HTTP exporters, or reliable async appenders, prefer reusing them. Only build a custom extension when the requirement demands distinct behavior.

**Step 3 — Separate pure logic from I/O.** Formatters, schema validation, and simple filtering should be easy to test with fixed inputs; network/file operations have their own lifecycle and failure policies.

**Step 4 — Functional testing.** With JUL, construct a LogRecord with Level, message, parameters, and Throwable, then verify Filter, Formatter, and Handler; test null fields, Unicode, quotes, newlines, and duplicate logs.

**Step 5 — Operational scenario testing.** Simulate an unavailable sink, full queue, multiple threads, application shutdown, and configuration changes. Verify there is no recursion or memory leak; measure latency/throughput and allocation rate under high log volume.

**Step 6 — Integration testing.** Verify runtime dependencies have the right provider, bridges work one-way, effective logger/handler levels are correct, and structured fields reach the backend; trace a sample request end-to-end when correlation is enabled.

**Step 7 — Reversible deployment.** Allow changing configuration or disabling the extension when needed; monitor dropped logs, queue depth, formatter/exporter errors, and CPU/memory impact. Never trade business stability for excessive telemetry.

A short QA checklist:

- The same event appears the exact expected number of times, at the right severity, in the right destination.
- No PII/tokens, and no unescaped malicious control characters are emitted.
- Output is parseable and matches the downstream pipeline schema.
- Concurrency, exceptions, flush/close, and dead-sink scenarios have been addressed.
- RequestId/traceId flows through the expected steps.
- Policies can be changed without modifying core business logic.

## 12. Common Mistakes

**Mistake 1: "To get JSON, write a handler that sends HTTP requests."** A good Formatter/Encoder handles representation; an Appender/Collector handles I/O and transport. Mixing them makes the formatter hard to test, complicates error handling, and easily slows down requests.

**Mistake 2: "Once the logger is set to FINE, every FINE log will appear."** Handlers also have levels and filters. The standalone example in Section 5 proves a FINE record is rejected by an INFO handler.

**Mistake 3: "Add multiple bridges to make sure all logs are collected."** Bidirectional bridges can create loops; multiple providers or backends receiving the same event can create duplicate records. Use a clear flow diagram and verify runtime dependencies.

**Mistake 4: "Request context is always available in child threads."** Executors/async tasks can lose context. Controlled propagation and post-processing cleanup are required.

**Mistake 5: "If a handler fails, just log an ERROR inside it."** If the error message goes back into the same broken handler, the system can loop endlessly. Use the framework's error handling and a safe fallback policy.

**Mistake 6: "A filter is a complete security barrier for all logs."** A single record can reach multiple sinks. Minimize sensitive data at the source, combined with controls at every stage of the pipeline.

**Mistake 7: "Every message should be a single text field."** Without a stable schema, tools struggle to search and group logs. Separate event, severity, service, requestId, and error attributes where appropriate.

## 13. Self-Assessment Exercises

1. In the demo, why does **order.debug** not appear even though the Logger is set to FINE? Which exact property should you change to print it while still excluding health.ping?
2. If a record appears twice after configuring an additional console handler, explain the relationship between child Loggers, parent handlers, and attaching multiple sinks.
3. An application wants both human-readable console output and a JSON file. Should you choose one or two Handlers? What does each destination need in order to write the same event schema with different representations?
4. A service hangs when the log storage system stops accepting data. Identify the layer to investigate, the metrics to measure, and the policy when the queue is full.
5. If switching the backend from JUL to Logback, which parts of business code might need changes when the code uses JUL directly? How does using a shared facade reduce the scope of change?
6. Design a **payment.rejected** log event with a stable event name, requestId, a non-sensitive reason code, appropriate severity, and an exception if present. Describe how to test that no token/card data is leaked.

**Suggested Answers:**

- (1) The Handler at INFO rejects FINE. Change **sink.setLevel(Level.FINE)**; the filter still keeps only events starting with order.
- (2) A child Logger can forward records to parent Handlers; check **useParentHandlers** and the list of registered Handlers.
- (3) Usually two destinations/Appenders/Handlers (console and file), each with an appropriate formatter/encoder; event semantics must remain consistent.
- (4) Inspect the Appender/Handler, exporter, or collector; monitor blocked time, queue depth, dropped records, and retries; choose a backpressure policy aligned with data durability commitments.
- (5) Code calling JUL directly may need an adapter/migration when switching to another facade; code calling a stable facade reduces application coupling to the backend.
- (6) Do not log payment credentials, and do not put raw payloads into exception messages; test with dangerous/newline inputs across all output sinks.

**Key takeaway:** a logging architecture extends cleanly when the layers for **emitting events**, **selecting events**, **adding context**, **formatting**, **writing to destinations**, and **transporting** have clear boundaries. The same business event can reach multiple destinations in multiple formats while business code preserves its meaning and stability.

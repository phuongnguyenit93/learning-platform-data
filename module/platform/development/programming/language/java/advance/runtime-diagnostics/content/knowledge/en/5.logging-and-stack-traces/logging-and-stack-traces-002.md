# 5.2. Logging Level, Thread, Timestamp, and Correlation ID Sufficient to Trace an Operation

An error like "order did not complete" typically traverses multiple layers: HTTP gateway → Java application → executor → inventory service → database → result callback. If logs only contain lines like "start", "processing", "failed", finding **which lines belong to the same operation** is very difficult. Each log record must be designed with enough context to answer: **what happened, when, at what severity, on which thread, and for which request/trace**.

This lesson belongs to group **5. Logging and Stack Traces**. The focus is choosing **log level**, **timestamp**, **thread identity**, and **correlation ID**; practicing emitting a sequence of events that can be stitched together even when work hops across threads or multiple services. Java 17+ is used to illustrate structured log generation; SLF4J/MDC and trace context are explained separately since those libraries are not part of the standard JDK.

## 1. Model of a Searchable and Correlatable Log Event

A useful record is not just a prose sentence. It should have **stable fields** and meaningful values:

| Field | Purpose | Example | Notes |
| --- | --- | --- | --- |
| `timestamp` | Know when the event occurred, roughly order chronologically | `2026-10-29T08:15:30.123Z` | Prefer UTC ISO-8601, explicitly include timezone |
| `level` | Severity/operational significance | `INFO`, `WARN`, `ERROR` | Level must reflect the event, not the author's mood |
| `service` / `instance` / `version` | Identify the application, pod, and build the line belongs to | `order-api`, `pod-a`, `1.8.2` | Especially critical in multi-replica systems |
| `thread` | JVM thread that emitted the record | `http-nio-8080-exec-7` | Threads are reused; **not a request ID** |
| `correlationId` / `requestId` | Link all events belonging to one business operation/request | `req-7c41` | Must be generated/accepted at ingress and propagated across boundaries |
| `traceId` / `spanId` | Link logs with distributed traces and work segments | ID per trace context | Only emit when valid tracing/context exists |
| `event` / `operation` | Stable event type for searching and grouping | `order.reserve.started` | Stable names are better than arbitrary changing prose |
| `message` | Concise explanation of what happened | `inventory reservation failed` | Do not copy raw sensitive data |
| `outcome` / `errorCode` / `durationMs` | Result and impact | `FAILED`, `INV_TIMEOUT`, `832` | Use explicit units, log at work boundaries |
| `exception` / `stackTrace` | Call-path evidence on error | Exception type and stack | Pass the Throwable object to the logging framework, avoid logging only message |

**Minimal set** for diagnostic application logs: `timestamp + level + service + event + thread + correlationId + message`. Add `traceId/spanId` when distributed tracing is present; add `durationMs` and `outcome` for completion events; add exceptions properly for errors. Fields like `instance` and `version` can be attached by collector/resource metadata instead of repeated on every log call.

Illustrative **JSON Lines example** (each line is a JSON object, not the fixed stdout of the program below):

~~~json
{"timestamp":"2026-10-29T08:15:30.120Z","level":"INFO","service":"order-api","thread":"http-worker-4","correlationId":"req-7c41","event":"order.accepted","orderRef":"ORD-42"}
{"timestamp":"2026-10-29T08:15:30.122Z","level":"INFO","service":"order-api","thread":"pool-2-thread-1","correlationId":"req-7c41","event":"inventory.reserve.started"}
{"timestamp":"2026-10-29T08:15:30.954Z","level":"WARN","service":"order-api","thread":"pool-2-thread-1","correlationId":"req-7c41","event":"inventory.reserve.timeout","durationMs":832,"errorCode":"INV_TIMEOUT"}
{"timestamp":"2026-10-29T08:15:30.958Z","level":"ERROR","service":"order-api","thread":"http-worker-4","correlationId":"req-7c41","event":"order.failed","outcome":"FAILED","durationMs":838,"errorCode":"INV_TIMEOUT"}
~~~

The four lines show the **same correlation ID** across **two threads**. If you only filter by thread name, you may miss half of the operation or mix in another request processed on that thread. Timestamps also indicate the time window, but exact causal relationships should be further established via events, parent-child spans/traces, or business workflow rather than inferred from timestamp order alone.

## 2. Log Level: Capturing Signal Without Noise

Frameworks use different level names. SLF4J/Logback/Log4j typically have `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`; Java Util Logging (JUL) uses `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`. These are **two different naming scales**; do not assume a strict one-to-one mapping across every bridge configuration.

| Common SLF4J level | What should be logged | Example events |
| --- | --- | --- |
| **ERROR** | Operation failed or the system could not fulfill its responsibility, requiring investigation/action | Unable to persist order after bounded retries exhausted |
| **WARN** | Abnormal condition, still recoverable/fallback possible, risk of degradation but not a terminal failure | Dependency timeout on first attempt, fallback activated |
| **INFO** | Important business/lifecycle milestones, low churn, useful in production | Request received, transaction completed, major state change |
| **DEBUG** | Details to find root causes within a flow; can be selectively enabled | Processing branch selected, cache miss, retry decision |
| **TRACE** | Very fine-grained, high-frequency operations, enabled only when truly needed | Small internal steps, individual branch evaluations |

**Practical principles:**
- **Do not log ERROR for expected failures** handled per contract, such as invalid requests resulting in 400 as designed. Count or log at INFO/WARN depending on requirements.
- **WARN** is for recoverable anomalies; if every normal request emits a WARN, alerts become meaningless.
- **INFO** marks operational observability milestones, not printing inside every loop.
- **DEBUG/TRACE** must be controlled for volume and sensitive data. Especially avoid logging full request/response bodies, tokens, cookies, credentials, or personal information.
- **One error should have one primary logging point** at the layer owning the outcome. Throwing an exception up through multiple layers where every layer logs ERROR with a stack trace creates duplicates and alert noise.

**Filtering by level:** logger, handler/appender, filter, and collector may have different thresholds. Calling `logger.debug(...)` does not guarantee output when DEBUG is not enabled. When lines are missing, check thresholds at both the logger and output/collector, sampling settings, and pipeline drops under overload.

**Note on stack traces:** when a real error occurs, pass the **Throwable object** to the logging API so the backend renders the exception class, message, and stack/cause chain; calling only `exception.getMessage()` loses the call path. Correlate stack traces with `correlationId`/`traceId` and error events while limiting sensitive data in messages.

## 3. Time: Event Timestamp vs. Duration

**Timestamps** are used to correlate logs across machines, query by time window, and construct timelines. Preferences:
- ISO-8601 UTC format, e.g. `2026-10-29T08:15:30.123Z`; keep timezone/offset explicit.
- Precision appropriate to the system, usually milliseconds or microseconds if supported by tools; do not confuse many digits with true accuracy.
- When a collector is present, distinguish **event timestamp** (when the app emitted it) from **ingestion timestamp** (when the pipeline received it), as batching/network makes them differ.
- Synchronize host/container clocks via infrastructure mechanisms. Clock skew between machines can make a downstream event look like it occurred before upstream.

**Duration** is the length of a measured interval. In Java within the same JVM, measure duration using the difference of `System.nanoTime()` (elapsed time clock) and convert units; do not use `System.currentTimeMillis()` differences for short measurements because the wall clock can be adjusted.

~~~java
long startNanos = System.nanoTime();
// Actual operation enclosed in the measurement interval.
long durationMs = java.util.concurrent.TimeUnit.NANOSECONDS
        .toMillis(System.nanoTime() - startNanos);
~~~

This is an **illustrative measurement snippet**, not a standalone runnable program. Include `durationMs` in completion logs and clearly state **which segment's time** it measures: end-to-end request, a DB call, or waiting for a connection. Do not add durations of parallel branches as if they were sequential; use trace/span critical paths when needed.

Examples:
- Request A enters at `08:00:00.000Z`, finishes at `08:00:00.500Z`: elapsed is about 500 ms if the clock is reliable.
- A DB call span takes 300 ms and a cache call span takes 250 ms **which may run in parallel**: you cannot conclude total request time equals 550 ms simply by adding them.
- UTC timestamps help join multi-timezone logs; durations within a single process should still use monotonic measurement.

## 4. Thread Name Is Execution Context, Not a Correlation ID

`Thread.currentThread().getName()` (Java 17+) reports the current thread's name. The name helps check:
- Whether the task ran on an HTTP worker, executor pool, scheduled task, or special thread.
- Whether a thread is stuck in a stack trace, lock contention, or queue.
- Whether an operation hopped across different executors across multiple events.

However, **a thread can serve many requests sequentially** and a single request can **execute across multiple threads**. With async work, callbacks, `CompletableFuture`, or reactive pipelines, the thread on the start event may differ from the thread on the completion event. Therefore:
- Do not construct a correlation ID from thread name/thread ID.
- Do not filter the entire issue by thread name and assume all those logs belong to one request.
- To correlate with thread dumps, store thread name/identifier alongside timestamp and process identity, then match against event logs.

Thread names can be customized in operationally meaningful ways, such as `inventory-worker-2`, but you should not embed request IDs directly into pooled thread names: cleanup is easily missed and observations become misleading.

## 5. Correlation ID, Request ID, Trace ID, and Span ID

These identifiers are related but **not synonymous**:

| Identifier | Scope | Purpose |
| --- | --- | --- |
| **correlationId** | A system-defined operation/workflow | Find all related logs, potentially linking multiple requests/messages |
| **requestId** | A single request entering a service/gateway | Distinguish individual requests, including retries |
| **traceId** | A distributed trace spanning multiple services and spans | Link logs with distributed tracing |
| **spanId** | A unit/segment of work within a trace | Attach logs to a specific processing segment |
| **business reference** | Order, transaction, business message | Look up by domain entity; not necessarily unique per execution |

Depending on architecture, `correlationId` may equal request ID at ingress; if a workflow spans multiple retries/sequential requests, design a way to distinguish individual attempts alongside the shared correlation ID. Do not substitute `userId`, email, or phone number for correlation ID: it introduces security risks and is not unique per operation.

**Trace context:** the W3C Trace Context standard defines the `traceparent` header to carry trace ID/parent span ID and trace flags over the network; OpenTelemetry can attach `TraceId` and `SpanId` in log records. **TraceId** is typically represented as 32 hex characters, **SpanId** as 16 hex characters in W3C format. Do not fabricate a random string into `traceId` if the system does not actually have a valid span/context.

At system boundaries:
1. If a valid correlation ID already exists from the gateway/parent, continue using it per system policy; **validate length and characters** to prevent log injection and resource abuse.
2. If no ID exists or the value is untrusted, generate a new ID via a suitable mechanism, such as a UUID for internal correlation IDs.
3. Place the ID into the request/job context, and add it to outgoing HTTP headers or message metadata when components need correlation.
4. Downstream, read/validate and propagate per trust boundary policy; attach the ID to logs for relevant events.
5. On retry, you can keep a **shared** correlation ID while adding `attempt` or a separate `requestId` to distinguish each attempt.

Do not blindly trust forged client headers as authentication/authorization data. IDs serve **observability and correlation only**, never as proof of identity or access rights.

## 6. Choosing Log Points to Trace an Operation

A typical flow:
1. **Ingress/accepted:** request/job is received; log INFO with ID, task type, endpoint or business event, source.
2. **Dispatch/start:** record start of processing, optionally including queue wait if measurable.
3. **Key boundaries:** before/after dependency calls, connection acquisition, retry start, fallback, message publish; if emitted frequently, consider DEBUG paired with metrics/tracing.
4. **Failure:** WARN for recoverable failures; ERROR for failed outcomes. Log a stable `errorCode`, valid Throwable, and relevant dependency details.
5. **Completion:** INFO for the main outcome, `outcome`, end-to-end `durationMs`, correlation ID; do not over-log every tiny step.

**Balancing principle:** not every application needs INFO logs on every request if traffic is massive. You can use structured access logs, tracing, and metrics to preserve needed signal without excessive log volume; raise DEBUG/TRACE selectively when investigating.

### Event and Status Naming Conventions

Choose stable, meaningful event names, for example:
- `order.received`
- `order.inventory.reserve.start`
- `order.inventory.reserve.retry`
- `order.inventory.reserve.failure`
- `order.completed`

Avoid relying solely on a free-form `message` sentence like "doing something" or "failed again". If wording or language changes, a stable `event` field still supports queries and dashboards. Separate `outcome=SUCCESS/FAILED/CANCELLED` and `errorCode=...` as structured data rather than text requiring regex extraction.

## 7. Standalone Java 17 Example Requiring No External Libraries

Standard Java provides `java.util.logging` (JUL): `Logger`, `Level`, `LogRecord`, `Handler`, and `Formatter`. The snippet below creates a **logger**, stores metadata in `LogRecord.parameters`, uses `StreamHandler` to write to stdout, and uses an explicit `Formatter` to output four required pieces of information: **timestamp, level, thread, correlation ID**, along with event type and message.

To make stdout reproducibly exact in this lesson, the example uses **`Clock.fixed`** with a fixed instant; production must use a real clock like `Clock.systemUTC()` or the timestamp source managed by the logging framework. This is an **educational illustration**; in production, use the framework's structured JSON encoder to escape content and attach standard metadata.

Create the file **CorrelatedLoggingDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class CorrelatedLoggingDemo {
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-10-29T08:00:00Z"),
            ZoneOffset.UTC
    );
    private static final Logger LOG = Logger.getLogger("order.demo");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                Object[] p = record.getParameters();
                return "%s level=%s thread=%s correlationId=%s event=%s message=\"%s\"%n"
                        .formatted(
                                p[0],
                                record.getLevel().getName(),
                                p[1],
                                p[2],
                                p[3],
                                record.getMessage()
                        );
            }
        };

        StreamHandler handler = new StreamHandler(System.out, formatter);
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        String correlationId = "req-42";
        emit(Level.INFO, correlationId, "order.received", "begin");
        emit(Level.WARNING, correlationId, "inventory.retry", "retry scheduled");
        emit(Level.INFO, correlationId, "order.completed", "success");

        handler.flush();
    }

    private static void emit(
            Level level, String correlationId, String event, String message) {
        LogRecord record = new LogRecord(level, message);
        record.setParameters(new Object[] {
                Instant.now(CLOCK),
                Thread.currentThread().getName(),
                correlationId,
                event
        });
        LOG.log(record);
    }
}
~~~

Compile and run from the file's directory using **JDK 17+**:

~~~bash
javac CorrelatedLoggingDemo.java
java CorrelatedLoggingDemo
~~~

**Exact stdout** (three logs sharing the correlation ID, thread is `main`, clock is fixed in the example):

~~~text
2026-10-29T08:00:00Z level=INFO thread=main correlationId=req-42 event=order.received message="begin"
2026-10-29T08:00:00Z level=WARNING thread=main correlationId=req-42 event=inventory.retry message="retry scheduled"
2026-10-29T08:00:00Z level=INFO thread=main correlationId=req-42 event=order.completed message="success"
~~~

**Reading the output:**
- Although the messages differ, all three events share `correlationId=req-42`, so they can be grouped into one flow.
- `level=WARNING` is **JUL's** naming convention; many other frameworks use `WARN`.
- `thread=main` is expected since the example runs synchronously on the main thread; async examples may switch threads while still keeping the correlation ID.
- Identical timestamps come from `Clock.fixed` **solely for reproducible verification**, not representing real production timing.
- `LogRecord.parameters` carries metadata in this lesson; in production, a backend JSON encoder or typed key-value API is safer than manual string formatting.

**What this example does not yet do:** propagate context across threads/services, record exception stack traces, redact sensitive data, async logging, sampling, or automatically record trace IDs. Those tasks require logging frameworks, tracing instrumentation, and corresponding system policies, covered in the following sections.

## 8. MDC with SLF4J/Logback: Attaching IDs to Every Log on a Flow

Java applications commonly use `org.slf4j.MDC` (Mapped Diagnostic Context) to store metadata per execution context. A compatible framework/encoder can read MDC and include it in logs without passing `correlationId` into every log call.

The snippet **illustrates SLF4J usage** and **does not run standalone** because it requires the SLF4J dependency, a supported backend such as Logback, and application variables `log`/`correlationId`:

~~~java
import org.slf4j.MDC;

// Input assumed already validated and normalized.
String previous = MDC.get("correlationId");
MDC.put("correlationId", correlationId);
try {
    log.info("order.received");
    performOrderWork();
    log.info("order.completed");
} catch (RuntimeException ex) {
    log.error("order.failed errorCode=ORDER_FAILURE", ex);
    throw ex;
} finally {
    if (previous == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", previous);
    }
}
~~~

**Why is `finally` mandatory?** Thread pools reuse threads for subsequent requests. Without clearing or restoring MDC, the next request can be stamped with the previous request's ID, corrupting timelines and leaking context across users. The snippet preserves any prior MDC value for nested calls; at a completely independent request boundary, many systems choose to clear the entire context at the start/end by a consistent convention.

**Essential note:** merely calling `MDC.put(...)` does not ensure the ID appears in the output. The backend's pattern/JSON encoder must be configured to include the MDC field—for example, conceptually `correlationId` in a Logback pattern is `%X{correlationId}`. If the encoder/collector omits the field or uses a different name, logs still lack the ID even though MDC was set.

### When Work Moves to Another Thread

MDC is usually bound to the thread context and does not automatically carry across `ExecutorService`, `CompletableFuture`, or all reactive pipelines by default. You must intentionally capture and restore context or use framework/observability agent integration.

The snippet below **illustrates a single call site**, assuming `ExecutorService executor`, `org.slf4j.MDC`, and logger `log` already exist:

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        log.info("inventory.reserve.started");
        // Process work for the current operation.
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Here the **parent's snapshot** is transferred to the worker, and the **worker's previous context** is restored upon exit. Other contexts besides MDC (e.g., OpenTelemetry Context, security context) may need separate propagation mechanisms; copying MDC alone is **not enough** to maintain an active trace span. If the framework already provides a supported task decorator/instrumentation, prefer that mechanism to avoid missing an async branch.

With reactive pipelines or virtual threads (JDK 21+), do not assume `ThreadLocal`/MDC propagates properly across executor switches. Propagate context according to the framework's context model, use verified integrations, and test logs across every async boundary.

## 9. Distributed Tracing: Linking Logs Across Multiple Services

An application-specific correlation ID may suffice to find all records for one workflow. When tracing is present, also link:
- **`traceId`** stays constant across the entire distributed trace.
- **`spanId`** changes per unit of work/operation.
- **`service.name`** identifies the service owning the log.
- **`correlationId`** may exist alongside, especially when business workflows span multiple messages or separate traces.

OpenTelemetry defines **log correlation** via time, execution context, and resource attributes; log records can carry `TraceId`/`SpanId` to jump from logs to the corresponding trace. The condition is that **trace context is properly propagated** across functions/threads and HTTP/message boundaries, and the logging backend/exporter actually attaches those fields.

### Illustrating an Operation Crossing Two Services

~~~text
Request POST /orders
  |
  | correlationId=req-42
  | traceId=4f... (same trace)
  v
order-api
  |  event=order.received
  |  spanId=aa... (order span)
  |
  +---- calls inventory-api (HTTP context propagation) ---->
            event=inventory.reserve.started
            traceId=4f... (same trace)
            spanId=bb... (inventory span)
            |
            +---- event=inventory.reserve.completed
  |
  v
order-api
  event=order.completed
~~~

The shortened IDs in the diagram are **illustrative only**, not valid W3C formats for network transmission. Obtain real IDs from the active tracing context rather than reconstructing span IDs from thread names. If `traceparent` or context is lost at an async boundary, downstream logs may lack trace IDs or belong to a different trace; an application correlation ID can still aid investigation, though it does not replace proper propagation.

**Do not use correlation ID as a high-cardinality metric label** per request; log fields serve detailed queries, whereas metrics generally use low-cardinality labels like route, outcome, and status class.

## 10. Keeping Logs Structured, Safe, and Cost-Effective

**Structure:** one valid JSON object per event (JSON Lines) is a common choice with log search systems. Declare consistent field names, data types, and units: `durationMs` as a number, `level` as an enum/string, `timestamp` as an ISO timestamp, `event` as a stable name. Never manually concatenate unescaped JSON from user input.

**Correlation IDs:** generate unique IDs within system scope; when received via headers, enforce character/length limits and guard against newline/control characters. Forward IDs downstream only per contract. Do not turn IDs into access credentials or identifiers containing personal data.

**Security and sensitive data:** never log access tokens, passwords, session cookies, private keys, full payment cards, raw authentication headers, or sensitive request bodies. Log only minimal approved business fields, with masking/redaction and access controls. Stack traces may contain paths, user inputs, query text, or sensitive context; review before exporting/sharing.

**Log injection:** client-supplied data can contain newlines or control characters that forge log lines in plain-text output. Use a structured logger/encoder that escapes properly; avoid interpolating raw user input into `message`.

**Frequency and performance:** logging DEBUG/TRACE inside hot-path loops causes CPU, allocation, and I/O overhead; async log pipelines can drop entries when queues fill. Rely on metrics to track rates, logs to explain events, and traces to connect critical paths. During an investigation, raise log levels selectively and revert once sufficient evidence is gathered.

**Do not duplicate exception logs:** if a lower layer merely throws an exception and an upper layer decides the outcome, prefer logging ERROR at the deciding layer while preserving the cause chain. If a lower layer needs to log WARN for a retry, a distinct event and errorCode prevent mistaking two logs for two independent incidents.

## 11. Procedure to Trace an Operation from Logs

Suppose a user says "Order ORD-42 errored around 15:15". Diagnostic procedure:

1. **Lock down scope:** timezone, time range, environment, service, version, endpoint, business reference, or correlation ID from response/gateway. Do not rely on vague times like "sometime in the afternoon" as the sole anchor.
2. **Find the request/correlation ID:** query ingress logs by the permitted business reference; if an ID came from a response header, look it up directly. Do not search by thread name first.
3. **Group by ID:** gather logs across services, instances, and worker threads, sorted by event timestamp. Use trace/span parent-child links to determine causality when clocks skew or events run concurrently.
4. **Locate start, boundary, error, and end markers:** which event is missing? Was the request queued, sent to a dependency, retried/fallen back, or timed out where?
5. **Compare durations and outcomes:** total request duration, queue wait, dependency call, timeout, attempt count. Do not add overlapping spans to deduce total latency.
6. **Read the stack trace on the right event:** inspect exception type/cause chain, throw site, and the first meaningful failure event; do not assume the final ERROR line is the root cause.
7. **Cross-check other sources:** metrics, distributed traces, thread dumps, GC logs, dependency/server logs, and deployment timelines as needed.
8. **Write an evidence-backed conclusion:** state "request req-42 timed out calling inventory after 832 ms, order-api returned an error at 838 ms" if proven by logs/traces; avoid stating "DB failed" without evidence.

**Examples of distinction:**
- Logs `order.received` on thread `http-4`, `inventory.reserve.started` on `pool-2-thread-1`, and `order.failed` on `http-4` still belong to the same workflow if the ID matches and was propagated properly.
- Two different requests running sequentially on `http-4` are not the same operation even though the thread name is identical.
- A lower-layer `ERROR` may be retried successfully at a higher layer; confirm the final outcome from the completion log rather than stopping at the first error.

## 12. Common Mistakes and Fixes

| Symptom | Common cause | How to improve |
| --- | --- | --- |
| Logs only have messages, no IDs | No log field contract or missing formatter setup | Attach ID at ingress; add to encoder and log boundaries |
| ID vanishes across an executor | MDC/trace context was not propagated | Use task decorator/context wrapper/instrumentation; test async boundaries |
| New request carries old request's ID | Forgot ThreadLocal/MDC cleanup in thread pool | Use `try/finally` to restore or clear per contract |
| Same ID yet timestamps go "backward" | Clock skew, async batching, ingestion delay | Use UTC/event timestamps, span relationships, and monotonic durations |
| Too many ERRORs for one exception | Every layer catches, logs, then rethrows | Log outcome only at the responsible layer; distinguish retry WARNs |
| Missing DEBUG logs | Logger/appender threshold, filter/sampling, or pipeline drop | Check effective level and entire log emission path |
| No stack trace in ERROR log | Logged `e.getMessage()` instead of Throwable | Pass Throwable object to the framework |
| Filtered by thread only, missed half the flow | Async request switched threads | Group by correlation/trace ID; thread is auxiliary context |
| JSON parse failure or split log lines | Appended user input via string concatenation | Use proper escaping encoder and restrict raw input |
| Log queries too expensive | High volume, overly long retention, inconsistent fields | Reduce high-frequency logs, standardize schema, targeted retention/sampling |
| Logs contain passwords/tokens | Logged raw requests/headers or exception context | Redaction, field allowlists, check access/retention |
| Mismatch between logs and traces | Trace context not propagated or not injected into logger | Check `traceparent` and integration, include valid traceId/spanId |

## 13. Correlation Testing Checklist

Before considering a service's logging sufficient for diagnostics, test a request with a known correlation ID and verify:

1. **Level:** INFO for major milestones; WARN/ERROR at appropriate severities; DEBUG appears only when enabled.
2. **Timestamp:** UTC with offset, adequate resolution; records include event time and duration in proper units.
3. **Thread:** logs show the emitting thread; flows switching executors preserve the same correlation ID.
4. **Correlation ID:** generated at ingress if absent; validated on receipt; attached at every relevant boundary; distinct requests never bleed old IDs.
5. **Trace:** if instrumented, `traceId` links across services and `spanId` reflects the actual span.
6. **Lifecycle:** accepted/started, dependency/retry, failure or completed events and processing duration are all discoverable.
7. **Exception:** terminal errors have a stable `errorCode` and Throwable stack/cause chain when needed.
8. **Structured output:** parser/collector parses all fields; user data is escaped, secrets are stripped.
9. **Load:** check drop rates under high log volume; ensure DEBUG does not become a bottleneck.
10. **Real queries:** from one correlation ID, you can retrieve all events across multiple threads and services and write an evidence-backed conclusion with timestamps.

**Key takeaway:** **timestamp** answers *when*; **level** answers *how urgent*; **thread** answers *where in the JVM it ran*; **correlationId/traceId** answers *which operation it belonged to*. To trace an operation end to end, attach the same ID at key milestones from ingress to completion, propagate context across every boundary, and always record outcome, duration, and exceptions properly. No single field replaces the full context.

### References

- Java SE 17, `java.util.logging` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html
- Java SE 17, `StreamHandler` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- SLF4J, Mapped Diagnostic Context: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- OpenTelemetry Logs Specification, Log Correlation: https://opentelemetry.io/docs/specs/otel/logs/
- W3C Trace Context: https://www.w3.org/TR/trace-context/

Format, event, and ID examples in this lesson are illustrative; in implementation, use a logging backend, tracing integration, and data protection policy suitable for the real system.

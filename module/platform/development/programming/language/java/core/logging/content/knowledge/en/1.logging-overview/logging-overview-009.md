# Logging and Observability in Java Core

## 1. Learning Objectives

After this lesson, you will be able to:
- Distinguish between logging, monitoring, and observability; choose the right signals (logs, metrics, or traces) to investigate an issue in a Java application.
- Design logs with context, priority levels, structured data, and the ability to correlate processing steps of a single request.
- Use `java.util.logging` (JUL) in Java 17+ programs, and understand the role of SLF4J and common logging backends.
- Understand how telemetry is collected, propagated, correlated, and leveraged to detect incidents, find root causes, and measure impact.
- Avoid common pitfalls regarding noise, performance, sensitive data, context propagation, and storage costs.

**Scope:** This covers foundational knowledge of Java Core Logging. Tools such as OpenTelemetry, Logback, Log4j 2, Prometheus, and centralized observability systems are referenced by their roles and integration points; no specific framework is required to understand the principles.

## 2. How Does Logging Differ from Observability?

**Logging** is the practice of an application recording meaningful events: a request was received, processing succeeded, a connection was retried, an authentication error occurred, an external service call failed, and so on. A useful log answers: *what happened, where, when, in what context, and what was the outcome?*

**Monitoring** typically tracks predefined metrics and conditions: error rate, response time, memory usage, requests per second, and queue depth. It helps recognize *that there is a problem*.

**Observability** is the ability to infer the internal state and behavior of a system from the signals it emits. It helps answer unforeseen questions as well, such as: *why are only requests of a certain operation type slow when calling the inventory service?* Logs are one source of observability signals, but a system with many logs is not necessarily observable.

Example: an order lookup endpoint starts experiencing p95 latency increasing from 120 ms to 1.8 s.

- **Metrics** show when the latency started rising, what percentage of requests are affected, and whether the error rate changed.
- **Traces** show where time is spent: in a database query, an HTTP call, or processing inside the JVM.
- **Logs** explain the specific events: a connection timed out, a retry occurred, an upstream error code was returned, or an unusual execution path was taken.

All three are needed to go from **detection → localization → explanation → fix verification**. Observability can also use profiles, thread dumps, and operational events; the three signals below are the common foundation, not the entirety of observability.

## 3. The Three Signal Pillars: Logs, Metrics, and Traces

| Signal | Typical Data | Questions It Answers Well | Limitations to Keep in Mind |
| --- | --- | --- | --- |
| **Logs** | Events with timestamp, level, message, attributes, exception | Exactly what events occurred for this request? | High volume of records; hard to infer latency distributions from logs alone |
| **Metrics** | Counters, gauges, histograms with timestamps and labels | Have error rates, throughput, p95/p99, or resource levels changed? | Aggregated numbers usually lack per-request detail |
| **Traces** | A trace consisting of spans with parent–child relationships and execution durations | Which components did the request pass through; which step was slow? | May be sampled; incomplete instrumentation leaves gaps |

**Core concepts:**

- **Log record/event:** the unit of recording an event. Common fields include timestamp, severity, logger, message, event name, service, and correlation IDs.
- **Counter:** a value that increases with the number of event occurrences, such as request count or error count. Use the increase over a time interval to compute a rate; note that counters may reset when a process restarts.
- **Gauge:** a current value that can go up or down, such as the number of active tasks or heap currently in use.
- **Histogram:** a distribution of observations, such as response times. Used to evaluate tail latency (p95/p99), rather than looking only at averages.
- **Trace:** the logical journey of an operation across components. A **Span** describes a single step, with start/end times, attributes, events, and status.
- **Trace ID:** identifies the entire journey; **span ID:** identifies a single step within the trace. A **Request ID** assigned by the application/gateway can be useful, but does not automatically replace a trace ID.

A single scenario can produce all three signals:

~~~text
HTTP GET /orders/42
  trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  [server span: GET /orders/{id}]
    [client span: GET inventory-service]
      [server span: inventory lookup]
          WARNING event=inventory_timeout trace_id=... request_id=req-42
  metric: http.server.request.duration (histogram)
  metric: http.server.request.count / failed_requests (counter)
~~~

The ellipsis in the example above is just shorthand for illustration; real telemetry must contain the full ID value. A log with a trace ID only correlates with a trace when the ID is propagated and included in the log properly; the system does not correlate them automatically just because a logger is enabled.

## 4. Logging Flow and Tools in the Java Ecosystem

A typical logging flow:

~~~text
Java code creates log event
        |
   Logging API / facade
        |
  Logger + level + filter
        |
 Handler / Appender + formatter / encoder
        |
 Console / file / telemetry pipeline
        |
 Collector / storage / search / alerting
~~~

**java.util.logging (JUL)** is built into the JDK and uses these main components:
- **Logger:** where the application emits records and configures level thresholds.
- **LogRecord:** data about an event (level, message, timestamp, logger, exception, etc.).
- **Handler:** where records are sent to a destination, such as `ConsoleHandler` or `FileHandler`.
- **Formatter:** converts a `LogRecord` into text. A formatter can produce plain text, XML, or a structured format you implement.
- **Filter:** decides whether a record is accepted or rejected.

A record can be blocked at the logger, filter, or handler. For example, if a logger allows `FINE` but `ConsoleHandler` is set to `INFO`, the `FINE` record will still not appear. JUL uses levels such as **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**.

**SLF4J** is a facade: application code calls a unified API, while the actual logging provider (such as Logback or Log4j 2 via its corresponding provider) handles the logs. This is common in many Java applications, though it does not mean every Java project uses SLF4J. When using SLF4J 2.x, you need a compatible provider and configuration that avoids multiple providers or bidirectional bridges that cause loops. JUL can be bridged to another backend via a carefully chosen bridge. Java 9+ also provides **System.Logger** as a JDK logging API.

Log levels should reflect **operational meaning**, not message length:

| Common Level | Appropriate Situation |
| --- | --- |
| ERROR / JUL SEVERE | A critical operation failed and cannot be completed at this layer |
| WARN / JUL WARNING | An unusual condition, retry, fallback, or risk; the system can still proceed |
| INFO | Valuable business/lifecycle events with controlled record volume |
| DEBUG / JUL FINE | Details needed during investigation; usually disabled in production |
| TRACE / JUL FINER, FINEST | Very detailed execution flow, potentially high overhead |

Level names and mappings across frameworks are not identical. For example, JUL's `SEVERE` is not a level name in the SLF4J API. Do not use `ERROR` for a request rejected due to invalid user input, or log every method call at `INFO`.

## 5. Designing Structured Logs with Sufficient Context

Instead of a hard-to-parse string like "An error occurred!", log a **stable event name** and well-defined fields. An illustrative single-line JSON record:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "severity": "WARN",
  "service.name": "inventory",
  "environment": "production",
  "event": "stock_lookup_failed",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "dependency": "inventory-db",
  "error.type": "ConnectionTimeoutException",
  "retry_count": 1
}
~~~

This is example data, not a mandatory format for JUL. In a real system, agree on a schema up front (attribute names, data types, how severity and exceptions are represented) so queries, event grouping, and dashboards stay consistent.

Design principles:

1. **Log enough to act:** standardized timestamp with timezone (usually UTC), service, environment, deployment version, event name, severity, outcome, correlation IDs, and meaningful error info. Choose details based on investigation needs.
2. **Stable event names:** prefer `event=payment_authorization_failed` with fields like `reason` and `gateway` instead of generating thousands of distinct message strings. A field should not change its data type across cases.
3. **Consistent context:** `request_id`, `trace_id`, `span_id`, and non-sensitive operation IDs must be carried across relevant layers. Do not assume logs from the current thread alone are enough to trace an entire request.
4. **Exceptions in the right place:** log the cause and stack trace at the appropriate handling boundary; avoid logging the same exception at every layer and flooding the system with duplicates. If handled and recovered successfully, severity may be `WARN`/`INFO` depending on your operational contract.
5. **Log only permitted data:** never log passwords, access tokens, private keys, session cookies, payment details, or sensitive payloads. Apply masking/redaction before logging and enforce clear access/retention policies.
6. **Separate data from the message:** structured encoders handle extraction and escaping better than manual string concatenation. In particular, user-supplied content may contain newlines or control characters that cause log injection; encode formats properly.
7. **Do not rely on absolute ordering:** logs across JVMs/hosts can have clock skew, be buffered, or arrive at the collector late. Use timestamps together with IDs and span relationships to reconstruct execution; do not infer causality solely from display order.

**A sign of a useful log:** when encountering `event=stock_lookup_failed`, the on-call engineer knows to filter by `trace_id`/`request_id`, inspect `dependency`, `error.type`, `retry_count`, and the timestamp to narrow down the issue—they do not have to guess from free-form prose.

## 6. Standalone Java 17+ Example with `java.util.logging`

This example uses built-in JDK APIs to log two events and count requests/errors. The program intentionally triggers one successful request and one failed request; a small formatter makes the output easy to compare.

Create the file **LoggingObservabilityDemo.java**:

~~~java
import java.util.concurrent.atomic.LongAdder;
import java.util.logging.*;

public class LoggingObservabilityDemo {
    private static final Logger LOG = Logger.getLogger(LoggingObservabilityDemo.class.getName());
    private static final LongAdder REQUESTS = new LongAdder();
    private static final LongAdder ERRORS = new LongAdder();

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                String message = record.getLevel().getName() + " " + record.getMessage();
                Throwable error = record.getThrown();
                return message + (error == null ? "" : " exception=" + error.getClass().getSimpleName())
                        + System.lineSeparator();
            }
        });
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            lookup("req-001", false);
            lookup("req-002", true);
            handler.flush();

            System.out.println("metric.requests_total=" + REQUESTS.sum());
            System.out.println("metric.errors_total=" + ERRORS.sum());
        } finally {
            LOG.removeHandler(handler);
        }
    }

    private static void lookup(String requestId, boolean shouldFail) {
        REQUESTS.increment();
        long start = System.nanoTime();
        try {
            if (shouldFail) throw new IllegalStateException("stock unavailable");
            LOG.info("event=stock_lookup_success requestId=" + requestId);
        } catch (IllegalStateException error) {
            ERRORS.increment();
            LOG.log(Level.WARNING, "event=stock_lookup_failed requestId=" + requestId, error);
        } finally {
            long durationNanos = System.nanoTime() - start;
            LOG.log(Level.FINE, () -> "event=stock_lookup_finished requestId=" + requestId
                    + " duration_ns=" + durationNanos);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 LoggingObservabilityDemo.java
java LoggingObservabilityDemo
~~~

Output on **stdout** (verified by actual compilation and execution):

~~~text
INFO event=stock_lookup_success requestId=req-001
WARNING event=stock_lookup_failed requestId=req-002 exception=IllegalStateException
metric.requests_total=2
metric.errors_total=1
~~~

Notable points:

- **LOG.setUseParentHandlers(false)** prevents the record from being printed a second time by the root logger when we attach a custom handler.
- **StreamHandler** is buffered; calling **handler.flush()** before printing the counters ensures the output order in the example. This formatter intentionally prints only the exception class name to keep output stable. **In production, configure it to display/collect the necessary stack traces**, rather than using this abbreviated formatter as a standard template.
- Both the logger and handler are set to **INFO**, so the **FINE** duration event does not appear. Using the supplier **() -> ...** ensures the detailed message is only constructed when the level allows it.
- **System.nanoTime()** is suitable for measuring elapsed time within the same process; it is not a wall-clock timestamp. To timestamp logs, use a real-time timestamp with a timezone.
- **LongAdder** is a safer counter when multiple threads increment concurrently. However, the values printed here are only **in-memory counters**, not exported metrics; a real monitoring system needs an appropriate collector and metrics exposition mechanism.
- A total counter does not tell you p95/p99. To track latency, record timing observations into a **histogram** via a metrics library and export them to a suitable backend.

This example demonstrates **specific events + contextual identifiers + aggregated metrics**. It does not yet create distributed traces; traces must be instrumented and context propagated when multiple steps or multiple services are involved.

## 7. Correlating Logs Within a Flow and Across Threads

When a request travels through controller → service → repository → HTTP client, you often want every log to carry the same **request_id**. In applications using SLF4J, **MDC (Mapped Diagnostic Context)** lets you attach information to the logging context of the current thread.

The following snippet is **for integration illustration only**; it requires the SLF4J dependency, a provider supporting MDC, and a layout/encoder configured to read the `requestId` key (it does not compile standalone with only the JDK):

~~~java
import org.slf4j.MDC;

// In a handler that has received a valid requestId:
try (MDC.MDCCloseable ignored = MDC.putCloseable("requestId", requestId)) {
    // Process the request; the logger can read MDC["requestId"] via the encoder configuration.
    processRequest();
}
// Scope closed; prevents requestId from leaking to the next request on the same thread.
~~~

With a Logback pattern encoder, an illustrative field might be **%X{requestId}**. If using a structured encoder, configure it to emit `requestId` as a dedicated attribute. Do not assume every backend or configuration exports MDC automatically.

**Important concurrency pitfall:** MDC is typically thread-bound; handing work off to an **ExecutorService, CompletableFuture**, another thread, or an async pipeline can lose `requestId`, or leak context if you forget to clean it up. Propagate context properly using a wrapper/task decorator or a propagation mechanism compatible with your library; clean up context in a `finally` block or closeable scope. Do not assume context propagates automatically across every executor, virtual thread, or reactive pipeline.

In **distributed tracing**, context must be propagated across process boundaries (usually via HTTP headers following W3C Trace Context, such as `traceparent`). An example of a valid `traceparent`:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Components must extract incoming context, create child spans when needed, and inject context into outbound calls. OpenTelemetry is a popular choice for instrumenting Java and exporting telemetry; whether `trace_id`/`span_id` automatically appear in logs **depends on instrumentation and logging integration configuration**, not a default feature of JUL or SLF4J. Always verify correlation on real requests.

## 8. From Instrumentation to an Observability System

A common deployment architecture:

~~~text
Java service
  |-- structured logs ---------|
  |-- request/DB latency metrics|--> agent/collector --> backends --> dashboards/search/alerts
  |-- trace spans --------------|
~~~

Each component has a distinct role:

- **Instrumentation:** records request counts, durations, errors, key spans (HTTP, DB, queue), and meaningful events. Auto-instrumentation reduces effort, but does not replace adding necessary business context.
- **Propagation:** preserves trace context across threads/tasks and network boundaries; limit, validate, and sanitize context data received from untrusted sources when appropriate.
- **Collection/export:** console/file handlers, agents, or SDKs/collectors receive telemetry, buffer, batch, and ship it to storage. Account for CPU, memory, network, retries, and backpressure policies when outputs are congested.
- **Storage & queries:** log search by event/service/request_id/trace_id; metrics for time-series and percentile queries; trace viewers for span trees.
- **Alerting:** alert on user-facing symptoms and service objectives, such as sustained error rates and latency; do not alert simply because a single `ERROR` line appeared.

Many teams track the **four golden signals**: **latency, traffic, errors, saturation**. For example, if the HTTP error rate increases, group by route and status code using labels with bounded values; avoid metric labels containing raw URLs with IDs, `request_id`, `user_id`, or `trace_id` because of **cardinality** explosion. Detailed identifying data is usually better suited for access-controlled logs and traces.

Techniques like **trace sampling** reduce stored trace volume, but may mean a specific trace does not appear in the backend. Do not assume every log has a trace you can open. **Log sampling/rate limiting** also reduces noise, but must account for events that must be retained (e.g., records for security investigations under separate policies).

## 9. Incident Investigation Workflow with Logs–Metrics–Traces

Suppose failed requests increase when the system calls `inventory-service`:

1. **Detect with metrics:** inspect error rate, request rate, p95/p99, and when the change started. Distinguish whether errors rose due to traffic, a dependency, or a deployment.
2. **Localize with traces:** pick a trace of a failed request (if available), identify the slow or failing span, parent–child relationships, and the affected endpoint/dependency. A long span does not automatically prove the work inside that span is the culprit; inspect child spans and additional data.
3. **Explain with logs:** filter by the right service, time range, `trace_id` or `request_id`; inspect `event`, `error.type`, `retry_count`, and exception logs. Cross-check nodes because data may arrive at the central collector with delay.
4. **Test hypotheses:** compare before/after deploy windows, active connection counts, timeouts, thread pools, GC, or downstream limits based on actual symptoms. Do not conclude from a single message.
5. **Verify after fixing:** compare error rate, latency histogram, and sample traces/logs under the same load context; ensure user-facing symptoms actually decreased.

If **metrics report errors but you cannot find logs**, check levels/filters, pipelines, timestamps, service labels, redaction, and whether logging happens at the right boundary. If **logs have a `trace_id` but the trace is missing**, check propagation, export, sampling, and backend connectivity. If **a trace is missing a span**, check instrumentation at that step rather than immediately assuming the step did not run.

## 10. Cost, Reliability, and Data Protection

**Performance and noise**
- Avoid building large strings, expensive manual JSON, or serializing sensitive objects when the corresponding log level is disabled; use your API's parameterized logging or supplier.
- Do not log every item in a high-volume loop at `INFO`/`ERROR`. Choose events at boundaries, aggregate counters, and enable `DEBUG` temporarily during investigations.
- Async logging/queues can reduce latency on request threads, but can **block, slow down, or drop logs** when full; understand your backend's backpressure, flush, and shutdown policies.
- Choose retention, per-environment log levels, log volume budgets, and sampling based on investigative value. Monitor the health **of the telemetry pipeline itself** (dropped events, queue fullness, exporter failures).

**Correctness**
- Record event timestamps (wall-clock timestamp) and measure durations with a monotonic clock; clearly define units (`ms`, `µs`, or `ns`).
- Distinguish between handled errors with a fallback and errors returned to the user. Severity must be consistent so alerts do not trigger falsely.
- Avoid logging exceptions at multiple layers; log errors where the handling decision is made and preserve the cause chain.
- Metadata such as service version, deployment, environment, and route template helps investigate regressions across releases.

**Security and privacy**
- Never log passwords, bearer tokens, API keys, session cookies, payment card data, or full request/response bodies by default.
- Redaction must happen before data reaches the console, file, collector, or backend; restrict who can view, export, retain, and delete logs.
- Trace attributes and MDC can also leak data; omitting something from the message string does not mean it is safe.
- Do not use untrusted input as metric label keys or unbounded event names; control both attribute size and cardinality.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Better Practice |
| --- | --- | --- |
| Logging only "Error happened" | Unknown layer, request, or cause | Add event name, service, correlation ID, `error.type`, and appropriate exception |
| Using ERROR for every expected case | Noisy dashboards/alerts | Distinguish operational failures from valid business outcomes |
| Attaching `request_id` to every metric label | Time series explode with request count | Use low-cardinality labels like route template, method, status |
| Using system wall-clock time to measure duration | Inaccurate when the clock shifts | Use `System.nanoTime()` or an appropriate timer |
| Assuming MDC automatically crosses thread pools | Logs lose IDs or pick up another request's ID | Propagate context and clean it up in every scope |
| Assuming a `trace_id` in logs guarantees a trace exists | Investigation breaks due to sampling/export | Verify propagation, sampling, and backend integration |
| Logging entire objects/requests | Data exposure; higher CPU and storage | Select necessary fields, redact sensitive data |
| Trusting a single final log line | Misses swallowed errors and parallel work | Cross-check metrics, spans, logs, and independent signals |

## 12. Self-Check and Practice

**Scenario A:** p99 latency increases while the error rate stays unchanged. Where should you start?  
**Hint:** Check duration histograms and traffic by route, then pick slow traces to see which step is taking time. Individual logs are not enough to see latency distributions.

**Scenario B:** Logs from the controller have `request_id`, but logs inside a `CompletableFuture` do not. Why?  
**Hint:** Thread-bound logging context may not have been propagated to the executor. Use an appropriate propagation mechanism and clean up the context after processing.

**Scenario C:** A metrics dashboard shows a new time series for every `customerId`. What is wrong?  
**Hint:** Customer ID is a high-cardinality label. Change the label to a bounded category for aggregated queries; per-customer details (if permitted) belong in access-controlled, data-protected telemetry.

**Suggested exercise:** Run the JUL program in Section 6; change the logger and handler levels from `INFO` to `FINE` to see the duration record, and observe how the value changes on each run. Then design a stable log schema for an `order_lookup_failed` event and three metrics for observing the endpoint: total requests, total errors, and a response-time histogram. Explain why the three signals complement each other and when you would look up a `trace_id`.

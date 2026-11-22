# Logs, Metrics, and Traces in Java Observability

## 1. Three Signals for Understanding What a System Is Doing

When a Java application is operating normally, users see requests return results. When the system is slow or failing, developers need to know **what event occurred, how large the impact is, and which steps a request went through**. That is the goal of **observability**: using data emitted by the system to understand its internal state and behavior.

The three commonly used signals are **logs, metrics, and traces**:

- **Log:** a record of a specific event at a point in time, such as an authentication failure or a DB connection timeout.
- **Metric:** a measurement aggregated over time or by a set of labels, such as requests/second, error rate, p95 latency, or number of active connections.
- **Trace:** a chain of **spans** describing the path, duration, and causal relationships of a request/workflow across components.

No single signal completely replaces the other two. A metric tells you **“5% of requests are failing”** but usually does not say which requests; a log tells you **“request X was rejected due to error Y”** but does not by itself provide a latency distribution; a trace tells you **“request X spent 720 ms waiting on the database”** but may have been sampled so not every request has a trace.

### 1.1. Quick Comparison Table

| Question | Log | Metric | Trace |
| --- | --- | --- | --- |
| What just happened? | Event details, level, error code | Event count/rate | Event/span in the flow |
| How many requests failed? | Countable if logs are complete | **Very suitable** via counter/rate | Only when trace coverage is sufficient |
| What is the p95/p99 latency? | Not ideal if there is sampling/dropping | **Histogram/timer** is suitable | Per-request detail for traced requests |
| Why is a request slow? | Error/debug messages | Points out affected endpoint/set of instances | **Path and span duration** |
| Need to see the exact input? | Only metadata permitted to be logged | Do not put specific inputs into labels | Only controlled attributes |
| Which service's resource caused the error? | Resource + correlation ID | Resource/low-cardinality labels | `service.name` of each span |
| How many services did a request pass through? | Can be reconstructed with IDs, harder | Insufficient call-graph relationships | **Best suited** with parent/child spans |
| Is an SLO alert being violated? | Not the source of truth when sampling | **Metric** should be the foundation | Traces support investigation |

**Rule of thumb:**
- **Metrics** detect and quantify problems.
- **Traces** localize where time/errors occur along the path.
- **Logs** explain the context, state, and specific decision steps.

This is a collaboration pattern that is usually effective, not a mandatory sequence for every incident. There are errors that only have logs, important system metrics that are not tied to a request, and traces that contain no logs at all.

## 2. A Practical Scenario: Slow Order Placement

Suppose a customer calls `POST /api/orders`. The request passes through the gateway, order service, inventory service, and database:

```text
Client
  |
  v
API Gateway -------- 1 HTTP request -------->
  |
  v
Order Service (HTTP SERVER span)
  |--- validate payload (INTERNAL span)
  |--- Inventory Service (HTTP CLIENT span) ---> Inventory HTTP SERVER span
  |--- JDBC query (DB CLIENT span) ------------> Database
  |
  v
HTTP response
```

When an issue occurs, the three signals might look like this.

**Metric** (numbers are illustrative examples only):

```text
http.server.request.count{route="/api/orders",status="500"} += 1
http.server.duration histogram: one observation = 1.400 s
service CPU utilization = 82%
db connection pool pending = 12
```

**Log**:

```text
ERROR event=order.create_failed route=/api/orders
      error_type=STORAGE_TIMEOUT request_id=req-42
      trace_id=4bf92f3577b34da6a3ce929d0e0e4736
```

**Trace**:

```text
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
  POST /api/orders             1,400 ms
    inventory.validate           60 ms
    db.connection.acquire     1,050 ms
    db.insert                  180 ms
```

Looking at the metrics tells you this is not an isolated request if p95 and pending connections rise together. The trace shows a large **connection-pool wait**; the log shows the error type at the boundary. Spans can be nested or run in parallel, so **do not mechanically sum all durations in a trace**.

The field names above are just an **illustrative model**; not every backend uses the same names. With OpenTelemetry, you should follow the semantic conventions of the chosen instrumentation version.

## 3. Logs: Every Event Has Context and Severity

A log event should answer:
- When the event occurred.
- Which service/instance emitted it.
- What the meaningful event type or message is.
- Severity level (DEBUG/INFO/WARN/ERROR) and outcome.
- Which request/trace/span is associated, if any.
- Enough metadata for diagnosis without **containing secrets or unnecessary personal data**.

An illustrative structured log:

```json
{
  "timestamp": "2026-11-10T10:15:20.123Z",
  "severity": "ERROR",
  "event": "payment.provider_failed",
  "service.name": "orders-service",
  "operation": "authorize_payment",
  "error.type": "REMOTE_TIMEOUT",
  "http.route": "/api/orders",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

This line has custom fields, not standard OTLP JSON. The OpenTelemetry Logs Data Model defines conceptual fields such as `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Attributes`, `Resource`, `TraceId`, and `SpanId`. The encoder and Collector decide how to map the logging framework to that model.

### 3.1. Severity Is Not Impact Rate

An error logged as `ERROR` may affect only a single request; thousands of WARNs may have a much larger impact. Levels help classify events, while **system-wide impact should be measured with metrics** such as error rate, availability, latency, and queue depth.

Do not use `log.error` as the sole way to count failed requests if logs are subject to sampling, dropping, duplication, or multiple loggers recording the same failure.

### 3.2. Exactly One Place Logs the Summary Failure

When a repository throws an exception, the service wraps the error, and the controller handler decides on HTTP 503: all three layers do not need to log the same stack trace at ERROR. Choose the place that **owns the outcome** and attach context such as error code/trace ID; lower layers should only log diagnostics when they have distinct information.

This keeps logs clearer and avoids unnecessary cost. A trace can have multiple spans recording an error status, but each ERROR span should not be interpreted as an independent failure.

### 3.3. Do Not Log Credentials

Do not log raw `Authorization`, `Cookie`, access tokens, refresh tokens, API keys, passwords, query strings containing signed URLs, raw SQL binds, or entire request bodies. **A Trace ID is not an authentication secret**, but it is still metadata that can correlate activity and needs appropriate retention/ACL.

Use the route template `/api/orders/{id}` instead of a raw path containing IDs or recovery codes; technical values also need to pass privacy policies.

## 4. Metrics: Aggregated Measurements and Trends

Metrics typically show current state or volume of work by **series**, identified by a metric name and a set of attributes/labels.

Common types:

| Type | Example | Interpretation |
| --- | --- | --- |
| Counter/monotonic sum | `http.requests.total` | Total requests, only increases within an appropriate lifecycle |
| UpDownCounter | Number of active tasks | Can increase/decrease based on events |
| Gauge | Heap in use, active connections | Value observed at a point in time |
| Histogram | Request duration | Distribution of observations into buckets, count, and sum |
| Timer (Micrometer) | `http.server.requests` | Measures count + total duration and optional histogram/percentiles |

The names above are examples; OTel, Micrometer, Prometheus, and backends have different naming/unit conventions and conversions. When using semantic conventions, adhere to published names and units instead of inventing multiple schemas for the same concept.

### 4.1. Why Not Compute p95 from the Average?

Suppose out of 100 requests, 95 requests take 40 ms and 5 requests take 2,000 ms. The average:

```text
(95 × 40 + 5 × 2000) / 100 = 138 ms
```

An average of 138 ms does not describe the group of users experiencing 2 seconds. Percentiles such as **p50, p95, p99** along with throughput and error rate are useful for tracking tail latency. Percentiles require a distribution/histogram or suitable data and can vary depending on the estimation method.

Do not infer p99 of all traffic solely from sampled slow-request logs. If histograms are configured and supported by the backend, use bucket distributions; remember that client-side percentiles measured per instance **cannot be arbitrarily averaged to get a cluster-wide percentile**.

### 4.2. Computing Rate from a Counter

Cumulative counters are handled by the backend according to temporality/reset rules. For example, if a request counter is 1,000 at 10:00 and 1,120 at 10:01 (same instance, no reset), the request count increased by 120 in 60 seconds, giving an average rate of **2 requests/second**.

If an instance restarts, a raw cumulative counter can drop back to 0; the query system must handle resets. Do not arbitrarily subtract two samples from two different pods without resource identity and reset awareness.

### 4.3. High Cardinality Is a Metrics Architecture Flaw

Wrong:

```text
http_requests_total{user_id="123",request_id="req-42",url="/orders/42"}
```

Labels that vary per user/request create a massive number of series. The consequence is increased memory, storage, index, and query costs; it can slow down or overload the metrics pipeline. Use:

```text
http_requests_total{method="GET",route="/orders/{id}",status="200"}
```

**Low-cardinality attributes** such as method, route template, status class, operation, or service version are suitable for aggregation. `trace_id` and `request_id` belong in logs/traces for investigating individual requests, **not as metric labels**.

### 4.4. Metric Units and Temporality

Duration can be exported in `s` or `ms` depending on the instrument and backend; do not compare 0.25 s with 0.25 ms. OTel metrics distinguish representations such as cumulative/delta temporality; the Collector/backend may need to convert between them.

A histogram metric is an **aggregated measurement**, not a complete list of original requests. Losing logs does not mean counters are lost, and a trace dropped due to sampling does not by itself make histograms inaccurate if the metrics pipeline is still working.

## 5. Traces: Relationships and Timing Between Spans

A **trace** typically represents the processing flow of a single request/workflow. It contains multiple **spans**, each representing a unit of work:

- `name`, `start/end timestamp`, `duration`.
- Shared `trace_id` across the trace.
- Unique `span_id` for each span.
- `parent_span_id` linking parent/child relationships.
- `span.kind` such as SERVER, CLIENT, INTERNAL, PRODUCER, or CONSUMER.
- `attributes`, `events`, `links`, `status`.

Example:

```text
trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  [server span] POST /orders     1.40 s
      ├─ [client span] inventory 0.06 s
      ├─ [client span] JDBC      1.20 s
      │      ├─ connection wait 1.05 s
      │      └─ INSERT          0.15 s
      └─ [internal] build DTO    0.02 s
```

A trace only shows spans that were actually created and exported/retained. **Not seeing a span does not mean the operation did not happen**: instrumentation may not cover it, context may have been lost, the span may have been sampled out, or the exporter may have failed to send it.

### 5.1. Trace ID, Span ID, and Causal Relationships

According to W3C Trace Context, an illustrative `traceparent`:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

The parts are version, trace ID (32 hex digits), parent ID (16 hex digits), and trace flags. A Trace ID must not be all zeros; a Span ID must not be all zeros either. When service B creates a child span, it gets a **new span ID**, usually inherits the trace ID, and attaches the parent relationship via propagation.

The sampled bit in trace flags is a signal in the context, **not a guarantee that the trace has been stored in the backend**. The backend might not receive it due to exporter failures, retention, or different sampling policies.

### 5.2. Span Duration Differs from Total Request Time

A DB span might be 600 ms inside a 900 ms HTTP span; do not add them together to get 1,500 ms. Nested spans coexist on the timeline; parallel spans can also overlap.

A CLIENT span and a SERVER span across two services can have skewed start/system times due to clock skew. Use parent/child relationships and causal markers to interpret them, not just sorting timestamps across multiple machines.

### 5.3. Span Events Do Not Replace All Application Logs

A span event describes a timestamped milestone within an operation. It is suitable for marking `"cache.miss"` or `"retry.scheduled"` inside the relevant span, but it does not mean every DEBUG log should be turned into a span event. Logs and span events have different retention, indexing, sampling, and query mechanisms.

## 6. Correlation: What Connects Logs, Metrics, and Traces?

There are three main correlation axes:

1. **Context:** `trace_id` and `span_id` link a log to an active span.
2. **Resource:** `service.name`, service version, environment, instance/pod, and host identify the source emitting all three signals.
3. **Time + dimensions:** incident time window, route template, method, status, operation, and business domain help select related metrics/logs/traces.

An investigation workflow:
- Metrics indicate `GET /orders/{id}` in the orders service has high p95.
- The dashboard opens a related trace/exemplar, or queries traces by service + route + time.
- Inside the trace, the DB span accounts for most of the duration.
- Use `trace_id`/`span_id` to find WARN logs for connection pool wait or timeout.
- Check DB pool metrics to see whether the issue is widespread or isolated to one request.

### 6.1. A Trace ID in a Log Does Not Mean the Trace Exists in the Backend

You might have a log:

```text
WARN ... trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7
```

yet searching for the trace finds nothing. Reasons include:
- The sampler dropped the trace.
- The Collector/exporter/transport is not working.
- Backend trace retention differs from log retention.
- The UI/query is filtering the wrong environment/tenant or service.
- Instrumentation injects IDs into MDC, but the exporter is not enabled.
- The span was not ended/flushed, or the SDK was shut down before sending.

Conversely, a trace may appear completely while logs lack trace IDs if the logger does not receive context, MDC injection is not enabled, the log occurred outside an active span, or the encoder does not print those fields. **Both directions must be verified independently**.

### 6.2. Exemplars Connect Metrics to Traces

In the OTel Metrics Data Model, an **exemplar** is an observation kept alongside a metric point to link the metric value to a trace context when available. For example, a duration histogram has an exemplar carrying `trace_id` and `span_id` for a sample. Dashboards supporting exemplars can take an operator from a latency bucket directly to a specific trace.

However, an exemplar:
- May not exist depending on configuration/instrumentation/backend.
- Does not store every request and is not a complete list of traces.
- Must not be used to “fix” p95 by looking at just a few samples.
- Can lose its link if the trace was sampled/dropped or has expired past retention.

Use exemplars to **investigate a representative example**, not as a replacement for aggregate histograms.

## 7. Runnable Java 17+: Simulating All Three Signals for One Request

The following example **uses only the JDK** and runs with `javac`/`java` without needing a Collector or the OpenTelemetry SDK. It simulates a request with an HTTP span and a DB span, a count + sum duration metric, and an application log tagged with trace/span IDs.

**This is an educational model**, not a real OpenTelemetry exporter. The goal is to understand data shapes and how correlation works. The IDs and timestamps are synthetic test fixtures; production applications must let instrumentation generate trace IDs and measure clocks properly.

Create `ThreeSignalsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ThreeSignalsDemo {
    private static final String TRACE_ID =
            "4bf92f3577b34da6a3ce929d0e0e4736";
    private static final String SERVER_SPAN_ID =
            "00f067aa0ba902b7";
    private static final String DB_SPAN_ID =
            "b7ad6b7169203331";

    private static final class Capture extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> lines() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.three.signals");
        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);
        logger.addHandler(capture);

        try {
            // Fake monotonic time (nanoseconds), so output is deterministic.
            long httpStart = 1_000_000_000L;
            long dbStart = 1_002_000_000L;
            long dbEnd = 1_006_000_000L;
            long httpEnd = 1_013_000_000L;

            long httpNanos = httpEnd - httpStart;
            long dbNanos = dbEnd - dbStart;
            int requestCount = 1;

            logger.info("event=db.lookup.completed operation=find_order "
                    + "trace_id=" + TRACE_ID
                    + " span_id=" + DB_SPAN_ID);

            System.out.printf(Locale.ROOT,
                    "METRIC requests_total=%d duration_sum_ms=%.3f%n",
                    requestCount, httpNanos / 1_000_000.0);

            System.out.printf(Locale.ROOT,
                    "TRACE name=http.server span_id=%s "
                    + "parent=none duration_ms=%.3f%n",
                    SERVER_SPAN_ID, httpNanos / 1_000_000.0);

            System.out.printf(Locale.ROOT,
                    "TRACE name=db.query span_id=%s "
                    + "parent=%s duration_ms=%.3f%n",
                    DB_SPAN_ID, SERVER_SPAN_ID,
                    dbNanos / 1_000_000.0);

            for (String line : capture.lines()) {
                System.out.println("LOG " + line);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Run on JDK 17+:

```bash
javac --release 17 ThreeSignalsDemo.java
java ThreeSignalsDemo
```

Exact stdout:

```text
METRIC requests_total=1 duration_sum_ms=13.000
TRACE name=http.server span_id=00f067aa0ba902b7 parent=none duration_ms=13.000
TRACE name=db.query span_id=b7ad6b7169203331 parent=00f067aa0ba902b7 duration_ms=4.000
LOG INFO event=db.lookup.completed operation=find_order trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331
```

Explanation:
- `requests_total=1` and total duration 13 ms are an **illustrative aggregated metric for one observation**, not enough to compute p95.
- The HTTP span lasts from 1,000,000,000 to 1,013,000,000 ns: **13.000 ms**.
- The DB span lasts from 1,002,000,000 to 1,006,000,000 ns: **4.000 ms** and has the HTTP span as its parent.
- The `db.lookup.completed` log has the same trace ID and uses the DB span's span ID so it can be linked to the data query part.
- `Capture` avoids the default JUL console handler and does not add timestamps automatically; output is independent of machine speed and locale.
- There is no W3C propagation, remote call, real histogram, SDK, or exporter in this example. Lines labeled METRIC/TRACE/LOG are **simulated stdout**, not real OTLP exports.

In real applications, elapsed time uses `System.nanoTime()` (or the tracing/metrics library's clock) instead of fixed numbers. To produce real telemetry, use the OpenTelemetry API/SDK, Micrometer, the Java agent, or appropriate instrumentation as covered in the following sections.

## 8. OpenTelemetry Architecture for Java

A common architecture:

```text
Java application
  ├─ SLF4J/Logback/Log4j2 ------> App logs ----\
  ├─ OTel Java agent / API -----> Traces --------+--> OTel Collector
  ├─ Micrometer/OTel Meter -----> Metrics -------/         |
  └─ W3C context propagation                           processors
                                                          |
                                                       exporters
                                                          |
                                         Logs / Metrics / Trace backends
```

This is a conceptual diagram. Logs can be read by the Collector from stdout/files **or** converted into OTel LogRecords via a compatible logging bridge/appender. You do not always need both paths for the same event: **collecting both stdout and OTLP logs for the same event into one backend can create duplicates**.

### 8.1. Roles of the Components

- **Logging framework:** SLF4J is the façade; Logback, Log4j 2, or JUL writes events according to configuration.
- **OpenTelemetry API:** provides interfaces for spans, meters, and log context; adding it does not mean an exporter is configured.
- **OpenTelemetry SDK:** collects/processes/exports signals according to configuration, sampling, and processors.
- **Java agent (zero-code):** automatically instruments supported libraries/frameworks (HTTP server/client, JDBC, etc.) without modifying business code directly.
- **Micrometer:** a metrics/observation API widely used in Spring; observations can be linked to tracing when handlers/bridges are configured.
- **Collector:** receives telemetry via receivers, processes it with processors, and sends it to exporters/backends.
- **Backend:** indexes/queries logs, time-series metrics, trace stores, and correlation UIs.

**Do not confuse “added the API dependency” with “telemetry is in the dashboard”.** You need instrumentation, an SDK/provider, an export pipeline, and a backend actually receiving data. Conversely, the agent can create spans automatically without needing manual API calls in every method.

### 8.2. Java Agent: Local Configuration Example

After downloading the **Java agent JAR** from an official release and having a built Java application, you can run it in a Bash-like test environment:

```bash
export OTEL_SERVICE_NAME="orders-service"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=dev,service.version=1.0.0"

export OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:4318"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="otlp"

java -javaagent:/path/to/opentelemetry-javaagent.jar -jar app.jar
```

This is an **integration command requiring the agent JAR, app.jar, and a running OTLP receiver**. The JAR path is illustrative; replace it with the real path. This configuration is only suitable for **local/test without secrets**: the HTTP endpoint has no TLS/auth and should not be exposed publicly in production.

With Java agent 2.x, the default OTLP protocol of the agent is usually `http/protobuf`; the example sets it explicitly to avoid confusing port `4318` (HTTP) with `4317` (gRPC). Depending on the version and instrumentation, log capture from frameworks may require separate configuration. **Enabling `OTEL_LOGS_EXPORTER=otlp` does not prove every Logback line is bridged/exported.** Check supported libraries, logger integration, the pipeline, and actual results.

Do not enable multiple independent instrumentations creating the same HTTP server span or metric simultaneously without understanding duplicates. If Spring Boot uses Micrometer observation, check the OTel agent and bridge before manually instrumenting the same scope on top.

## 9. OpenTelemetry Collector: Three Separate Pipelines

Here is an **example Collector configuration for local development**, using an OTLP receiver and `debug` exporter to inspect telemetry structure:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "127.0.0.1:4317"
      http:
        endpoint: "127.0.0.1:4318"

processors:
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

This diagram shows **separate pipeline names** `traces`, `metrics`, and `logs`. A single OTLP receiver can feed all three, but **that does not mean they are the same signal**. Production requires auth/TLS, memory limits, retry/batching, resource attribution, backend exporters, high availability, monitoring, and privacy policies.

The `debug` exporter can print sensitive telemetry into the Collector's own logs; use it only in safe environments with synthetic data. If the Collector runs in a separate container, `127.0.0.1` inside that container is not the loopback of the host or app container; adjust network endpoints to match the actual topology, and avoid exposing `0.0.0.0` publicly without controls.

### 9.1. Logs Pipeline: Choose One Primary Source per Event

There are two common paths:
- **stdout/file → filelog/agent receiver → backend**.
- **logging bridge/SDK → OTLP receiver → backend**.

Both are valid. However, if the same event reaches the same backend through both paths without a fan-out/dedup policy, the dashboard may show two records. Having a service write one copy to console and one to a file **is not automatically wrong**; the error happens when the pipeline ingests those two copies as two logical events unintentionally.

### 9.2. Batching, Retries, and Observation Time

Collector processors/exporters use batching, buffering, and retries. A log emitted earlier may arrive at the backend after another log; `Timestamp` (source time) and `ObservedTimestamp` (observed time) can differ. Traces and metrics also have their own export delays. Do not use the arrival order in the dashboard to infer absolute execution order across multiple services.

## 10. Linking Application Logs with Active Trace Context

In applications using SLF4J/Logback or Log4j 2, a common approach is to let instrumentation populate `trace_id` and `span_id` into the logging context/MDC when an active span exists, and then have the encoder output them in logs.

An illustrative **Logback** pattern:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
      trace_id=%X{trace_id:-} span_id=%X{span_id:-}
      %logger{36} - %msg%n</pattern>
</encoder>
```

This is an **XML fragment inside an already declared appender**, not a complete `logback.xml` file. In real projects, the pattern is usually written on a single line to avoid unwanted newline whitespace. `%X{trace_id:-}`/`%X{span_id:-}` read from MDC; they do not generate IDs by themselves.

**Preconditions:** logging instrumentation must be attaching context to MDC under the corresponding keys, the application must have an active span, and MDC must be handled properly. Otherwise, the fields will appear empty. Simply adding the pattern **does not give the system distributed tracing**.

### 10.1. Manually Retrieving Trace Context via the OpenTelemetry API

When a project already has the `io.opentelemetry:opentelemetry-api` dependency and the SDK/agent creates context, you can retrieve the active span:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

// Fragment inside a method that has an SLF4J Logger log.
SpanContext context = Span.current().getSpanContext();

if (context.isValid()) {
    log.info("event=order.lookup.completed trace_id={} span_id={}",
            context.getTraceId(), context.getSpanId());
} else {
    log.info("event=order.lookup.completed trace_context=absent");
}
```

This is an **integration snippet** and will not run standalone without the OpenTelemetry API and a logger. `Span.current()` only returns the active context for the current thread/scope; if uninstrumented or if context was lost, `isValid()` may be false.

If the logger already injects trace/span IDs via MDC or a structured encoder, **there is no need to manually embed the IDs into the message again**: doing so duplicates data in the record and increases cost. Prefer a single standard configuration across the project; use manual IDs only when genuinely needed and tested.

### 10.2. Context Propagation Across Threads and Services

W3C Trace Context propagates span context over HTTP headers; the SDK/instrumentation performs **inject/extract** at network boundaries. With `CompletableFuture`, executors, Reactor, message queues, callbacks, and virtual threads, appropriate instrumentation/context propagation is required.

A common bug: the request thread has a trace ID, but a worker thread continues execution and its logs lose the trace ID. Do not fix this by copying raw `Authorization` headers or putting tokens into baggage. Baggage can propagate across service boundaries; **do not store secrets or unnecessary PII in it**.

With async operations, a span can end before the worker runs if code only opens the scope around submission rather than around completion. When designing custom spans, tie the lifecycle to the actual unit of work, close the scope in `finally`, call `end()` on the span when the operation finishes, and test exception/cancellation branches.

## 11. Metrics + Tracing in Spring Boot/Micrometer

Spring Boot uses Micrometer to collect metrics and Micrometer Observation to create a single instrumentation point that can serve both metrics and tracing when appropriate handlers are registered.

An illustrative snippet, **requiring Micrometer Observation and a configured ObservationRegistry**:

```java
import io.micrometer.observation.Observation;

// Fragment inside a service that has observationRegistry, repository, and id.
Observation observation =
        Observation.createNotStarted("order.lookup", observationRegistry)
                .lowCardinalityKeyValue("operation", "find_by_id")
                .start();

try (Observation.Scope scope = observation.openScope()) {
    repository.findById(id);
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
```

Meaning:
- `Observation` defines a unit of work.
- Low-cardinality key `operation=find_by_id` is suitable for metrics.
- `openScope()` attaches context to the current scope so handlers can use it.
- `error(ex)` reports the error to the observation; the exception is still rethrown.
- `stop()` ends the unit of work, even when an error occurs.

**Merely creating an ObservationRegistry does not guarantee spans/metrics will be produced.** You need ObservationHandlers, a MeterRegistry/tracing bridge, and an actual exporter; metric/span names, conventions, and attributes depend on Spring/Micrometer configuration. If the framework already instruments HTTP/JDBC, do not wrap the same operation in a duplicate observation just to “have all three signals”.

### 11.1. Timers/Histograms Reveal Tail Latency

With a Micrometer timer, statistics include count and total time, plus optional histograms/percentiles if configured. A timer is not a trace and does not store all raw request durations. Calling `timer.record(...)` does not automatically attach a trace ID to every observation unless the system has appropriate exemplar/context integration.

A good instrumentation pattern:
- `http.server.requests`/HTTP server metrics to evaluate SLOs.
- Custom observations for business operations that truly need separate visibility.
- Structured error log events only when there is something to investigate.
- Trace spans for service-to-service paths and critical operations.

Do not use `user_id`, `request_id`, or `trace_id` as low-cardinality metric tags.

## 12. Sampling: Why Are There Logs Without Traces?

Trace sampling reduces volume and cost, but can cause a log with a trace ID to have no corresponding trace found.

Sampling approaches:
- **Head sampling:** decides early, usually near the creation of the root trace.
- **Tail sampling:** the Collector or backend decides after gathering enough spans/traces within a time window, e.g., keeping error/slow traces by policy.
- **Adaptive sampling:** rates are adjusted based on traffic/conditions depending on the system.

These are general concepts; concrete configuration depends on the library/backend and must consider memory, latency, and consistency of traces traversing multiple collectors.

**Do not equate trace sampling with log sampling and metric aggregation:**
- A 10% sampled trace rate can still keep metric histograms for all requests, provided metrics instrumentation operates independently.
- Logs can still be written when a trace is not exported, depending on log instrumentation/pipeline.
- Blindly sampling logs can drop rare ERRORs; use policies based on severity/event.
- Metric points can be dropped due to separate pipeline errors; traces working does not prove metrics are complete.

A trace ID in a log helps correlation **when the trace is accessible**, not as a guarantee that the trace can be found.

### 12.1. Exemplars and Sampling

A metric exemplar can point to a trace sample, but not every observation has an exemplar and not every exemplar still has its trace in the backend. If the backend supports it, operators can pick an exemplar from a slow bucket and open the related trace.

For alerting, still prioritize histograms/rates and SLOs. A single trace exemplar is not sufficient statistical evidence.

## 13. Timestamps and Clocks: The Three Signals Do Not Always Appear Together

There are multiple timestamps:
- **Event timestamp:** when the log event occurred at the source.
- **Observed timestamp:** when the Collector/receiver observed the event.
- **Span start/end:** when the operation started/ended, possibly measured on different services.
- **Metric observation timestamp / collection interval:** when a measurement point was recorded or exported in aggregate.
- **Ingestion time:** when the backend stored and indexed it.

A log may have `Timestamp=10:00:00.100` but only be ingested at `10:00:01.000` due to queues/retries. Metric collection may update dashboards a few seconds later. Trace exporters also batch separately. **Different display times do not automatically mean the system executed out of order.**

Clock skew between hosts can invert timestamps even when the HTTP request/response relationship is valid. Use W3C parent/child context and monotonic elapsed clocks within their appropriate scope to explain durations. `System.nanoTime()` is for measuring elapsed differences within the same JVM, not as an absolute Unix timestamp across JVMs.

In OTel Logs, `Timestamp` and `ObservedTimestamp` are two distinct fields. Do not strip source timestamps to “put the whole system on one clock” without understanding what diagnostic value is lost.

## 14. Cost, Cardinality, and Data Protection

The three signals have different cost drivers:

| Signal | Cost Drivers | Recommended Optimizations |
| --- | --- | --- |
| Logs | Record count, size, indexing, retention | Structured events, levels, policy-based sampling, avoid duplicates |
| Metrics | Time series count by labels, bucket count, scrape/export frequency | Low-cardinality dimensions, sensible histograms |
| Traces | Trace/span count, attributes, events, sampling, retention | Instrument meaningful operations; sampling and attribute limits |
| Collector | CPU/memory queues, batch/retry, exporters | Bounded pipelines, monitoring, backpressure, and SLOs |

Data has varying sensitivity:
- **Logs:** messages or exceptions can contain PII, SQL binds, or tokens.
- **Metrics:** labels can accidentally contain raw user IDs/URLs, causing both privacy and cardinality risks.
- **Traces:** span attributes, events, baggage, HTTP headers, or DB queries can contain secrets.

Do not log raw `Authorization`, `Cookie`, passwords, access tokens, refresh tokens, client secrets, private keys, signed URLs/queries, or raw SQL bind values. Avoid putting such data into span attributes, baggage, or metric tags; sanitizers in the Collector are only a secondary safeguard **after data has already left the JVM**.

Apply least privilege, appropriate retention, TLS/auth between exporters and backends, and secret scanning on synthetic fixtures. A log may be copied to alerts/tickets/backups, so deleting it from the app console does not remove copies stored elsewhere.

### 14.1. Cardinality Should Be Controlled at the Right Signal

`request_id` is suitable for **log correlation**, but not as a metric label. In traces, high-cardinality attributes can sometimes help locate a specific request, though cost/privacy must still be weighed; **this does not mean banning every ID from traces**. Policies should differ by instrument, backend, sampling, and purpose.

`http.route` should be a route template; a raw URI with an order ID can have a nearly unbounded set of values. For HTTP metrics, method + route + status are usually sufficient for aggregation.

## 15. Incident Example: p95 Spikes, Finding Root Cause with Three Signals

Context: `orders-service` suddenly sees p95 latency jump from 180 ms to 1,600 ms after a deployment.

### Step 1 — Metric: Confirm the Scope

Check:
- `http.server.requests` and p95/p99 by route.
- Error rate and request rate (was there a traffic spike?).
- CPU, GC, heap, thread pools.
- DB pool active/pending/acquire time.
- Different service versions/pods to compare before and after.

If only one route is affected, narrow down quickly. If the whole cluster spikes, shared infrastructure may be bottlenecked.

### Step 2 — Trace: Inspect the Critical Path

Select traces from the affected route and incident window, prioritizing slow/error traces present in the backend:
- How long is the HTTP server span?
- How long is the DB client span?
- Are there outbound HTTP retries, queue waits, or lock contention?
- Are spans running in parallel or nested?
- Are there missing spans due to uninstrumented code?

Do not sum durations of all spans; find the segment on the **critical path**.

### Step 3 — Logs: Find Specific Context

Take the trace ID from the span and query logs:
- `event=storage.connection_wait` or `event=repository.slow_operation`.
- Error type and retry attempt.
- Relevant request/operation ID.
- Logs indicating a fallback was taken or an exception was handled.

If logs lack a trace ID, check MDC/active context; searching by time + service + route is only an approximation and may return many unrelated requests.

### Step 4 — Action and Verification

Suppose high DB connection pool pending counts are found after the release; check for connection leaks, excessive concurrency, slow queries, or pool/DB limits. Fix the root cause, then verify **p95 metric drops, trace DB wait drops, and log warnings drop**. Do not merely turn off the WARN logger to make alerts disappear.

## 16. When One of the Three Signals Does Not Appear

### 16.1. Logs Exist, but No Traces

Check:
1. Was the Java agent/API/SDK actually initialized?
2. Was the span created, active, and ended?
3. Did head/tail sampling drop the trace?
4. Does the W3C propagator inject/extract across HTTP/messaging?
5. Are the OTLP exporter and Collector traces pipeline working?
6. Are the backend trace index/tenant/retention settings correct?
7. Do clock/timestamp/search filters put the trace outside the search window?

Having `trace_id` in a log only proves it was written at some layer, not that the Collector received the span.

### 16.2. Traces Exist, but Logs Lack `trace_id`

Check:
1. Was the log emitted inside an active span/scope?
2. Does the logger backend have proper MDC/context injection?
3. Does the encoder output `trace_id` and `span_id` correctly?
4. When `CompletableFuture`/Reactor runs async, is context propagated?
5. Are logs emitted early before span creation or after the span has ended?
6. Do logs come only from a filelog receiver whose parser does not recognize the ID fields?

Do not “fix” this by pulling IDs from another request's thread-local or from unvalidated client-supplied headers.

### 16.3. Traces/Logs Exist, but Metrics Are Zero

Check:
- Are a MeterProvider/MeterRegistry and metric exporter configured?
- Are metric instruments actually being updated, or only registered?
- Is the collection interval too long so data has not been exported yet?
- Does the Collector metrics pipeline have matching receivers/exporters?
- Are units/temporality misinterpreted by the backend?
- Does the dashboard query use the right service/route labels?
- Did cardinality limits drop series or did labels change?

**The three pipelines can fail independently.** Do not assume “OTel is enabled” means every signal definitely has data.

## 17. Common Implementation Mistakes

**Mistake 1 — believing Logback will generate traces automatically:** SLF4J/Logback writes logs; it does not produce distributed spans on its own; instrumentation/context is required.

**Mistake 2 — using `trace_id` as a metric label:** explodes cardinality to the point where the metrics backend becomes hard to operate.

**Mistake 3 — looking only at logs to compute p99:** log sampling/dropping/duplication makes the observation set incomplete or skewed; use histogram/timer metrics.

**Mistake 4 — creating a span for every getter/setter:** huge volume, hard-to-read traces; choose units of work that actually provide value.

**Mistake 5 — using one trace for an entire batch of unrelated jobs:** can create giant traces and wrong relationships; distinguish parent/child vs. span links according to workflow semantics.

**Mistake 6 — losing context on thread switches:** async worker logs miss trace IDs; instrumentation/context propagation must cover the full lifecycle.

**Mistake 7 — logging tokens into MDC/baggage:** leaks secrets across loggers/traces/services. Use a safe request ID instead.

**Mistake 8 — sending both stdout/filelog and direct OTLP logs:** the same event is ingested twice into the same backend if unintentional.

**Mistake 9 — attaching both the OTel agent and manual instrumentation to the same HTTP server scope:** can duplicate spans/metrics; check the instrumentation map.

**Mistake 10 — using default/unstable `service.name`:** makes logs, metrics, and traces hard to join; configure resources consistently.

**Mistake 11 — treating sampled traces as statistical data for all traffic:** sampling can be biased; use metrics specifically for SLOs and rates.

**Mistake 12 — comparing timestamps across services as an absolute clock:** clock skew and queueing can invert order; inspect causal span relationships.

**Mistake 13 — logging errors at every layer:** one failure produces many redundant ERROR logs and span events; have one place own the summary log.

**Mistake 14 — using the Collector debug exporter in production:** can print sensitive telemetry into the Collector's own logs and increase volume.

**Mistake 15 — measuring “success” right before transaction commit:** logs or success spans can be wrong if the commit subsequently fails. For durable auditing, use outbox/transactional storage.

## 18. QA Matrix for Java Observability

| Test | What to Verify |
| --- | --- |
| Synchronous HTTP 200 | Request metric exists, one server span when sampled, logs follow policy |
| HTTP 500 JDBC error | Error metrics reflect outcome, trace/span status is appropriate, error log has error type |
| One request across 2 services | Trace ID is propagated, service B creates a new span ID |
| Log inside active span | Log contains trace/span ID per schema if configured |
| Log outside active span | No fabricated IDs; event remains valid |
| Async/CompletableFuture | Context is propagated, span lifecycle follows completion |
| Head sampling drops trace | Metrics still update; log behavior follows independent policy |
| Collector/exporter failure | Diagnostics/queue retry exist; loss is detectable rather than silent |
| Exemplar support | Metric links to trace when actually present; do not assume every sample has one |
| Logback + OTLP/filelog | Same event is not ingested twice into one index |
| HTTP route containing ID | Metrics use route template; do not use raw URI |
| Exception message with fake token | Canary secret is not leaked into log/span/metric attributes |
| High-cardinality input | Metric label policy blocks raw user/request/token |
| Service restart | Counter resets and telemetry shutdown/export are handled properly |
| Clock skew | Causal trace and source timestamp are not misinterpreted |
| Spring Observation + OTel agent | No duplicate instrumentation for the same operation |
| Traffic spike | No metric loss from series explosion; bounded export pipeline |
| Dashboard correlation | From route metric → trace → log by ID/resource and time window |

Use a synthetic trace ID in unit tests to assert formatting, but for integration tests let the tracer/agent actually generate IDs and propagate them. When testing production-like setups, do not use real credentials and do not expose the debug exporter to the network.

## 19. Repeatable Implementation Workflow

1. **Define goals:** availability, error rate, p95 latency, DB pool wait, queue delay—which business operations need visibility?
2. **Establish resource identity:** `service.name`, environment, version, instance; align across all three signals.
3. **Choose instrumentation approach:** Java agent, Spring/Micrometer Observation, or manual API for remaining gaps.
4. **Define log schema:** event code, severity, error type, route template, approved request/trace/span IDs.
5. **Configure metrics:** counters/gauges/histograms with low-cardinality labels and clear units.
6. **Configure traces:** span names/kinds, parent relationships, W3C propagation, sensible sampling.
7. **Set up exporters/Collector:** OTLP protocol, receivers, processors, separate pipelines, TLS/auth, buffering/retries.
8. **Verify log path:** stdout/file shipper or OTLP bridge, avoiding double-ingestion of the same event.
9. **Test correlation:** from a test request, find logs by trace ID, verify spans and metric increments.
10. **Test failure/async/restart:** context loss, timeouts, queue-full, retries, and shutdown.
11. **Control cost/privacy:** cardinality, sampling, retention, access control, secret redaction at the source.
12. **Operate by signals:** alert on metrics/SLOs, drill down with traces, diagnose details with logs.

**Conclusion:** Logs answer **“what happened?”**, Metrics answer **“how much/often is it happening, and what is the trend?”**, and Traces answer **“where in the processing journey did it happen?”**. Effective observability is not about emitting as much data as possible, but designing **three signals that are consistent in service identity, time, context, and privacy** so an incident can be detected, localized, and explained with evidence.

## Official References

- [OpenTelemetry – Signals: Logs, Metrics, Traces](https://opentelemetry.io/docs/concepts/signals/).
- [OpenTelemetry – Java overview](https://opentelemetry.io/docs/languages/java/).
- [OpenTelemetry – Java Agent zero-code instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/).
- [OpenTelemetry – Java Agent configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/).
- [OpenTelemetry – Logs Data Model and correlation](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [OpenTelemetry – Log Correlation](https://opentelemetry.io/docs/specs/otel/logs/).
- [OpenTelemetry – Metrics Data Model and exemplars](https://opentelemetry.io/docs/specs/otel/metrics/data-model/).
- [OpenTelemetry – Trace API, SpanContext, and propagation](https://opentelemetry.io/docs/specs/otel/trace/api/).
- [OpenTelemetry – Propagators API](https://opentelemetry.io/docs/specs/otel/context/api-propagators/).
- [OpenTelemetry – Collector processors](https://opentelemetry.io/docs/collector/components/processor/).
- [OpenTelemetry – Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/).
- [Micrometer – Observation handlers](https://docs.micrometer.io/micrometer/reference/observation/components.html).
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
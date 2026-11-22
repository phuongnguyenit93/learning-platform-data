# Logs and Dashboards in Observability for Java Applications

## 1. Goal: Turning Logs into Actionable Operational Information

**Logs and dashboards** are two different layers in an **Observability** system:

- **Logs** record specific events: timestamp, source, severity level, operation, outcome, error code, and context for investigation.
- **Dashboards** organize queries, charts, tables, and investigation links so operators can see service health over a period of time.
- **Observability** is the ability to understand the internal state of a system based on external signals, typically combining **logs, metrics, and traces**. A good-looking dashboard with missing data, wrong semantics, or no way to correlate incidents is not good observability.

For example, when an operations team sees HTTP 5xx responses increasing, they usually want to answer in sequence:
1. Which service and environment are experiencing the issue?
2. Since when did the error rate, throughput, and latency change?
3. Are errors concentrated on a specific route, deployment version, instance, or event group?
4. Are there detailed logs, stack traces, and trace IDs to trace specific requests?
5. Is the data on the dashboard complete, or is the logging pipeline lagging, sampling, or dropping events?

This lesson in the **Observability** section uses **Java 17+, JUL/SLF4J, and Grafana Loki/LogQL** as examples. The core concepts also apply to Elasticsearch/Kibana, OpenSearch Dashboards, or other logging platforms, though **query syntax and system capabilities differ**.

By the end of this lesson, you will be able to:
- Design an event log with a stable schema that is queryable without redundant data.
- Understand the pipeline from a Java logger to collector/storage and dashboards.
- Choose between Loki stream labels versus parsed fields/structured metadata to avoid high cardinality.
- Write LogQL queries for log tables, volume, rate, 5xx counts, errors by route, and p95 latency.
- Build operational panels and correlate logs with traces/metrics.
- Write and run a Java 17+ example that emits controlled events, computes a small summary, and verifies no secrets are leaked.
- Evaluate sampling, ingestion errors, retention, access permissions, and alert accuracy.

## 2. Data Flow: From Logger Calls to Dashboards

A reference architecture:

```text
Java service (JUL / SLF4J + Logback / Log4j 2)
  |
  | logger.info("event=...") or structured JSON
  v
Console / stdout / rolling file / OTLP exporter
  |
  v
Agent / collector / pipeline (parse, enrich, batch, redact)
  |
  v
Log backend (e.g. Grafana Loki)
  |
  v
Grafana Explore / dashboard / alert query
  |
  +----> drill-down via request_id / trace_id -> trace backend
  |
  +----> compare with metrics in Prometheus/OpenTelemetry
```

**Java applications do not send data directly to the Grafana UI.** Grafana typically queries a *data source* such as Loki. The application layer emits events, an agent/collector may transport and normalize them, the backend stores/indexes them appropriately, and the dashboard executes queries.

Clear definition of responsibilities:
- **Application:** chooses meaningful events/fields; never logs passwords, tokens, or sensitive raw payloads.
- **Logging API/backend:** decides levels, layouts, formats, encoders, appenders, buffering, and sync/async behavior.
- **Collector:** receives, attaches resource metadata, performs additional filtering/redaction, forwards data, and retries/batches according to policy.
- **Storage:** handles retention, querying/indexing, multi-tenancy, quotas, and access permissions.
- **Dashboard:** focuses on operational questions, presenting panels with units, time windows, data sources, and investigation links.
- **Alerting:** detects critical conditions on reliable signals, with thresholds, pending durations, routing, and runbooks.

A log event generated in the JVM might **never reach the dashboard** if blocked by a logger level/filter, a full queue, a failing appender, a lagging agent, a rate-limited collector, an unindexed backend, or insufficient query permissions. Therefore, you must monitor the **logging pipeline** itself, not just the application.

## 3. Logs, Metrics, Traces: What Does Each Answer?

| Signal | Best-Suited Question | Strengths | Limitations |
| --- | --- | --- | --- |
| Logs | “Which error, in which request, with what details?” | Rich context, pinpoints specific root causes | High cost, can be missing/sampled/dropped |
| Metrics | “How are RPS, error rate, and p95 changing?” | Optimized for quantitative aggregation and alerting | Lacks per-event detail |
| Traces | “Which services/spans did the request pass through?” | Connects distributed flows, latency waterfalls | Usually sampled, requires propagation |
| Dashboard | “What is abnormal right now and in service trends?” | Operational window combining multiple signals | Cannot fix missing or incorrect source data |

**Do not use logs to replace all metrics.** For example, to monitor a 99.9% SLO, metrics/histograms from an appropriate instrumentation point are usually more reliable than counting log lines, especially if success logs are sampled. Logs help investigate the specific anomalous requests behind a metric alert.

An effective investigation flow typically looks like this:

```text
Metric: 5xx increases -> Dashboard: route /orders/{id} degrades
         |
         v
Explore: log event=order_lookup_failed by time range
         |
         v
Trace ID -> distributed trace -> database timeout span
         |
         v
Identify deployment / dependency / saturation changes
```

Correlation IDs/trace IDs build the bridge. However, IDs do not replace verifying the actual timestamp, service, route, error code, or state.

## 4. Designing Event Logs for Dashboard Readability

A log record should have a **stable schema**. Example in JSON format:

```json
{
  "timestamp": "2026-11-10T03:15:30Z",
  "severity": "ERROR",
  "service": "orders-api",
  "environment": "prod",
  "event": "http_request",
  "route": "/orders/{id}",
  "status": 503,
  "duration_ms": 75,
  "error_type": "UPSTREAM_TIMEOUT",
  "correlation_id": "req_7c9"
}
```

This is a hypothetical example, not an event captured from production.

### 4.1. Field Groups to Consider

| Group | Fields | Purpose |
| --- | --- | --- |
| Time | `timestamp`, ingestion/observed timestamp | Determine when the event occurred and delay to backend |
| Source | `service`, `environment`, `instance`, `deployment_version` | Identify service, environment, and deployment changes |
| Severity | `severity` / `level` | Filter INFO/WARN/ERROR per backend contract |
| Event type | `event`, `error_type` | Stable querying instead of searching free-form text messages |
| Request | `method`, `route`, `status`, `duration_ms` | Build tables/error rates and latency analysis |
| Correlation | `request_id`/`correlation_id`, `trace_id`, `span_id` | Pivot from overview panels to specific events/traces |
| Messaging | `topic`, `partition`, `offset`, `consumer_group` | When using Kafka, locate the record and consumer |
| Reliability | `sampling_policy`, `log_source` when applicable | Explain discrepancies between log count and actual traffic |

Timestamp fields should have an explicit timezone; the occurrence time (`Timestamp`) can differ from when the collector observed it (`ObservedTimestamp`). The OpenTelemetry Logs Data Model also includes `SeverityText`/`SeverityNumber`, `Body`, `Resource`, `Attributes`, `TraceId`, `SpanId`, and `EventName`. Not every Logback layout generates all of these fields automatically; you need an encoder/OTel integration and actual schema mapping.

### 4.2. Names and Types Must Be Consistent

Avoid situations where service A uses `duration=120` meaning milliseconds while service B uses `duration=120` meaning microseconds. A dashboard summing or comparing these two sources will be wrong even though the query executes validly.

Recommendations:
- Explicitly name `duration_ms` or an equivalent unit.
- `status` should be a numeric HTTP code; `error_type` should belong to a finite enum.
- `route` should be a template (`/orders/{id}`), not a path containing real IDs.
- `event` should be stable, e.g., `http_request`, `payment_failed`; do not depend on a localized/translated message string.
- `service` and `environment` should use consistent names; do not log `prod` in service A and `production` in service B if they share a dashboard.
- Avoid renaming keys during a rollout without supporting compatible dashboards/queries.
- When the schema changes, have a version or migration plan; test JSON/logfmt end-to-end.

**Structured logging does not guarantee security by itself.** If an `authorization` field contains a Bearer token, it still gets stored in JSON. Data minimization rules must be enforced at the source.

## 5. Loki Labels vs. Fields in Log Content

With **Grafana Loki**, distinguish between:
- **Stream labels (indexed labels):** metadata used to locate streams, such as `app="orders-api"`, `env="prod"`, or `namespace="backend"`. Should have a controlled set of values.
- **Parsed fields:** fields extracted at query time using `| json` or `| logfmt`. Useful for `status`, `route`, `error_type`, `duration_ms`.
- **Structured metadata:** information attached to a log line, not necessarily indexed as a stream label; depending on the pipeline/version, can be used for searchable fields without creating too many streams.

A sensible split:

| Field | Typical Choice |
| --- | --- |
| `app`/`service` | Stream label when the set of services is stable |
| `env`/`namespace` | Stream label |
| `cluster`/`region` | Can be a stream label if cardinality is reasonable |
| `route` | Parsed field; occasionally a label if the route set is controlled and cost-evaluated |
| `status`/`error_type` | Parsed field; can be aggregated at query time |
| `duration_ms` | Numeric field for `unwrap` |
| `request_id`/`correlation_id` | Keep in event/structured metadata, **do not use as an indexed label per request** |
| `trace_id`/`span_id` | Event/metadata for drill-down, avoid high-cardinality indexed labels |
| `user_id`, raw URL, raw payload | Do not log by default; definitely never use as arbitrary labels |

**High cardinality**: if every request produces a different label value, Loki can create a massive number of streams, increasing index cost, memory usage, write/query latency, and slowing down dashboards. In Prometheus/metrics, using `request_id` as a label similarly causes time-series explosion.

On the other hand, selecting only `{app="orders-api"}` may be too broad and scan huge amounts of data. Add **stable labels** like `env`, `namespace`, and an appropriate time range before parsing/filtering.

### 5.1. Where Do app/env Values in Examples Come From?

In the queries below, the selector:

```logql
{app="orders-api", env="prod"}
```

assumes the **ingest pipeline has attached** the stream labels `app` and `env`. If the application only prints `event=http_request ...` to stdout and the collector does not attach these labels, the query will **not match**. In systems using OpenTelemetry's `service.name` resource attribute, you must map according to what your actual exporter/collector/storage uses. Do not assume label names from a documentation example.

## 6. LogQL Examples for Dashboard Panels

The following examples assume Loki receives **logfmt** lines such as:

```text
event=http_request route=/orders/{id} status=200 duration_ms=12 correlation_id=req_01
event=http_request route=/orders/{id} status=503 duration_ms=75 correlation_id=req_06
```

and the collector has attached stream labels `app="orders-api"` and `env="prod"`. Queries will differ if logs are stored as JSON, if keys are renamed, or if values reside only in structured metadata.

### 6.1. Finding Recent Logs in Explore

```logql
{app="orders-api", env="prod"}
  | logfmt
  | event="http_request"
```

- The selector narrows streams based on labels.
- `| logfmt` parses `key=value` fields.
- `| event="http_request"` filters events after parsing.
- Pick a short time range (e.g., 15 minutes) and inspect timestamps/labels on an actual log line.

For JSON:

```logql
{app="orders-api", env="prod"}
  | json
  | event="http_request"
```

**Do not use `| json` on logfmt or vice versa** and assume events were lost; verify the actual ingested format first.

### 6.2. HTTP Event Count in 5 Minutes

```logql
sum(
  count_over_time(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request" [5m]
  )
)
```

`count_over_time` counts **matching log lines** within a 5-minute window, which does not automatically equal the real request count if logging uses sampling/dropping, if two layers log duplicates, or if certain statuses are not logged. Label the panel “HTTP access log events / 5m” rather than “exact request count” when there is no one-event-per-request guarantee.

### 6.3. Event Rate per Second (from Logs)

```logql
sum(
  rate(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request" [5m]
  )
)
```

`rate` estimates **log events/second**, which is not an absolute, reliable requests/second metric if success logs are sampled. For production services, cross-check against an official request counter metric.

### 6.4. 5xx Errors by Route

```logql
sum by (route) (
  count_over_time(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request"
      | status=~"5.." [5m]
  )
)
```

`status=~"5.."` matches 500–599 codes parsed as text. This is the **count of 5xx events in 5 minutes**, not the error rate. If `route` in logs is a raw path containing IDs, the series count can explode; prefer route templates.

### 6.5. Estimated 5xx Error Rate from Logs

```logql
100 *
sum(
  rate(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request"
      | status=~"5.." [5m]
  )
)
/
sum(
  rate(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request" [5m]
  )
)
```

Explanation: the numerator is the rate of 5xx events/second; the denominator is the rate of all HTTP events/second; multiplying by 100 yields a percentage. This is a rate based on **log events**. Results can be skewed if levels are filtered differently, success logs are sampled, the collector drops logs, or two log pipelines emit duplicates.

**No data does not mean 0% errors.** When the denominator is 0 or the query finds no logs, Grafana/Loki may return no data/NaN. For alerting, explicitly design how to handle “no traffic” versus “no telemetry,” and test against your actual LogQL version; do not blindly treat all no-data states as healthy.

### 6.6. Estimated p95 Latency from Event Duration

```logql
quantile_over_time(
  0.95,
  {app="orders-api", env="prod"}
    | logfmt
    | event="http_request"
    | unwrap duration_ms
    | __error__="" [5m]
) by (route)
```

- `unwrap duration_ms` uses the numeric value of the parsed field.
- `__error__=""` excludes lines that encountered parse/conversion errors in this pipeline.
- Results are grouped by `route`, when Loki and the query are configured appropriately.

**Important:** this is the p95 **of the surviving log events**. If log sampling is uneven or queues drop events, the percentile does not represent full traffic. For latency SLOs, use histogram metrics instrumented at the appropriate processing point and verify aggregation across replicas.

### 6.7. Specific Business Errors

Suppose the schema has `event=payment_failed` and `error_type=UPSTREAM_TIMEOUT`:

```logql
{app="orders-api", env="prod"}
  | logfmt
  | event="payment_failed"
  | error_type="UPSTREAM_TIMEOUT"
```

This is a **sample** query for an application with matching event types, not something emitted by default by the Java program in section 8. When pivoting from a panel to Explore, preserve the time range, app/env/namespace, and error type so drill-down does not fire a system-wide query.

### 6.8. Using Dashboard Variables

Grafana provides template variables, such as `$app` or `$env`. For a **single-value** variable:

```logql
{app="$app", env="$env"} | logfmt | event="http_request"
```

If Multi-value or Include All is enabled, Grafana typically combines values into a regex; use the matching operator, for example:

```logql
{app=~"$app", env=~"$env"} | logfmt | event="http_request"
```

Set defaults and keep scopes narrow, especially in multi-tenant systems. Dashboard variables **do not replace RBAC/tenant isolation**; users must not be able to view unauthorized data even if they manually enter different values.

## 7. Essential Panels for a Service Dashboard

A good dashboard does not necessarily have many panels. Organize them by operational questions:

| Position/Panel | Suggested Data | Action on Anomaly |
| --- | --- | --- |
| Header: service, env, time range, version | Labels/variables and deployment annotations | Confirm you are viewing the right environment |
| Request rate | Request counter metrics or LogQL event rate | Is there a traffic drop or spike? |
| 5xx error rate | Metrics/LogQL error ratio | Which route has rising errors? |
| Latency p50/p95/p99 | Histogram metrics; log duration only when appropriate | Are requests slow or only a backend? |
| Errors by route/error type | Grouped counts by stable keys | Open Explore with specific route/error type |
| Recent ERROR/WARN logs | Log table with links to trace/request | Inspect error details and safe stack traces |
| Service/dependency panels | CPU, heap, GC, DB pool, queue, dependency latency | Distinguish app bugs from saturation |
| Pipeline health | dropped logs, collector queue, ingestion latency/no data | Are we losing observability data? |
| Deploy annotations | Release/config change timestamps | Correlate incidents with changes |
| Runbook/owner link | Operational docs and escalation | Reduce time to resolution |

**Key point:** request rates and latencies from logs can be a useful perspective, but for strict SLO/SLA requirements, prioritize properly instrumented metrics with clear definitions and use logs for root-cause investigation.

### 7.1. Designing Readable Panels

- Specify **units** and time windows: `5xx events/5m` is different from `5xx rate (%)`.
- Use clear panel titles: “HTTP 5xx (log event count, 5m)” is better than “Errors”.
- Keep the same time range and timezone for panels being compared; distinguish event timestamps from ingestion timestamps.
- Limit the number of displayed series; use Top N when there are many routes/error types.
- Do not plot the same metric in three different chart types if it adds no new insight.
- Base thresholds on SLOs/policies, not colors chosen just to “look nice”.
- Annotate when sampling or data gaps are present.
- Add links from overview panels to relevant log queries, traces, and runbooks.

### 7.2. Drilling Down from Overview to Record

A practical workflow:

```text
Dashboard: 5xx increases in orders-api / prod
  |
  v
Select route /orders/{id} and window 10:05-10:15
  |
  v
Explore: event=http_request, status=503
  |
  v
Open event, grab valid correlation_id or trace_id
  |
  v
Search application error logs, traces, DB queries, upstream timeouts
  |
  v
Compare deployment_version and configuration changes
```

Never store raw tokens, passwords, or personal request content in dashboard links. Links/derived fields for traces must be configured with the proper pattern, source, and access permissions. To link OpenTelemetry traces, a **standard W3C TraceId is 16 bytes (typically displayed as 32 hex characters)**; an application `correlation_id` like `req_01` in the demo below is **not** a standard trace ID.

## 8. Standalone Java 17+: Generating Dashboard-Ready Logs and Verifying Summaries

The example below **does not run Loki/Grafana**, but illustrates the **Java application's** responsibilities: emitting events with a finite schema, keeping route templates, omitting authorization headers, and then using an in-memory handler to validate the data and compute a simple summary.

The simulated data consists of six HTTP requests with statuses and durations:

| Route | Status | Duration (ms) |
| --- | --- | --- |
| `/orders/{id}` | 200 | 12 |
| `/orders/{id}` | 200 | 18 |
| `/orders` | 201 | 22 |
| `/orders/{id}` | 500 | 35 |
| `/health` | 200 | 40 |
| `/orders/{id}` | 503 | 75 |

Create the file **`LogDashboardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogDashboardDemo {
    enum Route {
        ORDER("/orders/{id}"),
        CREATE("/orders"),
        HEALTH("/health");

        final String value;

        Route(String value) {
            this.value = value;
        }
    }

    // authorization is present in the input to test that it is NOT logged.
    record RequestEvent(
            Route route,
            int status,
            long durationMs,
            String correlationId,
            String authorization) {}

    static String logLine(RequestEvent e) {
        if (e.route() == null
                || e.status() < 100 || e.status() > 599
                || e.durationMs() < 0) {
            throw new IllegalArgumentException("Invalid event");
        }

        String id = e.correlationId() != null
                && e.correlationId()
                    .matches("[A-Za-z0-9_-]{1,32}")
                ? e.correlationId() : "invalid";

        // Allowlisted fields only; never use e.authorization().
        return "event=http_request route=" + e.route().value
                + " status=" + e.status()
                + " duration_ms=" + e.durationMs()
                + " correlation_id=" + id;
    }

    static final class Capture extends Handler {
        final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                lines.add(record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        List<String> snapshot() {
            return List.copyOf(lines);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        List<RequestEvent> events = List.of(
            new RequestEvent(Route.ORDER, 200, 12,
                    "req_01", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.ORDER, 200, 18,
                    "req_02", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.CREATE, 201, 22,
                    "req_03", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.ORDER, 500, 35,
                    "req_04", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.HEALTH, 200, 40,
                    "req_05", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.ORDER, 503, 75,
                    "req_06", "Bearer FAKE_SECRET")
        );

        try {
            events.forEach(e -> logger.info(logLine(e)));
            List<String> saved = capture.snapshot();

            if (saved.size() != events.size()
                    || saved.stream().anyMatch(x ->
                        x.contains("FAKE_SECRET")
                        || x.contains("Authorization"))) {
                throw new AssertionError("Unsafe log");
            }

            // Verify that CR/LF in correlation_id is rejected.
            if (!logLine(new RequestEvent(
                    Route.ORDER, 200, 1,
                    "bad\nrequest", "secret"))
                    .endsWith("correlation_id=invalid")) {
                throw new AssertionError("Unsafe ID");
            }

            long errors = events.stream()
                    .filter(e -> e.status() >= 500)
                    .count();

            List<Long> times = events.stream()
                    .map(RequestEvent::durationMs)
                    .sorted()
                    .toList();

            // Nearest-rank for this small illustrative dataset.
            long p95 = times.get(
                    (int) Math.ceil(0.95 * times.size()) - 1);

            System.out.println("events=" + saved.size());
            System.out.println("errors_5xx=" + errors);
            System.out.printf(Locale.ROOT,
                    "error_rate_percent=%.1f%n",
                    100.0 * errors / events.size());
            System.out.println(
                    "p95_nearest_rank_ms=" + p95);
            System.out.println(
                    "sensitive_payload_logged=false");
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LogDashboardDemo.java
java LogDashboardDemo
```

**Expected standard output:**

```text
events=6
errors_5xx=2
error_rate_percent=33.3
p95_nearest_rank_ms=75
sensitive_payload_logged=false
```

### 8.1. Explaining the Example

- Six `logger.info(...)` calls are captured by the local handler as `LogRecord`s; the logger is set to INFO, and the handler to ALL. The program **does not print individual log lines** to stdout, only the summary.
- There are two `500`/`503` statuses out of six events. The rate on this small sample is `2/6 × 100 ≈ 33.3%`.
- The sorted durations array is `12,18,22,35,40,75`. The **nearest-rank** rule picks element `ceil(0.95 × 6)=6`, so the illustrative p95 is `75 ms`.
- The `logLine` function only uses the fixed route enum, status, duration, and validated correlation ID. The `authorization` field holds a dummy secret string but is **never included in the message**.
- When `correlationId` contains a newline, it is replaced with `invalid`, preventing untrusted input from breaking the logfmt structure.
- The isolated logger uses `getAnonymousLogger()` and `setUseParentHandlers(false)` to avoid affecting the root logger; `finally` detaches the handler.

**Very important limitation:** the nearest-rank algorithm in this demo **does not guarantee the same results** as Grafana/LogQL quantile functions, histograms, or pre-aggregated data. For production latency SLOs, use the proper measurement, histogram type, and aggregation contract rather than reusing this small test code.

The program also **does not set up** `app`/`env` stream labels, a collector, authentication, or Loki. To use the LogQL queries in section 6, a real pipeline must ship these logfmt lines and attach the environment/service labels properly.

### 8.2. Moving to a Real Application

- Choose a logger/backend (JUL, SLF4J+Logback, Log4j 2) fitting your existing system.
- Define event schemas and units; use a reliable JSON/logfmt encoder, and **do not concatenate raw user input** via string concatenation as a general-purpose serializer.
- Attach service/environment/deployment metadata via deployment/collector configuration.
- For real HTTP servers, measure duration at the proper start/end points; use `System.nanoTime()` for elapsed time, not wall-clock time, for latency.
- For async requests, measure at the completion callback rather than just when the handler returns.
- For errors, keep exceptions/stack traces where appropriate without printing credentials, query strings, or sensitive DTOs.
- Add trace context via standard OpenTelemetry integration; do not put a custom correlation ID string into the `TraceId` field.
- Test across the logger, encoder, collector, and dashboard using a dummy canary before rolling out.

## 9. Sending Logback/SLF4J or JUL Events to the Pipeline

SLF4J is an **API facade**; Logback/Log4j 2 are backends that determine how logs are written to console/file/OTLP. This statement:

```java
// Integration snippet in a service with SLF4J Logger LOG.
LOG.info("event=http_request route={} status={} duration_ms={}",
         routeTemplate, statusCode, durationMs);
```

is readable, but only formats a message according to the active formatter/backend. It **does not** automatically generate JSON, resource attributes, or Loki labels. You need compatible encoder and collector configurations.

A common pattern for containerized Java apps:
1. The application writes log lines to **stdout/stderr** in a standardized format.
2. The runtime/kubelet/agent collects stdout.
3. The agent/collector parses, adds resource metadata, processes according to policy, and ships to Loki or another backend.
4. Grafana/Loki queries by stable stream labels; event fields are parsed at query time.

If the application uses a **file appender**, handle rotation, file permissions, backups, and avoid shippers reading duplicates or losing files after rollover. If using **OTLP/OTel logs**, check the exporter/collector, batching/retry, resource mapping, and semantic conventions for your exact version. Never assume installing the OpenTelemetry Java agent will automatically collect every console file in your desired schema.

### 9.1. Choosing Log Levels and Volume

At 10,000 requests/second, logging one INFO event per request can generate hundreds of millions of events per day before counting DEBUG/WARN logs. Keep:
- Metrics/histograms for traffic and latency at operational resolution.
- Contextual logs for ERROR/WARN, audit events, and a portion of INFO per policy.
- Sampled success logs when appropriate, but clearly note that dashboards count **sampled events**, not actual requests.
- Preserve critical errors/audit logs as required; do not drop them just to make charts look smooth.
- Monitor queues, drop counts, collector backpressure, and ingestion lag.

**Balancing cost and investigability** is not just lowering the level from DEBUG to WARN. It requires stable event codes, trace links, a sampling strategy, and data-type-appropriate retention.

## 10. The Truth About Log-Based Alerts

A dashboard only reveals a problem when someone is looking at it. Alerts must have proper conditions and guide the responder to action.

For example, a log-based alert can detect a 5-minute spike in `payment_failed`/`UPSTREAM_TIMEOUT`. However, consider:
- Are the logs representative? Is there sampling or dropped events?
- What is a sensible denominator? 20 errors out of 20 requests is different from 20 errors out of 1 million requests.
- Is an event emitted **once** per failure, or is the same error retried and logged multiple times?
- Have you separated ingress 5xx errors from application 5xx errors?
- Does the alert include route, service, env, timestamp, an investigation query, and a runbook?
- Are **No Data** scenarios, query failures, collector outages, and telemetry gaps handled separately?

When well-instrumented metrics exist, use **metrics-based SLO/error budget alerts** as primary signals, and use logs to analyze “which specific error”. Log-based alerts are suited for rare, distinct events such as security policy violations, specific business processing failures, or a notable exception type.

### 10.1. Reducing False Positives

- Choose windows/thresholds based on traffic, not just a few-second spike.
- Use a ratio + minimum sample count when needed to avoid paging on near-zero traffic.
- Distinguish **severity** from actual user impact.
- Group/dedupe alerts by service/env/error type; avoid sending hundreds of alerts for the same incident.
- Have controlled silence/maintenance windows.
- After an incident, update panels/alerts/queries based on evidence rather than just raising thresholds.

## 11. Data Quality: How Dashboards Can Be Wrong

### 11.1. Lost or Delayed Logs

A log pipeline can:
- Drop events via logger level/filter before creation.
- Fill async queues and drop/block the producer.
- Lose buffered events on shutdown/crash.
- Have an agent lag behind reading files/stdout or hit permission errors.
- Have a collector retry/batch too long or hit rate limits/quotas.
- Suffer slow backend ingestion, wrong timestamps, or premature retention deletion.
- Restrict visibility via Tenant/RBAC so viewers only see a subset of logs.

If a dashboard suddenly drops to 0, traffic might actually be 0 **or** log ingestion is broken. You need dashboards/metrics tracking `log_pipeline_dropped`, `collector_queue_size`, `last_successful_export`, or equivalent metrics for your tools. Specific metric names vary by product and version; do not assume these example names exist out of the box.

### 11.2. Timestamps and Ordering

An event can have:
- **Event timestamp:** when the code created the log.
- **Observed/ingest timestamp:** when the collector/backend saw the event.
- **Dashboard evaluation time:** when the query ran.

Clocks across nodes can skew, and events can arrive late or out of order in Explore. When investigating, check timezones, NTP, lag, source timestamps, sort order, and retention. Do not assume a log appearing earlier in the UI always happened earlier across all services.

### 11.3. Duplication and Sampling

A single request might produce access logs at both the gateway and the application, or an agent might re-read a file after rotation/restart. A dashboard aggregating both sources will double-count events. Conversely, sampling 1% of success logs while keeping 100% of errors severely inflates log-derived error ratios.

Dashboard documentation should state:
- Primary source and layer (`gateway` vs. `application`).
- Event scope: per request, per retry, or per operation.
- Sampling/drop policy.
- Units and time range.
- How no-data states are handled.
- Conditions under which results must not be used for SLO calculations.

## 12. Privacy, Security, and Dashboard Access Control

**Logs can contain sensitive data.** Dashboards make data easier to view and can increase the risk of broad exposure.

Measures:
- Never log passwords, tokens, Authorization/Cookie headers, secrets, or full request/response bodies.
- Prefer route templates, error codes, random request IDs, and field allowlists.
- Do not log IPs, emails, user IDs, or tenant IDs by default without a clear purpose and retention policy.
- Audit stack traces, MDC/ThreadContext, headers, and formatters to ensure they do not automatically log private data.
- Use proper encoder escaping; with logfmt, sanitize spaces/quotes/newlines in values from untrusted sources.
- Explore/query/export permissions must follow need-to-know, enforcing tenant/environment isolation at the data source/storage layer.
- Control sharing of dashboard links, snapshots, screenshots, CSV/JSON exports, and incident attachments.
- Enforce retention, backups, encryption, and access auditing per policy; never rely on dashboard links as a data security boundary.
- When sensitive data must be investigated, use an approved, audited, time-bound channel.

**Watch out for template variables:** letting users edit `$service` or `$tenant` is not an authorization mechanism. The query/backend system must reject unauthorized data access regardless of URL parameters or dashboard variables.

### 12.1. Do Not Confuse Correlation IDs with Trace IDs

A string like `req_01` in the demo is only an **application correlation_id**. OpenTelemetry/W3C trace IDs have their own format, entropy, and propagation rules. Only display a “View trace” link when the field is genuinely a valid trace ID and the trace backend holds corresponding data. Never allow queries to jump from service A to service B using an unvalidated client-supplied ID.

## 13. Optimizing Cost, Performance, and Query Speed

Log costs accumulate across multiple stages:
- CPU and allocations to build/format messages.
- I/O/stdout and log rotation.
- Agent/collector CPU, memory, batching, retries, and egress.
- Backend storage, indexing, retention, and query scans.
- Dashboard refreshes, variables, and overly broad queries.

Balanced optimization:
1. Set **appropriate levels** per environment and module. Do not enable system-wide DEBUG unnecessarily.
2. Use parameterized/lazy logging to avoid expensive message construction when the level is disabled.
3. Define key events so you **do not need to dump payloads**.
4. Keep stream labels low-cardinality and selectors narrow.
5. Avoid putting `request_id`/`trace_id` in indexed labels.
6. Choose reasonable query windows; avoid overly frequent dashboard refreshes and queries spanning the entire log history.
7. Use metrics for high-volume continuous aggregations; use logs for drill-down.
8. Design retention/tiering based on data value and compliance requirements.
9. Monitor ingestion errors, queue/drop rates, query latency, and cost per service.

**Example:** a top-routes panel grouping by raw path `/orders/12345` instead of route template `/orders/{id}` creates too many groups and loses meaning. Fixing the schema at the source is far more effective than trying to write regexes at query time to normalize every path variant.

## 14. Testing Log-to-Dashboard Across Layers

### 14.1. Java Unit Tests

Test the event-building function:
- Correct `event` name, `route` from enum/allowlist, status 100–599, non-negative duration.
- No raw Authorization/password/token/query string in the message.
- Overly long IDs or IDs containing CRLF are normalized/rejected.
- Consistent field units; never switch ms to µs without changing the key.
- Clear error/normal event levels per contract.

The demo in section 8 performed tests using `AssertionError` and a local handler without external dependencies beyond the JDK.

### 14.2. Testing the Logging Backend

With Logback, use `ListAppender<ILoggingEvent>` or a test appender; with JUL, use a `Handler`; with Log4j 2, use the appropriate appender/test context. Verify:
- Do levels/filters actually let required events through?
- Does the JSON/logfmt encoder output the right fields and escaping?
- Does `MDC` contain non-allowlisted data or leak across requests?
- Do exceptions include stack traces without exposing secrets?
- Do appenders/async queues affect how tests read events?

Wait for events using signals/timeouts if async; do not use a fixed `Thread.sleep` and assume flushing is complete. Restore logger levels, appenders, context, and resources after tests to prevent cross-test pollution in parallel runs.

### 14.3. Pipeline Integration Tests

In a staging/test environment:
1. Send an HTTP request with dummy data and a canary `FAKE_SECRET`.
2. Wait for the app to write the event; verify schema/trace/correlation fields.
3. Verify the agent/collector receives it properly, attaches `app`/`env` metadata, and preserves time units.
4. Query a real log from Loki using `| logfmt`/`| json` matching the format; test the LogQL queries from section 6.
5. Check dashboard variables, time ranges, status filters, and route groupings.
6. Trigger a deterministic 5xx error, watch the error panel rise, and follow the Explore link to the record.
7. Disconnect the collector in the test environment; observe queues, retries, drops, or no-data behavior.
8. Verify the canary never appears in any sink/export/backup.
9. Check backend permissions and retention; test that an unauthorized user cannot view the logs.
10. Measure application and dashboard cost/latency under increased traffic.

Do not use real production data to create canaries. Direct Grafana/Loki checks require a deployed system; the standalone Java example **cannot replace** these integration tests.

## 15. Troubleshooting: Empty Panels, Wrong Numbers, or Slow Queries

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Panel shows “No data” while app is running | Wrong `app`/`env` labels, time range, not yet ingested, wrong filter | Inspect raw logs in Explore and actual labels |
| Query `| json` returns no fields | Source is logfmt/plain text | Inspect a sample log and choose the right parser |
| Wrong 5xx count | Multi-layer/duplicate logging or sampled success logs | Separate layers, dedupe, or check metrics |
| Duration is 1000x too large | Confusing milliseconds and microseconds | Check field unit and measurement source |
| p95 query parse error | `duration_ms` missing or non-numeric | `unwrap` the right field and filter `__error__` |
| Too many route groups | Raw path contains IDs or query params | Use route templates from the application |
| Very slow query | Broad selector, huge time range, high cardinality | Use stable labels, reduce scan scope |
| Trace link won't open | Non-standard ID or trace was sampled/expired | Check trace ID format, sampling, retention, backend |
| Dashboard suddenly drops to 0 | Traffic dropped or pipeline drop/collector failure | Compare metrics, ingestion health, and log delivery |
| Alert did not fire | “No data” is not zero, query returned NaN, or wrong window | Test query/rule over actual time range |
| More errors than requests | Retries, multiple layers, multiple logs per request | Define event/denominator clearly, dedupe |
| Secret appeared in dashboard | Source field/formatter/collector logged too broadly | Block at source, handle incident and access |
| Only one user cannot see data | RBAC/tenant/data source permissions | Check policy without granting blanket access |
| Chart mismatches metrics | Sampling, units, time bounds, clock skew, labels | Compare same source/scope and definitions |

**Investigation order:** identify service/env/time range → inspect a real raw event → check labels and parser → test simple LogQL → add filters/aggregations step by step → cross-check metrics → check collector/retention/RBAC. Never start with a storage-wide query or enable DEBUG in production just to “generate data”.

## 16. Production Dashboard Design Checklist

- [ ] Clear operational goal: error triage, SLO tracking, dependency analysis, security events, etc.
- [ ] Primary source chosen for RPS/errors/latency, knowing when logs are only sampled.
- [ ] Every panel clearly states unit, window, environment, service, and data meaning.
- [ ] Log schema includes `event`, `service`, `env`, level, timestamp, and required fields.
- [ ] Low-cardinality labels; never index request/trace IDs per event.
- [ ] Can drill down from 5xx/latency to logs and traces when IDs are valid.
- [ ] Displays deployment annotations or change markers for correlation.
- [ ] Includes panels/metrics reflecting ingestion lag, collector queues, and log loss.
- [ ] Alerts distinguish “zero”, “no data”, query errors, and logging pipeline outages.
- [ ] No leaked tokens/PII; never use dashboard variables as authorization.
- [ ] View/export permissions, retention, and backups verified against policy.
- [ ] Schema/query/panel tested with dummy data through a real pipeline.
- [ ] Runbook/owner, alert response steps, and periodic dashboard review schedule in place.

## 17. Practice Exercises

1. Run `LogDashboardDemo`. Manually calculate event count, 5xx count, error rate, and nearest-rank p95; compare with stdout.
2. Add a `status=404` event. Verify why it does not increment `errors_5xx` even though it affects total traffic and 4xx analysis.
3. Pass a correlation ID containing a newline or exceeding the length limit. Verify the raw string does not appear in logs; test a valid input.
4. Change a route from a template to a raw path containing a fake ID. Explain the cardinality/privacy risks and fix it using an enum/route mapping.
5. In a test Loki instance with valid stream labels, try querying a log table and 5-minute `count_over_time`. Distinguish count from rate.
6. Create a 5xx-by-route panel, add a total traffic query, and compute the error rate. Observe how no data/zero denominator is handled.
7. Create a request duration histogram metric using an appropriate instrumentation library and compare it with log-derived p95 under the same workload. Explain discrepancies caused by sampling/aggregation.
8. Attach a valid W3C trace ID to a request in a test environment and create a derived link from the event to the trace. Try a custom `req_01` and verify why it is not a valid trace ID.
9. Intentionally stop the collector in a test environment; observe how app log lines still exist while the dashboard loses data.
10. Create `app` and `env` dashboard variables, and test single-value vs. multi-value cases with different query selectors.
11. Build a retention/access-control matrix for DEBUG, ERROR, audit logs, and dashboard exports. Verify dummy canary data does not leak out of scope.
12. Write a 5xx spike runbook for a service: from metrics to dashboard, Explore, trace, deployment annotations, and root-cause verification.

## 18. Key Takeaways

- **Logs** are detailed events; **dashboards** are query-driven views; **observability** requires consistency and correlation across logs, metrics, and traces.
- Design schemas around operational questions: event code, service/env, status, route template, duration/unit, and correlation/trace ID when available.
- In Loki, choose **low-cardinality stream labels**, while keeping request IDs, trace IDs, durations, and most event fields in parsed fields or structured metadata.
- `count_over_time` counts log events; `rate` measures log events/second; `unwrap` uses numeric fields for percentiles. Do not treat them as exact request metrics when pipelines sample, drop, or duplicate.
- Use reliable metrics/histograms for SLOs and critical alerts, and logs for drill-down.
- A good dashboard specifies data sources, time ranges, units, access control, pipeline health, runbooks, and investigation links.
- Test for no-data states, data masking, log injection, label explosion, retention, and access control before going to production.

### Official References

- OpenTelemetry — Logs Data Model (Timestamp, ObservedTimestamp, Resource, Attributes, TraceId, Severity): https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry — Java instrumentation and logging: https://opentelemetry.io/docs/languages/java/
- Grafana Loki — LogQL / query language: https://grafana.com/docs/loki/latest/query/
- Grafana — Loki query editor, metric queries: https://grafana.com/docs/grafana/latest/datasources/loki/query-editor/
- Grafana — Loki template variables: https://grafana.com/docs/grafana/latest/datasources/loki/template-variables/
- Grafana Loki — Label design and cardinality: https://grafana.com/docs/loki/latest/get-started/labels/
- Prometheus — Histograms and summaries: https://prometheus.io/docs/practices/histograms/
- Oracle JDK 17 — java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

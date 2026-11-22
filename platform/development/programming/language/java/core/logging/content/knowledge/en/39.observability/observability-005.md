# Log Search in Java Core Logging and Observability

## 1. What Is Log Search and What Problem Does It Solve?

**Log search** is the ability to find, filter, sort, correlate, and analyze log records based on conditions such as time, service, severity level, event name, request ID, trace ID, or message content. In a Java system, log search turns lines emitted by `java.util.logging` (JUL), SLF4J/Logback, Log4j2, or other libraries into usable data for incident investigation, explaining application behavior, and assessing user impact.

For example, when a dashboard reports a spike in the HTTP 5xx rate for `checkout-api`, the questions to answer are:

1. During the anomalous 5-minute window, which service logged `ERROR` and which endpoint had the concentrated failures?
2. Did every request fail, or did some attempts fail and succeed on retry?
3. Which services did a specific request pass through, and in what order?
4. What do the original message, exception type, and error code indicate as the root cause?
5. Are logs missing because the system did not emit them, because the query is wrong, or because the ingest pipeline is delayed?
6. Are the found events reliable, free of duplicates, and free of sensitive data?

**Search is not just Ctrl+F in a single file.** In multi-instance and containerized environments, logs are typically collected, parsed, enriched with metadata, stored centrally, and then indexed or organized for querying. Understanding how data is produced in Java and how the backend organizes it is essential for accurate search results.

Learning objectives: distinguish between text search and field search; design appropriate structured logs; construct queries by time and correlation; understand event time vs. ingest time, indexing, sampling, and retention; optimize query cost; protect data; and run a standalone Java 17 example demonstrating structured querying.

## 2. Where Does Log Search Sit in the Observability Pipeline?

```text
Java application
  -> logger API / logging backend
  -> console, file, appender, or OTLP log exporter
  -> container runtime / agent / OpenTelemetry Collector
  -> parse, validate, enrich, redact, route
  -> log backend: storage + indexing/search engine
  -> query, visualization, alert, incident investigation
```

Some backends index every field, while others only index selected fields or use a distinct search mechanism. Do not assume that the storage and query capabilities of Elasticsearch/OpenSearch, Loki, Cloud Logging, CloudWatch Logs, or a SaaS service are identical. Actual syntax and limits must be verified against the specific version and architecture in use.

Each layer can affect searchability:

| Layer | Responsibility | If Misconfigured |
| --- | --- | --- |
| **Java logger** | Emit the right event, severity, timestamp, and context | Missing logs due to level/filter; message lacks searchable fields |
| **Encoder** | Convert events to JSON/text and escape data | Stack traces split across multiple lines; JSON parse errors |
| **Agent/Collector** | Read logs, add pod/service/tenant metadata, route | Events sent to the wrong environment/project; dropped or duplicated |
| **Backend ingest** | Accept, parse, and store events | Quota, permission, mapping, or ingest lag errors |
| **Index/search** | Enable filtering, text search, and field/time aggregation | Slow queries, missing results due to index/retention |
| **UI/alert** | Display results and detection conditions | Wrong time zone, wrong query, noisy alerts |

Distinguish three states: **emitted by the application**, **received by the backend**, and **queryable**. A log appearing in `kubectl logs` or the console does not prove it has been ingested and indexed. Conversely, seeing no search results does not prove the event did not occur; the query scope may be wrong or the data may have arrived late.

## 3. From Plain-Text Logs to Structured Logs

### Plain-Text Logs

A message like:

```text
2026-01-01T10:00:02Z ERROR Payment failed for order 42
```

can be searched by the words `Payment` or `ERROR`, but it is hard to distinguish the service, request, exception, tenant, order ID, and final outcome if those fields are not recorded consistently.

Text search is useful when looking for an error phrase with an unknown schema, but it can return **false positives** because messages are free-form data. For instance, searching for `timeout` might match an explanation like “request completed without timeout”. Analyzing error counts based on text can also drift when messages change across releases.

### Structured Logs

A JSON Lines event is easy to filter by field:

```json
{
  "timestamp": "2026-01-01T10:00:02Z",
  "severity": "ERROR",
  "service.name": "checkout-api",
  "service.version": "1.2.0",
  "deployment.environment.name": "prod",
  "event.name": "payment.failed",
  "operation": "payment.authorize",
  "http.route": "/api/payments",
  "request_id": "req-100",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "error.code": "DOWNSTREAM_TIMEOUT",
  "exception.type": "java.net.SocketTimeoutException",
  "message": "Payment provider did not respond"
}
```

This is an **illustrative application schema**, not a claim that every log backend automatically understands those exact field names. Some backends store them inside a JSON payload, while others use their own mappings. With OpenTelemetry, resource attributes, log record attributes, and semantic conventions must be exported/mapped according to the corresponding SDK and version.

Commonly useful fields:

| Field | Purpose | Notes |
| --- | --- | --- |
| `timestamp` | Search by when the event occurred | UTC or offset; synchronize clocks |
| `ingested_at` (if present) | Search by when the backend received the data | Do not confuse with event time |
| `severity` | Filter ERROR/WARN/INFO | Level mappings vary by framework/backend |
| `service.name`, `service.version` | Distinguish service and deployment | Source from trusted configuration |
| `deployment.environment.name` | Distinguish prod/staging/test | Do not rely solely on client-supplied strings |
| `event.name` | Search for a stable event type | Standardize names across services |
| `operation`, `http.route` | Filter by business operation/endpoint | Use route template, not raw path with IDs |
| `request_id`, `trace_id` | Trace a request across services | Do not turn into metric labels |
| `error.code`, `exception.type` | Group errors | Use stable codes, not message strings |
| `message`, exception detail | Read incident context | Sanitization, size limits, access control |

**Each event should sit on a single valid JSON line.** Newlines in messages or stack traces must be escaped inside the JSON string, or the pipeline must have proper multiline handling. If one stack trace is split into 30 separate events, text search might find a middle line while losing the context of the original exception.

## 4. Common Log Search Patterns

| Search Type | Intent Example | When to Use |
| --- | --- | --- |
| **Field equality** | `service.name = checkout-api` | Filter for an exact service or event name |
| **Multiple AND conditions** | service + severity + time window | Narrow down an incident with minimal noise |
| **OR/IN** | `severity ∈ {WARN, ERROR}` | Observe multiple related log levels |
| **Full-text** | Message contains words related to timeout | Look for signals without a dedicated field |
| **Phrase/exact match** | Message contains a specific phrase | Reduce unintended matches |
| **Range** | timestamp in `[start, end)` | Investigate a specific time period |
| **Prefix/regex/wildcard** | Event or path pattern | When schema is not standardized; watch cost and accuracy |
| **Aggregation/group-by** | Count errors by service/route/error code | Identify abnormal concentrations |
| **Sort/top-N** | Most recent events or most common errors | Rapid triage |
| **Correlation timeline** | Find all events for `request_id=req-100` | Reconstruct request flow across services |
| **Comparison** | Before and after deployment | Check for regressions by version |

Not every backend supports all operators or executes them the same way. Some search indexes tokenize values, so `"payment.failed"` might not match as an exact field; use an **exact/keyword field** query when comparing strings for equality. Broad regex and wildcard queries can be very expensive; narrow down the time window, service, and indexed fields first.

### Field Queries Differ from Text Queries

Suppose a log contains:

```json
{"severity":"INFO","message":"Recovery succeeded after prior timeout"}
```

A text query containing `timeout` will return this event, whereas `severity=ERROR` will not. Conversely, an `ERROR` with `error.code=DB_UNAVAILABLE` whose message is just `"Dependency failed"` will not match the keyword `timeout`. Use **fields with stable semantics** for classification; use text search as a supplement for detailed investigation.

### Vendor-Neutral Illustrative Syntax

```text
WHERE service.name = "checkout-api"
  AND severity IN ("ERROR", "WARN")
  AND timestamp >= 2026-01-01T10:00:00Z
  AND timestamp <  2026-01-01T10:05:00Z
ORDER BY timestamp ASC
```

This is a **pseudo-query to explain intent**, not a command you can paste verbatim into every cloud console. In SQL-like backends, keys containing dots may require quoting; in label-based or text-pipeline query systems, the syntax differs. Always check how your backend handles case sensitivity, text analysis, empty values, and missing fields.

## 5. Choosing the Right Search Time Range

A log query must clarify:

- **Event time:** when the application emitted or recorded the event, usually generated by `Instant.now()` or the logger timestamp.
- **Ingest time:** when the backend received the log; may be later due to queue batching, retries, or network delays.
- **Query time:** when the user runs the search; the UI may default to displaying in the local time zone.
- **Request completion time:** may differ from when an exception attempt within the request was logged.

For example, an event occurs at `10:04:59Z` but due to backend throttling only becomes queryable at `10:06:30Z`. If the UI filters by ingest time, it appears in the later window; if it filters by event time, it belongs to the earlier window. Know which timestamp your system uses.

Use a **half-open** interval `[start, end)` for programmatic queries and windowed reports:

```text
start inclusive: 2026-01-01T10:00:00Z
end exclusive:   2026-01-01T10:05:00Z
```

Advantage: two consecutive windows never double-count an event falling exactly on `10:05:00Z`. When investigating in the UI, you can pad the range before and after the reported error time to avoid missing late-arriving logs, clock skew, or earlier request steps. Do not arbitrarily shift timestamp time zones.

If a query returns too much data, narrow it from 24 hours down to 15 minutes or 5 minutes after pinpointing the incident timestamp; if there are no results, widen it in a controlled manner **after checking the time field and ingest pipeline**, rather than concluding the event does not exist.

### Event Ordering Is Not Based Solely on Timestamp

Multiple logs can share the same timestamp or arrive out of order from different threads or containers. If a stable timeline is needed, sort by timestamp plus a secondary key such as event ID or sequence when available. **Do not infer global execution order from clocks on different machines**, especially when clock skew or asynchronous operations are involved. In tracing, parent/child spans and business sequences help reconstruct causal order more reliably.

## 6. Standalone Java 17 Example: Searching Logs by Field, Time, and Request ID

This example uses **only JDK 17**, with no database or external logging library required. It demonstrates query logic over **events already parsed into Java records**, without performing full-text indexing or JSON parsing. In a real system, logs are sent to a backend and similar queries are executed by the search engine. The sample data is fixed for deterministic stdout.

Problem:

1. Retrieve all `ERROR` events from `checkout-api` in `[10:00, 10:05)`.
2. Retrieve the timeline of `req-100` across **multiple services**, sorted by ascending time.
3. The `req-102` log falls outside the window at minute 10:06, so it is excluded from query 1's results, but not deleted from the source dataset.

Create **`LogSearchDemo.java`**:

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.function.Predicate;

public final class LogSearchDemo {
    record LogEvent(
            String eventId,
            Instant occurredAt,
            String severity,
            String service,
            String eventName,
            String requestId,
            String message) {}

    private static List<LogEvent> data() {
        return List.of(
                new LogEvent(
                        "e-001", Instant.parse("2026-01-01T10:00:00Z"),
                        "INFO", "checkout-api", "checkout.started",
                        "req-100", "Checkout started"),
                new LogEvent(
                        "e-002", Instant.parse("2026-01-01T10:00:01Z"),
                        "WARN", "inventory-api", "inventory.slow",
                        "req-100", "Inventory took longer than expected"),
                new LogEvent(
                        "e-003", Instant.parse("2026-01-01T10:00:02Z"),
                        "ERROR", "checkout-api", "payment.failed",
                        "req-100", "Payment provider timed out"),
                new LogEvent(
                        "e-004", Instant.parse("2026-01-01T10:01:00Z"),
                        "INFO", "checkout-api", "checkout.started",
                        "req-101", "Checkout started"),
                new LogEvent(
                        "e-005", Instant.parse("2026-01-01T10:01:02Z"),
                        "ERROR", "checkout-api", "payment.failed",
                        "req-101", "Payment provider timed out"),
                new LogEvent(
                        "e-006", Instant.parse("2026-01-01T10:06:00Z"),
                        "ERROR", "checkout-api", "payment.failed",
                        "req-102", "Payment provider timed out"));
    }

    private static List<LogEvent> search(
            List<LogEvent> events, Predicate<LogEvent> condition) {
        return events.stream()
                .filter(condition)
                .sorted(Comparator.comparing(LogEvent::occurredAt)
                        .thenComparing(LogEvent::eventId))
                .toList();
    }

    private static void printEvents(List<LogEvent> events) {
        for (LogEvent event : events) {
            System.out.println(
                    event.occurredAt() + " " + event.severity()
                    + " " + event.service() + " " + event.eventName()
                    + " req=" + event.requestId());
        }
    }

    public static void main(String[] args) {
        List<LogEvent> events = data();

        Instant start = Instant.parse("2026-01-01T10:00:00Z");
        Instant end = Instant.parse("2026-01-01T10:05:00Z");

        List<LogEvent> errors = search(events, event ->
                "checkout-api".equals(event.service())
                && "ERROR".equals(event.severity())
                && !event.occurredAt().isBefore(start)
                && event.occurredAt().isBefore(end));

        System.out.println("QUERY 1: checkout-api ERROR [10:00,10:05)");
        printEvents(errors);

        List<LogEvent> timeline = search(events,
                event -> "req-100".equals(event.requestId()));

        System.out.println("QUERY 2: request_id=req-100");
        printEvents(timeline);
    }
}
```

Compile and run:

```bash
javac LogSearchDemo.java
java LogSearchDemo
```

**Exact stdout:**

```text
QUERY 1: checkout-api ERROR [10:00,10:05)
2026-01-01T10:00:02Z ERROR checkout-api payment.failed req=req-100
2026-01-01T10:01:02Z ERROR checkout-api payment.failed req=req-101
QUERY 2: request_id=req-100
2026-01-01T10:00:00Z INFO checkout-api checkout.started req=req-100
2026-01-01T10:00:01Z WARN inventory-api inventory.slow req=req-100
2026-01-01T10:00:02Z ERROR checkout-api payment.failed req=req-100
```

Explanation:

- `Predicate<LogEvent>` expresses AND conditions; each condition uses standardized fields instead of parsing free-form message strings.
- `Instant` and `!isBefore(start) && isBefore(end)` implement a half-open interval; events occurring exactly at `end` are excluded.
- Query 1 returns **two** `ERROR` events for the same service within the window; `e-006` is excluded because it is at 10:06, and `e-002` is excluded because it is from the inventory service at `WARN` level.
- Query 2 does not filter by service, showing a single request traversing both `checkout-api` and `inventory-api`. This is the first step of correlation search, even though the demo does not yet include real distributed tracing.
- `sorted` orders by timestamp and then event ID for deterministic ordering on equal timestamps; `Stream.toList()` was introduced in Java 16+, fitting Java 17.
- The `message` field is kept in the record but intentionally **not printed** in the default output, because initial queries should display structured, low-sensitivity fields. In production, reveal messages/stack traces only when authorized and needed for investigation.
- This example does not measure throughput or prove backend completeness. All data resides in RAM, with no indexing, ingest lag, sampling, retries, ACLs, or retention guarantees. **Do not use in-memory search over all production logs**; offload this logic to a scalable search backend.

## 7. Capturing Enough Fields from Java Loggers for Search

### JUL: java.util.logging

JUL provides loggers, `Handler`, `Formatter`, and `Filter`. By default, output is usually plain text and does not automatically conform to a JSON schema like the table above. Illustrative snippet:

```java
Logger logger = Logger.getLogger("checkout-api");
logger.log(Level.WARNING, "Payment provider timeout");
```

This snippet **does not run standalone** without imports and configuration, and it does not automatically attach `request_id`/`trace_id`. To search logs by these fields, the application must use a suitable formatter/handler or a parser/enrichment pipeline.

### SLF4J with Logback/Log4j2

SLF4J is a facade; the provider/backend determines the appender and encoder. A common pattern is parameterized log messages:

```java
logger.error("payment failed orderId={} errorCode={}",
        orderId, "DOWNSTREAM_TIMEOUT", exception);
```

This is an **illustrative snippet** requiring an SLF4J logger, `orderId`, and `exception` in scope. It does not automatically guarantee that every placeholder becomes a JSON field. If the backend only has a text encoder, those values end up inside the message string; to query by `error.code` separately, you need structured arguments, a key-value API, or a compatible encoder/instrumentation.

With Spring Boot, logging configuration and dependencies/providers vary by version. `logging.level.*` can control log levels per package; a JSON encoder or structured logging support must be enabled and configured for your stack. Do not assume every version emits full JSON to stdout by default.

### Distinguishing Fields "Present in Context" vs. "Actually Emitted"

Context in MDC/ThreadContext only helps log search if the appender/encoder is configured to **include MDC in the output**. For example, calling `MDC.put("request_id", id)` when the encoder only prints `%msg` means the log backend still never sees the request ID. Conversely, a JSON encoder that dumps all MDC fields unrestrictedly may accidentally emit tokens or personal data.

Verify all four stages:

1. Request context has the right fields.
2. Logger/backend retains the fields and encodes them in the expected format.
3. Agent/Collector does not drop or rename fields outside the contract.
4. Backend parses/indexes them into queryable fields, not just a JSON string trapped inside `message`.

## 8. Correlation Search: Request ID, Trace ID, and Span ID

In a microservices system, errors often occur in a different service from the one returning the response to the client. A typical investigation flow looks like:

```text
HTTP 503 at gateway (request_id=req-100)
    |
    +-- search request_id=req-100 in same environment/time
           |
           +-- checkout-api: request started
           +-- inventory-api: warning slow dependency
           +-- payment-api: timeout / retry
           +-- checkout-api: request completed with 503
```

**Request ID** helps filter logs for the same request, but propagation must follow trusted rules. If a client supplies its own request ID, the gateway may need to validate its format and length limit, or issue a new ID. Never let clients supply sensitive fields such as tenant or service identity and treat them as trusted evidence.

**Trace ID** connects multiple spans of a distributed trace; span ID identifies a specific span. One request can generate many spans, many logs, and many retries. Logs containing `trace_id` remain useful even when trace sampling prevents the corresponding trace from being stored; never conclude “no trace = no error”.

In Java using SLF4J/Logback, MDC is typically bound to a thread. With `ExecutorService`, `CompletableFuture`, or reactive chains, MDC does not automatically propagate across all asynchronous tasks. You must use proper context propagation and restore/clear the context after the request so logs from a new request are not tagged with stale IDs.

When searching by trace ID:

- Select the same environment and an appropriate time range.
- Make sure not to confuse a span's `trace_id` with an HTTP gateway's request ID.
- Group by service/span/operation to build a timeline.
- Watch for retries and parallel branches; do not assume all logs sharing a trace have causal order based solely on timestamp.
- Validate trace/span IDs before placing them into a query; do not concatenate queries from unvalidated input if the system has special query syntax.

## 9. From Metric Anomaly to Log Search

Metrics detect the situation; logs explain the cause. Suppose a dashboard shows a spike in `http.server.request.duration` or 5xx counts for `checkout-api`.

Workflow:

1. From the metric, extract **service, environment, route, status/error code, and time window**. Confirm whether the metric counts requests or attempts.
2. Search structured logs with the same scope. Start with completion events or `ERROR` events, depending on the question.
3. Group by `error.code`/`event.name`/`service.version` to see clustered errors or differences across deployments.
4. Pick a few representative request IDs and inspect the full cross-service timeline, including `WARN` and `INFO`.
5. If traces are available, open the related trace/span to inspect duration, retries, and dependencies; if traces are missing due to sampling, logs can still suffice for investigation.
6. Check for multiple logs per request or duplicate event ingestion. Do not use the count of `ERROR` log lines as a direct substitute for a failed request counter.
7. Cross-check sanitized exception messages, timing, and actual behavior; distinguish recovered errors from final failures.
8. If the query returns no results, check the time window, service scope, retention, ingest errors, sampling, and index lag before concluding the metric is wrong.

An aggregated metric can cover millions of requests; **do not attach request IDs as metric labels**, as cardinality can grow unbounded. In systems supporting exemplars, a metric measurement sample can attach a trace ID for investigation, while detailed lookups should happen in logs/traces.

## 10. Useful Operational Query Patterns

### A. Errors by Service and Time

```text
filter:
  environment = prod
  service = checkout-api
  severity = ERROR
  timestamp in [start, end)
sort:
  timestamp ascending
```

Use when isolating newly emerging errors. If results are too numerous, add `event.name`, `error.code`, or `http.route`.

### B. Errors by Endpoint/Route

```text
filter:
  http.route = /api/orders/{orderId}
  http.status_code >= 500
  timestamp in [start, end)
group by:
  error.code, service.version
```

Find endpoints exhibiting the same error type across versions. The route must be the **matched template**, not `/api/orders/987123` containing a dynamic ID.

### C. Request Timeline

```text
filter:
  request_id = req-100
  timestamp in [start - context, end + context]
sort:
  timestamp, event_id
```

Do not filter by severity initially; `INFO`/`WARN` logs often show where the request started, retried, fell back, or routed to another service.

### D. Before/After Deployment Comparison

```text
filter:
  service = checkout-api
  timestamp in comparable windows
group by:
  service.version, event.name, error.code
```

Normalize windows by traffic, environment, and route. An increase in `ERROR` logs after deployment could be caused by a logging level change rather than a higher error rate; cross-check against request/error metrics.

### E. Exception Search

```text
filter:
  exception.type = java.net.SocketTimeoutException
  error.code = DOWNSTREAM_TIMEOUT
  timestamp in [start, end)
```

Use type/error code fields rather than only searching for the word “timeout” in the message. If the system lacks structured exception types, text search is an exploratory step, but treat its results as potentially noisy.

### F. Audit and Security Events

```text
filter:
  event.name = authz.access.denied
  environment = prod
  timestamp in [start, end)
group by:
  service, target_type, reason_code
```

Use only server-verified fields and restrict read access by policy. Audit logs may require dedicated retention/durability and must not be arbitrarily sampled.

The blocks above are **pseudo-queries**, not YAML config syntax or complete query commands. For a specific backend, translate them into its supported query syntax and verify indexing, permissions, and time range capabilities.

## 11. Search Backends and Indexing: What Affects Performance?

Log search may need to scan massive volumes of data. Cost and latency typically depend on:

- **Time range:** narrower ranges reduce the number of segments/chunks scanned; most log stores partition by time.
- **Service/tenant/environment scope:** selective conditions applied early shrink the dataset.
- **Indexed fields/labels:** exact queries on indexed fields/labels usually differ significantly in cost from full-message scans. Each backend has its own indexing and storage trade-offs.
- **Text tokenization:** token, phrase, and exact keyword searches can yield different results; casing, punctuation, and analyzers matter greatly.
- **Regex and wildcards:** patterns over too many events can be expensive; do not assume the same regex executes efficiently across all backends.
- **Aggregation:** grouping by high-cardinality values can consume substantial memory and create thousands of buckets.
- **Sort, pagination, and top-N:** fetching all data and sorting by time is resource-intensive; limit pages/results and specify a sort key for stable pagination.
- **Retention and storage tiers:** data in cold/archive tiers may require restoration or have different query latency; logs past retention cannot be recovered merely by widening the time window.

### Avoid High Cardinality in the Wrong Places

A log may contain `request_id`, `trace_id`, or order ID for investigation, but that does not mean those values should be **index partitions, metric labels, or stream labels**. In systems that use labels to select streams, making every request ID a label can create a massive number of streams. For metrics, request ID/trace ID are completely inappropriate as regular labels.

Conversely, removing all ability to search by request ID can make investigation very difficult. The solution is to **choose a storage structure suited to the technology**: some systems support searching request IDs via an indexed field, while others use scan filters within streams narrowed by service/environment/route. Do not blindly copy label policies across Loki, Elasticsearch, and Prometheus.

### Sampling Reduces Searchable Data

If the application or collector samples `DEBUG`/`INFO` logs, a request may lack a complete timeline. This must be documented in policy; do not conclude an event never happened just because no log was found. For `ERROR` or mandatory audit logs, define retention policies based on criticality and capacity.

## 12. Delayed, Missing, and Duplicate Logs

### Ingestion Delay

A log is emitted at 10:00 but indexed at 10:03 due to queueing/retries. If the search UI is set to “Last 1 minute”, the event may fall outside the window depending on whether the backend uses event time or ingest time. Check pipeline latency, widen the range according to the time field, and use event IDs to cross-reference.

### Missing Data

Possible causes include:

- Logger level/filter dropped the event before creation.
- Async appender queue filled up and dropped events per policy.
- Container runtime rotation occurred or the agent could not read fast enough.
- Collector parse error, missing exporter, or quota/network/auth failure.
- Backend rejected ingestion, retention expired, or wrong project/tenant.

Do not emit a "test" log event and treat failing to find it in search as proof of a single root cause. Check independent metrics from the source, agent, and backend, alongside end-to-end testing.

### Duplicate Events

An exporter sends an event and misses the ACK; a retry can cause the backend to receive two copies. The same exception can also be logged in the DAO, service, and controller. These two types of duplication are different:

- **Duplicate transport:** the same logical `event_id` is resent; can be deduplicated per the storage contract.
- **Duplicate semantic logging:** multiple independent events are created from one underlying error; standardize logging points, event names, and owners.

Do not treat identical stack traces as proof that two logs are the same event. Multiple independent requests can fail at the exact same stack frame.

## 13. Security and Log Search Access Control

Logs often contain data from multiple services/tenants, sometimes including PII or internal details. A powerful search system must be paired with access control.

- **Do not log secrets at the source:** access tokens, session cookies, passwords, private keys, connection strings with credentials, sensitive card numbers, or unnecessary customer payloads. Redaction at the Collector is only a secondary layer because data has already left the JVM.
- **Read permissions differ from write permissions:** a service having ingest permission does not mean it should be allowed to query all logs; users should only read within their role/tenant/environment.
- **Retention and data residency:** limit retention duration and data regions per actual policy. There is no single default retention value suitable for every organization.
- **Audit query activity:** for sensitive data, track who searched, exported, or changed permissions/retention; restrict unauthorized bulk exports.
- **Query injection:** if an application accepts search parameters from users and concatenates query strings, apply validation/escaping or use parameterized APIs. Use field/value allowlists and limit time range, page size, and query cost.
- **Log injection:** newline/control characters in user input must be escaped by the JSON encoder; do not allow clients to spoof severity, service, actor, or audit outcomes.
- **Trusted context:** request IDs may be validated or newly issued by ingress; do not use untrusted headers as identity or tenant scope for search authorization.

For example, a URI path or query string containing an email or token should not be logged verbatim under `url.full` merely for debugging convenience. A structured event with `http.route`, status, error code, and correlation ID is usually sufficient for operations; raw evidence, if needed, must go through a restricted-access channel.

### Distinguishing Data Search from Inference Rights

Even when a dashboard only displays counts per tenant, small result groups can indirectly leak sensitive information. Consider query limits, aggregation grouping, masking, and permission checks before returning results to viewers.

## 14. Diagnostic Scenario: "Cannot Find Logs for a Failed Request"

A systematic checklist:

1. **Verify event existence per contract:** which services did the request traverse, at what level does it log, under what event name, and is it sampled?
2. **Verify IDs:** were request ID, trace ID, tenant ID, and service name generated and propagated correctly? Did the ID change at the gateway or in an async worker?
3. **Verify time:** compare UTC vs. local time, event time vs. ingest time, machine clocks, and filter bounds; widen the range in a controlled way.
4. **Verify output:** do console/file/OTLP outputs contain valid events? Does the encoder include the searchable fields in the payload?
5. **Verify pipeline:** did the agent/Collector read, parse, and route to the right backend/project/region/tenant? Are there exporter errors, drops, or queue backlogs?
6. **Verify schema:** does searching by exact `event.name`/`request_id` field match? Was the field renamed, nested, or stored as plain text?
7. **Verify policy:** has retention expired, is the index/archive unavailable, does the querier lack permissions, or is there a query quota?
8. **Cross-check independent sources:** request/error metrics, tracing spans (if any), canary events, and audit/transaction events to identify blind spots.
9. **Record evidence:** query, time range, result count, actual fields, ingest lag, and the failing step so the fix is reproducible.

**Zero results does not necessarily mean zero errors.** Overly narrow queries, wrong routes, late-arriving data, disabled log levels, or insufficient query permissions can all produce an empty list.

## 15. Testing Log Search Capabilities

A test suite should verify both **generated content** and **searchability in the backend**:

| Test | Expectation |
| --- | --- |
| INFO/ERROR with schema | All required fields have the right types and names |
| Message with quotes/newlines | JSON Lines still parses cleanly without splitting events |
| Query ERROR by service/time | Returns only events matching severity/service/window |
| Query request ID across services | Timeline is complete per policy, without mixing other requests |
| Multiple events with same timestamp | Stable sort using secondary key if available |
| Request containing token/PII | Not leaked into default message/query/raw path logs |
| Exception with stack trace | Includes exception type/error code and protected trace |
| Async/Executor/reactive | Correlation ID is neither lost nor leaked across threads |
| 404/401 before controller | Event is emitted if required by access/security policy |
| Exporter retry / ACK loss | Duplicates are not counted as new business errors |
| Queue overflow / Collector error | Counters and alerts reflect dropped events |
| Ingest delay | Queries by event time and ingest time are not conflated |
| Deployment version change | Searching by `service.version` shows the distinction |
| Tenant authorization | Unauthorized users cannot search logs outside their scope |
| Retention/archive | Data sits in the right tier/duration with expected search behavior |
| Expensive wildcard/regex query | Enforces time, result, and resource budget limits |

Java unit tests can use records and predicates as in the example to verify filter/sort logic, but they do not prove the backend parses and indexes properly. Integration tests must run a **real logger/backend/collector/indexer**, emit an event with a unique ID, and poll with a condition and finite timeout. Never use `Thread.sleep(1000)` as a guarantee that an event is searchable.

When comparing log counts with metrics, distinguish request count, exception attempts, retries, and log event count. One request can produce multiple logs; sampling or duplication will cause counts to diverge per policy.

## 16. Workflow for Writing Effective Queries

Start from the question and choose the query approach accordingly:

1. **State the question:** “Which 5xx requests came from `checkout-api` after deployment `1.2.0` in the last 10 minutes?”
2. **Select scope:** service, environment, route, version, and instance if needed.
3. **Select time window:** use event time consistently, with enough margin for ingest lag and clock skew.
4. **Select condition types:** equality for fields, range for time/numbers, text/regex only when schema is truly missing.
5. **Minimize returned data:** fetch only timestamp, event name, severity, error code, request ID, and sanitized message; limit rows/pages.
6. **Group before reading details:** identify top error codes/routes or highest-failing versions, then open a few representative requests.
7. **Build the timeline:** expand conditions by request/trace ID, removing the severity filter so related `INFO`/`WARN` events are not missed.
8. **Check exclusion conditions:** sampling, log level, missing fields, 404/unmatched routes, permission/index errors, and late arrival.
9. **Save named queries:** dashboards or saved searches, with schema/timezone descriptions and an owner for team reuse.
10. **Verify impact:** compare against request/error metrics and independent data sources before concluding the root cause.

Standardize field names across services and maintain a mapping table if multiple backends use different schemas. Common search queries should have tested examples matching the exact backend and version in internal project documentation.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Searching only for `ERROR` in message | Misses errors with other codes or matches wrong text | Query structured severity/event/error code fields |
| Searching entire retention with broad wildcards | Slow, wastes resources and money | Narrow time/service first, limit rows |
| Using raw URL as route/metric label | Cardinality explodes by ID and may leak data | Use matched route template |
| Forgetting event time vs. ingest time difference | Misses late-arriving logs | Check time field and ingestion lag |
| Assuming request ID propagates across threads automatically | Async logs lack or have wrong correlation | Context propagation + cleanup |
| Counting `ERROR` logs as failed requests | Retries/rethrows/duplicates skew counts | Measure final outcome metric at boundary |
| Assuming a trace ID means the trace was stored | Tracing uses sampling | Use logs independently, check trace sampling |
| Using text query instead of exact-field query | Analyzer/tokenization yields wrong results | Use keyword/exact field when needed |
| Reading all tenants' logs with one shared permission | Risk of data exposure | RBAC/IAM and tenant isolation |
| Logging raw tokens/secrets in query/path | Data leak, hard to purge all copies | Never emit secrets; redaction/retention |
| Assuming unsearchable log means never emitted | Could be index/permission/ingest loss | End-to-end probes and self-metrics |
| Confusing transport duplicates with semantic duplicates | Double-counting and misdiagnosis | Event ID and log owner/event name |
| Skipping schema tests on backend changes | Saved searches/dashboards break silently | Contract tests and versioned schemas |
| Overusing regex on structured fields | Complex, resource-heavy queries | Index/field equality, bounded labels |
| Checking logs without metrics/traces | Missing view of impact and causality | Correlate all three observability signals |

## 18. Checklist for a Java Service

- [ ] Does every important log have `timestamp`, severity, service/environment, event name, and required metadata?
- [ ] Does the structured encoder produce valid JSON, escape newlines/quotes, and preserve exception details safely?
- [ ] Does the log backend parse searchable fields instead of storing JSON as a single message string?
- [ ] Can `ERROR`/`WARN` events be searched by time window, service, operation, error code, and deployment version?
- [ ] Can a timeline be reconstructed across services using request ID/trace ID?
- [ ] Do routes use templates, avoiding raw paths/dynamic IDs in metric labels or high-cardinality stream labels?
- [ ] Is event timestamp distinguished from ingest timestamp, with known ingestion lag and retention?
- [ ] Do queries enforce scope/time/page limits instead of defaulting to broad wildcards?
- [ ] Are sensitive queries governed by role/tenant/environment access control and access auditing?
- [ ] Are secrets and unnecessary PII excluded from logs, with appropriate redaction/allowlists on raw paths/queries/messages?
- [ ] Are sampling, level filtering, retries, duplicates, dropped logs, and collector errors observable?
- [ ] Are there integration tests emitting canary events and searching them back in the backend with a timeout, not just console tests?
- [ ] Do saved queries and dashboards have owners, and are schemas/versions checked on upgrades?
- [ ] Is there a workflow from metric spike → structured log search → request timeline → trace and root cause?

**Remember:** good **Log search** starts when Java emits the event: recording consistent fields, using correlation IDs, and protecting sensitive data. Next, ensure the pipeline actually ingests, parses, and indexes them, and query with the right time window and backend semantics. **Field search answers “which group is affected”, request/trace search answers “what happened to a single request”, and metrics and traces verify the scope and root cause of the incident.**

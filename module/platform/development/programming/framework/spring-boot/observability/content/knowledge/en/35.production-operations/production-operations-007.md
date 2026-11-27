# Controlling Storage Costs

Observability helps engineering teams understand what is happening inside an application, but every metric sample, log event, and trace span creates data that must be transmitted, processed, indexed, and retained. As traffic grows, a metric with too many tags or a log emitted on every request can cause costs to rise much faster than expected.

Controlling storage costs is part of Spring Boot operations. The goal is to retain enough data to detect issues, investigate errors, and meet operational requirements while bounding duplicates, cardinality, sampling, retention, and index volume. You must look at the entire lifecycle—from Micrometer Observation and in-app instrumentation, through Collectors/exporters, to the storage backend.

## 1. Understand What Drives Costs

Do not look only at final storage size on disk. An observability platform typically bills on one or more of these factors:

- **Ingestion:** bytes or events sent into the backend per day.
- **Active time series:** metrics with many label value combinations create many series, increasing ingest, memory, and query costs.
- **Indexes and metadata:** indexed logs, traces, and attributes consume extra storage and processing resources.
- **Retention:** the longer data is kept, the larger total storage footprint becomes.
- **Replication and high availability:** data replicas improve durability and availability at the cost of extra resources.
- **Query and compute:** broad queries, overly frequent dashboard refreshes, heavy alert rules, or queries over long retention windows consume CPU and memory.
- **Network and processing:** cross-region data transfer, transforms, enrichment, compression, and Collector processing also carry cost.

The three signals grow differently:

| Signal | Primary Data Unit | Rapid Growth Drivers |
| --- | --- | --- |
| Metrics | Time series and samples over time | Many metric names, high label cardinality, histograms with many buckets, short scrape intervals |
| Traces | Traces and spans | High request rates, many spans per request, high sampling, spans with many attributes |
| Logs | Log events and bytes | Overly verbose log levels, repetitive events, large payloads, indexing many fields |

A data reduction decision inside the application cuts costs across every downstream layer. Conversely, simply expanding backend capacity often masks root causes like unbounded metric tags or debug logging left enabled indefinitely.

## 2. Estimate Data Volume Before Setting Budgets

Rough estimates reveal which component dominates cost. The formulas below use raw data sizes to compare options; actual storage depends on encoding, compression, indexing, replication, and how your backend bills.

### Metrics

Daily samples can be estimated as:

\[
\text{samples/day} \approx \text{active series} \times
\frac{86\,400}{\text{scrape interval (seconds)}}
\]

For example, 10,000 series scraped every 15 seconds generate roughly 57.6 million samples per day. If cardinality pushes active series to 100,000, samples jump to roughly 576 million per day even with the same scrape interval.

### Traces

Spans per second can be estimated as:

\[
\text{spans/sec} \approx \text{requests/sec} \times
\text{spans/request} \times \text{sampling probability}
\]

Daily raw volume is estimated by multiplying spans per second by average span size and 86,400 seconds. For example, a service handling 300 requests/second with an average of 20 spans/request at 10% sampling produces about 600 spans/second. At an average of 700 bytes per span, raw span volume is roughly 36.3 GB/day before compression, indexing, and replication.

### Logs

\[
\text{bytes/day} \approx \text{events/sec} \times
\text{average event size} \times 86\,400
\]

For example, 200 log events/second averaging 500 bytes equals about 8.64 GB/day of raw data. A long stack trace or large JSON payload can raise the average size significantly.

These calculations are budgeting models, not exact billing forecasts. When measuring in practice, pull actual ingestion, active series, span/event size, index size, and compression ratios from your backend. Measure across both peak and off-peak hours rather than treating one moment as representative of an entire day.

## 3. Reduce Metric Cardinality at Instrumentation Time

Cardinality is the number of distinct label value combinations on a metric. If `http.server.requests` has `method`, `route`, `status`, and `region` dimensions, the number of series can grow as the product of each dimension's distinct values. Adding a label whose value varies on almost every request can trigger a sharp spike in series count.

Attributes suited for metrics usually have a bounded domain:

| Good to Use | Avoid as Metric Tags |
| --- | --- |
| HTTP methods like `GET`, `POST` | Full URLs with free-form query strings |
| Route templates like `/orders/{id}` | Raw paths containing actual order IDs |
| Status classes like `2xx`, `4xx`, `5xx` | Exception messages or stack traces |
| Bounded regions or environments | User IDs, emails, session IDs, request IDs |
| Stable operation names | Operation names concatenated from input data |

Never use trace ID, span ID, user ID, order ID, or tokens as metric tags. Those values create high cardinality and may contain sensitive data. When you need to trace a specific request, use the trace ID in logs/traces or backend-supported exemplars.

### Distinguishing low-cardinality and high-cardinality in Micrometer Observation

Micrometer Observation lets you attach key-values to an Observation. Low-cardinality key-values can become metric tags, so they should hold only bounded, stable values. High-cardinality key-values are intended for detailed data in traces or suitable handlers; they should not become metric tags.

For example, a business operation can attach a stable name and outcome category:

```java
Observation.createNotStarted("order.submit", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .lowCardinalityKeyValue("result", "accepted")
        .observe(() -> orderService.submit(command));
```

`channel` and `result` should only be used this way when their value sets are controlled. Never add `command.getOrderId()` or `command.getCustomerId()` as low-cardinality key-values. If an identifier is needed for investigation and permitted to be recorded, evaluate placing it on spans as a high-cardinality attribute with restricted access and retention. High cardinality still increases trace size and index cost.

Metric names and Observation names must remain stable. Never build dynamic metric names from customer names, specific endpoints, or exceptions. For HTTP servers, prefer route templates over raw paths; verify your framework's conventions and filters so routes with IDs do not generate thousands of distinct values.

### Set cardinality limits and track changes

Track active series by metric name, job, service, and environment. Alert when a metric grows rapidly or exceeds budget. Before adding a new label, estimate the maximum number of combinations before deploying. A tag with 20 values added to a metric that already has 50,000 series can multiply series count significantly depending on combination distribution.

Never delete a label purely for high cardinality if alerts or SLOs rely on it. Identify which queries use that label, find a bounded alternative dimension, or move detailed data to traces/logs. Changing labels can also create new series and split historical dashboards in two; update queries and alert rules at the same time.

## 4. Control Histograms and Metric Resolution

Histograms are valuable for latency because they allow computing aggregated percentiles across multiple instances. However, classic bucketed histograms create a separate series per bucket, plus `_sum` and `_count`. A histogram with many buckets and many tag combinations can multiply series count rapidly.

Choose buckets around measurement goals:

- Define SLOs or latency alert thresholds before adding buckets.
- Place higher bucket resolution near critical thresholds; you do not need dense buckets across the entire range.
- Keep identical bucket configurations across instances so distribution aggregation stays meaningful.
- Enable histograms only on metrics that genuinely need latency distributions; do not enable them blanket-wide on every timer or operation.
- Multiply bucket counts by tag combinations to estimate active series.

An example Spring Boot configuration enabling histograms for HTTP server request duration:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Metric names depend on active conventions and instrumentation; verify the exact name in the metrics endpoint or backend before applying. This setting can expand series count, so account for both buckets and tag combinations. If your backend supports native histograms or another histogram representation, evaluate cost and compatibility across the full pipeline before choosing.

Micrometer can also compute client-side percentiles for certain meters. Client-computed percentiles cannot be aggregated across instances the way histogram buckets can. Choose distribution types based on query needs and SLOs rather than enabling multiple representations simultaneously just for extra charts.

### Use exemplars to link metrics to traces

Exemplars can store a trace ID reference alongside a histogram observation so operators can jump from a latency metric directly to a sample trace. This enables investigating specific requests without adding trace ID as a label on every metric sample. Exemplars require support from instrumentation, registry/exporter, and backend; verify your pipeline before relying on them.

## 5. Choose Sampling for Distributed Tracing

Trace cost depends on retained requests, spans per request, and span size. Sampling is one of the most direct levers to control volume, though cutting sampling too aggressively risks missing rare or failing traces.

### Head-based sampling

Head-based sampling decides whether to keep a trace when it begins. In Spring Boot configurations supporting Micrometer Tracing, sampling probability can be set with:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

`0.10` illustrates a 10% rate. Verify your Spring Boot version, tracing bridge, and actual sampler setup; sampling probability is not a guarantee that all error or slow traces are kept. When a request is sampled at the head, downstream services must continue the same trace context and honor the sampling decision so data is not fragmented.

Head-based sampling is simple with predictable costs, making it a good fit for high traffic needing a representative sample. Its limitation is that when deciding, the system does not yet know if the request will be slow or fail; a rare error trace can still be dropped.

### Tail-based sampling

Tail-based sampling evaluates a trace after the Collector receives enough of its spans. Policies can retain traces with errors, durations above a threshold, or critical operations while dropping a share of routine successful traces.

Tail sampling fits cases where rare but high-value diagnostic traces must be prioritized. It requires the Collector to hold state during the wait window, route all spans of the same trace to the same processing node, and enforce memory bounds. With insufficient resources or spans scattered across collectors, tail-sampling decisions can be wrong or lose traces.

### Combine sampling policies

A production strategy might keep a baseline percentage of successful traces, prioritize error and slow traces with tail sampling, and apply tailored policies for critical operations. Avoid overlapping sampling rules with unclear precedence that retain far more data than planned.

When reducing sampling, ask:

- Are enough traces retained to investigate p95/p99 latency and rare errors?
- Are traces captured for checkout, login, or high-impact operations?
- Is sampling consistent across services and async boundaries?
- Does the Collector have enough memory, CPU, and trace-aware routing for tail sampling?
- Does actual post-sampling span volume match the budgeted forecast?

Never lower sampling probability just to fix a rising bill without investigating the cause. Instrumentation emitting 200 spans per request or spans carrying huge payloads may need optimization first.

## 6. Reduce Trace Volume and Span Size

A trace should model operation boundaries that have diagnostic value. Instrumenting every tiny method or creating unnecessary nested spans inflates span count without clarifying root causes.

Ways to keep traces lean:

- Instrument meaningful boundaries such as HTTP servers/clients, database calls, message publish/consume, and key business operations.
- Avoid creating spans for getters, helpers, or tight loops if they do not help pinpoint bottlenecks.
- Use stable span names; never embed order IDs, user IDs, or dynamic values in span names.
- Record only attributes used for filtering or explaining behavior; avoid attaching full request/response payloads.
- Avoid repeating full stack traces or exception messages across multiple spans when existing status and events already convey the error.
- Eliminate duplicate instrumentation where one call produces two equivalent spans.
- Verify propagation across executors and message brokers so new disconnected traces or double-instrumented spans are not created.

In Micrometer Observation, create Observations only for operations that need observing. Use low-cardinality key-values for bounded metric dimensions; add high-cardinality key-values to traces only when genuinely needed and permitted by data policy.

## 7. Control Log Volume and Indexing Cost

Logs often balloon when debug logging stays on in production, when each request emits many lines, or when apps log full payloads. Identify which logs aid operations and which merely duplicate information already captured in metrics or traces.

### Choose log levels intentionally

| Level | Production Usage | Example |
| --- | --- | --- |
| ERROR | Failures requiring attention or failing an operation | Dependency timeout preventing request completion |
| WARN | Abnormal condition to watch that still recovered | Retry succeeded after a transient error |
| INFO | Key lifecycle or business events at controlled frequency | Service startup, applied deployment configuration |
| DEBUG | Diagnostic detail enabled for short windows | Non-sensitive internal branch decision values |
| TRACE | Very fine-grained detail enabled only under strict control | Detailed library control-flow tracing |

Do not emit an INFO log on every function call when metrics and traces already capture call counts and durations. Use WARN selectively for retried errors; if a dependency fails continuously, logging WARN on every retry can trigger a log storm. Apply rate limiting or periodic summaries for repeated errors.

### Log structured data and avoid large payloads

Prefer JSON or structured logging with consistent fields such as timestamp, level, service, environment, operation, trace ID, and span ID. Avoid logging full request objects, responses, headers, or personal data. Logging error codes, error types, and a few approved attributes is usually more helpful than full payloads.

Keep indexed fields to what is necessary. Indexing every JSON field drives up storage and query costs; rarely filtered fields can stay in unindexed log bodies if the backend supports it. Use consistent schemas and parsing so the same concept is not stored under multiple field names.

### Sampling and rate limiting for logs

Sampling suits repetitive high-frequency logs, such as an identical debug message on every successful request. Never blindly sample security logs, audit logs, severe errors, or policy-mandated events. For repetitive logs, you can emit a sample alongside an aggregated counter to preserve frequency visibility.

If sampling is applied, record the sampling rate or method in operational metadata so investigators know logs are partial. Never use sampling to hide errors or distort audit numbers. Compliance logs must follow dedicated retention and integrity policies.

## 8. Filter and Process Data at the OpenTelemetry Collector

The Collector is a convenient choke point to enforce centralized policies before sending data to backends. Common processors include:

- **Memory limiter:** bounds memory usage and applies appropriate backpressure as the Collector nears overload.
- **Batch:** groups telemetry into batches to cut transport overhead and improve export efficiency.
- **Filter:** drops unnecessary signals, spans, metrics, or logs according to explicit conditions.
- **Attributes/resource processor:** normalizes or strips unnecessary attributes while keeping resource metadata consistent.
- **Tail sampling:** keeps or drops traces based on status, duration, and attributes after receiving spans.
- **Transform:** standardizes data, strips disallowed fields, or trims payloads before export.

The Collector does not replace controls inside the application. If an application emits excessive series or spans, that data still consumes CPU, network, and memory in transit and at the Collector before being dropped. Cut cardinality and redundant instrumentation at the source, then use the Collector for centralized policy enforcement.

When configuring processors, verify ordering carefully. For instance, a filter placed before tail sampling might drop spans needed to identify error traces; a transform deleting attributes before sampling can break sampling policy conditions. Ensure spans of the same trace route to the same tail sampler pool with sensible wait timeouts.

Never drop data solely because a metric or span name looks unfamiliar without checking dashboards, alerts, SLOs, and investigation use cases. Every filter rule needs an owner, rationale, scope, and rollback plan.

## 9. Design Retention Around Operational Value

Keeping all data at full granularity for long periods is rarely necessary. Retention should reflect investigation speed, audit rules, SLOs, legal policies, and historical query needs.

A tiered model can include:

| Storage Tier | Suitable Data | Purpose |
| --- | --- | --- |
| Hot | Near-real-time detailed metrics, recent logs/traces | Dashboards, alerts, and active incident response |
| Warm | Aggregated metrics, logs/traces needed for shorter-term lookups | Trend analysis and post-incident reviews |
| Cold/archive | Audit data or records retained long-term by policy | Rare lookups and compliance retention |

No single retention day count fits every system. Set explicit durations per signal and environment. Traces may need shorter hot retention than aggregated metrics; audit logs may need longer retention than debug logs. Development environments rarely need detailed data kept as long as production.

### Metrics: downsampling and recording rules

Keep high-resolution detailed metrics for the window needed by near-real-time investigations. Beyond that window, use recording rules or backend downsampling to keep aggregated series at coarser intervals. For example, 15-second data can be rolled up into 5-minute windows for long-term trend reporting.

Downsampling discards short-term detail. Do not use rolled-up series to answer questions requiring sub-minute spikes or raw percentiles if the aggregation does not preserve distributions. Keep series required for SLOs, capacity planning, and reporting at appropriate resolution.

### Logs and traces: retention by event type

Different retention periods can apply to application logs, audit logs, security events, and debug logs. For traces, error traces or tail-sampled traces can be kept longer than routine successful traces if the backend supports attribute-based policies. Verify policies do not accidentally purge traces needed to reconstruct incidents.

Before deleting or tiering data, verify legal, contractual, security, and recovery requirements. Archive tiers may be cheaper yet slower to query or require restore workflows; document those constraints for operations teams.

## 10. Control Queries, Dashboards, and Export Pipelines

Costs do not live in ingest volume alone. Overly frequent dashboard refreshes, unbounded time-range queries, or alert rules scanning every label combination can consume substantial compute.

Key principles:

- Set sensible default time ranges; do not query full history when a dashboard only needs the last hour.
- Avoid broad regex queries or joins across high-cardinality dimensions unless necessary.
- Use recording rules for repeatedly evaluated aggregate queries.
- Lengthen refresh intervals on infrequently watched dashboards; not every chart needs to auto-refresh every few seconds.
- Enforce concurrency limits, timeouts, and max query ranges per user or workspace when supported by the backend.
- Monitor expensive alert rules, query timeouts, and high-scan-volume queries.
- Tune batching and compression on exporters/Collectors within backend limits; avoid unbounded batch growth that inflates memory and latency.

In Spring Boot, a metrics exporter's `step` determines export cadence in some registries. Shorter steps increase send frequency and processing overhead; longer steps lower observation granularity. Pick intervals based on alerting and backend needs rather than choosing the smallest value just for faster dashboard updates.

## 11. Budget Allocation and Change Governance

Costs must be attributed to services, teams, environments, and signals to see where spend originates. Use stable resource attributes such as service name, environment, region, and version when the backend supports metadata-based cost attribution. Avoid putting user identifiers or sensitive business data into cost-allocation labels.

Establish budgets around trackable indicators:

- Active metric series and daily samples.
- Daily ingest bytes or events per signal.
- Spans per request, trace sampling rate, and total retained spans.
- Log events/second, average event size, and log distribution by level.
- Retention days, index size, storage bytes, and query compute.
- Share of data filtered, dropped, or failing export.

When an indicator spikes abnormally, trace it back by service, metric name, label, logger, operation, or Collector pipeline. Do not simply raise global quotas or cut retention across the board; blanket changes penalize services operating within budget.

Any change with major data impact should be reviewed like an operational change:

1. State the reason and identify the signal driving cost.
2. Estimate data volume before and after the change.
3. List affected dashboards, alerts, SLOs, and investigation workflows.
4. Test on a small service or environment first.
5. Watch ingestion, dropped data, latency, and diagnostic capability after rollout.
6. Record the owner, review date, and rollback plan.

## 12. Example: Reducing Trace and Metric Costs for the Checkout Service

Suppose `checkout` handles 300 requests/second with an average of 20 spans/request. At 100% sampling, the system generates about 6,000 spans/second. At 10% sampling, it drops to roughly 600 spans/second. Assuming 700 bytes/span on average, raw span volume falls from about 362.9 GB/day to 36.3 GB/day before compression, indexing, and replication.

However, if every span still carries 30 attributes—many of which are payloads or unnecessary IDs—average span size remains large. Therefore, operations also:

1. Keep spans on HTTP, database, and payment boundaries; remove instrumentation from tiny helpers that create redundant spans.
2. Strip payloads and attributes unused for filtering or debugging; keep status, duration, service, and essential operations.
3. Combine baseline sampling with tail sampling to prioritize error traces and traces exceeding latency thresholds.
4. Keep route templates in metric tags; remove order IDs from metrics and retain approved references only in traces where needed.
5. Track active series, span volume, and retained error-trace ratio to verify investigation quality.

For metrics, suppose the service has 10,000 active series at a 15-second scrape interval—roughly 57.6 million samples/day. Adding an `orderId` tag could multiply series by unique order counts; shrinking the scrape interval to 5 seconds would triple sample volume. Restrict dimensions to route, method, status class, and other bounded tags; enable histograms only on latency metrics used for SLOs.

This example shows how multiple levers work together. Never slash sampling so far that error traces disappear, or disable histograms needed for SLO percentiles. Validate every change using ingestion metrics alongside incident detection and debugging capability.

## 13. Common Mistakes

- **Slashing retention globally as soon as costs rise:** can wipe out required audit or historical data. Differentiate by signal and retention policy.
- **Uniformly sampling traces without considering request type:** can miss rare errors and critical flows. Consider tail-sampling policies and baseline reference traces.
- **Putting IDs into metric tags for easier debugging:** causes cardinality explosions. Use trace/log correlation or exemplars.
- **Enabling histograms on every meter:** creates many bucket series without value for every operation. Enable only on metrics requiring distribution analysis.
- **Logging INFO or DEBUG on every request:** inflates log volume and buries critical events. Rely on metrics, traces, proper log levels, and rate limiting.
- **Filtering at the Collector while leaving wasteful instrumentation in apps:** still burns CPU, network, and memory before data is dropped. Optimize at the source.
- **Dropping attributes before tail sampling:** can strip conditions needed to retain error or slow traces. Verify processor ordering.
- **Measuring storage bytes alone:** overlooks active series, indexes, query compute, replication, and network transfer. Track all cost drivers.
- **Changing emitted data without updating dashboards/alerts:** can trigger false alerts or blind spots. Review queries alongside instrumentation changes.

## 14. Storage Cost Control Checklist

- [ ] Measured ingestion, active series, span volume, log volume, index size, and retention per signal.
- [ ] Defined daily data estimates and budgets per service, environment, or team.
- [ ] Metric tags use only bounded-domain dimensions; routes use templates.
- [ ] No trace IDs, user IDs, order IDs, tokens, or payloads appear in metric tags.
- [ ] Histograms are enabled only where needed; bucket counts align with SLOs and series budgets.
- [ ] Trace sampling combines a baseline rate with policies to retain error/slow traces as needed.
- [ ] Span names are stable, instrumentation has no duplicates, and attributes are bounded.
- [ ] Log levels, log sampling, and rate limiting are controlled; audit/security logs follow separate retention.
- [ ] Collectors have tuned batching, memory limits, filters, and tail sampling; processor order is verified.
- [ ] Retention, downsampling, and archiving match investigation, SLO, and data-policy requirements.
- [ ] Dashboards, alerts, and queries use reasonable time ranges, refresh intervals, and compute budgets.
- [ ] Alerts exist for abnormal spikes in cardinality, ingestion, or dropped data.
- [ ] Every data-reduction change is checked for impact on alerts, SLOs, and investigation capability.

Effective observability cost control starts by emitting only valuable data, then bounding how it is sampled, processed, indexed, and stored. In Spring Boot, Micrometer Observation governs where metrics and spans originate; the Collector enforces centralized policies; and the backend manages indexing, retention, downsampling, and querying. Track both cost and signal quality so the system continues detecting and explaining incidents as scale grows.

# Monitoring Latency, Errors, Throughput, and Synchronization Lag

A Spring Data Elasticsearch system can continue returning HTTP 200 while search experience has degraded, synchronized data is delayed, or part of a bulk batch has failed. Watching only green node status and total request counts is insufficient to tell whether the application meets its requirements. You must observe at least four signal groups: **latency, errors, throughput, and synchronization lag**.

These metrics must be measured on both the application side and the Elasticsearch side. The application knows how long users actually wait, how many items succeed/fail, and when events pass through each step. Elasticsearch reports search/index processing times, thread pool pressure, heap, refreshes, merges, and shards. Combining both sides determines whether slowdowns sit in the client/network, service, queues, cluster, or sync pipeline.

In Spring Boot, Micrometer and Actuator provide a convenient foundation for emitting metrics; tracing can use Micrometer Observation/OpenTelemetry; Elasticsearch exposes Node Stats, Index Stats, and Cluster APIs. For asynchronous synchronization, record timestamps or offsets from source commit until the document becomes searchable, rather than measuring only the duration of calling `save()`.

## 1. Four signal groups to monitor

| Group | Question to answer | Example metrics |
|---|---|---|
| Latency | How long must users/jobs wait? | Search p50/p95/p99, bulk request duration, queue wait |
| Errors | How many operations fail and why? | HTTP 4xx/5xx, 409 conflicts, 429 rejections, bulk item failures |
| Throughput | How much work does the system complete per unit of time? | Search requests/s, documents indexed/s, events processed/s, bytes/s |
| Sync lag | How long does source data take to appear in search? | Event age, consumer lag, source-to-search-visible duration |

Do not optimize one group in isolation. Raising concurrency can boost throughput briefly while driving up p99 latency, 429s, and queue depth. A pipeline can write to Elasticsearch very quickly yet search still shows stale data due to refresh intervals or consumer lag.

## 2. Distinguishing latency across layers

A search operation from a client traverses multiple layers:

```text
Client
  |
  v
API gateway / load balancer
  |
  v
Spring WebFlux / MVC controller
  |
  v
Service + query construction
  |
  v
Elasticsearch Java client / connection pool
  |
  v
Network -> coordinating node -> shard execution
  |
  v
Response decode -> DTO mapping -> HTTP response
```

What users perceive is end-to-end latency. It includes wait and processing times across all the layers above. Measuring only Elasticsearch's returned time is insufficient to represent the entire request.

### Latencies to separate

- **HTTP/API latency:** from when the application receives the request until it sends the response.
- **Service latency:** business logic, validation, authorization, and mapping time.
- **Elasticsearch client latency:** client call time, including connection wait, network, and waiting for server response.
- **Elasticsearch `took`:** time Elasticsearch reports spending to process the search request; excludes full wait time in gateways, application, network, and response mapping.
- **Queue wait:** time an event/job waits before a consumer starts processing.
- **Processing latency:** time a consumer spends transforming data and sending write requests.
- **Search visibility lag:** span from source commit until data becomes searchable after refresh.

### Analysis example

Suppose the search API has p95 of 900 ms, while Elasticsearch `took` p95 is 180 ms. The ~720 ms gap may sit in gateways, connection acquisition, network, service processing, response mapping, or auxiliary calls. You cannot pinpoint it by subtraction alone; tracing and per-span metrics are needed to find the slow segment.

If API latency and `took` climb together, examine queries, shards, thread pools, and cluster resources. If `took` stays flat while API latency climbs, focus on the application, connection pools, gateways, network, or payload/serialization.

## 3. Use percentiles instead of looking only at averages

Average latency helps reveal broad trends but can hide very slow requests. For search APIs, track:

- **p50:** half of requests are faster than or equal to this value.
- **p95:** 95% of requests are faster than or equal to this value.
- **p99:** 99% of requests are faster than or equal to this value; captures tail latency.
- **Max:** slowest request in the window, sensitive to outliers.

Example:

| Metric | Duration |
|---|---:|
| p50 | 80 ms |
| p95 | 350 ms |
| p99 | 1,800 ms |
| Max | 5,200 ms |

The average may look acceptable while a subset of users wait several seconds. Therefore, SLOs should typically target p95/p99 and be broken down by endpoint/workload.

### Separate workloads

Do not lump every request into a single timer. Interactive search, autocomplete, dashboard aggregations, exports, and bulk ingestion have very different characteristics. Track separately by low-cardinality operation or endpoint to see which workload drives tail latency.

## 4. Define SLIs and SLOs before setting alerts

An SLI (Service Level Indicator) is a metric reflecting how well a service meets expectations. An SLO (Service Level Objective) is the target set for an SLI over a period of time.

Illustrative examples:

| SLI | Example SLO | Scope |
|---|---|---|
| Search API p95 | Under 400 ms | Interactive search requests |
| Search success rate | Above 99.9% | Valid requests, excluding client input errors |
| Bulk item success | Above 99.5% within a window | Item ingestion before retry/DLQ |
| Projection freshness p95 | Under 30 seconds | Source commit to search-visible |
| Consumer backlog age | Under 2 minutes | Continuous sync event stream |

These numbers are examples only. Choose SLOs based on product requirements, real workloads, and operational capacity. Never apply one uniform threshold to both interactive search and multi-million-document exports.

### Defining success rate clearly

An HTTP 200 from the Bulk API does not mean all items succeeded. For ingestion, maintain two indicators:

- Bulk request success: request to Elasticsearch completed at HTTP/client level.
- Bulk item success: successful actions divided by total submitted actions.

Additionally, track the percentage of items eventually succeeding after retries. Keep denominators distinct so dashboards never conceal partial failures.

## 5. Measuring latency in Spring Boot with Micrometer

Micrometer provides `Timer` to record durations and counts. With Spring Boot Actuator, metrics can be exposed to monitoring backends such as Prometheus depending on configured registries.

Common Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Spring Boot dependency management should govern compatible Micrometer versions. Do not pin a different Micrometer version outside the BOM without clear reason.

Example endpoint configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Expose metrics endpoints only to authorized monitoring networks/roles. Never expose metrics, health details, or internal Elasticsearch info to the public Internet without proper authentication and network policies.

## 6. Recording Timers for Spring Data Elasticsearch operations

Example timing saving a document via `ElasticsearchOperations`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductWriter {

    private final ElasticsearchOperations operations;
    private final MeterRegistry registry;

    public ProductWriter(
            ElasticsearchOperations operations,
            MeterRegistry registry) {
        this.operations = operations;
        this.registry = registry;
    }

    public ProductDocument save(ProductDocument document) {
        return Timer.builder("app.elasticsearch.write")
            .description("Time spent saving a product document")
            .tag("operation", "save")
            .tag("index", "products")
            .register(registry)
            .record(() -> operations.save(
                document,
                IndexCoordinates.of("products")
            ));
    }
}
```

This example is for synchronous APIs. With reactive APIs, do not wrap `Mono` construction in `Timer.record(Supplier)` and assume the timer measured completion time. You must measure from subscription to terminal signal.

### Timing reactive publishers

Example using `Timer.Sample` and `doFinally`:

```java
public Mono<ProductDocument> saveReactive(ProductDocument document) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        AtomicReference<String> outcome = new AtomicReference<>("success");

        return reactiveOperations.save(document)
            .doOnError(error -> outcome.set(classifyOutcome(error)))
            .doFinally(signal -> sample.stop(
                Timer.builder("app.elasticsearch.write")
                    .tag("operation", "save")
                    .tag("outcome", outcome.get())
                    .register(registry)
            ));
    });
}
```

`doFinally` runs when the publisher completes, errors, or cancels, so the timer covers the entire subscription lifecycle. In production, `classifyOutcome` should return a bounded set of values such as `success`, `conflict`, `rejected`, `timeout`, `client_error`, `server_error`, or `cancelled`; never use exception messages as metric tags.

With `Flux`, decide whether the timer measures the whole stream or individual elements. Measuring the whole stream depends on element count and consumer demand; if timing search page requests, wrap the specific request operation.

## 7. Tracking errors with Counters

`Counter` fits counting failures or events by category:

```java
Counter.builder("app.elasticsearch.errors")
    .description("Elasticsearch operation failures")
    .tag("operation", "bulk")
    .tag("error_type", "rejected")
    .register(registry)
    .increment();
```

Do not create a new counter per exception message. Tags must belong to a small, stable set of values to avoid unbounded cardinality growth.

### Error rate

You can count total operations and failed operations separately:

```java
Counter.builder("app.elasticsearch.operations")
    .tag("operation", "search")
    .register(registry)
    .increment();

Counter.builder("app.elasticsearch.errors")
    .tag("operation", "search")
    .tag("error_type", "timeout")
    .register(registry)
    .increment();
```

Error rate over a time window:

\[
\text{Error rate} = \frac{\text{failed operations}}{\text{total operations}} \times 100\%
\]

For bulk, also compute the item failure rate:

\[
\text{Bulk item failure rate} = \frac{\text{failed items}}{\text{submitted items}} \times 100\%
\]

Do not mix HTTP request failures and item failures because they have different denominators.

## 8. Avoiding high metric cardinality

Metric labels/tags partition time series. Placing values that grow almost infinitely into tags can exhaust memory in Prometheus or monitoring backends.

Avoid tags such as:

- Document IDs.
- User IDs or emails.
- Request IDs/correlation IDs.
- Verbatim query text.
- Exception messages.
- Exact timestamps.
- URLs containing dynamic IDs.

Use low-cardinality tags:

- `operation=search|save|bulk|delete`.
- `outcome=success|error|cancelled`.
- `error_type=timeout|rejected|conflict|mapping|other`.
- `workload=interactive|dashboard|bulk_import`.
- `index_alias=products|orders` if the alias set is small and stable.

Per-request details belong in traces/logs with appropriate sampling and retention, not metric labels.

## 9. Measuring throughput

Throughput shows how much work completes per unit of time. Depending on the workload, measure multiple throughput signals:

- Search requests per second.
- Documents indexed per second.
- Bulk requests per second.
- Bulk items succeeded per second.
- Events consumed per second.
- Bytes indexed per second.
- Search hits returned per second if that is a product metric to observe.

Example:

\[
\text{Documents/sec} = \frac{\text{successful indexed documents}}{\text{elapsed seconds}}
\]

For bulk, count successful items rather than only counting bulk requests. A request with 500 items and a request with 5 items do not represent the same throughput.

### Counters and rates

A Micrometer `Counter` increments by the number of successful documents. Metric backends like Prometheus compute rates over time windows. If recording throughput directly, define exact units and measurement intervals to avoid confusing cumulative counters with instantaneous rates.

Example:

```java
Counter.builder("app.elasticsearch.documents.indexed")
    .description("Number of successfully indexed documents")
    .tag("index", "products")
    .register(registry)
    .increment(successCount);
```

Increment `successCount` only after verifying item responses succeeded, not by the number of submitted items.

## 10. Measuring Bulk API throughput and partial failures

The Bulk API can return HTTP 200 while `errors: true`. Therefore, inspect items after each response:

```java
int submitted = response.items().size();
int succeeded = 0;
int failed = 0;

for (BulkResponseItem item : response.items()) {
    if (item.error() == null) {
        succeeded++;
    } else {
        failed++;
        recordBulkItemFailure(item);
    }
}

registry.counter("app.elasticsearch.bulk.items", "outcome", "submitted")
    .increment(submitted);
registry.counter("app.elasticsearch.bulk.items", "outcome", "success")
    .increment(succeeded);
registry.counter("app.elasticsearch.bulk.items", "outcome", "failure")
    .increment(failed);
```

The `BulkResponseItem` type and accessors depend on the client/API used; this snippet illustrates the counting pattern. In real implementations, map the response item type from your version of the Elasticsearch Java API Client or Spring Data response type.

Classify failed items by error type and track retries separately:

- Submitted items.
- Items succeeding on first attempt.
- Retried items.
- Items succeeding after retry.
- Permanent failures/DLQ.
- Items still pending.

This prevents initial throughput from being conflated with eventual throughput after retries.

## 11. Measuring bulk request latency

A bulk job can have high throughput while individual batches take too long. Measure each bulk request's duration and analyze alongside batch size:

- Batch item count.
- Payload bytes.
- Request duration p50/p95/p99.
- Item success/failure counts.
- Retry count.
- Number of concurrent bulk requests.

Do not place exact batch sizes or document IDs into metric tags if they create too many time series. Use histograms for duration and record batch sizes/payload bytes in logs or suitable distribution metrics.

If p95 climbs as batch size increases without a matching throughput gain, batches may already be too large. If latency stays stable while throughput is low and cluster CPU/resources have headroom, try cautiously increasing concurrency.

## 12. Monitoring synchronization lag

Synchronization lag is the elapsed time from when data changes in the source of truth until that change is reflected in the search projection and becomes queryable.

An event-driven pipeline may include these milestones:

```text
Source transaction commit
          |
          v
Outbox event created
          |
          v
Event published to broker
          |
          v
Consumer receives event
          |
          v
Projection transformation
          |
          v
Elasticsearch write acknowledged
          |
          v
Index refresh
          |
          v
Document becomes searchable
```

Useful timestamps:

- `source_committed_at`: when the source of truth committed the change.
- `event_created_at`: when the event was created.
- `event_published_at`: when the publisher sent the event.
- `event_received_at`: when the consumer received the event.
- `projection_started_at`: when processing began.
- `elasticsearch_acknowledged_at`: when the write was acknowledged.
- `search_visible_at`: when the document became searchable, if measured reliably.

You do not necessarily need to store all timestamps inside production documents. They can be recorded in event metadata, tracing spans, or logs/metrics. What matters is consistent definitions and synchronized clocks.

## 13. Breaking sync lag into segments

Total sync lag can be decomposed into components:

\[
L_{total} = L_{publish} + L_{queue} + L_{processing} + L_{write} + L_{refresh}
\]

Where:

- `L_publish`: from source commit until the event is published.
- `L_queue`: time the event sits in the broker before a consumer receives it.
- `L_processing`: deserializing, loading related source data, mapping projections, and preparing bulk actions.
- `L_write`: time Elasticsearch takes to process and acknowledge the write.
- `L_refresh`: from write acknowledgement until the document is searchable.

This is an analytical model; actual measurements must define clear timestamp boundaries without double-counting intervals.

### Example

| Component | p95 |
|---|---:|
| Publish | 100 ms |
| Queue wait | 4,000 ms |
| Processing | 250 ms |
| Elasticsearch write | 180 ms |
| Refresh visibility | 900 ms |
| Approximate total | 5,430 ms |

In this example, queue wait is the largest component. Speeding up Elasticsearch writes will not address the primary cause; you must raise consumer capacity, throttle event sources, or drain the backlog.

## 14. Measuring consumer lag and event age

With Kafka, consumer lag is typically expressed as the offset delta between log end offset and consumer committed/current offset. This measures unprocessed record counts, not directly elapsed delay time.

Track both:

- Record/offset lag.
- Age of the oldest waiting event.
- Event processing duration p50/p95/p99.
- Consumer throughput.
- Number of lagging partitions.
- Retry/DLQ counts.

A backlog of 10,000 events may drain in seconds under high throughput, or linger for hours if consumers are stalled. Event age measures freshness more directly than record lag alone.

### Do not measure only the timestamp of the newest event

If consumers process new events quickly while one partition is stuck on an old event, the timestamp of the most recently processed event can make dashboards look healthy. Observe the oldest unprocessed event or per-partition lag to catch localized bottlenecks.

## 15. Measuring search-visible time

Write acknowledgement and search visibility are two distinct milestones. A successful `index` request does not mean the document immediately appears in search; the document needs a refresh.

Visibility lag can be measured by one of these methods:

- Use `refresh=wait_for` in controlled measurement/test workflows and record the wait time.
- Store event ID/source version in the document, then run bounded search probes by ID/version.
- Measure time from bulk response to the next refresh if suitable instrumentation exists.
- Use a periodic synthetic canary document to measure source-to-search-visible.

Do not run a search probe for every document in production just to measure visibility; that creates unnecessary load. Use sampling or canaries and distinguish direct measurements from estimates.

### `refresh=wait_for` in write flows

`wait_for` waits for the next refresh to make changes searchable. It does not force an immediate refresh like `refresh=true`, though wait times grow if refreshes are delayed or periodic refresh is disabled. Use it selectively where read-after-write is required, rather than adding it to every bulk request merely to improve dashboard lag numbers.

## 16. Measuring sync lag using source versions

Beyond timestamps, business versions help detect stale projections. For instance, the source of truth emits `aggregateVersion=42` while the search document stores `sourceVersion=41`; the projection has not yet applied the latest change.

Metrics to track:

- Number of aggregates whose source version is newer than the projection version.
- Version gap if versions increment monotonically.
- Number of events skipped as stale or duplicate.
- Number of documents missing projections.
- Number of incompatible projection versions.

A version gap does not always equal lost events; versions may increment from changes irrelevant to the projection or coalesced events. Define version semantics clearly before turning it into an SLI.

## 17. Using consistent timestamps and clocks

Computing sync lag by subtracting timestamps across services requires synchronized clocks. If a source machine runs 2 seconds ahead of a consumer machine, calculations can yield negative or skewed lag.

Recommendations:

- Synchronize host/container clocks via NTP or platform time services.
- Store timestamps in UTC, preferring `Instant`.
- Distinguish event time from processing time.
- Record timestamps in a uniform format.
- Handle late-arriving events or skewed source timestamps.
- Use broker offsets/monotonic sequences to gauge backlogs additionally when timestamps are untrusted.

In Java code, inject a `Clock` for easier testing and to avoid scattered time logic.

## 18. Tracking errors by taxonomy

Do not lump every error into a single `error` counter. Error categories carry different operational meanings:

| Group | Example | Meaning | Common action |
|---|---|---|---|
| Validation/client | 400, invalid query, bad mapping input | Invalid request or input data | Fix caller/payload; do not retry blindly |
| Authorization | 401/403 | Insufficient credentials or permissions | Check auth/roles; do not retry continuously |
| Not found | 404 document/index | ID or index does not exist | Check semantics; may be a valid outcome |
| Version conflict | 409 | Document already changed | Reload tokens, evaluate business rules, and conditional retry |
| Rejection/overload | 429, rejected execution | Cluster cannot accept more load | Backoff, reduce concurrency and backlog |
| Timeout/network | timeout, connection reset | Unclear how far the request progressed | Check idempotency before retrying |
| Server/transient | 5xx | Temporary failure or cluster issue | Bounded retry, check cluster |
| Mapping/serialization | mapper parsing, conversion exception | Source incompatible with mapping/model | Fix data or mapping, DLQ if needed |
| Partial bulk | Some items failed | Request partially succeeded | Classify per item |

### Do not retry every exception

Retrying validation or mapping errors will not make them disappear. Retrying conflicts with the same old `if_seq_no`/`if_primary_term` will keep conflicting. Retrying timeouts can repeat an operation that succeeded while the response was lost. Retry policies must be driven by error type and operation idempotency.

## 19. Monitoring Elasticsearch with Node Stats

Elasticsearch provides the Node Stats API to inspect resources and activity per node:

```http
GET /_nodes/stats
```

You can request only specific stat groups to shrink payloads:

```http
GET /_nodes/stats/jvm,process,os,fs,thread_pool,indices,breaker
```

Key groups:

- `jvm`: heap, garbage collection, and memory pressure.
- `process`/`os`: CPU and OS resources.
- `fs`: disk capacity and filesystem activity.
- `thread_pool`: active, queue, and rejected per pool.
- `indices`: search, indexing, refresh, merge, query cache, and request cache.
- `breaker`: circuit breaker trips and estimated usage.
- `indexing_pressure`: memory pressure linked to indexing if supported by version.

Node Stats is cluster/node-level data; combine it with application metrics to see which requests drive load. Avoid polling full stats too frequently or parsing all fields when dashboards need only a handful of signals.

## 20. Monitoring Index Stats

Index Stats helps isolate by index:

```http
GET /products/_stats
```

You can limit retrieved metrics:

```http
GET /products/_stats/indexing,search,refresh,merge,segments,store
```

Useful fields:

| Group | Metrics to watch | Meaning |
|---|---|---|
| `indexing` | `index_total`, `index_time_in_millis`, `index_failed` | Index operation counts, time, and failures |
| `search` | `query_total`, `query_time_in_millis`, `fetch_total`, `fetch_time_in_millis` | Search volume and query/fetch durations |
| `refresh` | `total`, `total_time_in_millis` | Refresh frequency and cost |
| `merge` | `total`, `total_time_in_millis`, `current` | Segment merge activity |
| `segments` | segment count, memory | Segment fragmentation and memory footprint |
| `store` | size | Index storage size |

Counters are typically cumulative since node/index startup or the appropriate reset. When computing rates, subtract across two scrapes for the same node/index over an interval, handling counter resets or node restarts.

## 21. Monitoring thread pools and rejections

When searches or bulk writes slow down, inspect thread pool queues and rejected counts:

```http
GET /_nodes/stats/thread_pool
```

Fields commonly inspected:

- `active`: actively executing threads.
- `queue`: queued tasks waiting.
- `rejected`: rejected tasks.
- `completed`: completed tasks.

Pool names and layout vary across Elasticsearch versions. Never rely on old pool names from another guide without checking the live cluster.

If queues grow steadily, latency rises before rejections appear. If rejections rise, the cluster is already dropping work. Identify which pool is pressured and its corresponding request type; do not simply enlarge queue sizes, as that increases wait times and memory consumption.

## 22. Monitoring indexing pressure, heap, and merges

Indexing pressure reflects memory pressure caused by node indexing activity. Prolonged high heap usage and long GC pauses inflate latency for both searches and writes. Merges burn CPU and I/O when consolidating segments.

When ingestion throughput rises and search latency worsens, inspect simultaneously:

- Indexing pressure and rejections.
- JVM heap usage and GC pauses.
- Current/total merge times.
- Refresh frequency and segment counts.
- Disk I/O and filesystem saturation.
- Shard distribution and hot shards.

Do not conclude "Elasticsearch is slow" solely from high CPU. A bulk workload can turn merges or disk I/O into the bottleneck; an aggregation query can trigger heap pressure; a single hot shard can lag while node averages look normal.

## 23. Cluster health and shard allocation

Cluster Health API:

```http
GET /_cluster/health
```

States:

- `green`: primary and replica shards are all allocated.
- `yellow`: primary shards are allocated, but some replicas are unassigned.
- `red`: at least one primary shard is unassigned; some data may be inaccessible.

Cluster health matters, but it is not a latency/throughput metric. A `green` cluster can still be overloaded, run slow queries, or suffer consumer lag. Conversely, `yellow` in a single-node setup may be the designed state if replicas cannot be placed on the same node.

Also track unassigned shards, relocating shards, and pending tasks when investigating performance shifts.

## 24. Slow logs and query profiling

Elasticsearch search slow logs record query or fetch phases exceeding configured thresholds. Indexing slow logs can record slow index operations. These are tools for investigating specific slow queries/documents.

Slow logs help:

- Spot high-latency queries.
- Separate query phase from fetch phase.
- Identify shards or indices with abnormal workloads.
- Uncover unsuitable mapping/query patterns.

Do not set thresholds too low or log every request; log volume grows fast and adds overhead. Tune for your workload, enable selectively, and protect log contents if queries/sources contain sensitive data.

The Search Profile API explains how Elasticsearch executes a query in detail, though it adds overhead and does not accurately represent normal production latency. Use profiling for targeted investigations rather than enabling it on every request.

## 25. Distributed tracing from API to Elasticsearch

Metrics show trends; traces show which steps a specific request traversed. A search request trace might contain spans:

```text
HTTP GET /products/search
  ├── authenticate-and-authorize
  ├── build-search-query
  ├── elasticsearch.search
  │     ├── connection-acquire
  │     └── client-request
  ├── map-search-hits
  └── serialize-response
```

For ingestion:

```text
consume ProductUpdated
  ├── load-source-data
  ├── build-projection
  ├── elasticsearch.bulk
  ├── inspect-item-results
  └── acknowledge-event
```

Micrometer Observation and OpenTelemetry can connect metrics and tracing per Spring Boot configuration. Span names and auto-instrumentation depend on client/version; if the client does not emit spans automatically, wrap operations with Observation/Timer at the service layer.

### Correlation IDs and trace IDs

Propagate trace/correlation IDs across APIs, events, consumers, and projectors where architecture permits. Events can carry `correlationId` or `causationId` to link source changes to projection updates.

Do not use trace IDs as metric labels. Use them inside logs/traces to look up specific executions.

## 26. Structured logging

Logs should help answer:

- Which operation was slow or failed?
- Which index alias did the request/event belong to?
- How many items and bytes did the bulk batch contain?
- How many items succeeded, retried, or went to DLQ?
- Which source version was processed?
- How long did the event sit in the queue?
- What is the trace/correlation ID?

Structured log example:

```json
{
  "event": "elasticsearch.bulk.completed",
  "index_alias": "products-write",
  "batch_size": 500,
  "payload_bytes": 4200000,
  "success_count": 497,
  "failure_count": 3,
  "duration_ms": 245,
  "retryable_count": 2,
  "permanent_failure_count": 1,
  "trace_id": "..."
}
```

The sample log excludes document sources or personal data. For failed items, log IDs protected/anonymized per policy and error categories; never log access tokens, secrets, or full sensitive payloads.

### Logs and metrics serve different roles

- Metrics: trends, rates, percentiles, and alerts.
- Logs: event details and causes for a specific execution.
- Traces: order and timings across steps in a request/job.

Do not try to substitute logs for time-series metrics or metrics for detailed logs.

## 27. What should an operational dashboard include?

A dashboard for Spring Data Elasticsearch can be divided into areas:

### Search/API

- Request rate.
- p50/p95/p99 latency by endpoint/workload.
- Error rate by status/error category.
- Timeouts and client connection errors.
- Elasticsearch `took` vs. end-to-end latency.
- Hits/page size and response bytes.

### Indexing/Bulk

- Bulk requests/s.
- Documents/items succeeded per second.
- Item failure rate by type.
- Batch size/payload bytes.
- Bulk latency p50/p95/p99.
- 429s/rejections and retry counts.
- In-flight bulk requests.

### Synchronization

- Events received/processed per second.
- Consumer lag by partition.
- Oldest event age.
- Source-to-search-visible lag p50/p95/p99.
- Retry queue/DLQ depth.
- Source version vs. projection version.

### Elasticsearch cluster

- Cluster health and unassigned shards.
- CPU, heap, GC pauses.
- Search/index thread pool active, queue, rejected.
- Indexing pressure.
- Refresh/merge times.
- Disk I/O, free disk, and shard distribution.

Maintain an overview dashboard for on-call and drill-down dashboards by workload. Every chart must state units, time windows, and denominators clearly.

## 28. Designing actionable alerts

Alerts should reflect service impact and suggest an investigation path. Avoid alerting on brief single-counter blips.

Example alert groups:

| Alert | Example condition | Investigation direction |
|---|---|---|
| Search latency high | p95 breaches SLO across consecutive windows | Query latency, `took`, shards, thread pools, network |
| Search error rate high | 5xx/timeout rate exceeds threshold | Cluster health, connection pool, breakers, node logs |
| Bulk rejection | 429/rejected climbs continuously | Lower concurrency, indexing pressure, thread pools |
| Bulk item failure | Mapping/permanent failures breach threshold | Mappings, payload schemas, DLQ |
| Sync lag high | Oldest event age or source-to-visible p95 breaches SLO | Consumer lag, processing, writes, refreshes |
| Backlog growing | Arrival rate exceeds processing rate persistently | Consumer capacity, downstream throughput |
| Cluster degraded | Red health or unassigned primaries | Allocation, disk, node failure |

Exact thresholds must reflect SLOs and baselines. Alerts should require sustained duration (`for` duration) or burn-rate logic to avoid firing on brief, harmless spikes.

## 29. Distinguishing backlog count from backlog age

Backlog count tells you how many events are waiting. Backlog age tells you how long the oldest event has waited.

Examples:

| Situation | Backlog count | Oldest age | Interpretation |
|---|---:|---:|---|
| A | 50,000 | 5 seconds | High processing throughput, likely absorbing a large batch |
| B | 500 | 20 minutes | A partition or job may be stuck |
| C | 10,000 | 15 minutes and growing | Consumers are falling behind |

Do not alert on count alone when processing speed is sufficient. Conversely, a small backlog with high event age can reveal a poison event or blocked partition.

## 30. Identifying bottlenecks via relationships across metrics

Common diagnostic patterns:

| Observation | Possible cause | Next step |
|---|---|---|
| API latency rises, ES `took` stable | Gateway, network, connection pool, response mapping | Inspect trace spans and client metrics |
| ES `took` rises, search queue rises | Search nodes/thread pools overloaded | Inspect queries, shards, CPU, heap, and concurrency |
| Bulk latency rises, 429 rises | Ingestion exceeds cluster capacity | Reduce bulk concurrency/batch, backoff |
| Bulk writes fast yet sync lag high | Consumer queue or publish is slow | Check oldest event age and consumer throughput |
| Write ack fast yet search visibility slow | Refresh interval or delayed refreshes | Measure refresh lag and check refresh policies |
| Average stable yet p99 rises | Hot shard, outlier query, GC, or queue burst | Analyze tail traces and shard/node metrics |
| Error rate rises yet HTTP 200 unchanged | Partial bulk item failures | Check `errors` and per-item responses |
| Low CPU yet high latency | Network, locks/queues, storage I/O, or downstream | Check spans, disks, connection pools, and queues |

These are investigative hypotheses, not automatic conclusions. Use traces/logs and change one variable at a time to verify causes.

## 31. Measuring freshness with synthetic canaries

A canary can write a document with a unique ID and source timestamp, then periodically search for that document and measure elapsed time until it appears.

```text
Canary writer
    |
    | write {id, createdAt}
    v
Elasticsearch index
    |
    | periodic search probe
    v
Canary reader
    |
    v
visibleAt - createdAt = observed visibility lag
```

Canaries should:

- Use a dedicated index/tenant or safe namespace.
- Run at low frequency without adding noticeable load.
- Have cleanup/retention for canary documents.
- Use UTC timestamps and synchronized clocks.
- Measure write ack and search-visible times separately.
- Alert when the canary fails to appear within allowed thresholds.

Canaries measure the overall path, yet do not replace per-partition consumer lag metrics. They provide a valuable supplementary end-to-end signal.

## 32. Monitoring sync when using Outbox or CDC

With transactional outbox, monitor:

- Unpublished outbox rows count.
- Age of oldest unpublished row.
- Publish attempts and failures.
- Time from commit to publish.
- Cleaned-up rows count.

With CDC, monitor:

- Source log position/offset.
- Connector lag.
- Change events emitted.
- Connector restarts/failures.
- Schema changes/errors.
- Downstream consumer lag.

If a projector re-reads source state instead of using event payloads, also measure latency of source service/database calls. When multiple sources are joined, one slow dependency can lag the entire projection.

## 33. Monitoring retries and DLQ

Retries affect throughput and sync lag. If you count only eventually successful events, a system churning through retries can appear healthy while burning heavy resources and stretching freshness.

Monitor:

- Retry attempts per event/item.
- Retry delays and time spent in retry queues.
- Retry success rate.
- Events exceeding max attempts.
- DLQ depth and oldest message age.
- Replay successes/failures.
- Permanent failure reasons.

Messages in a DLQ are not necessarily an outage if an operational process exists, yet a steadily growing DLQ or messages aging past retention/SLO require alerts. Maintain dashboards and runbooks to fix data and replay safely.

## 34. Integrating Observation/Tracing in Spring

Spring Boot can integrate Micrometer Observation to create unified observations that wire metrics and tracing to configured registries/exporters.

Conceptual example wrapping a service operation:

```java
Observation.createNotStarted("product.search", observationRegistry)
    .lowCardinalityKeyValue("operation", "search")
    .observe(() -> searchService.execute(query));
```

For reactive publishers, use Observation/reactive instrumentation APIs compatible with your Spring/Micrometer version so spans cover the full subscription lifecycle rather than just publisher creation. When using `Mono`/`Flux`, verify context propagation and client instrumentation integration.

### Low-cardinality and high-cardinality key values

- Low-cardinality: operation, outcome, workload; safe for metrics.
- High-cardinality: trace ID, request ID, document ID; use only in traces/logs when needed.

Never put high-cardinality keys into metric dimensions.

## 35. Testing metrics and instrumentation

Instrumentation should also be tested at appropriate levels:

- Success increments operation counters and records timers.
- Errors increment error counters under the right category.
- Bulk item successes/failures are counted per item, not solely per request.
- Cancellations are classified if required by business logic.
- Retry counters increment by actual retry attempts.
- Queue gauges reflect current queue depth.
- Metric tags contain no IDs or dynamic messages.
- Reactive timers stop only on publisher termination/cancellation.

Micrometer provides `SimpleMeterRegistry` suited for unit tests:

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

// Invoke the instrumented service and verify its publisher with StepVerifier.

assertThat(registry.get("app.elasticsearch.errors")
    .tag("operation", "search")
    .counter()
    .count()).isEqualTo(1.0);
```

This is an illustrative skeleton; tests must wire the registry into the service and assert the exact metric names/tags produced by the implementation. For timers, assert counts and total time rather than exact durations sensitive to schedulers.

## 36. Runbook when latency or sync lag rises

When an alert fires, investigate in order:

1. Identify affected workloads: search, dashboards, bulk, or sync pipelines.
2. Inspect SLIs: p95/p99, error rates, throughput, and oldest event age.
3. Compare API latency against Elasticsearch `took`/client latency.
4. Inspect sample traces to locate slow spans.
5. Check node health, CPU, heap, GC, disk, and shard allocation.
6. Check thread pool queues/rejections and indexing pressure.
7. For bulk, inspect batch size, concurrency, 429s, item failures, and retries.
8. For sync lag, check publish lag, consumer lag, processing time, write time, and refresh lag.
9. Identify recent changes: deployments, mappings, queries, refresh intervals, shards/replicas, or ingest pipelines.
10. Apply controlled load shedding: lower concurrency, pause consumers, shrink batches, or isolate workloads.
11. Watch metrics after changes and confirm backlog/latency recovery.
12. Document root causes and preventive actions.

Never enlarge thread pools or queue sizes immediately upon seeing rejections before identifying the bottleneck. Larger queues can convert fast rejections into long waits and heavier heap pressure.

## 37. Observability rollout workflow

A practical rollout sequence:

1. List critical operations: search, get, save, update, delete, bulk, and projectors.
2. Define latency, error, throughput, and sync lag with clear units/denominators.
3. Select SLIs/SLOs per workload and freshness requirements.
4. Add Micrometer Timers/Counters/Gauges at application boundaries.
5. Add per-item metrics for the Bulk API and retry/DLQ flows.
6. Enable Actuator/Prometheus or matching exporters and secure endpoints.
7. Collect Elasticsearch Node Stats, Index Stats, and Cluster Health.
8. Add traces/correlation across APIs, event consumers, and projectors.
9. Record timestamps/versions at sync milestones to compute lag.
10. Build dashboards separating Search, Bulk, Sync, and Cluster.
11. Create alerts driven by SLOs, backlog age, and rejections.
12. Write runbooks, test instrumentation, and rehearse failure scenarios.

## 38. Conclusion

Effective Elasticsearch monitoring combines latency, errors, throughput, and synchronization lag. Measure end-to-end latency in the application, separate client time from Elasticsearch `took`, use p50/p95/p99 to watch tail latency, and define success rates with exact denominators. For bulk, count item-level successes/failures rather than requests alone. For asynchronous sync, measure event age and decompose lag into publish, queue, processing, write, and refresh visibility.

In Spring Boot/Spring Data Elasticsearch, Micrometer Timers/Counters/Gauges and Actuator emit application metrics; Elasticsearch Node Stats, Index Stats, thread pools, indexing pressure, refreshes, and merges explain cluster load; tracing and structured logs investigate individual requests/events. Set SLIs/SLOs per workload, avoid high-cardinality metrics, secure monitoring endpoints, and pair alerts with runbooks. When signals are defined consistently from source commit to search visibility, operations teams know where the system is slow, what errors occur, how much work the cluster handles, and how far behind search data lags.

## References

- [Spring Boot – Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Elasticsearch – Node Stats API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-nodes-stats)
- [Elasticsearch – Index Stats API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-stats)
- [Elasticsearch – Cluster Health API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-cluster-health)
- [Elasticsearch – Search slow log](https://www.elastic.co/docs/deploy-manage/monitor/logging-configuration/slow-logs)
- [Elasticsearch – Indexing slow log](https://www.elastic.co/docs/deploy-manage/monitor/logging-configuration/slow-logs)
- [OpenTelemetry – Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)

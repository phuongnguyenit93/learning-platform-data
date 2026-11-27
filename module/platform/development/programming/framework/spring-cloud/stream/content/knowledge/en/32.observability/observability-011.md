# Limiting High-Cardinality Metric Labels

In a Spring Cloud Stream system, each message can carry an event ID, correlation ID, tenant ID, customer ID, topic, partition, routing key, and many other headers. These values are very useful when investigating a specific message, but not all of them belong in metric tags/labels.

**Cardinality** is the number of distinct values a data dimension can take. A metric has high cardinality when its labels have too many or virtually unbounded values. If every message produces a new label value, Micrometer must register another meter and the metrics backend must store another time series. The consequences can include increased memory, CPU, scrape/remote-write payload size, storage costs, and query latency.

An essential design rule: metrics are for aggregating and comparing along a small, stable set of dimensions; logs and distributed traces are for looking up individual events, requests, or messages. Spring Cloud Stream integrates Micrometer Observation, allowing you to keep low-cardinality dimensions for metrics and place high-cardinality data into traces.

## 1. What are cardinality and time series?

A metric is a measurement such as processed message count, processing duration, retry count, or batch size. Tags add classification dimensions so metrics can be queried by binding, outcome, binder, or environment.

Metric example:

~~~text
stream.messages.processed{binding="orders-in-0", outcome="success"} 1250
stream.messages.processed{binding="orders-in-0", outcome="error"} 12
~~~

Two different tag combinations create two distinct meters in Micrometer. For simple counters/gauges, each meter typically maps to one time series in Prometheus; timers/histograms can generate multiple series for buckets, sum, and count. In Prometheus, every unique combination of metric name and label key/value pairs creates a time series.

A label's cardinality is the number of distinct values that label can hold. A metric's cardinality also depends on the combinations across all its labels. Suppose a metric has:

- 4 bindings.
- 3 binders.
- 4 outcomes.
- 6 instances.

The theoretical maximum number of combinations is:

\[
4 \times 3 \times 4 \times 6 = 288
\]

Not every combination necessarily occurs, yet this product estimates the upper bound. Adding an `eventId` label with 100,000 distinct values raises the theoretical combinations to:

\[
288 \times 100\,000 = 28\,800\,000
\]

A single per-message label can push time series counts from a few hundred into tens of millions.

~~~mermaid
flowchart TD
    A[Metric: stream.messages.processed] --> B[Tag binding: 4 values]
    A --> C[Tag outcome: 4 values]
    A --> D[Tag instance: 6 values]
    A --> E[Tag eventId: 100,000 values]
    B --> F[Tag combinations create time series]
    C --> F
    D --> F
    E --> F
    F --> G[Cardinality and costs surge sharply]
~~~

Cardinality is not the number of samples recorded per minute. One time series can receive millions of samples over time while keeping a cardinality of one. Conversely, a metric updated only once per event still has very high cardinality if each event generates a different tag set.

## 2. Why does high cardinality cause problems?

Every meter in Micrometer is identified by name, type, and tag set. When tags change, the registry may have to register a new meter. With Prometheus, the backend stores each label combination as a separate time series.

High cardinality impacts multiple layers:

1. **Inside the application:** the registry retains extra meters and data structures; continuous meter registration increases allocations, memory, and CPU overhead.
2. **During export:** scrape endpoints or exporters must iterate over and serialize more series; metric payloads grow larger.
3. **In the backend:** Prometheus/remote storage must index, hold metadata for, compress, and query more series.
4. **In dashboards:** group-by queries, aggregations, and joins over large series sets can become slow or resource-intensive.
5. **In operational costs:** many platforms bill by series count, sample count, or ingestion volume; rising cardinality can rapidly inflate costs.
6. **In alerting:** alert rules must evaluate more series and may fire excessive alert instances.

Timers and histograms amplify this impact. Each tag combination on a histogram can spawn multiple bucket series plus sum/count series. Bucket counts depend on registry/backend settings; thus a timer with high-cardinality labels is typically far more expensive than a simple counter with the same tag combinations.

## 3. Which labels fit message-processing metrics?

A good tag has a bounded, stable set of values that is meaningful when aggregated. With Spring Cloud Stream, start with dimensions like these:

| Tag | Example values | Assessment | Reason |
|---|---|---|---|
| `binding` | `orders-in-0`, `orders-out-0` | Usually suitable | Binding names are declared in application config. |
| `binder` | `kafka`, `rabbit`, `pulsar` | Suitable | The number of binder types is small and controlled. |
| `outcome` | `success`, `retry`, `error`, `discarded` | Suitable | Bounded set of states defined by the application. |
| `error_category` | `validation`, `timeout`, `serialization`, `other` | Suitable | Stable error groups without free-form error messages. |
| `exception` | `IllegalArgumentException`, `TimeoutException` | Conditional | Class names are usually bounded in code; never use exception messages. |
| `destination` | `orders.created`, `orders.validated` | Conditional | Suitable if destinations form a static, bounded list. |
| `partition` | `0`, `1`, `2` | Conditional | Partition counts are bounded, though combining with many topics/instances can grow total series. |
| `consumer_group` | `order-projection` | Conditional | Reasonable if groups are statically configured; never use per-request/per-tenant groups. |
| `region` | `ap-southeast-1`, `ap-northeast-1` | Usually suitable | Region sets are small and stable. |
| `event_id` | `evt-8f3...` | Unsuitable | Every message can have a unique ID. |
| `correlation_id` | `corr-...` | Unsuitable | Nearly unique per request/message flow. |
| `trace_id`, `span_id` | Trace/span IDs | Unsuitable | Continuously generated new values; use traces for lookup. |
| `customer_id`, `user_id`, `tenant_id` | Per-customer IDs | Usually unsuitable | Large value set varying with business data. |
| `exception_message` | Exception text | Unsuitable | Free-form text that may contain IDs, URLs, inputs, or secrets. |
| `payload`, arbitrary `routing_key` | Message content or headers | Unsuitable | Can vary with every message. |
| `timestamp` | Per-event timestamp | Unsuitable | Virtually every message has a different value. |

A tag is not automatically safe just because it is a number or short string. `tenant_id` might have hundreds of thousands of values; `partition` might have only a few. Evaluate the actual number of values, combinations with other tags, and query needs.

## 4. Cardinality in Spring Cloud Stream

Message flows commonly introduce high-cardinality labels in several places:

### 4.1. Attaching event ID or correlation ID to custom counters

The following snippet creates a separate meter for every event:

~~~java
registry.counter(
    "stream.messages.processed",
    "eventId",
    event.eventId()
).increment();
~~~

If 500,000 messages carry 500,000 distinct event IDs, the registry can hold roughly 500,000 meters with the same name. Put event IDs into logs or traces to locate a specific message; counters should only carry tags like binding and outcome.

### 4.2. Dynamic destinations from StreamBridge

`StreamBridge` can create output bindings for destinations determined at runtime. That is useful when an application routes messages to a few distinct destinations. However, if destinations are built from tenant IDs, customer IDs, or arbitrary request values, using destination as a tag creates a new series per tenant/request.

Avoid blindly adding dynamic destinations to every metric. You can bucket destinations into bounded business groups such as `orders`, `audit`, `notification`, `other`, while logging the real destination or recording it in traces when needed for investigation.

### 4.3. Consumer group and partition

Consumer group and partition names can be helpful observability dimensions. Yet if every tenant or request spins up a new consumer group, the `consumer_group` tag is no longer low-cardinality. Similarly, partitions are bounded within one topic, but the `topic × partition × instance × outcome` cross-product can grow substantially when topic and replica counts are large.

Only include partition in metrics when dashboards or alerts genuinely need per-partition visibility. If the goal is overall binding throughput, aggregate by binding and outcome.

### 4.4. Exceptions and headers

Never use `exception.getMessage()` as a tag. Messages can embed order IDs, URLs, SQL, filenames, or offending input. Exception class names usually have a smaller set of values, though normalizing them into an application-controlled `error_category` is safer when many exception types or external libraries exist.

Message headers should not automatically become metric tags either. Headers such as `eventId`, `traceparent`, `x-correlation-id`, `tenant`, `user-agent`, or `routingKey` frequently carry ever-changing values. Extract only attributes that have small bounded value sets, are validated, and require aggregation.

## 5. Estimating cardinality before adding a tag

Before adding a tag, estimate:

- How many distinct values can that tag take on a single instance?
- How many instances of the application run?
- How many bindings, destinations, groups, and outcomes exist?
- Is the metric a counter, gauge, timer, or histogram?
- How long does the backend retain data?
- Do you actually need aggregated queries along that dimension, or only lookup of a specific event?

Suppose a message-processing metric has 5 bindings, 4 outcomes, and 8 instances. Adding 20 static destinations yields a theoretical maximum of:

\[
5 \times 4 \times 8 \times 20 = 3\,200
\]

If destinations become 10,000 tenant destinations:

\[
5 \times 4 \times 8 \times 10\,000 = 1\,600\,000
\]

That is just one metric; adding timer histograms, retry metrics, and other meters drives total series counts much higher. These figures are worst-case combination estimates; actual counts depend on observed combinations.

A practical rule is assigning a cardinality budget per metric family. Every new tag needs an owner, an expected value set, and a query justification. Never add a tag merely because the value happens to be on the message.

## 6. Designing tags with bounded value sets

Instead of passing arbitrary strings, map input values to enums or status groups:

~~~java
enum ProcessingOutcome {
    SUCCESS,
    VALIDATION_ERROR,
    TRANSIENT_ERROR,
    OTHER_ERROR
}

enum DestinationGroup {
    ORDERS,
    AUDIT,
    NOTIFICATIONS,
    OTHER
}
~~~

Classification helper:

~~~java
DestinationGroup classifyDestination(String destination) {
    if (destination == null) {
        return DestinationGroup.OTHER;
    }
    if (destination.startsWith("orders.")) {
        return DestinationGroup.ORDERS;
    }
    if (destination.startsWith("audit.")) {
        return DestinationGroup.AUDIT;
    }
    if (destination.startsWith("notifications.")) {
        return DestinationGroup.NOTIFICATIONS;
    }
    return DestinationGroup.OTHER;
}
~~~

Record the counter with normalized tags:

~~~java
registry.counter(
    "stream.messages.processed",
    "binding", "orders-in-0",
    "destination_group", classifyDestination(destination).name(),
    "outcome", outcome.name().toLowerCase(Locale.ROOT)
).increment();
~~~

The tag set is predictable: binding is statically configured, destination group has four values, and outcome has four values. No event ID or arbitrary destination enters meter identity.

If you need to retain the real destination, write it to structured logs or spans/traces. When per-tenant reporting is required, consider analytical tables or a dedicated analytics system instead of turning metric time series into a per-tenant database.

## 7. Registering custom metrics with Micrometer

Spring Boot Actuator auto-configures `MeterRegistry` and Micrometer. You can inject the registry into components to create counters, timers, or gauges.

Example component recording message counts:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.Locale;

@Component
class StreamMetrics {

    private final MeterRegistry registry;

    StreamMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordProcessed(String binding, ProcessingOutcome outcome) {
        registry.counter(
            "stream.messages.processed",
            "binding", binding,
            "outcome", outcome.name().toLowerCase(Locale.ROOT)
        ).increment();
    }
}
~~~

Micrometer identifies meters by name and tag set. When name and tags match, the registry reuses the existing meter; when a tag value varies, the registry needs a new meter. Therefore `binding` and `outcome` in the example must come from controlled value sets.

Do not write:

~~~java
void recordProcessed(OrderEvent event) {
    registry.counter(
        "stream.messages.processed",
        "eventId", event.eventId(),
        "customerId", event.customerId()
    ).increment();
}
~~~

The snippet above creates a meter per event/customer pair. As traffic grows, meter counts can scale nearly linearly with event volume.

If there is a fixed set of tag combinations called very frequently, you can pre-register Counters/Timers during bean initialization and reuse them. Whether pre-registering or calling `registry.counter(...)` each time, keeping the tag set stable and bounded remains essential.

## 8. Placing high-cardinality data into Observations and traces

Micrometer Observation distinguishes low-cardinality from high-cardinality key-values:

- Low-cardinality key-values are used to create metric tags and can also appear in traces.
- High-cardinality key-values are not used as metric tags; they are meant for traces or other handlers capable of handling detailed data.

Example observation for message processing:

~~~java
Observation.createNotStarted("stream.message.process", observationRegistry)
    .lowCardinalityKeyValue("binding", "orders-in-0")
    .lowCardinalityKeyValue("outcome", "success")
    .lowCardinalityKeyValue("binder", "kafka")
    .highCardinalityKeyValue("eventId", event.eventId())
    .highCardinalityKeyValue("correlationId", correlationId)
    .observe(() -> orderService.process(event));
~~~

Here metrics can aggregate by binding, outcome, and binder. Traces can retain event ID/correlation ID to look up a specific execution when a tracing handler is configured.

Do not dump all sensitive data into traces simply because traces tolerate higher cardinality. Traces still incur ingestion/storage costs and may hold personal data. Never attach passwords, access tokens, emails, or confidential payloads; apply appropriate masking, retention, and access controls.

If the application already has an Observation created by Spring Cloud Stream for the function invocation, review the existing convention/context before adding another Observation for the exact same operation. Only nest observations when measuring a distinct child operation with independent value.

## 9. Spring Cloud Stream observability

Spring Cloud Stream integrates Micrometer Observation at the Spring Cloud Function layer:

- For imperative functions, the framework can wrap the function with `ObservationFunctionAroundWrapper`. When required observability dependencies are present, each function invocation (typically one message) gets an observation.
- For reactive functions, the function initializes the stream and is invoked at application startup. The framework cannot assume every Flux item is a standalone invocation; attach observations to reactive processing segments intentionally.

Common observability dependencies include Spring Boot Actuator, `reactor-core-micrometer` for reactive setups, and an appropriate tracing bridge. Exact dependencies and activation depend on your Spring Boot/Spring Cloud versions.

Example with Reactor, attaching per-message observations using `tap`:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> normalize(
        ObservationRegistry observationRegistry) {
    return events -> events
        .flatMap(event -> Mono.just(event)
            .map(this::normalizeOrder)
            .tap(Micrometer.observation(observationRegistry)));
}
~~~

This snippet illustrates where to attach the observation; conventions/contexts should be configured to add bounded low-cardinality tags and suitable high-cardinality metadata. Never pass event ID as a low-cardinality key-value.

## 10. Keeping metric names stable

Cardinality does not come only from tags. Generating dynamic metric names also floods the registry with meters:

~~~java
// Avoid: meter name changes for every order.
registry.counter("orders." + orderId + ".processed").increment();
~~~

`HighCardinalityTagsDetector` primarily detects many meters sharing the same name due to tags; it does not catch every case where random values are embedded in meter names. Therefore, always use fixed metric names:

~~~java
registry.counter(
    "orders.processed",
    "outcome", "success"
).increment();
~~~

Variable details belong in bounded tags, logs, or traces. Never create a separate metric name per message, customer, or dynamic destination.

## 11. Common tags and environment tags

Spring Boot allows configuring common tags across all metrics:

~~~yaml
management:
  metrics:
    tags:
      application: orders-stream
      environment: production
      region: ap-southeast-1
~~~

Values like application, environment, and region usually have small, stable sets useful for comparing environments or deployment regions.

Evaluate instance/host/pod tags carefully:

- If replica counts are limited and per-instance views are needed, an instance tag can be useful.
- If every restart generates a random ID and the backend retains data long-term, accumulated instance values can grow over time.
- Never attach per-task request IDs, event IDs, or container IDs to all metrics merely because they are available.

Common tags are added to every meter, so an application-wide high-cardinality tag multiplies series across many metrics at once.

## 12. Using MeterFilter as a guardrail

`MeterFilter` can deny meters, transform names/tags, or cap tag value counts. It is a guardrail when instrumentation cannot be fixed immediately, not the primary tag design approach.

Example capping destination tag values for a metric family:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StreamMetricFilterConfiguration {

    @Bean
    MeterFilter limitDestinationTags() {
        return MeterFilter.maximumAllowableTags(
            "stream.messages.processed",
            "destination",
            20,
            MeterFilter.deny()
        );
    }
}
~~~

This filter applies to meters whose names start with `stream.messages.processed`, allowing at most 20 distinct values for the `destination` tag. Once exceeded, `MeterFilter.deny()` rejects new meter registrations; the registry returns a NOOP meter and measurements recorded through it are dropped.

**This cap does not automatically group overflow values into `other`.** To preserve aggregate counts, normalize values before creating the meter—for example, mapping destinations outside an allowlist to `other`.

You can also strip an unwanted tag from meters:

~~~java
@Bean
MeterFilter removeEventIdTag() {
    return MeterFilter.ignoreTags("eventId");
}
~~~

`ignoreTags` removes matching tags from every meter passing through the filter. Because its scope is registry-wide, check all instrumentation before applying it. If a tag should only be dropped from one metric group, use a conditional filter matching the meter name prefix.

MeterFilters run in registration order. A `deny` filter can turn a meter into a NOOP; a tag-transforming filter can change meter identity. Test filter order and impact before deploying.

## 13. Detecting high cardinality with Micrometer

Micrometer includes `HighCardinalityTagsDetector` to spot meter names whose meter counts exceed a threshold. Enable it on the registry:

~~~java
registry.config().withHighCardinalityTagsDetector();
~~~

Place this call inside configuration for the Spring-managed `MeterRegistry` (such as a registry customizer) so the detector monitors the exported registry. Or construct a detector with custom thresholds and callbacks per your Micrometer version's API; check the version managed by the Spring Boot BOM before using newer APIs. The detector counts meters sharing a name and warns when a threshold is crossed; it is a heuristic for spotting potential high-cardinality tags.

The detector has limitations:

- It does not catch meter names dynamically constructed with event IDs.
- It does not catch every cause of memory growth.
- It may report only the first offending meter; investigate per metric family.
- Appropriate thresholds depend on application scale and backend capacity.

Enable the detector in production or realistic-load staging, and test instrumentation to catch mistakes before release. Do not simply raise the threshold when warned; find the tag or meter name driving growth.

## 14. Inspecting cardinality with Prometheus

When using Prometheus, inspect series counts by metric name:

~~~promql
count by (__name__) ({job="orders-stream"})
~~~

Find the metric families with the most series:

~~~promql
topk(20, count by (__name__) ({job="orders-stream"}))
~~~

If a metric has a `destination` tag, inspect series counts per destination:

~~~promql
count by (destination) (stream_messages_processed_total)
~~~

Prometheus metric names can differ from Micrometer names due to naming conventions and counter/timer suffixes. Substitute the actual exported names in your system.

When investigating, look for:

- Metric families whose series counts climb unusually fast.
- Tag values that are UUIDs, timestamps, full URLs, emails, or business IDs.
- Dynamically created destinations/groups.
- Metric names varying by event or tenant.
- Histograms with many buckets paired with high-cardinality tags.
- Stale series lingering throughout retention even after instances or destinations are removed.

Spring Boot Actuator `/actuator/metrics` lets you browse meter names and filter by tags inside the application registry. The metrics endpoint is not exposed over HTTP by default; expose it only when needed and protect it with appropriate authentication/network policies. This endpoint is useful for inspecting meters registered on the application side; the Prometheus backend shows actual series after scraping and naming-convention normalization.

## 15. Testing that instrumentation does not create per-event meters

Write tests proving that many events with different IDs still share a bounded set of meters:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class StreamMetricsTest {

    @Test
    void reusesMetersForManyEvents() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        for (int i = 0; i < 1_000; i++) {
            registry.counter(
                "stream.messages.processed",
                "binding", "orders-in-0",
                "outcome", "success"
            ).increment();
        }

        assertThat(registry.getMeters()).hasSize(1);
        assertThat(registry.get("stream.messages.processed")
            .tag("binding", "orders-in-0")
            .tag("outcome", "success")
            .counter()
            .count()).isEqualTo(1_000);

        registry.close();
    }
}
~~~

This test performs 1,000 updates on the same meter identity. You can expand it across a bounded set of outcomes and assert the meter count equals the exact expected number of combinations.

To see the anti-pattern, replace the `outcome` tag with a unique `eventId` per iteration; the registry registers many meters. Never put the anti-pattern into production just to test it; verify it using SimpleMeterRegistry in an isolated test.

Beyond meter count, verify:

- Tag values always come from an enum/allowlist.
- Unknown destinations map to `other`.
- Exception messages never enter tags.
- Metric names never contain dynamic IDs.
- Histograms are enabled only on metrics that need them.
- Observations place detailed IDs in high-cardinality metadata, not low-cardinality key-values.

## 16. Notes on using histograms and timers

Timers measuring message processing duration are often useful:

~~~java
Timer.builder("stream.message.processing")
    .tag("binding", "orders-in-0")
    .tag("outcome", "success")
    .register(registry)
    .record(() -> orderService.process(event));
~~~

Never attach event ID or customer ID to a timer. Every tag set creates a separate timer; when percentile histograms or SLO buckets are enabled, each timer spawns additional series in the backend.

Enable percentile histograms only when backend-aggregatable percentile queries are needed and bucket/series counts have been estimated. For per-message latency, use traces/spans; timer metrics should answer aggregate questions like p95 latency by binding/outcome.

## 17. Separating metrics, logs, and traces by goal

| Need | Appropriate tool | Example data |
|---|---|---|
| How many messages succeeded/failed? | Counter metric | binding, binder, outcome |
| What is p95 processing time of a binding? | Timer/histogram | binding, outcome |
| Which consumer group is lagging? | Broker/binder metric | topic, group, bounded partition |
| Where did event `evt-123` fail? | Structured log or trace | event ID, correlation ID, exception detail |
| Which services did a request traverse? | Distributed trace | trace ID, span ID, appropriate event ID |
| Which errors are rising by business group? | Metric with error category | validation, timeout, serialization |
| Which payload caused the error? | Controlled log/DLQ | masked payload or reference |

Metrics must support aggregation and alerting. Logs/traces handle drill-down. Never use a metrics backend as a database to store every event ID.

## 18. Workflow when cardinality growth is detected

1. Identify the fast-growing metric family via dashboard/backend queries.
2. Inspect its tag keys and sample tag values to spot IDs, URLs, timestamps, or dynamic destinations.
3. Locate where meters are created: custom MeterRegistry usage, ObservationConvention, binder instrumentation, or common tags.
4. Decide whether that dimension is needed for aggregation/alerting or only for finding a single event.
5. If needed for aggregate analysis, normalize into enums, categories, templates, or ranges.
6. If needed for detailed investigation, move the value to traces/logs and apply masking/retention.
7. If unnecessary, remove the tag from instrumentation or apply MeterFilter as a temporary safeguard.
8. Test meter and series counts before release.
9. Re-check cardinality, memory, and ingestion rates after deployment.
10. Document tag budgets and rules for new metrics during instrumentation reviews.

For emergency protection, `maximumAllowableTags` shields the registry/backend, though meters past the cap are denied and their data is lost. Fix the instrumentation source and remove temporary guardrails once no longer needed.

## 19. Common mistakes

1. Adding `eventId`, `traceId`, or `customerId` as tags to find messages. Use traces/logs for that.
2. Using exception messages as tags. Messages vary and can hold unbounded data.
3. Embedding IDs in metric names. Tag-based MeterFilters do not solve dynamic meter names.
4. Passing dynamic StreamBridge destinations into metrics without bounding the value set.
5. Using tenant ID as a tag just because tenant count is currently small; account for growth and long-term retention.
6. Adding partition and instance to every metric when dashboards only need totals.
7. Assuming counters have no histograms so tag cardinality is cheap.
8. Enabling histograms on multi-dimensional metrics without calculating bucket/series counts.
9. Assuming `maximumAllowableTags` buckets overflow tags into `other`; default `deny` turns new meters into NOOPs.
10. Applying registry-wide `ignoreTags` without checking other metrics relying on that tag.
11. Watching only samples/second while ignoring total active time series.
12. Raising detector thresholds without finding the root cause.
13. Putting sensitive data into traces under the assumption traces have no cost or security needs.
14. Using metrics to store per-event records instead of logs, traces, or an event analytics system.

## 20. Metric design checklist for Spring Cloud Stream

- [ ] Metric names are static, with no event IDs, tenant IDs, or dynamic destinations.
- [ ] Every tag has a bounded, controlled value set.
- [ ] `binding`, `binder`, `outcome`, and `error_category` have normalized values.
- [ ] `destination`, `consumer_group`, and `partition` are added only when needed and within the cardinality budget.
- [ ] Event IDs, correlation IDs, trace IDs, user/customer IDs, and payloads are never used as metric tags.
- [ ] Exception tags use stable classes/categories, never exception messages.
- [ ] Common tags such as application, environment, and region have stable values.
- [ ] Dynamic destinations are mapped to bounded groups before recording metrics.
- [ ] Histograms/timers have appropriate bucket counts and tag combinations.
- [ ] High-cardinality metadata is sent to traces/logs per data policy.
- [ ] MeterFilter is treated only as a guardrail, recognizing that denied meters drop measurements.
- [ ] Tests verify meter counts across many distinct event IDs.
- [ ] Dashboards/alerts monitor series counts and detectors in appropriate environments.
- [ ] New metrics document their cardinality budget and query purpose.

Limiting high-cardinality metric labels keeps observability aggregatable as message volume grows. In Spring Cloud Stream, use stable dimensions such as binding, binder, outcome, and error categories for metrics; keep event IDs, correlation IDs, and per-message details in traces/logs. Combining tag normalization, MeterFilter guardrails, detectors, and instrumentation tests catches cardinality explosions early while retaining enough detail to investigate incidents.

## References

- [Spring Cloud Stream – Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer – High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Micrometer – Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer – Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Prometheus – Metric and Label Naming](https://prometheus.io/docs/practices/naming/)

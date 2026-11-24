# Metric cardinality and tag hygiene

In a production Spring Kafka system, monitoring is more than enabling Micrometer, configuring Prometheus scrapes, and building dashboards. **A metric with uncontrolled tag values can spawn tens of thousands or millions of time series**, inflating application memory, metrics backend load, storage cost, query latency, and the risk of monitoring overloading right when Kafka is in an incident.

**Metric cardinality** describes how many distinct label combinations a metric can generate. **Tag hygiene** is the set of rules for naming, selecting tags, bounding values, protecting sensitive data, and managing time-series lifecycles. In Spring Kafka Reliability Operations, tag hygiene matters especially because Kafka data routinely includes **topic, partition, group ID, client ID, listener ID, transaction ID, event ID, tenant ID, retry topic, and exception details**. Some values belong in metric tags; many others belong strictly in logs or traces.

This lesson explains how to calculate cardinality, spot risky tags, design metrics for Kafka consumers/producers/transactions/retries/DLTs, use Micrometer `MeterFilter` and Observation, organize Prometheus/Actuator, budget time series, monitor label churn, and respond when a cardinality explosion occurs.

## 1. What is a metric tag?

A metric describes the quantity being measured, such as successfully processed records, listener latency, or failed message sends. **Tags** (also called **labels** in Prometheus) add classification dimensions to the metric.

Example counter tracking consumer failures:

~~~text
Metric name:
  app.kafka.consumer.failures

Tags:
  application = orders-service
  listener    = orders-listener
  topic       = orders.events
  category    = deserialization
~~~

In Prometheus, a sample may be represented as:

~~~promql
app_kafka_consumer_failures_total{
  application="orders-service",
  listener="orders-listener",
  topic="orders.events",
  category="deserialization"
}
~~~

Actual metric names depend on the registry, naming conventions, and instrumentation version. In the example, the counter-type Micrometer metric exports to a Prometheus-compatible name. What matters is not the exact spelling, but that **each unique label combination creates a distinct time series**.

If `category` changes from `deserialization` to `timeout`, even with the same metric name and other tags, Prometheus stores a separate time series.

## 2. How is cardinality calculated?

Suppose a metric has four labels:

| Tag | Possible values |
|---|---:|
| `application` | 5 |
| `listener` | 8 |
| `topic` | 12 |
| `outcome` | 3 |

If every combination appears, the maximum series count across these dimensions is:

~~~text
5 applications
  × 8 listeners
  × 12 topics
  × 3 outcomes
= 1,440 time series
~~~

Estimation formula:

\[
C \leq \prod_{i=1}^{n} |V_i|
\]

Where C is the number of label combinations and V_i is the observed value set for the i-th tag. This is an **upper bound by Cartesian product of value counts**, not an exact count when dimensions are correlated. For example, each listener consumes only a subset of topics, so many theoretical combinations never materialize.

However, adding an **`event_id`** tag with one million distinct values yields:

~~~text
1,440 initial series
  × 1,000,000 event IDs
= 1,440,000,000 potential combinations
~~~

Not all combinations will necessarily be created, yet simply having a tag that changes per event makes metric growth uncontrollable.

**Question to ask before adding any tag:** over a day, a week, and a deploy cycle, how many distinct values will this tag take?

## 3. Series count vs. sample count

Two concepts are frequently confused:

- **Time series cardinality**: number of distinct metric name + label set combinations.
- **Sample volume**: number of data points written into series over time, depending on scrape interval and series lifetime.

A metric with 20 series scraped every 15 seconds writes many samples over a day, yet series count stays small. A metric with 200,000 new series appearing in 5 minutes causes massive **series churn** even if each series has only a few samples.

~~~text
Case A:
  20 series
  scraped every 15 seconds
  series stay stable for days

Case B:
  every message creates a new event_id
  20,000 new series in a few minutes
  many series live only briefly
~~~

Case B is far more dangerous for indexing, memory, WAL, remote write, and lifecycle management in time-series backends.

**Lowering scrape frequency** reduces sample ingestion yet **does not fix cardinality caused by label combinations**. Unbounded tag values must be removed or normalized.

## 4. Why does Kafka create high cardinality risk?

Kafka carries many identifiers useful for tracing yet unsuitable for metrics:

| Data | Potential cardinality | Remarks |
|---|---|---|
| application/service | Usually low | Suitable when names are stable |
| environment | Low | `dev`, `staging`, `production` |
| cluster alias | Usually low | Use controlled cluster names |
| consumer group | Low to medium | Avoid generating one group per request |
| listener ID | Low if statically defined | Watch out for dynamically generated listeners |
| topic | Low to very high | Topic-per-tenant or retry topics can explode |
| partition | Bounded per topic, yet huge cluster-wide | Do not attach to every metric |
| `client.id` | Can be high and volatile | Random suffixes, pod IDs, instance churn |
| `transactional.id` | High with many producers, suffixes, and lifecycles | Better suited for logs |
| exception class | Usually finite yet needs governance | Group into failure categories when needed |
| exception message | Very high | Contains IDs, URLs, payloads, timestamps |
| record key | Very high | Often matches business/entity IDs |
| event ID / correlation ID | Nearly unbounded | Never put in metric tags |
| tenant ID / customer ID | Tens to millions | Use only with strict budgets and caps |
| original offset | Grows per record | Never use as an aggregate metric tag |

Most dangerous are **values generated per record or per request**, because metrics can spawn new series for every order, retry attempt, or offset.

## 5. Three tiers of tags

A practical policy divides tags into three groups:

| Group | Examples | How to use |
|---|---|---|
| **Low cardinality** | `environment`, `outcome`, `error_category`, `operation` | Suitable for metrics |
| **Bounded cardinality** | Whitelisted `topic`, fixed `listener ID`, managed `group ID` | Use with a budget and monitoring |
| **High/unbounded cardinality** | `event_id`, `order_id`, `user_id`, stack traces, `exception_message` | Use only in logs/traces or other query systems |

**Bounded does not mean permanently safe.** A cluster with 20 topics today can grow to 20,000 topics if someone introduces topic-per-customer. A `topic` tag stays safe only while the organization enforces clear topic limits and naming policies.

Similarly, exception classes are relatively finite yet grow with libraries and versions. If exact exception names are unnecessary on dashboards, a normalized tag like `error_category` is easier to govern.

## 6. Tag hygiene is a process, not just naming conventions

Tag hygiene encompasses:

1. Explicitly defining **which operational decision a metric serves**.
2. Adding only classification dimensions genuinely needed by dashboards, alerts, and SLOs.
3. Naming tags consistently across services.
4. Standardizing allowed value lists.
5. Capping value counts and the arrival rate of new values.
6. Preventing Kafka record data from turning into arbitrary labels.
7. Keeping PII, tokens, secrets, emails, payloads, or SQL text out of tags.
8. Monitoring active series counts and churn.
9. Governing changes via code reviews and tests.
10. Having an emergency kill switch to disable series-exploding instrumentation.

A nicely named metric with an `event_id` tag on every record is still a broken metric design.

## 7. Designing a standard tag schema for Spring Kafka

Example schema for application metrics:

| Tag | Valid values | Constraints |
|---|---|---|
| `application` | `orders-service` | Stable service name |
| `environment` | `prod`, `staging`, `dev` | Fixed value set |
| `kafka_cluster` | `core`, `analytics` | Managed alias |
| `listener` | `orders-created`, `orders-payment` | Predefined IDs |
| `operation` | `consume`, `produce`, `recover` | Closed enum |
| `outcome` | `success`, `error`, `skipped` | Closed enum |
| `error_category` | `none`, `deserialize`, `timeout`, `validation`, `infra`, `unknown` | Standard taxonomy |
| `topic_family` | `orders`, `payments`, `inventory`, `retry`, `dlt` | Bounded topic groups |

Example:

~~~text
app.kafka.listener.records{
  application="orders-service",
  environment="prod",
  listener="orders-created",
  topic_family="orders",
  outcome="error",
  error_category="deserialize"
}
~~~

There is no need to repeat `application`, `environment`, and `cluster` aliases **everywhere in code** when Micrometer common tags or resource attributes add them consistently. The more places manually attach tags, the higher the risk of colliding names or inconsistent values.

## 8. What goes into metrics, logs, and traces?

Three telemetry pillars answer different questions:

| Question | Data to use |
|---|---|
| What is the consumer failure rate by topic family? | Aggregate metrics |
| Which partition has heavy lag in the current incident? | Bounded per-partition Kafka client metrics, specialized dashboard |
| At which step did event `E123` fail? | Structured logs/traces with event ID |
| At which offset is the failed record located? | Logs/traces and DLT metadata |
| How long did listeners take to process records? | Timers/histograms with bounded tags |
| Why did a record time out? | Traces/logs with exception details |
| How many recoveries went to the DLT in 5 minutes? | Counters by outcome/category |
| Which tenants are affected? | Query logs/traces or metrics by controlled tenant tier |

**Low cardinality does not mean losing diagnostic power.** Use aggregate metrics to spot symptoms, then pivot to logs/traces with correlation IDs to inspect individual records.

Example:

~~~text
Metric:
  error_category="serialization"
  count spikes abnormally

Trace:
  trace_id = ...
  event.id = E123
  topic = orders.created
  partition = 2
  offset = 105

Log:
  detailed root cause and redacted context
~~~

Never force a metrics system to act as a per-event search database.

## 9. Consumer metrics: which classification dimensions help?

For Spring Kafka consumers, core metrics typically include:

- Records processed/failed counts.
- Listener processing duration.
- Poll/consumer liveness.
- Consumer lag.
- Offset commit failures.
- Rebalance count/duration.
- Error handler recoveries.
- Retry attempts or DLT outputs.

Suitable dimensions are typically:

~~~text
application
listener
topic_family
outcome
error_category
~~~

Evaluate `topic` and `partition` carefully:

- **`topic`** is helpful when topic counts are managed and budgeted.
- **`topic_family`** fits better when topic names embed tenant IDs, dates, or dynamic suffixes.
- **`partition`** is helpful on select native Kafka metrics, not needed on all business metrics.
- **`consumer group`** separates flows, though avoid generating a new group ID per ad-hoc job when jobs are unbounded.

Never put **`record.key()`**, **`record.offset()`**, or business event IDs into tags just to look up records on dashboards.

## 10. Impact of partition-level metrics

Suppose a service runs 12 consumer instances, each owning multiple partitions. If a metric carries:

~~~text
topic = 40 values
partition = up to 200 values on some topics
client_id = 12 values
outcome = 3 values
~~~

Theoretical maximum combinations can surge. In practice each client owns only a subset of topic-partitions, yet when broker/client metrics export multiple metric families, total series remain significant.

For **per-partition lag**, partition granularity is valuable because one stalled partition can hide behind an average lag. Still, there is no need to add `partition` to every timer and business counter.

A balanced design:

- Track **max lag or aggregated lag** per consumer group/listener for broad alerts.
- Track **partition lag** on diagnostic dashboards with bounded scope and retention.
- Use logs/consumer group tooling to inspect individual partitions during investigations.
- Never create a separate latency metric per **offset**.

**Partition is a finite dimension at a point in time, yet total partitions across a large system can still be huge.**

## 11. Topic-per-tenant: how a topic tag turns into customer IDs

Suppose a system creates topics like:

~~~text
orders.tenant-1001
orders.tenant-1002
orders.tenant-1003
...
orders.tenant-9999
~~~

Putting `topic` as a tag on every listener timer/counter gives the metric at least one label value per tenant. Multiplied by partitions, outcomes, and instances, cardinality explodes quickly.

Instead of:

~~~text
topic="orders.tenant-1001"
topic="orders.tenant-1002"
~~~

You can use:

~~~text
topic_family="orders"
tenant_tier="standard"
~~~

If you must view metrics for a handful of priority tenants, design an explicit whitelist/allowlist mapping all others to `other`, rather than dumping every customer ID into Prometheus for a single custom dashboard.

Important: **replacing dynamic values with a meaningful group** is usually better than stripping all topic context. Dashboards still know errors hit the `orders` group without spawning a series per customer.

## 12. Client IDs and transactional IDs require special care

Native Kafka client metrics typically carry `client.id`. Spring Kafka can generate client IDs suffixed by concurrency or container lifecycle. If names also embed pod UUIDs or timestamps, every restart creates new labels.

~~~text
client_id="orders-consumer-f4b8d1-0"
client_id="orders-consumer-a19c77-0"
client_id="orders-consumer-2d851e-0"
~~~

Even if each instance runs only a few consumers, **frequent restarts cause series churn**. Under autoscaling, series generated over time far exceed running pod counts.

For transactional producers, `transactional.id` can carry instance prefixes and suffixes. That is vital in **logs when handling `ProducerFencedException`**, yet rarely needed as a label on every transaction metric.

Recommendations:

1. Use stable logical listener/container IDs on aggregate metrics.
2. Never embed random UUIDs into custom metric labels.
3. Keep `client.id` on native client metrics if needed, while budgeting scrape/retention and series counts.
4. Emit exact `transactional.id` in controlled structured logs when investigating fencing.
5. Avoid combining `client_id`, `transactional_id`, `pod_uid`, and `event_id` on the same custom timer.

Dropping client IDs from metrics must weigh per-client debugging needs rather than acting as an absolute ban. **The point is balancing budget and diagnostic value against cost.**

## 13. How retry and DLT tags easily explode

Spring Kafka retries can create topics such as:

~~~text
orders-retry-1000
orders-retry-5000
orders-dlt
~~~

Exact names depend on retry topology and naming strategy. A `topic` tag can stay manageable when topic counts are fixed.

Yet if retry topics are dynamically created per tenant, event, duration, deployment ID, or random suffix, a `topic` tag inflates cardinality fast.

Suitable metrics:

~~~text
app.kafka.recovery.attempts{
  topic_family="orders",
  stage="retry",
  outcome="scheduled"
}

app.kafka.recovery.attempts{
  topic_family="orders",
  stage="dlt",
  outcome="published"
}
~~~

Recommended tags:

| Tag | Controlled values |
|---|---|
| `stage` | `listener`, `retry`, `dlt`, `replay` |
| `outcome` | `success`, `failed`, `scheduled`, `published` |
| `error_category` | `deserialize`, `validation`, `infra`, `timeout`, `unknown` |
| `topic_family` | `orders`, `payments`, `inventory`, `other` |

Never use retry attempt UUIDs, original offsets, DLT offsets, or full exception messages as metric labels.

When tracing a DLT record, put **original topic/partition/offset** headers in logs or a DLT investigation store.

## 14. Exception class vs. exception message

Classifying errors is essential for alerts, yet label choices must stay bounded.

Compare:

~~~text
Good:
  error_category="timeout"

Acceptable when controlled:
  exception_class="org.apache.kafka.common.errors.TimeoutException"

Avoid:
  exception_message="Request for order 927341 to https://... timed out at 12:01:32"
~~~

Exception messages often contain:

- Event IDs, order IDs, or tenant IDs.
- URLs and dynamic request parameters.
- Timestamps.
- SQL queries, database keys, or stack trace fragments.
- Sensitive data details.

Putting verbatim exception messages into tags can spawn a new time series for every error. That is a common trigger for **cardinality explosion during an incident**: right as errors surge, metric labels multiply with the failing inputs themselves.

A sound strategy:

~~~text
exception -> classification function
               |
               +-- DeserializationException -> deserialize
               +-- TimeoutException         -> timeout
               +-- ValidationException      -> validation
               +-- ProducerFencedException  -> transaction
               +-- others                   -> unknown
~~~

Keep full exceptions in access-controlled logs, never in metric tags.

## 15. Writing a finite failure classifier

An enum prevents arbitrary metric values from being generated:

~~~java
public enum KafkaFailureCategory {
    NONE,
    DESERIALIZE,
    VALIDATION,
    TIMEOUT,
    TRANSACTION,
    INFRASTRUCTURE,
    UNKNOWN
}
~~~

Illustrative mapper:

~~~java
public final class KafkaFailureClassifier {

    private KafkaFailureClassifier() {
    }

    public static KafkaFailureCategory classify(Throwable error) {
        if (error == null) {
            return KafkaFailureCategory.NONE;
        }

        if (error instanceof org.apache.kafka.common.errors.TimeoutException) {
            return KafkaFailureCategory.TIMEOUT;
        }

        if (error instanceof org.apache.kafka.common.errors.ProducerFencedException) {
            return KafkaFailureCategory.TRANSACTION;
        }

        if (error instanceof org.springframework.kafka.support.serializer.DeserializationException) {
            return KafkaFailureCategory.DESERIALIZE;
        }

        return KafkaFailureCategory.UNKNOWN;
    }
}
~~~

This snippet illustrates attaching a **finite category**; real apps should unwrap wrapper exceptions, classify by root cause appropriately, and add business exception categories. Do not let the enum grow so large that every new exception class gets its own category.

When recording metrics, convert the enum to a standardized form like lowercase. Never use **`error.toString()`** as a category.

## 16. Counters with Micrometer: a safe example

Suppose you want to count processed records by listener, outcome, and error category:

~~~java
@Component
public class KafkaProcessingMetrics {

    private final MeterRegistry registry;

    public KafkaProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSuccess() {
        registry.counter(
                "app.kafka.listener.records",
                "listener", "orders-created",
                "outcome", "success",
                "error_category", "none")
            .increment();
    }

    public void recordFailure(KafkaFailureCategory category) {
        registry.counter(
                "app.kafka.listener.records",
                "listener", "orders-created",
                "outcome", "error",
                "error_category", category.name().toLowerCase(Locale.ROOT))
            .increment();
    }
}
~~~

Here, tag values come from enums or fixed literals. Series counts stay strictly bounded by listeners, outcomes, and categories.

In production code, counters can be pre-created once during initialization to avoid lookup overhead at high throughput. Still, **caching metric instances does not reduce cardinality** if every record still constructs a distinct tag combination.

Never pass `record.key()`, `eventId`, or `customerName` into `registry.counter(...)`.

## 17. Anti-pattern: creating metrics per record

Wrong example:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    registry.counter(
            "app.kafka.listener.records",
            "topic", record.topic(),
            "partition", String.valueOf(record.partition()),
            "offset", String.valueOf(record.offset()),
            "record_key", String.valueOf(record.key()))
        .increment();

    orderService.process(record.value());
}
~~~

Every record normally has a distinct offset, so an **offset tag practically guarantees a brand-new series per record**. Record keys are also commonly unbounded order or customer IDs.

A better version:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    long started = System.nanoTime();
    try {
        orderService.process(record.value());
        metrics.recordSuccess();
    }
    catch (RuntimeException ex) {
        metrics.recordFailure(
                KafkaFailureClassifier.classify(ex));

        log.error(
                "Kafka record failed: topic={}, partition={}, offset={}, key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                ex);

        throw ex;
    }
}
~~~

Here `topic`/`partition`/`offset`/`key` go to structured logs for investigation. **Apply appropriate redaction/truncation if keys contain PII**, and avoid logging payloads indiscriminately.

`started` simply marks where latency measurement could begin; to record a Timer, use `Timer.Sample` or `Observation` per supported APIs, without creating dynamic timestamp tags.

## 18. Timers/histograms multiply cardinality far more than counters

A counter typically maps to one or a few time series in the backend. A timer/histogram exports many more series, for example:

~~~text
app_kafka_processing_seconds_count{...}
app_kafka_processing_seconds_sum{...}

If histogram enabled:
app_kafka_processing_seconds_bucket{...,le="0.01"}
app_kafka_processing_seconds_bucket{...,le="0.05"}
app_kafka_processing_seconds_bucket{...,le="0.1"}
...
~~~

Each label combination multiplies by the configured histogram buckets. For example:

~~~text
400 tag combinations
  × 15 bucket series
= roughly 6,000 bucket series

Not yet counting count/sum and auxiliary series.
~~~

Hence a timer carrying `event_id` or `tenant_id` is vastly more dangerous than an equivalent counter.

When p95/p99 is needed:

- Enable histograms only on timers requiring SLOs.
- Choose boundaries/buckets matching realistic latencies.
- Keep label sets small.
- Never enable percentile histograms across all metrics just for prettier dashboards.
- Calculate newly added histogram series across listeners, outcomes, topics, and instances.

For metric-heavy systems, **bucket counts must be included in the time-series budget**.

## 19. Timer.Sample example with bounded tags

~~~java
@Component
public class OrderProcessingTimer {

    private final MeterRegistry registry;

    public OrderProcessingTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(Runnable work) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            work.run();
        }
        catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        }
        finally {
            sample.stop(
                    Timer.builder("app.kafka.processing")
                            .description("Kafka listener processing duration")
                            .tag("listener", "orders-created")
                            .tag("outcome", outcome)
                            .register(registry));
        }
    }
}
~~~

This code uses two finite outcome values and a fixed listener ID. Timers are looked up/registered under a bounded tag set.

If the app wants timers broken down by error category, that category must also come from a standard taxonomy. Avoid exception messages, full stack traces, or record keys.

In Spring Kafka, **built-in listener observation/timers** may already exist. Inspect existing instrumentation before writing custom timers to avoid double-recording and unnecessary cardinality.

## 20. Spring Kafka Micrometer timers and Observations

Spring Kafka integrates with Micrometer to measure listener and producer activity. Depending on version, you can use **Micrometer timers** or **Micrometer Observation** and emit metrics/traces through `ObservationRegistry`.

Example configuring observation on a listener container in supported versions:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        observedKafkaListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setObservationEnabled(true);
    return factory;
}
~~~

`KafkaTemplate` also supports enabling observation in supported versions, e.g. via the template setter:

~~~java
kafkaTemplate.setObservationEnabled(true);
~~~

Exact methods and metric names depend on Spring Kafka/Micrometer versions. Do not assume all timers and observations are enabled by default or produce identical metric names across every release.

**Tag hygiene still matters when the framework creates instrumentation.** Default conventions, listener IDs, client IDs, and custom tags can inflate series counts sharply, especially when applications plug in custom dynamic tags.

## 21. Micrometer Observation: low vs. high cardinality

Micrometer Observation separates:

- **Low-cardinality key values**: suitable as metric labels.
- **High-cardinality key values**: provide context for tracing, yet must not be exported as metric labels.

Conceptual example:

~~~java
Observation.createNotStarted(
        "app.kafka.order.processing",
        observationRegistry)
    .lowCardinalityKeyValue("operation", "consume")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("event.id", eventId)
    .observe(() -> orderService.process(event));
~~~

This illustrates separating context by cardinality in the Observation API. **High-cardinality observation keys do not automatically guarantee sensitive data safety**: tracing backends still have cost and security policies. If event IDs, user IDs, or payloads carry protected data, apply proper filtering and retention.

Never turn `event.id` into a `lowCardinalityKeyValue` just to look up traces from Prometheus.

To link metrics to traces, use trace exemplars or trace IDs in logs/traces as supported by your monitoring stack, rather than adding `trace_id` as a label on every sample.

## 22. Custom ObservationConventions can cause bugs

Spring Kafka supports custom observation conventions in appropriate versions. This is where instrumentation adds key values to spans/metrics.

Rules when writing conventions:

~~~text
Low cardinality:
  listener = orders-created
  operation = consume
  result = success | error
  topic_family = orders

High cardinality / tracing only:
  event.id
  kafka.record.offset
  message.key (if permitted)
  correlation.id
~~~

Never put raw payloads into conventions and never copy arbitrary Kafka headers into metric tags. Headers are controlled by producers or clients; mapping arbitrary headers to tags lets message senders accidentally or maliciously spawn unbounded series.

A convention should be code-reviewed as part of your **telemetry schema**, not merely as a technical utility.

## 23. MeterFilter: defense at the registry layer

Micrometer provides **`MeterFilter`** to accept, deny, or transform meter IDs before registration in `MeterRegistry`.

Example blocking dangerous tags:

~~~java
@Bean
MeterFilter denyDynamicKafkaTags() {
    return MeterFilter.deny(id ->
            id.getName().startsWith("app.kafka.")
                    && (id.getTag("event_id") != null
                        || id.getTag("order_id") != null
                        || id.getTag("record_key") != null
                        || id.getTag("offset") != null));
}
~~~

In Spring Boot, `MeterFilter` beans are typically applied to the registry by auto-configuration.

The example above **denies meters** carrying banned tags in the custom `app.kafka` namespace. This is a safety guardrail, not a substitute for avoiding dangerous tags in source code.

When `MeterFilter` denies a meter, instrumentation can receive a **noop meter**. Metrics disappear while business processing continues. Therefore, monitor filter changes with alerts/observability so an important operational metric is never silently hidden.

## 24. maximumAllowableTags: capping value counts

Micrometer also provides a way to cap tag values:

~~~java
@Bean
MeterFilter limitTenantTagValues() {
    return MeterFilter.maximumAllowableTags(
            "app.kafka.",
            "tenant",
            20,
            MeterFilter.deny());
}
~~~

General meaning: for meters starting with `app.kafka.`, allow only the filter-configured count of distinct `tenant` tag values; beyond that cap, apply the fallback filter (`deny`).

Important caveats:

- This cap **does not make tenant IDs a good metric tag**.
- Once tag values exceed the cap, new metrics get denied, creating blind spots.
- Filter state can reflect historically registered values rather than just currently active tenants.
- Each application instance owns a separate `MeterRegistry`; local caps are not cluster-wide cardinality quotas.
- Which values win depends on arrival order and can differ across pods.

Thus **`maximumAllowableTags` is a safety net**, not a primary strategy for per-tenant metrics across millions of tenants. Use whitelists/aggregations upfront and forecast series counts.

## 25. Normalizing tags with MeterFilter mapping

Another strategy maps dynamic tags into a finite set. For instance, keeping only allowed topic families:

~~~java
private static String topicFamily(String topic) {
    if (topic == null) {
        return "unknown";
    }
    if (topic.startsWith("orders.")) {
        return "orders";
    }
    if (topic.startsWith("payments.")) {
        return "payments";
    }
    if (topic.startsWith("inventory.")) {
        return "inventory";
    }
    return "other";
}
~~~

At the application instrumentation layer, it is best to call:

~~~java
registry.counter(
        "app.kafka.listener.records",
        "topic_family", topicFamily(record.topic()),
        "outcome", "success")
    .increment();
~~~

If using a `MeterFilter` to rewrite tags, ensure the filter maps/renames tags without dropping other tags and adheres to Micrometer contracts. Still, **normalizing at the source** is usually simpler and easier to test than a hidden filter mutating every metric of that name.

`topicFamily` functions should also be reviewed: overly broad prefixes can misgroup topics or expose infrastructure naming. Use managed whitelists/regexes when topologies grow complex.

## 26. Why dropping tags after scraping is not enough

Prometheus supports **metric relabeling** to drop series or labels before ingestion. That saves storage/backend load yet has limits:

~~~text
Spring application
  |
  +-- Micrometer already created meter IDs
  +-- Actuator already prepared metric export
  |
  v
Prometheus scrape
  |
  v
metric_relabel_configs
  |
  +-- drop/keep series or labels
  |
  v
Prometheus storage
~~~

If the application already registered hundreds of thousands of meters, dropping post-scrape **does not erase meter registry and export overhead inside the application process**. Nor does it shrink the HTTP response of `/actuator/prometheus` before scraping.

Therefore, apply defense in depth:

1. **Instrumentation source**: never emit unbounded tags.
2. **Micrometer `MeterFilter`**: cap/block before meter registration.
3. **Prometheus metric relabeling**: drop unwanted labels/series at ingestion.
4. **Backend quotas**: enforce active series, ingestion rate, and storage limits.
5. **Monitoring alerts**: catch sudden spikes before resources run out.

Never rely on a single layer to fix the entire telemetry pipeline.

## 27. Spring Boot Actuator/Prometheus example

A basic Spring Boot configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: orders-service
      environment: production
~~~

The application requires suitable dependencies such as Spring Boot Actuator and the Micrometer Prometheus registry; without the registry, the Prometheus endpoint may not be exposed.

This config sets stable common tags. It does not solve dynamic tags inside custom metrics or Kafka client meters.

In operations:

- Never expose sensitive Actuator endpoints directly to the Internet.
- Restrict `/actuator/prometheus` access via monitoring network/security policies.
- Never put secrets into common tags.
- Measure response size and scrape duration.
- Size scrape timeouts to match export duration.
- Confirm metrics carry valid values before adding labels to dashboards.

If metrics endpoint responses bloat suddenly after a deployment, check tag cardinality rather than merely raising the Prometheus scrape timeout.

## 28. Common tags: consistent without overusing

Common tags help distinguish application, environment, or region.

~~~text
application = orders-service
environment = prod
region = ap-southeast-1
~~~

Yet common tags apply to **vast numbers of meters** across the app. Adding a per-request fluctuating tag to common tags amplifies impact far beyond a single metric.

Never put:

~~~text
request_id
event_id
user_id
order_id
last_processed_offset
current_transactional_id
~~~

into common tags.

In Kubernetes, `service`, `namespace`, `pod`, and `instance` labels are commonly added at scrape/service discovery layers. Identify the authoritative source for those labels so you do not spawn redundant variants like `application`, `app`, `app_name`, and `service_name` on the same metric without adding value.

**A consistent tag convention matters more than having lots of tags.**

## 29. Metric schemas and namespaces

Teams should document an explicit contract for each metric:

~~~text
Metric:
  app.kafka.listener.records

Type:
  counter

Unit:
  records

Purpose:
  count handled records by outcome

Allowed tags:
  application: set from common tags
  listener: fixed listener IDs
  outcome: success | error | skipped
  error_category:
    none | deserialize | timeout | validation | transaction | unknown

Forbidden:
  event_id, record_key, offset, payload, exception_message

Owner:
  messaging-platform

Budget:
  maximum expected series documented per service
~~~

For Kafka latency timers, also document whether histograms are enabled, bucket configuration, SLOs, and expected series multiplication.

Metric names themselves must not embed dynamic IDs:

~~~text
Wrong:
  app.kafka.orders.customer123.failures
  app.kafka.orders.customer124.failures

Good:
  app.kafka.orders.failures{customer_tier="premium"}
~~~

Metric name is part of meter identity too; creating a new metric name per customer causes cardinality identical to creating new tag values.

## 30. Budgeting cardinality

A budget should be calculated **per metric family and per service**, rather than setting only one cluster-wide cap.

Forecast example for a listener latency timer:

| Dimension | Expected values |
|---|---:|
| `listener` | 6 |
| `topic_family` | 4 |
| `outcome` | 2 |
| `instance` | 10 |
| **Max combinations** | **480** |

If the timer exports 12 buckets plus count/sum, 480 combinations can turn into several thousand Prometheus series.

A realistic budget accounts for:

1. Peak service replicas, not just current average.
2. Consumer concurrency.
3. Listener IDs per deployment.
4. Supported topic families and group IDs.
5. Histogram buckets, sum, count, and auxiliary series.
6. Native Kafka producer/consumer client metrics.
7. Series churn during rollouts/restarts.
8. Number of environments/clusters sharing one backend.

A budget is a **verifiable estimate**, not a guarantee every combination exists. Measure actual active series after a small rollout and compare against the forecast.

## 31. Checking active series with Prometheus

Prometheus provides functions/queries to count series by namespace or label set, depending on ingested data.

Example counting series whose metric names start with `app_kafka_` in an instant query:

~~~promql
count({__name__=~"app_kafka_.*"})
~~~

Count by metric name:

~~~promql
count by (__name__) ({__name__=~"app_kafka_.*"})
~~~

Count distinct values of the `topic` label appearing in a metric:

~~~promql
count(
  count by (topic) (app_kafka_listener_records_total)
)
~~~

These queries are illustrative; if a metric lacks a `topic` label or uses a different name in a deployment, substitute exact names/tags.

A metric with many time series can reflect a legitimate need, such as partition lag in a huge cluster. Before dropping anything, weigh **cost against operational value**.

## 32. Watch label churn, not just active series

A service can keep active series modest while continuously spawning new series as pods restart or event IDs rotate.

In Prometheus, check:

- Active series by metric and job.
- New series creation rate in TSDB via available backend internal metrics.
- Remote-write sample/series ingestion and queue backlog.
- WAL/storage growth.
- Scrape duration and scraped samples per target.

A telltale pattern:

~~~text
Running service:
  10 pods, each currently has 200 series

Over the day:
  pods change identity hundreds of times
  labels include a fresh pod UUID each time

Backend accumulates many short-lived historical series
~~~

This is **series churn**, which does not always show up as rising active series. Watching only current series counts can miss heavy indexing and storage pressure.

For labels like `client_id`, `pod_uid`, and `session_id`, verify stability across deployments and restarts.

## 33. Security rules for Kafka metric labels

Metric labels do not just cost money—they are also a data-leak channel:

~~~text
record_key = email@example.com
tenant_id = customer-secret-code
exception_message = Authorization failed for token ...
payload = {"creditCard": "..."}
~~~

Metrics are often accessible across many dashboards, exporters, Prometheus servers, and remote-write endpoints. Data placed in labels can be retained long-term with broader access than application logs.

Rules:

- Never put PII, access tokens, passwords, emails, phones, or account numbers into labels.
- Never map Kafka headers to unbounded tags.
- Never use raw exception messages or stack traces.
- Use **tier/region/category** when segmentation analysis is needed.
- Control retention and RBAC on telemetry backends.
- When identifiers must enter traces/logs, apply masking/hashing per policy; hashing alone does not solve cardinality if every value remains unique.

**Hashing an event ID before putting it in a label still creates just as many distinct values.** Hashing hides direct readability without shrinking cardinality.

## 34. Do native Kafka client metrics need filtering?

Kafka producers/consumers expose many JMX/client metrics: request rate, bytes in/out, fetch latency, records lag, rebalance metrics, connection metrics, and more. Spring/Kafka instrumentation can bind or export these via Micrometer.

Some metrics are valuable at client/partition granularity; others may be excessive if the application only needs aggregate SLOs.

When enabling native client metrics:

1. Check how many consumer/producer instances are actually created.
2. Check default tags such as `client-id`, `topic`, `partition`, or `node`.
3. Check how many metric families exist per client.
4. Check whether producer caches hold many transactional producers.
5. Measure newly spawned series after raising listener concurrency.
6. Filter unused groups if cost is too high.
7. Never strip metrics needed to diagnose lag or broker/network failures without a replacement.

Using `KafkaClientMetrics`, `MicrometerConsumerListener`, or `MicrometerProducerListener` depends on integration and Spring Kafka version. These APIs can create binders with differing tags; verify your deployed version instead of assuming identical metric names across releases.

## 35. Partition tag in consumer lag: a controlled exception

Per-partition lag is one case where a `partition` tag can genuinely be needed:

~~~text
Consumer group orders-service:
  P0 lag = 0
  P1 lag = 0
  P2 lag = 50,000
  P3 lag = 0
~~~

If dashboards show only average lag, a stalled partition P2 gets masked. Partition-level lag catches skew and hot partitions.

Keep it bounded:

- Only lag-related metric families need the `partition` tag.
- Never attach `partition` to all business metrics.
- Evaluate total partition count across the group and cluster.
- Use appropriate retention for fine-grained data.
- Revisit budgets and dashboards whenever partition counts jump.

A tiered design:

~~~text
General alert:
  max group lag > threshold

Diagnostic dashboard:
  lag by topic/partition to spot hot partitions

Logs/traces:
  event IDs and offsets when hunting specific records
~~~

Match granularity to the question instead of copying the same tag set onto every metric.

## 36. DLT metrics must separate success and failure

When a consumer fails and a recoverer routes records to the DLT, a dashboard with only a "DLT attempts" counter cannot tell whether publishing succeeded.

Distinguish outcomes:

~~~text
app.kafka.recovery.records{
  stage="dlt",
  outcome="publish_success",
  error_category="deserialize"
}

app.kafka.recovery.records{
  stage="dlt",
  outcome="publish_failed",
  error_category="infrastructure"
}
~~~

`outcome` values should be a bounded enum, never verbatim Kafka producer exceptions.

When publishing fails, **never increment a success counter merely because the recoverer was called**. Concluding success must follow acknowledgment/send-result semantics provided by the recovery path.

For DLT investigations, store **original topic/partition/offset** in Kafka headers and logs; never create metric labels per original offset.

## 37. Transactions and producer fencing metrics

In Kafka transactional processing, signals to track include:

- Transaction begin/commit/abort outcomes.
- `ProducerFencedException` counts.
- Commit duration.
- Transaction timeout occurrences.
- `ConsumerStoppedEvent` `reason=FENCED`.
- Retries/restarts after fencing.

A suitable schema:

~~~text
app.kafka.transaction.events{
  application="orders-service",
  operation="commit",
  outcome="error",
  failure_category="fenced"
}
~~~

Do not put full `transactional.id` on every metric to distinguish individual producers. To investigate a fenced producer, log its exact identity alongside instance/pod in access-controlled structured logs.

With `ConsumerStoppedEvent`, the **`reason`** tag typically has a finite value set (`NORMAL`, `FENCED`, `AUTH`, `NO_OFFSET`, `ERROR`, and version-supported values). It is a safe tag as long as it never turns into a verbatim exception message.

When metrics for `reason=FENCED` rise, drill down into logs for `transactional.id` and timelines rather than putting `transactional.id` on counters.

## 38. Consumer application events and cardinality

Spring Kafka emits events such as `ConsumerPausedEvent`, `ConsumerResumedEvent`, `ConsumerStoppedEvent`, `ListenerContainerIdleEvent`, and `NonResponsiveConsumerEvent`.

Useful metrics:

~~~text
app.kafka.consumer.lifecycle.events{
  listener="orders-created",
  event="paused"
}

app.kafka.consumer.lifecycle.events{
  listener="orders-created",
  event="resumed"
}

app.kafka.consumer.lifecycle.events{
  listener="orders-created",
  event="stopped",
  reason="fenced"
}
~~~

A finite **`event` type** or **`stop` reason** works far better than **`event.getSource().toString()`**, which can contain object identities or ever-changing child consumer IDs.

For concurrent containers, a bounded child index can aid debugging, yet avoid attaching full thread names with runtime-generated IDs without clear need and budget.

Never use lifecycle metrics as a logbook of every partition event; that detail belongs in logs when needed.

## 39. Controlling empty and malformed label values

When data is unknown, instrumentation sometimes emits:

~~~text
topic=""
topic="null"
topic="unknown"
topic="N/A"
topic="undefined"
~~~

Five ways to express the same thing bloat cardinality and complicate queries.

Tag hygiene requires consistency:

- Pick one fallback value such as **`unknown`**.
- Never use `String.valueOf(null)` if it emits `"null"` outside convention.
- Normalize casing: `success`/`error`, never mixing `SUCCESS`, `Success`, and `success`.
- Never embed whitespace or timestamps in labels.
- Distinguish `unknown`, `none`, and `not_applicable` when they carry distinct operational meanings.

Normalization helper example:

~~~java
private static String normalizeOutcome(String value) {
    if ("success".equalsIgnoreCase(value)) {
        return "success";
    }
    if ("error".equalsIgnoreCase(value)) {
        return "error";
    }
    if ("skipped".equalsIgnoreCase(value)) {
        return "skipped";
    }
    return "unknown";
}
~~~

Never pass unrecognized input strings straight into tags when unmatched; doing so defeats cardinality bounding.

## 40. Metric schema changes across deployments

A deployment might change:

~~~text
Before:
  tag result="ok"

After:
  tag outcome="success"
~~~

During a rolling update, both versions run concurrently and emit two sets of series. Legacy dashboards/alerts may miss the new metric.

When changing tags:

1. Plan migrations for dashboards and PromQL alerts.
2. Estimate the overlap window when both versions run side by side.
3. Budget the temporary surge in series.
4. Choose tag/value names meant to stay stable long-term.
5. Never alter outcome definitions arbitrarily across teams.
6. Remove old instrumentation/recording rules after the compatibility period.

Tag hygiene is also **telemetry schema versioning**. A renamed label will not break Java compilation, yet it breaks alerts silently.

## 41. How to check cardinality before merging

Code reviews should inspect every metric creation site:

~~~text
registry.counter(...)
Counter.builder(...)
Timer.builder(...)
DistributionSummary.builder(...)
Gauge.builder(...)
Observation.lowCardinalityKeyValue(...)
custom ObservationConvention
MeterFilter map(...)
Kafka/Micrometer binder configuration
~~~

A simple test can invoke instrumentation with many distinct event IDs and verify meter counts do not grow with event count.

Test logic example:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
KafkaProcessingMetrics metrics = new KafkaProcessingMetrics(registry);

for (int i = 0; i < 1000; i++) {
    metrics.recordSuccess();
}

long meterCount =
        registry.getMeters().stream()
                .filter(m -> m.getId().getName()
                        .equals("app.kafka.listener.records"))
                .count();

assertThat(meterCount).isEqualTo(1L);
~~~

Here, every `recordSuccess()` call uses the same tag set. Thus 1,000 events increment one counter's value **without creating 1,000 meter identities**.

If the `listener` tag were `"orders-"` plus event ID, this test would immediately catch `meterCount` climbing with events.

You do not need to test a million events to expose the bug; testing a few hundred to a few thousand synthetic IDs suffices to prove unwanted cardinality growth.

## 42. Testing MeterFilter rejecting banned tags

You can unit test filters with `SimpleMeterRegistry`:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config().meterFilter(
        MeterFilter.deny(id ->
                id.getTag("event_id") != null));

registry.counter(
        "app.kafka.listener.records",
        "event_id", "E-1001")
    .increment();

assertThat(
        registry.find("app.kafka.listener.records")
                .meters())
        .isEmpty();
~~~

This is an illustrative test pattern; add matching imports and assertion libraries. `MeterFilter` can return a noop meter for denied registrations, so `counter.increment()` not throwing does not mean the metric was recorded.

More importantly, do not test only the filter. Test that instrumentation **never emits an `event_id` tag in the first place**. Filters are a second line of defense against future code or convention slips.

## 43. Incident: metrics backend overloaded by event_id

A realistic production scenario:

~~~text
New deployment:
  adds event_id tag to listener timer

Traffic:
  10,000 records/minute

After a few minutes:
  meter IDs surge rapidly
  /actuator/prometheus response bloats
  scrape duration spikes
  Prometheus ingestion and memory climb
  dashboards slow down or fail
~~~

When the application hits business errors, distinct failed event IDs also surge, piling extra load onto monitoring right when it is needed most.

Emergency response procedure:

1. Identify the metric family and tag driving series growth.
2. Confirm which recent deploy or custom instrumentation emits dynamic labels.
3. Temporarily **disable/deny the offending metric at the application registry** if a safe config toggle exists.
4. If needed, apply metric relabel drop/keep rules to cut backend ingestion.
5. Roll back or hotfix instrumentation, stripping `event_id`/`exception_message` from metric labels.
6. Verify scrape duration, active series, and series churn recover afterward.
7. Confirm the monitoring backend stabilized before re-enabling heavy alerts/queries.
8. Record a postmortem: why did reviews/tests miss the cardinality leak?

Do not rashly drop critical Kafka metrics for consumer lag, transaction failures, or DLTs because of one buggy custom metric. Isolate the affected metric family.

## 44. Incident: partition tags surge after scaling

Suppose a topic grows from 16 to 256 partitions and a service scales from 4 to 30 consumers. Native client metrics keyed by `client-id`, `topic`, `partition`, and `node` can multiply series counts.

No `event_id` tag is involved, yet:

~~~text
Consumers increase
Partitions increase
Metrics per client increase
Histogram buckets enabled broadly

=> Series jump substantially
~~~

This is not necessarily an instrumentation bug; it can be a **consequence of topology growth**.

Solutions:

- Budget series before raising partition counts.
- Select only metric families that genuinely need partition detail.
- Trim redundancy between application metrics and native Kafka metrics.
- Use aggregate group-level alerts paired with partition-level drill-downs.
- Review scrape intervals and retention.
- Adjust backend capacity or metric filtering.

Do not blindly delete partition lag metrics if they are the sole way to spot hot partitions.

## 45. Incident: client ID churn from restart loops

A service hits producer fencing and enters a crash loop. Each restart generates a new client ID or pod UID, forcing the metrics backend to retain short-lived time series.

~~~text
12:00  pod-A-1 -> client_id=orders-abc
12:05  pod-A-2 -> client_id=orders-def
12:10  pod-A-3 -> client_id=orders-ghi
...
~~~

When investigating:

1. Fix the root cause of restarts/fencing first.
2. Measure series churn and new client IDs.
3. Check whether select metrics can use logical listener IDs instead of runtime IDs.
4. Keep detailed client IDs only on native metrics that need them.
5. Ensure pod/instance labels in scrape metadata are not duplicated into multiple variants.

Tag hygiene does not replace producer/container reliability engineering. If an app is crash-looping, curbing label churn only reduces telemetry overhead—it does not cure the root cause.

## 46. Alerting should not depend on unstable tags

Alerts should rest on aggregate signals:

~~~promql
sum by (application, listener) (
  rate(app_kafka_listener_records_total{outcome="error"}[5m])
)
~~~

For error ratio, also compute total processed and guard the denominator with `clamp_min`:

~~~promql
sum by (application, listener) (
  rate(app_kafka_listener_records_total{outcome="error"}[5m])
)
/
clamp_min(
  sum by (application, listener) (
    rate(app_kafka_listener_records_total[5m])
  ),
  0.001
)
~~~

PromQL above illustrates a ratio for a custom counter; real alert rules must account for low traffic, missing data, and SLOs.

Never create one alert rule per event ID or exception message. Instead, alert by listener/topic family/error category and link to logs/traces carrying correlation context.

To alert on transaction fencing, group cleanly by application/listener/reason rather than creating separate rules per `transactional.id`.

## 47. Two-tier dashboard design

A practical reliability dashboard:

### Tier 1: Overview

- Processing rate.
- Error rate.
- p95/p99 processing latency.
- Max/group consumer lag.
- Rebalance rate.
- DLT publish success/failure.
- Transaction commit/abort/fencing.
- Pause/stop/idle/non-responsive events.

All using small tag sets so dashboards load fast.

### Tier 2: Drill-down

- Specific whitelisted topics.
- Partition lag.
- Client-specific native Kafka metrics.
- Exception classes where needed.
- Trace/log links by listener, event ID, or original topic/partition/offset.

You do not need partition-level views for every service on every dashboard. When investigating, drill-downs give enough detail without multiplying every metric by partition and tenant.

## 48. Health indicators for the telemetry pipeline

The metrics pipeline itself needs monitoring:

| Indicator | What an unusual rise may signal |
|---|---|
| App meter registry size | Dynamic tag registration |
| Prometheus scrape samples | Growing metric families or label combinations |
| Scrape duration | Metrics endpoint too huge or app slowing down |
| Active series | Rising tag cardinality |
| Series creation/churn | Random IDs, rollouts/restarts, or event tags |
| Remote write queue backlog | Backend cannot keep up with ingestion |
| Metrics endpoint response bytes | App exporting too many samples |
| Query latency | High cardinality or overly broad queries |

Not every monitoring backend exposes identically named metrics. Use the native metrics provided by your deployed Prometheus, collector, or vendor version.

If the telemetry pipeline degrades, alerts arrive late or without data. An observability strategy must balance detail against the operational health of the monitoring system itself.

## 49. A tag hygiene checklist for code reviews

Before accepting a new metric, ask:

1. Which SLO, dashboard, alert, or capacity decision does this metric serve?
2. Which tags are strictly needed for that decision?
3. What is the maximum number of values per tag over a day/month?
4. Do any tags come from record keys, headers, payloads, or exception messages?
5. Do any IDs rotate across retries, deployments, or partition assignments?
6. If topic/tenant/partition counts grow 10x, how does the series budget scale?
7. If histograms are enabled, how many bucket series does each combination spawn?
8. Does this duplicate default Kafka/Micrometer instrumentation?
9. Could PII or secrets leak into labels?
10. Are `MeterFilter` guards and tests in place to block dynamic tags?
11. Is there a dashboard/alert owner and migration path when the schema changes?
12. Is there an alert when cardinality, churn, or scrape duration spikes abnormally?

A good metric has **clear value, a small tag schema, an estimable cardinality, and an owner**. More tags does not mean better.

## 50. Implementing metric cardinality and tag hygiene

For a production Spring Kafka application:

1. Inventory existing Spring Kafka listener metrics, producer metrics, native Kafka client metrics, and custom metrics.
2. Classify tags into low, bounded, and high/unbounded cardinality.
3. Ban `event_id`, `record_key`, `offset`, raw `exception_message`, payloads, and unbounded tenant IDs from metric labels.
4. Build whitelists for listener IDs, error categories, outcomes, and topic families.
5. Use Micrometer common tags for stable `application`/`environment` values.
6. Use Observation low-cardinality key values for metric dimensions; keep high-cardinality context strictly in controlled traces/logs.
7. Apply `MeterFilter` as a safety net for banned tags and tag value caps.
8. Forecast series across replicas, listeners, topics, partitions, outcomes, and histogram buckets.
9. Keep partition-level detail only on metrics needed to diagnose lag or skew.
10. Never rely on Prometheus metric relabeling as the sole fix for in-app meter explosion.
11. Write tests feeding many dynamic record IDs to prove meter counts do not grow with message counts.
12. Monitor active series, series churn, scrape duration, exporter response size, and ingestion rate.
13. Design alerts aggregated by service/listener/outcome; use logs and traces to locate individual records.
14. Maintain rollout/rollback plans when changing metric names or tags.
15. Make tag schemas and cardinality budgets part of routine code reviews and operations.

**Metric cardinality and tag hygiene** are part of Spring Kafka system reliability, not merely monitoring cost optimization. A single metric spawning hundreds of thousands of series can blind monitoring right when consumer lag, DLT failures, or transaction fencing spike. Choosing **bounded, operationally meaningful labels** while keeping record IDs, offsets, exception details, and correlation context in logs/traces lets systems detect incidents early and trace root causes without overwhelming the metrics backend.

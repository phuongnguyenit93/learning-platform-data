# micrometerTags

In Spring Kafka operations, the question "where is the listener processing slowly?" often cannot be answered by a single consumer lag number. A single application can have multiple listeners, consumer groups, business flows, and workload types. If all processing times are recorded into one generic metric, dashboards struggle to identify **which flow is slow, where errors are happening, and which release is affected**.

Spring Kafka integrates with Micrometer to measure listener execution duration. The **`micrometerTags`** property allows adding **static tags** to the timer recorded by the listener container. Tags such as `service=order-processing`, `pipeline=orders`, and `workload=consumer` make it easy to filter and aggregate data in Micrometer, Prometheus, or other monitoring systems. In addition, some Spring Kafka versions support `micrometerTagsProvider` to determine tags per `ConsumerRecord`.

Key point: `micrometerTags` is a **telemetry configuration**; it does not alter Kafka consumer groups, offset commits, retries, dead-letter handling, or processing semantics. Proper tagging makes metrics easy to observe; setting tags arbitrarily from `eventId`, `orderId`, or payload can cause the number of time series to grow out of control. This lesson focuses on configuration, scope of impact, and safe operations.

## 1. What does Spring Kafka's Micrometer timer measure?

When Micrometer is on the classpath and the listener container is properly configured, Spring Kafka can record a timer for listener invocation duration. The typical meter name is **`spring.kafka.listener`**. The timer provides information such as invocation count, total time, maximum time within the measurement window, and, when configured, histograms/percentiles.

```text
Kafka topic orders
        |
        v
KafkaConsumer.poll()
        |
        v
Spring Kafka listener container
        |
        +--> @KafkaListener.process(record)
        |                |
        |                +--> business logic / DB / HTTP
        |                |
        |                v
        |          returns or throws exception
        |
        +--> Micrometer timer
                   |
                   +--> duration
                   +--> framework-provided result/exception tags
                   +--> application-configured micrometerTags
```

**The listener timer is not synonymous with the end-to-end duration of a record.** It typically measures listener execution, excluding the full time spent in the Kafka log before being polled, wait time in retry topics, time taken by the producer to send to the broker, or all subsequent offset commit operations. The exact scope depends on the Spring Kafka version and listener mode.

Framework-added tags may include listener/container identifier, success/failure result, and exception information; specific names and tag sets should be verified on actual meters in your deployed version. `micrometerTags` adds **application**-meaningful operational labels and does not replace the framework's own distinction between success and failure.

## 2. `micrometerTags` is a static tag map

Spring Kafka's `ContainerProperties` has a setter to declare a `String -> String` map for Micrometer timers:

```java
factory.getContainerProperties().setMicrometerTags(
        Map.of(
                "service", "order-processing",
                "pipeline", "orders",
                "environment", "production"));
```

These values **do not change per record**. Every listener invocation belonging to a container using this configuration can receive these additional tags, provided Micrometer timers are enabled.

| Static tag | Example | Why is it useful? |
|---|---|---|
| `service` | `order-processing` | Filter metrics by responsible service |
| `pipeline` | `orders` | Separate orders business flow from payments or inventory |
| `environment` | `production` | Distinguish environments if metrics are aggregated centrally |
| `team` | `fulfillment` | Map ownership and alerts |
| `component` | `kafka-listener` | Distinguish listener latency from HTTP handler latency |

These tags have a relatively small and stable number of values, so they are generally suitable for metrics. A `service` tag with 15 values is acceptable; an `order_id` tag with millions of values will create vast numbers of time series and is a design mistake.

Do not set keys that collide with **internal listener timer tags** such as the result tag or meter identifier without understanding the merge rules. An application tag name can break analysis or yield unpredictable results if it conflicts with a framework tag.

## 3. Conditions for `micrometerTags` to appear on metrics

Adding `setMicrometerTags(...)` alone does not guarantee the monitoring backend will have data. Both the timer creation mechanism and a suitable `MeterRegistry` are required.

In Spring Kafka releases with Micrometer timer support, the listener container has a `micrometerEnabled` property. Timers are typically enabled by default when Micrometer is present and a suitable `MeterRegistry` exists, though behavior also depends on framework version, context configuration, and Observation mode. You can set it explicitly:

```java
ContainerProperties properties = factory.getContainerProperties();
properties.setMicrometerEnabled(true);
properties.setMicrometerTags(Map.of("pipeline", "orders"));
```

A Spring Boot application that wants to export Prometheus metrics typically needs corresponding dependencies and observability settings, such as the Micrometer Prometheus registry and Spring Boot Actuator. Endpoint exposure and authentication mechanisms must be configured according to operational policy. Never leave public metrics endpoints containing topology information or sensitive details open without access controls.

When a listener has not yet received any records, the timer may **not yet have samples to report**. Not seeing a specific series right after startup is not enough to conclude that `micrometerTags` was ignored. Send a test record or observe a listener with actual traffic.

## 4. Complete container factory configuration example

Suppose a service processes order events with `@KafkaListener`. The configuration below illustrates static tags on a factory dedicated to this flow:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class OrdersListenerConfiguration {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties properties = factory.getContainerProperties();
        properties.setAckMode(ContainerProperties.AckMode.RECORD);
        properties.setMicrometerEnabled(true);
        properties.setMicrometerTags(Map.of(
                "service", "order-processing",
                "pipeline", "orders",
                "component", "kafka-listener"));

        return factory;
    }
}
```

The listener specifies the corresponding factory:

```java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersKafkaListenerContainerFactory")
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
```

`OrderEvent` and `OrderService` are hypothetical application classes; the consumer factory must be configured with serializers/deserializers, Kafka bootstrap, authentication, and required properties. The example only illustrates `micrometerTags` configuration; it does not by itself provide retry/error handlers, idempotency, or DLT rules.

With `concurrency=3`, the factory can create multiple child consumer containers. Static tags apply to listener containers created from the factory; analyzing individual children relies on framework-provided tags/identifiers and runtime configuration. Do not create arbitrary tags based on random thread IDs per record.

## 5. Scope: one factory can serve multiple listeners

An easy operational mistake is forgetting that **tags set on a factory apply to the containers created by that factory**. If the same `ordersKafkaListenerContainerFactory` is used for both orders and payments listeners, both can receive `pipeline=orders`, mislabeling payments metrics.

Configuration example to avoid:

```java
// A factory with tag pipeline=orders
@KafkaListener(
        topics = "orders",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void processOrder(OrderEvent event) { /* ... */ }

// Should not use that factory for a different business flow
@KafkaListener(
        topics = "payments",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void processPayment(PaymentEvent event) { /* ... */ }
```

This example omits generic type details to highlight the mislabeling risk. If multiple listeners handle independent business flows, you can create **dedicated factories** per workload group or use static tags at a shared service level and rely on container identifiers to distinguish listeners. Do not overuse separate factories just to add one tag when doing so causes consumer configs to drift out of sync; choose the model that fits the codebase scale.

Stable rollout steps typically are: define observability boundaries (service, listener, pipeline); define a tag vocabulary; place tags at a scope that avoids mislabeling data; verify metrics after traffic flows through the listener.

## 6. `micrometerTagsProvider`: per-record tags

Besides the static map, Spring Kafka versions support `micrometerTagsProvider`, allowing tags to be provided based on the **`ConsumerRecord` being processed**. Unlike `micrometerTags`, the provider can read headers, topic, key, or record metadata to decide tags. This flexibility also introduces the risk of **cardinality explosion**.

A reasonable usage is normalizing event types into a small set like `created`, `cancelled`, `updated`, `other`. Do not export arbitrary full header values as tags.

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class SafeKafkaTags {

    private SafeKafkaTags() { }

    public static Map<String, String> fromRecord(
            ConsumerRecord<?, ?> record) {

        Header header = record.headers().lastHeader("event-type");
        if (header == null || header.value() == null) {
            return Map.of("event_family", "other");
        }

        String value = new String(
                header.value(), StandardCharsets.UTF_8);

        String family;
        switch (value) {
            case "OrderCreated":
                family = "created";
                break;
            case "OrderCancelled":
                family = "cancelled";
                break;
            case "OrderUpdated":
                family = "updated";
                break;
            default:
                family = "other";
        }

        return Map.of("event_family", family);
    }
}
```

Attach the provider to the container factory in versions supporting this API:

```java
ContainerProperties properties = factory.getContainerProperties();

properties.setMicrometerTags(
        Map.of("service", "order-processing", "pipeline", "orders"));

properties.setMicrometerTagsProvider(SafeKafkaTags::fromRecord);
```

The provider above always returns a value from a small set, even when a producer sends unexpected values. This is an **allowlist** mechanism, not merely escaping header characters. If code returned `new String(header.value())` directly, a buggy producer could generate millions of tag values and overload the monitoring system.

Per-record tagging features and their applicability to record/batch listeners must be verified for the Spring Kafka version in use. With a batch listener, do not assume a provider callback is invoked individually for each record in the batch unless you have confirmed the behavior and API. If per-record metrics are needed in a batch, instrument at the application layer as designed.

## 7. Static and dynamic tags should be chosen differently

| Characteristic | `micrometerTags` | `micrometerTagsProvider` |
|---|---|---|
| Value source | Container/factory configuration | `ConsumerRecord` metadata |
| When value is known | When building the container | When processing the record |
| Good examples | `service=orders`, `team=checkout` | `event_family=created` from an allowlist |
| Cardinality risk | Usually low if map has fixed values | High if taking uncontrolled keys/headers/payloads |
| Cost | Relatively stable | Can create many series/timers per tag combination |
| Scope | Records handled by the container | Each record in supported listener modes |

**Prefer static tags** when the same label describes the entire listener. Use a provider only if an operational question truly requires breaking down by a record attribute with **a small, stable, and non-sensitive set of values**. Fields such as tenant ID, user ID, or order ID generally belong in structured logs/traces, not metric tags.

When `micrometerTagsProvider` varies tag values over time, each combination can correspond to a meter/time series. Even if records appear only once, series can remain in the registry/backend for some time; seeing no immediate issue inside the JVM does not guarantee the monitoring system will not suffer increased storage costs.

## 8. Cardinality explosion: a concrete example

Suppose a service processes 100,000 orders per hour and adds an `order_id` tag taken from the Kafka key:

```java
// DO NOT DO THIS: each record can create a different tag value.
properties.setMicrometerTagsProvider(record ->
        Map.of("order_id", String.valueOf(record.key())));
```

If every `order_id` is distinct, there could already be 100,000 tag combinations in a single hour. When the timer also carries labels such as container, `result`, `exception`, environment, or replica, the series count can multiply by the product of those dimensions. The metrics backend may have to store millions of time series, slowing queries, increasing memory usage, raising costs, and risking loss of monitoring data.

```text
Potential series count ≈
  containers/instances count
  × result/exception combinations
  × event family tag values
  × additional tag dimensions
```

This estimate is a design bound, not a claim that every combination will necessarily be created. Still, it shows why **every new tag must be reviewed for cardinality**.

The following tags are generally **unsuitable**:

- `order_id`, `payment_id`, `event_id`, `request_id`, `correlation_id`.
- Kafka offset or raw message timestamp.
- JSON payload, exception message, parameterized SQL query.
- Full URL with path parameters or query strings containing IDs.
- Unbounded tenant/user IDs without a strictly limited count.

When you need to trace a specific order, put the ID into **structured logs/traces** along with topic-partition-offset, not into metric labels.

## 9. Which tags can be based on Kafka metadata?

Kafka attributes vary widely in cardinality:

| Attribute | Suitable as a metric tag? | Notes |
|---|---|---|
| Service/application name | Usually yes | Bounded values within a system |
| Listener ID | Usually yes, if bounded | May already be added by framework via internal tag |
| Topic name | Conditionally | Reasonable for a bounded topic set; dynamic topic names need control |
| Partition number | Conditionally | Bounded count, though it multiplies series across dimensions |
| Consumer group | Conditionally | Dynamic per-deploy/per-tenant groups easily inflate cardinality |
| Event type from finite enum | Usually yes | Use an allowlist; map unknown to `other` |
| Event key | Usually no | Typically a business identifier |
| Offset | No | Continuously increasing, extremely high cardinality |
| Exception class | Conditionally | Framework may already provide it; never include exception message |

Do not duplicate tags like `topic`, `partition`, `name`, or `result` if the Micrometer timer already records the same meaning. Inspect existing tags via the registry or metrics endpoint before designing an extra map. Tag names and label normalization can vary by version or monitoring exporter.

## 10. Same metric name, multiple time series

Micrometer models a meter by **name + tag set**. Two listeners both recording `spring.kafka.listener` with different tags create distinct time series. This is intentional for independent observability, but it also means the tag vocabulary must stay consistent.

Example:

```text
spring.kafka.listener
  service=order-processing
  pipeline=orders
  result=success

spring.kafka.listener
  service=order-processing
  pipeline=orders
  result=failure

spring.kafka.listener
  service=payment-processing
  pipeline=payments
  result=success
```

This illustrates the tag-value model; actual Spring Kafka default tags may add `name`, `exception`, or other labels. When building dashboards, do not simply query `spring.kafka.listener` and sum everything while forgetting to filter by pipeline: an aggregate can mask a listener timing out.

If a deployment arbitrarily renames the `pipeline` tag to `flow`, old dashboards may lose data or display two separate sets of series. Treat metric tags as **an operational contract**: maintain a naming convention, review changes, and plan dashboard migrations.

## 11. Spring Kafka Micrometer timer vs. Kafka client metrics

The `micrometerTags` discussed here primarily relate to **listener container** instrumentation. They do not automatically add labels to every metric emitted by Kafka clients, brokers, or producer exporters.

| Metric source | What does it measure? | Examples |
|---|---|---|
| Spring Kafka listener timer | Listener/handler invocation duration | `spring.kafka.listener` |
| Kafka consumer client metrics | Poll, fetch, records-lag, request latency, commit, rebalance | Metrics exported by Kafka client via JMX/Micrometer binder |
| Kafka producer client metrics | Batch, request, retries, error rate, buffer | Kafka producer metrics |
| Broker metrics | Under-replicated partitions, request queue, bytes in/out | Kafka broker/JMX exporter |
| Application custom metrics | DLT count, business throughput, inbox duplicates | Application-defined counters/timers/gauges |

If the question is "how much time does the listener spend calling the database?", a listener timer with a pipeline tag helps. If the question is "is the consumer stuck between two `poll()` calls?", you need Kafka client metrics, listener duration, and lifecycle logs. If the question is "is the DLT backlog growing?", you need DLT topic/group metrics or a dedicated application counter.

Do not treat `setMicrometerTags` as an API to configure broker metric tags or native Kafka client `client.id`. Those components have separate observability configuration paths.

## 12. Relationship with Micrometer Observation and tracing

Newer Spring Kafka versions support **Micrometer Observation** to combine metrics and distributed tracing. `ContainerProperties` may offer an `observationEnabled` option; with Observation enabled, instrumentation uses observation conventions and typically replaces legacy listener Micrometer timers.

```java
ContainerProperties properties = factory.getContainerProperties();

// Choose instrumentation based on version and tracing design.
properties.setObservationEnabled(true);
```

Important point: **legacy timer `micrometerTags` is not a general mechanism for adding tags to all Observations/spans**. If a service enables Observation, check the metric names, tags, and tracing context provided by the active observation convention. Customizing low-cardinality observation keys is typically done via an appropriate observation convention, not simply by continuing to add `setMicrometerTags` and expecting exporters to pick everything up.

Because meter/tag names and Observation support vary across Spring Kafka/Micrometer versions, verify behavior against `/actuator/metrics`, registry tests, or your monitoring backend. Do not enable multiple instrumentation modes simultaneously on the same listener without checking for duplicates or label changes.

### Metrics are not tracing

Metrics answer aggregate questions like error rate or p95 latency by service. Traces track an individual request/event across services. When you need to know where a specific `event_id` slowed down, use traces/span links and logs containing the event ID, rather than turning `event_id` into a metric label.

## 13. Producer-side Micrometer tags have a different scope

Spring Kafka also has a Micrometer timer mechanism for `KafkaTemplate` send operations in supported versions, with separate producer-side tag configuration. Do not confuse `ContainerProperties.setMicrometerTags` with producer template tag configuration.

```text
KafkaTemplate.send()  --> producer send timer / observation
                              |
                              +--> producer-side tags

@KafkaListener method --> listener container timer / observation
                              |
                              +--> ContainerProperties.micrometerTags
```

An event passing through both producer and consumer can be measured at both ends, but the two timers do not sum to end-to-end latency because broker storage, network, consumer polling, and queues sit in between. When you need to measure record age or end-to-end latency, design dedicated timestamps and telemetry with controlled clock skew.

If the application customizes `KafkaTemplate` metrics, check the actual API of your Spring Kafka version and avoid turning dynamic keys/payloads into tags. Still prefer bounded tags like `pipeline` or `message_family`.

## 14. Exporting metrics to Prometheus and reading timers correctly

With the Micrometer Prometheus registry, the `spring.kafka.listener` timer may be exported under Prometheus naming conventions, such as a metric family suffixed with `_seconds_count`, `_seconds_sum`, and related series. Exact names depend on Micrometer/registry/exporter versions and histogram configuration.

**Illustrative** PromQL examples—verify the actual exported names in your environment:

```promql
# Successful listener invocations per second, grouped by pipeline
sum by (pipeline) (
  rate(spring_kafka_listener_seconds_count{result="success"}[5m])
)
```

```promql
# Average listener duration (seconds/invocation) by pipeline
sum by (pipeline) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
sum by (pipeline) (
  rate(spring_kafka_listener_seconds_count[5m])
)
```

The average duration expression needs division-by-zero handling in dashboards. It is not p95 or p99. If you want reliable percentiles across multiple instances, configure appropriate distribution histogram/SLO buckets and use histogram queries instead of directly aggregating local percentiles computed on individual pods.

```promql
# p95 example usable only if corresponding histogram buckets exist
histogram_quantile(
  0.95,
  sum by (le, pipeline) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
```

Do not assume `_bucket` appears just because a timer exists: histogram buckets must be configured in Micrometer/Spring Boot distribution settings. For business errors, also use explicit metrics for recovered/DLT records instead of inferring everything from `result=failure` timers.

## 15. Which operational questions should Micrometer tags serve?

A good tag design starts from the questions on-call engineers must answer during a shift:

| Question | Tags likely needed | Complementary metrics |
|---|---|---|
| Which business flow is slowest? | `service`, `pipeline` | Listener p95/p99 latency |
| After a deploy, which service's errors increased? | `service`, `environment`, bounded version | Error rate, deploy timeline |
| Which event family causes high latency? | `event_family` from allowlist | Record count, processing duration |
| Is a slow dependency increasing consumer lag? | `pipeline` | DB/HTTP latency, consumer lag |
| Which business flow is affected by a retry storm? | `pipeline`, `service` | Retry attempts, retry-topic lag, DLT rate |

Keep the number of tags small enough to serve dashboards and alerts. Putting every analytical dimension into a single timer can create a large cross-product. If you need detailed breakdowns across hundreds of business states, consider domain-level metrics with standardized enums or log analytics instead of pushing everything into `micrometerTagsProvider`.

## 16. Multi-instance and aggregation

A Spring Kafka service may run multiple replicas, each with different listener concurrency. When all share `pipeline=orders`, the metrics backend can aggregate by pipeline; infrastructure tags such as `instance` and `pod` are usually added by the registry or exporter and do not necessarily need to be added manually in `micrometerTags`.

```text
orders-service replica A  --> spring.kafka.listener, pipeline=orders
orders-service replica B  --> spring.kafka.listener, pipeline=orders
orders-service replica C  --> spring.kafka.listener, pipeline=orders
                                         |
                                         v
                                    Prometheus
                                         |
                                         v
                             sum by (pipeline) (...)
```

**Consistency matters more than granularity.** If each replica writes the tag differently—such as `orders`, `order`, `order-service`—dashboards will split a single pipeline into multiple groups incorrectly. Tag values should come from standardized configuration or controlled enumerations.

Do not attach random container thread names or Kubernetes pod UIDs to custom `micrometerTags` if the backend already provides sufficient instance labels. Pod tags may have infrastructure-managed cardinality, but duplicating multiple tag levels does not improve diagnosis.

## 17. Performance and risks when using a provider

`micrometerTagsProvider` is invoked on the telemetry path of the record listener. Therefore, the provider function should be **pure, fast, and non-blocking**:

```java
// DO: O(1), reads one header and maps to a small value set.
properties.setMicrometerTagsProvider(SafeKafkaTags::fromRecord);

// DO NOT: call the database to decide a metric label.
// properties.setMicrometerTagsProvider(record -> database.findTenant(...));
```

Do not parse large JSON payloads just to build a tag, as this increases CPU usage and can throw errors on invalid payloads. Do not make network calls from the provider. Do not let a telemetry exception break the business listener; the provider must guard against missing headers, malformed bytes, or values outside the allowlist.

If records come from untrusted producers or carry arbitrary headers, bound the size and values turned into metrics. Treat every header as unvalidated input before converting it into a label.

## 18. Testing Micrometer tags with `MeterRegistry`

Rather than only inspecting configuration, you can verify **the actual meter after the listener processes a record**. In a Spring Boot test environment, `SimpleMeterRegistry` is a lightweight registry for observing metrics without an external backend.

Test configuration concept:

```java
@TestConfiguration
static class MetricsTestConfiguration {

    @Bean
    MeterRegistry testMeterRegistry() {
        return new SimpleMeterRegistry();
    }
}
```

After sending a valid record and confirming the listener finished processing, you can look up the timer by name and application tags:

```java
Collection<Timer> timers = registry
        .find("spring.kafka.listener")
        .tags("service", "order-processing")
        .tags("pipeline", "orders")
        .timers();

long invocations = timers.stream()
        .mapToLong(Timer::count)
        .sum();

assertThat(invocations).isGreaterThan(0);
```

This is an illustrative test snippet: you need to inject `MeterRegistry`, set up a Kafka test broker/producer, wait for the listener to finish using a latch or Awaitility, and ensure the application context has no other registry altering instrumentation conditions. If Observation is enabled, verify the actual meter/tracing name instead of asserting that legacy timers always exist.

Cases worth testing:

1. Record processed successfully: listener timer appears with expected static tags.
2. Listener throws exception: failure timer or observation is recorded according to framework/version mechanics.
3. Two listeners in different pipelines: metrics are not mislabeled from sharing a factory.
4. Provider encounters unknown header: returns `event_family=other`, without creating a raw header tag.
5. Batch listener: confirm exact timer recording behavior and provider scope for your version.
6. Application Observation enabled: confirm metric names and labels in the active telemetry pipeline.
7. Restart/rebalance: meter/tag counts do not grow abnormally from unstable runtime ID labels.

Do not write a test that only asserts a timer exists while ignoring `result`, `name`, or actual tag values. Inspect the meter IDs and tags recorded by the registry to confirm instrumentation is configured properly.

## 19. Troubleshooting: `micrometerTags` has no effect

| Symptom | Possible cause | What to check |
|---|---|---|
| `spring.kafka.listener` not visible | Micrometer lacks a suitable registry, timer disabled, no records yet, or Observation replaced legacy timers | Check dependencies, registry, `micrometerEnabled`, `observationEnabled`, traffic |
| Timer exists but custom tags are missing | Listener uses a different container factory or tags were not applied | Check `@KafkaListener` `containerFactory` and bean wiring |
| All listeners have `pipeline=orders` | Sharing one factory with orders-specific tags | Choose appropriate tag scope or separate factories |
| Prometheus shows hundreds of thousands of series | Provider uses unbounded event ID/key/tenant | Stop generating new tags, apply allowlist, handle stale series/retention in backend |
| Metrics only show success, no failure | No failure recorded yet or error handling semantics differ | Check listener/error handler behavior and actual meters |
| Grafana query returns empty | Wrong exporter metric name, wrong labels, histograms not enabled, or mismatched filter | Inspect actual exported series names before writing PromQL |
| Latency rises after enabling provider | Provider parses payload or performs IO, continuously creating meters | Switch to constant/enum mapping, remove IO, measure CPU and meter count |
| Tags missing in traces | `micrometerTags` is for timers; Observation has its own conventions | Check observation configuration and low-cardinality keys |
| Two sets of series appear after deploy | Renamed tag key/value or switched Observation mode | Standardize naming, update dashboards and migration plan |

For a "missing metric" issue, distinguish three layers: **is the listener processing records**, **is `MeterRegistry` being updated**, and **is the exporter/backend receiving the series**. If the registry already has the timer and tags but Prometheus does not see them, the issue lies in export/scrape/label filtering rather than `setMicrometerTags` alone.

## 20. Safe tag rollout process

Introducing `micrometerTags` into production should follow a controlled flow:

1. Identify what questions dashboards/alerts need to answer; choose minimal tags for the right scope.
2. Check current instrumentation: legacy Micrometer timers vs. Micrometer Observation, Spring Kafka version, and registry.
3. Define a consistent key naming convention, e.g. `service`, `pipeline`, `component`.
4. Place static tags on the appropriate container factory; avoid mislabeling multiple listeners into the same pipeline.
5. Use a provider only when per-record data is truly needed, and always normalize to a finite set of values.
6. Test success/failure records, inspect meter IDs, and verify tags in the registry.
7. Compare time series counts before and after the change; set cardinality/memory alerts on the monitoring backend.
8. Expose metrics through Actuator/Prometheus via secured mechanisms; verify actual exported metric names.
9. Deploy dashboards/alerts with proper filtering and aggregation, avoiding label filters that drop data.
10. Monitor listener performance, meter count, scrape latency, and storage costs after rollout.

If a custom tag needs a name or semantic change, treat it as a monitoring contract change. Update dashboards, recording rules, alert rules, and runbooks alongside the application release rather than just changing a string in code.

## 21. Core principles

1. `micrometerTags` is a **static tag map** supplementing Spring Kafka listener container metrics, not Kafka broker or consumer offset configuration.
2. When using listener timers, the common meter name is `spring.kafka.listener`; verify actual names/tags per version.
3. Enable and wire the proper Micrometer registry; calling the tag setter alone does not ensure exporter output.
4. Place tags on the right **container factory** to avoid mislabeling multiple business flows.
5. `micrometerTagsProvider` allows per-record tags when the API is supported, but values must be bounded via enum/allowlist.
6. Never put order IDs, event IDs, offsets, payloads, or exception messages in tags due to cardinality and privacy.
7. Listener timers do not replace Kafka client metrics, consumer lag, DLT metrics, or end-to-end tracing.
8. When enabling Micrometer Observation, verify observation conventions and metric names; do not assume legacy timer tags automatically carry over to traces.
9. Favor consistent metric tags across all replicas, with a clear schema and migration process.
10. Test with `MeterRegistry`, observe actual series in the backend, and monitor cardinality costs post-rollout.

**Conclusion:** `micrometerTags` turns generic listener timers into operationally contextualized signals: which service is slow, which pipeline is failing, and which team owns it. Real value comes from a **small, stable, meaningful** tag set placed at the right scope. Combining them with Kafka client metrics, consumer lag, retry/DLT monitoring, and tracing provides a fuller reliability picture without exploding time series counts or impacting the record processing path.

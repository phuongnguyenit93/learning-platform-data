# micrometerTagsProvider in Spring Kafka

In a production environment, Spring Kafka consumers must be observed across multiple layers: the Kafka client's ability to poll, listener invocation counts, processing duration per record, exception rates, consumer lag, retries/DLT, and business processing throughput. **`micrometerTagsProvider`** is an extension point allowing applications to **attach dynamic Micrometer tags based on `ConsumerRecord`** to listener timers.

For example, a listener processes multiple event types: `OrderCreated`, `OrderCancelled`, and `OrderShipped`. The average processing time of each group can differ greatly. If every invocation is recorded into the same timer metric, dashboards struggle to show which type is slow. With a dynamic tag `event_family=created`, `cancelled`, or `shipped`, counts and latencies can be broken down directly on the listener metric.

However, every tag value can create a new time series. If `orderId`, `eventId`, or Kafka key is used as a tag, series counts can grow into millions and overload the monitoring backend. Therefore, `micrometerTagsProvider` is both a useful tool and a place where **cardinality, performance, and privacy** must be tightly controlled.

This lesson is in the **Monitoring and metrics** chapter of the Spring Kafka Reliability Operations module. The content focuses on the mechanism, `ContainerProperties` API, Spring Boot configuration, practical examples, relationship with Micrometer Timer and Observation, and safe operation.

## 1. Where micrometerTagsProvider fits in the pipeline

A record flows from the Kafka broker to the listener method:

~~~text
Kafka broker
    |
    v
KafkaConsumer.poll()
    |
    v
ConsumerRecord<K, V>
    |
    v
Spring Kafka listener container
    |
    +--> Timer instrumentation
    |       |
    |       +--> Built-in tags
    |       +--> Static micrometerTags
    |       +--> Dynamic micrometerTagsProvider(record)
    |
    v
@KafkaListener
    |
    +--> Success
    |       |
    |       v
    |   Record success listener timer
    |
    +--> Exception
            |
            v
        Record failure listener timer
            |
            v
      Error handler / retry / DLT
~~~

The diagram depicts component responsibilities. Internal details regarding when tags are extracted and meter creation may vary by Spring Kafka version.

The provider **does not process records in place of the listener**. It does not commit offsets, route records to DLT, change partitions, alter `RetryTopicConfiguration`, or control `KafkaConsumer`. It only supplies additional metadata for listener metrics.

## 2. Core API on ContainerProperties

In supported Spring Kafka versions, `ContainerProperties` provides a setter for a dynamic tags provider:

~~~java
setMicrometerTagsProvider(
        Function<ConsumerRecord<?, ?>, Map<String, String>> provider
)
~~~

The signature illustrates the data types the API accepts:

- **Input:** Kafka client `ConsumerRecord`.
- **Output:** `Map` with `String` tag keys and `String` tag values.
- **Purpose:** add tags to Micrometer listener timers.
- **Timing:** during the listener container's record processing lifecycle.
- **Scope:** the container or containers created from the configured factory.

Short example:

~~~java
factory.getContainerProperties()
        .setMicrometerTagsProvider(record -> Map.of(
                "event_family",
                classifyTopic(record.topic())
        ));
~~~

The `classifyTopic` method is responsible for mapping topics to a small, controlled set of values.

Do not attach a provider to one factory and assume every listener in the application inherits that config. Each `@KafkaListener` can use a different `containerFactory`. Configuration must be applied to **the actual factory used by the listener**.

## 3. Differences between static tags, dynamic tags, and built-in tags

Spring Kafka can supply three tag sources for timers:

| Tag kind | Data source | Example | Purpose |
|---|---|---|---|
| Built-in tags | Framework listener instrumentation | name, result, exception | Identify listener and processing outcome |
| Static tags | `ContainerProperties.micrometerTags` | `service_area=orders` | Categorize by application/container |
| Dynamic tags | `ContainerProperties.micrometerTagsProvider` | `event_family=cancelled` | Categorize by `ConsumerRecord` |

Combined example:

~~~java
ContainerProperties props = factory.getContainerProperties();

props.setMicrometerEnabled(true);

props.setMicrometerTags(Map.of(
        "service_area", "orders",
        "processing_mode", "record"
));

props.setMicrometerTagsProvider(record -> Map.of(
        "event_family", classifyTopic(record.topic())
));
~~~

Static tags `service_area` and `processing_mode` do not change per record. The `event_family` tag can vary depending on the current topic.

Do not use the same tag key in both static and dynamic maps, nor reuse framework-owned keys such as `result` and `exception`. If multiple sources emit the same key, merge/overwrite rules may depend on implementation/version; it is far better to design non-colliding keys.

## 4. What is the listener timer measuring?

Spring Kafka can create a Micrometer Timer for listener processing duration, typically using the meter name **`spring.kafka.listener`**. Common tags depending on version include:

- **name:** listener/container name.
- **result:** `success` or `failure`.
- **exception:** exception type or a placeholder value when no error occurred.
- Custom tags provided by the application.

Example illustrative data point:

~~~text
Meter: spring.kafka.listener

name=ordersListener
result=success
exception=none
service_area=orders
processing_mode=record
event_family=created
~~~

The timer reflects listener invocations per framework instrumentation. It does not directly measure:

- Consumer lag.
- Kafka broker request latency.
- Time the record waited in the topic.
- Number of unique business events.
- End-to-end producer-to-outcome duration.
- Number of committed database transactions.
- DLT publish outcomes.

For example, a record sits in Kafka for 10 minutes due to backlog and then the listener processes it in 25 ms. The Listener Timer may record 25 ms, whereas end-to-end event age exceeds 10 minutes. These are completely different numbers.

## 5. Complete Java configuration with @KafkaListener

Example application processing order events:

~~~java
@Configuration
public class OrderKafkaMetricsConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        ContainerProperties properties =
                factory.getContainerProperties();

        properties.setMicrometerEnabled(true);

        properties.setMicrometerTags(Map.of(
                "service_area", "orders",
                "listener_type", "business"
        ));

        properties.setMicrometerTagsProvider(record -> Map.of(
                "event_family", classifyTopic(record.topic())
        ));

        return factory;
    }

    private static String classifyTopic(String topic) {
        return switch (topic) {
            case "orders.created" -> "created";
            case "orders.cancelled" -> "cancelled";
            case "orders.shipped" -> "shipped";
            default -> "other";
        };
    }
}
~~~

Listener using the right factory:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = {
                    "orders.created",
                    "orders.cancelled",
                    "orders.shipped"
            },
            groupId = "orders-service",
            containerFactory = "ordersListenerFactory"
    )
    public void onOrderEvent(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

In a real project, corresponding Spring Kafka, Spring Framework, and `java.util.Map` imports are required; `OrderEvent`, `OrderService`, and consumer deserializers are application components to implement.

Classification results:

| Record topic | event_family |
|---|---|
| orders.created | created |
| orders.cancelled | cancelled |
| orders.shipped | shipped |
| Topic not in allowlist | other |

Returning `other` instead of the raw topic name for unknown topics helps bound series counts.

## 6. When a single topic carries multiple event types

If all order events share one topic:

~~~text
orders.events
   |
   +--> OrderCreated
   +--> OrderCancelled
   +--> OrderShipped
   +--> OrderAddressChanged
~~~

Using `record.topic()` alone will not distinguish event types. You can read a header defined by the event contract and map it to a small list of allowed categories.

Example:

~~~java
private static String classifyEventType(
        ConsumerRecord<?, ?> record) {

    Header header =
            record.headers().lastHeader("event-type");

    if (header == null || header.value() == null) {
        return "unknown";
    }

    String value = new String(
            header.value(),
            StandardCharsets.UTF_8
    );

    return switch (value) {
        case "OrderCreated" -> "created";
        case "OrderCancelled" -> "cancelled";
        case "OrderShipped" -> "shipped";
        default -> "other";
    };
}
~~~

Provider:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "event_type",
        classifyEventType(record)
));
~~~

Properties of this approach:

1. Does not re-parse the entire JSON/Avro payload just to classify.
2. Has a fallback when the header is missing.
3. Has a fallback when a producer sends an unsupported event type.
4. Does not expose raw headers in metrics.
5. Values are bounded.
6. Handles null values without relying on domain objects.

Headers may come from a producer that is not fully trusted. **Never attach raw header values as metric tags**, even when the header is named `event-type`. Always use an allowlist or bucket mapping.

## 7. Configuring the provider with two bounded dimensions

You may want to distinguish both event family and processing lane:

~~~text
Topic orders.live   -> processing_lane=live
Topic orders.replay -> processing_lane=replay
Topic orders.retry  -> processing_lane=retry
Other topic         -> processing_lane=other
~~~

Example:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "event_type",
        classifyEventType(record),
        "processing_lane",
        classifyLane(record.topic())
));
~~~

Helper:

~~~java
private static String classifyLane(String topic) {
    return switch (topic) {
        case "orders.live" -> "live";
        case "orders.replay" -> "replay";
        case "orders.retry" -> "retry";
        default -> "other";
    };
}
~~~

Values should be governed as an **observability contract**. If a tag name changes or the meaning of `retry`/`replay` shifts, dashboards and alert queries may also need updates.

Specifically, with non-blocking retries, actual retry topic names depend on `RetryTopicConfiguration` and version. Do not try to parse arbitrary suffixes from any topic name if the topology is unverified; use mappings based on managed configuration.

## 8. Cardinality is the biggest risk of dynamic tags

A metric time series is distinguished by **meter name and its set of tag key/value pairs**. Every new value of a tag can spawn additional series.

Suppose:

~~~text
event_type:       5 values
processing_lane:  3 values
listener:         4 values
result:           2 values

Potential combinations:
5 × 3 × 4 × 2 = 120
~~~

If `tenant_id` with 10,000 values is added:

~~~text
120 × 10,000 = 1,200,000 potential combinations
~~~

This is only an illustrative model multiplication. Actual series also depend on observed combinations and sub-series generated by `count`, `sum`, `max`, or histogram buckets.

Excessively high tag cardinality can cause:

- Increased memory usage in Micrometer `MeterRegistry`.
- Larger scrape response sizes.
- Higher series counts in Prometheus or the monitoring backend.
- Higher ingestion rates and storage costs.
- Slower dashboard query execution.
- Dropped metrics due to rate limits.
- Delayed alerts or incomplete data.
- Turning instrumentation itself into a source of JVM pressure.

**Do not use `micrometerTagsProvider` as a detailed store for every record.** To look up a specific event, use log or trace correlation.

## 9. Fields to avoid as tags

| ConsumerRecord field or metadata | Problem | Alternative |
|---|---|---|
| `record.offset()` | Every record has a different offset | Logs with topic/partition/offset |
| `record.timestamp()` | Vast number of values over time | Measure event age with a histogram |
| `record.key()` | Often contains user/order/customer ID | Event category or tier |
| `eventId` | Almost unique per event | Tracing/log correlation |
| `orderId`/`paymentId` | High cardinality, potentially sensitive | Business domain |
| Raw `customerId`/`tenantId` | Can have thousands or millions of values | Finite customer/tenant tier |
| Raw exception message | Contains identifiers and variable text | Exception category |
| Free-form header sent by producer | Unbounded number of values | Allowlist mapping |
| Full class name from type header | Can change unpredictably | Schema/event family |
| Kafka topic per tenant | Topic count grows per tenant | Topic group |
| Pod UID changing across deploys | Series churn | Stable service identity |

Some values look low-cardinality initially but grow alongside customers or tenants. Design policies for future scale, not just initial development data.

## 10. Providers should be fast, pure, and side-effect free

A suitable provider:

~~~java
properties.setMicrometerTagsProvider(record -> {
    String family = switch (record.topic()) {
        case "orders.created" -> "created";
        case "orders.cancelled" -> "cancelled";
        default -> "other";
    };

    return Map.of("event_family", family);
});
~~~

An unsuitable provider:

~~~java
properties.setMicrometerTagsProvider(record -> {
    Customer customer = customerRepository.findById(
            String.valueOf(record.key())
    );

    return Map.of(
            "customer_name",
            customer.getName()
    );
});
~~~

Problems with the second example:

- Every record triggers an extra database query solely to generate a tag.
- When the database slows down, instrumentation slows the listener down further.
- When the DB loses connectivity, the provider can throw an exception.
- Customer name creates many series and can contain sensitive data.
- Performance-collecting instrumentation ends up altering the performance being measured.

Practical principles:

1. Only read metadata already present.
2. Never call DB, HTTP, Redis, schema registry, or object storage.
3. Never parse large payloads.
4. Never sleep or acquire long-held locks.
5. Never mutate the record, key, value, or headers.
6. Never retain the `ConsumerRecord` reference after the provider returns.
7. Never generate dynamic tag keys.
8. Never allow null tag values.
9. Provide an `unknown`/`other` fallback.
10. Never let a provider exception disrupt the instrumentation flow.

`Map.of` works well for small numbers of tags and immutable values. If using a mutable map, never share and mutate the same map object across multiple consumer threads.

## 11. Interaction with null values, tombstones, and deserialization errors

Not every record has a complete payload object.

- A Kafka tombstone is a valid record with a null value per compacted topic contracts.
- Key or value may suffer deserialization failure.
- Headers may not exist.
- Header values may be empty.
- Event type may be newer than the mapping.
- Value may not share the same Java class across topics.

A defensive helper:

~~~java
private static Map<String, String> tagsFor(
        ConsumerRecord<?, ?> record) {

    if (record == null) {
        return Map.of("event_type", "unknown");
    }

    Header header =
            record.headers().lastHeader("event-type");

    if (header == null || header.value() == null) {
        return Map.of("event_type", "unknown");
    }

    String type = new String(
            header.value(),
            StandardCharsets.UTF_8
    );

    return Map.of(
            "event_type",
            switch (type) {
                case "OrderCreated" -> "created";
                case "OrderCancelled" -> "cancelled";
                default -> "other";
            }
    );
}
~~~

In normal flow the framework supplies `ConsumerRecord` per contract; the null branch shows how to make a helper resilient when reused across places.

**Do not use `record.value()==null` to decide a `deserialize_error` tag.** A tombstone is a valid null value. To distinguish deserialization failures, rely on `ErrorHandlingDeserializer` metadata and the actual error-handling path.

Some errors occur during `KafkaConsumer.poll()` before a valid record is produced to invoke the listener. Consequently, **the listener timer and `micrometerTagsProvider` may not run for those errors**. Supplement with error-handler, DLT, log, or consumer metrics.

## 12. The provider does not know the listener processing outcome

A common misconception is manually adding:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "result", "success"
));
~~~

This value is decided when the record arrives, not as the result of business logic. If the listener throws an exception afterward, a custom `result=success` creates misleading semantics or conflicts with the built-in `result` tag.

The provider fits **existing properties of the input record**. For post-processing business outcomes, use:

- Built-in listener timer `result`/`exception` tags.
- Custom `MeterRegistry` counters inside the business service.
- `DefaultErrorHandler`/recoverer instrumentation.
- Observation conventions if the goal is context beyond legacy timers.
- Structured logs/traces for failure details.

Example counter grouping business failures:

~~~java
@Service
public class OrderFailureMetrics {

    private final MeterRegistry registry;

    public OrderFailureMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void incrementFailure(String reasonCode) {
        registry.counter(
                "orders.processing.failures",
                "reason",
                normalize(reasonCode)
        ).increment();
    }

    private static String normalize(String reasonCode) {
        return switch (reasonCode) {
            case "DB_TIMEOUT" -> "database";
            case "INVALID_EVENT" -> "validation";
            case "PARTNER_UNAVAILABLE" -> "dependency";
            default -> "other";
        };
    }
}
~~~

Reasons must have a finite value set. Never attach raw exception messages, SQL queries, or Kafka keys to counters.

## 13. Enable Micrometer listener timers properly

Example:

~~~java
ContainerProperties properties =
        factory.getContainerProperties();

properties.setMicrometerEnabled(true);

properties.setMicrometerTagsProvider(
        record -> Map.of("event_family", classifyTopic(record.topic()))
);
~~~

If listener timers are disabled or Micrometer is absent from the classpath, the provider may not yield the expected metrics.

In Spring Boot, dependencies typically involve Actuator and an export registry:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

This is a Maven example. With Gradle, declare the equivalent dependencies and let the Spring Boot BOM manage compatible versions.

Having a Micrometer Timer in-process **does not mean metrics have reached Prometheus**. You also need:

- An appropriate registry.
- Endpoint exposure.
- Security/network restrictions.
- Prometheus scrape configuration.
- Application/target labels.
- Data retention and alert rules.

Never leave the `/actuator/prometheus` endpoint publicly open without access controls.

## 14. How to read listener Timers

A Micrometer Timer can record:

- **count:** number of measured invocations.
- **total time:** cumulative duration.
- **max:** maximum within the registry's statistical window.
- **histogram/percentiles:** when the corresponding feature is enabled.

An illustrative meter:

~~~text
spring.kafka.listener
  name=ordersListener
  result=success
  exception=none
  service_area=orders
  event_family=cancelled
~~~

If 100 invocations of `event_family=cancelled` take 8 seconds total, the average invocation time is 80 ms. That says nothing about how long records sat in Kafka before being polled.

Do not confuse Timer count with unique orders. One event may be processed three times due to retries and counted as three invocations if all three are instrumented.

## 15. Metric names in Prometheus

Micrometer uses an abstraction name like `spring.kafka.listener`. When exported to Prometheus, the metric name may be normalized to forms such as:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
~~~

Actual names depend on Micrometer/registry naming conventions and Spring Kafka version. Check endpoint/scrape output before building dashboards.

PromQL example for listener invocation rate by event family:

~~~promql
sum by (event_family, result) (
  rate(spring_kafka_listener_seconds_count[5m])
)
~~~

Average listener duration example:

~~~promql
sum by (event_family) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
sum by (event_family) (
  rate(spring_kafka_listener_seconds_count[5m])
)
~~~

If a query returns no data, check exported series names and labels, whether timers are enabled, exporter configuration, and whether the listener is actually receiving records.

## 16. Percentiles require histograms or distribution statistics

To inspect P95/P99 listener latency, configure the Timer to export histogram buckets or appropriate distribution statistics.

If Prometheus histogram buckets exist, illustrative query:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, event_family) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

If `_bucket` series are not exported, the query cannot compute percentiles from missing data.

When enabling histograms:

- Series counts increase per bucket and per tag combination.
- Know latency SLOs to pick useful buckets.
- If an `event_family` has few samples, P99 can be unstable.
- Avoid enabling histograms on high-cardinality metrics.
- Consider monitoring backend cost.

A timer with good P95 while backlog grows rapidly can still indicate an unhealthy system. Monitor event age and consumer lag alongside it.

## 17. MeterFilter helps guard tag value counts

Micrometer provides `MeterFilter` to cap certain tag values. Illustrative example:

~~~java
@Bean
MeterFilter kafkaEventFamilyGuard() {
    return MeterFilter.maximumAllowableTags(
            "spring.kafka.listener",
            "event_family",
            10,
            MeterFilter.deny()
    );
}
~~~

The goal is to prevent distinct `event_family` values from exceeding a threshold, per the API capabilities of the Micrometer version in use.

**`MeterFilter` does not replace an allowlist in the provider.** Once the limit is reached, new meters may be denied and metrics become incomplete. Dropping metrics does not fix an unbounded tag generator.

Good design uses multiple layers:

1. Allowlist/bucket mapping in the provider.
2. Tests for invalid headers.
3. Limiting tag keys.
4. `MeterFilter` guardrails where needed.
5. Alerts on series counts/scrape size.
6. Logs/meters when tag mapping falls into `unknown`/`other` too frequently.
7. Reviewing the tag contract when business adds new event types.

## 18. One provider shared across multiple listeners

A single `ConcurrentKafkaListenerContainerFactory` can be shared by multiple `@KafkaListener` methods.

~~~text
ordersListenerFactory
     |
     +--> ordersCreatedListener
     +--> ordersCancelledListener
     +--> ordersReplayListener
     |
     +--> shared micrometerTagsProvider
~~~

Advantages:

- Consistent mapping.
- Less duplicate code.
- Easier dashboard aggregation.
- Easier to enforce a uniform cardinality policy.

However, if `paymentListenerFactory` is a different bean, it will not automatically inherit the provider from `ordersListenerFactory`.

Using two factories for two distinct event-type scopes makes sense when domains have separate metric contracts. Do not copy an overly generic provider that reads arbitrary headers across every domain to classify everything.

A common mistake is configuring the default `kafkaListenerContainerFactory` bean while `@KafkaListener` explicitly specifies `containerFactory="paymentsFactory"`. In that case, metrics tagging must be placed on `paymentsFactory` or shared configuration logic must apply to it.

## 19. Concurrency and multi-pod deployment

With container `concurrency=3`, Spring Kafka can create three child Kafka consumers:

~~~text
ordersListener parent
    |
    +--> child 0: P0, P1
    +--> child 1: P2, P3
    +--> child 2: P4, P5
~~~

Records flowing through multiple child consumers can still receive the same tag mapping.

However, series counts can still multiply by listener name, exception/result, application instance, and exporter labels. To stay in control:

- Never add random instance UUIDs from records into tags.
- Avoid attaching `partition` unless clearly needed.
- Use Prometheus scrape target labels for pod/namespace when needed.
- Avoid semantic duplication between static `service` tags and exporter service labels.
- Monitor series churn during rolling deploys.
- Never treat a single child consumer as a unique business event stream.

`micrometerTagsProvider` operates locally in-process. Pods do not share an in-memory `MeterRegistry`; the central monitoring system consolidates metrics across pods.

## 20. Should you tag topic and partition?

`topic` and `partition` are easy fields to read:

~~~java
record.topic()
record.partition()
~~~

Yet suitability depends on scale:

| Tag | When acceptable | When to avoid |
|---|---|---|
| `topic` | 3–10 stable topics | Continuously growing per-tenant/day/job topics |
| `partition` | Small partition count and real need to diagnose timers per partition | Hundreds/thousands of partitions multiplied across many tags |
| `topic_group` | When mapping topics into a finite group | Lower risk than raw `topic` |
| `event_type` | With an allowlist | Unbounded raw/free-form headers |
| `tenant_tier` | With a small finite set of tiers | Per-customer `tenantId` |

Safer `topic_group` mapping example:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "topic_group",
        switch (record.topic()) {
            case "orders.created" -> "orders";
            case "payments.authorized" -> "payments";
            default -> "other";
        }
));
~~~

If you need consumer lag per partition, use Kafka client/group metrics instead of multiplying a `partition` tag into every listener Timer. Listener latency and lag are different concepts.

## 21. Retries, DLT, and listener measurement counts

A record can fail and then retry:

~~~text
orders.events
     |
     +--> Listener attempt 1: failure
     |
     +--> Listener attempt 2: failure
     |
     +--> Listener attempt 3: success
~~~

Timer count can reflect three listener invocations, not three unique events. When non-blocking retries use retry topics, the record can pass through one or more different listener endpoints and emit multiple metrics with different names/topics.

Do not use `micrometerTagsProvider` to guess the attempt number from Kafka offsets or topic suffixes without a guaranteed contract. If retry metrics are needed:

- Counter for attempt counts.
- Counter for publishes to retry topics.
- Counter for DLT publishes.
- Consumer lag on each retry topic.
- End-to-end event completion latency.
- Duplicate detection metrics at the business layer.

Grouping `processing_lane=source/retry/replay` can be helpful when topology mapping is finite and explicit.

## 22. Deserialization errors may have no listener timer

Some errors occur before the `@KafkaListener` method is invoked:

~~~text
KafkaConsumer.poll()
     |
     v
Deserializer fails
     |
     +--> Listener has not received the record
     |
     +--> Invocation timer is not necessarily created
     |
     +--> micrometerTagsProvider may not run
~~~

Therefore, the listener Timer failure count does not always equal the count of malformed records.

With Spring Kafka, `ErrorHandlingDeserializer` can turn deserialization failures into metadata/headers for `CommonErrorHandler` to handle. However, when listener metrics are recorded depends on the error path and version.

Observe a combination of:

- Deserialization errors.
- Schema registry errors.
- `DefaultErrorHandler`/recovery metrics.
- DLT publish failures.
- Consumer lag.
- Kafka client poll errors.
- Logs containing appropriate topic/partition/offset.

Providers must not read `value` directly assuming it is always an `OrderEvent` object. It may be null or an unconverted failure.

## 23. Batch listeners and limits of per-record providers

`micrometerTagsProvider` takes a single `ConsumerRecord`, so it fits **record listeners** naturally.

A batch listener can receive:

~~~java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "batchFactory"
)
public void onOrders(List<OrderEvent> batch) {
    orderService.processBatch(batch);
}
~~~

A batch contains multiple event types and does not necessarily have a single `event_type` representing the entire batch.

~~~text
Batch:
  OrderCreated
  OrderCancelled
  OrderCreated
  OrderShipped
~~~

With a batch listener, **do not assume the provider creates per-record tags or separate timers per record**. Specific support depends on Spring Kafka version and listener instrumentation type.

If per-item metrics are needed inside a batch, record counters by event type in business code with explicit semantics, such as items attempted vs. items completed. If a batch fails mid-way, those two metrics will differ.

Do not divide total batch duration by record count and call it per-record latency if bulk operations have non-linear cost.

## 24. Micrometer Timer and Micrometer Observation are not equivalent

Modern Spring Kafka supports Micrometer Observation, which can unify metrics and tracing.

| Criterion | Micrometer Timer + micrometerTagsProvider | Micrometer Observation |
|---|---|---|
| Purpose | Timer duration/count by tags | Observation lifecycle, metrics, and tracing |
| Extension point | `ContainerProperties.micrometerTagsProvider` | Observation convention/handler |
| Input metadata | `ConsumerRecord` in provider | Corresponding Observation context |
| Low-cardinality data | Suitable for metrics | Used to group metrics |
| High-cardinality data | Should not go in tags | May suit tracing after privacy/sampling review |
| Trace spans | Does not automatically create full spans | Can create spans if configured |
| Enable flag | `micrometerEnabled` | `observationEnabled` |

Example enabling Observation:

~~~java
factory.getContainerProperties()
        .setObservationEnabled(true);
~~~

In many Spring Kafka versions, when Observation is enabled, the legacy listener Timer mechanism does not continue running as before. **Do not assume `micrometerTagsProvider` automatically applies to observation metrics or trace spans**.

If a project migrates from Micrometer Timer to Observation, review Observation convention extension points, metric names, tags, and corresponding dashboards. This is an instrumentation change, not just flipping a boolean.

## 25. Low-cardinality tags and tracing attributes

**Low-cardinality** values have a finite set, suitable for metrics:

~~~text
event_family = created | cancelled | shipped | other
processing_lane = source | retry | replay
service_area = orders | payments | notifications
~~~

**High-cardinality** values have large or nearly unique sets:

~~~text
event_id = evt-...
order_id = 983721
trace_id = 46fa...
user_id = 200348
~~~

High-cardinality attributes generally belong in logs/traces with controlled sampling, retention, and privacy. Not all specific data is allowed in traces; secrets, PII, and sensitive data must be handled under data protection policies.

Two different questions:

- **Metrics:** What is the P95 listener latency for the `cancelled` group over the last 15 minutes?
- **Tracing:** At which database step did event `evt-123` slow down?

The first question fits low-cardinality tags. The second needs a correlation ID in logs/traces rather than creating a dedicated Timer series for `evt-123`.

## 26. Do not confuse Timer count with unique business events

Suppose record E is redelivered:

~~~text
E attempt 1 --> DB timeout
E attempt 2 --> DB timeout
E attempt 3 --> success
~~~

The Spring Kafka listener may be called three times. The business system may complete only one logical operation.

| Metric | What is counted |
|---|---|
| Listener Timer count | Invocations measured by instrumentation |
| Retry count | Retries per policy |
| Unique business event count | Unique event IDs completed |
| Database mutation count | DB mutations actually applied |
| DLT publish count | Records sent to DLT |
| Duplicate rejected count | Redeliveries blocked by idempotency |

Do not conclude the producer created three new orders just because the Timer count increased by three. Monitoring must separate attempt-based metrics from logical-operation-based metrics.

## 27. Combining listener metrics with consumer lag and database metrics

A reliability dashboard should combine:

~~~text
Listener Timer p95
       |
       +--> Kafka consumer lag
       |
       +--> Listener failure rate
       |
       +--> Retry/DLT rate
       |
       +--> HikariCP active/waiting
       |
       +--> Database query p95/p99
       |
       +--> Pause/resume state
       |
       +--> Oldest unprocessed event age
~~~

For example, a listener is paused because the database is overloaded. While paused, Timer count may stop rising since no new invocations occur. Timer p95 might look healthy while consumer lag and event age climb rapidly. Looking only at the Timer could miss the incident.

Conversely, high Timer p95 without rising consumer lag might simply represent a low-traffic, more expensive event group; rely on SLAs rather than a single number.

`micrometerTagsProvider` helps **break down listener metrics by record group**, without turning it into a full-system measurement tool.

## 28. Common configuration mistakes

### Provider does not add new tags

Check the right container factory, `micrometerEnabled`, Micrometer dependencies, Observation mode, exporter, and whether the listener actually receives records. If the listener uses another factory, update the right factory.

### Every tag becomes `other`

The allowlist does not match actual topics/headers. Check the mapping contract; do not fix it by returning unbounded raw headers.

### Series count spikes sharply

A tag includes raw Kafka keys, `tenantId`, `eventId`, `offset`, `timestamp`, or an unbounded header. Replace with a bounded mapping and add a `MeterFilter`.

### Provider throws NullPointerException

Header/value/key may be null or a map was built with null. Return `unknown`/`other` and avoid passing null values to `Map.of`.

### Listener latency increases after adding tag provider

The provider is parsing large payloads, calling DB/API, or blocking. Switch to lightweight in-memory mapping.

### Timer reports success even though DB operation is unfinished

The listener may dispatch an async task and return early. The timer reflects the callback, unaware of actual work completion. Fix the completion/ack boundary and add business metrics.

### P95 query returns no data

Histogram buckets may not be enabled or series names differ. Inspect actual scraped data.

### Metrics missing for deserialization failures

Errors may happen before the listener method and timer run. Add error-handler/DLT/deserializer metrics.

### Retries make count exceed event count

Invocation count is not unique event count. Add idempotency/business counters and separate dashboard panels.

### Multiple pods produce constantly changing instance tags

Never add random UUIDs inside provider tags. Use stable infrastructure labels or scrape target metadata.

## 29. Testing to verify wiring and semantics

Test mapping logic first:

| Input | Expected tag |
|---|---|
| orders.created | `event_family=created` |
| orders.cancelled | `event_family=cancelled` |
| orders.shipped | `event_family=shipped` |
| An unknown topic | `event_family=other` |
| Missing `event-type` header | `event_type=unknown` |
| Arbitrary `event-type` header | `event_type=other` |

To verify integration, wire a container factory with the provider and a `MeterRegistry`. Use suitable Kafka test infrastructure to send records and inspect the recorded listener meters.

Cases to observe:

1. Listener success.
2. Listener exception and retry.
3. Multiple event types on the same topic.
4. Missing/null headers.
5. Concurrent child consumers.
6. Listeners using a different factory.
7. Observation enabled replacing Timer.
8. Batch listener.
9. Deserialization error before method.
10. Actual Prometheus exporter showing the new tags.

A unit test calling `classifyTopic` directly does not prove the provider is wired into the Spring Kafka listener container. Integration tests confirm wiring and actual metric names.

## 30. Team-wide tag contract design rules

Large services often have multiple listeners; multiple services need centralized dashboards. Agree on:

| Tag key | Expected values | Source |
|---|---|---|
| `service_area` | `orders`, `payments`, `notifications` | Static config |
| `event_family` | `created`, `cancelled`, `shipped`, `other` | Topic/header allowlist |
| `processing_lane` | `source`, `retry`, `replay`, `other` | Topic mapping |
| `schema_family` | `order_v1`, `order_v2`, `other` | Schema contract |
| `deployment_tier` | `dev`, `staging`, `prod` | Static config |

Principles:

- Tag keys are named consistently.
- Never reuse the same tag key with different meanings.
- Values must be finite.
- Include `unknown`/`other` fallbacks.
- Never store PII or secrets.
- Never copy raw Kafka headers into tags.
- When changing allowed values, review dashboard/alert dependencies.
- Set a series budget before expanding tenants/topics.
- Monitor cardinality and scrape cost over time.

If a team requests adding a `customerId` tag for debugging, explain that this goal should be solved with log/tracing correlation rather than per-customer time series.

## 31. Pre-production checklist

- The listener actually uses the factory configured with `micrometerTagsProvider`.
- Micrometer Timer mode is enabled and the version supports the API.
- The provider accepts `ConsumerRecord` and returns `Map<String,String>`.
- Static tags and dynamic tags have distinct roles with no colliding keys.
- All dynamic tag values are normalized through an allowlist.
- `eventId`, `orderId`, `offset`, `timestamp`, Kafka keys, or raw `tenantId` are never used.
- Missing/null/unknown headers do not break the provider.
- Tombstones and deserialization failures are properly understood.
- The provider never calls DB, HTTP, Redis, schema registry, or storage.
- The provider never blocks or mutates the record.
- Maps contain no null keys/values.
- Metric series cardinality has been estimated and monitored.
- `MeterFilter` guardrails exist if the monitoring backend needs them.
- Metric names and labels are verified against the actual exporter.
- P95/P99 are used only when histograms/distributions are configured.
- Listener timers are distinguished from Kafka client metrics and consumer lag.
- Invocation counts are not confused with unique business event counts.
- Retries/DLT have dedicated metrics, not relying solely on the provider.
- Batch listeners are not assumed to behave as per-record timers.
- Observation mode is configured via the appropriate extension points.
- Dashboards/alerts cover listener failure rate, latency, lag, and downstream saturation.
- Multi-factory, concurrency, multiple replicas, and unknown headers have been tested.

**Conclusion:** `micrometerTagsProvider` lets Spring Kafka generate **dynamic tags from each `ConsumerRecord`** to segment Micrometer listener timers by useful traits such as event family or processing lane. Its value lies in identifying which record group is slow, failing, or impacted after a deploy without duplicating listener code. To stay safe, providers must be **fast, pure, side-effect free, null-safe, and bounded to finite tag values**. These metrics should be combined with Kafka lag, retry/DLT, database metrics, and Observation/tracing, since listener Timers do not represent the full delivery guarantee or end-to-end reliability.

